"""Pure wait verdict for CI job snapshots."""

from __future__ import annotations

import argparse
import sys
import urllib.parse
from collections.abc import Callable, Sequence, Set
from dataclasses import dataclass
from enum import Enum

HARD_CONCLUSIONS = frozenset({"failure", "timed_out", "startup_failure"})


class TargetError(ValueError):
    """A target argument or git remote could not be used."""


class Verdict(Enum):
    WAIT = "wait"
    OK = "ok"
    FAILED = "failed"
    SUPERSEDED = "superseded"
    TIMED_OUT = "timed_out"


@dataclass(frozen=True)
class Target:
    kind: str
    value: str


@dataclass(frozen=True)
class Remote:
    name: str
    host: str
    slug: str


@dataclass(frozen=True)
class Job:
    name: str
    url: str
    done: bool
    conclusion: str | None
    allowed_failure: bool


@dataclass(frozen=True)
class Run:
    id: str
    url: str
    status: str
    superseded: bool
    jobs: tuple[Job, ...]


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    reason: str
    job: Job | None = None
    run: Run | None = None
    pending: tuple[Job, ...] = ()
    runs: tuple[Run, ...] = ()


def parse_targets(raw: Sequence[str], kinds: Set[str]) -> tuple[Target, ...]:
    """Parse one or more KIND:VALUE targets. Kind must be in ``kinds``."""
    if not raw:
        raise TargetError("at least one target is required")
    parsed: list[Target] = []
    for item in raw:
        kind, sep, value = item.partition(":")
        if not sep or not kind or not value:
            raise TargetError(f"target must be KIND:VALUE, got {item!r}")
        if kind not in kinds:
            allowed = ", ".join(sorted(kinds))
            raise TargetError(f"unknown target kind {kind!r}; expected one of: {allowed}")
        parsed.append(Target(kind, value))
    return tuple(parsed)


def parse_remotes(text: str) -> tuple[Remote, ...]:
    """Parse fetch lines from ``git remote -v``."""
    found: list[Remote] = []
    seen: set[tuple[str, str, str]] = set()
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 3 or parts[2] != "(fetch)":
            continue
        parsed = _remote_url(parts[1])
        if parsed is None:
            continue
        host, slug = parsed
        key = (parts[0], host, slug)
        if key in seen:
            continue
        seen.add(key)
        found.append(Remote(parts[0], host, slug))
    return tuple(found)


def choose_remote(
    remotes: Sequence[Remote],
    *,
    accept_hosts: Set[str] | None = None,
    reject_hosts: Set[str] = frozenset(),
) -> Remote:
    """Pick one remote. Prefer ``origin`` when several match."""
    matches = [
        remote
        for remote in remotes
        if (accept_hosts is None or remote.host in accept_hosts) and remote.host not in reject_hosts
    ]
    if not matches:
        raise TargetError("no matching git remote")
    origins = [remote for remote in matches if remote.name == "origin"]
    if len(origins) == 1:
        return origins[0]
    if len(matches) == 1:
        return matches[0]
    raise TargetError("several git remotes match; pass a repo whose origin is the forge you want")


def allowed_job_names(workflow: str) -> frozenset[str]:
    """Job ids and static names with job-level ``continue-on-error: true``.

    Names containing ``${{`` are omitted. Flags under ``steps`` are ignored.
    """
    lines = workflow.splitlines()
    start = next((i for i, line in enumerate(lines) if _strip_comment(line).rstrip() == "jobs:"), None)
    if start is None:
        return frozenset()
    return frozenset(_jobs_after(lines[start + 1 :]))


def decide(runs: tuple[Run, ...], *, fail_on_allowed: bool) -> Decision:
    """Halt on hard failure or superseded; otherwise wait or judge aggregates."""
    if not runs:
        return Decision(Verdict.WAIT, "pending", runs=runs)

    for run in runs:
        for job in run.jobs:
            if not job.done or job.conclusion not in HARD_CONCLUSIONS:
                continue
            if job.allowed_failure and not fail_on_allowed:
                continue
            return Decision(Verdict.FAILED, "job", job=job, run=run, runs=runs)

    superseded = next((run for run in runs if run.superseded), None)
    if superseded is not None:
        return Decision(Verdict.SUPERSEDED, "superseded", run=superseded, runs=runs)

    pending = tuple(job for run in runs for job in run.jobs if not job.done)
    if pending or any(run.status == "pending" for run in runs):
        return Decision(Verdict.WAIT, "pending", pending=pending, runs=runs)

    blocked = next((run for run in runs if run.status == "blocked"), None)
    if blocked is not None:
        return Decision(Verdict.FAILED, "blocked", run=blocked, runs=runs)

    serious = next((run for run in runs if run.status in {"failure", "cancelled", "skipped"}), None)
    if serious is not None:
        return Decision(Verdict.FAILED, "aggregate", run=serious, runs=runs)

    other = next((run for run in runs if run.status != "success"), None)
    if other is not None:
        return Decision(Verdict.FAILED, "aggregate", run=other, runs=runs)
    return Decision(Verdict.OK, "ok", runs=runs)


def watch(
    fetch: Callable[[], tuple[Run, ...]],
    *,
    fail_on_allowed: bool,
    timeout_s: float | None,
    sleep: Callable[[float], None],
    monotonic: Callable[[], float],
    interval_s: float = 15,
    max_interval_s: float = 60,
) -> Decision:
    """Poll ``fetch`` until a terminal verdict or timeout. Backoff doubles to max."""
    start = monotonic()
    interval = interval_s
    seen: tuple[Run, ...] = ()
    while True:
        seen = fetch()
        decision = decide(seen, fail_on_allowed=fail_on_allowed)
        if decision.verdict is not Verdict.WAIT:
            return decision
        if timeout_s is not None and monotonic() - start >= timeout_s:
            return _timed_out(seen)
        delay = interval
        if timeout_s is not None:
            remaining = timeout_s - (monotonic() - start)
            if remaining <= 0:
                return _timed_out(seen)
            delay = min(delay, remaining)
        sleep(delay)
        interval = min(interval * 2, max_interval_s)


def format_report(decision: Decision) -> str:
    """Render the short wait report."""
    if decision.verdict is Verdict.OK:
        return "OK\n"
    if decision.verdict is Verdict.FAILED and decision.reason == "job" and decision.job is not None:
        job = decision.job
        return f"Failed\njob: {job.name}\nconclusion: {job.conclusion}\nurl: {job.url}\n"
    if decision.verdict is Verdict.FAILED and decision.reason == "blocked" and decision.run is not None:
        run = decision.run
        return f"Blocked\naggregate: {run.status}\nrun: {run.id}\nurl: {run.url}\n"
    if decision.verdict is Verdict.FAILED and decision.run is not None:
        run = decision.run
        return f"Failed\naggregate: {run.status}\nrun: {run.id}\nurl: {run.url}\n"
    if decision.verdict is Verdict.SUPERSEDED and decision.run is not None:
        run = decision.run
        return f"Superseded\nrun: {run.id}\nurl: {run.url}\n"
    if decision.verdict is Verdict.TIMED_OUT:
        return _format_timeout(decision)
    raise ValueError(f"cannot format {decision.verdict}")


def exit_code(verdict: Verdict) -> int:
    """Process status for a terminal verdict."""
    return {
        Verdict.OK: 0,
        Verdict.FAILED: 1,
        Verdict.SUPERSEDED: 2,
        Verdict.TIMED_OUT: 3,
    }[verdict]


def argument_parser(prog: str) -> argparse.ArgumentParser:
    """CLI shared by the forge scripts. Usage errors exit 1."""

    class Parser(argparse.ArgumentParser):
        def error(self, message: str) -> None:
            self.print_usage(sys.stderr)
            print(f"{self.prog}: error: {message}", file=sys.stderr)
            raise SystemExit(1)

    parser = Parser(prog=prog)
    parser.add_argument(
        "--fail-on-allowed",
        action="store_true",
        help="halt on a job the workflow marks as allowed to fail",
    )
    parser.add_argument("--timeout", type=float, help="seconds before reporting unfinished jobs")
    parser.add_argument("targets", nargs="+", help="KIND:VALUE target, repeatable")
    return parser


def _timed_out(runs: tuple[Run, ...]) -> Decision:
    pending = tuple(job for run in runs for job in run.jobs if not job.done)
    return Decision(Verdict.TIMED_OUT, "timeout", pending=pending, runs=runs)


def _format_timeout(decision: Decision) -> str:
    lines = ["Timed out"]
    wrote = False
    for job in decision.pending:
        lines.append(f"job: {job.name}")
        lines.append("status: pending")
        lines.append(f"url: {job.url}")
        wrote = True
    for run in decision.runs:
        if run.status != "pending" or any(not job.done for job in run.jobs):
            continue
        lines.append(f"run: {run.id}")
        lines.append("status: pending")
        lines.append(f"url: {run.url}")
        wrote = True
    if not wrote:
        lines.append("runs: none")
    return "\n".join(lines) + "\n"


def _jobs_after(lines: Sequence[str]) -> set[str]:
    names: set[str] = set()
    job_indent: int | None = None
    body_indent: int | None = None
    job_id: str | None = None
    job_name: str | None = None
    allowed = False

    def flush() -> None:
        nonlocal job_id, job_name, allowed
        if job_id and allowed:
            names.add(job_id)
            if job_name is not None:
                names.add(job_name)
        job_id = None
        job_name = None
        allowed = False

    for line in lines:
        raw = _strip_comment(line).rstrip()
        if not raw.strip():
            continue
        indent = _indent(raw)
        if job_indent is None:
            job_indent = indent
        if indent < job_indent:
            break
        if indent == job_indent:
            flush()
            body_indent = None
            key, _, _rest = raw.strip().partition(":")
            job_id = _unquote(key.strip())
            continue
        if job_id is None:
            continue
        if body_indent is None:
            body_indent = indent
        if indent != body_indent:
            continue
        key, _, rest = raw.strip().partition(":")
        key = key.strip()
        if key == "continue-on-error" and rest.strip() == "true":
            allowed = True
        elif key == "name":
            job_name = _static_name(rest)
    flush()
    return names


def _static_name(value: str) -> str | None:
    plain = _unquote(value.strip())
    if not plain or plain in {">", "|", ">-", "|-", ">+", "|+"} or "${{" in plain:
        return None
    return plain


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _strip_comment(line: str) -> str:
    in_single = False
    in_double = False
    for index, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            return line[:index]
    return line


def _indent(line: str) -> int:
    count = 0
    for char in line:
        if char != " ":
            break
        count += 1
    return count


def _remote_url(url: str) -> tuple[str, str] | None:
    url = url.strip()
    if url.endswith(".git"):
        url = url[: -len(".git")]
    if url.startswith("git@") and ":" in url[4:]:
        host, _, path = url[4:].partition(":")
        return _host(host), path.strip("/")
    if "://" not in url:
        return None
    parsed = urllib.parse.urlparse(url)
    if not parsed.hostname:
        return None
    return _host(parsed.hostname), parsed.path.strip("/")


def _host(host: str) -> str:
    host = host.lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    return host

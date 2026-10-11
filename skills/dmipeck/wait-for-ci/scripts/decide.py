"""Pure wait verdict for CI job snapshots."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

HARD_CONCLUSIONS = frozenset({"failure", "timed_out", "startup_failure"})


class Verdict(Enum):
    WAIT = "wait"
    OK = "ok"
    FAILED = "failed"
    SUPERSEDED = "superseded"
    TIMED_OUT = "timed_out"


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


def decide(runs: tuple[Run, ...], *, fail_on_allowed: bool) -> Decision:
    """Halt on the first hard failure; otherwise wait or judge finished runs."""
    if not runs:
        return Decision(Verdict.WAIT, "pending", runs=runs)

    for run in runs:
        for job in run.jobs:
            if not job.done or job.conclusion not in HARD_CONCLUSIONS:
                continue
            if job.allowed_failure and not fail_on_allowed:
                continue
            return Decision(Verdict.FAILED, "job", job=job, run=run, runs=runs)

    pending = tuple(job for run in runs for job in run.jobs if not job.done)
    if pending or any(run.status == "pending" for run in runs):
        return Decision(Verdict.WAIT, "pending", pending=pending, runs=runs)

    superseded = next((run for run in runs if run.superseded), None)
    if superseded is not None:
        return Decision(Verdict.SUPERSEDED, "superseded", run=superseded, runs=runs)

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


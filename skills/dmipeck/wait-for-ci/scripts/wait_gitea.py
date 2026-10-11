#!/usr/bin/env python3
"""Wait for Gitea Actions CI via ``tea api``."""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence, Set
from typing import Any
from urllib.parse import quote

from decide import (
    Job,
    Run,
    Target,
    TargetError,
    allowed_job_names,
    argument_parser,
    choose_remote,
    exit_code,
    format_report,
    parse_remotes,
    parse_targets,
    watch,
)

KINDS = frozenset({"pr", "branch", "tag", "sha", "run"})
REJECT_HOSTS = frozenset({"github.com", "gitlab.com"})
_PENDING = frozenset(
    {
        "",
        "cancelling",
        "created",
        "in_progress",
        "pending",
        "preparing",
        "queued",
        "requested",
        "running",
        "scheduled",
        "unknown",
        "waiting",
        "waiting_for_resource",
    }
)

Runner = Callable[..., subprocess.CompletedProcess[str]]


def normalize_conclusion(value: str) -> str:
    """Map forge aliases onto decide conclusions."""
    value = value.lower()
    if value == "canceled":
        return "cancelled"
    if value == "failed":
        return "failure"
    return value


def run_aggregate(status: str | None, conclusion: str | None) -> str:
    """Normalize a Gitea Actions run to a decide aggregate status."""
    status = (status or "").lower()
    if status in _PENDING:
        return "pending"
    if status == "completed":
        return _aggregate_from_conclusion(conclusion)
    if conclusion:
        return _aggregate_from_conclusion(conclusion)
    return _aggregate_from_conclusion(status)


def map_job(raw: Mapping[str, Any], *, allowed: Set[str]) -> Job:
    """Map one Gitea Actions job payload onto ``Job``."""
    name = str(raw.get("name") or "")
    url = str(raw.get("html_url") or raw.get("url") or "")
    done, conclusion = _job_outcome(raw.get("status"), raw.get("conclusion"))
    return Job(name, url, done, conclusion, name in allowed)


def map_run(
    raw: Mapping[str, Any],
    jobs: tuple[Job, ...],
    *,
    tip_sha: str | None,
) -> Run:
    """Map a Gitea Actions run payload onto ``Run``."""
    aggregate = run_aggregate(raw.get("status"), raw.get("conclusion"))
    head_sha = str(raw.get("head_sha") or "")
    superseded = aggregate == "cancelled" and bool(tip_sha) and bool(head_sha) and tip_sha != head_sha
    return Run(
        str(raw.get("id")),
        str(raw.get("html_url") or raw.get("url") or ""),
        aggregate,
        superseded,
        jobs,
    )


def commit_sha_from_ref(
    payload: Any,
    *,
    fetch_tag_object: Callable[[str], Mapping[str, Any]],
) -> str:
    """Resolve a git ref API payload to a commit SHA, peeling annotated tags."""
    ref = payload[0] if isinstance(payload, list) else payload
    if not isinstance(ref, Mapping):
        raise TargetError("unexpected git ref payload")
    obj = ref.get("object")
    if not isinstance(obj, Mapping):
        raise TargetError("git ref missing object")
    sha = str(obj.get("sha") or "")
    typ = str(obj.get("type") or "")
    if not sha:
        raise TargetError("git ref missing sha")
    if typ == "commit":
        return sha
    if typ != "tag":
        raise TargetError(f"unsupported git ref object type {typ!r}")
    tag = fetch_tag_object(sha)
    tagged = tag.get("object")
    if not isinstance(tagged, Mapping) or not tagged.get("sha"):
        raise TargetError("annotated tag missing commit")
    return str(tagged["sha"])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argument_parser("wait_gitea.py")
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        targets = parse_targets(args.targets, KINDS)
        remotes = parse_remotes(_git_remote_v())
        remote = choose_remote(remotes, reject_hosts=REJECT_HOSTS)
        resolved = resolve_watch(targets, remote.slug, runner=subprocess.run)
    except TargetError as exc:
        print(f"wait_gitea.py: error: {exc}", file=sys.stderr)
        return 1
    decision = watch(
        lambda: fetch_runs(resolved, remote.slug, runner=subprocess.run),
        fail_on_allowed=args.fail_on_allowed,
        timeout_s=args.timeout,
        sleep=time.sleep,
        monotonic=time.monotonic,
    )
    sys.stdout.write(format_report(decision))
    return exit_code(decision.verdict)


def resolve_watch(
    targets: Sequence[Target],
    slug: str,
    *,
    runner: Runner,
) -> tuple[frozenset[str], frozenset[str]]:
    """Resolve targets once to explicit run ids and commit SHAs."""
    run_ids: set[str] = set()
    shas: set[str] = set()
    for target in targets:
        if target.kind == "run":
            run_ids.add(target.value)
            continue
        if target.kind == "sha":
            shas.add(target.value)
            continue
        if target.kind == "pr":
            pull = tea_api(f"repos/{slug}/pulls/{quote(target.value, safe='')}", runner=runner)
            sha = _dig(pull, "head", "sha")
            if not sha:
                raise TargetError(f"pull {target.value!r} missing head.sha")
            shas.add(sha)
            continue
        if target.kind == "branch":
            ref = tea_api(
                f"repos/{slug}/git/refs/heads/{quote(target.value, safe='')}",
                runner=runner,
            )
            shas.add(commit_sha_from_ref(ref, fetch_tag_object=_unused_tag_fetch))
            continue
        if target.kind == "tag":
            ref = tea_api(
                f"repos/{slug}/git/refs/tags/{quote(target.value, safe='')}",
                runner=runner,
            )

            def fetch_tag(tag_sha: str) -> Mapping[str, Any]:
                return tea_api(f"repos/{slug}/git/tags/{tag_sha}", runner=runner)

            shas.add(commit_sha_from_ref(ref, fetch_tag_object=fetch_tag))
            continue
        raise TargetError(f"unsupported target kind {target.kind!r}")
    return frozenset(run_ids), frozenset(shas)


def fetch_runs(
    resolved: tuple[frozenset[str], frozenset[str]],
    slug: str,
    *,
    runner: Runner,
) -> tuple[Run, ...]:
    """Load and normalize the watched runs for one poll."""
    run_ids, shas = resolved
    by_id: dict[str, Mapping[str, Any]] = {}
    for run_id in run_ids:
        by_id[run_id] = tea_api(f"repos/{slug}/actions/runs/{run_id}", runner=runner)
    for sha in shas:
        payload = tea_api(
            f"repos/{slug}/actions/runs?head_sha={quote(sha, safe='')}&page=1&limit=20",
            runner=runner,
        )
        for item in _workflow_runs(payload):
            by_id[str(item.get("id"))] = item
    tip_cache: dict[str, str | None] = {}
    yaml_cache: dict[tuple[str, str], frozenset[str]] = {}
    runs: list[Run] = []
    for run_id, raw in sorted(by_id.items(), key=lambda item: item[0]):
        if "jobs" not in raw or raw.get("path") is None:
            raw = tea_api(f"repos/{slug}/actions/runs/{run_id}", runner=runner)
        jobs_payload = tea_api(
            f"repos/{slug}/actions/runs/{run_id}/jobs?page=1&limit=100",
            runner=runner,
        )
        allowed = _allowed_for_run(raw, slug, runner=runner, cache=yaml_cache)
        jobs = tuple(map_job(job, allowed=allowed) for job in _jobs(jobs_payload))
        branch = str(raw.get("head_branch") or "")
        if branch not in tip_cache:
            tip_cache[branch] = _branch_tip(slug, branch, runner=runner) if branch else None
        runs.append(map_run(raw, jobs, tip_sha=tip_cache[branch]))
    return tuple(runs)


def tea_api(path: str, *, runner: Runner) -> Any:
    """GET a Gitea API path through ``tea api`` and parse JSON."""
    completed = runner(
        ["tea", "api", path],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip() or f"exit {completed.returncode}"
        raise TargetError(f"tea api {path}: {err}")
    text = completed.stdout.strip()
    if not text:
        raise TargetError(f"tea api {path}: empty response")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise TargetError(f"tea api {path}: invalid JSON") from exc


def _allowed_for_run(
    raw: Mapping[str, Any],
    slug: str,
    *,
    runner: Runner,
    cache: dict[tuple[str, str], frozenset[str]],
) -> frozenset[str]:
    path = str(raw.get("path") or "")
    head_sha = str(raw.get("head_sha") or "")
    if not path and raw.get("workflow_id") is not None:
        workflow = tea_api(f"repos/{slug}/actions/workflows/{raw['workflow_id']}", runner=runner)
        path = str(workflow.get("path") or "")
    if not path or not head_sha:
        return frozenset()
    key = (path, head_sha)
    if key not in cache:
        content = tea_api(
            f"repos/{slug}/contents/{quote(path, safe='/')}?ref={quote(head_sha, safe='')}",
            runner=runner,
        )
        cache[key] = allowed_job_names(_decode_content(content))
    return cache[key]


def _decode_content(payload: Mapping[str, Any]) -> str:
    encoded = payload.get("content")
    if not isinstance(encoded, str) or not encoded:
        raise TargetError("workflow contents missing content")
    raw = base64.b64decode(encoded)
    return raw.decode("utf-8")


def _branch_tip(slug: str, branch: str, *, runner: Runner) -> str | None:
    try:
        ref = tea_api(
            f"repos/{slug}/git/refs/heads/{quote(branch, safe='')}",
            runner=runner,
        )
        return commit_sha_from_ref(ref, fetch_tag_object=_unused_tag_fetch)
    except TargetError:
        return None


def _workflow_runs(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    if isinstance(payload, Mapping):
        items = payload.get("workflow_runs")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, Mapping)]
    return []


def _jobs(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    if isinstance(payload, Mapping):
        items = payload.get("jobs")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, Mapping)]
    return []


def _job_outcome(status: Any, conclusion: Any) -> tuple[bool, str | None]:
    status_s = str(status or "").lower()
    conclusion_s = None if conclusion in (None, "") else str(conclusion)
    if status_s in _PENDING:
        return False, None
    if status_s == "manual":
        return True, "skipped"
    if status_s == "completed":
        if not conclusion_s:
            return False, None
        return True, normalize_conclusion(conclusion_s)
    if status_s in {
        "success",
        "failure",
        "failed",
        "cancelled",
        "canceled",
        "skipped",
        "timed_out",
        "startup_failure",
        "neutral",
    }:
        return True, normalize_conclusion(conclusion_s or status_s)
    if conclusion_s:
        return True, normalize_conclusion(conclusion_s)
    return False, None


def _aggregate_from_conclusion(conclusion: str | None) -> str:
    if not conclusion:
        return "pending"
    value = normalize_conclusion(conclusion)
    if value == "success":
        return "success"
    if value == "cancelled":
        return "cancelled"
    if value == "skipped":
        return "skipped"
    if value in {"action_required", "blocked", "manual"}:
        return "blocked"
    return "failure"


def _dig(payload: Any, *keys: str) -> str:
    cur: Any = payload
    for key in keys:
        if not isinstance(cur, Mapping):
            return ""
        cur = cur.get(key)
    return str(cur or "")


def _unused_tag_fetch(_sha: str) -> Mapping[str, Any]:
    raise TargetError("unexpected annotated tag object")


def _git_remote_v() -> str:
    completed = subprocess.run(
        ["git", "remote", "-v"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip() or "git remote -v failed"
        raise TargetError(err)
    return completed.stdout


if __name__ == "__main__":
    raise SystemExit(main())

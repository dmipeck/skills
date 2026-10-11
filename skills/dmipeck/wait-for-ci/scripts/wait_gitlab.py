#!/usr/bin/env python3
"""Wait for GitLab CI via glab until a definitive job-level verdict."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.parse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from decide import (
    Job,
    Remote,
    Run,
    Target,
    TargetError,
    argument_parser,
    choose_remote,
    exit_code,
    format_report,
    parse_remotes,
    parse_targets,
    watch,
)

KINDS = frozenset({"mr", "branch", "tag", "sha", "pipeline"})
REJECT_HOSTS = frozenset({"github.com"})
TERMINAL_JOB = frozenset({"success", "failed", "canceled", "cancelled", "skipped"})
TIMEOUT_REASONS = frozenset({"timeout", "stuck_or_timeout_failure", "job_execution_timeout"})
PENDING_PIPELINE = frozenset(
    {
        "created",
        "waiting_for_resource",
        "preparing",
        "pending",
        "running",
        "scheduled",
        "canceling",
    }
)

Runner = Callable[[Sequence[str]], str]


@dataclass(frozen=True)
class Resolved:
    kind: str
    value: str
    sha: str | None
    pipeline_id: str | None
    ref: str | None


def map_job(raw: Mapping[str, Any]) -> Job:
    """Map a GitLab job object to the shared Job snapshot."""
    status = str(raw.get("status") or "")
    done = status in TERMINAL_JOB
    conclusion = _job_conclusion(status, raw.get("failure_reason")) if done else None
    return Job(
        name=str(raw.get("name") or raw.get("id") or "job"),
        url=str(raw.get("web_url") or ""),
        done=done,
        conclusion=conclusion,
        allowed_failure=bool(raw.get("allow_failure")),
    )


def map_pipeline_status(status: str) -> str:
    """Normalize a GitLab pipeline status for decide."""
    if status in PENDING_PIPELINE:
        return "pending"
    if status == "failed":
        return "failure"
    if status in {"canceled", "cancelled"}:
        return "cancelled"
    if status == "manual":
        return "blocked"
    if status in {"success", "skipped"}:
        return status
    return status


def map_pipeline(
    pipeline: Mapping[str, Any],
    jobs: Sequence[Mapping[str, Any]],
    *,
    superseded: bool = False,
) -> Run:
    """Map a GitLab pipeline plus jobs to the shared Run snapshot."""
    return Run(
        id=str(pipeline["id"]),
        url=str(pipeline.get("web_url") or ""),
        status=map_pipeline_status(str(pipeline.get("status") or "")),
        superseded=superseded,
        jobs=tuple(map_job(job) for job in jobs),
    )


def pipeline_superseded(
    pipeline: Mapping[str, Any],
    *,
    latest_id_for_ref: int | None,
    watched_sha: str,
    current_sha: str | None,
) -> bool:
    """True when a canceled pipeline was replaced by a newer tip or pipeline."""
    status = str(pipeline.get("status") or "")
    if status not in {"canceled", "cancelled"}:
        return False
    if current_sha is not None and current_sha != watched_sha:
        return True
    if latest_id_for_ref is None:
        return False
    return int(pipeline["id"]) < latest_id_for_ref


def resolve_targets(
    targets: Sequence[Target],
    *,
    remote: Remote,
    runner: Runner,
) -> tuple[Resolved, ...]:
    """Resolve each target once to a SHA and/or explicit pipeline id."""
    resolved: list[Resolved] = []
    for target in targets:
        if target.kind == "pipeline":
            resolved.append(
                Resolved("pipeline", target.value, sha=None, pipeline_id=target.value, ref=None)
            )
            continue
        if target.kind == "sha":
            resolved.append(
                Resolved("sha", target.value, sha=target.value, pipeline_id=None, ref=None)
            )
            continue
        if target.kind == "mr":
            payload = _glab_json(
                (
                    "mr",
                    "view",
                    target.value,
                    "-R",
                    remote.slug,
                    "-F",
                    "json",
                ),
                runner=runner,
            )
            if not isinstance(payload, dict):
                raise TargetError(f"mr:{target.value} returned no JSON object")
            sha = str(payload.get("sha") or (payload.get("diff_refs") or {}).get("head_sha") or "")
            if not sha:
                raise TargetError(f"mr:{target.value} has no head sha")
            ref = str(payload.get("source_branch") or "") or None
            resolved.append(Resolved("mr", target.value, sha=sha, pipeline_id=None, ref=ref))
            continue
        if target.kind == "branch":
            path = urllib.parse.quote(target.value, safe="")
            payload = _glab_json(
                _api_args(remote, f"repository/commits/{path}"),
                runner=runner,
            )
            if not isinstance(payload, dict):
                raise TargetError(f"branch:{target.value} returned no JSON object")
            sha = str(payload.get("id") or "")
            if not sha:
                raise TargetError(f"branch:{target.value} has no commit id")
            resolved.append(
                Resolved("branch", target.value, sha=sha, pipeline_id=None, ref=target.value)
            )
            continue
        if target.kind == "tag":
            path = urllib.parse.quote(target.value, safe="")
            payload = _glab_json(
                _api_args(remote, f"repository/tags/{path}"),
                runner=runner,
            )
            if not isinstance(payload, dict):
                raise TargetError(f"tag:{target.value} returned no JSON object")
            sha = str((payload.get("commit") or {}).get("id") or "")
            if not sha:
                raise TargetError(f"tag:{target.value} has no commit id")
            resolved.append(
                Resolved("tag", target.value, sha=sha, pipeline_id=None, ref=target.value)
            )
            continue
        raise TargetError(f"unknown target kind {target.kind!r}")
    return tuple(resolved)


def fetch_runs(
    resolved: Sequence[Resolved],
    *,
    remote: Remote,
    runner: Runner,
) -> tuple[Run, ...]:
    """Fetch and map the current pipeline/job snapshots for resolved targets."""
    pipeline_ids: list[str] = []
    seen: set[str] = set()
    sha_by_pipeline: dict[str, str] = {}
    ref_by_pipeline: dict[str, str | None] = {}

    for item in resolved:
        if item.pipeline_id is not None:
            pid = item.pipeline_id
            if pid not in seen:
                seen.add(pid)
                pipeline_ids.append(pid)
                sha_by_pipeline[pid] = item.sha or ""
                ref_by_pipeline[pid] = item.ref
            continue
        assert item.sha is not None
        for pipeline in _list_pipelines(remote, sha=item.sha, runner=runner):
            pid = str(pipeline["id"])
            if pid in seen:
                continue
            seen.add(pid)
            pipeline_ids.append(pid)
            sha_by_pipeline[pid] = item.sha
            ref_by_pipeline[pid] = item.ref or str(pipeline.get("ref") or "") or None

    runs: list[Run] = []
    for pid in pipeline_ids:
        pipeline, jobs = _pipeline_with_jobs(remote, pid, runner=runner)
        watched_sha = sha_by_pipeline.get(pid) or str(pipeline.get("sha") or "")
        ref = ref_by_pipeline.get(pid) or str(pipeline.get("ref") or "") or None
        latest_id = _latest_pipeline_id(remote, ref=ref, runner=runner) if ref else None
        current_sha = _current_sha_for_ref(resolved, ref=ref, remote=remote, runner=runner)
        superseded = pipeline_superseded(
            pipeline,
            latest_id_for_ref=latest_id,
            watched_sha=watched_sha,
            current_sha=current_sha,
        )
        runs.append(map_pipeline(pipeline, jobs, superseded=superseded))
    return tuple(runs)


def main(argv: Sequence[str] | None = None, *, runner: Runner | None = None) -> int:
    parser = argument_parser("wait_gitlab.py")
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        targets = parse_targets(args.targets, KINDS)
        remotes = parse_remotes(_git_remotes())
        remote = choose_remote(remotes, reject_hosts=REJECT_HOSTS)
    except TargetError as exc:
        print(f"wait_gitlab.py: error: {exc}", file=sys.stderr)
        return 1

    active_runner = runner or _subprocess_runner
    try:
        resolved = resolve_targets(targets, remote=remote, runner=active_runner)
    except (TargetError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"wait_gitlab.py: error: {exc}", file=sys.stderr)
        return 1

    def fetch() -> tuple[Run, ...]:
        return fetch_runs(resolved, remote=remote, runner=active_runner)

    try:
        decision = watch(
            fetch,
            fail_on_allowed=args.fail_on_allowed,
            timeout_s=args.timeout,
            sleep=time.sleep,
            monotonic=time.monotonic,
        )
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError, TargetError) as exc:
        print(f"wait_gitlab.py: error: {exc}", file=sys.stderr)
        return 1

    sys.stdout.write(format_report(decision))
    return exit_code(decision.verdict)


def _job_conclusion(status: str, failure_reason: Any) -> str | None:
    if status == "success":
        return "success"
    if status in {"canceled", "cancelled"}:
        return "cancelled"
    if status == "skipped":
        return "skipped"
    if status != "failed":
        return status
    reason = str(failure_reason or "")
    if reason in TIMEOUT_REASONS:
        return "timed_out"
    if reason == "runner_system_failure":
        return "startup_failure"
    return "failure"


def _list_pipelines(remote: Remote, *, sha: str, runner: Runner) -> list[dict[str, Any]]:
    payload = _glab_json(
        ("ci", "list", "-R", remote.slug, "--sha", sha, "-F", "json"),
        runner=runner,
    )
    if payload is None:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    raise TargetError("unexpected glab ci list payload")


def _pipeline_with_jobs(
    remote: Remote,
    pipeline_id: str,
    *,
    runner: Runner,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = _glab_json(
        (
            "ci",
            "get",
            "-R",
            remote.slug,
            "-p",
            pipeline_id,
            "-F",
            "json",
            "-d",
        ),
        runner=runner,
    )
    if not isinstance(payload, dict):
        raise TargetError(f"unexpected glab ci get payload for pipeline {pipeline_id}")
    jobs = payload.get("jobs")
    if jobs is None:
        jobs = _jobs_api(remote, pipeline_id, runner=runner)
    elif not isinstance(jobs, list):
        raise TargetError(f"unexpected jobs payload for pipeline {pipeline_id}")
    else:
        jobs = [job for job in jobs if isinstance(job, dict)]
    return payload, jobs


def _jobs_api(remote: Remote, pipeline_id: str, *, runner: Runner) -> list[dict[str, Any]]:
    payload = _glab_json(
        _api_args(remote, f"pipelines/{pipeline_id}/jobs?per_page=100"),
        runner=runner,
    )
    if payload is None:
        return []
    if isinstance(payload, list):
        return [job for job in payload if isinstance(job, dict)]
    raise TargetError(f"unexpected jobs api payload for pipeline {pipeline_id}")


def _latest_pipeline_id(remote: Remote, *, ref: str | None, runner: Runner) -> int | None:
    if not ref:
        return None
    payload = _glab_json(
        ("ci", "list", "-R", remote.slug, "--ref", ref, "-F", "json", "-P", "1"),
        runner=runner,
    )
    if not isinstance(payload, list) or not payload:
        return None
    first = payload[0]
    if not isinstance(first, dict) or "id" not in first:
        return None
    return int(first["id"])


def _current_sha_for_ref(
    resolved: Sequence[Resolved],
    *,
    ref: str | None,
    remote: Remote,
    runner: Runner,
) -> str | None:
    if not ref:
        return None
    for item in resolved:
        if item.kind == "mr" and item.ref == ref:
            payload = _glab_json(
                ("mr", "view", item.value, "-R", remote.slug, "-F", "json"),
                runner=runner,
            )
            return str(
                payload.get("sha") or (payload.get("diff_refs") or {}).get("head_sha") or ""
            ) or None
        if item.kind == "branch" and item.value == ref:
            path = urllib.parse.quote(ref, safe="")
            payload = _glab_json(
                _api_args(remote, f"repository/commits/{path}"),
                runner=runner,
            )
            return str(payload.get("id") or "") or None
    return None


def _api_args(remote: Remote, suffix: str) -> tuple[str, ...]:
    project = urllib.parse.quote(remote.slug, safe="")
    return ("api", f"projects/{project}/{suffix}", "--hostname", remote.host)


def _glab_json(args: Sequence[str], *, runner: Runner) -> Any:
    text = runner(("glab", *args))
    if not text.strip():
        return None
    return json.loads(text)


def _subprocess_runner(args: Sequence[str]) -> str:
    completed = subprocess.run(
        list(args),
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def _git_remotes() -> str:
    completed = subprocess.run(
        ["git", "remote", "-v"],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


if __name__ == "__main__":
    raise SystemExit(main())

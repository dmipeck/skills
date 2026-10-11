#!/usr/bin/env python3
"""Wait for GitHub Actions jobs via ``gh``; fail-fast through decide."""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
import urllib.parse
from collections.abc import Callable, Mapping, Sequence, Set
from dataclasses import dataclass
from typing import Any

from decide import (
    Job,
    Remote,
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
HARD_AGGREGATE = frozenset({"failure", "timed_out", "startup_failure"})


@dataclass(frozen=True)
class ShaWatch:
    sha: str
    branch: str | None = None
    pr: str | None = None


@dataclass(frozen=True)
class Plan:
    repo: str
    shas: tuple[ShaWatch, ...]
    run_ids: tuple[str, ...]


def github_run_status(status: str, conclusion: str | None) -> str:
    if status != "completed":
        return "pending"
    if conclusion == "success":
        return "success"
    if conclusion in HARD_AGGREGATE:
        return "failure"
    if conclusion in {"cancelled", "skipped"}:
        return conclusion
    return conclusion or "failure"


def github_job(raw: Mapping[str, Any], allowed: Set[str]) -> Job:
    name = str(raw["name"])
    url = str(raw.get("url") or raw.get("html_url") or "")
    done = raw.get("status") == "completed"
    conclusion = raw.get("conclusion")
    if conclusion is not None:
        conclusion = str(conclusion)
    return Job(name, url, done, conclusion, name in allowed)


def github_run(
    raw: Mapping[str, Any],
    jobs: Sequence[Job],
    *,
    superseded: bool,
) -> Run:
    run_id = str(raw.get("databaseId") or raw["id"])
    url = str(raw.get("url") or raw.get("html_url") or "")
    status = github_run_status(str(raw.get("status") or ""), raw.get("conclusion"))
    return Run(run_id, url, status, superseded, tuple(jobs))


def select_runs(rows: Sequence[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
    return tuple(rows)


def superseded_cancelled(cancelled: bool, *, sha_moved: bool, newer_run: bool) -> bool:
    return cancelled and (sha_moved or newer_run)


def sha_from_pr(payload: Mapping[str, Any]) -> tuple[str, str]:
    return str(payload["headRefOid"]), str(payload["headRefName"])


def sha_from_commit(payload: Mapping[str, Any]) -> str:
    return str(payload["sha"])


def sha_from_tag_ref(
    ref_payload: Mapping[str, Any],
    tag_object: Mapping[str, Any] | None,
) -> str:
    obj = ref_payload["object"]
    if obj["type"] == "commit":
        return str(obj["sha"])
    if obj["type"] == "tag" and tag_object is not None:
        return str(tag_object["object"]["sha"])
    raise TargetError("annotated tag could not be peeled to a commit")


def _run_gh(args: Sequence[str], *, runner: Callable[[Sequence[str]], str] | None = None) -> str:
    if runner is not None:
        return runner(args)
    proc = subprocess.run(
        ["gh", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "gh failed").strip()
        raise TargetError(err)
    return proc.stdout


def _gh_json(
    args: Sequence[str],
    *,
    runner: Callable[[Sequence[str]], str] | None = None,
) -> Any:
    return json.loads(_run_gh(args, runner=runner) or "null")


def _repo_from_git(
    *,
    remote_text: str | None = None,
    git_runner: Callable[[Sequence[str]], str] | None = None,
) -> Remote:
    if remote_text is None:
        if git_runner is not None:
            remote_text = git_runner(["remote", "-v"])
        else:
            proc = subprocess.run(
                ["git", "remote", "-v"],
                check=False,
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                raise TargetError((proc.stderr or "git remote -v failed").strip())
            remote_text = proc.stdout
    return choose_remote(parse_remotes(remote_text), accept_hosts=frozenset({"github.com"}))


def resolve_plan(
    targets: Sequence[Target],
    repo: str,
    *,
    runner: Callable[[Sequence[str]], str] | None = None,
) -> Plan:
    shas: list[ShaWatch] = []
    run_ids: list[str] = []
    seen_sha: set[str] = set()
    seen_run: set[str] = set()
    for target in targets:
        if target.kind == "run":
            if target.value not in seen_run:
                seen_run.add(target.value)
                run_ids.append(target.value)
            continue
        if target.kind == "sha":
            watch = ShaWatch(target.value)
        elif target.kind == "pr":
            payload = _gh_json(
                ["pr", "view", target.value, "-R", repo, "--json", "headRefOid,headRefName"],
                runner=runner,
            )
            sha, branch = sha_from_pr(payload)
            watch = ShaWatch(sha, branch=branch, pr=target.value)
        elif target.kind == "branch":
            enc = urllib.parse.quote(target.value, safe="")
            payload = _gh_json(
                ["api", f"repos/{repo}/commits/{enc}", "--jq", "{sha:.sha}"],
                runner=runner,
            )
            watch = ShaWatch(sha_from_commit(payload), branch=target.value)
        elif target.kind == "tag":
            enc = urllib.parse.quote(target.value, safe="")
            ref = _gh_json(
                ["api", f"repos/{repo}/git/ref/tags/{enc}"],
                runner=runner,
            )
            tag_obj = None
            if ref["object"]["type"] == "tag":
                tag_obj = _gh_json(
                    ["api", f"repos/{repo}/git/tags/{ref['object']['sha']}"],
                    runner=runner,
                )
            watch = ShaWatch(sha_from_tag_ref(ref, tag_obj))
        else:
            raise TargetError(f"unknown target kind {target.kind!r}")
        if watch.sha not in seen_sha:
            seen_sha.add(watch.sha)
            shas.append(watch)
    return Plan(repo, tuple(shas), tuple(run_ids))


def _workflow_yaml(
    repo: str,
    run_id: str,
    *,
    runner: Callable[[Sequence[str]], str] | None,
    cache: dict[tuple[str, str], str],
) -> str:
    meta = _gh_json(
        ["api", f"repos/{repo}/actions/runs/{run_id}", "--jq", "{path,head_sha}"],
        runner=runner,
    )
    path = str(meta["path"])
    head_sha = str(meta["head_sha"])
    key = (path, head_sha)
    if key in cache:
        return cache[key]
    encoded = urllib.parse.quote(path, safe="/")
    ref = urllib.parse.quote(head_sha, safe="")
    payload = _gh_json(
        [
            "api",
            f"repos/{repo}/contents/{encoded}?ref={ref}",
            "--jq",
            "{content:.content}",
        ],
        runner=runner,
    )
    text = base64.b64decode(str(payload["content"]).replace("\n", "")).decode()
    cache[key] = text
    return text


def _list_runs_for_sha(
    repo: str,
    sha: str,
    *,
    runner: Callable[[Sequence[str]], str] | None,
) -> list[dict[str, Any]]:
    rows = _gh_json(
        [
            "run",
            "list",
            "-R",
            repo,
            "-c",
            sha,
            "--limit",
            "30",
            "--json",
            "databaseId,status,conclusion,workflowName,headBranch,event,createdAt,url,headSha",
        ],
        runner=runner,
    )
    return list(rows or [])


def _view_run(
    repo: str,
    run_id: str,
    *,
    runner: Callable[[Sequence[str]], str] | None,
) -> dict[str, Any]:
    return _gh_json(
        [
            "run",
            "view",
            str(run_id),
            "-R",
            repo,
            "--json",
            "databaseId,status,conclusion,headSha,url,workflowName,jobs,headBranch",
        ],
        runner=runner,
    )


def _branch_has_newer_run(
    repo: str,
    branch: str,
    run_id: str,
    created_at: str,
    *,
    runner: Callable[[Sequence[str]], str] | None,
) -> bool:
    rows = _gh_json(
        [
            "run",
            "list",
            "-R",
            repo,
            "-b",
            branch,
            "--limit",
            "5",
            "--json",
            "databaseId,createdAt",
        ],
        runner=runner,
    )
    for row in rows or []:
        other_id = str(row["databaseId"])
        if other_id == run_id:
            continue
        if str(row.get("createdAt") or "") > created_at:
            return True
        try:
            if int(other_id) > int(run_id):
                return True
        except ValueError:
            continue
    return False


def _pr_sha_moved(
    repo: str,
    pr: str,
    watched_sha: str,
    *,
    runner: Callable[[Sequence[str]], str] | None,
) -> bool:
    payload = _gh_json(
        ["pr", "view", pr, "-R", repo, "--json", "headRefOid"],
        runner=runner,
    )
    return str(payload["headRefOid"]) != watched_sha


def fetch_runs(
    plan: Plan,
    *,
    runner: Callable[[Sequence[str]], str] | None = None,
) -> tuple[Run, ...]:
    yaml_cache: dict[tuple[str, str], str] = {}
    by_id: dict[str, Run] = {}

    def add_from_view(view: Mapping[str, Any], *, sha_moved: bool, newer_run: bool) -> None:
        run_id = str(view.get("databaseId") or view["id"])
        yaml_text = _workflow_yaml(plan.repo, run_id, runner=runner, cache=yaml_cache)
        allowed = allowed_job_names(yaml_text)
        jobs = tuple(github_job(job, allowed) for job in view.get("jobs") or ())
        cancelled = github_run_status(str(view.get("status") or ""), view.get("conclusion")) == "cancelled"
        superseded = superseded_cancelled(cancelled, sha_moved=sha_moved, newer_run=newer_run)
        by_id[run_id] = github_run(view, jobs, superseded=superseded)

    for run_id in plan.run_ids:
        view = _view_run(plan.repo, run_id, runner=runner)
        newer = False
        branch = view.get("headBranch")
        if branch and str(view.get("status") or "") == "completed" and view.get("conclusion") == "cancelled":
            newer = _branch_has_newer_run(
                plan.repo,
                str(branch),
                run_id,
                "",
                runner=runner,
            )
        add_from_view(view, sha_moved=False, newer_run=newer)

    for watch_sha in plan.shas:
        sha_moved = False
        if watch_sha.pr is not None:
            sha_moved = _pr_sha_moved(
                plan.repo,
                watch_sha.pr,
                watch_sha.sha,
                runner=runner,
            )
        rows = _list_runs_for_sha(plan.repo, watch_sha.sha, runner=runner)
        for row in select_runs(rows):
            run_id = str(row["databaseId"])
            view = _view_run(plan.repo, run_id, runner=runner)
            newer = False
            branch = watch_sha.branch or view.get("headBranch")
            if branch and str(view.get("status") or "") == "completed" and view.get("conclusion") == "cancelled":
                newer = _branch_has_newer_run(
                    plan.repo,
                    str(branch),
                    run_id,
                    str(row.get("createdAt") or ""),
                    runner=runner,
                )
            add_from_view(view, sha_moved=sha_moved, newer_run=newer)

    return tuple(by_id.values())


def main(
    argv: Sequence[str] | None = None,
    *,
    runner: Callable[[Sequence[str]], str] | None = None,
) -> int:
    parser = argument_parser("wait_github.py")
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        targets = parse_targets(args.targets, KINDS)
        remote = _repo_from_git()
        plan = resolve_plan(targets, remote.slug, runner=runner)
        decision = watch(
            lambda: fetch_runs(plan, runner=runner),
            fail_on_allowed=args.fail_on_allowed,
            timeout_s=args.timeout,
            sleep=time.sleep,
            monotonic=time.monotonic,
        )
    except TargetError as exc:
        print(f"wait_github.py: error: {exc}", file=sys.stderr)
        return 1
    sys.stdout.write(format_report(decision))
    return exit_code(decision.verdict)


if __name__ == "__main__":
    raise SystemExit(main())

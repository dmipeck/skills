#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import subprocess
import unittest
from typing import Any

from decide import Job, Run, Target, Verdict, decide
from wait_gitea import (
    branch_has_newer_run,
    commit_sha_from_ref,
    fetch_runs,
    map_job,
    map_run,
    normalize_conclusion,
    resolve_watch,
    run_aggregate,
    superseded_cancelled,
)


class JobMappingTests(unittest.TestCase):
    def test_completed_hard_failure(self) -> None:
        job = map_job(
            {
                "name": "lint",
                "status": "completed",
                "conclusion": "failure",
                "html_url": "https://gitea.test/j/1",
            },
            allowed=frozenset(),
        )
        self.assertEqual(
            job,
            Job("lint", "https://gitea.test/j/1", True, "failure", False),
        )

    def test_pending_statuses_are_not_done(self) -> None:
        for status in ("pending", "queued", "in_progress", "waiting"):
            with self.subTest(status=status):
                job = map_job(
                    {"name": "test", "status": status, "conclusion": None, "html_url": ""},
                    allowed=frozenset(),
                )
                self.assertFalse(job.done)
                self.assertIsNone(job.conclusion)

    def test_allowed_by_workflow_name_or_id(self) -> None:
        soft = map_job(
            {
                "name": "Soft Check",
                "status": "completed",
                "conclusion": "failure",
                "html_url": "https://gitea.test/j/2",
            },
            allowed=frozenset({"soft", "Soft Check"}),
        )
        self.assertTrue(soft.allowed_failure)
        by_id = map_job(
            {
                "name": "soft",
                "status": "completed",
                "conclusion": "timed_out",
                "html_url": "https://gitea.test/j/3",
            },
            allowed=frozenset({"soft"}),
        )
        self.assertTrue(by_id.allowed_failure)
        self.assertEqual(by_id.conclusion, "timed_out")

    def test_status_as_conclusion_alias(self) -> None:
        job = map_job(
            {"name": "build", "status": "failure", "html_url": "https://gitea.test/j/4"},
            allowed=frozenset(),
        )
        self.assertTrue(job.done)
        self.assertEqual(job.conclusion, "failure")


class RunMappingTests(unittest.TestCase):
    def test_success_aggregate(self) -> None:
        jobs = (Job("test", "https://gitea.test/j", True, "success", False),)
        run = map_run(
            {
                "id": 9,
                "status": "completed",
                "conclusion": "success",
                "html_url": "https://gitea.test/r/9",
                "head_sha": "abc",
            },
            jobs,
            tip_sha="abc",
        )
        self.assertEqual(run, Run("9", "https://gitea.test/r/9", "success", False, jobs))

    def test_cancelled_with_moved_tip_is_superseded(self) -> None:
        jobs = (Job("test", "https://gitea.test/j", True, "cancelled", False),)
        run = map_run(
            {
                "id": 3,
                "status": "completed",
                "conclusion": "cancelled",
                "html_url": "https://gitea.test/r/3",
                "head_sha": "old",
            },
            jobs,
            tip_sha="new",
        )
        self.assertEqual(run.status, "cancelled")
        self.assertTrue(run.superseded)

    def test_cancelled_same_tip_is_not_superseded(self) -> None:
        run = map_run(
            {
                "id": 3,
                "status": "canceled",
                "html_url": "https://gitea.test/r/3",
                "head_sha": "abc",
            },
            (),
            tip_sha="abc",
        )
        self.assertEqual(run.status, "cancelled")
        self.assertFalse(run.superseded)

    def test_cancelled_with_newer_run_is_superseded(self) -> None:
        run = map_run(
            {
                "id": 3,
                "status": "completed",
                "conclusion": "cancelled",
                "html_url": "https://gitea.test/r/3",
                "head_sha": "abc",
            },
            (),
            tip_sha="abc",
            newer_run=True,
        )
        self.assertTrue(run.superseded)

    def test_superseded_cancelled_helpers(self) -> None:
        self.assertTrue(superseded_cancelled(True, tip_moved=True, newer_run=False))
        self.assertTrue(superseded_cancelled(True, tip_moved=False, newer_run=True))
        self.assertFalse(superseded_cancelled(True, tip_moved=False, newer_run=False))
        self.assertFalse(superseded_cancelled(False, tip_moved=True, newer_run=True))

    def test_branch_has_newer_run_by_id_or_created(self) -> None:
        rows = (
            {"id": 3, "created_at": "2026-01-01T00:00:00Z"},
            {"id": 9, "created_at": "2026-01-01T01:00:00Z"},
        )
        self.assertTrue(branch_has_newer_run(rows, "3", "2026-01-01T00:00:00Z"))
        self.assertFalse(branch_has_newer_run(rows, "9", "2026-01-01T01:00:00Z"))

    def test_pending_run(self) -> None:
        self.assertEqual(run_aggregate("in_progress", None), "pending")
        self.assertEqual(run_aggregate("queued", None), "pending")


class RefAndConclusionTests(unittest.TestCase):
    def test_normalize_conclusion_aliases(self) -> None:
        self.assertEqual(normalize_conclusion("canceled"), "cancelled")
        self.assertEqual(normalize_conclusion("failed"), "failure")
        self.assertEqual(normalize_conclusion("startup_failure"), "startup_failure")

    def test_commit_sha_from_direct_ref(self) -> None:
        sha = commit_sha_from_ref(
            {"ref": "refs/heads/main", "object": {"type": "commit", "sha": "deadbeef"}},
            fetch_tag_object=lambda _sha: self.fail("should not peel"),
        )
        self.assertEqual(sha, "deadbeef")

    def test_commit_sha_peels_annotated_tag(self) -> None:
        calls: list[str] = []

        def fetch_tag(tag_sha: str) -> dict:
            calls.append(tag_sha)
            return {"object": {"type": "commit", "sha": "cafebabe"}}

        sha = commit_sha_from_ref(
            {"ref": "refs/tags/v1", "object": {"type": "tag", "sha": "tagobj"}},
            fetch_tag_object=fetch_tag,
        )
        self.assertEqual(sha, "cafebabe")
        self.assertEqual(calls, ["tagobj"])

    def test_commit_sha_from_ref_list(self) -> None:
        sha = commit_sha_from_ref(
            [{"object": {"type": "commit", "sha": "abc123"}}],
            fetch_tag_object=lambda _sha: {},
        )
        self.assertEqual(sha, "abc123")


class ResolveAndFetchTests(unittest.TestCase):
    def test_resolve_pr_and_run(self) -> None:
        responses = {
            "repos/o/r/pulls/4": {"head": {"sha": "prsha"}},
        }

        def runner(cmd: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
            path = cmd[2]
            return subprocess.CompletedProcess(cmd, 0, json.dumps(responses[path]), "")

        run_ids, shas = resolve_watch(
            (Target("pr", "4"), Target("run", "99"), Target("sha", "direct")),
            "o/r",
            runner=runner,
        )
        self.assertEqual(run_ids, frozenset({"99"}))
        self.assertEqual(shas, frozenset({"prsha", "direct"}))

    def test_fetch_maps_allowed_failure_and_hard_fail(self) -> None:
        yaml = """
jobs:
  soft:
    name: Soft Check
    continue-on-error: true
    runs-on: ubuntu-latest
  lint:
    runs-on: ubuntu-latest
"""
        encoded = base64.b64encode(yaml.encode()).decode()
        responses = {
            "repos/o/r/actions/runs?head_sha=abc&page=1&limit=20": {
                "workflow_runs": [
                    {
                        "id": 7,
                        "status": "completed",
                        "conclusion": "failure",
                        "html_url": "https://gitea.test/r/7",
                        "head_sha": "abc",
                        "head_branch": "main",
                        "path": ".gitea/workflows/ci.yml",
                    }
                ]
            },
            "repos/o/r/actions/runs/7": {
                "id": 7,
                "status": "completed",
                "conclusion": "failure",
                "html_url": "https://gitea.test/r/7",
                "head_sha": "abc",
                "head_branch": "main",
                "path": ".gitea/workflows/ci.yml",
            },
            "repos/o/r/actions/runs/7/jobs?page=1&limit=100": {
                "jobs": [
                    {
                        "name": "Soft Check",
                        "status": "completed",
                        "conclusion": "failure",
                        "html_url": "https://gitea.test/j/soft",
                    },
                    {
                        "name": "lint",
                        "status": "completed",
                        "conclusion": "failure",
                        "html_url": "https://gitea.test/j/lint",
                    },
                ]
            },
            "repos/o/r/contents/.gitea/workflows/ci.yml?ref=abc": {"content": encoded},
            "repos/o/r/git/refs/heads/main": {
                "object": {"type": "commit", "sha": "abc"},
            },
        }

        def runner(cmd: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
            path = cmd[2]
            return subprocess.CompletedProcess(cmd, 0, json.dumps(responses[path]), "")

        runs = fetch_runs((frozenset(), frozenset({"abc"})), "o/r", runner=runner)
        self.assertEqual(len(runs), 1)
        soft, lint = runs[0].jobs
        self.assertTrue(soft.allowed_failure)
        self.assertFalse(lint.allowed_failure)
        decision = decide(runs, fail_on_allowed=False)
        self.assertEqual(decision.verdict, Verdict.FAILED)
        self.assertEqual(decision.job.name, "lint")

    def test_fetch_cancelled_with_newer_branch_run_is_superseded(self) -> None:
        responses = {
            "repos/o/r/actions/runs?head_sha=old&page=1&limit=20": {
                "workflow_runs": [
                    {
                        "id": 3,
                        "status": "completed",
                        "conclusion": "cancelled",
                        "html_url": "https://gitea.test/r/3",
                        "head_sha": "old",
                        "head_branch": "feat",
                        "created_at": "2026-01-01T00:00:00Z",
                        "path": ".gitea/workflows/ci.yml",
                    }
                ]
            },
            "repos/o/r/actions/runs/3": {
                "id": 3,
                "status": "completed",
                "conclusion": "cancelled",
                "html_url": "https://gitea.test/r/3",
                "head_sha": "old",
                "head_branch": "feat",
                "created_at": "2026-01-01T00:00:00Z",
                "path": ".gitea/workflows/ci.yml",
            },
            "repos/o/r/actions/runs/3/jobs?page=1&limit=100": {
                "jobs": [
                    {
                        "name": "test",
                        "status": "completed",
                        "conclusion": "cancelled",
                        "html_url": "https://gitea.test/j/1",
                    }
                ]
            },
            "repos/o/r/contents/.gitea/workflows/ci.yml?ref=old": {
                "content": base64.b64encode(b"jobs:\n  test:\n    runs-on: ubuntu-latest\n").decode()
            },
            "repos/o/r/git/refs/heads/feat": {
                "object": {"type": "commit", "sha": "old"},
            },
            "repos/o/r/actions/runs?branch=feat&page=1&limit=5": {
                "workflow_runs": [
                    {"id": 3, "created_at": "2026-01-01T00:00:00Z"},
                    {"id": 8, "created_at": "2026-01-01T01:00:00Z"},
                ]
            },
        }

        def runner(cmd: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
            path = cmd[2]
            return subprocess.CompletedProcess(cmd, 0, json.dumps(responses[path]), "")

        runs = fetch_runs((frozenset(), frozenset({"old"})), "o/r", runner=runner)
        self.assertEqual(len(runs), 1)
        self.assertTrue(runs[0].superseded)
        self.assertEqual(decide(runs, fail_on_allowed=False).verdict, Verdict.SUPERSEDED)


if __name__ == "__main__":
    unittest.main()

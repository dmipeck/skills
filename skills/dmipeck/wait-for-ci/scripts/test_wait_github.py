#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import unittest
from collections.abc import Sequence

from decide import Job, Run, Target
from wait_github import (
    KINDS,
    Plan,
    ShaWatch,
    fetch_runs,
    github_job,
    github_run,
    github_run_status,
    resolve_plan,
    select_runs,
    sha_from_commit,
    sha_from_pr,
    sha_from_tag_ref,
    superseded_cancelled,
)


class GithubRunStatusTests(unittest.TestCase):
    def test_incomplete_is_pending(self) -> None:
        for status in ("queued", "in_progress", "waiting", "requested", "pending"):
            with self.subTest(status=status):
                self.assertEqual(github_run_status(status, None), "pending")
                self.assertEqual(github_run_status(status, "success"), "pending")

    def test_completed_maps_conclusion(self) -> None:
        self.assertEqual(github_run_status("completed", "success"), "success")
        self.assertEqual(github_run_status("completed", "failure"), "failure")
        self.assertEqual(github_run_status("completed", "timed_out"), "failure")
        self.assertEqual(github_run_status("completed", "startup_failure"), "failure")
        self.assertEqual(github_run_status("completed", "cancelled"), "cancelled")
        self.assertEqual(github_run_status("completed", "skipped"), "skipped")
        self.assertEqual(github_run_status("completed", "neutral"), "neutral")


class GithubJobTests(unittest.TestCase):
    def test_maps_cli_job_shape(self) -> None:
        raw = {
            "name": "lint",
            "status": "completed",
            "conclusion": "failure",
            "url": "https://github.com/o/r/actions/runs/1/job/2",
            "databaseId": 2,
        }
        job = github_job(raw, frozenset())
        self.assertEqual(
            job,
            Job("lint", "https://github.com/o/r/actions/runs/1/job/2", True, "failure", False),
        )

    def test_incomplete_job_not_done(self) -> None:
        job = github_job(
            {"name": "test", "status": "in_progress", "conclusion": None, "html_url": "https://j"},
            frozenset(),
        )
        self.assertEqual(job, Job("test", "https://j", False, None, False))

    def test_allowed_by_display_name(self) -> None:
        job = github_job(
            {"name": "Soft Check", "status": "completed", "conclusion": "failure", "url": "u"},
            frozenset({"soft", "Soft Check"}),
        )
        self.assertTrue(job.allowed_failure)


class SelectRunsTests(unittest.TestCase):
    def test_keeps_every_run_for_sha(self) -> None:
        rows = [
            {
                "databaseId": 1,
                "workflowName": "CI",
                "status": "completed",
                "createdAt": "2026-01-01T00:00:00Z",
            },
            {
                "databaseId": 2,
                "workflowName": "CI",
                "status": "in_progress",
                "createdAt": "2026-01-01T01:00:00Z",
            },
            {
                "databaseId": 3,
                "workflowName": "Lint",
                "status": "completed",
                "createdAt": "2026-01-01T02:00:00Z",
            },
        ]
        selected = select_runs(rows)
        self.assertEqual([row["databaseId"] for row in selected], [1, 2, 3])

    def test_keeps_re_runs_of_same_workflow(self) -> None:
        rows = [
            {
                "databaseId": 1,
                "workflowName": "CI",
                "status": "completed",
                "createdAt": "2026-01-01T00:00:00Z",
            },
            {
                "databaseId": 2,
                "workflowName": "CI",
                "status": "completed",
                "createdAt": "2026-01-01T03:00:00Z",
            },
        ]
        selected = select_runs(rows)
        self.assertEqual([row["databaseId"] for row in selected], [1, 2])


class SupersededTests(unittest.TestCase):
    def test_cancelled_with_newer_push_is_superseded(self) -> None:
        self.assertTrue(superseded_cancelled(True, sha_moved=True, newer_run=False))
        self.assertTrue(superseded_cancelled(True, sha_moved=False, newer_run=True))

    def test_cancelled_alone_is_not_superseded(self) -> None:
        self.assertFalse(superseded_cancelled(True, sha_moved=False, newer_run=False))

    def test_not_cancelled_is_never_superseded(self) -> None:
        self.assertFalse(superseded_cancelled(False, sha_moved=True, newer_run=True))


class ResolveShaTests(unittest.TestCase):
    def test_sha_from_pr(self) -> None:
        self.assertEqual(
            sha_from_pr({"headRefOid": "abc", "headRefName": "feat"}),
            ("abc", "feat"),
        )

    def test_sha_from_commit(self) -> None:
        self.assertEqual(sha_from_commit({"sha": "deadbeef"}), "deadbeef")

    def test_sha_from_lightweight_tag(self) -> None:
        self.assertEqual(
            sha_from_tag_ref({"object": {"type": "commit", "sha": "cafebabe"}}, None),
            "cafebabe",
        )

    def test_sha_from_annotated_tag(self) -> None:
        ref = {"object": {"type": "tag", "sha": "tagobj"}}
        tag = {"object": {"type": "commit", "sha": "cafebabe"}}
        self.assertEqual(sha_from_tag_ref(ref, tag), "cafebabe")


class GithubRunTests(unittest.TestCase):
    def test_builds_decide_run(self) -> None:
        jobs = (Job("lint", "u", True, "success", False),)
        run = github_run(
            {
                "databaseId": 9,
                "url": "https://r",
                "status": "completed",
                "conclusion": "success",
            },
            jobs,
            superseded=False,
        )
        self.assertEqual(run, Run("9", "https://r", "success", False, jobs))


class KindsTests(unittest.TestCase):
    def test_github_kinds(self) -> None:
        self.assertEqual(KINDS, frozenset({"pr", "branch", "tag", "sha", "run"}))


class ResolvePlanTests(unittest.TestCase):
    def test_resolves_and_dedupes(self) -> None:
        def runner(args: Sequence[str]) -> str:
            joined = " ".join(args)
            if joined.startswith("pr view 12 "):
                return json.dumps({"headRefOid": "aaa", "headRefName": "feat"})
            if "repos/o/r/commits/main" in joined:
                return json.dumps({"sha": "bbb"})
            if "git/ref/tags/v1" in joined:
                return json.dumps({"object": {"type": "commit", "sha": "ccc"}})
            raise AssertionError(joined)

        plan = resolve_plan(
            (
                Target("pr", "12"),
                Target("sha", "aaa"),
                Target("branch", "main"),
                Target("tag", "v1"),
                Target("run", "99"),
                Target("run", "99"),
            ),
            "o/r",
            runner=runner,
        )
        self.assertEqual(
            plan,
            Plan(
                "o/r",
                (
                    ShaWatch("aaa", branch="feat", pr="12"),
                    ShaWatch("bbb", branch="main"),
                    ShaWatch("ccc"),
                ),
                ("99",),
            ),
        )


class FetchRunsTests(unittest.TestCase):
    def test_maps_jobs_and_continue_on_error(self) -> None:
        yaml = """
jobs:
  soft:
    name: Soft Check
    continue-on-error: true
    runs-on: ubuntu-latest
  lint:
    runs-on: ubuntu-latest
"""
        b64 = base64.b64encode(yaml.encode()).decode()

        def runner(args: Sequence[str]) -> str:
            joined = " ".join(args)
            if joined.startswith("run list ") and "-c abc" in joined:
                return json.dumps(
                    [
                        {
                            "databaseId": 7,
                            "workflowName": "CI",
                            "status": "completed",
                            "conclusion": "success",
                            "createdAt": "2026-01-01T00:00:00Z",
                            "url": "https://r/7",
                            "headSha": "abc",
                            "headBranch": "feat",
                        }
                    ]
                )
            if joined.startswith("run view 7 "):
                return json.dumps(
                    {
                        "databaseId": 7,
                        "status": "completed",
                        "conclusion": "success",
                        "url": "https://r/7",
                        "workflowName": "CI",
                        "headSha": "abc",
                        "headBranch": "feat",
                        "jobs": [
                            {
                                "name": "Soft Check",
                                "status": "completed",
                                "conclusion": "failure",
                                "url": "https://j/soft",
                            },
                            {
                                "name": "lint",
                                "status": "completed",
                                "conclusion": "success",
                                "url": "https://j/lint",
                            },
                        ],
                    }
                )
            if "actions/runs/7" in joined and "head_sha" in joined:
                return json.dumps({"path": ".github/workflows/ci.yml", "head_sha": "abc"})
            if "contents/.github/workflows/ci.yml" in joined:
                return json.dumps({"content": b64})
            raise AssertionError(joined)

        runs = fetch_runs(Plan("o/r", (ShaWatch("abc", branch="feat"),), ()), runner=runner)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].status, "success")
        soft, lint = runs[0].jobs
        self.assertTrue(soft.allowed_failure)
        self.assertEqual(soft.conclusion, "failure")
        self.assertFalse(lint.allowed_failure)


if __name__ == "__main__":
    unittest.main()

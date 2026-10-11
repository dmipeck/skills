#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest
from collections.abc import Sequence

from decide import Job, Remote, Target, Verdict, decide
from wait_gitlab import (
    Resolved,
    fetch_runs,
    map_job,
    map_pipeline,
    map_pipeline_status,
    pipeline_superseded,
    resolve_targets,
)


class MapJobTests(unittest.TestCase):
    def test_failed_job_maps_hard_failure_and_allow_failure(self) -> None:
        job = map_job(
            {
                "id": 9,
                "name": "lint",
                "status": "failed",
                "allow_failure": False,
                "web_url": "https://gitlab.example/j/9",
                "failure_reason": "script_failure",
            }
        )
        self.assertEqual(
            job,
            Job(
                name="lint",
                url="https://gitlab.example/j/9",
                done=True,
                conclusion="failure",
                allowed_failure=False,
            ),
        )

    def test_allow_failure_true_marks_soft(self) -> None:
        job = map_job(
            {
                "id": 2,
                "name": "flake",
                "status": "failed",
                "allow_failure": True,
                "web_url": "https://gitlab.example/j/2",
            }
        )
        self.assertTrue(job.allowed_failure)
        self.assertEqual(job.conclusion, "failure")

    def test_timeout_failure_reason_maps_to_timed_out(self) -> None:
        for reason in ("timeout", "stuck_or_timeout_failure", "job_execution_timeout"):
            with self.subTest(reason=reason):
                job = map_job(
                    {
                        "id": 1,
                        "name": "slow",
                        "status": "failed",
                        "allow_failure": False,
                        "web_url": "https://gitlab.example/j/1",
                        "failure_reason": reason,
                    }
                )
                self.assertEqual(job.conclusion, "timed_out")

    def test_runner_system_failure_maps_to_startup_failure(self) -> None:
        job = map_job(
            {
                "id": 1,
                "name": "boot",
                "status": "failed",
                "allow_failure": False,
                "web_url": "https://gitlab.example/j/1",
                "failure_reason": "runner_system_failure",
            }
        )
        self.assertEqual(job.conclusion, "startup_failure")

    def test_running_job_is_not_done(self) -> None:
        job = map_job(
            {
                "id": 3,
                "name": "test",
                "status": "running",
                "allow_failure": False,
                "web_url": "https://gitlab.example/j/3",
            }
        )
        self.assertFalse(job.done)
        self.assertIsNone(job.conclusion)

    def test_manual_job_is_not_done(self) -> None:
        job = map_job(
            {
                "id": 4,
                "name": "deploy",
                "status": "manual",
                "allow_failure": False,
                "web_url": "https://gitlab.example/j/4",
            }
        )
        self.assertFalse(job.done)
        self.assertIsNone(job.conclusion)

    def test_canceled_job_is_done(self) -> None:
        job = map_job(
            {
                "id": 5,
                "name": "build",
                "status": "canceled",
                "allow_failure": False,
                "web_url": "https://gitlab.example/j/5",
            }
        )
        self.assertTrue(job.done)
        self.assertEqual(job.conclusion, "cancelled")


class MapPipelineTests(unittest.TestCase):
    def test_status_aliases(self) -> None:
        self.assertEqual(map_pipeline_status("success"), "success")
        self.assertEqual(map_pipeline_status("failed"), "failure")
        self.assertEqual(map_pipeline_status("canceled"), "cancelled")
        self.assertEqual(map_pipeline_status("skipped"), "skipped")
        self.assertEqual(map_pipeline_status("manual"), "blocked")
        self.assertEqual(map_pipeline_status("running"), "pending")
        self.assertEqual(map_pipeline_status("pending"), "pending")
        self.assertEqual(map_pipeline_status("created"), "pending")

    def test_map_pipeline_builds_run(self) -> None:
        run = map_pipeline(
            {
                "id": 77,
                "status": "running",
                "web_url": "https://gitlab.example/p/77",
            },
            (
                {
                    "id": 1,
                    "name": "lint",
                    "status": "success",
                    "allow_failure": False,
                    "web_url": "https://gitlab.example/j/1",
                },
                {
                    "id": 2,
                    "name": "test",
                    "status": "running",
                    "allow_failure": False,
                    "web_url": "https://gitlab.example/j/2",
                },
            ),
        )
        self.assertEqual(run.id, "77")
        self.assertEqual(run.url, "https://gitlab.example/p/77")
        self.assertEqual(run.status, "pending")
        self.assertFalse(run.superseded)
        self.assertEqual(len(run.jobs), 2)
        self.assertTrue(run.jobs[0].done)
        self.assertFalse(run.jobs[1].done)

    def test_superseded_flag_passes_through(self) -> None:
        run = map_pipeline(
            {"id": 1, "status": "canceled", "web_url": "https://gitlab.example/p/1"},
            (),
            superseded=True,
        )
        self.assertTrue(run.superseded)
        self.assertEqual(run.status, "cancelled")

    def test_hard_fail_through_decide(self) -> None:
        run = map_pipeline(
            {"id": 1, "status": "failed", "web_url": "https://gitlab.example/p/1"},
            (
                {
                    "id": 9,
                    "name": "lint",
                    "status": "failed",
                    "allow_failure": False,
                    "web_url": "https://gitlab.example/j/9",
                },
            ),
        )
        decision = decide((run,), fail_on_allowed=False)
        self.assertEqual(decision.verdict, Verdict.FAILED)
        self.assertEqual(decision.job.name, "lint")

    def test_allow_failure_does_not_halt_decide(self) -> None:
        run = map_pipeline(
            {"id": 1, "status": "running", "web_url": "https://gitlab.example/p/1"},
            (
                {
                    "id": 9,
                    "name": "flake",
                    "status": "failed",
                    "allow_failure": True,
                    "web_url": "https://gitlab.example/j/9",
                },
                {
                    "id": 10,
                    "name": "test",
                    "status": "running",
                    "allow_failure": False,
                    "web_url": "https://gitlab.example/j/10",
                },
            ),
        )
        decision = decide((run,), fail_on_allowed=False)
        self.assertEqual(decision.verdict, Verdict.WAIT)


class SupersededHelperTests(unittest.TestCase):
    def test_canceled_with_newer_pipeline_id(self) -> None:
        self.assertTrue(
            pipeline_superseded(
                {"id": 10, "status": "canceled"},
                latest_id_for_ref=12,
                watched_sha="aaa",
                current_sha="aaa",
            )
        )

    def test_canceled_when_watched_sha_moved(self) -> None:
        self.assertTrue(
            pipeline_superseded(
                {"id": 10, "status": "canceled"},
                latest_id_for_ref=10,
                watched_sha="aaa",
                current_sha="bbb",
            )
        )

    def test_success_is_never_superseded(self) -> None:
        self.assertFalse(
            pipeline_superseded(
                {"id": 10, "status": "success"},
                latest_id_for_ref=99,
                watched_sha="aaa",
                current_sha="bbb",
            )
        )

    def test_canceled_alone_is_not_superseded(self) -> None:
        self.assertFalse(
            pipeline_superseded(
                {"id": 10, "status": "canceled"},
                latest_id_for_ref=10,
                watched_sha="aaa",
                current_sha="aaa",
            )
        )


REMOTE = Remote("origin", "gitlab.example", "group/project")


def _runner(table: dict[tuple[str, ...], object]):
    def run(args: Sequence[str]) -> str:
        key = tuple(args)
        if key not in table:
            raise AssertionError(f"unexpected glab args: {key}")
        payload = table[key]
        return json.dumps(payload)

    return run


class ResolveTargetsTests(unittest.TestCase):
    def test_pipeline_and_sha_pass_through(self) -> None:
        resolved = resolve_targets(
            (Target("pipeline", "55"), Target("sha", "abc")),
            remote=REMOTE,
            runner=_runner({}),
        )
        self.assertEqual(resolved[0].pipeline_id, "55")
        self.assertEqual(resolved[1].sha, "abc")

    def test_mr_resolves_sha_once(self) -> None:
        runner = _runner(
            {
                (
                    "glab",
                    "mr",
                    "view",
                    "42",
                    "-R",
                    "group/project",
                    "-F",
                    "json",
                ): {
                    "sha": "deadbeef",
                    "source_branch": "feature",
                }
            }
        )
        resolved = resolve_targets((Target("mr", "42"),), remote=REMOTE, runner=runner)
        self.assertEqual(resolved[0].sha, "deadbeef")
        self.assertEqual(resolved[0].ref, "feature")

    def test_branch_resolves_via_api(self) -> None:
        runner = _runner(
            {
                (
                    "glab",
                    "api",
                    "projects/group%2Fproject/repository/commits/main",
                    "--hostname",
                    "gitlab.example",
                ): {"id": "cafebabe"}
            }
        )
        resolved = resolve_targets((Target("branch", "main"),), remote=REMOTE, runner=runner)
        self.assertEqual(resolved[0].sha, "cafebabe")


class FetchRunsTests(unittest.TestCase):
    def test_pipeline_target_maps_jobs_and_allow_failure(self) -> None:
        runner = _runner(
            {
                (
                    "glab",
                    "ci",
                    "get",
                    "-R",
                    "group/project",
                    "-p",
                    "77",
                    "-F",
                    "json",
                    "-d",
                ): {
                    "id": 77,
                    "status": "failed",
                    "sha": "abc",
                    "ref": "main",
                    "web_url": "https://gitlab.example/p/77",
                    "jobs": [
                        {
                            "id": 1,
                            "name": "lint",
                            "status": "failed",
                            "allow_failure": False,
                            "web_url": "https://gitlab.example/j/1",
                        },
                        {
                            "id": 2,
                            "name": "flake",
                            "status": "failed",
                            "allow_failure": True,
                            "web_url": "https://gitlab.example/j/2",
                        },
                    ],
                },
                (
                    "glab",
                    "ci",
                    "list",
                    "-R",
                    "group/project",
                    "--ref",
                    "main",
                    "-F",
                    "json",
                    "-P",
                    "1",
                ): [{"id": 77}],
            }
        )
        runs = fetch_runs(
            (Resolved("pipeline", "77", sha=None, pipeline_id="77", ref=None),),
            remote=REMOTE,
            runner=runner,
        )
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].jobs[0].allowed_failure, False)
        self.assertEqual(runs[0].jobs[1].allowed_failure, True)
        decision = decide(runs, fail_on_allowed=False)
        self.assertEqual(decision.verdict, Verdict.FAILED)
        self.assertEqual(decision.job.name, "lint")

    def test_sha_lists_pipelines_then_fetches_jobs(self) -> None:
        runner = _runner(
            {
                (
                    "glab",
                    "ci",
                    "list",
                    "-R",
                    "group/project",
                    "--sha",
                    "abc",
                    "-F",
                    "json",
                ): [
                    {
                        "id": 9,
                        "status": "success",
                        "sha": "abc",
                        "ref": "main",
                        "web_url": "https://gitlab.example/p/9",
                    }
                ],
                (
                    "glab",
                    "ci",
                    "get",
                    "-R",
                    "group/project",
                    "-p",
                    "9",
                    "-F",
                    "json",
                    "-d",
                ): {
                    "id": 9,
                    "status": "success",
                    "sha": "abc",
                    "ref": "main",
                    "web_url": "https://gitlab.example/p/9",
                    "jobs": [
                        {
                            "id": 1,
                            "name": "test",
                            "status": "success",
                            "allow_failure": False,
                            "web_url": "https://gitlab.example/j/1",
                        }
                    ],
                },
                (
                    "glab",
                    "ci",
                    "list",
                    "-R",
                    "group/project",
                    "--ref",
                    "main",
                    "-F",
                    "json",
                    "-P",
                    "1",
                ): [{"id": 9}],
            }
        )
        runs = fetch_runs(
            (Resolved("sha", "abc", sha="abc", pipeline_id=None, ref=None),),
            remote=REMOTE,
            runner=runner,
        )
        self.assertEqual(runs[0].status, "success")
        self.assertEqual(decide(runs, fail_on_allowed=False).verdict, Verdict.OK)


if __name__ == "__main__":
    unittest.main()


#!/usr/bin/env python3
from __future__ import annotations

import unittest

from decide import Decision, Job, Run, Verdict, decide


def job(
    name: str,
    *,
    done: bool = True,
    conclusion: str | None = "success",
    allowed_failure: bool = False,
    url: str = "https://example.test/job",
) -> Job:
    return Job(name, url, done, conclusion, allowed_failure)


def run(
    run_id: str = "1",
    *,
    status: str = "success",
    superseded: bool = False,
    jobs: tuple[Job, ...] = (),
    url: str = "https://example.test/run",
) -> Run:
    return Run(run_id, url, status, superseded, jobs)


class DecideFailFastTests(unittest.TestCase):
    def test_hard_failure_halts_immediately(self) -> None:
        failed = job("lint", conclusion="failure")
        pending = job("test", done=False, conclusion=None)
        decision = decide((run(jobs=(failed, pending), status="pending"),), fail_on_allowed=False)
        self.assertEqual(decision.verdict, Verdict.FAILED)
        self.assertEqual(decision.reason, "job")
        self.assertIs(decision.job, failed)

    def test_timed_out_and_startup_failure_are_hard(self) -> None:
        for conclusion in ("timed_out", "startup_failure"):
            with self.subTest(conclusion=conclusion):
                decision = decide(
                    (run(jobs=(job("build", conclusion=conclusion),), status="failure"),),
                    fail_on_allowed=False,
                )
                self.assertEqual(decision.verdict, Verdict.FAILED)
                self.assertEqual(decision.reason, "job")
                self.assertEqual(decision.job.conclusion, conclusion)

    def test_allowed_failure_does_not_halt_by_default(self) -> None:
        soft = job("flake", conclusion="failure", allowed_failure=True)
        pending = job("test", done=False, conclusion=None)
        decision = decide((run(jobs=(soft, pending), status="pending"),), fail_on_allowed=False)
        self.assertEqual(decision.verdict, Verdict.WAIT)
        self.assertEqual(decision.pending, (pending,))

    def test_fail_on_allowed_halts_on_soft_failure(self) -> None:
        soft = job("flake", conclusion="failure", allowed_failure=True)
        pending = job("test", done=False, conclusion=None)
        decision = decide((run(jobs=(soft, pending), status="pending"),), fail_on_allowed=True)
        self.assertEqual(decision.verdict, Verdict.FAILED)
        self.assertIs(decision.job, soft)


class DecideWaitAndOkTests(unittest.TestCase):
    def test_pending_job_means_wait(self) -> None:
        decision = decide(
            (run(jobs=(job("test", done=False, conclusion=None),), status="pending"),),
            fail_on_allowed=False,
        )
        self.assertEqual(decision.verdict, Verdict.WAIT)

    def test_pending_run_without_jobs_means_wait(self) -> None:
        decision = decide((run(jobs=(), status="pending"),), fail_on_allowed=False)
        self.assertEqual(decision.verdict, Verdict.WAIT)

    def test_empty_runs_means_wait(self) -> None:
        decision = decide((), fail_on_allowed=False)
        self.assertEqual(decision.verdict, Verdict.WAIT)

    def test_allowed_failure_must_finish_before_ok(self) -> None:
        soft = job("flake", done=False, conclusion=None, allowed_failure=True)
        ok = job("test", conclusion="success")
        decision = decide((run(jobs=(soft, ok), status="pending"),), fail_on_allowed=False)
        self.assertEqual(decision.verdict, Verdict.WAIT)

    def test_all_success_is_ok(self) -> None:
        decision = decide(
            (run(jobs=(job("test"), job("lint")), status="success"),),
            fail_on_allowed=False,
        )
        self.assertEqual(decision.verdict, Verdict.OK)

    def test_finished_allowed_failure_with_green_aggregate_is_ok(self) -> None:
        soft = job("flake", conclusion="failure", allowed_failure=True)
        ok = job("test", conclusion="success")
        decision = decide((run(jobs=(soft, ok), status="success"),), fail_on_allowed=False)
        self.assertEqual(decision.verdict, Verdict.OK)


class DecideAggregateTests(unittest.TestCase):
    def test_superseded_cancelled_run(self) -> None:
        decision = decide(
            (run(jobs=(job("test"),), status="cancelled", superseded=True),),
            fail_on_allowed=False,
        )
        self.assertEqual(decision.verdict, Verdict.SUPERSEDED)

    def test_superseded_waits_while_jobs_pending(self) -> None:
        decision = decide(
            (
                run(
                    jobs=(job("test", done=False, conclusion=None),),
                    status="cancelled",
                    superseded=True,
                ),
            ),
            fail_on_allowed=False,
        )
        self.assertEqual(decision.verdict, Verdict.WAIT)

    def test_aggregate_failure_is_failed(self) -> None:
        decision = decide(
            (run(jobs=(job("test"),), status="failure"),),
            fail_on_allowed=False,
        )
        self.assertEqual(decision.verdict, Verdict.FAILED)
        self.assertEqual(decision.reason, "aggregate")

    def test_blocked_aggregate_is_failed(self) -> None:
        decision = decide(
            (run(jobs=(job("test"),), status="blocked"),),
            fail_on_allowed=False,
        )
        self.assertEqual(decision.verdict, Verdict.FAILED)
        self.assertEqual(decision.reason, "blocked")

    def test_cancelled_skipped_other_aggregates_are_failed(self) -> None:
        for status in ("cancelled", "skipped", "neutral"):
            with self.subTest(status=status):
                decision = decide(
                    (run(jobs=(job("test"),), status=status, superseded=False),),
                    fail_on_allowed=False,
                )
                self.assertEqual(decision.verdict, Verdict.FAILED)
                self.assertIn(decision.reason, {"aggregate", "blocked"})


if __name__ == "__main__":
    unittest.main()

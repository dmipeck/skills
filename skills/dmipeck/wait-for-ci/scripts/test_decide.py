#!/usr/bin/env python3
from __future__ import annotations

import unittest

from decide import (
    Decision,
    Job,
    Remote,
    Run,
    Target,
    TargetError,
    Verdict,
    allowed_job_names,
    argument_parser,
    choose_remote,
    decide,
    exit_code,
    format_report,
    parse_remotes,
    parse_targets,
    watch,
)


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


class FormatAndExitTests(unittest.TestCase):
    def test_ok_report_and_exit(self) -> None:
        decision = Decision(Verdict.OK, "ok")
        self.assertEqual(format_report(decision), "OK\n")
        self.assertEqual(exit_code(Verdict.OK), 0)

    def test_job_failure_report(self) -> None:
        failed = job("lint", conclusion="failure", url="https://ci/j")
        decision = Decision(Verdict.FAILED, "job", job=failed, run=run())
        self.assertEqual(
            format_report(decision),
            "Failed\njob: lint\nconclusion: failure\nurl: https://ci/j\n",
        )
        self.assertEqual(exit_code(Verdict.FAILED), 1)

    def test_aggregate_and_blocked_reports(self) -> None:
        agg = Decision(Verdict.FAILED, "aggregate", run=run("9", status="failure", url="https://ci/r"))
        self.assertEqual(
            format_report(agg),
            "Failed\naggregate: failure\nrun: 9\nurl: https://ci/r\n",
        )
        blocked = Decision(Verdict.FAILED, "blocked", run=run("9", status="blocked", url="https://ci/r"))
        self.assertEqual(
            format_report(blocked),
            "Blocked\naggregate: blocked\nrun: 9\nurl: https://ci/r\n",
        )

    def test_superseded_and_timeout_reports(self) -> None:
        superseded = Decision(Verdict.SUPERSEDED, "superseded", run=run("3", url="https://ci/r"))
        self.assertEqual(format_report(superseded), "Superseded\nrun: 3\nurl: https://ci/r\n")
        self.assertEqual(exit_code(Verdict.SUPERSEDED), 2)
        pending = job("test", done=False, conclusion=None, url="https://ci/j")
        timed = Decision(
            Verdict.TIMED_OUT,
            "timeout",
            pending=(pending,),
            runs=(run(jobs=(pending,), status="pending"),),
        )
        self.assertEqual(
            format_report(timed),
            "Timed out\njob: test\nstatus: pending\nurl: https://ci/j\n",
        )
        self.assertEqual(exit_code(Verdict.TIMED_OUT), 3)


class WatchTests(unittest.TestCase):
    def test_watch_returns_terminal_without_sleep_when_already_done(self) -> None:
        sleeps: list[float] = []
        decision = watch(
            lambda: (run(jobs=(job("test"),), status="success"),),
            fail_on_allowed=False,
            timeout_s=None,
            sleep=sleeps.append,
            monotonic=lambda: 0.0,
        )
        self.assertEqual(decision.verdict, Verdict.OK)
        self.assertEqual(sleeps, [])

    def test_watch_backoff_doubles_to_max(self) -> None:
        sleeps: list[float] = []
        clock = {"t": 0.0}
        polls = {"n": 0}

        def fetch() -> tuple[Run, ...]:
            polls["n"] += 1
            if polls["n"] < 4:
                return (run(jobs=(job("test", done=False, conclusion=None),), status="pending"),)
            return (run(jobs=(job("test"),), status="success"),)

        def sleep(delay: float) -> None:
            sleeps.append(delay)
            clock["t"] += delay

        decision = watch(
            fetch,
            fail_on_allowed=False,
            timeout_s=None,
            sleep=sleep,
            monotonic=lambda: clock["t"],
        )
        self.assertEqual(decision.verdict, Verdict.OK)
        self.assertEqual(sleeps, [15.0, 30.0, 60.0])

    def test_watch_timeout_lists_unfinished_jobs(self) -> None:
        sleeps: list[float] = []
        clock = {"t": 0.0}
        pending = job("test", done=False, conclusion=None, url="https://ci/j")

        def sleep(delay: float) -> None:
            sleeps.append(delay)
            clock["t"] += delay

        decision = watch(
            lambda: (run(jobs=(pending,), status="pending"),),
            fail_on_allowed=False,
            timeout_s=20.0,
            sleep=sleep,
            monotonic=lambda: clock["t"],
        )
        self.assertEqual(decision.verdict, Verdict.TIMED_OUT)
        self.assertEqual(decision.pending, (pending,))
        self.assertEqual(sleeps, [15.0, 5.0])


class TargetTests(unittest.TestCase):
    def test_parse_targets(self) -> None:
        kinds = frozenset({"pr", "branch", "sha", "run", "tag"})
        self.assertEqual(
            parse_targets(["pr:12", "sha:abc"], kinds),
            (Target("pr", "12"), Target("sha", "abc")),
        )

    def test_parse_targets_rejects_empty_and_bad_kind(self) -> None:
        kinds = frozenset({"pr", "branch"})
        with self.assertRaises(TargetError):
            parse_targets([], kinds)
        with self.assertRaises(TargetError):
            parse_targets(["pr"], kinds)
        with self.assertRaises(TargetError):
            parse_targets(["mr:1"], kinds)


class RemoteTests(unittest.TestCase):
    def test_parse_and_choose_origin(self) -> None:
        text = (
            "origin\tgit@github.com:dmipeck/skills.git (fetch)\n"
            "origin\tgit@github.com:dmipeck/skills.git (push)\n"
            "upstream\thttps://github.com/other/skills.git (fetch)\n"
        )
        remotes = parse_remotes(text)
        self.assertEqual(
            remotes,
            (
                Remote("origin", "github.com", "dmipeck/skills"),
                Remote("upstream", "github.com", "other/skills"),
            ),
        )
        chosen = choose_remote(remotes, accept_hosts=frozenset({"github.com"}))
        self.assertEqual(chosen.name, "origin")
        self.assertEqual(chosen.slug, "dmipeck/skills")

    def test_choose_remote_rejects_when_ambiguous(self) -> None:
        remotes = (
            Remote("a", "gitlab.com", "org/a"),
            Remote("b", "gitlab.com", "org/b"),
        )
        with self.assertRaises(TargetError):
            choose_remote(remotes, accept_hosts=frozenset({"gitlab.com"}))


class AllowedJobNamesTests(unittest.TestCase):
    def test_literal_continue_on_error_true(self) -> None:
        yaml = """
name: ci
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - run: true
  soft:
    name: Soft Check
    continue-on-error: true
    runs-on: ubuntu-latest
    steps:
      - continue-on-error: true
        run: false
  expr:
    continue-on-error: ${{ true }}
    name: Dyn ${{ matrix.os }}
    runs-on: ubuntu-latest
"""
        self.assertEqual(allowed_job_names(yaml), frozenset({"soft", "Soft Check"}))

    def test_missing_jobs_is_empty(self) -> None:
        self.assertEqual(allowed_job_names("name: only\n"), frozenset())


class ArgumentParserTests(unittest.TestCase):
    def test_shared_flags(self) -> None:
        parser = argument_parser("wait_github.py")
        args = parser.parse_args(["--fail-on-allowed", "--timeout", "90", "pr:1", "branch:main"])
        self.assertTrue(args.fail_on_allowed)
        self.assertEqual(args.timeout, 90.0)
        self.assertEqual(args.targets, ["pr:1", "branch:main"])

    def test_requires_targets(self) -> None:
        parser = argument_parser("wait_github.py")
        with self.assertRaises(SystemExit) as raised:
            parser.parse_args([])
        self.assertEqual(raised.exception.code, 1)


if __name__ == "__main__":
    unittest.main()


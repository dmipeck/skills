"""Pure wait verdict for CI job snapshots."""

from __future__ import annotations

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

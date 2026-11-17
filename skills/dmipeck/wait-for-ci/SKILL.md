---
name: wait-for-ci
description: >-
  Wait for CI to reach a definitive result. Use when waiting on GitHub
  Actions, GitLab pipelines, Gitea Actions, or check runs.
---

# Wait for CI

Run the forge script for the host. Scripts watch **jobs** (not aggregate
status), fail-fast on the first hard failure, and print a short report.

## Scripts

| Host | Script | CLI |
|---|---|---|
| GitHub | `scripts/wait_github.py` | `gh` |
| GitLab | `scripts/wait_gitlab.py` | `glab` |
| Gitea | `scripts/wait_gitea.py` | `tea` |

```bash
python <this-skill>/scripts/wait_github.py pr:42
python <this-skill>/scripts/wait_gitlab.py mr:7 --timeout 1800
python <this-skill>/scripts/wait_gitea.py branch:main --fail-on-allowed
```

Pass one or more `KIND:VALUE` targets (required; never infer from the
checkout). Multiple targets are watched as a union (deduped).

| Host | Kinds |
|---|---|
| GitHub / Gitea | `pr`, `branch`, `tag`, `sha`, `run` |
| GitLab | `mr`, `branch`, `tag`, `sha`, `pipeline` |

Flags:

- `--fail-on-allowed` — treat the first allowed/soft failure like a hard
  failure (default: ignore soft fails for halt, still wait for them before
  the final aggregate check).
- `--timeout <seconds>` — stop with **Timed out** and list unfinished jobs.
  Omit to poll until a terminal verdict.

## Loop (implemented by the scripts)

1. **Resolve** each target once at startup (PR/MR/branch/tag → commit SHA;
   `run` / `pipeline` → that id only). Targets are required; never infer.
2. **List jobs** each poll. Track conclusion/status and whether the job is
   **allowed to fail**.
3. **PR/MR merge check** (only when a `pr` or `mr` target is in the set),
   before the job verdict. Each poll asks the forge whether that PR/MR must
   be updated onto its base before merge.
   - Required → **Needs rebase** and abort, even if a job has already
     failed or is still running. Do not claim OK. This wait does not
     rebase; re-run after the branch is updated.
   - Not computed yet (GitHub `UNKNOWN`; GitLab `checking`, `unchecked`,
     `preparing`, `approvals_syncing`, `ci_still_running`) → keep polling.
     Do not report **OK** until the merge check is known.
   - `branch`, `tag`, `sha`, `run`, and `pipeline` targets are not a PR
     merge check.
4. **Fail fast:** first job with a hard conclusion (`failure`, `timed_out`,
   `startup_failure`, or forge alias) that is **not** allowed → stop.
   Report **Failed** (job name, conclusion, URL). Do not wait for the rest.
5. **Continue** while any job is queued/running/pending (or not yet created
   while the matrix/DAG expands). Backoff ~15s, doubling up to ~60s.
6. **All jobs terminal** and none hard-failed → sanity-check aggregate
   pipeline/workflow status. Green → **OK** only when every watched PR/MR
   merge check is known and none requires a rebase. Otherwise **Failed** /
   **Blocked** with the aggregate — never claim OK.
7. Cancelled by a newer push → **Superseded**, not OK. A required rebase
   still wins over superseded.

A required rebase is the forge rule that blocks merge until the head
contains the base (GitHub protected branch “up to date”, GitLab
fast-forward `need_rebase`, Gitea `block_on_outdated_branch`). A branch
that is merely behind, or that has conflicts, does not abort when the
forge will still merge it.

Allowed failure: GitLab job `allow_failure`; GitHub/Gitea only a literal
job-level `continue-on-error: true` in that run's workflow (job id or
static `name`). Branch-protection "optional" alone does not mark allowed.

## Platform notes

| Concept | GitHub Actions | GitLab CI | Gitea Actions |
|---|---|---|---|
| Run | workflow run | pipeline | workflow run |
| Unit | job | job | job |
| Soft fail | `continue-on-error: true` | `allow_failure` | `continue-on-error: true` |
| Aggregate | workflow / check suite | pipeline status | workflow run |
| Must rebase | `mergeStateStatus` `BEHIND` | `detailed_merge_status` `need_rebase` | base protection `block_on_outdated_branch` and the base has commits the head lacks |

## Report shape

Stdout is short; exit codes: OK=0, Failed=1, Superseded=2, Timed out=3,
Needs rebase=4.

- **OK** — all jobs done, no hard failures, aggregate green. A watched
  PR/MR whose merge check is still unknown stays a wait, not OK.
- **Failed** — first hard-failed job (name + link), or non-green aggregate.
- **Needs rebase** — `pr`/`mr`, base branch, URL. Abort. The PR cannot merge
  until it is updated onto that base.
- **Superseded / Timed out / Blocked** — say which; list unfinished jobs
  when relevant.

Do not dump full job logs unless asked or needed to name the failing step.

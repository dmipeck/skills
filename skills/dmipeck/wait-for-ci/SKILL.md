---
name: wait-for-ci
description: >-
  Wait for CI to reach a definitive result. Use when waiting on GitHub
  Actions, GitLab pipelines, Gitea Actions, or check runs.
---

# Wait for CI

## Auth

Status of each forge CLI at skill load. Use the host that matches the
target; if that host shows failed or logged-out, run that CLI's login
before waiting. For GitLab, run `glab auth login` (opens a browser for the
user to log in).

```!
gh auth status
```

```!
glab auth status
```

```!
tea auth status
```

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
3. **Fail fast:** first job with a hard conclusion (`failure`, `timed_out`,
   `startup_failure`, or forge alias) that is **not** allowed → stop.
   Report **Failed** (job name, conclusion, URL). Do not wait for the rest.
4. **Continue** while any job is queued/running/pending (or not yet created
   while the matrix/DAG expands). Backoff ~15s, doubling up to ~60s.
5. **All jobs terminal** and none hard-failed → sanity-check aggregate
   pipeline/workflow status. Green → **OK**. Otherwise **Failed** /
   **Blocked** with the aggregate — never claim OK.
6. Cancelled by a newer push → **Superseded**, not OK.

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

## Report shape

Stdout is short; exit codes: OK=0, Failed=1, Superseded=2, Timed out=3.

- **OK** — all jobs done, no hard failures, aggregate green.
- **Failed** — first hard-failed job (name + link), or non-green aggregate.
- **Superseded / Timed out / Blocked** — say which; list unfinished jobs
  when relevant.

Do not dump full job logs unless asked or needed to name the failing step.

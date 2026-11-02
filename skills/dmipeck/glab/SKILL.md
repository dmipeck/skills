---
name: glab
description: >-
  Authenticate the GitLab CLI (`glab`) before any `glab` work. Use when
  running `glab`, opening GitLab MRs/issues/pipelines via CLI, or when
  `glab auth` fails.
---

# glab

Gate every `glab` session on auth. Do this before the first `glab` command in
the task.

## 1. Check

```bash
bash <this-skill>/scripts/check-auth.sh
```

Pass `--hostname <host>` (or `--all`) when the default context is wrong.

Exit 0 → continue. Non-zero (or output shows failed / logged out) → §2.

## 2. Login — JUST DO IT

If check failed, **run login yourself via Shell immediately**:

```bash
glab auth login --web --git-protocol https
```

Add `--hostname <host>` when the instance is not inferred from the repo /
`GITLAB_HOST` (self-managed / Dedicated).

- **Never** ask the user to run `glab auth login`.
- **Never** ask permission to run it.
- **Never** stop with "please log in".
- Open the browser flow, wait until it finishes, re-run §1, then continue the
  original task.

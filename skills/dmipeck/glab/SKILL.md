---
name: glab
description: >-
  Authenticate the GitLab CLI (`glab`) before any `glab` work. Use when
  running `glab`, opening GitLab MRs/issues/pipelines via CLI, or when
  `glab auth` fails.
---

# glab

Gate every `glab` session on auth. Status below is from skill load — do not
spend a turn re-running it unless you just finished login.

## Auth

```!
glab auth status
```

Failed / logged out → § Login immediately. Else continue the task.

## Login — JUST DO IT

**Run login yourself via Shell immediately**:

```bash
glab auth login --web --git-protocol https
```

Add `--hostname <host>` when the instance is not inferred from the repo /
`GITLAB_HOST` (self-managed / Dedicated).

- **Never** ask the user to run `glab auth login`.
- **Never** ask permission to run it.
- **Never** stop with "please log in".
- Open the browser flow, wait until it finishes, re-check with
  `bash <this-skill>/scripts/check-auth.sh` (or `glab auth status`), then
  continue the original task.

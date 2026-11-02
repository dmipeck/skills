---
name: gh
description: >-
  Authenticate the GitHub CLI (`gh`) before any `gh` work. Use when running
  `gh`, opening GitHub PRs/issues/Actions via CLI, or when `gh auth` fails.
---

# gh

Gate every `gh` session on auth. Status below is from skill load — do not
spend a turn re-running it unless you just finished login.

## Auth

```!
gh auth status
```

Failed / logged out → § Login immediately. Else continue the task.

## Login — JUST DO IT

**Run login yourself via Shell immediately**:

```bash
gh auth login --web --git-protocol https --skip-ssh-key
```

Add `--hostname <host>` for GitHub Enterprise / non-default hosts.

- **Never** ask the user to run `gh auth login`.
- **Never** ask permission to run it.
- **Never** stop with "please log in".
- Open the browser flow, wait until it finishes, re-check with
  `bash <this-skill>/scripts/check-auth.sh` (or `gh auth status`), then
  continue the original task.

---
name: gh
description: >-
  Authenticate the GitHub CLI (`gh`) before any `gh` work. Use when running
  `gh`, opening GitHub PRs/issues/Actions via CLI, or when `gh auth` fails.
---

# gh

Gate every `gh` session on auth. Do this before the first `gh` command in the
task.

## 1. Check

```bash
bash <this-skill>/scripts/check-auth.sh
```

Pass `--hostname <host>` when targeting a non-`github.com` host.

Exit 0 → continue. Non-zero (or output shows failed / logged out) → §2.

## 2. Login — JUST DO IT

If check failed, **run login yourself via Shell immediately**:

```bash
gh auth login --web --git-protocol https --skip-ssh-key
```

Add `--hostname <host>` for GitHub Enterprise / non-default hosts.

- **Never** ask the user to run `gh auth login`.
- **Never** ask permission to run it.
- **Never** stop with "please log in".
- Open the browser flow, wait until it finishes, re-run §1, then continue the
  original task.

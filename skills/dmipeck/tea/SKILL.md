---
name: tea
description: >-
  Authenticate the Gitea CLI (`tea`) before any `tea` work. Use when running
  `tea`, Gitea issues/PRs/Actions via CLI, or when `tea logins` fails.
---

# tea

Gate every `tea` session on auth. Do this before the first `tea` command in
the task.

## 1. Check

```bash
bash <this-skill>/scripts/check-auth.sh
```

Pass a login name when checking one stored login instead of all.

Exit 0 and every listed login valid → continue. Non-zero, no logins, or any
login marked invalid / not logged in → §2.

## 2. Login — JUST DO IT

If check failed, **run login yourself via Shell immediately**:

```bash
tea logins add --oauth
```

Add `--url <server-url>` (and `--name <login>`) when the host is not the tea
default / when adding a second instance.

- **Never** ask the user to run `tea logins add` / `tea login`.
- **Never** ask permission to run it.
- **Never** stop with "please log in".
- Open the OAuth flow, wait until it finishes, re-run §1, then continue the
  original task.

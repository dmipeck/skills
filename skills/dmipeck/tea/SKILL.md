---
name: tea
description: >-
  Authenticate the Gitea CLI (`tea`) before any `tea` work. Use when running
  `tea`, Gitea issues/PRs/Actions via CLI, or when `tea logins` fails.
---

# tea

Gate every `tea` session on auth. Status below is from skill load — do not
spend a turn re-running it unless you just finished login.

## Auth

```!
tea logins status
```

Failed, no logins, or any login invalid → § Login immediately. Else continue
the task.

## Login — JUST DO IT

**Run login yourself via Shell immediately**:

```bash
tea logins add --oauth
```

Add `--url <server-url>` (and `--name <login>`) when the host is not the tea
default / when adding a second instance.

- **Never** ask the user to run `tea logins add` / `tea login`.
- **Never** ask permission to run it.
- **Never** stop with "please log in".
- Open the OAuth flow, wait until it finishes, re-check with
  `bash <this-skill>/scripts/check-auth.sh` (or `tea logins status`), then
  continue the original task.

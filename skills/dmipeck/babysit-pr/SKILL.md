---
name: babysit-pr
description: >-
  Babysit a PR until it is mergeable: rebase onto the default branch, wait
  for CI via wait-for-ci, fix conflicts and CI failures, then report.
disable-model-invocation: true
argument-hint: "[pr-number|url|branch]"
---

# Babysit PR

Slash-only: keep an open PR/MR mergeable. Rebase onto latest default, clear
conflicts and CI failures, then report. Do **not** merge unless asked.

## 1. Resolve target

1. Prefer the argument (PR number, URL, or branch). Else current branch's open
   PR/MR. Else ask.
2. Resolve platform CLI (GitHub → `gh`; GitLab → `glab`).
3. Note: source branch, target/default branch, HEAD SHA, PR/MR URL, draft
   vs ready.

Work in a checkout of the **source** branch (existing worktree under
`.agent/worktrees/` if present; otherwise create/use one — never edit on the
default-branch checkout).

## 2. Rebase onto default

1. Fetch origin; fast-forward the local default branch.
2. Rebase the source branch onto default (`git rebase origin/<default>`).
   Never merge the default branch in — no merge commits.
3. **Conflicts:** resolve preserving the PR's intent; prefer the change
   under review when both sides touch the same lines unless default clearly
   renamed/moved the code. Finish the rebase; do not leave it half-done.
4. If the rebase rewrote history that was already pushed:
   `git push --force-with-lease`. Never `--force` without lease.
5. If already up to date on default and clean → skip push.

Unresolvable conflict (needs product choice) → stop and report what blocked;
do not guess.

## 3. Wait for CI — fix loop

Follow the `wait-for-ci` skill on the pushed HEAD.

| Result | Action |
| --- | --- |
| **OK** | Proceed to report. |
| **Failed** | Diagnose failing job(s); fix on the source branch; commit (`conventional-commits`); push; re-run `wait-for-ci`. |
| **Superseded** | Re-resolve HEAD; wait again. |
| **Blocked / timed out** | Report status; ask whether to keep waiting. |

After each push that lands behind default again, return to **§2** before
another CI wait.

Repeat until CI is green **and** the branch is rebased on current default,
or the user stops you. Cap silent fix attempts at ~3 distinct failure
modes; then summarize and ask before looping further.

## 4. Mergeability check

Before finishing, confirm:

- [ ] Rebased on latest default (no behind-target commits)
- [ ] No unresolved conflicts; worktree clean
- [ ] Branch pushed; not ahead of upstream
- [ ] CI green per `wait-for-ci`
- [ ] PR/MR not draft (mark ready if it was draft and CI is green), unless
      the user wanted it left draft

Do not enable auto-merge or click merge unless explicitly asked.

## Report shape

Short final reply:

- **Ready** — PR/MR URL, HEAD SHA, CI OK, rebased on `<default>`.
- **Blocked** — what failed (conflict, CI job + link, permissions) and what
  you tried; next human step if any.

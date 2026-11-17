---
name: babysit-pr
description: >-
  Babysit a PR until it is mergeable
argument-hint: "[pr-number|url|branch]"
---

# Babysit PR

The goal is a **mergeable** PR/MR: CI green **and** the branch up to date
with its target, so the forge will merge without a required rebase. Rebase
onto latest default, clear conflicts and CI failures, then report. Do
**not** merge unless asked.

## 1. Resolve target

1. Prefer the argument (PR number, URL, or branch). Else current branch's open
   PR/MR. Else ask.
2. Resolve platform CLI (GitHub → `gh`; GitLab → `glab`).
3. Note: source branch, target/default branch, HEAD SHA, PR/MR URL, draft
   vs ready.

Work in a checkout of the **source** branch (existing worktree if present;
otherwise create/use one — never edit on the default-branch checkout).

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

Follow the `wait-for-ci` skill on the pushed HEAD. Mergeable means that
wait returns **OK** and does not abort with **Needs rebase**.

| Result | Action |
| --- | --- |
| **OK** | Proceed to the mergeability check. |
| **Needs rebase** | The forge will not merge until the head contains the target tip. Return to **§2**, rebase, push, re-run `wait-for-ci`. Not a CI failure. |
| **Failed** | Diagnose failing job(s); fix on the source branch; commit (`conventional-commits`); push; re-run `wait-for-ci`. |
| **Superseded** | Re-resolve HEAD; wait again. |
| **Blocked / timed out** | Report status; ask whether to keep waiting. |

After each push that lands behind the target again, return to **§2** before
another CI wait.

Repeat until CI is green **and** the PR/MR is up to date with the target
branch, or the user stops you. Cap silent fix attempts at ~3 distinct
failure modes; then summarize and ask before looping further.

## 4. Mergeability check

A PR/MR is mergeable only when CI is green and the branch is up to date
with the target. Before finishing, confirm:

- [ ] Up to date with the latest target (`wait-for-ci` did not abort with **Needs rebase**)
- [ ] No unresolved conflicts; worktree clean
- [ ] Branch pushed; not ahead of upstream
- [ ] CI green per `wait-for-ci` (**OK**)
- [ ] PR/MR not draft (mark ready if it was draft and the PR is mergeable),
      unless the user wanted it left draft

Do not enable auto-merge or click merge unless explicitly asked.

## Report shape

Short final reply:

- **Ready** — PR/MR URL, HEAD SHA, CI OK, up to date with `<target>` (mergeable).
- **Blocked** — what failed (conflict, CI job + link, permissions) and what
  you tried; next human step if any.

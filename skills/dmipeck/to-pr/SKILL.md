---
name: to-pr
description: >-
  Turn a prompted task into a PR that is done only when CI is green. Use when
  the user invokes /to-pr.
disable-model-invocation: true
argument-hint: <task>
---

# To PR

Slash-only: isolate in a worktree from the latest default tip, do the
prompted work, open a PR, and do not finish until CI is green.

## 1. Fresh worktree from default

1. Resolve the repo default branch (`main` / `master` / remote HEAD).
2. Fast-forward pull that branch — no stale base.
3. Create a **new** worktree + branch for this task
   (`.agent/worktrees/<change-name>`; keep `.agent/worktrees/` in
   `.git/info/exclude`). Do not edit on the default-branch checkout.
4. If already inside the worktree + branch for **this** task, continue;
   do not recreate.

All later reads, edits, shell, and repo-local git for this task use that
worktree only.

## 2. Do the work

Complete whatever the user prompted. Follow `git-workflow` and
`conventional-commits`. Commit and push discrete changes. Open a draft
PR/MR as soon as the first commit is pushable (GitHub → `gh`; GitLab →
`glab`). Do not merge unless asked.

## 3. Done gate — wait for CI

Not done until **all** of:

1. Worktree clean (no change-related unstaged/staged/untracked).
2. Branch pushed; not ahead of upstream.
3. **CI green** — follow the `wait-for-ci` skill. On failure: fix, push,
   re-run `wait-for-ci`. Repeat until green (or the user stops you).
4. Mark the PR/MR ready for review once CI is confirmed green.

Report the PR/MR URL and CI status. Merge stays human unless asked.

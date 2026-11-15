---
name: implement-next
description: Implement the next quick-win issue.
disable-model-invocation: true
---

# Implement next

Slash-only. One issue per run. The complement of `grill-next`.

Read `docs/agents/issue-tracker.md` and `docs/agents/triage-labels.md`. If either is missing, tell the user to run `/setup-matt-pocock-skills` and stop. List, read, and edit issues the way that tracker doc specifies. Role names below are the canonical ones; apply the label strings from the triage-label map.

**Claim** assigns the issue to the current user (GitHub: `gh issue edit <n> --add-assignee @me`). **Release** clears that assignee.

## Terms

**Quick win**: the unclaimed issue labelled `spec` and `ready-for-agent` with the narrowest user-visible change that one session can implement. The lowest issue number wins a tie. An issue labelled `ticket` and not `spec` is not a quick win.

## 1. Pick

List open issues and keep the pool:

- An issue, not a pull request.
- Labelled `spec` and `ready-for-agent`.
- No assignee.
- Not labelled `ticket`.
- Drop any `wayfinder:*` label, and any issue that carries a second state label.

A lone ticket stays out of the pool. Read each survivor. Pick the quick win, and record one sentence on why it won.

If nothing remains, or every survivor is bigger than one session, list number, title, and why it is out. Claim nothing. Stop.

Same session, already holding the claim on one pool issue: that issue is the quick win. Do not pick another.

## 2. Claim

Claim the spec before any other write. Re-read it. If the assignee is not the current user, skip it and pick the next quick win.

Then claim every open child ticket of that spec. Children are the tracker's sub-issues. Where sub-issues are unavailable, children are open issues whose body starts with `Part of #<spec>`. Leave a child already assigned to someone else, and report it. Do not claim a ticket that is not a child of this spec.

Abandoning the run before the implementation is on the pull request releases the spec and every ticket this run claimed.

## 3. Implement

The issue body is the spec. Follow `to-pr`. The work inside it is `implement-spec` on that spec.

`## Start from` in the spec names the base. When it names a branch, that branch is the integration branch: open the worktree from it. When it names a pull request, push the implementation onto that pull request. Do not open a second one. When `## Start from` names the default branch, `to-pr` starts from the latest default tip and opens the pull request.

A new pull request uses the issue's category. `bug` selects `fix`. `enhancement` selects `feat`. Branch `<fix-or-feat>/<number>-<slug>`. Title `<fix-or-feat>(<slug>): <imperative user-facing outcome>`, subject 50 characters or fewer. Body ends with `Closes #<number>`.

Child tickets of the issue are `implement-spec`'s task graph. With none, the spec is the single ticket.

`to-pr`'s done gate still applies: clean worktree, branch pushed, CI green (`wait-for-ci`), then mark the pull request ready. Do not merge.

Report the issue URL and the pull request URL.

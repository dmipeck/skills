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

**Quick win**: the unclaimed `ready-for-agent` issue with the narrowest user-visible change that one session can implement. The lowest issue number wins a tie.

## 1. Pick

List open issues and keep the pool:

- An issue, not a pull request.
- Labelled `ready-for-agent`.
- No assignee.
- Drop any `wayfinder:*` label, and any issue that carries a second state label.

Read each survivor. Pick the quick win, and record one sentence on why it won.

If nothing remains, or every survivor is bigger than one session, list number, title, and why it is out. Claim nothing. Stop.

Same session, already holding the claim on one pool issue: that issue is the quick win. Do not pick another.

## 2. Claim

Claim it before any other write. Re-read the issue. If the assignee is not the current user, skip it and pick the next quick win.

Abandoning the run before the implementation is on the pull request releases the claim.

## 3. Implement

The issue body is the spec. Follow `to-pr`. The work inside it is `implement-spec` on that spec.

`## Start from` in the spec names the base. When it names a branch, that branch is the integration branch: open the worktree from it. When it names a pull request, push the implementation onto that pull request. Do not open a second one. When `## Start from` names the default branch, `to-pr` starts from the latest default tip and opens the pull request.

A new pull request uses the issue's category. `bug` selects `fix`. `enhancement` selects `feat`. Branch `<fix-or-feat>/<number>-<slug>`. Title `<fix-or-feat>(<slug>): <imperative user-facing outcome>`, subject 50 characters or fewer. Body ends with `Closes #<number>`.

Child tickets of the issue are `implement-spec`'s task graph. With none, the spec is the single ticket.

`to-pr`'s done gate still applies: clean worktree, branch pushed, CI green (`wait-for-ci`), then mark the pull request ready. Do not merge.

Report the issue URL and the pull request URL.

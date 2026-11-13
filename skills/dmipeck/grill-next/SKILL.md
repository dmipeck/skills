---
name: grill-next
description: >-
  Grill the next quick-win issue. Use when the user invokes /grill-next.
disable-model-invocation: true
---

# Grill next

Slash-only. One issue per run. Leave the issue's product code unimplemented.

A glossary or ADR diff is the only thing that opens a pull request. No such diff, no pull request.

Read `docs/agents/issue-tracker.md` and `docs/agents/triage-labels.md`. If either is missing, tell the user to run `/setup-matt-pocock-skills` and stop. List, read, and edit issues the way that tracker doc specifies. Role names below are the canonical ones; apply the label strings from the triage-label map.

**Claim** assigns the issue to the current user (GitHub: `gh issue edit <n> --add-assignee @me`). **Release** clears that assignee.

## Terms

**Ungrilled issue**: an open, unclaimed issue that is unlabeled or labelled `needs-triage`, whose body is not a Spec. A category label (`bug` or `enhancement`) may sit beside that.

**Spec**: the `to-spec` template, stored as the issue body. A body that contains `## Problem Statement` is a Spec.

**Quick win**: the ungrilled issue with the narrowest user-visible change that still has a design decision, and that one session can finish as a Spec. The lowest issue number wins a tie.

## 1. Pick

List open issues and keep the pool:

- An issue, not a pull request.
- No assignee.
- State is unlabeled or `needs-triage` only. Drop `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`, any `wayfinder:*` label, and any issue that carries two state labels.
- Body is not a Spec.

Read each survivor. Drop a typo, chore, or other change with nothing to decide. Pick the quick win from what remains, and record one sentence on why it won.

If nothing remains, or every survivor is bigger than one grill, list number, title, and why it is out. Claim nothing. Stop.

Same session, already holding the claim on one pool issue with no Spec yet: that issue is the quick win. Do not pick another.

## 2. Claim

Claim it before any other write. Re-read the issue. If the assignee is not the current user, skip it and pick the next quick win.

Abandoning the run before step 5, with no feature pull request opened, releases the claim. A feature pull request already opened in this run stays; publish the Spec onto it. Do not open a second one.

## 3. Grill

Follow `grilling` and `domain-modeling` on the claimed issue (the pair `grill-with-docs` runs). Interview the maintainer. Glossary and ADR edits land in the current checkout as decisions crystallise. Do not implement the issue. Do not open a pull request during the grill.

The issue's category is `bug` or `enhancement` before you leave the grill. Keep an existing category label unless the grill changes it. With neither label, the grill settles one.

When the grilling frontier is empty, the user confirms shared understanding. That confirmation is the publish gate. Do not interview again. The Spec records the seams agreed in the grill.

## 4. Docs diff

A docs change is a create or edit, tracked or untracked, of a file named `GLOSSARY.md` or `GLOSSARY-MAP.md`, or of a file under `docs/adr/`. Compare those paths to `HEAD`. Any other dirty file is not a docs change.

### No docs change

Do not create a branch, worktree, commit, or pull request. `## Start from` is:

```markdown
## Start from

The default branch. The grill changed no glossary or ADR files.
```

Go to step 5.

### Docs change

This pull request is the one the feature or fix will be implemented on. Its only commit is the docs change.

`bug` selects `fix`. `enhancement` selects `feat`. The slug is a short hyphenated name taken from the issue title.

Follow `to-pr` for the worktree, the commit, the push, the draft, and green CI (`wait-for-ci`). Constrain that run:

- New worktree from the latest default tip. Branch `<fix-or-feat>/<number>-<slug>`.
- One commit. It contains only the glossary and ADR files from the grill.
- Commit message: `docs(<slug>): record <short name> decisions`. Imperative subject, 50 characters or fewer.
- Pull request title: `<fix-or-feat>(<slug>): <imperative user-facing outcome>`. Subject 50 characters or fewer. The title names the feature or the fix.
- Pull request body: a few sentences of the user-facing outcome, then `Closes #<number>`.
- Open as a draft. Wait until CI is green. Leave the draft in place. Do not mark it ready. Do not merge.

Bug #42, "Session expiry drops the refresh token":

- Branch `fix/42-session-expiry`
- Commit `docs(session-expiry): record session expiry decisions`
- Title `fix(session-expiry): keep refresh tokens across expiry`

After that commit is on the branch, clean the grilling checkout of those files only. Restore tracked glossary and ADR paths to `HEAD`. Delete untracked glossary and ADR files that now live on the branch. Leave every other dirty path alone.

`## Start from` is:

```markdown
## Start from

Branch `<branch>` (<pull-request-url>).

Push the implementation onto this branch and this pull request. Leave the pull request in draft until the feature is implemented.
```

A draft pull request for this issue already open in this run: use it. Do not open another.

## 5. Publish the Spec

Replace the issue body. Keep the title. Do not add a comment.

1. `## Start from`, from step 4.
2. The Spec, using the template in `to-spec`. Do not publish a second issue.
3. `## Original report`, then the previous body verbatim.

In that same edit: add `ready-for-agent`, remove `needs-triage` when it is present, add `bug` or `enhancement` when the issue has no category label, and release the claim.

Report the issue URL and, when a pull request exists, its URL.

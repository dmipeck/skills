---
name: commits-review
description: >-
  Review commit messages against the `conventional-commits` conventions and
  report the violations. Use when asked to review commits or check commit
  messages. NOT for: writing a commit — use `conventional-commits`; reviewing
  code — use `code-review`.
argument-hint: "[range]"
---

# Commits Review

Judge commit messages against the `conventional-commits` skill and report
every violation. Read-only: propose rewrites, never amend or rebase. Load the
`conventional-commits` skill first — it is the standard.

## 1. Pin the range

1. Argument given → that range (`main..HEAD`, `HEAD~5..HEAD`, a ref).
2. No argument, branch ahead of default → `git log <default>..HEAD` (the
   unpushed / PR commits).
3. No argument on default, or unsure → ask; defaulting, use the last commit.

Pull full messages: `git log --format='%H%n%s%n%b%n---' <range>`. Confirm the
range resolves and is non-empty.

## 2. Check each message against `conventional-commits`

Every subject must match `<type>(<scope>): <subject>`. Flag:

- **Format** — no `type:`, or a type outside `feat fix refactor build ci docs
  test style chore`; free-form (`Fix bug`, `Update docs`), ticket-only
  (`ABC-123`), or a sentence-case subject.
- **Type** — picked from the task, not the content; the user-impact test
  fails: `feat:`/`fix:` used for scaffolding, plumbing, unshipped groundwork,
  comment typos, dead code, or type-tightening never wrong at runtime. Name
  the correct type.
- **Subject** — not imperative, longer than 50 chars, trailing period, or
  describes the process (`wip`, `oops`, `fix tests`, `address review`).
- **Scope** — present but noise, or missing where it would add signal.
- **Breaking change** — a consumer-facing contract broke but there is no `!`
  after type/scope and no `BREAKING CHANGE:` footer.
- **Body / footer** — body restates the diff instead of the why; known issue
  references missing from the footer.

When a commit's diff is small, read it (`git show --stat <sha>`) to check the
type against the actual change; otherwise classify from the subject and mark
the finding a judgement call.

## 3. Report

Most severe, then most recent, one row per violating commit:

| sha | subject | rule | severity | suggested subject |
| --- | --- | --- | --- | --- |

- **severity** — `hard` for a format or type-set break (an invalid commit
  title); `judgement` for type classification and body/subject quality.
- **suggested subject** — a concrete rewrite, imperative, ≤50 chars, no
  trailing period.

End with a summary line: *N commits reviewed, M violating (X hard, Y
judgement)*. All clean → say so plainly.

Propose only. Never amend, reword, rebase, or push.

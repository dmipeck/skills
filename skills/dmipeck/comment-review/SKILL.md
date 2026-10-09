---
name: comment-review
description: >-
  Review comments against the `comments` conventions and report the
  violations. Use when asked to review comments, audit a diff for unnecessary
  comments, or check whether comments are necessary. NOT for: writing
  comments — use `comments`; a full code review — use `code-review`.
argument-hint: "[range|path]"
---

# Comment Review

Judge the comments in a change against the `comments` skill and report every
violation. Read-only: propose fixes, never edit. Load the `comments` skill
first — it is the standard.

## 1. Pin the scope

1. Argument given → a git range (`main...HEAD`), a ref (`HEAD~5`), or a
   path/glob (review those files as they are now).
2. No argument, worktree dirty → the uncommitted change (`git diff`,
   `git diff --staged`, plus untracked files).
3. No argument, worktree clean → `git diff <default>...HEAD`.

Resolve the ref and confirm the scope is non-empty before judging. Quote the
scope in the report.

## 2. Collect every comment in scope

Read each changed hunk and list every comment: line, block, and doc comments,
section banners, and disabled code. Match the comment forms of the language
(`//`, `#`, `/* */`, `--`, `<!-- -->`). Read wide enough to see the commented
symbol — function/method, type, field, constant — so you know whether it is
public surface or internal guts.

## 3. Judge each comment against `comments`

**Violation** when the comment:

- restates what the code does — narrating the next line or an obvious
  operation (`increment i`, `loop over items`, `set the value`);
- narrates a private/internal symbol — a what-comment on a private function,
  field, or local (only a *why* belongs there);
- is a section banner (`// ---- helpers ----`);
- is a commented-out corpse — disabled code; git remembers, delete it;
- is a TODO/FIXME with no reason — allowed only with a *why*.

**Keep** when it:

- is a doc comment on the public surface — exported function/method, public
  type, package/module doc, public constant;
- explains *why* an unusual choice was made — workaround, ordering, perf
  trick, external constraint.

Restating comment → delete it. If the code truly needs the comment to be
understood, the finding is *the code is unclear*: recommend a reshape, not a
better comment. A repo's own comment rule (e.g. a `comment-sicko`-style
`.mdc`) may be stricter; the stricter rule wins.

## 4. Report

Worst first, one row per violation:

| file:line | comment | rule | severity | fix |
| --- | --- | --- | --- | --- |

- **severity** — `hard` for a pure what-comment/narration on internal code or
  dead code; `judgement` for a borderline doc comment, or a why-comment that
  does not earn its keep.
- **fix** — the exact action: delete, or a rewritten *why*-comment.

End with a summary line: *N comments reviewed, M violations (X hard, Y
judgement)*. No violations → say so plainly; a clean scope needs no edit.

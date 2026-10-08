---
name: conventional-commits
description: >-
  Write conventional commit messages and pick the right type. Use any time
  you commit to git.
---

# Conventional Commits

Format `<type>(<scope>): <subject>`, optional body + footer. Commit-msg hook
enforces it, so every commit must conform. Type + scope keep history
skimmable for humans and machines — `git log`, changelogs, blame.

## Feat, fix, and breaking changes

Classify by how the change impacts the user once shipped:

- `feat:` new or changed capability the user can notice or benefit from.
- `fix:` corrects broken behavior the user could hit — wrong output,
  crash, regression.
- Breaking: the user must change how they use the product (API, CLI,
  config, contract). Mark with `BREAKING CHANGE:` footer or `!` after
  type/scope (`feat!: ...`).

Scaffolding, plumbing, unshipped groundwork, comment typos, dead code, and
types never wrong at runtime are not feat/fix/breaking — pick another type.

### Who is the user?

The user is whoever consumes the change after it ships: end users of the
product, API/CLI callers, or developers depending on a library this repo
publishes. If only maintainers of this codebase feel the change, it is not
feat/fix/breaking.

Do **not** infer whether deploy/gitops/ops config has external consumers —
that is not reliable from the repo alone. When a change touches those
surfaces and feat/fix/breaking vs maintainer work depends on that
distinction: if `AGENTS.md` has no clear answer under
`Commit users (conventional commits)`, ask the user whether anyone
outside this repo consumes that surface, add their answer to `AGENTS.md`
using the template in `agents-user-surface.md` (this skill directory),
then classify the commit.

## Types

Pick the type from actual content, not the overall task:

- `feat:` / `fix:` — see above (user impact).
- `refactor:` internal restructuring, no behavior change.
- `build:` build system, deps, tooling. `ci:` CI config.
- `docs:` documentation. `test:` tests. `style:` formatting only.
- `chore:` deprecated catch-all; only when nothing else fits.

## Scope

Optional, use when it adds signal: `feat(auth): ...`. Name the component or
package touched; skip when the change is one obvious area.

## Subject + body

Imperative, ≤50 chars, no trailing period. Describe the change, not the
process. Body explains why, not what — the diff already shows what; note
tradeoffs, context. Reference issues in footer (`Closes #123`).

## Bad message?

Never push a second "oops" commit. Amend or rebase before merge so history
reads as written right the first time.

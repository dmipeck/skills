# AGENTS.md

This repository is the **skills repo**: the canonical Cursor Authoring Format
source for `dmipeck` machines.

## Purpose

Own and evolve portable agent tooling as files in this tree:

| Path | Role |
| --- | --- |
| `skills/dmipeck/<id>/SKILL.md` | First-party Cursor-pure skills (folder name = skill id) |
| `skills/<owner>/<id>/SKILL.md` | Third-party skills, namespaced by owner |
| `agents/<id>.md` | Flat subagents / agents |
| `rules/*.mdc` | Always-on and scoped Cursor rules |
| `mcp.json` | MCP server definitions (Cursor-shaped) |

home-manager symlinks this checkout into `~/.cursor/{skills,agents,rules}` and
`~/.cursor/mcp.json`. Edit and commit here; content changes do not require
`home-manager switch`. Secrets and per-host URLs stay in the environment,
referenced from `mcp.json` via `${env:…}`.

## Working in this repo

- Prefer Authoring Format conventions: Cursor-pure skills; agents nest
  portability under `metadata.opencode` / `metadata.claude` only.
- Install third-party skills **only** with `npx skills` (never hand-copy or
  invent vendor trees). Keep them under a namespaced dir, e.g.
  `skills/mattpocock/grilling/SKILL.md` — not `skills/grilling/`.
- Example:

  ```bash
  npx skills add <owner/repo> -g -a cursor --copy
  ```

  Then place/commit the result as `skills/<owner>/<skill-id>/`.
- Keep changes scoped to the skill, agent, rule, or MCP entry you are changing.
- See `README.md` for deploy/symlink layout.

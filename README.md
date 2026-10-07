# skills

Canonical Cursor Authoring Format for `dmipeck` machines: `skills/`, `agents/`,
`rules/`, and `mcp.json`.

home-manager clones this repo to `~/d/github.com/dmipeck/skills` (if missing)
and creates targeted symlinks:

- `~/.cursor/skills` → `$checkout/skills`
- `~/.cursor/agents` → `$checkout/agents`
- `~/.cursor/rules` → `$checkout/rules`
- `~/.cursor/mcp.json` → `$checkout/mcp.json`

Edit files here and commit; no `home-manager switch` is required for content
changes. Secrets and per-host URLs stay in home-manager as process environment
(`systemd` user + login session) referenced via `${env:…}` in `mcp.json`.

## Third-party skills

```bash
npx skills add <owner/repo> -g -a cursor --copy
```

Commit the resulting trees under `skills/`.

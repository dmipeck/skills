# Merge Stack — reference

Host CLI, auth health, merge templates, deploy profile schema, and
pipeline cancel. Loop / roles live in [`SKILL.md`](SKILL.md); CI poll
semantics live in `wait-for-ci`.

## Auth health

At start of run, for the resolved host CLI only:

| Host | Check |
| --- | --- |
| GitHub | `gh auth status` |
| GitLab | `glab auth status` |
| Gitea | `tea login list` (or equivalent whoami) |

Done when: the check reports a valid session for that host.

On **401** / auth failure / invalid token: **stop**. Ask the human to
re-auth (`gh auth login`, `glab auth login`, `tea login add`). Do not
retry-spin. Keep hostnames generic in prompts — never paste private
instance identity from env into repo files.

## Host merge CLI

Parent merges only. Pin the exact head SHA at merge time. Prefer
fast-forward (or rebase on GitHub); squash only when the PR/MR is
marked for squash on the host. Never use a merge-commit method.

### GitHub (`gh`)

```bash
# Fast-forward-shaped (rebase onto base) — default when not squash-marked
gh pr merge <id> --rebase --match-head-commit <sha>

# Squash when the PR is squash-marked
gh pr merge <id> --squash --match-head-commit <sha>
```

Never pass `--merge` (merge commit).

### GitLab (`glab`)

Project `merge_method` is `ff` (see `scaffold-gitlab`). Default merge
honours that; pass `-s` only when the MR is squash-marked.

```bash
# FF — project merge_method=ff
glab mr merge <id> --sha <sha> -y

# Squash when the MR is squash-marked
glab mr merge <id> -s --sha <sha> -y
```

### Gitea (`tea` / API)

Repo allows fast-forward-only and squash only (see `scaffold-gitea`).
Merge via API; pin head with `head_commit_id`.

```bash
# Fast-forward-only
tea api -X POST "/repos/<owner>/<repo>/pulls/<id>/merge" \
  -f do=fast-forward-only \
  -f head_commit_id=<sha>

# Squash when the PR is squash-marked
tea api -X POST "/repos/<owner>/<repo>/pulls/<id>/merge" \
  -f do=squash \
  -f head_commit_id=<sha>
```

Never `do=merge` / `do=rebase-merge` (merge commit). Pass `--login
<name>` on every `tea` call when the instance is not the default login.

## Deploy profile schema

Anonymous Kargo + Argo CD shape. Placeholders only — no real org,
project, app, hostname, or URL identity in examples or profiles stored
in-repo.

| Field | Shape |
| --- | --- |
| `project` | `<project>` |
| `stages` | `[<stage>, …]` — ordered promotion path |
| `apps` | `[<app>, …]` — Argo CD applications under those stages |
| health | each listed app **Synced** + **Healthy** on freight whose git artifact contains the **merged SHA** |

**`none`** — skip the deploy bar entirely (merge gate is **Ready**
alone after the first item).

### Wait outline

After merge, for profile ≠ `none`:

1. Resolve freight / promotion for `<project>` that carries the merged
   SHA through each `<stage>` in order.
2. For every `<app>`: wait until Argo reports **Synced** and
   **Healthy** against that freight.
3. If status is stale, refresh the app (or equivalent sync/refresh) —
   generic refresh only; do not hard-code warehouse or cluster names.

Done when: every `<app>` on the required `<stage>`s is Synced + Healthy
for freight containing the merged SHA — or profile is `none`.

## Pipeline cancel

When advancing after a merge, cancel CI / waits only for **later**
**merge order** items (index `> i`). Keep:

- the **current** item's deploy wait
- the **next** item's PR agent (and its CI)

| Host | Cancel later-item CI |
| --- | --- |
| GitHub | `gh run cancel <run-id>` for runs on later PR heads |
| GitLab | `glab ci cancel pipeline <id>` for later MR pipelines |
| Gitea | cancel via `tea` / Actions API for later PR runs |

Do not cancel the in-flight deploy wait or the next item's babysit /
`wait-for-ci` work.

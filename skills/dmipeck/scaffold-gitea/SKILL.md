---
name: scaffold-gitea
description: >-
  Configure a new Gitea repository with a minimal feature set and no merge
  commits.
---

Configure a **new** Gitea repository after creation (or while creating it).
Prefer the Gitea API through `tea api` — `tea` has no repo-create command, and
the Gitea MCP server exposes no repo-settings tools. Ask for owner/name/
visibility only when not already decided; otherwise proceed with the defaults
below.

Two tenets govern every setting: **minimal feature set**, and **never merge
commits**.

## Target shape

**Features on** (everything else off):

| UI | API field | Value |
|---|---|---|
| Repository | `has_code` | `true` |
| Issues | `has_issues` | `true` |
| Pull requests | `has_pull_requests` | `true` |
| Actions | `has_actions` | `true` |

**Features off** (set each to `false`):

`has_wiki`, `has_projects`, `has_releases`, `has_packages`.

`has_actions` only takes effect where Actions is enabled on the instance.

**Issue tracker** — enable native issue dependencies (`gitea-tracker` records
blocking edges as Gitea issue dependencies); leave time tracking off. Nested
object, so send it whole:

| UI | Field | Value |
|---|---|---|
| Enable dependencies for issues and pull requests | `enable_issue_dependencies` | `true` |
| Enable time tracking | `enable_time_tracker` | `false` |

**Merge settings — no merge commit can be produced:**

| UI | API field | Value |
|---|---|---|
| Allow merge commits | `allow_merge_commits` | `false` |
| Allow rebase merging (with merge commit) | `allow_rebase_explicit` | `false` |
| Allow rebase merging | `allow_rebase` | `false` |
| Allow manual merge | `allow_manual_merge` | `false` |
| Autodetect manual merge | `autodetect_manual_merge` | `false` |
| Allow fast-forward-only merging | `allow_fast_forward_only_merge` | `true` |
| Allow squash merging | `allow_squash_merge` | `true` |
| Default merge style | `default_merge_style` | `fast-forward-only` |
| Update pull request branch by merge | `allow_merge_update` | `false` |
| Update pull request branch by rebase | `allow_rebase_update` | `true` |
| Default update style | `default_update_style` | `rebase` |
| Delete branch after merge by default | `default_delete_branch_after_merge` | `true` |

Only fast-forward and squash remain — neither can write a merge commit. This
is the repository-side enforcement of the `no-merge-commits` rule.

**Merge gate:** protect the default branch with a required status check only
when CI is configured. CI means the repo has (or is about to gain) a
`.gitea/workflows/*.yml` or `.github/workflows/*.yml` workflow. No workflow
and none planned → skip this step.

## Steps

1. **Create the repository** if it does not exist:

```bash
OWNER='<owner>'
REPO='<name>'

tea api -X POST "/user/repos" -f name="${REPO}" -F private=true
# organization owner instead:
# tea api -X POST "/orgs/${OWNER}/repos" -f name="${REPO}" -F private=true
```

`-f` sends a string field, `-F` a typed one (bool/int/null/JSON) — booleans
need `-F`. Add `-F auto_init=true` to seed the default branch. Capture `id`
and `default_branch` from the response; `default_branch` defaults to `main`.
Pass `--login <name>` on every call when the instance is not `tea`'s default
login.

2. **Apply features + merge settings** with `PATCH /repos/{owner}/{repo}`.
   Nested settings (`internal_tracker`) go as one JSON object, not dotted:

```bash
tea api -X PATCH "/repos/${OWNER}/${REPO}" \
  -F has_code=true \
  -F has_issues=true \
  -F has_pull_requests=true \
  -F has_actions=true \
  -F has_wiki=false \
  -F has_projects=false \
  -F has_releases=false \
  -F has_packages=false \
  -F 'internal_tracker={"enable_issue_dependencies":true,"enable_time_tracker":false}' \
  -F allow_merge_commits=false \
  -F allow_rebase_explicit=false \
  -F allow_rebase=false \
  -F allow_manual_merge=false \
  -F autodetect_manual_merge=false \
  -F allow_fast_forward_only_merge=true \
  -F allow_squash_merge=true \
  -f default_merge_style=fast-forward-only \
  -F allow_merge_update=false \
  -F allow_rebase_update=true \
  -f default_update_style=rebase \
  -F default_delete_branch_after_merge=true
```

3. **Gate merges on CI** — only if CI is configured (see above). Required
   status contexts are the check names Gitea Actions reports, typically
   `<workflow name> / <job name>`; read them from the workflow file:

```bash
DEFAULT_BRANCH=$(tea api "/repos/${OWNER}/${REPO}" | jq -r .default_branch)

tea api -X POST "/repos/${OWNER}/${REPO}/branch_protections" \
  -f rule_name="${DEFAULT_BRANCH}" \
  -F enable_status_check=true \
  -F status_check_contexts='["<workflow> / <job>"]' \
  -F enable_push=true
```

`enable_push=false` instead forces every change through a pull request. If CI
lands later in the same session, run this update then.

4. **Verify** with a GET and confirm the readable fields match the target
   shape:

```bash
tea api "/repos/${OWNER}/${REPO}" | jq '{
  has_code, has_issues, has_pull_requests, has_actions,
  has_wiki, has_projects, has_releases, has_packages,
  allow_merge_commits, allow_rebase_explicit, allow_rebase,
  allow_fast_forward_only_merge, allow_squash_merge,
  default_merge_style, allow_merge_update, allow_rebase_update,
  default_update_style, internal_tracker
}'

tea api "/repos/${OWNER}/${REPO}/branch_protections" | jq '.[] | {
  rule_name, enable_status_check, status_check_contexts
}'
```

Report the repository URL and the settings applied, including whether the
status-check gate was enabled.

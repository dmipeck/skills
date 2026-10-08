## Commit users (conventional commits)

Who counts as a "user" when classifying `feat` / `fix` / breaking for this
repo. Maintainer-only churn is never feat/fix/breaking.

| Surface | External consumers? | Notes |
| --- | --- | --- |
| Product / UI end users | yes / no | |
| Public API or CLI | yes / no | |
| Published library / package | yes / no | |
| Operators (deploy, gitops, Helm, Terraform, ops config) | yes / no | |

When operators are **no**, rewriting this repo's own deploy/gitops is
maintainer work — not a breaking change. When **yes**, treat shared deploy
contracts as user-facing; breaking changes need `BREAKING CHANGE:` / `!`.

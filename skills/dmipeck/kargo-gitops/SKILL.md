---
name: kargo-gitops
description: >-
  Set up in-repo Kustomize, Argo CD, and Kargo: dir layout, a meta
  Application that manages an ApplicationSet, and promotions (automatic
  test and staging, manual prod). Use when adding argocd/ and config/ to
  an app, replacing a central kustomize repo, or wiring Kargo stages.
---

# Kargo GitOps

In-repo GitOps for an application. Workloads live under `config/`. Argo CD
and Kargo CRs live under `argocd/<app>/`. A **meta Application** in a hub
gitops repo syncs those CRs. The ApplicationSet then syncs **rendered**
manifests from `stage/<overlay>` branches that Kargo writes.

Canonical promotion: **automatic test and staging, manual prod**.

Copy YAML from [reference.md](reference.md). Replace `<app>`, `<repo>`,
`<image>`, and Argo CD cluster names.

## Dir layout

```
config/
  bases/
    default/                 # includes workload bases; namespace: <app>
    <workload>/              # Deployment, Service, … — image tag 0.0.0
  overlays/
    <app>-test/
    <app>-staging/
    <app>-production/        # namespace + images.newTag
argocd/
  <app>/
    kustomization.yaml       # kargo/, appproj.yaml, appset.yaml
    appproj.yaml
    appset.yaml
    kargo/
      kustomization.yaml
      namespace.yaml         # label kargo.akuity.io/project: "true"
      project.yaml           # Project + ProjectConfig
      warehouse.yaml
      promotiontask-update-images.yaml
      stage-test.yaml
      stage-staging.yaml
      stage-production.yaml
```

Rules:

1. One overlay per stage. Overlay sets `namespace` and `images:` (the pin
   Kargo rewrites). Bases use placeholder tag `0.0.0`.
2. Do not change live workload **selectors** when porting manifests.
3. `.kustomize-ci.yaml` lists overlay paths (and optionally `argocd/<app>`).
4. Omit a stage that has no cluster. Do not invent a fake environment.

## Meta Application

Hub repo (the cluster's app-of-apps tree, e.g. `*/kustomize`) holds a
plain Application. It is the only object that points at the **app** repo's
control-plane path. It does **not** sync workloads.

```
source:
  repoURL: <repo>
  targetRevision: main
  path: argocd/<app>
  kustomize: {}
destination:
  server: https://kubernetes.default.svc
  namespace: argocd
```

Automated prune + selfHeal. `project: default` (or whatever owns hub
apps). Register it in the hub `argocd/kustomization.yaml`.

That sync creates: AppProject, ApplicationSet, Kargo Project / Warehouse /
Stages / PromotionTask, and the app namespace (Kargo project label).

SCM ApplicationSets that match `*-kustomize` will **not** discover a
normal app repo. App repos need this static meta Application.

## ApplicationSet

Lives in namespace `<app>` (Applications-in-any-namespace). One list
element per stage. Each generated Application syncs a **rendered** tree:

```
source:
  repoURL: <repo>
  targetRevision: stage/{{bundleSlug}}
  path: "."
destination:
  namespace: "{{namespace}}"
  name: "{{destination}}"          # Argo CD cluster name as registered
```

`bundleSlug` = overlay dir name (`<app>-test`, …). Annotate

`kargo.akuity.io/authorized-stage: <app>:{{stage}}`

AppProject (namespace `argocd`): `sourceRepos: [<repo>]`, destinations
for every `{namespace, cluster}` pair, `sourceNamespaces: [<app>]`.

## Kargo promotions

```
Warehouse (git main + image tags ^sha-)
  │  auto
  ▼
test          overlay config/overlays/<app>-test
  │  auto     branch  stage/<app>-test
  ▼
staging       overlay config/overlays/<app>-staging
  │  manual   branch  stage/<app>-staging
  ▼
production    overlay config/overlays/<app>-production
              branch  stage/<app>-production
```

**ProjectConfig**

| Stage | `autoPromotionEnabled` | Freight source |
| --- | --- | --- |
| test | `true` | warehouse `direct: true` |
| staging | `true` | previous stage `test` |
| production | `false` | previous stage `staging` |

Warehouse subscriptions: git `NewestFromBranch` on `main`, plus one
`image` entry per promoted image (`NewestBuild`, `allowTagsRegexes: ["^sha-"]`).
Registry URL is the cluster pull URL (e.g. `cr.…`), not CI's push URL, if
those differ.

**Each Stage promotion** (same steps, different vars):

1. `git-clone` freight commit → `./src`; stage branch → `./out` (`create: true`)
2. `git-clear` `./out`
3. task `update-images` → `kustomize-set-image` on `./src/<overlayPath>`
4. `kustomize-build` that overlay → `./out`
5. `git-commit` / `git-push` the rendered YAML
6. `argocd-update` Application `<app>-<stage>` in namespace `<app>`

Shared PromotionTask `update-images` takes `vars.path`. Commit message:

`build: promote Freight ${{ ctx.targetFreight.name }} to <stage>`

Kargo and Argo need git credentials for `<repo>`. That is cluster config,
not files in the app repo.

## Cutover

Meta Application + ApplicationSet do nothing useful until the first
promote creates `stage/<app>-test` (auto) and so on.

Do **not** delete the old hub Application/ApplicationSet that still syncs
live workloads until:

1. Meta Application is healthy (Kargo CRs exist).
2. At least the first auto promote has created the stage branch the new
   ApplicationSet syncs.
3. The new Application owns the same resource names.

Deleting an ApplicationSet whose children have `prune: true` deletes
production. Preserve-or-disable prune on the old app first, or leave it
until the new app is syncing.

## Production-only

No test/staging cluster: one overlay, one Stage, warehouse `direct: true`,
`autoPromotionEnabled: false`. ApplicationSet has one list element.
Same dir layout; drop the extra overlay/stage files.

## Validate

```bash
kustomize build config/overlays/<app>-production
kustomize build argocd/<app>
```

Both must succeed before commit.

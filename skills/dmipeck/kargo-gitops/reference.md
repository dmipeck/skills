# Kargo GitOps YAML

Placeholders: `<app>`, `<repo>` (https Git URL), `<image>` (cluster pull
repo, no tag), `<cluster-test>`, `<cluster-staging>`, `<cluster-production>`
(Argo CD cluster names from `argocd cluster list`).

## Hub: meta Application

Path in the hub gitops repo: `argocd/<app>/application.yaml`. List that
dir from the hub `argocd/kustomization.yaml`.

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: <app>
  namespace: argocd
spec:
  project: default
  source:
    repoURL: <repo>
    targetRevision: main
    path: argocd/<app>
    kustomize: {}
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

```yaml
kind: Kustomization
resources:
  - application.yaml
```

## App repo: `argocd/<app>/kustomization.yaml`

```yaml
kind: Kustomization
resources:
  - kargo/
  - appproj.yaml
  - appset.yaml
```

## AppProject

```yaml
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: <app>
  namespace: argocd
spec:
  destinations:
    - namespace: <app>
      name: <cluster-test>
    - namespace: <app>
      name: <cluster-staging>
    - namespace: <app>
      name: <cluster-production>
  sourceNamespaces:
    - <app>
  sourceRepos:
    - <repo>
  clusterResourceWhitelist:
    - group: "*"
      kind: "*"
  namespaceResourceWhitelist:
    - group: "*"
      kind: "*"
```

## ApplicationSet

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: <app>
  namespace: <app>
spec:
  generators:
    - list:
        elements:
          - stage: test
            bundleSlug: <app>-test
            appName: <app>-test
            namespace: <app>
            destination: <cluster-test>
          - stage: staging
            bundleSlug: <app>-staging
            appName: <app>-staging
            namespace: <app>
            destination: <cluster-staging>
          - stage: production
            bundleSlug: <app>-production
            appName: <app>-production
            namespace: <app>
            destination: <cluster-production>
  template:
    metadata:
      name: "{{appName}}"
      namespace: <app>
      annotations:
        kargo.akuity.io/authorized-stage: <app>:{{stage}}
      labels:
        app.kubernetes.io/name: "{{appName}}"
        app.kubernetes.io/part-of: <app>
    spec:
      project: <app>
      source:
        repoURL: <repo>
        targetRevision: stage/{{bundleSlug}}
        path: "."
      destination:
        namespace: "{{namespace}}"
        name: "{{destination}}"
      syncPolicy:
        automated:
          enabled: true
          prune: true
          selfHeal: true
        syncOptions:
          - CreateNamespace=true
          - ServerSideApply=true
```

## Kargo

### `kargo/kustomization.yaml`

```yaml
kind: Kustomization
resources:
  - namespace.yaml
  - project.yaml
  - warehouse.yaml
  - promotiontask-update-images.yaml
  - stage-test.yaml
  - stage-staging.yaml
  - stage-production.yaml
```

### Namespace

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: <app>
  labels:
    kargo.akuity.io/project: "true"
```

### Project + ProjectConfig

```yaml
apiVersion: kargo.akuity.io/v1alpha1
kind: Project
metadata:
  name: <app>
---
apiVersion: kargo.akuity.io/v1alpha1
kind: ProjectConfig
metadata:
  name: <app>
  namespace: <app>
spec:
  promotionPolicies:
    - stage: test
      autoPromotionEnabled: true
    - stage: staging
      autoPromotionEnabled: true
    - stage: production
      autoPromotionEnabled: false
```

### Warehouse

```yaml
apiVersion: kargo.akuity.io/v1alpha1
kind: Warehouse
metadata:
  name: <app>
  namespace: <app>
spec:
  interval: 5m
  freightCreationPolicy: Automatic
  subscriptions:
    - git:
        repoURL: <repo>
        commitSelectionStrategy: NewestFromBranch
        branch: main
    - image:
        repoURL: <image>
        imageSelectionStrategy: NewestBuild
        allowTagsRegexes:
          - "^sha-"
```

Add one `image:` subscription per promoted image.

### PromotionTask

```yaml
apiVersion: kargo.akuity.io/v1alpha1
kind: PromotionTask
metadata:
  name: update-images
  namespace: <app>
spec:
  vars:
    - name: path
  steps:
    - uses: kustomize-set-image
      as: set-images
      config:
        path: ${{ vars.path }}
    - uses: compose-output
      as: results
      config:
        setImagesCommitMessage: ${{ task.outputs['set-images'].commitMessage }}
```

### Stages

`stage-test.yaml`: `direct: true`, `bundleBranch: stage/<app>-test`,
`overlayPath: config/overlays/<app>-test`, argocd app `<app>-test`.

`stage-staging.yaml`: freight `stages: [test]`, branch/overlay/app
`*-staging`.

`stage-production.yaml`: freight `stages: [staging]`, branch/overlay/app
`*-production`.

```yaml
apiVersion: kargo.akuity.io/v1alpha1
kind: Stage
metadata:
  name: test
  namespace: <app>
spec:
  requestedFreight:
    - origin:
        kind: Warehouse
        name: <app>
      sources:
        direct: true
  promotionTemplate:
    spec:
      vars:
        - name: appRepo
          value: <repo>
        - name: bundleBranch
          value: stage/<app>-test
        - name: overlayPath
          value: config/overlays/<app>-test
      steps:
        - uses: git-clone
          config:
            repoURL: ${{ vars.appRepo }}
            checkout:
              - commit: ${{ commitFrom(vars.appRepo).ID }}
                path: ./src
              - branch: ${{ vars.bundleBranch }}
                create: true
                path: ./out
        - uses: git-clear
          config:
            path: ./out
        - task:
            name: update-images
          as: update-images
          vars:
            - name: path
              value: ./src/${{ vars.overlayPath }}
        - uses: kustomize-build
          config:
            path: ./src/${{ vars.overlayPath }}
            outPath: ./out
        - uses: git-commit
          as: commit
          config:
            path: ./out
            message: |
              build: promote Freight ${{ ctx.targetFreight.name }} to test

              ${{ outputs['update-images'].setImagesCommitMessage }}
        - uses: git-push
          config:
            path: ./out
        - uses: argocd-update
          config:
            apps:
              - name: <app>-test
                namespace: <app>
```

Staging/production: same template. Change `metadata.name`, freight
`sources.stages`, `bundleBranch`, `overlayPath`, commit "to …", and
`argocd-update` app name. Staging freight:

```yaml
sources:
  stages:
    - test
```

Production freight `stages: [staging]`.

## Overlay

```yaml
kind: Kustomization
namespace: <app>
images:
  - name: <image>
    newTag: 0.0.0
resources:
  - ../../bases/default/
```

Kargo overwrites `newTag` on promote. Seed `newTag` with the tag currently
running in that environment.

## CI config

```yaml
# .kustomize-ci.yaml
paths:
  - config/overlays/<app>-test
  - config/overlays/<app>-staging
  - config/overlays/<app>-production
```

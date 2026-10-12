---
name: merge-stack
description: >-
  Merge an ordered stack of PRs with optional deploy gates
disable-model-invocation: true
argument-hint: "<merge_order> [deploy-profile|none]"
---

# Merge Stack

**merge-stack** runs a serial **merge gate** over an ordered PR stack:
rebase early, merge only when **Ready** and the prior **deploy bar** is
green, then wait that item's deploy before the next merge. Distinct from
`babysit-pr`: that skill keeps **one** PR mergeable and stops before
merge; **merge-stack** merges many, in order, with optional deploy waits.

## Roles

| Role | Model | Owns |
| --- | --- | --- |
| **Parent** (you) | inherit | Parse **merge order**, spawn agents, **merge gate** only |
| **PR agent** | cheap for wait/rebase; inherit for CI fixes | `babysit-pr` → **Ready**; parent alone merges |
| **Deploy agent** | cheap | Wait the **deploy profile** (or skip when `none`) |

Spawn **PR agent** and **deploy agent** as separate subagents every time
(`thrifty`). Parent keeps inherit and stays on order / spawn / **merge
gate**.

## 1. Inputs

1. Resolve host CLI once: GitHub → `gh`; GitLab → `glab`; Gitea → `tea`
   (auth/health → [`reference.md`](reference.md)).
2. Build a structured **merge order**: ordered list of PR/MR ids in one
   repo on one host. Prose in → normalize to that list and **confirm
   once** with the user; then lock it for the run.
3. Resolve **deploy profile** (named profile or `none`). Schema and
   Kargo+Argo wait shape → [`reference.md`](reference.md). Placeholders
   only in examples — no real org, project, app, or hostname identity.

Done when: host CLI chosen; **merge order** is a confirmed ordered id
list for one repo/host; **deploy profile** is a name or `none`.

## 2. Spawn the stack

For every item in **merge order**, spawn a **PR agent** that follows
`babysit-pr` until **Ready** (or **Blocked**). When **deploy profile**
is not `none`, keep one **deploy agent** ready to wait after each merge.

**Ready** means all of:

- [ ] Rebased on current merge base (default, or stack parent while
      stacked — see §4)
- [ ] CI green (`wait-for-ci`)
- [ ] Undrafted
- [ ] Host reports mergeable

Done when: every item has a live **PR agent** (or already **Ready**);
**deploy agent** exists iff profile ≠ `none`.

## 3. Loop — rebase early, merge late

Walk **merge order** in index order. For item _i_:

1. **Rebase ASAP** after item _i−1_ merges (first item: rebase on
   default) — rebase _i_ as soon as _i−1_ lands, before _i−1_ deploy
   finishes.
2. Hold the **merge gate** until **Ready** **and**:
   - first item, or **deploy profile** is `none` → **Ready** alone
   - else → prior item's **deploy bar** green
3. **Merge gate** (parent only):
   - Prefer fast-forward; use squash only when the PR/MR is marked for
     squash on the host.
   - Pass the exact head SHA at merge time.
   - Allowed methods: FF or squash-if-marked only. Host merge-commit as
     the sole option → **Blocked**; stop that item.
4. After merge: if profile ≠ `none`, **deploy agent** waits this item's
   **deploy bar**. Cancel only **later** **merge order** pipelines /
   waits; keep the current deploy wait and the next item's **PR agent**.
5. Advance to _i+1_ (rebase it now; merge still waits this deploy when
   profile ≠ `none`).

Done when each step's checks hold before the next: rebase complete →
**merge gate** satisfied → merge recorded at that SHA → deploy wait
started or skipped per profile.

## 4. Stacked targets

While item _i_ targets another open stack PR (not default):

- Keep that stack parent until the **previous** **merge order** item
  has landed, then retarget _i_ to default.
- If the current target is neither default nor the previous **merge
  order** item → retarget to default immediately.
- After retarget / rebase: verify the item's commits are still present
  on the branch (missing commits → **Blocked**).

Done when: target is default or the live previous stack parent; commits
of the PR are on the branch tip history.

## 5. Done

Stop when the **last** **merge order** item is merged and:

- **deploy profile** ≠ `none` → its **deploy bar** is green
- **deploy profile** is `none` → last merge alone

Report: each id → merged SHA / **Blocked** reason; final deploy status
when applicable.

## Guardrails

- Parent owns order, spawn, and **merge gate** only — PR work and deploy
  waits stay in their agents.
- One repo and one host per run; one confirmed **merge order**.
- Merge with FF or host-marked squash at a pinned head SHA.
- Rebase the next item as soon as the prior merges; gate the next merge
  on the prior **deploy bar** (unless `none` / first item).
- Cancel only work for items after the current index in **merge order**.
- Point host CLI, auth checks, and **deploy profile** schema at
  [`reference.md`](reference.md); keep identities anonymous in-repo.

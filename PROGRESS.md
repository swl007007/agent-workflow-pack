# Production Integration Progress

- Approved plan: `docs/superpowers/plans/2026-07-14-production-composition-release-fix.md`
- Branch: `fix/rc2-production-composition`
- Worktree: `/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Plan/.worktrees/agent-workflow-pack-rc2`
- Release status: blocked; no RC4 or final tag is authorized.
- Execution approval: subsequent implementation waves are pre-approved through the release gate; stop before tagging, pushing, or publishing.

## Completed

- Packaged production bundle prerequisites: commit `27c3ba9`.
- Atomic first-init Manifest/workspace/replay transaction: commit `1b4193b`.
- Packaged Trellis layout/discovery schemas and real scanner binding: commit `ed3dd3a`.
- Complete release authority preserved across Core Resolver: commit `85f5cb1`.
- Real packaged-bundle init composition and safe first overlay insertion: commit `c94fdda` plus the current production-init increment.
- Project launcher, runtime-control descriptor, and workflow lock committed under exact Reconciler control authority: commit `974d762`.
- Production sync reconstructs committed authority and returns strict no-op without mutation: commit `b387e1e`.
- Reserved launcher envelope is parsed and stripped before public argparse; unsafe/public mixing fails closed in the current increment.
- All lazy owner targets are now distinct importable functions; Runtime functions still require real state-loader/domain-service binding before closure.
- Verified launcher caller fields reach `ProductionCommand`; doctor now performs real read-only project authority reconstruction in the current increment.
- Production `workspace register` now verifies committed runtime authority and launcher caller context, loads the packaged Trellis layout, and commits the real workspace/replay pair for a fresh clone.
- Production heavy-task claim/release now load canonical integration state, verify project/caller authority, and call the real Task-state Service with generated transaction identities.
- Focused first-init/recovery verification: 29 tests passed; Ruff and `git diff --check` passed.
- Component-only release gates require absent production-integration evidence and therefore remain closed.

## In Progress

- Bind the remaining production command owners to reachable domain implementations.

## Remaining

- Protected launcher internal channel.
- All 17 production owner bindings backed by reachable domain implementations.
- Installed-wheel black-box acceptance and strict second-sync no-op.
- Full Ruff, mypy, pytest, wheel/sdist, and production-integration evidence verification.
- Publication is intentionally deferred until every item above passes.

## Resume

Add production task transition/recovery RED over canonical integration/journal state, then bind runtime-load/admission/archive before returning to workspace/lifecycle migration and recovery.

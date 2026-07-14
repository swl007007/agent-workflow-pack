# Production Integration Progress

- Approved plan: `docs/superpowers/plans/2026-07-14-production-composition-release-fix.md`
- Branch: `fix/rc2-production-composition`
- Worktree: `/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Plan/.worktrees/agent-workflow-pack-rc2`
- Release status: blocked; no RC4 or final tag is authorized.

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

Add representative initialized-project RED tests for doctor/routing/workspace/task/recovery/lifecycle. Extend `ProductionCommand` with verified caller context from the launcher envelope, then replace Runtime placeholder bodies with state loaders and domain-service requests. Missing authority must continue to fail closed.

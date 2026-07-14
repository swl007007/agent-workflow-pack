# Production Integration Progress

- Approved plan: `docs/superpowers/plans/2026-07-14-production-composition-release-fix.md`
- Branch: `fix/v0.1.4-reproducible-ci`
- Worktree: `/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Plan/agent-workflow-pack`
- Release status: `v0.1.0` through `v0.1.3` are preserved as failed publications; `v0.1.4` is being prepared after CI exposed non-reproducible container timestamps.
- Execution approval: continue through immutable publication and post-release acceptance.

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
- Production task transition/archive/recovery and existing-task runtime load now call the real domain services; the runtime inventory uses installed-package paths and a packaged runtime-entry registry.
- Public `task admit` now establishes project/caller authority and fails specifically at the absent platform-authenticated Decision/proof boundary instead of a fixed Runtime placeholder; it does not manufacture approval.
- Production `workspace migrate` now reconstructs source identity/contract/layout from canonical clone-local state, verifies an exact target-owned compatibility edge, scans source/target task state, and calls the real migration transaction.
- Production `recover --workspace-registration` now selects one exact journal and invokes the real registration recovery transaction after project/caller authority verification.
- Production `recover --workspace-migration` reconstructs the exact recorded layout/schema scanner context and resumes the real migration journal; a crash after local candidates is covered.
- Release publication now computes workflow-lock and artifact-bundle roots through the exact Core Resolver projections, closing a cross-layer authority mismatch that would have made a published init fail later runtime verification.
- Installed-console expectations now distinguish release-independent `test-routing` from unpublished release-dependent `doctor`/`sync`, which correctly fail at `AWP_RELEASE_MANIFEST_INVALID` with zero writes.
- Production `recover --transaction` now loads the exact lifecycle journal, verifies project/caller authority, reconstructs the packaged scanner contract, and resumes committed cleanup through the real Reconciler recovery path.
- Production `upgrade` now verifies the initialized project against the running immutable release and returns an exact same-release no-op; a distinct target is immutable-release verified before the command stops at the saved-plan approval boundary.
- A real built-and-installed wheel/sdist now passes the no-context-injection console chain `bootstrap → init --dry-run → init → doctor → test-routing → sync --dry-run → sync → sync` with HTTPS replaced only at the test transport boundary. It proves 17 owners, routing policy, user-file preservation, and strict repeated-sync no-op.
- `doctor --write-probe` now creates a durable ignored-local probe transaction before target mutation; normal completion records exact evidence, while `recover --probe` cleans only recorded byte-identical residue and explicitly resumes or rolls back under project locks.
- Final verification passed from the release-gate commit candidate: Ruff, `mypy src`, runtime vendor lock, generated notices, 686 pytest tests, rebuilt wheel/sdist inventory, production-integration prerequisite, and all 13 release gates.
- Reproducible candidate identities: artifact set `06a5254beecde1b716870cf7f1602e00c98ae76cc1d7bc6e4f81acab4add2722`; wheel `9e3d35ace68f58cf7dba5aafb764a9e9937cb3774ff8daafe90339c5419ab485`; sdist `2dac6da4ed72c8528ef18195cd87651407c9e4b9482e5bdd16667d9875484eec`.
- Focused first-init/recovery verification: 29 tests passed; Ruff and `git diff --check` passed.
- Focused release-authority and console verification: 9 tests passed; Ruff and mypy passed.
- Component-only release gates require absent production-integration evidence and therefore remain closed.

## In Progress

- Make cross-Python CI reproduce one artifact set, then freeze and dogfood `v0.1.4`.

## Remaining

- Obtain a green CI matrix for the deterministic gzip framing fix.
- Only after CI passes, create and publish `v0.1.4` and resume canonical dogfood.

## Resume

Resume from the reproducible-build CI fix; never move or replace earlier tags or assets.

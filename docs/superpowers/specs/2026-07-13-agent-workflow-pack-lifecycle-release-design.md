# Agent Workflow Pack Lifecycle, Packaging, and Release Design

**Status:** Approved
**Approval:** Covered by explicit user blanket approval on 2026-07-13 after successful self-review
**Dependencies:** All five preceding Agent Workflow Pack feature specs approved and interface-frozen
**Implementation gate:** No production implementation until the relevant per-feature implementation plan is separately approved

## 1. Scope and Integration Boundary

Task 6 composes the public CLI, structured output, release trust chain, distribution builds, compatibility/upgrade flow, licensing gates, and end-to-end acceptance. It consumes every frozen subsystem interface and may not redefine Resolver policy, provider security, Reconciler semantics, task commands, route calculation, adapter behavior, or domain error meaning.

Task 6 owns:

- command parsing and delegation to the owning feature callable;
- one CLI result/output envelope and domain-error presentation mapping;
- Release Identity, detached release manifest, immutable GitHub trust policy, compatibility-edge packaging, and release gates;
- wheel/sdist/Git-checkout equivalence and distribution_render_digest;
- supported upgrade/rollback orchestration and complete end-to-end closure.

A CLI command name does not transfer semantic ownership. Task commands remain Task 4; route and adapter semantics remain Task 5; provider execution remains Task 2; plan/apply/recovery semantics remain Task 3; schemas and pure policy remain Task 1.

Imported frozen interfaces:

| Interface | Producer C | Registry R | Digest |
|---|---|---|---|
| core.schema-catalog.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| core.profile-resolution.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| core.surface-impact.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| core.capability-manifest.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| core.route-contract.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| core.saved-plan.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| core.task-snapshot.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| core.task-evaluators.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| core.workspace-diagnostics.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| providers.execution.v1 | b19e57a0e4d6e5094b853d428909e4d10d2283de | ac370a18d24be0bc4d29f58d56642df392db15f3 | 8c3890facd3f57198a4427ef2497077b924b13c780b7ac9b14f5227106b21fdb |
| core.render-projection.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| renderer.reconcile.v1 | caa40221183cac41b381702d2669d4fcd5d5c5b4 | b28dcc9d95ad207bc3b9ec129014def322448422 | 6ee3510b029769d4fe8dbe2a508f48d871a2a444a63da6e322992bebe649f471 |
| runtime.task-state.v1 | 0bc82617df4ea6f09b59c827ab925faf36904b49 | f9a16a120a4c95bb0555a739d3f4ef89eca8938f | bca14e8b426f9253a5922572d2719ecb6a7faeb6ae29c1a59b8d156a842fd388 |
| route.adapters.v1 | 9148cc0620f7c58fbcf058d08f592e0b47ca00f8 | 5017dfd569f77531dc67f2dc044539ccb832e50b | 92b3af97e62fccc94ca4d85d589d86bf80c83a4529c458434180a09a0fe30919 |
| core.errors.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| providers.errors.v1 | b19e57a0e4d6e5094b853d428909e4d10d2283de | ac370a18d24be0bc4d29f58d56642df392db15f3 | 8c3890facd3f57198a4427ef2497077b924b13c780b7ac9b14f5227106b21fdb |
| renderer.errors.v1 | caa40221183cac41b381702d2669d4fcd5d5c5b4 | b28dcc9d95ad207bc3b9ec129014def322448422 | 6ee3510b029769d4fe8dbe2a508f48d871a2a444a63da6e322992bebe649f471 |
| runtime.errors.v1 | 0bc82617df4ea6f09b59c827ab925faf36904b49 | f9a16a120a4c95bb0555a739d3f4ef89eca8938f | bca14e8b426f9253a5922572d2719ecb6a7faeb6ae29c1a59b8d156a842fd388 |
| route.errors.v1 | 9148cc0620f7c58fbcf058d08f592e0b47ca00f8 | 5017dfd569f77531dc67f2dc044539ccb832e50b | 92b3af97e62fccc94ca4d85d589d86bf80c83a4529c458434180a09a0fe30919 |

## 2. Lifecycle CLI Command Matrix

The public entry point is agent-stack. Parsing validates one closed command branch before invoking an owner. Unknown flags, branch-crossing fields, repeated reserved caller fields, or arbitrary URLs/hashes are usage errors.

| Command | Mutation scope | Owning callable/contract | Admission summary |
|---|---|---|---|
| bootstrap | user cache only | Task 2 acquisition plus Task 6 release verification | verified release/lock authority; optional acceleration |
| init | project and initial local state | Tasks 1-3 | approved init plan, bootstrap locks, Manifest absent |
| sync | project when not no-op | Tasks 1 and 3 | installed release equality, workspace match, imported task gate |
| sync --repair | selected managed state | Tasks 1 and 3 | approved restorative impact, observed-state CAS |
| upgrade | project plus current-clone local migration | Tasks 1-4 plus Task 6 compatibility | exact directed edge, verified candidate, approved plan |
| doctor | none | all read-only diagnostics | always read-only; may report unhealthy state |
| doctor --write-probe | bounded probe paths/evidence | Task 3 probe protocol | explicit authorization and locks |
| test-routing | none | Tasks 1 and 5 | normalized signal/policy/adapter tests |
| recover | lifecycle/probe/registration/migration journal paths | Tasks 3 or 4 by journal type | exact matching journal and runtime allowlist |
| workspace register | fresh clone local pair | Task 4 | committed project, local pair absent |
| workspace migrate | ignored local state only | Task 4 | verified source-to-target edge and strict quiescence |
| route decide | none | Task 5 calculator | matching contract, no maintenance/unfinished task transaction |
| task runtime load | read-only bundle plus entry dispatch | Task 4 | existing integration/revision/phase/claim/surface authorization |
| task admit | integrated task transaction | Task 4 using Task 5 verification | fresh integrated Decision and direct-human proof |
| task claim | integration state | Task 4 | expected revision and claim preconditions |
| task transition | integration state | Task 4 | expected revision and closed transition |
| task release | integration state | Task 4 | exact current claim |
| task archive | task/integration/Trellis metadata transaction | Task 4 | completed, no claim, archive preconditions |
| task recover | recorded task transaction paths | Task 4 | exact transaction and explicit resume/rollback |

Planning and every --dry-run are zero-write. A true no-op sync returns success without locks or transaction. CLI composition never creates a second planner, scanner, route policy, ownership decision, task-state transition, or provider attempt state.

The default upgrade target is the immutable release of the exact running CLI. upgrade --to accepts only a target authorized by the current trust policy and a directed compatibility edge. A mismatched external CLI may enter upgrade only when its verified release is an authorized installed-to-running candidate; every other command requires committed runtime equality.

## 3. Structured Output, Errors, and Redaction

With --json, stdout contains exactly one object:

~~~json
{
  "schema_id": "agent-workflow.cli-result",
  "schema_version": 1,
  "command": "doctor",
  "status": "blocked",
  "exit_code": 21,
  "result": null,
  "workspace_diagnostic": {},
  "errors": [],
  "warnings": []
}
~~~

Progress, logs, and sanitized external diagnostics go to stderr. Tracebacks are absent unless explicit debug mode is requested, and remain on stderr. Human and JSON output are projections of the same typed diagnostic objects.

Exit categories are fixed:

| Exit | Category |
|---:|---|
| 0 | success or verified no-op |
| 2 | usage, schema, or input validation |
| 20 | ownership conflict or drift |
| 21 | recovery or workspace migration required |
| 22 | active-task, maintenance, approval, runtime, or task-state block |
| 23 | capability insufficient |
| 30 | supply-chain or runtime identity verification failure |
| 31 | external provider/initializer failure |
| 40 | stale/mismatched plan, Decision, snapshot, or CAS precondition |
| 70 | unexpected internal error |

Task 6 maps every imported error code to its frozen exit category and structured fields. It cannot collapse relationship invalid into missing, state blocker into command blocker, or transaction stale evidence into an ordinary active-task error.

All paths in output are repository-relative. Redaction removes URL userinfo, sensitive query parameters, credentials, tokens, cookies, authorization headers, proxy secrets, caller-context secrets, and bounded external stderr matches before object construction. Debug output does not disable redaction.

workspace_state and command_admission remain separate. Read-only doctor may be admitted while primary_state_blocker is non-null. A transaction-time task snapshot change always makes AWP_TASK_QUIESCENCE_CHANGED the command primary error; new findings are secondary.

## 4. Detached Release Manifest and Immutable GitHub Trust Policy

### 4.1 Non-self-referential Release Identity

All distributions compute:

~~~text
release_id = SHA256(JCS({
  repository_id,
  distribution_name,
  version
}))
~~~

repository_id is the normalized host/owner/repository fixed by trust policy. distribution_name is agent-workflow-pack, not wheel/sdist/Git form. Release Identity excludes source commit, bundle/container hashes, URLs, sizes, and manifest identity.

### 4.2 Detached manifest

release-manifest.json is canonical JSON outside wheel and sdist:

~~~json
{
  "schema_version": 1,
  "release_id": "64-lowercase-hex",
  "version": "0.1.1",
  "repository": {
    "host": "github.com",
    "owner": "pinned-owner",
    "name": "agent-workflow-pack",
    "tag": "v0.1.1",
    "immutable_release_required": true
  },
  "source_commit": "40-lowercase-hex",
  "bundles": {
    "trust_policy": "64-lowercase-hex",
    "workflow_lock": "64-lowercase-hex",
    "artifact": "64-lowercase-hex",
    "schema": "64-lowercase-hex",
    "migration": "64-lowercase-hex",
    "compatibility": "64-lowercase-hex",
    "launcher": "64-lowercase-hex"
  },
  "assets": {
    "wheel": {
      "name": "agent_workflow_pack-0.1.1-py3-none-any.whl",
      "url": "immutable-https-url",
      "size": 123456,
      "sha256": "64-lowercase-hex"
    },
    "sdist": {
      "name": "agent_workflow_pack-0.1.1.tar.gz",
      "url": "immutable-https-url",
      "size": 123456,
      "sha256": "64-lowercase-hex"
    }
  }
}
~~~

The manifest never contains its own digest. Distributions and compatibility bundles never contain their own container/bundle hash. The externally computed manifest digest is recorded by project/runtime state.

### 4.3 Trust policy and verification

github-immutable-release-v1 packages canonical policy bytes containing exact host, owner, repository, tag derivation, manifest asset name, HTTPS/API rules, redirect allowlist, repository immutable-release requirement, and policy ID/digest.

The current verified runtime derives every locator. Project files and journals cannot provide repository, URL, tag, manifest name, key, or trust override. Verification requires exact immutable release, manifest bytes/schema, repository/tag/version, Release Identity, source commit, asset name/URL/size/hash, and every bundle root.

Trust-root rotation is not an ordinary v0.1 upgrade. Candidate releases must retain the same policy ID and content digest. Repository transfer, host change, or future signing/attestation policy requires a separately approved transition anchored by the old trust root.

## 5. Wheel, sdist, and Git-Checkout Release Identity

Release build order is acyclic:

~~~text
fix repository/version Release Identity
  -> fix release-neutral trust/workflow/artifact/schema/migration/
     compatibility/launcher bundle roots
  -> build final wheel and sdist
  -> compute distribution hashes and sizes
  -> generate detached release-manifest.json
  -> publish assets and mark GitHub release immutable
  -> verify published bytes and immutability
~~~

The detached manifest is never rebuilt into a distribution. Compatibility edges may name logical Release Identities and target bundle roots, but not their own compatibility-bundle digest, their containing source commit, or target wheel URL/hash.

Wheel, sdist, and Git checkout expose the same packaged Release Identity, source-commit claim supplied by build metadata, workflow lock, schemas, compatibility metadata, runtime source, templates, profiles, catalogs, licenses, and notices. Release verification requires each distribution's packaged claims to agree with the same detached manifest.

Install/acceptance tests execute the built wheel and built sdist environment, not only a checkout. Source audit may inspect the source commit but cannot substitute for artifact execution.

The project launcher and canonical first-install command share Task 4's clean bootstrap contract. Before CLI startup, uv/uvx verifies the exact wheel-container SHA-256. After startup, the CLI verifies packaged identity and bundle claims against the detached manifest. It does not claim access to the original wheel container. Asset size is manifest/release-CI metadata; runtime byte identity is the exact immutable URL plus SHA-256.

## 6. Self-Contained Wheel and Python Version Contract

The wheel is a self-contained pure-Python runtime distribution:

- external runtime Requires-Dist is empty;
- every runtime dependency is first-party or vendored at a locked source/version/hash;
- build-system requirements remain build-time only;
- no command performs consumer-time dependency resolution or source build;
- wheel/sdist package-data enumeration includes every schema, profile, catalog, adapter contract, migration, launcher template, runtime entry, license, notice, and provenance record;
- wheel, sdist, and Git checkout enumerate equivalent logical runtime-visible units.

Supported Python is >=3.11,<3.15. CI and artifact acceptance run on Python 3.11, 3.12, 3.13, and 3.14. The project and first-install launchers require a compatible local Python and force --no-python-downloads. Missing Python fails before package execution.

The canonical first-install shell command is rendered only from a verified detached manifest and uses absolute verified uv and Python paths, env -i, cache-side HOME, fixed locale/timezone, --isolated, --no-config, --no-env-file, --no-index, --keyring-provider disabled, --no-sources, --no-build, --no-python-downloads, controlled cache, and the direct wheel URL with SHA-256 fragment.

No latest-version lookup, package index, global tool reuse, alternate URL, Python download, build dependency, or second runtime package is a fallback.

## 7. Directed Compatibility Edges and Candidate Runtime

A compatibility bundle contains closed directed edges. Forward upgrade is candidate-owned; supported rollback is current-runtime-owned. Reverse support requires a separate edge.

Each edge binds:

- from/to versions and target logical Release Identity;
- unchanged trust-policy digest;
- target workflow-lock, artifact, schema, migration, and launcher bundle digests;
- Manifest, workflow-lock, integration, task-transaction, workspace, replay, and outbox schema transitions;
- source/target local-state contract and Trellis-layout digests;
- exact migration IDs/digests.

It excludes target URL/hash/size, target source commit, its own compatibility-bundle digest, and any retained-runtime witness.

The current runtime verifies the target detached manifest and complete wheel bytes before parsing static target metadata. Candidate code executes only after Release Identity, source commit, bundle roots, and installed-to-candidate edge agree. A candidate journal cannot introduce another runtime.

Source-release relationship/discovery inspection treats a verified wheel only as a bounded data archive. It never imports or executes source code. Missing/unsupported/invalid evidence follows imported workspace diagnostic semantics.

v0.1 does not migrate or transparently resume non-archived tasks across local-contract changes. Every visible unfinished task transaction or non-archived task blocks workspace migration. Layout change may pass only when one-sided state is absent or canonical empty and no task/metadata state is stranded.

## 8. Upgrade, Supported Rollback, and Local-State Migration

### 8.1 Upgrade orchestration

~~~text
verified current release
  -> verify candidate detached manifest and wheel
  -> validate directed edge and candidate bundle roots
  -> Provider acquisition/verification
  -> candidate Resolver IR and CandidateImpact
  -> Renderer SavedPlan and supply-chain/routing/file diff
  -> imported task gate
  -> explicit plan approval
  -> Reconciler apply and local-state migration
  -> Manifest-last commit
~~~

upgrade without --to targets the exact running release. upgrade --to never means latest; it selects only a trust-policy-derived immutable release reachable by an exact edge.

The current clone's local contract must match the installed Manifest before project upgrade. Edge-bound workspace/replay/outbox migrations are exact Reconciler candidates applied before Manifest commit under Task 3 CAS. Other clones migrate later with Task 4 workspace migrate.

Immediately before Manifest commit, the shared scanner snapshot must still match the plan/journal. A change returns AWP_TASK_QUIESCENCE_CHANGED and preserves pre-commit recovery.

### 8.2 Supported rollback

Rollback is a new forward transaction from the currently installed release to an explicitly listed earlier target. The newer current runtime owns and executes the edge; older code is never run against newer project state. v0.1 supports only exact listed same-schema targets and has no generic transaction rewind or arbitrary history restore.

### 8.3 Recovery runtime

Every journal names committed or candidate Release Identity plus manifest digest and launcher contract only. The launcher starts its own exact wheel, then validates that reference. Pre-commit rollback restores launcher/descriptor/artifacts/local state under CAS. Manifest commit switches normal runtime authority; post-commit recovery performs cleanup only.

## 9. Distribution Render Digest and Reproducibility

distribution_render_digest is the deterministic Merkle root of:

- managed artifact repository-relative paths;
- exact rendered bytes and normalized modes;
- logical Release Identity;
- profile, workflow-lock, artifact-bundle, adapter, and renderer-derived content;
- detached-manifest-derived launcher/descriptor substitutions after the same verified manifest is supplied.

It excludes Manifest generation, project/workspace UUIDs, target-path identity, transaction/approval IDs, maintenance/probe evidence, journals, and ignored local state. Tests comparing a whole plan/tree inject a deterministic identity provider.

Wheel, sdist, and Git checkout must produce identical distribution_render_digest for the same verified manifest and profile. Release CI runs the comparison at least twice in independent clean roots.

Every materializing initializer runs at least twice with fixed locale, timezone, environment, umask/mode, ordering, inputs, command, adapter/renderer version, and no ambient clock/random/host/user/temp-path influence. Candidate content-root must equal the workflow-lock/artifact-bundle expectation. Mismatch is AWP_INITIALIZER_NONDETERMINISTIC and cannot become an upgrade diff.

Runtime-surface coverage is recomputed for each distribution and rendered tree. Every runtime-visible unit has one owner and complete recipe inclusion; registry, inventory, recipe, graph, and control-plane changes produce normalized impact. Unclassified content blocks release.

## 10. Release Gates, Licensing, and Provenance

Release CI fails unless all gates pass:

1. umbrella/interface registry and all schema/digest DAG validators pass;
2. wheel and sdist build in the uv.lock-controlled build environment;
3. wheel metadata has empty external runtime Requires-Dist;
4. artifact installation and command smoke tests pass on Python 3.11-3.14;
5. package-data inventory and bundle digests are exact;
6. distribution_render_digest agrees across wheel/sdist/Git checkout and repeated runs;
7. launcher-bundle and plan/Manifest dependency graphs have no cycle;
8. detached manifest verifies published asset names, sizes, hashes, source commit, Release Identity, and bundle roots;
9. canonical first-install and project launcher isolation/cold-cache tests pass;
10. default-platform capability and adapter golden suites pass;
11. Resolver, Provider, Reconciler, Task-state, route, repair, crash, concurrency, migration, and E2E suites pass;
12. immutable GitHub release status is verified after publication;
13. license/provenance/notices are complete.

LICENSES/ contains full exact upstream license texts. Every upstream-derived or modified artifact records component, version/commit, source path, source hash, SPDX expression, modification flag, notice, and full-license reference. At the pinned v0.1 inputs, Superpowers and Spec Kit are MIT and Trellis is AGPL-3.0-only; automation revalidates actual locked metadata rather than trusting component names.

Vendored runtime code remains third-party content. THIRD_PARTY_NOTICES.md is generated from the lock/provenance graph and target-project notices cover content actually projected there. Missing, ambiguous, incompatible, or unreviewed license/provenance blocks release.

Publication order is build, verify, generate manifest, publish, mark immutable, re-fetch, re-hash, and verify. A failed post-publication check invalidates the release candidate; assets are never silently replaced under the same version.

## 11. End-to-End and Cross-Distribution Test Sequence

The release suite executes this minimum sequence from built artifacts:

~~~text
wheel, sdist, Git checkout:
  -> verify one Release Identity and bundle roots
  -> render same profile with same detached manifest
  -> compare distribution_render_digest
  -> enumerate complete runtime-surface coverage

clone A:
  -> canonical first install and init
  -> doctor, test-routing, true no-op sync
  -> route decide + direct-human task approval
  -> crash/recover admission before active commit
  -> runtime load without stale create Decision
  -> reject unpinned/drifted entry
  -> restorative repair to pinned/current digest and resume
  -> crash/recover lifecycle apply
  -> heavy completed task still blocks contract-changing upgrade
  -> crash/recover archive and reuse active ref with new task UUID
  -> candidate layout/current-target union gate
  -> upgrade with local-state migration crash/recovery
  -> external task evidence change before Manifest commit is stale-evidence error
  -> complete upgrade

clone B:
  -> pull committed target
  -> classify source/target relationship from static verified source metadata
  -> unfinished task journal and non-archived task block
  -> source-only archive/nonempty metadata and target-only task block
  -> restore source checkout, recover/complete/archive, then pull target
  -> workspace migration crash/recovery
  -> external task journal before workspace commit is stale-evidence error
  -> commit local contract and resume doctor/no-op sync

clone C:
  -> reverse-only edge reports ahead
  -> no direction reports diverged
  -> missing relationship metadata reports required
  -> invalid cryptographic/authenticated relationship evidence exits 30
  -> unsupported discovery does not erase verified relationship
  -> launcher, doctor, and migrate share workspace_state
  -> only read-only diagnostics remain admitted
~~~

Crash injection occurs immediately before/after every launcher, descriptor, Manifest, workspace, integration, metadata, ledger, receipt, attempt-journal, and outbox atomic replacement. Concurrency covers lifecycle writers, task admissions/claims, cache acquisition, provider attempts, and external file changes.

Cross-distribution command goldens compare JSON schema, error code, exit category, redaction, repository-relative paths, and deterministic result fields.

## 12. Acceptance-Criteria Closure

This table imports the frozen primary owner and adds Task 6's lifecycle/release closure scenario. Each AC appears exactly once.

| AC | Primary owner | Lifecycle/release closure and gate |
|---|---|---|
| AC-01 | Task 6 | published self-contained wheel installs and runs the complete CLI from immutable release |
| AC-02 | Task 5 | release blocks unless all three default-platform capability manifests satisfy sol56-sdd |
| AC-03 | Task 5 | adapter goldens prove projections add no route, owner, or capability |
| AC-04 | Task 3 | repeated sync from built artifacts is a byte/mode zero-write no-op |
| AC-05 | Task 3 | managed drift produces frozen ownership error and no overwrite |
| AC-06 | Task 3 | overlay-external edits survive render/reconcile golden tests |
| AC-07 | Task 3 | drift requires approved restorative repair with exact CAS |
| AC-08 | Task 3 | every pre-Manifest crash resumes or rolls back |
| AC-09 | Task 3 | every post-Manifest crash performs cleanup only |
| AC-10 | Task 3 | two writers and external edits obey OS lock plus file CAS |
| AC-11 | Task 4 | integration union/revision/claim semantics pass artifact E2E |
| AC-12 | Task 1 | heavy/Trellis-native impact gate property matrix passes |
| AC-13 | Task 1 | disabled/gated dependency and discoverability closure passes |
| AC-14 | Task 6 | wheel, sdist, and checkout produce identical scoped render digest |
| AC-15 | Task 2 | provider acquisition/isolation outputs feed only verified render candidates |
| AC-16 | Task 1 | every domain error has identical human/JSON category and redaction |
| AC-17 | Task 3 | legacy fixture preserves protected Trellis/Spec Kit state |
| AC-18 | Task 6 | wheel/sdist package data, vendored runtime, and locks are complete |
| AC-19 | Task 3 | byte/type/symlink/mode CAS faults are injected |
| AC-20 | Task 3 | failed live filesystem probe blocks every write |
| AC-21 | Task 4 | task/lifecycle lock ordering and concurrency suite passes |
| AC-22 | Task 5 | route owners and sole heavy orchestrator pass goldens |
| AC-23 | Task 4 | fresh clone registration pair commits/recoveries atomically |
| AC-24 | Task 4 | project launcher cold-cache/hash/version/offline cases pass |
| AC-25 | Task 4 | task-bound approval and admission crash recovery pass |
| AC-26 | Task 3 | doctor/dry-run zero writes and explicit probe recovery pass |
| AC-27 | Task 1 | completed stays gating and archived alone is non-gating |
| AC-28 | Task 2 | nondeterministic initializer blocks runtime and release |
| AC-29 | Task 6 | manifest/distribution/bundle graph contains no self-hash |
| AC-30 | Task 5 | all legal/illegal Decision branches and authenticity limits pass |
| AC-31 | Task 4 | admitting-to-active and archiving-to-archived commit points pass |
| AC-32 | Task 4 | verifier binding, TTL, replay, and ledger crash cases pass |
| AC-33 | Task 1 | Trellis metadata cross-ownership validation passes |
| AC-34 | Task 1 | saved-plan init/sync/repair/upgrade union property suite passes |
| AC-35 | Task 6 | release substitutions are excluded only from launcher bundle root |
| AC-36 | Task 4 | single launcher rename and mixed descriptor recovery pass |
| AC-37 | Task 3 | immutable journal binding remains valid across phase updates |
| AC-38 | Task 4 | every authorized local-state writer/migration crash point passes |
| AC-39 | Task 4 | absent-to-reserved-to-consumed rollback path is preserved |
| AC-40 | Task 2 | approved unchanged provider plan retries serialize and audit |
| AC-41 | Task 1 | plan-core/journal/Manifest/plan dependency DAG cycle suite passes |
| AC-42 | Task 4 | clone B pull and exact local migration path passes |
| AC-43 | Task 4 | clean uv stage and verified caller-context stage remain separate |
| AC-44 | Task 2 | provider attempt whole-file journal and recovery pass |
| AC-45 | Task 2 | provider exception requires direct-human verifier receipt |
| AC-46 | Task 4 | diagnostics state checkout-local task visibility limitation |
| AC-47 | Task 4 | old unfinished task journal requires source-authorized checkout |
| AC-48 | Task 4 | no retained runtime; all non-archived tasks block migration |
| AC-49 | Task 2 | broker handshake SIGKILL/EOF/deadline boundaries pass |
| AC-50 | Task 6 | uv verifies wheel container; CLI verifies packaged claims only |
| AC-51 | Task 1 | exact directed relationship classifications and errors pass |
| AC-52 | Task 4 | source/target layout union and stored source snapshot pass |
| AC-53 | Task 1 | bounded closed Trellis discovery and ambiguity suite passes |
| AC-54 | Task 4 | source-only/target-only state preservation gate passes |
| AC-55 | Task 1 | one scanner plus fixed-state/operation-gate separation passes |
| AC-56 | Task 4 | final rescan mismatch is unconditional stale-evidence primary |
| AC-57 | Task 1 | workspace state and command admission remain separate |
| AC-58 | Task 4 | UUID identity, ref reuse, archive destination, uniqueness pass |
| AC-59 | Task 5 | surface closure and affected/unaffected adapter/skill cases pass |
| AC-60 | Task 1 | invalid authenticated relationship evidence exits 30 |
| AC-61 | Task 4 | existing-task load uses integration/surfaces, not create Decision |
| AC-62 | Task 1 | every runtime-visible unit is covered and impact-normalized |
| AC-63 | Task 3 | restorative repair separates contract/observed/after digests |
| AC-64 | Task 1 | identical evidence yields command-independent task quiescence |

Task 6 is the primary owner only for AC-01, AC-14, AC-18, AC-29, AC-35, and AC-50. The table does not reassign any other criterion.

## 13. Production Implementation Entry Gate

Feature-spec decomposition is complete only when:

- all six specs are Approved and their producer C plus later registry R validate;
- all 22 expected interfaces and every required consumer import validate in complete mode;
- umbrella commit/content digest is unchanged and an ancestor of HEAD;
- AC-01 through AC-64 occur exactly once in the frozen ownership matrix and this closure table preserves every primary owner;
- no placeholder or production implementation file was introduced;
- Markdown/JSON/YAML and whitespace checks pass.

Implementation planning begins after this gate and produces one separate review-required plan per feature. No plan is auto-approved by the Task 2-6 blanket feature-spec approval. Production code begins only after the relevant implementation plan is separately approved and the current route/integration contract admits execution.

The following object is the complete approved Task 6 interface:

~~~json
{
  "interface_schema": "agent-workflow.feature-interface",
  "interface_version": 1,
  "producer_task": "task-6",
  "producer_feature": "lifecycle-packaging-and-release",
  "schema_versions": {
    "agent-workflow.release-identity": 1,
    "agent-workflow.release-manifest": 1,
    "agent-workflow.release-trust-policy": 1,
    "agent-workflow.release-compatibility": 1,
    "agent-workflow.release-gate-result": 1,
    "agent-workflow.cli-result": 1,
    "agent-workflow.cli-diagnostic": 1
  },
  "exports": [
    {
      "interface_id": "lifecycle.release.v1",
      "definition_owner": "task-6",
      "implementation_owner": "task-6",
      "schema_ids": [
        "agent-workflow.release-identity",
        "agent-workflow.release-manifest",
        "agent-workflow.release-trust-policy",
        "agent-workflow.release-compatibility",
        "agent-workflow.release-gate-result"
      ],
      "callables": [
        "verify_release_manifest(ReleaseLocator, PackagedTrustPolicy) -> VerifiedRelease | LifecycleFailure",
        "classify_compatibility(VerifiedRelease, VerifiedRelease, LocalStateContract) -> CompatibilityResult | LifecycleFailure",
        "compose_lifecycle_command(CommandInvocation, VerifiedRuntimeContext) -> CLIResult",
        "compute_distribution_render_digest(DistributionRenderProjection) -> Digest",
        "build_release_artifacts(ReleaseBuildInputs) -> ReleaseArtifactSet | LifecycleFailure",
        "run_release_gates(ReleaseArtifactSet, AcceptanceMatrix) -> ReleaseGateResult | LifecycleFailure"
      ],
      "consumers": []
    },
    {
      "interface_id": "lifecycle.cli-output.v1",
      "definition_owner": "task-6",
      "implementation_owner": "task-6",
      "schema_ids": ["agent-workflow.cli-result", "agent-workflow.cli-diagnostic"],
      "callables": [
        "render_cli_json(CLIResult) -> CanonicalJSONObject",
        "render_cli_human(CLIResult) -> HumanOutput"
      ],
      "consumers": []
    }
  ],
  "digest_domains": [
    "agent-workflow.release-identity.v1",
    "agent-workflow.release-manifest.v1",
    "agent-workflow.release-trust-policy.v1",
    "agent-workflow.release-compatibility.v1",
    "agent-workflow.distribution-render.v1",
    "agent-workflow.release-gate.v1",
    "agent-workflow.cli-result.v1"
  ],
  "digest_domain_owners": {
    "agent-workflow.release-identity.v1": "lifecycle.release.v1",
    "agent-workflow.release-manifest.v1": "lifecycle.release.v1",
    "agent-workflow.release-trust-policy.v1": "lifecycle.release.v1",
    "agent-workflow.release-compatibility.v1": "lifecycle.release.v1",
    "agent-workflow.distribution-render.v1": "lifecycle.release.v1",
    "agent-workflow.release-gate.v1": "lifecycle.release.v1",
    "agent-workflow.cli-result.v1": "lifecycle.cli-output.v1"
  },
  "error_namespace": "lifecycle.cli-output.v1"
}
~~~

This approval completes feature-spec decomposition only after the separate registry commit freezes the interface and the complete validator passes. It does not approve any implementation plan or production implementation.


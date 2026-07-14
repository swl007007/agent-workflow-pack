# Agent Workflow Pack Runtime Launcher and Task-State Service Design

**Status:** Approved
**Approval:** Covered by explicit user blanket approval on 2026-07-13 after successful self-review
**Dependencies:** Approved Core Resolver, Providers, and Renderer/Reconciler feature specs
**Implementation gate:** No implementation until the Runtime/Task-State implementation plan is separately approved

## 1. Scope and Authority Boundaries

Task 4 owns the managed project launcher protocol, post-wheel runtime verification, clone-local workspace registration and migration, the one normative Trellis task scanner, integrated-task state, approval replay, task outbox delivery state, task transactions, and existing-task runtime-load authorization.

It is not a daemon and holds no independent route, profile, artifact, release, or ownership policy. It does not calculate Route Decisions, verify platform-specific receipt authenticity, render project artifacts, execute provider initializers, compose the public lifecycle CLI, or redefine imported schemas and evaluators. Task 5 supplies route/adapter semantics and wrappers; Task 6 supplies release assets, trust-policy publication, and CLI composition.

Task-state Service is the ordinary sole writer of:

- locked active-or-archive task integration.yaml files;
- .agent-workflow/task-transactions/**;
- .agent-workflow/local/approval-replay.json after registration;
- .agent-workflow/local/task-outbox/**;
- exact Trellis metadata paths declared by the verified adapter for one task transaction.

First init, workspace registration, and compatibility-edge local-state migration retain only the additional local-state authority granted by the umbrella. No artifact definition or wrapper may acquire Task-state Service write authority.

Imported frozen interfaces:

| Interface | Producer C | Registry R | Digest |
|---|---|---|---|
| core.schema-catalog.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| core.profile-resolution.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| core.artifact-policy.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| core.surface-impact.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| core.route-contract.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| core.saved-plan.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| core.task-snapshot.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| core.task-evaluators.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| core.workspace-diagnostics.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| renderer.reconcile.v1 | caa40221183cac41b381702d2669d4fcd5d5c5b4 | b28dcc9d95ad207bc3b9ec129014def322448422 | 6ee3510b029769d4fe8dbe2a508f48d871a2a444a63da6e322992bebe649f471 |
| core.errors.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| renderer.errors.v1 | caa40221183cac41b381702d2669d4fcd5d5c5b4 | b28dcc9d95ad207bc3b9ec129014def322448422 | 6ee3510b029769d4fe8dbe2a508f48d871a2a444a63da6e322992bebe649f471 |

## 2. Single-File Launcher and Cold-Cache Bootstrap

### 2.1 Managed files and sole pre-wheel authority

The project control plane contains:

~~~text
.agent-workflow/bin/agent-stack       mode 0755
.agent-workflow/runtime-control.json  mode 0644
.agent-workflow/runtime/              non-discoverable catalog
~~~

.agent-workflow/bin/agent-stack is the only pre-wheel authority. It is a UTF-8 POSIX sh program replaced by one file-level atomic rename. Generated wrappers invoke this repository-relative path and never search PATH for agent-stack.

The launcher embeds only release-specific literal constants needed before Python starts:

- launcher contract and renderer version;
- Release Identity and detached release-manifest.json digest;
- exact immutable wheel URL and SHA-256;
- supported uv/uvx range and discovery rule;
- supported local Python range >=3.11,<3.15 and discovery rule;
- controlled cache and cache-side bootstrap-HOME derivation;
- complete environment and uv argument contract.

It does not parse JSON, read the descriptor as an authority, accept a caller URL/hash, or contain a detached-manifest trust-policy override. Release substitutions participate in the rendered launcher digest and applied file hash, but not in the release-neutral launcher-bundle digest.

### 2.2 Bootstrap prerequisites and uv invocation

v0.1 requires trusted local POSIX sh, POSIX env, one supported non-symlink absolute uv/uvx path, and one supported non-symlink absolute local Python. Missing compatible Python fails closed; Python download is forbidden.

The fixed invocation is equivalent to:

~~~text
env -i \
  PATH=<bootstrap-path> \
  HOME=<cache-side-bootstrap-home> \
  LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC \
  <absolute-uvx-path> \
  --isolated \
  --no-config \
  --no-env-file \
  --no-index \
  --keyring-provider disabled \
  --no-sources \
  --no-build \
  --no-python-downloads \
  --python <absolute-compatible-python-path> \
  --cache-dir <controlled-cache-root> \
  --from '<immutable-wheel-url>#sha256=<wheel-sha256>' \
  agent-stack \
    --bootstrap-project <repository-root> \
    --caller-context-version 1 \
    <validated-caller-context-fields> \
    <command...>
~~~

Argument order, environment keys, executable paths, version policies, URL, hash, and cache derivation are launcher-contract data. The launcher rejects inherited UV_*, virtual-environment, Python-selection, index, proxy-credential, .env, and platform variables rather than forwarding them.

--isolated prevents reuse of a globally installed same-name tool. --no-config, --no-env-file, --no-index, --no-sources, and --no-build prohibit local configuration and dependency/build resolution. A cache miss may fetch only the hash-bound direct wheel through allowlisted HTTPS redirects. Offline cache miss, hash mismatch, incompatible uv, or missing Python produces no project write and no secondary download.

uv/uvx verifies the wheel container hash before execution. The running CLI never claims to reopen, size, or hash the original wheel container.

### 2.3 Repository-root discovery

The launcher resolves its own path without following a repository-controlled symlink, requires the expected .agent-workflow/bin/agent-stack suffix, derives one normalized repository root, rejects path aliases/collisions, and passes that root through the reserved bootstrap channel. User arguments cannot set or repeat reserved --bootstrap-* or --caller-* fields.

## 3. Clean uv Environment and Verified Caller Context

Bootstrap isolation and application context are separate stages.

Before env -i, the launcher captures only schema-allowlisted, bounded, non-sensitive caller context:

~~~yaml
schema_id: agent-workflow.caller-context
schema_version: 1
platform: codex
user_home: /absolute/user/home
config_roots:
  codex_home: /absolute/config/root
harness:
  executable: /absolute/path/to/harness
  version_probe_id: codex-version-v1
tty:
  stdin: true
  stdout: true
  stderr: true
  direct_confirmation_capable: true
~~~

Allowed fields are limited to OS-account/config roots, selected platform ID, absolute harness executable and version-probe identity, project-external paths needed for read-only capability inspection, and TTY/confirmation facts. Paths are absolute, normalized, length bounded, duplicate free, control-character free, and permitted by the selected locked adapter schema.

Tokens, cookies, SSH/cloud credentials, proxy secrets, arbitrary environment snapshots, file contents, unbounded PATH, and caller-selected wheel inputs are forbidden. Platform variables may contribute only an explicitly allowlisted normalized path field.

The started CLI first verifies release, packaged identity, project Manifest, descriptor, transaction state, workspace relationship, and command eligibility. Only then may it validate the caller envelope, re-probe OS account, filesystem, harness path/version, and TTY facts, and construct a command-specific runtime context. It never restores the original environment wholesale or reads an external config path before authority checks.

## 4. Runtime Allowlist, Descriptor Validation, and Recovery Dispatch

### 4.1 Post-wheel verification order

Before any command dispatch, provider/network operation, or project write, the pinned CLI:

1. verifies its packaged Release Identity, distribution metadata, source commit, trust-policy identity, and bundle roots;
2. derives and verifies the immutable detached manifest using packaged canonical trust-policy bytes;
3. validates the committed Manifest, workflow lock, runtime-control descriptor, managed launcher record, and local workspace relationship;
4. validates every unfinished lifecycle, workspace, probe, or task journal relevant to command admission;
5. constructs the imported command-independent workspace_state and command-specific command_admission diagnostic;
6. admits only commands allowed by the resulting state and recovery runtime.

The descriptor is a managed post-wheel input. With no unfinished transaction, launcher, descriptor, Manifest, Release Identity, manifest digest, pack version, wheel identity, source commit, launcher contract, and bundle claims must agree. Descriptor mismatch cannot prevent the shell from starting the CLI, but blocks ordinary dispatch.

### 4.2 Runtime allowlist

A journal records only:

~~~yaml
recovery_runtime:
  runtime_role: committed
  release_id: 64-lowercase-hex
  release_manifest_digest: 64-lowercase-hex
  launcher_contract_version: 1
~~~

runtime_role is committed or candidate. URL, wheel hash, repository, tag, asset locator, and trust-policy override are forbidden.

Committed is valid only when it equals the committed Manifest. Candidate is valid only when it equals the approved candidate Manifest/plan, its detached manifest is already independently trusted, and the exact compatibility edge authorizes the transition. An old task journal visible after a pull does not become executable because its release appears in compatibility metadata; recovery requires restoring a checkout whose committed Manifest authorizes that runtime.

While any validated transaction is unfinished, only read-only diagnostics and its matching recovery entry are admitted. Mixed launcher/descriptor preimage and candidate states are accepted only when both complete file states occur in that journal. An unrecorded third state fails closed.

### 4.3 Maintenance coordination

The Reconciler owns .agent-workflow/maintenance.json and holds the exclusive runtime-state gate while it exists. Task 4 validates its transaction_id, journal_binding_digest, plan_digest, task_quiescence_digest, and candidate generation against the journal or committed Manifest.

Maintenance blocks Route Decision issuance, task admission/mutation/archive, runtime loading, and all write entries. Only read-only diagnostics and the matching lifecycle recovery are legal. Task commands never acquire the Reconciler lock.

## 5. Workspace Registration and Local-State Contracts

### 5.1 Workspace-local authority

.agent-workflow/local/workspace.json is ignored clone-local state with schema agent-workflow.workspace-local version 1. It binds:

- project lineage UUID and clone-local workspace UUID;
- locally applied release ID/version and detached-manifest digest;
- local-state contract digest;
- exact normalized Trellis task-layout snapshot and digest;
- independent workspace, approval-replay, and task-outbox schema versions.

It is never a pack-managed artifact and must be covered by the managed ignore marker. A tracked, malformed, copied/identity-mismatched, unsupported, or unpaired workspace object blocks writes.

### 5.2 workspace register

The typed operation is:

~~~text
register_workspace(
  project_root: VerifiedProjectRoot,
  manifest: VerifiedCommittedManifest,
  caller_context: VerifiedCallerContext
) -> WorkspaceRegistrationResult | RuntimeFailure
~~~

It is legal only for a fresh clone with a valid committed Manifest/launcher/descriptor and absent workspace.json and approval-replay.json. It acquires the out-of-tree bootstrap lock and then the project Reconciler lock, followed by the runtime-state gate. It refuses maintenance and unrelated unfinished transactions.

The registration journal records original absence, target-path identity, candidate workspace/replay bytes and modes, project/release/layout/contract identities, and recovery runtime before either local file is written.

Registration phases are:

~~~text
planned -> workspace_written -> registration_committed
        -> cleanup_pending -> complete
~~~

The workspace candidate is atomically renamed first. The canonical empty replay ledger is atomically renamed last; that second rename is the registration commit point. Before commit, recovery may remove only exact candidate bytes under original-absence CAS. After commit, both files must validate as one pair; recovery may only finish cleanup. Plain registration encountering a journal directs to recover --workspace-registration rather than starting again.

The operation does not change Manifest, workflow lock, managed artifacts, tasks, Trellis metadata, or existing outbox content. After registration, a missing/corrupt replay ledger is never treated as first use.

## 6. Workspace Migration and Quiescence Revalidation

### 6.1 Static source evidence and relationship

workspace migrate is the only ordinary write command admitted when a registered clone's source local contract differs from the committed target contract. It may first populate the controlled user cache with the exact immutable source detached manifest and source distribution identified by workspace.json. The current trust policy verifies all bytes; the source wheel is treated only as a data archive. Source code is never imported, built, or executed.

Relationship evidence and discovery evidence remain independent. Verified target-owned source-to-target edge yields migration-required; verified reverse-only yields ahead; verified neither direction yields diverged; missing relationship bytes remains unknown; cryptographic or authenticated schema failure is relationship_evidence invalid and AWP_SOURCE_RELEASE_VERIFICATION_FAILED exit 30. Unsupported source task parser affects discovery/quiescence, not a verified release relationship.

### 6.2 Normative scanner

Task 4 implements the imported callable exactly:

~~~text
scan_task_quiescence(
  source_layout: VerifiedTrellisTaskLayout,
  target_layout: VerifiedTrellisTaskLayout,
  source_schemas: VerifiedDiscoverySchemas,
  target_schemas: VerifiedDiscoverySchemas
) -> TaskSnapshotAndFindings
~~~

The scanner enumerates the bounded union of source/target active and archive roots, exact/bounded metadata contracts, and task-transaction roots. It applies the frozen segment/filename grammars, task-recognition rule, integration schemas, metadata parsers/classifiers, journal phase classifier, hard depth/count/byte limits, case/Unicode uniqueness, non-symlink/type rules, and source/target partition semantics.

It returns only the canonical imported snapshot and sorted findings. It never selects error codes or command blockers. Missing roots may be canonical empty only where the verified contract says so; unknown, unsupported, corrupt, oversized, aliased, wrong-type, or ambiguous state remains a finding and is never skipped or truncated.

Task identity is the canonical UUID in integration.admission.task_id, not a task ref. The snapshot records current path, admission-time ref, lifecycle state/revision, complete pinned surface set, recomputed task-contract digest, exact metadata evidence, and every task journal. Duplicate task IDs, integration/journal disagreement, and active/archive interpretation conflict are ambiguity.

Layout change performs no task-layout migration in v0.1. Every source task/archive/metadata object must remain recognized at the same path and semantic role by the target; one-sided state may pass only when absent or classifier-proven canonical empty. Source-only archived/nonempty metadata or target-only task state yields a stranded-state finding.

### 6.3 Fixed state and command admission

Launcher, doctor, and migration populate workspace_state.task_quiescence only through imported evaluate_workspace_state_quiescence. The requested command never enters that result. The imported evaluate_task_gate separately decides command admission from operation, normalized impact, full snapshot, and findings.

For workspace-migrate, any ambiguity, unfinished task transaction, non-archived task, or stranded state blocks. v0.1 has no retained runtime, resume witness, or task/layout mover. Diagnostics instruct recovery/completion/archive under the source-authorized checkout before retrying migration.

### 6.4 Migration transaction

The typed operation is:

~~~text
migrate_workspace(
  source_contract: VerifiedLocalStateContract,
  target_contract: VerifiedLocalStateContract,
  edge: VerifiedDirectedCompatibilityEdge,
  snapshot: TaskSnapshotAndFindings
) -> WorkspaceMigrationResult | RuntimeFailure
~~~

After read-only evidence collection, it acquires the project Reconciler lock and exclusive runtime-state gate, revalidates source/target authorities, rescans, calls both imported evaluators, and requires a null command blocker. It writes a journal under .agent-workflow/local/workspace-transactions/<transaction-id>.json before local mutation.

The immutable journal binds the complete snapshot/findings/digest, evaluator IDs/versions/results, exact workspace/replay/outbox preimages and candidates, migration identities, release identities, layout snapshots, and recovery runtime.

Migration phases are:

~~~text
planned -> local_candidates_applied -> workspace_committed
        -> cleanup_pending -> complete
~~~

Replay-ledger and existing outbox candidates apply first under whole-file/path CAS. workspace.json applies last and is the migration commit point. Immediately before that rename, the exact scanner reruns under both locks; any snapshot/digest change produces AWP_TASK_QUIESCENCE_CHANGED as unconditional command primary error and leaves current findings secondary.

Before commit, resume or exact CAS rollback is legal. After commit, only cleanup is legal. Migration never changes project-scoped authority, Trellis/task state, task journals, or Manifest, and never resets an invalid ledger/outbox to empty. The quiescence guarantee is checkout-local and makes no claim about unseen clones or branches.

## 7. Integration Schema and Immutable Task Identity

agent-workflow.integration version 1 is a closed union keyed by mode: trellis-native or speckit-superpowers. Common fields are:

~~~yaml
schema_version: 1
mode: trellis-native
workflow_contract:
  version: 1
  profile_digest_at_admission: 64-lowercase-hex
  lock_digest_at_admission: 64-lowercase-hex
  artifact_bundle_digest_at_admission: 64-lowercase-hex
  policy_digest_at_admission: 64-lowercase-hex
  adapter_id: codex
  adapter_version_at_admission: 1.0.0
  route_contract_version: 1
  task_contract_surfaces: []
lifecycle:
  status: active
  state_revision: 2
  admitted_at: UTC-RFC3339
  archived_at: null
  blocked_reason: null
  last_transition: {}
admission:
  operation: create-integrated-task
  task_id: canonical-uuid
  task_ref: .trellis/tasks/example
  intent_id: stable-intent-id
  intent_digest: 64-lowercase-hex
  task_transaction_id: canonical-uuid
  candidate_tree_digest: 64-lowercase-hex
  workspace_instance_id_at_admission: canonical-uuid
  route_decision_id: canonical-uuid
  route_decision_digest: 64-lowercase-hex
  approval_id: canonical-uuid
  approval_challenge: 256-bit-value
  approval_proof_digest: 64-lowercase-hex
  approval_verifier_id: stable-verifier-id
  approval_verifier_version: 1.0.0
  approved_by: stable-actor-id
  approval_mechanism: platform-user-confirmation
  approved_at: UTC-RFC3339
~~~

admission.task_id is immutable canonical identity. admission.task_ref is the immutable admission-time label; current scanner path is separate evidence. Admission rejects duplicate task IDs across active/archive integrations and unfinished journals. After a committed archive the active ref may be reused only by a new task ID. Archive destination is produced by the locked adapter's collision-free function over task ID plus admission ref.

workflow_contract.task_contract_surfaces is a closed sorted set derived by Task 5 and reverified at admission. It contains all transitive runtime dependencies plus mandatory runtime-control-plane and surface-registry. Its imported digest and the imported task_contract_digest formula are recomputed; caller-supplied derived digests are never trusted.

The trellis-native branch contains only its admission-time task ref. Trellis remains authority for native internal phases.

The speckit-superpowers branch contains the locked router-contract version, closed heavy phase, structured executor claim, active feature authority, canonical/reference artifact projections, and completion flags. Task 4 enforces the locked transition table but does not define heavy orchestration semantics.

Lifecycle status is exactly admitting, active, blocked, completed, archiving, or archived. Blocked requires a reason. Every status except archived remains gating. Admitting is never runnable; completed is not archived; resume never reclassifies mode.

## 8. Task Admission, Claim, Transition, Release, and Archive

### 8.1 Typed command boundary

| Command | Required authoritative inputs | Success authority |
|---|---|---|
| task admit | fresh create-integrated-task Decision, matching direct-human proof, intent, task ID/ref, verified surfaces, absent ref, unique ID | active integration revision 2 |
| task claim | task ID/ref, expected revision, heavy implementing phase, absent claim, actor/executor | next integration revision with claim |
| task transition | task ID/ref, expected revision, closed transition ID, required claim/completion preconditions | next integration revision |
| task release | task ID/ref, expected revision, exact claim ID/actor | next revision with null claim |
| task archive | completed lifecycle, expected revision, no claim, completion flags, locked archive adapter | archived integration at collision-free destination |
| task recover | exact transaction ID, resume/rollback choice, authorized recovery runtime | phase-appropriate recovered state |

Every mutation validates committed runtime/workspace equality, rejects maintenance and unrelated unfinished transactions, acquires the exclusive runtime-state gate, then acquires the task lock at .agent-workflow/local/task-locks/<normalized-task-path-digest>.lock. It rereads complete bytes/mode/type/non-symlink state and uses one whole-file atomic rename per integration revision. Revisions increase exactly once per committed mutation.

### 8.2 Admission transaction

task admit is the only integrated task-creation entry. It consumes only the create-integrated-task branch; classify-only and execute-light are invalid. The Decision remains provenance after commit.

While holding the exclusive gate, admission:

1. replays route policy and all Decision/proof/workspace/task-state/surface bindings;
2. proves task-ref absence and task-ID uniqueness across active, archive, and unfinished journals;
3. writes the planned task journal before replay reservation or staging;
4. reserves the approval proof for this transaction;
5. renders and validates the complete deterministic task shell plus admitting integration revision 1 in same-filesystem staging;
6. atomically moves the directory to the requested ref while it remains non-runnable;
7. applies the finite exact Trellis metadata candidate set under byte-and-mode CAS;
8. atomically replaces integration from admitting revision 1 to active revision 2.

The final integration rename is the admission commit point. Admission phases are:

~~~text
planned -> staged -> task_moved -> metadata_applied
        -> admission_committed -> cleanup_pending -> complete
~~~

Before commit, validated resume or rollback is legal. Rollback restores metadata before reversing a matching task move and permanently consumes the approval reservation. After commit, only outbox enqueue and cleanup are legal. If a crash leaves journal phase behind, recovery recognizes committed state only from exact active revision 2, tree identity, and metadata candidates.

Pre-commit operations are limited to journaled reversible file work. Direct Trellis create, hooks, notifications, subprocess callbacks, network actions, and Git auto-commit are disabled.

### 8.3 Ordinary mutation and claims

claim is heavy-only, legal only in the locked implementing phase with null claim, and records claim_id, executor, actor, claimed time, and base_revision. Two claimants observing one revision serialize; only the first can pass CAS. Claims do not expire automatically.

release requires the exact claim identity and current revision. A transition requiring an executor rejects absent/foreign claim. A transition out of implementation rejects an unresolved claim. Forced release is a distinct audited recovery action requiring user direction and evidence; it is not a TTL path.

Trellis-native lifecycle changes use only the common lifecycle transition table and never pretend to own Trellis's native internal phase.

### 8.4 Archive transaction

Archive requires completed lifecycle, no live claim, satisfied completion flags, expected revision, and an absent same-filesystem destination derived by the locked adapter from task ID and admission ref.

The service marks the active integration archiving, moves the task directory, applies all exact Trellis metadata/index/pointer candidates, then atomically changes the archive-location integration to archived, sets archived_at, and increments revision. That last integration rename is the archive commit point.

~~~text
planned -> state_marked -> task_moved -> metadata_applied
        -> archive_committed -> cleanup_pending -> complete
~~~

Before commit, recovery may resume or reverse the directory/metadata operations only under complete tree and per-path CAS. After commit, only outbox enqueue and cleanup are legal. A directory move alone never makes a task non-gating. Opaque Trellis archive commands and pre-commit side effects are forbidden.

## 9. Existing-Task Runtime Load Authorization and In-memory Dispatch

Task creation and existing-task execution use separate admission contracts. Runtime load never requires the stale create Decision or approval.

The public command `agent-stack task runtime load` is the sole existing-task entry and maps without additional fields to the following callable:

~~~text
load_task_runtime(
  task_ref: NormalizedCurrentTaskRef,
  task_id: CanonicalUUID,
  expected_state_revision: uint64,
  expected_lifecycle_status: ClosedLifecycleStatus,
  expected_phase: ClosedModePhaseOrNull,
  expected_claim: ClosedClaimExpectation,
  surface_id: StableSurfaceID,
  runtime_entry_id: StableRuntimeEntryID
) -> ImmutableDispatchBundle | RuntimeFailure
~~~

The request cannot contain arbitrary paths, caller digests, a Route Decision, approval proof, mode override, loader module, or reusable authorization token.

Under the runtime-state gate, the pinned CLI:

1. rejects maintenance, contract mismatch, unfinished task transaction, and admitting/archiving/archived state;
2. rereads integration with no-follow regular-file access and recomputes task identity, current ref, revision, phase, claim, task-contract digest, and surface set;
3. verifies the requested entry's closed allowed-mode/phase/claim predicate;
4. verifies the requested surface is the canonical owner of the entry and belongs to the pinned closure;
5. expands the verified acyclic transitive surface dependency graph, including runtime-control-plane and surface-registry;
6. no-follow reads every declared package resource and managed runtime unit, including bytes and normalized modes, into one immutable in-memory bundle;
7. recomputes each owning/dependency observed digest and current contract digest using the frozen recipe and requires observed == current contract == pinned;
8. rechecks state and byte identities before bundle completion, then dispatches only from that bundle.

The adapter/leaf runtime may not reopen .agent-workflow/runtime/** or another managed catalog path after authorization. The service returns no bearer token and caches no authority across calls. A concurrent state or byte change before bundle completion fails closed and requires a fresh call.

Aggregate profile/lock/bundle/policy digests remain provenance and cannot replace surface membership/digest checks. Conversely, an unrelated aggregate change does not block a Trellis-native task whose exact surfaces remain valid. Drift blocks load until Task 3 commits a valid restorative repair whose after digest equals the pinned/current contract, without changing integration revision.

## 10. Approval Replay Ledger and Task Outbox

### 10.1 Approval replay

The independent ledger schema is agent-workflow.approval-replay version 1. Its stable key is:

~~~text
proof_key = SHA256(JCS({
  approval_id,
  approval_challenge,
  route_decision_digest,
  workspace_instance_id
}))
~~~

Transaction identity is not part of the key. Each value binds exactly one task transaction and follows only:

~~~text
absent -> reserved -> consumed
~~~

Initial reservation requires a successfully verified proof still within TTL and clock-skew policy. Same-transaction recovery may continue after expiry. Another transaction can neither rebind nor consume the proof as new authority.

The planned journal exists before reservation. If a crash occurs in that window, resume may create the reservation only when the journal proves original in-TTL validation and all proof bytes/digests match. Rollback preserves the legal graph by CAS-creating reserved for that same transaction and then CAS-moving to consumed; a crash between the writes may only finish consumption. Consumed entries are permanent tombstones.

Missing, malformed, version-mismatched, duplicated, rebound, or identity-mismatched ledger state after registration fails closed and is never recreated empty.

### 10.2 Task outbox

Optional post-commit effects are immutable items under .agent-workflow/local/task-outbox/<effect-id>.json, schema agent-workflow.task-outbox version 1. Each binds operation, task/transaction/effect identities, handler ID/version, payload digest, deterministic idempotency key, and delivery state pending, delivered, or failed.

Task-state Service alone performs ordinary item creation and delivery transitions. Items are non-authoritative: delivery cannot change active/archived acceptance or roll back task state. A handler must prove idempotent replay; correctness-critical work belongs in the pre-commit CAS transaction. Compatibility migration may transform only the exact preexisting item set recorded by its lifecycle/workspace journal.

## 11. Task Transactions, Crash Recovery, and Concurrency

### 11.1 Task journal

Task journals live at .agent-workflow/task-transactions/<transaction-id>.json, use schema agent-workflow.task-transaction version 1, and bind:

- operation, task ID, admission ref/current ref, expected revision, workspace/project identities;
- verified runtime role/release/manifest identity;
- Decision/approval provenance and proof key for admission;
- exact task tree, integration, metadata, replay, and outbox preimages/candidates;
- phase, rollback progress, diagnostics, and cleanup records.

Immutable identities cannot change on rewrite. Journal phase tables are closed and exported to the discovery classifier. Unknown phases or schemas are ambiguity and recovery blockers.

### 11.2 Locks and CAS

Lock order is:

~~~text
Reconciler lock (only lifecycle/workspace coordination)
  -> runtime-state gate
  -> task-ref/task-path lock
  -> approval-ledger or outbox path lock when separately needed
~~~

Task commands never acquire the Reconciler lock. Every file mutation checks repository-relative path, existence, regular type, non-symlink status, full byte hash, and normalized mode. Directory moves additionally bind deterministic tree digest and same-filesystem identity. An external third state stops automatic recovery.

### 11.3 Recovery rules

task recover --transaction <id> --resume|--rollback is the only task recovery entry. It revalidates the journal's committed recovery runtime, workspace identity, task/location evidence, phase, and every preimage/candidate.

- before the operation commit point: explicit resume or CAS rollback;
- after the commit point: forward outbox/cleanup only;
- rollback choice is never guessed;
- committed task/archive state is never erased by recovery;
- changed or ambiguous external state produces a manual-recovery diagnostic.

An unfinished task journal blocks route issuance, runtime load, unrelated task mutation, workspace migration, and non-no-op lifecycle writes according to imported policy.

## 12. Test Matrix and Acceptance-Criteria Mapping

### 12.1 Primary acceptance ownership

| AC | Primary Task 4 evidence |
|---|---|
| AC-11 | immutable mode union, revisioned lifecycle, claim CAS, pinned contract |
| AC-21 | admission/archive/mutation serialize through runtime-state and task locks |
| AC-23 | fresh-clone registration creates workspace/replay pair atomically |
| AC-24 | pinned launcher executes register/route path and cold-cache failures close |
| AC-25 | task-bound Decision/proof enters recoverable admitting-to-active transaction |
| AC-31 | metadata-complete admission commit and side-effect-free rollback zone |
| AC-32 | direct-human proof binding and transaction-independent replay key |
| AC-36 | single launcher authority and mixed descriptor recovery |
| AC-38 | exact local-state writers and workspace migration rollback/commit |
| AC-39 | replay rollback preserves absent-to-reserved-to-consumed |
| AC-42 | clone B source-static verification and local-only migration |
| AC-43 | clean bootstrap plus verified non-sensitive caller context |
| AC-46 | checkout-local task-gate scope is reported honestly |
| AC-47 | source-release unfinished task journal blocks post-pull migration |
| AC-48 | every non-archived task blocks v0.1 workspace migration |
| AC-52 | source/target layout union and stored source snapshot |
| AC-54 | one-sided nonempty layout state is never stranded |
| AC-56 | bound quiescence rescan before workspace commit |
| AC-58 | UUID identity, ref reuse, collision-free archive, runtime uniqueness |
| AC-61 | existing-task runtime load uses integration/surface authority, not create Decision |

Task 4 also supplies integration evidence for imported AC-12, AC-27, AC-33, AC-34, AC-37, AC-41, AC-51, AC-53, AC-55, AC-57, AC-59, AC-60, AC-62, AC-63, and AC-64 without changing their primary owners.

### 12.2 Required tests

| Area | Required cases |
|---|---|
| launcher | cold/warm cache, offline miss, malicious uv config/env, global tool collision, no Python download, local Python range, URL/hash mismatch |
| caller context | allowed fields, duplicate/reserved args, relative/control paths, secret rejection, real harness visibility after verification |
| runtime allowlist | committed/candidate, untrusted journal runtime, mixed launcher/descriptor states, old task journal after pull |
| registration | termination before/after each rename, duplicate registration, corrupt/missing ledger, managed-ignore failure |
| migration | ahead/diverged/missing/invalid evidence, unsupported parser, every local candidate crash, final rename, external task-state race |
| scanner | roots/partitions, limits, symlinks, aliases, unknown entries, corrupt schemas, metadata disagreement, journal phase classification, stranded state |
| identity | duplicate UUIDs, same-ref concurrent admit, ref reuse with new UUID, archive destination collision rejection |
| admission | proof/journal reservation windows, every phase crash, metadata CAS failure, admitting non-runnable, exact commit recognition |
| mutation | two claimants, foreign release, phase/claim table, revision/mode mismatch, maintenance race |
| archive | directory move is non-commit, metadata failure, each phase crash, completed prerequisite, no-claim prerequisite |
| runtime load | stale create Decision ignored, revision/phase/claim race, unpinned entry, missing dependency, mode/content drift, immutable bundle, repair then resume |
| outbox | deterministic key, crash replay, idempotent delivery, non-authoritative failure |

All crash tests cover termination immediately before and after every atomic rename and ledger transition. Latest task-state change before workspace/lifecycle commit must make AWP_TASK_QUIESCENCE_CHANGED primary with current findings secondary.

### 12.3 Runtime/task-state errors

| Code | Exit | Meaning |
|---|---:|---|
| AWP_RUNTIME_BOOTSTRAP_PREREQUISITE_MISSING | 30 | supported uv or local Python is absent |
| AWP_RUNTIME_BINDING_MISMATCH | 30 | launcher/package/descriptor/Manifest/release claims disagree |
| AWP_RUNTIME_RECOVERY_NOT_AUTHORIZED | 21 | journal runtime is outside committed/candidate allowlist |
| AWP_CALLER_CONTEXT_INVALID | 2 | reserved caller envelope is malformed or forbidden |
| AWP_WORKSPACE_REGISTRATION_REQUIRED | 21 | valid fresh clone lacks committed local state |
| AWP_WORKSPACE_REGISTRATION_RECOVERY_REQUIRED | 21 | partial registration journal must be recovered |
| AWP_WORKSPACE_MIGRATION_RECOVERY_REQUIRED | 21 | partial local migration must be recovered |
| AWP_TASK_TRANSACTION_RECOVERY_REQUIRED | 21 | unfinished matching task transaction exists |
| AWP_TASK_ID_CONFLICT | 22 | immutable task UUID is duplicate or ambiguous |
| AWP_TASK_REF_CONFLICT | 22 | requested/current task ref violates location precondition |
| AWP_TASK_STATE_STALE | 40 | revision, phase, lifecycle, claim, bytes, or mode changed |
| AWP_TASK_TRANSITION_INVALID | 2 | requested closed lifecycle/mode transition is illegal |
| AWP_APPROVAL_REPLAY_BLOCKED | 22 | proof is expired for first use, rebound, consumed, or ledger-invalid |
| AWP_TASK_RUNTIME_LOAD_DENIED | 22 | existing-task entry is not admitted by current lifecycle contract |
| AWP_TASK_SURFACE_MISMATCH | 22 | owning/dependency surface is absent, drifted, unpinned, or digest-mismatched |
| AWP_TASK_ARCHIVE_BLOCKED | 22 | completion, claim, destination, metadata, or archive precondition fails |

Task 6 may present these codes but may not redefine their meaning or exit category.

## 13. Downstream Interface Freeze

The following object is the complete Task 4 exported interface. Its interface digest is computed only from the approved producer-content commit and recorded by a later registry commit.

~~~json
{
  "interface_schema": "agent-workflow.feature-interface",
  "interface_version": 1,
  "producer_task": "task-4",
  "producer_feature": "runtime-launcher-and-task-state",
  "schema_versions": {
    "agent-workflow.runtime-control": 1,
    "agent-workflow.caller-context": 1,
    "agent-workflow.workspace-local": 1,
    "agent-workflow.workspace-registration-transaction": 1,
    "agent-workflow.workspace-migration-transaction": 1,
    "agent-workflow.integration": 1,
    "agent-workflow.task-command": 1,
    "agent-workflow.task-transaction": 1,
    "agent-workflow.task-runtime-load-request": 1,
    "agent-workflow.task-runtime-dispatch": 1,
    "agent-workflow.approval-replay": 1,
    "agent-workflow.task-outbox": 1,
    "agent-workflow.runtime-failure": 1
  },
  "exports": [
    {
      "interface_id": "runtime.task-state.v1",
      "definition_owner": "task-4",
      "implementation_owner": "task-4",
      "schema_ids": [
        "agent-workflow.runtime-control",
        "agent-workflow.caller-context",
        "agent-workflow.workspace-local",
        "agent-workflow.workspace-registration-transaction",
        "agent-workflow.workspace-migration-transaction",
        "agent-workflow.integration",
        "agent-workflow.task-command",
        "agent-workflow.task-transaction",
        "agent-workflow.task-runtime-load-request",
        "agent-workflow.task-runtime-dispatch",
        "agent-workflow.approval-replay",
        "agent-workflow.task-outbox"
      ],
      "callables": [
        "bootstrap_project_runtime(LauncherInvocation) -> VerifiedRuntimeInvocation | RuntimeFailure",
        "register_workspace(VerifiedProjectRoot, VerifiedCommittedManifest, VerifiedCallerContext) -> WorkspaceRegistrationResult | RuntimeFailure",
        "migrate_workspace(VerifiedLocalStateContract, VerifiedLocalStateContract, VerifiedDirectedCompatibilityEdge, TaskSnapshotAndFindings) -> WorkspaceMigrationResult | RuntimeFailure",
        "scan_task_quiescence(VerifiedTrellisTaskLayout, VerifiedTrellisTaskLayout, VerifiedDiscoverySchemas, VerifiedDiscoverySchemas) -> TaskSnapshotAndFindings",
        "load_task_runtime(TaskRuntimeLoadRequest) -> ImmutableDispatchBundle | RuntimeFailure",
        "admit_task(TaskAdmissionRequest) -> TaskMutationResult | RuntimeFailure",
        "claim_task(TaskClaimRequest) -> TaskMutationResult | RuntimeFailure",
        "transition_task(TaskTransitionRequest) -> TaskMutationResult | RuntimeFailure",
        "release_task(TaskReleaseRequest) -> TaskMutationResult | RuntimeFailure",
        "archive_task(TaskArchiveRequest) -> TaskMutationResult | RuntimeFailure",
        "recover_task_transaction(TaskRecoveryRequest) -> TaskRecoveryResult | RuntimeFailure"
      ],
      "consumers": ["task-5", "task-6"]
    },
    {
      "interface_id": "runtime.errors.v1",
      "definition_owner": "task-4",
      "implementation_owner": "task-4",
      "schema_ids": ["agent-workflow.runtime-failure"],
      "callables": [],
      "consumers": ["task-5", "task-6"]
    }
  ],
  "digest_domains": [
    "agent-workflow.runtime-control.v1",
    "agent-workflow.caller-context.v1",
    "agent-workflow.workspace-registration.v1",
    "agent-workflow.workspace-migration.v1",
    "agent-workflow.task-tree.v1",
    "agent-workflow.task-transaction.v1",
    "agent-workflow.approval-proof-key.v1",
    "agent-workflow.task-outbox.v1",
    "agent-workflow.task-runtime-dispatch.v1"
  ],
  "digest_domain_owners": {
    "agent-workflow.runtime-control.v1": "runtime.task-state.v1",
    "agent-workflow.caller-context.v1": "runtime.task-state.v1",
    "agent-workflow.workspace-registration.v1": "runtime.task-state.v1",
    "agent-workflow.workspace-migration.v1": "runtime.task-state.v1",
    "agent-workflow.task-tree.v1": "runtime.task-state.v1",
    "agent-workflow.task-transaction.v1": "runtime.task-state.v1",
    "agent-workflow.approval-proof-key.v1": "runtime.task-state.v1",
    "agent-workflow.task-outbox.v1": "runtime.task-state.v1",
    "agent-workflow.task-runtime-dispatch.v1": "runtime.task-state.v1"
  },
  "error_namespace": "runtime.errors.v1"
}
~~~

This approval freezes only Task 4's exported interface. It does not approve Task 5 or Task 6 implementation plans or any production implementation.

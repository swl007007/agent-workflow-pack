# Agent Workflow Pack Renderer and Reconciler Design

**Status:** Approved
**Approval:** Covered by explicit user blanket approval on 2026-07-13 after successful self-review
**Dependencies:** Approved Core Resolver and Providers feature specs
**Implementation gate:** No implementation until the Renderer/Reconciler implementation plan is separately approved

## 1. Scope and Sole-Writer Boundary

Task 3 converts a validated DesiredStateIR into deterministic staged bytes, ownership decisions, an approvable SavedPlanEnvelope, and one recoverable lifecycle transaction. During lifecycle apply it is the sole writer of pack-managed and overlay-managed target content.

It does not resolve profiles/catalogs, fetch unverified inputs, calculate routes, mutate integrated task state, create ordinary task outbox items, or redefine domain errors. Task-state Service writes remain Task 4 authority.

Imported frozen interfaces:

| Interface | Producer C | Registry R | Digest |
|---|---|---|---|
| core.schema-catalog.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| core.profile-resolution.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| core.artifact-policy.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| core.surface-impact.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| core.saved-plan.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| core.task-snapshot.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| core.task-evaluators.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| core.render-projection.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| core.errors.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| providers.execution.v1 | b19e57a0e4d6e5094b853d428909e4d10d2283de | ac370a18d24be0bc4d29f58d56642df392db15f3 | 8c3890facd3f57198a4427ef2497077b924b13c780b7ac9b14f5227106b21fdb |
| providers.errors.v1 | b19e57a0e4d6e5094b853d428909e4d10d2283de | ac370a18d24be0bc4d29f58d56642df392db15f3 | 8c3890facd3f57198a4427ef2497077b924b13c780b7ac9b14f5227106b21fdb |

## 2. Render Units, Deterministic Staging, and File Modes

### 2.1 Renderer callable

~~~text
render(ir: DesiredStateIR, verified_provider_results: list[ProviderExecutionResult])
  -> StagedRenderTree | RendererFailure
~~~

The renderer accepts only frozen Core projections and verified provider results. It cannot reopen provider URLs, rerun dependency resolution, read ambient platform configuration, or inspect target state while producing candidate bytes.

### 2.2 Staged tree

Every staged record binds:

~~~yaml
schema_id: agent-workflow.staged-file
schema_version: 1
path: normalized-repository-relative-path
definition_id: stable-artifact-definition-id
surface_id: stable-surface-id
ownership: managed
merge_strategy: whole-file
source_digest: 64-lowercase-hex
render_digest: 64-lowercase-hex
candidate_byte_hash: 64-lowercase-hex
mode_policy: exact
candidate_mode: "0644"
validator_results: []
~~~

Staging occurs outside the target project or under a transaction-private same-filesystem area after apply locks. Candidate generation fixes encoding, newline policy, renderer/validator versions, ordering, locale/timezone, and all substitutions. Target artifacts are UTF-8 regular files; binary targets are unsupported.

Managed whole-file output binds exact bytes and exact mode when declared. Overlay output binds stable unique markers, managed-block bytes, and preserved host mode. Adopted and create-once output never converts an observation into overwrite authority.

### 2.3 Determinism

The same IR, provider results, renderer versions, and release-manifest substitutions produce identical staged content roots. Release-specific launcher substitutions affect render_digest, applied_file_hash, and distribution_render_digest but are excluded from launcher_bundle_digest.

## 3. Ownership Classes and Protected Paths

### 3.1 Managed

- absent target may be created when authorized;
- existing managed target may update only when full preimage matches Manifest bytes, mode, type, and non-symlink state;
- missing or drifted target blocks ordinary sync;
- deletion requires prior managed ownership, matching current state, and explicit retirement in the approved plan.

### 3.2 Overlay-managed

- only the unique nonnested managed block may change;
- external edits are permitted;
- missing, duplicate, nested, malformed, or overlapping markers block;
- retirement removes only the matching block after managed-block and host-file preconditions;
- host mode is preserved.

### 3.3 Adopted

Initial migration records a baseline. Later drift is reported but not overwritten. Promotion to another ownership class requires a new artifact definition and explicit approved plan.

### 3.4 Create-once-then-user-owned

Creation requires historical absence and current absence. After Manifest commit the record has created_once true and ownership user-owned. Later user edits/deletion never trigger recreation.

### 3.5 User-owned

May be read or validated but never modified.

Every target is revalidated against the frozen protected-path and Trellis cross-ownership contract. Reconciler authority does not cover integration.yaml, task roots, task transactions, local workspace state except exact authorized compatibility migration, or Task-state Service outbox mutations.

## 4. Plan Construction and Approval Envelope

### 4.1 Ownership observation

~~~text
plan_reconcile(
  ir: DesiredStateIR,
  staged: StagedRenderTree,
  manifest: Manifest | null,
  observed: ObservedTargetState,
  task_snapshot: TaskSnapshotAndFindings
) -> SavedPlanEnvelope | RendererFailure
~~~

For every path, the planner emits one OwnershipDecision from the Core schema and one complete precondition object. Parallel path/hash/mode arrays are forbidden.

### 4.2 Plan core

The planner constructs the imported PlanCore with:

- operation-branch identities;
- candidate file states excluding Manifest;
- exact ownership changes and retirements;
- candidate local-state contract/migrations when authorized;
- provider plan/approval/attempt/result digests;
- task snapshot/findings/digest;
- imported fixed workspace-state and task-gate evaluator results;
- candidate impact;
- prospective transaction and recovery runtime.

The plan is approvable only with no command blocker and no unresolved ownership/provider failure. A true no-op sync has no candidate file change, no selected repair drift, and performs no write transaction.

### 4.3 Approval

Write apply requires the exact saved plan digest and command-specific explicit approval mechanism defined by Task 6. Applying recomputes the full imported digest DAG and rejects any changed candidate, precondition, capability, evaluator result, provider evidence, or workspace identity.

## 5. Bootstrap and Project Lock Ordering

### 5.1 Existing project

Lifecycle write and recovery acquire:

~~~text
.agent-workflow/reconcile.lock
  -> .agent-workflow/runtime-state.lock
  -> transaction journal
  -> maintenance marker
~~~

OS lock ownership is authoritative; lock-file PID/timestamps are diagnostic only.

### 5.2 First init

1. acquire out-of-tree bootstrap OS lock keyed by normalized target and filesystem identity;
2. revalidate saved init plan, target identity, Manifest absence, bootstrap preconditions, and task snapshot;
3. create minimum control directories and project lock file;
4. acquire project reconcile lock while retaining bootstrap lock;
5. acquire runtime-state lock;
6. create planned journal, run live write probes, clean probe paths by CAS;
7. create maintenance and apply;
8. retain all locks through Manifest commit and cleanup.

A missing valid Manifest always selects bootstrap locking even if control residue exists. Residue may be removed only when recorded/known initial bytes and absence conditions still match.

## 6. Lifecycle Journal, Maintenance, and Commit Point

### 6.1 Journal

~~~json
{
  "schema_id": "agent-workflow.lifecycle-transaction",
  "schema_version": 1,
  "immutable_header": {},
  "task_quiescence_snapshot": {},
  "plan_digest": "64-lowercase-hex",
  "candidate_manifest_digest": "64-lowercase-hex",
  "candidate_manifest": {},
  "phase": "planned",
  "file_records": [],
  "created_directories": [],
  "diagnostics": [],
  "rollback_state": {}
}
~~~

The immutable header is exactly the imported SavedPlan header. journal_binding_digest binds transaction, operation, project/workspace, plan_core_digest, task_quiescence_digest, baseline Manifest digest, candidate generation, and recovery runtime. Mutable phase, applied files, diagnostics, retries, and rollback state do not participate.

Every journal replacement revalidates immutable fields byte-for-byte.

### 6.2 Phase graph

~~~text
planned
  -> probing
  -> prepared
  -> applying
  -> files_applied
  -> manifest_committed
  -> cleanup_pending
  -> complete
~~~

### 6.3 Maintenance

maintenance.json binds transaction_id, journal_binding_digest, final plan_digest, task_quiescence_digest, and candidate Manifest generation. It is created after successful probes and before authoritative apply. It is not rewritten for mutable journal phases.

While maintenance exists, Task 4 blocks new admission, task mutation, runtime write entries, and resume; only diagnostics and authorized recovery remain.

### 6.4 Commit

Workflow lock, local-state compatibility candidates, and managed artifacts apply before Manifest. Immediately before Manifest rename, the shared Task 4 scanner reruns under both locks and must equal the plan/journal snapshot byte-for-byte. Mismatch returns AWP_TASK_QUIESCENCE_CHANGED as unconditional primary error.

Manifest atomic rename is the commit point. Before it, resume or CAS rollback is possible. After it, only forward cleanup is legal.

Pre-commit permits only journal-recorded reversible file operations: private staging writes, backups, exact CAS, same-filesystem rename, chmod covered by CAS, and cleanup of transaction-created empty directories. Hooks, notifications, subprocess callbacks, network actions, Git auto-commit, lifecycle hooks, and new lifecycle outbox mechanisms are forbidden.

Task 3 has no ordinary task-outbox authority. It may transform existing replay/outbox state only as exact preimage/candidate paths of an umbrella-authorized compatibility migration.

## 7. File-State CAS and Atomic Replacement

FileState is:

~~~yaml
path: normalized-repository-relative-path
exists: true
file_type: regular
byte_hash: 64-lowercase-hex
mode: "0644"
non_symlink: true
managed_block_hash: canonical-null
~~~

Immediately before rename, chmod, block replacement, or deletion, CAS compares existence, type, complete bytes or managed block as applicable, normalized POSIX mode, and non-symlink state.

Replacement files are on the target filesystem. A changed precondition stops without overwriting later edits. Case/Unicode collisions, symlinks, cross-device rename, unsupported type, or ambiguous path identity block.

Backups are transaction-private and bind the complete original FileState. Rollback restores only when current state equals the recorded candidate. If current equals original, it is already restored. Any third state stops automatic rollback.

Created-directory cleanup requires original absence, journal-before-create evidence, real non-symlink directory, and current emptiness; removal is deepest-first.

## 8. Restorative sync --repair

Repair consumes the imported CandidateImpact repair branch:

~~~yaml
surface_id: stable-surface-id
change_kind: repair
contract_before_digest: expected-contract-digest
observed_before_digest: observed-drift-or-canonical-null
after_digest: expected-contract-digest
~~~

It is valid only when:

- authority_changes is empty;
- contract_before_digest equals after_digest;
- registry/inventory/reference graph are unchanged;
- the observed bytes/mode match observed_before_digest at CAS time;
- every affected task pins the same expected digest;
- explicit plan approval is present.

Repair to different bytes is contract-change. Ordinary sync/upgrade cannot absorb unexplained drift. Runtime load remains blocked until repair commits and resumes afterward without changing task contract or revision.

## 9. Pre-commit Rollback and Post-commit Forward Recovery

| Phase | Recovery |
|---|---|
| planned | resume or remove journal/control residue only after proving no probe/candidate applied |
| probing | resume probe or CAS-clean exact probe residue |
| prepared/applying/files_applied | resume or CAS rollback |
| manifest_committed/cleanup_pending | cleanup only |
| complete | no transaction action |

Rollback restores only exact recorded preimages and removes only exact transaction-created candidates under original-absence/candidate CAS. It never guesses. External modification produces a manual-recovery diagnostic.

A committed Manifest whose generation, last_transaction_id, and last_transaction_binding_digest match the journal/maintenance proves commit even if a later journal update is absent. Recovery must not roll it back.

Supported reversal of a committed change is a new approved upgrade/sync transaction, never transaction history rewind.

## 10. Filesystem Probes and Portability Boundary

Ordinary doctor and every dry-run perform zero target writes.

doctor --write-probe is a distinct authorized transaction. Apply preflight always runs live probes after locks and before maintenance. Probes verify:

- cross-process advisory lock;
- same-filesystem atomic replacement;
- regular-file/non-symlink checks;
- readable/settable POSIX mode bits;
- case and Unicode collision behavior.

Probe paths have nonce identities, original-absence preconditions, journaled candidates, and CAS cleanup. Interrupted residue blocks unrelated writes until probe recovery.

v0.1 mutation supports only Linux/WSL filesystems passing live probes. Paths under /mnt receive no exemption. Network filesystems, cross-device replacement, and unverified locks/modes/collisions are unsupported for writes while read-only diagnostics remain available.

## 11. Test Matrix and Acceptance-Criteria Mapping

| AC | Primary Task 3 evidence |
|---|---|
| AC-04 | second sync true no-op and zero writes |
| AC-05 | managed drift blocks with AWP_OWNERSHIP_DRIFT |
| AC-06 | overlay-external edits do not drift |
| AC-07 | drift requires approved restorative repair |
| AC-08 | every pre-Manifest crash resumes or rolls back |
| AC-09 | post-Manifest crash permits cleanup only |
| AC-10 | OS lock serialization and per-file CAS |
| AC-17 | legacy fixture preserves protected Trellis/Spec Kit state |
| AC-19 | CAS detects bytes, type, symlink, and mode |
| AC-20 | failed filesystem probes block writes |
| AC-26 | doctor/dry-run zero writes; write probe explicit |
| AC-37 | immutable journal_binding_digest and maintenance binding |
| AC-63 | separate contract/observed/after repair digests |

Tests inject termination at every phase, immediately around each candidate/Manifest rename, and during rollback. Concurrency covers two writers and external edits before CAS. Ownership tests cover all five classes, marker corruption, retirements, modes, and protected paths. Migration tests cover exact local preimages/candidates without ordinary outbox authority.

Renderer/Reconciler errors:

| Code | Exit | Meaning |
|---|---:|---|
| AWP_RENDER_NONDETERMINISTIC | 2 | identical inputs produce different staged content |
| AWP_OWNERSHIP_DRIFT | 20 | managed or managed-block state differs from baseline |
| AWP_OWNERSHIP_CONFLICT | 20 | ownership class, target, or marker composition conflicts |
| AWP_RECONCILE_LOCKED | 21 | another live writer holds the OS lock |
| AWP_RECONCILE_RECOVERY_REQUIRED | 21 | unfinished lifecycle/probe transaction requires recovery |
| AWP_FILE_CAS_MISMATCH | 40 | complete current file state differs from approved precondition |
| AWP_FILESYSTEM_UNSUPPORTED | 20 | live lock/rename/mode/collision probe failed |
| AWP_MAINTENANCE_CORRUPT | 21 | marker binding matches neither journal nor committed Manifest |
| AWP_ROLLBACK_CONFLICT | 21 | current state is neither original nor candidate |

## 12. Downstream Interface Freeze

~~~json
{
  "interface_schema": "agent-workflow.feature-interface",
  "interface_version": 1,
  "producer_task": "task-3",
  "producer_feature": "renderer-and-reconciler",
  "schema_versions": {
    "agent-workflow.staged-file": 1,
    "agent-workflow.staged-render-tree": 1,
    "agent-workflow.reconcile-plan-result": 1,
    "agent-workflow.lifecycle-transaction": 1,
    "agent-workflow.maintenance-marker": 1,
    "agent-workflow.file-state": 1,
    "agent-workflow.reconcile-result": 1,
    "agent-workflow.reconcile-recovery-result": 1,
    "agent-workflow.renderer-failure": 1
  },
  "exports": [
    {
      "interface_id": "renderer.reconcile.v1",
      "definition_owner": "task-3",
      "implementation_owner": "task-3",
      "schema_ids": [
        "agent-workflow.staged-file",
        "agent-workflow.staged-render-tree",
        "agent-workflow.reconcile-plan-result",
        "agent-workflow.lifecycle-transaction",
        "agent-workflow.maintenance-marker",
        "agent-workflow.file-state",
        "agent-workflow.reconcile-result",
        "agent-workflow.reconcile-recovery-result"
      ],
      "callables": [
        "render(DesiredStateIR, list[ProviderExecutionResult]) -> StagedRenderTree | RendererFailure",
        "plan_reconcile(DesiredStateIR, StagedRenderTree, Manifest | null, ObservedTargetState, TaskSnapshotAndFindings) -> SavedPlanEnvelope | RendererFailure",
        "apply_saved_plan(SavedPlanEnvelope) -> ReconcileResult",
        "recover_lifecycle(TransactionId, ResumeOrRollback) -> ReconcileRecoveryResult"
      ],
      "consumers": ["task-4", "task-6"]
    },
    {
      "interface_id": "renderer.errors.v1",
      "definition_owner": "task-3",
      "implementation_owner": "task-3",
      "schema_ids": ["agent-workflow.renderer-failure"],
      "callables": [],
      "consumers": ["task-4", "task-6"]
    }
  ],
  "digest_domains": [
    "agent-workflow.staged-render-tree.v1",
    "agent-workflow.lifecycle-transaction.v1",
    "agent-workflow.file-state.v1",
    "agent-workflow.reconcile-result.v1",
    "agent-workflow.feature-interface.v1"
  ],
  "error_namespace": "renderer.errors.v1"
}
~~~

This approval freezes only Task 3 renderer/reconciler contracts. It does not approve implementation code or its implementation plan.

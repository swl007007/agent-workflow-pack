# Agent Workflow Pack v0.1 Design

**Status:** Approved conversational design; pending written-spec review  
**Date:** 2026-07-13  
**Target:** New sibling repository `agent-workflow-pack`  
**Initial profile:** `sol56-sdd`  
**Initial platforms:** Claude Code, Codex, and OpenCode  
**Initial operating environment:** WSL2 and Linux

## 1. Purpose

`agent-workflow-pack` is a declarative workflow compiler and project-state coordinator. It acquires locked upstream content, resolves an activation profile into a desired-state intermediate representation, renders candidate project files in staging, and reconciles only explicitly authorized files or marked blocks into a target repository.

It is not a planner, executor, task database, or replacement for Spec Kit, Superpowers, or Trellis. Its job is to make their combined installation reproducible while preventing duplicate planners, competing executors, over-broad skill discovery, unsafe upgrades, and accidental replacement of user or runtime state.

The existing sibling `workflow-pack` directory is a read-only migration source for this product. It is not a runtime or CI dependency and will not be modified by the new CLI. Implementation may derive a sanitized, synthetic fixture from its structure, but must exclude personal journals, local identities, caches, and other sensitive content.

## 2. Goals

- Provide one reproducible `uvx` entry point for a clean WSL/Linux project.
- Install or migrate the `sol56-sdd` workflow without exposing disabled or route-gated skills to automatic discovery.
- Lock Trellis, Spec Kit, Superpowers, custom skills, templates, renderers, validators, and licenses.
- Support safe `init`, `sync`, `sync --repair`, `upgrade`, `doctor`, `test-routing`, and transaction recovery.
- Preserve user files and Trellis/Spec Kit runtime artifacts through file- or block-level ownership.
- Make routing ownership deterministic and testable across Claude Code, Codex, and OpenCode.
- Produce identical rendered content from a Git checkout, wheel, and sdist of the same release.

## 3. Non-goals

- Windows Native or macOS release support in v0.1.
- Guaranteed persistence ordering after sudden power loss or filesystem failure.
- A general plugin API or executable third-party profile language.
- Dynamic installation or removal of skills while a development task is running.
- Vendoring the complete source trees of Superpowers, Spec Kit, or Trellis.
- Modifying the legacy `workflow-pack` in place.
- A public `revert --transaction` command in v0.1.
- Treating natural-language routing evaluation as a deterministic release gate.
- Providing legal advice; the repository supplies engineering provenance and notices only.

## 4. Core Authority Model

Each state dimension has one scoped authority.

| Authority | Sole responsibility |
|---|---|
| `profiles/*.yaml` | Activation intent, route-admission policy selection, workflow ownership selection, platform defaults, and required capability levels |
| Release `workflow.lock` | Default locked workflow supply chain shipped with one CLI release |
| Target `.agent-workflow/workflow.lock` | Project-scoped workflow supply-chain identity used by `sync` |
| `artifact-definitions/*.yaml` | Manageable target paths, ownership class, merge strategy, stable markers, validators, and additional forbidden paths |
| Global protected-path policy | Paths no artifact definition may target or relax |
| `.agent-workflow/manifest.json` | What was actually materialized, the applied baselines and hashes, selected profile, digests, generation, and last committed transaction |
| `.trellis/tasks/<task>/integration.yaml` | Runtime state of one admitted `speckit-superpowers` task, including phase, owners, pinned contract, and executor claim |

A profile may select a versioned artifact policy, but it cannot expand the paths authorized by artifact definitions. A manifest records prior application state but cannot authorize a future write that current definitions prohibit.

## 5. Planned Repository Structure

```text
agent-workflow-pack/
├── pyproject.toml
├── uv.lock
├── workflow.lock
├── profiles/
│   ├── base.yaml
│   ├── sol56-sdd.yaml
│   ├── full-superpowers.yaml
│   └── trellis-native.yaml
├── catalog/
│   ├── components.yaml
│   ├── skills.yaml
│   └── platforms.yaml
├── schemas/
├── artifact-definitions/
├── custom-skills/
│   ├── heavy-development-router/
│   │   └── references/
│   ├── speckit-evidence-pack/
│   ├── sdd-superpower-micro-plan/
│   └── claude-mem-compactor/
├── overlays/
│   ├── trellis/
│   ├── speckit/
│   └── project-policy/
├── LICENSES/
├── THIRD_PARTY_NOTICES.md
├── src/agent_stack/
└── tests/
    ├── unit/
    ├── contracts/
    ├── golden/
    ├── integration/
    ├── concurrency/
    ├── e2e/
    └── fixtures/
```

`uv.lock` locks the Python development, test, build, and CLI runtime environment. `workflow.lock` locks the workflow components projected into target projects. Neither file substitutes for the other.

`schemas/` contains versioned schemas for profiles, catalogs, workflow locks, artifact definitions, manifests, transactions, saved plans, Desired State IR, route decisions, integration state, diagnostics, capability manifests, and provenance records.

The supported Python range for v0.1 is `>=3.11,<3.15`, subject to the final CI matrix. A Python minor version is supported only when build, unit, integration, and packaging tests pass for that version.

## 6. Component Boundaries and Data Flow

```text
Catalog + Release Lock + Profile + Artifact Definitions
                         |
                         v
                  Resolve / Validate
                         |
                         v
                 Desired State IR
                         |
                         v
                    Render / Plan
                         |
                         v
                  Reconcile / Apply
                         |
                         v
                   Target Project
```

### 6.1 Bootstrap Providers

Providers fetch, cache, and verify locked upstream runtimes and content. They do not write the target project and do not perform default global installations. They return structured acquisition and capability results.

### 6.2 Resolver and Policy Engine

The Resolver and Policy Engine are pure with respect to the target project. They validate schemas, resolve profile inheritance, compute skill and command dependency closure, detect conflicts, evaluate platform capabilities, compile route admission policy, and produce a Desired State IR.

### 6.3 Renderer

The Renderer converts the IR into a staged tree and canonical reconcile plan. Third-party initializers such as `trellis init` and `specify init` run only inside isolated temporary directories. Their output becomes candidate input; they never run directly against an existing target project.

### 6.4 Reconciler

Within an `agent-stack` installation or upgrade transaction, the Reconciler is the only component allowed to modify pack-managed or overlay-managed target content. Runtime planners, executors, Trellis, and Spec Kit may modify user-owned code, tasks, journals, and specification artifacts according to their own contracts, but may not modify pack-managed content.

### 6.5 Lifecycle Service

The Lifecycle Service orchestrates commands and transactions but contains no independent routing or ownership policy. Read-only commands and write commands consume the same Resolver implementation and IR schema.

### 6.6 Platform Adapters

Adapters project resolved policy into the native files, hooks, agents, commands, and skill directories of Claude Code, Codex, and OpenCode. An adapter may not add routes, signals, owners, or capabilities absent from the resolved IR.

## 7. Profile Contract

Profiles use schema-validated YAML with single inheritance.

```yaml
schema_version: 1
id: sol56-sdd
extends: base

route_admission:
  policy_version: 1
  default_route: native-light
  light_owner: native-light
  heavy_owner: speckit-superpowers
  trellis_native: explicit-only

bindings:
  native-light: sol-native

skills:
  enable: []
  disable: []

artifact_policy: integrated-sdd-v1
default_platforms: [claude, codex, opencode]
required_capabilities:
  project_instructions: instruction-only
  explicit_runtime_load: enforced
  maintenance_gate: enforced
  project_skills: instruction-only
```

These are minimum levels, not assumed platform facts. Every default platform must prove the required levels for its pinned adapter and harness version before release.

Rules:

- YAML duplicate keys are fatal.
- Multiple inheritance, inheritance cycles, arbitrary expressions, and executable profile code are forbidden.
- Scalar values are replaced by the child when present.
- Known mapping fields merge only according to their schema-defined rule.
- `default_platforms` is replaced as one value, not concatenated.
- Fields with set semantics are deduplicated and sorted during normalization.
- Explicitly listing the same skill in both `enable` and `disable` is an error.
- Enabling a skill whose required dependency is disabled produces a blocked resolution.
- Unknown fields or IDs are fatal unless introduced by a recognized schema version.

The digest contract is:

```text
profile_digest = SHA256(JCS(resolved_profile))
```

`resolved_profile` is the profile after inheritance, default insertion, schema normalization, and sorting of set-semantic arrays. It excludes diagnostics and presentation-only fields. JCS means RFC 8785 JSON Canonicalization Scheme.

## 8. Catalog and Workflow Lock

Catalog entries use stable IDs and describe:

- origin component and upstream location;
- version, release, or commit selection rules;
- dependencies, conflicts, provided capabilities, and required capabilities;
- references among skills, commands, hooks, agents, and runtime entries;
- supported projection platforms;
- license and provenance metadata;
- cache and extraction policy.

The release `workflow.lock` is committed and packaged with the CLI. `init` computes the exact transitive component closure required by the resolved profile and deterministically projects those unchanged locked identities and hashes into `.agent-workflow/workflow.lock`. It performs no version re-resolution and never queries a latest version.

`sync` consumes only the existing project lock and cannot modify it. `upgrade` creates a candidate lock, fetches and verifies its content, generates a candidate IR, and presents supply-chain, routing, and file differences before approval.

```text
current lock
  -> candidate lock
  -> Provider fetch/verify
  -> candidate Desired State IR
  -> supply-chain + routing + file diff
  -> active-task gate
  -> approval
  -> Reconcile lock + artifacts + manifest
```

All network requests require a trusted lock source. In an initialized project, the manifest and project-lock digests must agree before any request. In a migration project without a valid manifest, a project-supplied lock is never trusted for downloads; only the lock embedded in the cryptographically anchored CLI release may authorize acquisition.

## 9. Artifact Definitions and Protected Paths

Artifact definitions state what the pack may manage.

```yaml
schema_version: 1
id: trellis-integrated-workflow
source: overlays/trellis/workflow.md
targets:
  - path: .trellis/workflow.md
    ownership: overlay-managed
    merge_strategy: marked-block
    markers:
      begin: "<!-- agent-workflow:begin integrated-mode -->"
      end: "<!-- agent-workflow:end integrated-mode -->"
forbidden_paths: []
validators:
  - id: no-disabled-skill-reference
    version: 1
```

The global protected-path policy is a hard constraint over all definitions and includes at least:

```yaml
protected_paths:
  - .git/**
  - .trellis/tasks/**
  - .trellis/workspace/**
  - specs/**
  - .agent-workflow/transactions/**
```

Artifact definitions may add restrictions but cannot relax global protection. Reconciler control-plane code retains explicit internal authority over `.agent-workflow/manifest.json`, `.agent-workflow/workflow.lock`, `.agent-workflow/reconcile.lock`, `.agent-workflow/maintenance.json`, and `.agent-workflow/transactions/**`; ordinary artifact definitions may not target those files.

Additional rules:

- Paths are normalized repository-relative paths.
- Absolute paths, `..`, device paths, and all symlink targets are rejected in v0.1.
- Multiple definitions may not manage the same path or overlapping marker ranges unless an explicit composition contract exists.
- Marker pairs must be unique, non-nested, and stable.
- `overlay-managed` is valid only with `marked-block`.
- `managed` is valid only with whole-file replacement.
- `create-once-then-user-owned` is a creation policy that transitions to user ownership after the first successful creation.
- `.trellis/spec/**` may be seeded only through `create-once-then-user-owned`; after creation it is never overwritten or drift-enforced by the pack.

## 10. Artifact Bundle Digest

`artifact_bundle_digest` is a deterministic Merkle root over:

- canonical artifact-definition JSON;
- the actual bytes of every referenced template or overlay;
- renderer ID and version;
- validator ID and version;
- any referenced compatibility overlay and its locked content hash.

Merkle leaves are domain-separated, keyed by stable ID, and sorted before tree construction. Changing template content without changing its path changes the bundle digest.

Per-file records retain separate values:

- `source_digest`;
- `render_digest`;
- `applied_file_hash`;
- `managed_block_hash` for overlays.

Structured digests use normalized RFC 8785 JCS plus SHA-256. Rendered-file hashes use the actual UTF-8 bytes and are never conflated with structured-data digests. For overlay-managed files, drift decisions use only the managed block hash; the whole-file hash is observational and user edits outside markers do not cause a conflict.

## 11. Desired State IR

The IR is serializable and versioned but is not a persistent authority. It includes:

- resolved profile and all authority digests;
- current or candidate lock identity;
- selected platforms and measured capabilities;
- dependency and reference closure;
- route policy, rule IDs, and entry ownership;
- selected discoverable leaf skills;
- route-gated runtime catalog entries;
- render units and artifact definitions;
- conflicts, warnings, blocked reasons, and validation evidence.

All commands use the same Resolver and IR schema. `upgrade` uses a candidate lock to generate a candidate IR; read-only commands do not invent a separate interpretation.

## 12. Target Manifest

The target manifest is stored at `.agent-workflow/manifest.json`.

```json
{
  "schema_version": 1,
  "project_id": "stable-project-uuid",
  "generation": 7,
  "pack_version": "0.1.0",
  "profile": "sol56-sdd",
  "profile_digest": "sha256-value",
  "lock_digest": "sha256-value",
  "artifact_bundle_digest": "sha256-value",
  "platforms": ["claude", "codex", "opencode"],
  "last_transaction_id": "transaction-uuid",
  "previous_manifest_digest": "sha256-value",
  "files": []
}
```

`project_id` is generated once as a random UUID during the first committed `init`, then preserved by repository copies and clones unless the user performs a future explicit re-identification operation.

Each applicable file record includes its repository-relative path, definition ID, ownership, source and render digests, applied hash, adopted baseline, and marker metadata. A create-once record remains present after ownership transitions:

```json
{
  "path": ".trellis/spec/example.md",
  "ownership": "user-owned",
  "created_once": true
}
```

If the user later deletes that file, the pack does not recreate it automatically. The manifest never lists or hashes itself inside `files[]`. Project lock and transaction control files are recorded by top-level digests and transaction identity rather than ordinary artifact records.

The manifest is written last by atomic rename and represents only a fully committed transaction. Staged or partially applied state must never appear as the current manifest.

## 13. Ownership and Reconcile Semantics

### 13.1 Managed

- Path absent from the manifest and target: initial creation is allowed.
- Path recorded as managed and current hash equals the applied hash: an approved update is allowed.
- Path recorded as managed but missing: ownership drift; ordinary `sync` blocks.
- Missing or drifted managed content requires an explicit `sync --repair` plan.
- Deletion requires both prior managed ownership and a current hash equal to the applied hash.
- Retirement of managed content must be explicitly listed in an approved plan.

### 13.2 Overlay-managed

- Marker-external edits are allowed.
- Marker-internal drift blocks ordinary synchronization.
- Missing, duplicate, nested, malformed, or overlapping markers block.
- Retiring an overlay removes only the matching managed block after a hash check; it never deletes the host file.

### 13.3 Adopted

- Initial migration records a baseline and reports later drift.
- Adopted content is not overwritten automatically.
- Promotion to managed or overlay-managed requires a new explicit plan and compatible artifact definition.

### 13.4 Create-once-then-user-owned

- Create only when the path has never been created by the pack and is currently absent.
- After commit, record `created_once: true` and treat the file as user-owned.
- Deletion or modification by the user never triggers recreation or overwrite.

### 13.5 User-owned

User-owned content may be read or validated but is never modified by the Reconciler.

## 14. Lifecycle Commands

### 14.1 `bootstrap`

When a valid manifest exists and its digest matches the project lock, `bootstrap` fetches and verifies that project lock. Otherwise it uses only the immutable CLI release lock and ignores any untrusted project-local lock. It writes only the user cache and is an optional acceleration command.

### 14.2 `init`

Performs first installation or migration. It deterministically projects the release lock, resolves and renders the selected profile, and reconciles an approved plan. If a valid manifest already exists, `init` refuses and directs the user to `sync`. If an unfinished transaction exists, it refuses and directs the user to `recover`.

Existing Trellis, Spec Kit, or platform files are compared with staged initializer output. A pre-existing file whose bytes exactly match a candidate may be enrolled at the ownership class authorized by its artifact definition without rewriting it, but the plan must display that ownership change. `adopted` is reserved for an explicit observe-baseline migration policy that does not grant overwrite authority. Recognized blocks may become overlay-managed; unsafe differences block. Protected runtime state remains untouched.

### 14.3 `sync`

Uses the existing project profile identity, project lock, artifact bundle identity, schema versions, renderer versions, and manifest `pack_version`. It may reconcile only when those inputs match the running pack release and the result passes active-task gates. A normal `sync` never modifies the project lock; a pack-version or contract mismatch requires `upgrade`.

A `sync` may bypass the active-task gate only when the reconcile plan is a true no-op. Creating, deleting, repairing, or modifying any runtime-visible file requires the gate.

### 14.4 `sync --repair`

Creates an explicit repair plan for missing or drifted pack-managed content. It never silently overwrites a divergent preimage. The plan must show the expected baseline, actual state, candidate bytes, and active-task impact and must be approved like any other write transaction.

### 14.5 `upgrade`

Generates a candidate lock and candidate IR, fetches and verifies candidate content, shows supply-chain, routing, capability, license, and file changes, checks all active tasks, and reconciles only after explicit approval.

`upgrade --to` may target an earlier trusted release. This is the supported post-commit rollback mechanism and always creates a new forward transaction. v0.1 does not expose `revert --transaction`.

### 14.6 `doctor`

Performs read-only checks of schemas, digests, cache, external runtimes, capabilities, ownership, drift, routing graph, unfinished transactions, and active-task compatibility. It never treats partial transaction state as success.

### 14.7 `test-routing`

Runs deterministic policy, graph, golden-case, and rendered-adapter checks. It accepts normalized signal IDs rather than interpreting natural language.

### 14.8 `recover`

Acquires the same project writer lock as all other write commands. It supports validated `--resume` and `--rollback` only before the manifest commit point. It never guesses between them.

## 15. Saved Reconcile Plans

The plan digest is SHA-256 over canonical plan content excluding the digest field. A saved plan includes at least:

```yaml
schema_version: 1
project_id: stable-project-uuid
manifest_generation: 6
manifest_digest: sha256-value
profile_digest: sha256-value
lock_digest: sha256-value
artifact_bundle_digest: sha256-value
pack_version: 0.1.0
preconditions: []
candidate_hashes: []
```

Applying a saved plan revalidates:

- project identity;
- manifest generation and digest;
- pack and schema versions;
- every path precondition, file type, and non-symlink status;
- reconstructability of candidate bytes from the locked cache;
- platform capabilities;
- active-task gate.

`--dry-run` writes nothing to the target project. A plan is saved only when the user explicitly supplies `--out`; default output remains terminal-only.

## 16. Single-writer, CAS, and Transaction Protocol

All write commands and `recover` acquire an OS advisory lock at `.agent-workflow/reconcile.lock`. PID and timestamps stored in the lock file are diagnostic only; ownership is determined by the live OS lock.

After acquiring the lock, the command revalidates manifest identity, active-task state, maintenance state, and plan baselines. Immediately before each rename or deletion, it performs a per-path compare-and-swap check of the preimage hash, file type, and non-symlink state. Any changed precondition stops the transaction without overwriting later edits.

Transaction journals live at `.agent-workflow/transactions/<transaction-id>.json` and record phase, original hashes, backups, applied files, candidate hashes, candidate manifest, rollback state, and diagnostics.

```text
planned
  -> prepared
  -> applying
  -> files_applied
  -> manifest_committed
  -> cleanup_pending
  -> complete
```

Before `prepared`, the Reconciler verifies baselines, creates backups, records the candidate manifest and lock, and prepares replacement files on the same filesystem as their target. Files use temporary writes plus atomic rename. The project lock and managed artifacts are applied before the manifest. Manifest atomic rename is the logical commit point.

Recovery rules:

- `prepared`, `applying`, and `files_applied`: validated resume or CAS-protected rollback is allowed.
- `manifest_committed` and `cleanup_pending`: only cleanup is allowed.
- A committed transaction may be reversed only by a new `upgrade --to` or other future reconcile transaction.
- Rollback may restore a backup only when the current file equals the candidate hash.
- If the current file equals the original hash, that path is already restored.
- If it equals neither, external modification occurred and automatic rollback stops with an explicit manual-recovery report.
- `last_transaction_id` and manifest generation determine whether a crash occurred after manifest commit but before journal update.

v0.1 guarantees recovery from process termination under the documented filesystem assumptions. It uses atomic rename and best-effort flushes but does not guarantee ordering after sudden power loss, host failure, storage failure, or filesystems that do not honor the required semantics.

## 17. Maintenance and Active-task Gate

After acquiring the writer lock, a write transaction creates `.agent-workflow/maintenance.json`, then scans active tasks again before apply. Generated platform adapters, runtime loaders, and the heavy router must check this marker.

While maintenance exists:

- no new task may be admitted;
- existing tasks may not resume or advance phase;
- write-type runtime commands are blocked;
- only read-only diagnostics and `recover` are allowed.

The route decision is:

```yaml
schema_version: 1
route: blocked
blocked_by: maintenance
transaction_id: transaction-uuid
```

After maintenance clears, an existing task resumes its pinned mode and contract without reclassification.

Activity checks cover every non-archived Trellis task, not only the current session pointer:

- Any unfinished `speckit-superpowers` task blocks a contract-changing upgrade.
- A Trellis-native task blocks a candidate that changes Trellis, route admission, adapters, hooks, agents, or related skills.
- Multiple inconsistent active pointers, contract mismatches, or ambiguous task status block.
- A true no-op `sync` may proceed without changing runtime-visible content.

## 18. Route-admission Policy

The route order is:

```text
maintenance block
  -> pinned current task mode
  -> explicit user selection
  -> versioned heavy-signal policy
  -> native-light
```

`native-light` is an abstract owner bound to `sol-native` by `sol56-sdd`. `trellis-native` is explicit-only: mentioning Trellis in text is not an explicit request to use its workflow.

Heavy signals use stable IDs shared by the adapter and router:

```yaml
heavy_signals:
  hard:
    - explicit_heavy_workflow
    - audit_traceability_required
    - security_permission_change
    - public_contract_change
    - schema_or_data_migration
    - irreversible_or_destructive_operation
    - deployment_or_rollback_change
    - multi_session_coordination
  compound:
    - all: [multi_module, contract_surface]
    - all: [brownfield_uncertainty, compatibility_risk]
    - all: [resource_sensitive, long_running_operation]
```

The Router consumes the same compiled admission policy as the adapter. It may revalidate decision identity, matched rule IDs, signal IDs, task state, pinned digests, and approval, but may not maintain a second independent signal list.

## 19. Route Decision Contract

```yaml
schema_version: 1
decision_id: decision-uuid
route: speckit-superpowers
profile_digest: sha256-value
policy_digest: sha256-value
platform: codex
entry_owner: heavy-development-router
matched_rule_ids: []
signals: []
reasons: []
task_creation_approval: required
```

Task-creation approval and implementation activation are separate gates. Activation belongs in `integration.yaml` after the heavy task exists.

Conflicting explicit selection and pinned task mode blocks. Multiple active tasks with inconsistent pointers, missing decision identity, or mismatched profile/policy/contract digests also block.

## 20. Runtime Exposure and Explicit Loaders

Only allowlisted leaf skills enter platform auto-discovery directories. Route-gated content is installed under a managed, non-discoverable catalog:

```text
.agent-workflow/runtime/
├── heavy-development-router/
├── speckit-evidence-pack/
├── sdd-superpower-micro-plan/
├── claude-mem-compactor/
└── trellis-native/
```

Non-discoverability is an exposure boundary, not a filesystem or security boundary. The only supported platform entry to route-gated content is a generated loader or wrapper.

Before loading a runtime entry, the wrapper validates:

- maintenance state;
- route and pinned mode;
- current phase;
- entry owner;
- executor claim;
- profile, lock, policy, and router-contract digests;
- locked runtime-entry content digest.

Direct platform entry points for `/speckit.implement`, Trellis implement/check, or Spec Kit phase commands must not coexist when they bypass this gate. If a platform or harness cannot hide or gate a native entry, that capability is `instruction-only` or `unsupported`, never `enforced`.

Discoverable leaf skills undergo transitive-reference validation. If their locked upstream content references `using-superpowers`, planners, executors, or other gated entries, the pack must apply a first-party, locked compatibility overlay or block projection. A skill is not considered safe merely because its name appears leaf-like.

`heavy-development-router` is the sole top-level orchestrator only after admission selects `mode: speckit-superpowers`. It is not the global router for lightweight or Trellis-native tasks.

## 21. Integration State Contract

Every admitted heavy task stores `.trellis/tasks/<task>/integration.yaml` with the existing authority and canonical-artifact fields plus a pinned workflow contract.

```yaml
version: 1
mode: speckit-superpowers

workflow_contract:
  version: 1
  profile_digest_at_admission: sha256-value
  lock_digest_at_admission: sha256-value
  policy_digest_at_admission: sha256-value
  router_contract_version: 1

state:
  phase: planning
  state_revision: 12
  executor_claim:
    claim_id: claim-uuid
    executor: speckit-implement
    actor: actor-id
    claimed_at: 2026-07-13T16:00:00Z
    base_revision: 11
  blocked_reason: null

authority: {}
canonical_artifacts: {}
reference_only_artifacts: []
last_transition: {}
```

The final schema retains `authority.active_feature`, `canonical_artifacts`, `reference_only_artifacts`, `last_transition`, completion flags, and `blocked_reason` from the current custom router contract.

Claims do not expire automatically. Claim creation rereads the current revision and fails on mismatch. Stale-claim recovery requires Git state, task artifacts, journals, and execution evidence; ambiguous ownership requires user direction.

## 22. Capability Model

Capability levels are ordered:

```text
enforced > instruction-only > unsupported
```

- `enforced`: a verified hook, wrapper, plugin, or platform mechanism technically gates the supported entry path.
- `instruction-only`: compliance depends on model instructions and cannot be described as a technical guarantee.
- `unsupported`: the platform has no corresponding mechanism.

Adapter capability manifests bind claims to adapter and harness versions. Each manifest contains a platform ID, adapter version, a non-empty list of exact tested harness versions or closed tested version ranges, the measured level of each capability, the probe used by `doctor`, and the integration-evidence identifier. A range may be declared only when every boundary version and the project's compatibility policy have been tested.

Profiles declare minimum levels. Materialization succeeds only when `actual >= required` for every selected platform. The strict `sol56-sdd` profile does not downgrade. Claude Code, Codex, and OpenCode all must pass version-bound integration tests at their required levels before they remain in `default_platforms` for v0.1.

`doctor` must probe actual harness configuration where possible. For example, a Codex project hook that requires user-level feature enablement and one-time approval is not `enforced` until the probe confirms both conditions.

## 23. Provider and Third-party Execution Security

Hash verification establishes identity, not safe execution. Third-party initializers execute with:

- a temporary HOME and temporary XDG directories;
- a minimal environment-variable allowlist;
- no inherited tokens, SSH agent, cloud credentials, or unrelated secrets;
- closed stdin;
- explicit working directory unrelated to the target project;
- command timeouts and bounded captured output;
- file-count, process, memory, and CPU limits where supported;
- no target-project path unless an audited adapter explicitly requires it;
- network disabled when the environment provides an enforceable mechanism.

An unavailable isolation feature is reported at its actual capability level and is never called enforced.

Archive validation rejects:

- absolute paths and traversal;
- symlinks, hardlinks, devices, FIFO entries, and sockets;
- duplicate paths, case-folding collisions, and Unicode-normalization collisions;
- unsafe setuid/setgid bits or modes;
- excessive file count, single-file size, expanded size, or compression ratio.

Redirected downloads revalidate URL scheme and host. Cache writes use their own interprocess lock, temporary paths, final hash verification, and atomic promotion. Suspected partial or polluted cache entries are quarantined and never reused automatically.

## 24. Machine-readable Output and Errors

With `--json`, stdout contains exactly one versioned JSON object. Progress, logs, and external command diagnostics go to stderr. Python tracebacks are excluded by default and appear only in explicit debug mode on stderr.

Contracts:

- stable machine error codes such as `AWP_OWNERSHIP_DRIFT`;
- stable exit-code categories;
- all paths repository-relative;
- URL userinfo and secret-bearing query values redacted;
- external stderr length-limited and centrally sanitized;
- human and JSON output derived from the same diagnostic objects.

Initial exit-code categories are:

| Exit | Category |
|---:|---|
| 0 | success or verified no-op |
| 2 | CLI usage or schema/input validation |
| 20 | ownership conflict or drift |
| 21 | recovery required |
| 22 | active-task or maintenance block |
| 23 | capability insufficient |
| 30 | supply-chain verification failure |
| 31 | external provider/initializer failure |
| 40 | stale or mismatched saved plan |
| 70 | unexpected internal error |

Every error category must have human-output, JSON-schema, exit-code, path-normalization, and redaction tests.

## 25. Deterministic Routing Tests

`test-routing` validates:

- dependency and transitive-reference closure;
- no disabled or gated reference in discoverable projections;
- exactly one canonical owner for each mode and phase;
- no nested top-level orchestrator;
- platform capability sufficiency;
- runtime loader targets and locked digests;
- rendered adapter snapshots.

Golden cases use normalized signal IDs and cover:

- maintenance taking priority over a pinned task;
- explicit mode conflicting with an active task;
- single-file security or schema changes entering heavy mode;
- explicit Trellis-native intent versus merely mentioning Trellis;
- direct `/speckit.implement` bypass attempts;
- leaf-skill gated-reference leakage;
- instruction-only capability failing an enforced profile requirement;
- native-light small fixes;
- multi-module contract changes;
- active heavy-task resume.

Natural-language classification evaluation may be added later as a non-blocking eval suite.

## 26. Test Strategy

### 26.1 Schema, Canonicalization, and Property Tests

Test duplicate YAML keys, inheritance cycles, unknown fields, JCS digests, set sorting, Merkle inputs, path normalization, marker parsing, and manifest generations. Property/fuzz tests target path normalization, archive extraction, URL handling, and marker parsers.

### 26.2 Resolver and Policy Tests

Test dependencies, conflicts, stable IDs, capability ordering, route rules, and source-of-truth separation.

### 26.3 Golden Rendering

Snapshot Claude Code, Codex, and OpenCode output. Verify route-gated runtime content is absent from auto-discovery paths.

### 26.4 Reconciler Tests

Use temporary projects to test every ownership class, protected paths, symlink refusal, CAS, repair, overlay retirement, saved-plan staleness, and no-write conflict behavior.

### 26.5 Crash and Concurrency Tests

Inject process termination at each transaction phase. Test two CLI writers, cache contention, external modification immediately before rename, manifest-committed cleanup, and CAS rollback refusal.

### 26.6 End-to-end Sequence

```text
init
  -> doctor
  -> test-routing
  -> no-op sync
  -> drift conflict
  -> assert zero writes
  -> injected crash during apply
  -> doctor reports recovery-required
  -> recover --resume / recover --rollback
  -> active-task upgrade block
  -> archive task
  -> approved upgrade
```

A sanitized, synthetic snapshot derived from the current sibling `workflow-pack` structure is committed under `tests/fixtures/`. It preserves the relevant Trellis, router, skill, and ownership-conflict shapes without copying personal journals, local developer identity, caches, or unrelated documents. Tests prove that `.trellis/tasks/`, `.trellis/workspace/`, `.trellis/spec/`, and Spec Kit feature artifacts are not claimed at directory scope.

## 27. Packaging and Release

Build and test both wheel and sdist. Installation tests run from the built artifacts, not only from a source checkout. Package-data tests verify inclusion and exact digests of profiles, catalogs, schemas, artifact definitions, overlays, custom skills, licenses, and notices.

The canonical end-user `uvx` command installs the exact wheel asset of a verified immutable GitHub release. Release metadata binds that immutable release and asset hash to the actual full 40-hex source commit SHA. A source-audit command may use the full commit SHA directly, but release acceptance must execute the built wheel and sdist rather than relying only on a source checkout. A movable ordinary tag is never a trust anchor.

Release gates require:

- wheel, sdist, and Git-checkout rendering digests are identical;
- all default platforms meet their profile-required capability levels;
- a clean WSL/Linux environment initializes from the published artifact;
- repeated `sync` is a true no-op;
- crash, CAS, active-task, repair, and upgrade tests pass;
- supply-chain hashes and license provenance are complete;
- Python CI passes across every claimed minor version.

## 28. Licensing and Provenance

The root repository license covers only first-party code and content. `LICENSES/` stores full upstream license texts. Every upstream-derived or modified artifact records provenance:

```yaml
origin:
  component: trellis
  commit: full-commit-sha
  upstream_path: source/path
  license: AGPL-3.0
  modified: true
```

This applies to Trellis overlays, projected skills, agents, commands, hooks, and initializer-generated files when they contain copyrightable upstream content. Superpowers and Spec Kit content retains MIT notices; Trellis-derived content retains applicable AGPL-3.0 notices and modification statements.

`THIRD_PARTY_NOTICES.md` is generated from lock and provenance metadata and tested for completeness. Target-project materialization includes the notices required for the third-party content actually projected there.

## 29. Legacy Migration Requirements

The current custom skills are migration inputs, not automatically valid release artifacts.

- `heavy-development-router` must be repackaged with a complete `references/` directory containing its routing policy, integration schema, heavy-workflow contract, Trellis overlay, and replacement matrix.
- Every reference named by `SKILL.md` must exist at the locked path and participate in the runtime-entry digest.
- The current string `active_executor` contract migrates to `state_revision` plus the structured `executor_claim` object.
- Existing integrated tasks, if supported by a later migration tool, require an explicit schema migration plan; v0.1 may otherwise block and require completion under the old contract.
- The current Trellis-generated `.trellis/workflow.md`, adapters, hooks, agents, and skills are evidence for definitions and fixtures, not files to copy wholesale.
- The synthetic legacy fixture must cover missing router references, broad Trellis skill discovery, user-modified workflow blocks, active tasks, journals, and protected Spec Kit artifacts without containing personal data.

## 30. v0.1 Acceptance Criteria

- **AC-01:** A clean WSL/Linux target initializes through `uvx` from the exact wheel asset of a verified immutable release whose metadata identifies the full source commit SHA and asset hash; the corresponding sdist passes the same installation scenario.
- **AC-02:** `sol56-sdd` materializes Claude Code, Codex, and OpenCode only when each satisfies the profile's strict capability requirements.
- **AC-03:** `doctor` and deterministic routing tests pass immediately after initialization.
- **AC-04:** A second `sync` produces a verified no-op and performs no target writes.
- **AC-05:** User modification of managed content produces `AWP_OWNERSHIP_DRIFT` and zero writes.
- **AC-06:** User modification outside an overlay-managed block does not cause drift.
- **AC-07:** Missing managed content blocks normal sync and can be restored only through an approved `sync --repair` transaction.
- **AC-08:** A process crash before manifest commit is recoverable through validated resume or rollback.
- **AC-09:** A crash after manifest commit permits cleanup only and does not roll back the committed manifest.
- **AC-10:** Concurrent CLI writers are serialized by the OS lock, and external edits are protected by per-file CAS.
- **AC-11:** Maintenance blocks new admission, task resume, phase advancement, and write-type runtime entry.
- **AC-12:** An unfinished heavy task blocks every contract-changing upgrade; affected Trellis-native tasks also block.
- **AC-13:** Disabled or gated pack-managed skills are neither auto-discoverable nor transitively referenced by discoverable leaves.
- **AC-14:** Wheel, sdist, and Git-checkout renders have identical digests.
- **AC-15:** Provenance, full licenses, notices, lock hashes, and target notices are complete for every projected third-party artifact.
- **AC-16:** JSON output, exit codes, and redaction pass their versioned contract tests.
- **AC-17:** The legacy `workflow-pack` migration fixture retains all protected Trellis and Spec Kit runtime state.

## 31. Implementation Decomposition

The approved design should be implemented through separate feature specs, in this order:

1. **Core schemas and Resolver** — profiles, catalog, locks, canonicalization, artifact definitions, IR, policy graph, and diagnostics.
2. **Providers and secure cache** — acquisition, isolation, verification, extraction limits, provenance, and cache concurrency.
3. **Renderer and Reconciler** — staging, ownership, plans, OS lock, CAS, transactions, repair, and recovery.
4. **Routing and platform adapters** — runtime catalog, loaders, capability probes, route decisions, maintenance, and platform golden output.
5. **Lifecycle, packaging, and release** — CLI commands, JSON contracts, upgrade flow, E2E tests, artifact builds, immutable trust anchors, and notices.

Each feature spec must preserve the authority boundaries and acceptance criteria in this document. No feature spec may introduce a second planner, executor, route-policy source, ownership source, or task-state source.

## 32. Design Risks

- Strict enforcement may delay a platform's inclusion in `default_platforms`; the profile must not silently downgrade.
- Third-party initializer execution remains higher risk than static extraction even with isolation; the capability report must remain honest.
- WSL-mounted filesystems may provide weaker durability semantics; v0.1 promises process-crash recovery only.
- Upstream platform and Trellis templates may change paths or hook behavior; adapter and harness versions therefore remain locked and tested.
- Trellis-derived overlays and generated content require artifact-level provenance and license handling rather than a repository-wide assumption.

No blocking product decision remains in this design. Implementation planning begins only after the user reviews and approves this written spec.

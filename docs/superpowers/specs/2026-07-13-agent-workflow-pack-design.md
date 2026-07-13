# Agent Workflow Pack v0.1 Design

**Status:** Written-spec review — revised; awaiting user approval
**Date:** 2026-07-13  
**Target:** New sibling repository `agent-workflow-pack`  
**Initial profile:** `sol56-sdd`  
**Initial platforms:** Claude Code, Codex, and OpenCode  
**Initial operating environment:** WSL2 and Linux

## 1. Purpose

`agent-workflow-pack` is a declarative workflow compiler, project-state coordinator, and minimal admission/task-state runtime control plane. It acquires locked upstream content, resolves an activation profile into a desired-state intermediate representation, renders candidate project files in staging, reconciles only explicitly authorized files or marked blocks, and supplies the version-pinned on-demand commands required by generated runtime wrappers.

It is not a planner, executor, task database, or replacement for Spec Kit, Superpowers, or Trellis. Its job is to make their combined installation reproducible while preventing duplicate planners, competing executors, over-broad skill discovery, unsafe upgrades, and accidental replacement of user or runtime state.

The existing sibling `workflow-pack` directory is a read-only migration source for this product. It is not a runtime or CI dependency and will not be modified by the new CLI. Implementation may derive a sanitized, synthetic fixture from its structure, but must exclude personal journals, local identities, caches, and other sensitive content.

## 2. Goals

- Provide one reproducible `uvx` entry point for a clean WSL/Linux project.
- Install or migrate the `sol56-sdd` workflow without exposing disabled or route-gated skills to automatic discovery.
- Lock Trellis, Spec Kit, Superpowers, custom skills, templates, renderers, validators, and licenses.
- Support safe `init`, `sync`, `sync --repair`, `upgrade`, `doctor`, `test-routing`, and transaction recovery.
- Preserve user files and Trellis/Spec Kit runtime artifacts through file- or block-level ownership.
- Make routing ownership deterministic and testable across Claude Code, Codex, and OpenCode.
- Keep runtime admission and task-state commands callable through a project-managed launcher pinned to the installed pack release.
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
- A resident daemon, background service, or mutable globally shared CLI installation.
- Providing legal advice; the repository supplies engineering provenance and notices only.

## 4. Core Authority Model

Each state dimension has one scoped authority.

| Authority | Sole responsibility |
|---|---|
| `profiles/*.yaml` | Activation intent, route-admission policy selection, workflow ownership selection, platform defaults, and required capability levels |
| Release `workflow.lock` | Default locked workflow supply chain shipped with one CLI release |
| Target `.agent-workflow/workflow.lock` | Project-scoped workflow supply-chain identity used by `sync` |
| `compatibility/releases.yaml` | Explicitly supported release-transition edges and the schema, artifact, and task-contract migrations required by each edge |
| `artifact-definitions/*.yaml` | Manageable target paths, ownership class, merge strategy, stable markers, validators, and additional forbidden paths |
| Global protected-path policy | Paths no artifact definition may target or relax |
| `.agent-workflow/manifest.json` | What was actually materialized, the applied baselines and hashes, selected profile, digests, generation, and last committed transaction |
| `.agent-workflow/local/workspace.json` | Non-Git identity of the current working copy, bound to the repository-lineage ID |
| `.trellis/tasks/<task>/integration.yaml` | Pinned mode, workflow contract, and lifecycle of one admitted integrated task; the mode-specific branch is also authoritative for heavy-router phase, owners, artifacts, and executor claim when applicable |

A profile may select a versioned artifact policy, but it cannot expand the paths authorized by artifact definitions. A manifest records prior application state but cannot authorize a future write that current definitions prohibit.

## 5. Planned Repository Structure

```text
agent-workflow-pack/
├── pyproject.toml
├── uv.lock
├── workflow.lock
├── compatibility/
│   └── releases.yaml
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
├── runtime-launcher/
│   ├── agent-stack.sh.tmpl
│   └── runtime-control.schema.json
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

`uv.lock` locks only the repository's Python development, test, and build environment. It does not lock the isolated consumer environment created by `uvx`. `workflow.lock` separately locks the workflow components projected into target projects. Neither file substitutes for the other.

The v0.1 release wheel is self-contained at runtime: required pure-Python third-party runtime code is vendored under a private package namespace from hash-locked source artifacts, and the published wheel declares no external runtime `Requires-Dist` dependencies. Vendored code participates in package digests, provenance, full-license inclusion, modification notices, and vulnerability review. A required dependency that cannot be safely vendored as pure Python blocks release and requires a new design decision rather than silently adding an external runtime resolution.

`schemas/` contains versioned schemas for profiles, catalogs, workflow locks, release compatibility, runtime-control descriptors, artifact definitions, manifests, transactions, saved reconcile plans, provider-execution plans and approvals, Desired State IR, route decisions, integration state, diagnostics, capability manifests, and provenance records.

The supported Python range for v0.1 is `>=3.11,<3.15`. Release is blocked unless Python 3.11, 3.12, 3.13, and 3.14 each pass build, unit, integration, and packaging tests; narrowing the range requires an explicit spec and release-metadata change.

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

The Renderer converts the IR into a staged tree and canonical reconcile plan. Third-party initializers such as `trellis init` and `specify init` run only inside isolated temporary directories under the deterministic execution contract in Section 23. Their output becomes candidate input; they never run directly against an existing target project.

### 6.4 Reconciler

Within an `agent-stack` installation or upgrade transaction, the Reconciler is the only component allowed to modify pack-managed or overlay-managed target content. Runtime planners, executors, Trellis, and Spec Kit may modify user-owned code, task files, journals, and specification artifacts according to their own contracts, but may not modify pack-managed content or write `integration.yaml` except through the Task-state Service.

### 6.5 Task-state Service

The Task-state Service is the sole supported writer of `.trellis/tasks/<task>/integration.yaml`. It is a runtime-state writer, not part of the Reconciler, and has no authority over pack-managed files. Platform adapters and runtime agents call its CLI instead of editing integration state directly.

### 6.6 Lifecycle Service

The Lifecycle Service orchestrates installation-state commands and transactions but contains no independent routing or ownership policy. Lifecycle read-only and write commands that evaluate desired state consume the same Resolver implementation and IR schema; Task-state Service mutations use their separate state-machine contract.

### 6.7 Platform Adapters

Adapters project resolved policy into the native files, hooks, agents, commands, and skill directories of Claude Code, Codex, and OpenCode. An adapter may not add routes, signals, owners, or capabilities absent from the resolved IR.

### 6.8 Runtime Launcher

The Runtime Launcher is a managed, on-demand bootstrap path for the Task-state Service, route issuer, diagnostics, recovery, and workspace registration. It is not a daemon and retains no independent policy. It selects only the exact runtime identity authorized by the committed Manifest or an unfinished transaction journal, then the selected CLI independently revalidates those authorities before executing a command.

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
  native-light:
    codex: sol-native
    claude: platform-native
    opencode: platform-native

skills:
  enable: []
  disable: []

artifact_policy: integrated-sdd-v1
default_platforms: [claude, codex, opencode]
required_capabilities:
  project_instructions: instruction-only
  explicit_runtime_load: enforced
  maintenance_gate: enforced
  task_admission_gate: enforced
  task_archive_gate: enforced
  project_skills: instruction-only
provider_security_policy:
  temporary_home_xdg: required
  environment_allowlist: required
  secret_stripping: required
  stdin_closed: required
  target_path_isolation: required
  timeout_output_limits: required
  archive_cache_integrity: required
  baseline_resource_limits: required
  network_isolation: approval-required
  enhanced_os_sandbox: best-effort
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

`sync` consumes only the existing project lock and cannot modify it. `upgrade` creates a candidate lock, fetches and verifies its content, generates a candidate IR, and presents supply-chain, routing, and file differences before approval. A release transition is legal only when the running release's compatibility metadata contains an exact directed edge from the current installed release to the requested target and identifies every required schema, artifact, and task-contract migration.

```yaml
schema_version: 1
release: 0.1.1
transitions:
  - from: 0.1.0
    to: 0.1.1
    target_release:
      version: 0.1.1
      wheel_url: immutable-https-wheel-url
      wheel_sha256: sha256-value
      source_commit: full-40-hex-commit
      workflow_lock_digest: sha256-value
      artifact_bundle_digest: sha256-value
      schema_bundle_digest: sha256-value
      migration_bundle_digest: sha256-value
    manifest_schemas: {from: 1, to: 1}
    workflow_lock_schemas: {from: 1, to: 1}
    integration_schemas: {from: 1, to: 1}
    artifact_migration_id: identity-v1
    migration_digest: sha256-value
```

Edges are directed; reverse support requires its own entry. Each edge shipped by the running immutable release binds the complete target release asset and the expected workflow-lock, artifact, schema, and migration bundles; `target_release.version` must equal `to`. An edge never implies compatibility with an unlisted patch, minor, or historical version.

The default `upgrade` target is the release of the exact CLI currently executing the command. A different `--to` target is legal only when the running release contains the complete directed edge above. The CLI may read its own trusted edge before acquisition, but it must verify the target wheel's complete byte hash before importing code or parsing any lock, schema, migration, or artifact metadata from that asset. Every parsed target bundle must then match the digest bound by the edge or the transition stops before project writes.

```text
current lock
  -> compatibility edge validation
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
    mode_policy: preserve
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
  - .agent-workflow/local/**
  - .agent-workflow/task-transactions/**
  - .agent-workflow/transactions/**
```

Artifact definitions may add restrictions but cannot relax global protection. Internal control-plane code retains explicit authority over `.agent-workflow/manifest.json`, `.agent-workflow/workflow.lock`, `.agent-workflow/reconcile.lock`, `.agent-workflow/runtime-state.lock`, `.agent-workflow/maintenance.json`, `.agent-workflow/local/**`, `.agent-workflow/task-transactions/**`, and `.agent-workflow/transactions/**`; ordinary artifact definitions may not target those files. Only the Task-state Service may use the local task locks, task staging, task-transaction journals, or integration state.

The generated ignore overlay excludes `.agent-workflow/local/`, `.agent-workflow/task-transactions/`, `.agent-workflow/transactions/`, both OS lock files, maintenance state, backups, and temporary files from Git. The Manifest, project workflow lock, and managed runtime catalog remain project-scoped files that may be committed. `doctor` blocks writes when ephemeral control state is tracked or when required project-scoped authority files are unexpectedly ignored.

Additional rules:

- Paths are normalized repository-relative paths.
- Absolute paths, `..`, device paths, and all symlink targets are rejected in v0.1.
- Multiple definitions may not manage the same path or overlapping marker ranges unless an explicit composition contract exists.
- Marker pairs must be unique, non-nested, and stable.
- `overlay-managed` is valid only with `marked-block`.
- `managed` is valid only with whole-file replacement.
- Every target declares `mode_policy: exact` or `preserve`. `exact` includes a normalized POSIX mode such as `0644` or `0755` and is valid only for whole-file `managed` or initial create-once output. Overlay-managed and adopted host files use `preserve`.
- v0.1 manages only regular-file POSIX permission bits masked to `0777`; it does not manage owner, group, ACLs, xattrs, or platform-specific flags. Executable bits are part of the file-state contract.
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
- `applied_mode` or observed preserved mode;
- `managed_block_hash` for overlays.

Structured digests use normalized RFC 8785 JCS plus SHA-256. Rendered-file hashes use the actual UTF-8 bytes and are never conflated with structured-data digests; v0.1 target artifacts must be valid UTF-8 regular files, so binary target materialization is unsupported. A file-state precondition combines path, regular-file type, byte hash, normalized POSIX mode, and non-symlink status. For overlay-managed files, content drift decisions use only the managed block hash and preserve the host mode; the whole-file hash and observed mode are informational unless a separately authorized policy says otherwise.

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

All lifecycle commands that evaluate workflow desired state use the same Resolver and IR schema. `upgrade` uses a candidate lock to generate a candidate IR; read-only lifecycle commands do not invent a separate interpretation. Task-state mutations do not create an IR and are governed by Section 21.

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

`project_id` is a repository-lineage UUID. It is generated as candidate plan data for first init, becomes authoritative only when that init commits, and is intentionally preserved by repository copies and clones unless a future explicit lineage-fork operation assigns a new identity.

Each working copy also has non-Git local state at `.agent-workflow/local/workspace.json`:

```json
{
  "schema_version": 1,
  "project_id": "stable-project-uuid",
  "workspace_instance_id": "clone-local-uuid"
}
```

The workspace UUID is generated independently in each ordinary clone. The local file must be excluded from version control by a managed ignore marker. `doctor` blocks writes if it is tracked, malformed, or bound to a different lineage. Artifact definitions cannot manage this local state. Deliberately copying this ignored local file is outside the supported portability contract.

Planning and dry-run do not create the local state. Before it exists, a first-init saved plan contains candidate lineage and workspace UUIDs plus a digest of the normalized target path and requires Manifest and local-state absence. The approved init transaction commits those identities for the same target. Every later saved plan binds both `project_id` and the persisted `workspace_instance_id`; applying it in another clone fails even when repository content and Manifest digests match.

Each applicable file record includes its repository-relative path, definition ID, ownership, source and render digests, applied byte hash, applied or observed POSIX mode, adopted baseline, and marker metadata. A create-once record remains present after ownership transitions:

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
- Path recorded as managed and current byte hash, mode, type, and non-symlink state equal the applied file state: an approved update is allowed.
- Path recorded as managed but missing: ownership drift; ordinary `sync` blocks.
- Missing or drifted managed content requires an explicit `sync --repair` plan.
- Deletion requires both prior managed ownership and a current file state equal to the applied file state.
- Retirement of managed content must be explicitly listed in an approved plan.

### 13.2 Overlay-managed

- Marker-external edits are allowed.
- Marker-internal drift blocks ordinary synchronization.
- Missing, duplicate, nested, malformed, or overlapping markers block.
- Retiring an overlay removes only the matching managed block after a managed-block hash and host-file precondition check; it never deletes the host file or changes the preserved host mode.

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

Planning and `--dry-run` do not create `.agent-workflow/`, a lock file, local identity, maintenance marker, or any other target-project content. First apply uses the bootstrap lock handoff defined in Section 16.

Existing Trellis, Spec Kit, or platform files are compared with staged initializer output. A pre-existing file whose bytes exactly match a candidate may be enrolled at the ownership class authorized by its artifact definition without rewriting it, but the plan must display that ownership change. `adopted` is reserved for an explicit observe-baseline migration policy that does not grant overwrite authority. Recognized blocks may become overlay-managed; unsafe differences block. Protected runtime state remains untouched.

### 14.3 `sync`

Uses the existing project profile identity, project lock, artifact bundle identity, schema versions, renderer versions, and manifest `pack_version`. It may reconcile only when those inputs match the running pack release and the result passes active-task gates. A normal `sync` never modifies the project lock; a pack-version or contract mismatch requires `upgrade`.

A `sync` may bypass the active-task gate only when the reconcile plan is a true no-op. Creating, deleting, repairing, or modifying any runtime-visible file requires the gate.

### 14.4 `sync --repair`

Creates an explicit repair plan for missing or drifted pack-managed content. It never silently overwrites a divergent preimage. The plan must show the expected baseline, actual state, candidate bytes, and active-task impact and must be approved like any other write transaction.

### 14.5 `upgrade`

Generates a candidate lock and candidate IR, fetches and verifies candidate content, shows supply-chain, routing, capability, license, and file changes, checks all active tasks, and reconciles only after explicit approval.

Without `--to`, the target is the immutable release of the currently executing CLI. The candidate workflow lock, definitions, schemas, and migrations come from that verified release bundle rather than from mutable project content or a latest-version query.

`upgrade --to` accepts only an immutable trusted release explicitly reachable from the installed release through `compatibility/releases.yaml`. Trust is necessary but not sufficient: a missing edge, unsupported Manifest or lock schema, absent artifact migration, or incompatible active task contract blocks before acquisition or apply. The command never invokes an older CLI against newer state.

Targeting an allowed earlier release is the supported post-commit rollback mechanism and always creates a new forward transaction using compatibility logic shipped by the currently running release. v0.1 supports only same-schema targets explicitly listed in the compatibility matrix; the initial v0.1 release has no historical target until a later compatible release publishes such an edge. Arbitrary historical rollback is not promised, and v0.1 does not expose `revert --transaction`.

### 14.6 `doctor`

Ordinary `doctor` is strictly read-only. It checks schemas, digests, cache, external runtimes, capabilities, ownership, drift, routing graph, unfinished transactions, active-task compatibility, static mount facts, and any previously recorded filesystem-probe evidence. It never creates locks, refreshes evidence, intentionally updates target or cache state, or treats partial transaction state as success. A filesystem property that cannot be established from still-valid evidence is reported as `unverified`, not guessed as passing.

`doctor --write-probe` is a separate, explicitly authorized mutation mode. It acquires the applicable bootstrap or project lock, performs bounded temporary probes on the actual target filesystem, CAS-cleans every probe path, and records cache-side or ignored local evidence only after successful cleanup. It does not reconcile artifacts, create a Manifest, or enter maintenance. A failed or interrupted probe leaves a recorded residue set that must be cleaned or recovered before another write command.

### 14.7 `test-routing`

Runs deterministic policy, graph, golden-case, and rendered-adapter checks. It accepts normalized signal IDs rather than interpreting natural language.

### 14.8 `recover`

Acquires the same bootstrap/project Reconciler locks required by the interrupted lifecycle transaction. It supports validated `--resume` and `--rollback` only before the Manifest commit point. It never guesses between them and does not use the Task-state Service's mutation path.

`recover --probe <id> --resume|--rollback` is the narrow recovery entry for a standalone `doctor --write-probe` journal. It may touch only the exact recorded probe paths and cache-side evidence under CAS; it cannot create a Manifest, enter maintenance, or reconcile artifacts. Task transactions continue to use `task recover`.

### 14.9 `route decide`

The project launcher dispatches `agent-stack route decide --platform <id> --operation create-task --task-ref <ref> --intent <file> --signals <stable-id,...>`, the sole issuer of executable task-creation Route Decisions. A model or user may propose the task ref, Task Intent, candidate signal IDs, and explanatory reasons, but cannot supply authority digests, matched rules, route, entry owner, decision identity, challenge, or approval state. The command validates and normalizes those proposals, takes a shared runtime-state gate lock for a consistent task snapshot, reads current project and task authorities, applies the compiled admission policy, and emits the decision without creating the task path. An implementation may use the exclusive gate when portable shared locking is unavailable. `operation: classify-only` remains available when no task creation is requested. The command does not interpret natural language or mutate task state.

### 14.10 `task admit|claim|transition|release|archive|recover`

These commands are the only supported mutation interface for integrated task lifecycle. `admit` consumes a task-bound Route Decision and one-time user-approval proof, then creates the task shell and revision 1 together through the task-admission transaction in Section 21. `claim`, `transition`, and `release` require the expected revision plus command-specific preconditions. `archive` coordinates the locked Trellis archive adapter and integration lifecycle in one recoverable task transaction. `task recover --transaction <id> --resume|--rollback` may resume any validated unfinished task transaction, but rollback is legal only before that operation's commit point; after commit it may finish forward completion or cleanup and may not erase the committed task or archive. Platform wrappers must not expose direct Trellis create/archive, direct integration writes, or non-interactive approval bypasses.

### 14.11 `workspace register`

A fresh clone contains the repository-lineage Manifest and managed launcher but not ignored local workspace state. `.agent-workflow/bin/agent-stack workspace register` validates the runtime binding, Manifest, and managed ignore marker, requires local-state absence, acquires the bootstrap and project locks in that order, and atomically creates a new `.agent-workflow/local/workspace.json`. It does not change the Manifest, workflow lock, artifacts, or tasks and refuses during maintenance or an unfinished transaction. Route issuance, task commands, and Reconciler-backed writes block until registration succeeds; read-only diagnostics remain available and report the required action.

## 15. Saved Reconcile Plans

The plan digest is SHA-256 over canonical plan content excluding the digest field. A saved plan includes at least:

```yaml
schema_version: 1
transaction_id: prospective-transaction-uuid
project_id: stable-project-uuid
workspace_instance_id: clone-local-uuid
manifest_generation: 6
manifest_digest: sha256-value
profile_digest: sha256-value
lock_digest: sha256-value
artifact_bundle_digest: sha256-value
pack_version: 0.1.0
preconditions: []
candidate_file_states: []
```

Each precondition and candidate file-state object binds one repository-relative path to existence, regular-file type, byte hash, normalized POSIX mode, and non-symlink status; overlay entries additionally bind marker and managed-block hashes. The plan never relies on parallel path, hash, and mode arrays.

Applying a saved plan revalidates:

- repository-lineage and workspace-instance identities;
- manifest generation and digest;
- pack and schema versions;
- prospective transaction identity and any bound provider-execution approvals;
- every path precondition, byte hash, POSIX mode, file type, and non-symlink status;
- reconstructability of candidate bytes from the locked cache;
- platform capabilities;
- active-task gate.

`--dry-run` writes nothing to the target project. A plan is saved only when the user explicitly supplies `--out`; default output remains terminal-only.

For first init only, the saved plan carries `project_id_precondition: absent`, `candidate_project_id`, `workspace_instance_precondition: absent`, `candidate_workspace_instance_id`, and `target_path_digest` instead of existing identities. These bootstrap fields are part of the canonical plan digest and cannot be rebound at apply time.

## 16. Single-writer, CAS, and Transaction Protocol

After a valid Manifest and local workspace identity exist, all Reconciler-backed lifecycle write commands and `recover` acquire the project OS advisory lock at `.agent-workflow/reconcile.lock`. Task-state commands use the separate protocol in Section 21. Fresh-clone workspace registration uses the bootstrap-to-project lock order without starting a Reconciler transaction. PID and timestamps stored in a lock file are diagnostic only; ownership is determined by the live OS lock.

First init and recovery of an uncommitted first-init transaction use an overlapping bootstrap-lock handoff:

1. Obtain explicit plan approval; planning and dry-run remain lock-free and perform no target writes.
2. Acquire an out-of-tree OS advisory lock under the user cache, keyed by the canonical normalized target path and probed filesystem identity. Symlinked or ambiguous targets are rejected.
3. Revalidate target identity, saved-plan bootstrap fields, absence of a valid Manifest, transaction state, ownership baselines, and active tasks.
4. Create the minimum control directories and lock files, then acquire `.agent-workflow/reconcile.lock` while continuing to hold the bootstrap lock.
5. Acquire `.agent-workflow/runtime-state.lock`, revalidate again, atomically create the transaction journal as `planned`, advance it to `probing`, and execute the filesystem write probe before creating maintenance or applying authoritative state.
6. CAS-clean all probe paths, persist the successful evidence, advance the journal, then create a maintenance marker bound to the transaction ID and journal digest. Rescan active tasks and only then begin apply.
7. Hold the bootstrap lock, project lock, and runtime-state gate through probing, file application, Manifest commit, maintenance cleanup, and journal finalization. Future lifecycle transactions use only the project lock plus the runtime-state gate while maintenance is active.

A lifecycle process that sees no valid Manifest always enters through the bootstrap lock even if a project lock file or control directory already exists. This prevents a half-created control plane from changing lock selection. Empty preparation residue created before the journal is treated as uncommitted bootstrap residue and may be removed only while the bootstrap and project locks are held and all expected paths remain empty or match their known initial bytes.

After acquiring the lock, the command revalidates manifest identity, active-task state, maintenance state, and plan baselines. Immediately before each rename, chmod, or deletion, it performs a per-path compare-and-swap check of the preimage byte hash, normalized POSIX mode, file type, and non-symlink state. Any changed precondition stops the transaction without overwriting later edits.

Transaction journals live at `.agent-workflow/transactions/<transaction-id>.json` and record phase, original file states, backups, applied files, candidate file states, candidate Manifest, rollback state, diagnostics, and every directory first created by that transaction with its original absence precondition.

```text
planned
  -> probing
  -> prepared
  -> applying
  -> files_applied
  -> manifest_committed
  -> cleanup_pending
  -> complete
```

Before `prepared`, the Reconciler verifies baselines, creates backups, records the candidate Manifest and workflow lock, and prepares replacement files on the same filesystem as their target. Files use temporary writes plus atomic rename. The project workflow lock and managed artifacts are applied before the Manifest. Manifest atomic rename is the logical commit point.

Recovery rules:

- `planned`: validated resume or cleanup of journal/control residue is allowed only after confirming that no probe or candidate file state was applied.
- `probing`: validated probe resume or CAS-protected cleanup is allowed; no artifact apply may begin until all probe residue is removed and passing evidence is recorded.
- `prepared`, `applying`, and `files_applied`: validated resume or CAS-protected rollback is allowed.
- `manifest_committed` and `cleanup_pending`: only cleanup is allowed.
- A committed transaction may be reversed only by a new `upgrade --to` or other future reconcile transaction.
- Rollback may restore a backup only when the current complete file state equals the recorded candidate state.
- If the current complete file state equals the original state, that path is already restored.
- If it equals neither state, external modification occurred and automatic rollback stops with an explicit manual-recovery report.
- Rollback removes a transaction-created directory only when it was absent at baseline, was recorded before creation, is still a real non-symlink directory, and is empty at cleanup time. Removal proceeds deepest-first; pre-existing or non-empty directories are never removed.
- `last_transaction_id` and manifest generation determine whether a crash occurred after manifest commit but before journal update.

v0.1 guarantees recovery from process termination under the documented filesystem assumptions. It uses atomic rename and best-effort flushes but does not guarantee ordering after sudden power loss, host failure, storage failure, or filesystems that do not honor the required semantics.

### 16.1 Filesystem Preconditions

Ordinary `doctor` and every `--dry-run` perform zero target writes. They may inspect mount metadata and cached probe evidence, but report absent, stale, path-mismatched, filesystem-mismatched, or version-incompatible evidence as `unverified`.

`doctor --write-probe` and an approved apply preflight test the actual target filesystem for cross-process advisory-lock behavior, same-filesystem atomic replacement, regular-file and non-symlink checks, readable and settable POSIX mode bits, path case behavior, and Unicode-normalization collision behavior. Apply commands always perform this live probe after acquiring the applicable writer locks and before maintenance or authoritative file replacement; cached evidence is diagnostic and cannot replace apply-time validation. Temporary replacement files and their targets must share a filesystem. Case-folded or normalized path collisions block even when the host would otherwise permit both names.

Each probe uses nonce-named paths with recorded original-absence preconditions. First-init probe residue is recorded in the bootstrap transaction; initialized-project probe residue is recorded in the current transaction; standalone `doctor --write-probe` uses a cache-side probe journal keyed to the canonical target and filesystem identity. Cleanup deletes only exact recorded paths that still match their candidate type, bytes, and mode. A crash or failed CAS leaves recovery-required evidence and blocks unrelated writes rather than treating the probe as successful. Successful evidence binds the canonical target, filesystem and mount identity, probe contract and CLI versions, measured capabilities, and completion time.

The v0.1 write contract supports only Linux or WSL filesystems that pass these probes. A WSL path under `/mnt/*` is never assumed safe from its path alone; failed or indeterminate lock, rename, mode, or collision probes block write commands while leaving read-only diagnostics available. Network filesystems, cross-device replacements, and filesystems with unverified advisory locks are unsupported for mutation.

## 17. Maintenance and Active-task Gate

After acquiring the applicable writer locks, a write transaction also acquires the exclusive runtime-state gate lock, atomically persists the transaction journal for process-crash recovery, creates `.agent-workflow/maintenance.json`, and then scans active tasks again before apply. It holds the gate through maintenance cleanup. The marker contains the transaction ID, journal digest, plan digest, and candidate Manifest generation. Generated platform adapters, runtime loaders, and the heavy router must check this marker.

If a marker references an existing unfinished transaction, `doctor` reports recovery-required. If the current Manifest's generation and `last_transaction_id` match the marker, the transaction is committed even when the journal update or journal itself is missing; `recover` may finish cleanup only. A marker matching neither a journal nor the current Manifest is corrupt or orphaned and is never silently ignored. Explicit orphan cleanup is allowed only while all applicable locks are held and after CAS validation proves that either the prior committed Manifest baseline or first-init bootstrap preconditions remain intact, no transaction temporary or backup files remain, and no candidate file state was applied; otherwise writes remain blocked for manual recovery.

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

Activity checks cover every non-archived integration state reachable from the locked Trellis active and archive roots, plus every unfinished task transaction; they do not rely only on the current session pointer:

- `active`, `blocked`, `completed`, and `archiving` all remain gating states; only `archived` is non-gating.
- Any unfinished `speckit-superpowers` task blocks a contract-changing upgrade.
- A Trellis-native task blocks a candidate that changes Trellis, route admission, adapters, hooks, agents, or related skills.
- Any unfinished task-admission or task-archive transaction blocks lifecycle writes and runtime mutation until `task recover` resolves it.
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

`native-light` is an abstract owner with platform-specific bindings. In `sol56-sdd`, Codex binds it to `sol-native`, while Claude Code and OpenCode bind it to their platform-native lightweight planning behavior. `trellis-native` is explicit-only: mentioning Trellis in text is not an explicit request to use its workflow.

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
    - architecture_or_subsystem_change
    - dependency_or_external_integration_change
    - resource_or_large_data_risk
    - reproducibility_provenance_governance
    - acceptance_criteria_blocking_ambiguity
  compound:
    - all: [multi_module, contract_surface]
    - all: [brownfield_uncertainty, compatibility_risk]
    - all: [resource_sensitive, long_running_operation]
```

The v0.1 admission policy preserves the effective heavy boundary of the legacy Router rather than intentionally shifting those cases to `native-light`. Legacy natural-language triggers are normalized into the stable IDs above, and the migration fixture records each mapping. Removing or weakening an existing trigger is a future policy migration that requires an ADR, a profile version change, and explicit old-versus-new routing golden cases.

The Router consumes the same compiled admission policy as the adapter. It may revalidate decision identity, matched rule IDs, signal IDs, task state, pinned digests, and approval, but may not maintain a second independent signal list.

## 19. Route Decision Contract

```yaml
schema_version: 1
decision_id: decision-uuid
decision_digest: sha256-value
operation: create-task
requested_task_ref: .trellis/tasks/001-feature
task_ref_precondition: absent
intent_id: feature-intent-id
intent_digest: sha256-value
approval_challenge: random-256-bit-value
route: speckit-superpowers
project_id: stable-project-uuid
workspace_instance_id: clone-local-uuid
manifest_generation: 7
manifest_digest: sha256-value
profile_digest: sha256-value
lock_digest: sha256-value
artifact_bundle_digest: sha256-value
policy_digest: sha256-value
platform: codex
adapter_id: codex
adapter_version: 1.0.0
task_state_digest: sha256-value-or-null
router_contract_version: 1
entry_owner: heavy-development-router
matched_rule_ids: []
signals: []
reasons: []
task_creation_approval: required
```

For a task-creating decision, the caller supplies a normalized proposed task ref plus a Task Intent document; the CLI validates the ref and computes `intent_digest`. The intent schema includes stable intent identity, title, concise objective, requested mode if explicit, acceptance summary, and the candidate signal IDs. The caller cannot substitute a different task ref, intent, or operation during admission. Classification-only decisions use `operation: classify-only` and omit task-creation fields.

The issuer generates a fresh cryptographically random 256-bit approval challenge, normalizes the payload excluding `decision_id` and `decision_digest`, derives `decision_id` as UUIDv5 over the payload hash in the fixed Agent Workflow Pack route namespace, and then computes `decision_digest` over the normalized payload plus derived ID. Policy evaluation remains deterministic, but each task-creation decision envelope is unique because the challenge is unique. Explanatory reasons participate in the digest but never alter policy evaluation.

`task_state_digest` covers the canonical non-archived-task scan, active pointers, modes, lifecycle revisions, pinned contract digests, and the requested task-ref absence precondition observed at decision time; it is null only for a classification-only project with no task-state inputs. Staging under `.agent-workflow/local/` does not alter this digest. Any intervening admission, transition, archive, pointer change, or creation of the requested ref makes the decision stale.

This decision is not authenticated by a secret signature. Its enforcement comes from independent reproducibility: every loader reads the current authorities, recomputes both identities, reruns the compiled policy over the supplied stable signal IDs, and requires exact agreement on route, matched rules, entry owner, task state, adapter version, and approval requirement. A hand-written, modified, stale, or copied decision cannot bypass the loader even if it is syntactically valid.

Task-creation approval and implementation activation are separate gates. The enforced platform approval mechanism returns a one-time proof binding approval ID, approval challenge, Route Decision digest, task ref, intent digest, operation, workspace instance, actor, time, and verifier ID/version. `task admit` accepts no free-form override for those fields and records the verified proof in revision 1. The proof may be consumed only by one task-admission transaction; recovery may continue that same transaction but may not apply it to another ref. Implementation activation belongs in the heavy branch after the task exists.

Conflicting explicit selection and pinned task mode blocks. Multiple active tasks with inconsistent pointers, missing decision identity, or mismatched profile/policy/contract digests also block.

## 20. Runtime Control Plane Deployment and Exposure

Initialization materializes two managed files:

```text
.agent-workflow/
├── bin/agent-stack          # UTF-8 POSIX launcher, mode 0755
├── runtime-control.json     # pinned runtime descriptor, mode 0644
└── runtime/                 # non-discoverable workflow catalog
```

The managed launcher path is `.agent-workflow/bin/agent-stack`; its managed descriptor is `.agent-workflow/runtime-control.json`.

Generated platform wrappers invoke the repository-relative launcher and never resolve `agent-stack` from `PATH`, a user-level tool installation, or an unversioned alias. The launcher locates the repository root from its own real non-symlink path.

The descriptor is a managed artifact recorded in the Manifest and includes at least:

```json
{
  "schema_version": 1,
  "launcher_contract_version": 1,
  "pack_version": "0.1.0",
  "distribution": "agent-workflow-pack",
  "entry_point": "agent-stack",
  "wheel_url": "immutable-https-wheel-url",
  "wheel_sha256": "sha256-value",
  "source_commit": "full-40-hex-commit",
  "uv_version_policy": "release-tested-closed-range",
  "cache_policy": "offline-first-pinned-redownload"
}
```

The launcher embeds the descriptor digest and the same immutable wheel identity. Before dispatch it verifies the descriptor's byte hash, the presence and schema of the Manifest, the Manifest file record for the descriptor, the installed `pack_version`, maintenance state, and the tested `uv` version policy. The selected CLI then repeats the Manifest, descriptor, source-commit, package-version, and command-eligibility checks. Ordinary runtime commands require exact agreement among launcher, descriptor, Manifest, and running CLI.

Invocation is offline-first against the exact wheel URL plus SHA-256. On a cache miss, the launcher may retry online only when the descriptor permits pinned redownload; redirects and the final artifact remain subject to the locked URL and hash rules. This narrowly scoped bootstrap may fetch only its embedded release wheel before full CLI validation and may not fetch workflow dependencies or project-supplied URLs. Offline cache miss, missing or unsupported `uv`, hash failure, source-commit mismatch, or pack-version mismatch returns a stable runtime-bootstrap error and performs no fallback to latest, source checkout, global installation, or PATH.

A fresh clone receives the committed launcher, descriptor, Manifest, and workflow lock even though local state is absent. The launcher therefore permits `workspace register` and read-only diagnostics before local registration; other runtime and write commands remain blocked.

Every Reconciler or task transaction journal records a `recovery_runtime` containing pack version, wheel URL, wheel SHA-256, source commit, and launcher-contract version before its first target mutation. While a transaction is unfinished, the launcher ignores the ordinary descriptor for command selection and permits only read-only diagnostics plus the matching `recover` command through that journal-pinned runtime. An unfinished task transaction therefore blocks `route decide`, task loaders, and every unrelated write command. This works whether a crash occurred before or after candidate launcher files were replaced.

Launcher and descriptor changes are ordinary managed artifacts with byte-and-mode CAS, backups, and atomic rename. Compatibility metadata must prove that both the preimage and candidate launcher contracts understand the transaction's recovery-runtime schema. Manifest commit switches the normal runtime authority; pre-commit rollback restores the prior launcher and descriptor, while post-commit recovery performs cleanup only.

A forward upgrade is invoked through the exact target-release wheel using the canonical external `uvx` command. A mismatched external CLI may run only `upgrade` when a trusted compatibility edge authorizes the installed-to-running transition; all other commands fail closed. Rollback to a listed earlier release may be orchestrated by the currently installed launcher runtime. After upgrade commit, all normal wrapper calls use the newly committed descriptor.

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
- Route Decision schema, identity, digest, and deterministic policy replay;
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

Every task admitted to `trellis-native` or `speckit-superpowers` stores `.trellis/tasks/<task>/integration.yaml`. The schema is a discriminated union keyed by `mode`; common fields pin the workflow contract and task lifecycle, while only the selected mode-specific branch is legal.

Common fields are:

```yaml
schema_version: 1
mode: trellis-native # or speckit-superpowers

workflow_contract:
  version: 1
  profile_digest_at_admission: sha256-value
  lock_digest_at_admission: sha256-value
  artifact_bundle_digest_at_admission: sha256-value
  policy_digest_at_admission: sha256-value
  adapter_id: codex
  adapter_version_at_admission: 1.0.0
  route_contract_version: 1

lifecycle:
  status: active
  state_revision: 12
  admitted_at: 2026-07-13T15:00:00Z
  archived_at: null
  blocked_reason: null
  last_transition: {}

admission:
  operation: create-task
  task_ref: .trellis/tasks/example
  intent_id: feature-intent-id
  intent_digest: sha256-value
  task_transaction_id: task-transaction-uuid
  candidate_tree_digest: sha256-value
  workspace_instance_id_at_admission: clone-local-uuid
  route_decision_id: decision-uuid
  route_decision_digest: sha256-value
  approval_id: approval-uuid
  approval_challenge: random-256-bit-value
  approval_proof_digest: sha256-value
  approval_verifier_id: platform-approval-verifier
  approval_verifier_version: 1.0.0
  approved_by: user-actor-id
  approval_mechanism: platform-user-confirmation
  approved_at: 2026-07-13T15:00:00Z
```

The `trellis-native` branch is deliberately small:

```yaml
mode: trellis-native
trellis_native:
  task_ref: .trellis/tasks/example
```

Trellis remains authoritative for its native internal phases and artifacts. The integration file exists only to pin mode, admission-time contract, and lifecycle so resume and upgrade gates do not have to infer them.

The `speckit-superpowers` branch extends the common contract:

```yaml
mode: speckit-superpowers
speckit_superpowers:
  router_contract_version: 1
  phase: implementing
  executor_claim:
    claim_id: claim-uuid
    executor: speckit-implement
    actor: actor-id
    claimed_at: 2026-07-13T16:00:00Z
    base_revision: 11
  authority:
    active_feature: feature-id
  canonical_artifacts: {}
  reference_only_artifacts: []
  completion_flags: {}
```

The heavy branch retains `authority.active_feature`, `canonical_artifacts`, `reference_only_artifacts`, phase, completion flags, and the structured executor claim from the current custom router contract. Common lifecycle retains `last_transition` and `blocked_reason` for both modes.

`lifecycle.status` is one of `active`, `blocked`, `completed`, `archiving`, or `archived`. `blocked` requires a non-null reason. `completed` means implementation and verification are complete, but finish, journal, memory, review, publication, or Trellis archive obligations may remain. `archiving` identifies an unfinished archive transaction. The states `active`, `blocked`, `completed`, and `archiving` all remain active for safety gates; only `archived` is non-gating. Archiving records `archived_at` through the task-state mutation protocol; deleting the file is not an archive operation. Resume always uses the pinned mode and contract and never reclassifies the task.

### 21.1 Atomic Task Admission

Task creation is a Task-state Service transaction, not a prerequisite performed by Trellis or the model. Its durable journal is `.agent-workflow/task-transactions/<transaction-id>.json`; its same-filesystem staging root is `.agent-workflow/local/task-staging/<transaction-id>/`. The journal is recovery evidence, not a second task authority.

`task admit` executes this order while holding the exclusive runtime-state gate and the task-ref lock:

1. Validate the current Manifest, workspace identity, task-bound Route Decision, one-time approval proof, requested-ref absence, task-state digest, adapter contract, and all pinned runtime digests.
2. Atomically persist a `planned` journal binding the decision, approval-proof digest, intent, task ref, operation, candidate generator, recovery runtime, and every precondition. Only then create staging residue.
3. Render the complete locked Trellis task shell and `integration.yaml` revision 1 under the staging root. No direct Trellis create command may write the target project. Validate the entire tree, record every file byte hash and normalized POSIX mode, and advance the journal to `staged`.
4. Revalidate the task ref, active pointers, decision, approval, and tree digest. Atomically rename the staged task directory to `requested_task_ref`; this directory rename is the task-admission commit point.
5. Perform the locked Trellis adapter's index or active-pointer coordination, advance through `task_committed` and `cleanup_pending`, then remove staging residue and mark the journal `complete`.

The task candidate tree uses a deterministic Merkle digest over repo-relative paths, bytes, and normalized modes. To avoid self-reference, the schema excludes `admission.candidate_tree_digest` itself when calculating that digest. Revision 1 records the transaction ID and resulting digest. If the process dies after the directory rename but before the journal advances, recovery recognizes a committed admission only when the target is a real non-symlink directory, its integration state binds the same transaction ID, and its recomputed candidate-tree digest matches. Otherwise recovery blocks without deleting or replacing the target.

Admission phases are:

```text
planned -> staged -> task_committed -> cleanup_pending -> complete
```

At `planned` or `staged`, `task recover --rollback` may remove only recorded staging residue after CAS validation; the approval proof remains bound to that transaction and may be reused only by `--resume` of the same journal. At `task_committed` or later, rollback is forbidden: recovery may only finish adapter coordination and cleanup. A committed task may be archived later through a new task transaction, never erased as admission recovery.

### 21.2 Atomic Task Archive

`task archive` is the only supported archive entry for an integrated task. It requires `lifecycle.status: completed`, the locked Trellis archive adapter, no live executor claim, satisfied mode-specific completion flags, an absent normalized archive destination on the same filesystem, and the expected integration revision. Direct Trellis finish/archive commands must be hidden or gated by the adapter; otherwise `task_archive_gate` is not `enforced` and `sol56-sdd` cannot materialize that platform.

While holding the runtime-state gate and task lock, the service atomically creates an `operation: archive` journal before changing the task. The journal records the active and archive refs, source-tree digest, integration preimage, candidate states, Trellis index/pointer preimages and candidates, directories created by the operation, and recovery runtime. It then transitions the integration state to `archiving`, with the archive transaction ID and destination, before moving any task content. An unfinished archive journal or any `archiving` state remains active for every safety gate.

The adapter applies its move, index, journal, and active-pointer operations with byte-and-mode CAS and atomic replacement. The task-directory rename to the archive ref is recorded explicitly but is not by itself a completed archive. After all Trellis metadata agrees with the destination, the service atomically transitions the integration file at the archive ref from `archiving` to `archived`, sets `archived_at`, increments the revision, and records the archive transaction ID. That integration-state rename is the archive commit point; only then may the task become non-gating.

Archive phases are:

```text
planned -> state_marked -> task_moved -> metadata_applied
        -> archive_committed -> cleanup_pending -> complete
```

Before the archive commit point, validated recovery may resume or roll back the journal, including reversing a directory move only when source/destination type, tree digest, integration state, and every Trellis metadata preimage still satisfy CAS. After the commit point, recovery may perform cleanup only. If external changes make either direction unsafe, automatic recovery stops with a manual-recovery report and the task remains gating. Trellis archive indexes, task location, integration lifecycle, and active pointers may never be accepted as partially consistent success.

### 21.3 Ordinary State Mutation

Task-state mutation uses this protocol:

1. Resolve and validate the repository-relative task path and reject symlinks or a mode/schema mismatch.
2. Acquire the exclusive project runtime-state gate lock, then the task-level OS advisory lock at `.agent-workflow/local/task-locks/<task-path-digest>.lock`.
3. Recheck maintenance and unfinished task transactions, then read the complete integration file and verify its byte hash, expected `state_revision`, lifecycle status, mode, and command-specific preconditions.
4. Write the complete next state to a temporary file in the task directory, recheck the absent or existing preimage and non-symlink path type, then atomically rename it.
5. Increment `state_revision` exactly once and emit the prior and resulting state digests.

The Reconciler takes the same runtime-state gate before installing maintenance and holds it through cleanup, so task admission or mutation cannot race the post-marker active-task rescan. Lock ordering is fixed: Reconciler lock before runtime-state gate; runtime-state gate before task lock. Task commands never acquire the Reconciler lock.

For `speckit-superpowers`, `claim` is legal only in `phase: implementing` when `executor_claim` is null. It records the caller-supplied expected revision as `base_revision`; concurrent callers that observed the same revision serialize at the lock and all but the first fail CAS. `release` requires the exact claim ID and current revision. Phase transitions that require an executor reject an absent or foreign claim, and transitions out of implementation reject an unresolved claim.

Claims do not expire automatically. Stale-claim recovery requires Git state, task artifacts, journals, and execution evidence; ambiguous ownership requires user direction and a separately audited forced-release transition.

## 22. Capability Model

Capability levels are ordered:

```text
enforced > instruction-only > unsupported
```

- `enforced`: a verified hook, wrapper, plugin, or platform mechanism technically gates the supported entry path.
- `instruction-only`: compliance depends on model instructions and cannot be described as a technical guarantee.
- `unsupported`: the platform has no corresponding mechanism.

`task_admission_gate: enforced` specifically requires a mechanism that distinguishes a direct user confirmation from model-generated command input and offers no unwrapped non-interactive task-creation path. `task_archive_gate: enforced` requires all supported Trellis finish/archive paths for integrated tasks to pass through the recoverable archive transaction. A plain prompt instructing the model to ask first or use the wrapper is only `instruction-only`.

Adapter capability manifests bind claims to adapter and harness versions. Each manifest contains a platform ID, adapter version, a non-empty list of exact tested harness versions or closed tested version ranges, the measured level of each capability, the probe used by `doctor`, and the integration-evidence identifier. A range may be declared only when every boundary version and the project's compatibility policy have been tested.

Profiles declare minimum levels. Materialization succeeds only when `actual >= required` for every selected platform. The strict `sol56-sdd` profile does not downgrade. Claude Code, Codex, and OpenCode all must pass version-bound integration tests at their required levels before they remain in `default_platforms` for v0.1.

Ordinary `doctor` inspects actual harness configuration only through read-only mechanisms. For example, a Codex project hook that requires user-level feature enablement and one-time approval is not `enforced` until read-only evidence confirms both conditions; when confirmation itself would mutate state, ordinary `doctor` reports `unverified` and the explicit write-probe path must be used.

## 23. Provider and Third-party Execution Security

Provider execution security is independent of platform-adapter capabilities. Each control is assigned one policy level:

- `required`: unavailable or failed enforcement blocks execution.
- `approval-required`: unavailable enforcement blocks until the user reviews a concrete risk report and approves that one provider execution in that one saved plan.
- `best-effort`: the CLI attempts and reports the control but does not block solely because it is unavailable.

`sol56-sdd` requires temporary HOME/XDG directories, environment allowlisting, secret stripping, closed stdin, target-path isolation, time and output limits, archive/cache integrity, and baseline OS resource limits. Enforceable network isolation is approval-required. Enhanced namespace, seccomp, or container isolation is best-effort.

Before any third-party process starts, the Renderer creates a canonical provider-execution plan containing the provider and command digests, project and workspace identities, workflow-lock digest, input digests, requested controls, measured isolation gaps, and a prospective transaction ID. An `approval-required` exception binds to that provider-plan digest, not to a final reconcile plan that cannot yet exist. The initializer result, approval record, sanitized diagnostics, and output digests then become inputs to the final reconcile plan, which still requires its separate apply approval.

An approval is valid for exactly one provider-execution plan, provider version, workspace instance, and prospective transaction identity. It is not reusable by another render, target project, or changed command and cannot become a persistent silent downgrade. Planning with such approval still performs no target-project writes.

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

Pinned initializer identity does not by itself make output deterministic. Each materializing initializer has a lock-bound output contract containing the exact command and argument vector, normalized input digests, locale, timezone, environment allowlist and fixed values, umask and mode policy, file-order policy, renderer/adapter version, and expected candidate content-root digest. Release execution fixes locale and timezone, prevents ambient clock, random, hostname, user, temporary-path, and filesystem-enumeration values from entering managed output, or applies only an explicitly schema-defined deterministic normalization before validation.

Release CI runs every locked initializer at least twice in independent clean temporary roots and requires identical validated content-root digests. Runtime rendering compares the validated candidate root with the digest bound by the workflow lock and artifact bundle. A mismatch is `AWP_INITIALIZER_NONDETERMINISTIC`, blocks materialization, and cannot be accepted as an ordinary upgrade diff; changing expected output requires a new reviewed lock or artifact bundle.

For a downloaded archive, the Provider enforces the compressed-download size ceiling while streaming and computes the hash over the complete archive bytes. The resulting hash must match the workflow lock before format detection, member enumeration, decompression, or extraction begins. Exceeding the download limit before hash completion aborts and rejects the object; a partial hash is never sufficient.

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
- architecture or subsystem changes entering heavy mode;
- new dependencies or external integrations entering heavy mode;
- standalone resource or large-data risk entering heavy mode;
- reproducibility, provenance, or governance requirements entering heavy mode;
- acceptance criteria whose ambiguity blocks safe implementation entering heavy mode;
- explicit Trellis-native intent versus merely mentioning Trellis;
- direct `/speckit.implement` bypass attempts;
- a model-authored or non-interactive task-creation approval bypass attempt;
- leaf-skill gated-reference leakage;
- instruction-only capability failing an enforced profile requirement;
- native-light small fixes;
- multi-module contract changes;
- active heavy-task resume;
- stale, copied, or field-tampered Route Decisions.

Natural-language classification evaluation may be added later as a non-blocking eval suite.

## 26. Test Strategy

### 26.1 Schema, Canonicalization, and Property Tests

Test duplicate YAML keys, inheritance cycles, unknown fields, JCS digests, set sorting, Merkle inputs, path normalization, POSIX-mode normalization, marker parsing, release-compatibility edges, and manifest generations. Property/fuzz tests target path normalization, archive extraction, URL handling, and marker parsers.

### 26.2 Resolver and Policy Tests

Test dependencies, conflicts, stable IDs, capability ordering, route rules, and source-of-truth separation.

### 26.3 Golden Rendering

Snapshot Claude Code, Codex, and OpenCode output. Verify route-gated runtime content is absent from auto-discovery paths. Execute each locked initializer twice in independent isolated roots and compare both runs with its lock-bound content-root digest.

### 26.4 Reconciler Tests

Use temporary projects to test every ownership class, protected paths, symlink refusal, byte-and-mode CAS, executable-bit changes, repair, overlay retirement, launcher/descriptor atomic replacement, transaction-created directory cleanup, fresh-clone workspace registration, cross-clone saved-plan refusal, saved-plan staleness, read-only `doctor`, explicit write-probe cleanup and interruption, filesystem capability refusal, and no-write conflict behavior.

### 26.5 Crash and Concurrency Tests

Inject process termination at each Reconciler, task-admission, and task-archive phase. Test two CLI writers, two admissions for one task ref, two claimants at the same revision, task mutation against maintenance admission, admission crash immediately before and after the task-directory rename, archive crash around the directory move and integration commit, task-transaction blocking, cache contention, external byte or mode modification immediately before rename, manifest-committed cleanup, and CAS rollback refusal.

### 26.6 End-to-end Sequence

```text
init
  -> doctor
  -> test-routing
  -> no-op sync
  -> route decide + direct approval
  -> injected task-admission crash + task recover
  -> drift conflict
  -> assert zero writes
  -> injected crash during apply
  -> doctor reports recovery-required
  -> recover --resume / recover --rollback
  -> active-task upgrade block
  -> mark task completed
  -> assert completed task still blocks upgrade
  -> injected task-archive crash + task recover
  -> archive task completely
  -> approved upgrade
```

A sanitized, synthetic snapshot derived from the current sibling `workflow-pack` structure is committed under `tests/fixtures/`. It preserves the relevant Trellis, router, skill, and ownership-conflict shapes without copying personal journals, local developer identity, caches, or unrelated documents. Tests prove that `.trellis/tasks/`, `.trellis/workspace/`, `.trellis/spec/`, and Spec Kit feature artifacts are not claimed at directory scope.

## 27. Packaging and Release

Build and test both wheel and sdist. Installation tests run from the built artifacts, not only from a source checkout. Package-data tests verify inclusion and exact digests of profiles, catalogs, schemas, compatibility metadata, runtime-launcher templates, artifact definitions, overlays, custom skills, licenses, and notices.

The sdist contains the same vendored runtime sources as the wheel. Release CI builds both artifacts in the `uv.lock`-controlled build environment and verifies that the wheel metadata has an empty external runtime `Requires-Dist` set. Build-system dependencies remain build-time concerns and are not represented as consumer runtime reproducibility.

Cross-distribution rendering compares a `distribution_render_digest`: the deterministic Merkle root of managed artifact paths, rendered bytes, normalized modes, and profile/lock/artifact-bundle-derived content. It excludes Manifest generations, project and workspace UUIDs, target-path identities, transaction IDs, approval evidence, maintenance state, probe evidence, and ignored local state. Tests that compare a complete plan or tree must inject a deterministic identity provider; AC-14 does not require independently generated runtime identities to be byte-equal.

The canonical end-user `uvx` command installs the exact wheel asset of a verified immutable GitHub release. Release metadata binds that immutable release and asset hash to the actual full 40-hex source commit SHA. A source-audit command may use the full commit SHA directly, but release acceptance must execute the built wheel and sdist rather than relying only on a source checkout. A movable ordinary tag is never a trust anchor.

Release gates require:

- wheel, sdist, and Git-checkout `distribution_render_digest` values are identical;
- all default platforms meet their profile-required capability levels;
- a clean WSL/Linux environment initializes from the published artifact;
- a fresh clone runs `workspace register` and `route decide` through the project launcher with cache-hit, permitted pinned-redownload, offline-miss, hash-mismatch, version-mismatch, and unfinished-transaction recovery cases;
- every initializer produces its lock-bound content-root digest in two independent clean runs;
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
  license_expression: AGPL-3.0-only
  modified: true
```

This applies to Trellis overlays, projected skills, agents, commands, hooks, and initializer-generated files when they contain copyrightable upstream content. At the upstream commits reviewed for v0.1, Superpowers and Spec Kit use the SPDX expression `MIT`, while Trellis uses `AGPL-3.0-only`; release automation must revalidate the exact pinned upstream license text and metadata rather than inheriting these values by component name. Derived content retains the applicable full notice and modification statement.

`THIRD_PARTY_NOTICES.md` is generated from lock and provenance metadata and tested for completeness. Target-project materialization includes the notices required for the third-party content actually projected there.

Vendored Python runtime code is third-party content, not first-party merely because it is packaged inside the wheel. Each vendored file maps to an exact source artifact, version, source hash, SPDX expression, modification status, and full license text.

## 29. Legacy Migration Requirements

The current custom skills are migration inputs, not automatically valid release artifacts.

- `heavy-development-router` must be repackaged with a complete `references/` directory containing its routing policy, integration schema, heavy-workflow contract, Trellis overlay, and replacement matrix.
- Every reference named by `SKILL.md` must exist at the locked path and participate in the runtime-entry digest.
- The current string `active_executor` contract migrates to `state_revision` plus the structured `executor_claim` object.
- Existing integrated tasks, if supported by a later migration tool, require an explicit schema migration plan; v0.1 may otherwise block and require completion under the old contract.
- The current Trellis-generated `.trellis/workflow.md`, adapters, hooks, agents, and skills are evidence for definitions and fixtures, not files to copy wholesale.
- The synthetic legacy fixture must cover missing router references, broad Trellis skill discovery, user-modified workflow blocks, active tasks, journals, and protected Spec Kit artifacts without containing personal data.

## 30. v0.1 Acceptance Criteria

- **AC-01:** A clean WSL/Linux target initializes through `uvx` from the exact self-contained wheel asset of a verified immutable release whose metadata identifies the full source commit SHA and asset hash; the corresponding sdist builds the same self-contained runtime and passes the same installation scenario.
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
- **AC-12:** Every non-archived heavy task blocks contract-changing upgrade; affected non-archived Trellis-native tasks also block.
- **AC-13:** Disabled or gated pack-managed skills are neither auto-discoverable nor transitively referenced by discoverable leaves.
- **AC-14:** Wheel, sdist, and Git-checkout renders have identical `distribution_render_digest` values over managed profile/lock/bundle-derived output; clone-local and transaction identities are excluded.
- **AC-15:** Provenance, full licenses, notices, lock hashes, and target notices are complete for every projected third-party artifact.
- **AC-16:** JSON output, exit codes, and redaction pass their versioned contract tests.
- **AC-17:** The legacy `workflow-pack` migration fixture retains all protected Trellis and Spec Kit runtime state.
- **AC-18:** `upgrade --to` rejects every target absent from the explicit directed compatibility matrix and never launches an older CLI against current state.
- **AC-19:** File-state CAS detects byte, type, symlink, and POSIX-mode changes, including executable-bit drift.
- **AC-20:** Write commands refuse filesystems that fail advisory-lock, atomic-replace, mode, or path-collision probes; `/mnt/*` receives no implicit exemption.
- **AC-21:** Concurrent executor claims at one base revision result in exactly one successful atomic state transition.
- **AC-22:** A model-generated Route Decision or command flag cannot satisfy the enforced user approval required by `task admit`.
- **AC-23:** A fresh clone must register a new local workspace identity before writes, and a saved plan from another clone is rejected by default.
- **AC-24:** A fresh clone can execute `workspace register` and `route decide` through the managed version-pinned launcher; cache miss, wheel-hash mismatch, source/pack-version mismatch, or unavailable offline runtime fails closed without PATH or latest-version fallback.
- **AC-25:** Route Decisions and approval proofs bind one task ref, intent, operation, workspace, and one-time challenge. The task shell and integration revision 1 commit through one atomic directory rename; every admission or archive crash point is diagnosable, recoverable under CAS, and blocked from becoming a partially accepted task state.
- **AC-26:** Ordinary `doctor` and every `--dry-run` perform zero target writes. Filesystem mutation probes run only through explicit `doctor --write-probe` or inside an approved apply transaction after lock acquisition, and interrupted probe residue is tracked and safely recoverable.
- **AC-27:** A `completed` but non-archived task remains gating; only a fully committed `archived` lifecycle state permits an otherwise compatible contract-changing upgrade.
- **AC-28:** A locked initializer whose candidate content-root digest is unstable or differs from its lock-bound contract blocks both release and runtime materialization rather than becoming a silent file diff.

## 31. Implementation Decomposition

The approved design should be implemented through separate feature specs, in this order:

1. **Core schemas and Resolver** — profiles, catalog, locks, canonicalization, artifact definitions, IR, policy graph, and diagnostics.
2. **Providers and secure cache** — acquisition, isolation, verification, extraction limits, provenance, and cache concurrency.
3. **Renderer and Reconciler** — staging, ownership, plans, OS lock, CAS, transactions, repair, and recovery.
4. **Runtime launcher and Task-state Service** — pinned launcher delivery, workspace registration, integration union, task locks and CAS, claims, admission/archive transactions, recovery, and maintenance coordination.
5. **Route admission and Platform Adapters** — compiled admission policy, Route Decisions and approval proof, runtime catalog and loaders, capability probes, adapter projection, and platform golden output.
6. **Lifecycle, packaging, and release** — CLI commands, JSON contracts, upgrade flow, E2E tests, artifact builds, immutable trust anchors, and notices.

Each feature spec must preserve the authority boundaries and acceptance criteria in this document. No feature spec may introduce a second planner, executor, route-policy source, ownership source, or task-state source.

## 32. Design Risks

- Strict enforcement may delay a platform's inclusion in `default_platforms`; the profile must not silently downgrade.
- Third-party initializer execution remains higher risk than static extraction even with isolation; the capability report must remain honest.
- WSL-mounted filesystems may provide weaker durability semantics; v0.1 promises process-crash recovery only.
- Upstream platform and Trellis templates may change paths or hook behavior; adapter and harness versions therefore remain locked and tested.
- Trellis-derived overlays and generated content require artifact-level provenance and license handling rather than a repository-wide assumption.

All third-round written-spec review blockers have been incorporated. The document has passed the local spec self-review and remains awaiting explicit user approval; implementation planning is prohibited until that approval.

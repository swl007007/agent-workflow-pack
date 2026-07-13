# Agent Workflow Pack v0.1 Design

**Status:** Changes required
**Review gate:** Incremental protocol errata applied; awaiting reviewer confirmation before approval or implementation decomposition
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
- Support safe `init`, `sync`, `sync --repair`, `upgrade`, `workspace register`, `workspace migrate`, `doctor`, `test-routing`, and transaction recovery.
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
- Transparent resume of a non-archived task after its checkout pulls a different local-state release contract, or migration of Trellis task/layout state between changed discovery contracts. v0.1 requires recovery, completion, and archive under the source release plus an empty-or-preserved layout-state check before workspace migration; multi-version retained-runtime resume and task-layout migration are deferred to v0.2 or later.
- Treating a same-user-writable checkout, including its project launcher, as a hostile-code execution sandbox or trusted verification root.
- Distributed task coordination or detection of active workflow state that exists only in another unsynchronized clone or branch.
- Providing legal advice; the repository supplies engineering provenance and notices only.

## 4. Core Authority Model

Each state dimension has one scoped authority.

| Authority | Sole responsibility |
|---|---|
| `profiles/*.yaml` | Activation intent, route-admission policy selection, workflow ownership selection, platform defaults, and required capability levels |
| `release/trust-policy.yaml` | Allowed GitHub host and exact owner/repository, immutable-release requirement, release-tag derivation, manifest asset name, and redirect-host policy |
| Detached immutable-release `release-manifest.json` | Distribution asset URLs, byte sizes and SHA-256 hashes, source commit, Release Identity, and the exact trust-policy, workflow, artifact, schema, migration, compatibility, and launcher bundle digests for one published release |
| Release `workflow.lock` | Default locked workflow supply chain shipped with one CLI release |
| Target `.agent-workflow/workflow.lock` | Project-scoped workflow supply-chain identity used by `sync` |
| `compatibility/releases.yaml` | Explicitly supported release-transition edges, target Release Identity and bundle identities, schema and artifact migrations, and v0.1 task-state transition prohibitions; never distribution-container hashes |
| `artifact-definitions/*.yaml` | Manageable target paths, ownership class, merge strategy, stable markers, validators, and additional forbidden paths |
| Locked Trellis adapter task-layout contract | The bounded task hierarchy and segment grammar, active/archive roots, integration recognition, metadata parser/classifier semantics, task-journal discovery and phase classification, scan limits, and exact or schema-bounded metadata paths eligible for task transactions |
| Global protected-path policy | Paths no artifact definition may target or relax |
| `.agent-workflow/manifest.json` | What was actually materialized, the applied baselines and hashes, selected profile, digests, generation, and last committed transaction |
| `.agent-workflow/local/workspace.json` | Non-Git identity of the current working copy plus the last locally applied release, detached-manifest digest, Trellis-layout snapshot, and aggregate workspace/replay/outbox contract |
| `.agent-workflow/local/approval-replay.json` | Workspace-local reservation and consumption state for one-time task-admission approval proofs |
| `<locked active-or-archive task ref>/integration.yaml` | Pinned mode, workflow contract, and lifecycle of one admitted integrated task; the mode-specific branch is also authoritative for heavy-router phase, owners, artifacts, and executor claim when applicable |

A profile may select a versioned artifact policy, but it cannot expand the paths authorized by artifact definitions. A manifest records prior application state but cannot authorize a future write that current definitions prohibit.

Task transaction journals are recovery evidence, and `.agent-workflow/local/task-outbox/**` is a non-authoritative delivery queue. Neither may independently change task lifecycle, approval-consumption state, routing, ownership, or acceptance; those outcomes must already be committed in the authority named above.

After cross-ownership validation, the Task-state Service receives temporary transaction-scoped CAS authority over the current task's integration file, task-shell move, and the exact expanded Trellis metadata candidates recorded in that task journal. This exception does not transfer ownership, authorize pack-managed content, or permit writes to any unplanned path.

Ordinary approval-replay transitions and task-outbox mutations are Task-state-Service-only. The only additional local-state writers are the approved first-init Reconciler transaction, the workspace-registration transaction, and an explicitly authorized compatibility-edge migration. Those exceptions are limited to the exact workspace, replay-ledger, and outbox paths and candidate states recorded in their own journals; they do not grant general artifact ownership or permit deletion-and-recreation as a migration strategy.

## 5. Planned Repository Structure

```text
agent-workflow-pack/
├── pyproject.toml
├── uv.lock
├── workflow.lock
├── release/
│   └── trust-policy.yaml
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

`schemas/` contains versioned schemas for profiles, catalogs, workflow locks, release identity and detached manifests, release compatibility, runtime-control descriptors and caller-context envelopes, artifact definitions, manifests, lifecycle and workspace transactions, acyclic saved reconcile plans, provider-execution plans, direct-human approval branches and attempt journals, Desired State IR, route decisions, integration state, workspace-local state, approval-replay ledgers, task-outbox items, diagnostics, capability manifests, and provenance records. Workspace-local state, replay ledgers, outbox items, and workspace transactions are separate schema domains with independent schema IDs and versions.

`release-manifest.json` is a release-CI output published beside the wheel and sdist; it is deliberately absent from the wheel, sdist, and source tree. Only its schema and the trust policy are packaged.

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

The Task-state Service is the sole supported writer of an admitted task's integration file at its locked active or archive ref. It is a runtime-state writer, not part of the Reconciler, and has no authority over pack-managed files. During admission or archive it may also write only the exact cross-ownership-validated Trellis metadata candidates recorded in the current task transaction. Platform adapters and runtime agents call its CLI instead of editing integration or metadata state directly.

### 6.6 Lifecycle Service

The Lifecycle Service orchestrates installation-state commands and transactions but contains no independent routing or ownership policy. Lifecycle read-only and write commands that evaluate desired state consume the same Resolver implementation and IR schema; Task-state Service mutations use their separate state-machine contract.

### 6.7 Platform Adapters

Adapters project resolved policy into the native files, hooks, agents, commands, and skill directories of Claude Code, Codex, and OpenCode. An adapter may not add routes, signals, owners, or capabilities absent from the resolved IR.

### 6.8 Runtime Launcher

The Runtime Launcher is a managed, on-demand bootstrap path for the Task-state Service, canonical route calculator, diagnostics, recovery, workspace registration, and clone-local workspace migration. It is not a daemon and retains no independent policy. It selects only the exact runtime identity authorized by the committed Manifest or a verified candidate allowlist, then the selected CLI independently revalidates those authorities before executing a command.

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
  provider_exception_approval: enforced
  project_skills: instruction-only
approval_policy:
  direct_human_actor_required: true
  max_ttl_seconds: 900
  max_clock_skew_seconds: 60
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

Every distribution form computes the same non-self-referential Release Identity:

```text
release_id = SHA256(JCS({
  repository_id,
  distribution_name,
  version
}))
```

`repository_id` is the normalized host/owner/repository fixed by the trust policy. `distribution_name` is the Python project/distribution identity `agent-workflow-pack`, not the wheel, sdist, or Git source form. The Release Identity contains no source commit, wheel, sdist, archive, detached-manifest, bundle digest, URL, or byte-size field. This intentionally allows the ID to be committed inside compatibility metadata without depending on the Git commit or any bytes that contain the ID. A Git checkout, wheel, and sdist compute it from the same repository identity, `distribution_name`, and version. The detached manifest then binds that logical release to the exact source commit, bundle roots, and distribution-container hashes; publishing a second artifact set for the same version is forbidden by the immutable-release policy.

The detached manifest has at least:

```json
{
  "schema_version": 1,
  "release_id": "sha256-release-identity",
  "version": "0.1.1",
  "repository": {
    "host": "github.com",
    "owner": "pinned-owner",
    "name": "agent-workflow-pack",
    "tag": "v0.1.1",
    "immutable_release_required": true
  },
  "source_commit": "full-40-hex-commit",
  "bundles": {
    "trust_policy": "sha256-value",
    "workflow_lock": "sha256-value",
    "artifact": "sha256-value",
    "schema": "sha256-value",
    "migration": "sha256-value",
    "compatibility": "sha256-value",
    "launcher": "sha256-value"
  },
  "assets": {
    "wheel": {
      "name": "agent_workflow_pack-0.1.1-py3-none-any.whl",
      "url": "immutable-release-asset-url",
      "size": 123456,
      "sha256": "sha256-value"
    },
    "sdist": {
      "name": "agent_workflow_pack-0.1.1.tar.gz",
      "url": "immutable-release-asset-url",
      "size": 123456,
      "sha256": "sha256-value"
    }
  }
}
```

The v0.1 trust root is `github-immutable-release-v1`: the trusted current CLI derives the manifest location from `release/trust-policy.yaml`, uses HTTPS and the GitHub release API, verifies the exact host/owner/repository/tag, requires the release to be immutable, restricts redirect hosts, and retrieves the fixed manifest asset by the policy-defined name. Neither a target project nor a transaction may supply or override that URL. The fetched manifest byte digest is computed externally and recorded for later offline use; the digest is not stored inside the manifest itself.

v0.1 does not support trust-root rotation through an ordinary upgrade. Every candidate must reverify under the currently committed trust-policy bytes and retain both the same policy ID and content digest. Repository transfer, host change, policy-content change, or a future signing/attestation policy requires a separately designed transition authorized by the old trust root.

Bundle digest domains are schema-defined and non-overlapping. They exclude distribution containers and the detached manifest. The compatibility bundle may name logical Release Identities but cannot contain its own digest or a source-commit field for the release that contains it. The launcher bundle covers release-neutral templates, schemas, and verifier logic; it excludes the rendered project descriptor and launcher substitutions derived from the detached manifest. Release CI rejects any bundle reference graph with a digest cycle.

`sync` consumes only the existing project lock and cannot modify it. `upgrade` creates a candidate lock, fetches and verifies its content, generates a candidate IR, and presents supply-chain, routing, and file differences before approval. A release transition is legal only when the runtime that owns the migration for that direction contains an exact directed edge from the current installed release to the requested target and identifies every required schema, artifact, and task-contract migration. A verified candidate release owns an installed-to-candidate forward edge; the currently installed newer release owns any supported edge to an earlier target. An immutable source release is never required to predict a future release's bundle identities.

```yaml
schema_version: 1
release: 0.1.1
transitions:
  - from: 0.1.0
    to: 0.1.1
    target_release:
      release_id: sha256-release-identity
      version: 0.1.1
      trust_policy_digest: sha256-value
      workflow_lock_digest: sha256-value
      artifact_bundle_digest: sha256-value
      schema_bundle_digest: sha256-value
      migration_bundle_digest: sha256-value
      launcher_bundle_digest: sha256-value
    manifest_schemas: {from: 1, to: 1}
    workflow_lock_schemas: {from: 1, to: 1}
    integration_schemas: {from: 1, to: 1}
    task_transaction_schemas: {from: 1, to: 1}
    local_state_contracts: {from: sha256-value, to: sha256-value}
    trellis_task_layouts: {from: sha256-value, to: sha256-value}
    workspace_state_schemas: {from: 1, to: 1}
    approval_replay_schemas: {from: 1, to: 1}
    task_outbox_schemas: {from: 1, to: 1}
    artifact_migration_id: identity-v1
    workspace_state_migration_id: identity-v1
    workspace_state_migration_digest: sha256-value
    approval_replay_migration_id: identity-v1
    approval_replay_migration_digest: sha256-value
    task_outbox_migration_id: identity-v1
    task_outbox_migration_digest: sha256-value
    migration_digest: sha256-value
```

Edges are directed; reverse support requires its own entry. Each edge binds the target logical Release Identity and expected trust-policy, workflow-lock, artifact, schema, migration, and launcher bundles, but never a source commit, its own compatibility-bundle digest, or a distribution-container URL or hash; `target_release.version` must equal `to`. It also declares the from/to aggregate local-state contract digests, Trellis task-layout digests, integration and task-transaction schema versions, and schema versions for every persistent project and workspace state domain used by the transition. A changed workspace, replay-ledger, or task-outbox schema requires an explicit migration ID and digest. An unfinished task transaction blocks every v0.1 transition that would change its release or schema contract; no compatibility edge may migrate or continue it under a different runtime. No transition may reset or silently recreate local state to avoid a migration. The detached manifest independently binds the source commit and the digest of the compatibility bundle containing the edge. An edge never implies compatibility with an unlisted patch, minor, or historical version.

v0.1 compatibility edges do not authorize transparent resume of non-archived tasks and do not contain a retained-runtime witness. A workspace migration is legal only after every checkout-visible task transaction is complete, every discovered task is fully archived, and the Section 9 layout-preservation check proves that no source-only or target-only task, archive, pointer, index, or other metadata state would be stranded. Content-addressed retained catalogs, multi-version wrappers, resume witnesses, old-contract loader branches, and true Trellis task-layout migration are deferred to v0.2 or later.

Compatibility-edge local-state migration runs only inside the approved lifecycle transaction while the Reconciler lock and exclusive runtime-state gate are held. Planning enumerates the exact `workspace.json`, `approval-replay.json`, and existing task-outbox item paths, rejects symlinks or unexpected additions, and derives each candidate through the verified migration identified by the edge. The lifecycle journal records every local path's schema ID/version, complete byte-and-mode preimage, candidate bytes and digest, and original absence or existence condition. Local candidates are applied before Manifest commit with per-path CAS. Before that commit, rollback restores every matching preimage or removes only a transaction-created candidate whose recorded precondition was absence; after commit, the new Manifest establishes the new local-state schema contract and recovery may only finish cleanup. A migration failure, partial path set, unexpected concurrent state, or candidate validation error blocks the upgrade and may never be converted into an empty ledger, empty outbox, or newly registered workspace.

That lifecycle migration covers only the working copy executing `upgrade`; ignored local state is neither committed nor propagated to other clones. A registered clone that later pulls the new Manifest uses the independent `workspace migrate` protocol in Section 14.12. The current committed launcher/runtime must contain a verified compatibility edge from that clone's recorded source local-state release and contract to the pulled target Manifest contract; absent support fails closed rather than treating the clone as fresh or rewriting empty state. Both same-clone lifecycle upgrade and clone-local migration invoke the single Section 9 `scan_task_quiescence` contract over the verified source and target layouts and schemas, but the scanner returns facts rather than command policy. `workspace migrate` applies the strict all-non-archived gate in Section 14.12; lifecycle commands apply the operation/mode/candidate-impact policy in Section 17. Recovery, completion, and archive occur only after restoring the project checkout/release matching the source task contract; neither lifecycle migration nor `workspace migrate` rewrites, resumes, or migrates Trellis task/layout state.

The source release is identified only by the validated `workspace.json` release ID, version, detached-manifest digest, and recorded Trellis-layout digest. Source inspection has two independent evidence stages. Relationship evidence verifies the immutable detached manifest, Release Identity, and compatibility bundle needed to classify the directed release graph. Discovery evidence then treats the hash-verified source wheel solely as a data archive and loads the complete Trellis layout, integration schemas, metadata parser/classifier declarations, and task-transaction journal schemas and phase tables needed to interpret checkout state. The static inspector applies the Section 23 download, path, count, size, collision, and compression protections, recomputes every declared bundle root, and never imports, builds, or executes source-release code.

The current trust policy derives every source immutable-release locator from the recorded version and repository identity. Ordinary `doctor` uses only already verified cached evidence; `workspace migrate` may fetch and cache the exact trusted source release before target-project mutation. Missing relationship bytes leave the relationship unknown and report `AWP_WORKSPACE_SOURCE_METADATA_REQUIRED`. Missing discovery bytes do not erase an already verified relationship but prevent task scanning. An unknown parser/classifier or unsupported discovery schema makes discovery evidence `unsupported` and task quiescence `ambiguous`; it does not prevent an already verified reverse edge from reporting `ahead`. A manifest, asset hash, Release Identity, compatibility/schema bundle-root, or other cryptographic trust mismatch is `AWP_SOURCE_RELEASE_VERIFICATION_FAILED` in exit category 30, never `AWP_WORKSPACE_SOURCE_METADATA_REQUIRED`. The same code/category applies when hash-authenticated relationship or compatibility bytes fail their closed schema or semantic validation; that state is `relationship_evidence: invalid`. Authentic but structurally invalid discovery metadata is independently discovery-invalid/layout-ambiguous rather than a fabricated graph result.

The default `upgrade` target is the release of the exact CLI currently executing the command. For a forward upgrade launched from an older project runtime, `--to` is only a trust-policy-bound candidate locator: the committed runtime verifies the target detached manifest, downloads the exact wheel named there, checks its full byte hash and size, and only then reads static identity and compatibility metadata from the verified archive. The candidate must contain the complete installed-to-candidate edge and describe itself as `target_release`; its internal Release Identity and every parsed bundle must match both the detached manifest and that edge before candidate code executes. For a supported transition to an earlier release, the currently executing newer runtime must contain the complete edge and performs the migration without executing the older CLI against newer state.

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

Workflow-component network requests require a trusted lock source. In an initialized project, the manifest and project-lock digests must agree before such a request. Release-asset requests instead require the packaged release trust policy and a verified detached release manifest. In a migration project without a valid manifest, project-supplied locks, manifests, journals, and URLs are never trusted for downloads; only the current immutable CLI release and its packaged trust policy may authorize acquisition.

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

The locked Trellis adapter declares its task layout instead of relying on an upstream path assumption:

```yaml
trellis_task_layout:
  schema_version: 1
  adapter_id: trellis-v0.1
  adapter_version: 1.0.0
  runtime_namespace: .trellis
  active_root: .trellis/tasks
  archive_root: .trellis/tasks/archive
  task_discovery:
    hierarchy: one-segment
    segment_grammar_id: safe-nfc-segment-v1
    integration_relative_path: integration.yaml
    integration_schema_id: agent-workflow.integration
    integration_schema_versions: [1]
    unknown_root_entry_policy: block
    allowed_non_task_entries: []
    max_scan_depth: 1
    max_tasks: 10000
    max_root_entries: 10000
    max_integration_bytes: 1048576
  metadata_contracts: []
  task_transaction_discovery:
    root: .agent-workflow/task-transactions
    filename_grammar_id: uuid-json-v1
    schema_id: agent-workflow.task-transaction
    schema_versions: [1]
    phase_classifier_id: task-transaction-phase-v1
    phase_classifier_version: 1
    task_id_field: /task_id
    task_ref_fields: [/task_ref]
    terminal_phases: [complete]
    max_journals: 10000
    max_journal_bytes: 1048576
```

`trellis_task_layout_digest = SHA256(JCS(normalized_trellis_task_layout))`. The normalized object is the closed field set shown above plus the closed metadata-contract union described below, after set-semantic declarations are sorted; it contains no diagnostics or discovered paths. Unknown fields are schema errors. `runtime_namespace` is a locked Trellis-owned repository-relative root. `active_root` and `archive_root` must be strict descendants of it, must resolve as real non-symlink directories when present, and may not escape into another project namespace. The Resolver requires the archive root to be explicitly partitioned from active-task enumeration even when nested, derives protected globs for both roots, and includes the complete discovery, metadata, and task-journal contract in the adapter and artifact-bundle digests.

`safe-nfc-segment-v1` is an algorithm identified by the schema bundle, not an adapter-supplied regular expression. It accepts one NFC-normalized path segment of 1 through 128 UTF-8 bytes, rejects `.`, `..`, `/`, `\\`, NUL, C0/C1 controls, leading or trailing whitespace, and trailing dot, and requires case-folded and Unicode-normalized uniqueness within the scanned partition. `uuid-json-v1` accepts only a lowercase canonical UUID followed by `.json`. The `one-segment` hierarchy means a task ref is exactly `active_root/<segment>` or `archive_root/<segment>`; nested task refs and additional directory levels are invalid. A new task ref must be in the active partition and outside the archive partition.

A discovered task is a real non-symlink directory at that exact depth whose declared integration path is a regular non-symlink file within the byte limit and valid under one listed integration schema version. A grammar-matching directory with missing, oversized, malformed, or unsupported integration state remains visible as a `layout-ambiguous` finding rather than disappearing from enumeration. Declared nested partition roots such as `archive_root` and entries in `allowed_non_task_entries` are the only exceptions to `unknown_root_entry_policy: block`; every other file, directory, symlink, excess-depth entry, or case/Unicode alias at a scanned root produces the corresponding unknown-entry, collision, or limit finding. Missing declared roots are canonical empty state, while a present root of the wrong type produces a layout-ambiguous finding. Count and byte limits are hard bounds: exceeding them produces a limit finding and never truncates the scan. Only `evaluate_task_gate` converts those findings into command blockers.

`metadata_contracts` contains every index, active pointer, session journal, or other Trellis metadata object participating in discovery, admission, or archive; it may be empty only when adapter tests prove the locked Trellis version has none. Each entry is a closed `exact` or `bounded` path branch and binds a stable contract ID, path or bounded root, segment-grammar ID where applicable, maximum depth and match count, schema ID and allowed versions, safe parser ID/version, semantic classifier ID/version, semantic role, normalized task-ref field projections, maximum bytes, whether absence is canonical empty, and the classifier's canonical-empty state ID. Arbitrary globs, free-form regular expressions, recursive wildcards, runtime-selected roots, and executable parser callbacks are invalid. Parser/classifier IDs select allowlisted deterministic logic and declarative schemas from the verified schema bundle; source-release code is never imported or executed.

When the list is nonempty, entries use exactly one of these branch shapes; angle-bracket values denote schema-validated stable IDs or normalized paths, not free-form extensions:

```yaml
exact_metadata_contract:
  kind: exact
  contract_id: <stable-contract-id>
  path: <repo-relative-path>
  schema_id: <schema-id>
  schema_versions: [1]
  parser_id: <safe-parser-id>
  parser_version: 1
  classifier_id: <semantic-classifier-id>
  classifier_version: 1
  semantic_role: <stable-role-id>
  task_ref_fields: [<normalized-json-pointer>]
  max_bytes: 1048576
  absence_is_empty: true
  canonical_empty_state_id: <empty-state-id>
bounded_metadata_contract:
  kind: bounded
  contract_id: <stable-contract-id>
  root: <repo-relative-root>
  segment_grammar_id: <schema-defined-grammar-id>
  max_depth: 1
  max_matches: 10000
  schema_id: <schema-id>
  schema_versions: [1]
  parser_id: <safe-parser-id>
  parser_version: 1
  classifier_id: <semantic-classifier-id>
  classifier_version: 1
  semantic_role: <stable-role-id>
  task_ref_fields: [<normalized-json-pointer>]
  max_bytes: 1048576
  absence_is_empty: true
  canonical_empty_state_id: <empty-state-id>
```

`task_transaction_discovery` is likewise closed. An absent root is canonical empty; a present root must be a real non-symlink directory and has no subdirectories. Unknown names or entries produce unknown-entry findings. The journal schema and phase classifier define the complete operation/phase table plus canonical task-ID and normalized task-ref projections. Every admission/archive journal carries the immutable task ID; a pre-admission journal also carries the requested ref. A schema-valid journal is unfinished whenever its phase is not one of the declared terminal phases. An unsupported schema or classifier, corrupt journal, illegal phase transition, oversized file, unknown entry, or count overflow produces a layout-ambiguous or limit finding because terminal state cannot be proven; command blocking remains evaluator policy.

First init, workspace registration, lifecycle local-state migration, and `workspace migrate` record the exact normalized layout snapshot and digest in `workspace.json`. After a pull changes the committed release, the target CLI must statically reverify that recorded source layout and every named integration, metadata, journal, parser, classifier, and phase-table schema against the source release metadata described in Section 8; local bytes alone cannot redefine the scan or interpretation contract. A missing declaration or unsupported static interpreter sets `discovery_evidence` to `invalid` or `unsupported` as applicable; a root collision, unsafe nesting change, case/Unicode alias, or partition that cannot distinguish active from archived tasks produces a `layout-ambiguous` finding. The command's evaluator maps that evidence to `AWP_WORKSPACE_TASK_LAYOUT_AMBIGUOUS` only when the requested operation requires task discovery.

Before each task transaction, the Resolver expands the applicable metadata contracts from normalized task inputs into a finite exact path set, rejects symlinks and collisions, and records that set, its parser/classifier identities, and its preconditions in the durable task journal. The Task-state Service cannot add another path or interpretation during apply or recovery.

One normative scanner is shared by lifecycle upgrade and post-pull workspace migration:

```text
scan_task_quiescence(
  source_layout,
  target_layout,
  source_schemas,
  target_schemas
) -> canonical task_quiescence_snapshot + findings

task_quiescence_digest = SHA256(JCS(task_quiescence_snapshot))

evaluate_task_gate(
  operation,
  candidate_impact,
  task_quiescence_snapshot,
  findings
) -> blockers
```

The scanner requires verified discovery evidence for both sides. The snapshot has digest domain `agent-workflow.task-quiescence.v1` and records the source and target layout digests and schema-bundle digests; every normalized current task path and its source/target active-or-archive discovery roles; stable task identity and admission-time task ref; integration byte hash, normalized mode, schema ID/version, lifecycle status, state revision, `task_contract_digest`, and complete normalized `task_contract_surfaces`; every metadata path, byte hash, mode, parser/classifier identity, parsed task references, semantic role, and empty/nonempty classification; and every task-transaction path, byte hash, mode, schema, operation, phase, task ID/ref, and terminal classification. It also records sorted finding objects for unknown entries, collisions, limit violations, interpretation conflicts, unfinished journals, non-archived tasks, and layout-preservation failures. All sets are sorted by normalized repository-relative path and stable IDs before JCS.

Task identity and task-contract identity are normative rather than adapter-defined:

```text
task_identity
  = canonical_uuid(integration.admission.task_id)

task_contract_digest
  = SHA256(
      UTF8("agent-workflow.task-contract.v1\0")
      || UTF8(JCS(normalized_workflow_contract))
    )
```

`admission.task_id` is a cryptographically random canonical UUID and is the immutable task identity across active and archive moves. The canonical route calculator generates it, while enforcement relies on decision/approval binding, UUID validity, and project-wide uniqueness rather than unprovable unsigned-decision issuer origin. `admission.task_ref` is an immutable admission-time location label; the current discovered path is separate scanner evidence, and a later task may reuse the same active ref after the earlier task is fully archived. `normalized_workflow_contract` is exactly the closed `workflow_contract` object in Section 21 after schema validation and normalization, with no diagnostic or derived digest field. Duplicate or malformed task IDs, a task journal whose ID/ref does not match its integration, or a current path inconsistent with the applicable active/archive contract is an interpretation-conflict finding. Duplicate historical `admission.task_ref` values alone are not a conflict when task IDs and current paths are distinct.

The scanner enumerates the union of source and target active/archive partitions, metadata contracts, and task-transaction roots while applying each side's own verified schemas. A source-only path is interpreted only by the verified source declarations; a target-only path only by the verified target declarations; an overlapping path is parsed independently under both. A path visible under both contracts must have the same task identity, admission-time ref, active/archive role, lifecycle classification, `task_contract_digest`, complete surface set, metadata semantic role and task references, and journal operation, phase, task ID/ref, and terminal result. Conflicts become `layout-ambiguous` findings; valid nonterminal journals become `unfinished-task-transaction` findings; non-archived integrations become `non-archived-task` findings. The scanner does not convert any finding into a command error code.

When source and target layout digests differ, v0.1 applies an additional preservation check. Every nonempty source task, archive, or metadata object must remain recognized at the same normalized path and semantic role by the target layout. Source-only task or archive state must be absent; source-only metadata must be absent under a contract that permits absence or classifier-proven canonical empty. Target-only task/archive state must be absent, and target-only metadata must likewise be permitted-absent or canonical empty. An archived task under a source-only archive root therefore produces a `layout-state-stranded` finding. Conflicting dual-schema interpretation produces `layout-ambiguous`; otherwise any nonempty state that would be lost from the target discovery surface produces `layout-state-stranded`. The scanner never moves, rewrites, deletes, archives, reindexes, or reclassifies Trellis state. True task-layout migration is outside v0.1.

`evaluate_task_gate` is the only layer that maps those facts to operation-specific blockers. It consumes the complete snapshot because findings alone do not contain enough mode or contract detail to evaluate impact. The Resolver derives `candidate_impact` from the candidate profile/lock/artifact/policy/adapter diff against the current runtime-surface registry; it is never caller-supplied free text:

```yaml
schema_version: 1
impact_kind: none # or runtime-visible
surface_changes:
  - surface_id: platform-adapter:codex
    before_digest: sha256-value
    after_digest: sha256-value
  - surface_id: skill:tdd
    before_digest: sha256-value
    after_digest: canonical-null
```

Surface IDs come from a closed, versioned registry in the artifact bundle. Reserved namespaces cover `trellis-runtime`, `trellis-layout`, `route-policy`, `router:<id>`, `platform-adapter:<platform>`, `hook:<platform>:<id>`, `agent:<platform>:<id>`, `skill:<id>`, and `runtime-entry:<id>`; unknown namespaces or free-form selectors are schema errors. Each digest binds the complete normalized bytes and contract metadata of that surface. `canonical-null` represents absence for an added or removed surface. `surface_changes` is the complete sorted registry diff: every before/after digest difference appears exactly once, while duplicates, omissions, unchanged entries, or inconsistent digests are invalid. A task's `task_contract_surfaces` is the complete exact set it may load or execute, including transitive skill and runtime-entry references, so an unrelated surface change does not affect it while a changed or removed consumed surface does. The evaluator matches stable IDs and verifies the task's pinned digest equals `before_digest`; a mismatch is stale/ambiguous evidence rather than permission to proceed.

Multiple blockers use one deterministic order: layout/discovery ambiguity, unfinished task transaction, affected non-archived task, then stranded layout state; ties sort by canonical task ID, normalized current path, surface ID, and finding ID. The normalized snapshot, impact object, evaluator ID/version, full blocker list, and selected primary evaluator blocker are plan-bound. Section 14.12 defines the strict workspace-migration policy; Section 17 defines lifecycle policy.

This `task_quiescence_digest` is a lifecycle/migration evidence domain. It is distinct from the Route Decision `task_state_digest`, which has its own route-time projection and cannot substitute for the source/target discovery snapshot.

A mandatory cross-ownership validator rejects an active/archive root or metadata declaration that overlaps `.git/**`, `.agent-workflow/**`, `specs/**`, any artifact-definition target or managed marker, another control-plane authority, Spec Kit artifacts, ordinary source code, or any user-owned file not explicitly classified by the locked, provenance-recorded Trellis adapter as transaction metadata. The sole control-plane exception is the exact `.agent-workflow/task-transactions` discovery root, which remains Task-state-Service-owned and read-only to the quiescence scanner. Metadata declarations also may not overlap the task roots except for the separately authorized task integration and shell-move contract. Validation uses normalized case/Unicode-aware paths and applies both to static exact paths and every possible bounded-root expansion. An adapter layout change is contract-changing and cannot silently weaken protected paths, artifact ownership, or the Task-state Service boundary.

The generated ignore overlay excludes `.agent-workflow/local/` including workspace-transaction journals, `.agent-workflow/task-transactions/`, `.agent-workflow/transactions/`, both OS lock files, maintenance state, backups, and temporary files from Git. The Manifest, project workflow lock, and managed runtime catalog remain project-scoped files that may be committed. `doctor` blocks writes when ephemeral control state is tracked or when required project-scoped authority files are unexpectedly ignored.

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
- the closed runtime-surface registry, each surface's canonical digest recipe, and transitive-reference graph;
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
  "release_id": "sha256-release-identity",
  "release_manifest_digest": "sha256-value",
  "release_trust_policy_id": "github-immutable-release-v1",
  "release_trust_policy_digest": "sha256-value",
  "profile": "sol56-sdd",
  "profile_digest": "sha256-value",
  "lock_digest": "sha256-value",
  "artifact_bundle_digest": "sha256-value",
  "local_state_contract": {
    "contract_version": 1,
    "release_id": "sha256-release-identity",
    "release_version": "0.1.0",
    "workspace_schema": 1,
    "approval_replay_schema": 1,
    "task_outbox_schema": 1,
    "trellis_task_layout_digest": "sha256-value",
    "contract_digest": "sha256-value"
  },
  "platforms": ["claude", "codex", "opencode"],
  "last_transaction_id": "transaction-uuid",
  "last_transaction_binding_digest": "sha256-value",
  "previous_manifest_digest": "sha256-value",
  "files": []
}
```

`project_id` is a repository-lineage UUID. It is generated as candidate plan data for first init, becomes authoritative only when that init commits, and is intentionally preserved by repository copies and clones unless a future explicit lineage-fork operation assigns a new identity.

Each working copy also has non-Git local state at `.agent-workflow/local/workspace.json`:

```json
{
  "schema_id": "agent-workflow.workspace-local",
  "schema_version": 1,
  "project_id": "stable-project-uuid",
  "workspace_instance_id": "clone-local-uuid",
  "local_state_release_id": "sha256-release-identity",
  "local_state_release_version": "0.1.0",
  "local_state_release_manifest_digest": "sha256-value",
  "local_state_contract_digest": "sha256-value",
  "trellis_task_layout": {
    "layout_digest": "sha256-value",
    "schema_version": 1,
    "adapter_id": "trellis-v0.1",
    "adapter_version": "1.0.0",
    "runtime_namespace": ".trellis",
    "active_root": ".trellis/tasks",
    "archive_root": ".trellis/tasks/archive",
    "task_discovery": {
      "hierarchy": "one-segment",
      "segment_grammar_id": "safe-nfc-segment-v1",
      "integration_relative_path": "integration.yaml",
      "integration_schema_id": "agent-workflow.integration",
      "integration_schema_versions": [1],
      "unknown_root_entry_policy": "block",
      "allowed_non_task_entries": [],
      "max_scan_depth": 1,
      "max_tasks": 10000,
      "max_root_entries": 10000,
      "max_integration_bytes": 1048576
    },
    "metadata_contracts": [],
    "task_transaction_discovery": {
      "root": ".agent-workflow/task-transactions",
      "filename_grammar_id": "uuid-json-v1",
      "schema_id": "agent-workflow.task-transaction",
      "schema_versions": [1],
      "phase_classifier_id": "task-transaction-phase-v1",
      "phase_classifier_version": 1,
      "terminal_phases": ["complete"],
      "max_journals": 10000,
      "max_journal_bytes": 1048576
    }
  },
  "local_state_schemas": {
    "workspace": 1,
    "approval_replay": 1,
    "task_outbox": 1
  }
}
```

The workspace UUID is generated independently in each ordinary clone. The local file must be excluded from version control by a managed ignore marker. `doctor` blocks writes if it is tracked, malformed, bound to a different lineage, or not accompanied by the valid replay ledger created in the same registration transaction. Artifact definitions cannot manage this local state. Deliberately copying this ignored local file is outside the supported portability contract.

Planning and dry-run do not create the local state. Before it exists, a first-init saved plan contains candidate lineage and workspace UUIDs, the candidate local-state contract derived from release/schema/layout inputs, a workspace candidate bound to that contract, candidate detached-manifest digest, and normalized Trellis-layout snapshot, an empty replay-ledger candidate, and a digest of the normalized target path and requires Manifest and both local-state files to be absent. The workspace candidate and candidate Manifest independently render the same `plan_core` contract object; neither derives it from the other's bytes. The approved init transaction applies `workspace.json` and the empty ledger as one recoverable candidate pair before Manifest commit; the Manifest commit makes the pair authoritative, and pre-commit rollback removes both only under their original-absence and candidate-byte CAS. Every later saved plan binds both `project_id` and the persisted `workspace_instance_id`; applying it in another clone fails even when repository content and Manifest digests match.

The Manifest's `local_state_contract.contract_digest` is SHA-256 over RFC 8785 JCS of the contract object excluding `contract_digest`. It records the release, schema versions, and Trellis task-layout digest required for workspace state, approval replay, task outbox items, and post-pull task discovery. `workspace.json` records the last contract, exact detached-manifest digest, and verified layout snapshot actually applied in that clone. These fields do not make ignored local files pack-managed; they establish the version and scan boundary that registration, the Task-state Service, `doctor`, and workspace migrations enforce. `last_transaction_binding_digest` copies the committing transaction's immutable journal binding so post-commit cleanup can be recognized even if the mutable journal was not advanced or was already removed.

When a registered clone receives a committed Manifest whose target local-state contract differs from `workspace.json`'s source contract, the mismatch is not corruption and is not eligible for `workspace register`. Contract identities are not ordinal. If the verified target release contains the exact directed source-to-target edge, the relationship is `migration-required` and relationship evidence is already verified even when source discovery bytes are absent. If that edge is absent, `ahead` is legal only after the current trust policy uses the recorded source release ID/version and detached-manifest digest to statically verify the source manifest and compatibility bundle, without executing source code, and finds the exact reverse target-to-source edge. If both verified directions are absent, the relationship is `diverged`; if required relationship bytes are unavailable before that determination, the relationship remains `unknown` rather than being guessed.

The launcher, `doctor`, and `workspace migrate` derive human and JSON output from one structured diagnostic with separate state and command-admission projections:

```yaml
schema_version: 1
workspace_state:
  relationship: matching | migration-required | ahead | diverged | unknown
  relationship_evidence: verified | missing | invalid
  discovery_evidence: verified | missing | unsupported | invalid
  task_quiescence: not-evaluated | quiescent | blocked | ambiguous
  primary_state_blocker: AWP_WORKSPACE_MIGRATION_REQUIRED
command_admission:
  command: workspace-migrate
  allowed: true
  blocker: null
```

The workspace-state dimensions are command-independent. `primary_state_blocker` describes the highest-priority condition preventing ordinary contract-matched runtime operation; it may remain non-null for an explicitly authorized diagnostic, migration, or recovery command. `command_admission` is calculated separately for the requested command and is the sole answer to whether that command may start target mutation or its authorized diagnostic path. Thus a fully evidenced `migration-required` state keeps `primary_state_blocker: AWP_WORKSPACE_MIGRATION_REQUIRED`, while `workspace migrate` has `allowed: true` and `blocker: null`; an ordinary `sync` against the same state has `allowed: false` and `blocker: AWP_WORKSPACE_MIGRATION_REQUIRED`. Read-only `doctor` may be admitted to report a non-null state blocker without treating the state as healthy.

A target-owned source-to-target edge may establish `relationship: migration-required` with `relationship_evidence: verified` while `discovery_evidence: missing`; task quiescence is then `not-evaluated`. `ahead` and `diverged` require verified relationship evidence but do not require the current runtime to understand the source Trellis parser/classifier. Discovery `unsupported` or authentic-but-invalid sets task quiescence to `ambiguous` only when a command needs task discovery; it does not erase an already verified release relationship. A completed scan plus `evaluate_task_gate` yields `quiescent` when there are no operation-specific blockers and `blocked` otherwise.

Initial workspace-state selection is deterministic and conditional. Any cryptographic manifest, asset, identity, or bundle-root mismatch, and any hash-authenticated relationship or compatibility object that fails its closed schema or semantic validation, sets `relationship: unknown`, `relationship_evidence: invalid`, `primary_state_blocker: AWP_SOURCE_RELEASE_VERIFICATION_FAILED`, and exit category 30 before ordinary workspace-state ordering. Invalid relationship evidence is never downgraded to missing metadata or divergence. Missing relationship evidence yields `AWP_WORKSPACE_SOURCE_METADATA_REQUIRED`; verified `ahead` or `diverged` then yields its relationship blocker regardless of discovery support. For `migration-required`, missing discovery evidence yields `AWP_WORKSPACE_SOURCE_METADATA_REQUIRED`, unsupported/invalid discovery or layout-ambiguous findings yield `AWP_WORKSPACE_TASK_LAYOUT_AMBIGUOUS`, and the evaluator's deterministic order then selects task-recovery, active-task, or stranded-layout blockers. `AWP_WORKSPACE_MIGRATION_REQUIRED` is the state blocker only when relationship and required discovery evidence are verified and no more specific evaluator blocker exists.

Command admission is derived after workspace-state selection. Migration-required state permits read-only diagnostics, `workspace migrate` only when relationship/discovery evidence is verified and the evaluator returns no blocker, and only recovery already authorized by the current runtime allowlist. Ahead or diverged state permits read-only diagnostics and independently authorized recovery but not migration. Invalid relationship evidence permits only read-only diagnostics that do not trust or execute the invalid source bundle; every migration or ordinary write command is rejected with `AWP_SOURCE_RELEASE_VERIFICATION_FAILED` and exit 30. All routing, task mutation, provider execution, and Reconciler-backed lifecycle writes remain blocked until the contracts match. An old task journal whose pinned runtime is no longer the committed or lifecycle-candidate runtime is reported as a recovery blocker; project-local target state cannot authorize execution of that source runtime.

`AWP_TASK_QUIESCENCE_CHANGED` is not part of workspace-state blocker ordering. It is a transaction stale-evidence error: after a plan or workspace-migration journal binds a snapshot, any later rescan mismatch makes `AWP_TASK_QUIESCENCE_CHANGED` the command's primary error unconditionally. Findings from the latest scan, including a newly created active task, are retained only as secondary diagnostics until the transaction is replanned or safely recovered.

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

When a valid Manifest exists and `Manifest.lock_digest == SHA256(canonical project workflow.lock)`, `bootstrap` fetches and verifies that project lock. Otherwise it uses only the workflow lock bound by the current verified Release Identity and ignores any untrusted project-local lock. It writes only the user cache and is an optional acceleration command.

### 14.2 `init`

Performs first installation or migration. It deterministically projects the release lock, resolves and renders the selected profile, and reconciles an approved plan. If a valid manifest already exists, `init` refuses and directs the user to `sync`. If an unfinished transaction exists, it refuses and directs the user to `recover`.

Planning and `--dry-run` do not create `.agent-workflow/`, a lock file, local identity, maintenance marker, or any other target-project content. First apply uses the bootstrap lock handoff defined in Section 16.

Existing Trellis, Spec Kit, or platform files are compared with staged initializer output. A pre-existing file whose bytes exactly match a candidate may be enrolled at the ownership class authorized by its artifact definition without rewriting it, but the plan must display that ownership change. `adopted` is reserved for an explicit observe-baseline migration policy that does not grant overwrite authority. Recognized blocks may become overlay-managed; unsafe differences block. Protected runtime state remains untouched.

### 14.3 `sync`

Uses the existing project Release Identity, profile identity, project lock, artifact bundle identity, schema versions, renderer versions, and Manifest `pack_version`. It may reconcile only when those inputs match the running verified release and the result passes active-task gates. A normal `sync` never modifies the project lock; a release, pack-version, or contract mismatch requires `upgrade`.

A mismatch limited to the ignored workspace-local contract requires `workspace migrate`, not `sync` or project `upgrade`; those commands remain blocked until the clone-local migration commits.

A `sync` may bypass the active-task gate only when the reconcile plan is a true no-op. Creating, deleting, repairing, or modifying any runtime-visible file requires the gate.

### 14.4 `sync --repair`

Creates an explicit repair plan for missing or drifted pack-managed content. It never silently overwrites a divergent preimage. The plan must show the expected baseline, actual state, candidate bytes, and active-task impact and must be approved like any other write transaction.

### 14.5 `upgrade`

Generates a candidate lock and candidate IR, fetches and verifies candidate content, shows supply-chain, routing, capability, license, and file changes, checks all active tasks, and reconciles only after explicit approval.

The executing clone's local-state contract must match its currently committed Manifest before project `upgrade` starts. The approved lifecycle transaction may migrate that clone to the candidate contract before Manifest commit, while other clones later use `workspace migrate` after receiving the committed project files.

Without `--to`, the target is the immutable release of the currently executing CLI. The candidate workflow lock, definitions, schemas, and migrations come from that verified release bundle rather than from mutable project content or a latest-version query.

`upgrade --to` accepts only an immutable trusted release explicitly reachable from the installed release through `compatibility/releases.yaml`. Trust is necessary but not sufficient: a missing edge, unsupported Manifest or lock schema, absent artifact migration, or incompatible active task contract blocks before acquisition or apply. The command never invokes an older CLI against newer state.

Targeting an allowed earlier release is the supported post-commit rollback mechanism and always creates a new forward transaction using compatibility logic shipped by the currently running release. v0.1 supports only same-schema targets explicitly listed in the compatibility matrix; the initial v0.1 release has no historical target until a later compatible release publishes such an edge. Arbitrary historical rollback is not promised, and v0.1 does not expose `revert --transaction`.

### 14.6 `doctor`

Ordinary `doctor` is strictly read-only. It checks schemas, digests, cache, external runtimes, capabilities, ownership, drift, routing graph, workspace-contract alignment, unfinished transactions, active-task compatibility, source/target task-discovery evidence, static mount facts, and any previously recorded filesystem-probe evidence. For a differing registered local contract it emits the Section 12 structured `workspace_state` plus `command_admission` diagnostic and uses the shared state priority. Missing cached detached-manifest or compatibility bytes are `relationship_evidence: missing` only when they are required to classify the graph; missing layout/integration/metadata/journal bytes are independently `discovery_evidence: missing`. Unsupported parser/classifier IDs set discovery to `unsupported` and quiescence to `ambiguous` without changing a verified relationship. Any cached manifest, asset, identity, or bundle-root mismatch, or hash-authenticated relationship object that fails closed schema/semantic validation, reports `AWP_SOURCE_RELEASE_VERIFICATION_FAILED` in exit category 30. `doctor` remains command-admitted for read-only reporting but never treats that state as healthy. It never fetches, creates locks, refreshes evidence, intentionally updates target or cache state, or treats partial transaction state as success. A filesystem property that cannot be established from still-valid evidence is reported as `unverified`, not guessed as passing.

`doctor --write-probe` is a separate, explicitly authorized mutation mode. It acquires the applicable bootstrap or project lock, performs bounded temporary probes on the actual target filesystem, CAS-cleans every probe path, and records cache-side or ignored local evidence only after successful cleanup. It does not reconcile artifacts, create a Manifest, or enter maintenance. A failed or interrupted probe leaves a recorded residue set that must be cleaned or recovered before another write command.

### 14.7 `test-routing`

Runs deterministic policy, graph, golden-case, and rendered-adapter checks. It accepts normalized signal IDs rather than interpreting natural language.

### 14.8 `recover`

`recover` dispatches by versioned journal type and acquires the exact bootstrap/project locks required by the interrupted control transaction. For a Reconciler-backed lifecycle journal, validated `--resume` and `--rollback` are available only before the Manifest commit point. It never guesses between them and does not use the Task-state Service's mutation path.

`recover --probe <id> --resume|--rollback` is the narrow recovery entry for a standalone `doctor --write-probe` journal. It may touch only the exact recorded probe paths and cache-side evidence under CAS; it cannot create a Manifest, enter maintenance, or reconcile artifacts. Task transactions continue to use `task recover`.

`recover --workspace-registration <id> --resume|--rollback` is the narrow recovery entry for a fresh-clone registration journal. It uses the bootstrap-to-project lock order and may touch only the recorded workspace and empty-ledger candidates under original-absence or candidate-byte CAS. It cannot change the Manifest, workflow lock, artifacts, or tasks. A later plain `workspace register` detects the journal and directs the user to this recovery path rather than starting a second registration.

`recover --workspace-migration <id> --resume|--rollback` is the narrow recovery entry for an existing clone's ignored local-state migration. It acquires the project Reconciler lock and runtime-state gate, may touch only the exact journaled workspace/replay/outbox preimages and candidates, and cannot change any project-scoped authority. Rollback is legal only before the final `workspace.json` commit rename; after commit, recovery performs cleanup only.

### 14.9 `route decide`

`agent-stack route decide` is the canonical calculator for unsigned Route Decisions. It accepts exactly one requested operation:

```text
classify-only --signals <stable-id,...>
execute-light --intent <file>
create-integrated-task --task-ref <ref> --intent <file>
```

For `classify-only`, a model or user may propose candidate stable signal IDs directly. For executable operations, the calculator reads signal IDs only from the normalized Task Intent; a separate `--signals` option is a schema/usage error rather than a second input to compare or merge. Explanatory reasons may be supplied but never alter policy. CLI flags cannot supply authority digests, matched rules, calculated route, entry owner, decision identity, challenge, or approval state. The command validates and normalizes inputs, takes a shared runtime-state gate lock for a consistent task snapshot, reads current authorities, and applies the compiled admission policy. An implementation may use the exclusive gate when portable shared locking is unavailable. It does not interpret natural language or mutate task state.

The calculated route must be legal for the requested operation. A mismatch returns `AWP_ROUTE_OPERATION_MISMATCH` and no executable Decision. In particular, `execute-light` cannot receive an integrated route, and `create-integrated-task` cannot receive `native-light`.

### 14.10 `task admit|claim|transition|release|archive|recover`

These commands are the only supported mutation interface for integrated task lifecycle. `admit` consumes only an `operation: create-integrated-task` Decision and its one-time user-approval proof, then creates the task shell and revision 1 together through the task-admission transaction in Section 21. `classify-only` and `execute-light` are invalid inputs. `claim`, `transition`, and `release` require the expected revision plus command-specific preconditions. `archive` coordinates the locked Trellis archive adapter and integration lifecycle in one recoverable task transaction. `task recover --transaction <id> --resume|--rollback` may resume any validated unfinished task transaction, but rollback is legal only before that operation's commit point; after commit it may finish forward completion or cleanup and may not erase the committed task or archive. Platform wrappers must not expose direct Trellis create/archive, direct integration writes, or non-interactive approval bypasses.

### 14.11 `workspace register`

A fresh clone contains the repository-lineage Manifest and managed launcher but not ignored local workspace state. `.agent-workflow/bin/agent-stack workspace register` validates the runtime binding, Manifest, and managed ignore marker, requires both `workspace.json` and `approval-replay.json` to be absent, and acquires the bootstrap and project locks in that order. It creates a recoverable registration journal, writes a workspace candidate bound to the current Manifest's local-state release, detached-manifest digest, contract digest, schema versions, and normalized Trellis-layout snapshot first, and atomically renames the empty replay-ledger candidate last; that final rename is the registration commit point. Before commit, recovery may remove only matching candidate files under original-absence CAS. After commit, both files must validate as a pair bound to the same project, workspace, and local contract. The command does not change the Manifest, workflow lock, artifacts, or tasks and refuses during maintenance or an unrelated unfinished transaction. Route issuance, task commands, and Reconciler-backed writes block until registration succeeds; a partial registration requires registration recovery, while read-only diagnostics remain available and report the required action. Once registration or first init commits, a missing, malformed, identity-mismatched, or unsupported replay ledger fails closed and is never interpreted as an empty first-use ledger.

### 14.12 `workspace migrate`

An already registered working copy whose source local-state release and contract differ from the committed target Manifest enters `.agent-workflow/bin/agent-stack workspace migrate` as the only write-capable inspection/migration command. Before acquiring target-project writer locks or creating a migration journal, it may acquire the release-cache lock and use the current packaged trust policy plus `workspace.json`'s source release ID/version and manifest digest to fetch the exact immutable source detached manifest and hash-verified source distribution into the user cache. It parses only the schema-allowlisted static metadata described in Section 8 and executes no source code. It emits the Section 12 structured diagnostic. A target-owned source-to-target edge establishes verified `migration-required` relationship evidence even before discovery bytes are available; a reverse-only or diverged relationship requires verified source compatibility evidence but not a supported Trellis parser. Missing relationship or discovery bytes use their separate dimensions. Any trust/hash/bundle-root mismatch or authenticated relationship-schema failure sets invalid relationship evidence and returns `AWP_SOURCE_RELEASE_VERIFICATION_FAILED` in exit category 30. None of this inspection performs a target-project write.

For a valid source-to-target edge and verified discovery evidence, the command acquires the project Reconciler lock followed by the exclusive runtime-state gate and revalidates both contract identities, the source manifest and bundle roots, the target edge, and the complete source layout snapshot. It invokes `scan_task_quiescence(source_layout, target_layout, source_schemas, target_schemas)` exactly as defined in Section 9; no command-specific root enumeration or fallback parser is permitted. The scanner applies the bounded task grammar, integration schemas, metadata parsers/classifiers, task-journal phase tables, source/target union, dual-interpretation checks, and layout-preservation rule, returning one canonical snapshot and finding set.

`workspace migrate` then calls `evaluate_task_gate(operation: workspace-migrate, candidate_impact: <normalized-local-state-contract-impact>, task_quiescence_snapshot: <snapshot>, findings: <findings>)`. This strict policy maps every layout-ambiguous finding to `AWP_WORKSPACE_TASK_LAYOUT_AMBIGUOUS`, every unfinished task transaction to `AWP_WORKSPACE_TASK_RECOVERY_BLOCK`, every non-archived task to `AWP_WORKSPACE_ACTIVE_TASK_BLOCK`, and every valid stranded-state finding to `AWP_WORKSPACE_LAYOUT_STATE_STRANDED`, using the Section 9 ordering. When it returns no blocker, `workspace_state.primary_state_blocker` remains `AWP_WORKSPACE_MIGRATION_REQUIRED` while `command_admission` for `workspace-migrate` becomes allowed with a null blocker. Diagnostics identify the source release and instruct the user to restore that project checkout, run the matching task recovery when necessary, complete the task, and archive it before pulling/retrying the target migration. Archiving is necessary but is not sufficient when the target layout would not recognize that archived state; v0.1 requires the source-only partition or metadata state to be absent/canonical-empty and provides no task-layout mover. The pulled target Manifest, launcher, or compatibility edge cannot authorize the source runtime. v0.1 has no retained catalog or loader exception: `workspace migrate` never edits, resumes, upgrades, archives, reindexes, or reclassifies task state.

Only after the evaluator returns no blocker does the command compute `task_quiescence_digest`, write the complete snapshot, findings, evaluator identity, strict policy inputs/result, and digest into the immutable portion of a workspace-migration journal under `.agent-workflow/local/workspace-transactions/<transaction-id>.json`, enumerate the exact workspace, replay-ledger, and task-outbox preimages, and apply the edge-bound local migrations. The durable journal and quiescence binding exist before the first local-state candidate write. It never modifies the Manifest, workflow lock, launcher, descriptor, managed artifacts, tasks, Trellis metadata, task journals, or source files. Task and journal visibility is checkout-local as defined in Section 17; success makes no claim about unsynchronized clones or branches.

The migration writes replay-ledger and outbox candidates first and atomically replaces `workspace.json` last. Immediately before that final rename, with both locks still held and no intervening unbound operation, it reruns the same scanner and requires byte-for-byte equality of the canonical snapshot and `task_quiescence_digest`. Any external task, integration, metadata, pointer, index, or task-journal change makes `AWP_TASK_QUIESCENCE_CHANGED` the unconditional command primary error, blocks the commit, and leaves the transaction pre-commit and eligible for CAS-protected resume or rollback; newly observed active-task, recovery, ambiguity, or stranded-state findings are secondary diagnostics rather than replacements for the stale-evidence error. The final workspace rename is the local migration commit point because it records the newly applied release, aggregate contract, detached-manifest digest, and target Trellis-layout snapshot. Before commit, recovery must revalidate quiescence and may resume or CAS-restore every exact preimage; after commit, recovery may finish cleanup only. An unfinished workspace-migration transaction must be recovered before a new migration begins; unfinished task transactions and non-archived tasks remain the unconditional v0.1 blockers above. `recover --workspace-migration <id> --resume|--rollback` is the only workspace-migration recovery entry and follows the same lock order. A missing edge, unrecognized source schema, unexpected local path, partial candidate set, failed task/layout scan, changed quiescence, or failed CAS blocks without resetting local state.

## 15. Saved Reconcile Plans

Saved plans use four domain-separated stages so the approved candidate Manifest, transaction binding, and final plan remain fully bound without a digest cycle:

```text
plan_core_digest
  = SHA256(JCS(plan_core))

journal_binding_digest
  = SHA256(JCS(immutable_header(plan_core_digest)))

candidate_manifest
  = render_manifest(plan_core, journal_binding_digest)
candidate_manifest_digest
  = SHA256(candidate_manifest_canonical_utf8_bytes)

plan_digest
  = SHA256(JCS(plan_envelope excluding plan_digest))
```

`plan_core` contains all normalized operation inputs, identities, authorities, preconditions, non-Manifest candidate file states, the candidate local-state contract derived from release/schema inputs, provider approvals, the applicable Section 9 `task_quiescence_snapshot`, findings, `task_quiescence_digest`, normalized `candidate_impact`, task-gate evaluator ID/version and result, prospective transaction ID, and recovery runtime. A plan eligible for approval has an empty blocker set even when its scanner findings are nonempty, as may occur for a true no-op `sync`. It excludes `plan_core_digest`, `journal_binding_digest`, candidate Manifest bytes/digest, `plan_digest`, and presentation diagnostics. The immutable header contains the fields defined in Section 16 but uses `plan_core_digest`, never final `plan_digest`, and copies the task-quiescence digest as an explicit sibling binding. The plan envelope contains `plan_core`, `plan_core_digest`, the immutable header, `journal_binding_digest`, `candidate_manifest_digest`, and the candidate Manifest file-state record. Candidate Manifest bytes are reconstructable from the locked inputs and must match both their file-state record and `candidate_manifest_digest`; any workspace candidate must independently render the identical `plan_core` local-state contract rather than reading candidate Manifest bytes. Serialization may flatten schema fields, but the digest domains and exclusions are normative.

Saved plans are a closed discriminated union over `operation: init | sync | repair | upgrade`. An upgrade envelope includes at least:

```yaml
schema_version: 1
operation: upgrade
plan_core:
  transaction_id: prospective-transaction-uuid
  project_id: stable-project-uuid
  workspace_instance_id: clone-local-uuid
  manifest_generation: 6
  manifest_digest: sha256-value
  installed_release:
    release_id: sha256-installed-release-identity
    release_manifest_digest: sha256-installed-manifest
  candidate_release:
    release_id: sha256-candidate-release-identity
    release_manifest_digest: sha256-candidate-manifest
  release_trust_policy_id: github-immutable-release-v1
  release_trust_policy_digest: sha256-value
  profile_digest: sha256-value
  lock_digest: sha256-value
  artifact_bundle_digest: sha256-value
  pack_version: 0.1.0
  source_trellis_task_layout_digest: sha256-value
  target_trellis_task_layout_digest: sha256-value
  source_schema_bundle_digest: sha256-value
  target_schema_bundle_digest: sha256-value
  task_quiescence_snapshot: {}
  task_findings: []
  task_quiescence_digest: sha256-value
  candidate_impact:
    schema_version: 1
    impact_kind: runtime-visible
    surface_changes:
      - surface_id: platform-adapter:codex
        before_digest: sha256-old
        after_digest: sha256-new
  task_gate_evaluation:
    evaluator_id: agent-workflow.task-gate
    evaluator_version: 1
    blockers: []
    primary_evaluator_blocker: null
  preconditions: []
  candidate_file_states: []
plan_core_digest: sha256-value
journal_binding_digest: sha256-value
candidate_manifest_digest: sha256-value
candidate_manifest_file_state:
  path: .agent-workflow/manifest.json
  byte_hash: sha256-value
  mode: "0644"
plan_digest: sha256-value
```

Branch rules are structural schema constraints:

- `init` requires `manifest_precondition: absent`, omits `installed_release`, and requires `candidate_release` to equal the exact currently executing verified release. It also uses the bootstrap identity and replay-ledger fields described below.
- `sync` and `repair` require both release objects and require them to be identical. `repair` changes only the approved ownership-repair intent, never release identity.
- `upgrade` requires both release objects; they may differ only when the verified directed compatibility edge authorizes the installed-to-candidate transition.

No branch may carry a release URL, redefine asset hashes, or change the trust-policy ID or digest. Fields from another branch are rejected rather than ignored.

Each precondition and candidate file-state object binds one repository-relative path to existence, regular-file type, byte hash, normalized POSIX mode, and non-symlink status; overlay entries additionally bind marker and managed-block hashes. The plan never relies on parallel path, hash, and mode arrays.

Applying a saved plan revalidates:

- the branch-appropriate existing repository/workspace identities or their absence and candidate-identity preconditions;
- the operation branch and its Manifest absence or generation/digest precondition;
- the branch-appropriate installed/candidate Release Identities, detached-manifest digests, trust policy, and compatibility-edge requirement;
- pack and schema versions;
- prospective transaction identity and any bound provider-execution approvals;
- the complete `plan_core_digest -> journal_binding_digest -> candidate_manifest_digest -> plan_digest` dependency chain and every domain exclusion;
- the source/target layout and schema-bundle identities, canonical task-quiescence snapshot/findings, and its domain-separated digest;
- normalized candidate impact plus exact task-gate evaluator ID/version and blocker-free result;
- every path precondition, byte hash, POSIX mode, file type, and non-symlink status;
- reconstructability of candidate bytes from the locked cache;
- platform capabilities;
- the shared scanner plus operation-specific task-gate evaluation.

`--dry-run` writes nothing to the target project. A plan is saved only when the user explicitly supplies `--out`; default output remains terminal-only.

The `init` branch carries `project_id_precondition: absent`, `candidate_project_id`, `workspace_instance_precondition: absent`, `candidate_workspace_instance_id`, `approval_replay_precondition: absent`, the canonical empty replay-ledger candidate digest, and `target_path_digest` instead of existing identities. These bootstrap fields are part of `plan_core` and cannot be rebound at apply time.

## 16. Single-writer, CAS, and Transaction Protocol

After a valid Manifest and local workspace identity exist, all Reconciler-backed lifecycle write commands and `recover` acquire the project OS advisory lock at `.agent-workflow/reconcile.lock`. Task-state commands use the separate protocol in Section 21. Fresh-clone workspace registration uses the bootstrap-to-project lock order without starting a Reconciler transaction. PID and timestamps stored in a lock file are diagnostic only; ownership is determined by the live OS lock.

First init and recovery of an uncommitted first-init transaction use an overlapping bootstrap-lock handoff:

1. Obtain explicit plan approval; planning and dry-run remain lock-free and perform no target writes.
2. Acquire an out-of-tree OS advisory lock under the user cache, keyed by the canonical normalized target path and probed filesystem identity. Symlinked or ambiguous targets are rejected.
3. Revalidate target identity, saved-plan bootstrap fields, absence of a valid Manifest, transaction state, ownership baselines, and active tasks.
4. Create the minimum control directories and lock files, then acquire `.agent-workflow/reconcile.lock` while continuing to hold the bootstrap lock.
5. Acquire `.agent-workflow/runtime-state.lock`, revalidate again, atomically create the transaction journal as `planned`, advance it to `probing`, and execute the filesystem write probe before creating maintenance or applying authoritative state.
6. CAS-clean all probe paths, persist the successful evidence, advance the journal, then create a maintenance marker bound to the transaction ID and immutable `journal_binding_digest`. Rerun the Section 9 scanner and require the approved task-quiescence snapshot and digest to match before apply; any mismatch is primarily `AWP_TASK_QUIESCENCE_CHANGED`, with the new findings secondary.
7. Hold the bootstrap lock, project lock, and runtime-state gate through probing, file application, Manifest commit, maintenance cleanup, and journal finalization. Future lifecycle transactions use only the project lock plus the runtime-state gate while maintenance is active.

A lifecycle process that sees no valid Manifest always enters through the bootstrap lock even if a project lock file or control directory already exists. This prevents a half-created control plane from changing lock selection. Empty preparation residue created before the journal is treated as uncommitted bootstrap residue and may be removed only while the bootstrap and project locks are held and all expected paths remain empty or match their known initial bytes.

After acquiring the lock, the command revalidates manifest identity, active-task state, maintenance state, and plan baselines. Immediately before each rename, chmod, or deletion, it performs a per-path compare-and-swap check of the preimage byte hash, normalized POSIX mode, file type, and non-symlink state. Any changed precondition stops the transaction without overwriting later edits.

Transaction journals live at `.agent-workflow/transactions/<transaction-id>.json` and record phase, original file states, backups, applied files, candidate file states, candidate Manifest, rollback state, diagnostics, and every directory first created by that transaction with its original absence precondition. Their immutable binding header is hashed as:

```text
journal_binding_digest = SHA256(JCS({
  transaction_id,
  operation,
  project_id,
  workspace_instance_id,
  plan_core_digest,
  task_quiescence_digest,
  baseline_manifest_digest,
  candidate_manifest_generation,
  recovery_runtime
}))
```

For first init, `project_id` and `workspace_instance_id` are the approved candidate identities and `baseline_manifest_digest` is the schema-defined canonical null value. `task_quiescence_digest` is the Section 9 result for the operation-specific source/target pair defined in Section 17; a command for which the schema explicitly makes task discovery inapplicable uses the domain-defined canonical null, never an omitted or caller-selected value. The immutable header is written before maintenance and never changes. The journal also records the complete `task_quiescence_snapshot`, final `plan_digest`, `candidate_manifest_digest`, and candidate Manifest as immutable sibling fields, but none participates directly in `journal_binding_digest`; the snapshot is verified by the header's digest and the other siblings through the Section 15 dependency DAG. Mutable journal fields such as `phase`, applied-file lists, diagnostics, retries, and rollback progress are likewise excluded. Every journal rewrite must preserve the header and all immutable sibling fields byte-for-byte and revalidate their respective digests.

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

Before `prepared`, the Reconciler verifies baselines, creates backups, records the candidate Manifest and workflow lock, and prepares replacement files on the same filesystem as their target. Files use temporary writes plus atomic rename. The project workflow lock and managed artifacts are applied before the Manifest. Immediately before invoking the Manifest rename, while the Reconciler and runtime-state locks remain held, it reruns the exact journal-bound Section 9 scanner with no intervening unbound operation and requires canonical snapshot and digest equality. A mismatch returns `AWP_TASK_QUIESCENCE_CHANGED` as the unconditional command primary error, reports the latest task-gate findings only as secondary diagnostics, leaves the transaction pre-commit, and permits only validated resume or CAS rollback. Manifest atomic rename is the logical commit point.

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
- `last_transaction_id`, `last_transaction_binding_digest`, and Manifest generation determine whether a crash occurred after Manifest commit but before journal update.

v0.1 guarantees recovery from process termination under the documented filesystem assumptions. It uses atomic rename and best-effort flushes but does not guarantee ordering after sudden power loss, host failure, storage failure, or filesystems that do not honor the required semantics.

### 16.1 Filesystem Preconditions

Ordinary `doctor` and every `--dry-run` perform zero target writes. They may inspect mount metadata and cached probe evidence, but report absent, stale, path-mismatched, filesystem-mismatched, or version-incompatible evidence as `unverified`.

`doctor --write-probe` and an approved apply preflight test the actual target filesystem for cross-process advisory-lock behavior, same-filesystem atomic replacement, regular-file and non-symlink checks, readable and settable POSIX mode bits, path case behavior, and Unicode-normalization collision behavior. Apply commands always perform this live probe after acquiring the applicable writer locks and before maintenance or authoritative file replacement; cached evidence is diagnostic and cannot replace apply-time validation. Temporary replacement files and their targets must share a filesystem. Case-folded or normalized path collisions block even when the host would otherwise permit both names.

Each probe uses nonce-named paths with recorded original-absence preconditions. First-init probe residue is recorded in the bootstrap transaction; initialized-project probe residue is recorded in the current transaction; standalone `doctor --write-probe` uses a cache-side probe journal keyed to the canonical target and filesystem identity. Cleanup deletes only exact recorded paths that still match their candidate type, bytes, and mode. A crash or failed CAS leaves recovery-required evidence and blocks unrelated writes rather than treating the probe as successful. Successful evidence binds the canonical target, filesystem and mount identity, probe contract and CLI versions, measured capabilities, and completion time.

The v0.1 write contract supports only Linux or WSL filesystems that pass these probes. A WSL path under `/mnt/*` is never assumed safe from its path alone; failed or indeterminate lock, rename, mode, or collision probes block write commands while leaving read-only diagnostics available. Network filesystems, cross-device replacements, and filesystems with unverified advisory locks are unsupported for mutation.

## 17. Maintenance and Active-task Gate

After acquiring the applicable writer locks, a write transaction also acquires the exclusive runtime-state gate lock, atomically persists the transaction journal for process-crash recovery, creates `.agent-workflow/maintenance.json`, and then reruns the journal-bound task-quiescence scan before apply. It holds the gate through maintenance cleanup. The marker contains the transaction ID, `journal_binding_digest`, final `plan_digest`, `task_quiescence_digest`, and candidate Manifest generation. The binding validates only against the immutable journal header defined in Section 16, while `plan_digest` and the quiescence digest must match the journal's immutable siblings and Section 15 envelope; journal phase and other mutable fields may advance without rewriting the marker. Generated platform adapters, runtime loaders, and the heavy router must check this marker.

If a marker references an existing unfinished transaction, `doctor` recomputes the immutable header digest and reports recovery-required. If the current Manifest's generation, `last_transaction_id`, and `last_transaction_binding_digest` match the marker, the transaction is committed even when a mutable journal update or the journal itself is missing; `recover` may finish cleanup only. A marker whose immutable binding matches neither an existing journal nor those committed Manifest fields is corrupt or orphaned and is never silently ignored. Explicit orphan cleanup is allowed only while all applicable locks are held and after CAS validation proves that either the prior committed Manifest baseline or first-init bootstrap preconditions remain intact, no transaction temporary or backup files remain, and no candidate file state was applied; otherwise writes remain blocked for manual recovery.

While maintenance exists:

- no new task may be admitted;
- existing tasks may not resume or advance phase;
- write-type runtime commands are blocked;
- only read-only diagnostics and `recover` are allowed.

Route calculation emits no Decision while maintenance is active. It returns this non-executable diagnostic:

```yaml
schema_version: 1
status: blocked
blocked_by: maintenance
transaction_id: transaction-uuid
```

After maintenance clears, an existing task resumes its pinned mode and contract without reclassification.

Every lifecycle task gate uses the Section 9 `scan_task_quiescence` implementation; “locked Trellis roots” is not a separate or sufficient enumeration rule. The source/target inputs are fixed by operation:

- first `init` scans the verified candidate layout/schema on both sides after bootstrap locking, so pre-existing candidate-visible task state cannot be skipped;
- `sync` and `repair` scan the currently committed layout/schema on both sides;
- `upgrade` scans the current committed layout/schema as source and the fully verified candidate layout/schema as target, including target-only roots and metadata paths;
- `recover` uses the immutable source/target layout, schema-bundle, snapshot, and digest identities recorded by its journal.

Planning records the canonical snapshot, findings, digest, normalized candidate impact, and evaluator result in `plan_core`. The scanner does not decide whether a discovered task blocks the command. `evaluate_task_gate(operation, candidate_impact, task_quiescence_snapshot, findings)` applies these lifecycle rules:

- `init` treats any pre-existing integrated task, task transaction, ambiguous discovery, or nonempty stranded layout state as a migration conflict rather than adopting it implicitly.
- Any non-no-op lifecycle write blocks on unfinished task transactions, layout-ambiguous findings, or inconsistent pointers/contracts because its safe impact cannot be established.
- For `upgrade`, every non-archived `speckit-superpowers` task blocks a contract-changing candidate. A non-archived `trellis-native` task blocks only when a candidate `surface_change` matches one of its exact pinned `task_contract_surfaces` and changes or removes that surface's digest. Adapter, hook, agent, skill, router, and runtime-entry impact therefore comes from stable surface intersection rather than inference from an aggregate task-contract digest.
- `sync` and `repair` use the same mode/surface comparison for runtime-visible writes. A task finding whose pinned surface set has no changed ID is not itself a blocker; a before-digest mismatch is stale/ambiguous evidence and fails closed.
- A layout-changing lifecycle operation blocks with `AWP_WORKSPACE_LAYOUT_STATE_STRANDED` when source-only archived or metadata state would cease to be recognized, or when target-only task state already exists; v0.1 does not migrate that state.
- `admitting`, `active`, `blocked`, `completed`, and `archiving` are all non-archived findings. `completed` therefore still blocks whenever its mode/impact rule blocks; only `archived` is categorically non-gating.
- A true no-op `sync` has `impact_kind: none` and an empty `surface_changes` list, may return verified no-op even when non-archived findings exist, and performs no write transaction. Findings remain available as diagnostics rather than being mislabeled as scanner errors.

After the Reconciler/runtime-state locks and maintenance marker are established, the scanner runs again. If the canonical snapshot or digest differs from the approved evidence, the command returns `AWP_TASK_QUIESCENCE_CHANGED` as primary before reevaluating command policy; latest findings are secondary and the transaction remains pre-commit recoverable. If the snapshot is identical, the plan-bound evaluator result remains valid. Section 16 requires the same equality immediately before Manifest commit. Layout or schema change does not permit a second scanner, current-only fallback, or adapter-specific shortcut.

This gate is checkout-local. It observes only task and transaction state present in the working copy executing the command and cannot detect an active task that exists only in another clone, branch, unpushed commit, or otherwise unsynchronized workspace. v0.1 provides no distributed task lock or cross-clone admission registry; teams must synchronize workflow state before contract-changing upgrades, and the CLI must not claim that a passing local scan makes an unseen workspace safe.

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

Route Decision is a closed discriminated union:

| `operation` | Allowed `route` | Required branch fields | Effect |
|---|---|---|---|
| `classify-only` | Any admitted route | No intent, task-ID/ref, surface, challenge, or approval fields | Read-only result; never accepted by an execution loader or `task admit` |
| `execute-light` | `native-light` only | `intent_id`, `intent_digest` | Enters the platform's bound native-light path; creates no Trellis task or integration state |
| `create-integrated-task` | `trellis-native` or `speckit-superpowers` only | Intent, decision-bound random task ID, task ref, ref-absence and ID-uniqueness preconditions, pinned surface digest, fresh challenge, and `task_creation_approval: required` | May be consumed only by `task admit` with a matching approval proof |

All branches contain the authority snapshot, policy inputs and results, platform and adapter identity, `decision_id`, and `decision_digest`. Fields belonging to another branch are schema errors rather than ignored data.

The integrated branch is:

```yaml
schema_version: 1
decision_id: decision-uuid
decision_digest: sha256-value
operation: create-integrated-task
requested_task_id: 4b27d17a-6b75-4b79-b7b0-7a1e56eaa2c1
requested_task_ref: .trellis/tasks/001-feature
task_ref_precondition: absent
task_id_precondition: unique
intent_id: feature-intent-id
intent_digest: sha256-value
task_contract_surfaces_digest: sha256-value
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

For `execute-light` and `create-integrated-task`, the caller supplies a Task Intent document and the calculator computes `intent_digest`. The intent schema includes stable intent identity, title, concise objective, requested mode if explicit, acceptance summary, and the sole executable set of candidate signal IDs. A separate CLI signal list is forbidden, and the Decision's normalized `signals` field must exactly equal the signals extracted from the digested Intent. The integrated branch additionally validates the normalized proposed task ref. The caller cannot substitute a different intent, signal set, task ref, or operation at the consuming loader. `classify-only` contains neither an intent nor task-creation fields and cannot be promoted in place; a later executable calculation rereads current authority.

For `create-integrated-task`, the calculator generates a cryptographically random canonical UUIDv4 `requested_task_id` and a fresh random 256-bit approval challenge. It derives the complete task-specific surface set from the selected mode, platform, adapter, router, and transitive runtime references, then records `task_contract_surfaces_digest = SHA256(UTF8("agent-workflow.task-surfaces.v1\0") || UTF8(JCS(normalized_task_contract_surfaces)))`. It normalizes each branch payload excluding `decision_id` and `decision_digest`, derives `decision_id` as UUIDv5 over the payload hash in the fixed Agent Workflow Pack route namespace, and then computes `decision_digest` over the normalized payload plus derived ID. Policy evaluation remains deterministic, while each integrated admission envelope is unique because its task ID and challenge are unique. Explanatory reasons participate in the digest but never alter policy evaluation.

`task_state_digest` covers the canonical checkout-visible task-identity inventory across active tasks, archives, and unfinished task journals, plus non-archived modes, active pointers, lifecycle revisions, recomputed `task_contract_digest` values, and exact surface sets. The integrated branch also covers requested task-ID uniqueness and active task-ref absence. It is null only for a classification-only project with no task-state inputs. Staging under `.agent-workflow/local/` does not alter this digest. Any intervening admission, transition, archive, pointer change, contract/surface change, task-ID appearance, or relevant ref creation makes an executable Decision stale.

Route Decisions are not signed and have no issuer-authenticity guarantee. The calculator, UUID, and digest prove only canonical internal consistency and freshness for the supplied fields. A policy-consistent envelope constructed elsewhere is indistinguishable from calculator output and is not treated as trusted because of its claimed origin. Every execution loader therefore rereads current authorities, recomputes identities, reruns the compiled policy over the supplied stable signal IDs, validates the operation/route union, and requires exact agreement on route, matched rules, entry owner, task state, adapter version, and approval requirement. Modified, inconsistent, stale, or cross-operation envelopes fail; origin alone is never an authorization input.

Deterministic routing begins only after candidate signal IDs are supplied. The pack cannot prove that a model or user extracted every relevant signal from natural language, and omission of a signal is outside the technical enforcement guarantee. Platform instructions require conservative extraction and golden tests cover known cases, but natural-language classification remains an instruction-level quality boundary rather than a security boundary.

Integrated task-creation approval and implementation activation are separate gates. The enforced platform approval mechanism returns a one-time proof binding approval ID, approval challenge, Route Decision digest, task ID, task ref, task-surface digest, intent digest, `operation: create-integrated-task`, workspace instance, actor, time, and verifier ID/version. It proves direct approval of that envelope, not completeness of signal extraction or exclusive calculator origin. `task admit` accepts no free-form override for those fields and records the verified proof in revision 1. The proof may be consumed only by one task-admission transaction; recovery may continue that same transaction but may not apply it to another task ID/ref. `classify-only` and `execute-light` never carry task-creation approval fields. Implementation activation belongs in the heavy branch after the task exists.

The approval verifier emits a versioned envelope through the platform's enforced confirmation channel:

```yaml
schema_version: 1
approval_id: approval-uuid
verifier_id: platform-approval-verifier
verifier_version: 1.0.0
platform: codex
harness_version: pinned-version
actor:
  id: platform-human-actor-id
  kind: direct-human
issued_at: 2026-07-13T15:00:00Z
expires_at: 2026-07-13T15:15:00Z
workspace_instance_id: clone-local-uuid
operation: create-integrated-task
task_id: 4b27d17a-6b75-4b79-b7b0-7a1e56eaa2c1
task_ref: .trellis/tasks/001-feature
task_contract_surfaces_digest: sha256-value
intent_digest: sha256-value
route_decision_digest: sha256-value
approval_challenge: random-256-bit-value
verifier_receipt: opaque-platform-verifier-value
```

The adapter capability manifest binds verifier ID/version to exact supported harness versions and proves that `actor.id`, timestamps, challenge, and receipt come from the confirmation mechanism rather than model-authored CLI input. `task admit` requires `kind: direct-human`, verifies the profile TTL and clock-skew limits, and rejects an unsupported verifier version. Existing unfinished admission journals pin their verifier version and recovery runtime; an upgrade that cannot continue that verifier contract is blocked. New verifier versions apply only to new approvals.

Replay detection uses `.agent-workflow/local/approval-replay.json`. Ordinary reservation and consumption transitions are written only by the Task-state Service under the runtime-state gate. The approved first-init transaction may create the canonical empty ledger, workspace registration may create the same empty ledger as part of its paired commit, and a verified compatibility-edge migration may transform the exact existing ledger under the Reconciler protocol in Sections 8 and 16. No other writer or delete-and-recreate path is permitted. Its independent schema is:

```json
{
  "schema_id": "agent-workflow.approval-replay",
  "schema_version": 1,
  "project_id": "stable-project-uuid",
  "workspace_instance_id": "clone-local-uuid",
  "entries": {
    "sha256-proof-key": {
      "bound_transaction_id": "task-transaction-uuid",
      "state": "reserved",
      "validated_at": "2026-07-13T15:00:00Z",
      "proof_expires_at": "2026-07-13T15:15:00Z",
      "consumed_at": null
    }
  }
}
```

The stable key excludes transaction identity:

```text
proof_key = SHA256(JCS({
  approval_id,
  approval_challenge,
  route_decision_digest,
  workspace_instance_id
}))
```

Each key has exactly one monotonic state path: absent to `reserved` to `consumed`. Its value binds one `task_transaction_id`; an existing entry may never be rebound, deleted, or reset. The normal admission path persists a planned journal containing `proof_key`, complete proof identity, and successful `validated_at`, then inserts the absent ledger entry as `reserved` only while the proof is within its TTL and clock-skew policy. A reservation held by another transaction or any consumed tombstone rejects the proof.

Once reservation succeeds, validated resume of that same journal and transaction may continue after proof expiry; expiry cannot strand pre- or post-commit recovery. If a crash leaves the planned journal durable but the ledger entry absent, resume may complete the reservation only for that same transaction when the journal proves the original validation occurred within TTL and the complete proof still matches the recorded digest. Rollback from this window preserves the sole legal `absent -> reserved -> consumed` path: it first CAS-creates the `reserved` entry bound to that same transaction from the journal's recorded validation, then separately CAS-transitions it to a `consumed` tombstone and records `consumed_at`. A crash between those two writes resumes from the same journal and may only complete consumption. Commit or later rollback of an already reserved transaction likewise changes it to `consumed` by CAS. A fresh clone cannot replay the proof because the workspace identity differs. Missing or corrupt ledger state after a committed workspace registration, duplicated keys, illegal transitions, expired first-use attempts, or conflicting bindings block admission.

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
  "release_id": "sha256-release-identity",
  "release_manifest_digest": "sha256-value",
  "release_trust_policy_id": "github-immutable-release-v1",
  "release_trust_policy_digest": "sha256-value",
  "pack_version": "0.1.0",
  "distribution_name": "agent-workflow-pack",
  "entry_point": "agent-stack",
  "wheel_url": "immutable-https-wheel-url",
  "wheel_sha256": "sha256-value",
  "source_commit": "full-40-hex-commit",
  "uv_version_policy": "release-tested-closed-range",
  "cache_policy": "offline-first-pinned-redownload"
}
```

The descriptor is rendered only from a detached manifest already verified under the packaged trust policy. v0.1 uses one cold-cache protocol and one pre-wheel authority: the launcher file itself. It embeds literal constants for Release Identity, detached-manifest digest, exact immutable wheel URL, wheel SHA-256, supported uv policy, supported local-Python range, the complete uv argument contract, and launcher contract version. It does not embed or pre-validate the descriptor digest. The descriptor is a post-wheel managed input that the pinned CLI validates before ordinary command dispatch.

Detached-manifest-derived substitutions and their renderer version participate in the rendered launcher's `render_digest`, `applied_file_hash`, and `distribution_render_digest`, but are excluded from `launcher_bundle_digest`. The launcher bundle contains only release-neutral templates, schemas, and verifier logic. Release CI rejects a launcher bundle containing wheel identity, detached-manifest identity, rendered descriptor bytes, or rendered launcher substitutions.

The v0.1 pre-wheel prerequisites are POSIX `sh`, POSIX `env`, a release-tested `uv`/`uvx` binary, and an already installed compatible Python interpreter satisfying `>=3.11,<3.15`. The launcher does not require pre-wheel JSON parsing or a separate `sha256sum`: uv verifies the direct-wheel hash, and the pinned Python CLI performs all project-file hashing after startup. The selected uv binary and local Python are user-provided trusted bootstrap prerequisites whose resolved paths and versions are reported by `doctor`; v0.1 does not supply or download Python.

Bootstrap isolation and application context are two separate stages. Before clearing the environment, the launcher captures only the non-sensitive caller context allowed by the selected platform adapter schema: the OS-account user/config roots, platform ID, absolute harness executable path and version-probe identity when available, project-external config paths needed for read-only capability inspection, and whether stdin/stdout/stderr are TTY-backed and support confirmation. Values are passed through a reserved, length-bounded internal CLI argument channel; they are not restored as ambient environment variables and do not participate in wheel selection. User/model command arguments may not set, repeat, or override reserved `--caller-*` or `--bootstrap-project` fields. The launcher and CLI reject relative paths, control characters, duplicates, unknown fields, and values outside the adapter's allowlist.

The caller-context envelope must never contain tokens, cookies, SSH or cloud credentials, proxy userinfo/passwords, arbitrary environment snapshots, file contents, or unbounded `PATH`. Platform-specific variables such as `CODEX_HOME` or Claude/OpenCode config locations may contribute only a normalized path field explicitly listed by the locked adapter schema. The CLI does not read any supplied external path until after release, Manifest, descriptor, journal, workspace-contract, and command eligibility checks succeed.

After capturing that narrow envelope, the launcher discards the inherited environment and constructs a fixed bootstrap allowlist containing only the resolved bootstrap `PATH`, a cache-side non-project `HOME`, `LANG=C.UTF-8`, `LC_ALL=C.UTF-8`, and `TZ=UTC`. It inherits no `UV_*`, index, proxy-credential, Python-selection, virtual-environment, `.env`, platform, or project variables. Its uv invocation is schema-fixed and equivalent to:

```text
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
  --from '<wheel-url>#sha256=<wheel-sha256>' \
  agent-stack \
    --bootstrap-project <repo-root> \
    --caller-context-version 1 \
    --caller-user-home <absolute-path> \
    --caller-config-root '<adapter-field>=<absolute-path>' \
    --caller-platform <platform-or-none> \
    --caller-harness-path <absolute-path-or-none> \
    --caller-tty <present-or-absent> \
    <command...>
```

The launcher resolves one release-supported uv executable and one compatible local Python executable before clearing the environment, validates their versions, converts both to absolute non-symlink paths, and then invokes only those paths. The exact argument order, supported uv version range, environment keys, bootstrap search/path derivation rules, direct-wheel URL, and hash are part of the launcher contract and rendered-launcher digest. `--isolated` creates an isolated tool environment rather than reusing a globally installed same-name tool; `--no-config` and `--no-env-file` ignore `uv.toml`, `pyproject.toml`, and `.env`; `--no-index`, `--no-sources`, and the dependency-free wheel prevent alternate package resolution; `--no-python-downloads` makes absence of compatible local Python a fail-closed bootstrap error. A cache miss may download only the hash-bound direct wheel and its allowed redirects. No Python distribution, registry package, build dependency, or second tool artifact may be fetched.

The exact launcher wheel identity is sufficient only to bootstrap already hash-pinned code; it is not full release authorization. Immediately after the wheel starts and before it dispatches `workspace register`, diagnostics, recovery, routing, task-state, lifecycle, or any provider/network operation, the CLI uses its packaged canonical trust-policy bytes to derive the detached-manifest locator, verifies the pinned GitHub repository and immutable release, parses the project Manifest, descriptor, and any transaction journal, and requires all applicable release, source, bundle, and file-record authorities to agree. It then emits the Section 12 structured diagnostic, plus independent registration/recovery state, and applies the command allowlist from that result. Launcher, `doctor`, and `workspace migrate` must assign the same `workspace_state` relationship, evidence, quiescence, and `primary_state_blocker` values to the same verified bytes; each separately derives `command_admission` for its requested command, so an authorized migration or diagnostic may be admitted while the shared state blocker remains non-null. Contract equality is required for every ordinary runtime command. A differing contract permits only read-only diagnostics, `workspace migrate` for trusted static inspection and an authorized source-to-target migration, and recovery independently authorized by the current committed/candidate allowlist; no route, wrapper, loader, or task command receives an old-contract exception. Ahead/diverged states remain diagnostic-only after classification even when task discovery is unsupported. Only after those checks does it validate the caller-context envelope against the locked adapter, re-probe OS account, filesystem, harness version/path, and live TTY facts where possible, and construct a command-specific runtime context. It never recreates the original process environment wholesale. Failure performs no target write and no workflow-component download. The cached detached manifest is therefore an optimization, not a cold-start prerequisite. The CLI verifies its packaged Release Identity, source commit, trust-policy identity, package/version metadata, and bundle roots against the detached manifest; it does not claim to re-read or independently hash the original wheel container bytes after startup.

Launcher replacement is a single-file atomic rename and is the only pre-wheel bootstrap switch. Descriptor replacement is a separate managed rename that cannot prevent the shell from starting the wheel. With no unfinished transaction, the started pinned CLI requires both files to match the committed Manifest. With an unfinished transaction, the pinned CLI accepts the launcher and descriptor independently only when each complete byte-and-mode state equals either the journal-recorded preimage or candidate state, permits only diagnostics and the matching `recover`, and selects or re-executes only the committed/candidate runtime allowlisted by the journal. Therefore old-launcher/new-descriptor and new-launcher/old-descriptor crash states remain recoverable; an unrecorded third state fails closed.

A fresh clone receives the committed launcher, descriptor, Manifest, and workflow lock even though local state is absent. After release verification, the pinned CLI permits `workspace register` and read-only diagnostics before local registration. A registered clone with differing source/target contracts permits read-only diagnostics, `workspace migrate`, and only recovery already authorized by the runtime allowlist. `workspace migrate` may populate the trusted cache with the exact source static metadata needed to distinguish migration-required, ahead, and diverged states, but may mutate ignored local state only for the verified source-to-target branch after the shared no-active-task, no-unfinished-journal, and no-stranded-layout-state quiescence gate passes. Other runtime and write commands remain blocked in all mismatch states.

Every Reconciler or task transaction journal records only a non-authoritative runtime reference before its first target mutation:

```yaml
recovery_runtime:
  runtime_role: committed # or candidate
  release_id: sha256-release-identity
  release_manifest_digest: sha256-value
  launcher_contract_version: 1
```

The journal may not contain a wheel URL, asset hash, repository, tag, or trust-policy override. After the launcher starts its own exact wheel, that pinned CLI interprets the journal. It accepts `runtime_role: committed` only when the reference equals the Release Identity and detached-manifest digest in the committed project Manifest. It accepts `candidate` only when the reference equals the candidate Manifest and approved plan, the candidate detached manifest is already cached and independently re-verifies under the committed trust policy, and the verified compatibility edge authorizes the installed-to-candidate transition. A journal mismatch cannot expand this two-entry allowlist and fails before candidate code executes. In particular, after a clone pulls a target Manifest, an unfinished task journal pinned to a different source release is not executable merely because that source appears in a compatibility edge or task contract. Diagnostics must direct the user to restore a project checkout whose committed Manifest authorizes that source runtime and recover there.

While a transaction is unfinished, the pinned CLI permits only read-only diagnostics plus the matching `recover` command through the selected allowed runtime. An unfinished task transaction therefore blocks `route decide`, task loaders, and every unrelated write command. This works whether a crash occurred before the launcher rename, between the launcher and descriptor renames in either order, or after both managed files reached their candidate states.

Launcher and descriptor changes are ordinary managed artifacts with independent byte-and-mode CAS, backups, and per-file atomic rename. Compatibility metadata must prove that both the preimage and candidate launcher contracts understand the transaction's recovery-runtime schema and mixed preimage/candidate file-state recovery. Manifest commit switches the normal runtime authority; pre-commit rollback restores the prior launcher and descriptor under CAS, while post-commit recovery performs cleanup only.

A forward upgrade begins in the trusted committed runtime, which verifies the target detached manifest and wheel before invoking that exact local wheel for the upgrade-only entry. A mismatched external CLI may run only `upgrade` when its verified Release Identity and compatibility edge authorize the installed-to-running transition; all other commands fail closed. Rollback to a listed earlier release may be orchestrated by the currently installed launcher runtime through the same detached-manifest verification. After upgrade commit, all normal wrapper calls start through the newly committed launcher, and the started CLI requires the post-wheel descriptor to match the committed Manifest.

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
- Route Decision branch schema, identity, digest, operation/route legality, and deterministic policy replay;
- route and pinned mode;
- current phase;
- entry owner;
- executor claim;
- profile, lock, policy, and router-contract digests;
- locked runtime-entry content digest.

Direct platform entry points for `/speckit.implement`, Trellis implement/check, or Spec Kit phase commands must not coexist when they bypass this gate. If a platform or harness cannot hide or gate a native entry, that capability is `instruction-only` or `unsupported`, never `enforced`.

Discoverable leaf skills undergo transitive-reference validation. If their locked upstream content references `using-superpowers`, planners, executors, or other gated entries, the pack must apply a first-party, locked compatibility overlay or block projection. A skill is not considered safe merely because its name appears leaf-like.

`heavy-development-router` is the sole top-level orchestrator only after admission selects `mode: speckit-superpowers`. It is not the global router for lightweight or Trellis-native tasks.

The `execute-light` adapter enters only the platform binding for `native-light`; it cannot load the heavy router, Trellis task runtime, or `task admit`. A `classify-only` result is presentation data and every execution wrapper rejects it.

## 21. Integration State Contract

Every task admitted to `trellis-native` or `speckit-superpowers` stores `integration.yaml` at its locked active or archive task ref. The schema is a discriminated union keyed by `mode`; common fields pin the workflow contract and task lifecycle, while only the selected mode-specific branch is legal.

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
  task_contract_surfaces:
    - surface_id: trellis-runtime
      surface_digest: sha256-value
    - surface_id: platform-adapter:codex
      surface_digest: sha256-value
    - surface_id: skill:tdd
      surface_digest: sha256-value

lifecycle:
  status: active
  state_revision: 12
  admitted_at: 2026-07-13T15:00:00Z
  archived_at: null
  blocked_reason: null
  last_transition: {}

admission:
  operation: create-integrated-task
  task_id: 4b27d17a-6b75-4b79-b7b0-7a1e56eaa2c1
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

`admission.task_id` is immutable and is the task's canonical identity even after archive moves the integration file. It must equal the Decision- and approval-bound canonical UUID and may not duplicate any checkout-visible active, archived, or unfinished-journal task ID. `admission.task_ref` is an immutable admission-time path label; the current active/archive file location is separate scanner evidence. A later task may reuse that active ref only after the previous task's archive commit moved it away, but receives a new task ID. Any mode-specific task-ref field equals the admission-time ref, not the current archive location.

`workflow_contract.task_contract_surfaces` is a closed, sorted set of `{surface_id, surface_digest}` records derived by the route calculator and reverified by `task admit`; models and adapters cannot append free-form surfaces. It contains every exact runtime surface the task may consume, including transitive references. Its digest must match the Route Decision's `task_contract_surfaces_digest`. The workflow contract is a closed object, and its derived identity is:

```text
task_contract_digest
  = SHA256(
      UTF8("agent-workflow.task-contract.v1\0")
      || UTF8(JCS(normalized_workflow_contract))
    )
```

`normalized_workflow_contract` contains exactly the schema-versioned fields shown above after path/string/version/surface normalization and excludes diagnostics and the derived digest itself. Loaders, task-state digests, scanners, and candidate-impact comparison recompute this value rather than accepting a caller-supplied contract identity. Surface records sort by `surface_id`; duplicates, unknown IDs, missing transitive references, or a surface digest inconsistent with the admission authorities invalidate the integration contract.

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

`lifecycle.status` is one of `admitting`, `active`, `blocked`, `completed`, `archiving`, or `archived`. `admitting` identifies a task whose directory exists but whose Trellis metadata has not yet reached the admission commit point; it is never runnable or resumable. `blocked` requires a non-null reason. `completed` means implementation and verification are complete, but finish, journal, memory, review, publication, or Trellis archive obligations may remain. `archiving` identifies an unfinished archive transaction. The states `admitting`, `active`, `blocked`, `completed`, and `archiving` all remain active for safety gates; only `archived` is non-gating. Archiving records `archived_at` through the task-state mutation protocol; deleting the file is not an archive operation. Resume always uses the pinned mode and contract and never reclassifies the task.

### 21.1 Atomic Task Admission

Task creation is a Task-state Service transaction, not a prerequisite performed by Trellis or the model. Its durable journal is `.agent-workflow/task-transactions/<transaction-id>.json`; its same-filesystem staging root is `.agent-workflow/local/task-staging/<transaction-id>/`. The journal is recovery evidence, not a second task authority.

`task admit` executes this order while holding the exclusive runtime-state gate and the task-ref lock; the exclusive gate serializes the project-wide task-ID uniqueness check:

1. Validate the current Manifest, workspace identity, `create-integrated-task` Decision, one-time approval proof, requested-ref absence, requested-task-ID uniqueness across active/archive integrations and unfinished journals, task-state digest, adapter contract, and all pinned runtime/surface digests.
2. Atomically persist a `planned` journal binding the decision, verifier envelope, proof digest, `proof_key`, proof validation time, intent, task ID/ref, operation, candidate generator, recovery runtime, local-state schema versions, exact task-contract surfaces, and every precondition. CAS-create or validate the one ledger reservation bound to this transaction under the Section 19 state machine. Only then create staging residue.
3. Render the complete locked Trellis task shell and `integration.yaml` revision 1 under the staging root. Revision 1 contains the approved task ID/ref and exact surface set, has `lifecycle.status: admitting`, `state_revision: 1`, and `admitted_at: null`. No direct Trellis create command may write the target project. Validate the entire tree, record every file byte hash and normalized POSIX mode, and advance the journal to `staged`.
4. Revalidate task-ID uniqueness, active task-ref absence, active pointers, decision, approval, surfaces, and tree digest. Atomically rename the staged task directory to `requested_task_ref` and advance to `task_moved`. The directory is now visible but remains non-runnable and uncommitted because its integration status is `admitting`.
5. Apply the locked Trellis adapter's index, active-pointer, and required journal-file candidates with byte-and-mode CAS, backups, and atomic replacement. Revalidate that every metadata path equals its recorded candidate and advance to `metadata_applied`.
6. CAS the integration preimage from the exact `admitting` revision 1 to `active` revision 2, set `admitted_at`, and record the transaction in `last_transition`. This atomic integration rename is the task-admission commit point.
7. Advance through `admission_committed` and `cleanup_pending`, durably enqueue any allowed post-commit effects, remove staging and backup residue, and mark the journal `complete`.

The task candidate tree uses a deterministic Merkle digest over repo-relative paths, bytes, and normalized modes. To avoid self-reference, the schema excludes `admission.candidate_tree_digest` itself when calculating that digest. Revision 1 records the transaction ID and resulting admitting-tree digest. If the process dies after the directory rename but before the journal advances, recovery recognizes `task_moved` only when the target is a real non-symlink directory, its integration state is the matching `admitting` revision, and its recomputed candidate-tree digest matches. If the integration state is the matching `active` revision 2 and every Trellis metadata path reached its recorded candidate, recovery recognizes `admission_committed` even when the journal did not advance. Any other combination blocks without accepting, deleting, or replacing the target.

Admission phases are:

```text
planned -> staged -> task_moved -> metadata_applied
        -> admission_committed -> cleanup_pending -> complete
```

Before `admission_committed`, validated recovery may resume or roll back. At `planned` or `staged`, rollback removes only recorded staging residue. At `task_moved` or `metadata_applied`, rollback first restores every changed Trellis metadata preimage under CAS, then reverses the task-directory move only when the complete admitting tree still matches its recorded digest and type. A rollback marks the approval reservation consumed permanently; only `--resume` of the same unfinished journal may use a reserved proof. At `admission_committed` or later, rollback is forbidden: recovery may only finish outbox enqueue and cleanup. A committed task may be archived later through a new task transaction, never erased as admission recovery.

Only reversible declared file operations are allowed before admission commit. The integrated overlay disables upstream task-create hooks, notifications, subprocess callbacks, network actions, and automatic Git commits during the transaction. Required Trellis journal content must be represented as a declared CAS-managed file candidate; an opaque journal command is not allowed. Automatic Git commit is disabled entirely in v0.1 and remains a user action.

Optional post-commit hooks may run only through `.agent-workflow/local/task-outbox/<effect-id>.json`. Each item uses the independent `agent-workflow.task-outbox` schema and carries its own `schema_version`, operation, task transaction ID, effect ID, handler ID/version, payload digest, deterministic idempotency key, and delivery state. The initial v1 delivery states are `pending`, `delivered`, and `failed`; they report delivery only and never alter authoritative task lifecycle. Admission recovery durably enqueues effects before cleanup, but effect success is not part of task acceptance and cannot roll back an active task. A handler that cannot prove idempotent replay is unsupported and must remain disabled. Correctness-critical effects belong in the pre-commit file transaction rather than the outbox.

### 21.2 Atomic Task Archive

`task archive` is the only supported archive entry for an integrated task. It requires `lifecycle.status: completed`, the locked Trellis archive adapter, no live executor claim, satisfied mode-specific completion flags, an absent normalized archive destination on the same filesystem, and the expected integration revision. The adapter's locked destination function consumes immutable `task_id` plus admission-time `task_ref`, produces a grammar-valid path, and must be collision-free for distinct task IDs so later reuse of an active ref cannot overwrite an earlier archive. Direct Trellis finish/archive commands must be hidden or gated by the adapter; otherwise `task_archive_gate` is not `enforced` and `sol56-sdd` cannot materialize that platform.

While holding the runtime-state gate and task lock, the service atomically creates an `operation: archive` journal before changing the task. The journal records the active and archive refs, source-tree digest, integration preimage, candidate states, Trellis index/pointer preimages and candidates, directories created by the operation, and recovery runtime. It then transitions the integration state to `archiving`, with the archive transaction ID and destination, before moving any task content. An unfinished archive journal or any `archiving` state remains active for every safety gate.

The adapter applies its move, index, journal, and active-pointer operations with byte-and-mode CAS and atomic replacement. The task-directory rename to the archive ref is recorded explicitly but is not by itself a completed archive. After all Trellis metadata agrees with the destination, the service atomically transitions the integration file at the archive ref from `archiving` to `archived`, sets `archived_at`, increments the revision, and records the archive transaction ID. That integration-state rename is the archive commit point; only then may the task become non-gating.

Archive phases are:

```text
planned -> state_marked -> task_moved -> metadata_applied
        -> archive_committed -> cleanup_pending -> complete
```

Before the archive commit point, validated recovery may resume or roll back the journal, including reversing a directory move only when source/destination type, tree digest, integration state, and every Trellis metadata preimage still satisfy CAS. After the commit point, recovery may perform cleanup only. If external changes make either direction unsafe, automatic recovery stops with a manual-recovery report and the task remains gating. Trellis archive indexes, task location, integration lifecycle, and active pointers may never be accepted as partially consistent success.

Only reversible declared file operations are allowed before archive commit. The integrated overlay disables upstream finish/archive hooks, notifications, subprocess callbacks, network actions, and automatic Git commits during the transaction. Required Trellis journal or index changes must be explicit CAS-managed file candidates; an opaque archive command with additional side effects is not allowed. Automatic Git commit remains disabled entirely in v0.1.

Optional archive post-commit effects use the same non-authoritative task outbox contract as admission. Recovery durably enqueues them before cleanup with deterministic idempotency keys, but delivery success is not part of archive acceptance and cannot roll an `archived` task back to a gating state. A non-idempotent handler is unsupported, and any correctness-critical archive effect must be part of the pre-commit CAS-managed file transaction.

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

`task_admission_gate: enforced` specifically requires a mechanism that distinguishes a direct user confirmation from model-generated command input, offers no unwrapped non-interactive task-creation path, prevents `admitting` tasks from being resumed or executed, and suppresses upstream pre-commit hooks and automatic Git commits. `task_archive_gate: enforced` requires all supported Trellis finish/archive paths for integrated tasks to pass through the recoverable archive transaction. `provider_exception_approval: enforced` requires the same direct-human verifier boundary for `operation: approve-provider-execution`; model-authored JSON, command flags, stdin, or an instruction to self-approve cannot satisfy it. A plain prompt instructing the model to ask first or use the wrapper is only `instruction-only`.

Adapter capability manifests bind claims to adapter and harness versions. Each manifest contains a platform ID, adapter version, a non-empty list of exact tested harness versions or closed tested version ranges, the measured level of each capability, the probe used by `doctor`, and the integration-evidence identifier. A range may be declared only when every boundary version and the project's compatibility policy have been tested.

Profiles declare minimum levels. Materialization succeeds only when `actual >= required` for every selected platform. The strict `sol56-sdd` profile does not downgrade. Claude Code, Codex, and OpenCode all must pass version-bound integration tests at their required levels before they remain in `default_platforms` for v0.1.

Ordinary `doctor` inspects actual harness configuration only through read-only mechanisms and the post-verification command context from Section 20. It reads normalized explicit config paths or invokes the validated absolute harness path with a bounded read-only probe; it does not depend on the cache-side bootstrap `HOME` or ambient platform variables. For example, a Codex project hook that requires user-level feature enablement and one-time approval is not `enforced` until read-only evidence confirms both conditions; when confirmation itself would mutate state, ordinary `doctor` reports `unverified` and the explicit write-probe path must be used. Missing, stale, or inconsistent caller-context evidence lowers the result to `unverified` or blocks the relevant capability claim but cannot change release or wheel identity.

## 23. Provider and Third-party Execution Security

Provider sandbox controls are evaluated separately from ordinary platform-adapter capabilities. Authenticating an `approval-required` exception additionally requires the shared `provider_exception_approval` capability defined in Section 22. Each sandbox control is assigned one policy level:

- `required`: unavailable or failed enforcement blocks execution.
- `approval-required`: unavailable enforcement blocks until the user reviews a concrete risk report and approves auditable attempts of one immutable provider-execution plan within its bounded approval window.
- `best-effort`: the CLI attempts and reports the control but does not block solely because it is unavailable.

`sol56-sdd` requires temporary HOME/XDG directories, environment allowlisting, secret stripping, closed stdin, target-path isolation, time and output limits, archive/cache integrity, and baseline OS resource limits. Enforceable network isolation is approval-required. Enhanced namespace, seccomp, or container isolation is best-effort.

Before any third-party process starts, the Renderer creates a canonical provider-execution plan containing the provider and command digests, project and workspace identities, workflow-lock digest, input digests, requested controls, measured isolation gaps, a fresh random approval challenge, and a prospective transaction ID. An `approval-required` exception binds to that provider-plan digest, not to a final reconcile plan that cannot yet exist. The initializer result, approval record, sanitized diagnostics, and output digests then become inputs to the final reconcile plan, which still requires its separate apply approval.

Provider exception approval reuses the enforced direct-human verifier contract from Section 19 as a distinct closed branch:

```yaml
schema_version: 1
approval_id: approval-uuid
verifier_id: platform-approval-verifier
verifier_version: 1.0.0
platform: codex
harness_version: pinned-version
actor:
  id: platform-human-actor-id
  kind: direct-human
issued_at: 2026-07-13T15:00:00Z
expires_at: 2026-07-13T15:15:00Z
workspace_instance_id: clone-local-uuid
operation: approve-provider-execution
provider_plan_digest: sha256-value
risk_report_digest: sha256-value
prospective_transaction_id: transaction-uuid
approval_challenge: random-256-bit-value
verifier_receipt: opaque-platform-verifier-value
```

This branch rejects task ref, Route Decision, intent, or implementation-activation fields, while the task-admission branch rejects provider fields. The verifier receipt must authenticate the operation and every bound digest through the platform's supported direct-human confirmation channel. If the platform cannot prove `provider_exception_approval: enforced`, an `approval-required` provider plan blocks; a model-generated envelope or free-form terminal flag is never an approval substitute.

An approval is valid only for one immutable provider-execution plan digest, provider/version, workspace instance, prospective transaction identity, and finite approval window. It authorizes serialized, auditable retries of that exact plan when an attempt is interrupted or fails; it does not claim exactly one process invocation. Any changed command, inputs, controls, provider identity, workspace, prospective transaction, or expired approval requires a new approval and cannot become a persistent silent downgrade. Planning with such approval still performs no target-project writes.

Provider attempts use one schema-validated object at `<user-cache>/agent-workflow-pack/provider-attempts/<workspace-id>/<provider-plan-digest>.json`:

```json
{
  "schema_id": "agent-workflow.provider-attempts",
  "schema_version": 1,
  "workspace_instance_id": "clone-local-uuid",
  "provider_plan_digest": "sha256-value",
  "prospective_transaction_id": "transaction-uuid",
  "approval_digest": "sha256-value",
  "attempts": []
}
```

An immutable broker release receipt uses the sibling path `<provider-plan-digest>.releases/<attempt-id>.json` and this minimum schema:

```json
{
  "schema_id": "agent-workflow.provider-release-receipt",
  "schema_version": 1,
  "workspace_instance_id": "clone-local-uuid",
  "provider_plan_digest": "sha256-value",
  "prospective_transaction_id": "transaction-uuid",
  "attempt_id": "attempt-uuid",
  "release_token_digest": "sha256-value",
  "broker_liveness_identity": "platform-bounded-identity",
  "released_at": "2026-07-13T15:01:00Z"
}
```

The receipt path has an original-absence precondition, is written once by the trusted broker through temporary write plus atomic rename, and is never replaced or deleted as part of retry. A receipt grants no approval and cannot start a provider; at most it forces conservative recovery to acknowledge that release occurred.

The cache layer holds a plan-specific OS lock, reads and validates the entire object, applies one state change in memory, and commits it by same-filesystem temporary write plus atomic whole-file replace. It never physically appends bytes to JSON. Attempt states follow this closed graph:

```text
prepared -> released -> succeeded | failed | interrupted
prepared -> interrupted
```

Before writing `prepared`, the CLI starts a first-party trusted broker in a new process group or containment unit with private control and acknowledgement pipes. The broker loads no provider module, initializer entry point, provider arguments, or third-party code while waiting. On Linux/WSL it arms a parent-death signal and immediately rechecks the expected parent identity to close the fork/setup race. It also enforces a monotonic release deadline. Parent-pipe EOF, parent death, deadline expiry, a malformed token, or a duplicate release frame makes the broker close its descriptors and exit without executing provider code. The initiating parent retains the plan lock through terminal journal replacement; if it dies and releases the lock, the next holder must complete the receipt/liveness recovery checks before any retry.

The parent generates a fresh one-time release token and passes only its digest, attempt ID, broker/process-group liveness identity, `prepared_at`, release deadline, command digest, and isolation measurements into the new `prepared` attempt. After the whole attempt object is durably atomically replaced, and never before, the parent sends the one framed token. The broker accepts it exactly once, atomically creates an immutable attempt-scoped release receipt under the same cache namespace containing the attempt ID, token digest, broker identity, and `released_at`, acknowledges release, closes the control channel, and only then loads or executes the provider inside the recorded containment. The parent atomically advances the attempt to `released` after validating that receipt and acknowledgement. The broker never edits the whole attempt journal; the receipt is bounded recovery evidence, not supply-chain, approval, or target-project authority.

If the parent dies before valid release, pipe EOF, the parent-death signal, or the deadline terminates the waiting broker; the next lock holder may move `prepared` to `interrupted` only after validating receipt absence and positive evidence that the broker/containment is gone. If the parent dies after the token is accepted but before the journal records `released`, the immutable receipt proves that provider execution became possible: recovery first records `released`, then blocks while the recorded process group or containment is live or liveness is ambiguous. Parent loss after release triggers the broker's containment cleanup contract, but recovery still relies on positive process-group/containment evidence rather than assuming termination. PID reuse, a missing or mismatched receipt, an expired-yet-live broker, or indeterminate containment state blocks for diagnosis instead of permitting another attempt.

Normal completion atomically replaces the object with that attempt in `succeeded` or `failed` state plus exit category, sanitized-output digest, and validated candidate-output digest when present. A released provider that exits before a terminal journal update becomes `interrupted` only after positive evidence that the entire containment ended; unjournaled output is never accepted. Attempts for one plan never overlap. A retry must revalidate the unchanged plan, direct-human approval envelope, and unexpired approval. Corrupt journals or receipts, duplicate attempt or token identities, illegal state changes, or an approval/plan mismatch block rather than truncating or recreating state. The attempt journal and release receipt are audit/recovery evidence, not a supply-chain or target-project authority.

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

- stable machine error codes such as `AWP_OWNERSHIP_DRIFT`, `AWP_SOURCE_RELEASE_VERIFICATION_FAILED`, `AWP_WORKSPACE_MIGRATION_REQUIRED`, `AWP_WORKSPACE_SOURCE_METADATA_REQUIRED`, `AWP_WORKSPACE_CONTRACT_AHEAD`, `AWP_WORKSPACE_CONTRACT_DIVERGED`, `AWP_WORKSPACE_TASK_RECOVERY_BLOCK`, `AWP_WORKSPACE_ACTIVE_TASK_BLOCK`, `AWP_WORKSPACE_TASK_LAYOUT_AMBIGUOUS`, `AWP_WORKSPACE_LAYOUT_STATE_STRANDED`, and `AWP_TASK_QUIESCENCE_CHANGED`;
- stable exit-code categories;
- all paths repository-relative;
- URL userinfo and secret-bearing query values redacted;
- external stderr length-limited and centrally sanitized;
- human and JSON output derived from the same diagnostic objects;
- workspace mismatch output carries command-independent `workspace_state` and command-specific `command_admission` objects, never one overloaded blocker field.

Initial exit-code categories are:

| Exit | Category |
|---:|---|
| 0 | success or verified no-op |
| 2 | CLI usage or schema/input validation |
| 20 | ownership conflict or drift |
| 21 | recovery or workspace migration required |
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
- stale, cross-workspace or cross-intent copied, or field-tampered Route Decisions;
- every legal and illegal operation/route pairing in the closed Decision union;
- `classify-only` rejection by every execution loader;
- `execute-light` creating no Trellis task or integration state;
- executable operations rejecting a separate CLI signal list and binding Decision signals exactly to the Task Intent;
- `create-integrated-task` requiring both integrated route and approval proof;
- policy-consistent externally reconstructed envelopes receiving no issuer-origin privilege and being judged only by replay, freshness, and branch gates.

Natural-language classification evaluation may be added later as a non-blocking eval suite. Deterministic `test-routing` begins from normalized signal IDs and does not claim to detect omitted signals.

## 26. Test Strategy

### 26.1 Schema, Canonicalization, and Property Tests

Test duplicate YAML keys, inheritance cycles, unknown fields, JCS digests, set sorting, Merkle inputs, path normalization, POSIX-mode normalization, marker parsing, Release Identity, detached-manifest trust rules, release-compatibility edges, source static-metadata schemas, the closed Trellis task-discovery/layout union, segment and filename grammars, integration/metadata/journal parser-classifier identities, UUID task identity, historical task-ref reuse, task-surface registry IDs/digests, `task_contract_digest`, task-quiescence snapshots/findings/digests, scanner-versus-gate separation, candidate surface-impact normalization, the structured workspace-state/command-admission diagnostic, the saved-plan operation union, the complete acyclic `plan_core_digest -> journal_binding_digest -> candidate_manifest_digest -> plan_digest` graph, closed Route Decision branches, task/provider approval-verifier unions, caller-context envelopes, workspace-registration and workspace-migration journals, workspace/replay/outbox schema migrations, replay state transitions, provider-attempt journals and release receipts, and Manifest generations. A dependency-graph test rejects every digest-domain cycle, including a final `plan_digest` entering `journal_binding_digest` or candidate Manifest input and a workspace candidate deriving its contract from candidate Manifest bytes instead of the shared `plan_core` contract. Property/fuzz tests target path normalization, bounded metadata expansion, task-segment grammar, maximum depth/count/byte bounds, unknown-root entries, source/target task-root union and partitioning, surface-ID grammar and ordering, archive extraction, release-manifest URLs and redirects, general URL handling, caller-context field normalization, and marker parsers.

### 26.2 Resolver and Policy Tests

Test dependencies, conflicts, stable IDs, capability ordering, route rules, source-of-truth separation, Trellis runtime-namespace constraints, closed discovery/parser/classifier references, metadata-path cross-ownership rejection against every protected or artifact-managed path class, and every `evaluate_task_gate` operation/mode/snapshot/surface-impact combination. Golden policy cases include strict workspace migration; heavy contract-changing upgrade; Codex-adapter affected versus Claude-adapter unaffected Trellis-native tasks; `skill:tdd` affected versus unrelated-skill unaffected tasks; hook, agent, router, and runtime-entry changes; removed surfaces; before-digest mismatch; deterministic multi-blocker ordering; runtime-visible `sync --repair`; and true no-op `sync` with non-archived findings.

### 26.3 Golden Rendering

Snapshot Claude Code, Codex, and OpenCode output. Verify route-gated runtime content is absent from auto-discovery paths. Execute each locked initializer twice in independent isolated roots and compare both runs with its lock-bound content-root digest.

### 26.4 Reconciler Tests

Use temporary projects to test every ownership class, protected paths, symlink refusal, byte-and-mode CAS, executable-bit changes, repair, overlay retirement, single-file launcher authority, post-wheel descriptor validation, mixed launcher/descriptor preimage and candidate states, cold-cache launcher-bound bootstrap, transaction-created directory cleanup, atomic workspace-plus-ledger registration, lifecycle local-state migration, independent post-pull workspace migration, trusted static inspection of a source release without code execution, unfinished and corrupt/unknown-schema source task journals, strict workspace-migration non-archived blocking, mode/surface-sensitive lifecycle gating, true no-op sync with non-archived findings, unknown task-root files/directories, invalid task segments, excess scan depth/count/size, metadata pointer/index schema disagreement, source-only archived tasks, source-only nonempty metadata, target-only task state, layout changes whose one-sided state is entirely absent/canonical-empty, same-clone current/candidate layout changes, verified `ahead` with unsupported discovery parser, invalid authenticated relationship schema with exit 30, separate workspace-state and per-command admission diagnostics, supply-chain mismatch exit-30 behavior, deterministic state/evaluator blocker priority across launcher/`doctor`/migration, every saved-plan operation and digest branch, cross-clone saved-plan refusal, saved-plan staleness, read-only `doctor`, explicit write-probe cleanup and interruption, filesystem capability refusal, and no-write conflict behavior.

### 26.5 Crash and Concurrency Tests

Inject process termination at each Reconciler, workspace-registration, lifecycle local-state migration, independent workspace-migration, task-admission, and task-archive phase. Terminate immediately before and after the launcher rename and immediately before and after the descriptor rename, and verify every resulting recorded old/new combination can start its exact wheel and enter only the matching recovery path. Test two CLI writers, two admissions for one task ref, forced duplicate task IDs across different refs, task-ref reuse after a completed archive with distinct task IDs, duplicate approval proofs with different transaction IDs, crash after the planned journal but before replay reservation, rollback crashes between CAS-creating `reserved` and CAS-transitioning it to `consumed`, same-transaction resume after proof expiry, consumed tombstones, missing/corrupt-ledger fail-closed behavior, two claimants at the same revision, task mutation against maintenance admission, admission crash around task move, metadata application, and the `admitting -> active` commit, archive crash around the task-ID-derived destination move and integration commit, task-transaction blocking, outbox replay idempotency, lifecycle local-state migration after each candidate write and around Manifest commit, workspace migration after each replay/outbox write and around the final workspace commit rename, post-pull scans with an unfinished source-release admission/archive journal, a task under source-only or target-only roots, a non-archived task under either archive root, source-only archived/metadata state, and source/target interpretation ambiguity, disabled pre-commit hooks and Git auto-commit, cache contention, external byte or mode modification immediately before rename, manifest-committed cleanup, immutable maintenance binding across mutable journal-phase updates, and CAS rollback refusal. For both lifecycle upgrade and workspace migration, create or alter a task, integration file, metadata pointer/index, and task journal after the initial scan but before the final Manifest or `workspace.json` rename; every case must produce `AWP_TASK_QUIESCENCE_CHANGED` as the primary error, retain any newly produced active/recovery/ambiguity/stranded findings as secondary diagnostics, preserve the pre-commit recovery boundary, and refuse commit.

Bootstrap tests run both the project launcher and canonical first-install command with no compatible Python, malicious project and user `uv.toml`, a hostile `.env`, injected `UV_INDEX` and Python-selection variables, an installed global same-name tool, empty and populated controlled caches, and redirect/hash failures. They assert that uv receives only its fixed clean environment, uses absolute validated uv and local-Python paths, downloads no Python or secondary package/build artifact, ignores ambient configuration and tools, and either starts the exact hash-bound wheel or fails closed. Separate post-verification tests supply real user config roots, a pinned harness executable, and TTY capability through the non-sensitive caller envelope and prove that `doctor` observes the actual harness configuration without exposing those values to uv or accepting secret/proxy/token fields.

Provider tests serialize concurrent attempts, validate whole-file atomic replacement and immutable release-receipt creation, and inject `SIGKILL` after broker creation, after durable `prepared`, immediately before token send, after token send, after token receipt/receipt creation, while provider code runs, and after provider exit but before terminal journal replacement. They prove EOF, Linux parent-death signaling, release deadline, malformed tokens, and duplicate frames terminate the unreleased broker without provider execution; a receipt-backed release is never mistaken for pre-release; live or ambiguous containment blocks retry; and `interrupted` is recorded only after positive liveness evidence. They permit auditable retry only for the unchanged plan while approval remains valid, require a direct-human `approve-provider-execution` verifier receipt, reject model-authored or cross-branch envelopes, and require new approval for any changed or expired plan.

### 26.6 End-to-end Sequence

```text
clone A: init
  -> doctor
  -> test-routing
  -> no-op sync
  -> route decide + direct approval
  -> injected task-admission crash while admitting + task recover
  -> assert metadata consistency before active commit
  -> drift conflict
  -> assert zero writes
  -> injected crash during apply
  -> doctor reports recovery-required
  -> recover --resume / recover --rollback
  -> true no-op sync reports task findings but remains a verified zero-write no-op
  -> heavy active-task contract-changing upgrade block
  -> mark task completed
  -> assert completed heavy task still blocks the same contract-changing upgrade
  -> injected task-archive crash + task recover
  -> archive task completely
  -> admit a new task at the same active ref with a distinct Decision-bound random task ID
  -> assert both archived/current integrations retain unique identities and no scanner ambiguity
  -> archive the replacement task before continuing
  -> candidate layout fixture exposes a target-only task and blocks same-clone upgrade through the shared quiescence scanner
  -> remove the fixture, replan, and bind the current/candidate task-quiescence snapshot
  -> approved upgrade with injected lifecycle local-state migration crash
  -> recover lifecycle migration under CAS
  -> external metadata change before Manifest rename reports AWP_TASK_QUIESCENCE_CHANGED and remains rollback-capable
  -> restore the journal-bound snapshot and resume
  -> complete approved upgrade and commit project-scoped files
clone B: pull clone A commit
  -> launcher detects differing source/target local contracts
  -> workspace migrate statically verifies the R0 manifest, compatibility bundle, complete task-discovery layout, integration/metadata schemas, and task-journal phase contract without executing R0 code
  -> unfinished R0 admission/archive journal fixture blocks workspace migrate
  -> diagnostic requires restoring the R0 project checkout and completing task recovery there
  -> assert pulled R1 state cannot authorize the R0 recovery runtime
  -> restore R0 checkout, recover transaction, complete and archive task, then pull R1 again
  -> non-archived task under the R0-only active root blocks workspace migrate
  -> an archived task or nonempty index under an R0-only archive/metadata path reports AWP_WORKSPACE_LAYOUT_STATE_STRANDED
  -> changed or ambiguous R0/R1 discovery/schema contracts block rather than skipping source state
  -> reset to a fixture whose one-sided roots and metadata are absent/canonical-empty, then pull R1 again
  -> assert only diagnostics, workspace migrate, and currently allowlisted recovery are allowed
  -> injected workspace-migration crash after replay/outbox candidate
  -> recover --workspace-migration under CAS
  -> external task-journal creation before final workspace rename reports AWP_TASK_QUIESCENCE_CHANGED
  -> restore the journal-bound snapshot and resume
  -> commit final workspace.json contract
  -> doctor and no-op sync resume normally
clone C: pull a target with no source-to-target edge
  -> target statically fetches and verifies source release metadata without executing it
  -> verified reverse-only edge reports AWP_WORKSPACE_CONTRACT_AHEAD
  -> unsupported source Trellis parser leaves discovery ambiguous but still reports the verified ahead relationship
  -> unreachable contracts report AWP_WORKSPACE_CONTRACT_DIVERGED
  -> unavailable relationship bytes report AWP_WORKSPACE_SOURCE_METADATA_REQUIRED
  -> source manifest/hash/bundle-root mismatch reports AWP_SOURCE_RELEASE_VERIFICATION_FAILED with exit 30
  -> hash-authenticated but schema-invalid relationship metadata reports relationship_evidence invalid and AWP_SOURCE_RELEASE_VERIFICATION_FAILED with exit 30
  -> launcher, doctor, and migrate emit identical workspace_state dimensions and primary_state_blocker
  -> doctor remains command-admitted for read-only reporting while workspace migrate and ordinary writes are rejected
  -> all outcomes remain read-only and do not apply a workspace migration
```

A sanitized, synthetic snapshot derived from the current sibling `workflow-pack` structure is committed under `tests/fixtures/`. It preserves the relevant Trellis, router, skill, and ownership-conflict shapes without copying personal journals, local developer identity, caches, or unrelated documents. Tests prove that `.trellis/tasks/`, `.trellis/workspace/`, `.trellis/spec/`, and Spec Kit feature artifacts are not claimed at directory scope.

## 27. Packaging and Release

Build and test both wheel and sdist. Installation tests run from the built artifacts, not only from a source checkout. Package-data tests verify inclusion and exact digests of profiles, catalogs, schemas, compatibility metadata, runtime-launcher templates, artifact definitions, overlays, custom skills, licenses, and notices.

The sdist contains the same vendored runtime sources as the wheel. Release CI builds both artifacts in the `uv.lock`-controlled build environment and verifies that the wheel metadata has an empty external runtime `Requires-Dist` set. Build-system dependencies remain build-time concerns and are not represented as consumer runtime reproducibility.

Cross-distribution rendering compares a `distribution_render_digest`: the deterministic Merkle root of managed artifact paths, rendered bytes, normalized modes, Release Identity, and profile/lock/artifact-bundle-derived content. Git checkout, wheel, and sdist tests supply the same verified detached release manifest, so asset-derived launcher fields are identical without placing asset hashes inside the distributions. The digest excludes Manifest generations, project and workspace UUIDs, target-path identities, transaction IDs, approval evidence, maintenance state, probe evidence, and ignored local state. Tests that compare a complete plan or tree must inject a deterministic identity provider; AC-14 does not require independently generated runtime identities to be byte-equal.

Release CI first fixes the Release Identity and all bundle roots, then builds the wheel and sdist. Only after both distributions are final does it compute their byte hashes and sizes, generate the detached `release-manifest.json`, and publish all three assets to the exact repository and tag required by the trust policy. It then verifies the GitHub release is immutable. The detached manifest is never rebuilt into either distribution.

The canonical end-user bootstrap command is generated from the verified detached manifest and uses the same Section 20 isolation contract as the project launcher: resolved absolute release-supported uv and compatible local-Python paths, `env -i`, cache-side `HOME`, fixed locale/timezone, `--isolated`, `--no-config`, `--no-env-file`, `--no-index`, `--keyring-provider disabled`, `--no-sources`, `--no-build`, `--no-python-downloads`, the exact Python path and controlled cache, and the manifest-bound direct wheel URL plus SHA-256. Its release-fixed shell renderer captures only the same non-sensitive caller-context envelope before clearing the environment and passes that envelope as dedicated CLI arguments. It has no alternate index, latest-version, global-tool, Python-download, source-build, or secondary dependency fallback.

Release acceptance verifies the immutable GitHub release and manifest before executing that command. A source-audit command may use the full source commit directly but must compute the same Release Identity; acceptance still executes the built wheel and sdist rather than relying only on a checkout. A movable ordinary tag, project-supplied URL, or unverified manifest is never a trust anchor.

First installation is the sole user-selected bootstrap boundary: the user obtains that hash-bound command from the pinned repository's immutable release. Before Python CLI startup, uv/uvx downloads the exact direct-wheel URL and verifies the original wheel-container bytes against the detached-manifest-bound SHA-256 fragment; hash failure prevents any package code from running. After startup and before `init` performs any target write, the CLI independently retrieves and verifies the detached manifest through its packaged trust policy and confirms its packaged Release Identity, source commit, trust-policy identity, package/version metadata, and bundle roots. It also verifies that the managed/bootstrap wheel URL and hash fields agree with the detached manifest, but it does not claim to possess or re-hash the original wheel container or independently confirm its byte size. Release CI and the detached manifest record the asset name and size; runtime byte identity is enforced by the exact immutable URL and SHA-256, not by a separate pre-start size assertion. Later project launch and upgrade never accept a new release location from user-controlled project state.

Release gates require:

- wheel, sdist, and Git-checkout `distribution_render_digest` values are identical;
- wheel, sdist, and Git checkout compute one Release Identity, while their detached manifest binds the final distribution hashes without being packaged inside them;
- `launcher_bundle_digest` contains only release-neutral templates, schemas, and verifier logic, while detached-manifest substitutions affect only rendered-launcher and distribution-render digests;
- saved-plan fixtures prove the digest dependency graph is acyclic and that the final approved `plan_digest` binds the derived candidate Manifest without entering `journal_binding_digest`;
- release-manifest verification rejects the wrong repository, tag, mutable release, redirect host, asset name/size/hash, source commit, or bundle identity;
- both the cold-cache project launcher and canonical first-install command succeed using only declared `sh`, `env`, release-supported `uv`/`uvx`, and an installed compatible Python; their fixed isolated uv invocation ignores ambient configuration, downloads only the embedded hash-bound wheel, verifies the wheel-container SHA-256 before CLI startup, and never downloads Python or another package/build artifact. The started CLI then verifies packaged Release Identity, source commit, trust-policy identity, package/version metadata, bundle roots, project state, descriptor, and journals before command dispatch without claiming independent access to the original wheel container;
- after verification, caller-context tests prove `doctor` can inspect the real user-level harness configuration while uv never receives platform config, credentials, proxy secrets, or the original environment;
- process termination at every launcher/descriptor rename boundary leaves a journal-recorded preimage/candidate combination from which the exact started CLI can enter only diagnostics or matching recovery;
- recovery journals containing URLs, hashes, trust-policy overrides, or runtime identities outside the committed/candidate allowlist are rejected before execution;
- all default platforms meet their profile-required capability levels;
- a clean WSL/Linux environment initializes from the published artifact;
- a fresh clone runs `workspace register` and `route decide` through the project launcher with cache-hit, permitted pinned-redownload, offline-miss, hash-mismatch, version-mismatch, and unfinished-transaction recovery cases;
- a previously registered second clone can pull a differing committed Manifest, statically verify the source release and complete source/target Trellis discovery contracts without executing source code, block migration on every unfinished task transaction, non-archived task, ambiguous interpretation, or stranded one-sided archive/metadata state, bind and revalidate the shared quiescence digest through workspace commit, and leave project-scoped task authorities unchanged;
- maintenance remains valid across mutable transaction-journal phase changes because it binds only the immutable journal header;
- every supported local-state schema transition passes per-stage crash, CAS rollback, and Manifest-commit recovery tests without resetting workspace, replay, or outbox state;
- provider approval tests prove direct-human-authenticated auditable retry semantics for one unchanged plan, whole-file attempt-journal recovery, broker release-receipt recovery, and rejection of model-authored, changed, expired, cross-workspace, cross-operation, or overlapping attempts;
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

- **AC-01:** A clean WSL/Linux target initializes through the exact self-contained wheel selected by a detached manifest from the pinned GitHub repository's immutable release. Before package code starts, uv/uvx verifies the downloaded wheel-container bytes against the manifest-bound direct-URL SHA-256. After startup, the CLI verifies packaged Release Identity, source commit, trust-policy identity, package/version metadata, and bundle roots against the detached manifest without claiming independent access to the original wheel container; the corresponding sdist passes the same applicable trust and installation scenario.
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
- **AC-12:** The shared scanner reports task facts without choosing command policy. `evaluate_task_gate` consumes operation, normalized candidate surface impact, the complete task snapshot, and findings. Every non-archived heavy task blocks a contract-changing upgrade, while a non-archived Trellis-native task blocks only when a stable changed surface ID and before-digest match one of its exact pinned Trellis, routing, adapter, hook, agent, skill, or runtime-entry surfaces.
- **AC-13:** Disabled or gated pack-managed skills are neither auto-discoverable nor transitively referenced by discoverable leaves.
- **AC-14:** Wheel, sdist, and Git-checkout renders use one logical Release Identity and the same verified detached manifest, producing identical `distribution_render_digest` values over managed profile/lock/bundle-derived output; clone-local and transaction identities are excluded.
- **AC-15:** Provenance, full licenses, notices, lock hashes, and target notices are complete for every projected third-party artifact.
- **AC-16:** JSON output, exit codes, and redaction pass their versioned contract tests.
- **AC-17:** The legacy `workflow-pack` migration fixture retains all protected Trellis and Spec Kit runtime state.
- **AC-18:** `upgrade --to` rejects every target absent from the explicit directed compatibility matrix and verifies the target detached manifest, distribution hash, Release Identity, and static compatibility metadata before candidate code runs.
- **AC-19:** File-state CAS detects byte, type, symlink, and POSIX-mode changes, including executable-bit drift.
- **AC-20:** Write commands refuse filesystems that fail advisory-lock, atomic-replace, mode, or path-collision probes; `/mnt/*` receives no implicit exemption.
- **AC-21:** Concurrent executor claims at one base revision result in exactly one successful atomic state transition.
- **AC-22:** A model-generated Route Decision or command flag cannot satisfy the enforced user approval required by `task admit`.
- **AC-23:** A fresh clone must register a new local workspace identity before writes, and a saved plan from another clone is rejected by default.
- **AC-24:** With no cached detached manifest, a fresh clone can bootstrap the launcher-bound exact wheel using only declared `sh`, `env`, a release-supported `uv`/`uvx`, and installed Python `>=3.11,<3.15`. The launcher uses absolute validated tool paths, a fixed cleared environment, and the specified isolated/no-config/no-index/no-sources/no-build/no-Python-download uv arguments; malicious `uv.toml`, `.env`, `UV_*` values, global same-name tools, or absence of compatible Python cannot change resolution or cause a second download. The pinned CLI then verifies the packaged trust policy, detached manifest, Manifest, descriptor, journal, and workspace contract before constructing any command-specific caller context.
- **AC-25:** Every `create-integrated-task` Decision and approval proof binds one random canonical task ID, task ref, task-surface digest, intent, operation, workspace, and one-time challenge. The canonical calculator generates the ID, while loaders enforce binding and uniqueness without claiming unsigned-decision issuer authenticity. The task shell and integration revision 1 commit through the specified admission transaction; every admission or archive crash point is diagnosable, recoverable under CAS, and blocked from becoming a partially accepted task state.
- **AC-26:** Ordinary `doctor` and every `--dry-run` perform zero target writes. Filesystem mutation probes run only through explicit `doctor --write-probe` or inside an approved apply transaction after lock acquisition, and interrupted probe residue is tracked and safely recoverable.
- **AC-27:** `completed` remains a non-archived finding and receives the same mode/impact evaluation as other unfinished lifecycle states; it cannot evade a blocker merely because implementation finished. Only `archived` is categorically non-gating, while an unaffected Trellis-native task follows AC-12 rather than a stricter scanner rule.
- **AC-28:** A locked initializer whose candidate content-root digest is unstable or differs from its lock-bound contract blocks both release and runtime materialization rather than becoming a silent file diff.
- **AC-29:** No wheel, sdist, source commit, compatibility bundle, or Release Identity contains its own container or bundle hash. Only the verified detached manifest binds distribution hashes, and transaction journals cannot introduce release URLs, hashes, or trust-policy overrides.
- **AC-30:** Route Decision validates as exactly one of `classify-only`, `execute-light`, or `create-integrated-task`; illegal route/operation or cross-branch fields produce no executable Decision, and policy replay guarantees only the result for supplied signal IDs, not issuer authenticity or natural-language signal completeness.
- **AC-31:** A newly moved task remains `admitting` and non-runnable until all declared Trellis metadata matches its CAS candidate and integration atomically transitions to `active`. Admission and archive pre-commit phases allow only reversible declared file operations; hooks, notifications, subprocess callbacks, network actions, and Git auto-commit cannot create untracked side effects. Optional post-commit effects use the idempotent non-authoritative outbox and cannot alter the committed lifecycle state.
- **AC-32:** Approval verifier envelopes bind direct-human actor, supported verifier/harness version, workspace, decision, challenge, task ID/ref, intent, and finite validity window. A transaction-independent proof key can bind at most one transaction through `absent -> reserved -> consumed`; initial reservation occurs within TTL, same-transaction recovery may continue after expiry, the journal-before-reservation crash window is recoverable, and a committed workspace with missing or corrupt ledger state fails closed.
- **AC-33:** Trellis active/archive roots and metadata paths pass cross-ownership validation. Bounded declarations expand to a finite journal-recorded exact set, and the Task-state Service cannot write an artifact-managed, control-plane, Git, Spec Kit, source, unrelated user-owned, or unplanned path.
- **AC-34:** Saved plans validate as exactly one operation branch: `init` has no installed release, `sync` and `repair` require identical installed/candidate releases, and `upgrade` permits a difference only through a verified directed compatibility edge.
- **AC-35:** Detached-manifest-derived launcher substitutions and their renderer version affect `render_digest`, `applied_file_hash`, and `distribution_render_digest` but are absent from `launcher_bundle_digest`; release CI rejects every launcher-bundle reference or input that recreates a distribution or manifest digest cycle.
- **AC-36:** The launcher is the sole pre-wheel authority and is switched by one atomic file rename. The descriptor cannot block wheel startup and is validated only by the pinned CLI. Termination at every launcher and descriptor rename boundary leaves only journal-recorded preimage/candidate file states from which matching recovery succeeds; an unrecorded third state fails closed.
- **AC-37:** Maintenance binds `journal_binding_digest` over the immutable transaction header, and the committing Manifest records the same digest. Mutable phase, applied-file, diagnostic, retry, and rollback updates neither invalidate nor require rewriting the marker, while any change to a bound header field is rejected.
- **AC-38:** First init, workspace registration, lifecycle compatibility migration, and independent `workspace migrate` are the only writers to local state besides ordinary Task-state Service transitions. Lifecycle migration applies exact candidates before Manifest commit; workspace migration modifies only ignored local files and commits by the final workspace rename. Both journal exact preimages/candidates, support pre-commit CAS rollback at every crash point, and never repair failure by recreating empty state.
- **AC-39:** Replay rollback from a durable admission journal with no ledger entry performs the legal two-step `absent -> reserved -> consumed` transition for the same transaction. A crash between those CAS writes can only resume consumption and can never make the proof reusable.
- **AC-40:** An `approval-required` provider approval authorizes serialized, audit-journaled retries only for one unchanged immutable provider plan, provider/version, workspace, prospective transaction, and validity window. Changed or expired plans require new approval, concurrent attempts do not overlap, and interrupted attempt evidence is retained.
- **AC-41:** Saved plans implement the normative acyclic dependency chain `plan_core_digest -> journal_binding_digest -> candidate_manifest_digest -> plan_digest`. The final plan binds the exact candidate Manifest, `journal_binding_digest` never consumes final `plan_digest`, workspace and Manifest candidates independently render one shared `plan_core` local-state contract, and dependency-graph cycle tests reject any self-reference or reverse edge.
- **AC-42:** After clone A upgrades and commits project-scoped authorities, registered clone B can pull them, statically verify its recorded source release and classify the differing ignored source contract against the committed target contract, and run or recover `workspace migrate` only through the exact verified source-to-target edge. Until commit, only diagnostics, workspace migration, and recovery authorized by the current runtime allowlist are permitted; migration never changes the Manifest or treats B as an unregistered clone.
- **AC-43:** Project launch and first-install bootstrap keep uv in the fixed clean environment while passing only a schema-allowlisted, non-sensitive caller-context envelope to the pinned CLI. After all authority checks, `doctor` can observe the real supported harness/config context; tokens, credentials, proxy secrets, arbitrary environment, and platform config never influence wheel selection.
- **AC-44:** Provider attempt state is one schema-validated `{attempts: [...]}` JSON object updated only by whole-file atomic replacement under its plan lock. Attempts follow the closed `prepared -> released -> terminal` protocol with an immutable broker release receipt; live or ambiguous containment blocks retry, `interrupted` requires positive liveness evidence, and corrupt or illegal state never triggers truncation or empty recreation.
- **AC-45:** `approve-provider-execution` is a closed direct-human verifier branch binding provider plan, risk report, workspace, prospective transaction, challenge, actor, verifier/harness version, and finite validity. Model-authored input, task-approval fields, or a platform below `provider_exception_approval: enforced` cannot authorize execution.
- **AC-46:** Active-task and upgrade gates report their checkout-local scope and do not claim to detect tasks present only in an unsynchronized clone, branch, or unpushed commit.
- **AC-47:** A post-pull `workspace migrate` scans all checkout-visible task journals under the exclusive runtime-state gate. Any unfinished source-release task transaction blocks with `AWP_WORKSPACE_TASK_RECOVERY_BLOCK`, identifies its pinned release, and instructs recovery under a matching old project checkout; the pulled target Manifest or compatibility edge cannot authorize that old runtime.
- **AC-48:** v0.1 has no retained-runtime resume branch. Every checkout-visible non-archived task blocks `workspace migrate` with `AWP_WORKSPACE_ACTIVE_TASK_BLOCK`, regardless of mode or apparent contract compatibility. The task must be recovered, completed, and archived under the source release; migration never rewrites or resumes it, and the separately required layout-preservation check may still block an archive that the target would strand.
- **AC-49:** The provider broker executes no third-party code until a durable `prepared` attempt is followed by one valid release token and immutable release receipt. EOF, parent death, deadline, malformed/duplicate token, and `SIGKILL` at every handshake boundary either prove no release or preserve release/liveness evidence; no orphaned or ambiguous broker permits a retry.
- **AC-50:** Wheel verification responsibility is split at process startup: uv/uvx verifies the actual downloaded wheel-container SHA-256 before CLI execution, while the CLI verifies only packaged identity and bundle claims plus their detached-manifest agreement. Asset size is release-manifest/CI metadata rather than a separate uv bootstrap assertion, and no release gate requires a running CLI to recover, size, or hash its original wheel container without a separately specified attestation channel.
- **AC-51:** Workspace contract mismatch uses exact directed graph relationships, never version-string ordering. A target-owned source-to-target edge establishes verified `migration-required`; a reverse-only result reports `AWP_WORKSPACE_CONTRACT_AHEAD` after static verification of source relationship evidence even if source task-discovery parsers are unsupported; two verified missing directions report `AWP_WORKSPACE_CONTRACT_DIVERGED`; missing relationship bytes report `AWP_WORKSPACE_SOURCE_METADATA_REQUIRED`; hash-authenticated but schema/semantically invalid relationship evidence reports `AWP_SOURCE_RELEASE_VERIFICATION_FAILED` with exit 30 instead of guessing.
- **AC-52:** `workspace.json` records the verified source detached-manifest digest and normalized Trellis task-layout snapshot. Post-pull migration revalidates that snapshot from source static metadata and scans the union of source and target active/archive roots; a source-only task, target-only task, non-archived archive entry, root collision, or ambiguous partition blocks with no local-state migration.
- **AC-53:** `trellis_task_layout` is a closed, digest-bound discovery contract covering task hierarchy and segment grammar, exact task recognition, integration schema/location, unknown-entry policy, hard scan limits, metadata parser/classifier semantics, and task-transaction filename/schema/phase classification. Unknown, corrupt, oversized, over-depth, over-count, symlinked, or unsupported state produces explicit ambiguity evidence rather than being skipped or truncated; write-command blocking is decided by the evaluator.
- **AC-54:** When source and target layout digests differ, v0.1 performs no Trellis state migration. Every nonempty source task/archive/metadata object must remain target-recognized at the same path and semantic role; source-only archived or nonempty metadata state and target-only task state block with `AWP_WORKSPACE_LAYOUT_STATE_STRANDED`, while contract-permitted absence or classifier-proven canonical-empty one-sided state may pass.
- **AC-55:** Same-clone lifecycle commands and post-pull `workspace migrate` invoke the same `scan_task_quiescence` implementation over verified source/target layouts and schemas. It returns only canonical snapshot/findings across active/archive partitions, metadata objects, and task journals. A separate versioned `evaluate_task_gate(operation, candidate_impact, snapshot, findings)` applies strict workspace-migration policy, mode/surface-sensitive lifecycle policy, deterministic multi-blocker ordering, and the zero-write no-op sync exception; current-only scanners or command-specific fallback parsers cannot satisfy either layer.
- **AC-56:** The canonical task-quiescence snapshot and digest are bound into the lifecycle plan and immutable journal header and into the workspace-migration journal before local writes. The exact scanner reruns after lock/maintenance acquisition and immediately before Manifest or `workspace.json` commit; any mismatch returns `AWP_TASK_QUIESCENCE_CHANGED` as the unconditional command primary error, retains latest task findings only as secondary diagnostics, and remains pre-commit CAS-recoverable.
- **AC-57:** Launcher, `doctor`, and `workspace migrate` emit one structured diagnostic with command-independent `workspace_state` dimensions and `primary_state_blocker`, plus a separately derived per-command `command_admission`. The same verified bytes produce identical workspace state, while `workspace migrate` or `doctor` may be admitted with a null command blocker even when the state blocker remains non-null.
- **AC-58:** Stable task identity is the immutable Decision- and approval-bound canonical UUID in `integration.admission.task_id`, distinct from admission-time ref and current active/archive path. Admission rejects duplicate IDs across active/archive integrations and unfinished journals; after a committed archive, the same active ref may be reused only with a new task ID and a collision-free task-ID-derived archive destination. `task_contract_digest = SHA256(UTF8("agent-workflow.task-contract.v1\0") || UTF8(JCS(normalized_workflow_contract)))` remains domain-separated and includes the exact task surface set.
- **AC-59:** `task_contract_surfaces` and `candidate_impact.surface_changes` use one closed registry of stable surface IDs and complete digests. Adapter-specific and skill-specific affected cases block, unrelated surfaces do not, removed surfaces use canonical null, before-digest mismatch fails closed, and the full evaluator input/result is plan-bound.
- **AC-60:** `relationship_evidence: invalid` is a closed state for cryptographic trust failure or hash-authenticated relationship/compatibility schema or semantic failure. Its state blocker and write-command blocker are `AWP_SOURCE_RELEASE_VERIFICATION_FAILED` with exit 30; it is never reported as missing metadata, migration-required, ahead, or diverged.

## 31. Deferred Implementation Decomposition

Only after unconditional design approval may separate feature specs be created in this order:

1. **Core schemas and Resolver** — profiles, catalog, locks, canonicalization, artifact definitions, acyclic saved-plan digest envelope, local-state schemas, IR, policy graph, and diagnostics.
2. **Providers and secure cache** — acquisition, isolation, direct-human exception approval, trusted broker release handshake, whole-file attempt journals and immutable release receipts, verification, extraction limits, provenance, and cache concurrency.
3. **Renderer and Reconciler** — staging, ownership, operation-discriminated plans, OS lock, CAS, transactions, repair, and recovery.
4. **Runtime launcher and Task-state Service** — single-file launcher cold bootstrap, split pre-start container/post-start package verification, two-stage caller context, post-wheel descriptor validation, pinned runtime delivery, atomic workspace/ledger registration, source-static-metadata verification, split workspace-state/command-admission diagnostics, the shared bounded Trellis quiescence scanner and snapshot/surface-aware task-gate evaluator, strict no-active-task/no-stranded-state cross-clone workspace migration, versioned replay ledger and outbox, UUID task identity and safe ref reuse, integration union, task locks and CAS, claims, admitting/archive transactions, recovery, and maintenance coordination.
5. **Route admission and Platform Adapters** — compiled admission policy, closed Route Decision union, intent-bound executable signals, approval-verifier envelopes, runtime catalog and loaders, Trellis root/metadata cross-ownership contracts, capability probes, adapter projection, and platform golden output.
6. **Lifecycle, packaging, and release** — CLI commands, JSON contracts, detached release manifests, immutable-repository trust policy, local-state compatibility edges, upgrade flow, E2E tests, artifact builds, trust anchors, and notices.

Each feature spec must preserve the authority boundaries and acceptance criteria in this document. No feature spec may introduce a second planner, executor, route-policy source, ownership source, or task-state source.

## 32. Design Risks

- Strict enforcement may delay a platform's inclusion in `default_platforms`; the profile must not silently downgrade.
- Third-party initializer execution remains higher risk than static extraction even with isolation; the capability report must remain honest.
- WSL-mounted filesystems may provide weaker durability semantics; v0.1 promises process-crash recovery only.
- Upstream platform and Trellis templates may change paths or hook behavior; adapter and harness versions therefore remain locked and tested.
- Trellis-derived overlays and generated content require artifact-level provenance and license handling rather than a repository-wide assumption.
- The project launcher is a same-user-writable shell file. The design detects supply-chain substitution, accidental drift, and inconsistent upgrades, but executing a maliciously modified checkout is outside its trust boundary because that launcher can run before project-state verification. When tampering is suspected, read-only verification must use the external canonical `uvx` command derived from the verified detached manifest rather than any executable from the checkout.
- Checkout-local task gates cannot see work that another clone has not synchronized. Operational policy must require coordination before contract-changing upgrades; v0.1 does not provide distributed locking or a remote task registry.
- Caller-context forwarding deliberately exposes only normalized non-sensitive paths and capability facts after release verification. Platform adapters must keep their allowlists narrow so harness inspection does not become an ambient-environment or credential channel.
- v0.1 deliberately refuses transparent task resume across a pulled release contract. This may require users to restore an earlier checkout to finish/archive work before migration, but avoids shipping a second content-addressed runtime catalog and compatibility loader before those contracts are separately designed.

The twelfth-version architecture remains stable, but this candidate is still `Changes required` until the snapshot/surface-complete evaluator, UUID task identity with safe ref reuse, split workspace-state/command-admission diagnostic, and invalid-relationship error contract receive focused reviewer approval. Implementation planning and feature-spec decomposition remain prohibited until that confirmation.

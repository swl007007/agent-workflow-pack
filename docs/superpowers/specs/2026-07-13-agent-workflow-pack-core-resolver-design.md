# Agent Workflow Pack Core Schemas and Resolver Design

**Status:** Approved
**Approval:** Explicit user approval on 2026-07-13
**Umbrella spec:** 2026-07-13-agent-workflow-pack-design.md
**Umbrella baseline:** commit 568689d3fa4f9a39500b2b0a294387db02a0fccc, content SHA-256 c2f23807cc36066b4b92478657cacaf15eb5cb6bd14e307e1e76f1c30de0284d
**Decomposition authority:** 2026-07-13-agent-workflow-pack-feature-spec-decomposition.md at approval commit 1cd99f9767af3f20e4f0c7776f8a1cb7f3c126b2
**Implementation gate:** No implementation until this feature spec and its implementation plan are separately approved

## 1. Scope and Non-goals

This feature owns the closed schemas, canonical projections, digest recipes, pure resolution rules, impact model, task-state evaluation policy, and diagnostic objects that later features consume. It is the only feature allowed to define:

- schema identity/version registration and canonicalization rules;
- profile resolution, catalog closure, capability comparison, artifact-policy validation, and protected-path validation;
- the runtime-surface registry, runtime-visible-unit inventory, surface digest recipes, reference graph, and full-coverage proof contract;
- Desired State IR and normalized candidate impact;
- TaskSnapshot and TaskFindings schemas plus the two pure task-state evaluators;
- the SavedPlanEnvelope schema and acyclic digest dependency graph;
- workspace-state and command-admission diagnostic schemas;
- the Core/Resolver/workspace diagnostic error namespace;
- the schema branches for CapabilityManifest, RouteDecision, ApprovalProof, render projection, and ownership-decision objects that downstream features implement or populate.

This feature does not:

- fetch providers or release assets;
- render or write target files;
- implement scan_task_quiescence;
- implement render_saved_plan;
- acquire project locks, create journals, apply CAS, or recover transactions;
- mutate integration state, replay ledgers, task outbox items, or Trellis metadata;
- calculate platform Route Decisions, verify platform approval receipts, or generate wrappers;
- compose CLI commands, packaging, release publication, or end-to-end orchestration.

Implementation ownership remains:

| Contract | Definition owner | Implementation owner |
|---|---|---|
| resolve and compute_candidate_impact | Task 1 | Task 1 |
| evaluate_workspace_state_quiescence | Task 1 | Task 1 |
| evaluate_task_gate | Task 1 | Task 1 |
| scan_task_quiescence | Task 1 schema/signature | Task 4 |
| render_saved_plan | Task 1 schema/signature | Task 3 |
| CapabilityManifest projection | Task 1 schema | Task 5 |
| RouteDecision and ApprovalProof calculation/verification | Task 1 schema | Task 5 |
| render units and ownership decisions | Task 1 schema | Task 3 |
| workspace diagnostic production | Task 1 schema/policy | Task 4 |
| CLI output mapping | Task 6 only | Task 6 |

No consumer may create a second profile resolver, surface registry, task-gate policy, workspace-state evaluator, schema-ID allocator, or error meaning.

## 2. Authority Inputs and Trust Assumptions

The Resolver is a pure function over verified bytes and explicit observed-state inputs. It performs no target write, cache write, network request, subprocess execution, clock read, random generation, environment discovery, or mutable global lookup.

### 2.1 Inputs

| Input | Authority or evidence status | Resolver treatment |
|---|---|---|
| resolved release identity and detached-manifest claims | verified by the lifecycle/release trust path | validate schema and cross-digest agreement; never fetch |
| release workflow lock or project workflow lock | authority selected by the lifecycle command | validate exact schema, identities, hashes, and closure inputs |
| selected profile and its inheritance chain | activation authority | validate and normalize before catalog closure |
| catalog entries | release-bundle authority | validate stable IDs, dependencies, conflicts, references, capabilities, platforms, and provenance fields |
| artifact definitions and global protected-path policy | ownership authority | validate before emitting render units |
| Trellis task-layout declaration | locked adapter authority | validate discovery and cross-ownership boundaries |
| runtime-surface registry and unit inventory | artifact-bundle authority | validate graph, digest recipes, and full coverage |
| platform capability observations | evidence produced under the CapabilityManifest contract | compare to profile minima; do not manufacture capability |
| current Manifest and workflow lock | current project authority | validate generation and digests; never let history authorize a currently forbidden write |
| observed target file states | non-authoritative evidence | normalize for drift/repair impact only |
| task-quiescence snapshot/findings | evidence produced by Task 4 scanner | validate schema and evaluate policy; never rescan |
| compatibility edge | direction-specific verified authority | use only for operation-branch and candidate-contract validation |

### 2.2 Trust rules

1. Project-local URLs, transaction journals, diagnostics, observed bytes, and caller-provided digest strings are never supply-chain authority.
2. A Manifest records committed state but cannot expand current artifact definitions, protected paths, surface ownership, or capabilities.
3. A compatibility edge is directional and is valid only with the exact verified source/target Release Identities, trust policy, bundles, schemas, layouts, and migration identities.
4. Missing, unsupported, and invalid evidence are distinct states. Cryptographic or authenticated-schema invalidity is never downgraded to missing evidence.
5. All repository paths are normalized, repository-relative, non-symlink paths. Absolute paths, dot-dot traversal, device paths, NUL, Unicode/case aliases, and ambiguous normalization fail closed.
6. The Resolver returns either one fully validated DesiredStateIR or one ordered ResolutionFailure. It never returns a partial IR for a write-capable command.

### 2.3 Validation order

The normative validation order is:

~~~text
schema catalog and version support
  -> canonical decoding and duplicate-key rejection
  -> release/trust/lock identity agreement
  -> profile inheritance and field merge
  -> catalog dependency/conflict/reference closure
  -> capability evaluation
  -> artifact definition and protected-path validation
  -> Trellis layout and cross-ownership validation
  -> runtime-surface registry, inventory, graph, recipes, and coverage
  -> Desired State IR construction
  -> observed-state normalization
  -> candidate impact construction
  -> task snapshot/findings validation
  -> workspace-state evaluation
  -> operation-specific task-gate evaluation
  -> saved-plan inputs
~~~

An earlier failure prevents later interpretation from being used as authority. Diagnostics may include already validated earlier evidence, but never speculative later results.

## 3. Schema Catalog and Versioning Rules

### 3.1 Identity rules

Schema identity and schema version are separate:

~~~yaml
schema_id: agent-workflow.workspace-local
schema_version: 1
~~~

A schema ID never embeds its numeric schema version merely for convenience. Digest domains are separate identifiers and do not double as schema IDs. Every schema is closed: unknown fields, duplicate keys, unsupported versions, illegal union fields, and invalid enum values fail.

New schema IDs owned here use the prefix agent-workflow. and a stable lower-kebab domain name. New digest domains use a stable ASCII label ending in .v1 followed by a NUL byte in the hashed preimage. Existing umbrella formulas and identities are inherited exactly even when their published formula does not use that generic prefix rule.

### 3.2 Task 1 schema definitions

| Schema ID | Version | Closed purpose |
|---|---:|---|
| agent-workflow.schema-catalog | 1 | schema IDs, supported versions, definition owners, implementation owners, and digest domains |
| agent-workflow.profile | 1 | profile inheritance, routing selection, bindings, skill activation, capabilities, approval policy, and provider-security policy |
| agent-workflow.catalog | 1 | component, skill, platform, command, hook, agent, and runtime-entry definitions |
| agent-workflow.workflow-lock | 1 | exact locked component identities, hashes, acquisition identities, and deterministic content contracts |
| agent-workflow.artifact-definition | 1 | manageable targets, ownership, merge strategy, mode policy, markers, validators, and additional restrictions |
| agent-workflow.trellis-task-layout | 1 | bounded task discovery, metadata interpretation, journal classification, and scan limits |
| agent-workflow.runtime-surface-registry | 1 | surface IDs, descriptors, digest recipes, and reference edges |
| agent-workflow.runtime-unit-inventory | 1 | every runtime-visible packaged or rendered unit and its unique owning surface |
| agent-workflow.surface-coverage-proof | 1 | release-neutral coverage witness and graph validation result |
| agent-workflow.desired-state-ir | 1 | pure Resolver output |
| agent-workflow.candidate-impact | 1 | normalized authority, contract-change, and restorative-repair impact |
| agent-workflow.task-quiescence-snapshot | 1 | canonical source/target task, metadata, and task-journal evidence |
| agent-workflow.task-findings | 1 | sorted discovery facts without command policy |
| agent-workflow.workspace-diagnostic | 1 | command-independent workspace state and command-specific admission |
| agent-workflow.saved-plan | 1 | init, sync, repair, and upgrade plan envelope |
| agent-workflow.capability-manifest | 1 | platform/harness capability facts and evidence identity |
| agent-workflow.route-policy | 1 | compiled stable-signal policy and deterministic rule graph |
| agent-workflow.task-intent | 1 | executable-operation intent and sole candidate signal set |
| agent-workflow.route-decision | 1 | closed classify-only, execute-light, and create-integrated-task union |
| agent-workflow.approval-proof | 1 | direct-human task-creation approval envelope |
| agent-workflow.render-unit | 1 | renderer input projection for one managed or overlay-managed unit |
| agent-workflow.ownership-decision | 1 | normalized ownership class, current-state evidence, and permitted reconcile action |
| agent-workflow.resolution-failure | 1 | ordered structured Core/Resolver failure |
| agent-workflow.feature-interface | 1 | decomposition-time exported interface object |

The catalog also registers schemas defined by later feature owners, including Manifest, lifecycle journal, workspace transaction, integration, task transaction, approval replay, task outbox, provider attempts, provider release receipt, runtime control, caller context, and provenance. Registration reserves the identity and owner but does not transfer field-definition ownership to Task 1.

### 3.3 Compatibility

- A higher schema version is unsupported unless an exact directed compatibility edge and owning-feature migration contract name it.
- Unknown fields never provide forward compatibility in v0.1.
- A schema migration changes normalized bytes and therefore changes every digest whose projection includes that schema.
- Parsers and semantic classifiers are selected only by allowlisted ID and version from the verified schema bundle.
- Schema IDs, parser IDs, classifier IDs, digest domains, and surface IDs are compared as exact normalized strings, not by prefix similarity.

### 3.4 Cross-feature closed schemas

Task 1 owns the following schema shapes while later tasks own their population or execution semantics.

#### CapabilityManifest

~~~yaml
schema_id: agent-workflow.capability-manifest
schema_version: 1
platform: codex
adapter_id: codex
adapter_version: 1.0.0
harness_id: codex-cli
harness_version: pinned-version
probe_suite_id: codex-capability-probes
probe_suite_version: 1
capabilities:
  project_instructions: instruction-only
  explicit_runtime_load: enforced
  maintenance_gate: enforced
  task_admission_gate: enforced
  task_archive_gate: enforced
  provider_exception_approval: enforced
  project_skills: instruction-only
approval_verifiers:
  task_creation:
    verifier_id: platform-approval-verifier
    verifier_version: 1.0.0
    actor_source: direct-human
    receipt_source: enforced-confirmation
evidence_digest: 64-lowercase-hex
~~~

The capability and verifier keys are closed catalog IDs. Task 5 produces the object from locked adapter/harness probes. A profile comparison consumes only this schema; an adapter cannot add a capability after resolution.

#### RouteDecision

The compiled RoutePolicy schema contains policy_version, default route, light/heavy owners, explicit-only Trellis rule, stable hard-signal IDs, closed compound rules, deterministic rule IDs, and entry ownership. Rule evaluation is pure over the normalized supplied signal set. Unknown signals, duplicate rule IDs, conflicting owners, cycles, or a rule referring to a non-catalog owner fail resolution.

TaskIntent is:

~~~yaml
schema_id: agent-workflow.task-intent
schema_version: 1
intent_id: stable-intent-id
title: concise-title
objective: concise-objective
requested_mode: null
acceptance_summary: concise-acceptance-summary
signals: []
~~~

requested_mode is null or one admitted mode. signals is the sole executable candidate signal set, contains only stable IDs from the compiled RoutePolicy, is deduplicated and sorted, and participates in intent_digest. Executable commands reject a separate CLI signal list.

All RouteDecision branches require:

- schema_id and schema_version;
- operation, route, decision_id, and decision_digest;
- project_id, workspace_instance_id, Manifest generation/digest, profile_digest, lock_digest, artifact_bundle_digest, and policy_digest;
- platform, adapter ID/version, router contract version, and entry owner;
- matched_rule_ids, normalized signals, reasons, and task_state_digest.

The discriminated branches are:

| operation | route | Additional required fields | Forbidden fields |
|---|---|---|---|
| classify-only | any policy-admitted route | none | intent, task ID/ref, preconditions, task surfaces, challenge, approval |
| execute-light | native-light | intent_id, intent_digest | task ID/ref, task preconditions, task surfaces, challenge, task approval |
| create-integrated-task | trellis-native or speckit-superpowers | requested_task_id, requested_task_ref, task_ref_precondition absent, task_id_precondition unique, intent_id, intent_digest, task_contract_surfaces_digest, approval_challenge, task_creation_approval required | light-only fields or any free-form override |

Task 5 calculates and verifies these fields. Task 4 may consume only create-integrated-task during task admission. Existing-task runtime load never accepts this object as a credential.

The fixed route namespace is:

~~~text
UUIDv5(
  6ba7b811-9dad-11d1-80b4-00c04fd430c8,
  "urn:agent-workflow-pack:route-decision:v1"
)
= c7c2dd65-7073-5e38-8004-fe6b9b4af8f5
~~~

The calculator normalizes the complete branch payload excluding decision_id and decision_digest, computes route_payload_digest with domain agent-workflow.route-decision-payload.v1, derives decision_id as UUIDv5 of the fixed route namespace and the lowercase payload-digest hex, then computes decision_digest with domain agent-workflow.route-decision.v1 over the payload plus decision_id.

task_state_digest uses domain agent-workflow.route-task-state.v1 and covers the canonical checkout-visible task identity inventory across active integrations, archives, and unfinished task journals; non-archived modes and lifecycle revisions; active pointers; recomputed task_contract_digest values and exact surface sets; plus requested task-ID uniqueness and task-ref absence for create-integrated-task. It is separate from task_quiescence_digest.

RouteDecision is unsigned. Schema validity, UUIDv5, and digests prove internal consistency only. Executable consumers reread authority, recompute the supplied stable-signal policy result and all digests, and enforce freshness; claimed calculator origin is not authorization.

#### ApprovalProof

~~~yaml
schema_id: agent-workflow.approval-proof
schema_version: 1
operation: create-integrated-task
approval_id: canonical-uuid
verifier_id: platform-approval-verifier
verifier_version: 1.0.0
platform: codex
harness_version: pinned-version
actor:
  id: platform-human-actor-id
  kind: direct-human
issued_at: UTC-RFC3339
expires_at: UTC-RFC3339
workspace_instance_id: canonical-uuid
task_id: canonical-uuid
task_ref: normalized-repository-relative-ref
task_contract_surfaces_digest: 64-lowercase-hex
intent_digest: 64-lowercase-hex
route_decision_digest: 64-lowercase-hex
approval_challenge: 256-bit-value
verifier_receipt: opaque-enforced-verifier-value
~~~

Unknown fields and any provider-approval branch fields fail. Task 2 separately defines the provider approval exception contract.

#### RenderUnit

~~~yaml
schema_id: agent-workflow.render-unit
schema_version: 1
unit_id: stable-render-unit-id
definition_id: stable-artifact-definition-id
source:
  source_id: stable-source-id
  source_digest: 64-lowercase-hex
target:
  path: normalized-repository-relative-path
  ownership: managed
  merge_strategy: whole-file
  mode_policy: exact
  mode: "0644"
surface_id: stable-surface-id
validator_ids: []
candidate_leaf_digest: 64-lowercase-hex
~~~

Fields illegal for the selected ownership/merge/mode branch are rejected. Task 3 renders bytes from this projection.

#### OwnershipDecision

~~~yaml
schema_id: agent-workflow.ownership-decision
schema_version: 1
path: normalized-repository-relative-path
definition_id: stable-artifact-definition-id
ownership: managed
observed_file_state: {}
baseline_file_state: {}
candidate_file_state: {}
action: replace
reason_code: stable-reconciler-input-reason
~~~

action is one of no-op, create, replace, update-managed-block, adopt-baseline, restorative-repair, or block. Task 1 defines the normalized shape; Task 3 alone decides transaction phases, CAS execution, and recovery.

### 3.5 Trellis task-layout schema

The closed top-level shape is:

~~~yaml
schema_id: agent-workflow.trellis-task-layout
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
~~~

runtime_namespace is a locked Trellis-owned repository-relative root. active_root and archive_root are strict descendants, are non-symlink directories when present, and are explicitly partitioned even when nested.

safe-nfc-segment-v1 accepts exactly one NFC-normalized segment of 1 through 128 UTF-8 bytes. It rejects dot, dot-dot, slash, backslash, NUL, C0/C1 controls, leading/trailing whitespace, and trailing dot, and requires case-folded and Unicode-normalized uniqueness. uuid-json-v1 accepts one lowercase canonical UUID followed by .json. one-segment permits no nested task refs.

A task is recognized only as a real non-symlink directory at the exact depth whose integration-relative path is a regular non-symlink file within the byte limit and valid under a listed integration schema. A grammar-matching directory with missing, oversized, malformed, or unsupported integration remains visible as ambiguity. Missing roots are canonical empty; wrong-type roots, unknown entries, excess depth/count/bytes, aliases, and symlinks produce findings and are never skipped or truncated.

metadata_contracts is a list of closed exact or bounded branches.

~~~yaml
kind: exact
contract_id: stable-contract-id
path: normalized-repository-relative-path
schema_id: stable-schema-id
schema_versions: [1]
parser_id: allowlisted-parser-id
parser_version: 1
classifier_id: allowlisted-classifier-id
classifier_version: 1
semantic_role: stable-role-id
task_ref_fields: []
max_bytes: 1048576
absence_is_empty: true
canonical_empty_state_id: stable-empty-state-id
~~~

~~~yaml
kind: bounded
contract_id: stable-contract-id
root: normalized-repository-relative-root
segment_grammar_id: allowlisted-segment-grammar-id
max_depth: 1
max_matches: 10000
schema_id: stable-schema-id
schema_versions: [1]
parser_id: allowlisted-parser-id
parser_version: 1
classifier_id: allowlisted-classifier-id
classifier_version: 1
semantic_role: stable-role-id
task_ref_fields: []
max_bytes: 1048576
absence_is_empty: true
canonical_empty_state_id: stable-empty-state-id
~~~

Arbitrary globs, regular expressions, recursive wildcards, executable callbacks, runtime-selected roots, and undeclared parser/classifier code are forbidden. Source-release code is never imported or executed to interpret discovery state.

task_transaction_discovery has an absent-is-empty root, no subdirectories, a hard count/byte limit, a closed journal schema/version set, and one phase classifier that defines the complete operation/phase table. A journal is unfinished whenever its phase is not terminal. Unknown names, corrupt or unsupported journals, illegal phases, and limit violations produce ambiguity evidence.

## 4. Canonicalization, Digest Domains, and Dependency DAGs

### 4.1 Common canonicalization

Structured canonicalization uses RFC 8785 JCS over schema-normalized JSON values. YAML is first decoded with duplicate-key rejection and converted to the schema's JSON data model. Normalization rules are:

- strings are valid Unicode and use schema-required NFC normalization;
- repository paths use forward slashes and the path contract in Section 2;
- set-semantic arrays are deduplicated and sorted by their schema-defined stable key;
- ordered arrays preserve semantic order only when the schema explicitly declares order significant;
- mappings are closed and contain no presentation-only aliases;
- POSIX modes are four-character octal strings normalized over bits masked to 0777;
- timestamps are UTC RFC 3339 values only in schemas that explicitly allow time;
- canonical UUID values are lowercase hyphenated form;
- canonical-null is the literal domain value representing absent content, never the hash of an empty file;
- diagnostics, display text, absolute host paths, transaction retry counters, and generated digests are excluded unless a projection explicitly includes them.

### 4.2 Digest catalog

| Name | Normative projection/formula |
|---|---|
| release_id | SHA256(JCS({repository_id, distribution_name, version})) |
| profile_digest | SHA256(JCS(resolved_profile)) |
| workflow_lock_digest | SHA256(canonical project workflow.lock UTF-8 bytes) |
| artifact_definition_digest | SHA256(domain agent-workflow.artifact-definition.v1 NUL plus JCS(normalized_definition)) |
| trellis_task_layout_digest | SHA256(JCS(normalized_trellis_task_layout)) |
| task_contract_digest | SHA256(UTF8(agent-workflow.task-contract.v1 NUL) plus UTF8(JCS(normalized_workflow_contract))) |
| task_contract_surfaces_digest | SHA256(UTF8(agent-workflow.task-surfaces.v1 NUL) plus UTF8(JCS(normalized_task_contract_surfaces))) |
| task_quiescence_digest | SHA256(UTF8(agent-workflow.task-quiescence.v1 NUL) plus UTF8(JCS(task_quiescence_snapshot))) |
| surface_registry_digest | SHA256(UTF8(agent-workflow.surface-registry.v1 NUL) plus UTF8(JCS(registry_projection))) |
| surface_digest | SHA256(UTF8(agent-workflow.runtime-surface.v1 NUL) plus UTF8(JCS(surface_projection))) |
| coverage_proof_digest | SHA256(UTF8(agent-workflow.surface-coverage.v1 NUL) plus UTF8(JCS(coverage_projection))) |
| desired_state_ir_digest | SHA256(UTF8(agent-workflow.desired-state-ir.v1 NUL) plus UTF8(JCS(ir_projection))) |
| candidate_impact_digest | SHA256(UTF8(agent-workflow.candidate-impact.v1 NUL) plus UTF8(JCS(candidate_impact))) |
| route_policy_digest | SHA256(UTF8(agent-workflow.route-policy.v1 NUL) plus UTF8(JCS(compiled_route_policy))) |
| intent_digest | SHA256(UTF8(agent-workflow.task-intent.v1 NUL) plus UTF8(JCS(normalized_task_intent))) |
| route_payload_digest | SHA256(UTF8(agent-workflow.route-decision-payload.v1 NUL) plus UTF8(JCS(normalized branch payload excluding decision identity fields))) |
| decision_digest | SHA256(UTF8(agent-workflow.route-decision.v1 NUL) plus UTF8(JCS(normalized branch payload plus decision_id))) |
| task_state_digest | SHA256(UTF8(agent-workflow.route-task-state.v1 NUL) plus UTF8(JCS(route-time task-state projection))) |
| local_state_contract_digest | SHA256(JCS(local_state_contract excluding contract_digest)) |
| workspace_diagnostic_digest | SHA256(UTF8(agent-workflow.workspace-diagnostic.v1 NUL) plus UTF8(JCS(workspace_diagnostic))) |
| plan_core_digest | SHA256(UTF8(agent-workflow.plan-core.v1 NUL) plus UTF8(JCS(plan_core))) |
| journal_binding_digest | SHA256(UTF8(agent-workflow.journal-binding.v1 NUL) plus UTF8(JCS(immutable_header))) |
| candidate_manifest_digest | SHA256(candidate Manifest canonical UTF-8 bytes) |
| plan_digest | SHA256(UTF8(agent-workflow.saved-plan.v1 NUL) plus UTF8(JCS(plan_envelope excluding plan_digest))) |
| interface_digest | SHA256(UTF8(agent-workflow.feature-interface.v1 NUL) plus UTF8(JCS(exported_interface))) |

The domain labels above are literal ASCII plus one NUL byte. The words “domain” and “NUL” in the table are notation, not bytes in the preimage.

### 4.3 Runtime-surface DAG

~~~text
registry source
  -> normalized descriptors, inventory identities, digest recipes, reference edges
  -> surface_registry_digest

owned unit bytes/contracts
  + surface descriptor
  + digest recipe version
  + referenced surface IDs and already-computed digests
  -> surface_digest

all unit identities and leaf digests
  + canonical owners
  + graph-validation result
  -> coverage_proof_digest

artifact definitions, templates, renderer/validator identities,
surface registry, unit inventory, recipes, coverage proof, reference graph
  -> artifact_bundle_digest
~~~

The reference graph must be acyclic. Surface digests are computed in stable topological order. Registry source contains no computed unit digest, surface digest, coverage root, or artifact-bundle root. The generated coverage proof contains no artifact-bundle digest. Other surfaces may reference surface-registry, but surface-registry has no reverse dependency on their computed roots.

### 4.4 Saved-plan DAG

~~~text
plan_core
  -> plan_core_digest
  -> immutable journal header
  -> journal_binding_digest
  -> candidate Manifest
  -> candidate_manifest_digest
  -> final plan envelope
  -> plan_digest
~~~

The following edges are forbidden:

- plan_digest into plan_core, immutable header, journal binding, or candidate Manifest;
- candidate Manifest bytes into plan_core local-state contract;
- workspace candidate bytes derived from candidate Manifest bytes;
- journal_binding_digest calculated from a header containing final plan_digest;
- a generated digest included in the projection that generates itself.

Workspace and Manifest candidates independently render the same normalized local-state contract from plan_core.

## 5. Runtime-Surface Registry, Unit Inventory, and Coverage Proof

### 5.1 Surface registry

The registry is a closed list sorted by surface_id. Each surface contains:

~~~yaml
surface_id: platform-adapter:codex
surface_kind: platform-adapter
descriptor_version: 1
digest_recipe_id: surface-content-v1
owned_unit_ids:
  - render-unit:codex-project-instructions
references:
  - runtime-control-plane
  - surface-registry
contract_change_class: runtime-visible
~~~

Reserved IDs and namespaces are:

- runtime-control-plane;
- surface-registry;
- trellis-runtime;
- trellis-layout;
- route-policy;
- router followed by one stable ID;
- platform-adapter followed by one platform ID;
- hook followed by platform and hook ID;
- agent followed by platform and agent ID;
- skill followed by skill ID;
- runtime-entry followed by entry ID.

Unknown namespaces, free-form selectors, aliases, and caller-created IDs fail. runtime-control-plane and surface-registry are mandatory members of every integrated task surface closure.

### 5.2 Unit inventory

Each inventory row contains:

~~~yaml
unit_id: render-unit:codex-project-instructions
unit_kind: rendered-instruction
distribution_scope: rendered-project
normalized_path: AGENTS.md
owning_surface_id: platform-adapter:codex
leaf_recipe_id: utf8-bytes-and-mode-v1
runtime_visible: true
~~~

The inventory covers:

- managed render units and generated instruction blocks;
- wrappers, loaders, hooks, agents, skills, commands, adapters, policies, routers, and runtime entries;
- every first-party module importable from a supported CLI entry in the self-contained wheel;
- packaged helper modules even when they are not direct entry points.

Build/test-only sources absent from wheel, sdist, Git-checkout runtime package, and rendered output are outside the inventory.

Exactly one canonical surface owns every runtime-visible unit. A unit may influence another surface only through a declared reference edge. Path aliases do not create another unit identity.

### 5.3 Surface digest recipe

surface_projection is exactly:

~~~json
{
  "surface_id": "stable surface ID",
  "surface_kind": "closed kind",
  "descriptor_version": 1,
  "digest_recipe_id": "stable recipe ID",
  "owned_units": [
    {
      "unit_id": "stable unit ID",
      "leaf_digest": "64 lowercase hex"
    }
  ],
  "references": [
    {
      "surface_id": "referenced stable ID",
      "surface_digest": "64 lowercase hex"
    }
  ]
}
~~~

owned_units and references are sorted by stable ID. Leaf recipes bind every byte, normalized mode, and contract field that can alter runtime behavior. Removed units and surfaces use canonical-null in impact comparison, not an empty-content hash.

### 5.4 Coverage algorithm

Resolution fails unless all of these are true:

1. every runtime-visible candidate unit is in the inventory;
2. every inventory unit exists in the applicable distribution/render projection;
3. every inventory unit has exactly one valid owning surface;
4. every runtime entry is owned and its required loader/control-plane modules are transitively covered;
5. every owned byte or contract field appears in its leaf recipe;
6. every reference resolves and the graph is acyclic;
7. every task-loadable surface transitively references runtime-control-plane and surface-registry;
8. registry schema, descriptor, inventory, recipe, or graph changes appear in surface-registry impact;
9. relevant CLI control-plane changes appear in runtime-control-plane impact;
10. wheel, sdist, Git-checkout runtime package, and rendered project enumeration produce equivalent ownership claims for common logical units.

The coverage proof is a release-neutral witness. It is evidence, not authority, and cannot override registry source or actual enumeration.

## 6. Resolver Inputs, Validation Order, and Desired State IR

### 6.1 Callable

~~~text
resolve(inputs: ResolverInputs) -> DesiredStateIR | ResolutionFailure
~~~

ResolverInputs is closed and contains:

- operation context: init, sync, repair, upgrade, doctor, test-routing, or planning;
- verified current and candidate release identities and bundle digests as applicable;
- selected authoritative workflow lock;
- profile source set and selected profile ID;
- catalog source set;
- artifact definitions and global protected-path policy;
- verified Trellis task-layout declaration;
- runtime-surface registry, unit inventory, digest recipes, and enumerated runtime-visible units;
- selected platforms and CapabilityManifest objects;
- current Manifest and normalized observed file states when applicable;
- compatibility edge when required;
- normalized repair selection when operation is repair.

No input may contain an already-resolved profile, caller-authored candidate impact, caller-authored surface digest, or caller-authored DesiredStateIR.

### 6.2 Profile resolution

Profiles use single inheritance. The complete chain is loaded before merge and must have unique IDs and no cycle.

| Field | Merge rule |
|---|---|
| schema_version | must be supported and identical across the chain |
| id | leaf profile identity |
| extends | resolution-only field; absent from resolved_profile |
| route_admission | closed mapping; child replaces supplied leaf keys |
| bindings | closed mode/platform mapping; child replaces supplied leaf binding |
| skills.enable | set union followed by stable-ID sort |
| skills.disable | set union followed by stable-ID sort |
| artifact_policy | child scalar replaces parent |
| default_platforms | child value replaces the complete parent array |
| required_capabilities | closed mapping; child replaces supplied capability minimum |
| approval_policy | closed mapping; child replaces supplied policy leaf |
| provider_security_policy | closed mapping; child replaces supplied policy leaf |

After merge and defaults:

- a skill in both enable and disable is an error;
- disabled precedence is absolute: a disabled node cannot be selected, pulled as a dependency, or reached by a discoverable reference;
- unknown fields, multiple parents, executable expressions, and arbitrary merge directives fail;
- set-semantic arrays are deduplicated and sorted;
- diagnostics and source locations are excluded from resolved_profile and profile_digest.

### 6.3 Catalog closure

The catalog algorithm is:

1. validate every stable ID and reject duplicate definitions;
2. seed enabled profile entries plus mandatory platform/control-plane entries;
3. traverse required dependency edges in stable-ID order;
4. reject a dependency that is disabled, missing, unsupported on the selected platform, or capability-incompatible;
5. evaluate symmetric and directional conflicts over the complete closure;
6. traverse references among skills, commands, hooks, agents, runtime entries, and policy/router objects;
7. reject dangling, cyclic where prohibited, gated, disabled, or ownership-inconsistent references;
8. compute discoverable leaves only after closure; a disabled or route-gated entry is neither discoverable nor transitively referenced from a discoverable leaf;
9. emit a stable topological component order and a separately sorted stable-ID index.

Catalog selection never re-resolves a version. All selected component identities and hashes come unchanged from the authoritative workflow lock.

### 6.4 Capability evaluation

Capability enforcement levels have this order:

~~~text
unsupported < instruction-only < enforced
~~~

A platform satisfies a required capability only when its verified observed level is greater than or equal to the profile minimum. Missing capability entries normalize to unsupported. A claimed level is accepted only from a schema-valid CapabilityManifest whose adapter, platform, harness version, probe ID/version, and evidence digest match the selected locked platform contract.

Provider-security values such as required, approval-required, and best-effort are separate policy enums and are not coerced into this capability ordering.

### 6.5 Artifact and protected-path validation

The minimum global protected set is:

- .git/**;
- the complete locked Trellis active and archive roots;
- .trellis/workspace/**;
- specs/**;
- .agent-workflow/local/**;
- .agent-workflow/task-transactions/**;
- .agent-workflow/transactions/**.

Ordinary artifact definitions also cannot target .agent-workflow/manifest.json, .agent-workflow/workflow.lock, either OS lock, maintenance state, runtime descriptors, transaction control files, or integration state. The exact control-plane writers defined by later features retain only their umbrella-authorized paths.

For every artifact definition, the Resolver:

- validates source identity, target path, ownership class, merge strategy, mode policy, markers, validators, and additional forbidden paths;
- rejects overlap with global protected paths or control-plane authority paths;
- rejects target-target collisions and overlapping marker ranges without an explicit composition contract;
- permits overlay-managed only with marked-block and managed only with whole-file replacement;
- requires exact mode only for whole-file managed or initial create-once output;
- requires preserve mode for overlay/adopted host files;
- rejects symlink targets and every possible bounded metadata expansion collision;
- derives protected globs for Trellis active/archive roots;
- applies cross-ownership validation to exact and bounded Trellis metadata contracts;
- never grants an artifact definition authority over integration, task transactions, local state, task outbox, Manifest, locks, maintenance, or lifecycle journals.

### 6.6 Desired State IR

DesiredStateIR is serializable but non-authoritative:

~~~yaml
schema_id: agent-workflow.desired-state-ir
schema_version: 1
operation: sync
release_contract: {}
resolved_profile: {}
authority_digests: {}
workflow_lock_projection: {}
selected_platforms: []
capability_results: []
catalog_closure: []
reference_closure: []
route_policy: {}
entry_ownership: []
discoverable_leaf_ids: []
runtime_catalog_entry_ids: []
trellis_task_layout: {}
surface_registry: {}
surface_digests: []
coverage_result: {}
render_units: []
artifact_definitions: []
candidate_impact: {}
diagnostics: []
~~~

All arrays have schema-defined stable ordering. diagnostics may contain warnings and blocking evidence, but a write-capable IR is returned only when blocking failures are absent. desired_state_ir_digest excludes presentation text and includes every contract field used by a downstream renderer, scanner caller, adapter, or evaluator.

## 7. Candidate Authority, Surface, and Restorative-Repair Impact

### 7.1 Callable

~~~text
compute_candidate_impact(
  current_contract: CurrentContract,
  observed_state: ObservedState,
  candidate_ir: DesiredStateIR
) -> CandidateImpact | ResolutionFailure
~~~

The callable is pure. candidate_impact is derived, never accepted from a CLI or saved-plan caller.

### 7.2 Schema

~~~yaml
schema_id: agent-workflow.candidate-impact
schema_version: 1
impact_kind: none
authority_changes: []
surface_changes: []
~~~

authority_changes is the complete sorted changed subset of:

- release-identity;
- profile;
- workflow-lock;
- artifact-bundle;
- route-policy;
- router-contract;
- surface-registry;
- trellis-layout.

Each authority change contains authority_id, before_digest, and after_digest. Unchanged entries are omitted. A release upgrade always changes release-identity.

surface_changes is the complete sorted union of:

- candidate contract changes; and
- observed drift explicitly selected for repair.

Each row contains:

~~~yaml
surface_id: runtime-entry:trellis-implement
change_kind: repair
contract_before_digest: 64-lowercase-hex
observed_before_digest: canonical-null
after_digest: 64-lowercase-hex
~~~

### 7.3 Normalization rules

- contract-change requires after_digest different from contract_before_digest.
- removal uses after_digest equal to canonical-null.
- addition uses contract_before_digest equal to canonical-null.
- ordinary sync or upgrade requires observed_before_digest equal to contract_before_digest for every affected or consumed surface; unexplained drift requires a separate repair plan.
- repair requires contract_before_digest equal to after_digest, observed_before_digest different from that digest, an empty authority vector, unchanged registry/inventory/reference graph, explicit repair selection, and later approval/CAS enforcement.
- impact_kind is none only when authority_changes and surface_changes are empty and no unclassified runtime-visible difference exists.
- otherwise impact_kind is runtime-visible.
- any runtime-visible byte not mapped to one owned surface is AWP_SURFACE_COVERAGE_INVALID, not an ignored change.

The heavy contract-changing predicate is true exactly when authority_changes is nonempty or any surface change has change_kind contract-change.

## 8. Task Quiescence Snapshot and Evaluator Interfaces

### 8.1 Scanner interface

Task 1 defines but does not implement:

~~~text
scan_task_quiescence(
  source_layout: VerifiedTrellisTaskLayout,
  target_layout: VerifiedTrellisTaskLayout,
  source_schemas: VerifiedDiscoverySchemas,
  target_schemas: VerifiedDiscoverySchemas
) -> TaskSnapshotAndFindings
~~~

Task 4 is the sole implementation owner. The scanner returns facts only and never emits command blockers.

### 8.2 Snapshot

The canonical snapshot includes:

- source and target layout digests and schema-bundle digests;
- every normalized task path and its source/target active/archive role;
- immutable canonical task UUID, admission-time task ref, and current path;
- integration byte hash, mode, schema ID/version, lifecycle status, revision, task_contract_digest, and complete task_contract_surfaces;
- every metadata path, byte hash, mode, parser/classifier ID/version, parsed task refs, semantic role, and empty/nonempty classification;
- every task-journal path, byte hash, mode, schema, operation, phase, task ID/ref, and terminal classification;
- sorted finding IDs associated with the evidence.

Task identity is canonical_uuid(integration.admission.task_id). Duplicate historical admission refs are legal after archive when task IDs and current paths are distinct. Duplicate or malformed task IDs, journal/integration disagreement, or path/partition disagreement is an interpretation conflict.

### 8.3 Findings

TaskFindings is a sorted list of closed branches:

| Finding kind | Required identity fields |
|---|---|
| layout-ambiguous | finding_id, normalized path, evidence class, parser/schema details |
| unknown-entry | finding_id, normalized path, root contract ID |
| collision | finding_id, normalized aliases, collision class |
| scan-limit | finding_id, contract ID, limit kind, configured limit |
| interpretation-conflict | finding_id, task ID/ref/path and conflicting fields |
| unfinished-task-transaction | finding_id, journal path, task ID/ref, operation, phase |
| non-archived-task | finding_id, task ID, current path, lifecycle status, mode, pinned surfaces |
| layout-state-stranded | finding_id, normalized path, semantic role, source/target visibility |

Findings are ordered by policy class, canonical task ID, normalized current path, surface ID, authority ID, and finding ID. They do not contain a preselected error code.

### 8.4 Fixed workspace-state evaluator

~~~text
evaluate_workspace_state_quiescence(
  snapshot: TaskQuiescenceSnapshot,
  findings: TaskFindings
) -> WorkspaceTaskState
~~~

The evaluator ID is agent-workflow.workspace-state-quiescence and version is 1.

Algorithm:

1. validate snapshot/findings identity and recompute task_quiescence_digest;
2. if any discovery, schema, parser, limit, collision, or interpretation ambiguity exists, return task_quiescence ambiguous;
3. otherwise, if any unfinished task transaction, non-archived task, or valid stranded-layout finding exists, return task_quiescence blocked;
4. otherwise return task_quiescence quiescent.

The requested operation, candidate impact, no-op policy, repair eligibility, and caller identity are not inputs. Identical verified evidence must produce identical state for launcher, doctor, migration, sync, repair, and upgrade.

### 8.5 Operation-specific task gate

~~~text
evaluate_task_gate(
  operation: TaskGateOperation,
  candidate_impact: CandidateImpact,
  snapshot: TaskQuiescenceSnapshot,
  findings: TaskFindings
) -> TaskGateResult
~~~

TaskGateOperation is init, sync, repair, upgrade, or workspace-migrate.

Common rules:

- ambiguity or unfinished task transaction blocks every non-no-op write;
- a pinned surface digest differing from candidate impact contract_before_digest is stale/ambiguous and blocks;
- admitting, active, blocked, completed, and archiving are non-archived; only archived is categorically non-gating;
- stranded layout state blocks every layout-changing write;
- no caller may replace snapshot mode/surface data with an aggregate digest or selector.

Operation rules:

| Operation | Policy |
|---|---|
| workspace-migrate | every ambiguity, unfinished journal, non-archived task, or stranded state blocks |
| init | any pre-existing integrated task, task journal, ambiguous discovery, or nonempty stranded state blocks implicit adoption |
| upgrade | every non-archived speckit-superpowers task blocks a contract-changing candidate; trellis-native blocks only when a contract-changing surface ID intersects its exact pinned set and changes/removes the pinned digest |
| sync | true no-op may return no blockers and no writes; otherwise use the same affected-surface rules and reject unexplained drift |
| repair | allow a matching task surface only for a valid restorative row whose contract_before_digest and after_digest equal the pinned digest, authority vector is empty, and registry graph is unchanged |

Blocker order is:

1. layout/discovery ambiguity;
2. unfinished task transaction;
3. affected non-archived task;
4. stranded layout state.

Ties use canonical task ID, normalized path, surface ID, authority ID, and finding ID. TaskGateResult contains the complete blocker list and primary_evaluator_blocker. A later snapshot mismatch is not reordered through this function; it becomes AWP_TASK_QUIESCENCE_CHANGED as the transaction's unconditional primary error.

## 9. Saved Plan and Candidate Manifest Envelope

### 9.1 Renderer interface

Task 1 defines but does not implement:

~~~text
render_saved_plan(plan_core: PlanCore) -> SavedPlanEnvelope
~~~

Task 3 is the sole implementation owner. It may serialize the schema but may not change projections, exclusions, digest domains, or branch rules.

### 9.2 Plan core

PlanCore contains:

- operation branch;
- project/workspace identities or bootstrap absence/candidate identities;
- installed and candidate release identities as branch-appropriate;
- trust-policy, profile, lock, artifact-bundle, schema-bundle, and layout identities;
- Manifest generation/digest precondition or absence precondition;
- prospective transaction ID and recovery runtime identity;
- candidate local-state contract;
- provider approval bindings;
- non-Manifest candidate file states and complete file preconditions;
- canonical task snapshot, findings, task_quiescence_digest, and candidate impact;
- workspace-state evaluator ID/version/result;
- task-gate evaluator ID/version/result;
- command blocker list, which must be empty for an approvable write plan;
- branch-specific bootstrap or repair fields.

PlanCore excludes all four derived digests, candidate Manifest bytes/digest, presentation diagnostics, mutable journal phase, applied-file lists, retries, and rollback state.

### 9.3 Closed operation union

| Operation | Release rule | Required special preconditions |
|---|---|---|
| init | installed_release absent; candidate is exact executing verified release | Manifest, project ID, workspace ID, replay ledger absent; target-path digest and candidate identities present |
| sync | installed and candidate releases identical | existing project/workspace identities and Manifest generation/digest |
| repair | installed and candidate releases identical | explicit restorative selection; no authority change |
| upgrade | installed and candidate may differ only through exact verified directed edge | compatibility identity, source/target schema/layout/bundle identities |

Fields from another branch are schema errors. No branch carries release URL, caller-defined asset hash, trust-policy override, or candidate runtime not authorized by the release contract.

### 9.4 Immutable header

The immutable header contains:

- transaction_id;
- operation;
- project_id or bootstrap candidate identity;
- workspace_instance_id or bootstrap candidate identity;
- plan_core_digest;
- baseline_manifest_digest or absence;
- candidate_manifest_generation;
- task_quiescence_digest;
- recovery_runtime.

Task 3 may add only fields already required by the umbrella's transaction contract and included in the closed immutable-header schema. Mutable journal fields never participate.

### 9.5 Envelope

SavedPlanEnvelope contains:

~~~yaml
schema_id: agent-workflow.saved-plan
schema_version: 1
operation: upgrade
plan_core: {}
plan_core_digest: 64-lowercase-hex
immutable_header: {}
journal_binding_digest: 64-lowercase-hex
candidate_manifest_digest: 64-lowercase-hex
candidate_manifest_file_state:
  path: .agent-workflow/manifest.json
  byte_hash: 64-lowercase-hex
  mode: "0644"
  file_type: regular
  non_symlink: true
plan_digest: 64-lowercase-hex
~~~

Every path precondition and candidate file state is one object binding path, existence, file type, byte hash, normalized mode, and non-symlink status. Overlay entries additionally bind marker identity and managed-block hash.

Apply must revalidate the complete digest DAG, operation branch, identities, capability facts, compatibility edge, reconstructable candidates, snapshot/findings, evaluator versions/results, and path preconditions. A saved plan from another workspace fails by default.

## 10. Workspace-State and Command-Admission Diagnostics

### 10.1 Schema

~~~yaml
schema_id: agent-workflow.workspace-diagnostic
schema_version: 1
workspace_state:
  relationship: matching
  relationship_evidence: verified
  discovery_evidence: verified
  task_quiescence: quiescent
  primary_state_blocker: null
command_admission:
  command: doctor
  allowed: true
  blocker: null
secondary_diagnostics: []
~~~

relationship is matching, migration-required, ahead, diverged, or unknown.

relationship_evidence is verified, missing, or invalid.

discovery_evidence is verified, missing, unsupported, or invalid.

task_quiescence is not-evaluated, quiescent, blocked, or ambiguous.

primary_state_blocker describes ordinary contract-matched runtime health. command_admission alone determines whether the requested command may proceed. A diagnostic or migration command can be admitted while primary_state_blocker remains non-null.

### 10.2 State selection

State selection order is:

1. invalid relationship evidence -> relationship unknown, AWP_SOURCE_RELEASE_VERIFICATION_FAILED, exit 30;
2. missing required relationship evidence -> AWP_WORKSPACE_SOURCE_METADATA_REQUIRED;
3. verified ahead -> AWP_WORKSPACE_CONTRACT_AHEAD;
4. verified diverged -> AWP_WORKSPACE_CONTRACT_DIVERGED;
5. migration-required with missing required discovery -> AWP_WORKSPACE_SOURCE_METADATA_REQUIRED;
6. migration-required with unsupported/invalid discovery or ambiguous quiescence -> AWP_WORKSPACE_TASK_LAYOUT_AMBIGUOUS;
7. migration-required with unfinished transaction -> AWP_WORKSPACE_TASK_RECOVERY_BLOCK;
8. migration-required with non-archived task -> AWP_WORKSPACE_ACTIVE_TASK_BLOCK;
9. migration-required with stranded state -> AWP_WORKSPACE_LAYOUT_STATE_STRANDED;
10. otherwise migration-required -> AWP_WORKSPACE_MIGRATION_REQUIRED;
11. matching preserves the evaluator-derived task_quiescence dimension. A non-archived task alone does not create a primary_state_blocker for contract-matched existing-task operation; ambiguity or unfinished recovery evidence may still create the corresponding state blocker, while operation-specific effects remain in command_admission.

Invalid authenticated relationship metadata is never reported as missing, ahead, diverged, or migration-required. Discovery support does not erase an already verified ahead/diverged relationship.

### 10.3 Command admission

- read-only doctor may be allowed to report any state without treating it as healthy;
- workspace-migrate is allowed only for verified migration-required relationship, verified discovery, and an empty strict task-gate blocker list;
- ordinary routing, task mutation, provider execution, and Reconciler writes require matching local/project contract plus their own authority gates;
- ahead/diverged permits read-only diagnostics and independently authorized recovery, not workspace migration;
- invalid relationship evidence blocks every write with AWP_SOURCE_RELEASE_VERIFICATION_FAILED;
- AWP_TASK_QUIESCENCE_CHANGED is a stale-evidence transaction error outside initial state-blocker ordering and always becomes the command primary error after a bound snapshot changes.

Human and JSON output are projections of this same object. Paths remain repository-relative and secrets are absent or redacted before construction.

## 11. Error Codes and Exit Categories

### 11.1 Exit categories

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

### 11.2 Core/Resolver/workspace error namespace

| Code | Exit | Meaning |
|---|---:|---|
| AWP_SCHEMA_INVALID | 2 | closed schema, duplicate-key, version, or union validation failure |
| AWP_CANONICALIZATION_INVALID | 2 | value has no unique permitted normalized representation |
| AWP_PROFILE_INVALID | 2 | inheritance, merge, field, or enable/disable contract invalid |
| AWP_CATALOG_CLOSURE_BLOCKED | 2 | dependency, conflict, reference, platform, or disabled-precedence closure failed |
| AWP_CAPABILITY_INSUFFICIENT | 23 | verified platform capability is below the profile minimum |
| AWP_ARTIFACT_POLICY_INVALID | 2 | artifact ownership/merge/mode/marker contract invalid |
| AWP_PROTECTED_PATH_VIOLATION | 20 | target or metadata declaration overlaps a forbidden authority boundary |
| AWP_SURFACE_GRAPH_INVALID | 2 | surface ID, reference, or graph is invalid or cyclic |
| AWP_SURFACE_COVERAGE_INVALID | 2 | runtime-visible unit is missing, multiply owned, omitted from a recipe, or unclassified |
| AWP_CANDIDATE_IMPACT_INVALID | 2 | authority/surface/repair impact is incomplete or inconsistent |
| AWP_SAVED_PLAN_GRAPH_INVALID | 2 | saved-plan projection contains a cycle or forbidden reverse edge |
| AWP_SAVED_PLAN_MISMATCH | 40 | saved plan identity, digest, branch, evaluator, or precondition is stale/mismatched |
| AWP_SOURCE_RELEASE_VERIFICATION_FAILED | 30 | cryptographic or authenticated relationship/schema verification failed |
| AWP_WORKSPACE_SOURCE_METADATA_REQUIRED | 21 | relationship or required discovery evidence is unavailable |
| AWP_WORKSPACE_MIGRATION_REQUIRED | 21 | exact directed local-state migration is required |
| AWP_WORKSPACE_CONTRACT_AHEAD | 21 | only the verified reverse relationship exists |
| AWP_WORKSPACE_CONTRACT_DIVERGED | 21 | neither verified direction exists |
| AWP_WORKSPACE_TASK_RECOVERY_BLOCK | 21 | unfinished task transaction must be recovered under its authorized runtime |
| AWP_WORKSPACE_ACTIVE_TASK_BLOCK | 22 | non-archived task blocks strict workspace migration |
| AWP_WORKSPACE_TASK_LAYOUT_AMBIGUOUS | 22 | task/layout evidence cannot be interpreted deterministically |
| AWP_WORKSPACE_LAYOUT_STATE_STRANDED | 22 | layout change would stop recognizing nonempty task/metadata state |
| AWP_TASK_QUIESCENCE_CHANGED | 40 | task snapshot changed after being bound into a plan or journal |

Task 6 may map these codes to CLI presentation but may not change their meaning or exit category. Errors owned by provider, reconciler, runtime/task-state, and route/adapter namespaces remain defined by Tasks 2–5.

## 12. Test Matrix and Acceptance-Criteria Mapping

### 12.1 Contract and property tests

| Area | Required tests |
|---|---|
| schema/versioning | unknown fields, duplicate YAML keys, unsupported versions, union cross-fields, schema-ID/digest-domain separation |
| canonicalization | JCS determinism, Unicode/path aliases, set sorting, mode normalization, canonical-null, excluded diagnostics |
| profile | inheritance cycle, field merge, default_platforms replacement, enable/disable conflict, disabled dependency |
| catalog | missing dependency, conflict, dangling reference, gated discoverability, stable closure ordering |
| capability | unsupported/instruction-only/enforced ordering, missing capability, harness/adapter mismatch |
| artifact policy | protected paths, target collision, marker overlap, illegal ownership/merge/mode combinations, bounded metadata collision |
| surface registry | unknown ID, missing mandatory meta-surface, dangling/cyclic graph, unowned/multiply owned unit, omitted leaf bytes, unclassified CLI module |
| digest DAG | computed root in registry source, coverage proof reverse edge, artifact root self-reference, plan/journal/Manifest reverse edge |
| candidate impact | additions/removals, heavy authority change, affected/unaffected adapter/skill, stale pinned digest, restorative repair, unexplained drift |
| task state | fixed state evaluator invariance, operation-specific gate, completed non-archived, strict migration, no-op sync, blocker order |
| saved plan | four operation branches, cross-branch rejection, other-workspace rejection, complete digest revalidation |
| diagnostics | relationship/discovery independence, invalid-vs-missing, state/admission separation, stale snapshot precedence |
| errors | JSON/human parity, exit category, repository-relative paths, redaction |

### 12.2 Primary acceptance ownership

| AC | Task 1 contract and evidence | Integration consumers |
|---|---|---|
| AC-12 | snapshot-aware, mode/surface-aware task-gate evaluator and heavy contract-change predicate | Tasks 3–6 |
| AC-13 | disabled precedence and discoverable-reference closure | Tasks 5–6 |
| AC-16 | structured diagnostic/error schema and exit/redaction contract | Tasks 2–6 |
| AC-27 | completed remains non-archived; only archived is categorically non-gating | Tasks 3–6 |
| AC-33 | Trellis roots/metadata cross-ownership validator | Tasks 4–5 |
| AC-34 | saved-plan discriminated union | Tasks 3, 4, 6 |
| AC-41 | acyclic plan_core -> journal binding -> candidate Manifest -> plan graph | Tasks 3, 4, 6 |
| AC-51 | exact directed relationship classification without version ordering | Tasks 4, 6 |
| AC-53 | closed Trellis layout/discovery schema and ambiguity evidence | Task 4 |
| AC-55 | scanner/evaluator separation and shared signatures | Tasks 3, 4, 6 |
| AC-57 | workspace state separated from command admission | Tasks 4, 6 |
| AC-60 | invalid relationship evidence and exit 30 | Tasks 4, 6 |
| AC-62 | full runtime-visible coverage and normalized contract-change impact | Tasks 3–6 |
| AC-64 | fixed command-independent task-quiescence result | Tasks 3, 4, 6 |

Task 1 supplies schema/digest primitives for AC-58 but does not own UUID generation, ref reuse, archive destination, or runtime uniqueness enforcement. Secondary integration evidence also supports AC-14, AC-29, AC-35, AC-54, AC-56, AC-58, AC-59, and AC-63 without changing their primary owners.

## 13. Downstream Interface Freeze

This review-requested draft contains the complete proposed exported_interface object. It is not frozen and has no registry digest until this feature spec is approved, committed as producer content commit C, and followed by a separate registry commit R.

~~~json
{
  "interface_schema": "agent-workflow.feature-interface",
  "interface_version": 1,
  "producer_task": "task-1",
  "producer_feature": "core-schemas-and-resolver",
  "schema_versions": {
    "agent-workflow.schema-catalog": 1,
    "agent-workflow.profile": 1,
    "agent-workflow.catalog": 1,
    "agent-workflow.workflow-lock": 1,
    "agent-workflow.artifact-definition": 1,
    "agent-workflow.trellis-task-layout": 1,
    "agent-workflow.runtime-surface-registry": 1,
    "agent-workflow.runtime-unit-inventory": 1,
    "agent-workflow.surface-coverage-proof": 1,
    "agent-workflow.desired-state-ir": 1,
    "agent-workflow.candidate-impact": 1,
    "agent-workflow.task-quiescence-snapshot": 1,
    "agent-workflow.task-findings": 1,
    "agent-workflow.workspace-diagnostic": 1,
    "agent-workflow.saved-plan": 1,
    "agent-workflow.capability-manifest": 1,
    "agent-workflow.route-policy": 1,
    "agent-workflow.task-intent": 1,
    "agent-workflow.route-decision": 1,
    "agent-workflow.approval-proof": 1,
    "agent-workflow.render-unit": 1,
    "agent-workflow.ownership-decision": 1,
    "agent-workflow.resolution-failure": 1,
    "agent-workflow.feature-interface": 1
  },
  "exports": [
    {
      "interface_id": "core.schema-catalog.v1",
      "definition_owner": "task-1",
      "implementation_owner": "task-1",
      "schema_ids": ["agent-workflow.schema-catalog", "agent-workflow.resolution-failure"],
      "callables": [],
      "consumers": ["task-2", "task-3", "task-4", "task-5", "task-6"]
    },
    {
      "interface_id": "core.profile-resolution.v1",
      "definition_owner": "task-1",
      "implementation_owner": "task-1",
      "schema_ids": ["agent-workflow.profile", "agent-workflow.catalog", "agent-workflow.workflow-lock"],
      "callables": ["resolve(ResolverInputs) -> DesiredStateIR | ResolutionFailure"],
      "consumers": ["task-3", "task-4", "task-5", "task-6"]
    },
    {
      "interface_id": "core.artifact-policy.v1",
      "definition_owner": "task-1",
      "implementation_owner": "task-1",
      "schema_ids": ["agent-workflow.artifact-definition", "agent-workflow.trellis-task-layout"],
      "callables": [],
      "consumers": ["task-3", "task-4", "task-5"]
    },
    {
      "interface_id": "core.surface-impact.v1",
      "definition_owner": "task-1",
      "implementation_owner": "task-1",
      "schema_ids": ["agent-workflow.runtime-surface-registry", "agent-workflow.runtime-unit-inventory", "agent-workflow.surface-coverage-proof", "agent-workflow.candidate-impact"],
      "callables": ["compute_candidate_impact(CurrentContract, ObservedState, DesiredStateIR) -> CandidateImpact | ResolutionFailure"],
      "consumers": ["task-3", "task-4", "task-5", "task-6"]
    },
    {
      "interface_id": "core.capability-manifest.v1",
      "definition_owner": "task-1",
      "implementation_owner": "task-5",
      "schema_ids": ["agent-workflow.capability-manifest"],
      "callables": [],
      "consumers": ["task-5", "task-6"]
    },
    {
      "interface_id": "core.route-contract.v1",
      "definition_owner": "task-1",
      "implementation_owner": "task-5",
      "schema_ids": ["agent-workflow.route-policy", "agent-workflow.task-intent", "agent-workflow.route-decision", "agent-workflow.approval-proof"],
      "callables": [],
      "consumers": ["task-4", "task-5", "task-6"]
    },
    {
      "interface_id": "core.saved-plan.v1",
      "definition_owner": "task-1",
      "implementation_owner": "task-3",
      "schema_ids": ["agent-workflow.saved-plan"],
      "callables": ["render_saved_plan(PlanCore) -> SavedPlanEnvelope"],
      "consumers": ["task-3", "task-4", "task-6"]
    },
    {
      "interface_id": "core.task-snapshot.v1",
      "definition_owner": "task-1",
      "implementation_owner": "task-4",
      "schema_ids": ["agent-workflow.task-quiescence-snapshot", "agent-workflow.task-findings"],
      "callables": ["scan_task_quiescence(VerifiedTrellisTaskLayout, VerifiedTrellisTaskLayout, VerifiedDiscoverySchemas, VerifiedDiscoverySchemas) -> TaskSnapshotAndFindings"],
      "consumers": ["task-3", "task-4", "task-6"]
    },
    {
      "interface_id": "core.task-evaluators.v1",
      "definition_owner": "task-1",
      "implementation_owner": "task-1",
      "schema_ids": ["agent-workflow.task-quiescence-snapshot", "agent-workflow.task-findings", "agent-workflow.candidate-impact"],
      "callables": [
        "evaluate_workspace_state_quiescence(TaskQuiescenceSnapshot, TaskFindings) -> WorkspaceTaskState",
        "evaluate_task_gate(TaskGateOperation, CandidateImpact, TaskQuiescenceSnapshot, TaskFindings) -> TaskGateResult"
      ],
      "consumers": ["task-3", "task-4", "task-6"]
    },
    {
      "interface_id": "core.workspace-diagnostics.v1",
      "definition_owner": "task-1",
      "implementation_owner": "task-4",
      "schema_ids": ["agent-workflow.workspace-diagnostic"],
      "callables": [],
      "consumers": ["task-4", "task-5", "task-6"]
    },
    {
      "interface_id": "core.render-projection.v1",
      "definition_owner": "task-1",
      "implementation_owner": "task-3",
      "schema_ids": ["agent-workflow.render-unit", "agent-workflow.ownership-decision"],
      "callables": [],
      "consumers": ["task-3", "task-5", "task-6"]
    },
    {
      "interface_id": "core.errors.v1",
      "definition_owner": "task-1",
      "implementation_owner": "task-1",
      "schema_ids": ["agent-workflow.resolution-failure", "agent-workflow.workspace-diagnostic"],
      "callables": [],
      "consumers": ["task-2", "task-3", "task-4", "task-5", "task-6"]
    }
  ],
  "digest_domains": [
    "agent-workflow.workflow-lock.v1",
    "agent-workflow.artifact-definition.v1",
    "agent-workflow.task-contract.v1",
    "agent-workflow.task-surfaces.v1",
    "agent-workflow.task-quiescence.v1",
    "agent-workflow.surface-registry.v1",
    "agent-workflow.runtime-surface.v1",
    "agent-workflow.surface-coverage.v1",
    "agent-workflow.desired-state-ir.v1",
    "agent-workflow.candidate-impact.v1",
    "agent-workflow.route-policy.v1",
    "agent-workflow.task-intent.v1",
    "agent-workflow.route-decision-payload.v1",
    "agent-workflow.route-decision.v1",
    "agent-workflow.route-task-state.v1",
    "agent-workflow.workspace-diagnostic.v1",
    "agent-workflow.plan-core.v1",
    "agent-workflow.journal-binding.v1",
    "agent-workflow.saved-plan.v1",
    "agent-workflow.feature-interface.v1"
  ],
  "digest_domain_owners": {
    "agent-workflow.workflow-lock.v1": "core.profile-resolution.v1",
    "agent-workflow.artifact-definition.v1": "core.artifact-policy.v1",
    "agent-workflow.task-contract.v1": "core.task-snapshot.v1",
    "agent-workflow.task-surfaces.v1": "core.route-contract.v1",
    "agent-workflow.task-quiescence.v1": "core.task-snapshot.v1",
    "agent-workflow.surface-registry.v1": "core.surface-impact.v1",
    "agent-workflow.runtime-surface.v1": "core.surface-impact.v1",
    "agent-workflow.surface-coverage.v1": "core.surface-impact.v1",
    "agent-workflow.desired-state-ir.v1": "core.profile-resolution.v1",
    "agent-workflow.candidate-impact.v1": "core.surface-impact.v1",
    "agent-workflow.route-policy.v1": "core.route-contract.v1",
    "agent-workflow.task-intent.v1": "core.route-contract.v1",
    "agent-workflow.route-decision-payload.v1": "core.route-contract.v1",
    "agent-workflow.route-decision.v1": "core.route-contract.v1",
    "agent-workflow.route-task-state.v1": "core.route-contract.v1",
    "agent-workflow.workspace-diagnostic.v1": "core.workspace-diagnostics.v1",
    "agent-workflow.plan-core.v1": "core.saved-plan.v1",
    "agent-workflow.journal-binding.v1": "core.saved-plan.v1",
    "agent-workflow.saved-plan.v1": "core.saved-plan.v1",
    "agent-workflow.feature-interface.v1": "core.schema-catalog.v1"
  },
  "error_namespace": "core.errors.v1"
}
~~~

Approval of this feature spec will freeze only the interfaces above. It will not approve any Task 2–6 feature spec or any implementation plan.

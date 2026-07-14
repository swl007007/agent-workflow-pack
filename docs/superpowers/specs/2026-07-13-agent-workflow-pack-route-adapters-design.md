# Agent Workflow Pack Route Admission and Platform Adapters Design

**Status:** Approved
**Approval:** Covered by explicit user blanket approval on 2026-07-13 after successful self-review
**Dependencies:** Approved Core Resolver, Renderer/Reconciler, and Runtime/Task-State feature specs
**Implementation gate:** No implementation until the Route/Adapters implementation plan is separately approved

## 1. Scope and Routing Ownership

Task 5 implements the canonical route calculator/verifier, platform direct-human approval verification, platform capability measurement, adapter projections, generated wrappers, native-light bindings, route-gated catalog exposure, and platform golden contracts.

It consumes and conforms to the closed RouteDecision, TaskIntent, ApprovalProof, CapabilityManifest, runtime-surface, render-unit, workspace-diagnostic, and Task-state Service contracts. It may not redefine those schemas, task lifecycle, runtime-load authorization, artifact ownership, or CLI error meaning.

The route calculator is the canonical policy calculation, not a cryptographic issuer. Unsigned Decision identity and digest establish deterministic internal consistency for supplied fields; executable consumers still replay current policy and authority. Natural-language-to-signal extraction is outside the security boundary.

Routing ownership is:

~~~text
maintenance block
  -> pinned current task mode
  -> explicit user selection
  -> compiled heavy-signal policy
  -> native-light
~~~

heavy-development-router is the sole top-level orchestrator only after an admitted task has mode speckit-superpowers. Superpowers executors and disciplines may be invoked only as leaves of that router. Native-light and Trellis-native paths do not pass through the heavy router.

Imported frozen interfaces:

| Interface | Producer C | Registry R | Digest |
|---|---|---|---|
| core.schema-catalog.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| core.profile-resolution.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| core.artifact-policy.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| core.surface-impact.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| core.capability-manifest.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| core.route-contract.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| core.workspace-diagnostics.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| core.render-projection.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| runtime.task-state.v1 | 0bc82617df4ea6f09b59c827ab925faf36904b49 | f9a16a120a4c95bb0555a739d3f4ef89eca8938f | bca14e8b426f9253a5922572d2719ecb6a7faeb6ae29c1a59b8d156a842fd388 |
| core.errors.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| runtime.errors.v1 | 0bc82617df4ea6f09b59c827ab925faf36904b49 | f9a16a120a4c95bb0555a739d3f4ef89eca8938f | bca14e8b426f9253a5922572d2719ecb6a7faeb6ae29c1a59b8d156a842fd388 |

## 2. Stable Signals and Compiled Heavy Policy

The versioned compiled policy uses stable signal IDs only. v0.1 hard signals are:

~~~yaml
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
~~~

Rules have stable IDs, closed predicates, one owner, deterministic priority, and no executable expressions. The calculator validates unknown/duplicate signals and evaluates normalized sets in stable order.

Explicit trellis-native selection is required; mentioning Trellis in prose is not selection. Explicit speckit-superpowers or any matching heavy rule selects the heavy route. Without an explicit integrated selection or heavy match, route is native-light. Conflicting explicit modes are errors, not priority ties.

The locked migration fixture maps every legacy Router trigger to the stable signal set. v0.1 must preserve the effective heavy boundary. Removing or weakening a legacy trigger requires an ADR, profile/policy version change, and reviewed old/new golden cases.

The same compiled policy bytes and digest are used by the calculator, execute-light verifier, task-admission verifier, heavy router admission checks, and test-routing. An adapter cannot maintain a second signal or rule list.

## 3. Task Intent Contract

The imported TaskIntent is the sole executable signal source:

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

For execute-light and create-integrated-task, the CLI accepts one intent document and rejects a separate --signals option. The normalized Decision signal array must equal the normalized Intent signal set byte-for-byte. Intent normalization, requested mode, and all stable signals participate in the imported intent digest.

classify-only may accept a candidate stable signal set without Intent. Its result cannot be promoted in place. A later executable operation rereads current authority and, for executable branches, requires an Intent.

Adapters may provide instructions that encourage conservative extraction, but the system cannot prove that every natural-language signal was identified. Deterministic guarantees begin after the signal IDs are supplied. Reasons are presentation/provenance inputs, participate in the Decision digest, and never change policy evaluation.

## 4. Frozen Route Decision Union Conformance and Calculator

### 4.1 Callable and authority snapshot

~~~text
calculate_route(
  operation: classify-only | execute-light | create-integrated-task,
  normalized_inputs: RouteCalculationInputs,
  authorities: VerifiedRouteAuthoritySnapshot
) -> RouteDecision | RouteFailure
~~~

The calculator validates the committed runtime, Manifest, matching workspace contract, profile, lock, artifact bundle, compiled route policy, adapter/harness identity, surface registry, and task-state evidence. It takes the runtime-state gate in shared mode, or exclusive mode where portable shared locking is unavailable, and emits no Decision during maintenance or an unfinished task transaction.

Caller flags cannot supply calculated route, decision identity/digest, authority digests, matched rules, entry owner, task-state digest, task surface digest, task ID, approval challenge, or approval requirement.

### 4.2 Closed branches

The implementation imports the Task 1 union without changing its fields:

| Operation | Legal route | Execution meaning |
|---|---|---|
| classify-only | any policy-admitted route | presentation-only, no Intent/task/challenge/approval fields |
| execute-light | native-light only | fresh Intent-bound Decision for one native-light dispatch |
| create-integrated-task | trellis-native or speckit-superpowers | task-bound Decision consumed only by task admit |

Fields from another branch fail closed. execute-light receiving an integrated route and create-integrated-task receiving native-light return AWP_ROUTE_OPERATION_MISMATCH and no executable Decision.

For create-integrated-task the calculator:

1. normalizes and validates an absent requested task ref;
2. generates a cryptographically random canonical UUIDv4 task ID;
3. generates a fresh 256-bit approval challenge;
4. verifies task-ID uniqueness and task-ref absence across Task 4's route-time inventory;
5. derives the complete task surface closure;
6. sets task_creation_approval required;
7. computes the imported task-state, intent, surface, payload, decision-ID, and decision digests.

The fixed UUIDv5 namespace and digest formulas are imported from core.route-contract.v1. The integrated Decision is unique because task ID and challenge are random even when policy inputs are otherwise identical.

### 4.3 Canonical verification

~~~text
verify_route_decision(
  decision: RouteDecision,
  current_authorities: VerifiedRouteAuthoritySnapshot,
  consumer: execute-light | task-admit
) -> VerifiedRouteDecision | RouteFailure
~~~

Verification rejects claimed origin as authority. It validates the branch schema, recomputes payload/UUIDv5/decision digests, rereads all current authority, reruns policy over supplied stable signals, recomputes task-state/surface preconditions where applicable, and requires exact route, rule IDs, entry owner, adapter version, and approval requirement.

A modified, stale, cross-operation, wrong-workspace, wrong-adapter, wrong-task, or policy-inconsistent envelope fails. Only execute-light consumes its branch. Only Task 4 task admit consumes create-integrated-task. classify-only is never executable.

After task admission, Decision ref-absence and state freshness are intentionally stale. Existing-task wrappers do not call this verifier; the recorded Decision remains provenance only.

## 5. Direct-Human Task-Creation Approval

### 5.1 Verifier boundary

Task 5 implements platform authenticity verification for the imported ApprovalProof branch:

~~~text
verify_task_creation_approval(
  proof: ApprovalProof,
  decision: VerifiedCreateIntegratedTaskDecision,
  capability: CapabilityManifest,
  runtime_context: VerifiedPlatformRuntimeContext
) -> VerifiedTaskCreationApproval | RouteFailure
~~~

The proof must bind:

- operation create-integrated-task;
- direct-human actor identity;
- supported verifier, adapter, and harness versions;
- issued/expires timestamps and profile TTL/clock-skew policy;
- workspace instance;
- task ID/ref and task-surface digest;
- intent and Route Decision digests;
- fresh approval challenge;
- opaque verifier receipt authenticated by the platform confirmation channel.

All values must equal the Decision/current context. Unknown fields, model-authored JSON, stdin, command flags, a generic yes token, or provider-approval fields fail.

Capability task_admission_gate must be enforced for the exact harness version. Instruction-only approval cannot satisfy the strict profile. A verifier version change affects new approvals only; unfinished admission recovery remains bound to its recorded verifier/runtime contract.

Task 5 verifies authenticity and returns a typed result. Task 4 owns replay reservation, one-transaction consumption, integration provenance, and crash recovery. The verifier does not edit approval-replay.json.

### 5.2 Confirmation presentation

Before confirmation, the platform presents one bounded immutable summary containing operation, route/mode, task ID/ref, intent title/objective/acceptance summary, matched rules/signals, surface summary, workspace, expiry, and challenge identity. The receipt authenticates the structured fields rather than rendered free text alone.

Cancellation or timeout produces no proof and no target write. A proof is not implementation activation; the heavy router separately enforces its admitted task phase/claim contract.

## 6. Task Surface Closure at Admission

~~~text
derive_task_surface_closure(
  route: trellis-native | speckit-superpowers,
  platform: StablePlatformID,
  entry_owner: StableEntryOwner,
  registry: VerifiedRuntimeSurfaceRegistry
) -> TaskContractSurfaces | RouteFailure
~~~

The closure starts from the selected platform adapter, route owner, Trellis/runtime entry set, hooks, agents, commands, skills, and mode-specific entry points required for task execution. It traverses the verified acyclic reference graph and includes every transitive surface.

runtime-control-plane and surface-registry are mandatory for every integrated task. Heavy mode also includes heavy-development-router and its selected runtime entries; Trellis-native includes only the locked Trellis-native runtime entries and dependencies. The platform adapter surface is always exact to the selected platform.

Every record is the imported stable surface ID plus current verified surface digest, sorted by surface ID. Unknown, duplicate, dangling, cyclic, unowned, uncovered, or digest-inconsistent units block. Caller-supplied surfaces, wildcards, aggregate profile/lock digests, and inferred names are forbidden.

The calculator computes the imported task_contract_surfaces_digest. Task 4 recomputes the closure/digest at admission. Candidate impact later uses the same IDs and before/after digests, enabling adapter-specific and skill-specific affected/unaffected gating. Registry, inventory, recipe, reference-graph, and relevant CLI changes must appear through surface-registry or runtime-control-plane rather than disappearing from impact.

## 7. Existing-Task Wrapper and Runtime-Load Integration

Generated wrappers have exactly two executable branches.

### 7.1 Native-light branch

A native-light wrapper accepts only a fresh verified execute-light Decision and one locked platform native-light binding. It creates no Trellis task, integration file, approval proof, task transaction, or heavy claim. It cannot invoke task admit, Trellis runtime, heavy-development-router, or a route-gated catalog path.

The execute-light Decision is consumed for one in-process dispatch and is not returned as a bearer token. Authority is rechecked immediately before dispatch. classify-only is rejected.

### 7.2 Integrated existing-task branch

An integrated wrapper accepts current task ID/ref, expected lifecycle revision/status, expected mode phase and claim state, requested surface ID, and runtime-entry ID. It invokes only:

~~~text
.agent-workflow/bin/agent-stack task runtime load ...
~~~

It never replays the create Decision, reads integration.yaml directly as authority, resolves agent-stack from PATH, opens .agent-workflow/runtime/**, imports a packaged gated module, or returns a reusable token.

Task 4 authorizes and constructs the immutable in-memory dispatch bundle. The wrapper or adapter dispatches only the already validated entry in that bundle. A state, surface, mode, claim, content, or maintenance mismatch fails before entry execution.

heavy-development-router is selected only by a heavy task's pinned entry. It remains the sole top-level orchestrator and may invoke Superpowers leaves under its contract. Trellis-native dispatches its own locked entry without entering the heavy router.

### 7.3 Bypass closure

All supported platform-native direct entries for integrated create, implement, finish, archive, heavy phase commands, or gated skills must be absent, hidden, or technically redirected through the wrapper. If a harness cannot prevent a bypass, the corresponding capability is instruction-only or unsupported. Instructions alone never justify enforced.

## 8. Platform Capability Manifest and Enforcement Levels

Task 5 populates the imported CapabilityManifest schema. Capability ordering is:

~~~text
unsupported < instruction-only < enforced
~~~

A capability is enforced only when a locked, version-bound integration test proves the supported entry cannot bypass its technical gate. instruction-only means model/user compliance is required. unsupported means no usable mechanism exists.

Each measured manifest binds:

- platform, adapter, and exact harness identity/version;
- exact tested versions or one closed tested range;
- probe suite ID/version and normalized result per capability;
- approval verifier ID/version and actor/receipt sources;
- evidence digest and integration-evidence IDs;
- caller-context fields used by read-only doctor probes.

A version range may be declared only when every boundary and compatibility rule is tested. Unknown or unprobed capability is unsupported, not optimistic enforced.

Required capability keys include project instructions, explicit runtime load, maintenance gate, task admission gate, task archive gate, provider exception approval, project skills, native-light binding, route-gated catalog, and direct-human confirmation.

The Resolver compares actual against profile minimum. sol56-sdd performs no downgrade. Claude Code, Codex, and OpenCode remain default platforms only when each exact locked harness contract meets every minimum. One failing default platform blocks materialization rather than silently dropping it.

doctor uses Task 4's post-verification caller context and only bounded read-only probes. If evidence would require mutation, ordinary doctor reports unverified; an explicit authorized probe may establish it. Capability evidence cannot alter release or wheel identity.

## 9. Claude Code, Codex, and OpenCode Bindings

### 9.1 Closed PlatformAdapterContract

Every platform is an immutable locked object:

~~~yaml
schema_id: agent-workflow.platform-adapter
schema_version: 1
platform: codex
adapter_id: codex
adapter_version: 1.0.0
tested_harness_versions: []
native_light_entry_id: sol-native
caller_context_fields: []
capability_probe_suite: {}
approval_verifiers: {}
render_projections: []
wrapper_entries: []
blocked_bypass_entries: []
trellis_adapter_contract: {}
golden_contract_id: codex-v1
~~~

render_projections contain exact logical unit ID, target path, ownership/merge/mode policy, owning surface ID, template/validator IDs, and discoverability. wrapper_entries bind operation, runtime entry, allowed mode/phase/claim predicate, and Task 4 command projection. blocked_bypass_entries identify every harness-native path that would evade admission/runtime/archive gates.

The adapter may project only IR-selected units and capabilities. It cannot add a route, signal, owner, skill, command, hook, agent, metadata path, or capability absent from verified inputs.

### 9.2 Initial platform bindings

| Platform | native-light owner | Required integrated behavior |
|---|---|---|
| Claude Code | locked platform-native lightweight planning entry | project instructions plus version-tested wrapper/hook/confirmation mechanisms |
| Codex | sol-native | AGENTS/project-skill projection plus version-tested hook/confirmation/runtime-load mechanisms |
| OpenCode | locked platform-native lightweight planning entry | project instructions plus version-tested command/plugin/confirmation mechanisms |

The exact paths and bytes are data in the locked PlatformAdapterContract and imported RenderUnit projections, not hard-coded alternate policy in adapter code. Each output is owned by one surface and participates in coverage and golden snapshots.

A platform implementation must prove:

- repository-relative launcher invocation;
- maintenance and task-state gating;
- direct-human task creation and provider exception receipts where required;
- all integrated execution through task runtime load;
- all integrated finish/archive through Task 4;
- route-gated runtime absent from auto-discovery;
- native-light unable to reach integrated/heavy entries;
- caller-context capture limited to its allowlisted external config/harness fields.

Trellis active/archive roots, metadata contracts, integration location, archive destination function, and pre-commit side-effect suppression are explicit locked adapter data and pass Core cross-ownership validation.

## 10. Discoverable Leaf and Route-Gated Catalog Projection

The route-gated catalog is managed and non-discoverable:

~~~text
.agent-workflow/runtime/
  heavy-development-router/
  speckit-evidence-pack/
  sdd-superpower-micro-plan/
  claude-mem-compactor/
  trellis-native/
~~~

Non-discoverability is exposure control, not a filesystem security boundary. Gated content is reachable only through a generated wrapper and Task 4 runtime load.

Only allowlisted leaf skills may enter platform auto-discovery directories. Before projection, Task 5 traverses their locked content/reference graph. A leaf whose upstream content references using-superpowers, a planner/executor, a heavy router, a task command, or another gated entry requires a first-party locked compatibility overlay or is blocked.

Disabled precedence is absolute. Disabled/gated nodes cannot appear as discoverable leaves or be referenced transitively from one. Every projected leaf, wrapper, command, hook, agent, and instruction block is a frozen RenderUnit with one surface owner and complete digest recipe coverage.

Adapter projection is:

~~~text
project_platform_adapter(
  ir: DesiredStateIR,
  adapter: VerifiedPlatformAdapterContract
) -> PlatformAdapterProjection | RouteFailure
~~~

The result is deterministic, contains no target observations, and is consumed by Task 3 rendering. Different distributions must produce the same logical projection for the same IR/adapter.

## 11. Golden Routing and Adapter Tests

### 11.1 Routing tests

Golden cases cover:

- every hard signal and compound rule;
- native-light small work;
- explicit trellis-native and explicit heavy selection;
- conflicting explicit modes;
- legacy trigger parity;
- unknown/duplicate signals and rule conflicts;
- classify-only non-executability;
- execute-light integrated-route rejection;
- create-integrated-task native-light rejection;
- deterministic matched-rule ordering and reasons;
- executable signal source restricted to Intent;
- Decision digest/UUID namespace and authority freshness;
- task-ID/challenge uniqueness;
- hand-constructed policy-consistent Decision accepted only after complete replay, never by issuer claim.

### 11.2 Surface and wrapper tests

Surface tests cover adapter-specific and skill-specific closures, mandatory meta-surfaces, transitive dependencies, removals, registry/control-plane changes, missing/duplicate ownership, cycles, and digest mismatch.

Wrapper tests prove execute-light isolation, stale create-Decision non-reuse, exact task runtime load arguments, immutable bundle dispatch, no PATH lookup, no catalog reopen, maintenance block, phase/claim mismatch, and heavy router sole-orchestrator behavior.

### 11.3 Platform golden tests

For every supported Claude Code, Codex, and OpenCode harness version:

1. materialize exact adapter outputs and compare byte/mode golden snapshots;
2. enumerate auto-discovery and prove gated catalog absence;
3. probe each CapabilityManifest claim and compare evidence digest;
4. attempt every declared bypass entry;
5. obtain/cancel/expire direct-human approval and reject model-authored substitutes;
6. run native-light, Trellis-native, and heavy integrated paths;
7. archive only through Task 4;
8. re-enumerate runtime-visible units and prove surface coverage.

A platform version outside its closed tested contract is unsupported until a new reviewed adapter contract and golden evidence are released.

### 11.4 Route/adapter errors

| Code | Exit | Meaning |
|---|---:|---|
| AWP_ROUTE_OPERATION_MISMATCH | 2 | requested operation cannot execute the calculated route |
| AWP_ROUTE_SIGNAL_INVALID | 2 | signal set is unknown, duplicated, or illegal for Intent |
| AWP_ROUTE_POLICY_MISMATCH | 40 | Decision policy result or authority snapshot is stale/inconsistent |
| AWP_ROUTE_DECISION_INVALID | 2 | union, UUID, digest, or cross-branch fields are invalid |
| AWP_ROUTE_TASK_STATE_STALE | 40 | task identity/ref/surface state changed after calculation |
| AWP_ROUTE_SURFACE_CLOSURE_INVALID | 2 | integrated surface closure is incomplete or inconsistent |
| AWP_ROUTE_APPROVAL_INVALID | 22 | approval fields or direct-human receipt do not verify |
| AWP_ROUTE_APPROVAL_EXPIRED | 22 | new admission proof is outside allowed time window |
| AWP_ADAPTER_CONTRACT_INVALID | 2 | platform contract or projection contains an illegal unit/binding |
| AWP_ADAPTER_CAPABILITY_UNVERIFIED | 23 | required capability lacks version-bound enforced evidence |
| AWP_ADAPTER_BYPASS_DETECTED | 23 | a supported native entry bypasses the required wrapper/gate |
| AWP_ADAPTER_PROJECTION_INVALID | 2 | rendered platform output is incomplete or nondeterministic |

Task 6 may map these errors to presentation but may not change their meaning or exit category.

## 12. Acceptance-Criteria Mapping and Downstream Freeze

### 12.1 Primary acceptance ownership

| AC | Primary Task 5 evidence |
|---|---|
| AC-02 | strict profile materializes all three initial platforms only when capabilities pass |
| AC-03 | adapters project one resolved policy and cannot add routes/owners/capabilities |
| AC-22 | native-light, Trellis-native, and heavy ownership remain disjoint and deterministic |
| AC-30 | RouteDecision is a closed three-branch union with honest authenticity limits |
| AC-59 | exact stable surface closure and affected/unaffected adapter/skill behavior |

Task 5 supplies integration evidence for AC-12, AC-13, AC-25, AC-27, AC-32, AC-33, AC-45, AC-58, AC-61, AC-62, and AC-64 without changing their primary owners.

### 12.2 Exported interface

The following object is the complete approved Task 5 interface. Its digest is computed from this producer-content commit and recorded by a later registry commit.

~~~json
{
  "interface_schema": "agent-workflow.feature-interface",
  "interface_version": 1,
  "producer_task": "task-5",
  "producer_feature": "route-admission-and-platform-adapters",
  "schema_versions": {
    "agent-workflow.platform-adapter": 1,
    "agent-workflow.platform-adapter-projection": 1,
    "agent-workflow.approval-verification-result": 1,
    "agent-workflow.adapter-golden-contract": 1,
    "agent-workflow.route-failure": 1
  },
  "exports": [
    {
      "interface_id": "route.adapters.v1",
      "definition_owner": "task-5",
      "implementation_owner": "task-5",
      "schema_ids": [
        "agent-workflow.platform-adapter",
        "agent-workflow.platform-adapter-projection",
        "agent-workflow.approval-verification-result",
        "agent-workflow.adapter-golden-contract"
      ],
      "callables": [
        "calculate_route(RouteCalculationInputs, VerifiedRouteAuthoritySnapshot) -> RouteDecision | RouteFailure",
        "verify_route_decision(RouteDecision, VerifiedRouteAuthoritySnapshot, RouteConsumer) -> VerifiedRouteDecision | RouteFailure",
        "verify_task_creation_approval(ApprovalProof, VerifiedCreateIntegratedTaskDecision, CapabilityManifest, VerifiedPlatformRuntimeContext) -> VerifiedTaskCreationApproval | RouteFailure",
        "derive_task_surface_closure(IntegratedRoute, StablePlatformID, StableEntryOwner, VerifiedRuntimeSurfaceRegistry) -> TaskContractSurfaces | RouteFailure",
        "measure_capability_manifest(PlatformProbeInputs) -> CapabilityManifest | RouteFailure",
        "project_platform_adapter(DesiredStateIR, VerifiedPlatformAdapterContract) -> PlatformAdapterProjection | RouteFailure",
        "invoke_execute_light(VerifiedExecuteLightDecision, VerifiedPlatformRuntimeContext) -> NativeLightDispatch | RouteFailure",
        "invoke_integrated_wrapper(IntegratedTaskInvocation) -> ImmutableDispatchBundle | RuntimeFailure"
      ],
      "consumers": ["task-6"]
    },
    {
      "interface_id": "route.errors.v1",
      "definition_owner": "task-5",
      "implementation_owner": "task-5",
      "schema_ids": ["agent-workflow.route-failure"],
      "callables": [],
      "consumers": ["task-6"]
    }
  ],
  "digest_domains": [
    "agent-workflow.platform-adapter.v1",
    "agent-workflow.platform-adapter-projection.v1",
    "agent-workflow.approval-verification-result.v1",
    "agent-workflow.adapter-golden-contract.v1"
  ],
  "digest_domain_owners": {
    "agent-workflow.platform-adapter.v1": "route.adapters.v1",
    "agent-workflow.platform-adapter-projection.v1": "route.adapters.v1",
    "agent-workflow.approval-verification-result.v1": "route.adapters.v1",
    "agent-workflow.adapter-golden-contract.v1": "route.adapters.v1"
  },
  "error_namespace": "route.errors.v1"
}
~~~

This approval freezes only Task 5's exported interface. It does not approve Task 6 or any implementation plan or production implementation.


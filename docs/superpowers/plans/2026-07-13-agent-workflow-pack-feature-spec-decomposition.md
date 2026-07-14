# Agent Workflow Pack Feature-Spec Decomposition Implementation Plan

> **Execution authority:** This plan does not select a second top-level executor. Execution follows the current route/integration contract; when `mode: speckit-superpowers`, `heavy-development-router` is the sole top-level orchestrator and may invoke Superpowers only as a leaf discipline. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce and approve six implementation-ready feature specifications from the approved Agent Workflow Pack v0.1 umbrella design before any production code is written.

**Plan status:** Approved — decomposition boundary and execution graph frozen

**Approval scope:** This approval authorizes Task 1 feature-spec drafting to begin. It does not approve any feature spec or implementation plan that has not yet been produced and reviewed.

**Architecture:** The approved umbrella design remains the sole cross-feature authority. Each feature spec owns one bounded subsystem, freezes its schemas and callable interfaces, maps its acceptance criteria, and exposes only the contracts needed by later specs. Work proceeds in the exact Section 31 order so later specs consume reviewed interfaces instead of inventing parallel planners, writers, loaders, or trust roots.

**Tech Stack:** Markdown design specifications, RFC 8785 JCS and SHA-256 contract notation, JSON/YAML schema contracts, Python `>=3.11,<3.15`, self-contained wheel packaging, WSL2/Linux filesystem semantics, pytest-based future verification.

## Global Constraints

- The umbrella authority is `docs/superpowers/specs/2026-07-13-agent-workflow-pack-design.md` at status `Approved`.
- The frozen umbrella baseline is commit `568689d3fa4f9a39500b2b0a294387db02a0fccc`; the exact approved umbrella content SHA-256 is `c2f23807cc36066b4b92478657cacaf15eb5cb6bd14e307e1e76f1c30de0284d`. The path, commit, and content digest are all required inputs; a mismatch stops this plan and requires an umbrella-spec erratum and renewed approval.
- This plan creates documentation only. Do not create or modify `src/`, `tests/`, `schemas/`, package metadata, runtime artifacts, or generated project files.
- Each feature spec must be approved before its implementation plan or production implementation begins.
- No task may consume a feature spec by path alone. A downstream task may start only after the upstream spec has an `Approved` status, an `interface-frozen` record, and the exact exported-interface SHA-256 recorded in the interface registry below.
- Feature specs must preserve the sole Resolver, Reconciler, route-policy source, Task-state Service, release trust root, ownership source, and task-state authority defined by the umbrella design.
- Runtime Python support is exactly `>=3.11,<3.15`; the published wheel has no external runtime `Requires-Dist` dependencies.
- v0.1 targets WSL2 and Linux only and fails closed when required lock, atomic-replace, mode, or path-collision semantics are unavailable.
- Every structured digest uses a named domain, RFC 8785 JCS, and SHA-256; every dependency graph must be acyclic.
- Schema identity and schema version remain separate fields. Every schema ID, schema version, and digest domain is inherited verbatim from the umbrella where one exists; a new identifier must declare its own schema-ID rule and its own digest domain. The plan must not rewrite `agent-workflow.workspace-local` plus `schema_version: 1` into `agent-workflow.workspace-local.v1`, and must not treat a digest domain such as `agent-workflow.task-contract.v1\0` as a schema ID.
- Every schema is closed and versioned. Unknown fields, duplicate YAML keys, unsupported versions, ambiguous ownership, and unclassified runtime-visible units fail closed.
- No feature spec may weaken protected paths, capability requirements, direct-human approval, supply-chain verification, CAS preconditions, transaction recovery, or checkout-local scope disclosures.
- Feature specs may clarify an umbrella contract but may not silently change product scope. A contradiction requires an explicit umbrella-spec erratum and renewed approval.

## Frozen Execution Baseline and Ownership Registry

Before Task 1 starts, run the following baseline check from the repository root:

```bash
git merge-base --is-ancestor 568689d3fa4f9a39500b2b0a294387db02a0fccc HEAD
test "$(git show HEAD:docs/superpowers/specs/2026-07-13-agent-workflow-pack-design.md | sha256sum | cut -d' ' -f1)" = "c2f23807cc36066b4b92478657cacaf15eb5cb6bd14e307e1e76f1c30de0284d"
test -z "$(git status --porcelain -- docs/superpowers/specs/2026-07-13-agent-workflow-pack-design.md)"
```

The umbrella section and acceptance mappings below are frozen against that exact content. A later edit at the same path is not an implicit refresh; stop and obtain an umbrella erratum before changing any owner, consumer, interface, or acceptance mapping.

### Cross-feature contract ownership

The first column is the sole schema/type/policy definition owner. The second is the sole implementation owner; a consumer may call or render the contract but may not redefine it. Every exported interface is represented by a machine-readable `exported_interface` object in the owning feature spec and is digested as:

```text
interface_digest = SHA256(
  UTF8("agent-workflow.feature-interface.v1\0")
  || UTF8(JCS(exported_interface))
)
```

The exact 64-hex digest is computed from an approved producer-content commit `C` and written by a later registry commit `R`. `R` records `producer_content_commit=C`, the digest, and `state=interface-frozen`; it does not attempt to record its own Git hash. A consumer starts only after `R`; its feature-spec content records `C`, `R`, and the same digest. After that consumer content is committed as `D`, a later plan-registry update may record `consumer_content_commit=D` for ancestry auditing. Neither `R` nor `D` is written inside the commit whose identity it names. A path, filename, version label, or symbolic task number is not an imported interface digest.

| Contract | Definition owner | Implementation owner | Imported by | Freeze record |
|---|---|---|---|---|
| Schema catalog, schema IDs/versions, digest domains, canonicalization rules | Task 1 | Task 1 | Tasks 2–6 | `core.schema-catalog.v1` |
| Profile field merge, catalog dependency/conflict/reference closure, disabled precedence, capability evaluation | Task 1 | Task 1 | Tasks 3–6 | `core.profile-resolution.v1` |
| Artifact-definition and protected-path validation | Task 1 | Task 1 | Tasks 3–5 | `core.artifact-policy.v1` |
| Runtime-surface registry, unit inventory, reference graph, coverage proof, authority/surface/repair impact | Task 1 | Task 1 | Tasks 3–6 | `core.surface-impact.v1` |
| `CapabilityManifest` schema and capability evaluation result | Task 1 | Task 5 platform projection | Tasks 5–6 | `core.capability-manifest.v1` |
| `RouteDecision`, `ApprovalProof`, and route-operation discriminated union schema | Task 1 | Task 5 calculation/verification | Tasks 4–6 | `core.route-contract.v1` |
| `SavedPlanEnvelope` schema, plan-core projection, and digest DAG | Task 1 | Task 3 construction | Tasks 3, 4, 6 | `core.saved-plan.v1` |
| `TaskSnapshot`/`TaskFindings` schema and scanner signature | Task 1 | Task 4 scanner | Tasks 3, 4, 6 | `core.task-snapshot.v1` |
| Fixed workspace-state and task-gate evaluator policy/functions | Task 1 | Task 1 pure evaluator implementation | Tasks 3, 4, 6 | `core.task-evaluators.v1` |
| Workspace-state and command-admission diagnostic schema/result production | Task 1 | Task 4 state service | Tasks 4–6 | `core.workspace-diagnostics.v1` |
| Provider plan, acquisition result, approval exception, broker receipt, and attempt journal | Task 2 | Task 2 | Tasks 3, 6 | `providers.execution.v1` |
| Render-unit/projection schema and ownership-decision shape | Task 1 | Task 3 renderer projection | Tasks 3, 5, 6 | `core.render-projection.v1` |
| Reconcile-plan construction, lifecycle transaction policy, journal, CAS, and recovery result | Task 3 | Task 3 | Tasks 4, 6 | `renderer.reconcile.v1` |
| Task runtime commands, integration state, task identity, replay ledger, outbox, and task recovery | Task 4 | Task 4 | Task 5 wrapper; Task 6 CLI | `runtime.task-state.v1` |
| Platform bindings, wrapper projections, discoverable-leaf catalog projection, adapter golden contract | Task 5 | Task 5 | Task 6 | `route.adapters.v1` |
| Lifecycle command composition, packaging/release gates, compatibility and E2E orchestration | Task 6 | Task 6 | Release CI only | `lifecycle.release.v1` |
| Core/Resolver/workspace diagnostic error namespace | Task 1 | Task 1 | Tasks 2–6 | `core.errors.v1` |
| Provider/cache error namespace | Task 2 | Task 2 | Tasks 3, 6 | `providers.errors.v1` |
| Renderer/Reconciler error namespace | Task 3 | Task 3 | Tasks 4, 6 | `renderer.errors.v1` |
| Runtime/task-state error namespace | Task 4 | Task 4 | Tasks 5, 6 | `runtime.errors.v1` |
| Route/adapter/capability error namespace | Task 5 | Task 5 | Task 6 | `route.errors.v1` |
| CLI composition, JSON stdout/stderr/redaction mapping | Task 6 | Task 6 | None may redefine domain semantics | `lifecycle.cli-output.v1` |

`render_saved_plan` is a Task 1 schema/signature contract with Task 3 implementation ownership. `scan_task_quiescence` is a Task 1 schema/signature contract with Task 4 scanner implementation ownership. Task 1 owns and implements the two pure evaluator functions; Task 3 and Task 4 call them without redefining their policy. Task 5 consumes Task 1's render-unit/projection schema and Task 3's frozen renderer projection implementation interface; “approved platform capability contracts” is not an external dependency because the capability contract is defined in Task 1 and projected by Task 5. Task 6 imports all domain command and error contracts and may only compose output; it may not redefine task commands, route semantics, or error meaning.

The interface registry and consumer imports are structured TSV blocks in this plan, not prose notes. They begin with headers only; later registry commits append validated rows.

<!-- interface-registry:start -->
```tsv
interface_id	definition_owner	implementation_owner	producer_content_commit	exported_interface_digest	state	imported_by	required_before_unlock
core.schema-catalog.v1	task-1	task-1	2e0bfda7619223397f7c9610d312a2aab42156ab	a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77	interface-frozen	task-2,task-3,task-4,task-5,task-6	task-2
core.profile-resolution.v1	task-1	task-1	2e0bfda7619223397f7c9610d312a2aab42156ab	a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77	interface-frozen	task-3,task-4,task-5,task-6	task-3
core.artifact-policy.v1	task-1	task-1	2e0bfda7619223397f7c9610d312a2aab42156ab	a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77	interface-frozen	task-3,task-4,task-5	task-3
core.surface-impact.v1	task-1	task-1	2e0bfda7619223397f7c9610d312a2aab42156ab	a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77	interface-frozen	task-3,task-4,task-5,task-6	task-3
core.capability-manifest.v1	task-1	task-5	2e0bfda7619223397f7c9610d312a2aab42156ab	a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77	interface-frozen	task-5,task-6	task-5
core.route-contract.v1	task-1	task-5	2e0bfda7619223397f7c9610d312a2aab42156ab	a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77	interface-frozen	task-4,task-5,task-6	task-4
core.saved-plan.v1	task-1	task-3	2e0bfda7619223397f7c9610d312a2aab42156ab	a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77	interface-frozen	task-3,task-4,task-6	task-3
core.task-snapshot.v1	task-1	task-4	2e0bfda7619223397f7c9610d312a2aab42156ab	a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77	interface-frozen	task-3,task-4,task-6	task-3
core.task-evaluators.v1	task-1	task-1	2e0bfda7619223397f7c9610d312a2aab42156ab	a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77	interface-frozen	task-3,task-4,task-6	task-3
core.workspace-diagnostics.v1	task-1	task-4	2e0bfda7619223397f7c9610d312a2aab42156ab	a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77	interface-frozen	task-4,task-5,task-6	task-4
core.render-projection.v1	task-1	task-3	2e0bfda7619223397f7c9610d312a2aab42156ab	a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77	interface-frozen	task-3,task-5,task-6	task-3
core.errors.v1	task-1	task-1	2e0bfda7619223397f7c9610d312a2aab42156ab	a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77	interface-frozen	task-2,task-3,task-4,task-5,task-6	task-2
providers.execution.v1	task-2	task-2	b19e57a0e4d6e5094b853d428909e4d10d2283de	8c3890facd3f57198a4427ef2497077b924b13c780b7ac9b14f5227106b21fdb	interface-frozen	task-3,task-6	task-3
providers.errors.v1	task-2	task-2	b19e57a0e4d6e5094b853d428909e4d10d2283de	8c3890facd3f57198a4427ef2497077b924b13c780b7ac9b14f5227106b21fdb	interface-frozen	task-3,task-6	task-3
```
<!-- interface-registry:end -->

<!-- consumer-imports:start -->
```tsv
consumer_task	consumer_content_commit	interface_id	producer_content_commit	registry_commit	imported_interface_digest
task-2	b19e57a0e4d6e5094b853d428909e4d10d2283de	core.schema-catalog.v1	2e0bfda7619223397f7c9610d312a2aab42156ab	14edc566f707bb6ad21c551f1112b7c4f543330c	a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77
task-2	b19e57a0e4d6e5094b853d428909e4d10d2283de	core.errors.v1	2e0bfda7619223397f7c9610d312a2aab42156ab	14edc566f707bb6ad21c551f1112b7c4f543330c	a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77
```
<!-- consumer-imports:end -->

For each exported interface, first commit the approved feature-spec content and obtain `producer_content_commit=C`. Read the `exported_interface` object from `C`, compute its digest, then create a later registry commit `R` that appends the registry row with `C` and `state=interface-frozen`. The row cannot contain `R` because that would recreate a Git self-reference. A consumer feature spec created after `R` records `C`, `R`, and the same digest and is then committed as `D`; only a later plan-registry update appends the audit row containing `consumer_content_commit=D`. The validator rejects missing or unexpected IDs, non-unique definition ownership, non-hex commits/digests, duplicate IDs, mismatched import digests, a producer content commit that is not an ancestor of the consumer content commit, or a registry commit that is not an ancestor of the consumer content commit.

### Umbrella section ownership and consumers

This matrix freezes the primary feature owner for every umbrella section from §§4–30. Subsection implementation ownership follows the cross-feature contract table above; consumers may not create a second authority.

| Umbrella section | Primary feature owner | Implementation focus | Consumers |
|---|---|---|---|
| §4 Core Authority Model | Task 1 | authority/schema boundary registry | Tasks 2–6 |
| §5 Planned Repository Structure | Task 6 | release/package layout contract | Tasks 1–5 |
| §6 Component Boundaries and Data Flow | Task 1 | cross-feature boundary map | Tasks 2–6 |
| §7 Profile Contract | Task 1 | merge, capability, and profile digest | Tasks 3–6 |
| §8 Catalog and Workflow Lock | Task 1 | closure, lock, Release Identity, compatibility inputs | Tasks 2–6 |
| §9 Artifact Definitions and Protected Paths | Task 1 | validation and protected-path policy | Tasks 3–5 |
| §10 Artifact Bundle Digest | Task 1 | bundle roots and surface coverage input | Tasks 3, 5, 6 |
| §11 Desired State IR | Task 1 | IR schema and Resolver output | Tasks 3, 6 |
| §12 Target Manifest | Task 3 | materialization and Manifest-last application | Tasks 4, 6 |
| §13 Ownership and Reconcile Semantics | Task 3 | file/block ownership and drift behavior | Tasks 4, 6 |
| §14 Lifecycle Commands | Task 6 | CLI composition; task/workspace command semantics imported from Tasks 4–5 | Tasks 1–5 |
| §15 Saved Reconcile Plans | Task 1 | envelope/schema; Task 3 constructs it | Tasks 3, 4, 6 |
| §16 Single-writer, CAS, and Transaction Protocol | Task 3 | locks, CAS, phases, recovery | Tasks 4, 6 |
| §17 Maintenance and Active-task Gate | Task 1 | policy/evaluator; Task 3/4 enforce | Tasks 3–6 |
| §18 Route-admission Policy | Task 1 | policy schema/compiled input; Task 5 realizes it | Tasks 4–6 |
| §19 Route Decision Contract | Task 1 | discriminated schema/provenance bounds; Task 5 calculates/verifies | Tasks 4–6 |
| §20 Runtime Control Plane Deployment | Task 4 | launcher, allowlist, caller context, runtime load | Tasks 5, 6 |
| §21 Integration State Contract | Task 4 | task identity, admission/archive, state machine | Tasks 5, 6 |
| §22 Capability Model | Task 1 | capability schema; Task 5 platform projection | Tasks 5, 6 |
| §23 Provider and Third-party Execution Security | Task 2 | provider isolation, broker, approval | Tasks 3, 6 |
| §24 Machine-readable Output and Errors | Task 1 | domain diagnostic/error schemas; Task 6 maps CLI output | Tasks 2–6 |
| §25 Deterministic Routing Tests | Task 5 | route and adapter goldens | Task 6 |
| §26 Test Strategy | Task 6 | integration/release test orchestration | Tasks 1–5 |
| §27 Packaging and Release | Task 6 | distributions, detached manifest, release gates | Tasks 1–5 |
| §28 Licensing and Provenance | Task 2 | provenance records; Task 6 release gate | Tasks 3, 6 |
| §29 Legacy Migration Requirements | Task 3 | legacy render/migration fixture and protected-state preservation | Task 6 |
| §30 v0.1 Acceptance Criteria | Task 6 | closure matrix only; primary owners are in the AC matrix below | Tasks 1–5 |

### Feature-spec review and interface-freeze state machine

Every feature follows the same executable loop; a keyword grep is never an approval:

```text
draft
  -> review-requested
  -> changes-required -> revised -> review-requested
  -> approved -> interface-frozen
```

At `draft`, create the file with `Status: Draft` and run its structural/schema checks. At `review-requested`, commit the draft and submit it for review. Every finding is either applied or explicitly resolved; unresolved findings keep the feature in `changes-required`. At `revised`, rerun the complete checks and submit again. Only when review reports no remaining blocking finding may the author set `Status: Approved` and commit the approved feature-spec content as `producer_content_commit=C`. The author then reads the closed `exported_interface` object from `C`, computes its exact `interface_digest`, and creates a later registry commit `R` that records `C + interface_digest + interface-frozen`. The next task is unlocked only after `R`; its consumer feature spec records `C`, `R`, and the same digest and is committed as `D`. A later plan-registry update records `D` for audit without asking `D` to contain itself. A later producer amendment creates a new content commit and registry commit and reopens every downstream consumer whose imported digest changes.

The per-task final step must therefore include:

1. commit the draft and set `review-requested`;
2. apply review findings through `changes-required`/`revised` until clean;
3. set `Approved` and commit the final feature-spec content as `producer_content_commit=C`;
4. read `exported_interface` from `C` and compute its SHA-256;
5. create a later registry commit `R` recording `C`, the digest, and `state=interface-frozen`, without recording `R` inside itself;
6. unlock the next task only after `R`, require its `Consumes` block to name `C`, `R`, and the exact digest, commit that consumer content as `D`, then record `D` only in a later plan-registry update.

### Acceptance-criteria primary ownership matrix

The following matrix is authoritative. It contains exactly one primary owner per AC; integration consumers and test layers are explicit. Task-local AC lists below must agree with this table.

| AC | Primary owner | Integration consumers | Test layer |
|---|---|---|---|
| AC-01 | Task 6 | Tasks 1-6 | release/e2e |
| AC-02 | Task 5 | Task 6 | golden/integration |
| AC-03 | Task 5 | Task 6 | golden/integration |
| AC-04 | Task 3 | Task 6 | reconciler/concurrency |
| AC-05 | Task 3 | Task 6 | reconciler/concurrency |
| AC-06 | Task 3 | Task 6 | reconciler/concurrency |
| AC-07 | Task 3 | Tasks 4, 6 | reconciler/concurrency |
| AC-08 | Task 3 | Tasks 4, 6 | reconciler/concurrency |
| AC-09 | Task 3 | Tasks 4, 6 | reconciler/concurrency |
| AC-10 | Task 3 | Tasks 4, 6 | reconciler/concurrency |
| AC-11 | Task 4 | Tasks 5, 6 | runtime/concurrency/e2e |
| AC-12 | Task 1 | Tasks 3-6 | schema/policy/property |
| AC-13 | Task 1 | Tasks 5, 6 | golden/integration |
| AC-14 | Task 6 | Tasks 1, 3, 5 | release/e2e |
| AC-15 | Task 2 | Tasks 3, 6 | provider/security/integration |
| AC-16 | Task 1 | Tasks 2-6 | contract/cli |
| AC-17 | Task 3 | Task 6 | reconciler/integration |
| AC-18 | Task 6 | Tasks 1, 2, 4 | release/e2e |
| AC-19 | Task 3 | Tasks 4, 6 | reconciler/concurrency |
| AC-20 | Task 3 | Tasks 4, 6 | reconciler/concurrency |
| AC-21 | Task 4 | Tasks 5, 6 | runtime/concurrency/e2e |
| AC-22 | Task 5 | Tasks 4, 6 | golden/integration |
| AC-23 | Task 4 | Task 6 | runtime/concurrency/e2e |
| AC-24 | Task 4 | Task 6 | runtime/concurrency/e2e |
| AC-25 | Task 4 | Tasks 5, 6 | runtime/concurrency/e2e |
| AC-26 | Task 3 | Tasks 4, 6 | reconciler/concurrency |
| AC-27 | Task 1 | Tasks 4-6 | schema/policy/property |
| AC-28 | Task 2 | Tasks 3, 6 | provider/security/integration |
| AC-29 | Task 6 | Tasks 1, 2, 4 | release/e2e |
| AC-30 | Task 5 | Tasks 4, 6 | golden/integration |
| AC-31 | Task 4 | Tasks 5, 6 | runtime/concurrency/e2e |
| AC-32 | Task 4 | Tasks 5, 6 | runtime/concurrency/e2e |
| AC-33 | Task 1 | Tasks 4, 5 | schema/policy/property |
| AC-34 | Task 1 | Tasks 3, 6 | schema/policy/property |
| AC-35 | Task 6 | Tasks 3, 4 | release/e2e |
| AC-36 | Task 4 | Tasks 5, 6 | runtime/concurrency/e2e |
| AC-37 | Task 3 | Tasks 4, 6 | reconciler/concurrency |
| AC-38 | Task 4 | Task 6 | runtime/concurrency/e2e |
| AC-39 | Task 4 | Tasks 5, 6 | runtime/concurrency/e2e |
| AC-40 | Task 2 | Tasks 4-6 | provider/security/integration |
| AC-41 | Task 1 | Tasks 3, 6 | schema/policy/property |
| AC-42 | Task 4 | Task 6 | runtime/concurrency/e2e |
| AC-43 | Task 4 | Tasks 5, 6 | runtime/concurrency/e2e |
| AC-44 | Task 2 | Tasks 4, 6 | provider/security/integration |
| AC-45 | Task 2 | Tasks 4-6 | provider/security/integration |
| AC-46 | Task 4 | Task 6 | runtime/concurrency/e2e |
| AC-47 | Task 4 | Task 6 | runtime/concurrency/e2e |
| AC-48 | Task 4 | Task 6 | runtime/concurrency/e2e |
| AC-49 | Task 2 | Task 6 | provider/security/integration |
| AC-50 | Task 6 | Task 2 | release/e2e |
| AC-51 | Task 1 | Tasks 4, 6 | schema/policy/property |
| AC-52 | Task 4 | Task 6 | runtime/concurrency/e2e |
| AC-53 | Task 1 | Task 4 | schema/policy/property |
| AC-54 | Task 4 | Task 6 | runtime/concurrency/e2e |
| AC-55 | Task 1 | Tasks 3, 4, 6 | schema/policy/property |
| AC-56 | Task 4 | Tasks 3, 6 | runtime/concurrency/e2e |
| AC-57 | Task 1 | Tasks 4, 6 | schema/policy/property |
| AC-58 | Task 4 | Tasks 1, 5, 6 | runtime/concurrency/e2e |
| AC-59 | Task 5 | Tasks 4, 6 | golden/integration |
| AC-60 | Task 1 | Tasks 4, 6 | schema/policy/property |
| AC-61 | Task 4 | Tasks 5, 6 | runtime/concurrency/e2e |
| AC-62 | Task 1 | Tasks 5, 6 | schema/policy/property |
| AC-63 | Task 3 | Tasks 4-6 | reconciler/concurrency |
| AC-64 | Task 1 | Tasks 4, 6 | schema/policy/property |

## Feature-Spec Artifact Map

| Order | Feature spec | Primary responsibility |
|---|---|---|
| 1 | `docs/superpowers/specs/2026-07-13-agent-workflow-pack-core-resolver-design.md` | Schemas, canonicalization, registry/inventory, Resolver, IR, plans, diagnostics |
| 2 | `docs/superpowers/specs/2026-07-13-agent-workflow-pack-providers-cache-design.md` | Acquisition, cache, provider isolation, approval, broker, provenance |
| 3 | `docs/superpowers/specs/2026-07-13-agent-workflow-pack-renderer-reconciler-design.md` | Rendering, ownership, planning, apply, repair, transactions, recovery |
| 4 | `docs/superpowers/specs/2026-07-13-agent-workflow-pack-runtime-task-state-design.md` | Launcher, workspace state, task runtime load, task mutations, migration |
| 5 | `docs/superpowers/specs/2026-07-13-agent-workflow-pack-route-adapters-design.md` | Route decisions, approvals, platform adapters, wrappers, capability projection |
| 6 | `docs/superpowers/specs/2026-07-13-agent-workflow-pack-lifecycle-release-design.md` | Lifecycle CLI, packaging, detached releases, compatibility, E2E release gates |

---

### Task 1: Core Schemas and Resolver Feature Spec

**Files:**
- Create: `docs/superpowers/specs/2026-07-13-agent-workflow-pack-core-resolver-design.md`
- Reference: `docs/superpowers/specs/2026-07-13-agent-workflow-pack-design.md`

**Interfaces:**
- Consumes: approved authority model; profile/catalog/workflow-lock contracts; release and artifact bundle identities; Trellis layout declarations; AC-12, AC-14, AC-16, AC-29, AC-34, AC-35, AC-41, AC-51, AC-53 through AC-60, AC-62, and AC-64.
- Produces: frozen schema catalog and inherited ID/version/digest rules; field-level profile merge and capability evaluation; catalog dependency/conflict/reference closure with disabled precedence; artifact-definition and protected-path validation; canonicalization and digest contracts; runtime-surface registry/inventory and coverage contract; `Desired State IR`; `candidate_impact`; the pure implementations of the fixed workspace-state evaluator and operation-specific task gate; the `SavedPlanEnvelope` schema/signature; and structured diagnostics consumed by Tasks 2 through 6. Task 3 implements `render_saved_plan`; Task 4 implements `scan_task_quiescence`; Tasks 3 and 4 call the Task 1 evaluators.

- [ ] **Step 1: Create the feature-spec skeleton and freeze its boundary**

Create the file with these exact top-level sections:

```markdown
# Agent Workflow Pack Core Schemas and Resolver Design

**Status:** Draft — feature-spec review required
**Umbrella spec:** `2026-07-13-agent-workflow-pack-design.md`
**Implementation gate:** No implementation until this feature spec is approved

## 1. Scope and Non-goals
## 2. Authority Inputs and Trust Assumptions
## 3. Schema Catalog and Versioning Rules
## 4. Canonicalization, Digest Domains, and Dependency DAGs
## 5. Runtime-Surface Registry, Unit Inventory, and Coverage Proof
## 6. Resolver Inputs, Validation Order, and Desired State IR
## 7. Candidate Authority, Surface, and Restorative-Repair Impact
## 8. Task Quiescence Snapshot and Evaluator Interfaces
## 9. Saved Plan and Candidate Manifest Envelope
## 10. Workspace-State and Command-Admission Diagnostics
## 11. Error Codes and Exit Categories
## 12. Test Matrix and Acceptance-Criteria Mapping
## 13. Downstream Interface Freeze
```

- [ ] **Step 2: Define the closed schema catalog and exact digest DAGs**

Inherit each umbrella schema ID and schema version verbatim, and inherit each approved digest domain verbatim. For a new identifier, declare the schema ID, numeric `schema_version`, and digest domain as separate fields; never apply one blanket `agent-workflow.<domain>.v1` template. Enumerate every domain owned by this feature and include exact canonical projections and exclusions for Release Identity, Trellis layout, surface registry, surface digest, task contract, task quiescence, local-state contract, plan core, journal binding, candidate Manifest, final plan, workspace diagnostic, and candidate impact. Include two explicit acyclic graphs:

```text
registry source -> surface roots -> coverage proof -> artifact bundle
plan core -> journal binding -> candidate Manifest -> final plan
```

State that no reverse edge, computed root in registry source, detached-manifest input in a distribution root, or final plan input in journal binding is legal.

- [ ] **Step 3: Freeze Resolver and evaluator interfaces**

Specify exact typed pseudocode for:

```text
resolve(inputs: ResolverInputs) -> DesiredStateIR | ResolutionFailure
compute_candidate_impact(current_contract, observed_state, candidate_ir) -> CandidateImpact
scan_task_quiescence(source_layout, target_layout, source_schemas, target_schemas) -> TaskSnapshotAndFindings
evaluate_workspace_state_quiescence(snapshot, findings) -> WorkspaceTaskState
evaluate_task_gate(operation, candidate_impact, snapshot, findings) -> TaskGateResult
render_saved_plan(plan_core) -> SavedPlanEnvelope
```

Define closed input/output fields, deterministic ordering, stable IDs, error precedence, and which downstream feature owns each caller. Task 1 owns and implements `evaluate_workspace_state_quiescence` and `evaluate_task_gate` as pure Resolver/Policy functions. Task 3 owns the `render_saved_plan` implementation and calls the evaluators during planning/coordination. Task 4 owns `scan_task_quiescence` and calls the evaluators for runtime/workspace state. Preserve `contract_before_digest`, `observed_before_digest`, and `after_digest` as separate fields. The exported interface block must list each schema ID, schema version, digest domain, callable signature, error namespace, and implementation-owner reference before its digest is frozen.

- [ ] **Step 4: Add full coverage and failure-case matrices**

Include tables proving:

- every packaged or rendered runtime-visible unit has exactly one canonical owning surface;
- `runtime-control-plane` and `surface-registry` are mandatory task surfaces;
- unowned, multiply owned, cyclic, dangling, omitted, or unclassified units block resolution;
- heavy contract change is exactly a nonempty authority vector or `change_kind: contract-change`;
- restorative repair requires an empty authority vector and `contract_before_digest == after_digest`;
- workspace task-quiescence is command-independent while command admission is operation-specific.
- profile merge, catalog dependency/conflict/reference closure, disabled precedence, capability evaluation, artifact-definition validation, and protected-path validation have one resolver owner and explicit failure cases;
- every `candidate_impact` surface ID is from the closed registry and carries the old/new digest fields required by the umbrella.

Primary AC ownership is AC-12, AC-13, AC-16, AC-27, AC-33, AC-34, AC-41, AC-51, AC-53, AC-55, AC-57, AC-60, AC-62, and AC-64. Task 1 supplies schema/digest primitives consumed by Task 4 for AC-58 but is not its primary owner. Tasks 2–6 provide the integration evidence listed in the frozen matrix but may not reassign these primary rows.

- [ ] **Step 5: Verify the feature spec**

Run:

```bash
rg -n "^## " docs/superpowers/specs/2026-07-13-agent-workflow-pack-core-resolver-design.md
rg -n "agent-workflow\.|resolve\(|compute_candidate_impact|scan_task_quiescence|evaluate_workspace_state_quiescence|evaluate_task_gate|AC-" docs/superpowers/specs/2026-07-13-agent-workflow-pack-core-resolver-design.md
git diff --check
```

Expected: all 13 sections exist; every listed interface and acceptance-criteria mapping is present; `git diff --check` prints nothing.

- [ ] **Step 6: Enter the review and interface-freeze loop**

```bash
git add docs/superpowers/specs/2026-07-13-agent-workflow-pack-core-resolver-design.md
git commit -m "Add core resolver feature spec"
```

Set the feature to `review-requested`. Apply every review finding through `changes-required` and `revised`, rerun Steps 2–5, then set `Status: Approved` and commit the final feature-spec content as `C`. Read the closed `exported_interface` object from `C`, compute `interface_digest`, and create a later registry commit `R` recording `C`, the digest, and `interface-frozen`. Unlock Task 2 only after `R`; Task 2 records `C`, `R`, and the same digest in its import record.

---

### Task 2: Providers and Secure Cache Feature Spec

**Files:**
- Create: `docs/superpowers/specs/2026-07-13-agent-workflow-pack-providers-cache-design.md`
- Consume: Task 1's recorded `interface-frozen` digest entries for the core contracts.

**Interfaces:**
- Consumes: the exact `interface_digest` values frozen by Task 1 for schema/catalog, diagnostics, Release Identity, provider-plan input, and candidate-output contracts; no path-only or version-only import is valid.
- Produces: cache namespace and lock protocol; hash-before-parse acquisition; initializer isolation policy; provider security policy; direct-human exception envelope; broker/attempt journal; deterministic output and provenance contracts consumed by Tasks 3 and 6.

- [ ] **Step 1: Create the feature-spec skeleton**

```markdown
# Agent Workflow Pack Providers and Secure Cache Design

**Status:** Draft — feature-spec review required
**Dependency:** Approved Core Schemas and Resolver feature spec

## 1. Scope and Non-goals
## 2. Provider Interface and Acquisition Result
## 3. Cache Namespace, Locks, and Atomic Publication
## 4. Download Limits, Hash-Before-Parse, and Archive Safety
## 5. Provider Security Policy and Capability Outcomes
## 6. Direct-Human Provider Exception Approval
## 7. Trusted Broker Handshake and Attempt Journal
## 8. Deterministic Initializer Output Contract
## 9. Provenance, Licenses, and Notices
## 10. Failure Recovery and Retry Semantics
## 11. Test Matrix and Acceptance-Criteria Mapping
## 12. Downstream Interface Freeze
```

- [ ] **Step 2: Freeze provider and cache state machines**

Define exact inputs and outputs for acquisition, cache lookup/publication, provider planning, approval verification, broker release, attempt transitions, and candidate-output validation. Preserve the closed attempt path:

```text
prepared -> released -> succeeded | failed | interrupted
```

Specify parent EOF, parent-death signal, release deadline, immutable release receipt, positive liveness evidence, serialized retries, and corrupt-state fail-closed behavior.

- [ ] **Step 3: Freeze isolation and determinism contracts**

Copy the umbrella requirements for fixed locale/timezone/environment, no ambient clock/random/hostname/user/path input, bounded output, exact command vector, provider security levels `required | approval-required | best-effort`, and repeated-output content-root verification. Primary AC ownership is AC-15, AC-28, AC-40, AC-44, AC-45, and AC-49; Task 6 consumes the release-gate evidence and Task 4 consumes provider recovery state.

- [ ] **Step 4: Verify and commit**

Run:

```bash
rg -n "prepared -> released|approve-provider-execution|hash-before|content-root|AC-15|AC-28|AC-40|AC-44|AC-45|AC-49" docs/superpowers/specs/2026-07-13-agent-workflow-pack-providers-cache-design.md
git diff --check
```

Expected: every provider state, approval binding, deterministic-output rule, and mapped AC is present; no whitespace errors.

```bash
git add docs/superpowers/specs/2026-07-13-agent-workflow-pack-providers-cache-design.md
git commit -m "Add providers and cache feature spec"
```

Set the feature to `review-requested`. Apply findings through `changes-required` and `revised`, rerun the provider checks, then set `Status: Approved` and commit the final feature-spec content as `C`. Compute the provider interface digest from `C`, then create a later registry commit `R` recording `C + digest + interface-frozen`. Unlock Task 3 only after `R`; Tasks 3 and 6 record the same `C`, `R`, and digest when they consume the interface.

---

### Task 3: Renderer and Reconciler Feature Spec

**Files:**
- Create: `docs/superpowers/specs/2026-07-13-agent-workflow-pack-renderer-reconciler-design.md`
- Consume: Task 1 and Task 2 `interface-frozen` digest entries; the spec paths are references, not authority.

**Interfaces:**
- Consumes: the exact frozen Task 1 digests for `DesiredStateIR`, artifact definitions, candidate impact, saved-plan envelope, and diagnostic/error contracts; the exact frozen Task 2 digest for verified provider outputs. Task 3 must expose its render-unit/projection interface for Task 5 and its transaction/recovery interface for Tasks 4 and 6.
- Produces: staged render tree, ownership decisions, approved reconcile plan, lifecycle journal, maintenance marker, restorative repair, apply/recovery results used by Tasks 4 and 6.

- [ ] **Step 1: Create the feature-spec skeleton**

```markdown
# Agent Workflow Pack Renderer and Reconciler Design

**Status:** Draft — feature-spec review required
**Dependencies:** Approved Core Resolver and Providers feature specs

## 1. Scope and Sole-Writer Boundary
## 2. Render Units, Deterministic Staging, and File Modes
## 3. Ownership Classes and Protected Paths
## 4. Plan Construction and Approval Envelope
## 5. Bootstrap and Project Lock Ordering
## 6. Lifecycle Journal, Maintenance, and Commit Point
## 7. File-State CAS and Atomic Replacement
## 8. Restorative `sync --repair`
## 9. Pre-commit Rollback and Post-commit Forward Recovery
## 10. Filesystem Probes and Portability Boundary
## 11. Test Matrix and Acceptance-Criteria Mapping
## 12. Downstream Interface Freeze
```

- [ ] **Step 2: Freeze transaction phases and file operations**

Define the exact lifecycle transaction phase table, immutable journal header, mutable fields, `journal_binding_digest`, maintenance binding, Manifest-last commit, created-directory cleanup, backup rules, and CAS comparisons over type, bytes, mode, and symlink status. Reconciler pre-commit may perform only journal-recorded, reversible file operations: validated staging writes, same-filesystem renames, backups, exact CAS checks, and cleanup of transaction-created empty directories. Hooks, notifications, subprocess callbacks, network effects, Git auto-commit, lifecycle hooks, and new lifecycle outbox mechanisms are forbidden. Task 3 receives no ordinary task-outbox mutation authority; it may only transform existing outbox state as an exact compatibility-edge schema migration already authorized by the umbrella. Task 4 alone defines admission/archive use of the Task-state Service outbox.

- [ ] **Step 3: Freeze ownership and restorative repair behavior**

Define whole-file managed, marked-block overlay, adopted baseline, create-once-then-user-owned, and user-owned behavior. Specify repair records with current contract, observed state, candidate state, approval, active-task evaluation, and CAS. Primary AC ownership is AC-04, AC-05, AC-06, AC-07, AC-08, AC-09, AC-10, AC-17, AC-19, AC-20, AC-26, AC-37, and AC-63. Task 4 consumes the transaction/repair results for AC-31, AC-38, AC-56, and runtime recovery; Task 6 consumes the release and E2E evidence.

- [ ] **Step 4: Verify and commit**

Run:

```bash
rg -n "Manifest-last|journal_binding_digest|maintenance|CAS|restorative|contract_before_digest|observed_before_digest|after_digest|AC-63" docs/superpowers/specs/2026-07-13-agent-workflow-pack-renderer-reconciler-design.md
git diff --check
```

Expected: transaction/ownership/repair contracts and mapped ACs are explicit; no whitespace errors.

```bash
git add docs/superpowers/specs/2026-07-13-agent-workflow-pack-renderer-reconciler-design.md
git commit -m "Add renderer and reconciler feature spec"
```

Set the feature to `review-requested`. Apply findings through `changes-required` and `revised`, rerun the renderer/reconciler checks, then set `Status: Approved` and commit the final feature-spec content as `C`. Compute the renderer interface digest from `C`, then create a later registry commit `R` recording `C + digest + interface-frozen`. Unlock Task 4 only after `R`; Tasks 4, 5, and 6 record the same `C`, `R`, and digest when they consume the interface.

---

### Task 4: Runtime Launcher and Task-State Service Feature Spec

**Files:**
- Create: `docs/superpowers/specs/2026-07-13-agent-workflow-pack-runtime-task-state-design.md`
- Consume: the `interface-frozen` digests exported by Tasks 1, 2, and 3; path-only dependencies are invalid.

**Interfaces:**
- Consumes: the exact Task 1 digests for release/runtime descriptor schemas, workspace diagnostics, task snapshot/evaluators, surface registry, and observed-digest recipes; the exact Task 2 provider/recovery digest where provider state is resumed; and the exact Task 3 Reconciler recovery/transaction digest. It implements the scanner, calls Task 1's pure evaluators, and consumes Task 3's reversible file-operation boundary.
- Produces: single-file launcher bootstrap, caller-context handoff, workspace register/migrate, task admission/mutation/archive/recovery, runtime-load authorization and dispatch contracts consumed by Task 5 and Task 6.

- [ ] **Step 1: Create the feature-spec skeleton**

```markdown
# Agent Workflow Pack Runtime Launcher and Task-State Service Design

**Status:** Draft — feature-spec review required
**Dependencies:** Approved Core Resolver, Providers, and Reconciler feature specs

## 1. Scope and Authority Boundaries
## 2. Single-File Launcher and Cold-Cache Bootstrap
## 3. Clean uv Environment and Verified Caller Context
## 4. Runtime Allowlist, Descriptor Validation, and Recovery Dispatch
## 5. Workspace Registration and Local-State Contracts
## 6. Workspace Migration and Quiescence Revalidation
## 7. Integration Schema and Immutable Task Identity
## 8. Task Admission, Claim, Transition, Release, and Archive
## 9. Existing-Task Runtime Load Authorization and In-memory Dispatch
## 10. Approval Replay Ledger and Task Outbox
## 11. Task Transactions, Crash Recovery, and Concurrency
## 12. Test Matrix and Acceptance-Criteria Mapping
## 13. Downstream Interface Freeze
```

- [ ] **Step 2: Freeze launcher and workspace protocols**

Define exact launcher constants, isolated uv argv, local Python prerequisite, permitted caller-context fields, descriptor post-start validation, committed/candidate runtime allowlist, workspace registration commit point, local-state migration phase table, fixed workspace-state evaluator use, command admission, and quiescence digest revalidation.

- [ ] **Step 3: Freeze task mutation and runtime-load protocols**

Define exact typed command contracts for:

```text
task runtime load
task admit
task claim
task transition
task release
task archive
task recover
workspace register
workspace migrate
```

For runtime load, require integration/task identity, expected revision/phase/claim, entry allowed-mode/phase/claim predicate, pinned surface membership, `observed == current contract == pinned` for the owning surface and dependencies, no-follow reads into an immutable in-memory bundle, and no reusable authorization token. Preserve create Decision as provenance only.

- [ ] **Step 4: Map task and workspace acceptance criteria**

Primary AC ownership is AC-11, AC-21, AC-23, AC-24, AC-25, AC-31, AC-32, AC-36, AC-38, AC-39, AC-42, AC-43, AC-46, AC-47, AC-48, AC-52, AC-54, AC-56, AC-58, and AC-61. Task 1 owns the schema/policy primitives consumed for AC-33, AC-51, AC-53, AC-55, AC-57, AC-58, AC-60, and AC-64; Task 4 owns AC-58's UUID task identity, ref reuse, archive destination, and runtime uniqueness behavior. Include crash points for registration, workspace migration, admission, archive, replay reservation, runtime-load races, and maintenance.

- [ ] **Step 5: Verify and commit**

Run:

```bash
rg -n "task runtime load|immutable in-memory|workspace migrate|task_quiescence|approval-replay|admitting|archiving|AC-61|AC-64" docs/superpowers/specs/2026-07-13-agent-workflow-pack-runtime-task-state-design.md
git diff --check
```

Expected: every command, commit point, authorization input, crash boundary, and mapped AC is present; no whitespace errors.

```bash
git add docs/superpowers/specs/2026-07-13-agent-workflow-pack-runtime-task-state-design.md
git commit -m "Add runtime and task-state feature spec"
```

Set the feature to `review-requested`. Apply findings through `changes-required` and `revised`, rerun the runtime/task-state checks, then set `Status: Approved` and commit the final feature-spec content as `C`. Compute the runtime interface digest from `C`, then create a later registry commit `R` recording `C + digest + interface-frozen`. Unlock Task 5 only after `R`; Tasks 5 and 6 record the same `C`, `R`, and digest when they consume the interface.

---

### Task 5: Route Admission and Platform Adapters Feature Spec

**Files:**
- Create: `docs/superpowers/specs/2026-07-13-agent-workflow-pack-route-adapters-design.md`
- Consume: the exact `interface-frozen` digests from Tasks 1, 3, and 4. Platform capability contracts are defined by Task 1 and projected/verified here; there is no undefined external capability-contract dependency.

**Interfaces:**
- Consumes: Task 1's frozen compiled-policy, stable-signal, task-intent, capability, and surface-closure contracts; Task 3's frozen render-unit/projection interface; and Task 4's frozen Task-state Service commands and runtime-load API. It may not redefine any of those domain semantics.
- Produces: a calculator/verifier conforming to Task 1's frozen closed Route Decision union, direct-human task approval verification semantics, platform bindings, generated wrappers, discoverable-leaf projection, and adapter golden contracts used by Task 6. Task 5 does not redefine the union schema.

- [ ] **Step 1: Create the feature-spec skeleton**

```markdown
# Agent Workflow Pack Route Admission and Platform Adapters Design

**Status:** Draft — feature-spec review required
**Dependencies:** Approved Core Resolver and Runtime Task-State feature specs

## 1. Scope and Routing Ownership
## 2. Stable Signals and Compiled Heavy Policy
## 3. Task Intent Contract
## 4. Frozen Route Decision Union Conformance and Calculator
## 5. Direct-Human Task-Creation Approval
## 6. Task Surface Closure at Admission
## 7. Existing-Task Wrapper and Runtime-Load Integration
## 8. Platform Capability Manifest and Enforcement Levels
## 9. Claude Code, Codex, and OpenCode Bindings
## 10. Discoverable Leaf and Route-Gated Catalog Projection
## 11. Golden Routing and Adapter Tests
## 12. Acceptance-Criteria Mapping and Downstream Freeze
```

- [ ] **Step 2: Freeze calculator/verifier behavior for the imported route branches**

Import the exact fields and forbidden cross-branch fields for `classify-only`, `execute-light`, and `create-integrated-task` from Task 1's frozen union digest without redefining them. Specify calculator/verifier behavior, policy replay limits, Task Intent signal ownership, task ID/ref/surface/challenge binding, one-time direct-human proof, and the rule that only `task admit` consumes the integrated Decision.

- [ ] **Step 3: Freeze platform wrapper behavior**

Specify that native-light consumes only a fresh `execute-light` Decision, while integrated wrappers call `task runtime load` and never replay the create Decision or open catalog paths directly. Define capability levels `enforced | instruction-only | unsupported`, strict default-platform admission, platform-specific native-light bindings, and bypass rejection.

- [ ] **Step 4: Map and verify**

Primary AC ownership is AC-02, AC-03, AC-22, AC-30, and AC-59. Task 1 owns the imported schemas and policy portions of AC-12, AC-13, AC-27, and AC-62; Task 4 owns the runtime-load/admission portions of AC-25 and AC-61. Task 5 supplies the adapter and routing integration evidence for all of those consumers.

Run:

```bash
rg -n "classify-only|execute-light|create-integrated-task|task runtime load|direct-human|enforced|instruction-only|AC-61|AC-62" docs/superpowers/specs/2026-07-13-agent-workflow-pack-route-adapters-design.md
git diff --check
```

Expected: every branch, approval binding, wrapper path, capability outcome, and mapped AC is present; no whitespace errors.

```bash
git add docs/superpowers/specs/2026-07-13-agent-workflow-pack-route-adapters-design.md
git commit -m "Add route and adapter feature spec"
```

Set the feature to `review-requested`. Apply findings through `changes-required` and `revised`, rerun the route/adapter checks, then set `Status: Approved` and commit the final feature-spec content as `C`. Compute the route/adapter interface digest from `C`, then create a later registry commit `R` recording `C + digest + interface-frozen`. Unlock Task 6 only after `R`; Task 6 records the same `C`, `R`, and digest when it consumes the interface.

---

### Task 6: Lifecycle, Packaging, and Release Feature Spec

**Files:**
- Create: `docs/superpowers/specs/2026-07-13-agent-workflow-pack-lifecycle-release-design.md`
- Consume: the exact `interface-frozen` digests exported by Tasks 1 through 5; path-only or status-only imports are invalid.

**Interfaces:**
- Consumes: every frozen subsystem interface, release trust policy, detached manifest schema, compatibility edges, domain error catalog, CLI diagnostic schema, and golden platform outputs. It composes CLI commands and output mappings only; it cannot redefine task commands, route semantics, ownership, or domain error meaning.
- Produces: complete lifecycle CLI composition, distribution build/release protocol, cross-distribution digest contract, compatibility and rollback flow, release gates, and end-to-end acceptance suite.

- [ ] **Step 1: Create the feature-spec skeleton**

```markdown
# Agent Workflow Pack Lifecycle, Packaging, and Release Design

**Status:** Draft — feature-spec review required
**Dependencies:** All five preceding Agent Workflow Pack feature specs approved

## 1. Scope and Integration Boundary
## 2. Lifecycle CLI Command Matrix
## 3. Structured Output, Errors, and Redaction
## 4. Detached Release Manifest and Immutable GitHub Trust Policy
## 5. Wheel, sdist, and Git-Checkout Release Identity
## 6. Self-Contained Wheel and Python Version Contract
## 7. Directed Compatibility Edges and Candidate Runtime
## 8. Upgrade, Supported Rollback, and Local-State Migration
## 9. Distribution Render Digest and Reproducibility
## 10. Release Gates, Licensing, and Provenance
## 11. End-to-End and Cross-Distribution Test Sequence
## 12. Acceptance-Criteria Closure
## 13. Production Implementation Entry Gate
```

- [ ] **Step 2: Freeze CLI and release supply-chain behavior**

Define the exact command matrix for bootstrap, init, sync, repair, upgrade, doctor, test-routing, recover, workspace commands, route decide, and task commands. Freeze exit categories, single-object JSON stdout, stderr diagnostics, redaction, trust-policy locator, detached-manifest verification, direct-wheel hash bootstrap, source commit/bundle agreement, and candidate runtime allowlist.

- [ ] **Step 3: Freeze packaging and compatibility gates**

Require the self-contained wheel, empty external runtime `Requires-Dist`, Python 3.11 through 3.14 CI, identical `distribution_render_digest` for wheel/sdist/Git checkout, no self-hash cycles, exact directed compatibility edges, source-static metadata verification without code execution, full SPDX provenance, and immutable-release publication.

- [ ] **Step 4: Close the complete acceptance matrix**

Use the frozen AC matrix near the start of this plan as the source of truth. The feature spec must import it without changing primary ownership, and its closure table must add the lifecycle/release scenario and release gate for every row. No AC may be unmapped, duplicated, or reassigned by Task 6; shared ACs must retain the single primary owner and list all integration consumers.

- [ ] **Step 5: Verify the six-spec graph**

Run:

```bash
rg -n "AC-[0-9][0-9]" docs/superpowers/specs/2026-07-13-agent-workflow-pack-*-design.md
rg -n "Release Identity|release-manifest.json|distribution_render_digest|Requires-Dist|Python 3.11|Python 3.14|compatibility" docs/superpowers/specs/2026-07-13-agent-workflow-pack-lifecycle-release-design.md
git diff --check
```

Run the structured AC/interface validator in the Plan Completion Gate as part of this step. Expected: AC-01 through AC-64 are all mapped exactly once with one primary owner; every imported interface points to an existing frozen digest; release identity, distribution, compatibility, Python, and provenance gates are explicit; no whitespace errors.

- [ ] **Step 6: Commit and stop at the implementation gate**

```bash
git add docs/superpowers/specs/2026-07-13-agent-workflow-pack-lifecycle-release-design.md
git commit -m "Add lifecycle and release feature spec"
```

Set the feature to `review-requested`. Apply findings through `changes-required` and `revised`, rerun the lifecycle/release checks, then set `Status: Approved` and commit the final feature-spec content as `C`. Compute the lifecycle interface digest from `C`, then create a later registry commit `R` recording `C + digest + interface-frozen`. Only after the imported-interface validator, AC matrix validator, and all six two-step freeze records pass may the decomposition phase enter the implementation-plan gate. Write one implementation plan per feature spec; do not combine the six subsystems and do not begin production code until the relevant per-feature plan is approved.

## Plan Completion Gate

The decomposition phase is complete only when:

- the frozen umbrella baseline commit is an ancestor of current `HEAD`, the umbrella bytes at current `HEAD` have SHA-256 `c2f23807cc36066b4b92478657cacaf15eb5cb6bd14e307e1e76f1c30de0284d`, and the umbrella path has no uncommitted change;
- all six files exist at the exact paths above;
- all six have status `Approved`;
- all six have an approved producer-content commit `C` plus a later registry commit `R` whose exported-interface rows contain `C`, `state=interface-frozen`, and exact 64-hex SHA-256 values;
- their dependency order matches the artifact map;
- every AC-01 through AC-64 has one primary owner and complete integration coverage;
- every cross-feature type, schema ID, digest domain, error code, and callable interface has exactly one definition;
- every imported interface names an existing frozen digest and passes the producer-ancestor and unlock-order checks;
- `rg -n "TB[D]|TO[D]O|FIXM[E]|implement late[r]|similar t[o]"` returns no feature-spec placeholders;
- `git diff --check` passes; and
- no production implementation file has changed during feature-spec decomposition.

### Structured matrix and interface validation

Run this from the repository root with `AWP_REGISTRY_MODE=partial` after every feature approval. Before the decomposition completion gate, set `AWP_REGISTRY_MODE=complete`; complete mode requires every expected interface and consumer import.

```bash
: "${AWP_REGISTRY_MODE:=partial}"
export AWP_REGISTRY_MODE
python3 - <<'PY'
from pathlib import Path
import os
import re
import subprocess

PLAN_PATH = "docs/superpowers/plans/2026-07-13-agent-workflow-pack-feature-spec-decomposition.md"
plan = Path(PLAN_PATH).read_text(encoding="utf-8")
rows = re.findall(r"^\| (AC-\d{2}) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|$", plan, re.MULTILINE)
ids = [int(ac[3:]) for ac, _, _, _ in rows]
assert ids == list(range(1, 65)), f"AC matrix must contain AC-01..AC-64 exactly once: {ids}"
assert len({ac for ac, _, _, _ in rows}) == 64
assert all(owner.strip() in {f"Task {n}" for n in range(1, 7)} for _, owner, _, _ in rows)
assert all(consumer.strip() and layer.strip() for _, _, consumer, layer in rows)

expected = {
    "core.schema-catalog.v1": ("task-1", "task-1", ("task-2", "task-3", "task-4", "task-5", "task-6"), "task-2"),
    "core.profile-resolution.v1": ("task-1", "task-1", ("task-3", "task-4", "task-5", "task-6"), "task-3"),
    "core.artifact-policy.v1": ("task-1", "task-1", ("task-3", "task-4", "task-5"), "task-3"),
    "core.surface-impact.v1": ("task-1", "task-1", ("task-3", "task-4", "task-5", "task-6"), "task-3"),
    "core.capability-manifest.v1": ("task-1", "task-5", ("task-5", "task-6"), "task-5"),
    "core.route-contract.v1": ("task-1", "task-5", ("task-4", "task-5", "task-6"), "task-4"),
    "core.saved-plan.v1": ("task-1", "task-3", ("task-3", "task-4", "task-6"), "task-3"),
    "core.task-snapshot.v1": ("task-1", "task-4", ("task-3", "task-4", "task-6"), "task-3"),
    "core.task-evaluators.v1": ("task-1", "task-1", ("task-3", "task-4", "task-6"), "task-3"),
    "core.workspace-diagnostics.v1": ("task-1", "task-4", ("task-4", "task-5", "task-6"), "task-4"),
    "providers.execution.v1": ("task-2", "task-2", ("task-3", "task-6"), "task-3"),
    "core.render-projection.v1": ("task-1", "task-3", ("task-3", "task-5", "task-6"), "task-3"),
    "renderer.reconcile.v1": ("task-3", "task-3", ("task-4", "task-6"), "task-4"),
    "runtime.task-state.v1": ("task-4", "task-4", ("task-5", "task-6"), "task-5"),
    "route.adapters.v1": ("task-5", "task-5", ("task-6",), "task-6"),
    "lifecycle.release.v1": ("task-6", "task-6", (), "release-ci"),
    "core.errors.v1": ("task-1", "task-1", ("task-2", "task-3", "task-4", "task-5", "task-6"), "task-2"),
    "providers.errors.v1": ("task-2", "task-2", ("task-3", "task-6"), "task-3"),
    "renderer.errors.v1": ("task-3", "task-3", ("task-4", "task-6"), "task-4"),
    "runtime.errors.v1": ("task-4", "task-4", ("task-5", "task-6"), "task-5"),
    "route.errors.v1": ("task-5", "task-5", ("task-6",), "task-6"),
    "lifecycle.cli-output.v1": ("task-6", "task-6", (), "release-ci"),
}
consumer_paths = {
    "task-1": "docs/superpowers/specs/2026-07-13-agent-workflow-pack-core-resolver-design.md",
    "task-2": "docs/superpowers/specs/2026-07-13-agent-workflow-pack-providers-cache-design.md",
    "task-3": "docs/superpowers/specs/2026-07-13-agent-workflow-pack-renderer-reconciler-design.md",
    "task-4": "docs/superpowers/specs/2026-07-13-agent-workflow-pack-runtime-task-state-design.md",
    "task-5": "docs/superpowers/specs/2026-07-13-agent-workflow-pack-route-adapters-design.md",
    "task-6": "docs/superpowers/specs/2026-07-13-agent-workflow-pack-lifecycle-release-design.md",
}
current_head = subprocess.run(
    ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
).stdout.strip()

ownership_section = plan.split("### Cross-feature contract ownership", 1)[1].split("`render_saved_plan`", 1)[0]
declared = {}
for line in ownership_section.splitlines():
    if not line.startswith("|") or line.startswith("|---") or "Freeze record" in line:
        continue
    cells = [cell.strip() for cell in line.strip("|").split("|")]
    if len(cells) != 5 or not re.fullmatch(r"`[^`]+`", cells[4]):
        continue
    interface_id = cells[4].strip("`")
    assert interface_id not in declared, f"duplicate ownership declaration: {interface_id}"
    declared[interface_id] = cells
assert set(declared) == set(expected), f"ownership/interface ID mismatch: {set(expected) ^ set(declared)}"
for interface_id, (definition_owner, implementation_owner, _, _) in expected.items():
    cells = declared[interface_id]
    assert cells[1] == f"Task {definition_owner[-1]}", (interface_id, cells[1])
    assert cells[2].startswith(f"Task {implementation_owner[-1]}"), (interface_id, cells[2])

def parse_tsv_block(text, start_marker, end_marker):
    segment = text.split(start_marker, 1)[1].split(end_marker, 1)[0]
    lines = [
        line for line in segment.splitlines()
        if line and not line.startswith(chr(96) * 3)
    ]
    header = lines[0].split("\t")
    return [dict(zip(header, line.split("\t"), strict=True)) for line in lines[1:]]

def require_commit(value, field):
    assert re.fullmatch(r"[0-9a-f]{40}", value), f"{field} must be 40 lowercase hex: {value}"
    subprocess.run(["git", "cat-file", "-e", f"{value}^{{commit}}"], check=True)

def is_ancestor(ancestor, descendant):
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        check=False,
    ).returncode == 0

registry_rows = parse_tsv_block(plan, "<!-- interface-registry:start -->", "<!-- interface-registry:end -->")
registry_ids = [row["interface_id"] for row in registry_rows]
assert len(registry_ids) == len(set(registry_ids)), f"duplicate interface IDs: {registry_ids}"
assert set(registry_ids) <= set(expected), f"unexpected interface IDs: {set(registry_ids) - set(expected)}"

registry = {}
for row in registry_rows:
    interface_id = row["interface_id"]
    definition_owner, implementation_owner, consumers, unlock = expected[interface_id]
    assert row["definition_owner"] == definition_owner
    assert row["implementation_owner"] == implementation_owner
    require_commit(row["producer_content_commit"], "producer_content_commit")
    assert is_ancestor(row["producer_content_commit"], current_head)
    assert re.fullmatch(r"[0-9a-f]{64}", row["exported_interface_digest"])
    assert row["state"] == "interface-frozen"
    assert row["imported_by"] == (",".join(consumers) if consumers else "none")
    assert row["required_before_unlock"] == unlock
    registry[interface_id] = row

mode = os.environ["AWP_REGISTRY_MODE"]
assert mode in {"partial", "complete"}
if mode == "complete":
    assert set(registry) == set(expected), f"missing interface IDs: {set(expected) - set(registry)}"

import_rows = parse_tsv_block(plan, "<!-- consumer-imports:start -->", "<!-- consumer-imports:end -->")
import_keys = [(row["consumer_task"], row["interface_id"]) for row in import_rows]
assert len(import_keys) == len(set(import_keys)), f"duplicate consumer imports: {import_keys}"

for row in import_rows:
    interface_id = row["interface_id"]
    assert interface_id in registry, f"import references unfrozen interface: {interface_id}"
    producer = registry[interface_id]
    assert row["consumer_task"] in expected[interface_id][2]
    require_commit(row["consumer_content_commit"], "consumer_content_commit")
    require_commit(row["producer_content_commit"], "producer_content_commit")
    require_commit(row["registry_commit"], "registry_commit")
    assert row["producer_content_commit"] == producer["producer_content_commit"]
    assert row["imported_interface_digest"] == producer["exported_interface_digest"]
    assert is_ancestor(row["producer_content_commit"], row["consumer_content_commit"])
    assert is_ancestor(row["registry_commit"], row["consumer_content_commit"])
    assert is_ancestor(row["consumer_content_commit"], current_head)

    consumer_spec = subprocess.run(
        ["git", "show", f"{row['consumer_content_commit']}:{consumer_paths[row['consumer_task']]}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert row["producer_content_commit"] in consumer_spec
    assert row["registry_commit"] in consumer_spec
    assert row["imported_interface_digest"] in consumer_spec

    registry_text = subprocess.run(
        ["git", "show", f"{row['registry_commit']}:{PLAN_PATH}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    registry_at_r = {
        item["interface_id"]: item
        for item in parse_tsv_block(registry_text, "<!-- interface-registry:start -->", "<!-- interface-registry:end -->")
    }
    assert interface_id in registry_at_r
    assert registry_at_r[interface_id]["producer_content_commit"] == row["producer_content_commit"]
    assert registry_at_r[interface_id]["exported_interface_digest"] == row["imported_interface_digest"]

if mode == "complete":
    expected_imports = {
        (consumer, interface_id)
        for interface_id, (_, _, consumers, _) in expected.items()
        for consumer in consumers
    }
    assert set(import_keys) == expected_imports, f"missing imports: {expected_imports - set(import_keys)}"

print(
    f"validated {len(rows)} AC rows, {len(registry_rows)} frozen interfaces, "
    f"and {len(import_rows)} consumer imports in {mode} mode"
)
PY
```

The validator performs the Git ancestry and registry-snapshot checks itself. Partial mode permits only a valid subset while feature specs are being approved; complete mode requires all expected interface IDs and all required consumer imports. A missing or symbolic digest is a hard failure, not a warning. Keyword searches remain auxiliary evidence only.

# Agent Workflow Pack Feature-Spec Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce and approve six implementation-ready feature specifications from the approved Agent Workflow Pack v0.1 umbrella design before any production code is written.

**Architecture:** The approved umbrella design remains the sole cross-feature authority. Each feature spec owns one bounded subsystem, freezes its schemas and callable interfaces, maps its acceptance criteria, and exposes only the contracts needed by later specs. Work proceeds in the exact Section 31 order so later specs consume reviewed interfaces instead of inventing parallel planners, writers, loaders, or trust roots.

**Tech Stack:** Markdown design specifications, RFC 8785 JCS and SHA-256 contract notation, JSON/YAML schema contracts, Python `>=3.11,<3.15`, self-contained wheel packaging, WSL2/Linux filesystem semantics, pytest-based future verification.

## Global Constraints

- The umbrella authority is `docs/superpowers/specs/2026-07-13-agent-workflow-pack-design.md` at status `Approved`.
- This plan creates documentation only. Do not create or modify `src/`, `tests/`, `schemas/`, package metadata, runtime artifacts, or generated project files.
- Each feature spec must be approved before its implementation plan or production implementation begins.
- Feature specs must preserve the sole Resolver, Reconciler, route-policy source, Task-state Service, release trust root, ownership source, and task-state authority defined by the umbrella design.
- Runtime Python support is exactly `>=3.11,<3.15`; the published wheel has no external runtime `Requires-Dist` dependencies.
- v0.1 targets WSL2 and Linux only and fails closed when required lock, atomic-replace, mode, or path-collision semantics are unavailable.
- Every structured digest uses a named domain, RFC 8785 JCS, and SHA-256; every dependency graph must be acyclic.
- Every schema is closed and versioned. Unknown fields, duplicate YAML keys, unsupported versions, ambiguous ownership, and unclassified runtime-visible units fail closed.
- No feature spec may weaken protected paths, capability requirements, direct-human approval, supply-chain verification, CAS preconditions, transaction recovery, or checkout-local scope disclosures.
- Feature specs may clarify an umbrella contract but may not silently change product scope. A contradiction requires an explicit umbrella-spec erratum and renewed approval.

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
- Produces: frozen schema catalog and naming convention; canonicalization and digest APIs; runtime-surface registry/inventory and coverage contract; `Desired State IR`; `candidate_impact`; fixed workspace-state evaluator; operation-specific task gate; saved-plan envelope; structured diagnostics consumed by Tasks 2 through 6.

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

Use the naming rule `agent-workflow.<domain>.v1` for schema/digest domains and enumerate every domain owned by this feature. Include exact canonical projections and exclusions for Release Identity, Trellis layout, surface registry, surface digest, task contract, task quiescence, local-state contract, plan core, journal binding, candidate Manifest, final plan, workspace diagnostic, and candidate impact. Include two explicit acyclic graphs:

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

Define closed input/output fields, deterministic ordering, stable IDs, error precedence, and which downstream feature owns each caller. Preserve `contract_before_digest`, `observed_before_digest`, and `after_digest` as separate fields.

- [ ] **Step 4: Add full coverage and failure-case matrices**

Include tables proving:

- every packaged or rendered runtime-visible unit has exactly one canonical owning surface;
- `runtime-control-plane` and `surface-registry` are mandatory task surfaces;
- unowned, multiply owned, cyclic, dangling, omitted, or unclassified units block resolution;
- heavy contract change is exactly a nonempty authority vector or `change_kind: contract-change`;
- restorative repair requires an empty authority vector and `contract_before_digest == after_digest`;
- workspace task-quiescence is command-independent while command admission is operation-specific.

- [ ] **Step 5: Verify the feature spec**

Run:

```bash
rg -n "^## " docs/superpowers/specs/2026-07-13-agent-workflow-pack-core-resolver-design.md
rg -n "agent-workflow\.|resolve\(|compute_candidate_impact|scan_task_quiescence|evaluate_workspace_state_quiescence|evaluate_task_gate|AC-" docs/superpowers/specs/2026-07-13-agent-workflow-pack-core-resolver-design.md
git diff --check
```

Expected: all 13 sections exist; every listed interface and acceptance-criteria mapping is present; `git diff --check` prints nothing.

- [ ] **Step 6: Commit the reviewed draft**

```bash
git add docs/superpowers/specs/2026-07-13-agent-workflow-pack-core-resolver-design.md
git commit -m "Add core resolver feature spec"
```

Stop for feature-spec review and approval before Task 2.

---

### Task 2: Providers and Secure Cache Feature Spec

**Files:**
- Create: `docs/superpowers/specs/2026-07-13-agent-workflow-pack-providers-cache-design.md`
- Consume: `docs/superpowers/specs/2026-07-13-agent-workflow-pack-core-resolver-design.md`

**Interfaces:**
- Consumes: frozen lock, digest, Release Identity, provider-plan, diagnostic, and candidate-output contracts from Task 1.
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

Copy the umbrella requirements for fixed locale/timezone/environment, no ambient clock/random/hostname/user/path input, bounded output, exact command vector, provider security levels `required | approval-required | best-effort`, and repeated-output content-root verification. Map AC-15, AC-28, AC-40, AC-44, AC-45, and AC-49.

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

Stop for feature-spec review and approval before Task 3.

---

### Task 3: Renderer and Reconciler Feature Spec

**Files:**
- Create: `docs/superpowers/specs/2026-07-13-agent-workflow-pack-renderer-reconciler-design.md`
- Consume: Tasks 1 and 2 feature specs.

**Interfaces:**
- Consumes: `DesiredStateIR`, artifact definitions, verified provider outputs, candidate impact, saved-plan envelope, file-state preconditions.
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

Define the exact lifecycle transaction phase table, immutable journal header, mutable fields, `journal_binding_digest`, maintenance binding, Manifest-last commit, created-directory cleanup, backup rules, and CAS comparisons over type, bytes, mode, and symlink status. State that hooks, network effects, and Git auto-commit are outside rollback phases.

- [ ] **Step 3: Freeze ownership and restorative repair behavior**

Define whole-file managed, marked-block overlay, adopted baseline, create-once-then-user-owned, and user-owned behavior. Specify repair records with current contract, observed state, candidate state, approval, active-task evaluation, and CAS. Map AC-04 through AC-10, AC-19, AC-20, AC-26, AC-35 through AC-39, AC-41, AC-56, and AC-63.

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

Stop for feature-spec review and approval before Task 4.

---

### Task 4: Runtime Launcher and Task-State Service Feature Spec

**Files:**
- Create: `docs/superpowers/specs/2026-07-13-agent-workflow-pack-runtime-task-state-design.md`
- Consume: Tasks 1 through 3 feature specs.

**Interfaces:**
- Consumes: release/runtime descriptor schemas, workspace diagnostics, task snapshot/evaluators, Reconciler recovery state, surface registry and observed digest recipe.
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

Cover AC-11, AC-21, AC-23 through AC-27, AC-31 through AC-33, AC-36 through AC-39, AC-42, AC-43, AC-46 through AC-48, AC-52 through AC-58, AC-61, and AC-64. Include crash points for registration, workspace migration, admission, archive, replay reservation, runtime-load races, and maintenance.

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

Stop for feature-spec review and approval before Task 5.

---

### Task 5: Route Admission and Platform Adapters Feature Spec

**Files:**
- Create: `docs/superpowers/specs/2026-07-13-agent-workflow-pack-route-adapters-design.md`
- Consume: Tasks 1 and 4 feature specs plus approved platform capability contracts.

**Interfaces:**
- Consumes: compiled policy, stable signal IDs, task intent, runtime-surface closure, Task-state Service commands, runtime-load API, capability reports.
- Produces: closed Route Decision union, direct-human task approval verifier, platform bindings, generated wrappers, discoverable-leaf projection, adapter golden contracts used by Task 6.

- [ ] **Step 1: Create the feature-spec skeleton**

```markdown
# Agent Workflow Pack Route Admission and Platform Adapters Design

**Status:** Draft — feature-spec review required
**Dependencies:** Approved Core Resolver and Runtime Task-State feature specs

## 1. Scope and Routing Ownership
## 2. Stable Signals and Compiled Heavy Policy
## 3. Task Intent Contract
## 4. Closed Route Decision Union
## 5. Direct-Human Task-Creation Approval
## 6. Task Surface Closure at Admission
## 7. Existing-Task Wrapper and Runtime-Load Integration
## 8. Platform Capability Manifest and Enforcement Levels
## 9. Claude Code, Codex, and OpenCode Bindings
## 10. Discoverable Leaf and Route-Gated Catalog Projection
## 11. Golden Routing and Adapter Tests
## 12. Acceptance-Criteria Mapping and Downstream Freeze
```

- [ ] **Step 2: Freeze route and approval branches**

Define exact fields and forbidden cross-branch fields for `classify-only`, `execute-light`, and `create-integrated-task`. Specify policy replay limits, Task Intent signal ownership, task ID/ref/surface/challenge binding, one-time direct-human proof, and the rule that only `task admit` consumes the integrated Decision.

- [ ] **Step 3: Freeze platform wrapper behavior**

Specify that native-light consumes only a fresh `execute-light` Decision, while integrated wrappers call `task runtime load` and never replay the create Decision or open catalog paths directly. Define capability levels `enforced | instruction-only | unsupported`, strict default-platform admission, platform-specific native-light bindings, and bypass rejection.

- [ ] **Step 4: Map and verify**

Map AC-02, AC-03, AC-12, AC-13, AC-22, AC-25, AC-27, AC-30, AC-59, AC-61, and AC-62.

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

Stop for feature-spec review and approval before Task 6.

---

### Task 6: Lifecycle, Packaging, and Release Feature Spec

**Files:**
- Create: `docs/superpowers/specs/2026-07-13-agent-workflow-pack-lifecycle-release-design.md`
- Consume: Tasks 1 through 5 approved feature specs.

**Interfaces:**
- Consumes: every frozen subsystem interface, release trust policy, detached manifest schema, compatibility edges, CLI diagnostics, golden platform outputs.
- Produces: complete lifecycle CLI behavior, distribution build/release protocol, cross-distribution digest contract, compatibility and rollback flow, release gates, and end-to-end acceptance suite.

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

Create a table with one row for every AC-01 through AC-64. Each row must identify the owning feature spec, the lifecycle/release integration scenario, the future test layer, and the release gate. No AC may be unmapped; shared ACs must name one primary owner and all integration consumers.

- [ ] **Step 5: Verify the six-spec graph**

Run:

```bash
rg -n "AC-[0-9][0-9]" docs/superpowers/specs/2026-07-13-agent-workflow-pack-*-design.md
rg -n "Release Identity|release-manifest.json|distribution_render_digest|Requires-Dist|Python 3.11|Python 3.14|compatibility" docs/superpowers/specs/2026-07-13-agent-workflow-pack-lifecycle-release-design.md
git diff --check
```

Expected: AC-01 through AC-64 are all mapped; release identity, distribution, compatibility, Python, and provenance gates are explicit; no whitespace errors.

- [ ] **Step 6: Commit and stop at the implementation gate**

```bash
git add docs/superpowers/specs/2026-07-13-agent-workflow-pack-lifecycle-release-design.md
git commit -m "Add lifecycle and release feature spec"
```

After all six feature specs are individually approved, write one implementation plan per feature spec. Do not combine the six subsystems into a single implementation plan, and do not begin production code until the relevant per-feature plan is approved.

## Plan Completion Gate

The decomposition phase is complete only when:

- all six files exist at the exact paths above;
- all six have status `Approved`;
- their dependency order matches the artifact map;
- every AC-01 through AC-64 has one primary owner and complete integration coverage;
- every cross-feature type, schema ID, digest domain, error code, and callable interface has exactly one definition;
- `rg -n "TB[D]|TO[D]O|FIXM[E]|implement late[r]|similar t[o]"` returns no feature-spec placeholders;
- `git diff --check` passes; and
- no production implementation file has changed during feature-spec decomposition.

# Agent Workflow Pack Renderer and Reconciler Implementation Plan

**Status:** Draft — implementation-plan review required

> **Execution contract:** Execute under the current route/integration contract. heavy-development-router is the only heavy top-level orchestrator. Track all steps with checkboxes.

**Goal:** Implement deterministic render staging, ownership planning, saved-plan construction, OS locks, filesystem probes, byte-and-mode CAS, Manifest-last transactions, restorative repair, rollback, and recovery.

**Architecture:** agent_stack.reconcile separates pure render/plan code from filesystem execution. Every mutation is represented by a typed FileState and journal record before apply. The Manifest atomic rename is the lifecycle commit point; before it recovery can resume or CAS-rollback, after it recovery cleans forward only.

**Tech Stack:** Python 3.11-3.14, frozen Core and Provider APIs, stdlib filesystem/locking primitives, pytest/Hypothesis, multiprocessing crash harnesses.

## Global Constraints

- Source: docs/superpowers/specs/2026-07-13-agent-workflow-pack-renderer-reconciler-design.md, producer C caa40221183cac41b381702d2669d4fcd5d5c5b4.
- Prerequisites: Core and Providers are integration-complete and Lifecycle Tasks 1-3 have reached release-kernel component-complete. Renderer does not consume Route or Runtime implementations during its component phase.
- Task 3 is sole lifecycle writer for pack-managed/overlay-managed targets.
- It never mutates ordinary task outbox or integrated task state.
- Planning/dry-run/ordinary doctor perform zero target writes.
- Pre-commit operations are journaled reversible file operations only.
- Manifest rename is the commit point.
- Every behavior-changing task uses strict TDD.
- No implementation until this plan is approved.

## Cross-Plan Execution DAG and Completion States

The six plans execute in this fixed order:

1. Core, including the frozen runtime-vendor lock, reaches integration-complete.
2. Providers reaches integration-complete without adding dependencies.
3. Lifecycle Tasks 1-3 implement the release kernel and stop at release-kernel component-complete.
4. Renderer Tasks 1-7 run against a contract fake for Core's frozen `scan_task_quiescence(VerifiedTrellisTaskLayout, VerifiedTrellisTaskLayout, VerifiedDiscoverySchemas, VerifiedDiscoverySchemas) -> TaskSnapshotAndFindings` signature and reach Renderer component-complete.
5. Runtime Tasks 1-8 consume the real release kernel and frozen Route ports; Runtime Task 4 binds the real scanner to Renderer, making Renderer integration-complete. Runtime remains component-complete while Route ports are faked.
6. Route Tasks 1-8 bind the real Decision/approval verifiers into Runtime, making Route and Runtime integration-complete.
7. Lifecycle Tasks 4-9 run only after the real Renderer, Runtime, and Route bindings pass, then establish system integration-complete.

`component-complete` means the feature's own contract/unit/property/crash tests pass with only frozen-port fakes. It does not satisfy downstream integration or release gates. `integration-complete` means every fake at a cross-feature port has been replaced by its real implementation and the named cross-module tests pass. Every fake is test-only; production composition must fail if a required port is absent.

## File Structure

~~~text
src/agent_stack/reconcile/
  __init__.py
  api.py
  models.py
  render.py
  staging.py
  ownership.py
  plan.py
  ports.py
  locks.py
  probes.py
  cas.py
  journal.py
  maintenance.py
  apply.py
  repair.py
  recovery.py
  manifest.py
  errors.py
schemas/reconcile/
tests/unit/reconcile/
tests/contracts/reconcile/
tests/property/reconcile/
tests/integration/reconcile/
tests/concurrency/reconcile/
tests/fixtures/reconcile/
~~~

---

### Task 1: Define FileState, staged records, journals, errors, and public API

**Files:**
- Create: src/agent_stack/reconcile/models.py
- Create: src/agent_stack/reconcile/errors.py
- Create: src/agent_stack/reconcile/api.py
- Create: src/agent_stack/reconcile/ports.py
- Create: schemas/reconcile/staged-file.v1.json
- Create: schemas/reconcile/file-state.v1.json
- Create: schemas/reconcile/lifecycle-transaction.v1.json
- Test: tests/contracts/reconcile/test_reconcile_api.py
- Test: tests/contracts/reconcile/test_journal_schema.py
- Test: tests/contracts/reconcile/test_task_scanner_port.py

**Interfaces:**
- Produces: render(), plan_reconcile(), apply_plan(), recover_transaction(), FileState, LifecycleJournal, and `TaskQuiescenceScannerPort` with the exact Core-frozen scanner signature.
- Consumes: Core IR/SavedPlan/OwnershipDecision and ProviderExecutionResult.

- [ ] **Step 1: RED schema/API tests**

Test one object binds path/existence/type/hash/mode/non-symlink; journal immutable/mutable field separation; public signatures exactly match frozen interface. Test that `TaskQuiescenceScannerPort` accepts and returns only the Core-frozen types/signature, a contract fake records both calls, and no Runtime module is imported.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/contracts/reconcile/test_reconcile_api.py tests/contracts/reconcile/test_journal_schema.py tests/contracts/reconcile/test_task_scanner_port.py -q`
Expected: FAIL because package is absent.

- [ ] **Step 3: Add immutable models and API stubs**

Implement closed enums/dataclasses, schema loading, and the injected scanner Protocol. No filesystem behavior, Runtime import, or production fake yet.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/contracts/reconcile/test_reconcile_api.py tests/contracts/reconcile/test_journal_schema.py tests/contracts/reconcile/test_task_scanner_port.py -q && uv run ruff check src/agent_stack/reconcile tests/contracts/reconcile && uv run mypy src/agent_stack/reconcile`
Expected: pass.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/reconcile schemas/reconcile tests/contracts/reconcile
git commit -m "Define reconciler transaction contracts"
~~~

### Task 2: Implement deterministic renderer and staged tree

**Files:**
- Create: src/agent_stack/reconcile/render.py
- Create: src/agent_stack/reconcile/staging.py
- Test: tests/unit/reconcile/test_render.py
- Test: tests/property/reconcile/test_render_determinism.py
- Fixtures: tests/fixtures/reconcile/render_units/

**Interfaces:**
- Produces: render(ir, verified_provider_results) -> StagedRenderTree.
- Consumes: Core RenderUnit/DesiredStateIR and verified provider outputs.

- [ ] **Step 1: RED tests**

Cover stable path ordering, UTF-8/newlines, fixed locale/timezone, substitutions, validators, exact modes, overlay blocks, provider content root, repeated independent staging roots, and release substitutions excluded from launcher_bundle_digest but included in render/applied/distribution digests.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/unit/reconcile/test_render.py tests/property/reconcile/test_render_determinism.py -q`
Expected: FAIL on missing renderer.

- [ ] **Step 3: Implement pure candidate generation**

Renderer reads no target state and performs no provider/network operation. Stage outside target or in transaction-private same-filesystem area only after apply begins.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/unit/reconcile/test_render.py tests/property/reconcile/test_render_determinism.py -q && uv run pytest tests/unit/reconcile/test_render.py tests/property/reconcile/test_render_determinism.py -q`
Expected: identical staged content roots.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/reconcile/render.py src/agent_stack/reconcile/staging.py tests
git commit -m "Render deterministic staged artifacts"
~~~

### Task 3: Implement ownership observation and SavedPlan construction

**Files:**
- Create: src/agent_stack/reconcile/ownership.py
- Create: src/agent_stack/reconcile/plan.py
- Create: schemas/reconcile/ownership-observation.v1.json
- Test: tests/unit/reconcile/test_ownership.py
- Test: tests/unit/reconcile/test_plan.py
- Test: tests/property/reconcile/test_plan_dag.py

**Interfaces:**
- Produces: plan_reconcile() and exact OwnershipDecision/FileState preconditions.
- Consumes: staged tree, current Manifest/ObservedTargetState, Core evaluators and render_saved_plan.

- [ ] **Step 1: RED tests**

Test managed, overlay-managed, adopted, create-once, user-owned, enrollment without rewrite, retirement, marker corruption, full plan branch rules, task snapshot/evaluator binding, and acyclic plan digest DAG.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/unit/reconcile/test_ownership.py tests/unit/reconcile/test_plan.py tests/property/reconcile/test_plan_dag.py -q`
Expected: FAIL on missing planner.

- [ ] **Step 3: Implement minimal planner**

Emit no write plan when any blocker exists. A true no-op sync has no candidate change and no transaction.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/unit/reconcile/test_ownership.py tests/unit/reconcile/test_plan.py tests/property/reconcile/test_plan_dag.py -q`
Expected: all ownership actions and plan digests match fixtures.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/reconcile/ownership.py src/agent_stack/reconcile/plan.py schemas/reconcile tests
git commit -m "Plan ownership-safe reconciliations"
~~~

### Task 4: Implement OS locks, filesystem probes, and byte-and-mode CAS

**Files:**
- Create: src/agent_stack/reconcile/locks.py
- Create: src/agent_stack/reconcile/probes.py
- Create: src/agent_stack/reconcile/cas.py
- Test: tests/integration/reconcile/test_probes.py
- Test: tests/concurrency/reconcile/test_locks.py
- Test: tests/concurrency/reconcile/test_cas.py

**Interfaces:**
- Produces: bootstrap/project lock contexts, runtime-state gate acquisition, probe evidence, compare_and_swap().
- Consumes: FileState and target identity.

- [ ] **Step 1: RED tests**

Test bootstrap-to-project handoff, fixed lock order, two processes, symlink refusal, same-filesystem rename, POSIX mode, case/Unicode collision, /mnt behavior, network/cross-device refusal, bytes/type/mode CAS, and probe residue recovery.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/integration/reconcile/test_probes.py tests/concurrency/reconcile/test_locks.py tests/concurrency/reconcile/test_cas.py -q`
Expected: FAIL on absent lock/probe/CAS code.

- [ ] **Step 3: Implement Linux/WSL mutation prerequisites**

Use live OS locks, nonce probe paths, recorded original absence, exact CAS cleanup, and no path-based safety assumptions.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/integration/reconcile/test_probes.py tests/concurrency/reconcile/test_locks.py tests/concurrency/reconcile/test_cas.py -q`
Expected: native-temp and available WSL-mounted fixtures pass; unsafe or indeterminate cases block.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/reconcile/locks.py src/agent_stack/reconcile/probes.py src/agent_stack/reconcile/cas.py tests
git commit -m "Add reconciler locks probes and CAS"
~~~

### Task 5: Implement journal, maintenance, Manifest-last apply

**Files:**
- Create: src/agent_stack/reconcile/journal.py
- Create: src/agent_stack/reconcile/maintenance.py
- Create: src/agent_stack/reconcile/manifest.py
- Create: src/agent_stack/reconcile/apply.py
- Test: tests/integration/reconcile/test_apply.py
- Test: tests/concurrency/reconcile/test_apply_killpoints.py
- Test: tests/contracts/reconcile/test_maintenance_binding.py

**Interfaces:**
- Produces: apply_plan(saved_plan, approval) -> ReconcileResult.
- Consumes: locks/probes/CAS, staged candidates, and injected `TaskQuiescenceScannerPort`. Component tests use a contract fake; production composition later binds Task 4's real scanner.

- [ ] **Step 1: RED transaction tests**

Inject termination at planned, probing, prepared, applying, files_applied, immediately around Manifest rename, manifest_committed, cleanup. Assert journal_binding_digest ignores mutable phase but matches marker/Manifest; the contract scanner fake is called for planning evidence and immediately before Manifest rename; a changed second snapshot is `AWP_TASK_QUIESCENCE_CHANGED`.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/integration/reconcile/test_apply.py tests/concurrency/reconcile/test_apply_killpoints.py tests/contracts/reconcile/test_maintenance_binding.py -q`
Expected: FAIL on missing transaction engine.

- [ ] **Step 3: Implement phase machine**

Write immutable journal before maintenance, probe before authoritative apply, apply workflow lock/artifacts/local candidates before Manifest, invoke the injected scanner port immediately before Manifest, and atomically rename Manifest last. Do not import Runtime or ship a fallback scanner.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/integration/reconcile/test_apply.py tests/concurrency/reconcile/test_apply_killpoints.py tests/contracts/reconcile/test_maintenance_binding.py -q`
Expected: every kill point has one recognized pre/post-commit outcome and scanner-fake evidence proves the required double observation. This establishes Task 5 component GREEN only.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/reconcile/journal.py src/agent_stack/reconcile/maintenance.py src/agent_stack/reconcile/manifest.py src/agent_stack/reconcile/apply.py tests
git commit -m "Apply reconciliations with Manifest-last transactions"
~~~

### Task 6: Implement restorative repair

**Files:**
- Create: src/agent_stack/reconcile/repair.py
- Test: tests/unit/reconcile/test_repair.py
- Test: tests/integration/reconcile/test_repair_apply.py

**Interfaces:**
- Produces: validate_repair_selection(), stage_restorative_repair().
- Consumes: Core CandidateImpact repair records and CAS.

- [ ] **Step 1: RED tests**

Test contract_before == after, observed drift/null, empty authority vector, unchanged registry graph, task pinned equality, repair-to-different digest, mode drift, and runtime load blocked until commit.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/unit/reconcile/test_repair.py tests/integration/reconcile/test_repair_apply.py -q`
Expected: FAIL on missing repair module.

- [ ] **Step 3: Implement repair branch only**

Never reinterpret drift as ordinary sync or upgrade. Preserve task revision/surface contract.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/unit/reconcile/test_repair.py tests/integration/reconcile/test_repair_apply.py tests/unit/core/test_task_policy.py -q`
Expected: restorative cases pass; contract changes block.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/reconcile/repair.py tests/unit/reconcile/test_repair.py tests/integration/reconcile/test_repair_apply.py
git commit -m "Add CAS-protected restorative repair"
~~~

### Task 7: Implement rollback and forward recovery

**Files:**
- Create: src/agent_stack/reconcile/recovery.py
- Modify: src/agent_stack/reconcile/api.py
- Test: tests/integration/reconcile/test_recovery.py
- Test: tests/concurrency/reconcile/test_recovery_external_changes.py

**Interfaces:**
- Produces: recover_transaction(journal, resume_or_rollback).
- Consumes: journal phases, backups, FileState CAS, Manifest commit recognition.

- [ ] **Step 1: RED tests**

Cover planned/probing/prepared/applying/files_applied resume and rollback; manifest_committed cleanup only; candidate/original/third-state rollback; created-directory cleanup; missing mutable journal update with committed Manifest; orphan marker safety.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/integration/reconcile/test_recovery.py tests/concurrency/reconcile/test_recovery_external_changes.py -q`
Expected: FAIL on missing recovery.

- [ ] **Step 3: Implement phase-specific recovery**

Never guess resume vs rollback. Restore only exact candidate states; remove only recorded empty created directories. A committed transaction is never rolled back.

- [ ] **Step 4: Verify GREEN and full Renderer component suite**

Run: `uv run pytest tests/unit/reconcile tests/contracts/reconcile tests/property/reconcile tests/integration/reconcile tests/concurrency/reconcile -q && uv run ruff check src/agent_stack/reconcile tests && uv run mypy src/agent_stack/reconcile`
Expected: pass.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/reconcile/recovery.py src/agent_stack/reconcile/api.py tests
git commit -m "Recover reconciler transactions safely"
~~~

## Renderer Integration-Complete Gate

Renderer is only `component-complete` after Task 7. Runtime Task 4 owns `tests/integration/runtime/test_reconciler_scanner_binding.py`, which binds the real `agent_stack.runtime.scanner.scan_task_quiescence` implementation to `TaskQuiescenceScannerPort`. That test must prove exact argument/return types, the planning/commit-time double scan, byte-for-byte snapshot comparison, `AWP_TASK_QUIESCENCE_CHANGED` on external change, lock ordering, and absence of a production fake.

Run after Runtime Task 4: `uv run pytest tests/integration/runtime/test_reconciler_scanner_binding.py tests/integration/reconcile/test_apply.py tests/concurrency/reconcile/test_apply_killpoints.py -q`

Expected: PASS with the real Runtime scanner. Only then is Renderer `integration-complete`; Lifecycle Tasks 4-9 remain locked before this gate.

## Global Validation

For component-complete, run the full Renderer suite with the scanner contract fake and kill points twice. Assert ordinary doctor/planning/dry-run write zero files and verify no Task-state paths are mutated except exact compatibility migration fixtures. For integration-complete, additionally run the real-scanner binding gate above. Run uv build only as a component packaging smoke check; it is not a final release artifact.

## Implementation Constraint Prompt

~~~text
Read the approved Renderer/Reconciler spec and this plan. Stop on conflict with Core/Provider frozen APIs. Use strict TDD and observe RED before every behavior change. Keep pure rendering/planning separate from filesystem mutation. Use only the injected Core-frozen scanner port during component work; do not import Runtime or ship a fake. Do not create task-state semantics, route behavior, provider execution, or release policy. Manifest rename is the only lifecycle commit point. Report component-complete after the fake-port suite and integration-complete only after Runtime Task 4's real-scanner binding gate passes. Run all ownership, probe, CAS, crash, repair, and recovery suites before completion.
~~~

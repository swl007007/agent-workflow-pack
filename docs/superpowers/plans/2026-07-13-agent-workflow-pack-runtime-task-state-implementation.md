# Agent Workflow Pack Runtime Launcher and Task-State Implementation Plan

**Status:** Draft — implementation-plan review required

> **Execution contract:** Execute only through the current route/integration contract. In heavy mode, heavy-development-router is the sole top-level orchestrator. Track each step below.

**Goal:** Implement the single-file project launcher, clean uv bootstrap and caller context, runtime allowlist, workspace registration/migration, normative Trellis scanner, integration/task transactions, approval replay/outbox, and existing-task runtime-load dispatch.

**Architecture:** A small POSIX launcher starts one hash-pinned wheel. The Python runtime verifies all authorities before command dispatch. Runtime/task-state modules share one runtime-state gate and closed journals; scanners return facts, imported Core evaluators decide policy, and runtime load constructs one immutable in-memory bundle.

**Tech Stack:** POSIX sh, uv/uvx, Python 3.11-3.14, frozen Core/Reconciler/Route schemas, pytest/Hypothesis, multiprocessing/SIGKILL harnesses.

## Global Constraints

- Source: docs/superpowers/specs/2026-07-13-agent-workflow-pack-runtime-task-state-design.md, producer C 0bc82617df4ea6f09b59c827ab925faf36904b49.
- Prerequisites: Core, Providers, and Renderer/Reconciler implementations complete.
- Launcher is sole pre-wheel authority; descriptor is post-wheel validation only.
- Bootstrap may download only the exact hash-bound wheel and never Python/secondary packages.
- Workspace migration never edits or resumes Trellis task state.
- Task identity is immutable UUID; refs may be reused only after archive with a new UUID.
- Existing-task load never requires the stale create Decision.
- Task-state Service ordinary writes are limited to its frozen authority paths.
- Strict TDD for behavior changes; no production implementation until plan approval.

## File Structure

~~~text
runtime-launcher/
  agent-stack.sh.tmpl
schemas/runtime/
src/agent_stack/runtime/
  __init__.py
  api.py
  bootstrap.py
  caller_context.py
  authority.py
  maintenance.py
  workspace.py
  scanner.py
  integration.py
  replay.py
  outbox.py
  task_journal.py
  task_service.py
  runtime_load.py
  recovery.py
  errors.py
tests/unit/runtime/
tests/contracts/runtime/
tests/property/runtime/
tests/integration/runtime/
tests/concurrency/runtime/
tests/e2e/runtime/
tests/fixtures/runtime/
~~~

---

### Task 1: Implement launcher template and bootstrap contract tests

**Files:**
- Create: runtime-launcher/agent-stack.sh.tmpl
- Create: src/agent_stack/runtime/bootstrap.py
- Create: schemas/runtime/runtime-control.v1.json
- Create: tests/contracts/runtime/test_launcher_template.py
- Create: tests/e2e/runtime/test_launcher_bootstrap.py

**Interfaces:**
- Produces: bootstrap_project_runtime(), rendered launcher constants/argv.
- Consumes: Task 6-supplied verified release substitutions at render time.

- [ ] **Step 1: RED launcher tests**

Run launcher under fake uv/Python with malicious UV_INDEX, uv.toml, .env, global agent-stack, no Python, cold cache, offline miss, redirect/hash failure. Assert exact env -i and argv, no descriptor precheck, no secondary download.

- [ ] **Step 2: Verify RED**

Run: uv run pytest tests/contracts/runtime/test_launcher_template.py tests/e2e/runtime/test_launcher_bootstrap.py -q
Expected: FAIL because launcher/template/bootstrap code is absent.

- [ ] **Step 3: Implement minimum POSIX launcher**

Resolve non-symlink self/root, absolute supported uv/Python, capture only reserved caller fields, clear environment, and exec fixed direct-wheel command.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/contracts/runtime/test_launcher_template.py tests/e2e/runtime/test_launcher_bootstrap.py -q`
Expected: on Linux/WSL, the exact wheel starts or the launcher fails before Python code.

- [ ] **Step 5: Commit**

~~~bash
git add runtime-launcher src/agent_stack/runtime/bootstrap.py schemas/runtime tests
git commit -m "Add pinned project runtime launcher"
~~~

### Task 2: Implement caller-context and post-wheel authority verification

**Files:**
- Create: src/agent_stack/runtime/caller_context.py
- Create: src/agent_stack/runtime/authority.py
- Create: src/agent_stack/runtime/maintenance.py
- Create: schemas/runtime/caller-context.v1.json
- Test: tests/unit/runtime/test_caller_context.py
- Test: tests/integration/runtime/test_runtime_authority.py
- Test: tests/integration/runtime/test_mixed_launcher_descriptor.py

**Interfaces:**
- Produces: VerifiedCallerContext, verify_runtime_authority(), select_recovery_runtime().
- Consumes: Task 6 release verifier, committed/candidate Manifest/plan, Task 3 journals.

- [ ] **Step 1: RED tests**

Test allowed paths/TTY/harness, reserved duplicates, relative/control/secret fields, verification-before-external-read, descriptor mismatch, committed/candidate allowlist, mixed launcher/descriptor preimage/candidate, third state, and old task journal after pull.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/unit/runtime/test_caller_context.py tests/integration/runtime/test_runtime_authority.py tests/integration/runtime/test_mixed_launcher_descriptor.py -q`
Expected: FAIL on missing authority/context modules.

- [ ] **Step 3: Implement verification pipeline**

Package/release -> Manifest/descriptor/journal/workspace -> command admission -> caller-context re-probe. Never restore ambient env.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/unit/runtime/test_caller_context.py tests/integration/runtime/test_runtime_authority.py tests/integration/runtime/test_mixed_launcher_descriptor.py -q`
Expected: ordinary commands require exact equality; diagnostics/recovery use the narrow allowlist.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/runtime schemas/runtime tests
git commit -m "Verify runtime authority and caller context"
~~~

### Task 3: Implement workspace registration

**Files:**
- Create: src/agent_stack/runtime/workspace.py
- Create: schemas/runtime/workspace-local.v1.json
- Create: schemas/runtime/workspace-registration-transaction.v1.json
- Create: schemas/runtime/approval-replay.v1.json
- Test: tests/integration/runtime/test_workspace_register.py
- Test: tests/concurrency/runtime/test_workspace_register_killpoints.py

**Interfaces:**
- Produces: register_workspace(), recover_workspace_registration().
- Consumes: Reconciler/bootstrap/runtime locks and verified committed Manifest.

- [ ] **Step 1: RED tests**

Inject crashes before/after workspace rename and replay-ledger rename; test duplicate registration, tracked local file, malformed/identity-mismatched pair, maintenance, unrelated transaction, and original-absence CAS.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/integration/runtime/test_workspace_register.py tests/concurrency/runtime/test_workspace_register_killpoints.py -q`
Expected: FAIL on missing implementation.

- [ ] **Step 3: Implement paired transaction**

Write journal first, workspace candidate first, empty replay ledger last as commit point. No Manifest/artifact/task mutation.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/integration/runtime/test_workspace_register.py tests/concurrency/runtime/test_workspace_register_killpoints.py -q`
Expected: partial states require exact recovery; the committed pair validates.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/runtime/workspace.py schemas/runtime tests
git commit -m "Register clone-local workspace state"
~~~

### Task 4: Implement normative Trellis quiescence scanner

**Files:**
- Create: src/agent_stack/runtime/scanner.py
- Test: tests/unit/runtime/test_scanner.py
- Test: tests/property/runtime/test_scanner_bounds.py
- Add fixtures: tests/fixtures/runtime/trellis_layouts/

**Interfaces:**
- Produces: scan_task_quiescence(source_layout, target_layout, source_schemas, target_schemas).
- Consumes: Core verified layout/snapshot/finding schemas.

- [ ] **Step 1: RED tests**

Cover source/target active/archive union, one-segment grammar, integration recognition, metadata parser/classifier, task-journal phase table, missing/unknown/wrong-type/symlink/oversized/overcount/overdepth/case/Unicode states, duplicate UUID/ref/path conflicts, and stranded one-sided state.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/unit/runtime/test_scanner.py tests/property/runtime/test_scanner_bounds.py -q`
Expected: FAIL on absent scanner.

- [ ] **Step 3: Implement fact-only bounded scan**

Return canonical snapshot/findings with stable order. Do not emit command blockers or run source code.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/unit/runtime/test_scanner.py tests/property/runtime/test_scanner_bounds.py -q`
Expected: no skipped or truncated ambiguous state.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/runtime/scanner.py tests/unit/runtime/test_scanner.py tests/property/runtime/test_scanner_bounds.py tests/fixtures/runtime
git commit -m "Implement bounded Trellis task scanner"
~~~

### Task 5: Implement workspace migration and stale-evidence revalidation

**Files:**
- Modify: src/agent_stack/runtime/workspace.py
- Create: schemas/runtime/workspace-migration-transaction.v1.json
- Test: tests/integration/runtime/test_workspace_migrate.py
- Test: tests/concurrency/runtime/test_workspace_migrate_killpoints.py

**Interfaces:**
- Produces: migrate_workspace(), recover_workspace_migration().
- Consumes: Task 6 static release evidence, scanner, Core evaluators, exact migration functions.

- [ ] **Step 1: RED tests**

Test migration-required/ahead/diverged/missing/invalid relationship, unsupported discovery, unfinished journal, non-archived task, stranded state, exact local candidates, crashes after replay/outbox writes, final workspace rename, and external task change before commit.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/integration/runtime/test_workspace_migrate.py tests/concurrency/runtime/test_workspace_migrate_killpoints.py -q`
Expected: FAIL on absent migration.

- [ ] **Step 3: Implement local-only transaction**

Acquire Reconciler lock then runtime-state gate, bind snapshot/evaluators before writes, apply replay/outbox first, rescan, rename workspace last. Never edit task/Trellis/project authority.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/integration/runtime/test_workspace_migrate.py tests/concurrency/runtime/test_workspace_migrate_killpoints.py -q`
Expected: snapshot mismatch is `AWP_TASK_QUIESCENCE_CHANGED` primary.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/runtime/workspace.py schemas/runtime/workspace-migration-transaction.v1.json tests
git commit -m "Migrate clone-local workspace contracts"
~~~

### Task 6: Implement integration schema, replay ledger, and task outbox

**Files:**
- Create: src/agent_stack/runtime/integration.py
- Create: src/agent_stack/runtime/replay.py
- Create: src/agent_stack/runtime/outbox.py
- Create: schemas/runtime/integration.v1.json
- Create: schemas/runtime/task-outbox.v1.json
- Test: tests/contracts/runtime/test_integration.py
- Test: tests/unit/runtime/test_replay.py
- Test: tests/unit/runtime/test_outbox.py

**Interfaces:**
- Produces: validate_integration(), reserve/consume_proof(), enqueue/deliver_effect().
- Consumes: Core task contract/surface digests and Task 5 proof schema.

- [ ] **Step 1: RED tests**

Test closed mode union, workflow contract digest, mandatory surfaces, UUID/ref semantics, status/revision/claim invariants, proof key excluding transaction, absent->reserved->consumed, TTL recovery, journal-before-reservation rollback, missing/corrupt ledger, deterministic outbox keys, idempotent delivery.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/contracts/runtime/test_integration.py tests/unit/runtime/test_replay.py tests/unit/runtime/test_outbox.py -q`
Expected: FAIL on missing modules.

- [ ] **Step 3: Implement monotonic local state**

Use whole-file CAS for replay and immutable outbox item creation/closed delivery transitions. No lifecycle authority from outbox status.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/contracts/runtime/test_integration.py tests/unit/runtime/test_replay.py tests/unit/runtime/test_outbox.py -q`
Expected: all invalid state transitions fail closed.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/runtime/integration.py src/agent_stack/runtime/replay.py src/agent_stack/runtime/outbox.py schemas/runtime tests
git commit -m "Add integration replay and task outbox state"
~~~

### Task 7: Implement task admission, mutation, archive, and recovery

**Files:**
- Create: src/agent_stack/runtime/task_journal.py
- Create: src/agent_stack/runtime/task_service.py
- Create: src/agent_stack/runtime/recovery.py
- Create: schemas/runtime/task-transaction.v1.json
- Test: tests/integration/runtime/test_task_admission.py
- Test: tests/integration/runtime/test_task_mutation.py
- Test: tests/integration/runtime/test_task_archive.py
- Test: tests/concurrency/runtime/test_task_killpoints.py

**Interfaces:**
- Produces: admit_task(), claim_task(), transition_task(), release_task(), archive_task(), recover_task_transaction().
- Consumes: Task 5 verified Decision/proof, Task 3 CAS, locked Trellis adapter candidates.

- [ ] **Step 1: RED transaction tests**

Cover duplicate UUID/ref, deterministic task tree, planned-before-reservation, every admission phase, admitting non-runnable, metadata commit, two claimants, foreign claim, phase transitions, completed prerequisite, collision-free archive destination, every archive phase, outbox cleanup, and rollback third state.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/integration/runtime/test_task_admission.py tests/integration/runtime/test_task_mutation.py tests/integration/runtime/test_task_archive.py tests/concurrency/runtime/test_task_killpoints.py -q`
Expected: FAIL on missing service.

- [ ] **Step 3: Implement phase machines**

Admission commit is integration admitting->active revision 2 after metadata. Archive commit is archiving->archived after move/metadata. Precommit is reversible file work only; postcommit is outbox/cleanup.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/integration/runtime/test_task_admission.py tests/integration/runtime/test_task_mutation.py tests/integration/runtime/test_task_archive.py tests/concurrency/runtime/test_task_killpoints.py -q && uv run pytest tests/concurrency/runtime/test_task_killpoints.py -q`
Expected: no partially accepted task state.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/runtime/task_journal.py src/agent_stack/runtime/task_service.py src/agent_stack/runtime/recovery.py schemas/runtime tests
git commit -m "Implement recoverable task-state transactions"
~~~

### Task 8: Implement existing-task runtime load and immutable dispatch

**Files:**
- Create: src/agent_stack/runtime/runtime_load.py
- Create: schemas/runtime/task-runtime-load-request.v1.json
- Create: schemas/runtime/task-runtime-dispatch.v1.json
- Modify: src/agent_stack/runtime/api.py
- Test: tests/integration/runtime/test_runtime_load.py
- Test: tests/concurrency/runtime/test_runtime_load_races.py

**Interfaces:**
- Produces: load_task_runtime(TaskRuntimeLoadRequest) -> ImmutableDispatchBundle.
- Consumes: integration state, runtime surface registry/inventory/recipes, managed/package resources.

- [ ] **Step 1: RED tests**

Test no create Decision input, task ID/ref/revision/status/phase/claim, canonical entry owner, pinned membership, transitive dependencies, observed=current=pinned, mandatory meta-surfaces, no arbitrary path/token, no-follow reads, immutable bundle, no catalog reopen, state/byte/graph races, restorative repair then resume.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/integration/runtime/test_runtime_load.py tests/concurrency/runtime/test_runtime_load_races.py -q`
Expected: FAIL on missing loader.

- [ ] **Step 3: Implement one-shot authorization/dispatch**

Hold runtime-state snapshot through complete bundle construction and recheck. Dispatch from memory only and return no reusable authority.

- [ ] **Step 4: Verify GREEN and full Task 4 suite**

Run: `uv run pytest tests/unit/runtime tests/contracts/runtime tests/property/runtime tests/integration/runtime tests/concurrency/runtime tests/e2e/runtime -q && uv run ruff check src/agent_stack/runtime tests && uv run mypy src/agent_stack/runtime`
Expected: pass.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/runtime/runtime_load.py src/agent_stack/runtime/api.py schemas/runtime tests
git commit -m "Authorize existing-task runtime dispatch"
~~~

## Global Validation

Run full runtime suite including launcher shell tests and all crash boundaries. Verify launcher/doctor/migrate task_quiescence equality. Verify only Task 4 authority paths changed in filesystem fixtures. Run uv build.

## Implementation Constraint Prompt

~~~text
Read the approved Runtime/Task-State spec and this plan. Stop on any frozen-interface conflict. Use strict TDD and observe RED before behavior code. The launcher is sole pre-wheel authority, workspace migration is local-only, Task-state Service writes only authorized paths, and existing-task load never uses the create Decision. Do not implement platform wrapper semantics or release publication. Run launcher, scanner, migration, task-transaction, replay, runtime-load, crash, and concurrency suites before completion.
~~~

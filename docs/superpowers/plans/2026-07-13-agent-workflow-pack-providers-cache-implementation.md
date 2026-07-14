# Agent Workflow Pack Providers and Secure Cache Implementation Plan

**Status:** Draft — implementation-plan review required

> **Execution contract:** Execute only under the current route/integration contract. In speckit-superpowers mode, heavy-development-router remains the sole top-level orchestrator. Track steps with checkboxes.

**Goal:** Implement verified acquisition, content-addressed cache, safe archive extraction, provider planning/approval, trusted broker release handshake, whole-file attempt journals, sandboxed initializer execution, deterministic output validation, and provenance.

**Architecture:** Provider code is isolated under agent_stack.providers and returns immutable verified evidence to the Renderer. Cache and attempt state live outside target projects, use OS locks plus atomic promotion, and never become project authority. A first-party broker separates durable attempt preparation from third-party process release.

**Tech Stack:** Python 3.11-3.14, Task 1 core API, stdlib networking/process/archive primitives with locked pure-Python vendored helpers where required, pytest/Hypothesis, Linux/WSL process controls.

## Global Constraints

- Source: docs/superpowers/specs/2026-07-13-agent-workflow-pack-providers-cache-design.md, producer C b19e57a0e4d6e5094b853d428909e4d10d2283de.
- Prerequisite: approved Core implementation and core.schema-catalog.v1/core.errors.v1 behavior.
- Provider/cache code never writes the target project.
- Archive full-byte hash precedes format parsing, enumeration, or extraction.
- Provider exception approval requires the frozen direct-human branch; model input cannot approve.
- Attempt object updates are whole-file atomic replaces under a plan lock.
- Third-party code cannot run before durable prepared state plus one broker release token/receipt.
- Behavior changes use strict TDD; no production code before observed RED.
- No implementation starts until this plan is separately approved.

## File Structure

~~~text
src/agent_stack/providers/
  __init__.py
  api.py
  models.py
  cache.py
  download.py
  archive.py
  approval.py
  attempts.py
  broker.py
  sandbox.py
  initializer.py
  provenance.py
  errors.py
schemas/providers/
tests/unit/providers/
tests/contracts/providers/
tests/property/providers/
tests/integration/providers/
tests/concurrency/providers/
tests/fixtures/providers/
~~~

---

### Task 1: Define provider models, errors, and frozen API

**Files:**
- Create: src/agent_stack/providers/models.py
- Create: src/agent_stack/providers/errors.py
- Create: src/agent_stack/providers/api.py
- Create: schemas/providers/provider-plan.v1.json
- Create: schemas/providers/provider-result.v1.json
- Create: schemas/providers/provider-failure.v1.json
- Test: tests/contracts/providers/test_provider_api.py

**Interfaces:**
- Produces: acquire(), execute_provider(), ProviderPlan, AcquisitionResult, ProviderExecutionResult, ProviderFailure.
- Consumes: Task 1 SchemaCatalog, canonical digest, structured errors.

- [ ] **Step 1: RED contract test**

~~~python
def test_provider_api_exports_frozen_callables():
    from agent_stack.providers.api import acquire, execute_provider
    assert callable(acquire)
    assert callable(execute_provider)
~~~

Add schema tests rejecting target paths, ambient env, caller URLs, final reconcile identity, and unknown fields.

- [ ] **Step 2: Verify RED**

Run: uv run pytest tests/contracts/providers/test_provider_api.py -q
Expected: FAIL because provider package is absent.

- [ ] **Step 3: Add immutable models and stubs**

Implement closed dataclasses/enums and ProviderFailure mapping only. Public functions may raise NotImplementedError until later tasks; tests must assert signatures/schema, not behavior.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/contracts/providers/test_provider_api.py -q && uv run ruff check src/agent_stack/providers tests/contracts/providers && uv run mypy src/agent_stack/providers`
Expected: pass.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/providers schemas/providers tests/contracts/providers
git commit -m "Define provider execution contracts"
~~~

### Task 2: Implement content-addressed cache and verified streaming download

**Files:**
- Create: src/agent_stack/providers/cache.py
- Create: src/agent_stack/providers/download.py
- Test: tests/unit/providers/test_cache.py
- Test: tests/integration/providers/test_download.py
- Test: tests/concurrency/providers/test_cache_locking.py

**Interfaces:**
- Produces: CacheStore.acquire_lock(), CacheStore.publish_verified(), download_verified().
- Consumes: AcquisitionRequest and trusted URL/hash/size policy from caller.

- [ ] **Step 1: RED tests**

Test temporary download, compressed-size ceiling, complete SHA-256, redirect host revalidation, interrupted partial quarantine, two-process contention, atomic promotion, immutable hash path, and polluted-cache refusal.

~~~python
def test_partial_download_is_never_promoted(tmp_cache, fake_transport):
    fake_transport.interrupt_after(128)
    with pytest.raises(ProviderFailure):
        download_verified(request_fixture(), tmp_cache, fake_transport)
    assert not tmp_cache.object_path(EXPECTED_SHA).exists()
~~~

- [ ] **Step 2: Verify RED**

Run: uv run pytest tests/unit/providers/test_cache.py tests/integration/providers/test_download.py tests/concurrency/providers/test_cache_locking.py -q
Expected: FAIL on missing cache/download code.

- [ ] **Step 3: Implement minimal cache protocol**

Use plan/object OS locks, same-filesystem temp files, streaming limit/hash, final rehash, atomic rename, immutable destination, and quarantine metadata. Never derive trust from cache presence.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/unit/providers/test_cache.py tests/integration/providers/test_download.py tests/concurrency/providers/test_cache_locking.py -q`
Expected: all pass, including two-process serialization.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/providers/cache.py src/agent_stack/providers/download.py tests
git commit -m "Add verified provider cache acquisition"
~~~

### Task 3: Implement hash-before-parse archive validation and extraction

**Files:**
- Create: src/agent_stack/providers/archive.py
- Create: schemas/providers/archive-policy.v1.json
- Test: tests/unit/providers/test_archive.py
- Test: tests/property/providers/test_archive_paths.py
- Add fixtures: tests/fixtures/providers/archives/

**Interfaces:**
- Produces: inspect_archive(), extract_verified_archive(), content_root_digest().
- Consumes: verified complete archive object and closed extraction policy.

- [ ] **Step 1: RED tests**

Create fixtures for traversal, absolute paths, symlink/hardlink/device/FIFO/socket, duplicate/case/Unicode collision, unsafe modes, excessive count/file/expanded size/ratio, and a sentinel proving no parser call before complete hash match.

- [ ] **Step 2: Verify RED**

Run: uv run pytest tests/unit/providers/test_archive.py tests/property/providers/test_archive_paths.py -q
Expected: FAIL because archive validator is absent.

- [ ] **Step 3: Implement bounded extraction**

Validate complete hash first, then format/member inventory, then extract into a private root with no-follow path creation. Compute deterministic content root over normalized paths/bytes/modes.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/unit/providers/test_archive.py tests/property/providers/test_archive_paths.py -q`
Expected: valid fixture passes; every hostile fixture fails before unsafe write.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/providers/archive.py schemas/providers/archive-policy.v1.json tests
git commit -m "Validate provider archives before extraction"
~~~

### Task 4: Implement provider exception approval verification

**Files:**
- Create: src/agent_stack/providers/approval.py
- Create: schemas/providers/provider-approval.v1.json
- Test: tests/unit/providers/test_approval.py
- Test: tests/contracts/providers/test_approval_union.py

**Interfaces:**
- Produces: verify_provider_approval(plan, proof, capability, now).
- Consumes: Core ApprovalProof catalog branch and Task 5 capability schema shape without importing Task 5 implementation.

- [ ] **Step 1: RED tests**

Test direct-human actor, provider-plan/risk/workspace/prospective-transaction/challenge binding, verifier/harness version, TTL/skew, task-field rejection, model-authored receipt rejection, and instruction-only capability failure.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/unit/providers/test_approval.py tests/contracts/providers/test_approval_union.py -q`
Expected: FAIL on missing verifier.

- [ ] **Step 3: Implement closed branch verification**

Return an immutable VerifiedProviderApproval. Perform no replay mutation and no execution.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/unit/providers/test_approval.py tests/contracts/providers/test_approval_union.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/providers/approval.py schemas/providers/provider-approval.v1.json tests/unit/providers/test_approval.py tests/contracts/providers/test_approval_union.py
git commit -m "Verify provider exception approvals"
~~~

### Task 5: Implement attempt journal and immutable release receipts

**Files:**
- Create: src/agent_stack/providers/attempts.py
- Create: schemas/providers/provider-attempts.v1.json
- Create: schemas/providers/provider-release-receipt.v1.json
- Test: tests/unit/providers/test_attempts.py
- Test: tests/concurrency/providers/test_attempt_journal.py

**Interfaces:**
- Produces: AttemptStore.prepare(), record_released(), record_terminal(), recover_interrupted().
- Consumes: provider-plan digest, approval digest, prospective transaction, liveness evidence.

- [ ] **Step 1: RED tests**

Cover prepared -> released -> succeeded/failed/interrupted, prepared -> interrupted, illegal transition, duplicate IDs/tokens, corrupt JSON, whole-file atomic replacement, immutable receipt original-absence, approval/plan mismatch, and concurrent attempt exclusion.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/unit/providers/test_attempts.py tests/concurrency/providers/test_attempt_journal.py -q`
Expected: FAIL on missing AttemptStore.

- [ ] **Step 3: Implement monotonic journal**

Lock one plan, validate complete object, apply one in-memory transition, write temp plus atomic replace. Receipts are immutable sibling files and never grant approval.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/unit/providers/test_attempts.py tests/concurrency/providers/test_attempt_journal.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/providers/attempts.py schemas/providers tests/unit/providers/test_attempts.py tests/concurrency/providers/test_attempt_journal.py
git commit -m "Add provider attempt recovery journal"
~~~

### Task 6: Implement trusted broker handshake and containment liveness

**Files:**
- Create: src/agent_stack/providers/broker.py
- Create: src/agent_stack/providers/sandbox.py
- Create: tests/integration/providers/test_broker.py
- Create: tests/concurrency/providers/test_broker_killpoints.py

**Interfaces:**
- Produces: TrustedBroker.start(), release_once(), containment_liveness(), terminate_containment().
- Consumes: durable prepared attempt and one-time token digest.

- [ ] **Step 1: RED kill-point tests**

Inject termination after broker spawn, parent-death setup, durable prepared, before token send, after send, after receipt, while child runs, after child exit, and before terminal journal update. Assert no third-party import before valid release and no retry while receipt/liveness is live or ambiguous.

- [ ] **Step 2: Verify RED**

Run: uv run pytest tests/integration/providers/test_broker.py tests/concurrency/providers/test_broker_killpoints.py -q
Expected: FAIL on absent broker.

- [ ] **Step 3: Implement minimal Linux/WSL broker**

Use private framed pipes, parent identity, Linux parent-death signal, immediate parent recheck, monotonic deadline, one token, immutable receipt before provider import, new process group/containment, and positive liveness evidence.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/integration/providers/test_broker.py tests/concurrency/providers/test_broker_killpoints.py -q`
Expected: all kill points match prepared/released/terminal evidence rules.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/providers/broker.py src/agent_stack/providers/sandbox.py tests/integration/providers tests/concurrency/providers
git commit -m "Gate provider execution through trusted broker"
~~~

### Task 7: Implement initializer execution, determinism, and provenance

**Files:**
- Create: src/agent_stack/providers/initializer.py
- Create: src/agent_stack/providers/provenance.py
- Create: schemas/providers/provenance.v1.json
- Modify: src/agent_stack/providers/api.py
- Test: tests/integration/providers/test_initializer.py
- Test: tests/property/providers/test_deterministic_output.py
- Test: tests/contracts/providers/test_provenance.py

**Interfaces:**
- Produces: complete execute_provider() and acquire() results consumed by Task 3.
- Consumes: Tasks 2-6 provider components.

- [ ] **Step 1: RED tests**

Test temporary HOME/XDG, environment allowlist/secret stripping, closed stdin, target isolation, time/output/resource limits, network policy report, identical output in independent roots, expected content-root match, sanitized diagnostics, and complete SPDX provenance.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/integration/providers/test_initializer.py tests/property/providers/test_deterministic_output.py tests/contracts/providers/test_provenance.py -q`
Expected: FAIL because orchestration is incomplete.

- [ ] **Step 3: Implement minimal orchestration**

Plan -> approval -> attempt preparation -> broker release -> sandboxed execution -> output validation -> terminal attempt/result. Reject unjournaled output and nondeterministic/mismatched roots.

- [ ] **Step 4: Verify GREEN and full provider suite**

Run:

~~~bash
uv run pytest tests/unit/providers tests/contracts/providers tests/property/providers tests/integration/providers tests/concurrency/providers -q
uv run ruff check src/agent_stack/providers tests
uv run mypy src/agent_stack/providers
~~~

Expected: all pass.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/providers schemas/providers tests
git commit -m "Complete secure provider execution"
~~~

## Global Validation

Run the full provider suite twice, including broker SIGKILL tests. Verify git diff contains no target-project writer outside test fixtures. Run uv build and inspect the provider public API.

## Implementation Constraint Prompt

~~~text
Use the approved Providers/Cache spec and this plan as execution inputs. Stop on conflict with frozen Core APIs. Follow strict TDD for every behavior change and observe the expected RED before production edits. Do not write target-project files, construct reconcile plans, mutate tasks, calculate routes, or publish releases. Cache, attempts, receipts, and provider output are evidence only. Run all provider unit, contract, property, integration, and concurrency tests before completion.
~~~

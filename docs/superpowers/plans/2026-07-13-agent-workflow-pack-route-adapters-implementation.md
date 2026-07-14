# Agent Workflow Pack Route Admission and Platform Adapters Implementation Plan

**Status:** Draft — implementation-plan review required

> **Execution contract:** Execute under the current route/integration contract. heavy-development-router is the sole top-level orchestrator for admitted heavy tasks; Superpowers components are leaves only. Track all steps below.

**Goal:** Implement the compiled route calculator/verifier, Intent handling, direct-human task approval verification, task surface closure, CapabilityManifest probes, Claude Code/Codex/OpenCode adapter contracts, wrappers, catalog projection, and golden tests.

**Architecture:** agent_stack.route contains pure policy/Decision logic and deterministic adapter projections. Platform-specific modules populate one closed PlatformAdapterContract; wrappers call the repository launcher and Task 4 runtime-load API. Route-gated content remains outside auto-discovery.

**Tech Stack:** Python 3.11-3.14, frozen Core/Runtime APIs, platform contract fixtures, pytest/Hypothesis, golden filesystem snapshots.

## Global Constraints

- Source: docs/superpowers/specs/2026-07-13-agent-workflow-pack-route-adapters-design.md, producer C 9148cc0620f7c58fbcf058d08f592e0b47ca00f8.
- Prerequisites: Tasks 1, 3, and 4 implementations complete.
- Task 1 owns RouteDecision/ApprovalProof/CapabilityManifest schemas; Task 5 only populates/verifies them.
- Natural-language signal completeness is not a security guarantee.
- classify-only is never executable.
- execute-light is native-light only and creates no integrated task.
- Integrated existing-task wrappers call task runtime load and never replay create Decision.
- No nested top-level orchestrator; heavy-development-router alone owns heavy top-level flow.
- Strict TDD for behavior changes; plan requires separate approval.

## File Structure

~~~text
src/agent_stack/route/
  __init__.py
  api.py
  signals.py
  intent.py
  calculator.py
  verifier.py
  approval.py
  surfaces.py
  capabilities.py
  adapter_contract.py
  projection.py
  wrappers.py
  errors.py
  platforms/
    claude_code.py
    codex.py
    opencode.py
schemas/route/
catalog/platforms.yaml
artifact-definitions/platforms/
overlays/project-policy/
tests/unit/route/
tests/contracts/route/
tests/property/route/
tests/golden/route/
tests/integration/route/
tests/fixtures/route/
~~~

---

### Task 1: Define platform adapter schemas, errors, and public API

**Files:**
- Create: src/agent_stack/route/api.py
- Create: src/agent_stack/route/adapter_contract.py
- Create: src/agent_stack/route/errors.py
- Create: schemas/route/platform-adapter.v1.json
- Create: schemas/route/platform-adapter-projection.v1.json
- Create: schemas/route/approval-verification-result.v1.json
- Create: schemas/route/adapter-golden-contract.v1.json
- Create: schemas/route/route-failure.v1.json
- Test: tests/contracts/route/test_route_api.py
- Test: tests/contracts/route/test_adapter_contract.py

**Interfaces:**
- Produces: frozen route.adapters.v1 callables and Task 5 schemas.
- Consumes: Core RouteDecision/CapabilityManifest/RenderUnit and Runtime Task-state types.

- [ ] **Step 1: RED contract tests**

Assert exact public signatures, closed adapter fields, exact platform IDs, no unknown routes/signals/capabilities, and no task mutation fields in adapter projection.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/contracts/route/test_route_api.py tests/contracts/route/test_adapter_contract.py -q`
Expected: FAIL because package is absent.

- [ ] **Step 3: Add immutable contracts and API stubs**

Implement dataclasses/enums/schema validation only.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/contracts/route/test_route_api.py tests/contracts/route/test_adapter_contract.py -q && uv run ruff check src/agent_stack/route tests/contracts/route && uv run mypy src/agent_stack/route`
Expected: pass.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/route schemas/route tests/contracts/route
git commit -m "Define route adapter contracts"
~~~

### Task 2: Implement stable signals, Intent validation, and compiled policy

**Files:**
- Create: src/agent_stack/route/signals.py
- Create: src/agent_stack/route/intent.py
- Create: catalog/route-policy.yaml
- Test: tests/unit/route/test_signals.py
- Test: tests/unit/route/test_intent.py
- Test: tests/fixtures/route/legacy-trigger-map.yaml

**Interfaces:**
- Produces: normalize_signals(), validate_task_intent(), evaluate_compiled_policy().
- Consumes: Core route-policy and TaskIntent schemas.

- [ ] **Step 1: RED tests**

Cover all hard/compound signals, unknown/duplicate IDs, conflicting explicit modes, explicit-only Trellis, native-light default, stable rule order, executable --signals rejection, Intent digest binding, and legacy trigger parity.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/unit/route/test_signals.py tests/unit/route/test_intent.py -q`
Expected: FAIL on missing policy implementation.

- [ ] **Step 3: Implement frozen policy evaluation**

Load one verified compiled policy; no second adapter/router signal list. Reasons cannot change route.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/unit/route/test_signals.py tests/unit/route/test_intent.py -q`
Expected: route parity against `tests/fixtures/route/legacy-trigger-map.yaml` passes.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/route/signals.py src/agent_stack/route/intent.py catalog/route-policy.yaml tests
git commit -m "Implement stable route policy evaluation"
~~~

### Task 3: Implement RouteDecision calculator and canonical verifier

**Files:**
- Create: src/agent_stack/route/calculator.py
- Create: src/agent_stack/route/verifier.py
- Test: tests/unit/route/test_calculator.py
- Test: tests/property/route/test_decision_digests.py
- Test: tests/integration/route/test_decision_freshness.py

**Interfaces:**
- Produces: calculate_route(), verify_route_decision().
- Consumes: Core digest formulas, Runtime route-time task inventory, compiled policy.

- [ ] **Step 1: RED tests**

Test all legal/illegal operation-route pairs, forbidden branch fields, UUIDv4 task/challenge uniqueness, UUIDv5 decision ID, authority/task-state freshness, workspace/adapter mismatch, externally reconstructed envelope no issuer privilege, classify-only rejection by consumers, and Intent-only executable signals.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/unit/route/test_calculator.py tests/property/route/test_decision_digests.py tests/integration/route/test_decision_freshness.py -q`
Expected: FAIL on missing modules.

- [ ] **Step 3: Implement calculator and replay verifier**

Acquire runtime-state snapshot through Runtime API, compute all derived fields, and verify by full current-authority replay. Do not sign or claim sole issuance.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/unit/route/test_calculator.py tests/property/route/test_decision_digests.py tests/integration/route/test_decision_freshness.py -q`
Expected: deterministic policy and unique integrated envelopes.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/route/calculator.py src/agent_stack/route/verifier.py tests
git commit -m "Calculate and verify route decisions"
~~~

### Task 4: Implement direct-human task approval verification

**Files:**
- Create: src/agent_stack/route/approval.py
- Test: tests/unit/route/test_task_approval.py
- Test: tests/integration/route/test_platform_approval_receipts.py

**Interfaces:**
- Produces: verify_task_creation_approval().
- Consumes: Core ApprovalProof and CapabilityManifest, verified Decision, Runtime caller context.

- [ ] **Step 1: RED tests**

Test actor/operation/workspace/task ID/ref/surface/intent/Decision/challenge/time/verifier/harness binding, cancellation/timeout, model JSON/stdin/generic yes rejection, instruction-only capability failure, and provider-field cross-branch rejection.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/unit/route/test_task_approval.py tests/integration/route/test_platform_approval_receipts.py -q`
Expected: FAIL on missing verifier.

- [ ] **Step 3: Implement platform receipt verification adapter**

Return immutable verification result only; Runtime owns replay/consumption.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/unit/route/test_task_approval.py tests/integration/route/test_platform_approval_receipts.py -q`
Expected: only version-tested direct-human receipts pass.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/route/approval.py tests
git commit -m "Verify direct-human task approvals"
~~~

### Task 5: Implement integrated task surface closure

**Files:**
- Create: src/agent_stack/route/surfaces.py
- Test: tests/unit/route/test_surface_closure.py
- Test: tests/property/route/test_surface_closure_graph.py

**Interfaces:**
- Produces: derive_task_surface_closure().
- Consumes: Core runtime-surface registry/digests and selected route/platform/entry.

- [ ] **Step 1: RED tests**

Cover mandatory meta-surfaces, platform adapter, route owner, Trellis/heavy entries, transitive hooks/agents/skills/commands, stable sort, cycles/dangling/unknown/duplicate, affected/unaffected adapter/skill, and Task 4 admission recomputation parity.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/unit/route/test_surface_closure.py tests/property/route/test_surface_closure_graph.py -q`
Expected: FAIL on missing module.

- [ ] **Step 3: Implement exact graph closure**

No caller surfaces or wildcard selectors. Compute imported task surface digest.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/unit/route/test_surface_closure.py tests/property/route/test_surface_closure_graph.py -q`
Expected: exact closures and digests match Core fixtures.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/route/surfaces.py tests
git commit -m "Derive integrated task surface closures"
~~~

### Task 6: Implement capability measurement and platform contracts

**Files:**
- Create: src/agent_stack/route/capabilities.py
- Create: src/agent_stack/route/platforms/claude_code.py
- Create: src/agent_stack/route/platforms/codex.py
- Create: src/agent_stack/route/platforms/opencode.py
- Create: catalog/platforms.yaml
- Create: artifact-definitions/platforms/claude-code.yaml
- Create: artifact-definitions/platforms/codex.yaml
- Create: artifact-definitions/platforms/opencode.yaml
- Test: tests/unit/route/test_capabilities.py
- Test: tests/integration/route/test_platform_probes.py

**Interfaces:**
- Produces: measure_capability_manifest() and three locked PlatformAdapterContracts.
- Consumes: Runtime verified caller context and Core capability schema.

- [ ] **Step 1: RED tests**

Test exact harness versions/ranges, unknown->unsupported, enforced proof by bypass test, instruction-only downgrade, read-only doctor probes, default-platform strict blocking, native-light binding, caller fields, Trellis roots/metadata, and approval verifier declarations.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/unit/route/test_capabilities.py tests/integration/route/test_platform_probes.py -q`
Expected: FAIL on missing implementations or data.

- [ ] **Step 3: Implement exact version-bound contracts**

Populate only measured claims. Store exact render units, wrapper entries, blocked bypass entries, and probe IDs in locked data.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/unit/route/test_capabilities.py tests/integration/route/test_platform_probes.py -q`
Expected: three manifests meet or explicitly fail strict requirements.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/route/capabilities.py src/agent_stack/route/platforms catalog/platforms.yaml artifact-definitions/platforms tests
git commit -m "Add versioned platform capability contracts"
~~~

### Task 7: Implement deterministic adapter projection and catalog exposure

**Files:**
- Create: src/agent_stack/route/projection.py
- Create: overlays/project-policy/
- Test: tests/golden/route/test_adapter_projection.py
- Test: tests/property/route/test_discoverable_closure.py
- Golden fixtures: tests/golden/route/fixtures/

**Interfaces:**
- Produces: project_platform_adapter().
- Consumes: Core DesiredStateIR/RenderUnit and locked PlatformAdapterContract.

- [ ] **Step 1: RED goldens**

For all three platforms, assert exact paths/bytes/modes/unit IDs/surface owners; disabled/gated reference closure; gated catalog absent from auto-discovery; leaf compatibility overlay or block; distribution-independent logical projection.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/golden/route/test_adapter_projection.py tests/property/route/test_discoverable_closure.py -q`
Expected: FAIL on missing projection.

- [ ] **Step 3: Implement pure projection**

Never inspect target state or add an IR-absent route/capability/unit.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/golden/route/test_adapter_projection.py tests/property/route/test_discoverable_closure.py -q && uv run pytest tests/golden/route/test_adapter_projection.py tests/property/route/test_discoverable_closure.py -q`
Expected: identical projections and complete surface inventory.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/route/projection.py overlays/project-policy tests/golden/route tests/property/route
git commit -m "Project deterministic platform adapters"
~~~

### Task 8: Implement native-light and integrated wrappers

**Files:**
- Create: src/agent_stack/route/wrappers.py
- Modify: src/agent_stack/route/api.py
- Test: tests/integration/route/test_wrappers.py
- Test: tests/golden/route/test_wrapper_outputs.py

**Interfaces:**
- Produces: invoke_execute_light(), invoke_integrated_wrapper().
- Consumes: verified execute-light Decision or Runtime load_task_runtime().

- [ ] **Step 1: RED tests**

Test classify-only rejection, execute-light one-shot/native-only/no task state, integrated exact runtime-load args, no create Decision replay, repository launcher path, no PATH/global tool, no catalog read/reopen, maintenance/phase/claim errors, heavy router sole top-level, and direct entry bypass detection.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/integration/route/test_wrappers.py tests/golden/route/test_wrapper_outputs.py -q`
Expected: FAIL on missing wrappers.

- [ ] **Step 3: Implement two closed branches**

Native-light consumes fresh Decision. Integrated delegates all authorization/bundle construction to Task 4 and dispatches only returned bundle.

- [ ] **Step 4: Verify GREEN and full Task 5 suite**

Run: `uv run pytest tests/unit/route tests/contracts/route tests/property/route tests/golden/route tests/integration/route -q && uv run ruff check src/agent_stack/route tests && uv run mypy src/agent_stack/route`
Expected: pass.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/route/wrappers.py src/agent_stack/route/api.py tests
git commit -m "Add route-gated platform wrappers"
~~~

## Global Validation

Run test-routing golden suite across supported Claude Code, Codex, and OpenCode fixtures. Re-enumerate auto-discovery and runtime surfaces. Verify no direct integrated/heavy bypass and no route-gated content leakage. Run uv build.

## Implementation Constraint Prompt

~~~text
Read the approved Route/Adapters spec and this plan. Stop on conflicts with Core or Runtime frozen APIs. Use strict TDD and observe RED before code. Do not redefine RouteDecision, ApprovalProof, CapabilityManifest, task lifecycle, runtime-load authorization, or ownership. Keep heavy-development-router as the sole heavy top-level orchestrator. Integrated wrappers must call task runtime load and never replay the create Decision or open the gated catalog. Run all routing, surface, capability, wrapper, and three-platform golden tests before completion.
~~~

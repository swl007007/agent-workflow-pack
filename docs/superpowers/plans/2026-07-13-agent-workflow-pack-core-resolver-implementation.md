# Agent Workflow Pack Core Resolver Implementation Plan

**Status:** Draft — implementation-plan review required

> **Execution contract:** Execute only under the current route/integration contract. If the admitted mode is speckit-superpowers, heavy-development-router is the sole top-level orchestrator; Superpowers tools may be leaf disciplines only. Track every step with the checkboxes below.

**Goal:** Build the schema, canonicalization, profile/catalog Resolver, protected-path policy, runtime-surface coverage, candidate-impact, pure task evaluators, saved-plan digest primitives, diagnostics, and frozen Task 1 API.

**Architecture:** A dependency-free public core package uses closed dataclasses and pure functions. Repository YAML/JSON is parsed into normalized values, validated against versioned schemas, and converted into immutable domain models before any digest or policy calculation. Downstream features import only src/agent_stack/core/api.py.

**Tech Stack:** Python 3.11-3.14, stdlib dataclasses/enum/hashlib/json/pathlib/uuid, a vendored pure-Python YAML/JSON-schema layer selected during Task 1, pytest, Hypothesis, Ruff, mypy, uv.

## Global Constraints

- Source of truth: approved core spec at docs/superpowers/specs/2026-07-13-agent-workflow-pack-core-resolver-design.md, producer C 2e0bfda7619223397f7c9610d312a2aab42156ab.
- Umbrella content digest must remain c2f23807cc36066b4b92478657cacaf15eb5cb6bd14e307e1e76f1c30de0284d.
- Runtime package must remain self-contained; pyproject runtime dependencies stay empty.
- Supported Python is >=3.11,<3.15.
- Schema ID, schema version, and digest domain are separate exact identifiers.
- RFC 8785 JCS, NFC/path/mode normalization, duplicate-key rejection, and domain-separated SHA-256 are normative.
- Core functions are pure and perform no network, target writes, platform probing, route receipt verification, or task mutation.
- Strict TDD applies to every behavior-changing task.
- This plan is an execution guide. A conflict with the approved spec or frozen interface stops the affected task.
- No production implementation begins until this plan is separately approved.

## Artifact Inputs

| Artifact | Path | Status |
|---|---|---|
| umbrella | docs/superpowers/specs/2026-07-13-agent-workflow-pack-design.md | Approved |
| feature spec | docs/superpowers/specs/2026-07-13-agent-workflow-pack-core-resolver-design.md | Approved/interface-frozen |
| decomposition/ownership | docs/superpowers/plans/2026-07-13-agent-workflow-pack-feature-spec-decomposition.md | Frozen |
| Speckit tasks.md | not present | Not applicable to this non-Speckit repository bootstrap; if later added, reconcile before execution |

## File Structure

Create:

~~~text
pyproject.toml
src/agent_stack/__init__.py
src/agent_stack/core/
  __init__.py
  api.py
  canonical.py
  schema_catalog.py
  models.py
  profile.py
  catalog.py
  artifact_policy.py
  surfaces.py
  impact.py
  task_policy.py
  saved_plan.py
  diagnostics.py
  errors.py
  resolver.py
schemas/core/
tests/conftest.py
tests/unit/core/
tests/contracts/core/
tests/property/core/
~~~

api.py is the only downstream import surface. schema_catalog.py loads versioned schemas and rejects duplicate keys/unknown versions. canonical.py owns normalization and digest helpers. Other modules each own one domain behavior.

---

### Task 1: Bootstrap the Python package and test harness

**Files:**
- Create: pyproject.toml
- Create: src/agent_stack/__init__.py
- Create: src/agent_stack/core/__init__.py
- Create: tests/conftest.py
- Create: tests/contracts/core/test_package_contract.py

**Interfaces:**
- Produces: importable agent_stack package, Python range, empty runtime dependency set, pytest/Ruff/mypy commands.
- Consumes: none.

- [ ] **Step 1: Write the failing package contract**

~~~python
def test_core_api_is_importable():
    from agent_stack.core import api
    assert api.CORE_INTERFACE_VERSION == 1
~~~

- [ ] **Step 2: Verify RED**

Run: uv run pytest tests/contracts/core/test_package_contract.py -q
Expected: FAIL because pyproject.toml/package/api.py do not exist.

- [ ] **Step 3: Add minimal scaffold**

Create pyproject.toml with build-system, package discovery under src, requires-python >=3.11,<3.15, no project.dependencies, and dev groups for pytest, hypothesis, ruff, mypy, build. Create api.py with CORE_INTERFACE_VERSION = 1 only.

- [ ] **Step 4: Verify GREEN and tool discovery**

Run:

~~~bash
uv sync
uv run pytest tests/contracts/core/test_package_contract.py -q
uv run ruff check src tests
uv run mypy src
~~~

Expected: one passing test and clean lint/type output.

- [ ] **Step 5: Commit**

~~~bash
git add pyproject.toml uv.lock src/agent_stack tests/conftest.py tests/contracts/core/test_package_contract.py
git commit -m "Bootstrap agent stack core package"
~~~

### Task 2: Implement duplicate-safe parsing, schema catalog, and canonical digests

**Files:**
- Create: src/agent_stack/core/canonical.py
- Create: src/agent_stack/core/schema_catalog.py
- Create: src/agent_stack/core/errors.py
- Create: schemas/core/schema-catalog.v1.json
- Create: schemas/core/resolution-failure.v1.json
- Test: tests/unit/core/test_canonical.py
- Test: tests/contracts/core/test_schema_catalog.py
- Test: tests/property/core/test_canonical_properties.py

**Interfaces:**
- Produces: canonical_json_bytes(value), digest(domain, value), normalize_path(), normalize_mode(), SchemaCatalog.load_and_validate().
- Consumes: package scaffold.

- [ ] **Step 1: Write RED tests**

~~~python
def test_duplicate_yaml_keys_are_rejected(schema_catalog):
    with pytest.raises(CoreFailure, match="AWP_SCHEMA_INVALID"):
        schema_catalog.parse_yaml("id: one\\nid: two\\n")

def test_domain_separation_changes_digest():
    value = {"x": 1}
    assert digest("agent-workflow.a.v1", value) != digest("agent-workflow.b.v1", value)
~~~

Add Hypothesis properties for mapping-order independence, set sorting, NFC normalization, path aliases, canonical UUIDs, modes, and canonical-null.

- [ ] **Step 2: Verify RED**

Run: uv run pytest tests/unit/core/test_canonical.py tests/contracts/core/test_schema_catalog.py tests/property/core/test_canonical_properties.py -q
Expected: FAIL on missing modules/functions.

- [ ] **Step 3: Implement minimal parser and canonicalization**

Implement a pure parser boundary that rejects duplicate keys before schema validation. Implement RFC 8785-compatible canonical bytes, exact ASCII-domain-plus-NUL digesting, and closed normalization helpers. Record every CoreFailure as code, exit category, repository-relative path, and structured details.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/unit/core/test_canonical.py tests/contracts/core/test_schema_catalog.py tests/property/core/test_canonical_properties.py -q && uv run ruff check src/agent_stack/core tests/unit/core tests/contracts/core tests/property/core && uv run mypy src/agent_stack/core`
Expected: all pass.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/core schemas/core tests/unit/core tests/contracts/core tests/property/core
git commit -m "Add core schema and canonicalization primitives"
~~~

### Task 3: Implement profile, catalog, workflow-lock, and capability resolution

**Files:**
- Create: src/agent_stack/core/models.py
- Create: src/agent_stack/core/profile.py
- Create: src/agent_stack/core/catalog.py
- Create: schemas/core/profile.v1.json
- Create: schemas/core/catalog.v1.json
- Create: schemas/core/workflow-lock.v1.json
- Create: schemas/core/capability-manifest.v1.json
- Test: tests/unit/core/test_profile.py
- Test: tests/unit/core/test_catalog.py
- Test: tests/contracts/core/test_workflow_lock.py

**Interfaces:**
- Produces: resolve_profile(), resolve_catalog_closure(), evaluate_capabilities(), normalized Profile/Catalog/WorkflowLock models.
- Consumes: canonical/schema/error primitives.

- [ ] **Step 1: Write RED tests**

Cover single inheritance, cycle rejection, exact field merge rules, disabled precedence, dependency/conflict/reference closure, stable topological order, unknown IDs, and enforced/instruction-only/unsupported capability ordering.

~~~python
def test_disabled_dependency_blocks_resolution():
    profile = profile_fixture(enable=["skill:a"], disable=["skill:b"])
    catalog = catalog_fixture(dependencies={"skill:a": ["skill:b"]})
    with pytest.raises(CoreFailure, match="AWP_CATALOG_CLOSURE_BLOCKED"):
        resolve_catalog_closure(profile, catalog, capability_fixture())
~~~

- [ ] **Step 2: Verify RED**

Run: uv run pytest tests/unit/core/test_profile.py tests/unit/core/test_catalog.py tests/contracts/core/test_workflow_lock.py -q
Expected: FAIL because Resolver models/functions are absent.

- [ ] **Step 3: Implement minimum closed resolution**

Implement exact merge/closure algorithms from the spec. Do not perform version lookup or latest queries. Emit immutable normalized models and stable ordering only.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/unit/core/test_profile.py tests/unit/core/test_catalog.py tests/contracts/core/test_workflow_lock.py -q && uv run pytest tests/unit/core tests/contracts/core -q`
Expected: all pass.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/core schemas/core tests/unit/core tests/contracts/core
git commit -m "Implement profile and catalog resolution"
~~~

### Task 4: Implement artifact definitions, Trellis layout, and protected-path validation

**Files:**
- Create: src/agent_stack/core/artifact_policy.py
- Create: schemas/core/artifact-definition.v1.json
- Create: schemas/core/trellis-task-layout.v1.json
- Test: tests/unit/core/test_artifact_policy.py
- Test: tests/property/core/test_trellis_layout.py
- Test: tests/fixtures/core/trellis_layouts/

**Interfaces:**
- Produces: validate_artifact_definitions(), validate_trellis_layout(), derive_protected_paths().
- Consumes: normalized models and canonical paths.

- [ ] **Step 1: Write RED tests**

Test all five ownership classes, legal ownership/merge/mode pairs, global protected paths, target collisions, marker overlap, bounded metadata expansion, safe-nfc-segment-v1, uuid-json-v1, root nesting, and metadata collision with artifacts/control-plane/Git/Spec Kit/source.

- [ ] **Step 2: Verify RED**

Run: uv run pytest tests/unit/core/test_artifact_policy.py tests/property/core/test_trellis_layout.py -q
Expected: FAIL on missing validators.

- [ ] **Step 3: Implement closed validators**

Implement no glob/regex callbacks, bounded exact expansion only, and finite collision proof. Return normalized VerifiedTrellisTaskLayout; never touch filesystem.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/unit/core/test_artifact_policy.py tests/property/core/test_trellis_layout.py -q`
Expected: all pass with no skipped collision cases.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/core schemas/core tests/unit/core tests/property/core tests/fixtures/core
git commit -m "Validate artifact and Trellis ownership boundaries"
~~~

### Task 5: Implement runtime-surface registry, inventory, digests, and coverage proof

**Files:**
- Create: src/agent_stack/core/surfaces.py
- Create: schemas/core/runtime-surface-registry.v1.json
- Create: schemas/core/runtime-unit-inventory.v1.json
- Create: schemas/core/surface-coverage-proof.v1.json
- Test: tests/unit/core/test_surfaces.py
- Test: tests/property/core/test_surface_graph.py

**Interfaces:**
- Produces: validate_surface_registry(), compute_surface_digests(), prove_surface_coverage().
- Consumes: canonical digest helpers and artifact/render-unit identities.

- [ ] **Step 1: Write RED tests**

Cover reserved IDs, mandatory runtime-control-plane/surface-registry, one owner per runtime-visible unit, full byte/mode/contract recipe inclusion, dangling/cyclic references, stable topological digest order, removed canonical-null, and distribution ownership equivalence.

- [ ] **Step 2: Verify RED**

Run: uv run pytest tests/unit/core/test_surfaces.py tests/property/core/test_surface_graph.py -q
Expected: FAIL on missing surface API.

- [ ] **Step 3: Implement minimal graph algorithms**

Validate registry source without computed roots, compute leaf/surface digests in stable topological order, and produce a non-authoritative coverage witness.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/unit/core/test_surfaces.py tests/property/core/test_surface_graph.py -q`
Expected: all pass, including cycle and omitted-byte failures.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/core/surfaces.py schemas/core tests/unit/core/test_surfaces.py tests/property/core/test_surface_graph.py
git commit -m "Add runtime surface coverage model"
~~~

### Task 6: Implement CandidateImpact and restorative-repair normalization

**Files:**
- Create: src/agent_stack/core/impact.py
- Create: schemas/core/candidate-impact.v1.json
- Test: tests/unit/core/test_impact.py
- Test: tests/property/core/test_impact_properties.py

**Interfaces:**
- Produces: compute_candidate_impact(CurrentContract, ObservedState, DesiredStateIR).
- Consumes: surface registry/digests and normalized current/candidate authority.

- [ ] **Step 1: Write RED tests**

Test authority additions/removals, surface before/after records, heavy contract-changing predicate, affected/unaffected adapter/skill, stale pinned digest, canonical-null removals, restorative repair with separate contract_before/observed_before/after, and unclassified runtime bytes.

- [ ] **Step 2: Verify RED**

Run: uv run pytest tests/unit/core/test_impact.py tests/property/core/test_impact_properties.py -q
Expected: FAIL on missing CandidateImpact implementation.

- [ ] **Step 3: Implement pure impact derivation**

Never accept caller-authored impact. Produce stable sorted authority/surface/repair records and reject incomplete evidence.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/unit/core/test_impact.py tests/property/core/test_impact_properties.py -q && uv run mypy src/agent_stack/core`
Expected: all pass.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/core/impact.py schemas/core/candidate-impact.v1.json tests/unit/core/test_impact.py tests/property/core/test_impact_properties.py
git commit -m "Normalize candidate surface and repair impact"
~~~

### Task 7: Implement task snapshot schemas, pure evaluators, and workspace diagnostics

**Files:**
- Create: src/agent_stack/core/task_policy.py
- Create: src/agent_stack/core/diagnostics.py
- Create: schemas/core/task-quiescence-snapshot.v1.json
- Create: schemas/core/task-findings.v1.json
- Create: schemas/core/workspace-diagnostic.v1.json
- Test: tests/unit/core/test_task_policy.py
- Test: tests/property/core/test_workspace_diagnostics.py

**Interfaces:**
- Produces: evaluate_workspace_state_quiescence(), evaluate_task_gate(), build_workspace_diagnostic().
- Consumes: TaskSnapshot/Findings values populated later by Task 4 and CandidateImpact.

- [ ] **Step 1: Write RED tests**

Create fixed fixtures for ambiguity, unfinished journal, heavy/Trellis-native tasks, completed/archived states, stranded layout, no-op sync, restorative repair, deterministic blocker order, ahead/diverged/missing/invalid relationship evidence, and state/admission separation.

- [ ] **Step 2: Verify RED**

Run: uv run pytest tests/unit/core/test_task_policy.py tests/property/core/test_workspace_diagnostics.py -q
Expected: FAIL on missing pure evaluators.

- [ ] **Step 3: Implement imported signatures exactly**

Keep the fixed state evaluator command-independent. Make operation/candidate impact inputs exclusive to evaluate_task_gate. Keep AWP_TASK_QUIESCENCE_CHANGED outside initial blocker ordering.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/unit/core/test_task_policy.py tests/property/core/test_workspace_diagnostics.py -q`
Expected: identical evidence yields identical task_quiescence for every command fixture.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/core/task_policy.py src/agent_stack/core/diagnostics.py schemas/core tests/unit/core/test_task_policy.py tests/property/core/test_workspace_diagnostics.py
git commit -m "Add task gate and workspace diagnostic policies"
~~~

### Task 8: Implement saved-plan digest DAG and Resolver facade

**Files:**
- Create: src/agent_stack/core/saved_plan.py
- Create: src/agent_stack/core/resolver.py
- Modify: src/agent_stack/core/api.py
- Create: schemas/core/saved-plan.v1.json
- Create: schemas/core/desired-state-ir.v1.json
- Test: tests/unit/core/test_saved_plan.py
- Test: tests/integration/core/test_resolver.py
- Test: tests/property/core/test_digest_dag.py

**Interfaces:**
- Produces: resolve(ResolverInputs), render_saved_plan schema helpers, frozen public exports in api.py.
- Consumes: Tasks 2-7 modules.

- [ ] **Step 1: Write RED tests**

Test four operation branches, forbidden cross-fields, exact plan_core -> journal_binding -> candidate_manifest -> plan order, cycle/reverse-edge rejection, DesiredStateIR stable ordering, and full Resolver validation order.

- [ ] **Step 2: Verify RED**

Run: uv run pytest tests/unit/core/test_saved_plan.py tests/integration/core/test_resolver.py tests/property/core/test_digest_dag.py -q
Expected: FAIL on missing facade/DAG.

- [ ] **Step 3: Implement minimal integration**

Compose previously tested pure modules. api.py exports only the frozen Task 1 types/callables/error namespace. Do not implement Task 3 rendering.

- [ ] **Step 4: Verify GREEN and full Task 1 suite**

Run:

~~~bash
uv run pytest tests/unit/core tests/contracts/core tests/property/core tests/integration/core -q
uv run ruff check src tests
uv run mypy src
~~~

Expected: all pass.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/core schemas/core tests
git commit -m "Complete core resolver interface"
~~~

## Global Validation

~~~bash
uv run pytest tests/unit/core tests/contracts/core tests/property/core tests/integration/core -q
uv run ruff check src tests
uv run mypy src
uv build
python - <<'PY'
from importlib.metadata import metadata
m = metadata("agent-workflow-pack")
assert not m.get_all("Requires-Dist")
PY
~~~

Expected: tests/lint/types/build pass; runtime Requires-Dist remains empty.

## Implementation Constraint Prompt

~~~text
Read the approved core feature spec and this plan before editing. The approved spec and frozen interface are authoritative; stop on conflict. Execute under the current route/integration contract. Use strict TDD for every behavior-changing step: write the focused failing test, run it and confirm the expected failure, implement the smallest change, rerun to green, then refactor. Do not implement providers, rendering/reconciliation, task state, route adapters, lifecycle CLI, or release behavior in this plan. Run the focused validation and full Task 1 suite before completion. Do not mark complete if validation was not executed.
~~~

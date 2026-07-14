# Agent Workflow Pack Lifecycle Packaging and Release Implementation Plan

**Status:** Draft — implementation-plan review required

> **Execution contract:** Execute only under the current route/integration contract. In heavy mode, heavy-development-router remains the sole top-level orchestrator. Track each step below.

**Goal:** Compose the complete CLI, structured output, immutable release trust chain, directed compatibility/upgrade flow, self-contained distributions, reproducibility/provenance gates, and full AC-01–AC-64 end-to-end release suite.

**Architecture:** agent_stack.cli is a thin composition layer over Tasks 1-5. agent_stack.release owns Release Identity, detached-manifest trust, compatibility classification, artifact build verification, distribution render digest, and release gates. CI builds wheel/sdist first, creates the detached manifest afterward, publishes an immutable GitHub release, and re-verifies published assets.

**Tech Stack:** Python 3.11-3.14, uv build/lock, stdlib packaging metadata plus build tooling, GitHub Actions/API, pytest, subprocess E2E fixtures, SPDX/provenance data.

## Global Constraints

- Source: docs/superpowers/specs/2026-07-13-agent-workflow-pack-lifecycle-release-design.md, producer C afe76961f5e7b3690ecb9e86eb322fff9e31cd30.
- Prerequisite: Tasks 1-5 implementations and frozen APIs complete.
- CLI composition cannot redefine domain semantics/errors.
- Wheel runtime Requires-Dist must be empty.
- release-manifest.json is detached and absent from wheel/sdist/source tree.
- Build order must not introduce self-hash or bundle cycles.
- Python 3.11, 3.12, 3.13, and 3.14 all pass.
- GitHub release must be immutable before acceptance.
- Compatibility is exact and directed; no latest lookup or arbitrary rollback.
- Strict TDD applies to behavior; release metadata generation uses deterministic artifact checks written before generator code.
- No implementation until this plan is separately approved.

## File Structure

~~~text
src/agent_stack/
  __main__.py
  cli/
    __init__.py
    parser.py
    dispatch.py
    output.py
    redaction.py
  release/
    __init__.py
    api.py
    identity.py
    trust.py
    manifest.py
    compatibility.py
    distribution.py
    gates.py
    provenance.py
    errors.py
release/trust-policy.yaml
compatibility/releases.yaml
workflow.lock
profiles/
catalog/
schemas/release/
LICENSES/
THIRD_PARTY_NOTICES.md
tools/release/
.github/workflows/ci.yml
.github/workflows/release.yml
tests/contracts/cli/
tests/contracts/release/
tests/unit/cli/
tests/unit/release/
tests/property/release/
tests/packaging/
tests/integration/cli/
tests/concurrency/cli/
tests/e2e/
tests/fixtures/e2e/
~~~

---

### Task 1: Define release schemas, identity, errors, and public API

**Files:**
- Create: src/agent_stack/release/api.py
- Create: src/agent_stack/release/identity.py
- Create: src/agent_stack/release/errors.py
- Create: schemas/release/release-identity.v1.json
- Create: schemas/release/release-manifest.v1.json
- Create: schemas/release/release-trust-policy.v1.json
- Create: schemas/release/release-compatibility.v1.json
- Create: schemas/release/release-gate-result.v1.json
- Test: tests/contracts/release/test_release_api.py
- Test: tests/property/release/test_release_identity.py

**Interfaces:**
- Produces: lifecycle.release.v1 schemas/callables and non-self-referential release_id().
- Consumes: Core canonicalization.

- [ ] **Step 1: RED tests**

Test identical Release Identity across wheel/sdist/Git form, repository/distribution/version sensitivity, excluded source/hash/URL fields, manifest no self digest, compatibility no self/source/container fields, and public API signatures.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/contracts/release/test_release_api.py tests/property/release/test_release_identity.py -q`
Expected: FAIL because release package is absent.

- [ ] **Step 3: Implement immutable release models and identity**

Only repository_id, distribution_name, version enter Release Identity.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/contracts/release/test_release_api.py tests/property/release/test_release_identity.py -q && uv run ruff check src/agent_stack/release tests/contracts/release tests/property/release && uv run mypy src/agent_stack/release`
Expected: pass.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/release schemas/release tests/contracts/release tests/property/release
git commit -m "Define release identity and manifest contracts"
~~~

### Task 2: Implement trust policy and detached-manifest verification

**Files:**
- Create: src/agent_stack/release/trust.py
- Create: src/agent_stack/release/manifest.py
- Create: release/trust-policy.yaml
- Test: tests/unit/release/test_trust_policy.py
- Test: tests/integration/release/test_manifest_verification.py

**Interfaces:**
- Produces: verify_release_manifest(locator, packaged_policy).
- Consumes: Provider verified download/cache and exact GitHub release metadata.

- [ ] **Step 1: RED tests**

Test exact host/owner/repo/tag/asset name, HTTPS/API, redirect allowlist, immutable release, manifest digest/schema, Release Identity, source commit, asset name/size/hash, bundle roots, project/journal override rejection, and trust-root change rejection.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/unit/release/test_trust_policy.py tests/integration/release/test_manifest_verification.py -q`
Expected: FAIL on missing verifier.

- [ ] **Step 3: Implement locator derivation and verification**

All locators derive from packaged policy. Cache is optimization, not authority.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/unit/release/test_trust_policy.py tests/integration/release/test_manifest_verification.py -q`
Expected: all wrong-repository, tag, mutable-release, and hash cases exit with supply-chain failure.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/release/trust.py src/agent_stack/release/manifest.py release/trust-policy.yaml tests
git commit -m "Verify detached immutable releases"
~~~

### Task 3: Implement directed compatibility classification and upgrade target selection

**Files:**
- Create: src/agent_stack/release/compatibility.py
- Create: compatibility/releases.yaml
- Test: tests/unit/release/test_compatibility.py
- Test: tests/property/release/test_compatibility_graph.py
- Test: tests/integration/release/test_source_static_metadata.py

**Interfaces:**
- Produces: classify_compatibility(), select_candidate_runtime().
- Consumes: verified current/target releases, local-state contract, static source distribution metadata.

- [ ] **Step 1: RED tests**

Cover candidate-owned forward edge, current-owned rollback edge, reverse-only ahead, neither diverged, missing evidence, invalid authenticated schema exit 30, target bundle identities, local-state/layout/schema migrations, no URL/hash/source/self digest, source archive inspection without import/execute, no retained-runtime witness.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/unit/release/test_compatibility.py tests/property/release/test_compatibility_graph.py tests/integration/release/test_source_static_metadata.py -q`
Expected: FAIL on missing graph implementation.

- [ ] **Step 3: Implement exact directed classification**

No semantic version ordering and no implied patch/minor compatibility.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/unit/release/test_compatibility.py tests/property/release/test_compatibility_graph.py tests/integration/release/test_source_static_metadata.py -q`
Expected: all relationship dimensions match Core diagnostics.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/release/compatibility.py compatibility/releases.yaml tests
git commit -m "Add directed release compatibility"
~~~

### Task 4: Implement CLI parser, dispatch matrix, output, and redaction

**Files:**
- Create: src/agent_stack/__main__.py
- Create: src/agent_stack/cli/parser.py
- Create: src/agent_stack/cli/dispatch.py
- Create: src/agent_stack/cli/output.py
- Create: src/agent_stack/cli/redaction.py
- Create: schemas/release/cli-result.v1.json
- Create: schemas/release/cli-diagnostic.v1.json
- Test: tests/contracts/cli/test_command_matrix.py
- Test: tests/contracts/cli/test_json_output.py
- Test: tests/unit/cli/test_redaction.py
- Test: tests/integration/cli/test_dispatch_ownership.py

**Interfaces:**
- Produces: compose_lifecycle_command(), render_cli_json(), render_cli_human().
- Consumes: all Task 1-5 APIs/errors without redefining them.

- [ ] **Step 1: RED contract tests**

Test every command branch/flag, owner delegation, one JSON stdout object, stderr diagnostics, exit categories, workspace state/admission separation, repository-relative paths, URL/secret/external-stderr redaction, traceback debug behavior, and no semantic duplicate in dispatch.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/contracts/cli/test_command_matrix.py tests/contracts/cli/test_json_output.py tests/unit/cli/test_redaction.py tests/integration/cli/test_dispatch_ownership.py -q`
Expected: FAIL on missing CLI.

- [ ] **Step 3: Implement thin composition**

Parser builds one typed invocation. Dispatch calls owning API. Output derives human/JSON from same result.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/contracts/cli/test_command_matrix.py tests/contracts/cli/test_json_output.py tests/unit/cli/test_redaction.py tests/integration/cli/test_dispatch_ownership.py -q`
Expected: stable JSON schema and frozen error category for every imported error.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/__main__.py src/agent_stack/cli schemas/release/cli-result.v1.json schemas/release/cli-diagnostic.v1.json tests
git commit -m "Compose lifecycle CLI and structured output"
~~~

### Task 5: Implement upgrade and supported rollback orchestration

**Files:**
- Modify: src/agent_stack/cli/dispatch.py
- Create: src/agent_stack/release/distribution.py
- Test: tests/integration/cli/test_upgrade.py
- Test: tests/integration/cli/test_rollback.py
- Test: tests/concurrency/cli/test_upgrade_recovery.py

**Interfaces:**
- Produces: verified candidate-to-Reconciler orchestration.
- Consumes: release verifier/edge, Provider acquisition, Core Resolver/impact/evaluators, Renderer plan/apply, Runtime scanner/local migration.

- [ ] **Step 1: RED tests**

Test default running-release target, exact --to, candidate wheel verified before metadata/code, no latest lookup, plan diff/approval, active-task gate, local migration before Manifest, quiescence rescan, committed/candidate journal runtime, older-target rollback executed by current runtime, and crash recovery.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/integration/cli/test_upgrade.py tests/integration/cli/test_rollback.py tests/concurrency/cli/test_upgrade_recovery.py -q`
Expected: FAIL because orchestration is incomplete.

- [ ] **Step 3: Implement composition only**

Do not duplicate provider/Resolver/Reconciler/Runtime behavior. Preserve each owner result and error.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/integration/cli/test_upgrade.py tests/integration/cli/test_rollback.py tests/concurrency/cli/test_upgrade_recovery.py -q`
Expected: exact directed transitions only; post-commit cleanup only.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/cli/dispatch.py src/agent_stack/release/distribution.py tests
git commit -m "Orchestrate verified upgrades and rollback"
~~~

### Task 6: Implement distribution render digest and artifact builds

**Files:**
- Modify: pyproject.toml
- Create: tools/release/build_artifacts.py
- Create: tools/release/compute_render_digest.py
- Test: tests/packaging/test_self_contained_wheel.py
- Test: tests/packaging/test_package_data.py
- Test: tests/packaging/test_distribution_render_digest.py
- Test: tests/packaging/test_python_matrix_contract.py

**Interfaces:**
- Produces: build_release_artifacts(), compute_distribution_render_digest().
- Consumes: all package data, render projections, verified detached-manifest substitutions.

- [ ] **Step 1: RED artifact checks**

Before generator code, write checks for empty wheel Requires-Dist, all package data, manifest absent from distributions, wheel/sdist/Git logical inventory parity, scoped digest exclusions, same digest across forms/repeated roots, Python 3.11-3.14 metadata.

- [ ] **Step 2: Verify RED**

Run: uv run pytest tests/packaging -q
Expected: FAIL because build scripts/package data are incomplete.

- [ ] **Step 3: Implement build and digest tools**

Fix bundle roots before build; compute distribution hashes/sizes only after artifacts are final. Do not create detached manifest inside source distributions.

- [ ] **Step 4: Verify GREEN**

Run:

~~~bash
uv build
uv run pytest tests/packaging -q
~~~

Expected: wheel/sdist pass and render digests match.

- [ ] **Step 5: Commit**

~~~bash
git add pyproject.toml tools/release tests/packaging
git commit -m "Build reproducible self-contained distributions"
~~~

### Task 7: Implement provenance, notices, and release gates

**Files:**
- Create: src/agent_stack/release/provenance.py
- Create: src/agent_stack/release/gates.py
- Create: tools/release/generate_notices.py
- Create: LICENSES/
- Create: THIRD_PARTY_NOTICES.md
- Test: tests/packaging/test_provenance.py
- Test: tests/packaging/test_notices.py
- Test: tests/integration/release/test_release_gates.py

**Interfaces:**
- Produces: run_release_gates() and complete license/provenance artifacts.
- Consumes: Provider provenance and full artifact/unit inventory.

- [ ] **Step 1: RED tests**

Test every upstream/vendored/projected artifact maps to source/version/hash/SPDX/modified/full license; exact pinned license revalidation; target notices; missing/ambiguous provenance gate; all 13 release gates.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/packaging/test_provenance.py tests/packaging/test_notices.py tests/integration/release/test_release_gates.py -q`
Expected: FAIL on missing modules or assets.

- [ ] **Step 3: Implement deterministic provenance aggregation**

Generate notices from locked records. Do not infer license solely from component name.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/packaging/test_provenance.py tests/packaging/test_notices.py tests/integration/release/test_release_gates.py -q`
Expected: complete SPDX and full texts; a missing record blocks.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/release/provenance.py src/agent_stack/release/gates.py tools/release/generate_notices.py LICENSES THIRD_PARTY_NOTICES.md tests
git commit -m "Enforce release provenance and notices"
~~~

### Task 8: Implement CI matrices and immutable publication workflow

**Files:**
- Create: .github/workflows/ci.yml
- Create: .github/workflows/release.yml
- Create: tools/release/publish_release.py
- Create: tools/release/verify_published_release.py
- Test: tests/contracts/release/test_ci_workflows.py
- Test: tests/integration/release/test_publication_sequence.py

**Interfaces:**
- Produces: build->verify->manifest->publish->immutable->reverify pipeline.
- Consumes: build artifacts and release gates.

- [ ] **Step 1: RED workflow tests**

Parse workflows and assert Python 3.11-3.14, artifact-based tests, no manifest-before-build, immutable release verification, exact asset re-fetch/hash, no asset replacement, and required gate dependencies.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/contracts/release/test_ci_workflows.py tests/integration/release/test_publication_sequence.py -q`
Expected: FAIL because workflows or scripts are absent.

- [ ] **Step 3: Implement deterministic workflow**

Use immutable version/tag inputs only. Generate release-manifest.json after final wheel/sdist, publish once, require immutable status, re-download and verify.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/contracts/release/test_ci_workflows.py tests/integration/release/test_publication_sequence.py -q`
Expected: the ordered mocked publication sequence passes; mutation or replacement fails.

- [ ] **Step 5: Commit**

~~~bash
git add .github/workflows tools/release tests
git commit -m "Add immutable release publication workflow"
~~~

### Task 9: Implement full AC-01–AC-64 E2E closure

**Files:**
- Create: tests/e2e/test_distribution_sequence.py
- Create: tests/e2e/test_clone_a_lifecycle.py
- Create: tests/e2e/test_clone_b_workspace_migration.py
- Create: tests/e2e/test_clone_c_relationship_diagnostics.py
- Create: tests/e2e/test_acceptance_matrix.py
- Create: tests/fixtures/e2e/legacy-workflow-pack/
- Create: tests/fixtures/e2e/releases/

**Interfaces:**
- Produces: executable release evidence for all 64 AC rows.
- Consumes: every Task 1-8 implementation.

- [ ] **Step 1: RED acceptance matrix**

Create a machine-readable table mapping AC-01..AC-64 to one primary test and required supporting suites. Assert exactly 64 unique IDs and no missing test node.

- [ ] **Step 2: Verify RED**

Run: uv run pytest tests/e2e/test_acceptance_matrix.py -q
Expected: FAIL because scenarios/evidence nodes are incomplete.

- [ ] **Step 3: Implement clone/distribution scenarios incrementally**

Add the approved Task 6 sequence: artifact identity/render parity; clone A init/route/admission/load/repair/archive/upgrade; clone B pull/static source evidence/task gates/workspace migration; clone C ahead/diverged/missing/invalid diagnostics. Each behavior gets its own RED before helper/fixture code.

- [ ] **Step 4: Verify GREEN and complete release suite**

Run:

~~~bash
uv run pytest tests/unit tests/contracts tests/property tests/golden tests/integration tests/concurrency tests/packaging tests/e2e -q
uv run ruff check src tests tools
uv run mypy src
uv build
~~~

Expected: all pass on every supported Python job; acceptance matrix reports 64/64.

- [ ] **Step 5: Commit**

~~~bash
git add tests/e2e tests/fixtures/e2e
git commit -m "Close release acceptance matrix"
~~~

## Global Validation

Run the complete suite from clean wheel, sdist, and Git checkout environments. Run release gates twice. Inspect built wheel metadata for empty Requires-Dist and absence of release-manifest.json. Verify published-release workflow with a disposable immutable test repository before production release.

## Implementation Constraint Prompt

~~~text
Read the approved Lifecycle/Release spec and this plan. Stop on conflicts with any frozen Task 1-5 interface. Use strict TDD for behavior and prewritten deterministic checks for generated release artifacts. Keep CLI composition thin; never redefine domain semantics/errors. Build wheel/sdist before generating the detached manifest, keep runtime Requires-Dist empty, support Python 3.11-3.14, use exact directed compatibility, and verify immutable GitHub release assets after publication. Run the complete AC-01–AC-64 suite before completion.
~~~

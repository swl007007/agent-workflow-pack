# Agent Workflow Pack Lifecycle Packaging and Release Implementation Plan

**Status:** Approved — implementation-plan frozen

> **Execution contract:** Execute only under the current route/integration contract. In heavy mode, heavy-development-router remains the sole top-level orchestrator. Track each step below.

**Goal:** Compose the complete CLI, structured output, immutable release trust chain, directed compatibility/upgrade flow, self-contained distributions, reproducibility/provenance gates, and full AC-01–AC-64 end-to-end release suite.

**Architecture:** `agent_stack.release` is split into an early release kernel and a late lifecycle/release composition. Lifecycle Tasks 1-3 implement Release Identity, detached-manifest trust, static source evidence, and directed compatibility before Renderer/Runtime work. After real Renderer, Runtime, and Route bindings are integration-complete, Tasks 4-9 compose the CLI, freeze provenance/licenses/notices, build the final wheel/sdist, run gates on those final bytes, create the detached manifest, publish an immutable GitHub release, and re-verify published assets.

**Tech Stack:** Python 3.11-3.14, uv build/lock, stdlib packaging metadata plus build tooling, GitHub Actions/API, pytest, subprocess E2E fixtures, SPDX/provenance data.

## Global Constraints

- Source: docs/superpowers/specs/2026-07-13-agent-workflow-pack-lifecycle-release-design.md, producer C afe76961f5e7b3690ecb9e86eb322fff9e31cd30.
- Prerequisite for Lifecycle Tasks 1-3: Core and Providers integration-complete.
- Prerequisite for Lifecycle Tasks 4-9: release-kernel component-complete plus Renderer, Runtime, and Route integration-complete with all cross-feature fakes replaced.
- CLI composition cannot redefine domain semantics/errors.
- Wheel runtime Requires-Dist must be empty.
- release-manifest.json is detached and absent from wheel/sdist/source tree.
- Build order must not introduce self-hash or bundle cycles.
- Python 3.11, 3.12, 3.13, and 3.14 all pass.
- GitHub release must be immutable before acceptance.
- Compatibility is exact and directed; no latest lookup or arbitrary rollback.
- Strict TDD applies to behavior; release metadata generation uses deterministic artifact checks written before generator code.
- No implementation until this plan is separately approved.

## Cross-Plan Execution DAG and Completion States

The fixed waves are:

1. Core -> Providers.
2. Lifecycle Tasks 1-3 -> `release-kernel component-complete`; then stop this plan.
3. Renderer component-complete through frozen scanner port tests.
4. Runtime component-complete using the real release kernel and test-only Route verifier ports; Runtime Task 4 makes Renderer integration-complete.
5. Route Task 8 binds real verifiers, making Route and Runtime integration-complete.
6. Resume Lifecycle Tasks 4-9. Task 6 freezes provenance/licenses/notices, Task 7 builds and gates final distributions, Task 8 publishes, and Task 9 closes E2E.

`release-kernel component-complete` is narrower than Lifecycle component-complete: only the Task 1-3 public release APIs and tests pass, with no CLI, distribution build, publication, or system-completion claim. `integration-complete` is granted only after Tasks 4-9 use real cross-feature implementations and the final artifact/E2E gates pass.

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
    kernel.py
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
- Create: src/agent_stack/release/kernel.py
- Create: src/agent_stack/release/identity.py
- Create: src/agent_stack/release/errors.py
- Create: schemas/release/release-identity.v1.json
- Create: schemas/release/release-manifest.v1.json
- Create: schemas/release/release-trust-policy.v1.json
- Create: schemas/release/release-compatibility.v1.json
- Create: schemas/release/release-gate-result.v1.json
- Test: tests/contracts/release/test_release_api.py
- Test: tests/contracts/release/test_release_kernel_boundary.py
- Test: tests/property/release/test_release_identity.py

**Interfaces:**
- Produces: lifecycle.release.v1 schemas/callables, non-self-referential release_id(), and a release-kernel import boundary that contains no CLI/Renderer/Runtime/Route imports.
- Consumes: Core canonicalization.

- [ ] **Step 1: RED tests**

Test identical Release Identity across wheel/sdist/Git form, repository/distribution/version sensitivity, excluded source/hash/URL fields, manifest no self digest, compatibility no self/source/container fields, and public API signatures. Test that `agent_stack.release.kernel` exports only the Task 1-3 release callables/types and cannot import `agent_stack.cli`, reconcile, runtime, or route modules.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/contracts/release/test_release_api.py tests/contracts/release/test_release_kernel_boundary.py tests/property/release/test_release_identity.py -q`
Expected: FAIL because release package is absent.

- [ ] **Step 3: Implement immutable release models and identity**

Only repository_id, distribution_name, version enter Release Identity. Define the release-kernel public module as a leaf API; Tasks 2-3 fill its verifier/compatibility callables without importing late lifecycle composition.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/contracts/release/test_release_api.py tests/contracts/release/test_release_kernel_boundary.py tests/property/release/test_release_identity.py -q && uv run ruff check src/agent_stack/release tests/contracts/release tests/property/release && uv run mypy src/agent_stack/release`
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
- Produces: release-kernel `verify_release_manifest(locator, packaged_policy)` and `VerifiedRelease` evidence consumable before late lifecycle composition.
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
- Produces: release-kernel classify_compatibility(), select_candidate_runtime(), and statically verified source-release metadata evidence for workspace migration without source-code execution.
- Consumes: verified current/target releases, local-state contract, static source distribution metadata.

- [ ] **Step 1: RED tests**

Cover candidate-owned forward edge, current-owned rollback edge, reverse-only ahead, neither diverged, missing evidence, invalid authenticated schema exit 30, target bundle identities, local-state/layout/schema migrations, no URL/hash/source/self digest, source archive inspection without import/execute, no retained-runtime witness.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/unit/release/test_compatibility.py tests/property/release/test_compatibility_graph.py tests/integration/release/test_source_static_metadata.py -q`
Expected: FAIL on missing graph implementation.

- [ ] **Step 3: Implement exact directed classification**

No semantic version ordering and no implied patch/minor compatibility.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/unit/release/test_compatibility.py tests/property/release/test_compatibility_graph.py tests/integration/release/test_source_static_metadata.py tests/contracts/release/test_release_kernel_boundary.py -q`
Expected: all relationship dimensions match Core diagnostics and the release kernel remains a leaf import boundary.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/release/compatibility.py compatibility/releases.yaml tests
git commit -m "Add directed release compatibility"
~~~

## Release Kernel Component Gate

Stop Lifecycle execution after Task 3 and run:

~~~bash
uv run pytest tests/contracts/release/test_release_api.py tests/contracts/release/test_release_kernel_boundary.py tests/property/release/test_release_identity.py tests/unit/release/test_trust_policy.py tests/integration/release/test_manifest_verification.py tests/unit/release/test_compatibility.py tests/property/release/test_compatibility_graph.py tests/integration/release/test_source_static_metadata.py -q
uv run ruff check src/agent_stack/release tests/contracts/release tests/unit/release tests/integration/release tests/property/release
uv run mypy src/agent_stack/release
~~~

Expected: PASS and `release-kernel component-complete`. This unlocks Renderer/Runtime component waves only. Do not run Lifecycle Task 4, claim Lifecycle completion, build release artifacts, or publish until Renderer, Runtime, and Route are integration-complete.

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
- Consumes: all real Core/Provider/Renderer/Runtime/Route APIs and errors without redefining them. This task starts only after the Renderer/Runtime/Route integration-complete gates.

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

### Task 6: Freeze provenance, full licenses, and notices before artifact build

**Files:**
- Create: src/agent_stack/release/provenance.py
- Create: schemas/release/provenance-lock.v1.json
- Create: release/provenance-lock.json
- Create: tools/release/generate_notices.py
- Create: LICENSES/PyYAML-6.0.2.txt
- Create: LICENSES/fastjsonschema-2.21.1.txt
- Create: THIRD_PARTY_NOTICES.md
- Test: tests/contracts/release/test_provenance_inventory.py
- Test: tests/packaging/test_notices.py

**Interfaces:**
- Produces: FrozenProvenanceInventory plus complete `LICENSES/` and `THIRD_PARTY_NOTICES.md` inputs that must exist before any final distribution build.
- Consumes: Core `vendor/runtime-vendor-lock.json` and source licenses, Provider provenance, complete first-party/runtime-visible-unit inventory, and projected artifact provenance.

- [ ] **Step 1: RED provenance checks**

Test every upstream, vendored, generated, and projected unit maps to exact source/version/archive hash/per-file hash/SPDX/modification/full-license records. Assert PyYAML 6.0.2 and fastjsonschema 2.21.1 source hashes, installed private namespaces, namespace-relocation modification notices, exact license bytes, no unregistered vendor file, deterministic notice ordering, and failure on missing/ambiguous provenance. Assert the frozen inventory contains no wheel/sdist/container hash that would create a build cycle.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/contracts/release/test_provenance_inventory.py tests/packaging/test_notices.py -q`
Expected: FAIL because the provenance lock, full licenses, notices, and generator do not exist.

- [ ] **Step 3: Implement deterministic provenance aggregation**

Generate the closed provenance lock, full license copies, and notices from frozen Core/Provider/artifact records. Do not infer a license from a component name and do not inspect a built distribution. The generated files are inputs to Task 7, not post-build patches.

- [ ] **Step 4: Verify GREEN**

Run: `uv run python tools/vendor/sync_runtime_vendor.py --check && uv run pytest tests/contracts/release/test_provenance_inventory.py tests/packaging/test_notices.py -q`
Expected: complete deterministic provenance and full-license inputs pass before any final wheel/sdist exists; a missing or changed record blocks.

- [ ] **Step 5: Commit**

~~~bash
git add src/agent_stack/release/provenance.py schemas/release/provenance-lock.v1.json release/provenance-lock.json tools/release/generate_notices.py LICENSES THIRD_PARTY_NOTICES.md tests/contracts/release/test_provenance_inventory.py tests/packaging/test_notices.py
git commit -m "Freeze release provenance and license inputs"
~~~

### Task 7: Build final distributions, compute render digest, and run release gates

**Files:**
- Modify: pyproject.toml
- Create: src/agent_stack/release/gates.py
- Create: tools/release/build_artifacts.py
- Create: tools/release/compute_render_digest.py
- Test: tests/packaging/test_self_contained_wheel.py
- Test: tests/packaging/test_package_data.py
- Test: tests/packaging/test_distribution_render_digest.py
- Test: tests/packaging/test_python_matrix_contract.py
- Test: tests/packaging/test_provenance.py
- Test: tests/packaging/test_vendor_payload.py
- Test: tests/integration/release/test_release_gates.py

**Interfaces:**
- Produces: build_release_artifacts(), compute_distribution_render_digest(), run_release_gates(), and the final gated wheel/sdist byte set consumed by publication.
- Consumes: all package/render data plus Task 6's frozen provenance inventory, `LICENSES/`, notices, Core vendor lock, and verified detached-manifest substitutions. No later task may mutate distribution contents.

- [ ] **Step 1: RED final-artifact checks**

Before build code, test empty wheel Requires-Dist, all package data, full licenses/notices/provenance present, detached manifest absent, wheel/sdist/Git logical inventory parity, scoped digest exclusions, repeated-root render equality, Python 3.11-3.14 metadata, and all 13 release gates. Extract wheel and sdist and assert every `agent_stack._vendor` path and byte hash exactly equals `vendor/runtime-vendor-lock.json`, with no unregistered file or top-level public vendor package.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/packaging/test_self_contained_wheel.py tests/packaging/test_package_data.py tests/packaging/test_distribution_render_digest.py tests/packaging/test_python_matrix_contract.py tests/packaging/test_provenance.py tests/packaging/test_vendor_payload.py tests/integration/release/test_release_gates.py -q`
Expected: FAIL because final build/digest/gate code and final artifacts do not exist.

- [ ] **Step 3: Implement final build, digest, and gate tools**

Fix bundle/provenance/license roots before build, build wheel/sdist once from those committed inputs, compute distribution hashes/sizes only after final bytes exist, and write `dist/release-artifact-set.json` with the exact paths, sizes, and hashes. Run gates against that exact artifact set. Do not create the detached manifest inside source distributions and do not regenerate notices or licenses after build.

- [ ] **Step 4: Verify GREEN**

Run:

~~~bash
uv run python tools/vendor/sync_runtime_vendor.py --check
uv build
uv run pytest tests/packaging/test_self_contained_wheel.py tests/packaging/test_package_data.py tests/packaging/test_distribution_render_digest.py tests/packaging/test_python_matrix_contract.py tests/packaging/test_provenance.py tests/packaging/test_vendor_payload.py tests/integration/release/test_release_gates.py -q
~~~

Expected: final wheel/sdist contain the frozen licenses, notices, provenance, and exact vendor bytes; render digests match and all release gates pass on those same bytes.

- [ ] **Step 5: Commit**

~~~bash
git add pyproject.toml src/agent_stack/release/gates.py tools/release tests/packaging tests/integration/release/test_release_gates.py
git commit -m "Build and gate final release distributions"
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
- Consumes: Task 7's gated `dist/release-artifact-set.json` and exact final artifact bytes; publication may not rebuild or mutate them.

- [ ] **Step 1: RED workflow tests**

Parse workflows and assert Python 3.11-3.14, provenance/licenses/notices frozen before build, artifact-based tests, release gates against the exact final artifact set before detached-manifest generation, no manifest-before-build, immutable release verification, exact asset re-fetch/hash, no asset replacement, and required gate dependencies.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/contracts/release/test_ci_workflows.py tests/integration/release/test_publication_sequence.py -q`
Expected: FAIL because workflows or scripts are absent.

- [ ] **Step 3: Implement deterministic workflow**

Use immutable version/tag inputs only. Consume Task 7's already gated final wheel/sdist without rebuilding or modifying them, generate release-manifest.json afterward, publish once, require immutable status, re-download, and verify.

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
uv run python tools/release/build_artifacts.py --verify-existing dist/release-artifact-set.json
~~~

Expected: all pass on every supported Python job; acceptance matrix reports 64/64 and the final artifact-set hashes still match the Task 7 bytes without rebuilding.

- [ ] **Step 5: Commit**

~~~bash
git add tests/e2e tests/fixtures/e2e
git commit -m "Close release acceptance matrix"
~~~

## Global Validation

Run the release-kernel gate after Task 3, then stop until Renderer/Runtime/Route are integration-complete. After Task 9, run the complete suite from clean final wheel, sdist, and Git checkout environments. Verify vendor-lock bytes, full licenses/notices/provenance, empty Requires-Dist, and absence of release-manifest.json inside distributions. Run release gates twice against the same artifact hashes and verify the publication workflow with a disposable immutable test repository before production release.

## Implementation Constraint Prompt

~~~text
Read the approved Lifecycle/Release spec and this plan. Execute Tasks 1-3 after Core/Providers, stop at release-kernel component-complete, and do not begin Tasks 4-9 until Renderer/Runtime/Route are integration-complete. Use strict TDD for behavior and prewritten deterministic checks for generated release artifacts. Keep CLI composition thin and never redefine domain semantics/errors. Freeze provenance/full licenses/notices before building final wheel/sdist; gate those exact final bytes before detached-manifest generation, keep runtime Requires-Dist empty, support Python 3.11-3.14, use exact directed compatibility, and verify immutable GitHub release assets after publication. Run the complete AC-01–AC-64 suite before completion.
~~~

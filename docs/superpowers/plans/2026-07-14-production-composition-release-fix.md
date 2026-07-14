# Production Composition Release Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the approved production integration wave: packaged bundle closure, 17 real owners, atomic first-init local state, a protected launcher channel, and a no-injection installed-wheel acceptance chain.

**Architecture:** Add a packaged production bundle containing the exact Core inputs and neutral render sources already required by the approved Resolver/Renderer contracts. A single composition module loads and validates those bytes, derives release authority only from `VerifiedRelease`, scans task state through the real Runtime scanner, then calls the existing `resolve → render → plan_reconcile → apply_plan` pipeline. Console handlers remain thin and never redefine ownership, task-gate, CAS, or release policy.

**Tech Stack:** Python 3.11-3.14, immutable dataclasses/mappings, vendored YAML/JSON schema support, pytest, Ruff, mypy, Hatch wheel/sdist build.

## Global Constraints

- No local manifest, environment override, mutable tag, alternate index, source build, or Python-download trust path.
- `bootstrap` and `init` verify the immutable detached release before target-project writes.
- Production code contains no fake ports, fallback owner registry, or special-case bypass.
- Dry-run performs zero target-project writes.
- Existing `.trellis/`, `.specify/`, and user-owned bytes/modes are preserved.
- The second unchanged sync is a strict no-op with zero file or Manifest mutation.
- `heavy-development-router` remains the only heavy orchestrator; Superpowers planner/executor remain undiscoverable.

---

### Task 1: Freeze the packaged production Resolver/render inputs

**Files:**
- Create: `profiles/default.yaml`
- Create: `catalog/workflow-components.yaml`
- Create: `catalog/workflow.lock`
- Create: `catalog/runtime-surfaces.yaml`
- Create: `catalog/runtime-units.yaml`
- Create: `templates/platforms/codex/AGENTS.md.tmpl`
- Create: `templates/platforms/codex/SKILL.md.tmpl`
- Create: `templates/platforms/codex/codex-wrapper.tmpl`
- Replace: `artifact-definitions/platforms/codex.yaml` with three closed single-source definitions: `codex-agents.yaml`, `codex-skill.yaml`, and `codex-wrapper.yaml`
- Modify: `pyproject.toml`
- Test: `tests/contracts/core/test_production_bundle.py`

**Interfaces:**
- Produces `load_production_bundle(data_root: Path) -> ProductionBundle` inputs with exact schema IDs and closed paths.
- Neutral templates contain only Resolver-approved substitutions and never contain detached manifest bytes.

- [ ] Write a failing contract test that builds the wheel and proves every production input and every artifact-definition source exists exactly once.
- [ ] Verify RED because the profile, Core catalog/lock, surfaces, units, and templates are absent.
- [ ] Add the minimal Codex v0.1 documents derived from the frozen platform catalog, route policy, artifact definitions, launcher contract, and approved leaf policy.
- [ ] Add all new roots to wheel/sdist packaging and release bundle inventories.
- [ ] Verify schema validation, reference closure, surface coverage, and wheel inventory GREEN.
- [ ] Commit `Freeze production composition bundle`.

### Task 2: Compose verified init and sync through existing domain owners

**Files:**
- Create: `src/agent_stack/reconcile/production.py`
- Modify: `src/agent_stack/reconcile/commands.py`
- Modify: `src/agent_stack/cli/production.py`
- Test: `tests/integration/reconcile/test_production_composition.py`

**Interfaces:**
- Consumes `VerifiedRelease`, `ProductionBundle`, `NormativeTaskScanner`, `resolve`, `render`, `plan_reconcile`, and `apply_plan`.
- Produces `compose_init(command, release, *, apply: bool) -> Mapping[str, object]` and `compose_sync(command, release, *, apply: bool) -> Mapping[str, object]`.

- [ ] Write a failing init integration test with a verified-release value and a real temporary Git project containing pre-existing `.trellis/`, `.specify/`, and user files.
- [ ] Verify RED on the current fixed `AWP_RECONCILE_RECOVERY_REQUIRED` placeholder.
- [ ] Load and validate the packaged bundle; derive release/profile/lock/artifact/task evidence without test injection.
- [ ] Bind the real scanner, renderer, ownership planner, journal/CAS apply, Manifest-last commit, workspace/replay initialization, and project launcher generation.
- [ ] Verify init dry-run is byte-for-byte read-only and init apply creates only authorized managed/overlay files.
- [ ] Write a failing sync test over the initialized project, including a first no-change dry-run and two no-change applies.
- [ ] Implement sync planning from committed Manifest/workspace state and return `no_op: true` without a transaction or Manifest generation change when candidate bytes are identical.
- [ ] Verify restorative repair remains separate and ordinary sync never overwrites user-owned content.
- [ ] Commit `Bind production init and sync composition`.

### Task 3: Make first init one atomic project-plus-local-state transaction

**Files:**
- Modify: `src/agent_stack/reconcile/apply.py`
- Modify: `src/agent_stack/reconcile/journal.py`
- Modify: `src/agent_stack/reconcile/recovery.py`
- Modify: `src/agent_stack/runtime/workspace.py`
- Test: `tests/concurrency/reconcile/test_first_init_local_state.py`

**Interfaces:**
- Consumes the init saved-plan fields for project/workspace identity and empty replay-ledger digest.
- Produces one recoverable transaction whose commit establishes Manifest, `workspace.json`, and `approval-replay.json` as a valid set.

- [ ] Write crash tests at candidate creation, managed-file apply, workspace rename, replay rename, Manifest rename, and cleanup.
- [ ] Verify RED because current `apply_plan` commits only the Manifest and managed files.
- [ ] Record local-state preimages/candidates and their CAS conditions in the lifecycle journal before target mutation.
- [ ] Apply workspace/replay candidates before the final Manifest commit while retaining rollback authority.
- [ ] Define the final Manifest rename as acceptance of the complete project/local contract; post-commit recovery is cleanup-only.
- [ ] Verify rollback never recreates an empty ledger over existing/corrupt state and no crash leaves a valid Manifest with missing local state.
- [ ] Commit `Make first init local state atomic`.

### Task 4: Close the reserved launcher-to-CLI channel

**Files:**
- Modify: `src/agent_stack/cli/parser.py`
- Modify: `src/agent_stack/__main__.py`
- Modify: `src/agent_stack/runtime/bootstrap.py`
- Test: `tests/contracts/runtime/test_launcher_internal_channel.py`

**Interfaces:**
- Produces `parse_launcher_envelope(argv) -> (LauncherInvocation, public_argv)` before the public argparse parser.
- Public `parse_cli_args` never exposes reserved options as ordinary command options.

- [ ] Write RED tests for one valid launcher envelope and for public attempts to add, repeat, override, reorder, or mix reserved fields.
- [ ] Add rejection tests for unknown fields, relative paths, control characters, excessive lengths, duplicate config roots, and unsupported versions.
- [ ] Parse the reserved prefix only when the invocation contains the complete schema-fixed launcher envelope and normalized project path.
- [ ] Strip the verified envelope before invoking the closed public parser and pass it into production context composition.
- [ ] Verify a direct public invocation containing any reserved option still exits 2.
- [ ] Commit `Protect launcher internal CLI channel`.

### Task 5: Bind all 17 production owners to reachable domain implementations

**Files:**
- Modify: `src/agent_stack/cli/production.py`
- Modify: `src/agent_stack/runtime/commands.py`
- Modify: `src/agent_stack/release/commands.py`
- Modify: `src/agent_stack/route/commands.py`
- Test: `tests/contracts/cli/test_production_composition.py`

**Interfaces:**
- `production_owner_bindings()` remains key-equal to `OWNER_MATRIX`.
- Every binding calls its owning domain implementation or fails because verified domain input/state is absent; no fixed-failure adapter is registered.

- [ ] Add a structural reachability test that rejects aliases to fixed-failure helpers and imports every binding target from the final wheel.
- [ ] Add representative initialized-project tests for workspace, route, runtime load, task mutation, recovery, lifecycle, and reconcile owners.
- [ ] Replace fixed-failure adapters with input loaders that validate project Manifest/workspace/journal/integration bytes and call the existing domain service.
- [ ] Verify missing or malformed authority returns the owning closed failure without empty/default object substitution.
- [ ] Commit `Bind all production domain owners`.

### Task 6: Add final-wheel black-box acceptance with verified release evidence

**Files:**
- Modify: `tests/e2e/test_console_entrypoint.py`
- Create: `tests/e2e/test_production_dogfood.py`
- Modify: `tests/e2e/test_acceptance_matrix.py`

**Interfaces:**
- Uses the real console entry point without `VerifiedRuntimeContext` injection.
- Replaces HTTPS only at the process boundary with a deterministic immutable GitHub metadata/manifest server fixture; no production trust override is introduced.

- [ ] Write a failing subprocess test for `bootstrap → init --dry-run → init → doctor → test-routing → sync --dry-run → sync → sync` from the built wheel.
- [ ] Verify RED at actual init apply before changing production composition.
- [ ] Serve canonical immutable release metadata and detached manifest bytes at the policy-derived endpoints while retaining the real packaged trust policy and release digest verification.
- [ ] Assert JSON/exit contracts, 17 owner bindings, default/heavy routes, sole heavy orchestrator, hidden planner/executor, preserved user files, and strict second-sync no-op.
- [ ] Keep the existing unpublished-release test proving bootstrap/init exit 30 with zero writes when evidence is absent.
- [ ] Run the complete acceptance matrix from Git checkout, wheel, and sdist.
- [ ] Commit `Gate release on real console dogfood`.

### Task 7: Reinstate release gates only after production integration passes

**Files:**
- Modify: `src/agent_stack/release/gates.py`
- Modify: `tests/integration/release/test_release_gates.py`
- Modify: `tests/e2e/test_acceptance_matrix.py`

**Interfaces:**
- Adds a production-integration prerequisite to the existing 13-gate result without weakening any existing gate.

- [ ] Write RED proving the current component-only artifact cannot report release gates passed.
- [ ] Bind the prerequisite to packaged bundle validation, 17-owner reachability, first-init transaction tests, launcher-channel tests, and installed-wheel acceptance evidence.
- [ ] Require all original 13 gates plus production integration before `status: passed`.
- [ ] Commit `Gate release on production integration`.

### Task 8: Re-freeze and publish one immutable v0.1.0

**Files:**
- Modify: `tests/fixtures/e2e/releases/final-artifact-contract.json`
- Generate detached only: `dist/release-manifest.json`

**Interfaces:**
- Consumes one clean final commit and produces one tag, wheel, sdist, detached manifest, GitHub immutable release, and post-release evidence set.

- [ ] Run Ruff, mypy, and the complete pytest suite from the final commit.
- [ ] Fast-forward `main`, create local `v0.1.0`, and verify tag equals HEAD.
- [ ] Build wheel/sdist once; freeze wheel, sdist, render, provenance, and artifact-set hashes.
- [ ] Generate the detached manifest from the actual owner/repository/tag/HEAD/artifact hashes.
- [ ] Create public `swl007007/agent-workflow-pack`, configure `origin`, and push `main` plus `v0.1.0`.
- [ ] Publish the exact frozen assets, mark the release immutable, re-download all assets, and verify hashes.
- [ ] Execute the canonical bootstrap command in a new project and repeat the full console dogfood chain.
- [ ] Preserve feature branches/worktrees until formal release acceptance.

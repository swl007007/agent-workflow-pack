# Agent Workflow Pack Operations Manual

This manual covers trusted installation, project operation, diagnostics, routing,
recovery, upgrades, and release verification for `agent-workflow-pack` v0.1.

## 1. Trust boundary

The production trust root is the immutable GitHub release repository:

```text
github.com/swl007007/agent-workflow-pack
```

The release tag, detached manifest, wheel, sdist, source commit, bundle roots, asset
URLs, and hashes must agree. A local tag or candidate manifest can validate structure
before publication, but it is not immutable-release evidence.

Never add or use:

- a `--local-manifest` production option;
- an environment variable that overrides release identity;
- a local or arbitrary manifest URL;
- `latest` or unconstrained package resolution;
- replacement assets under an existing version.

## 2. Prerequisites

Confirm the following before installation:

```bash
git --version
uv --version
python3 --version
```

Python must satisfy `>=3.11,<3.15`. The bootstrap path must not download Python.

The canonical release command uses an isolated `uvx` environment with the equivalent
constraints:

```text
--isolated --no-config --no-env-file --no-index
--keyring-provider disabled --no-sources --no-build
--no-python-downloads
```

It selects one exact wheel URL with a SHA-256 fragment. Copy that complete command only
from an accepted immutable release. The `v0.1.0` through `v0.1.5` publications or candidates are failed
evidence and must not be used; no accepted release currently exists.

## 3. First installation

Use a clean project checkout or a disposable copy for the first run. Record the initial
state if the project already contains `.trellis/`, `.specify/`, agent instructions, or
other user-owned files.

Run the canonical bootstrap command from the release, then:

```bash
agent-stack bootstrap --json
agent-stack init --dry-run --json
agent-stack init --json
```

Review the dry-run before apply. A dry-run must not create `.agent-workflow/`, a lock,
workspace identity, maintenance marker, task state, or generated target files.

After successful initialization, use the managed project launcher for ordinary work:

```bash
.agent-workflow/bin/agent-stack doctor --json
```

If immutable release metadata or the detached manifest cannot be verified, bootstrap
and init must stop with a release/supply-chain error before target-project writes.
`AWP_CLI_OWNER_UNAVAILABLE` is not an acceptable production failure for a supported
command.

## 4. Initial acceptance sequence

Run the complete sequence in order:

```bash
agent-stack bootstrap --json
agent-stack init --dry-run --json
agent-stack init --json
agent-stack doctor --json
agent-stack test-routing --json
agent-stack sync --dry-run --json
agent-stack sync --json
agent-stack sync --json
```

Acceptance conditions:

1. Ordinary work routes to `native-light`.
2. Heavy signals route to `speckit-superpowers`.
3. `heavy-development-router` is the only top-level orchestrator.
4. Superpowers planner and executor are not exposed.
5. Only TDD, debugging, verification, and review leaf capabilities are projected.
6. The second unchanged sync is a strict no-op.
7. Existing `.trellis/`, `.specify/`, and user-owned files retain their bytes and modes.
8. No command downloads an unbound dependency, source build, or Python distribution.

## 5. Diagnostics

Normal diagnostics are read-only:

```bash
.agent-workflow/bin/agent-stack doctor --json
```

Use the explicit write probe only when a filesystem capability must be measured:

```bash
.agent-workflow/bin/agent-stack doctor --write-probe --json
```

A write probe uses bounded temporary paths and CAS cleanup. If interrupted residue
remains, follow the reported recovery command instead of deleting control files by hand.

Useful checks include:

- initialized Manifest and workflow-lock agreement;
- runtime launcher and descriptor authority;
- workspace registration or migration requirement;
- active tasks and unfinished transactions;
- harness capability/configuration evidence;
- trust-policy repository and digest;
- resolved uv and Python prerequisites.

## 6. Routing verification

Run:

```bash
.agent-workflow/bin/agent-stack test-routing --json
```

Expected summary:

```json
{
  "default_route": "native-light",
  "heavy_route": "speckit-superpowers",
  "heavy_orchestrator": "heavy-development-router",
  "superpowers_planner_exposed": false,
  "superpowers_executor_exposed": false
}
```

Use route calculation only through the project launcher. Signals for executable
operations must agree with the task intent; signal extraction is routing input, not an
issuer-authentication security boundary.

## 7. Synchronization and repair

Preview ordinary synchronization:

```bash
.agent-workflow/bin/agent-stack sync --dry-run --json
```

Apply only the reviewed plan:

```bash
.agent-workflow/bin/agent-stack sync --json
```

For restorative repair:

```bash
.agent-workflow/bin/agent-stack sync --repair --dry-run --json
.agent-workflow/bin/agent-stack sync --repair --json
```

Repair may restore a task-pinned expected digest. It must not silently change an active
task to a different contract. Protected paths, user-owned files, symlinks, stale CAS
evidence, or changed task-quiescence evidence block the operation.

## 8. Workspace registration and migration

A fresh clone has committed project control files but lacks ignored local workspace
state. Register it with:

```bash
.agent-workflow/bin/agent-stack workspace register --json
```

After pulling a project Manifest with a different directed local-state contract:

```bash
.agent-workflow/bin/agent-stack workspace migrate --json
```

Migration is allowed only through an exact verified compatibility edge. In v0.1, any
checkout-visible non-archived task or unfinished task transaction blocks migration.
Finish and archive tasks in the source checkout first. Workspace migration changes
ignored local state only; it does not rewrite tasks or the committed Manifest.

## 9. Task operations

Task operations are transaction- and revision-bound. Representative commands are:

```bash
.agent-workflow/bin/agent-stack task admit --task-ref <ref> --json
.agent-workflow/bin/agent-stack task claim --task-ref <ref> --revision <n> --executor <id> --json
.agent-workflow/bin/agent-stack task transition --task-ref <ref> --revision <n> --to completed --json
.agent-workflow/bin/agent-stack task archive --task-ref <ref> --revision <n> --json
```

Do not edit integration state, replay ledgers, journals, pointers, or task outbox files
manually. A task has an immutable UUID identity; a human-readable ref may be reused only
under the task service's identity and archive rules.

## 10. Recovery

When a command reports recovery-required, use the exact journal type and ID from the
diagnostic. Examples:

```bash
.agent-workflow/bin/agent-stack recover --transaction <id> --resume --json
.agent-workflow/bin/agent-stack recover --transaction <id> --rollback --json
.agent-workflow/bin/agent-stack recover --workspace-registration <id> --resume --json
.agent-workflow/bin/agent-stack recover --workspace-migration <id> --rollback --json
.agent-workflow/bin/agent-stack task recover --transaction <id> --resume --json
```

Recovery never guesses between resume and rollback. Do not remove maintenance markers,
journals, candidates, backups, or replay tombstones manually. Post-commit recovery is
cleanup-only; committed state is not rolled back.

## 11. Upgrade

Preview an exact target release:

```bash
.agent-workflow/bin/agent-stack upgrade --to <version> --dry-run --json
```

Apply only after the candidate detached manifest and directed compatibility edge verify:

```bash
.agent-workflow/bin/agent-stack upgrade --to <version> --json
```

The lifecycle gate scans the union of current and candidate Trellis layouts. Active-task
policy, task surfaces, unfinished transactions, local-state migration, ownership, and
filesystem CAS must all pass before commit.

## 12. Error categories

The JSON envelope always includes `command`, `status`, `exit_code`, `result`, `errors`,
and `warnings`.

Common categories:

- exit `2`: usage or closed-contract input error;
- exit `20`-`23`: ownership, workspace, task, or recovery blocker;
- exit `30`: release, supply-chain, runtime binding, or bootstrap prerequisite failure;
- exit `40`: stale CAS or changed quiescence evidence;
- exit `70`: unexpected internal composition failure.

Treat exit 30 as a trust failure. Do not bypass it with alternate URLs, local manifests,
mutable tags, or environment overrides.

## 13. Release operator procedure

Release only from a clean commit whose final tag points exactly to `HEAD`:

```bash
git status --porcelain
git rev-parse HEAD
git rev-list -n 1 v0.1.6
```

Required sequence:

1. Run Ruff, mypy, and the complete pytest suite.
2. Build wheel and sdist once from the tagged commit.
3. Freeze wheel, sdist, render, provenance, and artifact-set digests.
4. Generate detached `release-manifest.json` from the actual repository, tag, HEAD, and
   frozen artifact hashes.
5. Create the GitHub release and upload those exact bytes.
6. Confirm repository release immutability was enabled before creation, publish the
   asset-complete draft, and verify the resulting release reports `immutable: true`.
7. Re-download every asset and compare hashes.
8. Run the canonical bootstrap command in a new environment and complete the acceptance
   sequence in Section 4.

Never rebuild after freezing and then reuse old hashes. Never move a published tag or
replace published assets. `v0.1.0` through `v0.1.5` are already recorded as failed; any
failure after the `v0.1.6` publication must use a new `v0.1.7` Release Identity.

## 14. Evidence to retain

Keep the following through formal release completion:

- source commit and tag;
- wheel, sdist, manifest, render, and artifact-set hashes;
- complete test/lint/type-check output;
- pre-publication dogfood logs;
- GitHub immutable-release metadata;
- re-downloaded asset hashes;
- post-publication console dogfood logs;
- release notes, provenance lock, licenses, and third-party notices;
- feature branch/worktree until the release is accepted.

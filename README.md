# Agent Workflow Pack

Agent Workflow Pack installs a deterministic, project-local workflow control plane for
Codex, Claude Code, OpenCode, Trellis, Spec Kit, and selected Superpowers disciplines.
It keeps routing, generated files, task state, recovery, and release identity under one
versioned contract.

The default route is intentionally lightweight. Ordinary changes stay on `native-light`.
Tasks enter `speckit-superpowers` only when explicit heavy-work signals match the frozen
route policy, and `heavy-development-router` remains the sole top-level orchestrator.
Superpowers contributes only allowlisted leaf disciplines such as TDD, debugging,
verification, and review; its planner and executor are not automatically exposed.

## Release status

**v0.1.8 is the first accepted immutable release.**

Versions `0.1.0` through `0.1.7` are retained as failed publications or candidates. Their tags, release
metadata, and assets must not be moved, replaced, or treated as installation authorities.

The canonical first-install command is published with the release and binds:

- repository and exact tag;
- wheel URL and SHA-256;
- detached `release-manifest.json`;
- source commit and bundle roots;
- an isolated `uvx` invocation with no index, source build, or Python download fallback.

Use the command copied from the immutable release rather than constructing a `latest`
installation command.

## Requirements

- POSIX `sh` and `env`;
- a release-supported `uv`/`uvx`;
- local Python `>=3.11,<3.15`;
- Git for project identity and release operations;
- network access to the fixed GitHub release endpoints for first installation.
- WSL-native filesystem supported; Windows-mounted DrvFs not officially supported in
  v0.1.x.

The runtime wheel is self-contained and has no runtime `Requires-Dist` dependencies.

## Quick start

After an accepted release publishes a canonical bootstrap command, run it and then enter
the target project and execute:

```bash
agent-stack bootstrap --json
agent-stack init --dry-run --json
agent-stack init --json
agent-stack doctor --json
agent-stack test-routing --json
agent-stack sync --dry-run --json
agent-stack sync --json
```

The second unchanged `sync` must be a strict no-op. Existing user-owned files and
pre-existing `.trellis/` or `.specify/` content must not be overwritten.

For project-local use after initialization, invoke the managed launcher:

```bash
.agent-workflow/bin/agent-stack doctor --json
```

## Routing expectations

`agent-stack test-routing --json` should report:

- `default_route: native-light`;
- `heavy_route: speckit-superpowers`;
- `heavy_orchestrator: heavy-development-router`;
- `superpowers_planner_exposed: false`;
- `superpowers_executor_exposed: false`.

Trellis task state, SDD artifacts, and lightweight micro-plans do not depend on a
Superpowers planner.

## Safety model

Agent Workflow Pack fails closed when release evidence, ownership, task state,
compatibility, or filesystem CAS evidence is unavailable. It does not treat a hostile
user-writable checkout as a trusted execution environment. If a checkout may be
tampered with, use the canonical command from the immutable release for read-only
verification.

Normal `doctor` is read-only. Write probes are explicit. Active tasks, unfinished
transactions, incompatible workspace contracts, protected paths, and user-owned files
are enforced by their owning services rather than bypassed by the CLI.

## Documentation

- [Operations manual](docs/operations-manual.md)
- [Supported environments](docs/support-matrix.md)
- [FAQ](docs/faq.md)
- [Architecture specification](docs/superpowers/specs/2026-07-13-agent-workflow-pack-design.md)
- [Third-party notices](THIRD_PARTY_NOTICES.md)

## Development verification

```bash
uv sync
uv run ruff check src tests tools
uv run mypy src tools
uv run pytest -q
```

Release artifacts are generated only from a clean, exactly tagged commit. Never rebuild
or replace assets after publication.

## License

Apache-2.0. Vendored dependency licenses are distributed under `LICENSES/`; provenance
and modification notices are recorded in `THIRD_PARTY_NOTICES.md` and the release
provenance lock.

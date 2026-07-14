# v0.1.5 Canonical First-Install Closure Implementation Plan

> **For agentic workers:** Execute inline under the existing heavy-development-router authority. Superpowers is a leaf TDD discipline, not a second orchestrator.

**Goal:** Publish `v0.1.5` only through an exact-tag automated workflow whose immutable release body contains and verifies the deterministic canonical first-install command.

**Architecture:** Keep manifest v1 unchanged. Add a pure release renderer, derive one deterministic body, pass it into draft creation, verify full remote equality, and add a dedicated prepublication gate.

**Tech Stack:** Python 3.11-3.14, POSIX sh, pytest, GitHub Actions, GitHub Releases API.

## Task 1: Record immutable failed release

- [ ] Add structured and narrative `v0.1.4` failure records and update README.
- [ ] Validate JSON and documentation assertions.
- [ ] Commit.

## Task 2: Canonical first-install renderer

- [ ] Add RED tests for authority derivation, invalid inputs, injection resistance, determinism, `sh -n`, and state independence.
- [ ] Implement `render_canonical_first_install_shell(verified_manifest, manifest_digest) -> str`.
- [ ] Run focused tests and commit.

## Task 3: Deterministic release body and publication protocol

- [ ] Add RED tests for exact body generation and `create_release_once(tag, source_commit, body)`.
- [ ] Generate manifest, command and body before draft creation; publish exact assets once.
- [ ] Extend postpublication verifier to compare the complete body and emit `canonical_first_install_command_digest`.
- [ ] Run focused tests and commit.

## Task 4: Exact-tag workflow and fourteenth gate

- [ ] Add RED contract tests for full tag checkout and preflight in both jobs.
- [ ] Add the `canonical-first-install-publication` release gate.
- [ ] Update workflow and gate expectations; run focused tests and commit.

## Task 5: Release identity, complete verification, and publication

- [ ] Set package and documentation release identity to `0.1.5` while retaining failed-release warnings.
- [ ] Run Ruff, mypy, complete pytest, reproducible artifact build, and all 14 gates.
- [ ] Fast-forward main, create/push `v0.1.5`, and run only the automated release workflow.
- [ ] Verify immutable remote body/assets and execute fresh canonical-command dogfood.


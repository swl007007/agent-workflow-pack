# v0.1.7 Durable First-Install Handoff Progress

- Branch: `fix/v0.1.7-durable-handoff`
- Worktree: `/tmp/awp-v015-canonical-first-install`
- Approved design: `docs/superpowers/specs/2026-07-14-v015-canonical-first-install-design.md`
- Implementation plan: `docs/superpowers/plans/2026-07-14-v015-canonical-first-install.md`
- Current task: durable-handoff final verification before release gate
- Baseline: focused publication/workflow tests passed at `9398465`
- Release rule: no manual publication fallback; postpublication failure freezes `v0.1.7` and advances to `v0.1.8`.
- Completed: v0.1.6 failed-release record, canonical bootstrap-to-init handoff, durable launcher probe, 15th gate, and automated postpublication dogfood contract.
- Focused verification: 14 tests passed; Ruff and mypy passed; installed-wheel production dogfood passed.
- Full verification: Ruff passed; mypy passed; 706 tests passed; 15/15 prepublication gates passed.
- Frozen candidate artifact set: `c244d8cf573f0d95387eadfdb5c946589a33673cb38e44684f2157162cf24bda`.
- Wheel: `30b9cf4130bef1324709323cf8172d5e5fa1cc8fd472fd67c81680622f790498`.
- sdist: `0a5d369943604d00ad2b535e9baa5d7d432ed0fb23aecf10ffda8353e950d7c3`.
- Render digest: `d3d6c3f08c1b09ca62be32efe0e8f53f0c6142c6410dd6bbfdfae6213e062718`.

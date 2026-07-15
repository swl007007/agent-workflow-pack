# v0.1.8 Release Closure Progress

- Branch: `main`
- Worktree: `/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Plan/agent-workflow-pack`
- Approved design: `docs/superpowers/specs/2026-07-14-v015-canonical-first-install-design.md`
- Implementation plan: `docs/superpowers/plans/2026-07-14-v015-canonical-first-install.md`
- Current task: completed; v0.1.8 accepted after immutable postpublication dogfood
- Baseline: focused publication/workflow tests passed at `9398465`
- Release rule: no manual publication fallback; postpublication failure freezes `v0.1.8` and advances to `v0.1.9`.
- Completed: v0.1.7 immutable failure diagnosis, modern uv/uvx parser fix, v0.1.8 immutable publication, asset re-verification, and durable-handoff dogfood.
- Focused verification: launcher/release suite passed (19 tests); installed-wheel production dogfood passed.
- Full verification: Ruff passed; mypy passed; 707 tests passed; 15/15 prepublication gates passed.
- Postpublication verification: workflow `29377537295` passed; canonical command digest `f0e5fd2cbe7d3074e66f1a6ff1927092a7d9663671dca298ba8af13283711bce`.
- Post-release CI closure: commit `38188cb` made unpublished-release console tests independent of the real GitHub release/API state; workflow `29377977839` passed on Python 3.11-3.14.
- Cleanup: merged feature and temporary release-fix worktrees were removed after formal acceptance; `main` is the only remaining worktree.
- Frozen candidate artifact set: `26082fcd30226667e49d6faf0dddef94f45c9db383034b2c06d5cd5e142db76a`.
- Wheel: `db85f06beff3a3188146e5234dd8e77022586259dd769adda1ba53ecc43a71da`.
- sdist: `491e38443b0e340ab95ae4a792dfb72adaeef0ed24fd02c30637aa74c2e10614`.
- Render digest: `6b73cb0e3a6532266bd95f8f9d449596727870ef1d0bea68605d934704c4a8df`.

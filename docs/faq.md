# Agent Workflow Pack FAQ

## Windows-mounted filesystems

### Can I use `/mnt/c` or another Windows-mounted path?

**v0.1.x does not guarantee support. Put the project in the WSL-native filesystem, such
as `/home/<user>/projects`.**

`/mnt/c`, `/mnt/d`, and similar paths normally use DrvFs. Its default configuration may
not preserve POSIX file permissions correctly, and its file locking, atomic replacement,
and case semantics may not satisfy Agent Workflow Pack's transaction-safety contract.
Typical symptoms include:

- initialization stopping at `probing`;
- permissions still appearing as `777` after `chmod 600` or `chmod 700`;
- an `AWP_FILESYSTEM_UNSUPPORTED` error;
- `.agent-workflow/bin/agent-stack` not being generated;
- repeated initialization attempts being unable to complete.

Use a WSL-native checkout:

```bash
cd ~/projects
git clone <repository-url>
cd <repository>
```

Access it from Windows at:

```text
\\wsl$\Ubuntu\home\<user>\projects\<repository>
```

Or open it from WSL:

```bash
code .
explorer.exe .
```

Enabling DrvFs `metadata` may allow some `/mnt/c` environments to pass the POSIX-mode
probe. It does not guarantee compatible advisory locking, atomic replacement, case, or
Unicode behavior. DrvFs therefore remains **experimental / best-effort** and mutation
commands may continue only after the complete live filesystem probe passes.

If init fails during `probing`, the command stops; it is not retrying in the background.
For v0.1.x, start again from a clean clone under `/home/<user>/...`. If the original
checkout contains uncommitted work, review and carry those changes into the new clone
without copying `.agent-workflow`. Do not repeatedly rerun init in the partially
initialized checkout on the unchanged DrvFs mount.

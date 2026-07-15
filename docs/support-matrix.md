# Supported Environments

This matrix defines the v0.1.x support boundary. All mutation-capable environments must
also pass the complete live filesystem probe; an environment label alone never bypasses
the probe.

## Runtime platforms

| Environment | v0.1.x status | Notes |
| --- | --- | --- |
| Linux | Supported | Requires POSIX `sh`, `env`, Git, supported `uv`/`uvx`, and Python `>=3.11,<3.15`. |
| WSL2 | Supported | Use a WSL-native project path such as `/home/<user>/projects`. |
| Windows native | Not supported | Outside the v0.1.x runtime contract. |
| macOS | Not supported | Outside the v0.1.x runtime contract. |

## Filesystems

| Filesystem or path | v0.1.x status | Mutation policy |
| --- | --- | --- |
| WSL-native local filesystem, such as `/home/<user>/...` | Supported | Allowed only after advisory-lock, atomic-replace, POSIX-mode, case, and Unicode probes pass. |
| Linux local filesystem | Supported | Allowed only after the complete live probe passes. |
| Windows-mounted DrvFs, such as `/mnt/c` or `/mnt/d` | Experimental / best-effort; not officially supported | `metadata` may improve permission behavior, but every live probe must still pass. A failed or indeterminate probe blocks mutation. |
| NFS, CIFS/SMB, SSHFS, and other detected network filesystems | Not supported for mutation | Read-only diagnostics remain available; write commands fail closed. |
| Cross-device replacement paths | Not supported | Candidate and target must be on the same filesystem. |

DrvFs support cannot be inferred from mount options or a successful `chmod` alone. File
locking and atomic replacement are independent requirements. See the
[Windows-mounted filesystem FAQ](faq.md#windows-mounted-filesystems) for migration and
recovery instructions.

# v0.1.5 Canonical First-Install Closure Design

Status: Approved

## Outcome

`v0.1.5` is publishable only when the immutable GitHub release body is a deterministic
projection of the verified detached manifest and contains the one canonical first-install
shell command. Manifest schema v1 remains unchanged and is the only release-data authority.

## Authority and data flow

```text
final manifest v1
  -> render_canonical_first_install_shell(verified_manifest, manifest_digest)
  -> deterministic release body
  -> draft release plus exact wheel/sdist/manifest assets
  -> immutable publication
  -> complete body and asset re-verification
```

The first-install renderer is independent of the project-local launcher. It accepts only a
verified manifest and its digest, reads no environment or checkout state, and emits stable
POSIX shell. It binds the exact repository, tag, version, manifest URL/digest, wheel URL/hash,
supported local Python and uv constraints, isolated uv flags, and reserved bootstrap/caller
channel. Invalid repository identity, tag, URL, hash, placeholder, or shell-unsafe input fails
closed.

The release body includes the version, source commit, immutable-release warning, generated
command block, exact asset hashes, manifest link, and a generated-do-not-edit marker. The
publisher supplies this body when creating the draft. The verifier compares the complete
remote body with a locally rendered expected body and reports the command digest.

## Release workflow

Both release jobs check out `refs/tags/v${version}` with full tag history, prove HEAD equals
the tag commit, and prove the checkout is clean. Publication is automated only; a failed
workflow never authorizes a manual fallback.

## Gates and acceptance

A fourteenth `canonical-first-install-publication` gate verifies the candidate manifest,
renderer, and release body before publication. Post-publication verification covers the
immutable body and three assets. Only after the re-rendered command completes the full fresh
project console dogfood, including a strict second-sync no-op, may README name an accepted
release.


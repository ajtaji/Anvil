# Provenance and public-tree verification

Anvil uses two complementary records rather than treating an old export hash
as the state of a living repository.

## Historical migration record

The `historical_*` fields in `PROVENANCE.json` preserve the first source-only
migration: source revision, selected board entries, path transformations,
closure counts, and source/export SHA-256 pairs. These values are immutable
history. A later edit to an imported file does not rewrite history and is not a
hash failure.

## Current public manifest

Git is the content-addressed manifest for the current tree. The
`current_tree` section states which top-level roots may be public, which entry
points and legal notices must exist, and which private or generated boundaries
are forbidden.

By default, `tools/verify_export.py` asks Git for the exact tracked set and
checks the files currently in the worktree against it. It fails when a tracked
path is outside the public boundary, a required file is untracked, a source
include escapes the repository, a dependency is absent from the selected set,
or a common sensitive/generated filename is selected.

Before files have been staged, maintainers can check the non-ignored candidate
tree explicitly:

```sh
python3 tools/verify_export.py --working-tree
```

After staging, and again from a clean checkout, use the release form:

```sh
python3 tools/verify_export.py
```

The second form also reports non-ignored untracked files and unstaged changes,
because either condition means the worktree is not an exact view of the Git
selection being verified.

The verifier deliberately does not create or update a second table of current
file hashes. Git already records those hashes, and duplicating them inside a
tracked JSON file creates a self-referential manifest and a stale second source
of truth.

## Redistribution boundary

The public tree may contain Anvil sources and documentation, target profiles,
runtime firmware with its original notices, and focused reproducible host or
emitted-code tests. It must not contain compiler executables or implementation
source, build products, credentials, NVRAM/calibration data, local settings,
private keys, machine-specific paths, worktree scratch, or bench transcripts.

The repository MIT license applies only where no more specific notice exists.
CYW43455 firmware, Khronos Registry-derived material, DejaVu-derived glyph
tables, and BearSSL-derived cryptography retain their own terms; see
[LICENSING.md](LICENSING.md) and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

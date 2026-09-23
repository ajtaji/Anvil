# Provenance and public-tree verification

Anvil uses two complementary records rather than treating an old export hash
as the state of a living repository.

## Historical migration record

The `historical_*` fields in `PROVENANCE.json` preserve the first source-only
migration: source revision, selected board entries, path transformations,
closure counts, and source/export SHA-256 pairs. These values are immutable
history. A later edit to an imported file does not rewrite history and is not a
hash failure.

Immutable is not the same as unchecked. `tools/verify_export.py` walks every
`historical_migration_files`/`historical_standalone_files` record and confirms
its `destination` exists and is tracked, for every destination that record's
own `current_tree` boundary (`allowed_prefixes`/`allowed_root_files`) claims as
part of this repository. A destination outside that boundary (for example
`keywords.def`, named by `historical_selection` as compiler data the export
pulled in from outside this repository) is not this repository's to have gone
missing, so it is left alone rather than guessed at. It does not re-verify the
recorded `sha256` fields, for the reason above. This closes the gap that let
`PROVENANCE.json` name two `Firmware/CYW43455/LICENSE*.txt` rows that had never
been part of any tracked tree, with nothing checking the claim (forum 925).

## Boot-medium checksum verification

A board's shipped `SHA256SUMS` is a separate, install-facing record: it lets
an operator verify the files they are about to put on a boot medium, and it is
not derived from `current_tree` at all. `tools/verify_export.py` now also
walks `CHECKSUM_FILES_TO_VERIFY` (currently `Boards/RaspberryPi4/sdcard/SHA256SUMS`)
and, for every line, recomputes the named file's SHA-256 and fails on any
mismatch — a tampered file and a stale checksum both fail the same way. It
also checks `REQUIRED_ADDITIONAL_CHECKSUMS`: files a board's own README tells
an operator to add from elsewhere in the repository, so that a required row
cannot be silently dropped again. This is how forum 926 was found:
`Boards/RaspberryPi4/sdcard/SHA256SUMS` checksummed only the three files
`tools/build.py` produces (`kernel8.img`, `armstub8.bin`, `config.txt`) and
said nothing about the two CYW43455 radio-firmware files
(`Firmware/CYW43455/brcmfmac43455-sdio.bin`,
`Firmware/CYW43455/brcmfmac43455-sdio.clm_blob`) the same board's README tells
an operator to copy onto the medium. The board-appropriate NVRAM file
(`BRCMNV.TXT`) is deliberately not part of this repository — it carries
per-board calibration and identity data — so it has no canonical hash to check
and is intentionally outside this list.

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

Before files have been staged, the non-ignored candidate tree can be checked
explicitly:

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

A source repository and a release ZIP are different artifacts, and the
diagnostics boundary applies to each in its own way: this repository deliberately
tracks its `RaspberryPi4/Tests/` gates and declares two
`RaspberryPi4/Examples/Diagnostics/` programs as public entry points, because a
reproducible test is how a reader checks what the source claims, while release
ZIPs exclude `Diagnostics` entirely — the staging pass refuses any path with a
`Diagnostics` segment and the finished stage is swept again to prove it.

The repository MIT license applies only where no more specific notice exists.
CYW43455 firmware, Khronos Registry-derived material, DejaVu-derived glyph
tables, and BearSSL-derived cryptography retain their own terms; see
[LICENSING.md](LICENSING.md) and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

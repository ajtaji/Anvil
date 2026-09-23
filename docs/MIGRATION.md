# Migration record

Anvil began as a source-only export of the recursive include closures for the
Pi 4 and UNO Q board entries. Development now continues in this repository, so
the initial import and the current public tree are intentionally different
provenance concepts.

`PROVENANCE.json` schema 2 records both:

- **historical migration mapping** — the original source revision, path
  transformations, source/export digests, entry points, and closure counts;
- **current public selection** — the allowed repository roots, required
  notices and entry points, and forbidden private/generated boundaries. Git's
  index and object database are the content-addressed manifest for current
  files.

Historical digests describe what was imported on the migration date. They are
not expected to match files that have since been edited here, and the verifier
does not misreport normal development as a failed historical export.

## Initial mechanical mapping

The first export applied these path-only transformations:

- `Anvil/Core/*.pi4` → `Anvil/Core/*.pbi`
- `Anvil/Hal/*.pi4` → `Anvil/Hal/*.pbi`
- `ArduinoQ/Board/*.pi4` → `ArduinoQ/Board/*.unoq`
- `ArduinoQ/Lib/*.pi4` → `ArduinoQ/Lib/*.unoq`
- Raspberry Pi 4 hardware source names remained `.pi4`

The original checkout and independent development worktrees were not modified
or imported as Git history. Compiler source and binaries were not exported.
Build products are written below ignored directories and are never migration
inputs.

## Dynamic image-map integration

The first post-export integration combined runtime image measurement with the
already-selected DSI memory range. The resulting Pi board policy keeps both:

- a live image reservation rounded through its final megabyte;
- the DSI framebuffer as a separate guarded range;
- a dedicated autoboot page below the image; and
- the first payload/staging window at the next free megabyte.

This matters to migration because older notes described the DSI range as a
future module arena. It is not available: the board now owns it for display
memory, and module placement must obtain another explicitly guarded range from
the HAL.

## Repository-native additions

The PMFMOD v1 constants, parser/relocator, transactional arena records, and
their emitted-code gate were authored for this standalone repository. The
Vulkan-compatible foundation and its tests are also repository-native work.
They are part of the current Git manifest, not retroactively attributed to the
historical import.

When work is carried from another tree, review and transform it as an explicit
source change. Do not overlay a worktree or regenerate the historical hashes.
Current release integrity belongs to Git; historical mapping remains an audit
record.

# Driver provenance review

Status: open, 2026-09-10. Further public pushes are held. This document records
engineering evidence and the publication boundary, not a legal determination.
No project-wide license change or public-history rewrite is authorized by it.

`PROVENANCE.json` records the hold. `tools/verify_export.py` continues to check
local packaging, but its `--for-publication` mode refuses while that review is
not recorded as cleared. Neither mode is a substitute for the actual review.

**The file- and function-level inventory is complete and lives in
[`PROVENANCE_INVENTORY.md`](PROVENANCE_INVENTORY.md)**, with the same data in
machine-readable form under `PROVENANCE.json`'s `third_party` block and a gate,
`tools/provenance_inventory_check.py`, that fails if a derived file loses its
notice or if any source file cites an upstream the inventory does not list.
Acceptance item 1 below is met by it; items 2 to 4 are not, and cannot be until
the owner answers the question in the next section.

## Confirmed discrepancy

The existing GENET driver describes structural translation from U-Boot,
including reset, DMA-ring initialization and transmit procedures. Its stated
primary source is U-Boot v2025.01, commit
`6d41f0a39d6423c8e57e92ebbe9f8c0333a63f72`.
The corresponding [bcmgenet.c](https://github.com/u-boot/u-boot/blob/6d41f0a39d6423c8e57e92ebbe9f8c0333a63f72/drivers/net/bcmgenet.c)
and PHY source carry GPL-2.0-or-later notices. These are not covered by
declaring original Anvil code MIT, and the current notices did not account for
this derivation. Removing citations or renaming procedures would not resolve it.

The confirmed Broadcom ISC Wi-Fi source notices are now retained separately
from the binary firmware license. The rest of the actual include and source
provenance closure still needs review, including register headers and the
MMU/SDIO implementation; a hardware register citation is not automatically
code derivation, and each case needs inspection.

Follow-up source-header checks extend the inventory beyond GENET:
`mmu.pi4` explicitly names its all-level set/way loop as ported from
U-Boot [`cache.S`](https://github.com/u-boot/u-boot/blob/6d41f0a39d6423c8e57e92ebbe9f8c0333a63f72/arch/arm/cpu/armv8/cache.S),
whose header is GPL-2.0-or-later. The V3D source describes transcribed routines
from Linux
[`v3d_gem.c`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/v3d/v3d_gem.c);
that file, `v3d_regs.h`, and `drivers/pmdomain/bcm/bcm2835-power.c` at the same
revision carry GPL-2.0-or-later headers. Distinguish register facts from copied
implementation when reviewing each routine; no whole-file legal conclusion is
inferred solely from a reference to a register header.

The owner has been asked whether to retain applicable GPL components with
their obligations alongside MIT original code, or pursue a permissive-only
replacement. That choice is pending. Network and touch development continue
locally, with no public push or historical rewrite.

## The exact decision, restated after the full inventory

The inventory did not change the question; it bounded it. Sixteen upstreams are
cited across the tree. Thirteen of them need no decision at all: MIT, ISC,
BSD-3-Clause, the Khronos registry, DejaVu, the separately licensed Cypress
binaries, and the specification documents are all either compatible with the
project's MIT terms or already carried under their own retained notices, and
their notices and texts now all ship.

**The decision is only about the files derived from U-Boot and from the Linux
kernel, and it is per driver:**

> Retain those components under their GPL-2.0 terms — shipping the license
> text, a per-file notice, and an offer of corresponding source — **or** replace
> the derived blocks with independently derived or permissively licensed work.

Seventeen files carry such a block. The per-driver table in
[`PROVENANCE_INVENTORY.md`](PROVENANCE_INVENTORY.md) lists, for each, exactly
which procedures would have to be rewritten under "replace" and exactly which
notices would have to ship under "retain". Three separable groups fall out of
it:

1. **GENET, xHCI and PCIe** — the expensive replacements. GENET is the largest
   and it carries the console, so a replacement is also a network regression
   risk. The OpenBSD basis remains a candidate and remains unwritten.
2. **MMU set/way, the V3D cache and power sequences, `hw_boot`'s EL2→EL1 block,
   the mailbox and display message composition, TFTP's retransmission policy,
   the RNG enable order, one USB retry constant** — small, bounded, and
   re-derivable from the Arm ARM, the firmware interface, the RFCs and the
   register semantics that are already cited beside them.
3. **The U-Boot-shaped console command set** — no U-Boot code is present. What
   is at stake is whether a deliberately compatible command vocabulary and
   argument grammar is disclosed as derivation. This costs nothing to decide and
   should be decided rather than assumed.

No GPL license text has been added to this repository, and that is deliberate:
shipping one would itself be an election. `PROVENANCE.json` marks those sources
`license_text_pending_decision`, and the inventory check reports it as a note
rather than a failure for exactly as long as the hold stands.

The relevant derivations are now disclosed in
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) under their own sections.
Disclosure is not election: it states what the code is, which was the gap the
original notice had, and it is correct under either answer.

## Candidate replacement basis, not an accepted replacement

OpenBSD has a GENET implementation under a two-clause BSD notice. Review is
pinned to OpenBSD source commit
`d728e260a5a9b55d69a81bf0ff6af38626ab17a4`:

- [`bcmgenet.c`](https://github.com/openbsd/src/blob/d728e260a5a9b55d69a81bf0ff6af38626ab17a4/sys/dev/ic/bcmgenet.c)
- [`bcmgenetreg.h`](https://github.com/openbsd/src/blob/d728e260a5a9b55d69a81bf0ff6af38626ab17a4/sys/dev/ic/bcmgenetreg.h)
- [`bcmgenetvar.h`](https://github.com/openbsd/src/blob/d728e260a5a9b55d69a81bf0ff6af38626ab17a4/sys/dev/ic/bcmgenetvar.h)

Those MAC files retain Jared McNeill and Mark Kettenis notices. Do not extend
that license description to the entire network stack: the related
[`brgphy.c`](https://github.com/openbsd/src/blob/d728e260a5a9b55d69a81bf0ff6af38626ab17a4/sys/dev/mii/brgphy.c)
and register header retain a four-clause BSD notice, including an advertising
condition. The required BCM54213PE PHY behavior must be reviewed independently.

No replacement driver has been implemented or tested from this basis yet.
A replacement must retain its applicable notices, preserve the actual Anvil
driver contract, and pass emitted-code and hardware lifecycle/traffic checks.
Existing public history remains a separate publication question even if the
current source is replaced. No historical commits have been removed.

## Acceptance still owed

1. ~~Finish the file-level provenance inventory and retained notices.~~ **Done,
   2026-09-10:** [`PROVENANCE_INVENTORY.md`](PROVENANCE_INVENTORY.md),
   `PROVENANCE.json` `third_party`, `tools/provenance_inventory_check.py`, and
   two newly retained texts (`licenses/Mesa-MIT.txt`,
   `licenses/RaspberryPi-armstub8-BSD-3-Clause.txt`). The Mesa-derived V3D
   material and the Raspberry Pi stub's binary-distribution obligation were both
   undisclosed before this pass.
2. Resolve the GENET implementation and license compatibility while preserving
   the user-selected MIT terms for original Anvil code.
3. Verify any replacement against the public include closure and real board
   behavior; do not turn a licensing repair into an untested network regression.
4. Explicitly resolve the existing public-history/distribution boundary before
   lifting this publication hold.

Forum tracking: [topic 725](https://forum.ajtaji.com/topic/725).

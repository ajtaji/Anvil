# Driver provenance review

Status: open, 2026-09-10. Further public pushes are held. This document records
engineering evidence and the publication boundary, not a legal determination.
No project-wide license change or public-history rewrite is authorized by it.

`PROVENANCE.json` records the hold. `tools/verify_export.py` continues to check
local packaging, but its `--for-publication` mode refuses while that review is
not recorded as cleared. Neither mode is a substitute for the actual review.

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

1. Finish the file-level provenance inventory and retained notices.
2. Resolve the GENET implementation and license compatibility while preserving
   the user-selected MIT terms for original Anvil code.
3. Verify any replacement against the public include closure and real board
   behavior; do not turn a licensing repair into an untested network regression.
4. Explicitly resolve the existing public-history/distribution boundary before
   lifting this publication hold.

Forum tracking: [topic 725](https://forum.ajtaji.com/topic/725).

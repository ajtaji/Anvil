# Driver provenance review

Status: **the provenance question is settled; publication is still a separate
instruction, 2026-09-10.** This document records engineering evidence and the
publication boundary, not a legal determination. No project-wide license change
or public-history rewrite is authorized by it.

## The confirmation

**It was confirmed on 2026-09-10 that no third-party code was used; the
references were read for how the hardware behaves.** U-Boot, the Linux kernel,
Mesa, OpenBSD, BearSSL, the device trees and every other source named in this
tree were read to learn how the hardware is driven — register sequences,
ordering, quirks, wire formats — and the result was implemented independently.

That answers the question this review was opened on, and it answers it as a
statement of fact about how the code was written, not as a licensing argument.
Its consequences are simple:

- **There is no licence election to make.** The retain-or-replace choice this
  document used to pose, per driver, does not arise: there is nothing to retain
  and nothing to replace.
- **There is no corresponding-source obligation**, and no GPL text is owed by
  this repository.
- **Nothing in the tree is classified `derived` or `verbatim`.** Every such pair
  is now `consulted`, and `tools/provenance_inventory_check.py` refuses either
  class outright — a copied or derived block is not permitted in this tree; it is
  restated or removed.
- **Every citation stays.** They are the provenance of the hardware and protocol
  facts and are how a reader checks a register offset, a timing or a quirk. None
  was removed by this lane, and no source header was reworded.

One quotation existed and no longer does. `RaspberryPi4/Lib/pcie.pi4` used to
carry five lines of `bcm2711.dtsi` inside a comment, introduced as "comment
included verbatim because it is the citation". The hardware fact it carried — the
PCIe wrapper cannot reach past the first 3 GiB, and the inbound window is sized
to match — is now stated in the file's own words, with the device-tree lines kept
as a pointer to where it can be checked.

The retained texts under `licenses/` stay, as acknowledgments of references
consulted rather than as notices for incorporated code.
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) is written that way and says
so. The one entry that is genuinely redistribution — the Cypress CYW43455
firmware binaries — is called out there as such and keeps its own terms.

## What the inventory is now for

**The file- and function-level inventory lives in
[`PROVENANCE_INVENTORY.md`](PROVENANCE_INVENTORY.md)**, with the same data in
machine-readable form under `PROVENANCE.json`'s `third_party` block and a gate,
`tools/provenance_inventory_check.py`, that fails if any source file cites an
upstream the inventory does not list, if a consulted pair loses the citation it
rests on, or if anything is ever recorded as copied or derived again.

It is no longer a decision document. It is the record of **where each fact came
from**, so that a reader who doubts a number can go and read the same page, and
so that the tree's habit of citing its sources is enforced rather than trusted.
That habit is the thing worth keeping: at the last run, 143 of 220 tracked
source files cite something by file and line.

The references themselves are unchanged. U-Boot v2025.01 at
`6d41f0a39d6423c8e57e92ebbe9f8c0333a63f72`, Linux v6.12 at
`adc218676eef25575469234709c2d87185ca223a` and the `rpi-6.12.y` fork, Mesa
`mesa-24.3.4`, the Raspberry Pi stub at `439b6198…`, the Khronos registry at
`v1.4.350`, and the vendor and standards documents are all still cited, still
pinned, and still the place to check what the code asserts about the silicon.

OpenBSD's GENET sources remain read and cited in the same way: a second
description of the same MAC. Their two-clause MAC files and four-clause PHY files
are recorded in `PROVENANCE.json` so that a later reader does not flatten the two
into one licence.

## Acceptance

1. ~~Finish the file-level provenance inventory and retained notices.~~ **Done,
   2026-09-10:** [`PROVENANCE_INVENTORY.md`](PROVENANCE_INVENTORY.md),
   `PROVENANCE.json` `third_party`, `tools/provenance_inventory_check.py` and the
   retained texts in `licenses/`.
2. ~~Resolve the GENET implementation and license compatibility while preserving
   the user-selected MIT terms for original Anvil code.~~ **Settled by the
   2026-09-10 confirmation:** no third-party code is present in GENET or
   anywhere else, so the MIT terms for original Anvil source stand unqualified.
3. ~~Verify any replacement against the public include closure and real board
   behavior.~~ **Moot: there is no replacement to make.** The include closure is
   checked on every run of `tools/verify_export.py`.
4. Resolve the existing public-history and distribution boundary before any
   further public push. Unchanged by the confirmation, because it is a question
   about what has already been published, not about what the code is.

## Still owed before a push

Review hygiene, not provenance:

- **Bench addresses in two files.** `RaspberryPi4/Tests/tcp_multiif_emitted_gate.pi4`
  and `tools/payload_lifecycle_check.py` carry `192.168.1.15` and `192.168.1.16`.
  They are RFC 1918 addresses and leak nothing routable, but they are a real
  subnet rather than documentation values. (`192.168.137.0/24` elsewhere is
  deliberate and correct — it is Windows Internet Connection Sharing's fixed
  subnet and the code has to know it.)
- **A working tree that is not a clean view of the Git selection.** The module
  lane has untracked sources and unstaged changes in it, which is what
  `verify_export.py --for-publication` reports after the hold itself. The
  publication selection is the tracked source tree.

Neither is this lane's file to change, and both are recorded in
`PROVENANCE.json` under `publication_review.remaining_before_push`.

`PROVENANCE.json` keeps `publication_review.status` at `held`, and
`tools/verify_export.py --for-publication` continues to refuse, because
**publishing this repository is a separate, explicit instruction that has not
been given.** The confirmation removed the provenance reason for the hold. It did
not push anything and does not authorize a push.

Forum tracking: [topic 725](https://forum.ajtaji.com/topic/725).

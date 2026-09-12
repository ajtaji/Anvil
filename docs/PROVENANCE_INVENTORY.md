# Provenance inventory

Status: **desk review, 2026-09-10, updated the same day by the confirmation
below.** This document records engineering evidence: where each fact in this
tree came from and how a reader checks it. It is not a legal determination, it
does not relicense anything, and it removes no attribution and no citation.

**It was confirmed on 2026-09-10 that no third-party code was used; the
references were read for how the hardware behaves.** Every pair this document
once classified `derived` or `verbatim` is therefore `consulted`. See
[The 2026-09-10 confirmation, and what it means](#the-2026-09-10-confirmation-and-what-it-means).

Companion records:

- `docs/PUBLICATION_REVIEW.md` — the publication boundary and what is still owed.
- `docs/THIRD_PARTY_NOTICES.md` — the references consulted, acknowledged.
- `PROVENANCE.json` — the same inventory in machine-readable form, under
  `third_party`.
- `tools/provenance_inventory_check.py` — the gate that keeps the two agreeing.

## What was inventoried, and how

### EL3 additions (2026-09-11)

`RaspberryPi4/Lib/interrupts.pi4` is independently implemented against the
GICv2 register contract. Arm IHI 0048B supplies the register roles, interrupt
ID rules, group semantics and acknowledge/end-of-interrupt requirements.
[Arm DDI 0471B, section 3.6.1](https://documentation-service.arm.com/static/5e8f15e27100066a414f7424)
supplies the GIC-400 CPU-interface identification fields. The pinned
[Raspberry Pi firmware stub](https://github.com/raspberrypi/tools/blob/439b6198a9b340de5998dd14a26a0d9d38a6bcac/armstubs/armstub8.S)
supplies the inherited secure-view controller values used for compatibility.
These entries are `hardware-facts`; no third-party driver body was imported.

`RaspberryPi4/Lib/exceptions.pi4` records AArch64 architectural facts under
`vendor-spec`: exception-vector layout, exception-level register banks and
exception return state. These premises were inherited from the project's
existing exception, stub and multicore implementation and checked against its
instruction model; the new implementation session did not directly consult
an Arm manual. A subsequent architectural review directly checked Arm
102412_0103_02, Cortex-A72 TRM 100095_0003_06 and DDI0595 ID092421; the exact
official URLs, pages and verified properties are recorded in
[the EL3 startup review](EL3_STARTUP_REVIEW.md). This is post-implementation
verification, not imported handler code or silicon proof. Its primary-only
frame ownership, callback policy and
bounded failure reporting are Anvil implementation choices, not an imported
exception-handler implementation.

The counts below remain the explicitly dated historical snapshot, not a
claim that the new files existed in that inventory.

Every Git-tracked `.pi4`, `.pbi`, `.unoq`, `.asm` and `.def` file in this
repository: **218 source files, 207,715 lines** at local `main` `baddc30`.
Other lanes commit to this tree continuously — that count rose by five while
this document was being written — so treat every figure here as a snapshot and
`tools/provenance_inventory_check.py` as the authority. It recomputes all of
them and fails if a new file has brought in a citation nobody listed. Each file
was scanned for
citations of a third-party project, an upstream filename, a revision, a
specification or a copyright notice, using the citation patterns recorded in
`PROVENANCE.json` under `third_party.sources.*.citation_pattern`. Every match
was then read in context and classified by hand. The scan is repeated on every
run of the check script, so a citation added later cannot go unlisted.

**143 of 218 files carry at least one citation; 75 carry none.** The 311
resulting file/source pairs classify as:

| Class | Pairs | What it means |
| --- | ---: | --- |
| `hardware-facts` | 199 | Register offsets, bit positions, magic values, timings, required orderings — read from a datasheet, a manual, a device tree, or a vendor header that is a table of definitions. Facts about a chip, not expression. |
| `protocol-facts` | 39 | Wire formats and constants from a published specification (RFC, IEEE 802.11/802.3, USB-IF HID/HUT, FIPS, SP 800). |
| `interface-facts` | 18 | Command names, argument grammar and documented defaults modelled on U-Boot's console so an operator's transcript transfers. The implementations are original. |
| `consulted` | 41 | Hardware or protocol behaviour learned by reading a third-party implementation, then implemented independently. The citation records where the fact can be checked; no code was taken. |
| `reference-only` | 14 | Cited as corroboration or as a candidate basis; no material taken. |

Those 41 were 40 `derived` and 1 `verbatim` before the 2026-09-10 confirmation.
The counts are otherwise unchanged, because reclassifying is not rewriting: the
same files cite the same sources at the same lines.

The remaining 75 files, and every procedure in the 143 that carries no citation,
are **original**. `--list-original` prints them.

### The line this inventory draws

A register offset is a fact about silicon. Anyone who reads the same document
writes the same number, and `#GENET_SYS_PORT_CTRL = $0004` is the only correct
answer. Those citations exist so a reader can check the number, not because
anything was taken.

A *sequence* is a fact about silicon too, and a more expensive one to establish.
"Set RBUF flush bit 1, wait 10 us, clear it, wait 10 us, write zero, wait 10 us,
then UMAC_CMD = 0, then SW_RESET | LCL_LOOP_EN for 2 us" is what this part needs
in order to come up, asymmetries and all — and for a block whose vendor document
does not describe it, a working driver is where that behaviour is written down.
Reading one to learn what the hardware requires is what the `consulted` class
records, and it is why the citation is kept: it is the only way a later reader
can check that the sequence is right.

The sections below say, per file, what was read and how much of the behaviour
came from reading it rather than from a datasheet. That gradient is worth
keeping — it tells the next person which facts are corroborated twice and which
rest on a single source — even though it no longer feeds a licensing decision.

## The project's intended license — recorded, not inferred

**MIT, `Copyright (c) 2026 PureMetal Labs`.** It is stated in four places that
agree: the root `LICENSE`, `README.md` under "License", `docs/LICENSING.md`
("Unless a file or subtree carries a different notice…"), and the development
record, where MIT was selected for original Anvil source.
There is no ambiguity to resolve on that point.

## Consulted references, file by file

Line numbers are from the current working tree at local `main` `9e0e55e` and
will drift; the procedure names will not.

> **A note on the vocabulary in some file headers, before anything below is
> misread.** Several of these files say "transcribed", "ported from", "copied"
> or "THE PRIMARY SOURCE". That is bring-up vocabulary: it is how someone
> describes working with a reference open beside them, and it was written to
> stop a later reader from "tidying away" a sequence the hardware actually
> needs. It was confirmed on 2026-09-10 that no third-party code was used; the
> references were read for how the hardware behaves. The headers are left
> exactly as their authors wrote them — rewording a source comment is not this
> lane's to do — and they are quoted below because they are the record of which
> reference answered which question.

### `RaspberryPi4/Lib/genet.pi4` — U-Boot, read for GENET bring-up — **primary reference**

The file names U-Boot v2025.01 `drivers/net/bcmgenet.c` as **"THE PRIMARY
SOURCE"** and cites it as `[U:line]` throughout. It is the most heavily consulted
reference in the tree, and the file's own comments are the record of it.

| Anvil procedure | Upstream | What was read there |
| --- | --- | --- |
| `GenetInterfaceSet` | `bcmgenet_interface_set`, `[U:605-620]` | The one branch this board can take. |
| `GenetUmacReset` | `[U:199-234]` | The whole reset order, including the RBUF flush's three writes and three delays and the `SW_RESET \| LCL_LOOP_EN` loopback step, which the header explains must not be "tidied away". |
| `GenetWriteHwAddr` | `bcmgenet_gmac_write_hwaddr`, `[U:236]` | The register pair and byte order. |
| `GenetDisableDma` / `GenetEnableDma` | `[U:252-260]`, `[U:262-269]` | Both, and the file says of the enable path: *"NOTE THE ASYMMETRY, IT IS IN THE DRIVER AND IT IS COPIED."* |
| `GenetRxRingInit` / `GenetRxDescsInit` / `GenetTxRingInit` | `[U:397-439]` | Ring setup; the driver's own comment about `RDMA_PROD_INDEX` is quoted. `GenetRxRingInit`'s header says *"THE ONE THING IN HERE THAT IS NOT A TRANSCRIPTION…"*. |
| `GenetSend` | `bcmgenet_gmac_eth_send`, `[U:271-314]` | The descriptor write order, the `len_stat` composition, the producer-index arming. One deliberate departure: a real deadline replaces U-Boot's bare `tries = 100`. |
| `GenetRecv` | `[U:340-370]` | Consumer-index walk, cache invalidation points. |
| `GenetAdjustLink` | `[U:461-468]` | The `ID_MODE_DIS` choice, which the file records as following U-Boot where Linux differs. |

Everything in the `#GENET_*` constant block is `hardware-facts`, each line
citing `[U:n]` and `[L:n]` — two independent readings of the same register map.
Linux `bcmgenet.h`, `bcmmii.c` and `brcmphy.h` are cited as a second witness and
for the half-duplex refusal that is deliberately **not** enabled.

### `RaspberryPi4/Lib/mmu.pi4` — U-Boot, read for cache maintenance — **narrow**

`MmuFlushDCacheAll()` (≈:2195) and `MmuInvalidateDCacheAll()` (≈:1833) carry a
header that begins **"PORTED FROM U-Boot's `__asm_flush_dcache_all` /
`__asm_dcache_all` / `__asm_dcache_level` (`arch/arm/cpu/armv8/cache.S`)"**.
That file's header is GPL-2.0+, Copyright 2013 David Feng, and describes its own
Arm sample-code basis.

Two things narrow it and one widens it:

- The set/way walk is the canonical ARMv8 algorithm and the operand layout for
  `DC CISW` is in the Arm ARM. Much of what is "ported" is the architecture.
- It is two procedures, not a file. Everything else in `mmu.pi4` — the TCR
  fields, MAIR encoding, descriptor layout, SCTLR bits — is `hardware-facts`
  from `armv8_mmu.h`, `arm_system.h` and the Linux `sysreg.h` encodings.
- Widening it: the file also adopts `cache_v8.c`'s **ordering** rule
  (`dcache_disable` clears `C|M` before flushing) and says so. That ordering
  is a requirement learned from a working implementation rather than read off
  a manual page, which is exactly why the citation is kept beside it.

**Inventory-accuracy note:** the header still says
`cache.S` "is NOT in this tree, so the algorithm below is the canonical one".
`cache.S` was fetched on 2026-08-29 and is now a reference file. The comment is
stale. It is left exactly as it stands — correcting a source header is not this
lane's to do — and is recorded here so the next reader is not misled.

### `RaspberryPi4/Lib/v3d.pi4` — Mesa and Linux, read for V3D — **the deepest reading in the tree**

The file states plainly that the BCM2711 manual contains exactly one fact about
V3D and that **"everything below is transcribed from four sources"**. Those four
split cleanly by license:

- **Mesa 24.3.4 (MIT)** — the control-list packet layouts (`v3d_packet.xml`),
  the QPU field/opcode tables, the TFU and tiling descriptions, and the
  register-write order of `v3dx_simulator.c`'s job submission. Packet bit
  layouts are hardware description; the job-submission *order* and the
  render-list construction in `V3dRclBuild`, `V3dRenderBegin`,
  `V3dClStoreTileBufferGeneral`, `V3dShaderRecordBegin`, `V3dAttrRecord`,
  `V3dClMulticoreSupertileCfg` and `V3dCsdBegin` were written to the order Mesa
  shows the hardware requires. **Acknowledged in `docs/THIRD_PARTY_NOTICES.md`;
  nothing owed.**
- **Linux v6.12 (GPL-2.0+)** — `v3d_regs.h` is a table of definitions and is
  `hardware-facts`. Two things are not: `V3dInvalidateCaches()` is described as
  **"transcribed from `v3d_gem.c:20-35` and `:225-240`"**, and the power/reset/
  ASB-bridge sequence follows `drivers/pmdomain/bcm/bcm2835-power.c`
  (`:100-227`, cited per constant and per step). Both files are GPL-2.0+.
- **`bcm2711.dtsi`** — block bases. `hardware-facts`.
- **py-videocore6** — an independent witness that the block bases are what a
  working userspace driver maps. No expression taken. Recorded anyway, because
  that project is **GPL-2.0-or-later** and a reader must not mistake the
  citation for a permissive one.

`RaspberryPi4/Lib/v3dqpu.pi4` (QPU field packing, opcode tables, the hazard
list) and `RaspberryPi4/Lib/neon.pi4` (tiling/format material) rest on the same
Mesa reading. For a block with one line of vendor documentation, that backend
is the specification, and these two files are where that shows most.

### `RaspberryPi4/Lib/cyw43.pi4`, `cyw43_rx_glom.pi4` — Linux brcmfmac, read for SDIO and BCDC — **acknowledged in the files**

Both carry the ISC copyright line in their own headers and point at
`licenses/Broadcom-brcmfmac-ISC.txt`. `cyw43_rx_glom.pi4` says "Adapted from
Linux brcmfmac `sdio.c`/`bcmsdh.c` receive-glom semantics" in its second line.
Those acknowledgments stay as their authors wrote them, and
`licenses/Broadcom-brcmfmac-ISC.txt` stays beside them.

`RaspberryPi4/Lib/sdio.pi4` is the awkward neighbour: its CYW43-facing half
cites the same ISC files, but its host-controller half cites
`rpi-6.12.y_bcm2835-mmc.c`, `sdhci.h` and the Linux MMC core — **GPL-2.0**, not
ISC. The register maps are facts; the host-controller initialization order was
learned from that driver. Classified `consulted` against both sources so the
distinction between the two halves is not lost.

### `RaspberryPi4/Lib/display.pi4` and `mailbox.pi4` — U-Boot, read for the firmware mailbox — **moderate**

`DisplayInit()` builds the same combined firmware message U-Boot's
`struct msg_setup` builds, with the same nine tags in the same order
(`v2025.01_msg.c:36-45`, `:166-189`), plus a tenth Anvil adds. The tag numbers
are interface facts from `mbox.h`; *which* tags to send in *what* order in *one*
message is U-Boot's arrangement, and the file says it is reproduced deliberately.

`mailbox.pi4` is more explicit. Its header records that the kernel and U-Boot
differ on the tag "value length" word, that Anvil's list path **follows U-Boot**,
and the reason: *"reproducing it byte for byte removes one variable from the
next thing that goes wrong."* Two conventions exist, the firmware accepts both,
and the file records which one it matches and why — that is the fact worth
keeping, and the citation is how the next reader checks it.

### `RaspberryPi4/Lib/tftp.pi4` — U-Boot, read for TFTP behaviour — **moderate**

The protocol is RFC 1350 and most of the file is `protocol-facts`. But the
retransmission design, the server-TID adoption, the timeout handler's re-send of
the last ACK and the option handling are each cited to
`v2025.01_net_tftp.c` by line (`:264-278`, `:341-362`, `:597-616`, `:702-712`),
and the header says of one of them "This is U-Boot's design, deliberately".

### `RaspberryPi4/Lib/xhci.pi4` and `pcie.pi4` — U-Boot, read for controller and window bring-up — **moderate**

`xhci.pi4` names U-Boot's `xhci.h` as **"THE SPECIFICATION for this file"** —
and for a controller with no public datasheet, a vendor-neutral register header
genuinely is the specification, so the constant block is `hardware-facts`. The
init path is not: `xh_MemInit`, `XhciMaxPacket`, `xh_Control`, `xh_Bulk` and
`XhciBulkReady` cite `xhci-mem.c`, `xhci-ring.c` and `xhci.c` routines by name.

`pcie.pi4` programs the outbound and inbound windows the way
`v2025.01_pcie_brcmstb.c` shows this wrapper requires, and cites that file's
`brcm_pcie_config_address` behaviour.

**The tree's one quotation was here, and it is gone.** `pcie.pi4:224-232` used to
reproduce five lines of `bcm2711.dtsi:577-583` — the DMA erratum comment and the
`dma-ranges` property — introduced with *"comment included verbatim because it is
the citation"*. On 2026-09-10 that passage was **restated in the file's own
words**: the wrapper cannot reach past the first 3 GiB, and the node's inbound
translation is declared over PCI memory space as bus `$0000_0000` to CPU
`$0000_0000` with a length of `$C000_0000`. The device-tree file and lines stay
as a pointer to where the fact can be checked. Nothing in this tree is a
quotation now, and the pair is classified `consulted` like every other.

### `RaspberryPi4/Board/hw_boot.pi4` — U-Boot, read for the EL2 to EL1 step — **moderate**

`HwBootToEl1()`'s EL2→EL1 register block (CNTHCTL_EL2, CNTVOFF_EL2, VPIDR_EL2,
VMPIDR_EL2, CPTR_EL2, HSTR_EL2, HCR_EL2, then SPSR/ELR and `eret`) is the shape
of U-Boot's `armv8_switch_to_el1`, and the file names
`v2025.01_transition.S` as "the two-step shape to transcribe". The arm64 `Image`
header layout comes from `v2025.01_image.c` and is `hardware-facts`.

### `RaspberryPi4/Board/armstub8.asm` — Raspberry Pi tools — **notice retained in the file**

A declared translation and modification of `armstubs/armstub8.S` at commit
`439b6198…`, with the **complete** three-clause notice retained in full at the
top of the file and `setup_gic` marked "transcribed from `armstub8.S:214-235`".
That header is left exactly as it stands, and
`licenses/RaspberryPi-armstub8-BSD-3-Clause.txt` carries the same text beside
it. Nothing in the source header was touched by this lane, and nothing in it is
removed by the 2026-09-10 confirmation: an acknowledgment costs nothing to keep
and is how a reader finds what was read.

### `RaspberryPi4/Lib/touch_goodix.pi4`, `dsi_panel_v2.pi4`, `dsi_panel_v2_dcs.pi4`, `Tests/Fixtures/dsi_panel_v1.pi4` — Linux panel and touch drivers — **light**

Panel initialization sequences and touch-controller register maps taken from
`rpi-6.12.y` `goodix.c` (GPL-2.0-**only**), `panel-waveshare-dsi-v2.c` and
`panel-raspberrypi-touchscreen.c`. A DCS command sequence for a specific panel
is close to pure hardware fact — the panel accepts one sequence and no other —
but the kernel driver is where it is written down, so that is where it was
read. Classified `consulted`, with the citations kept: a panel that will not
come up is debugged by comparing the sequence against the place it came from.

### `RaspberryPi4/Lib/entropy.pi4` — Linux, read for the RNG enable order — **light**

The RNG200 register map is corroborated **three ways** — Raspberry Pi's kernel
fork, mainline Linux, and U-Boot — and the file shows they agree character for
character on every offset and mask. That is the textbook argument that these are
facts. The one behaviour that is not corroborated by a datasheet is the
enable/warm-up ordering, which was learned from `iproc-rng200.c`. Listed as
`consulted` and cited so that a later reader can check the warm-up against the
same file.

### `RaspberryPi4/Lib/hid.pi4` — U-Boot, read for one USB quirk — **light**

Almost all of this file is USB-IF HID 1.11 and HUT 1.21 (`vendor-spec`). One
behaviour is cited: `HidAttach`'s retry count and the one-millisecond wait
follow U-Boot's `usb_setup_descriptor()`, which is the fix for a real hardware
quirk described in that function's own comment. A timing workaround for a
misbehaving device is close to fact; it is listed because the file says where it
came from.

### BearSSL family — **acknowledged in the files**

`aes.pi4`, `bignum.pi4`, `drbg.pi4`, `ec256.pi4`, `ecdsa.pi4`, `gcm.pi4`,
`hkdf.pi4`, `hmac.pi4`, `rsa.pi4`, `t0vm.pi4`, `x25519.pi4`, `x509.pi4`,
`x509_blob.pi4`, `Anvil/Core/sha256.pbi` and the BearSSL-sourced vectors in
`Anvil/Core/cryptotest_vectors.pbi`.

Every one of these opens with *"Translated from BearSSL (c) 20xx Thomas Pornin —
MIT licence. The notice ships as `licenses/BearSSL-LICENSE.txt` (release
condition)."* Those headers stand as their authors wrote them; rewording a
source comment is not this lane's to do, and the acknowledgment and the retained
text both stay. BearSSL is where these algorithms' constant-time strategies and
state layouts are written down plainly, and it is cited for that.
`x509_blob.pi4` is generated material and says "DO NOT EDIT BY HAND"; the same
acknowledgment covers it.

### Generated and vocabulary material

- `RaspberryPi4/Monitor/anvil_fonts.pi4` — 4-bit coverage tables baked from
  three DejaVu faces. **Generated from the font files themselves, so this one is
  not a consulted reference in the ordinary sense**: the tables are font
  material, they are not relicensed under the project's MIT terms, and
  `licenses/DejaVu-Fonts-LICENSE.txt` ships with them.
- `Anvil/Graphics/Vulkan/vk_core_1_0.pbi` — names, values, relationships and
  ordering from the Khronos Vulkan Registry at `v1.4.350` — the interface, which
  is what makes a binding a binding. Offered as Apache-2.0 OR MIT; the MIT text
  is retained as the acknowledgment. The XML is not vendored.
- `Firmware/CYW43455/*.bin`, `*.clm_blob` — Cypress binaries, digests matched to
  pinned upstream, `binary-redist-Cypress` terms retained. Not relicensed, and
  the grant is limited to use with Cypress parts.

### Cited but with nothing taken

`RaspberryPi4/Lib/pbkdf2.pi4` cites `hostap_sha1-pbkdf2.c` only as the on-disk
statement of IEEE 802.11 Annex H.4's 4096 iterations and 32-byte output.
`Anvil/Core/memcmd.pbi` and friends are covered under `interface-facts` below.
`tools/a64/a64_interp.py` reads LLVM's AArch64 `.td` tables as encoding facts.
The OpenBSD GENET sources were read as a second description of the same MAC and
**nothing was taken from them**. They were recorded as a candidate replacement
basis while a replacement was thought to be owed; after the 2026-09-10
confirmation no replacement is owed, and they stay in the record as what they
always were — another reading of the same hardware.

### `interface-facts` — the U-Boot-shaped console

`Anvil/Core/memcmd.pbi` (67 citations), `help.pbi`, `flow_cmd.pbi`,
`settings_cmd.pbi`, `hash_cmd.pbi`, `fs_cmd.pbi`, `boot_cmd.pbi`, `net_cmd.pbi`,
`state.pbi`, `xfer.pbi`, `parse.pbi`, `settings.pbi`, `auto.pbi`,
`bootfile_cmd.pbi`, `rxbreak.pbi`, `pmfboot.pbi`, and the command tables in
`RaspberryPi4/Board/board.pi4` and `screen_cmd.pi4`.

These implement U-Boot's *command vocabulary* — `md`, `mw`, `cp`, `cmp`,
`crc32`, `base`, `sleep`, `echo`, `version`, `sha256sum` — with its argument
grammar, its width suffixes and its documented defaults, so that a line copied
out of a U-Boot session runs here. The stated purpose is operator compatibility,
the citations are to behaviour (`cmd_mem.c:143` for a default size, `:512-520`
for the report form), and the code is original: it is written in a different
language against a different console, and it diverges loudly where Anvil's
behaviour is better, announcing base-address addition that U-Boot performs
silently.

Command names, argument syntax and documented default values are the functional
interface of a program. The class is kept separate from `original` so that the
compatibility is disclosed rather than discovered: an operator should know the
vocabulary was matched on purpose, and a reader should know no U-Boot code came
with it.

## Per-source record

Every row is a reference that was read. None of them contributed code, so the
"owed" column is the same everywhere: cite it, and keep the citation.

| Source | Revision | Upstream license | Acknowledged as consulted | Retained text | What Anvil owes |
| --- | --- | --- | --- | --- | --- |
| Das U-Boot | `6d41f0a3…` (v2025.01) | GPL-2.0-or-later | yes | none needed | the citations, kept |
| Linux kernel + rpi-6.12.y | `adc21867…` (v6.12) | GPL-2.0-only / -or-later per file | yes | none needed | the citations, kept |
| BCM2711 device tree | rpi-6.12.y | GPL-2.0 | yes | none needed | the citations, kept |
| Mesa | `769e5146…` (24.3.4) | MIT | yes | `licenses/Mesa-MIT.txt` | the citations, kept |
| BearSSL | per-file acknowledgments | MIT | yes | `licenses/BearSSL-LICENSE.txt` | the citations, kept |
| Raspberry Pi armstub8 | `439b6198…` | BSD-3-Clause | yes | `licenses/RaspberryPi-armstub8-BSD-3-Clause.txt` | the citations, kept |
| Broadcom brcmfmac | `adc21867…` | ISC | yes | `licenses/Broadcom-brcmfmac-ISC.txt` | the citations, kept |
| Khronos Vulkan Registry | `a33416ed…` (v1.4.350) | Apache-2.0 OR MIT | yes | `licenses/Khronos-Vulkan-Registry-MIT.txt` | the citations, kept |
| DejaVu Fonts | `9b5d1b2f…` | DejaVu / Bitstream Vera | generated tables, not consulted behaviour | `licenses/DejaVu-Fonts-LICENSE.txt` | the font terms, which are not replaced by the project's MIT terms |
| Cypress CYW43455 firmware | `c91cd280…` | binary-redist-Cypress | **not a reference: redistributed binaries** | `licenses/Cypress-CYW43455-EULA.txt` | its own terms; the grant is limited to use with Cypress parts |
| hostap | not pinned | BSD-3-Clause | yes (facts only) | none needed | the citations, kept |
| LLVM AArch64 tables | `llvmorg-19.1.0` | Apache-2.0 WITH LLVM-exception | yes (facts only) | none needed | the citations, kept |
| py-videocore6 | not pinned | GPL-2.0-or-later | yes (corroboration only) | none needed | the citations, kept; recorded so the copyleft upstream is not mistaken for a permissive one |
| OpenBSD GENET | `d728e260…` | BSD-2-Clause (MAC) / **BSD-4-Clause (PHY)** | yes; nothing taken | none needed | the citations, kept; the four-clause PHY files stay flagged so nobody treats the set as one licence |
| IETF RFCs | per document | specification | yes | none needed | the citations, kept |
| Vendor and standards documents | per document | specification | yes | none needed | the citations, kept |

The retained texts are acknowledgments of references consulted. They attach no
terms to any Anvil file and they are not an election; the one genuine exception
is the Cypress row, whose binaries really are redistributed under their own
agreement.

## The 2026-09-10 confirmation, and what it means

**It was confirmed on 2026-09-10 that no third-party code was used; the
references were read for how the hardware behaves.**

That is a statement of fact about how this tree was written, and it replaces the
per-driver retain-versus-rewrite decision this document used to carry. What
follows from it:

- **There is no licence election to make.** Not for U-Boot, not for the Linux
  kernel, not per driver, not at all. There is nothing to retain and nothing to
  replace, so the table of what each answer would cost is gone rather than
  answered.
- **There is no corresponding-source obligation** and no GPL text is owed by
  this repository. No such text was ever added here, which was the right call
  for a different reason than the one recorded at the time.
- **No pair is `derived` or `verbatim`.** All 41 are `consulted`. The gate now
  refuses either class outright: a copied or derived block is not permitted in
  this tree; restate it or remove it.
- **Every citation is retained.** They are the provenance of the *facts* — a
  register offset, a reset order, a warm-up delay, an erratum — and they are how
  a reader who doubts one goes and checks it. Removing them would make this tree
  less verifiable, not cleaner, and no attribution was removed by this lane.
- **The one quotation is gone.** `pcie.pi4`'s device-tree fragment is restated in
  the file's own words with the citation kept as a pointer. Nothing in the tree
  is a quotation now.
- **Nothing here is a legal determination.** It is a dated statement of how the
  work was done, recorded so that the next reader does not re-derive a question
  that has been answered.

### What did not change

Existing public history. The public repository is at `3b2e5a9`, and the
confirmation says nothing about what is already published; that remains its own
question, and nothing in this lane touched history.

Publication also did not change. `PROVENANCE.json` keeps
`publication_review.status` at `held`, and `--for-publication` still refuses,
because publishing this repository is a separate, explicit instruction that has
not been given. What remains before a push is review hygiene, listed in
`docs/PUBLICATION_REVIEW.md`: bench addresses in two files, and a working tree
that another lane is mid-commit in.

## The gate, and the six things that make it bite

`tools/provenance_inventory_check.py` passes on the current tree: **665 checks**,
220 tracked source files scanned, 143 cited, 77 with no citation at all. (That is
two files more than when this pass began; other lanes commit continuously, which
is the reason the script recomputes rather than trusting a number written here.)

A gate that has never been seen to fail is not evidence of anything, so every
refusal was provoked on the real file with a byte-for-byte copy taken first, and
each one bit. Two of them enforce the 2026-09-10 confirmation and are new:

| Provoked fault | Refusal |
| --- | --- |
| **A pair recorded as `derived`** | `RaspberryPi4/Lib/genet.pi4: classified 'derived' against 'uboot-v2025.01'. a copied or derived block is not permitted in this tree; restate it or remove it. It was confirmed on 2026-09-10 that no third-party code was used; the references were read for how the hardware behaves, so the only class this tree carries against an implementation is 'consulted'.` |
| **A pair recorded as `verbatim`** | the same refusal, against `RaspberryPi4/Lib/pcie.pi4` / `linux-dt-bcm2711` |
| **A consulted pair whose file cites nothing of its source** | `classified consulted against 'bearssl' and cites nothing of it. A consulted pair must cite the source the fact came from.` |
| A retained acknowledgment text named but not on disk | `source 'bearssl' names retained text 'licenses/NOPE.txt', which is not on disk` |
| An inventory entry dropped while the citation remains in the code | `cites 'uboot-v2025.01' and the inventory does not list it` |
| An acknowledgment pointing at a heading that does not exist | `source 'uboot-v2025.01' points at acknowledgment section 'docs/THIRD_PARTY_NOTICES.md#no-such-heading', and docs/THIRD_PARTY_NOTICES.md has no such heading` |
| The table and `PROVENANCE.json` disagreeing about a classification | `PROVENANCE.json says 'consulted', the inventory table says 'original'` |

Each mutated file was restored from its copy and verified byte-identical by
SHA-256 before the next one was provoked, and the gate was run clean afterwards.

**What it cannot do, and this is the important sentence in this document.** It
finds unlisted **citations** and it enforces what the inventory **records**. It
cannot look at a procedure and tell you how it was written. The refusal on
`derived` and `verbatim` makes the ruling structural — nothing in this tree can
be recorded as copied again without the gate stopping it — but a person reading
the code is still the only thing that can check the code. The inventory rests on
the tree's habit of citing its sources, which, on the evidence of 143 files that
do it by file and line, is a good habit here. It is not a guarantee.

## Public closure hygiene — what was checked now

These are checks that do not require publishing anything, and passing them does
not authorize a push.

| Check | Result |
| --- | --- |
| Secrets in the tracked set (private keys, PEM, passwords, passphrases, PSKs, API keys, tokens) | **Clean.** No match across the tracked set. `.gitignore` excludes `*.pem`, `*.key`, `.env`, `wifi_credentials.*`, `BRCMNV.TXT`, `SETTINGS.TXT`. |
| Machine-specific and personal paths in tracked files | **Clean.** The only absolute-home-directory-shaped string anywhere in the tracked set is the detection pattern inside `tools/verify_export.py` itself, which is supposed to be there. |
| Include closure of the public tree | **Complete.** `verify_export.py --working-tree` re-run on 2026-09-10 after this pass: 352 candidate files; `RaspberryPi4/Board/board.pi4` 157, `ArduinoQ/Board/board.unoq` 58, `pi4FpGate.pi4` 4, `pi4FpState.pi4` 3. No include escapes the repository. (At `baddc30` earlier the same day it was 345/147/48/4/3; the module lane has been committing.) |
| Retained acknowledgment texts present | **Yes**, all seven under `licenses/`, including `licenses/Mesa-MIT.txt` and `licenses/RaspberryPi-armstub8-BSD-3-Clause.txt`, which were added during this pass. |
| Publication gate refuses while held | **Yes.** `verify_export.py --for-publication` fails first on the recorded reason: *publication review is not cleared: Publishing this repository is a separate, explicit instruction that has not been given.* It also reports the module lane's uncommitted work, which is that lane's to land. |
| Private bench transcripts / session handoffs in the tracked set | **Clean.** `chatgptHandoff.md` and both dated handoff docs are gitignored and listed in `forbidden_names`. |
| Private network detail | **Two items to look at, neither a secret.** Test fixtures and a host-side check carry specific bench addresses (`192.168.1.15`, `192.168.1.16` in `RaspberryPi4/Tests/tcp_multiif_emitted_gate.pi4` and `tools/payload_lifecycle_check.py`). They are RFC 1918 private-range addresses and leak nothing routable, but they are a real subnet rather than documentation values. Separately, `192.168.137.0/24` appears throughout the networking sources; that one is *deliberate and correct* — it is Windows Internet Connection Sharing's fixed subnet and the code has to know it. |
| Diagnostics in the public selection | **Answered, 2026-09-10.** The project rule is that diagnostics are in-house and are not packaged in a release; this repository tracks 34 `RaspberryPi4/Tests/` gates and declares two `RaspberryPi4/Examples/Diagnostics/` programs as public entry points. A release ZIP and a source repository are different artifacts, and `docs/PROVENANCE.md` now says so in one sentence under "Redistribution boundary" instead of leaving it implicit. |

### One relocation caught in flight

While this pass was running, the driver-module lane moved the AVS temperature
register half of `RaspberryPi4/Lib/thermal.pi4` into a separately compiled
module at `RaspberryPi4/Modules/thermal_avs.pi4`. The check script noticed
immediately: `thermal.pi4` had rows for `linux-dt-bcm2711` and `linux-v6.12` and
no longer cited either.

**Nothing was lost.** `thermal.pi4`'s own note says the facts "moved, whole and
with their citations", and the destination file does carry them. The two rows
were removed from the table because they no longer describe that file, and the
move is recorded in `PROVENANCE.json` under `third_party.relocations` with the
classifications they had. The destination is not tracked yet, so it cannot be
classified here; the check script reports it as a note and will refuse the
moment it is committed unlisted. `RaspberryPi4/Board/hw_mod.pi4` and
`RaspberryPi4/Tests/module_pipeline_emitted_gate.pi4`, from the same lane, are
in the same state: `hw_mod.pi4` carries the device-tree address translation in
its device table and the gate restates the conversion so it can check its
direction.

**The removal and the split have to land in ONE commit.** This check reads the
WORKING tree, so a committed `thermal.pi4` that still cites the documents with
the rows already deleted is just as red as the reverse - which is exactly how
the rows came to be restored once already. Classify the three destinations in
that same commit, here and in `PROVENANCE.json`.

This is what the gate is for. A file-level inventory written once is stale the
week after; one that is recomputed on every run survives other people working.

### One inventory-hygiene finding

Forty-two upstream filenames cited in source comments do not resolve in the
development reference tree those citations mostly point at. They are not
missing — they are in an older reference location, which the citations naming
them do say. But the two have diverged, and the citations that matter most for
this review are among the split: the GENET
primary source `v2025.01_bcmgenet.c`, the mailbox headers `v2025.01_mbox.h` and
`v2025.01_msg.c`, the brcmfmac SDIO sources, and `v2025.01_pcie_brcmstb.c`.

Consolidating them is cheap and would make this inventory re-checkable from one
place. It is recorded, not done: both trees are outside this repository and
neither is this lane's to reorganize.

## Proven versus reasoned

**Proven** — by reading the current source, the pinned upstream headers on disk,
and by running the checks:

- Every classification above is anchored to a citation the file itself carries,
  quoted or cited by line.
- The license of every upstream named here was read from the file header or the
  repository's own retained notice, not recalled: U-Boot `bcmgenet.c` SPDX
  `GPL-2.0+`; Linux `bcm2711.dtsi` SPDX `GPL-2.0`; `goodix.c` SPDX
  `GPL-2.0-only`; `vc4_hvs.c` SPDX `GPL-2.0-only`; Mesa `v3d_tiling.c` MIT;
  OpenBSD `bcmgenet.c` BSD-2-Clause; OpenBSD `brgphy.c` **BSD-4-Clause with the
  advertising condition**; py-videocore6 GPL-2.0-or-later; hostap BSD.
- The counts at `baddc30`: 218 source files, 207,715 lines, 143 cited, 311
  file/source pairs, 41 of them consulted across 38 files. The check script
  recomputes these; the tree moved three times during this pass.
- The hygiene results in the table above, each from a command that was run.
- The check script's five refusals, each provoked and each observed to fire.
- That the tree now contains no quotation: `pcie.pi4`'s five-line device-tree
  fragment was restated in the file's own words on 2026-09-10 and re-read after
  the edit. It was the only pair ever classified `verbatim`.

**Stated as fact on 2026-09-10, and applied here as such:**

- It was confirmed on 2026-09-10 that no third-party code was used; the
  references were read for how the hardware behaves. Every `consulted`
  classification in this document rests on that statement, not on an inference
  drawn from a file comment.

**Reasoned** — judgement, stated so it can be overruled:

- Which citations are `hardware-facts`, which are `protocol-facts` and which are
  `consulted`. The line between reading a number off a datasheet and learning a
  behaviour from a driver is an engineering reading.
- The `interface-facts` class for the U-Boot-shaped command set.
- The depth labels (primary reference / moderate / light) on individual files.
  They say how much of a file's behaviour came from reading rather than from a
  document; they are useful to the next person debugging it and nothing more.

**Not established, and must not be read as established:**

- This is not legal advice and no lawyer has looked at it.
- It does not prove the classifications are complete for code that carries no
  comment. The check script finds *unlisted citations*; it cannot look at a
  procedure and tell you how it was written.
- Passing `verify_export.py` proves packaging, privacy and include closure. It
  has never proved anything about provenance and still does not.
- Nothing here authorizes a push. Publication is a separate, explicit
  instruction.

## Complete file inventory

One row per file/source pair, 311 rows, generated from `PROVENANCE.json`
`third_party.classified_files` and checked against the sources by
`tools/provenance_inventory_check.py`. The 75 files that carry no citation at
all are `original` and are not listed; `--list-original` enumerates them.

| File | Class | Upstream source | License | Obligation |
| --- | --- | --- | --- | --- |
| `Anvil/Applications/Forum/http_head.pbi` | protocol-facts | ietf-rfc | RFC publication | cite the document; no copied implementation |
| `Anvil/Core/argfmt.pbi` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `Anvil/Core/auto.pbi` | interface-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `Anvil/Core/boot_cmd.pbi` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `Anvil/Core/boot_cmd.pbi` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `Anvil/Core/boot_cmd.pbi` | interface-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `Anvil/Core/bootfile_cmd.pbi` | interface-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `Anvil/Core/crc.pbi` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `Anvil/Core/crypto_cmd.pbi` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `Anvil/Core/crypto_cmd.pbi` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `Anvil/Core/cryptotest_vectors.pbi` | consulted | bearssl | MIT | cite the source; no notice obligation; `licenses/BearSSL-LICENSE.txt` retained as an acknowledgment |
| `Anvil/Core/cryptotest_vectors.pbi` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `Anvil/Core/cryptotest_vectors.pbi` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `Anvil/Core/dhcpd.pbi` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `Anvil/Core/flow_cmd.pbi` | interface-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `Anvil/Core/flow_cmd.pbi` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `Anvil/Core/fs_cmd.pbi` | interface-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `Anvil/Core/hash_cmd.pbi` | interface-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `Anvil/Core/help.pbi` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `Anvil/Core/help.pbi` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `Anvil/Core/help.pbi` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Board/boot_timing.pi4` | hardware-facts | vendor-spec | vendor document | cite the document; no notice obligation |
| `RaspberryPi4/Board/screen_cmd.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document (HVS behaviour read); no notice obligation |
| `Anvil/Graphics/Vulkan/vk_v3d_backend.pi4` | consulted | mesa-24.3.4 | MIT | reference read for V3D behaviour; cite; no code taken |
| `Anvil/Graphics/Vulkan/vk_v3d_backend.pi4` | consulted | khronos-vulkan | Apache-2.0 OR MIT (registry) | specification read for semantics; cite; no code taken |
| `Anvil/Graphics/Vulkan/vk_spirv.pbi` | consulted | khronos-vulkan | Apache-2.0 OR MIT (registry) | SPIR-V specification and the Vulkan environment appendix read for the binary layout, the opcode numbers and the enumerants; cite; no code taken |
| `Anvil/Graphics/Vulkan/vk_spirv_fixtures.pbi` | consulted | khronos-vulkan | Apache-2.0 OR MIT (registry) | SPIR-V specification read for the module layout the hand-assembled fixtures follow; cite; no code taken |
| `Anvil/Graphics/Vulkan/vk_v3d_shader.pi4` | consulted | mesa-24.3.4 | MIT | reference read for the shaded-vertex layout, the VPM segment rule and the thread-end ordering; cite; no code taken |
| `RaspberryPi4/Examples/Diagnostics/vulkanTriangleProof.pi4` | consulted | khronos-vulkan | Apache-2.0 OR MIT (registry) | specification read for the SPIR-V and Vulkan semantics the diagnostic exercises; cite; no code taken |
| `Anvil/Graphics/Vulkan/vk_descriptor.pbi` | consulted | khronos-vulkan | Apache-2.0 OR MIT (registry) | specification and registry read for the descriptor set layout, pool, allocation and update rules and for the structure members, their order and their widths; cite; no code taken |
| `Anvil/Graphics/Vulkan/vk_interp_expect.pbi` | consulted | khronos-vulkan | Apache-2.0 OR MIT (registry) | specification read for the single-sample fragment sample position and for VK_FORMAT_B8G8R8A8_UNORM's byte order; cite; no code taken |
| `RaspberryPi4/Examples/Diagnostics/vulkanVaryingProof.pi4` | consulted | khronos-vulkan | Apache-2.0 OR MIT (registry) | specification read for the SPIR-V and Vulkan semantics the diagnostic exercises; cite; no code taken |
| `RaspberryPi4/Examples/Diagnostics/pi4CoreWitness.pi4` | hardware-facts | vendor-spec | vendor document | cite the document; no notice obligation |
| `RaspberryPi4/Board/hw_mod.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Board/hw_mod.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Board/hw_mod.pi4` | hardware-facts | vendor-spec | vendor document | cite the document; no notice obligation |
| `RaspberryPi4/Modules/thermal_avs.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Modules/thermal_avs.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Tests/module_pipeline_emitted_gate.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `Anvil/Core/help.pbi` | interface-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `Anvil/Core/memcmd.pbi` | interface-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `Anvil/Core/memcmd.pbi` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `Anvil/Core/net_cmd.pbi` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Tests/net_xfer_pump_ownership_emitted_gate.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `Anvil/Core/net_cmd.pbi` | interface-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `Anvil/Core/netcfg.pbi` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `Anvil/Core/netconsole.pbi` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `Anvil/Core/netif.pbi` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `Anvil/Core/netll.pbi` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `Anvil/Core/parse.pbi` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `Anvil/Core/parse.pbi` | interface-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `Anvil/Core/pmfboot.pbi` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `Anvil/Core/pmfboot.pbi` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `Anvil/Core/pmfboot.pbi` | interface-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `Anvil/Core/rxbreak.pbi` | interface-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `Anvil/Core/settings.pbi` | hardware-facts | broadcom-brcmfmac | ISC | cite the document; no notice obligation |
| `Anvil/Core/settings.pbi` | interface-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `Anvil/Core/settings_cmd.pbi` | interface-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `Anvil/Core/sha256.pbi` | consulted | bearssl | MIT | cite the source; no notice obligation; `licenses/BearSSL-LICENSE.txt` retained as an acknowledgment |
| `Anvil/Core/sha256.pbi` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `Anvil/Core/sha256.pbi` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `Anvil/Core/sntp_codec.pbi` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `Anvil/Core/state.pbi` | interface-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `Anvil/Core/state.pbi` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `Anvil/Core/usb_cmd.pbi` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `Anvil/Core/wallclock.pbi` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `Anvil/Core/xfer.pbi` | interface-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `Anvil/Graphics/Vulkan/vk_core_1_0.pbi` | consulted | khronos-vulkan | MIT (of Apache-2.0 OR MIT) | cite the source; no notice obligation; `licenses/Khronos-Vulkan-Registry-MIT.txt` retained as an acknowledgment |
| `Anvil/Hal/abi.pbi` | hardware-facts | rpi-armstub8 | BSD-3-Clause | cite the document; no notice obligation |
| `Anvil/Hal/abi.pbi` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `Anvil/Hal/hal.pbi` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `Anvil/Hal/hal.pbi` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `Anvil/Hal/hal.pbi` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `Anvil/Hal/hal.pbi` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `Anvil/Hal/hal.pbi` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `ArduinoQ/Board/board.unoq` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `ArduinoQ/Board/board.unoq` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `ArduinoQ/Board/board.unoq` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `ArduinoQ/Board/hw_addr_q.unoq` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `ArduinoQ/Board/hw_addr_q.unoq` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `ArduinoQ/Board/hw_file_q.unoq` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `ArduinoQ/Board/hw_gpio_q.unoq` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `ArduinoQ/Board/hw_gpio_q.unoq` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `ArduinoQ/Board/hw_i2c_q.unoq` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `ArduinoQ/Board/hw_i2c_q.unoq` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `ArduinoQ/Board/hw_id_q.unoq` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `ArduinoQ/Board/hwtimer_q.unoq` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `ArduinoQ/Board/hwtimer_q.unoq` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `ArduinoQ/Board/memmap_q.unoq` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `ArduinoQ/Board/qcon_q.unoq` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `ArduinoQ/Board/qcon_q.unoq` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `ArduinoQ/Board/qefi_q.unoq` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `ArduinoQ/Board/qefi_q.unoq` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `ArduinoQ/Board/qstubs_q.unoq` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `ArduinoQ/Board/qstubs_q.unoq` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `ArduinoQ/Board/qstubs_q.unoq` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `ArduinoQ/Intrinsics/qcm2290_hardware.def` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `ArduinoQ/Lib/geni_i2c.unoq` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `ArduinoQ/Lib/geni_i2c.unoq` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `ArduinoQ/Lib/tlmm.unoq` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `ArduinoQ/Lib/tlmm.unoq` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Board/armstub8.asm` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Board/armstub8.asm` | consulted | rpi-armstub8 | BSD-3-Clause | cite the source; no notice obligation; `licenses/RaspberryPi-armstub8-BSD-3-Clause.txt` retained as an acknowledgment |
| `RaspberryPi4/Board/board.pi4` | hardware-facts | broadcom-brcmfmac | ISC | cite the document; no notice obligation |
| `RaspberryPi4/Board/board.pi4` | reference-only | cypress-fw | binary-redist-Cypress | cite the document; no notice obligation |
| `RaspberryPi4/Board/board.pi4` | reference-only | dejavu-fonts | DejaVu/Bitstream Vera | cite the document; no notice obligation |
| `RaspberryPi4/Board/board.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Board/board.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Board/board.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Board/board.pi4` | hardware-facts | rpi-armstub8 | BSD-3-Clause | cite the document; no notice obligation |
| `RaspberryPi4/Board/board.pi4` | interface-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Board/board.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Board/boot.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Board/boot.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Board/cache.pi4` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Board/cursor_input.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Board/display.pi4` | reference-only | dejavu-fonts | DejaVu/Bitstream Vera | cite the document; no notice obligation |
| `RaspberryPi4/Board/display.pi4` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Board/display_globals.pi4` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Board/dsi_cmd.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Board/dsi_cmd.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Board/eth.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Board/eth_globals.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Board/eth_globals.pi4` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Board/hw_addr.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Board/hw_board.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Board/hw_boot.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Board/hw_boot.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Board/hw_boot.pi4` | hardware-facts | rpi-armstub8 | BSD-3-Clause | cite the document; no notice obligation |
| `RaspberryPi4/Board/hw_boot.pi4` | consulted | uboot-v2025.01 | GPL-2.0-or-later | cite the source; no notice obligation |
| `RaspberryPi4/Board/hw_boot.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Board/hw_con.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Board/hw_file.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Board/hw_gpio.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Board/hw_gpio.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Board/hw_i2c.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Board/hw_link.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Board/hw_link.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Board/hw_touch.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Board/hw_touch.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Board/hw_usb.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi3/Lib/interrupt_timer.pbi` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Board/memmap.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Board/memmap.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Board/memmap.pi4` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Board/memmap.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Board/power.pi4` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Board/screen_cmd.pi4` | interface-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Board/screen_geom.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Board/screen_geom.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Board/screen_source.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Board/storage.pi4` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Board/storage.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Board/touch_cmd.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Board/touch_cmd.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Board/touch_cmd.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Board/v3d_console.pi4` | reference-only | dejavu-fonts | DejaVu/Bitstream Vera | cite the document; no notice obligation |
| `RaspberryPi4/Examples/Diagnostics/pi4FpGate.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Examples/Diagnostics/pi4FpState.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Examples/Diagnostics/pi4FpState.pi4` | hardware-facts | llvm-19.1.0 | Apache-2.0 WITH LLVM-exception | cite the document; no notice obligation |
| `RaspberryPi4/Examples/Diagnostics/pi4FpState.pi4` | hardware-facts | rpi-armstub8 | BSD-3-Clause | cite the document; no notice obligation |
| `RaspberryPi4/Examples/Diagnostics/pi4FpState.pi4` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Examples/Diagnostics/pi4FpState.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/aes.pi4` | consulted | bearssl | MIT | cite the source; no notice obligation; `licenses/BearSSL-LICENSE.txt` retained as an acknowledgment |
| `RaspberryPi4/Lib/aes.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Lib/aes.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/bignum.pi4` | consulted | bearssl | MIT | cite the source; no notice obligation; `licenses/BearSSL-LICENSE.txt` retained as an acknowledgment |
| `RaspberryPi4/Lib/core_worker.pi4` | hardware-facts | rpi-armstub8 | BSD-3-Clause | cite the document; no notice obligation |
| `RaspberryPi4/Lib/cyw43.pi4` | consulted | broadcom-brcmfmac | ISC | cite the source; no notice obligation; `licenses/Broadcom-brcmfmac-ISC.txt` retained as an acknowledgment |
| `RaspberryPi4/Lib/cyw43.pi4` | reference-only | cypress-fw | binary-redist-Cypress | cite the document; no notice obligation |
| `RaspberryPi4/Lib/cyw43.pi4` | reference-only | hostap | BSD-3-Clause | cite the document; no notice obligation |
| `RaspberryPi4/Lib/cyw43.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/cyw43.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/cyw43.pi4` | hardware-facts | rpi-armstub8 | BSD-3-Clause | cite the document; no notice obligation |
| `RaspberryPi4/Lib/cyw43.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/cyw43_rx_glom.pi4` | consulted | broadcom-brcmfmac | ISC | cite the source; no notice obligation; `licenses/Broadcom-brcmfmac-ISC.txt` retained as an acknowledgment |
| `RaspberryPi4/Lib/cyw43_rx_glom.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/dhcp.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Lib/display.pi4` | reference-only | dejavu-fonts | DejaVu/Bitstream Vera | cite the document; no notice obligation |
| `RaspberryPi4/Lib/display.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/display.pi4` | consulted | uboot-v2025.01 | GPL-2.0-or-later | cite the source; no notice obligation |
| `RaspberryPi4/Lib/dma.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/dma.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/dma.pi4` | hardware-facts | rpi-armstub8 | BSD-3-Clause | cite the document; no notice obligation |
| `RaspberryPi4/Lib/dma.pi4` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Lib/dma.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/dns.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Lib/drbg.pi4` | consulted | bearssl | MIT | cite the source; no notice obligation; `licenses/BearSSL-LICENSE.txt` retained as an acknowledgment |
| `RaspberryPi4/Lib/drbg.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/drbg.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/dsi_host.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/dsi_host.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/dsi_host.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/dsi_panel_v2.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/dsi_panel_v2.pi4` | consulted | linux-v6.12 | GPL-2.0 (per file) | cite the source; no notice obligation |
| `RaspberryPi4/Lib/dsi_panel_v2.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/dsi_panel_v2_dcs.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/dsi_panel_v2_dcs.pi4` | consulted | linux-v6.12 | GPL-2.0 (per file) | cite the source; no notice obligation |
| `RaspberryPi4/Lib/ec256.pi4` | consulted | bearssl | MIT | cite the source; no notice obligation; `licenses/BearSSL-LICENSE.txt` retained as an acknowledgment |
| `RaspberryPi4/Lib/ecdsa.pi4` | consulted | bearssl | MIT | cite the source; no notice obligation; `licenses/BearSSL-LICENSE.txt` retained as an acknowledgment |
| `RaspberryPi4/Lib/ecdsa.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Lib/emmc.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/emmc.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/entropy.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/entropy.pi4` | consulted | linux-v6.12 | GPL-2.0 (per file) | cite the source; no notice obligation |
| `RaspberryPi4/Lib/entropy.pi4` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Lib/entropy.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/fat.pi4` | hardware-facts | broadcom-brcmfmac | ISC | cite the document; no notice obligation |
| `RaspberryPi4/Lib/fat.pi4` | reference-only | cypress-fw | binary-redist-Cypress | cite the document; no notice obligation |
| `RaspberryPi4/Lib/fat.pi4` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Lib/fat.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/gcm.pi4` | consulted | bearssl | MIT | cite the source; no notice obligation; `licenses/BearSSL-LICENSE.txt` retained as an acknowledgment |
| `RaspberryPi4/Lib/genet.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/genet.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/genet.pi4` | consulted | uboot-v2025.01 | GPL-2.0-or-later | cite the source; no notice obligation |
| `RaspberryPi4/Lib/genet.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/gpio.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/gpio.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/hid.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/hid.pi4` | consulted | uboot-v2025.01 | GPL-2.0-or-later | cite the source; no notice obligation |
| `RaspberryPi4/Lib/hid.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/hkdf.pi4` | consulted | bearssl | MIT | cite the source; no notice obligation; `licenses/BearSSL-LICENSE.txt` retained as an acknowledgment |
| `RaspberryPi4/Lib/hkdf.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Lib/hmac.pi4` | consulted | bearssl | MIT | cite the source; no notice obligation; `licenses/BearSSL-LICENSE.txt` retained as an acknowledgment |
| `RaspberryPi4/Lib/hmac.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Lib/hmacsha1.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Lib/hmacsha1.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/http.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Lib/hvs.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/hvs.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/i2c.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/i2c.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/i2c.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/keywrap.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Lib/keywrap.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/link.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Lib/mailbox.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/mailbox.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/mailbox.pi4` | hardware-facts | rpi-armstub8 | BSD-3-Clause | cite the document; no notice obligation |
| `RaspberryPi4/Lib/mailbox.pi4` | consulted | uboot-v2025.01 | GPL-2.0-or-later | cite the source; no notice obligation |
| `RaspberryPi4/Lib/mmu.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/exceptions.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/interrupts.pi4` | hardware-facts | rpi-armstub8 | BSD-3-Clause | cite the document; no notice obligation |
| `RaspberryPi4/Lib/interrupts.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/mmu.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/mmu.pi4` | hardware-facts | llvm-19.1.0 | Apache-2.0 WITH LLVM-exception | cite the document; no notice obligation |
| `RaspberryPi4/Lib/mmu.pi4` | hardware-facts | rpi-armstub8 | BSD-3-Clause | cite the document; no notice obligation |
| `RaspberryPi4/Lib/mmu.pi4` | consulted | uboot-v2025.01 | GPL-2.0-or-later | cite the source; no notice obligation |
| `RaspberryPi4/Lib/mmu.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/mmu_secondary.pi4` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Lib/neon.pi4` | consulted | mesa-24.3.4 | MIT | cite the source; no notice obligation; `licenses/Mesa-MIT.txt` retained as an acknowledgment |
| `RaspberryPi4/Lib/net.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Lib/net.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/net.pi4` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Lib/net.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/pbkdf2.pi4` | reference-only | hostap | BSD-3-Clause | cite the document; no notice obligation |
| `RaspberryPi4/Lib/pbkdf2.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Lib/pbkdf2.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/pcie.pi4` | consulted | linux-dt-bcm2711 | GPL-2.0 | cite the source; no notice obligation |
| `RaspberryPi4/Lib/pcie.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/pcie.pi4` | consulted | uboot-v2025.01 | GPL-2.0-or-later | cite the source; no notice obligation |
| `RaspberryPi4/Lib/pcie.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/pwm.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/pwm.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/pwm.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/rsa.pi4` | consulted | bearssl | MIT | cite the source; no notice obligation; `licenses/BearSSL-LICENSE.txt` retained as an acknowledgment |
| `RaspberryPi4/Lib/rsa.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Lib/safety.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/safety.pi4` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Lib/safety.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/sdio.pi4` | consulted | broadcom-brcmfmac | ISC | cite the source; no notice obligation; `licenses/Broadcom-brcmfmac-ISC.txt` retained as an acknowledgment |
| `RaspberryPi4/Lib/sdio.pi4` | reference-only | cypress-fw | binary-redist-Cypress | cite the document; no notice obligation |
| `RaspberryPi4/Lib/sdio.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/sdio.pi4` | consulted | linux-v6.12 | GPL-2.0 (per file) | cite the source; no notice obligation |
| `RaspberryPi4/Lib/sdio.pi4` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Lib/sdio.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/sha1.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Lib/sha1.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/t0vm.pi4` | consulted | bearssl | MIT | cite the source; no notice obligation; `licenses/BearSSL-LICENSE.txt` retained as an acknowledgment |
| `RaspberryPi4/Lib/tcp.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Lib/tftp.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Lib/tftp.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/tftp.pi4` | consulted | uboot-v2025.01 | GPL-2.0-or-later | cite the source; no notice obligation |
| `RaspberryPi4/Lib/timer.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/timer.pi4` | hardware-facts | rpi-armstub8 | BSD-3-Clause | cite the document; no notice obligation |
| `RaspberryPi4/Lib/timer.pi4` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Lib/timer.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/touch_goodix.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/touch_goodix.pi4` | consulted | linux-v6.12 | GPL-2.0 (per file) | cite the source; no notice obligation |
| `RaspberryPi4/Lib/touch_goodix.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/uart.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/uart.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/uart.pi4` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Lib/uart.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/usbmsc.pi4` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Lib/usbmsc.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/v3d.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/v3d.pi4` | consulted | linux-v6.12 | GPL-2.0 (per file) | cite the source; no notice obligation |
| `RaspberryPi4/Lib/v3d.pi4` | consulted | mesa-24.3.4 | MIT | cite the source; no notice obligation; `licenses/Mesa-MIT.txt` retained as an acknowledgment |
| `RaspberryPi4/Lib/v3d.pi4` | reference-only | py-videocore6 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Lib/v3d.pi4` | hardware-facts | rpi-armstub8 | BSD-3-Clause | cite the document; no notice obligation |
| `RaspberryPi4/Lib/v3d.pi4` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Lib/v3d.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/v3dqpu.pi4` | consulted | mesa-24.3.4 | MIT | cite the source; no notice obligation; `licenses/Mesa-MIT.txt` retained as an acknowledgment |
| `RaspberryPi4/Lib/v3dqpu.pi4` | reference-only | py-videocore6 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Lib/wifi.pi4` | hardware-facts | broadcom-brcmfmac | ISC | cite the document; no notice obligation |
| `RaspberryPi4/Lib/wifi.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/wpa2sup.pi4` | hardware-facts | broadcom-brcmfmac | ISC | cite the document; no notice obligation |
| `RaspberryPi4/Lib/wpa2sup.pi4` | reference-only | cypress-fw | binary-redist-Cypress | cite the document; no notice obligation |
| `RaspberryPi4/Lib/wpa2sup.pi4` | reference-only | hostap | BSD-3-Clause | cite the document; no notice obligation |
| `RaspberryPi4/Lib/wpa2sup.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Lib/wpa2sup.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/wpa2sup.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/x25519.pi4` | consulted | bearssl | MIT | cite the source; no notice obligation; `licenses/BearSSL-LICENSE.txt` retained as an acknowledgment |
| `RaspberryPi4/Lib/x25519.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Lib/x509.pi4` | consulted | bearssl | MIT | cite the source; no notice obligation; `licenses/BearSSL-LICENSE.txt` retained as an acknowledgment |
| `RaspberryPi4/Lib/x509_blob.pi4` | consulted | bearssl | MIT | cite the source; no notice obligation; `licenses/BearSSL-LICENSE.txt` retained as an acknowledgment |
| `RaspberryPi4/Lib/xhci.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/xhci.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/xhci.pi4` | hardware-facts | rpi-armstub8 | BSD-3-Clause | cite the document; no notice obligation |
| `RaspberryPi4/Lib/xhci.pi4` | consulted | uboot-v2025.01 | GPL-2.0-or-later | cite the source; no notice obligation |
| `RaspberryPi4/Lib/xhci.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Monitor/anvil_fonts.pi4` | consulted | dejavu-fonts | DejaVu/Bitstream Vera | cite the source; no notice obligation; `licenses/DejaVu-Fonts-LICENSE.txt` retained as an acknowledgment |
| `RaspberryPi4/Tests/Fixtures/dsi_panel_v1.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Tests/Fixtures/dsi_panel_v1.pi4` | consulted | linux-v6.12 | GPL-2.0 (per file) | cite the source; no notice obligation |
| `RaspberryPi4/Tests/Fixtures/dsi_panel_v1.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Tests/dhcp_emitted_gate.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Tests/i2c_abort_resume_probe.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Tests/i2c_abort_resume_probe.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Tests/i2c_boot_trace_emitted_gate.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Tests/i2c_mcu_read_timeline_probe.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Tests/i2c_mcu_write_timeline_probe.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Tests/i2c_touch_recovery_probe.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Tests/pbkdf2_step_emitted_gate.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Tests/touch_goodix_compile.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Tests/touch_goodix_compile.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |

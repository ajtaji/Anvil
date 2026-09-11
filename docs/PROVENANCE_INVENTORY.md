# Provenance inventory

Status: **desk review, 2026-09-10. The publication hold stands.** This document
records engineering evidence. It is not a legal determination, it does not
relicense anything, and it does not decide the question the hold is waiting on.
It removes no attribution and no notice.

Companion records:

- `docs/PUBLICATION_REVIEW.md` — the publication boundary and what is still owed.
- `docs/THIRD_PARTY_NOTICES.md` — the notices themselves.
- `PROVENANCE.json` — the same inventory in machine-readable form, under
  `third_party`.
- `tools/provenance_inventory_check.py` — the gate that keeps the two agreeing.

## What was inventoried, and how

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
| `derived` | 40 | Translated from, or structurally following, a third-party implementation. Treat as a derivative work of that source. |
| `verbatim` | 1 | A passage copied unchanged, inside a comment, as its own citation. |
| `reference-only` | 14 | Cited as corroboration or as a candidate basis; no material taken. |

The remaining 75 files, and every procedure in the 143 that carries no citation,
are **original**. `--list-original` prints them.

### The line this inventory draws

A register offset is a fact about silicon. Anyone who reads the same document
writes the same number, and `#GENET_SYS_PORT_CTRL = $0004` is the only correct
answer. Those citations exist so a reader can check the number, not because
anything was taken.

A *sequence* is different. "Set RBUF flush bit 1, wait 10 us, clear it, wait
10 us, write zero, wait 10 us, then UMAC_CMD = 0, then SW_RESET | LCL_LOOP_EN
for 2 us" is a choice somebody made and wrote down, and reproducing it —
including its asymmetries, in its order, with its constants — is following an
implementation, not reading a datasheet. Where a file says so in its own words,
this inventory takes the file at its word.

The hard cases are marked below with how strong the case is, because "derived"
is a spectrum and pretending otherwise would make this document useless for the
decision it exists to support.

## The project's intended license — recorded, not inferred

**MIT, `Copyright (c) 2026 PureMetal Labs`.** It is stated in four places that
agree: the root `LICENSE`, `README.md` under "License", `docs/LICENSING.md`
("Unless a file or subtree carries a different notice…"), and the vault's own
hold note, which records that the owner selected MIT for original Anvil source.
There is no ambiguity to resolve on that point.

## Derived and verbatim blocks, in detail

Line numbers are from the current working tree at local `main` `9e0e55e` and
will drift; the procedure names will not.

### `RaspberryPi4/Lib/genet.pi4` — U-Boot, GPL-2.0-or-later — **strong**

The file names U-Boot v2025.01 `drivers/net/bcmgenet.c` as **"THE PRIMARY
SOURCE"** and cites it as `[U:line]` throughout. This is the clearest case in
the tree, and the file's own comments are the evidence.

| Anvil procedure | Upstream | What is taken |
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

### `RaspberryPi4/Lib/mmu.pi4` — U-Boot, GPL-2.0-or-later — **strong, narrow**

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
- Against that: the file also adopts `cache_v8.c`'s **ordering** rule
  (`dcache_disable` clears `C|M` before flushing) and says so, which is a
  behavioural choice taken from the implementation, not from the manual.

**Inventory-accuracy note, not a licensing one:** the header still says
`cache.S` "is NOT in this tree, so the algorithm below is the canonical one".
`cache.S` was fetched on 2026-08-29 and is now a reference file. The comment is
stale. It is left exactly as it stands — correcting a source header is not this
lane's to do — and is recorded here so the next reader is not misled.

### `RaspberryPi4/Lib/v3d.pi4` — Mesa (MIT) and Linux (GPL-2.0+) — **mixed**

The file states plainly that the BCM2711 manual contains exactly one fact about
V3D and that **"everything below is transcribed from four sources"**. Those four
split cleanly by license:

- **Mesa 24.3.4 (MIT)** — the control-list packet layouts (`v3d_packet.xml`),
  the QPU field/opcode tables, the TFU and tiling descriptions, and the
  register-write order of `v3dx_simulator.c`'s job submission. Packet bit
  layouts are hardware description; the job-submission *order* and the
  render-list construction in `V3dRclBuild`, `V3dRenderBegin`,
  `V3dClStoreTileBufferGeneral`, `V3dShaderRecordBegin`, `V3dAttrRecord`,
  `V3dClMulticoreSupertileCfg` and `V3dCsdBegin` follow Mesa. **MIT — compatible
  with the project license, notice required, no source offer.**
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
list) and `RaspberryPi4/Lib/neon.pi4` (tiling/format material) are Mesa-derived
on the same basis. Those are the easy half of V3D: MIT in, MIT out, one notice.

### `RaspberryPi4/Lib/cyw43.pi4`, `cyw43_rx_glom.pi4` — Broadcom brcmfmac, ISC — **already resolved**

Both carry the ISC copyright line in their own headers and point at
`licenses/Broadcom-brcmfmac-ISC.txt`. `cyw43_rx_glom.pi4` says "Adapted from
Linux brcmfmac `sdio.c`/`bcmsdh.c` receive-glom semantics" in its second line.
ISC is permissive and compatible; the obligation is notice retention and it is
met. This one is done.

`RaspberryPi4/Lib/sdio.pi4` is the awkward neighbour: its CYW43-facing half
cites the same ISC files, but its host-controller half cites
`rpi-6.12.y_bcm2835-mmc.c`, `sdhci.h` and the Linux MMC core — **GPL-2.0**, not
ISC. The register maps are facts; the initialization ordering follows the
driver. Classified `derived` against both sources so the distinction is not lost.

### `RaspberryPi4/Lib/display.pi4` and `mailbox.pi4` — U-Boot, GPL-2.0+ — **moderate**

`DisplayInit()` builds the same combined firmware message U-Boot's
`struct msg_setup` builds, with the same nine tags in the same order
(`v2025.01_msg.c:36-45`, `:166-189`), plus a tenth Anvil adds. The tag numbers
are interface facts from `mbox.h`; *which* tags to send in *what* order in *one*
message is U-Boot's arrangement, and the file says it is reproduced deliberately.

`mailbox.pi4` is more explicit. Its header records that the kernel and U-Boot
differ on the tag "value length" word, that Anvil's list path **follows U-Boot**,
and the reason: *"reproducing it byte for byte removes one variable from the
next thing that goes wrong."* That is a statement of structural derivation.

### `RaspberryPi4/Lib/tftp.pi4` — U-Boot, GPL-2.0+ — **moderate**

The protocol is RFC 1350 and most of the file is `protocol-facts`. But the
retransmission design, the server-TID adoption, the timeout handler's re-send of
the last ACK and the option handling are each cited to
`v2025.01_net_tftp.c` by line (`:264-278`, `:341-362`, `:597-616`, `:702-712`),
and the header says of one of them "This is U-Boot's design, deliberately".

### `RaspberryPi4/Lib/xhci.pi4` and `pcie.pi4` — U-Boot, GPL-2.0+ — **moderate**

`xhci.pi4` names U-Boot's `xhci.h` as **"THE SPECIFICATION for this file"** —
and for a controller with no public datasheet, a vendor-neutral register header
genuinely is the specification, so the constant block is `hardware-facts`. The
init path is not: `xh_MemInit`, `XhciMaxPacket`, `xh_Control`, `xh_Bulk` and
`XhciBulkReady` cite `xhci-mem.c`, `xhci-ring.c` and `xhci.c` routines by name.

`pcie.pi4` programs the outbound/inbound windows following
`v2025.01_pcie_brcmstb.c`, and quotes that file's `brcm_pcie_config_address`
comment. It also contains the tree's **one `verbatim` block**: `pcie.pi4:224-232`
reproduces five lines of `bcm2711.dtsi:577-583` — the DMA erratum comment and the
`dma-ranges` property — introduced with *"comment included verbatim because it is
the citation"*. It is a quotation of a hardware erratum inside a comment, with
attribution, and is almost certainly fine; it is listed because an inventory that
quietly drops the one verbatim copy is not an inventory.

### `RaspberryPi4/Board/hw_boot.pi4` — U-Boot, GPL-2.0+ — **moderate**

`HwBootToEl1()`'s EL2→EL1 register block (CNTHCTL_EL2, CNTVOFF_EL2, VPIDR_EL2,
VMPIDR_EL2, CPTR_EL2, HSTR_EL2, HCR_EL2, then SPSR/ELR and `eret`) is the shape
of U-Boot's `armv8_switch_to_el1`, and the file names
`v2025.01_transition.S` as "the two-step shape to transcribe". The arm64 `Image`
header layout comes from `v2025.01_image.c` and is `hardware-facts`.

### `RaspberryPi4/Board/armstub8.asm` — Raspberry Pi tools, BSD-3-Clause — **resolved**

A declared translation and modification of `armstubs/armstub8.S` at commit
`439b6198…`, with the **complete** three-clause notice retained verbatim at the
top of the file and `setup_gic` marked "transcribed from `armstub8.S:214-235`".
BSD-3-Clause is compatible with MIT. The only gap was that the retained text did
not also live in `licenses/`, which mattered because the upstream terms bind
binary distributions of the assembled stub too. `licenses/RaspberryPi-armstub8-BSD-3-Clause.txt`
now carries it. Nothing in the source header was touched.

### `RaspberryPi4/Lib/touch_goodix.pi4`, `dsi_panel_v2.pi4`, `dsi_panel_v2_dcs.pi4`, `Tests/Fixtures/dsi_panel_v1.pi4` — Linux, GPL-2.0 — **weak to moderate**

Panel initialization sequences and touch-controller register maps taken from
`rpi-6.12.y` `goodix.c` (GPL-2.0-**only**), `panel-waveshare-dsi-v2.c` and
`panel-raspberrypi-touchscreen.c`. A DCS command sequence for a specific panel
is close to pure hardware fact — the panel accepts one sequence and no other —
but the kernel driver is where it is written down, and `goodix.c` being
GPL-2.0-only (no "or later") narrows the options if the retain route is taken.
Classified `derived` so the decision is made knowingly.

### `RaspberryPi4/Lib/entropy.pi4` — Linux, GPL-2.0 — **weak**

The RNG200 register map is corroborated **three ways** — Raspberry Pi's kernel
fork, mainline Linux, and U-Boot — and the file shows they agree character for
character on every offset and mask. That is the textbook argument that these are
facts. What keeps it on the derived list is the enable/warm-up ordering, which
follows `iproc-rng200.c`. Listed as `derived` for disclosure; it is the weakest
claim in this section and would be the cheapest to re-derive from the register
semantics alone.

### `RaspberryPi4/Lib/hid.pi4` — U-Boot, GPL-2.0+ — **weak**

Almost all of this file is USB-IF HID 1.11 and HUT 1.21 (`vendor-spec`). One
behaviour is cited: `HidAttach`'s retry count and the one-millisecond wait
follow U-Boot's `usb_setup_descriptor()`, which is the fix for a real hardware
quirk described in that function's own comment. A timing workaround for a
misbehaving device is close to fact; it is listed because the file says where it
came from.

### BearSSL family — MIT — **resolved**

`aes.pi4`, `bignum.pi4`, `drbg.pi4`, `ec256.pi4`, `ecdsa.pi4`, `gcm.pi4`,
`hkdf.pi4`, `hmac.pi4`, `rsa.pi4`, `t0vm.pi4`, `x25519.pi4`, `x509.pi4`,
`x509_blob.pi4`, `Anvil/Core/sha256.pbi` and the BearSSL-sourced vectors in
`Anvil/Core/cryptotest_vectors.pbi`.

Every one of these opens with *"Translated from BearSSL (c) 20xx Thomas Pornin —
MIT licence. The notice ships as `licenses/BearSSL-LICENSE.txt` (release
condition)."* These are declared translations, they are correctly attributed,
the license text ships, and MIT-in-MIT-out needs no decision. `x509_blob.pi4` is
generated from BearSSL-generated C and says "DO NOT EDIT BY HAND" — same
license, same obligation.

### Generated and vocabulary material — **resolved**

- `RaspberryPi4/Monitor/anvil_fonts.pi4` — 4-bit coverage tables baked from
  three DejaVu faces. Derived font material, not MIT; `licenses/DejaVu-Fonts-LICENSE.txt`
  ships with it.
- `Anvil/Graphics/Vulkan/vk_core_1_0.pbi` — names, values, relationships and
  ordering from the Khronos Vulkan Registry at `v1.4.350`. Apache-2.0 OR MIT,
  MIT elected, text retained. The XML is not vendored.
- `Firmware/CYW43455/*.bin`, `*.clm_blob` — Cypress binaries, digests matched to
  pinned upstream, `binary-redist-Cypress` terms retained. Not relicensed, and
  the grant is limited to use with Cypress parts.

### Cited but with nothing taken

`RaspberryPi4/Lib/pbkdf2.pi4` cites `hostap_sha1-pbkdf2.c` only as the on-disk
statement of IEEE 802.11 Annex H.4's 4096 iterations and 32-byte output.
`Anvil/Core/memcmd.pbi` and friends are covered under `interface-facts` below.
`tools/a64/a64_interp.py` reads LLVM's AArch64 `.td` tables as encoding facts.
The OpenBSD GENET sources are the candidate replacement basis and **no Anvil
source derives from them today**.

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
interface of a program. This is the weakest derivation claim in the tree, and it
is called out as a separate class rather than buried in either "original" or
"derived" because it is the one a reviewer should decide about explicitly rather
than have decided for them.

## Per-source obligations and compatibility

| Source | Revision | License | Notice | Source offer | Compatible with MIT project? |
| --- | --- | --- | --- | --- | --- |
| Das U-Boot | `6d41f0a3…` (v2025.01) | GPL-2.0-or-later | required, **text not yet shipped** | **yes, if retained** | **No** |
| Linux kernel + rpi-6.12.y | `adc21867…` (v6.12) | GPL-2.0-only / -or-later per file | required, **text not yet shipped** | **yes, if retained** | **No** |
| BCM2711 device tree | rpi-6.12.y | GPL-2.0 | required for the verbatim quotation | if retained | **No** |
| Mesa | `769e5146…` (24.3.4) | MIT | `licenses/Mesa-MIT.txt` | no | **Yes** |
| BearSSL | per-file notices | MIT | `licenses/BearSSL-LICENSE.txt` | no | **Yes** |
| Raspberry Pi armstub8 | `439b6198…` | BSD-3-Clause | `licenses/RaspberryPi-armstub8-BSD-3-Clause.txt` | no | **Yes** |
| Broadcom brcmfmac | `adc21867…` | ISC | `licenses/Broadcom-brcmfmac-ISC.txt` | no | **Yes** |
| Khronos Vulkan Registry | `a33416ed…` (v1.4.350) | Apache-2.0 OR MIT → MIT | `licenses/Khronos-Vulkan-Registry-MIT.txt` | no | **Yes** |
| DejaVu Fonts | `9b5d1b2f…` | DejaVu / Bitstream Vera | `licenses/DejaVu-Fonts-LICENSE.txt` | no | **Yes** |
| Cypress CYW43455 firmware | `c91cd280…` | binary-redist-Cypress | `licenses/Cypress-CYW43455-EULA.txt` | no | separately licensed binary, **not relicensed** |
| hostap | not pinned | BSD-3-Clause | none (facts only) | no | **Yes** |
| LLVM AArch64 tables | `llvmorg-19.1.0` | Apache-2.0 WITH LLVM-exception | none (facts only) | no | **Yes** |
| py-videocore6 | not pinned | GPL-2.0-or-later | none (corroboration only) | no | No — but nothing is taken |
| OpenBSD GENET | `d728e260…` | BSD-2-Clause (MAC) / **BSD-4-Clause (PHY)** | if adopted | no | MAC yes; **PHY advertising clause needs its own review** |
| IETF RFCs | per document | specification | none | no | **Yes** |
| Vendor and standards documents | per document | specification | none | no | **Yes** |

"Source offer" means the GPL's requirement to make the corresponding source of
the derived work available to recipients. It is the obligation with the widest
reach, because it attaches to the Anvil files that contain the derived blocks,
not only to the upstream ones.

## The decision this hold is waiting on

**Nothing in this inventory decides it.** The choice is the owner's, it is per
driver, and it is the same choice the hold note recorded as pending:

> **Retain** the applicable GPL-2.0 components with their terms and notices
> alongside original MIT code, **or** replace the derived blocks with
> independently derived or permissively licensed work.

The MIT, ISC and BSD material is not part of this question. It is settled:
notices retained, texts shipped, compatible. The question is **only** about the
files derived from U-Boot and from Linux.

### Per driver, with what each answer costs

| Driver / file | Upstream | Retain: what must ship | Replace: what must be rewritten | Notes |
| --- | --- | --- | --- | --- |
| `RaspberryPi4/Lib/genet.pi4` | U-Boot `bcmgenet.c`, GPL-2.0+ | GPL-2.0 text; a per-file notice naming U-Boot and the revision; corresponding-source offer covering this file | `GenetUmacReset`, `GenetDisableDma`, `GenetEnableDma`, `GenetRxRingInit`, `GenetRxDescsInit`, `GenetTxRingInit`, `GenetSend`, `GenetRecv`, `GenetWriteHwAddr`, `GenetInterfaceSet`, `GenetAdjustLink` — the bring-up and data path. The register block survives either way. | The candidate basis is OpenBSD (BSD-2-Clause MAC). A replacement must pass emitted-code and real traffic checks; this driver carries the console. **Nothing has been written or tested.** |
| `RaspberryPi4/Lib/mmu.pi4` | U-Boot `cache.S`, GPL-2.0+ | same three obligations, narrowly scoped to two procedures | `MmuFlushDCacheAll` and `MmuInvalidateDCacheAll`, plus the `dcache_disable` ordering rule adopted from `cache_v8.c` | Cheapest replacement in the tree. The walk is the architectural algorithm; the Arm ARM gives the `DC CISW` operand layout directly, and silicon proof already exists (`pi4MmuCycleDF` 8/8, `pi4MmuFlush` 4/4) to re-run against. |
| `RaspberryPi4/Lib/v3d.pi4` | Linux `v3d_gem.c`, `bcm2835-power.c`, GPL-2.0+ | same three obligations for the Linux-derived parts only | `V3dInvalidateCaches()` and the power/reset/ASB-bridge sequence | The Mesa half (MIT) is unaffected either way and is the bulk of the file. This is a small, well-bounded replacement. |
| `RaspberryPi4/Lib/sdio.pi4` | Linux MMC / `bcm2835-mmc.c`, GPL-2.0 | same three obligations | host-controller init ordering | The ISC brcmfmac half is unaffected. |
| `RaspberryPi4/Lib/display.pi4`, `mailbox.pi4` | U-Boot `msg.c`, `mbox.h`, GPL-2.0+ | same three obligations | `DisplayInit()`'s combined-message composition and the list path's value-length convention | Replacement is genuinely cheap — the alternative convention is the kernel's, which the file already documents and which the single-tag path already uses. The stated reason for following U-Boot is bring-up risk, not necessity. |
| `RaspberryPi4/Lib/tftp.pi4` | U-Boot `net_tftp.c`, GPL-2.0+ | same three obligations | retransmission policy, TID adoption, option handling | RFC 1350/2347-2349 specify all of it; this is re-derivable from the RFCs already cited alongside. Nothing here has ever run on hardware, so there is no regression risk to weigh. |
| `RaspberryPi4/Lib/xhci.pi4`, `pcie.pi4` | U-Boot `xhci*.c`, `pcie_brcmstb.c`, GPL-2.0+ | same three obligations | controller init, ring management, window programming | The largest replacement after GENET. `pcie.pi4`'s verbatim device-tree quotation is separable and could stay as an attributed quotation under either answer. |
| `RaspberryPi4/Board/hw_boot.pi4` | U-Boot `transition.S`, GPL-2.0+ | same three obligations | `HwBootToEl1()`'s EL2→EL1 register block | The register set is architectural; the sequence is documented in the Arm ARM. Cheap. Compile-verified only today. |
| `touch_goodix.pi4`, `dsi_panel_v2*.pi4`, `Tests/Fixtures/dsi_panel_v1.pi4` | Linux panel/touch drivers, GPL-2.0(-only) | same three obligations; note `goodix.c` is GPL-2.0-**only** | panel DCS sequences and the touch register map | Weak derivation, but `goodix.c`'s "only" removes the or-later flexibility. Panel vendors publish these sequences; a vendor-document basis would settle it. |
| `entropy.pi4`, `hid.pi4` | Linux `iproc-rng200.c`; U-Boot `usb.c` | same three obligations | RNG enable ordering; one retry/delay constant | Weakest claims in the tree. Cheapest to re-derive of anything listed. |
| `Anvil/Core/memcmd.pbi` and the command set | U-Boot command behaviour | a disclosure that the console vocabulary is modelled on U-Boot | nothing, if the interface-facts classification holds | **This is a classification decision, not a rewrite decision.** No U-Boot code is present. What is at stake is whether a compatible command vocabulary and argument grammar is disclosed as derivation. Deciding this one costs nothing but must be decided explicitly. |

### A third thing the decision must cover, and it is not a driver

Existing public history. The public repository is at `3b2e5a9`, and a
current-tree replacement does not change what is already published. The hold note
records this as a separate question. It is still separate, and nothing in this
lane touched history.

### What happens after the answer

- **If "retain" for a driver:** add `licenses/GPL-2.0-or-later.txt`, add that
  file's notice to `docs/THIRD_PARTY_NOTICES.md`, set its
  `license_text_pending_decision` to `false` in `PROVENANCE.json`, and record
  how corresponding source is offered. The check script then passes on that
  source. **Do not add a GPL text before the answer** — shipping one is itself a
  statement of election.
- **If "replace" for a driver:** the replacement keeps its own new upstream's
  notices, the derived entries move to `original` or to the new source, and the
  replacement must pass the same emitted-code and hardware checks the current
  driver passes. A licensing repair that becomes an untested network regression
  is a worse outcome than the hold.

## The gate, and the five things that make it bite

`tools/provenance_inventory_check.py` passes on the current tree: **665 checks**,
218 tracked source files scanned, 143 cited, 75 with no citation at all.

A gate that has never been seen to fail is not evidence of anything, so each of
its five refusals was provoked on a scratch copy and each one bit:

| Provoked fault | Refusal |
| --- | --- |
| A retained license text named but not on disk | `source 'bearssl' names retained text 'licenses/NOPE.txt', which is not on disk` |
| A source with derived files declaring it needs no notice | `classified derived against 'uboot-v2025.01', but that source is recorded as needing no notice. A derivative work needs one, or the classification is wrong.` |
| An inventory entry dropped while the citation remains in the code | `cites 'uboot-v2025.01' and the inventory does not list it` |
| A notice pointing at a heading that does not exist | `points at notice section '…#no-such-heading', and docs/THIRD_PARTY_NOTICES.md has no such heading` |
| The table and `PROVENANCE.json` disagreeing about a classification | `PROVENANCE.json says 'derived', the inventory table says 'original'` |

Both mutated files were restored and verified byte-identical by SHA-256
afterwards.

**What it cannot do, and this is the important sentence in this document.** It
finds unlisted **citations**, not uncited **copies**. A block translated from
somewhere and committed with no comment is invisible to this gate and to every
other check in this repository. The whole inventory rests on the tree's habit of
citing its sources — which, on the evidence of 143 files that do it by file and
line, is a good habit here. It is not a guarantee.

## Public closure hygiene — what was checked now

These are checks that do not require publishing anything. They are **not**
license-compatibility checks and passing them does not lift the hold.

| Check | Result |
| --- | --- |
| Secrets in the tracked set (private keys, PEM, passwords, passphrases, PSKs, API keys, tokens) | **Clean.** No match across the tracked set. `.gitignore` excludes `*.pem`, `*.key`, `.env`, `wifi_credentials.*`, `BRCMNV.TXT`, `SETTINGS.TXT`. |
| Machine-specific and personal paths in tracked files | **Clean.** The only absolute-home-directory-shaped string anywhere in the tracked set is the detection pattern inside `tools/verify_export.py` itself, which is supposed to be there. |
| Include closure of the public tree | **Complete.** `verify_export.py --working-tree` at `baddc30`: 345 candidate files; `RaspberryPi4/Board/board.pi4` 147, `ArduinoQ/Board/board.unoq` 48, `pi4FpGate.pi4` 4, `pi4FpState.pi4` 3. No include escapes the repository. |
| Required notice files present | **Yes**, and two more are now required and present: `licenses/Mesa-MIT.txt` and `licenses/RaspberryPi-armstub8-BSD-3-Clause.txt`. |
| Publication gate refuses while held | **Yes.** `verify_export.py --for-publication` fails with the recorded reason. |
| Private bench transcripts / session handoffs in the tracked set | **Clean.** `chatgptHandoff.md` and both dated handoff docs are gitignored and listed in `forbidden_names`. |
| Private network detail | **Two items to look at, neither a secret.** Test fixtures and a host-side check carry specific bench addresses (`192.168.1.15`, `192.168.1.16` in `RaspberryPi4/Tests/tcp_multiif_emitted_gate.pi4` and `tools/payload_lifecycle_check.py`). They are RFC 1918 private-range addresses and leak nothing routable, but they are a real subnet rather than documentation values. Separately, `192.168.137.0/24` appears throughout the networking sources; that one is *deliberate and correct* — it is Windows Internet Connection Sharing's fixed subnet and the code has to know it. |
| Diagnostics in the public selection | **A boundary question for the owner, not a defect.** The project rule is that diagnostics are in-house and are not packaged in a release. This repository tracks 34 `RaspberryPi4/Tests/` gates and declares two `RaspberryPi4/Examples/Diagnostics/` programs as public entry points, and `docs/PROVENANCE.md` expressly permits "focused reproducible host or emitted-code tests" in the public tree. Those two statements can both be true — a release ZIP and a source repository are different artifacts — but the distinction is currently implicit. Worth one sentence in `docs/PROVENANCE.md` either way. |

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
moment it is committed unlisted. `RaspberryPi4/Board/hw_mod.pi4`, from the same
lane, is in the same state.

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
  file/source pairs, 38 files carrying a derived or verbatim block. The check
  script recomputes these; the tree moved three times during this pass.
- The hygiene results in the table above, each from a command that was run.
- The check script's five refusals, each provoked and each observed to fire.
- That no later decision on the hold exists: the vault was searched again on
  2026-09-10 and the hold note, the lane ledger and the current handoff all still
  say pending.

**Reasoned** — judgement, stated so it can be overruled:

- The fact/expression line itself. Calling a register table `hardware-facts` and
  a reset sequence `derived` is a defensible engineering reading, not a ruling.
- The `interface-facts` class for the U-Boot-shaped command set.
- Strength labels (strong / moderate / weak) on individual derivations.
- The replacement-cost estimates in the decision table. They are scoped from the
  code, but nothing has been written, so no estimate has been tested.
- That the `pcie.pi4` verbatim quotation is de minimis.

**Not established, and must not be read as established:**

- This is not legal advice and no lawyer has looked at it.
- It does not prove the classifications are complete for code that carries no
  comment. A block derived from something and never cited would not appear here;
  the check script finds *unlisted citations*, not *uncited derivations*.
- Passing `verify_export.py` proves packaging, privacy and include closure. It
  has never proved license compatibility and still does not.

## Complete file inventory

One row per file/source pair, 311 rows, generated from `PROVENANCE.json`
`third_party.derived_files` and checked against the sources by
`tools/provenance_inventory_check.py`. The 75 files that carry no citation at
all are `original` and are not listed; `--list-original` enumerates them.

| File | Class | Upstream source | License | Obligation |
| --- | --- | --- | --- | --- |
| `Anvil/Core/argfmt.pbi` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `Anvil/Core/auto.pbi` | interface-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `Anvil/Core/boot_cmd.pbi` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `Anvil/Core/boot_cmd.pbi` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `Anvil/Core/boot_cmd.pbi` | interface-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `Anvil/Core/bootfile_cmd.pbi` | interface-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `Anvil/Core/crc.pbi` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `Anvil/Core/crypto_cmd.pbi` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `Anvil/Core/crypto_cmd.pbi` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `Anvil/Core/cryptotest_vectors.pbi` | derived | bearssl | MIT | retain notice; ship `licenses/BearSSL-LICENSE.txt` |
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
| `Anvil/Core/help.pbi` | interface-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `Anvil/Core/memcmd.pbi` | interface-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `Anvil/Core/memcmd.pbi` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `Anvil/Core/net_cmd.pbi` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
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
| `Anvil/Core/sha256.pbi` | derived | bearssl | MIT | retain notice; ship `licenses/BearSSL-LICENSE.txt` |
| `Anvil/Core/sha256.pbi` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `Anvil/Core/sha256.pbi` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `Anvil/Core/sntp_codec.pbi` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `Anvil/Core/state.pbi` | interface-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `Anvil/Core/state.pbi` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `Anvil/Core/usb_cmd.pbi` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `Anvil/Core/wallclock.pbi` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `Anvil/Core/xfer.pbi` | interface-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `Anvil/Graphics/Vulkan/vk_core_1_0.pbi` | derived | khronos-vulkan | MIT (of Apache-2.0 OR MIT) | retain notice; ship `licenses/Khronos-Vulkan-Registry-MIT.txt` |
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
| `RaspberryPi4/Board/armstub8.asm` | derived | rpi-armstub8 | BSD-3-Clause | retain notice; ship `licenses/RaspberryPi-armstub8-BSD-3-Clause.txt` |
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
| `RaspberryPi4/Board/hw_boot.pi4` | derived | uboot-v2025.01 | GPL-2.0-or-later | retain notice; license text NOT YET SHIPPED; offer corresponding source; **not MIT-compatible** |
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
| `RaspberryPi4/Board/memmap.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Board/memmap.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Board/memmap.pi4` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
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
| `RaspberryPi4/Lib/aes.pi4` | derived | bearssl | MIT | retain notice; ship `licenses/BearSSL-LICENSE.txt` |
| `RaspberryPi4/Lib/aes.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Lib/aes.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/bignum.pi4` | derived | bearssl | MIT | retain notice; ship `licenses/BearSSL-LICENSE.txt` |
| `RaspberryPi4/Lib/core_worker.pi4` | hardware-facts | rpi-armstub8 | BSD-3-Clause | cite the document; no notice obligation |
| `RaspberryPi4/Lib/cyw43.pi4` | derived | broadcom-brcmfmac | ISC | retain notice; ship `licenses/Broadcom-brcmfmac-ISC.txt` |
| `RaspberryPi4/Lib/cyw43.pi4` | reference-only | cypress-fw | binary-redist-Cypress | cite the document; no notice obligation |
| `RaspberryPi4/Lib/cyw43.pi4` | reference-only | hostap | BSD-3-Clause | cite the document; no notice obligation |
| `RaspberryPi4/Lib/cyw43.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/cyw43.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/cyw43.pi4` | hardware-facts | rpi-armstub8 | BSD-3-Clause | cite the document; no notice obligation |
| `RaspberryPi4/Lib/cyw43.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/cyw43_rx_glom.pi4` | derived | broadcom-brcmfmac | ISC | retain notice; ship `licenses/Broadcom-brcmfmac-ISC.txt` |
| `RaspberryPi4/Lib/cyw43_rx_glom.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/dhcp.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Lib/display.pi4` | reference-only | dejavu-fonts | DejaVu/Bitstream Vera | cite the document; no notice obligation |
| `RaspberryPi4/Lib/display.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/display.pi4` | derived | uboot-v2025.01 | GPL-2.0-or-later | retain notice; license text NOT YET SHIPPED; offer corresponding source; **not MIT-compatible** |
| `RaspberryPi4/Lib/dma.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/dma.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/dma.pi4` | hardware-facts | rpi-armstub8 | BSD-3-Clause | cite the document; no notice obligation |
| `RaspberryPi4/Lib/dma.pi4` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Lib/dma.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/dns.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Lib/drbg.pi4` | derived | bearssl | MIT | retain notice; ship `licenses/BearSSL-LICENSE.txt` |
| `RaspberryPi4/Lib/drbg.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/drbg.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/dsi_host.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/dsi_host.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/dsi_host.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/dsi_panel_v2.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/dsi_panel_v2.pi4` | derived | linux-v6.12 | GPL-2.0 (per file) | retain notice; license text NOT YET SHIPPED; offer corresponding source; **not MIT-compatible** |
| `RaspberryPi4/Lib/dsi_panel_v2.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/dsi_panel_v2_dcs.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/dsi_panel_v2_dcs.pi4` | derived | linux-v6.12 | GPL-2.0 (per file) | retain notice; license text NOT YET SHIPPED; offer corresponding source; **not MIT-compatible** |
| `RaspberryPi4/Lib/ec256.pi4` | derived | bearssl | MIT | retain notice; ship `licenses/BearSSL-LICENSE.txt` |
| `RaspberryPi4/Lib/ecdsa.pi4` | derived | bearssl | MIT | retain notice; ship `licenses/BearSSL-LICENSE.txt` |
| `RaspberryPi4/Lib/ecdsa.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Lib/emmc.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/emmc.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/entropy.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/entropy.pi4` | derived | linux-v6.12 | GPL-2.0 (per file) | retain notice; license text NOT YET SHIPPED; offer corresponding source; **not MIT-compatible** |
| `RaspberryPi4/Lib/entropy.pi4` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Lib/entropy.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/fat.pi4` | hardware-facts | broadcom-brcmfmac | ISC | cite the document; no notice obligation |
| `RaspberryPi4/Lib/fat.pi4` | reference-only | cypress-fw | binary-redist-Cypress | cite the document; no notice obligation |
| `RaspberryPi4/Lib/fat.pi4` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Lib/fat.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/gcm.pi4` | derived | bearssl | MIT | retain notice; ship `licenses/BearSSL-LICENSE.txt` |
| `RaspberryPi4/Lib/genet.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/genet.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/genet.pi4` | derived | uboot-v2025.01 | GPL-2.0-or-later | retain notice; license text NOT YET SHIPPED; offer corresponding source; **not MIT-compatible** |
| `RaspberryPi4/Lib/genet.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/gpio.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/gpio.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/hid.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/hid.pi4` | derived | uboot-v2025.01 | GPL-2.0-or-later | retain notice; license text NOT YET SHIPPED; offer corresponding source; **not MIT-compatible** |
| `RaspberryPi4/Lib/hid.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/hkdf.pi4` | derived | bearssl | MIT | retain notice; ship `licenses/BearSSL-LICENSE.txt` |
| `RaspberryPi4/Lib/hkdf.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Lib/hmac.pi4` | derived | bearssl | MIT | retain notice; ship `licenses/BearSSL-LICENSE.txt` |
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
| `RaspberryPi4/Lib/mailbox.pi4` | derived | uboot-v2025.01 | GPL-2.0-or-later | retain notice; license text NOT YET SHIPPED; offer corresponding source; **not MIT-compatible** |
| `RaspberryPi4/Lib/mmu.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/mmu.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/mmu.pi4` | hardware-facts | llvm-19.1.0 | Apache-2.0 WITH LLVM-exception | cite the document; no notice obligation |
| `RaspberryPi4/Lib/mmu.pi4` | hardware-facts | rpi-armstub8 | BSD-3-Clause | cite the document; no notice obligation |
| `RaspberryPi4/Lib/mmu.pi4` | derived | uboot-v2025.01 | GPL-2.0-or-later | retain notice; license text NOT YET SHIPPED; offer corresponding source; **not MIT-compatible** |
| `RaspberryPi4/Lib/mmu.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/mmu_secondary.pi4` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Lib/neon.pi4` | derived | mesa-24.3.4 | MIT | retain notice; ship `licenses/Mesa-MIT.txt` |
| `RaspberryPi4/Lib/net.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Lib/net.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/net.pi4` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Lib/net.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/pbkdf2.pi4` | reference-only | hostap | BSD-3-Clause | cite the document; no notice obligation |
| `RaspberryPi4/Lib/pbkdf2.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Lib/pbkdf2.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/pcie.pi4` | verbatim | linux-dt-bcm2711 | GPL-2.0 | retain notice; license text NOT YET SHIPPED; offer corresponding source; **not MIT-compatible** |
| `RaspberryPi4/Lib/pcie.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/pcie.pi4` | derived | uboot-v2025.01 | GPL-2.0-or-later | retain notice; license text NOT YET SHIPPED; offer corresponding source; **not MIT-compatible** |
| `RaspberryPi4/Lib/pcie.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/pwm.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/pwm.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/pwm.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/rsa.pi4` | derived | bearssl | MIT | retain notice; ship `licenses/BearSSL-LICENSE.txt` |
| `RaspberryPi4/Lib/rsa.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Lib/safety.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/safety.pi4` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Lib/safety.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/sdio.pi4` | derived | broadcom-brcmfmac | ISC | retain notice; ship `licenses/Broadcom-brcmfmac-ISC.txt` |
| `RaspberryPi4/Lib/sdio.pi4` | reference-only | cypress-fw | binary-redist-Cypress | cite the document; no notice obligation |
| `RaspberryPi4/Lib/sdio.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/sdio.pi4` | derived | linux-v6.12 | GPL-2.0 (per file) | retain notice; license text NOT YET SHIPPED; offer corresponding source; **not MIT-compatible** |
| `RaspberryPi4/Lib/sdio.pi4` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Lib/sdio.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/sha1.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Lib/sha1.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/t0vm.pi4` | derived | bearssl | MIT | retain notice; ship `licenses/BearSSL-LICENSE.txt` |
| `RaspberryPi4/Lib/tcp.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Lib/tftp.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Lib/tftp.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/tftp.pi4` | derived | uboot-v2025.01 | GPL-2.0-or-later | retain notice; license text NOT YET SHIPPED; offer corresponding source; **not MIT-compatible** |
| `RaspberryPi4/Lib/timer.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/timer.pi4` | hardware-facts | rpi-armstub8 | BSD-3-Clause | cite the document; no notice obligation |
| `RaspberryPi4/Lib/timer.pi4` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Lib/timer.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/touch_goodix.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/touch_goodix.pi4` | derived | linux-v6.12 | GPL-2.0 (per file) | retain notice; license text NOT YET SHIPPED; offer corresponding source; **not MIT-compatible** |
| `RaspberryPi4/Lib/touch_goodix.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/uart.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/uart.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/uart.pi4` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Lib/uart.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/usbmsc.pi4` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Lib/usbmsc.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/v3d.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/v3d.pi4` | derived | linux-v6.12 | GPL-2.0 (per file) | retain notice; license text NOT YET SHIPPED; offer corresponding source; **not MIT-compatible** |
| `RaspberryPi4/Lib/v3d.pi4` | derived | mesa-24.3.4 | MIT | retain notice; ship `licenses/Mesa-MIT.txt` |
| `RaspberryPi4/Lib/v3d.pi4` | reference-only | py-videocore6 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Lib/v3d.pi4` | hardware-facts | rpi-armstub8 | BSD-3-Clause | cite the document; no notice obligation |
| `RaspberryPi4/Lib/v3d.pi4` | hardware-facts | uboot-v2025.01 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Lib/v3d.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/v3dqpu.pi4` | derived | mesa-24.3.4 | MIT | retain notice; ship `licenses/Mesa-MIT.txt` |
| `RaspberryPi4/Lib/v3dqpu.pi4` | reference-only | py-videocore6 | GPL-2.0-or-later | cite the document; no notice obligation |
| `RaspberryPi4/Lib/wifi.pi4` | hardware-facts | broadcom-brcmfmac | ISC | cite the document; no notice obligation |
| `RaspberryPi4/Lib/wifi.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/wpa2sup.pi4` | hardware-facts | broadcom-brcmfmac | ISC | cite the document; no notice obligation |
| `RaspberryPi4/Lib/wpa2sup.pi4` | reference-only | cypress-fw | binary-redist-Cypress | cite the document; no notice obligation |
| `RaspberryPi4/Lib/wpa2sup.pi4` | reference-only | hostap | BSD-3-Clause | cite the document; no notice obligation |
| `RaspberryPi4/Lib/wpa2sup.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Lib/wpa2sup.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/wpa2sup.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Lib/x25519.pi4` | derived | bearssl | MIT | retain notice; ship `licenses/BearSSL-LICENSE.txt` |
| `RaspberryPi4/Lib/x25519.pi4` | protocol-facts | ietf-rfc | IETF specification | cite the document; no notice obligation |
| `RaspberryPi4/Lib/x509.pi4` | derived | bearssl | MIT | retain notice; ship `licenses/BearSSL-LICENSE.txt` |
| `RaspberryPi4/Lib/x509_blob.pi4` | derived | bearssl | MIT | retain notice; ship `licenses/BearSSL-LICENSE.txt` |
| `RaspberryPi4/Lib/xhci.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Lib/xhci.pi4` | hardware-facts | linux-v6.12 | GPL-2.0 (per file) | cite the document; no notice obligation |
| `RaspberryPi4/Lib/xhci.pi4` | hardware-facts | rpi-armstub8 | BSD-3-Clause | cite the document; no notice obligation |
| `RaspberryPi4/Lib/xhci.pi4` | derived | uboot-v2025.01 | GPL-2.0-or-later | retain notice; license text NOT YET SHIPPED; offer corresponding source; **not MIT-compatible** |
| `RaspberryPi4/Lib/xhci.pi4` | hardware-facts | vendor-spec | vendor/standards document | cite the document; no notice obligation |
| `RaspberryPi4/Monitor/anvil_fonts.pi4` | derived | dejavu-fonts | DejaVu/Bitstream Vera | retain notice; ship `licenses/DejaVu-Fonts-LICENSE.txt` |
| `RaspberryPi4/Tests/Fixtures/dsi_panel_v1.pi4` | hardware-facts | linux-dt-bcm2711 | GPL-2.0 | cite the document; no notice obligation |
| `RaspberryPi4/Tests/Fixtures/dsi_panel_v1.pi4` | derived | linux-v6.12 | GPL-2.0 (per file) | retain notice; license text NOT YET SHIPPED; offer corresponding source; **not MIT-compatible** |
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

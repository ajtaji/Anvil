# References consulted

It was confirmed on 2026-09-10 that no third-party code was used; the references
were read for how the hardware behaves. The projects and documents listed below
are those references: they were read to learn how a part is driven — register
sequences, ordering, quirks, wire formats — and the result was implemented
independently for Anvil. No file here is a copy or a translation of any of them.

That is why this document is titled the way it is. These sections are
acknowledgments of what was read, not notices for incorporated code. They are
kept because a citation is how a reader checks a hardware fact, and removing one
would make this tree harder to verify rather than cleaner.

The permissive license texts retained in [`licenses/`](../licenses/) are kept in
the same spirit — as acknowledgments of references consulted. They are not an
election, they do not attach terms to any Anvil file, and nothing in this
repository is relicensed by their presence. **One entry on this page is not a
reference at all:** the CYW43455 firmware binaries are third-party files that
really are redistributed here, under their own terms, and they are listed last so
the difference is not blurred.

Per-file classification, with every citation, is in
[`PROVENANCE_INVENTORY.md`](PROVENANCE_INVENTORY.md); the same data is in
`PROVENANCE.json` under `third_party`, and
`tools/provenance_inventory_check.py` fails if a file cites something this
document does not acknowledge — or if anything in the tree is ever recorded as
copied or derived again.

Publishing this repository remains a separate, explicit instruction. See
[`PUBLICATION_REVIEW.md`](PUBLICATION_REVIEW.md).

## Das U-Boot

U-Boot v2025.01, commit `6d41f0a39d6423c8e57e92ebbe9f8c0333a63f72`, was read for
how this board's peripherals are brought up. What was learned from it — and then
written independently — appears in:

| Anvil file | What was read |
| --- | --- |
| `RaspberryPi4/Lib/genet.pi4` | `drivers/net/bcmgenet.c`, for the GENET reset, ring and data-path behaviour |
| `RaspberryPi4/Lib/mmu.pi4` | `arch/arm/cpu/armv8/cache.S`, `cache_v8.c`, for the all-level set/way maintenance the architecture defines |
| `RaspberryPi4/Lib/display.pi4`, `RaspberryPi4/Lib/mailbox.pi4` | `drivers/video/bcm2835/msg.c`, `bcm2835_mbox.h`, for the firmware mailbox interface |
| `RaspberryPi4/Lib/tftp.pi4` | `net/tftp.c`, alongside RFC 1350 and RFC 2347-2349 |
| `RaspberryPi4/Lib/xhci.pi4`, `RaspberryPi4/Lib/pcie.pi4` | `drivers/usb/host/xhci*.c`, `drivers/pci/pcie_brcmstb.c`, for controller and window behaviour |
| `RaspberryPi4/Board/hw_boot.pi4` | `arch/arm/cpu/armv8/transition.S`, for the EL2→EL1 register set the Arm ARM documents |
| `RaspberryPi4/Lib/hid.pi4` | `common/usb.c`, for a hardware quirk in the first Get Descriptor |

Register definitions, mailbox tag numbers and the arm64 `Image` header layout
read from the same tree are hardware and interface facts and are cited as such.

Anvil's console also speaks a deliberately U-Boot-compatible command vocabulary —
`md`, `mw`, `cp`, `cmp`, `crc32`, `base`, `sleep`, `echo`, `version`,
`sha256sum` — with its argument grammar and documented defaults, so that a line
out of a U-Boot session runs here. That is an interface, implemented from
scratch; it is classified `interface-facts` and is disclosed here because a
reader deserves to know the compatibility is intentional.

## Linux kernel

Linux v6.12, commit `adc218676eef25575469234709c2d87185ca223a`, and the Raspberry
Pi `rpi-6.12.y` fork were read for the behaviour of parts with little or no
public documentation:

| Anvil file | What was read |
| --- | --- |
| `RaspberryPi4/Lib/v3d.pi4` | `drivers/gpu/drm/v3d/v3d_gem.c`, `drivers/pmdomain/bcm/bcm2835-power.c`, for cache invalidation and the power/reset/ASB bridge sequence |
| `RaspberryPi4/Lib/sdio.pi4` | `drivers/mmc/host/bcm2835-mmc.c`, `sdhci.h`, the MMC core, for host-controller initialization |
| `RaspberryPi4/Lib/touch_goodix.pi4` | `drivers/input/touchscreen/goodix.c`, for the touch controller's register map |
| `RaspberryPi4/Lib/dsi_panel_v2.pi4`, `dsi_panel_v2_dcs.pi4`, `RaspberryPi4/Tests/Fixtures/dsi_panel_v1.pi4` | `drivers/gpu/drm/panel/panel-waveshare-dsi-v2.c`, `panel-raspberrypi-touchscreen.c`, for panel DCS sequences these panels accept |
| `RaspberryPi4/Lib/entropy.pi4` | `drivers/char/hw_random/iproc-rng200.c`, for the RNG200 enable and warm-up order |

Register headers such as `v3d_regs.h` are tables of definitions and are cited as
hardware facts. The brcmfmac protocol and transport sources in the same tree are
ISC rather than GPL and are acknowledged separately below.

## Linux brcmfmac sources

`RaspberryPi4/Lib/cyw43.pi4`, `cyw43_rx_glom.pi4` and the CYW43-facing half of
`sdio.pi4` were written against the behaviour described by Linux
`drivers/net/wireless/broadcom/brcm80211/brcmfmac/` at the revision above —
`bcmsdh.c`, `sdio.c`, `bcdc.c` (2010 Broadcom Corporation), `fwil.h` (2012) and
`chip.c` (2014), all ISC. The SDIO transport, the BCDC protocol framing and the
receive-glom semantics are documented nowhere else.

The copyright lines those files carry are repeated in the Anvil sources that
consulted them, and the complete
[ISC text](../licenses/Broadcom-brcmfmac-ISC.txt) is retained in `licenses/` as
an acknowledgment. This is separate from the firmware binaries listed at the
bottom of this page.

Sources: [pinned brcmfmac directory](https://github.com/torvalds/linux/tree/adc218676eef25575469234709c2d87185ca223a/drivers/net/wireless/broadcom/brcm80211/brcmfmac),
[pinned license text](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/LICENSES/deprecated/ISC).

## BCM2711 device tree

`bcm2711.dtsi`, `bcm2711-rpi-4-b.dts` and their includes, from the `rpi-6.12.y`
fork, are the board's own description of itself: block addresses, bus ranges,
interrupt numbers, `phy-mode`, panel timings, and the PCIe wrapper's 3 GiB DMA
erratum. That material is hardware description and is cited by file and line
throughout `RaspberryPi4/`, most consequentially in `RaspberryPi4/Lib/pcie.pi4`,
where the erratum and the inbound window it forces are stated in Anvil's own
words with the device-tree lines named as the place to check them.

## Mesa V3D backend

`RaspberryPi4/Lib/v3d.pi4`, `RaspberryPi4/Lib/v3dqpu.pi4` and
`RaspberryPi4/Lib/neon.pi4` were written from the V3D control-list packet
layouts, QPU instruction field and opcode tables, the instruction-restriction
list, tiling and TFU descriptions, and the job-submission register order
described by the Broadcom V3D backend of Mesa at tag `mesa-24.3.4`, commit
`769e51468b49b2a42f0a0eaf71cf9eed5ff4e5de`. For a block whose vendor
documentation contains one fact about V3D, that backend is the specification.

No Mesa source file is vendored here. The complete
[Mesa MIT text](../licenses/Mesa-MIT.txt) is retained as an acknowledgment.
Per-routine classification is in
[`PROVENANCE_INVENTORY.md`](PROVENANCE_INVENTORY.md).

## BearSSL

The portable and Raspberry Pi cryptographic implementations were written against
BearSSL's descriptions of the same algorithms — its constant-time strategies,
its state layouts, and, for X.509, the structure of its validation engine. The
per-file acknowledgments in those sources name BearSSL and Thomas Pornin, and the
complete [BearSSL MIT text](../licenses/BearSSL-LICENSE.txt) is retained in
`licenses/`.

Those source headers are left exactly as their authors wrote them. This lane
removed no acknowledgment from any file and does not rewrite what a header says.

## Raspberry Pi firmware stub

`RaspberryPi4/Board/armstub8.asm` was written for the same job as
[Raspberry Pi's armstub8.S](https://github.com/raspberrypi/tools/blob/439b6198a9b340de5998dd14a26a0d9d38a6bcac/armstubs/armstub8.S)
at commit `439b6198a9b340de5998dd14a26a0d9d38a6bcac`, which was read for how the
secondary cores are parked and released and how the GIC is set up on this SoC.
The file carries the complete three-clause copyright, conditions and disclaimer
in its own header, and
[`licenses/RaspberryPi-armstub8-BSD-3-Clause.txt`](../licenses/RaspberryPi-armstub8-BSD-3-Clause.txt)
retains the same text. Both stay as they are.

## Khronos Vulkan Registry

`Anvil/Graphics/Vulkan/vk_core_1_0.pbi` and the PureBasic registry generator take
API names, values, type/member relationships and ordering from the Khronos Vulkan
API Registry, pinned to Vulkan-Headers tag `v1.4.350`, commit
`a33416ed2ce6bf8ef48b4eda821825f66d1850d3`. An API's names and numbers are the
interface; they are what makes a binding a binding. The registry is offered under
Apache-2.0 OR MIT and this repository retains the complete
[Khronos MIT text](../licenses/Khronos-Vulkan-Registry-MIT.txt). The XML itself is
not vendored. Generator-specific acknowledgment is retained in
[`Anvil/Graphics/Vulkan/THIRD_PARTY_NOTICES.md`](../Anvil/Graphics/Vulkan/THIRD_PARTY_NOTICES.md).

## DejaVu fonts

`RaspberryPi4/Monitor/anvil_fonts.pi4` contains 4-bit coverage maps for printable
ASCII glyphs, generated at 48 pixels from `DejaVuSans-Bold.ttf`,
`DejaVuSerif-Bold.ttf` and `DejaVuSansCondensed-Bold.ttf`. These are generated
tables rather than consulted behaviour, and they are not relicensed under Anvil's
MIT terms: the complete upstream
[DejaVu Fonts license](../licenses/DejaVu-Fonts-LICENSE.txt), including the
Bitstream Vera and Arev notices, is retained beside them.

Source license revision: `dejavu-fonts/dejavu-fonts` commit
`9b5d1b2ffeec20c7b46aa89c0223d783c02762cf`.

## Other documents read

- **IETF RFCs**, per document, cited inline — wire formats, field widths, state
  machines and constants.
- **Vendor and standards documents** — Broadcom BCM2711 ARM Peripherals; Arm
  DDI/IHI manuals; USB-IF HID 1.11 and HUT 1.21; NIST FIPS 197, FIPS 180-4 and
  SP 800-38A/90A; the SD Association specifications; Goodix and Renesas
  datasheets. Cited inline by section, table and page.
- **hostap** — read only as the on-disk statement of IEEE 802.11 Annex H.4's
  4096 iterations and 32-byte output.
- **LLVM AArch64 target description tables** (`llvmorg-19.1.0`) — instruction and
  system-register encodings, read as fact tables by `tools/a64/a64_interp.py`.
- **py-videocore6** — an independent witness that the V3D block bases are what a
  working userspace driver maps. Recorded because that project is
  GPL-2.0-or-later and the citation must not be mistaken for a permissive one;
  nothing was taken from it.
- **OpenBSD GENET** (`d728e260a5a9b55d69a81bf0ff6af38626ab17a4`) — a second
  description of the same MAC. Its two-clause MAC files and four-clause PHY files
  are recorded so a later reader does not treat the whole tree as one licence.

## CYW43455 firmware binaries

**This section is not a reference consulted. It is redistribution.**

The firmware image and CLM data in `Firmware/CYW43455/` are binary Cypress
software, not Anvil source, and they ship as they are. They match the following
files from the RPi-Distro `firmware-nonfree` `bookworm` branch at commit
`c91cd2804cf7463aab913e7247c176049f16bbd6`:

| Distributed file | Upstream file | SHA-256 |
| --- | --- | --- |
| `brcmfmac43455-sdio.bin` | `debian/config/brcm80211/cypress/cyfmac43455-sdio-standard.bin` | `d608f866582519c0a28d86db43040f4f1b98dd1d153e72e9752586546b4a36c3` |
| `brcmfmac43455-sdio.clm_blob` | `debian/config/brcm80211/cypress/cyfmac43455-sdio.clm_blob` | `9823842cae9fb9a5dd1e5fb31f595516ec7deee341354bef30bb3026eee29cc1` |

The same pinned upstream `debian/copyright` assigns files matching
`debian/config/brcm80211/*/*43455*` to Cypress Semiconductor Corporation under
`binary-redist-Cypress`. Read the complete retained
[Cypress agreement](../licenses/Cypress-CYW43455-EULA.txt) before using or
redistributing these files. In particular, its binary grant is limited to use
with Cypress integrated circuit products, and the repository's MIT license does
not extend to them.

Source: [RPi-Distro/firmware-nonfree at the pinned commit](https://github.com/RPi-Distro/firmware-nonfree/tree/c91cd2804cf7463aab913e7247c176049f16bbd6)

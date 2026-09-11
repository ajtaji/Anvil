# Third-party notices

Anvil includes or derives material from the projects listed below. The
repository MIT license does not replace these terms. The complete retained
license texts are in [`licenses/`](../licenses/).

**Publication review is open.** The source-export gate checks packaging, not
license compatibility. The GENET derivation and the remaining driver closure
are being reviewed before further public pushes. See
[`PUBLICATION_REVIEW.md`](PUBLICATION_REVIEW.md); the project MIT declaration
must not be read as resolving that review.

## Broadcom brcmfmac source

`RaspberryPi4/Lib/cyw43.pi4` adapts protocol and transport code from Linux
`drivers/net/wireless/broadcom/brcm80211/brcmfmac/`. The reviewed upstream
revision is Linux v6.12, commit
`adc218676eef25575469234709c2d87185ca223a`:

| Source | Retained copyright | SPDX identifier |
| --- | --- | --- |
| `bcmsdh.c`, `sdio.c`, `bcdc.c` | 2010 Broadcom Corporation | ISC |
| `fwil.h` | 2012 Broadcom Corporation | ISC |
| `chip.c` | 2014 Broadcom Corporation | ISC |

The complete [ISC notice](../licenses/Broadcom-brcmfmac-ISC.txt) accompanies
these adaptations. This is separate from the binary CYW43455 firmware license
below. Retaining these confirmed source notices does not claim that the entire
driver dependency/provenance audit is complete.

Sources: [pinned brcmfmac directory](https://github.com/torvalds/linux/tree/adc218676eef25575469234709c2d87185ca223a/drivers/net/wireless/broadcom/brcm80211/brcmfmac),
[pinned license text](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/LICENSES/deprecated/ISC).

## Raspberry Pi firmware stub

`RaspberryPi4/Board/armstub8.asm` is a translation and modification of
[Raspberry Pi's armstub8.S](https://github.com/raspberrypi/tools/blob/439b6198a9b340de5998dd14a26a0d9d38a6bcac/armstubs/armstub8.S).
It retains the complete BSD-3-Clause copyright, conditions and disclaimer in
its source header. Binary distributions of the optional stub must also carry
that notice; it is not relicensed under Anvil's MIT license.

## CYW43455 firmware

The firmware image and CLM data in `Firmware/CYW43455/` are binary Cypress
software, not Anvil source. They match the following files from the official
RPi-Distro `firmware-nonfree` `bookworm` branch at commit
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
with Cypress integrated circuit products.

Source: [RPi-Distro/firmware-nonfree at the pinned commit](https://github.com/RPi-Distro/firmware-nonfree/tree/c91cd2804cf7463aab913e7247c176049f16bbd6)

## Khronos Vulkan Registry

`Anvil/Graphics/Vulkan/vk_core_1_0.pbi` and the PureBasic registry generator
derive API names, values, type/member relationships, and ordering from the
Khronos Vulkan API Registry. The input is pinned to Vulkan-Headers tag
`v1.4.350`, commit `a33416ed2ce6bf8ef48b4eda821825f66d1850d3`.
The registry is offered under Apache-2.0 OR MIT; this distribution retains and
uses the complete [Khronos MIT license](../licenses/Khronos-Vulkan-Registry-MIT.txt).
The XML itself is not vendored. Generator-specific attribution is retained in
[`Anvil/Graphics/Vulkan/THIRD_PARTY_NOTICES.md`](../Anvil/Graphics/Vulkan/THIRD_PARTY_NOTICES.md).

## DejaVu fonts

`RaspberryPi4/Monitor/anvil_fonts.pi4` contains generated 4-bit coverage maps
for printable ASCII glyphs baked at 48 pixels from these faces:

- `DejaVuSans-Bold.ttf`
- `DejaVuSerif-Bold.ttf`
- `DejaVuSansCondensed-Bold.ttf`

The generated tables are derived font material and are not relicensed under
Anvil's MIT license. The complete upstream [DejaVu Fonts license](../licenses/DejaVu-Fonts-LICENSE.txt),
including the Bitstream Vera and Arev notices, accompanies them.

Source license revision: `dejavu-fonts/dejavu-fonts` commit
`9b5d1b2ffeec20c7b46aa89c0223d783c02762cf`.

## BearSSL-derived cryptography

Parts of the portable and Raspberry Pi cryptographic implementation are
translations or adaptations of BearSSL algorithms and generated material.
The original per-file copyright notices remain in the source. The complete
[BearSSL MIT license](../licenses/BearSSL-LICENSE.txt) accompanies the tree and
also covers the derived X.509 VM blob.

## Mesa derived V3D material

`RaspberryPi4/Lib/v3d.pi4`, `RaspberryPi4/Lib/v3dqpu.pi4` and
`RaspberryPi4/Lib/neon.pi4` derive V3D control-list packet layouts, QPU
instruction field and opcode tables, the instruction-restriction list, tiling
and TFU descriptions, and the register-write order of job submission from the
Broadcom V3D backend of Mesa. The reviewed upstream is tag `mesa-24.3.4`,
commit `769e51468b49b2a42f0a0eaf71cf9eed5ff4e5de`.

Mesa's cited files carry per-file MIT notices. The complete retained text is in
[`licenses/Mesa-MIT.txt`](../licenses/Mesa-MIT.txt). No Mesa source file is
vendored here. Per-routine classification is in
[`PROVENANCE_INVENTORY.md`](PROVENANCE_INVENTORY.md).

## Das U-Boot GPL-2.0-or-later under review

**This section discloses a derivation. It is not a license election.**

Several files translate or structurally follow U-Boot v2025.01, commit
`6d41f0a39d6423c8e57e92ebbe9f8c0333a63f72`, whose relevant sources carry
`GPL-2.0-or-later` SPDX headers:

| Anvil file | Upstream |
| --- | --- |
| `RaspberryPi4/Lib/genet.pi4` | `drivers/net/bcmgenet.c` — named by the file as its primary source |
| `RaspberryPi4/Lib/mmu.pi4` | `arch/arm/cpu/armv8/cache.S`, `cache_v8.c` — the all-level set/way routines |
| `RaspberryPi4/Lib/display.pi4`, `RaspberryPi4/Lib/mailbox.pi4` | `drivers/video/bcm2835/msg.c`, `bcm2835_mbox.h` |
| `RaspberryPi4/Lib/tftp.pi4` | `net/tftp.c` |
| `RaspberryPi4/Lib/xhci.pi4`, `RaspberryPi4/Lib/pcie.pi4` | `drivers/usb/host/xhci*.c`, `drivers/pci/pcie_brcmstb.c` |
| `RaspberryPi4/Board/hw_boot.pi4` | `arch/arm/cpu/armv8/transition.S` |
| `RaspberryPi4/Lib/hid.pi4` | `common/usb.c` — one retry and delay behaviour |

Register definitions, mailbox tag numbers and the arm64 `Image` header layout
taken from the same tree are hardware and interface facts and are cited as such;
the table above lists only the blocks classified as derived.

The GPL-2.0 license text is **deliberately not shipped in this repository yet.**
The choice between retaining these components with their terms and replacing
them with independently derived work is open, and shipping a license text would
itself be a decision. See
[`PUBLICATION_REVIEW.md`](PUBLICATION_REVIEW.md) and
[`PROVENANCE_INVENTORY.md`](PROVENANCE_INVENTORY.md). Public pushes are held
until it is resolved. Nothing here is relicensed by the repository's MIT terms.

## Linux kernel GPL-2.0 under review

**This section discloses a derivation. It is not a license election.**

Files deriving from Linux v6.12, commit
`adc218676eef25575469234709c2d87185ca223a`, and from the Raspberry Pi
`rpi-6.12.y` fork, under `GPL-2.0-only` or `GPL-2.0-or-later` per file:

| Anvil file | Upstream |
| --- | --- |
| `RaspberryPi4/Lib/v3d.pi4` | `drivers/gpu/drm/v3d/v3d_gem.c`, `drivers/pmdomain/bcm/bcm2835-power.c` |
| `RaspberryPi4/Lib/sdio.pi4` | `drivers/mmc/host/bcm2835-mmc.c`, `sdhci.h`, the MMC core |
| `RaspberryPi4/Lib/touch_goodix.pi4` | `drivers/input/touchscreen/goodix.c` (**GPL-2.0-only**) |
| `RaspberryPi4/Lib/dsi_panel_v2.pi4`, `dsi_panel_v2_dcs.pi4`, `RaspberryPi4/Tests/Fixtures/dsi_panel_v1.pi4` | `drivers/gpu/drm/panel/panel-waveshare-dsi-v2.c`, `panel-raspberrypi-touchscreen.c` |
| `RaspberryPi4/Lib/entropy.pi4` | `drivers/char/hw_random/iproc-rng200.c` |

The brcmfmac protocol and transport sources in the same tree are ISC, not GPL,
and are covered separately above. Register headers such as `v3d_regs.h` are
tables of definitions and are cited as hardware facts.

As with U-Boot, the license text is not shipped yet and the retain-or-replace
decision is open.

## BCM2711 device tree quotation

`RaspberryPi4/Lib/pcie.pi4` reproduces five lines of `bcm2711.dtsi` verbatim
inside a comment — the PCIe wrapper's 3 GiB DMA erratum note and the
`dma-ranges` property it explains — introduced in the source as "comment
included verbatim because it is the citation". `bcm2711.dtsi` carries SPDX
`GPL-2.0`. The quotation is attributed where it appears. It is recorded here so
that the review covers it rather than passing over the tree's one verbatim copy.

Block addresses, interrupt numbers, `phy-mode` and panel timings read from the
same device tree elsewhere in the tree are hardware description and are cited as
hardware facts.

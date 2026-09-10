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

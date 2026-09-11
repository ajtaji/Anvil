# Licensing and redistribution

Unless a file or subtree carries a different notice, original Anvil source and
documentation are licensed under the repository's [MIT License](../LICENSE):

> Copyright (c) 2026 PureMetal Labs

The MIT license does not replace third-party terms. Keep every upstream notice
with the material it covers. The repository-wide map is
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), and complete retained texts
are in [`licenses/`](../licenses/).

## CYW43455 firmware

`Firmware/CYW43455/` contains:

- `brcmfmac43455-sdio.bin`
- `brcmfmac43455-sdio.clm_blob`
- `README.txt`

The two binaries are third-party firmware. Their SHA-256 digests match the
official RPi-Distro `firmware-nonfree` `bookworm` source at commit
`c91cd2804cf7463aab913e7247c176049f16bbd6`. That pinned source assigns its
CYW43455 files to Cypress Semiconductor Corporation under
`binary-redist-Cypress`. The complete applicable agreement and exact file
mapping are retained in
[`licenses/Cypress-CYW43455-EULA.txt`](../licenses/Cypress-CYW43455-EULA.txt).

The agreement's binary-code grant is limited to use with Cypress integrated
circuit products and includes additional restrictions. Read and comply with
the complete agreement before using or redistributing the files. This summary
is not a substitute for the license text. The firmware is not covered by
Anvil's MIT license.

The Wi-Fi driver also needs a board-appropriate NVRAM text file. It is not
bundled because it may contain calibration and identity data. Obtain the
correct file for the board and place it on the Pi boot medium as `BRCMNV.TXT`;
place the firmware image as `BRCMFW.BIN` and the CLM data as `BRCMCLM.BLB`.

## Vulkan vocabulary from the Khronos Registry

The Vulkan vocabulary and generator derive names, values, relationships, and
ordering from the Khronos Vulkan API Registry. That registry is licensed
Apache-2.0 OR MIT. This distribution uses the MIT option and includes the full
Khronos text in
[`licenses/Khronos-Vulkan-Registry-MIT.txt`](../licenses/Khronos-Vulkan-Registry-MIT.txt).
The exact tag, commit, input digest, and generator attribution are recorded in
[`Anvil/Graphics/Vulkan/THIRD_PARTY_NOTICES.md`](../Anvil/Graphics/Vulkan/THIRD_PARTY_NOTICES.md).
The registry XML itself is not vendored.

The generator's separate PureBasic XML reference attribution and license are
also retained in that notice file.

## DejaVu-derived glyph tables

`RaspberryPi4/Monitor/anvil_fonts.pi4` contains generated coverage tables for
glyphs from three DejaVu faces. These tables are derived font material, not
original Anvil code. Keep
[`licenses/DejaVu-Fonts-LICENSE.txt`](../licenses/DejaVu-Fonts-LICENSE.txt)
with any distribution that contains them. The exact faces and upstream license
revision are recorded in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Cryptography, and BearSSL as a reference consulted

Anvil's cryptography is original code. BearSSL was read for its constant-time
designs and test vectors; it was confirmed on 2026-09-10 that no third-party
code was used. Source-file citations remain the pointers to what was read; the
BearSSL MIT text is kept as an acknowledgment in
[`licenses/BearSSL-LICENSE.txt`](../licenses/BearSSL-LICENSE.txt). See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the coverage summary.

## Material that must not be committed

Credentials, Wi-Fi settings, board NVRAM/calibration, private keys, product
license files, local compiler binaries, build outputs, and bench logs do not
belong in the public repository. The root `.gitignore` excludes their common
filenames, and `tools/verify_export.py` checks the selected public boundary.

CYW43455 Wi-Fi firmware — Raspberry Pi 4
=========================================

The Raspberry Pi 4's on-board wireless device is a Cypress/Infineon CYW43455.
Anvil's Raspberry Pi Wi-Fi path downloads firmware to that device over SDIO
during bring-up.

Files:
  brcmfmac43455-sdio.bin       CYW43455 Wi-Fi firmware image
  brcmfmac43455-sdio.clm_blob  country-localized regulatory data

For the Anvil boot medium, copy these files as:
  BRCMFW.BIN
  BRCMCLM.BLB

A board-appropriate NVRAM file is also required as BRCMNV.TXT. It is not
included in this repository because it may contain board calibration and
identity data.

License and provenance:
  ../../licenses/Cypress-CYW43455-EULA.txt
  ../../docs/THIRD_PARTY_NOTICES.md

The firmware image and CLM data are third-party binary software and are not
covered by Anvil's MIT license. Read the complete Cypress agreement before use
or redistribution.

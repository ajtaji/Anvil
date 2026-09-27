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

Bluetooth (added 2026-09-27):
  BCM4345C0.hcd                the same chip's Bluetooth patch RAM, downloaded
                               over the HCI UART before the controller is
                               used (the Pi 4's and the Pi 5's radio)

  From RPi-Distro/bluez-firmware commit
  cdf61dc691a49ff01a124752bd04194907f0f9cd, debian/firmware/broadcom/,
  SHA-256 51c45e77ddad91a19e96dc8fb75295b2087c279940df2634b23baf71b6dea42c.
  Licence: ../../licenses/Cypress-bluez-firmware-LICENSE.cypress.html (that
  tree's LICENSE.cypress, byte-exact - upstream stores it as a saved HTML
  page of the linux-firmware LICENCE.cypress) and ../../docs/THIRD_PARTY_NOTICES.md.

Raspberry Pi 3 CYW43430 candidate radio data

These files are staged for the Raspberry Pi 3 Model B CYW43430 profile.
The runtime must first identify a supported board and radio revision; it
must refuse firmware upload when the detected profile does not match the
files present here. The NVRAM text is transformed at runtime to substitute
the device's validated WLAN MAC address before upload. Its sample MAC is
not used as a device address.

Pinned source: RPi-Distro/firmware-nonfree commit
3bab0f823f5b53150b76aab77093adef6655b920.

The firmware and CLM bytes are the target files of that source tree's
debian/added-firmware symlinks:
  brcm/brcmfmac43430-sdio.raspberrypi,3-model-b.bin
    -> ../cypress/cyfmac43430-sdio.bin
  brcm/brcmfmac43430-sdio.raspberrypi,3-model-b.clm_blob
    -> ../cypress/cyfmac43430-sdio.clm_blob
The board NVRAM file is the target of the matching symlink to
brcm/brcmfmac43430-sdio.txt.

License mapping follows debian/copyright at that pinned commit. The binary
firmware and CLM blob are redistributed under the Cypress binary firmware
terms in Cypress-CYW43430-EULA.txt. The board NVRAM text is GPL-2.0-or-later
and is accompanied by GPL-2.0.txt. See manifest.json for byte counts and
SHA-256 digests. Preserve the license files with the data when installing.

On the Pi 3 data partition, the intended paths are /wifi/<filename> (the
Anvil filesystem namespace exposes this partition as 2:/wifi/<filename>).

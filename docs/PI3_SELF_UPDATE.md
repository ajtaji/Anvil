# Updating the Raspberry Pi 3 direct boot files

The Pi 3 firmware loads the complete Anvil monitor from `kernel8.img` after
running Anvil's Pi 3 `armstub8.bin`. This update replaces those direct boot
files on an already prepared FAT boot volume. It does not update a monitor
slot, format media, or change partitions.

## Build and review

Build the counted Pi 3 artifacts from the repository root:

```text
python tools/build.py pi3 --compiler <PureMetalForge.exe>
```

The build emits `build/pi3/armstub8.bin` and the full monitor
`build/pi3/kernel8.img`, with PMF metadata beside the monitor image. Review the
build identity, inspect the source changes, and record the SHA-256 of both
artifacts. Run the direct-entry gate against those exact files:

```text
python tools/pi3_direct_boot_check.py --stub build/pi3/armstub8.bin --kernel build/pi3/kernel8.img
```

The stub is firmware-specific. The staging command checks it against the
accepted digest, validates the monitor's BCM2837 PMF load, BSS and stack
addresses, checks the pinned Raspberry Pi firmware files, and validates the
direct-boot configuration before it creates a new bundle:

```text
python tools/pi3_boot_stage.py --firmware <pinned-firmware-dir> --image build/pi3/kernel8.img --image-sha256 <reviewed-image-sha256> --armstub build/pi3/armstub8.bin --armstub-sha256 <reviewed-stub-sha256> --output <new-bundle-dir>
```

Review the emitted `SHA256.json` and the manifest digest printed by staging.
Keep the staged bundle and its digest together; provisioning requires the
reviewed manifest digest and will reject files that no longer match it.

## Install on the mounted boot volume

Mount the intended card's FAT boot volume and verify its identity independently
before running the provisioner. Choose a new host backup directory. The tool
backs up every existing file that it will change before writing any bundle
file, refuses alternate `autoboot.txt` selection, and verifies readback hashes.

```text
python tools/pi3_provision.py --card-root <mounted-boot-root> --bundle <new-bundle-dir> --manifest-sha256 <reviewed-SHA256.json-sha256> --backup-dir <new-host-backup-dir> --yes-replace-kernel8
```

Provisioning is limited to the manifest's direct firmware bundle. It does not
select or format a disk, edit partitions, or invoke an A/B trial protocol. Keep
the backup until the board has cold-booted the new image and the serial prompt
and expected firmware DTB diagnostics are visible. If boot fails, stop and
restore the backed-up files with the card unmounted from the board.

## What protects the boot

The configured custom stub enters the full monitor directly at `0x200000` and
passes the firmware DTB in `x0`. No updater runs before the prompt, and normal
startup does not mount the boot filesystem or hash a slot record. A monitor
replacement therefore relies on reviewing and hashing the exact image, the
host backup, and post-install readback. The file-backed `boot <name>` command
is a separate payload loader available after the monitor has started.

The host gates prove artifact structure, firmware-file pinning, and emitted
entry behavior. They do not prove that the card is the intended physical
device, that firmware accepts the files on a particular board, or that a
replacement boots successfully; confirm those facts on the target before
discarding the backup.

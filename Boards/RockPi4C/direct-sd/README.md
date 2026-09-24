# ROCK Pi 4C direct-SD Anvil build 147

`anvil.bin` is one self-contained EL3 Anvil component loaded at `0x00040000`.
It contains the entry prefix, complete runtime, and embedded Rock Pi 4C device
tree. `trust-anvil.img` packages two identical copies of that component; it
contains no U-Boot or separate Anvil payload. The image installed and booted
on the original ROCK Pi 4C v1.2 on 2026-09-23.

This package updates a card with the tested Rockchip DDR/miniloader layout.
It is not a whole blank-card image. The trust container belongs in the fixed
12–16 MiB SD range; use Anvil's checked `trustupdate` command from a running
direct-SD build. The update writes and reads back both copies, then requires
an explicit reboot. `anvil.bin` is the extracted component for inspection and
checksum verification, not a filesystem boot file.

Build 147 runs at EL3, mounts the SD exFAT volume, and exposes checked serial
file commands. It also mounts the eMMC user-area FAT32 data partition and
passed file creation, transfer, remount, readback, rename, and removal checks
on both media. Its 1920×1080 HDMI console uses a shared TrueType atlas and
RGA2 row publication. Resident counters reported 46 RGA jobs with no
failures and zero CPU text-copy bytes. The live CPU-status update received
400/400 serial bytes at 1.5 Mbaud with no receive errors on two runs.
Deadman-guarded returning payloads
proved private Mali-T860 fragment rendering, Mali-to-RGA transfer, bounded
live scanout, and exact screen restoration. The production console does not
use Mali yet. SPI and MiniDP are outside this package's validated paths.

Verify both packaged files with `sha256sum -c SHA256SUMS`. The exact sources,
sizes, checksums, and hardware checks are in `BUILD-MANIFEST.json`. See
`RockPi4C/README.md`, `RockPi4C/EMMC.md`, and `RockPi4C/RENDERING.md` for the
board contract and current subsystem limits.

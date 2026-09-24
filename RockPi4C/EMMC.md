# Rock Pi 4C eMMC storage

Anvil boots from the removable SD card and can select the separate RK3399
Arasan SDHCI eMMC controller at `0xFE330000` for file operations. The eMMC
user area has one 512 MiB FAT32 data partition: MBR partition 1, type `0x0C`,
starting at LBA 32768 and spanning 1,048,576 sectors. The remaining user-area
space is unallocated. eMMC boot0, boot1, RPMB, and SPI are untouched.

The eMMC backend identifies the card at 400 kHz, checks that the EXT_CSD
access selector names the user area, and compares a sector before and after
moving to 25 MHz. If that comparison or clock change fails, it resets the
command/data lines and verifies the sector again at 400 kHz before accepting
the fallback. Transfers use bounded single-block CMD17/CMD24 operations;
eMMC multiblock CMD18/CMD25 is not enabled. Serial uploads use 16 KiB
acknowledged windows and a bounded 4 MiB staging area.

The serial `emmc` and `sd` commands select a medium and try to mount it;
`fs` reports the selection, filesystem, partition, and capacity. `ls`,
`stat`, `cat`, and `load` read through the selected medium. `put` and `get`
transfer files with the host utility. `receive` checks data into the staging
area without executing it, and `save` writes that checked data as a file.
`mkdir`, `rm`, `rmdir`, and `mv` operate on the selected mounted filesystem.
File changes arm the selected medium's writer for one operation, then disarm
it. eMMC writer arming rechecks the live EXT_CSD user-area selector.

On the original Rock Pi 4C, deadman-armed returning payloads proved eMMC
identification, user-area selection, 25 MHz reads, and a single-sector
write/readback/restore at LBA 32768. The formatter wrote and read back all
2,084 FAT32 metadata sectors, then published and checked the MBR last. A
separate read-only payload subsequently checked the MBR, primary and backup
boot/FSInfo sectors, both FAT heads, and the root sector twice against their
planned CRC32 values. The production 25 MHz initialization path passed the
same read-only sector check with no fallback.

Build 145 mounted the FAT32 volume on the board at 25 MHz, and build 147
mounted it again after reboot. The build 145 serial smoke
test passed `ls`, `stat`, `cat`, `load`, `get`, `receive`, `save`, `put`, `mkdir`,
`mv`, `rm`, and `rmdir` with checksummed file readback and a clean final root.
The SD exFAT command smoke also passed after the build 145 reboot. The
formatter covers only the 512 MiB data partition; the rest of the user area
remains unallocated.

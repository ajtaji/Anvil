# Native exFAT support

Anvil has a target-neutral exFAT 1.x filesystem behind the same block-device
and filesystem seams used by FAT32. Board code supplies 512-byte block read,
write, and optional flush callbacks; the filesystem contains no USB, SD,
firmware, or chip-specific logic.

## Supported surface

- raw exFAT volumes, MBR type-07 partitions, and CRC-validated GPT Microsoft
  Basic Data partitions
- 512, 1024, 2048, and 4096-byte logical sectors and clusters through 32 MiB
- active FAT and allocation bitmap, free-space accounting, and bounds checks
- main and backup boot-region validation
- nested directory traversal
- UTF-8 paths, strict UTF-16 decoding, the volume up-case table, case-insensitive
  lookup, long names, name hashes, and entry-set checksums
- read, write, create, extend, truncate, rename, and remove for files
- create, enumerate, rename, and remove for directories
- timestamps, metadata preservation during rename, flush, and clean unmount

`load`, `save`, and `ls` accept paths. Enclose paths containing spaces in
double quotes. The monitor line editor accepts the full 1023-byte path limit.
FAT32 media continues to use its existing short-name behavior through the same
facade.

## Safety behavior

Read-only mount and unmount never write. Before metadata changes, the driver
marks a previously clean volume dirty; flush completes device writes before it
clears that flag. A volume already marked dirty or recording media failure may
be read but cannot be changed. Malformed geometry, checksums, names, chains,
allocation, or out-of-volume references are refused with a numbered sentence.

Two-FAT volumes are TexFAT. Anvil selects the active FAT and bitmap for
read-only inspection but refuses changes because it does not implement TexFAT
transactions. Formatting and filesystem repair are intentionally outside this
driver.

## Verification status

The repository includes `RaspberryPi4/Tests/exfat_emitted_gate.pi4` and
`tools/exfat_fixture_check.py`. They compile the production driver with the
unified IDE's headless mode and execute the emitted A64 against a writable
memory volume. The gate covers read-only behavior, dirty-volume refusal, MBR
and GPT discovery, Unicode and folded lookup, nested directory growth, the
file/directory mutation lifecycle, flush/unmount/remount persistence,
free-space restoration, rename-cycle rejection, and damaged metadata refusal.

Pi 4 silicon verification remains pending. The bounded hardware gate must use
a disposable exFAT copy and prove long and Unicode names, nested directories,
create/read/write/extend/truncate/rename/delete, free-space accounting,
flush/unmount/remount and reboot persistence, then prove a separately damaged
copy is refused. No board-completion claim is made by the desk implementation.

## Source and specification

The implementation is clean-room code based on Microsoft's public
[exFAT specification](https://learn.microsoft.com/en-us/windows/win32/fileio/exfat-specification).
No Linux or U-Boot filesystem implementation is included or copied.

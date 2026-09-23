# ROCK Pi 4C direct-SD Anvil build 124

`anvil.bin` is the one self-contained Anvil component loaded at `0x00040000`.
It contains the EL3 entry prefix, the complete runtime, and the embedded board
DTB. `trust-anvil.img` is the Rockchip two-copy trust container holding that
same single component; it contains no U-Boot or separate Anvil payload.

This package updates a card that already has the repository's tested Rockchip
DDR/miniloader layout. It is not a whole blank-card image. The trust container
belongs at byte offset 12 MiB and occupies bytes 12–16 MiB; use the bounded
Anvil `trustupdate` command on an already running direct-SD build. Do not write
it to a filesystem file or use it as a generic disk image.

Build 124 passed on the original ROCK Pi 4C v1.2: EL3 entry, exFAT mount,
serial recovery, 1920×1080 HDMI with no VOP fault, and a guarded Mali-T860
private write-value job. Anvil's shared TrueType library loaded Courier Prime
from SD and prepared a 95-glyph atlas. The on-screen console still uses its
bitmap glyph path; a Mali textured blit is pending. Verify these files with
`sha256sum -c SHA256SUMS`.

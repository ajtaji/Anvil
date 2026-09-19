#!/usr/bin/env python3
"""anvil_putfile.py - put an arbitrary file onto Anvil's boot medium.

    python tools/anvil_putfile.py <local file> <NAME.EXT> [more pairs ...]

anvil_update.py already did this for exactly one file, KERNEL8.IMG, with
the slot name and size wired in as constants. The CYW43455 needs three
files on the stick - a 609 KB firmware image, an NVRAM text file and a
CLM blob - and none of them is the boot image, so the wired-in constants
had to come out. This is that tool with the name and length passed in
instead of assumed.

WHY THE FILE HAS TO BE ON THE STICK AT ALL. The radio has no flash of
its own. Its ARM comes out of reset with empty RAM, so every cold boot
has to push the whole 609309-byte image across SDIO before the chip can
do anything. Anvil cannot hold that inside itself - it would triple the
size of the monitor - so it reads it from the medium it booted from.

THE NAMES ARE 8.3 AND THAT IS NOT A STYLE CHOICE. fat.pi4 writes short
directory entries only; it does not generate VFAT long-name chains. So
brcmfmac43455-sdio.bin cannot be its name on this volume. The mapping is
recorded here and in cyw43.pi4 rather than left for someone to rediscover
by watching a load fail:

    brcmfmac43455-sdio.bin        ->  BRCMFW.BIN
    brcmfmac43455-sdio.txt        ->  BRCMNV.TXT
    brcmfmac43455-sdio.clm_blob   ->  BRCMCLM.BLB

EACH FILE IS VERIFIED TWICE, and the second time is the one that counts.
`receive` checks a CRC32 over the serial transfer, which proves the wire
was clean and proves nothing whatever about what reached the FAT. So
after the save, the file is loaded BACK off the stick into a different
address and its CRC32 taken again on the board. A firmware image that is
wrong by one byte does not fail loudly; it makes a radio that almost
works, which is far more expensive to debug than a refusal here.
"""
import os
import sys
import time
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from anvil import Anvil, stage_help

# TWO STAGING ADDRESSES, deliberately far apart and both inside the low
# payload window. The readback goes to a DIFFERENT address from the send
# so that a save which quietly did nothing cannot be certified by the
# bytes still sitting in RAM from the send - which is exactly the vacuous
# control that made an SDIO run unreadable on 2026-08-28.
#
# NEITHER IS A CONSTANT NOW - 2026-09-08. The first is whatever the board
# answers `map` with; the second is sixteen megabytes above it, which is
# the same distance the old pair had (0x400000 and 0x1400000) expressed
# as the thing that mattered about it rather than as a second number to
# keep in step. Both are inside the low window on any board this runs on:
# that window is 123 MB on the Pi 4 and its bottom edge is the address
# the first one came from.
CHECK_GAP = 0x1000000


def put(a, local, name, stage, check):
    data = open(local, "rb").read()
    want = zlib.crc32(data) & 0xFFFFFFFF
    print("  %-42s -> %-11s %7d bytes  crc32 %08X"
          % (local.split("/")[-1], name, len(data), want))

    t0 = time.time()
    out = a.block(local, stage)
    if "ok" not in out or "crc" in out:
        print("    the serial transfer did not verify:")
        print("    " + out[-300:].replace("\n", "\n    "))
        return False
    print("    sent in %.1f s" % (time.time() - t0))

    out = a.cmd("save %s %X %X" % (name, stage, len(data)), 120)
    if "written." not in out:
        print("    SAVE DID NOT COMPLETE:")
        print("    " + out.strip().replace("\n", "\n    "))
        return False

    # --- the readback, which is the check that actually matters -------
    out = a.cmd("load %s %X" % (name, check), 120)
    if "Loaded" not in out:
        print("    could not read the file back:")
        print("    " + out.strip().replace("\n", "\n    "))
        return False
    out = a.cmd("crc32 %X %X" % (check, len(data)), 120)
    # Anchored on the sentence that carries the answer, NOT on "the last
    # thing in the output that looks like eight hex digits". The loose
    # version read EDB88320 - the CRC-32 POLYNOMIAL, which the command
    # helpfully prints two lines below the result - and reported a
    # perfectly good file as corrupt. That is the same shape as every
    # other false alarm today: the instrument was wrong and the board
    # was right, and a loose parser is an instrument.
    got = None
    for line in out.splitlines():
        i = line.find("The CRC32 is ")
        if i >= 0:
            tok = line[i + 13:].strip().rstrip(".").strip()
            try:
                got = int(tok, 16)
            except ValueError:
                got = None
    if got is None:
        print("    the board printed no CRC32 I could read:")
        print("    " + out.strip().replace("\n", "\n    "))
        return False
    if got != want:
        print("    READBACK CRC MISMATCH - want %08X, the stick holds %08X"
              % (want, got))
        return False
    print("    read back off the stick, crc32 %08X - matches" % got)
    return True


def main():
    pairs = sys.argv[1:]
    if not pairs or len(pairs) % 2:
        print(__doc__)
        return 1
    pairs = list(zip(pairs[0::2], pairs[1::2]))

    a = Anvil()
    try:
        if a.prompt() != "pmf":
            print("no Anvil prompt - is it running?")
            return 1
        a.settle()
        # ASKED ONCE, BEFORE ANY FILE MOVES. See WHERE THE BOARD WANTS A
        # FILE PUT in tools/anvil.py for why it is asked at all.
        stage = a.stage_addr()
        if stage is None:
            print(stage_help("these files"))
            return 1
        check = stage + CHECK_GAP
        print("staging at %08X, reading back at %08X - both from this "
              "board's own map" % (stage, check))
        fast = a.setbaud(1500000)
        print("1.5 Mbaud" if fast else "115200 (the adapter would not go faster)")
        print()
        ok = True
        for local, name in pairs:
            if not put(a, local, name, stage, check):
                ok = False
                break
        if fast:
            a.settle()
            a.setbaud(115200)
        print()
        print("all %d files are on the stick and verified" % len(pairs)
              if ok else "STOPPED - the stick is not in the state you wanted")
        return 0 if ok else 1
    finally:
        a.close()


if __name__ == "__main__":
    sys.exit(main())

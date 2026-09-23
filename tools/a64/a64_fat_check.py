#!/usr/bin/env python3
"""Executable gate for Anvil/Storage/fat32.pbi - FAT32, read AND write.

      python tools/a64/a64_fat_check.py --compiler <PureMetalForge.exe>
      python tools/a64/a64_fat_check.py --compiler <PureMetalForge.exe> --mutate

The library is reached exactly as the Pi 4 board reaches it, through the
RaspberryPi4/Lib/fat.pi4 compatibility include, which pulls in
Anvil/Storage/fat32.pbi, exfat.pbi and filesystem.pbi.

There is no SD card in this machine, so the medium is fabricated here: a
real MBR, a real FAT32 boot sector, a real FSInfo sector, two real FATs
and a real root directory, built byte by byte to the layout fat32.pbi
believes in, plus deliberately WRONG variants of each.  The image is
written into the test program's `tdisk` Dim array; the program points
fat32.pbi at it through the same FatSetRangeReader / FatSetRangeWriter
seams the monitor uses for @SdReadBlock and @MscWriteBlock, and the
whole thing is executed on Anvil's A64 model (tools/a64/a64_interp.py).

TWO KINDS OF ASSERTION LIVE HERE AND THE DIFFERENCE MATTERS.

  * EXPECT is what the PROGRAM reported - a list of values this file
    holds independently of the program that produces them.  Good for
    return codes and refusals; it is still the program grading itself.

  * check_structure() is the real evidence.  After the run it reads the
    finished medium back out of interpreter memory and parses the FAT,
    the root directory and FSInfo the way a DIFFERENT implementation
    would, asking fat32.pbi nothing.  That is the only kind of check that
    can catch a library being confidently wrong in the same way twice.

It also checks something no finished image can show: the ORDER the
sectors were written in.  The program's block writer records every LBA
it is handed, with TdMark tags between phases, and this file does all
the judging.  A correct image comes out of the wrong order just as
happily as out of the right one - right up until the power goes off in
the middle of a write.

--mutate rebuilds the library thirteen times with a deliberate defect in
each and requires the gate to go RED for every one.  A gate that has
only ever passed proves nothing about itself.

Nothing here touches hardware, a serial port, or a card.
"""

from __future__ import annotations
import os

import argparse
import pathlib
import struct
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "a64"))
from a64_interp import A64, attach_symbols  # noqa: E402
import sys as _pmfsys
import pathlib as _pmfpath
_pmfsys.path.insert(0, str(_pmfpath.Path(__file__).resolve().parents[1]))
from pmf_compiler import resolve_compiler  # noqa: E402

LOAD = 0x200000
SEC = 512

# ---------------------------------------------------------------------
# The volume's geometry.  These numbers are the ones the test asserts
# fat32.pbi derives, so they are written once here and nowhere else.
# ---------------------------------------------------------------------
PART_LBA = 63          # NOT zero - the partition-offset trap
PART_SECS = 66600
RSVD = 32
NUM_FATS = 2
FAT_SECS = 512         # 65527 entries * 4 bytes = 262108 -> 512 sectors
SEC_PER_CLUS = 1
META = RSVD + NUM_FATS * FAT_SECS          # 1056
CLUSTERS = 65525                           # EXACTLY the FAT32 boundary
TOT_SECS = META + CLUSTERS                 # 66581
FAT_LBA = PART_LBA + RSVD                  # 95
FAT1_LBA = FAT_LBA + FAT_SECS              # 607 - the mirror
DATA_LBA = PART_LBA + META                 # 1119

FSINFO_LBA = PART_LBA + 1                  # 64 - BPB_FSInfo says sector 1
FAT_BASE = PART_LBA + RSVD                 # 95 - copy 0 of the FAT
FAT_END = FAT_BASE + NUM_FATS * FAT_SECS   # 1119 - one past the last copy
DATA_END = DATA_LBA + CLUSTERS * SEC_PER_CLUS   # 66644, NOT the partition end

FAT16_BOOT_LBA = 2000
FAT12_BOOT_LBA = 2001

# The write half's source pattern.  Deliberately a different shape from
# content() so that a byte of one turning up where the other belongs is
# obvious instead of plausible.
def wcontent(n: int) -> bytes:
    return bytes((((i // SEC) * 91 + (i % SEC) * 29) + 200) & 0xFF
                 for i in range(n))

EOC = 0x0FFFFFFF
BADC = 0x0FFFFFF7

PMF_SIZE = 2500
PMF_CHAIN = [5, 9, 6, 12, 8]   # NOT contiguous and NOT in order


def clus_lba(cl: int) -> int:
    return DATA_LBA + (cl - 2) * SEC_PER_CLUS


def content(n: int) -> bytes:
    """The file's known bytes.  The cluster index is folded in so that a
    chain read in the wrong order cannot accidentally compare equal."""
    return bytes(((i // SEC) * 37 + (i % SEC) * 7 + 11) & 0xFF for i in range(n))


class Disk:
    def __init__(self) -> None:
        self.s: dict[int, bytearray] = {}

    def sec(self, lba: int) -> bytearray:
        if lba not in self.s:
            self.s[lba] = bytearray(SEC)
        return self.s[lba]

    def put(self, lba: int, off: int, data: bytes) -> None:
        self.sec(lba)[off:off + len(data)] = data

    def u8(self, lba, off, v):
        self.put(lba, off, struct.pack("<B", v))

    def u16(self, lba, off, v):
        self.put(lba, off, struct.pack("<H", v))

    def u32(self, lba, off, v):
        self.put(lba, off, struct.pack("<I", v))


def mbr_entry(status, ptype, lba, count) -> bytes:
    # status, CHS start (3), type, CHS end (3), LBA, sector count.
    # The CHS fields are junk on purpose - nothing reads them, and a
    # reader that did would get plausible nonsense.
    return (bytes([status, 0x20, 0x21, 0x00, ptype, 0xFE, 0xFF, 0xFF])
            + struct.pack("<II", lba, count))


def bpb(d: Disk, lba: int, tot_secs: int, fat_secs: int = FAT_SECS,
        root_clus: int = 2) -> None:
    """A FAT32 boot sector.  The FAT type is decided by tot_secs alone."""
    d.put(lba, 0x00, bytes([0xEB, 0x58, 0x90]) + b"MSWIN4.1")
    d.u16(lba, 0x0B, SEC)
    d.u8(lba, 0x0D, SEC_PER_CLUS)
    d.u16(lba, 0x0E, RSVD)
    d.u8(lba, 0x10, NUM_FATS)
    d.u16(lba, 0x11, 0)          # RootEntCnt - zero on FAT32
    d.u16(lba, 0x13, 0)          # TotSec16   - zero on FAT32
    d.u8(lba, 0x15, 0xF8)
    d.u16(lba, 0x16, 0)          # FATSz16    - zero on FAT32
    d.u16(lba, 0x18, 63)
    d.u16(lba, 0x1A, 255)
    d.u32(lba, 0x1C, lba)        # HiddSec
    d.u32(lba, 0x20, tot_secs)
    d.u32(lba, 0x24, fat_secs)
    d.u16(lba, 0x28, 0)          # ExtFlags - all FATs mirrored
    d.u16(lba, 0x2A, 0)          # FSVer
    d.u32(lba, 0x2C, root_clus)
    d.u16(lba, 0x30, 1)          # FSInfo
    d.u16(lba, 0x32, 6)          # BkBootSec
    d.u8(lba, 0x40, 0x80)
    d.u8(lba, 0x42, 0x29)
    d.u32(lba, 0x43, 0x12345678)
    d.put(lba, 0x47, b"PMFBOOT    ")
    # The type STRING is deliberately "FAT32   " on all three volumes,
    # including the two that are not FAT32.  A reader that trusted it
    # would pass this test's FAT16 and FAT12 cases.
    d.put(lba, 0x52, b"FAT32   ")
    d.put(lba, 0x1FE, bytes([0x55, 0xAA]))


def fsinfo(d: Disk, part_lba: int, free_count: int, nxt_free: int,
           lead: int = 0x41615252, struc: int = 0x61417272,
           trail: int = 0xAA550000) -> None:
    """The FSInfo sector, at reserved-region sector 1 of a volume.

    [FATGEN], "FAT32 FSInfo Sector Structure and Backup Boot Sector":
    FSI_LeadSig at 0, FSI_StrucSig at 0x1E4, FSI_Free_Count at 0x1E8,
    FSI_Nxt_Free at 0x1EC, FSI_TrailSig at 0x1FC.  The three signatures
    are parameters so that the gate can build a BROKEN one and watch
    fat32.pbi refuse to write to it.
    """
    lba = part_lba + 1
    d.sec(lba)[:] = bytearray(SEC)
    d.u32(lba, 0x000, lead)
    d.u32(lba, 0x1E4, struc)
    d.u32(lba, 0x1E8, free_count & 0xFFFFFFFF)
    d.u32(lba, 0x1EC, nxt_free & 0xFFFFFFFF)
    d.u32(lba, 0x1FC, trail)


def dirent(name: bytes, attr: int, cluster: int, size: int) -> bytes:
    assert len(name) == 11, name
    e = bytearray(32)
    e[0:11] = name
    e[0x0B] = attr
    struct.pack_into("<H", e, 0x14, (cluster >> 16) & 0xFFFF)
    struct.pack_into("<H", e, 0x1A, cluster & 0xFFFF)
    struct.pack_into("<I", e, 0x1C, size)
    return bytes(e)


def lfn(seq: int) -> bytes:
    e = bytearray(32)
    e[0] = seq
    e[0x0B] = 0x0F          # ATTR_LONG_NAME - not a directory entry
    e[1:11] = b"L\x00o\x00n\x00g\x00N\x00"
    return bytes(e)


def build() -> Disk:
    d = Disk()

    # ---- MBR ---------------------------------------------------------
    d.put(0, 0x000, b"\xFA\x33\xC0\x8E\xD0")          # a plausible stub
    d.put(0, 0x1BE, mbr_entry(0x80, 0x0C, PART_LBA, PART_SECS))
    d.put(0, 0x1CE, mbr_entry(0x00, 0x06, 70000, 1000))     # FAT16 type
    d.put(0, 0x1DE, bytes(16))                              # empty slot
    d.put(0, 0x1EE, mbr_entry(0x00, 0x0C, FAT16_BOOT_LBA, 70000))
    d.put(0, 0x1FE, bytes([0x55, 0xAA]))

    # ---- the FAT32 volume --------------------------------------------
    bpb(d, PART_LBA, TOT_SECS)

    # ---- FSInfo, with BOTH hints unknown ------------------------------
    # $FFFFFFFF is [FATGEN]'s "no idea", and it is what a freshly
    # formatted volume carries.  Seeding it that way means the FIRST
    # allocation has to rebuild the free count by scanning the whole
    # FAT, which is the expensive path and therefore the one worth
    # putting on the critical path of the gate.  The cheap path - a
    # hint that IS valid and is honoured - is tested separately, by
    # poking a hint in and remounting.
    fsinfo(d, PART_LBA, 0xFFFFFFFF, 0xFFFFFFFF)

    # ---- the FAT, both copies ----------------------------------------
    # THE TOP FOUR BITS OF ENTRIES 8 AND 9 ARE DELIBERATELY NOT ZERO.
    # [FATGEN] reserves the high nibble of a FAT32 entry: a reader must
    # mask it off, and a writer must CARRY IT OVER rather than zero it.
    # Both of those entries are rewritten during the run - 8 is linked
    # onward when PMF.IMG grows, 9 becomes the new end of chain when it
    # is truncated - so a write path that drops the nibble shows up in
    # the finished image.  On a FAT of all-zero nibbles the mutation
    # that zeroes them would be invisible, and a gate that cannot see a
    # defect is not testing for it.
    entries = {
        0: 0x0FFFFFF8, 1: 0x0FFFFFFF,
        2: EOC,                       # the root directory, one cluster
        3: 3,                         # a root directory that LOOPS
        5: 9, 9: 0xA0000006, 6: 12, 12: 8, 8: 0x5FFFFFF8,   # PMF.IMG
        20: 21, 21: 20,               # LOOP.IMG - back to the start
        22: 22,                       # SELF.IMG - points at itself
        30: 31, 31: EOC,              # SHORT.BIN - chain ends early
        40: 41, 41: BADC,             # BADMARK.BIN - defective cluster
        50: EOC, 60: EOC,
    }
    for fat_base in (FAT_LBA, FAT1_LBA):
        for cl, val in entries.items():
            off = cl * 4
            d.u32(fat_base + off // SEC, off % SEC, val)

    # ---- the root directory, cluster 2 -------------------------------
    root = b"".join([
        dirent(b"PMFBOOT    ", 0x08, 0, 0),          # 0  volume label
        dirent(b"\xE5OLDFILEBIN", 0x20, 70, 99),     # 1  DELETED
        lfn(0x42),                                   # 2  long name run
        lfn(0x01),                                   # 3
        dirent(b"LONGNA~1IMG", 0x20, 50, 10),        # 4  its 8.3 entry
        dirent(b"SUBDIR     ", 0x10, 60, 0),         # 5  a directory
        dirent(b"PMF     IMG", 0x20, 5, PMF_SIZE),   # 6  THE FILE
        dirent(b"LOOP    IMG", 0x20, 20, 3000),      # 7
        dirent(b"SELF    IMG", 0x20, 22, 3000),      # 8
        dirent(b"SHORT   BIN", 0x20, 30, 2000),      # 9
        dirent(b"BADMARK BIN", 0x20, 40, 2000),      # 10
        dirent(b"OFFVOL  BIN", 0x20, 999999, 100),   # 11
        dirent(b"NOCLUS  BIN", 0x20, 0, 100),        # 12
        dirent(b"EMPTY   TXT", 0x20, 0, 0),          # 13
        dirent(b"HUGE    BIN", 0x20, 5, 4000000000), # 14
        bytes(32),                                   # 15 END OF DIRECTORY
    ])
    assert len(root) == SEC
    d.put(clus_lba(2), 0, root)

    # ---- cluster 3: a directory with no end marker, chained to itself -
    loopdir = b"".join(
        dirent(("DUMMY%03dTXT" % i).encode(), 0x20, 50, 4) for i in range(16)
    )
    assert len(loopdir) == SEC
    d.put(clus_lba(3), 0, loopdir)

    # ---- the file's data, spread over its out-of-order chain ---------
    body = content(PMF_SIZE)
    for idx, cl in enumerate(PMF_CHAIN):
        chunk = body[idx * SEC:(idx + 1) * SEC]
        # Pad the short last cluster with a byte the test must NEVER see.
        d.put(clus_lba(cl), 0, chunk + b"\xAA" * (SEC - len(chunk)))

    for cl in (20, 21, 22, 30, 31, 40, 41, 50, 60):
        d.put(clus_lba(cl), 0, bytes([cl & 0xFF]) * SEC)

    # Cluster 10 is free and holds a deleted file's bytes, as free space on a
    # real medium does. It is the cluster the root directory grows into when
    # THREE.BIN is created, so a directory cluster linked in WITHOUT being
    # zeroed reads these bytes back as entries - the mutation that went
    # green on an all-zero fixture once growth became lazy (2026-09-17).
    d.put(clus_lba(10), 0, bytes((0x41 + (i % 23)) for i in range(SEC)))

    # ---- the two volumes that are NOT FAT32 --------------------------
    # 65524 clusters is FAT16 - one below the boundary the good volume
    # sits exactly on.  4084 clusters is FAT12.  Both carry the $0C
    # FAT32 partition type and the "FAT32   " string.
    bpb(d, FAT16_BOOT_LBA, META + 65524)
    bpb(d, FAT12_BOOT_LBA, META + 4084)

    return d


# ---------------------------------------------------------------------
# The expected value of every check, in the order the program makes them.
# ---------------------------------------------------------------------
E_NONE, E_NO_READER, E_READ_FAIL, E_NO_MBR, E_PARTNUM = 0, 1, 2, 3, 4
E_PART_STATUS, E_PART_EMPTY, E_PART_GPT, E_PART_TYPE, E_PART_GEOM = 5, 6, 7, 8, 9
E_NO_BOOTSEC, E_SECSIZE, E_SPC, E_RESERVED, E_NUMFATS = 10, 11, 12, 13, 14
E_FATSZ, E_TOTSEC, E_GEOMETRY, E_FAT12, E_FAT16 = 15, 16, 17, 18, 19
E_ROOTENT, E_FATSZ16, E_FSVER, E_ROOTCLUS, E_ACTIVEFAT = 20, 21, 22, 23, 24
E_BUF_ALIGN, E_NOT_MOUNTED, E_NAME, E_NOTFOUND, E_IS_DIR = 25, 26, 27, 28, 29
E_DIRLOOP, E_BADCLUS, E_BADCLUS_MARK, E_CHAINLOOP = 30, 31, 32, 33
E_SHORT_CHAIN, E_FILE_CLUSTER, E_NO_FILE, E_NULL_DST = 34, 35, 36, 37
E_BAD_MAX, E_FILE_TOO_BIG = 38, 39

EXPECT: list[tuple[str, int]] = []


def ex(label: str, *values: int) -> None:
    for i, v in enumerate(values):
        EXPECT.append((label if len(values) == 1 else f"{label}[{i}]", v))


# 1. no reader
ex("no reader: FatMount refuses", 0)
ex("no reader: error code", E_NO_READER)
ex("no reader: FatBlockReader is 0", 0)
ex("reader installed", 1)
# 2. partition number
ex("FatMount(0) refuses", 0)
ex("FatMount(0) code", E_PARTNUM)
ex("FatMount(5) refuses", 0)
ex("FatMount(5) code", E_PARTNUM)
# 3. the good mount
ex("FatMount(1)", 1)
ex("mount left no error", E_NONE)
ex("FatMounted", 1)
ex("FatType is 32", 32)
ex("partition type byte $0C", 0x0C)
ex("partition LBA is 63, NOT 0", PART_LBA)
ex("partition sector count", PART_SECS)
ex("total sectors from the BPB", TOT_SECS)
ex("bytes per cluster", SEC_PER_CLUS * SEC)
ex("CountofClusters is exactly the FAT32 boundary", CLUSTERS)
ex("FAT LBA is absolute", FAT_LBA)
ex("data LBA is absolute", DATA_LBA)
ex("root cluster", 2)
# 4. the file
ex("FatOpen(PMF.IMG)", 1)
ex("open left no error", E_NONE)
ex("FatSize", PMF_SIZE)
ex("first cluster", 5)
ex("FatIsOpen", 1)
ex("whole-file read returned the size", PMF_SIZE)
ex("FatTell after the read", PMF_SIZE)
ex("a read past the end returns 0", 0)
ex("end of file is not an error", E_NONE)
# 5. piecewise
ex("FatRewind", 1)
ex("FatTell after rewind", 0)
ex("100 bytes at a time totals the size", PMF_SIZE)
ex("FatTell after the pieces", PMF_SIZE)
# 6. unaligned destination
ex("reopen for the unaligned read", 1)
ex("unaligned read returned the size", PMF_SIZE)
# 7. case, and a name behind a long-name run
ex("lowercase name matches", 1)
ex("lowercase size", PMF_SIZE)
ex("the 8.3 entry behind the $0F run", 1)
ex("its size", 10)
# 8. names refused
ex("long name refused", 0)
ex("long name code - a valid long name, not there", E_NOTFOUND)
ex("path separator refused", 0)
ex("path separator code - no BOOT folder", E_NOTFOUND)
ex("two dots refused", 0)
ex("two dots code - a valid long name, not there", E_NOTFOUND)
ex("four-character extension refused", 0)
ex("four-character extension code - a valid long name, not there", E_NOTFOUND)
# 9. skipping
ex("volume label is not a file", 0)
ex("volume label code", E_NOTFOUND)
ex("a directory is refused as a file", 0)
ex("directory code", E_IS_DIR)
ex("a missing name", 0)
ex("missing name code", E_NOTFOUND)
# 10. corrupt entries
ex("cluster off the volume", 0)
ex("cluster off the volume code", E_BADCLUS)
ex("nonzero size with no cluster", 0)
ex("no cluster code", E_FILE_CLUSTER)
ex("size larger than the volume", 0)
ex("too-big code", E_FILE_TOO_BIG)
# 11. empty file
ex("an empty file opens", 1)
ex("its size is 0", 0)
ex("its first cluster is 0", 0)
ex("reading it returns 0", 0)
ex("and that is not an error", E_NONE)
# 12. bad chains
ex("LOOP.IMG opens", 1)
ex("LOOP.IMG read refuses", -1)
ex("LOOP.IMG code", E_CHAINLOOP)
ex("SELF.IMG opens", 1)
ex("SELF.IMG read refuses", -1)
ex("SELF.IMG code", E_CHAINLOOP)
ex("SHORT.BIN opens", 1)
ex("SHORT.BIN read refuses", -1)
ex("SHORT.BIN code", E_SHORT_CHAIN)
ex("BADMARK.BIN opens", 1)
ex("BADMARK.BIN read refuses", -1)
ex("BADMARK.BIN code", E_BADCLUS_MARK)
# 13. medium failure
ex("reopen before the medium fails", 1)
ex("read refuses when the reader fails", -1)
ex("read failure code", E_READ_FAIL)
ex("FatLastLba names the sector", clus_lba(9))
# 14. argument refusals
ex("reopen", 1)
ex("null destination refused", -1)
ex("null destination code", E_NULL_DST)
ex("negative max refused", -1)
ex("negative max code", E_BAD_MAX)
ex("FatClose closed it", 0)
ex("read with no file refused", -1)
ex("no file code", E_NO_FILE)
ex("FatSize with no file", -1)
ex("FatSize code", E_NO_FILE)
# 15. MBR refusals
ex("no $55AA at LBA 0", 0)
ex("no MBR code", E_NO_MBR)
ex("bad status byte", 0)
ex("bad status code", E_PART_STATUS)
ex("empty partition slot", 0)
ex("empty slot code", E_PART_EMPTY)
ex("protective MBR", 0)
ex("GPT code", E_PART_GPT)
ex("FAT16 partition type byte", 0)
ex("partition type code", E_PART_TYPE)
ex("FAT32 type with LBA 0", 0)
ex("partition geometry code", E_PART_GEOM)
# 16. boot sector refusals
ex("no $55AA in the boot sector", 0)
ex("no boot sector code", E_NO_BOOTSEC)
ex("1024-byte sectors", 0)
ex("sector size code", E_SECSIZE)
ex("3 sectors per cluster", 0)
ex("sectors-per-cluster code", E_SPC)
ex("zero reserved sectors", 0)
ex("reserved code", E_RESERVED)
ex("zero FATs", 0)
ex("num FATs code", E_NUMFATS)
ex("FAT bigger than the volume", 0)
ex("geometry code", E_GEOMETRY)
ex("volume bigger than the partition", 0)
ex("geometry code again", E_GEOMETRY)
ex("FATSz16 nonzero on FAT32", 0)
ex("FATSz16 code", E_FATSZ16)
ex("RootEntCnt nonzero on FAT32", 0)
ex("RootEntCnt code", E_ROOTENT)
ex("unknown FSVer", 0)
ex("FSVer code", E_FSVER)
ex("active FAT 2 of 2", 0)
ex("active FAT code", E_ACTIVEFAT)
ex("active FAT 1 mounts", 1)
ex("and the FAT LBA moves to the mirror", FAT1_LBA)
ex("root cluster 0", 0)
ex("root cluster code", E_ROOTCLUS)
# 17. FAT16 / FAT12
ex("the FAT16 volume is refused", 0)
ex("FAT16 code", E_FAT16)
ex("FatType still reports 16", 16)
ex("the FAT12 volume is refused", 0)
ex("FAT12 code", E_FAT12)
ex("FatType still reports 12", 12)
# 18. looping root directory
ex("the looping-root volume mounts", 1)
ex("its root cluster is 3", 3)
ex("the scan refuses", 0)
ex("directory loop code", E_DIRLOOP)
# 19. before a mount
ex("a failed mount leaves it unmounted", 0)
ex("FatOpen refuses", 0)
ex("not mounted code", E_NOT_MOUNTED)
# 20. recovery
ex("it mounts again", 1)
ex("still FAT32", 32)
ex("still opens", 1)
ex("still the right size", PMF_SIZE)
# 21. the reader's own contract
ex("the reader was never given a misaligned buffer", 0)
ex("the reader was actually used", 1)
ex("the direct path filled four whole sectors", PMF_SIZE // SEC)
ex("the unaligned destination took the direct path too", PMF_SIZE // SEC)

# =====================================================================
#  THE WRITE HALF.  Everything below is a value the PROGRAM reports;
#  the structural proof - the FAT, the directory, FSInfo, and the fact
#  that nothing outside the FAT and data regions was ever written - is
#  done by this harness afterwards, reading tdisk[] back out of the
#  interpreter and parsing it without asking the program anything.
# =====================================================================
E_NO_WRITER, E_WRITE_FAIL, E_SIZE_MISMATCH = 40, 41, 42
E_NO_SPACE, E_DIR_FULL, E_EXISTS, E_READ_ONLY = 43, 44, 45, 46
E_FSINFO, E_BAD_LEN, E_LBA_RANGE = 47, 48, 49
E_RESERVED_CLUS, E_NO_DIRENT, E_GROW_REFUSED = 50, 51, 52

# 22. every write entry point refuses when no writer was installed
ex("no writer yet", 0)
ex("mount for the write half", 1)
ex("open for the write half", 1)
ex("FatWrite with no writer", -1)
ex("FatWrite no-writer code", E_NO_WRITER)
ex("FatOverwrite with no writer", 0)
ex("FatOverwrite no-writer code", E_NO_WRITER)
ex("FatCreate with no writer", 0)
ex("FatCreate no-writer code", E_NO_WRITER)
ex("FatDelete with no writer", 0)
ex("FatDelete no-writer code", E_NO_WRITER)
ex("writer installed", 1)
ex("and nothing has been written yet", 0)
# 23. what the mount learned about free space
ex("FSInfo signatures checked out", 1)
ex("FSInfo LBA is absolute", FSINFO_LBA)
ex("free count starts unknown", -1)
ex("next-free hint starts unknown", 0)
ex("no full scan has run", 0)
ex("all FATs are mirrored", 1)
ex("two FATs", NUM_FATS)
ex("FAT copy 0 base", FAT_BASE)
ex("one past the last FAT sector", FAT_END)
ex("one past the last data sector", DATA_END)
# 24. growing a file across a cluster boundary
GROWN = PMF_SIZE + 300                     # 2800
ex("open PMF.IMG to append", 1)
ex("its size before", PMF_SIZE)
ex("seek to the append position", 1)
ex("tell is the old size", PMF_SIZE)
ex("300 bytes written", 300)
ex("the append left no error", E_NONE)
ex("the size grew", GROWN)
ex("tell is the new size", GROWN)
ex("the first allocation rebuilt the free count", 1)
ex("free clusters after one allocation", CLUSTERS - 17)
ex("the entry's sector", clus_lba(2))
ex("the entry's offset - the seventh slot", 6 * 32)
# 25. read it back through a fresh open
ex("reopen after the append", 1)
ex("the reopened size", GROWN)
ex("the whole grown file came back", GROWN)
# 26. truncation
ex("open to truncate", 1)
ex("truncate LARGER is refused", 0)
ex("grow-refused code", E_GROW_REFUSED)
ex("truncate negative is refused", 0)
ex("negative length code", E_BAD_LEN)
ex("neither refusal changed the size", GROWN)
ex("truncate to 1000", 1)
ex("truncate left no error", E_NONE)
ex("the size shrank", 1000)
ex("the position is still 0", 0)
ex("and it reads 1000 bytes, not 2800", 1000)
ex("the new end really is the end", 0)
ex("rewind", 1)
# 27. create, write, close, find again
ex("FatCreate", 1)
ex("it is open", 1)
ex("an empty file is 0 bytes", 0)
ex("and has NO first cluster", 0)
ex("attribute is ARCHIVE", 0x20)
ex("creating it twice is refused", 0)
ex("exists code", E_EXISTS)
ex("reopen the created file", 1)
ex("still empty", 0)
ex("1300 bytes written", 1300)
ex("the size is 1300", 1300)
ex("it now has a first cluster", 4)
ex("a FRESH open finds it", 1)
ex("with the right size", 1300)
ex("and the right first cluster", 4)
ex("and reads back 1300 bytes", 1300)
# 28. a create that has to extend the root directory
ex("create the file that fills the directory", 1)
ex("its entry is still in the first root cluster", clus_lba(2))
ex("in the sixteenth slot", 15 * 32)
ex("100 bytes into it", 100)
ex("its size", 100)
ex("reopen it", 1)
ex("its size again", 100)
ex("a create into the EXTENDED directory", 1)
ex("its entry is in the second root cluster", clus_lba(10))
ex("first slot of it", 0)
ex("a fresh scan walks into the new cluster", 1)
ex("and finds an empty file", 0)
# 29. deletion
ex("FatDelete", 1)
ex("delete left no error", E_NONE)
ex("the deleted name is gone", 0)
ex("gone code", E_NOTFOUND)
ex("deleting a missing name", 0)
ex("missing code", E_NOTFOUND)
ex("deleting a directory is refused", 0)
ex("a folder that is not empty is refused", 55)
ex("deleting an unspellable name is refused", 0)
ex("a long name that is not there", E_NOTFOUND)
# 30. FatOverwrite, resizing
ex("open the 100-byte file", 1)
ex("its size", 100)
ex("overwrite with 1700 bytes", 1)
ex("overwrite left no error", E_NONE)
ex("it grew to 1700", 1700)
ex("reopen", 1)
ex("still 1700", 1700)
ex("and reads back 1700", 1700)
ex("reopen to shrink", 1)
ex("overwrite with 40 bytes", 1)
ex("it shrank to 40", 40)
ex("reopen after the shrink", 1)
ex("still 40", 40)
# 31. argument refusals
ex("open for the refusals", 1)
ex("FatWrite from a null source", -1)
ex("null source code", E_NULL_DST)
ex("FatWrite a negative length", -1)
ex("negative length code again", E_BAD_LEN)
ex("FatWrite zero bytes", 0)
ex("zero bytes is not an error", E_NONE)
ex("seek past the end", 0)
ex("seek past the end code", E_BAD_LEN)
ex("seek negative", 0)
ex("seek negative code", E_BAD_LEN)
ex("seek to the append position is allowed", 1)
ex("and leaves no error", E_NONE)
ex("FatWrite with nothing open", -1)
ex("no file code", E_NO_FILE)
ex("FatTruncate with nothing open", 0)
ex("no file code again", E_NO_FILE)
ex("FatSeek with nothing open", 0)
ex("no file code once more", E_NO_FILE)
# 32. a read-only entry
ex("remount after marking an entry read-only", 1)
ex("open the read-only file", 1)
ex("its attribute", 0x21)
ex("FatWrite is refused", -1)
ex("read-only code", E_READ_ONLY)
ex("FatTruncate is refused", 0)
ex("read-only code again", E_READ_ONLY)
ex("FatDelete is refused", 0)
ex("read-only code once more", E_READ_ONLY)
ex("remount with the attribute back", 1)
# 33. a valid FSInfo hint is honoured
ex("remount with a hint poked in", 1)
ex("the mount is clean", E_NONE)
ex("the hint was taken as given", 700)
ex("no scan was needed to take it", 0)
ex("create a file to spend it on", 1)
ex("write 10 bytes", 10)
ex("it landed exactly on the hinted cluster", 700)
ex("and still no full scan happened", 0)
# 34. an FSInfo whose signature is wrong
ex("a broken FSInfo still mounts", 1)
ex("but it is reported", E_FSINFO)
ex("mounted anyway", 1)
ex("FSInfo is not usable", 0)
ex("and has no LBA", -1)
ex("a file can still be created", 1)
ex("and written", 10)
ex("allocation had to count for itself", 1)
ex("remount with the signature restored", 1)
ex("clean again", E_NONE)
ex("FSInfo is usable again", 1)
ex("FatRescanFree", 1)
ex("rescan left no error", E_NONE)
# 35. the medium refusing a write
ex("open the file whose sector will fail", 1)
ex("the write is refused", -1)
ex("write-failure code", E_WRITE_FAIL)
ex("FatLastLba names the sector", 1)
ex("reopen after the failure", 1)
ex("its size is untouched", 40)
# 36. the deletion the harness will inspect in the finished image
ex("delete the hinted file", 1)
ex("that delete left no error", E_NONE)
ex("it is gone", 0)
ex("gone code again", E_NOTFOUND)
# 37. the writer's contract
ex("the writer was never handed a misaligned buffer", 0)
ex("no write was ever aimed outside the partition", 0)
ex("the writer was actually used", 1)
ex("the write trace is complete", 0)
ex("and so are the per-write snapshots", 0)

ex("check count", len(EXPECT))    # the value of nres at that moment


# =====================================================================
#  Running the thing
# =====================================================================
SRC = ROOT / "RaspberryPi4" / "Examples" / "Diagnostics" / "pi4FatSelfTest.pi4"
LIB = ROOT / "Anvil" / "Storage" / "fat32.pbi"
# The Pi 4 compatibility include the self-test program names.
WRAPPER = ROOT / "RaspberryPi4" / "Lib" / "fat.pi4"
COMPILER: str = ""


def run_cmd(args: list[str]) -> str:
    r = subprocess.run(args, cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
                       text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, check=False)
    if r.returncode != 0:
        raise SystemExit(f"The compile failed: {' '.join(args)}\n{r.stdout}")
    return r.stdout


def build_image(src: pathlib.Path, img: pathlib.Path) -> dict:
    out = run_cmd([COMPILER, "--compile", str(src), "-t", "pi4",
                   "--load-addr", hex(LOAD), "-o", str(img), "-s"])
    if not img.exists():
        raise SystemExit("The compiler reported success but wrote no "
                         "image:\n" + out)
    symfile = img.parent / (img.name + ".sym")
    syms = dict(
        line.split("=", 1)
        for line in symfile.read_text(encoding="utf-8-sig").splitlines()
        if "=" in line
    )
    return {k: int(v) for k, v in syms.items()}


class Run:
    """One execution: what the program reported, and the medium it left."""

    def __init__(self, cpu, sym, steps: int) -> None:
        self.cpu = cpu
        self.sym = sym
        self.steps = steps
        n = cpu.load(sym["global_nres"], 8)
        base = sym["global_res"]
        self.res = [cpu.load(base + i * 8, 8) for i in range(n)]
        self.res = [v - (1 << 64) if v >= (1 << 63) else v for v in self.res]
        self.nres = n

        # The medium, read straight back out of the array the program
        # writes into.  THIS is the evidence; everything in self.res is
        # the program's own account of what it did.
        tb = sym["global_tdisk"]
        mem = cpu.memory
        self.disk = bytes(mem.get(tb + i, 0) for i in range(2048 * SEC))

        # The write trace.  Non-negative entries are LBAs, negative ones
        # are TdMark tags.
        ln = cpu.load(sym["global_tdlogn"], 8)
        lb = sym["global_tdlog"]
        raw = [cpu.load(lb + i * 8, 8) for i in range(ln)]
        self.log = [v - (1 << 64) if v >= (1 << 63) else v for v in raw]
        self.log_lost = cpu.load(sym["global_tdloglost"], 8)

        # The bytes of each write, in the same order.  self.writes[k] is
        # (lba, 512 bytes) for the k-th write; the LBAs come from the
        # trace and the bytes from the snapshot array, and the program
        # appends to both on every call so they cannot drift apart.
        sn = cpu.load(sym["global_tdsnapn"], 8)
        sb = sym["global_tdsnap"]
        snaps = bytes(mem.get(sb + i, 0) for i in range(sn * SEC))
        self.snap_lost = cpu.load(sym["global_tdsnaplost"], 8)
        lbas = [v for v in self.log if v >= 0]
        self.writes = [(lbas[k], snaps[k * SEC:(k + 1) * SEC])
                       for k in range(min(sn, len(lbas)))]

    def sec(self, lba: int) -> bytes:
        return self.disk[lba * SEC:(lba + 1) * SEC]

    def u32(self, lba: int, off: int) -> int:
        return struct.unpack_from("<I", self.disk, lba * SEC + off)[0]

    # ---- the FAT, as this harness reads it, not as fat32.pbi reports it
    def fat_entry(self, copy: int, cl: int) -> int:
        off = (FAT_BASE + copy * FAT_SECS) * SEC + cl * 4
        return struct.unpack_from("<I", self.disk, off)[0] & 0x0FFFFFFF

    def chain(self, start: int, limit: int = 4096) -> list:
        """Walk a chain with a bound of its own, so a defect in fat32.pbi
        that produced a loop cannot hang the harness meant to catch it."""
        out = []
        cl = start
        while 2 <= cl <= CLUSTERS + 1 and len(out) < limit:
            out.append(cl)
            cl = self.fat_entry(0, cl)
        return out

    # ---- the root directory, walked the same way fat32.pbi walks it
    def root_sectors(self) -> list:
        out = []
        cl = 2
        seen = 0
        while 2 <= cl <= CLUSTERS + 1 and seen < 64:
            for s in range(SEC_PER_CLUS):
                out.append(clus_lba(cl) + s)
            seen += 1
            cl = self.fat_entry(0, cl)
        return out

    def dirents(self):
        """Yield (lba, offset, 32 bytes) for every slot in the root."""
        for lba in self.root_sectors():
            for e in range(SEC // 32):
                off = e * 32
                yield lba, off, self.disk[lba * SEC + off:lba * SEC + off + 32]

    def find(self, name: bytes):
        """The finished image's own answer for a name, found by scanning
        the way a fresh driver would: skip $E5, stop at $00, skip $0F
        entries and volume labels."""
        for lba, off, e in self.dirents():
            if e[0] == 0x00:
                return None
            if e[0] == 0xE5:
                continue
            if e[0x0B] == 0x0F or (e[0x0B] & 0x08):
                continue
            if e[0:11] == name:
                clus = ((struct.unpack_from("<H", e, 0x14)[0] << 16) |
                        struct.unpack_from("<H", e, 0x1A)[0])
                size = struct.unpack_from("<I", e, 0x1C)[0]
                return dict(lba=lba, off=off, attr=e[0x0B], clus=clus,
                            size=size, raw=e)
        return None

    def file_bytes(self, name: bytes) -> bytes:
        f = self.find(name)
        if f is None:
            return b""
        out = bytearray()
        for cl in self.chain(f["clus"]):
            start = clus_lba(cl) * SEC
            out += self.disk[start:start + SEC_PER_CLUS * SEC]
            if len(out) >= f["size"]:
                break
        return bytes(out[:f["size"]])


def execute(sym: dict, img: pathlib.Path) -> Run:
    blob = img.read_bytes()
    cpu = A64(pc=LOAD)
    for i, b in enumerate(blob):
        cpu.memory[LOAD + i] = b
    # Names for the alignment rule's message, read from the `.dbg` the
    # compiler writes. A missing `.dbg` costs the name, not the check.
    attach_symbols(cpu, img, LOAD)

    # Skip the BSS-zero loop.  A fresh interpreter dict already reads as
    # zero everywhere, but the loop would wipe the fabricated disk if the
    # disk were written before it ran.
    cpu.pc = LOAD + sym["__a64_bss_done"]

    disk = build()
    base = sym["global_tdisk"]
    for lba, data in disk.s.items():
        for i, b in enumerate(data):
            if b:
                cpu.memory[base + lba * SEC + i] = b

    trap = LOAD + sym["_a64_end_trap"]
    steps = 0
    for steps in range(120_000_000):
        if cpu.pc == trap:
            break
        cpu.step()
    else:
        raise SystemExit("the test program never reached its end trap")
    return Run(cpu, sym, steps)


# =====================================================================
#  THE STRUCTURAL PROOF
#
#  Nothing below asks the program anything.  It reads the medium the
#  program left behind and checks it the way a DIFFERENT implementation
#  would - which is the only kind of check that can catch a library
#  being confidently wrong in the same way twice.
# =====================================================================

def allowed(lba: int) -> bool:
    """The three regions fat32.pbi is permitted to write, computed here
    from the fabricated geometry.  fat32.pbi derives the same three from
    the BPB; if the two ever disagree, one of them has the volume
    wrong."""
    if lba == FSINFO_LBA:
        return True
    if FAT_BASE <= lba < FAT_END:
        return True
    if DATA_LBA <= lba < DATA_END:
        return True
    return False


def window(log: list, a: int, b: int) -> list:
    """The LBAs written between TdMark(a) and TdMark(b)."""
    try:
        i = log.index(-a)
        j = log.index(-b)
    except ValueError:
        return []
    return [v for v in log[i + 1:j] if v >= 0]


def check_structure(r: Run, fails: list) -> int:
    """Reads the finished medium and judges it.  Returns how many
    assertions were made."""
    n = 0

    def want(cond, msg: str) -> None:
        nonlocal n
        n += 1
        if not cond:
            fails.append(msg)

    model = build()

    # ---- 1. NOTHING WAS WRITTEN WHERE IT MAY NOT BE -------------------
    want(r.log_lost == 0,
         "the write trace overflowed by %d entries - the 'nothing "
         "outside' proof would have a hole in it" % r.log_lost)
    bad = sorted({v for v in r.log if v >= 0 and not allowed(v)})
    want(not bad,
         "writes were aimed outside the FAT and data regions: %s" % bad[:8])
    inside = [v for v in r.log if v >= 0]
    want(len(inside) > 40,
         "only %d writes happened - the write half barely ran" % len(inside))

    # And from the BYTES, independently: every sector outside an allowed
    # region must still be exactly what was fabricated.  This catches a
    # write that reached the medium by a route the trace missed.
    untouched = (list(range(0, FSINFO_LBA)) +
                 list(range(FSINFO_LBA + 1, FAT_BASE)))
    changed = [lba for lba in untouched
               if r.sec(lba) != bytes(model.sec(lba))]
    want(not changed,
         "sector(s) %s changed and lie outside every region this library "
         "may write" % changed[:8])
    for lba in (FAT16_BOOT_LBA, FAT12_BOOT_LBA):
        want(r.sec(lba) == bytes(model.sec(lba)),
             "the decoy boot sector at LBA %d was written to" % lba)
    want(r.sec(0) == bytes(model.sec(0)), "the MBR changed")
    want(r.sec(PART_LBA) == bytes(model.sec(PART_LBA)),
         "the volume boot sector was written to")

    # ---- 2. THE SECOND FAT IS A MIRROR OF THE FIRST -------------------
    diff = [s for s in range(FAT_SECS)
            if r.sec(FAT_BASE + s) != r.sec(FAT_BASE + FAT_SECS + s)]
    want(not diff,
         "the two FATs disagree in %d sector(s), first at FAT offset %d - "
         "the mirror was not maintained"
         % (len(diff), diff[0] if diff else -1))

    # ---- 3. THE GROWN, THEN TRUNCATED, FILE ---------------------------
    pmf = r.find(b"PMF     IMG")
    want(pmf is not None, "PMF.IMG is not in the finished directory")
    if pmf:
        want(pmf["size"] == 1000,
             "PMF.IMG's directory size is %d, want 1000" % pmf["size"])
        want(pmf["clus"] == 5,
             "PMF.IMG's first cluster is %d, want 5" % pmf["clus"])
        want(r.chain(5) == [5, 9],
             "PMF.IMG's chain is %s, want [5, 9]" % r.chain(5))
        want(r.file_bytes(b"PMF     IMG") == content(2500)[:1000],
             "PMF.IMG's surviving 1000 bytes are not the original ones")

    # ---- 4. THE FREED CLUSTERS REALLY ARE FREE ------------------------
    for cl in (6, 7, 12):
        want(r.fat_entry(0, cl) == 0,
             "cluster %d was freed but its FAT entry reads %#x"
             % (cl, r.fat_entry(0, cl)))

    # ---- 4a. THE RESERVED TOP FOUR BITS SURVIVED THE WRITES -----------
    # Entry 9 was fabricated as $A0000006 and rewritten to end-of-chain
    # when the file was truncated; entry 8 was $5FFFFFF8 and was linked
    # onward when it grew.  [FATGEN] says the high nibble is reserved
    # and must be preserved on write.  Read RAW here - fat_entry() masks
    # it off, which is what a READER is supposed to do.
    for cl, nib in ((9, 0xA), (8, 0x5)):
        raw = struct.unpack_from("<I", r.disk, FAT_BASE * SEC + cl * 4)[0]
        want((raw >> 28) == nib,
             "cluster %d's reserved top four bits are %#x, want %#x - a "
             "write zeroed bits [FATGEN] says to carry over"
             % (cl, raw >> 28, nib))

    # ---- 5. THE CREATED FILES -----------------------------------------
    two = r.find(b"TWO     BIN")
    want(two is not None, "TWO.BIN is not in the finished directory")
    if two:
        want(two["size"] == 40, "TWO.BIN's size is %d, want 40" % two["size"])
        want(two["attr"] == 0x20,
             "TWO.BIN's attribute is %#x, want $20 ARCHIVE" % two["attr"])
        want(r.chain(two["clus"]) == [8],
             "TWO.BIN's chain is %s, want [8]" % r.chain(two["clus"]))
        want(r.file_bytes(b"TWO     BIN") == wcontent(40),
             "TWO.BIN's 40 bytes are not what was written")
        wdate = struct.unpack_from("<H", two["raw"], 0x18)[0]
        wtime = struct.unpack_from("<H", two["raw"], 0x16)[0]
        want(wdate == 0x0021,
             "TWO.BIN's write DATE is %#06x, want $0021 - the 1980-01-01 "
             "sentinel" % wdate)
        want(wtime == 0x0000,
             "TWO.BIN's write TIME is %#06x, want the 00:00:00 sentinel"
             % wtime)

    three = r.find(b"THREE   BIN")
    want(three is not None,
         "THREE.BIN is not findable - the root directory extension did not "
         "produce a scannable second cluster")
    if three:
        want(three["lba"] == clus_lba(10),
             "THREE.BIN's entry is at LBA %d, want %d - the second root "
             "cluster" % (three["lba"], clus_lba(10)))
        want(three["size"] == 0 and three["clus"] == 0,
             "THREE.BIN should be an empty file with no first cluster")

    nofsi = r.find(b"NOFSI   BIN")
    want(nofsi is not None, "NOFSI.BIN is not in the finished directory")
    if nofsi:
        want(nofsi["size"] == 10,
             "NOFSI.BIN's size is %d, want 10" % nofsi["size"])
        want(r.file_bytes(b"NOFSI   BIN") == wcontent(10),
             "NOFSI.BIN's bytes are not what was written")

    # ---- 6. THE ROOT DIRECTORY IS STILL A DIRECTORY -------------------
    want(r.chain(2) == [2, 10],
         "the root directory's chain is %s, want [2, 10]" % r.chain(2))
    seen_end = False
    junk = None
    for lba, off, e in r.dirents():
        if e[0] == 0x00:
            seen_end = True
            break
        if e[0] != 0xE5 and e[0x0B] != 0x0F and not (e[0x0B] & 0x08):
            if any(c < 0x20 for c in e[0:11]) and junk is None:
                junk = (lba, off)
    want(junk is None,
         "the entry at %s has control characters in its name - a directory "
         "cluster was linked in without being zeroed" % (junk,))
    want(seen_end,
         "the root directory has no $00 end marker anywhere - a scan would "
         "run off the end of its chain")

    # ---- 7. THE DELETED FILE ------------------------------------------
    hint = [(lba, off, e) for lba, off, e in r.dirents()
            if e[1:11] == b"INT    BIN"]
    want(len(hint) == 1,
         "expected exactly one slot still carrying the deleted name, found "
         "%d" % len(hint))
    if hint:
        want(hint[0][2][0] == 0xE5,
             "the deleted entry's first byte is %#04x, want $E5"
             % hint[0][2][0])
    want(r.fat_entry(0, 700) == 0,
         "the deleted file's cluster 700 has FAT entry %#x, want 0 - it was "
         "not freed" % r.fat_entry(0, 700))
    want(r.find(b"HINT    BIN") is None,
         "a scan of the finished directory still finds the deleted name")

    # ---- 8. FSINFO AGREES WITH A FULL SCAN OF THE FAT -----------------
    free = 0
    first_free = 0
    for cl in range(2, CLUSTERS + 2):
        if r.fat_entry(0, cl) == 0:
            free += 1
            if first_free == 0:
                first_free = cl
    want(r.u32(FSINFO_LBA, 0x000) == 0x41615252, "FSI_LeadSig was damaged")
    want(r.u32(FSINFO_LBA, 0x1E4) == 0x61417272, "FSI_StrucSig was damaged")
    want(r.u32(FSINFO_LBA, 0x1FC) == 0xAA550000, "FSI_TrailSig was damaged")
    want(r.u32(FSINFO_LBA, 0x1E8) == free,
         "FSI_Free_Count is %d, a full scan of the FAT says %d"
         % (r.u32(FSINFO_LBA, 0x1E8), free))
    want(r.u32(FSINFO_LBA, 0x1EC) == first_free,
         "FSI_Nxt_Free is %d, the first free cluster is %d"
         % (r.u32(FSINFO_LBA, 0x1EC), first_free))

    # ---- 9. A BROKEN FSINFO SECTOR IS LEFT ALONE ----------------------
    w = window(r.log, 14, 15)
    want(w, "the broken-FSInfo window is empty - that phase did not run")
    want(FSINFO_LBA not in w,
         "the FSInfo sector was written while its signatures were wrong - "
         "and a sector that is not an FSInfo structure is something else")

    # ---- 9a. THE FAT NEVER LINKS TO A FREE CLUSTER, AT ANY INSTANT ----
    # This is the ordering rule stated as an invariant instead of as a
    # sequence, and it is checked after EVERY SINGLE WRITE rather than
    # at the end.  A trace of LBAs cannot see it: fat_SetEntry writes
    # the same sector twice in a row when it claims a cluster and then
    # links it on, so claim-then-link and link-then-claim are the same
    # two addresses in the same order.  They are not the same two
    # SECTORS, and the second order leaves a window in which a live
    # chain runs into free space - which is the failure a repair tool
    # cannot undo, it can only pick a loser.
    #
    # Only clusters 2..127 are covered, because they are the ones whose
    # entries share FAT sector 0 with each other, and they are every
    # cluster this test uses except the hint at 700.
    want(r.snap_lost == 0,
         "%d written sectors were not kept - the after-every-write check "
         "would have a hole in it" % r.snap_lost)
    viol = None
    for k, (lba, buf) in enumerate(r.writes):
        if lba not in (FAT_BASE, FAT_BASE + FAT_SECS):
            continue
        ent = [struct.unpack_from("<I", buf, i * 4)[0] & 0x0FFFFFFF
               for i in range(128)]
        for cl in range(2, 128):
            v = ent[cl]
            if 2 <= v <= 127 and ent[v] == 0:
                viol = (k, lba, cl, v)
                break
        if viol:
            break
    want(viol is None,
         "write #%s left the FAT with cluster %s pointing at cluster %s, "
         "whose own entry says FREE - a crash there hands that cluster to "
         "the next file as well"
         % (viol[0] if viol else "-", viol[2] if viol else "-",
            viol[3] if viol else "-"))

    # ---- 10. THE ORDER OF THE WRITES ----------------------------------
    # Neither of these is visible in a finished image.  A correct image
    # is produced by the wrong order just as happily as by the right one,
    # right up until the power goes off in the middle.
    w = window(r.log, 1, 2)
    want(w, "the append window is empty - phase 24 did not run")
    if w:
        dirlba = clus_lba(2)
        data = [i for i, v in enumerate(w)
                if v in (clus_lba(8), clus_lba(4))]
        dirw = [i for i, v in enumerate(w) if v == dirlba]
        want(data, "no data sector was written during the append")
        want(dirw, "the directory entry was never written during the append")
        if data and dirw:
            want(min(dirw) > max(data),
                 "the directory entry was written BEFORE the data it "
                 "describes - an interrupted write would leave a file "
                 "promising bytes that were never stored")
        fatw = [i for i, v in enumerate(w) if FAT_BASE <= v < FAT_END]
        c4 = [i for i, v in enumerate(w) if v == clus_lba(4)]
        want(fatw and c4,
             "the append did not both claim a cluster and fill it")
        if fatw and c4:
            want(min(fatw) < min(c4),
                 "cluster 4 was written to before it was claimed in the "
                 "FAT - two files can then be handed the same cluster")

    # The truncate window, where the order is the other way round: the
    # directory entry must stop referring to the tail BEFORE the tail is
    # released, or an interruption leaves a live file whose chain runs
    # through free space.
    w = window(r.log, 3, 4)
    want(w, "the truncate window is empty - phase 26 did not run")
    if w:
        dirw = [i for i, v in enumerate(w) if v == clus_lba(2)]
        fatw = [i for i, v in enumerate(w) if FAT_BASE <= v < FAT_END]
        want(dirw, "the directory entry was never written during the "
                   "truncate - the file's size would still be the old one")
        want(fatw, "the FAT was never written during the truncate - the "
                   "tail's clusters would still be in use")
        if dirw and fatw:
            want(min(dirw) < min(fatw),
                 "the tail was released BEFORE the directory stopped "
                 "pointing at it - an interruption there leaves a live "
                 "entry whose chain runs through free space")

    return n


def check_reported(r: Run, fails: list) -> int:
    """The program's own account, against the list this harness holds
    independently."""
    if r.nres != len(EXPECT):
        fails.append("check count: program made %d, harness expects %d"
                     % (r.nres, len(EXPECT)))
    for i, (label, wantv) in enumerate(EXPECT):
        if i >= len(r.res):
            fails.append("#%d %s: never ran" % (i, label))
        elif r.res[i] != wantv:
            fails.append("#%d %s: got %d, want %d"
                         % (i, label, r.res[i], wantv))
    return len(EXPECT)


def check_bytes(r: Run, fails: list) -> int:
    """The read half's three destinations, and the write half's three."""
    n = 0
    sym, cpu = r.sym, r.cpu

    def grab(name: str, off: int, ln: int) -> bytes:
        addr = sym["global_" + name] + off
        return bytes(cpu.memory.get(addr + i, 0) for i in range(ln))

    for name, off, ln, wantb in (
            ("dsta", 0, PMF_SIZE, content(PMF_SIZE)),
            ("dstb", 0, PMF_SIZE, content(PMF_SIZE)),
            ("dstu", 1, PMF_SIZE, content(PMF_SIZE)),
            # the write half: the grown file, a created file, and a file
            # FatOverwrite made LONGER than it was
            ("dstw", 0, 2800, content(PMF_SIZE) + wcontent(300)),
            ("dstn", 0, 1300, wcontent(1300)),
            ("dsto", 0, 1700, wcontent(1700)),
    ):
        n += 1
        gotb = grab(name, off, ln)
        if gotb != wantb:
            bad = next(i for i in range(ln) if gotb[i] != wantb[i])
            fails.append("%s: first difference at byte %d (got %#04x, "
                         "want %#04x)" % (name, bad, gotb[bad], wantb[bad]))
    n += 1
    if cpu.memory.get(sym["global_dstu"], 0) != 0:
        fails.append("dstu: byte 0 was written; the +1 offset was ignored")
    return n


# =====================================================================
#  MUTATION - proof the gate can go red
#
#  A gate that has only ever passed proves nothing about itself.  Each
#  entry below breaks fat32.pbi in a way somebody could plausibly write,
#  or plausibly tidy into existence, and the gate must go RED for every
#  one.  Some carry TWO edits, because a defence and the arithmetic it
#  defends have to be broken together before the damage is visible -
#  which is itself the argument for having the defence.
# =====================================================================
MUTATIONS = [
    ("the chain walk is off by one",
     [("  While k < idx\n    nxt = fat_NextOrAlloc(cl, grow)",
       "  While k <= idx\n    nxt = fat_NextOrAlloc(cl, grow)")]),

    ("the directory size update is forgotten after a write",
     [("  ; STEP 3. Not one line earlier.\n"
       "  If fat_UpdateDirEntry(fat_fileSize, fat_firstClus) = 0\n"
       "    ProcedureReturn -1\n"
       "  EndIf",
       "  ; STEP 3, removed by a mutation")]),

    ("the directory is updated BEFORE the data instead of after",
     [("  idx = fat_pos / fat_clusterBytes\n"
       "  cl  = fat_ChainAt(idx, 1)\n"
       "  If cl = 0\n"
       "    ProcedureReturn -1\n"
       "  EndIf",
       "  idx = fat_pos / fat_clusterBytes\n"
       "  cl  = fat_ChainAt(idx, 1)\n"
       "  If cl = 0\n"
       "    ProcedureReturn -1\n"
       "  EndIf\n"
       "  If (fat_pos + len) > fat_fileSize\n"
       "    fat_fileSize = fat_pos + len\n"
       "  EndIf\n"
       "  If fat_UpdateDirEntry(fat_fileSize, fat_firstClus) = 0\n"
       "    ProcedureReturn -1\n"
       "  EndIf")]),

    # "a cluster is written to before it is claimed in the FAT" lived here
    # until 2026-09-17. FAT entries now wait in a buffer and a sector goes out
    # whole (fat_FlushFat), so claim-then-link and link-then-claim differ on
    # the medium only when the two entries are in DIFFERENT FAT sectors - which
    # this 128-cluster volume never does. The mutant moved to
    # tools/fileops_check.py, and stays GREEN there too - see the note at
    # "fat-link-before-claim" in that file for why.
    ("the second FAT is not mirrored",
     [("  If fat_mirrorFats = 1\n"
       "    i = 0\n"
       "    While i < fat_numFats\n"
       "      lba = fat_fatBase + (i * fat_fatSecs) + secOff",
       "  If fat_mirrorFats = 1\n"
       "    i = 0\n"
       "    While i < 1\n"
       "      lba = fat_fatBase + (i * fat_fatSecs) + secOff")]),

    # A true MOVE, not a deletion: the finished image is identical and
    # only the order changes, so nothing but the trace can see it.
    ("truncation frees the tail BEFORE the directory stops pointing at it",
     [("    If fat_UpdateDirEntry(newLen, fat_firstClus) = 0\n"
       "      ProcedureReturn 0\n"
       "    EndIf\n"
       "    fat_fileSize = newLen",
       "    fat_fileSize = newLen"),
      ("  If fat_FreeChain(tail) = 0\n"
       "    ProcedureReturn 0\n"
       "  EndIf\n"
       "  If fat_WriteFsInfo() = 0",
       "  If fat_FreeChain(tail) = 0\n"
       "    ProcedureReturn 0\n"
       "  EndIf\n"
       "  If fat_UpdateDirEntry(fat_fileSize, fat_firstClus) = 0\n"
       "    ProcedureReturn 0\n"
       "  EndIf\n"
       "  If fat_WriteFsInfo() = 0")]),

    ("a deleted file's clusters are not returned to the free pool",
     [("  ; 2. THE CHAIN.\n"
       "  If first <> 0\n"
       "    If fat_FreeChain(first) = 0\n"
       "      ProcedureReturn 0\n"
       "    EndIf\n"
       "  EndIf",
       "  ; 2. THE CHAIN - removed by a mutation")]),

    ("FSInfo is never written back",
     [("    ProcedureReturn 0\n"
       "  EndIf\n"
       "  If fat_fsinfoOk = 0\n"
       "    ProcedureReturn 1",
       "    ProcedureReturn 0\n"
       "  EndIf\n"
       "  If fat_fsinfoOk = 0 Or 1 = 1\n"
       "    ProcedureReturn 1")]),

    # THE FAT WRITE-BACK (2026-09-17) is gated by tools/fileops_check.py
    # ("fat-writeback-lost", "fat-dir-before-fat"): losing a changed sector or
    # letting a directory entry overtake it only shows once allocations cross
    # a FAT sector, and this volume's never do.
    ("a sector run is not stopped where the chain is not contiguous",
     [("    If nxt <> last + 1 Or fat_ClusterValid(nxt) = 0\n"
       "      Break",
       "    If fat_ClusterValid(nxt) = 0\n"
       "      Break")]),

    ("the free count is never rebuilt when FSInfo does not have one",
     [("  ProcedureReturn fat_ScanFree()\n"
       "EndProcedure",
       "  ProcedureReturn 1\n"
       "EndProcedure")]),

    ("the reserved top four bits of a FAT entry are zeroed on write",
     [("  nv  = (old & #FAT_CLUS_RSVD) | (val & #FAT_ENTRY_MASK)",
       "  nv  = (val & #FAT_ENTRY_MASK)")]),

    ("a new directory cluster is linked in WITHOUT being zeroed",
     [("    If fat_ZeroCluster(newc) = 0\n"
       "      ProcedureReturn 0\n"
       "    EndIf\n"
       "    If fat_SetEntry(last, newc) = 0",
       "    ; the zeroing, removed by a mutation\n"
       "    If fat_SetEntry(last, newc) = 0")]),

    ("cluster arithmetic loses the data-region offset, fence INTACT",
     [("Procedure.i fat_ClusterLba(cl.i)\n"
       "  ProcedureReturn (fat_dataLba + ((cl - 2) * fat_secPerClus))",
       "Procedure.i fat_ClusterLba(cl.i)\n"
       "  ProcedureReturn (((cl - 2) * fat_secPerClus))")]),

    ("the same arithmetic broken AND the LBA fence removed",
     [("Procedure.i fat_ClusterLba(cl.i)\n"
       "  ProcedureReturn (fat_dataLba + ((cl - 2) * fat_secPerClus))",
       "Procedure.i fat_ClusterLba(cl.i)\n"
       "  ProcedureReturn (((cl - 2) * fat_secPerClus))"),
      ("  If fat_LbaWritable(lba) = 0\n"
       "    fat_lastLba = lba\n"
       "    ProcedureReturn fat_Fail(#FAT_ERR_LBA_RANGE)\n"
       "  EndIf",
       "  ; the fence, removed by a mutation")]),
]


def mutate_run(name: str, edits: list) -> bool:
    """True when the gate went RED, which is what a mutation must do.

    Every mutant is a COPY in a temporary directory: fat32.pbi is copied
    and edited, the RaspberryPi4/Lib/fat.pi4 compatibility include is copied
    to name the mutant, and the self-test program is copied to name that
    wrapper.  Nothing in the tree is opened for writing.  An empty `edits`
    list is the control: the unmutated copy must go GREEN through exactly
    the same substitution path.
    """
    src = LIB.read_text(encoding="utf-8")
    for old, new in edits:
        if src.count(old) != 1:
            print("    ANCHOR BROKEN - the anchor text appears %d times in "
                  "fat32.pbi; repair the anchor, do not delete the mutation"
                  % src.count(old))
            return False
        src = src.replace(old, new)
    with tempfile.TemporaryDirectory(prefix="fatcheck-mut-") as td:
        work = pathlib.Path(td)
        mut_lib = work / "fat32_mut.pbi"
        mut_lib.write_text(src, encoding="utf-8")

        inc = 'XIncludeFile "Anvil/Storage/fat32.pbi"'
        wrapper = WRAPPER.read_text(encoding="utf-8")
        if wrapper.count(inc) != 1:
            raise SystemExit("RaspberryPi4/Lib/fat.pi4 no longer includes "
                             "Anvil/Storage/fat32.pbi exactly once, so the "
                             "mutation harness cannot substitute a mutant.")
        mut_wrapper = work / "fat_mut.pi4"
        mut_wrapper.write_text(
            wrapper.replace(inc, 'XIncludeFile "%s"' % mut_lib.as_posix()),
            encoding="utf-8")

        pinc = 'XIncludeFile "RaspberryPi4/Lib/fat.pi4"'
        prog = SRC.read_text(encoding="utf-8")
        if prog.count(pinc) != 1:
            raise SystemExit("pi4FatSelfTest.pi4 no longer includes "
                             "RaspberryPi4/Lib/fat.pi4 exactly once, so the "
                             "mutation harness cannot substitute a mutant.")
        mut_prog = work / "fatselftest_mut.pi4"
        mut_prog.write_text(
            prog.replace(pinc, 'XIncludeFile "%s"' % mut_wrapper.as_posix()),
            encoding="utf-8")

        img = work / "fatcheck_mut.img"
        try:
            sym = build_image(mut_prog, img)
            r = execute(sym, img)
        except SystemExit as e:
            # A build refusal or a program that never finished both count
            # as red: the gate noticed.
            print("    (it did not even run: %s)" % str(e).splitlines()[0][:88])
            return True
    fails: list = []
    check_reported(r, fails)
    check_structure(r, fails)
    check_bytes(r, fails)
    return bool(fails)


# =====================================================================
def main(argv: list[str] | None = None) -> int:
    global COMPILER
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"),
                    help="PureMetalForge.exe (default: $PMF_COMPILER)")
    ap.add_argument("--mutate", action="store_true",
                    help="prove the gate can fail, by breaking the library")
    args = ap.parse_args(argv); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    if not args.compiler:
        ap.error("No compiler was named. Pass --compiler with the path to "
                 "PureMetalForge.exe, or set PMF_COMPILER.")
    COMPILER = args.compiler

    with tempfile.TemporaryDirectory(prefix="fatcheck-") as td:
        img = pathlib.Path(td) / "fatselftest.img"
        sym = build_image(SRC, img)
        r = execute(sym, img)

    fails: list = []
    total = check_reported(r, fails)
    total += check_structure(r, fails)
    total += check_bytes(r, fails)

    writes = len([v for v in r.log if v >= 0])
    if fails:
        for f in fails:
            print("FAIL " + f)
        print("FAILED: %d of %d assertions, %d steps"
              % (len(fails), total, r.steps))
        return 1
    print("PASS: fat32.pbi read AND WROTE a fabricated FAT32 volume - "
          "%d assertions, %d interpreter steps, %d sector writes, none of "
          "them outside the FAT and data regions" % (total, r.steps, writes))

    if args.mutate:
        print()
        print("--mutate: breaking the library on purpose; each must go RED")
        # THE CONTROL RUNS FIRST.  Without it, a substitution path that does
        # not build would make every mutation read "RED" while nothing was
        # being tested.
        if mutate_run("control", []):
            print("  CONTROL FAILED - the unmutated copy does not pass through "
                  "the mutation path, so no RED below would mean anything.")
            return 1
        print("  control: the unmutated copy passes")
        bad = 0
        for name, edits in MUTATIONS:
            print("  * %s" % name)
            if mutate_run(name, edits):
                print("    RED, as required")
            else:
                print("    *** STILL GREEN - the gate does not catch this ***")
                bad += 1
        if bad:
            return 1
        print("  all %d mutations caught" % len(MUTATIONS))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

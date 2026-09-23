#!/usr/bin/env python3
"""File-operation correctness gate for Anvil's FAT32 and exFAT drivers.

    python tools/fileops_check.py --compiler <PureMetalForge.exe> [--fs fat32|exfat|both]
                                  [--mutate [NAME ...]] [--jobs N]
                                  [--export DIR] [--fsck-host user@host]

WHAT RUNS. A small disk is formatted here by an independent implementation
(tools/fs_reference.py): an MBR, partition 1 FAT32 (65,920 clusters of 512
bytes) and partition 2 exFAT (4,089 clusters of 4,096 bytes), with fixtures a
PC would have left - a long-named file, a file whose ValidDataLength is short
of its size, and a filler file that leaves the volume nearly full. A program
generated from the operation list below is compiled with the real compiler
and the REAL Anvil/Storage code, and run on the A64 model with the disk behind
a memory-mapped block device this harness serves. Every sector write is
logged.

WHAT IS CHECKED, and only the first is the program grading itself:
  1. every operation returns what it must - success, or the named refusal
  2. the finished medium, parsed by fs_reference.py and asking the drivers
     nothing: no errors and no leftovers, clean dirty flags, free counts that
     match the allocation, and a tree equal NAME FOR NAME AND BYTE FOR BYTE
     to the model this file keeps of what the operations should have done
  3. POWER CUTS: the logged writes are replayed onto the starting disk and
     the volume is checked after EVERY write. A cut may leave only what a
     repair tool reclaims without losing data (lost clusters, orphaned
     long-name entries or exFAT secondaries, a stale free count), and never
     while the volume says it is clean; the only damage tolerated is the
     documented window of each operation (see POWER-CUT ALLOWANCES)
  4. the backup boot regions and every other sector outside what a driver may
     change are byte-identical to the start
  5. with --export and --fsck-host, the FAT32 partition is checked by
     dosfstools' fsck.fat on a Linux host (read-only, -n)

--mutate rebuilds with one defect at a time in a temporary copy of the tree
and requires the gate to go RED for each. Rule 27 of this project allows this
kind of small-fixture desk gate; it is not a substitute for the board run.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "a64"))
import fs_reference as fr  # noqa: E402
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler

SEC = 512
LOAD = 0x400000
STACK = 0x3000000
MMIO = 0x7F000000
RET = 0x7FFF0000
FAT_LBA, FAT_SECS = 2048, 67000
EX_LBA, EX_SECS = 2048 + 67000, 32768
DISK_SECS = EX_LBA + EX_SECS
FAT_FREE_LEFT = 400
EX_FREE_LEFT = 200

# ----------------------------------------------------------------------
#  the data pattern: folds the sector index in, so bytes that land one
#  sector or one cluster off can never compare equal by accident
# ----------------------------------------------------------------------


def pattern(n: int, seed: int) -> bytes:
    return bytes((((i >> 9) * 91) + i * 37 + seed * 13 + 7) & 0xFF for i in range(n))


# ======================================================================
#  THE DISK
# ======================================================================
def build_disk() -> bytearray:
    img = bytearray(DISK_SECS * SEC)
    fr.mbr(img, [(0x0C, FAT_LBA, FAT_SECS), (0x07, EX_LBA, EX_SECS)])
    f = fr.format_fat32(img, FAT_LBA, FAT_SECS)
    # A PC's long-named file: LFN run + short alias (forum 894's shape).
    lfn_data = pattern(700, 8)
    f.alloc_contiguous(3, 2)
    img[f.clus_off(3):f.clus_off(3) + 700] = lfn_data
    f.add_root_entry(b"B84DET~1IMG", 0x20, 3, 700, long="B84DETAIL long name.img")
    # Filler: everything but FAT_FREE_LEFT clusters, contiguous from 16.
    n = f.count - 3 - FAT_FREE_LEFT
    f.alloc_contiguous(16, n)
    f.add_root_entry(b"FILLER  BIN", 0x20, 16, n * f.cbytes)
    f.set_fsinfo(f.free_count(), 5)
    # Free space holds what deleted files left, never zeros: a folder
    # cluster linked in without being zeroed must show up as garbage entries.
    for cl in list(range(5, 16)) + list(range(16 + n, f.count + 2)):
        o = f.clus_off(cl)
        img[o:o + f.cbytes] = bytes((0x41 + (i % 23)) for i in range(f.cbytes))
    e = fr.format_exfat(img, EX_LBA, EX_SECS)
    vdl = pattern(1000, 9) + b"\xAA" * 2096
    e.add_root_file("vdl.bin", vdl, first=e.root + 1, valid=1000, datalen=3000)
    first = e.root + 2
    n = e.count + 2 - first - EX_FREE_LEFT
    e.add_root_file("filler.bin", b"", first=first, datalen=n * e.cbytes)
    for cl in range(first + n, e.count + 2):
        o = e.clus_off(cl)
        img[o:o + e.cbytes] = bytes((0x41 + (i % 23)) for i in range(e.cbytes))
    # A STALE PercentInUse, as a driver that ignores the field leaves it: the
    # finished medium must carry the true value or FFh (forum 904).
    img[EX_LBA * SEC + 112] = 50
    e.fix_boot_checksums()
    return img


# ======================================================================
#  THE OPERATIONS, AND THE MODEL OF WHAT THEY DO
# ======================================================================
TS_DATE = (46 << 9) | (9 << 5) | 17          # 2026-09-17
TS_TIME = (14 << 11) | (5 << 5) | 18         # 14:05:36
TS_HUND = 137                                 # the odd second + 0.37 s
TS_OFFSET = -18000                            # CDT, UTC-5


def sequence(fs: str) -> list:
    P = "" if fs == "fat32" else "2:/"
    CB = 512 if fs == "fat32" else 4096
    ex = fs == "exfat"
    E = (lambda fat, exf: ("EXFAT", exf) if ex else ("FAT", fat))
    ops = [
        ("ts", TS_DATE, TS_TIME, TS_HUND, TS_OFFSET, 1),
        ("create_write", P + "a.txt", 100, 1),
        ("create_write", P + "exact.bin", CB, 2),
        ("append", P + "exact.bin", CB, 3),
        ("create_write", P + "zero.bin", 0, 0),
        ("read", P + "zero.bin", [(0, 0)]),
        ("overwrite", P + "a.txt", 3 * CB + 17, 4),
        ("read", P + "a.txt", [(3 * CB + 17, 4)]),
        ("read", P + "exact.bin", [(CB, 2), (CB, 3)]),
        ("truncate", P + "exact.bin", CB + 1),
        ("truncate", P + "exact.bin", CB),
        ("read", P + "exact.bin", [(CB, 2)]),
        # A FRAGMENTED FILE, read in one call: frag.bin's chain jumps over
        # gap.bin, so a sector run must stop where the chain does.
        ("create_write", P + "frag.bin", CB, 13),
        ("create_write", P + "gap.bin", CB, 14),
        ("append", P + "frag.bin", 2 * CB, 15),
        ("read", P + "frag.bin", [(CB, 13), (2 * CB, 15)]),
        ("hcheck", "dirty_now"),
        ("flush",),
        ("hcheck", "clean_now"),
        ("mkdir", P + "Dir One"),
        ("mkdir", P + "Dir One/Sub"),
        ("create_write", P + "Dir One/Sub/Résumé – final version.txt", 700, 5),
        ("read", P + "dir one/SUB/RÉSUMÉ – FINAL VERSION.TXT", [(700, 5)]),
        ("create_write", P + "Long File Name One.txt", 10, 6),
        ("create_write", P + "Long File Name Two.txt", 20, 7),
    ]
    if ex:
        ops.append(("fail_open", P + "LONGFI~2.TXT", E(28, "#EXFAT_E_NOT_FOUND")))
    else:
        ops.append(("read", P + "LONGFI~2.TXT", [(20, 7)]))
    ops += [
        ("fail_create", P + "LONG FILE NAME ONE.TXT", E("#FAT_ERR_EXISTS", "#EXFAT_E_EXISTS")),
        ("mkdir", P + "Dir One/many"),
    ]
    for k in range(50):
        ops.append(("create_write", P + "Dir One/many/item %02d growth test file.bin" % k, k, 20 + k))
    ops += [
        ("list", P + "Dir One/many", 50),
        ("rename", P + "a.txt", P + "A renamed file.txt"),
        ("rename", P + "zero.bin", P + "ZERO.BIN"),
        ("rename", P + "exact.bin", P + "Dir One/Sub/moved exact.bin"),
        ("rename", P + "Dir One/Sub", P + "Sub moved"),
        ("fail_rename", P + "Sub moved", P + "Sub moved/inner", E("#FAT_ERR_INTO_SELF", "#EXFAT_E_PATH")),
        ("read", P + "Sub moved/moved exact.bin", [(CB, 2)]),
        ("read", P + "sub moved/résumé – final version.txt", [(700, 5)]),
        ("rm", P + "Long File Name One.txt"),
        ("fail_rmdir", P + "Dir One", E("#FAT_ERR_NOT_EMPTY", "#EXFAT_E_NOT_EMPTY")),
        ("fail_rmdir", P + "Sub moved/moved exact.bin", E("#FAT_ERR_NOT_DIR", "#EXFAT_E_NOT_DIR")),
    ]
    for k in range(50):
        if k not in (7, 42):
            ops.append(("rm", P + "Dir One/many/item %02d growth test file.bin" % k))
    ops += [
        ("rm", P + "Dir One/many/ITEM 07 GROWTH TEST FILE.BIN"),
        ("rm", P + "Dir One/many/item 42 growth test file.bin"),
        ("rmdir", P + "Dir One/many"),
        ("list", P + "Dir One", 0),
        ("fail_mkdir", P + "..", E("#FAT_ERR_RESERVED_NAME", "#EXFAT_E_RESERVED_NAME")),
        ("fail_mkdir", P + "Dir One/.", E("#FAT_ERR_RESERVED_NAME", "#EXFAT_E_RESERVED_NAME")),
        ("fail_create", P + "bad:name.txt", E("#FAT_ERR_NAME", "#EXFAT_E_PATH")),
    ]
    if ex:
        ops += [
            ("read", P + "vdl.bin", [(1000, 9), (2000, None)]),
            ("pwrite", P + "vdl.bin", 2000, 100, 10),
            ("read", P + "vdl.bin", [(1000, 9), (1000, None), (100, 10), (900, None)]),
            ("fail_write_huge", P + "A renamed file.txt", "#EXFAT_E_NO_SPACE"),
        ]
    else:
        ops += [
            ("rm", P + "b84detail LONG name.img"),
            ("fail_write_huge", P + "A renamed file.txt", "#FAT_ERR_FILE_4G"),
        ]
    free_left = EX_FREE_LEFT if ex else FAT_FREE_LEFT
    ops += [
        ("read", P + "A renamed file.txt", [(3 * CB + 17, 4)]),
        ("fail_full", P + "big.bin", (free_left + 10) * CB, E("#FAT_ERR_NO_SPACE", "#EXFAT_E_NO_SPACE")),
        ("read", P + "big.bin", [(0, 0)]),
        ("rm", P + "big.bin"),
        # A FOLDER ON RECYCLED CLUSTERS. The full volume wrapped the
        # allocator, so the next claims land on freed clusters that still hold
        # file data: a folder there must be zeroed or it lists garbage.
        ("mkdir", P + "After full"),
        ("create_write", P + "After full/inner.txt", 30, 16),
        ("list", P + "After full", 1),
        ("read", P + "After full/inner.txt", [(30, 16)]),
        ("hcheck", "times"),
        ("ts", 0, 0, 0, 0, 0),
        ("create_write", P + "undated.txt", 5, 11),
        ("hcheck", "undated"),
        ("flush",),
        ("hcheck", "clean_now"),
    ]
    if ex:
        ops += [
            ("action", "set_dirty"),
            ("remount",),
            ("fail_overwrite_dirty", P + "A renamed file.txt", 50, "#EXFAT_E_DIRTY"),
            ("action", "clear_dirty"),
            ("remount",),
        ]
    else:
        ops += [
            ("action", "set_dirty"),
            ("remount",),
            ("overwrite", P + "A renamed file.txt", 3 * CB + 17, 4),
            ("flush",),
            ("hcheck", "still_dirty"),
            ("action", "clear_dirty"),
            ("remount",),
        ]
    ops += [
        ("read", P + "Sub moved/moved exact.bin", [(CB, 2)]),
        ("read", P + "ZERO.BIN", [(0, 0)]),
        ("read", P + "Long File Name Two.txt", [(20, 7)]),
        ("flush",),
    ]
    return ops


class Model:
    """What the tree must hold. Keys fold case; values keep the stored name."""

    def __init__(self, fs: str, disk: bytearray):
        self.fs = fs
        ref = fr.check_fat32(disk, FAT_LBA) if fs == "fat32" else fr.check_exfat(disk, EX_LBA)
        self.items = {}
        for path, ent in ref.tree.items():
            self.items[fr.fold(path)] = [path, ent.is_dir, ent.data]

    @staticmethod
    def norm(path: str) -> str:
        if len(path) > 1 and path[1] == ":":
            path = path[2:]
        return "/" + path.strip("/")

    def stored_name(self, path: str) -> str:
        return self.norm(path)

    def get(self, path: str):
        return self.items[fr.fold(self.norm(path))]

    def apply(self, op) -> None:
        k = op[0]
        if k == "create_write":
            self.items[fr.fold(self.norm(op[1]))] = [self.norm(op[1]), False, pattern(op[2], op[3])]
        elif k == "fail_full":
            # the create succeeds; the write that would overfill is refused
            self.items[fr.fold(self.norm(op[1]))] = [self.norm(op[1]), False, b""]
        elif k == "append":
            self.get(op[1])[2] += pattern(op[2], op[3])
        elif k == "overwrite":
            self.get(op[1])[2] = pattern(op[2], op[3])
        elif k == "truncate":
            it = self.get(op[1])
            it[2] = it[2][:op[2]]
        elif k == "pwrite":
            it = self.get(op[1])
            d = bytearray(it[2])
            d[op[2]:op[2] + op[3]] = pattern(op[3], op[4])
            it[2] = bytes(d)
        elif k == "mkdir":
            self.items[fr.fold(self.norm(op[1]))] = [self.norm(op[1]), True, None]
        elif k in ("rm", "rmdir"):
            del self.items[fr.fold(self.norm(op[1]))]
        elif k == "rename":
            old = self.norm(op[1])
            new = self.norm(op[2])
            moved = {}
            for key in list(self.items):
                path = self.items[key][0]
                if fr.fold(path) == fr.fold(old) or fr.fold(path).startswith(fr.fold(old) + "/"):
                    item = self.items.pop(key)
                    item[0] = new + path[len(old):]
                    moved[fr.fold(item[0])] = item
            self.items.update(moved)

    def fat_display(self, path: str) -> str:
        return path


# ======================================================================
#  THE PROGRAM
# ======================================================================
def utf8_data(label: str, text: str) -> str:
    raw = text.encode("utf-8") + b"\x00"
    return "  %s: Data.a %s" % (label, ",".join(str(b) for b in raw))


def generate(fs: str) -> str:
    ops = sequence(fs)
    strings = {}

    def S(text: str) -> str:
        if text not in strings:
            strings[text] = "str%d" % len(strings)
        return "?" + strings[text]

    body = []
    n = 0

    def step(code: str) -> None:
        nonlocal n
        n += 1
        body.append("  Mark(%d)" % n)
        for line in code.strip("\n").split("\n"):
            body.append("  " + line.replace("@@", str(n)))

    for op in ops:
        k = op[0]
        if k == "ts":
            step("FsSetTimestamp(%d, %d, %d, %d, %d)" % op[1:])
        elif k == "create_write":
            step("If FsCreate(%s) = 0 : ProcedureReturn Fail(@@) : EndIf\n"
                 "Fill(%d, %d)\n"
                 "If FsWrite(@gBuf[0], %d) <> %d : ProcedureReturn Fail(@@) : EndIf\n"
                 "FsClose()" % (S(op[1]), op[2], op[3], op[2], op[2]))
        elif k == "append":
            step("If FsOpen(%s) = 0 Or FsSeek(FsSize()) = 0 : ProcedureReturn Fail(@@) : EndIf\n"
                 "Fill(%d, %d)\n"
                 "If FsWrite(@gBuf[0], %d) <> %d : ProcedureReturn Fail(@@) : EndIf\n"
                 "FsClose()" % (S(op[1]), op[2], op[3], op[2], op[2]))
        elif k == "overwrite":
            step("If FsOpen(%s) = 0 : ProcedureReturn Fail(@@) : EndIf\n"
                 "Fill(%d, %d)\n"
                 "If FsOverwrite(@gBuf[0], %d) = 0 : ProcedureReturn Fail(@@) : EndIf\n"
                 "FsClose()" % (S(op[1]), op[2], op[3], op[2]))
        elif k == "pwrite":
            step("If FsOpen(%s) = 0 Or FsSeek(%d) = 0 : ProcedureReturn Fail(@@) : EndIf\n"
                 "Fill(%d, %d)\n"
                 "If FsWrite(@gBuf[0], %d) <> %d : ProcedureReturn Fail(@@) : EndIf\n"
                 "FsClose()" % (S(op[1]), op[2], op[3], op[4], op[3], op[3]))
        elif k == "truncate":
            step("If FsOpen(%s) = 0 Or FsTruncate(%d) = 0 Or FsSize() <> %d : ProcedureReturn Fail(@@) : EndIf\n"
                 "FsClose()" % (S(op[1]), op[2], op[2]))
        elif k == "read":
            total = sum(s[0] for s in op[2])
            lines = ["If FsOpen(%s) = 0 Or FsSize() <> %d : ProcedureReturn Fail(@@) : EndIf" % (S(op[1]), total),
                     "If FsRead(@gBuf[0], %d) <> %d : ProcedureReturn Fail(@@) : EndIf" % (total + 9, total)]
            at = 0
            for size, seed in op[2]:
                if seed is None:
                    lines.append("If Zeros(%d, %d) = 0 : ProcedureReturn Fail(@@) : EndIf" % (size, at))
                else:
                    lines.append("If Verify(%d, %d, %d) = 0 : ProcedureReturn Fail(@@) : EndIf" % (size, seed, at))
                at += size
            lines.append("FsClose()")
            step("\n".join(lines))
        elif k == "mkdir":
            step("If FsMkdir(%s) = 0 : ProcedureReturn Fail(@@) : EndIf" % S(op[1]))
        elif k == "rm":
            step("If FsRemove(%s) = 0 : ProcedureReturn Fail(@@) : EndIf" % S(op[1]))
        elif k == "rmdir":
            step("If FsRmdir(%s) = 0 : ProcedureReturn Fail(@@) : EndIf" % S(op[1]))
        elif k == "rename":
            step("If FsRename(%s, %s) = 0 : ProcedureReturn Fail(@@) : EndIf" % (S(op[1]), S(op[2])))
        elif k == "list":
            step("If FsDirOpen(%s) = 0 : ProcedureReturn Fail(@@) : EndIf\n"
                 "seen = 0\n"
                 "r = FsDirNext()\n"
                 "While r > 0\n"
                 "  If FsDirNameUtf8(@gName[0], 1024) <= 0 : ProcedureReturn Fail(@@) : EndIf\n"
                 "  seen = seen + 1\n"
                 "  r = FsDirNext()\n"
                 "Wend\n"
                 "If r < 0 Or seen <> %d : ProcedureReturn Fail(@@) : EndIf" % (S(op[1]), op[2]))
        elif k.startswith("fail_"):
            code = op[-1][1] if isinstance(op[-1], tuple) else op[-1]
            if k == "fail_open":
                call = "FsOpen(%s) <> 0" % S(op[1])
            elif k == "fail_create":
                call = "FsCreate(%s) <> 0" % S(op[1])
            elif k == "fail_mkdir":
                call = "FsMkdir(%s) <> 0" % S(op[1])
            elif k == "fail_rmdir":
                call = "FsRmdir(%s) <> 0" % S(op[1])
            elif k == "fail_rename":
                call = "FsRename(%s, %s) <> 0" % (S(op[1]), S(op[2]))
            elif k == "fail_write_huge":
                step("If FsOpen(%s) = 0 : ProcedureReturn Fail(@@) : EndIf\n"
                     "sizeBefore = FsSize()\n"
                     "If FsWrite(@gBuf[0], $100000000) > 0 Or FsLastError() <> %s : ProcedureReturn Fail(@@) : EndIf\n"
                     "FsClose()\n"
                     "If FsOpen(%s) = 0 Or FsSize() <> sizeBefore : ProcedureReturn Fail(@@) : EndIf\n"
                     "FsClose()" % (S(op[1]), code, S(op[1])))
                continue
            elif k == "fail_full":
                step("If FsCreate(%s) = 0 : ProcedureReturn Fail(@@) : EndIf\n"
                     "Fill(%d, 12)\n"
                     "If FsWrite(@gBuf[0], %d) > 0 Or FsLastError() <> %s : ProcedureReturn Fail(@@) : EndIf\n"
                     "FsClose()" % (S(op[1]), op[2], op[2], code))
                continue
            elif k == "fail_overwrite_dirty":
                step("If FsOpen(%s) = 0 : ProcedureReturn Fail(@@) : EndIf\n"
                     "writes = PeekI(%d)\n"
                     "Fill(%d, 13)\n"
                     "If FsWrite(@gBuf[0], %d) > 0 Or FsLastError() <> %s Or PeekI(%d) <> writes : ProcedureReturn Fail(@@) : EndIf\n"
                     "FsClose()" % (S(op[1]), MMIO + 40, op[2], op[2], code, MMIO + 40))
                continue
            else:
                raise SystemExit("unknown op " + k)
            step("If %s Or FsLastError() <> %s : ProcedureReturn Fail(@@) : EndIf" % (call, code))
        elif k == "flush":
            step("If FsFlush() = 0 : ProcedureReturn Fail(@@) : EndIf")
        elif k == "hcheck":
            step("If Host(6, %d) = 0 : ProcedureReturn Fail(@@) : EndIf" % HCHECKS.index(op[1]))
        elif k == "action":
            step("Host(5, %d)" % ACTIONS.index(op[1]))
        elif k == "remount":
            other = 2 if fs == "fat32" else 1
            mine = 1 if fs == "fat32" else 2
            # the other partition may not mount (it is fine either way):
            # selecting it unmounts ours, which is the point
            step("FsSelectPartition(%d)\nIf FsSelectPartition(%d) = 0 : ProcedureReturn Fail(@@) : EndIf" % (other, mine))
        else:
            raise SystemExit("unknown op " + k)

    out = ['; GENERATED by tools/fileops_check.py - do not edit; the operation list is there.',
           'XIncludeFile "RaspberryPi4/Lib/fat.pi4"',
           "",
           "#MMIO = $%X" % MMIO,
           "Global Dim gBuf.a[1048576]",
           "Global Dim gName.a[1024]",
           "",
           "Procedure.i Host(command.i, value.i)",
           "  PokeI(#MMIO + 24, value)",
           "  PokeI(#MMIO + 16, command)",
           "  ProcedureReturn PeekI(#MMIO + 32)",
           "EndProcedure",
           "",
           "; The block-range seam: count blocks per call (register 48).",
           "Procedure.i DiskRead(lba.i, count.i, *buf)",
           "  PokeI(#MMIO, lba)",
           "  PokeI(#MMIO + 8, *buf)",
           "  PokeI(#MMIO + 48, count)",
           "  PokeI(#MMIO + 16, 1)",
           "  ProcedureReturn PeekI(#MMIO + 32)",
           "EndProcedure",
           "",
           "Procedure.i DiskWrite(lba.i, count.i, *buf)",
           "  PokeI(#MMIO, lba)",
           "  PokeI(#MMIO + 8, *buf)",
           "  PokeI(#MMIO + 48, count)",
           "  PokeI(#MMIO + 16, 2)",
           "  ProcedureReturn PeekI(#MMIO + 32)",
           "EndProcedure",
           "",
           "Procedure.i DiskFlush()",
           "  PokeI(#MMIO + 16, 3)",
           "  ProcedureReturn PeekI(#MMIO + 32)",
           "EndProcedure",
           "",
           "Procedure Mark(n.i)",
           "  Host(4, n)",
           "EndProcedure",
           "",
           "Procedure.i Fail(n.i)",
           "  Host(7, FsErrorKind() * 1000 + FsLastError())",
           "  ProcedureReturn n",
           "EndProcedure",
           "",
           "Procedure Fill(n.i, seed.i)",
           "  Define i.i",
           "  i = 0",
           "  While i < n",
           "    gBuf[i] = (((i >> 9) * 91) + (i * 37) + (seed * 13) + 7) & 255",
           "    i = i + 1",
           "  Wend",
           "EndProcedure",
           "",
           "Procedure.i Verify(n.i, seed.i, at.i)",
           "  Define i.i",
           "  i = 0",
           "  While i < n",
           "    If gBuf[at + i] <> ((((i >> 9) * 91) + (i * 37) + (seed * 13) + 7) & 255)",
           "      ProcedureReturn 0",
           "    EndIf",
           "    i = i + 1",
           "  Wend",
           "  ProcedureReturn 1",
           "EndProcedure",
           "",
           "Procedure.i Zeros(n.i, at.i)",
           "  Define i.i",
           "  i = 0",
           "  While i < n",
           "    If gBuf[at + i] <> 0",
           "      ProcedureReturn 0",
           "    EndIf",
           "    i = i + 1",
           "  Wend",
           "  ProcedureReturn 1",
           "EndProcedure",
           "",
           "Procedure.i Main()",
           "  Define r.i",
           "  Define seen.i",
           "  Define writes.i",
           "  Define sizeBefore.i",
           "  FsSetRangeReader(@DiskRead)",
           "  FsSetRangeWriter(@DiskWrite)",
           "  FsSetBlockFlusher(@DiskFlush)",
           ]
    out += body
    out += ["  ProcedureReturn 0", "EndProcedure", "", "DataSection"]
    out += [utf8_data(label, text) for text, label in strings.items()]
    out += ["EndDataSection", ""]
    return "\r\n".join(out)


HCHECKS = ["dirty_now", "clean_now", "times", "undated", "still_dirty"]
ACTIONS = ["set_dirty", "clear_dirty"]


# ======================================================================
#  RUNNING IT
# ======================================================================
def build(compiler: Path, source_root: Path, program: str, work: Path) -> tuple:
    src = work / "fileops_gate.pi4"
    src.write_bytes(program.encode("utf-8"))
    staged = work / compiler.name
    shutil.copy2(compiler, staged)
    if not (work / "Boards").exists():
        shutil.copytree(source_root / "Boards", work / "Boards")
    image = work / "fileops_gate.img"
    env = os.environ.copy()
    env["PMF_ROOT"] = str(source_root)
    run = subprocess.run([str(staged), "--compile", str(src), "-t", "pi4", "--load-addr", hex(LOAD),
                          "--stack-addr", hex(STACK), "--entry-returns", "-o", str(image), "-s"],
                         cwd=source_root, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if run.returncode or not image.is_file() or "COMPILER ERROR" in run.stdout:
        raise RuntimeError("compile failed\n" + run.stdout[-4000:])
    syms = {}
    for line in (image.with_suffix(".img.sym")).read_text(encoding="utf-8-sig").splitlines():
        if "=" in line:
            a, b = line.split("=", 1)
            try:
                syms[a] = int(b, 0)
            except ValueError:
                pass
    return image, syms


class Run:
    def __init__(self, fs: str, disk: bytearray):
        self.fs = fs
        self.disk = disk
        self.base = bytes(disk)
        self.writes = []          # (lba, bytes, mark)
        self.marks = []
        self.mark = 0
        self.flushes = 0
        self.fail_detail = None
        self.host_failures = []
        self.reg = {0: 0, 8: 0, 24: 0, 32: 0}
        self.lba_range = (FAT_LBA, FAT_LBA + FAT_SECS) if fs == "fat32" else (EX_LBA, EX_LBA + EX_SECS)

    # the checks a program asks for at a point in its sequence
    def hcheck(self, which: str) -> bool:
        if self.fs == "fat32":
            fat1 = struct.unpack_from("<I", self.disk, (FAT_LBA + 32) * SEC + 4)[0]
            clean = bool(fat1 & fr.FAT_CLEAN)
            vol = fr.Fat32Image(self.disk, FAT_LBA)
        else:
            flags = struct.unpack_from("<H", self.disk, EX_LBA * SEC + 106)[0]
            clean = not flags & 2
        if which == "dirty_now":
            return not clean
        if which == "clean_now":
            return clean
        if which == "still_dirty":
            return not clean
        rep = fr.check_fat32(self.disk, FAT_LBA, read_data=False) if self.fs == "fat32" else \
            fr.check_exfat(self.disk, EX_LBA, read_data=False)
        if which == "times":
            ent = rep.tree.get("/Sub moved/Résumé – final version.txt")
            if ent is None:
                return False
            if self.fs == "fat32":
                return ent.times["crt"] == (TS_DATE, TS_TIME, TS_HUND) and ent.times["wrt"] == (TS_DATE, TS_TIME) \
                    and ent.times["acc"] == TS_DATE
            want = (TS_DATE << 16) | TS_TIME
            off = 0x80 | ((TS_OFFSET // 900) & 0x7F)
            return ent.times["crt"] == want and ent.times["mod"] == want and ent.times["crt10"] == TS_HUND \
                and ent.times["crtoff"] == off and ent.times["modoff"] == off
        if which == "undated":
            ent = rep.tree.get("/undated.txt")
            if ent is None:
                return False
            if self.fs == "fat32":
                return ent.times["crt"] == (0x21, 0, 0) and ent.times["wrt"] == (0x21, 0)
            return ent.times["crt"] == 0x21 << 16 and ent.times["crtoff"] == 0 and ent.times["modoff"] == 0
        return False

    def action(self, which: str) -> None:
        if self.fs == "fat32":
            for copy in (0, 1):
                fat_sz = struct.unpack_from("<I", self.disk, FAT_LBA * SEC + 36)[0]
                o = (FAT_LBA + 32 + copy * fat_sz) * SEC + 4
                v = struct.unpack_from("<I", self.disk, o)[0]
                v = (v & ~fr.FAT_CLEAN) if which == "set_dirty" else (v | fr.FAT_CLEAN)
                struct.pack_into("<I", self.disk, o, v)
        else:
            o = EX_LBA * SEC + 106
            v = struct.unpack_from("<H", self.disk, o)[0]
            v = (v | 2) if which == "set_dirty" else (v & ~2)
            struct.pack_into("<H", self.disk, o, v)
        self.writes.append((-1, which, self.mark))


def execute(a64mod, image: Path, syms: dict, run: Run, limit: int) -> tuple:
    blob = image.read_bytes()
    cpu = a64mod.A64()
    for i, b in enumerate(blob):
        cpu.memory[LOAD + i] = b
    a64mod.attach_symbols(cpu, image, LOAD)
    cpu.pc = LOAD
    cpu.sp = STACK
    cpu.x[30] = RET
    mem = cpu.memory
    disk = run.disk
    base_store = cpu.store
    base_load = cpu.load

    def load(addr, size):
        if MMIO <= addr < MMIO + 64:
            return run.reg.get(addr - MMIO, 0) if addr - MMIO != 40 else len(run.writes)
        return base_load(addr, size)

    watch = {}
    spec = os.environ.get("FILEOPS_WATCH")          # e.g. "exfat_error=25,fat_err=43"
    if spec:
        for part in spec.split(","):
            name, val = part.split("=")
            if "global_" + name in syms:
                watch[LOAD + syms["global_" + name] if syms["global_" + name] < LOAD else syms["global_" + name]] = (name, int(val))

    def store(addr, value, size):
        if addr in watch and value == watch[addr][1]:
            loc = cpu.locate(cpu.this_instr) if cpu.locate else hex(cpu.this_instr)
            back = cpu.locate(cpu.x[30]) if cpu.locate else hex(cpu.x[30])
            print("WATCH %s=%d at %s, called from %s (step %d)" % (watch[addr][0], value, loc, back, run.mark), flush=True)
        if not MMIO <= addr < MMIO + 64:
            return base_store(addr, value, size)
        off = addr - MMIO
        run.reg[off] = value
        if off != 16:
            return
        cmd = value
        lba = run.reg[0]
        buf = run.reg[8]
        count = run.reg.get(48, 0)
        if cmd == 1:
            # A RANGE of blocks. The reader must never be handed a count the
            # block-range contract does not allow.
            if count < 1 or not 0 <= lba or lba + count > DISK_SECS:
                if count < 1:
                    run.host_failures.append("read of %d blocks at sector %d" % (count, lba))
                run.reg[32] = 0
                return
            o = lba * SEC
            chunk = disk[o:o + count * SEC]
            for i in range(count * SEC):
                mem[buf + i] = chunk[i]
            run.reg[32] = 1
        elif cmd == 2:
            if count < 1 or not (run.lba_range[0] <= lba and lba + count <= run.lba_range[1]):
                run.host_failures.append("write of %d blocks at sector %d outside partition %s" % (count, lba, run.fs))
                run.reg[32] = 0
                return
            # EVERY BLOCK OF A RANGE IS LOGGED AS ITS OWN WRITE, in order, so
            # the power-cut replay can still cut between any two sectors - a
            # range write is not atomic on a real device either.
            for k in range(count):
                data = bytes(mem.get(buf + k * SEC + i, 0) for i in range(SEC))
                disk[(lba + k) * SEC:(lba + k + 1) * SEC] = data
                run.writes.append((lba + k, data, run.mark))
            run.reg[32] = 1
        elif cmd == 3:
            run.flushes += 1
            run.reg[32] = 1
        elif cmd == 4:
            run.mark = run.reg[24]
            run.marks.append((run.mark, len(run.writes)))
            run.reg[32] = 1
        elif cmd == 5:
            run.action(ACTIONS[run.reg[24]])
            run.reg[32] = 1
        elif cmd == 6:
            ok = run.hcheck(HCHECKS[run.reg[24]])
            if not ok:
                run.host_failures.append("host check %s failed at step %d" % (HCHECKS[run.reg[24]], run.mark))
            run.reg[32] = 1 if ok else 0
        elif cmd == 7:
            run.fail_detail = run.reg[24]
            run.reg[32] = 1

    cpu.load = load
    cpu.store = store
    for steps in range(limit):
        if cpu.pc == RET:
            return cpu.x[0], steps
        cpu.step()
    raise RuntimeError("no return within %d instructions (step %d)" % (limit, run.mark))


# ----------------------------------------------------------------------
#  POWER-CUT ALLOWANCES. The windows the drivers document, and nothing else.
# ----------------------------------------------------------------------
def op_kind(fs: str, mark: int) -> str:
    ops = sequence(fs)
    return ops[mark - 1][0] if 1 <= mark <= len(ops) else ""


def cut_allowed(fs: str, kind: str, errors: list) -> bool:
    for e in errors:
        if kind == "rename" and ("cross-linked" in e or "chain has 0" in e or "used twice" in e
                                 or "collides" in e or "'..' names cluster" in e):
            # FatRename / ExFatRename write the new entry first and remove the
            # old one after it: in between, two entries name the same object
            # (the chain, the short name when only the case changed, and a
            # moved folder's "..", which already names its new parent).
            continue
        if fs == "exfat" and "entry set checksum wrong" in e and kind in (
                "create_write", "append", "overwrite", "truncate", "pwrite", "fail_full", "mkdir", "rename"):
            continue      # a set whose file and stream entries straddle two sectors
        return False
    return True


def replay(run: Run, every: int = 1) -> list:
    problems = []
    img = bytearray(run.base)
    part = FAT_LBA if run.fs == "fat32" else EX_LBA
    checker = fr.check_fat32 if run.fs == "fat32" else fr.check_exfat
    for idx, (lba, data, mark) in enumerate(run.writes):
        if lba < 0:
            tmp = Run(run.fs, img)
            tmp.action(data)
            continue
        img[lba * SEC:(lba + 1) * SEC] = data
        if idx % every and idx != len(run.writes) - 1:
            continue
        rep = checker(img, part, read_data=False)
        kind = op_kind(run.fs, mark)
        benign = [b for b in rep.benign if not b.startswith("FSInfo") and not b.startswith("PercentInUse")]
        if rep.errors and not cut_allowed(run.fs, kind, rep.errors):
            problems.append("cut after write %d (step %d %s): %s" % (idx + 1, mark, kind, rep.errors[:3]))
        if (rep.errors or benign) and not rep.dirty:
            problems.append("cut after write %d (step %d %s): volume says CLEAN with %s"
                            % (idx + 1, mark, kind, (rep.errors + benign)[:3]))
        if len(problems) > 20:
            break
    return problems


def untouchable(fs: str) -> list:
    """Sector ranges no driver may write."""
    if fs == "fat32":
        v = fr.Fat32Image(bytearray(build_disk()), FAT_LBA)
        allowed = {FAT_LBA + v.fsinfo}
        return [(FAT_LBA + s) for s in range(0, v.rsvd) if FAT_LBA + s not in allowed]
    return [EX_LBA + s for s in range(1, 24)]


def final_checks(fs: str, run: Run, model: Model) -> list:
    fails = []
    part = FAT_LBA if fs == "fat32" else EX_LBA
    rep = fr.check_fat32(run.disk, part) if fs == "fat32" else fr.check_exfat(run.disk, part)
    fails += ["final medium: " + e for e in rep.errors]
    fails += ["final medium leftover: " + b for b in rep.benign]
    if rep.dirty:
        fails.append("final medium is marked dirty")
    got = {fr.fold(p): (p, e.is_dir, e.data) for p, e in rep.tree.items()}
    want = {k: tuple(v) for k, v in model.items.items()}
    for key in sorted(set(got) | set(want)):
        if key not in got:
            fails.append("missing on the medium: %s" % want[key][0])
        elif key not in want:
            fails.append("unexpected on the medium: %s" % got[key][0])
        else:
            g, w = got[key], want[key]
            if g[0] != w[0]:
                fails.append("name %r stored as %r" % (w[0], g[0]))
            if g[1] != w[1]:
                fails.append("%s: directory flag %s, expected %s" % (w[0], g[1], w[1]))
            if not w[1] and g[2] != w[2]:
                fails.append("%s: %d bytes on the medium differ from the %d expected"
                             % (w[0], len(g[2] or b""), len(w[2])))
    for lba in untouchable(fs):
        if run.base[lba * SEC:(lba + 1) * SEC] != run.disk[lba * SEC:(lba + 1) * SEC]:
            fails.append("sector %d (boot/backup region) was changed" % lba)
    written = {w[0] for w in run.writes if w[0] >= 0}
    if fs == "exfat" and any(EX_LBA + 12 <= lba < EX_LBA + 24 for lba in written):
        fails.append("the Backup Boot Region was written (forum 903)")
    if fs == "exfat" and rep.info.get("percent") not in (0xFF, rep.info["used"] * 100 // rep.info["count"]):
        fails.append("PercentInUse %s does not follow the allocation (forum 904)" % rep.info.get("percent"))
    if run.flushes == 0:
        fails.append("the device flusher was never called")
    return fails


def gate(fs: str, compiler: Path, source_root: Path, export: Path | None = None, cuts_every: int = 1) -> dict:
    import importlib.util
    spec = importlib.util.spec_from_file_location("anvil_fileops_a64", source_root / "tools" / "a64" / "a64_interp.py")
    a64mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = a64mod
    spec.loader.exec_module(a64mod)
    started = time.time()
    disk = build_disk()
    model = Model(fs, disk)
    for op in sequence(fs):
        model.apply(op)
    with tempfile.TemporaryDirectory(prefix="anvil-fileops-") as td:
        image, syms = build(compiler, source_root, generate(fs), Path(td))
        run = Run(fs, disk)
        result, steps = execute(a64mod, image, syms, run, 4_000_000_000)
    out = {"fs": fs, "steps": steps, "result": result, "writes": len(run.writes), "fails": []}
    if result != 0:
        detail = run.fail_detail
        ops = sequence(fs)
        out["fails"].append("program stopped at step %d (%s) - error kind %s code %s"
                            % (result, ops[result - 1] if result <= len(ops) else "?",
                               None if detail is None else detail // 1000,
                               None if detail is None else detail % 1000))
    out["fails"] += run.host_failures
    if result == 0:
        out["fails"] += final_checks(fs, run, model)
        cut_problems = replay(run, cuts_every)
        out["fails"] += cut_problems
        out["cuts"] = len([w for w in run.writes if w[0] >= 0])
    if export is not None:
        export.mkdir(parents=True, exist_ok=True)
        part, secs = (FAT_LBA, FAT_SECS) if fs == "fat32" else (EX_LBA, EX_SECS)
        (export / ("%s_final_partition.img" % fs)).write_bytes(bytes(run.disk[part * SEC:(part + secs) * SEC]))
        (export / ("%s_final_disk.img" % fs)).write_bytes(bytes(run.disk))
    out["seconds"] = round(time.time() - started, 1)
    return out


# ======================================================================
#  MUTANTS - each must turn the gate red
# ======================================================================
MUTANTS = {
    # forum 894: the long-name run is left behind by rm
    "fat-rm-leaves-lfn": ("Anvil/Storage/fat32.pbi", [
        ("  i = 0\n  While i < fat_oldRunN\n    lba = fat_oldRunLba[i]\n    If lba <> fat_oldLba",
         "  i = fat_oldRunN\n  While i < fat_oldRunN\n    lba = fat_oldRunLba[i]\n    If lba <> fat_oldLba"),
        ("    If fat_oldRunLba[i] = fat_oldLba\n      PokeA(@fat_secBuf[0] + fat_oldRunOff[i], #FAT_DIRENT_FREE)",
         "    If fat_oldRunLba[i] = -99\n      PokeA(@fat_secBuf[0] + fat_oldRunOff[i], #FAT_DIRENT_FREE)")], "fat32"),
    # short entry written before its long name
    "fat-short-before-lfn": ("Anvil/Storage/fat32.pbi", [
        ("  fat_setN = count + 1\nEndProcedure",
         "  If count > 0\n    fat_CopyBytes(@fat_tmp[0], @fat_set[0], #FAT_DIRENT_SIZE)\n    fat_CopyBytes(@fat_set[0], @fat_set[0] + count * #FAT_DIRENT_SIZE, #FAT_DIRENT_SIZE)\n    fat_CopyBytes(@fat_set[0] + count * #FAT_DIRENT_SIZE, @fat_tmp[0], #FAT_DIRENT_SIZE)\n  EndIf\n  fat_setN = count + 1\nEndProcedure")], "fat32"),
    # no numeric tail: every long name gets its bare basis
    "fat-no-tail": ("Anvil/Storage/fat32.pbi", [
        ("    t = fat_ShortTaken(dirClus, ignoreLba, ignoreOff)\n    If t < 0\n      ProcedureReturn 0\n    EndIf\n    If t = 0\n      ProcedureReturn 1\n    EndIf\n    If n = 1",
         "    t = 0\n    If t < 0\n      ProcedureReturn 0\n    EndIf\n    If t = 0\n      ProcedureReturn 1\n    EndIf\n    If n = 1")], "fat32"),
    # folder cluster linked before it is zeroed... and not zeroed at all
    "fat-dir-grow-unzeroed": ("Anvil/Storage/fat32.pbi", [
        ("    If fat_ZeroCluster(newc) = 0\n      ProcedureReturn 0\n    EndIf\n    If fat_SetEntry(last, newc) = 0",
         "    If fat_SetEntry(last, newc) = 0")], "fat32"),
    # a moved folder keeps its old ".."
    "fat-dotdot-stale": ("Anvil/Storage/fat32.pbi", [
        ("  If (attr & #FAT_ATTR_DIRECTORY) <> 0 And newParent <> oldParent\n    If fat_ReadSec",
         "  If (attr & #FAT_ATTR_DIRECTORY) <> 0 And newParent = -7\n    If fat_ReadSec")], "fat32"),
    # FAT[1] dirty bit never cleared (forum 901)
    "fat-no-dirty-bit": ("Anvil/Storage/fat32.pbi", [
        ("    fat_wasClean = 1\n    If fat_SetCleanBit(0) = 0",
         "    fat_wasClean = 0\n    If 0 <> 0")], "fat32"),
    # no rollback on a full volume (forum 900)
    "fat-no-rollback": ("Anvil/Storage/fat32.pbi", [
        ("    If fat_wTrack <> 0\n      fat_RollbackAlloc()", "    If fat_wTrack = -5\n      fat_RollbackAlloc()")], "fat32"),
    # the 4 GiB ceiling removed (forum 899)
    "fat-no-4g": ("Anvil/Storage/fat32.pbi", [
        ("  If fat_pos + len > #FAT_MAX_FILE_BYTES\n", "  If fat_pos + len > $7FFFFFFFFFFFFFFF\n")], "fat32"),
    # rmdir without the emptiness check
    "fat-rmdir-nonempty": ("Anvil/Storage/fat32.pbi", [
        ("    If empty = 0\n      ProcedureReturn fat_Fail(#FAT_ERR_NOT_EMPTY)", "    If empty = 9\n      ProcedureReturn fat_Fail(#FAT_ERR_NOT_EMPTY)")], "fat32"),
    # timestamps ignored (forum 911)
    "fs-no-timestamps": ("Anvil/Storage/filesystem.pbi", [
        ("  If valid = 0 Or FatSetTimestamp(date, time) = 0\r\n", "  If 1 = 1\r\n")], "both"),
    # exFAT: in-cluster write skips the dirty mark (forum 902)
    "ex-write-no-dirty": ("Anvil/Storage/exfat.pbi", [
        ("  If exfat_BeginMutation() = 0\r\n    ProcedureReturn -1\r\n  EndIf\r\n  oldLength = exfat_fileLength",
         "  oldLength = exfat_fileLength")], "exfat"),
    # exFAT: dirty mark into the backup region too (forum 903)
    "ex-backup-written": ("Anvil/Storage/exfat.pbi", [
        ("  If exfat_WriteSector(0, @exfat_sector[0]) = 0\r\n    ProcedureReturn 0\r\n  EndIf\r\n  exfat_volumeFlags = flags",
         "  If exfat_WriteSector(0, @exfat_sector[0]) = 0\r\n    ProcedureReturn 0\r\n  EndIf\r\n  exfat_ReadSector(12, @exfat_sector[0])\r\n  exfat_Put16(@exfat_sector[0], 106, flags)\r\n  exfat_WriteSector(12, @exfat_sector[0])\r\n  exfat_volumeFlags = flags")], "exfat"),
    # exFAT: PercentInUse left alone (forum 904)
    "ex-percent-stale": ("Anvil/Storage/exfat.pbi", [
        ("  If dirty = 0 And exfat_allocChanged <> 0\r\n", "  If dirty = 7\r\n")], "exfat"),
    # exFAT: . and .. accepted (forum 905)
    "ex-dotnames": ("Anvil/Storage/exfat.pbi", [
        ("  If PeekW(*out) = 46 And (n = 1 Or (n = 2 And PeekW(*out + 2) = 46))\r\n",
         "  If PeekW(*out) = 9999\r\n")], "exfat"),
    # exFAT: reads stop at ValidDataLength (forum 906)
    "ex-vdl-read": ("Anvil/Storage/exfat.pbi", [
        ("  If got < count\r\n    exfat_Zero(*dst + got, count - got)\r\n    got = count\r\n  EndIf\r\n",
         "")], "exfat"),
    # exFAT: no rollback on a full volume (forum 907)
    "ex-no-rollback": ("Anvil/Storage/exfat.pbi", [
        ("    exfat_ReleaseClaimed(newStart, claimed)\r\n    ProcedureReturn 0\r\n  EndIf\r\n  ProcedureReturn 1",
         "    ProcedureReturn 0\r\n  EndIf\r\n  ProcedureReturn 1")], "exfat"),
    # exFAT: remove clears the secondaries first (forum 908)
    "ex-remove-order": ("Anvil/Storage/exfat.pbi", [
        ("  e = 0\r\n  While e <= secondary\r\n    If exfat_DirRead(parentFirst, parentFlags, parentLength, setIndex + e, @exfat_aux[0]) = 0\r\n      ProcedureReturn 0\r\n    EndIf\r\n    PokeA(@exfat_aux[0], PeekA(@exfat_aux[0]) & $7F)",
         "  e = secondary\r\n  While e >= 0 And e <= secondary\r\n    If exfat_DirRead(parentFirst, parentFlags, parentLength, setIndex + e, @exfat_aux[0]) = 0\r\n      ProcedureReturn 0\r\n    EndIf\r\n    PokeA(@exfat_aux[0], PeekA(@exfat_aux[0]) & $7F)"),
        ("    e = e + 1\r\n  Wend\r\n  ProcedureReturn 1\r\nEndProcedure\r\n\r\nProcedure.i ExFatRemove",
         "    e = e - 1\r\n  Wend\r\n  ProcedureReturn 1\r\nEndProcedure\r\n\r\nProcedure.i ExFatRemove")], "exfat"),
    # exFAT: case-only rename refused (forum 910)
    "ex-case-rename": ("Anvil/Storage/exfat.pbi", [
        ("    If exfat_fileParent <> oldParent Or exfat_fileSetIndex <> oldIndex\r\n",
         "    If 1 = 1\r\n")], "exfat"),
    # exFAT: a scan runs past the clusters of an exactly full folder (forum 913)
    "ex-full-dir": ("Anvil/Storage/exfat.pbi", [
        ("  index = 0\n  While index < limit\n    If exfat_DirRead(dirFirst, dirFlags, dirLength, index, @exfat_entry[0]) = 0",
         "  index = 0\n  While index < 8388608\n    If exfat_DirRead(dirFirst, dirFlags, dirLength, index, @exfat_entry[0]) = 0")], "exfat"),
    # exFAT: name entries written before the file entry past the end marker (forum 914)
    "ex-create-order": ("Anvil/Storage/exfat.pbi", [
        ("  multi = Bool(exfat_entSector <> primarySector)", "  multi = 1"),
        ("    If exfat_entSector = primarySector\n      exfat_Copy(@exfat_sector[0] + exfat_entOffset, @exfat_setBuf[0] + e * 32, 32)",
         "    If exfat_entSector = primarySector And e > 0\n      exfat_Copy(@exfat_sector[0] + exfat_entOffset, @exfat_setBuf[0] + e * 32, 32)"),
        ("  If multi <> 0\n    PokeA(@exfat_sector[0] + primaryOffset, $05)\n  EndIf\n", "")], "exfat"),
    # exFAT: the empty-directory check skipped
    "ex-rmdir-nonempty": ("Anvil/Storage/exfat.pbi", [
        ("    If empty = 0\r\n      ProcedureReturn exfat_Fail(#EXFAT_E_NOT_EMPTY)",
         "    If empty = 9\r\n      ProcedureReturn exfat_Fail(#EXFAT_E_NOT_EMPTY)")], "exfat"),
    # ---- THE SPEED PATH (2026-09-17, forum 893/895/896/897) --------------
    # FAT32: a changed FAT sector is thrown away when another is read
    "fat-writeback-lost": ("Anvil/Storage/fat32.pbi", [
        ("  ; lose them. See fat_FlushFat.\n  If fat_FlushFat() = 0\n    ProcedureReturn 0\n  EndIf",
         "  ; lose them. See fat_FlushFat.\n  fat_fatDirty = 0")], "fat32"),
    # FAT32: a directory entry goes out ahead of the FAT entries it names
    "fat-dir-before-fat": ("Anvil/Storage/fat32.pbi", [
        ("  ; Pending FAT entries first - see fat_FlushFat.\n  If fat_FlushFat() = 0\n    ProcedureReturn 0\n  EndIf",
         "  ; removed by a mutation"),
        ("  ; certain to reach the medium.\n  If fat_FlushFat() = 0\n    ProcedureReturn 0\n  EndIf",
         "  ; removed by a mutation")], "fat32"),
    # FAT32: a sector run does not stop where the chain jumps
    "fat-run-ignores-chain": ("Anvil/Storage/fat32.pbi", [
        ("    If nxt <> last + 1 Or fat_ClusterValid(nxt) = 0\n", "    If fat_ClusterValid(nxt) = 0\n")], "fat32"),
    # exFAT: an entry set or other metadata sector goes out ahead of FAT and bitmap
    "ex-meta-after-dir": ("Anvil/Storage/exfat.pbi", [
        ("Procedure.i exfat_WriteSector(sector.i, *src)\n  If exfat_FlushMeta() = 0\n    ProcedureReturn 0\n  EndIf",
         "Procedure.i exfat_WriteSector(sector.i, *src)")], "exfat"),
    # exFAT: a changed FAT sector is thrown away when another is loaded
    "ex-writeback-lost": ("Anvil/Storage/exfat.pbi", [
        ("  If exfat_FlushFat() = 0\n    ProcedureReturn 0\n  EndIf\n  exfat_fatTag = -1\n  If exfat_ReadSectors(sector, 1, @exfat_fatSector[0]) = 0",
         "  exfat_fatDirty = 0\n  exfat_fatTag = -1\n  If exfat_ReadSectors(sector, 1, @exfat_fatSector[0]) = 0")], "exfat"),
    # exFAT: a sector run does not stop where the chain jumps
    "ex-run-ignores-chain": ("Anvil/Storage/exfat.pbi", [
        ("    If nxt <> cluster + 1\n      Break\n    EndIf", "    If nxt < 0\n      Break\n    EndIf")], "exfat"),
    # exFAT: the read cache survives a write
    "ex-rcache-stale": ("Anvil/Storage/exfat.pbi", [
        ("  exfat_rcacheSector = -1\n  If exfat_writer(lba, count, *src) = 0", "  If exfat_writer(lba, count, *src) = 0")], "exfat"),
    # "fat-link-before-claim" (link a cluster on before claiming it) was tried
    # here on 2026-09-17 and stays GREEN: with FAT entries written a sector at
    # a time the two orders differ on the medium only when prev and the new
    # cluster sit in different FAT sectors, and then the interrupted state is
    # a chain running past the file's size into a free cluster - which
    # fs_reference.py does not walk. Recorded rather than claimed.
    # "ex-dir-unzeroed" (a new directory cluster not zeroed) stays GREEN: the
    # exFAT allocator never hands a folder a cluster that held file data in
    # this sequence (it does not move its hint back on a free), so the
    # property has no fixture here yet. FAT32's twin, fat-dir-grow-unzeroed,
    # is RED.
}


def run_mutant(name: str, compiler: Path, fs_filter: str) -> tuple:
    rel, edits, fs = MUTANTS[name]
    with tempfile.TemporaryDirectory(prefix="anvil-fileops-mut-") as td:
        tree = Path(td) / "tree"
        tree.mkdir()
        for sub in ("Anvil", "RaspberryPi4", "Boards", "tools"):
            shutil.copytree(ROOT / sub, tree / sub, ignore=shutil.ignore_patterns("__pycache__", "*.img*", "Reference"))
        p = tree / rel
        # Line endings differ between checkouts (core.autocrlf); anchors are
        # compared with both sides reduced to LF.
        data = p.read_bytes().decode("utf-8").replace("\r\n", "\n")
        for old, new in edits:
            old = old.replace("\r\n", "\n")
            new = new.replace("\r\n", "\n")
            if data.count(old) != 1:
                return name, None, "ANCHOR BROKEN (%d matches) - repair the anchor" % data.count(old)
            data = data.replace(old, new)
        p.write_bytes(data.encode("utf-8"))
        targets = ["fat32", "exfat"] if fs == "both" else [fs]
        reasons = []
        for t in targets:
            if fs_filter not in ("both", t):
                continue
            try:
                res = gate(t, compiler, tree, cuts_every=4)
                if res["fails"]:
                    reasons.append("%s: %s" % (t, res["fails"][0]))
            except Exception as e:  # noqa: BLE001
                reasons.append("%s: did not run: %s" % (t, str(e).splitlines()[0][:120]))
        return name, bool(reasons), "; ".join(reasons) or "still GREEN"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--fs", choices=("fat32", "exfat", "both"), default="both")
    ap.add_argument("--mutate", nargs="*", default=None)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--export", type=Path)
    ap.add_argument("--fsck-host")
    ap.add_argument("--cuts-every", type=int, default=1)
    ap.add_argument("--show", choices=("fat32", "exfat"))
    args = ap.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    if args.show:
        print(generate(args.show))
        return 0
    if not args.compiler:
        raise SystemExit("fileops_check: pass --compiler or set PMF_COMPILER")
    compiler = Path(args.compiler).resolve()
    if args.mutate is not None:
        names = args.mutate or list(MUTANTS)
        bad = 0
        with cf.ProcessPoolExecutor(max_workers=args.jobs) as ex:
            futs = [ex.submit(run_mutant, n, compiler, args.fs) for n in names]
            for f in cf.as_completed(futs):
                name, red, why = f.result()
                print("mutant %-24s %s  %s" % (name, "RED  " if red else "GREEN", why), flush=True)
                if not red:
                    bad += 1
        print("fileops_check --mutate: %d of %d mutants caught" % (len(names) - bad, len(names)))
        return 1 if bad else 0
    targets = ["fat32", "exfat"] if args.fs == "both" else [args.fs]
    rc = 0
    with cf.ProcessPoolExecutor(max_workers=len(targets)) as ex:
        futs = {ex.submit(gate, t, compiler, ROOT, args.export, args.cuts_every): t for t in targets}
        for f in cf.as_completed(futs):
            res = f.result()
            status = "PASS" if not res["fails"] else "FAIL"
            print("fileops_check %s %s: %d operations, %s emitted A64 instructions, %d sector writes, "
                  "%s power-cut states checked, %.0f s"
                  % (res["fs"], status, len(sequence(res["fs"])), format(res["steps"], ","), res["writes"],
                     res.get("cuts", "no"), res["seconds"]), flush=True)
            for fail in res["fails"][:40]:
                print("   FAIL " + fail, flush=True)
            if res["fails"]:
                rc = 1
    if args.export and args.fsck_host and rc == 0 and args.fs in ("fat32", "both"):
        img = args.export / "fat32_final_partition.img"
        subprocess.run(["ssh", args.fsck_host, "mkdir -p anvil-fileops-audit-tmp"], check=True)
        subprocess.run(["scp", "-q", str(img), "%s:anvil-fileops-audit-tmp/fat32_final_partition.img" % args.fsck_host], check=True)
        r = subprocess.run(["ssh", args.fsck_host,
                            "cd anvil-fileops-audit-tmp && fsck.fat -n -V -v fat32_final_partition.img; echo EXIT=$?; "
                            "rm -f fat32_final_partition.img"], text=True, capture_output=True)
        print(r.stdout[-3000:])
        if "EXIT=0" not in r.stdout:
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

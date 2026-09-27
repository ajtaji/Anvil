#!/usr/bin/env python3
"""pi5_sd_save_check.py - `save ANVIL5.IMG <addr> <len>` on the Pi 5 monitor, executed.

The self-update path writes the new monitor over the boot file on the SD
card (tools/anvil_update.py --board pi5: `b`, then `save ANVIL5.IMG ...`,
then `reset`). This gate proves the middle step on the desk:

  * builds the REAL monitor, RaspberryPi4/Board/board.pi4 -t pi5;
  * builds a FAT32 card in Python - MBR (type $0C at LBA 2048), BPB, FSInfo,
    two FATs, a root directory holding an OLD ANVIL5.IMG (5000 bytes) and a
    CONFIG.TXT that must not be disturbed;
  * models the BCM2712 SD host (/soc@107c000000/mmc@fff000: SDHCI at
    $10_00FF_F000, Broadcom cfg at $10_00FF_F400) and an SDHC card behind
    it: CMD0/8/55+41/2/3/9/7/16/17/24, Buffer Read/Write Ready, Transfer
    Complete, 512-byte PIO through the data port;
  * places a new image in the payload window and runs the shipped CmdSave
    (Anvil/Core/fs_cmd.pbi) with the command line the host tool types;
  * reads the card back with its OWN FAT32 reader (below, not the
    monitor's) and requires ANVIL5.IMG to be exactly the new image, both
    FATs equal, CONFIG.TXT byte-identical, and the 2712 host set-up seen
    on the model: cfg SD_PIN_SEL = SD and SDIO_CFG_CTRL TEST_EN=1/TEST_LEV=0.

NEGATIVE CONTROL: the same run on a card that silently loses one word of
every block written to the file-data area must go red at the readback - proof the verdict comes from the
card's contents, not from the monitor's word.

Like pi5_serial_update_check.py, it compiles a copy of board.pi4 without
the tracked compiler's `#PMF_CHIP = 2711` bridge line, and says so.

    py -3 tools/a64/pi5_sd_save_check.py --compiler PureMetalForge.exe
"""
from __future__ import annotations

import argparse
import os
import pathlib
import random
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import pi5_desk as d                                   # noqa: E402
from pi5_serial_update_check import build_monitor, Uart, UART0, MON_LOAD, put_line  # noqa: E402

SD = 0x1000FFF000
CFG = 0x1000FFF400
PAYLOAD_AT = 0x10000000
PART_LBA = 2048
VOL_SECTORS = 70000
RESERVED = 32
FAT_SECTORS = 548
CARD_BLOCKS = 73728                     # (csize 71 + 1) * 1024
ROOT_CLUSTER = 2


# ----------------------------------------------------------------------
#  The card image: a sparse dict of 512-byte sectors.
# ----------------------------------------------------------------------
def fat_lba(n, copy=0):
    return PART_LBA + RESERVED + copy * FAT_SECTORS + n


def data_lba(cluster):
    return PART_LBA + RESERVED + 2 * FAT_SECTORS + (cluster - 2)


def make_card(old_image: bytes, config: bytes) -> dict:
    s = {}
    mbr = bytearray(512)
    mbr[446:462] = struct.pack("<B3sB3sII", 0, b"\0\0\0", 0x0C, b"\0\0\0", PART_LBA, VOL_SECTORS)
    mbr[510:512] = b"\x55\xAA"
    s[0] = bytes(mbr)
    bs = bytearray(512)
    bs[0:3] = b"\xEB\x58\x90"
    bs[3:11] = b"MSWIN4.1"
    struct.pack_into("<HBHBHHBHHHII", bs, 11, 512, 1, RESERVED, 2, 0, 0, 0xF8, 0, 63, 255, PART_LBA, VOL_SECTORS)
    struct.pack_into("<IHHIHH", bs, 36, FAT_SECTORS, 0, 0, ROOT_CLUSTER, 1, 6)
    bs[64] = 0x80
    bs[66] = 0x29
    struct.pack_into("<I", bs, 67, 0x27122712)
    bs[71:82] = b"ANVILBOOT  "
    bs[82:90] = b"FAT32   "
    bs[510:512] = b"\x55\xAA"
    s[PART_LBA] = bytes(bs)
    s[PART_LBA + 6] = bytes(bs)
    fsi = bytearray(512)
    struct.pack_into("<I", fsi, 0, 0x41615252)
    struct.pack_into("<III", fsi, 484, 0x61417272, 0xFFFFFFFF, 0xFFFFFFFF)
    struct.pack_into("<I", fsi, 508, 0xAA550000)
    s[PART_LBA + 1] = bytes(fsi)
    fat = {0: 0x0FFFFFF8, 1: 0x0FFFFFFF, ROOT_CLUSTER: 0x0FFFFFFF}
    entries = []
    nxt = 3
    for name, data in ((b"CONFIG  TXT", config), (b"ANVIL5  IMG", old_image)):
        n = (len(data) + 511) // 512
        first = nxt
        for k in range(n):
            c = first + k
            fat[c] = (c + 1) if k < n - 1 else 0x0FFFFFFF
            blk = data[k * 512:(k + 1) * 512]
            s[data_lba(c)] = blk + b"\0" * (512 - len(blk))
        nxt += n
        e = bytearray(32)
        e[0:11] = name
        e[11] = 0x20
        struct.pack_into("<HH", e, 20, first >> 16, 0)
        struct.pack_into("<HI", e, 26, first & 0xFFFF, len(data))
        entries.append(bytes(e))
    root = bytearray(512)
    lab = bytearray(32)
    lab[0:11] = b"ANVILBOOT  "
    lab[11] = 0x08
    root[0:32] = lab
    for i, e in enumerate(entries):
        root[32 * (i + 1):32 * (i + 2)] = e
    s[data_lba(ROOT_CLUSTER)] = bytes(root)
    for copy in (0, 1):
        for sec in range(FAT_SECTORS):
            blk = bytearray(512)
            any_ = False
            for i in range(128):
                c = sec * 128 + i
                if c in fat:
                    struct.pack_into("<I", blk, 4 * i, fat[c])
                    any_ = True
            if any_:
                s[fat_lba(sec, copy)] = bytes(blk)
    return s


def sector(s, lba):
    return s.get(lba, b"\0" * 512)


def fat_entry(s, c, copy=0):
    return struct.unpack_from("<I", sector(s, fat_lba(c // 128, copy)), 4 * (c % 128))[0] & 0x0FFFFFFF


def read_file(s, name: bytes):
    """An independent FAT32 reader: root directory (one cluster chain), 8.3 names."""
    c = ROOT_CLUSTER
    seen = 0
    while c < 0x0FFFFFF8 and seen < 64:
        blk = sector(s, data_lba(c))
        for off in range(0, 512, 32):
            e = blk[off:off + 32]
            if e[0] == 0:
                return None
            if e[0] == 0xE5 or e[11] == 0x0F or (e[11] & 0x08):
                continue
            if e[0:11] == name:
                first = (struct.unpack_from("<H", e, 20)[0] << 16) | struct.unpack_from("<H", e, 26)[0]
                size = struct.unpack_from("<I", e, 28)[0]
                out = bytearray()
                cc = first
                hops = 0
                while len(out) < size:
                    if cc < 2 or cc >= 0x0FFFFFF7 or hops > 100000:
                        return ("broken chain", bytes(out), size)
                    out += sector(s, data_lba(cc))
                    cc = fat_entry(s, cc)
                    hops += 1
                return bytes(out[:size])
        c = fat_entry(s, c)
        seen += 1
    return None


# ----------------------------------------------------------------------
#  The BCM2712 SD host and an SDHC card.
# ----------------------------------------------------------------------
class SdHost:
    RCA = 0x2712

    def __init__(self, card: dict, drop_word: int = -1):
        self.card = card
        self.regs = {}
        self.intr = 0
        self.cfg = {}
        self.cfg_writes = []
        self.rx = []
        self.wbuf = []
        self.wlba = None
        self.cmds = []
        self.words_written = 0
        self.drop_word = drop_word
        self.app = False

    def complete(self):
        self.intr |= 0x1                                     # CMD_DONE

    def command(self, v):
        idx = (v >> 24) & 0x3F
        arg = self.regs.get(0x08, 0)
        self.cmds.append(idx)
        r = [0, 0, 0, 0]
        app, self.app = self.app, False
        if idx == 0:
            pass
        elif idx == 8:
            r[0] = arg & 0xFFF
        elif idx == 55:
            r[0] = 0x120
            self.app = True
        elif idx == 41 and app:
            r[0] = 0xC0FF8000                               # ready, CCS (SDHC)
        elif idx == 2:
            r = [0x12345678, 0x9ABCDEF0, 0x0F1E2D3C, 0x00415056]
        elif idx == 3:
            r[0] = self.RCA << 16
        elif idx == 9:
            r = [0, 71 << 8, 0, 1 << 22]                     # CSD v2, C_SIZE 71
        elif idx in (7, 16, 13):
            r[0] = 0x900
        elif idx == 17:
            self.rx = list(struct.unpack("<128I", sector(self.card, arg)))
            self.intr |= 0x20                                # READ_RDY
        elif idx == 24:
            self.wlba = arg
            self.wbuf = []
            self.intr |= 0x10                                # WRITE_RDY
        else:
            self.intr |= 0x8000 | 0x10000                    # ERR + CMD timeout
            return
        for i in range(4):
            self.regs[0x10 + 4 * i] = r[i] & 0xFFFFFFFF
        self.complete()

    def __call__(self, addr, size, value):
        if UART0 <= addr < UART0 + 0x1000:
            return 0 if value is not None else (0x10 if True else 0)
        if CFG <= addr < CFG + 0x200:
            off = addr - CFG
            if value is None:
                return self.cfg.get(off, 0)
            self.cfg[off] = value
            self.cfg_writes.append((off, value))
            return 0
        if not (SD <= addr < SD + 0x260):
            d.die("the SD path touched $%X, which is neither the SD host nor its cfg window" % addr)
        off = addr - SD
        if value is None:
            if off == 0xFC:
                return 0x10040000                            # version field 4 (SDHCI 4.10)
            if off == 0x40:
                return 0x25FE32B2
            if off == 0x44:
                return 0x00000077
            if off == 0x24:
                return 0x00070000                            # inserted, stable, pin; no inhibit
            if off == 0x2C:
                return self.regs.get(0x2C, 0) | 0x2          # internal clock stable
            if off == 0x30:
                return self.intr
            if off == 0x20:
                w = self.rx.pop(0) if self.rx else 0
                if not self.rx:
                    self.intr |= 0x2                         # DATA_DONE after the last word
                return w
            return self.regs.get(off, 0)
        if off == 0x30:
            self.intr &= ~value
            return 0
        if off == 0x2C:
            self.regs[off] = value & ~0x07000000             # software resets self-clear
            return 0
        if off == 0x0C:
            self.command(value)
            return 0
        if off == 0x20:
            self.words_written += 1
            # the negative control's defect: in every block written to the
            # file-data area (past the root directory cluster), one word is lost
            if self.drop_word >= 0 and self.wlba > data_lba(ROOT_CLUSTER) and len(self.wbuf) == self.drop_word:
                self.wbuf.append(None)
            else:
                self.wbuf.append(value)
            if len(self.wbuf) == 128:
                blk = bytearray(sector(self.card, self.wlba))
                for i, w in enumerate(self.wbuf):
                    if w is not None:
                        struct.pack_into("<I", blk, 4 * i, w)
                self.card[self.wlba] = bytes(blk)
                self.wbuf = []
                self.intr |= 0x2
            return 0
        self.regs[off] = value
        return 0


def run(img, procs, syms, new_image: bytes, card: dict, drop_word=-1):
    host = SdHost(card, drop_word)
    d.LOAD = MON_LOAD
    m = d.Machine(img, procs, host)
    m.poke(PAYLOAD_AT, new_image)
    put_line(m, syms, "save ANVIL5.IMG %X %X" % (PAYLOAD_AT, len(new_image)))
    m.poke(syms["global_gpos"], (4).to_bytes(8, "little"))   # just past "save"
    m.call("CmdSave", limit=400_000_000)
    return host


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    args = ap.parse_args()
    cc = d.compiler(args.compiler)
    work = ROOT / "_work" / "pi5_sd_save"
    rnd = random.Random(2712)
    old = bytes(rnd.randrange(256) for _ in range(5000))
    new = bytes(rnd.randrange(256) for _ in range(3000))
    config = b"enable_rp1_uart=1\npciex4_reset=0\nkernel=ANVIL5.IMG\n"
    fails = []

    def check(ok, what):
        print("  %s  %s" % ("ok  " if ok else "FAIL", what))
        if not ok:
            fails.append(what)

    try:
        img, procs, syms = build_monitor(cc, work)
        card = make_card(old, config)
        check(read_file(card, b"ANVIL5  IMG") == old, "the model card reads back its own old image (reader sanity)")
        host = run(img, procs, syms, new, card)
        got = read_file(card, b"ANVIL5  IMG")
        check(got == new, "ANVIL5.IMG on the card is now exactly the new %d-byte image" % len(new))
        check(read_file(card, b"CONFIG  TXT") == config, "CONFIG.TXT is byte-identical")
        f0 = [sector(card, fat_lba(i, 0)) for i in range(FAT_SECTORS)]
        f1 = [sector(card, fat_lba(i, 1)) for i in range(FAT_SECTORS)]
        check(f0 == f1, "both FAT copies agree")
        check(24 in host.cmds, "the writes went out as CMD24 (%d data words)" % host.words_written)
        pinsel = [v for o, v in host.cfg_writes if o == 0x44]
        ctrl = [v for o, v in host.cfg_writes if o == 0x00]
        check(bool(pinsel) and all((v & 3) == 2 for v in pinsel), "2712: cfg SD_PIN_SEL written as SD (%s)"
              % ", ".join("$%X" % v for v in pinsel))
        check(bool(ctrl) and (ctrl[-1] & 0x80000000) and not (ctrl[-1] & 0x40000000),
              "2712: cfg SDIO_CFG_CTRL TEST_EN set, TEST_LEV clear")
        # negative control
        card2 = make_card(old, config)
        run(img, procs, syms, new, card2, drop_word=5)
        check(read_file(card2, b"ANVIL5  IMG") != new,
              "negative control: a card that loses one word per data block fails the readback")
    except d.GateFail as e:
        print("pi5_sd_save_check: FAIL - %s" % e)
        return 1
    if fails:
        print("pi5_sd_save_check: FAIL - %d check(s)" % len(fails))
        return 1
    print("pi5_sd_save_check: PASS - save replaced ANVIL5.IMG on a modelled BCM2712 SD card, readback independent, negative control red. Desk only: silicon owed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

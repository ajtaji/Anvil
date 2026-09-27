#!/usr/bin/env python3
"""Desk gate: BCM2712 pcie1 cold start (pcie.pi4) + NVMe (Anvil/Storage/nvme.pbi) + the shared filesystems.

SILICON OWED. Builds RaspberryPi5/Tests/nvme2712_probe.pi5 with `-t pi5` and runs
it on tools/a64/a64_interp.py against:

  * a modelled brcmstb pcie1 root complex at $10_0011_0000: the link trains
    only after RESCAL is calibrated, the bridge has been through <&bcm_reset
    43>, SerDes IDDQ is off, the 54 MHz MDIO refclk table is written and
    PERST# is released - and then only after 20 ms of modelled time.
    Outbound and inbound translation are computed FROM THE WINDOW REGISTERS
    the image programmed, so a wrong window reaches nothing
  * the RESCAL and brcmstb-reset controllers (only bank 1 bit 11 may move)
  * an NVMe controller as the endpoint (config space with a 64-bit BAR0,
    CAP/CC/CSTS/AQA/ASQ/ACQ, doorbells, admin + one I/O queue pair,
    Identify, create CQ/SQ, read/write/flush with PRP1/PRP2/PRP list),
    reached only through the routes the image built
  * a FAT32 volume on the namespace, built here, served as 512-byte or
    4096-byte logical blocks

Scenarios: 512-byte and 4 KiB namespaces mount partition 1, read HELLO.TXT
and write NEW.TXT through FsSetRangeReader/Writer/BlockFlusher; the written
file is then found by parsing the disk image here. Refusals: no endpoint
(link never up) -> Pcie1Init -4 inside the bounded wait with no config
access below the root; Controller Fatal Status on enable -> NvmeAttach
#NVME_ERR_FATAL with no admin command; RESCAL already calibrated -> START
never written. Mutants of pcie.pi4 / nvme.pbi must each go red.

Run from PowerShell:
  $env:PMF_ALLOW_UNTRACKED_COMPILER = 1
  py -3 -B tools/a64/a64_nvme_pi5_check.py --compiler <PureMetalForge.exe>
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "a64"))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "RaspberryPi5" / "Boot"))
from a64_interp import A64, AlignmentFault, attach_symbols  # noqa: E402
from pmf_compiler import resolve_compiler  # noqa: E402

FIXTURE = pathlib.PurePosixPath("RaspberryPi5/Tests/nvme2712_probe.pi5")
PCIE = pathlib.PurePosixPath("RaspberryPi4/Lib/pcie.pi4")
NVME = pathlib.PurePosixPath("Anvil/Storage/nvme.pbi")
MUTANT_FILES = (FIXTURE, PCIE, NVME,
                pathlib.PurePosixPath("RaspberryPi4/Lib/timer.pi4"),
                pathlib.PurePosixPath("Anvil/Storage/fat32.pbi"),
                pathlib.PurePosixPath("Anvil/Storage/exfat.pbi"),
                pathlib.PurePosixPath("Anvil/Storage/filesystem.pbi"),
                pathlib.PurePosixPath("RaspberryPi4/Intrinsics/bcm2711_hardware.def"))
DEFAULT_SOURCES = pathlib.Path(r"C:\Users\ajtaj\Desktop\CompilerEmbedded\Raspberry Pi 5")

LOAD, STACK, LOADER_SP, LOADER_LR = 0x00400000, 0x03000000, 0x00100000, 0xDEADBEE0
CTL, OUT, BUF, ARENA, DONE = 0x00E00000, 0x00E00100, 0x00E01000, 0x01000000, 0x600DF00D
BIG = 0x00E20000
RAW_LBA, RAW_N = 1000, 48


def raw_pattern(sector):
    return bytes(((sector * 31 + i * 7) ^ (i >> 3)) & 0xFF for i in range(512))
CNTFRQ = 54_000_000                       # TF-A rpi5_bl31_setup.c 118-126
TICKS_PER_STEP = 256                      # 4.7 us per instruction: coarse enough to be
                                          # quick, fine enough for the 100 us MDIO and
                                          # 1 ms RESCAL budgets to be real budgets
LINK_TRAIN_MS = 20

L = "raspberrypi/linux 7e030b60 "
PINNED = {
    "RC": (0x1000110000, "DTB /axi/pcie@1000110000 reg"),
    "RC_SIZE": (0x9310, "DTB pcie1 reg size"),
    "PCIE2": (0x1000120000, "DTB /axi/pcie@1000120000 - must NOT be touched"),
    "RESCAL": (0x1000119500, "DTB reset-controller@119500 via /soc ranges"),
    "RESET": (0x1001504318, "DTB reset-controller@1504318 via /soc ranges"),
    "BRIDGE_ID": (43, "DTB pcie1 resets <&bcm_reset 43>"),
    "OUT_CPU": (0x1B80000000, "DTB pcie1 ranges entry 1 cpu"),
    "OUT_BUS": (0x80000000, "DTB pcie1 ranges entry 1 pci"),
    "OUT_SIZE": (0x80000000, "DTB pcie1 ranges entry 1 size"),
    "DMA_BUS": (0x1000000000, "DTB pcie1 dma-ranges entry 1 pci"),
    "DMA_SIZE": (0x1000000000, "DTB pcie1 dma-ranges entry 1 size"),
    "MISC_CTRL": (0x4008, L + "pcie-brcmstb.c 100"),
    "WIN0_LO": (0x400C, "112"), "WIN0_HI": (0x4010, "116"),
    "RC_BAR1_LO": (0x402C, "129"), "PCIE_CTRL": (0x4064, "143"), "PCIE_STATUS": (0x4068, "147"),
    "WIN0_BASE_LIMIT": (0x4070, "157"), "WIN0_BASE_HI": (0x4080, "163"), "WIN0_LIMIT_HI": (0x4084, "168"),
    "UBUS_BAR1": (0x40AC, "189"), "HARD_DEBUG": (0x4304, "2235"),
    "EXT_CFG_INDEX": (0x9000, "2233"), "EXT_CFG_DATA": (0x8000, "2234"),
    "MDIO_ADDR": (0x1100, "56"), "MDIO_WR": (0x1104, "57"),
    "PERSTB": (0x4, "144"), "SERDES_IDDQ": (0x08000000, "178"),
    "RESCAL_STATUS": (0x8, L + "reset-brcmstb-rescal.c 14"),
    "SW_INIT_BANK": (0x18, L + "reset-brcmstb.c SW_INIT_BANK_SIZE"),
    "MDIO_TABLE": ([(0x1F, 0x1600), (0x16, 0x50B9), (0x17, 0xBDA1), (0x18, 0x0094), (0x19, 0x97B4),
                    (0x1B, 0x5030), (0x1C, 0x5030), (0x1E, 0x0007)], L + "pcie-brcmstb.c 1031-1045"),
    "NVME_CC": (0x14, L + "include/linux/nvme.h 136"), "NVME_CSTS": (0x1C, "137"),
    "NVME_AQA": (0x24, "139"), "NVME_ASQ": (0x28, "140"), "NVME_ACQ": (0x30, "141"),
    "NVME_DBS": (0x1000, "162"), "NVME_IOSQES": (6, "199"), "NVME_IOCQES": (4, "200"),
}


def fail(msg):
    raise SystemExit("a64_nvme_pi5_check: FAIL - " + msg)


def derive(src):
    from dtb_contract import parse, mapped_reg
    d = {}
    s = src / "Sources"
    c = (s / "pcie-brcmstb.c").read_text(errors="replace")

    def df(name, text=c):
        m = re.search(r"#define\s+" + name + r"\s+(0x[0-9a-fA-F]+|\d+)", text)
        if not m:
            fail(f"{name} not found")
        return int(m.group(1), 0)
    for k, n in (("MISC_CTRL", "PCIE_MISC_MISC_CTRL"), ("WIN0_LO", "PCIE_MISC_CPU_2_PCIE_MEM_WIN0_LO"),
                 ("WIN0_HI", "PCIE_MISC_CPU_2_PCIE_MEM_WIN0_HI"), ("RC_BAR1_LO", "PCIE_MISC_RC_BAR1_CONFIG_LO"),
                 ("PCIE_CTRL", "PCIE_MISC_PCIE_CTRL"), ("PCIE_STATUS", "PCIE_MISC_PCIE_STATUS"),
                 ("WIN0_BASE_LIMIT", "PCIE_MISC_CPU_2_PCIE_MEM_WIN0_BASE_LIMIT"),
                 ("WIN0_BASE_HI", "PCIE_MISC_CPU_2_PCIE_MEM_WIN0_BASE_HI"),
                 ("WIN0_LIMIT_HI", "PCIE_MISC_CPU_2_PCIE_MEM_WIN0_LIMIT_HI"),
                 ("UBUS_BAR1", "PCIE_MISC_UBUS_BAR1_CONFIG_REMAP"), ("MDIO_ADDR", "PCIE_RC_DL_MDIO_ADDR"),
                 ("MDIO_WR", "PCIE_RC_DL_MDIO_WR_DATA"), ("PERSTB", "PCIE_MISC_PCIE_CTRL_PCIE_PERSTB_MASK"),
                 ("SERDES_IDDQ", "PCIE_MISC_HARD_PCIE_HARD_DEBUG_SERDES_IDDQ_MASK")):
        d[k] = df(n)
    m = re.search(r"pcie_offsets_bcm7712\[\] = \{(.*?)\};", c, re.S)
    offs = dict(re.findall(r"\[(\w+)\]\s*=\s*(0x[0-9a-f]+)", m.group(1)))
    d["HARD_DEBUG"] = int(offs["PCIE_HARD_DEBUG"], 16)
    d["EXT_CFG_INDEX"] = int(offs["EXT_CFG_INDEX"], 16)
    d["EXT_CFG_DATA"] = int(offs["EXT_CFG_DATA"], 16)
    m = re.search(r"data\[\] = \{([^}]*)\};\s*static const u8 regs\[\] = \{([^}]*)\};", c)
    data = [int(x, 16) for x in re.findall(r"0x[0-9a-f]+", m.group(1))]
    regs = [int(x, 16) for x in re.findall(r"0x[0-9a-f]+", m.group(2))]
    d["MDIO_TABLE"] = [(0x1F, 0x1600)] + list(zip(regs, data))
    r = (s / "reset-brcmstb-rescal.c").read_text(errors="replace")
    d["RESCAL_STATUS"] = df("BRCM_RESCAL_STATUS", r)
    b = (s / "reset-brcmstb.c").read_text(errors="replace")
    d["SW_INIT_BANK"] = df("SW_INIT_BANK_SIZE", b)
    h = (s / "linux-nvme.h").read_text(errors="replace")
    for k, n in (("NVME_CC", "NVME_REG_CC"), ("NVME_CSTS", "NVME_REG_CSTS"), ("NVME_AQA", "NVME_REG_AQA"),
                 ("NVME_ASQ", "NVME_REG_ASQ"), ("NVME_ACQ", "NVME_REG_ACQ"), ("NVME_DBS", "NVME_REG_DBS")):
        d[k] = int(re.search(n + r"\s*=\s*(0x[0-9a-f]+)", h).group(1), 16)
    d["NVME_IOSQES"] = df("NVME_NVM_IOSQES", h)
    d["NVME_IOCQES"] = df("NVME_NVM_IOCQES", h)
    for name in ("bcm2712-rpi-5-b.dtb", "bcm2712-d-rpi-5-b.dtb", "bcm2712d0-rpi-5-b.dtb"):
        n = parse((src / "Boot staging" / name).read_bytes())
        node = n["/axi/pcie@1000110000"]
        rg = node["ranges"]
        dr = node["dma-ranges"]
        cells = lambda blob, i, k: int.from_bytes(blob[4 * i:4 * (i + k)], "big")
        found = {"RC": mapped_reg(n, "/axi/pcie@1000110000"), "RC_SIZE": cells(node["reg"], 2, 2),
                 "PCIE2": mapped_reg(n, "/axi/pcie@1000120000"),
                 "RESCAL": mapped_reg(n, "/soc@107c000000/reset-controller@119500"),
                 "RESET": mapped_reg(n, "/soc@107c000000/reset-controller@1504318"),
                 "BRIDGE_ID": cells(node["resets"], 2, 1),
                 "OUT_BUS": cells(rg, 1, 2), "OUT_CPU": cells(rg, 3, 2), "OUT_SIZE": cells(rg, 5, 2),
                 "DMA_BUS": cells(dr, 1, 2), "DMA_SIZE": cells(dr, 5, 2)}
        if cells(dr, 3, 2) != 0:
            fail(f"{name}: pcie1 dma-ranges entry 1 is not onto CPU 0")
        for k, v in found.items():
            if k in d and d[k] != v:
                fail(f"the pinned DTBs disagree about {k}")
            d[k] = v
    return d


def constants(src):
    k = {n: v for n, (v, _w) in PINNED.items()}
    if src is None:
        print("  SOURCES NOT CROSS-CHECKED - PINNED table only")
        return k
    got = derive(src)
    for n, (v, w) in PINNED.items():
        if got.get(n) != v:
            fail(f"PINNED {n} = {v!r} but the sources say {got.get(n)!r} ({w})")
    print(f"  sources: {len(PINNED)} pinned values re-derived from {src} - all agree")
    return k


# =====================================================================
#  A FAT32 VOLUME (Microsoft FAT specification field layout)
# =====================================================================
PART_LBA = 2048
PART_SECTORS = 72000
RSVD, NFATS, SPC = 32, 2, 1
HELLO = (b"Hello from an NVMe namespace behind the Pi 5's external PCIe x1 connector. "
         b"If this text came back, the shared FAT32 driver read it through NvmeReadBlocks.\r\n")


def make_disk():
    disk = {}
    fatsz = ((PART_SECTORS - RSVD) // (128 * SPC + NFATS)) + 1
    clusters = (PART_SECTORS - RSVD - NFATS * fatsz) // SPC
    assert clusters >= 65525, clusters
    mbr = bytearray(512)
    mbr[446 + 4] = 0x0C
    struct.pack_into("<II", mbr, 446 + 8, PART_LBA, PART_SECTORS)
    mbr[510:512] = b"\x55\xAA"
    disk[0] = bytes(mbr)
    bs = bytearray(512)
    bs[0:3] = b"\xEB\x58\x90"
    bs[3:11] = b"MSWIN4.1"
    struct.pack_into("<HBHBHHBHHHII", bs, 11, 512, SPC, RSVD, NFATS, 0, 0, 0xF8, 0, 63, 255, PART_LBA, PART_SECTORS)
    struct.pack_into("<IHHIHH", bs, 36, fatsz, 0, 0, 2, 1, 6)
    bs[64] = 0x80
    bs[66] = 0x29
    struct.pack_into("<I", bs, 67, 0x12345678)
    bs[71:82] = b"NO NAME    "
    bs[82:90] = b"FAT32   "
    bs[510:512] = b"\x55\xAA"
    disk[PART_LBA] = bytes(bs)
    disk[PART_LBA + 6] = bytes(bs)
    fsi = bytearray(512)
    struct.pack_into("<I", fsi, 0, 0x41615252)
    struct.pack_into("<III", fsi, 484, 0x61417272, 0xFFFFFFFF, 0xFFFFFFFF)
    struct.pack_into("<I", fsi, 508, 0xAA550000)
    disk[PART_LBA + 1] = bytes(fsi)
    disk[PART_LBA + 7] = bytes(fsi)
    fat = bytearray(512)
    struct.pack_into("<IIII", fat, 0, 0x0FFFFFF8, 0x0FFFFFFF, 0x0FFFFFFF, 0x0FFFFFFF)
    for f in range(NFATS):
        disk[PART_LBA + RSVD + f * fatsz] = bytes(fat)
    data0 = PART_LBA + RSVD + NFATS * fatsz
    root = bytearray(512)
    root[0:11] = b"HELLO   TXT"
    root[11] = 0x20
    struct.pack_into("<HHI", root, 26, 3, len(HELLO) & 0xFFFF, len(HELLO))
    struct.pack_into("<H", root, 20, 0)
    struct.pack_into("<H", root, 26, 3)
    struct.pack_into("<I", root, 28, len(HELLO))
    disk[data0 + 0] = bytes(root)
    disk[data0 + 1] = HELLO.ljust(512, b"\0")
    for s in range(RAW_LBA, RAW_LBA + RAW_N):          # below the partition
        disk[s] = raw_pattern(s)
    return disk, fatsz, data0


def find_file(disk, fatsz, data0, name83):
    root = disk.get(data0, bytes(512))
    for i in range(0, 512, 32):
        e = root[i:i + 32]
        if e[0:11] == name83:
            clus = struct.unpack_from("<H", e, 20)[0] << 16 | struct.unpack_from("<H", e, 26)[0]
            size = struct.unpack_from("<I", e, 28)[0]
            return disk.get(data0 + clus - 2, bytes(512))[:size]
    return None


# =====================================================================
#  THE MODEL
# =====================================================================
class Nvme:
    def __init__(self, bus, lba_shift, fatal=False):
        self.bus, self.shift, self.fatal = bus, lba_shift, fatal
        self.cfg = {0x00: 0xA80A144D, 0x04: 0, 0x08: 0x01080200, 0x0C: 0, 0x10: 0x4, 0x14: 0}
        self.bar_mask = ~(0x4000 - 1) & 0xFFFFFFFF
        self.cc = 0
        self.csts = 0
        self.rdy_countdown = 0
        self.aqa = self.asq = self.acq = 0
        self.sqs = {}            # qid -> dict(base, size, head, cqid)
        self.cqs = {}            # qid -> dict(base, size, tail, head, phase)
        self.log = []
        self.faults = []
        self.admin_after_fatal = 0

    # config space
    def cfg_read(self, off):
        return self.cfg.get(off, 0)

    def cfg_write(self, off, v):
        if off == 0x10:
            self.cfg[0x10] = (v & self.bar_mask) | 0x4
        elif off == 0x14:
            self.cfg[0x14] = v
        elif off == 0x04:
            self.cfg[0x04] = v & 0x7
        elif off in (0x00, 0x08, 0x0C):
            pass
        else:
            self.cfg[off] = v

    def bar(self):
        return (self.cfg[0x10] & 0xFFFFFFF0) | (self.cfg[0x14] << 32)

    # registers
    def reg_read(self, off):
        if off == 0x00:
            return 63 | (1 << 16) | (20 << 24)                 # MQES 63, CQR, TO 20
        if off == 0x04:
            return (1 << 5)                                    # CSS NVM; DSTRD 0; MPSMIN 0
        if off == 0x08:
            return 0x00010400
        if off == 0x14:
            return self.cc
        if off == 0x1C:
            if self.rdy_countdown > 0:
                self.rdy_countdown -= 1
                if self.rdy_countdown == 0:
                    if self.cc & 1:
                        if self.fatal:
                            self.csts |= 2
                        else:
                            self.csts |= 1
                    else:
                        self.csts &= ~1
            return self.csts
        if off == 0x24:
            return self.aqa
        return 0

    def reg_write(self, off, v, board):
        if off == 0x0C:
            return
        if off == 0x14:
            was = self.cc & 1
            self.cc = v
            if (v & 1) and not was:
                if ((v >> 16) & 0xF) != 6 or ((v >> 20) & 0xF) != 4 or ((v >> 7) & 0xF) != 0 or ((v >> 4) & 7) != 0:
                    self.faults.append(f"CC enabled with ${v:08X}")
                    return
                if not (self.aqa and self.asq and self.acq):
                    self.faults.append("enabled without admin queues")
                self.sqs = {0: dict(base=self.asq, size=(self.aqa & 0xFFF) + 1, head=0, cqid=0)}
                self.cqs = {0: dict(base=self.acq, size=((self.aqa >> 16) & 0xFFF) + 1, tail=0, head=0, phase=1)}
                self.rdy_countdown = 3
            elif not (v & 1) and was:
                self.rdy_countdown = 2
            return
        if off == 0x24:
            self.aqa = v
            return
        if off in (0x28, 0x2C, 0x30, 0x34):
            reg = "asq" if off < 0x30 else "acq"
            cur = getattr(self, reg)
            if off in (0x28, 0x30):
                cur = (cur & ~0xFFFFFFFF) | v
            else:
                cur = (cur & 0xFFFFFFFF) | (v << 32)
            setattr(self, reg, cur)
            return
        if off >= 0x1000:
            idx = (off - 0x1000) // 4
            qid, is_cq = idx // 2, idx % 2
            table = self.cqs if is_cq else self.sqs
            if qid not in table:
                self.faults.append(f"doorbell for unknown queue {qid} ({'CQ' if is_cq else 'SQ'})")
                return
            if is_cq:
                self.cqs[qid]["head"] = v
            else:
                self.run_sq(qid, v, board)
            return
        self.faults.append(f"write to NVMe register +${off:X}")

    def run_sq(self, qid, tail, board):
        if self.csts & 2:
            self.admin_after_fatal += 1
            return
        q = self.sqs[qid]
        if not 0 <= tail < q["size"]:
            self.faults.append(f"SQ{qid} tail {tail} outside the queue")
            return
        guard = 0
        while q["head"] != tail:
            guard += 1
            if guard > q["size"]:
                self.faults.append("SQ doorbell loop")
                return
            sqe = board.dma_read(q["base"] + 64 * q["head"], 64)
            q["head"] = (q["head"] + 1) % q["size"]
            status = self.execute(qid, sqe, board)
            cq = self.cqs[q["cqid"]]
            if (cq["tail"] + 1) % cq["size"] == cq["head"]:
                self.faults.append(f"CQ{q['cqid']} overflow - its head doorbell was not rung")
                return
            cqe = bytearray(16)
            struct.pack_into("<HHHH", cqe, 8, q["head"], qid, struct.unpack_from("<H", sqe, 2)[0],
                             (status << 1) | cq["phase"])
            board.dma_write(cq["base"] + 16 * cq["tail"], bytes(cqe))
            cq["tail"] += 1
            if cq["tail"] >= cq["size"]:
                cq["tail"] = 0
                cq["phase"] ^= 1

    def prp_pages(self, sqe, nbytes, board):
        prp1, prp2 = struct.unpack_from("<QQ", sqe, 24)
        pages = (nbytes + 4095) // 4096
        if prp1 & 0xFFF:
            self.faults.append("PRP1 not page aligned")
        out = [prp1]
        if pages == 2:
            out.append(prp2)
        elif pages > 2:
            lst = board.dma_read(prp2, 8 * (pages - 1))
            out += list(struct.unpack_from("<%dQ" % (pages - 1), lst))
        return out

    def execute(self, qid, sqe, board):
        op = sqe[0]
        self.log.append((qid, op))
        if qid == 0:
            if op == 0x06:
                cns = sqe[40]
                buf = bytearray(4096)
                if cns == 1:
                    struct.pack_into("<HH", buf, 0, 0x144D, 0x144D)
                    buf[4:24] = b"DESKMODEL-0001".ljust(20)
                    buf[24:64] = b"Modelled NVMe for a64_nvme_pi5_check".ljust(40)
                    buf[77] = 5
                    struct.pack_into("<I", buf, 516, 1)
                elif cns == 0 and struct.unpack_from("<I", sqe, 4)[0] == 1:
                    blocks = (PART_LBA + PART_SECTORS) * 512 >> self.shift
                    struct.pack_into("<QQQ", buf, 0, blocks, blocks, blocks)
                    buf[26] = 0
                    buf[128 + 2] = self.shift
                else:
                    return 0x0B                     # invalid namespace or format
                pages = self.prp_pages(sqe, 4096, board)
                board.dma_write(pages[0], bytes(buf))
                return 0
            if op in (0x05, 0x01):
                qidn, qsize, flags, other = struct.unpack_from("<HHHH", sqe, 40)
                base = struct.unpack_from("<Q", sqe, 24)[0]
                if not flags & 1:
                    self.faults.append("queue not physically contiguous")
                if op == 0x05 and flags & 2:
                    self.faults.append("CQ created with interrupts enabled")
                if op == 0x05:
                    self.cqs[qidn] = dict(base=base, size=qsize + 1, tail=0, head=0, phase=1)
                else:
                    if other not in self.cqs:
                        self.faults.append("SQ created on a CQ that does not exist")
                        return 0x100
                    self.sqs[qidn] = dict(base=base, size=qsize + 1, head=0, cqid=other)
                return 0
            return 0x01                             # invalid opcode
        # I/O on queue 1 (its CQ is queue cqid)
        if op == 0x00:
            return 0
        slba = struct.unpack_from("<Q", sqe, 40)[0]
        nlb = (struct.unpack_from("<H", sqe, 48)[0]) + 1
        nbytes = nlb << self.shift
        pages = self.prp_pages(sqe, nbytes, board)
        per = 1 << (self.shift - 9)
        if op == 0x02:
            data = bytearray()
            for i in range(nlb * per):
                data += board.disk.get(slba * per + i, bytes(512))
            for i, pg in enumerate(pages):
                board.dma_write(pg, bytes(data[i * 4096:(i + 1) * 4096]))
            return 0
        if op == 0x01:
            data = bytearray()
            for pg in pages:
                data += board.dma_read(pg, 4096)
            data = data[:nbytes]
            for i in range(nlb * per):
                board.disk[slba * per + i] = bytes(data[i * 512:(i + 1) * 512])
            return 0
        return 0x01


class Board:
    def __init__(self, k, lba_shift=9, present=True, fatal=False, rescal_done=False):
        self.k = k
        self.steps = 0
        self.rc = {k["PCIE_STATUS"]: 0x80, 0x4DC: 0x43, k["HARD_DEBUG"]: k["SERDES_IDDQ"]}
        self.rescal = {0: 0, 4: 0, 8: 1 if rescal_done else 0}
        self.rescal_start_writes = 0
        self.rescal_countdown = 0
        self.bridge_asserted = False
        self.bridge_cycled = False
        self.reset_faults = []
        self.mdio = []
        self.perst_released_at = None
        self.present = present
        self.ep = Nvme(k["OUT_BUS"], lba_shift, fatal)
        self.disk, self.fatsz, self.data0 = make_disk()
        self.cfg_index = 0
        self.faults = []
        self.events = []
        self.cfg_below_root = 0
        self.mem = None

    def tick(self):
        return self.steps * TICKS_PER_STEP

    def ms(self, t):
        return t * 1000.0 / CNTFRQ

    def link_up(self):
        k = self.k
        if not self.present or self.perst_released_at is None:
            return False
        ok = (self.rescal[8] & 1) and self.bridge_cycled and not (self.rc.get(k["HARD_DEBUG"], 0) & k["SERDES_IDDQ"])
        ok = ok and [m for m in self.mdio if m[0] == 0x1F] and len(self.mdio) >= 8
        return bool(ok) and self.ms(self.tick() - self.perst_released_at) >= LINK_TRAIN_MS

    # -- the RC register file --------------------------------------------
    def rc_read(self, off):
        k = self.k
        if off == k["PCIE_STATUS"]:
            return 0x80 | (0x30 if self.link_up() else 0)
        if off == 0xBC:
            return (self.rc.get(0xBC, 0) & 0xFFFF) | ((0x12 << 16) if self.link_up() else 0)
        if off == k["MDIO_WR"]:
            return self.rc.get(off, 0) & 0x7FFFFFFF
        if k["EXT_CFG_DATA"] <= off < k["EXT_CFG_DATA"] + 0x1000:
            if not self.link_up():
                self.faults.append("config read below the root with the link down (a CPU abort on silicon)")
                return 0xFFFFFFFF
            self.cfg_below_root += 1
            bus, dev = (self.cfg_index >> 20) & 0xFF, (self.cfg_index >> 15) & 0x1F
            if bus == 1 and dev == 0 and ((self.cfg_index >> 12) & 7) == 0:
                return self.ep.cfg_read(off - k["EXT_CFG_DATA"])
            return 0xFFFFFFFF
        return self.rc.get(off, 0)

    def rc_write(self, off, v):
        k = self.k
        self.events.append((self.tick(), off, v))
        if off == k["PCIE_CTRL"]:
            if (v & k["PERSTB"]) and not (self.rc.get(off, 0) & k["PERSTB"]):
                self.perst_released_at = self.tick()
            if not (v & k["PERSTB"]):
                self.perst_released_at = None
        if off == k["MDIO_WR"]:
            self.mdio.append((self.rc.get(k["MDIO_ADDR"], 0) & 0xFFFF, v & 0xFFFF))
        if off == k["EXT_CFG_INDEX"]:
            self.cfg_index = v
        if k["EXT_CFG_DATA"] <= off < k["EXT_CFG_DATA"] + 0x1000:
            if not self.link_up():
                self.faults.append("config write below the root with the link down")
                return
            bus, dev = (self.cfg_index >> 20) & 0xFF, (self.cfg_index >> 15) & 0x1F
            if bus == 1 and dev == 0:
                self.ep.cfg_write(off - k["EXT_CFG_DATA"], v)
            return
        self.rc[off] = v

    # -- translation, from the registers the image wrote -------------------
    def outbound(self, cpu):
        k = self.k
        bl = self.rc.get(k["WIN0_BASE_LIMIT"], 0)
        base_mb = ((self.rc.get(k["WIN0_BASE_HI"], 0) & 0xFF) << 12) | ((bl >> 4) & 0xFFF)
        lim_mb = ((self.rc.get(k["WIN0_LIMIT_HI"], 0) & 0xFF) << 12) | ((bl >> 20) & 0xFFF)
        if not (base_mb << 20 <= cpu < (lim_mb + 1) << 20):
            return None
        pci = (self.rc.get(k["WIN0_LO"], 0) | (self.rc.get(k["WIN0_HI"], 0) << 32)) + (cpu - (base_mb << 20))
        # the root port forwards only inside its memory window, with memory on
        w = self.rc.get(0x20, 0)
        if not (self.rc.get(0x04, 0) & 2):
            return None
        if not (((w & 0xFFF0) << 16) <= pci <= ((w & 0xFFF00000) | 0xFFFFF)):
            return None
        if not (self.ep.cfg[0x04] & 2):
            return None
        b = self.ep.bar()
        if not (b <= pci < b + 0x4000):
            return None
        return pci - b

    def inbound(self, bus):
        k = self.k
        lo, hi = self.rc.get(k["RC_BAR1_LO"], 0), self.rc.get(k["RC_BAR1_LO"] + 4, 0)
        code = lo & 0x1F
        size = (1 << (code + 15)) if 1 <= code <= 21 else 0
        off = (lo & 0xFFFFFFE0) | (hi << 32)
        rlo, rhi = self.rc.get(k["UBUS_BAR1"], 0), self.rc.get(k["UBUS_BAR1"] + 4, 0)
        if not size or not (rlo & 1) or not (off <= bus < off + size):
            raise SystemExit(f"endpoint DMA to bus ${bus:X} matches no inbound window")
        if not (self.ep.cfg[0x04] & 4):
            raise SystemExit("endpoint DMA with bus mastering off")
        return ((rlo & 0xFFFFF000) | (rhi << 32)) + (bus - off)

    def dma_read(self, bus, n):
        a = self.inbound(bus)
        return bytes(self.mem.get(a + i, 0) for i in range(n))

    def dma_write(self, bus, data):
        a = self.inbound(bus)
        for i, v in enumerate(data):
            self.mem[a + i] = v


def build(compiler, root, out):
    r = subprocess.run([compiler, "--compile", str(FIXTURE), "-t", "pi5", "--load-addr", hex(LOAD),
                        "--stack-addr", hex(STACK), "--entry-returns", "-o", str(out)],
                       cwd=root, env=dict(os.environ, PMF_ROOT=str(root)), text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout:
        raise SystemExit("BUILD FAILED:\n" + r.stdout[-2500:])


def run(img, k, scenario, limit=200_000_000, **kw):
    cpu = A64()
    for i, b in enumerate(img.read_bytes()):
        cpu.memory[LOAD + i] = b
    attach_symbols(cpu, img, LOAD)
    for i, v in enumerate(struct.pack("<I", scenario)):
        cpu.memory[CTL + i] = v
    for off, s in ((0x800, b"HELLO.TXT\0"), (0x840, b"NEW.TXT\0")):
        for i, v in enumerate(s):
            cpu.memory[CTL + off + i] = v
    cpu.pc, cpu.sp, cpu.x[30] = LOAD, LOADER_SP, LOADER_LR
    board = Board(k, **kw)
    board.mem = cpu.memory
    rc, rcs = k["RC"], k["RC_SIZE"]

    def mmio(addr, sz, write, value=0):
        if rc <= addr < rc + rcs:
            if sz != 4:
                raise SystemExit("non-32-bit RC access")
            off = addr - rc
            if write:
                board.rc_write(off, value & 0xFFFFFFFF)
                return None
            return board.rc_read(off)
        if k["RESCAL"] <= addr < k["RESCAL"] + 0x10:
            off = addr - k["RESCAL"]
            if write:
                if off == 0 and (value & 1) and not (board.rescal[0] & 1):
                    board.rescal_start_writes += 1
                    board.rescal_countdown = 2
                board.rescal[off] = value
                return None
            if off == 8 and board.rescal_countdown:
                board.rescal_countdown -= 1
                if board.rescal_countdown == 0:
                    board.rescal[8] = 1
            return board.rescal.get(off, 0)
        if k["RESET"] <= addr < k["RESET"] + 0x30:
            off = addr - k["RESET"]
            if write:
                bank = k["SW_INIT_BANK"] * (k["BRIDGE_ID"] >> 5)
                bit = 1 << (k["BRIDGE_ID"] & 31)
                if off == bank and value == bit:
                    board.bridge_asserted = True
                elif off == bank + 4 and value == bit:
                    if board.bridge_asserted:
                        board.bridge_cycled = True
                    board.bridge_asserted = False
                else:
                    board.reset_faults.append(f"reset controller +${off:X} <- ${value:X}")
                return None
            return 0
        if k["OUT_CPU"] <= addr < k["OUT_CPU"] + k["OUT_SIZE"]:
            off = board.outbound(addr)
            if off is None:
                if write:
                    board.faults.append(f"outbound write at ${addr:X} reached no device")
                    return None
                return 0xFFFFFFFF
            if write:
                board.ep.reg_write(off, value & 0xFFFFFFFF, board)
                return None
            return board.ep.reg_read(off)
        if addr >= 0x40000000:
            raise SystemExit(f"unmodelled MMIO {'write' if write else 'read'} at ${addr:X}")
        return False

    def load(addr, sz):
        cpu.align_guard(addr, sz, False)
        if addr >= 0x40000000:
            return mmio(addr, sz, False)
        return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(sz))

    def store(addr, value, sz):
        cpu.align_guard(addr, sz, True)
        if addr >= 0x40000000:
            mmio(addr, sz, True, value)
            return
        for i in range(sz):
            cpu.memory[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load, cpu.store = load, store
    plain = A64.step.__get__(cpu)

    def step():
        board.steps += 1
        ins = load(cpu.pc, 4)
        if (ins & 0xFFFFFFE0) == 0xD53BE000:
            cpu.x[ins & 31] = CNTFRQ
            cpu.pc += 4
            return
        if (ins & 0xFFFFFFE0) == 0xD53BE020:
            cpu.x[ins & 31] = board.tick()
            cpu.pc += 4
            return
        plain()

    n = 0
    try:
        while cpu.pc != LOADER_LR:
            n += 1
            if n > limit:
                raise SystemExit("the fixture never returned")
            step()
    except AlignmentFault as f:
        raise SystemExit(f.message())
    out = [struct.unpack_from("<I", bytes(cpu.memory.get(OUT + 4 * j + i, 0) for i in range(4)))[0]
           for j in range(19)]
    out = [v - (1 << 32) if v & 0x80000000 else v for v in out]
    return board, out, cpu.memory


class Checks:
    def __init__(self, verbose):
        self.bad, self.n, self.verbose = [], 0, verbose

    def __call__(self, cond, msg):
        self.n += 1
        if not cond:
            self.bad.append(msg)
        elif self.verbose:
            print("    ok  " + msg)


def check_bringup(ck, tag, b, k):
    rc = b.rc
    ck(not b.reset_faults, f"{tag}: only <&bcm_reset {k['BRIDGE_ID']}> moved {b.reset_faults}")
    ck(b.bridge_cycled, f"{tag}: the bridge went through reset (assert, then deassert)")
    ck(rc.get(k["RC_BAR1_LO"]) == ((k["DMA_BUS"] & 0xFFFFFFE0) | 21) and rc.get(k["RC_BAR1_LO"] + 4) == k["DMA_BUS"] >> 32
       and rc.get(k["UBUS_BAR1"]) == 1 and rc.get(k["UBUS_BAR1"] + 4) == 0,
       f"{tag}: inbound window 1 = PCIe ${k['DMA_BUS']:X} -> CPU 0, 64 GiB")
    cpu_mb, lim_mb = k["OUT_CPU"] >> 20, (k["OUT_CPU"] + k["OUT_SIZE"] - 1) >> 20
    ck(rc.get(k["WIN0_LO"]) == k["OUT_BUS"] and rc.get(k["WIN0_HI"]) == 0
       and rc.get(k["WIN0_BASE_LIMIT"]) == (((cpu_mb & 0xFFF) << 4) | ((lim_mb & 0xFFF) << 20))
       and rc.get(k["WIN0_BASE_HI"]) == cpu_mb >> 12 and rc.get(k["WIN0_LIMIT_HI"]) == lim_mb >> 12,
       f"{tag}: outbound window 0 = CPU ${k['OUT_CPU']:X} -> PCIe ${k['OUT_BUS']:X}, ${k['OUT_SIZE']:X}")
    mc = rc.get(k["MISC_CTRL"], 0)
    ck((mc & 0x1000) and (mc & 0x2000) and ((mc >> 20) & 3) == 2 and (mc & 0x400) and (mc & 0x80),
       f"{tag}: MISC_CTRL SCB access, UR mode, 512-byte burst, RCB MPS/64B (${mc:08X})")
    ck(b.mdio[:8] == k["MDIO_TABLE"], f"{tag}: the MDIO 54 MHz refclk table {b.mdio[:8]}")
    ev = b.events
    perst_rel = [i for i, (t, off, v) in enumerate(ev) if off == k["PCIE_CTRL"] and v & k["PERSTB"]]
    perst_as = [i for i, (t, off, v) in enumerate(ev) if off == k["PCIE_CTRL"] and not v & k["PERSTB"]]
    win = [i for i, (t, off, v) in enumerate(ev) if off in (k["RC_BAR1_LO"], k["WIN0_LO"])]
    mdio = [i for i, (t, off, v) in enumerate(ev) if off == k["MDIO_WR"]]
    ck(bool(perst_rel) and bool(perst_as) and perst_as[0] < min(win) and max(win + mdio) < perst_rel[0],
       f"{tag}: PERST# asserted first, windows and MDIO programmed, then released")


def gate(img, k, verbose, quick=False):
    ck = Checks(verbose)
    for shift in ((9,) if quick else (9, 12)):
        tag = f"{1 << shift}-byte namespace"
        b, o, mem = run(img, k, 1, lba_shift=shift)
        ck(o[12] == DONE, f"{tag}: the fixture ran to its end {o}")
        ck(o[0] == 1 and o[2] == 1 and o[3] == 0x010802, f"{tag}: pcie1 up, one NVMe endpoint (class ${o[3]:06X})")
        ck(o[4] == 1 and o[6] == 1 << shift and o[7] == (PART_LBA + PART_SECTORS),
           f"{tag}: NvmeAttach 1, LBA {o[6]}, {o[7]} blocks of 512 (err {o[5]})")
        check_bringup(ck, tag, b, k)
        ck(o[8] != 0, f"{tag}: partition 1 mounted through the seam (fs error {o[11]})")
        got = bytes(mem.get(BUF + i, 0) for i in range(len(HELLO)))
        ck(o[9] == len(HELLO) and got == HELLO,
           f"{tag}: HELLO.TXT read back byte for byte ({o[9]} bytes, open {o[13]}, size {o[14]})")
        new = find_file(b.disk, b.fatsz, b.data0, b"NEW     TXT")
        ck(o[10] == 1 and new == HELLO[:64], f"{tag}: NEW.TXT written and found on the disk ({o[10]}, {new!r})")
        ck(("flush", 0) in [("flush", op) for q, op in b.ep.log if q == 1], f"{tag}: an NVMe Flush was issued")
        ck(not b.faults and not b.ep.faults, f"{tag}: model faults {b.faults + b.ep.faults}")
        big = bytes(mem.get(BIG + i, 0) for i in range(RAW_N * 512))
        want = b"".join(raw_pattern(s) for s in range(RAW_LBA, RAW_LBA + RAW_N))
        ck(o[17] == 1 and big == want, f"{tag}: a 48-block read (six pages, PRP list) byte for byte ({o[17]})")
        mbr = make_disk()[0][0]
        others = all(b.disk.get(s, bytes(512)) == bytes(512) for s in range(2, 8))
        ck(o[18] == 1 and b.disk.get(1) == want[:512] and b.disk.get(0) == mbr and others,
           f"{tag}: a one-block write at LBA 1 lands and leaves the rest of its device block alone ({o[18]})")
        ios = [op for q, op in b.ep.log if q == 1]
        ck(len(ios) > 16, f"{tag}: the I/O queue wrapped ({len(ios)} commands through a 16-deep queue)")
    # no endpoint: link never trains.
    b, o, mem = run(img, k, 2, present=False)
    ck(o[0] == 0 and o[1] == -4 and b.cfg_below_root == 0 and not b.faults,
       f"no endpoint: Pcie1Init -4, no config access below the root ({o[0]}, {o[1]})")
    # From PERST# release: the driver's 100 ms wait plus up to 100 ms of
    # polling. Each modelled instruction costs TICKS_PER_STEP ticks (4.7 us),
    # so the instructions around the waits add a little here;
    # the check is that the refusal is bounded, not a stopwatch.
    rel = [t for t, off, v in b.events if off == k["PCIE_CTRL"] and v & k["PERSTB"]]
    span = b.ms(b.tick() - rel[-1]) if rel else 1e9
    ck(200 <= span < 500, f"no endpoint: refused {span:.0f} ms after PERST# release (100 + 100 ms of waits)")
    # Controller Fatal Status on enable.
    b, o, mem = run(img, k, 2, fatal=True)
    ck(o[4] == 0 and o[5] == 8 and b.ep.admin_after_fatal == 0 and not [1 for q, op in b.ep.log],
       f"fatal: NvmeAttach refused with #NVME_ERR_FATAL, no admin command ({o[4]}, {o[5]})")
    if not quick:
        b, o, mem = run(img, k, 2, rescal_done=True)
        ck(o[4] == 1 and b.rescal_start_writes == 0, "rescal already calibrated: START never written, attach ok")
        b, o, mem = run(img, k, 2)
        ck(b.rescal_start_writes == 1, "cold rescal: START written once")
    return ck


def _once(t, old, new):
    if t.count(old) != 1:
        raise SystemExit(f"mutant anchor not unique: {old!r} ({t.count(old)})")
    return t.replace(old, new)


MUTANTS = [
    (PCIE, "bridge reset id 44 (pcie2's)",
     lambda t: _once(t, "#PCIE1_BRIDGE_ID = 43", "#PCIE1_BRIDGE_ID = 44")),
    (PCIE, "inbound size code 20 (32 GiB)",
     lambda t: _once(t, "(#PCIE1_DMA_BUS & $FFFFFFE0) | 21)", "(#PCIE1_DMA_BUS & $FFFFFFE0) | 20)")),
    (PCIE, "SerDes IDDQ left on",
     lambda t: _once(t, "    pcie1_Mod(#PCIE_B_HARD_DEBUG, #PCIE_B_SERDES_IDDQ, 0)\n", "")),
    (PCIE, "outbound limit one MiB short",
     lambda t: _once(t, "limMb = (#PCIE1_OUT_CPU + #PCIE1_OUT_SIZE - 1) / $100000",
                     "limMb = (#PCIE1_OUT_CPU + #PCIE1_OUT_SIZE - 1) / $100000 - 1")),
    (PCIE, "PERST# released before the MDIO table",
     lambda t: _once(t, "    ; --- post_setup_bcm2712 -----------------------------------------------\n",
                     "    pcie1_Mod(#PCIE_B_PCIE_CTRL, 0, #PCIE_B_PERSTB)\n")),
    (NVME, "completion phase never flipped",
     lambda t: _once(t, "    phase = phase ! 1\n", "")),
    (NVME, "I/O CQ head rung on the SQ doorbell",
     lambda t: _once(t, "nvme_Wr(#NVME_REG_DBS + (3 * nvme_stride), head)", "nvme_Wr(#NVME_REG_DBS + (2 * nvme_stride), head)")),
    (NVME, "CC without IOCQES",
     lambda t: _once(t, "nvme_Wr(#NVME_REG_CC, #NVME_CC_IOCQES | #NVME_CC_IOSQES | #NVME_CC_ENABLE)",
                     "nvme_Wr(#NVME_REG_CC, #NVME_CC_IOSQES | #NVME_CC_ENABLE)")),
    (NVME, "CFS ignored while waiting",
     lambda t: _once(t, "    If (s & #NVME_CSTS_CFS) <> 0\n      ProcedureReturn nvme_Fail(#NVME_ERR_FATAL)\n    EndIf\n    If (s & mask) = want",
                     "    If (s & mask) = want")),
    (NVME, "PRP2 used as page 1 when a PRP list is needed",
     lambda t: _once(t, "    nvme_PutQ(sqe + 32, nvme_Bus(nvme_arena + #NVME_PRP_LIST))",
                     "    nvme_PutQ(sqe + 32, nvme_Bus(bounce + #NVME_PAGE))")),
    (NVME, "4 KiB edges written without read-modify-write",
     lambda t: _once(t, "    If writing = 0 Or edge <> 0\n", "    If writing = 0\n")),
]


def mutants(compiler, k, work):
    alive = []
    for rel, name, edit in MUTANTS:
        root = work / "m"
        if root.exists():
            shutil.rmtree(root)
        for f in MUTANT_FILES:
            (root / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / f, root / f)
        raw = (ROOT / rel).read_bytes().decode("latin-1")
        crlf = "\r\n" in raw
        text = edit(raw.replace("\r\n", "\n"))
        (root / rel).write_bytes((text.replace("\n", "\r\n") if crlf else text).encode("latin-1"))
        img = work / "m.img"
        try:
            build(compiler, root, img)
            quick = name not in ("4 KiB edges written without read-modify-write",)
            ck = gate(img, k, False, quick=quick)
            red, why = bool(ck.bad), (ck.bad[0] if ck.bad else "every check passed")
        except SystemExit as e:
            red, why = True, str(e).splitlines()[0][:150]
        print(f"  mutant {'RED  ' if red else 'ALIVE'} {name}: {why[:150]}")
        if not red:
            alive.append(name)
    return alive


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--sources", default=str(DEFAULT_SOURCES))
    ap.add_argument("--no-mutants", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    if not a.compiler:
        fail("pass --compiler or set PMF_COMPILER")
    compiler = str(resolve_compiler(a.compiler))
    src = None if a.sources == "none" else pathlib.Path(a.sources)
    if src is not None and not src.is_dir():
        src = None
    k = constants(src)
    with tempfile.TemporaryDirectory(prefix="pmf_nvme_pi5_") as td:
        work = pathlib.Path(td)
        img = work / "nvme2712.img"
        build(compiler, ROOT, img)
        ck = gate(img, k, a.verbose)
        for m in ck.bad:
            print("  FAIL " + m)
        alive = [] if a.no_mutants else mutants(compiler, k, work)
    if ck.bad or alive:
        print(f"a64_nvme_pi5_check: FAIL - {len(ck.bad)} of {ck.n} checks red, {len(alive)} mutant(s) alive")
        return 1
    print(f"a64_nvme_pi5_check: PASS - {ck.n} checks"
          + ("" if a.no_mutants else f", {len(MUTANTS)}/{len(MUTANTS)} mutants red")
          + ". Desk only: silicon owed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

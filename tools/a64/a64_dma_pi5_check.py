#!/usr/bin/env python3
"""Desk gate for the BCM2712 (Raspberry Pi 5) 40-bit branch of RaspberryPi4/Lib/dma.pi4.

SILICON OWED. Compiles RaspberryPi5/Tests/dma2712_probe.pi5 with `-t pi5`
(the SAME dma.pi4 the Pi 4 uses, taking its `CompilerIf #PMF_CHIP = 2712`
branches) and runs it on tools/a64/a64_interp.py against a modelled
BCM2712 DMA register file:

  * twelve channel slots at $1000010000 + n*$100 (the driver's rebasing,
    bcm2835-dma.c 1324-1325); channels 6-11 are 40-bit and executed as
    the driver describes them; any access to a channel other than the one
    the scenario expects to be driven is a failure
  * the engine walks the control-block chain from CB << 5, executes each
    struct bcm2711_dma40_scb into DRAM, reports completion only after a
    few polls (so the poll loop runs) by clearing CB - the driver's own
    idle test - and honours the pause / CS = PROT / DEBUG RESET abort
  * DRAM anywhere else, including $140000000 (five gigabytes), where the
    rectangles are drawn so that the top address byte in srci/dsti is
    exercised

WHAT IS ASSERTED
  fill (chained rectangle above 4 GiB) and copy (rectangle in batches from
  a small scratch block), plus contiguous fill and copy as one block each:
  every byte inside the rectangle right, every byte between rows and
  outside it untouched; each block's ti/srci/dsti/len/next exactly as the
  driver builds them (WAIT_RESP; SIZE_128, burst, INC on the destination,
  INC on the source only for a copy; next = following block >> 5, last 0);
  CB written with the first block >> 5 BEFORE CS = ACTIVE | PROT |
  WAIT_FOR_WRITES; no CB write while a chain is running; the blocks inside
  the caller's scratch.
  refusals: channel 11 (outside the pinned mask $7C0) -> #DMA_ERR_RESERVED
  and no access to it; channel 0 -> #DMA_ERR_CHANNEL; a mask narrowed to
  exclude channel 6 -> DmaInit #DMA_ERR_RESERVED with no register touched;
  a busy channel -> #DMA_ERR_BUSY; an engine that never finishes ->
  #DMA_ERR_TIMEOUT after the abort sequence (pause, drain, PROT, RESET).
  MUTANTS (unless --no-mutants): edits of the 2712 branch; each must go red.

The numbers the model checks against are pinned below with file and line
and re-derived from the vault's "Raspberry Pi 5" folder when it is present.

Run from PowerShell:
  $env:PMF_ALLOW_UNTRACKED_COMPILER = 1
  py -3 -B tools/a64/a64_dma_pi5_check.py --compiler <PureMetalForge.exe>
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = ROOT / "tools" / "a64"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "RaspberryPi5" / "Boot"))
from a64_interp import A64, AlignmentFault, attach_symbols  # noqa: E402
from pmf_compiler import resolve_compiler  # noqa: E402

FIXTURE = pathlib.PurePosixPath("RaspberryPi5/Tests/dma2712_probe.pi5")
LIBRARY = pathlib.PurePosixPath("RaspberryPi4/Lib/dma.pi4")
MUTANT_FILES = (FIXTURE, LIBRARY,
                pathlib.PurePosixPath("RaspberryPi4/Intrinsics/bcm2711_hardware.def"))
DEFAULT_SOURCES = pathlib.Path(r"C:\Users\ajtaj\Desktop\CompilerEmbedded\Raspberry Pi 5")

LOAD, STACK = 0x00400000, 0x03000000
LOADER_SP, LOADER_LR = 0x00100000, 0xDEADBEE0
CTL, OUT, DONE = 0x00E00000, 0x00E00100, 0x600DF00D
SCR, SRC, WIN, WIN_SIZE = 0x00800000, 0x00A00000, 0x140000000, 0x100000
CNTFRQ = 54_000_000                       # TF-A rpi5_bl31_setup.c 118-126
TICKS_PER_STEP = 4096                     # a knob; every wait is a deadline
POLLS_TO_FINISH = 6                       # more than any CS-only test would wait

LINUX = "raspberrypi/linux 7e030b60 "
PINNED = {
    "CHAN0_PHYS": (0x1000010000, "bcm2712-ds.dtsi 307-309 + bcm2835-dma.c 1324-1325"),
    "CHAN_SIZE": (0x100, LINUX + "bcm2835-dma.c 216"),
    "CHAN_40BIT": (0xFC0, LINUX + "bcm2835-dma.c 334-336"),
    "MASK40_DTB": (0x7C0, "pinned firmware DTBs dma@10600 brcm,dma-channel-mask"),
    "MASK32_DTB": (0x3F, "pinned firmware DTBs dma@10000 brcm,dma-channel-mask"),
    "CS": (0x00, LINUX + "bcm2835-dma.c 225"), "CB": (0x04, "226"),
    "DEBUG": (0x0C, "227"),
    "ACTIVE": (1 << 0, "237"), "END": (1 << 1, "238"), "INT": (1 << 2, "239"),
    "WAITING": (1 << 7, "244"), "PROT": (0x300, "246"), "ERR": (1 << 10, "247"),
    "TRANSACTIONS": (1 << 25, "250"), "WAIT_FOR_WRITES": (1 << 28, "251"),
    "TI_WAIT_RESP": (1 << 2, "264"), "DEBUG_RESET": (1 << 23, "285"),
    "XI_INC": (1 << 12, "299"), "XI_SIZE_128": (2 << 13, "302"),
    "XI_BURST_SHIFT": (8, "298"),
}


def fail(msg: str) -> None:
    raise SystemExit("a64_dma_pi5_check: FAIL - " + msg)


def derive(src: pathlib.Path) -> dict:
    from dtb_contract import parse, mapped_reg
    d = {}
    c = (src / "Sources" / "bcm2835-dma.c").read_text(encoding="utf-8", errors="replace")

    def df(name):
        m = re.search(r"#define\s+" + name + r"\s+(.+)", c)
        if not m:
            fail(f"{name} not in bcm2835-dma.c")
        v = m.group(1).split("/*")[0].strip()
        if re.fullmatch(r"BIT\((\d+)\)", v):
            return 1 << int(v[4:-1])
        if re.fullmatch(r"\(BIT\((\d+)\)\|BIT\((\d+)\)\)", v):
            a, b = re.findall(r"\d+", v)
            return (1 << int(a)) | (1 << int(b))
        m2 = re.fullmatch(r"\((\d+) << (\d+)\)", v)
        if m2:
            return int(m2.group(1)) << int(m2.group(2))
        return int(v, 0)
    d["CHAN_SIZE"] = df("BCM2835_DMA_CHAN_SIZE")
    for k, n in (("CS", "BCM2711_DMA40_CS"), ("CB", "BCM2711_DMA40_CB"), ("DEBUG", "BCM2711_DMA40_DEBUG"),
                 ("ACTIVE", "BCM2711_DMA40_ACTIVE"), ("END", "BCM2711_DMA40_END"), ("INT", "BCM2711_DMA40_INT"),
                 ("WAITING", "BCM2711_DMA40_WAITING_FOR_WRITES"), ("PROT", "BCM2711_DMA40_PROT"),
                 ("ERR", "BCM2711_DMA40_ERR"), ("TRANSACTIONS", "BCM2711_DMA40_TRANSACTIONS"),
                 ("WAIT_FOR_WRITES", "BCM2711_DMA40_WAIT_FOR_WRITES"), ("TI_WAIT_RESP", "BCM2711_DMA40_WAIT_RESP"),
                 ("DEBUG_RESET", "BCM2711_DMA40_DEBUG_RESET"), ("XI_INC", "BCM2711_DMA40_INC"),
                 ("XI_SIZE_128", "BCM2711_DMA40_SIZE_128")):
        d[k] = df(n)
    d["XI_BURST_SHIFT"] = 8 if "#define BCM2711_DMA40_BURST_LEN(x)\t(((x) & 15) << 8)" in c else -1
    m = re.search(r"bcm2712_dma_cfg = \{\s*\.chan_40bit_mask = ([^;]*?),\s*\.dma_mask", c, re.S)
    d["CHAN_40BIT"] = sum(1 << int(x) for x in re.findall(r"BIT\((\d+)\)", m.group(1))) if m else -1
    if "chan_start = ((u32)(uintptr_t)base / BCM2835_DMA_CHAN_SIZE) & 0xf;" not in c:
        fail("the driver's channel rebasing line moved")
    for name in ("bcm2712-rpi-5-b.dtb", "bcm2712-d-rpi-5-b.dtb", "bcm2712d0-rpi-5-b.dtb"):
        n = parse((src / "Boot staging" / name).read_bytes())
        base0 = mapped_reg(n, "/axi/dma@10000")
        base6 = mapped_reg(n, "/axi/dma@10600")
        found = {"CHAN0_PHYS": base0,
                 "MASK32_DTB": int.from_bytes(n["/axi/dma@10000"]["brcm,dma-channel-mask"], "big"),
                 "MASK40_DTB": int.from_bytes(n["/axi/dma@10600"]["brcm,dma-channel-mask"], "big")}
        if base6 - ((base6 // 0x100) & 0xF) * 0x100 != base0:
            fail(f"{name}: dma@10600 does not rebase onto dma@10000's channel 0")
        for k2, v in found.items():
            if k2 in d and d[k2] != v:
                fail(f"the pinned DTBs disagree about {k2}")
            d[k2] = v
    return d


def constants(src):
    k = {n: v for n, (v, _w) in PINNED.items()}
    if src is None:
        print("  SOURCES NOT CROSS-CHECKED - running on the PINNED table only")
        return k
    got = derive(src)
    for n, (v, w) in PINNED.items():
        if got.get(n) != v:
            fail(f"PINNED {n} = {v!r} but the sources say {got.get(n)!r} ({w})")
    print(f"  sources: {len(PINNED)} pinned values re-derived from {src} - all agree")
    return k


def codes(text: str) -> dict:
    return {m.group(1): int(m.group(2)) for m in
            re.finditer(r"^#(DMA_ERR_\w+)\s*=\s*(-?\d+)", text, re.M)}


# =====================================================================
#  THE MODEL
# =====================================================================
class Engine:
    def __init__(self, k, ch, hang=False, busy=False):
        self.k, self.ch, self.hang = k, ch, hang
        self.cs, self.cb, self.debug = 0, (0x123 if busy else 0), 0
        self.running = False
        self.polls = 0
        self.paused = False
        self.events = []          # ("cb", value) / ("cs", value) / ("debug", value)
        self.chains = []          # list of lists of decoded blocks
        self.faults = []

    def write(self, off, v, mem, board):
        k = self.k
        if off == k["CB"]:
            if self.running:
                self.faults.append("CB written while a chain was still running")
            self.cb = v
            self.events.append(("cb", v))
        elif off == k["CS"]:
            self.events.append(("cs", v))
            # END/INT are write-1-to-clear; ACTIVE, TRANSACTIONS, ERR and
            # the other status bits are not stored from a write (the
            # driver's own pause writes CS back with them set, 691-692).
            w1c = v & (k["END"] | k["INT"])
            writable = k["PROT"] | k["WAIT_FOR_WRITES"] | (0xFF << 16) | (1 << 29)
            self.cs = (self.cs & (k["END"] | k["INT"]) & ~w1c) | (v & writable)
            if v & k["ACTIVE"]:
                if self.running:
                    self.faults.append("ACTIVE written while running")
                if self.cb == 0:
                    self.faults.append("ACTIVE with CB zero")
                    return
                self.chains.append(self.execute(mem, board))
                self.running, self.polls, self.paused = True, 0, False
            elif self.running:
                self.paused = True
        elif off == k["DEBUG"]:
            self.events.append(("debug", v))
            if v & k["DEBUG_RESET"]:
                self.cb, self.cs, self.running, self.paused = 0, 0, False, False
        else:
            self.faults.append(f"write to +${off:X}")

    def read(self, off):
        k = self.k
        if off == k["CS"]:
            if self.running and not self.paused and not self.hang:
                self.polls += 1
                if self.polls >= POLLS_TO_FINISH:
                    self.running, self.cb = False, 0
                    self.cs |= k["END"]
            v = self.cs
            if self.running:
                v |= k["ACTIVE"]
                # TRANSACTIONS is momentary: seen on the first poll only.
                # A library that trusts CS alone for "done" is caught; the
                # driver's own test is CB zero (681-686, 815).
                if not self.paused and self.polls <= 1:
                    v |= k["TRANSACTIONS"]
            return v
        if off == k["CB"]:
            return self.cb
        if off == k["DEBUG"]:
            return self.debug
        self.faults.append(f"read of +${off:X}")
        return 0

    def execute(self, mem, board):
        k = self.k
        blocks = []
        addr = (self.cb << 5)
        for _ in range(100000):
            w = [sum(mem.get(addr + 4 * j + i, 0) << (8 * i) for i in range(4)) for j in range(8)]
            ti, src_lo, srci, dst_lo, dsti, ln, nxt, rsvd = w
            src = src_lo | ((srci & 0xFF) << 32)
            dst = dst_lo | ((dsti & 0xFF) << 32)
            blocks.append(dict(addr=addr, ti=ti, srci=srci, dsti=dsti, src=src, dst=dst, len=ln,
                               next=nxt, rsvd=rsvd))
            burst = (srci >> k["XI_BURST_SHIFT"]) & 15
            if srci & k["XI_INC"]:
                for i in range(ln):
                    board.write_byte(dst + i, mem.get(src + i, 0))
            else:
                period = max(1, burst) * (16 if (srci & (3 << 13)) == k["XI_SIZE_128"] else 4)
                for i in range(ln):
                    board.write_byte(dst + i, mem.get(src + (i % period), 0))
            if nxt == 0:
                break
            addr = nxt << 5
        return blocks


class Board:
    def __init__(self, k, active_ch, hang=False, busy=False):
        self.k = k
        self.engines = {ch: Engine(k, ch, hang=hang, busy=busy and ch == active_ch) for ch in range(12)}
        self.touched = set()
        self.reg_writes = set()
        self.written = {}
        self.steps = 0
        self.mem = None

    def write_byte(self, a, v):
        self.written[a] = v
        self.mem[a] = v


def build(compiler, root, out):
    r = subprocess.run([compiler, "--compile", str(FIXTURE), "-t", "pi5", "--load-addr", hex(LOAD),
                        "--stack-addr", hex(STACK), "--entry-returns", "-o", str(out)],
                       cwd=root, env=dict(os.environ, PMF_ROOT=str(root)), text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout or "BCM2712" not in r.stdout:
        raise SystemExit("BUILD FAILED:\n" + r.stdout[-2500:])


def seed(mem):
    for a in range(WIN, WIN + 0x10000):       # the part the scenarios draw in
        mem[a] = 0x3C
    for i in range(16384):
        mem[SRC + i] = (i * 7 + 3) & 0xFF


def run(img, k, scenario, scratch, active_ch=6, hang=False, busy=False, limit=40_000_000):
    cpu = A64()
    for i, b in enumerate(img.read_bytes()):
        cpu.memory[LOAD + i] = b
    attach_symbols(cpu, img, LOAD)
    seed(cpu.memory)
    for off, v in ((0, scenario), (4, scratch)):
        for i in range(4):
            cpu.memory[CTL + off + i] = (v >> (8 * i)) & 0xFF
    cpu.pc, cpu.sp, cpu.x[30] = LOAD, LOADER_SP, LOADER_LR
    board = Board(k, active_ch, hang, busy)
    board.mem = cpu.memory
    base, size = k["CHAN0_PHYS"], k["CHAN_SIZE"]

    def dev(addr):
        if base <= addr < base + 12 * size:
            return (addr - base) // size, (addr - base) % size
        if 0xFC000000 <= addr < 0x100000000 or addr >= 0x1000000000:
            raise SystemExit(f"unmodelled MMIO access at ${addr:X}")
        return None, 0

    def load(addr, sz):
        cpu.align_guard(addr, sz, False)
        ch, off = dev(addr)
        if ch is not None:
            if sz != 4:
                raise SystemExit(f"{sz}-byte DMA register read")
            board.touched.add(ch)
            return board.engines[ch].read(off)
        return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(sz))

    def store(addr, value, sz):
        cpu.align_guard(addr, sz, True)
        ch, off = dev(addr)
        if ch is not None:
            if sz != 4:
                raise SystemExit(f"{sz}-byte DMA register write")
            board.touched.add(ch)
            board.reg_writes.add(ch)
            board.engines[ch].write(off, value & 0xFFFFFFFF, cpu.memory, board)
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
            cpu.x[ins & 31] = board.steps * TICKS_PER_STEP
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
    out = [sum(cpu.memory.get(OUT + 4 * j + i, 0) << (8 * i) for i in range(4)) for j in range(11)]
    out = [v - (1 << 32) if v & 0x80000000 else v for v in out]
    return board, out, cpu.memory


# =====================================================================
#  THE ASSERTIONS
# =====================================================================
class Checks:
    def __init__(self, verbose):
        self.bad, self.n, self.verbose = [], 0, verbose

    def __call__(self, cond, msg):
        self.n += 1
        if not cond:
            self.bad.append(msg)
        elif self.verbose:
            print("    ok  " + msg)


def check_blocks(ck, tag, eng, k, rows, row_bytes, src_inc, scratch, burst=8):
    blocks = [b for chain in eng.chains for b in chain]
    ck(len(blocks) == rows, f"{tag}: {len(blocks)} control blocks, want {rows}")
    xi = k["XI_SIZE_128"] | (burst << k["XI_BURST_SHIFT"])
    for chain in eng.chains:
        for i, b in enumerate(chain):
            want_next = (chain[i + 1]["addr"] >> 5) if i + 1 < len(chain) else 0
            ok = (b["ti"] == k["TI_WAIT_RESP"] and b["len"] == row_bytes and b["rsvd"] == 0
                  and (b["srci"] & ~0xFF) == (xi | (k["XI_INC"] if src_inc else 0))
                  and (b["dsti"] & ~0xFF) == (xi | k["XI_INC"])
                  and b["next"] == want_next and SCR <= b["addr"] < SCR + scratch)
            if not ok:
                ck(False, f"{tag}: block at ${b['addr']:X} is {b}")
                return
    ck(True, f"{tag}: every block's ti/srci/dsti/len/next is the driver's")
    # CB before ACTIVE, CS flags.
    ev = eng.events
    starts = [i for i, (kind, v) in enumerate(ev) if kind == "cs" and v & k["ACTIVE"]]
    good = bool(starts)
    for s in starts:
        cbw = [v for kind, v in ev[:s] if kind == "cb"]
        good = good and bool(cbw) and cbw[-1] != 0 and \
            ev[s][1] == (k["ACTIVE"] | k["PROT"] | k["WAIT_FOR_WRITES"])
    ck(good, f"{tag}: CB = block >> 5 written before CS = ACTIVE|PROT|WAIT_FOR_WRITES ({len(starts)} starts)")
    ck(not eng.faults, f"{tag}: engine faults {eng.faults}")
    ck(not eng.running, f"{tag}: the engine had finished when the library said it had")


def check_rect(ck, tag, board, mem, dst, pitch, row_bytes, rows, expect):
    bad = None
    inside = set()
    for r in range(rows):
        for i in range(row_bytes):
            a = dst + r * pitch + i
            inside.add(a)
            if mem.get(a) != expect(r, i):
                bad = (r, i, mem.get(a), expect(r, i))
                break
        if bad:
            break
    ck(bad is None, f"{tag}: every byte of the rectangle is right {bad or ''}")
    stray = [a for a in board.written if a not in inside]
    ck(not stray, f"{tag}: nothing written outside the rectangle ({len(stray)} bytes)")
    ck(all(WIN <= a < WIN + WIN_SIZE for a in board.written), f"{tag}: every write inside the window")


def gate(img, k, cd, verbose, quick=False):
    ck = Checks(verbose)
    # 1: chained fill, destination above 4 GiB.
    b, o, mem = run(img, k, 1, 4096)
    ck(o[9] == DONE and o[3] == 1 and o[4] == 1, f"fill: init and fill returned 1 ({o})")
    ck(o[7] == 1 + (4096 - 512) // 32, f"fill: chain capacity {o[7]}")
    check_blocks(ck, "fill", b.engines[6], k, 20, 256, False, 4096)
    ck(all((blk["dsti"] & 0xFF) == 1 for c in b.engines[6].chains for blk in c),
       "fill: the top address byte (1, for $1_40000100) is in dsti")
    pat = (0x11223344).to_bytes(4, "little")
    check_rect(ck, "fill", b, mem, WIN + 0x100, 1024, 256, 20, lambda r, i: pat[i % 4])
    ck(b.touched == {6}, f"fill: only channel 6 touched {sorted(b.touched)}")
    # 2: copy in batches of 4 (scratch 608 bytes).
    b, o, mem = run(img, k, 2, 608)
    ck(o[3] == 1 and o[4] == 1, f"copy: init and copy returned 1 ({o})")
    ck([len(c) for c in b.engines[6].chains] == [4, 4, 2], f"copy: batches {[len(c) for c in b.engines[6].chains]}")
    check_blocks(ck, "copy", b.engines[6], k, 10, 300, True, 608)
    check_rect(ck, "copy", b, mem, WIN + 0x40, 2048, 300, 10,
               lambda r, i: ((r * 1536 + i) * 7 + 3) & 0xFF)
    if quick:
        return ck
    # 3/4: contiguous - one block each.
    b, o, mem = run(img, k, 3, 512)
    ck(o[4] == 1 and o[6] == 1 and len(b.engines[6].chains) == 1, f"contiguous copy: one block ({o})")
    check_rect(ck, "contiguous copy", b, mem, WIN, 8192, 8192, 1, lambda r, i: (i * 7 + 3) & 0xFF)
    b, o, mem = run(img, k, 4, 512)
    ck(o[4] == 1 and o[6] == 1, f"contiguous fill: one block ({o})")
    pat = (0xA5A55A5A).to_bytes(4, "little")
    check_rect(ck, "contiguous fill", b, mem, WIN, 256, 256, 16, lambda r, i: pat[i % 4])
    # 5: channel 11 is the firmware's.
    b, o, mem = run(img, k, 5, 512)
    ck(o[2] == 0 and o[10] == cd["DMA_ERR_RESERVED"] and 11 not in b.touched,
       f"channel 11: refused #DMA_ERR_RESERVED, never touched ({o[2]}, {o[10]}, {sorted(b.touched)})")
    # 6: channel 0 is a 32-bit engine.
    b, o, mem = run(img, k, 6, 512)
    ck(o[2] == 0 and o[10] == cd["DMA_ERR_CHANNEL"] and 0 not in b.touched,
       f"channel 0: refused #DMA_ERR_CHANNEL, never touched ({o[2]}, {o[10]})")
    # 7: mask narrowed after the choice.
    b, o, mem = run(img, k, 7, 512)
    ck(o[2] == 1 and o[3] == 0 and o[5] == cd["DMA_ERR_RESERVED"] and not b.reg_writes,
       f"mask $780: DmaInit refuses channel 6 with no register written ({o[3]}, {o[5]}, {sorted(b.reg_writes)})")
    # 8: the engine never finishes.
    b, o, mem = run(img, k, 8, 4096, hang=True)
    e = b.engines[6]
    kinds = [(kind, v) for kind, v in e.events]
    last_start = max(i for i, (kind, v) in enumerate(kinds) if kind == "cs" and v & k["ACTIVE"])
    tail = kinds[last_start + 1:]
    pause = next((i for i, (kind, v) in enumerate(tail) if kind == "cs" and not v & k["ACTIVE"]), None)
    prot = next((i for i, (kind, v) in enumerate(tail) if kind == "cs" and v == k["PROT"]), None)
    rst = next((i for i, (kind, v) in enumerate(tail) if kind == "debug" and v & k["DEBUG_RESET"]), None)
    ck(o[4] == 0 and o[5] == cd["DMA_ERR_TIMEOUT"], f"hang: #DMA_ERR_TIMEOUT ({o[4]}, {o[5]})")
    ck(None not in (pause, prot, rst) and pause <= prot < rst,
       f"hang: abort = pause, CS=PROT, DEBUG RESET in order ({pause}, {prot}, {rst})")
    ck(e.cb == 0 and not e.running, "hang: the channel is idle afterwards")
    # 9: busy at init.
    b, o, mem = run(img, k, 1, 4096, busy=True)
    ck(o[3] == 0 and o[5] == cd["DMA_ERR_BUSY"] and not b.engines[6].chains,
       f"busy: DmaInit #DMA_ERR_BUSY, nothing started ({o[3]}, {o[5]})")
    return ck


# =====================================================================
#  MUTANTS
# =====================================================================
def _once(t, old, new):
    if t.count(old) != 1:
        raise SystemExit(f"mutant anchor not unique: {old!r} ({t.count(old)})")
    return t.replace(old, new)


MUTANTS = [
    ("next_cb not shifted right 5",
     lambda t: _once(t, "PokeL(cb + 24, (DmaBusAddr(dma40_Slot(nextBlock)) >> 5) & $FFFFFFFF)",
                     "PokeL(cb + 24, DmaBusAddr(dma40_Slot(nextBlock)) & $FFFFFFFF)")),
    ("CB register not shifted right 5",
     lambda t: _once(t, "DmaRegWrite(#DMA40_CB, (DmaBusAddr(dma40_Slot(0)) >> 5) & $FFFFFFFF)",
                     "DmaRegWrite(#DMA40_CB, DmaBusAddr(dma40_Slot(0)) & $FFFFFFFF)")),
    ("start without PROT",
     lambda t: _once(t, "DmaRegWrite(#DMA40_CS, #DMA40_CS_ACTIVE | #DMA40_CS_PROT | #DMA40_CS_WAIT_WRITES)",
                     "DmaRegWrite(#DMA40_CS, #DMA40_CS_ACTIVE | #DMA40_CS_WAIT_WRITES)")),
    ("top address byte dropped from dsti",
     lambda t: _once(t, "PokeL(cb + 16, ((dstBus >> 32) & $FF) | xi | #DMA40_XI_INC)",
                     "PokeL(cb + 16, xi | #DMA40_XI_INC)")),
    ("fill source incremented",
     lambda t: _once(t, "ProcedureReturn dma40_Rect(DmaBusAddr(dst), pitch, DmaBusAddr(p), 0, 0, rowBytes, rows)",
                     "ProcedureReturn dma40_Rect(DmaBusAddr(dst), pitch, DmaBusAddr(p), 0, 1, rowBytes, rows)")),
    ("channel mask not checked",
     lambda t: _once(t, "  If ((dma_mask40 >> ch) & 1) = 0\n    dma_err = #DMA_ERR_RESERVED\n",
                     "  If 0\n    dma_err = #DMA_ERR_RESERVED\n")),
    ("idle test ignores CB (ACTIVE-style completion)",
     lambda t: _once(t, "  If DmaRegRead(#DMA40_CB) <> 0 : ProcedureReturn 0 : EndIf\n", "")),
    ("abort resets before the drain",
     lambda t: _once(t, "  DmaRegWrite(#DMA40_CS, #DMA40_CS_PROT)\n  DmaRegWrite(#DMA40_DEBUG, DmaRegRead(#DMA40_DEBUG) | #DMA40_DEBUG_RESET)\n",
                     "  DmaRegWrite(#DMA40_DEBUG, DmaRegRead(#DMA40_DEBUG) | #DMA40_DEBUG_RESET)\n  DmaRegWrite(#DMA40_CS, #DMA40_CS_PROT)\n")),
]


def mutants(compiler, k, cd, work):
    raw = (ROOT / LIBRARY).read_bytes().decode("latin-1")
    crlf = "\r\n" in raw
    lib = raw.replace("\r\n", "\n")
    alive = []
    for name, edit in MUTANTS:
        root = work / "m"
        if root.exists():
            shutil.rmtree(root)
        for rel in MUTANT_FILES:
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, root / rel)
        text = edit(lib)
        (root / LIBRARY).write_bytes((text.replace("\n", "\r\n") if crlf else text).encode("latin-1"))
        img = work / "m.img"
        try:
            build(compiler, root, img)
            ck = gate(img, k, cd, False, quick=name not in (
                "channel mask not checked", "abort resets before the drain"))
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
    cd = codes((ROOT / LIBRARY).read_text(encoding="latin-1"))
    for need in ("DMA_ERR_RESERVED", "DMA_ERR_CHANNEL", "DMA_ERR_TIMEOUT", "DMA_ERR_BUSY"):
        if need not in cd:
            fail(f"#{need} not declared in {LIBRARY}")
    with tempfile.TemporaryDirectory(prefix="pmf_dma_pi5_") as td:
        work = pathlib.Path(td)
        img = work / "dma2712.img"
        build(compiler, ROOT, img)
        ck = gate(img, k, cd, a.verbose)
        for m in ck.bad:
            print("  FAIL " + m)
        alive = [] if a.no_mutants else mutants(compiler, k, cd, work)
    if ck.bad or alive:
        print(f"a64_dma_pi5_check: FAIL - {len(ck.bad)} of {ck.n} checks red, {len(alive)} mutant(s) alive")
        return 1
    print(f"a64_dma_pi5_check: PASS - {ck.n} checks"
          + ("" if a.no_mutants else f", {len(MUTANTS)}/{len(MUTANTS)} mutants red")
          + ". Desk only: silicon owed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

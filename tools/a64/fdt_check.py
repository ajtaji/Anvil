#!/usr/bin/env python3
"""Desk gate for Anvil/Core/fdt.pbi - the one shared device-tree reader.

Builds RaspberryPi5/Tests/fdt_gate.pi5 (-t pi5; the reader itself is
chip-free), loads each DTB into tools/a64/a64_interp.py memory, runs the
reader, and compares every answer with RaspberryPi5/Boot/dtb_contract.py -
the Python validator already used for the pinned Pi 5 trees - on:

  * the three pinned Pi 5 DTBs (vault "Raspberry Pi 5/Boot staging/"):
    UART10 $10_7D00_1000, SDIO2 $10_0110_0000, SD mmc@fff000
    $10_00FF_F000, GIC distributor and CPU interface, RP1 UART0
    $1F_0003_0000 through /aliases and TWO ranges levels (rp1 -> a PCI bus
    -> pcie@1000120000), /chosen stdout-path, /memory, the pinctrl
    compatible, #address-cells of the PCI bus, a unit-less path component,
    a missing node and a size-less child's raw reg;
  * corrupt and truncated variants, each of which dtb_contract.parse()
    must refuse and FdtCheck must refuse.

dtb_contract.mapped_reg takes one- and two-cell buses only. For the RP1 path
this gate widens the same arithmetic to N-cell integers (xlate below) and
ANCHORS the widening: on every node mapped_reg can answer, xlate must agree.

--mutate builds broken copies of fdt.pbi and demands each fails.
Run: py -3 -B tools/a64/fdt_check.py --compiler <PureMetalForge.exe> [--dtb-dir DIR] [--mutate]
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from pmf_compiler import resolve_compiler  # noqa: E402

LIB_REL = pathlib.Path("Anvil/Core/fdt.pbi")
DEF_REL = pathlib.Path("RaspberryPi4/Intrinsics/bcm2711_hardware.def")
PROBE_REL = pathlib.Path("RaspberryPi5/Tests/fdt_gate.pi5")
DEFAULT_DTB_DIR = pathlib.Path(r"C:\Users\ajtaj\Desktop\CompilerEmbedded\Raspberry Pi 5\Boot staging")
DTBS = ("bcm2712-rpi-5-b.dtb", "bcm2712-d-rpi-5-b.dtb", "bcm2712d0-rpi-5-b.dtb")

LOAD, STACK, LR = 0x400000, 0x3000000, 0xDEAD0000
DTB_AT = 0x1000000
IN, OUT = 0x5F0000, 0x5F1000
NQ = 19


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


A = _load("fdt_a64", ROOT / "tools/a64/a64_interp.py")
DC = _load("fdt_dtb_contract", ROOT / "RaspberryPi5/Boot/dtb_contract.py")


class Fail(Exception):
    pass


# ---------------------------------------------------------------- oracle
def cells(nodes, path, name, dflt):
    v = nodes[path].get(name)
    return dflt if v is None else DC._number(v)


def parent_of(path):
    return path.rsplit("/", 1)[0] or "/"


def xlate(nodes, path, index):
    """dtb_contract.mapped_reg's arithmetic on N-cell integers, any reg index."""
    par = parent_of(path)
    ac, sc = cells(nodes, par, "#address-cells", 2), cells(nodes, par, "#size-cells", 1)
    reg = nodes[path].get("reg", b"")
    w = 4 * (ac + sc)
    if not 1 <= ac <= 3 or not 1 <= sc <= 2 or len(reg) < w * (index + 1) or len(reg) % w:
        return -1
    e = reg[w * index:w * (index + 1)]
    addr, span = int.from_bytes(e[:4 * ac], "big"), int.from_bytes(e[4 * ac:], "big")
    if span == 0:
        return -1
    bus = par
    while bus != "/":
        g = parent_of(bus)
        cc, bsc, pc = cells(nodes, bus, "#address-cells", 2), cells(nodes, bus, "#size-cells", 1), cells(nodes, g, "#address-cells", 2)
        rng = nodes[bus].get("ranges")
        if rng is None:
            return -1
        if rng:
            ew = 4 * (cc + pc + bsc)
            if len(rng) % ew:
                return -1
            for o in range(0, len(rng), ew):
                en = rng[o:o + ew]
                ch = int.from_bytes(en[:4 * cc], "big")
                cpu = int.from_bytes(en[4 * cc:4 * (cc + pc)], "big")
                ln = int.from_bytes(en[4 * (cc + pc):], "big")
                if addr >= ch and span <= ln and addr - ch <= ln - span:
                    addr = cpu + addr - ch
                    break
            else:
                return -1
        bus = g
    return addr if addr < (1 << 63) else -1


def reserve_count(blob):
    rsv, off_struct = struct.unpack_from(">I", blob, 16)[0], struct.unpack_from(">I", blob, 8)[0]
    n = 0
    while rsv + 16 <= off_struct and blob[rsv:rsv + 16] != bytes(16):
        n, rsv = n + 1, rsv + 16
    return n


def compat_first(nodes, s):
    for p, props in nodes.items():
        if "compatible" in props and s in DC.strings(props["compatible"]):
            return p
    return None


def expected(blob, facts=True):
    nodes = DC.parse(blob)
    info = DC.inspect(blob)
    # anchor the widened arithmetic on everything mapped_reg answers
    for p, props in nodes.items():
        if p != "/" and "reg" in props:
            try:
                m = DC.mapped_reg(nodes, p)
            except DC.DtbError:
                continue
            if xlate(nodes, p, 0) != m:
                raise Fail(f"oracle widening disagrees with mapped_reg at {p}")
    x = lambda p, i=0: xlate(nodes, p, i) if p in nodes else -1
    mem_end = 0
    for p, props in nodes.items():
        if props.get("device_type") == b"memory\0":
            ac, sc = cells(nodes, "/", "#address-cells", 2), cells(nodes, "/", "#size-cells", 1)
            reg, w = props["reg"], 4 * (ac + sc)
            for o in range(0, len(reg), w):
                if int.from_bytes(reg[o:o + 4 * ac], "big") == 0 and not mem_end:
                    mem_end = int.from_bytes(reg[o + 4 * ac:o + w], "big")
    uart0 = DC.strings(nodes["/aliases"]["uart0"])[0]
    c0 = compat_first(nodes, "brcm,bcm2712c0-pinctrl")
    d0 = compat_first(nodes, "brcm,bcm2712d0-pinctrl")
    pin = nodes.get("/soc@107c000000/pinctrl@7d504100", {})
    want = [0,
            x("/soc@107c000000/serial@7d001000"),
            x("/axi/mmc@1100000"),
            x("/soc@107c000000/mmc@fff000"),
            x("/soc@107c000000/interrupt-controller@7fff9000", 0),
            x("/soc@107c000000/interrupt-controller@7fff9000", 1),
            x(uart0),
            info["early_uart_physical"],
            mem_end,
            x(c0) if c0 else -1,
            x(d0) if d0 else -1,
            int("compatible" in pin and "brcm,bcm2712c0-pinctrl" in DC.strings(pin["compatible"])),
            cells(nodes, "/axi/pcie@1000120000", "#address-cells", 2),
            x("/soc@107c000000/serial@7d001000"),
            -1,
            int.from_bytes(nodes["/axi/mmc@1100000/wifi@1"]["reg"], "big"),
            reserve_count(blob),
            sum(1 for p in nodes if p != "/" and p.count("/") == 1),
            sum(1 for p in nodes if p.startswith("/reserved-memory/") and p.count("/") == 2)
            if "/reserved-memory" in nodes else -1]
    if not facts:
        return want
    # the fixed facts this gate is named for, independently of the oracle
    for i, v in ((1, 0x107D001000), (2, 0x1001100000), (3, 0x1000FFF000), (4, 0x107FFF9000),
                 (5, 0x107FFFA000), (6, 0x1F00030000), (7, 0x107D001000)):
        if want[i] != v:
            raise Fail(f"oracle answer {i} is ${want[i]:X}, the pinned fact is ${v:X}")
    if want[1] != info["early_uart_physical"] or want[2] != info["wifi_sdio_physical"]:
        raise Fail("xlate disagrees with dtb_contract.inspect")
    return want


# ---------------------------------------------------------------- run
def build(root, compiler, out):
    r = subprocess.run([compiler, "--compile", str(root / PROBE_REL), "-t", "pi5", "--entry-returns",
                        "--load-addr", hex(LOAD), "--stack-addr", hex(STACK), "-o", str(out)],
                       cwd=root, env=dict(os.environ, PMF_ROOT=str(root)), capture_output=True, text=True)
    if r.returncode or not out.exists():
        raise Fail("build failed\n" + r.stdout[-1500:] + r.stderr)
    return out


STEP_LIMIT = 40_000_000     # the healthy fixture needs well under this per tree


def run(img, blob, limit=None):
    cpu = A.A64()
    mem = cpu.memory
    for i, b in enumerate(img.read_bytes()):
        mem[LOAD + i] = b
    for i, b in enumerate(blob):
        mem[DTB_AT + i] = b

    def put(a, v):
        for i in range(8):
            mem[a + i] = (v >> (8 * i)) & 0xFF
    put(IN, DTB_AT)
    put(IN + 8, len(blob) if limit is None else limit)
    base_load, base_store = cpu.load, cpu.store

    def load(a, size):
        if not (0x100000 <= a < 0x8000000):
            raise Fail(f"the reader read ${a:X}, outside the image, stack and DTB")
        if DTB_AT + len(blob) <= a < DTB_AT + len(blob) + 0x100000:
            raise Fail(f"the reader read ${a:X}, past the DTB's {len(blob)} bytes")
        return base_load(a, size)

    def store(a, v, size):
        if DTB_AT <= a < DTB_AT + len(blob) + 0x100000:
            raise Fail(f"the reader WROTE the DTB at ${a:X}")
        return base_store(a, v, size)
    cpu.load, cpu.store = load, store
    cpu.pc, cpu.sp, cpu.x[30] = LOAD, STACK, LR
    for n in range(STEP_LIMIT):
        if cpu.pc == LR:
            break
        cpu.step()
    else:
        raise Fail(f"the fixture did not return within {STEP_LIMIT} instructions")
    run.last_steps = n
    got = []
    for i in range(NQ):
        v = sum(mem.get(OUT + 8 * i + k, 0) << (8 * k) for k in range(8))
        got.append(v - (1 << 64) if v >> 63 else v)
    return got


def modified_valid(blob):
    """Valid trees with one ranges entry changed so that a translation must
    now FAIL - for the code paths the pinned trees never exercise: a PCI
    space code that differs, and a reg that overruns its window by less than
    its own length."""
    rp1 = bytes.fromhex("000000c0" "40000000" "02000000" "00000000" "00000000" "00000000" "00410000")
    # The same bytes also open rp1's dma-ranges; take the one whose property
    # header names "ranges".
    strings_at = struct.unpack_from(">I", blob, 12)[0]
    hits = []
    at = blob.find(rp1)
    while at >= 0:
        tok, ln, name = struct.unpack_from(">3I", blob, at - 12)
        end = blob.index(b"\0", strings_at + name)
        if tok == 3 and ln == len(rp1) and blob[strings_at + name:end] == b"ranges":
            hits.append(at)
        at = blob.find(rp1, at + 1)
    if len(hits) != 1:
        raise Fail(f"rp1's ranges property was found {len(hits)} times, want once")
    at = hits[0]
    io_space = bytearray(blob)
    io_space[at + 8] = 0x01                        # phys.hi space 2 (memory) -> 1 (I/O)
    short = bytearray(blob)
    short[at + 24:at + 28] = bytes.fromhex("00030080")   # UART0 0x30000+0x100 overruns it
    return [("rp1 ranges in PCI I/O space", bytes(io_space)),
            ("rp1 window ends inside UART0's reg", bytes(short))]


def corrupt_variants(blob):
    h = list(struct.unpack_from(">10I", blob))
    off_struct, off_strings, off_rsv, size_strings, size_struct = h[2], h[3], h[4], h[8], h[9]

    def hdr(i, v):
        b = bytearray(blob)
        struct.pack_into(">I", b, 4 * i, v)
        return bytes(b)

    def at(o, v):
        b = bytearray(blob)
        struct.pack_into(">I", b, o, v)
        return bytes(b)
    end_tok = off_struct + size_struct - 4
    first_prop = off_struct + 8       # root BEGIN_NODE + empty name, then the first token
    assert struct.unpack_from(">I", blob, first_prop)[0] == 3, "root's first token is not a property"
    child = blob.index(b"\x00\x00\x00\x01", first_prop)          # first child BEGIN_NODE
    bad_name = bytearray(blob)
    bad_name[child + 4] = 0xC3
    rsv_zero = bytearray(blob)
    o = off_rsv
    while o + 16 <= off_struct and blob[o:o + 16] != bytes(16):
        o += 16
    rsv_zero[o:o + 16] = b"\x11" * 16
    # FDT_END followed by four more structure bytes (one NOP): grow the
    # structure block and move everything behind it.
    end_block = off_struct + size_struct
    grown = bytearray(blob[:end_block] + struct.pack(">I", 4) + blob[end_block:])
    struct.pack_into(">I", grown, 4, len(grown))
    struct.pack_into(">I", grown, 36, size_struct + 4)
    for field in (2, 3, 4):
        v = struct.unpack_from(">I", grown, 4 * field)[0]
        if v >= end_block:
            struct.pack_into(">I", grown, 4 * field, v + 4)
    return [
        ("FDT_END not final", bytes(grown), None),
        ("bad magic", hdr(0, 0xD00DFEEE), None),
        ("totalsize past the buffer", hdr(1, len(blob) + 4), None),
        ("totalsize below the header", hdr(1, 32), None),
        ("version 16", hdr(5, 16), None),
        ("last_comp above version", hdr(6, h[5] + 1), None),
        ("structure offset inside the header", hdr(2, 8), None),
        ("structure size past the tree", hdr(9, len(blob)), None),
        ("strings size past the tree", hdr(8, len(blob)), None),
        ("reserve map at the structure", hdr(4, off_struct), None),
        ("reserve map unterminated", bytes(rsv_zero), None),
        ("strings overlapping structure", hdr(3, off_struct), None),
        ("unknown token", at(first_prop, 7), None),
        ("FDT_END replaced by NOP", at(end_tok, 4), None),
        ("FDT_END replaced by END_NODE", at(end_tok, 2), None),
        ("property length past the block", at(first_prop + 4, size_struct), None),
        ("property name offset past strings", at(first_prop + 8, size_strings), None),
        ("non-ASCII node name", bytes(bad_name), None),
        ("truncated to half", blob[:len(blob) // 2], None),
    ]


def scenarios(img, dtb_dir, first=False):
    errs = []
    base = None
    for name in DTBS:
        blob = (dtb_dir / name).read_bytes()
        base = base or blob
        want = expected(blob)
        got = run(img, blob)
        for i, (g, w) in enumerate(zip(got, want)):
            if g != w:
                errs.append(f"{name}: answer {i} is {g:#x}, dtb_contract says {w:#x}")
        if first and errs:
            return errs
        print(f"  {name}: {run.last_steps} instructions")
    for label, blob in modified_valid(base):
        want = expected(blob, facts=False)
        if want[6] != -1:
            raise Fail(f"modified '{label}': the oracle still translates UART0")
        got = run(img, blob)
        for i, (g, w) in enumerate(zip(got, want)):
            if g != w:
                errs.append(f"modified '{label}': answer {i} is {g:#x}, dtb_contract says {w:#x}")
        if first and errs:
            return errs
    for label, blob, limit in corrupt_variants(base):
        try:
            DC.parse(blob)
            errs.append(f"corrupt '{label}': dtb_contract accepted it - the variant is not corrupt")
            continue
        except DC.DtbError:
            pass
        got = run(img, blob, limit)
        if got[0] >= 0:
            errs.append(f"corrupt '{label}': FdtCheck returned {got[0]}, want a refusal")
            if first:
                return errs
    return errs


MUTANTS = [
    ("magic not checked", "  If fdt_Be32(base) <> #FDT_MAGIC\n", "  If 0\n"),
    ("version floor removed", "  If version < 17 Or lastComp > version\n", "  If lastComp > version\n"),
    ("END position not checked", "        If depth <> 0 Or at <> fdt_structEnd\n", "        If depth <> 0\n"),
    ("three-cell top ignored", "        If chHi = hi And addr >= ch", "        If addr >= ch"),
    ("ranges range check off by one", "addr - ch <= length - span", "addr - ch <= length"),
    ("unit-less match removed", "  If hasAt = 0 And PeekA(p + n) = #FDT_CH_AT\n    ProcedureReturn 1\n  EndIf\n", ""),
    ("stdout alias not followed", "  q = FdtFindNode(\"/aliases\")\n  If q = 0 : ProcedureReturn 0 : EndIf\n", "  ProcedureReturn 0\n"),
    ("sibling walk does not skip subtrees", "      If depth = 0 : ProcedureReturn at : EndIf\n      depth = depth + 1\n", "      ProcedureReturn at\n"),
    ("memory entry at zero ignored", "      If FdtRegAddress(node, k) = 0\n", "      If FdtRegAddress(node, k) = 1\n"),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compiler", required=True)
    ap.add_argument("--dtb-dir", type=pathlib.Path, default=DEFAULT_DTB_DIR)
    ap.add_argument("--mutate", action="store_true")
    ap.add_argument("--only", default=None, help="only mutants whose label contains one of these comma-separated texts")
    a = ap.parse_args()
    compiler = resolve_compiler(a.compiler)
    rc = 0
    with tempfile.TemporaryDirectory(prefix="fdt-") as td:
        td = pathlib.Path(td)
        try:
            errs = scenarios(build(ROOT, compiler, td / "fdt.img"), a.dtb_dir)
        except Fail as e:
            errs = [str(e)]
        for e in errs:
            print("FAIL", e)
        print(f"fdt_check: 3 pinned DTBs x {NQ} answers + 2 modified trees + 19 corrupt variants, {len(errs)} failure(s)")
        rc = 1 if errs else 0
        if a.mutate:
            src = (ROOT / LIB_REL).read_text(encoding="utf-8").replace("\r\n", "\n")
            killed = 0
            chosen = [m for m in MUTANTS if not a.only or any(k in m[0] for k in a.only.split(","))]
            for i, (label, old, new) in enumerate(chosen):
                if src.count(old) != 1:
                    print(f"MUTANT {label}: pattern not found once - list is stale")
                    rc = 1
                    continue
                mroot = td / f"m{i}"
                for rel in (LIB_REL, DEF_REL, PROBE_REL):
                    (mroot / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(ROOT / rel, mroot / rel)
                (mroot / LIB_REL).write_text(src.replace(old, new), encoding="utf-8")
                try:
                    merr = scenarios(build(mroot, compiler, td / f"m{i}.img"), a.dtb_dir, first=True)
                except Fail as e:
                    merr = [str(e)]
                killed += bool(merr)
                print(f"MUTANT {label}: {'killed' if merr else 'SURVIVED'}"
                      + (f" ({merr[0][:100]})" if merr else ""))
            print(f"mutants: {killed}/{len(chosen)} killed")
            if killed != len(chosen):
                rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

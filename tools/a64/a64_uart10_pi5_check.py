#!/usr/bin/env python3
"""Desk gate: the Pi 5 debug connector (BCM2712 UART10) as a second port in uart.pi4.

SILICON OWED. Builds RaspberryPi5/Tests/uart10_probe.pi5 with `-t pi5` and
runs it on tools/a64/a64_interp.py against two modelled PL011s: the header
console (RP1 UART0, $1F_0003_0000) and UART10 at the address the pinned DTBs
give serial10 ($10_7D00_1000, re-derived below). Any other MMIO is refused.

Asserted:
  adopt   Uart10Attach takes the port as the EL3 stub left it (enabled, the
          stub's divisor) and writes NO control or divisor register
  tee     with Uart10Tee(1) every console byte reaches BOTH ports, the
          header's bytes exactly as without the tee; with Uart10Tee(0) the
          header alone; Uart10WriteStr reaches UART10 alone; Uart10Read
          returns what UART10 received
  init    a port found off is brought up in the PL011 order (CR 0 first,
          divisor, LCRH latching it, CR = UARTEN|TXE|RXE last) at the DTB's
          clk-uart, 9,216,000 Hz: IBRD 5, FBRD 0 for 115200
  bound   a UART10 whose FIFO never drains costs dropped tee bytes, counted,
          and the header still receives every byte
  refuse  selecting the tee with UART10 neither attached nor initialised
          refuses and writes nothing to UART10
MUTANTS: the pre-DTB address $107C001000, the tee replacing the header write,
the TF-A clock in the cold path, the tee ignoring its switch, the tee's
bound removed.

Run from PowerShell:
  $env:PMF_ALLOW_UNTRACKED_COMPILER = 1
  py -3 -B tools/a64/a64_uart10_pi5_check.py --compiler <PureMetalForge.exe>
"""
from __future__ import annotations

import argparse
import os
import pathlib
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

FIXTURE = pathlib.PurePosixPath("RaspberryPi5/Tests/uart10_probe.pi5")
LIBRARY = pathlib.PurePosixPath("RaspberryPi4/Lib/uart.pi4")
MUTANT_FILES = (FIXTURE, LIBRARY, pathlib.PurePosixPath("Anvil/Core/console_style.pbi"),
                pathlib.PurePosixPath("RaspberryPi4/Intrinsics/bcm2711_hardware.def"))
DEFAULT_SOURCES = pathlib.Path(r"C:\Users\ajtaj\Desktop\CompilerEmbedded\Raspberry Pi 5")

LOAD, STACK, LOADER_SP, LOADER_LR = 0x00400000, 0x03000000, 0x00100000, 0xDEADBEE0
CTL, OUT, DONE = 0x00E00000, 0x00E00100, 0x600DF00D
CNTFRQ, TICKS_PER_STEP = 54_000_000, 64

PINNED = {
    "UART10": (0x107D001000, "DTB /soc@107c000000/serial@7d001000 via /soc ranges"),
    "UART10_CLK": (9216000, "DTB serial10 clocks -> /clocks/clk-uart clock-frequency"),
    "STDOUT": ("serial10:115200n8", "DTB /chosen stdout-path"),
    "HEADER": (0x1F00030000, "rp1.dtsi serial@30000 through the pcie2/&rp1 ranges (uart.pi4)"),
}
# ARM PrimeCell UART (PL011) TRM register map; the same offsets are in
# Linux include/linux/amba/serial.h (UART01x_DR 0x00, UART01x_FR 0x18,
# UART011_IBRD 0x24, _FBRD 0x28, _LCRH 0x2c, _CR 0x30, _IMSC 0x38, _ICR 0x44).
DR, FR, IBRD, FBRD, LCRH, CR, IMSC, ICR = 0x00, 0x18, 0x24, 0x28, 0x2C, 0x30, 0x38, 0x44
FR_TXFF, FR_RXFE = 0x20, 0x10
STUB_IBRD, STUB_CR, STUB_LCRH = 24, 0x301, 0x70    # armstub8-2712.asm primary_prepare


def fail(msg):
    raise SystemExit("a64_uart10_pi5_check: FAIL - " + msg)


def constants(src):
    k = {n: v for n, (v, _w) in PINNED.items()}
    if src is None:
        print("  SOURCES NOT CROSS-CHECKED - PINNED table only")
        return k
    from dtb_contract import parse, mapped_reg, strings
    for name in ("bcm2712-rpi-5-b.dtb", "bcm2712-d-rpi-5-b.dtb", "bcm2712d0-rpi-5-b.dtb"):
        n = parse((src / "Boot staging" / name).read_bytes())
        path = strings(n["/aliases"]["serial10"])[0]
        node = n[path]
        ph = int.from_bytes(node["clocks"][:4], "big")
        clk = [int.from_bytes(p["clock-frequency"], "big") for p in n.values()
               if p.get("phandle") and int.from_bytes(p["phandle"], "big") == ph]
        got = {"UART10": mapped_reg(n, path), "UART10_CLK": clk[0] if clk else -1,
               "STDOUT": strings(n["/chosen"]["stdout-path"])[0]}
        if "arm,pl011" not in strings(node["compatible"]):
            fail(f"{name}: serial10 is not a PL011")
        for key, v in got.items():
            if v != k[key]:
                fail(f"{name}: {key} is {v!r}, PINNED says {k[key]!r}")
    print(f"  sources: UART10 address, clock and stdout re-derived from the three DTBs in {src} - all agree")
    return k


class Pl011:
    def __init__(self, name, enabled, stuck=False, rx=b""):
        self.name = name
        self.regs = {CR: STUB_CR, IBRD: STUB_IBRD, FBRD: 0, LCRH: STUB_LCRH} if enabled else {CR: 0}
        self.tx = bytearray()
        self.rx = bytearray(rx)
        self.stuck = stuck
        self.writes = []                 # (off, value) other than DR

    def read(self, off):
        if off == FR:
            return (FR_TXFF if self.stuck else 0) | (0 if self.rx else FR_RXFE)
        if off == DR:
            return self.rx.pop(0) if self.rx else 0
        return self.regs.get(off, 0)

    def write(self, off, v):
        if off == DR:
            if self.stuck:
                raise SystemExit(f"{self.name}: DR written while TXFF was set")
            if not (self.regs.get(CR, 0) & 0x101) == 0x101:
                raise SystemExit(f"{self.name}: DR written with the port or its transmitter off")
            self.tx.append(v & 0xFF)
            return
        self.writes.append((off, v))
        self.regs[off] = v


def build(compiler, root, out):
    r = subprocess.run([compiler, "--compile", str(FIXTURE), "-t", "pi5", "--load-addr", hex(LOAD),
                        "--stack-addr", hex(STACK), "--entry-returns", "-o", str(out)],
                       cwd=root, env=dict(os.environ, PMF_ROOT=str(root)), text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout:
        raise SystemExit("BUILD FAILED:\n" + r.stdout[-2500:])


STRINGS = {0x800: b"tee+hdr ", 0x840: b"hdr-only ", 0x880: b"dbg-only"}


def run(img, k, scenario, u10, limit=20_000_000):
    cpu = A64()
    for i, b in enumerate(img.read_bytes()):
        cpu.memory[LOAD + i] = b
    attach_symbols(cpu, img, LOAD)
    for i, v in enumerate(struct.pack("<I", scenario)):
        cpu.memory[CTL + i] = v
    for off, s in STRINGS.items():
        for i, v in enumerate(s + b"\0"):
            cpu.memory[CTL + off + i] = v
    cpu.pc, cpu.sp, cpu.x[30] = LOAD, LOADER_SP, LOADER_LR
    hdr = Pl011("header", True)
    ports = [(k["HEADER"], hdr), (k["UART10"], u10)]
    steps = [0]

    def port(addr):
        for base, p in ports:
            if base <= addr < base + 0x1000:
                return p, addr - base
        raise SystemExit(f"unmodelled MMIO access at ${addr:X}")

    def load(addr, sz):
        cpu.align_guard(addr, sz, False)
        if addr >= 0x40000000:
            p, off = port(addr)
            return p.read(off)
        return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(sz))

    def store(addr, value, sz):
        cpu.align_guard(addr, sz, True)
        if addr >= 0x40000000:
            p, off = port(addr)
            p.write(off, value & 0xFFFFFFFF)
            return
        for i in range(sz):
            cpu.memory[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load, cpu.store = load, store
    plain = A64.step.__get__(cpu)

    def step():
        steps[0] += 1
        ins = load(cpu.pc, 4)
        if (ins & 0xFFFFFFE0) == 0xD53BE000:
            cpu.x[ins & 31] = CNTFRQ
            cpu.pc += 4
            return
        if (ins & 0xFFFFFFE0) == 0xD53BE020:
            cpu.x[ins & 31] = steps[0] * TICKS_PER_STEP
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
           for j in range(7)]
    out = [v - (1 << 32) if v & 0x80000000 else v for v in out]
    return hdr, u10, out


class Checks:
    def __init__(self, verbose):
        self.bad, self.n, self.verbose = [], 0, verbose

    def __call__(self, cond, msg):
        self.n += 1
        if not cond:
            self.bad.append(msg)
        elif self.verbose:
            print("    ok  " + msg)


def gate(img, k, verbose):
    ck = Checks(verbose)
    # 1: adopt, tee on then off, UART10-only write, a read.
    hdr, u10, o = run(img, k, 1, Pl011("UART10", True, rx=b"A"))
    ck(o[6] == DONE and o[0] == 1 and o[1] == 1, f"adopt: Uart10Attach 1, Uart10Tee(1) 1 ({o})")
    ck(bytes(hdr.tx) == b"tee+hdr hdr-only ", f"tee: the header got exactly its bytes {bytes(hdr.tx)!r}")
    ck(bytes(u10.tx) == b"tee+hdr dbg-only", f"tee: UART10 got the tee'd bytes then its own {bytes(u10.tx)!r}")
    ck(o[2] == ord("A"), f"read: Uart10Read returned {o[2]} (want {ord('A')})")
    ck(not u10.writes, f"adopt: no UART10 control/divisor register written {u10.writes}")
    ck(not hdr.writes, f"the header port's registers untouched {hdr.writes}")
    # 2: found off, cold init at the DTB clock.
    hdr, u10, o = run(img, k, 2, Pl011("UART10", False))
    t = (((k["UART10_CLK"] * 8) // 115200) + 1) // 2
    want_ibrd, want_fbrd = t >> 6, t & 63
    w = u10.writes
    offs = [off for off, v in w]
    ck(o[4] == 1 and o[5] == 1, f"init: Uart10Init 1, up ({o})")
    ck(bool(w) and w[0] == (CR, 0) and w[-1] == (CR, 0x301), f"init: CR 0 first, CR $301 last {w}")
    ck((IBRD, want_ibrd) in w and (FBRD, want_fbrd) in w,
       f"init: IBRD {want_ibrd} FBRD {want_fbrd} from {k['UART10_CLK']} Hz ({w})")
    ck(IBRD in offs and FBRD in offs and LCRH in offs and
       max(offs.index(IBRD), offs.index(FBRD)) < len(offs) - 1 - offs[::-1].index(LCRH),
       "init: LCRH written after the divisor (it latches it)")
    ck(u10.regs.get(LCRH) == 0x70, f"init: LCRH $70 (WLEN8|FEN) ({u10.regs.get(LCRH)})")
    ck(bytes(u10.tx) == b"dbg-only" and not hdr.tx, "init: UART10 write reaches UART10 only")
    # 3: UART10 stuck: dropped, counted, header complete.
    hdr, u10, o = run(img, k, 3, Pl011("UART10", True, stuck=True))
    ck(bytes(hdr.tx) == b"tee+hdr " and o[3] == len(b"tee+hdr "),
       f"bound: header complete {bytes(hdr.tx)!r}, {o[3]} tee bytes dropped and counted")
    # 4: tee refused with the port neither attached nor initialised.
    hdr, u10, o = run(img, k, 4, Pl011("UART10", False))
    ck(o[1] == 0 and o[5] == 0 and not u10.writes and not u10.tx and bytes(hdr.tx) == b"hdr-only ",
       f"refuse: Uart10Tee(1) 0, UART10 untouched, header unaffected ({o})")
    return ck


def _once(t, old, new):
    if t.count(old) != 1:
        raise SystemExit(f"mutant anchor not unique: {old!r} ({t.count(old)})")
    return t.replace(old, new)


MUTANTS = [
    ("the pre-DTB address $107C001000",
     lambda t: _once(t, "#UART10_BASE         = $107D001000", "#UART10_BASE         = $107C001000")),
    ("the tee replaces the header write",
     lambda t: _once(t, "  If uart10_tee <> 0\n    uart10_Put(c)\n  EndIf\n",
                     "  If uart10_tee <> 0\n    uart10_Put(c)\n    ProcedureReturn 1\n  EndIf\n")),
    ("the TF-A clock in the cold path",
     lambda t: _once(t, "ProcedureReturn Uart10InitClk(baud, #UART10_CLOCK_HZ_DTB)",
                     "ProcedureReturn Uart10InitClk(baud, #UART10_CLOCK_HZ_TFA)")),
    ("the tee ignores its switch",
     lambda t: _once(t, "  If uart10_tee <> 0\n    uart10_Put(c)", "  If 1\n    uart10_Put(c)")),
    ("the tee's bound removed",
     lambda t: _once(t, "      If n >= #UART10_TEE_SPINS\n", "      If n < 0\n")),
]


def mutants(compiler, k, work):
    raw = (ROOT / LIBRARY).read_bytes().decode("latin-1")
    crlf = "\r\n" in raw
    lib = raw.replace("\r\n", "\n")
    alive = []
    for name, edit in MUTANTS:
        root = work / "m"
        if root.exists():
            shutil.rmtree(root)
        for f in MUTANT_FILES:
            (root / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / f, root / f)
        text = edit(lib)
        (root / LIBRARY).write_bytes((text.replace("\n", "\r\n") if crlf else text).encode("latin-1"))
        img = work / "m.img"
        try:
            build(compiler, root, img)
            ck = gate(img, k, False)
            red, why = bool(ck.bad), (ck.bad[0] if ck.bad else "every check passed")
        except SystemExit as e:
            if str(e).startswith("BUILD FAILED"):
                raise SystemExit(f"mutant '{name}' did not build - a mutant that does not build proves nothing: {e}")
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
    with tempfile.TemporaryDirectory(prefix="pmf_uart10_") as td:
        work = pathlib.Path(td)
        img = work / "uart10.img"
        build(compiler, ROOT, img)
        ck = gate(img, k, a.verbose)
        for m in ck.bad:
            print("  FAIL " + m)
        alive = [] if a.no_mutants else mutants(compiler, k, work)
    if ck.bad or alive:
        print(f"a64_uart10_pi5_check: FAIL - {len(ck.bad)} of {ck.n} checks red, {len(alive)} mutant(s) alive")
        return 1
    print(f"a64_uart10_pi5_check: PASS - {ck.n} checks"
          + ("" if a.no_mutants else f", {len(MUTANTS)}/{len(MUTANTS)} mutants red")
          + ". Desk only: silicon owed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

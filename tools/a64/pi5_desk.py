#!/usr/bin/env python3
"""Shared desk harness for the Pi 5 (-t pi5, #PMF_CHIP = 2712) peripheral gates.

tools/a64/gpio_rp1_check.py, i2c_dw_check.py and rtc_fw_check.py all do the
same three things, so they are here once:

  build()    compile a small driver program with -t pi5 against PMF_ROOT =
             this checkout, and read every procedure's address out of the
             `.dbg` the compiler writes beside the image (the `.dbg`, not the
             `.sym` - see the note in a64_interp.py).
  Machine    load the image into a64_interp's A64, route every access at or
             above 4 GiB (where BCM2712/RP1 peripherals live) and inside any
             extra window the gate names to the gate's MODEL, and refuse any
             other device access by name. RAM is the interpreter's dict.
  call()     run ONE compiled procedure with arguments in x0..x7 until it
             returns to a sentinel link register, bounded.

A gate states its own CNTFRQ_EL0: a64_interp answers CNTPCT_EL0 but refuses
CNTFRQ_EL0 on purpose, because a frequency is board data a program divides
by (see the interpreter's note). The Pi 5 figure, 54 MHz, is the stock
BCM2712 TF-A's (vault HARDWARE-BRINGUP.md, "counter frequency 54000000").

Mutation runs substitute the TEXT of one tracked source: `override` maps a
repo-relative path to replacement text, and build() includes the replacement
from the work directory instead. No tracked file is ever opened for writing.
"""
from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
from a64_interp import A64, attach_symbols        # noqa: E402
from pmf_compiler import resolve_compiler          # noqa: E402

LOAD = 0x400000
STACK = 0x3000000
RETURN = 0xDEADBEE0
CNTFRQ_PI5 = 54_000_000


class GateFail(Exception):
    pass


def die(msg: str) -> "None":
    raise GateFail(msg)


def compiler(path_arg):
    if not path_arg:
        raise SystemExit("No compiler named: pass --compiler or set PMF_COMPILER.")
    return str(pathlib.Path(resolve_compiler(path_arg)).resolve())


def source(rel: str, override: dict) -> str:
    if rel in override:
        return override[rel]
    return (ROOT / rel).read_text(encoding="utf-8")


def const_in(text: str, name: str, where: str) -> int:
    m = re.search(r"^[ \t]*%s\s*=\s*(-?\$?[0-9A-Fa-f]+)" % re.escape(name), text, re.M)
    if not m:
        die("%s no longer defines %s" % (where, name))
    v = m.group(1)
    neg = v.startswith("-")
    v = v.lstrip("-")
    n = int(v[1:], 16) if v.startswith("$") else int(v)
    return -n if neg else n


def build(cc: str, text: str, name: str, workdir: pathlib.Path,
          override: dict, includes: list) -> tuple:
    """Compile `text` with its XIncludeFile lines for `includes` redirected
    to mutated copies where `override` names them. Returns (image, procs)."""
    workdir.mkdir(parents=True, exist_ok=True)
    for rel in includes:
        marker = 'XIncludeFile "%s"' % rel
        if text.count(marker) != 1:
            die("driver does not include %s exactly once" % rel)
        if rel in override:
            copy = workdir / ("mut_" + pathlib.Path(rel).name)
            copy.write_text(override[rel], encoding="utf-8")
            text = text.replace(marker, 'XIncludeFile "%s"' % copy.resolve().as_posix())
    src = workdir / (name + ".pi4")
    src.write_text(text, encoding="utf-8")
    img = workdir / (name + ".img")
    r = subprocess.run([cc, "--compile", str(src), "-t", "pi5",
                        "--entry-returns", "--load-addr", hex(LOAD),
                        "--stack-addr", hex(STACK), "-o", str(img)],
                       cwd=str(ROOT), env=dict(os.environ, PMF_ROOT=str(ROOT)),
                       capture_output=True, text=True)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout or not img.exists():
        die("the driver would not build:\n" + r.stdout[-3000:] + r.stderr[-1500:])
    procs = {}
    for line in pathlib.Path(str(img) + ".dbg").read_text(
            encoding="utf-8", errors="replace").splitlines():
        f = line.split("|")
        if len(f) >= 3 and f[0] == "1" and f[1].isdigit():
            procs[f[2].lower()] = LOAD + int(f[1])
    return img, procs


class Machine:
    """One image, one model. `model(addr, size, value)` answers a load when
    value is None and performs a store otherwise; `windows` is a list of
    (lo, hi) ranges below 4 GiB that also belong to the model."""

    def __init__(self, img: pathlib.Path, procs: dict, model, windows=(),
                 cntfrq: int = CNTFRQ_PI5, ticks_per_step: int = 1):
        self.procs = procs
        self.cpu = cpu = A64()
        blob = img.read_bytes()
        for i, b in enumerate(blob):
            cpu.memory[LOAD + i] = b
        attach_symbols(cpu, img, LOAD)
        cpu.cntpct_per_instruction = ticks_per_step
        mem = cpu.memory
        wins = list(windows)

        def is_dev(addr):
            if addr >= 0x1_0000_0000:
                return True
            return any(lo <= addr < hi for lo, hi in wins)

        def load(addr, size):
            cpu.align_guard(addr, size, False)
            if is_dev(addr):
                return model(addr, size, None) & ((1 << (8 * size)) - 1)
            return sum(mem.get(addr + i, 0) << (8 * i) for i in range(size))

        def store(addr, value, size):
            cpu.align_guard(addr, size, True)
            if is_dev(addr):
                model(addr, size, value & ((1 << (8 * size)) - 1))
                return
            for i in range(size):
                mem[addr + i] = (value >> (8 * i)) & 0xFF

        cpu.load = load
        cpu.store = store
        plain = A64.step.__get__(cpu)

        def step():
            ins = cpu.fetch(cpu.pc)
            if (ins & 0xFFFFFFE0) == 0xD53BE000:          # mrs Xt, cntfrq_el0
                cpu.x[ins & 31] = cntfrq
                cpu.pc += 4
                cpu.cntpct += cpu.cntpct_per_instruction
                return
            plain()
        self.step = step

    def call(self, name: str, *args, limit: int = 5_000_000) -> int:
        key = name.lower()
        if key not in self.procs:
            die("the image has no procedure %s" % name)
        c = self.cpu
        c.pc = self.procs[key]
        c.sp = STACK
        c.x[30] = RETURN
        for i, v in enumerate(args):
            c.x[i] = v & ((1 << 64) - 1)
        n = 0
        while c.pc != RETURN:
            n += 1
            if n > limit:
                die("%s never returned after %d steps" % (name, limit))
            self.step()
        return c.x[0]

    def signed(self, v: int) -> int:
        return v - (1 << 64) if v & (1 << 63) else v

    def cstr(self, addr: int, limit: int = 400) -> str:
        out = []
        for i in range(limit):
            b = self.cpu.memory.get(addr + i, 0)
            if b == 0:
                break
            out.append(chr(b))
        return "".join(out)

    def poke(self, addr: int, data: bytes) -> None:
        for i, b in enumerate(data):
            self.cpu.memory[addr + i] = b

    def peek(self, addr: int, n: int) -> bytes:
        return bytes(self.cpu.memory.get(addr + i, 0) for i in range(n))


def run_mutations(label: str, mutations: list, gate, workdir: pathlib.Path) -> int:
    """Each mutation is (rel, why, old, new). The gate must go RED on every
    one. Returns the number that SURVIVED (0 is the only passing answer)."""
    survived = 0
    for i, (rel, why, old, new) in enumerate(mutations):
        text = (ROOT / rel).read_text(encoding="utf-8")
        if text.count(old) != 1:
            print("  %2d  SURVIVED  %s: %s (the edit matched %d times, not once)"
                  % (i, rel, why, text.count(old)))
            survived += 1
            continue
        override = {rel: text.replace(old, new)}
        try:
            gate(override, workdir / ("m%02d" % i))
        except GateFail as exc:
            print("  %2d  KILLED    %s: %s (%s)"
                  % (i, rel, why, str(exc).replace("\n", " ")[:110]))
            continue
        except Exception as exc:                          # noqa: BLE001
            print("  %2d  KILLED    %s: %s (%r)" % (i, rel, why, exc))
            continue
        print("  %2d  SURVIVED  %s: %s" % (i, rel, why))
        survived += 1
    print("%s mutations: %d killed, %d survived"
          % (label, len(mutations) - survived, survived))
    return survived

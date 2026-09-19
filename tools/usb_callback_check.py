#!/usr/bin/env python3
"""Emit and execute the USB core control callback seam.

The fixture includes the production Anvil/Bus/usb_core.pbi and supplies a
small control-transfer provider. It proves that descriptor requests reach the
provider with the documented six arguments and that its byte count is returned
as a count. The mutation restores the leading-star call that dereferences the
provider's integer result.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "Anvil" / "Bus" / "usb_core.pbi"
LOAD = 0x00400000
STACK = 0x03000000
LR = 0xDEAD0000
LIMIT = 2_000_000


def interp(path: Path):
    spec = importlib.util.spec_from_file_location("usb_callback_a64", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def symbols(path: Path):
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            name, value = line.split("=", 1)
            try:
                out[name] = int(value, 0)
            except ValueError:
                pass
    return out


PROBE = r'''
XIncludeFile "Anvil/Bus/usb_core.pbi"

Global gCalls.i
Global gBad.i

Procedure.i FakeCtrlIn(rt.i, req.i, val.i, idx.i, *dst, length.i)
  Define i.i
  gCalls = gCalls + 1
  If rt <> $80 Or req <> 6 Or idx <> 0 Or *dst = 0
    gBad = 1
    ProcedureReturn -1
  EndIf
  If val = $0100
    If length <> 18 : gBad = 2 : ProcedureReturn -1 : EndIf
    For i = 0 To 17 : PokeA(*dst + i, i + 1) : Next
    ProcedureReturn 18
  EndIf
  If val = $0200
    If length = 9
      PokeA(*dst + 0, 9) : PokeA(*dst + 1, 2)
      PokeA(*dst + 2, 18) : PokeA(*dst + 3, 0)
      PokeA(*dst + 4, 1) : PokeA(*dst + 5, 1)
      PokeA(*dst + 6, 0) : PokeA(*dst + 7, $80)
      PokeA(*dst + 8, 50)
      ProcedureReturn 9
    EndIf
    If length <> 18 : gBad = 3 : ProcedureReturn -1 : EndIf
    For i = 0 To 17 : PokeA(*dst + i, i + 9) : Next
    PokeA(*dst + 0, 9) : PokeA(*dst + 1, 2)
    PokeA(*dst + 2, 18) : PokeA(*dst + 3, 0)
    ProcedureReturn 18
  EndIf
  gBad = 4
  ProcedureReturn -1
EndProcedure

Procedure.i FakeCtrlOut(rt.i, req.i, val.i, idx.i, *src, length.i)
  ProcedureReturn 0
EndProcedure

Procedure.i Main()
  Define got.i
  UsbCoreSetHost(@FakeCtrlIn, @FakeCtrlOut)
  got = UsbGetDescriptor(#USB_DT_DEVICE, 0, 0, @usbc_dev[0], 18)
  If got <> 18 : ProcedureReturn 11 : EndIf
  If usbc_dev[0] <> 1 Or usbc_dev[17] <> 18 : ProcedureReturn 12 : EndIf
  got = UsbGetConfiguration(@usbc_cfg[0], #USB_CFG_BYTES)
  If got <> 18 Or UsbConfigurationHeld() <> 18 : ProcedureReturn 21 : EndIf
  If usbc_cfg[0] <> 9 Or usbc_cfg[2] <> 18 : ProcedureReturn 22 : EndIf
  If gCalls <> 3 Or gBad <> 0 : ProcedureReturn 31 : EndIf
  ProcedureReturn 0
EndProcedure
'''


def build(compiler: Path, work: Path, mutant: bool) -> Path:
    source = PROBE
    core = CORE.read_text(encoding="utf-8")
    if mutant:
        fixed = "ProcedureReturn usbc_ctrlIn($80, 6, ((dtype & $FF) << 8) | (dindex & $FF), langid, *dst, wLength)"
        broken = fixed.replace("usbc_ctrlIn(", "*usbc_ctrlIn(", 1)
        if core.count(fixed) != 1:
            raise SystemExit("usb callback gate: mutation anchor drifted")
        bad = work / "usb_core_mutant.pbi"
        bad.write_text(core.replace(fixed, broken, 1), encoding="utf-8")
        source = source.replace('XIncludeFile "Anvil/Bus/usb_core.pbi"',
                                f'XIncludeFile "{bad.as_posix()}"', 1)
    probe = work / "usb_callback_gate.pi4"
    probe.write_text(source, encoding="utf-8")
    image = work / "usb_callback_gate.img"
    cmd = [str(compiler), "--compile", str(probe), "-t", "pi4",
           "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
           "--entry-returns", "-o", str(image), "-s"]
    run = subprocess.run(cmd, cwd=ROOT, env={**os.environ, "PMF_ROOT": str(ROOT)},
                         text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise SystemExit("usb callback gate: compile failed\n" + run.stdout)
    return image


def execute(a64, image: Path):
    blob = image.read_bytes()
    syms = symbols(image.with_suffix(image.suffix + ".sym"))
    bss_lo, bss_hi = syms.get("__bss_start__"), syms.get("__bss_end__")
    if bss_lo is None or bss_hi is None:
        raise SystemExit("usb callback gate: compiler omitted BSS bounds")
    cpu = a64.A64()
    for i, b in enumerate(blob):
        cpu.memory[LOAD + i] = b
    a64.attach_symbols(cpu, image, LOAD)
    cpu.pc, cpu.sp, cpu.x[30] = LOAD, STACK, LR
    image_hi = LOAD + len(blob)
    def inside(addr, size, writable=False):
        if size <= 0: return False
        if STACK - 0x100000 <= addr and addr + size <= STACK + 16: return True
        if bss_lo <= addr and addr + size <= bss_hi: return True
        if not writable and LOAD <= addr and addr + size <= image_hi: return True
        return False
    def load(addr, size):
        cpu.align_guard(addr, size, False)
        if not inside(addr, size): raise SystemExit(f"read outside fixture ${addr:X}")
        return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(size))
    def store(addr, value, size):
        cpu.align_guard(addr, size, True)
        if not inside(addr, size, True): raise SystemExit(f"write outside fixture ${addr:X}")
        for i in range(size): cpu.memory[addr + i] = (value >> (8 * i)) & 255
    cpu.load, cpu.store = load, store
    for steps in range(LIMIT):
        if cpu.pc == LR: return cpu.x[0], steps
        cpu.step()
    raise SystemExit("usb callback gate: execution did not return")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"), required=False)
    ap.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"), required=False)
    args = ap.parse_args()
    if not args.compiler or not args.interp:
        raise SystemExit("usb callback gate: set PMF_COMPILER and PMF_A64_INTERP")
    compiler, interpreter = Path(args.compiler).resolve(), Path(args.interp).resolve()
    a64 = interp(interpreter)
    for mutant, expected in ((False, 0), (True, 11)):
        with tempfile.TemporaryDirectory(prefix="usb-callback-") as tmp:
            try:
                result, steps = execute(a64, build(compiler, Path(tmp), mutant))
            except a64.AlignmentFault as fault:
                if not mutant or fault.addr != 18 or fault.size != 8 or fault.write:
                    raise
                print("PASS bad-star mutant rejected: 8-byte read through returned count 18")
                continue
        if result != expected:
            raise SystemExit(f"usb callback gate: {'mutant' if mutant else 'fixed'} returned {result}, expected {expected}")
        print(f"PASS {'bad-star mutant rejected' if mutant else 'callback/configuration seam'} after {steps:,} instructions")


if __name__ == "__main__":
    main()

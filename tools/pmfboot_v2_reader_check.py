#!/usr/bin/env python3
"""Execute the shipped PMFBOOT v1/v2 parser and admission checks.

The PureMetal procedure bodies are extracted from Anvil/Core/pmfboot.pbi,
compiled by the requested PureMetalForge build and run as emitted AArch64.
Hardware and printing are stubs; the version/length/provenance decisions are
the production code, not a Python reimplementation of them.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler


ROOT = Path(__file__).resolve().parents[1]
PMFBOOT = ROOT / "Anvil" / "Core" / "pmfboot.pbi"
INTERP = ROOT / "tools" / "a64" / "a64_interp.py"
LOAD = 0x00400000
STACK = 0x03000000
RETURN = 0xDEAD0000


def procedure(text: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^Procedure(?:\.i)?\s+{re.escape(name)}\([^\n]*\)\s*$"
        rf".*?^EndProcedure\s*$", text
    )
    if not match:
        raise AssertionError(f"production procedure not found: {name}")
    return match.group(0)


PRELUDE = r'''
EnableExplicit

#PMF_HDR_LEN_V1 = 96
#PMF_HDR_LEN_V2 = 128
#PMF_VERSION_V1 = 1
#PMF_VERSION_V2 = 2
#PMF_DIGEST = 32
#PMF_OFF_VERSION = 8
#PMF_OFF_HDRLEN = 12
#PMF_OFF_LOAD = 16
#PMF_OFF_ENTRY = 24
#PMF_OFF_IMGLEN = 32
#PMF_OFF_BSSBASE = 40
#PMF_OFF_BSSLEN = 48
#PMF_OFF_FLAGS = 56
#PMF_OFF_RESERVED = 60
#PMF_OFF_SHA = 64
#PMF_OFF_ARCH = 96
#PMF_OFF_TARGET = 100
#PMF_OFF_STACK = 104
#PMF_OFF_EXTRES = 112
#PMF_EXTRES_LEN = 16
#PMF_ARCH_AARCH64 = 1
#PMF_TARGET_BCM2837 = 2837
#PMF_TARGET_BCM2711 = 2711
#PMF_TARGET_QCM2290 = 2290
#PMF_FLAG_RETURNS = 1
#PMF_FLAG_WANTS_DTB = 2
#PMF_FLAG_WANTS_SERVICES = 4
#LEN_MAX = $3FFFFFFF
#PMF_STACK_ABI_BYTES = 16
#PAY_STACK_LO = $7F00000
#PAY_STACK_HI = $80FFFFF
#HW_ADDR_SAFE = 1

Global Dim gPmfHdr.a[159]
Global Dim gPmfWant.a[63]
Global gPmfLoad.i
Global gPmfEntry.i
Global gPmfImgLen.i
Global gPmfBssBase.i
Global gPmfBssLen.i
Global gPmfFlags.i
Global gPmfVersion.i
Global gPmfHdrLen.i
Global gPmfArchitecture.i
Global gPmfTarget.i
Global gPmfStack.i
Global gPmfReserved.i
Global gPmfExtReservedOk.i
Global gMonHitLo.i
Global gMonHitHi.i
Global gQAddrSafe.i

Procedure str_print_at(*s) : EndProcedure
Procedure PrintNl() : EndProcedure
Procedure GatePrint(*s) : EndProcedure
Procedure GatePrintN(*s) : EndProcedure
Procedure PrintDec(v.i) : EndProcedure
Procedure PutAddr(v.i) : EndProcedure
Procedure PutHex8(v.i) : EndProcedure
Procedure.i HwPmfTargetId() : ProcedureReturn #PMF_TARGET_BCM2711 : EndProcedure
Procedure.i HwPayWindows() : ProcedureReturn 2 : EndProcedure
Procedure.i HwPayLo(i.i)
  If i=0 : ProcedureReturn $600000 : EndIf
  If i=1 : ProcedureReturn $40000000 : EndIf
  ProcedureReturn 1
EndProcedure
Procedure.i HwPayHi(i.i)
  If i=0 : ProcedureReturn $7EFFFFF : EndIf
  If i=1 : ProcedureReturn $FBFFFFFF : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i GatePi3PayLo(i.i)
  If i=0 : ProcedureReturn $2E00000 : EndIf
  ProcedureReturn 1
EndProcedure
Procedure.i GatePi3PayHi(i.i)
  If i=0 : ProcedureReturn $3EFFFFFF : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i GatePi3MonRegions() : ProcedureReturn 1 : EndProcedure
Procedure.i GatePi3MonRegionLo(i.i)
  If i=0 : ProcedureReturn $70000000 : EndIf
  ProcedureReturn 1
EndProcedure
Procedure.i GatePi3MonRegionHi(i.i)
  If i=0 : ProcedureReturn $700FFFFF : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i GateQPayWindows() : ProcedureReturn 2 : EndProcedure
Procedure.i GateQPayLo(i.i)
  If i=0 : ProcedureReturn $40000000 : EndIf
  If i=1 : ProcedureReturn $100000000 : EndIf
  ProcedureReturn 1
EndProcedure
Procedure.i GateQPayHi(i.i)
  If i=0 : ProcedureReturn $FFFFFFFF : EndIf
  If i=1 : ProcedureReturn $13FFFFFFF : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i GateQAddrCheck(lo.i, hi.i, forWrite.i)
  If gQAddrSafe <> 0 : ProcedureReturn #HW_ADDR_SAFE : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i GateQMonRegions() : ProcedureReturn 1 : EndProcedure
Procedure.i GateQMonRegionLo(i.i)
  If i=0 : ProcedureReturn $70000000 : EndIf
  ProcedureReturn 1
EndProcedure
Procedure.i GateQMonRegionHi(i.i)
  If i=0 : ProcedureReturn $700FFFFF : EndIf
  ProcedureReturn 0
EndProcedure
Procedure UartWriteStr(*s) : EndProcedure
Procedure PutWindows() : EndProcedure
Procedure.i HitsMonitor(lo.i, hi.i)
  If lo <= $5FFFFF And hi >= $200000 : ProcedureReturn 1 : EndIf
  If lo <= $DFFFFFF And hi >= $D000000 : ProcedureReturn 1 : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i InPayload(lo.i, hi.i)
  If lo >= $600000 And hi <= $7EFFFFF : ProcedureReturn 1 : EndIf
  If lo >= $40000000 And hi <= $FBFFFFFF : ProcedureReturn 1 : EndIf
  ProcedureReturn 0
EndProcedure
'''


TESTS = r'''
Procedure GatePut32(off.i, value.i)
  PokeA(@gPmfHdr[0] + off + 0, value)
  PokeA(@gPmfHdr[0] + off + 1, value >> 8)
  PokeA(@gPmfHdr[0] + off + 2, value >> 16)
  PokeA(@gPmfHdr[0] + off + 3, value >> 24)
EndProcedure

Procedure GatePut64(off.i, value.i)
  Define i.i
  i = 0
  While i < 8
    PokeA(@gPmfHdr[0] + off + i, value >> (i * 8))
    i = i + 1
  Wend
EndProcedure

Procedure GateReset(version.i, hdrlen.i)
  Define i.i
  i = 0
  While i < 160
    gPmfHdr[i] = 0
    i = i + 1
  Wend
  GatePut32(#PMF_OFF_VERSION, version)
  GatePut32(#PMF_OFF_HDRLEN, hdrlen)
  GatePut64(#PMF_OFF_LOAD, $200000)
  GatePut64(#PMF_OFF_ENTRY, $200000)
  GatePut64(#PMF_OFF_IMGLEN, 4)
  GatePut64(#PMF_OFF_BSSBASE, $1100000)
  GatePut64(#PMF_OFF_BSSLEN, 0)
  GatePut32(#PMF_OFF_FLAGS, 0)
EndProcedure

Procedure GateV2(target.i, stack.i)
  GatePut32(#PMF_OFF_ARCH, #PMF_ARCH_AARCH64)
  GatePut32(#PMF_OFF_TARGET, target)
  GatePut64(#PMF_OFF_STACK, stack)
EndProcedure

Procedure.i GateCheck(fileLen.i)
  PmfParseAt(@gPmfHdr[0])
  ProcedureReturn PmfCheckHeader(fileLen)
EndProcedure

Procedure.i GatePlacement(version.i, load.i, imageLen.i, bssBase.i, bssLen.i, stack.i)
  gPmfVersion = version
  gPmfLoad = load
  gPmfEntry = load
  gPmfImgLen = imageLen
  gPmfBssBase = bssBase
  gPmfBssLen = bssLen
  gPmfStack = stack
  ProcedureReturn PmfCheckPlacement()
EndProcedure

Procedure Main()
  Define fail.i

  ; Exact v1 path: offset 96 is already image data. Poison it and prove
  ; it is neither parsed nor judged as a v2 extension.
  GateReset(#PMF_VERSION_V1, #PMF_HDR_LEN_V1)
  GatePut32(#PMF_OFF_ARCH, 99)
  GatePut32(#PMF_OFF_TARGET, 99)
  GatePut64(#PMF_OFF_STACK, 3)
  If GateCheck(100) = 0 : fail = fail + 1 : EndIf
  If gPmfArchitecture <> 0 Or gPmfTarget <> 0 Or gPmfStack <> 0
    fail = fail + 1
  EndIf

  GateReset(#PMF_VERSION_V2, #PMF_HDR_LEN_V2)
  GateV2(#PMF_TARGET_BCM2711, $1F00000)
  If GateCheck(132) = 0 : fail = fail + 1 : EndIf

  ; A known target is not enough: this is emitted as a Pi 4 fixture, so a
  ; perfectly valid BCM2837 identity must still be refused by the board seam.
  GateReset(#PMF_VERSION_V2, #PMF_HDR_LEN_V2)
  GateV2(#PMF_TARGET_BCM2837, $1F00000)
  If GateCheck(132) <> 0 : fail = fail + 1 : EndIf

  GateReset(#PMF_VERSION_V2, #PMF_HDR_LEN_V1)
  If GateCheck(100) <> 0 : fail = fail + 1 : EndIf
  GateReset(#PMF_VERSION_V1, #PMF_HDR_LEN_V2)
  If GateCheck(132) <> 0 : fail = fail + 1 : EndIf
  GateReset(3, #PMF_HDR_LEN_V2)
  If GateCheck(132) <> 0 : fail = fail + 1 : EndIf

  GateReset(#PMF_VERSION_V2, #PMF_HDR_LEN_V2)
  GateV2(#PMF_TARGET_BCM2711, $1F00000)
  GatePut32(#PMF_OFF_ARCH, 2)
  If GateCheck(132) <> 0 : fail = fail + 1 : EndIf
  GateReset(#PMF_VERSION_V2, #PMF_HDR_LEN_V2)
  GateV2(9999, $1F00000)
  If GateCheck(132) <> 0 : fail = fail + 1 : EndIf
  GateReset(#PMF_VERSION_V2, #PMF_HDR_LEN_V2)
  GateV2(#PMF_TARGET_BCM2711, 0)
  If GateCheck(132) <> 0 : fail = fail + 1 : EndIf
  GateReset(#PMF_VERSION_V2, #PMF_HDR_LEN_V2)
  GateV2(#PMF_TARGET_BCM2711, $1F00008)
  If GateCheck(132) <> 0 : fail = fail + 1 : EndIf

  GateReset(#PMF_VERSION_V2, #PMF_HDR_LEN_V2)
  GateV2(#PMF_TARGET_BCM2711, $1F00000)
  GatePut32(#PMF_OFF_RESERVED, 1)
  If GateCheck(132) <> 0 : fail = fail + 1 : EndIf
  GateReset(#PMF_VERSION_V2, #PMF_HDR_LEN_V2)
  GateV2(#PMF_TARGET_BCM2711, $1F00000)
  PokeA(@gPmfHdr[0] + #PMF_OFF_EXTRES + 15, 1)
  If GateCheck(132) <> 0 : fail = fail + 1 : EndIf

  GateReset(#PMF_VERSION_V1, #PMF_HDR_LEN_V1)
  If GateCheck(99) <> 0 : fail = fail + 1 : EndIf
  GateReset(#PMF_VERSION_V2, #PMF_HDR_LEN_V2)
  GateV2(#PMF_TARGET_BCM2711, $1F00000)
  If GateCheck(127) <> 0 : fail = fail + 1 : EndIf
  If GateCheck(131) <> 0 : fail = fail + 1 : EndIf
  If GateCheck(133) <> 0 : fail = fail + 1 : EndIf

  ; PMF v2 supplies a stack top but no extent. Admission validates the
  ; initial 16-byte ABI stack area, including Pi 4's documented corridor.
  If GatePlacement(#PMF_VERSION_V2, $600000, $10000, $720000, $10000, $8000000) = 0 : fail = fail + 1 : EndIf
  ; Payload and BSS outside the payload windows, including monitor BSS.
  If GatePlacement(#PMF_VERSION_V2, $200000, $10000, $720000, $10000, $8000000) <> 0 : fail = fail + 1 : EndIf
  If GatePlacement(#PMF_VERSION_V2, $600000, $10000, $D000000, $1000, $8000000) <> 0 : fail = fail + 1 : EndIf
  If GatePlacement(#PMF_VERSION_V2, $600000, $10000, $8000000, $1000, $8000000) <> 0 : fail = fail + 1 : EndIf
  ; Image/BSS and stack/image or stack/BSS overlap are all independently refused.
  If GatePlacement(#PMF_VERSION_V2, $600000, $20000, $610000, $10000, $8000000) <> 0 : fail = fail + 1 : EndIf
  If GatePlacement(#PMF_VERSION_V2, $600000, $10000, $720000, $10000, $610000) <> 0 : fail = fail + 1 : EndIf
  If GatePlacement(#PMF_VERSION_V2, $600000, $10000, $7F0000, $10000, $800000) <> 0 : fail = fail + 1 : EndIf
  ; The Pi 4 payload high window accepts a stack area; the gap and a top
  ; below that area do not.
  If GatePlacement(#PMF_VERSION_V2, $50000000, $10000, $50020000, $10000, $50000000) = 0 : fail = fail + 1 : EndIf
  If GatePlacement(#PMF_VERSION_V2, $600000, $10000, $720000, $10000, $9000000) <> 0 : fail = fail + 1 : EndIf
  If GatePlacement(#PMF_VERSION_V2, $600000, $10000, $720000, $10000, $80000) <> 0 : fail = fail + 1 : EndIf
  ; Overflowed range arithmetic must not wrap into a permitted region.
  If GatePlacement(#PMF_VERSION_V2, $7FFFFFFFFFF00000, $200000, $720000, $1000, $8000000) <> 0 : fail = fail + 1 : EndIf
  ; Historical v1 carries no stack field and keeps its existing admission contract.
  If GatePlacement(#PMF_VERSION_V1, $600000, $10000, $720000, $10000, 0) = 0 : fail = fail + 1 : EndIf
  ; Execute the real Pi 3 stack hook too: its payload window accepts a
  ; valid top while the old monitor-stack default is refused.
  If GatePi3StackAllowed($2E00000,$2E0000F) = 0 : fail = fail + 1 : EndIf
  If GatePi3StackAllowed($1EFFFF0,$1EFFFFF) <> 0 : fail = fail + 1 : EndIf

  ; UNO Q checks the complete initial stack against Q DRAM windows, board
  ; address classification, and the dynamically located monitor regions.
  gQAddrSafe = 1
  If GateQStackAllowed($50000000,$5000000F) = 0 : fail = fail + 1 : EndIf
  If GateQStackAllowed($70000FF0,$7000100F) <> 0 : fail = fail + 1 : EndIf
  If GateQStackAllowed($30000000,$3000000F) <> 0 : fail = fail + 1 : EndIf
  If GateQStackAllowed($13FFFFFF0,$14000000F) <> 0 : fail = fail + 1 : EndIf
  gQAddrSafe = 0
  If GateQStackAllowed($50000000,$5000000F) <> 0 : fail = fail + 1 : EndIf
  gQAddrSafe = 1
  If GateQStackAllowed($50000010,$50000000) <> 0 : fail = fail + 1 : EndIf

  ProcedureReturn fail
EndProcedure
'''


def load_interpreter():
    spec = importlib.util.spec_from_file_location("pmfboot_v2_a64", INTERP)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load interpreter {INTERP}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def symbols(image: Path) -> dict[str, int]:
    result = {}
    for line in Path(str(image) + ".sym").read_text(encoding="utf-8").splitlines():
        if "=" in line:
            name, value = line.split("=", 1)
            result[name.strip().lower()] = int(value.strip())
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", required=True)
    args = parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    source_text = PMFBOOT.read_text(encoding="utf-8")
    pi4_map_text = (ROOT / "RaspberryPi4" / "Board" / "memmap.pi4").read_text(encoding="utf-8")
    pi3_map_text = (ROOT / "RaspberryPi3" / "Board" / "memmap.pi3").read_text(encoding="utf-8")
    unoq_stubs_text = (ROOT / "ArduinoQ" / "Board" / "qstubs_q.unoq").read_text(encoding="utf-8")
    pi4_stack_hook = procedure(pi4_map_text, "HwPmfStackAllowed")
    pi3_stack_hook = procedure(pi3_map_text, "HwPmfStackAllowed")
    unoq_stack_hook = procedure(unoq_stubs_text, "HwPmfStackAllowed")
    if "#PAY_STACK_LO" not in pi4_stack_hook or "HwPayWindows()" not in pi4_stack_hook:
        raise AssertionError("Pi 4 stack admission no longer covers its dedicated band and payload windows")
    if "HwPayLo(w)" not in pi3_stack_hook or "HwPayHi(w)" not in pi3_stack_hook:
        raise AssertionError("Pi 3 stack admission no longer requires its payload DRAM window")
    pi3_stack_hook = re.sub(r"\bHwPmfStackAllowed\b", "GatePi3StackAllowed", pi3_stack_hook)
    pi3_stack_hook = re.sub(r"\bHwPayLo\b", "GatePi3PayLo", pi3_stack_hook)
    pi3_stack_hook = re.sub(r"\bHwPayHi\b", "GatePi3PayHi", pi3_stack_hook)
    pi3_stack_hook = re.sub(r"\bHwMonRegions\b", "GatePi3MonRegions", pi3_stack_hook)
    pi3_stack_hook = re.sub(r"\bHwMonRegionLo\b", "GatePi3MonRegionLo", pi3_stack_hook)
    pi3_stack_hook = re.sub(r"\bHwMonRegionHi\b", "GatePi3MonRegionHi", pi3_stack_hook)
    unoq_stack_hook = re.sub(r"\bHwPmfStackAllowed\b", "GateQStackAllowed", unoq_stack_hook)
    for old, new in (("HwPayWindows", "GateQPayWindows"), ("HwPayLo", "GateQPayLo"),
                     ("HwPayHi", "GateQPayHi"), ("HwAddrCheck", "GateQAddrCheck"),
                     ("HwMonRegions", "GateQMonRegions"), ("HwMonRegionLo", "GateQMonRegionLo"),
                     ("HwMonRegionHi", "GateQMonRegionHi")):
        unoq_stack_hook = re.sub(rf"\b{old}\b", new, unoq_stack_hook)
    bodies = "\n\n".join(procedure(source_text, name) for name in (
        "PmfRd32", "PmfRd64", "PmfHeaderLengthForVersion", "PmfParseAt",
        "PmfCheckFlags", "PmfCheckV2Metadata", "PmfCheckHeader",
        "PmfCheckRange", "PmfCheckPlacement",
    )) + "\n\n" + pi4_stack_hook + "\n\n" + pi3_stack_hook + "\n\n" + unoq_stack_hook
    bodies = re.sub(r"\bPrintN\b", "GatePrintN", bodies)
    bodies = re.sub(r"\bPrint\b", "GatePrint", bodies)

    with tempfile.TemporaryDirectory(prefix="pmfboot-v2-reader-") as folder:
        work = Path(folder)
        compiler = work / Path(args.compiler).name
        shutil.copy2(Path(args.compiler).resolve(), compiler)
        shutil.copytree(ROOT / "Boards", work / "Boards")
        source = work / "pmfboot_v2_reader.pi4"
        image = work / "pmfboot_v2_reader.img"
        source.write_text(PRELUDE + "\n" + bodies + "\n" + TESTS, encoding="ascii")
        env = os.environ.copy()
        env["PMF_ROOT"] = str(ROOT)
        command = [str(compiler), "--compile", str(source), "-t", "pi4",
                   "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
                   "--entry-returns", "-o", str(image)]
        built = subprocess.run(command, cwd=ROOT, env=env, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if built.returncode or not image.is_file():
            raise AssertionError("reader fixture failed to compile:\n" + built.stdout)

        sym = symbols(image)
        a64 = load_interpreter()
        cpu = a64.A64()
        for offset, byte in enumerate(image.read_bytes()):
            cpu.memory[LOAD + offset] = byte
        cpu.sp = STACK
        cpu.pc = LOAD + sym["main"]
        cpu.x[30] = RETURN
        for _ in range(2_000_000):
            if cpu.pc == RETURN:
                break
            cpu.step()
        else:
            raise AssertionError("reader fixture exceeded instruction ceiling")
        if cpu.x[0] != 0:
            raise AssertionError(f"production reader fixture reported {cpu.x[0]} failures")

    print("PASS: emitted production reader accepts exact v1 and exact v2")
    print("PASS: v1 does not parse offset 96; strict v2 rejects wrong-known target, bad IDs/stack/reserved/length")
    print("PASS: placement rejects monitor/outside-window/overlap/overflow ranges and validates the v2 initial stack area")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

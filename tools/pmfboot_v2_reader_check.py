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

Procedure str_print_at(*s) : EndProcedure
Procedure PrintNl() : EndProcedure
Procedure PrintDec(v.i) : EndProcedure
Procedure PutAddr(v.i) : EndProcedure
Procedure PutHex8(v.i) : EndProcedure
Procedure.i HwPmfTargetId() : ProcedureReturn #PMF_TARGET_BCM2711 : EndProcedure
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
    args = parser.parse_args()
    source_text = PMFBOOT.read_text(encoding="utf-8")
    bodies = "\n\n".join(procedure(source_text, name) for name in (
        "PmfRd32", "PmfRd64", "PmfHeaderLengthForVersion", "PmfParseAt",
        "PmfCheckFlags", "PmfCheckV2Metadata", "PmfCheckHeader",
    ))

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build and execute the PMFMOD parser/relocator/arena engine as A64 code.

This gate generates deterministic PMFMOD v1 containers, embeds them in a
PureMetal harness, compiles the real Core implementation, and runs the emitted
A64 image in the project's instruction interpreter. It models RAM only: no
board, cache, device discovery, probe, init, service binding or trust policy is
claimed.
"""

from __future__ import annotations

import hashlib
import importlib.util
import argparse
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "build/tests/module_engine"
SOURCE = WORK / "module_engine_harness.pi4"
IMAGE = WORK / "module_engine_harness.img"
LOAD = 0x00200000
STACK = 0x03000000
RETURN_PC = 0xDEAD0000
STEP_LIMIT = 40_000_000

HEADER = 160
DIGEST_OFF = 96
DIGEST_END = 128
RELOC_BYTES = 16
MATCH_BYTES = 64


def locate_required(env_name: str, relative: str) -> Path:
    choices = []
    if os.environ.get(env_name):
        choices.append(Path(os.environ[env_name]))
    choices.append(ROOT / relative)
    for path in choices:
        if path.is_file():
            return path.resolve()
    raise SystemExit(
        f"module engine gate: set {env_name}, or provide {relative} in the repo"
    )


def digest(blob: bytearray) -> bytes:
    return hashlib.sha256(blob[:DIGEST_OFF] + blob[DIGEST_END:]).digest()


def seal(blob: bytearray) -> bytes:
    blob[DIGEST_OFF:DIGEST_END] = digest(blob)
    return bytes(blob)


def valid_container(*, reloc_kind: int | None = None, match: bytes = b"vendor,device") -> bytes:
    image = bytearray(64)
    words = (
        0x90000000,  # ADRP x0, target
        0x91000000,  # ADD  x0, x0, target low 12
        0,
        0,
        0xD2800000,  # MOVZ x0, G0
        0xD2A00000,  # MOVZ x0, G1
        0xD2C00000,  # MOVZ x0, G2
        0xD2E00000,  # MOVZ x0, G3
        0x94000000,  # BL image offset zero
        0xD65F03C0,  # init wrapper stand-in: RET
        0xD65F03C0,  # probe wrapper stand-in: RET
        0xD65F03C0,  # quiesce wrapper stand-in: RET
    )
    for index, word in enumerate(words):
        struct.pack_into("<I", image, index * 4, word)

    relocs = [
        (0, 1, 0x1120),
        (4, 2, 0x1120),
        (8, 3, 0),
        (16, 4, 0),
        (20, 5, 0),
        (24, 6, 0),
        (28, 7, 0),
        (32, 8, 0),
    ]
    if reloc_kind is not None:
        relocs[0] = (relocs[0][0], reloc_kind, relocs[0][2])

    reloc_off = (HEADER + len(image) + 7) & ~7
    match_off = reloc_off + len(relocs) * RELOC_BYTES
    total = match_off + MATCH_BYTES
    blob = bytearray(total)
    blob[:8] = b"PMFMOD\0\0"
    struct.pack_into("<IIIIII", blob, 8, 1, HEADER, 1, 0, 1, 0)
    struct.pack_into("<QQQQ", blob, 32, len(image), 0x1000, 0x200, 36)
    struct.pack_into("<III", blob, 64, len(relocs), reloc_off, 4096)
    struct.pack_into("<I", blob, 76, 1)
    struct.pack_into("<IIII", blob, 80, 3, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF)
    struct.pack_into("<IIQQQ", blob, 128, 1, match_off, 40, 44, 0)
    blob[HEADER:HEADER + len(image)] = image
    for index, (site, kind, addend) in enumerate(relocs):
        struct.pack_into("<IHHq", blob, reloc_off + index * RELOC_BYTES,
                         site, kind, 0, addend)
    if not (1 <= len(match) <= 63):
        raise ValueError("test match must fit one canonical record")
    blob[match_off:match_off + len(match)] = match
    return seal(blob)


def cases(writer_fixture: bytes | None = None) -> dict[str, bytes]:
    good = valid_container()
    result = {"good": good}

    bad_magic = bytearray(good)
    bad_magic[0] ^= 1
    result["bad_magic"] = bytes(bad_magic)

    bad_header = bytearray(good)
    struct.pack_into("<I", bad_header, 28, 1)
    result["bad_header"] = bytes(bad_header)

    bad_range = bytearray(good)
    struct.pack_into("<Q", bad_range, 32, 0x7FFFFFFFFFFFFFFF)
    result["bad_range"] = bytes(bad_range)

    bad_major = bytearray(good)
    struct.pack_into("<I", bad_major, 16, 2)
    result["bad_major"] = bytes(bad_major)

    bad_minor = bytearray(good)
    struct.pack_into("<I", bad_minor, 20, 1)
    result["bad_minor"] = bytes(bad_minor)

    bad_hash = bytearray(good)
    bad_hash[HEADER + 52] ^= 0x80
    result["bad_hash"] = bytes(bad_hash)

    result["bad_relkind"] = valid_container(reloc_kind=99)
    result["bad_match"] = valid_container(match=b"vendor/device")

    bad_overlap = bytearray(good)
    reloc_off = struct.unpack_from("<I", bad_overlap, 68)[0]
    # ADD@12 is a valid four-byte relocation by itself, but overlaps ABS64@8.
    struct.pack_into("<I", bad_overlap, HEADER + 12, 0x91000000)
    struct.pack_into("<I", bad_overlap, reloc_off + RELOC_BYTES, 12)
    result["bad_overlap"] = seal(bad_overlap)

    bad_call_bss = bytearray(good)
    # CALL26 cannot transfer into BSS even though BSS is a valid data target.
    struct.pack_into("<q", bad_call_bss, reloc_off + 7 * RELOC_BYTES + 8, 0x1000)
    result["bad_call_bss"] = seal(bad_call_bss)
    if writer_fixture is not None:
        result["writer_fixture"] = writer_fixture
    return result


def data_lines(label: str, blob: bytes) -> list[str]:
    lines = [f"  {label}:"]
    for start in range(0, len(blob), 24):
        row = ", ".join(str(value) for value in blob[start:start + 24])
        lines.append("  Data.a " + row)
    return lines


def make_source(blobs: dict[str, bytes], has_writer_fixture: bool) -> None:
    labels = "\n".join(
        f"#LEN_{name.upper()} = {len(blob)}" for name, blob in blobs.items()
    )
    data = []
    for name, blob in blobs.items():
        data.extend(data_lines("case_" + name, blob))

    writer_phase = ""
    if has_writer_fixture:
        writer_phase = r'''
  ; Cross-proof: load a container emitted by the independent native writer.
  TestColdReset()
  gTestArenaBase = #TEST_ARENA_D
  gTestArenaBytes = $100000
  gTestSyncOk = 1
  fails = fails + Expect(ModArenaInit(), #MOD_OK)
  fails = fails + Expect(ModPreflight(?case_writer_fixture, #LEN_WRITER_FIXTURE, 1, 0), #MOD_OK)
  fails = fails + Expect(gModImageBytes, 48)
  fails = fails + Expect(gModBssOffset, $80000)
  fails = fails + Expect(gModMatchCount, 2)
  fails = fails + Expect(ModArenaLoadPrepared(), #MOD_OK)
  fails = fails + Expect(gModRecordCount, 1)
  fails = fails + Expect(gModRecBase[0], #TEST_ARENA_D)
  fails = fails + Expect(gModRecBytes[0], $81000)
  fails = fails + Expect(gModRecInit[0], #TEST_ARENA_D + 40)
  fails = fails + Expect(gModRecMatchCount[0], 2)
  fails = fails + Expect(PeekA(ModRecordMatchAddr(0, 0)) & 255, 116)
  fails = fails + Expect(PeekA(ModRecordMatchAddr(0, 1)) & 255, 116)
  fails = fails + Expect(PeekN(#TEST_ARENA_D), $90000400)
  fails = fails + Expect(PeekN(#TEST_ARENA_D + 4), $91000000)
  fails = fails + Expect(PeekI(#TEST_ARENA_D + 8), #TEST_ARENA_D + $80000)
  fails = fails + Expect(PeekN(#TEST_ARENA_D + 16), $D2800001)
  fails = fails + Expect(PeekN(#TEST_ARENA_D + 20), $F2A08701)
  fails = fails + Expect(PeekN(#TEST_ARENA_D + 24), $F2C00001)
  fails = fails + Expect(PeekN(#TEST_ARENA_D + 28), $F2E00001)
  fails = fails + Expect(PeekN(#TEST_ARENA_D + 32), $94000002)
  fails = fails + Expect(PeekA(#TEST_ARENA_D + $80000) & 255, 0)
'''

    source = f'''EnableExplicit

XIncludeFile "Anvil/Hal/seams.pbi"
XIncludeFile "Anvil/Hal/module_format.pbi"
XIncludeFile "Anvil/Hal/module_runtime.pbi"
XIncludeFile "Anvil/Core/sha256.pbi"

; Print()/PrintN() resolve by name onto a console library. The registry
; carries one procedure that prints the owners of a binding for a
; refusal sentence; this harness never calls it and supplies the name so
; that no UART is linked in.
Procedure str_print_at(p.i)
EndProcedure

XIncludeFile "Anvil/Core/mod_registry.pbi"

{labels}

#TEST_ARENA_A = $04000000
#TEST_ARENA_B = $04100000
#TEST_ARENA_C = $04200000
#TEST_ARENA_D = $04300000

Global gTestArenaBase.i
Global gTestArenaBytes.i
Global gTestSyncOk.i
Global gTestSyncCalls.i

Procedure.i HwModArenaBase()
  ProcedureReturn gTestArenaBase
EndProcedure

Procedure.i HwModArenaBytes()
  ProcedureReturn gTestArenaBytes
EndProcedure

Procedure.i HwModCodeSync(base.i, bytes.i)
  gTestSyncCalls = gTestSyncCalls + 1
  ProcedureReturn gTestSyncOk
EndProcedure

; ModArenaInit() checks the arena against the board's own reserved map
; and payload windows. This harness models a board that reserves nothing,
; so the check is present and passes; the arena/map refusals themselves
; are gated by tools/module_pipeline_check.py against a board that does.
Procedure.i HwModArenaRegion()
  ProcedureReturn -1
EndProcedure

Procedure.i HwMonRegions()
  ProcedureReturn 0
EndProcedure

Procedure.i HwMonRegionLo(i.i)
  ProcedureReturn 1
EndProcedure

Procedure.i HwMonRegionHi(i.i)
  ProcedureReturn 0
EndProcedure

Procedure.i HwPayWindows()
  ProcedureReturn 0
EndProcedure

Procedure.i HwPayLo(i.i)
  ProcedureReturn 1
EndProcedure

Procedure.i HwPayHi(i.i)
  ProcedureReturn 0
EndProcedure

XIncludeFile "Anvil/Core/mod_container.pbi"
XIncludeFile "Anvil/Core/mod_arena.pbi"

Procedure.i Expect(value.i, wanted.i)
  If value <> wanted
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

; Each placement below models a separate cold boot. Product code cannot reset
; a READY arena; this test-only harness clears the engine globals between CPUs.
Procedure TestColdReset()
  gModArenaReady = 0
  gModArenaBase = 0
  gModArenaBytes = 0
  gModArenaEnd = 0
  gModArenaNext = 0
  gModRecordCount = 0
  gModLastRecord = -1
  gModPrepared = 0
  ModSeamReset()
EndProcedure

Procedure.i Main()
  Define fails.i
  Define oldNext.i
  Define oldCount.i
  fails = 0
  gTestArenaBase = #TEST_ARENA_A
  gTestArenaBytes = $20000
  gTestSyncOk = 1
  fails = fails + Expect(ModArenaInit(), #MOD_OK)
  PokeB(#TEST_ARENA_A, $A5)

  ; All of these fail before any arena byte, bump or record can change.
  fails = fails + Expect(ModPreflight(?case_bad_magic, #LEN_BAD_MAGIC, 1, 0), #MOD_ERR_MAGIC)
  fails = fails + Expect(ModPreflight(?case_bad_header, #LEN_BAD_HEADER, 1, 0), #MOD_ERR_HEADER)
  fails = fails + Expect(ModPreflight(?case_bad_range, #LEN_BAD_RANGE, 1, 0), #MOD_ERR_RANGE)
  fails = fails + Expect(ModPreflight(?case_bad_major, #LEN_BAD_MAJOR, 1, 0), #MOD_ERR_ABI_MAJOR)
  fails = fails + Expect(ModPreflight(?case_bad_minor, #LEN_BAD_MINOR, 1, 0), #MOD_ERR_ABI_MINOR)
  fails = fails + Expect(ModPreflight(?case_bad_hash, #LEN_BAD_HASH, 1, 0), #MOD_ERR_HASH)
  fails = fails + Expect(ModPreflight(?case_bad_relkind, #LEN_BAD_RELKIND, 1, 0), #MOD_ERR_RELKIND)
  fails = fails + Expect(ModPreflight(?case_bad_match, #LEN_BAD_MATCH, 1, 0), #MOD_ERR_MATCH)
  fails = fails + Expect(ModPreflight(?case_bad_overlap, #LEN_BAD_OVERLAP, 1, 0), #MOD_ERR_RELOC)
  fails = fails + Expect(ModPreflight(?case_bad_call_bss, #LEN_BAD_CALL_BSS, 1, 0), #MOD_ERR_RELOC)
  fails = fails + Expect(PeekA(#TEST_ARENA_A) & 255, $A5)
  fails = fails + Expect(gModArenaNext, #TEST_ARENA_A)
  fails = fails + Expect(gModRecordCount, 0)

  ; Placement A: every relocation kind is applied and one READY row commits.
  fails = fails + Expect(ModPreflight(?case_good, #LEN_GOOD, 1, 0), #MOD_OK)
  fails = fails + Expect(ModArenaLoadPrepared(), #MOD_OK)
  fails = fails + Expect(gModRecordCount, 1)
  fails = fails + Expect(gModRecState[0], #MOD_STATE_READY)
  fails = fails + Expect(gModRecBase[0], #TEST_ARENA_A)
  fails = fails + Expect(gModRecMatchCount[0], 1)
  fails = fails + Expect(PeekA(ModRecordMatchAddr(0, 0)) & 255, 118)
  fails = fails + Expect(ModRecordMatchAddr(0, 1), 0)
  fails = fails + Expect(gModArenaNext, #TEST_ARENA_A + $2000)
  fails = fails + Expect(PeekN(#TEST_ARENA_A), $B0000000)
  fails = fails + Expect(PeekN(#TEST_ARENA_A + 4), $91048000)
  fails = fails + Expect(PeekI(#TEST_ARENA_A + 8), #TEST_ARENA_A)
  fails = fails + Expect(PeekN(#TEST_ARENA_A + 16), $D2800000)
  fails = fails + Expect(PeekN(#TEST_ARENA_A + 20), $D2A08000)
  fails = fails + Expect(PeekN(#TEST_ARENA_A + 24), $D2C00000)
  fails = fails + Expect(PeekN(#TEST_ARENA_A + 28), $D2E00000)
  fails = fails + Expect(PeekN(#TEST_ARENA_A + 32), $97FFFFF8)
  fails = fails + Expect(PeekA(#TEST_ARENA_A + $1120) & 255, 0)
  fails = fails + Expect(ModHitsRange(#TEST_ARENA_A, #TEST_ARENA_A + $1FFF), 1)
  fails = fails + Expect(gTestSyncCalls, 1)
  fails = fails + Expect(ModArenaInit(), #MOD_ERR_INIT)
  fails = fails + Expect(gModRecordCount, 1)

  ; Placement B: a separate cold boot loads the same bytes at a second base.
  TestColdReset()
  gTestArenaBase = #TEST_ARENA_B
  gTestArenaBytes = $20000
  fails = fails + Expect(ModArenaInit(), #MOD_OK)
  fails = fails + Expect(ModPreflight(?case_good, #LEN_GOOD, 1, 0), #MOD_OK)
  fails = fails + Expect(ModArenaLoadPrepared(), #MOD_OK)
  fails = fails + Expect(PeekI(#TEST_ARENA_B + 8), #TEST_ARENA_B)
  fails = fails + Expect(PeekN(#TEST_ARENA_B + 20), $D2A08200)
  fails = fails + Expect(PeekN(#TEST_ARENA_B + 32), $97FFFFF8)

  ; A later bad transaction cannot consume a record or a byte of arena.
  oldNext = gModArenaNext
  oldCount = gModRecordCount
  PokeB(oldNext, $A5)
  fails = fails + Expect(ModPreflight(?case_bad_hash, #LEN_BAD_HASH, 1, 0), #MOD_ERR_HASH)
  fails = fails + Expect(gModArenaNext, oldNext)
  fails = fails + Expect(gModRecordCount, oldCount)
  fails = fails + Expect(PeekA(oldNext) & 255, $A5)

  ; Allocation and cache-sync refusals also commit no allocator/record state.
  TestColdReset()
  gTestArenaBase = #TEST_ARENA_C
  gTestArenaBytes = $1000
  fails = fails + Expect(ModArenaInit(), #MOD_OK)
  fails = fails + Expect(ModPreflight(?case_good, #LEN_GOOD, 1, 0), #MOD_OK)
  fails = fails + Expect(ModArenaLoadPrepared(), #MOD_ERR_ARENA_FULL)
  fails = fails + Expect(gModArenaNext, #TEST_ARENA_C)
  fails = fails + Expect(gModRecordCount, 0)

  TestColdReset()
  gTestArenaBytes = $20000
  fails = fails + Expect(ModArenaInit(), #MOD_OK)
  gTestSyncOk = 0
  fails = fails + Expect(ModPreflight(?case_good, #LEN_GOOD, 1, 0), #MOD_OK)
  fails = fails + Expect(ModArenaLoadPrepared(), #MOD_ERR_SYNC)
  fails = fails + Expect(gModArenaNext, #TEST_ARENA_C)
  fails = fails + Expect(gModRecordCount, 0)
{writer_phase}
  ProcedureReturn fails
EndProcedure

DataSection
{chr(10).join(data)}
EndDataSection
'''
    WORK.mkdir(parents=True, exist_ok=True)
    SOURCE.write_text(source, encoding="utf-8", newline="\n")


def build(compiler: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="anvil-module-compiler-") as name:
        stage = Path(name)
        staged = stage / compiler.name
        shutil.copy2(compiler, staged)
        shutil.copytree(ROOT / "Boards", stage / "Boards")
        env = os.environ.copy()
        env["PMF_ROOT"] = str(ROOT)
        command = [
            str(staged), "--compile", SOURCE.relative_to(ROOT).as_posix(), "-t", "pi4",
            "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
            "--entry-returns", "-o", str(IMAGE), "-s",
        ]
        run = subprocess.run(command, cwd=ROOT, env=env, text=True,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if run.returncode != 0 or "pmfc: OK" not in run.stdout:
        raise SystemExit("module engine gate: build failed\n" + run.stdout)


def load_interpreter(path: Path):
    spec = importlib.util.spec_from_file_location("anvil_module_a64", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"module engine gate: cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def execute(a64) -> tuple[int, int]:
    cpu = a64.A64()
    for index, value in enumerate(IMAGE.read_bytes()):
        cpu.memory[LOAD + index] = value
    a64.attach_symbols(cpu, IMAGE, LOAD)
    cpu.pc = LOAD
    cpu.sp = STACK
    cpu.x[30] = RETURN_PC
    for steps in range(STEP_LIMIT):
        if cpu.pc == RETURN_PC:
            return cpu.x[0], steps
        cpu.step()
    raise SystemExit(f"module engine gate: no return in {STEP_LIMIT} instructions")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--writer-fixture", type=Path,
        help="optional PMFMOD produced by the independent compiler writer",
    )
    args = parser.parse_args()
    compiler = locate_required("PMF_COMPILER", "PureMetalForge.exe")
    interpreter = locate_required("PMF_A64_INTERP", "tools/a64/a64_interp.py")
    fixture = None
    if args.writer_fixture is not None:
        fixture = args.writer_fixture.read_bytes()
    blobs = cases(fixture)
    make_source(blobs, fixture is not None)
    build(compiler)
    rc, steps = execute(load_interpreter(interpreter))
    if rc:
        print(f"module engine gate: FAIL - compiled harness reports {rc} checks")
        return 1
    check_count = 78 if fixture is not None else 56
    print(f"module engine gate: PASS - {check_count} emitted-code checks")
    print(f"  interpreted {steps} A64 instructions")
    print("  malformed header/range/ABI/hash/match/relocation refusals passed")
    print("  all v1 relocation kinds passed at two page-aligned placements")
    print("  failed preflight/allocation/cache-sync transactions committed no state")
    if fixture is not None:
        print("  independent native-writer fixture parsed, relocated and recorded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

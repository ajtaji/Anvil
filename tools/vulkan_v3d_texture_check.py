#!/usr/bin/env python3
"""Desk gate for the isolated V3D 4.2 optimal-texture TFU component.

The emitted half compiles and executes the production planner/transfer wrapper
with mocked TFU owners. The independent Python half implements Mesa's
UIF_NO_XOR byte-offset equation and proves the planned allocation covers every
packed four-byte texel without aliases. No hardware path is linked or touched.

  py -3 tools/vulkan_v3d_texture_check.py --mutate
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler


HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
MODULE = ROOT / "Anvil" / "Graphics" / "Vulkan" / "vk_v3d_texture.pi4"
GATE = ROOT / "Anvil" / "Graphics" / "Vulkan" / "Tests" / "vulkan_v3d_texture_gate.pi4"

LOAD = 0x00400000
STACK = 0x03000000
LOADER_LR = 0xDEAD0000
MMIO = 0xFC000000
STEP_LIMIT = 20_000_000
MAGIC = 0x56545446

EXPECTED_TOKENS = (
    "#ANVIL_V3D_TEXTURE_RAW32_TTYPE    = 29",
    "#ANVIL_V3D_TEXTURE_TFU_UIF_NO_XOR = 6",
    "#ANVIL_V3D_TEXTURE_MEM_UIF_NO_XOR = 4",
    "#ANVIL_V3D_TEXTURE_WIDTH_ALIGN    = 32",
    "#ANVIL_V3D_TEXTURE_HEIGHT_ALIGN   = 8",
    "#ANVIL_V3D_TEXTURE_DEST_ALIGN     = 4096",
    "readBytes = (sourcePitch * (height - 1)) + rowBytes",
    "dstBytes = paddedW * paddedH * #ANVIL_V3D_TEXTURE_TEXEL_BYTES",
    "V3dTfuSourceRaster(*transfer\\sourceBase, *plan\\sourceStrideTexels, *plan\\sourceReadBytes)",
    "V3dTfuDest(*transfer\\destinationBase, *plan\\tfuOutputFormat, *plan\\destinationBytes)",
    "ProcedureReturn V3dTfuWait(*transfer\\timeoutUs)",
)

FORBIDDEN = (
    "PokeA(", "PokeL(", "PokeN(", "CopyMemory", "Dma", "DspCopy",
    "V3dCacheRange(", "VK_FORMAT_B8G8R8A8_UNORM",
)

MUTANTS = (
    ("UIF width loses four-block-column alignment",
     "#ANVIL_V3D_TEXTURE_WIDTH_ALIGN    = 32",
     "#ANVIL_V3D_TEXTURE_WIDTH_ALIGN    = 8"),
    ("UIF height loses full-block alignment",
     "#ANVIL_V3D_TEXTURE_HEIGHT_ALIGN   = 8",
     "#ANVIL_V3D_TEXTURE_HEIGHT_ALIGN   = 4"),
    ("raw four-byte copies use an uncited type",
     "#ANVIL_V3D_TEXTURE_RAW32_TTYPE    = 29",
     "#ANVIL_V3D_TEXTURE_RAW32_TTYPE    = 4"),
    ("TFU output silently switches to UIF XOR",
     "#ANVIL_V3D_TEXTURE_TFU_UIF_NO_XOR = 6",
     "#ANVIL_V3D_TEXTURE_TFU_UIF_NO_XOR = 7"),
    ("texture metadata disagrees with TFU output",
     "#ANVIL_V3D_TEXTURE_MEM_UIF_NO_XOR = 4",
     "#ANVIL_V3D_TEXTURE_MEM_UIF_NO_XOR = 5"),
    ("the last staging row is counted as fully padded",
     "readBytes = (sourcePitch * (height - 1)) + rowBytes",
     "readBytes = (sourcePitch * height) + rowBytes"),
    ("destination capacity omits padded rows",
     "dstBytes = paddedW * paddedH * #ANVIL_V3D_TEXTURE_TEXEL_BYTES",
     "dstBytes = paddedW * height * #ANVIL_V3D_TEXTURE_TEXEL_BYTES"),
    ("overlapping input and output reach TFU",
     "If avkV3dTextureRangesOverlap(*transfer\\sourceBase, *plan\\sourceReadBytes, *transfer\\destinationBase, *plan\\destinationBytes) <> 0",
     "If avkV3dTextureRangesOverlap(*transfer\\sourceBase, *plan\\sourceReadBytes, *transfer\\destinationBase, *plan\\destinationBytes) < 0"),
    ("an owner failure no longer stops the call chain",
     "rc = V3dTfuBegin(*plan\\width, *plan\\height, *plan\\rawTextureType)\n  If rc <> 0 : ProcedureReturn rc : EndIf",
     "rc = V3dTfuBegin(*plan\\width, *plan\\height, *plan\\rawTextureType)\n  If rc > 0 : ProcedureReturn rc : EndIf"),
    ("timeout loses its finite upper bound",
     "*transfer\\timeoutUs > #ANVIL_V3D_TEXTURE_MAX_TIMEOUT_US",
     "*transfer\\timeoutUs < #ANVIL_V3D_TEXTURE_MAX_TIMEOUT_US"),
)


def locate(env_name: str, explicit: str | None, fallbacks: list[pathlib.Path]) -> pathlib.Path:
    candidates: list[pathlib.Path] = []
    if explicit:
        candidates.append(pathlib.Path(explicit))
    value = os.environ.get(env_name)
    if value:
        candidates.append(pathlib.Path(value))
    candidates.extend(fallbacks)
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise SystemExit(f"vulkan V3D texture gate: {env_name} was not found; pass its option")


def load_interpreter(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("anvil_v3d_texture_a64", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"vulkan V3D texture gate: cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def source_contract(text: str) -> list[str]:
    failures: list[str] = []
    for token in EXPECTED_TOKENS:
        if token not in text:
            failures.append("missing source contract: " + token)
    for token in FORBIDDEN:
        if token in text:
            failures.append("isolated transfer owns forbidden fallback/cache/format token: " + token)

    start = text.find("Procedure.i AnvilVkV3dTextureConvert(")
    end = text.find("EndProcedure", start)
    body = text[start:end] if start >= 0 and end > start else ""
    order = (
        "V3dTfuBegin(", "V3dTfuSourceRaster(", "V3dTfuDest(",
        "V3dTfuSubmit(", "V3dTfuWait(",
    )
    cursor = 0
    for call in order:
        found = body.find(call, cursor)
        if found < 0:
            failures.append("transfer call order lost at " + call)
            break
        cursor = found + len(call)
    return failures


def build(compiler: pathlib.Path, suffix: str) -> pathlib.Path:
    image = pathlib.Path(tempfile.gettempdir()) / f"anvil_v3d_texture_{suffix}.img"
    command = [
        str(compiler), "--compile", GATE.relative_to(ROOT).as_posix(),
        "-t", "pi4", "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
        "--entry-returns", "-o", str(image), "-s",
    ]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    run = subprocess.run(command, cwd=ROOT, env=env, text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise SystemExit("vulkan V3D texture gate: compile failed\n" + run.stdout)
    return image


def execute(a64, image: pathlib.Path):
    cpu = a64.A64()
    for i, byte in enumerate(image.read_bytes()):
        cpu.memory[LOAD + i] = byte
    a64.attach_symbols(cpu, image, LOAD)
    cpu.pc, cpu.sp, cpu.x[30] = LOAD, STACK, LOADER_LR

    def load(addr: int, size: int) -> int:
        cpu.align_guard(addr, size, False)
        if addr >= MMIO:
            raise SystemExit(f"vulkan V3D texture gate: MMIO read at ${addr:08X}")
        return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr: int, value: int, size: int) -> None:
        cpu.align_guard(addr, size, True)
        if addr >= MMIO:
            raise SystemExit(f"vulkan V3D texture gate: MMIO write at ${addr:08X}")
        for i in range(size):
            cpu.memory[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    for steps in range(STEP_LIMIT):
        if cpu.pc == LOADER_LR:
            return cpu, cpu.x[0] & 0xFFFFFFFFFFFFFFFF, steps
        cpu.step()
    raise SystemExit(f"vulkan V3D texture gate: fixture did not return in {STEP_LIMIT} instructions")


def u64(cpu, addr: int) -> int:
    return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(8))


def grade(cpu, report: int) -> tuple[int, list[str]]:
    failures: list[str] = []
    if u64(cpu, report) != MAGIC:
        failures.append(f"bad report magic at ${report:X}: {u64(cpu, report):X}")
        return 0, failures
    checks = u64(cpu, report + 8)
    failed = u64(cpu, report + 16)
    if checks < 50:
        failures.append(f"fixture ran only {checks} checks")
    if failed:
        rows = [str(i + 1) for i in range(checks) if u64(cpu, report + (8 + i) * 8) == 0]
        failures.append(f"{failed} emitted checks failed: " + ",".join(rows))
    return checks, failures


def uif_no_xor_offset(x: int, y: int, image_h: int) -> int:
    """Independent transcription of Mesa v3d_tiling.c:149-210 for cpp=4."""
    mb_x, mb_y = x // 8, y // 8
    px, py = x % 8, y % 8
    mb_h = (image_h + 7) // 8
    mb_id = (mb_x // 4) * ((mb_h - 1) * 4) + mb_x + mb_y * 4
    utile = (128 if py >= 4 else 0) + (64 if px >= 4 else 0)
    within = (px % 4) * 4 + (py % 4) * 16
    return mb_id * 256 + utile + within


def oracle() -> list[str]:
    failures: list[str] = []
    cases = ((1, 1), (4, 4), (5, 5), (8, 8), (9, 9), (17, 13))
    for width, height in cases:
        pw = (width + 31) // 32 * 32
        ph = (height + 7) // 8 * 8
        size = pw * ph * 4
        offsets = [uif_no_xor_offset(x, y, ph) for y in range(ph) for x in range(pw)]
        if min(offsets) != 0 or max(offsets) != size - 4:
            failures.append(f"{width}x{height}: offsets do not span [0,{size})")
        if len(set(offsets)) != len(offsets):
            failures.append(f"{width}x{height}: UIF byte offsets alias")
        if any((off & 3) or off < 0 or off + 4 > size for off in offsets):
            failures.append(f"{width}x{height}: UIF byte offset escaped/aligned incorrectly")

    # Maximum extent: enumerate each 8x8 UIF block rather than allocating a
    # sixteen-million-entry pixel set. A unique permutation of every block ID,
    # combined with the independently checked 0..252 within-block equation,
    # proves the complete 64 MiB address space without sampling it.
    pw = ph = 4096
    blocks_w, blocks_h = pw // 8, ph // 8
    ids = []
    for by in range(blocks_h):
        for bx in range(blocks_w):
            ids.append(uif_no_xor_offset(bx * 8, by * 8, ph) // 256)
    if len(set(ids)) != blocks_w * blocks_h or min(ids) != 0 or max(ids) != blocks_w * blocks_h - 1:
        failures.append("4096x4096: UIF macroblocks are not an exact allocation permutation")
    if uif_no_xor_offset(4095, 4095, ph) + 4 > 4096 * 4096 * 4:
        failures.append("4096x4096: final texel escapes the 64 MiB allocation")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler")
    parser.add_argument("--interp")
    parser.add_argument("--mutate", action="store_true")
    args = parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler

    compiler = locate("PMF_COMPILER", args.compiler, [
        ROOT / "PureMetalForge.exe",
        pathlib.Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\RaspberryPi4\Reference\PureMetalForge.exe"),
        pathlib.Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe"),
    ])
    interp = locate("PMF_A64_INTERP", args.interp, [ROOT / "tools" / "a64" / "a64_interp.py"])
    a64 = load_interpreter(interp)

    original = MODULE.read_text(encoding="utf-8")
    failures = source_contract(original) + oracle()
    if failures:
        print("vulkan_v3d_texture_check: FAIL")
        for failure in failures:
            print("  " + failure)
        return 1

    cpu, report, steps = execute(a64, build(compiler, "base"))
    checks, failures = grade(cpu, report)
    if failures:
        print(f"vulkan_v3d_texture_check: FAIL ({checks} emitted checks, {steps:,} instructions)")
        for failure in failures:
            print("  " + failure)
        return 1

    print(f"vulkan_v3d_texture_check: PASS - {checks} emitted checks, {steps:,} instructions")
    print("  raw four-byte raster staging -> V3D 4.2 UIF_NO_XOR, level 0 only")
    print("  independent UIF address oracle covers 1x1, utile/block edges, odd and 4096x4096")
    print("  mapped ranges, capacities, alignment, overlap and timeout refuse before TFU")
    print("  exact Begin/Source/Dest/Submit/Wait order and injected owner failures are enforced")

    if not args.mutate:
        print("  (run with --mutate to prove the gate catches plausible layout/packet mistakes)")
        return 0

    missed = 0
    for name, fixed, broken in MUTANTS:
        if original.count(fixed) != 1:
            print(f"  STALE  {name}: anchor appears {original.count(fixed)} times")
            missed += 1
            continue
        MODULE.write_text(original.replace(fixed, broken, 1), encoding="utf-8")
        try:
            # Mutations must be caught by the independently emitted fixture,
            # not merely because the source token above no longer matches.
            mcpu, mreport, _ = execute(a64, build(compiler, "mutant"))
            _, dynamic_fail = grade(mcpu, mreport)
            caught = bool(dynamic_fail)
            detail = dynamic_fail[0] if dynamic_fail else ""
        except SystemExit as exc:
            caught, detail = True, str(exc).splitlines()[0]
        finally:
            MODULE.write_text(original, encoding="utf-8")
        if caught:
            print(f"  RED    {name} - {detail[:100]}")
        else:
            print(f"  GREEN  {name} <-- gate did not notice")
            missed += 1

    if missed:
        print(f"vulkan_v3d_texture_check: FAIL - {missed} of {len(MUTANTS)} mutations escaped")
        return 1
    print(f"vulkan_v3d_texture_check: all {len(MUTANTS)} mutations rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

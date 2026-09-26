#!/usr/bin/env python3
"""Source and emitted-code gate for Neon's borrowed CPU atlas contract."""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from pmf_compiler import resolve_compiler


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "RaspberryPi4/Tests/neon_atlas_contract_emitted_gate.pi4"
NEON = ROOT / "RaspberryPi4/Lib/neon.pi4"
LIBS = (
    "uart.pi4", "timer.pi4", "safety.pi4", "mailbox.pi4", "display.pi4",
    "v3dqpu.pi4", "v3d.pi4", "neon.pi4",
)
LOAD = 0x00400000
STACK = 0x03000000
STACK_BYTES = 0x00100000
LOADER_LR = 0xDEAD0000
STEP_LIMIT = 20_000_000
ASSERTIONS = 46

MUTANTS = (
    (
        "the raster base is exposed before publication",
        "Procedure.i Neon_AtlasRasterBase()\n  If Neon_AtlasRasterReady() = 0 : ProcedureReturn 0 : EndIf\n  ProcedureReturn neon_texSrc",
        "Procedure.i Neon_AtlasRasterBase()\n  ProcedureReturn neon_texSrc",
        3,
    ),
    (
        "the byte extent loses half its texels",
        "bytes = #NEON_ATLAS_W * paddedH * 4",
        "bytes = #NEON_ATLAS_W * paddedH * 2",
        14,
    ),
    (
        "a prior font's raster remains visible",
        "If neon_rasterBuilt = 0 Or neon_rasterFontBits <> neon_fbits Or neon_rasterRevision <> neon_fontRevision",
        "If neon_rasterBuilt = 0",
        28,
    ),
    (
        "glyph UV copy omits the right edge",
        "  *uv\\right  = PeekN(src + 4)",
        "  *uv\\right  = 0",
        18,
    ),
    (
        "the reserved solid-colour texel is not made white",
        "  PokeN(neon_texSrc + (((paddedH - 1) * #NEON_ATLAS_W) * 4), $FFFFFFFF)",
        "  PokeN(neon_texSrc + (((paddedH - 1) * #NEON_ATLAS_W) * 4), $00000000)",
        39,
    ),
)


def required_path(value: str | None, name: str) -> Path:
    if not value:
        raise SystemExit(f"neon atlas gate: set {name} or pass its option")
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"neon atlas gate: {name} file not found: {path}")
    return path


def load_interpreter(path: Path):
    spec = importlib.util.spec_from_file_location("anvil_neon_atlas_a64", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"neon atlas gate: cannot load interpreter: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise AssertionError("mutation anchor drifted: " + old.splitlines()[0])
    return text.replace(old, new, 1)


def source_gate(text: str) -> int:
    checks = (
        "Structure NeonAtlasGlyphUV",
        "Procedure.i neon_RasterEnsure()",
        "Procedure.i Neon_AtlasRasterEnsure()",
        "Procedure.i Neon_AtlasRasterReady()",
        "Procedure.i Neon_AtlasRasterBase()",
        "Procedure.i Neon_AtlasRasterWidth()",
        "Procedure.i Neon_AtlasRasterHeight()",
        "Procedure.i Neon_AtlasRasterBytes()",
        "Procedure.i Neon_AtlasRasterFirstGlyph()",
        "Procedure.i Neon_AtlasRasterLastGlyph()",
        "Procedure.i Neon_AtlasRasterGlyphUV(ch.i, *uv.NeonAtlasGlyphUV)",
        "Procedure.i Neon_AtlasRasterWhiteUV(*uv.NeonAtlasGlyphUV)",
        "r = neon_RasterEnsure()",
        "V3dTfuSourceRaster(neon_texSrc, gNeonAtlasW, bytes)",
        "ProcedureReturn neon_texSrc",
        "*uv\\left   = PeekN(src + 0)",
        "*uv\\right  = PeekN(src + 4)",
        "*uv\\top    = PeekN(src + 8)",
        "*uv\\bottom = PeekN(src + 12)",
        "The final row is reserved",
        "PokeN(neon_texSrc + (((paddedH - 1) * #NEON_ATLAS_W) * 4), $FFFFFFFF)",
        "BORROWED view",
        "There is deliberately\n;  no setter, detach or free operation",
    )
    for needle in checks:
        if needle not in text:
            raise AssertionError("source contract missing: " + needle.splitlines()[0])
    if text.index("r = neon_RasterEnsure()") > text.index("V3dTfuBegin(gNeonAtlasW"):
        raise AssertionError("tiled path does not build the CPU raster first")
    publish = text.index("neon_rasterBuilt = 1")
    if publish < text.index("PokeN(neon_glyphUV") or publish < text.index("neon_rasterBytes = bytes"):
        raise AssertionError("CPU atlas is published before its pixels/metadata")
    if "Procedure.i Neon_AtlasRasterSet" in text or "Procedure Neon_AtlasRasterFree" in text:
        raise AssertionError("read-only contract acquired an ownership-transfer API")
    return len(checks) + 3


def build(compiler: Path, work: Path, name: str, neon_text: str) -> Path:
    root = work / name
    libdir = root / "RaspberryPi4/Lib"
    testdir = root / "RaspberryPi4/Tests"
    intrinsics = root / "RaspberryPi4/Intrinsics"
    coredir = root / "Anvil/Core"
    libdir.mkdir(parents=True)
    testdir.mkdir(parents=True)
    intrinsics.mkdir(parents=True)
    coredir.mkdir(parents=True)
    for item in LIBS:
        src = ROOT / "RaspberryPi4/Lib" / item
        (libdir / item).write_text(
            neon_text if item == "neon.pi4" else src.read_text(encoding="utf-8-sig"),
            encoding="utf-8",
        )
    shutil.copy2(GATE, testdir / GATE.name)
    shutil.copy2(
        ROOT / "RaspberryPi4/Intrinsics/bcm2711_hardware.def",
        intrinsics / "bcm2711_hardware.def",
    )
    shutil.copy2(ROOT / "Anvil/Core/console_style.pbi", coredir / "console_style.pbi")
    image = root / f"{name}.img"
    env = os.environ.copy()
    env["PMF_ROOT"] = str(root)
    run = subprocess.run(
        [
            str(compiler), "--compile", str(testdir / GATE.name), "-t", "pi4", "-s",
            "--entry-returns", "--load-addr", hex(LOAD), "--bss-addr", "0x800000",
            "--stack-addr", hex(STACK), "-o", str(image),
        ],
        cwd=root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=180,
    )
    if run.returncode or "pmfc: OK" not in run.stdout or not image.is_file():
        raise AssertionError(name + " compile failed\n" + run.stdout)
    return image


def symbol_bounds(path: Path) -> tuple[int, int]:
    values: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            if key.strip() in ("__bss_start__", "__bss_end__"):
                values[key.strip()] = int(value.strip(), 0)
    return values["__bss_start__"], values["__bss_end__"]


def execute(a64, image: Path) -> tuple[int, int]:
    blob = image.read_bytes()
    bss = symbol_bounds(Path(str(image) + ".sym"))
    code = (LOAD, LOAD + len(blob))
    stack = (STACK - STACK_BYTES, STACK + 16)

    def contains(ranges, addr: int, size: int) -> bool:
        return size > 0 and any(lo <= addr and addr + size <= hi for lo, hi in ranges)

    cpu = a64.A64()
    cpu.memory = {LOAD + i: byte for i, byte in enumerate(blob)}
    a64.attach_symbols(cpu, image, LOAD)
    cpu.pc = LOAD
    cpu.sp = STACK
    cpu.x[30] = LOADER_LR

    def load(addr: int, size: int) -> int:
        cpu.align_guard(addr, size, False)
        if not contains((code, bss, stack), addr, size):
            raise AssertionError(f"read outside image/BSS/stack: {addr:#x}+{size}")
        return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr: int, value: int, size: int) -> None:
        cpu.align_guard(addr, size, True)
        if not contains((bss, stack), addr, size):
            raise AssertionError(f"write outside BSS/stack: {addr:#x}+{size}")
        for i in range(size):
            cpu.memory[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    for steps in range(STEP_LIMIT):
        if cpu.pc == LOADER_LR:
            return cpu.x[0], steps
        cpu.step()
    raise AssertionError(f"gate did not return within {STEP_LIMIT:,} instructions")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"))
    args = parser.parse_args()
    compiler = Path(resolve_compiler(args.compiler))
    interp = required_path(args.interp, "PMF_A64_INTERP")
    a64 = load_interpreter(interp)
    source = NEON.read_text(encoding="utf-8-sig")
    source_checks = source_gate(source)

    with tempfile.TemporaryDirectory(prefix="anvil-neon-atlas-") as tmp:
        image = build(compiler, Path(tmp), "baseline", source)
        result, steps = execute(a64, image)
        if result:
            raise AssertionError(f"baseline failed assertion {result} after {steps:,} instructions")

        mutant_steps = 0
        for number, (label, old, new, expected) in enumerate(MUTANTS, 1):
            mutant = replace_once(source, old, new)
            image = build(compiler, Path(tmp), f"mutant{number}", mutant)
            result, used = execute(a64, image)
            mutant_steps += used
            if result != expected:
                raise AssertionError(f"mutant escaped ({label}): returned {result}, expected {expected}")

    print(
        f"neon_atlas_contract_emitted_check: PASS - {source_checks} source checks, "
        f"{ASSERTIONS} emitted assertions, {steps:,} baseline A64 instructions"
    )
    print(f"  {len(MUTANTS)} hostile mutations rejected in {mutant_steps:,} emitted instructions")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (AssertionError, KeyError) as exc:
        print("neon_atlas_contract_emitted_check: FAIL - " + str(exc))
        sys.exit(1)

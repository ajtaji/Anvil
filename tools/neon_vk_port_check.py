"""Compile and execute the Neon Vulkan canvas-port gate without board access."""

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "Anvil/Graphics/Vulkan/Tests/neon_vk_port_gate.pi4"
GEOMETRY = ROOT / "Anvil/Graphics/Vulkan/Tests/neon_vk_port_geometry_gate.pi4"
CHROME = ROOT / "Anvil/Graphics/Vulkan/neon_vk_chrome.pi4"
NEON_HOOK_GATE = ROOT / "Anvil/Graphics/Vulkan/Tests/neon_draw_backend_hook_gate.pi4"
DEFAULT_COMPILER = Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")

sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools/a64"))
import neon_vk_chrome_acceptance_check as gate  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, default=DEFAULT_COMPILER)
    args = parser.parse_args()
    compiler = args.compiler.resolve()
    if not compiler.is_file():
        parser.error(f"compiler not found: {compiler}")
    with tempfile.TemporaryDirectory(prefix="neon-vk-port-") as temp:
        work = Path(temp)
        production = CHROME.read_text(encoding="utf-8-sig")
        geometry = GEOMETRY.read_text(encoding="utf-8-sig")
        marker = "; @PRODUCTION_SPRITE_GEOMETRY@"
        if geometry.count(marker) != 1:
            raise AssertionError("sprite geometry marker missing or duplicated")
        geometry = geometry.replace(marker, "\n\n".join(
            gate.procedure_body(production, name)
            for name in ("nvcSpriteCornerQ8", "nvcSpriteTransformRegion")
        ))
        batch_marker = "; @PRODUCTION_SPRITE_BATCH@"
        if geometry.count(batch_marker) != 1:
            raise AssertionError("sprite batch marker missing or duplicated")
        geometry = geometry.replace(batch_marker, "\n\n".join(
            gate.procedure_body(production, name)
            for name in ("NeonVkChromeSpriteBatchBegin", "NeonVkChromeSpriteBatchAdd", "NeonVkChromeSpriteBatchEnd")
        ))
        geometry_source = work / "neon_vk_port_geometry_gate.pi4"
        geometry_source.write_text(geometry, encoding="utf-8")
        hook = NEON_HOOK_GATE.read_text(encoding="utf-8-sig")
        entry = "Procedure.i Main()"
        if hook.count(entry) != 1:
            raise AssertionError("Neon hook gate entry changed")
        image_stubs = """
Procedure.i NeonVkChromeImageSpriteReplaceId(id.i, *pixels, width.i, height.i) : ProcedureReturn 0 : EndProcedure
Procedure.i NeonVkChromeImageSpriteReplaceBGRAId(id.i, *pixels, width.i, height.i) : ProcedureReturn 0 : EndProcedure
Procedure.i NeonVkChromeImageSpriteGenerationId(id.i) : ProcedureReturn 1 : EndProcedure
Procedure.i NeonVkChromeImageSpriteClearId(id.i) : ProcedureReturn 0 : EndProcedure
Procedure.i NeonVkChromeImageSpriteDrawTransformId(id.i, x.i, y.i, sourceX.i, sourceY.i, sourceW.i, sourceH.i, drawW.i, drawH.i, colour.i, angleQ16.i, cameraX.i, cameraY.i, zoomQ16.i, ignoreCamera.i) : ProcedureReturn 0 : EndProcedure
Procedure.i NeonVkChromeSpriteBatchBegin() : ProcedureReturn 0 : EndProcedure
Procedure.i NeonVkChromeSpriteBatchAdd(id.i, x.i, y.i, sourceX.i, sourceY.i, sourceW.i, sourceH.i, drawW.i, drawH.i, colour.i, angleQ16.i, cameraX.i, cameraY.i, zoomQ16.i, ignoreCamera.i) : ProcedureReturn 0 : EndProcedure
Procedure.i NeonVkChromeSpriteBatchEnd() : ProcedureReturn 0 : EndProcedure
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_port.pi4"
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_sprite_port.pi4"
"""
        hook_source = work / "neon_vk_port_real_neon_gate.pi4"
        hook_source.write_text("EnableFloatingPoint\n" + hook.replace(entry, image_stubs + entry), encoding="utf-8")
        env = dict(os.environ, PMF_ROOT=str(ROOT))
        a64 = gate.load_interpreter(ROOT / "tools/a64/a64_interp.py")
        base = a64.A64

        class FloatingPointA64(base):
            def __init__(self):
                super().__init__()
                self.enable_system_registers(el=2)

        a64.A64 = FloatingPointA64
        for label, source in (("canvas port", SOURCE), ("production sprite geometry", geometry_source), ("real Neon include", hook_source)):
            image = work / (source.stem + ".img")
            run = subprocess.run(
                [str(compiler), "--compile", str(source), "-t", "pi4", "-s",
                 "--entry-returns", "--load-addr", "0x400000", "--bss-addr", "0x800000",
                 "--stack-addr", "0x3000000", "-o", str(image)],
                cwd=ROOT, env=env, capture_output=True, text=True,
            )
            if run.returncode or not image.is_file():
                raise AssertionError(f"{label} compilation failed:\n{run.stdout}\n{run.stderr}")
            result, steps = gate.execute(a64, image, 3_000_000)
            if result != 0:
                raise AssertionError(f"{label} assertion {result} failed after {steps:,} instructions")
            print(f"PASS: Neon Vulkan {label} ({steps:,} emitted A64 instructions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

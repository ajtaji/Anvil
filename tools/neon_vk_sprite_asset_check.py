"""Compile and execute the bounded Neon sprite asset bridge without a board."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "Anvil/Graphics/Vulkan/Tests/neon_vk_port_gate.pi4"
COMPILER = Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")

sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools/a64"))
import neon_vk_chrome_acceptance_check as gate  # noqa: E402


TEST_BODY = r'''
Global nvpFileBytes.i
Global nvpFileSize.i
Global nvpFileOpen.i
Global nvpFileCloses.i
Global nvpFileReadFail.i
Global Dim nvpBmp24.a[80]
Global Dim nvpBmp32.a[64]
Global Dim nvpScratch.a[128]
Global Dim nvpRgba.a[64]
Global Dim nvpMask.a[16]
Global Dim nvpRaw.a[64]

Procedure.i HwFileOpen(*path)
  If nvpFileSize < 1 : ProcedureReturn 0 : EndIf
  nvpFileOpen = 1
  ProcedureReturn 1
EndProcedure

Procedure.i HwFileSize()
  ProcedureReturn nvpFileSize
EndProcedure

Procedure.i HwFileReadAt(offset.i, *target, count.i)
  Protected i.i
  If nvpFileReadFail = 1 : ProcedureReturn -1 : EndIf
  If nvpFileReadFail = 2 : ProcedureReturn 0 : EndIf
  If offset >= nvpFileSize : ProcedureReturn 0 : EndIf
  If count > 3 : count = 3 : EndIf
  For i = 0 To count - 1
    PokeA(*target + i, PeekA(nvpFileBytes + offset + i))
  Next
  ProcedureReturn count
EndProcedure

Procedure HwFileClose()
  nvpFileOpen = 0 : nvpFileCloses = nvpFileCloses + 1
EndProcedure

XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_port.pi4"
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_sprite_port.pi4"
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_sprite_asset.pi4"

Procedure nvpTestPut16(*target, value.i)
  PokeA(*target, value & 255) : PokeA(*target + 1, (value >> 8) & 255)
EndProcedure

Procedure nvpTestPut32(*target, value.i)
  PokeA(*target, value & 255) : PokeA(*target + 1, (value >> 8) & 255)
  PokeA(*target + 2, (value >> 16) & 255) : PokeA(*target + 3, (value >> 24) & 255)
EndProcedure

Procedure.i Main()
  Protected sprite.NeonVkPortSpriteRef
  Protected calls.i, i.i
  ; Two-by-two bottom-up 24-bit BMP. Every 6-byte row has two pad bytes.
  PokeA(@nvpBmp24[0], 66) : PokeA(@nvpBmp24[1], 77)
  nvpTestPut32(@nvpBmp24[2], 70) : nvpTestPut32(@nvpBmp24[10], 54)
  nvpTestPut32(@nvpBmp24[14], 40) : nvpTestPut32(@nvpBmp24[18], 2)
  nvpTestPut32(@nvpBmp24[22], 2) : nvpTestPut16(@nvpBmp24[26], 1)
  nvpTestPut16(@nvpBmp24[28], 24)
  ; Bottom row: blue, white. Top row: red, green.
  PokeA(@nvpBmp24[54], 255)
  PokeA(@nvpBmp24[57], 255) : PokeA(@nvpBmp24[58], 255) : PokeA(@nvpBmp24[59], 255)
  PokeA(@nvpBmp24[64], 255)
  PokeA(@nvpBmp24[66], 255)
  If NeonVkPortSpriteLoadMemory(@sprite, 2, @nvpBmp24[0], 70, @nvpRgba[0], 16, $0000FF00, @nvpMask[0], 4) <> 0 : ProcedureReturn 1 : EndIf
  If sprite\id <> 2 Or sprite\width <> 2 Or sprite\height <> 2 : ProcedureReturn 2 : EndIf
  If (nvpAssetU32(@nvpRgba[0]) & $FFFFFFFF) <> $FF0000FF : ProcedureReturn 3 : EndIf
  If (nvpAssetU32(@nvpRgba[4]) & $FFFFFFFF) <> 0 : ProcedureReturn 4 : EndIf
  If (nvpAssetU32(@nvpRgba[8]) & $FFFFFFFF) <> $FFFF0000 : ProcedureReturn 5 : EndIf
  If (nvpAssetU32(@nvpRgba[12]) & $FFFFFFFF) <> $FFFFFFFF : ProcedureReturn 6 : EndIf
  If (PeekA(@nvpMask[0]) & 255) <> 1 Or (PeekA(@nvpMask[1]) & 255) <> 0 Or (PeekA(@nvpMask[2]) & 255) <> 1 Or (PeekA(@nvpMask[3]) & 255) <> 1 : ProcedureReturn 7 : EndIf

  ; File path must handle short reads and close before decoding/uploading.
  nvpFileBytes = @nvpBmp24[0] : nvpFileSize = 70
  If NeonVkPortSpriteLoadFile(@sprite, 3, @nvpRaw[0], @nvpScratch[0], 128, @nvpRgba[0], 16, -1, 0, 0) <> 0 : ProcedureReturn 8 : EndIf
  If nvpFileOpen <> 0 Or nvpFileCloses <> 1 Or sprite\id <> 3 Or (nvpAssetU32(@nvpRgba[4]) & $FFFFFFFF) <> $FF00FF00 : ProcedureReturn 9 : EndIf
  nvpFileReadFail = 1 : calls = nvpTestSpriteUploadCalls
  If NeonVkPortSpriteLoadFile(@sprite, 4, @nvpRaw[0], @nvpScratch[0], 128, @nvpRgba[0], 16, -1, 0, 0) <> #NEON_VK_ASSET_ERR_IO : ProcedureReturn 10 : EndIf
  If nvpFileOpen <> 0 Or nvpFileCloses <> 2 Or sprite\id <> 3 Or nvpTestSpriteUploadCalls <> calls : ProcedureReturn 11 : EndIf
  nvpFileReadFail = 2
  If NeonVkPortSpriteLoadFile(@sprite, 4, @nvpRaw[0], @nvpScratch[0], 128, @nvpRgba[0], 16, -1, 0, 0) <> #NEON_VK_ASSET_ERR_TRUNCATED : ProcedureReturn 26 : EndIf
  If nvpFileOpen <> 0 Or nvpFileCloses <> 3 Or sprite\id <> 3 Or nvpTestSpriteUploadCalls <> calls : ProcedureReturn 27 : EndIf
  nvpFileReadFail = 0
  nvpFileSize = 129
  If NeonVkPortSpriteLoadFile(@sprite, 4, @nvpRaw[0], @nvpScratch[0], 128, @nvpRgba[0], 16, -1, 0, 0) <> #NEON_VK_ASSET_ERR_CAPACITY : ProcedureReturn 28 : EndIf
  If nvpFileOpen <> 0 Or nvpFileCloses <> 4 Or sprite\id <> 3 Or nvpTestSpriteUploadCalls <> calls : ProcedureReturn 29 : EndIf
  nvpFileSize = 70

  ; A top-down 32-bit BMP carries an explicit half-alpha byte, then zero.
  PokeA(@nvpBmp32[0], 66) : PokeA(@nvpBmp32[1], 77)
  nvpTestPut32(@nvpBmp32[2], 62) : nvpTestPut32(@nvpBmp32[10], 54)
  nvpTestPut32(@nvpBmp32[14], 40) : nvpTestPut32(@nvpBmp32[18], 1)
  nvpTestPut32(@nvpBmp32[22], -2) : nvpTestPut16(@nvpBmp32[26], 1)
  nvpTestPut16(@nvpBmp32[28], 32)
  PokeA(@nvpBmp32[54], 30) : PokeA(@nvpBmp32[55], 20) : PokeA(@nvpBmp32[56], 10) : PokeA(@nvpBmp32[57], 128)
  PokeA(@nvpBmp32[58], 60) : PokeA(@nvpBmp32[59], 50) : PokeA(@nvpBmp32[60], 40)
  If NeonVkPortSpriteLoadMemory(@sprite, 4, @nvpBmp32[0], 62, @nvpRgba[0], 8, -1, @nvpMask[0], 2) <> 0 : ProcedureReturn 12 : EndIf
  If (nvpAssetU32(@nvpRgba[0]) & $FFFFFFFF) <> $801E140A Or (nvpAssetU32(@nvpRgba[4]) & $FFFFFFFF) <> $003C3228 : ProcedureReturn 13 : EndIf
  If (PeekA(@nvpMask[0]) & 255) <> 1 Or (PeekA(@nvpMask[1]) & 255) <> 0 : ProcedureReturn 14 : EndIf

  calls = nvpTestSpriteUploadCalls
  If NeonVkPortSpriteLoadMemory(@sprite, 5, @nvpBmp24[0], 69, @nvpRgba[0], 16, -1, 0, 0) <> #NEON_VK_ASSET_ERR_TRUNCATED : ProcedureReturn 15 : EndIf
  nvpTestPut32(@nvpBmp24[30], 1)
  If NeonVkPortSpriteLoadMemory(@sprite, 5, @nvpBmp24[0], 70, @nvpRgba[0], 16, -1, 0, 0) <> #NEON_VK_ASSET_ERR_FORMAT : ProcedureReturn 16 : EndIf
  nvpTestPut32(@nvpBmp24[30], 0)
  If NeonVkPortSpriteLoadMemory(@sprite, 5, @nvpBmp24[0], 70, @nvpRgba[0], 15, -1, 0, 0) <> #NEON_VK_ASSET_ERR_CAPACITY : ProcedureReturn 17 : EndIf
  If NeonVkPortSpriteLoadMemory(@sprite, 5, @nvpBmp24[0], 70, @nvpBmp24[0], 80, -1, 0, 0) <> #NEON_VK_ASSET_ERR_ARGUMENT : ProcedureReturn 18 : EndIf
  PokeA(@nvpBmp24[0], 137)
  If NeonVkPortSpriteLoadMemory(@sprite, 5, @nvpBmp24[0], 70, @nvpRgba[0], 16, -1, 0, 0) <> #NEON_VK_ASSET_ERR_FORMAT : ProcedureReturn 19 : EndIf
  PokeA(@nvpBmp24[0], 66)
  If nvpTestSpriteUploadCalls <> calls Or sprite\id <> 4 : ProcedureReturn 20 : EndIf

  ; Decoded RGBA is a usable independent path, including in-place keying.
  PokeA(@nvpRaw[0], 10) : PokeA(@nvpRaw[1], 20) : PokeA(@nvpRaw[2], 30) : PokeA(@nvpRaw[3], 80)
  PokeA(@nvpRaw[4], 1) : PokeA(@nvpRaw[5], 2) : PokeA(@nvpRaw[6], 3) : PokeA(@nvpRaw[7], 255)
  If NeonVkPortSpriteLoadRGBA(@sprite, 6, @nvpRaw[0], 8, 2, 1, @nvpRaw[0], 8, $001E140A, @nvpMask[0], 2) <> 0 : ProcedureReturn 21 : EndIf
  If (nvpAssetU32(@nvpRaw[0]) & $FFFFFFFF) <> 0 Or (nvpAssetU32(@nvpRaw[4]) & $FFFFFFFF) <> $FF030201 : ProcedureReturn 22 : EndIf
  If (PeekA(@nvpMask[0]) & 255) <> 0 Or (PeekA(@nvpMask[1]) & 255) <> 1 : ProcedureReturn 23 : EndIf
  calls = nvpTestSpriteUploadCalls
  If NeonVkPortSpriteLoadRGBA(@sprite, 7, @nvpRaw[0], 8, 2, 1, @nvpRaw[1], 8, -1, 0, 0) <> #NEON_VK_ASSET_ERR_ARGUMENT : ProcedureReturn 24 : EndIf
  If nvpTestSpriteUploadCalls <> calls Or sprite\id <> 6 : ProcedureReturn 25 : EndIf
  If NeonVkPortSpriteLoadRGBA(@sprite, 7, @nvpRaw[0], 52, 13, 1, @nvpRgba[0], 52, -1, 0, 0) <> -99 : ProcedureReturn 30 : EndIf
  If sprite\id <> 6 Or nvpTestSpriteUploadCalls <> calls + 1 : ProcedureReturn 31 : EndIf
  calls = nvpTestSpriteUploadCalls
  If NeonVkPortSpriteLoadRGBA(@sprite, 7, @nvpRaw[0], 8, 2, 1, @nvpRgba[0], 8, -1, @nvpRaw[1], 2) <> #NEON_VK_ASSET_ERR_ARGUMENT : ProcedureReturn 32 : EndIf
  If NeonVkPortSpriteLoadRGBA(@sprite, 7, @nvpRaw[0], 8, 2, 1, @nvpRgba[0], 8, -1, @nvpRgba[1], 2) <> #NEON_VK_ASSET_ERR_ARGUMENT : ProcedureReturn 33 : EndIf
  If NeonVkPortSpriteLoadMemory(@sprite, 7, @nvpBmp24[0], 70, @nvpRgba[0], 16, -1, @nvpBmp24[1], 4) <> #NEON_VK_ASSET_ERR_ARGUMENT : ProcedureReturn 34 : EndIf
  If NeonVkPortSpriteLoadMemory(@sprite, 7, @nvpBmp24[0], 70, @nvpRgba[0], 16, -1, @nvpRgba[1], 4) <> #NEON_VK_ASSET_ERR_ARGUMENT : ProcedureReturn 35 : EndIf
  If nvpTestSpriteUploadCalls <> calls Or sprite\id <> 6 : ProcedureReturn 36 : EndIf
  If NeonVkPortSpriteLoadMemory(@sprite, 0, @nvpBmp24[0], 70, @nvpRgba[0], 16, -1, 0, 0) <> #NEON_VK_ASSET_ERR_ARGUMENT : ProcedureReturn 37 : EndIf
  nvpBatchActive = 1
  If NeonVkPortSpriteLoadRGBA(@sprite, 7, @nvpRaw[0], 8, 2, 1, @nvpRgba[0], 8, -1, 0, 0) <> #NEON_VK_PORT_ERR_BATCH : ProcedureReturn 38 : EndIf
  nvpBatchActive = 0
  If nvpTestSpriteUploadCalls <> calls Or sprite\id <> 6 : ProcedureReturn 39 : EndIf
  If NeonVkPortSpriteLoadRGBA(@sprite, 7, @nvpRaw[0], 7, 2, 1, @nvpRgba[0], 8, -1, 0, 0) <> #NEON_VK_ASSET_ERR_CAPACITY : ProcedureReturn 40 : EndIf
  If nvpTestSpriteUploadCalls <> calls Or sprite\id <> 6 : ProcedureReturn 41 : EndIf
  ProcedureReturn 0
EndProcedure
'''


def main() -> int:
    if not COMPILER.is_file():
        raise SystemExit(f"compiler not found: {COMPILER}")
    prelude, separator, _ = GATE.read_text(encoding="utf-8-sig").partition(
        'XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_port.pi4"'
    )
    if not separator:
        raise AssertionError("port gate prelude changed")
    with tempfile.TemporaryDirectory(prefix="neon-vk-asset-") as temp:
        source = Path(temp) / "neon_vk_sprite_asset_gate.pi4"
        image = Path(temp) / "neon_vk_sprite_asset_gate.img"
        source.write_text(prelude + TEST_BODY, encoding="utf-8")
        run = subprocess.run(
            [str(COMPILER), "--compile", str(source), "-t", "pi4", "-s",
             "--entry-returns", "--load-addr", "0x400000", "--bss-addr", "0x800000",
             "--stack-addr", "0x3000000", "-o", str(image)],
            cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
            capture_output=True, text=True,
        )
        if run.returncode or not image.is_file():
            raise AssertionError(f"asset gate compilation failed:\n{run.stdout}\n{run.stderr}")
        a64 = gate.load_interpreter(ROOT / "tools/a64/a64_interp.py")
        base = a64.A64

        class FloatingPointA64(base):
            def __init__(self):
                super().__init__()
                self.enable_system_registers(el=2)

        a64.A64 = FloatingPointA64
        result, steps = gate.execute(a64, image, 3_000_000)
        if result:
            raise AssertionError(f"asset gate assertion {result} failed after {steps:,} instructions")
        print(f"PASS: Neon Vulkan sprite asset gate ({steps:,} emitted A64 instructions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Check early Pi4 Vulkan boot order and execute the geometry resume path."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import tempfile

from a64_interp import A64


ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "RaspberryPi4" / "Board" / "board.pi4"
SCREEN = ROOT / "RaspberryPi4" / "Board" / "screen_cmd.pi4"
VULKAN = ROOT / "RaspberryPi4" / "Board" / "vulkan_console.pi4"
FIXTURE = ROOT / "tools" / "a64" / "early_vulkan_boot_check.pi4"
LOAD = 0x200000
STACK = 0x400000
RESULT = 0x300000
RETURN = 0x7FF00000


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, default=os.environ.get("PMF_COMPILER"),
                        required="PMF_COMPILER" not in os.environ)
    args = parser.parse_args()

    board = BOARD.read_text(encoding="utf-8")
    boot_start = board.index("BootTimingMark(#BTM_TOUCH_END")
    boot_end = board.index("ScreenEarlyLogFinish()", boot_start)
    boot = board[boot_start:boot_end]
    start = boot.index("vulkanBootRc = VulkanConsoleStart()")
    pump = boot.index("VulkanConsolePump()", start)
    presented = boot.index("If avcFramePresented <> 0", pump)
    config = boot.index("BootConfigUp()", presented)
    geometry = boot.index("ScreenApplyStoredGeometry()", config)
    if not start < pump < presented < config < geometry:
        raise AssertionError("Vulkan first frame must precede USB/storage and stored geometry")

    screen = SCREEN.read_text(encoding="utf-8")
    begin = screen.index("Procedure.i ScreenApplyStoredGeometry()")
    end = screen.index("\nEndProcedure", begin)
    apply_geometry = screen[begin:end]
    if apply_geometry.index("gScreenDeferFirstFrame = 1") > apply_geometry.index("VulkanConsoleStop()"):
        raise AssertionError("geometry stop can expose CPU painter")
    if apply_geometry.count("ScreenStoredGeometryVulkanResume(hadVulkan)") != 6:
        raise AssertionError("not every changed-geometry return path resumes Vulkan")
    stop = VULKAN.read_text(encoding="utf-8")
    begin = stop.index("Procedure.i VulkanConsoleStop()")
    end = stop.index("\nEndProcedure", begin)
    stop = stop[begin:end]
    if stop.count("If gScreen <> 0 And gScreenDeferFirstFrame = 0") != 2:
        raise AssertionError("Vulkan stop may paint a CPU frame while deferred")

    begin = screen.index("Procedure.i ScreenStoredGeometryVulkanResume(hadVulkan.i)")
    end = screen.index("\nEndProcedure", begin) + len("\nEndProcedure")
    resume = screen[begin:end]
    resume = "\n".join(line for line in resume.splitlines()
                       if not line.lstrip().startswith(("Print(", "PrintN(", "PrintDec(")))
    fixture = FIXTURE.read_text(encoding="utf-8").replace("__RESUME__", resume)
    with tempfile.TemporaryDirectory(prefix="anvil-early-vulkan-") as directory:
        temp = Path(directory)
        source = temp / "early_vulkan.pi4"
        image = temp / "early_vulkan.img"
        source.write_text(fixture, encoding="utf-8")
        command = [str(args.compiler), "--compile", str(source), "-t", "pi4",
                   "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
                   "--entry-returns", "-o", str(image)]
        result = subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, check=False)
        if result.returncode or "pmfc: OK" not in result.stdout or not image.is_file():
            raise RuntimeError("fixture compile failed:\n" + result.stdout)
        cpu = A64()
        for index, byte in enumerate(image.read_bytes()):
            cpu.memory[LOAD + index] = byte
        cpu.pc = LOAD
        cpu.sp = STACK
        cpu.x[30] = RETURN
        for steps in range(300000):
            if cpu.pc == RETURN:
                break
            cpu.step()
        else:
            raise RuntimeError("geometry resume exceeded its execution bound")
        status = sum(cpu.memory.get(RESULT + index, 0) << (8 * index) for index in range(8))
        if status:
            raise AssertionError(f"geometry resume returned failure {status} after {steps} steps")
    print(f"PASS: Vulkan first frame precedes USB/storage; geometry resume owns GPU or stays deferred ({steps} A64 steps)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

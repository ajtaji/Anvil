#!/usr/bin/env python3
"""Emitted-A64 proof of private particle CSD-output synchronization."""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
GATE = ROOT / "Anvil/Graphics/Vulkan/Tests/neon_particle_sync_foundation_gate.pi4"
COMPILER = pathlib.Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")
LOAD, STACK, END = 0x80000, 0x8000000, 0xDEAD0000
REPORT = 0x06000000

sys.path.insert(0, str(ROOT / "tools/a64"))
import a64_interp as a64  # noqa: E402


def get64(cpu: a64.A64, address: int) -> int:
    value = sum(cpu.memory.get(address + k, 0) << (8 * k) for k in range(8))
    return value if value < (1 << 63) else value - (1 << 64)


def main() -> None:
    api = (ROOT / "Anvil/Graphics/Vulkan/vk_api.pbi").read_text()
    dispatch = (ROOT / "Anvil/Graphics/Vulkan/vk_dispatch.pbi").read_text()
    if "Procedure vkCmdDispatch(" in api or 'avkDispatchName(*pName, "vkCmdDispatch")' in dispatch:
        raise AssertionError("public vkCmdDispatch must remain unavailable")
    if "If AnvilVkBackendCanDraw() <> 0" not in api or "#VK_QUEUE_COMPUTE_BIT" in api.split("Procedure vkGetPhysicalDeviceQueueFamilyProperties", 1)[1].split("EndProcedure", 1)[0]:
        raise AssertionError("queue family must continue to omit compute")
    with tempfile.TemporaryDirectory(prefix="anvil_compute_sync_") as tmp:
        image = pathlib.Path(tmp) / "gate.img"
        command = [str(COMPILER), "--compile", GATE.relative_to(ROOT).as_posix(),
                   "-t", "pi4", "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
                   "--entry-returns", "-o", str(image), "-s"]
        env = os.environ.copy()
        env["PMF_ROOT"] = str(ROOT)
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                                text=True, timeout=120, check=False)
        if result.returncode or "pmfc: OK" not in result.stdout:
            raise AssertionError("gate compile failed:\n" + result.stdout + result.stderr)
        cpu = a64.A64()
        for i, byte in enumerate(image.read_bytes()):
            cpu.memory[LOAD + i] = byte
        a64.attach_symbols(cpu, image, LOAD)
        cpu.pc, cpu.sp, cpu.x[30] = LOAD, STACK, END
        for steps in range(15_000_000):
            if cpu.pc == END:
                break
            cpu.step()
        else:
            raise AssertionError("emitted gate did not return within 15,000,000 instructions")
        if cpu.x[0] != 0:
            raise AssertionError(f"gate setup returned {cpu.x[0]}")
        magic, checks, fails = (get64(cpu, REPORT + 8 * i) for i in range(3))
        if magic != 0x4E535934 or checks < 30 or fails:
            raise AssertionError(f"gate report magic={magic:#x} checks={checks} failures={fails} firstFailure={get64(cpu, REPORT + 24)}")
        print(f"PASS: private compute-output sync foundation, {checks} emitted checks, {steps:,} A64 instructions")


if __name__ == "__main__":
    main()

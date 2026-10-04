#!/usr/bin/env python3
"""Run the Pi 4 backend GPU lease state gate in emitted A64."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "Anvil/Graphics/Vulkan/Tests/vulkan_pi4_gpu_lease_gate.pi4"
COMPILER = Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")
LOAD, STACK, END, REPORT = 0x80000, 0x8000000, 0xDEAD0000, 0x06100000
EXPECTED = [0, 0, 1, 1, 0, 0, 0, 1, 1, 0, 1, 2, 1, -2, 0, 0, -2]
sys.path.insert(0, str(ROOT / "tools/a64"))
import a64_interp as a64  # noqa: E402


def get64(cpu: a64.A64, address: int) -> int:
    value = sum(cpu.memory.get(address + k, 0) << (8 * k) for k in range(8))
    return value if value < (1 << 63) else value - (1 << 64)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="anvil_pi4_gpu_lease_") as tmp:
        image = Path(tmp) / "gate.img"
        command = [str(COMPILER), "--compile", GATE.relative_to(ROOT).as_posix(),
                   "-t", "pi4", "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
                   "--entry-returns", "-o", str(image), "-s"]
        env = dict(os.environ, PMF_ROOT=str(ROOT))
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                                text=True, timeout=120, check=False)
        if result.returncode or "pmfc: OK" not in result.stdout:
            raise AssertionError("lease gate compile failed:\n" + result.stdout + result.stderr)
        cpu = a64.A64()
        for index, byte in enumerate(image.read_bytes()):
            cpu.memory[LOAD + index] = byte
        a64.attach_symbols(cpu, image, LOAD)
        cpu.pc, cpu.sp, cpu.x[30] = LOAD, STACK, END
        for steps in range(12_000_000):
            if cpu.pc == END:
                break
            cpu.step()
        else:
            raise AssertionError("lease gate did not return within 12,000,000 A64 steps")
        report = [get64(cpu, REPORT + 8 * index) for index in range(len(EXPECTED))]
        if cpu.x[0] != 0 or report != EXPECTED:
            raise AssertionError(f"lease transition mismatch: return={cpu.x[0]}, report={report}")
        print(f"vulkan_pi4_gpu_lease_check: PASS - {steps:,} emitted A64 instructions; idle, owners and quarantine")


if __name__ == "__main__":
    main()

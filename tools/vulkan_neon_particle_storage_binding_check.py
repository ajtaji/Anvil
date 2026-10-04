#!/usr/bin/env python3
"""Emitted-A64 desk proof of passive Pi 4 particle storage bindings."""
from __future__ import annotations

import hashlib
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
GATE = ROOT / "Anvil/Graphics/Vulkan/Tests/neon_particle_storage_binding_gate.pi4"
SPV = ROOT / "Anvil/Graphics/Vulkan/Tests/neon_particle_expand.spv"
SHA = "0d5ced6e1a5e9a91ffed258d860912d53a6a7fc832dfc20ffad5b549a367660a"
COMPILER = pathlib.Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")
LOAD, STACK, END = 0x80000, 0x8000000, 0xDEAD0000
ARG, REPORT, MODULE = 0x06000000, 0x06100000, 0x06020000
sys.path.insert(0, str(ROOT / "tools/a64"))
import a64_interp as a64  # noqa: E402


def put64(cpu, address: int, value: int) -> None:
    for k in range(8):
        cpu.memory[address + k] = (value >> (8 * k)) & 255


def get64(cpu, address: int) -> int:
    return sum(cpu.memory.get(address + k, 0) << (8 * k) for k in range(8))


def signed(value: int) -> int:
    return value if value < (1 << 63) else value - (1 << 64)


def main() -> None:
    blob = SPV.read_bytes()
    if hashlib.sha256(blob).hexdigest() != SHA:
        raise AssertionError("tracked particle SPIR-V changed")
    with tempfile.TemporaryDirectory(prefix="anvil_storage_binding_") as tmp:
        image_path = pathlib.Path(tmp) / "gate.img"
        command = [str(COMPILER), "--compile", GATE.relative_to(ROOT).as_posix(),
                   "-t", "pi4", "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
                   "--entry-returns", "-o", str(image_path), "-s"]
        env = os.environ.copy()
        env["PMF_ROOT"] = str(ROOT)
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                                text=True, timeout=120, check=False)
        if result.returncode or "pmfc: OK" not in result.stdout:
            raise AssertionError("gate compile failed:\n" + result.stdout + result.stderr)
        cpu = a64.A64()
        for i, byte in enumerate(image_path.read_bytes()):
            cpu.memory[LOAD + i] = byte
        a64.attach_symbols(cpu, image_path, LOAD)
        for i, byte in enumerate(blob):
            cpu.memory[MODULE + i] = byte
        put64(cpu, ARG, MODULE)
        put64(cpu, ARG + 8, len(blob))
        cpu.pc, cpu.sp, cpu.x[30] = LOAD, STACK, END
        for steps in range(8_000_000):
            if cpu.pc == END:
                break
            cpu.step()
        else:
            raise AssertionError("emitted gate did not return within 8,000,000 instructions")
        if cpu.x[0] != 0:
            raise AssertionError(f"gate setup failed at step {cpu.x[0]}")
        values = [signed(get64(cpu, REPORT + 8 * i)) for i in range(34)]
        expected = {0: 0x53425034, 1: 0, 2: 2, 3: 0,
                    5: 768, 7: 2304, 8: 2304, 9: 16, 11: -20001,
                    12: -20001, 13: -20001, 14: -20001, 15: -20002,
                    16: -20005, 17: -20005, 18: -20001, 19: -20001,
                    20: -20002, 21: -20002, 22: 1, 23: -20001,
                    24: 0, 25: 0, 26: 268435456, 27: 2, 28: 2,
                    29: 4, 30: -20001, 31: -1000069000, 32: 1,
                    33: -20003}
        for index, wanted in expected.items():
            if values[index] != wanted:
                raise AssertionError(f"report[{index}]={values[index]}, expected {wanted}; all={values}")
        if values[4] != values[10] or values[6] != values[10] + 4096:
            raise AssertionError(f"descriptor base/offset mismatch: {values}")
        if values[4] == 0 or values[6] <= values[4] + values[5]:
            raise AssertionError("live input/output spans are not distinct")
        print(f"vulkan_neon_particle_storage_binding_check: PASS - {steps:,} emitted A64 instructions, "
              "real set 0 storage descriptors, 48/144-byte group capacity, "
              "15 hostile binding/preflight cases and queried storage limits")


if __name__ == "__main__":
    main()

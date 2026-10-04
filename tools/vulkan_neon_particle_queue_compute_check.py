#!/usr/bin/env python3
"""Emitted-A64 proof of internal compute queue flight and quarantine."""
from __future__ import annotations

import hashlib
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
GATE = ROOT / "Anvil/Graphics/Vulkan/Tests/neon_particle_queue_compute_gate.pi4"
SPV = ROOT / "Anvil/Graphics/Vulkan/Tests/neon_particle_expand.spv"
SHA = "0d5ced6e1a5e9a91ffed258d860912d53a6a7fc832dfc20ffad5b549a367660a"
COMPILER = pathlib.Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")
LOAD, STACK, END = 0x80000, 0x8000000, 0xDEAD0000
ARG, MODULE, REPORT = 0x06000000, 0x06020000, 0x06100000
sys.path.insert(0, str(ROOT / "tools/a64"))
import a64_interp as a64  # noqa: E402


def put64(cpu, address: int, value: int) -> None:
    for k in range(8):
        cpu.memory[address + k] = (value >> (8 * k)) & 255


def get64(cpu, address: int) -> int:
    value = sum(cpu.memory.get(address + k, 0) << (8 * k) for k in range(8))
    return value if value < (1 << 63) else value - (1 << 64)


def main() -> None:
    blob = SPV.read_bytes()
    if hashlib.sha256(blob).hexdigest() != SHA:
        raise AssertionError("tracked particle SPIR-V changed")
    api = (ROOT / "Anvil/Graphics/Vulkan/vk_api.pbi").read_text()
    dispatch = (ROOT / "Anvil/Graphics/Vulkan/vk_dispatch.pbi").read_text()
    if "Procedure vkCmdDispatch(" in api or 'avkDispatchName(*pName, "vkCmdDispatch")' in dispatch:
        raise AssertionError("vkCmdDispatch must remain unavailable")
    with tempfile.TemporaryDirectory(prefix="anvil_dispatch_record_") as tmp:
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
        total_steps = 0
        for mode in (0, 1, 2):
            cpu = a64.A64()
            for i, byte in enumerate(image.read_bytes()):
                cpu.memory[LOAD + i] = byte
            a64.attach_symbols(cpu, image, LOAD)
            for i, byte in enumerate(blob):
                cpu.memory[MODULE + i] = byte
            put64(cpu, ARG, MODULE)
            put64(cpu, ARG + 8, len(blob))
            put64(cpu, ARG + 16, mode)
            cpu.pc, cpu.sp, cpu.x[30] = LOAD, STACK, END
            for steps in range(35_000_000):
                if cpu.pc == END:
                    break
                cpu.step()
            else:
                raise AssertionError("emitted gate did not return within 35,000,000 instructions")
            total_steps += steps
            values = [get64(cpu, REPORT + 8 * i) for i in range(41)]
            if cpu.x[0] != 0:
                raise AssertionError(f"gate mode {mode} setup failed at return {cpu.x[0]}; report={values}")
            expected = {0: 0x44525034, 1: 0, 2: 1, 3: 1, 4: 16,
                        7: 2304, 8: 1, 9: 0, 10: 0, 11: 1, 12: 1}
            if mode == 0:
                expected.update({13: -4, 14: 1, 15: -20004, 16: 1,
                                 17: -20004, 18: 1, 19: -4, 20: 1, 21: 1,
                                 22: 1, 23: -1, 24: -4, 25: 1})
            elif mode == 1:
                expected.update({26: -20004, 27: 1, 28: 0, 29: 1,
                                 30: -4, 31: 1, 32: 1, 33: -1})
            else:
                expected.update({34: -1, 35: -4, 36: 1,
                                 37: -4, 38: -4, 39: 1, 40: 1})
            for index, wanted in expected.items():
                if values[index] != wanted:
                    raise AssertionError(f"mode {mode} report[{index}]={values[index]}, expected {wanted}; all={values}")
            if values[5] != 0x06200000 or values[6] != values[5] + 4096:
                raise AssertionError(f"mode {mode} recorded descriptor addresses mismatch: {values}")
        print(f"vulkan_neon_particle_queue_compute_check: PASS - {total_steps:,} emitted A64 instructions; "
              "compute and graphics lease, completion, prelaunch refusal, stale binding, and quarantine")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Emitted-A64 proof of Pi 4 particle modules and internal typed pipelines."""
from __future__ import annotations

import hashlib
import os
import pathlib
import struct
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
GATE = ROOT / "Anvil/Graphics/Vulkan/Tests/neon_particle_public_pipeline_gate.pi4"
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
    dispatch = (ROOT / "Anvil/Graphics/Vulkan/vk_dispatch.pbi").read_text()
    if 'avkDispatchName(*pName, "vkCreateComputePipelines")' in dispatch:
        raise AssertionError("public compute pipeline must remain unavailable")
    if 'avkDispatchName(*pName, "vkCmdDispatch")' in dispatch:
        raise AssertionError("public vkCmdDispatch must remain unavailable")
    with tempfile.TemporaryDirectory(prefix="anvil_public_pipeline_") as tmp:
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
        for i, byte in enumerate(blob):
            cpu.memory[MODULE + i] = byte
        put64(cpu, ARG, MODULE)
        put64(cpu, ARG + 8, len(blob))
        cpu.pc, cpu.sp, cpu.x[30] = LOAD, STACK, END
        for steps in range(15_000_000):
            if cpu.pc == END:
                break
            cpu.step()
        else:
            raise AssertionError("emitted gate did not return within 15,000,000 instructions")
        if cpu.x[0] != 0:
            raise AssertionError(f"gate setup failed at return {cpu.x[0]}")
        values = [get64(cpu, REPORT + 8 * i) for i in range(30)]
        expected = {0: 0x50503434, 1: 0, 2: 36, 3: 16, 4: 1,
                    5: 0, 6: 0, 7: 0, 8: 1, 9: 36, 10: 1, 11: 1,
                    12: -20002, 13: -20001, 14: -20005,
                    15: -20005, 16: -20005, 17: -20003,
                    18: -8, 19: 1, 20: -8, 21: 1,
                    22: -20001, 25: 1, 26: 0, 27: 0, 28: -20001,
                    29: -20005}
        for index, wanted in expected.items():
            if values[index] != wanted:
                raise AssertionError(f"report[{index}]={values[index]}, expected {wanted}; all={values}")
        words = list(struct.unpack(f"<{len(blob)//4}I", blob))
        entries = []
        pos = 5
        while pos < len(words):
            count, opcode = words[pos] >> 16, words[pos] & 0xFFFF
            if count == 0 or pos + count > len(words):
                raise AssertionError("invalid fixture instruction span")
            if opcode == 15:
                entries.append(pos)
            pos += count
        if len(entries) != 1 or words[entries[0] + 3] != 0x6E69616D:
            raise AssertionError("fixture main entry selector changed")
        words[entries[0] + 3] = 0x006F6F66  # foo\0
        wrong_entry = struct.pack(f"<{len(words)}I", *words)
        mutant = a64.A64()
        for i, byte in enumerate(image.read_bytes()):
            mutant.memory[LOAD + i] = byte
        a64.attach_symbols(mutant, image, LOAD)
        for i, byte in enumerate(wrong_entry):
            mutant.memory[MODULE + i] = byte
        put64(mutant, ARG, MODULE)
        put64(mutant, ARG + 8, len(wrong_entry))
        mutant.pc, mutant.sp, mutant.x[30] = LOAD, STACK, END
        for mutant_steps in range(12_000_000):
            if mutant.pc == END:
                break
            mutant.step()
        else:
            raise AssertionError("wrong-entry module did not return")
        if mutant.x[0] != 1 or get64(mutant, REPORT + 8) == 0:
            raise AssertionError("public vkCreateShaderModule accepted a foo-only compute entry")
        print(f"vulkan_neon_particle_public_pipeline_check: PASS - {steps:,} emitted A64 instructions; "
              "public module, internal Pi4-lowerable 36-store pipeline, immutable IR, "
              "hostile entry/handle/layout/graph cases, and public pipeline refusal")


if __name__ == "__main__":
    main()

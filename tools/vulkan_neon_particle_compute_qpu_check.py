#!/usr/bin/env python3
"""Emitted-A64 proof that bounded compute IR generates the private Pi 4 QPU program."""
from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import struct
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
GATE = ROOT / "Anvil/Graphics/Vulkan/Tests/neon_particle_compute_qpu_gate.pi4"
FIXTURE = ROOT / "Anvil/Graphics/Vulkan/Tests/neon_particle_expand.spv"
SHA = "0d5ced6e1a5e9a91ffed258d860912d53a6a7fc832dfc20ffad5b549a367660a"
DEFAULT_COMPILER = pathlib.Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")
LOAD, STACK, END = 0x80000, 0x8000000, 0xDEAD0000
ARG, MODULE, REPORT = 0x06000000, 0x06020000, 0x06100000
PRIVATE, LOWERED, CHANGED, REFUSED = 0x06200000, 0x06201000, 0x06202000, 0x06203000
UNIFORM = 0x06204000

sys.path.insert(0, str(ROOT / "tools/a64"))
import a64_interp as a64  # noqa: E402
from v3d42_qpu_decode import decode_program  # noqa: E402


def put64(cpu, address: int, value: int) -> None:
    for byte in range(8):
        cpu.memory[address + byte] = (value >> (8 * byte)) & 255


def get64(cpu, address: int) -> int:
    return sum(cpu.memory.get(address + byte, 0) << (8 * byte) for byte in range(8))


def raw(cpu, address: int, size: int) -> bytes:
    return bytes(cpu.memory.get(address + byte, 0) for byte in range(size))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=pathlib.Path, default=DEFAULT_COMPILER)
    args = parser.parse_args()
    blob = FIXTURE.read_bytes()
    if hashlib.sha256(blob).hexdigest() != SHA:
        raise AssertionError("tracked particle SPIR-V changed")
    with tempfile.TemporaryDirectory(prefix="anvil_compute_qpu_") as tmp:
        image_path = pathlib.Path(tmp) / "gate.img"
        command = [str(args.compiler), "--compile", GATE.relative_to(ROOT).as_posix(),
                   "-t", "pi4", "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
                   "--entry-returns", "-o", str(image_path), "-s"]
        env = os.environ.copy()
        env["PMF_ROOT"] = str(ROOT)
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                                text=True, timeout=120, check=False)
        if result.returncode or "pmfc: OK" not in result.stdout:
            raise AssertionError("Pi 4 QPU gate compile failed:\n" + result.stdout + result.stderr)
        cpu = a64.A64()
        for index, byte in enumerate(image_path.read_bytes()):
            cpu.memory[LOAD + index] = byte
        a64.attach_symbols(cpu, image_path, LOAD)
        for index, byte in enumerate(blob):
            cpu.memory[MODULE + index] = byte
        put64(cpu, ARG, MODULE)
        put64(cpu, ARG + 8, len(blob))
        cpu.pc, cpu.sp, cpu.x[30] = LOAD, STACK, END
        for steps in range(12_000_000):
            if cpu.pc == END:
                break
            cpu.step()
        else:
            raise AssertionError("QPU gate did not return within 12,000,000 A64 steps")
        report = [get64(cpu, REPORT + 8 * index) for index in range(41)]
        if cpu.x[0] != 0 or report[:4] != [0x43515034, 0, 1, 0]:
            raise AssertionError(f"gate setup failed: return={cpu.x[0]}, report={report}")
        if report[5] != 32 or report[6] != 0 or report[7] != report[4]:
            raise AssertionError(f"private/lowered code size or uniform count mismatch: {report}")
        if report[8:11] != [1, 0, report[4]]:
            raise AssertionError(f"changed-source lower failed: {report}")
        if report[11] != 0 or report[12] == 0 or report[13] != 0xA5A5A5A5:
            raise AssertionError(f"unsupported constants were not refused before code write: {report}")
        if (report[14] != 0 or report[15] == 0 or report[16] != 0xA5A5A5A5
                or report[17] == 0 or report[18] != 0xA5A5A5A5
                or report[19] == 0 or report[20] != 0xA5A5A5A5):
            raise AssertionError(f"unsupported stride or invalid code span was accepted: {report}")
        if any(report[index] == 0 or report[index + 1] != 0xA5A5A5A5
               for index in (21, 23, 25, 27, 29, 39)):
            raise AssertionError(f"overlapping or overflowing data span was accepted: {report}")
        if any(report[index] == 0 or report[index + 1] != 0xA5A5A5A5
               for index in (31, 33, 35, 37)):
            raise AssertionError(f"out-of-window span was accepted: {report}")
        code_bytes = report[4]
        if code_bytes < 8 or code_bytes > 4096 or code_bytes % 8:
            raise AssertionError(f"invalid emitted code length: {code_bytes}")
        private = raw(cpu, PRIVATE, code_bytes)
        lowered = raw(cpu, LOWERED, code_bytes)
        changed = raw(cpu, CHANGED, code_bytes)
        if lowered != private:
            first = next(i for i, (a, b) in enumerate(zip(lowered, private)) if a != b)
            raise AssertionError(f"IR-emitted QPU bytes differ from private silicon-proven program at byte {first}")
        diff_words = [i for i in range(code_bytes // 8)
                      if changed[i * 8:(i + 1) * 8] != lowered[i * 8:(i + 1) * 8]]
        if len(diff_words) != 1:
            raise AssertionError(f"source-offset mutation changed {diff_words}, expected one QPU word")
        before = decode_program(lowered)[diff_words[0]]
        after = decode_program(changed)[diff_words[0]]
        if (before.mul_op, after.mul_op, before.raddr_a, after.raddr_a) != ("mov", "mov", 0, 1):
            raise AssertionError(f"source mutation did not select rf0 -> rf1: {before}, {after}")
        uniforms = struct.unpack("<8I", raw(cpu, UNIFORM, 32))
        if uniforms != (0x06400000, 0x06500000, 0x3F800000, 0xFFFF, 16,
                        0xFFFFFF7C, 0xFFFFFF7C, 0xFFFFFF7C):
            raise AssertionError(f"lowered uniform stream mismatch: {uniforms}")
        print(f"vulkan_neon_particle_compute_qpu_check: PASS - {steps:,} emitted A64 instructions, "
              f"{code_bytes} exact QPU bytes, IR source rf0 -> rf1, unsupported literal refused")


if __name__ == "__main__":
    main()

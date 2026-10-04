#!/usr/bin/env python3
"""Pi 4 emitted-A64 oracle for passive Neon particle compute dataflow."""
from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import struct
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
GATE = ROOT / "Anvil/Graphics/Vulkan/Tests/neon_particle_compute_ir_gate.pi4"
FIXTURE = ROOT / "Anvil/Graphics/Vulkan/Tests/neon_particle_expand.spv"
FIXTURE_SHA = "0d5ced6e1a5e9a91ffed258d860912d53a6a7fc832dfc20ffad5b549a367660a"
DEFAULT_COMPILER = pathlib.Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")
LOAD, STACK, RETURN = 0x80000, 0x200000, 0xDEAD0000
IN, OUT, MODULE = 0x06000000, 0x06010000, 0x06020000

sys.path.insert(0, str(HERE / "a64"))
import a64_interp as a64  # noqa: E402


def instructions(words: list[int]):
    pos = 5
    while pos < len(words):
        count, opcode = words[pos] >> 16, words[pos] & 0xFFFF
        if not count or pos + count > len(words):
            raise AssertionError("invalid fixture instruction span")
        yield pos, opcode, words[pos + 1:pos + count]
        pos += count


def mutate(blob: bytes, opcode: int, predicate, operand: int, replacement: int) -> bytes:
    words = list(struct.unpack(f"<{len(blob)//4}I", blob))
    matches = [(pos, args) for pos, op, args in instructions(words)
               if op == opcode and predicate(args)]
    if len(matches) != 1:
        raise AssertionError(f"mutation selector for opcode {opcode}: {len(matches)} matches")
    pos, args = matches[0]
    if operand < 0:
        words[pos] = (words[pos] & 0xFFFF0000) | replacement
    else:
        if operand >= len(args):
            raise AssertionError("mutation operand outside instruction")
        words[pos + 1 + operand] = replacement
    return struct.pack(f"<{len(words)}I", *words)


def splice(blob: bytes, opcode: int, predicate, replacement: list[int],
           *, before: bool = False) -> bytes:
    words = list(struct.unpack(f"<{len(blob)//4}I", blob))
    matches = [(pos, len(args) + 1) for pos, op, args in instructions(words)
               if op == opcode and predicate(args)]
    if len(matches) != 1:
        raise AssertionError(f"splice selector for opcode {opcode}: {len(matches)} matches")
    pos, count = matches[0]
    words[pos:pos if before else pos + count] = replacement
    return struct.pack(f"<{len(words)}I", *words)


def move_before_return(blob: bytes, opcode: int, predicate) -> bytes:
    words = list(struct.unpack(f"<{len(blob)//4}I", blob))
    matches = [(pos, len(args) + 1) for pos, op, args in instructions(words)
               if op == opcode and predicate(args)]
    if len(matches) != 1:
        raise AssertionError(f"move selector for opcode {opcode}: {len(matches)} matches")
    pos, count = matches[0]
    instruction = words[pos:pos + count]
    del words[pos:pos + count]
    returns = [at for at, op, _ in instructions(words) if op == 253]
    if len(returns) != 1:
        raise AssertionError("expected one OpReturn")
    words[returns[0]:returns[0]] = instruction
    return struct.pack(f"<{len(words)}I", *words)


def change_version(blob: bytes, version: int) -> bytes:
    words = list(struct.unpack(f"<{len(blob)//4}I", blob))
    words[1] = version
    return struct.pack(f"<{len(words)}I", *words)


def put64(cpu, address: int, value: int) -> None:
    for byte in range(8):
        cpu.memory[address + byte] = (value >> (byte * 8)) & 255


def get64(cpu, address: int) -> int:
    return sum(cpu.memory.get(address + byte, 0) << (byte * 8) for byte in range(8))


def execute(image: bytes, image_path: pathlib.Path, blob: bytes) -> tuple[list[int], list[tuple[int, int, int, int]]]:
    cpu = a64.A64()
    for index, byte in enumerate(image):
        cpu.memory[LOAD + index] = byte
    a64.attach_symbols(cpu, image_path, LOAD)
    for index, byte in enumerate(blob):
        cpu.memory[MODULE + index] = byte
    put64(cpu, IN, MODULE)
    put64(cpu, IN + 8, len(blob))
    cpu.pc, cpu.sp, cpu.x[30] = LOAD, STACK, RETURN
    for steps in range(6_000_000):
        if cpu.pc == RETURN:
            break
        cpu.step()
    else:
        raise AssertionError("compute gate failed to return within 6,000,000 A64 steps")
    fields = [get64(cpu, OUT + 8 * index) for index in range(12)]
    stores = [tuple(get64(cpu, OUT + 96 + 32 * index + 8 * field)
                    for field in range(4)) for index in range(36)]
    return fields, stores


def check_positive(fields, stores, source_override: dict[int, int] | None = None) -> None:
    expected_header = [0, 1, 16, 1, 1, 48, 4, 1, 36, 0, 1, 36]
    if fields != expected_header:
        raise AssertionError(f"compute header mismatch: {fields} != {expected_header}")
    input_vertices = [(0, 4), (16, 20), (24, 28), (0, 4), (24, 28), (8, 12)]
    expected = []
    for x, y in input_vertices:
        for source in (x, y, 32, 36, None, None):
            offset = len(expected)
            if source is None:
                expected.append((offset, 2, 0, 0x3F800000))
            else:
                expected.append((offset, 1, source, 0))
    for index, source in (source_override or {}).items():
        expected[index] = (index, 1, source, 0)
    if stores != expected:
        for index, (actual, wanted) in enumerate(zip(stores, expected)):
            if actual != wanted:
                raise AssertionError(f"store {index}: actual {actual}, expected {wanted}; "
                                     f"output byte offset = {index * fields[6]}, "
                                     f"invocation byte stride = {fields[8] * fields[6]}")
        raise AssertionError("store count mismatch")
    # The byte destinations are derived from the reported typed output stride
    # and affine index scale; cover every store, including constants.
    assert [word * fields[6] for word, *_ in stores] == list(range(0, 144, 4))
    assert fields[8] * fields[6] == 144


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=pathlib.Path, default=DEFAULT_COMPILER)
    args = parser.parse_args()
    blob = FIXTURE.read_bytes()
    digest = hashlib.sha256(blob).hexdigest()
    if digest != FIXTURE_SHA:
        raise AssertionError(f"tracked SPIR-V SHA changed: {digest}")
    with tempfile.TemporaryDirectory(prefix="anvil_neon_compute_ir_") as tmp:
        image_path = pathlib.Path(tmp) / "compute_gate.img"
        command = [str(args.compiler), "--compile", GATE.relative_to(ROOT).as_posix(),
                   "-t", "pi4", "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
                   "--entry-returns", "-o", str(image_path), "-s"]
        env = os.environ.copy()
        env["PMF_ROOT"] = str(ROOT)
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                                text=True, timeout=120, check=False)
        if result.returncode or "pmfc: OK" not in result.stdout:
            raise AssertionError("Pi 4 compute gate compile failed:\n" + result.stdout + result.stderr)
        image = image_path.read_bytes()
        fields, stores = execute(image, image_path, blob)
        check_positive(fields, stores)
        print("positive: 36 typed stores, 48-byte input, 144-byte output, "
              "GlobalInvocationID.x scale 1, LocalSize 16x1x1")

        reject = [
            ("LocalSize", mutate(blob, 16, lambda x: x[:2] == [4, 17], 2, 8)),
            ("input member offset", mutate(blob, 72, lambda x: x[:3] == [21, 1, 35], 3, 20)),
            ("input array stride", mutate(blob, 71, lambda x: x[:2] == [22, 6], 2, 64)),
            ("output array stride", mutate(blob, 71, lambda x: x[:2] == [45, 6], 2, 8)),
            ("input binding", mutate(blob, 71, lambda x: x[:2] == [25, 33], 2, 2)),
            ("output index scale", mutate(blob, 43, lambda x: x[:2] == [6, 43], 2, 35)),
            ("store order", mutate(blob, 62, lambda x: x == [55, 53], 0, 61)),
            ("missing store", mutate(blob, 62, lambda x: x == [55, 53], -1, 0)),
            ("out-of-range ID", mutate(blob, 65, lambda x: x == [13, 14, 11, 12], 1, 244)),
            ("wild ID", mutate(blob, 65, lambda x: x == [13, 14, 11, 12], 1, 0xFFFFFFFF)),
            ("wild composite member", mutate(blob, 81, lambda x: x == [17, 32, 31, 0], 3, 0xFFFFFFFF)),
            ("dead duplicate type ID", splice(blob, 253, lambda x: x == [],
                                               [(5 << 16) | 128, 6, 16, 15, 12], before=True)),
            ("word-count-one OpName", splice(blob, 5, lambda x: x[0] == 4,
                                              [(1 << 16) | 5])),
            ("undefined OpName target", mutate(blob, 5, lambda x: x[0] == 4, 0, 200)),
            ("non-struct OpMemberName target", mutate(blob, 6,
                                                       lambda x: x[:2] == [21, 0], 0, 11)),
            ("constant composite inside function", move_before_return(
                blob, 44, lambda x: x[:2] == [9, 243])),
            ("undeclared decoration target", splice(blob, 19, lambda x: x == [2],
                                                    [(3 << 16) | 71, 200, 24], before=True)),
            ("SPIR-V version zero", change_version(blob, 0)),
        ]
        for name, mutant in reject:
            got, _ = execute(image, image_path, mutant)
            if got[0] == 0 or got[1] != 0:
                raise AssertionError(f"{name} mutant unexpectedly accepted: {got}")
            print(f"reject: {name}")

        reflected = mutate(blob, 81, lambda x: x == [16, 53, 32, 0], 3, 1)
        got, changed = execute(image, image_path, reflected)
        check_positive(got, changed, {0: 4, 18: 4})
        print("reflect: changed source component appears in stores 0 and 18")
    print("compute IR gate: PASS (20 cases, all 36 ordered stores checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

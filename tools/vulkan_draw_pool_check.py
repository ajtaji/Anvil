#!/usr/bin/env python3
"""Compile and execute the bounded Vulkan recorded-draw pool gate.

The image uses the state-only backend, runs in the A64 interpreter, and never
touches a board.  Mutations are made only in a private staged source tree.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import os
import pathlib
import sys
import tempfile
import time
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler


HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
VULKAN = ROOT / "Anvil" / "Graphics" / "Vulkan"
COMMAND = VULKAN / "vk_command.pbi"
GATE = VULKAN / "Tests" / "vulkan_draw_pool_gate.pi4"

DEFAULT_COMPILER = pathlib.Path(
    r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe"
)
DEFAULT_REGISTRY = pathlib.Path(
    tempfile.gettempdir()
) / "vulkan-v1.4.350-vk.xml"
COMPILER_SHA256 = "bde17c26fd5ba64ddad92dad05d429e14b7d4048d2877834ec7e1e8cf32a9335"
REGISTRY_SHA256 = "50bd8c0f316eabf73d1c5fe3add2d89eaa480dbda9282c12c289e80e9d081e08"

OUT = 0x06000000
ROWS = 0x06000100
MAGIC = 0x564B4450

CONTRACTS = (
    "#ANVIL_VK_MAX_RECORDED_DRAWS = 4096",
    "#ANVIL_VK_RECORDED_DRAW_BYTES = 216",
    "Structure AnvilVkRecordedDraw Align #PB_Structure_AlignC",
    "Global Dim avkCbDrawHead.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]",
    "Global Dim avkCbDrawTail.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]",
    "Procedure.i avkRecordedDrawAppend(c.i, firstVertex.i, vertexCount.i, viewportX.i, viewportY.i, viewportW.i, viewportH.i, scissorX.i, scissorY.i, scissorW.i, scissorH.i, indexBuffer.i, indexOffset.i, indexType.i)",
    "Procedure.i avkRecordedDrawRelease(c.i)",
    "If avkRecordedDrawRelease(c) = 0",
)

MUTANTS = (
    (
        "zero-vertex draws consume a pool slot",
        "  If vertexCount = 0 : ProcedureReturn 0 : EndIf\n",
        "  If vertexCount < 0 : ProcedureReturn 0 : EndIf\n",
    ),
    (
        "allocation does not advance the free-list head",
        "  avkRecordedDrawFreeHead = nextFree\n  avkRecordedDrawFreeCount = avkRecordedDrawFreeCount - 1\n",
        "  avkRecordedDrawFreeHead = s\n  avkRecordedDrawFreeCount = avkRecordedDrawFreeCount - 1\n",
    ),
    (
        "a later draw is not linked after the previous tail",
        "    avkRecordedDraw[avkCbDrawTail[c]]\\next = s\n",
        "    avkRecordedDraw[avkCbDrawTail[c]]\\next = 0\n",
    ),
    (
        "the recorded pipeline is taken from the descriptor binding",
        "  avkRecordedDraw[s]\\pipeline = avkCbPipe[c]\n",
        "  avkRecordedDraw[s]\\pipeline = avkCbDescSet[c]\n",
    ),
    (
        "a later draw overwrites the first draw's pipeline snapshot",
        "  avkRecordedDraw[s]\\pipeline = avkCbPipe[c]\n",
        "  avkRecordedDraw[1]\\pipeline = avkCbPipe[c]\n",
    ),
    (
        "only one vertex binding is cloned into a draw snapshot",
        "  avkRecordedDraw[s]\\scissorH = scissorH\n  k = 0\n  While k < 4\n",
        "  avkRecordedDraw[s]\\scissorH = scissorH\n  k = 0\n  While k < 1\n",
    ),
    (
        "release accepts a hostile terminal link",
        "      If s <> avkCbDrawTail[c] Or n <> 0 : ProcedureReturn 0 : EndIf\n",
        "      If s <> avkCbDrawTail[c] Or n < 0 : ProcedureReturn 0 : EndIf\n",
    ),
    (
        "release splices the old head rather than the old tail",
        "  avkRecordedDraw[avkCbDrawTail[c]]\\next = avkRecordedDrawFreeHead\n",
        "  avkRecordedDraw[avkCbDrawHead[c]]\\next = avkRecordedDrawFreeHead\n",
    ),
    (
        "release restores one slot instead of the complete chain",
        "  avkRecordedDrawFreeCount = avkRecordedDrawFreeCount + count\n",
        "  avkRecordedDrawFreeCount = avkRecordedDrawFreeCount + 1\n",
    ),
    (
        "command-buffer clear skips recorded-draw ownership release",
        "  If avkRecordedDrawRelease(c) = 0\n",
        "  If 1 = 0\n",
    ),
    (
        "the deterministic free list starts at slot two",
        "  avkRecordedDrawFreeHead = 1\n  avkRecordedDrawFreeCount = #ANVIL_VK_MAX_RECORDED_DRAWS\n",
        "  avkRecordedDrawFreeHead = 2\n  avkRecordedDrawFreeCount = #ANVIL_VK_MAX_RECORDED_DRAWS\n",
    ),
    (
        "a 4097th draw is allowed to consume the null slot",
        "  If s < 1 Or s > #ANVIL_VK_MAX_RECORDED_DRAWS Or avkRecordedDrawFreeCount < 1\n",
        "  If s < 0 Or s > #ANVIL_VK_MAX_RECORDED_DRAWS Or avkRecordedDrawFreeCount < 0\n",
    ),
)


def locate(explicit: str | None, env_name: str, fallback: pathlib.Path) -> pathlib.Path:
    value = explicit or os.environ.get(env_name)
    path = pathlib.Path(value) if value else fallback
    if not path.is_file():
        raise SystemExit(f"vulkan draw-pool gate: {env_name} not found: {path}")
    return path.resolve()


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_pin(path: pathlib.Path, wanted: str, label: str) -> None:
    got = digest(path)
    if got.lower() != wanted.lower():
        raise SystemExit(
            f"vulkan draw-pool gate: {label} hash mismatch for {path}\n"
            f"  got {got}\n  expected {wanted}"
        )


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"vulkan draw-pool gate: cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@contextlib.contextmanager
def checker_lock():
    path = pathlib.Path(tempfile.gettempdir()) / "anvil_vk_pipeline_check.lock"
    with path.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt

            while True:
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.1)
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def u64(cpu, address: int) -> int:
    return sum(cpu.memory.get(address + i, 0) << (8 * i) for i in range(8))


def grade(cpu, rc: int) -> list[str]:
    failures: list[str] = []
    magic = u64(cpu, OUT)
    checks = u64(cpu, OUT + 8)
    in_image = u64(cpu, OUT + 16)
    if magic != MAGIC:
        failures.append(f"magic got {magic:#x}, expected {MAGIC:#x}")
    if rc != 0:
        failures.append(f"return code got {rc}, expected 0")
    if in_image != 0:
        failures.append(f"in-image failures got {in_image}, expected 0")
    if checks < 55:
        failures.append(f"only {checks} property rows ran")
    if in_image and checks < 4096:
        bad = [str(i + 1) for i in range(checks) if u64(cpu, ROWS + i * 8) == 0]
        failures.append("failed property rows " + ",".join(bad))
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler")
    parser.add_argument("--interp")
    parser.add_argument("--registry")
    parser.add_argument("--mutate", action="store_true")
    args = parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler

    compiler = locate(args.compiler, "PMF_COMPILER", DEFAULT_COMPILER)
    registry = locate(args.registry, "VULKAN_REGISTRY", DEFAULT_REGISTRY)
    interp = locate(args.interp, "PMF_A64_INTERP", HERE / "a64" / "a64_interp.py")
    require_pin(compiler, COMPILER_SHA256, "unified compiler")
    require_pin(registry, REGISTRY_SHA256, "Vulkan registry")

    command_text = COMMAND.read_text(encoding="utf-8")
    missing = [token for token in CONTRACTS if token not in command_text]
    if missing:
        for token in missing:
            print(f"vulkan_draw_pool_check: STALE - missing contract: {token}")
        return 1
    stale = [(name, command_text.count(fixed)) for name, fixed, _ in MUTANTS
             if command_text.count(fixed) != 1]
    if stale:
        for name, count in stale:
            print(f"vulkan_draw_pool_check: STALE - {name}: anchor count {count}")
        return 1

    harness = load_module("anvil_vk_draw_pool_harness", HERE / "vulkan_resource_check.py")
    harness.GATE = GATE
    harness.STEP_LIMIT = 250_000_000
    a64 = harness.load_interpreter(interp)

    with checker_lock():
        cpu, rc, steps = harness.run_once(a64, compiler, {})
        failures = grade(cpu, rc)
        if failures:
            print(f"vulkan_draw_pool_check: FAIL ({steps:,} A64 instructions)")
            for failure in failures:
                print("  " + failure)
            return 1
        rows = u64(cpu, OUT + 8)
        print(
            f"vulkan_draw_pool_check: PASS - {rows} properties, "
            f"{steps:,} executed A64 instructions"
        )
        print(f"  compiler sha256 {digest(compiler)}")
        print(f"  registry sha256 {digest(registry)}")

        if not args.mutate:
            print("  (run with --mutate to require all hostile mistakes to go red)")
            return 0

        missed = 0
        for name, fixed, broken in MUTANTS:
            mutated = command_text.replace(fixed, broken, 1)
            try:
                mcpu, mrc, msteps = harness.run_once(
                    a64, compiler, {COMMAND.name: mutated}
                )
            except SystemExit as exc:
                print(f"  STALE  {name} - {str(exc).splitlines()[0]}")
                missed += 1
                continue
            mfailures = grade(mcpu, mrc)
            if mfailures:
                print(f"  RED    {name} - {mfailures[0]} ({msteps:,} instructions)")
            else:
                print(f"  GREEN  {name} <-- gate did not notice ({msteps:,} instructions)")
                missed += 1

    if missed:
        print(f"vulkan_draw_pool_check: FAIL - {missed} of {len(MUTANTS)} mutations escaped")
        return 1
    print(f"vulkan_draw_pool_check: PASS - all {len(MUTANTS)} mutations rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

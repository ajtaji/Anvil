#!/usr/bin/env python3
"""Fast emitted-A64 proof for the closed draw-list transaction and ledger.

The gate executes the real public command-buffer and queue-submit path over
the state-only backend. Mutations are compiled from private staged sources;
the repository is never left in a hostile state.
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
PIPELINE = VULKAN / "vk_pipeline.pbi"
TEST_BACKEND = VULKAN / "vk_backend_test.pbi"
GATE = VULKAN / "Tests" / "vulkan_draw_list_gate.pi4"

DEFAULT_COMPILER = pathlib.Path(
    r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe"
)
DEFAULT_REGISTRY = pathlib.Path(
    tempfile.gettempdir()
) / "vulkan-v1.4.350-vk.xml"
COMPILER_SHA256 = "bde17c26fd5ba64ddad92dad05d429e14b7d4048d2877834ec7e1e8cf32a9335"
REGISTRY_SHA256 = "50bd8c0f316eabf73d1c5fe3add2d89eaa480dbda9282c12c289e80e9d081e08"

OUT = 0x06100000
MAGIC = 0x564B444C
ERR_STATE = -20004


def locate(explicit: str | None, env_name: str, fallback: pathlib.Path) -> pathlib.Path:
    value = explicit or os.environ.get(env_name)
    path = pathlib.Path(value) if value else fallback
    if not path.is_file():
        raise SystemExit(f"vulkan draw-list gate: {env_name} not found: {path}")
    return path.resolve()


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_pin(path: pathlib.Path, wanted: str, label: str) -> None:
    got = digest(path)
    if got.lower() != wanted.lower():
        raise SystemExit(
            f"vulkan draw-list gate: {label} hash mismatch for {path}\n"
            f"  got {got}\n  expected {wanted}"
        )


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"vulkan draw-list gate: cannot load {path}")
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


def s64(cpu, address: int) -> int:
    value = u64(cpu, address)
    return value - (1 << 64) if value >= (1 << 63) else value


EXPECTED = {
    0: MAGIC,
    1: 0,
    3: 0,
    4: ERR_STATE,
    5: 0,
    6: 0,
    7: 0,
    8: 0,
    9: 0,
    10: 1,
    11: 0,
    12: 0,
    13: 0,
    14: 0,
    15: 3,
    16: 0,
    17: 3,
    18: 3,
    19: 1,
    20: 1,
    21: 1,
    22: 1,
    23: 1,
    24: 1,
    25: ERR_STATE,
    26: ERR_STATE,
    27: ERR_STATE,
    28: 0,
    29: 0,
    30: 0,
    31: 0,
    32: 0,
    33: 0,
    34: 1,
    35: 1,
    36: 0,
    37: 0,
    38: ERR_STATE,
    39: 1,
    40: 0,
    41: 0,
    42: 0,
    43: 1,
    44: 0,
    45: 0,
    46: 1,
    47: 0,
    48: 1,
    49: 0,
    50: 0,
    51: 1,
    52: 0,
    53: -20005,
    54: -20004,
    55: 0,
    56: 0,
    57: 1,
    58: 1,
    59: 0,
    60: 0,
    61: 0,
    62: 1,
    63: 1,
    64: 0,
    65: 1,
    66: 1,
    67: 0,
}


def grade(cpu, rc: int) -> list[str]:
    failures: list[str] = []
    if rc == 0:
        failures.append("gate returned a null report pointer")
    for slot, wanted in EXPECTED.items():
        got = s64(cpu, OUT + slot * 8)
        if got != wanted:
            failures.append(f"report[{slot}] got {got}, expected {wanted}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler")
    parser.add_argument("--interp")
    parser.add_argument("--registry")
    parser.add_argument("--mutate", action="store_true")
    parser.add_argument("--mutate-name", action="append", default=[])
    args = parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler

    compiler = locate(args.compiler, "PMF_COMPILER", DEFAULT_COMPILER)
    registry = locate(args.registry, "VULKAN_REGISTRY", DEFAULT_REGISTRY)
    interp = locate(args.interp, "PMF_A64_INTERP", HERE / "a64" / "a64_interp.py")
    require_pin(compiler, COMPILER_SHA256, "unified compiler")
    require_pin(registry, REGISTRY_SHA256, "Vulkan registry")

    full = load_module("anvil_vk_pipeline_mutants", HERE / "vulkan_pipeline_check.py")
    mutants = (
        [(COMMAND, *m) for m in full.DRAW_LIST_COMMAND_MUTANTS]
        + [(PIPELINE, *m) for m in full.DRAW_LIST_PIPELINE_MUTANTS]
        + [
            (COMMAND,
             "signalled-fence abandon keeps the preflighted draw list",
             "    If f <= 0\n      avkDrawListDiscard()\n      ProcedureReturn f\n    EndIf\n",
             "    If f <= 0\n      ProcedureReturn f\n    EndIf\n"),
            (TEST_BACKEND,
             "the test backend always decodes a legacy Draw as DrawList",
             "  If (avkTbCaps & #ANVIL_VK_CAP_DRAW_LIST) <> 0\n",
             "  If 1 = 1\n"),
            (COMMAND,
             "command reset preserves a supplied dynamic scissor",
             "  avkCbScissorSet[c] = 0\n",
             "  avkCbScissorSet[c] = 1\n"),
            (COMMAND,
             "command reset preserves a supplied dynamic viewport",
             "  avkCbViewportSet[c] = 0\n",
             "  avkCbViewportSet[c] = 1\n"),
            (PIPELINE,
             "a dynamic-scissor draw may execute before vkCmdSetScissor",
             "    If avkCbScissorSet[c] = 0\n      avkCbFail(c, #ANVIL_VK_ERR_STATE, \"vkCmdDraw used a pipeline with VK_DYNAMIC_STATE_SCISSOR before vkCmdSetScissor supplied that state (Anvil code -20004, dynamic scissor not set); command-buffer reset deliberately makes dynamic state undefined again.\")\n",
             "    If avkCbScissorSet[c] < 0\n      avkCbFail(c, #ANVIL_VK_ERR_STATE, \"vkCmdDraw used a pipeline with VK_DYNAMIC_STATE_SCISSOR before vkCmdSetScissor supplied that state (Anvil code -20004, dynamic scissor not set); command-buffer reset deliberately makes dynamic state undefined again.\")\n"),
            (PIPELINE,
             "draw-list preflight reads the later command-buffer scissor",
             "    avkFlightDraw[draw]\\scissorX = avkRecordedDraw[slot]\\scissorX\n    avkFlightDraw[draw]\\scissorY = avkRecordedDraw[slot]\\scissorY\n    avkFlightDraw[draw]\\scissorW = avkRecordedDraw[slot]\\scissorW\n    avkFlightDraw[draw]\\scissorH = avkRecordedDraw[slot]\\scissorH\n",
             "    avkFlightDraw[draw]\\scissorX = avkCbScissorX[c]\n    avkFlightDraw[draw]\\scissorY = avkCbScissorY[c]\n    avkFlightDraw[draw]\\scissorW = avkCbScissorW[c]\n    avkFlightDraw[draw]\\scissorH = avkCbScissorH[c]\n"),
            (PIPELINE,
             "a dynamic-viewport draw may execute before vkCmdSetViewport",
             "    If avkCbViewportSet[c] = 0\n      avkCbFail(c, #ANVIL_VK_ERR_STATE, \"vkCmdDraw used a pipeline with VK_DYNAMIC_STATE_VIEWPORT before vkCmdSetViewport supplied that state (Anvil code -20004, dynamic viewport not set); command-buffer reset deliberately makes dynamic state undefined again.\")\n",
             "    If avkCbViewportSet[c] < 0\n      avkCbFail(c, #ANVIL_VK_ERR_STATE, \"vkCmdDraw used a pipeline with VK_DYNAMIC_STATE_VIEWPORT before vkCmdSetViewport supplied that state (Anvil code -20004, dynamic viewport not set); command-buffer reset deliberately makes dynamic state undefined again.\")\n"),
            (PIPELINE,
             "draw-list preflight reads later command-buffer viewport state",
             "    avkFlightDraw[draw]\\viewportX = avkRecordedDraw[slot]\\viewportX\n    avkFlightDraw[draw]\\viewportY = avkRecordedDraw[slot]\\viewportY\n    avkFlightDraw[draw]\\viewportW = avkRecordedDraw[slot]\\viewportW\n    avkFlightDraw[draw]\\viewportH = avkRecordedDraw[slot]\\viewportH\n",
             "    avkFlightDraw[draw]\\viewportX = avkCbViewportX[c]\n    avkFlightDraw[draw]\\viewportY = avkCbViewportY[c]\n    avkFlightDraw[draw]\\viewportW = avkCbViewportW[c]\n    avkFlightDraw[draw]\\viewportH = avkCbViewportH[c]\n"),
        ]
    )
    if args.mutate_name:
        wanted = set(args.mutate_name)
        known = {entry[1] for entry in mutants}
        missing = sorted(wanted - known)
        if missing:
            raise SystemExit("unknown mutation name(s): " + ", ".join(missing))
        mutants = [entry for entry in mutants if entry[1] in wanted]
        args.mutate = True
    originals = {
        COMMAND: COMMAND.read_text(encoding="utf-8"),
        PIPELINE: PIPELINE.read_text(encoding="utf-8"),
        TEST_BACKEND: TEST_BACKEND.read_text(encoding="utf-8"),
    }
    stale = []
    for path, name, fixed, _broken in mutants:
        hits = originals[path].count(fixed)
        if hits != 1:
            stale.append(f"{path.name}: {name}: anchor count {hits}")
    if stale:
        print("vulkan_draw_list_check: STALE - mutation anchors are not unique")
        for line in stale:
            print("  " + line)
        return 2

    harness = load_module("anvil_vk_draw_list_harness", HERE / "vulkan_resource_check.py")
    harness.GATE = GATE
    harness.STEP_LIMIT = 40_000_000
    a64 = harness.load_interpreter(interp)

    with checker_lock():
        cpu, rc, steps = harness.run_once(a64, compiler, {})
        failures = grade(cpu, rc)
        if failures:
            print(f"vulkan_draw_list_check: FAIL ({steps:,} A64 instructions)")
            for failure in failures:
                print("  " + failure)
            return 1
        print(
            f"vulkan_draw_list_check: PASS - {len(EXPECTED)} properties, "
            f"{steps:,} executed A64 instructions"
        )
        print(f"  compiler sha256 {digest(compiler)}")
        print(f"  registry sha256 {digest(registry)}")
        if not args.mutate:
            print("  (run with --mutate to require all hostile mistakes to go red)")
            return 0

        missed = 0
        for path, name, fixed, broken in mutants:
            sources = {path.name: originals[path].replace(fixed, broken, 1)}
            try:
                mcpu, mrc, msteps = harness.run_once(a64, compiler, sources)
                mfailures = grade(mcpu, mrc)
            except SystemExit as exc:
                mfailures = [str(exc).splitlines()[0]]
                msteps = 0
            if mfailures:
                print(f"  RED    {name} - {mfailures[0]} ({msteps:,} instructions)")
            else:
                print(f"  GREEN  {name} <-- gate did not notice ({msteps:,} instructions)")
                missed += 1

    if missed:
        print(f"vulkan_draw_list_check: FAIL - {missed} of {len(mutants)} mutations escaped")
        return 1
    print(f"vulkan_draw_list_check: PASS - all {len(mutants)} mutations rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

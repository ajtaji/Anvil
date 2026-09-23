#!/usr/bin/env python3
"""Emitted-A64 proof for bounded Vulkan indexed drawing on Pi 4.

The public-path fixture covers record/submit validation and captured resource
lifetimes over the state-only backend. A second fixture executes the production
V3D packet encoders and compares every emitted byte with the V3D 4.2 layout.
The hardware backend integration itself is covered by
vulkan_v3d_backend_list_check.py, whose indexed rows observe its exact packet
arguments and cache span.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler

ROOT = Path(__file__).resolve().parents[1]
VULKAN = ROOT / "Anvil/Graphics/Vulkan"
PUBLIC_GATE = VULKAN / "Tests/vulkan_indexed_draw_gate.pi4"
PACKET_GATE = ROOT / "RaspberryPi4/Tests/vulkan_index_packet_emitted_gate.pi4"
PIPELINE = VULKAN / "vk_pipeline.pbi"
BACKEND = VULKAN / "vk_v3d_backend.pi4"
V3D = ROOT / "RaspberryPi4/Lib/v3d.pi4"
COMPILER = Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")
INTERP = ROOT / "tools/a64/a64_interp.py"
LOAD, BSS, STACK = 0x400000, 0x800000, 0x3000000
OUT = 0x06300000
MASK = (1 << 64) - 1

PUBLIC_EXPECTED = {
    0: 0x564B4944, 1: 0, 2: 0,
    3: 0, 4: 0, 5: 1, 6: 1, 7: 1, 8: -20004, 9: 0, 10: 1,
    11: 0, 12: 0, 13: 1, 14: 1, 15: 0,
    16: 0, 17: -20001, 18: 0, 19: -20001,
    20: 0, 21: -20004, 22: 0, 23: 0, 24: 0, 25: 0, 26: 1,
    27: 0, 28: -20004, 29: 0, 30: 0, 31: 1,
}

PACKET_RESULTS = (0, 0, 19, 0, 0, 19, 0, 27, 0, 0, 27, 0)
PACKET16 = bytes((
    44, 0x78, 0x56, 0x34, 0x12, 0x44, 0x33, 0x22, 0x11,
    32, 0x44, 3, 0, 0, 0, 4, 0, 0, 0,
))
PACKET32 = bytes((
    44, 0x40, 0x30, 0x20, 0x10, 0x88, 0x77, 0x66, 0x55,
    32, 0x84, 3, 2, 1, 0, 4, 3, 2, 1,
))

CONTRACTS = {
    V3D: (
        "#V3D_PKT_INDEXED_PRIM_LIST     = 32",
        "#V3D_PKT_INDEX_BUFFER_SETUP    = 44",
        "((indexType & 3) << 6)",
        "Procedure V3dClIndexBufferSetup(address.i, bytes.i)",
    ),
    BACKEND: (
        "V3dClIndexBufferSetup(*d\\indexBase, *d\\indexBytes)",
        "V3dClIndexedPrims(#AVKQ_PRIM_TRIANGLES, *d\\vertexCount, 1, *d\\firstVertex * 2)",
        "V3dClIndexedPrims(#AVKQ_PRIM_TRIANGLES, *d\\vertexCount, 2, *d\\firstVertex * 4)",
        "AnvilVkV3dBuildDrawSlotRecord(pipe, pbase, drawBase, *d, *d\\maxVertex",
        "avkV3dCacheIntervalAdd(*d\\indexBase + indexOffset, bytes)",
    ),
}

PUBLIC_MUTANTS = (
    ("max-index scan is disabled",
     "If indexValue > maxVertex : maxVertex = indexValue : EndIf",
     "If indexValue < maxVertex : maxVertex = indexValue : EndIf"),
    ("index buffer lifetime is not retained",
     "    s = avkFlightIndexBuf[draw]\n    If s > 0\n      avkBufInFlight[s] = avkBufInFlight[s] + 1",
     "    s = avkFlightIndexBuf[draw]\n    If s < 0\n      avkBufInFlight[s] = avkBufInFlight[s] + 1"),
    ("recording accepts a range past the index buffer",
     "If firstIndex > (available / indexBytes) Or indexCount > ((available / indexBytes) - firstIndex)",
     "If firstIndex > (available / indexBytes) And indexCount > ((available / indexBytes) - firstIndex)"),
)

PACKET_MUTANTS = (
    ("index type occupies the wrong bits", "((indexType & 3) << 6)", "((indexType & 3) << 5)"),
    ("index setup size becomes an inclusive end",
     "  v3d_ClU32(address)\n  v3d_ClU32(bytes)\nEndProcedure",
     "  v3d_ClU32(address)\n  v3d_ClU32(bytes - 1)\nEndProcedure"),
    ("indexed byte offset is emitted in words",
     "  v3d_ClU32(indexOffset)\nEndProcedure\n\n; v3d_packet.xml:520-523.",
     "  v3d_ClU32(indexOffset / 4)\nEndProcedure\n\n; v3d_packet.xml:520-523."),
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@contextlib.contextmanager
def checker_lock():
    path = Path(tempfile.gettempdir()) / "anvil_vk_pipeline_check.lock"
    with path.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0"); stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            while True:
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1); break
                except OSError:
                    time.sleep(0.1)
            try:
                yield
            finally:
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def signed(value: int) -> int:
    return value - (1 << 64) if value & (1 << 63) else value


def check_public(harness, a64, compiler: Path, mutation: str | None = None):
    harness.GATE = PUBLIC_GATE
    harness.OUT = OUT
    harness.STEP_LIMIT = 250_000_000
    sources = {PIPELINE.name: mutation} if mutation is not None else {}
    cpu, rc, steps = harness.run_once(a64, compiler, sources)
    failures = []
    if rc == 0:
        failures.append("gate returned null")
    for slot, want in PUBLIC_EXPECTED.items():
        got = signed(harness.u64(cpu, OUT + slot * 8))
        if got != want:
            failures.append(f"public[{slot}] got {got}, expected {want}")
    return failures, steps


def packet_product(compiler: Path, root: Path, core: str):
    lib = root / "RaspberryPi4/Lib"
    tests = root / "RaspberryPi4/Tests"
    (root / "Anvil/Core").mkdir(parents=True)
    lib.mkdir(parents=True); tests.mkdir(parents=True)
    for name in ("uart.pi4", "timer.pi4", "safety.pi4", "mailbox.pi4", "v3dqpu.pi4", "v3d.pi4"):
        source = ROOT / "RaspberryPi4/Lib" / name
        (lib / name).write_text(core if name == "v3d.pi4" else source.read_text(encoding="utf-8-sig"), encoding="utf-8")
    shutil.copy2(PACKET_GATE, tests / PACKET_GATE.name)
    shutil.copy2(ROOT / "Anvil/Core/console_style.pbi", root / "Anvil/Core/console_style.pbi")
    if (ROOT / "Boards").is_dir(): shutil.copytree(ROOT / "Boards", root / "Boards", dirs_exist_ok=True)
    if (ROOT / "RaspberryPi4/Intrinsics").is_dir(): shutil.copytree(ROOT / "RaspberryPi4/Intrinsics", root / "RaspberryPi4/Intrinsics", dirs_exist_ok=True)
    image = root / "packet.img"
    env = os.environ.copy(); env["PMF_ROOT"] = str(root)
    run = subprocess.run([
        str(compiler), "--compile", f"RaspberryPi4/Tests/{PACKET_GATE.name}", "-t", "pi4", "-s",
        "--entry-returns", "--load-addr", hex(LOAD), "--bss-addr", hex(BSS),
        "--stack-addr", hex(STACK), "-o", str(image),
    ], cwd=root, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if run.returncode or not image.is_file():
        raise RuntimeError("packet fixture compile failed\n" + run.stdout)
    symbols = {}
    for line in Path(str(image) + ".sym").read_text(encoding="utf-8-sig").splitlines():
        if "=" in line:
            key, value = line.split("=", 1); symbols[key.strip().lower()] = int(value.strip(), 0)
    return image, symbols


def check_packets(harness, a64, compiler: Path, core: str):
    with tempfile.TemporaryDirectory(prefix="anvil-vk-index-packet-") as temporary:
        image, symbols = packet_product(compiler, Path(temporary), core)
        cpu, rc, steps = harness.execute(a64, image)
        result = symbols["global_vipresult"]
        packet = symbols["global_vippacket"]
        got_results = tuple(signed(harness.u64(cpu, result + i * 8)) for i in range(12))
        got16 = bytes(cpu.memory.get(packet + i, 0) for i in range(19))
        got32 = bytes(cpu.memory.get(packet + 256 + i, 0) for i in range(19))
        rejected8 = bytes(cpu.memory.get(packet + 512 + i, 0) for i in range(4))
        rejected_wrap = bytes(cpu.memory.get(packet + 768 + i, 0) for i in range(4))
        failures = []
        if rc == 0: failures.append("packet gate returned null")
        if got_results != PACKET_RESULTS: failures.append(f"packet results {got_results!r}")
        if got16 != PACKET16: failures.append(f"UINT16 bytes {got16.hex()}")
        if got32 != PACKET32: failures.append(f"UINT32 bytes {got32.hex()}")
        if rejected8 != b"\0" * 4: failures.append("UINT8 refusal wrote bytes")
        if rejected_wrap != b"\0" * 4: failures.append("wrapped setup refusal wrote bytes")
        return failures, steps


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", type=Path, default=COMPILER)
    parser.add_argument("--interp", type=Path, default=INTERP)
    parser.add_argument("--mutate", action="store_true")
    args = parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    for path, tokens in CONTRACTS.items():
        text = path.read_text(encoding="utf-8-sig")
        missing = [token for token in tokens if token not in text]
        if missing:
            print(f"vulkan_indexed_draw_check: STALE {path.name}: {missing}"); return 2
    harness = load_module("anvil_vk_index_harness", ROOT / "tools/vulkan_resource_check.py")
    a64 = harness.load_interpreter(args.interp)
    core = V3D.read_text(encoding="utf-8-sig")
    with checker_lock():
        failures, public_steps = check_public(harness, a64, args.compiler)
        packet_failures, packet_steps = check_packets(harness, a64, args.compiler, core)
    failures += packet_failures
    if failures:
        print("vulkan_indexed_draw_check: FAIL")
        for failure in failures: print("  " + failure)
        return 1
    print(f"vulkan_indexed_draw_check: PASS - 32 public-path cells, 12 encoder results and 46 exact packet/refusal bytes, {public_steps + packet_steps:,} emitted A64 instructions")
    print("  UINT16/UINT32, firstIndex once, max-index vertex bound, atomic refusals and index lifetime passed")
    if not args.mutate:
        return 0
    misses = 0
    pipeline = PIPELINE.read_text(encoding="utf-8-sig")
    for name, fixed, broken in PUBLIC_MUTANTS:
        if pipeline.count(fixed) != 1:
            print("  STALE " + name); misses += 1; continue
        with checker_lock():
            bad, _ = check_public(harness, a64, args.compiler, pipeline.replace(fixed, broken, 1))
        caught = bool(bad); print(("  CAUGHT " if caught else "  MISSED ") + name); misses += 0 if caught else 1
    for name, fixed, broken in PACKET_MUTANTS:
        if core.count(fixed) != 1:
            print("  STALE " + name); misses += 1; continue
        with checker_lock():
            bad, _ = check_packets(harness, a64, args.compiler, core.replace(fixed, broken, 1))
        caught = bool(bad); print(("  CAUGHT " if caught else "  MISSED ") + name); misses += 0 if caught else 1
    return 1 if misses else 0


if __name__ == "__main__":
    raise SystemExit(main())

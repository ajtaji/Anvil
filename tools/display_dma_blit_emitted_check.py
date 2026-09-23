#!/usr/bin/env python3
"""Desk-only emitted-A64 proof for DisplayBlit's DMA/fallback seam."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler


ROOT = pathlib.Path(__file__).resolve().parents[1]
GATE = ROOT / "RaspberryPi4" / "Tests" / "display_dma_blit_emitted_gate.pi4"
DISPLAY = ROOT / "RaspberryPi4" / "Lib" / "display.pi4"
INTERP = ROOT / "tools" / "a64" / "a64_interp.py"
DEFAULT_COMPILER = pathlib.Path(
    r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe"
)
COMPILER_SHA256 = "06efee6763efb53ae5a2ca325b367ce9cbb8cb80680d76d491d82de44120b740"
LOAD = 0x00400000
STACK = 0x03000000
RETURN = 0x0DEAD000
REPORT = 0x09000000
STEP_LIMIT = 12_000_000


EXPECTED = (
    1, 0x09010000, 40, 0x09020020, 24, 12, 3,
    3, 0x09020020, 24, 12, 3, 0x09010000, 40, 12, 3,
    0x09010000, 40, 12, 3,
    0x1012, 0x1014, 0x1023, 0x7003, 0x12345678, 1, 0, 0,
    1, 2, 0x2000, 0x2012, 0x09010080, 1, 0, 1,
    0, 0, 0x2000, 0x2011, 1, 1, 1,
    1, 0x090100A0, 0x09010000, 12, 2, 0x7040, 0x7040, 2, 1, 1,
)

MUTATIONS = (
    (
        "DisplayBlit never offers the clipped rectangle to DMA",
        "    If DspDmaBlit(*src, srcPitch, sx0, sy0, x0, y0, x1 - x0, y1 - y0) = 1\n",
        "    If 0 = 1\n",
    ),
    (
        "the clipped source offset is discarded",
        "DspDmaBlit(*src, srcPitch, sx0, sy0, x0, y0, x1 - x0, y1 - y0)",
        "DspDmaBlit(*src, srcPitch, 0, 0, x0, y0, x1 - x0, y1 - y0)",
    ),
    (
        "the arbitrary source is not cleaned before DMA reads it",
        "  DmaCacheRect(s, srcPitch, rowBytes, h)\n",
        "  ; hostile mutation: source clean removed\n",
    ),
    (
        "the destination pre-transfer cache pass is omitted",
        "  DspDmaSyncRect(dstX, dstY, w, h)\n\n  If DmaCopy2D",
        "  ; hostile mutation: destination pre-pass removed\n\n  If DmaCopy2D",
    ),
    (
        "a successful DMA blit incorrectly calls the CPU touched path",
        "  ; Deliberately no DspTouched: the engine wrote DRAM, not the CPU cache.\n  dsp_dmaOps",
        "  DspTouched(dstX, dstY, w, h)\n  dsp_dmaOps",
    ),
    (
        "a DMA refusal is falsely reported as handled",
        "    dsp_dmaFail = dsp_dmaFail + 1\n    ProcedureReturn 0\n  EndIf\n\n  ; Hazard B",
        "    dsp_dmaFail = dsp_dmaFail + 1\n    ProcedureReturn 1\n  EndIf\n\n  ; Hazard B",
    ),
)


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextlib.contextmanager
def checker_lock():
    path = pathlib.Path(tempfile.gettempdir()) / "anvil_vk_pipeline_check.lock"
    with path.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        if os.name == "nt":
            import msvcrt
            while True:
                try:
                    stream.seek(0)
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


def load_interpreter():
    spec = importlib.util.spec_from_file_location("display_dma_a64", INTERP)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load A64 interpreter: {INTERP}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def compile_gate(compiler: pathlib.Path, work: pathlib.Path, display_text: str | None):
    source = GATE
    if display_text is not None:
        mutant_display = work / "display.pi4"
        mutant_display.write_text(display_text, encoding="utf-8")
        gate_text = GATE.read_text(encoding="utf-8")
        anchor = 'XIncludeFile "RaspberryPi4/Lib/display.pi4"'
        if gate_text.count(anchor) != 1:
            raise AssertionError("display include anchor is not unique")
        gate_text = gate_text.replace(
            anchor, f'XIncludeFile "{mutant_display.as_posix()}"'
        )
        source = work / "gate.pi4"
        source.write_text(gate_text, encoding="utf-8")
    image = work / "gate.img"
    cmd = [
        str(compiler), "--compile", str(source), "-t", "pi4",
        "--entry-returns", "--load-addr", hex(LOAD),
        "--stack-addr", hex(STACK), "-s", "-o", str(image),
    ]
    run = subprocess.run(
        cmd, cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    if run.returncode != 0 or "pmfc: OK" not in run.stdout:
        raise AssertionError("compile failed\n" + run.stdout)
    return image


def execute(a64, image: pathlib.Path):
    cpu = a64.A64()
    for index, byte in enumerate(image.read_bytes()):
        cpu.memory[LOAD + index] = byte
    a64.attach_symbols(cpu, image, LOAD)
    cpu.pc = LOAD
    cpu.sp = STACK
    cpu.x[30] = RETURN
    mmio = []
    original_load = cpu.load
    original_store = cpu.store

    def load(addr: int, size: int) -> int:
        if addr >= 0xFC000000:
            mmio.append(("read", addr, size))
            return 0
        return original_load(addr, size)

    def store(addr: int, value: int, size: int) -> None:
        if addr >= 0xFC000000:
            mmio.append(("write", addr, size))
            return
        original_store(addr, value, size)

    cpu.load = load
    cpu.store = store
    for steps in range(STEP_LIMIT):
        if cpu.pc == RETURN:
            return cpu, steps, mmio
        cpu.step()
    raise AssertionError(f"gate exceeded {STEP_LIMIT} A64 instructions")


def grade(cpu, mmio):
    got = tuple(
        sum(cpu.memory.get(REPORT + index * 4 + byte, 0) << (byte * 8)
            for byte in range(4))
        for index in range(len(EXPECTED))
    )
    if mmio:
        raise AssertionError(f"unexpected MMIO: {mmio[:3]}")
    for index, (actual, wanted) in enumerate(zip(got, EXPECTED)):
        if actual != wanted:
            raise AssertionError(
                f"report[{index}] got 0x{actual:08X}, expected 0x{wanted:08X}"
            )


def run_one(compiler, a64, display_text=None):
    with tempfile.TemporaryDirectory(prefix="display-dma-blit-") as raw:
        work = pathlib.Path(raw)
        image = compile_gate(compiler, work, display_text)
        cpu, steps, mmio = execute(a64, image)
        grade(cpu, mmio)
        return steps


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", default=str(DEFAULT_COMPILER))
    parser.add_argument("--mutate", action="store_true")
    args = parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    compiler = pathlib.Path(args.compiler).resolve()
    if not compiler.is_file():
        raise SystemExit(f"compiler not found: {compiler}")
    got_hash = digest(compiler)
    if got_hash.lower() != COMPILER_SHA256:
        raise SystemExit(
            f"compiler hash mismatch: got {got_hash}, expected {COMPILER_SHA256}"
        )
    a64 = load_interpreter()
    with checker_lock():
        steps = run_one(compiler, a64)
        print(
            f"display_dma_blit_emitted_check: PASS - {len(EXPECTED)} properties, "
            f"{steps:,} executed A64 instructions"
        )
        print(f"  compiler sha256 {got_hash}")
        if args.mutate:
            production = DISPLAY.read_text(encoding="utf-8")
            rejected = 0
            for name, old, new in MUTATIONS:
                if production.count(old) != 1:
                    raise AssertionError(f"mutation anchor is not unique: {name}")
                mutant = production.replace(old, new)
                try:
                    run_one(compiler, a64, mutant)
                except AssertionError as exc:
                    rejected += 1
                    print(f"  RED    {name} - {exc}")
                else:
                    raise AssertionError(f"mutation survived: {name}")
            print(
                "display_dma_blit_emitted_check: PASS - "
                f"all {rejected} mutations rejected"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

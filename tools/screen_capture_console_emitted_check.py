#!/usr/bin/env python3
"""Execute presented-surface capture and lossless-console emitted code."""

from __future__ import annotations

import importlib.util
import os
import pathlib
import struct
import subprocess
import sys
import tempfile
import zlib


HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from pmf_compiler import resolve_compiler  # noqa: E402
PROBE = ROOT / "RaspberryPi4" / "Tests" / "screen_capture_console_compile.pi4"
LOAD = 0x00400000
STACK = 0x03000000
LOADER_LR = 0xDEAD0000
STEP_LIMIT = 60_000_000
FB = 0x07000000
FB_STEP = 0x1000
OUT = 0x07100000
OUT_STEP = 0x80
MODEL = 0x07101000
STYLE = 0x07101400
MAGIC = 0x43415043
PW, PH = 5, 7
ROTS = (0, 90, 180, 270)


def locate(name: str, local: pathlib.Path) -> pathlib.Path:
    value = os.environ.get(name)
    choices = [pathlib.Path(value)] if value else []
    choices.append(local)
    for path in choices:
        if path.is_file():
            return path.resolve()
    raise SystemExit(
        f"screen capture/console gate: {name} was not found; set {name} "
        f"or provide {local.relative_to(ROOT)}"
    )


def load_interpreter(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("anvil_capture_a64", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load A64 interpreter: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build(compiler: pathlib.Path) -> pathlib.Path:
    work = pathlib.Path(tempfile.gettempdir()) / "anvil_capture_console_emitted"
    work.mkdir(parents=True, exist_ok=True)
    image = work / "capture_console.img"
    cmd = [
        str(compiler), "--compile", PROBE.relative_to(ROOT).as_posix(), "-t", "pi4",
        "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
        "--entry-returns", "-o", str(image), "-s",
    ]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    run = subprocess.run(
        cmd, cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if run.returncode != 0 or "pmfc: OK" not in run.stdout:
        raise SystemExit("screen capture/console gate: build failed\n" + run.stdout)
    return image


def logical_dims(rot: int) -> tuple[int, int]:
    return (PH, PW) if rot in (90, 270) else (PW, PH)


def physical_xy(rot: int, x: int, y: int) -> tuple[int, int]:
    lw, lh = logical_dims(rot)
    if rot == 90:
        return lh - 1 - y, x
    if rot == 270:
        return y, lw - 1 - x
    # 180 is intentionally identity in RAM: HVS mirrors during scan-out.
    return x, y


def colour(slot: int, x: int, y: int) -> int:
    return 0xFF000000 | (slot << 20) | (y << 8) | (x // 2)


def seed(cpu) -> None:
    for slot, rot in enumerate(ROTS):
        base = FB + slot * FB_STEP
        for i in range(PW * PH * 4):
            cpu.memory[base + i] = 0xA5
        lw, lh = logical_dims(rot)
        for y in range(lh):
            for x in range(lw):
                px, py = physical_xy(rot, x, y)
                raw = struct.pack("<I", colour(slot, x, y))
                for i, byte in enumerate(raw):
                    cpu.memory[base + py * PW * 4 + px * 4 + i] = byte


def execute(a64, image: pathlib.Path):
    cpu = a64.A64()
    for i, byte in enumerate(image.read_bytes()):
        cpu.memory[LOAD + i] = byte
    a64.attach_symbols(cpu, image, LOAD)
    cpu.pc = LOAD
    cpu.sp = STACK
    cpu.x[30] = LOADER_LR
    seed(cpu)

    def load(addr: int, size: int) -> int:
        cpu.align_guard(addr, size, False)
        if addr >= 0xFC000000:
            raise SystemExit(f"unexpected MMIO read at ${addr:08X}")
        return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr: int, value: int, size: int) -> None:
        cpu.align_guard(addr, size, True)
        if addr >= 0xFC000000:
            raise SystemExit(f"unexpected MMIO write at ${addr:08X}")
        for i in range(size):
            cpu.memory[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    for steps in range(STEP_LIMIT):
        if cpu.pc == LOADER_LR:
            return cpu, cpu.x[0], steps
        cpu.step()
    raise SystemExit(f"probe exceeded {STEP_LIMIT} emitted instructions")


def u64(cpu, addr: int) -> int:
    return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(8))


def expected_runs(slot: int, rot: int) -> bytes:
    lw, lh = logical_dims(rot)
    records = bytearray()
    for y in range(lh):
        x = 0
        while x < lw:
            value = colour(slot, x, y)
            run = 1
            while x + run < lw and colour(slot, x + run, y) == value:
                run += 1
            records.extend(struct.pack("<II", run, value))
            x += run
    return bytes(records)


def check(cpu) -> None:
    if u64(cpu, OUT - 8) != MAGIC:
        raise SystemExit("probe did not write its magic")
    for slot, rot in enumerate(ROTS):
        at = OUT + slot * OUT_STEP
        lw, lh = logical_dims(rot)
        values = [u64(cpu, at + off) for off in range(0, 72, 8)]
        records = expected_runs(slot, rot)
        expected = [
            rot, lw, lh,
            colour(slot, 0, 0), colour(slot, lw - 1, 0),
            colour(slot, 0, lh - 1), colour(slot, lw - 1, lh - 1),
            len(records) // 8, zlib.crc32(records) & 0xFFFFFFFF,
        ]
        if values != expected:
            raise SystemExit(
                f"rotation {rot} capture mismatch\nactual   {values}\nexpected {expected}"
            )

    lost, queued, scrolls, dirty, paints_before, paints_after, scroll_after = (
        u64(cpu, MODEL + off) for off in (0, 8, 16, 24, 32, 40, 48)
    )
    if (lost, queued, dirty, paints_before, paints_after, scroll_after) != (
        0, 0, 1, 0, 1, 0
    ):
        raise SystemExit(
            "console burst state mismatch: "
            f"lost={lost} queued={queued} dirty={dirty} "
            f"paint={paints_before}->{paints_after} scroll_after={scroll_after}"
        )
    if scrolls != 298:
        raise SystemExit(f"console burst scroll count {scrolls}, expected 298")
    grid = bytes(cpu.memory.get(MODEL + 64 + i, 0) for i in range(640))
    expected_grid = bytearray(b" " * 640)
    for row, line in enumerate((298, 299, 300)):
        expected_grid[row * 160:row * 160 + 149] = bytes([65 + line % 26]) * 149
    if grid != expected_grid:
        raise SystemExit(f"final shared console grid mismatch: {grid!r}")

    if (u64(cpu, STYLE), u64(cpu, STYLE + 8)) != (2, 2):
        raise SystemExit("styled console cursor did not survive wrap/tab/scroll")
    chars = bytes(cpu.memory.get(STYLE + 16 + i, 0) for i in range(24))
    styles = bytes(cpu.memory.get(STYLE + 40 + i, 0) for i in range(24))
    expected_chars = b"        12345678AC      "
    expected_styles = bytes([0] * 8 + [1] * 8 + [0, 1] + [0] * 6)
    if chars != expected_chars or styles != expected_styles:
        raise SystemExit(
            "styled terminal state mismatch after wrap/tab/scroll/backspace\n"
            f"chars  {chars!r}\nstyles {list(styles)}"
        )
    clear_chars = bytes(cpu.memory.get(STYLE + 64 + i, 0) for i in range(24))
    clear_styles = bytes(cpu.memory.get(STYLE + 88 + i, 0) for i in range(24))
    if clear_chars != b" " * 24 or clear_styles != bytes(24):
        raise SystemExit("console clear did not reset characters and styles together")


def check_source_contract() -> None:
    uart = (ROOT / "RaspberryPi4/Lib/uart.pi4").read_text(encoding="utf-8")
    board = (ROOT / "RaspberryPi4/Board/board.pi4").read_text(encoding="utf-8")
    dma = (ROOT / "RaspberryPi4/Board/screen_cmd.pi4").read_text(encoding="utf-8")
    v3d = (ROOT / "RaspberryPi4/Board/v3d_console.pi4").read_text(encoding="utf-8")

    prompt = 'Print("pmf> ")'
    at = board.index(prompt)
    before = board.rfind("UartScreenStyle(#UART_SCREEN_STYLE_PROMPT)", 0, at)
    after = board.find("UartScreenStyle(#UART_SCREEN_STYLE_NORMAL)", at)
    if before < 0 or after < 0 or at - before > 300 or after - at > 300:
        raise SystemExit("prompt is not tightly bracketed by screen-only style changes")
    if "uart_AuxPut(c)" not in uart or "uart_mirrorStyle[uart_mirrorHead]" not in uart:
        raise SystemExit("UART screen and network fan-out no longer have separate paths")
    if "uart_auxStyle" in uart or "UartWrite(27)" in board or "\\x1b" in board:
        raise SystemExit("screen styling leaked into the raw/network protocol")
    for name, text, colour in (
        ("DMA", dma, "DisplayRGB(80, 255, 120)"),
        ("V3D", v3d, "Neon_RGBA(80, 255, 120, 255)"),
    ):
        if "ConGridStyleRunText" not in text or colour not in text:
            raise SystemExit(f"{name} renderer does not paint bright-green style runs")


def main() -> int:
    check_source_contract()
    _compiler_named = os.environ.get("PMF_COMPILER")
    compiler = (pathlib.Path(resolve_compiler(_compiler_named)) if _compiler_named
                else locate("PMF_COMPILER", ROOT / "PureMetalForge.exe"))
    interp = locate("PMF_A64_INTERP", ROOT / "tools" / "a64" / "a64_interp.py")
    image = build(compiler)
    cpu, rc, steps = execute(load_interpreter(interp), image)
    if rc != 0:
        raise SystemExit(f"probe returned {rc}")
    check(cpu)
    print(
        "screen_capture_console_emitted_check: PASS "
        f"(4 rotations + RLE CRC, 45150 bytes lossless, styled terminal ops, {steps} instructions)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

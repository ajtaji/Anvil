#!/usr/bin/env python3
"""Run the compiled Neon orientation boundary in the A64 interpreter.

This is an emitted-code gate, not a renderer or board simulation.  It executes
the real procedures in RaspberryPi4/Lib/neon.pi4 and independently checks the
DRAM records they emit.  V3D submission, DMA and display MMIO are deliberately
outside the probe; those remain board-proof obligations.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import struct
import subprocess
import sys
import tempfile


HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
PROBE = ROOT / "RaspberryPi4" / "Tests" / "neon_orientation_compile.pi4"
LOAD = 0x00400000
STACK = 0x03000000
LOADER_LR = 0xDEAD0000
STEP_LIMIT = 20_000_000

OUT = 0x06000000
REC_BYTES = 0x1000
POINT_OFF = 0x000
RECT_OFF = 0x100
GLYPH_OFF = 0x300
CLIP_OFF = 0x500
MAGIC = 0x4F524E54

W, H = 1280, 800
ROTS = (0, 90, 180, 270)
POINTS = ((0, 0), (W, 0), (0, H), (W, H), (37, 61))
RECTS = ((10, 20, 30, 40), (W - 19, H - 23, 19, 23))
GLYPH = (
    (101, 203, 0x3E800000, 0x3E000000),
    (101, 235, 0x3E800000, 0x3F600000),
    (117, 203, 0x3F400000, 0x3E000000),
    (101, 235, 0x3E800000, 0x3F600000),
    (117, 235, 0x3F400000, 0x3F600000),
    (117, 203, 0x3F400000, 0x3E000000),
)


def locate_interpreter() -> pathlib.Path:
    choices = []
    if os.environ.get("PMF_A64_INTERP"):
        choices.append(pathlib.Path(os.environ["PMF_A64_INTERP"]))
    choices.append(ROOT / "tools" / "a64" / "a64_interp.py")
    for path in choices:
        if path.is_file():
            return path
    raise SystemExit(
        "display emitted gate: a64_interp.py was not found; set "
        "PMF_A64_INTERP or add the existing tools/a64 closure"
    )


def load_interpreter(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("anvil_a64_interp", path)
    if spec is None or spec.loader is None:
        raise SystemExit("display emitted gate: cannot load %s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def locate_compiler() -> pathlib.Path:
    choices = []
    if os.environ.get("PMF_COMPILER"):
        choices.append(pathlib.Path(os.environ["PMF_COMPILER"]))
    choices.append(ROOT / "PureMetalForge.exe")
    for path in choices:
        if path.is_file():
            return path
    raise SystemExit("display emitted gate: PureMetalForge.exe was not found; set PMF_COMPILER")


def build() -> pathlib.Path:
    compiler = locate_compiler()
    work = pathlib.Path(tempfile.gettempdir()) / "anvil_display_emitted"
    work.mkdir(parents=True, exist_ok=True)
    image = work / "orientation.img"
    cmd = [
        str(compiler), "--compile",
        str(PROBE.relative_to(ROOT)).replace("\\", "/"),
        "-t",
        "pi4",
        "--load-addr",
        hex(LOAD),
        "--stack-addr",
        hex(STACK),
        "--entry-returns",
        "-o",
        str(image),
        "-s",
    ]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    run = subprocess.run(
        cmd, cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
    )
    if run.returncode != 0 or "pmfc: OK" not in run.stdout:
        raise SystemExit("display emitted gate: build failed\n" + run.stdout)
    return image


def execute(a64, image: pathlib.Path):
    cpu = a64.A64()
    for i, byte in enumerate(image.read_bytes()):
        cpu.memory[LOAD + i] = byte
    a64.attach_symbols(cpu, image, LOAD)
    cpu.pc = LOAD
    cpu.sp = STACK
    cpu.x[30] = LOADER_LR

    def load(addr: int, size: int) -> int:
        cpu.align_guard(addr, size, False)
        if addr >= 0xFC000000:
            raise SystemExit(
                "display emitted gate: unexpected MMIO read at $%08X" % addr
            )
        return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr: int, value: int, size: int) -> None:
        cpu.align_guard(addr, size, True)
        if addr >= 0xFC000000:
            raise SystemExit(
                "display emitted gate: unexpected MMIO write at $%08X" % addr
            )
        for i in range(size):
            cpu.memory[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    for steps in range(STEP_LIMIT):
        if cpu.pc == LOADER_LR:
            return cpu, cpu.x[0], steps
        cpu.step()
    raise SystemExit(
        "display emitted gate: probe did not return in %d instructions"
        % STEP_LIMIT
    )


def u16(cpu, addr: int) -> int:
    return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(2))


def u32(cpu, addr: int) -> int:
    return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(4))


def physical_dims(rot: int) -> tuple[int, int]:
    return (H, W) if rot in (90, 270) else (W, H)


def point(rot: int, x: int, y: int) -> tuple[int, int]:
    if rot == 90:
        return H - y, x
    if rot == 180:
        return W - x, H - y
    if rot == 270:
        return y, W - x
    return x, y


def rect(rot: int, x: int, y: int, w: int, h: int):
    if rot == 90:
        return H - (y + h), x, h, w
    if rot == 180:
        return W - (x + w), H - (y + h), w, h
    if rot == 270:
        return y, W - (x + w), h, w
    return x, y, w, h


def f32_ratio_bits(n: int, d: int) -> int:
    return struct.unpack("<I", struct.pack("<f", n / d))[0]


def vertex_words(px: int, py: int, pw: int, ph: int) -> tuple[int, ...]:
    cx, cy = pw // 2, ph // 2
    return (
        f32_ratio_bits(px - cx, cx),
        f32_ratio_bits(py - cy, cy),
        ((px - cx) * 256) & 0xFFFFFFFF,
        ((py - cy) * 256) & 0xFFFFFFFF,
    )


def words(cpu, addr: int, count: int) -> tuple[int, ...]:
    return tuple(u32(cpu, addr + i * 4) for i in range(count))


def require(name: str, got, want, failures: list[str]) -> None:
    if got != want:
        failures.append("%s: got %r, wanted %r" % (name, got, want))


def grade(cpu) -> tuple[list[str], int]:
    failures: list[str] = []
    checks = 0
    require("probe magic", u32(cpu, OUT - 8), MAGIC, failures)
    checks += 1

    for slot, rot in enumerate(ROTS):
        base = OUT + slot * REC_BYTES
        pw, ph = physical_dims(rot)

        for index, (x, y) in enumerate(POINTS):
            px, py = point(rot, x, y)
            got = words(cpu, base + POINT_OFF + index * 16, 4)
            require(
                "rot%d point(%d,%d)" % (rot, x, y),
                got,
                vertex_words(px, py, pw, ph),
                failures,
            )
            checks += 1

        at = base + RECT_OFF
        for index, logical in enumerate(RECTS):
            x, y, w, h = rect(rot, *logical)
            want_points = (
                (x, y), (x, y + h), (x + w, y),
                (x, y + h), (x + w, y + h), (x + w, y),
            )
            want = tuple(
                word for px, py in want_points
                for word in vertex_words(px, py, pw, ph)
            )
            got = words(cpu, at + index * 96, 24)
            require("rot%d rect%d" % (rot, index), got, want, failures)
            checks += 1

        want_glyph = []
        for x, y, u, v in GLYPH:
            px, py = point(rot, x, y)
            xy = vertex_words(px, py, pw, ph)
            want_glyph.extend(
                (xy[0], xy[1], 0x00000000, 0x3F800000,
                 xy[2], xy[3], 0x00000000, 0x3F800000, u, v)
            )
        require(
            "rot%d textured glyph geometry/UV" % rot,
            words(cpu, base + GLYPH_OFF, 60),
            tuple(want_glyph),
            failures,
        )
        checks += 1

        # Logical (-5, 790, 30, 20) clamps to (0, 790, 25, 10) before
        # the half-open rectangle transform.  This specifically crosses the
        # right/bottom boundary where a pixel-centre -1 would be wrong.
        cx, cy, cw, ch = rect(rot, 0, 790, 25, 10)
        clip = base + CLIP_OFF
        got_clip = (
            cpu.memory.get(clip, 0),
            u16(cpu, clip + 1), u16(cpu, clip + 3),
            u16(cpu, clip + 5), u16(cpu, clip + 7),
        )
        require(
            "rot%d scissor packet" % rot,
            got_clip,
            (107, cx, cy, cw, ch),
            failures,
        )
        checks += 1

    return failures, checks


def main() -> int:
    interp = locate_interpreter()
    a64 = load_interpreter(interp)
    image = build()
    cpu, rc, steps = execute(a64, image)
    failures, checks = grade(cpu)
    if rc != 0:
        failures.insert(0, "compiled Main returned %d" % rc)
    if failures:
        print("display emitted gate: FAIL (%d checks, %d instructions)" % (checks, steps))
        for failure in failures:
            print("  " + failure)
        return 1
    print("display emitted gate: PASS")
    print("  compiled and interpreted %d A64 instructions" % steps)
    print("  %d independent record checks across rotations %s" % (checks, ROTS))
    print("  real Neon vertex, rectangle, textured-glyph and scissor emitters ran")
    print("  no GPU submission, DMA or display MMIO was modelled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

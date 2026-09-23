#!/usr/bin/env python3
"""Emit and exercise the shared, transport-neutral EDID parser."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "Anvil" / "Graphics" / "Tests" / "edid_parse_gate.pi3"
INTERPRETER = ROOT / "tools" / "a64" / "a64_interp.py"
LOAD = 0x400000
STACK = 0x3000000
RETURN = 0x7000000
CONTROL = 0x06000000
EDID = 0x06000100


def load_interpreter():
    spec = importlib.util.spec_from_file_location("edid_parse_a64", INTERPRETER)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load A64 interpreter: {INTERPRETER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build(compiler: Path, out: Path):
    image = out / "edid-parse.img"
    cmd = [str(compiler), "--compile", str(SOURCE), "-t", "pi3",
           "--entry-returns", "--load-addr", hex(LOAD),
           "--stack-addr", hex(STACK), "-s", "-o", str(image)]
    result = subprocess.run(cmd, cwd=ROOT,
                            env=dict(os.environ, PMF_ROOT=str(ROOT)),
                            capture_output=True, text=True)
    if result.returncode or not image.is_file():
        raise SystemExit("EDID parser gate compile failed\n" + result.stdout + result.stderr)
    sym = Path(str(image) + ".sym")
    if not sym.is_file():
        raise SystemExit("compiler omitted EDID fixture symbols")
    symbols = {k.lower(): int(v, 0) for k, v in
               (line.split("=", 1) for line in sym.read_text().splitlines() if "=" in line)}
    return image.read_bytes(), symbols


def write32(cpu, address, value):
    for i, b in enumerate((value & 0xFFFFFFFF).to_bytes(4, "little")):
        cpu.memory[address + i] = b


def read32(cpu, address):
    return sum(cpu.memory.get(address + i, 0) << (8 * i) for i in range(4))


def dtd(width, height, clock10=6500):
    b = bytearray(18)
    hb, hf, hs = 320, 24, 136
    vb, vf, vs = 38, 3, 6
    b[0:2] = clock10.to_bytes(2, "little")
    b[2], b[3] = width & 255, hb & 255
    b[4] = ((width >> 8) << 4) | (hb >> 8)
    b[5], b[6] = height & 255, vb & 255
    b[7] = ((height >> 8) << 4) | (vb >> 8)
    b[8], b[9] = hf & 255, hs & 255
    b[10] = ((vf & 15) << 4) | (vs & 15)
    b[11] = ((hf >> 8) << 6) | ((hs >> 8) << 4) | ((vf >> 4) << 2) | (vs >> 4)
    b[17] = 0x1E
    return b


def dtd_1080p60():
    b = bytearray(18)
    width, height, hb, vb = 1920, 1080, 280, 45
    hf, hs, vf, vs = 88, 44, 4, 5
    b[0:2] = (14850).to_bytes(2, "little")
    b[2], b[3], b[4] = width & 255, hb & 255, ((width >> 8) << 4) | (hb >> 8)
    b[5], b[6], b[7] = height & 255, vb & 255, ((height >> 8) << 4) | (vb >> 8)
    b[8], b[9], b[10] = hf, hs, (vf << 4) | vs
    b[11] = 0
    b[17] = 0x1E
    return b


def checksum(block):
    block[127] = (-sum(block[:127])) & 255


def fixture_edid(*, extension=False, bad_base=False, bad_ext=False,
                 bad_porch=False, interlaced=False, preferred_dtd=None):
    base = bytearray(128)
    base[:8] = bytes.fromhex("00 ff ff ff ff ff ff 00")
    base[18:20] = bytes((1, 4))
    base[24] = 2
    preferred = bytearray(preferred_dtd) if preferred_dtd is not None else dtd(1024, 768)
    if bad_porch:
        preferred[8], preferred[9] = 250, 250  # exceeds 320-pixel blanking
    if interlaced:
        preferred[17] |= 0x80
    base[54:72] = preferred
    base[126] = int(extension)
    checksum(base)
    if bad_base:
        base[127] ^= 1
    if not extension:
        return bytes(base)
    cta = bytearray(128)
    cta[0], cta[1], cta[2] = 2, 3, 6
    cta[4], cta[5] = 0x41, 16  # one SVD, CTA VIC 16: 1920x1080p60
    checksum(cta)
    if bad_ext:
        cta[127] ^= 1
    return bytes(base + cta)


class Runner:
    def __init__(self, a64, blob, symbols):
        self.cpu = a64.A64()
        self.symbols = symbols
        self.cpu.memory.update({LOAD + i: b for i, b in enumerate(blob)})
        self.cpu.enable_system_registers(el=3, preset={0xD51E1000: 0})

    def call(self, selector, *args, limit=1_000_000):
        for i in range(16):
            write32(self.cpu, CONTROL + i * 8, 0)
        write32(self.cpu, CONTROL, selector)
        for i, arg in enumerate(args):
            write32(self.cpu, CONTROL + 8 + i * 8, arg)
        self.cpu.pc = LOAD + self.symbols["main"]
        self.cpu.sp = STACK
        self.cpu.x[30] = RETURN
        for n in range(limit):
            if self.cpu.pc == RETURN:
                return self.cpu.x[0], n
            self.cpu.step()
        raise AssertionError(f"selector {selector} exceeded instruction limit")

    def put_edid(self, data):
        for i, b in enumerate(data):
            self.cpu.memory[EDID + i] = b


def run_cases(a64, blob, symbols):
    checks = 0
    steps = 0
    runner = Runner(a64, blob, symbols)

    def call(sel, *args):
        nonlocal steps
        value, count = runner.call(sel, *args)
        steps += count
        return value

    # One base block with preferred DTD; parser API remains mode-format neutral.
    runner.put_edid(fixture_edid())
    assert call(1, 128, 1, 0) == 1
    assert (call(5), call(8), call(9), call(2), call(3)) == (1, 1, 0, 1024, 768)
    assert call(10) == 65000
    assert call(11) > 0
    assert tuple(call(n) for n in range(13, 24)) == (
        1, 1048, 1184, 1344, 771, 777, 806, 0, 1, 1, 1)
    checks += 18

    # Malformed porches cannot become a programmable timing. Interlace and
    # sync polarity are preserved explicitly so a board can refuse rather
    # than silently inventing a progressive mode.
    runner.put_edid(fixture_edid(bad_porch=True))
    assert call(1, 128, 1, 0) == 1 and call(13) == 0
    runner.put_edid(fixture_edid(interlaced=True))
    assert call(1, 128, 1, 0) == 1
    assert call(13) == 1 and call(20) == 1 and call(11) == 0
    checks += 6

    # Canonical CEA-861 1080p60 detailed timing: retain every programmable
    # field and report refresh in milli-Hz, not Hz.
    runner.put_edid(fixture_edid(preferred_dtd=dtd_1080p60()))
    assert call(1, 128, 1, 0) == 1
    assert (call(2), call(3), call(10), call(11)) == (1920, 1080, 148500, 60000)
    assert tuple(call(n) for n in range(13, 20)) == (
        1, 2008, 2052, 2200, 1084, 1089, 1125)
    checks += 12

    # Valid CTA extension contributes a second mode without displacing base DTD.
    runner.put_edid(fixture_edid(extension=True))
    assert call(1, 256, 2, 0) == 1
    assert (call(2), call(3), call(8), call(9), call(6)) == (1024, 768, 2, 1, 0)
    found_1080 = False
    count = call(4)
    for index in range(count):
        write32(runner.cpu, CONTROL + 8 + 4 * 4, index)
        assert call(12, index) == 1
        if read32(runner.cpu, CONTROL + 0x28) == 1920 and read32(runner.cpu, CONTROL + 0x30) == 1080:
            found_1080 = True
    assert found_1080
    checks += 6 + count

    # Transport-reported truncation remains visible; a bad extension checksum
    # cannot silently contribute modes but does not erase the valid base block.
    runner.put_edid(fixture_edid(extension=True))
    assert call(1, 128, 1, 1) == 1
    assert call(6) == 1 and call(5) == 1
    checks += 3
    runner.put_edid(fixture_edid(extension=True, bad_ext=True))
    assert call(1, 256, 2, 0) == 1
    assert call(5) == 1 and call(6) == 1 and call(7) == 5
    checks += 4

    # Refuse malformed base/checksum/length and clear stale state each attempt.
    for data, size, blocks, expected_error in (
        (fixture_edid(bad_base=True), 128, 1, 3),
        (bytes([1]) + fixture_edid()[1:], 128, 1, 2),
        (fixture_edid(), 127, 1, 1),
        (fixture_edid(), 128, 9, 1),
    ):
        runner.put_edid(data)
        assert call(1, size, blocks, 0) == 0
        assert call(5) == 0 and call(7) == expected_error
        checks += 3
    assert call(12, 9999) == 0
    checks += 1
    return checks, steps


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True)
    args = parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    compiler = Path(args.compiler).resolve()
    if not compiler.is_file():
        raise SystemExit(f"compiler not found: {compiler}")
    with tempfile.TemporaryDirectory(prefix="anvil-edid-parse-") as tmp:
        blob, symbols = build(compiler, Path(tmp))
        missing = [n for n in ("main", "anviledidparse", "anviledidmodeat") if n not in symbols]
        if missing:
            raise SystemExit("missing emitted parser procedures: " + ", ".join(missing))
        checks, steps = run_cases(load_interpreter(), blob, symbols)
    print(f"PASS: {checks} shared EDID parser assertions / {steps:,} A64 instructions")
    print("  standalone parser fixture has no board transport dependencies")
    print("  full base-DTD porches/sync/polarity; malformed porch and interlace visibility")
    print("  CTA SVD, bounds, truncation, checksum and stale-state cases")
    print("Compiler SHA256:", hashlib.sha256(compiler.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()

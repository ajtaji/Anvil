#!/usr/bin/env python3
"""Compile the portable clock probe and compare emitted A64 with Python's calendar."""

from __future__ import annotations

import argparse
import datetime as dt
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import tcp_multiif_emitted_check as emitted
from pmf_compiler import resolve_compiler

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "RaspberryPi4" / "Tests" / "wallclock_emitted_probe.pi4"
LOAD = 0x00400000
STACK = 0x03000000
STACK_BYTES = 0x00100000
LOADER_LR = 0xDEAD0000
UART_DR = 0xFE201000
UART_FR = 0xFE201018
CNTFRQ = 54_000_000
UTC = dt.timezone.utc


def build(compiler: Path, work: Path) -> Path:
    staged = work / compiler.name
    shutil.copy2(compiler, staged)
    if (ROOT / "Boards").is_dir():
        shutil.copytree(ROOT / "Boards", work / "Boards")
    image = work / "wallclock_gate.img"
    command = [
        str(staged), "--compile", PROBE.relative_to(ROOT).as_posix(), "-t", "pi4",
        "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
        "--entry-returns", "-o", str(image), "-s",
    ]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    run = subprocess.run(command, cwd=ROOT, env=env, text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise SystemExit("wall-clock emitted gate: compile failed\n" + run.stdout)
    return image


def run(a64, image: Path, ticks_per_step: int, stop: bytes | None = None,
        limit: int = 60_000_000) -> tuple[str, int]:
    blob = image.read_bytes()
    bss_lo, bss_hi = emitted.symbol_bounds(image.with_suffix(image.suffix + ".sym"))
    readable = ((LOAD, LOAD + len(blob)), (bss_lo, bss_hi),
                (STACK - STACK_BYTES, STACK + 16))
    writable = ((bss_lo, bss_hi), (STACK - STACK_BYTES, STACK + 16))

    def contains(ranges, address: int, size: int) -> bool:
        return size > 0 and any(lo <= address and address + size <= hi for lo, hi in ranges)

    cpu = a64.A64()
    for offset, byte in enumerate(blob):
        cpu.memory[LOAD + offset] = byte
    a64.attach_symbols(cpu, image, LOAD)
    cpu.pc = LOAD
    cpu.sp = STACK
    cpu.x[30] = LOADER_LR
    uart = bytearray()
    ticks = 0

    def load(address: int, size: int) -> int:
        cpu.align_guard(address, size, False)
        if address == UART_FR:
            return 0
        if not contains(readable, address, size):
            raise SystemExit(f"wall-clock gate: read outside image/BSS/stack at ${address:08X}+{size}")
        return sum(cpu.memory.get(address + i, 0) << (8 * i) for i in range(size))

    def store(address: int, value: int, size: int) -> None:
        cpu.align_guard(address, size, True)
        if address == UART_DR:
            uart.append(value & 0xFF)
            return
        if not contains(writable, address, size):
            raise SystemExit(f"wall-clock gate: write outside BSS/stack at ${address:08X}+{size}")
        for i in range(size):
            cpu.memory[address + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    plain_step = a64.A64.step.__get__(cpu)
    for steps in range(limit):
        if cpu.pc == LOADER_LR:
            return uart.decode("ascii", "replace"), steps
        ticks += ticks_per_step
        ins = load(cpu.pc, 4)
        if (ins & 0xFFFFFFE0) == 0xD53BE000:       # mrs Xt,cntfrq_el0
            cpu.x[ins & 31] = CNTFRQ
            cpu.pc += 4
        elif (ins & 0xFFFFFFE0) == 0xD53BE020:     # mrs Xt,cntpct_el0
            cpu.x[ins & 31] = ticks
            cpu.pc += 4
        else:
            plain_step()
        if stop is not None and uart.endswith(stop):
            return uart.decode("ascii", "replace"), steps + 1
    raise SystemExit(f"wall-clock gate: no return in {limit:,} instructions")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"))
    args = parser.parse_args()
    compiler = Path(resolve_compiler(args.compiler))
    interp = emitted.required_path(args.interp, "PMF_A64_INTERP")
    a64 = emitted.load_interpreter(interp)

    with tempfile.TemporaryDirectory(prefix="anvil-wallclock-emitted-") as temporary:
        image = build(compiler, Path(temporary))
        text, steps = run(a64, image, 1)
        moving, moving_steps = run(a64, image, 54_000,
                                   b"--- monotonic done ---\r\n")

    failures: list[str] = []

    def number(label: str, body: str = text) -> int | None:
        match = re.search(re.escape(label) + r"\s+(-?\d+)\b", body)
        return int(match.group(1)) if match else None

    def words(label: str, body: str = text) -> str | None:
        match = re.search(re.escape(label) + r"  (.*)", body)
        return match.group(1).strip() if match else None

    def expect(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    epoch_min = int(dt.datetime(1980, 1, 1, tzinfo=UTC).timestamp())
    epoch_max = int(dt.datetime(2100, 1, 1, tzinfo=UTC).timestamp())
    ntp_epoch = int((dt.datetime(1970, 1, 1, tzinfo=UTC) -
                     dt.datetime(1900, 1, 1, tzinfo=UTC)).total_seconds())

    expect(number("init            ") == 1, "portable tick source did not initialize")
    expect(number("now      (want -1)") == -1, "unset clock returned a plausible time")
    expect(number("fat date (want 0)") == 0 and number("fat time (want 0)") == 0,
           "unset clock reached the FAT seam")
    expect((words("line            ") or "").startswith("clock not set"),
           "unset status did not say clock not set")

    samples = number("samples         ")
    stride = number("stride          ")
    expect(samples == 1000 and stride is not None, "calendar corpus shape changed")
    checksum = 0
    if samples is not None and stride is not None:
        for i in range(samples):
            when = dt.datetime.fromtimestamp(epoch_min + i * stride, UTC)
            packed = (((((when.year * 13 + when.month) * 32 + when.day) * 24
                         + when.hour) * 60 + when.minute) * 60 + when.second)
            checksum = (checksum * 131 + packed) % 1_000_000_007
    expect(number("roundtrip bad (want 0)") == 0, "epoch/civil round-trip failed")
    expect(number("checksum        ") == checksum,
           "1000-date civil checksum disagrees with Python datetime")

    expect(number("2026-02-29  (want -1)") == -1, "invalid leap day was accepted")
    expect(number("2026-04-31  (want -1)") == -1, "31 April was accepted")
    expect(number("2028-02-29  (want ok)") == int(dt.datetime(2028, 2, 29, tzinfo=UTC).timestamp()),
           "valid leap day was refused")
    expect(number("trusted    (want 0)") == 0, "restored floor was marked trusted")
    expect(number("fat date   (want 0)") == 0 and number("fat time   (want 0)") == 0,
           "restored floor reached the FAT seam")
    expect(number("now unchanged   ") == int(dt.datetime(2026, 1, 1, 12, tzinfo=UTC).timestamp()),
           "fixed display zone moved stored UTC")
    expect(number("ntp epoch const ") == ntp_epoch, "NTP epoch offset is wrong")
    expect(number("decode small (want -1)") == -1 and number("decode huge (want -1)") == -1,
           "restored text range validation failed")
    expect(epoch_min + 999 * (stride or 0) < epoch_max, "calendar corpus left supported range")

    age0 = number("age first       ", moving)
    age1 = number("age later       ", moving)
    micros = [int(v) for v in re.findall(r"micros sample\s+(-?\d+)", moving)]
    expect(age0 is not None and age1 is not None and age1 > age0,
           "monotonic source age did not advance")
    expect(len(micros) >= 12 and all(0 <= v <= 999_999 for v in micros)
           and max(micros, default=0) > 1000,
           "subsecond phase is absent, out of range, or scaled as milliseconds")

    if failures:
        print("wallclock_emitted_check: FAIL")
        for failure in failures:
            print("  " + failure)
        return 1
    print("wallclock_emitted_check: PASS - independent Python calendar agrees over "
          f"1,000 instants; {steps:,}+{moving_steps:,} A64 instructions")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Execute Anvil's real banner overlay for all rotations in the A64 model."""

from __future__ import annotations

import argparse
import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROBE = ROOT / "RaspberryPi4" / "Tests" / "banner_clock_emitted_gate.pi4"
INTERP = ROOT / "tools" / "a64" / "a64_interp.py"
LOAD, STACK, RETURN_PC = 0x00400000, 0x03000000, 0xDEAD0000
OUT, META, SLOT = 0x06000000, 0x06800000, 0x20000
PW, PH, PITCH = 128, 160, 512
ROTS = (0, 90, 180, 270)
BG, FG, CUR = 0xFF101820, 0xFF788496, 0xFFF09A32


def path(value: str | None, label: str) -> pathlib.Path:
    if not value:
        raise SystemExit("banner clock gate: pass --%s or set %s" % (label.lower(), label))
    result = pathlib.Path(value).expanduser().resolve()
    if not result.is_file():
        raise SystemExit("banner clock gate: %s not found: %s" % (label, result))
    return result


def module(source: pathlib.Path):
    spec = importlib.util.spec_from_file_location("anvil_banner_a64", source)
    if spec is None or spec.loader is None:
        raise SystemExit("banner clock gate: cannot load %s" % source)
    result = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = result
    spec.loader.exec_module(result)
    return result


def u32(cpu, at: int) -> int:
    return sum(cpu.memory.get(at + i, 0) << (i * 8) for i in range(4))


def u64(cpu, at: int) -> int:
    return sum(cpu.memory.get(at + i, 0) << (i * 8) for i in range(8))


def dims(rot: int) -> tuple[int, int]:
    return (PH, PW) if rot in (90, 270) else (PW, PH)


def point(rot: int, x: int, y: int) -> tuple[int, int]:
    if rot == 90:
        return PW - 1 - y, x
    if rot == 270:
        return y, PH - 1 - x
    return x, y


def pixel(cpu, base: int, rot: int, x: int, y: int) -> int:
    px, py = point(rot, x, y)
    return u32(cpu, base + py * PITCH + px * 4)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pmfc", default=os.environ.get("PMFC"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP") or str(INTERP))
    args = parser.parse_args()
    pmfc, a64 = path(args.pmfc, "PMFC"), module(path(args.interp, "PMF_A64_INTERP"))

    with tempfile.TemporaryDirectory(prefix="anvil-banner-clock-") as temporary:
        image = pathlib.Path(temporary) / "banner_clock.img"
        command = [str(pmfc), str(PROBE.relative_to(ROOT)).replace("\\", "/"),
                   "-t", "pi4", "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
                   "--entry-returns", "-o", str(image), "-s"]
        env = os.environ.copy()
        env["PMF_ROOT"] = str(ROOT)
        built = subprocess.run(command, cwd=ROOT, env=env, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        if built.returncode != 0 or not image.is_file():
            raise SystemExit("banner clock gate: compile failed\n" + built.stdout)
        cpu = a64.A64()
        for offset, byte in enumerate(image.read_bytes()):
            cpu.memory[LOAD + offset] = byte
        a64.attach_symbols(cpu, image, LOAD)
        cpu.pc, cpu.sp, cpu.x[30] = LOAD, STACK, RETURN_PC
        for steps in range(5_000_000):
            if cpu.pc == RETURN_PC:
                break
            cpu.step()
        else:
            raise SystemExit("banner clock gate: probe did not return")

        failures: list[str] = []
        checks = 0
        for slot, rot in enumerate(ROTS):
            base = OUT + slot * SLOT
            # Cell clear, two seeded font bits, and the cursor redrawn over it.
            samples = ((10, 94, FG), (11, 95, FG), (17, 109, BG),
                       (12, 94, CUR), (13, 95, CUR))
            for x, y, expected in samples:
                got = pixel(cpu, base, rot, x, y)
                checks += 1
                if got != expected:
                    failures.append("rot%d pixel(%d,%d)=%08X wanted %08X" %
                                    (rot, x, y, got, expected))

            # Independently derive the physical bounding box and the exact
            # row-batched coherency calls captured by the test stub.
            corners = [point(rot, x, y) for x in (10, 25) for y in (94, 109)]
            lo_x, hi_x = min(x for x, _ in corners), max(x for x, _ in corners)
            lo_y, hi_y = min(y for _, y in corners), max(y for _, y in corners)
            count = u64(cpu, META + slot * 0x1000 + 0xFF0)
            checks += 1
            if count != hi_y - lo_y + 1:
                failures.append("rot%d clean count %d wanted %d" %
                                (rot, count, hi_y - lo_y + 1))
            for row in range(count):
                address = u64(cpu, META + slot * 0x1000 + row * 16)
                size = u64(cpu, META + slot * 0x1000 + row * 16 + 8)
                wanted_address = base + (lo_y + row) * PITCH + lo_x * 4
                wanted_size = (hi_x - lo_x + 1) * 4
                checks += 2
                if address != wanted_address or size != wanted_size:
                    failures.append("rot%d clean row%d=(%X,%d) wanted (%X,%d)" %
                                    (rot, row, address, size, wanted_address, wanted_size))
        if cpu.x[0] != 0:
            failures.append("compiled Main returned %d" % cpu.x[0])
        if failures:
            print("banner_clock_emitted_check: FAIL - %d checks" % checks)
            for failure in failures:
                print("  " + failure)
            return 1
        checks += 4  # Main return plus arm/disarm/pump early-log assertions.
        print("banner_clock_emitted_check: PASS - %d checks, %d emitted A64 instructions" %
              (checks, steps))
        print("  real early-log service, overlay glyph, cursor redraw, rotation and row-batched damage ran")
        print("  cache calls were recorded in memory; no GPU/DMA/MMIO was modelled")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

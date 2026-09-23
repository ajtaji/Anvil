#!/usr/bin/env python3
"""Emitted test of the isolated Pi 3 Wi-Fi HwLink frame adapter."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pi3_gate_build  # noqa: E402
import truetype_slots_check as slots  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "RaspberryPi3/Tests/hw_link_wifi_gate.pi3"
LOAD, STACK, LIMIT = 0x00400000, 0x03000000, 1_000_000


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--compiler", required=True, type=Path)
    args = ap.parse_args()
    compiler = args.compiler.expanduser().resolve()
    if not compiler.is_file():
        raise SystemExit("compiler does not exist")
    with tempfile.TemporaryDirectory(prefix="anvil-pi3-hwlink-") as name:
        temp = Path(name)
        source, image = temp / "hw_link_wifi.pi3", temp / "hw_link_wifi.img"
        source.write_text(GATE.read_text(encoding="utf-8"), encoding="utf-8")
        env = os.environ.copy()
        env["PMF_ROOT"] = str(ROOT)

        def compile_fixture() -> None:
            result = subprocess.run(
                [str(compiler), "--compile", str(source), "-t", "pi3", "--entry-returns",
                 "--load-addr", hex(LOAD), "--stack-addr", hex(STACK), "-s", "-o", str(image)],
                cwd=ROOT, env=env, capture_output=True, text=True,
            )
            if result.returncode or "pmfc: OK" not in result.stdout or not image.is_file():
                raise SystemExit("Pi3 HwLink fixture compile failed\n" + result.stdout + result.stderr)

        pi3_gate_build.compile_counted(
            compile_fixture, source, image, compiler=compiler,
            by="tools/pi3_hw_link_wifi_check.py", root=ROOT,
        )
        symbols = slots.base.parse_symbols(image)
        cpu = slots.base.load_interp(slots.base.INTERP).A64()
        cpu.memory = {LOAD + i: value for i, value in enumerate(image.read_bytes())}
        cpu.sp = STACK
        cpu.pc = LOAD + symbols["main"]
        cpu.x[30] = slots.base.RETURN_PC
        steps = 0
        while steps < LIMIT and cpu.pc != slots.base.RETURN_PC:
            cpu.step()
            steps += 1
        if cpu.pc != slots.base.RETURN_PC:
            raise SystemExit(f"Pi3 HwLink fixture exceeded {LIMIT:,} A64 instructions")
        result = cpu.x[0] & 0xFFFFFFFF
        if result:
            raise SystemExit(f"Pi3 HwLink assertion {result} after {steps:,} instructions")
        print(f"Pi3 Wi-Fi HwLink PASS: 17 assertions, {steps:,} A64 instructions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Emitted regression for the Pi 3 BCM2835 RNG WPA2 nonce adapter."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pi3_gate_build  # noqa: E402
import truetype_slots_check as slots  # noqa: E402
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "RaspberryPi3/Lib/wifi_rng.pi3"
GATE = ROOT / "RaspberryPi3/Tests/wifi_rng_gate.pi3"
LOAD, STACK, LIMIT = 0x00400000, 0x03000000, 500_000


def proc(raw: str, name: str) -> str:
    match = re.search(rf"(?ms)^Procedure(?:\.i)? {re.escape(name)}\(.*?^EndProcedure\s*$", raw)
    if not match:
        raise SystemExit(f"RNG procedure missing: {name}")
    return match.group(0)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--compiler", required=True, type=Path)
    args = ap.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    compiler = args.compiler.expanduser().resolve()
    if not compiler.is_file():
        raise SystemExit("compiler does not exist")
    raw = SOURCE.read_text(encoding="utf-8")
    fixture = GATE.read_text(encoding="utf-8")
    defs = "\n".join(line for line in raw.splitlines()
                      if line.startswith("#PI3_WIFI_RNG_"))
    defs += "\n" + "\n".join(line for line in raw.splitlines()
                               if line.startswith("Global pi3_wifi_rng_"))
    procs = "\n\n".join(proc(raw, name) for name in
                          ("Pi3WifiRngStart", "Pi3WifiRngBytes", "Pi3WifiRngError"))
    for marker, value in (("; @@RNG_DEFS@@", defs), ("; @@RNG_PROCS@@", procs)):
        if fixture.count(marker) != 1:
            raise SystemExit(f"RNG fixture marker missing/duplicated: {marker}")
        fixture = fixture.replace(marker, value, 1)

    with tempfile.TemporaryDirectory(prefix="anvil-pi3-rng-") as name:
        temp = Path(name)
        source, image = temp / "wifi_rng.pi3", temp / "wifi_rng.img"
        source.write_text(fixture, encoding="utf-8")
        env = os.environ.copy()
        env["PMF_ROOT"] = str(ROOT)

        def compile_fixture() -> None:
            result = subprocess.run(
                [str(compiler), "--compile", str(source), "-t", "pi3", "--entry-returns",
                 "--load-addr", hex(LOAD), "--stack-addr", hex(STACK), "-s", "-o", str(image)],
                cwd=ROOT, env=env, capture_output=True, text=True,
            )
            if result.returncode or "pmfc: OK" not in result.stdout or not image.is_file():
                raise SystemExit("Pi3 RNG fixture compile failed\n" + result.stdout + result.stderr)

        pi3_gate_build.compile_counted(
            compile_fixture, source, image, compiler=compiler,
            by="tools/pi3_wifi_rng_check.py", root=ROOT,
        )
        symbols = slots.base.parse_symbols(image)
        cpu = slots.base.load_interp(slots.base.INTERP).A64()
        raw_image = image.read_bytes()
        cpu.memory = {LOAD + i: value for i, value in enumerate(raw_image)}
        cpu.sp = STACK
        cpu.pc = LOAD + symbols["main"]
        cpu.x[30] = slots.base.RETURN_PC
        steps = 0
        while steps < LIMIT and cpu.pc != slots.base.RETURN_PC:
            cpu.step()
            steps += 1
        if cpu.pc != slots.base.RETURN_PC:
            raise SystemExit(f"Pi3 RNG gate exceeded {LIMIT:,} instructions")
        result = cpu.x[0] & 0xFFFFFFFF
        if result:
            raise SystemExit(f"Pi3 RNG gate assertion {result} after {steps:,} A64 instructions")
        print(f"Pi3 BCM2835 RNG adapter PASS: 9 assertions, {steps:,} A64 instructions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

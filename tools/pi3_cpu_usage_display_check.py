#!/usr/bin/env python3
"""Run the production Pi3 CPU usage draw procedure against a bounded cell model."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pi3_gate_build  # noqa: E402
import truetype_slots_check as slots  # noqa: E402
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "RaspberryPi3/Tests/cpu_usage_display_gate.pi3"
STUBS = ROOT / "RaspberryPi3/Board/pi3stubs.pi3"
LOAD, STACK, LIMIT = 0x00400000, 0x03000000, 2_000_000


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True, type=Path)
    args = parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    compiler = args.compiler.expanduser().resolve()
    if not compiler.is_file():
        raise SystemExit("compiler does not exist")
    stub = STUBS.read_text(encoding="utf-8")
    match = re.search(r"(?ms)^Procedure\s+Pi3ScreenUsageDraw\(.*?^EndProcedure\s*$", stub)
    if not match:
        raise SystemExit("production Pi3ScreenUsageDraw procedure not found")
    fixture = GATE.read_text(encoding="utf-8")
    marker = "; @@CPU_USAGE_DRAW@@"
    if fixture.count(marker) != 1:
        raise SystemExit("CPU draw fixture marker missing or duplicated")
    fixture = fixture.replace(marker, match.group(0), 1)
    with tempfile.TemporaryDirectory(prefix="pi3-cpu-display-") as name:
        temp = Path(name)
        source, image = temp / "cpu_usage_display.pi3", temp / "cpu_usage_display.img"
        source.write_text(fixture, encoding="utf-8")
        env = os.environ.copy()
        env["PMF_ROOT"] = str(ROOT)

        def do_compile() -> None:
            result = subprocess.run(
                [str(compiler), "--compile", str(source), "-t", "pi3", "--entry-returns",
                 "--load-addr", hex(LOAD), "--stack-addr", hex(STACK), "-s", "-o", str(image)],
                cwd=ROOT, env=env, capture_output=True, text=True,
            )
            if result.returncode or "pmfc: OK" not in result.stdout or not image.is_file():
                raise SystemExit("Pi3 CPU display fixture compile failed\n" + result.stdout + result.stderr)

        pi3_gate_build.compile_counted(
            do_compile, source, image, compiler=compiler,
            by="tools/pi3_cpu_usage_display_check.py", root=ROOT,
        )
        symbols = slots.base.parse_symbols(image)
        blob = image.read_bytes()
        cpu = slots.base.load_interp(slots.base.INTERP).A64()
        cpu.sp = STACK
        cpu.memory = {LOAD + i: byte for i, byte in enumerate(blob)}
        cpu.pc = LOAD + symbols["main"]
        cpu.x[30] = slots.base.RETURN_PC
        steps = 0
        while steps < LIMIT and cpu.pc != slots.base.RETURN_PC:
            cpu.step()
            steps += 1
        if cpu.pc != slots.base.RETURN_PC:
            raise SystemExit(f"Pi3 CPU display fixture exceeded {LIMIT} instructions")
        result = cpu.x[0] & 0xFFFFFFFF
        if result:
            def read32(name: str) -> int:
                at = LOAD + symbols[name]
                return sum(cpu.memory.get(at + i, 0) << (8 * i) for i in range(4))
            cells_at = LOAD + symbols["global_gatecell"]
            cells = [sum(cpu.memory.get(cells_at + i * 8 + j, 0) << (j * 8) for j in range(8)) for i in range(12)]
            counts = {name: read32(name) for name in ("global_gatefillcount", "global_gatedrawcount")}
            context = {name: read32(name) for name in ("global_pi3_screen_fault", "global_pi3_screen_cell_w", "global_pi3_screen_cell_h", "global_pi3_screen_scale")}
            raise SystemExit(f"Pi3 CPU display emitted assertion {result} after {steps:,} steps; {counts}; {context}; cells={cells}")
        print(f"Pi3 CPU display PASS: 8 assertions, {steps:,} A64 instructions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

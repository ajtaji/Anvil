#!/usr/bin/env python3
"""Emitted regression for the board-neutral CYW43 saved-network scan policy."""
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
GATE = ROOT / "RaspberryPi3/Tests/wifi_join_policy_gate.pi3"
SOURCE = ROOT / "Anvil/Net/wifi_join_policy.pbi"
LOAD, STACK, LIMIT = 0x00400000, 0x03000000, 2_000_000


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True, type=Path)
    args = parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    compiler = args.compiler.expanduser().resolve()
    if not compiler.is_file():
        raise SystemExit("compiler does not exist")

    raw = SOURCE.read_text(encoding="utf-8")
    match = re.search(r"(?ms)^Procedure\.i AnvilWifiJoinKnownScan\(.*?^EndProcedure\s*$", raw)
    if not match:
        raise SystemExit("shared scan policy procedure is missing")
    fixture = GATE.read_text(encoding="utf-8")
    include = 'XIncludeFile "Anvil/Net/wifi_join_policy.pbi"'
    if fixture.count(include) != 1:
        raise SystemExit("scan fixture include missing or duplicated")
    constants = "\n".join(line for line in raw.splitlines()
                            if line.startswith("#ANVIL_WIFI_SCAN_"))
    fixture = fixture.replace(include, constants + "\n" + match.group(0), 1)
    fixture = fixture.replace("; @@SCAN_CONSTANTS@@", "", 1)

    with tempfile.TemporaryDirectory(prefix="anvil-wifi-scan-") as name:
        temp = Path(name)
        source, image = temp / "wifi_scan.pi3", temp / "wifi_scan.img"
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
                raise SystemExit("shared scan fixture compile failed\n" + result.stdout + result.stderr)

        pi3_gate_build.compile_counted(
            do_compile, source, image, compiler=compiler,
            by="tools/wifi_join_policy_emitted_check.py", root=ROOT,
        )
        symbols = slots.base.parse_symbols(image)
        cpu = slots.base.load_interp(slots.base.INTERP).A64()
        cpu.sp = STACK
        raw_image = image.read_bytes()
        cpu.memory = {LOAD + i: byte for i, byte in enumerate(raw_image)}
        cpu.pc = LOAD + symbols["main"]
        cpu.x[30] = slots.base.RETURN_PC
        steps = 0
        while steps < LIMIT and cpu.pc != slots.base.RETURN_PC:
            try:
                cpu.step()
            except Exception as exc:
                raise SystemExit(
                    f"scan fixture fault at PC=${cpu.pc:08X}, x0..x8="
                    f"{[hex(v) for v in cpu.x[:9]]}: {exc}"
                ) from exc
            steps += 1
        if cpu.pc != slots.base.RETURN_PC:
            raise SystemExit(f"scan fixture exceeded {LIMIT:,} A64 instructions")
        result = cpu.x[0] & 0xFFFFFFFF
        if result:
            raise SystemExit(f"shared scan gate assertion {result} after {steps:,} instructions")
        print(f"shared CYW43 scan policy PASS: 11 assertions, {steps:,} A64 instructions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

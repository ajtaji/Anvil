#!/usr/bin/env python3
"""Emitted regression for the exact Pi3 implicit settings-load branches."""
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
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler

ROOT = Path(__file__).resolve().parents[1]
FONT = ROOT / "RaspberryPi3/Board/pi3stubs.pi3"
AUTO = ROOT / "RaspberryPi3/Board/board.pi3"
FIXTURE = ROOT / "RaspberryPi3/Tests/settings_load_reuse_gate.pi3"
LOAD, STACK, LIMIT = 0x00400000, 0x03000000, 100_000


def extract_condition(path: Path, variable: str, label: str) -> str:
    source = path.read_text(encoding="utf-8")
    import re

    pattern = (
        rf"If SettingsLoadState\(\)\s*=\s*1\s*\r?\n"
        rf"\s*{variable}\s*=\s*1\s*\r?\n"
        rf"\s*Else\s*\r?\n"
        rf"\s*{variable}\s*=\s*SettingsLoad\(\)\s*\r?\n"
        rf"\s*EndIf"
    )
    matches = list(re.finditer(pattern, source))
    if len(matches) != 1:
        raise SystemExit(f"{label}: expected one production condition, found {len(matches)}")
    return matches[0].group(0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True, type=Path)
    args = parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    compiler = args.compiler.expanduser().resolve()
    if not compiler.is_file():
        raise SystemExit("compiler does not exist")

    fixture = FIXTURE.read_text(encoding="utf-8")
    font_branch = extract_condition(FONT, "loadRc", "font boot")
    auto_branch = extract_condition(AUTO, "settingsRc", "autoconnect")
    if fixture.count("; @@FONT_SETTINGS_LOAD@@") != 1 or fixture.count("; @@AUTO_SETTINGS_LOAD@@") != 1:
        raise SystemExit("fixture extraction markers are not unique")
    fixture = fixture.replace("; @@FONT_SETTINGS_LOAD@@", font_branch)
    fixture = fixture.replace("; @@AUTO_SETTINGS_LOAD@@", auto_branch)

    with tempfile.TemporaryDirectory(prefix="anvil-pi3-settings-load-reuse-") as td:
        work = Path(td)
        source = work / "settings_load_reuse.pi3"
        image = work / "settings_load_reuse.img"
        source.write_text(fixture, encoding="utf-8", newline="\n")
        env = {**os.environ, "PMF_ROOT": str(ROOT)}

        def compile_fixture() -> None:
            result = subprocess.run(
                [str(compiler), "--compile", str(source), "-t", "pi3", "--entry-returns",
                 "--load-addr", hex(LOAD), "--stack-addr", hex(STACK), "-s", "-o", str(image)],
                cwd=ROOT, env=env, capture_output=True, text=True,
            )
            if result.returncode or "pmfc: OK" not in result.stdout or not image.is_file():
                raise SystemExit("settings-load reuse compile failed\n" + result.stdout + result.stderr)

        pi3_gate_build.compile_counted(
            compile_fixture, source, image, compiler=compiler,
            by="tools/pi3_settings_load_reuse_check.py", root=ROOT,
        )
        symbols = slots.base.parse_symbols(image)
        raw = image.read_bytes()
        cpu = slots.base.load_interp(slots.base.INTERP).A64()
        cpu.memory = {LOAD + i: value for i, value in enumerate(raw)}
        cpu.sp = STACK
        cpu.pc = LOAD + symbols["main"]
        cpu.x[30] = slots.base.RETURN_PC
        steps = 0
        while steps < LIMIT and cpu.pc != slots.base.RETURN_PC:
            cpu.step()
            steps += 1
        if cpu.pc != slots.base.RETURN_PC:
            raise SystemExit(f"settings-load reuse gate exceeded {LIMIT:,} A64 instructions")
        result = cpu.x[0] & 0xFFFFFFFF
        if result:
            raise SystemExit(f"settings-load reuse assertion {result} after {steps:,} A64 instructions")
        print(f"Pi3 implicit settings-load reuse PASS: 7 assertions, {steps:,} A64 instructions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

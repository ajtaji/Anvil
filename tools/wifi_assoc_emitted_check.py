#!/usr/bin/env python3
"""Emitted test for the shared bounded CYW43 association retry policy."""
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
GATE = ROOT / "RaspberryPi3/Tests/wifi_assoc_gate.pi3"
SOURCE = ROOT / "Anvil/Net/wifi_assoc.pbi"
LOAD, STACK, LIMIT = 0x00400000, 0x03000000, 2_000_000


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True, type=Path)
    args = parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    compiler = args.compiler.expanduser().resolve()
    if not compiler.is_file():
        raise SystemExit("compiler does not exist")
    raw = SOURCE.read_text(encoding="utf-8")
    match = re.search(
        r"(?ms)^Procedure\.i AnvilWifiAssociateCandidate\(.*?^EndProcedure\s*$", raw
    )
    if not match:
        raise SystemExit("shared association procedure is missing")
    fixture = GATE.read_text(encoding="utf-8")
    marker = "; @@SHARED_ASSOC@@"
    if fixture.count(marker) != 1:
        raise SystemExit("association gate marker missing or duplicated")
    fixture = fixture.replace(marker, match.group(0), 1)
    constants = "\n".join(line for line in raw.splitlines()
                            if line.startswith("#ANVIL_WIFI_ASSOC_EVENT_"))
    constant_marker = "; @@ASSOC_CONSTANTS@@"
    if fixture.count(constant_marker) != 1:
        raise SystemExit("association constants marker missing or duplicated")
    fixture = fixture.replace(constant_marker, constants, 1)
    with tempfile.TemporaryDirectory(prefix="anvil-wifi-assoc-") as name:
        temp = Path(name)
        source, image = temp / "wifi_assoc.pi3", temp / "wifi_assoc.img"
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
                raise SystemExit("shared association fixture compile failed\n" + result.stdout + result.stderr)

        pi3_gate_build.compile_counted(
            do_compile, source, image, compiler=compiler,
            by="tools/wifi_assoc_emitted_check.py", root=ROOT,
        )
        symbols = slots.base.parse_symbols(image)
        cpu = slots.base.load_interp(slots.base.INTERP).A64()
        cpu.sp = STACK
        cpu.memory = {LOAD + i: byte for i, byte in enumerate(image.read_bytes())}
        cpu.pc = LOAD + symbols["main"]
        cpu.x[30] = slots.base.RETURN_PC
        steps = 0
        while steps < LIMIT and cpu.pc != slots.base.RETURN_PC:
            try:
                cpu.step()
            except Exception as exc:
                nearest = sorted((abs((LOAD + off) - cpu.pc), name, off)
                                 for name, off in symbols.items() if off <= len(image.read_bytes()))[:8]
                words = [sum(cpu.memory.get(cpu.pc - 12 + k * 4 + j, 0) << (8 * j) for j in range(4)) for k in range(8)]
                raise SystemExit(f"association fixture fault at PC=${cpu.pc:08X}, x0..x10={[hex(v) for v in cpu.x[:11]]}, words={[hex(v) for v in words]}, nearest={nearest}: {exc}") from exc
            steps += 1
        if cpu.pc != slots.base.RETURN_PC:
            raise SystemExit(f"shared association gate exceeded {LIMIT} instructions")
        result = cpu.x[0] & 0xFFFFFFFF
        if result:
            names = ["gate_starts", "gate_polls", "gate_handshakes", "gate_progress", "gate_events", "gate_disassoc", "gate_drains", "gate_event"]
            state = {}
            for name in names:
                off = symbols.get(name)
                if off is not None:
                    width = 64 if name != "gate_event" else 32
                    state[name] = sum(cpu.memory.get(LOAD + off + j, 0) << (8 * j) for j in range(width // 8))
            raise SystemExit(f"shared association gate assertion {result} after {steps:,} steps; globals={state}")
        print(f"shared CYW43 association PASS: 14 assertions, {steps:,} A64 instructions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

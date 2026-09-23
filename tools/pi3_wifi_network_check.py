#!/usr/bin/env python3
"""Mocked emitted orchestration gate for the Pi 3 WPA2 adapter.

The test compiles the exact Pi 3 adapter with actual shared association and
scan policy procedures. Hardware, settings, PMK primitive and WPA2 packet
cryptography are stubbed, so this proves call order/ownership only, not radio
association or cryptographic correctness.
"""
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
GATE = ROOT / "RaspberryPi3/Tests/wifi_network_gate.pi3"
LOAD, STACK, LIMIT = 0x00400000, 0x03000000, 1_000_000


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--compiler", required=True, type=Path)
    args = ap.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    compiler = args.compiler.expanduser().resolve()
    if not compiler.is_file():
        raise SystemExit("compiler does not exist")
    fixture = GATE.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="anvil-pi3-wifi-network-") as name:
        temp = Path(name)
        source, image = temp / "wifi_network.pi3", temp / "wifi_network.img"
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
                raise SystemExit("Pi3 Wi-Fi adapter fixture compile failed\n" + result.stdout + result.stderr)

        pi3_gate_build.compile_counted(
            compile_fixture, source, image, compiler=compiler,
            by="tools/pi3_wifi_network_check.py", root=ROOT,
        )
        symbols = slots.base.parse_symbols(image)
        raw_image = image.read_bytes()
        cpu = slots.base.load_interp(slots.base.INTERP).A64()
        cpu.memory = {LOAD + i: value for i, value in enumerate(raw_image)}
        cpu.sp = STACK
        cpu.pc = LOAD + symbols["main"]
        cpu.x[30] = slots.base.RETURN_PC
        steps = 0
        while steps < LIMIT and cpu.pc != slots.base.RETURN_PC:
            try:
                cpu.step()
            except Exception as exc:
                raise SystemExit(
                    f"Pi3 Wi-Fi fixture fault at PC=${cpu.pc:08X}, "
                    f"x0..x9={[hex(v) for v in cpu.x[:10]]}: {exc}"
                ) from exc
            steps += 1
        if cpu.pc != slots.base.RETURN_PC:
            raise SystemExit(f"Pi3 Wi-Fi adapter fixture exceeded {LIMIT:,} A64 instructions")
        result = cpu.x[0] & 0xFFFFFFFF
        if result:
            raise SystemExit(f"Pi3 Wi-Fi adapter assertion {result} after {steps:,} instructions")
        print(f"Pi3 WPA2/rekey/DHCP seam PASS (mocked radio/crypto/IP transport): 32 assertions, {steps:,} A64 instructions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

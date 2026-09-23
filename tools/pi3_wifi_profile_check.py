#!/usr/bin/env python3
"""Compile and execute the Pi 3 board/radio profile selectors."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import pi3_gate_build

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "RaspberryPi3" / "Tests" / "wifi_profile_gate.pi3"
INTERP = ROOT / "tools" / "a64" / "a64_interp.py"
LOAD = 0x400000
STACK = 0x3000000
RETURN = 0x7000000


def load_interpreter():
    spec = importlib.util.spec_from_file_location("pi3_wifi_profile_a64", INTERP)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load A64 interpreter")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def compile_fixture(compiler: Path, temp: Path) -> tuple[bytes, dict[str, int]]:
    image = temp / "wifi_profile_gate.img"
    command = [str(compiler), "--compile", str(GATE), "-t", "pi3",
               "--entry-returns", "--load-addr", hex(LOAD), "--stack-addr",
               hex(STACK), "-s", "-o", str(image)]

    def run_compile() -> None:
        result = subprocess.run(command, cwd=ROOT,
                                env=dict(os.environ, PMF_ROOT=str(ROOT)),
                                capture_output=True, text=True)
        if result.returncode or not image.is_file():
            raise SystemExit("Pi 3 Wi-Fi profile gate compile failed\n" +
                             result.stdout + result.stderr)

    pi3_gate_build.compile_counted(run_compile, GATE, image,
                                   compiler=compiler, by="pi3_wifi_profile_check",
                                   root=ROOT)
    symbols: dict[str, int] = {}
    for line in Path(str(image) + ".sym").read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        try:
            symbols[name.lower()] = int(value, 0)
        except ValueError:
            pass
    return image.read_bytes(), symbols


def execute(a64, image: bytes, symbols: dict[str, int]) -> tuple[int, int]:
    if "main" not in symbols:
        raise AssertionError("compiler omitted fixture Main")
    cpu = a64.A64()
    for offset, byte in enumerate(image):
        cpu.memory[LOAD + offset] = byte
    for address in range(symbols.get("__bss_start__", 0),
                         symbols.get("__bss_end__", 0)):
        cpu.memory[address] = 0
    cpu.pc = LOAD + symbols["main"]
    cpu.sp = STACK
    cpu.x[30] = RETURN
    for steps in range(1, 100000):
        if cpu.pc == RETURN:
            return cpu.x[0], steps
        cpu.step()
    raise AssertionError("Pi 3 Wi-Fi profile gate exceeded 100,000 instructions")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, required=True)
    args = parser.parse_args()
    compiler = args.compiler.resolve()
    if not compiler.is_file():
        raise SystemExit(f"compiler not found: {compiler}")
    a64 = load_interpreter()
    with tempfile.TemporaryDirectory(prefix="pi3-wifi-profile-") as name:
        image, symbols = compile_fixture(compiler, Path(name))
        result, steps = execute(a64, image, symbols)
    if result != 0:
        raise SystemExit(f"emitted Pi 3 Wi-Fi profile assertion {result} failed")
    source = (ROOT / "RaspberryPi3" / "Lib" / "wifi_profile.pi3").read_text(encoding="utf-8")
    expected_stems = ("brcmfmac43430a0-sdio", "brcmfmac43430-sdio",
                      "brcmfmac43430b0-sdio", "brcmfmac43455-sdio",
                      "brcmfmac43456-sdio")
    if any(stem not in source for stem in expected_stems):
        raise SystemExit("firmware stem table is incomplete")
    print(f"PASS: 30 emitted profile/reset assertions; {steps:,} A64 instructions")
    print("PASS: unsupported board/chip/revision pairings fail closed; exact Linux firmware stems present")
    print("Compiler SHA-256:", hashlib.sha256(compiler.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Emit and execute the production CYW43 CM3/SOCSRAM RAM geometry routine."""
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
SOURCE = ROOT / "Anvil" / "Net" / "cyw43.pbi"
FIXTURE = ROOT / "RaspberryPi3" / "Tests" / "cyw43_cm3_socram_gate.pi3"
INTERP = ROOT / "tools" / "a64" / "a64_interp.py"
MARKERS = {
    "Cyw43ReadRamInfo": "; @@PRODUCTION_CYW43_READRAMINFO@@",
    "Cyw43PrepareDownload": "; @@PRODUCTION_CYW43_PREPAREDOWNLOAD@@",
    "Cyw43Start": "; @@PRODUCTION_CYW43_START@@",
}
LOAD = 0x400000
STACK = 0x3000000
RETURN = 0x7000000


def load_interpreter():
    spec = importlib.util.spec_from_file_location("pi3_cyw43_cm3_a64", INTERP)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load A64 interpreter")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def production_proc(text: str, name: str) -> str:
    marker = f"Procedure.i {name}()"
    start = text.find(marker)
    if start < 0:
        raise SystemExit(f"production {name} procedure not found")
    end = text.find("\nEndProcedure", start)
    if end < 0:
        raise SystemExit(f"production {name} has no EndProcedure")
    return text[start:end + len("\nEndProcedure")]


def compile_gate(compiler: Path, temp: Path):
    source = SOURCE.read_text(encoding="utf-8")
    fixture = FIXTURE.read_text(encoding="utf-8")
    for name, marker in MARKERS.items():
        if fixture.count(marker) != 1:
            raise SystemExit(f"CM3 fixture {name} production marker drifted")
        fixture = fixture.replace(marker, production_proc(source, name), 1)
    generated = temp / "cyw43_cm3_socram_gate.pi3"
    generated.write_text(fixture, encoding="utf-8", newline="\n")
    image = temp / "cyw43_cm3_socram_gate.img"
    command = [str(compiler), "--compile", str(generated), "-t", "pi3",
               "--entry-returns", "--load-addr", hex(LOAD), "--stack-addr",
               hex(STACK), "-s", "-o", str(image)]

    def run_compile():
        result = subprocess.run(command, cwd=ROOT,
                                env=dict(os.environ, PMF_ROOT=str(ROOT)),
                                capture_output=True, text=True)
        if result.returncode or "pmfc: OK" not in (result.stdout + result.stderr):
            raise SystemExit("CM3/SOCSRAM fixture compile failed\n" +
                             result.stdout + result.stderr)

    pi3_gate_build.compile_counted(run_compile, generated, image,
                                   compiler=compiler,
                                   by="pi3_cyw43_cm3_socram_check", root=ROOT)
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


def execute(a64, blob: bytes, symbols: dict[str, int]) -> tuple[int, int]:
    if "main" not in symbols:
        raise AssertionError("compiler omitted fixture Main")
    cpu = a64.A64()
    for offset, byte in enumerate(blob):
        cpu.memory[LOAD + offset] = byte
    for address in range(symbols.get("__bss_start__", 0),
                         symbols.get("__bss_end__", 0)):
        cpu.memory[address] = 0
    cpu.pc = LOAD + symbols["main"]
    cpu.sp = STACK
    cpu.x[30] = RETURN
    for steps in range(1, 100_000):
        if cpu.pc == RETURN:
            return cpu.x[0], steps
        cpu.step()
    raise AssertionError("CM3/SOCSRAM gate exceeded 100,000 instructions")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, required=True)
    args = parser.parse_args()
    compiler = args.compiler.resolve()
    if not compiler.is_file():
        raise SystemExit(f"compiler not found: {compiler}")
    a64 = load_interpreter()
    with tempfile.TemporaryDirectory(prefix="pi3-cyw43-cm3-") as name:
        blob, symbols = compile_gate(compiler, Path(name))
        result, steps = execute(a64, blob, symbols)
    if result:
        raise SystemExit(f"CM3/SOCSRAM assertion {result} failed")
    print("PASS: exact production ReadRamInfo/PrepareDownload/Start bodies; SOCSRAM geometry, CM3 passive/active ordering, vector-zero release, and fail-closed bounds")
    print(f"PASS: emitted A64 executed in {steps:,} instructions; compiler SHA-256 {hashlib.sha256(compiler.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

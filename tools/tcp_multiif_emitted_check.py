#!/usr/bin/env python3
"""Compile and execute the production multi-interface TCP ownership gate.

Requires external tools; neither is copied into the product tree:
  PMF_COMPILER=<path-to-PureMetalForge.exe> PMF_A64_INTERP=<path-to-a64_interp.py> \
      python tools/tcp_multiif_emitted_check.py
"""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from pmf_compiler import resolve_compiler


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "RaspberryPi4" / "Tests" / "tcp_multiif_emitted_gate.pi4"
LOAD = 0x00400000
STACK = 0x03000000
STACK_BYTES = 0x00100000
LOADER_LR = 0xDEAD0000
STEP_LIMIT = 8_000_000


def required_path(value: str | None, env_name: str) -> Path:
    if not value:
        raise SystemExit(f"tcp multi-if gate: set {env_name} or pass its option")
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"tcp multi-if gate: {env_name} file not found: {path}")
    return path


def load_interpreter(path: Path):
    spec = importlib.util.spec_from_file_location("anvil_tcp_multiif_a64_interp", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"tcp multi-if gate: cannot load interpreter: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def symbol_bounds(sym_path: Path) -> tuple[int, int]:
    values: dict[str, int] = {}
    for line in sym_path.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        name, raw = line.split("=", 1)
        if name in ("__bss_start__", "__bss_end__"):
            values[name] = int(raw, 0)
    try:
        return values["__bss_start__"], values["__bss_end__"]
    except KeyError as exc:
        raise SystemExit("tcp multi-if gate: compiler symbol map has no BSS bounds") from exc


def build(compiler: Path, work: Path, mutation: str = "") -> Path:
    staged = work / compiler.name
    shutil.copy2(compiler, staged)
    boards = ROOT / "Boards"
    if boards.is_dir():
        shutil.copytree(boards, work / "Boards")
    image = work / "tcp_multiif_gate.img"
    probe = PROBE
    if mutation:
        # Restore the actual defective production admission predicate in an
        # isolated generated include. All other protocol code remains real.
        receiver = (ROOT / "Anvil/Core/netrecv.pbi").read_text(encoding="utf-8")
        if mutation == "old_wait":
            fixed = "If st = #TCP_ESTABLISHED Or st = #TCP_CLOSE_WAIT"
            broken = "If st = #TCP_ESTABLISHED"
        elif mutation == "no_close":
            fixed = "        TcpClose()"
            broken = "        ; TcpClose removed by mutation"
        elif mutation == "last_ack_only":
            fixed = "orderly = Bool(gNrState = #NR_DONE And TcpState() = #TCP_LAST_ACK)"
            broken = "orderly = Bool(TcpState() = #TCP_LAST_ACK)"
        else:
            raise SystemExit(f"tcp multi-if mutation: unknown mutation {mutation}")
        if receiver.count(fixed) != 1:
            raise SystemExit(f"tcp multi-if mutation: {mutation} site drifted")
        mutated = work / "netrecv_old_wait.pbi"
        mutated.write_text(receiver.replace(fixed, broken, 1), encoding="utf-8")
        source = PROBE.read_text(encoding="utf-8")
        include = 'XIncludeFile "Anvil/Core/netrecv.pbi"'
        if source.count(include) != 1:
            raise SystemExit("tcp multi-if mutation: receiver include drifted")
        probe = work / "tcp_multiif_old_wait.pi4"
        probe.write_text(source.replace(include, f'XIncludeFile "{mutated.as_posix()}"'), encoding="utf-8")
    command = [
        str(staged), "--compile",
        str(probe),
        "-t", "pi4",
        "--load-addr", hex(LOAD),
        "--stack-addr", hex(STACK),
        "--entry-returns",
        "-o", str(image),
        "-s",
    ]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    run = subprocess.run(
        command, cwd=ROOT, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise SystemExit("tcp multi-if gate: compile failed\n" + run.stdout)
    if not image.is_file() or not image.with_suffix(image.suffix + ".sym").is_file():
        raise SystemExit("tcp multi-if gate: compiler omitted image or symbol map")
    return image


def execute(a64, image: Path) -> tuple[int, int]:
    blob = image.read_bytes()
    bss_lo, bss_hi = symbol_bounds(image.with_suffix(image.suffix + ".sym"))
    image_range = (LOAD, LOAD + len(blob))
    bss_range = (bss_lo, bss_hi)
    stack_range = (STACK - STACK_BYTES, STACK + 16)
    readable = (image_range, bss_range, stack_range)
    writable = (bss_range, stack_range)

    def contains(ranges: tuple[tuple[int, int], ...], addr: int, size: int) -> bool:
        return size > 0 and any(lo <= addr and addr + size <= hi for lo, hi in ranges)

    cpu = a64.A64()
    for offset, byte in enumerate(blob):
        cpu.memory[LOAD + offset] = byte
    a64.attach_symbols(cpu, image, LOAD)
    cpu.pc = LOAD
    cpu.sp = STACK
    cpu.x[30] = LOADER_LR

    def load(addr: int, size: int) -> int:
        cpu.align_guard(addr, size, False)
        if not contains(readable, addr, size):
            raise SystemExit(
                f"tcp multi-if gate: read outside image/BSS/stack at ${addr:08X}+{size}"
            )
        return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr: int, value: int, size: int) -> None:
        cpu.align_guard(addr, size, True)
        if not contains(writable, addr, size):
            raise SystemExit(
                f"tcp multi-if gate: write outside BSS/stack at ${addr:08X}+{size}"
            )
        for i in range(size):
            cpu.memory[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    for steps in range(STEP_LIMIT):
        if cpu.pc == LOADER_LR:
            return cpu.x[0], steps
        cpu.step()
    raise SystemExit(f"tcp multi-if gate: no return in {STEP_LIMIT} instructions")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"))
    args = parser.parse_args()
    compiler = Path(resolve_compiler(args.compiler))
    interp = required_path(args.interp, "PMF_A64_INTERP")
    a64 = load_interpreter(interp)
    with tempfile.TemporaryDirectory(prefix="anvil-tcp-multiif-emitted-") as temporary:
        image = build(compiler, Path(temporary))
        result, steps = execute(a64, image)
    if result:
        print(f"tcp_multiif_emitted_check: FAIL assertion {result} after {steps:,} A64 instructions")
        return 1
    with tempfile.TemporaryDirectory(prefix="anvil-tcp-old-wait-") as temporary:
        mutant = build(compiler, Path(temporary), mutation="old_wait")
        mutation_result, mutation_steps = execute(a64, mutant)
    if mutation_result != 109:
        print(f"tcp_multiif_emitted_check: FAIL old-wait mutation returned {mutation_result}; expected assertion 109")
        return 1
    for mutation, expected in (("no_close", 115), ("last_ack_only", 162)):
        with tempfile.TemporaryDirectory(prefix=f"anvil-tcp-{mutation}-") as temporary:
            mutant = build(compiler, Path(temporary), mutation=mutation)
            mutation_result, mutation_steps = execute(a64, mutant)
        if mutation_result != expected:
            print(f"tcp_multiif_emitted_check: FAIL {mutation} mutation returned {mutation_result}; expected assertion {expected}")
            return 1
    print(f"tcp_multiif_emitted_check: PASS - 27 endpoint assertions, 16 receiver scenarios, {steps:,} A64 instructions")
    print(f"  orderly ACK and lost-ACK success, overflow/stop/idle abort, peer-RST silence, no-peer and revoked-listener on both links; 3 mutations rejected")
    return 0


if __name__ == "__main__":
    sys.exit(main())

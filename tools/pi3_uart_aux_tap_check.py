#!/usr/bin/env python3
"""Emit and run the Pi3 UART auxiliary-output tap against fake hardware."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pi3_gate_build  # noqa: E402
import truetype_slots_check as slots  # noqa: E402

CONSOLE = ROOT / "RaspberryPi3/Lib/pl011_console.pi3"
GATE = ROOT / "RaspberryPi3/Tests/uart_aux_tap_gate.pi3"
LOAD, STACK, LIMIT = 0x00400000, 0x03000000, 2_000_000
PROCEDURES = (
    "UartAuxMirror",
    "UartAuxSetFlush",
    "UartAuxBulk",
    "UartAuxFillHigh",
    "UartAuxOn",
    "UartAuxGet",
    "UartAuxLost",
    "uart_AuxPut",
    "UartWrite",
)
RX_PROCEDURES = (
    "UartReadReady",
    "UartRead",
    "UartReadWait",
    "UartAdmitPending",
    "UartDeferredRxLost",
)


def production_body(source: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^Procedure(?:\.\w+)?\s+{re.escape(name)}\s*\(.*?^EndProcedure\s*$",
        source,
    )
    if match is None:
        raise SystemExit(f"missing production procedure: {name}")
    return match.group(0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True, type=Path)
    args = parser.parse_args()
    compiler = args.compiler.expanduser().resolve()
    if not compiler.is_file():
        raise SystemExit("compiler does not exist")

    source = CONSOLE.read_text(encoding="utf-8")
    fixture = GATE.read_text(encoding="utf-8")
    marker = "; @@UART_AUX_PRODUCTION@@"
    if fixture.count(marker) != 1:
        raise SystemExit("UART aux gate marker missing or duplicated")
    bodies = "\n\n".join(production_body(source, name) for name in PROCEDURES)
    fixture = fixture.replace(marker, bodies, 1)
    rx_marker = "; @@UART_RX_PRODUCTION@@"
    rx_bodies = "\n\n".join(production_body(source, name) for name in RX_PROCEDURES)
    if fixture.count(rx_marker) != 1:
        raise SystemExit("UART deferred RX gate marker missing or duplicated")
    fixture = fixture.replace(rx_marker, rx_bodies, 1)
    admit = production_body(source, "UartAdmitPending")
    if any(token in admit for token in ("InputFeedByte", "ReadLine", "CmdPi3Wifi", "CommandDispatch")):
        raise SystemExit("UART admission must not re-enter editor/parser dispatch")

    with tempfile.TemporaryDirectory(prefix="pi3-uart-aux-") as temp_name:
        temp = Path(temp_name)
        source_path = temp / "uart_aux_tap.pi3"
        image_path = temp / "uart_aux_tap.img"
        source_path.write_text(fixture, encoding="utf-8")
        env = os.environ.copy()
        env["PMF_ROOT"] = str(ROOT)

        def do_compile() -> None:
            result = subprocess.run(
                [str(compiler), "--compile", str(source_path), "-t", "pi3", "--entry-returns",
                 "--load-addr", hex(LOAD), "--stack-addr", hex(STACK), "-s", "-o", str(image_path)],
                cwd=ROOT, env=env, capture_output=True, text=True,
            )
            if result.returncode or "pmfc: OK" not in result.stdout or not image_path.is_file():
                raise SystemExit("Pi3 UART aux emitted gate compile failed\n" + result.stdout + result.stderr)

        pi3_gate_build.compile_counted(
            do_compile, source_path, image_path, compiler=compiler,
            by="tools/pi3_uart_aux_tap_check.py", root=ROOT,
        )
        symbols = slots.base.parse_symbols(image_path)
        cpu = slots.base.load_interp(slots.base.INTERP).A64()
        cpu.sp = STACK
        blob = image_path.read_bytes()
        cpu.memory = {LOAD + i: byte for i, byte in enumerate(blob)}
        index_at = LOAD + symbols["global_gate_rx_index"]
        count_at = LOAD + symbols["global_gate_rx_count"]
        def read_mem(addr: int, size: int) -> int:
            if addr == 0x3F201018 and size == 4:
                index = sum(cpu.memory.get(index_at + i, 0) << (8 * i) for i in range(4))
                count = sum(cpu.memory.get(count_at + i, 0) << (8 * i) for i in range(4))
                return 0x10 if index >= count else 0
            cpu.align_guard(addr, size, False)
            return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(size))
        def write_mem(addr: int, value: int, size: int) -> None:
            cpu.align_guard(addr, size, True)
            for i in range(size):
                cpu.memory[addr + i] = (value >> (8 * i)) & 0xFF
        cpu.load = read_mem
        cpu.store = write_mem
        cpu.pc = LOAD + symbols["main"]
        cpu.x[30] = slots.base.RETURN_PC
        steps = 0
        while steps < LIMIT and cpu.pc != slots.base.RETURN_PC:
            cpu.step()
            steps += 1
        if cpu.pc != slots.base.RETURN_PC:
            raise SystemExit(f"Pi3 UART aux emitted gate exceeded {LIMIT:,} instructions")
        result = cpu.x[0] & 0xFFFFFFFF
        if result:
            def read32(name: str) -> int:
                at = LOAD + symbols["global_" + name]
                return sum(cpu.memory.get(at + i, 0) << (8 * i) for i in range(4))
            state = {name: read32(name) for name in (
                "gate_uart_accept", "gate_uart_count", "gate_screen_count",
                "gate_screen_last", "gate_flush_count", "p3c_dropped",
                "uart_auxhead", "uart_auxtail", "uart_auxlost",
                "gate_rx_count", "gate_rx_index", "gate_rx_reads",
                "p3c_deferredrxhead", "p3c_deferredrxtail",
            )}
            raise SystemExit(f"Pi3 UART aux emitted assertion {result} after {steps:,} instructions; {state}")
        print(f"Pi3 UART aux tap + deferred RX PASS: 30 assertions, {steps:,} A64 instructions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

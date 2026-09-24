#!/usr/bin/env python3
"""Stress installed build 145 UART while its display service is active."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import tempfile
import zlib

from pmf_compiler import TRACKED_COMPILER, resolve_compiler
from rockpi4c_mali_job_proof import compile_for_stage
from rockpi4c_update import Recovery, STAGE_LIMIT


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "RockPi4C/Tests/build145_live_uart_screen_proof.rockpi4c"
FONT_SOURCE = ROOT / "RockPi4C/Tests/build145_live_uart_font_pump_proof.rockpi4c"
CHUNK_SOURCE = ROOT / "RockPi4C/Tests/build146_live_uart_status_chunk_proof.rockpi4c"
BOARD = ROOT / "RockPi4C/Board/board.rockpi4c"
SYMBOLS = ROOT / "build/rockpi4c/anvil-flat.img.sym"
TEXT_BASE = 0x41000
EXPECTED = {
    "rockrecoverypoll": 0x000DED08,
    "rockscreenservice": 0x000DA35C,
    "rockuartbyte": 0x00042260,
    "rockscreenfontglyph": 0x000D5898,
    "rockuartpump": 0x00041EDC,
    "rockscreencpufill32": 0x000D46FC,
    "rockwatchdogpet": 0x000A2738,
    "global_rock_recovery_length": 68778224,
    "global_rock_recovery_discard": 69023640,
    "global_rock_recovery_error": 45323880,
    "global_rock_uart_error": 68398472,
    "global_rock_uart_rx_max_outside_ticks": 44490344,
    "global_rock_uart_rx_last_pump_end": 62789832,
    "global_rock_uart_rx_context": 68365008,
    "global_rock_uart_rx_max_context": 68774080,
    "global_rock_screen_head": 68398456,
    "global_rock_screen_tail": 44835864,
    "global_rock_screen_scroll_active": 44125072,
    "global_rock_screen_row_buffer_dirty": 64099144,
    "global_rock_screen_cpu_dirty": 45324544,
    "global_rock_screen_cpu_hundredths": 44490352,
    "global_rock_screen_fault": 62388040,
    "global_rock_font_ready": 43793656,
}


def check_build_identity(build_number: int = 145) -> None:
    if f"#ANVIL_BUILD = {build_number}" not in BOARD.read_text(encoding="utf-8"):
        raise RuntimeError(f"payload is bound to build {build_number}")
    expected = dict(EXPECTED)
    if build_number == 146:
        expected["rockrecoverypoll"] += 56
        expected["rockscreenservice"] += 56
    elif build_number == 147:
        expected["rockrecoverypoll"] += 364
        expected["rockscreenservice"] += 364
        expected["rockscreenfontglyph"] += 280
    elif build_number != 145:
        raise RuntimeError("only installed builds 145-147 are mapped")
    symbols: dict[str, int] = {}
    for line in SYMBOLS.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            name, value = line.split("=", 1)
            if name in expected:
                symbols[name] = int(value, 10) + (TEXT_BASE if not name.startswith("global_") else 0)
    if symbols != expected:
        raise RuntimeError(f"resident symbol mismatch: {symbols!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=1500000)
    parser.add_argument("--installed-build", type=int, default=145, choices=(145, 146, 147))
    parser.add_argument("--compiler", default=str(TRACKED_COMPILER))
    parser.add_argument("--skip-cpu-status", action="store_true",
                        help="differential proof: leave the CPU status publication idle")
    parser.add_argument("--font-pump", action="store_true",
                        help="proof resident TrueType glyph work with UART pumps on a private strip")
    parser.add_argument("--skip-fill-pump", action="store_true",
                        help="differential proof: 20 status clear rows without UART pumps")
    parser.add_argument("--chunk-fill", action="store_true",
                        help="private status clear with a UART pump per 128 bytes")
    options = parser.parse_args()
    check_build_identity(options.installed_build)
    recovery = Recovery(options.port, options.baud)
    try:
        # The command deliberately leaves a console row/status job pending.
        recovery.send_command("help")
        recovery.wait_line(lambda line: line.startswith(b"COMMANDS:"), 3.0)
        stage, capacity = recovery.stage_map()
        if capacity != STAGE_LIMIT:
            raise RuntimeError("unexpected stage capacity")
        with tempfile.TemporaryDirectory(prefix="rockpi4c-live-rx-") as folder:
            source = CHUNK_SOURCE if options.chunk_fill else FONT_SOURCE if options.font_pump else SOURCE
            if options.installed_build in (146, 147):
                updated = Path(folder) / f"build{options.installed_build}_live_uart_screen_proof.rockpi4c"
                original = source.read_text(encoding="utf-8")
                shift = 56 if options.installed_build == 146 else 364
                replacements = {
                    "#LIVE_POLL = $000DED08": f"#LIVE_POLL = ${0xDED08 + shift:08X}",
                    "#LIVE_SCREEN = $000DA35C": f"#LIVE_SCREEN = ${0xDA35C + shift:08X}",
                }
                for before, after in replacements.items():
                    if original.count(before) != 1:
                        raise RuntimeError(f"resident address marker changed: {before}")
                    original = original.replace(before, after)
                updated.write_text(original, encoding="utf-8")
                source = updated
            if options.skip_fill_pump:
                if not options.font_pump:
                    raise RuntimeError("fill differential requires --font-pump")
                updated = Path(folder) / "build_live_uart_no_fill_pump.rockpi4c"
                original = source.read_text(encoding="utf-8")
                needle = "LivePump() ; private status clear row pump"
                if original.count(needle) != 1:
                    raise RuntimeError("status-clear pump marker changed")
                updated.write_text(original.replace(needle, "; deliberately omit fill row pump"),
                                   encoding="utf-8")
                source = updated
            if options.skip_cpu_status:
                original = source.read_text(encoding="utf-8")
                source = Path(folder) / f"build{options.installed_build}_live_uart_no_cpu_status.rockpi4c"
                needle = "PokeI(#LIVE_CPU_DIRTY, 1)"
                if original.count(needle) != 1:
                    raise RuntimeError("CPU status probe marker changed")
                source.write_text(original.replace(needle, "; CPU status disabled for differential probe"),
                                  encoding="utf-8")
            image = compile_for_stage(resolve_compiler(options.compiler), stage,
                                      Path(folder) / "live-rx.bin", source)
            if recovery.stage_map() != (stage, capacity):
                raise RuntimeError("payload stage changed after linking")
            checksum = zlib.crc32(image) & 0xFFFFFFFF
            recovery.send_command(f"payload {len(image):X} {checksum:08X}")
            recovery.transfer_in(image, len(image), checksum)
            recovery.wait_line(lambda line: line == b"RXREADY", 10.0)
            payload = b"x" * 400
            if recovery.port.write(payload) != len(payload):
                raise RuntimeError("short UART stress write")
            recovery.port.flush()
            line = recovery.wait_line(lambda item: item.startswith(b"PAYLOAD RETURN X0="), 12.0)
            match = re.match(rb"PAYLOAD RETURN X0=([0-9A-F]{16})", line)
            if match is None:
                raise RuntimeError(f"malformed payload return: {line!r}")
            if match.end() != len(line):
                print(f"serial noise after payload return: {line[match.end():]!r}")
            result = int(match.group(1), 16)
            if result >> 32 == 0x4C524552:
                gap = (result >> 16) & 0xFFFF
                count_low = (result >> 8) & 0xFF
                code = result & 0xFF
                raise RuntimeError(f"live UART proof check {code} failed: count_low={count_low}, "
                                   f"max outside-pump gap={gap / 24:.2f} us")
            if result >> 48 != 0x4C52:
                raise RuntimeError(f"unexpected proof return 0x{result:016X}")
            gap = (result >> 32) & 0xFFFF
            count = (result >> 16) & 0xFFFF
            cpu = result & 0xFFFF
            if count != 400 or gap >= 10240 or cpu > 10000:
                raise RuntimeError(f"invalid proof result: count={count} gap={gap / 24:.2f} us "
                                   f"CPU0={cpu / 100:.2f}%")
            print(f"build {options.installed_build} live UART read {count}/400 bytes; no UART error/discard; "
                  f"max outside-pump gap {gap / 24:.2f} us; "
                  f"sampled CPU0 {cpu / 100:.2f}%")
    finally:
        recovery.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

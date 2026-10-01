#!/usr/bin/env python3
"""Build and check staged Pi 4 Vulkan draw-list scale RAM diagnostics.

This tool never contacts a board. Build 64 first; run and check its report
before admitting the 256 image, then repeat before admitting 1024. Each image
contains that many actual vkCmdDraw commands in one render pass and submit.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile

from pmf_compiler import TRACKED_COMPILER, resolve_compiler


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "RaspberryPi4/Examples/Diagnostics/vulkanDrawListScaleProof.pi4"
OUTPUT = ROOT / "tmp/pi4-drawscale"
COUNTS = (64, 256, 1024)
LOAD = 0x00700000
STACK = 0x04F00000
SURFACE = 0x06000000
SURFACE_BYTES = 4096000
WINDOW = 0x063E8000
WINDOW_BYTES = 8388608
DSI_SCAN = 0x08A00000
ARENA = 0x0A000000
MAGIC = 0x564B4453
TAIL = 0x53444B56
CLEAR = 0xFF3380B2
RED = 0xFFFF0000
GREEN = 0xFF00FF00
BENIGN_VCDI = 0x1000
LAYOUT_TRANSFER_SRC = 6  # vk_api.pbi's VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL


def expected_word(x: int, y: int, draws: int) -> int:
    if x % 4 in (1, 2) and y % 4 in (1, 2):
        index = (y // 4) * 32 + (x // 4)
        if index < draws:
            return GREEN if index & 1 else RED
    return CLEAR


def expected_hash(draws: int) -> int:
    value = 0x811C9DC5
    for y in range(128):
        for x in range(128):
            value = ((value ^ expected_word(x, y, draws)) * 0x01000193) & 0xFFFFFFFF
    return value


def parse_report(path: Path) -> tuple[int, ...]:
    data = path.read_bytes()
    if len(data) == 256:
        return struct.unpack("<64I", data)
    words: list[int] = []
    for line in data.decode("ascii").splitlines():
        body = line.partition(":")[2] if ":" in line else line
        words.extend(int(word, 16) for word in re.findall(r"\b[0-9A-Fa-f]{8}\b", body))
    if len(words) != 64:
        raise ValueError(f"report must contain 64 32-bit words; found {len(words)}")
    return tuple(words)


def verify_report(words: tuple[int, ...], draws: int) -> None:
    if draws not in COUNTS or len(words) != 64:
        raise ValueError("unsupported variant or report length")
    checks = {
        "magic": words[0] == MAGIC and words[63] == TAIL and words[62] == 256,
        "status": words[1] == 0 and words[61] == 8 and words[58] == 1,
        "map": words[5] == SURFACE and words[6] == WINDOW and words[7] == WINDOW_BYTES,
        "draws": words[54] == draws and words[52] == draws and words[14] == draws
                 and words[39] - words[38] == draws,
        "jobs": words[25] - words[24] == 1 and words[27] - words[26] == 1,
        "image": words[17] == 16384 and words[18] == 0 and words[19] == 0xFFFFFFFF
                 and words[22] == 0 and words[53] == expected_hash(draws),
        "guards": words[32] == words[33] and words[34] == words[35],
        "faults": words[42] == 0 and words[44] == 0 and words[45] == 0
                  and words[47] == 0 and words[48] == 0
                  and words[49] & ~BENIGN_VCDI == 0
                  and words[50] & ~BENIGN_VCDI == 0,
        "submission": words[23] == 0 and words[40] == 0 and words[41] == 0
                      and words[51] == LAYOUT_TRANSFER_SRC,
        "pixels": words[55] == RED and words[56] == GREEN
                  and words[59] == RED and words[60] == CLEAR,
    }
    bad = [name for name, passed in checks.items() if not passed]
    if bad:
        raise ValueError(f"draw-scale {draws} report failed: {', '.join(bad)}")


def self_test() -> None:
    for draws in COUNTS:
        report = [0] * 64
        report[0], report[63], report[62] = MAGIC, TAIL, 256
        report[61], report[58] = 8, 1
        report[5], report[6], report[7] = SURFACE, WINDOW, WINDOW_BYTES
        report[54] = report[52] = report[14] = draws
        report[38], report[39] = 4, 4 + draws
        report[24], report[25] = 7, 8
        report[26], report[27] = 9, 10
        report[17], report[19], report[53] = 16384, 0xFFFFFFFF, expected_hash(draws)
        report[32], report[33] = 0x9ABCDEF0, 0x9ABCDEF0
        report[34], report[35] = 0x12345678, 0x12345678
        report[43], report[44], report[45] = 0, 0, 0
        report[49], report[50] = BENIGN_VCDI, BENIGN_VCDI
        report[51] = LAYOUT_TRANSFER_SRC
        report[55], report[56], report[59], report[60] = RED, GREEN, RED, CLEAR
        verify_report(tuple(report), draws)
        for slot in (1, 18, 25, 39, 53, 33, 47, 63):
            altered = report.copy()
            altered[slot] ^= 1
            try:
                verify_report(tuple(altered), draws)
            except ValueError:
                pass
            else:
                raise AssertionError(f"checker accepted mutation in slot {slot}")
        binary = struct.pack("<64I", *report)
        if struct.unpack("<64I", binary) != tuple(report):
            raise AssertionError("report binary round-trip failed")
        with tempfile.TemporaryDirectory(prefix="drawscale-check-") as directory:
            path = Path(directory) / "report.bin"
            path.write_bytes(binary)
            if parse_report(path) != tuple(report):
                raise AssertionError("binary report parser failed")
            path.write_text(" ".join(f"{word:08X}" for word in report), encoding="ascii")
            if parse_report(path) != tuple(report):
                raise AssertionError("text report parser failed")
        other = 256 if draws == 64 else 64
        try:
            verify_report(tuple(report), other)
        except ValueError:
            pass
        else:
            raise AssertionError("checker accepted a report for the wrong variant")
    print("checker self-test PASS: 64/256/1024, report round-trip and eight mutations each")


def build(draws: int, compiler: str) -> None:
    if draws not in COUNTS:
        raise ValueError("variant must be 64, 256, or 1024")
    template = SOURCE.read_text(encoding="utf-8")
    marker = "#VTP_LIST_DRAWS = 64                 ; runner substitutes 256 or 1024"
    if template.count(marker) != 1:
        raise RuntimeError("draw-count template marker changed")
    if template.count("vkCmdBeginRenderPass(cmd,") != 1 or \
            template.count("vkCmdEndRenderPass(cmd)") != 1 or \
            template.count("vkQueueSubmit(queue, 1,") != 1 or \
            template.count("vkCmdDraw(cmd, 6, 1, scaleDraw * 6, 0)") != 1:
        raise RuntimeError("draw/pass/submit source contract changed")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    source = OUTPUT / f"drawscale-{draws}.pi4"
    image = OUTPUT / f"drawscale-{draws}.bin"
    source.write_text(template.replace(marker, marker.replace("= 64 ", f"= {draws} ")),
                      encoding="utf-8")
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    command = [compiler, "--compile", str(source), "-t", "pi4",
               "--load-addr", f"0x{LOAD:X}", "--stack-addr", f"0x{STACK:X}",
               "--entry-returns", "-o", str(image)]
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                            text=True, check=False)
    print(result.stdout, end="")
    print(result.stderr, end="")
    if result.returncode or not image.is_file():
        raise RuntimeError(f"signed IDE compile failed for {draws} draws")
    bss = re.search(r"\bbss \$([0-9A-F]+)\.\.\$([0-9A-F]+)\b", result.stdout)
    if bss is None:
        raise RuntimeError("compiler omitted BSS map")
    bss_first, bss_last = (int(value, 16) for value in bss.groups())
    if not LOAD <= bss_first <= bss_last < STACK or LOAD + image.stat().st_size >= bss_first:
        raise RuntimeError("compiled image/BSS/stack ranges overlap")
    if not SURFACE + SURFACE_BYTES == WINDOW or not WINDOW + WINDOW_BYTES < DSI_SCAN < ARENA:
        raise RuntimeError("private graphics map changed")
    if image.stat().st_size >= 4 * 1024 * 1024:
        raise RuntimeError("diagnostic image escaped the bounded RAM slot")
    for artifact in (source, image, Path(str(image) + ".pmf")):
        if not artifact.is_file():
            raise RuntimeError(f"compiler artifact missing: {artifact}")
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        print(f"{artifact.resolve()} SHA256 {digest}")
    print(f"map image=0x{LOAD:08X}..0x{LOAD + image.stat().st_size:08X} "
          f"BSS=0x{bss_first:08X}..0x{bss_last:08X} stack=0x{STACK:08X} "
          f"surface=0x{SURFACE:08X}..0x{WINDOW:08X} "
          f"window=0x{WINDOW:08X}..0x{WINDOW + WINDOW_BYTES:08X} "
          f"arena=0x{ARENA:08X}")
    print(f"variant {draws}: expected full-image FNV32 {expected_hash(draws):08X}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--build", type=int, choices=COUNTS)
    parser.add_argument("--check-report", type=Path)
    parser.add_argument("--draws", type=int, choices=COUNTS)
    parser.add_argument("--compiler", default=str(TRACKED_COMPILER))
    args = parser.parse_args()
    if args.self_test:
        self_test()
    if args.build is not None:
        build(args.build, resolve_compiler(args.compiler))
    if args.check_report is not None:
        if args.draws is None:
            parser.error("--check-report requires --draws")
        verify_report(parse_report(args.check_report), args.draws)
        print(f"draw-scale {args.draws} report PASS")
    if not args.self_test and args.build is None and args.check_report is None:
        parser.error("select --self-test, --build, or --check-report")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

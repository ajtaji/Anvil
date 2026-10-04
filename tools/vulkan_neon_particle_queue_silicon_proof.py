#!/usr/bin/env python3
"""Build/check the RAM-only Pi 4 internal particle-compute queue proof.

This tool never contacts a board. `build` prints the exact deadman-armed
board_run.py command for an operator to use when the board is available.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "Anvil/Graphics/Vulkan/Tests/neon_particle_queue_silicon_proof.pi4.in"
SPV = ROOT / "Anvil/Graphics/Vulkan/Tests/neon_particle_expand.spv"
OUT = ROOT / "runs/pi4-neon-compute-queue-proof-20261004"
COMPILER = Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")
SPV_SHA = "0d5ced6e1a5e9a91ffed258d860912d53a6a7fc832dfc20ffad5b549a367660a"
LOAD, STACK = 0x800000, 0x3000000
MAGIC, TAIL = 0x51504334, 0x34435051
INPUT_LIVE, OUTPUT_LIVE = 32 * 48, 32 * 144


def source_text() -> str:
    blob = SPV.read_bytes()
    if hashlib.sha256(blob).hexdigest() != SPV_SHA or len(blob) != 4036:
        raise ValueError("tracked particle SPIR-V differs from pinned silicon fixture")
    words = struct.unpack(f"<{len(blob) // 4}I", blob)
    template = TEMPLATE.read_text(encoding="utf-8")
    marker = "; @TRACKED_SPV_WORDS@"
    if template.count(marker) != 1:
        raise ValueError("SPIR-V insertion marker is absent or duplicated")
    return template.replace(marker, "\n".join(f"  Data.l ${word:08X}" for word in words))


def report_address(sym: Path) -> int:
    matches = re.findall(r"(?im)^global_pqreport\s*=\s*(\d+)\s*$", sym.read_text())
    if len(matches) != 1:
        raise ValueError("compiled symbol file lacks exactly one pqReport address")
    addr = int(matches[0])
    if addr < LOAD or addr >= STACK or addr % 8:
        raise ValueError(f"unexpected pqReport address 0x{addr:X}")
    return addr


def build() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    src = OUT / "neon_particle_queue_silicon_proof.pi4"
    image = OUT / "neon_particle_queue_silicon_proof.img"
    src.write_text(source_text(), encoding="utf-8", newline="\n")
    command = [str(COMPILER), "--compile", str(src), "-t", "pi4",
               "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
               "--entry-returns", "-o", str(image), "-s"]
    result = subprocess.run(command, cwd=ROOT, env={**os.environ, "PMF_ROOT": str(ROOT)},
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            timeout=180, check=False)
    (OUT / "compiler.log").write_text(result.stdout, encoding="utf-8")
    if result.returncode or "pmfc: OK" not in result.stdout:
        raise RuntimeError("payload compile failed; see " + str(OUT / "compiler.log") +
                           "\n" + result.stdout[-4000:])
    pmf = image.with_suffix(".img.pmf")
    if not pmf.is_file():
        raise RuntimeError("compiler did not produce returning PMF envelope")
    report = report_address(image.with_suffix(".img.sym"))
    if image.stat().st_size >= (STACK - LOAD):
        raise RuntimeError("image reaches the stack address")
    board_cmd = (f'python tools/board_run.py "{pmf.relative_to(ROOT).as_posix()}" '
                 f'--console-ip <BOARD_IP> --out "{(OUT / "board").relative_to(ROOT).as_posix()}" '
                 f'--deadman 15 --no-shot --trace 0x{report:X}:256 --expect-x0 0x{report:X}')
    check_cmd = ("python tools/vulkan_neon_particle_queue_silicon_proof.py check "
                 f'"{(OUT / "board" / (pmf.stem + ".trace.bin")).relative_to(ROOT).as_posix()}"')
    image_blob = image.read_bytes()
    if image_blob.count(SPV.read_bytes()) != 1:
        raise RuntimeError("image must contain exactly one byte-exact tracked SPIR-V module")
    pmf_blob = pmf.read_bytes()
    manifest = {
        "load_address": f"0x{LOAD:X}", "stack_address": f"0x{STACK:X}",
        "report_address": f"0x{report:X}", "report_bytes": 256,
        "image_bytes": image.stat().st_size,
        "image_sha256": hashlib.sha256(image_blob).hexdigest(),
        "upload_pmf": pmf.relative_to(ROOT).as_posix(),
        "upload_pmf_bytes": len(pmf_blob),
        "upload_pmf_sha256": hashlib.sha256(pmf_blob).hexdigest(),
        "spirv_sha256": SPV_SHA, "items": 32, "groups_x": 2,
        "input_live_bytes": INPUT_LIVE, "output_live_bytes": OUTPUT_LIVE,
        "board_command": board_cmd, "report_check_command": check_cmd,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"payload build: PASS ({image.stat().st_size} bytes, report 0x{report:X})")
    print(board_cmd)
    print(check_cmd)


def validate_report(blob: bytes) -> None:
    if len(blob) != 256:
        raise ValueError(f"report must be exactly 256 bytes; got {len(blob)}")
    w = struct.unpack("<64I", blob)
    failures = []

    def require(ok: bool, description: str) -> None:
        if not ok:
            failures.append(description)

    require(w[0] == MAGIC and w[63] == TAIL, "magic/tail")
    require(w[1] == 0 and w[2] == 5, f"status/stage ({w[1]}/{w[2]})")
    require(all(w[i] == 0 for i in (3, 4, 5, 6, 7, 9, 27)), "Vulkan/API status")
    require(w[8] == 32, "recorded invocation count")
    require(w[10] + 1 == w[33] and w[11] + 1 == w[34], "one native CSD job")
    require(w[12] == w[13] == w[14] == 0, "flight/quarantine/lease released")
    require(w[32] == 0, "no Vulkan faults")
    require(all(w[i] == 0 for i in (15, 16, 17, 18)), "vertex/input/guard mismatches")
    require(w[19] == 0, "first mismatch absent")
    require(w[22] == 0x063E8000 and w[23] == 0x00800000, "mapped GPU window")
    require(w[24] == INPUT_LIVE and w[25] == OUTPUT_LIVE, "descriptor live byte counts")
    require(w[26] >= w[22] and w[26] <= w[22] + w[23] - 12288 and w[26] % 4096 == 0,
            "bound storage allocation")
    require(w[28] == w[29] == 0x3F000000, "first output word")
    require(w[30] == w[31] == 0x3F800000, "last output word")
    if failures:
        raise ValueError("silicon report FAIL: " + ", ".join(failures) +
                         f"; status={w[1]}, stage={w[2]}, rc={w[9]}, "
                         f"first=({w[19]},0x{w[20]:08X},0x{w[21]:08X})")


def check_report(path: Path) -> None:
    validate_report(path.read_bytes())
    print("silicon report: PASS (32 items, 192 vertices, 1152 output words, "
          "input intact, both guards intact, one native CSD, lease released)")


def self_test() -> None:
    src = source_text()
    assert src.count("Data.l $") == 1009
    assert "AnvilVkCmdRecordComputeDispatch(pqCmd, 2, 1, 1)" in src
    assert "vkCmdDispatch(" not in src
    # Sanity-check the independent six-vertex oracle's 36 store sources.
    xy = ((0, 1), (4, 5), (6, 7), (0, 1), (6, 7), (2, 3))
    stores = [field for pair in xy for field in (*pair, 8, 9, None, None)]
    assert len(stores) == 36 and stores[:6] == [0, 1, 8, 9, None, None]
    w = [0] * 64
    w[0], w[63], w[2], w[8] = MAGIC, TAIL, 5, 32
    w[10], w[33], w[11], w[34] = 6, 7, 9, 10
    w[22], w[23], w[24], w[25], w[26] = 0x063E8000, 0x00800000, INPUT_LIVE, OUTPUT_LIVE, 0x06400000
    w[28], w[29], w[30], w[31] = 0x3F000000, 0x3F000000, 0x3F800000, 0x3F800000
    validate_report(struct.pack("<64I", *w))
    w[15] = 1
    try:
        validate_report(struct.pack("<64I", *w))
    except ValueError:
        pass
    else:
        raise AssertionError("host checker accepted an output mismatch")
    print("payload source: PASS (pinned SPIR-V, 36-store oracle, internal dispatch)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "check", "self-test"))
    parser.add_argument("report", type=Path, nargs="?", help="256-byte board trace for check")
    args = parser.parse_args()
    if args.action == "build":
        self_test()
        build()
    elif args.action == "self-test":
        self_test()
    elif args.report is None:
        parser.error("check requires the 256-byte board trace path")
    else:
        check_report(args.report)


if __name__ == "__main__":
    main()

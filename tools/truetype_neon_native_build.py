#!/usr/bin/env python3
"""Build a small returning PMF that exercises the real TrueType NEON converter."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tarfile
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from truetype_t1_check import base  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "_work/truetype-neon-native-20260919"
LOAD = 0x00600000
STACK = 0x03000000
STACK_RESERVE_BYTES = 0x10000
LOW_LO, LOW_HI = 0x00600000, 0x07EFFFFF
MON_BSS_LO, MON_BSS_HI = 0x0D000000, 0x0DFFFFFF
VULKAN_HEAP_LO, VULKAN_HEAP_HI = 0x0C000000, 0x0CFFFFFF
TOUCH_LO, TOUCH_HI = 0x01000000, 0x0100201F

OVERLAY = (
    "Anvil/Graphics/truetype.pbi",
    "Anvil/Graphics/truetype_metrics.pbi",
    "Anvil/Graphics/truetype_cmap.pbi",
    "Anvil/Graphics/truetype_outlines.pbi",
    "Anvil/Graphics/truetype_raster.pbi",
    "Anvil/Graphics/truetype_raster_neon.pbi",
    "RaspberryPi4/Tests/truetype_neon_gate.pi4",
    "RaspberryPi4/Intrinsics/bcm2711_hardware.def",
    "Boards/Raspberry_Pi_4.board",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def emulate_emitted_image(image: Path, blob: bytes, entry: int) -> tuple[int, int, tuple[int, ...]]:
    cpu = base.load_interp(base.INTERP).A64()
    cpu.sp = STACK
    cpu.memory = {LOAD + offset: byte for offset, byte in enumerate(blob)}
    cpu.pc = entry
    cpu.x[30] = base.RETURN_PC
    for steps in range(5_000_000):
        if cpu.pc == base.RETURN_PC:
            record = struct.unpack(
                "<8I", bytes(cpu.memory.get(TOUCH_LO + 0x2000 + i, 0) for i in range(32))
            )
            return cpu.x[0], steps, record
        cpu.step()
    raise SystemExit("compiled native-proof image exceeded 5,000,000 emitted instructions")


def make_export(export: Path) -> tuple[str, list[dict[str, object]]]:
    if export.exists() and any(export.iterdir()):
        raise SystemExit(f"refusing to replace non-empty native proof export: {export}")
    export.mkdir(parents=True, exist_ok=True)
    archive = subprocess.run(
        ["git", "archive", "--format=tar", "HEAD"], cwd=ROOT,
        check=True, capture_output=True,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tf:
        tf.extractall(export, filter="data")
    records = []
    for rel in OVERLAY:
        source = ROOT / rel
        if not source.is_file():
            raise SystemExit(f"required source is missing: {rel}")
        target = export / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        records.append({"path": rel, "bytes": target.stat().st_size, "sha256": sha256(target)})
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    return head, records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--compiler", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT,
                    help=f"output directory (default: {DEFAULT_OUT})")
    args = ap.parse_args()
    compiler = args.compiler.expanduser().resolve()
    out = args.out.expanduser().resolve()
    export = out / "clean-export"
    if not compiler.is_file():
        raise SystemExit(f"compiler not found: {compiler}")
    out.mkdir(parents=True, exist_ok=True)
    head, overlay = make_export(export)
    source = export / "RaspberryPi4/Tests/truetype_neon_gate.pi4"
    image = out / "truetype_neon_returning.img"
    env = os.environ.copy()
    env["PMF_ROOT"] = str(export)
    result = subprocess.run(
        [str(compiler), "--compile", str(source), "-t", "pi4", "--entry-returns",
         "--load-addr", hex(LOAD), "--stack-addr", hex(STACK), "-s", "-o", str(image)],
        cwd=export, env=env, capture_output=True, text=True,
    )
    (out / "compiler.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode or not image.is_file():
        raise SystemExit("native converter payload compile failed; see compiler.log")
    container = Path(str(image) + ".pmf")
    if not container.is_file():
        raise SystemExit("compiler did not emit a PMF container")
    data = container.read_bytes()
    if data[:8] != b"PMFBOOT\x00" or struct.unpack_from("<I", data, 8)[0] != 2:
        raise SystemExit("payload is not a PMF v2 container")
    header_bytes = struct.unpack_from("<I", data, 12)[0]
    load, entry, image_bytes, bss, bss_bytes = struct.unpack_from("<QQQQQ", data, 16)
    stack = struct.unpack_from("<Q", data, 104)[0]
    raw_image = image.read_bytes()
    if (header_bytes != 128 or image_bytes != len(raw_image)
            or len(data) != header_bytes + len(raw_image)
            or data[header_bytes:] != raw_image
            or data[64:96] != hashlib.sha256(raw_image).digest()):
        raise SystemExit("PMF container length, payload bytes, or image digest mismatch")
    image_hi = load + image_bytes - 1
    bss_hi = bss + bss_bytes - 1 if bss_bytes else bss - 1
    if load != LOAD or not load <= entry <= image_hi:
        raise SystemExit("PMF image/entry does not match the requested load address")
    if load < LOW_LO or image_hi > LOW_HI or bss < LOW_LO or bss_hi > LOW_HI:
        raise SystemExit("PMF image or BSS is outside the live low-payload mapping")
    if not (image_hi < bss or bss_hi < load):
        raise SystemExit("PMF image overlaps its BSS")
    if stack != STACK or not LOW_LO <= stack <= LOW_HI:
        raise SystemExit("PMF stack is not at the reviewed low-payload stack address")
    if bss_bytes and bss <= stack <= bss_hi:
        raise SystemExit("PMF stack overlaps its BSS")
    if bss_bytes and not (bss_hi < MON_BSS_LO or bss > MON_BSS_HI):
        raise SystemExit("PMF BSS overlaps build207's reserved monitor BSS")
    if bss_bytes and not (bss_hi < VULKAN_HEAP_LO or bss > VULKAN_HEAP_HI):
        raise SystemExit("PMF BSS overlaps build207's Vulkan heap")
    if not LOW_LO <= TOUCH_LO <= TOUCH_HI <= LOW_HI:
        raise SystemExit("declared test touch span is outside mapped low payload RAM")
    stack_lo = stack - STACK_RESERVE_BYTES + 1
    stack_hi = stack
    if not (TOUCH_HI < load or TOUCH_LO > image_hi):
        raise SystemExit("declared test touch span overlaps the PMF image")
    if bss_bytes and not (TOUCH_HI < bss or TOUCH_LO > bss_hi):
        raise SystemExit("declared test touch span overlaps PMF BSS")
    if not (TOUCH_HI < stack_lo or TOUCH_LO > stack_hi):
        raise SystemExit("declared test touch span overlaps the stack reserve")
    symbols = base.parse_symbols(image)
    if "main" not in symbols:
        raise SystemExit("compiler symbols are missing Main entry")
    returned, emitted_steps, record = emulate_emitted_image(image, raw_image, LOAD + symbols["main"])
    expected_record = (0x4E4E5053, 0x01000000, 0x01000040, 0x01001000,
                       0x01001040, 64, 17, 2)
    if returned != 0 or record != expected_record:
        raise SystemExit(f"native-proof image emitted replay failed: x0={returned}, record={record}")
    manifest = {
        "base_commit": head,
        "compiler": str(compiler),
        "compiler_sha256": sha256(compiler),
        "overlay": overlay,
        "output_directory": str(out),
        "payload_image": str(image),
        "payload_bytes": image.stat().st_size,
        "payload_sha256": sha256(image),
        "payload_container": str(container),
        "payload_container_bytes": container.stat().st_size,
        "payload_container_sha256": sha256(container),
        "load_range_inclusive": [f"0x{load:08X}", f"0x{image_hi:08X}"],
        "entry": f"0x{entry:08X}",
        "bss_range_inclusive": [f"0x{bss:08X}", f"0x{bss_hi:08X}"],
        "bss_bytes": bss_bytes,
        "stack_top": f"0x{stack:08X}",
        "stack_reserve_inclusive": [f"0x{stack_lo:08X}", f"0x{stack_hi:08X}"],
        "live_build207_monitor_bss_reservation_inclusive": [
            f"0x{MON_BSS_LO:08X}", f"0x{MON_BSS_HI:08X}"
        ],
        "live_build207_vulkan_heap_inclusive": [
            f"0x{VULKAN_HEAP_LO:08X}", f"0x{VULKAN_HEAP_HI:08X}"
        ],
        "declared_low_payload_touch_span_inclusive": [
            f"0x{TOUCH_LO:08X}", f"0x{TOUCH_HI:08X}"
        ],
        "test_buffers": {
            "scalar": ["0x01000000", "0x01000040"],
            "neon": ["0x01001000", "0x01001040"],
            "result_record": ["0x01002000", "0x0100201F"],
            "result_magic": "0x4E4E5053",
            "success_x0": 0,
        },
        "native_board_run_performed_by_builder": False,
        "emitted_replay": {"result_x0": returned, "instructions": emitted_steps,
                           "result_record_words": list(record), "result": "PASS"},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

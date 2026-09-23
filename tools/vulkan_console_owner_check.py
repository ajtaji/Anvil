#!/usr/bin/env python3
"""Emitted CPU-only safety gate for Vulkan console teardown and payload suspend."""
from __future__ import annotations
from pathlib import Path
import re
import shutil
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "RaspberryPi4/Board/vulkan_console.pi4"
TEMPLATE = ROOT / "RaspberryPi4/Tests/vulkan_console_owner_gate.pi4"
CACHE = ROOT / "RaspberryPi4/Board/cache.pi4"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from truetype_slots_check import compile_gate, run_entry  # noqa: E402

PROCEDURES = ("VulkanConsoleDestroy", "avcCpuCursorRefresh", "avcFailover", "VulkanConsoleStop", "VulkanConsolePayloadSuspend")

def body(source: str, name: str) -> str:
    m = re.search(rf"(?ms)^Procedure(?:\.[A-Za-z]+)?\s+{re.escape(name)}\s*\(.*?^EndProcedure\s*$", source)
    if not m:
        raise SystemExit(f"missing production procedure {name}")
    return m.group(0)

def validate_payload_boundary(cache: str) -> None:
    start = cache.index("Procedure RunAt(a.i)")
    run = cache[start:cache.index("\nEndProcedure", start)]
    suspend = run.index("VulkanConsolePayloadSuspend()")
    refusal = run.index("If vkState < 0", suspend)
    jump = run.index("CallAddr()", refusal)
    if not suspend < refusal < jump:
        raise SystemExit("RunAt no longer refuses payload entry after failed Vulkan suspend")
    refusal_block = run[refusal:jump]
    if "ProcedureReturn 0" not in refusal_block:
        raise SystemExit("failed Vulkan suspend does not abort cleanly before payload entry")

def validate_grid_batch_reservation(source: str) -> None:
    if not re.search(r"(?m)^#AVC_UI_QUAD_RESERVE\s*=\s*512\s*$", source):
        raise SystemExit("resident UI quad reserve is missing or changed")
    if not re.search(
        r"NeonVkChromeGridBatchReserve\(\s*ConGridCols\(\)\s*\*\s*ConGridRows\(\)\s*\+\s*#AVC_UI_QUAD_RESERVE\s*,\s*2\s*\)",
        source,
    ):
        raise SystemExit("resident grid does not reserve the full cell count and two color segments")
    pump_start = source.index("Procedure VulkanConsolePump()")
    pump = source[pump_start:source.index("\nEndProcedure", pump_start)]
    if not re.search(r"For pass\s*=\s*0 To 1", pump):
        raise SystemExit("resident grid no longer emits both ink passes")

def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python tools/vulkan_console_owner_check.py COMPILER")
    compiler = Path(sys.argv[1]).expanduser().resolve()
    if not compiler.is_file():
        raise SystemExit(f"compiler not found: {compiler}")
    source = SOURCE.read_text(encoding="utf-8")
    validate_payload_boundary(CACHE.read_text(encoding="utf-8"))
    validate_grid_batch_reservation(source)
    procs = "\n\n".join(body(source, n) for n in PROCEDURES)
    gate = TEMPLATE.read_text(encoding="utf-8")
    marker = ";@@OWNER_PROCS@@"
    if gate.count(marker) != 1:
        raise SystemExit("fixture insertion marker missing or duplicated")
    gate = gate.replace(marker, procs, 1)
    with tempfile.TemporaryDirectory(prefix="anvil-vulkan-owner-") as tmp:
        stage = Path(tmp) / "stage"
        stage.mkdir()
        for rel in ("RaspberryPi4/Intrinsics/bcm2711_hardware.def", "Boards/Raspberry_Pi_4.board"):
            target = stage / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, target)
        emitted = stage / "vulkan_console_owner_emitted.pi4"
        emitted.write_text(gate, encoding="utf-8")
        symbols, blob = compile_gate(compiler, stage, emitted, Path(tmp) / "owner.img")
        result, steps = run_entry(symbols, blob, b"")
        if result:
            raise SystemExit(f"Vulkan owner emitted gate failed: case {result}")
        checks = gate.count("ownerCheck(") - 1
        print(f"PASS: Vulkan owner teardown/payload emitted gate; {checks} checks, {steps} interpreted instructions")
        print("PASS: failed idle retains handles and forbids V3D invalidation, framebuffer paint and payload entry")
        print("PASS: safe release repaints once; failed V3D invalidation quarantines without repaint")
        print("PASS: resident owner reserves cols*rows plus 512 UI quads for two color passes")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

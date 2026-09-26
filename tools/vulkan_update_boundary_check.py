#!/usr/bin/env python3
"""Emitted A64 gate for the complete 64 KiB vkCmdUpdateBuffer payload."""

from __future__ import annotations

import argparse
import pathlib

import vulkan_resource_check as resource

ROOT = pathlib.Path(__file__).resolve().parent.parent
GATE = ROOT / "RaspberryPi4" / "Tests" / "vulkan_update_boundary_gate.pi4"
MAGIC = 0x56555044  # VUPD


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler")
    parser.add_argument("--interp")
    args = parser.parse_args()
    compiler = resource.locate("PMF_COMPILER", args.compiler, [ROOT / "PureMetalForge.exe"])
    interp = resource.load_interpreter(resource.locate(
        "PMF_A64_INTERP", args.interp, [ROOT / "tools" / "a64" / "a64_interp.py"]))
    resource.GATE = GATE
    cpu, rc, steps = resource.run_once(interp, compiler, {})
    checks = resource.u64(cpu, resource.OUT + 8)
    fails = resource.u64(cpu, resource.OUT + 16)
    bad = [i + 1 for i in range(checks)
           if resource.u64(cpu, resource.ROWS + i * 8) == 0]
    if resource.u64(cpu, resource.OUT) != MAGIC or checks != 14 or fails or rc or bad:
        print(f"vulkan_update_boundary_check: FAIL - {checks} checks, {steps:,} A64 instructions")
        print(f"  magic={resource.u64(cpu, resource.OUT):#x} rc={rc} fails={fails} bad rows={bad}")
        return 1
    print(f"vulkan_update_boundary_check: PASS - {checks} checks, {steps:,} A64 instructions")
    print("  all 65536 destination bytes match the recorded source, including bytes later changed by the caller; no MMIO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

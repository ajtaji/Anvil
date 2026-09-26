#!/usr/bin/env python3
"""Emitted A64 gate for transactional vkAllocateDescriptorSets arrays."""
from __future__ import annotations

import argparse
import pathlib

import vulkan_resource_check as resource

ROOT = pathlib.Path(__file__).resolve().parent.parent
GATE = ROOT / "RaspberryPi4" / "Tests" / "vulkan_descriptor_allocate_gate.pi4"
MAGIC = 0x5644414C
CHECKS = 31


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
    if resource.u64(cpu, resource.OUT) != MAGIC or checks != CHECKS or fails or rc or bad:
        print(f"vulkan_descriptor_allocate_check: FAIL - {checks} checks, {steps:,} A64 instructions")
        print(f"  magic={resource.u64(cpu, resource.OUT):#x} rc={rc} fails={fails} bad rows={bad}")
        return 1
    print(f"vulkan_descriptor_allocate_check: PASS - {checks} checks, {steps:,} A64 instructions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

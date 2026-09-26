#!/usr/bin/env python3
"""Emitted A64 gate for public vkFreeDescriptorSets pool accounting."""
from __future__ import annotations

import argparse
import pathlib

import vulkan_resource_check as resource

ROOT = pathlib.Path(__file__).resolve().parent.parent
GATE = ROOT / "RaspberryPi4" / "Tests" / "vulkan_descriptor_free_gate.pi4"
MAGIC = 0x56444652
CHECKS = 38


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler")
    parser.add_argument("--interp")
    parser.add_argument("--mutate", action="store_true")
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
        print(f"vulkan_descriptor_free_check: FAIL - {checks} checks, {steps:,} A64 instructions")
        print(f"  magic={resource.u64(cpu, resource.OUT):#x} rc={rc} fails={fails} bad rows={bad}")
        return 1
    print(f"vulkan_descriptor_free_check: PASS - {checks} checks, {steps:,} A64 instructions")
    if args.mutate:
        source = (ROOT / "Anvil" / "Graphics" / "Vulkan" / "vk_descriptor.pbi").read_text(encoding="utf-8")
        mutations = (
            ("quota leak", "  avkDpUboOut[p] = avkDpUboOut[p] - needUbo\n",
             "  avkDpUboOut[p] = avkDpUboOut[p] - 0\n"),
            ("duplicate free accepted", "        If PeekI(*sets + (j * SizeOf(.i))) = handle\n",
             "        If 0 = 1\n"),
        )
        for name, before, after in mutations:
            if source.count(before) != 1:
                raise SystemExit(f"stale mutation anchor: {name}")
            mcpu, mrc, _ = resource.run_once(interp, compiler, {
                "vk_descriptor.pbi": source.replace(before, after, 1)})
            mfails = resource.u64(mcpu, resource.OUT + 16)
            if mrc == 0 and mfails == 0:
                raise SystemExit(f"GREEN mutation: {name}")
            print(f"  RED: {name} ({mfails} failed rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

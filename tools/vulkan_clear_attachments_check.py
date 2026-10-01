#!/usr/bin/env python3
"""Focused public command and AArch64 ABI gate for ordered attachment clears."""

from __future__ import annotations

import argparse
import hashlib
import vulkan_pipeline_check as pipeline
import vulkan_v3d_backend_check as backend


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", required=True)
    args = parser.parse_args()
    compiler = pipeline.locate_compiler(args.compiler)
    digest = hashlib.sha256(compiler.read_bytes()).hexdigest().upper()
    a64 = pipeline.load_interpreter(pipeline.ROOT / "tools" / "a64" / "a64_interp.py")

    public_source = pipeline.ROOT / "Anvil" / "Graphics" / "Vulkan" / "Tests" / "vulkan_clear_attachments_gate.pi4"
    image = pipeline.compile_one(compiler, public_source,
                                 "anvil_vk_clear_attachments_gate.img",
                                 backend.LOAD, backend.STACK)
    _cpu, result, steps = backend.execute(a64, image)
    failures = []
    if result != 0:
        failures.append(f"public clear fixture returned checkpoint {result}")

    abi_source = pipeline.ROOT / "Anvil" / "Graphics" / "Vulkan" / "Tests" / "vulkan_clear_abi_gate.pi4"
    abi_image = pipeline.compile_one(compiler, abi_source,
                                     "anvil_vk_clear_abi_gate.img",
                                     backend.LOAD, backend.STACK)
    _abi_cpu, abi_result, abi_steps = backend.execute(a64, abi_image)
    if abi_result != 0:
        failures.append(f"AArch64 record size/offset ABI: got {abi_result}, expected 0")

    if failures:
        print("vulkan_clear_attachments_check: FAIL")
        for failure in failures:
            print("  " + failure)
        return 1
    print(f"vulkan_clear_attachments_check: PASS - 2 fixtures over "
          f"{steps + abi_steps:,} executed A64 instructions")
    print(f"  compiler SHA-256 {digest}")
    print("  public clear-only, capability-off, ordered clear/clear, malformed rectangle, and ABI")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

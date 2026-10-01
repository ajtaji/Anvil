#!/usr/bin/env python3
"""Focused public optimal-to-linear image-copy gate on the AArch64 test backend."""

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
    source = pipeline.ROOT / "Anvil" / "Graphics" / "Vulkan" / "Tests" / "vulkan_partial_optimal_linear_gate.pi4"
    image = pipeline.compile_one(compiler, source,
                                 "anvil_vk_partial_optimal_linear_gate.img",
                                 backend.LOAD, backend.STACK)
    _cpu, result, steps = backend.execute(a64, image)
    if result != 0:
        print(f"vulkan_partial_optimal_linear_check: FAIL - checkpoint {result} "
              f"after {steps:,} A64 instructions")
        return 1
    print(f"vulkan_partial_optimal_linear_check: PASS - public edge-tail, offset, "
          f"refusal, whole-image and state-only submission checks over {steps:,} A64 instructions")
    print(f"  compiler SHA-256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

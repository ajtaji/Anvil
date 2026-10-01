#!/usr/bin/env python3
"""Focused public linear-image to optimal-image microcopy gate."""

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
    total = 0
    for stem in ("vulkan_linear_tiled_micro_gate", "vulkan_buffer_tiled_micro_validator_gate"):
        source = pipeline.ROOT / "Anvil" / "Graphics" / "Vulkan" / "Tests" / (stem + ".pi4")
        image = pipeline.compile_one(compiler, source, "anvil_" + stem + ".img", backend.LOAD, backend.STACK)
        _cpu, result, steps = backend.execute(a64, image)
        if result != 0:
            print(f"vulkan_linear_tiled_micro_check: FAIL - {stem} checkpoint {result} after {steps:,} A64 instructions")
            return 1
        total += steps
    print(f"vulkan_linear_tiled_micro_check: PASS - 2 fixtures; public cap/preflight and pure UIF micro validator over {total:,} A64 instructions")
    print(f"  compiler SHA-256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

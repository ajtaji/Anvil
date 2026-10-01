#!/usr/bin/env python3
"""Focused public tiled-rectangle copy gate on the AArch64 test backend."""

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
    source = pipeline.ROOT / "Anvil" / "Graphics" / "Vulkan" / "Tests" / "vulkan_tiled_rect_copy_gate.pi4"
    image = pipeline.compile_one(compiler, source,
                                 "anvil_vk_tiled_rect_copy_gate.img",
                                 backend.LOAD, backend.STACK)
    _cpu, result, steps = backend.execute(a64, image)
    if result != 0:
        print(f"vulkan_tiled_rect_copy_check: FAIL - checkpoint {result} "
              f"after {steps:,} A64 instructions")
        return 1
    validator = pipeline.ROOT / "Anvil" / "Graphics" / "Vulkan" / "Tests" / "vulkan_tiled_rect_validator_gate.pi4"
    validator_image = pipeline.compile_one(compiler, validator,
                                           "anvil_vk_tiled_rect_validator_gate.img",
                                           backend.LOAD, backend.STACK)
    _cpu, validator_result, validator_steps = backend.execute(a64, validator_image)
    if validator_result != 0:
        print(f"vulkan_tiled_rect_copy_check: FAIL - UIF validator checkpoint "
              f"{validator_result} after {validator_steps:,} A64 instructions")
        return 1
    print(f"vulkan_tiled_rect_copy_check: PASS - 2 fixtures; partial tiled rectangle, "
          f"capability, alignment, alias, tile-range, whole-stream and TFU-independence "
          f"checks over {steps + validator_steps:,} A64 instructions")
    print(f"  compiler SHA-256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

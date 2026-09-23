#!/usr/bin/env python3
"""Execute the shared banner identity formatter, without board or MMIO access.

Uses the same guarded image/BSS/stack executor as the packet-state probes.
Pass --compiler and --interp, or set PMF_COMPILER and PMF_A64_INTERP.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import tempfile

import tcp_multiif_emitted_check as emitted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"))
    args = parser.parse_args()
    compiler = emitted.required_path(args.compiler, "PMF_COMPILER")
    interpreter = emitted.load_interpreter(
        emitted.required_path(args.interp, "PMF_A64_INTERP")
    )
    emitted.PROBE = emitted.ROOT / "RaspberryPi4/Tests/build_identity_compile.pi4"
    with tempfile.TemporaryDirectory(prefix="anvil-build-identity-") as temporary:
        image = emitted.build(compiler, Path(temporary))
        result, steps = emitted.execute(interpreter, image)
    if result:
        raise SystemExit(f"build identity: FAIL assertion {result}")
    print(f"build identity: PASS - 11 assertions, {steps:,} emitted A64 instructions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

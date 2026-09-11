#!/usr/bin/env python3
"""Compile and execute the production network-console ownership gate.

Requires PMF_COMPILER and PMF_A64_INTERP (or --compiler/--interp). The execution
sandbox is the shared emitted-gate runner's image/BSS/stack whitelist.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile

import tcp_multiif_emitted_check as emitted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"))
    args = parser.parse_args()
    compiler = emitted.required_path(args.compiler, "PMF_COMPILER")
    interp = emitted.required_path(args.interp, "PMF_A64_INTERP")
    emitted.PROBE = emitted.ROOT / "RaspberryPi4" / "Tests" / "netconsole_owner_emitted_gate.pi4"
    a64 = emitted.load_interpreter(interp)
    with tempfile.TemporaryDirectory(prefix="anvil-netconsole-owner-emitted-") as temporary:
        image = emitted.build(compiler, Path(temporary))
        result, steps = emitted.execute(a64, image)
    if result:
        print(f"netconsole_owner_emitted_check: FAIL assertion {result} after {steps:,} A64 instructions")
        return 1
    print(f"netconsole_owner_emitted_check: PASS - 51 assertions, {steps:,} A64 instructions")
    return 0


if __name__ == "__main__":
    sys.exit(main())

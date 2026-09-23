#!/usr/bin/env python3
"""Prove Vulkan pipeline gates cannot alias outputs or mutation windows."""

from __future__ import annotations

import pathlib
import subprocess
import sys


CHECKER = pathlib.Path(__file__).resolve().with_name("vulkan_pipeline_check.py")


def main() -> int:
    command = [sys.executable, str(CHECKER), "--coordination-probe"]
    first = subprocess.Popen(command, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True)
    second = subprocess.Popen(command, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True)
    out_a, _ = first.communicate(timeout=10)
    out_b, _ = second.communicate(timeout=10)
    if first.returncode or second.returncode:
        print("vulkan_pipeline_concurrency_check: probe failed")
        print(out_a + out_b)
        return 1

    try:
        path_a, start_a, end_a = out_a.strip().rsplit("|", 2)
        path_b, start_b, end_b = out_b.strip().rsplit("|", 2)
        start_a, end_a = int(start_a), int(end_a)
        start_b, end_b = int(start_b), int(end_b)
    except ValueError:
        print("vulkan_pipeline_concurrency_check: malformed probe output")
        print(repr(out_a), repr(out_b))
        return 1

    distinct = path_a != path_b
    serialized = end_a <= start_b or end_b <= start_a
    if not distinct or not serialized:
        print("vulkan_pipeline_concurrency_check: FAIL")
        print(f"  distinct workspaces: {distinct}")
        print(f"  serialized source window: {serialized}")
        return 1
    print("vulkan_pipeline_concurrency_check: PASS - 2 unique workspaces, "
          "non-overlapping source windows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

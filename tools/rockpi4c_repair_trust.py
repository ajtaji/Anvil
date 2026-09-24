#!/usr/bin/env python3
"""Repair the fixed Rock Pi 4C SD trust area after validating the disk bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from rockpi4c_update import TRUST_BYTES, TRUST_COPY, validate_trust_image


OFFSET = 0x6000 * 512
DTB_OFFSET = 2048 + (0x1C0000 - 0x40000)


def disk_info(number: int) -> dict:
    script = (
        f"$d=Get-Disk -Number {number}; "
        f"$p=Get-Partition -DiskNumber {number} | Sort-Object Offset | Select-Object -First 1; "
        "@{BusType=[string]$d.BusType;Size=[int64]$d.Size;"
        "FirstPartition=[int64]$p.Offset} | ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def repair(number: int, expected: bytes, replacement: bytes, template: bytes) -> dict:
    if number < 0 or number > 99:
        raise ValueError("invalid disk number")
    if len(expected) != TRUST_BYTES or len(replacement) != TRUST_BYTES:
        raise ValueError("trust images must each be exactly 4 MiB")
    validate_trust_image(expected)
    validate_trust_image(replacement)
    validate_trust_image(template)
    if replacement[:2048] == expected[:2048]:
        raise ValueError("replacement still has the old component digest")
    for copy in (0, TRUST_COPY):
        if replacement[copy + DTB_OFFSET:copy + DTB_OFFSET + 4] != bytes.fromhex("d00dfeed"):
            raise ValueError("replacement has no embedded DTB")
        if replacement[copy + DTB_OFFSET:copy + TRUST_COPY] != template[DTB_OFFSET:TRUST_COPY]:
            raise ValueError("replacement does not preserve the proven DTB tail")

    info = disk_info(number)
    if info["BusType"].upper() != "USB" or info["Size"] < 64 * 1024 * 1024:
        raise ValueError("target is not a USB storage disk")
    if info["FirstPartition"] != 16 * 1024 * 1024:
        raise ValueError("target's first partition does not start at 16 MiB")

    path = rf"\\.\PhysicalDrive{number}"
    with open(path, "r+b", buffering=0) as disk:
        disk.seek(OFFSET)
        present = disk.read(TRUST_BYTES)
        if present != expected:
            raise ValueError("disk trust area does not match the expected failed image")
        for copy in (TRUST_COPY, 0):
            disk.seek(OFFSET + copy)
            written = disk.write(replacement[copy:copy + TRUST_COPY])
            if written != TRUST_COPY:
                raise OSError("short trust-copy write")
            disk.flush()
            disk.seek(OFFSET + copy)
            if disk.read(TRUST_COPY) != replacement[copy:copy + TRUST_COPY]:
                raise OSError("trust-copy readback mismatch")
        disk.seek(OFFSET)
        if disk.read(TRUST_BYTES) != replacement:
            raise OSError("full trust-area readback mismatch")
    return {
        "disk": number,
        "bus": info["BusType"],
        "bytes": TRUST_BYTES,
        "sha256": hashlib.sha256(replacement).hexdigest(),
        "result": "both trust copies read back exactly",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disk-number", type=int, required=True)
    parser.add_argument("--expected-current", type=Path, required=True)
    parser.add_argument("--replacement", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = repair(
            args.disk_number,
            args.expected_current.read_bytes(),
            args.replacement.read_bytes(),
            args.template.read_bytes(),
        )
    except Exception as exc:
        result = {"result": "failed", "error": str(exc)}
        args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result))
        return 1
    args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

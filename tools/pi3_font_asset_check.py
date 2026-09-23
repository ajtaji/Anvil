#!/usr/bin/env python3
"""Verify the bundled Pi 3 Courier Prime font and its license pairing."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "RaspberryPi3" / "Data" / "fonts"
FONT = ASSETS / "CourierPrime-Regular.ttf"
LICENSE = ASSETS / "CourierPrime-OFL.txt"
MANIFEST = ASSETS / "manifest.json"
README = ASSETS / "README.txt"

EXPECTED_FONT_BYTES = 71188
EXPECTED_FONT_SHA256 = "72f793376f8e2841656bf21d77a5de010f2929bd6956a22ee848ad0c7eb978af"
EXPECTED_LICENSE_BYTES = 4403
EXPECTED_LICENSE_SHA256 = "9a755af092b494944c99f471be6fddd19b006a448fefdc4717e4ee0aa09a97b0"
EXPECTED_MONITOR_PATH = "2:/fonts/CourierPrime-Regular.ttf"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    for path in (FONT, LICENSE, MANIFEST, README):
        if not path.is_file():
            raise SystemExit(f"missing Pi 3 font package file: {path}")

    if FONT.stat().st_size != EXPECTED_FONT_BYTES or sha256(FONT) != EXPECTED_FONT_SHA256:
        raise SystemExit("Courier Prime font bytes do not match the pinned source artifact")
    if LICENSE.stat().st_size != EXPECTED_LICENSE_BYTES or sha256(LICENSE) != EXPECTED_LICENSE_SHA256:
        raise SystemExit("Courier Prime OFL text does not match the pinned source artifact")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    expected = {
        "family": "Courier Prime",
        "font_file": FONT.name,
        "font_bytes": EXPECTED_FONT_BYTES,
        "font_sha256": EXPECTED_FONT_SHA256,
        "source_commit": "f2bd09badbc763d8757951d52deec29da27e85fb",
        "license": "SIL Open Font License 1.1",
        "license_file": LICENSE.name,
        "license_bytes": EXPECTED_LICENSE_BYTES,
        "license_sha256": EXPECTED_LICENSE_SHA256,
        "monitor_path": EXPECTED_MONITOR_PATH,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise SystemExit(f"manifest field {key!r} does not match the pinned asset")
    license_text = LICENSE.read_text(encoding="utf-8")
    if "Copyright 2015 The Courier Prime Project Authors" not in license_text:
        raise SystemExit("font-specific copyright notice is missing")
    if "SIL OPEN FONT LICENSE Version 1.1" not in license_text:
        raise SystemExit("full SIL Open Font License 1.1 text is missing")
    if EXPECTED_MONITOR_PATH not in README.read_text(encoding="utf-8"):
        raise SystemExit("README does not name the Pi 3 partition path")

    print("PASS: Courier Prime TTF and matching SIL OFL 1.1 package")
    print(f"PASS: {EXPECTED_FONT_BYTES} bytes, SHA-256 {EXPECTED_FONT_SHA256}")
    print(f"PASS: monitor path {EXPECTED_MONITOR_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

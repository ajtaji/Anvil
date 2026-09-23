#!/usr/bin/env python3
"""Check that Pi 3 storage installs the shared ranged block seam."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORAGE = ROOT / "RaspberryPi3" / "Board" / "storage.pi3"
SDHOST = ROOT / "RaspberryPi3" / "Lib" / "sdhost.pbi"


def fail(message: str) -> None:
    raise SystemExit("pi3 storage seam gate: " + message)


def uncomment(text: str) -> str:
    text = re.sub(r";[^\r\n]*", "", text)
    return re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)


def procedure(text: str, header: str) -> str:
    start = text.find(header)
    if start < 0:
        fail(f"missing procedure {header}")
    end = text.find("\nEndProcedure", start)
    if end < 0:
        fail(f"unterminated procedure {header}")
    return text[start:end]


def check(storage: str, sdhost: str) -> list[str]:
    held: list[str] = []
    clean = uncomment(storage)
    confirm = procedure(clean, "Procedure.i Pi3StorageForConfirm()")
    normal = procedure(clean, "Procedure.i StorageUp()")
    record = procedure(clean, "Procedure.i Pi3BootWriteRecord(slot.i, buffer.i)")
    if confirm.count("FsSetRangeReader(@Pi3SdReadBlocks)") != 1 or normal.count("FsSetRangeReader(@Pi3SdReadBlocks)") != 1:
        fail("both confirm and normal storage paths must install Pi3SdReadBlocks")
    held.append("reader installed as ranged Pi3SdReadBlocks")
    if confirm.count("FsSetRangeWriter(0)") != 1 or normal.count("FsSetRangeWriter(0)") != 1 or record.count("FsSetRangeWriter(0)") != 2:
        fail("confirm, normal setup, and record cleanup must disarm the writer")
    held.append("writer is disarmed outside writes")
    for body in (confirm, normal):
        for pointer in ("gPi3FileWriter", "gHwFileWriter"):
            assignments = re.findall(rf"\b{pointer}\s*=\s*(@\w+|0)\b", body)
            if assignments != ["@Pi3StorageWriteBlocks", "0", "0"]:
                fail(f"{pointer} must use the ranged writer or be disabled")
    if record.count("FsSetRangeWriter(@Pi3SdWriteBlocks)") != 1:
        fail("record writes must arm the ranged writer pointer")
    bounded = procedure(clean, "Procedure.i Pi3StorageWriteBlocks(lba.i, count.i, buffer.i)")
    if not (bounded.index('Pi3SdSetWriteWindow(lba, count)') < bounded.index('Pi3SdWriteBlocks(lba, count, buffer)') < bounded.index('Pi3SdSetWriteWindow(0, 0)')):
        fail('file writes must arm the exact range then close it')
    held.append("writer uses ranged Pi3SdWriteBlocks under a per-call fence")
    if len(re.findall(r"^Procedure\.i Pi3SdReadBlocks\(lba\.i, count\.i, buffer\.i\)", uncomment(sdhost), re.MULTILINE)) != 1:
        fail("sdhost must define the three-argument ranged reader")
    if len(re.findall(r"^Procedure\.i Pi3SdWriteBlocks\(lba\.i, count\.i, buffer\.i\)", uncomment(sdhost), re.MULTILINE)) != 1:
        fail("sdhost must define the three-argument ranged writer")
    held.append("driver procedures have the ranged three-argument contract")
    return held


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    storage = STORAGE.read_text(encoding="utf-8") + '\n' + (ROOT / 'RaspberryPi3/Lib/boot_record.pbi').read_text(encoding='utf-8')
    sdhost = SDHOST.read_text(encoding="utf-8")
    check(storage, sdhost)
    if args.self_test:
        mutant = storage.replace("    gPi3FileWriter = @Pi3StorageWriteBlocks", "    gPi3FileWriter = @Pi3SdWriteBlock", 1)
        try:
            check(mutant, sdhost)
        except SystemExit:
            pass
        else:
            fail("one-block writer mutant was not rejected")
    print("pi3_storage_seam_check: PASS - shared filesystem has ranged reader/writer and the driver arity matches")
    if args.self_test:
        print("  self-test: one-block writer mutant rejected")
    return 0


if __name__ == "__main__":
    main()

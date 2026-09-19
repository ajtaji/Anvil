#!/usr/bin/env python3
"""Check the Pi 3 source placement contract and an optional emitted slot."""

from __future__ import annotations

import argparse
import hashlib
import re
import struct
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "RaspberryPi3" / "Board" / "board.pi3"
sys.path.insert(0, str(ROOT / "tools"))
from pi3_slot import SlotError, validate_slot  # noqa: E402


def fail(message: str) -> None:
    raise SystemExit("pi3 slot contract gate: " + message)


def source_values(text: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for name in ("LoadAddress", "BssAddress", "StackAddress"):
        found = re.findall(rf"^\s*{name}\s+\$([0-9A-Fa-f]+)\s*$", text, re.MULTILINE)
        if len(found) != 1:
            fail(f"{name} must occur once")
        out[name] = int(found[0], 16)
    return out


def check(board: str, slot: bytes | None = None) -> dict[str, int | str]:
    values = source_values(board)
    import pi3_slot
    expected = {"LoadAddress": pi3_slot.LOAD_ADDRESS, "BssAddress": pi3_slot.BSS_ADDRESS, "StackAddress": pi3_slot.STACK_ADDRESS}
    if values != expected:
        fail(f"source placement {values} differs from tools/pi3_slot.py {expected}")
    result: dict[str, int | str] = {k: f"0x{v:X}" for k, v in values.items()}
    if slot is not None:
        try:
            metadata = validate_slot(slot)
        except SlotError as exc:
            fail(str(exc))
        result.update({k: metadata[k] for k in ("imageBytes", "bssBytes", "slotBytes", "slotSha256")})
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slot", type=Path,
                        help="optional legacy A/B slot; normal direct boot needs no slot")
    parser.add_argument("--source-only", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    board = BOARD.read_text(encoding="utf-8")
    if args.source_only or args.slot is None:
        artifact = None
    else:
        if not args.slot.is_file():
            fail(f"monitor artifact is missing: {args.slot}; use --source-only for the source contract")
        artifact = args.slot.read_bytes()
    result = check(board, artifact)
    if args.self_test:
        for name, old, new in (("load", "LoadAddress  $200000", "LoadAddress  $300000"), ("bss", "BssAddress   $1100000", "BssAddress   $1200000"), ("stack", "StackAddress $1F00000", "StackAddress $1E00000")):
            mutant = board.replace(old, new, 1)
            try:
                check(mutant, None)
            except SystemExit:
                continue
            fail(f"{name} placement mutant was not rejected")
        if artifact is not None:
            for name, offset, value in (("wrong-target", 100, 9999), ("oversize-bss", 48, 0xD00001)):
                mutant = bytearray(artifact)
                pmf = 128
                struct.pack_into("<I", mutant, pmf + offset, value)
                mutant[pmf + 64:pmf + 96] = hashlib.sha256(mutant[pmf + 128:]).digest()
                mutant[40:72] = hashlib.sha256(mutant[128:]).digest()
                try:
                    check(board, bytes(mutant))
                except SystemExit:
                    continue
                fail(f"{name} artifact mutant was not rejected")
    source_note = "source-only" if artifact is None else f"explicit artifact {args.slot} structurally validated"
    print(f"pi3_slot_contract_check: PASS - {source_note}; load {result['LoadAddress']}, BSS {result['BssAddress']}, stack {result['StackAddress']}")
    if artifact is not None:
        print(f"  emitted image {result['imageBytes']} B, BSS {result['bssBytes']} B, slot {result['slotBytes']} B, sha256 {result['slotSha256']}")
    if args.self_test:
        print("  self-test: 3/3 placement mutants rejected")
        if artifact is not None:
            print("  self-test: 2/2 rehashed PMF target/bounds mutants rejected")
    return 0


if __name__ == "__main__":
    main()

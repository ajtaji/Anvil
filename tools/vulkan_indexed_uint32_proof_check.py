#!/usr/bin/env python3
"""Check the short Pi 4 UINT32 indexed-draw RAM report and captured BCL."""
from __future__ import annotations

import argparse
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "RaspberryPi4/Examples/Diagnostics/vulkanIndexedTriangle32Proof.pi4"
BODY = ROOT / "RaspberryPi4/Examples/Diagnostics/vulkanTriangleProofBody.pbi"
INDEX_WORDS = (0xA1B2C3D4, 0xE5F60718, 99, 2, 0, 1, 0x193A5B7C, 0x8D9EAFB0)
REPORT_WORDS = 64


def check_source(wrapper: str, body: str) -> list[str]:
    required = (
        ("wrapper mode", "#VTP_INDEXED_PROOF = 2", wrapper),
        ("public UINT32 bind", "vkCmdBindIndexBuffer(cmd, ibuf, 8, #VK_INDEX_TYPE_UINT32)", body),
        ("firstIndex one", "vkCmdDrawIndexed(cmd, 3, 1, 1, 0, 0)", body),
        ("UINT32 packet type", "indexType = $84", body),
        ("four-byte firstIndex", "firstByte = 4", body),
        ("bound index bytes", "iaddr + 8, 24", body),
        ("index guard failure", "#VTP_ERR_INDEX_GUARD", body),
        ("index post-read", "PeekL(mapped + 28)", body),
        ("one DMA present", "vtpGet(#VTP_S_CB_TEXT) <> 1", body),
        ("short display hold", "CompilerIf #VTP_INDEXED_PROOF <> 2\n    delay(#VTP_SHOW_MS)", body),
    )
    return [label for label, token, source in required if token not in source]


def packet_offsets(bcl: bytes) -> list[tuple[int, int]]:
    out = []
    for pos in range(max(0, len(bcl) - 18)):
        if bcl[pos] != 44 or bcl[pos + 9] != 32:
            continue
        base, size = struct.unpack_from("<II", bcl, pos + 1)
        if (size, bcl[pos + 10], struct.unpack_from("<II", bcl, pos + 11)) == (24, 0x84, (3, 4)):
            out.append((pos, base))
    return out


def check_report(report: bytes, bcl: bytes, index: bytes | None = None) -> list[str]:
    errors = []
    if len(report) != 256:
        return [f"report length {len(report)} != 256"]
    r = struct.unpack("<64I", report)
    expected = {0: 0x564B5452, 1: 0, 4: 0, 14: 0xFF3380B2,
                15: 0xFFFF0000, 16: 0xFF00FF00, 17: 0xFFFF0000,
                18: 0xFFFF0000, 19: 0xFFFF0000, 20: 0xFF3380B2,
                21: 0xFF3380B2, 22: 0xFF3380B2, 23: 0xFF00FF00,
                24: 0xFF00FF00, 25: 0xFF00FF00, 26: 0xFF3380B2,
                27: 0xFF3380B2, 28: 0xFF3380B2, 33: 0, 36: 0,
                44: 0, 45: 0, 47: 1, 48: 1, 57: 1, 58: 1,
                61: 10, 62: 256, 63: 0x52544B56}
    for slot, want in expected.items():
        if r[slot] != want:
            errors.append(f"slot {slot}: {r[slot]:#x} != {want:#x}")
    for before, after, label in ((29, 30, "bin"), (31, 32, "render")):
        if r[after] - r[before] != 2:
            errors.append(f"{label} job delta is not two")
    if r[38] != r[39]:
        errors.append("surface guard changed")
    if r[2] == 0 or r[3] != len(bcl):
        errors.append("BCL address/length disagree with report")
    found = packet_offsets(bcl)
    if len(found) != 1:
        errors.append(f"expected one exact adjacent UINT32 packet pair, found {len(found)}")
    else:
        _, base = found[0]
        if base % 4 or not (r[6] <= base < r[6] + r[7]):
            errors.append("index base outside aligned Vulkan window")
    if index is not None and index != struct.pack("<8I", *INDEX_WORDS):
        errors.append("index words or surrounding sentinels changed")
    return errors


def self_test(wrapper: str, body: str) -> None:
    assert not check_source(wrapper, body)
    r = [0] * REPORT_WORDS
    for slot, value in {0: 0x564B5452, 14: 0xFF3380B2, 15: 0xFFFF0000,
                        16: 0xFF00FF00, 33: 0, 36: 0, 44: 0, 45: 0,
                        47: 1, 48: 1, 57: 1, 58: 1, 61: 10, 62: 256,
                        63: 0x52544B56, 6: 0x700000, 7: 0x400000,
                        2: 0x710000, 3: 21, 29: 3, 30: 5, 31: 3, 32: 5}.items():
        r[slot] = value
    for slot in (17, 18, 19): r[slot] = 0xFFFF0000
    for slot in (20, 21, 22, 26, 27, 28): r[slot] = 0xFF3380B2
    for slot in (23, 24, 25): r[slot] = 0xFF00FF00
    r[38] = r[39] = 0xABCDEF00
    bcl = b"\0" + bytes((44,)) + struct.pack("<II", 0x720008, 24) + bytes((32, 0x84)) + struct.pack("<II", 3, 4) + b"\0"
    index = struct.pack("<8I", *INDEX_WORDS)
    good = lambda: check_report(struct.pack("<64I", *r), bcl, index)
    assert not good(), good()
    for slot, bad in ((1, 32), (4, 30), (38, 0), (57, 0), (30, 3)):
        old = r[slot]; r[slot] = bad
        assert good(), f"uncaught hostile report slot {slot}"
        r[slot] = old
    for offset, bad in ((10, 0x44), (15, 2), (5, 25)):
        mutant = bytearray(bcl); mutant[1 + offset] = bad
        assert check_report(struct.pack("<64I", *r), mutant, index), f"uncaught packet byte {offset}"
    mutant = bytearray(index); mutant[28] ^= 1
    assert check_report(struct.pack("<64I", *r), bcl, mutant)
    assert check_source(wrapper.replace("#VTP_INDEXED_PROOF = 2", "#VTP_INDEXED_PROOF = 1"), body)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--bcl", type=Path)
    parser.add_argument("--index-buffer", type=Path)
    args = parser.parse_args()
    wrapper = WRAPPER.read_text(encoding="utf-8-sig")
    body = BODY.read_text(encoding="utf-8-sig")
    errors = check_source(wrapper, body)
    if args.self_test:
        self_test(wrapper, body)
    if args.report or args.bcl:
        if not args.report or not args.bcl:
            parser.error("--report and --bcl must be supplied together")
        errors += check_report(args.report.read_bytes(), args.bcl.read_bytes(),
                               args.index_buffer.read_bytes() if args.index_buffer else None)
    if errors:
        print("indexed UINT32 proof FAIL: " + "; ".join(errors))
        return 1
    print("indexed UINT32 proof PASS" + ("; 10 hostile mutations caught" if args.self_test else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

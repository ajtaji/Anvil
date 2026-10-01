#!/usr/bin/env python3
"""Validate the fixed report returned by pi4TrueTypeCoverageNeon.pi4."""

import argparse
import pathlib
import struct

REPORT_BYTES = 128
PIXELS = 35


def expected_report_data():
    source = bytes(list(range(17)) + list(range(17)) + [0])
    converted = bytes((value * 255 + 8) // 16 for value in source)
    guards = bytes([0xA5] * 16)
    invalid = bytes([0xC3, 0xC3] + list(range(17)) + [8, 17] + [0xC3] * 3)
    return converted, guards, invalid


def check(report):
    if len(report) != REPORT_BYTES:
        raise ValueError(f"report is {len(report)} bytes, expected {REPORT_BYTES}")
    fields = struct.unpack_from("<12I", report, 0)
    magic, version, status, checks, valid_rc, invalid_rc, pixels, size = fields[:8]
    output_failures, guard_failures, invalid_changes, shape = fields[8:]
    if magic != 0x314E5454:
        raise ValueError(f"bad magic 0x{magic:08X}")
    expected_fields = (1, 0, 213, 1, 0, PIXELS, REPORT_BYTES, 0, 0, 0, (2 << 16) | 3)
    got_fields = (version, status, checks, valid_rc, invalid_rc, pixels, size,
                  output_failures, guard_failures, invalid_changes, shape)
    if got_fields != expected_fields:
        raise ValueError(f"header {got_fields}, expected {expected_fields}")

    converted, guards, invalid = expected_report_data()
    if report[48:83] != converted:
        raise ValueError("converted coverage bytes do not match the independent scalar oracle")
    if report[84:100] != guards:
        raise ValueError("a pre/post guard byte changed")
    if report[100:124] != invalid:
        raise ValueError("the rejected invalid input changed")
    if struct.unpack_from("<I", report, 124)[0] != 0x03080001:
        raise ValueError("tested-alignment marker is not 8, 0 and 1")


def self_test():
    converted, guards, invalid = expected_report_data()
    report = bytearray(REPORT_BYTES)
    struct.pack_into("<12I", report, 0, 0x314E5454, 1, 0, 213, 1, 0,
                     PIXELS, REPORT_BYTES, 0, 0, 0, (2 << 16) | 3)
    report[48:83] = converted
    report[84:100] = guards
    report[100:124] = invalid
    struct.pack_into("<I", report, 124, 0x03080001)
    check(bytes(report))
    broken = bytearray(report)
    broken[70] ^= 1
    try:
        check(bytes(broken))
    except ValueError:
        return
    raise ValueError("checker self-test did not detect a changed output byte")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", nargs="?", type=pathlib.Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("PASS: report checker accepts the oracle and rejects a mutation")
    if args.report:
        check(args.report.read_bytes())
        print("PASS: Pi 4 TrueType NEON coverage report")
    if not args.self_test and not args.report:
        parser.error("provide a report file or --self-test")


if __name__ == "__main__":
    main()

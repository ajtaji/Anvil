"""Validate defined initial-layout CLEAR and pre-execution mismatch refusal."""
import argparse
import json
import struct
from pathlib import Path
from neon_attachment_load_check import check as native_check

IDS = [600] + list(range(610, 631)) + list(range(640, 661)) + list(range(670, 691)) + list(range(700, 712))


def check_rows(report):
    assert len(report) == 16384
    count = 48 + len(IDS)
    assert struct.unpack_from('<4q', report, 10304) == (0x4e414c31, 0, count, 1)
    for n, ident in enumerate(IDS):
        expected = -20004 if ident in (619, 649, 679) else -20005 if ident in (708, 710) else 0
        row = struct.unpack_from('<3q', report, 10368 + (48 + n) * 24)
        assert row == (ident, expected, expected), (ident, row)
    assert not any(report[10368 + count * 24:])


def check(report, picture):
    check_rows(report)
    base = bytearray(report)
    struct.pack_into('<q', base, 10320, 48)
    base[10368 + 48 * 24:] = bytes(16384 - (10368 + 48 * 24))
    result = native_check(base, picture)
    result.update(clear_initial_layout_checks=len(IDS),
                  initial_layouts=['GENERAL', 'TRANSFER_SRC_OPTIMAL', 'COLOR_ATTACHMENT_OPTIMAL'],
                  pixel_comparisons=7 * 193 * 127,
                  color_attachment_final_then_load=True,
                  forbidden_final_layouts_refused=True,
                  mismatched_layout_refused_before_clear=True)
    return result


def self_test():
    report = bytearray(16384)
    struct.pack_into('<4q', report, 10304, 0x4e414c31, 0, 48 + len(IDS), 1)
    for n, ident in enumerate(IDS):
        expected = -20004 if ident in (619, 649, 679) else -20005 if ident in (708, 710) else 0
        struct.pack_into('<3q', report, 10368 + (48 + n) * 24, ident, expected, expected)
    check_rows(report)
    positions = list(range(10304, 10336, 8))
    positions += list(range(10368 + 48 * 24, 10368 + (48 + len(IDS)) * 24, 8)) + [16383]
    for pos in positions:
        damaged = bytearray(report)
        damaged[pos] ^= 1
        try:
            check_rows(damaged)
        except AssertionError:
            continue
        raise AssertionError(('accepted corruption', pos))
    return dict(scope='Synthetic checker validation, not target execution',
                rejected_corruptions=len(positions))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--self-test', action='store_true')
    p.add_argument('--report', type=Path)
    p.add_argument('--picture', type=Path)
    a = p.parse_args()
    if not a.self_test and (a.report is None or a.picture is None):
        p.error('--report and --picture are required')
    print(json.dumps(self_test() if a.self_test else check(a.report.read_bytes(), a.picture), indent=2))

"""Check public clear-array acceptance, refusal/retry and full attachment pixels."""
import struct
import argparse
import json
from pathlib import Path
from neon_attachment_load_check import check as native_check


def check_rows(report):
    assert len(report) == 16384
    q = lambda o: struct.unpack_from('<q', report, o)[0]
    ids = [500, 501, 502, 503, 505, 506, 507, 509, 510, 511, 512, 513, 514]
    assert [q(o) for o in range(10304, 10336, 8)] == [0x4e414c31, 0, 61, 1]
    for n, ident in enumerate(ids):
        expected = -20001 if ident in (502, 506) else 0
        row = struct.unpack_from('<3q', report, 10368 + (48 + n) * 24)
        assert row == (ident, expected, expected), (ident, row)
    assert not any(report[10368 + 61 * 24:])


def check(report, picture):
    check_rows(report)
    base = bytearray(report)
    struct.pack_into('<q', base, 10320, 48)
    base[10368 + 48 * 24:] = bytes(16384 - (10368 + 48 * 24))
    result = native_check(base, picture)
    result.update(clear_value_count_checks=13, surplus_clear_values=True,
                  clear_pixels_checked=193 * 127, missing_clear_refused=True)
    return result


def self_test():
    report = bytearray(16384)
    for offset, value in zip(range(10304, 10336, 8), [0x4e414c31, 0, 61, 1]):
        struct.pack_into('<q', report, offset, value)
    ids = [500, 501, 502, 503, 505, 506, 507, 509, 510, 511, 512, 513, 514]
    for n, ident in enumerate(ids):
        value = -20001 if ident in (502, 506) else 0
        struct.pack_into('<3q', report, 10368 + (48 + n) * 24, ident, value, value)
    check_rows(report)
    positions = list(range(10304, 10336, 8))
    positions += list(range(10368 + 48 * 24, 10368 + 61 * 24, 8)) + [16383]
    for pos in positions:
        damaged = bytearray(report)
        damaged[pos] ^= 1
        try:
            check_rows(damaged)
        except AssertionError:
            continue
        raise AssertionError(('accepted corruption', pos))
    return dict(scope='Synthetic report-checker test only; no board execution',
                rejected_corruptions=len(positions))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--picture', type=Path)
    args = parser.parse_args()
    if args.self_test:
        result = self_test()
    else:
        if args.report is None or args.picture is None:
            parser.error('--report and --picture are required')
        result = check(args.report.read_bytes(), args.picture)
    print(json.dumps(result, indent=2))

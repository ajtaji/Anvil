"""Check the returned report from neon_dma_copy_compare.pi4.

The payload checks every copied word and the outer destination guards. Host
checks validate completion, the measured cache state and the padded-row cases;
this is a DMA comparison, not a complete application frame-rate acceptance.
"""
import argparse
import json
from pathlib import Path
import statistics
import struct


def check(data, *, padded=True):
    if len(data) != 512:
        raise ValueError('Expected the complete 512-byte report')
    q = struct.unpack('<64Q', data)
    if q[0] != 0x4350444D or q[1] != 54000000 or q[7] != 0x454E4421:
        raise ValueError('Incomplete report or unexpected counter clock')
    if (q[2], q[27], q[28]) != (0, 0x1005, 0):
        raise ValueError('Expected cached execution and restored entry state')
    if q[3] != 0 or q[4] != 8 or q[5] != 1 or q[6] != 4096000:
        raise ValueError('Unexpected DMA channel, burst, quiescence or extent')
    if q[24:26] != (0, 0):
        raise ValueError('Full-frame data mismatch')
    if padded and (q[32:37] != (0, 0, 0, 0, 0) or q[37] != 0x50414433):
        raise ValueError('Padded-row or invalid-geometry checks failed')
    samples = [[x * 1e6 / q[1] for x in q[i:i+4]] for i in (8, 16)]
    if not all(0 < x < 100000 for row in samples for x in row):
        raise ValueError('Missing or implausible timing sample')
    return dict(rectangular_us=samples[0], linear_us=samples[1],
                rectangular_warm_median_us=statistics.median(samples[0][1:]),
                linear_warm_median_us=statistics.median(samples[1][1:]),
                verified_bytes_per_method=q[6], padded_cases=3 if padded else 0,
                invalid_geometry_cases=2 if padded else 0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.report.read_bytes()), indent=2))

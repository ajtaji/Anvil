#!/usr/bin/env python3
"""Check the physical Pi4 atlas transaction's report and full GPU pixels."""
import argparse
import json
from pathlib import Path
import struct


def verify(report, pixels, injected=False):
    assert len(report) == 8192, 'The native report must be8192 bytes.'
    assert struct.unpack_from('<I', report)[0] == 0x4157564E, 'The report magic is wrong.'
    assert struct.unpack_from('<I', report, 4)[0] == 0, 'The widget setup did not succeed.'
    assert struct.unpack_from('<I', report, 51 * 4)[0] == 0, 'An unexpected Vulkan validation fault occurred.'
    q = struct.unpack_from('<8q', report, 0x1000)
    assert q[0] == 0, f'The native transaction stopped with code{q[0]}.'
    assert q[1] == -21203, 'The capacity refusal was lost.'
    assert q[2] == 0, 'The old atlas was modified during a refused replacement.'
    assert q[3] == 3 and q[6] > 0 and q[7] == 2097152, 'The complete replacement test did not execute.'
    if injected:
        x = struct.unpack_from('<7q', report, 0x1040)
        assert x[0] == -4 and x[1] != 0 and x[2] == q[4] + 1 and x[3] == 0, 'Uncertain work did not retain both generations.'
        assert x[4:] == (1, 0, 0) and q[5] == 1, 'Device-idle retirement or final caller teardown leaked memory.'
    else:
        assert q[4] == q[5], 'Repeated replacement leaked a memory allocation.'
    assert len(pixels) == 49152, 'All three complete64x64 GPU captures are required.'
    font = report[0x1800:0x1820]
    assert font[16:] == bytes(x ^ 255 for x in font[:16]), 'The two font inputs are not complementary.'
    for frame in range(3):
        actual = pixels[frame * 16384:(frame + 1) * 16384]
        glyph = font[:16] if frame == 1 else font[16:]
        expected = bytearray(16384)
        for y in range(64):
            for x in range(64):
                # Clear(0.1,0.2,0.3,1), rounded UNORM8, plus opaque draws.
                colour = 0xFF1A334D
                if x < 8 and y < 8:
                    colour = 0xFFFFFFFF
                if 32 <= x < 40 and 8 <= y < 16:
                    colour = 0xFF00FF00
                if 8 <= x < 16 and 8 <= y < 24 and glyph[y - 8] & (0x80 >> (x - 8)):
                    colour = 0xFFFFFFFF
                struct.pack_into('<I', expected, (y * 64 + x) * 4, colour)
        assert actual == expected, f'Frame{frame} differs from the independent complete pixel oracle.'
    assert pixels[:16384] == pixels[32768:], 'The repeated font generation changed its pixels.'
    return dict(swaps=3, preserved_atlas_bytes=q[7], exact_gpu_bytes=49152, uncertain_injection=injected)


def self_test(report, pixels, injected):
    mutations = [(0x1000, 1), (0x1008, 0), (0x1010, 1), (0x1018, 0), (4, 1), (51 * 4, 1)]
    rejected = 0
    for offset, value in mutations:
        bad = bytearray(report)
        struct.pack_into('<I', bad, offset, value)
        try:
            verify(bad, pixels, injected)
        except AssertionError:
            rejected += 1
        else:
            raise AssertionError(f'The checker accepted a bad report at{offset:x}.')
    for offset in (0, 16384 + 12 * 256 + 8 * 4, 49151):
        bad = bytearray(pixels)
        bad[offset] ^= 1
        try:
            verify(report, bad, injected)
        except AssertionError:
            rejected += 1
        else:
            raise AssertionError(f'The checker accepted a changed pixel at{offset:x}.')
    return rejected


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--report', type=Path, required=True)
    ap.add_argument('--pixels', type=Path, required=True)
    ap.add_argument('--injected-uncertain', action='store_true')
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()
    report = args.report.read_bytes()
    pixels = args.pixels.read_bytes()
    result = verify(report, pixels, args.injected_uncertain)
    if args.self_test:
        result['rejected_mutations'] = self_test(report, pixels, args.injected_uncertain)
    print('neon atlas generation proof PASS', json.dumps(result))

"""Exact native text crop oracle, independent of renderer run decomposition."""
def check(blob):
    assert len(blob) == 65568, 'Native text capture length'
    assert blob[:16] == blob[-16:] == b'\xa5' * 16, 'Native text capture guards'
    black = bytes((0, 0, 0, 255))
    white = bytes((255, 255, 255, 255))
    glyphs = ((0xF0, 0xF0, 0xA0, 0xA0), (0xCC,) * 4)
    for kind in range(2):
        for mode in range(4):
            expected = bytearray(black * (64 * 32))
            for cell, glyph in enumerate((0, 1, 0)):
                for row, bits in enumerate(glyphs[glyph]):
                    for col in range(8):
                        x, y = 10 + cell * 8 + col, 10 + row
                        visible = mode != 3 or (12 <= x < 30 and 11 <= y < 13)
                        if visible and bits & (128 >> col):
                            offset = (y * 64 + x) * 4
                            expected[offset:offset + 4] = white
            start = 16 + (kind * 4 + mode) * 8192
            actual = blob[start:start + 8192]
            if actual != expected:
                differences = [i for i, (a, b) in enumerate(zip(actual, expected)) if a != b]
                raise AssertionError(('Native text pixels', kind, mode, len(differences), differences[:16]))
    return dict(frames=8, exact_bytes=65536, modes=['ordinary', 'exact_vertices', 'exact_records', 'clipped'])

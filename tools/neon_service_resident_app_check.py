#!/usr/bin/env python3
"""Independent returned report and physical display checks for the service app."""
import argparse, json, struct
from pathlib import Path
from PIL import Image

def check(report, picture):
    assert len(report) == 4096, 'report extent'
    q = struct.unpack('<512q', report)
    assert q[:6] == (0x4E534131, 1, 0, 22, 1, 8), q[:6]
    context, width, height, font, final_context, ready = q[6:12]
    assert context > 0 and (width, height) == (1280, 800)
    assert font == (context << 16) | 1
    assert (final_context, ready) == (context, 1), 'the app must leave its live owner for kernel cleanup'
    positive = {3, 4, 5, 6, 11, 12}
    for index in range(1, 23):
        actual, expected = struct.unpack_from('<2q', report, 128 + index * 16)
        want = int(index in positive)
        assert (actual, expected) == (want, want), (index, actual, expected, want)
    im = Image.open(picture).convert('RGB')
    assert im.size == (1280, 800), im.size
    probes = [(10, 10, (5, 10, 20)), (1000, 600, (5, 10, 20)),
              (520, 160, (0, 191, 128)), (620, 190, (0, 191, 128)),
              (570, 300, (230, 102, 26)), (60, 140, (102, 102, 102)),
              (70, 150, (38, 51, 153))]
    for x, y, colour in probes:
        got = im.getpixel((x, y))
        assert max(abs(a - b) for a, b in zip(got, colour)) <= 1, (x, y, got, colour)
    title_ink = sum(1 for y in range(60, 110) for x in range(60, 650)
                    if (lambda c: c[0] > 180 and c[1] > 130 and c[2] < 100)(im.getpixel((x, y))))
    button_ink = sum(1 for y in range(150, 195) for x in range(180, 300)
                     if min(im.getpixel((x, y))) > 180)
    assert title_ink > 200 and button_ink > 50, (title_ink, button_ink)
    return dict(passed=True, assertions=22, display_probes=len(probes), title_ink=title_ink,
                button_ink=button_ink, context=context, font=font,
                scope='Resident Vulkan, confirmed physical display snapshot; kernel cleanup checked separately')

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('report', type=Path)
    ap.add_argument('picture', type=Path)
    a = ap.parse_args()
    print(json.dumps(check(a.report.read_bytes(), a.picture), indent=2))

if __name__ == '__main__':
    main()

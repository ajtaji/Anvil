"""Check the 256-byte returning Pi 4 particle proof report."""

import struct
import sys
from pathlib import Path


def rgba_word(word):
    return ((word >> 16) & 255, (word >> 8) & 255, word & 255, (word >> 24) & 255)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: vulkanNeonParticlePaletteProofCheck.py REPORT.BIN")
        return 2
    payload = Path(sys.argv[1]).read_bytes()
    if len(payload) != 256:
        raise ValueError(f"expected 256 report bytes, got {len(payload)}")
    words = struct.unpack("<64I", payload)
    signed = lambda n: struct.unpack("<i", struct.pack("<I", n))[0]
    assert words[0] == 0x4D42524E and words[15] == words[0]
    assert words[1] == 0 and words[2] == 12, (words[1], words[2])
    assert (words[4], words[5]) == (1, 12)
    assert (words[6], words[7]) == (1, 60000)
    assert signed(words[19]) == -21201
    assert words[9] == 0xFFFF0000 and words[12] == 0xFF000000
    red, green, blue, alpha = rgba_word(words[10])
    assert 125 <= red <= 129 and 125 <= green <= 129 and blue == 0
    assert 188 <= alpha <= 193
    red, green, blue, alpha = rgba_word(words[11])
    assert red == 0 and 125 <= green <= 129 and blue == 0
    assert 188 <= alpha <= 193
    assert words[8] == 0xFF000000
    assert (words[20], words[21], words[22]) == (
        0xFFF70000, 0xFFC80000, 0xFF470000
    ), tuple(hex(words[i]) for i in (20, 21, 22))
    assert words[13] == 0, f"native Vulkan faults: {words[13]}"
    timings = words[23:26]
    assert all(0 < value < 10_000_000 for value in timings), timings
    hundred = words[26:29]
    thousand = words[29:32]
    assert all(0 < value < 10_000_000 for value in hundred + thousand)
    assert (words[32], words[33]) == (1, 600)
    assert (words[34], words[35]) == (1, 6000)
    assert (signed(words[36]), words[37], words[38], words[39]) == (
        -21203, 3, 1, 0x5A36C07D
    ), tuple(hex(words[i]) for i in range(36, 40))
    assert (words[40], words[41], words[42], words[43]) == (
        0xFFFF00FF, 0xFF000000, 0xFF0000FF, 0xFF000000
    ), tuple(hex(words[i]) for i in range(40, 44))
    assert (words[44], words[45]) == (1, 1)
    print(
        "particle palette proof: 10,000 particles, one draw, ordered alpha, repeat, "
        "lazy allocation, rotated/camera pixels, and exact fan-boundary refusal pass; "
        f"10k prepare/draw/end {timings[0]}/{timings[1]}/{timings[2]} us; "
        f"100 {hundred[0]}/{hundred[1]}/{hundred[2]} us; "
        f"1k {thousand[0]}/{thousand[1]}/{thousand[2]} us"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

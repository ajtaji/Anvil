"""Check a 512-byte matched 800x800 CSD End-split report."""

import argparse
from pathlib import Path
import statistics
import struct


def check(data: bytes) -> str:
    if len(data) != 512:
        raise ValueError(f"expected 512 report bytes, got {len(data)}")
    words = struct.unpack("<128I", data)

    def expect(index: int, wanted: int) -> None:
        if words[index] != wanted:
            raise ValueError(f"word {index} = 0x{words[index]:08X}, expected 0x{wanted:08X}")

    for index, wanted in {
        0: 0x474D504E, 1: 0, 2: 4, 3: 0, 5: 3200, 6: 10000,
        7: 3, 8: 4, 11: 0, 12: 0, 13: 0,
        25: 0xFF000000, 26: 0xFF00FF00, 27: 0xFF00FF00,
        28: 0xFF00FF00, 29: 0xFF00FF00, 30: 0,
        31: 4, 32: 4, 33: 0, 46: 0x063E8000, 47: 0x01000000,
        52: 0, 53: 0, 54: 1, 55: 0, 56: 0,
        58: 0, 59: 0, 60: 0, 63: 0x4E504D47,
        64: 0x454E4453, 65: 1, 66: 3, 127: 0x4E504D47,
    }.items():
        expect(index, wanted)
    if words[4] == 0 or words[48] == 0 or words[49] == 0:
        raise ValueError("framebuffer or external vertex buffer missing")
    for sample in range(3):
        pre = words[67 + sample]
        reset = words[70 + sample]
        submit = words[73 + sample]
        fence = words[76 + sample]
        post = words[79 + sample]
        clean = words[82 + sample]
        binning = words[85 + sample]
        rendering = words[88 + sample]
        inner = words[91 + sample]
        outer = words[22 + sample]
        expect(97 + sample, 1)
        if not all(0 <= x < 10_000_000 for x in (pre, reset, submit, fence, post, clean, binning, rendering, inner, outer)):
            raise ValueError(f"sample {sample}: timing out of range")
        if not (pre > 0 and submit > 0 and inner > 0 and outer > 0 and binning + rendering > 0):
            raise ValueError(f"sample {sample}: missing End timing or backend job")
        if pre + reset + submit + fence + post > inner + 100:
            raise ValueError(f"sample {sample}: phase times exceed Chrome End")
        if inner > outer + 100:
            raise ValueError(f"sample {sample}: Chrome End exceeds outer End timer")
    expect(109, 1)
    if words[102] == 0 or words[108] == 0 or words[106] + words[107] == 0:
        raise ValueError("warm-up End split missing")
    if sum(words[100:105]) > words[108] + 100:
        raise ValueError("warm-up phase times exceed Chrome End")
    median = lambda start: int(statistics.median(words[start:start + 3]))
    values = {
        "end_us": median(91),
        "pre_submit_us": median(67),
        "fence_reset_us": median(70),
        "queue_submit_us": median(73),
        "fence_wait_us": median(76),
        "post_submit_us": median(79),
        "nested_clean_us": median(82),
        "nested_bin_us": median(85),
        "nested_render_us": median(88),
    }
    return "PASS: matched 800x800 CSD End split; " + ", ".join(f"{name}={value}" for name, value in values.items())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    print(check(args.report.read_bytes()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

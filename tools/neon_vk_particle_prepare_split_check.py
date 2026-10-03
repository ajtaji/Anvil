"""Check a 512-byte returning particle Prepare split report."""

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

    expect(0, 0x474D504E)  # NPMG: matched CSD base report
    expect(1, 0)           # returned with success
    expect(2, 4)           # finish stage
    expect(6, 10000)
    expect(7, 3)
    expect(8, 4)           # one warm-up, three samples
    expect(30, 0)          # 20k pixel probes
    expect(31, 4)
    expect(32, 4)
    expect(33, 0)
    expect(55, 0)
    expect(56, 0)
    expect(58, 0)
    expect(59, 0)
    expect(60, 0)
    expect(63, 0x4E504D47)
    expect(64, 0x50534D50)  # split-report magic
    expect(65, 1)
    expect(66, 3)
    expect(82, 1)           # warm-up first upload only
    expect(83, 3)           # measured static-color reuse
    expect(84, 1)
    expect(85, 1)
    expect(127, 0x4E504D47)
    if not all(words[index] > 0 for index in (86, 88, 89, 90, 91)):
        raise ValueError("warm-up upload or timing data missing")
    if words[86] + words[87] + words[88] + words[89] > words[90] + 100:
        raise ValueError("warm-up phase timers exceed Chrome Prepare")
    if words[90] > words[91] + 100:
        raise ValueError("warm-up Chrome Prepare exceeds producer Prepare")
    for sample in range(3):
        validation = words[67 + sample]
        idle = words[70 + sample]
        copy = words[73 + sample]
        upload = words[76 + sample]
        total = words[79 + sample]
        outer = words[40 + sample]
        if validation == 0 or copy == 0 or total == 0 or outer == 0:
            raise ValueError(f"sample {sample}: missing timing data")
        if upload != 0:
            raise ValueError(f"sample {sample}: static colors unexpectedly uploaded")
        if validation + idle + copy > total + 100:
            raise ValueError(f"sample {sample}: phase timers exceed Chrome Prepare")
        if total > outer + 100:
            raise ValueError(f"sample {sample}: Chrome Prepare exceeds producer Prepare")
    medians = {
        "validation_us": int(statistics.median(words[67:70])),
        "idle_us": int(statistics.median(words[70:73])),
        "copy_us": int(statistics.median(words[73:76])),
        "upload_us": int(statistics.median(words[76:79])),
        "chrome_prepare_us": int(statistics.median(words[79:82])),
        "producer_palette_us": int(statistics.median(words[40:43])),
    }
    medians["warmup_upload_us"] = words[89]
    return "PASS: 10k static-color split; " + ", ".join(f"{k}={v}" for k, v in medians.items())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    print(check(args.report.read_bytes()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

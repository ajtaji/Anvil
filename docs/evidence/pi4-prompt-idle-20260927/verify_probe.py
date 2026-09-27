#!/usr/bin/env python3
"""Check the Pi 4 WFE trace and both boot-image hashes."""
import hashlib
import json
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent


def check_hash(name: str, expected: str) -> None:
    actual = hashlib.sha256((HERE / name).read_bytes()).hexdigest()
    assert actual == expected, (name, actual)


def main() -> None:
    check_hash("outgoing-build210-KERNEL8.IMG",
               "9c5518a3112bd20f0a5dfeea415f0885c5d92a1a3e6431f6485166f4115d3381")
    check_hash("anvil-build221.img",
               "65feea85f6205781a8d10b78a811616253488b53d018ce174903329b63d0fd8e")
    check_hash("anvil-build222.img",
               "e5eab20873ffcf3bb7de0d314243b9253c404c701d5a7c53d3ce3b497cdc0489")
    check_hash("anvil-build223.img",
               "9db6861b6cd644e0f1f6b9b1d8237da663950bbf4180e4b9181fb04e6be7f344")
    check_hash("pi4PromptWfeBit13.img.pmf",
               "54bf9a9c7ddde2cf1221b88e4109d3a6d68c3ad919fef1c5d82f0d93085d6670")
    check_hash("pi4PromptWfeBit15.img.pmf",
               "3ab973995e636202d809c1e24a97ebd437dcdba4ab5313fb0e0e44e72a09d8f6")
    for name, seq, period in (("pi4-prompt-wfe-measured", 110, 16384),
                              ("pi4-prompt-wfe-bit15", 113, 65536)):
        meta = json.loads((HERE / f"{name}.json").read_text())
        assert meta["x0"] == "0000000000000000"
        assert meta["shot_header"]["seq"] == seq
        magic, minimum, maximum, total, actual_period = struct.unpack_from(
            "<5I", (HERE / f"{name}.trace.bin").read_bytes())
        assert magic == 0x31454657
        assert 0 < minimum <= maximum <= 108001
        assert 32 * minimum <= total <= 32 * maximum
        assert actual_period == period
        print(f"{name}: 32 WFE wakes, {minimum}..{maximum} ticks, "
              f"mean {total / 32:.1f} ticks")
    print("PASS: build-210 backup and build-221/222/223 image hashes match")


if __name__ == "__main__":
    main()

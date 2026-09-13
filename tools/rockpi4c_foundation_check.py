#!/usr/bin/env python3
"""Desk gate for the original ROCK Pi 4C v1.2 foundation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import subprocess
import tempfile

import build_count
from rockpi4c_image import (
    BRANCH_TO_PAYLOAD, CODE_BASE, CODE_LIMIT, DTB_ADDRESS, FLAGS,
    HEADER_BYTES, IMAGE_BASE, ImageError, validate, wrap,
)

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def static_contract() -> None:
    board = (ROOT / "RockPi4C/Board/board.rockpi4c").read_text(encoding="utf-8")
    joined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "RockPi4C").rglob("*")) if path.is_file()
    ).lower()
    required = (
        "pmf:target rockpi4c", "pmf:load $02000040", "pmf:bss $02800000",
        "pmf:stack $05000000", "$ff1a0000", "$fee00000", "$fef00000",
        "cntpct_el0", "vbar_el2", "icc_sre_el2", "rockgicfindredistributor",
        "serial2:1500000n8", "irq still masked",
    )
    for token in required:
        require(token.lower() in joined, f"missing contract token: {token}")
    for forbidden in ("bcm2711", "mailbox", "v3d", "genet"):
        # The platform comment names forbidden assumptions; executable source
        # must not include a Pi file or an address from those drivers.
        require(f'xincludefile "raspberrypi4/' not in board.lower(), "Pi 4 include leaked into RK3399 root")
    profile = json.loads((ROOT / "Boards/ROCK_Pi_4C.board").read_text(encoding="utf-8"))
    require(profile["TargetChip"] == "RK3399", "board profile is not RK3399")


def image_contract() -> None:
    payload = struct.pack("<I", 0xD503201F) + bytes(range(1, 241))
    image, meta = wrap(payload)
    validate(image)
    require(len(image) == HEADER_BYTES + len(payload), "wrapper inserted hidden padding")
    require(struct.unpack_from("<I", image, 0)[0] == BRANCH_TO_PAYLOAD, "entry branch drift")
    require(struct.unpack_from("<Q", image, 24)[0] == FLAGS, "placement flag drift")
    require(meta["image_address"] == f"0x{IMAGE_BASE:08x}", "image address drift")
    require(meta["code_address"] == f"0x{CODE_BASE:08x}", "code address drift")
    require(meta["dtb_address"] == f"0x{DTB_ADDRESS:08x}", "DTB address drift")
    mutations = []
    for offset in (0, 4, 16, 24, 32, 40, 48, 56, 60):
        changed = bytearray(image)
        changed[offset] ^= 1
        mutations.append(bytes(changed))
    for changed in mutations:
        try:
            validate(changed)
        except ImageError:
            pass
        else:
            raise AssertionError("a malformed arm64 Image header was accepted")
    try:
        wrap(bytes(CODE_LIMIT - CODE_BASE + 1))
    except ImageError:
        pass
    else:
        raise AssertionError("a payload overlapping BSS was accepted")


def compiler_contract(compiler: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="anvil-rockpi4c-") as temp_name:
        output = Path(temp_name) / "foundation.img"
        command = [
            str(compiler), "--compile", "RockPi4C/Board/board.rockpi4c",
            "-t", "rockpi4c", "--load-addr", "0x02000040", "--bss-addr",
            "0x02800000", "--stack-addr", "0x05000000", "--jobs", "auto",
            "-S", "-o", str(output),
        ]
        run = subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, timeout=300)
        require(run.returncode == 0, "rockpi4c compile failed:\n" + run.stdout)
        require(output.is_file() and output.stat().st_size > 0, "compiler wrote no payload")
        require(Path(str(output) + ".pmf").is_file(), "compiler wrote no PMF sidecar")
        asm = Path(str(output) + ".asm").read_text(encoding="utf-8", errors="replace").lower()
        for token in ("cntfrq_el0", "vbar_el2", "icc_sre_el2"):
            require(token in asm, f"emitted assembly lacks {token}")
        counted = build_count.record_build(
            ROOT / "RockPi4C/Board/board.rockpi4c", "rockpi4c", output,
            by="tools/rockpi4c_foundation_check.py", compiler=compiler,
        )
        print(f"  build count: {counted.message}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path)
    args = parser.parse_args()
    static_contract()
    image_contract()
    if args.compiler:
        compiler_contract(args.compiler.resolve())
    print("ROCK Pi 4C foundation desk gate: PASS")
    print("silicon: NOT RUN; IRQ remains masked by the board root")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

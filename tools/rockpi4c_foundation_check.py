#!/usr/bin/env python3
"""Desk gate for the original ROCK Pi 4C v1.2 foundation."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

import build_count
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler
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
        "pmf:target rockpi4c", "pmf:load $00041000", "pmf:bss $02800000",
        "pmf:stack $05000000", "$ff1a0000", "$fee00000", "$fef00000",
        "rock_image_base = $00040000", "rock_dtb_expected = $001c0000",
        "rock_anvil_limit = $00240000", "rock_dtb_max_bytes = $00080000",
        "cntpct_el0", "vbar_el3", "sctlr_el3", "currentel",
        "rock_timer_frequency_expected = 24000000", "global_rock_entry_sp",
        "rock_directsd_gic_enabled = 0", "rock_directsd_display_enabled = 0",
        "rock_directsd_hdmi_enabled = 1", "rock_directsd_hdmi_auto = 0",
        "serial2:1500000n8", "type hdmi; vopb; auto off",
    )
    for token in required:
        require(token.lower() in joined, f"missing contract token: {token}")
    require("rockrangesoverlap(rock_dtb,total,#rock_image_base" not in joined,
            "embedded DTB is still rejected as overlap with its Anvil component")
    main = board[board.index("Procedure Main()"):]
    require(main.index("str x0, [x9]") < main.index("RockCaptureEnvironment()"),
            "incoming firmware x0 is not preserved before entry validation")
    require(main.index("RockCaptureEnvironment()") < main.index("RockTimerInit()"),
            "execution level is not captured before timer setup")
    require(main.index("RockCaptureSctlrEl3()") < main.index("RockTimerInit()"),
            "EL3 MMU/cache state is not checked before timer setup")
    require(main.index("If (rock_entry_sp & 15) <> 0") < main.index("RockTimerInit()"),
            "entry stack alignment is not checked before timer setup")
    require("RockGicInitTimerFoundation()" in main and
            "#ROCK_DIRECTSD_GIC_ENABLED <> 0" in main,
            "GIC setup is not behind the explicit direct-SD capability")
    require("#ROCK_DIRECTSD_DISPLAY_ENABLED <> 0" in main,
            "display setup is not behind the explicit direct-SD capability")
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


def compiler_contract(compiler: Path, output_path: Path | None = None) -> None:
    with tempfile.TemporaryDirectory(prefix="anvil-rockpi4c-") as temp_name:
        temp = Path(temp_name)
        output = output_path.resolve() if output_path else temp / "foundation.img"
        output.parent.mkdir(parents=True, exist_ok=True)
        staged_compiler = temp / compiler.name
        shutil.copy2(compiler, staged_compiler)
        shutil.copytree(ROOT / "Boards", temp / "Boards")
        command = [
            str(staged_compiler), "--compile", "RockPi4C/Board/board.rockpi4c",
            "-t", "rockpi4c", "--load-addr", "0x00041000", "--bss-addr",
            "0x02800000", "--stack-addr", "0x05000000",
            "-S", "-o", str(output),
        ]
        run = subprocess.run(
            command, cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=300,
        )
        require(run.returncode == 0, "rockpi4c compile failed:\n" + run.stdout)
        require(output.is_file() and output.stat().st_size > 0, "compiler wrote no payload")
        require(Path(str(output) + ".pmf").is_file(), "compiler wrote no PMF sidecar")
        asm = Path(str(output) + ".asm").read_text(encoding="utf-8", errors="replace").lower()
        for token in ("cntfrq_el0", "vbar_el3", "sctlr_el3"):
            require(token in asm, f"emitted assembly lacks {token}")
        counted = build_count.record_build(
            ROOT / "RockPi4C/Board/board.rockpi4c", "rockpi4c", output,
            by="tools/rockpi4c_foundation_check.py", compiler=compiler,
        )
        print(f"  build count: {counted.message}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path)
    parser.add_argument("--output", type=Path,
                        help="keep the successful flat Anvil payload at this path")
    args = parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    static_contract()
    image_contract()
    if args.compiler:
        compiler_contract(args.compiler.resolve(), args.output)
    print("ROCK Pi 4C foundation desk gate: PASS")
    print("silicon: NOT RUN; IRQ remains masked by the board root")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Structural gate for the Pi 4's early V3D boot activation.

This checks source ownership and order only. It does not compile, execute, or
make a GPU/cache/hardware-performance claim.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "RaspberryPi4/Board/board.pi4"

# Main()'s skeleton, in the order it must keep. The screen is now brought up
# BEFORE the slow half of the boot and corrected to the stored geometry after
# it (tools/boot_display_order_check.py owns that contract); what this file
# owns is where the GPU takes over relative to the rest.
REQUIRED = (
    "ScreenUp()",
    "TouchBoot()",
    "I2cTraceEnable(0)",
    "BootConfigUp()",
    "ScreenApplyStoredGeometry()",
    "V3dConAutoStart()",
    "ScreenEarlyLogFinish()",
    "GenetSetProgressHook(@ScreenServiceTick)",
    "NetWaitSetProgressHook(@ScreenServiceTick)",
    "WifiSetProgressHook(@ScreenServiceTick)",
    "BootNetUp()",
    "BootWait()",
    "BootFileWait()",
)


def main_body(text: str) -> str:
    found = re.search(r"(?ms)^Procedure Main\(\)\n(.*?)^EndProcedure", text)
    if not found:
        raise AssertionError("Main procedure not found")
    return found.group(1)


def validate(text: str) -> None:
    body = main_body(text)
    for token in REQUIRED:
        pattern = rf"(?m)^  {re.escape(token)}$"
        if len(re.findall(pattern, body)) != 1:
            raise AssertionError(f"expected exactly one {token}")
    positions = [re.search(rf"(?m)^  {re.escape(token)}$", body).start()
                 for token in REQUIRED]
    if positions != sorted(positions):
        raise AssertionError("early V3D dependency/order contract changed")
    call = body.index("V3dConAutoStart()")
    before = body.rfind("CompilerIf #ANVIL_V3D_CONSOLE = 1", 0, call)
    after = body.find("CompilerEndIf", call)
    if before < 0 or after < 0:
        raise AssertionError("V3D activation lost its compile-time fallback guard")


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise AssertionError("mutation anchor is not unique: " + old)
    return text.replace(old, new, 1)


def moved(body: str, anchor: str, before: bool = False) -> str:
    body = replace_once(body, "  V3dConAutoStart()\n", "")
    insertion = "  V3dConAutoStart()\n" + anchor if before else anchor + "  V3dConAutoStart()\n"
    return replace_once(body, anchor, insertion)


MUTATIONS = (
    # The GPU must not take the console over with the long, hang-prone half
    # of the boot already running: its progress would be painted by a
    # renderer whose activation is the thing being timed.
    ("activation after the network", lambda b: moved(b, "  BootNetUp()\n")),
    # Touch shares the I2C bus the panel came up on and must be finished
    # with before anything else claims the surface.
    ("touch after activation", lambda b: moved(b, "  TouchBoot()\n", True)),
    # THE ONE THIS REORDER ADDED. A geometry correction rebuilds the grid
    # and re-installs the CPU/DMA renderer, so a GPU that took ownership
    # first would be detached again one line later - and the console would
    # spend the whole of the network bring-up on the tier the activation
    # was supposed to leave behind.
    ("activation before the stored geometry is applied",
     lambda b: moved(b, "  ScreenApplyStoredGeometry()\n", True)),
    ("log drained before activation", lambda b: moved(b, "  ScreenEarlyLogFinish()\n")),
    ("missing activation", lambda b: replace_once(b, "  V3dConAutoStart()\n", "")),
    ("duplicate activation", lambda b: replace_once(
        b, "  V3dConAutoStart()\n", "  V3dConAutoStart()\n  V3dConAutoStart()\n")),
    ("missing compile guard", lambda b: replace_once(
        b, "  CompilerIf #ANVIL_V3D_CONSOLE = 1\n", "")),
)


def main() -> int:
    source = SOURCE.read_text(encoding="utf-8")
    validate(source)
    for label, transform in MUTATIONS:
        body = main_body(source)
        changed = transform(body)
        mutant = source.replace(body, changed, 1)
        try:
            validate(mutant)
        except AssertionError:
            print("  rejected structural mutation: " + label)
        else:
            raise AssertionError("structural mutation survived: " + label)
    print(f"boot_v3d_order_check: PASS - exact boot order and {len(MUTATIONS)} mutations")
    print("  structural source proof only; no compile, execution, GPU, cache or timing claim")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

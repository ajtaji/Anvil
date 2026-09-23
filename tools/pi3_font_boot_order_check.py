#!/usr/bin/env python3
"""Focused source-flow regression for Pi 3 initial TrueType boot ordering."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUBS = ROOT / "RaspberryPi3" / "Board" / "pi3stubs.pi3"


def procedure(source: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^Procedure(?:\.[A-Za-z]+)?\s+{re.escape(name)}\s*\(.*?^EndProcedure\s*$",
        source,
    )
    if not match:
        raise SystemExit(f"Pi 3 font boot order: missing production procedure {name}")
    return match.group(0)


def require(condition: bool, label: str) -> None:
    if not condition:
        raise SystemExit(f"Pi 3 font boot order: FAIL {label}")


def main() -> int:
    source = STUBS.read_text(encoding="utf-8")
    drain = procedure(source, "Pi3ScreenDrain")
    font = procedure(source, "Pi3ScreenFontBootTick")
    banner = procedure(source, "Pi3ScreenBannerStep")
    mirror = procedure(source, "Pi3ScreenMirrorByte")

    early = drain.index("ElseIf pi3_screen_initialized=0")
    font_call = drain.index("Pi3ScreenFontServiceTick()", early)
    ready_guard = drain.index("If pi3_screen_font_boot<>2", font_call)
    banner_call = drain.index("Pi3ScreenBannerStep()", ready_guard)
    require(early < font_call < ready_guard < banner_call,
            "initial clear runs font service and waits for terminal choice before banner")

    require("initialPreload=Bool(pi3_screen_initialized=0 And pi3_screen_init_state=2 And pi3_screen_banner_phase=0)" in font,
            "preload is restricted to the cleared, not-yet-painted initial banner")
    bypass = font.index("If initialPreload=0")
    queue_guard = font.index("pi3_screen_tail<>pi3_screen_head", bypass)
    require(bypass < queue_guard,
            "initial boot text may stay queued while normal redraws still require an empty ring")

    ready = font.index("pi3_screen_ttf_ready_us<0")
    initial_return = font.index("If initialPreload<>0", ready)
    reset = font.index("pi3_screen_initialized=0 : pi3_screen_init_state=0", initial_return)
    synthetic = font.index('"TrueType active; pmf> "', reset)
    require(ready < initial_return < reset < synthetic,
            "initial success records readiness and returns before legacy redraw/prompt replay")

    terminal_errors = (
        "If loadRc=0 And SettingsLastError()<>12",
        "If *configured<>0 And SettingsLength(\"font.default\")=6",
        "If pi3_screen_font_path_bytes<1 Or pi3_screen_font_path_bytes>=1024",
        "If HwStorageUp()=0 Or HwFileOpen",
        "If n<1 Or n>#PI3_SCREEN_FONT_MAX_BYTES",
        "If got<>take",
        "If AnvilTrueTypeSlotLoad",
    )
    for item in terminal_errors:
        pos = font.index(item)
        end = font.find("EndIf", pos)
        require(pos >= 0 and end > pos and "pi3_screen_font_boot=2" in font[pos:end],
                f"font failure has a terminal bitmap-fallback state: {item}")

    require("Global Dim pi3_screen_ring.a[8192]" in source
            and "pi3_screen_tail=(pi3_screen_tail+1)&8191" in mirror
            and "pi3_screen_dropped=pi3_screen_dropped+1" in mirror,
            "queued UART text remains bounded with counted drop-oldest overflow")
    case0 = banner.index("Case 0")
    paint = banner.index("Pi3ScreenDrawText", case0)
    first_stamp = banner.index("pi3_screen_first_banner_us=Pi3Micros()", case0)
    require(first_stamp < paint,
            "first graphical banner timestamp precedes its first text draw")

    print("pi3_font_boot_order_check: PASS - 12 focused source-flow assertions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

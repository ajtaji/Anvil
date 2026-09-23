#!/usr/bin/env python3
"""Host gate for the source-aware Anvil display/V3D contract.

This does not model V3D or the DSI block. It independently checks the
half-open rotation arithmetic and guards the source-shape decisions whose
failure froze the panel: DSI must select its fixed back buffer before any
firmware DisplayInit path, presentation must cover both reserved buffers,
and a detach must invalidate geometry-derived V3D state.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NEON = (ROOT / "RaspberryPi4/Lib/neon.pi4").read_text(encoding="utf-8")
SOURCE = (ROOT / "RaspberryPi4/Board/screen_source.pi4").read_text(encoding="utf-8")
CONSOLE = (ROOT / "RaspberryPi4/Board/v3d_console.pi4").read_text(encoding="utf-8")
SCREEN = (ROOT / "RaspberryPi4/Board/screen_cmd.pi4").read_text(encoding="utf-8")
DISPLAY = (ROOT / "RaspberryPi4/Board/display.pi4").read_text(encoding="utf-8")
CURSOR = (ROOT / "RaspberryPi4/Board/cursor_input.pi4").read_text(encoding="utf-8")
UART = (ROOT / "RaspberryPi4/Lib/uart.pi4").read_text(encoding="utf-8")
CORE_PARSE = (ROOT / "Anvil/Core/parse.pbi").read_text(encoding="utf-8")
CORE_CONSOLE = (ROOT / "RaspberryPi4/Board/console.pi4").read_text(encoding="utf-8")


def body(text: str, name: str) -> str:
    start = text.index(f"Procedure.i {name}(")
    end = text.index("EndProcedure", start)
    return text[start:end]


def point(rot: int, lw: int, lh: int, x: int, y: int) -> tuple[int, int]:
    if rot == 90:
        return lh - y, x
    if rot == 180:
        return lw - x, lh - y
    if rot == 270:
        return y, lw - x
    return x, y


def rect(rot: int, lw: int, lh: int, x: int, y: int, w: int, h: int):
    corners = (
        point(rot, lw, lh, x, y),
        point(rot, lw, lh, x + w, y),
        point(rot, lw, lh, x, y + h),
        point(rot, lw, lh, x + w, y + h),
    )
    xs = [p[0] for p in corners]
    ys = [p[1] for p in corners]
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def main() -> None:
    # Logical 1280x800 must land exactly on the 800x1280 physical target.
    assert rect(90, 1280, 800, 0, 0, 1280, 800) == (0, 0, 800, 1280)
    assert rect(270, 1280, 800, 0, 0, 1280, 800) == (0, 0, 800, 1280)
    assert rect(90, 1280, 800, 10, 20, 30, 40) == (740, 10, 40, 30)
    assert rect(270, 1280, 800, 10, 20, 30, 40) == (20, 1240, 40, 30)

    # The engine has separate logical and physical geometry and applies the
    # transform at all three emission boundaries.
    for token in (
        "Global neon_physW.i",
        "Global neon_physH.i",
        "Procedure.i NeonSurfaceOriented(",
        "V3dRenderBegin(neon_physW, neon_physH",
        "Procedure neon_Vertex(",
        "Procedure neon_Rect(",
        "Procedure neon_TexVertex(",
        "Procedure neon_SyncClip(",
    ):
        assert token in NEON, token

    # The fixed DSI back-buffer decision dominates both firmware allocation
    # calls. This is the regression guard for picture-memory becoming zero.
    try_double = body(CONSOLE, "V3dConTryDouble")
    guard = try_double.index("If ScrGpuHasFixedBack() <> 0")
    assert guard < try_double.index("DisplayInit(w, h, 32)")
    assert try_double.count("DisplayInit(w, h, 32)") == 2

    assert "Procedure.i ScrGpuBase()" in SOURCE
    assert "Procedure.i ScrGpuPresent(" in SOURCE
    assert "Procedure.i ScrGpuKeepBanner(" in SOURCE
    # The invalidate helper returns its refusal/status to the lifecycle owner;
    # accept the intentional typed declaration and reject a missing/duplicate
    # seam rather than matching only the old untyped spelling.
    invalidate_decl = "Procedure.i V3dConInvalidate()"
    assert CONSOLE.count(invalidate_decl) == 1
    assert "V3dConInvalidate()" in body(SCREEN.replace("Procedure ScreenDetach(",
                                                       "Procedure.i ScreenDetach("),
                                               "ScreenDetach")
    assert "DmaSetBounds(#MON_FB_LO, (#MON_FB_HI - #MON_FB_LO) + 1)" in DISPLAY
    assert "Global gCursorGpuOwned.i = 0" in CURSOR
    assert CURSOR.count("ConRepaint()") >= 3
    assert CONSOLE.count("gCursorGpuOwned") >= 3

    # Capture names the physical presented surface once, then both screenshot
    # protocols sample it through the common map. In particular they must not
    # fall back to DisplayViewBase directly inside either command.
    assert "Procedure.i ScrCaptureSnapshot(" in SOURCE
    snapshot = body(SOURCE, "ScrCaptureSnapshot")
    assert "fb = #MON_FB_SCAN" in snapshot
    assert "fb = DisplayViewBase()" in snapshot
    assert SCREEN.count("ScrCaptureSnapshot(@fb") == 2
    # The current screen command has four capture probes plus the two legacy
    # protocol paths; each path samples its row anchor and pixel body.
    assert SCREEN.count("ScrCapturePixel(fb, pitch, rot") == 8

    # Producer-side draining updates only the model AT THE PROMPT. The
    # renderer remains a ScreenPump concern, which is what turns a 45 KB help
    # into one frame.
    #
    # DURING THE BOOT LOG IT PAINTS, and that is the one exception. The
    # decision lives in ConMirrorDrain (console.pi4) rather than in the UART,
    # which still knows nothing about renderers, and the window is opened and
    # closed by ScreenEarlyLogStart/Finish - so a long command at the prompt
    # costs exactly what it always did.
    assert "Procedure UartMirrorSetDrain(" in UART
    mirror_put = UART[UART.index("Procedure uart_MirrorPut("):
                      UART.index("EndProcedure", UART.index("Procedure uart_MirrorPut("))]
    assert "uart_mirrorDrain()" in mirror_put
    assert "gConPaint" not in mirror_put
    assert "UartMirrorSetDrain(@ConMirrorDrain)" in SCREEN
    assert "UartMirrorSetDrain(@ConDrainRing)" not in SCREEN
    at = CORE_CONSOLE.index("Procedure ConMirrorDrain()")
    drain_cb = CORE_CONSOLE[at:CORE_CONSOLE.index("EndProcedure", at)]
    assert "gConLiveBoot" in drain_cb and "gConDrainBusy" in drain_cb
    assert "ScreenPump()" in drain_cb and "ConDrainRing()" in drain_cb

    # The alive glint is advanced by the existing core-service spin and has a
    # bounded presented-pixel seam. It must never grow back into a periodic
    # full repaint or reinterpret a renderer-owned back buffer.
    tick_at = DISPLAY.index("Procedure ScreenBannerTick(")
    tick = DISPLAY[tick_at:DISPLAY.index("EndProcedure", tick_at)]
    assert tick.count("ScrPresentedPixel(") == 5
    assert "DrawAnvilPresentedRect(" in tick
    assert "Procedure.i ScrPresentedPixel(" in SOURCE
    assert "DrawBanner()" not in tick
    assert "ConRepaint()" not in tick
    assert "delay(" not in tick
    assert "ScreenServiceTick()" in CORE_PARSE

    # Font scale is one source of truth for both renderer tiers.
    for face in ("UI", "SMALL", "MONO", "BOLD"):
        assert f"#NEON_FONT_{face}," in CONSOLE
    assert CONSOLE.count("gScrScale") >= 4

    print("display_pipeline_check: PASS")


if __name__ == "__main__":
    main()

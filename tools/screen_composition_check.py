#!/usr/bin/env python3
"""THE COMPOSITION CONTRACT: NO STALE SCAN LINE, AND TWO SCREENS THAT DO NOT
BORROW EACH OTHER'S ASSUMPTIONS.

A structural gate. It reads source and proves ownership and coverage; it does
not compile or execute, and it makes no claim about what a panel looks like.
What it exists to catch is the family of defects that are invisible from a
desk and nearly invisible on a bench:

  A BAND THAT IS PAINTED AND NOT PRESENTED. On HDMI, and on the panel at 0
  and 180, the bytes drawn are the bytes scanned and a missing present costs
  nothing. At 90 and 270 the drawn buffer and the scanned buffer are
  different memory, so any row the renderer painted and did not present
  leaves the PREVIOUS contents of that row on the glass - a stale scan line
  that looks like a rendering glitch and is really a coverage bug. Every
  branch of ConPaintDma that puts pixels down must widen the band, and the
  band must be presented exactly once, at the end.

  A CLEAN THAT MISSES A BYTE THE TRANSPOSE WROTE. The pixels and the cache
  maintenance must come from the same address arithmetic - ScrRunAddr - or a
  board running with the caches on scans bytes the CPU still holds.

  A SURFACE SHARED WITH A BUS MASTER AND MAPPED CACHEABLE. Both fixed DSI
  surfaces are written by the DMA engine and read by the display controller,
  whichever one is currently adopted, so the mapping must cover the whole
  reserved window and not the adopted base.

  AN HDMI ASSUMPTION IN THE DSI PATH, OR THE REVERSE. The firmware owns an
  HDMI surface - its address, its stride, its scanout - and owns no DSI
  display at all. A stride, a rotation or a scanout assumption that crosses
  between them produces a console that is perfect on the screen it was
  developed against.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SCREEN = ROOT / "RaspberryPi4/Board/screen_cmd.pi4"
SOURCE = ROOT / "RaspberryPi4/Board/screen_source.pi4"
CACHE = ROOT / "RaspberryPi4/Board/cache.pi4"

NL = chr(10)


def body(text: str, name: str) -> str:
    found = re.search(rf"(?ms)^Procedure(?:\.i)? {re.escape(name)}\(.*?\)\n(.*?)^EndProcedure",
                      text)
    if not found:
        raise AssertionError(f"{name} not found")
    return found.group(1)


# Words that belong to one screen's acquisition contract and must never
# appear in the other's composition path.
FIRMWARE_ONLY = ("DisplayInit(", "DisplaySelect(", "DisplaySelectNone(",
                 "DisplayStandardTags(", "ScreenPixelOrder(", "DisplayCount(")
PANEL_ONLY = ("HvsFlip", "HvsUp(", "HvsFill(", "ScrTranspose", "ScrDsiBringUp",
              "DsiHost", "PvUp(", "#MON_FB_")


def validate(screen: str, source: str, cache: str) -> None:
    # ---- 1. THE PRESENTED BAND COVERS EVERY BRANCH THAT DREW ------------
    paint = body(screen, "ConPaintDma")
    if paint.count("ScrPresent(") != 1:
        raise AssertionError("ConPaintDma no longer presents exactly once")
    if "If pHi >= pLo" not in paint:
        raise AssertionError("ConPaintDma presents an empty band")
    if paint.index("ScrPresent(pLo, pHi)") < paint.rindex("pHi = "):
        raise AssertionError("ConPaintDma presents before the band is complete")
    # A whole-screen clear presents the whole screen.
    clear = paint[paint.index("If ConGridFullClear()"):paint.index("ElseIf ConGridScrollN()")]
    if "pLo = 0" not in clear or "pHi = DisplayHeight() - 1" not in clear:
        raise AssertionError("a full clear no longer presents the whole surface")
    # A SCROLL MOVES EVERY ROW WHETHER OR NOT IT IS DIRTY. Presenting only
    # the rows the loop repaints is the exact defect that shows as a panel
    # scrolling its bottom line with the rest standing still.
    scroll = paint[paint.index("ElseIf ConGridScrollN()"):paint.index("  r = 0")]
    if "pLo = LogoHeight()" not in scroll or "pHi = DisplayHeight() - 1" not in scroll:
        raise AssertionError("a scroll no longer presents the whole console")
    # Every dirty row joins the band.
    rows = paint[paint.index("  r = 0"):paint.index("ConGridClearDirty()")]
    if "If y < pLo" not in rows or "If (y + ch - 1) > pHi" not in rows:
        raise AssertionError("a repainted row no longer joins the presented band")
    # THE CURSOR IS PART OF THE PICTURE AND IT MOVES ON ITS OWN, often onto
    # a row nothing else touched.
    cur = paint[paint.index("ConGridClearDirty()"):]
    if "If gCurY < pLo" not in cur or "If (gCurY + #CUR_H - 1) > pHi" not in cur:
        raise AssertionError("the cursor no longer joins the presented band")

    # ---- 2. THE CLEAN AND THE PIXELS SHARE ONE ADDRESS CALCULATION ------
    present = body(source, "ScrPresent")
    if "ScrTranspose(" not in present or "MmuCleanRange(ScrRunAddr(" not in present:
        raise AssertionError("the present no longer cleans what it transposed")
    if "While sy < #MON_FB_PANEL_H" not in present:
        raise AssertionError("the clean no longer walks every physical row")
    if present.index("ScrTranspose(") > present.index("MmuCleanRange("):
        raise AssertionError("the clean runs before the pixels it is for")
    # A whole-surface present is the only thing that covers the banner band,
    # which is not part of the console grid.
    allp = body(source, "ScrPresentAll")
    if "ScrPresent(0, ScrLogicalH(" not in allp:
        raise AssertionError("the whole-surface present no longer covers the whole surface")

    # ---- 3. BOTH FIXED SURFACES ARE NON-CACHEABLE, ALWAYS ---------------
    nc = body(cache, "CacheMapNc")
    if "MmuAddNc(#MON_FB_LO, #MON_FB_HI + 1)" not in nc:
        raise AssertionError("the fixed DSI window is no longer mapped non-cacheable whole")
    if nc.index("MmuAddNc(#MON_FB_LO") > nc.index("If DisplayReady()"):
        raise AssertionError("the fixed window mapping now depends on the adopted surface")

    # ---- 4. THE TWO SCREENS DO NOT BORROW EACH OTHER'S CONTRACT ---------
    # ScrPresent is the seam, and it answers for one screen only.
    if "If gScrSrc <> #SCR_SRC_DSI" not in present:
        raise AssertionError("the present no longer refuses a screen it does not own")
    for name in ("ScrDsiReadoptBegin", "ScrDsiReadoptResolve", "ScrDsiReadoptAbandon"):
        text = body(source, name)
        for word in FIRMWARE_ONLY:
            if word in text:
                raise AssertionError(f"{name} reaches the firmware display path: {word}")
    hdmi = body(screen, "ScreenHdmiRescale")
    for word in PANEL_ONLY + ("DisplayAdopt(",):
        if word in hdmi:
            raise AssertionError(f"the HDMI redraw borrows a panel assumption: {word}")
    # And the shared tail is shared - it must contain neither screen's
    # acquisition, because it runs after both of them.
    rebuild = body(screen, "ScreenRebuildAtGeometry")
    for word in FIRMWARE_ONLY + ("DisplayAdopt(", "HvsFlip", "ScrDsiBringUp"):
        if word in rebuild:
            raise AssertionError(f"the shared composition tail re-acquires a surface: {word}")
    if "ScrPresentAll()" not in rebuild:
        raise AssertionError("the shared composition tail does not present what it drew")
    # EVERY QUEUED TOUCH EVENT WAS MAPPED AGAINST THE OLD SURFACE. A finger
    # that went down on the old geometry must not come up on the new one.
    if "HwTouchFlush()" not in rebuild:
        raise AssertionError("the shared composition tail keeps touch events from the old surface")
    if rebuild.index("HwTouchFlush()") > rebuild.index("ScrPresentAll()"):
        raise AssertionError("touch events are flushed after the new frame is presented")


def once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise AssertionError("mutation anchor is not unique: " + repr(old))
    return text.replace(old, new, 1)


MUTATIONS = (
    ("a scroll presents only the rows it repaints",
     lambda s, so, c: (once(s, "    pLo = LogoHeight()" + NL, "    pLo = DisplayHeight()" + NL), so, c)),
    ("a full clear presents nothing",
     lambda s, so, c: (once(s, "    pLo = 0" + NL, "    pLo = DisplayHeight()" + NL), so, c)),
    ("a repainted row does not join the band",
     lambda s, so, c: (once(s, "      If y < pLo" + NL, "      If y < -1" + NL), so, c)),
    ("the cursor does not join the band",
     lambda s, so, c: (once(s, "    If gCurY < pLo" + NL, "    If gCurY < -1" + NL), so, c)),
    ("the band is presented before it is complete",
     lambda s, so, c: (s.replace("  If pHi >= pLo" + NL + "    ScrPresent(pLo, pHi)" + NL + "  EndIf" + NL,
                                 "  If pHi >= pLo" + NL + "  EndIf" + NL, 1), so, c)),
    ("a second present appears in the renderer",
     lambda s, so, c: (once(s, "  ConGridClearDirty()" + NL,
                            "  ConGridClearDirty()" + NL + "  ScrPresent(0, 0)" + NL), so, c)),
    ("the clean stops walking every physical row",
     lambda s, so, c: (s, once(so, "  While sy < #MON_FB_PANEL_H" + NL,
                               "  While sy < 1" + NL), c)),
    ("the clean stops using the transpose's own address",
     lambda s, so, c: (s, once(so, "    MmuCleanRange(ScrRunAddr(gScrRot, #MON_FB_SCAN, #MON_FB_PANEL_W, lh, y0, y1, sy), run)",
                               "    MmuCleanRange(#MON_FB_SCAN + sy * #MON_FB_PANEL_W * 4, run)"), c)),
    ("the present stops refusing a screen it does not own",
     lambda s, so, c: (s, once(so, "  If gScrSrc <> #SCR_SRC_DSI" + NL + "    ProcedureReturn" + NL + "  EndIf" + NL, ""), c)),
    ("only the adopted surface is mapped non-cacheable",
     lambda s, so, c: (s, so, once(c, "  MmuAddNc(#MON_FB_LO, #MON_FB_HI + 1)" + NL, ""))),
    ("the fixed window mapping is made to follow the adopted base",
     lambda s, so, c: (s, so, once(c,
                                   "  MmuAddNc(#MON_FB_LO, #MON_FB_HI + 1)" + NL + "  If DisplayReady()",
                                   "  If DisplayReady()"))),
    ("the DSI re-adoption asks the firmware for a display",
     lambda s, so, c: (s, once(so, "  If gScrReadoptPending <> 0 Or gScrDsiUp = 0 Or HvsIsUp() = 0",
                               "  DisplayStandardTags()" + NL + "  If gScrReadoptPending <> 0 Or gScrDsiUp = 0 Or HvsIsUp() = 0"), c)),
    ("the HDMI redraw borrows the panel's fixed framebuffer",
     lambda s, so, c: (once(s, "  gScrScale = scale" + NL,
                            "  gScrScale = scale" + NL + "  DisplayAdopt(#MON_FB_SCAN, 3200, 800, 1280, 32)" + NL), so, c)),
    ("the shared composition tail keeps the old surface's touch events",
     lambda s, so, c: (once(s, "  HwTouchFlush()" + NL + NL + "  ScrPresentAll()" + NL,
                            "  ScrPresentAll()" + NL), so, c)),
    ("the shared composition tail re-acquires a surface",
     lambda s, so, c: (once(s, "  gDma = ScreenDmaUp()" + NL + "  DisplayAutoFlush(1)" + NL,
                            "  DisplayInit(1920, 1080, 32)" + NL + "  gDma = ScreenDmaUp()" + NL + "  DisplayAutoFlush(1)" + NL), so, c)),
)


def main() -> int:
    screen = SCREEN.read_text(encoding="utf-8")
    source = SOURCE.read_text(encoding="utf-8")
    cache = CACHE.read_text(encoding="utf-8")
    validate(screen, source, cache)

    for label, transform in MUTATIONS:
        mutant = transform(screen, source, cache)
        try:
            validate(*mutant)
        except AssertionError:
            print("  rejected: " + label)
        else:
            raise AssertionError("mutation survived: " + label)

    print("screen_composition_check: PASS - presented band covers every branch that "
          f"drew, clean and pixels share one address, both fixed surfaces stay "
          f"non-cacheable, DSI and HDMI keep their own contracts; "
          f"{len(MUTATIONS)} mutations rejected")
    print("  structural source proof only; no compile, execution or panel claim")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

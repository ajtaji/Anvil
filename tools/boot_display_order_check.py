#!/usr/bin/env python3
"""THE DISPLAY COMES UP BEFORE THE SLOW HALF OF THE BOOT, AND BEFORE THE NETWORK.

A structural gate over the actual boot sequence and the seams that make that
order safe. It proves ORDER and OWNERSHIP in source; it compiles nothing,
executes nothing, and makes no claim about how long anything takes on silicon -
the retained timing record is what answers that, and
tools/boot_timing_emitted_check.py is what proves the record.

What it refuses, and why each one is a defect that boots perfectly:

  the screen after USB/storage    the old order. PCIe, the xHCI host and the
                                  boot medium are the longest thing before the
                                  radio, and their lines went to the wire while
                                  the glass was dark.
  the screen after the network    a board that stalls in the radio says nothing
                                  at all.
  the stored geometry applied
    before the settings exist     it would read an empty store, find the
                                  default it already used, and do nothing -
                                  silently, forever.
  the transcript armed after the
    screen                        the geometry correction would rebuild the
                                  grid and have nothing to put back in it.
  capture never stopped           the operator's own session would be retained
                                  and replayed at them.
  live painting never armed       every boot line would sit in the grid
                                  unpainted until the prompt, which is the
                                  "buffered until startup ends" failure this
                                  reorder exists to remove.
  live painting never turned off  every long command afterwards would repaint
                                  the whole console once per line.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "RaspberryPi4/Board/board.pi4"
BANNER = ROOT / "RaspberryPi4/Board/banner_clock.pi4"
CONSOLE = ROOT / "RaspberryPi4/Board/console.pi4"
BOOT = ROOT / "RaspberryPi4/Board/boot.pi4"
SCREEN = ROOT / "RaspberryPi4/Board/screen_cmd.pi4"

NL = chr(10)

# Exactly one of each, in this order, at Main()'s own indentation.
ORDER = (
    "BootTimingBegin(hz, ClockMeasuredHz(#MBX_CLK_ARM))",
    "ScreenEarlyLogStart()",
    "Banner()",
    "ScreenDsiEarlyCacheArm()",
    "ScreenUp()",
    "TouchBoot()",
    "BootConfigUp()",
    "ScreenApplyStoredGeometry()",
    "ScreenEarlyLogFinish()",
    "BootNetUp()",
)


def body(text: str, name: str) -> str:
    found = re.search(rf"(?ms)^Procedure(?:\.i)? {re.escape(name)}\(.*?\)\n(.*?)^EndProcedure",
                      text)
    if not found:
        raise AssertionError(f"{name} not found")
    return found.group(1)


def validate(board: str, banner: str, console: str, boot: str, screen: str) -> None:
    main = body(board, "Main")
    for token in ORDER:
        if len(re.findall(rf"(?m)^  {re.escape(token)}$", main)) != 1:
            raise AssertionError(f"expected exactly one {token} in Main")
    at = [re.search(rf"(?m)^  {re.escape(token)}$", main).start() for token in ORDER]
    if at != sorted(at):
        raise AssertionError("the display-first boot order changed")

    # THE SLOW PERIPHERALS ARE INSIDE BootConfigUp AND NOWHERE ELSE. If one of
    # them ever migrates back into Main above ScreenUp the order above would
    # still read correctly while the glass went dark again.
    config = body(boot, "BootConfigUp")
    for slow in ("UsbEnumerate()", "StorageUp()", "SettingsLoad()"):
        if slow not in config:
            raise AssertionError(f"{slow} left BootConfigUp")
        if re.search(rf"(?m)^  {re.escape(slow)}$", main):
            raise AssertionError(f"{slow} is called directly from Main")

    start = body(banner, "ScreenEarlyLogStart")
    finish = body(banner, "ScreenEarlyLogFinish")

    # PROGRESS IS PAINTED AS IT IS PRINTED, AND THE WINDOW IS EXPLICIT.
    drain_cb = body(console, "ConMirrorDrain")
    if "gConLiveBoot" not in drain_cb or "ScreenPump()" not in drain_cb:
        raise AssertionError("the boot log no longer paints as it is printed")
    if "gConDrainBusy" not in drain_cb:
        raise AssertionError("the producer-side callback lost its re-entry guard")
    if "ConSetLiveBoot(1)" not in start:
        raise AssertionError("live boot painting is never armed")
    if "ConSetLiveBoot(0)" not in finish:
        raise AssertionError("live boot painting is never turned off")
    if "UartMirrorSetDrain(@ConDrainRing)" in screen:
        raise AssertionError("a mirror registration bypasses the live-boot decision")
    if screen.count("UartMirrorSetDrain(@ConMirrorDrain)") < 1:
        raise AssertionError("nothing registers the producer-side callback")

    if "BootTranscriptStart()" not in start:
        raise AssertionError("the boot transcript is not armed with the early log")
    if "BootTranscriptStop()" not in finish:
        raise AssertionError("the boot transcript is never stopped")
    if finish.index("BootTranscriptStop()") > finish.index("ScreenServiceTick()"):
        raise AssertionError("capture outlives the boot log it is for")

    # ONE TAP, ON THE ONE CONSUMER. Capture must sit in ConDrainRing beside
    # ConGridPutc: at the producer it would catch bytes the grid never got, and
    # in a renderer it would catch them once per repaint.
    drain = body(console, "ConDrainRing")
    if "BootTranscriptPut(c)" not in drain:
        raise AssertionError("the transcript is not taken from the one output consumer")
    if drain.index("BootTranscriptPut(c)") > drain.index("ConGridPutc(c)"):
        raise AssertionError("the transcript is taken after the grid, not with it")
    for other in ("ScreenPump", "ConRepaint", "ConGridPutc"):
        if "BootTranscriptPut" in body(console, other):
            raise AssertionError(f"a second transcript tap appeared in {other}")


def once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise AssertionError("mutation anchor is not unique: " + repr(old))
    return text.replace(old, new, 1)


def move_main(board: str, token: str, anchor: str, before: bool) -> str:
    main = body(board, "Main")
    line = "  " + token + NL
    moved = once(main, line, "")
    ins = line + anchor if before else anchor + line
    return board.replace(main, once(moved, anchor, ins), 1)


MUTATIONS = (
    ("the screen after USB, storage and settings",
     lambda b, bn, c, bt, sc: (move_main(b, "ScreenUp()", "  ScreenApplyStoredGeometry()" + NL, True),
                               bn, c, bt, sc)),
    ("the screen after the network",
     lambda b, bn, c, bt, sc: (move_main(b, "ScreenUp()", "  BootWait()" + NL, True), bn, c, bt, sc)),
    ("the stored geometry applied before the settings are read",
     lambda b, bn, c, bt, sc: (move_main(b, "ScreenApplyStoredGeometry()", "  BootConfigUp()" + NL, True),
                               bn, c, bt, sc)),
    ("the stored geometry never applied",
     lambda b, bn, c, bt, sc: (once(b, "  ScreenApplyStoredGeometry()" + NL, ""), bn, c, bt, sc)),
    ("the timing record started after the screen",
     lambda b, bn, c, bt, sc: (move_main(b, "BootTimingBegin(hz, ClockMeasuredHz(#MBX_CLK_ARM))",
                                         "  TouchBoot()" + NL, False), bn, c, bt, sc)),
    ("USB enumeration hoisted into Main above the screen",
     lambda b, bn, c, bt, sc: (once(b, "  ScreenDsiEarlyCacheArm()" + NL,
                                    "  UsbEnumerate()" + NL + "  ScreenDsiEarlyCacheArm()" + NL),
                               bn, c, bt, sc)),
    ("the transcript never armed",
     lambda b, bn, c, bt, sc: (b, once(bn, "  BootTranscriptStart()" + NL, ""), c, bt, sc)),
    ("the transcript never stopped",
     lambda b, bn, c, bt, sc: (b, once(bn, "  BootTranscriptStop()" + NL, ""), c, bt, sc)),
    ("live boot painting never armed",
     lambda b, bn, c, bt, sc: (b, once(bn, "  ConSetLiveBoot(1)" + NL, ""), c, bt, sc)),
    ("live boot painting left on after the boot log",
     lambda b, bn, c, bt, sc: (b, once(bn, "  ConSetLiveBoot(0)" + NL, ""), c, bt, sc)),
    ("the transcript taken after the grid instead of with it",
     lambda b, bn, c, bt, sc: (b, bn,
                               once(c, "    BootTranscriptPut(c)" + NL + "    ConGridPutc(c)" + NL,
                                    "    ConGridPutc(c)" + NL + "    BootTranscriptPut(c)" + NL),
                               bt, sc)),
    ("a second transcript tap in the pump",
     lambda b, bn, c, bt, sc: (b, bn,
                               once(c, NL + "  ConDrainRing()" + NL,
                                    NL + "  ConDrainRing()" + NL + "  BootTranscriptPut(0)" + NL),
                               bt, sc)),
    ("the producer-side callback loses its re-entry guard",
     lambda b, bn, c, bt, sc: (b, bn, c.replace("gConDrainBusy", "gConDrainIdle"), bt, sc)),
    ("the producer-side callback stops painting",
     lambda b, bn, c, bt, sc: (b, bn,
                               once(c, "    ScreenPump()" + NL + "  Else" + NL,
                                    "    ConDrainRing()" + NL + "  Else" + NL),
                               bt, sc)),
    ("the registrations bypass the live-boot decision",
     lambda b, bn, c, bt, sc: (b, bn, c, bt,
                               sc.replace("UartMirrorSetDrain(@ConMirrorDrain)",
                                          "UartMirrorSetDrain(@ConDrainRing)"))),
    ("the boot medium moved out of the configuration half",
     lambda b, bn, c, bt, sc: (b, bn, c, once(bt, "  up = StorageUp()" + NL, "  up = 0" + NL), sc)),
)


def main() -> int:
    board = BOARD.read_text(encoding="utf-8")
    banner = BANNER.read_text(encoding="utf-8")
    console = CONSOLE.read_text(encoding="utf-8")
    boot = BOOT.read_text(encoding="utf-8")
    screen = SCREEN.read_text(encoding="utf-8")
    validate(board, banner, console, boot, screen)

    for label, transform in MUTATIONS:
        mutant = transform(board, banner, console, boot, screen)
        try:
            validate(*mutant)
        except AssertionError:
            print("  rejected: " + label)
        else:
            raise AssertionError("mutation survived: " + label)

    print("boot_display_order_check: PASS - display before the slow peripherals and "
          "before the network, live boot painting, one transcript tap, "
          f"{len(MUTATIONS)} mutations rejected")
    print("  structural source proof only; no compile, execution or timing claim")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

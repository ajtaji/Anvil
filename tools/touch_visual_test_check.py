#!/usr/bin/env python3
"""Structural gate for the bounded, real-input visual touch diagnostic."""
import pathlib
import sys

root = pathlib.Path(__file__).resolve().parents[1]
board = (root / "RaspberryPi4/Board/board.pi4").read_text(encoding="utf-8")
cmd = (root / "RaspberryPi4/Board/touch_cmd.pi4").read_text(encoding="utf-8")
vis = (root / "RaspberryPi4/Board/touch_visual_test.pi4").read_text(encoding="utf-8")
fails = []

def need(label, ok):
    if not ok: fails.append(label)

need("visual/test/command include order",
     board.index('XIncludeFile "RaspberryPi4/Board/v3d_console.pi4"') <
     board.index('XIncludeFile "RaspberryPi4/Board/screen_cmd.pi4"') <
     board.index('XIncludeFile "RaspberryPi4/Board/touch_visual_test.pi4"') <
     board.index('XIncludeFile "RaspberryPi4/Board/touch_cmd.pi4"') <
     board.index("      CmdTouch()"))
need("single command route", cmd.count('WordIs("test")') == 1 and
     cmd.count("TouchVisualTest()") == 1)
need("bounded key/timeout exit", "polls < #TOUCH_VISUAL_POLLS" in vis and
     "Ticks() < deadline" in vis and "OutBreak()" in vis and
     "KeyboardChar()" in vis and "#TOUCH_VISUAL_POLLS = 1500" in vis)
need("real controller current frame", "n = HwTouchTick()" in vis and
     "HwTouchPointId(i)" in vis and "HwTouchPointX(i)" in vis and
     "HwTouchPointY(i)" in vis)
need("stable tracking-id state", "active[id]" in vis and "oldX[id]" in vis)
need("actual capacity and peak", "cap = HwTouchMaxPoints()" in vis and
     "If n > peak" in vis)
need("queue drained", "While HwTouchPoll(@ev[0]) = 1" in vis)
code = "\n".join(line.split(";", 1)[0] for line in vis.splitlines())
need("no transaction-changing recovery", all(x not in code for x in
     ("HwTouchRestart(", "HwTouchUp(", "I2c", "Reset(", "PinAlt", "DsiV2")))
need("normal renderer restored", "ConRepaint()" in vis and
     "ConSetRenderer(*wasPaint)" in vis and "gV3dConOn = 1" in vis)

if fails:
    print("touch_visual_test_check: FAIL")
    for f in fails: print("  * " + f)
    sys.exit(1)
print("touch_visual_test_check: PASS - bounded real-input 10-contact diagnostic")

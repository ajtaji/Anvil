#!/usr/bin/env python3
"""Execute the shipped console-restoration bodies against the shipped transcript.

The screen comes up on the defaults before the settings store exists and is
corrected afterwards. The correction rebuilds the console grid, and the one
thing it may never do is restore that grid from the pixels still on the glass:
at a new rotation or magnification those pixels are the wrong shape.

So this runs the actual ScreenApplyStoredGeometry, ScreenRebuildAtGeometry,
ScreenDsiReadoptStart / Service / Abandon and ScreenHdmiRescale bodies over the
actual Anvil/Core/boot_transcript.pbi, with counting stubs for the surface, the
renderer, the HVS and the timing record. No board, no display, no GPU.

  PMF_COMPILER=<PureMetalForge.exe> PMF_A64_INTERP=<a64_interp.py> python tools/screen_restore_emitted_check.py
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import tcp_multiif_emitted_check as emitted

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "RaspberryPi4" / "Board" / "screen_cmd.pi4"
FIXTURE = ROOT / "RaspberryPi4" / "Tests" / "screen_restore_emitted_gate.pi4"

BODIES = (
    "ScreenRebuildAtGeometry",
    "ScreenDsiReadoptStart",
    "ScreenDsiReadoptService",
    "ScreenDsiReadoptAbandon",
    "ScreenHdmiRescale",
    "ScreenApplyStoredGeometry",
)
GLOBALS = "Global *gScreenReadoptPaint\nGlobal gScreenReadoptSuspended.i\n"


def procedure(source: str, name: str) -> str:
    found = re.search(rf"(?ms)^Procedure(?:\.i)? {re.escape(name)}\(.*?^EndProcedure\s*$", source)
    if not found:
        raise SystemExit(f"screen restore gate: {name} not found in screen_cmd.pi4")
    return found.group(0)


def product_bodies(source: str) -> str:
    return GLOBALS + "\n" + "\n\n".join(procedure(source, name) for name in BODIES)


def fixture(bodies: str) -> str:
    text = FIXTURE.read_text(encoding="utf-8")
    if text.count("; @@BODY@@") != 1:
        raise SystemExit("screen restore gate: fixture marker drifted")
    return text.replace("; @@BODY@@", bodies, 1)


def build(compiler: Path, work: Path, text: str, stem: str) -> Path:
    staged = work / compiler.name
    if not staged.exists():
        shutil.copy2(compiler, staged)
    if (ROOT / "Boards").is_dir() and not (work / "Boards").exists():
        shutil.copytree(ROOT / "Boards", work / "Boards")
    src = work / f"{stem}.pi4"
    src.write_text(text, encoding="utf-8", newline="\n")
    image = work / f"{stem}.img"
    run = subprocess.run(
        [str(staged), "--compile", str(src), "-t", "pi4",
         "--load-addr", hex(emitted.LOAD), "--stack-addr", hex(emitted.STACK),
         "--entry-returns", "-o", str(image), "-s"],
        cwd=ROOT, env={**os.environ, "PMF_ROOT": str(ROOT)},
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise SystemExit(f"screen restore gate: {stem} compile failed\n{run.stdout}")
    return image


def mutate(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"screen restore gate: {label} anchor count {text.count(old)}")
    return text.replace(old, new, 1)


MUTATIONS = (
    # THE ONE THIS GATE EXISTS FOR. A rebuild that does not replay is a
    # console that keeps its banner and loses everything printed before the
    # geometry moved - and on a quiet bench it looks perfectly normal.
    ("the retained boot log is not replayed",
     "  While i < BootTranscriptCount()",
     "  While i < 0"),
    ("the replay resumes instead of starting at byte zero",
     "  i = 0\n  While i < BootTranscriptCount()",
     "  i = 1\n  While i < BootTranscriptCount()"),
    # A grid that is not re-sized to the new geometry keeps the old column
    # count, so every line wraps in the wrong place.
    ("the grid is not rebuilt at the new geometry",
     "  ConGridInit(DisplayCols(), DisplayRows())",
     "  ; grid not rebuilt"),
    # The banner band is not part of the grid, so only a whole-surface
    # present puts it back.
    ("the rebuilt surface is never presented",
     "  HwTouchFlush()\n\n  ScrPresentAll()",
     "  HwTouchFlush()"),
    # Every touch event still queued was mapped against the old surface.
    ("the old surface's touch events survive the rebuild",
     "  HwTouchFlush()\n\n  ScrPresentAll()",
     "  ScrPresentAll()"),
    ("the GPU keeps geometry-derived state across the rebuild",
     "  V3dConInvalidate()\n  gV3dConOn = 0\n  gCursorGpuOwned = 0",
     "  ; GPU state kept"),
    # The keyboard's hit rectangles were derived from the old surface.
    ("the keyboard keeps rectangles from the old surface",
     "  TouchKeyboardOverlayReset()",
     "  ; layout kept"),
    # Painting while the HVS has not taken the list is a frame torn between
    # two geometries.
    ("the console paints while the list switch is pending",
     "  If ScrDsiReadoptResolve() = 0\n    ProcedureReturn 0\n  EndIf",
     "  ScrDsiReadoptResolve()"),
    # Giving up must not pretend the request was cancelled.
    ("giving up forgets the staged display list",
     "  ScrDsiReadoptAbandon()",
     "  ; request forgotten"),
    ("giving up leaves the console with no renderer",
     "  ConSetRenderer(*gScreenReadoptPaint)\n  UartMirrorSetDrain(@ConMirrorDrain)\n  gScreenReadoptSuspended = 0\n  ConRepaint()",
     "  gScreenReadoptSuspended = 0",),
    # A refused stage must leave the console running.
    ("a refused stage leaves the console suspended",
     "    ConSetRenderer(*gScreenReadoptPaint)\n    UartMirrorSetDrain(@ConMirrorDrain)\n    gScreenReadoptSuspended = 0\n    ProcedureReturn 0",
     "    ProcedureReturn 0"),
    # THE TWO SCREENS ARE DIFFERENT CONTRACTS. An HDMI console routed into
    # the DSI re-adoption would ask the HVS for a display list that points
    # at a framebuffer the firmware owns.
    ("HDMI is routed through the DSI re-adoption",
     "  If gScrSrc <> #SCR_SRC_DSI\n    If rot <> gScrRot",
     "  If gScrSrc = #SCR_SRC_NONE\n    If rot <> gScrRot"),
    ("the HDMI redraw accepts a DSI console",
     "  If gScreen = 0 Or gScrSrc <> #SCR_SRC_HDMI\n    ProcedureReturn 0\n  EndIf",
     "  If gScreen = 0\n    ProcedureReturn 0\n  EndIf"),
    # A stored magnification out of range must not reach DisplayScale.
    ("an out-of-range magnification is applied",
     "  If ScrScaleOk(scale) = 0\n    ProcedureReturn 0\n  EndIf",
     "  ; range not checked"),
    # The common case must cost nothing: a store that agrees with the
    # default must not rebuild the console at every boot.
    ("the console is rebuilt even when nothing changed",
     "  If rot = gScrRot And scale = gScrScale\n    ProcedureReturn 0\n  EndIf",
     "  ; always rebuild"),
    # THE WIDTH THE SCALE RULE IS HANDED. Used for the eighty-column cap
    # only, so a wrong one makes the type smaller for no reason - and then
    # makes the comparison above believe the store disagrees with the
    # screen at every boot, rebuilding the console every time.
    ("the panel's width is used for an HDMI console",
     "  If gScrSrc = #SCR_SRC_DSI\n    scale = ScrScaleWanted(gScrSrc, ScrLogicalW(rot, #MON_FB_PANEL_W, #MON_FB_PANEL_H))\n  Else\n    scale = ScrScaleWanted(gScrSrc, DisplayWidth())\n  EndIf",
     "  scale = ScrScaleWanted(gScrSrc, ScrLogicalW(rot, #MON_FB_PANEL_W, #MON_FB_PANEL_H))"),
    ("the live surface's width is used for a rotation that has not happened yet",
     "    scale = ScrScaleWanted(gScrSrc, ScrLogicalW(rot, #MON_FB_PANEL_W, #MON_FB_PANEL_H))\n  Else",
     "    scale = ScrScaleWanted(gScrSrc, DisplayWidth())\n  Else"),
    # And there must be a screen to correct.
    ("the stored geometry is applied with no screen up",
     "  If gScreen = 0\n    ProcedureReturn 0\n  EndIf\n\n  rot = ScrRotWanted(gScrSrc)",
     "  rot = ScrRotWanted(gScrSrc)"),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"))
    args = parser.parse_args()
    compiler = emitted.required_path(args.compiler, "PMF_COMPILER")
    a64 = emitted.load_interpreter(emitted.required_path(args.interp, "PMF_A64_INTERP"))

    source = PRODUCT.read_text(encoding="utf-8")
    bodies = product_bodies(source)

    with tempfile.TemporaryDirectory(prefix="anvil-screen-restore-") as td:
        work = Path(td)
        result, steps = emitted.execute(a64, build(compiler, work, fixture(bodies), "screen_restore_gate"))
        if result:
            print(f"screen_restore_emitted_check: FAIL assertion {result} after {steps:,} A64 instructions")
            return 1
        killed = []
        for i, (label, old, new) in enumerate(MUTATIONS, 1):
            mutant = mutate(bodies, old, new, label)
            r, _ = emitted.execute(a64, build(compiler, work, fixture(mutant), f"screen_restore_mutant_{i}"))
            if r == 0:
                print(f"screen_restore_emitted_check: FAIL {label} mutant survived")
                return 1
            killed.append(f"{label}:{r}")

    print(f"screen_restore_emitted_check: PASS - 61 assertions over the shipped restore "
          f"paths and the shipped transcript, {steps:,} A64 instructions; "
          f"{len(MUTATIONS)} mutants rejected")
    for entry in killed:
        print("  rejected: " + entry)
    print("  the surface, the renderer, the HVS and the timing record are counting")
    print("  stubs. Emitted execution, not a physical display proof.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

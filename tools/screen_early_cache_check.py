#!/usr/bin/env python3
"""Emitted policy and structural order gate for early DSI caching.

CacheEnable is a counting leaf in the emitted fixture. This proves policy and
call placement, not MMU/cache hardware behavior or display speed.
"""
from pathlib import Path
import argparse
import os
import re
import subprocess
import tempfile

import sys

import tcp_multiif_emitted_check as emitted

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_count  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "RaspberryPi4/Board/screen_cmd.pi4"
BOARD = ROOT / "RaspberryPi4/Board/board.pi4"
LOAD, BSS, STACK, RETURN = 0x500000, 0x600000, 0x800000, 0xDEAD0000


def procedure(text: str, name: str) -> str:
    match = re.search(rf"(?ms)^Procedure(?:\.i)? {name}\([^\n]*\)\n.*?^EndProcedure", text)
    if not match:
        raise AssertionError("missing procedure " + name)
    return match.group(0)


def validate_order(text: str) -> None:
    body = procedure(text, "ScreenUpOn")
    tokens = ("rc = ScrDsiSurface()", "gScrSrc = #SCR_SRC_DSI",
              "ScreenDsiEarlyCache(earlyCache)", "gDma = ScreenDmaUp()",
              "DisplayClear(DisplayRGB(0, 0, 40))", "DrawBanner()")
    positions = []
    for token in tokens:
        matches = list(re.finditer(rf"(?m)^\s*{re.escape(token)}$", body))
        if len(matches) != 1:
            raise AssertionError("expected one source-order token: " + token)
        positions.append(matches[0].start())
    if positions != sorted(positions):
        raise AssertionError("DSI adoption/cache/DMA/paint order changed")
    helper = procedure(text, "ScreenDsiEarlyCache")
    if "If armed <> 0 And gScrSrc = #SCR_SRC_DSI\n    CacheEnable()\n  EndIf" not in helper:
        raise AssertionError("early cache is not narrowly DSI-only")
    take = procedure(text, "ScreenDsiEarlyCacheTake")
    if take.index("armed = gScreenDsiEarlyCacheArm") > take.index("gScreenDsiEarlyCacheArm = 0"):
        raise AssertionError("boot arm is not consumed after capture")
    board = BOARD.read_text(encoding="utf-8")
    main = procedure(board, "Main")
    def callpos(token: str) -> int:
        found = re.search(rf"(?m)^  {re.escape(token)}$", main)
        if not found:
            raise AssertionError("missing boot call " + token)
        return found.start()
    arm = callpos("ScreenDsiEarlyCacheArm()")
    trace = callpos("I2cTraceEnable(1)")
    screen = callpos("ScreenUp()")
    if not arm < trace < screen:
        raise AssertionError("boot arm/trace/screen order changed")


def build(compiler: Path, work: Path, text: str, feature: int):
    fixture = (f"EnableExplicit\n#ANVIL_V3D_CONSOLE={feature}\n#SCR_SRC_NONE=0\n#SCR_SRC_HDMI=1\n#SCR_SRC_DSI=2\n"
               "Global gScrSrc.i\nGlobal cacheCalls.i\n"
               "Global gScreenDsiEarlyCacheArm.i\n"
               "Procedure.i CacheEnable()\n cacheCalls=cacheCalls+1\n ProcedureReturn 1\nEndProcedure\n" +
               procedure(text, "ScreenDsiEarlyCacheArm") + "\n" +
               procedure(text, "ScreenDsiEarlyCacheTake") + "\n" +
               procedure(text, "ScreenDsiEarlyCache") +
               "\nProcedure.i Probe(src.i, armed.i)\n gScrSrc=src\n cacheCalls=0\n gScreenDsiEarlyCacheArm=0\n If armed<>0\n ScreenDsiEarlyCacheArm()\n EndIf\n armed=ScreenDsiEarlyCacheTake()\n ScreenDsiEarlyCache(armed)\n ProcedureReturn cacheCalls + gScreenDsiEarlyCacheArm*10\nEndProcedure\n"
               "Procedure.i Main()\n ProcedureReturn Probe(#SCR_SRC_DSI,1)\nEndProcedure\n")
    src, image = work / f"early{feature}.pi4", work / f"early{feature}.img"
    src.write_text(fixture, encoding="utf-8")
    run = subprocess.run([str(compiler), "--compile", str(src), "-t", "pi4", "-s", "--entry-returns",
                          "--load-addr", hex(LOAD), "--bss-addr", hex(BSS),
                          "--stack-addr", hex(STACK), "-o", str(image)], cwd=ROOT,
                         capture_output=True, text=True, timeout=120)
    if run.returncode or not image.exists():
        raise AssertionError("fixture build failed\n" + run.stdout + run.stderr)
    # EVERY COMPILE IN tools/ ASKS THE COUNTER. This one builds a fixture, so
    # record_build() answers "not a board file" and nothing moves - the decision
    # about what is a build of the monitor belongs to one module, not to each
    # gate's reading of its own fixture. If this gate ever compiles a board file
    # instead, the count follows it with nothing to remember.
    build_count.record_build(src, "pi4", image,
                             by="tools/screen_early_cache_check.py", compiler=compiler)
    entries = {}
    for line in Path(str(image) + ".dbg").read_text(encoding="utf-8-sig").splitlines():
        fields = line.split("|")
        if len(fields) >= 4 and fields[0] == "1" and fields[1].isdigit():
            entries[fields[2].lower()] = LOAD + int(fields[1])
    return image.read_bytes(), entries["probe"]


def execute(a64, product, src: int, armed: int) -> int:
    blob, entry = product
    cpu = a64.A64()
    cpu.memory = {LOAD + i: b for i, b in enumerate(blob)}
    cpu.pc, cpu.sp, cpu.x[30], cpu.x[0], cpu.x[1] = entry, STACK, RETURN, src, armed
    for _ in range(100000):
        if cpu.pc == RETURN:
            return cpu.x[0]
        cpu.step()
    raise AssertionError("emitted policy did not return")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--interp", type=Path, default=ROOT / "tools/a64/a64_interp.py")
    args = ap.parse_args()
    compiler = emitted.required_path(args.compiler, "PMF_COMPILER")
    a64 = emitted.load_interpreter(args.interp)
    text = SOURCE.read_text(encoding="utf-8")
    validate_order(text)
    with tempfile.TemporaryDirectory(prefix="anvil-screen-early-cache-") as td:
        products = [build(compiler, Path(td), text, feature) for feature in (0, 1)]
        results = [[execute(a64, product, src, armed)
                    for armed in (0, 1) for src in (0, 1, 2)] for product in products]
    if results != [[0, 0, 0, 0, 0, 1], [0, 0, 0, 0, 0, 1]]:
        raise AssertionError("emitted NONE/HDMI/DSI policy mismatch: " + repr(results))
    mutants = (
        ("cache after DMA", "  ScreenDsiEarlyCache(earlyCache)\n", "", "  gDma = ScreenDmaUp()\n", "  gDma = ScreenDmaUp()\n  ScreenDsiEarlyCache(earlyCache)\n"),
        ("cache after clear", "  ScreenDsiEarlyCache(earlyCache)\n", "", "  DisplayClear(DisplayRGB(0, 0, 40))\n", "  DisplayClear(DisplayRGB(0, 0, 40))\n  ScreenDsiEarlyCache(earlyCache)\n"),
        ("missing cache", "  ScreenDsiEarlyCache(earlyCache)\n", "", "", ""),
    )
    for label, old1, new1, old2, new2 in mutants:
        changed = text.replace(old1, new1, 1)
        if old2:
            changed = changed.replace(old2, new2, 1)
        try:
            validate_order(changed)
        except AssertionError:
            print("  rejected structural mutation: " + label)
        else:
            raise AssertionError("mutation survived: " + label)
    print("screen_early_cache_check: PASS - boot-arm NONE/HDMI/DSI policy at feature 0/1 and three order mutations")
    print("  cache leaf stubbed; no MMU, display, DMA, panel or timing claim")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

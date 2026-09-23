#!/usr/bin/env python3
"""Compile and run Pi3 payload/backbuffer reservation guards from production.

The gate extracts the actual Pi3 map constants and address-window procedures,
then executes boundary and stack-admission cases in emitted A64 code. It
checks the NC-rounded reserve gap and dynamic firmware scanout ownership.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

import tcp_multiif_emitted_check as emitted

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "RaspberryPi3" / "Board" / "memmap.pi3"
MMU = ROOT / "RaspberryPi3" / "Lib" / "mmu.pi3"
FRAMEBUFFER = ROOT / "RaspberryPi3" / "Lib" / "framebuffer.pbi"
MEMRANGE = ROOT / "Anvil" / "Core" / "memrange.pbi"
FIXTURE = ROOT / "RaspberryPi3" / "Tests" / "render_reserve_gate.pi3"
LOAD, STACK = emitted.LOAD, emitted.STACK

CONSTANTS = (
    "#MMU3_PERIPH_BASE", "#MON_STACK_LO", "#MON_DATA_LO", "#MON_DATA_HI",
    "#MON_STACK", "#MON_STACK_HI", "#MON_TABLES_LO", "#MON_TABLES_HI",
    "#MON_DTB_LO", "#MON_DTB_HI", "#MON_HANDOFF_LO", "#MON_HANDOFF_HI",
    "#MON_STAGE_LO", "#MON_STAGE_HI", "#MON_FB_RENDER_LO",
    "#MON_FB_RENDER_HI", "#PAY0_LO", "#PAY1_LO", "#PAY0_HI_MAX",
    "#MON_REGION_CODE", "#MON_REGION_DATA", "#MON_REGION_STACK",
    "#MON_REGION_TABLES", "#MON_REGION_DTB", "#MON_REGION_HANDOFF",
    "#MON_REGION_STAGE",
    "#MON_REGION_FB_RENDER", "#MON_REGION_FB_SCANOUT", "#MON_REGION_COUNT",
)
MAP_PROC_HEADERS = (
    "Procedure.i HwMonRegions()",
    "Procedure.i HwMonRegionLo(i.i)",
    "Procedure.i HwMonRegionHi(i.i)",
    "Procedure.i HwPayWindows()",
    "Procedure.i HwPayLo(i.i)",
    "Procedure.i HwPayHi(i.i)",
    "Procedure.i HwPmfStackAllowed(lo.i, hi.i)",
)


def extract_proc(source: str, header: str) -> str:
    if source.count(header) != 1:
        raise SystemExit(f"render-reserve gate: {header!r} count {source.count(header)}")
    start = source.index(header)
    end = source.find("\nEndProcedure", start)
    if end < 0:
        raise SystemExit(f"render-reserve gate: no EndProcedure for {header}")
    return source[start:end + len("\nEndProcedure")] + "\n"


def extract_constant(source: str, name: str) -> str:
    matches = re.findall(r"^\s*%s\s*=.*$" % re.escape(name), source, re.MULTILINE)
    if len(matches) != 1:
        raise SystemExit(f"render-reserve gate: {name} definition count {len(matches)}")
    return matches[0].split(";")[0].strip() + "\n"


def production_parts() -> dict[str, str]:
    m = MAP.read_text(encoding="utf-8")
    mmu = MMU.read_text(encoding="utf-8")
    fb = FRAMEBUFFER.read_text(encoding="utf-8")
    mr = MEMRANGE.read_text(encoding="utf-8")
    for name in ("#PI3_FB_RENDER_BASE", "#PI3_FB_RENDER_BYTES"):
        line = extract_constant(fb, name).replace(name, {
            "#PI3_FB_RENDER_BASE": "#MON_FB_RENDER_LO",
            "#PI3_FB_RENDER_BYTES": "#MON_FB_RENDER_BYTES",
        }[name])
        expected = {"#MON_FB_RENDER_LO": "$3000000", "#MON_FB_RENDER_BYTES": "9216000"}
        if not re.search(r"=\s*%s\b" % re.escape(expected[line.split("=")[0].strip()]), line):
            raise SystemExit(f"render-reserve gate: framebuffer/map reserve mismatch: {line.strip()}")
    out = {
        "constants": "".join(
            extract_constant(mmu if n == "#MMU3_PERIPH_BASE" else m, n)
            for n in CONSTANTS
        ),
        "fb_constants": "".join(
            extract_constant(fb, n) for n in ("#PI3_FB_RENDER_BASE", "#PI3_FB_RENDER_BYTES")
        ),
        "map_procs": "".join(extract_proc(m, h) for h in MAP_PROC_HEADERS),
        "in_payload": extract_proc(mr, "Procedure.i InPayload(lo.i, hi.i)") +
                      extract_proc(mr, "Procedure.i HitsMonitor(lo.i, hi.i)"),
    }
    return out


def source(parts: dict[str, str]) -> str:
    text = FIXTURE.read_text(encoding="utf-8")
    text = text.replace("; @@PRODUCTION_RENDER_MAP_CONSTANTS@@", parts["constants"] + parts["fb_constants"])
    text = text.replace("; @@PRODUCTION_RENDER_MAP_PROCEDURES@@", parts["map_procs"] + parts["in_payload"])
    if "@@PRODUCTION_" in text:
        raise SystemExit("render-reserve gate: unfilled production marker")
    return text


def compile_fixture(compiler: Path, work: Path, text: str) -> Path:
    staged = work / compiler.name
    if not staged.exists():
        shutil.copy2(compiler, staged)
    boards = ROOT / "Boards"
    if boards.is_dir() and not (work / "Boards").exists():
        shutil.copytree(boards, work / "Boards")
    intr = ROOT / "RaspberryPi3" / "Intrinsics"
    if intr.is_dir() and not (work / "RaspberryPi3" / "Intrinsics").exists():
        (work / "RaspberryPi3").mkdir(exist_ok=True)
        shutil.copytree(intr, work / "RaspberryPi3" / "Intrinsics")
    src = work / "pi3_render_reserve_gate.pi3"
    src.write_text(text, encoding="utf-8", newline="\n")
    img = work / "pi3_render_reserve_gate.img"
    run = subprocess.run(
        [str(staged), "--compile", str(src), "-t", "pi3", "--load-addr", hex(LOAD),
         "--stack-addr", hex(STACK), "--entry-returns", "-o", str(img), "-s"],
        cwd=ROOT, env={**os.environ, "PMF_ROOT": str(ROOT)},
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise SystemExit("render-reserve gate: compile failed\n" + run.stdout)
    return img


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"))
    args = ap.parse_args()
    compiler = emitted.required_path(args.compiler, "PMF_COMPILER")
    interp = emitted.required_path(args.interp or str(ROOT / "tools" / "a64" / "a64_interp.py"), "PMF_A64_INTERP")
    a64 = emitted.load_interpreter(interp)
    parts = production_parts()
    with tempfile.TemporaryDirectory(prefix="anvil-pi3-render-reserve-") as d:
        image = compile_fixture(compiler, Path(d), source(parts))
        result, steps = emitted.execute(a64, image)
    if result:
        raise SystemExit(f"pi3_render_reserve_check: FAIL assertion {result} after {steps:,} instructions")
    print(f"pi3_render_reserve_check: PASS - 25 assertions / {steps:,} A64 instructions")
    print("  fixed render reserve/NC gap, firmware-bounded payload windows, dynamic DTB/scanout exclusions, initial-stack overlap guards")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

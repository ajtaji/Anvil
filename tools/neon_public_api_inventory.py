#!/usr/bin/env python3
"""Build a deterministic inventory of the public Neon surface and its callers."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEON = ROOT / "RaspberryPi4" / "Lib" / "neon.pi4"
SOURCE_SUFFIXES = {".pi4", ".pbi", ".unoq"}
PROC_RE = re.compile(r"^\s*Procedure(\.i)?\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)")
STRUCT_RE = re.compile(r"^\s*Structure\s+([A-Za-z_][A-Za-z0-9_]*)")
CONST_RE = re.compile(r"^\s*(#NEON_[A-Za-z0-9_]+)\s*=")
CALL_RE = re.compile(r"\b(Neon[A-Za-z0-9_]*)\s*\(")
BACKEND = {"NeonInit","NeonShutdown","NeonFrameBegin","NeonFrameEnd","NeonRebindSurface","NeonRetarget","Neon_Box","NeonFanBegin","NeonFanPoint","NeonFanEnd","NeonFanOutline","NeonLinesBegin","NeonLine","NeonLinesEnd","Neon_ScissorSet","Neon_ScissorClear","NeonFontUse","NeonFontSetup","NeonFontDefaults","Neon_Text","Neon_TextRight","Neon_TextCentre","Neon_TextTex","Neon_TextTexRight","Neon_TextTexCentre","Neon_TexAtlasBuild","NeonDrawBackendInstall","NeonDrawBackendClear","NeonDrawBackendActive","NeonMeasureBackendInstall","NeonMeasureBackendClear","NeonMeasureBackendActive"}
NATIVE = {"Neon_UsBegin","Neon_UsClean","Neon_UsBin","Neon_UsRender","Neon_ArenaNeed","Neon_ArenaTop","Neon_GuardAddr","Neon_VertsAddr","Neon_ShrecAddr","Neon_UnifAddr","Neon_BclAddr","Neon_PtBytes","Neon_BclBytes"}


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()

def renderer_classification(name):
    return "native-only-diagnostic" if name in NATIVE else ("backend-dispatched" if name in BACKEND else "renderer-neutral")

def category(name):
    if name in NATIVE: return "native-only diagnostic"
    if name in {"NeonInit","NeonShutdown","NeonFrameBegin","NeonFrameEnd"}: return "lifecycle"
    if name in {"NeonArena","NeonSurface","NeonSurfaceOriented","NeonSurfaceMapSpan","NeonRenderCapacity","NeonRebindSurface","NeonRetarget","NeonRbSwap"}: return "surface"
    if name in BACKEND: return "font/atlas" if ("Font" in name or "Text" in name or "Atlas" in name) else "render operation"
    if name in {"Neon_Error","Neon_Ready","Neon_Draws","Neon_Boxes","Neon_Glyphs","Neon_Runs","Neon_Verts","Neon_TexDraws","Neon_TexGlyphs","Neon_TexVerts","Neon_Clipped"}: return "status/metric"
    if name in {"Neon_RGBA","Neon_RGB","Neon_R","Neon_G","Neon_B","Neon_A","Neon_WithAlpha","Neon_Mul","Neon_Mul3","Neon_Lift"}: return "colour/helper"
    return "renderer-neutral UI/state"


def inventory() -> dict:
    lines = NEON.read_text(encoding="utf-8").splitlines()
    procedures = []
    structures = []
    constants = []
    for number, line in enumerate(lines, 1):
        m = PROC_RE.match(line)
        if m and m.group(2).startswith("Neon"):
            procedures.append({"name": m.group(2), "return_suffix": m.group(1) or "", "return_type": "i" if m.group(1) else "void", "params": m.group(3).strip(), "line": number, "category": category(m.group(2)), "renderer_classification": renderer_classification(m.group(2))})
        m = STRUCT_RE.match(line)
        if m and m.group(1).startswith("Neon"):
            structures.append({"name": m.group(1), "line": number})
        m = CONST_RE.match(line)
        if m:
            constants.append({"name": m.group(1), "line": number})

    callers = {}
    ignored_dirs = {".git", "build", "runs", "tmp", "_work", ".migration-local"}
    for path in sorted(ROOT.rglob("*")):
        if (not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES or path == NEON
                or any(part in ignored_dirs for part in path.parts)):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        found = {}
        for line_number, raw_line in enumerate(text.splitlines(), 1):
            line = raw_line.split(";", 1)[0]
            if not line.strip() or re.match(r"^\s*(Procedure|Declare)", line): continue
            for match in CALL_RE.finditer(line): found.setdefault(match.group(1), []).append(line_number)
        if found:
            callers[rel(path)] = {k: sorted(v) for k, v in sorted(found.items())}

    public_names = [p["name"] for p in procedures]
    canonical = {
        "procedures": [(p["name"], p["return_suffix"], p["return_type"], p["params"], p["category"], p["renderer_classification"]) for p in procedures],
        "structures": [s["name"] for s in structures],
        "constants": [c["name"] for c in constants],
    }
    api_sha256 = hashlib.sha256(json.dumps(canonical, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    return {
        "schema": 2,
        "source": rel(NEON),
        "api_sha256": api_sha256,
        "public_procedure_count": len(procedures),
        "public_procedures": procedures,
        "public_structures": structures,
        "public_constants": constants,
        "caller_file_count": len(callers),
        "callers": callers,
        "called_public_names": sorted({name for rows in callers.values() for name in rows if name in public_names}),
        "unresolved_neon_calls": sorted({name for rows in callers.values() for name in rows if name not in public_names}),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = inventory()
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

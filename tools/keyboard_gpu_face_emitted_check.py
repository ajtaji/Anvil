#!/usr/bin/env python3
"""Grade the V3D tier's key labels, and the route that puts them on the panel.

This is an emitted-code gate.  It LIFTS TWO PRODUCTION PROCEDURES verbatim
- nothing is copied and nothing is paraphrased, and if either pair of
fences moves the gate refuses to build rather than test a transcript:

  * TouchKeyboardComposeCpu, from RaspberryPi4/Board/banner_clock.pi4,
    run with gCursorGpuOwned = 1 - the tier the bench panel runs on;
  * ScrGpuKeepLogicalBand, from RaspberryPi4/Board/screen_source.pi4,
    run over the real rotation arithmetic in screen_geom.pi4.

What it grades is the thing the source cannot say.  On the V3D tier the
key labels used to be the engine's one-bit cell face magnified - the
staircase that was called blocky, on the only panel this monitor is
actually used on.  They are now the same 30 px anti-aliased face the
framebuffer tier uses, composed by the same procedure and carried to the
panel by the same route the banner's smooth title already takes.  This
gate executes that: every label at six surfaces, the whole band painted
so the transpose has something complete to move, the drain before the
copy, the pointer left alone on a tier with no save-under, and the
carried rectangle checked against the checker's own arithmetic over the
panel's geometry.

  PMFC=<pmfc.exe> PMF_A64_INTERP=<a64_interp.py> \
      py -3 tools/keyboard_gpu_face_emitted_check.py
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
ADAPTER = ROOT / "RaspberryPi4" / "Board" / "banner_clock.pi4"
SEAM = ROOT / "RaspberryPi4" / "Board" / "screen_source.pi4"
GATE = ROOT / "RaspberryPi4" / "Tests" / "keyboard_gpu_face_emitted_gate.pi4"
FONTS = ROOT / "RaspberryPi4" / "Monitor" / "anvil_fonts.pi4"
LIFT_COMPOSE = "_keyboard_gpu_face_lift.pbi"
LIFT_KEEP = "_keyboard_gpu_keep_lift.pbi"

COMPOSE_BEGIN = "; ANVIL-TOUCH-KEYBOARD-COMPOSE-BEGIN"
COMPOSE_END = "; ANVIL-TOUCH-KEYBOARD-COMPOSE-END"
KEEP_BEGIN = "; ANVIL-SCR-KEEP-LOGICAL-BAND-BEGIN"
KEEP_END = "; ANVIL-SCR-KEEP-LOGICAL-BAND-END"

LOAD = 0x00400000
STACK = 0x03000000
LOADER_LR = 0xDEAD0000
STEP_LIMIT = 120_000_000
MMIO = 0xFC000000

MAGIC_AT = 0x06000000
MAGIC = 0x4B424750
META = 0x06000100
SCEN = 0x06010000
STRIDE = 0x00010000
KEEP = 0x06100000
KEEPSZ = 0x00001000

F_OK, F_ITEMS, F_LABELS, F_SMOOTH, F_BITMAP = 0, 8, 16, 24, 32
F_SCALEEND, F_FIDMIN, F_FIDMAX, F_TEXTN = 40, 48, 56, 64
F_RECTS, F_R0X, F_R0Y, F_R0W, F_R0H = 72, 80, 88, 96, 104
F_BANDY, F_BANDH, F_LW = 112, 120, 128
F_PRESN, F_PRESY0, F_PRESY1 = 136, 144, 152
F_LASTWRITE, F_BARRIER, F_PRESENTAT, F_CURSORAT = 160, 168, 176, 184
F_CURSOROPS, F_OUTSIDE = 192, 200

REC, RECSZ = 0x400, 96
R_FACE, R_BOXX, R_BOXY, R_BOXW, R_BOXH = 0, 8, 16, 24, 32
R_DRAWX, R_DRAWW, R_TOP, R_DRAWH, R_TEXT = 40, 48, 56, 64, 72

K_RC, K_DST, K_SRC, K_WIDE, K_TALL = 0, 8, 16, 24, 32
K_PITCH, K_DMA, K_ROWS, K_DRAIN, K_LAST = 40, 48, 56, 64, 72

SMOOTH, BITMAP = 1, 2
PANEL_W, PANEL_H = 800, 1280
FB_SCAN, FB_DRAW = 0x08A00000, 0x08E00000

# slot, page, logicalW, logicalH, ppi, displayScale, every label smooth?, note
SCENARIOS = (
    (0, 0, 1280, 800, 149, 1, True,
     "the bench panel, landscape - the tier and the geometry a finger actually touches"),
    (1, 0, 800, 1280, 149, 1, None,
     "the panel's own portrait scan, where the keys are narrower"),
    (2, 0, 1280, 800, 149, 2, True,
     "the bench panel at the large-text setting"),
    (3, 1, 1280, 800, 149, 1, True,
     "the symbol page, landscape"),
    (4, 0, 640, 480, 149, 1, False,
     "the smallest surface this arrangement fits - the fallback's reason to exist"),
    (5, 0, 1280, 800, 0, 1, True,
     "a screen that never said how big it is: the display-scale fallback"),
)

# slot, rotation, dma offered, note
CARRIES = (
    (1, 90, 0, "the bench rotation, carried by the CPU mover"),
    (2, 90, 1, "the same, carried by the DMA engine"),
    (3, 270, 0, "the other landscape"),
    (4, 0, 0, "the panel's own scan direction"),
    (5, 180, 0, "upside down, where the scaler's mirrors do the turning"),
)

REDIRECT = {
    "TouchKeyboardDrawX(i)": "KgDrawX(i)",
    "TouchKeyboardDrawY(i)": "KgDrawY(i)",
    "TouchKeyboardDrawW(i)": "KgDrawW(i)",
    "TouchKeyboardDrawH(i)": "KgDrawH(i)",
    "TouchKeyboardDrawText(i)": "KgDrawText(i)",
}

# Plausible mistakes in the lifted composer.  Each MUST turn the gate red.
COMPOSE_MUTANTS = (
    ("the GPU tier is not composed at all - the old early return",
     "  gpu = Bool(gCursorGpuOwned <> 0)\n",
     "  gpu = 0\n  If gCursorGpuOwned <> 0\n    ProcedureReturn\n  EndIf\n"),
    ("the band is painted only where a key changed, so the transpose "
     "carries the last frame between the keys",
     "  If gpu <> 0\n    gTkbCpuDamage = #TKB_DAMAGE_TRANSITION\n  EndIf\n", ""),
    ("the drain before the copy is left out",
     "    a64_barrier()\n  EndIf\n  ScrPresent(y0, y1)\n",
     "  EndIf\n  ScrPresent(y0, y1)\n"),
    ("the drain happens after the copy instead of before it",
     "    a64_barrier()\n  EndIf\n  ScrPresent(y0, y1)\n",
     "  EndIf\n  ScrPresent(y0, y1)\n  If gpu <> 0\n    a64_barrier()\n  EndIf\n"),
    ("the pointer's save-under is lifted on a tier that has none",
     "    hadCur = 0\n  EndIf\n", "  EndIf\n"),
    ("the pointer is never written back over the finished band",
     "  If gpu <> 0\n    TouchKeyboardPresentedCursor(y0, y1)\n  EndIf\n", ""),
    ("the pass draws the prompt-side button on a tier that already has it",
     "  If gpu <> 0 And TouchKeyboardViewVisible() = 0\n", "  If 1 = 0\n"),
    ("the smooth face is never tried, so the labels stay blocky here too",
     "      If h >= #FONT_keys_LINEH\n", "      If h >= 100000\n"),
    ("a label wider than its key is set in the smooth face anyway",
     "        If sw <= w\n", "        If 1 <> 0\n"),
    ("the smooth label is left-aligned instead of centred",
     "          DrawSmoothText(x + (w - sw) / 2, ", "          DrawSmoothText(x, "),
    ("a box the smooth face does not fit loses its label altogether",
     "      If drawn = 0\n", "      If drawn = 2\n"),
)

# ... and in the lifted carry.
KEEP_MUTANTS = (
    ("the carry takes only the band's first row, so a turned panel gets a "
     "one-pixel column of it",
     "  v = ScrMapX(rot, 0, y1, pw, ph)\n  If v < loX : loX = v : EndIf\n"
     "  If v > hiX : hiX = v : EndIf\n"
     "  v = ScrMapX(rot, lw - 1, y1, pw, ph)\n  If v < loX : loX = v : EndIf\n"
     "  If v > hiX : hiX = v : EndIf\n", ""),
    ("the carry copies the logical rectangle, ignoring the turn",
     "  loX = ScrMapX(rot, 0, y0, pw, ph)\n", "  loX = 0\n"),
    ("the carry moves the band the wrong way, out of the target and into "
     "the panel",
     "    If DmaCopy2D(dst, pitch, src, pitch, wide, tall) <> 0\n",
     "    If DmaCopy2D(src, pitch, dst, pitch, wide, tall) <> 0\n"),
    ("the CPU mover's writes are not drained before the present reads them",
     "  a64_barrier()\n  ProcedureReturn 1\n", "  ProcedureReturn 1\n"),
    ("the carry runs even when the renderer is drawing straight into the front",
     "  If front = 0 Or renderBase = 0 Or renderBase = front\n",
     "  If front = 0 Or renderBase = 0\n"),
)


def locate(env_name: str, given, fallbacks) -> pathlib.Path:
    for candidate in [given, os.environ.get(env_name)]:
        if candidate:
            path = pathlib.Path(candidate).expanduser()
            if path.is_file():
                return path.resolve()
    for path in fallbacks:
        if path.is_file():
            return path.resolve()
    raise SystemExit(f"keyboard GPU face gate: {env_name} was not found; set it or pass its option")


def load_interpreter(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("anvil_kbdgpuface_a64", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"keyboard GPU face gate: cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def between(path: pathlib.Path, begin: str, end: str) -> str:
    text = path.read_text(encoding="utf-8")
    start = text.find(begin)
    stop = text.find(end)
    if start < 0 or stop < 0 or stop < start:
        raise SystemExit(f"keyboard GPU face gate: the fences {begin[2:]} / {end[2:]} are not "
                         f"both in {path.name} in order; the gate cannot lift what it grades")
    return text[start + len(begin):stop]


def lift_compose() -> str:
    body = between(ADAPTER, COMPOSE_BEGIN, COMPOSE_END)
    for was, now in REDIRECT.items():
        if body.count(was) < 1:
            raise SystemExit(f"keyboard GPU face gate: the lifted composer no longer reads "
                             f"{was}, so the gate cannot attribute a label to a box")
        body = body.replace(was, now)
    return ("; LIFTED VERBATIM from RaspberryPi4/Board/banner_clock.pi4 between\n"
            "; the compose fences by tools/keyboard_gpu_face_emitted_check.py. The\n"
            "; only edit is that the view's four rectangle accessors and its label\n"
            "; accessor are read through the gate's recorders. Do not edit this\n"
            "; file; edit the adapter.\n" + body)


def lift_keep() -> str:
    return ("; LIFTED VERBATIM from RaspberryPi4/Board/screen_source.pi4 between\n"
            "; the keep-logical-band fences by\n"
            "; tools/keyboard_gpu_face_emitted_check.py. Nothing is edited. Do not\n"
            "; edit this file; edit the seam.\n" + between(SEAM, KEEP_BEGIN, KEEP_END))


def parse_key_advances() -> dict[int, int]:
    """The advance byte of every glyph in the baked 30 px face, read out of
    the generated source the board compiles - the checker's own reading of
    the same table the image reads."""
    text = FONTS.read_text(encoding="utf-8")
    at = text.find("fontKeysMeta:")
    if at < 0:
        raise SystemExit("keyboard GPU face gate: anvil_fonts.pi4 has no fontKeysMeta")
    end = text.find("fontKeysPix:", at)
    first = int(re.search(r"#FONT_keys_FIRST\s*=\s*(\d+)", text).group(1))
    count = int(re.search(r"#FONT_keys_COUNT\s*=\s*(\d+)", text).group(1))
    data: list[int] = []
    for line in text[at:end].splitlines():
        line = line.strip()
        if not line.startswith("Data.b"):
            continue
        for item in line[len("Data.b"):].split(","):
            item = item.strip()
            if item.startswith("$"):
                data.append(int(item[1:], 16))
    return {first + i: data[i * 8] for i in range(count)}


def smooth_width(label: str, advances: dict[int, int]) -> int:
    return sum(advances.get(ord(c), 0) for c in label)


def stage(work: pathlib.Path, compose: str, keep: str) -> pathlib.Path:
    for folder in ("Anvil/Core", "Anvil/Graphics", "RaspberryPi4/Board",
                   "RaspberryPi4/Monitor", "RaspberryPi4/Tests"):
        (work / folder).mkdir(parents=True, exist_ok=True)
    for rel in ("Anvil/Core/touch_keyboard.pbi",
                "Anvil/Core/boot_transcript.pbi",
                "Anvil/Graphics/touch_keyboard_view.pbi",
                "RaspberryPi4/Board/console.pi4",
                "RaspberryPi4/Board/screen_geom.pi4",
                "RaspberryPi4/Monitor/anvil_fonts.pi4"):
        shutil.copy2(ROOT / rel, work / rel)
    shutil.copy2(GATE, work / "RaspberryPi4" / "Tests" / GATE.name)
    (work / "RaspberryPi4" / "Tests" / LIFT_COMPOSE).write_text(compose, encoding="utf-8")
    (work / "RaspberryPi4" / "Tests" / LIFT_KEEP).write_text(keep, encoding="utf-8")
    src = ROOT / "RaspberryPi4" / "Intrinsics"
    if src.is_dir():
        shutil.copytree(src, work / "RaspberryPi4" / "Intrinsics", dirs_exist_ok=True)
    if (ROOT / "Boards").is_dir():
        shutil.copytree(ROOT / "Boards", work / "Boards", dirs_exist_ok=True)
    if (ROOT / "keywords.def").is_file():
        shutil.copy2(ROOT / "keywords.def", work / "keywords.def")
    return work / "RaspberryPi4" / "Tests" / GATE.name


def build(compiler: pathlib.Path, work: pathlib.Path, source: pathlib.Path) -> pathlib.Path:
    image = work / "keyboard_gpu_face_gate.img"
    command = [str(compiler), source.relative_to(work).as_posix(),
               "-t", "pi4", "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
               "--entry-returns", "-o", str(image), "-s"]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(work)
    run = subprocess.run(command, cwd=work, env=env, text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if run.returncode or "pmfc: OK" not in run.stdout or not image.is_file():
        raise SystemExit("keyboard GPU face gate: compile failed\n" + run.stdout)
    return image


def execute(a64, image: pathlib.Path):
    cpu = a64.A64()
    for i, byte in enumerate(image.read_bytes()):
        cpu.memory[LOAD + i] = byte
    a64.attach_symbols(cpu, image, LOAD)
    cpu.pc, cpu.sp, cpu.x[30] = LOAD, STACK, LOADER_LR

    def guard(addr: int, write: bool) -> None:
        if addr >= MMIO:
            kind = "write" if write else "read"
            raise SystemExit(f"keyboard GPU face gate: unexpected MMIO {kind} at ${addr:08X} - "
                             "this gate is supposed to touch no hardware at all")

    def load(addr: int, size: int) -> int:
        cpu.align_guard(addr, size, False)
        guard(addr, False)
        return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr: int, value: int, size: int) -> None:
        cpu.align_guard(addr, size, True)
        guard(addr, True)
        for i in range(size):
            cpu.memory[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    for steps in range(STEP_LIMIT):
        if cpu.pc == LOADER_LR:
            return cpu, cpu.x[0] & 0xFFFFFFFF, steps
        cpu.step()
    raise SystemExit(f"keyboard GPU face gate: the probe did not return in {STEP_LIMIT} instructions")


def u64(cpu, addr: int) -> int:
    v = sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(8))
    return v - (1 << 64) if v >= 1 << 63 else v


def cstr(cpu, addr: int, limit: int = 64) -> str:
    out = []
    for i in range(limit):
        byte = cpu.memory.get(addr + i, 0)
        if byte == 0:
            break
        out.append(chr(byte))
    return "".join(out)


class Grader:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.checks = 0

    def want(self, name: str, condition: bool, detail: str = "") -> None:
        self.checks += 1
        if not condition:
            self.failures.append(name + ((": " + detail) if detail else ""))


def physical_band(rot: int, y0: int, y1: int):
    """The checker's OWN arithmetic for where a full-width logical row band
    lands on the panel.  Deliberately written out per rotation rather than
    calling anything the image also calls."""
    # The console's own width and height at this rotation: turned, the
    # panel's 800 x 1280 is a 1280 x 800 console.
    lw = PANEL_H if rot in (90, 270) else PANEL_W
    lh = PANEL_W if rot in (90, 270) else PANEL_H
    if rot == 90:
        # a logical row is a physical column, counted back from the right
        return (lh - 1 - y1, 0, lh - 1 - y0, lw - 1)
    if rot == 270:
        return (y0, 0, y1, lw - 1)
    # 0 and 180 are the identity - the scaler's two mirror bits do 180 at
    # scan-out, which is why nothing is reversed here.
    return (0, y0, lw - 1, y1)


def grade(cpu, rc: int, advances: dict[int, int]) -> Grader:
    g = Grader()
    g.want("the probe returned 0", rc == 0, str(rc))
    g.want("the record carries its magic", u64(cpu, MAGIC_AT) & 0xFFFFFFFF == MAGIC)
    lineh = u64(cpu, META)
    asc = u64(cpu, META + 8)
    g.want("the key face has a line height", lineh > 0, str(lineh))
    g.want("the key face has an ascent inside its line", 0 < asc <= lineh, f"{asc}/{lineh}")

    for slot, page, lw, lh, ppi, ds, all_smooth, note in SCENARIOS:
        b = SCEN + slot * STRIDE
        tag = f"slot {slot} ({note})"
        ok = u64(cpu, b + F_OK)
        g.want(f"{tag} lays out", ok == 1)
        if ok != 1:
            continue
        labels = u64(cpu, b + F_LABELS)
        smooth = u64(cpu, b + F_SMOOTH)
        bitmap = u64(cpu, b + F_BITMAP)
        textn = u64(cpu, b + F_TEXTN)
        bandY = u64(cpu, b + F_BANDY)
        bandH = u64(cpu, b + F_BANDH)
        bandW = u64(cpu, b + F_LW)

        # THE COMPOSER RAN. It used to return at its second line when the
        # GPU owned the frame, and a gate that only looked at faces would
        # have called an empty pass perfect.
        g.want(f"{tag} composed the band on the GPU tier at all",
               labels > 0 and u64(cpu, b + F_RECTS) > 0,
               f"{labels} labels, {u64(cpu, b + F_RECTS)} rectangles")
        g.want(f"{tag} draws every label the view asked for",
               labels == textn and labels > 0, f"{labels} drawn, {textn} asked for")
        g.want(f"{tag} counts add up", smooth + bitmap == labels)
        g.want(f"{tag} restores the library magnification",
               u64(cpu, b + F_SCALEEND) == ds, str(u64(cpu, b + F_SCALEEND)))

        fidmin, fidmax = u64(cpu, b + F_FIDMIN), u64(cpu, b + F_FIDMAX)
        if smooth or fidmax >= 0:
            g.want(f"{tag} asks only for the key face",
                   fidmin == 3 and fidmax == 3, f"{fidmin}..{fidmax}")

        # THE WHOLE BAND, PAINTED FIRST. What the seam moves is a range of
        # logical rows over the GPU's physical frame; an unpainted pixel in
        # them is last frame's bytes on the glass.
        g.want(f"{tag} fills the whole band before anything else",
               u64(cpu, b + F_R0X) <= 0 and u64(cpu, b + F_R0Y) <= bandY
               and u64(cpu, b + F_R0X) + u64(cpu, b + F_R0W) >= bandW
               and u64(cpu, b + F_R0Y) + u64(cpu, b + F_R0H) >= bandY + bandH,
               f"first rect {u64(cpu, b + F_R0X)},{u64(cpu, b + F_R0Y)} "
               f"{u64(cpu, b + F_R0W)}x{u64(cpu, b + F_R0H)} for a band "
               f"0,{bandY} {bandW}x{bandH}")
        g.want(f"{tag} draws nothing outside the band",
               u64(cpu, b + F_OUTSIDE) == 0,
               f"{u64(cpu, b + F_OUTSIDE)} items left it")

        # AND THE ROWS PRESENTED ARE THE BAND'S, exactly - the rectangle
        # the carry will preserve afterwards is derived from the same two.
        g.want(f"{tag} presents once", u64(cpu, b + F_PRESN) == 1,
               str(u64(cpu, b + F_PRESN)))
        g.want(f"{tag} presents exactly the band's rows",
               u64(cpu, b + F_PRESY0) == bandY
               and u64(cpu, b + F_PRESY1) == bandY + bandH - 1,
               f"{u64(cpu, b + F_PRESY0)}..{u64(cpu, b + F_PRESY1)} "
               f"for {bandY}..{bandY + bandH - 1}")

        # THE DRAIN, BEFORE THE COPY, BY EXECUTION.
        last, drain, present = (u64(cpu, b + F_LASTWRITE), u64(cpu, b + F_BARRIER),
                                u64(cpu, b + F_PRESENTAT))
        g.want(f"{tag} drains its writes", drain > 0)
        g.want(f"{tag} drains AFTER the last pixel it wrote", drain > last,
               f"last write {last}, drain {drain}")
        g.want(f"{tag} drains BEFORE the copy that reads them", present > drain,
               f"drain {drain}, present {present}")

        # THE POINTER. No save-under is touched on this tier, and where one
        # is on the glass over the band the mask is written again after it.
        g.want(f"{tag} leaves the pointer's save-under alone",
               u64(cpu, b + F_CURSOROPS) == 0, str(u64(cpu, b + F_CURSOROPS)))
        if slot == 0:
            g.want(f"{tag} writes the pointer back over the finished band",
                   u64(cpu, b + F_CURSORAT) > present,
                   f"pointer {u64(cpu, b + F_CURSORAT)}, present {present}")

        if all_smooth is True:
            g.want(f"{tag} sets EVERY key label in the smooth face",
                   bitmap == 0, f"{bitmap} of {labels} fell back")
        elif all_smooth is False:
            g.want(f"{tag} falls back where the smooth face cannot fit",
                   bitmap > 0, "nothing fell back, so the fallback is untested here")
            g.want(f"{tag} still sets most labels in the smooth face",
                   smooth > bitmap, f"{smooth} smooth, {bitmap} bitmap")

        for r in range(labels):
            at = b + REC + r * RECSZ
            face = u64(cpu, at + R_FACE)
            bx, by = u64(cpu, at + R_BOXX), u64(cpu, at + R_BOXY)
            bw, bh = u64(cpu, at + R_BOXW), u64(cpu, at + R_BOXH)
            dx, dw = u64(cpu, at + R_DRAWX), u64(cpu, at + R_DRAWW)
            dy, dh = u64(cpu, at + R_TOP), u64(cpu, at + R_DRAWH)
            label = cstr(cpu, at + R_TEXT, 16)
            what = f"{tag} label {r} {label!r}"

            g.want(f"{what} has a face", face in (SMOOTH, BITMAP), str(face))
            g.want(f"{what} is inside its box horizontally",
                   bx <= dx and dx + dw <= bx + bw, f"{dx}+{dw} in {bx}+{bw}")
            g.want(f"{what} is inside its box vertically",
                   by <= dy and dy + dh <= by + bh, f"{dy}+{dh} in {by}+{bh}")
            left, right = dx - bx, (bx + bw) - (dx + dw)
            g.want(f"{what} is centred across the box", abs(left - right) <= 1,
                   f"{left} left, {right} right")
            top, bottom = dy - by, (by + bh) - (dy + dh)
            g.want(f"{what} is centred down the box", abs(top - bottom) <= 1,
                   f"{top} above, {bottom} below")

            if face == SMOOTH:
                g.want(f"{what} is set at the baked face's width",
                       dw == smooth_width(label, advances),
                       f"{dw} drawn, {smooth_width(label, advances)} baked")
                g.want(f"{what} was set in the smooth face because it fits",
                       bh >= lineh and dw <= bw, f"box {bw}x{bh}, text {dw}x{lineh}")
            else:
                wanted = smooth_width(label, advances)
                g.want(f"{what} fell back because the smooth face does not fit",
                       bh < lineh or wanted > bw,
                       f"box {bw}x{bh} would have held {wanted}x{lineh}")

    # ---- the band down: this pass owns nothing outside the band --------
    b = SCEN + 6 * STRIDE
    g.want("with the band down the GPU tier's pass lays out", u64(cpu, b + F_OK) == 1)
    g.want("with the band down the GPU tier's pass draws nothing",
           u64(cpu, b + F_LABELS) == 0 and u64(cpu, b + F_RECTS) == 0,
           f"{u64(cpu, b + F_LABELS)} labels, {u64(cpu, b + F_RECTS)} rectangles")
    g.want("with the band down the GPU tier's pass presents nothing",
           u64(cpu, b + F_PRESN) == 0, str(u64(cpu, b + F_PRESN)))

    # ---- the carry ------------------------------------------------------
    b0 = SCEN + 0 * STRIDE
    bandY, bandH = u64(cpu, b0 + F_BANDY), u64(cpu, b0 + F_BANDH)
    b7 = SCEN + 7 * STRIDE
    portraitY, portraitH = u64(cpu, b7 + F_BANDY), u64(cpu, b7 + F_BANDH)
    pitch = PANEL_W * 4
    for slot, rot, dma, note in CARRIES:
        k = KEEP + slot * KEEPSZ
        tag = f"carry {slot} at {rot} ({note})"
        y0, y1 = (bandY, bandY + bandH - 1) if rot in (90, 270) else (portraitY, portraitH + portraitY - 1)
        loX, loY, hiX, hiY = physical_band(rot, y0, y1)
        wide, tall = (hiX - loX + 1) * 4, hiY - loY + 1
        g.want(f"{tag} carried the band", u64(cpu, k + K_RC) == 1, str(u64(cpu, k + K_RC)))
        g.want(f"{tag} reads the presented front",
               u64(cpu, k + K_SRC) == FB_SCAN + loY * pitch + loX * 4,
               f"${u64(cpu, k + K_SRC):08X} for ${FB_SCAN + loY * pitch + loX * 4:08X}")
        g.want(f"{tag} writes the GPU's target",
               u64(cpu, k + K_DST) == FB_DRAW + loY * pitch + loX * 4,
               f"${u64(cpu, k + K_DST):08X} for ${FB_DRAW + loY * pitch + loX * 4:08X}")
        if dma:
            g.want(f"{tag} hands it to the DMA engine", u64(cpu, k + K_DMA) == 1)
            g.want(f"{tag} moves the band's own physical rectangle",
                   u64(cpu, k + K_WIDE) == wide and u64(cpu, k + K_TALL) == tall,
                   f"{u64(cpu, k + K_WIDE)}x{u64(cpu, k + K_TALL)} for {wide}x{tall}")
            g.want(f"{tag} keeps the surface's pitch",
                   u64(cpu, k + K_PITCH) == pitch, str(u64(cpu, k + K_PITCH)))
        else:
            g.want(f"{tag} moves it row by row when there is no DMA engine",
                   u64(cpu, k + K_DMA) == 0 and u64(cpu, k + K_ROWS) == tall,
                   f"{u64(cpu, k + K_ROWS)} rows for {tall}")
            g.want(f"{tag} moves a row of the band's own width",
                   u64(cpu, k + K_WIDE) == wide,
                   f"{u64(cpu, k + K_WIDE)} for {wide}")
            g.want(f"{tag} drains the mover before the present reads it",
                   0 < u64(cpu, k + K_LAST) < u64(cpu, k + K_DRAIN),
                   f"last byte {u64(cpu, k + K_LAST)}, drain {u64(cpu, k + K_DRAIN)}")

    # AND THE CASE IT MUST REFUSE. A single-buffered renderer draws straight
    # into the surface that is being scanned; carrying there would copy the
    # band over itself while the panel reads it.
    k = KEEP + 6 * KEEPSZ
    g.want("the carry refuses a target that is already the presented front",
           u64(cpu, k + K_RC) == 0, str(u64(cpu, k + K_RC)))
    g.want("and moves nothing when it refuses",
           u64(cpu, k + K_DMA) == 0 and u64(cpu, k + K_ROWS) == 0
           and u64(cpu, k + K_LAST) == 0,
           f"dma {u64(cpu, k + K_DMA)}, rows {u64(cpu, k + K_ROWS)}, "
           f"last {u64(cpu, k + K_LAST)}")
    return g


def run_once(a64, compiler, compose: str, keep: str, work_root: str):
    with tempfile.TemporaryDirectory(prefix="anvil-kbdgpu-", dir=work_root) as temporary:
        work = pathlib.Path(temporary)
        source = stage(work, compose, keep)
        image = build(compiler, work, source)
        return execute(a64, image)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pmfc")
    parser.add_argument("--interp")
    parser.add_argument("--no-mutate", action="store_true")
    parser.add_argument("--record", action="store_true",
                        help="print every label, its box and the face it was set in")
    args = parser.parse_args()

    compiler = locate("PMFC", args.pmfc, [ROOT / "pmfc.exe", ROOT / "pmfc"])
    a64 = load_interpreter(locate("PMF_A64_INTERP", args.interp,
                                  [ROOT / "tools" / "a64" / "a64_interp.py"]))
    advances = parse_key_advances()
    compose = lift_compose()
    keep = lift_keep()

    with tempfile.TemporaryDirectory(prefix="anvil-kbdgpu-root-") as root:
        cpu, rc, steps = run_once(a64, compiler, compose, keep, root)
        g = grade(cpu, rc, advances)

        if args.record:
            for slot, page, lw, lh, ppi, ds, all_smooth, note in SCENARIOS:
                b = SCEN + slot * STRIDE
                if u64(cpu, b + F_OK) != 1:
                    print(f"  slot {slot}: refused")
                    continue
                print(f"  slot {slot} {lw}x{lh} ppi {ppi} scale {ds}: "
                      f"{u64(cpu, b + F_SMOOTH)} smooth, {u64(cpu, b + F_BITMAP)} bitmap, "
                      f"band 0,{u64(cpu, b + F_BANDY)} "
                      f"{u64(cpu, b + F_LW)}x{u64(cpu, b + F_BANDH)}")
                for r in range(u64(cpu, b + F_LABELS)):
                    at = b + REC + r * RECSZ
                    label = cstr(cpu, at + R_TEXT, 16)
                    face = "smooth" if u64(cpu, at + R_FACE) == SMOOTH else "bitmap"
                    print(f"      {label!r:14} box {u64(cpu, at + R_BOXW)}x"
                          f"{u64(cpu, at + R_BOXH)}  drew {u64(cpu, at + R_DRAWW)}x"
                          f"{u64(cpu, at + R_DRAWH)}  {face}")
            for slot, rot, dma, note in CARRIES:
                k = KEEP + slot * KEEPSZ
                print(f"  carry {slot} rot {rot}: rc {u64(cpu, k + K_RC)} "
                      f"${u64(cpu, k + K_SRC):08X} -> ${u64(cpu, k + K_DST):08X} "
                      f"{u64(cpu, k + K_WIDE)} bytes x {u64(cpu, k + K_TALL)} "
                      f"(dma {u64(cpu, k + K_DMA)}, rows {u64(cpu, k + K_ROWS)})")

        if g.failures:
            print(f"keyboard_gpu_face_emitted_check: FAIL ({g.checks} checks, "
                  f"{steps:,} instructions)")
            for failure in g.failures[:40]:
                print("  " + failure)
            if len(g.failures) > 40:
                print(f"  ... and {len(g.failures) - 40} more")
            return 1

        print(f"keyboard_gpu_face_emitted_check: PASS - {g.checks} checks over "
              f"{steps:,} executed A64 instructions")
        print("  the lifted composer ran on the V3D tier - gCursorGpuOwned set - over the "
              "real key model and the real view at six surfaces")
        print("  every label on the bench panel is set in the 30 px face; the narrow "
              "surface falls back and keeps its label")
        print("  the whole band is painted before the seam moves it, the writes are "
              "drained before the copy, and the pointer's save-under is untouched")
        print("  and the lifted carry moves the band's own physical rectangle at 0, 90, "
              "180 and 270")

        if args.no_mutate:
            return 0

        print()
        missed = 0
        for name, fixed, broken in COMPOSE_MUTANTS + KEEP_MUTANTS:
            compose_is = (name, fixed, broken) in COMPOSE_MUTANTS
            text = compose if compose_is else keep
            if text.count(fixed) != 1:
                print(f"  STALE  {name} - its anchor is not in the lifted text exactly once")
                missed += 1
                continue
            mutated = text.replace(fixed, broken, 1)
            try:
                if compose_is:
                    mcpu, mrc, msteps = run_once(a64, compiler, mutated, keep, root)
                else:
                    mcpu, mrc, msteps = run_once(a64, compiler, compose, mutated, root)
            except SystemExit as exc:
                print(f"  STALE  {name} - the mutation did not build, so the gate's checks")
                print(f"         were never exercised: {str(exc).splitlines()[0][:100]}")
                missed += 1
                continue
            mg = grade(mcpu, mrc, advances)
            if mg.failures:
                print(f"  rejected: {name} ({len(mg.failures)} checks failed, "
                      f"first: {mg.failures[0][:90]})")
            else:
                print(f"  GREEN    {name}  <-- THE GATE DID NOT NOTICE")
                missed += 1

        total = len(COMPOSE_MUTANTS) + len(KEEP_MUTANTS)
        if missed:
            print(f"\nkeyboard_gpu_face_emitted_check: {missed} of {total} mutations "
                  "were not caught")
            return 1
        print(f"\nkeyboard_gpu_face_emitted_check: all {total} mutations rejected")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

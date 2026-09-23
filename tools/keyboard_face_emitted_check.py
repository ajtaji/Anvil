#!/usr/bin/env python3
"""Grade the touch keyboard's choice of face on the A64 oracle.

This is an emitted-code gate.  It LIFTS TouchKeyboardComposeCpu verbatim
from between the fences in RaspberryPi4/Board/banner_clock.pi4 - nothing
is copied and nothing is paraphrased; if the fences move the gate goes
red - redirects only the four rectangle accessors so the fixture can see
which box each label belonged to, compiles it against the REAL key model
and the REAL view, and runs it in the A64 interpreter with a hard stop
armed on any MMIO access.

What it grades is the thing the source cannot say: that on the panel this
monitor runs on every key label is set in the 30 px anti-aliased face,
that a box the face does not fit still gets its label from the bitmap
cell font rather than losing it, and that either way the label is centred
inside the key.

  PMF_COMPILER=<PureMetalForge.exe> PMF_A64_INTERP=<a64_interp.py> \
      py -3 tools/keyboard_face_emitted_check.py
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
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
ADAPTER = ROOT / "RaspberryPi4" / "Board" / "banner_clock.pi4"
GATE = ROOT / "RaspberryPi4" / "Tests" / "keyboard_face_emitted_gate.pi4"
FONTS = ROOT / "RaspberryPi4" / "Monitor" / "anvil_fonts.pi4"
LIFT_NAME = "_keyboard_face_lift.pbi"

COMPOSE_BEGIN = "; ANVIL-TOUCH-KEYBOARD-COMPOSE-BEGIN"
COMPOSE_END = "; ANVIL-TOUCH-KEYBOARD-COMPOSE-END"

LOAD = 0x00400000
STACK = 0x03000000
LOADER_LR = 0xDEAD0000
STEP_LIMIT = 80_000_000
MMIO = 0xFC000000

MAGIC_AT = 0x06000000
MAGIC = 0x4B424446
META = 0x06000100
SCEN = 0x06010000
STRIDE = 0x00010000

F_OK, F_ITEMS, F_LABELS, F_SMOOTH, F_BITMAP = 0, 8, 16, 24, 32
F_SCALEEND, F_FIDMIN, F_FIDMAX, F_TEXTN = 40, 48, 56, 64
REC, RECSZ = 0x400, 96
R_FACE, R_BOXX, R_BOXY, R_BOXW, R_BOXH = 0, 8, 16, 24, 32
R_DRAWX, R_DRAWW, R_TOP, R_DRAWH, R_TEXT = 40, 48, 56, 64, 72

SMOOTH, BITMAP = 1, 2

# slot, page, logicalW, logicalH, ppi, displayScale, every label smooth?, note
SCENARIOS = (
    (0, 0, 1280, 800, 149, 1, True,
     "the bench panel, landscape - the geometry a finger actually touches"),
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

# The four accessors the fixture wraps, so it can attribute a recorded
# label to the box it was drawn in.  Nothing else in the lifted text is
# touched, and the substitution count is checked.
REDIRECT = {
    "TouchKeyboardDrawX(i)": "KfDrawX(i)",
    "TouchKeyboardDrawY(i)": "KfDrawY(i)",
    "TouchKeyboardDrawW(i)": "KfDrawW(i)",
    "TouchKeyboardDrawH(i)": "KfDrawH(i)",
    "TouchKeyboardDrawText(i)": "KfDrawText(i)",
}

# Plausible mistakes in the lifted composer.  Each MUST turn the gate red.
MUTANTS = (
    ("the smooth face is never tried",
     "      If h >= #FONT_keys_LINEH\n", "      If h >= 100000\n"),
    ("a label wider than its key is set in the smooth face anyway",
     "        If sw <= w\n", "        If 1 <> 0\n"),
    ("the smooth label is left-aligned instead of centred",
     "          DrawSmoothText(x + (w - sw) / 2, ", "          DrawSmoothText(x, "),
    ("the smooth label is placed at the box top instead of on its baseline",
     "y + (h - #FONT_keys_LINEH) / 2 + #FONT_keys_ASC, p, 3, fg, bg)\n",
     "y, p, 3, fg, bg)\n"),
    ("the banner's 48 px face is asked for instead of the key face",
     "        sw = SmoothTextWidth(p, 3)\n", "        sw = SmoothTextWidth(p, 0)\n"),
    ("the fallback label is left-aligned instead of centred",
     "        x = x + (w - len * DisplayCharWidth()) / 2\n", "        x = x\n"),
    ("the fallback label is not centred vertically either",
     "        y = y + (h - DisplayCharHeight()) / 2\n", "        y = y\n"),
    ("a box the smooth face does not fit loses its label altogether",
     "      If drawn = 0\n", "      If drawn = 2\n"),
    ("the library magnification is not put back",
     "  DisplayScale(savedScale)\n", "  \n"),
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
    raise SystemExit(f"keyboard face gate: {env_name} was not found; set it or pass its option")


def load_interpreter(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("anvil_kbdface_a64", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"keyboard face gate: cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def lift() -> str:
    text = ADAPTER.read_text(encoding="utf-8")
    start = text.find(COMPOSE_BEGIN)
    end = text.find(COMPOSE_END)
    if start < 0 or end < 0 or end < start:
        raise SystemExit("keyboard face gate: the compose fences are not both in "
                         f"{ADAPTER.name} in order; the gate cannot lift what it grades")
    body = text[start + len(COMPOSE_BEGIN):end]
    for was, now in REDIRECT.items():
        if body.count(was) < 1:
            raise SystemExit(f"keyboard face gate: the lifted composer no longer reads "
                             f"{was}, so the gate cannot attribute a label to a box")
        body = body.replace(was, now)
    header = (
        "; LIFTED VERBATIM from RaspberryPi4/Board/banner_clock.pi4 between\n"
        "; " + COMPOSE_BEGIN[2:] + " and " + COMPOSE_END[2:] + " by\n"
        "; tools/keyboard_face_emitted_check.py. The only edit is that the\n"
        "; view's four rectangle accessors and its label accessor are read\n"
        "; through the gate's recorders. Do not edit this file; edit the\n"
        "; adapter.\n"
    )
    return header + body


def parse_key_advances() -> dict[int, int]:
    """The advance byte of every glyph in the baked 30 px face, read out of
    the generated source the board compiles.  This is the checker's own
    reading of the same table the image reads."""
    text = FONTS.read_text(encoding="utf-8")
    at = text.find("fontKeysMeta:")
    if at < 0:
        raise SystemExit("keyboard face gate: anvil_fonts.pi4 has no fontKeysMeta")
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
    advances = {}
    for i in range(count):
        advances[first + i] = data[i * 8]
    return advances


def smooth_width(label: str, advances: dict[int, int]) -> int:
    return sum(advances.get(ord(c), 0) for c in label)


def stage(work: pathlib.Path, lifted: str) -> pathlib.Path:
    for folder in ("Anvil/Core", "Anvil/Graphics", "RaspberryPi4/Board",
                   "RaspberryPi4/Monitor", "RaspberryPi4/Tests"):
        (work / folder).mkdir(parents=True, exist_ok=True)
    for rel in ("Anvil/Core/touch_keyboard.pbi",
                "Anvil/Core/boot_transcript.pbi",
                "Anvil/Core/console_style.pbi",
                "Anvil/Graphics/touch_keyboard_view.pbi",
                "RaspberryPi4/Board/console.pi4",
                "RaspberryPi4/Monitor/anvil_fonts.pi4"):
        shutil.copy2(ROOT / rel, work / rel)
    shutil.copy2(GATE, work / "RaspberryPi4" / "Tests" / GATE.name)
    (work / "RaspberryPi4" / "Tests" / LIFT_NAME).write_text(lifted, encoding="utf-8")
    src = ROOT / "RaspberryPi4" / "Intrinsics"
    if src.is_dir():
        shutil.copytree(src, work / "RaspberryPi4" / "Intrinsics", dirs_exist_ok=True)
    if (ROOT / "Boards").is_dir():
        shutil.copytree(ROOT / "Boards", work / "Boards", dirs_exist_ok=True)
    return work / "RaspberryPi4" / "Tests" / GATE.name


def build(compiler: pathlib.Path, work: pathlib.Path, source: pathlib.Path) -> pathlib.Path:
    image = work / "keyboard_face_gate.img"
    command = [str(compiler), "--compile", source.relative_to(work).as_posix(),
               "-t", "pi4", "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
               "--entry-returns", "-o", str(image), "-s"]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(work)
    run = subprocess.run(command, cwd=work, env=env, text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if run.returncode or "pmfc: OK" not in run.stdout or not image.is_file():
        raise SystemExit("keyboard face gate: compile failed\n" + run.stdout)
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
            raise SystemExit(f"keyboard face gate: unexpected MMIO {kind} at ${addr:08X} - "
                             "this file is supposed to touch no hardware at all")

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
    raise SystemExit(f"keyboard face gate: the probe did not return in {STEP_LIMIT} instructions")


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

        # NO LABEL IS EVER LOST. The view asked for this many, and a
        # renderer that draws fewer has silently blanked a key.
        g.want(f"{tag} draws every label the view asked for",
               labels == textn and labels > 0, f"{labels} drawn, {textn} asked for")
        g.want(f"{tag} counts add up", smooth + bitmap == labels)

        # THE LIBRARY MAGNIFICATION IS PUT BACK. The console is drawn with
        # it; a pass that leaves the keyboard's behind changes the console.
        g.want(f"{tag} restores the library magnification",
               u64(cpu, b + F_SCALEEND) == ds, str(u64(cpu, b + F_SCALEEND)))

        # ONE FACE IS ASKED FOR, AND IT IS THE KEY FACE.
        fidmin, fidmax = u64(cpu, b + F_FIDMIN), u64(cpu, b + F_FIDMAX)
        if smooth or fidmax >= 0:
            g.want(f"{tag} asks only for the key face",
                   fidmin == 3 and fidmax == 3, f"{fidmin}..{fidmax}")

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
            # INSIDE THE KEY, both ways.
            g.want(f"{what} is inside its box horizontally",
                   bx <= dx and dx + dw <= bx + bw, f"{dx}+{dw} in {bx}+{bw}")
            g.want(f"{what} is inside its box vertically",
                   by <= dy and dy + dh <= by + bh, f"{dy}+{dh} in {by}+{bh}")
            # CENTRED, to the pixel integer division allows.
            left, right = dx - bx, (bx + bw) - (dx + dw)
            g.want(f"{what} is centred across the box", abs(left - right) <= 1,
                   f"{left} left, {right} right")
            top, bottom = dy - by, (by + bh) - (dy + dh)
            g.want(f"{what} is centred down the box", abs(top - bottom) <= 1,
                   f"{top} above, {bottom} below")

            if face == SMOOTH:
                # THE WIDTH IS THE BAKED FACE'S OWN, read independently.
                g.want(f"{what} is set at the baked face's width",
                       dw == smooth_width(label, advances),
                       f"{dw} drawn, {smooth_width(label, advances)} baked")
                g.want(f"{what} was set in the smooth face because it fits",
                       bh >= lineh and dw <= bw, f"box {bw}x{bh}, text {dw}x{lineh}")
            else:
                # AND A FALLBACK HAPPENS ONLY WHERE THE FACE DOES NOT FIT.
                wanted = smooth_width(label, advances)
                g.want(f"{what} fell back because the smooth face does not fit",
                       bh < lineh or wanted > bw,
                       f"box {bw}x{bh} would have held {wanted}x{lineh}")
    return g


def run_once(a64, compiler, lifted: str, work_root: str):
    with tempfile.TemporaryDirectory(prefix="anvil-kbdface-", dir=work_root) as temporary:
        work = pathlib.Path(temporary)
        source = stage(work, lifted)
        image = build(compiler, work, source)
        return execute(a64, image)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler")
    parser.add_argument("--interp")
    parser.add_argument("--no-mutate", action="store_true")
    parser.add_argument("--record", action="store_true",
                        help="print every label, its box and the face it was set in")
    args = parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler

    compiler = locate("PMF_COMPILER", args.compiler, [ROOT / "PureMetalForge.exe", ROOT / "compiler"])
    a64 = load_interpreter(locate("PMF_A64_INTERP", args.interp,
                                  [ROOT / "tools" / "a64" / "a64_interp.py"]))
    advances = parse_key_advances()
    lifted = lift()

    with tempfile.TemporaryDirectory(prefix="anvil-kbdface-root-") as root:
        cpu, rc, steps = run_once(a64, compiler, lifted, root)
        g = grade(cpu, rc, advances)

        if args.record:
            for slot, page, lw, lh, ppi, ds, all_smooth, note in SCENARIOS:
                b = SCEN + slot * STRIDE
                if u64(cpu, b + F_OK) != 1:
                    print(f"  slot {slot}: refused")
                    continue
                print(f"  slot {slot} {lw}x{lh} ppi {ppi} scale {ds}: "
                      f"{u64(cpu, b + F_SMOOTH)} smooth, {u64(cpu, b + F_BITMAP)} bitmap")
                for r in range(u64(cpu, b + F_LABELS)):
                    at = b + REC + r * RECSZ
                    label = cstr(cpu, at + R_TEXT, 16)
                    face = "smooth" if u64(cpu, at + R_FACE) == SMOOTH else "bitmap"
                    print(f"      {label!r:14} box {u64(cpu, at + R_BOXW)}x"
                          f"{u64(cpu, at + R_BOXH)}  drew {u64(cpu, at + R_DRAWW)}x"
                          f"{u64(cpu, at + R_DRAWH)}  {face}")

        if g.failures:
            print(f"keyboard_face_emitted_check: FAIL ({g.checks} checks, {steps:,} instructions)")
            for failure in g.failures[:40]:
                print("  " + failure)
            if len(g.failures) > 40:
                print(f"  ... and {len(g.failures) - 40} more")
            return 1

        print(f"keyboard_face_emitted_check: PASS - {g.checks} checks over "
              f"{steps:,} executed A64 instructions")
        print("  the lifted composer ran over the real key model and the real view at "
              "six surfaces")
        print("  every label on the bench panel is set in the 30 px face; the narrow "
              "surface falls back")
        print("  and keeps its label; every label is centred inside its key either way")

        if args.no_mutate:
            return 0

        print()
        missed = 0
        for name, fixed, broken in MUTANTS:
            if lifted.count(fixed) != 1:
                print(f"  STALE  {name} - its anchor is not in the lifted composer exactly once")
                missed += 1
                continue
            mutant = lifted.replace(fixed, broken, 1)
            try:
                mcpu, mrc, msteps = run_once(a64, compiler, mutant, root)
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

        if missed:
            print(f"\nkeyboard_face_emitted_check: {missed} of {len(MUTANTS)} mutations "
                  "were not caught")
            return 1
        print(f"\nkeyboard_face_emitted_check: all {len(MUTANTS)} mutations rejected")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

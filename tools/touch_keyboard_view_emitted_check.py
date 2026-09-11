#!/usr/bin/env python3
"""Grade the compiled touch keyboard view and console viewport on the A64 oracle.

This is an emitted-code gate.  It builds RaspberryPi4/Tests/
touch_keyboard_view_emitted_gate.pi4 with the real compiler, runs the real
image in the A64 interpreter with an MMIO hard stop armed, and then checks
PROPERTIES of the record the image left in DRAM.  Nothing here re-implements
the layout: the checker does not know how a key rectangle is produced, only
what has to be true of the set of them.

  PMFC=<pmfc.exe> PMF_A64_INTERP=<a64_interp.py> \
      py -3.12 tools/touch_keyboard_view_emitted_check.py

Add --mutate to also apply a list of plausible mistakes to the product
sources, one at a time, and require the gate to go RED for each.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile


HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
GATE = ROOT / "RaspberryPi4" / "Tests" / "touch_keyboard_view_emitted_gate.pi4"
VIEW = ROOT / "Anvil" / "Graphics" / "touch_keyboard_view.pbi"
MODEL = ROOT / "Anvil" / "Core" / "touch_keyboard.pbi"
CONSOLE = ROOT / "RaspberryPi4" / "Board" / "console.pi4"

LOAD = 0x00400000
STACK = 0x03000000
LOADER_LR = 0xDEAD0000
STEP_LIMIT = 80_000_000
MMIO = 0xFC000000

MAGIC_AT = 0x06000000
MAGIC = 0x4B424456
SCEN = 0x06010000
STRIDE = 0x00010000
BANNER = 120

# Scenario block offsets, mirroring the gate's header.
F_OK, F_LW, F_LH, F_BH = 0, 8, 16, 24
F_CELLW, F_CELLH, F_PPI, F_DS = 32, 40, 48, 56
F_MIN, F_PREF, F_GUT = 64, 72, 80
F_BANDY, F_BANDH, F_CONROWS, F_ROWS, F_KEYS, F_KNOWN = 88, 96, 104, 112, 120, 128
F_HIDEX, F_HIDEY, F_HIDEW, F_HIDEH = 136, 144, 152, 160
F_BTNX, F_BTNY, F_BTNW, F_BTNH = 168, 176, 184, 192
F_REFUSAL, F_SPLIT, F_MAXKEYS, F_SCANROWS, F_VSCANX, F_SIZEADJ = 200, 208, 216, 224, 232, 240
F_FULLSCAN, F_SAMPLES = 248, 256
F_KEYTAB = 0x400
F_HSCAN = 0x1000
F_HSCAN_STRIDE = 0x1000
F_VSCAN = 0x9000
F_SAMPLETAB = 0xA000

CON_ROWS = 0x06000100
CON_VIEW0 = 0x06000108
CON_VIEW1 = 0x06000110
CON_TOP1 = 0x06000118
CON_CUR1 = 0x06000120
CON_VIEW2 = 0x06000128
CON_TOP2 = 0x06000130
CON_SCROLLN_RAW = 0x06000138
CON_SCROLLN_VIEW = 0x06000140
SNAP_BEFORE = 0x06000200
SNAP_SHOWN = 0x06000280
SNAP_AFTER = 0x06000300

DMG_ALLN = 0x06000800
DMG_CHGN = 0x06000808
DMG_X, DMG_Y, DMG_W, DMG_H = 0x06000810, 0x06000818, 0x06000820, 0x06000828
DMG_KEY, DMG_OUTSIDE, DMG_ITEMS = 0x06000830, 0x06000838, 0x06000840

PAGE_ABC, PAGE_SYMBOL = 0, 1

# slot, page, logicalW, logicalH, ppi, displayScale, must lay out
SCENARIOS = (
    (0, PAGE_ABC, 1280, 800, 149, 1, True, "bench panel, landscape, the shipped default"),
    (1, PAGE_ABC, 800, 1280, 149, 1, True, "the panel's own portrait scan"),
    (2, PAGE_ABC, 1280, 800, 149, 2, True, "landscape at the large-text setting"),
    (3, PAGE_ABC, 640, 480, 149, 1, True, "the smallest screen this arrangement fits"),
    (4, PAGE_ABC, 480, 800, 149, 1, False, "too narrow for this arrangement"),
    (5, PAGE_ABC, 400, 300, 149, 1, False, "too short for a safe key"),
    (6, PAGE_ABC, 1280, 800, 0, 1, True, "density unknown: the display-scale fallback"),
    (7, PAGE_SYMBOL, 1280, 800, 149, 1, True, "the symbol page, landscape"),
    (8, PAGE_ABC, 800, 1280, 149, 2, True, "portrait at the large-text setting"),
)

MIN_THOU = 320
PREF_THOU = 380
MIN_CONSOLE_ROWS = 2

# Plausible mistakes.  Each MUST turn the gate red; a mutation that leaves it
# green is a hole in the gate and is reported as one.
MUTANTS = (
    (
        "keys overlap by one pixel",
        "view",
        "      gTkbKeyW[i] = right - left\n",
        "      gTkbKeyW[i] = right - left + gTkbGutter + 1\n",
    ),
    (
        "band no longer starts on a whole console row",
        "view",
        "  kbY = bh + gTkbConsoleRows * ch\n",
        "  kbY = lh - want\n",
    ),
    (
        "hit test includes the pixel past a key's right edge",
        "view",
        "    If x >= gTkbKeyX[i] And x < (gTkbKeyX[i] + gTkbKeyW[i])\n",
        "    If x >= gTkbKeyX[i] And x <= (gTkbKeyX[i] + gTkbKeyW[i])\n",
    ),
    (
        "one changed key damages the whole band",
        "view",
        "        TkbDamage(gTkbKeyX[i], gTkbKeyY[i], gTkbKeyW[i], gTkbKeyH[i])\n",
        "        TkbDamage(0, gTkbBandY, gTkbLW, gTkbBandH)\n",
    ),
    (
        "the chevron stops being the model's hide key",
        "view",
        "    If TouchKeyboardKeyKind(i) = #TK_KIND_HIDE\n",
        "    If TouchKeyboardKeyKind(i) = #TK_KIND_SHIFT\n",
    ),
    (
        "the minimum key width is not enforced",
        "view",
        "      If gTkbKeyW[i] < gTkbMinPx\n",
        "      If gTkbKeyW[i] < 0\n",
    ),
    (
        "the reserved rows are counted from the top of the screen, not from below the banner",
        "view",
        "  gTkbConsoleRows = (lh - bh - want) / ch\n",
        "  gTkbConsoleRows = (lh - want) / ch\n",
    ),
    (
        "reserving rows re-initialises the grid, as it used to",
        "console",
        "  gConViewRows = want\n  gConFullClear = 1\n  gConOverlayWhole = 1\n  ConGridMarkAll()\n",
        "  gConViewRows = want\n  ConGridInit(gConCols, gConRows)\n",
    ),
    (
        "the viewport accessor ignores the window origin",
        "console",
        "Procedure.i ConGridCell(r.i, c.i)\n  ProcedureReturn ConContentCell(ConViewTop() + r, c)\n",
        "Procedure.i ConGridCell(r.i, c.i)\n  ProcedureReturn ConContentCell(r, c)\n",
    ),
)


def locate(env_name: str, explicit: str | None, fallbacks) -> pathlib.Path:
    choices = []
    if explicit:
        choices.append(pathlib.Path(explicit))
    if os.environ.get(env_name):
        choices.append(pathlib.Path(os.environ[env_name]))
    choices.extend(fallbacks)
    for path in choices:
        if path.is_file():
            return path.resolve()
    raise SystemExit(
        f"touch keyboard view gate: {env_name} was not found; set it or pass its option"
    )


def load_interpreter(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("anvil_tkb_a64_interp", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"touch keyboard view gate: cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# The gate needs a very small root: the two product sources it executes, the
# gate itself, the intrinsics table and the pin aliases.  Staging it means a
# mutation never touches the repository.
def stage(work: pathlib.Path, view_text: str, console_text: str) -> pathlib.Path:
    (work / "Anvil" / "Graphics").mkdir(parents=True, exist_ok=True)
    (work / "Anvil" / "Core").mkdir(parents=True, exist_ok=True)
    (work / "RaspberryPi4" / "Board").mkdir(parents=True, exist_ok=True)
    (work / "RaspberryPi4" / "Tests").mkdir(parents=True, exist_ok=True)
    shutil.copy2(MODEL, work / "Anvil" / "Core" / MODEL.name)
    # console.pi4 includes the bounded boot transcript beside the drain that
    # feeds it. Pure storage; nothing here exercises it, but the staged tree
    # has to resolve the include.
    shutil.copy2(ROOT / "Anvil" / "Core" / "boot_transcript.pbi",
                 work / "Anvil" / "Core" / "boot_transcript.pbi")
    (work / "Anvil" / "Graphics" / "touch_keyboard_view.pbi").write_text(view_text, encoding="utf-8")
    (work / "RaspberryPi4" / "Board" / "console.pi4").write_text(console_text, encoding="utf-8")
    shutil.copy2(GATE, work / "RaspberryPi4" / "Tests" / GATE.name)
    for name in ("Intrinsics",):
        src = ROOT / "RaspberryPi4" / name
        if src.is_dir():
            shutil.copytree(src, work / "RaspberryPi4" / name, dirs_exist_ok=True)
    if (ROOT / "Boards").is_dir():
        shutil.copytree(ROOT / "Boards", work / "Boards", dirs_exist_ok=True)
    # PMF_ROOT is the ONLY place the compiler looks for its keyword table.
    for loose in ("keywords.def",):
        if (ROOT / loose).is_file():
            shutil.copy2(ROOT / loose, work / loose)
    return work / "RaspberryPi4" / "Tests" / GATE.name


def build(compiler: pathlib.Path, work: pathlib.Path, source: pathlib.Path) -> pathlib.Path:
    image = work / "touch_keyboard_view_gate.img"
    command = [
        str(compiler),
        source.relative_to(work).as_posix(),
        "-t", "pi4",
        "--load-addr", hex(LOAD),
        "--stack-addr", hex(STACK),
        "--entry-returns",
        "-o", str(image),
        "-s",
    ]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(work)
    run = subprocess.run(
        command, cwd=work, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise SystemExit("touch keyboard view gate: compile failed\n" + run.stdout)
    return image


def execute(a64, image: pathlib.Path):
    cpu = a64.A64()
    for i, byte in enumerate(image.read_bytes()):
        cpu.memory[LOAD + i] = byte
    a64.attach_symbols(cpu, image, LOAD)
    cpu.pc = LOAD
    cpu.sp = STACK
    cpu.x[30] = LOADER_LR

    def guard(addr: int, write: bool) -> None:
        if addr >= MMIO:
            kind = "write" if write else "read"
            raise SystemExit(
                f"touch keyboard view gate: unexpected MMIO {kind} at ${addr:08X} - "
                "this file is supposed to touch no hardware at all"
            )

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
    raise SystemExit(
        f"touch keyboard view gate: the probe did not return in {STEP_LIMIT} instructions"
    )


def u64(cpu, addr: int) -> int:
    v = sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(8))
    if v >= 1 << 63:
        v -= 1 << 64
    return v


def u8(cpu, addr: int) -> int:
    return cpu.memory.get(addr, 0)


def cstr(cpu, addr: int, limit: int = 512) -> str:
    out = []
    for i in range(limit):
        b = cpu.memory.get(addr + i, 0)
        if b == 0:
            break
        out.append(chr(b))
    return "".join(out)


class Grader:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.checks = 0

    def need(self, name: str, got, want) -> None:
        self.checks += 1
        if got != want:
            self.failures.append(f"{name}: got {got!r}, wanted {want!r}")

    def want_true(self, name: str, condition: bool, detail: str = "") -> None:
        self.checks += 1
        if not condition:
            self.failures.append(f"{name}{(': ' + detail) if detail else ''}")


def grade_scenario(cpu, g: Grader, slot, page, lw, lh, ppi, ds, expect_ok, note) -> None:
    b = SCEN + slot * STRIDE
    tag = f"scenario {slot} ({note})"
    ok = u64(cpu, b + F_OK)
    g.need(f"{tag} lays out", bool(ok), expect_ok)
    g.need(f"{tag} surface width", u64(cpu, b + F_LW), lw)
    g.need(f"{tag} surface height", u64(cpu, b + F_LH), lh)

    refusal = u64(cpu, b + F_REFUSAL)
    if not expect_ok:
        # A REFUSAL IS A WHOLE SENTENCE. This is the rule the project runs
        # on, so the gate reads the actual bytes out of the shipped image
        # rather than trusting that one was set.
        g.want_true(f"{tag} names a refusal", refusal != 0)
        if refusal:
            text = cstr(cpu, refusal)
            g.want_true(f"{tag} refusal is a sentence", text.endswith("."), repr(text[:60]))
            g.want_true(f"{tag} refusal is not a bare code", len(text.split()) >= 12, repr(text[:60]))
            g.want_true(
                f"{tag} refusal says what to do",
                any(w in text for w in ("Use ", "Ask ", "use the physical", "select", "bring", "check")),
                repr(text[:120]),
            )
        if slot == 4:
            # A NARROW SCREEN TELLS THE KEY MODEL SO. The design's answer is
            # a split utility row and the symbol page, and the model cannot
            # offer one unless the view says which way it was narrow.
            g.need(f"{tag} asks the key model for a split utility row", u64(cpu, b + F_SPLIT), 1)
            g.want_true(f"{tag} says how many keys a row of this screen holds",
                        u64(cpu, b + F_MAXKEYS) >= 1, str(u64(cpu, b + F_MAXKEYS)))
        return
    if not ok:
        return

    cellH = u64(cpu, b + F_CELLH)
    minPx = u64(cpu, b + F_MIN)
    prefPx = u64(cpu, b + F_PREF)
    gut = u64(cpu, b + F_GUT)
    bandY = u64(cpu, b + F_BANDY)
    bandH = u64(cpu, b + F_BANDH)
    conRows = u64(cpu, b + F_CONROWS)
    rows = u64(cpu, b + F_ROWS)
    keys = u64(cpu, b + F_KEYS)
    known = u64(cpu, b + F_KNOWN)

    g.need(f"{tag} density known", bool(known), ppi > 0)
    if ppi > 0:
        # 0.32 inch, in whole pixels, is the floor the design states.
        g.want_true(
            f"{tag} minimum target is at least 0.32 inch",
            minPx * 1000 >= MIN_THOU * ppi - 1000,
            f"{minPx} px at {ppi} ppi = {minPx * 1000 / ppi:.0f} thou",
        )
        g.want_true(
            f"{tag} preferred target is at least the floor",
            prefPx >= minPx,
            f"{prefPx} < {minPx}",
        )
    else:
        # NOT A GUESSED INCH. With no density the policy is the explicit
        # display scale, and it has to be exactly that.
        g.need(f"{tag} fallback floor is the display scale's", minPx, max(48 * ds, (cellH * 3) // 2))

    # THE BAND SITS ON A WHOLE CONSOLE ROW and is flush to the bottom. If it
    # did not, the framebuffer renderer's per-row repaint would reach into it.
    g.need(f"{tag} band top is a whole number of console rows", bandY, BANNER + conRows * cellH)
    g.need(f"{tag} band reaches the bottom of the screen", bandY + bandH, lh)
    g.want_true(f"{tag} leaves a usable prompt row", conRows >= MIN_CONSOLE_ROWS, str(conRows))
    g.want_true(f"{tag} has key rows", rows >= 1 and keys >= rows, f"{rows} rows, {keys} keys")

    rects = []
    for i in range(keys):
        at = b + F_KEYTAB + i * 48
        rects.append((
            u64(cpu, at), u64(cpu, at + 8), u64(cpu, at + 16),
            u64(cpu, at + 24), u64(cpu, at + 32), u64(cpu, at + 40),
        ))

    # Inside the band, never cropped, never below the minimum target.
    bad_inside = []
    bad_size = []
    bad_scale = []
    for i, (x, y, w, h, row, scale) in enumerate(rects):
        if x < 0 or y < bandY or x + w > lw or y + h > bandY + bandH:
            bad_inside.append((i, x, y, w, h))
        if w < minPx or h < minPx:
            bad_size.append((i, w, h))
        if scale < 1 or 16 * scale > h - 4:
            bad_scale.append((i, scale, h))
    g.need(f"{tag} every key rectangle is inside the keyboard", bad_inside, [])
    g.need(f"{tag} every key meets the minimum target size", bad_size, [])
    g.need(f"{tag} every key label has a whole magnification that fits", bad_scale, [])

    # No two key rectangles overlap - exhaustively, every pair.
    overlaps = []
    for i in range(keys):
        xi, yi, wi, hi = rects[i][:4]
        for j in range(i + 1, keys):
            xj, yj, wj, hj = rects[j][:4]
            if xi < xj + wj and xj < xi + wi and yi < yj + hj and yj < yi + hi:
                overlaps.append((i, j))
    g.need(f"{tag} no two key rectangles overlap", overlaps, [])

    # THE DOWN-CHEVRON IS THE MODEL'S HIDE KEY, laid out like every other
    # key and republished under its own name. So the property is no longer
    # "disjoint from every key" - it is "exactly one key's rectangle", which
    # is the stronger statement: there is one dismiss target on the glass
    # and the picture and the hit test are the same rectangle by identity.
    hx, hy, hw, hh = (u64(cpu, b + f) for f in (F_HIDEX, F_HIDEY, F_HIDEW, F_HIDEH))
    g.want_true(
        f"{tag} the hide chevron is inside the band",
        hx >= 0 and hy >= bandY and hx + hw <= lw and hy + hh <= bandY + bandH,
        f"({hx},{hy},{hw},{hh}) band {bandY}+{bandH}",
    )
    g.want_true(f"{tag} the hide chevron is a real target", hw >= minPx and hh >= minPx, f"{hw}x{hh}")
    same = [i for i, (x, y, w, h, _r, _s) in enumerate(rects)
            if (x, y, w, h) == (hx, hy, hw, hh)]
    g.need(f"{tag} the hide chevron is exactly one key's rectangle", len(same), 1)
    g.need(f"{tag} the hide chevron is on the utility row", rects[same[0]][4] if same else -1, 0)

    # The keyboard button beside the prompt is OUTSIDE the band.
    bx, by, bw, bh = (u64(cpu, b + f) for f in (F_BTNX, F_BTNY, F_BTNW, F_BTNH))
    g.want_true(
        f"{tag} the keyboard button is above the band and on the screen",
        by + bh <= bandY and bx >= 0 and bx + bw <= lw,
        f"({bx},{by},{bw},{bh}) band top {bandY}",
    )

    # Rows: every key of a row shares its top and height, and the rows go
    # down the band in order with a gutter between them. NO CROPPED ROWS.
    by_row: dict[int, list[int]] = {}
    for i, (_x, _y, _w, _h, row, _s) in enumerate(rects):
        by_row.setdefault(row, []).append(i)
    g.need(f"{tag} rows are numbered without gaps", sorted(by_row), list(range(rows)))
    ragged = []
    for row, members in by_row.items():
        ys = {rects[i][1] for i in members}
        hs = {rects[i][3] for i in members}
        if len(ys) != 1 or len(hs) != 1:
            ragged.append((row, sorted(ys), sorted(hs)))
    g.need(f"{tag} every key in a row shares that row's top and height", ragged, [])
    stacked = []
    for row in range(rows - 1):
        a = rects[by_row[row][0]]
        c = rects[by_row[row + 1][0]]
        if c[1] < a[1] + a[3] + 1:
            stacked.append((row, a[1] + a[3], c[1]))
    g.need(f"{tag} rows do not run into each other", stacked, [])

    # ---- THE SCAN LINES -------------------------------------------------
    # Whole lines of the REAL hit test, one pixel a step, graded against the
    # rectangle table. This is where "every point inside a rect hits that
    # key" and "points in gutters hit -1" are actually proved.
    def expected_hit(px: int, py: int) -> int:
        for i, (x, y, w, h, _r, _s) in enumerate(rects):
            if x <= px < x + w and y <= py < y + h:
                return i
        return -1

    # Every key's own boundary: the four corners and the centre hit it, the
    # pixel one step outside each edge does not. Nine points a key, every
    # scenario - this is where an off-by-one lives.
    samples = u64(cpu, b + F_SAMPLES)
    g.need(f"{tag} nine boundary points were taken for every key", samples, keys * 9)
    bad_samples = []
    for s in range(samples):
        at = b + F_SAMPLETAB + s * 24
        px, py, got = u64(cpu, at), u64(cpu, at + 8), u64(cpu, at + 16)
        want = expected_hit(px, py)
        if got != want:
            bad_samples.append((s // 9, s % 9, px, py, got, want))
    g.need(f"{tag} every key boundary point hits the key it is in ({samples} points)",
           bad_samples[:4], [])

    scan_rows = u64(cpu, b + F_SCANROWS)
    if u64(cpu, b + F_FULLSCAN) == 0:
        g.need(f"{tag} no full scan was recorded", scan_rows, 0)
        return
    g.need(f"{tag} a scan line was taken through every row", scan_rows, rows)
    hmismatch = 0
    first_bad = None
    scanned = 0
    for row in range(scan_rows):
        anchor = rects[by_row[row][0]]
        y = anchor[1] + anchor[3] // 2
        at = b + F_HSCAN + row * F_HSCAN_STRIDE
        for x in range(lw):
            got = u8(cpu, at + x) - 1
            want = expected_hit(x, y)
            scanned += 1
            if got != want:
                hmismatch += 1
                if first_bad is None:
                    first_bad = (row, x, y, got, want)
    g.need(
        f"{tag} horizontal scan lines agree with the rectangles at every pixel "
        f"({scanned} points)",
        (hmismatch, first_bad), (0, None),
    )

    vx = u64(cpu, b + F_VSCANX)
    vmismatch = 0
    first_vbad = None
    above = 0
    for y in range(BANNER, lh):
        got = u8(cpu, b + F_VSCAN + (y - BANNER)) - 1
        want = expected_hit(vx, y)
        if y < bandY:
            above += 1
            if got != -1:
                vmismatch += 1
                if first_vbad is None:
                    first_vbad = ("console area", vx, y, got, -1)
                continue
        if got != want:
            vmismatch += 1
            if first_vbad is None:
                first_vbad = ("band", vx, y, got, want)
    g.need(
        f"{tag} the vertical scan agrees at every pixel and nothing above the "
        f"band is a key ({lh - BANNER} points, {above} of them console)",
        (vmismatch, first_vbad), (0, None),
    )


def grade(cpu, rc: int) -> Grader:
    g = Grader()
    g.need("probe magic", u64(cpu, MAGIC_AT), MAGIC)
    g.need("compiled Main returned", rc, 0)
    for slot, page, lw, lh, ppi, ds, ok, note in SCENARIOS:
        grade_scenario(cpu, g, slot, page, lw, lh, ppi, ds, ok, note)

    # ---- damage ---------------------------------------------------------
    b7 = SCEN + 7 * STRIDE
    key = u64(cpu, DMG_KEY)
    at = b7 + F_KEYTAB + key * 48
    # ONE RECTANGLE, NOT ONE PER KEY - and not two: the keyboard button
    # beside the prompt is not drawn while the band is up, because the
    # chevron is the affordance then and a button that does nothing when
    # it is tapped is a button the design forbids.
    g.need("a whole pass damages the band and nothing per key",
           u64(cpu, DMG_ALLN), 1)
    g.need("one changed key damages one rectangle", u64(cpu, DMG_CHGN), 1)
    g.need("that rectangle is exactly the changed key's",
           (u64(cpu, DMG_X), u64(cpu, DMG_Y), u64(cpu, DMG_W), u64(cpu, DMG_H)),
           (u64(cpu, at), u64(cpu, at + 8), u64(cpu, at + 16), u64(cpu, at + 24)))
    g.need("no draw item of that pass falls outside it", u64(cpu, DMG_OUTSIDE), 0)
    g.want_true("that pass drew something", u64(cpu, DMG_ITEMS) >= 3, str(u64(cpu, DMG_ITEMS)))

    # ---- the viewport against the content -------------------------------
    g.need("the console stores 20 rows", u64(cpu, CON_ROWS), 20)
    g.need("nothing reserved shows every row", u64(cpu, CON_VIEW0), 20)
    g.need("reserving shows twelve", u64(cpu, CON_VIEW1), 12)
    g.need("the window is pinned to the cursor", u64(cpu, CON_TOP1), 8)
    g.need("the prompt row is the last visible row", u64(cpu, CON_CUR1), 11)
    g.need("releasing shows every row again", u64(cpu, CON_VIEW2), 20)
    g.need("and the window goes back to the top", u64(cpu, CON_TOP2), 0)
    g.need("the content scrolled once", u64(cpu, CON_SCROLLN_RAW), 1)
    g.need("the hardware scroll hint is withheld while reserved", u64(cpu, CON_SCROLLN_VIEW), 0)

    before = bytes(u8(cpu, SNAP_BEFORE + i) for i in range(20))
    shown = bytes(u8(cpu, SNAP_SHOWN + i) for i in range(20))
    after = bytes(u8(cpu, SNAP_AFTER + i) for i in range(20))
    want = bytes([65 + i for i in range(19)] + [90])
    g.need("the stored grid holds what was printed into it", before, want)
    g.need("showing the keyboard changes not one stored cell", shown, before)
    g.need("hiding it again changes not one stored cell", after, before)
    return g


def run_once(a64, compiler, view_text: str, console_text: str, label: str):
    with tempfile.TemporaryDirectory(prefix="anvil-tkbview-") as td:
        work = pathlib.Path(td)
        source = stage(work, view_text, console_text)
        image = build(compiler, work, source)
        cpu, rc, steps = execute(a64, image)
    return cpu, rc, steps


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pmfc")
    parser.add_argument("--interp")
    parser.add_argument("--mutate", action="store_true")
    parser.add_argument("--geometry", action="store_true",
                        help="print what the layout actually computed, in pixels and in inches")
    args = parser.parse_args()

    compiler = locate("PMFC", args.pmfc, [ROOT / "pmfc.exe", ROOT / "pmfc"])
    a64 = load_interpreter(locate("PMF_A64_INTERP", args.interp, [ROOT / "tools" / "a64" / "a64_interp.py"]))

    view_text = VIEW.read_text(encoding="utf-8")
    console_text = CONSOLE.read_text(encoding="utf-8")

    cpu, rc, steps = run_once(a64, compiler, view_text, console_text, "product")
    g = grade(cpu, rc)
    if g.failures:
        print(f"touch_keyboard_view_emitted_check: FAIL ({g.checks} checks, {steps:,} instructions)")
        for failure in g.failures:
            print("  " + failure)
        return 1

    print(f"touch_keyboard_view_emitted_check: PASS - {g.checks} independent property checks "
          f"over {steps:,} executed A64 instructions")
    print("  the real TouchKeyboardLayout, TouchKeyboardHitKey, TouchKeyboardPaint and the")
    print("  real console viewport ran; no MMIO, framebuffer, GPU or DMA was touched")

    if args.geometry:
        print()
        print("  what the layout computed (149 px/in is the bench panel's own reading):")
        head = ("  slot  surface     scale  ppi  min  pref  gut  band y  band h  rows  "
                "keyH  keyH in  console rows")
        print(head)
        for slot, page, lw, lh, ppi, ds, ok, note in SCENARIOS:
            b = SCEN + slot * STRIDE
            if not u64(cpu, b + F_OK):
                text = cstr(cpu, u64(cpu, b + F_REFUSAL))
                print(f"  {slot:<5} {lw}x{lh:<7} {ds:<6} {ppi:<4} REFUSED: {text[:90]}")
                continue
            keys = u64(cpu, b + F_KEYS)
            kh = u64(cpu, b + F_KEYTAB + 24) if keys else 0
            ppi_used = ppi if ppi else 149
            print(f"  {slot:<5} {lw}x{lh:<7} {ds:<6} {ppi:<4} "
                  f"{u64(cpu, b + F_MIN):<4} {u64(cpu, b + F_PREF):<5} {u64(cpu, b + F_GUT):<4} "
                  f"{u64(cpu, b + F_BANDY):<7} {u64(cpu, b + F_BANDH):<7} "
                  f"{u64(cpu, b + F_ROWS):<5} {kh:<5} {kh / ppi_used:<8.3f} "
                  f"{u64(cpu, b + F_CONROWS)}")

    if not args.mutate:
        print("  (run with --mutate to also require every plausible mistake to be caught)")
        return 0

    print()
    failed = 0
    for name, where, fixed, broken in MUTANTS:
        text = view_text if where == "view" else console_text
        if text.count(fixed) != 1:
            print(f"  STALE  {name} - its anchor is not in {where} exactly once; the gate did not test it")
            failed += 1
            continue
        mutated = text.replace(fixed, broken, 1)
        try:
            if where == "view":
                mcpu, mrc, msteps = run_once(a64, compiler, mutated, console_text, name)
            else:
                mcpu, mrc, msteps = run_once(a64, compiler, view_text, mutated, name)
        except SystemExit as exc:
            # A MUTATION THAT WILL NOT BUILD PROVES NOTHING ABOUT THE GATE.
            # The compiler stopped it, and the checks this gate exists for
            # were never run, so it is reported as a hole and not as a
            # rejection - the same trap a64_touch_check's negative control
            # fell into by printing an unapplied mutation as a miss.
            print(f"  STALE  {name} - the mutation did not build or run, so the gate's")
            print(f"         checks were never exercised: {str(exc).splitlines()[0][:100]}")
            failed += 1
            continue
        mg = grade(mcpu, mrc)
        if mg.failures:
            print(f"  RED    {name} - {len(mg.failures)} checks failed, first: {mg.failures[0][:100]}")
        else:
            print(f"  GREEN  {name}  <-- THE GATE DID NOT NOTICE ({msteps:,} instructions)")
            failed += 1

    if failed:
        print(f"\ntouch_keyboard_view_emitted_check: {failed} of {len(MUTANTS)} mutations were not caught")
        return 1
    print(f"\ntouch_keyboard_view_emitted_check: all {len(MUTANTS)} mutations rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""What an interpolated varying must be, at a named pixel.

Anvil/Graphics/Vulkan/vk_interp_expect.pbi is the file the board
diagnostic asks "what colour should this pixel be?". It is the only
place in the Vulkan tree whose answers are not checked by comparing
bytes against hardware, because the hardware is the thing being tested -
so it is checked here instead, against a second implementation of the
same stated rule.

EVERY EXPECTATION IN THIS FILE IS BUILT HERE, from the chain written out
in that file's header - clip to screen, pixel centre, edge functions,
weighted average, 8-bit UNORM - and never from its output. The two sides
are written in different languages by different code, which is the whole
of the argument: an expectation the implementation produced would only
prove the implementation agrees with itself.

  PMF_COMPILER=<PureMetalForge.exe> PMF_A64_INTERP=<a64_interp.py> \\
      py -3 tools/vulkan_interp_check.py

Add --mutate to require every plausible mistake to be caught.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from pmf_compiler import resolve_compiler as _pmf_resolve_compiler  # noqa: E402

GATE = ROOT / "Anvil" / "Graphics" / "Vulkan" / "Tests" / "vulkan_interp_gate.pi4"
EXPECT = ROOT / "Anvil" / "Graphics" / "Vulkan" / "vk_interp_expect.pbi"
# THE BOARD DIAGNOSTIC IS NOT BUILT HERE, and that is deliberate: it pulls in
# the SPIR-V front end and the whole pipeline layer, which tools/vulkan_spirv_check.py
# and tools/vulkan_pipeline_check.py MUTATE while they run. Building it here
# would make this gate unable to run beside either of them. The diagnostic is
# built by tools/vulkan_pipeline_check.py, which owns that closure.

LOAD = 0x00400000
STACK = 0x03000000
LOADER_LR = 0xDEAD0000
STEP_LIMIT = 200_000_000
MMIO = 0xFC000000

IN = 0x06000000
OUT = 0x06100000
MAGIC = 0x564B4950

IN_SLOTS = 64
OUT_SLOTS = 128
HEAD = 64
MAX_PROBES = 8
PROBE_BASE = 16
PROBE_SLOTS = 9

TOL = 2
DIST_A = 0xFF102030
DIST_B = 0xFE152B33


# ----------------------------------------------------------------------
#  The rule, written a second time.
# ----------------------------------------------------------------------
def rnd(num: int, den: int) -> int:
    """Nearest integer, halves away from zero, for a signed rational."""
    if den == 0:
        return 0
    if den < 0:
        num, den = -num, -den
    if num >= 0:
        return (num + den // 2) // den
    return -(((-num) + den // 2) // den)


class Triangle:
    """One triangle, the way vk_interp_expect.pbi's header states it."""

    def __init__(self, view_w: int, view_h: int, verts, colours):
        self.ok = view_w >= 2 and view_h >= 2 and view_w % 2 == 0 and view_h % 2 == 0
        self.half_w = (view_w // 2) * 256
        self.half_h = (view_h // 2) * 256
        self.sx, self.sy = [], []
        for (xn, yn, den) in verts:
            self.sx.append(rnd(xn * self.half_w, den) + self.half_w)
            self.sy.append(rnd(yn * self.half_h, den) + self.half_h)
        self.c = [list(c) for c in colours]

    @staticmethod
    def edge(ax, ay, bx, by, px, py) -> int:
        return (bx - ax) * (py - ay) - (by - ay) * (px - ax)

    def area(self) -> int:
        return self.edge(self.sx[0], self.sy[0], self.sx[1], self.sy[1],
                         self.sx[2], self.sy[2])

    def weight(self, px: int, py: int, k: int) -> int:
        cx, cy = px * 256 + 128, py * 256 + 128
        a, b = (k + 1) % 3, (k + 2) % 3
        return self.edge(self.sx[a], self.sy[a], self.sx[b], self.sy[b], cx, cy)

    def inside(self, px: int, py: int) -> int:
        d = self.area()
        if d == 0:
            return 0
        for k in range(3):
            w = self.weight(px, py, k)
            if (w <= 0) if d > 0 else (w >= 0):
                return 0
        return 1

    def channel(self, px: int, py: int, ch: int) -> int:
        d = self.area()
        if d == 0:
            return 0
        acc = sum(self.weight(px, py, k) * self.c[k][ch] for k in range(3))
        return max(0, min(255, rnd(acc, d)))

    def expect(self, px: int, py: int) -> int:
        r, g, b, a = (self.channel(px, py, ch) for ch in range(4))
        return ((a << 24) | (r << 16) | (g << 8) | b) & 0xFFFFFFFF


def distance(got: int, want: int) -> int:
    return max(abs(((got >> (k * 8)) & 0xFF) - ((want >> (k * 8)) & 0xFF))
               for k in range(4))


# ----------------------------------------------------------------------
#  THE CASES.
#
#  Case 0 is the diagnostic's own: the panel's 800 x 1280 viewport, the
#  same triangle vulkanTriangleProof draws, and red, green, blue at its
#  three vertices. Its probes are the diagnostic's own probes, so this
#  gate checks the exact numbers the board will be compared against.
#
#  The rest exist to move one thing at a time: a winding reversal (the
#  weights must not care), an off-centre triangle, a probe outside, a
#  probe on an edge, a degenerate triangle, and a small viewport where
#  the pixel-centre offset is a large fraction of the triangle.
# ----------------------------------------------------------------------
PANEL_W, PANEL_H = 800, 1280

# (0, -1/2), (-1/2, 1/2), (1/2, 1/2) -> (400, 320), (200, 960), (600, 960)
PANEL_TRI = ((0, -1, 2), (-1, 1, 2), (1, 1, 2))
RGB = ((255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255))

# The three corner probes are inset 40 pixels along the median towards
# the centroid: a probe AT a vertex sits on two edges at once, where the
# rasteriser's fill rule and not arithmetic decides whether it is covered.
# The centroid is ((400+200+600)/3, (320+960+960)/3) = (400, 746.67).
CORNER0 = (400, 346)
CORNER1 = (213, 946)
CORNER2 = (587, 946)
CENTRE = (400, 747)
EDGEMID = (400, 940)

CASES = [
    dict(name="the panel triangle, red green blue",
         w=PANEL_W, h=PANEL_H, verts=PANEL_TRI, colours=RGB,
         probes=[CORNER0, CORNER1, CORNER2, CENTRE, EDGEMID,
                 (400, 500), (100, 100), (700, 1200)]),
    dict(name="the same triangle wound the other way",
         w=PANEL_W, h=PANEL_H,
         verts=((0, -1, 2), (1, 1, 2), (-1, 1, 2)),
         colours=((255, 0, 0, 255), (0, 0, 255, 255), (0, 255, 0, 255)),
         probes=[CORNER0, CORNER1, CORNER2, CENTRE]),
    dict(name="a triangle in the top left quarter",
         w=PANEL_W, h=PANEL_H,
         verts=((-3, -3, 4), (-1, -3, 4), (-3, -1, 4)),
         colours=((255, 255, 0, 255), (0, 255, 255, 255), (255, 0, 255, 255)),
         probes=[(120, 200), (150, 250), (400, 700), (60, 100)]),
    dict(name="a degenerate triangle - three collinear vertices",
         w=PANEL_W, h=PANEL_H,
         verts=((-1, 0, 2), (0, 0, 1), (1, 0, 2)),
         colours=RGB, probes=[CENTRE, (400, 640)]),
    dict(name="a 64 x 64 viewport, where a pixel centre is a big fraction",
         w=64, h=64,
         verts=((0, -1, 2), (-1, 1, 2), (1, 1, 2)),
         colours=RGB, probes=[(32, 40), (32, 47), (20, 46), (44, 46), (2, 2)]),
    # Every clip coordinate above divides exactly, so the rounding in the
    # clip-to-screen step never has anything to round. This one does not:
    # -2/3 of the half width is x.67, which rounds AWAY from zero, and a
    # truncating implementation lands one unit of 1/256 pixel short.
    dict(name="clip coordinates that do not divide exactly",
         w=PANEL_W, h=PANEL_H,
         verts=((-2, -2, 3), (2, -1, 3), (0, 2, 3)),
         colours=RGB, probes=[(400, 700), (250, 400), (550, 500), (400, 200)]),
    # A probe whose centre lands EXACTLY on an edge. The triangle's left
    # side is the vertical line x = 32.5 pixels, which is the centre of
    # pixel column 32, so the edge function there is exactly zero and the
    # strict inside test must say no. Which way a rasteriser resolves that
    # is a fill rule, not arithmetic, and a diagnostic must not probe one.
    dict(name="a probe centre exactly on an edge",
         w=64, h=64,
         verts=((1, -63, 64), (1, 63, 64), (-63, 63, 64)),
         colours=RGB, probes=[(32, 20), (20, 40), (32, 32), (50, 10), (40, 45)]),
    dict(name="an odd viewport width, which Begin must refuse",
         w=801, h=1280, verts=PANEL_TRI, colours=RGB, probes=[CENTRE]),
]


def locate(env_name: str, explicit, fallbacks) -> pathlib.Path:
    choices = []
    if explicit:
        choices.append(pathlib.Path(explicit))
    if os.environ.get(env_name):
        choices.append(pathlib.Path(os.environ[env_name]))
    choices.extend(fallbacks)
    for path in choices:
        if path.is_file():
            return path.resolve()
    raise SystemExit(f"vulkan_interp_check: {env_name} was not found; set it or pass its option")


def locate_compiler(explicit) -> pathlib.Path:
    """Resolve through the shared, validating resolver (tools/pmf_compiler.py)
    when a compiler was named (explicit, PMF_COMPILER or the legacy PMFC);
    otherwise fall back to a copy in the repo root, unchanged (forum 977)."""
    requested = explicit or os.environ.get("PMF_COMPILER") or os.environ.get("PMFC")
    if requested:
        return pathlib.Path(_pmf_resolve_compiler(requested))
    fallback = ROOT / "PureMetalForge.exe"
    if fallback.is_file():
        return fallback.resolve()
    raise SystemExit("set PMF_COMPILER to PureMetalForge.exe, or pass --compiler")


def load_interpreter(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("anvil_vkig_a64_interp", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"vulkan_interp_check: cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def compile_one(compiler: pathlib.Path, source: pathlib.Path, name: str,
                load: int = LOAD, stack: int = STACK) -> pathlib.Path:
    image = pathlib.Path(tempfile.gettempdir()) / name
    command = [
        str(compiler), "--compile", source.relative_to(ROOT).as_posix(),
        "-t", "pi4", "--load-addr", hex(load), "--stack-addr", hex(stack),
        "--entry-returns", "-o", str(image),
    ]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    run = subprocess.run(command, cwd=ROOT, env=env, text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise SystemExit("vulkan_interp_check: %s failed to compile\n%s"
                         % (source.name, run.stdout))
    return image


def poke(cpu, addr: int, value: int) -> None:
    value &= (1 << 64) - 1
    for b in range(8):
        cpu.memory[addr + b] = (value >> (8 * b)) & 0xFF


def u64(cpu, addr: int) -> int:
    return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(8))


def s64(cpu, addr: int) -> int:
    v = u64(cpu, addr)
    return v - (1 << 64) if v >= (1 << 63) else v


def execute(a64, image: pathlib.Path):
    cpu = a64.A64()
    for i, byte in enumerate(image.read_bytes()):
        cpu.memory[LOAD + i] = byte
    a64.attach_symbols(cpu, image, LOAD)

    poke(cpu, IN, len(CASES))
    for i, case in enumerate(CASES):
        base = IN + HEAD + i * IN_SLOTS * 8
        poke(cpu, base + 0 * 8, case["w"])
        poke(cpu, base + 1 * 8, case["h"])
        for k, (xn, yn, den) in enumerate(case["verts"]):
            poke(cpu, base + (2 + k * 3) * 8, xn)
            poke(cpu, base + (3 + k * 3) * 8, yn)
            poke(cpu, base + (4 + k * 3) * 8, den)
        for k, colour in enumerate(case["colours"]):
            for ch in range(4):
                poke(cpu, base + (11 + k * 4 + ch) * 8, colour[ch])
        probes = case["probes"]
        poke(cpu, base + 23 * 8, len(probes))
        for p, (px, py) in enumerate(probes):
            poke(cpu, base + (24 + p * 2) * 8, px)
            poke(cpu, base + (25 + p * 2) * 8, py)

    cpu.pc, cpu.sp, cpu.x[30] = LOAD, STACK, LOADER_LR

    def guard(a: int) -> None:
        if a >= MMIO:
            raise SystemExit(
                f"vulkan_interp_check: MMIO access at ${a:08X} - the expectation module is "
                "integer arithmetic over memory this checker supplies, so reaching a "
                "peripheral means it grew a dependency it must not have")

    def load(a: int, size: int) -> int:
        cpu.align_guard(a, size, False)
        guard(a)
        return sum(cpu.memory.get(a + i, 0) << (8 * i) for i in range(size))

    def store(a: int, value: int, size: int) -> None:
        cpu.align_guard(a, size, True)
        guard(a)
        for i in range(size):
            cpu.memory[a + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    for steps in range(STEP_LIMIT):
        if cpu.pc == LOADER_LR:
            return cpu, cpu.x[0] & 0xFFFFFFFFFFFFFFFF, steps
        cpu.step()
    raise SystemExit(f"vulkan_interp_check: the gate did not return in {STEP_LIMIT} steps")


class Grader:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.checks = 0

    def need(self, name, got, want) -> None:
        self.checks += 1
        if got != want:
            self.failures.append(f"{name}: got {got!r}, wanted {want!r}")


def grade(cpu, rc) -> Grader:
    g = Grader()
    g.need("the gate returned its report block", rc, OUT)
    g.need("the report's magic", hex(u64(cpu, OUT) & 0xFFFFFFFF), hex(MAGIC))
    g.need("the case count", u64(cpu, OUT + 8), len(CASES))

    for i, case in enumerate(CASES):
        tag = f"case {i} ({case['name']})"
        base = OUT + HEAD + i * OUT_SLOTS * 8
        tri = Triangle(case["w"], case["h"], case["verts"], case["colours"])
        g.need(f"{tag}: Begin", u64(cpu, base + 0 * 8), 1 if tri.ok else 0)
        if not tri.ok:
            # A refused viewport must leave every derived number at zero:
            # a half-built triangle that still answers is the failure this
            # case exists to forbid.
            g.need(f"{tag}: the area of a refused viewport",
                   s64(cpu, base + 1 * 8), 0)
            for k in range(3):
                g.need(f"{tag}: screen x{k} of a refused viewport",
                       s64(cpu, base + (2 + k * 2) * 8), 0)
                g.need(f"{tag}: screen y{k} of a refused viewport",
                       s64(cpu, base + (3 + k * 2) * 8), 0)
            continue

        g.need(f"{tag}: twice the signed area", s64(cpu, base + 1 * 8), tri.area())
        for k in range(3):
            g.need(f"{tag}: screen x{k}", s64(cpu, base + (2 + k * 2) * 8), tri.sx[k])
            g.need(f"{tag}: screen y{k}", s64(cpu, base + (3 + k * 2) * 8), tri.sy[k])
        g.need(f"{tag}: the stated tolerance", u64(cpu, base + 8 * 8), TOL)
        g.need(f"{tag}: the probe count", u64(cpu, base + 9 * 8), len(case["probes"]))
        g.need(f"{tag}: distance of a word from itself",
               u64(cpu, base + 10 * 8), distance(DIST_A, DIST_A))
        g.need(f"{tag}: distance is the worst channel",
               u64(cpu, base + 11 * 8), distance(DIST_A, DIST_B))

        for p, (px, py) in enumerate(case["probes"]):
            pb = base + (PROBE_BASE + p * PROBE_SLOTS) * 8
            what = f"{tag}: probe {p} ({px},{py})"
            g.need(f"{what} inside", u64(cpu, pb + 0 * 8), tri.inside(px, py))
            g.need(f"{what} expected pixel",
                   hex(u64(cpu, pb + 1 * 8)), hex(tri.expect(px, py)))
            for ch, letter in enumerate("rgba"):
                g.need(f"{what} {letter}", u64(cpu, pb + (2 + ch) * 8),
                       tri.channel(px, py, ch))
            for k in range(3):
                g.need(f"{what} weight {k}", s64(cpu, pb + (6 + k) * 8),
                       tri.weight(px, py, k))

    # The properties the whole point rests on, checked on case 0 only
    # because they are statements about the rule and not about a case.
    tri = Triangle(CASES[0]["w"], CASES[0]["h"], CASES[0]["verts"], CASES[0]["colours"])
    d = tri.area()
    for p, (px, py) in enumerate(CASES[0]["probes"]):
        if not tri.inside(px, py):
            continue
        total = sum(tri.weight(px, py, k) for k in range(3))
        g.need(f"the three weights at probe {p} sum to twice the area", total, d)
    # At each corner probe the owning vertex must dominate: this is what
    # makes a gradient run distinguish a real interpolation from a flat
    # fill, and if it were not true the board check would prove nothing.
    for k, probe in enumerate((CORNER0, CORNER1, CORNER2)):
        got = [tri.channel(probe[0], probe[1], ch) for ch in range(3)]
        g.need(f"corner probe {k} is dominated by vertex {k}",
               got.index(max(got)), k)
        g.need(f"corner probe {k}'s own channel is well clear of the others",
               max(got) - sorted(got)[1] > 3 * TOL, True)
    return g


MUTANTS = (
    ("the pixel centre is dropped, so a varying is sampled at the corner",
     "  cx = (px * 256) + 128\n  cy = (py * 256) + 128\n",
     "  cx = (px * 256)\n  cy = (py * 256)\n"),
    ("the viewport centre is not added back after the clip transform",
     "  avkiSx[k] = avkiRound(xNum * avkiHalfW, den) + avkiHalfW\n",
     "  avkiSx[k] = avkiRound(xNum * avkiHalfW, den)\n"),
    ("the half height is used for x as well as for y",
     "  avkiSy[k] = avkiRound(yNum * avkiHalfH, den) + avkiHalfH\n",
     "  avkiSy[k] = avkiRound(yNum * avkiHalfW, den) + avkiHalfW\n"),
    ("rounding a negative rational rounds towards zero",
     "  ProcedureReturn -(((-num) + (den / 2)) / den)\n",
     "  ProcedureReturn -((-num) / den)\n"),
    ("the edge function's two products are swapped, flipping every sign",
     "  ProcedureReturn ((bx - ax) * (py - ay)) - ((by - ay) * (px - ax))\n",
     "  ProcedureReturn ((by - ay) * (px - ax)) - ((bx - ax) * (py - ay))\n"),
    ("weight 1 and weight 2 are exchanged, so two vertices swap colours",
     "  If k = 1\n    ProcedureReturn avkiEdge(avkiSx[2], avkiSy[2], avkiSx[0], avkiSy[0], cx, cy)\n  EndIf\n",
     "  If k = 1\n    ProcedureReturn avkiEdge(avkiSx[0], avkiSy[0], avkiSx[1], avkiSy[1], cx, cy)\n  EndIf\n"),
    ("a probe exactly on an edge counts as inside",
     "      If w <= 0 : ProcedureReturn 0 : EndIf\n",
     "      If w < 0 : ProcedureReturn 0 : EndIf\n"),
    ("the weighted average forgets to normalise against the area",
     "  v = avkiRound(acc, d)\n",
     "  v = avkiRound(acc, 1)\n"),
    ("red and blue are packed the wrong way round",
     "  ProcedureReturn ((a << 24) | (r << 16) | (g << 8) | b) & $FFFFFFFF\n",
     "  ProcedureReturn ((a << 24) | (b << 16) | (g << 8) | r) & $FFFFFFFF\n"),
    ("the distance is the last channel rather than the worst",
     "    If d > worst : worst = d : EndIf\n",
     "    worst = d\n"),
    ("the tolerance quietly widens",
     "#ANVIL_VKI_TOL = 2\n",
     "#ANVIL_VKI_TOL = 8\n"),
    ("an odd viewport is accepted, putting its centre on a half pixel",
     "  If (viewW % 2) <> 0 Or (viewH % 2) <> 0 : ProcedureReturn 0 : EndIf\n",
     "  If (viewW % 2) < 0 Or (viewH % 2) < 0 : ProcedureReturn 0 : EndIf\n"),
    ("a channel is clamped to 254 instead of 255",
     "  If v > 255 : v = 255 : EndIf\n",
     "  If v > 254 : v = 254 : EndIf\n"),
    ("a degenerate triangle answers with a colour instead of zero",
     "  d = AnvilVkInterpArea()\n  If d = 0 : ProcedureReturn 0 : EndIf\n  acc = 0\n",
     "  d = AnvilVkInterpArea()\n  If d = 0 : d = 1 : EndIf\n  acc = 0\n"),
)


def run(a64, compiler):
    cpu, rc, steps = execute(a64, compile_one(compiler, GATE, "anvil_vk_interp_gate.img"))
    return grade(cpu, rc), steps


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler")
    parser.add_argument("--interp")
    parser.add_argument("--mutate", action="store_true")
    args = parser.parse_args()

    compiler = locate_compiler(args.compiler)
    a64 = load_interpreter(locate("PMF_A64_INTERP", args.interp,
                                  [ROOT / "tools" / "a64" / "a64_interp.py"]))

    g, steps = run(a64, compiler)
    if g.failures:
        print(f"vulkan_interp_check: FAIL ({g.checks} checks, {steps:,} instructions)")
        for failure in g.failures:
            print("  " + failure)
        return 1

    probes = sum(len(c["probes"]) for c in CASES)
    print(f"vulkan_interp_check: PASS - {g.checks} property checks over "
          f"{steps:,} executed A64 instructions")
    print(f"  {len(CASES)} triangles and {probes} probe pixels: the clip-to-screen")
    print("  transform, twice the signed area, the three barycentric numerators, the")
    print("  strict inside test, the four channels and the packed B8G8R8A8 word, each")
    print("  against a second implementation of the rule written in this file")
    print("  the weights at every covered probe sum to twice the area, and each corner")
    print("  probe is dominated by its own vertex by more than three tolerances")
    print("  NOT ONE MMIO access was made - this module owns no hardware")

    if not args.mutate:
        print("  (run with --mutate to also require every plausible mistake to be caught)")
        return 0

    print()
    missed = 0
    original = EXPECT.read_text(encoding="utf-8")
    for name, fixed, broken in MUTANTS:
        if original.count(fixed) != 1:
            print(f"  STALE  {name} - its anchor appears {original.count(fixed)} times")
            missed += 1
            continue
        EXPECT.write_text(original.replace(fixed, broken, 1), encoding="utf-8")
        try:
            mg, _ = run(a64, compiler)
            red = bool(mg.failures)
            first = mg.failures[0][:96] if mg.failures else ""
        except SystemExit as exc:
            red, first = True, str(exc).splitlines()[0][:96]
        finally:
            EXPECT.write_text(original, encoding="utf-8")
        if red:
            print(f"  RED    {name} - {first}")
        else:
            print(f"  GREEN  {name}  <-- THE GATE DID NOT NOTICE")
            missed += 1

    print()
    if missed:
        print(f"vulkan_interp_check: {missed} of {len(MUTANTS)} mutations were not caught")
        return 1
    print(f"vulkan_interp_check: all {len(MUTANTS)} mutations rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

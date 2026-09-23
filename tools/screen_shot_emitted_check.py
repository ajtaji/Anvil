#!/usr/bin/env python3
"""Execute the shipped screenshot-capture bodies, and the memory map they use.

THE RULING, 2026-09-11: every board run comes back with a picture. The two
ways that can silently not happen are the two this gate is about, and neither
shows up on a bench where somebody is watching the panel:

  THE WRONG BUFFER. With the console sideways, what it draws into is not
  what the panel scans. A capture of the drawing buffer is the same SIZE and
  different BYTES, so every length check passes and the picture is of an
  intention rather than of a screen.

  THE WRONG MOMENT. The monitor's own report that a payload returned is
  printed through the console grid onto the surface being asked about. A
  capture taken one statement later is a picture of that report.

So the actual shipped bodies - ScrCaptureToArea, ScrCaptureSnapshot and the
three readers out of screen_source.pi4, ScrShotTier and ScrShotNow out of
screen_cmd.pi4, the rotation map out of screen_geom.pi4, and the WHOLE of
RunAt out of cache.pi4 - are spliced into a fixture with a modelled turned
panel and counting stubs, compiled by the one application, and executed on
the A64 interpreter. Then each mutant is built and must be REJECTED.

AND THE MEMORY MAP IS CHECKED STATICALLY, in this file, because "is the
capture area clear of every other owner and big enough for the largest frame
this monitor can bring up" is a question about a list of constants. Executing
a copy loop cannot answer it, and getting it wrong means a capture written
over the framebuffer it was copied from, or over a loaded driver.

  PMF_COMPILER=<PureMetalForge.exe> PMF_A64_INTERP=<a64_interp.py> \
      python tools/screen_shot_emitted_check.py
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEMMAP = ROOT / "RaspberryPi4" / "Board" / "memmap.pi4"
SOURCE = ROOT / "RaspberryPi4" / "Board" / "screen_source.pi4"
GEOM = ROOT / "RaspberryPi4" / "Board" / "screen_geom.pi4"
SCREEN = ROOT / "RaspberryPi4" / "Board" / "screen_cmd.pi4"
CACHE = ROOT / "RaspberryPi4" / "Board" / "cache.pi4"
DISPLAY = ROOT / "RaspberryPi4" / "Lib" / "display.pi4"
ABI = ROOT / "Anvil" / "Hal" / "abi.pbi"
HWCON = ROOT / "RaspberryPi4" / "Board" / "hw_con.pi4"
SHOTARM = ROOT / "Anvil" / "Core" / "shotarm.pbi"
FIXTURE = ROOT / "RaspberryPi4" / "Tests" / "screen_shot_emitted_gate.pi4"

LOAD = 0x00400000
STACK = 0x03000000
LOADER_LR = 0xDEAD0000
STEP_LIMIT = 40_000_000

# The order is the include order the product has: the pure map first, then
# the seam that uses it, then the command layer that knows which renderer is
# live, then the payload path. A procedure has to be defined before it is
# called in this language, and this list is that rule written down.
BODIES = (
    (DISPLAY, "DisplayMemorySafe"),
    (SHOTARM, "ShotArm"),
    (SHOTARM, "ShotArmed"),
    (SHOTARM, "ShotTakeArm"),
    (SHOTARM, "ShotNextSeq"),
    (SHOTARM, "ShotSeq"),
    (SHOTARM, "ShotSeqCarry"),
    (GEOM, "ScrSideways"),
    (GEOM, "ScrLogicalW"),
    (GEOM, "ScrLogicalH"),
    (GEOM, "ScrMapX"),
    (GEOM, "ScrMapY"),
    (GEOM, "ScrCapturePixel"),
    (SOURCE, "ScrCaptureSnapshot"),
    (SOURCE, "ScrCaptureToArea"),
    (SOURCE, "ScrShotValid"),
    (SOURCE, "ScrShotField"),
    (SOURCE, "ScrShotPixels"),
    (SCREEN, "ScrShotTier"),
    (SCREEN, "ScrShotNow"),
    (CACHE, "RunAt"),
)


def required_path(value: str | None, name: str) -> Path:
    if not value:
        raise SystemExit(f"screen shot gate: set {name} or pass its option")
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"screen shot gate: {name} not found: {path}")
    return path


def load_interpreter(path: Path):
    spec = importlib.util.spec_from_file_location("anvil_shot_a64", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"screen shot gate: cannot load interpreter {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def procedure(path: Path, name: str) -> str:
    text = path.read_text(encoding="utf-8")
    found = re.search(
        rf"(?ms)^Procedure(?:\.i)? {re.escape(name)}\(.*?^EndProcedure\s*$", text)
    if not found:
        raise SystemExit(
            f"screen shot gate: {name} was not found in {path.name}, so the "
            "gate would have graded a model instead of the product.")
    return found.group(0)


def product_bodies() -> str:
    return "\n\n".join(procedure(path, name) for path, name in BODIES)


def fixture(bodies: str) -> str:
    text = FIXTURE.read_text(encoding="utf-8")
    if text.count("; @@BODY@@") != 1:
        raise SystemExit("screen shot gate: the fixture's body marker drifted")
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
         "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
         "--entry-returns", "-o", str(image), "-s"],
        cwd=ROOT, env={**os.environ, "PMF_ROOT": str(ROOT)},
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise SystemExit(f"screen shot gate: {stem} did not compile\n{run.stdout}")
    return image


def execute(a64, image: Path) -> tuple[int, int]:
    cpu = a64.A64()
    for offset, byte in enumerate(image.read_bytes()):
        cpu.memory[LOAD + offset] = byte
    a64.attach_symbols(cpu, image, LOAD)
    cpu.pc = LOAD
    cpu.sp = STACK
    cpu.x[30] = LOADER_LR

    # THE MODELLED PANEL AND THE MODELLED CAPTURE AREA ARE PLAIN DRAM, and
    # nothing here may touch a peripheral: a capture that reached MMIO would
    # be reading a register block and calling it a picture.
    def guard(addr: int, size: int, write: bool) -> None:
        cpu.align_guard(addr, size, write)
        if addr >= 0xFC000000:
            raise SystemExit(
                f"screen shot gate: the capture path touched MMIO at ${addr:08X}")

    def load(addr: int, size: int) -> int:
        guard(addr, size, False)
        return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr: int, value: int, size: int) -> None:
        guard(addr, size, True)
        for i in range(size):
            cpu.memory[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    for steps in range(STEP_LIMIT):
        if cpu.pc == LOADER_LR:
            return cpu.x[0], steps
        cpu.step()
    raise SystemExit(f"screen shot gate: exceeded {STEP_LIMIT} instructions")


def mutate(text: str, edits, label: str) -> str:
    """Apply one mutant's edits. A mutant may take more than one.

    MOVING A STATEMENT IS TWO EDITS AND HAS TO BE BOTH. A mutant that only
    ADDED a second capture later would still capture first and would survive,
    which is a gate that passes a check it is not making - so the anchors are
    counted and a mutant that cannot be built is an error rather than a
    silently skipped case.
    """
    for old, new in edits:
        if text.count(old) != 1:
            raise SystemExit(
                f"screen shot gate: an anchor for the {label!r} mutant appears "
                f"{text.count(old)} times, so that mutant is not being built. "
                "Fix the anchor rather than dropping the mutant.")
        text = text.replace(old, new, 1)
    return text


MUTATIONS = (
    ("DMA quarantine is ignored during screenshot capture",
     "    If DmaQuarantined() <> 0 : ProcedureReturn 0 : EndIf",
     "    If DmaQuarantined() < 0 : ProcedureReturn 0 : EndIf"),
    # THE ONE THIS GATE EXISTS FOR, HALF ONE. Capture the buffer the console
    # DRAWS into rather than the one the panel scans. Same size, different
    # bytes, and on a quiet bench a plausible picture of a frame nobody saw.
    ("the drawing buffer is captured instead of the scanned one",
     "    fb = #MON_FB_SCAN\n    pw = #MON_FB_PANEL_W\n    ph = #MON_FB_PANEL_H\n"
     "    p = pw * 4\n    d = 4\n    r = gScrRot",
     "    fb = #MON_FB_DRAW\n    pw = #MON_FB_PANEL_W\n    ph = #MON_FB_PANEL_H\n"
     "    p = pw * 4\n    d = 4\n    r = gScrRot"),
    # THE ONE THIS GATE EXISTS FOR, HALF TWO. Keep the frame after the
    # monitor has printed its report about the run - which is after the
    # console has repainted over it.
    ("the console repaints before the frame is kept",
     "  If ShotTakeArm() <> 0\n    ScrShotNow(#MON_SHOT_WHO_RETURN, gGoRc)\n  EndIf\n",
     ""),
    # THE SAME STATEMENT, MOVED rather than removed - which is the mistake
    # somebody would actually make: keep the frame, but do it down beside the
    # line that reports x0, where it reads as belonging with the report. By
    # then the console has repainted.
    ("the frame is kept only after the return line is printed",
     "  If ShotTakeArm() <> 0\n    ScrShotNow(#MON_SHOT_WHO_RETURN, gGoRc)\n  EndIf\n",
     "",
     '  Print("The payload returned to the monitor. Its x0 register held ")',
     '  If ShotTakeArm() <> 0\n'
     '    ScrShotNow(#MON_SHOT_WHO_RETURN, gGoRc)\n'
     '  EndIf\n'
     '  Print("The payload returned to the monitor. Its x0 register held ")'),
    # THE LOGICAL SURFACE ON A TURNED PANEL. Recording the console's own
    # width and height as the raster geometry makes the host decode the copy
    # at the wrong pitch, which looks like a display fault.
    ("the logical geometry is recorded as the physical raster",
     "  PokeI(#MON_SHOT_HDR + #MON_SHOT_OFF_PANELW, panelW)\n"
     "  PokeI(#MON_SHOT_HDR + #MON_SHOT_OFF_PANELH, panelH)",
     "  PokeI(#MON_SHOT_HDR + #MON_SHOT_OFF_PANELW, w)\n"
     "  PokeI(#MON_SHOT_HDR + #MON_SHOT_OFF_PANELH, h)"),
    ("the rotation is recorded as zero on a turned panel",
     "  PokeI(#MON_SHOT_HDR + #MON_SHOT_OFF_ROT,    rot)",
     "  PokeI(#MON_SHOT_HDR + #MON_SHOT_OFF_ROT,    0)"),
    # THE MAGIC IS THE ONLY THING THAT SAYS "THERE IS A PICTURE HERE". Not
    # clearing it first means a refused capture leaves the previous run's
    # picture looking like this run's.
    ("a refused capture leaves the previous picture looking current",
     "  PokeI(#MON_SHOT_HDR + #MON_SHOT_OFF_MAGIC, 0)\n\n"
     "  If ScrCaptureSnapshot(",
     "  If ScrCaptureSnapshot("),
    # THE SIZE CHECK. Writing what fits is a torn picture that decodes.
    ("a frame larger than the area is truncated instead of refused",
     "  If n < 1 Or n > #MON_SHOT_PIX_BYTES\n    ProcedureReturn 0\n  EndIf",
     "  If n < 1\n    ProcedureReturn 0\n  EndIf\n  If n > #MON_SHOT_PIX_BYTES\n"
     "    n = #MON_SHOT_PIX_BYTES\n  EndIf"),
    # THE SEQUENCE NUMBER is what tells a host "this is the run I asked
    # about". A frozen one makes a stale picture indistinguishable.
    ("the sequence number does not move",
     "  PokeI(#MON_SHOT_HDR + #MON_SHOT_OFF_SEQ,    ShotNextSeq())",
     "  PokeI(#MON_SHOT_HDR + #MON_SHOT_OFF_SEQ,    ShotSeq())"),
    # THE NUMBER ACROSS A RESET (forum 876). Without the carry the first
    # capture of every boot is numbered below the picture it replaces.
    ("the sequence number restarts after a reset",
     "    ShotSeqCarry(PeekI(#MON_SHOT_HDR + #MON_SHOT_OFF_SEQ))\n",
     ""),
    # THE RUN RECORD'S RETURN, dropped: `last run` would say a payload that
    # came back never did.
    ("the run record never hears that the payload returned",
     "  RunRecordReturn(gGoRc)\n",
     ""),
    # THE RUN RECORD'S ENTRY, moved above the refusals: a refused jump would
    # move the run number and read as entered.
    ("a refused jump is recorded as an entry",
     "  RunRecordEnter(a, dead)\n",
     "",
     "  If HitsMonitor(a, a) <> 0\n    Print(\"!! \")",
     "  RunRecordEnter(a, dead)\n  If HitsMonitor(a, a) <> 0\n    Print(\"!! \")"),
    # THE DEADMAN IS ONE-SHOT (forum 879). Reading the setting without
    # spending it is the defect that left every later payload armed.
    ("the deadman setting survives the payload it was armed for",
     "  dead = gDead\n  gDead = 0\n",
     "  dead = gDead\n"),
    # And spending it before the refusals takes it from a jump that never ran.
    ("a refused jump spends the deadman",
     "  If HitsMonitor(a, a) <> 0\n    Print(\"!! \")",
     "  If HitsMonitor(a, a) <> 0\n    gDead = 0\n    Print(\"!! \")"),
    # THE TIER. A measured frame time read against the wrong path is
    # unreadable, and this is the only place the path is recorded.
    ("the tier is always reported as the processor path",
     "  CompilerIf #ANVIL_V3D_CONSOLE = 1\n  If gV3dConOn <> 0\n"
     "    ProcedureReturn #HW_TIER_V3D\n  EndIf\n  CompilerEndIf",
     "  CompilerIf #ANVIL_V3D_CONSOLE = 1\n  CompilerEndIf"),
    # THE ARM IS ONE-SHOT. An arm that survives overwrites the picture
    # somebody is still reading with the next run's.
    ("the arm is read without being spent",
     "Procedure.i ShotTakeArm()\n  Define was.i\n  was = gShotArm\n  gShotArm = 0\n"
     "  ProcedureReturn was\nEndProcedure",
     "Procedure.i ShotTakeArm()\n  ProcedureReturn gShotArm\nEndProcedure"),
    # x0 AND THE PICTURE ARE ONE FACT. A header that carried zero always
    # would let a host pair a failing run with a picture and call it a pass.
    ("the payload's x0 is not recorded with its picture",
     "  PokeI(#MON_SHOT_HDR + #MON_SHOT_OFF_X0,     x0)",
     "  PokeI(#MON_SHOT_HDR + #MON_SHOT_OFF_X0,     0)"),
    # A CAPTURE WITH NO SCREEN BEHIND THE CONSOLE would read zeroes out of
    # whatever DisplayViewBase last answered and call it a picture.
    ("a console with no screen is captured anyway",
     "    If gScrDsiUp = 0\n      ProcedureReturn 0\n    EndIf\n    fb = #MON_FB_SCAN",
     "    fb = #MON_FB_SCAN"),
    # THE REFUSED JUMP. Nothing ran, so there is nothing to keep - and the
    # arm must survive, or an operator who mistyped an address silently
    # loses the capture for the run they meant.
    ("a refused jump spends the arm",
     "  If HitsMonitor(a, a) <> 0\n    Print(\"!! \")",
     "  If HitsMonitor(a, a) <> 0\n    ShotTakeArm()\n    Print(\"!! \")"),
)


# =====================================================================
#  THE MEMORY MAP, CHECKED AS A LIST OF CONSTANTS
# =====================================================================
def constants(text: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for name, value in re.findall(r"^#(\w+)\s*=\s*(\$?[0-9A-Fa-f]+)\s*(?:;|$)",
                                  text, re.M):
        try:
            out[name] = int(value[1:], 16) if value.startswith("$") else int(value)
        except ValueError:
            continue
    return out


def check_map() -> list[str]:
    """The capture area's placement and size, against every other owner.

    THE LARGEST FRAME THIS MONITOR CAN BRING UP is what the area has to
    hold, and the panel is not it: the DSI panel is 800 x 1280 x 4 and an
    HDMI console on this bench is 1824 x 984 x 4. An area sized for the
    panel would silently refuse every HDMI capture.
    """
    text = MEMMAP.read_text(encoding="utf-8")
    k = constants(text)
    notes: list[str] = []
    need = ("MON_SHOT_LO", "MON_SHOT_HI", "MON_SHOT_HDR", "MON_SHOT_PIX",
            "MON_SHOT_PIX_BYTES", "MON_SHOT_MAGIC", "MON_REGION_SHOT",
            "MON_DATA_LO", "MON_DATA_HI", "MON_VK_HEAP_LO",
            "MON_VK_HEAP_HI")
    missing = [name for name in need if name not in k]
    if missing:
        raise SystemExit(f"screen shot gate: memmap.pi4 has no {', '.join(missing)}")

    lo, hi = k["MON_SHOT_LO"], k["MON_SHOT_HI"]
    if k["MON_SHOT_HDR"] != lo:
        raise SystemExit("screen shot gate: the header is not at the area's base")
    if k["MON_SHOT_PIX"] != lo + 0x1000:
        raise SystemExit("screen shot gate: the pixels do not start on the "
                         "page after the header")
    if k["MON_SHOT_PIX_BYTES"] != hi - k["MON_SHOT_PIX"] + 1:
        raise SystemExit(
            f"screen shot gate: MON_SHOT_PIX_BYTES is {k['MON_SHOT_PIX_BYTES']} "
            f"and the window from {k['MON_SHOT_PIX']:#x} to {hi:#x} is "
            f"{hi - k['MON_SHOT_PIX'] + 1}. A capture that believed the larger "
            "of those would write past the area.")
    if lo % 0x100000 or (hi + 1) % 0x100000:
        raise SystemExit("screen shot gate: the capture area is not a whole "
                         "number of megabytes, so a refusal naming it would "
                         "not read as a window")

    # Every other owner this board declares, and the payload windows.
    others = {
        "the monitor's variables": (k["MON_DATA_LO"], k["MON_DATA_HI"]),
        "the Vulkan heap": (k["MON_VK_HEAP_LO"], k["MON_VK_HEAP_HI"]),
        "the DSI framebuffer": (k["MON_FB_LO"], k["MON_FB_HI"]),
        "the module region": (k["MOD_REGION_LO"], k["MOD_REGION_HI"]),
        "the autoboot record": (k["AB_BASE"], k["AB_BASE"] + k["AB_BYTES"] - 1),
        "the boot phase record": (k["MON_PHASE_LO"],
                                  k["MON_PHASE_LO"] + k["MON_PHASE_BYTES"] - 1),
        "the reserved raw stacks": (k["CORE_RAW_STACK_LO"], k["CORE_RAW_STACK_HI"]),
        "the high payload window": (k["PAY1_LO"], k["PAY1_HI"]),
    }
    v3d = (ROOT / "RaspberryPi4" / "Board" / "v3d_console.pi4").read_text(encoding="utf-8")
    v3dk = constants(v3d)
    if "V3DCON_ARENA" in v3dk and "V3DCON_ARENA_BYTES" in v3dk:
        others["the V3D arena"] = (v3dk["V3DCON_ARENA"],
                                   v3dk["V3DCON_ARENA"] + v3dk["V3DCON_ARENA_BYTES"] - 1)
    else:
        notes.append("v3d_console.pi4's arena constants could not be read, so "
                     "the capture area was NOT checked against them")
    for label, (olo, ohi) in others.items():
        if lo <= ohi and hi >= olo:
            raise SystemExit(
                f"screen shot gate: the capture area {lo:#x}..{hi:#x} overlaps "
                f"{label} at {olo:#x}..{ohi:#x}. A capture there would be "
                "written over something that is in use.")
    # THE LOW PAYLOAD WINDOW'S TOP EDGE IS A CONSTANT; its bottom follows the
    # image, so the only thing worth asserting is that the area is above it.
    if lo <= k["PAY0_HI"]:
        raise SystemExit(
            f"screen shot gate: the capture area starts at {lo:#x}, inside the "
            f"low payload window which ends at {k['PAY0_HI']:#x}. A `load` or a "
            "`net recv` would land on the picture and InPayload() would allow it.")

    # The frames it has to hold.
    for label, (w, h) in (("the DSI panel", (800, 1280)),
                          ("this bench's HDMI console", (1824, 984)),
                          ("a 1920 x 1200 mode", (1920, 1200))):
        want = w * h * 4
        if k["MON_SHOT_PIX_BYTES"] < want:
            raise SystemExit(
                f"screen shot gate: {label} is {want} bytes at 32 bpp and the "
                f"capture area holds {k['MON_SHOT_PIX_BYTES']}. Every capture "
                "of that screen would be refused.")

    # The magic must be positive in a signed .i, or PeekI would compare a
    # negative number against a positive constant and the record would never
    # read as valid. The same rule #AB_MAGIC and #MON_PHASE_MAGIC are under.
    if k["MON_SHOT_MAGIC"] >> 63:
        raise SystemExit("screen shot gate: the capture magic is negative in a "
                         "signed .i")

    # The region has to be ENUMERATED, or `w`, `fill` and `copy` can scribble
    # on a picture without being told - and a corrupted capture is a garbled
    # frame that reads as a display fault.
    if f"Case #MON_REGION_SHOT : ProcedureReturn #MON_SHOT_LO" not in text:
        raise SystemExit("screen shot gate: the capture area is not in "
                         "HwMonRegionLo()")
    if f"Case #MON_REGION_SHOT : ProcedureReturn #MON_SHOT_HI" not in text:
        raise SystemExit("screen shot gate: the capture area is not in "
                         "HwMonRegionHi()")
    count = re.search(r"Procedure\.i HwMonRegions\(\)\s*\n\s*ProcedureReturn (\d+)",
                      text)
    if count is None or int(count.group(1)) <= k["MON_REGION_SHOT"]:
        raise SystemExit(
            "screen shot gate: HwMonRegions() does not reach the capture "
            "area's index, so HitsMonitor() never walks it and the region is "
            "declared but not protected.")
    return notes


def check_abi() -> None:
    """The slot exists, is installed, and reaches the board's own capture."""
    abi = ABI.read_text(encoding="utf-8")
    if "Procedure.i SvcScreenCapture()" not in abi:
        raise SystemExit("screen shot gate: abi.pbi has no SvcScreenCapture")
    if "#SVC_BASE_CONSOLE + 13] = @SvcScreenCapture" not in abi:
        raise SystemExit(
            "screen shot gate: SvcScreenCapture is written but not installed "
            "in the service table, so a payload calling slot 13 gets "
            "#SVC_ENOSYS from SvcUnimplemented and the code is unreachable.")
    if "HwConCapture()" not in abi:
        raise SystemExit("screen shot gate: the slot does not go through the "
                         "HwCon seam")
    hwcon = HWCON.read_text(encoding="utf-8")
    if "Procedure.i HwConCapture()" not in hwcon:
        raise SystemExit("screen shot gate: the Pi 4 has no HwConCapture")
    if "ScrShotNow(#MON_SHOT_WHO_PAYLOAD" not in hwcon:
        raise SystemExit(
            "screen shot gate: HwConCapture does not take the same capture the "
            "operator and the payload return path take, so there would be two "
            "shapes of capture in one area.")
    minor = re.search(r"#SVC_ABI_MINOR\s*=\s*(\d+)",
                      (ROOT / "Anvil" / "Hal" / "abi_version.pbi").read_text(
                          encoding="utf-8"))
    if minor is None or int(minor.group(1)) < 2:
        raise SystemExit(
            "screen shot gate: a console slot was filled and #SVC_ABI_MINOR "
            "did not rise, so a payload cannot tell whether this monitor can "
            "keep a picture for it.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"))
    args = parser.parse_args()
    compiler = required_path(args.compiler, "PMF_COMPILER")
    a64 = load_interpreter(required_path(args.interp, "PMF_A64_INTERP"))

    notes = check_map()
    check_abi()

    bodies = product_bodies()
    with tempfile.TemporaryDirectory(prefix="anvil-screen-shot-") as td:
        work = Path(td)
        result, steps = execute(
            a64, build(compiler, work, fixture(bodies), "screen_shot_gate"))
        if result:
            print(f"screen_shot_emitted_check: FAIL assertion {result} after "
                  f"{steps:,} A64 instructions")
            return 1
        killed = []
        for i, entry in enumerate(MUTATIONS, 1):
            label, rest = entry[0], entry[1:]
            edits = list(zip(rest[0::2], rest[1::2]))
            mutant = mutate(bodies, edits, label)
            code, _ = execute(
                a64, build(compiler, work, fixture(mutant), f"shot_mutant_{i}"))
            if code == 0:
                print(f"screen_shot_emitted_check: FAIL the {label!r} mutant "
                      "survived - the gate does not actually check that.")
                return 1
            killed.append(f"{label}:{code}")

    print(f"screen_shot_emitted_check: PASS - the shipped capture, the shipped "
          f"rotation map and the shipped payload-return path over a modelled "
          f"turned panel on both tiers, {steps:,} A64 instructions; "
          f"{len(MUTATIONS)} mutants rejected")
    for entry in killed:
        print("  rejected: " + entry)
    for note in notes:
        print("  NOTE: " + note)
    print("  the capture area's placement, size and protection are checked "
          "against")
    print("  RaspberryPi4/Board/memmap.pi4's own constants, and the ABI slot "
          "against")
    print("  Anvil/Hal/abi.pbi and the Pi 4's HwCon seam.")
    print("  Emitted execution over a modelled panel. Only the board can prove "
          "that")
    print("  the bytes copied are the bytes the glass was showing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

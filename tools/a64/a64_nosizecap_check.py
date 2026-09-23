#!/usr/bin/env python3
r"""Executable gate: the monitor has no size cap, and the map moves with it.

    python tools/a64/a64_nosizecap_check.py --compiler <PureMetalForge.exe>

WHAT THE RULING WAS

2026-09-08: "the bootloader is a kernel and can be as big as it wants."
Until that day Anvil reserved a fixed two-megabyte window on the Pi 4 -
#MON_LO $00200000 to #MON_HI $003FFFFF - with the autoboot record in the
last 256 bytes of it, the low payload window starting at the constant
$00400000, and four host tools each carrying 0x400000 as a staging
address of their own.  That is a size cap: the program may not grow past
it, and everything downstream is positioned around the constant rather
than around the program.  It was 16,872 bytes from binding when the
ruling was made.

WHAT REPLACED IT

The image carries the address of its own end.  The A64 emitter writes
__image_start__ / __image_end__ on every build - the same thing a Linux
kernel calls `_end` - and RaspberryPi4/Board/memmap.pi4 reads them with an
adrp/add pair.  The monitor reserves the megabyte its image ends in, the
low payload window starts at the next megabyte above the image, and the
staging address is that window's base.  All three are arithmetic on one
measurement.

WHY THIS GATE EXISTS SEPARATELY FROM a64_anvil_check.py

That gate builds the monitor AS IT SHIPS and checks that its map is the
map this tree computes.  On the day of the ruling the shipped monitor was
2,083,268 bytes and its arithmetic landed on $00200000..$003FFFFF and
$00400000 - the two numbers that used to be constants - so every number
in that gate was consistent with a monitor that still had a ceiling, and
it would have stayed green if the ceiling came back.

The only way to tell a computed map from a lucky constant is to build a
monitor that CANNOT fit under the old ceiling and watch the map move.
That is what this does.  It also builds the monitor as it ships, and
requires the padded monitor's staging address to be ABOVE that one's: a
map that did not move when a megabyte was added is a constant, whatever
number it happens to print.

THE PADDING IS A REAL TABLE AND NOT A BLOCK OF ZEROS

A megabyte of zeros would prove nothing about the toolchain: an emitter
could special-case it, an assembler could run-length it, and a
compressing anything on the path would hide it.  The pad is 131,072
64-bit values from a linear congruential generator with a fixed seed -
every byte different, deterministic run to run, and emitted through the
ordinary DataSection path.  It is exactly the shape of the thing that
would really push this program over a megabyte: a table somebody had to
embed.

WHAT IS COVERED

  1. a monitor larger than the old ceiling BUILDS at all
  2. `map`, executed on that image, reports the monitor's extent as the
     megabyte the image ends in - and NOT $003FFFFF
  3. the byte count it prints is the length of the file on disk, which is
     the measurement everything else rests on
  4. the low payload window and the staging address moved with it, are
     NOT $00400000, and are above the staging address of the monitor as
     it ships
  5. $00400000 - the address every tool in this tree used to stage at -
     is now INSIDE the monitor and is refused, and the refusal from
     `net recv` prints the new window
  6. the new staging address is accepted, in both the window test and the
     monitor test
  7. the autoboot record is untouched: it is below the load address, the
     image cannot reach it however large it is, and arming, reading back
     and clearing it all still work ON THE BIG IMAGE
  8. a payload placed at the new staging address is ENTERED by the same
     RunAt() that `run` and the autoboot use, and comes back with its own
     value - so `receive` + `run` really does land above a monitor of
     this size.  The payload it enters is the one built
     `--load-addr 0x400000`, which is how the diagnostics in this tree
     are built, and it reaches a Global, a Dim array and a DataSection
     label before it answers, so its data was found at the address it
     was STAGED at and not the one it was built for
  9. that build line does not put one byte into the image: the same
     payload built for $400000 and for $1000000 is the same file, whole.
     This is the answer to "then what happens to the diagnostics whose
     recipes name $400000, now that the monitor has grown over it" -
     nothing.  Their code and data are reached PC-relative, they do not
     need rebuilding, and what has to move is where they are STAGED,
     which is the thing the board now says and the tools now ask.  (A
     payload built with an explicit --bss-addr IS pinned: its variables
     are then at an absolute address and the adrp distance to them
     changes with the load address.  The payload here leaves --bss-addr
     off, as the diagnostics do.)

RUNAT IS ENTERED THE WAY tools/payload_return_emitted_check.py ENTERS IT

RunAt today reclaims secondary cores, quiesces the Ethernet bus master,
arms the deadman, turns the caches off and writes a run record before it
jumps, and undoes all of that after.  Those are hardware seams, and that
gate is where their order is proved.  Here they are answered the way it
answers them - no secondary cores owned, the Ethernet was down, the
reclaim readback succeeds, the watchdog and cache calls do nothing - so
the thing under test is only what this gate is about: the real RunAt and
the real CallAddr (with the real ExceptionInstall, on the system-register
model) handing control to a real payload at the new staging address and
getting it back.

IT WAS SEEN TO BITE, AND HERE IS WHAT THAT LOOKED LIKE

A gate nobody has watched refuse is a gate nobody has any reason to
believe.  One line of RaspberryPi4/Board/memmap.pi4 was put back to what
it used to be -

    Case 0 : ProcedureReturn $00400000        instead of
    Case 0 : ProcedureReturn MonGrainUp(#MON_LO + HwMonBytes())

- which is the cap returning in the smallest possible way: one constant,
in one procedure, on a monitor whose extent is still measured correctly
everywhere else.  MUTATION RECORD, at the bottom of this docstring, says
what went red.  The mutation is not automated here: it is one line, it is
quoted above, and an automated mutator that rewrites a board file is a
bigger risk to the tree than the thing it checks.

WHAT IS NOT COVERED

  * silicon.  This is the project's own A64 interpreter
    (tools/a64/a64_interp.py), one flat memory, no bus and no devices.
    It answers "does the generated code compute the right address" and
    says nothing about a board.
  * whether a 3 MB kernel8.img boots on the real firmware.  The firmware
    loads the whole file at kernel_address and branches; nothing in the
    boot path has a size in it (see THE MEMORY MAP in
    RaspberryPi4/Board/memmap.pi4).  That is reasoning, not a
    measurement, and it is written here as reasoning.

EVERY RUN BUILDS THE MONITOR TWICE, and both builds are counted by
tools/build_count.py: once as it ships and once padded.  The two payload
builds are not board files and have no build number.

NOTHING IS TRANSCRIBED.  #MON_LO, #MON_GRAIN, #AB_BASE and #AB_BYTES are
read out of memmap.pi4; the expected map is computed from those and the
length of the image on disk; the numbers the monitor prints are read back
off its own UART.  The one exception is deliberate: 0x00200000 and
0x00400000 appear below as THE OLD CONSTANTS, written out so the gate can
assert the map is no longer them.

MUTATION RECORD

2026-09-16, against Anvil main, with the one-line mutant above put into a
copy of memmap.pi4 that only the padded board copy included: 11 of 40
cases went red, and they were the right eleven.  The window and the
staging address stopped moving and fell BELOW the shipped monitor's
$00500000; `map` printed 00400000 on a 4,035,904-byte image and did not
print 00600000 on its staging line; HitsMonitor refused the address the
board was telling every tool to use while InPayload accepted $00400000;
the `net recv` refusal did not name the real window; and RunAt refused to
enter the payload at all ("inside the monitor itself"), so gGoRc kept 0
and no return line was printed.  The unmutated tree was 40 of 40 on the
same day, with a 4,021,552-byte padded monitor staging at $00600000.

Separately, one byte of the staged payload's own table was changed in
memory (7 became 9): case 8 went red on both of its return checks (and case 9, which
compares that same file), which
is what shows the payload really runs and really reads its data at the
staging address rather than the gate being handed a value.
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
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools"))

from a64_interp import A64                                       # noqa: E402
import build_count                                               # noqa: E402

# THE HELPERS COME FROM a64_anvil_check RATHER THAN BEING COPIED.
# read_sym(), make_cpu_for(), call3(), peek64() and const() are the
# machinery for running a piece of this monitor under the interpreter, and
# a second copy of them would be a second thing to keep in step with the
# image.  Importing runs that module's top level, which only defines
# things; its main() is behind an if-name-main guard.
_spec = importlib.util.spec_from_file_location(
    "a64_anvil_check", HERE / "a64_anvil_check.py")
_ac = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_ac)

BY = "tools/a64/a64_nosizecap_check.py"
BOARD = ROOT / "RaspberryPi4" / "Board" / "board.pi4"
MEMMAP = ROOT / "RaspberryPi4" / "Board" / "memmap.pi4"
ANCHOR = 'XIncludeFile "Anvil/Core/help.pbi"'

# THE OLD CONSTANTS, written out on purpose - see NOTHING IS TRANSCRIBED.
# The gate's job is to prove the map is no longer these.
OLD_MON_HI = 0x003FFFFF
OLD_PAY0_LO = 0x00400000
OLD_CEILING_BYTES = 0x003FFF00 - 0x00200000     # 2,096,896
MOVED_LOAD = 0x01000000                         # case 9's second address

# The pad: 131,072 doublewords = 1 MiB, in 2,048 Data lines.
#
# THE LINE LENGTH IS CHOSEN, not incidental.  The emitter accumulates the
# DataSection one append per Data line, so ten thousand short lines cost
# minutes where two thousand long ones cost seconds.  Sixty-four values a
# line is a readable row and a build that finishes.
PAD_ROWS = 2048
PAD_PER_ROW = 64
PAD_SEED = 0x243F6A8885A308D3                   # pi, as everybody's is
LCG_MUL = 6364136223846793005
LCG_ADD = 1442695040888963407
MASK63 = 0x7FFFFFFFFFFFFFFF
MASK64 = 0xFFFFFFFFFFFFFFFF

# The payload for cases 8 and 9.  --entry-returns, so RunAt's blr comes
# back.  It answers its magic only if a Global, a Dim array and a
# DataSection label were all reached where the image actually sits.
PAYLOAD_MAGIC = 0x5CA1AB1E
PAYLOAD_SOURCE = """; Generated by tools/a64/a64_nosizecap_check.py - do not edit.
;
; A small honest payload: it returns a value nothing else in the run could
; have produced, and only after reaching its own variables and its own
; table - so a payload whose data was looked for at the address it was
; BUILT for, rather than the one it was staged at, answers 0 instead.
; Built --entry-returns so that RunAt()'s blr comes back to the monitor.
Global nsc_count.i
Global Dim nsc_tab.i(8)

Procedure.i NscTwice(v.i)
  ProcedureReturn v * 2
EndProcedure

Procedure.i Main()
  Define *p
  nsc_count = NscTwice(21)
  nsc_tab(3) = nsc_count
  *p = ?nsc_table
  If PeekI(*p) = 7 And PeekI(*p + 8) = 8 And nsc_tab(3) = 42
    ProcedureReturn $%X
  EndIf
  ProcedureReturn 0
EndProcedure

DataSection
nsc_table:
  Data.i 7, 8
EndDataSection
""" % PAYLOAD_MAGIC
PAYLOAD_FLAGS = ["--stack-addr", "0x3000000", "--entry-returns"]

UART_DR = _ac.UART_DR
UART_FR = _ac.UART_FR
FR_RXFE = _ac.FR_RXFE
PRINT_STEPS = 20_000_000

# RunAt's hardware seams, answered as tools/payload_return_emitted_check.py
# answers them for its "inactive uncached return" route.  name -> x0.
RUNAT_SEAMS = {
    "coreacceptownssecondaries": 0,     # no secondary core is owned
    "coreacceptreclaim": 1,
    "netconsoleflush": 0,
    "touchkeyboardpayloadsuspend": 0,
    "ethpayloadquiesce": 0,             # the Ethernet was down: nothing to resume
    "ethpayloadreclaim": 1,             # the stop readback succeeded
    "ethpayloadresume": 0,
    "safetywatchdogstart": 0,
    "safetywatchdogstop": 0,
    "safetytofirmware": 0,
    "uartdrain": 0,
    "cachedisable": 0,
    "cacheenable": 1,
    "dmachannelreset": 1,
    "displayusedma": 0,
    "shottakearm": 0,
    "netdhcptick": 0,
    "netconsolerearm": 0,
}
RETURN_PC = 0xDEAD7290
VBAR_EL2 = 0xD51CC000
CPTR_EL2 = 0xD51C1140


# =====================================================================
#  BUILD
# =====================================================================
class Build:
    """Where everything this run compiles is written."""

    def __init__(self, compiler: str, src_dir: pathlib.Path,
                 out_dir: pathlib.Path) -> None:
        self.compiler = compiler
        self.src_dir = src_dir
        self.out_dir = out_dir
        self.plain = out_dir / "nosizecap_plain.img"
        self.big = out_dir / "nosizecap_big.img"
        self.pay = out_dir / "nosizecap_payload.img"
        self.moved = out_dir / "nosizecap_payload_moved.img"


def compile_one(b: Build, source: pathlib.Path, image: pathlib.Path,
                extra: list[str], board: bool) -> None:
    """Compile with the one compiler, the way a64_anvil_check does.

    A board file (the shipped board.pi4, or the padded copy - which is
    named board.pi4 so tools/build_count.py knows it for the Pi 4 monitor)
    is counted after it is proven built.  A payload is not a board file.
    """
    image.parent.mkdir(parents=True, exist_ok=True)
    if image.exists():
        image.unlink()
    cmd = [b.compiler, "--compile", source.relative_to(ROOT).as_posix(),
           "-t", "pi4", *extra, "-o", str(image)]
    r = subprocess.run(cmd, cwd=ROOT, text=True,
                       env=dict(os.environ, PMF_ROOT=str(ROOT)),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout or not image.is_file():
        raise SystemExit("The build of %s failed, so nothing below can be "
                         "checked:\n%s\n%s" % (source, " ".join(cmd),
                                               r.stdout[-4000:]))
    if board:
        counted = build_count.record_build(source, "pi4", image, by=BY,
                                           compiler=b.compiler)
        print("[gate] build count: %s" % counted.message, file=sys.stderr)


def make_pad(path: pathlib.Path) -> None:
    v = PAD_SEED & MASK63
    lines = [
        "; Generated by tools/a64/a64_nosizecap_check.py - do not edit.",
        ";",
        "; A megabyte of real table, for the proof that this monitor has no",
        "; size cap. Every value is different and every run produces the same",
        "; file: a block of zeros would prove nothing about a toolchain that",
        "; might special-case one.",
        "DataSection",
        "nosizecap_pad_table:",
    ]
    for _ in range(PAD_ROWS):
        row = []
        for _ in range(PAD_PER_ROW):
            v = (v * LCG_MUL + LCG_ADD) & MASK63
            row.append(str(v))
        lines.append("  Data.i " + ", ".join(row))
    lines.append("EndDataSection")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_big_source(b: Build) -> pathlib.Path:
    """board.pi4 with the pad included, as its own file.

    A COPY RATHER THAN AN EDIT, because the tree must be the same before
    and after this gate runs - and because other work shares it.  The copy
    keeps board.pi4's own LoadAddress / BssAddress / StackAddress lines,
    so the padded monitor is laid out exactly the way the shipped one is;
    the only difference between the two images is the table.
    """
    pad = b.src_dir / "nosizecap_pad.pi4"
    make_pad(pad)
    src = BOARD.read_text(encoding="utf-8", errors="replace")
    if src.count(ANCHOR) != 1:
        raise SystemExit("cannot find the include anchor %r in board.pi4 - it "
                         "is there %d times" % (ANCHOR, src.count(ANCHOR)))
    src = src.replace(ANCHOR, ANCHOR + '\nXIncludeFile "%s"'
                      % pad.relative_to(ROOT).as_posix())
    big = b.src_dir / "board.pi4"
    big.write_text(src, encoding="utf-8", newline="\n")
    return big


def build_all(b: Build) -> None:
    compile_one(b, BOARD, b.plain, [], board=True)
    compile_one(b, make_big_source(b), b.big, [], board=True)
    pay = b.src_dir / "nosizecap_payload.pi4"
    pay.write_text(PAYLOAD_SOURCE, encoding="utf-8", newline="\n")
    # THE PAYLOAD IS BUILT TWICE, AT THE OLD ADDRESS AND AT A NEW ONE - see
    # case 9.  b.pay is the OLD one, built --load-addr 0x400000 the way the
    # diagnostics are, and it is the one case 8 stages above the big
    # monitor and enters.
    compile_one(b, pay, b.pay, ["--load-addr", "0x%X" % OLD_PAY0_LO]
                + PAYLOAD_FLAGS, board=False)
    compile_one(b, pay, b.moved, ["--load-addr", "0x%X" % MOVED_LOAD]
                + PAYLOAD_FLAGS, board=False)


# =====================================================================
#  RUNNING PIECES OF THE IMAGE
# =====================================================================
def edges() -> dict[str, int]:
    text = MEMMAP.read_text(encoding="utf-8", errors="replace")
    return {name: _ac.const(text, name)
            for name in ("MON_LO", "MON_GRAIN", "AB_BASE", "AB_BYTES")}


def monitor_cpu(img: pathlib.Path, load: int) -> A64:
    cpu = _ac.make_cpu_for(img, load)
    cpu.enable_system_registers(el=2, preset={VBAR_EL2: 0x8800,
                                              CPTR_EL2: 0x33FF})
    return cpu


def captured(cpu: A64, entry: int, args: tuple = (),
             hooks: dict | None = None, limit: int = PRINT_STEPS
             ) -> tuple[int, str]:
    """Run one procedure at an ABSOLUTE entry; return x0 and its UART text.

    The flag register is forced to 'receive FIFO empty' first and held
    there, for the reason a64_anvil_check records: it reads 0 out of flat
    memory, 0 means a key is waiting, and the monitor's break check would
    then stop a long print after one line - which looks exactly like a
    pass with less output.  A hook, keyed by absolute address, stands in
    for the procedure there: its value goes in x0 and control returns to
    x30.
    """
    hooks = hooks or {}
    for k, byte in enumerate(FR_RXFE.to_bytes(4, "little")):
        cpu.memory[UART_FR + k] = byte
    out = bytearray()
    real = cpu.store

    def spy(addr: int, value: int, size: int, _r=real, _o=out) -> None:
        if addr == UART_DR:
            _o.append(value & 0xFF)
            return
        if addr == UART_FR:
            return
        _r(addr, value, size)

    cpu.store = spy                                  # type: ignore[method-assign]
    try:
        cpu.x = [0] * 31
        for i, a in enumerate(args):
            cpu.x[i] = a & MASK64
        cpu.x[30] = RETURN_PC
        cpu.sp = _ac.STACK
        cpu.pc = entry
        for _ in range(limit):
            if cpu.pc == RETURN_PC:
                break
            hook = hooks.get(cpu.pc)
            if hook is not None:
                cpu.x[0] = hook & MASK64
                cpu.pc = cpu.x[30]
                continue
            cpu.step()
        else:
            raise SystemExit("a procedure at $%X never returned within %d "
                             "steps; it was last at $%X"
                             % (entry, limit, cpu.pc))
    finally:
        cpu.store = real                             # type: ignore[method-assign]
    return cpu.x[0] & MASK64, out.decode("latin-1")


def stage_of(img: pathlib.Path, load: int) -> int:
    sym = _ac.read_sym(img)
    return _ac.call3(monitor_cpu(img, load), load + sym["hwstageaddr"],
                     0, 0, 0)


# =====================================================================
#  THE CASES
# =====================================================================
def check_all(b: Build) -> int:
    e = edges()
    mon_lo, grain = e["MON_LO"], e["MON_GRAIN"]
    if _ac.load_addr(BOARD) != mon_lo:
        raise SystemExit("board.pi4 is linked at $%X and #MON_LO is $%X"
                         % (_ac.load_addr(BOARD), mon_lo))

    img_bytes = b.big.stat().st_size
    want_mon_hi = ((mon_lo + img_bytes + grain - 1) // grain) * grain - 1
    want_pay_lo = want_mon_hi + 1

    fails: list[str] = []
    cases = 0

    def check(cond: bool, msg: str) -> bool:
        nonlocal cases
        cases += 1
        if not cond:
            fails.append(msg)
        return cond

    sym = _ac.read_sym(b.big)
    cpu = monitor_cpu(b.big, mon_lo)

    def at(name: str) -> int:
        return mon_lo + sym[name]

    def call(name: str, *args: int) -> int:
        a = list(args) + [0, 0, 0]
        return _ac.call3(cpu, at(name), a[0], a[1], a[2])

    # ---- 1. IT IS BIGGER THAN THE OLD CEILING ------------------------
    check(img_bytes > OLD_CEILING_BYTES,
          "the padded monitor is %d bytes, which still fits under the old "
          "%d-byte ceiling. This gate proves nothing unless the image it "
          "builds could not have existed before 2026-09-08 - raise "
          "PAD_ROWS." % (img_bytes, OLD_CEILING_BYTES))

    # ---- 2/3/4. THE MAP MOVED, AND IT MOVED TO THE COMPUTED PLACE ----
    for name in ("cmdmap", "hwmonhi", "hwmonbytes", "hwstageaddr",
                 "hwpaylo", "hitsmonitor", "inpayload", "autoset",
                 "autoentry", "runat", "netrecvplacerefused",
                 "global_ggorc"):
        check(name in sym,
              "the padded monitor has no %s - this gate cannot run without "
              "it" % name)
    if fails:
        return report(cases, fails, img_bytes, mon_lo, want_mon_hi,
                      want_pay_lo, 0)

    got_mon_hi = call("hwmonhi")
    got_bytes = call("hwmonbytes")
    got_stage = call("hwstageaddr")
    got_pay_lo = call("hwpaylo", 0)
    plain_stage = stage_of(b.plain, mon_lo)

    check(got_bytes == img_bytes,
          "the image measures itself as %d bytes and it is %d on disk. That "
          "measurement is __image_end__ minus __image_start__, and every "
          "other number in this map is computed from it."
          % (got_bytes, img_bytes))
    check(got_mon_hi == want_mon_hi,
          "the monitor reserves up to $%08X and the arithmetic says $%08X "
          "for a %d-byte image at $%08X with a $%X grain"
          % (got_mon_hi, want_mon_hi, img_bytes, mon_lo, grain))
    check(got_mon_hi != OLD_MON_HI,
          "the monitor still reserves up to $%08X, which is the CONSTANT "
          "#MON_HI used to be. A %d-byte image reaching past it means the "
          "region did not follow the image - the cap is back."
          % (OLD_MON_HI, img_bytes))
    check(got_pay_lo == want_pay_lo and got_stage == want_pay_lo,
          "the low payload window starts at $%08X and the staging address "
          "is $%08X; both should be $%08X, the megabyte above this image"
          % (got_pay_lo, got_stage, want_pay_lo))
    check(got_stage != OLD_PAY0_LO,
          "the board still stages at $%08X, which is the constant every "
          "tool used to carry - and which is now INSIDE a monitor of this "
          "size" % OLD_PAY0_LO)
    check(got_stage > plain_stage,
          "the padded monitor stages at $%08X and the monitor as it ships "
          "stages at $%08X. A megabyte was added and the staging address "
          "did not move up, so whatever produced it is not following the "
          "image." % (got_stage, plain_stage))

    _, map_text = captured(cpu, at("cmdmap"))
    map_text = map_text.lower()
    check(str(img_bytes) in map_text,
          "map does not print %d, the length of the image on disk. It said: "
          "%r" % (img_bytes, map_text[:600]))
    for value, what in ((mon_lo, "the image base"),
                        (mon_lo + img_bytes - 1, "the image's last byte"),
                        (want_mon_hi, "the top of the reserved region"),
                        (want_pay_lo, "the low payload window base"),
                        (e["AB_BASE"], "the autoboot record")):
        check("%08x" % value in map_text,
              "map does not print %08X (%s). It said: %r"
              % (value, what, map_text[:600]))
    check(re.search(r"stage a file at\s+(0x)?%08x\b" % want_pay_lo,
                    map_text) is not None,
          "map's staging line does not name %08X. It said: %r"
          % (want_pay_lo, map_text[:600]))
    # A WORD-BOUNDARY MATCH: map lists more regions than it did, and an
    # eight-digit address that merely CONTAINS these digits is not this one.
    check(re.search(r"\b%08x\b" % OLD_PAY0_LO, map_text) is None,
          "map still prints %08X. On an image this size that address is "
          "inside the monitor, so a map naming it is describing a computer "
          "this is not. It said: %r" % (OLD_PAY0_LO, map_text[:600]))

    # ---- 5/6. THE OLD STAGING ADDRESS IS NOW REFUSED -----------------
    check(call("hitsmonitor", OLD_PAY0_LO, OLD_PAY0_LO + 0xFFF) != 0,
          "HitsMonitor($%08X) says clear on a %d-byte monitor whose code "
          "runs to $%08X. That address is inside the running program and a "
          "payload written there would overwrite it."
          % (OLD_PAY0_LO, img_bytes, mon_lo + img_bytes - 1))
    check(call("hitsmonitor", got_stage, got_stage + 0xFFF) == 0,
          "HitsMonitor($%08X) REFUSED the board's own staging address. A "
          "guard that refuses the one address the board tells every tool "
          "to use would pass every case above it." % got_stage)
    check(call("inpayload", OLD_PAY0_LO, OLD_PAY0_LO + 0xFFF) == 0,
          "InPayload($%08X) says that range is in a payload window. The "
          "window starts at $%08X on this image." % (OLD_PAY0_LO, want_pay_lo))
    check(call("inpayload", got_stage, got_stage + 0xFFF) == 1,
          "InPayload($%08X) refused the base of the window it just "
          "reported" % got_stage)
    rc, text = captured(cpu, at("netrecvplacerefused"), (OLD_PAY0_LO, 0x1000))
    text = text.lower()
    check(rc == 1 and "%08x" % want_pay_lo in text,
          "net recv aimed at $%08X returned %d, and its refusal should print "
          "the window that IS allowed ($%08X). A refusal whose replacement "
          "address is missing sends somebody to look it up in a file that no "
          "longer has it. It said: %r"
          % (OLD_PAY0_LO, rc, want_pay_lo, text[:600]))

    # ---- 7. THE AUTOBOOT RECORD, ON THE BIG IMAGE --------------------
    ab, ab_bytes = e["AB_BASE"], e["AB_BYTES"]
    check(ab + ab_bytes <= mon_lo,
          "the autoboot record $%08X is not below the load address $%08X. "
          "Above it, an image of this size lands on the record and the "
          "armed payload is silently gone next boot - which is the ceiling "
          "that was removed." % (ab, mon_lo))
    call("autoset", got_stage)
    check(call("autoentry") == got_stage,
          "arming the autoboot record with $%08X on a %d-byte monitor and "
          "reading it back did not return it. The record is below the load "
          "address and no image size can reach it - if this fails the "
          "record moved back inside something that grows."
          % (got_stage, img_bytes))
    check(_ac.peek64(cpu, ab) != 0,
          "the magic word at $%08X is zero after arming. AutoSet writes the "
          "magic LAST so a record is never briefly valid with a half-written "
          "address, and a zero there means nothing was written at all." % ab)
    call("autoset", 0)
    check(call("autoentry") == 0,
          "clearing the autoboot record left it armed")

    # ---- 8. A PAYLOAD ABOVE THE MONITOR IS ENTERED AND COMES BACK ----
    # AND IT IS THE ONE BUILT FOR $400000, which is what makes this the
    # answer to "then what happens to the diagnostics" rather than a
    # demonstration with a freshly built payload.  See case 9.
    for i, byte in enumerate(b.pay.read_bytes()):
        cpu.memory[got_stage + i] = byte
    _ac.poke64(cpu, sym["global_ggorc"], 0)
    hooks = {at(n): v for n, v in RUNAT_SEAMS.items() if n in sym}
    ran, text = captured(cpu, at("runat"), (got_stage,), hooks)
    check("%08x" % got_stage in text.lower(),
          "RunAt did not say it was starting the payload at $%08X. It said: "
          "%r" % (got_stage, text[:600]))
    # THE PAYLOAD'S x0 IS READ OUT OF gGoRc, NOT OFF THE PROCESSOR.  RunAt
    # returns 1 for "it ran"; the value the payload handed back crosses in
    # a BSS global, because CallAddr swaps stacks around the blr and
    # nothing on the register file survives that by contract.
    got_rc = _ac.peek64(cpu, sym["global_ggorc"])
    check(got_rc == PAYLOAD_MAGIC,
          "the payload at $%08X did not come back with its own value: gGoRc "
          "holds $%X and the payload returns $%X once it has found its own "
          "data. `receive` and `run` are only useful if a payload staged "
          "above a monitor of this size is entered and runs correctly "
          "there. RunAt printed: %r"
          % (got_stage, got_rc, PAYLOAD_MAGIC, text[:600]))
    check(("%x" % PAYLOAD_MAGIC) in text.lower(),
          "RunAt did not print the value the payload returned. That line is "
          "the only thing a console shows of a payload that comes back. It "
          "said: %r" % text[:600])

    # ---- 9. --load-addr DOES NOT CHANGE ONE BYTE OF A PAYLOAD --------
    # Diagnostics in this tree carry `--load-addr 0x400000` in the recipe
    # in their header, and a monitor can now grow past $400000, so that
    # address can be inside it.  If the address in the build line were
    # baked into the image, every one of those files would need
    # rebuilding at a new address the day the monitor crossed a megabyte.
    #
    # It is not baked in: code reaches its own code and data with PC-
    # relative branches and adrp/add pairs, and BSS is placed relative to
    # the code.  So the two builds - one at $400000, one at $1000000 - are
    # the SAME FILE, and case 8 has just entered the $400000 one at the
    # new staging address and had its own value back.
    #
    # THE COMPARISON IS THE WHOLE IMAGE, byte for byte, and not a spot
    # check on the entry point: one absolute address anywhere in it - a
    # table of pointers, a literal pool - would make this false in a way a
    # spot check would miss.
    old_bytes = b.pay.read_bytes()
    moved_bytes = b.moved.read_bytes()
    check(old_bytes == moved_bytes,
          "the same payload built --load-addr 0x%X and --load-addr 0x%X is "
          "not the same file: %d bytes against %d, first difference at "
          "offset %s. If the load address is in the image then every "
          "diagnostic in this tree is pinned to the address it was built "
          "for, and the monitor may not grow past it."
          % (OLD_PAY0_LO, MOVED_LOAD, len(old_bytes), len(moved_bytes),
             next((str(i) for i, (x, y) in
                   enumerate(zip(old_bytes, moved_bytes)) if x != y),
                  "nowhere - the lengths differ")))

    return report(cases, fails, img_bytes, mon_lo, want_mon_hi, want_pay_lo,
                  plain_stage)


def report(cases: int, fails: list[str], img_bytes: int, mon_lo: int,
           mon_hi: int, pay_lo: int, plain_stage: int) -> int:
    if fails:
        for f in fails:
            print("  FAIL %s" % f)
        print()
        print("a64_nosizecap_check: FAIL - %d of %d cases" % (len(fails), cases))
        return 1
    print("a64_nosizecap_check: PASS - %d cases" % cases)
    print("  a %d-byte monitor was built - %.2f times the old 2,096,896-byte"
          % (img_bytes, img_bytes / float(OLD_CEILING_BYTES)))
    print("  ceiling - and its map followed it: the monitor reserves")
    print("  $%08X..$%08X, and the low payload window and the staging"
          % (mon_lo, mon_hi))
    print("  address moved to $%08X, above the $%08X the monitor as it ships"
          % (pay_lo, plain_stage))
    print("  stages at. The autoboot record stayed at its fixed page below the")
    print("  load address and still armed, and a payload BUILT FOR $00400000")
    print("  was staged at the new address, entered by RunAt, found its own")
    print("  data and came back. That payload is byte for byte the same file")
    print("  when it is built for $%08X instead." % MOVED_LOAD)
    return 0


# =====================================================================
#  MAIN
# =====================================================================
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--work", default=None,
                    help="directory for the images (default: a temporary "
                         "directory removed afterwards)")
    args = ap.parse_args()
    if not args.compiler:
        print("a64_nosizecap_check: no compiler was named. Pass --compiler "
              "with the path of PureMetalForge.exe, or set PMF_COMPILER.")
        return 2
    compiler = str(pathlib.Path(args.compiler).resolve())
    print("[gate] tree under test: %s" % ROOT, file=sys.stderr)
    # The generated SOURCES live under the tree's _work (ignored by git),
    # because a board file's includes are named from the tree root; the
    # images go wherever --work says.
    (ROOT / "_work").mkdir(exist_ok=True)
    src_dir = pathlib.Path(tempfile.mkdtemp(prefix="nosizecap-",
                                            dir=ROOT / "_work"))
    try:
        with tempfile.TemporaryDirectory(prefix="nosizecap-img-") as tmp:
            out_dir = pathlib.Path(args.work).resolve() if args.work else \
                pathlib.Path(tmp)
            b = Build(compiler, src_dir, out_dir)
            build_all(b)
            return check_all(b)
    finally:
        shutil.rmtree(src_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

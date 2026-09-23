#!/usr/bin/env python3
"""Execute `measure <command>`'s own two halves against a fake clock.

WHY THIS NEEDS A GATE AT ALL. `measure` exists because host-timed figures
include the console's round trip, and that round trip is neither small
nor constant between client programs - one client on this bench has a
floor of about four hundred milliseconds per command and another about
one, so the same load reads as 0.078 s or 0.502 s depending on who held
the stopwatch. A stopwatch that is itself wrong is worse than no
stopwatch, because every number taken with it looks like a measurement.

So the two production procedures - TimeArm and TimeReport, lifted
verbatim out of Anvil/Core/parse.pbi with the word matcher and the two
line walkers they use - are compiled against a tick source this file
controls and run in tools/a64/a64_interp.py. The clock advances by a
known amount between the arm and the report - and only then - so the
microseconds that come out are arithmetic this file predicts exactly.

THE MUTANT THAT MATTERS is the one that times only the parse: it stamps
the clock in TimeReport instead of in TimeArm, so every command measures
as instantaneous. That is the failure that would never be noticed,
because a fast answer is the answer everybody wants.

  PMF_COMPILER=<PureMetalForge.exe> python tools/measure_command_check.py
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import tcp_multiif_emitted_check as emitted
from pmf_compiler import resolve_compiler

ROOT = Path(__file__).resolve().parents[1]
PARSE = ROOT / "Anvil" / "Core" / "parse.pbi"
LOCAL_INTERP = ROOT / "tools" / "a64" / "a64_interp.py"

BODIES = ("WordIs", "SkipSpace", "SkipWord", "TimeArm", "TimeReport")


def procedure(source: str, name: str) -> str:
    starts = (f"Procedure {name}(", f"Procedure.i {name}(")
    lines = source.splitlines()
    first = next((i for i, line in enumerate(lines) if line.startswith(starts)), None)
    if first is None:
        raise SystemExit(f"measure gate: {name} is not in {PARSE.name} any more")
    last = next((i for i in range(first, len(lines)) if lines[i].rstrip() == "EndProcedure"), None)
    if last is None:
        raise SystemExit(f"measure gate: {name} has no end")
    return "\n".join(lines[first:last + 1])


PRELUDE = r'''
; ---- the line, and the two cursors over it ---------------------------
Global Dim gLine.a[256]
Global gPos.i = 0
Global gWordAt.i = 0
Global gWordLen.i = 0

; ---- the clock this gate controls ------------------------------------
; READING IT DOES NOT ADVANCE IT. The first version of this fake added a
; step on every read, and that made the gate blind to the mutant that
; matters: stamping the clock inside the report instead of at the arm
; still produced one step of difference, so "times only the parse" looked
; exactly like a correct measurement. Time passes here only when the
; fixture says a command ran.
Global gateTick.i = 0
Global gateHz.i = 54000000

Procedure.i Ticks()
  ProcedureReturn gateTick
EndProcedure

; The command runs. This is the only thing in the fixture that moves time.
Procedure GateAdvance(n.i)
  gateTick = gateTick + n
EndProcedure

Procedure.i TickHz()
  ProcedureReturn gateHz
EndProcedure

; ---- what the two procedures print, captured instead of sent ---------
; The TEXT matters as much as the number: a refusal that prints nothing
; is a refusal nobody sees, and this is how the gate proves one happened.
Global gateOut.i = 0
Global gateLines.i = 0
Global Dim gateText.a[1024]

Procedure GatePut(c.i)
  If gateOut < 1023
    gateText[gateOut] = c
    gateOut = gateOut + 1
  EndIf
EndProcedure

; Print() and PrintN() are the compiler's own; what they reach is
; str_print_at and PrintNl, and those are what a fixture replaces.
Procedure str_print_at(v.i)
  Define i.i
  i = 0
  While PeekA(v + i) <> 0
    GatePut(PeekA(v + i))
    i = i + 1
  Wend
EndProcedure

Procedure UartWriteStr(v.i)
  str_print_at(v)
EndProcedure

Procedure PrintNl()
  GatePut(10)
  gateLines = gateLines + 1
EndProcedure

Procedure PrintDec(v.i)
  Define d.i
  Define n.i
  Define i.i
  Define buf.i
  If v = 0
    GatePut(48)
    ProcedureReturn
  EndIf
  If v < 0
    GatePut(45)
    v = -v
  EndIf
  n = 0
  d = 1
  While d <= v / 10
    d = d * 10
    n = n + 1
  Wend
  While d > 0
    GatePut(48 + ((v / d) % 10))
    d = d / 10
  Wend
EndProcedure

Procedure GateReset()
  Define i.i
  gateOut = 0
  gateLines = 0
  gateTick = 0
  i = 0
  While i < 1024
    gateText[i] = 0
    i = i + 1
  Wend
EndProcedure

; Put a line in and read the first word of it, exactly as the command
; loop does before it calls TimeArm.
Procedure GateLine(*s)
  Define i.i
  i = 0
  While PeekA(*s + i) <> 0 And i < 255
    gLine[i] = PeekA(*s + i)
    i = i + 1
  Wend
  gLine[i] = 0
  gPos = 0
  SkipSpace()
  gWordAt = gPos
  SkipWord()
  gWordLen = gPos - gWordAt
EndProcedure

; Is `*needle` somewhere in what was printed?
Procedure.i GateSaid(*needle)
  Define i.i
  Define k.i
  i = 0
  While i < gateOut
    k = 0
    While PeekA(*needle + k) <> 0 And gateText[i + k] = PeekA(*needle + k)
      k = k + 1
    Wend
    If PeekA(*needle + k) = 0
      ProcedureReturn 1
    EndIf
    i = i + 1
  Wend
  ProcedureReturn 0
EndProcedure
'''

MAIN = r'''
Procedure.i Main()
  ; ---- 1. AN ORDINARY COMMAND IS LEFT ALONE. Nothing armed, nothing
  ;         printed, and the command word untouched.
  GateReset()
  GateLine("version")
  If TimeArm() <> 0 : ProcedureReturn 1 : EndIf
  If gTimeArmed <> 0 : ProcedureReturn 2 : EndIf
  TimeReport()
  If gateOut <> 0 : ProcedureReturn 3 : EndIf
  If WordIs("version") = 0 : ProcedureReturn 4 : EndIf

  ; ---- 2. `measure version` ARMS AND MOVES THE WORD. The command that
  ;         runs must be `version` and not `measure`.
  GateReset()
  GateLine("measure version")
  If TimeArm() <> 1 : ProcedureReturn 10 : EndIf
  If gTimeArmed <> 1 : ProcedureReturn 11 : EndIf
  If WordIs("version") = 0 : ProcedureReturn 12 : EndIf
  If gateOut <> 0 : ProcedureReturn 13 : EndIf

  ; ---- 3. THE NUMBER IS THE CLOCK'S, AND IT IS THE RIGHT ONE. The arm
  ;         reads the clock once and the report reads it once, so a step
  ;         of 54,000,000 ticks is one second - 1,000,000 microseconds.
  GateReset()
  GateLine("measure version")
  If TimeArm() <> 1 : ProcedureReturn 20 : EndIf
  GateAdvance(54000000)
  TimeReport()
  If GateSaid("measure: 1000.000 ms") = 0 : ProcedureReturn 21 : EndIf
  If GateSaid("1000000 us") = 0 : ProcedureReturn 22 : EndIf
  ; And it is disarmed afterwards: a second report prints nothing.
  GateReset()
  GateAdvance(54000000)
  TimeReport()
  If gateOut <> 0 : ProcedureReturn 23 : EndIf

  ; ---- 4. THE FRACTION KEEPS ITS LEADING ZEROS. 54,000 ticks is one
  ;         millisecond; 54 ticks is one microsecond. 1.007 ms must not
  ;         print as 1.7, which is the classic way a timing report lies
  ;         by a factor of a hundred.
  GateReset()
  GateLine("measure version")
  TimeArm()
  GateAdvance(54378)
  TimeReport()
  If GateSaid("measure: 1.007 ms") = 0 : ProcedureReturn 30 : EndIf

  ; ---- 5. A BARE `measure` RUNS NOTHING AND SAYS SO.
  GateReset()
  GateLine("measure")
  If TimeArm() <> 2 : ProcedureReturn 40 : EndIf
  If gTimeArmed <> 0 : ProcedureReturn 41 : EndIf
  If GateSaid("needs a command after it") = 0 : ProcedureReturn 42 : EndIf

  ; ---- 6. NESTING IS REFUSED, and refused LOUDLY - not flattened into
  ;         one silent measurement of the inner command.
  GateReset()
  GateLine("measure measure version")
  If TimeArm() <> 2 : ProcedureReturn 50 : EndIf
  If gTimeArmed <> 0 : ProcedureReturn 51 : EndIf
  If GateSaid("cannot measure itself") = 0 : ProcedureReturn 52 : EndIf

  ; ---- 7. A TICK SOURCE THAT CANNOT BE DIVIDED IS SAID TO BE, not
  ;         reported as an instant command - which is the one wrong
  ;         answer that looks like a good result.
  GateReset()
  gateHz = 0
  GateLine("measure version")
  TimeArm()
  GateAdvance(54000)
  TimeReport()
  gateHz = 54000000
  If GateSaid("did not answer") = 0 : ProcedureReturn 60 : EndIf
  If GateSaid("measure: 0.000") <> 0 : ProcedureReturn 61 : EndIf
  ProcedureReturn 0
EndProcedure
'''

MUTANTS = (
    # The one that matters. Stamping the clock in the report means the
    # measured interval is the report's own arithmetic - zero.
    ("the clock is stamped at the report, so only the parse is timed",
     "  gTimeArmed = 0\n  d = Ticks() - gTimeAt",
     "  gTimeArmed = 0\n  gTimeAt = Ticks()\n  d = Ticks() - gTimeAt"),
    ("nesting is flattened instead of refused",
     '  If WordIs("measure") <> 0\n    PrintN("!! measure cannot measure itself',
     '  If WordIs("measure") <> 0 And 1 = 0\n    PrintN("!! measure cannot measure itself'),
    ("a bare measure falls through and runs whatever follows",
     "    ProcedureReturn 2\n  EndIf\n  gWordAt = gPos",
     "    ProcedureReturn 1\n  EndIf\n  gWordAt = gPos"),
    ("the fraction loses its leading zeros",
     "  If (us % 1000) < 100\n    Print(\"0\")\n  EndIf",
     "  If (us % 1000) < 100 And 1 = 0\n    Print(\"0\")\n  EndIf"),
    ("a report is printed when nothing was armed",
     "  If gTimeArmed = 0\n    ProcedureReturn\n  EndIf",
     "  If gTimeArmed = 0 And 1 = 0\n    ProcedureReturn\n  EndIf"),
)


def build(compiler: Path, work: Path, source: Path, stem: str) -> Path:
    staged = work / compiler.name
    if not staged.exists():
        shutil.copy2(compiler, staged)
    if (ROOT / "Boards").is_dir():
        shutil.copytree(ROOT / "Boards", work / "Boards", dirs_exist_ok=True)
    image = work / f"{stem}.img"
    command = [str(staged), "--compile", str(source), "-t", "pi4",
               "--load-addr", hex(emitted.LOAD), "--stack-addr", hex(emitted.STACK),
               "--entry-returns", "-o", str(image), "-s"]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    run = subprocess.run(command, cwd=ROOT, env=env, text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if run.returncode or not image.is_file() or "COMPILER ERROR" in run.stdout:
        raise SystemExit("measure gate: compile failed\n" + run.stdout)
    return image


def program(source: str) -> str:
    globals_ = "Global gTimeArmed.i = 0\nGlobal gTimeAt.i = 0\n"
    bodies = "\n\n".join(procedure(source, name) for name in BODIES)
    return "EnableExplicit\n" + PRELUDE + "\n" + globals_ + "\n" + bodies + "\n" + MAIN


def run(a64, compiler: Path, work: Path, text: str, stem: str):
    src = work / f"{stem}.pi4"
    src.write_text(text, encoding="utf-8", newline="\n")
    return emitted.execute(a64, build(compiler, work, src, stem))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP") or str(LOCAL_INTERP))
    args = parser.parse_args()
    compiler = Path(resolve_compiler(args.compiler))
    interp = emitted.required_path(args.interp, "PMF_A64_INTERP")
    a64 = emitted.load_interpreter(interp)
    emitted.STEP_LIMIT = 20_000_000

    source = PARSE.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="anvil-measure-") as temporary:
        work = Path(temporary)
        result, steps = run(a64, compiler, work, program(source), "measure_gate")
        if result:
            print(f"measure_command_check: FAIL assertion {result} after {steps:,} instructions")
            return 1
        caught = 0
        for index, (label, old, new) in enumerate(MUTANTS):
            if source.count(old) != 1:
                print(f"measure_command_check: FAIL the mutant anchor for '{label}' "
                      f"appears {source.count(old)} times - the gate is out of date, "
                      "which is not the same as the code being right")
                return 1
            bad, _ = run(a64, compiler, work, program(source.replace(old, new, 1)),
                         f"mutant{index}")
            if bad == 0:
                print(f"measure_command_check: FAIL the mutant '{label}' was not caught")
                return 1
            caught += 1
    print(f"measure_command_check: PASS - seven cases including a refused bare "
          f"prefix, a refused nesting and an unusable tick source, in "
          f"{steps:,} emitted instructions; {caught} mutants rejected")
    return 0


if __name__ == "__main__":
    sys.exit(main())

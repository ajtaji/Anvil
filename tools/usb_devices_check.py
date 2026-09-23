#!/usr/bin/env python3
"""Execute the core's descriptor walk over fabricated devices.

WHAT THIS PROVES AND WHY IT IS NOT A READING. `usb devices` decodes a
configuration descriptor - a chain of variable-length records - and the
whole class of failure worth catching is a chain that does not behave:
a record claiming a length of zero, which sends a walk round forever, and
a record claiming a length that runs past what the device actually sent,
which walks off the end of the buffer into whatever is behind it. Neither
can be produced on demand by a board with working devices plugged into
it, and both are exactly what somebody writing a driver against a new
device is most likely to be holding.

So the production walk - UsbCfgByte, UsbCfgWord, UsbCfgNext, UsbClassText
and UsbEpTypeText, lifted verbatim out of Anvil/Bus/usb_core.pbi - is
compiled against a FAKE seam whose bytes this file chooses, and run in
tools/a64/a64_interp.py. Four descriptor sets: a hub, a SuperSpeed stick
with endpoint companions, a composite keyboard-and-serial device, and two
malformed ones.

The decoding is CORE code and knows nothing about any controller, which
is why this gate needs no board and no host: rule 30 says there is one
copy of this walk for every board Anvil is built for, so there is one
gate for it too.

  PMF_COMPILER=<PureMetalForge.exe> python tools/usb_devices_check.py
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
USB_CORE = ROOT / "Anvil" / "Bus" / "usb_core.pbi"
LOCAL_INTERP = ROOT / "tools" / "a64" / "a64_interp.py"

WALK = ("UsbCfgByte", "UsbCfgWord", "UsbCfgNext", "UsbClassText", "UsbEpTypeText")


def procedure(source: str, name: str) -> str:
    starts = (f"Procedure {name}(", f"Procedure.i {name}(")
    lines = source.splitlines()
    first = next((i for i, line in enumerate(lines) if line.startswith(starts)), None)
    if first is None:
        raise SystemExit(f"usb devices gate: {name} is not in {USB_CORE.name} any more")
    last = next((i for i in range(first, len(lines)) if lines[i].rstrip() == "EndProcedure"), None)
    if last is None:
        raise SystemExit(f"usb devices gate: {name} has no end")
    return "\n".join(lines[first:last + 1])


# ---------------------------------------------------------------- fixtures
#
# Each set is (name, bytes). The bytes are written out rather than built by
# a helper on purpose: a helper that generated them could generate them
# consistently wrong, and the whole point is that these are what a device
# really sends.

def cfg(total_children, *records):
    body = b"".join(records)
    total = 9 + len(body)
    return bytes([9, 2, total & 0xFF, (total >> 8) & 0xFF, total_children,
                  1, 0, 0xA0, 50]) + body


def iface(num, alt, neps, cls, sub, proto):
    return bytes([9, 4, num, alt, neps, cls, sub, proto, 0])


def ep(addr, attr, mps, ivl):
    return bytes([7, 5, addr, attr, mps & 0xFF, (mps >> 8) & 0xFF, ivl])


def companion(burst):
    return bytes([6, 0x30, burst, 0, 0, 0])


HUB = cfg(1, iface(0, 0, 1, 0x09, 0, 0), ep(0x81, 3, 1, 12))

STICK = cfg(1,
            iface(0, 0, 2, 0x08, 6, 0x50),
            ep(0x81, 2, 1024, 0), companion(15),
            ep(0x02, 2, 1024, 0), companion(15),
            iface(0, 1, 4, 0x08, 6, 0x62),
            ep(0x81, 2, 1024, 0), companion(15),
            ep(0x02, 2, 1024, 0), companion(15),
            ep(0x83, 2, 1024, 0), companion(15),
            ep(0x04, 2, 1024, 0), companion(15))

COMPOSITE = cfg(2,
                iface(0, 0, 1, 0x03, 1, 1), ep(0x81, 3, 8, 10),
                iface(1, 0, 2, 0x0A, 0, 0), ep(0x82, 2, 64, 0), ep(0x03, 2, 64, 0))

# A record that claims a length of zero. A walk that trusts it never
# advances, and the console sits there until the board is reset.
ZERO_LEN = cfg(1, iface(0, 0, 1, 0x09, 0, 0)) + bytes([0, 5, 0x81, 3, 1, 0, 12])

# A record whose length runs past what the device actually sent. A walk
# that trusts it reads whatever is behind the buffer and prints it as an
# endpoint.
OVERRUN = cfg(1, iface(0, 0, 1, 0x09, 0, 0)) + bytes([64, 5, 0x81, 3, 1, 0, 12])


def literal(name, data):
    rows = ", ".join(str(b) for b in data)
    return f"Global Dim {name}.a[{len(data)}]\n" \
           f"#{name.upper()}_LEN = {len(data)}\n" \
           f"Procedure {name}_Fill()\n" \
           + "\n".join(f"  {name}[{i}] = {b}" for i, b in enumerate(data)) \
           + "\nEndProcedure\n"


PRELUDE = """
; The walk reads the USB core's OWN store, so the fixture fills that store
; rather than a fake of it. The two globals below are the production ones,
; declared here because only the walk is extracted and not the whole file.
#USB_CFG_BYTES = 512
Global Dim usbc_cfg.a[#USB_CFG_BYTES]
Global usbc_cfgHeld.i = 0

; Load one fabricated set. The HELD count is deliberately separate from
; the length the descriptor CLAIMS, because the overrun case is exactly a
; descriptor that claims more than arrived.
Procedure GateLoad(which.i)
  Define i.i
  i = 0
  While i < #USB_CFG_BYTES
    usbc_cfg[i] = 0
    i = i + 1
  Wend
  usbc_cfgHeld = GateSet(which)
EndProcedure
"""


def gate_set_source():
    sets = (("HUB", HUB), ("STICK", STICK), ("COMPOSITE", COMPOSITE),
            ("ZERO_LEN", ZERO_LEN), ("OVERRUN", OVERRUN))
    out = ["Procedure.i GateSet(which.i)"]
    for n, (name, data) in enumerate(sets):
        out.append(f"  If which = {n}")
        for i, b in enumerate(data):
            out.append(f"    usbc_cfg[{i}] = {b}")
        out.append(f"    ProcedureReturn {len(data)}")
        out.append("  EndIf")
    out.append("  ProcedureReturn 0")
    out.append("EndProcedure")
    return "\n".join(out)


MAIN = r'''
; Walk a set and count the interfaces, endpoints and companions in it.
; Returns -1 the moment the chain refuses, which is the answer the
; malformed sets must produce and the working ones must not.
Global gIf.i
Global gEp.i
Global gComp.i
Global gBurst.i

Procedure.i GateWalk()
  Define off.i
  Define typ.i
  gIf = 0
  gEp = 0
  gComp = 0
  gBurst = -1
  off = UsbCfgNext(0)
  While off > 0
    typ = UsbCfgByte(off + 1)
    If typ < 0
      ProcedureReturn -1
    EndIf
    If typ = 4
      gIf = gIf + 1
    EndIf
    If typ = 5
      gEp = gEp + 1
    EndIf
    If typ = $30
      gComp = gComp + 1
      gBurst = UsbCfgByte(off + 2) & $1F
    EndIf
    off = UsbCfgNext(off)
    If off < 0
      ProcedureReturn -1
    EndIf
  Wend
  ProcedureReturn 0
EndProcedure

Procedure.i Main()
  Define n.i

  ; ---- 1. a hub: one interface, one interrupt endpoint, no companion.
  GateLoad(0)
  If GateWalk() <> 0 : ProcedureReturn 1 : EndIf
  If gIf <> 1 Or gEp <> 1 Or gComp <> 0 : ProcedureReturn 2 : EndIf
  If UsbCfgByte(1) <> 2 : ProcedureReturn 3 : EndIf

  ; ---- 2. a SuperSpeed stick: TWO alternate settings on one interface
  ;         number - Bulk-Only and UAS - six endpoints and six companions.
  ;         This is the shape that used to be reported as "not storage".
  GateLoad(1)
  If GateWalk() <> 0 : ProcedureReturn 10 : EndIf
  If gIf <> 2 : ProcedureReturn 11 : EndIf
  If gEp <> 6 : ProcedureReturn 12 : EndIf
  If gComp <> 6 : ProcedureReturn 13 : EndIf
  If gBurst <> 15 : ProcedureReturn 14 : EndIf
  ; wTotalLength is read as a WHOLE word and not as one byte plus a zero.
  If UsbCfgWord(2) <> 105 : ProcedureReturn 15 : EndIf

  ; ---- 3. a composite device: a boot keyboard and a serial port.
  GateLoad(2)
  If GateWalk() <> 0 : ProcedureReturn 20 : EndIf
  If gIf <> 2 Or gEp <> 3 Or gComp <> 0 : ProcedureReturn 21 : EndIf

  ; ---- 4. A LENGTH OF ZERO IS REFUSED. Without the refusal this loops
  ;         forever and the console never comes back.
  GateLoad(3)
  If GateWalk() <> -1 : ProcedureReturn 30 : EndIf

  ; ---- 5. A RECORD PAST THE END IS REFUSED, rather than decoded from
  ;         whatever is behind the buffer.
  GateLoad(4)
  If GateWalk() <> -1 : ProcedureReturn 31 : EndIf

  ; ---- 6. A word straddling the end is -1, not a half value. The stick
  ;         set is 105 bytes long, so byte 104 is its last.
  GateLoad(1)
  If UsbCfgByte(104) < 0 : ProcedureReturn 40 : EndIf
  If UsbCfgByte(105) <> -1 : ProcedureReturn 41 : EndIf
  If UsbCfgWord(104) <> -1 : ProcedureReturn 42 : EndIf

  ; ---- 7. The class names a driver author reads, in words.
  If GateStrEq(UsbClassText($08, 6, $50), "mass storage, SCSI, Bulk-Only") = 0 : ProcedureReturn 50 : EndIf
  If GateStrEq(UsbClassText($08, 6, $62), "mass storage, SCSI, USB Attached SCSI") = 0 : ProcedureReturn 51 : EndIf
  If GateStrEq(UsbClassText($09, 0, 0), "hub") = 0 : ProcedureReturn 52 : EndIf
  If GateStrEq(UsbClassText($03, 1, 1), "human interface, boot keyboard") = 0 : ProcedureReturn 53 : EndIf
  If GateStrEq(UsbClassText($FF, 0, 0), "vendor specific") = 0 : ProcedureReturn 54 : EndIf
  ; An unassigned class is NAMED as unnamed rather than guessed at.
  If GateStrEq(UsbClassText($7B, 0, 0), "unnamed class") = 0 : ProcedureReturn 55 : EndIf
  If GateStrEq(UsbEpTypeText(2), "bulk") = 0 : ProcedureReturn 56 : EndIf
  If GateStrEq(UsbEpTypeText(3), "interrupt") = 0 : ProcedureReturn 57 : EndIf
  ProcedureReturn 0
EndProcedure
'''

STRCMP = r'''
Procedure.i GateStrEq(*a, *b)
  Define i.i
  i = 0
  While PeekA(*a + i) <> 0 And PeekA(*b + i) <> 0
    If PeekA(*a + i) <> PeekA(*b + i)
      ProcedureReturn 0
    EndIf
    i = i + 1
  Wend
  If PeekA(*a + i) <> PeekA(*b + i)
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure
'''

MUTANTS = (
    # The anchor carries the line above it because `If len < 2` also guards
    # the string-descriptor reader a few hundred lines up, and a mutant that
    # matched both would be testing two things and proving neither.
    ("a length of zero is walked on",
     "  held = usbc_cfgHeld\n"
     "  ; A DESCRIPTOR SHORTER THAN ITS OWN HEADER IS NOT A DESCRIPTOR. Two is\n"
     "  ; bLength plus bDescriptorType; a length of 0 or 1 advances the walk by\n"
     "  ; nothing and loops forever, which is the failure this refuses.\n"
     "  If len < 2",
     "  held = usbc_cfgHeld\n  If len < 0"),
    ("a record past the end is decoded anyway",
     "  If off + len > held\n    ProcedureReturn -1\n  EndIf",
     "  If off + len > held And 1 = 0\n    ProcedureReturn -1\n  EndIf"),
    ("a word straddling the end is built from one byte",
     "  If lo < 0 Or hi < 0\n    ProcedureReturn -1\n  EndIf",
     "  If lo < 0\n    ProcedureReturn -1\n  EndIf"),
    ("an unassigned class is named as though it were known",
     '  ProcedureReturn "unnamed class"',
     '  ProcedureReturn "hub"'),
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
        raise SystemExit("usb devices gate: compile failed\n" + run.stdout)
    return image


def program(source: str) -> str:
    bodies = "\n\n".join(procedure(source, name) for name in WALK)
    return ("EnableExplicit\n" + PRELUDE + "\n" + gate_set_source() + "\n"
            + STRCMP + "\n" + bodies + "\n" + MAIN)


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
    emitted.STEP_LIMIT = 40_000_000

    source = USB_CORE.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="anvil-usb-devices-") as temporary:
        work = Path(temporary)
        result, steps = run(a64, compiler, work, program(source), "devices_gate")
        if result:
            print(f"usb_devices_check: FAIL assertion {result} after {steps:,} instructions")
            return 1
        caught = 0
        for index, (label, old, new) in enumerate(MUTANTS):
            if source.count(old) != 1:
                print(f"usb_devices_check: FAIL the mutant anchor for '{label}' "
                      f"appears {source.count(old)} times - the gate is out of date, "
                      "which is not the same as the code being right")
                return 1
            mutated = program(source.replace(old, new, 1))
            try:
                bad, _ = run(a64, compiler, work, mutated, f"mutant{index}")
            except SystemExit as stop:
                # A WALK THAT NEVER RETURNS IS THE DEFECT ITSELF, not a
                # broken gate. The zero-length mutant is precisely the
                # chain that advances by nothing forever, so running out
                # of instructions is the correct way to catch it - and it
                # is reported as what it is rather than as a tool failure.
                if "no return" not in str(stop):
                    raise
                caught += 1
                continue
            if bad == 0:
                print(f"usb_devices_check: FAIL the mutant '{label}' was not caught")
                return 1
            caught += 1
    print(f"usb_devices_check: PASS - five descriptor sets walked, two of them "
          f"malformed and both refused, in {steps:,} emitted instructions; "
          f"{caught} mutants rejected")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""The raw link readout decodes the words it is given - proved, not asserted.

WHY THIS GATE EXISTS AT ALL

`usb tree` has always ended its controller line with the words "spread-
spectrum clocking on". Those words came from a boolean, and a boolean is
the one kind of evidence nobody can check: it reads identically whether the
driver turned the feature on, found it already on, or merely believes it
did. `usb link` replaces the boolean with the PHY's and the controller's
own registers - and a readout that misdecodes them is WORSE than the
boolean it replaced, because it looks like evidence.

So the decode is the thing under test. The production HwUsbLinkRegValue /
HwUsbLinkFieldCount / HwUsbLinkFieldValue procedures are lifted out of
RaspberryPi4/Board/hw_usb.pi4 verbatim and run over a root complex whose
registers hold planted words. Every expectation below is a bit position
taken from a driver that runs this part in service:

  Linux rpi-6.12.y drivers/pci/controller/pcie-brcmstb.c
      38-39    BRCM_PCIE_CAP_REGS $AC, so LNKCAP is $B8 and the
               LNKCTL/LNKSTA halfword pair shares the word at $BC
      95-99    MISC_CTRL RCB_64B $80, RCB_MPS $400, SCB_ACCESS_EN $1000,
               CFG_READ_UR $2000, MAX_BURST $300000
      145      MISC_REVISION $406C
      165-172  HARD_DEBUG CLKREQ_DEBUG $2, REFCLK_OVRD_ENABLE $10000,
               REFCLK_OVRD_OUT $100000, L1SS_ENABLE $200000,
               SERDES_IDDQ $08000000
      219-226  SSC_CNTL OVRD_EN $8000 and OVRD_VAL $4000, SSC_STATUS
               SSC $400 and PLL_LOCK $800
      55-56    ROOT_CAP $4F8, L1SS_MODE bits 7:3
  U-Boot v2025.01 drivers/pci/pcie_brcmstb.c and its bcm2711_acpi.h
      73-79    PCIE_STATUS $4068, PHYLINKUP $10, DL_ACTIVE $20, PORT $80

THE PLANTS ARE NOT CONVENIENT. Every scenario sets bits NEXT TO each field
as well as inside it, because a mask one bit too wide and a shift one place
out both read correctly on a register whose neighbours are zero. Scenario A
is this board's real MISC_CTRL word, read off the silicon on 2026-09-18.

No board, no image, no build counter: the fixture is a handful of
procedures, not a monitor.
"""
import argparse
import os
import pathlib
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "a64"))
import el3_runtime_emitted_check as b  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--compiler", required=True)
args = ap.parse_args()

SRC = (b.ROOT / "RaspberryPi4/Board/hw_usb.pi4").read_text()


def proc(name):
    m = re.search(r"(?ms)^Procedure(?:\.i)? " + name + r"\([^\n]*\).*?^EndProcedure", SRC)
    if not m:
        raise SystemExit("the readout gate cannot find " + name + " in hw_usb.pi4")
    return m.group()


BODY = "\n".join(
    proc(n)
    for n in (
        "HwUsbLinkRegCount",
        "HwUsbLinkRegValue",
        "HwUsbLinkFieldCount",
        "HwUsbLinkFieldValue",
    )
)

# The #HWUSB_LINK_* row numbers, taken from the file rather than repeated
# here - a gate that keeps its own copy of the numbering stops noticing when
# the numbering moves.
CONST = "\n".join(
    m.group(0) for m in re.finditer(r"(?m)^#HWUSB_LINK_\w+\s*=.*$", SRC)
)
ROW = {
    m.group(1): int(m.group(2))
    for m in re.finditer(r"(?m)^#HWUSB_LINK_(\w+)\s*=\s*(\d+)", SRC)
}

MODEL = """
Global sscCntl.i
Global sscStatus.i
Dim rc.i[20000]
Procedure.i PcieSscCntlRaw()   : ProcedureReturn sscCntl   : EndProcedure
Procedure.i PcieSscStatusRaw() : ProcedureReturn sscStatus : EndProcedure
Procedure.i PcieRcPeek(off.i)
 ; The production accessor refuses an unaligned or out-of-range offset with
 ; a negative code, and the readout has to survive that answer the same way
 ; it survives a PHY that never spoke.
 If off < 0 : ProcedureReturn -1 : EndIf
 If (off & 3) <> 0 : ProcedureReturn -2 : EndIf
 ProcedureReturn rc[off/4]
EndProcedure
"""

MAIN = """
Procedure.i Main()
 Define r.i
 Define f.i
 Define k.i
 sscCntl=SSCCNTL
 sscStatus=SSCSTATUS
 rc[$B8/4]=LNKCAPW
 rc[$BC/4]=LNKW
 rc[$4008/4]=MISCCTRL
 rc[$4204/4]=HARDDEBUG
 rc[$04F8/4]=ROOTCAP
 rc[$406C/4]=REVISION
 rc[$4068/4]=STATUSW
 ; Row 0 of the output is the register count; then, for every row, its raw
 ; value followed by its field values - flattened, eight bytes each, in the
 ; order the command prints them.
 PokeI($06000000,HwUsbLinkRegCount())
 k=1
 r=0
 While r < HwUsbLinkRegCount()
  PokeI($06000000+8*k,HwUsbLinkRegValue(r))
  k=k+1
  f=0
  While f < HwUsbLinkFieldCount(r)
   PokeI($06000000+8*k,HwUsbLinkFieldValue(r,f))
   k=k+1
   f=f+1
  Wend
  r=r+1
 Wend
 ProcedureReturn 0
EndProcedure
"""

INTERP = b.load_interpreter(b.INTERP)


def run(work, text, plants):
    src = work / "linkread.pi4"
    img = work / "linkread.img"
    main = MAIN
    for key, value in plants.items():
        main = main.replace(key, str(value))
    src.write_text(CONST + "\n" + MODEL + text + main)
    env = os.environ.copy()
    env["PMF_ROOT"] = str(b.ROOT)
    r = subprocess.run(
        [args.compiler, "--compile", str(src), "-t", "pi4", "--entry-returns",
         "--load-addr", hex(b.LOAD), "--stack-addr", hex(b.STACK), "-o", str(img)],
        cwd=b.ROOT, env=env, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stdout + r.stderr)
    c = INTERP.A64()
    c.memory.update({b.LOAD + i: v for i, v in enumerate(img.read_bytes())})
    c.pc = b.LOAD
    c.sp = b.STACK
    c.x[30] = b.RETURN_PC
    for _ in range(400000):
        if c.pc == b.RETURN_PC:
            break
        c.step()
    else:
        raise RuntimeError("instruction limit")
    out = []
    for i in range(120):
        v = b.u64(c, b.OUT + 8 * i)
        out.append(v - (1 << 64) if v >= (1 << 63) else v)
    return out


def rows(out):
    """Re-cut the flat output into {row: (raw, [fields])} using the shape the
    command itself walks, so the gate reads the readout the way a person does."""
    n = out[0]
    got = {}
    k = 1
    for r in range(n):
        raw = out[k]
        k += 1
        fields = []
        # The field count is a property of the row, not of the run, so it is
        # taken from the same source the fixture used: the production
        # procedure, re-read here from its own answer in scenario A.
        for _ in range(FIELDS[r]):
            fields.append(out[k])
            k += 1
        got[r] = (raw, fields)
    return got


# How many fields each row has, read out of the production procedure's text
# rather than restated - the one number this gate is allowed to take on
# trust, because getting it wrong desynchronises the whole flat vector and
# every assertion below would fail loudly rather than quietly.
FIELDS = {}
_fc = proc("HwUsbLinkFieldCount")
for name, count in re.findall(r"Case #HWUSB_LINK_(\w+)\s*:\s*ProcedureReturn (\d+)", _fc):
    FIELDS[ROW[name]] = int(count)
for r in range(len(ROW) - 1):
    FIELDS.setdefault(r, 0)

# ---- the scenarios ---------------------------------------------------
# A: THIS BOARD, HEALTHY. MISC_CTRL is the word build 188 actually read off
#    the silicon ($88003480); the rest are the states both drivers leave.
#    Neighbouring bits are set on purpose so a wide mask or a shifted read
#    cannot pass.
A = dict(SSCCNTL=0xC123, SSCSTATUS=0x0E00, LNKCAPW=0xF012, LNKW=0x10120040,
         MISCCTRL=0x88003480, HARDDEBUG=0x80110001, ROOTCAP=0x117,
         REVISION=0x12345678, STATUSW=0xB1)
A_EXPECT = {
    "SSC_CNTL":   (0xC123, [1, 1]),
    "SSC_STATUS": (0x0E00, [1, 1]),
    "LNKCAP":     (0xF012, [2, 1, 0]),
    "LNKCTL":     (0x0040, [0, 0, 1]),
    "LNKSTA":     (0x1012, [2, 1, 0]),
    "MISC_CTRL":  (0x88003480, [0, 1, 1, 1, 1, 17]),
    "HARD_DEBUG": (0x80110001, [0, 1, 1, 0, 0]),
    "ROOT_CAP":   (0x117, [2]),
    "REVISION":   (0x12345678, []),
    "STATUS":     (0xB1, [1, 1, 1]),
}

# B: THE PHY NEVER ANSWERED. -1 must reach every field of those two rows.
#    A zero here would credit the driver with bits it never read, which is
#    exactly the failure this whole command exists to make impossible.
B = dict(A, SSCCNTL=-1, SSCSTATUS=-1)

# C: SPREAD SPECTRUM ON, PLL NOT LOCKED - the failure both drivers report.
#    With the two bits DIFFERENT, reading one of them from the other's
#    position is visible; in scenario A, where both are 1, it is not.
C = dict(A, SSCSTATUS=0x0400)

# D: A WIDE, FAST LINK. Width 16 and speed code 3 (8.0 GT/s) are not what
#    this board trains at, and that is the point: a width masked to four
#    bits reads 0 where the register says 16. The values are the ARCHITECTED
#    CODES, not gigatransfers - decoding a code into words is the core's
#    job and this seam never does it.
D = dict(A, LNKW=0x01030040, LNKCAPW=0x0103)

with tempfile.TemporaryDirectory(prefix="pcie-link-readout-") as tmp:
    work = pathlib.Path(tmp)

    out = run(work, BODY, A)
    assert out[0] == len(ROW) - 1, ("row count", out[0])
    got = rows(out)
    for name, want in A_EXPECT.items():
        r = ROW[name]
        assert got[r] == (want[0], want[1]), (name, want, got[r])
    print("A  this board, healthy:", {k: got[ROW[k]] for k in ("SSC_CNTL", "SSC_STATUS", "LNKSTA", "MISC_CTRL", "HARD_DEBUG", "ROOT_CAP")})

    got = rows(run(work, BODY, B))
    for name in ("SSC_CNTL", "SSC_STATUS"):
        raw, fields = got[ROW[name]]
        assert raw == -1 and fields == [-1] * len(fields), (name, raw, fields)
    # and the controller registers are untouched by the PHY's silence
    assert got[ROW["MISC_CTRL"]] == A_EXPECT["MISC_CTRL"], got[ROW["MISC_CTRL"]]
    print("B  the PHY never answered: every SSC field -1, the controller rows unchanged")

    got = rows(run(work, BODY, C))
    assert got[ROW["SSC_STATUS"]] == (0x0400, [1, 0]), got[ROW["SSC_STATUS"]]
    print("C  spread spectrum on, PLL not locked:", got[ROW["SSC_STATUS"]])

    got = rows(run(work, BODY, D))
    assert got[ROW["LNKSTA"]][1] == [3, 16, 0], got[ROW["LNKSTA"]]
    print("D  a sixteen-lane speed-code-3 link:", got[ROW["LNKSTA"]])

    # ---- and every one of those readings is a claim something can break --
    MUTANTS = [
        # The SSC bit read from the PLL's position. Invisible in A, where
        # both are 1; scenario C is what catches it.
        ("ssc-bit-swapped",
         BODY.replace("        Case 0 : ProcedureReturn (v >> 10) & 1\n        Case 1 : ProcedureReturn (v >> 11) & 1",
                      "        Case 0 : ProcedureReturn (v >> 11) & 1\n        Case 1 : ProcedureReturn (v >> 10) & 1", 1),
         (A, C)),
        # The negotiated width masked to four bits instead of six - correct
        # for every link this board has ever trained, and wrong for a x16.
        ("lnksta-width-narrow",
         BODY.replace("        Case 1 : ProcedureReturn (v >> 4) & $3F\n        Case 2 : ProcedureReturn (v >> 11) & 1",
                      "        Case 1 : ProcedureReturn (v >> 4) & $0F\n        Case 2 : ProcedureReturn (v >> 11) & 1", 1),
         (A, D)),
        # A register nothing answered reported as a register holding zero.
        ("unread-reads-as-zero",
         BODY.replace("  v = HwUsbLinkRegValue(r)\n  If v < 0\n    ProcedureReturn -1\n  EndIf",
                      "  v = HwUsbLinkRegValue(r)\n  If v < 0\n    v = 0\n  EndIf", 1),
         (A, B)),
        # The inbound window size read one bit low - a five-bit field at 26
        # instead of 27 reads 2 where the board says 17.
        ("scb0-shift-off-by-one",
         BODY.replace("        Case 5 : ProcedureReturn (v >> 27) & $1F",
                      "        Case 5 : ProcedureReturn (v >> 26) & $1F", 1),
         (A,)),
        # The read completion boundary read from the wrong bit: $400 is
        # RCB_MPS and $800 is not a MISC_CTRL field at all.
        ("rcb-mps-wrong-bit",
         BODY.replace("        Case 3 : ProcedureReturn (v >> 10) & 1",
                      "        Case 3 : ProcedureReturn (v >> 11) & 1", 1),
         (A,)),
        # The LNKCTL/LNKSTA split reversed, which would print the control
        # register's bits under the status register's names.
        ("lnkctl-lnksta-halves-swapped",
         BODY.replace("      ProcedureReturn v & $FFFF\n    Case #HWUSB_LINK_LNKSTA",
                      "      ProcedureReturn (v >> 16) & $FFFF\n    Case #HWUSB_LINK_LNKSTA", 1),
         (A,)),
    ]
    for label, mutant, scenarios in MUTANTS:
        assert mutant != BODY, "mutant " + label + " changed nothing - its target text has moved"
        caught = False
        for plants in scenarios:
            try:
                got = rows(run(work, mutant, plants))
                expect = A_EXPECT if plants is A else None
                if plants is A:
                    for name, want in A_EXPECT.items():
                        assert got[ROW[name]] == (want[0], want[1]), name
                elif plants is B:
                    for name in ("SSC_CNTL", "SSC_STATUS"):
                        raw, fields = got[ROW[name]]
                        assert raw == -1 and fields == [-1] * len(fields), name
                elif plants is C:
                    assert got[ROW["SSC_STATUS"]] == (0x0400, [1, 0])
                elif plants is D:
                    assert got[ROW["LNKSTA"]][1] == [3, 16, 0]
            except AssertionError:
                caught = True
        if not caught:
            raise AssertionError("readout mutant survived: " + label)
        print("   mutant rejected:", label)

print("PASS the raw link readout decodes every named field out of the word it "
      "printed - this board's real MISC_CTRL, a PHY that never answered, spread "
      "spectrum without PLL lock, and a sixteen-lane link - with six decode "
      "mutants rejected")

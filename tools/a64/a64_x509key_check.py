#!/usr/bin/env python3
"""Executable gate for the X.509 end-entity key buffer's own bound on
AArch64 - XkeyFits in RaspberryPi4/Lib/x509.pi4.

WHAT THIS PROVES, AND WHY IT IS SEPARATE FROM a64_x509_check.py

  a64_x509_check.py walks REAL captured certificate chains.  It proves
  that the engine still validates what it should, which is the claim
  "the bound did not break the parser".  It cannot prove the other half,
  because no certificate on earth reaches these lengths: the lifted
  bytecode caps the key window before the copy runs, and that cap lives
  in a GENERATED blob whose header says to regenerate it from upstream.
  The bound exists precisely because that coincidence is not an
  invariant, so the proof has to drive the native dispatch directly -
  which is what RaspberryPi4/Examples/Diagnostics/pi4X509KeyBoundProbe.pi4
  does, through X509Native(), the same route a certificate takes.

  THE PROBE IS THE A64 TWIN OF THE 32-BIT KEY-BOUND PROBE, case for
  case, and the two halves are what make it a proof rather than an
  assertion:

    * REFUSALS - an oversized, negative or wrapping length is refused by
      NAME (#X509ERR_KEY_BOUNDS, 901), the machine is halted, nothing is
      published and not one byte is copied.  Including the case the
      CONTEXT-RAM guard would have waved through: 560 bytes at the key
      window, asserted in range for XrInRange on the line before.
    * ACCEPTANCES - every key size a real certificate carries still
      round-trips, including the two that fill the buffer exactly.  A
      bound that refused everything would pass every refusal check and
      be worse than no bound at all.

  THE 64-BIT DIFFERENCE IS THE REASON THE PORT NEEDED ITS OWN RUN.  The
  32-bit probe's wrap case is two $7FFFFFFF halves; on this part they
  sum to 4,294,967,294 and a naive `n + e > SIZE` would catch them.  The
  probe uses $7FFFFFFFFFFFFFFF instead and check 54 shows the naive test
  answering FITS on the part's own arithmetic, one line above the check
  that refuses the pair.  The guard is width-independent because of its
  FORM - `n > SIZE - e` - and this is where that is measured rather than
  argued.

THE NEGATIVE CONTROL IS NOT OPTIONAL

  A gate that is only ever green proves nothing.  --sabotage (on by
  default; --no-sabotage skips it) builds a SECOND image in which
  XkeyFits' body is replaced by `ProcedureReturn 1` and NOTHING ELSE
  changes - asserted by diffing the two library files and requiring
  exactly one hunk.  That image must FAIL, every acceptance check must
  still pass, and the two overrun witnesses must be among the failures:
  bytes landing past the end of a 520-byte array, in the globals next
  door.  A sabotage that failed for any other reason would be measuring
  the sabotage and not the bound.

  The library is COPIED, never mutated in place.

WHAT THIS GATE DOES NOT SAY

  Nothing about silicon.  The oracle is tools/a64/a64_interp.py, a model
  of the instruction set: no caches, no memory system, no clock.  The
  board pass is owed separately and is recorded as owed.

IT RUNS THE TWO IMAGES ON TWO PROCESSES.  Two jobs is not a corpus, but
a serial pass here is two builds and two runs back to back for no
reason; --jobs 1 forces serial when another worker owns the machine.

Run: python tools/a64/a64_x509key_check.py
     python tools/a64/a64_x509key_check.py --no-sabotage
"""

from __future__ import annotations

import argparse
import concurrent.futures
import difflib
import os
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
# THE TREE UNDER TEST IS THE ONE THIS SCRIPT LIVES IN.  A root pinned
# into a file made another gate build a DIFFERENT working copy, with
# that copy's compiler, and print the answer as this tree's.
ROOT = pathlib.Path(__file__).resolve().parents[2]
print("[gate] tree under test: %s" % ROOT, file=sys.stderr)
sys.path.insert(0, str(HERE))
from a64_interp import A64, attach_symbols  # noqa: E402

PMFC = os.environ.get("PMF_COMPILER") or "PureMetalForge.exe"  # rebound from --compiler
# Every compile resolves includes from THIS tree only.
BUILD_ENV = dict(os.environ, PMF_ROOT=str(ROOT))
X509 = ROOT / "RaspberryPi4" / "Lib" / "x509.pi4"
PROBE = (ROOT / "RaspberryPi4" / "Examples" / "Diagnostics"
         / "pi4X509KeyBoundProbe.pi4")
WORK = ROOT / "_work" / "x509key"

# The bench flags.  A gate that ran a differently-linked image would be
# proving something about an artefact nobody deploys.
LOAD = 0x00400000
STACK = 0x03000000
LOADER_SP = 0x00100000
LOADER_LR = 0xDEADBEE0

# The probe copies at most a few thousand bytes a byte at a time and
# prints 67 lines.  Measured at well under ten million; this is a
# runaway detector, not a budget.
STEP_LIMIT = 400_000_000

UART_DR = 0xFE201000
UART_FR = 0xFE201018
GPIO_LO, GPIO_HI = 0xFE200000, 0xFE2000FF
PL011_LO, PL011_HI = 0xFE201000, 0xFE201FFF
FR_IDLE = 0x90

# The probe's own numbers, re-stated here.  A harness that read the
# count out of the program's output would agree with a program that ran
# half its cases.
EXPECT_CHECKS = 67
# Which checks are ACCEPTANCE and which are REFUSAL, from the probe's
# own report text.  The sabotage must not disturb the first group.
ACCEPT = set(range(1, 32)) | set(range(65, 68))
REFUSE = set(range(32, 65))
# The two overrun witnesses.  Under sabotage these are the checks that
# say bytes really did land past the end of the array, and the sabotage
# is only meaningful if at least one of them fires.
WITNESSES = {48, 49}
# Check 54 is ARITHMETIC, not a guard: it runs the naive `n + e > SIZE`
# test and requires it to answer FITS.  It must pass in BOTH images, and
# a sabotage run in which it failed would mean the harness had changed
# the arithmetic rather than removed the bound.
ARITHMETIC = {54}

CHECK_RE = re.compile(r"^\s*check (\d+)\s+(ok|FAIL)\s+expected (-?\d+) saw (-?\d+)\s*$")

# The one hunk the sabotage is allowed to be.
SAB_FIND = """Procedure.i XkeyFits(n.i, e.i)
  If n < 0 Or e < 0 Or n > (#X_EEPKEY_SIZE - e)
    xErr = #X509ERR_KEY_BOUNDS
    t0_ip = -1
    ProcedureReturn 0
  EndIf
  If XrInRange(#X_pkey_data, n + e) = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure"""
SAB_REPLACE = """Procedure.i XkeyFits(n.i, e.i)
  ; SABOTAGE - the bound removed, nothing else touched.
  If n = e
    ProcedureReturn 1
  EndIf
  ProcedureReturn 1
EndProcedure"""


# ---------------------------------------------------------------------
#  BUILD AND RUN
# ---------------------------------------------------------------------
def build(source: pathlib.Path, out: pathlib.Path) -> dict[str, int]:
    WORK.mkdir(parents=True, exist_ok=True)
    cmd = [str(PMFC), "--compile", str(source), "-t", "pi4",
           "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
           "--entry-returns", "-s", "-o", str(out)]
    r = subprocess.run(cmd, cwd=ROOT, env=BUILD_ENV, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout:
        raise SystemExit("build failed for %s:\n%s" % (source, r.stdout))
    syms: dict[str, int] = {}
    symfile = pathlib.Path(str(out) + ".sym")
    for line in symfile.read_text(encoding="utf-8-sig").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            syms[k.strip()] = int(v.strip(), 0)
    return syms


def run(img: pathlib.Path, syms: dict[str, int]):
    """Execute the image on the model.  Returns (uart text, globals)."""
    blob = img.read_bytes()
    cpu = A64()
    for i, b in enumerate(blob):
        cpu.memory[LOAD + i] = b
    attach_symbols(cpu, img, LOAD)
    cpu.pc = LOAD
    cpu.sp = LOADER_SP
    cpu.x[30] = LOADER_LR

    mem = cpu.memory
    uart = bytearray()

    def load(addr: int, size: int) -> int:
        if addr >= 0xFE000000:
            if addr == UART_FR:
                return FR_IDLE
            if PL011_LO <= addr <= PL011_HI:
                return 0
            if GPIO_LO <= addr <= GPIO_HI:
                return 0
            raise SystemExit("unmodelled MMIO read at $%08X - this probe is "
                             "supposed to touch no hardware but the console"
                             % addr)
        return sum(mem.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr: int, value: int, size: int) -> None:
        if addr >= 0xFE000000:
            if addr == UART_DR:
                uart.append(value & 0xFF)
                return
            if PL011_LO <= addr <= PL011_HI:
                return
            if GPIO_LO <= addr <= GPIO_HI:
                return
            raise SystemExit("unmodelled MMIO write at $%08X" % addr)
        for i in range(size):
            mem[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store

    steps = 0
    while steps < STEP_LIMIT:
        if cpu.pc == LOADER_LR:
            break
        cpu.step()
        steps += 1
    else:
        raise SystemExit("the probe never returned after %d model "
                         "instructions\n%s" % (steps, uart.decode("latin-1")))

    def g(name: str) -> int:
        a = syms.get("global_" + name)
        if a is None:
            raise SystemExit("%s is not in the symbol map" % name)
        v = sum(cpu.memory.get(a + i, 0) << (8 * i) for i in range(8))
        return v - (1 << 64) if v >= (1 << 63) else v

    return uart.decode("latin-1"), {
        "n": g("xkn"), "bad": g("xkbad"), "ran": g("xkran"),
    }, steps


def parse_checks(text: str) -> dict[int, tuple[bool, int, int]]:
    """check number -> (passed, wanted, saw), from the probe's report."""
    out: dict[int, tuple[bool, int, int]] = {}
    for line in text.splitlines():
        m = CHECK_RE.match(line)
        if m:
            out[int(m.group(1))] = (m.group(2) == "ok",
                                    int(m.group(3)), int(m.group(4)))
    return out


# ---------------------------------------------------------------------
#  THE HONEST BUILD
# ---------------------------------------------------------------------
def job_honest():
    img = WORK / "keyprobe.img"
    syms = build(PROBE, img)
    text, g, steps = run(img, syms)
    return text, g, steps, img.stat().st_size


def judge_honest(text, g, size) -> list[str]:
    bad: list[str] = []
    checks = parse_checks(text)
    if g["ran"] != 1:
        bad.append("the probe did not reach the end of Main - xkRan is 0, so "
                   "xkBad means nothing")
    if g["n"] != EXPECT_CHECKS:
        bad.append("the probe ran %d checks and this gate expects %d - a case "
                   "was added or lost and one of the two files was not "
                   "updated" % (g["n"], EXPECT_CHECKS))
    if g["bad"] != 0:
        bad.append("xkBad = %d: the bound is wrong on this part" % g["bad"])
    if len(checks) != EXPECT_CHECKS:
        bad.append("the report carries %d check lines, not %d - the console "
                   "output and the globals disagree, which is worse than "
                   "either alone" % (len(checks), EXPECT_CHECKS))
    for i, (ok, want, saw) in sorted(checks.items()):
        if not ok:
            half = "ACCEPTANCE" if i in ACCEPT else "REFUSAL"
            bad.append("check %d (%s) wanted %d and saw %d" % (i, half, want, saw))
    if "x509 key-buffer bound: PASS" not in text and not bad:
        bad.append("the probe did not print its PASS line although every "
                   "value this gate reads looks right - read its output")
    return bad


# ---------------------------------------------------------------------
#  THE NEGATIVE CONTROL
# ---------------------------------------------------------------------
def stage_sabotage() -> tuple[pathlib.Path, pathlib.Path, str]:
    """Write the sabotaged library and a probe that includes it.

    THE LIBRARY IS COPIED, NEVER EDITED IN PLACE, and the diff between
    the two copies is returned so the caller can assert it is one hunk.
    """
    WORK.mkdir(parents=True, exist_ok=True)
    orig = X509.read_text(encoding="utf-8")
    if orig.count(SAB_FIND) != 1:
        raise SystemExit(
            "the sabotage cannot find XkeyFits' body in %s exactly once. "
            "Either the bound is gone - which is the thing this gate "
            "exists to notice - or it was reformatted and SAB_FIND in "
            "this file has to be updated to match." % X509)
    sab = orig.replace(SAB_FIND, SAB_REPLACE)
    sab_path = WORK / "x509_sab.pi4"
    sab_path.write_text(sab, encoding="utf-8")

    probe = PROBE.read_text(encoding="utf-8")
    inc = 'XIncludeFile "RaspberryPi4/Lib/x509.pi4"'
    if probe.count(inc) != 1:
        raise SystemExit("the probe does not include x509.pi4 exactly once")
    probe = probe.replace(inc, 'XIncludeFile "_work/x509key/x509_sab.pi4"')
    probe_path = WORK / "keyprobe_sab.pi4"
    probe_path.write_text(probe, encoding="utf-8")

    diff = "\n".join(difflib.unified_diff(
        orig.splitlines(), sab.splitlines(),
        fromfile="RaspberryPi4/Lib/x509.pi4",
        tofile="_work/x509key/x509_sab.pi4", lineterm="", n=1))
    return sab_path, probe_path, diff


def job_sabotage():
    sab_lib, sab_probe, diff = stage_sabotage()
    img = WORK / "keyprobe_sab.img"
    syms = build(sab_probe, img)
    text, g, steps = run(img, syms)
    return text, g, steps, diff, sab_lib


def judge_sabotage(text, g, diff) -> tuple[list[str], list[int]]:
    bad: list[str] = []

    # ONE HUNK, and it is XkeyFits'.  A sabotage that changed anything
    # else would be measuring the change and not the bound.
    hunks = [l for l in diff.splitlines() if l.startswith("@@")]
    if len(hunks) != 1:
        bad.append("the sabotage diff has %d hunks, not 1 - it changed "
                   "something besides XkeyFits' body:\n%s"
                   % (len(hunks), diff))

    checks = parse_checks(text)
    if g["ran"] != 1:
        bad.append("the sabotaged probe did not finish, so its failures "
                   "cannot be read")
    if g["n"] != EXPECT_CHECKS:
        bad.append("the sabotaged probe ran %d checks, not %d"
                   % (g["n"], EXPECT_CHECKS))
    if g["bad"] == 0:
        bad.append("THE SABOTAGE WAS NOT CAUGHT. XkeyFits' body was replaced "
                   "by `ProcedureReturn 1` and every check still passed, so "
                   "this gate is not measuring the bound at all.")

    failed = sorted(i for i, (ok, _w, _s) in checks.items() if not ok)

    # Every acceptance check must STILL pass: the probe has to be
    # measuring the bound and not something else.
    still = [i for i in failed if i in ACCEPT]
    if still:
        bad.append("acceptance checks %s failed under sabotage as well - the "
                   "probe is measuring something other than the bound"
                   % still)
    arith = [i for i in failed if i in ARITHMETIC]
    if arith:
        bad.append("check(s) %s are ARITHMETIC and must answer the same in "
                   "both images; the harness changed the sum, not the guard"
                   % arith)
    if not (WITNESSES & set(failed)):
        bad.append("neither overrun witness (checks %s) fired under "
                   "sabotage. Without the bound the copy is supposed to "
                   "write past the end of the array; if it did not, the "
                   "witnesses are looking at the wrong place and the "
                   "'nothing was overwritten' half of the honest run proves "
                   "less than it claims." % sorted(WITNESSES))
    return bad, failed


# ---------------------------------------------------------------------
def resolve_compiler(requested):
    """Resolve the PureMetal compiler the way tools/build.py does."""
    sys.path.insert(0, str(ROOT / "tools"))
    import build as anvil_build  # noqa: E402
    return anvil_build.find_compiler(requested)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"),
                    help="path of PureMetalForge.exe (or set PMF_COMPILER); "
                         "it is run with --compile")
    ap.add_argument("--no-sabotage", action="store_true",
                    help="skip the negative control (do not do this in CI)")
    ap.add_argument("--jobs", type=int, default=2,
                    help="worker processes (default 2: the two images)")
    args = ap.parse_args(argv)
    globals()["PMFC"] = resolve_compiler(args.compiler)


    print("=" * 70)
    print(" THE X.509 END-ENTITY KEY BUFFER'S BOUND, ON AArch64")
    print("=" * 70)
    print("  library:  RaspberryPi4/Lib/x509.pi4  (XkeyFits, "
          "#X509ERR_KEY_BOUNDS 901)")
    print("  probe:    RaspberryPi4/Examples/Diagnostics/"
          "pi4X509KeyBoundProbe.pi4")
    print("  oracle:   tools/a64/a64_interp.py - a MODEL. Silicon is a "
          "separate claim.")
    print()

    jobs = 1 if args.no_sabotage else max(1, min(args.jobs, 2))
    if jobs > 1:
        print("  %d images on %d worker threads" % (2, jobs))
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as ex:
            f_ok = ex.submit(job_honest)
            f_sab = ex.submit(job_sabotage)
            text, g, steps, size = f_ok.result()
            stext, sg, ssteps, diff, sab_lib = f_sab.result()
    else:
        text, g, steps, size = job_honest()
        stext = sg = diff = None
        if not args.no_sabotage:
            stext, sg, ssteps, diff, sab_lib = job_sabotage()

    print("-" * 70)
    print(" THE IMAGE UNDER TEST")
    print("-" * 70)
    print("  %d bytes, %d model instructions" % (size, steps))
    print(text.rstrip())
    print()

    problems = judge_honest(text, g, size)

    if not args.no_sabotage:
        print("-" * 70)
        print(" THE NEGATIVE CONTROL - XkeyFits' body replaced by "
              "`ProcedureReturn 1`")
        print("-" * 70)
        print("  %s" % sab_lib)
        print("  %d model instructions" % ssteps)
        sbad, failed = judge_sabotage(stext, sg, diff)
        print("  xkN=%d xkBad=%d" % (sg["n"], sg["bad"]))
        print("  failed without the bound: %s" % failed)
        wit = sorted(WITNESSES & set(failed))
        if wit:
            print("  including the OVERRUN WITNESSES %s - bytes landed past "
                  "the end of a %d-byte array, in the globals next door"
                  % (wit, 520))
        problems += sbad

    print()
    if problems:
        print("X509 KEY-BOUND GATE RED")
        for p in problems:
            print("  - %s" % p)
        return 1
    print("X509 KEY-BOUND GATE GREEN: %d/%d checks on the A64 model; the "
          "bound refuses every oversized, negative and wrapping length by "
          "name and copies nothing, and every real key size still "
          "round-trips." % (g["n"], g["n"]))
    if not args.no_sabotage:
        print("  Negative control: %d of %d fail without it, every "
              "acceptance check still passes, and the overrun is witnessed."
              % (sg["bad"], sg["n"]))
    print("  NOT A SILICON RESULT. The Pi 4 pass is owed separately.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

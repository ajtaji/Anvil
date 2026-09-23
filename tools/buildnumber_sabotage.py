#!/usr/bin/env python3
# ======================================================================
#  tools/buildnumber_sabotage.py - the build number's negative controls
# ======================================================================
#
#  A GATE THAT CATCHES NOTHING HAS ABSTAINED. tools/a64/a64_anvil_check.py
#  section 7 is what stands between Anvil and a version command that
#  quietly stops carrying a build number; green on this tree proves only
#  that it passes. This breaks the tree on purpose, once per control, and
#  requires the grader to go red FOR THE NAMED REASON. Red for another
#  reason is a failure of the control.
#
#  (tools/build_count_check.py proves the counter module itself - bump,
#  stamps, ledger, lock, refusals, and exactly one marker of each kind in
#  the real board files. It does not grade the shared core carrying a
#  marker, or what `version` prints, which is what these controls break.)
#
#  Usage:
#     python tools/buildnumber_sabotage.py --compiler <PureMetalForge.exe>
#            [--only N] [--keep-going]
#  Exit 0 if every control bit, 1 if any did not, 2 if a restore failed.
#
#  THIS EDITS THE TREE IT LIVES IN. Run it from a private export copy of
#  the repository, never from a working tree other builds read: each
#  control writes one file, runs the grader, restores the exact bytes in a
#  `finally` and verifies them by SHA-256. It is serial for the same
#  reason - two controls at once would grade each other's sabotage. The
#  grader's builds are counted by tools/build_count.py like any other.
# ======================================================================

import argparse
import hashlib
import os
import re
import subprocess
import sys
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GRADER = os.path.join(HERE, "a64", "a64_anvil_check.py")

FLOW = os.path.join(ROOT, "Anvil", "Core", "flow_cmd.pbi")
UPTIME = os.path.join(ROOT, "Anvil", "Core", "uptime.pbi")
QBOARD = os.path.join(ROOT, "ArduinoQ", "Board", "board.unoq")


def sha(b):
    return hashlib.sha256(b).hexdigest()


def read(path):
    with open(path, "rb") as f:
        return f.read()


def write(path, data):
    with open(path, "wb") as f:
        f.write(data)


def nl(text):
    """The file's own line ending, so an anchor matches LF and CRLF trees."""
    return b"\r\n" if b"\r\n" in text else b"\n"


def run_grader(compiler):
    r = subprocess.run([sys.executable, GRADER, "--compiler", compiler],
                       cwd=ROOT, capture_output=True, text=True)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def plant_marker_in_the_shared_core(text):
    # A marker in Anvil/ is raised by whichever board was built last and
    # counts nothing - PMF-BLD-003. It sits on a real constant, because a
    # comment-only line is never a marker.
    n = nl(text)
    return text + (n + b"; planted by tools/buildnumber_sabotage.py - if this is"
                   + n + b"; in a committed file, the restore failed." + n
                   + b"#SABOTAGE_BUILD = 1        ; pmf:build" + n)


def machine_line_prints_zero(text):
    # The machine-readable line and the prose line are two renderings of
    # one number; a grader that only asks "is the number somewhere" passes
    # this, which is why it is a control.
    n = nl(text)
    old = b'  Print("build ")' + n + b"  PrintDec(b)" + n
    new = b'  Print("build ")' + n + b"  PrintDec(0)" + n
    if old not in text:
        return None
    return text.replace(old, new, 1)


def content_stamp_deleted(text):
    # Without the content stamp the build number stands alone as an
    # identity: it says WHICH build, never WHAT is in it. Matched by the
    # call's NAME on its own line, whatever it is passed.
    pat = re.compile(br"^[ \t]*PutContentStamp\([^)\r\n]*\)[ \t]*\r?\n", re.M)
    if not pat.search(text):
        return None
    return pat.sub(b"", text, count=1)


def two_markers_in_one_board_file(text):
    # A project has exactly one build number (PMF-BLD-002 at tree level).
    pat = re.compile(br"^(#ANVIL_BUILD = \d+[ \t]+; pmf:build[ \t]*)(\r?\n)",
                     re.M)
    m = pat.search(text)
    if not m:
        return None
    return (text[:m.end()] + b"#SECOND_BUILD = 1        ; pmf:build"
            + m.group(2) + text[m.end():])


CONTROLS = [
    dict(n=1,
         what="a build-number marker planted on a constant in the shared core "
              "(Anvil/Core/uptime.pbi)",
         path=UPTIME,
         mutate=plant_marker_in_the_shared_core,
         wants=[r"uptime\.pbi carries a build-number marker", r"PMF-BLD-003"]),
    dict(n=2,
         what="version's machine-readable line printing 0 while the prose line "
              "still prints the real number",
         path=FLOW,
         mutate=machine_line_prints_zero,
         wants=[r"machine-readable line says the build number is 0"]),
    dict(n=3,
         what="the content stamp deleted from version, leaving the build "
              "number standing alone as an identity",
         path=FLOW,
         mutate=content_stamp_deleted,
         wants=[r"prints a build number without pointing at the digest",
                r"printed no digest of the image it is running from"]),
    dict(n=4,
         what="a second build-number marker in the UNO Q's board file",
         path=QBOARD,
         mutate=two_markers_in_one_board_file,
         wants=[r"board\.unoq carries 2 build-number marker lines"]),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--only", type=int, default=0,
                    help="run just this control number")
    ap.add_argument("--keep-going", action="store_true",
                    help="do not stop at the first control that did not bite")
    args = ap.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    if not args.compiler:
        print("buildnumber_sabotage: no compiler was named. Pass --compiler "
              "with the path of PureMetalForge.exe, or set PMF_COMPILER.")
        return 2

    print("=== build-number negative controls ===")
    print("tree:   " + ROOT)
    print("grader: tools/a64/a64_anvil_check.py")
    print("Serial on purpose - every control mutates this one tree.")
    print()
    print("0. the unmutated tree must be GREEN")
    rc, out = run_grader(args.compiler)
    m = re.search(r"a64_anvil_check: PASS - (\d+) cases", out)
    if rc != 0 or not m:
        print("  FAIL the grader is not green before anything was broken, so no "
              "control below could be believed. Fix that first.")
        print(out[-4000:])
        return 1
    print("  ok   a64_anvil_check: PASS - %s cases" % m.group(1))
    print()

    bad = 0
    chosen = [c for c in CONTROLS if not args.only or c["n"] == args.only]
    for c in chosen:
        rel = os.path.relpath(c["path"], ROOT).replace("\\", "/")
        print("%d. %s" % (c["n"], c["what"]))
        print("   file: " + rel)
        original = read(c["path"])
        before = sha(original)
        mutated = c["mutate"](original)
        if mutated is None:
            print("  FAIL the control could not find what it edits in %s. The "
                  "source moved and this control has been grading nothing - "
                  "repair the control, do not delete it." % rel)
            bad += 1
            if not args.keep_going:
                return 1
            continue
        try:
            write(c["path"], mutated)
            rc, out = run_grader(args.compiler)
        finally:
            write(c["path"], original)
            after = sha(read(c["path"]))
        if after != before:
            print("  *** RESTORE FAILED on %s: before=%s after=%s. Restore it by "
                  "hand before anything else. ***" % (rel, before[:16],
                                                      after[:16]))
            return 2
        if rc == 0:
            print("  FAIL the grader stayed GREEN with this broken.")
            bad += 1
        else:
            missing = [w for w in c["wants"] if not re.search(w, out)]
            if missing:
                print("  FAIL the grader went red, but not for this reason - it "
                      "never said: " + " | ".join(missing))
                for line in out.splitlines():
                    if line.strip().startswith("FAIL"):
                        print("       it said: " + line.strip()[:200])
                bad += 1
            else:
                for line in out.splitlines():
                    if line.strip().startswith("FAIL"):
                        print("  ok   RED: " + line.strip()[:160])
                        break
        print("       restored, sha256 %s" % before[:16])
        print()
        if bad and not args.keep_going:
            return 1

    print("=== %d of %d controls bit ===" % (len(chosen) - bad, len(chosen)))
    if bad:
        print("build-number negative controls FAIL")
        return 1
    print("build-number negative controls PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# ======================================================================
#  tools/a64/anvil_identity_sabotage.py - negative controls for the
#  board-identity seam (a64_anvil_check section 8) and the width table
#  (section 9).
# ======================================================================
#
#  A GATE THAT CATCHES NOTHING HAS ABSTAINED. Sections 8 and 9 go green on
#  this tree; what has to be shown is that they go RED, for the named
#  reason, when the defects they exist to stop are put back. Both defects
#  are the quiet kind: a board printing a description of a different
#  computer, and a help sentence disagreeing with the command it
#  describes. Neither ever turns a build red.
#
#  Controls 5, 6 and 7 guard section 8b's one-definition scan, which reads
#  the tree's SOURCE (tracked plus untracked-not-ignored files, from git)
#  rather than the disk:
#    5  a second banner in a TRACKED file              must go RED
#    6  a second banner in a NEW, never-added file     must go RED
#    7  a release packager's copy of the core under
#       tools/_release_stage/                          must stay GREEN
#  Control 8 plants a board name in a printed literal BEHIND a semicolon,
#  the shape a reader that cut lines at the first `;` could not see.
#
#  Usage:
#     python tools/a64/anvil_identity_sabotage.py --compiler <exe>
#            [--only N] [--keep-going]
#  Exit 0 if every control did what it says, 1 if any did not.
#
#  THIS EDITS THE TREE IT LIVES IN. Run it from a private export copy of
#  the repository (a git work tree, because controls 5 to 7 depend on what
#  git tracks and ignores), never from a tree other builds read. Each
#  control writes or plants files, runs the grader, puts the exact bytes
#  back - absence included - and verifies them by SHA-256. Serial, because
#  controls mutating one tree at once would grade each other.
# ======================================================================
from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
GRADER = os.path.join(HERE, "a64_anvil_check.py")

HELP = os.path.join(ROOT, "Anvil", "Core", "help.pbi")
MEMCMD = os.path.join(ROOT, "Anvil", "Core", "memcmd.pbi")
QID = os.path.join(ROOT, "ArduinoQ", "Board", "hw_id_q.unoq")

# A TRACKED source that neither board file includes, so a planted banner is
# visible to the scan and invisible to both builds.
IDLE = os.path.join(ROOT, "RaspberryPi4", "Examples", "Diagnostics",
                    "pi4Idle.pi4")
# A new file under a board directory, source by any reading, not ignored.
NEWFORK = os.path.join(ROOT, "ArduinoQ", "Board", "board_banner_fork.unoq")
# What a release packager leaves behind: a copy of the core.
STAGED = os.path.join(ROOT, "tools", "_release_stage", "PureMetalForge",
                      "Anvil", "Core", "help.pbi")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def read(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def write(path: str, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)


def nl(text: bytes) -> bytes:
    return b"\r\n" if b"\r\n" in text else b"\n"


def relof(path: str) -> str:
    return os.path.relpath(path, ROOT).replace("\\", "/")


def run_grader(compiler: str) -> tuple[int, str]:
    r = subprocess.run([sys.executable, GRADER, "--compiler", compiler],
                       cwd=ROOT, capture_output=True, text=True)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                          text=True)


def is_ignored(path: str) -> bool:
    return git("check-ignore", "-q", "--", relof(path)).returncode == 0


def is_tracked(path: str) -> bool:
    return git("ls-files", "--error-unmatch", "--", relof(path)).returncode == 0


ABSENT = "absent"


def snapshot(paths: list[str]):
    out = []
    for p in paths:
        if os.path.exists(p):
            b = read(p)
            out.append((p, True, b, sha(b)))
        else:
            out.append((p, False, None, ABSENT))
    return out


def put(path: str, data: bytes) -> list[str]:
    """Write `path`, making parents. Returns the dirs made, deepest first."""
    made = []
    d = os.path.dirname(path)
    while d and not os.path.isdir(d):
        made.append(d)
        d = os.path.dirname(d)
    if made:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    write(path, data)
    return made


def undo(snap, made: list[str]) -> None:
    for p, existed, b, _ in snap:
        if existed:
            write(p, b or b"")
        elif os.path.exists(p):
            os.remove(p)
    for d in made:
        try:
            os.rmdir(d)
        except OSError:
            pass


def verify(snap):
    wrong = []
    for p, _, _, was in snap:
        now = sha(read(p)) if os.path.exists(p) else ABSENT
        if now != was:
            wrong.append((p, was, now))
    return wrong


# ----------------------------------------------------------------------
#  The controls.
# ----------------------------------------------------------------------
def board_name_back_in_the_core(text: bytes) -> bytes | None:
    """The original defect: a board's own name in a literal the SHARED
    CORE prints, in place of the banner's seam call."""
    n = nl(text)
    old = n + b"  PutIdLine()" + n
    new = (n + b'  PrintN("PureMetal Forge - Anvil, the Raspberry Pi 4 serial '
           b'monitor.")' + n)
    if old not in text:
        return None
    return text.replace(old, new, 1)


def the_q_claims_the_other_target(text: bytes) -> bytes | None:
    """A board file that answers the seam with the other board's word -
    only running the image catches it."""
    n = nl(text)
    old = b"Procedure.i HwIdTarget()" + n + b'  ProcedureReturn "unoq"' + n
    new = b"Procedure.i HwIdTarget()" + n + b'  ProcedureReturn "pi4"' + n
    if old not in text:
        return None
    return text.replace(old, new, 1)


def the_dump_is_made_to_scale(text: bytes) -> bytes | None:
    """The width table told that the dump's count scales with the suffix.
    Help and table still agree with each other, which is why section 9
    executes md.l and counts the bytes."""
    m = re.search(br"(Procedure\.i WtScales\(i\.i\).*?If i = #WT_MD\r?\n"
                  br"\s*ProcedureReturn )0", text, re.S)
    if not m:
        return None
    return text[:m.end(1)] + b"1" + text[m.end():]


def the_dump_stops_printing_its_total(text: bytes) -> bytes | None:
    """The dump prints no byte count, so a wrong count goes unnoticed."""
    n = nl(text)
    old = b'  Print("Dumped ")' + n + b"  PrintDec(got)" + n + \
        b'  Print(" bytes, ")' + n
    new = b'  Print("Dumped some memory")' + n + b"  PrintDec(0)" + n + \
        b'  Print(" ")' + n
    if old not in text:
        return None
    return text.replace(old, new, 1)


def fork(eol: bytes) -> bytes:
    return (eol + b"; Planted by tools/a64/anvil_identity_sabotage.py. If this"
            + eol + b"; is in a committed file, a control did not clean up."
            + eol + b"Procedure Banner()"
            + eol + b'  PrintN("a second banner, which the tree must not have")'
            + eol + b"EndProcedure" + eol)


def a_second_banner_in_a_tracked_file(text: bytes) -> bytes | None:
    if b"Procedure Banner()" in text:
        return None
    return text + fork(nl(text))


def plant_new_untracked_fork() -> list[tuple[str, bytes]]:
    return [(NEWFORK, fork(b"\n"))]


def plant_release_stage_copy() -> list[tuple[str, bytes]]:
    return [(STAGED, read(HELP))]


def board_name_after_a_semicolon(text: bytes) -> bytes | None:
    """A board's name in a printed literal, behind a semicolon INSIDE the
    quotes - nothing is commented out."""
    n = nl(text)
    old = b"  HwIdSayConsole()" + n + b"  PutProcessorLine()" + n
    new = (b"  HwIdSayConsole()" + n
           + b'  PrintN("Careful; this is the Raspberry Pi 4 and no other.")'
           + n + b"  PutProcessorLine()" + n)
    if old not in text:
        return None
    return text.replace(old, new, 1)


# ----------------------------------------------------------------------
#  CONTROL 9: THE RULE-12 SCAN STILL BITES.
#
#  No file in this repository holds the words the rule-12 scan refuses.
#  The grader reads them at run time from the list named by
#  PMF_ATTRIBUTION_WORDS (outside the tree), and so does this control: it
#  plants every listed word, in the form its flag says the scan must catch,
#  in one comment line of this export, and requires the grader to report
#  every entry for that file. Without the list this control FAILS rather
#  than being skipped.
# ----------------------------------------------------------------------
UPTIME = os.path.join(ROOT, "Anvil", "Core", "uptime.pbi")
WORDS_ENV = "PMF_ATTRIBUTION_WORDS"


def listed_words() -> list[tuple[str, str]] | None:
    path = os.environ.get(WORDS_ENV, "")
    if not path or not os.path.isfile(path):
        return None
    out = []
    for line in open(path, encoding="utf-8").read().splitlines():
        parts = line.split()
        if len(parts) == 2 and not line.lstrip().startswith("#"):
            out.append((parts[0], parts[1]))
    return out or None


def planted_form(flag: str, word: str) -> str:
    """The spelling the scan's rule for this flag must still catch."""
    if flag == "capitalised":
        return word.capitalize()
    if flag == "capitals":
        return word.upper()
    return "my%sLexer" % word.upper()      # inside an identifier, other case


def plant_listed_words(text: bytes) -> bytes | None:
    words = listed_words()
    if words is None:
        return None
    line = "; planted by anvil_identity_sabotage control 9: " + ", ".join(
        planted_form(f, w) for f, w in words)
    return text + line.encode("utf-8") + nl(text)


def control9_wants() -> list[str]:
    words = listed_words() or []
    # One planted line, one hit per listed entry.
    return ([r"attribution: FAIL - %d lines" % len(words)] +
            [r"word-%s +Anvil/Core/uptime\.pbi:\d+" % f
             for f in sorted({f for f, _ in words})])


CONTROLS = [
    dict(n=1, what="a board's own name printed from the SHARED CORE, put "
                   "back in the banner",
         path=HELP, mutate=board_name_back_in_the_core,
         wants=[r"help\.pbi prints a board's own name from the SHARED CORE",
                r"Raspberry Pi 4"]),
    dict(n=2, what="the UNO Q's board file answering HwIdTarget with the "
                   "OTHER board's target word",
         path=QID, mutate=the_q_claims_the_other_target,
         wants=[r"the UNO Q's version says 'pi4', which is the other board",
                r"the UNO Q's version does not say 'for target unoq'"]),
    dict(n=3, what="the width table told that the memory dump's count scales "
                   "with the suffix, which it does not",
         path=MEMCMD, mutate=the_dump_is_made_to_scale,
         wants=[r"md\.l with a count of 8 touched 8 bytes and the width "
                r"table says it should touch 32"]),
    dict(n=4, what="the memory dump stops printing its byte total",
         path=MEMCMD, mutate=the_dump_stops_printing_its_total,
         wants=[r"md.* printed no byte total"]),
    dict(n=5, what="a SECOND banner in a TRACKED file",
         path=IDLE, mutate=a_second_banner_in_a_tracked_file,
         must_be_tracked=[IDLE],
         wants=[r"the tree defines the banner in 2 places", r"pi4Idle\.pi4"]),
    dict(n=6, what="a SECOND banner in a NEW file, written but never added",
         plant=plant_new_untracked_fork, must_not_be_ignored=[NEWFORK],
         wants=[r"the tree defines the banner in 2 places",
                r"board_banner_fork\.unoq"]),
    dict(n=7, what="a release packager's copy of the core under "
                   "tools/_release_stage - the false positive, which must "
                   "NOT come back",
         plant=plant_release_stage_copy, expect="green"),
    dict(n=8, what="a board's own name in a printed literal BEHIND A "
                   "SEMICOLON",
         path=HELP, mutate=board_name_after_a_semicolon,
         wants=[r"help\.pbi prints a board's own name from the SHARED CORE",
                r"Careful; this is the Raspberry Pi 4"]),
    dict(n=9, what="every word on the external rule-12 list planted in a "
                   "core comment - the scan must report each rule",
         path=UPTIME, mutate=plant_listed_words, wants=None),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--only", default="",
                    help="run just these control numbers, e.g. 5 or 5,9")
    ap.add_argument("--keep-going", action="store_true",
                    help="do not stop at the first control that did not bite")
    args = ap.parse_args()
    only = {int(x) for x in args.only.split(",") if x.strip()}
    if not args.compiler:
        print("anvil_identity_sabotage: no compiler was named. Pass --compiler "
              "with the path of PureMetalForge.exe, or set PMF_COMPILER.")
        return 2
    if git("rev-parse", "--is-inside-work-tree").returncode != 0:
        print("anvil_identity_sabotage: %s is not a git work tree, and controls "
              "5 to 7 are about what git tracks and ignores. Run this from a "
              "git export of the repository." % ROOT)
        return 2

    print("=== board-identity and width-table negative controls ===")
    print("tree:   " + ROOT)
    print("grader: tools/a64/a64_anvil_check.py")
    print("Serial on purpose - every control mutates this one tree.")
    print()
    print("0. the unmutated tree must be GREEN")
    rc, out = run_grader(args.compiler)
    m = re.search(r"a64_anvil_check: PASS - (\d+) cases", out)
    if rc != 0 or not m:
        print("  FAIL the grader is not green before anything was broken, so "
              "no control below could be believed. Fix that first.")
        print(out[-4000:])
        return 1
    print("  ok   a64_anvil_check: PASS - %s cases" % m.group(1))
    print()

    bad = 0
    for c in CONTROLS:
        if only and c["n"] not in only:
            continue
        print("%d. %s" % (c["n"], c["what"]))
        if "plant" in c:
            targets = c["plant"]()
        else:
            mutated = c["mutate"](read(c["path"]))
            if mutated is None:
                print("   file: " + relof(c["path"]))
                if c["n"] == 9 and listed_words() is None:
                    print("   FAIL %s does not name a readable word list, so "
                          "there is nothing to plant and the rule-12 scan was "
                          "not proven to bite. Set it to the list file and "
                          "run this control again." % WORDS_ENV)
                else:
                    print("   FAIL the control could not be applied - the text "
                          "it edits is not in that file any more. Repair the "
                          "control, do not delete it.")
                bad += 1
                if not args.keep_going:
                    return 1
                continue
            targets = [(c["path"], mutated)]
        for path, _ in targets:
            print("   file: " + relof(path))

        problems = ["%s is ignored by .gitignore, so planting there proves "
                    "nothing" % relof(p)
                    for p in c.get("must_not_be_ignored", []) if is_ignored(p)]
        problems += ["%s is not tracked by git, so it cannot stand for a "
                     "tracked file" % relof(p)
                     for p in c.get("must_be_tracked", []) if not is_tracked(p)]
        if problems:
            print("   FAIL " + "; ".join(problems) + ". Move the control's "
                  "file, do not delete the control.")
            bad += 1
            if not args.keep_going:
                return 1
            continue

        snap = snapshot([p for p, _ in targets])
        made: list[str] = []
        try:
            for path, data in targets:
                made = put(path, data) + made
            rc, out = run_grader(args.compiler)
        finally:
            undo(snap, made)
            wrong = verify(snap)
            if wrong:
                print("   !! THE RESTORE FAILED. The tree is NOT what it was.")
                for p, was, now in wrong:
                    print("      %s  before %s  after %s" % (relof(p), was, now))
        if wrong:
            return 1

        digests = ", ".join(s[:16] for _, _, _, s in snap)
        if c.get("expect", "red") == "green":
            if rc == 0:
                print("   ok   GREEN, as a correct tree must be. %s restored"
                      % digests)
            else:
                print("   FAIL the grader went RED on a tree with nothing wrong "
                      "with it. The false positive is back.")
                for line in out.splitlines():
                    if line.strip().startswith("FAIL"):
                        print("   " + line.strip())
                bad += 1
        elif rc == 0:
            print("   FAIL the grader stayed GREEN with that broken.")
            bad += 1
        else:
            wants = c["wants"] if c["wants"] is not None else control9_wants()
            missing = [w for w in wants if not re.search(w, out)]
            if missing:
                print("   FAIL the grader went red, but not for the named "
                      "reason. Missing: %s" % "; ".join(missing))
                for line in out.splitlines():
                    if line.strip().startswith("FAIL"):
                        print("   " + line.strip())
                bad += 1
            else:
                print("   ok   RED, for the named reason. %s restored"
                      % digests)
        print()
        if bad and not args.keep_going:
            return 1

    if bad:
        print("%d control(s) did not bite." % bad)
        return 1
    print("every control bit, and every file was restored by SHA-256.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

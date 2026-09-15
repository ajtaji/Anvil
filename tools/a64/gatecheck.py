#!/usr/bin/env python3
"""A GATE THAT EXAMINED NOTHING HAS NOT PASSED - IT HAS ABSTAINED.

A checking tool usually ends the same way:

    return 1 if problems else 0

which is correct right up until the collection it was checking comes back
EMPTY. Then there are no problems, because there was no work: the loop body
never ran, and the tool prints its success line having verified nothing at
all. The denominator went to zero and the verdict stayed green.

The shapes this takes in practice are ordinary: an emulator budget too
short for the program to print anything, so empty output is compared with
empty output; a tally of PASS lines that stays the same across a change
that makes the program crash after its last PASS; a reference build that
fails to resolve its includes on both sides of an A/B, so both sides record
"no build" and the sweep reports everything unchanged.

HOW TO USE IT. Count what you actually examined, and say so before you are
allowed to succeed:

    from gatecheck import examined
    ...
    examined(len(cases), "boot container cases", minimum=3)
    return 1 if problems else 0

THE EXIT CODE IS DELIBERATELY NOT 1. A gate that failed found something
wrong; a gate that abstained found nothing to look at, which is a broken
harness, a bad path or a moved corpus - a different problem needing a
different fix. Anything scripting these tools should treat 2 as "this told
you nothing" rather than folding it into "failed".
"""
import sys

#: exit status for "this gate could not do its job" - NOT the same as failing
GATE_ABSTAINED = 2


def examined(count, what, minimum=1, hint=""):
    """Assert the gate actually looked at `count` of `what`, else abstain.

    Returns count so it can be used inline. Raises SystemExit(2) - loudly,
    naming what it expected - when there was not enough to check.
    """
    if count >= minimum:
        return count

    print("", file=sys.stderr)
    print("*** GATE ABSTAINED - it examined %d %s and expected at least %d."
          % (count, what, minimum), file=sys.stderr)
    print("    This is NOT a pass. Nothing was verified, so nothing is known.",
          file=sys.stderr)
    if hint:
        print("    %s" % hint, file=sys.stderr)
    print("    Usual causes: run from the wrong directory, a corpus that "
          "moved,", file=sys.stderr)
    print("    or a build/run step that failed so quietly the loop had no "
          "input.", file=sys.stderr)
    print("    See tools/a64/gatecheck.py for why this check exists.",
          file=sys.stderr)
    raise SystemExit(GATE_ABSTAINED)


def _selftest():
    """Prove the guard fires. A guard nobody has seen fail is a guess."""
    ok = 0

    if examined(5, "things", minimum=1) == 5:
        ok += 1

    try:
        examined(0, "things", minimum=1)
        print("FAIL: examined(0) did not abstain")
    except SystemExit as e:
        if e.code == GATE_ABSTAINED:
            ok += 1
        else:
            print("FAIL: wrong exit code %r" % (e.code,))

    # SOME work but less than the floor - the partial case, which is the
    # one a bare "> 0" test would wave through.
    try:
        examined(3, "things", minimum=17)
        print("FAIL: examined(3, minimum=17) did not abstain")
    except SystemExit as e:
        if e.code == GATE_ABSTAINED:
            ok += 1

    print("gatecheck selftest: %d/3" % ok)
    return 0 if ok == 3 else 1


if __name__ == "__main__":
    raise SystemExit(_selftest())

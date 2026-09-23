#!/usr/bin/env python3
"""a64_toolout_check.py - a tool that relays a board's output cannot die on it.

WHAT THIS GATE IS FOR

Every host tool here that talks to a board decodes the board's reply with
errors="replace", so a mangled byte becomes U+FFFD and the DECODE cannot
throw. Writing it is the other half: a Windows console is cp1252, cp1252
has no U+FFFD, and print() raises UnicodeEncodeError. The tool dies
holding the board's answer.

It has happened twice, both times at the worst possible seam - inside a
flash, after the image was written and before the reset was sent:

  * 2026-09-07  anvil_update.py
  * 2026-09-08  pi4_upload.py

The first was fixed by pasting a block into that one file. That is why
the second happened: "somebody remembers to paste it" is not a property
anything can check, and these tools are written independently with no
shared base class. tools/console_out.py is the one home now, and this
gate is the thing that checks - so the third tool cannot be added
without it.

WHAT IT ASSERTS

  1. console_out.relay_safe_output exists, and actually makes a stream
     that would raise stop raising. Asserted by BEHAVIOUR against a
     cp1252 stream carrying U+FFFD - the exact byte and codec of both
     failures - not by looking for the word "reconfigure".
  2. Every tool that relays board output imports it and calls it.
  3. It calls it BEFORE the tool's own work, so the protection is in
     place for the first thing printed.
  4. No tool carries a private copy of the block any more. A second copy
     is how the fix drifts back out of one of them.
  5. relay_safe_output is safe on streams that cannot be reconfigured -
     a redirected stream, a test double - because a tool must not be
     broken BY its output handling either.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)

# THE TOOLS THAT RELAY A BOARD'S CONSOLE OUTPUT.
#
# Membership is by JOB, not by whether the file currently passes: these
# are the tools that print bytes that came off a board. A new one goes in
# this list when it is written. The list is deliberately not derived by
# grepping for "decode(", because most decode() calls here read FILES,
# and a gate whose scope drifts with an unrelated grep is a gate nobody
# can read the verdict of.
RELAYS = [
    "anvil.py",              # the serial console reader
    "anvil_wifi.py",         # the UDP console reader
    "anvil_wifi_update.py",  # flashes over the radio/cable, chunked
    "anvil_update.py",       # flashes over the serial line
    "pi4_upload.py",         # flashes over the network, `net recv`
    "pi4_say.py",            # one network console command, answer printed
]

CASES = []


def check(name, ok, detail=""):
    CASES.append((name, bool(ok), detail))


def read(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


# ----------------------------------------------------------------------
# 1. THE HELPER ACTUALLY WORKS, PROVED AGAINST THE FAILING CODEC
# ----------------------------------------------------------------------
def case_helper_behaviour():
    try:
        from console_out import relay_safe_output
    except ImportError as exc:
        check("console_out.relay_safe_output imports", False, str(exc))
        return
    check("console_out.relay_safe_output imports", True)

    # The negative control FIRST: prove the stream under test really does
    # raise before the helper touches it. Without this the positive case
    # could pass on a stream that was never capable of failing, which is
    # how a gate quietly stops testing anything.
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252", errors="strict")
    raised = False
    try:
        stream.write("�")
        stream.flush()
    except UnicodeEncodeError:
        raised = True
    check("negative control: a cp1252 stream DOES raise on U+FFFD", raised,
          "if this is green the positive case below proves nothing")

    raw2 = io.BytesIO()
    stream2 = io.TextIOWrapper(raw2, encoding="cp1252", errors="strict")
    done = relay_safe_output([stream2])
    check("relay_safe_output reports the stream it fixed", len(done) == 1,
          "returned %r" % (done,))
    ok = True
    detail = ""
    try:
        stream2.write("board said �� and a degree sign \xb0")
        stream2.flush()
    except UnicodeEncodeError as exc:
        ok, detail = False, str(exc)
    check("after relay_safe_output the same write does not raise", ok, detail)

    # 5. it must not itself break a stream it cannot reconfigure.
    class NoReconfigure:
        def write(self, _):
            return 0

    ok = True
    detail = ""
    try:
        got = relay_safe_output([NoReconfigure(), None])
        ok = (got == [])
        detail = "returned %r, expected []" % (got,)
    except Exception as exc:                     # noqa: BLE001 - that is the point
        ok, detail = False, "raised %r" % (exc,)
    check("a stream that cannot be reconfigured is skipped, not fatal",
          ok, detail)


# ----------------------------------------------------------------------
# 2-4. EVERY RELAY IMPORTS IT, CALLS IT EARLY, AND KEEPS NO PRIVATE COPY
# ----------------------------------------------------------------------
PRIVATE_COPY = re.compile(r"\.reconfigure\s*\(\s*encoding\s*=")


def case_relays():
    for name in RELAYS:
        path = os.path.join(TOOLS, name)
        if not os.path.exists(path):
            check("%s exists" % name, False, path)
            continue
        src = read(path)

        imports = "from console_out import relay_safe_output" in src
        check("%s imports relay_safe_output" % name, imports)

        call = re.search(r"^relay_safe_output\(\)", src, re.M)
        check("%s calls relay_safe_output()" % name, bool(call))

        # 3. BEFORE the tool's own work. The test is that the call comes
        # before the first def/class in the file - i.e. it runs at import
        # time, not somewhere inside main() that an early error path
        # could get in front of.
        if call:
            first_def = re.search(r"^(def|class)\s", src, re.M)
            early = (first_def is None) or (call.start() < first_def.start())
            check("%s calls it before its first def/class" % name, early,
                  "the first thing printed must already be protected")

        # 4. and no private copy of the block survives anywhere.
        stray = PRIVATE_COPY.search(src)
        check("%s keeps no private copy of the reconfigure block" % name,
              stray is None,
              "" if stray is None else "at offset %d" % stray.start())


def main():
    case_helper_behaviour()
    case_relays()

    bad = [c for c in CASES if not c[1]]
    for name, ok, detail in CASES:
        if not ok:
            print("  FAIL %s%s" % (name, (" - " + detail) if detail else ""))
    if bad:
        print("a64_toolout_check: FAIL - %d of %d cases" % (len(bad), len(CASES)))
        print("           A host tool that relays a board's output can die on "
              "the output again.")
        print("           Fix: import relay_safe_output from tools/console_out.py "
              "and call it at import time.")
        return 1
    print("a64_toolout_check: PASS - %d cases, %d relaying tools" %
          (len(CASES), len(RELAYS)))
    print("           The negative control confirms a cp1252 stream really "
          "does raise on U+FFFD,")
    print("           so the positive cases are measuring something. Every "
          "relaying tool imports the")
    print("           one helper, calls it before its first def, and keeps no "
          "private copy of it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""console_out.py - a tool that relays a board's output must not die on it.

WHY THIS EXISTS, AND WHAT IT COST TWICE

A board's console reply arrives as bytes. Every reader here decodes with
errors="replace", so a byte the wire mangled - a serial burst on the
known ground loop, a clobbered string in the monitor's own image, a
degree sign emitted in a code page nobody agreed on - becomes U+FFFD and
the DECODE cannot throw. That is only half the round trip. WRITING it is
the half that throws: a Windows console is cp1252 by default, cp1252
cannot represent U+FFFD, and print() raises UnicodeEncodeError.

The failure is at its worst in exactly the place it keeps happening: a
flashing tool, between the save and the reset. The image is already on
the medium and correct, the board is waiting, and the only thing on the
screen is a traceback from the print statement - so the reset never goes,
and the next reader has to work out from the source which commands were
sent before the exception and which were not.

  * 2026-09-07 it killed anvil_update.py that way. The fix was written
    into that one file.
  * 2026-09-08 it killed pi4_upload.py at the same seam, at the line that
    prints what `save` replied - one line after the save had returned and
    one line before `reset` would have been sent. The board sat running a
    monitor it was in the middle of replacing.

The second one is the reason this is a module and not a third copy of the
block. A defect that is fixed per-file is fixed in the files somebody
remembered; the tools here that speak to a board are written
independently and do not share a base class, so "remember to paste it"
is not a property anything can check. Importing this is one line, and
`a64_toolout_check.py` asserts that every tool which relays board output
does it.

USE

    from console_out import relay_safe_output
    relay_safe_output()

Call it once, at import time, before anything is printed.

The reconfiguration is guarded: .reconfigure arrived in 3.7, and a
stream that has been redirected to something without it must not turn a
working tool into a broken one. Both platforms, which is house rule 14.
"""
import sys


def relay_safe_output(streams=None):
    """Make this process's output streams incapable of raising on a
    character they cannot represent.

    Returns the list of streams actually reconfigured, so a caller - or a
    gate - can tell "there was nothing to do" from "it did not work".
    """
    if streams is None:
        streams = (sys.stdout, sys.stderr)
    done = []
    for stream in streams:
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            # AttributeError: not a TextIOWrapper (a redirected stream, a
            # test double). ValueError: already detached. Neither is a
            # reason to stop the tool - the point of this module is that
            # output handling never becomes the thing that fails.
            continue
        done.append(stream)
    return done

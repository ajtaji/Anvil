#!/usr/bin/env python3
"""anvil_update.py - replace Anvil with a new build, from Anvil.

    python tools/anvil_update.py [image]

No U-Boot, no second machine, no pulling the stick. The running monitor
receives the new image over the serial line, writes it to the file it
boots from, and resets into it:

    receive 400000 <len> <crc>
    save KERNEL8.IMG 400000 <len>
    reset

THE FILE IS RESIZED TO THE IMAGE. The length is passed to `save`, so the
monitor grows or shrinks the boot file to the exact image size - the
image is NOT padded to a fixed slot. fat.pi4 does the resize in place.

IT CAN GO AT 1.5 Mbaud (pass --fast); 115200 takes about a minute for a
~1 MB image. The monitor's baud command moves both ends and reverts by
itself if the host cannot follow. The default leaves the baud alone (see
the note in main).
"""
import os
import sys
import time
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from anvil import Anvil, stage_help

SLOT_NAME = "KERNEL8.IMG"

# STAGE IS NOT A CONSTANT ANY MORE - 2026-09-08. It was 0x400000 here and
# in three other tools; the board is asked instead, because the monitor's
# extent is now the size of its own image and the address above it moves
# with it. See WHERE THE BOARD WANTS A FILE PUT in tools/anvil.py.

# ----------------------------------------------------------------------
# THIS TOOL PRINTS WHAT THE BOARD SAID, AND A SERIAL LINE GARBLES BURSTS.
#
# This block used to live here in full, written on 2026-09-07 when it
# killed this tool between the save and the reset. On 2026-09-08 the SAME
# defect killed pi4_upload.py at the same seam, because the fix had been
# made a property of one FILE rather than of the job. It is a module now
# and the tools that relay board output all import it.
# ----------------------------------------------------------------------
from console_out import relay_safe_output   # noqa: E402

relay_safe_output()


def main():
    # AN UNRECOGNISED OPTION IS A STOP (tid 502's shape, swept 2026-09-03).
    # `--fast` was matched by scanning the whole argv, so `--fst` or
    # `--Fast` was silently dropped and the write went ahead at 115200
    # while the invocation looked like the fast one. Anything starting
    # with `-` that is not `--fast` now refuses before a byte is sent.
    positional = []
    for a in sys.argv[1:]:
        if a == "--fast":
            continue
        if a.startswith("-"):
            print("!! not an option this tool knows: %s" % a)
            print(__doc__)
            return 2
        positional.append(a)
    if len(positional) > 1:
        print("!! one image at a time; did not expect: %s" % positional[1])
        print(__doc__)
        return 2

    src = positional[0] if positional else os.path.join(REPO, "build", "pi4", "anvil.img")
    img = open(src, "rb").read()
    tmp = src
    print("%s: %d bytes" % (src, len(img)))

    a = Anvil()
    try:
        if a.prompt() != "pmf":
            print("no Anvil prompt - is it running?")
            return 1
        a.settle()
        # THE BAUD IS LEFT ALONE. Ruled 2026-08-28: "you're crashing the
        # pi 4 leave the baud alone" - and the ruling is right, two saves in a
        # row died at "SAVE DID NOT COMPLETE" with 1.5 Mbaud in the
        # middle of them. Pass --fast to opt back in; the default is the
        # rate the board booted at, which is the one that finishes.
        fast = False
        if "--fast" in sys.argv:
            fast = a.setbaud(1500000)
            print("1.5 Mbaud" if fast else "115200 (the adapter would not go faster)")
        else:
            print("115200 - the baud is not touched (pass --fast to change it)")

        # WHERE TO PUT IT, FROM THE BOARD. Asked here rather than at the
        # top of main() because it needs a prompt, and asked before the
        # transfer rather than after because a monitor that will not say
        # is a run that must not start: the alternative is sending two
        # megabytes and then discovering there is nowhere to put them.
        stage = a.stage_addr()
        if stage is None:
            print(stage_help("the image"))
            return 1
        print("staging at %08X, which is where this board said to put it"
              % stage)

        t0 = time.time()
        out = a.block(tmp, stage)
        if "ok" not in out or "crc" in out:
            print("the transfer did not verify:")
            print(out[-400:])
            return 1
        print("received %d bytes in %.1f s, CRC verified on the board"
              % (len(img), time.time() - t0))

        if fast:
            a.setbaud(115200)
        a.settle()

        # The length goes with it, so the file is resized to the image
        # rather than the image being padded to the file.
        out = a.cmd("save %s %X %X" % (SLOT_NAME, stage, len(img)), 90)
        print(out.strip())
        if "written." not in out:
            print("SAVE DID NOT COMPLETE - not resetting.")
            print("The file may be part old and part new; write it again")
            print("before the board is reset, or it boots half an image.")
            return 1

        # ------------------------------------------------------------------
        # ASK THE FILE SYSTEM, NOT THE COMMAND THAT WROTE IT.
        #
        # `save` saying "written." is that command's own account of itself,
        # and the one question that actually matters afterwards - is the file
        # the firmware will load now the length of the image we sent - is
        # answered by the directory and by nothing else. Reading it back
        # costs one command and one line of output, and the alternative is
        # resetting into a file nobody has looked at.
        #
        # HOW THIS WAS EARNED, 2026-09-07: this tool crashed printing a
        # non-ASCII byte out of the board's reply, AFTER the save had landed
        # and BEFORE the reset. The save was fine and the operator could not
        # tell, because there was nothing to look at that was not the
        # traceback. The serial line on this bench garbles bursts (the panel
        # ground loop), so the length is matched out of whatever came back
        # rather than the line being parsed by position.
        #
        # A MISMATCH IS NOT A RESET. A file that is not the length we sent is
        # a file that is part old and part new, and the one thing that must
        # not follow that is a boot.
        want = str(len(img))
        out = a.cmd("ls", 20)
        line = ""
        for ln in out.splitlines():
            if SLOT_NAME.lower() in ln.lower():
                line = ln.strip()
                break
        if not line:
            print("!! %s is not in the directory listing after the save, so"
                  % SLOT_NAME)
            print("   NOT resetting. The board is still running the old image")
            print("   and the stick still has whatever it had. Type ls on the")
            print("   console to see what is actually there.")
            print(out[-400:])
            return 1
        print("  " + line)
        if want not in line.replace(",", ""):
            print("!! %s is %s and the image sent was %s bytes, so the file on"
                  % (SLOT_NAME, line, want))
            print("   the stick is NOT the image that was just sent. NOT")
            print("   resetting - write it again before the board is reset, or")
            print("   it boots part of one image and part of another.")
            return 1
        print("  %s is %s bytes on the stick, which is the image that was sent."
              % (SLOT_NAME, want))

        print()
        print("resetting into the new build ...")
        a.settle()
        a.s.write(b"reset\r")
        print(a.grab(40))
    finally:
        a.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

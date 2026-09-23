#!/usr/bin/env python3
"""anvil.py - drive Anvil over the serial line, reliably.

Written after three ad-hoc test scripts each got the timing wrong in a
different way and produced a wrong verdict about the board. The two
mistakes worth naming, because both LOOKED like hardware faults:

  * a "quiet timeout" that extends on every byte SHORTENS the window
    when the thing you are waiting for is silence followed by output.
    A board mid-reset is silent for several seconds while the firmware
    reloads, so a 6 s quiet timer declared "no reboot" on a board that
    was in fact rebooting.
  * reconnecting after a reset misses the U-Boot banner entirely, so
    "did it reset" has to be answered from whatever is still scrolling -
    which was U-Boot's MMC retry loop, easy to misread as a hang.

So: capture for a FIXED wall-clock window, never an adaptive one, and
decide from the whole transcript.

  python tools/anvil.py boot                      - get to a prompt, load Anvil
  python tools/anvil.py run IMG ADDR [cmds...]    - load an image and go
  python tools/anvil.py cmd  CMD [CMD...]         - send commands
  python tools/anvil.py watch SECONDS             - listen only
"""
import os
import re
import sys, time, zlib, serial

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# THIS MODULE IS THE SERIAL CONSOLE READER, so everything it hands back
# came off a board, and a burst on this bench's known ground loop garbles
# it. Decoding cannot throw; printing it can. See console_out.py for the
# two flashes this killed.
from console_out import relay_safe_output   # noqa: E402

relay_safe_output()

PORT = "COM7"
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MON = os.path.join(REPO, "build", "pi4", "anvil.img")
MON_ADDR = 0x200000



# =====================================================================
#  WHERE THE BOARD WANTS A FILE PUT - ASKED, NOT ASSUMED
# =====================================================================
#  Every tool in this tree used to carry 0x400000 as a constant of its
#  own: DEFAULT_ADDR in pi4_upload.py and STAGE in anvil_update.py,
#  anvil_wifi_update.py and anvil_putfile.py.  Four copies of one number
#  on the far side of a cable, none of which could find out it had
#  changed.
#
#  It changed on 2026-09-08.  The ruling that day was that Anvil is a
#  kernel and may be as big as it wants, so the monitor's extent is now
#  the size of the image and the low payload window begins above it -
#  which means the staging address MOVES when the monitor crosses a
#  megabyte boundary.  A tool holding a stale constant would aim a file
#  at the running monitor.  It would be refused, loudly, by
#  HitsMonitor() - so nothing would be destroyed - but the tool would
#  fail for a reason its own message could not explain.
#
#  So the board is asked, the same way a U-Boot script reads $loadaddr
#  with printenv rather than assuming one.  `map` prints one line
#
#      stage a file at 00400000               which is what ...
#
#  and this is the only place in the tree that knows that.  The parse is
#  a pure function of the text so that each tool can obtain the text over
#  whatever transport it has - a serial line, a UDP console - and there
#  is still one reader.
#
#  IT RETURNS None RATHER THAN GUESSING.  A monitor too old to have `map`
#  answers nothing, and a tool that fell back to 0x400000 there would be
#  reintroducing the constant with an extra step.  Each caller says what
#  it needs and stops.
#
#  ONE QUESTION, NOT TWO.  `map` also prints the extent of the running
#  image, on the line above:
#
#      this image      00200000 to 003FCBCF   2083792 bytes, measured ...
#      stage a file at 00400000               which is what ...
#
#  and a tool that stages a file needs BOTH - where to put it, and what
#  it must not land on when somebody passes an address by hand.  Those
#  two facts come out of one answer to one command, because they are one
#  fact: the staging address IS the first megabyte above that extent.
#  Asking `version` for the extent and `map` for the address would be two
#  round trips that can disagree - a monitor could be replaced between
#  them - and two parsers to keep in step with the monitor's prose.  So
#  read_map() returns the whole record and stage_from_map() is the narrow
#  accessor on top of it for the callers that only place a file.
# =====================================================================
STAGE_LINE = re.compile(r"stage a file at\s+([0-9A-Fa-f]{8,16})")
IMAGE_LINE = re.compile(r"this image\s+([0-9A-Fa-f]{8,16})\s+to\s+"
                        r"([0-9A-Fa-f]{8,16})\s+(\d+)\s+bytes")
PAY_WINDOW_LINE = re.compile(r"(?:the low window|the high window|window\s+\d+)\s+"
                             r"([0-9A-Fa-f]{8,16})\s+to\s+"
                             r"([0-9A-Fa-f]{8,16})", re.I)


class BoardMap(object):
    """What `map` said: where a file goes, and where the monitor is.

    `stage` is never None - read_map() returns None instead of a record
    with nothing in it.  `image_lo`/`image_hi`/`image_bytes` are None on
    a monitor that prints a staging address without its own extent; a
    caller that needs them says so and stops rather than assuming the
    image is somewhere.
    """

    def __init__(self, stage, image_lo=None, image_hi=None, image_bytes=None,
                 payload_windows=()):
        self.stage = stage
        self.image_lo = image_lo
        self.image_hi = image_hi
        self.image_bytes = image_bytes
        self.payload_windows = tuple(payload_windows)

    def hits_image(self, addr, length):
        """Would `length` bytes at `addr` land on the running monitor?

        None when the board did not say where its image is, which is not
        the same answer as False and must not be printed as one: see the
        board that stayed reachable and stopped understanding commands,
        2026-09-08.
        """
        if self.image_lo is None or self.image_hi is None:
            return None
        return addr <= self.image_hi and addr + length - 1 >= self.image_lo


def read_map(text):
    """The whole of `map`'s answer, or None if it did not answer."""
    m = STAGE_LINE.search(text or "")
    if not m:
        return None
    rec = BoardMap(int(m.group(1), 16),
                   payload_windows=[(int(a, 16), int(b, 16))
                                    for a, b in PAY_WINDOW_LINE.findall(text or "")])
    i = IMAGE_LINE.search(text or "")
    if i:
        rec.image_lo = int(i.group(1), 16)
        rec.image_hi = int(i.group(2), 16)
        rec.image_bytes = int(i.group(3))
    return rec


def stage_from_map(text):
    """The staging address out of `map`'s output, or None."""
    rec = read_map(text)
    return None if rec is None else rec.stage


def stage_help(what="the file"):
    """What to print when the board would not say. One sentence with the
    numeric fact in it, per the errors-are-full-sentences rule."""
    return ("!! the board did not answer `map` with a staging address, so "
            "there is nowhere" + "\n" +
            "   to put %s. A monitor built before 2026-09-08 has no `map` "
            "command:" % what + "\n" +
            "   check its actual running image and reserved ranges "
            "before choosing an" + "\n" +
            "   explicit address. Do not assume the old 0x400000 "
            "address is safe. Nothing was sent.")

def srec(data, base):
    recs = []
    for off in range(0, len(data), 32):
        c = data[off:off + 32]
        a = base + off
        n = len(c) + 5
        s = n + sum((a >> k) & 0xFF for k in (0, 8, 16, 24)) + sum(c)
        recs.append("S3%02X%08X%s%02X" % (n, a, c.hex().upper(), (~s) & 0xFF))
    s = 5 + sum((base >> k) & 0xFF for k in (0, 8, 16, 24))
    recs.append("S705%08X%02X" % (base, (~s) & 0xFF))
    return recs


class Anvil:
    def __init__(self, port=PORT):
        self.s = serial.Serial(port, 115200, timeout=0.3)
        self.s.dtr = False
        self.s.rts = False
        self.log = []

    def grab(self, seconds):
        """Capture for a FIXED window. Never adaptive - see the header."""
        end = time.time() + seconds
        out = ""
        while time.time() < end:
            c = self.s.read(4096)
            if c:
                out += c.decode("utf-8", "replace")
        self.log.append(out)
        return out

    def settle(self, quiet=1.2, cap=20):
        """Read until the line has been silent for `quiet` seconds.

        The board can still be draining a previous command's output when
        the next one is sent - a bare `h` is forty lines - and a command
        written into that backlog gets interleaved with it. That is how a
        `b` header line went missing and the binary payload behind it was
        read as commands: the log showed `pmf> l` and `pmf> k`, which are
        not commands anyone typed, they are bytes of an image.

        So: never write to this board without settling first.
        """
        end = time.time() + cap
        last = time.time()
        got = ""
        while time.time() < end and time.time() - last < quiet:
            c = self.s.read(4096)
            if c:
                got += c.decode("utf-8", "replace")
                last = time.time()
        self.s.reset_input_buffer()
        return got

    def prompt(self, timeout=240):
        """Return 'pmf', 'uboot' or None. Taps CR to interrupt autoboot."""
        t0 = time.time()
        tail = b""
        while time.time() - t0 < timeout:
            self.s.write(b"\r")
            time.sleep(0.08)
            c = self.s.read(512)
            if c:
                tail = (tail + c)[-64:]
                if b"pmf>" in tail:
                    return "pmf"
                if b"U-Boot>" in tail:
                    return "uboot"
        return None

    def load_monitor(self):
        p = self.prompt()
        if p == "pmf":
            self.settle()
            return "already up"
        if p is None:
            raise SystemExit("no prompt at all - is the board powered?")
        self.s.reset_input_buffer()
        self.s.write(b"loads\r")
        time.sleep(0.6)
        self.grab(2)
        data = open(MON, "rb").read()
        for r in srec(data, MON_ADDR):
            self.s.write(r.encode() + b"\r\n")
            time.sleep(0.004)
        time.sleep(1.0)
        self.grab(3)
        self.s.write(b"go 0x%X\r" % MON_ADDR)
        return self.grab(7)

    def setbaud(self, rate):
        """Move both ends to a new rate. Returns True if it stuck.

        THE BOARD AUTO-REVERTS, which is what makes this safe to try. It
        switches, waits eight seconds for the host to say anything at the
        new rate, and puts 115200 back if nobody does. A rate the adapter
        cannot manage costs a pause, not a power cycle.

        The confirming byte has to arrive AT THE NEW RATE - that is the
        entire handshake. Sending it before reopening the port confirms
        nothing and the board reverts.
        """
        self.settle()
        self.s.write(("baud %d\r" % rate).encode())
        # Let the announcement finish at the OLD rate before touching the
        # port - the divisor changes immediately after it.
        time.sleep(1.0)
        self.s.baudrate = rate
        time.sleep(0.2)
        self.s.reset_input_buffer()
        self.s.write(b"\r")
        out = self.grab(3)
        if "pmf>" in out or "kept" in out:
            return True
        # It did not take. The board is on its way back to 115200; follow.
        self.s.baudrate = 115200
        time.sleep(9)
        self.s.reset_input_buffer()
        return False

    def block(self, path, addr):
        """Anvil's fast loader. Returns the transcript; check for 'ok'."""
        data = open(path, "rb").read()
        crc = zlib.crc32(data) & 0xFFFFFFFF
        self.settle()
        self.s.write(("b %X %X %08X\r" % (addr, len(data), crc)).encode())

        # WAIT FOR "rdy", THEN STREAM AT ONCE. Anvil's raw receive has its
        # own timeout, and a fixed sleep here spends it. A 3.5 s pause
        # after the header produced
        #     !! timed out after 0 of 6420 bytes - transfer incomplete
        # and the image bytes behind it were then read as COMMANDS,
        # because the monitor had gone back to its prompt while the host
        # was still politely waiting. The log filled with "pmf> l" and
        # "pmf> k", which nobody typed - those are bytes of an ARM image.
        # Poll for the handshake instead of guessing how long it takes.
        out = ""
        end = time.time() + 6
        while time.time() < end and "rdy" not in out:
            c = self.s.read(256)
            if c:
                out += c.decode("utf-8", "replace")
        if "rdy" not in out:
            return out + "\n[no rdy handshake - nothing was sent]"

        for i in range(0, len(data), 1024):
            self.s.write(data[i:i + 1024])
            self.s.flush()

        # WAIT FOR THE VERDICT, not for a fixed number of seconds. This
        # used to grab(6) unconditionally, which put a six-second floor
        # under every transfer and made a thirteen-fold baud increase
        # look like it had changed nothing at all - 85 KB "in 8.4 s"
        # was 2 s of transfer and 6 s of politely waiting.
        end = time.time() + 30
        while time.time() < end:
            c = self.s.read(4096)
            if c:
                out += c.decode("utf-8", "replace")
                if "ok" in out or "crc" in out or "timed out" in out:
                    break
        return out

    def cmd(self, text, seconds=4):
        self.settle()
        self.s.write(text.encode() + b"\r")
        return self.grab(seconds)

    def stage_addr(self):
        """Ask the board where to stage a file. None if it will not say.

        See stage_from_map above for why this is asked rather than
        carried. `map` prints a dozen lines; six seconds is the same
        budget `uptime` uses for one, which is slack rather than a
        measurement.
        """
        return stage_from_map(self.cmd("map", 6))

    def uptime(self):
        """Seconds since the monitor started, and the boot count.

        Returns (seconds, boots) with boots None when the counter has no
        magic in it. Returns (None, None) if the monitor is too old to
        know the command.

        THIS IS HOW A RESET IS CAUGHT WITHOUT A HUMAN NOTICING. A reset
        is otherwise invisible over the wire: the board comes back,
        prints the same banner and offers the same prompt, so "still
        running" and "died and rebooted" look identical - and a payload
        that wedged the machine looks exactly like one that returned.
        Uptime going BACKWARDS is the proof, and it costs two reads.
        """
        import re
        out = self.cmd("uptime", 6)
        m = re.search(r"uptime\s+(\d+)\s+boots\s+(\d+|\?)", out)
        if not m:
            return (None, None)
        boots = None if m.group(2) == "?" else int(m.group(2))
        return (int(m.group(1)), boots)

    def close(self):
        self.s.close()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    what = sys.argv[1]
    a = Anvil()
    try:
        if what == "boot":
            print(a.load_monitor())
        elif what == "watch":
            print(a.grab(float(sys.argv[2])))
        elif what == "cmd":
            a.prompt()
            for c in sys.argv[2:]:
                print(">>> " + c)
                print(a.cmd(c))
        elif what == "run":
            img, addr = sys.argv[2], int(sys.argv[3], 16)
            a.load_monitor()
            out = a.block(img, addr)
            print(out)
            if "ok" not in out:
                print("!! the block did not land cleanly - not running it")
                return 1
            for c in sys.argv[4:]:
                print(">>> " + c)
                print(a.cmd(c))
        else:
            print(__doc__)
            return 1
    finally:
        a.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

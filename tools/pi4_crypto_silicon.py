#!/usr/bin/env python3
r"""pi4_crypto_silicon.py - run Anvil's `crypto` self-test ON THE BOARD and
keep a transcript that can be trusted.

    python tools/pi4_crypto_silicon.py --identify
    python tools/pi4_crypto_silicon.py --flash [image] [--net]
    python tools/pi4_crypto_silicon.py --run    [--out transcript.txt]

`--flash` goes down the serial line, which is about two minutes for a
1.6 MB image; `--flash --net` sends it over a TCP connection through
Anvil's `net recv` (tools/pi4_upload.py) and takes seconds. The serial
path is the default and stays the fallback - it is the only one that
works on a board that has not joined a network, and the only one that
can put a `net recv`-capable image on a board that has not got one.

======================================================================
 WHY THIS TOOL EXISTS AND tools/anvil.py DOES NOT DO THE JOB
======================================================================

Anvil.cmd captures for a FIXED window and reads the port only when it
gets round to it.  That is right for a command that answers in two
lines and it is WRONG for one that prints a hundred and forty, for two
separate reasons, and the second one cost this pass a whole run:

  1. A FIXED WINDOW GUESSES WHEN THE BOARD IS FINISHED.  This tool
     waits for the board's own end marker instead, and refuses to
     report a capture that never printed one.

  2. AT 115200 BAUD A POLLING READER LOSES BYTES.  The line delivers
     11,520 bytes a second; Windows gives a serial port a 4096-byte
     receive ring by default; so a reader that comes back every 0.3 s
     is within a hair of the ring, and any pause at all - a garbage
     collection, a print - wraps it.  A wrapped ring does not report
     an error.  It hands back a mixture: the FIRST attempt at this
     sweep printed `crypto: 142 of 142 vectors PASS` above a
     transcript with six GCM vectors missing, replaced by a run of NUL
     bytes, and a 32-byte chunk delivered twice.

     A CORRECT VERDICT OVER A CORRUPTED TRANSCRIPT IS THE WORST
     ARTEFACT THIS EXERCISE CAN PRODUCE.  It reads as evidence.

So the port here is drained by a THREAD that does nothing else, from
the moment it is opened, and every capture is checked for both ways a
transcript lies: a missing end marker, and a NUL byte the monitor
never prints.

======================================================================
 WHAT IT HASHES, AND WHY BEFORE AND AFTER
======================================================================

`KERNEL8.IMG` is one file on one medium and the monitor's banner cannot
tell two builds apart (`version` is hard-coded).  The only
honest check is to hash the image and match the host file, which is why
every pass on this bench does that first.  Doing it AGAIN at the end
proves nothing wrote over it while the results were being taken - which
has happened on this board, twice, when two workers held the port
within four minutes of each other.

The board is asked by LOADING the file to the staging address and
running crc32 and sha256sum over exactly its length, because crc32 and
sha256sum take memory, not files.

======================================================================
 THE STRAY-KEYSTROKE DEFECT THIS TOOL HAS TO WORK AROUND
======================================================================

On a board built from `main` and joined to Wi-Fi, the monitor's command
input acquires characters nobody typed.  It shows as prompts that keep
arriving after a command has finished, and as the tail of the last
command's output being produced again and again - a one-kilobyte
directory listing came back as 416,640 bytes.

IT IS ALREADY DIAGNOSED AND ALREADY FIXED, on a branch that has not
merged: the wireless console's UDP arm took ANY datagram the IP layer
delivered and pushed it into the console's input ring, so a reply meant
for something else arrives as keystrokes (a DNS reply was seen typing
`fexample` and `comhB` at the prompt).  A board on a network with any
broadcast traffic on it therefore has something typing at it.

THIS TOOL DOES NOT FIX IT - that file belongs to another branch - it
works around it, in two ways, and says so in the transcript: every
command is preceded by Ctrl-C and a purge, and every capture STOPS the
moment the board prints its own end marker instead of reading on.  The
crypto commands themselves are unaffected: they run to completion and
print their own totals line, which is the marker.

A BOARD RESERVATION IS NOT THIS TOOL'S JOB and it deliberately does not
take one.  Whatever arrangement a bench uses to share a board is made
before this is run and released after; a tool that reserved the board
itself would do so on every dry run.
"""
from __future__ import annotations

import os
import argparse
import hashlib
import re
import subprocess
import sys
import threading
import time
import zlib

import serial

# WHERE THIS TOOL PUTS THE IMAGE IT READS BACK - ASKED, NOT CARRIED.
# STAGE was 0x400000 here until 2026-09-08, and this tool `load`s a whole
# KERNEL8.IMG into DRAM at that address before hashing it. On a monitor
# that has grown past two megabytes that address is INSIDE the running
# program, so this tool would have written a copy of the image over the
# monitor that was executing it, and then hashed the result and called it
# a measurement. See WHERE THE BOARD WANTS A FILE PUT in tools/anvil.py
# for the one reader of the board's answer in this tree.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from anvil import read_map, stage_help                    # noqa: E402

PORT = "COM7"
SLOT = "KERNEL8.IMG"
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_IMG = os.path.join(REPO, "build", "pi4", "anvil.img")  # what `python tools/build.py pi4` writes


def repeated_run(text: str, times: int = 3, minlen: int = 12):
    """Find a substantial LINE this capture prints three or more times.

    THIS IS THE SIGNATURE OF THE ADAPTER FAULT, and it is the only one of
    the three checks that catches a capture which still contains its end
    marker.  When the port wedges it hands back the last bytes it
    delivered, over and over - so the marker is present, the capture
    reads plausibly at a glance, and the middle of it is gone.

    Counted by LINE rather than by fixed-size chunk, because the repeat
    period is whatever the last delivery happened to be: 57 characters
    for one flood, 62 for another, 9 for a third.  A chunk scanner on a
    fixed grid misses all three; a line counter catches all three.

    NOTHING THIS MONITOR LEGITIMATELY PRINTS TRIPS IT - EXCEPT ONE
    THING, AND ON 2026-09-05 IT DID.  Every self-test line carries its
    own vector id and its own tick count, so no two are equal; the prose
    lines are each written once.  Bare prompts and short fragments are
    excluded by `minlen`, because a queued Enter really can produce three
    prompts and that is not corruption.

    WHAT WAS MISSED: A FAILURE EXPLANATION IS FIXED PROSE PRINTED ONCE
    PER FAILING VECTOR.  When fourteen bignum vectors failed in one run,
    the monitor printed the same five-line `!!` block fourteen times -
    correctly, that is what it is for - and this function called it the
    adapter handing back its own tail.  The cost was not just a wrong
    label: `ask()` RETRIED, five times, on the two slowest commands in
    the pass, and then reported the run as "not a result" when it was a
    perfectly good capture of a genuine failure.  **A guard against a
    lying transcript that fires on a truthful one is worse than no
    guard, because it teaches the reader to skip it.**

    THE FIX IS TO COUNT ONLY LINES THE MONITOR CANNOT LEGITIMATELY
    REPEAT, and the explanation blocks are excluded by structure rather
    than by matching their text: a block opens on a line whose first
    characters are `!!` and runs until the next per-vector line, blank
    line or prompt.  Nothing else is exempted.  The detector keeps all
    its power, because a wedged adapter re-delivers whatever it last
    delivered - and the per-vector lines, which carry an id and a tick
    count and are the bulk of every capture, are still counted.
    """
    VECLINE = re.compile(r"^[a-z0-9-]+\s+\d+\s+(PASS|FAIL)\b")
    counts: dict[str, int] = {}
    in_explanation = False
    for raw in text.replace("\r", "\n").split("\n"):
        line = raw.strip()
        if not line or line.startswith("pmf>") or VECLINE.match(line):
            in_explanation = False
        elif line.startswith("!!"):
            in_explanation = True
        if in_explanation:
            continue
        if len(line) < minlen:
            continue
        counts[line] = counts.get(line, 0) + 1
    worst = max(counts.items(), key=lambda kv: kv[1], default=None)
    if worst and worst[1] >= times:
        return worst[0], worst[1]
    return None


class Board:
    """COM7, drained by a thread, so nothing is ever lost to a slow reader."""

    def __init__(self, port: str = PORT, baud: int = 115200):
        self.s = serial.Serial(port, baud, timeout=0.05)
        self.s.dtr = False
        self.s.rts = False
        try:
            # A recommendation to the driver, not a guarantee - which is
            # why it is belt and the reader thread is braces.
            self.s.set_buffer_size(rx_size=1 << 18, tx_size=1 << 16)
        except Exception:
            pass
        self.unwedge()
        self._buf = bytearray()
        self._lock = threading.Lock()
        self._stop = False
        self._t = threading.Thread(target=self._reader, daemon=True)
        self._t.start()

    def unwedge(self) -> None:
        """Shake the adapter out of re-delivering its own last chunk.

        WHAT GOES WRONG.  On this bench the USB serial port intermittently
        stops delivering NEW bytes and starts handing back the LAST few it
        delivered, for ever.  It is unmistakable once seen: an `uptime`
        whose real answer is 388 bytes came back as 238,586 bytes of
        `d.\\r\\npmf> ` - the last ten characters of that answer - and a
        one-kilobyte directory listing came back as 416,640 bytes of its
        own last two lines.  The rate gives it away before the content
        does: 30 to 270 KB a second down a line that carries 11.5.

        IT IS NOT THE BOARD.  Asked at 115200 immediately after this
        sequence, the same board answers `uptime 218 boots ?` in 388
        bytes with nothing wrong with it.  Closing and reopening the port
        does not clear it, and neither does a twenty-second close, a
        purge, a break, or toggling DTR and RTS.  What does clear it,
        every time it has been tried, is making the driver reprogram the
        line: set a different rate, purge, set the real one back.

        This is a BENCH workaround for a host-side fault and it is not
        something a shipped tool should need.  It is here, with its
        evidence, because a run that silently produced 6 MB of repeated
        tail and called it a transcript would be far worse.
        """
        try:
            real = self.s.baudrate
            self.s.reset_input_buffer()
            self.s.reset_output_buffer()
            self.s.baudrate = 9600
            time.sleep(0.25)
            self.s.reset_input_buffer()
            self.s.baudrate = real
            time.sleep(0.25)
            self.s.reset_input_buffer()
        except Exception as e:
            print("  !! could not cycle the line rate (%s)" % e)

    def _reader(self) -> None:
        """Drain the port: take everything waiting, idle briefly when empty.

        THE SLEEP IS ON THE EMPTY PATH ONLY, and that ordering was
        arrived at by measurement rather than by taste.  A version that
        paused after every SUCCESSFUL read - on the theory that the
        adapter was being asked too often - made the corruption worse,
        not better.  What this bench actually does when it is unhappy is
        hand back the TAIL of what it last delivered, over and over: a
        `uptime` whose answer is 388 bytes came back as 238,586 bytes of
        `d.\\r\\npmf> ` repeated, which is the last ten bytes of the real
        answer.  Draining promptly is what keeps that from starting.
        """
        while not self._stop:
            try:
                n = self.s.in_waiting
                if n:
                    data = self.s.read(n)
                else:
                    data = self.s.read(1)
            except Exception:
                return
            if data:
                with self._lock:
                    self._buf += data
            else:
                time.sleep(0.005)

    def take(self) -> str:
        with self._lock:
            out = bytes(self._buf)
            self._buf = bytearray()
        return out.decode("utf-8", "replace")

    def drop(self) -> None:
        with self._lock:
            self._buf = bytearray()

    def quiet(self, seconds: float = 1.0, cap: float = 30) -> str:
        """Wait until the line has been silent for `seconds`."""
        end = time.time() + cap
        last = time.time()
        got = ""
        while time.time() < end and time.time() - last < seconds:
            chunk = self.take()
            if chunk:
                got += chunk
                last = time.time()
            else:
                time.sleep(0.02)
        return got

    def prompt(self, timeout: float = 60) -> bool:
        """Tap Enter until a prompt comes back. Returns True if it did."""
        t0 = time.time()
        while time.time() - t0 < timeout:
            self.drop()
            self.s.write(b"\r")
            end = time.time() + 1.5
            seen = ""
            while time.time() < end:
                seen += self.take()
                if "pmf>" in seen:
                    self.quiet(0.6)
                    return True
                time.sleep(0.02)
        return False

    def send(self, cmd: str, marker: str, count: int = 1,
             cap: float = 600, idle: float = 150,
             maxbytes: int = 250_000) -> tuple[str, list]:
        """One command, captured until the BOARD says it is finished.

        IT STOPS AT THE MARKER AND DOES NOT LINGER, and that is not an
        optimisation.  On this build the monitor's command input can
        acquire characters nobody typed - see the note in the module
        header about the wireless console's datagram injection, which is
        fixed on an unmerged branch and not in this image - so the line
        goes on producing prompts and re-runs after a command has
        finished.  A capture that keeps reading for a few more seconds
        pulls that into the transcript; a capture that stops when the
        board says it is done does not.  Ctrl-C and a purge before every
        command clear whatever accumulated in between.
        """
        self.s.write(b"\x03")          # the monitor's own stop
        time.sleep(0.4)
        self.quiet(0.4, cap=6)
        self.drop()
        self.s.write(cmd.encode() + b"\r")
        # ANCHOR ON THE BOARD'S ECHO OF THE COMMAND, AND DO IT INSIDE
        # THE LOOP, NOT AFTER IT.
        #
        # Whatever the line was doing before this command was typed is
        # not part of this command's answer, and on this bench there can
        # be a great deal of it - the adapter hands back stale buffer
        # content after an idle stretch, so a capture often opens with
        # the tail of something else repeated many times over. The board
        # echoes what it received, so the echo is the one landmark that
        # says "the answer starts here".
        #
        # Testing the end marker against the WHOLE capture instead would
        # be worse than useless: `ls` ends in "Case is not significant."
        # and so does every one of those stale repeats, so the wait
        # would be satisfied by the junk before the command had even
        # been answered, and the capture would be the junk.
        # THE ECHO IS MATCHED AS A WHOLE TYPED LINE - the command text
        # followed by the carriage return that ended it - and NOT as the
        # bare command text. `ls` as a substring lives inside the word
        # "listed", which appears in this monitor's own ls trailer, so a
        # bare rfind lands three words from the end of the junk and the
        # capture comes back empty of everything that matters.
        #
        # THE PROMPT IS NOT PART OF THE ANCHOR, and that cost two runs.
        # The obvious anchor is "pmf> <cmd>\r", but this routine PURGES
        # the buffer immediately before it writes - after the board has
        # already printed the prompt it is sitting at - so the "pmf> "
        # is on the far side of the purge and never appears in the
        # capture. Anchoring on it matched nothing, every command looked
        # unanswered, and the retries turned a healthy board into a
        # flooded one.
        def answer(t: str) -> str:
            for pat in ("pmf> " + cmd + "\r", cmd + "\r"):
                cut = t.rfind(pat)
                if cut >= 0:
                    return t[cut:]
            return ""

        # TWO PHASES WITH TWO DIFFERENT DEADLINES, because the two things
        # that can go wrong have completely different timescales.
        #
        #   * THE ECHO IS IMMEDIATE OR IT IS NEVER COMING. A live line
        #     echoes a typed command in milliseconds. If ten seconds pass
        #     with no echo the write went into a wedged adapter, and
        #     waiting the full timeout just means reading its repeated
        #     tail for another two minutes before finding that out.
        #
        #   * AFTER THE ECHO, SILENCE IS WORK. `crypto pbkdf2` is three
        #     RFC 6070 derivations at 4096 iterations each and prints
        #     nothing at all between vectors - about a minute of quiet on
        #     this part with the caches off. A short idle timeout there
        #     would abort a healthy run at its slowest and most
        #     interesting moment.
        raw = ""
        echo_by = time.time() + 10
        end = time.time() + cap
        tick = time.time() + 20
        last_byte = time.time()
        seen_echo = False
        while time.time() < end:
            chunk = self.take()
            if chunk:
                raw += chunk
                last_byte = time.time()
                if not seen_echo and answer(raw):
                    seen_echo = True
                if answer(raw).count(marker) >= count:
                    # Just the tail of the line the marker is on.
                    deadline = time.time() + 0.35
                    while time.time() < deadline:
                        raw += self.take()
                        time.sleep(0.02)
                    break
            else:
                time.sleep(0.02)
            if not seen_echo and time.time() > echo_by:
                print("    `%s` was not echoed within 10 s - the line is not "
                      "listening (%d bytes of other traffic)" % (cmd, len(raw)))
                break
            if seen_echo and time.time() - last_byte > idle:
                print("    `%s` went quiet for %.0f s without finishing"
                      % (cmd, idle))
                break
            # A SIZE CEILING, because the wedge can start AFTER the echo
            # and then neither of the two deadlines above can fire: bytes
            # keep arriving, so the line is never quiet, and they are the
            # same bytes over and over, so the end marker never comes.
            # `crypto vectors` - the largest thing this tool asks for -
            # prints about ten kilobytes. A quarter of a megabyte is
            # twenty-five times that and is not a number any healthy
            # answer can reach; the run that forced this line was at
            # nineteen megabytes and still climbing.
            if len(raw) > maxbytes:
                print("    `%s` produced %d bytes, far past anything it can "
                      "legitimately print - the line is repeating"
                      % (cmd, len(raw)))
                break
            if time.time() > tick:
                print("    ... %s: %d bytes so far (%d after the echo)"
                      % (cmd, len(raw), len(answer(raw))))
                tick += 20
        text = answer(raw)

        bad = []
        if not text:
            bad.append("`%s` was never echoed back, so the board may not have "
                       "received it at all and there is nothing to read as an "
                       "answer (%d bytes of other traffic arrived)"
                       % (cmd, len(raw)))
            text = raw
        if text.count(marker) < count:
            bad.append("`%s` never printed %r %d time(s) inside %.0f s, so "
                       "that capture is INCOMPLETE and is not a result"
                       % (cmd, marker, count, cap))
        if "\x00" in text:
            bad.append("`%s` came back with NUL bytes in it, which this "
                       "monitor never prints - the transcript has holes"
                       % cmd)
        rep = repeated_run(text)
        if rep:
            bad.append("`%s` came back with a %d-character run repeated %d "
                       "times (%r) - that is the adapter handing back its own "
                       "tail, and a capture with it in is not evidence"
                       % (cmd, len(rep[0]), rep[1], rep[0][:40]))
        return text, bad

    def ask(self, cmd: str, marker: str, count: int = 1,
            cap: float = 420, tries: int = 5,
            idle: float = 150) -> tuple[str, list]:
        """send(), RETRIED until the capture is clean or the tries run out.

        A RETRY IS HONEST HERE AND WOULD NOT BE EVERYWHERE.  Every
        command this tool sends is a READ - a hash, a report, a
        known-answer self-test over buffers in .bss - so running one
        again cannot change the board's state or the answer.  What the
        retry is fighting is a LINK that intermittently loses or
        duplicates bytes, and the two tests below (the board's own end
        marker, and a NUL the monitor cannot have printed) tell a bad
        capture from a good one every time.  A pass that needed a retry
        SAYS SO in the transcript, so the reader can see the link was
        not clean even though the result is.
        """
        last: tuple[str, list] = ("", ["never attempted"])
        for attempt in range(1, tries + 1):
            # PROVE THERE IS A PROMPT BEFORE TYPING AT IT. Every capture
            # that came back with no echo in it turned out to be a
            # command typed into a line that was not listening: the
            # adapter was mid-wedge, the write went nowhere, and the
            # tool then read the tail of the last flood for two minutes
            # and called the command unanswered. One Enter, answered,
            # costs a few milliseconds and removes that whole class.
            if not self.prompt(timeout=30):
                print("    no prompt before `%s` - shaking the line" % cmd)
                self.unwedge()
                self.prompt(timeout=30)
            text, bad = self.send(cmd, marker, count=count, cap=cap,
                                  idle=idle)
            if not bad:
                if attempt > 1:
                    print("    (`%s` needed %d attempts - the LINK was dirty, "
                          "not the board)" % (cmd, attempt))
                    text = ("[this capture took %d attempts; the earlier ones "
                            "lost bytes on the wire]\n" % attempt) + text
                return text, []
            last = (text, bad)
            print("    retry %d/%d for `%s`: %s"
                  % (attempt, tries, cmd, bad[0]))
            # The commonest reason a capture is bad on this bench is the
            # adapter re-delivering its own tail, and the only thing that
            # clears that is reprogramming the line - so a retry does it
            # before trying again rather than repeating the same failure.
            self.unwedge()
            self.drop()
            self.s.write(b"\x03")
            time.sleep(0.6)
            self.quiet(0.8, cap=8)
            self.drop()
        return last

    def close(self) -> None:
        self._stop = True
        time.sleep(0.1)
        try:
            self.s.close()
        except Exception:
            pass


def host_identity(path: str) -> dict:
    blob = open(path, "rb").read()
    return {"length": len(blob),
            "crc32": "%08X" % (zlib.crc32(blob) & 0xFFFFFFFF),
            "sha256": hashlib.sha256(blob).hexdigest()}


def identify(b: Board, tr: list) -> tuple[dict, list]:
    """What is on KERNEL8.IMG right now, from the board's own arithmetic."""
    info: dict = {}
    problems: list = []

    # WHERE TO PUT IT, FROM THE BOARD, BEFORE ANY BYTE IS WRITTEN. Asked
    # once per call and used for all three commands below, so the load,
    # the CRC and the digest cannot end up describing three addresses.
    out, bad = b.ask("map", "stage a file at", tries=2)
    problems += bad
    tr.append("")
    tr.append("=== pmf> map ===")
    tr.append(out)
    rec = read_map(out)
    if rec is None:
        print(stage_help("the image being read back"))
        raise SystemExit(
            "the board would not say where a file may be staged, so there is "
            "nowhere to load %s that is known not to be the monitor itself. "
            "Nothing was read back and nothing was hashed." % SLOT)
    stage = rec.stage
    print("  staging at %08X, which is where this board said to put it" % stage)

    # THE LENGTH COMES FROM `load`, NOT FROM `ls`, AND THAT IS A CHOICE.
    #
    # `load` prints "Loaded N bytes into memory", and N is the file's
    # length read out of the directory entry by the board itself - the
    # same number `ls` prints, from the same place, with one fewer
    # command. It matters here because `ls` is the command that upsets
    # this board's console: it is the longest uninterrupted burst the
    # monitor produces, and it is the one after which the line starts
    # handing back its own tail. Asking for the length as a side effect
    # of a command we have to run anyway removes the trigger instead of
    # working around it.
    out, bad = b.ask("load %s %X" % (SLOT, stage), "bytes into memory")
    problems += bad
    tr.append("")
    tr.append("=== pmf> load %s %X ===" % (SLOT, stage))
    tr.append(out)
    m = re.search(r"Loaded (\d+) bytes into memory", out)
    if not m:
        print(out)
        raise SystemExit(
            "the board did not say how many bytes it loaded from %s, so the "
            "image on the medium cannot be identified. Nothing here is a "
            "result until it can be." % SLOT)
    n = int(m.group(1))
    info["length"] = n
    print("  the board loaded %d bytes from %s" % (n, SLOT))

    # ANCHORED ON THE MONITOR'S OWN SENTENCE, not on "eight hex digits":
    # the explanation crc32 prints under its answer names the polynomial
    # EDB88320, which is eight hex digits, and a loose match would report
    # it as the checksum on a run where the answer was missing.
    out, bad = b.ask("crc32 %X %X" % (stage, n), "The CRC32 is ")
    problems += bad
    tr.append("")
    tr.append("=== pmf> crc32 %X %X ===" % (stage, n))
    tr.append(out)
    m = re.search(r"The CRC32 is ([0-9A-Fa-f]{8})", out)
    info["crc32"] = m.group(1).upper() if m else None
    print("  board crc32 %s" % info["crc32"])

    out, bad = b.ask("sha256sum %X %X" % (stage, n), "sha256sum is ")
    problems += bad
    tr.append("")
    tr.append("=== pmf> sha256sum %X %X ===" % (stage, n))
    tr.append(out)
    m = re.search(r"sha256sum is ([0-9a-f]{64})", out)
    info["sha256"] = m.group(1) if m else None
    print("  board sha256 %s" % info["sha256"])
    return info, problems


def compare(board: dict, host: dict, what: str) -> bool:
    ok = True
    for k in ("length", "crc32", "sha256"):
        bo, h = board.get(k), host.get(k)
        if bo is None:
            print("  %-7s board: (not printed)   host: %s" % (k, h))
            ok = False
            continue
        if str(bo) != str(h):
            print("  %-7s DIFFERS - board %s, host %s" % (k, bo, h))
            ok = False
        else:
            print("  %-7s matches: %s" % (k, bo))
    if not ok:
        print("  ** %s: the image on the board is NOT the image on the host."
              % what)
    return ok


def uptime(b: Board) -> int | None:
    out, _ = b.ask("uptime", "This monitor has been up")
    m = re.search(r"uptime\s+(\d+)", out)
    return int(m.group(1)) if m else None


MODULES = ("sha256", "sha1", "hmac", "hmacsha1", "hkdf", "pbkdf2", "drbg",
           "aes", "aes-ctr", "gcm", "keywrap",
           # ---- part two, the public-key half ----
           "bignum", "p256", "x25519", "ecdsa", "rsa", "t0vm", "x509")

# THE PUBLIC-KEY MODULES NEED A LONGER LEASH AND THE REASON IS PHYSICAL.
# With the D-cache off a P-256 scalar multiply on this part is seconds,
# not microseconds, and ecdsa runs fifty-one vectors of which nine are
# full verifications - two scalar multiplies each. The default 150 s
# idle would abort a healthy run in the middle of the slowest and most
# interesting module, which is the same trap the throughput row already
# records for pbkdf2. Named per module rather than raised globally, so a
# module that goes quiet when it should not still fails fast.
SLOW = {"ecdsa": (3600, 1200), "p256": (1800, 900), "x25519": (1200, 600),
        "rsa": (1800, 900), "x509": (1800, 900), "bignum": (1800, 900)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--identify", action="store_true")
    ap.add_argument("--flash", nargs="?", const=DEFAULT_IMG, metavar="IMAGE")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--image", default=DEFAULT_IMG)
    ap.add_argument("--out", default=os.path.join(REPO, "_work", "pi4_crypto_silicon.txt"))
    ap.add_argument("--speed-kb", type=int, default=64)
    # ------------------------------------------------------------------
    #  --net: FLASH OVER THE NETWORK instead of down the serial line.
    #
    #  The serial flash is about two minutes for a 1.6 MB image at 115200
    #  and the cable on this bench has started corrupting long transfers -
    #  a whole class of lost run that has nothing to do with cryptography.
    #  tools/pi4_upload.py drives Anvil's `net recv` instead: the image
    #  goes over a TCP connection, the board hashes THE MEMORY it landed
    #  in, and the tool refuses to save or boot anything unless that
    #  digest equals the host file's.
    #
    #  THE SERIAL PATH IS THE DEFAULT AND STAYS THE FALLBACK. It is the
    #  only one that works on a board which has not joined a network, it
    #  is the only way to get a `net recv`-capable image onto a board that
    #  does not have one yet, and it is the one that has to work when the
    #  network path is the thing that broke.
    # ------------------------------------------------------------------
    ap.add_argument("--net", action="store_true",
                    help="flash over the network (Anvil's net recv) instead "
                         "of down the serial line. The serial path is the "
                         "default and stays the fallback")
    ap.add_argument("--board-ip", default=None,
                    help="the board's address for --net; the default is to "
                         "ask the board")
    args = ap.parse_args()

    if not (args.identify or args.flash or args.run):
        ap.print_help()
        return 1

    if args.flash:
        # The flash goes through the tool that owns it. This one closes
        # the port first so there is exactly one reader at a time - two
        # readers on one port is how a transcript loses half its bytes
        # and neither side can tell.
        b = Board()
        try:
            if not b.prompt():
                raise SystemExit("no pmf> prompt on COM7 before the flash.")
            print("BEFORE THE FLASH - what is on the medium now:")
            identify(b, [])
        finally:
            b.close()
        print("")
        if args.net:
            cmd = [sys.executable, "tools/pi4_upload.py", args.flash,
                   "--to", "card", "--name", "KERNEL8.IMG", "--reset",
                   "--cache"]
            if args.board_ip:
                cmd += ["--board-ip", args.board_ip]
        else:
            cmd = [sys.executable, "tools/anvil_update.py",
                   args.flash, "--fast"]
        r = subprocess.run(cmd, text=True)
        if r.returncode != 0:
            if args.net:
                print("")
                print("!! the network flash did not complete, and NOTHING "
                      "was written to the")
                print("   medium unless the transcript above says it was. "
                      "The serial path is")
                print("   the fallback: run this again without --net. Do "
                      "not take a result")
                print("   until the image on the board hashes equal to the "
                      "host file.")
            return r.returncode
        time.sleep(6)

    tr: list = []
    problems: list = []
    b = Board()
    try:
        if not b.prompt():
            raise SystemExit("no pmf> prompt on COM7. Power-cycle the board "
                             "and try once more before concluding anything.")

        host = host_identity(args.image)
        print("")
        print("THE IMAGE, BEFORE ANY RESULT IS TAKEN:")
        print("  host  %s: %d bytes, crc32 %s" %
              (args.image, host["length"], host["crc32"]))
        print("  host  sha256 %s" % host["sha256"])
        tr.append("=== the image, before any result was taken ===")
        tr.append("host   %s  %d bytes  crc32 %s"
                  % (args.image, host["length"], host["crc32"]))
        tr.append("host   sha256 %s" % host["sha256"])
        before, bad = identify(b, tr)
        problems += bad
        same = compare(before, host, "before")
        tr.append("board  %s bytes  crc32 %s  sha256 %s"
                  % (before["length"], before["crc32"], before["sha256"]))
        up0 = uptime(b)
        tr.append("uptime before: %s s" % up0)

        if not args.run:
            open(args.out, "w", encoding="utf-8", newline="\n").write(
                "\n".join(tr) + "\n")
            print("\ntranscript -> %s" % args.out)
            return 0 if not problems else 1

        if not same:
            raise SystemExit(
                "the image on the board is not the one on the host, so any "
                "result taken now would be against an image nobody can "
                "identify. Flash first.")

        def run(cmd, marker, count=1, cap=600, idle=150):
            out, bad = b.ask(cmd, marker, count=count, cap=cap, idle=idle)
            tr.append("")
            tr.append("=== pmf> %s ===" % cmd)
            tr.append(out)
            print(">>> %s" % cmd)
            print(out)
            for x in bad:
                print("  ** %s" % x)
            return out, bad

        # THE CLOCK BELONGS IN THE TRANSCRIPT, NEXT TO THE RATES.
        # `crypto speed` prints bytes per second and deliberately does NOT
        # read the ARM clock - that would be a mailbox transaction and
        # would cost the self-test its "touches nothing but the console"
        # property. The clock is captured here instead, in the same file,
        # so a reader converting KB/s into cycles per byte has the number
        # a few lines above it.
        for c, mk in (("version", "Type info"),
                      ("clock", "DECIMAL rather than hex"),
                      ("cache status", "SCTLR_EL2"),
                      ("crypto list", "tools/gen_pi4_crypto")):
            problems += run(c, mk)[1]

        # ======================================================
        #  THE VECTOR SWEEP RUNS WITH THE CACHES ON, AND HERE IS
        #  THE ARITHMETIC THAT FORCED IT
        # ======================================================
        # Part one's sweep ran in the monitor's boot state - D-cache and
        # MMU off - because that is the world a payload gets unless it
        # asks for another, and its slowest module was PBKDF2 at nine
        # seconds.  Part two changes the scale by three orders of
        # magnitude and the change is physical, not a matter of taste:
        #
        #   * with the caches off this part retires about TWO MILLION
        #     instructions a second.  That is not a guess - part one's
        #     own table says SHA-256 over 64 KB takes 1.036 s, which is
        #     about a thousand block compressions, and PBKDF2's 8,192
        #     HMAC-SHA-1 calls take 8.86 s.  Every instruction fetch is
        #     a separate uncached DRAM transaction;
        #   * the desk gate counts ONE P-256 scalar multiply at
        #     276,006,456 instructions.  That is over two minutes on the
        #     part in the boot state, and an ECDSA verify is two of
        #     them.  Thirty of the forty-six shared ECDSA records reach
        #     the arithmetic.
        #
        # So the uncached vector sweep is a SIX-HOUR job on a board three
        # other lanes are waiting for, to produce exactly the verdicts a
        # cached sweep produces in four minutes.  The verdicts do not
        # depend on the cache state; only the tick column does, and the
        # tick column is labelled.
        #
        # THE UNCACHED COST IS NOT LOST - it is measured where it costs
        # minutes instead of hours: the throughput run below still runs
        # in BOTH states, one operation per module, so the boot-state
        # number for every public-key module is in this transcript as a
        # rate rather than as a table of two hundred identical waits.
        problems += run("cache on", "SCTLR_EL2")[1]

        # ONE MODULE AT A TIME FIRST, THEN THE WHOLE SWEEP.
        #
        # The per-module runs are not redundant with the sweep. Each ends
        # in its own totals line, so a capture that loses bytes loses ONE
        # module and says so, instead of putting a hole in the middle of
        # the only copy of the evidence. They also line up one for one
        # with the desk gate, which runs the modules in separate
        # processes, so the two tables compare row by row.
        print("")
        print("the eighteen modules, one at a time (caches ON)")
        for name in MODULES:
            cap, idle = SLOW.get(name, (600, 150))
            problems += run("crypto " + name, "crypto: ", cap=cap,
                            idle=idle)[1]

        print("")
        print("and the whole sweep in one go")
        problems += run("crypto vectors", "crypto: ", cap=7200, idle=1200)[1]

        # THE THROUGHPUT, TWICE: cached, then as the monitor boots.
        #
        # Anvil comes up with the D-cache and MMU OFF - the firmware
        # stub's state, which the monitor keeps - so every instruction
        # fetch and every data access goes to DRAM. That is the honest
        # default because it is the world a payload gets unless it asks
        # for another. `cache on` is a documented monitor command that
        # builds the identity tables and enables M|C|I, with the
        # framebuffer and the GENET ring mapped non-cacheable so the rest
        # stays coherent. The PAIR is the interesting number; either one
        # alone invites the wrong conclusion.
        #
        # THE ORDER IS CACHED FIRST NOW, because the sweep above left the
        # caches on and turning them off and back on around a throughput
        # run would be two more state changes than the measurement needs.
        # `cache off` is issued after the second run, so the board is
        # released in the state it boots in.
        for label, pre in (("caches ON", None),
                           ("caches OFF - the monitor's boot state",
                            "cache off")):
            if pre:
                problems += run(pre, "SCTLR_EL2")[1]
            print("")
            print("throughput, %s" % label)
            # THE MARKER IS THE BOARD'S OWN END LINE, NOT "KB/s".
            #
            # It used to be `"KB/s", count=3`, back when the run measured
            # three modules, and counting occurrences of a unit is a bad
            # anchor for two reasons that both bit here. It has to be
            # updated every time a row is added, silently accepting a
            # short table until somebody notices; and one of the eleven
            # rows - pbkdf2 - deliberately reports HMAC calls a second
            # rather than KB/s, because bytes a second for a 32-byte
            # output is 0 and reads as a broken instrument. The board
            # prints one line when it has finished all eleven. That is
            # the thing to wait for.
            #
            # AND IT IS GIVEN A LONG LEASH, because with the caches off
            # this is the slowest thing the board is asked to do and the
            # slowness is the measurement. RFC 3394 makes six passes over
            # the semiblocks, so one 64 KB wrap is about 49,000 single
            # AES-128 blocks against DRAM with no D-cache; PBKDF2 is
            # 8,192 HMAC-SHA-1 calls and was measured at 10.25 s on this
            # part when the supplicant was written. A row that prints
            # nothing for two minutes is a row that is working, so the
            # default 150 s idle would abort the run at its most
            # interesting moment - the same trap the module header
            # already records for `crypto pbkdf2`.
            # The marker is the LAST of the board's two end lines - the
            # symmetric table finishes first and the public-key one
            # follows it, so waiting on the symmetric marker would stop
            # the capture with six rows still to come.
            problems += run("crypto speed %d" % args.speed_kb,
                            "throughput: 6 public-key modules measured",
                            cap=5400, idle=1200)[1]
        # The second pass above already issued `cache off`. This asks the
        # board to SAY so, so the transcript ends with the state the next
        # worker will find rather than with an assumption about it.
        problems += run("cache status", "SCTLR_EL2")[1]

        print("")
        print("THE IMAGE, AFTER THE RESULTS:")
        after, bad = identify(b, tr)
        problems += bad
        if not compare(after, host, "after"):
            problems.append("the image on the board changed during the pass")
        tr.append("")
        tr.append("=== the image, after the results ===")
        tr.append("board  %s bytes  crc32 %s  sha256 %s"
                  % (after["length"], after["crc32"], after["sha256"]))
        up1 = uptime(b)
        tr.append("uptime after: %s s" % up1)
        print("  uptime %s -> %s s (it must go UP; a fall is a reset, and a "
              "reset mid-pass invalidates the run)" % (up0, up1))
        if up0 is not None and up1 is not None and up1 < up0:
            problems.append("uptime went DOWN, so the board reset during the "
                            "pass and nothing above is a result")

        open(args.out, "w", encoding="utf-8", newline="\n").write(
            "\n".join(tr) + "\n")
        print("")
        print("transcript -> %s" % args.out)
        print("=" * 70)
        if problems:
            print("%d PROBLEM(S) WITH THIS PASS - it is not a result until "
                  "they are dealt with:" % len(problems))
            for p in problems:
                print("  * %s" % p)
            return 1
        print("THE PASS IS COMPLETE AND THE TRANSCRIPT IS CLEAN: every "
              "capture ended in the board's own end marker, and not one of "
              "them contains a byte the monitor cannot have printed.")
        return 0
    finally:
        b.close()


if __name__ == "__main__":
    sys.exit(main())

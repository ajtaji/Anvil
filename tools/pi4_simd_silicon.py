#!/usr/bin/env python3
r"""pi4_simd_silicon.py - run the SIMD diagnostics ON THE BOARD and keep a
transcript that can be trusted.

    python tools/pi4_simd_silicon.py --identify
    python tools/pi4_simd_silicon.py --payload <image> --addr 0x400000 \
                                     --marker "pi4SimdSelfTest done" \
                                     --out transcript.txt
    python tools/pi4_simd_silicon.py --payload <image> --pre "cache on" ...

======================================================================
 IT LOADS A PAYLOAD AND RUNS IT. IT DOES NOT TOUCH `KERNEL8.IMG`.
======================================================================

The crypto passes on this bench flashed the boot file, because what they
were proving lived inside Anvil.  These two diagnostics do not: they are
ordinary `--entry-returns` images that go into RAM at 0x400000 and give
control back.  So this tool never issues `save` and never resets, and the
resident monitor the next worker meets is the one it left.

That also removes the whole class of accident the lock note's three
"it happened again" callouts are about: there is no boot file to
overwrite, so a second worker arriving mid-run cannot silently replace
what these results were taken against.  What CAN still happen is the
port being taken, so the staged payload is hashed IN BOARD MEMORY,
before the run and again after it, against the host file.

======================================================================
 WHY NOT tools/anvil.py
======================================================================

`anvil.py cmd` captures for a FIXED wall-clock window and reads the port
only when it gets round to it.  That is right for a command that answers
in two lines and wrong for one that prints two hundred, for the reason
`tools/pi4_crypto_silicon.py` on main records at length and paid for
once already:

  AT 115200 BAUD A POLLING READER LOSES BYTES.  The line delivers 11,520
  bytes a second and Windows gives a serial port a 4096-byte receive
  ring, so any pause at all - a garbage collection, a print - wraps it.
  A wrapped ring does not report an error.  It hands back a mixture, and
  the FIRST crypto sweep on this bench produced a correct verdict line
  above a transcript with six vectors missing.

  A CORRECT VERDICT OVER A CORRUPTED TRANSCRIPT IS THE WORST ARTEFACT
  THIS EXERCISE CAN PRODUCE, because it reads as evidence.

So the port is drained by a thread that does nothing else from the
moment it is opened, the capture ends on the program's OWN end marker
rather than on a guess, and every transcript is checked for the three
ways one lies: no end marker, a NUL byte the monitor never prints, and
a substantial line delivered three or more times, which is the
signature of the adapter re-delivering its tail.

======================================================================
 THE LOCK IS NOT THIS TOOL'S JOB
======================================================================

`Raspberry Pi 4\BOARD-IN-USE.md` in the vault is claimed before this is
run and released after.  A tool that claimed a lock would claim it on
every dry run.
"""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import re
import sys
import threading
import time
import zlib

import serial

PORT = "COM7"
BAUD = 115200


# ---------------------------------------------------------------------
#  THE THREE WAYS A TRANSCRIPT LIES
# ---------------------------------------------------------------------
def repeated_run(text: str, times: int = 3, minlen: int = 12) -> str | None:
    """A substantial NON-VERDICT line this capture prints three or more
    times.

    When the port wedges it hands back the last bytes it delivered, over
    and over, so the end marker is present, the capture reads plausibly
    at a glance, and the middle of it is gone.  Counted by LINE and not
    by fixed-size chunk, because the repeat period is whatever the last
    delivery happened to be.

    ======================================================================
     VERDICT LINES ARE EXCLUDED, AND THIS CHECK CLAIMED OTHERWISE FIRST
    ======================================================================
    The first version said "every verdict line carries its own case
    label, and the labels are unique".  IT IS NOT TRUE and the first
    silicon run said so: `pi4SimdSelfTest` has twelve fill cases and
    twelve blit cases, and each of them prints `returned count ... PASS`
    under its own `fill count=N` heading.  Twenty-four identical lines,
    all real.

    So a perfect 140-of-140 transcript came back accused of being
    corrupt.  **A checker that cries wolf over good evidence is worse
    than no checker**, because the next person reads past its warning -
    and the warning it exists to give is the one about a transcript that
    looks fine and is not.

    The property that actually catches a wedged port on THIS transcript
    is `verdicts_match_self_report` below: the program counts its own
    verdicts and prints the total, so bytes lost make the printed count
    LOWER than the program's own number and bytes re-delivered make it
    HIGHER.  That is exact, and it cannot be fooled by a line the
    program legitimately repeats.  This function keeps the throughput
    table, whose rows are all distinct and which prints no verdicts at
    all.
    """
    seen: dict[str, int] = {}
    for line in text.splitlines():
        s = line.strip()
        if len(s) < minlen or "... PASS" in s or "... FAIL" in s:
            continue
        seen[s] = seen.get(s, 0) + 1
        if seen[s] >= times:
            return s
    return None


def verdicts_match_self_report(text: str) -> str | None:
    """The program's own count against the verdicts actually delivered.

    `pi4SimdSelfTest` ends with "N passed, M failed", computed by
    counters it incremented as it went.  Comparing that with the lines
    that reached the host is an EXACT completeness check: bytes lost
    make the delivered count lower, bytes re-delivered make it higher,
    and neither can hide behind a line the program prints twice on
    purpose.

    Returns None when the transcript carries no such summary - the
    throughput table has no verdicts and is not being accused of
    missing any.
    """
    m = re.search(r"(\d+) passed, (\d+) failed", text)
    if not m:
        return None
    said_pass, said_fail = int(m.group(1)), int(m.group(2))
    got_pass = text.count("... PASS")
    got_fail = text.count("... FAIL")
    if (got_pass, got_fail) == (said_pass, said_fail):
        return None
    return ("the program counted %d passed and %d failed, and %d PASS and %d "
            "FAIL lines actually arrived. Fewer means bytes were lost; more "
            "means the adapter re-delivered some. Either way the middle of "
            "this transcript is not what the board printed."
            % (said_pass, said_fail, got_pass, got_fail))


def transcript_faults(text: str, marker: str) -> list[str]:
    fails = []
    if "\x00" in text:
        fails.append(
            "the capture contains a NUL byte, which this monitor never "
            "prints. That is a wrapped receive ring: bytes were lost and "
            "whatever verdict this transcript carries is about a message "
            "that is not all here.")
    if marker not in text:
        fails.append(
            f"the capture never contained the program's own end marker "
            f"({marker!r}). It stopped rather than finished - a fault, the "
            "deadman, or the port taken - and a partial run has no failures "
            "in the part it printed.")
    dup = repeated_run(text)
    if dup:
        fails.append(
            "a non-verdict line was delivered three or more times, which is "
            "the adapter re-delivering its tail rather than the board "
            f"printing: {dup!r}. The middle of this capture is missing.")
    miscount = verdicts_match_self_report(text)
    if miscount:
        fails.append(miscount)
    return fails


class Board:
    """COM7, drained by a thread that does nothing else."""

    def __init__(self, port: str = PORT, baud: int = BAUD):
        self.s = serial.Serial(port, baud, timeout=0.05)
        self.s.dtr = False
        self.s.rts = False
        self.buf = bytearray()
        self.lock = threading.Lock()
        self.stop = False
        self.t = threading.Thread(target=self._reader, daemon=True)
        self.t.start()

    def _reader(self) -> None:
        while not self.stop:
            try:
                c = self.s.read(4096)
            except Exception:
                return
            if c:
                with self.lock:
                    self.buf += c

    def take(self) -> str:
        with self.lock:
            out = bytes(self.buf)
            self.buf.clear()
        return out.decode("latin-1")

    def peek(self) -> str:
        with self.lock:
            return bytes(self.buf).decode("latin-1")

    def drop(self) -> None:
        with self.lock:
            self.buf.clear()

    def quiet(self, seconds: float = 1.0, cap: float = 30) -> str:
        """Read until the line has been silent for `seconds`."""
        end = time.time() + cap
        last = time.time()
        got = ""
        while time.time() < end and time.time() - last < seconds:
            chunk = self.take()
            if chunk:
                got += chunk
                last = time.time()
            time.sleep(0.02)
        return got

    def unwedge(self) -> None:
        """Ctrl-C, then purge.

        A board on a network with any broadcast traffic on it has
        something typing at it - the wireless console's UDP arm pushes
        any delivered datagram into the console input ring (the pi4-tcp
        worker's finding of 2026-09-04, fixed on a branch that has not
        merged).  So a command is never written into whatever the
        monitor thinks it was already reading.
        """
        self.s.write(b"\x03")
        time.sleep(0.2)
        self.s.write(b"\r")
        self.quiet(0.8, 8)
        self.drop()

    def prompt(self, timeout: float = 60) -> bool:
        t0 = time.time()
        while time.time() - t0 < timeout:
            self.s.write(b"\r")
            time.sleep(0.15)
            if "pmf>" in self.peek():
                self.quiet(0.6, 5)
                self.drop()
                return True
        return False

    def ask(self, cmd: str, marker: str, cap: float = 60,
            idle: float = 8) -> str:
        """Send one command; capture until its marker, or until it goes
        quiet for `idle`, or until `cap`. Returns everything read."""
        self.unwedge()
        self.s.write(cmd.encode() + b"\r")
        out = ""
        end = time.time() + cap
        last = time.time()
        while time.time() < end:
            chunk = self.take()
            if chunk:
                out += chunk
                last = time.time()
                if marker and marker in out:
                    # Let the line that carries the marker finish, and
                    # STOP - do not read on into whatever is typing at
                    # this board.
                    time.sleep(0.4)
                    out += self.take()
                    break
            elif time.time() - last > idle:
                break
            time.sleep(0.02)
        return out

    def close(self) -> None:
        self.stop = True
        time.sleep(0.15)
        try:
            self.s.close()
        except Exception:
            pass


# ---------------------------------------------------------------------
#  STAGING AND ITS PROOF
# ---------------------------------------------------------------------
def host_identity(path: pathlib.Path) -> dict:
    data = path.read_bytes()
    return {"bytes": len(data),
            "crc32": "%08X" % (zlib.crc32(data) & 0xFFFFFFFF),
            "sha256": hashlib.sha256(data).hexdigest()}


def stage(b: Board, path: pathlib.Path, addr: int, tr: list) -> bool:
    """Anvil's `b` fast loader, with the handshake polled and not slept.

    A fixed sleep after the header spends the monitor's own receive
    timeout, and the image bytes behind it are then read as COMMANDS -
    that is the `pmf> l` / `pmf> k` failure anvil.py's header records.
    """
    data = path.read_bytes()
    crc = zlib.crc32(data) & 0xFFFFFFFF
    b.unwedge()
    b.s.write(("b %X %X %08X\r" % (addr, len(data), crc)).encode())

    out = ""
    end = time.time() + 8
    while time.time() < end and "rdy" not in out:
        out += b.take()
        time.sleep(0.02)
    if "rdy" not in out:
        tr.append("  !! no `rdy` handshake - NOTHING was sent")
        tr.append("     " + out.strip().replace("\n", "\n     "))
        return False

    t0 = time.time()
    for i in range(0, len(data), 1024):
        b.s.write(data[i:i + 1024])
        b.s.flush()

    end = time.time() + 60
    while time.time() < end:
        out += b.take()
        if "ok" in out or "crc" in out or "timed out" in out:
            break
        time.sleep(0.02)
    took = time.time() - t0
    tr.append("  the board's own answer to `b`: "
              + " ".join(out.split())[-160:])
    tr.append("  %d bytes in %.1f s (%.1f KB/s)"
              % (len(data), took, len(data) / took / 1024 if took else 0))
    return "timed out" not in out and "!!" not in out


def verify_staged(b: Board, host: dict, addr: int, tr: list, when: str) -> bool:
    """Hash what is IN BOARD MEMORY against the host file.

    The monitor's banner cannot tell two builds apart (forum 586 -
    `version` is hard-coded), so the only honest check is this one, and
    it is done again AFTER the run because the port has been taken out
    from under a pass on this bench twice.
    """
    # PARSED OFF THE MONITOR'S OWN SENTENCE, not off the end of the
    # capture. `crc32` prints "The CRC32 is XXXXXXXX" and `sha256sum`
    # prints "The sha256 is <64 hex>", and a capture ends with a prompt
    # and possibly with whatever is typing at this board - so an anchor
    # on the tail of the text matches the wrong thing or nothing.
    #
    # A STOPPED CHECKSUM PRINTS NO CHECKSUM AT ALL, deliberately, so a
    # missing match means "interrupted", never "zero" - and that is
    # reported as a failure rather than passed over.
    ok = True
    got = b.ask("crc32 %X %X" % (addr, host["bytes"]), "The CRC32 is",
                cap=180, idle=20)
    m = re.search(r"The CRC32 is\s+([0-9A-Fa-f]{8})", got)
    board_crc = m.group(1).upper() if m else None
    got2 = b.ask("sha256sum %X %X" % (addr, host["bytes"]), "is ",
                 cap=300, idle=30)
    m2 = re.search(r"([0-9a-fA-F]{64})", " ".join(got2.split()))
    board_sha = m2.group(1).lower() if m2 else None
    if board_crc is None:
        tr.append("  !! the board printed no CRC32 at all. A stopped one "
                  "prints nothing by design, so this is an interrupted "
                  "checksum and not a zero: " + " ".join(got.split())[-200:])
        ok = False

    tr.append("  %s: board crc32 %s (host %s), board sha256 %s"
              % (when, board_crc, host["crc32"],
                 (board_sha[:16] + "...") if board_sha else "?"))
    if board_crc != host["crc32"]:
        tr.append("  !! CRC32 MISMATCH %s vs host %s - the bytes in memory "
                  "are not the bytes that were built. Nothing taken against "
                  "this staging can be attributed to the source."
                  % (board_crc, host["crc32"]))
        ok = False
    if board_sha and board_sha != host["sha256"]:
        tr.append("  !! SHA-256 MISMATCH - as above, and the two hashes "
                  "agreeing on the failure means it is not a read error.")
        ok = False
    if board_sha is None:
        tr.append("  (the monitor did not answer sha256sum; the CRC32 "
                  "stands on its own but it is one witness, not two)")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--identify", action="store_true",
                    help="prompt, banner and uptime; touch nothing")
    ap.add_argument("--payload")
    ap.add_argument("--addr", default="0x400000")
    ap.add_argument("--marker", default="done")
    ap.add_argument("--pre", action="append", default=[],
                    help="a command to send before the run, e.g. 'cache on'")
    ap.add_argument("--post", action="append", default=[])
    # 15 AND NOT MORE. The monitor's deadman counter is 20 bits at
    # 65536/s, so the ceiling is ~15.999 s; anything larger is clamped
    # and REPORTED as 15, because a deadman must never fire before it
    # said it would. Asking for 60 would print 15 and read like a
    # 60-second cover that does not exist.
    ap.add_argument("--deadman", type=int, default=15)
    ap.add_argument("--cap", type=float, default=600)
    ap.add_argument("--out")
    ap.add_argument("--port", default=PORT)
    args = ap.parse_args()

    tr: list[str] = []
    b = Board(args.port)
    rc = 0
    try:
        if not b.prompt():
            print("no `pmf>` prompt on %s - is the board powered and is the "
                  "resident image Anvil?" % args.port)
            return 2
        tr.append("prompt reached on %s at %s"
                  % (args.port, time.strftime("%Y-%m-%d %H:%M:%SZ",
                                              time.gmtime())))
        up = b.ask("uptime", "", cap=15, idle=4)
        tr.append("  uptime: " + " ".join(up.split())[:160])
        ver = b.ask("version", "", cap=15, idle=4)
        tr.append("  version: " + " ".join(ver.split())[:200])

        if args.identify:
            print("\n".join(tr))
            return 0

        if not args.payload:
            print("--payload is required unless --identify")
            return 2

        path = pathlib.Path(args.payload)
        host = host_identity(path)
        addr = int(args.addr, 16)
        tr.append("payload %s: %d bytes, crc32 %s, sha256 %s"
                  % (path.name, host["bytes"], host["crc32"], host["sha256"]))

        # ARM THE DEADMAN BEFORE THE PAYLOAD RUNS, not after. A payload
        # that wedges the machine is exactly the case where nothing
        # later gets a chance to arm anything.
        dm = b.ask("deadman %d" % args.deadman, "", cap=15, idle=4)
        tr.append("  deadman: " + " ".join(dm.split())[:120])

        if not stage(b, path, addr, tr):
            tr.append("!! the payload did not land - NOT running it")
            print("\n".join(tr))
            return 1
        if not verify_staged(b, host, addr, tr, "staged"):
            tr.append("!! staged bytes do not match the host file - "
                      "NOT running it")
            print("\n".join(tr))
            return 1

        for cmd in args.pre:
            got = b.ask(cmd, "", cap=60, idle=6)
            tr.append("  pre `%s`: %s" % (cmd, " ".join(got.split())[:200]))

        tr.append("")
        tr.append("=== the run, captured until the program's own end marker "
                  "%r ===" % args.marker)
        run = b.ask("run %X" % addr, args.marker, cap=args.cap, idle=120)
        tr.append(run.replace("\r\n", "\n").rstrip())
        tr.append("=== end of the run ===")
        tr.append("")

        faults = transcript_faults(run, args.marker)
        for f in faults:
            tr.append("!! " + f)
            rc = 1

        for cmd in args.post:
            got = b.ask(cmd, "", cap=60, idle=6)
            tr.append("  post `%s`: %s" % (cmd, " ".join(got.split())[:200]))

        # AGAIN, AFTER. Nothing may have written over the payload while
        # the results were being taken - which has happened here.
        if not verify_staged(b, host, addr, tr, "after the run"):
            rc = 1
        up2 = b.ask("uptime", "", cap=15, idle=4)
        tr.append("  uptime after: " + " ".join(up2.split())[:160])
        tr.append("  (uptime going BACKWARDS is a reset, and a reset means "
                  "the payload wedged the machine and the deadman rescued "
                  "it - which looks exactly like a clean return otherwise)")
    finally:
        b.close()

    text = "\n".join(tr)
    print(text)
    if args.out:
        p = pathlib.Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text + "\n", encoding="utf-8")
        print("\nwritten to %s" % p)
    return rc


if __name__ == "__main__":
    sys.exit(main())

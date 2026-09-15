#!/usr/bin/env python3
r"""pi4_upload_check.py - gate tools/pi4_upload.py against a FAKE Anvil.

    python tools/pi4_upload_check.py

WHY A GATE FOR A HOST TOOL AT ALL

tools/pi4_upload.py is the thing that decides whether an image is
allowed to be saved onto the boot medium or entered.  Everything it
protects is on the other side of a comparison it makes itself, and a
comparison nobody has ever seen refuse is a comparison nobody has any
reason to believe.  The board proves the RECEIVER; this proves the
JUDGE, and it does it here rather than at the bench because taking a
shared board out of service to watch a tool fail on purpose is the
wrong use of a shared board.

WHAT THE FAKE BOARD IS

A few dozen lines below: a UDP socket that answers Anvil's wireless
console on 127.0.0.1, and a TCP listener it opens when it is told
`net recv`.  It speaks only the sentences the real monitor prints and
the tool actually reads, and each of them is quoted from
Anvil/Core/netrecv_cmd.pbi:

    "Listening on port N over ... for ONE connection."
    "Received N bytes from A.B.C.D to ADDR in M ms."
    "  sha256 <64 hex>"
    "... written."          (from Anvil/Core/fs_cmd.pbi's save)

IT IS A MODEL AND IT IS NOT THE BOARD.  It proves the host tool's
sequencing, its parsing and its verdict; it proves nothing whatever
about the receiver, the ceiling, the memory or the digest, which are
gated in tools/a64/a64_tcp_check.py against the real receiver driven by
byte-exact frames, and proven on silicon on the bench Pi 4.  Saying so
is the point: a fake board that answered every question would quietly
become the evidence.

THE CASES

Cases 1 to 5 all pass --addr, which is the override, and they are
therefore also the negative control for cases 6 to 8: a guard that
refused every address, or a tool that could no longer place a file at
all, would turn them red before it turned anything green.

  1. A GOOD UPLOAD.  Exit 0, the digests equal, `save` not issued.
  2. --to card.  Exit 0 and the fake board must have SEEN `save` with
     the right name, address and length - because a tool that verified
     and then wrote the wrong length is the failure worth catching.
  3. --corrupt.  One bit flipped on the wire.  The fake board hashes
     what it actually received, so its digest differs, and the tool MUST
     exit non-zero AND MUST NOT issue `save` or `boot`.
  4. A BOARD THAT NEVER PRINTS A DIGEST.  The tool must exit non-zero
     rather than treating a silent board as a pass.  This is the one
     that a "if the digests differ, fail" implementation gets wrong.
  5. A BOARD THAT REPORTS THE RIGHT DIGEST AND THE WRONG LENGTH.  The
     verdict is TWO comparisons, not one, and until this case existed
     only the digest half had ever been seen to refuse.  The fake board
     hashes what it really received and then understates the count by
     one - which is what a receiver that stopped at a ceiling and hashed
     the part it kept would look like from here, and it is not far
     fetched: `net recv` has a ceiling and reports the count it stored.
     `--to card` would otherwise write a length that is part new and
     part whatever was on the medium, so the tool must refuse before
     `save`.
  6. NO --addr AT ALL: THE BOARD CHOOSES.  This is the case the whole
     2026-09-08 lane exists for.  The fake board is a monitor of
     3,145,728 bytes - one that could not have existed under the old
     two-megabyte ceiling - so its map says `stage a file at 00500000`,
     an address that appears nowhere in this tree as a constant.  The
     tool must arm `net recv` at that address and, with --to card, save
     at it.  A tool that had kept 0x400000 as a default would stage
     inside that monitor, and the way that fails on a real board is not
     a crash: it is a board that answers and cannot obey.
  7. A MONITOR TOO OLD TO HAVE `map`, WITH NO --addr.  There is nowhere
     to put the file and no way to find out, so the tool must stop with
     a sentence and MUST NOT arm a listener.  A fallback to 0x400000
     here would be the constant back with an extra step.
  8. AN --addr THAT LANDS ON THE RUNNING MONITOR.  Refused before
     anything is armed or sent, naming both extents, the size of the
     overlap and the address the board did offer.  The extent comes out
     of the SAME `map` answer as the staging address - one command, not
     a second query to `version` - and the case is real: on 2026-09-08 a
     flash without --addr staged 2,105,296 bytes at 0x400000 over an
     image running to $00401607 and cost a human at the power lead.
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import socket
import subprocess
import sys
import threading
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(os.environ.get("PMF_REPO") or HERE.parent)
print("[gate] tree under test: %s" % ROOT, file=sys.stderr)
TOOL = HERE / "pi4_upload.py"
WORK = ROOT / "_work"

ADDR = 0x400000
IMAGE_BYTES = 200_000            # big enough to cross many TCP segments

# THE FAKE BOARD'S OWN MAP.  The default is the monitor as it ships
# today - 2,083,792 bytes at $200000, so its staging address is $400000
# and ADDR above is clear of it, which is what makes cases 1 to 5 the
# negative control.  BIG_* is a monitor that could not have existed
# before 2026-09-08: three megabytes, so the low window and the staging
# address are at $500000 and the old constant is INSIDE the image.
MON_LO = 0x200000
MON_BYTES = 2_083_792
BIG_BYTES = 3_145_728
BIG_STAGE = 0x500000


def map_text(lo: int, nbytes: int, stage: int) -> str:
    """`map`'s two lines that a host tool reads, quoted from the monitor.

    PutMonitorMap() in Anvil/Core/memrange.pbi prints the image line with
    the EXACT end and the byte count it was measured from, and the
    staging line with the rounded-up address above it.  Nothing else in
    that output is parsed by anything, so nothing else is modelled - a
    fake that reproduced the whole page would be a second copy of the
    monitor's prose to keep in step.
    """
    return ("THE MEMORY MAP, AS THIS IMAGE MEASURES IT\r\n"
            "  this image      %08X to %08X   %d bytes, measured from the "
            "image itself\r\n"
            "  stage a file at %08X               which is what the upload "
            "tools ask for\r\nok\r\npmf> "
            % (lo, lo + nbytes - 1, nbytes, stage))


class FakeAnvil:
    """Anvil's wireless console and one `net recv` listener, on loopback.

    `silent` drops the digest line, which is case 4.  `short` understates
    the byte count while still printing the digest of what it really
    received, which is case 5 - the length half of the verdict.
    `mon_bytes` is how big this board says its own image is, and
    `no_map` makes it a monitor built before 2026-09-08, which answers
    `map` with nothing at all.
    """

    def __init__(self, silent: bool = False, short: int = 0,
                 mon_bytes: int = MON_BYTES, stage: int = ADDR,
                 no_map: bool = False, cache_on: bool = False,
                 stale_cache_reply: bool = False,
                 report_ms: int | None = None) -> None:
        self.silent = silent
        self.short = short
        self.mon_bytes = mon_bytes
        self.stage = stage
        self.no_map = no_map
        self.cache_on = cache_on
        self.stale_cache_reply = stale_cache_reply
        self.report_ms = report_ms
        self.seen: list[str] = []
        self.received: bytes = b""
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp.bind(("127.0.0.1", 0))
        self.udp.settimeout(0.2)
        self.port = self.udp.getsockname()[1]
        self.peer: tuple | None = None
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._serve, daemon=True)

    # ---- the console -------------------------------------------------
    def say(self, text: str) -> None:
        if self.peer is not None:
            self.udp.sendto(text.encode(), self.peer)

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.stop.set()
        self.thread.join(timeout=5)
        self.udp.close()

    def _serve(self) -> None:
        while not self.stop.is_set():
            try:
                data, peer = self.udp.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                return
            self.peer = peer
            for line in data.decode("latin-1").replace("\n", "\r").split("\r"):
                line = line.strip()
                if not line:
                    self.say("pmf> ")
                    continue
                self.seen.append(line)
                self._command(line)

    def _command(self, line: str) -> None:
        if line == "cache on" and self.stale_cache_reply:
            self.say("Wi-Fi: reconnect complete.\r\ncache\r\n"
                     "The D-cache and MMU are OFF - old response.\r\npmf> ")
        # The real interpreter echoes its accepted command before replying.
        self.say(line + "\r\n")
        if line == "wifi ip":
            self.say("  network  BENCH\r\n  IP       127.0.0.1\r\n"
                     "  netmask  255.0.0.0\r\npmf> ")
        elif line == "map":
            # A MONITOR TOO OLD FOR THIS COMMAND SAYS SO, in the words
            # the real one uses for anything it does not know. It does
            # not stay silent: silence and "I do not know that word" are
            # different answers and only one of them is what an old
            # monitor gives.
            if self.no_map:
                self.say("? map - type h for the list.\r\npmf> ")
            else:
                self.say(map_text(MON_LO, self.mon_bytes, self.stage))
        elif line.startswith("net recv "):
            self._net_recv(line)
        elif line.startswith("save "):
            self.say("%d bytes written.\r\npmf> " % len(self.received))
        elif line == "cache on":
            self.cache_on = True
            self.say("Caches ON.\r\npmf> ")
        elif line == "cache off":
            self.cache_on = False
            self.say("Caches OFF.\r\npmf> ")
        elif line == "cache":
            self.say("The D-cache and MMU are %s - verified state.\r\npmf> "
                     % ("ON" if self.cache_on else "OFF"))
        elif line.startswith("boot "):
            self.say("## entered.\r\npmf> ")
        else:
            self.say("pmf> ")

    # ---- `net recv <port> <addr>` -------------------------------------
    def _net_recv(self, line: str) -> None:
        parts = line.split()
        port = int(parts[2])
        addr = int(parts[3], 16)
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", port))
        srv.listen(1)
        # THE ANNOUNCEMENT IS THE HANDSHAKE: the tool waits for this
        # sentence before it connects, so it goes out after the listener
        # is really up and not before.
        self.say("Listening on port %d over the bench loopback for ONE "
                 "connection.\r\n" % port)
        srv.settimeout(20.0)
        try:
            conn, _ = srv.accept()
        except socket.timeout:
            srv.close()
            self.say("!! nobody connected.\r\npmf> ")
            return
        got = bytearray()
        t0 = time.time()
        with conn:
            conn.settimeout(20.0)
            while True:
                try:
                    chunk = conn.recv(65536)
                except socket.timeout:
                    break
                if not chunk:
                    break
                got += chunk
        srv.close()
        ms = int((time.time() - t0) * 1000)
        if self.report_ms is not None:
            ms = self.report_ms
        self.received = bytes(got)
        self.say("Received %d bytes from 127.0.0.1 to %08X in %d ms.\r\n"
                 % (len(got) - self.short, addr, ms))
        if self.silent:
            self.say("pmf> ")
            return
        self.say("  sha256 %s\r\npmf> "
                 % hashlib.sha256(bytes(got)).hexdigest())


def run_tool(board: FakeAnvil, image: pathlib.Path, *extra: str):
    cmd = [sys.executable, str(TOOL), str(image),
           "--console", "wifi",
           "--console-ip", "127.0.0.1",
           "--console-port", str(board.port),
           "--board-ip", "127.0.0.1",
           "--port", str(free_port()),
           *extra]
    r = subprocess.run(cmd, cwd=str(ROOT), text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       timeout=180)
    return r.returncode, r.stdout


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main() -> int:
    WORK.mkdir(exist_ok=True)
    image = WORK / "pi4_upload_check.bin"
    # Deterministic, non-repeating, and nothing like zero - a payload of
    # zeroes would make "the bytes arrived" and "nothing arrived" produce
    # the same digest for a truncated transfer.
    body = bytearray()
    x = 0x12345678
    while len(body) < IMAGE_BYTES:
        x = (1103515245 * x + 12345) & 0xFFFFFFFF
        body += x.to_bytes(4, "little")
    image.write_bytes(bytes(body[:IMAGE_BYTES]))
    want = hashlib.sha256(image.read_bytes()).hexdigest()
    print("fixture: %d bytes, sha256 %s" % (IMAGE_BYTES, want))
    print()

    fails: list[str] = []
    cases = 0

    # ---- 1. a good upload -------------------------------------------
    cases += 1
    b = FakeAnvil()
    b.start()
    try:
        rc, out = run_tool(b, image, "--addr", "%X" % ADDR)
    finally:
        b.close()
    if rc != 0:
        fails.append("a good upload exited %d, and it must exit 0:\n%s"
                     % (rc, indent(out)))
    if b.received != image.read_bytes():
        fails.append("the fake board received %d bytes and the file is %d"
                     % (len(b.received), IMAGE_BYTES))
    if any(s.startswith("save ") for s in b.seen):
        fails.append("a plain upload issued `save`. --to ram must leave the "
                     "medium alone: %r" % b.seen)
    print("  1. a good upload                        %s"
          % ("OK" if rc == 0 else "FAIL"))

    # ---- 2. --to card, and the save has to be RIGHT -------------------
    cases += 1
    b = FakeAnvil()
    b.start()
    try:
        rc, out = run_tool(b, image, "--addr", "%X" % ADDR,
                           "--to", "card", "--name", "KERNEL8.IMG")
    finally:
        b.close()
    saves = [s for s in b.seen if s.startswith("save ")]
    if rc != 0:
        fails.append("--to card exited %d:\n%s" % (rc, indent(out)))
    want_save = "save KERNEL8.IMG %X %X" % (ADDR, IMAGE_BYTES)
    if saves != [want_save]:
        fails.append("--to card issued %r; wanted exactly [%r]. A tool that "
                     "verified the image and then saved the wrong LENGTH "
                     "writes a boot file that is part new and part whatever "
                     "was there" % (saves, want_save))
    print("  2. --to card issues the right save      %s"
          % ("OK" if saves == [want_save] and rc == 0 else "FAIL"))

    # ---- 3. one bit flipped on the wire ------------------------------
    cases += 1
    b = FakeAnvil()
    b.start()
    try:
        rc, out = run_tool(b, image, "--addr", "%X" % ADDR,
                           "--to", "card", "--boot", "--corrupt")
    finally:
        b.close()
    bad = []
    if rc == 0:
        bad.append("it exited 0")
    if any(s.startswith("save ") for s in b.seen):
        bad.append("it issued `save` anyway")
    if any(s.startswith("boot ") for s in b.seen):
        bad.append("it issued `boot` anyway")
    if "DID NOT VERIFY" not in out:
        bad.append("it did not say the upload had not verified")
    if bad:
        fails.append("ONE BIT WAS FLIPPED ON THE WIRE AND THE TOOL DID NOT "
                     "REFUSE: %s.\n%s" % ("; ".join(bad), indent(out)))
    print("  3. one flipped bit is REFUSED           %s"
          % ("OK" if not bad else "FAIL"))

    # ---- 4. a board that never prints a digest -----------------------
    cases += 1
    b = FakeAnvil(silent=True)
    b.start()
    try:
        rc, out = run_tool(b, image, "--addr", "%X" % ADDR,
                           "--to", "card", "--boot",
                           "--verify-timeout", "8")
    finally:
        b.close()
    bad = []
    if rc == 0:
        bad.append("it exited 0")
    if any(s.startswith("save ") for s in b.seen):
        bad.append("it issued `save`")
    if any(s.startswith("boot ") for s in b.seen):
        bad.append("it issued `boot`")
    if bad:
        fails.append("A BOARD THAT PRINTED NO DIGEST WAS TREATED AS A PASS: "
                     "%s. No verdict is not a good verdict.\n%s"
                     % ("; ".join(bad), indent(out)))
    print("  4. no digest is not a pass              %s"
          % ("OK" if not bad else "FAIL"))

    # ---- 5. the right digest and the wrong length --------------------
    cases += 1
    b = FakeAnvil(short=1)
    b.start()
    try:
        rc, out = run_tool(b, image, "--addr", "%X" % ADDR,
                           "--to", "card", "--boot")
    finally:
        b.close()
    bad = []
    if rc == 0:
        bad.append("it exited 0")
    if any(s.startswith("save ") for s in b.seen):
        bad.append("it issued `save`")
    if any(s.startswith("boot ") for s in b.seen):
        bad.append("it issued `boot`")
    if "DID NOT VERIFY" not in out:
        bad.append("it did not say the upload had not verified")
    if "stored %d bytes" % (IMAGE_BYTES - 1) not in out:
        bad.append("it did not name the two lengths, so a reader cannot "
                   "tell WHICH half of the verdict failed")
    if bad:
        fails.append("THE BOARD REPORTED THE RIGHT DIGEST AND A LENGTH ONE "
                     "SHORT AND THE TOOL DID NOT REFUSE: %s. The verdict is "
                     "two comparisons and both of them have to bite.\n%s"
                     % ("; ".join(bad), indent(out)))
    print("  5. a short length is REFUSED            %s"
          % ("OK" if not bad else "FAIL"))

    # ---- 6. no --addr: the board chooses, and it is not 0x400000 -----
    cases += 1
    b = FakeAnvil(mon_bytes=BIG_BYTES, stage=BIG_STAGE)
    b.start()
    try:
        rc, out = run_tool(b, image, "--to", "card")
    finally:
        b.close()
    bad = []
    if rc != 0:
        bad.append("it exited %d" % rc)
    if not any(s == "map" for s in b.seen):
        bad.append("it never asked the board for its map")
    if not any(s.startswith("net recv ") and s.endswith(" %X" % BIG_STAGE)
               for s in b.seen):
        bad.append("it did not arm the listener at %X - the board said "
                   "`stage a file at %08X` and the listener was armed with "
                   "%s" % (BIG_STAGE, BIG_STAGE,
                           "; ".join(s for s in b.seen
                                     if s.startswith("net recv ")) or "nothing"))
    if not any(s == "save %s %X %X" % ("KERNEL8.IMG", BIG_STAGE, IMAGE_BYTES)
               for s in b.seen):
        bad.append("it did not save from %X" % BIG_STAGE)
    if "%08X" % ADDR in out:
        bad.append("it printed %08X, which is the constant this lane "
                   "removed and is inside a monitor of this size" % ADDR)
    if bad:
        fails.append("WITH NO --addr THE TOOL DID NOT PUT THE FILE WHERE "
                     "THIS BOARD SAID: %s. A %d-byte monitor stages at "
                     "%08X and nothing in this tree may assume otherwise.\n%s"
                     % ("; ".join(bad), BIG_BYTES, BIG_STAGE, indent(out)))
    print("  6. the board chooses the address        %s"
          % ("OK" if not bad else "FAIL"))

    # ---- 7. a monitor with no `map`, and no --addr -------------------
    cases += 1
    b = FakeAnvil(no_map=True)
    b.start()
    try:
        rc, out = run_tool(b, image, "--to", "card")
    finally:
        b.close()
    bad = []
    if rc == 0:
        bad.append("it exited 0")
    if any(s.startswith("net recv ") for s in b.seen):
        bad.append("it armed a listener anyway")
    if any(s.startswith("save ") for s in b.seen):
        bad.append("it issued `save`")
    if "map" not in out:
        bad.append("it did not say that `map` was what went unanswered, so "
                   "a reader cannot tell what is wrong with the board")
    if bad:
        fails.append("A MONITOR THAT WOULD NOT SAY WHERE TO STAGE DID NOT "
                     "STOP THE RUN: %s. Falling back to an address is the "
                     "constant back with an extra step.\n%s"
                     % ("; ".join(bad), indent(out)))
    print("  7. no map and no --addr STOPS the run   %s"
          % ("OK" if not bad else "FAIL"))

    # ---- 8. an --addr that lands on the running monitor --------------
    cases += 1
    b = FakeAnvil(mon_bytes=BIG_BYTES, stage=BIG_STAGE)
    b.start()
    try:
        rc, out = run_tool(b, image, "--addr", "%X" % ADDR, "--to", "card")
    finally:
        b.close()
    bad = []
    if rc == 0:
        bad.append("it exited 0")
    if any(s.startswith("net recv ") for s in b.seen):
        bad.append("it armed a listener, so the board was already committed "
                   "to receiving before anything was checked")
    if any(s.startswith("save ") for s in b.seen):
        bad.append("it issued `save`")
    if "REFUSING TO SEND" not in out:
        bad.append("it did not refuse in so many words")
    for want, what in (("%08X" % MON_LO, "the base of the running image"),
                       ("%08X" % (MON_LO + BIG_BYTES - 1),
                        "the end of the running image"),
                       ("%08X" % BIG_STAGE, "the address the board offered")):
        if want not in out:
            bad.append("it did not print %s (%s)" % (want, what))
    if bad:
        fails.append("AN --addr INSIDE THE RUNNING MONITOR WAS NOT REFUSED: "
                     "%s. The board does not fall over when this happens - "
                     "it answers and stops obeying - so the refusal has to "
                     "be here.\n%s" % ("; ".join(bad), indent(out)))
    print("  8. --addr onto the monitor is REFUSED   %s"
          % ("OK" if not bad else "FAIL"))

    # Real tool subprocess and loopback protocol: no invented denominator for
    # a zero-resolution sample, with positive timing unchanged.
    for reported_ms in (0, 25):
        cases += 1
        b = FakeAnvil(report_ms=reported_ms)
        b.start()
        try:
            rc, out = run_tool(b, image, "--addr", "%X" % ADDR)
        finally:
            b.close()
        summaries = [line for line in out.splitlines() if line.startswith("  VERIFIED:")]
        good = rc == 0 and len(summaries) == 1 and b.received == bytes(body[:IMAGE_BYTES])
        if good and reported_ms == 0:
            good = "timer resolution; transfer rate unavailable" in summaries[0] and "KB/s" not in summaries[0]
        elif good:
            expected_rate = "(%.0f KB/s)." % ((IMAGE_BYTES / 1024.0) / (reported_ms / 1000.0))
            good = expected_rate in summaries[0] and "25 ms on the board" in summaries[0]
        if not good:
            fails.append("invalid verified rate summary for %d ms:\n%s" % (reported_ms, indent(out)))
        print("  %d. board timing %d ms is reported honestly %s" % (cases, reported_ms, "OK" if good else "FAIL"))

    print()
    if fails:
        for f in fails:
            print("  FAIL " + f)
        print()
        print("pi4_upload_check: FAIL - %d of %d cases" % (len(fails), cases))
        return 1
    print("pi4_upload_check: PASS - %d cases against a fake Anvil" % cases)
    print("           It proves the HOST tool: the sequencing, the parsing")
    print("           and the verdict, including that a flipped bit, a")
    print("           short length and a silent board each stop it before")
    print("           anything is saved or booted.")
    print("           IT PROVES NOTHING ABOUT THE BOARD. The receiver, the")
    print("           ceiling, the memory and the digest are gated against")
    print("           the real code in tools/a64/a64_tcp_check.py and proven")
    print("           on the bench Pi 4.")
    return 0


def indent(text: str) -> str:
    return "\n".join("      " + ln for ln in text.strip().splitlines())


if __name__ == "__main__":
    sys.exit(main())

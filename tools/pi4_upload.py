#!/usr/bin/env python3
"""pi4_upload.py - put an image on the Pi 4 over the NETWORK, in seconds.

    python tools/pi4_upload.py <image> [options]

WHAT IT REPLACES, AND THE NUMBER THAT MADE IT WORTH WRITING

    the serial `b` path        11.5 kB/s   ~2 minutes for a 1.5 MB image
    the acknowledged `wb` path ~100 KB/s   stop-and-wait, one KiB at a time
    this                       measured and printed on every run

Two minutes is what it costs to change one line of Anvil and see the
result, and the FTDI cable on this bench has started corrupting long
transfers, so the two minutes are not even reliable. This drives Anvil's
`net recv` instead: the console (serial, or the network UDP console) arms
a one-shot TCP listener on the board, the image goes over that
connection, and the board prints how many bytes landed and the SHA-256 of
the memory they landed in.

THE VERDICT IS THE HASH AND NOTHING ELSE

The board hashes THE MEMORY after the transfer, not the bytes as they
came off the wire, and this tool hashes the local file. Equal means the
DRAM about to be booted holds the file on this disk. Unequal - by one bit
- and this tool exits NON-ZERO and boots nothing. Same rule as Anvil's
own hash-before-jump, one layer earlier.

    --to ram        leave it in memory (the default)
    --to card       and then `save <name> <addr> <len>` onto the boot medium
    --boot          and then enter it: `boot mem <addr>`, or `boot <name>`
                    for --to card
    --reset         and then reset the board (use with --to card --name
                    KERNEL8.IMG to replace Anvil itself)

    --addr HEX      where in DRAM it goes. Default: ASK THE BOARD, with
                    `map` - the monitor has no fixed size, so the bottom
                    of the low payload window follows its image
    --port N        the port the board listens on. Default 5001
    --name NAME     the file --to card writes. Default KERNEL8.IMG
    --board-ip A    the board's address. Default: ask it, with `wifi ip`
    --console serial|net      how the commands get there. Default serial.
                    `wifi` is kept as an alias for `net` and always will
                    be: the console rode only the radio until 2026-09-07
                    and every note and script written before then says
                    wifi. It is the same UDP console on the same port,
                    armed on EVERY interface the board holds an address
                    on, answering each request out of the interface that
                    request arrived on. `wifi` reaches a board on a cable
    --com PORT      the serial port. Default COM7
    --console-ip A  the board's address for the network console. Defaults
                    to --board-ip. On a board with a cable AND a radio
                    this is the one that decides which path the commands
                    take - the board answers on both
    --console-port N  the network console's UDP port. 5555 unless somebody
                    has changed it, and a flag rather than a constant so
                    that tools/pi4_upload_check.py can stand a fake Anvil
                    up on a loopback port and watch this tool refuse
    --cache         send `cache on` first. On this part SHA-256 is 61 KB/s
                    with the caches off and 4,041 KB/s with them on, so the
                    digest is otherwise the slow half of the run. The
                    radio, the console and the framebuffer all stay
                    coherent with them on - see Anvil's own `cache` text
    --keep-cache    leave the caches on afterwards (default: put them back
                    the way they were found)

    --corrupt [OFF] THE BENCH INSTRUMENT. Flip one bit of ONE BYTE on its
                    way out, while still comparing against the digest of
                    the real file, and this run MUST FAIL. It is the
                    negative control for everything above: a verifier
                    nobody has ever seen refuse is a verifier nobody has
                    any reason to believe. OFF is a decimal byte offset;
                    the default is the middle of the file. It prints a
                    loud line and nothing is saved or booted.

BEFORE YOU RUN IT: the Pi 4 is a shared bench board. Read
`Raspberry Pi 4\\BOARD-IN-USE.md` in the vault and claim it. This tool
opens COM7 by default and will take the port out from under whoever has
it, exactly the collision that note exists to record.
"""
import argparse
import hashlib
import os
import re
import socket
import sys
import time
from typing import NamedTuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# THIS TOOL PRINTS WHAT THE BOARD SAID, AT A SEAM WHERE DYING IS WORST.
# On 2026-09-08 the print at the end of the `save` step raised
# UnicodeEncodeError on a U+FFFD in the board's reply - one line after
# the save had returned and one line before `reset` would have been sent,
# leaving the board running a monitor it was halfway through replacing.
# See console_out.py.
from console_out import relay_safe_output   # noqa: E402

relay_safe_output()

# WHICH OF THIS MACHINE'S INTERFACES IS ON THE BOARD'S SEGMENT. Written
# once, in anvil_wifi.py, beside the interface enumeration it needs -
# a second copy here would be a second thing to be right about, and the
# two would disagree the first time a platform's interface table changed
# shape. See local_bind_for there for what it is for and what it refuses
# to match (a /32 tunnel endpoint is not a segment).
from anvil_wifi import local_bind_for, bound_udp_socket   # noqa: E402
# THE STAGING ADDRESS COMES FROM THE BOARD, and there is one reader of
# its answer in this tree. DEFAULT_ADDR used to be 0x400000 here, one of
# four copies of that number; the monitor's extent is now the size of its
# own image and the first free address above it moves with it. See WHERE
# THE BOARD WANTS A FILE PUT in tools/anvil.py. Imported rather than
# re-implemented even though this tool has two transports of its own: the
# parse is a pure function of the text for exactly that reason. The same
# answer carries the extent of the running image, which is what stops an
# --addr given by hand from landing on the monitor driving the upload -
# one command, because they are one fact.
from anvil import read_map, stage_help                   # noqa: E402

DEFAULT_COM = "COM7"
DEFAULT_PORT = 5001
DEFAULT_NAME = "KERNEL8.IMG"
WIFI_CONSOLE_PORT = 5555


# =====================================================================
#  THE TWO CONSOLES
# =====================================================================
#  Anvil answers the same command set over the serial line and over UDP
#  5555, so the only thing that differs is how a line gets there and how
#  the reply comes back.  Both classes present the same three methods and
#  nothing below this section knows which one it is holding.
# =====================================================================
class SerialConsole:
    kind = "serial"

    def __init__(self, port, baud=115200):
        import serial                       # imported here: the wireless
        self.name = port                    # path needs no pyserial
        self.s = serial.Serial(port, baud, timeout=0.2)
        self.s.dtr = False
        self.s.rts = False

    def settle(self, quiet=1.0, cap=15):
        """Read until the line has been silent. NEVER write without this.

        The board can still be draining the previous command when the
        next one is sent, and a command written into that backlog gets
        interleaved with it - see tools/anvil.py's own note, which was
        earned by a binary payload being read as commands.
        """
        end = time.time() + cap
        last = time.time()
        got = ""
        while time.time() < end and time.time() - last < quiet:
            c = self.s.read(4096)
            if c:
                got += c.decode("utf-8", "replace")
                last = time.time()
        try:
            self.s.reset_input_buffer()
        except Exception:
            pass
        return got

    def send(self, line):
        self.s.write(line.encode() + b"\r")
        self.s.flush()

    def recv_some(self):
        """Whatever has arrived, after at most one read timeout. "" if
        nothing did. A bulk reader calls this in a loop and keeps its own
        tail, so a megabyte reply is not re-scanned per read."""
        c = self.s.read(4096)
        return c.decode("utf-8", "replace") if c else ""

    def read_until(self, needles, timeout, on_line=None):
        """Collect until any needle appears, or the timeout expires."""
        end = time.time() + timeout
        out = ""
        shown = 0
        while time.time() < end:
            c = self.s.read(4096)
            if c:
                out += c.decode("utf-8", "replace")
                if on_line is not None:
                    while "\n" in out[shown:]:
                        i = out.index("\n", shown)
                        on_line(out[shown:i].rstrip("\r"))
                        shown = i + 1
                if any(nd in out for nd in needles):
                    break
        return out

    def close(self):
        self.s.close()


# THE CONSOLE'S KEEPALIVE - the same 20 s as tools/board_run.py, for the same
# measured reason. The PC's stateful firewall forgets a UDP flow it has seen no
# traffic on: on 2026-09-16 a reply after 120 s of silence arrived and replies
# after 150 s and 300 s were dropped (forum 839). A long upload or a slow digest
# is exactly such a silence on the console socket, because the bytes go over a
# separate TCP connection. An EMPTY datagram, which the monitor reads as no
# keystrokes at all.
KEEPALIVE_SECONDS = 20.0


class WifiConsole:
    kind = "wifi"
    keepalive_seconds = KEEPALIVE_SECONDS
    keepalives = 0
    last_sent = None
    # Only while a command of ours is outstanding - an empty datagram at an
    # idle prompt would take the console for good (forum 888; see
    # tools/board_run.py).
    command_open = False

    def __init__(self, ip, port=WIFI_CONSOLE_PORT):
        self.name = "%s:%d" % (ip, port)
        self.addr = (ip, port)
        # BOUND TO THE INTERFACE ON THE BOARD'S SUBNET, for the same
        # reason `stream` below binds its TCP connection: a socket bound
        # to 0.0.0.0 on a machine with a VPN up can send the console's
        # datagrams down the tunnel, and a console that never answers
        # looks identical to a board that never armed one.
        self.s, self.local = bound_udp_socket(ip)
        if self.local:
            print("  console from this machine's %s" % self.local)
        else:
            print("  NOTE: no address on this machine is on %s's subnet, so "
                  "the routing" % ip)
            print("  table chooses which interface the console's datagrams "
                  "leave from.")
        self.s.settimeout(0.2)
        # ROOM FOR A BULK READBACK. `readback` sends full datagrams 250 us
        # apart, about four thousand a second; a default receive buffer on
        # this platform holds a few dozen of them, so a host that paused to
        # write a transcript line would drop a run of them and the stream's
        # length check would fail for a reason that has nothing to do with
        # the board. Asked for, not assumed: the platform may give less.
        try:
            self.s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 << 20)
        except OSError:
            pass
        # Whoever sends a datagram becomes the peer, so the board has to
        # be nudged once before it knows where to print.
        self.s.sendto(b"\r", self.addr)
        self.last_sent = time.time()

    def keepalive(self):
        """An empty datagram if nothing has gone to the board for a while.

        Called before every receive, which is where all of this class's
        waiting happens, so no wait can outlast the firewall's memory.
        """
        if self.last_sent is None or not self.command_open:
            return
        if time.time() - self.last_sent >= self.keepalive_seconds:
            self.s.sendto(b"", self.addr)
            self.last_sent = time.time()
            self.keepalives += 1

    def _recvfrom(self, size):
        self.keepalive()
        data, peer = self.s.recvfrom(size)
        if peer == self.addr and b"pmf>" in data:
            self.command_open = False
        return data, peer

    def settle(self, quiet=0.6, cap=8):
        end = time.time() + cap
        last = time.time()
        got = ""
        while time.time() < end and time.time() - last < quiet:
            try:
                data, peer = self._recvfrom(4096)
            except socket.timeout:
                continue
            if peer != self.addr:
                continue
            got += data.decode("utf-8", "replace")
            last = time.time()
        return got

    def send(self, line):
        self.s.sendto(line.encode() + b"\r", self.addr)
        self.last_sent = time.time()
        self.command_open = bool(line.strip())

    def recv_some(self):
        """One datagram from the board, or "" after the socket timeout."""
        try:
            data, peer = self._recvfrom(65536)
        except socket.timeout:
            return ""
        if peer != self.addr:
            return ""
        return data.decode("utf-8", "replace")

    def read_until(self, needles, timeout, on_line=None):
        end = time.time() + timeout
        out = ""
        shown = 0
        while time.time() < end:
            try:
                data, peer = self._recvfrom(4096)
            except socket.timeout:
                continue
            if peer != self.addr:
                continue
            out += data.decode("utf-8", "replace")
            if on_line is not None:
                while "\n" in out[shown:]:
                    i = out.index("\n", shown)
                    on_line(out[shown:i].rstrip("\r"))
                    shown = i + 1
            if any(nd in out for nd in needles):
                break
        return out

    def close(self):
        self.s.close()


# =====================================================================
#  Talking to the prompt
# =====================================================================
def at_prompt(con, timeout=30):
    """Tap CR until 'pmf>' comes back. True if the monitor is there."""
    end = time.time() + timeout
    tail = ""
    while time.time() < end:
        con.send("")
        out = con.read_until(["pmf>"], 1.0)
        tail = (tail + out)[-200:]
        if "pmf>" in tail:
            con.settle()
            return True
    return False


class ConsoleReplyError(RuntimeError):
    """The command has no attributable, completed response; do not retry it."""


def command(con, line, seconds=6, needles=None):
    """Read this command's echoed line through its completion prompt.

    A leftover prompt or asynchronous link report does not acknowledge a
    later command. Never resend a possibly executed command on timeout.
    `needles` is retained for callers but is not a completion boundary:
    a success word inside a reply cannot release the interpreter early.
    """
    con.settle()
    con.send(line)
    echo = re.compile(r"(?:^|\n)(?:pmf>[ \t]*)?" + re.escape(line) + r"[ \t]*\n")
    prompt = re.compile(r"(?:^|\n)pmf>[ \t]*(?:\n|$)")
    end = time.monotonic() + seconds
    out = ""
    while time.monotonic() < end:
        out += con.read_until(["\n", "pmf>"], max(0, end - time.monotonic()))
        normalized = out.replace("\r", "")
        start = echo.search(normalized)
        if start and prompt.search(normalized, start.end()):
            return normalized[start.start():]
        if len(out) > 1024 * 1024:
            break
    raise ConsoleReplyError(
        "Error 1: no complete response attributable to %r arrived. "
        "The command may have executed; it was not retried. Check the "
        "board console and its connection before sending another command." % line)


def cache_enabled(con):
    out = command(con, "cache", 10)
    states = re.findall(r"^The D-cache and MMU are (ON|OFF)\b", out, re.M)
    if len(states) != 1:
        raise ConsoleReplyError(
            "Error 2: the board did not report one unambiguous cache state. "
            "Check its cache status before changing settings or uploading.")
    return states[0] == "ON"


class CacheState:
    """Own only a verified OFF-to-ON transition, and restore it on every exit."""

    def __init__(self, con, keep=False):
        self.con, self.keep, self.restore_off = con, keep, False

    def enable(self):
        if cache_enabled(self.con):
            print("  cache:   already ON (verified; left unchanged)")
            return
        # Record cleanup before sending the mutating command: its response
        # might be lost even though the setting actually changed.
        self.restore_off = not self.keep
        command(self.con, "cache on", 15)
        if not cache_enabled(self.con):
            raise ConsoleReplyError(
                "Error 3: caches remain OFF after enabling them. Check the "
                "board's MMU/cache diagnostic; no upload was started.")
        print("  cache:   ON (verified by a separate status read)")

    def restore(self):
        if not self.restore_off:
            return
        self.restore_off = False  # One cleanup attempt; failure must remain loud.
        command(self.con, "cache off", 15)
        if cache_enabled(self.con):
            raise ConsoleReplyError(
                "Error 4: the original OFF cache state could not be restored. "
                "Check the board's cache status; do not assume cleanup succeeded.")
        print("  cache:   original OFF state restored and verified")


def board_address(con):
    """Ask the board what address it is on. None if it has not got one."""
    out = command(con, "wifi ip", 6)
    m = re.search(r"^\s*IP\s+(\d+\.\d+\.\d+\.\d+)\s*$", out, re.M)
    if m:
        return m.group(1)
    # The wired side, when the radio has nothing: `net` prints the four
    # addresses and the first of them is this board's.
    out = command(con, "net", 8)
    m = re.search(r"this board\s+(\d+\.\d+\.\d+\.\d+)", out)
    if m and m.group(1) != "0.0.0.0":
        return m.group(1)
    return None


# =====================================================================
#  Getting bytes OFF the board: `readback`
# =====================================================================
#  tools/anvil_readback.py, re-exported so a caller that already holds this
#  module as its console transport - the compiler repository's readback
#  tool does - reaches the reader through the same name. One
#  implementation: see that file for the format and the verdict.
from anvil_readback import (ReadbackError, ReadbackTimeout,   # noqa: E402,F401
                            parse_readback, read_range, readback_reply)


# =====================================================================
#  The transfer
# =====================================================================
class TransferTiming(NamedTuple):
    queued_seconds: float
    elapsed_seconds: float
    peer_closed: bool
    close_error: str


def stream_report(size, timing):
    """Host socket observations, never a claim about board memory or rate."""
    queued = "  %d bytes queued to the host TCP socket in %.2f s."
    lines = [queued % (size, timing.queued_seconds)]
    if timing.peer_closed:
        lines.append("  Peer TCP close observed after %.2f s; waiting for "
                     "the board's length and SHA-256 verdict."
                     % timing.elapsed_seconds)
    else:
        lines.append("  Peer TCP close not confirmed after %.2f s (%s); "
                     "delivery is not yet verified."
                     % (timing.elapsed_seconds, timing.close_error))
    return "\n".join(lines)


def stream(ip, port, data, connect_timeout=15.0):
    """Queue every byte, half-close, and report host-only timing observations.

    THE CLOSE IS THE END-OF-FILE MARKER and it is a half close, not a
    hang up: shutdown(SHUT_WR) sends the FIN and leaves the socket able
    to see the peer's own FIN come back. sendall only proves that the
    host socket accepted the bytes, not that the board has received or
    stored them. A timeout/reset is explicitly not a confirmed close.
    Only the later board length and memory digest can verify delivery.
    """
    # THE CONNECTION IS MADE FROM THE INTERFACE ON THE BOARD'S SUBNET.
    # On a machine with a VPN up, letting the routing table choose can
    # send the SYN down the tunnel: nothing answers, and it reads exactly
    # like a board whose listener never armed. Measured on this bench
    # 2026-09-07, where the laptop carries two /32 tunnel interfaces and
    # a VPN default route while the board sits on a link-local 169.254/16
    # cable. None when no interface of ours is on the board's subnet -
    # which is the honest answer for a board behind a router, and
    # create_connection then behaves exactly as it always did.
    src = local_bind_for(ip)
    if src:
        print("  connecting from this machine's %s, which is on the "
              "board's subnet" % src)
    end = time.monotonic() + connect_timeout
    last = None
    s = None
    while time.monotonic() < end:
        try:
            s = socket.create_connection(
                    (ip, port), timeout=5.0,
                    source_address=((src, 0) if src else None))
            break
        except OSError as e:                 # the listener may not be up yet
            last = e
            s = None
            time.sleep(0.15)
    if s is None:
        raise SystemExit("!! could not connect to %s port %d: %s\n"
                         "   The board printed that it was listening, so "
                         "something between\n   this machine and it is "
                         "dropping the connection." % (ip, port, last))
    t0 = time.monotonic()
    peer_closed = False
    close_error = ""
    with s:
        s.settimeout(30.0)
        s.sendall(data)
        queued_seconds = time.monotonic() - t0
        s.shutdown(socket.SHUT_WR)
        # A FIN is a transport observation, not the memory verdict. The
        # OS can keep draining queued bytes after this bounded wait.
        try:
            while s.recv(4096):
                pass
            peer_closed = True
        except socket.timeout:
            close_error = "peer-close wait timed out"
        except OSError as error:
            close_error = "peer-close wait failed: %s" % error
    return TransferTiming(queued_seconds, time.monotonic() - t0,
                          peer_closed, close_error)


BOARD_LINE = re.compile(r"Received\s+(\d+)\s+bytes.*?in\s+(\d+)\s+ms", re.S)
BOARD_HASH = re.compile(r"sha256\s+([0-9a-f]{64})")


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("image", nargs="?")
    ap.add_argument("--to", choices=["ram", "card"], default="ram")
    ap.add_argument("--boot", action="store_true")
    ap.add_argument("--reset", action="store_true")
    # --addr IS AN OVERRIDE, NOT A DEFAULT. Left alone, the address comes
    # from the board's own `map`; passing it says "put it here instead",
    # and the board still refuses an address that lands on itself with a
    # sentence naming the region and the windows.
    ap.add_argument("--addr", default=None)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--name", default=DEFAULT_NAME)
    ap.add_argument("--board-ip", default=None)
    # `wifi` and `net` are the same choice. The console stopped being a
    # radio-only thing on 2026-09-07 and the new word says so; the old one
    # keeps every script and every note that already exists working.
    ap.add_argument("--console", choices=["serial", "wifi", "net"],
                    default="serial")
    ap.add_argument("--com", default=DEFAULT_COM)
    ap.add_argument("--console-ip", default=None)
    ap.add_argument("--console-port", type=int, default=WIFI_CONSOLE_PORT)
    ap.add_argument("--cache", action="store_true")
    ap.add_argument("--keep-cache", action="store_true")
    ap.add_argument("--corrupt", nargs="?", const=-1, type=int, default=None)
    ap.add_argument("--verify-timeout", type=float, default=0.0,
                    dest="verify_timeout")
    ap.add_argument("-h", "--help", action="store_true")
    try:
        args = ap.parse_args()
    except SystemExit:
        print(__doc__)
        return 2
    if args.help or not args.image:
        print(__doc__)
        return 2 if not args.image else 0

    if not os.path.exists(args.image):
        print("!! there is no file at %s, so nothing was sent." % args.image)
        return 2
    data = open(args.image, "rb").read()
    if not data:
        print("!! %s is empty, so there is nothing to send." % args.image)
        return 2
    want = hashlib.sha256(data).hexdigest()
    addr = None
    if args.addr is not None:
        try:
            addr = int(args.addr, 16)
        except ValueError:
            print("!! --addr takes a hexadecimal address, and %s is not one."
                  % args.addr)
            return 2
        if addr < 0 or addr + len(data) > 1 << 64:
            print("!! Error 5: the image range does not fit an unsigned 64-bit "
                  "address. Check --addr and the file size. Nothing was sent.")
            return 2

    print("%s: %d bytes" % (args.image, len(data)))
    print("  host sha256 %s" % want)

    # THE NEGATIVE CONTROL.  `want` above is the digest of the REAL file
    # and is not recomputed, which is the whole point: the board is sent
    # something else and the comparison has to notice.  This models the
    # corrupting cable exactly - one bit, in the middle, with everything
    # either side of it perfect.
    on_wire = data
    if args.corrupt is not None:
        off = args.corrupt if args.corrupt >= 0 else len(data) // 2
        if off >= len(data):
            print("!! --corrupt %d is past the end of a %d-byte file."
                  % (off, len(data)))
            return 2
        b = bytearray(data)
        b[off] ^= 0x01
        on_wire = bytes(b)
        print("  !! --corrupt IS ARMED: bit 0 of byte %d is flipped ON THE "
              "WIRE, and the" % off)
        print("     comparison is still against the digest above. THIS RUN "
              "MUST FAIL.")
        print("     Nothing will be saved and nothing will be booted. It is "
              "a bench")
        print("     instrument and it is here because a verifier nobody has "
              "seen refuse")
        print("     is a verifier nobody has any reason to believe.")

    if args.console in ("wifi", "net"):
        ip = args.console_ip or args.board_ip
        if not ip:
            print("!! the network console needs an address: pass "
                  "--console-ip or --board-ip.")
            print("   On a board reached over the Ethernet cable that is "
                  "usually 192.168.137.x;")
            print("   python tools/anvil_wifi.py --find lists everything "
                  "that answers, with")
            print("   the interface on this machine that heard it.")
            return 2
        con = WifiConsole(ip, args.console_port)
    else:
        con = SerialConsole(args.com)
    print("  console: %s" % con.name)

    cache_state = CacheState(con, args.keep_cache)
    try:
        if not at_prompt(con):
            print("!! no Anvil prompt on %s. Is the board powered and is this "
                  "the right\n   console? Nothing was sent." % con.name)
            return 1

        board_ip = args.board_ip or board_address(con)
        if not board_ip:
            print("!! this board has no network address, so there is nowhere "
                  "to send to.\n   Type `wifi join` or `dhcp` on it first, or "
                  "pass --board-ip. Nothing\n   was sent.")
            return 1
        print("  board:   %s" % board_ip)

        # WHERE THE IMAGE GOES, AND WHAT IT MUST NOT LAND ON. Both out of
        # ONE `map`, asked here with the prompt already answering and
        # before the listener is armed - a monitor that will not say
        # where to stage is a run that must not start.
        board_map = read_map(command(con, "map", 10))
        if board_map is None:
            if addr is None:
                print(stage_help("the image"))
                return 1
            # An --addr was given, so there IS somewhere to put it; what
            # is missing is the check. That is a warning and not a
            # refusal, because a board too old to print a map is still a
            # board somebody may have to flash a new monitor onto.
            print("  !! this board did not answer `map`, so the staging "
                  "address at %X could\n     not be checked against its own "
                  "image. If it stops answering mid-upload,\n     that is "
                  "the first thing to suspect." % addr)
        elif addr is None:
            addr = board_map.stage
            if board_map.image_lo is None:
                print("  stage:   %08X (from the board's own map)" % addr)
            else:
                print("  stage:   %08X (from the board's own map; its image "
                      "is\n           %08X..%08X, %d bytes)"
                      % (addr, board_map.image_lo, board_map.image_hi,
                         board_map.image_bytes))
        else:
            print("  stage:   %08X (--addr, overriding the board's map, "
                  "which said %08X)" % (addr, board_map.stage))
            # ---- DO NOT STAGE ON TOP OF THE MONITOR THAT IS RUNNING ---
            # THE BOARD DOES NOT FALL OVER WHEN THIS HAPPENS, WHICH IS
            # THE WHOLE PROBLEM. Measured 2026-09-08: staging 2,105,296
            # bytes at 0x400000 on an image running to $00401607
            # overwrote its last 5,640 bytes. The board kept its address,
            # kept serving the laptop's lease and kept answering --find
            # in under two seconds, and could not execute a single
            # command - `reset` included - because the command names and
            # the `pmf> ` prompt are strings near the end of the image.
            # It cost a human at the power lead. A reachable board is not
            # a drivable one.
            #
            # NO OVERRIDE FLAG. --addr already is the way to say where it
            # goes; a flag beside this refusal would be the second path
            # the no-patching rule is about. And the check is against the
            # extent this same `map` printed rather than a second query
            # to `version`: the staging address and the extent are one
            # fact, and two round trips can disagree.
            hits = board_map.hits_image(addr, len(data))
            if hits is None:
                print("  !! this board printed a staging address but not "
                      "the extent of its own\n     image, so %X could not be "
                      "checked against it." % addr)
            elif hits:
                lo, hi = board_map.image_lo, board_map.image_hi
                print("!! REFUSING TO SEND: staging %d bytes at %X would "
                      "overwrite the monitor that is\n   running this "
                      "upload. Its image is %08X..%08X, and the %d bytes "
                      "would land\n   on %08X..%08X - an overlap of %d bytes."
                      % (len(data), addr, lo, hi, len(data),
                         addr, addr + len(data) - 1,
                         min(hi, addr + len(data) - 1) - max(lo, addr) + 1))
                print("   The board would keep answering and stop "
                      "understanding commands, because its\n   command names "
                      "are strings near the end of the image. Nothing was "
                      "sent.")
                print("   Leave --addr out and it goes to %08X, which is "
                      "where this board says to\n   put it."
                      % board_map.stage)
                return 1

        if args.cache:
            cache_state.enable()

        # ---- arm the listener ----------------------------------------
        cmd = "net recv %d %X" % (args.port, addr)
        print("  %s" % cmd)
        con.settle()
        con.send(cmd)
        out = con.read_until(["for ONE connection", "!!", "? net"], 12)
        if "for ONE connection" not in out:
            print("!! the board did not arm a listener, so nothing was sent. "
                  "It said:")
            print(indent(out))
            return 1

        # ---- the bytes -----------------------------------------------
        timing = stream(board_ip, args.port, on_wire)
        print(stream_report(len(on_wire), timing))

        # ---- the verdict, from the board -----------------------------
        # HOW LONG TO WAIT IS A FUNCTION OF THE IMAGE, not a constant.
        # The digest is the slow half with the caches off - SHA-256 is
        # 61 KB/s on this part there - so the wait is sized from a floor
        # of 40 KB/s plus half a minute of slack, and --verify-timeout
        # overrides it. A fixed number is wrong in both directions: too
        # small fails a big image on a cold board, and too large means a
        # board that has crashed holds this tool for minutes.
        wait = args.verify_timeout
        if wait <= 0:
            wait = 30.0 + len(on_wire) / 40000.0
        out += con.read_until(["sha256 ", "!!"], wait)
        got_len = None
        got_ms = None
        m = BOARD_LINE.search(out)
        if m:
            got_len = int(m.group(1))
            got_ms = int(m.group(2))
        h = BOARD_HASH.search(out)
        got_hash = h.group(1) if h else None

        print(indent(tail_of(out)))

        bad = []
        if got_len is None or got_hash is None:
            bad.append("the board never printed a length and a digest inside "
                       "%.0f s, so this transfer HAS NO VERDICT AT ALL - "
                       "which is not the same as a good one, and is treated "
                       "here as a failure. Raise --verify-timeout if the "
                       "image is large and the board's caches are off"
                       % wait)
        else:
            if got_len != len(data):
                bad.append("the board stored %d bytes and this file is %d"
                           % (got_len, len(data)))
            if got_hash != want:
                bad.append("the digests DIFFER:\n"
                           "     host  %s\n"
                           "     board %s" % (want, got_hash))
        if bad:
            print("!! THE UPLOAD DID NOT VERIFY, so nothing was saved and "
                  "nothing was booted.")
            for b in bad:
                print("   %s" % b)
            print("   What is in the board's memory at %X is NOT this file. "
                  "Do not boot it." % addr)
            return 1

        if got_ms > 0:
            rate = (len(data) / 1024.0) / (got_ms / 1000.0)
            print("  VERIFIED: %d bytes, sha256 equal, %d ms on the board "
                  "(%.0f KB/s)." % (got_len, got_ms, rate))
        else:
            print("  VERIFIED: %d bytes, sha256 equal, 0 ms at the board's "
                  "timer resolution; transfer rate unavailable." % got_len)

        # ---- onto the medium -----------------------------------------
        if args.to == "card":
            out = command(con, "save %s %X %X" % (args.name, addr, len(data)),
                          120, needles=["written.", "!!"])
            print(indent(tail_of(out)))
            if "written." not in out:
                print("!! THE SAVE DID NOT COMPLETE, so %s may be part old "
                      "and part new.\n   Write it again before this board is "
                      "reset, or it boots half an image." % args.name)
                return 1

        # ---- and enter it --------------------------------------------
        # Finish our temporary configuration before handing ownership to a
        # payload or a freshly booted monitor. Never change its new state.
        cache_state.restore()
        if args.boot:
            if args.to == "card":
                line = "boot %s" % args.name
            else:
                line = "boot mem %X" % addr
            print("  %s" % line)
            con.settle()
            con.send(line)
            print(indent(con.read_until(["## ", "!!", "pmf>"], 60)))

        if args.reset:
            print("  reset")
            con.settle()
            con.send("reset")
            print(indent(con.read_until(["pmf>"], 60)))
    finally:
        try:
            cache_state.restore()
        finally:
            con.close()
    return 0


def indent(text):
    return "\n".join("    " + l for l in text.strip().splitlines()) or "    -"


def tail_of(text, lines=24):
    ls = text.strip().splitlines()
    return "\n".join(ls[-lines:])


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ConsoleReplyError as error:
        print("!! " + str(error))
        sys.exit(1)

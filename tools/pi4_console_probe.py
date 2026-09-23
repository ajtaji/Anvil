#!/usr/bin/env python3
"""pi4_console_probe.py - measure whether Anvil's network console answers.

WHY THIS EXISTS. On 2026-09-08 the board pinged perfectly and its console
dropped most of the datagrams sent to it: ICMP 10 of 10, unicast UDP
`uptime` 3 of 12, broadcast `--find` sometimes silent. "Sometimes it
answers" is not a measurement and cannot tell a firmware receive filter
from a console ring that overruns, so this counts.

It runs three probes against the same board, back to back, and prints a
count and the round trip for each one:

  ICMP        does the IP layer answer at all - the control
  UNICAST     a command datagram to <ip>:5555, the path that drops
  BROADCAST   the same command to the subnet broadcast, which reaches
              the console through a different acceptance test

    python tools/pi4_console_probe.py <board-ip>
    python tools/pi4_console_probe.py <board-ip> --probes 20 --cmd uptime
    python tools/pi4_console_probe.py <board-ip> --only unicast
    python tools/pi4_console_probe.py <board-ip> --one-socket

THE SOCKET QUESTION IS AN EXPERIMENTAL VARIABLE, NOT A DETAIL. Anvil's
console takes whoever last sent it a datagram as its peer, so a probe
from a fresh source port re-registers the peer every time and a probe
that reuses one socket does not. Both are measured: `--one-socket` keeps
a single source port for the whole run. If the two counts differ, the
peer registration is in the fault path.

Every count is printed as "n of N" with the round trips behind it, and
the exit code is 0 whatever the board does - this is an instrument, and
a board that answers nothing is a reading, not a tool failure.
"""
import argparse
import os
import re
import socket
import statistics
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from console_out import relay_safe_output   # noqa: E402

relay_safe_output()

PORT = 5555


def bcast_for(ip):
    """The /24 broadcast address of the board's subnet.

    A /24 is an assumption and it is stated rather than hidden: every
    bench segment this project uses is one, and a probe sent to the
    wrong broadcast address looks exactly like a board that is deaf.
    """
    parts = ip.split(".")
    return ".".join(parts[:3] + ["255"])


def local_bind_for(ip):
    """The address on THIS machine that the routing table would use.

    Bound explicitly, because on a machine with a VPN up a socket bound
    to 0.0.0.0 can send the datagram down the tunnel and the board looks
    dead. Measured on this bench 2026-09-07.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect((ip, PORT))
        return probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()


def icmp_probe(ip, count, gap):
    """One ping per probe, so each is timed on its own like the others."""
    rtts = []
    got = 0
    for _ in range(count):
        t0 = time.time()
        if os.name == "nt":
            cmd = ["ping", "-n", "1", "-w", "2000", ip]
        else:
            cmd = ["ping", "-c", "1", "-W", "2", ip]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True,
                                 timeout=6).stdout
        except (OSError, subprocess.TimeoutExpired):
            out = ""
        ms = (time.time() - t0) * 1000.0
        if re.search(r"ttl=", out, re.I):
            got += 1
            rtts.append(ms)
        time.sleep(gap)
    return got, rtts


def udp_probe(ip, dest, count, gap, timeout, cmd, one_socket, local):
    """Send `cmd` and wait for anything back. One probe, THREE verdicts.

    THE ECHO IS THE ARRIVAL WITNESS AND THAT IS WHY IT IS COUNTED
    SEPARATELY. Anvil's console echoes the characters it is sent, one
    datagram at a time, before the command it spells has run. So:

      ANSWERED   the echo and the reply both came back - the whole path
                 worked
      ECHO ONLY  the datagram REACHED the console, was fed into the
                 keystroke ring, and the reply did not come back - the
                 loss is on the way OUT or in the command loop
      SILENT     nothing at all - the datagram did not reach the
                 console, or every datagram of the exchange was lost

    Counting them together, which is what this tool did for its first
    twenty probes, cannot tell an inbound loss from an outbound one -
    and those have entirely different causes and entirely different
    fixes. Returns (answered, echo_only, rtts).
    """
    rtts = []
    got = 0
    echoed_only = 0
    shared = None
    if one_socket:
        shared = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        shared.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        shared.bind((local or "0.0.0.0", 0))

    for _ in range(count):
        s = shared
        if s is None:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.bind((local or "0.0.0.0", 0))
        # Anything still in flight from the previous probe is not this
        # probe's answer. Drain before timing, or a late reply is
        # credited to the wrong datagram and the count comes out high.
        s.settimeout(0.0)
        while True:
            try:
                s.recvfrom(4096)
            except OSError:
                break
        s.settimeout(timeout)
        t0 = time.time()
        try:
            s.sendto((cmd + "\r").encode(), (dest, PORT))
        except OSError:
            if shared is None:
                s.close()
            time.sleep(gap)
            continue
        answered = False
        saw_echo = False
        end = t0 + timeout
        while time.time() < end:
            try:
                s.settimeout(max(0.05, end - time.time()))
                data, _addr = s.recvfrom(4096)
            except OSError:
                break
            text = data.decode("utf-8", "replace").strip()
            stripped = text.strip()
            if not stripped:
                continue
            # The console echoes the command a character at a time, so a
            # piece of the word we sent - "u", "upt", "uptime" - is the
            # echo and not the answer to it.
            if cmd.startswith(stripped):
                saw_echo = True
                continue
            answered = True
            rtts.append((time.time() - t0) * 1000.0)
            break
        if answered:
            got += 1
        elif saw_echo:
            echoed_only += 1
        if shared is None:
            s.close()
        time.sleep(gap)

    if shared is not None:
        shared.close()
    return got, echoed_only, rtts


def report(label, got, echo, count, rtts):
    line = "  %-10s %2d of %2d answered" % (label, got, count)
    if echo:
        line += ", %d more echoed and never replied" % echo
    if rtts:
        line += "   [rtt min %.0f ms, median %.0f ms, max %.0f ms]" % (
            min(rtts), statistics.median(rtts), max(rtts))
    print(line)
    return got, echo


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("ip")
    ap.add_argument("--probes", type=int, default=20)
    ap.add_argument("--cmd", default="uptime")
    ap.add_argument("--gap", type=float, default=0.8)
    ap.add_argument("--timeout", type=float, default=3.0)
    ap.add_argument("--only", default="all",
                    choices=["all", "icmp", "unicast", "broadcast"])
    ap.add_argument("--one-socket", action="store_true")
    ap.add_argument("--label", default="")
    ap.add_argument("-h", "--help", action="store_true")
    # Asked before parsing, because the board's address is required and
    # argparse would otherwise refuse `--help` alone for the missing ip.
    if "-h" in sys.argv[1:] or "--help" in sys.argv[1:]:
        print(__doc__)
        return 0
    args = ap.parse_args()

    local = local_bind_for(args.ip)
    print("Anvil console probe against %s:%d%s" %
          (args.ip, PORT, ("  [" + args.label + "]") if args.label else ""))
    print("  from this machine's %s, %d probes each, command %r, "
          "%s source port" %
          (local or "the routing table's choice", args.probes, args.cmd,
           "one" if args.one_socket else "a fresh"))
    print("")

    results = {}
    if args.only in ("all", "icmp"):
        got, rtts = icmp_probe(args.ip, args.probes, args.gap)
        results["icmp"] = (got, 0)
        report("ICMP", got, 0, args.probes, rtts)
    if args.only in ("all", "unicast"):
        got, echo, rtts = udp_probe(args.ip, args.ip, args.probes, args.gap,
                                    args.timeout, args.cmd, args.one_socket,
                                    local)
        results["unicast"] = (got, echo)
        report("UNICAST", got, echo, args.probes, rtts)
    if args.only in ("all", "broadcast"):
        b = bcast_for(args.ip)
        got, echo, rtts = udp_probe(args.ip, b, args.probes, args.gap,
                                    args.timeout, args.cmd, args.one_socket,
                                    local)
        results["broadcast"] = (got, echo)
        report("BROADCAST", got, echo, args.probes, rtts)

    print("")
    for k, (v, e) in results.items():
        print("RESULT %s answered %d/%d echo-only %d" % (k, v, args.probes, e))
    return 0


if __name__ == "__main__":
    sys.exit(main())

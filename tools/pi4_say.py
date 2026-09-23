#!/usr/bin/env python3
"""pi4_say.py - run one network console command, with retries.

The board's console dropped most of the datagrams sent to it on
2026-09-08 (forum 698), and on a lossy link it can again, so a tool
that sends a command once and reports "the board did not answer" is
measuring the defect rather than reading the board. This sends the command again until an answer comes back, says
how many attempts it took, and prints what the board said.

    python tools/pi4_say.py <board-ip> "net link"
    python tools/pi4_say.py <board-ip> "uptime" --tries 20

    --tries N       attempts before giving up (default 15)
    --timeout S     seconds to wait for each attempt's answer (default 3)
    --port N        the console's UDP port (default 5555)

It exits 0 with the board's answer, or 2 if no attempt was answered.

THE ATTEMPT COUNT IS PART OF THE OUTPUT, not noise to be swallowed. A
command that needed nine attempts and one that needed one are different
readings of the same board, and hiding that difference is how "the
console works" got written down while it was dropping three datagrams in
four.
"""
import argparse
import os
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from console_out import relay_safe_output   # noqa: E402

relay_safe_output()

PORT = 5555


def local_bind_for(ip):
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect((ip, PORT))
        return probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()


def say(ip, cmd, tries=15, timeout=3.0, quiet_for=0.7, port=PORT):
    """Returns (text, attempts) - text is "" when nothing ever answered."""
    local = local_bind_for(ip)
    for attempt in range(1, tries + 1):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.bind((local or "0.0.0.0", 0))
        buf = b""
        try:
            s.sendto((cmd + "\r").encode(), (ip, port))
            end = time.time() + timeout
            while time.time() < end:
                try:
                    s.settimeout(max(0.05, end - time.time()))
                    data, _ = s.recvfrom(4096)
                except OSError:
                    break
                buf += data
                end = time.time() + quiet_for
        finally:
            s.close()
        text = buf.decode("utf-8", "replace")
        # The echo alone is not an answer: the console echoes the command
        # before it runs it, so a reply that is only the echo means the
        # command was heard and its output was lost.
        body = "\n".join(ln for ln in text.splitlines()
                         if ln.strip() and ln.strip() != cmd)
        if body.strip():
            return text, attempt
        time.sleep(0.6)
    return "", tries


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("ip")
    ap.add_argument("cmd")
    ap.add_argument("--tries", type=int, default=15)
    ap.add_argument("--timeout", type=float, default=3.0)
    ap.add_argument("--port", type=int, default=PORT)
    if "-h" in sys.argv[1:] or "--help" in sys.argv[1:]:
        print(__doc__)
        return 0
    args = ap.parse_args()

    text, attempts = say(args.ip, args.cmd, args.tries, args.timeout,
                         port=args.port)
    if not text:
        print("!! %s did not answer %r in %d attempts."
              % (args.ip, args.cmd, attempts))
        return 2
    print("--- %r answered on attempt %d of %d ---"
          % (args.cmd, attempts, args.tries))
    sys.stdout.write(text)
    if not text.endswith("\n"):
        print("")
    return 0


if __name__ == "__main__":
    sys.exit(main())

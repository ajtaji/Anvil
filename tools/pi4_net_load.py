#!/usr/bin/env python3
"""pi4_net_load.py - put a KNOWN, MEASURED broadcast load on the segment.

WHY THIS EXISTS. On 2026-09-08 the cause of the console's datagram loss
was proven with a load control - 57% answered at rest, 20% under about a
hundred added broadcast frames a second, 13% under four hundred, and 60%
again when the load stopped - and the thing that generated that load was
never written down. So the after-half of the proof could not be taken
under the same conditions as the before-half, and on 2026-09-09 the fault
would not reproduce at all: the same unchanged image that answered 5 of
20 one night answered 20 of 20 the next, because the house was quiet.

A BOARD MEASURED UNDER THE WEATHER IS NOT MEASURED. The load is the
control, the control is half the reading, and a control that lives only
in a shell history is a control nobody else can run.

    python tools/pi4_net_load.py <board-ip> --rate 100 --seconds 30
    python tools/pi4_net_load.py <board-ip> --rate 400 --seconds 30

Run it in one window and tools/pi4_console_probe.py in another, or use
--seconds long enough to cover the probe run.

IT REPORTS THE RATE IT ACHIEVED, NOT THE RATE IT WAS ASKED FOR, and that
distinction is the whole reason the number is printed at all. A laptop
that cannot keep up with --rate 400 and says "400" would put a wrong
number beside a measured percentage forever. Python's sleep granularity
and the Wi-Fi driver's own pacing both bite well below a thousand frames
a second, so the achieved figure is routinely lower than the asked one
and the honest reading is the one the socket actually managed.

WHAT IT SENDS, and why it cannot be mistaken for real traffic: UDP to
the discard port (9, RFC 863) at the /24 broadcast address, carrying an
ASCII payload that names this tool. Nothing on the board binds port 9,
so every frame reaches the receive ring, is parsed by the IP layer and
is dropped as nobody's - which is exactly the house-broadcast chatter
being modelled. It is NOT sent to the console port: a load that the
console had to answer would be measuring a different thing.
"""
import argparse
import os
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from console_out import relay_safe_output   # noqa: E402

relay_safe_output()

# RFC 863. Nothing binds it on the board, so a datagram sent here costs
# the receive path exactly what a neighbour's broadcast costs it and
# nothing more.
DISCARD_PORT = 9

PAYLOAD = b"pi4_net_load - deliberate bench load, discard me"


def bcast_for(ip):
    """The /24 broadcast address of the board's subnet.

    A /24 is an assumption and it is stated rather than hidden, the same
    way tools/pi4_console_probe.py states it: every bench segment this
    project uses is one, and load sent to the wrong broadcast address is
    load the board never sees - which reads exactly like a board that is
    immune to load.
    """
    parts = ip.split(".")
    return ".".join(parts[:3] + ["255"])


def local_bind_for(ip):
    """The address on THIS machine the routing table would use.

    Bound explicitly for the reason pi4_console_probe.py gives: on a
    machine with a VPN up, a socket bound to 0.0.0.0 can send the
    datagram down the tunnel, and then the load never reaches the
    segment at all.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect((ip, DISCARD_PORT))
        return probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()


def run(ip, rate, seconds):
    dest = bcast_for(ip)
    local = local_bind_for(ip)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    if local:
        sock.bind((local, 0))

    print("broadcast load to %s:%d  asked for %d frames/s for %d s"
          % (dest, DISCARD_PORT, rate, seconds))
    if local:
        print("  from this machine's %s" % local)

    interval = 1.0 / float(rate)
    t0 = time.time()
    deadline = t0 + seconds
    sent = 0
    failed = 0
    # PACED AGAINST THE START, NOT AGAINST THE LAST FRAME. Sleeping a
    # fixed interval after each send accumulates every overshoot, so a
    # run asked for 400 a second drifts to a fraction of it over thirty
    # seconds and nothing says so. The target time for frame n is
    # t0 + n*interval, which cannot drift.
    while True:
        now = time.time()
        if now >= deadline:
            break
        target = t0 + sent * interval
        if target > now:
            time.sleep(min(target - now, deadline - now))
        try:
            sock.sendto(PAYLOAD, (dest, DISCARD_PORT))
            sent += 1
        except OSError:
            failed += 1
            # A radio out of transmit credit for a moment is ordinary and
            # is counted rather than raised; a run that failed every send
            # is a different reading and the count is what shows it.
            time.sleep(0.001)

    elapsed = time.time() - t0
    sock.close()

    achieved = sent / elapsed if elapsed > 0 else 0.0
    print("  SENT %d frames in %.1f s = %.0f frames/s ACHIEVED"
          % (sent, elapsed, achieved))
    if failed:
        print("  %d sends were refused by this machine's own stack" % failed)
    if achieved < rate * 0.8:
        print("  NOTE: this machine could not reach the asked-for rate. The")
        print("  achieved figure above is the one to quote beside a result.")
    return achieved


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("ip", help="the board's address - its /24 is the target")
    ap.add_argument("--rate", type=int, default=100,
                    help="frames a second to aim for (default 100)")
    ap.add_argument("--seconds", type=float, default=30.0,
                    help="how long to keep it up (default 30)")
    ap.add_argument("-h", "--help", action="help")
    a = ap.parse_args()
    if a.rate < 1:
        print("!! a rate below one frame a second is not a load, so nothing")
        print("   was sent.")
        return 2
    run(a.ip, a.rate, a.seconds)
    return 0


if __name__ == "__main__":
    sys.exit(main())

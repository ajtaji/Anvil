#!/usr/bin/env python3
"""anvil_wifi.py - talk to Anvil's network console over UDP.

Anvil listens on UDP port 5555 as soon as it has an address, on EVERY
interface that holds one and can carry a frame right now - the Ethernet
cable AND the Wi-Fi radio, both at once, neither displacing the other -
and answers each request out of the interface it arrived on, sourced from
the address it was sent to. Whoever sends it a datagram becomes the peer:
from then on everything the monitor prints comes back as UDP over the
interface that peer spoke on, and every line
you type is fed into its command input, exactly like the serial console.

    python tools/anvil_wifi.py <board-ip>          # interactive
    python tools/anvil_wifi.py <board-ip> "info"   # one command, print reply
    python tools/anvil_wifi.py --find              # who is out there?

THE NAME IS HISTORICAL. This script was written when the console could
only ride the radio, and the monitor called it the wireless console. It
is the NETWORK console now and the same script speaks to it either way -
same port, same datagrams. The file keeps its name so that every note,
script and forum post that already says `anvil_wifi.py` still works.

--find broadcasts one `version` and lists everything that answers, with
the address it answered from and the address of the interface on THIS
machine that heard it. That last part is the point on a bench with more
than one path to the board: an answer on 192.168.137.x is the board on
the Ethernet cable, an answer on 192.168.1.x is the same board over the
access point, and knowing which is which is the difference between a
working session and half an hour.

ONE BOARD ANSWERS MORE THAN ONCE NOW, and that is not a duplicate. Since
2026-09-07 the board holds an address on every interface at the same
time, so a Pi 4 with a cable and a radio answers twice - one ANSWERED
line per address it answered from. Measured 2026-09-08: 192.168.137.1 on
the cable, heard on this machine's 192.168.137.2 - a lease the Pi itself
handed out - and 192.168.1.12 on the radio. Both are live and either one
gives you a console.

    --find                 probe every directly connected IPv4 subnet of
                           this machine, plus 192.168.1.255 and
                           192.168.137.255 whether or not this machine is
                           on them
    --net A.B.C.D          probe this broadcast address instead. May be
                           given more than once.
    --timeout SECONDS      how long to listen for answers (default 2)
    --port N               the console's UDP port (default 5555)

The board prints every address the console is listening on, and which
link each one is over, in its own boot log, and `net` on the board says
the same thing at any time.
"""
import os
import socket
import struct
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# THIS TOOL PRINTS WHAT THE BOARD SAID, AND A BOARD CAN SAY ANYTHING.
# The reader below decodes with errors="replace", so a mangled byte
# becomes U+FFFD and cannot throw; WRITING it on a cp1252 console can,
# and that is the half that has to be stopped. See console_out.py for
# the two times this killed a tool in the middle of a flash.
from console_out import relay_safe_output   # noqa: E402

relay_safe_output()

PORT = 5555

# Probed by --find even when this machine is not on them, because they are
# where this project's boards live: the bench access point's segment, the
# address Windows connection sharing hands out on a cable straight between
# a PC and a board, and - since 2026-09-07 - the link-local block.
#
# 169.254.255.255 IS THE IMPORTANT ONE NOW, AND IT IS NOT A GUESS. When a
# cable runs straight from this PC into a board there is no DHCP server on
# it, so BOTH ends give themselves an address out of 169.254.0.0/16
# (RFC 3927): Windows calls it an "Autoconfiguration IPv4 Address" and the
# board takes one the same way, at boot, with nothing typed. This machine
# will normally be on that subnet and the enumerated list below finds it -
# it is written out here as well so that a PC whose interface table cannot
# be read still looks in the one place a board on a bare cable will be.
WELL_KNOWN_BROADCASTS = ["169.254.255.255", "192.168.1.255",
                         "192.168.137.255"]


# ----------------------------------------------------------------------
#  THIS MACHINE'S DIRECTLY CONNECTED IPv4 SUBNETS
#
#  Returns a list of (local_address, broadcast_address, how_we_know),
#  where how_we_know is "netmask" when the real netmask was read out of
#  the operating system and "assumed /24" when it could not be and the
#  broadcast address is a guess. THE GUESS IS LABELLED RATHER THAN
#  HIDDEN: a probe that went to the wrong broadcast address and found
#  nothing looks exactly like a board that is not there.
# ----------------------------------------------------------------------
def _local_subnets_windows():
    import ctypes
    from ctypes import wintypes

    class MIB_IPADDRROW(ctypes.Structure):
        _fields_ = [("dwAddr", wintypes.DWORD),
                    ("dwIndex", wintypes.DWORD),
                    ("dwMask", wintypes.DWORD),
                    ("dwBCastAddr", wintypes.DWORD),
                    ("dwReasmSize", wintypes.DWORD),
                    ("unused1", wintypes.USHORT),
                    ("wType", wintypes.USHORT)]

    iphlpapi = ctypes.WinDLL("iphlpapi.dll")
    size = wintypes.ULONG(0)
    # First call sizes the table; ERROR_INSUFFICIENT_BUFFER (122) is the
    # expected answer and not a failure.
    iphlpapi.GetIpAddrTable(None, ctypes.byref(size), False)
    buf = ctypes.create_string_buffer(size.value)
    rc = iphlpapi.GetIpAddrTable(buf, ctypes.byref(size), False)
    if rc != 0:
        raise OSError("GetIpAddrTable failed with code %d" % rc)
    count = struct.unpack("<I", buf.raw[:4])[0]
    rows = []
    row_size = ctypes.sizeof(MIB_IPADDRROW)
    for i in range(count):
        off = 4 + i * row_size
        row = MIB_IPADDRROW.from_buffer_copy(buf.raw[off:off + row_size])
        addr = socket.inet_ntoa(struct.pack("<I", row.dwAddr))
        mask = socket.inet_ntoa(struct.pack("<I", row.dwMask))
        rows.append((addr, mask))
    return rows


def _local_subnets_posix():
    import fcntl
    SIOCGIFNETMASK = 0x891B
    rows = []
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        for _idx, name in socket.if_nameindex():
            try:
                nb = name.encode()[:15]
                res = fcntl.ioctl(s.fileno(), SIOCGIFNETMASK,
                                  struct.pack("256s", nb))
                mask = socket.inet_ntoa(res[20:24])
            except OSError:
                continue
            try:
                # The address on the same interface.
                SIOCGIFADDR = 0x8915
                res = fcntl.ioctl(s.fileno(), SIOCGIFADDR,
                                  struct.pack("256s", nb))
                addr = socket.inet_ntoa(res[20:24])
            except OSError:
                continue
            rows.append((addr, mask))
    finally:
        s.close()
    return rows


def local_subnets():
    rows = []
    try:
        if sys.platform.startswith("win"):
            rows = _local_subnets_windows()
        else:
            rows = _local_subnets_posix()
        how = "netmask"
    except Exception:
        rows = []
        how = ""
    if not rows:
        # Last resort: the addresses this host answers to, with a /24
        # assumed. Said out loud in the listing.
        how = "assumed /24"
        seen = []
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None,
                                           socket.AF_INET):
                a = info[4][0]
                if a not in seen:
                    seen.append(a)
        except socket.gaierror:
            pass
        rows = [(a, "255.255.255.0") for a in seen]

    out = []
    for addr, mask in rows:
        if addr.startswith("127.") or addr == "0.0.0.0":
            continue
        if mask in ("0.0.0.0", "255.255.255.255"):
            continue
        a = struct.unpack(">I", socket.inet_aton(addr))[0]
        m = struct.unpack(">I", socket.inet_aton(mask))[0]
        b = (a | (~m & 0xFFFFFFFF)) & 0xFFFFFFFF
        out.append((addr, socket.inet_ntoa(struct.pack(">I", b)), how))
    return out


# ----------------------------------------------------------------------
#  WHICH OF THIS MACHINE'S ADDRESSES IS ON THE BOARD'S SEGMENT
#
#  Returns the local IPv4 address whose subnet contains `dest`, or None
#  when no interface on this machine is on it.
#
#  WHY A SOCKET HAS TO BE TOLD, 2026-09-07. This laptop has a Tailscale
#  interface and a second tunnel interface, both /32, and a VPN default
#  route. A UDP socket bound to 0.0.0.0 hands the choice of source
#  interface to the routing table, and the routing table on a machine
#  with a VPN up does not always choose the one the destination is
#  physically on - the datagram leaves down the tunnel, nothing answers,
#  and the board looks dead. Binding to the address that OWNS the
#  destination's subnet removes the choice: the source address selects
#  the interface, and there is nothing left to guess.
#
#  IT IS ADVICE, NOT A REQUIREMENT. When no interface is on the
#  destination's subnet this answers None and the caller binds to
#  0.0.0.0 as before, which is right - a board reached through a router
#  is not on any of our subnets and the routing table is then exactly
#  the right thing to ask.
# ----------------------------------------------------------------------
def local_bind_for(dest):
    try:
        d = struct.unpack(">I", socket.inet_aton(dest))[0]
    except OSError:
        return None
    for addr, mask in _rows_with_masks():
        try:
            a = struct.unpack(">I", socket.inet_aton(addr))[0]
            m = struct.unpack(">I", socket.inet_aton(mask))[0]
        except OSError:
            continue
        if m in (0, 0xFFFFFFFF):
            # A /32 is a tunnel endpoint, not a segment. Matching one
            # would bind every datagram to the VPN, which is the exact
            # failure this function exists to prevent.
            continue
        if (a & m) == (d & m):
            return addr
    return None


def _rows_with_masks():
    """(address, netmask) for every IPv4 interface, or [] if unreadable."""
    try:
        if sys.platform.startswith("win"):
            rows = _local_subnets_windows()
        else:
            rows = _local_subnets_posix()
    except Exception:
        return []
    return [(a, m) for a, m in rows if not a.startswith("127.")
            and a != "0.0.0.0"]


def bound_udp_socket(dest, broadcast=False):
    """A UDP socket bound to the interface that reaches `dest`.

    Returns (socket, local_address_or_None). The caller prints the
    second one: a session that went out of the wrong interface and a
    board that is not there look identical, and saying which address the
    datagrams left from is the difference.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if broadcast:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    local = local_bind_for(dest)
    try:
        s.bind((local or "0.0.0.0", 0))
    except OSError:
        # The address went away between reading the table and binding.
        # Fall back rather than fail: the routing table's answer is
        # still usually right.
        local = None
        s.bind(("0.0.0.0", 0))
    return s, local


# ----------------------------------------------------------------------
#  --find
#
#  One `version` to every broadcast address, from a socket bound to the
#  local address that owns it where there is one, so that an answer can
#  be attributed to the interface that heard it. A board on two paths
#  answers twice, at two different addresses, and BOTH are printed -
#  telling the operator they are the same board is not this script's job
#  and guessing at it would be the quiet wrong answer.
# ----------------------------------------------------------------------
def find(targets, port, timeout):
    probes = []
    subnets = local_subnets()
    known = {}
    for local, bcast, how in subnets:
        known[bcast] = (local, how)

    if targets:
        for t in targets:
            local, how = known.get(t, (None, "asked for"))
            probes.append((local, t, how))
    else:
        for local, bcast, how in subnets:
            probes.append((local, bcast, how))
        for b in WELL_KNOWN_BROADCASTS:
            if not any(p[1] == b for p in probes):
                probes.append((None, b, "well known"))

    if not probes:
        print("!! there is no IPv4 address on this machine to broadcast from,")
        print("   so nothing was probed. Check the network connection, or pass")
        print("   --net <broadcast address> to say where to look.")
        return 2

    print("Looking for an Anvil console on UDP port %d." % port)
    answers = []
    lock = threading.Lock()
    socks = []

    for local, bcast, how in probes:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            s.bind((local or "0.0.0.0", 0))
        except OSError as exc:
            print("  %-15s could not be used to send: %s" % (local, exc))
            s.close()
            continue
        note = how
        if local:
            print("  %-15s -> %-15s  (%s)" % (local, bcast, note))
        else:
            print("  %-15s -> %-15s  (%s)" % ("any interface", bcast, note))
        socks.append((s, local or "any interface", bcast))

    def listen(s, local):
        while True:
            try:
                data, addr = s.recvfrom(4096)
            except OSError:
                return
            text = data.decode("utf-8", "replace").strip()
            with lock:
                answers.append((addr[0], local, text))

    for s, local, _bcast in socks:
        threading.Thread(target=listen, args=(s, local), daemon=True).start()

    for s, _local, bcast in socks:
        try:
            s.sendto(b"version\r", (bcast, port))
        except OSError as exc:
            print("  the probe to %s did not go out: %s" % (bcast, exc))

    time.sleep(timeout)
    for s, _local, _bcast in socks:
        s.close()

    if not answers:
        print("")
        print("Nothing answered in %.1f seconds." % timeout)
        print("A board that is powered and joined but on a subnet none of the")
        print("addresses above reaches will not be found here - pass")
        print("--net <its broadcast address> if you know where it is. A board")
        print("whose console has not armed answers nothing at all: put a cable")
        print("in and run dhcp on it over the serial line, or check its boot log.")
        return 1

    print("")
    # EVERY DATAGRAM FROM ONE BOARD, JOINED, NOT JUST THE FIRST.
    #
    # The console sends a line per datagram, and since 2026-09-07 it also
    # delivers its SHORT lines - short console replies used to be runt
    # Ethernet frames and were discarded, so the first datagram to arrive
    # happened to be the first long one. It is now the board's ECHO of
    # the word this script sent it, and printing only the first answer
    # made --find report "version" instead of the build it was asked for.
    # Joining them is what the operator wanted in the first place.
    order = []
    joined = {}
    for board, local, text in answers:
        key = (board, local)
        if key not in joined:
            joined[key] = []
            order.append(key)
        joined[key].append(text)
    for key in order:
        board, local = key
        print("ANSWERED: %s   heard on this machine's %s" % (board, local))
        shown = 0
        for text in joined[key]:
            for line in text.splitlines():
                s = line.rstrip()
                # THE BOARD ECHOES WHAT IT WAS SENT, and it echoes it a
                # character at a time - so the echo can arrive split
                # across datagrams as "v" then "ersion". Anything that is
                # a piece of the word we sent is not an answer to it.
                t = s.strip()
                if not t or (t and "version".startswith(t)):
                    continue
                print("    %s" % s)
                shown += 1
                if shown >= 6:
                    break
            if shown >= 6:
                break
    print("")
    print("Talk to one with:  python tools/anvil_wifi.py <address>")
    return 0


def main():
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        return 1

    do_find = False
    nets = []
    timeout = 2.0
    port = PORT
    rest = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--find":
            do_find = True
        elif a == "--net":
            i += 1
            if i >= len(argv):
                print("!! --net needs a broadcast address after it, so nothing "
                      "was done.")
                return 2
            nets.append(argv[i])
        elif a == "--timeout":
            i += 1
            if i >= len(argv):
                print("!! --timeout needs a number of seconds after it, so "
                      "nothing was done.")
                return 2
            timeout = float(argv[i])
        elif a == "--port":
            i += 1
            if i >= len(argv):
                print("!! --port needs a UDP port number after it, so nothing "
                      "was done.")
                return 2
            port = int(argv[i])
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        elif a.startswith("-"):
            print("!! %s is not an option this script has, so nothing was "
                  "done. Run it with --help." % a)
            return 2
        else:
            rest.append(a)
        i += 1

    if do_find or (nets and not rest):
        return find(nets, port, timeout)

    if not rest:
        print(__doc__)
        return 1

    ip = rest[0]
    oneshot = rest[1] if len(rest) > 1 else None

    # BOUND TO THE INTERFACE THAT ACTUALLY REACHES THE BOARD. See
    # local_bind_for: on a machine with a VPN up, a socket bound to
    # 0.0.0.0 can send the datagram down the tunnel and the board looks
    # dead. Measured on this bench, 2026-09-07.
    s, local = bound_udp_socket(ip)

    if oneshot is not None:
        # Register as the peer, send the command, collect for a moment.
        s.sendto((oneshot + "\r").encode(), (ip, port))
        s.settimeout(0.4)
        buf = b""
        end = time.time() + 3.0
        while time.time() < end:
            try:
                data, _ = s.recvfrom(4096)
                buf += data
                end = time.time() + 0.5   # keep going while it streams
            except socket.timeout:
                if buf:
                    break
        sys.stdout.write(buf.decode("utf-8", "replace"))
        sys.stdout.flush()
        if not buf:
            print("")
            print("!! %s:%d did not answer." % (ip, port))
            if local:
                print("   The datagram went out from this machine's %s, which "
                      "is on that" % local)
                print("   subnet, so it reached the segment. A board whose "
                      "console has not")
                print("   armed answers nothing at all - check its boot log, "
                      "or run")
                print("   --find to see what is out there.")
            else:
                print("   NO INTERFACE ON THIS MACHINE IS ON THAT SUBNET, so "
                      "the datagram")
                print("   was handed to the routing table and may have left "
                      "down a VPN or")
                print("   a default route rather than towards the board. Run "
                      "--find.")
            return 2
        return 0

    # Interactive. A reader thread prints; the main thread sends stdin.
    print("connected to %s:%d - type commands, Ctrl-C to quit" % (ip, port))
    if local:
        print("  from this machine's %s, which is on the board's subnet"
              % local)
    else:
        print("  NOTE: no address on this machine is on %s's subnet, so the "
              "routing" % ip)
        print("  table chooses the interface. On a machine with a VPN up "
              "that is not")
        print("  always the one the board is on.")
    s.sendto(b"\r", (ip, port))   # nudge the board so it learns our address

    def reader():
        while True:
            try:
                data, _ = s.recvfrom(4096)
            except OSError:
                return
            sys.stdout.write(data.decode("utf-8", "replace"))
            sys.stdout.flush()

    threading.Thread(target=reader, daemon=True).start()
    try:
        for line in sys.stdin:
            s.sendto(line.rstrip("\n").encode() + b"\r", (ip, port))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())

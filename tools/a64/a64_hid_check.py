#!/usr/bin/env python3
"""Executable gate for RaspberryPi4/Lib/hid.pi4 and for the hub and
route-string additions to RaspberryPi4/Lib/xhci.pi4.

There is no keyboard on this bench, so the BUS is fabricated: an xHCI
controller with a high-speed HUB permanently on root port 1 - which is
what a Raspberry Pi 4 really has, observed on silicon 2026-08-26 as
$2109:$3431 class 09 - a low-speed keyboard and a full-speed composite
keyboard-plus-mouse behind that hub, a HID device that is NOT boot
protocol so the refusal path executes, and a SuperSpeed mass-storage
device on a root port so the walk has something to step over.  The real
driver is compiled and executed against it on the project's A64 oracle
(tools/a64/a64_interp).

Nothing here touches hardware, a PCIe link, or a USB device.

=====================================================================
WHAT THIS GATE CANNOT FAIL ON.  Read this before believing a pass.
=====================================================================
The honest list is longer than the list of what it proves.

  * SILICON.  Every register value, every descriptor and every report
    below was written alongside the driver, from the same documents.
    A shared misreading of the specification passes here and fails on
    the bench.  The specific places that could hide
    one: whether the VL805's internal hub is single- or multi-TT (this
    model says single, and so does the driver, and NOTHING HAS ASKED
    THE PART); and whether Configure Endpoint with only the slot flag
    is accepted by that particular controller.

    ONE ITEM CAME OFF THIS LIST ON 2026-08-28 - "whether a real
    keyboard answers GET_REPORT at all promptly".  It does: 8 bytes in
    2 ms from the keyboard interface of a wireless receiver behind the
    VL805's hub, 4 bytes in 0 ms from its mouse interface, idle, on
    silicon.  hid.pi4's header carries the numbers and what they do not
    cover.

  * A STALL RECOVERY THAT WORKS ON PAPER.  This model DOES now halt
    endpoint 0 on a stall and refuse to run a ring while it is halted,
    which is the trap that cost this project a day - see
    Composite.idle_refused_ifaces and Ctl.run_ep0.  What it cannot check
    is whether the VL805 accepts a Reset Endpoint and a Set TR Dequeue
    Pointer aimed the way xh_ClearHalt aims them.  That part was proven
    on the board, not here.

  * LATENCY.  The whole design decision in hid.pi4 rests on polling
    being fast enough, and this model's notion of time is a counter
    that advances a fixed amount per interpreter instruction.  The
    numbers HidPollMeanUs() produces here are arithmetic, not
    measurement.  The gate checks that the INSTRUMENT is wired up - the
    count matches the polls, the worst case is not below the mean - and
    that is all it can check.  The measurement itself needs the board.

  * A REAL DEVICE'S BAD BEHAVIOUR.  The keyboard modelled here answers
    every request correctly and on time.  It never NAKs, never returns
    a short report, never disconnects.  Real ones do all three.
    It DOES stall now - the composite device's mouse interface refuses
    SET_IDLE, which is what the receiver on the bench does and what HID
    1.11 Appendix G permits - because until 2026-08-28 every modelled
    device answered everything, and the gate was green through the
    entire life of a bug that made one refused SET_IDLE take down every
    interface on the device.  A model whose devices are all
    well-behaved is a model that cannot find the bugs that matter.

  * CACHE COHERENCY.  The interpreter has one flat coherent memory.
    Every `dc cvac` and `dc civac` in xhci.pi4 is a no-op here.  This is
    the same hole a64_xhci_check.py has and it is not closed.

  * THE FIRMWARE TAKEOVER PATH.  The self-test stubs pcie.pi4's
    ownership seam as a cold controller nothing adopted, so
    XhciQuiesceAdopted() is compiled and never runs here.

  * THE HUB'S ELECTRICAL BEHAVIOUR.  Port power really switching,
    debounce, over-current, a device that enumerates at the wrong speed
    because of a bad cable.  The model's ports switch instantly and
    perfectly.

  * WHETHER THE ROUTE STRING IS WHAT THE VL805 WANTS.  The model checks
    the route string against the topology IT invented.  If the real
    controller numbers its downstream ports differently, both the model
    and the driver are consistently wrong together.

What it DOES prove, and these are worth having:

  * that a keyboard behind a hub is reachable AT ALL - the driver never
    resets a root port and calls it a keyboard;
  * THAT A LEGAL STALL DOES NOT KILL THE DEVICE.  The composite
    device's mouse interface stalls SET_IDLE during its attach; the
    model halts endpoint 0 for it, as xHCI 1.1 section 4.8.3 says a
    controller does, and refuses every doorbell on that endpoint until
    a Reset Endpoint and a Set TR Dequeue Pointer have run.  Every
    later assertion in this file - the second interface's attach, all
    eighteen scripted reports, the LED writes - is therefore a transfer
    on a pipe that had to be recovered first.  The `no-clear-halt`
    breakage is the same driver without that recovery, and it is the
    bug that was on silicon on 2026-08-28;
  * that the hub's slot context is marked DEV_HUB, with the right port
    count and think time, BEFORE any device behind it is addressed.
    The model refuses to route a transfer to a device behind an
    unmarked hub, which is what real silicon does by simply not
    scheduling the split transaction;
  * that the TT Hub Slot ID and TT Port Number in a low-speed device's
    slot context name the hub and the port it is actually on;
  * that SET_PROTOCOL(boot) is issued before the first GET_REPORT.  The
    modelled keyboard answers with a DIFFERENT, longer, Report-ID-
    prefixed report until it is switched, which is exactly how a real
    keyboard with media keys behaves and exactly the bug that passes on
    the bench keyboard and fails on the next one;
  * that the boot report decode is right, including the three things
    HID 1.11 Appendix C warns about: array order carries no meaning,
    the phantom rollover state must be discarded, and the report is
    state and not events.  The expectations are computed by a SECOND
    decoder, in this file, written from the specification rather than
    transcribed from the driver;
  * that every wide access the driver makes is aligned.  That rule now
    lives in a64_interp.py's align_guard() and is called from the
    closures below; the `misaligned-report-read` mutation proves it is
    load-bearing here and not merely present.

Usage:
    python tools/a64/a64_hid_check.py --compiler <PureMetalForge.exe>
        [--break <name>] [--no-breaks]

Run with --break <name> to injure the driver deliberately and watch the
gate go red.  See BREAKAGES below.  Every broken copy is generated at run
time into a temporary directory from the real hid.pi4 or xhci.pi4 by an
anchored substitution; nothing is written into the tree.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
from a64_interp import A64, attach_symbols  # noqa: E402
import sys as _pmfsys
import pathlib as _pmfpath
_pmfsys.path.insert(0, str(_pmfpath.Path(__file__).resolve().parents[1]))
from pmf_compiler import resolve_compiler  # noqa: E402

LOAD = 0x200000
SRC = ROOT / "RaspberryPi4" / "Examples" / "Diagnostics" / "pi4HidSelfTest.pi4"
LIB_HID = ROOT / "RaspberryPi4" / "Lib" / "hid.pi4"
LIB_XHCI = ROOT / "RaspberryPi4" / "Lib" / "xhci.pi4"

# The two fabricated windows, identical to a64_xhci_check.py's so that
# the two gates present the same machine to the same driver.
CFG_BASE = 0x700000000
CFG_SIZE = 0x10000000
CAP_BASE = 0x600000000
CAP_SIZE = 0x4000

# ---------------------------------------------------------------------
# The controller's capability registers.  Same numbers as the xHCI gate
# except MAX_PORTS, which is 4 here: this model's board has four root
# ports and the hub is on the first of them.
# ---------------------------------------------------------------------
CAPLENGTH = 0x20
HCIVERSION = 0x0100
MAX_SLOTS = 32
MAX_INTRS = 1
MAX_PORTS = 4
ERST_MAX = 4
SCRATCHPADS = 4
CTX_SIZE = 32
DBOFF = 0x800
RTSOFF = 0x600

CAPBASE_VAL = (HCIVERSION << 16) | CAPLENGTH
HCS1 = MAX_SLOTS | (MAX_INTRS << 8) | (MAX_PORTS << 24)
HCS2 = (ERST_MAX << 4) | ((SCRATCHPADS & 0x1F) << 27)
HCS3 = 0
HCC1 = 0x09                      # AC64 | PPC, 32-byte contexts

OP = CAPLENGTH
R_USBCMD = OP + 0x00
R_USBSTS = OP + 0x04
R_PAGESIZE = OP + 0x08
R_DNCTRL = OP + 0x14
R_CRCR = OP + 0x18
R_DCBAAP = OP + 0x30
R_CONFIG = OP + 0x38
R_PORTS = OP + 0x400

IR0 = RTSOFF + 0x20
R_IMAN = IR0 + 0x00
R_IMOD = IR0 + 0x04
R_ERSTSZ = IR0 + 0x08
R_ERSTBA = IR0 + 0x10
R_ERDP = IR0 + 0x18

CMD_RUN = 1 << 0
CMD_RESET = 1 << 1
STS_HALT = 1 << 0
STS_CNR = 1 << 11

P_CONNECT = 1 << 0
P_PE = 1 << 1
P_RESET = 1 << 4
P_POWER = 1 << 9
P_CSC = 1 << 17
P_PEC = 1 << 18
P_RC = 1 << 21

SPEED_FS = 1
SPEED_LS = 2
SPEED_HS = 3
SPEED_SS = 4

# Slot context bit positions - xhci.h:517-563.  Duplicated here rather
# than imported from the driver, on purpose: a model that reads its
# expectations out of the thing it is testing agrees with any mistake.
DEV_MTT = 1 << 25
DEV_HUB = 1 << 26

CNTFRQ = 54_000_000
TICK_STEP = 65536
BREAK_BUDGET = 12_000_000

# USB port status bits, USB 2.0 chapter 11 via usb_defs.h:273-283.
PS_CONNECTION = 0x0001
PS_ENABLE = 0x0002
PS_RESET = 0x0010
PS_POWER = 0x0100
PS_LOW_SPEED = 0x0200
PS_HIGH_SPEED = 0x0400
PC_CONNECTION = 0x0001
PC_RESET = 0x0010

PF_RESET = 4
PF_POWER = 8
PF_C_CONNECTION = 16
PF_C_RESET = 20


def le16(v: int) -> list[int]:
    return [v & 0xFF, (v >> 8) & 0xFF]


def devdesc(cls: int, sub: int, proto: int, vid: int, pid: int,
            mps0: int) -> bytes:
    """USB 2.0 table 9-8."""
    return bytes([18, 1] + le16(0x0200) + [cls, sub, proto, mps0]
                 + le16(vid) + le16(pid) + le16(0x0100) + [0, 0, 0, 1])


def iface(num: int, neps: int, cls: int, sub: int, proto: int) -> list[int]:
    """USB 2.0 table 9-12."""
    return [9, 4, num, 0, neps, cls, sub, proto, 0]


def hiddesc() -> list[int]:
    """HID 1.11 section 6.2.1.  Present because a real HID interface has
    one between its interface and endpoint descriptors, and a descriptor
    walk that does not step over unknown types would trip on it."""
    return [9, 0x21] + le16(0x0111) + [0, 1, 0x22] + le16(63)


def epdesc(addr: int, mps: int, interval: int, xfer: int = 3) -> list[int]:
    """USB 2.0 table 9-13."""
    return [7, 5, addr, xfer] + le16(mps) + [interval]


def config(value: int, ifaces: list[list[int]]) -> bytes:
    body: list[int] = []
    for chunk in ifaces:
        body += chunk
    total = 9 + len(body)
    head = [9, 2] + le16(total) + [len({b for b in ()}) or 0, value, 0,
                                   0xA0, 50]
    # bNumInterfaces, counted properly rather than guessed.
    head[4] = sum(1 for chunk in ifaces if chunk and chunk[1] == 4)
    return bytes(head + body)


# =====================================================================
#  THE DEVICES
# =====================================================================
class Dev:
    """A USB device on the modelled bus.

    Every device answers control transfers and nothing else.  `state`
    tracks ADDRESS versus CONFIGURED, because a device that answers
    interface requests before SET_CONFIGURATION is a model more
    forgiving than the specification (USB 2.0 section 9.4) and would let
    a driver skip a step that matters.
    """

    speed = SPEED_FS
    name = "device"

    def __init__(self) -> None:
        self.configured = 0
        self.protocol = 1        # HID: 1 = REPORT protocol, the default
        self.idle = {}
        self.leds = None
        self.log: list[str] = []

    def descriptor(self, dtype: int, index: int) -> bytes | None:
        return None

    def control(self, ctl: "Ctl", rt: int, req: int, val: int, idx: int,
                length: int, buf: int):
        """Return (completion_code, bytes_written) or (code, payload)."""
        # ---- standard, device recipient
        if rt == 0x80 and req == 6:
            d = self.descriptor((val >> 8) & 0xFF, val & 0xFF)
            if d is None:
                return 6, b""            # Stall
            return 1, d[:length]
        if rt == 0x00 and req == 9:      # SET_CONFIGURATION
            self.configured = val & 0xFF
            self.log.append(f"set-config={self.configured}")
            return 1, b""
        return self.class_control(ctl, rt, req, val, idx, length, buf)

    def class_control(self, ctl, rt, req, val, idx, length, buf):
        return 6, b""


class HidDev(Dev):
    """A HID device.  Reports are scripted; which script is used depends
    on whether SET_PROTOCOL(boot) has been issued, which is the whole
    point of modelling the protocol state at all."""

    boot_capable = True

    def __init__(self, reports: list[bytes], report_proto: bytes) -> None:
        super().__init__()
        self.reports = reports
        self.report_proto = report_proto
        self.next = 0
        self.set_protocol_seen = False
        self.set_idle_seen = False
        self.accepts_set_idle = True

    def class_control(self, ctl, rt, req, val, idx, length, buf):
        if rt == 0xA1 and req == 0x01:               # GET_REPORT
            if not self.configured:
                ctl.bad(f"{self.name}: GET_REPORT before SET_CONFIGURATION")
                return 6, b""
            if self.protocol == 1:
                # STILL IN REPORT PROTOCOL.  A real keyboard with media
                # keys answers with its own report, which here carries a
                # leading Report ID and is a different length.  A driver
                # that never issued SET_PROTOCOL decodes this as a boot
                # report and gets nonsense - which is the bug this whole
                # branch exists to make visible.
                return 1, self.report_proto[:length]
            r = self.reports[min(self.next, len(self.reports) - 1)]
            self.next += 1
            return 1, r[:length]
        if rt == 0x21 and req == 0x0B:               # SET_PROTOCOL
            if not self.configured:
                ctl.bad(f"{self.name}: SET_PROTOCOL before SET_CONFIGURATION")
                return 6, b""
            self.protocol = val & 0xFF
            self.set_protocol_seen = True
            self.log.append(f"set-protocol={self.protocol}")
            return 1, b""
        if rt == 0x21 and req == 0x0A:               # SET_IDLE
            if not self.accepts_set_idle:
                return 6, b""
            self.set_idle_seen = True
            self.idle[val & 0xFF] = (val >> 8) & 0xFF
            return 1, b""
        if rt == 0x21 and req == 0x09:               # SET_REPORT
            if not self.configured:
                return 6, b""
            self.leds = ctl.rd(buf, 1) if length >= 1 else 0
            self.log.append(f"leds={self.leds:02X}")
            return 1, b""
        return 6, b""


class Keyboard(HidDev):
    name = "keyboard"
    speed = SPEED_LS

    def descriptor(self, dtype, index):
        if dtype == 1:
            # HID 1.11 Appendix E.1's example device descriptor is a
            # keyboard with class 0 at the device level and class 3 on
            # the interface, which is what real keyboards do.
            return devdesc(0, 0, 0, 0x413C, 0x2107, 8)
        if dtype == 2:
            return config(1, [iface(0, 1, 3, 1, 1), hiddesc(),
                              epdesc(0x81, 8, 10)])
        return None


class Composite(HidDev):
    """One device, two boot interfaces: a mouse on interface 0 and a
    keyboard on interface 1.  This is the ordinary wireless dongle, and
    it is here because a driver that attaches the first HID interface
    and stops loses half of one."""

    name = "composite"
    speed = SPEED_FS

    def __init__(self, mouse_reports, kbd_reports, report_proto):
        super().__init__(mouse_reports, report_proto)
        self.kbd_reports = kbd_reports
        self.kbd_next = 0
        self.protocol_by_iface = {0: 1, 1: 1}
        # THE MOUSE INTERFACE STALLS SET_IDLE, and that is not the model
        # being awkward.  HID 1.11 Appendix G makes Set_Idle required for
        # keyboards and optional for everything else, and the wireless
        # receiver on this bench refuses it on its mouse interface -
        # measured 2026-08-28, HidIdleAccepted() came back 0 for that
        # handle and 1 for the keyboard's.
        #
        # It is modelled because of what the refusal COSTS, not because
        # of the refusal.  A stall halts endpoint 0, endpoint 0 belongs
        # to the DEVICE and not to an interface, and until 2026-08-28
        # nothing cleared it - so one legal refusal on one interface
        # silently killed both.  Before this line existed every modelled
        # device answered every request and the gate was green through
        # the whole of that bug.
        self.idle_refused_ifaces = {0}

    def descriptor(self, dtype, index):
        if dtype == 1:
            return devdesc(0, 0, 0, 0x046D, 0xC52B, 8)
        if dtype == 2:
            return config(1, [iface(0, 1, 3, 1, 2), hiddesc(),
                              epdesc(0x81, 4, 10),
                              iface(1, 1, 3, 1, 1), hiddesc(),
                              epdesc(0x82, 8, 8)])
        return None

    def class_control(self, ctl, rt, req, val, idx, length, buf):
        # Everything here is per-interface, which is the difference that
        # matters: wIndex selects which.
        if rt == 0x21 and req == 0x0B:
            if not self.configured:
                return 6, b""
            self.protocol_by_iface[idx] = val & 0xFF
            self.set_protocol_seen = True
            return 1, b""
        if rt == 0xA1 and req == 0x01:
            if not self.configured:
                return 6, b""
            if self.protocol_by_iface.get(idx, 1) == 1:
                return 1, self.report_proto[:length]
            if idx == 0:
                r = self.reports[min(self.next, len(self.reports) - 1)]
                self.next += 1
            else:
                r = self.kbd_reports[min(self.kbd_next,
                                         len(self.kbd_reports) - 1)]
                self.kbd_next += 1
            return 1, r[:length]
        if rt == 0x21 and req == 0x0A:               # SET_IDLE
            if idx in self.idle_refused_ifaces:
                return 6, b""                        # Stall - and legal
            self.set_idle_seen = True
            self.idle[val & 0xFF] = (val >> 8) & 0xFF
            return 1, b""
        return super().class_control(ctl, rt, req, val, idx, length, buf)


class NonBootHid(HidDev):
    """A HID device with bInterfaceSubClass 0 - no boot protocol.  It
    must be REFUSED by HidAttach, and the walk must carry on past it."""

    name = "nonboot"
    speed = SPEED_FS

    def descriptor(self, dtype, index):
        if dtype == 1:
            return devdesc(0, 0, 0, 0x0000, 0x0001, 8)
        if dtype == 2:
            return config(1, [iface(0, 1, 3, 0, 0), hiddesc(),
                              epdesc(0x81, 16, 10)])
        return None


class MassStorage(Dev):
    """A SuperSpeed stick on a root port.  Present so that the walk has
    a non-HID device to step over, which is the boot stick's real role
    on this bench."""

    name = "stick"
    speed = SPEED_SS

    def descriptor(self, dtype, index):
        if dtype == 1:
            return devdesc(0, 0, 0, 0x090C, 0x1000, 9)
        if dtype == 2:
            return config(1, [iface(0, 2, 8, 6, 0x50),
                              epdesc(0x01, 1024, 0, xfer=2),
                              epdesc(0x82, 1024, 0, xfer=2)])
        return None


class Hub(Dev):
    """A USB 2.0 hub, USB 2.0 chapter 11.

    THE PORTS DO NOT REPORT A CONNECTION UNTIL THEY ARE POWERED, which
    is the behaviour that catches a driver that skips
    SetPortFeature(PORT_POWER).  Nothing on an unpowered port is
    visible, so such a driver finds an empty hub and reports no
    keyboard - and would otherwise pass against a model whose ports were
    always live.
    """

    name = "hub"
    speed = SPEED_HS

    def __init__(self, children: dict[int, Dev], nports: int = 4,
                 tttt: int = 1, protocol: int = 1) -> None:
        super().__init__()
        self.children = children
        self.nports = nports
        self.tttt = tttt            # the two-bit field, before shifting
        self.protocol = protocol    # bDeviceProtocol: 1 single TT
        self.powered = {i: False for i in range(1, nports + 1)}
        self.reset_done = {i: False for i in range(1, nports + 1)}
        self.change = {i: 0 for i in range(1, nports + 1)}
        self.pgood = 5              # bPwrOn2PwrGood, 2 ms units -> 10 ms

    def descriptor(self, dtype, index):
        if dtype == 1:
            return devdesc(9, 0, self.protocol, 0x2109, 0x3431, 64)
        if dtype == 2:
            return config(1, [iface(0, 1, 9, 0, 0), epdesc(0x81, 1, 12)])
        if dtype == 0x29:
            # USB 2.0 table 11-13.  wHubCharacteristics carries the TT
            # think time in bits 6:5; the rest is per-port power
            # switching and per-port over-current, which is what a real
            # hub reports and what makes the field non-zero elsewhere.
            char = 0x0009 | (self.tttt << 5)
            removable = [0x00, 0x00]
            return bytes([7 + len(removable), 0x29, self.nports]
                         + le16(char) + [self.pgood, 100] + removable)
        return None

    def class_control(self, ctl, rt, req, val, idx, length, buf):
        if rt == 0xA0 and req == 6:                  # GetHubDescriptor
            if not self.configured:
                ctl.bad("hub: a class request before SET_CONFIGURATION")
                return 6, b""
            d = self.descriptor((val >> 8) & 0xFF, val & 0xFF)
            if d is None:
                return 6, b""
            return 1, d[:length]
        if rt == 0xA3 and req == 0x00:               # GetPortStatus
            if not self.configured:
                ctl.bad("hub: GetPortStatus before SET_CONFIGURATION")
                return 6, b""
            if idx < 1 or idx > self.nports:
                ctl.bad(f"hub: GetPortStatus for port {idx}, which does "
                        f"not exist")
                return 6, b""
            st = 0
            if self.powered[idx]:
                st |= PS_POWER
                child = self.children.get(idx)
                if child is not None:
                    st |= PS_CONNECTION
                    if self.reset_done[idx]:
                        st |= PS_ENABLE
                        if child.speed == SPEED_LS:
                            st |= PS_LOW_SPEED
                        elif child.speed == SPEED_HS:
                            st |= PS_HIGH_SPEED
            return 1, bytes(le16(st) + le16(self.change[idx]))
        if rt == 0x23 and req in (0x01, 0x03):       # Clear/SetPortFeature
            if not self.configured:
                ctl.bad("hub: a port feature request before "
                        "SET_CONFIGURATION")
                return 6, b""
            if idx < 1 or idx > self.nports:
                ctl.bad(f"hub: port feature on port {idx}, which does "
                        f"not exist")
                return 6, b""
            setting = (req == 0x03)
            if val == PF_POWER and setting:
                self.powered[idx] = True
                if self.children.get(idx) is not None:
                    self.change[idx] |= PC_CONNECTION
                self.log.append(f"power{idx}")
                return 1, b""
            if val == PF_RESET and setting:
                if not self.powered[idx]:
                    ctl.bad(f"hub: port {idx} was reset before it was "
                            f"powered")
                    return 6, b""
                if self.children.get(idx) is None:
                    ctl.bad(f"hub: port {idx} was reset with nothing on it")
                    return 6, b""
                self.reset_done[idx] = True
                self.change[idx] |= PC_RESET
                self.log.append(f"reset{idx}")
                return 1, b""
            if val == PF_C_RESET and not setting:
                self.change[idx] &= ~PC_RESET
                self.log.append(f"clear-c-reset{idx}")
                return 1, b""
            if val == PF_C_CONNECTION and not setting:
                self.change[idx] &= ~PC_CONNECTION
                return 1, b""
            # An unknown feature is STALLED rather than ignored.  A hub
            # that silently accepts everything lets a driver send a
            # feature number it invented.
            ctl.bad(f"hub: unmodelled port feature {val} "
                    f"({'set' if setting else 'clear'})")
            return 6, b""
        return 6, b""


# =====================================================================
#  THE CONTROLLER
# =====================================================================
class Ctl:
    def __init__(self, cpu: A64, topology: dict) -> None:
        self.cpu = cpu
        self.violations: list[str] = []
        self.log: list[str] = []

        self.cfg: dict[int, int] = {}
        self.cfg[0x00] = 0x34831106
        self.cfg[0x04] = 0x00100000
        self.cfg[0x10] = 0xF8000004
        self.cfg[0x14] = 0x00000000

        self.reg: dict[int, int] = {
            R_USBCMD: 0,
            R_USBSTS: STS_HALT,
            R_PAGESIZE: 0x00000001,
            R_DNCTRL: 0xFFFF,
            R_CONFIG: 0,
            R_ERSTSZ: 0xABCD0000,
            R_IMAN: 0,
            R_IMOD: 0,
        }
        self.wide = {R_CRCR: 0, R_DCBAAP: 0, R_ERSTBA: 0, R_ERDP: 0}

        self.hcrst_reads = 0
        self.cnr_reads = 0
        self.halt_reads = 0

        # topology[root_port] is the device on that root port.
        self.topology = topology
        self.port = {}
        for n in range(1, MAX_PORTS + 1):
            self.port[n] = 0
        # THE HUB IS ALREADY CONNECTED AND POWERED at reset, because on
        # the real board it is soldered on and the firmware has powered
        # it.  Everything else needs its port powering first.
        for n, dev in topology.items():
            self.port[n] = P_POWER

        self.cmd_base = 0
        self.cmd_deq = 0
        self.cmd_ccs = 1
        self.ev_base = 0
        self.ev_size = 0
        self.ev_enq = 0
        self.ev_pcs = 1

        self.next_slot = 1
        # slot -> {"dev":, "ring":, "deq":, "ccs":, "route":, "port":,
        #          "speed":, "tt_slot":, "tt_port":, "hub":, "nports":,
        #          "ttt":, "mtt":}
        self.slots: dict[int, dict] = {}
        self.ticks = 0
        self.addr_ctx: list[dict] = []
        self.config_ep: list[dict] = []

    # -- raw memory ------------------------------------------------------
    def rd(self, addr: int, size: int) -> int:
        m = self.cpu.memory
        return sum(m.get(addr + i, 0) << (8 * i) for i in range(size))

    def wr(self, addr: int, value: int, size: int) -> None:
        m = self.cpu.memory
        for i in range(size):
            m[addr + i] = (value >> (8 * i)) & 0xFF

    def bad(self, msg: str) -> None:
        if msg not in self.violations:
            self.violations.append(msg)

    def cnr_set(self) -> bool:
        return bool(self.reg[R_USBSTS] & STS_CNR)

    # -- configuration space ---------------------------------------------
    def cfg_read(self, off: int, bdf) -> int:
        if bdf != (1, 0, 0):
            return 0xFFFFFFFF
        return self.cfg.get(off, 0)

    # -- registers --------------------------------------------------------
    def reg_read(self, off: int) -> int:
        if off == 0x00:
            return CAPBASE_VAL
        if off == 0x04:
            return HCS1
        if off == 0x08:
            return HCS2
        if off == 0x0C:
            return HCS3
        if off == 0x10:
            return HCC1
        if off == 0x14:
            return DBOFF
        if off == 0x18:
            return RTSOFF

        if off == R_USBCMD:
            v = self.reg[R_USBCMD]
            if v & CMD_RESET:
                self.hcrst_reads += 1
                if self.hcrst_reads >= 3:
                    self.reg[R_USBCMD] = v & ~CMD_RESET
                    self.reg[R_USBSTS] |= STS_CNR
                    self.cnr_reads = 0
                    self.log.append("hcrst-cleared")
            return self.reg[R_USBCMD]

        if off == R_USBSTS:
            v = self.reg[R_USBSTS]
            if v & STS_CNR:
                self.cnr_reads += 1
                if self.cnr_reads >= 4:
                    self.reg[R_USBSTS] = v & ~STS_CNR
                    self.log.append("cnr-cleared")
            elif self.halt_reads > 0:
                self.halt_reads -= 1
                if self.halt_reads == 0:
                    if self.reg[R_USBCMD] & CMD_RUN:
                        self.reg[R_USBSTS] &= ~STS_HALT
                        self.log.append("running")
                    else:
                        self.reg[R_USBSTS] |= STS_HALT
            return self.reg[R_USBSTS]

        for base in self.wide:
            if off == base:
                return self.wide[base] & 0xFFFFFFFF
            if off == base + 4:
                return (self.wide[base] >> 32) & 0xFFFFFFFF

        if R_PORTS <= off < R_PORTS + MAX_PORTS * 0x10:
            n = (off - R_PORTS) // 0x10 + 1
            if (off - R_PORTS) % 0x10 == 0:
                return self.port.get(n, 0)
            return 0

        return self.reg.get(off, 0)

    def reg_write(self, off: int, value: int) -> None:
        value &= 0xFFFFFFFF
        if self.cnr_set():
            if off >= OP and off != R_USBSTS:
                self.bad(f"operational register ${off:03X} written while "
                         f"Controller Not Ready was still set")
            if DBOFF <= off < DBOFF + 0x400:
                self.bad("doorbell rung while Controller Not Ready was set")
        if off < OP:
            self.bad(f"write to read-only capability register ${off:02X}")
            return

        if off == R_USBCMD:
            old = self.reg[R_USBCMD]
            self.reg[R_USBCMD] = value
            if value & CMD_RESET:
                self.hcrst_reads = 0
                self.log.append("hcrst")
                for k in self.wide:
                    self.wide[k] = 0
                self.reg[R_CONFIG] = 0
                self.cmd_base = 0
                self.ev_base = 0
            elif (value & CMD_RUN) and not (old & CMD_RUN):
                self.halt_reads = 2
                self.log.append("run-requested")
            elif (old & CMD_RUN) and not (value & CMD_RUN):
                self.halt_reads = 2
            return

        if off == R_USBSTS:
            self.reg[R_USBSTS] &= ~(value & 0x1F1C)
            return

        for base in self.wide:
            if off == base:
                self.wide[base] = (self.wide[base] & ~0xFFFFFFFF) | value
                return
            if off == base + 4:
                self.wide[base] = (self.wide[base] & 0xFFFFFFFF) | (value << 32)
                self._wide_written(base)
                return

        if R_PORTS <= off < R_PORTS + MAX_PORTS * 0x10:
            if (off - R_PORTS) % 0x10 == 0:
                self._port_write((off - R_PORTS) // 0x10 + 1, value)
            return

        self.reg[off] = value

    def _wide_written(self, base: int) -> None:
        v = self.wide[base]
        if base == R_DCBAAP:
            if v & 63:
                self.bad(f"DCBAAP is not 64-byte aligned (${v:X})")
            self.log.append("dcbaap")
        elif base == R_CRCR:
            ptr = v & ~0x3F
            if ptr and (ptr & 63):
                self.bad("the command ring pointer is not 64-byte aligned")
            self.cmd_base = ptr
            self.cmd_deq = 0
            self.cmd_ccs = v & 1
            self.log.append("crcr")
        elif base == R_ERSTBA:
            ptr = v & ~0xF
            if ptr & 63:
                self.bad("the ERST base is not 64-byte aligned")
            seg = self.rd(ptr, 8)
            size = self.rd(ptr + 8, 4)
            if seg & 63:
                self.bad("the event ring segment is not 64-byte aligned")
            self.ev_base = seg
            self.ev_size = size
            self.ev_enq = 0
            self.ev_pcs = 1
            self.log.append("erstba")

    def _port_write(self, n: int, value: int) -> None:
        cur = self.port.get(n, 0)
        cur &= ~(value & 0x00FE0000)
        if (value & P_POWER) and not (cur & P_POWER):
            cur |= P_POWER
            self.log.append(f"rootport{n}-powered")
        if not (value & P_POWER) and (cur & P_POWER):
            self.bad(f"root port {n} was powered down by a "
                     f"read-modify-write")
        if value & P_PE:
            self.bad(f"root port {n} was disabled by a write to Port "
                     f"Enabled")
        if value & P_RESET:
            dev = self.topology.get(n)
            if dev is None:
                self.bad(f"root port {n} was reset with nothing connected")
            else:
                cur |= P_PE | P_RC | P_PEC | (dev.speed << 10)
                self.log.append(f"rootport{n}-reset")
            cur &= ~P_RESET
        self.port[n] = cur

    def port_status(self, n: int) -> int:
        cur = self.port.get(n, 0)
        dev = self.topology.get(n)
        if dev is not None and (cur & P_POWER):
            cur |= P_CONNECT
        return cur

    # -- event ring --------------------------------------------------------
    def post_event(self, f0, f1, f2, f3) -> None:
        if not self.ev_base:
            self.bad("an event was produced before the event ring existed")
            return
        at = self.ev_base + self.ev_enq * 16
        self.wr(at, f0, 4)
        self.wr(at + 4, f1, 4)
        self.wr(at + 8, f2, 4)
        self.wr(at + 12, (f3 & ~1) | self.ev_pcs, 4)
        self.ev_enq += 1
        if self.ev_enq >= self.ev_size:
            self.ev_enq = 0
            self.ev_pcs ^= 1

    def doorbell(self, index: int, value: int) -> None:
        if not (self.cfg[0x04] & 0x04):
            self.bad("a doorbell was rung with PCI bus mastering disabled")
        if index == 0:
            if value != 0:
                self.bad(f"the command doorbell was rung with {value}, not 0")
            self.run_command_ring()
        else:
            if value != 1:
                self.bad(f"endpoint 0's doorbell was rung with {value}, "
                         f"not 1 - this driver has no other endpoints")
            self.run_ep0(index)

    # -- commands -----------------------------------------------------------
    def run_command_ring(self) -> None:
        if not self.cmd_base:
            self.bad("the command doorbell was rung before CRCR was set")
            return
        for _ in range(256):
            at = self.cmd_base + self.cmd_deq * 16
            ctl = self.rd(at + 12, 4)
            if (ctl & 1) != self.cmd_ccs:
                return
            ty = (ctl >> 10) & 0x3F
            if ty == 6:
                if self.rd(at, 8) != self.cmd_base:
                    self.bad("the command ring's Link TRB does not point "
                             "at its own segment")
                if not (ctl & 2):
                    self.bad("the command ring's Link TRB has no Toggle "
                             "Cycle bit")
                self.cmd_deq = 0
                self.cmd_ccs ^= 1
                continue
            param = self.rd(at, 8)
            self.handle_command(at, ty, param, (ctl >> 24) & 0xFF,
                                (ctl >> 16) & 0x1F)
            self.cmd_deq += 1
            if self.cmd_deq >= 64:
                self.bad("the command ring ran past its segment")
                return
        self.bad("the command ring did not terminate")

    def handle_command(self, at, ty, param, slot, ep: int = 0) -> None:
        comp = 1
        out_slot = 0
        if ty == 23:
            pass
        elif ty == 9:                                # Enable Slot
            out_slot = self.next_slot
            self.next_slot += 1
            self.log.append(f"enable-slot={out_slot}")
        elif ty == 11:                               # Address Device
            out_slot = slot
            comp = self.address_device(slot, param)
        elif ty == 12:                               # Configure Endpoint
            out_slot = slot
            comp = self.configure_endpoint(slot, param)
        elif ty == 13:                               # Evaluate Context
            out_slot = slot
            comp = self.evaluate_context(slot, param)
        elif ty == 14:                               # Reset Endpoint
            out_slot = slot
            comp = self.reset_endpoint(slot, ep)
        elif ty == 16:                               # Set TR Dequeue Pointer
            out_slot = slot
            comp = self.set_tr_dequeue(slot, ep, param)
        else:
            self.bad(f"unexpected command TRB type {ty}")
            comp = 5
        self.post_event(at & 0xFFFFFFFF, (at >> 32) & 0xFFFFFFFF,
                        comp << 24, (33 << 10) | (out_slot << 24))

    def set_ep0_state(self, rec: dict, state: int) -> None:
        """Write endpoint 0's state into the OUTPUT device context.

        The low three bits of word 0 of the endpoint context at DCI 1 -
        xhci.h's EP_STATE_MASK.  The driver reads this back to decide
        whether its recovery worked, so a model that tracked the halt
        only in Python would let a driver that reads the wrong offset
        pass.
        """
        rec["ep0state"] = state
        at = rec["out"] + CTX_SIZE
        self.wr(at, (self.rd(at, 4) & ~7) | state, 4)

    def reset_endpoint(self, slot: int, ep: int) -> int:
        """Reset Endpoint, TRB type 14.

        rpi-6.12.y_xhci.h:823 - EP_INDEX_FOR_TRB(p) is
        (((p) + 1) & 0x1f) << 16 with p the ep_index, so endpoint 0
        arrives as 1.  xHCI 1.1 section 4.6.8: the command is only valid
        on an endpoint in the Halted state and moves it to Stopped.
        """
        rec = self.slots.get(slot)
        if rec is None:
            self.bad(f"Reset Endpoint for slot {slot}, never addressed")
            return 11
        if ep != 1:
            self.bad(f"Reset Endpoint named endpoint index {ep}, not 1 - "
                     f"endpoint 0 is DCI 1 and the TRB carries the DCI")
            return 17
        if not rec.get("halted"):
            self.bad(f"Reset Endpoint on slot {slot}'s endpoint 0, which is "
                     f"not halted - xHCI 1.1 section 4.6.8 answers Context "
                     f"State Error")
            return 19
        rec["halted"] = False
        rec["reset"] = True
        self.set_ep0_state(rec, 3)                   # Stopped
        self.log.append(f"reset-ep slot={slot}")
        return 1

    def set_tr_dequeue(self, slot: int, ep: int, param: int) -> int:
        """Set TR Dequeue Pointer, TRB type 16.

        rpi-6.12.y_xhci_ring.c:758-763 - the low half of the parameter
        carries the new cycle bit in bit 0.

        THE POINTER MUST NOT LAND ON A TRB THE PRODUCER STILL OWNS.
        Aiming it at the base of the ring looks like "start again from
        the top" and is a replay of the transfer that just stalled,
        because every TRB below the enqueue point still carries the
        producer's cycle.
        """
        rec = self.slots.get(slot)
        if rec is None:
            self.bad(f"Set TR Dequeue for slot {slot}, never addressed")
            return 11
        if ep != 1:
            self.bad(f"Set TR Dequeue named endpoint index {ep}, not 1")
            return 17
        if not rec.get("reset"):
            self.bad(f"Set TR Dequeue Pointer on slot {slot} before Reset "
                     f"Endpoint - the endpoint is still Halted")
            return 19
        addr = param & ~0xF
        cyc = param & 1
        if addr < rec["ring"] or addr >= rec["ring"] + 64 * 16:
            self.bad(f"Set TR Dequeue points at ${addr:X}, outside slot "
                     f"{slot}'s EP0 ring")
            return 17
        if (self.rd(addr + 12, 4) & 1) == cyc:
            self.bad("Set TR Dequeue points at a TRB the controller would "
                     "own - the stalled transfer descriptor would run again")
        rec["deq"] = (addr - rec["ring"]) // 16
        rec["ccs"] = cyc
        rec["reset"] = False
        self.set_ep0_state(rec, 1)                   # Running
        self.log.append(f"set-deq slot={slot}")
        return 1

    def resolve(self, root: int, route: int) -> Dev | None:
        """Which device does (root hub port, route string) name?

        Route 0 is the device on the root port.  A non-zero low nibble
        is that downstream port of the hub on the root port - one tier,
        which is what the driver builds and all it claims to build.
        """
        top = self.topology.get(root)
        if route == 0:
            return top
        if not isinstance(top, Hub):
            self.bad(f"a route string names port {route & 0xF} of the "
                     f"device on root port {root}, which is not a hub")
            return None
        if route >> 4:
            self.bad("a route string names a second tier - this driver "
                     "does not build one")
            return None
        return top.children.get(route & 0xF)

    def evaluate_context(self, slot: int, in_ctx: int) -> int:
        """Evaluate Context, used to correct endpoint 0's Max Packet Size
        once the device descriptor has been read.

        THE MODEL ENFORCES THE THINGS THAT MAKE THIS COMMAND DIFFERENT
        FROM ADDRESS DEVICE, because getting any of them wrong produces a
        driver that works on a forgiving controller and not on this one:

          * add_flags must be EP0_FLAG ALONE. Setting SLOT_FLAG as well
            asks the controller to evaluate slot fields the driver did
            not fill in.
          * drop_flags must be zero - this command drops nothing.
          * ep_info's EP_STATE must be cleared. rpi-6.12.y_xhci.c:1497
            marks it "must clear"; the output context's copy carries a
            running state that is not legal on input.
          * the slot must already be addressed. Evaluating a context on
            a slot that was never addressed is a driver bug, and the
            real controller answers with an error rather than obliging.

        The Max Packet Size is then applied to the modelled device, so a
        LATER control transfer is judged against the corrected size. That
        is the whole point of the command: without applying it here the
        gate would accept the command and still model the old size, and
        a driver that issued the command but computed the wrong value
        would pass.
        """
        if in_ctx & 63:
            self.bad(f"the input context is not 64-byte aligned (${in_ctx:X})")
        drop = self.rd(in_ctx, 4)
        add = self.rd(in_ctx + 4, 4)
        if drop != 0:
            self.bad("Evaluate Context: drop_flags is not zero")
        if add != 2:
            self.bad(f"Evaluate Context: add_flags is {add}, not EP0_FLAG "
                     f"alone (2). SLOT_FLAG must not be set.")
        ectx = in_ctx + CTX_SIZE * 2
        ep0 = self.rd(ectx, 4)
        if ep0 & 7:
            self.bad(f"Evaluate Context: ep_info's EP_STATE is {ep0 & 7}, "
                     f"not cleared")
        ep2 = self.rd(ectx + 4, 4)
        mps = (ep2 >> 16) & 0xFFFF
        if mps not in (8, 16, 32, 64, 512):
            self.bad(f"Evaluate Context: max packet {mps} is not a legal "
                     f"endpoint-0 size")
        dev = self.slots.get(slot)
        if dev is None:
            self.bad(f"Evaluate Context on slot {slot}, which was never "
                     f"addressed")
            return 17
        dev["mps"] = mps
        self.log.append(f"eval-ctx slot={slot} mps={mps}")
        return 1

    def address_device(self, slot: int, in_ctx: int) -> int:
        if in_ctx & 63:
            self.bad(f"the input context is not 64-byte aligned (${in_ctx:X})")
        drop = self.rd(in_ctx, 4)
        add = self.rd(in_ctx + 4, 4)
        if drop != 0:
            self.bad("Address Device: drop_flags is not zero")
        if add != 3:
            self.bad(f"Address Device: add_flags is {add}, not "
                     f"SLOT_FLAG|EP0_FLAG (3)")
        sctx = in_ctx + CTX_SIZE
        ectx = in_ctx + CTX_SIZE * 2
        info = self.rd(sctx, 4)
        info2 = self.rd(sctx + 4, 4)
        tt = self.rd(sctx + 8, 4)
        ep2 = self.rd(ectx + 4, 4)
        deq = self.rd(ectx + 8, 8)

        seen = {
            "slot": slot,
            "route": info & 0xFFFFF,
            "speed": (info >> 20) & 0xF,
            "mtt": bool(info & DEV_MTT),
            "hub": bool(info & DEV_HUB),
            "last_ctx": (info >> 27) & 0x1F,
            "port": (info2 >> 16) & 0xFF,
            "nports": (info2 >> 24) & 0xFF,
            "tt_slot": tt & 0xFF,
            "tt_port": (tt >> 8) & 0xFF,
            "ttt": (tt >> 16) & 3,
            "maxpacket": (ep2 >> 16) & 0xFFFF,
            "deq": deq & ~1,
            "deq_cycle": deq & 1,
        }
        self.addr_ctx.append(seen)

        if seen["last_ctx"] != 1:
            self.bad("Address Device: LAST_CTX is not 1")
        if ((ep2 >> 3) & 7) != 4:
            self.bad("Address Device: endpoint 0 is not a control endpoint")
        if seen["deq"] & 63:
            self.bad("Address Device: the EP0 ring pointer is not aligned")

        dev = self.resolve(seen["port"], seen["route"])
        if dev is None:
            self.bad(f"Address Device names root port {seen['port']} "
                     f"route ${seen['route']:X}, where there is no device")
            return 17
        if dev.speed != seen["speed"]:
            self.bad(f"{dev.name}: the slot context says speed "
                     f"{seen['speed']}, the port trained at {dev.speed}")

        # ---- THE TRANSACTION TRANSLATOR.  This is the check the whole
        # hub effort exists for, and a real controller enforces it by
        # simply never scheduling the split transaction - silently.
        if seen["route"] != 0 and dev.speed in (SPEED_LS, SPEED_FS):
            hubslot = None
            for s, rec in self.slots.items():
                if rec["dev"] is self.topology.get(seen["port"]):
                    hubslot = s
            if seen["tt_slot"] == 0 or seen["tt_port"] == 0:
                self.bad(f"{dev.name} is {'low' if dev.speed == SPEED_LS else 'full'}"
                         f"-speed behind a hub and its slot context names "
                         f"no transaction translator - every transfer to "
                         f"it would be scheduled as if it were high speed")
            elif hubslot is not None and seen["tt_slot"] != hubslot:
                self.bad(f"{dev.name}: TT Hub Slot ID is {seen['tt_slot']}, "
                         f"but the hub is slot {hubslot}")
            if seen["tt_port"] != (seen["route"] & 0xF):
                self.bad(f"{dev.name}: TT Port Number is {seen['tt_port']} "
                         f"but the route string says hub port "
                         f"{seen['route'] & 0xF}")
            # The hub must ALREADY be marked as a hub.
            if hubslot is not None and not self.slots[hubslot].get("hub"):
                self.bad(f"{dev.name} was addressed behind a hub whose slot "
                         f"context has never had DEV_HUB set - the "
                         f"controller would not schedule split "
                         f"transactions for it")
        if seen["route"] == 0 and (seen["tt_slot"] or seen["tt_port"]):
            self.bad("a device on a root port names a transaction "
                     "translator")

        # A hub port must have been RESET before its device is addressed.
        top = self.topology.get(seen["port"])
        if seen["route"] and isinstance(top, Hub):
            p = seen["route"] & 0xF
            if not top.reset_done.get(p):
                self.bad(f"hub port {p} was never reset before the device "
                         f"on it was addressed")

        dcbaap = self.wide[R_DCBAAP] & ~63
        if not dcbaap:
            self.bad("Address Device with no DCBAA")
            return 17
        out_ctx = self.rd(dcbaap + slot * 8, 8)
        if not out_ctx:
            self.bad(f"DCBAA slot {slot} is empty at Address Device time")
            return 17
        if out_ctx & 63:
            self.bad("the output device context is not 64-byte aligned")

        # TWO SLOTS SHARING ONE RING is the 2026-08-26 defect.  Refuse it
        # here rather than reproducing it: it is silent on real silicon
        # and cost a day.
        for s, rec in self.slots.items():
            if s != slot and rec["ring"] == seen["deq"]:
                self.bad(f"slot {slot} was given the same endpoint-0 ring "
                         f"as slot {s}")

        self.wr(out_ctx + 0, info, 4)
        self.wr(out_ctx + 4, info2, 4)
        self.wr(out_ctx + 8, tt, 4)
        self.wr(out_ctx + 12, (2 << 27) | slot, 4)
        self.slots[slot] = {
            "dev": dev, "ring": seen["deq"], "deq": 0,
            "ccs": seen["deq_cycle"], "out": out_ctx,
            "route": seen["route"], "port": seen["port"],
            "speed": seen["speed"], "hub": seen["hub"],
            "mps": seen["maxpacket"],
            "halted": False, "reset": False, "ep0state": 1,
        }
        self.log.append(f"address slot={slot} {dev.name} "
                        f"root={seen['port']} route={seen['route']}")
        return 1

    def configure_endpoint(self, slot: int, in_ctx: int) -> int:
        if slot not in self.slots:
            self.bad(f"Configure Endpoint for slot {slot}, never addressed")
            return 17
        add = self.rd(in_ctx + 4, 4)
        drop = self.rd(in_ctx, 4)
        sctx = in_ctx + CTX_SIZE
        info = self.rd(sctx, 4)
        info2 = self.rd(sctx + 4, 4)
        tt = self.rd(sctx + 8, 4)
        rec = {
            "slot": slot, "add": add, "drop": drop,
            "hub": bool(info & DEV_HUB), "mtt": bool(info & DEV_MTT),
            "nports": (info2 >> 24) & 0xFF, "ttt": (tt >> 16) & 3,
            "route": info & 0xFFFFF, "port": (info2 >> 16) & 0xFF,
            "last_ctx": (info >> 27) & 0x1F,
        }
        self.config_ep.append(rec)
        if drop != 0:
            self.bad("Configure Endpoint: drop_flags is not zero")
        if not (add & 1):
            self.bad("Configure Endpoint: the slot context flag is not set, "
                     "so the slot context is not updated at all")
        # The slot context must have been COPIED, not rebuilt: the root
        # port number and the route string were established by Address
        # Device and losing them is how a hub stops being reachable.
        prev = self.slots[slot]
        if rec["port"] != prev["port"]:
            self.bad(f"Configure Endpoint on slot {slot} changed the root "
                     f"hub port from {prev['port']} to {rec['port']} - the "
                     f"slot context was rebuilt instead of copied")
        if rec["route"] != prev["route"]:
            self.bad(f"Configure Endpoint on slot {slot} changed the route "
                     f"string - the slot context was rebuilt")
        if rec["last_ctx"] < 1:
            self.bad("Configure Endpoint left Context Entries below 1")

        dev = prev["dev"]
        if rec["hub"]:
            if not isinstance(dev, Hub):
                self.bad(f"{dev.name} was marked as a hub and is not one")
            else:
                if rec["nports"] != dev.nports:
                    self.bad(f"hub slot context says {rec['nports']} ports, "
                             f"the hub descriptor said {dev.nports}")
                if rec["ttt"] != dev.tttt:
                    self.bad(f"hub slot context TT think time is "
                             f"{rec['ttt']}, the hub descriptor said "
                             f"{dev.tttt}")
                if rec["mtt"]:
                    self.bad("the hub was marked multi-TT without a "
                             "SET_INTERFACE selecting its multi-TT "
                             "alternate setting")
        prev["hub"] = rec["hub"]
        self.log.append(f"config-ep slot={slot} hub={rec['hub']}")
        return 1

    # -- endpoint zero -------------------------------------------------------
    def run_ep0(self, slot: int) -> None:
        rec = self.slots.get(slot)
        if rec is None:
            self.bad(f"endpoint 0 doorbell for slot {slot}, never addressed")
            return
        # A HALTED ENDPOINT RUNS NOTHING.  xHCI 1.1 section 4.8.3: a
        # Stall moves the endpoint to Halted, and the controller then
        # takes the doorbell and never walks the ring - no event, ever,
        # so the driver spends its whole transfer timeout on a transfer
        # that was never attempted.  ENDPOINT ZERO BELONGS TO THE
        # DEVICE, not to an interface, so this kills every interface of
        # a composite device at once.  Measured on silicon 2026-08-28:
        # the receiver's mouse interface stalled SET_IDLE - legal, HID
        # 1.11 Appendix G - and the keyboard interface, which had
        # answered GET_REPORT in 2 ms one transfer earlier, then timed
        # out at five seconds.
        if rec.get("halted"):
            self.bad(f"slot {slot}'s endpoint 0 doorbell was rung while the "
                     f"endpoint was HALTED - a Reset Endpoint and a Set TR "
                     f"Dequeue Pointer were owed after the stall, and "
                     f"without them every later transfer on this device "
                     f"times out")
            return
        setup = None
        data = None
        last = None
        # The bound is 256, not a handful: xh_RingRoom pads the tail of a
        # segment with up to 62 Transfer Ring No-Op TRBs so that the
        # consumer can WALK to the Link TRB, and a consumer that gave up
        # after sixteen would stop in the middle of the padding and
        # report a deadlock that is not there.
        for _ in range(256):
            at = rec["ring"] + rec["deq"] * 16
            ctl = self.rd(at + 12, 4)
            if (ctl & 1) != rec["ccs"]:
                break
            ty = (ctl >> 10) & 0x3F
            f0 = self.rd(at, 4)
            f1 = self.rd(at + 4, 4)
            f2 = self.rd(at + 8, 4)
            if ty == 6:
                if not (ctl & 2):
                    self.bad("an EP0 Link TRB has no Toggle Cycle bit")
                rec["deq"] = 0
                rec["ccs"] ^= 1
                continue
            if ty == 8:
                # Transfer Ring No-Op, xhci.h:918.  Consumed and stepped
                # over.  It must NOT carry IOC - one that did would post
                # an event the driver is not waiting for, and the next
                # real transfer would match against it.
                if ctl & 0x20:
                    self.bad("a Transfer Ring No-Op TRB carries TRB_IOC - "
                             "it would post an event nobody is waiting for")
                rec["deq"] += 1
                if rec["deq"] > 64:
                    self.bad("the EP0 ring ran past its segment")
                    return
                continue
            if ty == 2:
                if not (ctl & 0x40):
                    self.bad("the Setup Stage TRB does not set TRB_IDT")
                if (f2 & 0x1FFFF) != 8:
                    self.bad("the Setup Stage TRB length is not 8")
                setup = {
                    "rt": f0 & 0xFF, "req": (f0 >> 8) & 0xFF,
                    "val": (f0 >> 16) & 0xFFFF, "idx": f1 & 0xFFFF,
                    "len": (f1 >> 16) & 0xFFFF,
                }
            elif ty == 3:
                data = {"buf": f0 | (f1 << 32), "len": f2 & 0x1FFFF,
                        "dir_in": bool(ctl & (1 << 16))}
            elif ty == 4:
                last = at
                if not (ctl & 0x20):
                    self.bad("the Status Stage TRB does not set TRB_IOC")
            else:
                self.bad(f"unexpected TRB type {ty} on the EP0 ring")
            rec["deq"] += 1
            if last is not None:
                break
        if setup is None or last is None:
            self.bad("an EP0 doorbell produced no complete control transfer")
            return

        want = setup["len"]
        dev = rec["dev"]
        dir_in = bool(setup["rt"] & 0x80)
        if want and data is None:
            self.bad("a control transfer with wLength but no Data Stage TRB")
        if data is not None:
            if data["dir_in"] != dir_in:
                self.bad("the Data Stage TRB's direction bit disagrees with "
                         "bmRequestType")
            if data["len"] != want:
                self.bad("the Data Stage TRB length does not match wLength")

        comp, payload = dev.control(self, setup["rt"], setup["req"],
                                    setup["val"], setup["idx"], want,
                                    data["buf"] if data else 0)
        moved = 0
        if comp == 1 and dir_in and data is not None:
            body = payload[:want]
            for i, b in enumerate(body):
                self.cpu.memory[data["buf"] + i] = b
            moved = len(body)
            if moved < want:
                comp = 13
        elif comp == 1 and not dir_in:
            moved = want
        resid = want - moved
        if comp == 6:
            rec["halted"] = True
            self.set_ep0_state(rec, 2)               # Halted
            self.log.append(f"stall slot={slot} req={setup['req']:02X} "
                            f"iface={setup['idx']}")
        self.post_event(last & 0xFFFFFFFF, (last >> 32) & 0xFFFFFFFF,
                        (comp << 24) | (resid & 0xFFFFFF),
                        (32 << 10) | (1 << 16) | (slot << 24))


def install(cpu: A64, ctl: Ctl) -> None:
    raw_load = A64.load.__get__(cpu, A64)
    raw_store = A64.store.__get__(cpu, A64)
    orig_step = A64.step.__get__(cpu, A64)

    def load(addr: int, size: int) -> int:
        # THE ALIGNMENT RULE, FIRST LINE, ALWAYS.  a64_interp.py's
        # align_guard() is what closes the hole that once let an emulator
        # gate certify a payload that wedged the board dead; a gate that
        # installs closures and forgets this call is back to modelling a
        # machine more permissive than the part.  The
        # `misaligned-report-read` mutation below proves it fires.
        cpu.align_guard(addr, size, False)
        if CAP_BASE <= addr < CAP_BASE + CAP_SIZE:
            if size != 4:
                ctl.bad(f"a {size}-byte load from an xHCI register - every "
                        f"register access must be 32 bits")
                return 0
            off = addr - CAP_BASE
            if R_PORTS <= off < R_PORTS + MAX_PORTS * 0x10:
                if (off - R_PORTS) % 0x10 == 0:
                    return ctl.port_status((off - R_PORTS) // 0x10 + 1)
            return ctl.reg_read(off)
        if CFG_BASE <= addr < CFG_BASE + CFG_SIZE:
            off = addr - CFG_BASE
            bdf = ((off >> 20) & 0xFF, (off >> 15) & 0x1F, (off >> 12) & 7)
            return ctl.cfg_read(off & 0xFFF, bdf)
        return raw_load(addr, size)

    def store(addr: int, value: int, size: int) -> None:
        cpu.align_guard(addr, size, True)
        if CAP_BASE <= addr < CAP_BASE + CAP_SIZE:
            if size != 4:
                ctl.bad(f"a {size}-byte store to an xHCI register - every "
                        f"register access must be 32 bits")
                return
            off = addr - CAP_BASE
            if DBOFF <= off < DBOFF + 0x400:
                ctl.doorbell((off - DBOFF) // 4, value & 0xFFFFFFFF)
                return
            ctl.reg_write(off, value)
            return
        if CFG_BASE <= addr < CFG_BASE + CFG_SIZE:
            off = addr - CFG_BASE
            bdf = ((off >> 20) & 0xFF, (off >> 15) & 0x1F, (off >> 12) & 7)
            if bdf == (1, 0, 0):
                ctl.cfg[off & 0xFFF] = value & 0xFFFFFFFF
            return
        raw_store(addr, value, size)

    def step() -> None:
        ins = cpu.fetch(cpu.pc)
        if (ins & 0xFFFFFFE0) == 0xD53BE000:      # mrs Xt, cntfrq_el0
            cpu.put(ins & 31, CNTFRQ, 1)
            cpu.pc += 4
            return
        if (ins & 0xFFFFFFE0) == 0xD53BE020:      # mrs Xt, cntpct_el0
            ctl.ticks += TICK_STEP
            cpu.put(ins & 31, ctl.ticks, 1)
            cpu.pc += 4
            return
        orig_step()

    cpu.load = load
    cpu.store = store
    cpu.step = step


# =====================================================================
#  THE SCRIPTED REPORTS, AND WHAT EACH ONE IS FOR
# =====================================================================
#  These are consumed one per GET_REPORT.  pi4HidSelfTest.pi4 polls
#  #KBD_POLLS times and the two numbers must agree - see KBD_POLLS.
# ---------------------------------------------------------------------
def kr(mods: int, *keys: int) -> bytes:
    a = list(keys) + [0] * (6 - len(keys))
    return bytes([mods, 0] + a)


KBD_SCRIPT = [
    # 0  nothing at all.  No events.
    kr(0),
    # 1  'a' down.  One event, character 97.
    kr(0, 0x04),
    # 2  Left Shift added, 'a' still down.  ZERO EVENTS - a modifier
    #    change is not a key event in this model, and a decoder that
    #    diffs the modifier byte into events reports a phantom keypress
    #    for every capital letter.
    kr(0x02, 0x04),
    # 3  'x' added while shifted.  One down event, character 88.
    kr(0x02, 0x04, 0x1B),
    # 4  THE PHANTOM STATE.  HID 1.11 Appendix C: ErrorRollOver in all
    #    six array fields.  Must be DISCARDED - a decoder that diffs it
    #    normally emits two key-up events for keys that are still held.
    kr(0x02, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01),
    # 5  back to report 3's state.  ZERO EVENTS, which is only true if
    #    the phantom did not become the baseline.
    kr(0x02, 0x04, 0x1B),
    # 6  everything released.  Two UP events.
    kr(0),
    # 7  Caps Lock down.  One event, no character, and the lock flips.
    kr(0, 0x39),
    # 8  Caps Lock up.  One event.  The lock must NOT flip again - it
    #    toggles on the down edge only, or holding the key for two polls
    #    would toggle it twice.
    kr(0),
    # 9  'a' with Caps Lock on -> 'A' (65).
    kr(0, 0x04),
    # 10 released.
    kr(0),
    # 11 Shift + 'a' with Caps Lock on -> 'a' (97).  THE XOR CASE.
    kr(0x02, 0x04),
    # 12 released.
    kr(0),
    # 13 'b' and 'c' down together.  Two down events.
    kr(0, 0x05, 0x06),
    # 14 THE SAME TWO KEYS, SWAPPED IN THE ARRAY.  ZERO EVENTS.  HID
    #    1.11 Appendix C: "The order of keycodes in array fields has no
    #    significance."  A decoder that watches a slot rather than
    #    diffing the set reports two ups and two downs here.
    kr(0, 0x06, 0x05),
    # 15 six keys at once, no phantom.  Four new down events (b and c
    #    were already held).
    kr(0, 0x06, 0x05, 0x07, 0x08, 0x09, 0x0A),
    # 16 all released.  Six up events.
    kr(0),
    # 17 quiet, so the last report the program reads is a known one.
    kr(0),
]
KBD_POLLS = 18
assert len(KBD_SCRIPT) == KBD_POLLS

# The composite device's keyboard interface is polled by nothing in the
# test program, but it needs a script so that a stray poll is not an
# index error.
KBD2_SCRIPT = [kr(0)]

# The mouse.  Four bytes: buttons, dx, dy, wheel.  Signed bytes are
# written as their unsigned encoding, the way they arrive on the wire.
# THE LAST REPORT CARRIES NO MOTION, DELIBERATELY.  The first version of
# this script had deltas that summed to exactly what the last report
# contained, so a driver that OVERWROTE the accumulators instead of
# adding to them produced the right answer and the
# `mouse-no-accumulate` mutation passed.  A mutation the gate cannot
# fail on is a hole, so the script was changed rather than the check:
# the sums below (+12, -3, +2) share no value with the final report.
MOUSE_SCRIPT = [
    bytes([0x00, 0, 0, 0]),          # nothing at all - poll returns 0
    bytes([0x01, 5, 3, 0]),          # button 1, +5 right, +3 down
    bytes([0x01, 7, 0xFA, 0]),       # +7 right, -6 up.  Buttons
                                     # unchanged, so only motion makes
                                     # this report interesting
    bytes([0x00, 0, 0, 1]),          # button released, wheel +1
    bytes([0x00, 0, 0, 1]),          # wheel +1 again - IDENTICAL to the
                                     # previous report, which must still
                                     # count as movement
    bytes([0x07, 0, 0, 0]),          # all three buttons, NO motion
]
MOUSE_POLLS = 6
assert len(MOUSE_SCRIPT) == MOUSE_POLLS

# What a HID device answers while it is STILL IN REPORT PROTOCOL.  Nine
# bytes with a leading Report ID, which is what a keyboard with media
# keys really sends and which decodes to garbage if read as a boot
# report.  A driver that skips SET_PROTOCOL reads this.
REPORT_PROTO_ANSWER = bytes([0x01, 0x00, 0x00, 0x3A, 0x3B, 0x3C, 0x3D,
                             0x3E, 0x3F])


# =====================================================================
#  AN INDEPENDENT DECODER
#
#  Written from HID 1.11 Appendix B.1 and Appendix C, using sets, which
#  is a different shape from the driver's slot-by-slot loops.  The point
#  is not that this is better - it is that a bug would have to be made
#  twice, in two different idioms, to pass.
#
#  It returns, per poll, (count, [(usage, down, char), ...]).
# =====================================================================
US_UNSHIFTED = {}
US_SHIFTED = {}


def _build_tables() -> None:
    # a..z
    for i in range(26):
        US_UNSHIFTED[0x04 + i] = ord("a") + i
        US_SHIFTED[0x04 + i] = ord("A") + i
    digits = "1234567890"
    shifted_digits = "!@#$%^&*()"
    for i in range(10):
        US_UNSHIFTED[0x1E + i] = ord(digits[i])
        US_SHIFTED[0x1E + i] = ord(shifted_digits[i])
    plain = {0x28: 13, 0x29: 27, 0x2A: 8, 0x2B: 9, 0x2C: 32}
    US_UNSHIFTED.update(plain)
    US_SHIFTED.update(plain)
    pairs = {
        0x2D: ("-", "_"), 0x2E: ("=", "+"), 0x2F: ("[", "{"),
        0x30: ("]", "}"), 0x31: ("\\", "|"), 0x32: ("#", "~"),
        0x33: (";", ":"), 0x34: ("'", '"'), 0x35: ("`", "~"),
        0x36: (",", "<"), 0x37: (".", ">"), 0x38: ("/", "?"),
        0x64: ("\\", "|"),
    }
    for u, (a, b) in pairs.items():
        US_UNSHIFTED[u] = ord(a)
        US_SHIFTED[u] = ord(b)
    US_UNSHIFTED[0x4C] = 127
    US_SHIFTED[0x4C] = 127
    keypad = {0x54: "/", 0x55: "*", 0x56: "-", 0x57: "+", 0x67: "="}
    for u, ch in keypad.items():
        US_UNSHIFTED[u] = ord(ch)
        US_SHIFTED[u] = ord(ch)
    US_UNSHIFTED[0x58] = 13
    US_SHIFTED[0x58] = 13
    for i in range(9):
        US_UNSHIFTED[0x59 + i] = ord("1") + i
        US_SHIFTED[0x59 + i] = ord("1") + i
    US_UNSHIFTED[0x62] = ord("0")
    US_SHIFTED[0x62] = ord("0")
    US_UNSHIFTED[0x63] = ord(".")
    US_SHIFTED[0x63] = ord(".")


_build_tables()

MOD_SHIFT = 0x22
KEYPAD_LOCKED = set(range(0x59, 0x64))


def ref_char(usage: int, mods: int, caps: int, num: int) -> int:
    if usage < 0 or usage > 0x67:
        return 0
    shifted = bool(mods & MOD_SHIFT)
    if 0x04 <= usage <= 0x1D and caps:
        shifted = not shifted
    if usage in KEYPAD_LOCKED and not num:
        return 0
    table = US_SHIFTED if shifted else US_UNSHIFTED
    return table.get(usage, 0)


def ref_decode(script: list[bytes]) -> tuple[list[tuple], int, int, int]:
    """The reference decoder.  Returns the per-poll event lists and the
    lock states the sequence leaves behind."""
    prev = None
    prev_order: list[int] = []
    caps = num = scroll = 0
    out = []
    for rep in script:
        keys = [b for b in rep[2:8]]
        if all(k == 0x01 for k in keys):
            out.append([])            # the phantom - discarded whole
            continue
        mods = rep[0]
        cur = {k for k in keys if k > 0x03}
        events = []
        if prev is None:
            for k in [x for x in keys if x > 0x03]:
                events.append((k, 1))
        else:
            # ORDER NOTE.  HID 1.11 Appendix C says the order of keycodes
            # in the array has no significance, so WHICH ORDER the events
            # come out in is the driver's convention and not a
            # specification claim.  The convention is: releases first, in
            # the order the keys appeared in the PREVIOUS report's array;
            # then presses, in the order they appear in THIS one's.  The
            # reference has to adopt it to compare at all - what stays
            # independent is WHICH events happen, which is the part the
            # specification actually determines.
            for k in prev_order:
                if k not in cur:
                    events.append((k, 0))
            for k in [x for x in keys if x > 0x03]:
                if k not in prev:
                    events.append((k, 1))
        # Characters are computed with the lock state BEFORE this
        # report's lock keys are applied, which is what the driver does
        # and what a person expects: pressing Caps Lock does not
        # capitalise the Caps Lock keypress.
        decoded = [(u, d, ref_char(u, mods, caps, num) if d else 0)
                   for (u, d) in events]
        for (u, d) in events:
            if d:
                if u == 0x39:
                    caps ^= 1
                elif u == 0x53:
                    num ^= 1
                elif u == 0x47:
                    scroll ^= 1
        out.append(decoded)
        prev = cur
        prev_order = [x for x in keys if x > 0x03]
    return out, caps, num, scroll


# The driver emits releases before presses within one poll, and so does
# the reference above.  The ORDER within each group is the array order
# in the driver and sorted() here; for the scripted reports the two
# coincide because every report lists its keys in ascending order except
# #14, which produces no events, and #15, whose new keys 0x07..0x0A come
# after the held ones in the array anyway.  This is asserted rather than
# assumed - see the ORDER NOTE in build_expect().


# =====================================================================
#  THE EXPECTED RESULTS
# =====================================================================
E_NONE = 0
E_HUB_PORT = 38

PROTO_KEYBOARD = 1
PROTO_MOUSE = 2

SPEED_UNDEF = 0

HID_ERR_NONE = 0
HID_ERR_NO_HID = -2
HID_ERR_REPORT = -6
HID_ERR_ARG = -8


def build_expect(topology: dict) -> list[tuple[str, object]]:
    hub: Hub = topology[1]
    e: list[tuple[str, object]] = []

    def add(label, want):
        e.append((label, want))

    # ---- 1
    add("XhciInit succeeded", 1)
    add("no error after init", E_NONE)
    add("MaxPorts as reported by HCSPARAMS1", MAX_PORTS)

    # ---- 2.  keyboard on hub port 2, composite (mouse + keyboard) on
    # hub port 3 = three HID interfaces.  The non-boot HID on hub port 4
    # is refused and the stick on root port 3 is not HID at all.
    add("HID interfaces attached", 3)
    add("HidCount agrees", 3)
    # The last thing HidFindAndAttachAll tried was the non-boot HID on
    # hub port 4, which has no boot interface.  The error is LEFT
    # STANDING deliberately - a walk that clears its error on the way
    # out hides the reason the count is lower than expected.
    add("the last attach failure is named", HID_ERR_NO_HID)

    # ---- 3.  the hub
    add("the hub's slot id", 1)
    add("the hub is on root port 1", 1)
    add("the hub's downstream port count", hub.nports)
    add("the hub's TT think time field", hub.tttt)
    add("bPwrOn2PwrGood, doubled to milliseconds", hub.pgood * 2)
    add("wHubCharacteristics as read", 0x0009 | (hub.tttt << 5))
    add("hub port 1 is empty", 0)
    add("hub port 2 has the keyboard", 1)
    add("hub port 3 has the composite device", 1)
    add("hub port 4 has the non-boot HID", 1)
    add("hub port 2 trained at low speed", SPEED_LS)
    add("hub port 3 trained at full speed", SPEED_FS)
    add("a hub port past bNbrPorts is refused", -1)
    add("and named", E_HUB_PORT)

    # ---- 4.  what was attached.  Handles are allocated in the order
    # HidFindAndAttachAll finds things: hub port 2's keyboard first,
    # then hub port 3's mouse (interface 0) and keyboard (interface 1).
    add("the first keyboard's handle", 1)
    add("the mouse's handle", 2)
    add("it is a keyboard", PROTO_KEYBOARD)
    add("it is a mouse", PROTO_MOUSE)
    add("the keyboard's interface number", 0)
    add("the mouse's interface number", 0)
    add("the keyboard's slot", 3)
    add("the composite device's slot", 4)
    add("the keyboard's interrupt IN endpoint", 0x81)
    add("its max packet size", 8)
    add("its bInterval", 10)
    add("the mouse's endpoint", 0x81)
    add("the mouse's bInterval", 10)
    add("the keyboard accepted SET_IDLE", 1)
    # ZERO, AND THAT IS THE POINT.  The composite device's mouse
    # interface STALLS SET_IDLE - see Composite.idle_refused_ifaces -
    # which HID 1.11 Appendix G permits and which the receiver on this
    # bench really does.  The driver must record the refusal, survive
    # it, and go on using the pipe: everything after this assertion is
    # a transfer on the endpoint that stall halted.
    add("the mouse accepted SET_IDLE", 0)
    add("the composite device's second interface was claimed too", 3)
    add("and it is interface 1", 1)
    add("on the same slot as the mouse", 4)

    # ---- 5.  the pure layout function
    layout = [
        ("a", 0x04, 0, 0, 0), ("A by shift", 0x04, 0x02, 0, 0),
        ("A by caps", 0x04, 0, 1, 0),
        ("a by caps and shift together", 0x04, 0x02, 1, 0),
        ("A by RIGHT shift", 0x04, 0x20, 0, 0),
        ("1", 0x1E, 0, 0, 0), ("!", 0x1E, 0x02, 0, 0),
        ("caps does not shift a digit", 0x1E, 0, 1, 0),
        ("0", 0x27, 0, 0, 0), ("close paren", 0x27, 0x02, 0, 0),
        ("Return", 0x28, 0, 0, 0), ("Escape", 0x29, 0, 0, 0),
        ("Backspace", 0x2A, 0, 0, 0), ("Tab", 0x2B, 0, 0, 0),
        ("Space", 0x2C, 0, 0, 0), ("underscore", 0x2D, 0x02, 0, 0),
        ("apostrophe", 0x34, 0, 0, 0), ("double quote", 0x34, 0x02, 0, 0),
        ("grave", 0x35, 0, 0, 0), ("tilde", 0x35, 0x02, 0, 0),
        ("question mark", 0x38, 0x02, 0, 0),
        ("Caps Lock itself has no character", 0x39, 0, 0, 0),
        ("F1 has no character", 0x3A, 0, 0, 0),
        ("Right arrow has no character", 0x4F, 0, 0, 0),
        ("Delete Forward is ASCII DEL", 0x4C, 0, 0, 0),
        ("keypad 1 with Num Lock off", 0x59, 0, 0, 0),
        ("keypad 1 with Num Lock on", 0x59, 0, 0, 1),
        ("keypad 0", 0x62, 0, 0, 1),
        ("keypad Enter ignores Num Lock", 0x58, 0, 0, 0),
        ("Non-US backslash", 0x64, 0, 0, 0),
        ("Non-US pipe", 0x64, 0x02, 0, 0),
        ("Non-US hash", 0x32, 0, 0, 0),
        ("keypad equals", 0x67, 0, 0, 1),
        ("F13 is past the table", 0x68, 0, 0, 0),
    ]
    for label, u, m, c, n in layout:
        add("HidKeyChar: " + label, ref_char(u, m, c, n))
    add("HidKeyChar: an out-of-range usage", 0)
    add("HidKeyChar: a negative usage", 0)

    # ---- 6.  the scripted keyboard sequence
    decoded, caps, num, scroll = ref_decode(KBD_SCRIPT)
    for i, evs in enumerate(decoded):
        add(f"poll {i}: event count", len(evs))
        for j in range(6):
            if j < len(evs):
                u, d, ch = evs[j]
                add(f"poll {i} event {j}: usage", u)
                add(f"poll {i} event {j}: down", d)
                add(f"poll {i} event {j}: character", ch)
            else:
                add(f"poll {i} slot {j}: usage", 0)
                add(f"poll {i} slot {j}: down", 0)
                add(f"poll {i} slot {j}: character", 0)
    add("Caps Lock after the sequence", caps)
    add("Num Lock after the sequence", num)
    add("Scroll Lock after the sequence", scroll)
    add("no key events were dropped", 0)
    add("one timing sample per poll", KBD_POLLS)
    add("the tick total is non-zero", 1)
    add("the worst case is not below the mean", 1)

    # ---- 7.  the lamps.  Caps Lock is on, so the lamp byte is $02.
    add("HidSyncLeds succeeded", 1)
    add("the lamp byte", 0x02)
    add("a second sync is a no-op and still succeeds", 1)
    add("and the lamp byte is unchanged", 0x02)
    add("HidSetLeds with every bit set succeeded", 1)
    add("and was trimmed to the five defined bits", 0x1F)
    add("HidSetLeds on a mouse is refused", 0)
    add("and named", HID_ERR_ARG)

    # ---- 8.  the mouse
    dx = dy = wheel = 0
    btn = 0
    for i, rep in enumerate(MOUSE_SCRIPT):
        b = rep[0] & 0x07
        sx = rep[1] - 256 if rep[1] > 127 else rep[1]
        sy = rep[2] - 256 if rep[2] > 127 else rep[2]
        sw = rep[3] - 256 if rep[3] > 127 else rep[3]
        moved = 1 if (sx or sy or sw or b != btn) else 0
        btn = b
        dx += sx
        dy += sy
        wheel += sw
        add(f"mouse poll {i}: something changed", moved)
        add(f"mouse poll {i}: buttons", btn)
    add("accumulated dx over the whole sequence", dx)
    add("accumulated dy", dy)
    add("accumulated wheel", wheel)
    add("a fourth byte arrived, so there is a wheel", 1)
    add("dx is cleared by HidMouseTake", 0)
    add("dy is cleared", 0)
    add("the wheel is cleared", 0)
    add("buttons are STATE and are not cleared", btn)

    # ---- 9.  refusals
    add("a keyboard poll on a mouse is refused", HID_ERR_ARG)
    add("a mouse poll on a keyboard is refused", HID_ERR_ARG)
    add("handle 0 is refused", HID_ERR_ARG)
    add("a handle past the table is refused", HID_ERR_ARG)
    add("HidSlot(0) is 0", 0)
    add("HidProtocol(0) is none", 0)
    add("HidFind for a protocol nobody has", 0)

    last = KBD_SCRIPT[-1]
    for i in range(8):
        add(f"the last report's byte {i}", last[i])
    add("the last report's length", 8)

    # ---- 10
    add("the count after detaching one", 2)
    add("a detached handle has no slot", 0)
    add("and polling it is refused", HID_ERR_ARG)

    add("the arena was used and did not overflow", None)   # range test
    # xh_err is STICKY - nothing clears it on success - so the last
    # thing to have failed is still named at the end of the run, and
    # that is the deliberate out-of-range hub port above.  Checked
    # rather than ignored, because a DIFFERENT error here means
    # something failed silently in between.
    add("the sticky xHCI error is still the hub-port refusal", E_HUB_PORT)
    add("the check count the program itself counted", None)  # length
    return e


def build(compiler: str, src: pathlib.Path, img: pathlib.Path) -> str:
    """Compile a self-test program. It is a diagnostic, not a board file,
    so no build is recorded."""
    r = subprocess.run([compiler, "--compile", str(src), "-t", "pi4",
                        "--load-addr", hex(LOAD), "-s", "-o", str(img)],
                       cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
                       text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, check=False)
    if r.returncode != 0 or not img.exists() or "pmfc: OK" not in r.stdout:
        raise SystemExit(f"The compiler did not build {src.name}; its "
                         f"output follows.\n{r.stdout}")
    return r.stdout


def load_syms(img: pathlib.Path) -> dict[str, int]:
    text = (img.parent / (img.name + ".sym")).read_text(encoding="utf-8-sig")
    return {k: int(v) for k, v in
            (line.split("=", 1) for line in text.splitlines() if "=" in line)}


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"),
                    help="the PureMetal Forge compiler executable "
                         "(default: the PMF_COMPILER environment variable)")
    ap.add_argument("--break", dest="only", metavar="NAME",
                    help="build one named breakage and report how it fails")
    ap.add_argument("--no-breaks", action="store_true",
                    help="run the healthy driver only, skip the negative "
                         "controls")
    args = ap.parse_args(argv[1:]); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    if not args.compiler:
        ap.error("No compiler was given. Pass --compiler <path to "
                 "PureMetalForge.exe> or set the PMF_COMPILER environment "
                 "variable.")
    return args


def make_topology() -> dict:
    keyboard = Keyboard(KBD_SCRIPT, REPORT_PROTO_ANSWER)
    composite = Composite(MOUSE_SCRIPT, KBD2_SCRIPT, REPORT_PROTO_ANSWER)
    nonboot = NonBootHid([kr(0)], REPORT_PROTO_ANSWER)
    hub = Hub({2: keyboard, 3: composite, 4: nonboot})
    return {1: hub, 3: MassStorage()}


def execute(img: pathlib.Path, sym: dict[str, int], topology: dict,
            budget: int):
    blob = img.read_bytes()
    cpu = A64(pc=LOAD)
    for i, b in enumerate(blob):
        cpu.memory[LOAD + i] = b
    attach_symbols(cpu, img, LOAD)
    ctl = Ctl(cpu, topology)
    install(cpu, ctl)
    trap = LOAD + sym["_a64_end_trap"]
    steps = 0
    finished = False
    for steps in range(budget):
        if cpu.pc == trap:
            finished = True
            break
        cpu.step()
    return ctl, cpu, steps, finished


def collect(cpu: A64, sym: dict[str, int]) -> list[int]:
    nres = cpu.load(sym["global_nres"], 8)
    base = sym["global_res"]
    got = [cpu.load(base + i * 8, 8) for i in range(min(nres, 640))]
    return [v - (1 << 64) if v >= (1 << 63) else v for v in got]


def compare(got: list[int], ctl: Ctl, expect: list, topology: dict
            ) -> list[str]:
    fails: list[str] = []
    if len(got) != len(expect):
        fails.append(f"check count: the program made {len(got)}, the "
                     f"harness expects {len(expect)}")
    for i, (label, want) in enumerate(expect):
        if i >= len(got):
            fails.append(f"#{i} {label}: never ran")
            continue
        if want is None:
            continue
        if got[i] != want:
            fails.append(f"#{i} {label}: got {got[i]}, want {want}")

    # The two range tests, done by name rather than by index arithmetic.
    for i, (label, want) in enumerate(expect):
        if want is None and i < len(got):
            if "arena" in label and not (0 < got[i] <= 558912):
                fails.append(f"#{i} {label}: used {got[i]} bytes")
            # The program's own count, recorded by the LAST Chk, is one
            # short of the total because Chk stores before it increments,
            # so this compares against len - 1.  The off-by-one is by
            # construction.  What the check catches is a program that
            # overflowed #RES_MAX, where the counter keeps rising and the
            # array quietly stops - which would otherwise read as a
            # shorter, passing run.
            if "check count the program" in label and got[i] != len(got) - 1:
                fails.append(f"#{i} {label}: the program counted "
                             f"{got[i]} before its last check and made "
                             f"{len(got)} in total")

    def want(name: str, gotv, wantv) -> None:
        if gotv != wantv:
            fails.append(f"model: {name}: got {gotv!r}, want {wantv!r}")

    hub: Hub = topology[1]
    kbd = hub.children[2]
    comp = hub.children[3]
    stick = topology[3]

    want("PCI bus mastering was enabled", ctl.cfg[0x04] & 0x04, 0x04)
    want("the hub was configured", hub.configured, 1)
    want("the keyboard was configured", kbd.configured, 1)
    want("SET_PROTOCOL reached the keyboard", kbd.set_protocol_seen, True)
    want("and it selected BOOT protocol, not report", kbd.protocol, 0)
    want("SET_IDLE reached the keyboard", kbd.set_idle_seen, True)
    want("the composite device's mouse interface is in boot protocol",
         comp.protocol_by_iface.get(0), 0)
    want("the composite device's keyboard interface is in boot protocol too",
         comp.protocol_by_iface.get(1), 0)
    want("every scripted keyboard report was consumed",
         kbd.next, KBD_POLLS)
    want("every scripted mouse report was consumed",
         comp.next, MOUSE_POLLS)
    want("the keyboard's lamps were driven", kbd.leds, 0x1F)
    want("the stick was never configured by the HID walk",
         stick.configured, 0)

    # Every hub port was powered before anything was asked of it.
    for p in range(1, hub.nports + 1):
        want(f"hub port {p} was powered", hub.powered[p], True)
    want("hub port 1, which is empty, was never reset",
         hub.reset_done[1], False)
    want("hub port 2 was reset", hub.reset_done[2], True)
    want("every port reset change bit was cleared",
         all(v & PC_RESET == 0 for v in hub.change.values()), True)

    # The slot contexts, read back from what the controller was handed.
    hubslot = [r for r in ctl.addr_ctx if r["port"] == 1 and r["route"] == 0]
    want("exactly one device was addressed on root port 1",
         len(hubslot), 1)
    kbdctx = [r for r in ctl.addr_ctx if r["route"] == 2]
    want("exactly one device was addressed behind hub port 2",
         len(kbdctx), 1)
    if kbdctx:
        r = kbdctx[0]
        want("the keyboard's route string is its hub port", r["route"], 2)
        want("the keyboard's root hub port is the hub's", r["port"], 1)
        want("the keyboard's TT Hub Slot ID is the hub's slot",
             r["tt_slot"], hubslot[0]["slot"] if hubslot else -1)
        want("the keyboard's TT Port Number is its hub port",
             r["tt_port"], 2)
        want("the keyboard is not marked multi-TT", r["mtt"], False)
        want("the keyboard's endpoint-0 max packet is the low-speed 8",
             r["maxpacket"], 8)

    marks = [r for r in ctl.config_ep if r["hub"]]
    want("exactly one slot was marked as a hub", len(marks), 1)
    if marks:
        want("it is the hub's slot", marks[0]["slot"],
             hubslot[0]["slot"] if hubslot else -1)
        want("with only the slot context flag set", marks[0]["add"], 1)

    # ORDER: the hub must have been marked before the keyboard behind it
    # was addressed.  The model already refuses the reverse, but the
    # positive statement is made here too, so that a run in which the
    # keyboard was never addressed at all cannot pass by vacuity.
    marked_at = None
    for i, entry in enumerate(ctl.log):
        if entry.startswith("config-ep") and "hub=True" in entry:
            marked_at = i
    kbd_at = None
    for i, entry in enumerate(ctl.log):
        if "keyboard" in entry and entry.startswith("address"):
            kbd_at = i
    want("the hub was marked as a hub", marked_at is not None, True)
    want("the keyboard behind it was addressed", kbd_at is not None, True)
    if marked_at is not None and kbd_at is not None:
        want("and the marking happened FIRST", marked_at < kbd_at, True)

    for v in ctl.violations:
        fails.append(f"model refused: {v}")
    return fails


# =====================================================================
#  THE DELIBERATE BREAKAGES
#
#  Each is a text substitution into a COPY of hid.pi4 or xhci.pi4.  A
#  gate that passes with the driver broken is worth nothing, so this is
#  how that is demonstrated rather than asserted.
# =====================================================================
BREAKAGES = {
    # ---- hid.pi4 --------------------------------------------------------
    # Skip SET_PROTOCOL.  The modelled keyboard stays in REPORT protocol
    # and answers with a nine-byte, Report-ID-prefixed report - which is
    # what a real keyboard with media keys does, and is the whole reason
    # the request is mandatory.
    "no-set-protocol": ("hid", """  If XhciControlIn(#HID_RT_OUT, #HID_REQ_SET_PROTOCOL, #HID_PROTOCOL_BOOT, iface, 0) < 0
    hid_slot[h] = 0
    ProcedureReturn hid_Fail(#HID_ERR_PROTOCOL)
  EndIf
""", "\n"),

    # Ask for REPORT protocol instead of BOOT.  A one-character mistake
    # that a gate which only checks "SET_PROTOCOL was sent" would miss.
    "set-protocol-report": ("hid",
        "#HID_REQ_SET_PROTOCOL, #HID_PROTOCOL_BOOT, iface, 0",
        "#HID_REQ_SET_PROTOCOL, #HID_PROTOCOL_REPORT, iface, 0"),

    # Treat the phantom rollover state as an ordinary report.  Emits key
    # UP events for keys that are still held, and makes the report after
    # it emit them all again as downs.
    "no-phantom-check": ("hid", """  If hid_IsPhantom(base) <> 0
    ProcedureReturn 0
  EndIf
""", "\n"),

    # Look at array slot 2 only, instead of diffing the whole six-slot
    # array.  HID 1.11 Appendix C: "The order of keycodes in array
    # fields has no significance."  Script report 14 swaps two keys.
    "watch-slot-2-only": ("hid",
        "Procedure.i hid_InArray(base.i, usage.i, isPrev.i)\n"
        "  Define i.i\n"
        "  Define v.i\n"
        "  i = 2\n",
        "Procedure.i hid_InArray(base.i, usage.i, isPrev.i)\n"
        "  Define i.i\n"
        "  Define v.i\n"
        "  i = 2\n"
        "  If usage > 0\n"
        "    If isPrev = 0\n"
        "      If hid_cur[base + 2] = usage\n"
        "        ProcedureReturn 1\n"
        "      EndIf\n"
        "      ProcedureReturn 0\n"
        "    EndIf\n"
        "  EndIf\n"),

    # Caps Lock ORs with Shift instead of XORing.  Caps+Shift+a becomes
    # A, which is wrong on every keyboard ever made.
    "caps-or-shift": ("hid",
        "    If capsLock <> 0\n      shifted = shifted ! 1\n    EndIf",
        "    If capsLock <> 0\n      shifted = 1\n    EndIf"),

    # Toggle the lock keys from the REPORT rather than from the down
    # edge.  A key held across two polls toggles Caps Lock twice.
    "locks-on-every-report": ("hid",
        "    If hid_evDown[i] <> 0\n"
        "      If hid_evUsage[i] = #HID_USAGE_CAPSLOCK",
        "    If 1 = 1\n"
        "      If hid_evUsage[i] = #HID_USAGE_CAPSLOCK"),

    # Overwrite the mouse accumulators instead of adding.  The pointer
    # moves at the speed of the last report only.
    "mouse-no-accumulate": ("hid",
        "  hid_mouseDx = hid_mouseDx + dx\n"
        "  hid_mouseDy = hid_mouseDy + dy",
        "  hid_mouseDx = dx\n"
        "  hid_mouseDy = dy"),

    # Read the mouse's dx as unsigned.  Every leftward movement becomes
    # a large rightward one.
    "mouse-unsigned": ("hid",
        "Procedure.i hid_S8(v.i)\n  If v > 127\n    ProcedureReturn v - 256\n  EndIf",
        "Procedure.i hid_S8(v.i)\n  If v > 255\n    ProcedureReturn v - 256\n  EndIf"),

    # Do not re-select the slot before a transfer.  With a keyboard and
    # a mouse on different slots, a poll goes to whichever device spoke
    # last.
    "no-slot-select": ("hid",
        "  If XhciUseSlot(hid_slot[h]) = 0\n"
        "    ProcedureReturn hid_Fail(#HID_ERR_SLOT)\n"
        "  EndIf\n"
        "  ProcedureReturn 1\n"
        "EndProcedure",
        "  ProcedureReturn 1\n"
        "EndProcedure"),

    # Never claim a composite device's second interface.
    "no-composite": ("hid",
        "            h2 = HidAttach(slot, 0, hid_iface[h])\n"
        "            If h2 <> 0\n"
        "              found = found + 1\n"
        "            EndIf\n",
        "\n"),

    # Accept a HID interface whose subclass is not 1.  The non-boot
    # device on hub port 4 is then claimed, SET_PROTOCOL is meaningless
    # on it, and the count is wrong.
    "accept-non-boot": ("hid",
        "          If PeekA(hid_Desc(off + 6)) = #HID_SUBCLASS_BOOT",
        "          If PeekA(hid_Desc(off + 6)) >= 0"),

    # A MISALIGNED WIDE READ. This is the hole that once let an emulator
    # gate certify a payload which wedged the board dead, and the mutation
    # exists to prove align_guard() is actually called from this gate's
    # closures rather than merely imported.  Reading the port status
    # halves with one 32-bit load at an odd offset is exactly the shape
    # of the real bug: correct arithmetic, fatal address.
    "misaligned-report-read": ("xhci",
        "  st = PeekA(xh_bounce + 0) | (PeekA(xh_bounce + 1) << 8)",
        "  st = PeekL(xh_bounce + 1) & $FFFF"),

    # ---- xhci.pi4 -------------------------------------------------------
    # Never tell the controller the hub is a hub.  Every port request
    # still works perfectly; the keyboard behind it is unreachable.  This
    # is the failure that looks like a broken keyboard and is not.
    "no-hub-bit": ("xhci",
        "  info = info | #XHCI_DEV_HUB",
        "  info = info"),

    # Leave the transaction translator fields zero for a low-speed
    # device behind a hub.
    "no-tt": ("xhci",
        "  tt = (ttSlot & $FF) | ((ttPort & $FF) << 8)",
        "  tt = 0"),

    # Build no route string, so every device behind the hub is addressed
    # as though it were on the root port - which is the device the hub
    # itself occupies.
    "no-route": ("xhci",
        "  info = (route & #XHCI_ROUTE_MASK)",
        "  info = 0"),

    # Report the wrong downstream port count to the controller.
    "wrong-hub-ports": ("xhci",
        "  info2 = (info2 & $00FFFFFF) | ((nports & $FF) << 24)",
        "  info2 = (info2 & $00FFFFFF) | (1 << 24)"),

    # Rebuild the hub's slot context from zero instead of copying the
    # output context, losing the root hub port the controller
    # established at Address Device time.
    "hub-ctx-not-copied": ("xhci",
        "  info  = PeekN(out + 0)\n  info2 = PeekN(out + 4)\n  tt    = PeekN(out + 8)",
        "  info  = 0\n  info2 = 0\n  tt    = 0"),

    # Never power the hub's downstream ports.  The modelled hub reports
    # nothing connected on an unpowered port, so the walk finds an empty
    # hub - which is what a real one does too.
    "no-port-power": ("xhci",
        "    If XhciHubSetPortFeature(i, #XHCI_PF_POWER) = 0\n"
        "      xh_hubSlot = 0\n"
        "      ProcedureReturn xh_Fail(#XHCI_ERR_PORT_POWER)\n"
        "    EndIf\n",
        "\n"),

    # Leave the port reset change bit set.
    "no-clear-c-reset": ("xhci",
        "  XhciHubClearPortFeature(port, #XHCI_PF_C_RESET)",
        "  "),

    # PUT THE RING DEADLOCK BACK.  This is the code xh_RingRoom carried
    # until 2026-08-28: when a transfer descriptor will not fit before
    # the Link TRB, hand the Link TRB over and jump the enqueue index to
    # zero WITHOUT writing the TRBs in between.  The controller's
    # dequeue pointer is left in the gap, on a TRB it does not own, and
    # it never reaches the Link TRB.  Every transfer after that times
    # out.
    #
    # It is a mutation and not merely a fixed bug because the branch is
    # only reached when endpoint zero carries a MIX of two-TRB and
    # three-TRB transfer descriptors, which no workload in this tree did
    # before hid.pi4 - and a fix whose test can be deleted without
    # anything going red is not tested.
    "ringroom-skip-no-pad": ("xhci",
        "    xh_QueueTrb(r, 0, 0, 0, (#XHCI_TRB_TR_NOOP << 10))\n"
        "    pad = pad - 1\n"
        "  Wend",
        "    pad = pad - 1\n"
        "  Wend\n"
        "  pad = xh_TrbAddr(r, #XHCI_LINK_INDEX)\n"
        "  PokeN(pad + 12, (PeekN(pad + 12) & (~#XHCI_TRB_CYCLE)) | xh_ringCycle[r])\n"
        "  xh_Clean(pad, #XHCI_TRB_BYTES)\n"
        "  xh_ringCycle[r] = xh_ringCycle[r] ! 1\n"
        "  xh_ringEnq[r] = 0"),

    # Set the multi-TT bit without having selected the hub's multi-TT
    # alternate setting.  Intermittent on real hardware; caught here.
    "wrong-mtt": ("xhci",
        "  If multi <> 0\n    info = info | #XHCI_DEV_MTT\n  Else",
        "  If multi = 0\n    info = info | #XHCI_DEV_MTT\n  Else"),

    # ---- the one that mattered, added 2026-08-28 ---------------------
    # Report the stall and leave the endpoint halted, which is what the
    # driver did until this day.  It is here rather than only in
    # a64_xhci_check.py because this is where it BITES: the composite
    # device's mouse interface legally stalls SET_IDLE during attach,
    # and everything the gate does afterwards - the second interface's
    # attach, every poll of either interface, the LED writes - is a
    # transfer on the endpoint that stall halted.
    #
    # ON SILICON the same mutation is three consecutive five-second
    # timeouts out of a sixteen-second watchdog budget, and it reads as
    # "enumeration is too slow" rather than as a stall that was never
    # cleared.  Enumeration was 445 ms.
    "no-clear-halt": ("xhci",
        "  If xh_lastComp = #XHCI_COMP_STALL\n"
        "    If xh_ClearHalt(xh_slot, xh_slot, 1) = 0\n"
        "      ProcedureReturn -1      ; xh_err already names the recovery failure\n"
        "    EndIf\n"
        "    xh_Fail(#XHCI_ERR_STALL)\n",
        "  If xh_lastComp = #XHCI_COMP_STALL\n"
        "    xh_Fail(#XHCI_ERR_STALL)\n"),

    # Aim the recovered dequeue pointer at the base of the ring instead
    # of at the enqueue position.  The TRBs below the enqueue point
    # still carry the producer's cycle bit, so the controller re-runs
    # the SET_IDLE that just stalled.
    "deq-at-ring-base": ("xhci",
        "  deq = xh_TrbAddr(ring, xh_ringEnq[ring]) | xh_ringCycle[ring]",
        "  deq = xh_ringBase[ring] | xh_ringCycle[ring]"),

    # Stop recording whether SET_IDLE was accepted, and claim it always
    # was.  HidIdleAccepted() is how a caller learns that a keyboard is
    # out of specification - HID 1.11 Appendix C lists Set_Idle support
    # as a keyboard design requirement - and a driver that answers "yes"
    # for a device that stalled it is inventing the answer.
    "idle-always-accepted": ("hid",
        "  If XhciControlIn(#HID_RT_OUT, #HID_REQ_SET_IDLE, 0, iface, 0) >= 0\n"
        "    hid_idle[h] = 1\n"
        "  EndIf",
        "  XhciControlIn(#HID_RT_OUT, #HID_REQ_SET_IDLE, 0, iface, 0)\n"
        "  hid_idle[h] = 1"),
}

# ---------------------------------------------------------------------
# NOT breakages - mutations that were expected to fail and did not, kept
# here so the finding does not get lost.  Each must STILL PASS.
# ---------------------------------------------------------------------
HARMLESS = {
    # SET_IDLE is issued and its result recorded, but nothing in this
    # driver reads a report from an interrupt endpoint, so the idle rate
    # cannot change any answer.  Deleting the call was expected to be
    # invisible and is - the ONLY thing that moves is
    # HidIdleAccepted(), which the program checks, so the mutation is
    # written to leave that reporting alone and remove only the effect.
    # It is recorded because "we send SET_IDLE and it matters" would be
    # a superstition: it does not matter to THIS driver, and it will the
    # day interrupt endpoints land.
    "set-idle-duration-nonzero": ("hid",
        "#HID_REQ_SET_IDLE, 0, iface, 0",
        "#HID_REQ_SET_IDLE, $2000, iface, 0"),

    # THE REJECTED ALTERNATIVE TO NO-OP PADDING: do nothing at all, and
    # let a transfer descriptor STRADDLE the Link TRB.  U-Boot allows it
    # - xhci-ring.c's inc_enq() hands the Link TRB over mid-descriptor
    # whenever more_trbs_coming is set.
    #
    # a64_xhci_check.py already records this mutation as harmless, and
    # THAT MEASUREMENT WAS WORTHLESS: with only three-TRB transfers and
    # 63 usable slots the enqueue index lands exactly on the Link TRB
    # every lap, so the padding and the straddle both never happen
    # and the mutation removed code that never ran.  This workload mixes
    # two- and three-TRB descriptors and reaches the branch dozens of
    # times, so the measurement here is a real one.
    #
    # It passing is the reason the fix's comment can say the straddle
    # was REJECTED rather than BROKEN.  Padding was chosen anyway,
    # because the deferred-cycle trick in XhciControlIn is easier to
    # reason about when a descriptor cannot cross a producer-cycle
    # toggle - but that is a preference, and this line is the evidence
    # that it is only a preference.
    "straddle-the-link": ("xhci",
        "  pad = #XHCI_LINK_INDEX - xh_ringEnq[r]",
        "  pad = 0"),
}


def make_broken(name: str, work: pathlib.Path) -> pathlib.Path:
    """Write a broken copy of hid.pi4 or xhci.pi4, and a copy of the
    self-test that includes it by absolute path, into `work`.  The anchor
    must match exactly once: a moved anchor is a breakage that silently
    tests nothing, and a doubled one is aimed at two places."""
    which, old, new = BREAKAGES.get(name) or HARMLESS[name]
    lib = LIB_HID if which == "hid" else LIB_XHCI
    text = lib.read_text(encoding="utf-8")
    hits = text.count(old)
    if hits != 1:
        raise SystemExit(
            f"Breakage {name!r} matched its anchor {hits} times in "
            f"{lib.name}, not once. The breakage must be RE-AIMED at Anvil's "
            f"current source, not skipped. A mutation whose anchor has moved "
            f"silently tests nothing.")
    out_lib = work / f"hid_broken_{which}.pi4"
    out_lib.write_text(text.replace(old, new, 1), encoding="utf-8")
    include = f'"RaspberryPi4/Lib/{lib.name}"'
    prog = SRC.read_text(encoding="utf-8")
    if prog.count(include) != 1:
        raise SystemExit(f"The self-test no longer includes {lib.name} "
                         f"exactly once, so a broken copy cannot be swapped "
                         f"in.")
    out_src = work / "hid_broken_main.pi4"
    out_src.write_text(prog.replace(include, f'"{out_lib}"'),
                       encoding="utf-8")
    return out_src


def once(compiler: str, src: pathlib.Path, img: pathlib.Path,
         budget: int = 200_000_000):
    build(compiler, src, img)
    sym = load_syms(img)
    topology = make_topology()
    expect = build_expect(topology)
    try:
        ctl, cpu, steps, finished = execute(img, sym, topology, budget)
    except SystemExit:
        raise
    except BaseException as exc:
        # An AlignmentFault, or anything else the interpreter raises, is
        # a RED GATE and not a crashed harness.  Its message names the
        # procedure and the source line.
        return [f"the run stopped: {exc}"], 0, len(expect)
    got = collect(cpu, sym)
    fails = compare(got, ctl, expect, topology)
    if not finished:
        fails.insert(0, f"the program did not reach its end trap within "
                        f"{budget} interpreter steps - the driver hung")
    return fails, steps, len(expect)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.only is not None and args.only not in BREAKAGES \
            and args.only not in HARMLESS:
        raise SystemExit(f"There is no breakage named {args.only!r}.")

    with tempfile.TemporaryDirectory(prefix="a64-hid-") as tmp:
        work = pathlib.Path(tmp)
        broken_img = work / "hid_broken.img"

        if args.only:
            src = make_broken(args.only, work)
            fails, steps, total = once(args.compiler, src, broken_img,
                                       BREAK_BUDGET)
            print(f"--break {args.only}: {len(fails)} of {total} assertions "
                  f"failed, {steps} steps")
            for f in fails[:12]:
                print("  " + f)
            return 0 if fails else 1

        fails, steps, total = once(args.compiler, SRC,
                                   work / "hidselftest.img")
        if fails:
            for f in fails:
                print("FAIL " + f)
            print(f"FAILED: {len(fails)} of {total} assertions, {steps} steps")
            return 1
        print(f"PASS: hid.pi4 walked a modelled hub, attached a keyboard, a "
              f"mouse and a composite device's second interface, and decoded "
              f"{KBD_POLLS} scripted reports - {total} assertions, {steps} "
              f"interpreter steps")

        if args.no_breaks:
            return 0

        print("\nnegative controls - each of these must FAIL:")
        bad = []
        for name in BREAKAGES:
            src = make_broken(name, work)
            try:
                bfails, _, _ = once(args.compiler, src, broken_img,
                                    BREAK_BUDGET)
            except SystemExit:
                print(f"  {name:24s} REFUSED AT COMPILE TIME")
                continue
            if bfails:
                print(f"  {name:24s} {len(bfails)} assertion(s) failed"
                      f"   e.g. {bfails[0][:88]}")
            else:
                print(f"  {name:24s} *** STILL PASSED - the gate does not "
                      f"cover this ***")
                bad.append(name)
        if bad:
            print(f"\nGATE IS WEAK: {len(bad)} breakage(s) went undetected: "
                  f"{', '.join(bad)}")
            return 1
        print(f"\nevery one of the {len(BREAKAGES)} deliberate breakages was "
              f"caught.")

        print("\nmutations MEASURED HARMLESS - each of these must still PASS:")
        weak = []
        for name in HARMLESS:
            src = make_broken(name, work)
            hfails, _, _ = once(args.compiler, src, broken_img, BREAK_BUDGET)
            if hfails:
                print(f"  {name:24s} NOW FAILS - the note in HARMLESS is "
                      f"wrong and it belongs in BREAKAGES")
                weak.append(name)
            else:
                print(f"  {name:24s} still passes, as recorded")
        if weak:
            return 1
        print(f"\nPASS: {total} assertions; {len(BREAKAGES)} of "
              f"{len(BREAKAGES)} breakages rejected; {len(HARMLESS)} harmless "
              f"mutations still pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

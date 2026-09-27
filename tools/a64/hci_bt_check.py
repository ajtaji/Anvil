#!/usr/bin/env python3
"""Desk gate: Bluetooth over HCI/H4 - Anvil/Net/hci.pbi on the Pi 4
(RaspberryPi4/Lib/bt_uart.pi4, PL011 on GPIO 30-33) and the Pi 5
(RaspberryPi4/Lib/bt_uart_7271.pi4, BCM2712 uarta).

The compiled code (-t pi4 and -t pi5) runs under tools/a64/a64_interp.py
against models written from the pinned sources, not from the libraries:

  CONTROLLER (the CYW43455's HCI side), from btbcm.c / hci_bcm.c and the
  Core spec: parses H4 commands (01, opcode LITTLE-ENDIAN, plen, params)
  and answers with events. It REFUSES by name: any command before the
  first HCI_Reset; a byte sent unpowered, without RTS/CTS flow control,
  or at a rate other than its own (> 3 %); a patch record sooner than
  50 ms after Download_Minidriver ($FC2E); any command sooner than 250 ms
  after Launch_RAM ($FC4E), or other than HCI_Reset; Update_UART_Baud_Rate
  ($FC18) before the patch was launched and the controller reset. The
  patch it receives must equal the .hcd byte for byte. It answers
  Read_BD_ADDR with btbcm.c's BDADDR_BCM4345C0 placeholder until patched.
  Inquiry: Command Status, a standard Inquiry Result ($02, two devices,
  laid out FIELD BY FIELD), an Inquiry Result with RSSI ($22) repeating
  one of them, an Extended Inquiry Result ($2F), Inquiry Complete.

  PI 4: PL011 at $FE201000 (writes to IBRD/FBRD/LCRH while enabled are
  refused - the TRM rule uart.pi4 cites), BCM2711 GPIO at $FE200000 (the
  CTS/RTS/TXD/RXD pins must be on ALT3 before a byte moves), and the
  mailbox property channel answering SET_GPIO_CONFIG/SET_GPIO_STATE for
  expander line 128 (BT_ON). A board whose PL011 is the console (GPIO
  14/15 on ALT0) must be refused with NO register written at all.

  PI 5: 16550-class uarta at $107D50C000 (reg-shift 2, 96 MHz, MCR AFE),
  the BCM2712 pinctrl at $107D504100 (C0 and D0 layouts, pinctrl-brcmstb-
  bcm2712.c) and gio bank 0 at $107D508500 (BT_REG_ON = bit 29).

Desk proof only; silicon owed.
  py -3 -B tools/a64/hci_bt_check.py --compiler <PureMetalForge.exe> [--mutate]
"""
from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import struct
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import pi5_desk as d                               # noqa: E402

TPS = 200                         # model counter ticks per instruction
MS = 54_000 // 1                  # ticks per ms at 54 MHz
HCD_AT, BUF = 0x2800000, 0x2900000

REL_HCI = "Anvil/Net/hci.pbi"
REL_BT4 = "RaspberryPi4/Lib/bt_uart.pi4"
REL_BT5 = "RaspberryPi4/Lib/bt_uart_7271.pi4"
REL_HWBT = "RaspberryPi4/Board/hw_bt.pi4"
REL_GPIO = "RaspberryPi4/Lib/gpio.pi4"
REL_MBX = "RaspberryPi4/Lib/mailbox.pi4"
REL_TIMER = "RaspberryPi4/Lib/timer.pi4"
REL_CMD = "Anvil/Core/bt_cmd.pbi"
REL_FMT = "Anvil/Core/format.pbi"
INC4 = [REL_TIMER, REL_MBX, REL_GPIO, REL_BT4, REL_HWBT, REL_HCI, REL_FMT, REL_CMD]
INC5 = [REL_TIMER, REL_BT5, REL_HWBT, REL_HCI]

OP_RESET, OP_VER, OP_BD, OP_INQ = 0x0C03, 0x1001, 0x1009, 0x0401
OP_MINI, OP_WRITE_RAM, OP_LAUNCH, OP_BAUD = 0xFC2E, 0xFC4C, 0xFC4E, 0xFC18
PLACEHOLDER = bytes([0xAC, 0x1F, 0x00, 0xC0, 0x45, 0x43])
REAL_BD = bytes([0x66, 0x55, 0x44, 0x33, 0x22, 0x11])      # 11:22:33:44:55:66
DEVS = [(bytes([1, 2, 3, 4, 5, 6]), 0x5A020C, None),
        (bytes([0x10, 0x20, 0x30, 0x40, 0x50, 0x60]), 0x240404, None)]
EXT_DEV = (bytes([0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0xA6]), 0x002540, -61)

# A synthetic .hcd: Write_RAM records and a Launch_RAM, as btbcm_patchram
# walks it (opcode LE, plen, params).
def rec(op, payload):
    return struct.pack("<HB", op, len(payload)) + payload
HCD = (rec(OP_WRITE_RAM, bytes([0x00, 0x00, 0x21, 0x00]) + bytes(range(40))) +
       rec(OP_WRITE_RAM, bytes([0x28, 0x00, 0x21, 0x00]) + bytes(range(100, 160))) +
       rec(OP_LAUNCH, bytes([0xFF, 0xFF, 0xFF, 0xFF])))


class Controller:
    def __init__(self, cpu, hwerr=False):
        self.cpu = cpu
        self.powered = False
        self.baud = 115200
        self.rx = []                  # bytes waiting for the host
        self.buf = []
        self.reset_seen = False
        self.mini_t = None
        self.patch = bytearray()
        self.launch_t = None
        self.post_reset = False
        self.patched = False
        self.cmds = []
        self.hwerr = hwerr
        self.pkt_t = 0

    def now(self):
        return self.cpu.cntpct

    def event(self, code, params):
        self.rx += [0x04, code, len(params)] + list(params)

    def cc(self, op, params=b""):
        self.event(0x0E, bytes([1, op & 0xFF, op >> 8]) + bytes([0]) + params)

    def tx(self, b, host_baud, flow_ok):
        if not self.powered:
            d.die("a byte was sent to the controller while BT_REG_ON/BT_ON was low")
        if not flow_ok:
            d.die("a byte was sent before RTS/CTS flow control was set up")
        if abs(host_baud - self.baud) * 100 > self.baud * 3:
            d.die("the host sends at %d baud and the controller listens at %d" % (host_baud, self.baud))
        if not self.buf:
            self.pkt_t = self.now()      # timing is judged from a packet's FIRST byte
        self.buf.append(b)
        if self.buf[0] != 0x01:
            d.die("H4 packet indicator %#x, not 01 (command)" % self.buf[0])
        if len(self.buf) >= 4 and len(self.buf) == 4 + self.buf[3]:
            op = self.buf[1] | (self.buf[2] << 8)
            params = bytes(self.buf[4:])
            self.buf = []
            self.command(op, params)

    def command(self, op, params):
        t = self.pkt_t
        self.cmds.append(op)
        if not self.reset_seen and op != OP_RESET:
            d.die("command %#06x before the first HCI_Reset" % op)
        if self.launch_t is not None and not self.post_reset:
            if t - self.launch_t < 250 * MS:
                d.die("a command %.0f ms after Launch_RAM; btbcm waits 250 ms" % ((t - self.launch_t) / MS))
            if op != OP_RESET:
                d.die("command %#06x after Launch_RAM before the HCI_Reset btbcm_finalize sends" % op)
        if self.mini_t is not None:
            if t - self.mini_t < 50 * MS:
                d.die("a patch record %.0f ms after Download_Minidriver; btbcm waits 50 ms" % ((t - self.mini_t) / MS))
            self.patch += struct.pack("<HB", op, len(params)) + params
            self.cc(op)
            if op == OP_LAUNCH:
                self.mini_t = None
                self.launch_t = t
            return
        if self.hwerr and op == OP_BD:
            self.event(0x10, bytes([0]))
            return
        if op == OP_RESET:
            self.reset_seen = True
            if self.launch_t is not None:
                self.post_reset = True
                self.patched = True
            self.cc(op)
        elif op == OP_VER:
            self.cc(op, bytes([0x09, 0x00, 0x01, 0x09, 0x0F, 0x00, 0x19, 0x61]))
        elif op == OP_BD:
            self.cc(op, REAL_BD if self.patched else PLACEHOLDER)
        elif op == OP_MINI:
            self.cc(op)
            self.mini_t = self.now()
        elif op == OP_BAUD:
            if not self.patched:
                d.die("Update_UART_Baud_Rate before the patch was loaded and the controller reset")
            if len(params) != 6 or params[:2] != b"\0\0":
                d.die("Update_UART_Baud_Rate parameters %s, want 00 00 + rate LE32" % params.hex())
            self.cc(op)
            self.baud = struct.unpack("<I", params[2:])[0]
        elif op == OP_INQ:
            if params != bytes([0x33, 0x8B, 0x9E, 4, 0]):
                d.die("Inquiry parameters %s, want GIAC 33 8b 9e, length 4, 0 responses" % params.hex())
            self.event(0x0F, bytes([0, 1, op & 0xFF, op >> 8]))
            n = len(DEVS)
            p = bytes([n]) + b"".join(a for a, _, _ in DEVS) + bytes([1] * n) + bytes(2 * n)
            p += b"".join(struct.pack("<I", c)[:3] for _, c, _ in DEVS) + bytes(2 * n)
            self.event(0x02, p)
            a, c, _ = DEVS[0]                                     # heard again, with RSSI
            self.event(0x22, bytes([1]) + a + bytes([1, 0]) + struct.pack("<I", c)[:3] + bytes(2) + bytes([256 - 70]))
            a, c, r = EXT_DEV
            self.event(0x2F, bytes([1]) + a + bytes([1, 0]) + struct.pack("<I", c)[:3] + bytes(2) + bytes([256 + r]) + bytes(240))
            self.event(0x01, bytes([0]))
        else:
            d.die("unexpected command %#06x" % op)


class Pi4:
    """PL011 + BCM2711 GPIO + mailbox (BT_ON)."""
    UART, GPIO = 0xFE201000, 0xFE200000
    MBX_READ, MBX_ST0, MBX_WRITE, MBX_ST1 = 0xFE00B880, 0xFE00B898, 0xFE00B8A0, 0xFE00B8B8

    def __init__(self, cpu, console_on_pl011, ctl):
        self.cpu, self.ctl = cpu, ctl
        self.u = {0x24: 0, 0x28: 0, 0x2C: 0, 0x30: 0, 0x38: 0}
        self.g = {}
        f1 = (4 if console_on_pl011 else 2)
        self.g[0x04] = (f1 << 12) | (f1 << 15)       # GPIO 14/15: ALT0 = 4 / ALT5 = 2
        self.writes = []
        self.pending = []

    def fsel(self, pin):
        return (self.g.get((pin // 10) * 4, 0) >> ((pin % 10) * 3)) & 7

    def pull(self, pin):
        return (self.g.get(0xE4 + (pin // 16) * 4, 0) >> ((pin % 16) * 2)) & 3

    def host_baud(self):
        div64 = self.u[0x24] * 64 + self.u[0x28]
        return 0 if div64 == 0 else 48_000_000 * 4 // div64

    def flow_ok(self):
        return (self.u[0x30] & 0xC000) == 0xC000 and all(self.fsel(p) == 7 for p in (30, 31, 32, 33))

    def mailbox(self, msg):
        a = (msg & ~0xF) & 0x3FFFFFFF
        w = lambda o: sum(self.cpu.memory.get(a + o + i, 0) << (8 * i) for i in range(4))
        def put(o, v):
            for i in range(4):
                self.cpu.memory[a + o + i] = (v >> (8 * i)) & 0xFF
        tag = w(8)
        if tag == 0x00038043:
            vals = [w(20 + 4 * i) for i in range(6)]
            if vals[0] != 128 or vals[1] != 1:
                d.die("SET_GPIO_CONFIG %r: want expander line 128 as an output" % vals)
            self.ctl.powered = bool(vals[5])
        elif tag == 0x00038041:
            if w(20) != 128:
                d.die("SET_GPIO_STATE on line %d, not 128 (BT_ON)" % w(20))
            self.ctl.powered = bool(w(24))
        else:
            d.die("mailbox tag %#x - not one Bluetooth power needs" % tag)
        put(20, 0)
        put(4, 0x80000000)
        put(16, 0x80000000 | w(12))
        self.pending.append(msg)

    def __call__(self, addr, size, value):
        if value is not None:
            self.writes.append(addr)
        if self.UART <= addr < self.UART + 0x100:
            off = addr - self.UART
            if value is None:
                if off == 0x18:
                    return 0x10 if not self.ctl.rx else 0
                if off == 0x00:
                    if not self.ctl.rx:
                        d.die("DR read with the RX FIFO empty")
                    return self.ctl.rx.pop(0)
                return self.u.get(off, 0)
            if off in (0x24, 0x28, 0x2C) and self.u[0x30] & 1:
                d.die("PL011 %#x written while UARTEN is set" % off)
            if off == 0x00:
                if not (self.u[0x30] & 0x301) == 0x301:
                    d.die("DR written with the PL011 not enabled for TX/RX")
                self.ctl.tx(value & 0xFF, self.host_baud(), self.flow_ok())
                return
            self.u[off] = value
            return
        if self.GPIO <= addr < self.GPIO + 0x100:
            off = addr - self.GPIO
            if value is None:
                return self.g.get(off, 0)
            self.g[off] = value
            return
        if addr in (self.MBX_READ, self.MBX_ST0, self.MBX_WRITE, self.MBX_ST1):
            if value is None:
                if addr == self.MBX_ST1:
                    return 0
                if addr == self.MBX_ST0:
                    return 0 if self.pending else 0x40000000
                return self.pending.pop(0)
            if addr == self.MBX_WRITE:
                self.mailbox(value)
                return
        d.die("unmodelled Pi 4 access at $%X" % addr)


class Pi5:
    """16550 uarta + BCM2712 pinctrl + gio (BT_REG_ON)."""
    UART, PINCTRL, GIO = 0x107D50C000, 0x107D504100, 0x107D508500

    def __init__(self, cpu, stepping, ctl):
        self.cpu, self.ctl, self.step = cpu, ctl, stepping
        self.u = {0x0C: 0, 0x10: 0, 0x04: 0}
        self.dll = self.dlm = 0
        self.p = {}
        self.gio = {}
        self.writes = []

    def field(self, off, shift, mask):
        return (self.p.get(off, 0) >> shift) & mask

    def pins_ok(self):
        if self.step == "C0":
            want = [(0x0C, 0, 3), (0x0C, 4, 4), (0x0C, 8, 4), (0x0C, 12, 4)]
        else:
            want = [(0x08, 0, 4), (0x08, 4, 4), (0x08, 8, 4), (0x08, 12, 4)]
        return all(self.field(o, s, 0xF) == v for o, s, v in want)

    def power(self):
        return bool((self.gio.get(4, 0) >> 29) & 1) and not ((self.gio.get(8, 0xFFFFFFFF) >> 29) & 1)

    def host_baud(self):
        dl = self.dll | (self.dlm << 8)
        return 0 if dl == 0 else 96_000_000 // (16 * dl)

    def __call__(self, addr, size, value):
        if value is not None:
            self.writes.append(addr)
        if self.UART <= addr < self.UART + 0x20:
            off = addr - self.UART
            dlab = self.u[0x0C] & 0x80
            if value is None:
                if off == 0x14:
                    return 0x20 | (1 if self.ctl.rx else 0)
                if off == 0x00 and not dlab:
                    if not self.ctl.rx:
                        d.die("RBR read with nothing received")
                    return self.ctl.rx.pop(0)
                return self.u.get(off, 0)
            if off == 0x00 and dlab:
                self.dll = value & 0xFF
            elif off == 0x04 and dlab:
                self.dlm = value & 0xFF
            elif off == 0x00:
                self.ctl.powered = self.power()
                flow = (self.u[0x10] & 0x22) == 0x22 and self.pins_ok()
                self.ctl.tx(value & 0xFF, self.host_baud(), flow)
            else:
                self.u[off] = value
            return
        if self.PINCTRL <= addr < self.PINCTRL + 0x40:
            off = addr - self.PINCTRL
            if value is None:
                return self.p.get(off, 0)
            self.p[off] = value
            return
        if self.GIO <= addr < self.GIO + 0x20:
            off = addr - self.GIO
            if value is None:
                return self.gio.get(off, 0xFFFFFFFF if off == 8 else 0)
            self.gio[off] = value
            return
        d.die("unmodelled Pi 5 access at $%X" % addr)


def driver(pi4, override):
    head = "; hci_bt_check driver - generated\n"
    if pi4:
        # The `bt` command runs on the monitor's own line parser: its
        # procedures are extracted by name from parse.pbi, and the console
        # is captured (the approach spi_dw_check.py takes).
        import spi_dw_check as sp
        stub = sp.driver(override, 1)
        head += stub[stub.index("#LINE_MAX"):stub.index("#CAP_SPI")]
        head += stub[stub.index("Global Dim gLine"):stub.index("XIncludeFile")]
    head += "".join('XIncludeFile "%s"\n' % i for i in (INC4 if pi4 else INC5))
    if pi4:
        head += """Procedure GateRun(*s)
  Define i.i
  i = 0
  While PeekA(*s + i) <> 0 And i < #LINE_MAX
    gLine[i] = PeekA(*s + i)
    i = i + 1
  Wend
  gLine[i] = 0
  gLineLen = i
  gate_n = 0
  gPos = 0
  SkipSpace()
  SkipWord()
  CmdBt()
EndProcedure
Procedure.i GateOut()
  ProcedureReturn @gate_out[0]
EndProcedure
Procedure.i GateOutLen()
  ProcedureReturn gate_n
EndProcedure
"""
    return head + """Procedure.i GateUp(*hcd, n.i, baud.i)
  ProcedureReturn HciBringUp(*hcd, n, baud)
EndProcedure
Global gate_never2.i
If gate_never2 = 1
  GateUp(0, 0, 0) : HciInquiry(0) : HciError() : HciWhy() : HciBdAddrIsPlaceholder() : HciBdAddrByte(0)
  HciDeviceCount() : HciDeviceAddrByte(0, 0) : HciDeviceClass(0) : HciDeviceRssi(0) : HciSetBaud(0)
  HciBaud() : HciPatched() : HciManufacturer() : HciLmpSubver() : HciHciVer() : HciResultsSeen()
""" + ("  MailboxInit() : GateRun(0) : GateOut() : GateOutLen()\n" if pi4 else "  Bt7SetPinctrl(0)\n") + "EndIf\n"


def gate(cc, override, workdir):
    checks = [0]

    def check(ok, what):
        if not ok:
            d.die(what)
        checks[0] += 1

    img4, p4 = d.build(cc, driver(True, override), "bt4", workdir / "p4", override, INC4, target="pi4")
    img5, p5 = d.build(cc, driver(False, override), "bt5", workdir / "p5", override, INC5, target="pi5")

    def pi4_machine(console, hwerr=False):
        box = {}
        m = d.Machine(img4, p4, lambda a, s, v: box["m"](a, s, v),
                      windows=[(0xFE000000, 0xFF000000)], ticks_per_step=TPS)
        ctl = Controller(m.cpu, hwerr)
        box["m"] = Pi4(m.cpu, console, ctl)
        call = lambda n, *a: m.signed(m.call(n, *a, limit=40_000_000))
        return m, box["m"], ctl, call

    def pi5_machine(stepping):
        box = {}
        m = d.Machine(img5, p5, lambda a, s, v: box["m"](a, s, v), ticks_per_step=TPS)
        ctl = Controller(m.cpu)
        box["m"] = Pi5(m.cpu, stepping, ctl)
        call = lambda n, *a: m.signed(m.call(n, *a, limit=40_000_000))
        return m, box["m"], ctl, call

    def common(m, ctl, call, tag, patch):
        if patch:
            check(ctl.patch == HCD, "%s: the controller received a patch that differs from the .hcd" % tag)
            check(ctl.cmds[0] == OP_RESET, "%s: the first command was not HCI_Reset" % tag)
            check(OP_BAUD in ctl.cmds and ctl.cmds.index(OP_BAUD) > ctl.cmds.index(OP_LAUNCH),
                  "%s: the baud switch did not follow the patch" % tag)
            check(ctl.baud == 3_000_000 and call("HciBaud") == 3_000_000, "%s: not at 3 Mbaud after the switch" % tag)
            check(call("HciBdAddrIsPlaceholder") == 0 and
                  [call("HciBdAddrByte", i) for i in range(6)] == [0x11, 0x22, 0x33, 0x44, 0x55, 0x66],
                  "%s: the address after the patch is not 11:22:33:44:55:66" % tag)
        else:
            check(call("HciBdAddrIsPlaceholder") == 1, "%s: the unpatched placeholder address was not recognised" % tag)
            check(OP_BAUD not in ctl.cmds and call("HciBaud") == 115200, "%s: the rate changed without a patch" % tag)
            check(call("HciSetBaud", 3_000_000) == 0 and call("HciError") == 8 and OP_BAUD not in ctl.cmds,
                  "%s: a baud switch without a patch was not refused (NEEDS_PATCH)" % tag)
        check(call("HciManufacturer") == 15 and call("HciLmpSubver") == 0x6119 and call("HciHciVer") == 9,
              "%s: Read_Local_Version fields misread" % tag)
        n = call("HciInquiry", 4)
        check(n == 3, "%s: inquiry found %d devices, want 3 (one heard twice)" % (tag, n))
        want = [DEVS[0], DEVS[1], EXT_DEV]
        for i, (a, c, r) in enumerate(want):
            got = bytes(call("HciDeviceAddrByte", i, k) for k in range(6))
            check(got == a[::-1], "%s: device %d address %s, want %s" % (tag, i, got.hex(), a[::-1].hex()))
            check(call("HciDeviceClass", i) == c, "%s: device %d class %#x, want %#x" % (tag, i, call("HciDeviceClass", i), c))
        check(call("HciDeviceRssi", 0) == -70 and call("HciDeviceRssi", 1) == 127 and call("HciDeviceRssi", 2) == -61,
              "%s: RSSI values misread" % tag)
        check(call("HciResultsSeen") == 4, "%s: %d inquiry results parsed, want 4" % (tag, call("HciResultsSeen")))

    # ---- Pi 4: the console owns the PL011 -> refused, nothing written ----
    m, hw, ctl, call = pi4_machine(console=True)
    check(call("MailboxInit") == 1, "MailboxInit")
    hw.writes.clear()
    check(call("GateUp", 0, 0, 115200) == 0 and call("HciError") == 1, "Pi 4: a console-owned PL011 was not refused")
    check("console" in m.cstr(call("HciWhy")), "Pi 4: the refusal does not name the console")
    check(not hw.writes and not ctl.powered, "Pi 4: the refusal wrote %d registers" % len(hw.writes))

    # ---- Pi 4: patched bring-up at 3 Mbaud, inquiry ---------------------
    m, hw, ctl, call = pi4_machine(console=False)
    call("MailboxInit")
    m.poke(HCD_AT, HCD)
    check(call("GateUp", HCD_AT, len(HCD), 3_000_000) == 1, "Pi 4: bring-up failed: %s" % m.cstr(call("HciWhy")))
    check((hw.u[0x24], hw.u[0x28]) == (1, 0), "Pi 4: IBRD/FBRD %r at 3 Mbaud, want (1, 0)" % ((hw.u[0x24], hw.u[0x28]),))
    check(hw.u[0x30] & 0xC301 == 0xC301 and hw.u[0x2C] == 0x70, "Pi 4: CR/LCRH not 8N1 + FIFO + RTS/CTS")
    check([hw.fsel(p) for p in (30, 31, 32, 33)] == [7, 7, 7, 7], "Pi 4: GPIO 30-33 not on ALT3")
    check([hw.pull(p) for p in (30, 31, 32, 33)] == [1, 0, 0, 1],
          "Pi 4: pulls %r, want CTS up, RTS none, TXD none, RXD up" % [hw.pull(p) for p in (30, 31, 32, 33)])
    check(hw.fsel(14) == 2 and hw.fsel(15) == 2, "Pi 4: the console pins were disturbed")
    common(m, ctl, call, "Pi 4", True)

    # ---- Pi 4: no patch ------------------------------------------------------
    m, hw, ctl, call = pi4_machine(console=False)
    call("MailboxInit")
    check(call("GateUp", 0, 0, 3_000_000) == 1, "Pi 4 unpatched: bring-up failed")
    common(m, ctl, call, "Pi 4 unpatched", False)

    # ---- corrupted patch, and a hardware error ------------------------------
    m, hw, ctl, call = pi4_machine(console=False)
    call("MailboxInit")
    m.poke(HCD_AT, HCD[:-2])
    check(call("GateUp", HCD_AT, len(HCD) - 2, 3_000_000) == 0 and call("HciError") == 7,
          "Pi 4: a truncated .hcd was not refused as corrupted")
    m, hw, ctl, call = pi4_machine(console=False, hwerr=True)
    call("MailboxInit")
    check(call("GateUp", 0, 0, 115200) == 0 and call("HciError") == 6, "Pi 4: HCI_Hardware_Error not reported")

    # ---- Pi 4: the `bt` command ---------------------------------------------
    m, hw, ctl, call = pi4_machine(console=False)
    call("MailboxInit")

    def run(line):
        m.poke(0x2A00000, line.encode() + b"\0")
        m.call("GateRun", 0x2A00000, limit=40_000_000)
        return m.peek(m.call("GateOut"), m.call("GateOutLen")).decode("latin-1")
    m.poke(HCD_AT, HCD)
    o = run("bt up %x %x" % (HCD_AT, len(HCD)))
    check("Bluetooth up at 3000000 baud" in o and "11:22:33:44:55:66" in o and "placeholder" not in o,
          "bt up: %r" % o[:300])
    o = run("bt scan 4")
    check("3 device(s) heard" in o and "06:05:04:03:02:01" in o and "A6:A5:A4:A3:A2:A1" in o and "-61 dBm" in o
          and "class 0x5A020C" in o, "bt scan: %r" % o[:400])
    o = run("bt scan 99")
    check("1 to 48" in o, "bt scan 99 not refused: %r" % o)
    m, hw, ctl, call = pi4_machine(console=False)
    call("MailboxInit")
    o = run("bt up")
    check("placeholder" in o and "43:45:C0:00:1F:AC" in o, "bt up without a patch: %r" % o[:300])

    # ---- Pi 5, both steppings -------------------------------------------------
    for step, kind in (("C0", 1), ("D0", 2)):
        m, hw, ctl, call = pi5_machine(step)
        check(call("Bt7SetPinctrl", kind) == 1, "Pi 5 %s: stepping refused" % step)
        m.poke(HCD_AT, HCD)
        check(call("GateUp", HCD_AT, len(HCD), 3_000_000) == 1, "Pi 5 %s: bring-up failed: %s" % (step, m.cstr(call("HciWhy"))))
        check(hw.dll == 2 and hw.dlm == 0, "Pi 5 %s: divisor %d at 3 Mbaud, want 2" % (step, hw.dll))
        if step == "C0":
            pads = [hw.field(0x24, s, 3) for s in (2, 4, 6, 8)]
            gpio29 = hw.field(0x0C, 20, 0xF)
        else:
            pads = [hw.field(0x14, s, 3) for s in (12, 14, 16, 18)]
            gpio29 = hw.field(0x08, 20, 0xF)
        check(pads == [0, 2, 0, 2], "Pi 5 %s: pads %r, want RTS none, CTS up, TXD none, RXD up" % (step, pads))
        check(gpio29 == 0 and hw.power(), "Pi 5 %s: GPIO 29 is not a driven-high gpio (BT_REG_ON)" % step)
        common(m, ctl, call, "Pi 5 " + step, True)
    m, hw, ctl, call = pi5_machine("C0")
    check(call("GateUp", 0, 0, 115200) == 0 and "stepping" in m.cstr(call("HciWhy")) and not hw.writes,
          "Pi 5: an unknown stepping was not refused before any write")
    return checks[0]


MUTATIONS = [
    (REL_HCI, "the first HCI_Reset skipped",
     "  If HciReset() = 0 : ProcedureReturn 0 : EndIf\n  If HciReadLocalVersion() = 0 : ProcedureReturn 0 : EndIf\n  ProcedureReturn 1\nEndProcedure\n\nProcedure HciClose()",
     "  If HciReadLocalVersion() = 0 : ProcedureReturn 0 : EndIf\n  ProcedureReturn 1\nEndProcedure\n\nProcedure HciClose()"),
    (REL_HCI, "opcode sent high byte first",
     "HwBtPut(op & $FF) = 0 Or HwBtPut((op >> 8) & $FF) = 0", "HwBtPut((op >> 8) & $FF) = 0 Or HwBtPut(op & $FF) = 0"),
    (REL_BT4, "RTS flow-control pin not muxed", "  PinAlt(#BTU_PIN_RTS, #BTU_ALT)\n", "\n"),
    (REL_BT4, "Pi 5 base on the Pi 4 build", "#BTU_BASE  = $FE201000", "#BTU_BASE  = $107D50C000"),
    (REL_BT4, "CTSEN/RTSEN left off", "#BTU_CR_RUN  = $C301", "#BTU_CR_RUN  = $0301"),
    (REL_BT4, "console routing check removed",
     "  If PinModeGet(14) = #PIN_ALT0 Or PinModeGet(15) = #PIN_ALT0", "  If 1 = 0"),
    (REL_HCI, "baud switch before the patch",
     "  If hci_patched = 0 : hci_err = #HCI_ERR_NEEDS_PATCH : ProcedureReturn 0 : EndIf\n", "\n"),
    (REL_HCI, "no 250 ms after Launch_RAM", "  HciDelayMs(250)\n", "\n"),
    (REL_HCI, "no 50 ms after Download_Minidriver", "  HciDelayMs(50)\n", "\n"),
    (REL_HCI, "inquiry result read device by device",
     "          codOff = 1 + num * 6 + num + num * 2\n", "          codOff = 1 + 6 + 1 + 2\n"),
    (REL_BT5, "Pi 5 D0 uart0 function wrong", "    Bt7Field(#BT7_PINCTRL, $08, 0, $F, 4)\n", "    Bt7Field(#BT7_PINCTRL, $08, 0, $F, 3)\n"),
    (REL_BT5, "Pi 5 auto flow control off", "#BT7_MCR_AFE  = $22", "#BT7_MCR_AFE  = $02"),
    (REL_BT5, "Pi 5 BT_REG_ON on gio 28", "#BT7_BT_ON_BIT = 29", "#BT7_BT_ON_BIT = 28"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--mutate", action="store_true")
    a = ap.parse_args()
    cc = d.compiler(a.compiler)
    top = pathlib.Path(tempfile.mkdtemp(prefix="hci-bt-"))
    try:
        try:
            n = gate(cc, {}, top / "gate")
        except d.GateFail as exc:
            print("hci_bt_check: FAIL - %s" % exc)
            return 1
        print("hci_bt_check: PASS - %d checks (Pi 4 PL011, Pi 5 uarta C0 and D0)" % n)
        if a.mutate:
            if d.run_mutations("hci_bt_check", MUTATIONS, lambda ov, wd: gate(cc, ov, wd), top / "mut"):
                return 1
        return 0
    finally:
        shutil.rmtree(top, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

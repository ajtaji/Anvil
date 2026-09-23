#!/usr/bin/env python3
"""Executable gate for RaspberryPi4/Lib/xhci.pi4 - the VL805 xHCI driver.

There is no USB stack on this board and no access to the hardware, so the
CONTROLLER is fabricated here: a model of an xHCI host controller with real
capability registers, a USBSTS whose Controller Not Ready bit clears only
after several reads, a self-clearing HCRST, a command ring that consumes
TRBs and posts completion events, root ports that answer a reset, and a
device that answers GET_DESCRIPTOR.  The real driver is compiled and
executed against it on the project's A64 oracle (tools/a64/a64_interp).

Nothing here touches hardware, a PCIe link, or a USB device.

What this proves:
  * the ORDER of the reset sequence - in particular that no operational
    register is written while Controller Not Ready is set, which is the
    one xhci.c calls out by name and the one a driver silently gets wrong
  * that every structure handed to the controller is 64-byte aligned
  * that the DCBAA, the ERST, the event ring segment, the input context
    and the output device context each stay inside one PAGESIZE page -
    the BOUNDARY column of xHCI 1.2 Table 6-1, not only its alignment
  * that the cycle bits on the command ring and the event ring agree
  * that a Link TRB is built and toggled correctly
  * the exact TRB layout of a control transfer
  * THAT A STALL IS RECOVERED AND NOT MERELY REPORTED.  The modelled
    device stalls a descriptor it does not have; the model then does
    what xHCI 1.1 section 4.8.3 says a controller does - it HALTS the
    endpoint and runs nothing more on it - and refuses any doorbell
    until a Reset Endpoint and a Set TR Dequeue Pointer have arrived,
    aimed at the right endpoint index and at a TRB the controller does
    not already own.  Until 2026-08-28 this model posted a Stall
    completion and forgot about it, so a driver that never cleared the
    halt looked exactly like one that did.  On silicon it does not: it
    is every later transfer on the device timing out, on every
    interface, because endpoint zero is shared.

What this does NOT prove: anything about silicon, the PCIe link, cache
maintenance (this interpreter has one flat coherent memory), or the
VL805's real register values.  It does not exercise the firmware
takeover path (XhciQuiesceAdopted) or the incoming Controller Not Ready
wait before the first halt (xh_WaitReady): the self-test stubs the PCIe
ownership seam as a cold controller nothing adopted, and the model
starts ready.  tools/xhci_initial_readiness_check.py and
tools/xhci_frozen_reset_check.py cover those.  In particular this
model's Reset Endpoint always works, so it cannot exercise xh_ClearHalt's final
read-back of the endpoint state - see the `no-unhalt-readback` entry
under HARMLESS.

Usage:
    python tools/a64/a64_xhci_check.py --compiler <PureMetalForge.exe>
        [--break <name>] [--no-breaks]

Run with --break <name> to injure the driver deliberately and watch the
gate go red.  See BREAKAGES below.  Every broken copy is generated at run
time into a temporary directory from the real xhci.pi4 by an anchored
substitution; nothing is written into the tree.
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

LOAD = 0x200000
SRC = ROOT / "RaspberryPi4" / "Examples" / "Diagnostics" / "pi4XhciSelfTest.pi4"
LIB = ROOT / "RaspberryPi4" / "Lib" / "xhci.pi4"

# ---------------------------------------------------------------------
# The two fabricated windows.  These match the constants in the test
# program, which in turn match pcie.pi4's real outbound window.
# ---------------------------------------------------------------------
CFG_BASE = 0x700000000
CFG_SIZE = 0x10000000   # room for 256 buses of the fake ECAM
CAP_BASE = 0x600000000          # BAR0 bus $F8000000 -> CPU $6_0000_0000
CAP_SIZE = 0x4000

# ---------------------------------------------------------------------
# What the fabricated controller reports.  Every field is packed the way
# xhci.h's macros unpack it, so a driver that unpacks it differently is
# caught here rather than on a bench.
# ---------------------------------------------------------------------
CAPLENGTH = 0x20
HCIVERSION = 0x0100             # xHCI 1.0
MAX_SLOTS = 32
MAX_INTRS = 1
MAX_PORTS = 5
ERST_MAX = 4
SCRATCHPADS = 4
CTX_SIZE = 32                   # HCCPARAMS1 bit 2 clear
DBOFF = 0x800
RTSOFF = 0x600

CAPBASE_VAL = (HCIVERSION << 16) | CAPLENGTH
HCS1 = MAX_SLOTS | (MAX_INTRS << 8) | (MAX_PORTS << 24)
# HCS_MAX_SCRATCHPAD(p) = ((p >> 16) & 0x3e0) | ((p >> 27) & 0x1f)
HCS2 = (ERST_MAX << 4) | ((SCRATCHPADS & 0x1F) << 27)
HCS3 = 0
# bit 0 AC64, bit 3 PPC (port power switches).  Bit 2 clear = 32-byte ctx.
HCC1 = 0x09

OP = CAPLENGTH
R_USBCMD = OP + 0x00
R_USBSTS = OP + 0x04
R_PAGESIZE = OP + 0x08

# The page size this modelled controller reports, and therefore the
# boundary half of xHCI 1.2 Table 6-1 for every structure whose column
# says PAGESIZE. 4096 is bit 0 of the PAGESIZE register, which is what
# the model answers and the only size the driver provides pages of.
PAGESIZE = 4096
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

SPEED_HS = 3
SPEED_SS = 4

# The device the model presents on port 2.  idProduct is $90A5 so that
# bytes 10 and 11 are both above 127 - the PeekA/PeekB question, made
# observable.
DEVICE_DESC = bytes([
    18,          # bLength
    1,           # bDescriptorType = DEVICE
    0x00, 0x02,  # bcdUSB 2.00
    0x00,        # bDeviceClass
    0x00,        # bDeviceSubClass
    0x00,        # bDeviceProtocol
    64,          # bMaxPacketSize0
    0x6B, 0x1D,  # idVendor  $1D6B
    0xA5, 0x90,  # idProduct $90A5
    0x10, 0x01,  # bcdDevice
    1, 2, 3,     # iManufacturer / iProduct / iSerialNumber
    1,           # bNumConfigurations
])

# A tick increment large enough that a millisecond-scale delay finishes
# in a few hundred interpreter steps.  The driver reads CNTFRQ_EL0 as
# 54 MHz (the Pi 4's generic timer) and computes its deadlines from it,
# so the RATIO is what matters, not the absolute value.
CNTFRQ = 54_000_000
TICK_STEP = 65536

# The correct driver finishes in about 260,000 interpreter steps.
# A broken one usually hangs on a timeout it will never satisfy,
# so the negative controls are given a budget a few times the
# healthy figure and a hang is reported as the failure it is.
BREAK_BUDGET = 3_000_000


class Ctl:
    """The fabricated xHCI host controller."""

    def __init__(self, cpu: A64) -> None:
        self.cpu = cpu
        self.violations: list[str] = []
        self.log: list[str] = []

        # Configuration space, one device at bus 1 / dev 0 / fn 0.
        self.cfg: dict[int, int] = {}
        self.cfg[0x00] = 0x34831106          # VIA Labs VL805
        self.cfg[0x04] = 0x00100000          # status only, no command bits
        # A 64-BIT memory BAR: bits 2:1 = 10b.  BAR1 is its high half.
        self.cfg[0x10] = 0xF8000004
        self.cfg[0x14] = 0x00000000

        self.reg: dict[int, int] = {
            R_USBCMD: 0,
            R_USBSTS: STS_HALT,
            R_PAGESIZE: 0x00000001,          # 4 KiB pages only
            R_DNCTRL: 0xFFFF,                # non-zero, so zeroing shows
            R_CONFIG: 0,
            R_ERSTSZ: 0xABCD0000,            # reserved top half, preserved
            R_IMAN: 0,
            R_IMOD: 0,
        }
        self.wide: dict[int, int] = {R_CRCR: 0, R_DCBAAP: 0,
                                     R_ERSTBA: 0, R_ERDP: 0}

        self.hcrst_reads = 0
        self.cnr_reads = 0
        self.halt_reads = 0
        self.reset_count = 0

        # Ports, 1-based.  Port 1 powered and empty; port 2 unpowered with
        # a high-speed device waiting behind the switch; port 4 a
        # SuperSpeed port that trained itself.
        self.port = {1: P_POWER, 2: 0, 3: P_POWER, 4: 0, 5: P_POWER}
        self.port[4] = P_POWER | P_CONNECT | P_PE | (SPEED_SS << 10)
        self.port_dev = {2: SPEED_HS}        # what appears once powered

        # Ring state.
        self.cmd_base = 0
        self.cmd_deq = 0
        self.cmd_ccs = 1
        self.ev_base = 0
        self.ev_size = 0
        self.ev_enq = 0
        self.ev_pcs = 1
        self.ep0_base = 0
        self.ep0_deq = 0
        self.ep0_ccs = 1

        self.next_slot = 1
        self.addressed: dict[int, dict] = {}
        # THE HALTED ENDPOINT, modelled.  xHCI 1.1 section 4.8.3: a Stall
        # moves an endpoint to the HALTED state, and the controller then
        # accepts its doorbell and runs NOTHING - no event is ever posted
        # and the driver times out.  Before 2026-08-28 this model posted
        # the Stall completion and forgot about it, so a driver that
        # never cleared the halt looked identical to one that did.  On
        # silicon it is not identical: it is one refused SET_IDLE
        # followed by every later transfer on the device timing out.
        # ep0_state is what the OUTPUT endpoint context reports -
        # 1 running, 2 halted, 3 stopped - because that is what the
        # driver reads back to decide whether the recovery worked.
        self.ep0_halted = False
        self.ep0_state = 0
        self.out_ctx: dict[int, int] = {}
        self.in_ctx_seen: dict = {}
        self.erst_entry: dict = {}
        self.ticks = 0

    # -- raw memory, bypassing the MMIO decode --------------------------
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

    # xHCI 1.2 Table 6-1 gives every interface data structure a BOUNDARY
    # it may not span as well as an alignment: no structure whose size is
    # at most 64 KB may span a 64 KB boundary, and none whose size is at
    # most PAGESIZE may span a PAGESIZE boundary.
    #
    # The driver honoured the alignment column and had no notion of this
    # one, and nothing here looked either - so a Device Context sitting
    # across a 4 KB boundary passed every assertion in this gate.
    def spans(self, what: str, addr: int, size: int, boundary: int) -> None:
        if not addr or boundary <= 0:
            return
        if addr // boundary != (addr + size - 1) // boundary:
            edge = ((addr // boundary) + 1) * boundary
            self.bad(
                f"{what} at ${addr:X}..${addr + size - 1:X} spans the "
                f"{boundary}-byte boundary at ${edge:X}, which xHCI 1.2 "
                f"Table 6-1 forbids")

    def cnr_set(self) -> bool:
        return bool(self.reg[R_USBSTS] & STS_CNR)

    # -- configuration space --------------------------------------------
    def cfg_read(self, off: int, bdf: int) -> int:
        if bdf != (1, 0, 0):
            return 0xFFFFFFFF
        return self.cfg.get(off, 0)

    # -- the register decode --------------------------------------------
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
                # Self-clears after a few reads, and CNR comes up with it.
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
                        self.log.append("halted")
            return self.reg[R_USBSTS]

        # 64-bit registers, read as two halves.
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

        # xhci.c: "xHCI cannot write to any doorbells or operational
        # registers other than status until the Controller Not Ready flag
        # is cleared."  This is the check the deliberate breakage trips.
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
                self.reset_count += 1
                self.log.append("hcrst")
                # A reset returns every operational register to its
                # default, which is what makes a driver that writes them
                # before the reset lose the writes.
                self.wide[R_CRCR] = 0
                self.wide[R_DCBAAP] = 0
                self.wide[R_ERSTBA] = 0
                self.wide[R_ERDP] = 0
                self.reg[R_CONFIG] = 0
                self.cmd_base = 0
                self.ev_base = 0
            elif (value & CMD_RUN) and not (old & CMD_RUN):
                self.halt_reads = 2
                self.log.append("run-requested")
            elif (old & CMD_RUN) and not (value & CMD_RUN):
                self.halt_reads = 2
                self.log.append("stop-requested")
            return

        if off == R_USBSTS:
            # Every writable bit here is write-1-to-clear.
            self.reg[R_USBSTS] &= ~(value & 0x1F1C)
            return

        for base in self.wide:
            if off == base:
                self.wide[base] = (self.wide[base] & ~0xFFFFFFFF) | value
                self._wide_written(base, half=0)
                return
            if off == base + 4:
                self.wide[base] = (self.wide[base] & 0xFFFFFFFF) | (value << 32)
                self._wide_written(base, half=1)
                return

        if R_PORTS <= off < R_PORTS + MAX_PORTS * 0x10:
            if (off - R_PORTS) % 0x10 == 0:
                self._port_write((off - R_PORTS) // 0x10 + 1, value)
            return

        self.reg[off] = value

    def _wide_written(self, base: int, half: int) -> None:
        if half == 0:
            # The low half alone is not yet a complete pointer; U-Boot
            # writes low then high, so the model acts on the high write.
            return
        v = self.wide[base]
        if base == R_DCBAAP:
            if v & 63:
                self.bad(f"DCBAAP is not 64-byte aligned (${v:X})")
            # (MaxSlots + 1) * 8 = #XHCI_DCBAA_BYTES in xhci.pi4.
            self.spans("the DCBAA", v, 2056, PAGESIZE)
            self.log.append("dcbaap")
        elif base == R_CRCR:
            ptr = v & ~0x3F
            if ptr and (ptr & 63):
                self.bad(f"command ring pointer is not 64-byte aligned (${ptr:X})")
            self.cmd_base = ptr
            self.cmd_deq = 0
            self.cmd_ccs = v & 1
            self.log.append("crcr")
        elif base == R_ERSTBA:
            ptr = v & ~0xF
            if ptr & 63:
                self.bad(f"ERST base is not 64-byte aligned (${ptr:X})")
            seg = self.rd(ptr, 8)
            size = self.rd(ptr + 8, 4)
            if seg & 63:
                self.bad(f"event ring segment is not 64-byte aligned (${seg:X})")
            self.spans("the ERST", ptr, 16, PAGESIZE)
            self.spans("the event ring segment", seg, size * 16, PAGESIZE)
            if size == 0 or size > 4096:
                self.bad(f"ERST segment size is implausible ({size})")
            if self.rd(ptr + 12, 4) != 0:
                self.bad("ERST entry's reserved word is not zero")
            self.erst_entry = {"ptr": ptr, "seg": seg, "size": size}
            self.ev_base = seg
            self.ev_size = size
            self.ev_enq = 0
            self.ev_pcs = 1
            self.log.append("erstba")
        elif base == R_ERDP:
            self.log.append("erdp")

    def _port_write(self, n: int, value: int) -> None:
        cur = self.port.get(n, 0)
        # Change bits are write-1-to-clear.
        cleared = value & 0x00FE0000
        cur &= ~cleared
        # Port power: a switch that actually switches.
        if (value & P_POWER) and not (cur & P_POWER):
            cur |= P_POWER
            if n in self.port_dev:
                cur |= P_CONNECT | P_CSC
            self.log.append(f"port{n}-powered")
        if not (value & P_POWER) and (cur & P_POWER):
            self.bad(f"port {n} was powered down by a read-modify-write")
        # Writing a 1 to Port Enabled DISABLES it.  Nothing in the driver
        # should ever do that.
        if value & P_PE:
            self.bad(f"port {n} was disabled by a write to Port Enabled")
        if value & P_RESET:
            if not (cur & P_CONNECT):
                self.bad(f"port {n} was reset with nothing connected")
            spd = self.port_dev.get(n, 0)
            cur |= P_PE | P_RC | P_PEC | (spd << 10)
            cur &= ~P_RESET
            self.log.append(f"port{n}-reset")
        self.port[n] = cur

    # -- rings -----------------------------------------------------------
    def post_event(self, f0: int, f1: int, f2: int, f3: int) -> None:
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
                self.bad(f"endpoint 0's doorbell was rung with {value}, not 1")
            self.run_ep0_ring(index)

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
            if ty == 6:                      # Link TRB
                seg = self.rd(at, 8)
                if seg != self.cmd_base:
                    self.bad("the command ring's Link TRB does not point "
                             "at its own segment")
                if not (ctl & 2):
                    self.bad("the command ring's Link TRB has no Toggle "
                             "Cycle bit - the ring would never wrap")
                self.cmd_deq = 0
                self.cmd_ccs ^= 1
                continue
            f0 = self.rd(at, 4)
            f1 = self.rd(at + 4, 4)
            self.handle_command(at, ty, f0 | (f1 << 32), (ctl >> 24) & 0xFF,
                                (ctl >> 16) & 0x1F)
            self.cmd_deq += 1
            if self.cmd_deq >= 64:
                self.bad("the command ring ran past its segment without a "
                         "Link TRB")
                return
        self.bad("the command ring did not terminate")

    def set_ep0_state(self, state: int) -> None:
        """Write the endpoint state the driver reads back.

        The low three bits of word 0 of endpoint 0's context in the
        OUTPUT device context - xhci.h's EP_STATE_MASK.  Writing it is
        the whole reason xh_ClearHalt's final check can mean anything:
        a model that only tracked the halt in Python would let a driver
        that reads the wrong context offset pass.
        """
        self.ep0_state = state
        for slot, out in self.out_ctx.items():
            at = out + CTX_SIZE                     # DCI 1 = endpoint 0
            self.wr(at, (self.rd(at, 4) & ~7) | state, 4)

    def handle_command(self, at: int, ty: int, param: int, slot: int,
                       ep: int = 0) -> None:
        comp = 1
        out_slot = 0
        if ty == 23:                         # No-op Command
            self.log.append("noop")
        elif ty == 9:                        # Enable Slot
            out_slot = self.next_slot
            self.next_slot += 1
            self.log.append(f"enable-slot={out_slot}")
        elif ty == 11:                       # Address Device
            out_slot = slot
            comp = self.address_device(slot, param)
        elif ty == 14:                       # Reset Endpoint
            out_slot = slot
            comp = self.reset_endpoint(slot, ep)
        elif ty == 16:                       # Set TR Dequeue Pointer
            out_slot = slot
            comp = self.set_tr_dequeue(slot, ep, param)
        else:
            self.bad(f"unexpected command TRB type {ty}")
            comp = 5                         # TRB Error
        self.post_event(at & 0xFFFFFFFF, (at >> 32) & 0xFFFFFFFF,
                        comp << 24,
                        (33 << 10) | (out_slot << 24))

    def reset_endpoint(self, slot: int, ep: int) -> int:
        """Reset Endpoint, TRB type 14.

        rpi-6.12.y_xhci.h:823 - EP_INDEX_FOR_TRB(p) is
        (((p) + 1) & 0x1f) << 16 with p the ep_index, so endpoint 0
        arrives here as 1.  Naming endpoint 0 as 0 is the mistake this
        check exists for: the command would succeed, aim at nothing, and
        the endpoint would stay halted while the driver believed it was
        recovered.

        xHCI 1.1 section 4.6.8: the command may only be issued to an
        endpoint in the Halted state, and answers Context State Error
        (19) otherwise.  The endpoint moves Halted -> Stopped.
        """
        if slot not in self.addressed:
            self.bad(f"Reset Endpoint for slot {slot}, never addressed")
            return 11                        # Slot Not Enabled
        if ep != 1:
            self.bad(f"Reset Endpoint named endpoint index {ep}, not 1 - "
                     f"endpoint 0 is DCI 1 and the TRB carries the DCI")
            return 17                        # Parameter Error
        if not self.ep0_halted:
            self.bad("Reset Endpoint on an endpoint that is not halted - "
                     "xHCI 1.1 section 4.6.8 answers Context State Error")
            return 19                        # Context State Error
        self.ep0_halted = False
        self.ep0_reset = True
        self.set_ep0_state(3)                # Stopped
        self.log.append("reset-ep")
        return 1

    def set_tr_dequeue(self, slot: int, ep: int, param: int) -> int:
        """Set TR Dequeue Pointer, TRB type 16.

        rpi-6.12.y_xhci_ring.c:758-763: the low half of the parameter is
        the address with the new CYCLE BIT in bit 0.

        THE POINTER MUST NOT LAND ON A TRB THE PRODUCER STILL OWNS.
        Aiming it at the base of the ring looks tidy and re-runs the
        transfer that just stalled, because the TRBs below the enqueue
        point still carry the producer's cycle.  The model refuses that
        rather than quietly replaying a dead Setup stage.
        """
        if slot not in self.addressed:
            self.bad(f"Set TR Dequeue for slot {slot}, never addressed")
            return 11
        if ep != 1:
            self.bad(f"Set TR Dequeue named endpoint index {ep}, not 1")
            return 17
        if not getattr(self, "ep0_reset", False):
            self.bad("Set TR Dequeue Pointer before Reset Endpoint - the "
                     "endpoint is still Halted and the command is refused")
            return 19
        addr = param & ~0xF
        cyc = param & 1
        if not self.ep0_base:
            self.bad("Set TR Dequeue with no EP0 ring")
            return 17
        if addr < self.ep0_base or addr >= self.ep0_base + 64 * 16:
            self.bad(f"Set TR Dequeue points at ${addr:X}, outside the "
                     f"EP0 ring")
            return 17
        idx = (addr - self.ep0_base) // 16
        owned = (self.rd(addr + 12, 4) & 1) == cyc
        if owned:
            self.bad("Set TR Dequeue points at a TRB the controller would "
                     "own - the stalled transfer descriptor would be run "
                     "again")
        self.ep0_deq = idx
        self.ep0_ccs = cyc
        self.ep0_reset = False
        self.set_ep0_state(1)                # Running
        self.log.append("set-deq")
        self.log.append(f"set-deq idx={idx} cyc={cyc}")
        return 1

    def address_device(self, slot: int, in_ctx: int) -> int:
        if in_ctx & 63:
            self.bad(f"the input context is not 64-byte aligned (${in_ctx:X})")
        self.spans("the input context", in_ctx, 2112, PAGESIZE)
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
        ep2 = self.rd(ectx + 4, 4)
        deq = self.rd(ectx + 8, 8)
        tx = self.rd(ectx + 16, 4)
        self.in_ctx_seen = {
            "speed": (info >> 20) & 0xF,
            "last_ctx": (info >> 27) & 0x1F,
            "route": info & 0xFFFFF,
            "port": (info2 >> 16) & 0xFF,
            "ep_type": (ep2 >> 3) & 7,
            "maxpacket": (ep2 >> 16) & 0xFFFF,
            "errcount": (ep2 >> 1) & 3,
            "deq": deq & ~1,
            "deq_cycle": deq & 1,
            "avg_trb": tx & 0xFFFF,
        }
        if self.in_ctx_seen["last_ctx"] != 1:
            self.bad("Address Device: LAST_CTX is not 1")
        if self.in_ctx_seen["ep_type"] != 4:
            self.bad("Address Device: endpoint 0 is not a control endpoint")
        if self.in_ctx_seen["deq"] & 63:
            self.bad("Address Device: the EP0 ring pointer is not aligned")

        dcbaap = self.wide[R_DCBAAP] & ~63
        if not dcbaap:
            self.bad("Address Device with no DCBAA")
            return 17                        # Parameter Error
        out_ctx = self.rd(dcbaap + slot * 8, 8)
        if not out_ctx:
            self.bad(f"DCBAA slot {slot} is empty at Address Device time")
            return 17
        if out_ctx & 63:
            self.bad("the output device context is not 64-byte aligned")
        self.spans("the output device context", out_ctx, 2048, PAGESIZE)
        # Slot State = Addressed (2), device address 1.
        self.wr(out_ctx + 12, (2 << 27) | 1, 4)
        self.ep0_base = self.in_ctx_seen["deq"]
        self.ep0_deq = 0
        self.ep0_ccs = self.in_ctx_seen["deq_cycle"]
        self.addressed[slot] = dict(self.in_ctx_seen)
        self.out_ctx[slot] = out_ctx
        self.ep0_halted = False
        self.ep0_reset = False
        self.set_ep0_state(1)                # Running
        self.log.append(f"address-device slot={slot}")
        return 1

    def poll_ep0_race(self) -> None:
        """A real controller reads its rings whenever it likes, not only
        when a doorbell is rung.  This is called every few instructions
        so that a driver which hands the head of a transfer descriptor
        to the controller before the tail exists is CAUGHT, rather than
        being invisible because this model is single-threaded.

        xhci-ring.c, giveback_first_trb(): "Don't give the first TRB to
        the hardware (by toggling the cycle bit) until we've finished
        creating all the other TRBs."
        """
        if not self.ep0_base or not self.addressed:
            return
        at = self.ep0_base + self.ep0_deq * 16
        head = self.rd(at + 12, 4)
        if (head & 1) != self.ep0_ccs:
            return                       # the head is still ours
        if ((head >> 10) & 0x3F) != 2:   # only a Setup Stage matters here
            return
        i = self.ep0_deq
        for _ in range(4):
            i = (i + 1) % 64
            c = self.rd(self.ep0_base + i * 16 + 12, 4)
            if (c & 1) != self.ep0_ccs:
                self.bad("the controller owned the Setup Stage TRB while "
                         "the rest of the transfer descriptor was still "
                         "being written")
                return
            if ((c >> 10) & 0x3F) == 4:
                return                   # a complete Setup/Data/Status TD

    def run_ep0_ring(self, slot: int) -> None:
        if slot not in self.addressed:
            self.bad(f"endpoint 0 doorbell for slot {slot}, which was never "
                     f"addressed")
            return
        # A HALTED ENDPOINT RUNS NOTHING.  On silicon the doorbell is
        # accepted, the ring is never walked and no event is ever posted,
        # so the driver spends its whole transfer timeout and reports
        # "no event arrived" - a timeout for a transfer that was never
        # attempted.  Measured 2026-08-28 on a wireless HID receiver
        # whose mouse interface stalled SET_IDLE: three consecutive
        # five-second timeouts, on both interfaces, out of a
        # sixteen-second watchdog budget.  Modelled as a refusal because
        # a driver that reaches here has already lost.
        if self.ep0_halted:
            self.bad("endpoint 0's doorbell was rung while the endpoint "
                     "was HALTED - the controller runs nothing and the "
                     "transfer times out; a Reset Endpoint and a Set TR "
                     "Dequeue Pointer were owed after the stall")
            return
        setup = None
        data = None
        last = None
        for _ in range(16):
            at = self.ep0_base + self.ep0_deq * 16
            ctl = self.rd(at + 12, 4)
            if (ctl & 1) != self.ep0_ccs:
                break
            ty = (ctl >> 10) & 0x3F
            f0 = self.rd(at, 4)
            f1 = self.rd(at + 4, 4)
            f2 = self.rd(at + 8, 4)
            if ty == 6:
                if not (ctl & 2):
                    self.bad("the EP0 ring's Link TRB has no Toggle Cycle bit")
                self.ep0_deq = 0
                self.ep0_ccs ^= 1
                continue
            if ty == 2:                      # Setup Stage
                if not (ctl & 0x40):
                    self.bad("the Setup Stage TRB does not set TRB_IDT")
                if (f2 & 0x1FFFF) != 8:
                    self.bad(f"the Setup Stage TRB length is {f2 & 0x1FFFF}, "
                             f"not 8")
                setup = {
                    "bmRequestType": f0 & 0xFF,
                    "bRequest": (f0 >> 8) & 0xFF,
                    "wValue": (f0 >> 16) & 0xFFFF,
                    "wIndex": f1 & 0xFFFF,
                    "wLength": (f1 >> 16) & 0xFFFF,
                    "txtype": (ctl >> 16) & 3,
                }
            elif ty == 3:                    # Data Stage
                data = {"buf": f0 | (f1 << 32), "len": f2 & 0x1FFFF,
                        "dir_in": bool(ctl & (1 << 16))}
            elif ty == 4:                    # Status Stage
                last = at
                if not (ctl & 0x20):
                    self.bad("the Status Stage TRB does not set TRB_IOC - "
                             "nothing would ever complete")
            else:
                self.bad(f"unexpected TRB type {ty} on the EP0 ring")
            self.ep0_deq += 1
            if last is not None:
                break
        if setup is None or last is None:
            self.bad("an EP0 doorbell produced no complete control transfer")
            return

        want = setup["wLength"]
        comp = 1
        moved = 0
        if (setup["bmRequestType"], setup["bRequest"]) == (0x80, 6):
            dtype = (setup["wValue"] >> 8) & 0xFF
            if dtype == 1:
                body = DEVICE_DESC[:want]
                if data is not None:
                    if not data["dir_in"]:
                        self.bad("an IN control transfer's Data Stage TRB "
                                 "has no TRB_DIR_IN")
                    if data["len"] != want:
                        self.bad("the Data Stage TRB length does not match "
                                 "wLength")
                    for i, b in enumerate(body):
                        self.cpu.memory[data["buf"] + i] = b
                moved = len(body)
                if moved < want:
                    comp = 13                # Short Packet
            else:
                comp = 6                     # Stall
        else:
            comp = 6
        resid = want - moved
        # xHCI 1.1 section 4.8.3 - a Stall halts the endpoint, and it
        # stays halted until Reset Endpoint runs.  Set this BEFORE the
        # event is posted, because the driver acts on the event.
        if comp == 6:
            self.ep0_halted = True
            self.set_ep0_state(2)            # Halted
            self.log.append("stall")
        # A shared event ring can still contain a completed transfer from a
        # different slot or endpoint.  Put one such event ahead of the real
        # completion so the control wait must prove TRB ownership rather than
        # accepting any transfer-shaped event.  Its residual is the whole
        # request, making the old unfiltered wait return a false zero-byte
        # success and leave the descriptor buffer unchanged.
        self.post_event(0xDEAD0000, 0x00000000,
                        (1 << 24) | (want & 0xFFFFFF),
                        (32 << 10) | (1 << 16) | (((slot + 1) & 0xFF) << 24))
        self.post_event(last & 0xFFFFFFFF, (last >> 32) & 0xFFFFFFFF,
                        (comp << 24) | (resid & 0xFFFFFF),
                        (32 << 10) | (1 << 16) | (slot << 24))
        self.log.append(f"xfer comp={comp} moved={moved}")


def install(cpu: A64, ctl: Ctl) -> None:
    """Hook MMIO and MRS into the interpreter without touching it."""
    # cpu.raw_load / cpu.raw_store are the OBSERVER forms: plain memory,
    # no MMIO decoding and no alignment rule. Binding A64.load here -
    # which is what this did until the rule moved into the interpreter -
    # would run the alignment check a second time on every DRAM access
    # that already passed it at the top of the closure below. Harmless,
    # but it puts the check somewhere a reader would not look for it.
    raw_load = cpu.raw_load
    raw_store = cpu.raw_store
    orig_step = A64.step.__get__(cpu, A64)

    def load(addr: int, size: int) -> int:
        # THE ALIGNMENT RULE. This closure replaces A64.load, so the
        # guard has to be CALLED here - see a64_interp.py's ALIGNMENT
        # RULE note. With the MMU off every data access is
        # Device-nGnRnE and an unaligned wide one is a silent runaway
        # on the part; without this line the gate models a machine
        # more permissive than the board it certifies.
        cpu.align_guard(addr, size, False)
        if CAP_BASE <= addr < CAP_BASE + CAP_SIZE:
            if size != 4:
                ctl.bad(f"a {size}-byte load from an xHCI register - every "
                        f"register access must be 32 bits")
                return 0
            if addr & 3:
                ctl.bad(f"an unaligned load from xHCI register "
                        f"${addr - CAP_BASE:X}")
            return ctl.reg_read(addr - CAP_BASE)
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

    poll_every = 64
    counter = [0]

    def step() -> None:
        counter[0] += 1
        if counter[0] % poll_every == 0:
            ctl.poll_ep0_race()
        # cpu.fetch, not the observer read: it goes through the closure
        # above (so MMIO decoding is unchanged) while telling the model
        # this is an instruction fetch, which with the MMU off is Normal
        # Non-Cacheable rather than Device and is not subject to the data
        # alignment rule.
        ins = cpu.fetch(cpu.pc)
        # MRS Xt, cntfrq_el0 / cntpct_el0.  The interpreter has no system
        # register file; the driver's whole timeout model rides on these
        # two, so they are supplied here rather than faulting.
        if (ins & 0xFFFFFFE0) == 0xD53BE000:      # cntfrq_el0
            cpu.put(ins & 31, CNTFRQ, 1)
            cpu.pc += 4
            return
        if (ins & 0xFFFFFFE0) == 0xD53BE020:      # cntpct_el0
            ctl.ticks += TICK_STEP
            cpu.put(ins & 31, ctl.ticks, 1)
            cpu.pc += 4
            return
        orig_step()

    cpu.load = load
    cpu.store = store
    cpu.step = step


# ---------------------------------------------------------------------
# The expected results, held here and nowhere else, so that a check the
# program stops making is a length mismatch rather than a silent pass.
# ---------------------------------------------------------------------
E_NONE = 0
E_NO_CONNECT = 20
E_PORTNUM = 19
E_STALL = 29
E_ARG = 30

EXPECT: list[tuple[str, int]] = []


def ex(label: str, want: int) -> None:
    EXPECT.append((label, want))


# 1. bring-up
ex("XhciInit succeeded", 1)
ex("no error recorded", E_NONE)
ex("the driver reports ready", 1)
# 2. capability registers
ex("CAPLENGTH", CAPLENGTH)
ex("HCIVERSION", HCIVERSION)
ex("MaxSlots from HCSPARAMS1 bits 7:0", MAX_SLOTS)
ex("MaxIntrs from HCSPARAMS1 bits 18:8", MAX_INTRS)
ex("MaxPorts from HCSPARAMS1 bits 31:24", MAX_PORTS)
ex("ERST Max from HCSPARAMS2 bits 7:4", ERST_MAX)
ex("scratchpads, both HCSPARAMS2 fields recombined", SCRATCHPADS)
ex("context size from HCCPARAMS1 bit 2", CTX_SIZE)
ex("AC64 from HCCPARAMS1 bit 0", 1)
ex("page size decoded from PAGESIZE", 4096)
ex("the device id, as read", 0x34831106)
# 3. derived blocks
ex("operational block is CAPLENGTH past the capability block", CAPLENGTH)
ex("doorbell block is DBOFF past it", DBOFF)
ex("runtime block is RTSOFF past it", RTSOFF)
# 4. alignment
ex("the arena base is 64-byte aligned", 0)
ex("the DCBAA is 64-byte aligned", 0)
ex("the command ring is 64-byte aligned", 0)
ex("the event ring is 64-byte aligned", 0)
ex("the ERST is 64-byte aligned", 0)
ex("the DCBAA is reachable by the controller", 1)
ex("the command ring is reachable", 1)
ex("the event ring is reachable", 1)
# 5. command and event rings
ex("a No-Op command completed", 1)
ex("its completion code is Success", 1)
ex("no unexpected events were skipped", 0)
ex("a second No-Op completed", 1)
ex("and it is Success too", 1)
ex("seventy more No-Ops, wrapping both rings", 70)
ex("the last one is Success", 1)
ex("nothing unexpected turned up on the way", 0)
# 6. ports
ex("the first connected port is 4", 4)
ex("port 1 has nothing connected", 0)
ex("port 4 has something connected", 1)
ex("port 4 is already enabled", 1)
ex("port 4 reports SuperSpeed", SPEED_SS)
ex("resetting an already-enabled port succeeds", 1)
ex("and leaves its speed alone", SPEED_SS)
ex("port 2 is not connected before it is powered", 0)
ex("port 2 has no speed before it is reset", 0)
ex("port 2 powers up, connects and resets", 1)
ex("port 2 is enabled afterwards", 1)
ex("port 2 reports high speed", SPEED_HS)
ex("resetting an empty port fails", 0)
ex("and says nothing is connected", E_NO_CONNECT)
ex("resetting port 9 of 5 fails", 0)
ex("and says the port number is out of range", E_PORTNUM)
# 7. a device slot
ex("Enable Slot returned slot 1", 1)
ex("Address Device succeeded", 1)
ex("the driver remembers the slot", 1)
ex("the max packet size for high speed is 64", 64)
ex("the controller assigned device address 1", 1)
ex("the slot state is Addressed", 2)
# 8. the device descriptor
ex("18 bytes of device descriptor", 18)
ex("the transfer completed with Success", 1)
ex("nothing was left untransferred", 0)
ex("idProduct low byte is $A5, not -91", 0xA5)
ex("idProduct high byte is $90, not -112", 0x90)
ex("bLength", 18)
ex("bDescriptorType is DEVICE", 1)
ex("bMaxPacketSize0", 64)
# 9. eight bytes, then a short read
ex("asking for 8 bytes returns 8", 8)
ex("eight for eight is a plain Success", 1)
ex("with nothing outstanding", 0)
ex("8 bytes copied out", 8)
ex("byte 7 is bMaxPacketSize0 again", 64)
ex("asking for 64 returns the descriptor's 18", 18)
ex("the completion code is Short Packet", 13)
ex("with 46 bytes outstanding", 46)
# 9b. wrap the transfer ring
ex("thirty more control transfers, wrapping the EP0 ring", 30)
ex("the last of them is Success", 1)
# 10. a stall
ex("a descriptor the device does not have fails", -1)
ex("the completion code is Stall", 6)
ex("and the driver names it a stall", E_STALL)
# 11. argument refusals
ex("a null destination is refused", -1)
ex("with the argument error", E_ARG)
ex("a length past the bounce buffer is refused", -1)
ex("with the argument error again", E_ARG)
# 12. the arena
ex("the arena did not overflow", None)     # patched below - a range test
ex("check count", None)

ARENA_INDEX = len(EXPECT) - 2
COUNT_INDEX = len(EXPECT) - 1
# The program records nres BEFORE appending this last check, so the
# expected value is the index of the check itself.
EXPECT[COUNT_INDEX] = ("check count", COUNT_INDEX)


# ---------------------------------------------------------------------
# The deliberate breakages.  Each is a text substitution into a COPY of
# xhci.pi4; the gate is worthless if it passes with the driver broken,
# so this is how that is demonstrated rather than asserted.
# ---------------------------------------------------------------------
BREAKAGES = {
    # Accepting any transfer event lets the fabricated foreign completion
    # above satisfy control transfers with a false zero-byte success.  The
    # fixed path matches the control descriptor's setup/data/status range.
    "control-accepts-foreign-event": (
        "  If xh_WaitEventFor(#XHCI_TRB_TRANSFER, startTrb, lastTrb, #XHCI_TMO_CTRL_MS) = 0",
        "  If xh_WaitEvent(#XHCI_TRB_TRANSFER, #XHCI_TMO_CTRL_MS) = 0"),
    # Skip the Controller Not Ready wait AFTER HCRST.  xhci.c says no
    # operational register may be written until CNR clears; the model
    # raises CNR when the reset self-clears and refuses a write under it.
    # RE-AIMED to xh_Reset's post-reset loop, which reads USBSTS into
    # `cmd` between xh_Trace markers (xhci.pi4, xh_Reset).  The old anchor
    # text now also names xh_WaitReady, the INCOMING readiness wait before
    # the first halt, which this model cannot fail on because its
    # controller starts ready - tools/xhci_initial_readiness_check.py is
    # the gate for that one.
    "no-cnr-wait": (
        "  cmd = xh_Rd(xh_op, #XHCI_USBSTS)\n"
        "  xh_Trace(12)\n"
        "  While (cmd & #XHCI_STS_CNR) <> 0\n"
        "    If xh_Expired(d) <> 0\n"
        "      xh_Trace(13)\n"
        "      XhciAccountWait(#XHCI_W_CNR, t0)\n"
        "      ProcedureReturn xh_Fail(#XHCI_ERR_CNR)\n"
        "    EndIf\n"
        "    cmd = xh_Rd(xh_op, #XHCI_USBSTS)\n"
        "  Wend\n",
        "  xh_Trace(12)\n"),
    # Misalign the DCBAA by allocating it on an 8-byte boundary.
    # RE-AIMED: xh_Alloc grew a third argument when it was taught Table
    # 6-1's boundary column, so the old anchor stopped matching. The
    # anchor check SAID SO rather than passing with one fewer control.
    "misaligned-dcbaa": (
        "  xh_dcbaa = xh_Alloc(#XHCI_DCBAA_BYTES, #XHCI_ALIGN, xh_pageSize)",
        "  xh_dcbaa = xh_Alloc(#XHCI_DCBAA_BYTES, 8, xh_pageSize) + 8"),
    # Table 6-1's BOUNDARY column, ignored - the defect the driver carried
    # until xh_Alloc took a boundary argument. A 2048-byte Device Context
    # on a 64-byte grid straddled the next PAGESIZE boundary from 31 of
    # every 64 placements, and WHICH structures straddled was decided by
    # how many bytes of globals were declared ahead of xh_arena.
    #
    # It FORCES the straddle. Simply passing 0 for the boundary restores
    # the old code exactly - and that control PASSED, because whether a
    # structure lands across a page edge depends on where the linker put
    # the arena. A negative control that fires only on an unlucky layout
    # is not a control. So this takes a page of slack and places the
    # context 64 bytes below a page boundary, which straddles from any
    # arena base.
    "devctx-spans-page": (
        "    xh_devCtx[d] = xh_Alloc(#XHCI_DEV_CTX_BYTES, #XHCI_ALIGN, xh_pageSize)",
        "    xh_devCtx[d] = xh_Alloc(#XHCI_DEV_CTX_BYTES + 4096, #XHCI_ALIGN, 0)\n"
        "    xh_devCtx[d] = ((xh_devCtx[d] / 4096) + 1) * 4096 - 64"),
    # Drop the Toggle Cycle bit from the command ring's Link TRB.
    "no-link-toggle": (
        "  PokeN(lnk + 12, ((#XHCI_TRB_LINK << 10) | #XHCI_LINK_TOGGLE) & $FFFFFFFF)",
        "  PokeN(lnk + 12, (#XHCI_TRB_LINK << 10) & $FFFFFFFF)"),
    # Never enable PCI bus mastering.  RE-AIMED: xh_Locate now sets
    # memory space only, and XhciInitAt asks pcie.pi4 for bus mastering
    # through xh_EnableDma() after CAPLENGTH is read and before the
    # halt/reset path (xhci.pi4, XhciInitAt).  Deleting that call is the
    # driver forgetting to ask.
    "no-bus-master": (
        "  If xh_EnableDma() = 0\n"
        "    xh_FailStop()\n"
        "    ProcedureReturn 0\n"
        "  EndIf\n"
        "  If xh_Halt() = 0\n",
        "  If xh_Halt() = 0\n"),
    # Write the wide registers high half first.  RE-AIMED: xh_Wr64 now
    # puts an ordering barrier between the halves (xhci.pi4, xh_Wr64).
    "wide-wrong-order": (
        "  PokeN(base + off,     v & $FFFFFFFF)\n"
        "  a64_barrier()\n"
        "  PokeN(base + off + 4, (v >> 32) & $FFFFFFFF)",
        "  PokeN(base + off + 4, (v >> 32) & $FFFFFFFF)\n"
        "  a64_barrier()\n"
        "  PokeN(base + off,     v & $FFFFFFFF)"),
    # Read a register with PeekI - eight bytes - instead of PeekN.
    # RE-AIMED: xh_Rd now loads into `v` and barriers before returning
    # (xhci.pi4, xh_Rd).
    "64-bit-register-read": (
        "  v = PeekN(base + off)\n  ; xhci_readl() is an ordered readl(), not a raw load.",
        "  v = PeekI(base + off)\n  ; xhci_readl() is an ordered readl(), not a raw load."),
    # Leave TRB_IOC off the Status Stage TRB.
    "no-ioc": (
        "  f3 = #XHCI_TRB_IOC | (#XHCI_TRB_STATUS << 10)",
        "  f3 = (#XHCI_TRB_STATUS << 10)"),
    # Hand the first control TRB to the controller immediately, instead
    # of writing it with the cycle bit inverted and correcting it once
    # the rest of the transfer descriptor exists.  poll_ep0_race() is
    # what sees this; a doorbell-driven model cannot.
    # RE-AIMED 2026-08-26: the endpoint-zero ring became one ring PER
    # SLOT, so the ring argument is xh_slot and not a constant. The gate
    # refused to run rather than quietly skip a mutation whose anchor had
    # moved, which is the only reason this was noticed.
    "no-deferred-cycle": (
        "xh_QueueTrbCy(xh_slot, sf0, sf1, 8, f3, startCycle ! 1)",
        "xh_QueueTrbCy(xh_slot, sf0, sf1, 8, f3, startCycle)"),
    # ---- the stall-recovery mutations, added 2026-08-28 ---------------
    # Report the stall and walk away, which is what the file did until
    # the day this was written.  The endpoint stays HALTED and every
    # later transfer on the device is doorbelled and never run.
    "no-clear-halt": (
        "  If xh_lastComp = #XHCI_COMP_STALL\n"
        "    If xh_ClearHalt(xh_slot, xh_slot, 1) = 0\n"
        "      ProcedureReturn -1      ; xh_err already names the recovery failure\n"
        "    EndIf\n"
        "    xh_Fail(#XHCI_ERR_STALL)\n",
        "  If xh_lastComp = #XHCI_COMP_STALL\n"
        "    xh_Fail(#XHCI_ERR_STALL)\n"),
    # Reset the endpoint and stop there.  The controller's dequeue
    # pointer is undefined after a Reset Endpoint, so the endpoint is
    # left running against a pointer into the middle of a dead transfer
    # descriptor.
    "no-set-deq": (
        "  If xh_CommandEp(#XHCI_TRB_SET_DEQ, deq & $FFFFFFFF, (deq >> 32) & $FFFFFFFF, slot, dci, #XHCI_TMO_EVENT_MS) = 0\n"
        "    ok = 0\n"
        "  EndIf\n",
        "\n"),
    # Point the dequeue pointer at the base of the ring instead of at
    # the enqueue position.  It LOOKS like "start again from the top"
    # and it is a replay of the transfer that just stalled: the TRBs
    # below the enqueue point still carry the producer's cycle bit.
    "deq-at-ring-base": (
        "  deq = xh_TrbAddr(ring, xh_ringEnq[ring]) | xh_ringCycle[ring]",
        "  deq = xh_ringBase[ring] | xh_ringCycle[ring]"),
    # Write the ep_index where the DCI belongs.  EP_INDEX_FOR_TRB adds
    # one - rpi-6.12.y_xhci.h:823 - so endpoint 0 must arrive as 1, and
    # a 0 here names no endpoint at all while both commands still report
    # Success.
    "ep-index-off-by-one": (
        "  f3 = (cmd << 10) | ((dci & $1F) << 16) | ((slot & $FF) << 24)",
        "  f3 = (cmd << 10) | (((dci - 1) & $1F) << 16) | ((slot & $FF) << 24)"),
    # Let the recovery's own command completions overwrite the transfer's.
    # XhciLastComp() then answers 1 - the Set TR Dequeue's Success - to a
    # caller asking why their transfer failed.
    "clobber-last-comp": (
        "  xh_haltComp  = xh_lastComp\n"
        "  xh_lastComp  = savedComp\n"
        "  xh_lastResid = savedResid\n"
        "  xh_lastSlot  = savedSlot\n"
        "  ProcedureReturn ok\n",
        "  xh_haltComp = xh_lastComp\n"
        "  ProcedureReturn ok\n"),
}

# ---------------------------------------------------------------------
# NOT breakages - mutations that were EXPECTED to fail and did not, kept
# here so the finding does not get lost.  Deleting them would leave the
# driver carrying a comment claiming a hazard that was measured not to
# exist, which is how a superstition becomes documentation.
#
# Each of these must STILL PASS.  If one of them ever starts failing,
# the reasoning below is wrong and the entry belongs in BREAKAGES.
# ---------------------------------------------------------------------
HARMLESS = {
    # Skip xh_RingRoom(), so a three-TRB control transfer can straddle
    # the Link TRB.  Expected to corrupt the transfer; measured over
    # thirty transfers and two full laps of the ring, it does not.  The
    # Link TRB is handed over carrying the old cycle and carries the
    # consumer's cycle state across with it.  U-Boot allows the same
    # straddle - xhci-ring.c, inc_enq(), when more_trbs_coming is set.
    "no-ring-room": (
        "  xh_RingRoom(xh_slot, 3)",
        "  "),
    # Delete xh_ClearHalt's final read-back of the endpoint state.
    # Expected to go red and does not, and the reason is a limit of the
    # MODEL rather than a statement about the driver: this controller is
    # written to be correct, so its Reset Endpoint and Set TR Dequeue
    # Pointer either succeed and unhalt the endpoint or fail with a
    # completion code that xh_CommandEp already refuses.  There is no
    # modelled path where both commands answer Success and the endpoint
    # is still halted.
    #
    # THE CHECK STAYS ANYWAY, and this entry exists so nobody deletes it
    # on the strength of a green gate.  "The command was accepted" and
    # "the command took effect" came apart on this exact silicon during
    # the Evaluate Context work, which is why XhciCtxEntries() and
    # XhciEpState() exist at all, and a Reset Endpoint aimed at the
    # wrong endpoint index is precisely a command a real controller can
    # accept and act on somewhere else.  The failure it guards against
    # is invisible until the next transfer times out - which is the bug
    # the whole of xh_ClearHalt was written to end.
    "no-unhalt-readback": (
        "    st = xh_EpStateAt(slot, dci)\n"
        "    If st = #XHCI_EP_STATE_HALTED Or st < 0\n"
        "      xh_Fail(#XHCI_ERR_UNHALT)\n"
        "      ok = 0\n"
        "    EndIf\n",
        "\n"),
}


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
    args = ap.parse_args(argv[1:])
    if not args.compiler:
        ap.error("No compiler was given. Pass --compiler <path to "
                 "PureMetalForge.exe> or set the PMF_COMPILER environment "
                 "variable.")
    return args


def execute(img: pathlib.Path, sym: dict[str, int],
            budget: int = 120_000_000) -> tuple[Ctl, A64, int, bool]:
    blob = img.read_bytes()
    cpu = A64(pc=LOAD)
    for i, b in enumerate(blob):
        cpu.memory[LOAD + i] = b
    # Names for the alignment rule's message. "alignment fault at
    # $00484EDA" sends someone hunting; "cyw43seteventmask+332,
    # cyw43.pi4 line 4762" ends the search. Read from the `.dbg` pmfc
    # already writes - NOT the `.sym`, which mixes absolute BSS
    # addresses with load-relative code ones (A64Assembler.pbi:1994-1997)
    # and whose wrong half reads as a column of zeroes rather than an
    # error. A missing `.dbg` costs the name, not the check.
    attach_symbols(cpu, img, LOAD)
    ctl = Ctl(cpu)
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
    got = [cpu.load(base + i * 8, 8) for i in range(min(nres, 128))]
    return [v - (1 << 64) if v >= (1 << 63) else v for v in got]


def compare(got: list[int], ctl: Ctl) -> list[str]:
    fails: list[str] = []
    if len(got) != len(EXPECT):
        fails.append(f"check count: program made {len(got)}, harness "
                     f"expects {len(EXPECT)}")
    for i, (label, want) in enumerate(EXPECT):
        if i >= len(got):
            fails.append(f"#{i} {label}: never ran")
            continue
        if i == ARENA_INDEX:
            # A range test, not an equality: the arena must have been used
            # and must not have been exhausted.
            if not (0 < got[i] <= 76032):
                fails.append(f"#{i} {label}: used {got[i]} bytes of 76032")
            continue
        if got[i] != want:
            fails.append(f"#{i} {label}: got {got[i]}, want {want}")

    # ---- what the controller saw, checked from outside the program ----
    def want(name: str, gotv, wantv) -> None:
        if gotv != wantv:
            fails.append(f"model: {name}: got {gotv!r}, want {wantv!r}")

    want("PCI bus mastering was enabled", ctl.cfg[0x04] & 0x04, 0x04)
    want("PCI memory space was enabled", ctl.cfg[0x04] & 0x02, 0x02)
    want("CONFIG holds the slot count", ctl.reg[R_CONFIG] & 0xFF, MAX_SLOTS)
    want("DNCTRL was zeroed", ctl.reg[R_DNCTRL], 0)
    want("ERSTSZ names one segment", ctl.reg[R_ERSTSZ] & 0xFFFF, 1)
    want("ERSTSZ's reserved half was preserved",
         ctl.reg[R_ERSTSZ] >> 16, 0xABCD)
    want("the command ring's cycle state went into CRCR",
         ctl.wide[R_CRCR] & 1, 1)
    want("the ERST names the event ring",
         ctl.erst_entry.get("seg"), ctl.ev_base)
    want("the ERST segment is 64 TRBs", ctl.erst_entry.get("size"), 64)
    want("interrupt moderation was zeroed", ctl.reg[R_IMOD], 0)
    want("the controller was reset exactly once", ctl.reset_count, 1)
    want("the controller is running",
         ctl.reg[R_USBSTS] & STS_HALT, 0)
    want("Address Device asked for high speed",
         ctl.in_ctx_seen.get("speed"), SPEED_HS)
    want("Address Device named root port 2",
         ctl.in_ctx_seen.get("port"), 2)
    want("the route string is empty for a root-port device",
         ctl.in_ctx_seen.get("route"), 0)
    want("endpoint 0's max packet is 64",
         ctl.in_ctx_seen.get("maxpacket"), 64)
    want("endpoint 0's error count is 3",
         ctl.in_ctx_seen.get("errcount"), 3)
    want("endpoint 0's average TRB length is 8",
         ctl.in_ctx_seen.get("avg_trb"), 8)
    want("endpoint 0's dequeue pointer carries cycle 1",
         ctl.in_ctx_seen.get("deq_cycle"), 1)
    def before(a: str, b: str) -> bool:
        """Did a happen, and happen before b?  A missing entry is False,
        never an exception - a breakage that stops the driver reaching
        one of these must show up as a failed assertion, not a crash in
        the harness."""
        return a in ctl.log and b in ctl.log and ctl.log.index(a) < ctl.log.index(b)

    want("the reset happened before the DCBAA was programmed",
         before("hcrst", "dcbaap"), True)
    want("CNR cleared before the DCBAA was programmed",
         before("cnr-cleared", "dcbaap"), True)
    want("the command ring was programmed before it was rung",
         before("crcr", "noop"), True)
    want("the event ring was programmed before the first command",
         before("erstba", "noop"), True)
    want("the controller was running before the first command",
         before("running", "noop"), True)

    # ---- the stall was RECOVERED, not merely reported ------------------
    # The self-test asks for a descriptor the device does not have and
    # the model answers Stall, which halts endpoint 0.  Everything after
    # that point on this device - on ANY of its interfaces, because
    # endpoint zero belongs to the device - is dead until Reset Endpoint
    # and Set TR Dequeue Pointer have run.  There is no further transfer
    # in this program to notice that with, so the state is checked
    # directly: a driver that finishes a run having left an endpoint
    # halted has left the device unusable and does not know it.
    want("the stall halted endpoint 0 in the model", "stall" in ctl.log, True)
    want("a Reset Endpoint followed the stall",
         before("stall", "reset-ep"), True)
    want("a Set TR Dequeue Pointer followed the Reset Endpoint",
         before("reset-ep", "set-deq"), True)
    want("endpoint 0 is not left halted", ctl.ep0_halted, False)
    want("and the controller reports it running again", ctl.ep0_state, 1)

    for v in ctl.violations:
        fails.append(f"model refused: {v}")
    return fails


def once(compiler: str, src: pathlib.Path, img: pathlib.Path,
         budget: int = 120_000_000) -> tuple[list[str], int, int]:
    build(compiler, src, img)
    sym = load_syms(img)
    ctl, cpu, steps, finished = execute(img, sym, budget)
    got = collect(cpu, sym)
    fails = compare(got, ctl)
    if not finished:
        # A driver that hangs is a red gate, not a stuck harness.  The
        # deliberate breakages below are given a much smaller budget than
        # the real run precisely so that a hang costs seconds.
        fails.insert(0, f"the program did not reach its end trap within "
                        f"{budget} interpreter steps - the driver hung")
    return fails, steps, len(EXPECT)


def make_broken(name: str, work: pathlib.Path) -> pathlib.Path:
    """Write a broken copy of xhci.pi4, and a copy of the self-test that
    includes it by absolute path, into `work`.  The anchor must match
    exactly once: a moved anchor is a breakage that silently tests
    nothing, and a doubled one is a breakage aimed at two places."""
    old, new = BREAKAGES.get(name) or HARMLESS[name]
    text = LIB.read_text(encoding="utf-8")
    hits = text.count(old)
    if hits != 1:
        raise SystemExit(f"Breakage {name!r} matched its anchor {hits} times "
                         f"in xhci.pi4, not once. The breakage must be "
                         f"re-aimed at Anvil's current source, not skipped.")
    out_lib = work / "xhci_broken.pi4"
    out_lib.write_text(text.replace(old, new, 1), encoding="utf-8")
    include = '"RaspberryPi4/Lib/xhci.pi4"'
    prog = SRC.read_text(encoding="utf-8")
    if prog.count(include) != 1:
        raise SystemExit("The self-test no longer includes xhci.pi4 exactly "
                         "once, so a broken copy cannot be swapped in.")
    out_src = work / "xhci_broken_main.pi4"
    out_src.write_text(prog.replace(include, f'"{out_lib}"'),
                       encoding="utf-8")
    return out_src


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.only is not None and args.only not in BREAKAGES \
            and args.only not in HARMLESS:
        raise SystemExit(f"There is no breakage named {args.only!r}.")

    with tempfile.TemporaryDirectory(prefix="a64-xhci-") as tmp:
        work = pathlib.Path(tmp)
        broken_img = work / "xhci_broken.img"

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
                                   work / "xhciselftest.img")
        if fails:
            for f in fails:
                print("FAIL " + f)
            print(f"FAILED: {len(fails)} of {total} assertions, {steps} steps")
            return 1
        print(f"PASS: xhci.pi4 brought a modelled xHCI controller up and read "
              f"a device descriptor - {total} assertions, {steps} "
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
                # A breakage that will not even compile is still a red gate.
                print(f"  {name:22s} REFUSED AT COMPILE TIME")
                continue
            if bfails:
                print(f"  {name:22s} {len(bfails)} assertion(s) failed"
                      f"   e.g. {bfails[0][:96]}")
            else:
                print(f"  {name:22s} *** STILL PASSED - the gate does not "
                      f"cover this ***")
                bad.append(name)
        if bad:
            print(f"\nGATE IS WEAK: {len(bad)} breakage(s) went undetected: "
                  f"{', '.join(bad)}")
            return 1
        print(f"\nevery one of the {len(BREAKAGES)} deliberate breakages was "
              f"caught.")

        print("\nmutations MEASURED HARMLESS - each of these must still PASS:")
        wrong = []
        for name in HARMLESS:
            src = make_broken(name, work)
            hfails, _, _ = once(args.compiler, src, broken_img, BREAK_BUDGET)
            if hfails:
                print(f"  {name:22s} *** NOW FAILS - the reasoning in "
                      f"HARMLESS is wrong: {hfails[0][:80]} ***")
                wrong.append(name)
            else:
                print(f"  {name:22s} still passes, as recorded")
        if wrong:
            return 1
        print(f"\nPASS: {total} assertions; {len(BREAKAGES)} of "
              f"{len(BREAKAGES)} breakages rejected; {len(HARMLESS)} harmless "
              f"mutations still pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

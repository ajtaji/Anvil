#!/usr/bin/env python3
"""Desk gate: the Pi 5 header I2C - RaspberryPi4/Lib/i2c_dw.pi4 (RP1 I2C1,
a Synopsys DesignWare master) and the #PMF_CHIP = 2712 branch of
RaspberryPi4/Board/hw_i2c.pi4.

The -t pi5 compiled procedures run under tools/a64/a64_interp.py against a
model of the DesignWare block and a small I2C bus, written from the pinned
Linux sources (raspberrypi/linux 7e030b60792d), not from the library:

  include/linux/designware_i2c.h        register offsets and bits
  i2c-designware-core.h                 COMP_TYPE $44570140; TX_ABRT
                                        source bits 0..4 = no-acknowledge
  i2c-designware-master.c               DATA_CMD bit 8 = READ, bit 9 = STOP;
                                        clock_calc(); the "set STOP on the
                                        last byte always" rule, because an
                                        empty TX FIFO without it either ends
                                        the transfer (no IC_EMPTYFIFO_HOLD)
                                        or holds the bus forever (with it)
  i2c-designware-common.c               FIFO depths from COMP_PARAM_1
  rp1.dtsi + the Pi 5 DTB               i2c@74000 -> CPU $1F00074000;
                                        RP1_CLK_SYS 200 MHz; SCL rise 65 ns,
                                        fall 100 ns; i2c1 on GPIO 2/3 with
                                        pull-ups; pinctrl-rp1.c: FUNCSEL 3

WHAT THE MODEL ENFORCES, so a defect is an error it names:
  * TAR, CON and the SCL counts written while IC_ENABLE is set (the block
    ignores them) - refused;
  * DATA_CMD written while disabled, a TX FIFO pushed past its depth, READ
    commands outstanding past the RX depth (overrun), DATA_CMD read from an
    empty RX FIFO - refused;
  * the bus runs in model time: one byte takes BYTE_TICKS counter ticks, so
    a driver that lets the TX FIFO run dry mid-message is caught - under
    the NO-HOLD variant as a second START, under the HOLD variant as a
    transfer that never finishes. Both variants are run, and a third -
    HOLD with a bus faster than the CPU - catches a driver that queues
    more READs than the RX FIFO can hold (master.c's rx_outstanding).

The HW-level result codes (#HW_I2C_*) are read from Anvil/Hal/hal.pbi.
Desk proof only; silicon owed.

  py -3 -B tools/a64/i2c_dw_check.py --compiler <PureMetalForge.exe> [--mutate]
"""
from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import pi5_desk as d                               # noqa: E402
from gpio_rp1_check import Rp1Gpio, IO_BANK0, PADS_BANK0, SYS_RIO0   # noqa: E402

DW = 0x1F_0007_4000
COMP_TYPE = 0x44570140
TX_DEPTH, RX_DEPTH = 16, 4              # small, and unequal, on purpose
PARAM_1 = ((TX_DEPTH - 1) << 16) | ((RX_DEPTH - 1) << 8)
BYTE_TICKS = 2000                       # model time per byte on the wire
FAST_TICKS = 1                          # a bus that outruns the CPU
CLK_KHZ = 200_000
RISE_NS, FALL_NS = 65, 100
BUF = 0x2800000                         # scratch RAM for the byte buffers

REL_LIB = "RaspberryPi4/Lib/i2c_dw.pi4"
REL_HW = "RaspberryPi4/Board/hw_i2c.pi4"
REL_GPIO = "RaspberryPi4/Lib/gpio_rp1.pi4"
REL_TIMER = "RaspberryPi4/Lib/timer.pi4"
REL_HAL = "Anvil/Hal/hal.pbi"
HAL_NAMES = ("#HW_I2C_OK", "#HW_I2C_NACK", "#HW_I2C_TIMEOUT", "#HW_I2C_ARG",
             "#HW_I2C_NOBUS", "#HW_I2C_RANGE", "#HW_I2C_CLKT",
             "#HW_I2C_SDA", "#HW_I2C_SCL")


def clock_calc(khz):
    """master.c:56-72, restated."""
    if khz <= 100:
        min_high = 4000
    elif khz <= 400:
        min_high = ((khz - 100) * 600 + (400 - khz) * 4000) // 300
    else:
        min_high = ((khz - 400) * 260 + (1000 - khz) * 600) // 600
    high = (CLK_KHZ * min_high + 999999) // 1000000 + 1
    period = (CLK_KHZ + khz - 1) // khz
    return (high - CLK_KHZ * FALL_NS // 1000000,
            period - high - CLK_KHZ * RISE_NS // 1000000, period)


class Device:
    """A register-pointer device (EEPROM-like): first written byte sets the
    pointer, later bytes store; reads return successive bytes."""

    def __init__(self, nack_after=None, stretch=False):
        self.mem = bytearray(range(256))
        self.ptr = 0
        self.first = True
        self.nack_after = nack_after
        self.stretch = stretch
        self.written = []

    def start(self):
        self.first = True
        self.count = 0

    def write(self, b):
        self.count += 1
        if self.nack_after is not None and self.count > self.nack_after:
            return False
        self.written.append(b)
        if self.first:
            self.ptr = b
            self.first = False
        else:
            self.mem[self.ptr] = b
            self.ptr = (self.ptr + 1) & 0xFF
        return True

    def read(self):
        v = self.mem[self.ptr]
        self.ptr = (self.ptr + 1) & 0xFF
        return v


class DesignWare:
    def __init__(self, cpu, devices, hold, comp_type=COMP_TYPE, byte_ticks=BYTE_TICKS):
        self.cpu = cpu
        self.byte_ticks = byte_ticks
        self.devices = devices
        self.hold = hold
        self.comp_type = comp_type
        self.r = {}
        self.enabled = False
        self.txq = []                       # (cmd, enqueue time)
        self.rxq = []
        self.abort = False
        self.source = 0
        self.stop_det = False
        self.in_txn = False
        self.dev = None
        self.dir = None
        self.busy_until = 0
        self.hung = False
        self.txns = []                      # (addr, 'r'/'w', bytes, how it ended)
        self.cur = None
        self.writes_while_enabled = []

    def now(self):
        return self.cpu.cntpct

    def _end(self, how):
        if self.cur is not None:
            self.txns.append((self.cur[0], self.cur[1], bytes(self.cur[2]), how))
        self.cur = None
        self.in_txn = False
        self.stop_det = True

    def _abort(self, bit):
        self.source |= 1 << bit
        self.abort = True
        self.txq.clear()
        if self.in_txn:
            self._end("abort")
        else:
            self.stop_det = True

    def advance(self):
        now = self.now()
        while self.txq and not self.hung and self.busy_until <= now:
            cmd, t = self.txq[0]
            if self.in_txn and not self.hold and t > self.busy_until:
                self._end("fifo-empty")           # the FIFO ran dry: STOP
                continue
            self.txq.pop(0)
            start = max(self.busy_until, t)
            rd = bool(cmd & 0x100)
            if not self.in_txn:
                addr = self.r.get(0x04, 0) & 0x7F
                self.in_txn = True
                self.cur = [addr, "r" if rd else "w", []]
                self.dir = rd
                self.dev = self.devices.get(addr)
                if self.dev is None:
                    self.busy_until = start + self.byte_ticks
                    self._abort(0)                # ABRT_7B_ADDR_NOACK
                    return
                self.dev.start()
                if self.dev.stretch:
                    self.hung = True              # SCL held low for ever
                    return
            elif rd != self.dir:
                d.die("READ and WRITE commands mixed in one message without RESTART")
            if rd:
                if len(self.rxq) >= RX_DEPTH:
                    d.die("RX FIFO overrun: more READ commands outstanding than its depth")
                b = self.dev.read()
                self.rxq.append(b)
                self.cur[2].append(b)
            else:
                if not self.dev.write(cmd & 0xFF):
                    self.busy_until = start + self.byte_ticks
                    self._abort(3)                # ABRT_TXDATA_NOACK
                    return
                self.cur[2].append(cmd & 0xFF)
            self.busy_until = start + self.byte_ticks
            if cmd & 0x200:
                self._end("stop")
        if (not self.txq and self.in_txn and not self.hold and not self.hung
                and self.busy_until <= now):
            self._end("fifo-empty")

    def __call__(self, addr, size, value):
        if size != 4:
            d.die("DesignWare access of %d bytes at $%X" % (size, addr))
        off = addr - DW
        self.advance()
        if value is None:
            if off == 0x10:
                if not self.rxq:
                    d.die("DATA_CMD read with the RX FIFO empty")
                return self.rxq.pop(0)
            if off == 0x34:
                return (0x40 if self.abort else 0) | (0x200 if self.stop_det else 0)
            if off == 0x40:
                self.abort = False
                self.source = 0
                self.stop_det = False
                return 0
            if off == 0x54:
                self.abort = False
                self.source = 0
                return 0
            if off == 0x60:
                self.stop_det = False
                return 0
            if off == 0x6C:
                return 1 if self.enabled else 0
            if off == 0x9C:
                return 1 if self.enabled else 0
            if off == 0x74:
                return len(self.txq)
            if off == 0x78:
                return len(self.rxq)
            if off == 0x80:
                return self.source
            if off == 0xF4:
                return PARAM_1
            if off == 0xFC:
                return self.comp_type
            if off in (0x00, 0x04, 0x14, 0x18, 0x1C, 0x20, 0x30, 0x38, 0x3C):
                return self.r.get(off, 0)
            d.die("read of DesignWare offset $%X, which this gate does not model" % off)
        if off in (0x00, 0x04, 0x14, 0x18, 0x1C, 0x20):
            if self.enabled:
                d.die("offset $%X written while IC_ENABLE is set - the block ignores it" % off)
            self.r[off] = value
            return
        if off in (0x30, 0x38, 0x3C):
            self.r[off] = value
            return
        if off == 0x6C:
            if value & ~1:
                d.die("IC_ENABLE written with $%X" % value)
            if not (value & 1) and self.enabled:
                self.txq.clear()
                self.rxq.clear()
                if self.in_txn:
                    self._end("disabled")
                self.hung = False
            self.enabled = bool(value & 1)
            return
        if off == 0x10:
            if not self.enabled:
                d.die("DATA_CMD written while the block is disabled")
            if value & ~0x3FF or value & 0x400:
                d.die("DATA_CMD $%X sets a bit this driver has no business setting" % value)
            if self.abort:
                return                              # flushed until CLR_TX_ABRT
            if len(self.txq) >= TX_DEPTH:
                d.die("TX FIFO overflow: DATA_CMD pushed with TXFLR at its depth")
            self.txq.append((value, self.now()))
            self.advance()
            return
        d.die("write of DesignWare offset $%X, which this gate does not model" % off)


def driver(override):
    hal = d.source(REL_HAL, override)
    consts = "\n".join("%s = %d" % (n, d.const_in(hal, n, REL_HAL)) for n in HAL_NAMES)
    return ("; i2c_dw_check driver - generated\n" + consts + "\n"
            'XIncludeFile "%s"\nXIncludeFile "%s"\nXIncludeFile "%s"\nXIncludeFile "%s"\n'
            % (REL_TIMER, REL_GPIO, REL_LIB, REL_HW) +
            "Global gate_never.i\n"
            "If gate_never = 1\n"
            "  HwI2cDefaultBus() : HwI2cBusValid(0) : HwI2cUp(0) : HwI2cProbe(0, 0)\n"
            "  HwI2cWrite(0, 0, 0, 0) : HwI2cRead(0, 0, 0, 0) : HwI2cSetSpeed(0, 0)\n"
            "  HwI2cGetSpeed(0) : HwI2cSourceHz(0) : HwI2cSourceWhere(0)\n"
            "  HwI2cRateMin(0) : HwI2cRateMax(0) : HwI2cPin(0, 0) : HwI2cPinFunc(0)\n"
            "  HwI2cPinReady(0, 0) : HwI2cPadLevel(0, 0) : DwI2cAbortSource()\n"
            "EndIf\n")


def gate(cc, override, workdir):
    hal = d.source(REL_HAL, override)
    H = {n: d.const_in(hal, n, REL_HAL) for n in HAL_NAMES}
    img, procs = d.build(cc, driver(override), "i2c_dw_drv", workdir,
                         override, [REL_TIMER, REL_GPIO, REL_LIB, REL_HW])
    checks = [0]

    def check(ok, what):
        if not ok:
            d.die(what)
        checks[0] += 1

    def machine(hold, comp_type=COMP_TYPE, byte_ticks=BYTE_TICKS):
        gpio = Rp1Gpio()
        devs = {0x50: Device(), 0x3C: Device(nack_after=1), 0x21: Device(stretch=True)}
        box = {}

        def model(addr, size, value):
            if DW <= addr < DW + 0x1000:
                return box["dw"](addr, size, value)
            return gpio(addr, size, value)
        m = d.Machine(img, procs, model)
        box["dw"] = DesignWare(m.cpu, devs, hold, comp_type, byte_ticks)
        return m, box["dw"], gpio, devs

    for hold, ticks in ((False, BYTE_TICKS), (True, BYTE_TICKS), (True, FAST_TICKS)):
        m, dw, gpio, devs = machine(hold, byte_ticks=ticks)
        call = lambda name, *a: m.signed(m.call(name, *a))
        tag = ("HOLD" if hold else "NO-HOLD") + ("/FAST" if ticks == FAST_TICKS else "")

        # --- bus identity and up -------------------------------------------
        check(call("HwI2cDefaultBus") == 1, "default bus is not 1 (Linux i2c1)")
        check(call("HwI2cBusValid", 0) == 0 and call("HwI2cProbe", 0, 0x50) == H["#HW_I2C_NOBUS"],
              "bus 0 was accepted")
        check(call("HwI2cUp", 1) == 1, "HwI2cUp(1) failed against a DesignWare block")
        check(gpio.reg.get(IO_BANK0 + 2 * 8 + 4) == 3 and gpio.reg.get(IO_BANK0 + 3 * 8 + 4) == 3,
              "GPIO 2/3 are not on FUNCSEL 3 (i2c1)")
        for p in (2, 3):
            padv = gpio.reg.get(PADS_BANK0 + 4 + p * 4, 0)
            check((padv >> 2) & 3 == 2 and padv & 0x40 and not padv & 0x80 and (padv >> 4) & 3 == 3,
                  "pad %d is $%X: want pull UP (RP1 field 2), 12 mA (drive field 3, "
                  "rp1.dtsi drive-strength), input on, output enabled" % (p, padv))
        hc, lc, _ = clock_calc(100)
        check(dw.r.get(0x00) == 0x63, "IC_CON is $%X, want MASTER|SPEED_STD|RESTART_EN|"
              "SLAVE_DISABLE = $63" % dw.r.get(0x00, 0))
        check((dw.r.get(0x14), dw.r.get(0x18)) == (hc, lc),
              "SS counts %r, clock_calc says %r" % ((dw.r.get(0x14), dw.r.get(0x18)), (hc, lc)))
        check(dw.r.get(0x30) == 0, "interrupts not masked")
        check(call("HwI2cGetSpeed", 1) == 100000, "GetSpeed after up is not 100000")
        check(call("HwI2cPinReady", 1, H["#HW_I2C_SDA"]) == 1 and
              call("HwI2cPinReady", 1, H["#HW_I2C_SCL"]) == 1, "PinReady after up is not 1")
        check(call("HwI2cPin", 1, H["#HW_I2C_SDA"]) == 2 and call("HwI2cPin", 1, H["#HW_I2C_SCL"]) == 3,
              "SDA/SCL are not GPIO 2/3")
        check(m.cstr(call("HwI2cPinFunc", 1)) == "alt3", "pin function word is not alt3")
        gpio.pad_in = 1 << 3
        check(call("HwI2cPadLevel", 1, H["#HW_I2C_SCL"]) == 1 and
              call("HwI2cPadLevel", 1, H["#HW_I2C_SDA"]) == 0, "pad levels misread")
        check(call("HwI2cUp", 1) == 1 and len(dw.txns) == 0, "a second HwI2cUp did bus work")

        # --- probe ----------------------------------------------------------
        check(call("HwI2cProbe", 1, 0x50) == H["#HW_I2C_OK"], "%s: probe of a present device" % tag)
        check(dw.txns[-1][:2] == (0x50, "r") and len(dw.txns[-1][2]) == 1 and dw.txns[-1][3] == "stop",
              "%s: probe was not one 1-byte read ending in STOP: %r" % (tag, dw.txns[-1:]))
        check(call("HwI2cProbe", 1, 0x51) == H["#HW_I2C_NACK"], "%s: absent device not NACK" % tag)
        check(call("DwI2cAbortSource") & 1, "7B_ADDR_NOACK not kept")
        check(call("HwI2cProbe", 1, 0x50) == H["#HW_I2C_OK"], "%s: bus not usable after a NACK" % tag)

        # --- write longer than the TX FIFO (16), one message ---------------------
        payload = bytes([0x10] + [(0xA0 + i) & 0xFF for i in range(19)])
        m.poke(BUF, payload)
        n0 = len(dw.txns)
        check(call("HwI2cWrite", 1, 0x50, BUF, len(payload)) == H["#HW_I2C_OK"],
              "%s: 20-byte write failed" % tag)
        check(dw.txns[n0:] == [(0x50, "w", payload, "stop")],
              "%s: the write was not ONE message ending in STOP: %r" % (tag, dw.txns[n0:]))
        check(bytes(devs[0x50].mem[0x10:0x23]) == payload[1:], "device memory not written")

        # --- read longer than the RX FIFO, one message ----------------------
        m.poke(BUF, b"\x10")
        check(call("HwI2cWrite", 1, 0x50, BUF, 1) == H["#HW_I2C_OK"], "pointer write failed")
        m.poke(BUF, b"\x00" * 20)
        n0 = len(dw.txns)
        check(call("HwI2cRead", 1, 0x50, BUF, 20) == H["#HW_I2C_OK"], "%s: 20-byte read failed" % tag)
        want = bytes(devs[0x50].mem[0x10:0x24])
        check(m.peek(BUF, 20) == want, "%s: read data %s, device holds %s"
              % (tag, m.peek(BUF, 20).hex(), want.hex()))
        check(len(dw.txns) == n0 + 1 and dw.txns[-1][3] == "stop",
              "%s: the read was not ONE message ending in STOP: %r" % (tag, dw.txns[n0:]))

        # --- data NACK --------------------------------------------------------
        m.poke(BUF, b"\x01\x02\x03")
        check(call("HwI2cWrite", 1, 0x3C, BUF, 3) == H["#HW_I2C_NACK"], "%s: data NACK not reported" % tag)
        check(call("DwI2cAbortSource") & 8, "TXDATA_NOACK not kept")

        # --- a device that holds SCL: bounded TIMEOUT, controller off ------
        steps_before = m.cpu.cntpct
        check(call("HwI2cRead", 1, 0x21, BUF, 1) == H["#HW_I2C_TIMEOUT"], "%s: a hung bus did not time out" % tag)
        spent = m.cpu.cntpct - steps_before
        check(spent >= 54 * 20000, "%s: gave up after %d ticks, before the 20 ms deadline" % (tag, spent))
        check(not dw.enabled, "%s: controller left enabled after a timeout" % tag)
        check(call("HwI2cProbe", 1, 0x50) == H["#HW_I2C_OK"], "%s: bus not usable after a timeout" % tag)

        # --- arguments refused before the bus ------------------------------
        n0 = len(dw.txns)
        check(call("HwI2cWrite", 1, 0x80, BUF, 1) == H["#HW_I2C_ARG"], "address $80 accepted")
        check(call("HwI2cRead", 1, 0x50, BUF, 0) == H["#HW_I2C_ARG"], "zero-length read accepted")
        check(len(dw.txns) == n0, "a refused argument reached the bus")

        # --- speed -----------------------------------------------------------
        check(call("HwI2cSetSpeed", 1, 400000) == 400000, "400 kHz not accepted")
        hc, lc, _ = clock_calc(400)
        check(dw.r.get(0x00) == 0x65 and (dw.r.get(0x1C), dw.r.get(0x20)) == (hc, lc),
              "400 kHz: CON $%X FS %r, want $65 %r" % (dw.r.get(0x00, 0), (dw.r.get(0x1C), dw.r.get(0x20)), (hc, lc)))
        check(call("HwI2cGetSpeed", 1) == 400000, "GetSpeed after 400k")
        check(call("HwI2cSetSpeed", 1, 500000) == H["#HW_I2C_RANGE"], "500 kHz accepted")
        check(call("HwI2cSetSpeed", 1, 2000) == H["#HW_I2C_RANGE"], "2 kHz accepted (LCNT > 16 bits)")
        check(dw.r.get(0x00) == 0x65 and call("HwI2cGetSpeed", 1) == 400000,
              "a refused rate disturbed the programmed one")
        lo = next(k for k in range(1, 401) if 8 <= clock_calc(k)[1] <= 0xFFFF and clock_calc(k)[0] >= 6)
        check(call("HwI2cRateMin", 1) == lo * 1000, "RateMin %d, the 16-bit counts allow %d"
              % (call("HwI2cRateMin", 1), lo * 1000))
        check(call("HwI2cRateMax", 1) == 400000, "RateMax is not 400000")
        check(call("HwI2cSetSpeed", 1, 100000) == 100000 and dw.r.get(0x00) == 0x63, "back to 100k")
        m.poke(BUF, payload)
        n0 = len(dw.txns)
        check(call("HwI2cWrite", 1, 0x50, BUF, len(payload)) == H["#HW_I2C_OK"] and
              dw.txns[n0:] == [(0x50, "w", payload, "stop")], "%s: write after speed changes" % tag)
        check(call("HwI2cSourceHz", 1) == 200_000_000, "source clock is not RP1_CLK_SYS 200 MHz")
        check("not measured" in m.cstr(call("HwI2cSourceWhere", 1)), "source provenance not stated")

    # --- a block that is not DesignWare: refused loudly --------------------
    m, dw, gpio, devs = machine(False, comp_type=0x12345678)
    call = lambda name, *a: m.signed(m.call(name, *a))
    check(call("HwI2cUp", 1) == 0, "HwI2cUp accepted a block whose COMP_TYPE is not DesignWare")
    check(call("HwI2cProbe", 1, 0x50) == H["#HW_I2C_TIMEOUT"] and not dw.txns and not dw.txq,
          "a non-DesignWare block was driven")
    return checks[0]


MUTATIONS = [
    (REL_LIB, "the vault's mistyped base $1F0000074000",
     "#DWI2C_BASE = $1F00074000", "#DWI2C_BASE = $1F0000074000"),
    (REL_LIB, "STOP on the first byte, not the last",
     "          If issued = n - 1\n            cmd = #DWI2C_CMD_STOP",
     "          If issued = 0\n            cmd = #DWI2C_CMD_STOP"),
    (REL_LIB, "no STOP at all", "            cmd = #DWI2C_CMD_STOP\n", "            cmd = 0\n"),
    (REL_LIB, "READ as bit 10 (RESTART)", "#DWI2C_CMD_READ = $100", "#DWI2C_CMD_READ = $400"),
    (REL_LIB, "NACK bits not recognised", "#DWI2C_ABRT_NOACK = $1F", "#DWI2C_ABRT_NOACK = $0"),
    (REL_LIB, "RX outstanding limit ignored",
     "        If rd = 0 Or (issued - got) < dwi2c_rxdepth", "        If rd = 0 Or (issued - got) < 1000"),
    (REL_LIB, "TX depth ignored",
     "      If DwI2cRd(#DWI2C_TXFLR) < dwi2c_txdepth", "      If DwI2cRd(#DWI2C_TXFLR) < 1000"),
    (REL_LIB, "COMP_TYPE not checked",
     "  If dwi2c_comp_type <> #DWI2C_COMP_TYPE_VALUE\n    ProcedureReturn 0\n",
     "  If dwi2c_comp_type = -1\n    ProcedureReturn 0\n"),
    (REL_LIB, "fall time not subtracted from HCNT",
     "  hc = high - (clkKhz * #DWI2C_FALL_NS) / 1000000", "  hc = high"),
    (REL_LIB, "TAR written with the block enabled",
     "  DwI2cWr(#DWI2C_TAR, addr)\n  DwI2cWr(#DWI2C_INTR_MASK, 0)\n  DwI2cWr(#DWI2C_ENABLE, 1)",
     "  DwI2cWr(#DWI2C_INTR_MASK, 0)\n  DwI2cWr(#DWI2C_ENABLE, 1)\n  DwI2cWr(#DWI2C_TAR, addr)"),
    (REL_LIB, "deadline not measured from now",
     "    deadline = Ticks() + (hz / 1000000)", "    deadline = 0 * Ticks() + (hz / 1000000)"),
    (REL_LIB, "no deadline at all, the spin backstop only",
     "    If deadline > 0\n      If Ticks() > deadline", "    If deadline < 0\n      If Ticks() > deadline"),
    (REL_LIB, "timeout leaves the block enabled",
     "    dwi2c_timeouts = dwi2c_timeouts + 1\n    DwI2cDisable()\n", "    dwi2c_timeouts = dwi2c_timeouts + 1\n"),
    (REL_LIB, "fast mode programmed as standard",
     "    con = con | #DWI2C_CON_SPEED_FAST", "    con = con | #DWI2C_CON_SPEED_STD"),
    (REL_LIB, "pins on the wrong function", "#DWI2C_FUNCSEL  = 3", "#DWI2C_FUNCSEL  = 4"),
    (REL_LIB, "pins at 8 mA, not rp1.dtsi's 12", "#DWI2C_DRIVE_MA = 12 ", "#DWI2C_DRIVE_MA = 8 "),
    (REL_LIB, "pins pulled down", "  Rp1PinPull(#DWI2C_PIN_SDA, #RP1_PULL_UP)", "  Rp1PinPull(#DWI2C_PIN_SDA, #RP1_PULL_DOWN)"),
    (REL_LIB, "refused rate still programs counts",
     "  r = DwI2cCounts(hz)\n  If r <= 0\n    ProcedureReturn #DWI2C_RANGE\n  EndIf",
     "  r = DwI2cCounts(hz)\n  If r <= 0\n    dwi2c_rate = 5000\n    ProcedureReturn #DWI2C_RANGE\n  EndIf"),
    (REL_HW, "2712 NACK mapped to TIMEOUT",
     "    Case #DWI2C_NACK\n      ProcedureReturn #HW_I2C_NACK", "    Case #DWI2C_NACK\n      ProcedureReturn #HW_I2C_TIMEOUT"),
    (REL_HW, "2712 bus 0 accepted", "#PI5_I2C_HEADER_BUS = 1", "#PI5_I2C_HEADER_BUS = 0"),
    (REL_HW, "2712 SDA and SCL crossed",
     "  If which = #HW_I2C_SDA\n    ProcedureReturn #DWI2C_PIN_SDA",
     "  If which = #HW_I2C_SDA\n    ProcedureReturn #DWI2C_PIN_SCL"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--mutate", action="store_true")
    a = ap.parse_args()
    cc = d.compiler(a.compiler)
    top = pathlib.Path(tempfile.mkdtemp(prefix="i2c-dw-"))
    try:
        try:
            n = gate(cc, {}, top / "gate")
        except d.GateFail as exc:
            print("i2c_dw_check: FAIL - %s" % exc)
            return 1
        print("i2c_dw_check: PASS - %d checks, NO-HOLD, HOLD and HOLD/FAST bus variants" % n)
        if a.mutate:
            if d.run_mutations("i2c_dw_check", MUTATIONS,
                               lambda ov, wd: gate(cc, ov, wd), top / "mut"):
                return 1
        return 0
    finally:
        shutil.rmtree(top, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Desk gate: SPI on the Pi 5 - RaspberryPi4/Lib/spi_dw.pi4 (RP1 SPI0, a
Synopsys DesignWare APB SSI), the HwSpi* backend RaspberryPi4/Board/
hw_spi.pi4, the shared layer Anvil/Bus/spi.pbi and the `spi` command
Anvil/Core/spi_cmd.pbi.

The -t pi5 compiled code runs under tools/a64/a64_interp.py against a
model of the SSI and of RP1's GPIO (gpio_rp1_check.Rp1Gpio), written from
the pinned Linux sources (raspberrypi/linux 7e030b60792d), not from the
library:

  spi-dw.h       offsets CTRLR0 $00, SSIENR $08, SER $10, BAUDR $14,
                 TXFTLR $18, TXFLR $20, RXFLR $24, SR $28 (BUSY bit 0),
                 IMR $2C, ICR $48, DR $60; PSSI CTRLR0 SCPH bit 6, SCPOL
                 bit 7, TMOD [9:8], DFS [3:0] or DFS32 [20:16]
  spi-dw-core.c  the FIFO probe through TXFTLR; the DFS32 probe; SER must
                 be set or the SSI does not shift (dw_spi_set_cs); BAUDR =
                 (DIV_ROUND_UP(clk, hz) + 1) & ~1, even, 2..$FFFE; never
                 more frames in flight than the FIFO depth (dw_spi_tx_max)
  rp1.dtsi, bcm2712-rpi.dtsi, pinctrl-rp1.c
                 spi@50000 -> $1F00050000; spi0 = FUNCSEL 0 on GPIO 9/10/11,
                 bias disabled, 12 mA; CE0 = GPIO 8, CE1 = GPIO 7, active-low
                 GPIOs with pull-up; RP1_CLK_SYS 200 MHz

What the model refuses by name: CTRLR0 or BAUDR written while enabled; an
odd BAUDR; DR written while disabled or with the TX FIFO full; a frame
shifted with no chip select low or both low; a chip select released while
a frame is still on the wire; an RX FIFO overrun; a DR read
of an empty RX FIFO. The bus runs in model time. Two SSI builds are run
(16-bit frame field, FIFO 8; 32-bit frame field, FIFO 64; and FIFO 8 with a
bus faster than the CPU, which is what overruns an unbounded RX), each device has
a mode it answers in (the wrong CPOL/CPHA reads $FF), and a hung variant
never shifts. The `spi` command is driven through the real parse.pbi
procedures (extracted by name) with output captured, including a build
with #CAP_SPI = 0 that must refuse with hal.pbi's sentence and touch no
register. Desk proof only; silicon owed.

  py -3 -B tools/a64/spi_dw_check.py --compiler <PureMetalForge.exe> [--mutate]
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import pi5_desk as d                               # noqa: E402
from gpio_rp1_check import Rp1Gpio, IO_BANK0, PADS_BANK0, SYS_RIO0   # noqa: E402

SSI = 0x1F_0005_0000
CLK = 200_000_000
FRAME_TICKS = 1500
TX, RX = 0x2800000, 0x2801000

REL_LIB = "RaspberryPi4/Lib/spi_dw.pi4"
REL_HW = "RaspberryPi4/Board/hw_spi.pi4"
REL_BUS = "Anvil/Bus/spi.pbi"
REL_CMD = "Anvil/Core/spi_cmd.pbi"
REL_GPIO = "RaspberryPi4/Lib/gpio_rp1.pi4"
REL_TIMER = "RaspberryPi4/Lib/timer.pi4"
REL_HAL = "Anvil/Hal/hal.pbi"
REL_FMT = "Anvil/Core/format.pbi"
REL_PARSE = "Anvil/Core/parse.pbi"
REL_STATE = "Anvil/Core/state.pbi"
INCLUDES = [REL_TIMER, REL_FMT, REL_HAL, REL_GPIO, REL_LIB, REL_HW, REL_BUS, REL_CMD]
PARSE_PROCS = ("HexVal", "WordIs", "SkipSpace", "SkipWord", "ParseHex", "ParseDec")


def baud(hz):
    """dw_spi_update_config, restated."""
    return min(-(-CLK // hz) + 1, 0xFFFE) & 0xFFFE


class Device:
    def __init__(self, mode):
        self.mode = mode
        self.seen = []                    # bytes clocked in while selected

    def byte(self, mosi, mode, index):
        self.seen.append(mosi)
        if mode != self.mode:
            return 0xFF
        return (mosi ^ 0x5A) + index & 0xFF


class Ssi:
    def __init__(self, cpu, gpio, dfs32, fifo, hang=False, frame_ticks=FRAME_TICKS):
        self.cpu, self.gpio = cpu, gpio
        self.frame_ticks = frame_ticks
        self.dfs32, self.fifo, self.hang = dfs32, fifo, hang
        self.r = {0x00: 0, 0x10: 0, 0x14: 0, 0x18: 0, 0x2C: 0x3F}
        self.en = 0
        self.txq, self.rxq = [], []
        self.busy_until = 0
        self.devices = {0: Device(0), 1: Device(3)}
        self.frames = []                  # (cs, mosi, miso, ctrlr0, baudr)
        self.index = 0
        self.last_cs = None

    def cs_low(self):
        low = []
        for cs, pin in ((0, 8), (1, 7)):
            oe = self.gpio.reg.get(SYS_RIO0 + 4, 0) >> pin & 1
            out = self.gpio.reg.get(SYS_RIO0, 0) >> pin & 1
            fs = self.gpio.reg.get(IO_BANK0 + pin * 8 + 4, 0x1F) & 0x1F
            if oe and fs == 5 and out == 0:
                low.append(cs)
        return low

    def mode(self):
        c = self.r[0x00]
        return (2 if c & 0x80 else 0) | (1 if c & 0x40 else 0)

    def advance(self):
        now = self.cpu.cntpct
        while self.txq and self.en and self.r[0x10] and not self.hang and self.busy_until <= now:
            mosi = self.txq.pop(0)
            low = self.cs_low()
            if len(low) != 1:
                d.die("a frame was clocked with chip selects %r low - exactly one must be" % low)
            cs = low[0]
            if cs != self.last_cs:
                self.index = 0
                self.last_cs = cs
            miso = self.devices[cs].byte(mosi, self.mode(), self.index)
            self.index += 1
            if len(self.rxq) >= self.fifo:
                d.die("RX FIFO overrun: more frames in flight than the FIFO holds")
            self.rxq.append(miso)
            self.frames.append((cs, mosi, miso, self.r[0x00], self.r[0x14]))
            self.busy_until = max(self.busy_until, now) + self.frame_ticks
        if not self.cs_low():
            self.last_cs = None

    def __call__(self, addr, size, value):
        if size != 4:
            d.die("SSI access of %d bytes at $%X" % (size, addr))
        off = addr - SSI
        self.advance()
        if value is None:
            if off == 0x60:
                if not self.rxq:
                    d.die("DR read with the RX FIFO empty")
                return self.rxq.pop(0)
            if off == 0x20:
                return len(self.txq)
            if off == 0x24:
                return len(self.rxq)
            if off == 0x28:
                busy = bool(self.txq) or self.cpu.cntpct < self.busy_until
                return (1 if busy and self.en else 0) | (0 if len(self.txq) >= self.fifo else 2) | (0 if self.txq else 4)
            if off == 0x48:
                return 0
            if off == 0x08:
                return self.en
            if off in self.r:
                return self.r[off]
            d.die("read of SSI offset $%X, which this gate does not model" % off)
        if off == 0x08:
            if not value & 1:
                self.txq.clear()
                self.rxq.clear()
            self.en = value & 1
            return
        if off == 0x00:
            if self.en:
                d.die("CTRLR0 written while the SSI is enabled - the block ignores it")
            mask = (0x1F0000 | 0xFFF0) if self.dfs32 else 0xFFFF
            self.r[0x00] = value & mask
            return
        if off == 0x14:
            if self.en:
                d.die("BAUDR written while the SSI is enabled")
            if value and (value & 1 or value < 2):
                d.die("BAUDR $%X: the divider must be even and at least 2" % value)
            self.r[0x14] = value
            return
        if off == 0x18:
            if value < self.fifo:
                self.r[0x18] = value
            return
        if off in (0x10, 0x2C):
            self.r[off] = value
            return
        if off == 0x60:
            if not self.en:
                d.die("DR written while the SSI is disabled")
            if len(self.txq) >= self.fifo:
                d.die("TX FIFO overflow")
            self.txq.append(value & 0xFF)
            self.advance()
            return
        d.die("write of SSI offset $%X, which this gate does not model" % off)


def extract(text, name):
    m = re.search(r"^Procedure[.\w]*\s+%s\(.*?^EndProcedure[^\n]*\n" % name, text, re.M | re.S)
    if not m:
        d.die("parse.pbi no longer defines %s" % name)
    return m.group(0)


def driver(override, cap):
    state = d.source(REL_STATE, override)
    parse = d.source(REL_PARSE, override)
    consts = "\n".join("%s = %d" % (n, d.const_in(state, n, REL_STATE))
                       for n in ("#LINE_MAX", "#HEX_MAX", "#DEC_MAX"))
    head = """; spi_dw_check driver - generated
EnableExplicit
%s
#CAP_SPI = %d
Global Dim gLine.b[#LINE_MAX + 8]
Global gLineLen.i
Global gPos.i
Global gParseOk.i
Global gParseOver.i
Global gWordAt.i
Global gWordLen.i
Global Dim gate_out.a[65536]
Global gate_n.i
Procedure UartWrite(c.i)
  If gate_n < 65000
    gate_out[gate_n] = c & $FF
    gate_n = gate_n + 1
  EndIf
EndProcedure
Procedure UartWriteStr(*s)
  Define i.i
  Define c.i
  i = 0
  Repeat
    c = PeekA(*s + i) & $FF
    If c = 0
      Break
    EndIf
    UartWrite(c)
    i = i + 1
  ForEver
EndProcedure
Procedure str_print_at(*s)
  UartWriteStr(*s)
EndProcedure
Procedure UartWriteNl()
  UartWrite(13)
  UartWrite(10)
EndProcedure
Procedure PrintNl()
  UartWriteNl()
EndProcedure
Global Dim gate_dg.a[24]
Procedure PrintDec(v.i)

  Define n.i
  If v < 0
    UartWrite(45)
    v = -v
  EndIf
  n = 0
  Repeat
    gate_dg[n] = 48 + (v %% 10)
    v = v / 10
    n = n + 1
  Until v = 0
  While n > 0
    n = n - 1
    UartWrite(gate_dg[n])
  Wend
EndProcedure
""" % (consts, cap)
    body = "".join(extract(parse, p) for p in PARSE_PROCS)
    tail = """Procedure.i GateOut()
  ProcedureReturn @gate_out[0]
EndProcedure
Procedure.i GateOutLen()
  ProcedureReturn gate_n
EndProcedure
Procedure GateRun(*s)
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
  CmdSpi()
EndProcedure
Global gate_never.i
If gate_never = 1
  GateRun(0) : GateOut() : GateOutLen() : SpiOpen(0, 0, 0, 0) : SpiTransfer(0, 0, 0) : SpiClose()
  SpiWhy() : HwSpiRateMin(0) : HwSpiRateMax(0) : HwSpiGetSpeed(0) : HwSpiSetSpeed(0, 0) : HwSpiPin(0, 0)
EndIf
"""
    inc = "".join('XIncludeFile "%s"\n' % i for i in INCLUDES)
    return head + body + inc + tail


def gate(cc, override, workdir):
    hal = d.source(REL_HAL, override)
    H = {n: d.const_in(hal, n, REL_HAL) for n in
         ("#HW_SPI_OK", "#HW_SPI_ARG", "#HW_SPI_NOBUS", "#HW_SPI_IO",
          "#HW_SPI_MOSI", "#HW_SPI_MISO", "#HW_SPI_SCLK", "#HW_SPI_CS0", "#HW_SPI_CS1")}
    img, procs = d.build(cc, driver(override, 1), "spi_drv", workdir / "cap1", override, INCLUDES)
    checks = [0]

    def check(ok, what):
        if not ok:
            d.die(what)
        checks[0] += 1

    def machine(dfs32, fifo, hang=False, image=None, frame_ticks=FRAME_TICKS):
        gpio = Rp1Gpio()
        box = {}

        def model(addr, size, value):
            if SSI <= addr < SSI + 0x1000:
                return box["ssi"](addr, size, value)
            s = box.get("ssi")
            if (s is not None and value is not None and addr == SYS_RIO0 + 0x2000
                    and s.cpu.cntpct < s.busy_until and s.cs_low()
                    and value & (1 << (8 if s.cs_low()[0] == 0 else 7))):
                d.die("a chip select was released while a frame was still on the wire")
            return gpio(addr, size, value)
        m = d.Machine(image or img, procs if image is None else image_procs, model)
        box["ssi"] = Ssi(m.cpu, gpio, dfs32, fifo, hang, frame_ticks)
        call = lambda name, *a: m.signed(m.call(name, *a))
        return m, box["ssi"], gpio, call

    def run(m, line):
        s = 0x2802000
        m.poke(s, line.encode() + b"\0")
        m.call("GateRun", s)
        n = m.call("GateOutLen")
        return m.peek(m.call("GateOut"), n).decode("latin-1")

    for dfs32, fifo, ft in ((False, 8, FRAME_TICKS), (True, 64, FRAME_TICKS), (False, 8, 1)):
        tag = ("DFS32/FIFO64" if dfs32 else "DFS16/FIFO8") + ("/FAST" if ft == 1 else "")
        m, ssi, gpio, call = machine(dfs32, fifo, frame_ticks=ft)
        # --- open: pins, probes, divider --------------------------------
        check(call("SpiOpen", 0, 0, 0, 1_000_000) == 1, "%s: SpiOpen(0,0,0,1 MHz) failed: %s"
              % (tag, m.cstr(call("SpiWhy"))))
        for pin in (9, 10, 11):
            ctrl = gpio.reg.get(IO_BANK0 + pin * 8 + 4)
            pad = gpio.reg.get(PADS_BANK0 + 4 + pin * 4, 0)
            check(ctrl == 0, "GPIO %d is on FUNCSEL %r, want 0 (spi0)" % (pin, ctrl))
            check((pad >> 4) & 3 == 3 and (pad >> 2) & 3 == 0 and pad & 0x40 and not pad & 0x80,
                  "GPIO %d pad $%X: want 12 mA, no pull, enabled" % (pin, pad))
        for pin in (8, 7):
            pad = gpio.reg.get(PADS_BANK0 + 4 + pin * 4, 0)
            check(gpio.reg.get(IO_BANK0 + pin * 8 + 4) == 5 and gpio.reg.get(SYS_RIO0 + 4, 0) >> pin & 1
                  and gpio.reg.get(SYS_RIO0, 0) >> pin & 1 and (pad >> 2) & 3 == 2,
                  "CS GPIO %d is not a pulled-up output idling high" % pin)
        check(call("HwSpiGetSpeed", 0) == CLK // baud(1_000_000), "rate after open")
        for which, pin in (("#HW_SPI_MOSI", 10), ("#HW_SPI_MISO", 9), ("#HW_SPI_SCLK", 11),
                           ("#HW_SPI_CS0", 8), ("#HW_SPI_CS1", 7)):
            check(call("HwSpiPin", 0, H[which]) == pin, "HwSpiPin %s is not GPIO %d" % (which, pin))
        check(call("HwSpiRateMax", 0) == CLK // 2 and call("HwSpiRateMin", 0) == -(-CLK // 0xFFFE),
              "rate range is not clk/2 .. clk/$FFFE")
        # --- one full-duplex transfer, longer than the FIFO -------------
        out = bytes((i * 7 + 1) & 0xFF for i in range(100))
        m.poke(TX, out)
        m.poke(RX, b"\xEE" * 100)
        check(call("SpiTransfer", TX, RX, 100) == 1, "%s: 100-byte transfer failed: %s"
              % (tag, m.cstr(call("SpiWhy"))))
        want = bytes(((b ^ 0x5A) + i) & 0xFF for i, b in enumerate(out))
        check(m.peek(RX, 100) == want, "%s: received bytes differ from the device's reply" % tag)
        check([f[1] for f in ssi.frames] == list(out), "%s: bytes on MOSI differ from the buffer" % tag)
        check(all(f[0] == 0 for f in ssi.frames), "a frame went to the wrong chip select")
        c0 = ssi.frames[0][3]
        dfs = (c0 >> 16) & 0x1F if dfs32 else c0 & 0xF
        check(dfs == 7 and (c0 >> 8) & 3 == 0 and (c0 >> 4) & 3 == 0,
              "%s: CTRLR0 $%X: want 8-bit frames, TMOD transmit+receive, Motorola" % (tag, c0))
        check(ssi.frames[0][4] == baud(1_000_000), "BAUDR %d, Linux's formula says %d"
              % (ssi.frames[0][4], baud(1_000_000)))
        check(ssi.cs_low() == [] and ssi.r[0x10] == 0, "CS or SER left asserted after the transfer")
        # --- every mode, byte-exact only when it matches -----------------
        for mode in range(4):
            check(call("SpiOpen", 0, 1, mode, 3_000_000) == 1, "open cs1 mode %d" % mode)
            check(call("HwSpiGetSpeed", 0) <= 3_000_000, "the achieved rate is above the one asked for")
            ssi.frames.clear()
            m.poke(TX, b"\x10\x20")
            call("SpiTransfer", TX, RX, 2)
            got = m.peek(RX, 2)
            cr = ssi.frames[0][3]
            check(((cr >> 7) & 1, (cr >> 6) & 1) == (mode >> 1, mode & 1),
                  "mode %d programmed CPOL/CPHA %d/%d" % (mode, (cr >> 7) & 1, (cr >> 6) & 1))
            ok = got == bytes([0x10 ^ 0x5A, (0x20 ^ 0x5A) + 1])
            check(ok == (mode == 3), "mode %d: device (mode 3) reply %s" % (mode, got.hex()))
            check(all(f[0] == 1 for f in ssi.frames), "cs 1 was not the one selected")
            check(ssi.frames[0][4] == baud(3_000_000), "BAUDR %d at 3 MHz, Linux's formula says %d"
                  % (ssi.frames[0][4], baud(3_000_000)))
        # --- tx-only and rx-only ----------------------------------------
        ssi.frames.clear()
        check(call("SpiTransfer", 0, RX, 3) == 1 and [f[1] for f in ssi.frames] == [0, 0, 0],
              "an rx-only transfer did not clock out zeros")
        check(call("SpiTransfer", TX, 0, 2) == 1, "a tx-only transfer failed")
        # --- refusals, in sentences, nothing touched -----------------------
        n0 = len(ssi.frames)
        for args, frag in (((0, 2, 0, 1_000_000), "chip select"), ((0, 0, 4, 1_000_000), "modes run from 0 to 3"),
                           ((1, 0, 0, 1_000_000), "no SPI bus"), ((0, 0, 0, 1000), "slower")):
            check(call("SpiOpen", *args) == 0 and frag in m.cstr(call("SpiWhy")),
                  "SpiOpen%r was not refused with a sentence about the %s" % (args, frag))
        check(call("SpiTransfer", TX, RX, 0) == 0 and "1 to 4096" in m.cstr(call("SpiWhy")), "0-byte transfer")
        check(len(ssi.frames) == n0, "a refused request reached the bus")
        call("SpiClose")
        check(call("SpiTransfer", TX, RX, 1) == 0 and "no SPI device is open" in m.cstr(call("SpiWhy")),
              "a transfer after close was not refused")
        check(ssi.en == 0 and ssi.cs_low() == [], "close left the SSI enabled or a CS low")

    # --- a hung SSI: bounded, CS released, IO ---------------------------
    m, ssi, gpio, call = machine(False, 8, hang=True)
    check(call("SpiOpen", 0, 0, 0, 1_000_000) == 1, "open on the hung model")
    t0 = m.cpu.cntpct
    check(call("SpiTransfer", TX, RX, 4) == 0 and "did not finish" in m.cstr(call("SpiWhy")),
          "a hung controller was not reported in a sentence")
    check(m.cpu.cntpct - t0 >= 54 * 20000, "gave up before the 20 ms deadline")
    check(ssi.en == 0 and ssi.cs_low() == [] and ssi.r[0x10] == 0,
          "after a timeout the SSI, CS or SER was left asserted")

    # --- the command ------------------------------------------------------
    m, ssi, gpio, call = machine(False, 8)
    o = run(m, "spi")
    check("GPIO 11" in o and "GPIO 8" in o and "alt0" in o and "Nothing is open" in o, "spi status: %r" % o[:200])
    o = run(m, "spi open 1 3 2000000")
    check("open in mode 3 at %d Hz" % (CLK // baud(2_000_000)) in o, "spi open: %r" % o)
    o = run(m, "spi xfer 80 00 00")
    rep = " ".join("%02X" % v for v in (0x80 ^ 0x5A, (0 ^ 0x5A) + 1, (0 ^ 0x5A) + 2))
    check("Sent 3 bytes" in o and rep in o, "spi xfer: %r, want %s" % (o, rep))
    o = run(m, "spi xfer 1g")
    check("Nothing was sent" in o, "bad hex was not refused: %r" % o)
    o = run(m, "spi open 5 0 1000000")
    check("chip select does not exist" in o and "Nothing was opened" in o, "bad cs: %r" % o)
    o = run(m, "spi close")
    check("closed" in o and ssi.en == 0, "spi close: %r" % o)
    o = run(m, "spi xfer 01")
    check("no SPI device is open" in o, "xfer after close: %r" % o)
    o = run(m, "spi bogus")
    check("does not know that subcommand" in o, "unknown subcommand: %r" % o)

    # --- #CAP_SPI = 0: hal.pbi's refusal, no register touched ------------
    global image_procs
    img0, image_procs = d.build(cc, driver(override, 0), "spi_drv0", workdir / "cap0", override, INCLUDES)
    m, ssi, gpio, call = machine(False, 8, image=img0)
    o = run(m, "spi open 0 0 1000000")
    check("not available on this board" in o and "no SPI bus" in o and not gpio.log and ssi.r[0x14] == 0,
          "#CAP_SPI = 0 did not refuse cleanly: %r" % o[:160])
    return checks[0]


image_procs = None

MUTATIONS = [
    (REL_LIB, "SPI1's base, not SPI0's", "#SPIDW_BASE = $1F00050000", "#SPIDW_BASE = $1F00054000"),
    (REL_LIB, "odd divider (no & -2)", "  d = ((#SPIDW_CLK_HZ + hz - 1) / hz + 1) & (-2)", "  d = ((#SPIDW_CLK_HZ + hz - 1) / hz + 1)"),
    (REL_LIB, "divider without Linux's +1", "  d = ((#SPIDW_CLK_HZ + hz - 1) / hz + 1) & (-2)", "  d = ((#SPIDW_CLK_HZ + hz - 1) / hz) & (-2)"),
    (REL_LIB, "CPOL and CPHA swapped", "#SPIDW_SCPH    = $40", "#SPIDW_SCPH    = $80"),
    (REL_LIB, "SER never set", "  SpiDwWr(#SPIDW_SER, 1)\n", "  SpiDwWr(#SPIDW_SER, 0)\n"),
    (REL_LIB, "CE0 and CE1 swapped", "#SPIDW_PIN_CE0  = 8", "#SPIDW_PIN_CE0  = 7"),
    (REL_LIB, "in-flight not bounded by the FIFO", "If SpiDwRd(#SPIDW_TXFLR) < spidw_fifo And (sent - got) < spidw_fifo",
     "If SpiDwRd(#SPIDW_TXFLR) < spidw_fifo"),
    (REL_LIB, "DFS32 probe ignored", "    If (cr & #SPIDW_DFS_MASK) = 0\n      spidw_dfs32 = 1", "    If cr = -99\n      spidw_dfs32 = 1"),
    (REL_LIB, "CS released before the last frame finishes", "      If (SpiDwRd(#SPIDW_SR) & #SPIDW_SR_BUSY) = 0\n", "      If 1 = 1\n"),
    (REL_LIB, "CTRLR0 written while enabled", "  SpiDwWr(#SPIDW_SSIENR, 0)\n  SpiDwWr(#SPIDW_CTRLR0, cr)",
     "  SpiDwWr(#SPIDW_SSIENR, 1)\n  SpiDwWr(#SPIDW_CTRLR0, cr)"),
    (REL_LIB, "no deadline", "      If Ticks() > deadline\n", "      If Ticks() < 0\n"),
    (REL_LIB, "CS left low after a timeout", "  SpiDwCsLevel(cs, 1)\n  SpiDwWr(#SPIDW_SER, 0)\n  SpiDwBarrier()\n  ProcedureReturn result",
     "  If result = #SPIDW_OK\n    SpiDwCsLevel(cs, 1)\n  EndIf\n  SpiDwWr(#SPIDW_SER, 0)\n  SpiDwBarrier()\n  ProcedureReturn result"),
    (REL_LIB, "data pins on FUNCSEL 4", "#SPIDW_FUNCSEL  = 0", "#SPIDW_FUNCSEL  = 4"),
    (REL_HW, "MOSI reported as MISO", "    Case #HW_SPI_MOSI\n      ProcedureReturn #SPIDW_PIN_MOSI",
     "    Case #HW_SPI_MOSI\n      ProcedureReturn #SPIDW_PIN_MISO"),
    (REL_HW, "a timeout reported as OK", "  ; TIMEOUT and NODEV: the controller did not do the transfer.\n  ProcedureReturn #HW_SPI_IO",
     "  ProcedureReturn #HW_SPI_OK"),
    (REL_BUS, "mode 4 accepted", "  If mode < 0 Or mode > 3\n", "  If mode < 0 Or mode > 4\n"),
    (REL_BUS, "chip select not checked", "  If cs < 0 Or cs >= HwSpiCsCount(bus)\n", "  If cs < 0\n"),
    (REL_BUS, "transfer allowed without open", "  If spi_open = 0\n    spi_why = \"no SPI device is open",
     "  If spi_open = 9\n    spi_why = \"no SPI device is open"),
    (REL_CMD, "xfer prints what was sent, not received", "    PutHex2(gSpiRx[i] & $FF)", "    PutHex2(gSpiTx[i] & $FF)"),
    (REL_CMD, "no capability gate", "  If RequireCap(#CAP_SPI, \"spi\", \"this board exposes no SPI bus to Anvil\") = 0\n    ProcedureReturn\n  EndIf\n  bus = HwSpiDefaultBus()",
     "  bus = HwSpiDefaultBus()"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--mutate", action="store_true")
    a = ap.parse_args()
    cc = d.compiler(a.compiler)
    top = pathlib.Path(tempfile.mkdtemp(prefix="spi-dw-"))
    try:
        try:
            n = gate(cc, {}, top / "gate")
        except d.GateFail as exc:
            print("spi_dw_check: FAIL - %s" % exc)
            return 1
        print("spi_dw_check: PASS - %d checks (three SSI variants, a hung SSI, the command, #CAP_SPI = 0)" % n)
        if a.mutate:
            if d.run_mutations("spi_dw_check", MUTATIONS,
                               lambda ov, wd: gate(cc, ov, wd), top / "mut"):
                return 1
        return 0
    finally:
        shutil.rmtree(top, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

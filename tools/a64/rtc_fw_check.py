#!/usr/bin/env python3
"""Desk gate: the Pi 5 firmware RTC - RaspberryPi4/Lib/rtc_fw.pi4 over the
shared RaspberryPi4/Lib/mailbox.pi4 transport.

The -t pi5 compiled procedures (rtc_fw.pi4 AND the real mailbox.pi4) run
under tools/a64/a64_interp.py against a modelled VideoCore that parses the
property buffer the ARM hands it, the way the firmware protocol and the
pinned Linux driver define it (raspberrypi/linux 7e030b60792d):

  drivers/rtc/rtc-rpi.c                 GET_RTC_REG $00030087,
                                        SET_RTC_REG $00038087, value
                                        u32 data[2] = { reg, value },
                                        sizeof(data) = 8, registers 0..7
  include/soc/bcm2835/raspberrypi-firmware.h
                                        request code 0, SUCCESS $80000000,
                                        ERROR $80000001, the tag header
                                        { tag, value-buffer size,
                                        request/response code }, end tag 0

So the gate checks the BYTES of every message - tag, value-buffer size,
register word, value word, end tag - not what rtc_fw.pi4 says it sends.
The mailbox register addresses are read from mailbox.pi4 (the transport is
that file's and is not under test here); a definition inside
`CompilerIf #PMF_CHIP = 2712` wins over an unconditional one, so this gate
follows the Pi 5 transport when it lands. The bus-address alias the
transport applies is stripped by the model (bit 30/31) and recorded, not
judged. Desk proof only; silicon owed.

  py -3 -B tools/a64/rtc_fw_check.py --compiler <PureMetalForge.exe> [--mutate]
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import shutil
import struct
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import pi5_desk as d                               # noqa: E402

REL_LIB = "RaspberryPi4/Lib/rtc_fw.pi4"
REL_MBX = "RaspberryPi4/Lib/mailbox.pi4"

TAG_GET = 0x00030087
TAG_SET = 0x00038087
SUCCESS = 0x80000000
ERROR = 0x80000001
REG_TIME, REG_BBAT_VOLTS = 0, 7


def chip_const(text, name):
    """The value of `name` in mailbox.pi4 for a 2712 build: a definition
    inside CompilerIf #PMF_CHIP = 2712 wins, then one outside any
    #PMF_CHIP conditional."""
    stack = []
    best = {}
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("CompilerIf"):
            m = re.match(r"CompilerIf\s+#PMF_CHIP\s*=\s*(\d+)", s)
            stack.append(("yes" if m and m.group(1) == "2712" else "no") if m else "other")
            continue
        if s.startswith("CompilerElse") and stack:
            top = stack[-1]
            stack[-1] = {"yes": "no", "no": "yes"}.get(top, top)
            continue
        if s.startswith("CompilerEndIf") and stack:
            stack.pop()
            continue
        m = re.match(r"%s\s*=\s*\$([0-9A-Fa-f]+)" % re.escape(name), s)
        if m and "no" not in stack:
            best["yes" in stack] = int(m.group(1), 16)
    if True in best:
        return best[True]
    if False in best:
        return best[False]
    d.die("%s defines no %s for a 2712 build" % (REL_MBX, name))


class VideoCore:
    """The property channel, as the firmware answers it."""

    def __init__(self, cpu, regs):
        self.cpu = cpu
        self.regs = dict(regs)
        self.pending = []
        self.messages = []           # (tag, valbytes, words in, words out)
        self.aliases = set()
        self.fault = None            # None, "error", "untagged", "short"

    def word(self, a):
        return sum(self.cpu.memory.get(a + i, 0) << (8 * i) for i in range(4))

    def put(self, a, v):
        for i in range(4):
            self.cpu.memory[a + i] = (v >> (8 * i)) & 0xFF

    def request(self, msg):
        if msg & 0xF != 8:
            d.die("mailbox write on channel %d, not the property channel 8" % (msg & 0xF))
        bus = msg & ~0xF
        self.aliases.add(bus & 0xC0000000)
        a = bus & 0x3FFFFFFF
        size, code = self.word(a), self.word(a + 4)
        if code != 0:
            d.die("request code $%X, not RPI_FIRMWARE_STATUS_REQUEST (0)" % code)
        if size < 32 or size % 4:
            d.die("buffer size %d cannot hold one 8-byte tag" % size)
        tag, vlen, rcode = self.word(a + 8), self.word(a + 12), self.word(a + 16)
        w0, w1 = self.word(a + 20), self.word(a + 24)
        if tag not in (TAG_GET, TAG_SET):
            d.die("tag $%08X is neither GET_RTC_REG nor SET_RTC_REG" % tag)
        if vlen != 8:
            d.die("value buffer %d bytes; rtc-rpi.c sends sizeof(u32[2]) = 8" % vlen)
        if rcode != 0:
            d.die("tag request code $%X, not 0" % rcode)
        if self.word(a + 28) != 0:
            d.die("no end tag after the one 8-byte value")
        rec = [tag, vlen, (w0, w1), None]
        self.messages.append(rec)
        if tag == TAG_GET:
            if w1 != 0:
                d.die("GET_RTC_REG sent value word $%X; rtc-rpi.c sends { reg, 0 }" % w1)
            out = (w0, self.regs.get(w0, 0))
        else:
            self.regs[w0] = w1
            out = (w0, w1)
        rec[3] = out
        self.put(a + 20, out[0])
        self.put(a + 24, out[1])
        if self.fault == "error":
            self.put(a + 4, ERROR)
        else:
            self.put(a + 4, SUCCESS)
        if self.fault == "untagged":
            self.put(a + 16, 0)
        elif self.fault == "short":
            self.put(a + 16, 0x80000000 | 4)
        else:
            self.put(a + 16, 0x80000000 | 8)
        self.pending.append(msg)


def build_model(m_cpu, mbx):
    vc = VideoCore(m_cpu, {REG_TIME: 1790000000, REG_BBAT_VOLTS: 3012345})
    rd, st0, wr, st1 = mbx

    def model(addr, size, value):
        if size != 4:
            d.die("mailbox access of %d bytes at $%X" % (size, addr))
        if value is None:
            if addr == st1:
                return 0                                   # never FULL
            if addr == st0:
                return 0 if vc.pending else 0x40000000     # EMPTY unless a reply
            if addr == rd:
                if not vc.pending:
                    d.die("mailbox READ with nothing pending")
                return vc.pending.pop(0)
            d.die("read of $%X, not a mailbox register" % addr)
        if addr == wr:
            vc.request(value)
            return
        d.die("write of $%X to $%X, not the mailbox write register" % (value, addr))
    return vc, model


def driver():
    return ("; rtc_fw_check driver - generated\n"
            'XIncludeFile "%s"\nXIncludeFile "%s"\n' % (REL_MBX, REL_LIB) +
            "Global gate_never.i\n"
            "If gate_never = 1\n"
            "  MailboxInit() : MailboxError() : RtcFwTime() : RtcFwSetTime(0)\n"
            "  RtcFwBatteryMicrovolts() : RtcFwReadReg(0) : RtcFwWriteReg(0, 0) : RtcFwError()\n"
            "EndIf\n")


def gate(cc, override, workdir):
    mtext = d.source(REL_MBX, override)
    mbx = tuple(chip_const(mtext, n) for n in ("#MBX_READ", "#MBX_STATUS0", "#MBX_WRITE", "#MBX_STATUS1"))
    ltext = d.source(REL_LIB, override)
    ERR = {n: d.const_in(ltext, n, REL_LIB) for n in
           ("#RTCFW_OK", "#RTCFW_ERR_MAILBOX", "#RTCFW_ERR_SHORT", "#RTCFW_ERR_ARG")}
    img, procs = d.build(cc, driver(), "rtc_fw_drv", workdir, override, [REL_MBX, REL_LIB])
    checks = [0]

    def check(ok, what):
        if not ok:
            d.die(what)
        checks[0] += 1

    box = {}
    windows = [(min(mbx) & ~0xFFF, (max(mbx) & ~0xFFF) + 0x1000)]
    m = d.Machine(img, procs, lambda a, s, v: box["model"](a, s, v), windows=windows)
    vc, box["model"] = build_model(m.cpu, mbx)
    call = lambda name, *a: m.signed(m.call(name, *a))

    check(call("MailboxInit") == 1, "MailboxInit failed (buffer above the DMA window?)")

    # --- read the time: one GET, { reg 0, 0 }, value word 1 ---------------
    t = call("RtcFwTime")
    check(t == 1790000000, "RtcFwTime returned %d, the firmware said 1790000000" % t)
    check(len(vc.messages) == 1 and vc.messages[0][0] == TAG_GET and vc.messages[0][2] == (REG_TIME, 0),
          "the time read was not one GET_RTC_REG {0, 0}: %r" % vc.messages)
    check(call("RtcFwError") == ERR["#RTCFW_OK"], "error not cleared after a good read")

    # --- set the time: one SET, { 0, value } -------------------------------
    check(call("RtcFwSetTime", 1800000123) == 1, "RtcFwSetTime refused a good time")
    check(vc.messages[-1][0] == TAG_SET and vc.messages[-1][2] == (REG_TIME, 1800000123),
          "the set was not SET_RTC_REG {0, 1800000123}: %r" % vc.messages[-1])
    check(call("RtcFwTime") == 1800000123, "time did not read back")

    # --- the unsigned top half survives -------------------------------------
    check(call("RtcFwSetTime", 0xF0000000) == 1 and call("RtcFwTime") == 0xF0000000,
          "a time with bit 31 set came back as %d" % call("RtcFwTime"))

    # --- battery voltage: register 7 -----------------------------------------
    check(call("RtcFwBatteryMicrovolts") == 3012345 and vc.messages[-1][2] == (REG_BBAT_VOLTS, 0),
          "battery voltage was not GET_RTC_REG {7, 0}")

    # --- refusals before the mailbox -----------------------------------------
    n0 = len(vc.messages)
    for bad in (-5, 0x1_0000_0000):
        check(call("RtcFwSetTime", bad) == 0 and call("RtcFwError") == ERR["#RTCFW_ERR_ARG"],
              "RtcFwSetTime(%d) was not refused as an argument" % bad)
    check(call("RtcFwReadReg", 8) == -1 and call("RtcFwReadReg", -1) == -1, "register 8/-1 accepted")
    check(len(vc.messages) == n0, "a refused request reached the firmware")

    # --- firmware faults are failures, not times ------------------------------
    for fault, err in (("error", "#RTCFW_ERR_MAILBOX"), ("untagged", "#RTCFW_ERR_MAILBOX"),
                       ("short", "#RTCFW_ERR_SHORT")):
        vc.fault = fault
        check(call("RtcFwTime") == -1, "a %s reply produced a time" % fault)
        check(call("RtcFwError") == ERR[err], "a %s reply was not reported as %s" % (fault, err))
        if fault != "short":
            check(call("RtcFwSetTime", 1800000000) == 0, "a %s reply to SET was reported as success" % fault)
    vc.fault = None
    check(call("RtcFwTime") >= 0, "the RTC did not recover after the faults")
    return checks[0], sorted(vc.aliases)


MUTATIONS = [
    (REL_LIB, "GET tag off by one", "#RTCFW_TAG_GET = $00030087", "#RTCFW_TAG_GET = $00030086"),
    (REL_LIB, "SET sent with the GET tag", "#RTCFW_TAG_SET = $00038087", "#RTCFW_TAG_SET = $00030087"),
    (REL_LIB, "TIME is register 1", "#RTCFW_REG_TIME           = 0", "#RTCFW_REG_TIME           = 1"),
    (REL_LIB, "value buffer 4 bytes", "#RTCFW_VALUE_BYTES = 8", "#RTCFW_VALUE_BYTES = 4"),
    (REL_LIB, "answer read from word 0", "  ProcedureReturn MailboxWord(1)", "  ProcedureReturn MailboxWord(0)"),
    (REL_LIB, "short answer accepted",
     "  If MailboxRespBytes() < #RTCFW_VALUE_BYTES", "  If MailboxRespBytes() < 0"),
    (REL_LIB, "SET value and register swapped",
     "  MailboxSetWord(0, reg)\n  MailboxSetWord(1, value)", "  MailboxSetWord(0, value)\n  MailboxSetWord(1, reg)"),
    (REL_LIB, "negative time sent",
     "  If reg < 0 Or reg > #RTCFW_REG_LAST Or value < 0 Or value > $FFFFFFFF",
     "  If reg < 0 Or reg > #RTCFW_REG_LAST Or value > $FFFFFFFF"),
    (REL_LIB, "failed GET still returns a value",
     "  If MailboxSend() = 0\n    rtcfw_err = #RTCFW_ERR_MAILBOX\n    ProcedureReturn -1",
     "  If MailboxSend() = 0\n    rtcfw_err = #RTCFW_ERR_MAILBOX"),
    (REL_LIB, "battery read from register 6",
     "  ProcedureReturn RtcFwReadReg(#RTCFW_REG_BBAT_VOLTS)", "  ProcedureReturn RtcFwReadReg(#RTCFW_REG_BBAT_CHG_MAX)"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--mutate", action="store_true")
    a = ap.parse_args()
    cc = d.compiler(a.compiler)
    top = pathlib.Path(tempfile.mkdtemp(prefix="rtc-fw-"))
    try:
        try:
            n, aliases = gate(cc, {}, top / "gate")
        except d.GateFail as exc:
            print("rtc_fw_check: FAIL - %s" % exc)
            return 1
        print("rtc_fw_check: PASS - %d checks (transport bus alias seen: %s)"
              % (n, ", ".join("$%08X" % x for x in aliases)))
        if a.mutate:
            if d.run_mutations("rtc_fw_check", MUTATIONS,
                               lambda ov, wd: gate(cc, ov, wd), top / "mut"):
                return 1
        return 0
    finally:
        shutil.rmtree(top, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

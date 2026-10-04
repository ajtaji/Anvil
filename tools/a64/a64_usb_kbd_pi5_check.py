#!/usr/bin/env python3
"""End-to-end desk gate: a USB keyboard on the Pi 5, from RP1's xHCI to the
monitor's KeyboardChar(), and a USB attach that cannot hang the prompt.

WHAT RUNS. The monitor's own bring-up and key path, cut as TEXT from
RaspberryPi4/Board/cursor_input.pi4 at build time - UsbEnumerate() (PCIe,
firmware handover, xHCI, the shared HID walk) and KeyboardChar() (what
RxByte asks for a typed character) - linked with the real
RaspberryPi4/Lib/pcie.pi4, gpio_rp1.pi4, xhci.pi4 and hid.pi4, built -t pi5
so every #PMF_CHIP = 2712 branch is the one that runs. Only the boot-trail
printing around them (BootStep/BootOk, the phase words, Print) is stubbed,
and HwUsbBindCore is the board's: it installs the GPIO42/43 VBUS hook, as
hw_usb.pi4 does.

THE MACHINE. tools/a64/a64_hid_check.py's HID bus model (devices, EP0 control
transfers, Configure/Evaluate/Address, stall/halt) behind the RP1 layer of
tools/a64/a64_xhci_pi5_check.py (the pcie2 block, RP1 config space, the DWC3
wrapper, the GPIO42/43 VBUS pins, and DMA that must arrive as CPU +
$10_0000_0000). Every root port is switched OFF by HCRST, so a driver that
does not power them sees nothing.

SCENARIOS
  kbd          a low-speed boot keyboard on root port 1, a SuperSpeed stick
               on port 3: enumeration succeeds, VBUS is set, and scripted key
               reports come out of KeyboardChar() as the characters a
               reference decoder in this file computes from the reports the
               device actually served.
  empty        nothing plugged in: enumeration succeeds, no keyboard,
               KeyboardChar() answers -1 at once.
  rp1-absent   the PCIe link to RP1 is down (firmware reset it): refused,
               RP1 NEVER TOUCHED (on silicon that access hangs the core).
  no-window    the inbound DMA window is missing: refused before RP1.
  never-runs   the controller never leaves Halted: refused by name.
In every scenario the program must reach its end trap, and the modelled time
spent in UsbEnumerate() is bounded - the "cannot hang the prompt" proof.

Desk proof only. Silicon owed.

  py -3 -B tools/a64/a64_usb_kbd_pi5_check.py --compiler <PureMetalForge.exe> [--no-breaks]
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import a64_hid_check as H            # noqa: E402  the HID bus model
import a64_xhci_pi5_check as P5      # noqa: E402  the RP1 layer
from a64_interp import A64, attach_symbols  # noqa: E402
from pmf_compiler import resolve_compiler   # noqa: E402

LOAD = 0x200000
REL_CURSOR = "RaspberryPi4/Board/cursor_input.pi4"
LIBS = ("RaspberryPi4/Lib/pcie.pi4", "RaspberryPi4/Lib/gpio_rp1.pi4",
        "RaspberryPi4/Lib/xhci.pi4", "RaspberryPi4/Lib/hid.pi4")
CNTFRQ = H.CNTFRQ
POLLS = 12

# Boot-protocol keyboard reports (HID 1.11 Appendix B.1): modifiers,
# reserved, six usages.  The keys and the characters they must produce
# (HID Usage Tables 10: 0x0B 'h', 0x0C 'i', 0x1E '1', 0x28 Return).
KEYS = {0x0B: ("h", "H"), 0x0C: ("i", "I"), 0x1E: ("1", "!"), 0x28: ("\r", "\r")}
SCRIPT = [H.kr(0), H.kr(0), H.kr(0, 0x0B), H.kr(0), H.kr(0, 0x0C),
          H.kr(0x02, 0x1E), H.kr(0), H.kr(0, 0x28), H.kr(0), H.kr(0),
          H.kr(0), H.kr(0), H.kr(0), H.kr(0), H.kr(0), H.kr(0)]


def ref_char(prev: bytes, cur: bytes) -> int:
    """The first key newly DOWN in cur (not in prev), as KeyboardChar
    promises: a printable or control character, or -1."""
    shift = bool(cur[0] & 0x22)
    for u in cur[2:8]:
        if u and u not in prev[2:8] and u in KEYS:
            return ord(KEYS[u][1 if shift else 0])
    return -1


class LoggingKeyboard(H.Keyboard):
    """The HID gate's low-speed boot keyboard, recording every boot report
    it serves, so the expectation is computed from what the driver was
    actually given - not from a guess about how many reports the attach
    itself reads."""

    def __init__(self):
        super().__init__(SCRIPT, bytes([1] + [0] * 8))
        self.served: list[bytes] = []

    def class_control(self, ctl, rt, req, val, idx, length, buf):
        comp, payload = super().class_control(ctl, rt, req, val, idx, length, buf)
        if rt == 0xA1 and req == 0x01 and self.protocol == 0 and comp == 1:
            self.served.append(bytes(payload))
        return comp, payload


class Rp1HidCtl(H.Ctl):
    """The HID bus behind RP1: P5.Rp1Ctl's RP1 layer on H.Ctl's bus."""

    # the RP1 layer, borrowed - one definition, in a64_xhci_pi5_check.py
    link_up = P5.Rp1Ctl.link_up
    rc_read = P5.Rp1Ctl.rc_read
    rc_write = P5.Rp1Ctl.rc_write
    dwc_read = P5.Rp1Ctl.dwc_read
    dwc_write = P5.Rp1Ctl.dwc_write
    host_mode = P5.Rp1Ctl.host_mode

    def __init__(self, cpu, topology, scenario):
        super().__init__(cpu, topology)
        self.real_cpu = cpu
        self.cpu = P5._DmaView(P5.TransMem(cpu.memory, self))
        self.scenario = scenario
        self.cfg = {0x00: P5.RP1_ID, 0x04: 0x00100002, 0x10: 0, 0x14: 0}
        self.cfg_index = None
        self.rc = {P5.PCIE_STATUS: 0x80 if scenario == "rp1-absent" else 0xB0,
                   P5.LNK_WORD: ((4 << 4 | 2) << 16),
                   0x18: 0x00010100}   # root port buses 0/1/1 - see a64_xhci_pi5_check
        if scenario != "no-window":
            self.rc[P5.rc_bar(1)] = 21
            self.rc[P5.rc_bar(1) + 4] = 0x10
            self.rc[P5.ubus_bar(1)] = 1
            self.rc[P5.ubus_bar(1) + 4] = 0
        self.dwc = {P5.GSNPSID: P5.GSNPSID_330B, P5.GHWPARAMS0: 1,
                    P5.GCTL: 0x2000, P5.GUCTL1: 0, P5.GUSB2PHYCFG0: 0x2440,
                    P5.GUSB3PIPECTL0: 0x010E0002 | P5.U3_SUSPHY, P5.DCTL: 0}
        self.csft_reads = 0
        self.gpio = {a: 0x1F for a in P5.VBUS_CTRL.values()}
        self.gpio.update({a: 0x80 for a in P5.VBUS_PAD.values()})
        self.rp1_touched = False
        self.erstba_hi = None

    def reg_read(self, off):
        if off == 0x04:
            return P5.HCS1_RP1                       # three root ports
        v = super().reg_read(off)
        if off == H.R_USBSTS and self.scenario == "never-runs" and self.reg[H.R_USBCMD] & H.CMD_RUN:
            v |= H.STS_HALT
            self.reg[H.R_USBSTS] = v
        return v

    def reg_write(self, off, value):
        if off >= H.OP and not self.host_mode():
            self.bad(f"xHCI register ${off:X} written before the DWC3 core was in host mode")
        # ERSTBA, high dword first (dwc3 write-64-hi-lo-quirk): the table
        # base commits on the LOW write.
        if off == H.R_ERSTBA + 4:
            self.erstba_hi = value & 0xFFFFFFFF
            return
        if off == H.R_ERSTBA:
            if self.erstba_hi is None:
                self.bad("ERSTBA low dword written before its high dword")
                return
            self.wide[H.R_ERSTBA] = (self.erstba_hi << 32) | (value & 0xFFFFFFFF)
            self.erstba_hi = None
            self._wide_written(H.R_ERSTBA)
            return
        super().reg_write(off, value)
        if off == H.R_USBCMD and value & H.CMD_RESET:
            for n in self.port:
                self.port[n] = 0                     # PPC: switches off after HCRST

    def _wide_written(self, base):
        v = self.wide[base]
        ptr = v & ~0x3F if base != H.R_ERSTBA else v & ~0xF
        if base in (H.R_DCBAAP, H.R_CRCR, H.R_ERSTBA) and not (
                P5.DMA_OFF <= ptr < P5.DMA_OFF + P5.DMA_WIN):
            self.bad(f"a 64-bit pointer register holds ${ptr:X}, not an RP1 bus address")
        super()._wide_written(base)


def install(cpu, ctl):
    raw_load = A64.load.__get__(cpu, A64)
    raw_store = A64.store.__get__(cpu, A64)
    orig_step = A64.step.__get__(cpu, A64)

    def host_off(addr, size):
        if size != 4:
            ctl.bad(f"a {size}-byte RP1 USB register access")
            return None
        if not ctl.link_up():
            ctl.bad("RP1 USB register accessed with the link down - on silicon "
                    "this hangs the core")
            return None
        ctl.rp1_touched = True
        return addr - P5.HOST0

    def load(addr, size):
        cpu.align_guard(addr, size, False)
        if P5.RC_BASE <= addr < P5.RC_BASE + P5.RC_SIZE:
            return ctl.rc_read(addr - P5.RC_BASE)
        if P5.HOST0 <= addr < P5.HOST0 + P5.HOST_SIZE:
            off = host_off(addr, size)
            if off is None:
                return 0
            if off in P5.DWC3_REGS:
                return ctl.dwc_read(off)
            if H.R_PORTS <= off < H.R_PORTS + 3 * 0x10 and (off - H.R_PORTS) % 0x10 == 0:
                return ctl.port_status((off - H.R_PORTS) // 0x10 + 1)
            return ctl.reg_read(off)
        if addr in P5.VBUS_REGS:
            if not ctl.link_up():
                ctl.bad("RP1 GPIO read with the link down")
            return ctl.gpio[addr]
        if P5.RP1_CPU <= addr < P5.RP1_CPU + P5.RP1_SIZE:
            ctl.bad(f"load from RP1 ${addr - P5.RP1_CPU:X}")
            return 0
        return raw_load(addr, size)

    def store(addr, value, size):
        cpu.align_guard(addr, size, True)
        if P5.RC_BASE <= addr < P5.RC_BASE + P5.RC_SIZE:
            ctl.rc_write(addr - P5.RC_BASE, value & 0xFFFFFFFF)
            return
        if P5.HOST0 <= addr < P5.HOST0 + P5.HOST_SIZE:
            off = host_off(addr, size)
            if off is None:
                return
            if off in P5.DWC3_REGS:
                ctl.dwc_write(off, value)
                return
            if H.DBOFF <= off < H.DBOFF + 0x400:
                ctl.doorbell((off - H.DBOFF) // 4, value & 0xFFFFFFFF)
                return
            ctl.reg_write(off, value)
            return
        if addr in P5.VBUS_REGS:
            if not ctl.link_up():
                ctl.bad("RP1 GPIO written with the link down")
            ctl.gpio[addr] = value & 0xFFFFFFFF
            return
        if P5.RP1_CPU <= addr < P5.RP1_CPU + P5.RP1_SIZE:
            ctl.bad(f"store to RP1 ${addr - P5.RP1_CPU:X}")
            return
        raw_store(addr, value, size)

    def step():
        ins = cpu.fetch(cpu.pc)
        if (ins & 0xFFFFFFE0) == 0xD53BE000:
            cpu.put(ins & 31, CNTFRQ, 1)
            cpu.pc += 4
            return
        if (ins & 0xFFFFFFE0) == 0xD53BE020:
            ctl.ticks += H.TICK_STEP
            cpu.put(ins & 31, ctl.ticks, 1)
            cpu.pc += 4
            return
        orig_step()

    cpu.load, cpu.store, cpu.step = load, store, step


def cut(text: str, header: str) -> str:
    m = re.search(r"(?ms)^" + re.escape(header) + r".*?^EndProcedure\n", text)
    if not m:
        raise SystemExit(f"{REL_CURSOR} no longer has {header!r}")
    return m.group(0)


PROGRAM = r'''; a64_usb_kbd_pi5_check driver - generated from the tree, never committed.
XIncludeFile "RaspberryPi4/Lib/pcie.pi4"
XIncludeFile "RaspberryPi4/Lib/gpio_rp1.pi4"
XIncludeFile "RaspberryPi4/Lib/xhci.pi4"
XIncludeFile "RaspberryPi4/Lib/hid.pi4"

Global gUsbEnum.i = 0
Global gBootLog.i = 0
Global gKbdH.i = 0
#RES_MAX = 64
Global Dim res.i[#RES_MAX]
Global nres.i = 0
Procedure Chk(v.i)
  If nres < #RES_MAX
    res[nres] = v
  EndIf
  nres = nres + 1
EndProcedure

; ---- the boot trail around the bring-up, silent here ----
Procedure BootStep(*name)
EndProcedure
Procedure BootOk(*name)
EndProcedure
; Print() lowers to str_print_at; the boot log is off here (gBootLog = 0).
Procedure str_print_at(p.i)
EndProcedure
Procedure PrintNl()
EndProcedure
Procedure PciePhaseWord()
EndProcedure
Procedure UsbTraceWord()
EndProcedure
Procedure UsbPhaseWord()
EndProcedure
Procedure PcieTellMemory()
  PcieSetMemoryBytes($40000000)
EndProcedure
Procedure.i MscSetupCurrent()
  ProcedureReturn 0
EndProcedure

; ---- the board's HwUsbBindCore on 2712: the VBUS hook, as hw_usb.pi4 ----
Procedure GateVbus()
  If Rp1FuncSelSet(#RP1_GPIO_USB_VBUS_EN, #RP1_FUNCSEL_VBUS1) <> 0 And Rp1FuncSelSet(#RP1_GPIO_USB_OC_N, #RP1_FUNCSEL_VBUS1) <> 0
    XhciSetVbusState(1)
  Else
    XhciSetVbusState(0)
  EndIf
EndProcedure
Procedure HwUsbBindCore()
  XhciSetVbusHook(@GateVbus)
EndProcedure

; ---- cut from RaspberryPi4/Board/cursor_input.pi4 ----
%(CUT)s
; ---- end cut ----

Procedure Main()
  Define t0.i
  Define i.i
  t0 = xh_Ticks()
  Chk(UsbEnumerate())
  Chk((xh_Ticks() - t0) / (xh_TickHz() / 1000))
  Chk(PcieError())
  Chk(XhciLastError())
  gKbdH = HidFind(#HID_PROTO_KEYBOARD)
  Chk(Bool(gKbdH <> 0))
  Chk(XhciVbusState())
  i = 0
  While i < %(POLLS)d
    Chk(KeyboardChar())
    i = i + 1
  Wend
  t0 = xh_Ticks()
  Chk(UsbEnumerate())
  Chk((xh_Ticks() - t0) / (xh_TickHz() / 1000))
  Chk(nres)
EndProcedure

Main()
'''

# Bounds on the modelled time UsbEnumerate() may take.  A present keyboard
# costs the 100 ms root-port power-good wait plus debounce and attach; a
# refusal must be quick, and the idempotent second call nearly free.
BOUND_MS = {"kbd": 3000, "empty": 1000, "rp1-absent": 50, "no-window": 50, "never-runs": 1000}
SCENARIOS = tuple(BOUND_MS)


def topology_for(scenario):
    if scenario == "kbd":
        return {1: LoggingKeyboard(), 3: H.MassStorage()}
    return {}


# THE 2712 GUARD. Until the owner flips #CAP_USB on the Pi 5, cursor_input.pi4
# opens UsbEnumerate() with a CompilerIf #PMF_CHIP = 2712 block that returns
# 0 before anything is touched (stage 1 made it a boot killer). This gate
# proves the path THE FLIP ENABLES, so it removes exactly that block - and
# says so - and refuses if the block has changed shape.
GUARD = re.compile(r"  CompilerIf #PMF_CHIP = 2712\n(?:  ;[^\n]*\n)*  ProcedureReturn 0\n  CompilerEndIf\n")
GUARD_SEEN = [False]


def without_guard(proc_text: str) -> str:
    n = len(GUARD.findall(proc_text))
    if n > 1:
        raise SystemExit("UsbEnumerate has more than one 2712 guard")
    if "#PMF_CHIP = 2712" in proc_text and n == 0:
        raise SystemExit("UsbEnumerate's 2712 guard changed shape - re-aim the gate")
    GUARD_SEEN[0] = n == 1
    return GUARD.sub("", proc_text, count=1)


def build(compiler, work, root, cursor_text):
    text = PROGRAM.replace("%(CUT)s", without_guard(cut(cursor_text, "Procedure.i UsbEnumerate()"))
                           + "\n" + cut(cursor_text, "Procedure.i KeyboardChar()"))
    text = text.replace("%(POLLS)d", str(POLLS))
    src = work / "usbkbd5.pi4"
    src.write_text(text, encoding="utf-8")
    img = work / "usbkbd5.img"
    r = subprocess.run([compiler, "--compile", str(src), "-t", "pi5", "--load-addr",
                        hex(LOAD), "-s", "-o", str(img)], cwd=root,
                       env=dict(os.environ, PMF_ROOT=str(root)), text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode or "pmfc: OK" not in r.stdout or "target BCM2712" not in r.stdout:
        raise SystemExit("build failed:\n" + r.stdout[-3000:])
    return img


def run(img, scenario, budget=60_000_000):
    sym = H.load_syms(img)
    cpu = A64(pc=LOAD)
    for i, b in enumerate(img.read_bytes()):
        cpu.memory[LOAD + i] = b
    attach_symbols(cpu, img, LOAD)
    topo = topology_for(scenario)
    ctl = Rp1HidCtl(cpu, topo, scenario)
    install(cpu, ctl)
    trap = LOAD + sym["_a64_end_trap"]
    done = False
    for _ in range(budget):
        if cpu.pc == trap:
            done = True
            break
        cpu.step()
    nres = cpu.load(sym["global_nres"], 8)
    got = [cpu.load(sym["global_res"] + 8 * i, 8) for i in range(min(nres, 64))]
    got = [v - (1 << 64) if v >= 1 << 63 else v for v in got]
    fails = []
    if not done:
        fails.append(f"the program never reached its end trap in {budget} steps - IT HUNG")
        return fails
    kb = topo.get(1)
    head = got[:6]
    polls = got[6:6 + POLLS]
    tail = got[6 + POLLS:]
    enum_ok, ms, perr, xerr, has_kbd, vbus = head
    if ms > BOUND_MS[scenario]:
        fails.append(f"UsbEnumerate took {ms} ms of modelled time, bound {BOUND_MS[scenario]}")
    if scenario == "kbd":
        # XhciLastError is 0 after a walk that met the SuperSpeed stick. It
        # was 30 (#XHCI_ERR_ARG) until 2026-09-27: HidAttach handed the
        # stick's bMaxPacketSize0 exponent (9) to XhciSetEp0MaxPacket.
        if [enum_ok, perr, xerr, has_kbd, vbus] != [1, 0, 0, 1, 1]:
            fails.append(f"kbd: enumerate/pcie/xhci/keyboard/vbus = "
                         f"{[enum_ok, perr, xerr, has_kbd, vbus]}, want [1, 0, 0, 1, 1]")
        served = kb.served
        if len(served) < POLLS:
            fails.append(f"kbd: the keyboard served {len(served)} boot reports, "
                         f"fewer than the {POLLS} polls")
        else:
            mine = served[-POLLS:]
            before = served[-POLLS - 1] if len(served) > POLLS else H.kr(0)
            exp = []
            prev = before
            for r in mine:
                exp.append(ref_char(prev, r))
                prev = r
            if polls != exp:
                fails.append(f"kbd: KeyboardChar gave {polls}, the served reports decode to {exp}")
            typed = "".join(chr(c) for c in polls if c > 0)
            if typed != "hi!\r":
                fails.append(f"kbd: the monitor would have read {typed!r}, want 'hi!\\r'")
        if not ctl.host_mode():
            fails.append("kbd: the DWC3 core never reached host mode")
        for pin in (42, 43):
            if ctl.gpio[P5.VBUS_CTRL[pin]] & 0x1F != 2:
                fails.append(f"kbd: GPIO{pin} not muxed to vbus1")
    elif scenario == "empty":
        if [enum_ok, perr, xerr, has_kbd] != [1, 0, 0, 0]:
            fails.append(f"empty: {[enum_ok, perr, xerr, has_kbd]}, want [1, 0, 0, 0]")
        if polls != [-1] * POLLS:
            fails.append(f"empty: KeyboardChar with no keyboard gave {polls}")
    else:
        want_perr = {"rp1-absent": -4, "no-window": -16, "never-runs": 0}[scenario]
        if enum_ok != 0 or perr != want_perr or has_kbd != 0:
            fails.append(f"{scenario}: enumerate {enum_ok}, pcie error {perr} "
                         f"(want 0, {want_perr}), keyboard {has_kbd}")
        if scenario == "never-runs" and xerr != 17:
            fails.append(f"never-runs: xhci error {xerr}, want 17 (HCHalted never cleared)")
        if scenario in ("rp1-absent", "no-window") and ctl.rp1_touched:
            fails.append(f"{scenario}: RP1 was touched")
        if polls != [-1] * POLLS:
            fails.append(f"{scenario}: KeyboardChar gave {polls}")
    again, ms2, count = tail
    if again != enum_ok or ms2 > BOUND_MS[scenario]:
        fails.append(f"a second UsbEnumerate returned {again} in {ms2} ms")
    if count != 6 + POLLS + 2:
        fails.append(f"check count {count}")
    fails += ["model refused: " + v for v in ctl.violations]
    return fails


# The mutants reach through the whole path: each must turn some scenario red.
MUTANTS = {
    "no-root-port-power": ("RaspberryPi4/Lib/xhci.pi4", "    If xh_PowerRootPorts() = 0\n", "    If 1 = 0\n"),
    "no-link-check": ("RaspberryPi4/Lib/pcie.pi4", "    If PcieLinkUp() = 0\n      pcie_err = #PCIE_ERR_LINK\n",
                      "    If 0 = 1\n      pcie_err = #PCIE_ERR_LINK\n"),
    "event-not-back-translated": ("RaspberryPi4/Lib/xhci.pi4",
                                  "        xh_evTrb = xh_DmaCpu((xh_evF1 << 32) | (xh_evF0 & $FFFFFFFF))",
                                  "        xh_evTrb = (xh_evF1 << 32) | (xh_evF0 & $FFFFFFFF)"),
    "vbus-hook-not-called": ("RaspberryPi4/Lib/xhci.pi4", "    If *xh_vbusHook <> 0\n      xh_vbusHook()\n    EndIf\n", "\n"),
    # (Dropping KeyboardChar's HidKeyDown test was tried: HidKeyCharAt
    # answers 0 for a release, so that line is redundant here, not
    # load-bearing. The event index is.)
    "first-event-skipped": (REL_CURSOR, "  For i = 0 To HidKeyEventCount() - 1\n",
                            "  For i = 1 To HidKeyEventCount() - 1\n"),
}
MUTANT_SCENARIO = {"no-link-check": "rp1-absent"}


def make_mutant(name, work):
    rel, old, new = MUTANTS[name]
    tree = work / ("m_" + name)
    for r in LIBS + (REL_CURSOR,):
        text = (ROOT / r).read_bytes().decode("utf-8").replace("\r\n", "\n")
        if r == rel:
            n = text.count(old)
            if n != 1:
                raise SystemExit(f"mutant {name}: anchor missing in {rel}")
            text = text.replace(old, new, 1)
        dst = tree / r
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(text, encoding="utf-8")
    intr = ROOT / "RaspberryPi4" / "Intrinsics"
    (tree / "RaspberryPi4" / "Intrinsics").mkdir(parents=True, exist_ok=True)
    for f in intr.iterdir():
        if f.is_file():
            (tree / "RaspberryPi4" / "Intrinsics" / f.name).write_bytes(f.read_bytes())
    return tree


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--no-breaks", action="store_true")
    a = ap.parse_args(argv[1:])
    if not a.compiler:
        ap.error("pass --compiler or set PMF_COMPILER")
    cc = str(pathlib.Path(resolve_compiler(a.compiler)).resolve())
    cursor = (ROOT / REL_CURSOR).read_bytes().decode("utf-8").replace("\r\n", "\n")
    with tempfile.TemporaryDirectory(prefix="usb-kbd-pi5-") as tmp:
        work = pathlib.Path(tmp)
        img = build(cc, work, ROOT, cursor)
        if GUARD_SEEN[0]:
            print("NOTE: cursor_input.pi4's UsbEnumerate still opens with the 2712 guard "
                  "(#CAP_USB = 0 on the Pi 5); this run proves the path with it removed")
        red = 0
        for sc in SCENARIOS:
            f = run(img, sc)
            if f:
                red += 1
                print(f"FAIL {sc}:")
                for x in f:
                    print("   " + x)
            else:
                print(f"PASS {sc}")
        if red:
            print(f"FAILED: {red} scenario(s)")
            return 1
        if a.no_breaks:
            return 0
        print("mutants - each must go RED:")
        weak = []
        for name in MUTANTS:
            tree = make_mutant(name, work)
            try:
                mimg = build(cc, tree, tree, (tree / REL_CURSOR).read_text(encoding="utf-8"))
            except SystemExit:
                print(f"  {name:28s} refused at compile time (red)")
                continue
            f = run(mimg, MUTANT_SCENARIO.get(name, "kbd"), 20_000_000)
            if f:
                print(f"  {name:28s} red  e.g. {f[0][:90]}")
            else:
                print(f"  {name:28s} *** STILL PASSED ***")
                weak.append(name)
        if weak:
            print("GATE IS WEAK: " + ", ".join(weak))
            return 1
        print(f"PASS: {len(SCENARIOS)} scenarios; {len(MUTANTS)} of {len(MUTANTS)} mutants red.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

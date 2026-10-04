#!/usr/bin/env python3
"""Desk gate: the Pi 5 adopts the inbound DMA window the firmware left on
pcie2, at whatever PCIe base it chose, and RP1's DMA uses that base.

THE SILICON STATE (Pi 5, build 215 / Anvil f385c7b, pciex4_reset=0,
read by pi5PcieInboundDump.pi4 on 2026-09-27):
  PCIE_STATUS $0003E0B0 (RC mode, PHYLINKUP, DL_ACTIVE)  LNKSTA $90420000
  MISC_CTRL $A8003000 (SCB_ACCESS_EN on)  PCIE_CTRL $4  VENDOR_REG1 0
  UBUS_CTRL/TIMEOUT $00080000  WIN0 LO/HI 0/0, BASE_LIMIT $03F00000,
  BASE_HI/LIMIT_HI $1F/$1F
  RC_BAR1 0/0   RC_BAR2 $00000015/0   RC_BAR3 0/0   RC_BAR4..10 0
  UBUS_BAR1 1/0   UBUS_BAR2 1/0   UBUS_BAR3 0/0   UBUS_BAR4..10 0
So the only enabled inbound window is BAR2: 64 GiB at PCIe 0 -> ARM 0 - a
ZERO DMA offset, where Linux's dma-ranges put ARM 0 at PCIe $10_0000_0000.
Build 215 looked only for the Linux window and refused with -16.

WHAT RUNS. The payloads that go to the board, built from the tree as the
silicon test builds them (-t pi5 --entry-returns, load $400000, stack
$7E00000):
  RaspberryPi4/Examples/Diagnostics/pi5PcieInboundDump.pi4  - read only.
  RaspberryPi4/Examples/Diagnostics/pi5PcieDmaProof.pi4     - the real
      pcie.pi4 and xhci.pi4: PcieInit (adopts the window, writes no pcie2
      register), PcieEnumerate, XhciInit on RP1's usbhost0, then two No-Op
      commands. A No-Op's TRB is READ by the controller and its completion
      event WRITTEN, both by DMA - the proof RP1 reaches ARM memory.
The DMA-proof payload runs on a64_xhci_pi5_check's RP1 model (pcie2 block,
RP1 config space, the DWC3 wrapper, the xHCI), whose controller-side memory
is ONLY reachable at ARM + the window's base: a pointer handed over at any
other base is refused as the silent DMA-into-nothing it is on silicon. Any
pcie2 register write is refused too.

SCENARIOS
  dump        the read-only payload on the silicon registers: no write, no
              RP1 access, and its report is exactly those registers.
  silicon     the silicon registers: window adopted from BAR2 at base 0,
              RP1 enumerated, the xHCI up, both No-Ops complete with Success,
              the link still up, no pcie2 write.
  linux       the Linux layout (BAR1 at PCIe $10_0000_0000): adopted at that
              base, the same proof - the DMA base follows the window.
  no-remap    as silicon but UBUS_BAR2's ACCESS_EN is off: refused with -16
              before RP1 is touched.
  buses-elsewhere  the root port's bus numbers name bus 2: refused with -24,
              nothing written over them.
  rp1-bar-elsewhere  RP1's BARs do not decode at PCIe 0, where the outbound
              window points: refused with -25, nothing reassigned.
THE ROOT PORT'S BUS NUMBERS. Measured 0 (pi5PcieCfgDiag.pi4): every config
read of bus 1 came back all ones. In "silicon" the model routes a bus-1
read to RP1 only once the root port's secondary bus is 1, and allows the
one write that makes it so (0/1/1 into a root port that had none).

Desk proof only. Silicon owed (the DMA-proof payload IS the silicon test).

  py -3 -B tools/a64/a64_pcie_pi5_inbound_check.py --compiler <PureMetalForge.exe>
"""
from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import a64_xhci_pi5_check as P5       # noqa: E402  the RP1 + xHCI model
from a64_interp import A64            # noqa: E402
from pmf_compiler import resolve_compiler  # noqa: E402

LOAD = 0x400000
STACK = 0x7E00000
SENTINEL = 0x0DEAD000
OUT = 0x00600000
RC_BASE, RC_SIZE = P5.RC_BASE, P5.RC_SIZE
REL_LIB = "RaspberryPi4/Lib/pcie.pi4"
REL_PROOF = "RaspberryPi4/Examples/Diagnostics/pi5PcieDmaProof.pi4"
REL_DUMP = "RaspberryPi4/Examples/Diagnostics/pi5PcieInboundDump.pi4"
LIBS = (REL_LIB, "RaspberryPi4/Lib/gpio_rp1.pi4", "RaspberryPi4/Lib/xhci.pi4")
RP1_ID = 0x00011DE4


def rc_bar(n):
    return 0x402C + 8 * (n - 1) if n <= 3 else 0x40D4 + 8 * (n - 4)


def ubus_bar(n):
    return 0x40AC + 8 * (n - 1) if n <= 3 else 0x410C + 8 * (n - 4)


# The measured registers, verbatim (see the docstring).
SILICON = {0x4068: 0x0003E0B0, 0x00BC: 0x90420000, 0x4008: 0xA8003000, 0x4064: 0x00000004,
           0x0188: 0x00000000, 0x40A4: 0x00080000, 0x40A8: 0x00080000, 0x400C: 0, 0x4010: 0,
           0x4070: 0x03F00000, 0x4080: 0x0000001F, 0x4084: 0x0000001F}
for _n in range(1, 11):
    SILICON[rc_bar(_n)] = 0
    SILICON[rc_bar(_n) + 4] = 0
    SILICON[ubus_bar(_n)] = 0
    SILICON[ubus_bar(_n) + 4] = 0
SILICON[rc_bar(2)] = 0x00000015
SILICON[ubus_bar(1)] = 1
SILICON[ubus_bar(2)] = 1


def registers(scenario):
    r = dict(SILICON)
    if scenario == "linux":
        r[rc_bar(2)] = 0
        r[ubus_bar(2)] = 0
        r[rc_bar(1)] = 21
        r[rc_bar(1) + 4] = 0x10
        r[ubus_bar(1)] = 1
    if scenario == "no-remap":
        r[ubus_bar(2)] = 0
    # The root port's bus numbers ($18). MEASURED 0 (pi5PcieCfgDiag.pi4,
    # 2026-09-27: 14E4:2712, command $0146, $18 = 0, bus 1 read all ones).
    # The Linux layout has them 0/1/1; "buses-elsewhere" names bus 2.
    r[0x18] = 0x00010100 if scenario == "linux" else 0
    if scenario == "buses-elsewhere":
        r[0x18] = 0x00020200
    return r


class FirmwareCtl(P5.Rp1Ctl):
    """a64_xhci_pi5_check's RP1 model, plus the root port's bus numbers: a
    configuration read of bus 1 through EXT_CFG_INDEX/DATA reaches RP1 only
    while the root port's SECONDARY bus is 1 (a Type 1 request becomes Type 0
    on the secondary bus - PCI-to-PCI Bridge 1.2 3.2.5.3); otherwise it reads
    all ones, as measured. The one pcie2 write allowed beyond the model's own
    is the bus numbers 0/1/1 into a root port that had none."""

    buses_written = 0

    def rc_read(self, off):
        if P5.CFG_DATA <= off < P5.CFG_DATA + 0x1000:
            bus = ((self.cfg_index or 0) >> 20) & 0xFF
            if bus != (self.rc.get(0x18, 0) >> 8) & 0xFF:
                return 0xFFFFFFFF
        return super().rc_read(off)

    def rc_write(self, off, v):
        if off == 0x18:
            old = self.rc.get(0x18, 0)
            if old & 0xFFFFFF == 0 and v == (old & 0xFF000000) | 0x00010100:
                self.rc[0x18] = v
                self.buses_written += 1
                return
            self.bad(f"the root port's bus numbers written ${old:08X} -> ${v:08X} - only 0/1/1 into "
                     f"a root port that has none")
            return
        super().rc_write(off, v)


def build(compiler, root, rel, work, tag):
    img = work / f"{tag}.img"
    r = subprocess.run([compiler, "--compile", rel, "-t", "pi5", "--load-addr", hex(LOAD),
                        "--stack-addr", hex(STACK), "--entry-returns", "-o", str(img), "-s"],
                       cwd=root, env=dict(os.environ, PMF_ROOT=str(root)), text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode or "pmfc: OK" not in r.stdout or "target BCM2712" not in r.stdout:
        raise SystemExit(f"build of {rel} failed:\n" + r.stdout[-3000:])
    return img


def enter(cpu, img):
    for i, b in enumerate(img.read_bytes()):
        cpu.memory[LOAD + i] = b
    cpu.sp = 0x0E200000
    cpu.put(30, SENTINEL, 1)


def finish(cpu, budget):
    for _ in range(budget):
        if cpu.pc == SENTINEL:
            return True
        cpu.step()
    return False


def report(cpu, raw_load, words):
    return [raw_load(OUT + 4 * i, 4) for i in range(words)]


def s32(v):
    return v - (1 << 32) if v >= 1 << 31 else v


# -------------------------------------------------------------------- dump
def run_dump(img):
    fails = []
    regs = registers("silicon")
    writes, rp1 = [], []
    cpu = A64(pc=LOAD)
    enter(cpu, img)
    raw_load = A64.load.__get__(cpu, A64)
    raw_store = A64.store.__get__(cpu, A64)

    def load(addr, size):
        if RC_BASE <= addr < RC_BASE + RC_SIZE:
            off = addr - RC_BASE
            if 0x8000 <= off < 0x9000:
                rp1.append(off)
            if size != 4:
                fails.append(f"dump: a {size}-byte pcie2 read")
            return regs.get(off, 0)
        if addr >= 0x1_0000_0000:
            fails.append(f"dump: a read at ${addr:X}")
            return 0
        return raw_load(addr, size)

    def store(addr, value, size):
        if RC_BASE <= addr < RC_BASE + RC_SIZE or addr >= 0x1_0000_0000:
            writes.append((addr, value))
            return
        raw_store(addr, value, size)

    cpu.load, cpu.store = load, store
    if not finish(cpu, 2_000_000):
        return ["dump: the payload never returned - IT HUNG"]
    w = report(cpu, raw_load, 2 + 2 * 56)
    if cpu.x[0] != OUT or w[0] != 0x31444350:
        return [f"dump: no report (x0 ${cpu.x[0]:X}, magic ${w[0]:X})"]
    n = w[1]
    if n != 52:
        fails.append(f"dump: {n} registers, want 52")
    seen = set()
    for i in range(min(n, 56)):
        off, val = w[2 + 2 * i], w[3 + 2 * i]
        seen.add(off)
        if regs.get(off, 0) != val:
            fails.append(f"dump: +${off:04X} reported ${val:08X}, holds ${regs.get(off, 0):08X}")
    for need in SILICON:
        if need not in seen:
            fails.append(f"dump: +${need:04X} missing from the report")
    if writes or rp1:
        fails.append(f"dump: wrote {writes}, read RP1 config {len(rp1)} times - must be read-only")
    return fails


# ------------------------------------------------------------------- proof
WANT = {
    "silicon": dict(init=1, err=0, bar=2, base=0, size_hi=0x10, buses0=0, en=1, enerr=0,
                    buses1=0x00010100, written=1, rp1id=0x00011DE4, rp1bar=0, xinit=1, xerr=0,
                    noop1=1, comp=1, noop2=1, link=1),
    "linux": dict(init=1, err=0, bar=1, base=0x10_0000_0000, size_hi=0x10, buses0=0x00010100,
                  en=1, enerr=0, buses1=0x00010100, written=0, rp1id=0x00011DE4, rp1bar=0,
                  xinit=1, xerr=0, noop1=1, comp=1, noop2=1, link=1),
    "no-remap": dict(init=0, err=-16, bar=0, base=0, size_hi=0, buses0=0, en=0, enerr=0,
                     buses1=0, written=0, rp1id=0, rp1bar=0, xinit=0, xerr=0,
                     noop1=0, comp=0, noop2=0, link=1),
    "buses-elsewhere": dict(init=1, err=0, bar=2, base=0, size_hi=0x10, buses0=0x00020200,
                            en=0, enerr=-24, buses1=0x00020200, written=0, rp1id=0xFFFFFFFF,
                            rp1bar=0xFFFFFFFF, xinit=0, xerr=0, noop1=0, comp=0, noop2=0, link=1),
    "rp1-bar-elsewhere": dict(init=1, err=0, bar=2, base=0, size_hi=0x10, buses0=0, en=0,
                              enerr=-25, buses1=0x00010100, written=1, rp1id=0x00011DE4,
                              rp1bar=0xFFFFFFFF, xinit=0, xerr=0, noop1=0, comp=0, noop2=0, link=1),
}


def run_proof(img, scenario, budget=60_000_000):
    base = WANT[scenario]["base"]
    saved = P5.DMA_OFF
    P5.DMA_OFF = base            # the controller reaches ARM memory ONLY at this base
    try:
        cpu = A64(pc=LOAD)
        enter(cpu, img)
        ctl = FirmwareCtl(cpu, "healthy")
        ctl.rc = registers(scenario)
        if scenario == "rp1-bar-elsewhere":
            ctl.cfg[0x10] = 0x10000000          # neither BAR at PCIe 0
            ctl.cfg[0x14] = 0x10000000
        cpu.raw_load = A64.load.__get__(cpu, A64)
        cpu.raw_store = A64.store.__get__(cpu, A64)
        P5.install(cpu, ctl)
        if not finish(cpu, budget):
            return [f"{scenario}: the payload never returned - IT HUNG"] + \
                   [f"{scenario}: model: {v}" for v in ctl.violations]
        w = report(cpu, cpu.raw_load, 0x70 // 4)
    finally:
        P5.DMA_OFF = saved
    fails = []
    if cpu.x[0] != OUT or w[0] != 0x32584350:
        return [f"{scenario}: no report (x0 ${cpu.x[0]:X}, magic ${w[0]:X})"]
    rp1bar = 0xFFFFFFFF if w[0x3C // 4] == 0xFFFFFFFF else w[0x3C // 4]
    got = dict(init=w[1], err=s32(w[2]), bar=w[3], base=w[4] | (w[5] << 32), size_hi=w[6],
               buses0=w[7], en=w[8], enerr=s32(w[9]), buses1=w[10], written=w[11],
               rp1id=w[12], rp1bar=rp1bar, xinit=w[17], xerr=w[18], noop1=w[19], comp=w[20],
               noop2=w[21], link=w[24])
    if got != WANT[scenario]:
        fails.append(f"{scenario}: report {got}, want {WANT[scenario]}")
    if WANT[scenario]["written"] != ctl.buses_written:
        fails.append(f"{scenario}: the bus numbers were written {ctl.buses_written} times, "
                     f"want {WANT[scenario]['written']}")
    if WANT[scenario]["noop1"]:
        cmd_cpu, dma = w[25], w[26] | (w[27] << 32)
        if dma != cmd_cpu + base:
            fails.append(f"{scenario}: the command ring at ${cmd_cpu:X} was handed over as ${dma:X}, "
                         f"want ${cmd_cpu + base:X} (ARM + the adopted base)")
        if w[22] & 0x4:
            fails.append(f"{scenario}: USBSTS ${w[22]:X} has HSE - a DMA failed")
        if not w[23] & 0x4:
            fails.append(f"{scenario}: RP1's Bus Master Enable is off after XhciInit (${w[23]:X})")
    if scenario == "no-remap" and ctl.rp1_touched:
        fails.append("no-remap: RP1's USB block was touched after a refusal")
    if ctl.rc.get(0x4068) != 0x0003E0B0:
        fails.append(f"{scenario}: PCIE_STATUS is ${ctl.rc.get(0x4068, 0):X} at the end")
    return fails + [f"{scenario}: model: {v}" for v in ctl.violations]


MUTANTS = {
    # The old rule: only the Linux window is a window.
    "linux-window-only": ("      If bytes > 0 And (base & (bytes - 1)) = 0\n",
                          "      If bytes > 0 And base = #PCIE_DMA_BUS\n"),
    # The window is found, but DMA is still aimed at the Linux base.
    "wrong-dma-offset": ("    ProcedureReturn physAddr + pcie_dmaBase\n",
                         "    ProcedureReturn physAddr + #PCIE_DMA_BUS\n"),
    # The remap's ACCESS_EN is not checked.
    "remap-not-checked": ("        If (rlo & 1) <> 0 And (rlo & $FFFFF000) = 0 And rhi = 0\n",
                          "        If (rlo & $FFFFF000) = 0 And rhi = 0\n"),
    # The BAR size decoded one step small (32 GiB for code 21).
    "wrong-bar-size": ("      ProcedureReturn 1 << (code + 15)\n",
                       "      ProcedureReturn 1 << (code + 14)\n"),
    # The bus numbers are never written: RP1 cannot be read (the silicon bug).
    "no-bus-numbers": ("    If pcie_Buses() = 0\n      ProcedureReturn 0\n    EndIf\n", ""),
    # Numbers the firmware set for another bus are written over.
    "buses-renumbered": ("    If (v & $FFFFFF) <> 0\n      pcie_err = #PCIE_ERR_BUSNUM\n",
                         "    If 0 = 1\n      pcie_err = #PCIE_ERR_BUSNUM\n"),
    # RP1's BAR is not checked against the outbound window.
    "rp1-bar-unchecked": ("      If v >= 0 And (v & 1) = 0 And (v & $FFFFFFF0) = #PCIE_OUT_BUS\n",
                          "      If v >= 0 And (v & 1) = 0\n"),
    # "Fixing" it by resetting the link: PERST asserted on the live link.
    "link-reset": ("    pcie_Phase(#PCIE_PH_INBOUND)\n",
                   "    pcie_Poke($4064, 0)\n    pcie_Phase(#PCIE_PH_INBOUND)\n"),
}
MUTANT_SCENARIO = {"linux-window-only": "silicon", "wrong-dma-offset": "silicon",
                   "remap-not-checked": "no-remap", "wrong-bar-size": "silicon",
                   "link-reset": "silicon", "no-bus-numbers": "silicon",
                   "buses-renumbered": "buses-elsewhere", "rp1-bar-unchecked": "rp1-bar-elsewhere"}


def mutant_tree(name, work):
    old, new = MUTANTS[name]
    tree = work / ("m_" + name)
    for rel in LIBS + (REL_PROOF,):
        dst = tree / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        text = (ROOT / rel).read_bytes().decode("utf-8").replace("\r\n", "\n")
        if rel == REL_LIB:
            if text.count(old) != 1:
                raise SystemExit(f"mutant {name}: anchor not found once in {rel} - re-aim")
            text = text.replace(old, new, 1)
        dst.write_text(text, encoding="utf-8")
    shutil.copytree(ROOT / "RaspberryPi4" / "Intrinsics", tree / "RaspberryPi4" / "Intrinsics")
    return tree


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    a = ap.parse_args(argv[1:])
    if not a.compiler:
        ap.error("pass --compiler or set PMF_COMPILER")
    cc = str(pathlib.Path(resolve_compiler(a.compiler)).resolve())
    red = 0
    with tempfile.TemporaryDirectory(prefix="pcie-pi5-inbound-") as tmp:
        work = pathlib.Path(tmp)
        dump = build(cc, ROOT, REL_DUMP, work, "dump")
        proof = build(cc, ROOT, REL_PROOF, work, "proof")
        results = [("dump", run_dump(dump))] + [(sc, run_proof(proof, sc)) for sc in WANT]
        for sc, f in results:
            print(("FAIL " if f else "PASS ") + sc)
            for x in f:
                print("   " + x)
            red += bool(f)
        if red:
            print(f"FAILED: {red} scenario(s)")
            return 1
        print("mutants - each must go RED:")
        weak = []
        for name in MUTANTS:
            tree = mutant_tree(name, work)
            mimg = build(cc, tree, REL_PROOF, work, "m_" + name)
            f = run_proof(mimg, MUTANT_SCENARIO[name], 30_000_000)
            if f:
                print(f"  {name:20s} red  e.g. {f[0][:110]}")
            else:
                print(f"  {name:20s} *** STILL PASSED ***")
                weak.append(name)
        if weak:
            print("GATE IS WEAK: " + ", ".join(weak))
            return 1
    print(f"PASS: {len(results)} scenarios; {len(MUTANTS)} of {len(MUTANTS)} mutants red.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

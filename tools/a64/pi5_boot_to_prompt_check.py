#!/usr/bin/env python3
"""pi5_boot_to_prompt_check.py - the Pi 5 card image, from its first instruction to `pmf>`.

The closest thing to the bench boot at the desk. tools/pi5_card_build.py
builds ANVIL5.IMG (caches on) and ANVIL5.NOC (caches off) from a commit;
each is loaded at $8_0000, where the Pi 5 firmware loads kernel=, and
entered at its first instruction, at EL3,
with x0 = $2EFE_C600 holding the pinned bcm2712-rpi-5-b.dtb - what our EL3
stub hands over - and run under tools/a64/a64_interp.py until the monitor
prints its prompt.

EVERY DEVICE ACCESS LANDS IN A NAMED MODEL or the run fails naming it:

  RP1 UART0            the console; text captured
  BCM2712 UART10       the JST debug port; must carry the same text (the tee)
  mailbox              property channel; answered tags: board revision
                       (Pi 5 8 GB), clocks, temperature, display count 0,
                       MAC, RTC; any other tag is answered as the firmware
                       answers an unknown one (no response bit) and listed
  GIC-400              distributor/CPU interface identity per DDI0471B, and
                       registers that read back what was written
  PM                   the watchdog block (a register file)
  SD                   pi5_sd_save_check's BCM2712 SDHCI + an SDHC card with
                       a FAT32 volume (config.txt, ANVIL5.IMG) - or no card
  pcie2 + RP1 xHCI     a64_usb_kbd_pi5_check's model, nothing plugged in
  RP1 GEM + PHY        a64_gem_pi5_check's model, no cable
  pcie1 (NVMe port)    RESCAL already done by the firmware, link never trains
  RP1 clocks, GPIO banks, pads, SYS_RIO, I2C, PWM
                       register files (read back what was written; no
                       device behind them - the touch panel and fan are absent)

and the run fails on any access in the BCM2711 range ($FC00_0000..) or on a
$DEAD base (a switched-off block). The cache is not modelled: the
interpreter accepts SCTLR and the maintenance operations and ignores them,
so ANVIL5.IMG and ANVIL5.NOC differ here only in the path they take.

Asserted, per image and scenario: the prompt appears; the banner and the
boot lines appear in their order; UART10 carries the same bytes as UART0;
no unmodelled or forbidden access; model time (54 MHz counter, 128 ticks per
instruction - slower than the A76, so an over-estimate) under BOUND_S.

Scenarios: absent (card in, nothing else attached), rp1-down (the PCIe
link to RP1 down: RP1 accesses are listed - on silicon each one hangs the
core), nocard (the SD slot empty), wrongload (the image loaded at $20_0000,
the old link address, as a firmware that honoured a stale kernel_address
would: the monitor must refuse in a sentence and halt before its stack or
boot records are touched - 2026-09-27, the first full boot died when the
map and the load address disagreed).

THE LOAD ADDRESS IS THE FIRMWARE'S: $80000, whatever config.txt says - the
Pi 5 firmware ignored kernel_address=0x200000 with our arm stub (measured
2026-09-27, the load guard's own sentence). It is never read from the image.
Every store into the running image's code is a failure, with the writer
named.

    py -3 tools/a64/pi5_boot_to_prompt_check.py --compiler PureMetalForge.exe [--commit REV]
"""
from __future__ import annotations

import argparse
import bisect
import collections
import os
import pathlib
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import a64_gem_pi5_check as G                            # noqa: E402
import a64_usb_kbd_pi5_check as K                        # noqa: E402
import pi5_card_build as CB                              # noqa: E402
import pi5_sd_save_check as SD                           # noqa: E402
import pi5_storage_order_check as SO                     # noqa: E402
from a64_interp import A64, attach_symbols               # noqa: E402

LOAD = 0x80000
DTB_AT = 0x2EFEC600
DTB_FILE = pathlib.Path(r"C:\Users\ajtaj\Desktop\CompilerEmbedded\Raspberry Pi 5\Boot staging\bcm2712-rpi-5-b.dtb")
CONFIG_FILE = DTB_FILE.parent / "config.txt"
FIRMWARE_LOAD = 0x80000      # measured 2026-09-27, kernel_address or not (docstring)
WRONG_LOAD = 0x200000        # the `wrongload` scenario: the old link address
FORCED_LOAD = None
TICKS = 128
CNTFRQ = 54_000_000
BOUND_S = 120
STEP_LIMIT = 80_000_000
UART0 = 0x1F00030000
UART10 = 0x107D001000
MBX = 0x107C013880
GICD, GICC = 0x107FFF9000, 0x107FFFA000
PM = 0x107D200000
PCIE1_RC, PCIE1_RC_SIZE = 0x1000110000, 0x9310
PCIE1_RESCAL = 0x1000119500
BRCM_RESET = 0x1001504300
RP1 = 0x1F00000000
BOARD_REV = 0xD04170                 # Raspberry Pi 5 Model B rev 1.0, 8 GB
MAC = bytes.fromhex("2ccf67a1b2c3")

# RP1 blocks with no behavioural model here: (name, base offset, size, reset values)
# (a fifth element names bits that clear themselves once written)
RP1_FILES = [
    ("RP1 clocks_main", 0x018000, 0x8000, {}),
    ("RP1 I2C0..6", 0x070000, 0x1C000, {}),
    ("RP1 PWM0", 0x098000, 0x4000, {}),
    # pwm@9c000 GLOBAL_CTRL bit 31 SET_UPDATE is self-clearing (rp1_pwm.pi4, pwm-rp1.c)
    ("RP1 PWM1", 0x09C000, 0x4000, {}, {0x00: 0x80000000}),
    ("RP1 io_bank0..2", 0x0D0000, 0xC000, {}),
    ("RP1 sys_rio0..2", 0x0E0000, 0xC000, {}),
    ("RP1 pads_bank0..2", 0x0F0000, 0xC000, {}),
]
# BCM2712 register files: (name, base, size, reset values)
SOC_FILES = [
    ("GIC-400 distributor", GICD, 0x1000, {0x004: 0x0000040B, 0x008: 0x0200143B, 0xFE8: 0x2B}),
    ("GIC-400 CPU interface", GICC, 0x2000, {0x0FC: 0x0202143B}),
    ("PM (watchdog)", PM, 0x1000, {}),
    ("pcie1 root complex", PCIE1_RC, PCIE1_RC_SIZE, {0x4068: 0x80}),
    ("pcie1 RESCAL", PCIE1_RESCAL, 0x10, {0x8: 1}),
    ("brcmstb reset controller", BRCM_RESET, 0x100, {}),
]
MARKERS = ["PureMetal Forge - Anvil, the Raspberry Pi 5 Model B monitor",
           "The processor is a Cortex-A76 in AArch64 at exception level 3",
           "Bringing up the board",
           "wired:",
           "Wi-Fi is not joined at boot",
           "pmf>"]


class Fail(Exception):
    pass


class RegFile:
    def __init__(self, name, base, size, reset, selfclear=None):
        self.name, self.base, self.size = name, base, size
        self.r = dict(reset)
        self.selfclear = dict(selfclear or {})

    def __call__(self, off, value):
        if value is None:
            return self.r.get(off & ~3, 0)
        self.r[off & ~3] = value & ~self.selfclear.get(off & ~3, 0)
        return 0


class Mailbox:
    def __init__(self, mem):
        self.mem = mem
        self.pending = []
        self.unknown = collections.Counter()
        self.tags = collections.Counter()
        self.clock = {3: 1_500_000_000}

    def u32(self, a):
        return sum(self.mem.get(a + i, 0) << (8 * i) for i in range(4))

    def put(self, a, v):
        for i in range(4):
            self.mem[a + i] = (v >> (8 * i)) & 0xFF

    def answer(self, tag, a, vl):
        v0, v1 = self.u32(a), self.u32(a + 4)
        if tag == 0x00010002:
            self.put(a, BOARD_REV); return 4
        if tag == 0x00010003:
            for i, b in enumerate(MAC):
                self.mem[a + i] = b
            return 6
        if tag == 0x00010005:                                  # ARM memory: base, size
            self.put(a, 0); self.put(a + 4, 0x3F800000); return 8
        if tag in (0x00030002, 0x00030047):                   # clock rate / measured
            self.put(a + 4, self.clock.get(v0, 100_000_000)); return 8
        if tag == 0x00030004:                                  # max clock
            self.put(a + 4, 2_400_000_000 if v0 == 3 else self.clock.get(v0, 100_000_000)); return 8
        if tag == 0x00030007:                                  # min clock
            self.put(a + 4, 1_500_000_000 if v0 == 3 else self.clock.get(v0, 100_000_000)); return 8
        if tag == 0x00038002:                                  # set clock
            self.clock[v0] = v1; self.put(a + 4, v1); return 8
        if tag == 0x00030006:
            self.put(a + 4, 51_000); return 8
        if tag == 0x0003000A:
            self.put(a + 4, 85_000); return 8
        if tag == 0x00040013:                                  # number of displays
            self.put(a, 0); return 4
        if tag == 0x00030087:                                  # RTC register: time 0 (unset)
            self.put(a + 4, 0); return 8
        if tag == 0x00030064:                                  # reboot flags
            self.put(a, 0); return 4
        return None

    def __call__(self, off, value):
        if value is None:
            if off == 0x18:
                return 0 if self.pending else 0x40000000
            if off == 0x38:
                return 0
            if off == 0x00 and self.pending:
                return self.pending.pop(0)
            raise Fail("the mailbox was read at +$%X with nothing pending" % off)
        if off != 0x20 or (value & 0xF) != 8:
            raise Fail("the mailbox was written at +$%X with $%X" % (off, value))
        a = value & ~0xF
        size, o = self.u32(a), 8
        while o < size:
            tag = self.u32(a + o)
            if tag == 0:
                break
            vl = self.u32(a + o + 4)
            self.tags[tag] += 1
            n = self.answer(tag, a + o + 12, vl)
            if n is None:
                self.unknown[tag] += 1
                self.put(a + o + 8, 0)
            else:
                self.put(a + o + 8, 0x80000000 | n)
            o += 12 + ((vl + 3) & ~3)
        self.put(a + 4, 0x80000000)
        self.pending.append(value)
        return 0


def dbg_procs(img):
    starts = []
    for line in open(str(img) + ".dbg", encoding="utf-8", errors="replace"):
        f = line.rstrip("\n").split("|")
        if len(f) >= 3 and f[0] == "1" and f[1].isdigit():
            starts.append((LOAD + int(f[1]), f[2]))
    starts.sort()
    return [s for s, _ in starts], [n for _, n in starts]


def scenario_config(scen: str) -> bytes:
    """config.txt on the modelled card: the vault's staged one, which
    tools/pi5_card_build.py would accept (no kernel_address line)."""
    text = CONFIG_FILE.read_bytes()
    if CB.config_forbidden(text.decode("utf-8", "replace")):
        raise Fail("the staged config.txt (%s) has a line pi5_card_build refuses: %s"
                   % (CONFIG_FILE, CB.config_forbidden(text.decode("utf-8", "replace"))))
    return text


def boot(img: pathlib.Path, scen: str):
    global LOAD
    cfg = scenario_config(scen)
    LOAD = FORCED_LOAD if FORCED_LOAD is not None else (WRONG_LOAD if scen == "wrongload" else FIRMWARE_LOAD)
    starts, names = dbg_procs(img)

    def proc(pc):
        i = bisect.bisect_right(starts, pc) - 1
        return names[i] if i >= 0 else "(entry)"

    cpu = A64()
    for i, b in enumerate(img.read_bytes()):
        cpu.memory[LOAD + i] = b
    for i, b in enumerate(DTB_FILE.read_bytes()):
        cpu.memory[DTB_AT + i] = b
    attach_symbols(cpu, img, LOAD)
    cpu.enable_system_registers(el=3, preset={0xD51E1000: 0x30C50830, 0xD5190020: (2 << 24) | (4 << 3) | 3,
                                              0xD5190000: (7 << 13) | (3 << 3) | 2, 0xD51B4220: 0x3C0})
    cpu.cntpct_per_instruction = TICKS
    # the USB model (pcie2 root complex, RP1 xHCI, VBUS) owns the loads and
    # stores it knows; everything it would flag is decided here first
    usb = K.Rp1HidCtl(cpu, {}, "rp1-absent" if scen == "rp1-down" else "healthy")
    K.install(cpu, usb)
    usb_load, usb_store = cpu.load, cpu.store
    k = G.constants(None) if not G.DEFAULT_SOURCES.exists() else G.constants(G.DEFAULT_SOURCES)
    gem = G.Board(cpu, "rp1-down" if scen == "rp1-down" else "no-cable", k)
    if scen == "nocard":
        sd = SO.NoCardHost({})
    else:
        sd = SD.SdHost(SD.make_card(b"\0" * 3000, cfg))
    mbx = Mailbox(cpu.memory)
    files = [RegFile(f[0], RP1 + f[1], *f[2:]) for f in RP1_FILES] + [RegFile(*f) for f in SOC_FILES]
    files.sort(key=lambda f: f.base)
    fbases = [f.base for f in files]
    tx0, tx10 = bytearray(), bytearray()
    bad = collections.Counter()
    rp1_down_touch = collections.Counter()
    gem_lo, gem_hi = k["GEM"], k["GEM"] + 0x4000

    def find_file(addr):
        i = bisect.bisect_right(fbases, addr) - 1
        if i >= 0 and addr < files[i].base + files[i].size:
            return files[i]
        return None

    def dev(addr, size, value):
        """None = not ours (fall to the USB model)."""
        if 0xFC000000 <= addr < 0x1_0000_0000:
            bad["a BCM2711-range address $%X in %s" % (addr, proc(cpu.pc))] += 1
            return 0
        if (addr >> 32) == 0xDEAD:
            bad["a $DEAD base $%X in %s" % (addr, proc(cpu.pc))] += 1
            return 0
        if scen == "rp1-down" and RP1 <= addr < RP1 + 0x410000:
            rp1_down_touch[proc(cpu.pc)] += 1
        if UART0 <= addr < UART0 + 0x1000:
            off = addr - UART0
            if value is None:
                return 0x90 if off == 0x18 else 0
            if off == 0:
                tx0.append(value & 0xFF)
            return 0
        if UART10 <= addr < UART10 + 0x1000:
            off = addr - UART10
            if value is None:
                return 0x90 if off == 0x18 else 0
            if off == 0:
                tx10.append(value & 0xFF)
            return 0
        if MBX <= addr < MBX + 0x40:
            return mbx(addr - MBX, value)
        if SD.SD <= addr < SD.SD + 0x260 or SD.CFG <= addr < SD.CFG + 0x200:
            return sd(addr, size, value)
        if gem_lo <= addr < gem_hi or G.ETH_CFG <= addr < G.ETH_CFG + 0x2C or addr in (gem.ctrl_addr, gem.pad_addr) \
                or (gem.rio <= addr < gem.rio + 0x4000 and (addr & 0xFFF) in (0, 4, 8)):
            return gem.mmio(addr, size, value)
        if addr in K.P5.VBUS_REGS or K.P5.RC_BASE <= addr < K.P5.RC_BASE + K.P5.RC_SIZE \
                or K.P5.HOST0 <= addr < K.P5.HOST0 + K.P5.HOST_SIZE:
            return None
        f = find_file(addr)
        if f is not None:
            return f(addr - f.base, value)
        bad["an unmodelled device address $%X (%s) in %s" % (addr, "read" if value is None else "write",
                                                             proc(cpu.pc))] += 1
        return 0

    def load(addr, sz):
        if addr >= 0xFC000000:
            cpu.align_guard(addr, sz, False)
            v = dev(addr, sz, None)
            if v is not None:
                return v & ((1 << (8 * sz)) - 1)
        return usb_load(addr, sz)

    code_lo, code_hi = LOAD, starts[-1] + 0x1000
    code_writes = collections.Counter()

    def store(addr, value, sz):
        if code_lo <= addr < code_hi:
            # the running image's own code: nothing may write it
            code_writes["$%X (image +$%X, %s) written by %s" % (addr, addr - LOAD, proc(addr), proc(cpu.pc))] += 1
        if addr >= 0xFC000000:
            cpu.align_guard(addr, sz, True)
            if dev(addr, sz, value & ((1 << (8 * sz)) - 1)) is not None:
                return
        usb_store(addr, value, sz)

    cpu.load, cpu.store = load, store
    plain = A64.step.__get__(cpu, A64)
    # sp as the stub leaves it is not relied on: the image's preamble sets
    # its own before the first push. $08000000 is outside every placement.
    cpu.pc, cpu.x[0], cpu.sp = LOAD, DTB_AT, 0x08000000
    n = 0
    t0 = time.time()
    stop = None
    while n < STEP_LIMIT:
        pc = cpu.pc
        ins = cpu.fetch(pc)
        if pc == LOAD + 0x28 and ins == 0xEB0A013F and cpu.x[9] < cpu.x[10]:
            # the image's own BSS zero loop (cmp x9, x10 / str xzr / add / b):
            # RAM here is a dict whose missing keys read 0 and nothing has been
            # stored in that range yet, so its whole effect is x9 = x10.
            left = (cpu.x[10] - cpu.x[9] + 7) // 8
            cpu.x[9] += 8 * left
            cpu.cntpct += TICKS * 4 * left
            n += 4 * left
            continue
        if (ins & 0xFFFFFFE0) == 0xD53BE000:                   # mrs Xt, cntfrq_el0
            cpu.x[ins & 31] = CNTFRQ
            cpu.pc += 4
            cpu.cntpct += TICKS
            n += 1
            continue
        if ins == 0xD503205F and scen == "wrongload":               # wfe: the monitor stopped itself
            stop = "halted (wfe) in %s" % proc(pc)
            break
        try:
            plain()
        except Exception as e:                                 # noqa: BLE001
            stop = "the interpreter stopped in %s at $%X: %s" % (proc(pc), pc, str(e)[:300])
            break
        n += 1
        # the tee writes UART10 and UART0 a byte apart: stop when every live
        # port has the prompt (UART0 is dead with RP1's link down)
        if b"pmf>" in tx10[-6:] and (scen == "rp1-down" or b"pmf>" in tx0[-6:]):
            break
    return {"load": LOAD, "steps": n, "secs": time.time() - t0, "model_s": cpu.cntpct / CNTFRQ, "uart0": bytes(tx0),
            "uart10": bytes(tx10), "bad": bad, "stop": stop, "pc": proc(cpu.pc), "mbx_unknown": mbx.unknown,
            "usb_bad": list(usb.violations), "gem_bad": list(gem.bad), "rp1_down_touch": rp1_down_touch,
            "code_writes": code_writes}


def judge_wrongload(label, r, check):
    text = r["uart0"].decode("ascii", "replace")
    check(r["load"] == WRONG_LOAD, "%s wrongload: the image loaded at $%X" % (label, r["load"]))
    want = "Anvil was loaded at %08X and is built to run at %08X" % (WRONG_LOAD, FIRMWARE_LOAD)
    check(want in text and "stops now" in text and "pmf>" not in text,
          "%s wrongload: refused in a sentence on the UART (%r), no prompt" % (label, want))
    check((r["stop"] or "").startswith("halted"), "%s wrongload: the monitor halted itself (%s)"
          % (label, r["stop"] or r["pc"]))
    check(not r["code_writes"], "%s wrongload: nothing wrote the running image's code before it stopped%s"
          % (label, "" if not r["code_writes"] else " - " + "; ".join(list(r["code_writes"])[:4])))
    return text


def judge(label, scen, r, check):
    if scen == "wrongload":
        return judge_wrongload(label, r, check)
    # with RP1's link down UART0 (an RP1 block) is not a console; UART10 is
    text = (r["uart10"] if scen == "rp1-down" else r["uart0"]).decode("ascii", "replace")
    got_prompt = "pmf>" in text
    check(got_prompt, "%s %s: the prompt after %d steps, %.1f s of model time (%s)"
          % (label, scen, r["steps"], r["model_s"], r["stop"] or "last in " + r["pc"]))
    pos, ok, missing = -1, True, []
    for m in MARKERS:
        p = text.find(m, pos + 1)
        if p < 0:
            ok = False
            missing.append(m)
        else:
            pos = p
    check(ok, "%s %s: the banner and boot lines in order%s" % (label, scen, "" if ok else " - missing/out of order: %s" % missing))
    if scen != "rp1-down":
        check(r["uart0"] == r["uart10"], "%s %s: UART10 carries the same %d bytes as UART0 (%d)"
              % (label, scen, len(r["uart0"]), len(r["uart10"])))
    else:
        check(len(r["uart10"]) > 0 and b"pmf>" in r["uart10"], "%s rp1-down: the prompt reaches UART10" % label)
    check(not r["code_writes"], "%s %s: nothing writes the running image's code%s" % (label, scen, "" if not r["code_writes"] else ":\n        " + "\n        ".join("%dx %s" % (v, k) for k, v in sorted(r["code_writes"].items(), key=lambda kv: kv[0])[:int(os.environ.get("PI5BOOT_LIST", "12"))])))
    allbad = [k for k in r["bad"]] + ["USB model: " + v for v in r["usb_bad"]] + ["GEM model: " + v for v in r["gem_bad"]]
    check(not allbad, "%s %s: every access in a model, none forbidden%s" % (label, scen, "" if not allbad else ":\n        " + "\n        ".join(allbad[:12])))
    check(r["model_s"] <= BOUND_S, "%s %s: %.1f s of model time (bound %d s)" % (label, scen, r["model_s"], BOUND_S))
    if r["mbx_unknown"]:
        print("        (mailbox tags answered as unknown: %s)" % ", ".join("$%08X" % t for t in sorted(r["mbx_unknown"])))
    if scen == "rp1-down" and r["rp1_down_touch"]:
        print("        (RP1 touched with its link down, by: %s)" % ", ".join(sorted(r["rp1_down_touch"])))
    return text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--commit", default="HEAD")
    ap.add_argument("--images", type=pathlib.Path, help="a directory already holding ANVIL5.IMG/.NOC (+ .dbg/.sym)")
    ap.add_argument("--scenarios", default="absent,rp1-down,nocard,wrongload")
    ap.add_argument("--transcripts", type=pathlib.Path)
    ap.add_argument("--load", type=lambda s: int(s, 0), help="override the load address (every scenario)")
    a = ap.parse_args()
    globals()["FORCED_LOAD"] = a.load
    print("  load address: %s" % ("$%X, given" % a.load if a.load is not None else
                                  "$%X, the firmware's (wrongload: $%X)" % (FIRMWARE_LOAD, WRONG_LOAD)))
    fails = []

    def check(ok, what):
        print("  %s  %s" % ("ok  " if ok else "FAIL", what))
        if not ok:
            fails.append(what)

    with tempfile.TemporaryDirectory(prefix="pi5boot_") as td:
        d = a.images
        if d is None:
            if not a.compiler:
                raise SystemExit("pass --compiler (or --images)")
            d = pathlib.Path(td)
            CB.build(a.commit, a.compiler, d)
        for name in ("ANVIL5.IMG", "ANVIL5.NOC"):
            for scen in a.scenarios.split(","):
                try:
                    r = boot(d / name, scen)
                except Fail as e:
                    check(False, "%s %s: %s" % (name, scen, e))
                    continue
                text = judge(name, scen, r, check)
                if a.transcripts:
                    a.transcripts.mkdir(parents=True, exist_ok=True)
                    (a.transcripts / ("%s.%s.txt" % (name, scen))).write_text(text, encoding="utf-8")
    if fails:
        print("pi5_boot_to_prompt_check: FAIL - %d check(s)" % len(fails))
        return 1
    print("pi5_boot_to_prompt_check: PASS - ANVIL5.IMG and ANVIL5.NOC boot to the prompt in every scenario, "
          "every access modelled. Desk only: silicon owed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Desk gate for RaspberryPi5/Tests/v3d71_ident_probe.pi5 (Pi 5 V3D 7.1, stage 1).

Builds the probe with `--compile ... -t pi5 --entry-returns`, runs the
image in tools/a64/a64_interp.py, and answers every MMIO access from a
hand-written model of the BCM2712 PM block, the V3D SMS, hub and core0, and
the RP1 UART0.  The model is written from the same pinned sources the probe
cites (vault "Raspberry Pi 5/Sources/", kernel 7e030b60...):

  PM GRAFX power-on    bcm2835-power.c:214-281  (runs on BCM2712: no rpivid_asb)
  V3D subdomain        bcm2835-power.c:284-337, 380-383 (PM_GRAFX_2712, no ASB)
  PM password          bcm2835-power.c:102, 111-112
  SMS resume / reset   v3d_power.c:11-28, v3d_gem.c:113-127, v3d_drv.h:295-299
  IDENT                v3d_regs.h:35-60, 209-238; v3d_drv.c:418-424
  addresses            bcm2712-rpi-5-b.dtb (/axi/v3d@2000000, /soc/watchdog@7d200000)
  MIDR                 arch/arm64/include/asm/cputype.h:26-41, 54, 69, 75

WHAT IT PROVES: the order of the writes (GRAFX inrush ramp with POWUP, all
four steps as the kernel does; ISPOW; MEMREP then MRDONE; ISFUNC; V3DRSTN in
$304; SMS TEE_CS then REE_CS), that every PM write carries the password and
touches only $10C and $304, that no V3D register (SMS, hub, core) is read
before its domain is up, that the probe refuses by name when IDENT is not
$117, on a Cortex-A72, when POWOK or MRDONE never come, and when the SMS
never settles - and that each refusal leaves the undo writes the kernel does.

WHAT IT CANNOT PROVE: that the silicon behaves like the model.  Whether a
read of a powered-down V3D hangs or returns zero, how many reads POWOK takes,
whether the SMS answers from EL3: all are the model's assumptions (strict in
the safe direction).  The board answers those; see the vault plan's open
questions.

Run:  py -3 -B tools/a64/a64_v3d71_ident_check.py --compiler <PureMetalForge.exe>
      (a private build needs PMF_ALLOW_UNTRACKED_COMPILER=1 for that run)
      --mutate also builds deliberately broken copies of the probe and
      demands that each one fails.
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
PROBE = ROOT / "RaspberryPi5" / "Tests" / "v3d71_ident_probe.pi5"

sys.path.insert(0, str(HERE))
from a64_interp import A64  # noqa: E402
sys.path.insert(0, str(ROOT / "tools"))
from pmf_compiler import resolve_compiler  # noqa: E402

LOAD = 0x400000
STACK = 0x3000000
LOADER_LR = 0xDEADBEE0
CNTFRQ = 54_000_000

# Addresses, re-derived from the DTB values (not copied from the probe).
SOC_PARENT = 0x10_0000_0000            # /soc@107c000000 ranges child 0 -> $10_0000_0000
PM = SOC_PARENT + 0x7D200000           # watchdog@7d200000 reg
PM_SIZE = 0x308
HUB = (0x10 << 32) | 0x02000000        # /axi v3d reg "hub"   (axi ranges identity)
CORE0 = (0x10 << 32) | 0x02008000      # reg "core0"
SMS = (0x10 << 32) | 0x02030800        # reg "sms"
UART = 0x1F_0003_0000                  # RP1 UART0 (firmware-printed, boot log)
MMIO_FLOOR = 0x10_0000_0000

PM_GRAFX, PM_GRAFX_2712 = 0x10C, 0x304
POWUP, POWOK, ISPOW, MEMREP, MRDONE, ISFUNC, V3DRSTN = 1, 2, 4, 8, 0x10, 0x20, 0x40
INRUSH_SHIFT, INRUSH_MASK = 13, 3 << 13
PASSWORD = 0x5A000000
SMS_REE, SMS_TEE = 0x000, 0x400
SMS_CLEAR_POWER_OFF = 1 << 29
SMS_IDLE, SMS_ISO_RESET, SMS_RESETTING, SMS_POWER_OFF_STATE = 0x0, 0xA, 0xB, 0xD

MIDR_A76 = 0x414FD0B1    # implementer $41, part $D0B (cputype.h:54,75); variant/rev illustrative
MIDR_A72 = 0x410FD083    # part $D08 (cputype.h:69); the Pi 4's value per a64_interp.py


class Hang(SystemExit):
    pass


class Model:
    """PM + V3D + UART.  Strict: an access the silicon might hang on stops
    the run with a name instead of returning something plausible."""

    def __init__(self, *, grafx0=0, g2712_0=0, powok_at=1, powok_never=False,
                 mrdone_never=False, sms_resume_reads=3, sms_resume_stuck=False,
                 sms_reset_reads=3, sms_reset_stuck=False,
                 ident1=0x000F0117, core_ident0=0x07443344, core_ident1=0x81BF4341,
                 ident3=0x00000C00):
        self.grafx = grafx0
        self.g2712 = g2712_0
        self.powok_at = powok_at
        self.powok_never = powok_never
        self.mrdone_never = mrdone_never
        self.sms_state = SMS_POWER_OFF_STATE
        self.sms_resume_reads = sms_resume_reads
        self.sms_resume_stuck = sms_resume_stuck
        self.sms_reset_reads = sms_reset_reads
        self.sms_reset_stuck = sms_reset_stuck
        self.sms_countdown = 0
        self.sms_resumed = False
        self.sms_reset_done = False
        self.ident1 = ident1
        self.core_ident0 = core_ident0
        self.core_ident1 = core_ident1
        self.ident3 = ident3
        self.events: list[tuple] = []
        self.unpassworded = 0
        self.uart = bytearray()
        self.mmio_writes = 0

    # ---- PM
    def grafx_value(self) -> int:
        v = self.grafx
        if v & POWUP and not self.powok_never and \
                ((v & INRUSH_MASK) >> INRUSH_SHIFT) >= self.powok_at:
            v |= POWOK
        if v & MEMREP and not self.mrdone_never:
            v |= MRDONE
        return v

    def pm_read(self, off: int) -> int:
        if off == PM_GRAFX:
            return self.grafx_value()
        if off == PM_GRAFX_2712:
            return self.g2712
        raise SystemExit(f"a64_v3d71_ident_check: PM read at +${off:X}, which the probe "
                         "has no business reading")

    def pm_write(self, off: int, v: int, where: str) -> None:
        if off not in (PM_GRAFX, PM_GRAFX_2712):
            raise SystemExit(f"a64_v3d71_ident_check: PM WRITE at +${off:X} (${v:08X}). "
                             "Only $10C and $304 may be written: this block also holds "
                             f"PM_RSTC and PM_WDOG, which reset the SoC.\n  at {where}")
        if (v >> 24) != 0x5A:
            self.unpassworded += 1
            self.events.append(("pm-discarded", off, v))
            return                           # the hardware discards it silently
        v &= 0x00FFFFFF
        if off == PM_GRAFX:
            self.grafx = v & ~(POWOK | MRDONE)
        else:
            self.g2712 = v
        self.events.append(("pm", off, v))

    def domain_up(self) -> bool:
        g = self.grafx_value()
        need = POWUP | POWOK | ISPOW | ISFUNC
        return (g & need) == need and bool(self.g2712 & V3DRSTN)

    # ---- SMS
    def sms_read(self, off: int, where: str) -> int:
        if not self.domain_up():
            raise Hang("a64_v3d71_ident_check: SMS READ while the V3D domain is down "
                       f"(GRAFX ${self.grafx_value():X}, $304 ${self.g2712:X}). On silicon "
                       f"this may hang the bus.\n  at {where}")
        if self.sms_countdown > 0:
            self.sms_countdown -= 1
            if self.sms_countdown == 0:
                if self.sms_state == SMS_POWER_OFF_STATE and not self.sms_resume_stuck:
                    self.sms_state = SMS_IDLE
                    self.sms_resumed = True
                elif self.sms_state == SMS_RESETTING and not self.sms_reset_stuck:
                    self.sms_state = SMS_IDLE
                    self.sms_reset_done = True
        if off in (SMS_REE, SMS_TEE):
            return self.sms_state
        raise SystemExit(f"a64_v3d71_ident_check: SMS read at +${off:X}")

    def sms_write(self, off: int, v: int, where: str) -> None:
        if not self.domain_up():
            raise Hang(f"a64_v3d71_ident_check: SMS WRITE while the V3D domain is down\n  at {where}")
        self.events.append(("sms", off, v))
        if off == SMS_TEE and v == SMS_CLEAR_POWER_OFF:
            self.sms_countdown = self.sms_resume_reads
            if self.sms_resume_stuck:
                self.sms_countdown = 10 ** 12
        elif off == SMS_REE and (v & 0xF) == 4:
            if not self.sms_resumed:
                raise SystemExit("a64_v3d71_ident_check: SMS reset requested before the "
                                 "SMS was resumed (v3d_power.c:17-25 resumes first)")
            self.sms_state = SMS_RESETTING
            self.sms_countdown = self.sms_reset_reads
            if self.sms_reset_stuck:
                self.sms_countdown = 10 ** 12
        else:
            raise SystemExit(f"a64_v3d71_ident_check: unexpected SMS write +${off:X} = ${v:08X}")

    # ---- hub / core
    def v3d_ready(self) -> bool:
        return self.domain_up() and self.sms_resumed and self.sms_reset_done

    def hub_read(self, off: int, where: str) -> int:
        if not self.v3d_ready():
            raise Hang(f"a64_v3d71_ident_check: HUB READ +${off:X} before the domain, reset "
                       f"and SMS were all ready. On silicon this may hang.\n  at {where}")
        self.events.append(("hub-read", off))
        regs = {0x8: 0x42554856, 0xC: self.ident1, 0x10: 0x00000100,
                0x14: self.ident3, 0x1238: 0x00000081}
        if off not in regs:
            self._unmodelled("hub", off, where)
        return regs[off]

    def core_read(self, off: int, where: str) -> int:
        if not self.v3d_ready():
            raise Hang(f"a64_v3d71_ident_check: CORE READ +${off:X} before V3D was ready\n  at {where}")
        self.events.append(("core-read", off))
        return {0x0: self.core_ident0, 0x4: self.core_ident1, 0x8: 0x00000000}.get(off, 0) \
            if off in (0, 4, 8) else self._unmodelled("core", off, where)

    @staticmethod
    def _unmodelled(block: str, off: int, where: str) -> int:
        raise SystemExit(f"a64_v3d71_ident_check: unmodelled {block} read +${off:X}\n  at {where}")


def build(probe: pathlib.Path, workdir: pathlib.Path, compiler: str, name: str) -> pathlib.Path:
    img = workdir / name
    r = subprocess.run(
        [compiler, "--compile", str(probe), "-t", "pi5", "--entry-returns",
         "--load-addr", hex(LOAD), "--stack-addr", hex(STACK), "-o", str(img)],
        cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
        capture_output=True, text=True)
    if r.returncode != 0 or not img.exists():
        raise SystemExit("a64_v3d71_ident_check: %s did not build (exit %d).\n%s%s"
                         % (probe.name, r.returncode, r.stdout, r.stderr))
    if "target BCM2712" not in r.stdout:
        raise SystemExit("a64_v3d71_ident_check: the build did not report target BCM2712; "
                         "this compiler does not know -t pi5.\n" + r.stdout)
    return img


def _symbols(img: pathlib.Path):
    dbg = pathlib.Path(str(img) + ".dbg")
    out = []
    if dbg.exists():
        for line in dbg.read_text(encoding="utf-8", errors="replace").splitlines():
            f = line.split("|")
            if len(f) >= 4 and f[0] == "1" and f[1].isdigit():
                out.append((LOAD + int(f[1]), f[2]))
    return sorted(out)


def run(img: pathlib.Path, m: Model, midr: int = MIDR_A76, tick_step: int = 64,
        limit: int = 30_000_000) -> tuple[int, str]:
    cpu = A64()
    for i, b in enumerate(img.read_bytes()):
        cpu.memory[LOAD + i] = b
    cpu.pc = LOAD
    cpu.sp = STACK
    cpu.x[30] = LOADER_LR
    syms = _symbols(img)
    mem = cpu.memory

    def where() -> str:
        best = None
        for a, n in syms:
            if a <= cpu.pc:
                best = (a, n)
        return "$%X %s" % (cpu.pc, f"{best[1]}+{cpu.pc - best[0]}" if best else "")

    def guard(addr: int, size: int, write: bool) -> None:
        if size != 4:
            raise SystemExit(f"a64_v3d71_ident_check: a {size}-byte {'write' if write else 'read'} "
                             f"at ${addr:X}; peripheral registers are 32 bits (PeekN/PokeL)\n  at {where()}")
        if addr % 4:
            raise SystemExit(f"a64_v3d71_ident_check: unaligned MMIO at ${addr:X}\n  at {where()}")

    def load(addr: int, size: int) -> int:
        if addr >= MMIO_FLOOR:
            guard(addr, size, False)
            if addr == UART + 0x18:
                return 0
            if PM <= addr < PM + PM_SIZE:
                return m.pm_read(addr - PM)
            if SMS <= addr < SMS + 0x700:
                return m.sms_read(addr - SMS, where())
            if HUB <= addr < HUB + 0x4000:
                return m.hub_read(addr - HUB, where())
            if CORE0 <= addr < CORE0 + 0x6000:
                return m.core_read(addr - CORE0, where())
            raise SystemExit(f"a64_v3d71_ident_check: UNMODELLED MMIO READ ${addr:X}\n  at {where()}")
        if size > 1 and addr % size:
            raise SystemExit(f"a64_v3d71_ident_check: unaligned DRAM read ${addr:X}\n  at {where()}")
        return sum(mem.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr: int, value: int, size: int) -> None:
        if addr >= MMIO_FLOOR:
            guard(addr, size, True)
            v = value & 0xFFFFFFFF
            if addr == UART:
                m.uart.append(v & 0xFF)
                return
            m.mmio_writes += 1
            if PM <= addr < PM + PM_SIZE:
                m.pm_write(addr - PM, v, where())
                return
            if SMS <= addr < SMS + 0x700:
                m.sms_write(addr - SMS, v, where())
                return
            raise SystemExit(f"a64_v3d71_ident_check: UNMODELLED MMIO WRITE ${addr:X} = ${v:08X}\n  at {where()}")
        if size > 1 and addr % size:
            raise SystemExit(f"a64_v3d71_ident_check: unaligned DRAM write ${addr:X}\n  at {where()}")
        for i in range(size):
            mem[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    plain_step = A64.step.__get__(cpu)
    ticks = [0]

    def step() -> None:
        ins = load(cpu.pc, 4)
        base = ins & 0xFFFFFFE0
        if base == 0xD53BE020:          # mrs Xt, cntpct_el0
            ticks[0] += tick_step
            cpu.x[ins & 31] = ticks[0]
        elif base == 0xD53BE000:        # mrs Xt, cntfrq_el0
            cpu.x[ins & 31] = CNTFRQ
        elif base == 0xD5380000:        # mrs Xt, midr_el1
            cpu.x[ins & 31] = midr
        else:
            plain_step()
            return
        cpu.pc += 4

    for _ in range(limit):
        if cpu.pc == LOADER_LR:
            break
        step()
    else:
        raise SystemExit("a64_v3d71_ident_check: the probe did not return within %d "
                         "instructions (an unbounded wait)" % limit)
    return cpu.x[0] & 0xFFFFFFFF, m.uart.decode("utf-8", "replace")


def pm_writes(m: Model, off: int) -> list[int]:
    return [e[2] for e in m.events if e[0] == "pm" and e[1] == off]


def scenarios(img: pathlib.Path) -> list[str]:
    fails: list[str] = []

    def need(cond: bool, what: str) -> None:
        if not cond:
            fails.append(what)

    # 1. Healthy, domain off at entry.
    m = Model()
    x0, text = run(img, m)
    need(x0 == 0x117, f"healthy: returned ${x0:X}, want $117\n{text}")
    need("V3D 7.1 IS ALIVE" in text, "healthy: no ALIVE line")
    g = pm_writes(m, PM_GRAFX)
    ramp = [(v & INRUSH_MASK) >> INRUSH_SHIFT for v in g[:4]]
    need(len(g) >= 7 and ramp == [0, 1, 2, 3] and all(v & POWUP for v in g[:4]),
         f"healthy: GRAFX ramp is not four POWUP writes at inrush 0..3 (kernel :236-248): {[hex(v) for v in g]}")
    if len(g) >= 7:
        need(g[4] & ISPOW and not g[3] & ISPOW, "healthy: ISPOW is not the fifth GRAFX write")
        need(g[5] & MEMREP and not g[4] & MEMREP, "healthy: MEMREP is not the sixth GRAFX write")
        need(g[6] & ISFUNC and not g[5] & ISFUNC, "healthy: ISFUNC is not the seventh GRAFX write")
    need(len(g) == 7, f"healthy: {len(g)} GRAFX writes, want 7")
    r = pm_writes(m, PM_GRAFX_2712)
    need(r == [V3DRSTN], f"healthy: $304 writes {r}, want one V3DRSTN")
    order = [e[0] + ("-2712" if e[0] == "pm" and e[1] == PM_GRAFX_2712 else "") for e in m.events]
    first = {k: order.index(k) for k in ("pm-2712", "sms", "hub-read") if k in order}
    last_grafx = max((i for i, e in enumerate(m.events) if e[0] == "pm" and e[1] == PM_GRAFX),
                     default=10 ** 9)
    need(first.get("pm-2712", -1) > last_grafx,
         "healthy: V3DRSTN missing, or before the GRAFX rail finished")
    sms = [(e[1], e[2]) for e in m.events if e[0] == "sms"]
    need(sms == [(SMS_TEE, SMS_CLEAR_POWER_OFF), (SMS_REE, 4)],
         f"healthy: SMS writes {sms}, want TEE_CS=CLEAR_POWER_OFF then REE_CS=4")
    need(m.unpassworded == 0, "healthy: a PM write without the password")
    for k in ("HUB_IDENT0", "HUB_IDENT1", "HUB_IDENT2", "HUB_IDENT3", "MMU_DEBUG",
              "CORE_IDENT0", "CORE_IDENT1", "CORE_IDENT2", "IPREV"):
        need(k in text, f"healthy: {k} not printed")
    need("$000F0117" in text, "healthy: HUB_IDENT1 value not printed")

    # 2. The firmware left the domain powered: no rail writes at all.
    m = Model(grafx0=POWUP | ISPOW | MEMREP | ISFUNC | INRUSH_MASK)
    x0, text = run(img, m)
    need(x0 == 0x117 and pm_writes(m, PM_GRAFX) == [],
         f"already powered: GRAFX written {pm_writes(m, PM_GRAFX)} (kernel :227-229 leaves it)")

    # 3. A Cortex-A72 (a Pi 4): refuse, write nothing.
    m = Model()
    x0, text = run(img, m, midr=MIDR_A72)
    need(x0 == 0 and m.mmio_writes == 0 and "NOT_A76" in text,
         f"A72: x0 ${x0:X}, {m.mmio_writes} MMIO writes\n{text}")

    # 4. A 4.2 identity ($124), and 5. a dark one (0): refuse.
    for ident, label in ((0x00000124, "4.2 IDENT"), (0x00000000, "dark IDENT")):
        m = Model(ident1=ident)
        x0, text = run(img, m)
        need(x0 == 0 and "IDENT - HUB_IDENT1" in text and "ALIVE" not in text,
             f"{label}: x0 ${x0:X}\n{text}")
    # 5b. Right hub IDENT, wrong core version byte: refuse.
    m = Model(core_ident0=0x04443344)
    x0, text = run(img, m)
    need(x0 == 0, "core IDENT0 version 4 was accepted")

    # 6. POWOK never: named refusal, POWUP undone, no reset release, no V3D access.
    m = Model(powok_never=True)
    x0, text = run(img, m)
    g = pm_writes(m, PM_GRAFX)
    need(x0 == 0 and "GRAFX_POWOK" in text and g and not (g[-1] & (POWUP | INRUSH_MASK))
         and pm_writes(m, PM_GRAFX_2712) == [] and not any(e[0] != "pm" for e in m.events),
         f"POWOK never: x0 ${x0:X} writes {[hex(v) for v in g]}\n{text}")

    # 7. MRDONE never: ISPOW then POWUP undone (:277-280).
    m = Model(mrdone_never=True)
    x0, text = run(img, m)
    g = pm_writes(m, PM_GRAFX)
    need(x0 == 0 and "GRAFX_MRDONE" in text and len(g) >= 2 and not (g[-1] & (POWUP | ISPOW))
         and pm_writes(m, PM_GRAFX_2712) == [],
         f"MRDONE never: {[hex(v) for v in g]}\n{text}")

    # 8/9. SMS never settles: named refusal within the 100 ms bound, no hub read.
    for kw, label, name in (({"sms_resume_stuck": True}, "SMS resume stuck", "SMS_RESUME"),
                            ({"sms_reset_stuck": True}, "SMS reset stuck", "SMS_RESET")):
        m = Model(**kw)
        x0, text = run(img, m, tick_step=65536)
        need(x0 == 0 and name in text and not any(e[0] in ("hub-read", "core-read") for e in m.events),
             f"{label}: x0 ${x0:X}\n{text}")

    # 10. POWOK only at the highest inrush step: still up.
    m = Model(powok_at=3)
    x0, _ = run(img, m)
    need(x0 == 0x117, "POWOK at inrush 3 was not reached")
    return fails


MUTANTS = [
    ("password dropped", "#P5_PM_PASSWORD | (value & $00FFFFFF)", "(value & $00FFFFFF)"),
    ("reset in $10C", "#P5_PM_GRAFX_2712  = $304", "#P5_PM_GRAFX_2712  = $10C"),
    ("SMS reset skipped", "  PokeL(#P5_V3D_SMS + #P5_SMS_REE_CS, #P5_SMS_RESET_REQ)\n", ""),
    ("ident compare off", "(i1 & $FFF) <> #P5_IDENT1_EXPECT_LOW12 Or ", ""),
    ("MIDR guard off", "  If ((midr >> 24) & $FF) <> #P5_MIDR_IMPL_ARM Or ((midr >> 4) & $FFF) <> #P5_MIDR_PART_A76",
     "  If 0"),
    ("ramp stops early", "  While inrush <= 3\n", "  While inrush <= 3 And powok = 0\n"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Desk gate for the Pi 5 V3D 7.1 identity probe.")
    ap.add_argument("--compiler", default=None,
                    help="the PureMetalForge compiler executable (default: $PMF_COMPILER)")
    ap.add_argument("--mutate", action="store_true",
                    help="also build broken copies of the probe and require each to fail")
    a = ap.parse_args()
    compiler = resolve_compiler(a.compiler)
    with tempfile.TemporaryDirectory(prefix="v3d71-ident-") as td:
        wd = pathlib.Path(td)
        img = build(PROBE, wd, compiler, "v3d71ident.img")
        fails = scenarios(img)
        for f in fails:
            print("FAIL", f)
        print(f"a64_v3d71_ident_check: 11 scenarios, {len(fails)} failure(s)")
        rc = 1 if fails else 0
        if a.mutate:
            src = PROBE.read_text(encoding="utf-8")
            survived = 0
            for i, (name, old, new) in enumerate(MUTANTS):
                if old not in src:
                    print(f"MUTANT {name}: pattern not found in the probe - the list is stale")
                    rc = 1
                    continue
                mp = wd / f"mutant{i}.pi5"
                mp.write_text(src.replace(old, new, 1), encoding="utf-8")
                try:
                    mimg = build(mp, wd, compiler, f"mutant{i}.img")
                    mf = scenarios(mimg)
                    killed = bool(mf)
                except (SystemExit, Exception) as e:
                    killed, mf = True, [(str(e).splitlines() or [type(e).__name__])[0]]
                print(f"MUTANT {name}: {'killed' if killed else 'SURVIVED'}"
                      + (f" ({mf[0].splitlines()[0][:90]})" if killed else ""))
                survived += 0 if killed else 1
            print(f"mutants: {len(MUTANTS) - survived}/{len(MUTANTS)} killed")
            if survived:
                rc = 1
        return rc


if __name__ == "__main__":
    raise SystemExit(main())

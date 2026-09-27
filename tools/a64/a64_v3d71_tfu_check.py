#!/usr/bin/env python3
"""Desk gate for the first V3D 7.1 milestone (Pi 5): power, clock, IDENT, one TFU job.

Builds RaspberryPi5/Tests/v3d71_tfu_probe.pi5 with `-t pi5`. The probe calls
the REAL library, RaspberryPi4/Lib/v3d.pi4, whose `#PMF_CHIP = 2712` arms hold
the BCM2712 bring-up and the V3D 7.1 TFU. The gate runs the image in
tools/a64/a64_interp.py and answers every MMIO access from models. The models
are reused, not copied:

  PM block, SMS, IDENT, MIDR     a64_v3d71_ident_check.Model (stage 1's model:
                                 strict - a V3D read before the domain, the
                                 reset and the SMS are all up is a Hang)
  property mailbox               a64_v3d_check.Firmware (answers like the
                                 firmware; the 2712 buffer is not aliased,
                                 mailbox.pi4 #MBX_BUS_OFFSET = 0 on 2712)
  the V3D's own MMU              a64_v3d_check.V3dMmu (v3d_mmu.c, identical on
                                 7.1 - vault plan C4)

plus, new here, the V3D 7.1 TFU register block and job semantics, written
from the pinned sources (vault "Raspberry Pi 5/Sources/"):

  offsets     v3d_regs.h:99-147 (the `ver >= 71` arm; IOC at $71C is new)
  launch      v3d_sched.c:348-363 (IIA IIS ICA IUA IOA IOC IOS COEF0-3, then
              ICFG | IOC kicks; COEF1..3 ALWAYS on 7.1)
  fields      mesa-61f25904 common_v3d_tfu.h V3D71_* and
              vulkan_v3dvx_meta_common.c:962-1003 (ICFG = IFORMAT<<23 |
              OTYPE<<16; IOA = address; IOC = FORMAT<<12 | STRIDE<<16 |
              NUMMM<<4 | DIMTW)
  layout      LINEARTILE, Mesa v3d_tiling.c (the Pi 4 gate's transcription)
  completion  TFU_CS.CVTCT advances AND HUB_INT_STS.TFUC is raised

WHAT IT PROVES: that the library, built for the 2712, powers V3D the kernel's
way (no mailbox domain/power claim; the firmware clock 5 is claimed and set),
identifies a 7.1 part, programs the V3D MMU, and drives one TFU job through
the 7.1 registers in the kernel's order, and that the probe accepts the job
only when the counter moved, TFUC was raised and every output byte is where
LINEARTILE puts it. Negative models: a Cortex-A72 (no write at all), a 4.2
IDENT, POWOK never, SMS resume stuck, the TFU dead, the TFU failing, TFUC
never raised, the output left raster. --mutate breaks the LIBRARY in ways a
wrong port would, and each must go red.

WHAT IT CANNOT PROVE: that the silicon behaves like the model. See the vault
plan's open questions (the stepping, the SMS from EL3, whether a dark V3D
read hangs, the payload window).

Run:  py -3 -B tools/a64/a64_v3d71_tfu_check.py --compiler <PureMetalForge.exe> [--mutate]
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
sys.path.insert(0, str(ROOT / "tools"))
from a64_interp import A64  # noqa: E402
import a64_v3d_check as P4  # noqa: E402
import a64_v3d71_ident_check as S1  # noqa: E402
from pmf_compiler import resolve_compiler  # noqa: E402

PROBE_REL = pathlib.Path("RaspberryPi5/Tests/v3d71_tfu_probe.pi5")
LIB_REL = pathlib.Path("RaspberryPi4/Lib/v3d.pi4")
COPY_RELS = (PROBE_REL, LIB_REL, pathlib.Path("RaspberryPi4/Lib/mailbox.pi4"),
             pathlib.Path("RaspberryPi4/Intrinsics/bcm2711_hardware.def"))

LOAD, STACK, LOADER_LR, CNTFRQ = S1.LOAD, S1.STACK, S1.LOADER_LR, S1.CNTFRQ
PM, HUB, CORE0, SMS, UART = S1.PM, S1.HUB, S1.CORE0, S1.SMS, S1.UART
MMIO_FLOOR = S1.MMIO_FLOOR
# /soc@107c000000/mailbox@7c013880, soc ranges child 0 -> $10_0000_0000.
MBX = 0x10_0000_0000 + 0x7C013880
MBX_READ, MBX_STATUS0, MBX_WRITE, MBX_STATUS1 = MBX, MBX + 0x18, MBX + 0x20, MBX + 0x38

SRC, DST = 0x04410000, 0x04411000       # the probe's physical pages (its own constants)
W, H, CPP = 16, 4, 4

# ---- V3D 7.1 TFU, v3d_regs.h (pinned) ------------------------------------
TFU71 = dict(CS=0x700, SU=0x704, ICFG=0x708, IIA=0x70C, ICA=0x710, IIS=0x714,
             IUA=0x718, IOC=0x71C, IOA=0x720, IOS=0x724, COEF0=0x728,
             COEF1=0x72C, COEF2=0x730, COEF3=0x734)
TFU71_END = 0x738
LAUNCH_ORDER = ["IIA", "IIS", "ICA", "IUA", "IOA", "IOC", "IOS",
                "COEF0", "COEF1", "COEF2", "COEF3", "ICFG"]   # v3d_sched.c:348-363
ICFG_IFORMAT_SHIFT, ICFG_OTYPE_SHIFT = 23, 16                  # V3D71_TFU_ICFG_*
IOC_FORMAT_SHIFT, IOC_STRIDE_SHIFT, IOC_NUMMM_SHIFT, IOC_DIMTW = 12, 16, 4, 1
FMT_RASTER, FMT_LINEARTILE = 0, 3
TEXFMT_RGBA8 = P4.PINNED["TEXFMT_RGBA8"]   # v3d_packet.xml; unchanged on 7.1 (plan E8)

K = dict(P4.PINNED)                       # MMU, cache and INT registers: = on 7.1
HUB_INT_TFUC, HUB_INT_TFUF = K["HUB_INT_TFUC"], K["HUB_INT_TFUF"]

P4.MBX_BUS_OFFSET = 0     # Firmware.submit reads it; 2712 buffers are ARM-physical


class Tfu71:
    """The 7.1 TFU. `mode`: normal, dead, fail, tfuc_never, raster_out."""

    def __init__(self, mmu: P4.V3dMmu, mode: str = "normal"):
        self.mmu = mmu
        self.mode = mode
        self.reg: dict[str, int] = {}
        self.order: list[str] = []
        self.cvtct = 0
        self.int_sts = 0
        self.jobs: list[dict] = []

    def write(self, off: int, v: int, where: str) -> None:
        name = next((n for n, o in TFU71.items() if o == off), None)
        if name is None:
            raise SystemExit(f"a64_v3d71_tfu_check: TFU write at hub ${off:X}, no 7.1 register there\n  at {where}")
        if name in ("CS", "SU"):
            raise SystemExit(f"a64_v3d71_tfu_check: the library wrote TFU_{name}, which it has no reason to\n  at {where}")
        self.reg[name] = v
        self.order.append(name)
        if name == "ICFG":
            self._run(where)

    def read(self, off: int) -> int:
        if off == TFU71["CS"]:
            return ((self.cvtct & 0xFF) << 16) | (8 << 8)
        name = next((n for n, o in TFU71.items() if o == off), None)
        return self.reg.get(name, 0)

    def _run(self, where: str) -> None:
        job_order = self.order[-len(LAUNCH_ORDER):]
        if job_order != LAUNCH_ORDER:
            raise SystemExit("a64_v3d71_tfu_check: the TFU was launched with the writes in the "
                             f"order {self.order}; v3d_sched.c:348-363 writes {LAUNCH_ORDER} "
                             f"(IOC after IOA, COEF1-3 always on 7.1, ICFG last)\n  at {where}")
        self.order = []
        r = self.reg
        icfg, ioc = r["ICFG"], r["IOC"]
        if not icfg & K["ICFG_IOC"]:
            raise SystemExit("a64_v3d71_tfu_check: ICFG without the IOC bit (v3d_sched.c:362)")
        if any(r[c] for c in ("ICA", "IUA", "COEF0", "COEF1", "COEF2", "COEF3")):
            raise SystemExit("a64_v3d71_tfu_check: a chroma plane or YUV coefficient was set "
                             "for an RGBA copy")
        job = dict(iformat=(icfg >> ICFG_IFORMAT_SHIFT) & 0x7,
                   otype=(icfg >> ICFG_OTYPE_SHIFT) & 0x7F,
                   junk=icfg & ~((0x7 << 23) | (0x7F << 16) | 1),
                   ofmt=(ioc >> IOC_FORMAT_SHIFT) & 0x7, stride=ioc >> IOC_STRIDE_SHIFT,
                   nummm=(ioc >> IOC_NUMMM_SHIFT) & 0xF, dimtw=ioc & IOC_DIMTW,
                   ioa=r["IOA"], iia=r["IIA"], iis=r["IIS"],
                   w=r["IOS"] & 0xFFFF, h=(r["IOS"] >> 16) & 0xFFFF)
        self.jobs.append(job)
        if self.mode == "dead":
            return
        if self.mode == "fail":
            self.int_sts |= HUB_INT_TFUF
            return
        if job["junk"]:
            raise SystemExit(f"a64_v3d71_tfu_check: ICFG ${icfg:08X} has bits outside IFORMAT, "
                             "OTYPE and IOC - a 4.2 field layout?")
        if job["iformat"] != FMT_RASTER:
            raise SystemExit(f"a64_v3d71_tfu_check: input format {job['iformat']}, this model "
                             "implements RASTER input only")
        if job["otype"] != TEXFMT_RGBA8:
            raise SystemExit(f"a64_v3d71_tfu_check: texture type {job['otype']} at ICFG 22:16; the "
                             f"probe asks for RGBA8 ({TEXFMT_RGBA8}). A 4.2 OTYPE shift (9) lands here.")
        if job["ofmt"] != FMT_LINEARTILE or job["stride"] or job["nummm"] or job["dimtw"]:
            raise SystemExit(f"a64_v3d71_tfu_check: IOC ${ioc:08X} is not LINEARTILE with no stride, "
                             "no mips, no DIMTW")
        if job["ioa"] & 0x3F:
            raise SystemExit(f"a64_v3d71_tfu_check: IOA ${job['ioa']:X} carries flag bits; on 7.1 it "
                             "is the address alone")
        out = []
        for y in range(job["h"]):
            for x in range(job["w"]):
                word = self.mmu.read32(job["iia"] + (y * job["iis"] + x) * CPP)
                if word is None:
                    return
                if self.mode == "raster_out":
                    off = (y * job["w"] + x) * CPP
                else:
                    off = 64 * (x // 4 + y // 4) + (x % 4) * CPP + (y % 4) * 4 * CPP
                out.append((job["ioa"] + off, word))
        for va, word in out:
            if not self.mmu.write32(va, word):
                return
        self.cvtct = (self.cvtct + 1) & 0xFF
        if self.mode != "tfuc_never":
            self.int_sts |= HUB_INT_TFUC


class Pi5V3d(S1.Model):
    """Stage 1's PM/SMS/IDENT model, plus the hub INT, MMU and TFU and core caches."""

    def __init__(self, mem, tfu_mode="normal", **kw):
        super().__init__(**kw)
        self.mmu = P4.V3dMmu(K, mem)
        self.tfu = Tfu71(self.mmu, tfu_mode)
        self.int_msk = 0xFFFFFFFF          # masked at reset, v3d_irq.c:274
        self.core_writes: dict[int, int] = {}

    def hub_read(self, off: int, where: str) -> int:
        if off in (0x8, 0xC, 0x10, 0x14, 0x1238):
            return super().hub_read(off, where)
        if not self.v3d_ready():
            raise S1.Hang(f"a64_v3d71_tfu_check: HUB READ +${off:X} before V3D was ready\n  at {where}")
        m = self.mmu
        regs = {K["V3D_HUB_INT_STS"]: self.tfu.int_sts & ~self.int_msk,
                K["HUB_INT_MSK_STS"]: self.int_msk,
                K["MMU_CTL"]: m.ctl, K["MMU_PT_PA_BASE"]: m.pt_base,
                K["MMU_ILLEGAL_ADDR"]: m.illegal, K["MMU_HIT"]: m.hits,
                K["MMU_MISSES"]: m.misses, K["MMU_VIO_ADDR"]: m.vio_addr,
                K["MMU_VIO_ID"]: m.vio_id,
                K["MMUC_CONTROL"]: m.mmuc & ~K["MMUC_CONTROL_FLUSHING"]}
        if off in regs:
            return regs[off]
        if TFU71["CS"] <= off < TFU71_END:
            return self.tfu.read(off)
        return self._unmodelled("hub", off, where)

    def hub_write(self, off: int, v: int, where: str) -> None:
        if not self.v3d_ready():
            raise S1.Hang(f"a64_v3d71_tfu_check: HUB WRITE +${off:X} before V3D was ready\n  at {where}")
        self.events.append(("hub", off, v))
        m = self.mmu
        if off == K["V3D_HUB_INT_CLR"]:
            self.tfu.int_sts &= ~v
        elif off == K["HUB_INT_MSK_SET"]:
            self.int_msk |= v
        elif off == K["HUB_INT_MSK_CLR"]:
            self.int_msk &= ~v
        elif off == K["MMU_PT_PA_BASE"]:
            m.pt_base = v
        elif off == K["MMU_CTL"]:
            if v & K["MMU_CTL_TLB_CLEAR"]:
                m.flushes += 1
            m.ctl = v & ~K["MMU_CTL_TLB_CLEAR"]
        elif off == K["MMU_ILLEGAL_ADDR"]:
            m.illegal = v
        elif off == K["MMUC_CONTROL"]:
            m.mmuc = v & ~K["MMUC_CONTROL_FLUSH"]
        elif 0x400 <= off < 0x438:
            raise SystemExit(f"a64_v3d71_tfu_check: WRITE to hub ${off:X}, the V3D 4.2 TFU block. "
                             "On 7.1 the TFU is at $700 (v3d_regs.h:99); $4xx is something else."
                             f"\n  at {where}")
        elif TFU71["CS"] <= off < TFU71_END:
            self.tfu.write(off, v, where)
        else:
            raise SystemExit(f"a64_v3d71_tfu_check: unmodelled hub write +${off:X} = ${v:08X}\n  at {where}")

    def core_read(self, off: int, where: str) -> int:
        if off in (0x0, 0x4, 0x8):
            return super().core_read(off, where)
        if not self.v3d_ready():
            raise S1.Hang(f"a64_v3d71_tfu_check: CORE READ +${off:X} before V3D was ready\n  at {where}")
        if off in (K["V3D_CTL_L2TCACTL"], K["V3D_CTL_SLCACTL"], K["V3D_CTL_INT_STS"],
                   K["V3D_ERR_STAT"]):
            return 0                              # every flush modelled as instantaneous
        return self._unmodelled("core", off, where)

    def core_write(self, off: int, v: int, where: str) -> None:
        if not self.v3d_ready():
            raise S1.Hang(f"a64_v3d71_tfu_check: CORE WRITE +${off:X} before V3D was ready\n  at {where}")
        allowed = (K["V3D_CTL_L2TFLSTA"], K["V3D_CTL_L2TFLEND"], K["V3D_CTL_L2TCACTL"],
                   K["V3D_CTL_SLCACTL"])
        if off not in allowed:
            raise SystemExit(f"a64_v3d71_tfu_check: core write +${off:X}; only the cache "
                             f"registers are the TFU path's\n  at {where}")
        self.core_writes[off] = v


def build(root: pathlib.Path, workdir: pathlib.Path, compiler: str, name: str,
          probe_rel: pathlib.Path = PROBE_REL) -> pathlib.Path:
    img = workdir / name
    r = subprocess.run([compiler, "--compile", str(root / probe_rel), "-t", "pi5", "-s", "--entry-returns",
                        "--load-addr", hex(LOAD), "--stack-addr", hex(STACK), "-o", str(img)],
                       cwd=root, env=dict(os.environ, PMF_ROOT=str(root)),
                       capture_output=True, text=True)
    if r.returncode != 0 or not img.exists() or "BCM2712" not in r.stdout:
        raise SystemExit("a64_v3d71_tfu_check: the probe did not build -t pi5\n"
                         + (r.stdout + r.stderr)[-2500:])
    return img


def run(img, midr=S1.MIDR_A76, tfu_mode="normal", tick_step=64, fw_kw=None,
        limit=60_000_000, model_cls=None, **model_kw):
    cpu = A64()
    for i, b in enumerate(img.read_bytes()):
        cpu.memory[LOAD + i] = b
    cpu.pc, cpu.sp, cpu.x[30] = LOAD, STACK, LOADER_LR
    mem = cpu.memory
    m = (model_cls or Pi5V3d)(mem, tfu_mode, **model_kw)
    fw = P4.Firmware(dict(P4.PINNED_TAGS), P4.PINNED_CLOCK_ID, 11, 10, **(fw_kw or {}))
    syms = S1._symbols(img)

    def where():
        best = None
        for a, n in syms:
            if a <= cpu.pc:
                best = (a, n)
        return "$%X %s" % (cpu.pc, f"{best[1]}+{cpu.pc - best[0]}" if best else "")

    def guard(addr, size):
        if size != 4 or addr % 4:
            raise SystemExit(f"a64_v3d71_tfu_check: a {size}-byte MMIO access at ${addr:X}\n  at {where()}")

    def load(addr, size):
        if addr >= MMIO_FLOOR:
            guard(addr, size)
            if addr == UART + 0x18 or addr == MBX_STATUS1:
                return 0
            if addr == MBX_STATUS0:
                return 0 if fw.reply is not None else 0x40000000
            if addr == MBX_READ:
                if fw.reply is None:
                    raise SystemExit("a64_v3d71_tfu_check: read an empty mailbox\n  at " + where())
                r, fw.reply = fw.reply, None
                return r
            if PM <= addr < PM + S1.PM_SIZE:
                return m.pm_read(addr - PM)
            if SMS <= addr < SMS + 0x700:
                return m.sms_read(addr - SMS, where())
            if HUB <= addr < HUB + 0x4000:
                return m.hub_read(addr - HUB, where())
            if CORE0 <= addr < CORE0 + 0x6000:
                return m.core_read(addr - CORE0, where())
            raise SystemExit(f"a64_v3d71_tfu_check: UNMODELLED MMIO READ ${addr:X}\n  at {where()}")
        if size > 1 and addr % size:
            raise SystemExit(f"a64_v3d71_tfu_check: unaligned DRAM read ${addr:X}\n  at {where()}")
        return sum(mem.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr, value, size):
        if addr >= MMIO_FLOOR:
            guard(addr, size)
            v = value & 0xFFFFFFFF
            if addr == UART:
                m.uart.append(v & 0xFF)
                return
            m.mmio_writes += 1
            if addr == MBX_WRITE:
                fw.submit(v, mem)
                return
            if PM <= addr < PM + S1.PM_SIZE:
                return m.pm_write(addr - PM, v, where())
            if SMS <= addr < SMS + 0x700:
                return m.sms_write(addr - SMS, v, where())
            if HUB <= addr < HUB + 0x4000:
                return m.hub_write(addr - HUB, v, where())
            if CORE0 <= addr < CORE0 + 0x6000:
                return m.core_write(addr - CORE0, v, where())
            raise SystemExit(f"a64_v3d71_tfu_check: UNMODELLED MMIO WRITE ${addr:X} = ${v:08X}\n  at {where()}")
        if size > 1 and addr % size:
            raise SystemExit(f"a64_v3d71_tfu_check: unaligned DRAM write ${addr:X}\n  at {where()}")
        for i in range(size):
            mem[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load, cpu.store = load, store
    plain = A64.step.__get__(cpu)
    ticks = [0]
    for _ in range(limit):
        if cpu.pc == LOADER_LR:
            break
        ins = load(cpu.pc, 4)
        base = ins & 0xFFFFFFE0
        if base == 0xD53BE020:
            ticks[0] += tick_step
            cpu.x[ins & 31] = ticks[0]
        elif base == 0xD53BE000:
            cpu.x[ins & 31] = CNTFRQ
        elif base == 0xD5380000:
            cpu.x[ins & 31] = midr
        else:
            plain()
            continue
        cpu.pc += 4
    else:
        raise SystemExit(f"a64_v3d71_tfu_check: the probe did not return within {limit} instructions")
    return cpu.x[0] & 0xFFFFFFFF, m, fw, mem


def tags_sent(fw, name):
    return [w for t, w in fw.seen if t == P4.PINNED_TAGS[name]]


def scenarios(img) -> list[str]:
    errs: list[str] = []

    def need(cond, what):
        if not cond:
            errs.append(what)

    # 1. healthy
    rc, m, fw, mem = run(img)
    need(rc == 0x71, f"healthy: probe returned ${rc:X}, want $71\n{m.uart.decode(errors='replace')[-600:]}")
    if rc == 0x71:
        job = m.tfu.jobs[-1]
        need(job["w"] == W and job["h"] == H, f"healthy: IOS {job['w']}x{job['h']}")
        # the gate's own check of the bytes, not the probe's
        wrong = 0
        for y in range(H):
            for x in range(W):
                want = sum(mem.get(SRC + (y * W + x) * CPP + i, 0) << (8 * i) for i in range(4))
                off = 64 * (x // 4 + y // 4) + (x % 4) * CPP + (y % 4) * 16
                got = sum(mem.get(DST + off + i, 0) << (8 * i) for i in range(4))
                wrong += got != want
        need(wrong == 0, f"healthy: {wrong} output texels wrong in DRAM")
        need(m.tfu.cvtct == 1 and (m.tfu.int_sts & HUB_INT_TFUC) == 0,
             "healthy: one conversion, and TFUC cleared again afterwards")
        need(m.int_msk & (HUB_INT_TFUC | HUB_INT_TFUF) == (HUB_INT_TFUC | HUB_INT_TFUF),
             "healthy: the TFU interrupt mask was not restored")
    need(not tags_sent(fw, "SET_DOMAIN_STATE") and not tags_sent(fw, "SET_POWER_STATE")
         and not tags_sent(fw, "GET_DOMAIN_STATE") and not tags_sent(fw, "GET_POWER_STATE"),
         "healthy: a BCM2711 domain/power tag went to the Pi 5 firmware")
    need(any(w[0] == 5 and w[1] == 1 for w in tags_sent(fw, "SET_CLOCK_STATE")),
         "healthy: firmware clock 5 was not claimed (SET_CLOCK_STATE 5, on)")
    need(any(w[0] == 5 for w in tags_sent(fw, "SET_CLOCK_RATE")),
         "healthy: firmware clock 5 was not set to its maximum")
    g_writes = S1.pm_writes(m, S1.PM_GRAFX)
    inrush = [(v & S1.INRUSH_MASK) >> S1.INRUSH_SHIFT for v in g_writes if v & S1.POWUP
              and not v & (S1.ISPOW | S1.MEMREP | S1.ISFUNC)]
    need(inrush == [0, 1, 2, 3], f"healthy: inrush steps {inrush}, the kernel writes all four")
    need(m.unpassworded == 0, "healthy: an unpassworded PM write")

    # 2. firmware already powered the GRAFX domain
    up = S1.POWUP | S1.ISPOW | S1.ISFUNC
    rc, m, fw, _ = run(img, grafx0=up, powok_at=0)   # POWOK already showing
    need(rc == 0x71 and not S1.pm_writes(m, S1.PM_GRAFX),
         f"already powered: rc ${rc:X}, GRAFX writes {S1.pm_writes(m, S1.PM_GRAFX)}")

    # 3. refusals: (label, run kwargs, expected rc)
    for label, kw, want in (
            ("Cortex-A72", dict(midr=S1.MIDR_A72), 0x100 + 36),
            ("IDENT of a V3D 4.2", dict(ident1=0x000F0124), 0x100 + 9),
            ("POWOK never", dict(powok_never=True), 0x100 + 37),
            ("SMS resume stuck", dict(sms_resume_stuck=True, tick_step=65536), 0x100 + 39),
            ("TFU dead", dict(tfu_mode="dead", tick_step=65536), 0x300 + 20),
            ("TFU says TFUF", dict(tfu_mode="fail"), 0x300 + 21),
            ("TFUC never raised", dict(tfu_mode="tfuc_never"), 0x400),
            ("output left raster", dict(tfu_mode="raster_out"), None)):
        try:
            rc, m, fw, _ = run(img, **kw)
        except SystemExit as e:
            errs.append(f"{label}: the run stopped: {str(e)[:200]}")
            continue
        if want is None:
            need(0x500 < rc < 0x600, f"{label}: rc ${rc:X}, want $5xx (wrong bytes)")
        else:
            need(rc == want, f"{label}: rc ${rc:X}, want ${want:X}")
        if label == "Cortex-A72":
            need(m.mmio_writes == 0 and not fw.seen,
                 f"Cortex-A72: {m.mmio_writes} MMIO writes, {len(fw.seen)} mailbox tags - want none")
    return errs


def payload_window(img: pathlib.Path, monitor_bytes: int | None) -> list[str]:
    """The probe must sit where the Pi 5 monitor will admit it (memmap.pi4,
    2712 branch): image, BSS, buffers inside the LOW payload window
    MonGrainUp(#MON_LO + monitor) .. #PAY0_HI, the initial stack in the
    #PAY_STACK corridor. The high window #PAY1_* is outside the compiler's
    -t pi5 envelope ($80000..$0FFFFFFF) and is not used."""
    import re
    mm = (ROOT / "RaspberryPi4/Board/memmap.pi4").read_text(encoding="utf-8")
    probe = (ROOT / PROBE_REL).read_text(encoding="utf-8")

    def const(text, name):
        m = re.search(rf"(?m)^\s*#{name}\s*=\s*\$([0-9A-Fa-f]+)", text)
        if not m:
            raise SystemExit(f"a64_v3d71_tfu_check: #{name} not found")
        return int(m.group(1), 16)
    mon_lo, grain, pay0_hi = const(mm, "MON_LO"), const(mm, "MON_GRAIN"), const(mm, "PAY0_HI")
    stk_lo, stk_hi = const(mm, "PAY_STACK_LO"), const(mm, "PAY_STACK_HI")
    # The low edge follows the monitor. Without a measured image, assume the
    # monitor may grow to 32 MiB - the probe must still clear it.
    mon = monitor_bytes if monitor_bytes is not None else 32 << 20
    pay0_lo = -(-(mon_lo + mon) // grain) * grain
    errs = []
    sym = {}
    symf = pathlib.Path(str(img) + ".sym")
    for line in (symf.read_text(encoding="utf-8-sig").splitlines() if symf.exists() else []):
        if "=" in line:
            k, v = line.split("=", 1)
            sym[k.strip().lower()] = int(v.strip(), 0)
    if "__bss_start__" not in sym:
        return ["window: the build wrote no .sym with __bss_start__/__bss_end__"]
    spans = [("image", LOAD, LOAD + img.stat().st_size - 1),
             ("BSS", sym["__bss_start__"], sym["__bss_end__"])]
    for name in ("TP_PT", "TP_ILLEGAL", "TP_SRC", "TP_DST"):
        a = const(probe, name)
        spans.append((name, a, a + (0x4000 if name == "TP_PT" else 0x1000) - 1))
    for name, lo, hi in spans:
        if not (pay0_lo <= lo and hi <= pay0_hi):
            errs.append(f"window: {name} ${lo:X}..${hi:X} is outside the Pi 5 low payload "
                        f"window ${pay0_lo:X}..${pay0_hi:X}")
    # HwPmfStackAllowed: the initial 16-byte ABI area in the corridor, or in
    # a payload window.
    lo16, hi16 = STACK - 16, STACK - 1
    if not ((stk_lo <= lo16 and hi16 <= stk_hi) or (pay0_lo <= lo16 and hi16 <= pay0_hi)):
        errs.append(f"window: the stack top ${STACK:X} is in neither the #PAY_STACK corridor "
                    f"${stk_lo:X}..${stk_hi:X} nor the low payload window")
    return errs


def not_ported(lib: str) -> list[str]:
    """Every 4.2-only job path must refuse by name on a 2712 build, before it
    touches a register: binning and render (D1-D5) and the bridge-based
    ownership reset (A7). (CSD was ported at step 3; a64_v3d71_csd_check.py.)"""
    import re
    errs = []
    for name in ("V3dBinSubmit", "V3dRenderSubmit", "V3dOwnershipHardwareReset"):
        m = re.search(rf"(?ms)^Procedure\.i {name}\(\)\n(.*?)^EndProcedure", lib)
        if not m:
            errs.append(f"not ported: {name} is missing")
            continue
        body = m.group(1)
        head = body.split("CompilerEndIf", 1)[0]
        if "CompilerIf #PMF_CHIP = 2712" not in head or "#V3D_ERR_NOT_PORTED" not in head \
                or re.search(r"V3d(Hub|Core|Pm|Asb)(Write|Read)|v3d_Asb", head):
            errs.append(f"not ported: {name} does not refuse with #V3D_ERR_NOT_PORTED "
                        "on 2712 before its first register access")
    return errs


def _sub(text, old, new, n=1):
    if text.count(old) < n:
        raise SystemExit(f"mutant anchor missing: {old[:60]!r}")
    return text.replace(old, new, n)


MUTANTS = [
    ("TFU at the 4.2 offsets", lambda t: _sub(t, "  #V3D_TFU_CS    = $00700", "  #V3D_TFU_CS    = $00400")
     .replace("  #V3D_TFU_IIA   = $0070C", "  #V3D_TFU_IIA   = $0040C")),
    ("IOC never written", lambda t: _sub(t, "  V3dHubWrite(#V3D_TFU_IOC, v3d_tfuIoc)\n", "")),
    ("COEF1-3 skipped as on 4.2", lambda t: _sub(t, "  V3dHubWrite(#V3D_TFU_COEF1, 0)\n  V3dHubWrite(#V3D_TFU_COEF2, 0)\n  V3dHubWrite(#V3D_TFU_COEF3, 0)\n", "")),
    ("OTYPE at the 4.2 shift", lambda t: _sub(t, "  #V3D_TFU_ICFG_TTYPE_SHIFT  = 16", "  #V3D_TFU_ICFG_TTYPE_SHIFT  = 9")),
    ("output format in IOA as on 4.2", lambda t: _sub(t, "  ; tiling and DIMTW are V3dTfuIocWord's.\n  ProcedureReturn dstAddr\n",
                                                        "  ; tiling and DIMTW are V3dTfuIocWord's.\n  ProcedureReturn dstAddr | (outputFormat << 3)\n")),
    ("V3DRSTN into PM_GRAFX", lambda t: _sub(t, "  g = V3dPmRead(#V3D_PM_GRAFX_2712)\n  V3dPmWrite(#V3D_PM_GRAFX_2712, g | #V3D_PM_V3DRSTN)",
                                              "  g = V3dPmRead(#V3D_PM_GRAFX)\n  V3dPmWrite(#V3D_PM_GRAFX, g | #V3D_PM_V3DRSTN)")),
    ("SMS reset skipped", lambda t: _sub(t, "  V3dSmsWrite(#V3D_SMS_REE_CS, #V3D_SMS_RESET_REQ)\n", "")),
    ("inrush ramp stops at POWOK", lambda t: _sub(t, "    powok = v3d_PmWaitBit(#V3D_PM_GRAFX, #V3D_PM_POWOK, #V3D_PM_POWOK_WAIT_US)\n    inrush = inrush + 1\n",
                                                   "    powok = v3d_PmWaitBit(#V3D_PM_GRAFX, #V3D_PM_POWOK, #V3D_PM_POWOK_WAIT_US)\n    inrush = inrush + 1\n    If powok : Break : EndIf\n")),
    ("4.2 IDENT expected on 2712", lambda t: _sub(t, "  #V3D_EXPECT_TVER   = 7", "  #V3D_EXPECT_TVER   = 4")),
    ("MIDR guard removed", lambda t: _sub(t, "  If ((v3d_midr >> 24) & $FF) <> #V3D_MIDR_IMPL_ARM Or ((v3d_midr >> 4) & $FFF) <> #V3D_MIDR_PART_A76",
                                           "  If 0")),
    ("BCM2711 domain claim kept on 2712", lambda t: _sub(t, "  v3d_domainReply = -1\n  v3d_powerReply  = -1\n  CompilerElse\n",
                                                          "  v3d_domainReply = v3d_MbxIdState(#V3D_TAG_SET_DOMAIN_STATE, #V3D_DOMAIN_ID_NEW, #V3D_MBX_STATE_ON, 1)\n  v3d_powerReply  = -1\n  CompilerElse\n")),
    ("binning runs 4.2 packets on 2712", lambda t: _sub(
        t, "binning packets change shape (vault \"GPU - V3D 7.1 port plan\", D2-D4). Refused by\n"
           "  ; name rather than run with 4.2 offsets on a 7.1 part.\n"
           "  v3d_err = #V3D_ERR_NOT_PORTED\n  ProcedureReturn #V3D_ERR_NOT_PORTED\n",
        "binning packets change shape (vault \"GPU - V3D 7.1 port plan\", D2-D4).\n")),
    ("PM password dropped", lambda t: _sub(t, "  PokeL(#V3D_PM_BASE + off, #V3D_PM_PASSWORD | (value & $00FFFFFF))",
                                            "  PokeL(#V3D_PM_BASE + off, value & $00FFFFFF)")),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compiler", required=True)
    ap.add_argument("--mutate", action="store_true")
    a = ap.parse_args()
    compiler = resolve_compiler(a.compiler)
    rc = 0
    with tempfile.TemporaryDirectory(prefix="v3d71tfu-") as td:
        td = pathlib.Path(td)
        errs = not_ported((ROOT / LIB_REL).read_text(encoding="utf-8").replace("\r\n", "\n"))
        img = build(ROOT, td, compiler, "probe.img")
        errs += payload_window(img, None)
        errs += scenarios(img)
        for e in errs:
            print("FAIL", e)
        print(f"a64_v3d71_tfu_check: healthy + already-powered + 8 refusals + 3 not-ported "
              f"refusals + the payload window, {len(errs)} failure(s)")
        rc = 1 if errs else 0
        if a.mutate:
            lib = (ROOT / LIB_REL).read_text(encoding="utf-8").replace("\r\n", "\n")
            killed = 0
            for i, (label, fn) in enumerate(MUTANTS):
                mroot = td / f"m{i}"
                for rel in COPY_RELS:
                    (mroot / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(ROOT / rel, mroot / rel)
                try:
                    mlib = fn(lib)
                    (mroot / LIB_REL).write_text(mlib, encoding="utf-8")
                    merr = not_ported(mlib) or scenarios(build(mroot, td, compiler, f"m{i}.img"))
                except SystemExit as e:
                    merr = [str(e)]
                killed += bool(merr)
                print(f"MUTANT {label}: {'killed' if merr else 'SURVIVED'}"
                      + (f" ({merr[0][:100]!r})" if merr else ""), flush=True)
            print(f"mutants: {killed}/{len(MUTANTS)} killed")
            if killed != len(MUTANTS):
                rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

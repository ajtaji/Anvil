#!/usr/bin/env python3
"""Desk gate for step 3 of the Pi 5 GPU port: a V3D 7.1 compute dispatch.

Builds RaspberryPi5/Tests/v3d71_csd_probe.pi5 with `-t pi5`. The probe calls
RaspberryPi4/Lib/v3d.pi4 (the 7.1 CSD queue) and RaspberryPi4/Lib/v3dqpu.pi4
(the #PMF_CHIP = 2712 QPU packer) to build and dispatch a sixteen-lane
program that writes seed | lane to out[lane].

TWO INDEPENDENT WITNESSES:

  1. EVERY INSTRUCTION WORD the packer wrote into the code page must equal
     tools/v3d71_qpu.py's pack(assemble(text), strict=True) for the
     program's text, in order - the oracle transcribed from Mesa 61f25904
     qpu_pack.c and checked against Mesa's own vectors and py-videocore7.
  2. THE DISPATCH RUNS in a model of the 7.1 CSD (pinned v3d_regs.h:407-464,
     v3d_sched.c:411-424: CFG1..6, CFG7 = 0, then CFG0 kicks; CSD_STATUS
     NUM_COMPLETED; CSDDONE = bit 6), whose QPU executes the words by
     DECODING THEM WITH THE ORACLE (unpack) - so a word the packer got wrong
     either fails witness 1 or computes something else here.

The rest is reused by import: the PM/SMS/IDENT/mailbox/MMU models and the
MMIO loop of a64_v3d71_tfu_check.py (itself built on stage 1's model and
the Pi 4 gate's Firmware and V3dMmu).

Also checked in the source: on a 2712 build the 4.2 mux setters mark the
instruction and V3dQpuPack refuses it (#V3DQ_ERR_NOT_PORTED).

WHAT IT CANNOT PROVE: QPU timing - register-file write latency, the TMU
pipeline, thread switches - the model executes one instruction at a time.
The program leaves a gap between every producer and its consumer on
purpose. The silicon run answers the rest.

Run:  py -3 -B tools/a64/a64_v3d71_csd_check.py --compiler <PureMetalForge.exe> [--mutate]
"""
from __future__ import annotations

import argparse
import pathlib
import re
import shutil
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools"))
import a64_v3d71_tfu_check as T  # noqa: E402
import v3d71_qpu as Q  # noqa: E402
from pmf_compiler import resolve_compiler  # noqa: E402

PROBE_REL = pathlib.Path("RaspberryPi5/Tests/v3d71_csd_probe.pi5")
QPU_REL = pathlib.Path("RaspberryPi4/Lib/v3dqpu.pi4")
LIB_REL = T.LIB_REL
COPY_RELS = T.COPY_RELS[1:] + (PROBE_REL, QPU_REL)

CODE, UNIF, OUT = 0x04410000, 0x04411000, 0x04412000       # the probe's pages
CODE_VA, UNIF_VA, OUT_VA = 0x10000, 0x11000, 0x12000
SEED, POISON, LANES = 0xA5C30000, 0xA5A5A5A5, 16

# The program's text - the probe's header, instruction for instruction.
TEXT = [
    "nop ; nop ; ldunifrf.rf0",
    "nop ; nop ; ldunifrf.rf1",
    "eidx rf2 ; nop",
    "nop ; nop",
    "shl rf3, rf2, 2 ; nop",
    "or rf4, rf2, rf1 ; nop",
    "add rf3, rf3, rf0 ; nop",
    "nop ; mov tmud, rf4",
    "nop ; mov tmua, rf3",
    "tmuwt - ; nop",
    # V3dQpuThreadEnd: the last-THRSW pair, two slots, the end, three slots
    "nop ; nop ; thrsw", "nop ; nop ; thrsw", "nop ; nop", "nop ; nop",
    "nop ; nop ; thrsw", "nop ; nop", "nop ; nop", "nop ; nop",
]

# ---- the 7.1 CSD, pinned v3d_regs.h ---------------------------------------
CSD_STATUS = 0x900
CFG = {0x930 + 4 * i: i for i in range(8)}                  # CFG0..CFG7
CFG42 = range(0x904, 0x920)                                 # the 4.2 queue
CTL_INT_STS, CTL_INT_CLR = T.K["V3D_CTL_INT_STS"], T.K["V3D_CTL_INT_CLR"]
CSDDONE71 = 1 << 6                                          # V3D_INT_CSDDONE(71)


class Qpu71:
    """Executes decoded 7.1 words, sixteen lanes, one at a time."""

    def __init__(self, mmu, read_unif):
        self.mmu = mmu
        self.read_unif = read_unif
        self.rf = [[0] * LANES for _ in range(64)]
        self.tmud = None
        self.stores: list[tuple[int, int]] = []

    def _src(self, ins, raddr, imm_sig, lane):
        if imm_sig in ins.sig:
            return Q.SMALL_IMMEDIATES[raddr]
        return self.rf[raddr][lane]

    def _alu(self, op, a, b, lane):
        m = 0xFFFFFFFF
        return {"add": lambda: (a + b) & m, "sub": lambda: (a - b) & m,
                "shl": lambda: (a << (b & 31)) & m, "shr": lambda: a >> (b & 31),
                "and": lambda: a & b, "or": lambda: a | b, "xor": lambda: a ^ b,
                "mov": lambda: a, "eidx": lambda: lane, "tidx": lambda: 0,
                "umul24": lambda: ((a & 0xFFFFFF) * (b & 0xFFFFFF)) & m}[op]()

    def step(self, ins) -> None:
        if ins.kind != "alu" or ins.ac or ins.mc or ins.apf or ins.mpf or ins.auf or ins.muf:
            raise SystemExit(f"a64_v3d71_csd_check: the model has no branches or flags: {Q.disasm_instr(ins)}")
        writes = []
        for unit, alu, sa, sb in (("add", ins.add, "small_imm_a", "small_imm_b"),
                                  ("mul", ins.mul, "small_imm_c", "small_imm_d")):
            if alu.op in ("nop", "tmuwt"):
                continue
            if alu.op not in ("add", "sub", "shl", "shr", "and", "or", "xor", "mov", "eidx",
                              "tidx", "umul24"):
                raise SystemExit(f"a64_v3d71_csd_check: the model does not execute {alu.op}")
            vals = [self._alu(alu.op, self._src(ins, alu.a.raddr, sa, ln),
                              self._src(ins, alu.b.raddr, sb, ln), ln) for ln in range(LANES)]
            writes.append((alu.waddr, alu.magic, vals))
        if "ldunifrf" in ins.sig:
            u = self.read_unif()
            if ins.sig_magic:
                raise SystemExit("a64_v3d71_csd_check: ldunifrf to a magic address")
            writes.append((ins.sig_addr, False, [u] * LANES))
        for waddr, magic, vals in writes:
            if not magic:
                self.rf[waddr] = vals
            elif waddr == 11:                          # tmud
                self.tmud = vals
            elif waddr == 12:                          # tmua: the store fires
                if self.tmud is None:
                    raise SystemExit("a64_v3d71_csd_check: TMUA written with no TMUD")
                for ln in range(LANES):
                    if self.mmu.write32(vals[ln], self.tmud[ln]):
                        self.stores.append((vals[ln], self.tmud[ln]))
                self.tmud = None
            else:
                raise SystemExit(f"a64_v3d71_csd_check: write to magic waddr {waddr} not modelled")


class Pi5Csd(T.Pi5V3d):
    """The TFU gate's model plus the 7.1 CSD queue and a QPU that runs it."""

    def __init__(self, mem, tfu_mode="normal", csd_mode="normal", **kw):
        super().__init__(mem, tfu_mode, **kw)
        self.mem = mem
        self.csd_mode = csd_mode
        self.cfg: dict[int, int] = {}
        self.cfg_order: list[int] = []
        self.completed = 0
        self.core_int = 0
        self.words: list[int] = []
        self.qpu = None

    def core_read(self, off, where):
        if off in (0x0, 0x4, 0x8):
            return super().core_read(off, where)
        if not self.v3d_ready():
            raise T.S1.Hang(f"a64_v3d71_csd_check: CORE READ +${off:X} before V3D was ready\n  at {where}")
        if off == CSD_STATUS:
            return (self.completed & 0xFF) << 4
        if off == CTL_INT_STS:
            return self.core_int
        return super().core_read(off, where)

    def core_write(self, off, v, where):
        if not self.v3d_ready():
            raise T.S1.Hang(f"a64_v3d71_csd_check: CORE WRITE +${off:X} before V3D was ready\n  at {where}")
        if off in CFG42:
            raise SystemExit(f"a64_v3d71_csd_check: WRITE to core ${off:X}, the V3D 4.2 CSD queue. "
                             f"On 7.1 it is at $930 (v3d_regs.h:415)\n  at {where}")
        if off == CTL_INT_CLR:
            self.core_int &= ~v
            return
        if off in CFG:
            i = CFG[off]
            self.cfg[i] = v
            self.cfg_order.append(i)
            if i == 0:
                self._launch(where)
            return
        super().core_write(off, v, where)

    def _launch(self, where):
        order = self.cfg_order[-8:]
        if order != [1, 2, 3, 4, 5, 6, 7, 0]:
            raise SystemExit(f"a64_v3d71_csd_check: CSD launched with writes {self.cfg_order}; "
                             "v3d_sched.c:411-424 writes CFG1..CFG6, CFG7 = 0, then CFG0")
        if self.cfg[7] != 0:
            raise SystemExit("a64_v3d71_csd_check: CFG7 was not written 0 (v3d_sched.c:415-421)")
        c = self.cfg
        n_wg = [(c[i] >> 16) & 0xFFFF for i in range(3)]
        wg_size = c[3] & 0xFF
        if n_wg != [1, 1, 1] or wg_size != LANES:
            raise SystemExit(f"a64_v3d71_csd_check: dispatch {n_wg} x {wg_size}; the probe asks for one "
                             "workgroup of sixteen")
        code_va, flags = c[5] & ~7, c[5] & 7
        unif_va = c[6]
        if flags:
            raise SystemExit(f"a64_v3d71_csd_check: CFG5 flags {flags}; the program is single-threaded")
        if self.csd_mode == "dead":
            return
        # Fetch and run.
        unif = [unif_va]

        def read_unif():
            w = self.mmu.read32(unif[0])
            unif[0] += 4
            return w
        self.qpu = Qpu71(self.mmu, read_unif)
        pc, thrsw_pair, prev_thrsw, end_at = code_va, False, False, None
        for n in range(1000):
            lo, hi = self.mmu.read32(pc), self.mmu.read32(pc + 4)
            if lo is None or hi is None:
                return
            word = lo | (hi << 32)
            self.words.append(word)
            ins = Q.unpack(word)
            self.qpu.step(ins)
            if "thrsw" in ins.sig:
                if thrsw_pair and end_at is None:
                    end_at = n + 3
                if prev_thrsw:
                    thrsw_pair = True
                prev_thrsw = True
            else:
                prev_thrsw = False
            if end_at is not None and n >= end_at:
                break
            pc += 8
        else:
            raise SystemExit("a64_v3d71_csd_check: the program never ended (no program-end THRSW)")
        self.completed = (self.completed + 1) & 0xFF
        if self.csd_mode != "no_int":
            self.core_int |= CSDDONE71


def expected_words():
    return [Q.pack(Q.assemble(t), strict=True) for t in TEXT]


def source_checks(qpu: str) -> list[str]:
    errs = []
    m = re.search(r"(?ms)^Procedure\.i V3dQpuPack\(\)\n(.*?)^EndProcedure", qpu)
    if not m or not re.search(r"CompilerIf #PMF_CHIP = 2712\s+If v3dq_legacy <> 0\s+"
                              r"ProcedureReturn v3dq_Fail\(#V3DQ_ERR_NOT_PORTED\)", m.group(1)):
        errs.append("source: V3dQpuPack does not refuse a 4.2 mux operand on 2712")
    for name in ("V3dQpuAdd", "V3dQpuMul", "V3dQpuRaddr"):
        mm = re.search(rf"(?ms)^Procedure {name}\([^\n]*\)\n(.*?)^EndProcedure", qpu)
        if not mm or "v3dq_legacy = 1" not in mm.group(1):
            errs.append(f"source: {name} does not mark a 4.2 operand on 2712")
    return errs


def scenarios(img) -> list[str]:
    errs = []

    def need(c, w):
        if not c:
            errs.append(w)
    want = expected_words()
    rc, m, fw, mem = T.run(img, model_cls=Pi5Csd)
    need(rc == 0x71, f"healthy: rc ${rc:X}, want $71\n{m.uart.decode(errors='replace')[-700:]}")
    got = [sum(mem.get(CODE + 8 * i + k, 0) << (8 * k) for k in range(8)) for i in range(len(want) + 1)]
    for i, (g, w) in enumerate(zip(got, want)):
        if g != w:
            try:
                gt = Q.disasm(g)
            except Exception as e:   # noqa: BLE001
                gt = f"undecodable ({e})"
            errs.append(f"word {i}: packer ${g:016X} '{gt}', oracle ${w:016X} '{TEXT[i]}'")
    need(got[len(want)] == 0, "the packer wrote past the program")
    if rc == 0x71:
        outw = [sum(mem.get(OUT + 4 * i + k, 0) << (8 * k) for k in range(4)) for i in range(LANES)]
        need(outw == [SEED | i for i in range(LANES)], f"healthy: out {[hex(x) for x in outw]}")
    for label, kw, want_rc in (("CSD dead", dict(csd_mode="dead", tick_step=65536), 0x400 + 25),
                               ("CSDDONE never", dict(csd_mode="no_int"), 0x500)):
        try:
            rc, *_ = T.run(img, model_cls=Pi5Csd, **kw)
        except SystemExit as e:
            errs.append(f"{label}: stopped: {str(e)[:200]}")
            continue
        need(rc == want_rc, f"{label}: rc ${rc:X}, want ${want_rc:X}")
    return errs


def _sub(t, old, new):
    if t.count(old) < 1:
        raise SystemExit(f"mutant anchor missing: {old[:70]!r}")
    return t.replace(old, new, 1)


# (file, label, mutation)
MUTANTS = [
    (LIB_REL, "CSD queue at the 4.2 offsets", lambda t: _sub(t, "  #V3D_CSD_QUEUED_CFG0 = $00930", "  #V3D_CSD_QUEUED_CFG0 = $00904")),
    (LIB_REL, "CFG7 never written", lambda t: _sub(t, "  V3dCoreWrite(#V3D_CSD_QUEUED_CFG7, 0)\n", "")),
    (LIB_REL, "CSDDONE at the 4.2 bit", lambda t: _sub(t, "  #V3D_CTL_INT_CSDDONE = 64 ", "  #V3D_CTL_INT_CSDDONE = 128 ")),
    (QPU_REL, "or packed as xor (183)", lambda t: _sub(t, "    Case #V3DQ_A_OR   : opcode = 182", "    Case #V3DQ_A_OR   : opcode = 183")),
    (QPU_REL, "immediate B on the A signal row", lambda t: _sub(t, "    Case #V3DQ_SIG_SMIMM : ProcedureReturn 15", "    Case #V3DQ_SIG_SMIMM : ProcedureReturn 14")),
    (QPU_REL, "mul mov with .ul unpack (rd 7)", lambda t: _sub(t, "      rd = 3                ; int32 unpack none", "      rd = 7                ; int32 unpack none")),
    (QPU_REL, "nop half packs the 4.2 magic NOP", lambda t: _sub(t, "  If hasDst = 0\n    ProcedureReturn 0\n", "  If hasDst = 0\n    ProcedureReturn 70\n")),
    (QPU_REL, "raddr c and d swapped", lambda t: _sub(t, "  #V3DQ_RADDR_C_SHIFT = 18\n  #V3DQ_RADDR_D_SHIFT = 12", "  #V3DQ_RADDR_C_SHIFT = 12\n  #V3DQ_RADDR_D_SHIFT = 18")),
    (QPU_REL, "ldunifrf on the thrsw row", lambda t: _sub(t, "    Case #V3DQ_SIG_LDUNIFRF : ProcedureReturn 12", "    Case #V3DQ_SIG_LDUNIFRF : ProcedureReturn 13")),
    (QPU_REL, "eidx selector 1 (tidx)", lambda t: _sub(t, "    Case #V3DQ_A_EIDX : opcode = 187 : rb = 2", "    Case #V3DQ_A_EIDX : opcode = 187 : rb = 1")),
    (QPU_REL, "4.2 mux operand accepted on 2712", lambda t: _sub(t, "  If v3dq_legacy <> 0\n    ProcedureReturn v3dq_Fail(#V3DQ_ERR_NOT_PORTED)\n  EndIf\n", "")),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compiler", required=True)
    ap.add_argument("--mutate", action="store_true")
    a = ap.parse_args()
    compiler = resolve_compiler(a.compiler)
    rc = 0
    with tempfile.TemporaryDirectory(prefix="v3d71csd-") as td:
        td = pathlib.Path(td)
        errs = source_checks((ROOT / QPU_REL).read_text(encoding="utf-8").replace("\r\n", "\n"))
        errs += scenarios(T.build(ROOT, td, compiler, "csd.img", PROBE_REL))
        for e in errs:
            print("FAIL", e)
        print(f"a64_v3d71_csd_check: {len(TEXT)} words against the oracle, healthy run + 2 "
              f"refusals + source checks, {len(errs)} failure(s)")
        rc = 1 if errs else 0
        if a.mutate:
            killed = 0
            for i, (rel, label, fn) in enumerate(MUTANTS):
                mroot = td / f"m{i}"
                for r in COPY_RELS:
                    (mroot / r).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(ROOT / r, mroot / r)
                try:
                    txt = fn((ROOT / rel).read_text(encoding="utf-8").replace("\r\n", "\n"))
                    (mroot / rel).write_text(txt, encoding="utf-8")
                    merr = (source_checks(txt) if rel == QPU_REL else []) \
                        or scenarios(T.build(mroot, td, compiler, f"m{i}.img", PROBE_REL))
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

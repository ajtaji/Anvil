#!/usr/bin/env python3
"""Executable gate for RaspberryPi4/Lib/v3dqpu.pi4 - the QPU assembler.

Run:
  python tools/a64/a64_v3d_qpu_check.py --compiler PureMetalForge.exe
  python tools/a64/a64_v3d_qpu_check.py --compiler PureMetalForge.exe --mutate

=====================================================================
 WHERE THE EXPECTED WORDS COME FROM, AND HOW INDEPENDENT THEY ARE
=====================================================================

The expected 64-bit encodings for the corpus are GOLDEN WORDS produced
by py-videocore6 (Idein Inc., github.com/Idein/py-videocore6, commit
175741a389348a739a7d2bf559b9d302d7e390a9, assembler.py, 1258 lines), a
complete QPU assembler written by other people, from the same silicon,
that runs real compute kernels on real Raspberry Pi 4 boards.  They
were produced once by driving that assembler's public API with the
program spelled beside each word in PV6_CORPUS below, and are PINNED in
this file.  None of that project's code is in this repository and this
gate does not import it.

So the central comparison is v3dqpu.pi4's output against a recorded
answer from an independent implementation.  It is only as good as the
recording: a pinned word cannot notice a later change to py-videocore6,
and anyone wanting to re-derive a word can run that assembler on the
spelling printed beside it.

The encoding TABLES (field layout, signal table, small immediates, both
opcode tables, operand counts, the substituted muxes, the VPM waddr and
MA rules, the magic write addresses) are pinned from Mesa, tag
mesa-24.3.4 (commit 769e51468b49b2a42f0a0eaf71cf9eed5ff4e5de),
src/broadcom/qpu/qpu_pack.c, qpu_instr.c and qpu_instr.h, with line
ranges beside each table.  They were read out of those files by a
parser, not typed.  v3dqpu.pi4's constants and Select arms are checked
against them.  That half is two readings of the same Mesa source and is
weaker evidence than the golden words.

A THIRD, ANVIL-OWNED WITNESS.  tools/v3d42_qpu_decode.py is an
independent V3D 4.2 decoder in this repository that imports nothing from
the packer.  Every word the library emits for the corpus must decode
under it, and the seven LDVPM words - which py-videocore6 cannot encode -
must decode to the right operation, destination and operands.  That
lifts those seven above "a model agreeing with a model", though both the
decoder and the packer were still written from Mesa.

=====================================================================
 WHAT THIS GATE CANNOT DO.  READ THIS BEFORE TRUSTING A GREEN RUN.
=====================================================================

 1. IT CANNOT SAY THE QPU WILL EXECUTE ANY OF THIS.  There is no QPU in
    the A64 interpreter.  Two encoders agreeing means the encoding is
    transcribed right, not that the silicon decodes it the way both
    think.  Only pi4V3dCsd.pi4 on the board can say that, and only
    about the instructions it runs.

 2. WHERE py-videocore6 HAS NO OPINION, THE CHECK IS WEAKER.  Its
    operation table has no fxcd, xcd, fycd, ycd, flafirst, flnafirst,
    vadd or vsub.  v3dqpu.pi4 encodes all eight; THEY ARE UNWITNESSED
    and are kept out of the corpus rather than compared against this
    file's own reading.  The run prints them by name.

    The seven LDVPM operations are also absent from py-videocore6, but a
    vertex shader cannot read an attribute without LDVPMV_IN, so they
    are in the corpus as kind 'X': expected words assembled here from
    the pinned Mesa tables, plus the Anvil decoder check above.

 3. THE REFUSALS ARE NOT ORACLE-CHECKED.  They are checked against codes
    named in this gate, which is internal consistency only.

 4. IT CANNOT CATCH A CACHE COHERENCY BUG.  v3dqpu.pi4 does no cache
    maintenance; the flush belongs to v3d.pi4 and a64_v3d_check.py.

 5. IT CANNOT VALIDATE THE HAZARD RULES AGAINST HARDWARE.  Mesa's
    qpu_validate.c states them; nothing here measures them.

 6. NO PART OF THIS GATE TOUCHES A SERIAL PORT OR THE BOARD.

=====================================================================
 WHAT IT DOES
=====================================================================

 1. Builds RaspberryPi4/Examples/Diagnostics/pi4V3dQpuAsm.pi4 with the
    compiler named by --compiler and RUNS IT in tools/a64/a64_interp.py,
    with every memory access alignment-checked.  The encodings compared
    are the ones the compiled ARM code produced.

 2. Compares all sixty-four bits of every corpus instruction against the
    pinned py-videocore6 words, by name and in order.

 3. Checks v3dqpu.pi4's constants and Select arms against the pinned
    Mesa tables.

 4. Compares the compute shader the probe builds through the emitter
    against py-videocore6's pinned assembly of the same shader, and
    requires pi4V3dCsd.pi4 to build the identical shader.

 5. Checks sixteen refusals and the hazard refusals.

 6. Decodes every emitted word with tools/v3d42_qpu_decode.py.

 7. --mutate injects faults into a TEMPORARY COPY of v3dqpu.pi4 (the tree
    is never written), rebuilds and re-runs, and requires every fault to
    be caught.

=====================================================================
 THE ONE PLACE THE TWO IMPLEMENTATIONS DISAGREE
=====================================================================

 A BRANCH WITH UB CLEAR.  Mesa writes the BDU field only when UB is set
 (qpu_pack.c); py-videocore6 defaults bdu to 1 and writes it
 unconditionally.  The hardware ignores BDU when UB is clear.
 v3dqpu.pi4 writes what the caller asked for.  The corpus therefore
 contains "br_bdu0", the one entry whose expected value is the golden
 word with bits 17:15 cleared.  It is labelled in the output.

=====================================================================
 HOLES NO MUTANT CAN REACH
=====================================================================

 U-1  The eight unwitnessed operations above: their table rows are
      checked, their packing is not.
 U-2  The ROTATE signal: py-videocore6 attaches rotate-specific operand
      rewriting that v3dqpu.pi4 deliberately does not implement, so a
      corpus entry would compare two different things.
 U-3  The MSFIGN field of a branch: py-videocore6 hard-codes it to 0, so
      a mutant that shifted it would survive and is deliberately not
      listed.
"""

import argparse
import os
import pathlib
import re
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(__file__).resolve().parents[2]
LIB = ROOT / "RaspberryPi4" / "Lib" / "v3dqpu.pi4"
PROBE = ROOT / "RaspberryPi4" / "Examples" / "Diagnostics" / "pi4V3dQpuAsm.pi4"
CSD_PROBE = ROOT / "RaspberryPi4" / "Examples" / "Diagnostics" / "pi4V3dCsd.pi4"
LIB_INCLUDE = 'XIncludeFile "RaspberryPi4/Lib/v3dqpu.pi4"'

sys.path.insert(0, str(HERE))
from a64_interp import A64  # noqa: E402
sys.path.insert(0, str(ROOT / "tools"))
import v3d42_qpu_decode as QD  # noqa: E402
import sys as _pmfsys
import pathlib as _pmfpath
_pmfsys.path.insert(0, str(_pmfpath.Path(__file__).resolve().parents[1]))
from pmf_compiler import resolve_compiler  # noqa: E402

LOAD = 0x400000
STACK = 0x3000000
LOADER_LR = 0xDEADBEE0

UART_DR = 0xFE201000
UART_FR = 0xFE201018

# =====================================================================
#  PINNED REFERENCE DATA
#
#  Mesa tables: Mesa, tag mesa-24.3.4, commit 769e51468b49b2a42f0a0eaf71cf9eed5ff4e5de,
#  src/broadcom/qpu/{qpu_pack.c, qpu_instr.c, qpu_instr.h}.
#  They were read out of those files by a parser and recorded here; the
#  line ranges name where each table lives in that tag.  No Mesa code is
#  in this repository.
#
#  Golden words: py-videocore6 (Idein Inc.), commit
#  175741a389348a739a7d2bf559b9d302d7e390a9, assembler.py.  Each word is
#  what that assembler's public API produced for the spelling beside it,
#  inside its @qpu decorator.  No py-videocore6 code is in this
#  repository.
# =====================================================================

# {name: (shift, high bit, low bit)}, qpu_pack.c:47-111.
FIELD_SHIFTS = {
    'OP_MUL': (58, 63, 58), 'SIG': (53, 57, 53), 'COND': (46, 52, 46),
    'WADDR_M': (38, 43, 38), 'BRANCH_ADDR_LOW': (35, 55, 35), 'WADDR_A': (32, 37, 32),
    'BRANCH_COND': (32, 34, 32), 'BRANCH_ADDR_HIGH': (24, 31, 24), 'OP_ADD': (24, 31, 24),
    'MUL_B': (21, 23, 21), 'BRANCH_MSFIGN': (21, 22, 21), 'MUL_A': (18, 20, 18),
    'RADDR_C': (18, 23, 18), 'ADD_B': (15, 17, 15), 'BRANCH_BDU': (15, 17, 15),
    'ADD_A': (12, 14, 12), 'BRANCH_BDI': (12, 13, 12), 'RADDR_D': (12, 17, 12),
    'RADDR_A': (6, 11, 6), 'RADDR_B': (0, 5, 0), 'MM': (45, 45, 45),
    'MA': (44, 44, 44), 'BRANCH_UB': (14, 14, 14),
}

# v3d42_sig_map, qpu_pack.c:131-161: {frozenset(signal names): index}.
SIG_TABLE = {
    frozenset(()): 0,
    frozenset(('ldtlb',)): 16,
    frozenset(('ldtlbu',)): 17,
    frozenset(('ldtmu',)): 4,
    frozenset(('ldtmu', 'ldunif')): 6,
    frozenset(('ldtmu', 'ldunif', 'thrsw')): 7,
    frozenset(('ldtmu', 'smimm')): 31,
    frozenset(('ldtmu', 'thrsw')): 5,
    frozenset(('ldunif',)): 2,
    frozenset(('ldunif', 'ldvary')): 10,
    frozenset(('ldunif', 'ldvary', 'thrsw')): 11,
    frozenset(('ldunif', 'thrsw')): 3,
    frozenset(('ldunifa',)): 24,
    frozenset(('ldunifarf',)): 25,
    frozenset(('ldunifrf',)): 12,
    frozenset(('ldunifrf', 'thrsw')): 13,
    frozenset(('ldvary',)): 8,
    frozenset(('ldvary', 'smimm')): 14,
    frozenset(('ldvary', 'thrsw')): 9,
    frozenset(('ldvary', 'thrsw', 'wrtmuc')): 21,
    frozenset(('ldvary', 'wrtmuc')): 20,
    frozenset(('rotate',)): 23,
    frozenset(('smimm',)): 15,
    frozenset(('thrsw',)): 1,
    frozenset(('thrsw', 'wrtmuc')): 19,
    frozenset(('ucb',)): 22,
    frozenset(('wrtmuc',)): 18,
}

# small_immediates, qpu_pack.c:239-264.
SMALL_IMMEDIATES = [
    0x00000000, 0x00000001, 0x00000002, 0x00000003, 0x00000004, 0x00000005,
    0x00000006, 0x00000007, 0x00000008, 0x00000009, 0x0000000A, 0x0000000B,
    0x0000000C, 0x0000000D, 0x0000000E, 0x0000000F, 0xFFFFFFF0, 0xFFFFFFF1,
    0xFFFFFFF2, 0xFFFFFFF3, 0xFFFFFFF4, 0xFFFFFFF5, 0xFFFFFFF6, 0xFFFFFFF7,
    0xFFFFFFF8, 0xFFFFFFF9, 0xFFFFFFFA, 0xFFFFFFFB, 0xFFFFFFFC, 0xFFFFFFFD,
    0xFFFFFFFE, 0xFFFFFFFF, 0x3B800000, 0x3C000000, 0x3C800000, 0x3D000000,
    0x3D800000, 0x3E000000, 0x3E800000, 0x3F000000, 0x3F800000, 0x40000000,
    0x40800000, 0x41000000, 0x41800000, 0x42000000, 0x42800000, 0x43000000,
]

# v3d42_add_ops, qpu_pack.c:457-559: {operation: opcode_first}, first row only,
# which is the packer's own lookup rule.
ADD_OPS = {
    'FADD': 0, 'FADDNF': 0, 'VFPACK': 53, 'ADD': 56, 'SUB': 60, 'FSUB': 64,
    'MIN': 120, 'MAX': 121, 'UMIN': 122, 'UMAX': 123, 'SHL': 124, 'SHR': 125,
    'ASR': 126, 'ROR': 127, 'FMIN': 128, 'FMAX': 128, 'VFMIN': 176, 'AND': 181,
    'OR': 182, 'XOR': 183, 'VADD': 184, 'VSUB': 185, 'NOT': 186, 'NEG': 186,
    'FLAPUSH': 186, 'FLBPUSH': 186, 'FLPOP': 186, 'RECIP': 186, 'SETMSF': 186, 'SETREVF': 186,
    'NOP': 187, 'TIDX': 187, 'EIDX': 187, 'LR': 187, 'VFLA': 187, 'VFLNA': 187,
    'VFLB': 187, 'VFLNB': 187, 'FXCD': 187, 'XCD': 187, 'FYCD': 187, 'YCD': 187,
    'MSF': 187, 'REVF': 187, 'VDWWT': 187, 'IID': 187, 'SAMPID': 187, 'BARRIERID': 187,
    'TMUWT': 187, 'VPMWT': 187, 'FLAFIRST': 187, 'FLNAFIRST': 187, 'VPMSETUP': 187, 'LDVPMV_IN': 188,
    'LDVPMV_OUT': 188, 'LDVPMD_IN': 188, 'LDVPMD_OUT': 188, 'LDVPMP': 188, 'RSQRT': 188, 'EXP': 188,
    'LOG': 188, 'SIN': 188, 'RSQRT2': 188, 'LDVPMG_IN': 189, 'LDVPMG_OUT': 189, 'FCMP': 192,
    'VFMAX': 240, 'FROUND': 245, 'FTOIN': 245, 'FTRUNC': 245, 'FTOIZ': 245, 'FFLOOR': 246,
    'FTOUZ': 246, 'FCEIL': 246, 'FTOC': 246, 'FDX': 247, 'FDY': 247, 'STVPMV': 248,
    'STVPMD': 248, 'STVPMP': 248, 'ITOF': 252, 'CLZ': 252, 'UTOF': 252,
}

# v3d42_mul_ops, qpu_pack.c:561-574.
MUL_OPS = {
    'ADD': 1, 'SUB': 2, 'UMUL24': 3, 'VFMUL': 4, 'SMUL24': 9,
    'MULTOP': 10, 'FMOV': 14, 'NOP': 15, 'MOV': 15, 'FMUL': 16,
}

# add_op_args reduced to a source count, qpu_instr.c:387-501.
ADD_NUM_SRC = {
    'FADD': 2, 'FADDNF': 2, 'VFPACK': 2, 'ADD': 2, 'SUB': 2, 'FSUB': 2,
    'MIN': 2, 'MAX': 2, 'UMIN': 2, 'UMAX': 2, 'SHL': 2, 'SHR': 2,
    'ASR': 2, 'ROR': 2, 'FMIN': 2, 'FMAX': 2, 'VFMIN': 2, 'AND': 2,
    'OR': 2, 'XOR': 2, 'VADD': 2, 'VSUB': 2, 'NOT': 1, 'NEG': 1,
    'FLAPUSH': 1, 'FLBPUSH': 1, 'FLPOP': 1, 'RECIP': 1, 'SETMSF': 1, 'SETREVF': 1,
    'NOP': 0, 'TIDX': 0, 'EIDX': 0, 'LR': 0, 'VFLA': 0, 'VFLNA': 0,
    'VFLB': 0, 'VFLNB': 0, 'FXCD': 0, 'XCD': 0, 'FYCD': 0, 'YCD': 0,
    'MSF': 0, 'REVF': 0, 'VDWWT': 0, 'IID': 0, 'SAMPID': 0, 'BARRIERID': 0,
    'TMUWT': 0, 'VPMWT': 0, 'FLAFIRST': 0, 'FLNAFIRST': 0, 'VPMSETUP': 1, 'LDVPMV_IN': 1,
    'LDVPMV_OUT': 1, 'LDVPMD_IN': 1, 'LDVPMD_OUT': 1, 'LDVPMP': 1, 'RSQRT': 1, 'EXP': 1,
    'LOG': 1, 'SIN': 1, 'RSQRT2': 1, 'LDVPMG_IN': 2, 'LDVPMG_OUT': 2, 'FCMP': 2,
    'VFMAX': 2, 'FROUND': 1, 'FTOIN': 1, 'FTRUNC': 1, 'FTOIZ': 1, 'FFLOOR': 1,
    'FTOUZ': 1, 'FCEIL': 1, 'FTOC': 1, 'FDX': 1, 'FDY': 1, 'STVPMV': 2,
    'STVPMD': 2, 'STVPMP': 2, 'ITOF': 1, 'CLZ': 1, 'UTOF': 1, 'MOV': 1,
    'FMOV': 1, 'VPACK': 2, 'V8PACK': 2, 'V10PACK': 2, 'V11FPACK': 2, 'BALLOT': 1,
    'BCASTF': 1, 'ALLEQ': 1, 'ALLFEQ': 1, 'ROTQ': 2, 'ROT': 2, 'SHUFFLE': 2,
}

# ffs(mask) - 1 of each v3d42_add_ops row's a_mask and b_mask, first row
# only, qpu_pack.c:457-559: {operation: (a_first, b_first)}.
ADD_MUX_FIRSTS = {
    'FADD': (0, 0), 'FADDNF': (0, 0), 'VFPACK': (0, 0), 'ADD': (0, 0), 'SUB': (0, 0),
    'FSUB': (0, 0), 'MIN': (0, 0), 'MAX': (0, 0), 'UMIN': (0, 0), 'UMAX': (0, 0),
    'SHL': (0, 0), 'SHR': (0, 0), 'ASR': (0, 0), 'ROR': (0, 0), 'FMIN': (0, 0),
    'FMAX': (0, 0), 'VFMIN': (0, 0), 'AND': (0, 0), 'OR': (0, 0), 'XOR': (0, 0),
    'VADD': (0, 0), 'VSUB': (0, 0), 'NOT': (0, 0), 'NEG': (0, 1), 'FLAPUSH': (0, 2),
    'FLBPUSH': (0, 3), 'FLPOP': (0, 4), 'RECIP': (0, 5), 'SETMSF': (0, 6), 'SETREVF': (0, 7),
    'NOP': (0, 0), 'TIDX': (1, 0), 'EIDX': (2, 0), 'LR': (3, 0), 'VFLA': (4, 0),
    'VFLNA': (5, 0), 'VFLB': (6, 0), 'VFLNB': (7, 0), 'FXCD': (0, 1), 'XCD': (3, 1),
    'FYCD': (4, 1), 'YCD': (7, 1), 'MSF': (0, 2), 'REVF': (1, 2), 'VDWWT': (2, 2),
    'IID': (2, 2), 'SAMPID': (3, 2), 'BARRIERID': (4, 2), 'TMUWT': (5, 2), 'VPMWT': (6, 2),
    'FLAFIRST': (7, 2), 'FLNAFIRST': (0, 3), 'VPMSETUP': (0, 3), 'LDVPMV_IN': (0, 0), 'LDVPMV_OUT': (0, 0),
    'LDVPMD_IN': (0, 1), 'LDVPMD_OUT': (0, 1), 'LDVPMP': (0, 2), 'RSQRT': (0, 3), 'EXP': (0, 4),
    'LOG': (0, 5), 'SIN': (0, 6), 'RSQRT2': (0, 7), 'LDVPMG_IN': (0, 0), 'LDVPMG_OUT': (0, 0),
    'FCMP': (0, 0), 'VFMAX': (0, 0), 'FROUND': (0, 0), 'FTOIN': (0, 3), 'FTRUNC': (0, 4),
    'FTOIZ': (0, 7), 'FFLOOR': (0, 0), 'FTOUZ': (0, 3), 'FCEIL': (0, 4), 'FTOC': (0, 7),
    'FDX': (0, 0), 'FDY': (0, 4), 'STVPMV': (0, 0), 'STVPMD': (0, 0), 'STVPMP': (0, 0),
    'ITOF': (0, 0), 'CLZ': (0, 3), 'UTOF': (0, 4),
}

# The waddr / MA switch, qpu_pack.c:1549 (v3d42_qpu_add_pack, its first switch).
STVPM_WADDR = {'STVPMV': 0, 'STVPMD': 1, 'STVPMP': 2}
LDVPM_NO_MAGIC = frozenset(('LDVPMD_IN', 'LDVPMD_OUT', 'LDVPMG_IN', 'LDVPMG_OUT', 'LDVPMP', 'LDVPMV_IN', 'LDVPMV_OUT'))
LDVPM_OUT_MA = frozenset(('LDVPMD_OUT', 'LDVPMG_OUT', 'LDVPMV_OUT'))

# enum v3d_qpu_waddr, 4.x spellings, qpu_instr.h:93-138.
WADDRS = {
    'R0': 0, 'R1': 1, 'R2': 2, 'R3': 3, 'R4': 4, 'R5': 5,
    'NOP': 6, 'TLB': 7, 'TLBU': 8, 'TMU': 9, 'UNIFA': 9, 'TMUL': 10,
    'TMUD': 11, 'TMUA': 12, 'TMUAU': 13, 'VPM': 14, 'VPMU': 15, 'SYNC': 16,
    'SYNCU': 17, 'SYNCB': 18, 'RECIP': 19, 'RSQRT': 20, 'EXP': 21, 'LOG': 22,
    'SIN': 23, 'RSQRT2': 24, 'TMUC': 32, 'TMUS': 33, 'TMUT': 34, 'TMUR': 35,
    'TMUI': 36, 'TMUB': 37, 'TMUDREF': 38, 'TMUOFF': 39, 'TMUSCM': 40, 'TMUSF': 41,
    'TMUSLOD': 42, 'TMUHS': 43, 'TMUHSCM': 44, 'TMUHSF': 45, 'TMUHSLOD': 46, 'R5REP': 55,
}

# v3d_qpu_sig_writes_address, qpu_instr.c:1061-1073.
SIG_WRITES_ADDRESS = frozenset(('ldtlb', 'ldtlbu', 'ldtmu', 'ldunifarf', 'ldunifrf', 'ldvary'))

# The corpus, in probe order, as py-videocore6 spells it and the word it
# produced.  One line per 'I' or 'D' entry of NAMES.  The last spelling is
# the base for br_bdu0 (see the BDU note).
PV6_CORPUS = [
    ('nop()', 0x3C003186BB800000),
    ('tidx(r0)', 0x3C003180BB801000),
    ('eidx(r1)', 0x3C003181BB802000),
    ('lr(r0)', 0x3C003180BB803000),
    ('vfla(r0)', 0x3C003180BB804000),
    ('vflna(r0)', 0x3C003180BB805000),
    ('vflb(r0)', 0x3C003180BB806000),
    ('vflnb(r0)', 0x3C003180BB807000),
    ('msf(r0)', 0x3C003180BB810000),
    ('revf(r0)', 0x3C003180BB811000),
    ('iid(r0)', 0x3C003180BB812000),
    ('sampid(r0)', 0x3C003180BB813000),
    ('barrierid(syncb)', 0x3C003192BB814000),
    ('tmuwt()', 0x3C003186BB815000),
    ('vpmwt(r0)', 0x3C003180BB816000),
    ('bnot(r0, r1)', 0x3C003180BA801000),
    ('neg(r0, r1)', 0x3C003180BA809000),
    ('flapush(r0, r1)', 0x3C003180BA811000),
    ('flbpush(r0, r1)', 0x3C003180BA819000),
    ('flpop(r0, r1)', 0x3C003180BA821000),
    ('setmsf(r0, r1)', 0x3C003180BA831000),
    ('setrevf(r0, r1)', 0x3C003180BA839000),
    ('itof(r0, r1)', 0x3C003180FC801000),
    ('clz(r0, r1)', 0x3C003180FC819000),
    ('utof(r0, r1)', 0x3C003180FC821000),
    ('ftoin(r0, r1)', 0x3C003180F5819000),
    ('ftoiz(r0, r1)', 0x3C003180F5839000),
    ('ftouz(r0, r1)', 0x3C003180F6819000),
    ('ftoc(r0, r1)', 0x3C003180F6839000),
    ('fround(r0, r1)', 0x3C003180F5801000),
    ('ftrunc(r0, r1)', 0x3C003180F5821000),
    ('ffloor(r0, r1)', 0x3C003180F6801000),
    ('fceil(r0, r1)', 0x3C003180F6821000),
    ('fdx(r0, r1)', 0x3C003180F7801000),
    ('fdy(r0, r1)', 0x3C003180F7821000),
    ('recip(r0, r1)', 0x3C003180BA829000),
    ('rsqrt(r0, r1)', 0x3C003180BC819000),
    ('exp(r0, r1)', 0x3C003180BC821000),
    ('log(r0, r1)', 0x3C003180BC829000),
    ('sin(r0, r1)', 0x3C003180BC831000),
    ('rsqrt2(r0, r1)', 0x3C003180BC839000),
    ('add(r2, r0, r1)', 0x3C00318238808000),
    ('sub(r2, r0, r1)', 0x3C0031823C808000),
    ('imin(r2, r0, r1)', 0x3C00318278808000),
    ('imax(r2, r0, r1)', 0x3C00318279808000),
    ('umin(r2, r0, r1)', 0x3C0031827A808000),
    ('umax(r2, r0, r1)', 0x3C0031827B808000),
    ('shl(r2, r0, r1)', 0x3C0031827C808000),
    ('shr(r2, r0, r1)', 0x3C0031827D808000),
    ('asr(r2, r0, r1)', 0x3C0031827E808000),
    ('ror(r2, r0, r1)', 0x3C0031827F808000),
    ('band(r2, r0, r1)', 0x3C003182B5808000),
    ('bor(r2, r0, r1)', 0x3C003182B6808000),
    ('bxor(r2, r0, r1)', 0x3C003182B7808000),
    ('fadd(r2, r0, r1)', 0x3C00318205808000),
    ('fadd(r2, r1, r0)', 0x3C00318205808000),
    ('faddnf(r2, r0, r1)', 0x3C00318205801000),
    ('faddnf(r2, r1, r0)', 0x3C00318205801000),
    ('fmin(r2, r0, r1)', 0x3C00318285808000),
    ('fmin(r2, r1, r0)', 0x3C00318285808000),
    ('fmax(r2, r0, r1)', 0x3C00318285801000),
    ('fmax(r2, r1, r0)', 0x3C00318285801000),
    ('fsub(r2, r0, r1)', 0x3C00318245808000),
    ('fcmp(r2, r0, r1)', 0x3C003182C5808000),
    ('fadd(r2.pack("l"), r0, r1)', 0x3C00318215808000),
    ('fadd(r2.pack("h"), r0, r1)', 0x3C00318225808000),
    ('fadd(r2, r0.unpack("abs"), r1)', 0x3C00318201808000),
    ('fadd(r2, r0.unpack("l"), r1.unpack("h"))', 0x3C0031820B808000),
    ('nop().add(r2, r0, r1)', 0x04003086BB200000),
    ('nop().sub(r2, r0, r1)', 0x08003086BB200000),
    ('nop().umul24(r2, r0, r1)', 0x0C003086BB200000),
    ('nop().smul24(r2, r0, r1)', 0x24003086BB200000),
    ('nop().multop(r2, r0, r1)', 0x28003086BB200000),
    ('nop().fmul(r2, r0, r1)', 0x54003086BB200000),
    ('nop().mov(r2, r0)', 0x3C003086BBE00000),
    ('nop().mov(tmud, r0)', 0x3C0032C6BBE00000),
    ('nop().fmov(r2, r0)', 0x38003086BB200000),
    ('nop().fmul(r2.pack("l"), r0, r1)', 0x94003086BB200000),
    ('nop().fmul(r2, r0.unpack("abs"), r1.unpack("l"))', 0x48003086BB200000),
    ('nop().fmov(r2.pack("h"), r0)', 0x3C003086BB200000),
    ('add(r2, r0, r1).fmul(r3, r0, r1)', 0x540030C238208000),
    ('band(rf[3], r0, rf[1])', 0x3C002183B5830040),
    ('add(rf[10], rf[1], rf[2])', 0x3C00218A3883E042),
    ('shl(rf[5], rf[5], rf[6])', 0x3C0021857C83E146),
    ('add(r0, r1, 0)', 0x3DE0318038839000),
    ('add(r0, r1, 15)', 0x3DE031803883900F),
    ('add(r0, r1, -1)', 0x3DE031803883901F),
    ('add(r0, r1, -16)', 0x3DE0318038839010),
    ('nop().fmul(r0, r1, 1.0)', 0x55E03006BBE40028),
    ('nop().fmul(r0, r1, 2.0 ** -8)', 0x55E03006BBE40020),
    ('mov(rf[5], 1)', 0x3DE02185B683F001),
    ('nop(sig=thrsw)', 0x3C203186BB800000),
    ('nop(sig=ldunif)', 0x3C403186BB800000),
    ('nop(sig=ldunifa)', 0x3F003186BB800000),
    ('nop(sig=wrtmuc)', 0x3E403186BB800000),
    ('nop(sig=ucb)', 0x3EC03186BB800000),
    ('nop(sig=ldunifrf(rf[0]))', 0x3D803186BB800000),
    ('nop(sig=ldunifarf(rf[1]))', 0x3F207186BB800000),
    ('nop(sig=ldtmu(r4))', 0x3C913186BB800000),
    ('nop(sig=ldvary(rf[2]))', 0x3D00B186BB800000),
    ('nop(sig=ldtlb(rf[3]))', 0x3E00F186BB800000),
    ('nop(sig=ldtlbu(rf[4]))', 0x3E213186BB800000),
    ('nop(sig=[thrsw, ldunif])', 0x3C603186BB800000),
    ('nop(sig=[thrsw, ldunifrf(rf[7])])', 0x3DA1F186BB800000),
    ('nop(sig=[thrsw, wrtmuc])', 0x3E603186BB800000),
    ('nop(sig=[ldtmu(r4), ldunif])', 0x3CD13186BB800000),
    ('nop(sig=[thrsw, ldtmu(r4)])', 0x3CB13186BB800000),
    ('nop(sig=[ldvary(rf[1]), ldunif])', 0x3D407186BB800000),
    ('nop(sig=[thrsw, ldvary(rf[1])])', 0x3D207186BB800000),
    ('nop(sig=[ldvary(rf[2]), wrtmuc])', 0x3E80B186BB800000),
    ('add(r0, r1, r2, sig=ldtmu(r4))', 0x3C91318038811000),
    ('add(r0, r1, 15, sig=ldvary(rf[1]))', 0x3DC071803883900F),
    ('add(r0, r1, 15, sig=ldtmu(r4))', 0x3FF131803883900F),
    ('add(r0, r1, r2, cond="pushz")', 0x3C00718038811000),
    ('add(r0, r1, r2, cond="pushn")', 0x3C00B18038811000),
    ('add(r0, r1, r2, cond="pushc")', 0x3C00F18038811000),
    ('add(r0, r1, r2, cond="ifa")', 0x3C08318038811000),
    ('add(r0, r1, r2, cond="ifnb")', 0x3C0B318038811000),
    ('add(r0, r1, r2, cond="andz")', 0x3C01318038811000),
    ('add(r0, r1, r2, cond="norc")', 0x3C03F18038811000),
    ('add(r0, r1, r2).add(r3, r0, r1, cond="pushz")', 0x040470C038211000),
    ('add(r0, r1, r2).add(r3, r0, r1, cond="ifb")', 0x040D30C038211000),
    ('add(r0, r1, r2).add(r3, r0, r1, cond="andnz")', 0x040570C038211000),
    ('add(r0, r1, r2, cond="ifa").add(r3, r0, r1, cond="pushz")', 0x040870C038211000),
    ('add(r0, r1, r2, cond="pushz").add(r3, r0, r1, cond="ifa")', 0x040C70C038211000),
    ('add(r0, r1, r2, cond="ifa").add(r3, r0, r1, cond="ifb")', 0x041430C038211000),
    ('add(r0, r1, r2, cond="andz").add(r3, r0, r1, cond="ifa")', 0x041130C038211000),
    ('b(0, cond="always")', 0x0200000000009000),
    ('b(0x100, cond="a0")', 0x0200010200009000),
    ('b(0x100, cond="na0")', 0x0200010300009000),
    ('b(0x100, cond="alla")', 0x0200010400009000),
    ('b(0x100, cond="anyna")', 0x0200010500009000),
    ('b(0x100, cond="anya")', 0x0200010600009000),
    ('b(0x100, cond="allna")', 0x0200010700009000),
    ('b(0x1000, cond="always", absolute=True)', 0x0200100000008000),
    ('b(link, cond="always")', 0x020000000000A000),
    ('b(rf[7], cond="always")', 0x020000000000B1C0),
    ('b(0x100, cond="always", set_link=True)', 0x0200010000809000),
    ('b(0x100, cond="always").unif_addr(absolute=False)', 0x020001000000D000),
    ('b(0x100, cond="always").unif_addr(absolute=True)', 0x0200010000005000),
    ('b(0x100, cond="always").unif_addr(rf[9])', 0x020001000001D240),
    ('b(0x0ABCDEF8, cond="always")', 0x02BCDEF80A009000),
    ('b(0x100, cond="always")', 0x0200010000009000),
    ('vfpack(r0, r1, r2)', 0x3C00318035811000),
    ('vfpack(r0, r1.unpack("l"), r2.unpack("h"))', 0x3C0031803B811000),
    ('vfpack(tlbu, r1, r2)', 0x3C00318835811000),
    ('stvpmv(rf[0], r1, r2)', 0x3C002180F8811000),
    ('stvpmd(rf[1], r1, r2)', 0x3C002181F8811000),
    ('stvpmp(rf[2], r1, r2)', 0x3C002182F8811000),
    ('stvpmv(rf[0], r1, r2)', 0x3C002180F8811000),
]

# The compute shader pi4V3dQpuAsm.pi4 and pi4V3dCsd.pi4 build, as
# py-videocore6 spells and assembles it.
PV6_SHADER = [
    ('nop(sig=ldunifrf(rf[0]))', 0x3D803186BB800000),
    ('nop(sig=ldunifrf(rf[1]))', 0x3D807186BB800000),
    ('eidx(r0)', 0x3C003180BB802000),
    ('shl(r1, r0, 2)', 0x3DE031817C838002),
    ('add(r1, r1, rf[0])', 0x3C00318138831000),
    ('bor(r2, r0, rf[1])', 0x3C003182B6830040),
    ('nop().mov(tmud, r2)', 0x3C0032C6BBE80000),
    ('nop().mov(tmua, r1)', 0x3C003306BBE40000),
    ('tmuwt()', 0x3C003186BB815000),
    ('nop(sig=thrsw)', 0x3C203186BB800000),
    ('nop(sig=thrsw)', 0x3C203186BB800000),
    ('nop()', 0x3C003186BB800000),
    ('nop()', 0x3C003186BB800000),
    ('nop(sig=thrsw)', 0x3C203186BB800000),
    ('nop()', 0x3C003186BB800000),
    ('nop()', 0x3C003186BB800000),
    ('nop()', 0x3C003186BB800000),
]

# Operations confirmed ABSENT from py-videocore6's operation table
# (assembler.py at the commit above) when the words were pinned.
PV6_ABSENT = frozenset(('FLAFIRST', 'FLNAFIRST', 'FXCD', 'FYCD', 'LDVPMD_IN', 'LDVPMD_OUT', 'LDVPMG_IN', 'LDVPMG_OUT', 'LDVPMP', 'LDVPMV_IN', 'LDVPMV_OUT', 'VADD', 'VSUB', 'XCD', 'YCD'))

# The seven LDVPM words expected_x_words() produced from the tables above
# when they were pinned; check_pins() recomputes and compares.
PINNED_X_WORDS = {
    'ldvpmv_in': 0x3C0021A5BC8066E9,
    'ldvpmv_out': 0x3C0031A5BC8066E9,
    'ldvpmd_in': 0x3C0021A5BC80E6E9,
    'ldvpmd_out': 0x3C0031A5BC80E6E9,
    'ldvpmp': 0x3C0021A5BC8166E9,
    'ldvpmg_in': 0x3C0021A5BD82E6E9,
    'ldvpmg_out': 0x3C0031A5BD82E6E9,
}


# =====================================================================
#  PART 1 - THE PINNED ENCODING TABLES, AND THE LIBRARY'S TEXT
# =====================================================================

# Set only by mutate(): the text of the temporary mutated library copy,
# so the source-reading checks read what was compiled.
_LIB_TEXT = None


def _text(p: pathlib.Path) -> str:
    if not p.exists():
        raise SystemExit("a64_v3d_qpu_check: the source file %s is missing." % p)
    return p.read_text(encoding="utf-8", errors="replace")


def _lib_src() -> str:
    return _LIB_TEXT if _LIB_TEXT is not None else _text(LIB)


def lib_constant(name: str) -> int:
    """One #NAME = value out of v3dqpu.pi4, as the library states it."""
    m = re.search(r"^#%s\s*=\s*([^\s;]+)" % re.escape(name), _lib_src(), re.M)
    if not m:
        raise SystemExit("a64_v3d_qpu_check: v3dqpu.pi4 has no #%s constant." % name)
    tok = m.group(1)
    if tok.startswith("$"):
        return int(tok[1:], 16)
    return int(tok, 10)


def derive_field_shifts() -> dict:
    """{name: (shift, high, low)}, pinned from qpu_pack.c."""
    return dict(FIELD_SHIFTS)


def _sig_name(tok: str) -> str:
    """One signal's name in the spelling the pinned table uses.

    qpu_pack.c's table is written with shorthand macros - SMIMM_B for the
    V3D 4.2 small immediate and ROT for rotate - while the library calls
    them SMIMM and ROTATE.  SMIMM_A, _C and _D are 7.1 spellings that never
    appear in the 4.2 table, so collapsing them cannot merge two rows.
    """
    t = tok.lower()
    if t.startswith("smimm"):
        return "smimm"
    if t == "rot":
        return "rotate"
    return t


def derive_sig_table() -> dict:
    return dict(SIG_TABLE)


def derive_small_immediates() -> list:
    return list(SMALL_IMMEDIATES)


def derive_opcode_table(which: str) -> dict:
    return dict(ADD_OPS if which == "add" else MUL_OPS)


def derive_add_num_src() -> dict:
    return dict(ADD_NUM_SRC)


def derive_mux_firsts(which: str) -> dict:
    if which != "add":
        raise SystemExit("a64_v3d_qpu_check: only the ADD mux table is pinned.")
    return dict(ADD_MUX_FIRSTS)


def derive_vpm_rules():
    return dict(STVPM_WADDR), set(LDVPM_NO_MAGIC), set(LDVPM_OUT_MA)


def derive_waddrs() -> dict:
    return dict(WADDRS)


def derive_sig_writes_address() -> set:
    return set(SIG_WRITES_ADDRESS)


def lib_select_arms(proc: str) -> dict:
    """{Case expression text: returned integer} for one procedure."""
    m = re.search(r"^Procedure\.i %s\(.*?^EndProcedure" % re.escape(proc),
                  _lib_src(), re.M | re.S)
    if not m:
        raise SystemExit("a64_v3d_qpu_check: v3dqpu.pi4 has no %s() procedure." % proc)
    out = {}
    pending = None
    for line in m.group(0).splitlines():
        line = line.split(";")[0].strip()
        if line.startswith("Case "):
            pending = line[5:].strip()
        elif line.startswith("ProcedureReturn ") and pending is not None:
            tok = line.split()[1]
            try:
                out[pending] = int(tok, 10)
            except ValueError:
                pass
            pending = None
    return out


# =====================================================================
#  PART 2 - BUILDING AND RUNNING THE PROBE
# =====================================================================

def build(compiler: str, workdir: pathlib.Path, name: str,
          lib_text: str | None = None) -> pathlib.Path:
    """Compile the probe into workdir.  With lib_text, the probe is
    compiled against a temporary copy of v3dqpu.pi4 holding that text."""
    src = PROBE
    if lib_text is not None:
        lib_copy = workdir / ("mutant_" + LIB.name)
        lib_copy.write_text(lib_text, encoding="utf-8")
        probe_text = _text(PROBE)
        if LIB_INCLUDE not in probe_text:
            raise SystemExit("a64_v3d_qpu_check: pi4V3dQpuAsm.pi4 no longer has the "
                             "line %s, so a mutant library cannot be substituted."
                             % LIB_INCLUDE)
        src = workdir / ("mutant_" + PROBE.name)
        src.write_text(probe_text.replace(
            LIB_INCLUDE, 'XIncludeFile "%s"' % lib_copy.as_posix()), encoding="utf-8")
    img = workdir / name
    if img.exists():
        img.unlink()
    r = subprocess.run(
        [compiler, "--compile", str(src), "-t", "pi4", "--entry-returns",
         "--load-addr", hex(LOAD), "--stack-addr", hex(STACK), "-o", str(img)],
        cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
        capture_output=True, text=True)
    if r.returncode != 0 or not img.exists():
        raise SystemExit("a64_v3d_qpu_check: the probe did not build (exit code %d).\n%s%s"
                         % (r.returncode, r.stdout, r.stderr))
    return img


def _symbols(img: pathlib.Path):
    dbg = pathlib.Path(str(img) + ".dbg")
    out = []
    if not dbg.exists():
        return out
    for line in dbg.read_text(encoding="utf-8", errors="replace").splitlines():
        f = line.split("|")
        if len(f) >= 4 and f[0] == "1" and f[1].isdigit():
            out.append((LOAD + int(f[1]), f[2], f[3]))
    out.sort()
    return out


def _where(syms, pc: int) -> str:
    best = None
    for addr, name, s in syms:
        if addr <= pc:
            best = (addr, name, s)
        else:
            break
    if best is None:
        return "$%08X (no symbol covers it)" % pc
    return "$%08X - %s+%d, %s" % (pc, best[1], pc - best[0], best[2])


def run(img: pathlib.Path, limit: int = 200_000_000) -> tuple:
    """Execute the probe.  Returns (x0, uart text).

    The only MMIO is the UART.  Any other peripheral access is a failure:
    v3dqpu.pi4 is pure arithmetic and memory.  Alignment is checked on
    every access, DRAM included: with the ARM MMU off an unaligned access
    is an Alignment fault whatever SCTLR.A says, and no vector is
    installed, so on the board it is silence rather than a message.
    """
    cpu = A64()
    syms = _symbols(img)
    for i, b in enumerate(img.read_bytes()):
        cpu.memory[LOAD + i] = b
    cpu.pc = LOAD
    cpu.sp = STACK
    cpu.x[30] = LOADER_LR
    mem = cpu.memory
    uart = bytearray()

    def guard(addr: int, size: int, write: bool) -> None:
        if size > 1 and addr % size:
            raise SystemExit(
                "a64_v3d_qpu_check: an unaligned %d-byte %s happened at $%08X.  With "
                "the ARM MMU off that is an Alignment fault, and on the board it "
                "is silence.\n  at %s"
                % (size, "write" if write else "read", addr, _where(syms, cpu.pc)))

    def load(addr: int, size: int) -> int:
        guard(addr, size, False)
        if addr >= 0xFC000000:
            if addr == UART_FR:
                return 0
            raise SystemExit(
                "a64_v3d_qpu_check: the QPU assembler read peripheral $%08X, and "
                "v3dqpu.pi4 is supposed to touch no hardware at all.\n  at %s"
                % (addr, _where(syms, cpu.pc)))
        return sum(mem.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr: int, value: int, size: int) -> None:
        guard(addr, size, True)
        if addr >= 0xFC000000:
            if addr == UART_DR:
                uart.append(value & 0xFF)
                return
            raise SystemExit(
                "a64_v3d_qpu_check: the QPU assembler wrote peripheral $%08X, and "
                "v3dqpu.pi4 is supposed to touch no hardware at all.\n  at %s"
                % (addr, _where(syms, cpu.pc)))
        for i in range(size):
            mem[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store

    for _ in range(limit):
        if cpu.pc == LOADER_LR:
            break
        cpu.step()
    else:
        raise SystemExit("a64_v3d_qpu_check: the probe did not return within "
                         "%d instructions." % limit)
    return cpu.x[0] & 0xFFFFFFFF, uart.decode("utf-8", "replace")


# =====================================================================
#  PART 3 - THE CORPUS
#
#  kind 'I'  an instruction, checked against the pinned py-videocore6 word
#  kind 'D'  the golden word with bits 17:15 cleared - the BDU note above
#  kind 'X'  no py-videocore6 spelling: expected word assembled here from
#            the pinned Mesa tables, and decoded by the Anvil decoder
#  kind 'R'  a refusal, checked against a code named here
# =====================================================================

NAMES = [
    ("nop", "I"), ("tidx", "I"), ("eidx", "I"), ("lr", "I"),
    ("vfla", "I"), ("vflna", "I"), ("vflb", "I"), ("vflnb", "I"),
    ("msf", "I"), ("revf", "I"), ("iid", "I"), ("sampid", "I"),
    ("barrierid", "I"), ("tmuwt", "I"), ("vpmwt", "I"),

    ("bnot", "I"), ("neg", "I"), ("flapush", "I"), ("flbpush", "I"),
    ("flpop", "I"), ("setmsf", "I"), ("setrevf", "I"),
    ("itof", "I"), ("clz", "I"), ("utof", "I"),
    ("ftoin", "I"), ("ftoiz", "I"), ("ftouz", "I"), ("ftoc", "I"),
    ("fround", "I"), ("ftrunc", "I"), ("ffloor", "I"), ("fceil", "I"),
    ("fdx", "I"), ("fdy", "I"),
    ("recip", "I"), ("rsqrt", "I"), ("exp", "I"), ("log", "I"),
    ("sin", "I"), ("rsqrt2", "I"),

    ("add", "I"), ("sub", "I"), ("imin", "I"), ("imax", "I"),
    ("umin", "I"), ("umax", "I"), ("shl", "I"), ("shr", "I"),
    ("asr", "I"), ("ror", "I"), ("band", "I"), ("bor", "I"),
    ("bxor", "I"),
    ("fadd01", "I"), ("fadd10", "I"), ("faddnf01", "I"), ("faddnf10", "I"),
    ("fmin01", "I"), ("fmin10", "I"), ("fmax01", "I"), ("fmax10", "I"),
    ("fsub", "I"), ("fcmp", "I"),
    ("fadd_packl", "I"), ("fadd_packh", "I"), ("fadd_absa", "I"),
    ("fadd_unplh", "I"),

    ("mul_add", "I"), ("mul_sub", "I"), ("mul_umul24", "I"),
    ("mul_smul24", "I"), ("mul_multop", "I"), ("mul_fmul", "I"),
    ("mul_mov", "I"), ("mul_movtmud", "I"), ("mul_fmov", "I"),
    ("mul_fmul_packl", "I"), ("mul_fmul_unp", "I"), ("mul_fmov_packh", "I"),

    ("dual_add_fmul", "I"), ("band_rf3_r0_rf1", "I"),
    ("add_rf10_rf1_rf2", "I"), ("shl_rf5_rf5_rf6", "I"),

    ("add_imm0", "I"), ("add_imm15", "I"), ("add_immm1", "I"),
    ("add_immm16", "I"), ("fmul_imm1f", "I"), ("fmul_immtiny", "I"),
    ("bor_rf5_imm1", "I"),

    ("sig_thrsw", "I"), ("sig_ldunif", "I"), ("sig_ldunifa", "I"),
    ("sig_wrtmuc", "I"), ("sig_ucb", "I"),
    ("sig_ldunifrf0", "I"), ("sig_ldunifarf1", "I"), ("sig_ldtmu_r4", "I"),
    ("sig_ldvary_rf2", "I"), ("sig_ldtlb_rf3", "I"), ("sig_ldtlbu_rf4", "I"),
    ("sig_thrsw_ldunif", "I"), ("sig_thrsw_ldunifrf", "I"),
    ("sig_thrsw_wrtmuc", "I"), ("sig_ldtmu_ldunif", "I"),
    ("sig_thrsw_ldtmu", "I"), ("sig_ldvary_ldunif", "I"),
    ("sig_thrsw_ldvary", "I"), ("sig_ldvary_wrtmuc", "I"),
    ("add_sig_ldtmu", "I"), ("add_imm_ldvary", "I"), ("add_imm_ldtmu", "I"),

    ("cond_apushz", "I"), ("cond_apushn", "I"), ("cond_apushc", "I"),
    ("cond_ifa", "I"), ("cond_ifnb", "I"), ("cond_aandz", "I"),
    ("cond_anorc", "I"),
    ("cond_mpushz", "I"), ("cond_mifb", "I"), ("cond_mandnz", "I"),
    ("cond_ac_mpf", "I"), ("cond_mc_apf", "I"), ("cond_mc_ac", "I"),
    ("cond_mc_auf", "I"),

    ("br_always", "I"), ("br_a0", "I"), ("br_na0", "I"), ("br_alla", "I"),
    ("br_anyna", "I"), ("br_anya", "I"), ("br_allna", "I"),
    ("br_abs", "I"), ("br_link", "I"), ("br_reg7", "I"),
    ("br_setlink", "I"), ("br_unifrel", "I"), ("br_unifabs", "I"),
    ("br_unifreg", "I"), ("br_bigoff", "I"),
    ("br_bdu0", "D"),

    ("vfpack", "I"), ("vfpack_unp_lh", "I"), ("vfpack_tlbu", "I"),
    ("stvpmv", "I"), ("stvpmd", "I"), ("stvpmp", "I"),
    ("stvpmv_override", "I"),

    ("ldvpmv_in", "X"), ("ldvpmv_out", "X"),
    ("ldvpmd_in", "X"), ("ldvpmd_out", "X"),
    ("ldvpmp", "X"),
    ("ldvpmg_in", "X"), ("ldvpmg_out", "X"),

    ("ref_addop_vfmin", "R:V3DQ_ERR_ADD_OP"),
    ("ref_addop_vpmsetup", "R:V3DQ_ERR_ADD_OP"),
    ("ref_addop_vdwwt", "R:V3DQ_ERR_ADD_OP"),
    ("ref_mulop_vfmul", "R:V3DQ_ERR_MUL_OP"),
    ("ref_sig_thrsw_ucb", "R:V3DQ_ERR_SIG"),
    ("ref_sig_ldvpm", "R:V3DQ_ERR_SIG_LDVPM"),
    ("ref_flags_with_sig", "R:V3DQ_ERR_FLAGS_SIG"),
    ("ref_flags_ac_muf", "R:V3DQ_ERR_FLAGS"),
    ("ref_pack_on_add", "R:V3DQ_ERR_PACK"),
    ("ref_abs_on_ftoiz", "R:V3DQ_ERR_UNPACK"),
    ("ref_smallimm_17", "R:V3DQ_ERR_SMALLIMM"),
    ("ref_smimm_clash", "R:V3DQ_ERR_SMIMM_CLASH"),
    ("ref_waddr_64", "R:V3DQ_ERR_RANGE"),
    ("ref_ldvpm_magic", "R:V3DQ_ERR_VPM_DEST"),
    ("ref_vfpack_abs_a", "R:V3DQ_ERR_UNPACK"),
    ("ref_vfpack_pack", "R:V3DQ_ERR_PACK"),
]

# The operands the probe hands every 'X' entry - the same seven lines in
# pi4V3dQpuAsm.pi4.  No field is zero: waddr 37, mux_a 6 selects raddr_a,
# mux_b 5 is junk five of the seven must substitute away, and 27 and 41
# fill both read-address fields.
XOPERANDS = dict(waddr=37, mux_a=6, mux_b=5, raddr_a=27, raddr_b=41)

XOPS = {
    "ldvpmv_in": "LDVPMV_IN",
    "ldvpmv_out": "LDVPMV_OUT",
    "ldvpmd_in": "LDVPMD_IN",
    "ldvpmd_out": "LDVPMD_OUT",
    "ldvpmp": "LDVPMP",
    "ldvpmg_in": "LDVPMG_IN",
    "ldvpmg_out": "LDVPMG_OUT",
}

# The name tools/v3d42_qpu_decode.py gives each 'X' operation.  Its
# LDVPMP arm appends "_in" (the decoder's op-188 naming rule).
XDECODED = {
    "ldvpmv_in": "ldvpmv_in", "ldvpmv_out": "ldvpmv_out",
    "ldvpmd_in": "ldvpmd_in", "ldvpmd_out": "ldvpmd_out",
    "ldvpmp": "ldvpmp_in",
    "ldvpmg_in": "ldvpmg_in", "ldvpmg_out": "ldvpmg_out",
}

HAZARDS = [
    ("two_tmu", "V3DQ_ERR_HAZARD", "V3DQ_HZ_UNITS"),
    ("sfu_r4", "V3DQ_ERR_HAZARD", "V3DQ_HZ_SFU_R4"),
    ("thrsw_near", "V3DQ_ERR_HAZARD", "V3DQ_HZ_THRSW_NEAR"),
    ("rf_threnD", "V3DQ_ERR_HAZARD", "V3DQ_HZ_RF_THREND"),
    ("unif_vary", "V3DQ_ERR_HAZARD", "V3DQ_HZ_UNIF_VARY"),
    ("br_br", "V3DQ_ERR_HAZARD", "V3DQ_HZ_BR_BR"),
    ("no_threnD", "V3DQ_ERR_HAZARD", "V3DQ_HZ_NO_THREND"),
    ("buf_full", "V3DQ_ERR_FULL", None),
    ("buf_align", "V3DQ_ERR_RANGE", None),
    # The positive side of the same guard.  With only the plus-four case,
    # changing the library's `addr % 8` to `addr % 16` survived.  A guard
    # needs a case on each side.
    ("buf_align8", "V3DQ_OK", None),
    # The single-segment program: qpu_validate.c starts last_thrsw_found
    # at `!c->last_thrsw`, so a shader spawned in the final thread section
    # ends with one thrsw and three nops and one that is not does not.
    ("singleseg_ok", "V3DQ_OK", None),
    ("singleseg_off", "V3DQ_ERR_HAZARD", "V3DQ_HZ_NO_THREND"),
    ("singleseg_two", "V3DQ_ERR_HAZARD", "V3DQ_HZ_TWO_LAST"),
]

UNWITNESSED = ["FXCD", "XCD", "FYCD", "YCD", "FLAFIRST", "FLNAFIRST",
               "VADD", "VSUB"]
UNORACLED = ["LDVPMV_IN", "LDVPMV_OUT", "LDVPMD_IN", "LDVPMD_OUT",
             "LDVPMP", "LDVPMG_IN", "LDVPMG_OUT"]


# =====================================================================
#  PART 4 - THE CHECKS
# =====================================================================

def parse_probe(text: str):
    """Split the probe's output into its four kinds of line."""
    instrs = []
    shader = []
    hazards = {}
    header = {}
    for line in text.splitlines():
        f = line.split()
        if not f:
            continue
        if f[0] == "I" and len(f) == 5:
            instrs.append((int(f[1]), f[4], int(f[2], 16), int(f[3], 16)))
        elif f[0] == "R" and len(f) == 4:
            instrs.append((int(f[1]), f[3], None, int(f[2])))
        elif f[0] == "S" and len(f) == 4:
            shader.append((int(f[1]), int(f[2], 16), int(f[3], 16)))
        elif f[0] == "H" and len(f) == 4:
            hazards[f[1]] = (int(f[2]), int(f[3]))
        elif f[0] == "P" and len(f) == 9:
            header = {"build": int(f[2]), "hazard": int(f[4]),
                      "count": int(f[6]), "bytes": int(f[8])}
    return instrs, shader, hazards, header


def expected_x_words(oracle_nop: int) -> dict:
    """The seven LDVPM words, assembled from the pinned Mesa tables.

    Nothing here reads v3dqpu.pi4.  The opcode, the substituted muxes, the
    MA bit and every field position come from the pinned tables; the
    untouched half of the word comes from py-videocore6's golden bare
    `nop()` with every ADD-half field masked out.
    """
    shifts = derive_field_shifts()
    opcodes = derive_opcode_table("add")
    muxes = derive_mux_firsts("add")
    nsrcs = derive_add_num_src()
    _stvpm, _no_magic, out_ma = derive_vpm_rules()

    def sh(name):
        return shifts[name][0]

    def field_mask(name):
        _s, hi, lo = shifts[name]
        return ((1 << (hi - lo + 1)) - 1) << lo

    add_half = 0
    for f in ("OP_ADD", "ADD_A", "ADD_B", "WADDR_A", "MA",
              "RADDR_A", "RADDR_B"):
        add_half |= field_mask(f)
    base = oracle_nop & ~add_half & 0xFFFFFFFFFFFFFFFF

    out = {}
    for name, op in XOPS.items():
        mux_a = XOPERANDS["mux_a"]
        mux_b = XOPERANDS["mux_b"]
        if nsrcs[op] < 2:
            mux_b = muxes[op][1]
        if nsrcs[op] < 1:
            mux_a = muxes[op][0]
        w = base
        w |= opcodes[op] << sh("OP_ADD")
        w |= mux_a << sh("ADD_A")
        w |= mux_b << sh("ADD_B")
        w |= XOPERANDS["waddr"] << sh("WADDR_A")
        w |= XOPERANDS["raddr_a"] << sh("RADDR_A")
        w |= XOPERANDS["raddr_b"] << sh("RADDR_B")
        if op in out_ma:
            w |= 1 << sh("MA")
        out[name] = w
    return out


def oracle_corpus() -> list:
    return [w for _spelling, w in PV6_CORPUS]


def oracle_shader() -> list:
    return [w for _spelling, w in PV6_SHADER]


def check_pins(fails) -> None:
    """The pinned tables must be self-consistent before anything trusts them."""
    for name, (shift, high, low) in FIELD_SHIFTS.items():
        if shift != low or high < low:
            fails.append("The pinned field %s has shift %d and bits %d:%d, which "
                         "cannot be right." % (name, shift, high, low))
    if len(SIG_TABLE) != 27:
        fails.append("The pinned signal table has %d rows; qpu_pack.c's 4.2 table "
                     "has 27." % len(SIG_TABLE))
    if len(SMALL_IMMEDIATES) != 48:
        fails.append("The pinned small-immediate table has %d entries, not 48."
                     % len(SMALL_IMMEDIATES))
    n_oracle = sum(1 for _, k in NAMES if k in ("I", "D"))
    if len(PV6_CORPUS) != n_oracle:
        fails.append("There are %d pinned py-videocore6 words and %d corpus entries "
                     "that need one." % (len(PV6_CORPUS), n_oracle))
    xw = expected_x_words(PV6_CORPUS[0][1])
    for name, word in PINNED_X_WORDS.items():
        if xw.get(name) != word:
            fails.append("The LDVPM word for %s assembled from the pinned tables is "
                         "%016X, but the value recorded when the tables were pinned "
                         "is %016X." % (name, xw.get(name, 0), word))


def check_corpus(instrs, oracle_words, fails):
    """The central comparison.  Names first, then bits."""
    if len(instrs) != len(NAMES):
        fails.append(
            "The probe printed %d corpus entries and this gate expects %d.  The "
            "two lists have drifted apart, so no comparison below them is "
            "trustworthy." % (len(instrs), len(NAMES)))
        return 0, 0, 0

    xwords = expected_x_words(oracle_words[0]) if oracle_words else {}
    oracle_i = 0
    checked = 0
    xchecked = 0
    disagreements = 0
    for n, ((idx, name, hi, lo), (want_name, kind)) in enumerate(
            zip(instrs, NAMES)):
        if idx != n:
            fails.append("Corpus entry %d printed index %d, so the probe's own "
                         "counter is wrong." % (n, idx))
            return checked, disagreements, xchecked
        if name != want_name:
            fails.append("Corpus entry %d is %r in the probe and %r in this gate, "
                         "so the two lists are not the same corpus."
                         % (n, name, want_name))
            return checked, disagreements, xchecked

        if kind == "X":
            if hi is None:
                fails.append("%s: the library refused an instruction it must "
                             "encode, with code %d." % (name, lo))
                continue
            got = (hi << 32) | lo
            want = xwords[name]
            if got != want:
                fails.append(
                    "%s: this library says %016X and the pinned Mesa tables say "
                    "%016X (they differ in %016X).  Both are readings of "
                    "qpu_pack.c, so the gate cannot say which is wrong."
                    % (name, got, want, got ^ want))
            else:
                xchecked += 1
            continue

        if kind.startswith("R:"):
            want = lib_constant(kind[2:])
            if hi is not None:
                fails.append("%s: the library accepted an instruction it must "
                             "refuse, encoding it as %08X %08X." % (name, hi, lo))
            elif lo != want:
                fails.append("%s: it was refused with code %d, but #%s is %d."
                             % (name, lo, kind[2:], want))
            continue

        if hi is None:
            fails.append("%s: the library refused an instruction it must encode, "
                         "with code %d." % (name, lo))
            oracle_i += 1
            continue

        got = (hi << 32) | lo
        want = oracle_words[oracle_i]
        oracle_i += 1

        if kind == "D":
            want_masked = want & ~(0b111 << 15)
            if got != want_masked:
                fails.append(
                    "%s: the library says %016X, expected %016X (the golden word "
                    "%016X with bits 17:15 cleared - see the BDU note)."
                    % (name, got, want_masked, want))
            elif want == want_masked:
                fails.append(
                    "%s: the pinned golden word %016X already has bits 17:15 clear, "
                    "so the disagreement this entry records is gone and the pin "
                    "or the corpus has moved." % (name, want))
            else:
                disagreements += 1
            checked += 1
            continue

        if got != want:
            fails.append(
                "%s: this library says %016X and py-videocore6's golden word is "
                "%016X (they differ in %016X)." % (name, got, want, got ^ want))
        checked += 1

    if oracle_i != len(oracle_words):
        fails.append("There are %d golden words and the corpus consumed %d."
                     % (len(oracle_words), oracle_i))
    return checked, disagreements, xchecked


def check_decoder(instrs, fails) -> int:
    """Every word the library emitted, read by the Anvil-owned decoder."""
    n = 0
    kinds = dict(NAMES)
    for idx, name, hi, lo in instrs:
        kind = kinds.get(name, "")
        if hi is None or kind.startswith("R:"):
            continue
        word = (hi << 32) | lo
        try:
            ins = QD.decode_word(word, idx)
        except QD.DecodeError as e:
            fails.append("%s: tools/v3d42_qpu_decode.py cannot decode the library's "
                         "word %016X (%s)." % (name, word, e))
            continue
        if kind == "X":
            want = XDECODED[name]
            if ins.add_op != want:
                fails.append("%s: the Anvil decoder reads the library's word %016X as "
                             "ADD operation %r, not %r." % (name, word, ins.add_op, want))
                continue
            if ins.add_magic:
                fails.append("%s: the Anvil decoder reads a magic destination; LDVPM "
                             "loads must write the register file." % name)
                continue
            if (ins.add_waddr, ins.raddr_a, ins.add_mux_a) != (
                    XOPERANDS["waddr"], XOPERANDS["raddr_a"], XOPERANDS["mux_a"]):
                fails.append("%s: the Anvil decoder reads waddr %d, raddr_a %d, mux_a "
                             "%d; the probe passed %d, %d, %d."
                             % (name, ins.add_waddr, ins.raddr_a, ins.add_mux_a,
                                XOPERANDS["waddr"], XOPERANDS["raddr_a"],
                                XOPERANDS["mux_a"]))
                continue
            if ins.mul_op != "nop" or ins.signals:
                fails.append("%s: the Anvil decoder reads MUL %r and signals %s "
                             "beside the load." % (name, ins.mul_op, sorted(ins.signals)))
                continue
        n += 1
    return n


def check_shader(shader, oracle_words, header, fails):
    if header.get("build") != 0:
        fails.append("The probe could not build the compute shader: "
                     "V3dQpuProgramEnd/Emit returned %s with hazard %s."
                     % (header.get("build"), header.get("hazard")))
        return 0
    if header.get("bytes") != len(oracle_words) * 8:
        fails.append("The shader is %s bytes and py-videocore6's golden shader is %d."
                     % (header.get("bytes"), len(oracle_words) * 8))
        return 0
    if len(shader) != len(oracle_words):
        fails.append("The probe dumped %d shader instructions, expected %d."
                     % (len(shader), len(oracle_words)))
        return 0
    n = 0
    for (i, hi, lo), want in zip(shader, oracle_words):
        got = (hi << 32) | lo
        if got != want:
            fails.append("Shader instruction %d: this library says %016X and "
                         "py-videocore6's golden word is %016X." % (i, got, want))
        n += 1
    return n


def check_hazards(hazards, fails):
    n = 0
    for name, err_const, hz_const in HAZARDS:
        if name not in hazards:
            fails.append("The probe never printed hazard case %r." % name)
            continue
        err, hz = hazards[name]
        want_err = lib_constant(err_const)
        if err != want_err:
            fails.append("Hazard %s returned %d, expected %d (#%s)."
                         % (name, err, want_err, err_const))
            continue
        if hz_const is not None:
            want_hz = lib_constant(hz_const)
            if hz != want_hz:
                fails.append("Hazard %s named rule %d, expected %d (#%s).  The "
                             "refusal is right and the reason is wrong."
                             % (name, hz, want_hz, hz_const))
                continue
        n += 1
    return n


def check_derived(fails) -> int:
    """The pinned Mesa tables, against the library's own text."""
    n = 0
    fields = derive_field_shifts()

    def want_hi(name, mesa):
        return fields[mesa][0] - 32

    pairs = [
        ("V3DQ_OP_MUL_SHIFT_HI", want_hi, "OP_MUL"),
        ("V3DQ_SIG_SHIFT_HI", want_hi, "SIG"),
        ("V3DQ_COND_SHIFT_HI", want_hi, "COND"),
        ("V3DQ_WADDR_M_SHIFT_HI", want_hi, "WADDR_M"),
        ("V3DQ_WADDR_A_SHIFT_HI", want_hi, "WADDR_A"),
        ("V3DQ_BR_ADDR_LOW_SHIFT_HI", want_hi, "BRANCH_ADDR_LOW"),
        ("V3DQ_BR_COND_SHIFT_HI", want_hi, "BRANCH_COND"),
    ]
    for libname, fn, mesa in pairs:
        got = lib_constant(libname)
        want = fn(libname, mesa)
        if got != want:
            fails.append("#%s is %d and qpu_pack.c's V3D_QPU_%s_SHIFT is %d (%d "
                         "relative to bit 32)."
                         % (libname, got, mesa, fields[mesa][0], want))
        else:
            n += 1

    lowpairs = [
        ("V3DQ_BR_ADDR_HIGH_SHIFT", "BRANCH_ADDR_HIGH"),
        ("V3DQ_OP_ADD_SHIFT", "OP_ADD"),
        ("V3DQ_MUL_B_SHIFT", "MUL_B"),
        ("V3DQ_BR_MSFIGN_SHIFT", "BRANCH_MSFIGN"),
        ("V3DQ_MUL_A_SHIFT", "MUL_A"),
        ("V3DQ_ADD_B_SHIFT", "ADD_B"),
        ("V3DQ_BR_BDU_SHIFT", "BRANCH_BDU"),
        ("V3DQ_ADD_A_SHIFT", "ADD_A"),
        ("V3DQ_BR_BDI_SHIFT", "BRANCH_BDI"),
        ("V3DQ_RADDR_A_SHIFT", "RADDR_A"),
        ("V3DQ_RADDR_B_SHIFT", "RADDR_B"),
    ]
    for libname, mesa in lowpairs:
        got = lib_constant(libname)
        if got != fields[mesa][0]:
            fails.append("#%s is %d and qpu_pack.c says %d."
                         % (libname, got, fields[mesa][0]))
        else:
            n += 1

    singles = [("V3DQ_MM_HI", "MM", 32), ("V3DQ_MA_HI", "MA", 32),
               ("V3DQ_BR_UB", "BRANCH_UB", 0)]
    for libname, mesa, base in singles:
        want = 1 << (fields[mesa][0] - base)
        got = lib_constant(libname)
        if got != want:
            fails.append("#%s is %d and bit %d relative to %d is %d."
                         % (libname, got, fields[mesa][0], base, want))
        else:
            n += 1

    names = derive_sig_writes_address()
    want = 0
    for s in names:
        want |= lib_constant("V3DQ_SIG_" + s.upper())
    got = lib_constant("V3DQ_SIG_WRITES_ADDR")
    if got != want:
        fails.append(
            "#V3DQ_SIG_WRITES_ADDR is %d; qpu_instr.c names %s, which is %d.  A "
            "signal missing from that mask encodes a condition where the hardware "
            "expects a destination." % (got, sorted(names), want))
    else:
        n += 1

    mesa_sig = derive_sig_table()
    lib_sig = lib_select_arms("v3dq_SigPack")
    if len(lib_sig) != len(mesa_sig):
        fails.append("v3dq_SigPack has %d rows and v3d42_sig_map has %d."
                     % (len(lib_sig), len(mesa_sig)))
    for expr, idx in lib_sig.items():
        flags = set()
        for tok in re.findall(r"#V3DQ_SIG_(\w+)", expr):
            if tok != "NONE":
                flags.add(_sig_name(tok))
        key = frozenset(flags)
        if key not in mesa_sig:
            fails.append("v3dq_SigPack returns %d for %s, which is not a row of "
                         "v3d42_sig_map." % (idx, sorted(flags)))
        elif mesa_sig[key] != idx:
            fails.append("v3dq_SigPack returns %d for %s and v3d42_sig_map says %d."
                         % (idx, sorted(flags), mesa_sig[key]))
        else:
            n += 1

    imms = derive_small_immediates()
    lib_imm = lib_select_arms("v3dq_SmallImmIndex")
    for expr, idx in lib_imm.items():
        val = int(expr.lstrip("$"), 16)
        if imms[idx] != val:
            fails.append("v3dq_SmallImmIndex maps $%08X to %d and "
                         "small_immediates[%d] is $%08X." % (val, idx, idx, imms[idx]))
        else:
            n += 1
    for v in range(16):
        if imms[v] != v:
            fails.append("small_immediates[%d] is $%08X, not %d, so the library's "
                         "`If v <= 15 : return v` arm is wrong." % (v, imms[v], v))
            break
    else:
        n += 1
    for k in range(16):
        v = (0xFFFFFFF0 + k) & 0xFFFFFFFF
        if imms[16 + k] != v:
            fails.append("small_immediates[%d] is $%08X, expected $%08X, so the "
                         "library's negative arm is wrong." % (16 + k, imms[16 + k], v))
            break
    else:
        n += 1

    for which, proc, prefix in (("add", "v3dq_AddOpcode", "V3DQ_A_"),
                                ("mul", "v3dq_MulOpcode", "V3DQ_M_")):
        mesa_ops = derive_opcode_table(which)
        lib_ops = lib_select_arms(proc)
        for expr, code in lib_ops.items():
            name = expr.replace("#" + prefix, "")
            if name not in mesa_ops:
                fails.append("%s encodes %s, which is not in v3d42_%s_ops."
                             % (proc, name, which))
            elif mesa_ops[name] != code:
                fails.append("%s returns %d for %s and v3d42_%s_ops says %d."
                             % (proc, code, name, which, mesa_ops[name]))
            else:
                n += 1

    mesa_src = derive_add_num_src()
    lib_src = lib_select_arms("v3dq_AddNumSrc")
    for expr, count in lib_src.items():
        name = expr.replace("#V3DQ_A_", "")
        if name not in mesa_src:
            fails.append("v3dq_AddNumSrc names %s, which add_op_args does not." % name)
        elif mesa_src[name] != count:
            fails.append("v3dq_AddNumSrc says %s takes %d sources and add_op_args "
                         "says %d.  An unused mux field carries the opcode, so this "
                         "is a wrong instruction and not a wrong operand."
                         % (name, count, mesa_src[name]))
        else:
            n += 1
    # The default arm (`ProcedureReturn 2` for anything unnamed) is checked
    # over the ENCODABLE set only, read out of v3dq_AddOpcode.
    encodable = set(e.replace("#V3DQ_A_", "")
                    for e in lib_select_arms("v3dq_AddOpcode"))
    listed = set(e.replace("#V3DQ_A_", "") for e in lib_src)
    for name, count in mesa_src.items():
        if name in listed or name not in encodable:
            continue
        if count != 2:
            fails.append("v3dq_AddNumSrc falls through to 2 for %s, which "
                         "v3dq_AddOpcode does encode, and add_op_args says %d."
                         % (name, count))
    n += 1
    for name in sorted(listed - encodable):
        fails.append("v3dq_AddNumSrc names %s and v3dq_AddOpcode refuses it, so "
                     "the row is unreachable." % name)

    muxes = derive_mux_firsts("add")
    lib_mb = dict((e.replace("#V3DQ_A_", ""), v)
                  for e, v in lib_select_arms("v3dq_AddMuxBFixed").items())
    lib_ma = dict((e.replace("#V3DQ_A_", ""), v)
                  for e, v in lib_select_arms("v3dq_AddMuxAFixed").items())
    for name in sorted(encodable):
        if name not in muxes or name not in mesa_src:
            continue
        a_first, b_first = muxes[name]
        if mesa_src[name] < 2:
            got = lib_mb.get(name, 0)
            if got != b_first:
                fails.append(
                    "v3dq_AddMuxBFixed substitutes %d for %s and the b_mask in "
                    "v3d42_add_ops gives %d.  MUX_B is part of the opcode for this "
                    "row, so that is a different instruction." % (got, name, b_first))
            else:
                n += 1
        if mesa_src[name] < 1:
            got = lib_ma.get(name, 0)
            if got != a_first:
                fails.append("v3dq_AddMuxAFixed substitutes %d for %s and the a_mask "
                             "in v3d42_add_ops gives %d." % (got, name, a_first))
            else:
                n += 1

    stvpm, no_magic, out_ma = derive_vpm_rules()
    lib_stvpm = dict((e.replace("#V3DQ_A_", ""), v)
                     for e, v in lib_select_arms("v3dq_AddStvpmWaddr").items())
    if lib_stvpm != stvpm:
        fails.append("v3dq_AddStvpmWaddr says %r and qpu_pack.c's switch says %r.  "
                     "The STVPM operation is its destination field."
                     % (lib_stvpm, stvpm))
    else:
        n += 1
    lib_ldvpm = set(e.replace("#V3DQ_A_", "")
                    for e in lib_select_arms("v3dq_AddIsLdvpm"))
    if lib_ldvpm != no_magic:
        fails.append("v3dq_AddIsLdvpm names %r and the forms qpu_pack.c asserts "
                     "!magic_write on are %r." % (sorted(lib_ldvpm), sorted(no_magic)))
    else:
        n += 1
    lib_out = set(e.replace("#V3DQ_A_", "")
                  for e in lib_select_arms("v3dq_AddIsLdvpmOut"))
    if lib_out != out_ma:
        fails.append("v3dq_AddIsLdvpmOut names %r and the forms qpu_pack.c sets "
                     "V3D_QPU_MA for are %r.  _IN and _OUT differ only in bit 44."
                     % (sorted(lib_out), sorted(out_ma)))
    else:
        n += 1
    for name in sorted(set(stvpm) | no_magic):
        if name not in encodable:
            fails.append("v3dq_AddOpcode refuses %s, which the VPM rules describe."
                         % name)

    for name, val in derive_waddrs().items():
        libname = "V3DQ_WADDR_" + name
        try:
            got = lib_constant(libname)
        except SystemExit:
            continue          # the library need not name every one
        if got != val:
            fails.append("#%s is %d and qpu_instr.h says %d." % (libname, got, val))
        else:
            n += 1

    return n


def _shader_body(path: pathlib.Path) -> list:
    """BuildShader()'s executable lines, comments and spacing removed.

    The V3dQpuProgramBegin line is dropped: the two files legitimately
    build into different buffers.  Everything after it must be identical.
    """
    m = re.search(r"^Procedure\.i BuildShader\(\).*?^EndProcedure",
                  _text(path), re.M | re.S)
    if not m:
        raise SystemExit("a64_v3d_qpu_check: %s has no BuildShader() procedure."
                         % path.name)
    out = []
    for line in m.group(0).splitlines():
        line = line.split(";")[0].strip()
        if not line or "V3dQpuProgramBegin" in line:
            continue
        out.append(re.sub(r"\s+", " ", line))
    return out


def check_shader_copies(fails) -> None:
    """pi4V3dQpuAsm.pi4 and pi4V3dCsd.pi4 must build the SAME shader.

    The golden comparison runs against the corpus probe's copy; the
    instructions that reach silicon are the CSD probe's copy.
    """
    a = _shader_body(PROBE)
    b = _shader_body(CSD_PROBE)
    if a != b:
        n = min(len(a), len(b))
        where = "length %d vs %d" % (len(a), len(b))
        for i in range(n):
            if a[i] != b[i]:
                where = ("first difference at line %d:\n      corpus: %s\n      "
                         "csd:    %s" % (i, a[i], b[i]))
                break
        fails.append("pi4V3dQpuAsm.pi4's BuildShader() and pi4V3dCsd.pi4's have "
                     "drifted apart: the golden words check the first and the board "
                     "runs the second.  %s" % where)
    ca = _text(PROBE)
    cb = _text(CSD_PROBE)
    for name in re.findall(r"^#(MW_\w+)\s*=", ca, re.M):
        ma = re.search(r"^#%s\s*=\s*(\d+)" % name, ca, re.M)
        mb = re.search(r"^#%s\s*=\s*(\d+)" % name, cb, re.M)
        if mb is None:
            continue
        if ma.group(1) != mb.group(1):
            fails.append("#%s is %s in pi4V3dQpuAsm.pi4 and %s in pi4V3dCsd.pi4."
                         % (name, ma.group(1), mb.group(1)))


def check_unwitnessed(fails) -> None:
    """The eight operations py-videocore6 cannot encode must not be in the
    corpus, and the pin record must still say they were absent."""
    corpus_names = set(n for n, _ in NAMES)
    for op in UNWITNESSED:
        if op.lower() in corpus_names:
            fails.append("%r is in the corpus, and py-videocore6 cannot encode it, so "
                         "that entry is not compared against an independent "
                         "implementation." % op.lower())
        if op not in PV6_ABSENT:
            fails.append("The pin record does not list %s as absent from "
                         "py-videocore6's operation table, so its exclusion from the "
                         "corpus is unexplained." % op)


def check_unoracled(fails) -> None:
    """The seven LDVPM operations must be in the corpus as kind 'X' only."""
    kinds = dict(NAMES)
    for op in UNORACLED:
        low = op.lower()
        if low not in kinds:
            fails.append("%r is not in the corpus, and the triangle depends on it."
                         % low)
        elif kinds[low] != "X":
            fails.append("%r is in the corpus as kind %r.  Only 'X' is honest: "
                         "py-videocore6 has no ldvpm operation." % (low, kinds[low]))
        if op not in PV6_ABSENT:
            fails.append("The pin record does not list %s as absent from "
                         "py-videocore6, so kind 'X' is unexplained." % op)
    encodable = set(e.replace("#V3DQ_A_", "")
                    for e in lib_select_arms("v3dq_AddOpcode"))
    for op in UNORACLED:
        if op not in encodable:
            fails.append("v3dq_AddOpcode does not encode %s." % op)


# =====================================================================
#  PART 5 - MUTATION
#
#  Each entry rewrites a TEMPORARY COPY of v3dqpu.pi4 with one fault,
#  rebuilds the probe against that copy and re-runs everything above.
# =====================================================================
MUTANTS = [
    ("shift-sig", "#V3DQ_SIG_SHIFT_HI      = 21",
     "#V3DQ_SIG_SHIFT_HI      = 20"),
    ("shift-cond", "#V3DQ_COND_SHIFT_HI     = 14",
     "#V3DQ_COND_SHIFT_HI     = 15"),
    ("shift-opadd", "#V3DQ_OP_ADD_SHIFT      = 24",
     "#V3DQ_OP_ADD_SHIFT      = 25"),
    ("shift-raddra", "#V3DQ_RADDR_A_SHIFT     = 6",
     "#V3DQ_RADDR_A_SHIFT     = 7"),
    ("bit-ma", "#V3DQ_MA_HI             = 4096",
     "#V3DQ_MA_HI             = 8192"),
    ("opcode-and", "    Case #V3DQ_A_AND\n      ProcedureReturn 181",
     "    Case #V3DQ_A_AND\n      ProcedureReturn 180"),
    ("opcode-mov", "    Case #V3DQ_M_MOV\n      ProcedureReturn 15",
     "    Case #V3DQ_M_MOV\n      ProcedureReturn 14"),
    ("sig-row14", "    Case #V3DQ_SIG_SMIMM | #V3DQ_SIG_LDVARY\n"
     "      ProcedureReturn 14",
     "    Case #V3DQ_SIG_SMIMM | #V3DQ_SIG_LDVARY\n"
     "      ProcedureReturn 4"),
    ("sig-row31", "    Case #V3DQ_SIG_SMIMM | #V3DQ_SIG_LDTMU\n"
     "      ProcedureReturn 31",
     "    Case #V3DQ_SIG_SMIMM | #V3DQ_SIG_LDTMU\n"
     "      ProcedureReturn 30"),
    ("muxb-eidx", "    Case #V3DQ_A_EIDX\n      ProcedureReturn 2   ; :496",
     "    Case #V3DQ_A_EIDX\n      ProcedureReturn 3   ; :496"),
    ("muxb-clz", "    Case #V3DQ_A_CLZ\n      ProcedureReturn 3   ; :557",
     "    Case #V3DQ_A_CLZ\n      ProcedureReturn 2   ; :557"),
    ("numsrc-nop", "    Case #V3DQ_A_NOP\n      ProcedureReturn 0\n"
     "    Case #V3DQ_A_TIDX",
     "    Case #V3DQ_A_NOP\n      ProcedureReturn 2\n"
     "    Case #V3DQ_A_TIDX"),
    ("no-swap", "    If v3dq_AddWantsOrderFalse(op) = 1",
     "    If v3dq_AddWantsOrderFalse(op) = 2"),
    ("swap-both", "    If v3dq_AddWantsOrderTrue(op) = 1",
     "    If v3dq_AddWantsOrderTrue(op) = 2"),
    ("unpack-abs", "    Case #V3DQ_UNPACK_ABS\n      ProcedureReturn 0\n"
     "    Case #V3DQ_UNPACK_NONE\n      ProcedureReturn 1",
     "    Case #V3DQ_UNPACK_ABS\n      ProcedureReturn 1\n"
     "    Case #V3DQ_UNPACK_NONE\n      ProcedureReturn 0"),
    ("fmul-or", "      opcode = opcode + (packed << 4)",
     "      opcode = opcode | (packed << 4)"),
    ("fmov-split", "      opcode = opcode | ((packed >> 1) & 1)",
     "      opcode = opcode | (packed & 1)"),
    ("flags-base-mc", "    Case #V3DQ_FP_MC\n      ProcedureReturn 48",
     "    Case #V3DQ_FP_MC\n      ProcedureReturn 32"),
    ("flags-uf-bias", "    packed = packed | (v3dq_auf - #V3DQ_UF_ANDZ + 4)",
     "    packed = packed | (v3dq_auf - #V3DQ_UF_ANDZ + 3)"),
    ("flags-ac-shift", "      packed = packed | ((v3dq_ac - #V3DQ_COND_IFA) << 2)",
     "      packed = packed | ((v3dq_ac - #V3DQ_COND_IFA) << 1)"),
    ("sigaddr-magic", "      flags = flags | #V3DQ_COND_SIG_MAGIC",
     "      flags = flags | 32"),
    ("smimm-neg", "    ProcedureReturn 16 + (v - $FFFFFFF0)",
     "    ProcedureReturn 15 + (v - $FFFFFFF0)"),
    ("smimm-1f", "    Case $3F800000\n      ProcedureReturn 40",
     "    Case $3F800000\n      ProcedureReturn 41"),
    ("br-cond-bias", "    v3dq_hi = v3dq_hi | (((2 + (v3dq_brCond - #V3DQ_BR_A0))",
     "    v3dq_hi = v3dq_hi | (((1 + (v3dq_brCond - #V3DQ_BR_A0))"),
    ("br-addr-shift", "    addrLow  = (off & $00FFFFFF) >> 3",
     "    addrLow  = (off & $00FFFFFF) >> 2"),
    ("br-sig", "  v3dq_hi = v3dq_hi | (16 << #V3DQ_SIG_SHIFT_HI)",
     "  v3dq_hi = v3dq_hi | (17 << #V3DQ_SIG_SHIFT_HI)"),
    ("no-flagsig-guard",
     "    If v3dq_ac <> #V3DQ_COND_NONE\n      ProcedureReturn v3dq_Fail(#V3DQ_ERR_FLAGS_SIG)\n    EndIf",
     "    If v3dq_ac <> #V3DQ_COND_NONE\n      v3dq_ac = v3dq_ac\n    EndIf"),
    ("no-waddr-range", "  If waddr < 0 Or waddr > 63",
     "  If waddr < 0 Or waddr > 640"),
    ("no-smimm-clash", "    If v3dq_raddrBIsImm = 0\n"
     "      ProcedureReturn v3dq_Fail(#V3DQ_ERR_SMIMM_CLASH)\n    EndIf",
     "    If v3dq_raddrBIsImm = 2\n"
     "      ProcedureReturn v3dq_Fail(#V3DQ_ERR_SMIMM_CLASH)\n    EndIf"),
    ("no-hazard-units", "  If units > 1", "  If units > 2"),
    ("no-hazard-sfu", "  If (v3dq_ip - v3dq_lastSfuWrite) < 2",
     "  If (v3dq_ip - v3dq_lastSfuWrite) < 0"),
    ("no-hazard-thrend", "  If v3dq_threndFound = 1\n    If v3dq_addOp <> #V3DQ_A_NOP",
     "  If v3dq_threndFound = 2\n    If v3dq_addOp <> #V3DQ_A_NOP"),
    ("no-programend", "  If v3dq_threndFound = 0\n    v3dq_hazardName = #V3DQ_HZ_NO_THREND",
     "  If v3dq_threndFound = 2\n    v3dq_hazardName = #V3DQ_HZ_NO_THREND"),
    ("no-buf-align", "  If (addr % 8) <> 0", "  If (addr % 16) <> 0"),
    ("reset-waddr", "  v3dq_addWaddr   = #V3DQ_WADDR_NOP",
     "  v3dq_addWaddr   = 7"),
    ("emit-halves", "  PokeN(v3dq_bufAddr + v3dq_bufUsed,     v3dq_lo & $FFFFFFFF)\n"
     "  PokeN(v3dq_bufAddr + v3dq_bufUsed + 4, v3dq_hi & $FFFFFFFF)",
     "  PokeN(v3dq_bufAddr + v3dq_bufUsed,     v3dq_hi & $FFFFFFFF)\n"
     "  PokeN(v3dq_bufAddr + v3dq_bufUsed + 4, v3dq_lo & $FFFFFFFF)"),

    # ---- the VPM family and VFPACK -----------------------------------
    ("vpm-out-is-in",
     "    Case #V3DQ_A_LDVPMV_OUT\n      ProcedureReturn 1\n"
     "    Case #V3DQ_A_LDVPMD_OUT",
     "    Case #V3DQ_A_LDVPMV_IN\n      ProcedureReturn 1\n"
     "    Case #V3DQ_A_LDVPMD_OUT"),
    ("vpm-no-forcema", "  If forceMa = 1\n    v3dq_hi = v3dq_hi | #V3DQ_MA_HI",
     "  If forceMa = 2\n    v3dq_hi = v3dq_hi | #V3DQ_MA_HI"),
    ("vpm-stvpmd-waddr",
     "    Case #V3DQ_A_STVPMD\n      ProcedureReturn 1   ; :1582-1584",
     "    Case #V3DQ_A_STVPMD\n      ProcedureReturn 2   ; :1582-1584"),
    ("vpm-no-override", "  If stw >= 0", "  If stw >= 99"),
    ("vpm-magic-kept", "    waddr   = stw\n    magicOk = 0",
     "    waddr   = stw\n    magicOk = 1"),
    ("vpm-muxb-d", "    Case #V3DQ_A_LDVPMD_IN\n"
     "      ProcedureReturn 1   ; :522 b_mask OP_MASK(1)",
     "    Case #V3DQ_A_LDVPMD_IN\n"
     "      ProcedureReturn 0   ; :522 b_mask OP_MASK(1)"),
    ("vpm-nsrc-p", "    Case #V3DQ_A_LDVPMP\n      ProcedureReturn 1\n"
     "    Case #V3DQ_A_RSQRT",
     "    Case #V3DQ_A_LDVPMP\n      ProcedureReturn 2\n"
     "    Case #V3DQ_A_RSQRT"),
    ("vpm-no-dest-guard",
     "    If v3dq_addMagic <> 0\n"
     "      ProcedureReturn v3dq_Fail(#V3DQ_ERR_VPM_DEST)",
     "    If v3dq_addMagic <> 2\n"
     "      ProcedureReturn v3dq_Fail(#V3DQ_ERR_VPM_DEST)"),
    ("vfpack-opcode", "    Case #V3DQ_A_VFPACK\n      ProcedureReturn 53",
     "    Case #V3DQ_A_VFPACK\n      ProcedureReturn 52"),
    ("vfpack-unp-shift", "    opcode = (opcode & $F0) | (aUnp << 2) | bUnp",
     "    opcode = (opcode & $F0) | (aUnp << 3) | bUnp"),
    ("vfpack-no-abs-guard",
     "    If v3dq_addUnpackA = #V3DQ_UNPACK_ABS\n"
     "      ProcedureReturn v3dq_Fail(#V3DQ_ERR_UNPACK)\n    EndIf\n"
     "    If v3dq_addUnpackB",
     "    If v3dq_addUnpackA = #V3DQ_UNPACK_L\n"
     "      ProcedureReturn v3dq_Fail(#V3DQ_ERR_UNPACK)\n    EndIf\n"
     "    If v3dq_addUnpackB"),
    ("singleseg-ignored",
     "  If singleSeg <> 0\n    v3dq_lastThrswFound = 1\n  EndIf",
     "  If singleSeg <> 2\n    v3dq_lastThrswFound = 1\n  EndIf"),
]


def run_everything(compiler: str, workdir: pathlib.Path, img_name: str,
                   lib_text: str | None = None) -> list:
    """Build, run and check.  Returns the failure list."""
    fails: list = []
    img = build(compiler, workdir, img_name, lib_text)
    x0, text = run(img)
    instrs, shader, hazards, header = parse_probe(text)
    check_pins(fails)
    check_corpus(instrs, oracle_corpus(), fails)
    check_decoder(instrs, fails)
    check_shader(shader, oracle_shader(), header, fails)
    check_hazards(hazards, fails)
    check_derived(fails)
    check_unwitnessed(fails)
    check_unoracled(fails)
    check_shader_copies(fails)
    if x0 != len(NAMES):
        fails.append("The probe returned x0 = %d and the corpus is %d entries."
                     % (x0, len(NAMES)))
    return fails


def mutate(compiler: str, workdir: pathlib.Path, only=None) -> int:
    global _LIB_TEXT
    backup = _text(LIB).replace("\r\n", "\n")
    survivors = []
    killed = 0
    tried = 0
    for name, old, new in MUTANTS:
        if only and name not in only:
            continue
        tried += 1
        if old not in backup:
            print("  %-18s NOT APPLIED - the text this fault edits is gone from "
                  "v3dqpu.pi4.  The mutant list has rotted and this is a hole." % name)
            survivors.append(name + " (not applied)")
            continue
        _LIB_TEXT = backup.replace(old, new, 1)
        try:
            fails = run_everything(compiler, workdir, "v3dqpuasm_mut.img", _LIB_TEXT)
        except SystemExit as e:
            fails = ["build or run refused: %s" % str(e)[:120]]
        finally:
            _LIB_TEXT = None
        if fails:
            killed += 1
            print("  %-18s killed   (%s)" % (name, fails[0][:96]))
        else:
            survivors.append(name)
            print("  %-18s SURVIVED - the gate cannot see this fault" % name)
    print()
    print("  %d of %d faults killed" % (killed, tried))
    if survivors:
        print("  survivors: %s" % ", ".join(survivors))
    return 0 if not survivors else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"),
                    help="the PureMetalForge compiler executable")
    ap.add_argument("--mutate", action="store_true",
                    help="inject faults into a temporary copy of v3dqpu.pi4 and "
                         "require the gate to catch every one")
    ap.add_argument("--only", action="append",
                    help="with --mutate, run only the named mutant (repeatable)")
    args = ap.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    if not args.compiler:
        ap.error("No compiler was named.  Pass --compiler or set PMF_COMPILER to the "
                 "PureMetalForge executable.")

    with tempfile.TemporaryDirectory(prefix="v3d-qpu-") as td:
        workdir = pathlib.Path(td)
        if args.mutate:
            print("a64_v3d_qpu_check --mutate")
            print()
            return mutate(args.compiler, workdir, args.only)

        img = build(args.compiler, workdir, "v3dqpuasm.img")
        x0, text = run(img)
    instrs, shader, hazards, header = parse_probe(text)

    fails: list = []
    check_pins(fails)
    oracle = oracle_corpus()
    checked, disagreements, xchecked = check_corpus(instrs, oracle, fails)
    decoded = check_decoder(instrs, fails)
    shader_n = check_shader(shader, oracle_shader(), header, fails)
    hazard_n = check_hazards(hazards, fails)
    derived_n = check_derived(fails)
    check_unwitnessed(fails)
    check_unoracled(fails)
    check_shader_copies(fails)

    refusals = sum(1 for _, k in NAMES if k.startswith("R:"))
    if x0 != len(NAMES):
        fails.append("The probe returned x0 = %d and the corpus is %d entries."
                     % (x0, len(NAMES)))

    print("a64_v3d_qpu_check - RaspberryPi4/Lib/v3dqpu.pi4")
    print()
    print("  %3d instructions assembled by the library and compared over all" % checked)
    print("      64 bits with py-videocore6's pinned golden words, an")
    print("      independent implementation of the same encoding.")
    print("  %3d refusals, checked against codes written in this gate -" % refusals)
    print("      internal consistency only.")
    print("  %3d hazard sequences refused, with the right rule named." % hazard_n)
    print("  %3d shader instructions built through the emitter and compared" % shader_n)
    print("      with py-videocore6's pinned assembly of the same shader.")
    print("  %3d constants and table rows compared with the pinned Mesa" % derived_n)
    print("      mesa-24.3.4 tables.")
    print("  %3d emitted words decoded by tools/v3d42_qpu_decode.py." % decoded)
    print("  %3d known disagreement between the two implementations," % disagreements)
    print("      confirmed still present: BDU on a branch with UB clear.")
    print()
    print("  %3d VPM loads checked against the pinned Mesa tables and read" % xchecked)
    print("      back by the Anvil decoder, not against py-videocore6, which")
    print("      has no ldvpm operation:")
    print("      %s" % ", ".join(o.lower() for o in UNORACLED))
    print()
    print("  UNWITNESSED, and deliberately absent from the corpus:")
    print("      %s" % ", ".join(UNWITNESSED))
    print("      py-videocore6 cannot encode these.  Their table rows are")
    print("      checked; their packing is not.")
    print()
    print("  WHAT THIS GATE CANNOT SAY: that the silicon decodes any of it")
    print("      the way both encoders think.  pi4V3dCsd.pi4 on the board can.")
    print()

    if fails:
        print("FAIL - %d" % len(fails))
        for f in fails:
            print("  %s" % f)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

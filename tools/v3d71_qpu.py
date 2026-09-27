#!/usr/bin/env python3
"""Independent V3D 7.1 QPU packer, unpacker, disassembler and text assembler.

This is the desk oracle for the Raspberry Pi 5 GPU (BCM2712, V3D 7.1,
VideoCore VII).  It imports nothing from Anvil: every encoding below is
transcribed from Mesa's primary V3D sources at commit
61f259049cf0eb0c69ad2fae50d1268f82fd54e3 (gitlab.freedesktop.org/mesa/mesa):

* src/broadcom/qpu/qpu_pack.c:47-111    -- instruction fields
* src/broadcom/qpu/qpu_pack.c:164-197   -- the V3D 7.1 signal table
* src/broadcom/qpu/qpu_pack.c:239-264   -- the 48 small immediates
* src/broadcom/qpu/qpu_pack.c:296-421   -- condition/flag field
* src/broadcom/qpu/qpu_pack.c:586-813   -- 7.1 add and mul opcode tables
* src/broadcom/qpu/qpu_pack.c:866-1047  -- input unpack / output pack codes
* src/broadcom/qpu/qpu_pack.c:1212-1414, 1501-1581 -- 7.1 add/mul unpack
* src/broadcom/qpu/qpu_pack.c:1847-2142, 2262-2385 -- 7.1 add/mul pack
* src/broadcom/qpu/qpu_pack.c:2408-2636 -- whole-instruction unpack/pack
* src/broadcom/qpu/qpu_instr.c:30-91, 401-554, 1092-1104 -- magic waddr
  names, operand counts, signals that carry a write address
* src/broadcom/qpu/qpu_instr.h:88-133  -- waddr numbers, reserved on 7.x
* src/broadcom/qpu/qpu_disasm.c:93-396 -- the text form reproduced here
* src/broadcom/qpu/tests/qpu_disasm.c:45-46, 64-67, 98 -- Mesa's own 7.1
  vectors, reproduced by --self-test.

A second, independent encoder -- Idein py-videocore7 at commit
4707e67fcba62217293a5bb155bfd594d97d8eb3 (src/_videocore7/assembler.py) --
produced the PYVC7_VECTORS words below; they were decoded by this file and
checked by hand against the py-videocore7 source line recorded beside each.

What changed from V3D 4.2 (the reason this is a second encoder, not a table
edit): there are no accumulators r0-r5 and no input muxes.  Each of the four
ALU inputs names its own register-file address (raddr_a/b for the add ALU at
bits 11:6 and 5:0, raddr_c/d for the mul ALU at bits 23:18 and 17:12, where
V3D 4.2 had the 3-bit muxes), small immediates are selected per input by
four signals (14, 15, 30, 31), 1- and 0-source opcodes are distinguished by
raddr_b/raddr_d instead of the mux fields, ldunif/ldunifa/ldvary results
land in rf0 instead of r5, and magic waddrs 0-4 (r0-r4) and 19-24 (the SFU
writes) are reserved -- the SFU is reached by add opcodes instead.

The packer refuses (PackError) anything it cannot encode exactly, and with
strict=True also refuses writes to waddrs that are reserved on 7.x.  It never
guesses.
"""

from __future__ import annotations

import argparse
import random
import re
import sys
from dataclasses import dataclass, field, replace
from typing import Optional


class DecodeError(ValueError):
    """The word is not a defined V3D 7.1 instruction."""


class PackError(ValueError):
    """The instruction cannot be encoded on V3D 7.1."""


class ParseError(ValueError):
    """The text is not an instruction in the Mesa disassembly syntax."""


def _mask(high: int, low: int) -> int:
    return ((1 << (high - low + 1)) - 1) << low


# qpu_pack.c:47-111
F_OP_MUL = (63, 58)
F_SIG = (57, 53)
F_COND = (52, 46)
SIG_MAGIC_ADDR = 1 << 6
BIT_MM = 1 << 45
BIT_MA = 1 << 44
F_WADDR_M = (43, 38)
F_BRANCH_ADDR_LOW = (55, 35)
F_WADDR_A = (37, 32)
F_BRANCH_COND = (34, 32)
F_BRANCH_ADDR_HIGH = (31, 24)
F_OP_ADD = (31, 24)
F_BRANCH_MSFIGN = (22, 21)
F_RADDR_C = (23, 18)
F_BRANCH_BDU = (17, 15)
BIT_BRANCH_UB = 1 << 14
F_BRANCH_BDI = (13, 12)
F_RADDR_D = (17, 12)
F_RADDR_A = (11, 6)
F_RADDR_B = (5, 0)


def _get(word: int, f: tuple[int, int]) -> int:
    return (word & _mask(*f)) >> f[1]


def _set(value: int, f: tuple[int, int]) -> int:
    v = value << f[1]
    if v & ~_mask(*f):
        raise PackError(f"value {value} does not fit bits {f[0]}:{f[1]}")
    return v


# qpu_pack.c:164-197.  Index = packed signal.  Absent indexes are reserved.
SIGNALS: dict[int, frozenset[str]] = {
    0: frozenset(), 1: frozenset({"thrsw"}), 2: frozenset({"ldunif"}),
    3: frozenset({"thrsw", "ldunif"}), 4: frozenset({"ldtmu"}),
    5: frozenset({"thrsw", "ldtmu"}), 6: frozenset({"ldtmu", "ldunif"}),
    7: frozenset({"thrsw", "ldtmu", "ldunif"}), 8: frozenset({"ldvary"}),
    9: frozenset({"thrsw", "ldvary"}), 10: frozenset({"ldvary", "ldunif"}),
    11: frozenset({"thrsw", "ldvary", "ldunif"}),
    12: frozenset({"ldunifrf"}), 13: frozenset({"thrsw", "ldunifrf"}),
    14: frozenset({"small_imm_a"}), 15: frozenset({"small_imm_b"}),
    16: frozenset({"ldtlb"}), 17: frozenset({"ldtlbu"}),
    18: frozenset({"wrtmuc"}), 19: frozenset({"thrsw", "wrtmuc"}),
    20: frozenset({"ldvary", "wrtmuc"}),
    21: frozenset({"thrsw", "ldvary", "wrtmuc"}),
    22: frozenset({"ucb"}),
    24: frozenset({"ldunifa"}), 25: frozenset({"ldunifarf"}),
    26: frozenset({"ldtmu", "wrtmuc"}),
    27: frozenset({"thrsw", "ldtmu", "wrtmuc"}),
    30: frozenset({"small_imm_c"}), 31: frozenset({"small_imm_d"}),
}
SIGNAL_INDEX = {v: k for k, v in SIGNALS.items()}
# qpu_instr.c:1092-1104 -- these signals carry a write address in the
# condition field instead of flags.
SIG_WRITES_ADDRESS = frozenset({"ldunifrf", "ldunifarf", "ldvary", "ldtmu",
                                "ldtlb", "ldtlbu"})
SMALL_IMM_SIGS = ("small_imm_a", "small_imm_b", "small_imm_c", "small_imm_d")

# qpu_pack.c:239-264
SMALL_IMMEDIATES = [
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
    *[(v & 0xFFFFFFFF) for v in range(-16, 0)],
    0x3b800000, 0x3c000000, 0x3c800000, 0x3d000000, 0x3d800000, 0x3e000000,
    0x3e800000, 0x3f000000, 0x3f800000, 0x40000000, 0x40800000, 0x41000000,
    0x41800000, 0x42000000, 0x42800000, 0x43000000,
]

# qpu_instr.h:60-87 and qpu_instr.c:246-353
CONDS = ["", ".ifa", ".ifb", ".ifna", ".ifnb"]
PFS = ["", ".pushz", ".pushn", ".pushc"]
UFS = ["", ".andz", ".andnz", ".nornz", ".norz", ".andn", ".andnn",
       ".nornn", ".norn", ".andc", ".andnc", ".nornc", ".norc"]
IFA = 1
ANDZ = 1

# qpu_instr.h:88-133 and qpu_instr.c:30-91, as printed for ver >= 71.
MAGIC_WADDR_NAMES = {
    0: "r0", 1: "r1", 2: "r2", 3: "r3", 4: "r4", 5: "quad", 6: "-",
    7: "tlb", 8: "tlbu", 9: "unifa", 10: "tmul", 11: "tmud", 12: "tmua",
    13: "tmuau", 14: "vpm", 15: "vpmu", 16: "sync", 17: "syncu",
    18: "syncb", 19: "recip", 20: "rsqrt", 21: "exp", 22: "log", 23: "sin",
    24: "rsqrt2", 32: "tmuc", 33: "tmus", 34: "tmut", 35: "tmur",
    36: "tmui", 37: "tmub", 38: "tmudref", 39: "tmuoff", 40: "tmuscm",
    41: "tmusf", 42: "tmuslod", 43: "tmuhs", 44: "tmuscm", 45: "tmuhsf",
    46: "tmuhslod", 55: "rep",
}
# Mesa prints both 40 and 44 as "tmuscm" (qpu_instr.c:80, 84); the parser
# therefore maps the name back to 40 only, and 44 must be given as "waddr44".
MAGIC_WADDR_BY_NAME = {}
for _n, _name in sorted(MAGIC_WADDR_NAMES.items(), reverse=True):
    MAGIC_WADDR_BY_NAME[_name] = _n
# qpu_instr.h:89-93, 110-115: reserved on V3D 7.x.
RESERVED_MAGIC_WADDR_71 = frozenset({0, 1, 2, 3, 4, 19, 20, 21, 22, 23, 24})

# Output pack (qpu_instr.h enum v3d_qpu_output_pack) and input unpack.
PACK_NAMES = ["", ".l", ".h"]
U_NONE, U_ABS, U_L, U_H, U_SAT, U_NSAT, U_MAX0 = ("", ".abs", ".l", ".h",
                                                  ".sat", ".nsat", ".max0")
U_FF, U_LL, U_HH, U_SWP = ".ff", ".ll", ".hh", ".swp"
U_UL, U_UH, U_IL, U_IH = ".ul", ".uh", ".il", ".ih"
# qpu_pack.c:866-928 (float32), 930-978 (int32), 980-1028 (float16)
F32_UNPACK = [U_ABS, U_NONE, U_L, U_H, U_SAT, U_NSAT, U_MAX0]
I32_UNPACK = [U_NONE, U_UL, U_UH, U_IL, U_IH]
F16_UNPACK = [U_NONE, U_FF, U_LL, U_HH, U_SWP]


def _code(table: list[str], name: str, what: str) -> int:
    if name not in table:
        raise PackError(f"{what} unpack '{name or 'none'}' is not encodable")
    return table.index(name)


ANY = (1 << 64) - 1


def _r(lo: int, hi: int) -> int:
    return ((1 << (hi - lo + 1)) - 1) << lo


def _b(n: int) -> int:
    return 1 << n


def _ranges(*pairs: tuple[int, int]) -> int:
    m = 0
    for lo, hi in pairs:
        m |= _r(lo, hi)
    return m


def _bits(*ns: int) -> int:
    m = 0
    for n in ns:
        m |= 1 << n
    return m


# qpu_pack.c:586-770 (opcode_first, opcode_last, raddr_b mask, op).  Order
# matters: lookup returns the first match, exactly like Mesa.
ADD_OPS: list[tuple[int, int, int, str]] = [
    (0, 47, ANY, "fadd"), (0, 47, ANY, "faddnf"), (48, 52, ANY, "vfadd"),
    (53, 55, ANY, "vfpack"), (56, 56, ANY, "add"), (57, 59, ANY, "vfpack"),
    (60, 60, ANY, "sub"), (61, 63, ANY, "vfpack"), (64, 111, ANY, "fsub"),
    (112, 119, ANY, "vfsub"), (120, 120, ANY, "min"), (121, 121, ANY, "max"),
    (122, 122, ANY, "umin"), (123, 123, ANY, "umax"), (124, 124, ANY, "shl"),
    (125, 125, ANY, "shr"), (126, 126, ANY, "asr"), (127, 127, ANY, "ror"),
    (128, 175, ANY, "fmin"), (128, 175, ANY, "fmax"),
    (176, 180, ANY, "vfmin"), (181, 181, ANY, "and"), (182, 182, ANY, "or"),
    (183, 183, ANY, "xor"), (184, 184, ANY, "vadd"), (185, 185, ANY, "vsub"),
    (186, 186, _b(0), "not"), (186, 186, _b(1), "neg"),
    (186, 186, _b(2), "flapush"), (186, 186, _b(3), "flbpush"),
    (186, 186, _b(4), "flpop"), (186, 186, _b(5), "clz"),
    (186, 186, _b(6), "setmsf"), (186, 186, _b(7), "setrevf"),
    (187, 187, _b(0), "nop"), (187, 187, _b(1), "tidx"),
    (187, 187, _b(2), "eidx"), (187, 187, _b(3), "lr"),
    (187, 187, _b(4), "vfla"), (187, 187, _b(5), "vflna"),
    (187, 187, _b(6), "vflb"), (187, 187, _b(7), "vflnb"),
    (187, 187, _b(8), "xcd"), (187, 187, _b(9), "ycd"),
    (187, 187, _b(10), "msf"), (187, 187, _b(11), "revf"),
    (187, 187, _b(12), "iid"), (187, 187, _b(13), "sampid"),
    (187, 187, _b(14), "barrierid"), (187, 187, _b(15), "tmuwt"),
    (187, 187, _b(16), "vpmwt"), (187, 187, _b(17), "flafirst"),
    (187, 187, _b(18), "flnafirst"),
    (187, 187, _r(32, 34), "fxcd"), (187, 187, _r(36, 38), "fycd"),
    (187, 187, _b(48), "setnnmode_uu"), (187, 187, _b(49), "setnnmode_su"),
    (187, 187, _b(50), "setnnmode_us"), (187, 187, _b(51), "setnnmode_ss"),
    (188, 188, _b(0), "ldvpmv_in"), (188, 188, _b(1), "ldvpmd_in"),
    (188, 188, _b(2), "ldvpmp"),
    (188, 188, _b(32), "recip"), (188, 188, _b(33), "rsqrt"),
    (188, 188, _b(34), "exp"), (188, 188, _b(35), "log"),
    (188, 188, _b(36), "sin"), (188, 188, _b(37), "rsqrt2"),
    (188, 188, _b(38), "ballot"), (188, 188, _b(39), "bcastf"),
    (188, 188, _b(40), "alleq"), (188, 188, _b(41), "allfeq"),
    (189, 189, ANY, "ldvpmg_in"),
    (190, 190, ANY, "stvpmv"), (190, 190, ANY, "stvpmd"),
    (190, 190, ANY, "stvpmp"),
    (191, 191, _b(0), "vfmov"), (191, 191, _b(5), "vfabs"),
    (191, 191, _b(10), "vfneg"), (191, 191, _b(15), "vfnab"),
    (192, 207, ANY, "fcmp"), (208, 215, ANY, "vfcmp"),
    (240, 244, ANY, "vfmax"),
    (245, 245, _ranges((0, 2), (4, 6), (8, 10), (12, 14)), "fround"),
    (245, 245, _bits(3, 7, 11, 15), "ftoin"),
    (245, 245, _ranges((16, 18), (20, 22), (24, 26), (28, 30)), "ftrunc"),
    (245, 245, _bits(19, 23, 27, 31), "ftoiz"),
    (245, 245, _ranges((32, 34), (36, 38), (40, 42), (44, 46)), "ffloor"),
    (245, 245, _bits(35, 39, 43, 47), "ftouz"),
    (245, 245, _ranges((48, 50), (52, 54), (56, 58), (60, 62)), "fceil"),
    (245, 245, _bits(51, 55, 59, 63), "ftoc"),
    (246, 246, _ranges((0, 2), (4, 6), (8, 10), (12, 14)), "fdx"),
    (246, 246, _ranges((16, 18), (20, 22), (24, 26), (28, 30)), "fdy"),
    (246, 246, _r(32, 34), "itof"), (246, 246, _r(36, 38), "utof"),
    (247, 247, ANY, "vpack"), (248, 248, ANY, "v8pack"),
    (249, 249, _ranges((0, 2), (4, 6), (8, 10), (12, 14), (16, 18),
                       (20, 22), (24, 26)), "fmov"),
    (249, 249, _bits(3, 7, 11, 15, 19), "mov"),
    (250, 250, ANY, "v10pack"), (251, 251, ANY, "v11fpack"),
    (252, 252, ANY, "rotq"), (253, 253, ANY, "rot"),
    (254, 254, ANY, "shuffle"),
]

# qpu_pack.c:772-813 (raddr_d mask)
MUL_OPS: list[tuple[int, int, int, str]] = [
    (1, 1, ANY, "add"), (2, 2, ANY, "sub"), (3, 3, ANY, "umul24"),
    (3, 3, ANY, "umul24_rtop0"), (4, 8, ANY, "vfmul"), (9, 9, ANY, "smul24"),
    (10, 10, ANY, "multop"), (11, 11, ANY, "v8dot"),
    (14, 14, _ranges((0, 2), (4, 6), (8, 10), (12, 14), (16, 18), (20, 22),
                     (24, 26), (28, 30)), "fmov"),
    (14, 14, _bits(3, 7, 11, 15, 19), "mov"),
    (14, 14, _b(32), "ftounorm16"), (14, 14, _b(33), "ftosnorm16"),
    (14, 14, _b(34), "vftounorm8"), (14, 14, _b(35), "vftosnorm8"),
    (14, 14, _b(36), "funpackunormlo"), (14, 14, _b(37), "funpackunormhi"),
    (14, 14, _b(38), "funpacksnormlo"), (14, 14, _b(39), "funpacksnormhi"),
    (14, 14, _b(48), "vftounorm10lo"), (14, 14, _b(49), "vftounorm10hi"),
    (14, 14, _b(63), "nop"),
    (16, 63, ANY, "fmul"),
]

# qpu_instr.c:401-554: D=has dst, number of sources.
_D, _A, _B = 1, 2, 4
_ADD_ARGS_DAB = {"fadd", "faddnf", "vfpack", "add", "sub", "fsub", "min",
                 "max", "umin", "umax", "shl", "shr", "asr", "ror", "fmin",
                 "fmax", "vfmin", "vfadd", "vfsub", "vfcmp", "and", "or",
                 "xor", "vadd", "vsub", "ldvpmg_in", "ldvpmg_out", "fcmp",
                 "vfmax", "vpack", "v8pack", "v10pack", "v11fpack", "rotq",
                 "rot", "shuffle"}
_ADD_ARGS_DA = {"vfmov", "vfabs", "vfneg", "vfnab", "not", "neg", "flapush",
                "flbpush", "flpop", "recip", "setmsf", "setrevf", "vpmsetup",
                "ldvpmv_in", "ldvpmv_out", "ldvpmd_in", "ldvpmd_out",
                "ldvpmp", "rsqrt", "exp", "log", "sin", "rsqrt2", "fround",
                "ftoin", "ftrunc", "ftoiz", "ffloor", "ftouz", "fceil",
                "ftoc", "fdx", "fdy", "itof", "clz", "utof", "mov", "fmov",
                "ballot", "bcastf", "alleq", "allfeq"}
_ADD_ARGS_D = {"tidx", "eidx", "lr", "vfla", "vflna", "vflb", "vflnb",
               "fxcd", "xcd", "fycd", "ycd", "msf", "revf", "vdwwt", "iid",
               "sampid", "barrierid", "tmuwt", "vpmwt", "flafirst",
               "flnafirst"}
_ADD_ARGS_AB = {"stvpmv", "stvpmd", "stvpmp"}
_ADD_ARGS_NONE = {"nop", "setnnmode_uu", "setnnmode_su", "setnnmode_us",
                  "setnnmode_ss"}
_MUL_ARGS_DAB = {"add", "sub", "umul24", "umul24_rtop0", "vfmul", "smul24",
                 "multop", "fmul", "v8dot"}
_MUL_ARGS_DA = {"fmov", "mov", "ftounorm16", "ftosnorm16", "vftounorm8",
                "vftosnorm8", "funpackunormlo", "funpackunormhi",
                "funpacksnormlo", "funpacksnormhi", "vftounorm10lo",
                "vftounorm10hi"}


def add_has_dst(op: str) -> bool:
    return op not in _ADD_ARGS_AB and op not in _ADD_ARGS_NONE


def add_num_src(op: str) -> int:
    if op in _ADD_ARGS_DAB or op in _ADD_ARGS_AB:
        return 2
    if op in _ADD_ARGS_DA:
        return 1
    return 0


def mul_has_dst(op: str) -> bool:
    return op != "nop"


def mul_num_src(op: str) -> int:
    if op in _MUL_ARGS_DAB:
        return 2
    if op in _MUL_ARGS_DA:
        return 1
    return 0


@dataclass
class Src:
    raddr: int = 0
    unpack: str = U_NONE


@dataclass
class Alu:
    op: str = "nop"
    a: Src = field(default_factory=Src)
    b: Src = field(default_factory=Src)
    waddr: int = 6
    magic: bool = True
    pack: str = ""


@dataclass
class Instr:
    """A V3D 7.1 instruction in Mesa's struct v3d_qpu_instr shape."""
    kind: str = "alu"                   # "alu" or "branch"
    sig: frozenset = frozenset()
    sig_addr: int = 0
    sig_magic: bool = False
    ac: int = 0
    mc: int = 0
    apf: int = 0
    mpf: int = 0
    auf: int = 0
    muf: int = 0
    add: Alu = field(default_factory=Alu)
    mul: Alu = field(default_factory=Alu)
    # branch
    cond: int = 0                       # 0 always, 1 a0 .. 6 allna
    msfign: int = 0
    bdi: int = 0
    ub: bool = False
    bdu: int = 0
    b_raddr_a: int = 0
    offset: int = 0


BRANCH_CONDS = ["", ".a0", ".na0", ".alla", ".anyna", ".anya", ".allna"]
MSFIGNS = ["", "p", "q"]


def _lookup_packed(table, opcode: int, raddr: int) -> Optional[str]:
    for lo, hi, mask, op in table:
        if lo <= opcode <= hi and mask & (1 << raddr):
            return op
    return None


def _lookup_op(table, op: str):
    for entry in table:
        if entry[3] == op:
            return entry
    return None


def _ffs(mask: int) -> int:
    return (mask & -mask).bit_length() - 1


# ---------------------------------------------------------------- unpack

def _flags_unpack(p: int, ins: Instr) -> None:
    cond_map = [1, 2, 3, 4]
    if p == 0:
        return
    if p >> 2 == 0:
        ins.apf = p & 3
    elif p >> 4 == 0:
        ins.auf = (p & 0xF) - 4 + ANDZ
    elif p == 0x10:
        raise DecodeError("condition field 0x10 is reserved")
    elif p >> 2 == 0x4:
        ins.mpf = p & 3
    elif p >> 4 == 0x1:
        ins.muf = (p & 0xF) - 4 + ANDZ
    elif p >> 4 == 0x2:
        ins.ac = ((p >> 2) & 3) + IFA
        ins.mpf = p & 3
    elif p >> 4 == 0x3:
        ins.mc = ((p >> 2) & 3) + IFA
        ins.apf = p & 3
    elif p >> 6:
        ins.mc = cond_map[(p >> 4) & 3]
        if ((p >> 2) & 3) == 0:
            ins.ac = cond_map[p & 3]
        else:
            ins.auf = (p & 0xF) - 4 + ANDZ


def _f32(code: int) -> str:
    if code >= len(F32_UNPACK):
        raise DecodeError(f"float32 unpack code {code} is reserved")
    return F32_UNPACK[code]


def _i32(code: int) -> str:
    if code >= len(I32_UNPACK):
        raise DecodeError(f"int32 unpack code {code} is reserved")
    return I32_UNPACK[code]


def _f16(code: int) -> str:
    if code >= len(F16_UNPACK):
        raise DecodeError(f"float16 unpack code {code} is reserved")
    return F16_UNPACK[code]


def _add_unpack(w: int, ins: Instr) -> None:
    op_code = _get(w, F_OP_ADD)
    ra = _get(w, F_RADDR_A)
    rb = _get(w, F_RADDR_B)
    waddr = _get(w, F_WADDR_A)
    op = _lookup_packed(ADD_OPS, op_code, rb)
    if op is None:
        raise DecodeError(f"add opcode {op_code} with raddr_b {rb} is undefined")
    sa = "small_imm_a" in ins.sig
    sb = "small_imm_b" in ins.sig
    if sa * 256 + ((op_code >> 2) & 3) * 64 + ra > sb * 256 + (op_code & 3) * 64 + rb:
        if op == "fmin":
            op = "fmax"
        if op == "fadd":
            op = "faddnf"
    if op.startswith("stvpm"):
        if waddr > 2:
            raise DecodeError(f"stvpm with waddr {waddr} is undefined")
        op = ("stvpmv", "stvpmd", "stvpmp")[waddr]
    a = Alu(op=op)
    if op in ("fadd", "faddnf", "fsub", "fmin", "fmax", "fcmp", "vfpack"):
        a.pack = PACK_NAMES[(op_code >> 4) & 3] if op not in ("vfpack", "fcmp") else ""
        a.a.unpack = _f32((op_code >> 2) & 3)
        a.b.unpack = _f32(op_code & 3)
    elif op in ("ffloor", "fround", "ftrunc", "fceil", "fdx", "fdy"):
        a.pack = PACK_NAMES[rb & 3]
        a.a.unpack = _f32((rb >> 2) & 3)
    elif op in ("ftoin", "ftoiz", "ftouz", "ftoc"):
        a.a.unpack = _f32((rb >> 2) & 3)
    elif op in ("itof", "utof"):
        a.pack = PACK_NAMES[rb & 3]
    elif op in ("vfmin", "vfmax", "vfadd", "vfsub", "vfcmp"):
        if (op_code & 7) > 4:
            raise DecodeError(f"{op} unpack {op_code & 7} is reserved")
        a.a.unpack = _f16(op_code & 7)
    elif op == "mov":
        a.a.unpack = _i32((rb >> 2) & 7)
    elif op == "fmov":
        a.pack = PACK_NAMES[rb & 3]
        u = (rb >> 2) & 7
        if u == 7:
            raise DecodeError("add fmov unpack 7 is reserved")
        a.a.unpack = _f32(u)
    a.a.raddr = ra
    a.b.raddr = rb
    a.waddr = waddr
    a.magic = False
    if w & BIT_MA:
        if op in ("ldvpmv_in", "ldvpmd_in", "ldvpmg_in"):
            a.op = op.replace("_in", "_out")
        else:
            a.magic = True
    ins.add = a


def _mul_unpack(w: int, ins: Instr) -> None:
    op_code = _get(w, F_OP_MUL)
    rc = _get(w, F_RADDR_C)
    rd = _get(w, F_RADDR_D)
    op = _lookup_packed(MUL_OPS, op_code, rd)
    if op is None:
        raise DecodeError(f"mul opcode {op_code} with raddr_d {rd} is undefined")
    m = Alu(op=op)
    if op == "fmul":
        m.pack = PACK_NAMES[((op_code >> 4) & 3) - 1]
        m.a.unpack = _f32((op_code >> 2) & 3)
        m.b.unpack = _f32(op_code & 3)
    elif op == "fmov":
        m.pack = PACK_NAMES[rd & 3]
        m.a.unpack = _f32((rd >> 2) & 7)
    elif op == "vfmul":
        m.a.unpack = _f16(((op_code & 7) - 4) & 7)
    elif op == "mov":
        m.a.unpack = _i32((rd >> 2) & 7)
    m.a.raddr = rc
    m.b.raddr = rd
    m.waddr = _get(w, F_WADDR_M)
    m.magic = bool(w & BIT_MM)
    ins.mul = m


def unpack(w: int) -> Instr:
    """qpu_pack.c:2408-2515 for ver 71."""
    if not 0 <= w < (1 << 64):
        raise DecodeError("instruction words are 64 bits")
    ins = Instr()
    if _get(w, F_OP_MUL) != 0:
        s = _get(w, F_SIG)
        if s not in SIGNALS:
            raise DecodeError(f"signal {s} is reserved on V3D 7.1")
        ins.sig = SIGNALS[s]
        pc = _get(w, F_COND)
        if ins.sig & SIG_WRITES_ADDRESS:
            ins.sig_addr = pc & ~SIG_MAGIC_ADDR
            ins.sig_magic = bool(pc & SIG_MAGIC_ADDR)
        else:
            _flags_unpack(pc, ins)
        _add_unpack(w, ins)
        _mul_unpack(w, ins)
        return ins
    s = _get(w, F_SIG)
    if (s & 24) != 16:
        raise DecodeError("mul opcode 0 is only a branch when sig is 16..23")
    ins.kind = "branch"
    c = _get(w, F_BRANCH_COND)
    if c == 0:
        ins.cond = 0
    elif 2 <= c <= 7:
        ins.cond = c - 1
    else:
        raise DecodeError(f"branch condition {c} is reserved")
    ms = _get(w, F_BRANCH_MSFIGN)
    if ms == 3:
        raise DecodeError("branch msfign 3 is reserved")
    ins.msfign = ms
    ins.bdi = _get(w, F_BRANCH_BDI)
    ins.ub = bool(w & BIT_BRANCH_UB)
    if ins.ub:
        ins.bdu = _get(w, F_BRANCH_BDU)
        if ins.bdu > 3:
            # Mesa accepts and prints nothing (qpu_disasm.c:354-371 has no
            # case); the destination is undefined, so the oracle refuses.
            raise DecodeError(f"branch uniform destination {ins.bdu} is undefined")
    ins.b_raddr_a = _get(w, F_RADDR_A)
    ins.offset = ((_get(w, F_BRANCH_ADDR_LOW) << 3)
                  + (_get(w, F_BRANCH_ADDR_HIGH) << 24)) & 0xFFFFFFFF
    return ins


# ---------------------------------------------------------------- pack

def _flags_pack(ins: Instr) -> int:
    AC, MC, APF, MPF, AUF, MUF = 1, 2, 4, 8, 16, 32
    table = [(0, 0), (APF, 0), (AUF, 0), (MPF, 1 << 4), (MUF, 1 << 4),
             (AC, 1 << 5), (AC | MPF, 1 << 5), (MC, (1 << 5) | (1 << 4)),
             (MC | APF, (1 << 5) | (1 << 4)), (MC | AC, 1 << 6),
             (MC | AUF, 1 << 6)]
    present = ((AC if ins.ac else 0) | (MC if ins.mc else 0)
               | (APF if ins.apf else 0) | (MPF if ins.mpf else 0)
               | (AUF if ins.auf else 0) | (MUF if ins.muf else 0))
    for fp, bits in table:
        if fp != present:
            continue
        p = bits | ins.apf | ins.mpf
        if present & AUF:
            p |= ins.auf - ANDZ + 4
        if present & MUF:
            p |= ins.muf - ANDZ + 4
        if present & AC:
            p |= (ins.ac - IFA) if p & (1 << 6) else (ins.ac - IFA) << 2
        if present & MC:
            p |= (ins.mc - IFA) << 4 if p & (1 << 6) else (ins.mc - IFA) << 2
        return p
    raise PackError("this combination of conditions and flag updates has no encoding")


def _f32c(u: str) -> int:
    return _code(F32_UNPACK, u, "float32")


def _pack_code(p: str) -> int:
    if p not in PACK_NAMES:
        raise PackError(f"output pack '{p}' is not encodable")
    return PACK_NAMES.index(p)


def _add_pack(ins: Instr, word: int) -> int:
    a = ins.add
    waddr, ra, rb = a.waddr, a.a.raddr, a.b.raddr
    # The _out forms share the _in table entry and differ only by MA
    # (qpu_pack.c:1396-1411, 1893-1898).
    entry = _lookup_op(ADD_OPS, a.op.replace("_out", "_in"))
    if entry is None:
        raise PackError(f"'{a.op}' is not a V3D 7.1 add-ALU operation")
    opcode = entry[0]
    if add_num_src(a.op) < 2:
        rb = _ffs(entry[2])
    no_magic = False
    if a.op in ("stvpmv", "stvpmd", "stvpmp"):
        waddr = ("stvpmv", "stvpmd", "stvpmp").index(a.op)
        no_magic = True
    elif a.op in ("ldvpmv_in", "ldvpmd_in", "ldvpmp", "ldvpmg_in"):
        if a.magic:
            raise PackError(f"{a.op} cannot write a magic waddr")
    elif a.op in ("ldvpmv_out", "ldvpmd_out", "ldvpmg_out"):
        if a.magic:
            raise PackError(f"{a.op} cannot write a magic waddr")
        word |= BIT_MA
    op = a.op
    if op in ("fadd", "faddnf", "fsub", "fmin", "fmax", "fcmp"):
        if op != "fcmp":
            opcode |= _pack_code(a.pack) << 4
        au, bu = _f32c(a.a.unpack), _f32c(a.b.unpack)
        if au > 3 or bu > 3:
            raise PackError(f"{op} has only 2-bit input unpack fields")
        sa = "small_imm_a" in ins.sig
        sb = "small_imm_b" in ins.sig
        ordering = sa * 256 + au * 64 + ra > sb * 256 + bu * 64 + rb
        if ((op in ("fmin", "fadd") and ordering)
                or (op in ("fmax", "faddnf") and not ordering)):
            au, bu = bu, au
            ra, rb = rb, ra
            if sa or sb:
                if sa == sb:
                    raise PackError("both add inputs are small immediates")
                new = set(ins.sig)
                new ^= {"small_imm_a", "small_imm_b"}
                word = (word & ~_mask(*F_SIG)) | _set(_sig_pack(frozenset(new)), F_SIG)
            if ra == rb and au == bu and op in ("fadd", "fmin"):
                pass
        # A commutative pair with identical operands cannot express the
        # "nf"/"max" variant: the ordering test can never be true.
        opcode |= au << 2 | bu
    elif op == "vfpack":
        if U_ABS in (a.a.unpack, a.b.unpack):
            raise PackError("vfpack inputs cannot use .abs")
        au, bu = _f32c(a.a.unpack), _f32c(a.b.unpack)
        if au > 3 or bu > 3:
            raise PackError("vfpack has only 2-bit input unpack fields")
        opcode = (opcode & ~(3 << 2)) | au << 2
        opcode = (opcode & ~3) | bu
    elif op in ("ffloor", "fround", "ftrunc", "fceil", "fdx", "fdy"):
        rb |= _pack_code(a.pack)
        c = _f32c(a.a.unpack)
        if c == 0 or c > 3:
            raise PackError(f"{op} input unpack '{a.a.unpack}' is not encodable")
        rb = (rb & ~(3 << 2)) | c << 2
    elif op in ("ftoin", "ftoiz", "ftouz", "ftoc"):
        if a.pack:
            raise PackError(f"{op} has no output pack")
        c = _f32c(a.a.unpack)
        if c == 0 or c > 3:
            raise PackError(f"{op} input unpack '{a.a.unpack}' is not encodable")
        rb |= (rb & ~(3 << 2)) | c << 2
    elif op in ("itof", "utof"):
        if a.a.unpack:
            raise PackError(f"{op} has no input unpack")
        rb |= _pack_code(a.pack)
    elif op in ("vfmin", "vfmax", "vfsub", "vfadd", "vfcmp"):
        if a.pack or a.b.unpack:
            raise PackError(f"{op} has no output pack and no b unpack")
        opcode |= _code(F16_UNPACK, a.a.unpack, "float16")
    elif op in ("vfmov", "vfabs", "vfneg", "vfnab"):
        if a.pack or a.a.unpack or a.b.unpack:
            raise PackError(f"{op} takes no pack or unpack")
    elif op == "mov":
        if a.pack:
            raise PackError("mov has no output pack")
        rb |= _code(I32_UNPACK, a.a.unpack, "int32") << 2
    elif op == "fmov":
        rb = _pack_code(a.pack)
        rb |= _f32c(a.a.unpack) << 2
    else:
        if op != "nop" and (a.pack or a.a.unpack or a.b.unpack):
            raise PackError(f"{op} takes no pack or unpack")
    word |= _set(ra, F_RADDR_A) | _set(rb, F_RADDR_B)
    word |= _set(opcode, F_OP_ADD) | _set(waddr, F_WADDR_A)
    if a.magic and not no_magic:
        word |= BIT_MA
    return word


def _mul_pack(ins: Instr, word: int) -> int:
    m = ins.mul
    rc, rd = m.a.raddr, m.b.raddr
    entry = _lookup_op(MUL_OPS, m.op)
    if entry is None:
        raise PackError(f"'{m.op}' is not a V3D 7.1 mul-ALU operation")
    opcode = entry[0]
    if mul_num_src(m.op) < 2:
        rd = _ffs(entry[2])
    if m.op == "fmul":
        opcode += _pack_code(m.pack) << 4
        au, bu = _f32c(m.a.unpack), _f32c(m.b.unpack)
        if au > 3 or bu > 3:
            raise PackError("fmul has only 2-bit input unpack fields")
        opcode |= au << 2 | bu
    elif m.op == "fmov":
        rd |= _pack_code(m.pack)
        rd |= _f32c(m.a.unpack) << 2
    elif m.op == "vfmul":
        if m.pack or m.b.unpack:
            raise PackError("vfmul has no output pack and no b unpack")
        c = _code(F16_UNPACK, m.a.unpack, "float16")
        opcode = 8 if m.a.unpack == U_SWP else opcode | ((c + 4) & 7)
    elif m.op == "mov":
        if m.pack:
            raise PackError("mov has no output pack")
        rd |= _code(I32_UNPACK, m.a.unpack, "int32") << 2
    else:
        if m.op != "nop" and (m.pack or m.a.unpack or m.b.unpack):
            raise PackError(f"{m.op} takes no pack or unpack")
    word |= _set(rc, F_RADDR_C) | _set(rd, F_RADDR_D)
    word |= _set(opcode, F_OP_MUL) | _set(m.waddr, F_WADDR_M)
    if m.magic:
        word |= BIT_MM
    return word


def _sig_pack(sig: frozenset) -> int:
    if sig not in SIGNAL_INDEX:
        raise PackError("signal combination {" + ", ".join(sorted(sig))
                        + "} has no V3D 7.1 encoding")
    return SIGNAL_INDEX[sig]


def _check_strict(ins: Instr) -> None:
    for unit, alu, has_dst in (("add", ins.add, add_has_dst(ins.add.op)),
                               ("mul", ins.mul, mul_has_dst(ins.mul.op))):
        if has_dst and alu.magic and alu.waddr in RESERVED_MAGIC_WADDR_71:
            raise PackError(f"{unit} writes magic waddr {alu.waddr} "
                            f"({MAGIC_WADDR_NAMES[alu.waddr]}), reserved on "
                            "V3D 7.1 (qpu_instr.h:89-115)")
    if ins.sig & SIG_WRITES_ADDRESS and ins.sig_magic and \
            ins.sig_addr in RESERVED_MAGIC_WADDR_71:
        raise PackError(f"signal writes reserved magic waddr {ins.sig_addr}")


def pack(ins: Instr, strict: bool = False) -> int:
    """qpu_pack.c:2518-2636 for ver 71."""
    if ins.kind == "branch":
        w = _set(16, F_SIG)
        if ins.cond:
            w |= _set(ins.cond + 1, F_BRANCH_COND)
        w |= _set(ins.msfign, F_BRANCH_MSFIGN) | _set(ins.bdi, F_BRANCH_BDI)
        if ins.ub:
            w |= BIT_BRANCH_UB | _set(ins.bdu, F_BRANCH_BDU)
        if ins.bdi in (0, 1):
            off = ins.offset & 0xFFFFFFFF
            w |= _set((off & 0x00FFFFFF) >> 3, F_BRANCH_ADDR_LOW)
            w |= _set(off >> 24, F_BRANCH_ADDR_HIGH)
        if ins.bdi == 3 or ins.bdu == 3:
            w |= _set(ins.b_raddr_a, F_RADDR_A)
        return w
    if strict:
        _check_strict(ins)
    w = _set(_sig_pack(ins.sig), F_SIG)
    w = _add_pack(ins, w)
    w = _mul_pack(ins, w)
    if ins.sig & SIG_WRITES_ADDRESS:
        if ins.ac or ins.mc or ins.apf or ins.mpf or ins.auf or ins.muf:
            raise PackError("a signal that writes an address leaves no room for flags")
        flags = ins.sig_addr | (SIG_MAGIC_ADDR if ins.sig_magic else 0)
    else:
        flags = _flags_pack(ins)
    return w | _set(flags, F_COND)


# ---------------------------------------------------------------- text

def _raddr_text(raddr: int, imm: bool) -> str:
    if imm:
        if raddr >= len(SMALL_IMMEDIATES):
            raise DecodeError(f"small immediate index {raddr} is reserved")
        v = SMALL_IMMEDIATES[raddr]
        sv = v - (1 << 32) if v & 0x80000000 else v
        return str(sv) if -16 <= sv <= 15 else f"0x{v:08x}"
    return f"rf{raddr}"


def _waddr_text(waddr: int, magic: bool) -> str:
    if not magic:
        return f"rf{waddr}"
    return MAGIC_WADDR_NAMES.get(waddr, f"waddr UNKNOWN {waddr}")


def _pad(s: str, n: int) -> str:
    return s + " " * (n - len(s)) if len(s) < n else s


def disasm_instr(ins: Instr) -> str:
    """qpu_disasm.c:93-396 for ver 71."""
    if ins.kind == "branch":
        s = "b" + ("u" if ins.ub else "") + BRANCH_CONDS[ins.cond] + MSFIGNS[ins.msfign]
        off = ins.offset - (1 << 32) if ins.offset & 0x80000000 else ins.offset
        s += ["  zero_addr+0x%08x" % ins.offset, "  %d" % off, "  lri",
              "  rf%d" % ins.b_raddr_a][ins.bdi]
        if ins.ub:
            s += [", a:unif", ", r:unif", ", lri", ", rf%d" % ins.b_raddr_a][ins.bdu]
        return s
    wa = bool(ins.sig & SIG_WRITES_ADDRESS)
    a = ins.add
    s = a.op + ("" if wa else CONDS[ins.ac]) + PFS[ins.apf] + UFS[ins.auf] + " "
    hd, ns = add_has_dst(a.op), add_num_src(a.op)
    if hd:
        s += _waddr_text(a.waddr, a.magic) + a.pack
    if ns >= 1:
        if hd:
            s += ", "
        s += _raddr_text(a.a.raddr, "small_imm_a" in ins.sig) + a.a.unpack
    if ns >= 2:
        s += ", " + _raddr_text(a.b.raddr, "small_imm_b" in ins.sig) + a.b.unpack
    m = ins.mul
    s = _pad(s, 30) + "; " + m.op + ("" if wa else CONDS[ins.mc]) + PFS[ins.mpf] + UFS[ins.muf]
    if m.op != "nop":
        s += " "
        hd, ns = mul_has_dst(m.op), mul_num_src(m.op)
        if hd:
            s += _waddr_text(m.waddr, m.magic) + m.pack
        if ns >= 1:
            if hd:
                s += ", "
            s += _raddr_text(m.a.raddr, "small_imm_c" in ins.sig) + m.a.unpack
        if ns >= 2:
            s += ", " + _raddr_text(m.b.raddr, "small_imm_d" in ins.sig) + m.b.unpack
    shown = ("thrsw", "ldvary", "ldvpm", "ldtmu", "ldtlb", "ldtlbu", "ldunif",
             "ldunifrf", "ldunifa", "ldunifarf", "wrtmuc")
    if ins.sig & set(shown):
        s = _pad(s, 60)

        def addr() -> str:
            if not ins.sig_magic:
                return f".rf{ins.sig_addr}"
            n = MAGIC_WADDR_NAMES.get(ins.sig_addr)
            return f".{n}" if n else f".UNKNOWN{ins.sig_addr}"
        for name in shown:
            if name in ins.sig:
                s += "; " + name
                if name in SIG_WRITES_ADDRESS:
                    s += addr()
    return s


def disasm(w: int) -> str:
    return disasm_instr(unpack(w))


_SUFFIX_UNPACK = [U_ABS, U_L, U_H, U_SAT, U_NSAT, U_MAX0, U_FF, U_LL, U_HH,
                  U_SWP, U_UL, U_UH, U_IL, U_IH]


def _parse_operand(tok: str) -> tuple[str, str]:
    for u in sorted(_SUFFIX_UNPACK, key=len, reverse=True):
        if tok.endswith(u) and not re.fullmatch(r"-?\d+", tok):
            return tok[: -len(u)], u
    return tok, U_NONE


def _parse_src(tok: str) -> tuple[int, bool, str]:
    base, u = _parse_operand(tok.strip())
    m = re.fullmatch(r"rf(\d+)", base)
    if m:
        return int(m.group(1)), False, u
    try:
        v = int(base, 0) & 0xFFFFFFFF
    except ValueError:
        raise ParseError(f"source '{tok}' is neither rfN nor a small immediate")
    if v not in SMALL_IMMEDIATES:
        raise ParseError(f"{base} is not one of the 48 small immediates")
    return SMALL_IMMEDIATES.index(v), True, u


def _parse_dst(tok: str) -> tuple[int, bool, str]:
    tok = tok.strip()
    p = ""
    for cand in (".l", ".h"):
        if tok.endswith(cand):
            tok, p = tok[:-2], cand
    m = re.fullmatch(r"rf(\d+)", tok)
    if m:
        return int(m.group(1)), False, p
    m = re.fullmatch(r"waddr(\d+)", tok)
    if m:
        return int(m.group(1)), True, p
    if tok in MAGIC_WADDR_BY_NAME:
        return MAGIC_WADDR_BY_NAME[tok], True, p
    raise ParseError(f"destination '{tok}' is not rfN or a magic waddr name")


def _parse_opname(tok: str, which: str) -> tuple[str, int, int, int]:
    parts = tok.split(".")
    op, cond, pf, uf = parts[0], 0, 0, 0
    for p in parts[1:]:
        p = "." + p
        if p in CONDS:
            cond = CONDS.index(p)
        elif p in PFS:
            pf = PFS.index(p)
        elif p in UFS:
            uf = UFS.index(p)
        else:
            raise ParseError(f"unknown {which} suffix '{p}'")
    return op, cond, pf, uf


def _parse_alu_part(text: str, unit: str, ins: Instr, imm_sigs: tuple[str, str]) -> Alu:
    text = text.strip()
    head, _, rest = text.partition(" ")
    op, cond, pf, uf = _parse_opname(head, unit)
    if unit == "add":
        ins.ac, ins.apf, ins.auf = cond, pf, uf
        hd, ns = add_has_dst(op), add_num_src(op)
    else:
        ins.mc, ins.mpf, ins.muf = cond, pf, uf
        hd, ns = mul_has_dst(op), mul_num_src(op)
    # The text of an operation without a destination carries no waddr; the
    # encoding Mesa's compiler emits (and its vectors hold) is rf0, non-magic.
    alu = Alu(op=op, waddr=0, magic=False)
    ops = [t for t in rest.split(",")] if rest.strip() else []
    expected = (1 if hd else 0) + ns
    if unit == "mul" and op == "nop":
        expected = 0
    if len(ops) != expected:
        raise ParseError(f"{unit} '{op}' takes {expected} operands, got {len(ops)}")
    i = 0
    if hd and expected:
        alu.waddr, alu.magic, alu.pack = _parse_dst(ops[0])
        i = 1
    for n, src in enumerate((alu.a, alu.b)[:ns]):
        raddr, imm, u = _parse_src(ops[i + n])
        src.raddr, src.unpack = raddr, u
        if imm:
            ins.sig = ins.sig | {imm_sigs[n]}
    return alu


def assemble(text: str) -> Instr:
    """Parse one instruction in qpu_disasm.c's syntax."""
    text = text.strip()
    ins = Instr()
    m = re.fullmatch(r"b(u?)(\.a0|\.na0|\.alla|\.anyna|\.anya|\.allna)?([pq]?)\s+(.*)", text)
    if m and not text.startswith(("barrierid", "bcastf", "ballot")):
        ins.kind = "branch"
        ins.ub = bool(m.group(1))
        ins.cond = BRANCH_CONDS.index(m.group(2) or "")
        ins.msfign = MSFIGNS.index(m.group(3))
        dests = [d.strip() for d in m.group(4).split(",")]
        d = dests[0]
        if d.startswith("zero_addr+"):
            ins.bdi, ins.offset = 0, int(d[len("zero_addr+"):], 16)
        elif d == "lri":
            ins.bdi = 2
        elif d.startswith("rf"):
            ins.bdi, ins.b_raddr_a = 3, int(d[2:])
        else:
            ins.bdi, ins.offset = 1, int(d) & 0xFFFFFFFF
        if ins.ub:
            if len(dests) != 2:
                raise ParseError("bu needs a uniform destination")
            u = dests[1]
            if u == "a:unif":
                ins.bdu = 0
            elif u == "r:unif":
                ins.bdu = 1
            elif u == "lri":
                ins.bdu = 2
            elif u.startswith("rf"):
                ins.bdu = 3
                r = int(u[2:])
                if ins.bdi == 3 and r != ins.b_raddr_a:
                    raise ParseError("branch and uniform register files share raddr_a")
                ins.b_raddr_a = r
            else:
                raise ParseError(f"bad uniform destination '{u}'")
        return ins
    parts = [p for p in text.split(";")]
    if len(parts) < 2:
        raise ParseError("an ALU instruction needs '<add> ; <mul>'")
    sig = set()
    for p in parts[2:]:
        p = p.strip()
        name, _, addr = p.partition(".")
        if name not in ("thrsw", "ldvary", "ldvpm", "ldtmu", "ldtlb", "ldtlbu",
                        "ldunif", "ldunifrf", "ldunifa", "ldunifarf", "wrtmuc"):
            raise ParseError(f"unknown signal '{p}'")
        sig.add(name)
        if name in SIG_WRITES_ADDRESS:
            if not addr:
                raise ParseError(f"{name} needs a destination")
            mm = re.fullmatch(r"rf(\d+)", addr)
            if mm:
                ins.sig_addr, ins.sig_magic = int(mm.group(1)), False
            elif addr in MAGIC_WADDR_BY_NAME:
                ins.sig_addr, ins.sig_magic = MAGIC_WADDR_BY_NAME[addr], True
            else:
                raise ParseError(f"bad signal destination '{addr}'")
        elif addr:
            raise ParseError(f"{name} takes no destination")
    ins.sig = frozenset(sig)
    ins.add = _parse_alu_part(parts[0], "add", ins, ("small_imm_a", "small_imm_b"))
    ins.mul = _parse_alu_part(parts[1], "mul", ins, ("small_imm_c", "small_imm_d"))
    ins.sig = frozenset(ins.sig)
    return ins


# ---------------------------------------------------------------- vectors

# Mesa src/broadcom/qpu/tests/qpu_disasm.c lines 45, 46, 64, 65, 66, 67, 98.
MESA_VECTORS = [
    (0x38000411f9190250, "fmov rf17, rf9.sat            ; fmov rf16, rf6.sat"),
    (0x3800000af503f168, "ffloor rf10, rf5.l            ; nop"),
    (0x39c0000a3803f042, "add rf10, 1, rf2              ; nop"),
    (0x39e0000b3c03f0de, "sub rf11, rf3, -2             ; nop"),
    (0x57c00340bb105000, "nop                           ; fmul rf13, 4, rf5"),
    (0x27e00380bb188000, "nop                           ; smul24 rf14, rf6, 8"),
    (0x2c000300bb042030, "setnnmode_uu                  ; v8dot rf12, rf1, rf2"),
]

# Words produced by Idein py-videocore7 (commit 4707e67f,
# src/_videocore7/assembler.py) from the source line on the right; decoded
# here and checked by hand against that source.  See the vault note
# "Raspberry Pi 5/GPU - V3D 7.1 port plan.md" for how they were generated.
PYVC7_VECTORS: list[tuple[int, str, str]] = [
    (0x38003186bb03f000, 'nop()',
     'nop                           ; nop'),
    (0x38203186bb03f000, 'nop(sig=thrsw)',
     'nop                           ; nop                         ; thrsw'),
    (0x38403186bb03f000, 'nop(sig=ldunif)',
     'nop                           ; nop                         ; ldunif'),
    (0x3980f186bb03f000, 'nop(sig=ldunifrf(rf3))',
     'nop                           ; nop                         ; ldunifrf.rf3'),
    (0x3882f186bb03f000, 'nop(sig=ldtmu(rf11))',
     'nop                           ; nop                         ; ldtmu.rf11'),
    (0x3980218abb03f002, 'eidx(rf10, sig=ldunifrf(rf0))',
     'eidx rf10                     ; nop                         ; ldunifrf.rf0'),
    (0x38002185bb03f001, 'tidx(rf5)',
     'tidx rf5                      ; nop'),
    (0x39c0218df903f103, 'mov(rf13, 4)',
     'mov rf13, 4                   ; nop'),
    (0x3800218df903f1c3, 'mov(rf13, rf7)',
     'mov rf13, rf7                 ; nop'),
    (0x39e0218d7c03f344, 'shl(rf13, rf13, 4)',
     'shl rf13, rf13, 4             ; nop'),
    (0x380021803803f00a, 'add(rf0, rf0, rf10)',
     'add rf0, rf0, rf10            ; nop'),
    (0x380021843c03f146, 'sub(rf4, rf5, rf6)',
     'sub rf4, rf5, rf6             ; nop'),
    (0x380021810503f083, 'fadd(rf1, rf2, rf3)',
     'fadd rf1, rf2, rf3            ; nop'),
    (0x380021810503f0c2, 'faddnf(rf1, rf2, rf3)',
     'faddnf rf1, rf3, rf2          ; nop'),
    (0x380021818503f083, 'fmin(rf1, rf2, rf3)',
     'fmin rf1, rf2, rf3            ; nop'),
    (0x380021818503f0c2, 'fmax(rf1, rf2, rf3)',
     'fmax rf1, rf3, rf2            ; nop'),
    (0x380021814503f083, 'fsub(rf1, rf2, rf3)',
     'fsub rf1, rf2, rf3            ; nop'),
    (0x38002181b503f083, 'band(rf1, rf2, rf3)',
     'and rf1, rf2, rf3             ; nop'),
    (0x38002181b603f083, 'bor(rf1, rf2, rf3)',
     'or rf1, rf2, rf3              ; nop'),
    (0x38002181b703f083, 'bxor(rf1, rf2, rf3)',
     'xor rf1, rf2, rf3             ; nop'),
    (0x380021817a03f083, 'umin(rf1, rf2, rf3)',
     'umin rf1, rf2, rf3            ; nop'),
    (0x39e021817d03f083, 'shr(rf1, rf2, 3)',
     'shr rf1, rf2, 3               ; nop'),
    (0x380021817e03f083, 'asr(rf1, rf2, rf3)',
     'asr rf1, rf2, rf3             ; nop'),
    (0x380021817f03f083, 'ror(rf1, rf2, rf3)',
     'ror rf1, rf2, rf3             ; nop'),
    (0x38002181f603f0a0, 'itof(rf1, rf2)',
     'itof rf1, rf2                 ; nop'),
    (0x38002181f603f0a4, 'utof(rf1, rf2)',
     'utof rf1, rf2                 ; nop'),
    (0x38002181f503f097, 'ftoiz(rf1, rf2)',
     'ftoiz rf1, rf2                ; nop'),
    (0x38002181f503f0a7, 'ftouz(rf1, rf2)',
     'ftouz rf1, rf2                ; nop'),
    (0x38002181f503f0a4, 'ffloor(rf1, rf2)',
     'ffloor rf1, rf2               ; nop'),
    (0x38002181f503f084, 'fround(rf1, rf2)',
     'fround rf1, rf2               ; nop'),
    (0x38002181f503f0b4, 'fceil(rf1, rf2)',
     'fceil rf1, rf2                ; nop'),
    (0x38002181ba03f085, 'clz(rf1, rf2)',
     'clz rf1, rf2                  ; nop'),
    (0x38002181f903f084, 'fmov(rf1, rf2)',
     'fmov rf1, rf2                 ; nop'),
    (0x38002181bc03f0a0, 'recip(rf1, rf2)',
     'recip rf1, rf2                ; nop'),
    (0x38002181bc03f0a1, 'rsqrt(rf1, rf2)',
     'rsqrt rf1, rf2                ; nop'),
    (0x38002181bc03f0a2, 'exp(rf1, rf2)',
     'exp rf1, rf2                  ; nop'),
    (0x38002181bc03f0a3, 'log(rf1, rf2)',
     'log rf1, rf2                  ; nop'),
    (0x38002181bc03f0a4, 'sin(rf1, rf2)',
     'sin rf1, rf2                  ; nop'),
    (0x0420100cf900d003, 'mov(tmua, rf0, sig=thrsw).add(rf0, rf0, rf13)',
     'mov tmua, rf0                 ; add rf0, rf0, rf13          ; thrsw'),
    (0x3800318bf903f283, 'mov(tmud, rf10)',
     'mov tmud, rf10                ; nop'),
    (0x54001046bb083000, 'nop().fmul(rf1, rf2, rf3)',
     'nop                           ; fmul rf1, rf2, rf3'),
    (0x0c001046bb083000, 'nop().umul24(rf1, rf2, rf3)',
     'nop                           ; umul24 rf1, rf2, rf3'),
    (0x24001046bb083000, 'nop().smul24(rf1, rf2, rf3)',
     'nop                           ; smul24 rf1, rf2, rf3'),
    (0x38001046bb083000, 'nop().mov(rf1, rf2)',
     'nop                           ; mov rf1, rf2'),
    (0x38001046bb084000, 'nop().fmov(rf1, rf2)',
     'nop                           ; fmov rf1, rf2'),
    (0x5400010138146083, 'add(rf1, rf2, rf3).fmul(rf4, rf5, rf6)',
     'add rf1, rf2, rf3             ; fmul rf4, rf5, rf6'),
    (0x380061813803f083, "add(rf1, rf2, rf3, cond='pushz')",
     'add.pushz rf1, rf2, rf3       ; nop'),
    (0x380821813803f083, "add(rf1, rf2, rf3, cond='ifa')",
     'add.ifa rf1, rf2, rf3         ; nop'),
    (0x38203192bb03f00e, 'barrierid(syncb, sig=thrsw)',
     'barrierid syncb               ; nop                         ; thrsw'),
    (0x380021813503f083, 'vfpack(rf1, rf2, rf3)',
     'vfpack rf1, rf2, rf3          ; nop'),
    (0x38002181c503f083, 'fcmp(rf1, rf2, rf3)',
     'fcmp rf1, rf2, rf3            ; nop'),
    (0x38002181bb03f00f, 'tmuwt(rf1)',
     'tmuwt rf1                     ; nop'),
    (0x38003187f903f043, 'mov(tlb, rf1)',
     'mov tlb, rf1                  ; nop'),
    (0x3900b186bb03f000, 'nop(sig=ldvary(rf2))',
     'nop                           ; nop                         ; ldvary.rf2'),
    (0x3a00b186bb03f000, 'nop(sig=ldtlb(rf2))',
     'nop                           ; nop                         ; ldtlb.rf2'),
]


ROUNDING_OPS = frozenset({"ffloor", "fround", "ftrunc", "fceil", "fdx", "fdy",
                          "ftoin", "ftoiz", "ftouz", "ftoc"})


def _swap_commutative(ins: Instr) -> Instr:
    """tests/qpu_disasm.c:163-180: swapped operands must repack identically."""
    s = replace(ins, add=replace(ins.add, a=replace(ins.add.b), b=replace(ins.add.a)))
    if ("small_imm_a" in ins.sig) != ("small_imm_b" in ins.sig):
        s.sig = frozenset(set(ins.sig) ^ {"small_imm_a", "small_imm_b"})
    return s


def self_test(fuzz: int = 20000, seed: int = 71) -> int:
    failures = 0
    vectors = [(w, t, "mesa") for w, t in MESA_VECTORS]
    vectors += [(w, t, "py-videocore7: " + src) for w, src, t in PYVC7_VECTORS]
    for w, text, where in vectors:
        got = disasm(w)
        if got != text:
            print(f"FAIL disasm {w:#018x} ({where})\n  want {text!r}\n  got  {got!r}")
            failures += 1
            continue
        ins = unpack(w)
        if ins.kind == "alu" and ins.add.op in ("fadd", "faddnf", "fmin", "fmax"):
            ins = _swap_commutative(ins)
        rp = pack(ins)
        if rp != w:
            print(f"FAIL repack {w:#018x} -> {rp:#018x} ({where})")
            failures += 1
        ap = pack(assemble(text))
        if where != "mesa":
            # py-videocore7 fills the waddr of destination-less operations
            # with 6 (magic "-"); Mesa and this parser use 0.  The text does
            # not carry those bits, so compare at the text level.
            if disasm(ap) != text:
                print(f"FAIL assemble {text!r} -> {disasm(ap)!r} ({where})")
                failures += 1
        elif ap != w:
            print(f"FAIL assemble {text!r} -> {ap:#018x}, want {w:#018x} ({where})")
            failures += 1
    # Idempotence over random words: whatever decodes must re-encode to a
    # word that decodes to the same text and packs to itself.
    rng = random.Random(seed)
    decoded = 0
    asymmetric = 0
    for _ in range(fuzz):
        w = rng.getrandbits(64)
        try:
            t = disasm(w)
        except DecodeError:
            continue
        decoded += 1
        try:
            w2 = pack(unpack(w))
        except PackError as e:
            u = unpack(w)
            if u.kind == "alu" and u.add.op in ("fadd", "faddnf", "fmin", "fmax"):
                asymmetric += 1
                continue   # identical operands: Mesa cannot pack the "nf"/"max" twin either
            if (u.kind == "alu" and u.add.op in ROUNDING_OPS
                    and u.add.a.unpack == U_ABS):
                # Mesa decodes code 0 as .abs for these ops but its packer
                # refuses it (qpu_pack.c:2024-2025, 2043-2044).  Same here.
                asymmetric += 1
                continue
            print(f"FAIL pack {w:#018x} {t!r}: {e}")
            failures += 1
            continue
        t2 = disasm(w2)
        if t2 != t or pack(unpack(w2)) != w2:
            print(f"FAIL idempotence {w:#018x} {t!r} -> {w2:#018x} {t2!r}")
            failures += 1
            continue
        try:
            w3 = pack(assemble(t))
        except (ParseError, PackError) as e:
            if "waddr UNKNOWN" in t or "UNKNOWN" in t or "tmuscm" in t:
                continue
            print(f"FAIL assemble {t!r}: {e}")
            failures += 1
            continue
        if disasm(w3) != t:
            print(f"FAIL text round trip {t!r} -> {disasm(w3)!r}")
            failures += 1
    # Loud refusals the oracle promises.
    for bad, why in (("mov r0, rf1                   ; nop", "reserved waddr"),
                     ("recip rf1, rf2 ; mov recip, rf3", "reserved waddr")):
        try:
            pack(assemble(bad), strict=True)
            print(f"FAIL strict pack accepted {bad!r} ({why})")
            failures += 1
        except PackError:
            pass
    for bad in ("add rf1, 1, 2 ; nop", "fadd rf1, rf2 ; nop", "b.xx  12"):
        try:
            pack(assemble(bad))
            print(f"FAIL accepted {bad!r}")
            failures += 1
        except (ParseError, PackError):
            pass
    print(f"v3d71_qpu self-test: {len(vectors)} vectors, {decoded} random words "
          f"decoded ({asymmetric} decode-only as in Mesa), {failures} failure(s)")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--disasm", nargs="*", metavar="WORD",
                    help="64-bit words (hex) to disassemble")
    ap.add_argument("--asm", nargs="*", metavar="TEXT",
                    help="instructions in Mesa syntax to assemble")
    ap.add_argument("--strict", action="store_true",
                    help="refuse writes to waddrs reserved on V3D 7.1")
    ns = ap.parse_args(argv)
    rc = 0
    if ns.self_test:
        rc |= self_test()
    for w in ns.disasm or []:
        print(f"{int(w, 16):#018x}  {disasm(int(w, 16))}")
    for t in ns.asm or []:
        print(f"{pack(assemble(t), strict=ns.strict):#018x}  {t}")
    if not (ns.self_test or ns.disasm or ns.asm):
        ap.print_help()
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""Independent V3D 4.2 QPU decoder and straight-line verifier.

This is deliberately downstream of the byte stream: it imports neither the
PureMetal packer nor the Vulkan shader emitter.  Encodings and restrictions
are transcribed from Mesa's primary V3D sources (Mesa 23.3.6 in this tree):

* src/broadcom/qpu/qpu_pack.c:47-161, 457-574, 1050-1169, 1360-1428,
  2304-2411 -- fields, signal/opcode tables and the 4.2 unpack path.
* src/broadcom/qpu/qpu_instr.c:600-650, 1009-1073 -- magic-unit and
  signal-destination classification.
* src/broadcom/compiler/qpu_validate.c:170-391 -- instruction hazards.

The verifier intentionally promises the V3D 4.2 straight-line subset used by
Anvil's five current Vulkan shader variants.  It rejects rather than guesses
when a word is outside that subset.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


class DecodeError(ValueError):
    """A word is not a defined V3D 4.2 instruction in the audited subset."""


class VerifyError(ValueError):
    """A decoded program violates an instruction or shader contract."""


SIGNALS = {
    0: frozenset(), 1: frozenset(("thrsw",)), 2: frozenset(("ldunif",)),
    3: frozenset(("thrsw", "ldunif")), 4: frozenset(("ldtmu",)),
    5: frozenset(("thrsw", "ldtmu")),
    6: frozenset(("ldtmu", "ldunif")),
    7: frozenset(("thrsw", "ldtmu", "ldunif")),
    8: frozenset(("ldvary",)), 9: frozenset(("thrsw", "ldvary")),
    10: frozenset(("ldvary", "ldunif")),
    11: frozenset(("thrsw", "ldvary", "ldunif")),
    12: frozenset(("ldunifrf",)),
    13: frozenset(("thrsw", "ldunifrf")),
    14: frozenset(("smimm", "ldvary")), 15: frozenset(("smimm",)),
    16: frozenset(("ldtlb",)), 17: frozenset(("ldtlbu",)),
    18: frozenset(("wrtmuc",)), 19: frozenset(("thrsw", "wrtmuc")),
    20: frozenset(("ldvary", "wrtmuc")),
    21: frozenset(("thrsw", "ldvary", "wrtmuc")),
    22: frozenset(("ucb",)), 23: frozenset(("rotate",)),
    24: frozenset(("ldunifa",)), 25: frozenset(("ldunifarf",)),
    31: frozenset(("smimm", "ldtmu")),
}

SIGNAL_WRITES = frozenset(("ldunifrf", "ldunifarf", "ldvary", "ldtmu",
                           "ldtlb", "ldtlbu"))
TMU_WADDRS = frozenset(range(11, 14)) | frozenset(range(32, 40))
SFU_WADDRS = frozenset(range(19, 25))
VPM_WADDRS = frozenset((14, 15))
TLB_WADDRS = frozenset((7, 8))
TSY_WADDRS = frozenset((16, 17, 18))
UNIFORM_MAGIC_WADDRS = frozenset((8, 13, 15, 17))
WADDR_NAMES = {
    6: "nop", 7: "tlb", 8: "tlbu", 9: "unifa", 10: "tmul",
    11: "tmud", 12: "tmua", 13: "tmuau", 14: "vpm", 15: "vpmu",
    16: "sync", 17: "syncu", 18: "syncb", 32: "tmuc", 33: "tmus",
    34: "tmut", 35: "tmur", 36: "tmui", 37: "tmub",
    38: "tmudref", 39: "tmuhs"}


@dataclass(frozen=True)
class Instruction:
    index: int
    word: int
    kind: str
    signal_index: int = 0
    signals: frozenset[str] = frozenset()
    signal_addr: int | None = None
    signal_magic: bool = False
    add_op: str = ""
    add_waddr: int = 0
    add_magic: bool = False
    add_mux_a: int = 0
    add_mux_b: int = 0
    mul_op: str = ""
    mul_waddr: int = 0
    mul_magic: bool = False
    mul_mux_a: int = 0
    mul_mux_b: int = 0
    raddr_a: int = 0
    raddr_b: int = 0

    @property
    def add_active(self) -> bool:
        return self.add_op != "nop"

    @property
    def mul_active(self) -> bool:
        return self.mul_op != "nop"

    def magic_writes(self) -> tuple[int, ...]:
        out = []
        if self.add_active and self.add_magic:
            out.append(self.add_waddr)
        if self.mul_active and self.mul_magic:
            out.append(self.mul_waddr)
        return tuple(out)


def _add_name(op: int, ma: bool, waddr: int, a: int, b: int) -> str:
    if 0 <= op <= 47:
        return "fadd/faddnf"
    if op in range(53, 56) or op in range(57, 60) or op in range(61, 64):
        return "vfpack"
    fixed = {56: "add", 60: "sub", 64: "fsub", 120: "min",
             121: "max", 122: "umin", 123: "umax", 124: "shl",
             125: "shr", 126: "asr", 127: "ror", 181: "and",
             182: "or", 183: "xor", 184: "vadd", 185: "vsub"}
    if op in fixed:
        return fixed[op]
    if 64 <= op <= 111:
        return "fsub"
    if 128 <= op <= 175:
        return "fmin/fmax"
    if op == 186:
        return ("not", "neg", "flapush", "flbpush", "flpop", "recip",
                "setmsf", "setrevf")[b]
    if op == 187:
        table = {
            (0, 0): "nop", (1, 0): "tidx", (2, 0): "eidx", (3, 0): "lr",
            (4, 0): "vfla", (5, 0): "vflna", (6, 0): "vflb", (7, 0): "vflnb",
            (3, 1): "xcd", (7, 1): "ycd", (0, 2): "msf", (1, 2): "revf",
            (2, 2): "iid", (3, 2): "sampid", (4, 2): "barrierid",
            (5, 2): "tmuwt", (6, 2): "vpmwt", (7, 2): "flafirst",
            (0, 3): "flnafirst"}
        if b == 1 and a in (0, 1, 2):
            return "fxcd"
        if b == 1 and a in (4, 5, 6):
            return "fycd"
        if (a, b) in table:
            return table[(a, b)]
        raise DecodeError(f"undefined opcode-187 mux pair a={a}, b={b}")
    if op == 188:
        names = ("ldvpmv", "ldvpmd", "ldvpmp", "rsqrt", "exp", "log", "sin", "rsqrt2")
        return names[b] + ("_out" if ma and b in (0, 1) else "_in" if b in (0, 1, 2) else "")
    if op == 189:
        return "ldvpmg_out" if ma else "ldvpmg_in"
    if 192 <= op <= 239:
        return "fcmp"
    if op == 245:
        return "ftoin" if b == 3 else "fround/ftrunc"
    if op == 246:
        return "ftouz" if b == 3 else "ffloor/fceil"
    if op == 247:
        return "fdx/fdy"
    if op == 248:
        if waddr not in (0, 1, 2):
            raise DecodeError(f"STVPM has illegal selector {waddr}")
        return ("stvpmv", "stvpmd", "stvpmp")[waddr]
    if op == 252:
        return "clz" if b == 3 else "itof/utof"
    raise DecodeError(f"undefined V3D 4.2 ADD opcode {op}")


def _mul_name(op: int, a: int, b: int) -> str:
    if op == 1: return "add"
    if op == 2: return "sub"
    if op == 3: return "umul24"
    if 4 <= op <= 8: return "vfmul"
    if op == 9: return "smul24"
    if op == 10: return "multop"
    if op == 14 or (op == 15 and b <= 3): return "fmov"
    if op == 15 and a == 0 and b == 4: return "nop"
    if op == 15 and b == 7: return "mov"
    if 16 <= op <= 63: return "fmul"
    raise DecodeError(f"undefined V3D 4.2 MUL opcode/mux {op}/{a}/{b}")


def decode_word(word: int, index: int = 0) -> Instruction:
    if word < 0 or word >= 1 << 64:
        raise DecodeError("instruction is not one unsigned 64-bit word")
    op_mul = (word >> 58) & 0x3f
    sig_idx = (word >> 53) & 0x1f
    if op_mul == 0:
        if (sig_idx & 24) != 16:
            raise DecodeError(f"word {index}: zero MUL opcode is not a branch")
        cond = (word >> 32) & 7
        msfign = (word >> 21) & 3
        if cond == 1 or msfign == 3:
            raise DecodeError(f"word {index}: reserved branch condition/msfign")
        return Instruction(index, word, "branch", sig_idx)
    if sig_idx not in SIGNALS:
        raise DecodeError(f"word {index}: reserved signal index {sig_idx}")
    signals = SIGNALS[sig_idx]
    cond = (word >> 46) & 0x7f
    sig_addr = (cond & 0x3f) if signals & SIGNAL_WRITES else None
    sig_magic = bool(cond & 0x40) if sig_addr is not None else False
    if sig_addr is None and cond == 0x10:
        raise DecodeError(f"word {index}: reserved condition/flag encoding 0x10")
    op_add = (word >> 24) & 0xff
    add_a, add_b = (word >> 12) & 7, (word >> 15) & 7
    mul_a, mul_b = (word >> 18) & 7, (word >> 21) & 7
    wa, wm = (word >> 32) & 0x3f, (word >> 38) & 0x3f
    ma, mm = bool(word & (1 << 44)), bool(word & (1 << 45))
    add_name = _add_name(op_add, ma, wa, add_a, add_b)
    # MA denotes IN/OUT for the LDVPM family, not a magic destination.
    add_magic = ma and not add_name.startswith("ldvpm")
    return Instruction(index, word, "alu", sig_idx, signals, sig_addr,
                       sig_magic, add_name, wa, add_magic, add_a, add_b,
                       _mul_name(op_mul, mul_a, mul_b), wm, mm, mul_a, mul_b,
                       (word >> 6) & 0x3f, word & 0x3f)


def decode_program(data: bytes | bytearray | memoryview | Iterable[int]) -> list[Instruction]:
    if not isinstance(data, (bytes, bytearray, memoryview)):
        return [decode_word(int(w), i) for i, w in enumerate(data)]
    raw = bytes(data)
    if not raw or len(raw) % 8:
        raise DecodeError("program size must be a nonzero whole number of 64-bit words")
    return [decode_word(int.from_bytes(raw[i:i + 8], "little"), i // 8)
            for i in range(0, len(raw), 8)]


@dataclass(frozen=True)
class ProgramContract:
    name: str
    role: str
    uniform_words: int
    requires_vpm_load: bool = True


def _fail(ins: Instruction, text: str) -> None:
    raise VerifyError(f"{text} at instruction {ins.index} ({ins.word:#018x})")


def uniform_consumption(ins: Instruction) -> int:
    if ins.kind != "alu":
        return 1 if ins.kind == "branch" and bool(ins.word & (1 << 14)) else 0
    count = sum(name in ins.signals for name in
                ("ldunif", "ldunifrf", "ldunifa", "ldunifarf", "wrtmuc"))
    count += sum(addr in UNIFORM_MAGIC_WADDRS for addr in ins.magic_writes())
    return count


def verify_program(data: bytes | Sequence[int], contract: ProgramContract) -> list[Instruction]:
    insns = decode_program(data)
    last_branch = -10
    last_thrsw = -10
    last_marker_ip = -10
    last_sfu = -10
    last_marker = False
    thread_end = False
    prior_ldvary = False
    first_tlb = None
    for ins in insns:
        if ins.kind == "branch":
            if ins.index - last_branch < 3:
                _fail(ins, "branch in branch delay slots")
            if ins.index - last_thrsw < 3:
                _fail(ins, "branch in THRSW delay slots")
            last_branch = ins.index
            prior_ldvary = False
            continue
        unit_writes = ins.magic_writes()
        tmu = sum(w in TMU_WADDRS for w in unit_writes)
        sfu = sum(w in SFU_WADDRS for w in unit_writes)
        vpm = sum(w in VPM_WADDRS for w in unit_writes)
        tlb = sum(w in TLB_WADDRS for w in unit_writes)
        tsy = sum(w in TSY_WADDRS for w in unit_writes)
        units = tmu + sfu + vpm + tlb + tsy
        units += int("ldtmu" in ins.signals) + int("ldtlb" in ins.signals) + int("ldtlbu" in ins.signals)
        if units > 1:
            _fail(ins, "more than one TMU/SFU/VPM/TLB/TSY action")
        if prior_ldvary and ("ldunif" in ins.signals or "ldunifa" in ins.signals):
            _fail(ins, "LDUNIF immediately after LDVARY")
        if ins.index - last_sfu < 2 and sfu:
            _fail(ins, "SFU write in the previous SFU shadow")
        if ins.index - last_thrsw < 3:
            if sfu:
                _fail(ins, "SFU write in THRSW delay slots")
            if "ldvary" in ins.signals:
                _fail(ins, "LDVARY in V3D 4.2 THRSW delay slots")
        if "thrsw" in ins.signals:
            if ins.index - last_branch < 3:
                _fail(ins, "THRSW in branch delay slots")
            if last_thrsw == ins.index - 1:
                if last_marker:
                    _fail(ins, "duplicate last-THRSW marker")
                last_marker = True
                last_marker_ip = ins.index
                thread_end = True
            elif ins.index - last_thrsw < 3:
                _fail(ins, "THRSW too close to preceding THRSW")
            else:
                last_thrsw = ins.index
        if thread_end:
            if ins.add_active and not ins.add_magic and not ins.add_op.startswith("stvpm"):
                _fail(ins, "register-file ADD write after THREND")
            if ins.mul_active and not ins.mul_magic:
                _fail(ins, "register-file MUL write after THREND")
            if ins.signal_addr is not None and not ins.signal_magic:
                _fail(ins, "register-file signal write after THREND")
        if sfu:
            last_sfu = ins.index
        if tlb and first_tlb is None:
            first_tlb = ins.index
        prior_ldvary = "ldvary" in ins.signals

    role = contract.role
    sigs = [i.signals for i in insns if i.kind == "alu"]
    consumed = sum(uniform_consumption(i) for i in insns)
    if consumed != contract.uniform_words:
        raise VerifyError(f"{contract.name}: consumes {consumed} uniform words, stream has {contract.uniform_words}")
    if len(insns) < 4 or ["thrsw" in s for s in sigs[-4:]] != [True, False, False, False]:
        raise VerifyError(f"{contract.name}: missing program-end THRSW and three delay slots")
    tlb_writes = [(i.index, w) for i in insns for w in i.magic_writes() if w in TLB_WADDRS]
    if role in ("coordinate", "vertex"):
        if tlb_writes:
            raise VerifyError(f"{contract.name}: vertex-side program writes the tile buffer")
        if contract.requires_vpm_load and not any(i.add_op.startswith("ldvpm") for i in insns):
            raise VerifyError(f"{contract.name}: no VPM attribute load")
        if not any(i.add_op.startswith("stvpm") for i in insns):
            raise VerifyError(f"{contract.name}: no VPM result store")
        if sum(i.add_op == "vpmwt" for i in insns) != 1:
            raise VerifyError(f"{contract.name}: requires exactly one VPMWT")
        loaded = [i.signal_addr for i in insns if "ldunifrf" in i.signals]
        if loaded != list(range(contract.uniform_words)):
            raise VerifyError(f"{contract.name}: uniforms must land once in sequential RF destinations")
        if any(i.add_magic for i in insns if i.add_op.startswith("ldvpm")):
            raise VerifyError(f"{contract.name}: VPM loads require register-file destinations")
        if any(not i.add_op.endswith("_in") for i in insns if i.add_op.startswith("ldvpm")):
            raise VerifyError(f"{contract.name}: vertex input path used an output-side VPM load")
        if any(i.add_magic for i in insns if i.add_op.startswith("stvpm")):
            raise VerifyError(f"{contract.name}: STVPM selector was misread as a magic destination")
    elif role.startswith("fragment"):
        if [w for _, w in tlb_writes] != [8, 7]:
            raise VerifyError(f"{contract.name}: requires ordered TLBU then TLB writes")
        if any(i.add_op != "vfpack" for i in insns
               if any(w in TLB_WADDRS for w in i.magic_writes())):
            raise VerifyError(f"{contract.name}: tile writes must be VFPACK results")
        if not last_marker or first_tlb is None or first_tlb <= last_marker_ip + 2:
            raise VerifyError(f"{contract.name}: TLB writes are not after last-THRSW delay slots")
        ldtmu = [i for i in insns if "ldtmu" in i.signals]
        if role == "fragment:uniform":
            launches = [i for i in insns if 13 in i.magic_writes()]
            if len(launches) != 1 or "thrsw" not in launches[0].signals:
                raise VerifyError(f"{contract.name}: requires one TMUAU launch carrying THRSW")
            if [i.signal_addr for i in insns if "ldunifrf" in i.signals] != [8]:
                raise VerifyError(f"{contract.name}: descriptor address must land in rf8")
            if [i.signal_addr for i in ldtmu] != [0, 1, 2, 3]:
                raise VerifyError(f"{contract.name}: TMU vec4 must return to rf0..rf3")
            if [i.index for i in ldtmu] != list(range(launches[0].index + 3,
                                                       launches[0].index + 7)):
                raise VerifyError(f"{contract.name}: TMU reads require two THRSW delay slots then four results")
        elif role == "fragment:sampled":
            if sum("wrtmuc" in i.signals for i in insns) != 2:
                raise VerifyError(f"{contract.name}: requires texture and sampler WRTMUC loads")
            dests = [w for i in insns for w in i.magic_writes() if w in (33, 34)]
            if dests != [34, 33]:
                raise VerifyError(f"{contract.name}: coordinates must write TMUT before TMUS")
            if [i.signal_addr for i in insns if "ldvary" in i.signals] != [10, 11]:
                raise VerifyError(f"{contract.name}: sample coordinates must land in rf10/rf11")
            if [i.signal_addr for i in ldtmu] != [0, 1, 2, 3]:
                raise VerifyError(f"{contract.name}: sampled TMU result must return to rf0..rf3")
            switches = [i for i in insns if "thrsw" in i.signals]
            request = next((i for i in switches if i.index >
                            max(j.index for j in insns
                                if any(w in (33, 34) for w in j.magic_writes()))), None)
            if request is None or [i.index for i in ldtmu] != list(range(request.index + 3,
                                                                          request.index + 7)):
                raise VerifyError(f"{contract.name}: sample return violates THRSW/TMU latency sequence")
        elif role == "fragment:varying":
            varying = [i.signal_addr for i in insns if "ldvary" in i.signals]
            if varying != [0, 1, 2, 3]:
                raise VerifyError(f"{contract.name}: varying colour requires four LDVARY signals")
        elif role == "fragment:flat":
            if any("ldvary" in i.signals or "ldtmu" in i.signals for i in insns):
                raise VerifyError(f"{contract.name}: flat fragment unexpectedly uses VARY/TMU")
            if [i.signal_addr for i in insns if "ldunifrf" in i.signals] != [0, 1, 2, 3]:
                raise VerifyError(f"{contract.name}: flat RGBA uniforms must land in rf0..rf3")
        else:
            raise VerifyError(f"{contract.name}: unknown fragment contract {role}")
    else:
        raise VerifyError(f"{contract.name}: unknown role {role}")
    return insns


def describe(ins: Instruction) -> str:
    if ins.kind == "branch":
        return f"{ins.index:03d}: {ins.word:016x} branch"
    sig = "+".join(sorted(ins.signals)) or "-"
    aw = ("m:" + WADDR_NAMES.get(ins.add_waddr, str(ins.add_waddr))) if ins.add_magic else f"rf{ins.add_waddr}"
    mw = ("m:" + WADDR_NAMES.get(ins.mul_waddr, str(ins.mul_waddr))) if ins.mul_magic else f"rf{ins.mul_waddr}"
    sd = "" if ins.signal_addr is None else f" -> {'m:' if ins.signal_magic else 'rf'}{ins.signal_addr}"
    return f"{ins.index:03d}: {ins.word:016x} sig={sig}{sd} add={ins.add_op}->{aw} mul={ins.mul_op}->{mw}"

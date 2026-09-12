#!/usr/bin/env python3
"""Small independent A64 oracle for the Raspberry Pi 4 backend.

This intentionally models only the integer/system subset emitted by the first
backend.  It predates the project assembler, and its self-test uses fixed
machine words checked against the Arm A64 instruction descriptions.  The
assembler tests later feed their output into this interpreter.

IT ALSO HOLDS THE ONE COPY OF THE ALIGNMENT RULE.  With the MMU off - which
is how every Pi 4 payload here runs unless it has said otherwise - a wide
data access whose address is not a multiple of its size is fatal on the
part and SILENT, and until 2026-08-28 this model serviced it happily.  See
the long note above `AlignmentFault`, and `align_guard()`, which every gate
that installs its own load/store closures must call.
"""

from __future__ import annotations

import re
from pathlib import Path

from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Tuple

MASK32 = 0xFFFFFFFF
MASK64 = 0xFFFFFFFFFFFFFFFF

# The bottom of the BCM2711 peripheral/MMIO aperture in the low (35-bit)
# view every pi4 payload uses.  RaspberryPi4/Lib/mmu.pi4 maps everything
# from here up as Device even AFTER the MMU is enabled, which is why
# `mmu_on` below relaxes the alignment rule for DRAM and never for this.
DEVICE_FLOOR = 0xFC000000

# DC / IC / TLBI selector quadruples, keyed op1<<12 | CRn<<8 | CRm<<4 | op2.
# See the long note in A64.step() for why these are no-ops here and for the
# SYS bit layout. Kept as a table so the three models can be diffed by eye.
SYS_MAINTENANCE = {
    0x0761: "dc ivac",        # op1=0 CRn=7  CRm=6  op2=1
    0x0762: "dc isw",         # op1=0 CRn=7  CRm=6  op2=2
    0x07A2: "dc csw",         # op1=0 CRn=7  CRm=10 op2=2
    0x07E2: "dc cisw",        # op1=0 CRn=7  CRm=14 op2=2
    0x37A1: "dc cvac",        # op1=3 CRn=7  CRm=10 op2=1
    0x37B1: "dc cvau",        # op1=3 CRn=7  CRm=11 op2=1
    0x37E1: "dc civac",       # op1=3 CRn=7  CRm=14 op2=1
    0x0710: "ic ialluis",     # op1=0 CRn=7  CRm=1  op2=0
    0x0750: "ic iallu",       # op1=0 CRn=7  CRm=5  op2=0
    0x3751: "ic ivau",        # op1=3 CRn=7  CRm=5  op2=1
    0x0830: "tlbi vmalle1is",  # op1=0 CRn=8 CRm=3  op2=0
    0x0870: "tlbi vmalle1",   # op1=0 CRn=8  CRm=7  op2=0
    0x4830: "tlbi alle2is",   # op1=4 CRn=8  CRm=3  op2=0
    0x4870: "tlbi alle2",     # op1=4 CRn=8  CRm=7  op2=0
    0x6830: "tlbi alle3is",   # op1=6 CRn=8  CRm=3  op2=0
    0x6870: "tlbi alle3",     # op1=6 CRn=8  CRm=7  op2=0
}

# AT - address translation, 2026-09-04 (forum 627). Same SYS family and the
# same key, kept in its OWN table because everything in SYS_MAINTENANCE is a
# no-op here and nothing in this one is: AT walks the translation tables and
# answers in PAR_EL1. This interpreter has one flat memory and no walker, so
# it refuses rather than pretending. See A64.step().
SYS_ADDRESS_TRANSLATION = {
    0x0780: "at s1e1r",       # op1=0 CRn=7  CRm=8  op2=0
    0x0781: "at s1e1w",       # op1=0 CRn=7  CRm=8  op2=1
    0x0782: "at s1e0r",       # op1=0 CRn=7  CRm=8  op2=2
    0x0783: "at s1e0w",       # op1=0 CRn=7  CRm=8  op2=3
    0x4780: "at s1e2r",       # op1=4 CRn=7  CRm=8  op2=0
    0x4781: "at s1e2w",       # op1=4 CRn=7  CRm=8  op2=1
    0x4784: "at s12e1r",      # op1=4 CRn=7  CRm=8  op2=4
    0x4785: "at s12e1w",      # op1=4 CRn=7  CRm=8  op2=5
    0x6780: "at s1e3r",       # op1=6 CRn=7  CRm=8  op2=0
    0x6781: "at s1e3w",       # op1=6 CRn=7  CRm=8  op2=1
}

# SVC / HVC / SMC / BRK / HLT - exception generation, 2026-09-04 (forum 611).
#   1101 0100 opc(3) imm16(16) op2(3) LL(2)
# op2 is 000 in all five, so masking with 0xFFE0001F leaves the base word and
# the immediate sits at bits 20:5. Each raises an exception to a level this
# model does not have, so each is a named refusal; see A64.step().
EXCEPTION_GENERATION = {
    0xD4000001: ("svc", "a supervisor handler at EL1"),
    0xD4000002: ("hvc", "a hypervisor handler at EL2"),
    0xD4000003: ("smc", "a secure-monitor handler at EL3"),
    0xD4200000: ("brk", "an attached debugger"),
    0xD4400000: ("hlt", "an attached debug host"),
}


# The ELR and SPSR a given exception level's ERET reads, keyed by the
# level it returns FROM and valued by the WRITE base of each register -
# the same key the opt-in system-register store uses. The encodings come
# from RaspberryPi4/A64Assembler.pbi, which cites
# RaspberryPi4/Reference/llvm19.1.0_AArch64SystemOperands.td for the EL3
# pair and v6.12_arm64_sysreg.h for the other two.
#
# EL0 is absent on purpose: an exception return from EL0 is not defined,
# and a table entry answering it would be an invented destination.
ERET_BANKS = {
    3: (0xD51E4020, 0xD51E4000),   # elr_el3, spsr_el3
    2: (0xD51C4020, 0xD51C4000),   # elr_el2, spsr_el2
    1: (0xD5184020, 0xD5184000),   # elr_el1, spsr_el1
}


# MRS Xt, CNTPCT_EL0 - op0 3, op1 3, CRn 14, CRm 0, op2 1, with Rt in
# bits 4:0.  See the note on `cntpct` for why this one is answered and
# CNTFRQ_EL0 (the same quadruple with op2 0) is not.
CNTPCT_EL0_READ = 0xD53BE020


_CRC_TABLES: dict[int, list[int]] = {}


def _crc_table(poly: int) -> list[int]:
    """The 256-entry table for a REFLECTED polynomial, built once.

    The architecture states CRC32's polynomial as 0x04C11DB7 and then
    reverses the bit order of both operands and of the result around the
    calculation. Reflecting the POLYNOMIAL instead - 0xEDB88320, and
    0x82F63B78 for CRC32C - is the standard identity and gives the same
    answer for every input, with no bit reversals at all.
    """
    if poly not in _CRC_TABLES:
        table = []
        for byte in range(256):
            crc = byte
            for _ in range(8):
                crc = (crc >> 1) ^ (poly if crc & 1 else 0)
            table.append(crc)
        _CRC_TABLES[poly] = table
    return _CRC_TABLES[poly]


def sx(value: int, bits: int) -> int:
    sign = 1 << (bits - 1)
    value &= (1 << bits) - 1
    return value - (1 << bits) if value & sign else value


def ror(value: int, amount: int, bits: int) -> int:
    amount %= bits
    mask = (1 << bits) - 1
    return ((value >> amount) | (value << (bits - amount))) & mask


# ======================================================================
#  THE ALIGNMENT RULE - THE ONE COPY OF IT
# ======================================================================
#
#  WHY THIS IS IN THE INTERPRETER AND NOT IN NINETEEN GATES
#  --------------------------------------------------------
#  On 2026-08-27 `a64_sdio_check.py --scan` PASSED, printing five correct
#  SSIDs, on the exact cyw43.pi4 source that could not survive ten
#  milliseconds on the part.  The payload built the iovar
#  "bsscfg:event_msgs" - seventeen characters and a NUL - and then wrote a
#  u32 at offset 18.  That lowered to one `str w11, [x12]` with x12 ending
#  in 2, and the board stopped mid-line and never came back.
#
#  The gate agreed with the bug because this interpreter's memory is a
#  Python dict of bytes, which does not care where a word lands.  That is
#  not a misread datasheet - it is a MODEL MORE FORGIVING THAN THE PART,
#  and no amount of careful reading of vendor sources can catch it.
#
#  WHY THE ACCESS IS FATAL, AND WHY THE OBVIOUS REASONING IS WRONG
#  ---------------------------------------------------------------
#    * SCTLR_EL2.A - strict alignment checking - is CLEAR on this board.
#      Measured, not assumed: Datasheets/pi4/armstub8.S:136-141 writes
#      $30C50830 and every set bit in it is RES1, and `pi4MmuState` read
#      exactly that back off the board on 2026-08-26.  So the tempting
#      conclusion is "unaligned is fine here".
#    * THAT MISSES THE OTHER CLEAR BIT.  SCTLR_EL2.M is clear too.  With
#      the MMU off, ARMv8-A makes EVERY data access Device-nGnRnE, and an
#      unaligned access to Device memory is an Alignment fault REGARDLESS
#      of SCTLR.A.  `.A` governs Normal memory; with M clear nothing is
#      Normal, so `.A` has nothing to say about it.
#    * There is NO EXCEPTION VECTOR installed in most payloads - VBAR is
#      whatever the firmware stub left.  So the fault is not a message, it
#      is a runaway: the board prints a header and then nothing, for ever,
#      and needs a power cycle unless the deadman was armed.
#
#  Vault: [[Unaligned access with the MMU off 2026-08-27]].
#
#  TWO BEHAVIOURS, ONE RULE - see `on_align_fault` below
#  -----------------------------------------------------
#  Two gates grew private versions of this before it was shared, and they
#  must do DIFFERENT things, so the mechanism has to express both:
#
#    * a64_sdio_check.py REFUSES: SystemExit naming the procedure and
#      source line.  Right for a gate whose library must never make such
#      an access.  That is what happens here when `on_align_fault` is
#      None and the caller lets AlignmentFault escape.
#    * a64_fault_check.py DELIVERS a Data Abort into the vector table,
#      because the library it tests is the thing that CATCHES faults.  A
#      gate that merely refused could not test a fault handler at all.
#      That gate sets `on_align_fault` to a callback that raises its own
#      Abort carrying the manual's EC and DFSC.
#
#  Instruction fetch is deliberately NOT covered.  With the MMU off,
#  instruction fetches are Normal Non-Cacheable rather than Device, and
#  the PC is 4-aligned by construction anyway; a misaligned PC is a PC
#  alignment fault, a different exception with a different EC, and
#  pretending it is a data abort would name the wrong thing.
#
#  REJECTED ALTERNATIVES, and why
#  -------------------------------
#    * Nine lines copied into each gate (what a64_v3d_check.py did, and
#      what [[Open bugs]] offered as an option).  It works, and it is how
#      the first three were done - but the rule then has nineteen homes,
#      the message text drifts, and the next gate written starts life
#      without it.  The V3D copy already worded it differently from the
#      SDIO copy.
#    * Overriding A64.load/store in a mixin the gates inherit.  Every gate
#      installs `cpu.load = <closure>` because it must service MMIO, so a
#      mixin is bypassed by exactly the code path that needs guarding.
#      A guard the gate CALLS survives being wrapped; a guard it inherits
#      does not.
#    * Making it opt-in with a flag defaulting to off.  That is the
#      arrangement that already failed: eighteen of nineteen gates would
#      simply never have turned it on.  Default ON, opt OUT with a reason.
#
#  HOW THE TWO PRIVATE COPIES ADOPT THIS, WHEN THEIR OWNERS ARE FREE
#  ------------------------------------------------------------------
#  Neither was touched on 2026-08-28 - both were held by other workers -
#  and both still pass unchanged, because this mechanism only ADDS.  When
#  they are free:
#
#    a64_sdio_check.py - delete its `align_check()` closure (the ~14 lines
#      at the top of run()), its `_symbols()` and its `_where()`, call
#      `attach_symbols(cpu, img, LOAD)` after the image is loaded, and
#      replace the two `align_check(addr, size, ...)` calls at the head of
#      its load/store closures with `cpu.align_guard(addr, size, ...)`.
#      Its message becomes the shared one, which says the same things in
#      the same order.  ONE BEHAVIOUR CHANGES AND IT IS AN IMPROVEMENT:
#      its copy reports `cpu.pc`, which step() has already advanced, so it
#      names the instruction AFTER the faulting one.  `this_instr` fixes
#      that, and the offset in its recorded example moves from
#      cyw43seteventmask+332 to +328.  Anyone re-verifying that vault
#      entry should expect the four bytes.
#
#    a64_fault_check.py - the gate that must DELIVER rather than refuse.
#      Delete `Machine.align_guard`, and in __init__ set
#
#          self.cpu.on_align_fault = self._to_abort
#
#      where `_to_abort(f)` raises its existing Abort built from the
#      manual's own tables:
#
#          ec  = self.ec_tab["Exception_DataAbort_SAME"]
#          iss = self.dfsc["Fault_Alignment"] | ((1 << 6) if f.write else 0)
#          raise Abort(ec, iss, f.addr)
#
#      Its load()/store() then call `self.cpu.align_guard(...)` in place
#      of `self.align_guard(...)`, and its `self.fetching` flag is
#      replaced by `cpu.fetch()`.  Mutation A1 - "the alignment rule
#      deleted from the GATE ITSELF" - keeps working: it monkeypatches
#      `Machine.align_guard` today and would monkeypatch
#      `A64.align_guard` (or clear `cpu.align_check`) instead.  That
#      mutation is the proof the rule is load-bearing there, so it must
#      survive the move, not be dropped with the code it patched.
#
#  WHAT THIS RULE STILL CANNOT CATCH - say it, or a pass means nothing
#  --------------------------------------------------------------------
#    * Accesses this interpreter does not model.  The only load/store
#      family decoded here is the unsigned-immediate LDR/STR (the
#      `0x39000000` branch of step()).  LDUR/LDP/STP, the register-offset
#      forms and anything SIMD would raise "unsupported A64 word" long
#      before reaching an alignment question - which is loud, so nothing
#      hides, but it also means this rule has never been exercised
#      against them.  The day the backend emits LDP, that branch and this
#      guard have to arrive together.
#    * A gate that installs `cpu.load`/`cpu.store` closures and forgets to
#      call `align_guard`.  Nothing here can detect that from the inside;
#      it is caught by injecting a misaligned access and watching the gate
#      go red, which is why that test exists for every gate.
#    * Whether an address is Normal or Device after the MMU is enabled.
#      This model does no translation and never walks a table.  See
#      `mmu_enabled()`.
#    * Everything else about Device memory: access size restrictions,
#      ordering, gathering, and read side effects.  A 4-byte access to a
#      register that only accepts 4-byte accesses is checked by a couple
#      of gates by hand (a64_xhci_check.py refuses any non-32-bit xHCI
#      register access); that is a different rule and it is not here.
#    * Stack alignment.  SP must be 16-byte aligned at every use as a
#      base register, and nothing checks it.


class AlignmentFault(Exception):
    """A wide data access whose address is not a multiple of its size.

    Carries enough to name the culprit rather than print a hex number.
    `pc` is the address of the instruction that made the access, which is
    what a person needs; `addr` is the address it touched.
    """

    def __init__(self, addr: int, size: int, write: bool, pc: int,
                 locate: Optional[Callable[[int], str]] = None) -> None:
        self.addr = addr
        self.size = size
        self.write = write
        self.pc = pc
        self.locate = locate
        super().__init__(self.message())

    def message(self, prefix: str = "ALIGNMENT FAULT") -> str:
        where = self.locate(self.pc) if self.locate else "$%08X" % self.pc
        return (
            "%s: a %d-byte %s at $%08X, which is %d past a %d-byte "
            "boundary.\n"
            "  at %s\n"
            "  With the MMU off every data access is Device-nGnRnE and an "
            "unaligned one is an Alignment fault whatever SCTLR.A says. No "
            "vector is installed, so on the board this is not an error "
            "message - it is silence. Build the value out of PokeB/PeekB, "
            "or move the field to a %d-byte boundary."
            % (prefix, self.size, "write" if self.write else "read",
               self.addr, self.addr % self.size, self.size, where, self.size))


# ----------------------------------------------------------------------
#  NAMING THE CULPRIT.  "alignment fault at $00484EDA" sends someone
#  hunting; "cyw43seteventmask+332, cyw43.pi4 line 4762" ends the search.
#
#  The compiler writes a `.dbg` beside every image: one line per symbol,
#  as `kind|offset|name|source file and line`, kind 1 being a procedure
#  and the offset an IMAGE offset, so the absolute address is LOAD +
#  offset.
#
#  READ THE `.dbg`, NOT THE `.sym`, FOR THIS.  A64Assembler.pbi:1994-1997
#  exports a BSS symbol as its ABSOLUTE address and a code symbol as its
#  address MINUS the load base:
#
#      If A64Symbols()\IsBss
#        exportSymbols()=A64Symbols()\Address
#      Else
#        exportSymbols()=A64Symbols()\Address-A64LoadBase
#
#  So `LOAD + sym[name]` is right for a procedure and wrong for a Global
#  by exactly one load base - and getting it wrong is NOT an error.  The
#  read lands in unwritten memory and this interpreter's dict returns
#  ZERO for every unwritten byte, so a gate that only asked "did it
#  fault" would go green on a column of zeroes.  The `.dbg` has no such
#  ambiguity: every kind-1 line is code, every offset is image-relative,
#  and there is one rule to get wrong instead of two.
# ----------------------------------------------------------------------

class DbgSymbols:
    """Procedure names and source lines, read from `<image>.dbg`."""

    def __init__(self, entries: List[Tuple[int, str, str]]) -> None:
        self.entries = sorted(entries)

    @classmethod
    def read(cls, image: "Path | str", load_base: int) -> "DbgSymbols":
        dbg = Path(str(image) + ".dbg")
        found: List[Tuple[int, str, str]] = []
        if dbg.exists():
            text = dbg.read_text(encoding="utf-8", errors="replace")
            for line in text.splitlines():
                f = line.split("|")
                if len(f) >= 4 and f[0] == "1" and f[1].isdigit():
                    found.append((load_base + int(f[1]), f[2], f[3]))
        return cls(found)

    def where(self, pc: int) -> str:
        """The nearest procedure at or before pc, with its source line.

        READ THE OUTPUT CORRECTLY: "buildiovar+48, align_witness.pi4 line
        5" means the procedure `buildiovar` STARTS at line 5 and the fault
        is 48 bytes into it.  The `.dbg` carries one entry per procedure,
        not per statement, so the line number is the declaration's - the
        `+offset` is what pins the statement, against the `.asm` the same
        build writes.  Reading the line number as the faulting line sends
        someone to the wrong place in a long procedure, which is the whole
        thing this is here to prevent.
        """
        best = None
        for addr, name, src in self.entries:
            if addr <= pc:
                best = (addr, name, src)
            else:
                break
        if best is None:
            return "$%08X (no symbol covers it)" % pc
        return "$%08X - %s+%d, %s" % (pc, best[1], pc - best[0], best[2])

    __call__ = where


def attach_symbols(cpu: "A64", image: "Path | str", load_base: int) -> DbgSymbols:
    """Give `cpu` the ability to name the procedure a fault came from.

    A missing `.dbg` is not an error - the fault still reports its hex PC
    - because some gates run hand-assembled words with no image at all.
    """
    syms = DbgSymbols.read(image, load_base)
    cpu.locate = syms.where
    return syms


@dataclass
class A64:
    x: List[int] = field(default_factory=lambda: [0] * 31)
    sp: int = 0
    pc: int = 0
    n: int = 0
    z: int = 0
    c: int = 0
    # THE OVERFLOW FLAG IS `vflag`, NOT `v` - forum 650.
    # It used to be `v`, and when the SIMD register file arrived it took
    # the same name. In a dataclass the second declaration simply wins,
    # so the flag's default vanished and every flag-setting instruction
    # - adds, subs, cmp, cmn, which is every loop in every program -
    # REPLACED ALL 32 VECTOR REGISTERS with the integer 0 or 1. Reading
    # one afterwards raised, so nothing was silently miscomputed; what
    # was lost is the ability to point this model at real code at all.
    # Over ten thousand SIMD assertions missed it because not one
    # fixture set a flag - they build operands with moves and stores.
    vflag: int = 0
    memory: Dict[int, int] = field(default_factory=dict)
    halted: bool = False

    # The SIMD&FP register file, added 2026-09-04 with Advanced SIMD.
    # ONE 128-BIT PYTHON INTEGER PER REGISTER, where the native model has
    # to carry two doublewords - a deliberate difference, so the two
    # implementations cannot make the same mistake about the upper half.
    v: List[int] = field(default_factory=lambda: [0] * 32)

    # --- the alignment rule; see the long note above AlignmentFault ---
    #
    # DEFAULT ON.  A payload that has NOT enabled the MMU is the normal
    # case on this target and it is the strict one, so the strict answer
    # is what a gate gets without asking.  A gate that must opt out sets
    # this False and says why in a comment - "it was inconvenient" is not
    # a why.
    align_check: bool = True

    # Set True by a gate whose payload has ACTUALLY enabled the MMU with
    # DRAM mapped Normal.  See `mmu_enabled()` for what this can and
    # cannot be trusted to know.
    mmu_on: bool = False

    # Below this, `mmu_on` relaxes the rule.  At or above it, nothing
    # relaxes it: mmu.pi4 maps the peripheral aperture Device in both
    # regimes, so an unaligned wide MMIO access is fatal either way.
    device_floor: int = DEVICE_FLOOR

    # pc -> "$00417 5F8 - name+offset, file line N".  Set by
    # attach_symbols(); None means faults report a bare hex PC.
    locate: Optional[Callable[[int], str]] = None

    # None  -> AlignmentFault propagates, and a gate that lets it escape
    #          gets the "refuse, loudly, and name it" behaviour.
    # set   -> called with the AlignmentFault instead.  A gate that models
    #          exception delivery raises its own Abort from here.
    on_align_fault: Optional[Callable[["AlignmentFault"], None]] = None

    # True only while step() is reading the instruction word.  Instruction
    # fetch is Normal Non-Cacheable with the MMU off, not Device, so the
    # data-abort rule does not apply to it.
    fetching: bool = False

    # The address of the instruction currently executing.  step() sets it
    # before self.pc is advanced, so a fault names the access, not the
    # word after it.
    this_instr: int = 0

    # ------------------------------------------------------------------
    #  SYSTEM REGISTERS AND THE EXCEPTION LEVEL - added 2026-09-07,
    #  OPT-IN, AND OFF BY DEFAULT
    # ------------------------------------------------------------------
    #  This model decoded no MRS and no MSR at all: every gate that needed
    #  one shimmed it around step(), and a word nobody shimmed reached the
    #  "unsupported A64 word" refusal.  That was the right contract while
    #  the only registers anybody read were CurrentEL, CNTFRQ_EL0 and
    #  CNTPCT_EL0 - three read-only values a gate can answer in four lines
    #  (see tools/a64/a64_anvil_check.py's answer_sysregs).
    #
    #  The EL3 work needs more than an answer.  RaspberryPi4/Board/
    #  armstub8.asm exists to WRITE eleven system registers and then not
    #  eret, and the only useful question to ask of it at a desk is "which
    #  registers did it write, with what, and at what level did it leave
    #  the machine".  A shim that answers reads cannot record writes, and
    #  three gates growing three private copies of a register file is how
    #  three models come to disagree.
    #
    #  Most registers remain a store, not a peripheral/MMU model.
    #  Writing SCTLR_ELx.M does not turn on translation; writing SCR_EL3.NS
    #  does not create a second world. The later explicit take_irq/ERET
    #  subset does honor VBAR, ELR/SPSR, SP banks, NZCV and DAIF, with
    #  interrupt routing supplied by its caller. Other register values
    #  can be read back and judged without inventing consequences. That would be
    #  a wrong answer where an absent one is honest - and `mmu_enabled()`
    #  above already says at length why this model must not pretend to
    #  translate.
    #
    #  OFF BY DEFAULT so that every gate written before today keeps the
    #  behaviour it was written against: an un-shimmed MRS is still a loud
    #  refusal, not a silent zero.  A gate opts in with
    #  enable_system_registers(), which is also the only way to get an
    #  exception level that is anything but the 2 the firmware hands over.
    system_registers: Optional[Dict[int, int]] = None

    # The level MRS CurrentEL reports and the level an eret returns FROM.
    # 2 unless a gate says otherwise, because that is where the stock
    # armstub and U-Boot both hand over.
    current_el: int = 2
    pstate_sp: int = 1
    stack_banks: Dict[int, int] = field(default_factory=dict)

    # Every ERET this run executed, as (from_el, to_el, target_pc).  The
    # stub gate's central claim is a NEGATIVE one - that our stub never
    # erets - and a negative claim needs a record to check, not the
    # absence of a symptom.
    erets: List[Tuple[int, int, int]] = field(default_factory=list)

    # ------------------------------------------------------------------
    #  THE GENERIC TIMER'S COUNT - CNTPCT_EL0 - added 2026-09-11
    # ------------------------------------------------------------------
    #  MODELLED HERE, ALWAYS, AND NOT IN THE STORE ABOVE.  Nothing writes
    #  CNTPCT_EL0, so a store that answers it with whatever was last
    #  written answers zero forever, and a counter that does not move is
    #  a WRONG answer rather than an absent one: a program that waits for
    #  it never finishes, and a program that timestamps with it records
    #  the same instant for every event.  The architecture defines the
    #  BEHAVIOUR of this register completely - a 64-bit count that only
    #  ever increases - and says nothing about its value, so a model can
    #  honour it in full without inventing anything.
    #
    #  It advances once per EXECUTED INSTRUCTION rather than once per
    #  read, so that work done between two reads shows as elapsed time
    #  and a spin that only reads still terminates.  THE RATE IS A MODEL
    #  CHOICE AND MEANS NOTHING IN REAL TIME; `cntpct_per_instruction`
    #  exists so that a gate measuring a deadline can say what it is
    #  measuring in rather than reaching around step().
    #
    #  CNTFRQ_EL0 IS DELIBERATELY NOT HERE, and the asymmetry is the
    #  point.  Its value is board data programmed by firmware - 54 MHz on
    #  the Pi 4, 19.2 MHz on the UNO Q - and it is arithmetic a program
    #  DIVIDES BY, so a baked-in default would silently hand one board's
    #  frequency to another board's image and call the resulting duration
    #  a result.  There is a gate whose whole job is to catch 54 MHz
    #  baked in somewhere.  A gate that reads CNTFRQ_EL0 is doing time
    #  arithmetic and must therefore declare its frequency; a gate that
    #  only timestamps needs nothing, which is why one is answered here
    #  and the other is still refused by name at the foot of step().
    cntpct: int = 0
    cntpct_per_instruction: int = 1

    # ------------------------------------------------------------------
    #  THE LOCAL EXCLUSIVE MONITOR - added 2026-08-28 with the atomics
    # ------------------------------------------------------------------
    #  WHAT THIS IS FOR, AND WHAT IT HONESTLY CANNOT BE FOR.
    #
    #  This interpreter is SINGLE-THREADED.  It cannot model two cores
    #  racing for a lock, which is the entire reason a lock exists, so a
    #  gate that reports "the spinlock works" on the strength of running
    #  it here would be reporting that nothing contended it.  That is
    #  worse than no gate, and it is not what this models.
    #
    #  What it DOES model is the exclusive monitor's STATE MACHINE, which
    #  is single-PE logic and is where the encodable mistakes live:
    #
    #    * a stxr with no preceding ldxr must fail
    #    * a stxr to a different address than the ldxr must fail
    #    * an ordinary store between the two must clear the reservation
    #    * a stxr clears the reservation whether it passed or failed,
    #      so two stxr in a row cannot both succeed
    #    * clrex clears it
    #
    #  Every one of those is checkable without a second thread, and every
    #  one of them is a real way to write a broken primitive.
    #
    #  THE CLEAR-ON-STORE-EXCLUSIVE RULE IS NOT AN INVENTION.  The
    #  architecture's own pseudocode for AArch64_ExclusiveMonitorsPass
    #  reads the monitor into `passed` and then calls
    #  ClearExclusiveLocal unconditionally, before it has even looked at
    #  the result - Datasheets/arm-a64-instruction-set.txt:481582.  So
    #  the failure of a second stxr is architectural, not incidental.
    #  Exception return clears it too (:481519), which this model has no
    #  exceptions to exercise but which is why clrex exists at all.
    #
    #  THE GRANULE IS MODELLED AS THE ACCESSED BYTES, WHICH IS THE
    #  FORGIVING END, AND THAT IS A DELIBERATE, STATED LIMIT.  Real
    #  hardware reserves an IMPLEMENTATION DEFINED block (the ARM ARM
    #  permits 4 to 2048 bytes; a Cortex-A72 uses its cache line), so on
    #  the part an unrelated store NEAR the lock word also clears the
    #  reservation.  Widening the model would only ever make stxr fail
    #  MORE OFTEN, and a correct caller retries, so a narrow granule
    #  cannot hide a correctness bug in the program under test - it can
    #  only hide a LIVELOCK between two locks sharing one granule.  This
    #  model cannot see livelock anyway, because livelock needs two
    #  cores.  Widening it here would therefore buy nothing and would
    #  make every existing gate's ordinary stores start clobbering
    #  reservations they are nowhere near.  The limit is real; it is
    #  written down here rather than discovered later.
    excl_valid: bool = False
    excl_addr: int = 0
    excl_size: int = 0

    # A gate's seam for the one thing this model has no other way to
    # say: "another core wrote the lock word".  There is no second core
    # here, so a gate that wants to test the losing side of a race calls
    # excl_foreign_store() rather than pretending raw_store() did it.
    # Counted, so a gate can assert it actually exercised the path.
    excl_foreign_stores: int = 0

    # ------------------------------------------------------------------
    #  THE BOARD, AS MEASURED 2026-08-28 - opt in to reproduce it
    # ------------------------------------------------------------------
    #  Set True and a store-exclusive obeys the monitor for the STORE
    #  and reports failure anyway.  That is not a hypothetical failure
    #  mode invented to make a gate look thorough; it is what a Pi 4
    #  (MIDR_EL1 $410FD083) does at EL2 with the MMU off, printed by
    #  RaspberryPi4/Examples/Diagnostics/pi4Atomics.pi4:
    #
    #      ldxr / stxr  -> status 1, and the memory WAS written
    #      clrex / stxr -> status 1, and the memory was NOT written
    #
    #  With the MMU off every access is Device, Non-shareable, and the
    #  architecture does not guarantee exclusives outside Normal memory.
    #
    #  WHY IT IS WORTH MODELLING RATHER THAN JUST WRITING DOWN.  This is
    #  the single most dangerous thing a retry loop can meet: the loop
    #  sees failure, retries, and every retry PERFORMS THE OPERATION
    #  AGAIN.  A bounded AtomicAdd of 1 moves the counter by 1024 and
    #  then returns a refusal.  A model that cannot produce that cannot
    #  be used to prove any primitive is safe against it, and "safe
    #  against it" is the only reason RaspberryPi4/Lib/atomic.pi4 has an
    #  AtomicSelfTest at all.
    #
    #  DEFAULT FALSE, deliberately.  The default model is the
    #  architecture, not one board's deviation from it - a gate that got
    #  this behaviour without asking would be reporting a memory-regime
    #  problem as an assembler problem.
    excl_status_always_fails: bool = False

    def excl_mark(self, addr: int, size: int) -> None:
        """A load-exclusive takes a reservation.  A second one replaces it."""
        self.excl_valid = True
        self.excl_addr = addr
        self.excl_size = size

    def excl_clear(self) -> None:
        self.excl_valid = False
        self.excl_addr = 0
        self.excl_size = 0

    def excl_overlaps(self, addr: int, size: int) -> bool:
        if not self.excl_valid:
            return False
        return addr < self.excl_addr + self.excl_size and self.excl_addr < addr + size

    def excl_pass(self, addr: int, size: int) -> bool:
        """Would a store-exclusive to (addr, size) succeed?  ALWAYS clears.

        The unconditional clear is the architecture's, not a convenience -
        see :481582 in the note above.  Returning the answer and clearing
        in one call is what makes it impossible for a caller here to
        check the monitor and forget to clear it.
        """
        passed = self.excl_valid and self.excl_addr == addr and self.excl_size == size
        self.excl_clear()
        return passed

    def excl_foreign_store(self, addr: int, value: int, size: int) -> None:
        """Model another PE writing memory: the write lands, the local
        reservation dies if it covered those bytes.

        This is the ONLY honest way to inject the other side of a race
        into a single-threaded model, and naming it this way keeps a gate
        from quietly using raw_store() and believing it proved something
        about concurrency.  It proves one thing: that the program under
        test retries rather than losing an update.
        """
        if self.excl_overlaps(addr, size):
            self.excl_clear()
        self.excl_foreign_stores += 1
        self.raw_store(addr, value, size)

    def align_guard(self, addr: int, size: int, write: bool,
                    pc: Optional[int] = None) -> None:
        """Refuse a wide access the silicon would refuse.

        Call this FIRST from any load/store closure a gate installs over
        `cpu.load` / `cpu.store`.  A gate that installs a closure and
        forgets this line is back to modelling a machine more permissive
        than the part.
        """
        if self.fetching or not self.align_check:
            return
        if size <= 1 or (addr % size) == 0:
            return
        if self.mmu_on and addr < self.device_floor:
            # Normal memory: unaligned wide accesses are architecturally
            # permitted while SCTLR.A is clear, and it is clear here.
            return
        fault = AlignmentFault(addr, size, write,
                               self.this_instr if pc is None else pc,
                               self.locate)
        if self.on_align_fault is not None:
            self.on_align_fault(fault)
            return
        raise fault

    def mmu_enabled(self, on: bool) -> None:
        """Tell the model the payload has turned the MMU on (or off).

        WHAT THIS CANNOT KNOW, AND WHY IT IS THE GATE'S JOB TO SAY:

        This interpreter does NO ADDRESS TRANSLATION - it has one flat
        byte-addressed memory, no TLB, and it does not decode MRS or MSR
        at all (every gate that needs them shims them itself).  So it
        cannot observe SCTLR_ELx.M being set, and even if it could, whether
        a given address is Normal or Device is decided by the page tables,
        which it never walks.  It could not tell a correct table from a
        table of zeroes - a64_mmu_check.py's docstring has said so since
        the day that gate was written.

        Since it cannot know, THE SAFER DEFAULT IS THE STRICT ONE and the
        gate must assert the relaxation explicitly.  Getting this wrong in
        the strict direction fails correct code - loudly, with a file and
        a line, and a person fixes the gate in a minute.  Getting it wrong
        in the lenient direction is what cost a whole session: a green
        gate and a board that stops printing for ever.  The two errors are
        not the same size.

        Even after this, the rule stays on at and above `device_floor`,
        because mmu.pi4 maps that aperture MMU_ATTR_DEVICE in both
        regimes.  If DRAM is ever mapped Device too, this relaxation
        becomes wrong and must be deleted, not adjusted - it is keyed on
        "DRAM is Normal", which is what #MMU_DRAM_ATTR asserts today
        (a64_mmu_check.py refuses anything that is neither Normal NC nor
        Normal WB).
        """
        self.mmu_on = bool(on)

    def fetch(self, addr: int) -> int:
        """Read an instruction word, through whatever `load` is installed.

        Instruction fetch is NOT subject to the data alignment rule: with
        the MMU off, fetches are Normal Non-Cacheable rather than Device.
        A misaligned PC is a PC Alignment fault - a different exception
        with a different EC - and calling it a data abort would name the
        wrong thing.

        Gates with their own step() wrapper must pre-fetch through THIS
        rather than calling their load closure directly, or the fetch is
        counted as a data access.  It still goes through the closure, so
        a gate that decodes MMIO or counts traffic keeps doing so.
        """
        self.fetching = True
        try:
            return self.load(addr, 4)
        finally:
            self.fetching = False

    def raw_load(self, addr: int, size: int) -> int:
        """Read memory as an OBSERVER: no alignment rule, no MMIO.

        A gate reading a result out of the model afterwards is not the
        program under test and must not be able to raise the program's
        faults.  a64_fault_check.py needs exactly this to read the saved
        register block back.
        """
        return sum(self.memory.get(addr + i, 0) << (8 * i) for i in range(size))

    def raw_store(self, addr: int, value: int, size: int) -> None:
        """Write memory as an observer - image loading, fixtures, DMA."""
        for i in range(size):
            self.memory[addr + i] = (value >> (8 * i)) & 0xFF

    def reg(self, n: int, sf: int, sp_ok: bool = False) -> int:
        if n == 31:
            value = self.sp if sp_ok else 0
        else:
            value = self.x[n]
        return value & (MASK64 if sf else MASK32)

    def put(self, n: int, value: int, sf: int, sp_ok: bool = False) -> None:
        value &= MASK64 if sf else MASK32
        if n == 31:
            if sp_ok:
                self.sp = value
        else:
            # A write to Wn zero-extends into Xn.
            self.x[n] = value

    def load(self, addr: int, size: int) -> int:
        self.align_guard(addr, size, False)
        return sum(self.memory.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(self, addr: int, value: int, size: int) -> None:
        self.align_guard(addr, size, True)
        # A plain store by this PE to the reserved bytes kills the
        # reservation.  Added 2026-08-28; see the exclusive-monitor note
        # above excl_mark().  It is one line HERE rather than at each
        # store site on purpose - a reservation that survives an
        # intervening store is the bug this is meant to catch, and a
        # store site that forgot to call it would reintroduce exactly
        # that bug in the model.
        if self.excl_overlaps(addr, size):
            self.excl_clear()
        for i in range(size):
            self.memory[addr + i] = (value >> (8 * i)) & 0xFF

    def flags_add(self, a: int, b: int, result: int, bits: int) -> None:
        mask = (1 << bits) - 1
        sign = 1 << (bits - 1)
        rr = result & mask
        self.n = int(bool(rr & sign))
        self.z = int(rr == 0)
        self.c = int(a + b > mask)
        self.vflag = int(bool((~(a ^ b) & (a ^ rr) & sign)))

    def flags_sub(self, a: int, b: int, result: int, bits: int) -> None:
        mask = (1 << bits) - 1
        sign = 1 << (bits - 1)
        rr = result & mask
        self.n = int(bool(rr & sign))
        self.z = int(rr == 0)
        self.c = int((a & mask) >= (b & mask))
        self.vflag = int(bool(((a ^ b) & (a ^ rr) & sign)))

    def cond(self, code: int) -> bool:
        table = {
            0x0: self.z == 1, 0x1: self.z == 0,
            0x2: self.c == 1, 0x3: self.c == 0,
            0x4: self.n == 1, 0x5: self.n == 0,
            0x6: self.vflag == 1, 0x7: self.vflag == 0,
            0x8: self.c == 1 and self.z == 0,
            0x9: self.c == 0 or self.z == 1,
            0xA: self.n == self.vflag, 0xB: self.n != self.vflag,
            0xC: self.z == 0 and self.n == self.vflag,
            0xD: self.z == 1 or self.n != self.vflag,
            0xE: True,
        }
        return table.get(code, False)

    # ------------------------------------------------------------------
    #  The system-register store's entry points.  See the field above.
    # ------------------------------------------------------------------
    #  The encodings are the ones RaspberryPi4/A64Assembler.pbi emits, and
    #  the rule that produces them is stated there:
    #     base = 0xD5100000 | (op0-2)<<19 | op1<<16 | CRn<<12 | CRm<<8
    #            | op2<<5,  with 0x00200000 added for a read.
    #  A register is keyed here by its WRITE base, so `msr x, R` and
    #  `mrs R, x` reach the same slot.
    SYSREG_WRITE_MASK = 0xFFFFFFE0
    SYSREG_READ_BIT = 0x00200000
    CURRENTEL_WRITE_BASE = 0xD5184240

    def enable_system_registers(self, el: int = 2,
                                preset: Optional[Dict[int, int]] = None) -> None:
        """Turn on the register store, at exception level `el`.

        `preset` seeds registers the firmware or a previous stage would
        have left set - keyed by WRITE base, the same key a gate reads
        back with.  A gate that seeds nothing gets zero for every
        register it has not written, which is a MODEL CHOICE and not a
        claim about the part: the architecture leaves most of these
        UNKNOWN at reset.  Do not write a gate whose pass depends on an
        unwritten register reading zero.
        """
        if el not in (0, 1, 2, 3):
            raise ValueError("exception level must be 0, 1, 2 or 3, not %r" % el)
        self.system_registers = dict(preset or {})
        self.current_el = el
        self.pstate_sp = 0 if el == 0 else 1
        self.stack_banks = {}
        for key, bank in ((0xD5184100, 0), (0xD51C4100, 1), (0xD51E4100, 2)):
            if key in self.system_registers:
                self.stack_banks[bank] = self.system_registers[key]

    def _select_stack(self, el: int, selection: int) -> None:
        old = self.current_el if self.pstate_sp else 0
        new = el if selection else 0
        self.stack_banks[old] = self.sp
        if new != old:
            self.sp = self.stack_banks.get(new, 0)
        self.current_el, self.pstate_sp = el, selection

    def pstate(self) -> int:
        if self.system_registers is None:
            raise RuntimeError('PSTATE requires the opt-in system-register model.')
        return ((self.n << 31) | (self.z << 30) | (self.c << 29) |
                (self.vflag << 28) | (self.system_registers.get(0xD51B4220, 0) & 0x3c0) |
                (self.current_el << 2) | self.pstate_sp)

    def take_irq(self, target_el: Optional[int] = None) -> bool:
        """Inject an already-routed physical IRQ between instructions.

        Arm 102412_0103_02 sections5.1/5.2 and6: save PC/PSTATE, choose
        SP_ELx and vector group, mask DAIF. Routing/controller priority is
        supplied by the gate, not invented here. Nested IRQ requires software
        to unmask and save its banked ELR/SPSR first; no hidden context stack.
        https://documentation-service.arm.com/static/67ac57fb091bfc3e0a9479cc
        """
        if self.system_registers is None:
            raise RuntimeError('IRQ injection requires the opt-in system-register model.')
        target = self.current_el if target_el is None else target_el
        if target not in (1, 2, 3):
            raise ValueError('An IRQ target must be EL1, EL2 or EL3.')
        if target < self.current_el:
            return False
        if target == self.current_el and self.pstate() & 0x80:
            return False
        vector_key = {1:0xD518C000, 2:0xD51CC000, 3:0xD51EC000}[target]
        vector = self.system_registers.get(vector_key, 0)
        if vector == 0 or vector & 2047:
            raise RuntimeError('IRQ delivery requires a nonzero 2048-byte-aligned VBAR.')
        offset = 0x480 if target > self.current_el else (0x280 if self.pstate_sp else 0x80)
        elr, spsr = ERET_BANKS[target]
        self.system_registers[elr] = self.pc
        self.system_registers[spsr] = self.pstate()
        self._select_stack(target, 1)
        self.system_registers[0xD51B4220] = 0x3c0
        self.excl_clear()
        self.pc = vector + offset
        return True

    def sysreg(self, write_base: int) -> Optional[int]:
        """What a register holds, or None if nothing has written it.

        None and 0 are different answers and the caller must be able to
        tell them apart: "the stub never wrote SCR_EL3" and "the stub
        wrote zero into SCR_EL3" are two different stubs.
        """
        if self.system_registers is None:
            return None
        return self.system_registers.get(write_base)

    def step(self) -> None:
        here = self.pc
        # THE FAULT MUST NAME THE INSTRUCTION THAT MADE THE ACCESS, not
        # the one after it.  self.pc is advanced below before the operand
        # is touched, so a guard reading self.pc would report the fault
        # four bytes late - which is a DIFFERENT source line whenever the
        # store is the last instruction of a statement, and that is
        # exactly where these faults live.  Both private copies of the
        # rule had this off-by-one; it is fixed here once.
        self.this_instr = here
        ins = self.fetch(here)
        self.pc = (self.pc + 4) & MASK64

        # The generic timer's count moves with every instruction executed,
        # including this one.  See the note on `cntpct`.
        self.cntpct = (self.cntpct + self.cntpct_per_instruction) & MASK64

        # Hints: nop, wfe, wfi, sev. (wfi added 2026-08-24.)
        if ins in (0xD503201F, 0xD503205F, 0xD503207F, 0xD503209F):
            return

        # DSB/DMB/ISB with any barrier option - widened 2026-08-24, was
        # the three fixed 'sy' words.
        #   1101 0101 0000 0011 0011 CRm(4) op2(3) 11111
        # op2 4=DSB, 5=DMB, 6=ISB; CRm is the shareability/type option and
        # does not change what this single-threaded model has to do, which
        # is nothing.
        if (ins & 0xFFFFF01F) == 0xD503301F and 4 <= ((ins >> 5) & 7) <= 6:
            return

        # DC / IC / TLBI cache and TLB maintenance - added 2026-08-24.
        #
        # SYS: 1101 0101 00 L op0(2) op1(3) CRn(4) CRm(4) op2(3) Rt(5)
        # with L=0 and op0=01, so bits 31:19 are fixed at 0xD5080000 and
        # the four selector fields pack into the key below as
        # op1<<12 | CRn<<8 | CRm<<4 | op2 - the ARM ARM quadruple, in
        # order. The identical table lives in RaspberryPi4/A64EmuCore.pbi
        # (EmuA64SysOpName) and the mnemonic side in A64Assembler.pbi.
        #
        # MODELLED AS NO-OPS, correctly: this interpreter has one flat
        # byte-addressed memory with no I-cache, no D-cache and no TLB,
        # so every line is already coherent and there are no translations
        # to discard. They must still decode rather than fault, because a
        # boot or loader sequence that contains them has to be runnable
        # here - and this interpreter is the oracle the other two models
        # are checked against, so a fault would fail correct programs.
        #
        # DC ZVA is deliberately NOT in the table: it zeroes memory, so a
        # no-op would be a wrong answer rather than an invisible one.
        if (ins & 0xFFF80000) == 0xD5080000:
            key = (
                (((ins >> 16) & 7) << 12)
                | (((ins >> 12) & 15) << 8)
                | (((ins >> 8) & 15) << 4)
                | ((ins >> 5) & 7)
            )
            if key in SYS_MAINTENANCE:
                return
            # AT lives in the same family and is NOT a no-op: it walks the
            # translation tables and writes fault status, physical address
            # and memory attributes into PAR_EL1. There is no walker here,
            # so passing over it would leave PAR_EL1 holding the PREVIOUS
            # translation's answer - which reads as a successful
            # translation of the wrong address and lets the program carry
            # on. Refused by name instead. (Added 2026-09-04, forum 627.)
            if key in SYS_ADDRESS_TRANSLATION:
                raise RuntimeError(
                    f"the A64 interpreter cannot execute "
                    f"'{SYS_ADDRESS_TRANSLATION[key]}, x{ins & 31}' at {here:#x}: "
                    "address translation asks the hardware to walk the "
                    "translation tables and answer in PAR_EL1, and this model "
                    "has one flat memory with no translation-table walker, so "
                    "it has no answer to give. Running it as a no-op would "
                    "leave PAR_EL1 holding the previous translation's result, "
                    "which reads as a successful translation of the wrong "
                    "address. Run this sequence on the board, or replace the "
                    "AT with the check it stands in for."
                )
            raise RuntimeError(f"unsupported SYS instruction 0x{ins:08X}")

        # SVC / HVC / SMC / BRK / HLT - exception generation, 2026-09-04
        # (forum 611). Decoded so the refusal can name the instruction and
        # its immediate, then refused: this model has no exception vectors,
        # no secure world and no debug host, so there is no handler for any
        # of them to reach. Falling through would pretend the call returned
        # and let the program read a result nothing produced.
        entry = EXCEPTION_GENERATION.get(ins & 0xFFE0001F)
        if entry is not None:
            mnemonic, target = entry
            raise RuntimeError(
                f"the A64 interpreter cannot execute "
                f"'{mnemonic} #{(ins >> 5) & 0xFFFF}' at {here:#x}: it raises "
                f"an exception to {target}, and this model has no exception "
                "vectors, no secure world and no debug host, so no handler "
                "exists for it to reach. Continuing past it would pretend the "
                "call returned and let the program read a result nothing "
                "produced. Run this image on the board, or stub the call in "
                "the source under test."
            )

        # Immediate mask writes remain no-ops in legacy flat mode; in the
        # opt-in system model they control explicit routed IRQ injection.
        if (ins & 0xFFFFF0FF) in (0xD50340DF, 0xD50340FF):
            if self.system_registers is not None:
                bits = ((ins >> 8) & 15) << 6
                old = self.system_registers.get(0xD51B4220, 0)
                self.system_registers[0xD51B4220] = (old | bits) if (ins & 0xFFFFF0FF) == 0xD50340DF else (old & ~bits)
            return

        if (ins & 0xFFFFFEFF) == 0xD50040BF:
            if self.system_registers is None:
                raise RuntimeError('SPSel requires the opt-in system-register model.')
            if self.current_el == 0:
                raise RuntimeError('SPSel is privileged and cannot be changed at EL0.')
            self._select_stack(self.current_el, (ins >> 8) & 1)
            return

        # MRS Xt, CNTPCT_EL0.  ABOVE the opt-in store on purpose: nothing
        # writes this register, so the store would answer it with the zero
        # it has never been given and the count would stand still for a
        # gate that had opted in.  See the note on `cntpct`.
        if (ins & 0xFFFFFFE0) == CNTPCT_EL0_READ:
            rt = ins & 31
            if rt != 31:
                self.x[rt] = self.cntpct
            return

        # ------------------------------------------------------------------
        #  MRS / MSR (register form) and ERET - 2026-09-07, OPT-IN ONLY.
        # ------------------------------------------------------------------
        #  Both of these are silent unless a gate called
        #  enable_system_registers(); without it they fall through to the
        #  refusal at the foot of step(), exactly as they did before today.
        #  That is deliberate - see the long note on `system_registers`.
        #
        #  ORDER MATTERS. This test sits BELOW the hint, barrier, SYS and
        #  PSTATE-immediate tests above, because `msr daifset, #n`,
        #  `msr spsel, #n`, `dc`, `ic`, `tlbi` and the barriers all live in
        #  the same 0xD5.. space with op0 = 00 or 01, and a broader test
        #  placed first would swallow them and report each one as a system
        #  register nobody has heard of.
        if self.system_registers is not None:
            top = ins & 0xFFF00000
            if top in (0xD5100000, 0xD5300000):
                read = bool(ins & self.SYSREG_READ_BIT)
                base = (ins & self.SYSREG_WRITE_MASK) & ~self.SYSREG_READ_BIT
                rt = ins & 31
                if read:
                    if base == self.CURRENTEL_WRITE_BASE:
                        # CurrentEL holds the level in bits 3:2, so EL3
                        # reads as 12 and EL2 as 8. Answered from the
                        # model's own level rather than from the store,
                        # because it is not a register anything writes.
                        value = self.current_el << 2
                    elif base == 0xD5184200:
                        value = self.pstate_sp
                    elif base == 0xD51B4200:
                        value = (self.n << 31) | (self.z << 30) | (self.c << 29) | (self.vflag << 28)
                    elif base in (0xD5184100, 0xD51C4100, 0xD51E4100):
                        bank = {0xD5184100:0, 0xD51C4100:1, 0xD51E4100:2}[base]
                        value = self.sp if bank == (self.current_el if self.pstate_sp else 0) else self.stack_banks.get(bank, 0)
                    else:
                        value = self.system_registers.get(base, 0)
                    if rt != 31:
                        self.x[rt] = value & MASK64
                else:
                    self.system_registers[base] = (
                        self.x[rt] & MASK64 if rt != 31 else 0)
                    if base == 0xD51B4200:
                        value = self.system_registers[base]
                        self.n, self.z, self.c, self.vflag = ((value >> bit) & 1 for bit in (31, 30, 29, 28))
                    elif base == 0xD5184200:
                        if self.current_el == 0:
                            raise RuntimeError('SPSel is privileged and cannot be changed at EL0.')
                        self._select_stack(self.current_el, self.system_registers[base] & 1)
                    if base in (0xD5184100, 0xD51C4100, 0xD51E4100):
                        bank = {0xD5184100:0, 0xD51C4100:1, 0xD51E4100:2}[base]
                        value = self.system_registers[base]
                        self.stack_banks[bank] = value
                        if bank == (self.current_el if self.pstate_sp else 0):
                            self.sp = value
                return

            # ERET. The level it returns FROM decides which ELR and SPSR
            # it reads; SPSR.M[3:2] decides the level it returns TO. Both
            # halves are needed here: the stub gate's whole claim is that
            # our stub reaches the kernel WITHOUT one of these, and a
            # model that could not execute an eret at all could not tell
            # a stub that skips it from a stub whose eret it cannot decode.
            if ins == 0xD69F03E0:
                elr_base, spsr_base = ERET_BANKS.get(
                    self.current_el, (None, None))
                if elr_base is None:
                    raise RuntimeError(
                        f"eret at EL{self.current_el} at {here:#x}: an "
                        "exception return from EL0 is not a thing the "
                        "architecture defines, and this model will not "
                        "invent a destination for it.")
                spsr = self.system_registers.get(spsr_base, 0)
                if (spsr & 31) not in (0, 4, 5, 8, 9, 12, 13):
                    raise RuntimeError(f'eret at {here:#x}: invalid or unsupported SPSR mode {spsr & 31:#x}.')
                if spsr & ~0xF00003CF:
                    raise RuntimeError(f'eret at {here:#x}: unsupported PSTATE controls in SPSR {spsr:#x}.')
                if (spsr >> 4) & 1:
                    raise RuntimeError(
                        f"eret at {here:#x} with SPSR.M[4] set asks to "
                        f"return to AArch32 (SPSR = {spsr:#x}). This model "
                        "executes A64 only, and taking the request as "
                        "AArch64 would run a different machine's "
                        "instructions and call the answer a result.")
                to_el = (spsr >> 2) & 3
                if to_el > self.current_el:
                    raise RuntimeError(
                        f"eret at EL{self.current_el} at {here:#x} with "
                        f"SPSR.M asking for EL{to_el}. An exception return "
                        "cannot gain privilege; on the part this raises an "
                        "Illegal Exception Return, so it is refused here "
                        "rather than modelled as a level nobody may reach.")
                target = self.system_registers.get(elr_base, 0)
                if target & 3:
                    raise RuntimeError(f'eret at {here:#x}: unaligned A64 return PC {target:#x}.')
                self.erets.append((self.current_el, to_el, target))
                self._select_stack(to_el, spsr & 1)
                self.n, self.z, self.c, self.vflag = ((spsr >> bit) & 1 for bit in (31, 30, 29, 28))
                self.system_registers[0xD51B4220] = spsr & 0x3c0
                self.pc = target & MASK64
                return

        # CLREX - added 2026-08-28.  Same 0xD503 hint/barrier space as the
        # block above but op2 = 010, so it falls through that test rather
        # than colliding with it.  CRm is ignored on decode
        # (arm-a64-instruction-set.txt:10425) and the whole operation is
        # ClearExclusiveLocal (:10434).
        if (ins & 0xFFFFF0FF) == 0xD503305F:
            self.excl_clear()
            return

        # ------------------------------------------------------------------
        #  LOAD/STORE EXCLUSIVE AND ORDERED - added 2026-08-28
        # ------------------------------------------------------------------
        #  ldxr / ldaxr / stxr / stlxr / ldar / stlr, 32- and 64-bit.
        #  One diagram serves all six (arm-a64-instruction-set.txt:41583
        #  and its five siblings, listed in A64Assembler.pbi's block of the
        #  same name):
        #
        #    size(31:30) 001000(29:24) o2(23) L(22) o1(21) Rs(20:16)
        #    o0(15) Rt2(14:10) Rn(9:5) Rt(4:0)
        #
        #  o2 = 1 means "ordered but NOT exclusive" - ldar and stlr take no
        #  reservation and check none.  o0 = 1 adds acquire or release
        #  ordering.
        #
        #  ORDERING IS A NO-OP HERE AND THAT IS CORRECT, NOT A SHORTCUT.
        #  This model executes one instruction at a time to completion with
        #  a single flat memory, so every access is already globally
        #  ordered and there is nothing for an acquire or a release to
        #  constrain.  Modelling ordering would require a memory model with
        #  reordering, which is a different program.  The consequence is
        #  stated plainly for anyone reading a gate's output: THIS MODEL
        #  CANNOT FAIL A PROGRAM THAT USES ldxr/stxr WHERE IT NEEDED
        #  ldaxr/stlxr.  Only the board can, and only sometimes.
        #
        #  What it CAN fail is every reservation-logic mistake - see the
        #  note above excl_mark().
        if (ins & 0x3F000000) == 0x08000000:
            sz = (ins >> 30) & 3
            o2 = (ins >> 23) & 1
            load = (ins >> 22) & 1
            pair = (ins >> 21) & 1
            rs = (ins >> 16) & 31
            rn = (ins >> 5) & 31
            rt = ins & 31
            # REFUSE THE FORMS THE ASSEMBLER CANNOT EMIT rather than
            # guessing at them.  A model that quietly does something
            # plausible for ldxp is a model that will one day confirm a
            # wrong image.  A64Assembler.pbi encodes neither the pair
            # forms nor the byte/halfword forms and says why in its own
            # block; if that changes, this decodes them or this raises.
            #
            # o1 = 1 is TWO different things depending on o2, and the
            # message says which, because "not modelled" pointing at the
            # wrong instruction family costs the reader an hour: with
            # o2 = 0 it is the load/store PAIR exclusives, and with
            # o2 = 1 it is the ARMv8.1 LSE compare-and-swap family, which
            # shares this encoding group and is UNDEF on a Cortex-A72.
            if pair:
                if o2:
                    raise RuntimeError(
                        f"0x{ins:08X} at 0x{here:X} is an ARMv8.1 LSE compare-and-swap "
                        "(o2=1, o1=1 in the exclusive group).  It is UNDEFINED on the "
                        "Cortex-A72 (arm-a64-instruction-set.txt:6169) and "
                        "A64Assembler.pbi refuses to emit it.  Nothing should have "
                        "produced this word."
                    )
                raise RuntimeError(
                    f"exclusive PAIR form 0x{ins:08X} at 0x{here:X} is not modelled - "
                    "o1=1 selects ldxp/ldaxp/stxp/stlxp, which A64Assembler.pbi "
                    "does not encode.  Add both sides together or neither."
                )
            if sz < 2:
                raise RuntimeError(
                    f"exclusive/ordered byte or halfword form 0x{ins:08X} at 0x{here:X} "
                    f"is not modelled - size=0b{sz:02b}.  A64Assembler.pbi encodes only "
                    "the 32- and 64-bit forms."
                )
            size = 4 if sz == 2 else 8
            sf = 1 if sz == 3 else 0
            addr = self.reg(rn, 1, sp_ok=True)
            if o2:
                # ldar / stlr: ordered, no reservation taken, none checked.
                # Note stlr still goes through self.store(), so it clears a
                # reservation it overlaps - it is an ordinary store as far
                # as the monitor is concerned.
                if load:
                    self.put(rt, self.load(addr, size), sf)
                else:
                    self.store(addr, self.reg(rt, sf), size)
                return
            if load:
                # ldxr / ldaxr.  Mark BEFORE the load so that an alignment
                # fault raised by load() leaves no reservation behind - the
                # opposite order would mark and then abort, which is a
                # state real hardware never reaches through this path.
                value = self.load(addr, size)
                self.excl_mark(addr, size)
                self.put(rt, value, sf)
                return
            # stxr / stlxr.  excl_pass() answers and clears in one call.
            #
            # THE STORE AND THE STATUS ARE DECIDED SEPARATELY, which
            # looks redundant while excl_status_always_fails is False
            # and is the whole point when it is True: the measured board
            # performs the store exactly when the monitor says it may,
            # and then reports failure regardless.  See the note above
            # that flag.
            passed = self.excl_pass(addr, size)
            if passed:
                self.store(addr, self.reg(rt, sf), size)
            status = 0 if (passed and not self.excl_status_always_fails) else 1
            # The status register is always 32-bit: "<Ws> Is the 32-bit
            # name ..." (:65814).  Rs = 31 is WZR and the status is
            # discarded, which put() already does.
            self.put(rs, status, 0)
            return

        # MOVN/MOVZ/MOVK (wide immediate).
        wide = ins & 0x1F800000
        if wide in (0x12800000, 0x52800000, 0x72800000):
            sf = (ins >> 31) & 1
            opc = (ins >> 29) & 3
            hw = (ins >> 21) & 3
            bits = 64 if sf else 32
            if not sf and hw > 1:
                raise RuntimeError("invalid 32-bit wide-immediate shift")
            imm = ((ins >> 5) & 0xFFFF) << (16 * hw)
            rd = ins & 31
            if opc == 0:  # movn
                value = (~imm) & ((1 << bits) - 1)
            elif opc == 2:  # movz
                value = imm
            elif opc == 3:  # movk
                keep = self.reg(rd, sf)
                value = (keep & ~(0xFFFF << (16 * hw))) | imm
            else:
                raise RuntimeError("reserved wide-immediate opcode")
            self.put(rd, value, sf)
            return

        # ADD/SUB immediate.
        if (ins & 0x1F000000) == 0x11000000:
            sf, op, setflags = (ins >> 31) & 1, (ins >> 30) & 1, (ins >> 29) & 1
            shift = 12 if ((ins >> 22) & 1) else 0
            imm = ((ins >> 10) & 0xFFF) << shift
            rn, rd = (ins >> 5) & 31, ins & 31
            a = self.reg(rn, sf, True)
            result = a - imm if op else a + imm
            if setflags:
                (self.flags_sub if op else self.flags_add)(a, imm, result, 64 if sf else 32)
            self.put(rd, result, sf, not setflags)
            return

        # ADD/SUB shifted register.
        if (ins & 0x1F200000) == 0x0B000000:
            sf, op, setflags = (ins >> 31) & 1, (ins >> 30) & 1, (ins >> 29) & 1
            shift_type, amount = (ins >> 22) & 3, (ins >> 10) & 0x3F
            rm, rn, rd = (ins >> 16) & 31, (ins >> 5) & 31, ins & 31
            bits = 64 if sf else 32
            b = self.reg(rm, sf)
            if shift_type == 0: b = (b << amount) & ((1 << bits) - 1)
            elif shift_type == 1: b >>= amount
            elif shift_type == 2: b = sx(b, bits) >> amount
            else: raise RuntimeError("reserved add/sub shift")
            a = self.reg(rn, sf)
            result = a - b if op else a + b
            if setflags:
                (self.flags_sub if op else self.flags_add)(a, b, result, bits)
            self.put(rd, result, sf)
            return

        # Logical shifted register, including MOV/MVN aliases.
        if (ins & 0x1F000000) == 0x0A000000:
            sf, opc, invert = (ins >> 31) & 1, (ins >> 29) & 3, (ins >> 21) & 1
            shift_type, amount = (ins >> 22) & 3, (ins >> 10) & 0x3F
            rm, rn, rd = (ins >> 16) & 31, (ins >> 5) & 31, ins & 31
            bits = 64 if sf else 32
            b = self.reg(rm, sf)
            if shift_type == 0: b = (b << amount) & ((1 << bits) - 1)
            elif shift_type == 1: b >>= amount
            elif shift_type == 2: b = sx(b, bits) >> amount
            else: b = ror(b, amount, bits)
            if invert: b = ~b
            a = self.reg(rn, sf)
            result = (a & b, a | b, a ^ b, a & b)[opc]
            self.put(rd, result, sf)
            if opc == 3:
                result &= (1 << bits) - 1
                self.n, self.z = int(bool(result & (1 << (bits - 1)))), int(result == 0)
                self.c = self.vflag = 0
            return

        # SBFM / UBFM, restricted to the aliases the assembler emits:
        # sxtb / sxth / sxtw / uxtb / uxth and the immediate shifts
        # lsl / lsr / asr #imm.
        #
        # ADDED 2026-08-24 with the 64-bit change. This whole family was
        # MISSING from the oracle - the emitted subset had never happened
        # to reach it, so "lsl x0, x0, #5" would have raised "unsupported
        # A64 word" here while the assembler encoded it and the PureBasic
        # emulator executed it. Three models are only worth having when
        # they cover the same ground; two out of three agreeing is exactly
        # how a wrong encoding gets a pass.
        #
        # The decode mirrors A64EmuCore.pbi's deliberately, including the
        # refusal: a bitfield that is not one of those aliases raises here
        # rather than being served by a general BFM implementation, so an
        # encoder bug that produced a valid-but-unintended immr/imms pair
        # is caught instead of quietly executed.
        if (ins & 0x1F800000) in (0x13000000, 0x53000000):
            sf = (ins >> 31) & 1
            bits = 64 if sf else 32
            signed = (ins & 0x40000000) == 0
            immr, imms = (ins >> 16) & 0x3F, (ins >> 10) & 0x3F
            rn, rd = (ins >> 5) & 31, ins & 31
            a = self.reg(rn, sf)
            # imms == 31 is an EXTEND only at sf=1; at sf=0 it is bits-1
            # and means the shift alias on the next branch.
            if immr == 0 and (imms in (7, 15) or (imms == 31 and sf)):
                result = a & ((1 << (imms + 1)) - 1)
                if signed:
                    result = sx(result, imms + 1)
            elif imms == bits - 1:
                result = sx(a, bits) >> immr if signed else a >> immr
            elif imms < immr:
                amount = bits - immr
                if imms != bits - 1 - amount:
                    raise RuntimeError("bitfield is not one of the emitted shift aliases")
                result = (a << amount) & ((1 << bits) - 1)
            else:
                raise RuntimeError("bitfield is outside the emitted subset")
            self.put(rd, result, sf)
            return

        # ---- CRC32 and CRC32C, added 2026-09-05 ------------------
        #      sf 0 0 11010110 Rm 010 C(12) sz(11:10) Rn Rd
        #
        #  This part HAS them - ID_AA64ISAR0_EL1.CRC32 is the one
        #  non-zero field in the whole register - and the tree computed
        #  CRC32 in software until now.
        #
        #  A DIFFERENT SHAPE FROM THE NATIVE MODEL, as every arm here
        #  is meant to be. That one walks the reflected polynomial bit
        #  by bit; this one builds the 256-entry table the standard
        #  formulation uses and indexes it, which is the same function
        #  by a different route. Two witnesses, not one translated.
        if (ins & 0x1FE0E000) == 0x1AC04000:
            sf = (ins >> 31) & 1
            sz, c_bit = (ins >> 10) & 3, (ins >> 12) & 1
            if (sf == 1 and sz != 3) or (sf == 0 and sz == 3):
                raise RuntimeError(
                    f"A64 word {ins:08x} at {here:#x} is a CRC32 with "
                    f"sf={sf} and sz={sz:02b}, a pairing the architecture "
                    "prints as UNDEFINED: only sf=0 with sz 00/01/10 and "
                    "sf=1 with sz=11 are defined. The accumulator is 32 "
                    "bits in every variant; only the DATA operand widens.")
            rm, rn, rd = (ins >> 16) & 31, (ins >> 5) & 31, ins & 31
            poly = 0x82F63B78 if c_bit else 0xEDB88320
            table = _crc_table(poly)
            acc = self.reg(rn, 0) & 0xFFFFFFFF
            val = self.reg(rm, sf)
            for i in range(1 << sz):
                acc = (acc >> 8) ^ table[(acc ^ (val >> (i * 8))) & 0xFF]
            self.put(rd, acc & 0xFFFFFFFF, 0)
            return

        # Variable shifts and divide.
        key = ins & 0x1FE0FC00
        two_src = {
            0x1AC02000: "lsl", 0x1AC02400: "lsr", 0x1AC02800: "asr",
            0x1AC00800: "udiv", 0x1AC00C00: "sdiv",
        }
        if key in two_src:
            sf = (ins >> 31) & 1
            rm, rn, rd = (ins >> 16) & 31, (ins >> 5) & 31, ins & 31
            bits = 64 if sf else 32
            a, b = self.reg(rn, sf), self.reg(rm, sf)
            op = two_src[key]
            amount = b & (bits - 1)
            if op == "lsl": result = a << amount
            elif op == "lsr": result = a >> amount
            elif op == "asr": result = sx(a, bits) >> amount
            elif b == 0: result = 0
            elif op == "udiv": result = a // b
            else:
                # =====================================================
                # SDIV WAS `int(sx(a, bits) / sx(b, bits))` UNTIL
                # 2026-08-26 AND THAT IS FLOAT DIVISION.
                # =====================================================
                # Python's `/` converts both operands to float64, which
                # carries 53 bits of mantissa. A 64-bit dividend does
                # not fit, so the quotient came back rounded and
                # `int()` then truncated an ALREADY WRONG number - off
                # by one, either way, unpredictably.
                #
                # It is silent below 2^53 and wrong above it, which is
                # the worst possible shape: every small test agrees and
                # the oracle only lies about the operands nobody checks
                # by hand.
                #
                # FOUND BY, and this is the part worth recording: a
                # pure-integer library gate (a64_damage_check.py) whose
                # program disagreed with an independent Python model of
                # the same arithmetic. The program was right, the model
                # was right, and the machine underneath them both was
                # wrong. Three worked examples, all with a 300 divisor:
                #
                #   $35174A4158B8A0B7 % 300  gave -265, want  35
                #   $62CE1FFAD85B1C36 % 300  gave  374, want  74
                #   $0CF91633BE7328C1 % 300  gave  -43, want 257
                #
                # A remainder of 374 against a divisor of 300 cannot be
                # a remainder at all, which is what made it findable.
                #
                # THE COMPILER WAS NEVER INVOLVED. The emitted code is
                # the textbook pair, `sdiv x16, x12, x13` followed by
                # `msub x11, x16, x13, x12`, and it is correct. Only
                # this line was wrong. Anything on this disk that was
                # gated against a 64-bit divide or modulo of a large
                # value was gated against a lie and should be re-run.
                #
                # ARM ARM C6.2.x: SDIV rounds TOWARD ZERO. Python's //
                # floors, so a negative quotient must not be produced
                # by it - hence the magnitude-then-sign form rather
                # than the shorter `sx(a) // sx(b)`, which is correct
                # for same-sign operands and off by one for the rest.
                na, nb = sx(a, bits), sx(b, bits)
                q = abs(na) // abs(nb)
                if (na < 0) != (nb < 0):
                    q = -q
                result = q
            self.put(rd, result, sf)
            return

        # MADD/MSUB (MUL is MADD with Ra = ZR).
        if (ins & 0x1F000000) == 0x1B000000:
            sf, sub = (ins >> 31) & 1, (ins >> 15) & 1
            rm, ra, rn, rd = (ins >> 16) & 31, (ins >> 10) & 31, (ins >> 5) & 31, ins & 31
            product = self.reg(rn, sf) * self.reg(rm, sf)
            acc = self.reg(ra, sf)
            self.put(rd, acc - product if sub else acc + product, sf)
            return

        # Unsigned-immediate byte/halfword/word/dword loads and stores.
        #
        # THE MASK GAINED BIT 26 ON 2026-09-04, forum 633, and this half
        # of that fix is the one worth reading.  Bit 26 - the architecture
        # names it VR - selects the register BANK, and without it this
        # branch claimed the SIMD&FP loads and stores as well and wrote a
        # general-purpose register with no diagnostic.
        #
        # THE INDEPENDENT ORACLE CARRIED THE SAME BUG AS THE MODEL IT
        # CHECKS.  That is the finding, not the bit.  This interpreter
        # exists so two implementations can be diffed against each other;
        # both were written from the same reading of the same encoding
        # table, both dropped the same bit, and a differential run would
        # have reported perfect agreement.  Two implementations are two
        # witnesses only when they can fail differently - which is why
        # the gate that came with this fix rebuilds every word from the
        # manual's own bit-field diagram instead of from either of them.
        if (ins & 0x3F000000) == 0x39000000:
            size_code, load = (ins >> 30) & 3, (ins >> 22) & 1
            size = 1 << size_code
            imm = ((ins >> 10) & 0xFFF) * size
            rn, rt = (ins >> 5) & 31, ins & 31
            addr = (self.sp if rn == 31 else self.x[rn]) + imm
            if load: self.put(rt, self.load(addr, size), int(size == 8))
            else: self.store(addr, self.reg(rt, int(size == 8)), size)
            return

        # ADR.
        if (ins & 0x9F000000) == 0x10000000:
            imm = sx((((ins >> 5) & 0x7FFFF) << 2) | ((ins >> 29) & 3), 21)
            self.put(ins & 31, here + imm, 1)
            return

        # ADRP - the same 21-bit displacement counted in 4 KB PAGES, and
        # relative to the page holding the instruction. This is the third
        # place the encoding is written out: the assembler emits it, the
        # native emulator executes it, and this independent interpreter
        # checks them both. Adding it to two of the three would have made
        # the oracle agree with nothing.
        if (ins & 0x9F000000) == 0x90000000:
            imm = sx((((ins >> 5) & 0x7FFFF) << 2) | ((ins >> 29) & 3), 21)
            self.put(ins & 31, (here & ~0xFFF) + (imm << 12), 1)
            return

        # B / BL.
        if (ins & 0x7C000000) == 0x14000000:
            if ins & 0x80000000: self.x[30] = self.pc
            self.pc = here + (sx(ins & 0x03FFFFFF, 26) << 2)
            return

        # B.cond.
        if (ins & 0xFF000010) == 0x54000000:
            if self.cond(ins & 15):
                self.pc = here + (sx((ins >> 5) & 0x7FFFF, 19) << 2)
            return

        # CBZ / CBNZ.
        if (ins & 0x7E000000) == 0x34000000:
            sf, nz = (ins >> 31) & 1, (ins >> 24) & 1
            take = self.reg(ins & 31, sf) != 0
            if take == bool(nz):
                self.pc = here + (sx((ins >> 5) & 0x7FFFF, 19) << 2)
            return

        # BR / BLR / RET.
        masked = ins & 0xFFFFFC1F
        if masked in (0xD61F0000, 0xD63F0000, 0xD65F0000):
            rn = (ins >> 5) & 31
            target = self.x[rn] if rn != 31 else 0
            if masked == 0xD63F0000: self.x[30] = self.pc
            self.pc = target
            return

        if self.step_simd(ins):
            return

        # ---- SCALAR FLOATING POINT, added 2026-09-05 (tier 4b) --------
        #  The four diagrams the assembler encodes, executed through the
        #  exact-rational binary32 core - see this file's own note on why
        #  that core is imported rather than copied.
        if (ins & 0x5F000000) == 0x1E000000:
            import a64_f32_gate as f32
            ftype = (ins >> 22) & 3
            rn, rd, rm = (ins >> 5) & 31, ins & 31, (ins >> 16) & 31
            if ftype == 3:
                raise RuntimeError(
                    f'A64 word {ins:08x} at {here:#x} is a HALF-PRECISION '
                    'floating-point instruction, and it is UNDEFINED on '
                    'this part: ID_AA64PFR0_EL1.FP is a signed enumeration '
                    'in which 0 means implemented and 1 means implemented '
                    'WITH half precision, and it reads 0 here.')
            if ftype == 1:
                raise RuntimeError(
                    f'A64 word {ins:08x} at {here:#x} is a DOUBLE-PRECISION '
                    'floating-point instruction. This interpreter '
                    'implements binary32 exactly and deliberately absent '
                    'is the binary64 arithmetic: there is no caller for it '
                    'on this target and an approximation would be worse '
                    'than a refusal.')

            def fp(idx):
                return self.v[idx] & 0xFFFFFFFF

            # D: compare
            if (ins & 0xBF20FC00) == 0x1E202000:
                a = fp(rn)
                b = 0 if ((ins >> 3) & 1) else fp(rm)
                if f32.is_nan(a) or f32.is_nan(b):
                    n, z, c, v = 0, 0, 1, 1
                elif f32.f_rel(4, a, b):
                    n, z, c, v = 0, 1, 1, 0
                elif f32.f_rel(0, a, b):
                    n, z, c, v = 1, 0, 0, 0
                else:
                    n, z, c, v = 0, 0, 1, 0
                self.n, self.z, self.c, self.vflag = n, z, c, v
                return

            # A: two source
            if (ins & 0xBF200C00) == 0x1E200800:
                opc = (ins >> 12) & 15
                a, b = fp(rn), fp(rm)
                if   opc == 0b0000: r = f32.f_mul(a, b)
                elif opc == 0b0001: r = f32.f_div(a, b)
                elif opc == 0b0010: r = f32.f_add(a, b)
                elif opc == 0b0011: r = f32.f_sub(a, b)
                elif opc in (0b0100, 0b0101, 0b0110, 0b0111):
                    r = fp_minmax(f32, a, b, opc in (0b0100, 0b0110),
                                  opc in (0b0110, 0b0111))
                elif opc == 0b1000:
                    r = f32.f_mul(a, b)
                    if not f32.is_nan(r):
                        r ^= 0x80000000
                else:
                    raise RuntimeError(
                        f'A64 word {ins:08x} is in the scalar floating-point '
                        'two-source group but is not one of the operations '
                        'this interpreter implements.')
                self.v[rd] = r & 0xFFFFFFFF
                return

            # B: one source
            if (ins & 0xBF207C00) == 0x1E204000:
                opc = (ins >> 15) & 63
                if (opc >> 2) == 0b0001:
                    raise RuntimeError(
                        f'A64 word {ins:08x} at {here:#x} converts between '
                        'floating-point precisions, which needs the '
                        'binary64 format this interpreter deliberately '
                        'does not implement.')
                a = fp(rn)
                if   opc == 0b000000: r = a
                elif opc == 0b000001: r = a & 0x7FFFFFFF
                elif opc == 0b000010: r = a ^ 0x80000000
                elif opc == 0b000011: r = fp_sqrt(f32, a)
                elif opc in (0b001000, 0b001001, 0b001010, 0b001011,
                             0b001100, 0b001110, 0b001111):
                    mode = {0b001000: 'n', 0b001001: 'p', 0b001010: 'm',
                            0b001011: 'z', 0b001100: 'a', 0b001110: 'n',
                            0b001111: 'n'}[opc]
                    r = fp_rint(f32, a, mode)
                else:
                    raise RuntimeError(
                        f'A64 word {ins:08x} is in the scalar floating-point '
                        'one-source group but is not one of the operations '
                        'this interpreter implements.')
                self.v[rd] = r & 0xFFFFFFFF
                return

            # C: between floating point and integer
            if (ins & 0x7F20FC00) == 0x1E200000:
                sf = (ins >> 31) & 1
                rmode, opc = (ins >> 19) & 3, (ins >> 16) & 7
                bits = 64 if sf else 32
                mode = ('n', 'p', 'm', 'z')[rmode]
                if rmode == 0 and opc == 0b010:
                    self.v[rd] = fp_from_int(f32, sx(self.reg(rn, 1 if bits == 64 else 0), bits), True, bits)
                elif rmode == 0 and opc == 0b011:
                    self.v[rd] = fp_from_int(f32, self.reg(rn, 1 if bits == 64 else 0) & ((1 << bits) - 1), False, bits)
                elif rmode == 0 and opc == 0b110:
                    self.put(rd, fp(rn), sf)
                elif rmode == 0 and opc == 0b111:
                    self.v[rd] = self.reg(rn, 0) & 0xFFFFFFFF
                elif (opc & 0b110) == 0:
                    self.put(rd, fp_to_int(f32, fp(rn), (opc & 1) == 0, bits, mode), sf)
                elif rmode == 1 and (opc & 0b110) == 0b100:
                    self.put(rd, fp_to_int(f32, fp(rn), (opc & 1) == 0, bits, 'a'), sf)
                else:
                    raise RuntimeError(
                        f'A64 word {ins:08x} is a floating-point conversion '
                        'this interpreter does not implement.')
                return
        # THE SCALAR FLOATING-POINT GROUP, refused BY NAME. The assembler
        # has encoded it since 2026-08-26, so reaching here with one is a
        # missing arithmetic unit and not an unknown encoding - and the
        # two invite completely different repairs.
        if (ins & 0x5F000000) == 0x1E000000:
            raise RuntimeError(
                f"A64 word {ins:08x} at {here:#x} is a SCALAR "
                "FLOATING-POINT instruction. It is not an unknown "
                "encoding: the assembler encodes this group deliberately, "
                "and this interpreter deliberately does not execute it. A "
                "model built on the host language's own float type "
                "inherits that language's answers for signed zeros, "
                "gradual underflow, NaN payload propagation, ties-to-even "
                "and the saturation rails - which are exactly the corners "
                "in question - and then produces green results. Doing it "
                "honestly means transcribing FPAdd, FPMul, FPDiv, "
                "FPRound, FPUnpackBase and FPProcessNaNs from the "
                "architecture's own pseudocode.")

        # An MRS or MSR of a register this model does not answer.  NAME IT.
        # The encoding carries the architecture's own five-tuple, so the
        # refusal can say which register was asked for and what to do about
        # it; a bare hex word makes somebody decode it by hand before they
        # can even start, and that is the one thing this message was for.
        if (ins & 0xFFF00000) in (0xD5100000, 0xD5300000):
            rt = ins & 31
            register = "S%d_%d_C%d_C%d_%d" % (
                2 + ((ins >> 19) & 1), (ins >> 16) & 7,
                (ins >> 12) & 15, (ins >> 8) & 15, (ins >> 5) & 7)
            if ins & self.SYSREG_READ_BIT:
                asked = "mrs x%d, %s" % (rt, register)
            else:
                asked = "msr %s, x%d" % (register, rt)
            raise RuntimeError(
                f"A64 word {ins:08x} at {here:#x} is `{asked}`, a system "
                "register this model does not answer. It models CNTPCT_EL0 "
                "on its own, and enable_system_registers() adds a store "
                "that reads back what the program under test has written. "
                "Everything else - CNTFRQ_EL0 included, because its value "
                "is board data and not architecture - has to be answered "
                "by the gate, above step(), where the value it chooses is "
                "visible next to the claim it supports.")

        raise RuntimeError(f"unsupported A64 word {ins:08x} at {here:#x}")

    # ------------------------------------------------------------------
    #  ADVANCED SIMD, TIER 1 - added 2026-09-04
    # ------------------------------------------------------------------
    #  The second implementation of what the native model gained in the
    #  same change, and it is written from the manual rather than from
    #  that model - the point of a second implementation being that it
    #  can be wrong in a DIFFERENT place.  Forum 633 is the standing
    #  reminder of what happens when it is not: both implementations
    #  dropped the same bit from the same table and agreed perfectly.
    #
    #  The register file is one 128-bit Python integer per register,
    #  where the native model has to use two doublewords.  That is a
    #  deliberate difference, not an accident of language: the upper-half
    #  zeroing rule for 64-bit arrangements is invisible here (it falls
    #  out of masking to 64 bits) and is a separate, forgettable step
    #  there, so the two implementations cannot both forget it the same
    #  way.
    #
    #  Tried LAST in step(), after every integer arm, for the same reason
    #  the native model does it: these masks are wider than the exact
    #  tests above and must not be given the chance to claim a word that
    #  already has an owner.
    def vget(self, index: int) -> int:
        return self.v[index] & ((1 << 128) - 1)

    def vset(self, index: int, value: int, q: int) -> None:
        # 64-bit arrangements ZERO the upper half.  Here that is just the
        # mask; see the note above on why that difference is wanted.
        self.v[index] = value & ((1 << 128) - 1) if q else value & MASK64

    def velem(self, index: int, size: int, lane: int) -> int:
        bits = 8 << size
        return (self.vget(index) >> (lane * bits)) & ((1 << bits) - 1)

    def vsetelem(self, index: int, size: int, lane: int, value: int) -> None:
        bits = 8 << size
        mask = ((1 << bits) - 1) << (lane * bits)
        cur = self.vget(index) & ~mask
        self.v[index] = cur | ((value & ((1 << bits) - 1)) << (lane * bits))

    @staticmethod
    def _replicate(value: int, bits: int, total: int) -> int:
        out = 0
        for i in range(total // bits):
            out |= (value & ((1 << bits) - 1)) << (i * bits)
        return out

    @staticmethod
    def advsimd_expand_imm(op: int, cmode: int, imm8: int) -> int:
        """AdvSIMDExpandImm, for the cmode values MOVI and MVNI use.

        Transcribed from the architecture's own function.  The MSL forms
        (cmode 110x) are the ones a "shift the byte left" model gets
        wrong: they fill the bits BELOW the shifted byte with ONES, not
        zeros, which is the whole reason they exist.
        """
        top = cmode >> 1
        if top == 0b000:   val, unit = imm8, 32
        elif top == 0b001: val, unit = imm8 << 8, 32
        elif top == 0b010: val, unit = imm8 << 16, 32
        elif top == 0b011: val, unit = imm8 << 24, 32
        elif top == 0b100: val, unit = imm8, 16
        elif top == 0b101: val, unit = imm8 << 8, 16
        elif top == 0b110:
            val = ((imm8 << 16) | 0xFFFF) if (cmode & 1) else ((imm8 << 8) | 0xFF)
            unit = 32
        else:                                   # cmode 111x
            if cmode & 1:
                raise RuntimeError("cmode 1111 is the FMOV vector immediate, not modelled")
            if op == 0:
                return A64._replicate(imm8, 8, 64)
            # op == 1: each bit of imm8 selects a whole byte
            out = 0
            for i in range(8):
                if (imm8 >> i) & 1:
                    out |= 0xFF << (i * 8)
            return out
        return A64._replicate(val, unit, 64)

    def step_simd(self, ins: int) -> bool:
        # ---- LD1/2/3/4 and ST1/2/3/4 (multiple structures) -----------
        #      0 Q 001100 (post) L 0 Rm opcode(15:12) size(11:10) Rn Rt
        #
        #  THE OPCODE IS (rpt, selem) AND NOT A REGISTER COUNT. `rpt` is
        #  how many whole registers are filled in order; `selem` is the
        #  interleave factor. LD1 of four registers is (4, 1) and LD4 is
        #  (1, 4) - the same 64 bytes, de-interleaved into four streams.
        #  Written as the architecture's own double loop, because a
        #  whole-register copy is right for selem 1 and wrong for
        #  everything else.
        if (ins & 0xBF9F0000) == 0x0C000000 or (ins & 0xBF800000) == 0x0C800000:
            q, l = (ins >> 30) & 1, (ins >> 22) & 1
            opcode, size = (ins >> 12) & 15, (ins >> 10) & 3
            rn, rt, rm = (ins >> 5) & 31, ins & 31, (ins >> 16) & 31
            wb = (ins >> 23) & 1
            shape = {0b0111: (1, 1), 0b1010: (2, 1), 0b0110: (3, 1),
                     0b0010: (4, 1), 0b1000: (1, 2), 0b0100: (1, 3),
                     0b0000: (1, 4)}.get(opcode)
            if shape is None:
                return False
            rpt, selem = shape
            if selem > 1 and size == 3 and q == 0:
                raise RuntimeError(
                    f"Advanced SIMD word {ins:08x} is an interleaved "
                    "structure load or store with the 1D arrangement "
                    "(size:Q = 110), which the architecture prints as "
                    "RESERVED: one element per register leaves nothing "
                    "to interleave. LD1 and ST1 accept it and these do "
                    "not.")
            ebytes = 1 << size
            elements = (8 << q) // ebytes
            addr = self.sp if rn == 31 else self.x[rn]
            if l:
                # Element-at-a-time writes, so a 64-bit arrangement must
                # clear the upper half of every register it touches.
                for i in range(rpt * selem):
                    self.vset((rt + i) & 31, 0, q)
            for r in range(rpt):
                for e in range(elements):
                    tt = (rt + r) & 31
                    for _s in range(selem):
                        if l:
                            self.vsetelem(tt, size, e, self.load(addr, ebytes))
                        else:
                            self.store(addr, self.velem(tt, size, e), ebytes)
                        addr += ebytes
                        tt = (tt + 1) & 31
            if wb:
                base = self.sp if rn == 31 else self.x[rn]
                total = rpt * selem * (8 << q)
                base = (base + (total if rm == 31 else self.x[rm])) & MASK64
                if rn == 31: self.sp = base
                else: self.x[rn] = base
            return True

        # ---- THE SINGLE-STRUCTURE FAMILY: LDxR and the LANE forms ----
        #      0 Q 001101 (post) L R Rm opcode(15:13) S(12) size(11:10) Rn Rt
        #
        #  R is the PARITY of the structure count and the low bit of
        #  opcode says which pair, so selem = 2*(opcode & 1) + R + 1.
        #  The top two bits of opcode are the element width, except that
        #  11x is the replicate form and 10x covers word AND doubleword,
        #  told apart by the low bit of size. And the lane index is cut
        #  across Q, S and size differently at every width.
        if (ins & 0xBF9F0000) == 0x0D000000 or (ins & 0xBF800000) == 0x0D800000:
            q, l = (ins >> 30) & 1, (ins >> 22) & 1
            r_bit, opcode = (ins >> 21) & 1, (ins >> 13) & 7
            s_bit, size = (ins >> 12) & 1, (ins >> 10) & 3
            rn, rt, rm = (ins >> 5) & 31, ins & 31, (ins >> 16) & 31
            wb = (ins >> 23) & 1
            selem = 2 * (opcode & 1) + r_bit + 1
            addr = self.sp if rn == 31 else self.x[rn]
            if (opcode >> 1) == 0b11:
                if not l:
                    return False
                ebytes = 1 << size
                for i in range(selem):
                    val = self.load(addr + i * ebytes, ebytes)
                    self.vset((rt + i) & 31,
                              self._replicate(val, 8 << size, 128), q)
                total = selem * ebytes
            else:
                if (opcode >> 1) == 0b00:
                    esize, index = 0, (q << 3) | (s_bit << 2) | size
                elif (opcode >> 1) == 0b01:
                    esize, index = 1, (q << 2) | (s_bit << 1) | (size >> 1)
                elif size & 1:
                    esize, index = 3, q
                else:
                    esize, index = 2, (q << 1) | s_bit
                ebytes = 1 << esize
                for i in range(selem):
                    reg = (rt + i) & 31
                    if l:
                        self.vsetelem(reg, esize, index,
                                      self.load(addr + i * ebytes, ebytes))
                    else:
                        self.store(addr + i * ebytes,
                                   self.velem(reg, esize, index), ebytes)
                total = selem * ebytes
            if wb:
                base = self.sp if rn == 31 else self.x[rn]
                base = (base + (total if rm == 31 else self.x[rm])) & MASK64
                if rn == 31: self.sp = base
                else: self.x[rn] = base
            return True

        # ---- LDP / STP, integer and SIMD&FP --------------------------
        #      opc(31:30) 101 VR(26) cls(25:23) L(22) imm7 Rt2 Rn Rt
        if (ins & 0x3A000000) == 0x28000000 and 1 <= ((ins >> 23) & 7) <= 3:
            opc, vr = (ins >> 30) & 3, (ins >> 26) & 1
            cls, l = (ins >> 23) & 7, (ins >> 22) & 1
            imm7, rt2 = (ins >> 15) & 0x7F, (ins >> 10) & 31
            rn, rt = (ins >> 5) & 31, ins & 31
            if vr:
                scale = {0: 4, 1: 8, 2: 16}.get(opc)
            else:
                scale = {0: 4, 2: 8}.get(opc)    # opc 01 is LDPSW, not modelled
            if scale is None:
                return False
            off = sx(imm7, 7) * scale
            base = self.sp if rn == 31 else self.x[rn]
            addr = base if cls == 0b001 else base + off
            for i, reg in enumerate((rt, rt2)):
                at = addr + i * scale
                if vr:
                    if l: self.vset(reg, self.load(at, scale), int(scale == 16))
                    else: self.store(at, self.vget(reg) & ((1 << (scale * 8)) - 1), scale)
                else:
                    if l: self.put(reg, self.load(at, scale), int(scale == 8))
                    else: self.store(at, self.reg(reg, int(scale == 8)), scale)
            if cls in (0b001, 0b011):
                base = (base + off) & MASK64
                if rn == 31: self.sp = base
                else: self.x[rn] = base
            return True

        # ---- LDR / STR (immediate, SIMD&FP), unsigned offset ---------
        if (ins & 0x3F000000) == 0x3D000000:
            size, opc = (ins >> 30) & 3, (ins >> 22) & 3
            rn, rt, off = (ins >> 5) & 31, ins & 31, (ins >> 10) & 0xFFF
            if opc & 2:
                if size != 0:
                    return False
                scale, l = 16, int(opc == 3)
            else:
                scale, l = 1 << size, int(opc == 1)
            addr = (self.sp if rn == 31 else self.x[rn]) + off * scale
            if l:
                self.vset(rt, self.load(addr, scale), int(scale == 16))
            else:
                self.store(addr, self.vget(rt) & ((1 << (scale * 8)) - 1), scale)
            return True

        # ---- The copy group: DUP, INS, UMOV, SMOV --------------------
        #      0 Q op(29) 001110000 imm5(20:16) 0 imm4(14:11) 1 Rn Rd
        if (ins & 0x9FE08400) == 0x0E000400:
            q, op = (ins >> 30) & 1, (ins >> 29) & 1
            imm5, imm4 = (ins >> 16) & 31, (ins >> 11) & 15
            rn, rd = (ins >> 5) & 31, ins & 31
            if (imm5 & 15) == 0:
                return False
            size = 0
            while not ((imm5 >> size) & 1):
                size += 1
            index = imm5 >> (size + 1)
            if op == 1:                          # INS (element)
                self.vsetelem(rd, size, index, self.velem(rn, size, imm4 >> size))
                return True
            if imm4 == 0b0000:                   # DUP (element)
                if size == 3 and q == 0: return False
                self.vset(rd, self._replicate(self.velem(rn, size, index), 8 << size, 128), q)
                return True
            if imm4 == 0b0001:                   # DUP (general)
                if size == 3 and q == 0: return False
                self.vset(rd, self._replicate(self.reg(rn, int(size == 3)), 8 << size, 128), q)
                return True
            if imm4 == 0b0011:                   # INS (general)
                self.vsetelem(rd, size, index, self.reg(rn, int(size == 3)))
                return True
            if imm4 == 0b0111:                   # UMOV
                self.put(rd, self.velem(rn, size, index), q)
                return True
            if imm4 == 0b0101:                   # SMOV
                self.put(rd, sx(self.velem(rn, size, index), 8 << size), q)
                return True
            return False

        # ---- FAMILY A: Advanced SIMD three same ----------------------
        #      0 Q U(29) 01110 size(23:22) 1 Rm opcode(15:11) 1 Rn Rd
        #
        #  THE SECOND IMPLEMENTATION, and it is written to be different
        #  in shape rather than merely in language.  Where the native
        #  model carries two 64-bit halves and has to decide which one a
        #  lane lands in, this holds one arbitrary-precision integer per
        #  register and slices it; where that one has to detect a 64-bit
        #  overflow from the operands because the host has no wider type,
        #  this computes the full-width answer and clamps it.  Those are
        #  exactly the places a shared mistake would hide, which is the
        #  lesson of forum 633.
        if (ins & 0x9F200400) == 0x0E200400:
            q, u = (ins >> 30) & 1, (ins >> 29) & 1
            size, opc = (ins >> 22) & 3, (ins >> 11) & 31
            rm, rn, rd = (ins >> 16) & 31, (ins >> 5) & 31, ins & 31
            if opc >= 0b11000:
                # ---- THE FLOATING-POINT HALF. It EXECUTES since
                #      2026-09-05, through the exact-rational core.
                #
                #  BITS 23:22 ARE a:sz AND NOT AN ELEMENT WIDTH. The low
                #  bit is the precision; the HIGH bit belongs to the
                #  operation and is what tells FADD from FSUB and FMAX
                #  from FMIN. Read as a width it does not widen an
                #  instruction, it runs a different one.
                import a64_f32_gate as f32
                fa, fsz = (size >> 1) & 1, size & 1
                if fsz:
                    raise RuntimeError(
                        f"Advanced SIMD word {ins:08x} is a "
                        "DOUBLE-PRECISION vector operation (the .2D "
                        "arrangement). This interpreter implements "
                        "binary32 exactly and refuses binary64: there is "
                        "no caller for it on this target and an "
                        "approximation would be worse than a refusal.")
                key = (fa, u, opc)
                if key in ((0, 0, 0b11011), (0, 0, 0b11111), (1, 0, 0b11111)):
                    raise RuntimeError(
                        f"Advanced SIMD word {ins:08x} is FMULX, FRECPS or "
                        f"FRSQRTS (a={fa} U={u} opcode={opc:05b}). This "
                        "interpreter deliberately does not implement it, "
                        "together with the two estimates FRECPE and "
                        "FRSQRTE it exists to refine. The estimates have "
                        "IMPLEMENTATION-DEFINED precision - the "
                        "architecture states a bound, not a value - so "
                        "what this part returns is a measurement. The "
                        "silicon phase reads it and all five land "
                        "together.")
                # The pairwise five read Vn:Vm as ONE long vector. Named
                # one by one: FABD shares FADDP's opcode with the other
                # `a` bit and is not pairwise.
                fpair = key in ((0, 1, 0b11000), (0, 1, 0b11010),
                                (0, 1, 0b11110), (1, 1, 0b11000),
                                (1, 1, 0b11110))
                lanes = 2 << q
                out = 0
                for lane in range(lanes):
                    if fpair:
                        src = rn if lane < lanes // 2 else rm
                        idx = (lane if lane < lanes // 2
                               else lane - lanes // 2) * 2
                        x = self.velem(src, 2, idx)
                        y = self.velem(src, 2, idx + 1)
                    else:
                        x, y = self.velem(rn, 2, lane), self.velem(rm, 2, lane)
                    if   key == (0, 0, 0b11000): r = fp_minmax(f32, x, y, True, True)
                    elif key == (1, 0, 0b11000): r = fp_minmax(f32, x, y, False, True)
                    elif key == (0, 0, 0b11110): r = fp_minmax(f32, x, y, True, False)
                    elif key == (1, 0, 0b11110): r = fp_minmax(f32, x, y, False, False)
                    elif key == (0, 1, 0b11000): r = fp_minmax(f32, x, y, True, True)
                    elif key == (1, 1, 0b11000): r = fp_minmax(f32, x, y, False, True)
                    elif key == (0, 1, 0b11110): r = fp_minmax(f32, x, y, True, False)
                    elif key == (1, 1, 0b11110): r = fp_minmax(f32, x, y, False, False)
                    elif key == (0, 0, 0b11010): r = f32.f_add(x, y)
                    elif key == (1, 0, 0b11010): r = f32.f_sub(x, y)
                    elif key == (0, 1, 0b11010): r = f32.f_add(x, y)
                    elif key == (1, 1, 0b11010): r = fp_abd(f32, x, y)
                    elif key == (0, 1, 0b11011): r = f32.f_mul(x, y)
                    elif key == (0, 1, 0b11111): r = f32.f_div(x, y)
                    elif key == (0, 0, 0b11001):                      # FMLA
                        r = fp_muladd(f32, self.velem(rd, 2, lane), x, y)
                    elif key == (1, 0, 0b11001):                      # FMLS
                        # The architecture negates OPERAND ONE and then
                        # fuses; on a NaN that is not the same as
                        # negating the product afterwards.
                        r = fp_muladd(f32, self.velem(rd, 2, lane),
                                      x ^ 0x80000000, y)
                    # The compares write a MASK, all ones or all zeros,
                    # and an unordered pair is false for every one of
                    # them - which is what makes GE different from
                    # "not less".
                    elif key == (0, 0, 0b11100):
                        r = 0xFFFFFFFF if f32.f_rel(4, x, y) else 0
                    elif key == (0, 1, 0b11100):
                        r = 0xFFFFFFFF if f32.f_rel(3, x, y) else 0
                    elif key == (1, 1, 0b11100):
                        r = 0xFFFFFFFF if f32.f_rel(2, x, y) else 0
                    elif key == (0, 1, 0b11101):
                        r = 0xFFFFFFFF if f32.f_rel(3, x & 0x7FFFFFFF,
                                                    y & 0x7FFFFFFF) else 0
                    elif key == (1, 1, 0b11101):
                        r = 0xFFFFFFFF if f32.f_rel(2, x & 0x7FFFFFFF,
                                                    y & 0x7FFFFFFF) else 0
                    else:
                        raise RuntimeError(
                            f"Advanced SIMD word {ins:08x} is in the "
                            f"three-same FLOATING-POINT group (a={fa} "
                            f"U={u} opcode={opc:05b}) but is not one of "
                            "the operations this interpreter implements. "
                            "It is named rather than passed over.")
                    out |= (r & 0xFFFFFFFF) << (lane * 32)
                self.vset(rd, out, q)
                return True
            if opc in (0b01001, 0b01010, 0b01011, 0b10110):
                which = ("a saturating doubling multiply" if opc == 0b10110
                         else "a saturating or rounding variable shift")
                raise RuntimeError(
                    f"Advanced SIMD word {ins:08x} is {which} (three-same "
                    f"U={u} opcode={opc:05b}). The assembler encodes it and "
                    "this interpreter deliberately does not execute it - its "
                    "rounding and saturation have corners a plausible "
                    "implementation gets wrong, and a plausible wrong number "
                    "is worse here than a stop.")
            # The bitwise eight: whole-register, no lanes, and the size
            # field selects the operation rather than an element width.
            if opc == 0b00011:
                a, b, d = self.vget(rn), self.vget(rm), self.vget(rd)
                full = (1 << 128) - 1
                if u == 0:
                    r = (a & b, a & (~b & full), a | b, a | (~b & full))[size]
                else:
                    if size == 0:   r = a ^ b
                    elif size == 1: r = (d & a) | ((~d & full) & b)          # BSL
                    elif size == 2: r = (d & (~b & full)) | (a & b)          # BIT
                    else:           r = (d & b) | (a & (~b & full))          # BIF
                self.vset(rd, r, q)
                return True

            bits = 8 << size
            lanes = (8 << q) // (1 << size)
            mask = (1 << bits) - 1
            smin, smax_ = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
            pair = opc in (0b10100, 0b10101, 0b10111)
            out = 0
            for lane in range(lanes):
                if pair:
                    # The pairwise forms read Vn:Vm as ONE long vector.
                    src = rn if lane < lanes // 2 else rm
                    idx = (lane if lane < lanes // 2 else lane - lanes // 2) * 2
                    au, bu = self.velem(src, size, idx), self.velem(src, size, idx + 1)
                else:
                    au, bu = self.velem(rn, size, lane), self.velem(rm, size, lane)
                a, b = sx(au, bits), sx(bu, bits)
                key = (u, opc)
                if   key == (0, 0b00000): r = (a + b) >> 1                    # SHADD
                elif key == (1, 0b00000): r = (au + bu) >> 1                  # UHADD
                elif key == (0, 0b00010): r = (a + b + 1) >> 1                # SRHADD
                elif key == (1, 0b00010): r = (au + bu + 1) >> 1              # URHADD
                elif key == (0, 0b00100): r = (a - b) >> 1                    # SHSUB
                elif key == (1, 0b00100): r = (au - bu) >> 1                  # UHSUB
                elif key == (0, 0b00001): r = min(max(a + b, smin), smax_)    # SQADD
                elif key == (1, 0b00001): r = min(au + bu, mask)              # UQADD
                elif key == (0, 0b00101): r = min(max(a - b, smin), smax_)    # SQSUB
                elif key == (1, 0b00101): r = max(au - bu, 0)                 # UQSUB
                elif key == (0, 0b00110): r = mask if a > b else 0            # CMGT
                elif key == (1, 0b00110): r = mask if au > bu else 0          # CMHI
                elif key == (0, 0b00111): r = mask if a >= b else 0           # CMGE
                elif key == (1, 0b00111): r = mask if au >= bu else 0         # CMHS
                elif key == (0, 0b01000):                                     # SSHL
                    sh = sx(bu & 0xFF, 8)
                    r = (a << sh) if sh >= 0 else (a >> min(-sh, bits))
                elif key == (1, 0b01000):                                     # USHL
                    sh = sx(bu & 0xFF, 8)
                    r = (au << sh) if sh >= 0 else (au >> -sh if -sh < bits else 0)
                elif key == (0, 0b01100): r = max(a, b)                       # SMAX
                elif key == (1, 0b01100): r = max(au, bu)                     # UMAX
                elif key == (0, 0b01101): r = min(a, b)                       # SMIN
                elif key == (1, 0b01101): r = min(au, bu)                     # UMIN
                elif key == (0, 0b01110): r = abs(a - b)                      # SABD
                elif key == (1, 0b01110): r = abs(au - bu)                    # UABD
                elif key == (0, 0b01111): r = abs(a - b) + self.velem(rd, size, lane)   # SABA
                elif key == (1, 0b01111): r = abs(au - bu) + self.velem(rd, size, lane) # UABA
                elif key == (0, 0b10000): r = a + b                           # ADD
                elif key == (1, 0b10000): r = a - b                           # SUB
                elif key == (0, 0b10001): r = mask if (au & bu) else 0        # CMTST
                elif key == (1, 0b10001): r = mask if au == bu else 0         # CMEQ
                elif key == (0, 0b10010): r = self.velem(rd, size, lane) + a * b  # MLA
                elif key == (1, 0b10010): r = self.velem(rd, size, lane) - a * b  # MLS
                elif key == (0, 0b10011): r = a * b                           # MUL
                elif key == (1, 0b10011):                                     # PMUL
                    r = 0
                    for bit in range(8):
                        if (bu >> bit) & 1:
                            r ^= (au & 0xFF) << bit
                elif key == (0, 0b10100): r = max(a, b)                       # SMAXP
                elif key == (1, 0b10100): r = max(au, bu)                     # UMAXP
                elif key == (0, 0b10101): r = min(a, b)                       # SMINP
                elif key == (1, 0b10101): r = min(au, bu)                     # UMINP
                elif key == (0, 0b10111): r = a + b                           # ADDP
                else:
                    return False
                out |= (r & mask) << (lane * bits)
            self.vset(rd, out, q)
            return True

        # ---- FAMILY B and C: two-register misc, and across lanes -----
        if (ins & 0x9F3E0C00) in (0x0E200800, 0x0E300800):
            across = (ins & 0x9F3E0C00) == 0x0E300800
            q, u = (ins >> 30) & 1, (ins >> 29) & 1
            size, opc = (ins >> 22) & 3, (ins >> 12) & 31
            rn, rd = (ins >> 5) & 31, ins & 31
            bits = 8 << size
            lanes = (8 << q) // (1 << size)
            mask = (1 << bits) - 1

            if across:
                if opc == 0b00011:                                  # SADDLV/UADDLV
                    total = sum(self.velem(rn, size, i) if u
                                else sx(self.velem(rn, size, i), bits)
                                for i in range(lanes))
                    self.vset(rd, total & ((1 << (bits * 2)) - 1), 0)
                    return True
                if opc == 0b11011 and u == 0:                       # ADDV
                    total = sum(self.velem(rn, size, i) for i in range(lanes))
                    self.vset(rd, total & mask, 0)
                    return True
                if opc in (0b01010, 0b11010):                       # S/U MAXV/MINV
                    vals = [self.velem(rn, size, i) if u
                            else sx(self.velem(rn, size, i), bits)
                            for i in range(lanes)]
                    best = min(vals) if (opc & 0b10000) else max(vals)
                    self.vset(rd, best & mask, 0)
                    return True
                return False

            # THE FLOATING-POINT HALF. Opcode 11xxx is the rounding and
            # conversion family; 011xx (which always carries the high
            # size bit set) is the compares against zero, FABS and FNEG.
            # It EXECUTES since 2026-09-05.
            if opc >= 0b11000 or 0b01100 <= opc <= 0b01111:
                import a64_f32_gate as f32
                fa, fsz = (size >> 1) & 1, size & 1
                if fsz:
                    raise RuntimeError(
                        f"Advanced SIMD word {ins:08x} is a "
                        "DOUBLE-PRECISION vector operation (the .2D "
                        "arrangement). This interpreter implements "
                        "binary32 exactly and refuses binary64.")
                key = (fa, u, opc)
                if key in ((1, 0, 0b11101), (1, 1, 0b11101)):
                    raise RuntimeError(
                        f"Advanced SIMD word {ins:08x} is FRECPE or "
                        f"FRSQRTE (a={fa} U={u} opcode={opc:05b}). This "
                        "interpreter deliberately does not implement it: "
                        "the reciprocal and reciprocal square-root "
                        "ESTIMATES have IMPLEMENTATION-DEFINED precision, "
                        "so what this part returns is a measurement and "
                        "not a derivation. FMULX, FRECPS and FRSQRTS wait "
                        "with them for the silicon phase.")
                MODE = {(0, 0, 0b11000): 'n', (0, 0, 0b11001): 'm',
                        (1, 0, 0b11000): 'p', (1, 0, 0b11001): 'z',
                        (0, 1, 0b11000): 'a',
                        # FRINTX and FRINTI differ from FRINTN only in
                        # what they raise and in reading FPCR.RMode, and
                        # FPCR is zero here.
                        (0, 1, 0b11001): 'n', (1, 1, 0b11001): 'n'}
                CVT = {(0, 0, 0b11010): (True, 'n'), (0, 0, 0b11011): (True, 'm'),
                       (0, 0, 0b11100): (True, 'a'), (1, 0, 0b11010): (True, 'p'),
                       (1, 0, 0b11011): (True, 'z'), (0, 1, 0b11010): (False, 'n'),
                       (0, 1, 0b11011): (False, 'm'), (0, 1, 0b11100): (False, 'a'),
                       (1, 1, 0b11010): (False, 'p'), (1, 1, 0b11011): (False, 'z')}
                lanes = 2 << q
                out = 0
                for lane in range(lanes):
                    x = self.velem(rn, 2, lane)
                    if key in MODE:
                        r = fp_rint(f32, x, MODE[key])
                    elif key in CVT:
                        signed, mode = CVT[key]
                        r = fp_to_int(f32, x, signed, 32, mode)
                    elif key == (0, 0, 0b11101):                      # SCVTF
                        r = fp_from_int(f32, sx(x, 32), True, 32)
                    elif key == (0, 1, 0b11101):                      # UCVTF
                        r = fp_from_int(f32, x, False, 32)
                    elif key == (1, 1, 0b11111): r = fp_sqrt(f32, x)  # FSQRT
                    # FABS and FNEG are BIT operations: a NaN keeps its
                    # payload and -(+0) is -0.
                    elif key == (1, 0, 0b01111): r = x & 0x7FFFFFFF
                    elif key == (1, 1, 0b01111): r = x ^ 0x80000000
                    elif key == (1, 0, 0b01100):
                        r = 0xFFFFFFFF if f32.f_rel(2, x, 0) else 0   # FCMGT #0
                    elif key == (1, 0, 0b01101):
                        r = 0xFFFFFFFF if f32.f_rel(4, x, 0) else 0   # FCMEQ #0
                    elif key == (1, 0, 0b01110):
                        r = 0xFFFFFFFF if f32.f_rel(0, x, 0) else 0   # FCMLT #0
                    elif key == (1, 1, 0b01100):
                        r = 0xFFFFFFFF if f32.f_rel(3, x, 0) else 0   # FCMGE #0
                    elif key == (1, 1, 0b01101):
                        r = 0xFFFFFFFF if f32.f_rel(1, x, 0) else 0   # FCMLE #0
                    else:
                        raise RuntimeError(
                            f"Advanced SIMD word {ins:08x} is in the "
                            f"two-register FLOATING-POINT group (a={fa} "
                            f"U={u} opcode={opc:05b}) but is not one of "
                            "the operations this interpreter implements. "
                            "It is named rather than passed over.")
                    out |= (r & 0xFFFFFFFF) << (lane * 32)
                self.vset(rd, out, q)
                return True

            if opc in (0b00111, 0b00011, 0b10100) or (u == 1 and opc == 0b10010):
                raise RuntimeError(
                    f"Advanced SIMD word {ins:08x} is a saturating two-register "
                    f"operation (U={u} opcode={opc:05b}). The assembler encodes "
                    "it and this interpreter deliberately does not execute it.")

            if opc == 0b00101 and u == 1:
                full = (1 << 128) - 1
                if size == 0:                                       # NOT
                    self.vset(rd, (~self.vget(rn)) & full, q)
                    return True
                if size == 1:                                       # RBIT, per byte
                    out = 0
                    for i in range(8 << q):
                        v = self.velem(rn, 0, i)
                        out |= int(f"{v:08b}"[::-1], 2) << (i * 8)
                    self.vset(rd, out, q)
                    return True
                return False

            if u == 0 and opc == 0b10010:                           # XTN / XTN2
                narrow = 8 // (1 << size)
                out = 0
                for i in range(narrow):
                    out |= (self.velem(rn, size + 1, i) & mask) << (i * bits)
                if q:
                    # XTN2 preserves the lower half; vset would zero it.
                    self.v[rd] = (self.vget(rd) & ((1 << 64) - 1)) | (out << 64)
                else:
                    self.vset(rd, out, 0)
                return True

            if u == 1 and opc == 0b10011:                           # SHLL / SHLL2
                base = (8 // (1 << size)) if q else 0
                out = 0
                for i in range(8 // (1 << size)):
                    out |= (self.velem(rn, size, base + i) << bits) << (i * bits * 2)
                self.vset(rd, out, 1)
                return True

            if opc in (0b00010, 0b00110):                # SADDLP/UADDLP/SADALP/UADALP
                acc = opc == 0b00110
                wide = bits * 2
                wmask = (1 << wide) - 1
                out = 0
                for i in range((8 << q) // (1 << (size + 1))):
                    if u:
                        r = self.velem(rn, size, i * 2) + self.velem(rn, size, i * 2 + 1)
                    else:
                        r = (sx(self.velem(rn, size, i * 2), bits)
                             + sx(self.velem(rn, size, i * 2 + 1), bits))
                    if acc:
                        r += self.velem(rd, size + 1, i)
                    out |= (r & wmask) << (i * wide)
                self.vset(rd, out, q)
                return True

            out = 0
            for lane in range(lanes):
                vu = self.velem(rn, size, lane)
                v = sx(vu, bits)
                key = (u, opc)
                if key == (0, 0b00000):                              # REV64
                    group = 8 // (1 << size)
                    r = self.velem(rn, size,
                                   (lane // group) * group + (group - 1 - lane % group))
                elif key == (1, 0b00000):                            # REV32
                    group = 4 // (1 << size)
                    r = self.velem(rn, size,
                                   (lane // group) * group + (group - 1 - lane % group))
                elif key == (0, 0b00001):                            # REV16
                    r = self.velem(rn, size, lane ^ 1)
                elif key == (0, 0b00100):                            # CLS
                    top = (vu >> (bits - 1)) & 1
                    r = 0
                    for bit in range(bits - 2, -1, -1):
                        if ((vu >> bit) & 1) != top:
                            break
                        r += 1
                elif key == (1, 0b00100):                            # CLZ
                    r = bits - vu.bit_length()
                elif key == (0, 0b00101):                            # CNT
                    r = bin(vu & 0xFF).count("1")
                elif key == (0, 0b01000): r = mask if v > 0 else 0   # CMGT #0
                elif key == (1, 0b01000): r = mask if v >= 0 else 0  # CMGE #0
                elif key == (0, 0b01001): r = mask if v == 0 else 0  # CMEQ #0
                elif key == (1, 0b01001): r = mask if v <= 0 else 0  # CMLE #0
                elif key == (0, 0b01010): r = mask if v < 0 else 0   # CMLT #0
                elif key == (0, 0b01011): r = abs(v)                 # ABS
                elif key == (1, 0b01011): r = -v                     # NEG
                else:
                    return False
                out |= (r & mask) << (lane * bits)
            self.vset(rd, out, q)
            return True

        # ---- FAMILY D: Advanced SIMD shift by immediate ---------------
        #      0 Q U(29) 011110 immh(22:19) immb(18:16) opcode(15:11) 1 Rn Rd
        #
        #  immh != 0000 is part of the DECODE: with it zero the word is
        #  MOVI, decoded below off the same base.  The element width is
        #  the position of immh's highest set bit and the shift amount is
        #  the rest of the same seven-bit number, so nothing here can be
        #  read as a "size field" without reading the amount into it.
        #
        #  WHERE THIS DIFFERS IN SHAPE from the native model, which is
        #  the whole point of a second implementation: this slices one
        #  arbitrary-precision integer per register and lets Python's own
        #  >> do the arithmetic on an already-signed value, where the
        #  native one carries two 64-bit halves, has to decide which half
        #  a lane lands in, and has to clamp a shift of 64 its host does
        #  not define.
        if (ins & 0x9F800400) == 0x0F000400 and ((ins >> 19) & 15) != 0:
            q, u = (ins >> 30) & 1, (ins >> 29) & 1
            immhb = (ins >> 16) & 0x7F
            opc = (ins >> 11) & 31
            rn, rd = (ins >> 5) & 31, ins & 31
            size = (immhb >> 3).bit_length() - 1
            bits = 8 << size
            mask = (1 << bits) - 1
            if opc >= 0b11000:
                return False                     # fixed-point FP: not modelled
            which = ""
            if opc in (0b00100, 0b00110):
                which = "a rounding shift right by immediate"
            elif opc in (0b01100, 0b01110):
                which = "a saturating shift left by immediate"
            elif 0b10000 <= opc <= 0b10011 and not (u == 0 and opc == 0b10000):
                which = "a saturating or rounding narrowing shift"
            if which:
                raise RuntimeError(
                    f"Advanced SIMD word {ins:08x} is {which} "
                    f"(shift-by-immediate U={u} opcode={opc:05b}). The "
                    "assembler encodes it and this interpreter deliberately "
                    "does not execute it - its rounding and saturation have "
                    "corners a plausible implementation gets wrong, and a "
                    "plausible wrong number is worse here than a stop.")

            if opc == 0b10100:                   # SSHLL / USHLL (and SXTL/UXTL)
                amount = immhb - bits
                dbits = bits * 2
                elements = 64 // bits
                out = 0
                for lane in range(elements):
                    src = self.velem(rn, size, q * elements + lane)
                    val = (sx(src, bits) if u == 0 else src) << amount
                    out |= (val & ((1 << dbits) - 1)) << (lane * dbits)
                self.vset(rd, out, 1)
                return True

            if opc == 0b10000:                   # SHRN / SHRN2
                amount = 2 * bits - immhb
                elements = 64 // bits
                out = 0
                for lane in range(elements):
                    src = self.velem(rn, size + 1, lane)
                    out |= ((src >> amount) & mask) << (lane * bits)
                if q:
                    self.v[rd] = (self.vget(rd) & MASK64) | (out << 64)
                else:
                    self.vset(rd, out, 0)
                return True

            left = opc == 0b01010
            amount = (immhb - bits) if left else (2 * bits - immhb)
            lanes = (8 << q) // (1 << size)
            out = 0
            for lane in range(lanes):
                au = self.velem(rn, size, lane)
                a = sx(au, bits)
                d = self.velem(rd, size, lane)
                key = (u, opc)
                if   key == (0, 0b00000): r = a >> amount                     # SSHR
                elif key == (1, 0b00000): r = au >> amount                    # USHR
                elif key == (0, 0b00010): r = d + (a >> amount)               # SSRA
                elif key == (1, 0b00010): r = d + (au >> amount)              # USRA
                elif key == (0, 0b01010): r = au << amount                    # SHL
                elif key == (1, 0b01010):                                     # SLI
                    r = (au << amount) | (d & ((1 << amount) - 1))
                elif key == (1, 0b01000):                                     # SRI
                    r = (au >> amount) | (d & ~(mask >> amount))
                else:
                    return False
                out |= (r & mask) << (lane * bits)
            self.vset(rd, out, q)
            return True

        # ---- FAMILY E: Advanced SIMD three different ------------------
        #      0 Q U(29) 01110 size(23:22) 1 Rm(20:16) opcode(15:12) 00 Rn Rd
        #  BITS 11:10 ARE WHAT SEPARATE THIS FROM THREE-SAME, which has
        #  bit 10 set and a five-bit opcode.  Both masks pin them.
        if (ins & 0x9F200C00) == 0x0E200000:
            q, u = (ins >> 30) & 1, (ins >> 29) & 1
            size, opc = (ins >> 22) & 3, (ins >> 12) & 15
            rm, rn, rd = (ins >> 16) & 31, (ins >> 5) & 31, ins & 31
            if size == 3:
                return False                     # RESERVED for all of these
            if opc in (0b1001, 0b1011, 0b1101) or (u == 1 and opc in (0b0100, 0b0110)):
                raise RuntimeError(
                    f"Advanced SIMD word {ins:08x} is a saturating doubling or "
                    f"rounding narrowing three-different operation (U={u} "
                    f"opcode={opc:04b}). The assembler encodes it and this "
                    "interpreter deliberately does not execute it - the "
                    "doubling has its own case for the most negative element "
                    "and the rounding form rounds the bits it discards.")
            bits = 8 << size                     # the NARROW element
            wide = bits * 2
            elements = 64 // bits
            mask, wmask = (1 << bits) - 1, (1 << wide) - 1

            if opc in (0b0100, 0b0110):          # ADDHN / SUBHN
                out = 0
                for lane in range(elements):
                    a = self.velem(rn, size + 1, lane)
                    b = self.velem(rm, size + 1, lane)
                    total = (a + b) if opc == 0b0100 else (a - b)
                    out |= (((total & wmask) >> bits) & mask) << (lane * bits)
                if q:
                    self.v[rd] = (self.vget(rd) & MASK64) | (out << 64)
                else:
                    self.vset(rd, out, 0)
                return True

            out = 0
            for lane in range(elements):
                if opc in (0b0001, 0b0011):      # SADDW / SSUBW and friends
                    au = self.velem(rn, size + 1, lane)
                    a = sx(au, wide)
                else:
                    au = self.velem(rn, size, q * elements + lane)
                    a = sx(au, bits)
                bu = self.velem(rm, size, q * elements + lane)
                b = sx(bu, bits)
                d = self.velem(rd, size + 1, lane)
                key = (u, opc)
                if   key == (0, 0b0000): r = a + b                            # SADDL
                elif key == (1, 0b0000): r = au + bu                          # UADDL
                elif key == (0, 0b0001): r = a + b                            # SADDW
                elif key == (1, 0b0001): r = au + bu                          # UADDW
                elif key == (0, 0b0010): r = a - b                            # SSUBL
                elif key == (1, 0b0010): r = au - bu                          # USUBL
                elif key == (0, 0b0011): r = a - b                            # SSUBW
                elif key == (1, 0b0011): r = au - bu                          # USUBW
                elif key == (0, 0b0101): r = d + abs(a - b)                   # SABAL
                elif key == (1, 0b0101): r = d + abs(au - bu)                 # UABAL
                elif key == (0, 0b0111): r = abs(a - b)                       # SABDL
                elif key == (1, 0b0111): r = abs(au - bu)                     # UABDL
                elif key == (0, 0b1000): r = d + a * b                        # SMLAL
                elif key == (1, 0b1000): r = d + au * bu                      # UMLAL
                elif key == (0, 0b1010): r = d - a * b                        # SMLSL
                elif key == (1, 0b1010): r = d - au * bu                      # UMLSL
                elif key == (0, 0b1100): r = a * b                            # SMULL
                elif key == (1, 0b1100): r = au * bu                          # UMULL
                elif key == (0, 0b1110):                                      # PMULL, 8-bit
                    r = 0
                    for bit in range(8):
                        if (bu >> bit) & 1:
                            r ^= (au & 0xFF) << bit
                else:
                    return False
                out |= (r & wmask) << (lane * wide)
            self.vset(rd, out, 1)
            return True

        # ---- FAMILY F: Advanced SIMD permute --------------------------
        #      0 Q 001110 size(23:22) 0 Rm(20:16) 0 opcode(14:12) 10 Rn Rd
        #  Bit 21 is CLEAR here and SET in three-same, and that is the
        #  whole difference. Written as an explicit source-and-index pick
        #  per lane, where the native model builds two 64-bit halves - so
        #  a mistake about which half a lane lands in cannot be shared.
        if (ins & 0xBF208C00) == 0x0E000800:
            q = (ins >> 30) & 1
            size, opc = (ins >> 22) & 3, (ins >> 12) & 7
            rm, rn, rd = (ins >> 16) & 31, (ins >> 5) & 31, ins & 31
            if opc in (0b000, 0b100):
                return False                     # UNALLOCATED
            bits = 8 << size
            lanes_ = (8 << q) // (1 << size)
            part = opc >> 2
            out = 0
            for lane in range(lanes_):
                kind = opc & 0b011
                if kind == 0b001:                # UZP1 / UZP2
                    idx = lane * 2 + part
                    src, idx = (rn, idx) if idx < lanes_ else (rm, idx - lanes_)
                elif kind == 0b010:              # TRN1 / TRN2
                    idx = (lane & ~1) + part
                    src = rm if (lane & 1) else rn
                else:                            # ZIP1 / ZIP2
                    idx = (lane >> 1) + part * (lanes_ // 2)
                    src = rm if (lane & 1) else rn
                out |= self.velem(src, size, idx) << (lane * bits)
            self.vset(rd, out, q)
            return True

        # ---- FAMILY G: EXT --------------------------------------------
        #      0 Q 101110 00 0 Rm(20:16) 0 imm4(14:11) 0 Rn Rd
        #  Here the concatenation is a real arbitrary-precision integer
        #  and the extract is one shift, where the native model has to
        #  walk bytes because its host has no 128-bit type. Two shapes,
        #  one answer, which is the point of the second witness.
        if (ins & 0xBFE08400) == 0x2E000000:
            q = (ins >> 30) & 1
            rm, rn, rd = (ins >> 16) & 31, (ins >> 5) & 31, ins & 31
            index = (ins >> 11) & 15
            nbytes = 8 << q
            if q == 0 and (index & 8):
                raise RuntimeError(
                    f"Advanced SIMD word {ins:08x} is an EXT of a 64-bit "
                    "pair with bit 3 of its index set. The architecture "
                    "requires that bit to be zero on this form and prints "
                    "the encoding as reserved, so there is no defined "
                    "answer to give.")
            width = nbytes * 8
            low = self.vget(rn) & ((1 << width) - 1)
            high = self.vget(rm) & ((1 << width) - 1)
            joined = low | (high << width)
            self.vset(rd, (joined >> (index * 8)) & ((1 << width) - 1), q)
            return True

        # ---- FAMILY H: TBL / TBX --------------------------------------
        #      0 Q 001110 00 0 Rm(20:16) 0 len(14:13) op(12) 00 Rn Rd
        #  The table WRAPS PAST V31 - (n + i) mod 32 - so a table
        #  starting at v30 continues at v31, v0, v1. An index at or past
        #  the table gives zero for TBL and leaves the destination byte
        #  alone for TBX, which is the only difference between them.
        if (ins & 0xBFE08C00) == 0x0E000000:
            q = (ins >> 30) & 1
            rm, rn, rd = (ins >> 16) & 31, (ins >> 5) & 31, ins & 31
            length, op = ((ins >> 13) & 3) + 1, (ins >> 12) & 1
            nbytes = 8 << q
            table = b"".join(
                self.vget((rn + i) % 32).to_bytes(16, "little")
                for i in range(length))
            old = self.vget(rd)
            out = 0
            for byte in range(nbytes):
                index = self.velem(rm, 0, byte)
                if index < len(table):
                    value = table[index]
                elif op:
                    value = (old >> (byte * 8)) & 0xFF
                else:
                    value = 0
                out |= value << (byte * 8)
            self.vset(rd, out, q)
            return True

        # ---- MOVI / MVNI ---------------------------------------------
        if (ins & 0x9FF80C00) == 0x0F000400:
            q, op = (ins >> 30) & 1, (ins >> 29) & 1
            cmode = (ins >> 12) & 15
            imm8 = (((ins >> 16) & 7) << 5) | ((ins >> 5) & 31)
            rd = ins & 31
            val = self.advsimd_expand_imm(op, cmode, imm8)
            if op == 1 and cmode != 0b1110:
                val = (~val) & MASK64
            self.vset(rd, val | (val << 64), q)
            return True

        return False

    def run(self, limit: int = 10000) -> None:
        for _ in range(limit):
            if self.halted:
                return
            self.step()
        raise RuntimeError("A64 interpreter step limit exceeded")


# ======================================================================
#  binary32, through the exact-rational core - see the note at the
#  scalar floating-point arm for why that core is imported rather than
#  copied.  These five fill the gaps the core does not carry: it was
#  written for the four arithmetic operations and the relations.
# ======================================================================
def fp_minmax(f32, a, b, want_max, number_form):
    ka = f32.unpack(a)[1]
    kb = f32.unpack(b)[1]
    if number_form:
        if ka == 'snan' or kb == 'snan':
            return f32.process_nans(a, b)
        if ka == 'qnan' and kb == 'qnan':
            return a & 0xFFFFFFFF
        if ka == 'qnan':
            return b & 0xFFFFFFFF
        if kb == 'qnan':
            return a & 0xFFFFFFFF
    else:
        n = f32.process_nans(a, b)
        if n is not None:
            return n
    # +0 and -0 compare EQUAL, so a plain comparison never produces the
    # architecture's answer here: the maximum of the two is +0 and the
    # minimum is -0.
    if ka == 'zero' and kb == 'zero':
        sa, sb = (a >> 31) & 1, (b >> 31) & 1
        if want_max:
            return 0 if (sa == 0 or sb == 0) else 0x80000000
        return 0x80000000 if (sa == 1 or sb == 1) else 0
    a_less = bool(f32.f_rel(0, a, b))
    if want_max:
        return (b if a_less else a) & 0xFFFFFFFF
    return (a if a_less else b) & 0xFFFFFFFF


def fp_muladd(f32, d, a, b):
    """FPMulAdd: d + a*b with ONE rounding.

    THE SHAPE DIFFERENCE FROM THE NATIVE MODEL IS THE WHOLE POINT.  That
    one has a 48-bit product and a 24-bit addend and no host type wider
    than 64 bits, so it aligns them in a two-limb 97-bit accumulator and
    has to take the two "one operand is below half an ulp of the other"
    cases first to keep the shift in range - and the FIRST version of it
    shifted out of range, went negative, and HUNG for 451 seconds.  Here
    the product and the addend are exact Fractions and their sum is
    exact: no alignment, no accumulator, no width to get wrong.  Two
    implementations of one algorithm are one witness.  These are two
    algorithms.
    """
    n = f32.process_nans(a, b)
    if n is None:
        n = f32.process_nans(d, d)
    if n is not None:
        return n
    sa, ka, va = f32.unpack(a)
    sb, kb, vb = f32.unpack(b)
    sd, kd, vd = f32.unpack(d)
    sp = sa ^ sb
    if (ka == 'inf' and kb == 'zero') or (ka == 'zero' and kb == 'inf'):
        return f32.DEFAULT_NAN
    if ka == 'inf' or kb == 'inf':
        if kd == 'inf' and sp != sd:
            return f32.DEFAULT_NAN
        return (sp << 31) | 0x7F800000
    if kd == 'inf':
        return d & 0xFFFFFFFF
    if ka == 'zero' or kb == 'zero':
        if kd == 'zero':
            # Two zeros: a sign survives only when they agree.
            return (sp << 31) if sp == sd else 0
        return d & 0xFFFFFFFF
    if kd == 'zero':
        return f32.pack(sp, va * vb)
    total = (-(va * vb) if sp else (va * vb)) + (-vd if sd else vd)
    if total == 0:
        return 0                        # exact cancellation is +0
    return f32.pack(1 if total < 0 else 0, abs(total))


def fp_abd(f32, a, b):
    """|a - b|, which is neither abs(a) - abs(b) nor the absolute value
    of anything computed some other way: the subtraction rounds once and
    the sign bit is then cleared.  A NaN keeps its payload."""
    r = f32.f_sub(a, b)
    if f32.is_nan(r):
        return r
    return r & 0x7FFFFFFF


def _round_mag(val, mode, negative):
    """Round a non-negative exact rational to an integer under one of the
    architecture's five modes.  `negative` is the sign of the VALUE, which
    is what makes toward-plus and toward-minus differ."""
    from fractions import Fraction
    whole = val.numerator // val.denominator
    frac = val - whole
    if mode == 'z':
        return whole
    if mode == 'n':
        if frac > Fraction(1, 2) or (frac == Fraction(1, 2) and whole % 2 == 1):
            return whole + 1
        return whole
    if mode == 'a':
        return whole + 1 if frac >= Fraction(1, 2) else whole
    if mode == 'p':
        return whole if negative else (whole + 1 if frac > 0 else whole)
    return (whole + 1 if frac > 0 else whole) if negative else whole


def fp_rint(f32, bits, mode):
    n = f32.process_nans(bits, bits)
    if n is not None:
        return n
    from fractions import Fraction
    s, kind, val = f32.unpack(bits)
    if kind in ('zero', 'inf'):
        return bits & 0xFFFFFFFF
    mag = _round_mag(val, mode, s == 1)
    if mag == 0:
        return s << 31              # -0.4 rounds to MINUS zero
    return f32.pack(s, Fraction(mag))


def fp_to_int(f32, bits, signed, width, mode):
    s, kind, val = f32.unpack(bits)
    hi = (1 << (width - 1)) - 1 if signed else (1 << width) - 1
    lo = -(1 << (width - 1)) if signed else 0
    if kind in ('qnan', 'snan') or kind == 'zero':
        return 0                    # a NaN converts to ZERO, not to a rail
    if kind == 'inf':
        return lo if s else hi
    mag = _round_mag(val, mode, s == 1)
    r = -mag if s else mag
    return hi if r > hi else (lo if r < lo else r)


def fp_from_int(f32, n, signed, width):
    from fractions import Fraction
    if n == 0:
        return 0
    return f32.pack(1 if n < 0 else 0, Fraction(abs(n)))


def fp_sqrt(f32, bits):
    """The correctly rounded square root, by bisection on the ENCODING.
    Slow and obviously right, which is what a witness should be."""
    import math
    from fractions import Fraction
    n = f32.process_nans(bits, bits)
    if n is not None:
        return n
    s, kind, val = f32.unpack(bits)
    if kind == 'zero':
        return bits & 0xFFFFFFFF     # the sqrt of -0 is -0
    if s == 1:
        return f32.DEFAULT_NAN
    if kind == 'inf':
        return 0x7F800000
    SCALE = 1 << 200
    root = Fraction(math.isqrt(val.numerator * SCALE * SCALE // val.denominator), SCALE)
    return f32.pack(0, root)

def load_words(cpu: A64, words: Iterable[int], base: int = 0) -> None:
    # raw_store, not store: putting an image into memory is something the
    # HARNESS does, not something the program does, so it must not be able
    # to trip the program's alignment rule (or a gate's MMIO decoder).
    for index, word in enumerate(words):
        cpu.raw_store(base + index * 4, word, 4)


# ----------------------------------------------------------------------
# THE EXPECTED INITIAL STACK TOP, READ FROM THE ARTEFACT.
#
# Both A64 gates assert where sp finishes. That value used to be the
# literal 0x08000000, which was true only while the emitter hardcoded it.
# --stack-addr makes it a build-time choice, so a gate that keeps the
# constant would pass for the wrong reason on a default build and fail
# for the wrong reason on any other.
#
# The listing states it - "; Initial stack top $8000000", written by
# EmitASM_A64() next to the ".org" it already states - and both gates are
# already built with -S, so the file is there. Lives HERE, imported by
# both gates, because two copies of a parser is how the hardcoded end
# trap came to be hardcoded in two places.
STACK_TOP_RE = re.compile(r"^;\s*Initial stack top \$([0-9A-Fa-f]+)\s*$", re.M)


def expected_stack_top(listing: "Path") -> int:
    text = Path(listing).read_text(encoding="utf-8-sig")
    found = STACK_TOP_RE.search(text)
    if not found:
        raise AssertionError(
            f"{listing} has no '; Initial stack top $...' header - the emitter "
            "must state it so this gate does not have to guess"
        )
    return int(found.group(1), 16)


def selftest() -> None:
    # Fixed words are independent of the project assembler.  The program
    # covers constant materialisation, register/immediate ALU, multiply,
    # signed divide, remainder via MSUB, memory widths, flags/conditional
    # branch, BL/RET, and the architectural zero-register behavior.
    words = [
        0x52800280,       # movz w0, #20
        0x528000C1,       # movz w1, #6
        0x0B010002,       # add  w2, w0, w1          = 26
        0x4B010043,       # sub  w3, w2, w1          = 20
        0x1B037C44,       # mul  w4, w2, w3          = 520
        0x1AC10C85,       # sdiv w5, w4, w1          = 86
        0x1B0190A6,       # msub w6, w5, w1, w4      = 4
        0xD2802009,       # movz x9, #0x100
        0xB9000126,       # str  w6, [x9]
        0xB940012A,       # ldr  w10,[x9]
        0x7100115F,       # cmp  w10,#4
        0x54000061,       # b.ne fail (+12)
        0x94000004,       # bl   function (+16)
        0x14000005,       # b    done (+20)
        0x52801FE0,       # fail: movz w0,#255
        0x14000003,       # b done
        0x11000400,       # function: add w0,w0,#1
        0xD65F03C0,       # ret
        0xD503201F,       # done: nop
    ]
    cpu = A64(sp=0x1000)
    load_words(cpu, words)
    for _ in range(18):
        cpu.step()
        if cpu.pc == 18 * 4:
            break
    assert cpu.x[0] == 21, cpu.x[0]
    assert cpu.x[2] == 26 and cpu.x[4] == 520
    assert cpu.x[5] == 86 and cpu.x[6] == 4
    assert cpu.load(0x100, 4) == 4

    # Hints, barriers and cache/TLB maintenance, added 2026-08-24. Fixed
    # words again, so this does not depend on the project assembler. Each
    # must advance the PC by four and change nothing else - the point of
    # the test is that none of them reaches the unsupported-word fault.
    maintenance = [
        0xD503207F,  # wfi
        0xD5033B9F,  # dsb ish
        0xD5033A9F,  # dsb ishst
        0xD503379F,  # dsb nsh
        0xD503339F,  # dsb osh
        0xD5033D9F,  # dsb ld
        0xD5033E9F,  # dsb st
        0xD5033BBF,  # dmb ish
        0xD5087620,  # dc ivac, x0
        0xD50B7A20,  # dc cvac, x0
        0xD50B7B20,  # dc cvau, x0
        0xD50B7E20,  # dc civac, x0
        0xD5087641,  # dc isw, x1
        0xD5087A41,  # dc csw, x1
        0xD5087E41,  # dc cisw, x1
        0xD508751F,  # ic iallu
        0xD508711F,  # ic ialluis
        0xD50B7520,  # ic ivau, x0
        0xD508871F,  # tlbi vmalle1
        0xD508831F,  # tlbi vmalle1is
        0xD50C871F,  # tlbi alle2
        0xD50C831F,  # tlbi alle2is
        0xD50E871F,  # tlbi alle3
        0xD50E831F,  # tlbi alle3is
    ]
    quiet = A64(pc=0x2000)
    load_words(quiet, maintenance, base=0x2000)
    before = list(quiet.x)
    for index in range(len(maintenance)):
        quiet.step()
        assert quiet.pc == 0x2000 + (index + 1) * 4, (index, hex(quiet.pc))
    assert quiet.x == before, "cache/TLB maintenance must not touch registers"

    # And a SYS word that is NOT one of them must still be refused loudly.
    # 0xD50B7420 is dc cvac's neighbour with CRm=4 - not an operation the
    # oracle models, so silence here would mean the oracle agrees with
    # anything. (DC ZVA is exactly that word; see the note in step().)
    reject = A64(pc=0x3000)
    load_words(reject, [0xD50B7420], base=0x3000)
    try:
        reject.step()
    except RuntimeError:
        pass
    else:
        raise AssertionError("unmodelled SYS word was accepted silently")

    # AT and the exception-generation five: DECODED, and REFUSED BY NAME.
    # 2026-09-04, forum 627 and 611. Two properties are being held here at
    # once and both matter: the model must not run them (an AT modelled as
    # a no-op leaves the last translation's answer in PAR_EL1; an SVC
    # modelled as a no-op pretends a handler returned), and the refusal
    # must SAY WHICH INSTRUCTION it was, because before this change both
    # families reached a generic "unsupported A64 word" that named a hex
    # number and sent the reader to the assembler.
    for word, wanted in (
        (0xD5087800, "at s1e1r, x0"),    # op1=0 CRn=7 CRm=8 op2=0
        (0xD5087821, "at s1e1w, x1"),    # op2=1, Xt=x1
        (0xD5087840, "at s1e0r, x0"),
        (0xD5087860, "at s1e0w, x0"),
        (0xD50C7800, "at s1e2r, x0"),
        (0xD50C7820, "at s1e2w, x0"),
        (0xD50C7880, "at s12e1r, x0"),
        (0xD50C78A0, "at s12e1w, x0"),
        (0xD50E7800, "at s1e3r, x0"),
        (0xD50E7820, "at s1e3w, x0"),
        (0xD4000001, "svc #0"),
        (0xD4024681, "svc #4660"),       # imm16 = 0x1234, at bits 20:5
        (0xD4000002, "hvc #0"),
        (0xD4000003, "smc #0"),
        (0xD4200000, "brk #0"),
        (0xD4400000, "hlt #0"),
    ):
        refuse = A64(pc=0x4000)
        load_words(refuse, [word], base=0x4000)
        try:
            refuse.step()
        except RuntimeError as failure:
            assert wanted in str(failure), (hex(word), wanted, str(failure))
            assert "cannot execute" in str(failure), str(failure)
        else:
            raise AssertionError(
                "0x%08X (%s) was executed instead of refused" % (word, wanted)
            )

    # THE GENERIC TIMER'S COUNT, and the frequency that is still refused.
    # 2026-09-11. Before this, `mrs x0, cntpct_el0` reached the generic
    # unsupported-word fault, and the ten gates that meet it each carried
    # a private answer above step() - so the eleventh, which only needed a
    # timestamp, went red with a bare hex word for a reason nobody could
    # read. Four properties, and the fourth is the reason the first three
    # are safe to have: the frequency is NOT answered here.
    #
    #   movz x9,#0x200 ; mrs x0,cntpct_el0 ; nop ; nop ; mrs x1,cntpct_el0
    clock = A64(pc=0x7000)
    load_words(clock, [0xD2804009, 0xD53BE020, 0xD503201F, 0xD503201F,
                       0xD53BE021], base=0x7000)
    for _ in range(5):
        clock.step()
    #   1. It reads, into the register the encoding names.
    assert clock.x[0] == 2, clock.x[0]
    #   2. It only ever goes up, and
    #   3. the work between two reads is what it went up BY - a counter
    #      that moved only when read would call these two reads adjacent.
    assert clock.x[1] == 5, clock.x[1]
    assert clock.x[1] - clock.x[0] == 3
    #      The rate is the model's, and a gate that measures a deadline
    #      says what it is measuring in.
    fast = A64(pc=0x7000)
    fast.cntpct_per_instruction = 64
    load_words(fast, [0xD53BE020, 0xD503201F, 0xD53BE021], base=0x7000)
    for _ in range(3):
        fast.step()
    assert (fast.x[0], fast.x[1]) == (64, 192), (fast.x[0], fast.x[1])
    #      Rt = 31 is XZR here, not x31: the count is discarded, and no
    #      general register moves. (There are 31 of them; x[31] does not
    #      exist, which is the point.)
    zr = A64(pc=0x7000)
    load_words(zr, [0xD53BE03F], base=0x7000)
    quiet_before = list(zr.x)
    zr.step()
    assert zr.pc == 0x7004 and zr.x == quiet_before
    #   4. CNTFRQ_EL0 - the same quadruple with op2 0 - is REFUSED, and
    #      the refusal names the register and says who has to answer it.
    #      Its value is board data; see the note on `cntpct`.
    frequency = A64(pc=0x7000)
    load_words(frequency, [0xD53BE000], base=0x7000)
    try:
        frequency.step()
    except RuntimeError as failure:
        assert "mrs x0, S3_3_C14_C0_0" in str(failure), str(failure)
        assert "CNTFRQ_EL0" in str(failure) and "board data" in str(failure)
    else:
        raise AssertionError(
            "CNTFRQ_EL0 was answered. Its value is 54 MHz on one board and "
            "19.2 MHz on another, and a program divides by it - an invented "
            "default is a wrong duration reported as a measurement.")
    #      And the same naming for a write nobody models.
    write = A64(pc=0x7000)
    load_words(write, [0xD51BE021], base=0x7000)     # msr S3_3_C14_C0_1, x1
    try:
        write.step()
    except RuntimeError as failure:
        assert "msr S3_3_C14_C0_1, x1" in str(failure), str(failure)
    else:
        raise AssertionError("an unmodelled MSR was executed instead of refused")

    print("PASS: A64 interpreter fixed-word oracle (ALU, div/rem, memory, branch, call/return)")
    print("PASS: A64 interpreter cache/TLB maintenance decoded as no-ops")
    print("PASS: A64 interpreter refuses AT and SVC/HVC/SMC/BRK/HLT by name")
    print("PASS: A64 interpreter counts CNTPCT_EL0 and refuses CNTFRQ_EL0 by name")

    align_selftest()


def align_selftest() -> None:
    """The alignment rule, watched failing in every mode it has.

    Four gates in this project certified real bugs this week because
    nobody had ever seen their check go red.  So this does not merely
    assert that aligned accesses still work - it makes each behaviour
    fail on purpose and checks WHAT it said.
    """
    # str w1, [x0] at an address ending in 2 - the cyw43 defect exactly.
    #   movz x0, #0x1002 ; movz w1, #0x1234 ; str w1, [x0] ; ret
    words = [0xD2820040, 0x52824681, 0xB9000001, 0xD65F03C0]

    def fresh() -> A64:
        cpu = A64(sp=0x8000)
        load_words(cpu, words, base=0x1000)
        cpu.pc = 0x1000
        cpu.x[30] = 0xDEADBEE0
        return cpu

    # 1. It fires, and it names the STORE, not the word after it.
    cpu = fresh()
    try:
        for _ in range(4):
            cpu.step()
    except AlignmentFault as f:
        assert f.addr == 0x1002 and f.size == 4 and f.write, (f.addr, f.size)
        assert f.pc == 0x1008, (
            "the fault named $%X; the `str` is at $1008. Reporting pc+4 is "
            "the off-by-one this rule is supposed to have fixed." % f.pc)
        assert "2 past a 4-byte boundary" in str(f), str(f)
    else:
        raise AssertionError(
            "THE ALIGNMENT RULE DID NOT FIRE. This is the hole that cost a "
            "session on 2026-08-27; if this assertion is ever relaxed, "
            "eighteen gates go back to certifying payloads that cannot run.")

    # 2. A 4-byte read at the same address is refused too, and says read.
    cpu = fresh()
    try:
        cpu.load(0x1002, 4)
    except AlignmentFault as f:
        assert not f.write and "4-byte read" in str(f)
    else:
        raise AssertionError("an unaligned 4-byte LOAD was serviced")

    # 3. Bytes are always legal; aligned wides are always legal.
    cpu = fresh()
    cpu.store(0x2001, 0xAA, 1)
    cpu.store(0x2004, 0x11223344, 4)
    cpu.store(0x2008, 1 << 40, 8)
    cpu.store(0x2002, 0xBEEF, 2)
    assert cpu.load(0x2004, 4) == 0x11223344
    assert cpu.load(0x2008, 8) == 1 << 40
    assert cpu.load(0x2002, 2) == 0xBEEF

    # 4. Every width that can be misaligned, is caught.
    for size, addr in ((2, 0x3001), (4, 0x3002), (8, 0x3004)):
        cpu = fresh()
        try:
            cpu.store(addr, 0, size)
        except AlignmentFault:
            pass
        else:
            raise AssertionError("a %d-byte store at $%X was serviced"
                                 % (size, addr))

    # 5. THE REGIME SWITCH. With the MMU on and DRAM Normal, an unaligned
    #    DRAM access is architecturally legal - but the peripheral
    #    aperture is still Device and must still refuse. A relaxation
    #    that relaxed everything would be the original hole with a flag
    #    in front of it.
    cpu = fresh()
    cpu.mmu_enabled(True)
    cpu.store(0x4002, 0x11223344, 4)
    assert cpu.load(0x4002, 4) == 0x11223344
    try:
        cpu.store(DEVICE_FLOOR + 0x201002, 0x11223344, 4)
    except AlignmentFault:
        pass
    else:
        raise AssertionError(
            "mmu_on relaxed the rule inside the peripheral aperture. "
            "mmu.pi4 maps that Device in both regimes.")
    cpu.mmu_enabled(False)
    try:
        cpu.store(0x4002, 0, 4)
    except AlignmentFault:
        pass
    else:
        raise AssertionError("mmu_enabled(False) did not put the rule back")

    # 6. THE DELIVERY MODE, which a64_fault_check.py needs: the fault is
    #    handed to a callback instead of escaping, and the callback may
    #    raise something of its own.
    class Abort(Exception):
        pass

    seen: list = []

    def deliver(f: AlignmentFault) -> None:
        seen.append(f)
        raise Abort()

    cpu = fresh()
    cpu.on_align_fault = deliver
    try:
        cpu.store(0x5002, 0, 4)
    except Abort:
        pass
    else:
        raise AssertionError("on_align_fault did not get the fault")
    assert len(seen) == 1 and seen[0].addr == 0x5002

    #    ...and a callback that returns without raising lets the access
    #    proceed, which is what a model that RESUMES after the abort
    #    would want. Checked so the contract is stated, not inferred.
    cpu = fresh()
    cpu.on_align_fault = lambda f: seen.append(f)
    cpu.store(0x5002, 0x99, 4)
    assert len(seen) == 2

    # 7. Instruction fetch is exempt - Normal NC, not Device. Proven by
    #    running a program at an address that is 4-aligned but where the
    #    fetch would trip a rule applied blindly to every load. (A
    #    misaligned PC is a PC alignment fault, a different EC, and is
    #    not this rule's business.)
    cpu = fresh()
    cpu.align_check = True
    cpu.step()                       # the movz at $1000 - fetch, no fault
    assert cpu.pc == 0x1004

    # 8. raw_load / raw_store are observers and never fault.
    cpu = fresh()
    cpu.raw_store(0x6002, 0x11223344, 4)
    assert cpu.raw_load(0x6002, 4) == 0x11223344

    # 9. The symboliser names a procedure and a source line, and does not
    #    invent one it does not have.
    syms = DbgSymbols([(0x400000, "cyw43seteventmask", "cyw43.pi4 line 4762"),
                       (0x401000, "cyw43scanstart", "cyw43.pi4 line 5010")])
    assert syms.where(0x40014C) == \
        "$0040014C - cyw43seteventmask+332, cyw43.pi4 line 4762"
    assert "no symbol covers it" in syms.where(0x100)
    cpu = fresh()
    cpu.locate = syms.where
    cpu.this_instr = 0x40014C
    try:
        cpu.store(0x484EDA, 0, 4)
    except AlignmentFault as f:
        assert "cyw43seteventmask+332, cyw43.pi4 line 4762" in str(f), str(f)
    else:
        raise AssertionError("the symbolised fault did not fire")

    print("PASS: A64 alignment rule - fires on 2/4/8, exempts fetch and "
          "bytes,\n      switches with the MMU regime, delivers or refuses, "
          "and names\n      the procedure and source line")


if __name__ == "__main__":
    selftest()

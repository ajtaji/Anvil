#!/usr/bin/env python3
"""Offline gate for the Raspberry Pi 5 EL3 armstub, modelled on
tools/a64/a64_el3_check.py (the Pi 4 gate) - read that file's docstring
first, because everything it says about WHY this class of file is
dangerous applies here unchanged: RaspberryPi5/Board/armstub8-2712.asm is
loaded by closed firmware at address 0 on a board with no serial port and
no boot log until this stub itself opens one.

WHAT IS DIFFERENT FROM THE PI 4 GATE, AND WHY THIS FILE EXISTS SEPARATELY
--------------------------------------------------------------------------
  * The core number is MPIDR Aff1 (bits 15:8), not Aff0 - the A76 sets
    MPIDR.MT (armstub8-2712.asm:38-40). A core is therefore identified
    here by 0x81000000 | (core << 8), not by ORing the core into the low
    byte the way the Pi 4 gate does.
  * The A76 register set differs from the A72's (no L2CTLR_EL1, no
    CPUECTLR_EL1.SMPEN / ACTLR_EL3; instead CPUECTLR_EL1 and
    CLUSTERECTLR_EL1 on every core, plus the erratum-1946160 sequence).
  * The erratum writes the SAME THREE PHYSICAL REGISTERS three times in a
    row (selectors 3, 4, 5), so an interpreter whose system-register
    store is keyed by register - the only kind a64_interp.py offers - can
    only ever answer with the LAST group once a run has finished; the
    first two are already overwritten. THAT IS WHY PART B BELOW DECODES
    THE BUILT BYTES DIRECTLY rather than running the image and reading
    cpu.sysreg() back, which is what the Pi 4 gate does for its (single
    write, never repeated) registers. Part C, which only needs to know
    whether the LAST group's values are present, still executes and
    reads them back - a repeated overwrite of the same final answer is
    exactly what a single-slot store can tell apart from "never written".
  * The board has a real primary-core delay loop (100,000 iterations,
    armstub8-2712.asm:134-140, "early GPU firmware... need a little
    break"), so a run that reaches the branch takes on the order of
    200,000 steps, not the few hundred the Pi 4 stub needs. This
    interpreter answers that in well under a second; the step limits
    below are sized for it deliberately generously rather than tightly,
    because a limit that is merely "enough" turns into a red gate the
    day somebody adds one more instruction before the branch.
  * GICD_IGROUPR's word count comes from GICD_TYPER.ITLinesNumber, which
    this flat-memory model does not compute - there is no distributor
    behind the address, only whatever was last stored there. So GICD_TYPER
    is PRESET before every run, exactly as the task that produced this
    gate asked: 0x0000000A, so the stub's own arithmetic
    ((TYPER & 0x1F) + 1) computes 11 and writes 11 words. That preset is
    the one hook this gate installs; nothing here edits a64_interp.py.

WHAT THIS GATE FOUND ON ITS FIRST RUN (2026-09-26, fixed in the stub)
------------------------------------------------------------------------
  LOCAL_CONTROL is documented, in the stub's header and in the pinned TF-A
  source, as $107C280000. The first stub built it with

      movz x0, #0x0028, lsl #16
      movk x0, #0x107C, lsl #32

  which is 0x107C00280000 - the halfword split was wrong (correct:
  #0x7C28,lsl#16 / #0x0010,lsl#32). It passed a hand review of the
  disassembly. This gate decodes the ACTUAL bytes and asserts the
  DOCUMENTED address, so it went red instead of agreeing with whatever the
  stub computed. Keep every address check in that form.

WHAT THIS GATE CANNOT DO
--------------------------
  Same limits as the Pi 4 gate: no GIC model, no silicon consequence of a
  system-register write, and no opinion on whether the FIRMWARE accepts
  the file. Additionally: the erratum's SELECT/VALUE registers are
  implementation-defined (S3_6_C15_C8_0..3) and are answered here purely
  as a flat store, the same as every other system register - there is no
  claim that writing them does anything on real silicon, only that the
  image writes what it is documented to write.
"""

from __future__ import annotations

import argparse
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(os.environ.get("PMF_REPO")
            or Path(__file__).resolve().parents[2])
print("[gate] tree under test: %s" % ROOT, file=sys.stderr)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from a64_interp import A64  # noqa: E402
sys.path.insert(0, str(ROOT / "tools"))
from pmf_compiler import resolve_compiler as _pmf_resolve_compiler  # noqa: E402

STUB_SRC = "RaspberryPi5/Board/armstub8-2712.asm"

# ---------------------------------------------------------------------
#  THE LAYOUT - identical fixed block to the Pi 4 stub (the header of
#  armstub8-2712.asm says so and cites TF-A's own armstub8_header.S as
#  sharing it byte for byte with the Pi 4 stub).
# ---------------------------------------------------------------------
SPIN_CPU = (0xD8, 0xE0, 0xE8, 0xF0)
STUB_MAGIC_OFF = 0xF0
STUB_VERSION_OFF = 0xF4
DTB_PTR_OFF = 0xF8
KERNEL_ENTRY_OFF = 0xFC
FIXED_BLOCK_OFF = 0x100
STUB_MAGIC = 0x5AFE570B
PAD_TO = 256

# ---------------------------------------------------------------------
#  System registers, keyed by the WRITE base the interpreter's opt-in
#  store uses (base = 0xD5100000 | (op0-2)<<19 | op1<<16 | CRn<<12 |
#  CRm<<8 | op2<<5). Confirmed against the actual built bytes, not just
#  derived by hand - see the session that produced this file.
# ---------------------------------------------------------------------
MPIDR_EL1 = 0xD51800A0
MIDR_EL1 = 0xD5180000
CPUECTLR_EL1 = 0xD518F180        # S3_0_C15_C1_4
CLUSTERECTLR_EL1 = 0xD518F380    # S3_0_C15_C3_4
CNTFRQ_EL0 = 0xD51BE000
SCR_EL3 = 0xD51E1100
CPTR_EL3 = 0xD51E1140
SCTLR_EL2 = 0xD51C1000
SCTLR_EL3 = 0xD51E1000
ELR_EL3 = 0xD51E4020
SPSR_EL3 = 0xD51E4000

# The erratum's four registers, all S3_6_C15_C8_<op2>. Selector is op2=0;
# the three value registers are op2=1,2,3.
ERR_SELECT = 0xD51EF800
ERR_VAL1 = 0xD51EF820
ERR_VAL2 = 0xD51EF840
ERR_VAL3 = 0xD51EF860

ERET_WORD = 0xD69F03E0

# ---------------------------------------------------------------------
#  MMIO. All from armstub8-2712.asm's own header, cited to
#  TF-A/plat/rpi/rpi5/include/rpi_hw.h.
# ---------------------------------------------------------------------
LOCAL_CONTROL = 0x107C280000
LOCAL_PRESCALER = 0x107C280008
GIC_DISTB = 0x107FFF9000
GIC_CPUB = 0x107FFFA000
GICD_CTLR = GIC_DISTB
GICD_TYPER = GIC_DISTB + 0x004
GICD_IGROUPR = GIC_DISTB + 0x080
GICC_CTLR = GIC_CPUB
GICC_PMR = GIC_CPUB + 0x004
UART_DR = 0x107D001000
UART_FR = UART_DR + 0x18

# What Part B asserts, by decoding the built bytes rather than running
# them - see the module docstring for why. (name, write_base, want, why)
SYSREG_CHECKS = [
    ("cpuectlr_el1", CPUECTLR_EL1, 0x2000000960023000,
     "the A76's own reset-time control word, every core "
     "(TF-A plat_helpers.S:15-18,136-142)."),
    ("clusterectlr_el1", CLUSTERECTLR_EL1, 0x500,
     "cluster coherency control, every core (plat_helpers.S:136-142)."),
    ("cntfrq_el0", CNTFRQ_EL0, 54_000_000,
     "the architectural counter rate. A wrong value here makes every "
     "timeout built on it wrong by the same ratio, silently."),
    ("scr_el3", SCR_EL3, 0x5B3,
     "RW|HCE|SMD|RES1|RES1|NS plus IRQ routing to EL3, same as the Pi 4 "
     "stub and for the same reason: this stub does not eret either."),
    ("cptr_el3", CPTR_EL3, 0,
     "TFP clear, so floating point and SIMD work at EL3."),
    ("sctlr_el2", SCTLR_EL2, 0x30C50830,
     "all RES1: MMU/caches/alignment-checking/WXN off at EL2."),
    ("sctlr_el3", SCTLR_EL3, 0x30C50830,
     "the same RES1 pattern, for the level this stub actually stays at."),
]

MMIO_CHECKS = [
    (LOCAL_CONTROL, 0, "bit9 clear = increment by 1, bit8 clear = the "
     "54 MHz crystal (rpi5_bl31_setup.c:118-126)."),
    (LOCAL_PRESCALER, 0x80000000, "divide-by 1."),
    (GICC_CTLR, 0x1E7, "EnableGrp0|EnableGrp1|AckCtl, FIQEn clear - every "
     "core's banked CPU interface."),
    (GICC_PMR, 0xFF, "the widest priority mask."),
    (GICD_CTLR, 3, "EnableGrp0|EnableGrp1 in the Secure view - written by "
     "cores 1..3, transcribed from the stock stub as-is (see the Pi 4 "
     "gate's note on the same asymmetry)."),
]

# selector, val2 (op2=2), val3 (op2=3), val1 (op2=1) - in the order the
# stub itself writes them, per group.
ERRATA_GROUPS = [
    (3, 0x10E3900002, 0x10FFF00083, 0x2001003FF),
    (4, 0x10E3800082, 0x10FFF00083, 0x2001003FF),
    (5, 0x10E3800200, 0x10FFF003E0, 0x2001003FF),
]

# The instruction this gate mutates for the negative control: the core
# number extraction in the primary dispatch, `lsr x6, x6, #8`, patched to
# `lsr x6, x6, #0` (immr field zeroed; a UBFM with N=1, imms=63, Rn=Rd=6).
LSR_X6_X6_8 = 0xD348FCC6
LSR_X6_X6_0 = 0xD340FCC6


def u32(blob: bytes, off: int) -> int:
    return struct.unpack_from("<I", blob, off)[0]


def u64(blob: bytes, off: int) -> int:
    return struct.unpack_from("<Q", blob, off)[0]


# =====================================================================
#  STATIC DECODE - reconstructing an immediate from the MOVZ/MOVK chain
#  that built it, by reading the built bytes rather than running them.
# =====================================================================
def scan_immediate(blob: bytes, end_off: int, reg: int, bits: int,
                    max_back: int = 96) -> int | None:
    """What register `reg` holds immediately before the instruction at
    `end_off`, reconstructed from the contiguous MOVZ/MOVK (or MOVN)
    chain that precedes it - walking backward and stopping the moment a
    MOVZ/MOVN to `reg` is found, since that is the chain's start.

    Returns None if no such chain is found within `max_back` bytes -
    which is the honest answer when the value comes from somewhere this
    decoder does not model (a register load, a prior computation), not a
    zero or a guess.
    """
    have: dict[int, int] = {}
    off = end_off - 4
    limit = max(0, end_off - max_back)
    while off >= limit:
        word = u32(blob, off)
        wide = word & 0x1F800000
        if wide in (0x12800000, 0x52800000, 0x72800000):
            rd = word & 31
            if rd == reg:
                opc = (word >> 29) & 3
                hw = (word >> 21) & 3
                imm = ((word >> 5) & 0xFFFF) << (16 * hw)
                if opc == 2:            # MOVZ - the chain's start
                    have[hw] = imm
                    value = 0
                    for v in have.values():
                        value |= v
                    return value & ((1 << bits) - 1)
                elif opc == 3:          # MOVK - keep walking backward
                    have[hw] = imm
                elif opc == 0:          # MOVN - also a chain start
                    value = (~imm) & ((1 << bits) - 1)
                    for v in have.values():
                        value |= v
                    return value
                else:
                    return None
        off -= 4
    return None


def find_msr_writes(blob: bytes, write_base: int) -> list[tuple[int, int]]:
    """Every (offset, Rt) where the built bytes execute `msr <reg>, xRt`
    for the system register whose WRITE base is `write_base`."""
    target = write_base & 0xFFFFFFE0
    out = []
    for off in range(0, len(blob) - 3, 4):
        word = u32(blob, off)
        if (word & 0xFFF00000) == 0xD5100000 and (word & 0xFFFFFFE0) == target:
            out.append((off, word & 31))
    return out


def find_str_writes(blob: bytes, size: int = 4) -> list[tuple[int, int, int, int]]:
    """Every (offset, Rn, Rt, imm) unsigned-immediate STR of `size` bytes."""
    out = []
    for off in range(0, len(blob) - 3, 4):
        word = u32(blob, off)
        if (word & 0x3F000000) != 0x39000000:
            continue
        size_code = (word >> 30) & 3
        load = (word >> 22) & 1
        if load or (1 << size_code) != size:
            continue
        rn = (word >> 5) & 31
        rt = word & 31
        imm = ((word >> 10) & 0xFFF) * size
        out.append((off, rn, rt, imm))
    return out


# =====================================================================
#  A. THE LAYOUT, IN THE BUILT BYTES
# =====================================================================
def check_layout(blob: bytes) -> list[str]:
    fails: list[str] = []
    print("A. the layout the firmware relies on")

    if len(blob) % PAD_TO:
        fails.append(
            "the stub is %d bytes, not a multiple of %d." % (len(blob), PAD_TO))
    else:
        print("   %d bytes, a multiple of %d" % (len(blob), PAD_TO))

    if len(blob) < FIXED_BLOCK_OFF:
        return fails + ["the stub is shorter than the fixed block it must contain"]

    magic = u32(blob, STUB_MAGIC_OFF)
    if magic != STUB_MAGIC:
        fails.append("the magic at 0x%02X is 0x%08X, not 0x%08X."
                      % (STUB_MAGIC_OFF, magic, STUB_MAGIC))
    else:
        print("   0x%02X magic 0x%08X" % (STUB_MAGIC_OFF, magic))

    for off, name in ((STUB_VERSION_OFF, "stub_version"),
                      (DTB_PTR_OFF, "dtb_ptr32"),
                      (KERNEL_ENTRY_OFF, "kernel_entry32")):
        got = u32(blob, off)
        if got != 0:
            fails.append("%s at 0x%02X is 0x%08X and must ship as zero."
                         % (name, off, got))
        else:
            print("   0x%02X %-14s ships zero" % (off, name))

    for core, off in enumerate(SPIN_CPU[:3]):
        got = u64(blob, off)
        if got != 0:
            fails.append("spin_cpu%d at 0x%02X is 0x%016X and must ship as "
                         "zero." % (core, off, got))
    print("   0x%02X 0x%02X 0x%02X spin slots 0..2 ship zero" % SPIN_CPU[:3])
    print("   0x%02X spin slot 3 holds the magic and the version until the "
          "firmware clears them" % SPIN_CPU[3])

    last_code = max((off for off in range(0, SPIN_CPU[0], 4)
                     if u32(blob, off) != 0), default=-4)
    if last_code + 4 > SPIN_CPU[0]:
        fails.append("the entry code reaches 0x%02X and the spin table "
                     "starts at 0x%02X." % (last_code + 4, SPIN_CPU[0]))
    else:
        print("   entry code ends at 0x%02X, %d bytes clear of the spin table"
              % (last_code + 4, SPIN_CPU[0] - last_code - 4))
    return fails


# =====================================================================
#  B. THE CONSTANTS, DECODED FROM THE BUILT BYTES
# =====================================================================
def check_constants(blob: bytes) -> list[str]:
    fails: list[str] = []
    print()
    print("B. the constants, decoded from the built instructions")

    for name, base, want, why in SYSREG_CHECKS:
        hits = find_msr_writes(blob, base)
        if not hits:
            fails.append("the stub never writes %s. %s" % (name, why))
            continue
        off, rt = hits[0]
        got = scan_immediate(blob, off, rt, 64)
        if got is None:
            fails.append("%s is written at 0x%X but this decoder cannot "
                         "reconstruct the value loaded into x%d before it."
                         % (name, off, rt))
        elif got != want:
            fails.append("%s at 0x%X is built as 0x%X and must be 0x%X. %s"
                         % (name, off, got, want, why))
        else:
            print("      %-16s 0x%016X   (built at 0x%X)" % (name, got, off))

    for addr, want, why in MMIO_CHECKS:
        hits = [h for h in find_str_writes(blob, 4)]
        found = None
        for off, rn, rt, imm in hits:
            base_addr = scan_immediate(blob, off, rn, 64)
            if base_addr is None:
                continue
            if base_addr + imm == addr:
                found = (off, rt)
                break
        if found is None:
            fails.append(
                "no store to 0x%08X was found in the built bytes (%s). %s"
                % (addr, why, "" ))
            continue
        off, rt = found
        got = scan_immediate(blob, off, rt, 32)
        if got is None:
            fails.append("0x%08X is written at 0x%X but the value register "
                         "could not be decoded." % (addr, off))
        elif got != want:
            fails.append("0x%08X is written as 0x%X and must be 0x%X. %s"
                         % (addr, got, want, why))
        else:
            print("      0x%08X <- 0x%08X   (built at 0x%X)" % (addr, got, off))

    # Every address above is asserted against the DOCUMENTED value, never
    # against what the code computes: that is how LOCAL_CONTROL's wrong
    # halfword split (0x107C00280000) was caught - see the module docstring.

    sel_hits = find_msr_writes(blob, ERR_SELECT)
    v1_hits = find_msr_writes(blob, ERR_VAL1)
    v2_hits = find_msr_writes(blob, ERR_VAL2)
    v3_hits = find_msr_writes(blob, ERR_VAL3)
    if not (len(sel_hits) == len(v1_hits) == len(v2_hits) == len(v3_hits)
            == len(ERRATA_GROUPS)):
        fails.append(
            "expected %d erratum-1946160 selector/value groups and found "
            "select=%d val1=%d val2=%d val3=%d in the built bytes."
            % (len(ERRATA_GROUPS), len(sel_hits), len(v1_hits), len(v2_hits),
               len(v3_hits)))
    else:
        for i, (want_sel, want_v2, want_v3, want_v1) in enumerate(ERRATA_GROUPS):
            sel = scan_immediate(blob, sel_hits[i][0], sel_hits[i][1], 64)
            v2 = scan_immediate(blob, v2_hits[i][0], v2_hits[i][1], 64)
            v3 = scan_immediate(blob, v3_hits[i][0], v3_hits[i][1], 64)
            v1 = scan_immediate(blob, v1_hits[i][0], v1_hits[i][1], 64)
            got = (sel, v2, v3, v1)
            want = (want_sel, want_v2, want_v3, want_v1)
            if got != want:
                fails.append(
                    "erratum-1946160 group %d is built as select=%r val2=%r "
                    "val3=%r val1=%r and must be select=0x%X val2=0x%X "
                    "val3=0x%X val1=0x%X."
                    % (i, sel, v2, v3, v1, want_sel, want_v2, want_v3, want_v1))
            else:
                print("      erratum group %d: select=0x%X val2=0x%X "
                      "val3=0x%X val1=0x%X" % (i, sel, v2, v3, v1))

    if any(u32(blob, off) == ERET_WORD for off in range(0, len(blob) - 3, 4)):
        fails.append("the built image contains an ERET word (0x%08X). NOT "
                     "DROPPING A LEVEL IS THE ENTIRE POINT OF THIS FILE."
                     % ERET_WORD)
    else:
        print("      no ERET word anywhere in the image")

    return fails


# =====================================================================
#  C. BOTH DISPATCH PATHS, RUN, PLUS THE NEGATIVE MUTATION CONTROL
# =====================================================================
def make_cpu(blob: bytes, mpidr: int, midr: int | None = None) -> A64:
    cpu = A64()
    for i, byte in enumerate(blob):
        cpu.memory[i] = byte
    preset = {MPIDR_EL1: mpidr}
    if midr is not None:
        preset[MIDR_EL1] = midr
    cpu.enable_system_registers(el=3, preset=preset)
    cpu.align_check = True
    cpu.pc = 0
    cpu.sp = 0
    # GICD_TYPER: this flat model has no distributor behind the address,
    # only what was last stored there, so the word count setup_gic's own
    # loop computes has to come from somewhere. Preset to 0x0000000A so
    # ((TYPER & 0x1F) + 1) == 11, per the task this gate was built under.
    cpu.raw_store(GICD_TYPER, 0x0000000A, 4)
    return cpu


def trace_uart(cpu: A64) -> list[int]:
    """Record every byte stored to the debug UART's data register. The one
    hook this gate installs on a store; returns the live list."""
    captured: list[int] = []
    orig_store = cpu.store

    def traced_store(addr: int, value: int, size: int) -> None:
        orig_store(addr, value, size)
        if addr == UART_DR:
            captured.append(value & 0xFF)

    cpu.store = traced_store
    return captured


def run_bounded(cpu: A64, blob_len: int, limit: int) -> int:
    """Step until the pc leaves the stub or `limit` is reached. Returns
    the number of steps actually taken, so a run that never leaves can be
    told apart from one that left on the last step allowed."""
    steps = 0
    while cpu.pc < blob_len and steps < limit:
        cpu.step()
        steps += 1
    return steps


def check_primary(blob: bytes) -> list[str]:
    fails: list[str] = []
    print()
    print("C.1. core 0: MPIDR Aff1=0, both erratum-applicability cases")

    kernel = 0x00080000
    dtb = 0x2EFF0000
    # r4p1 - MIDR_EL1 $414FD0B1 - erratum 1946160 applies (variant.rev
    # 0x41 is inside the affected 0x30..0x41 range TF-A checks).
    cpu = make_cpu(blob, mpidr=0x81000000, midr=0x414FD0B1)
    cpu.memory.update({KERNEL_ENTRY_OFF + i: (kernel >> (8 * i)) & 0xFF
                       for i in range(4)})
    cpu.memory.update({DTB_PTR_OFF + i: (dtb >> (8 * i)) & 0xFF
                       for i in range(4)})
    cpu.memory.update({STUB_MAGIC_OFF + i: 0 for i in range(4)})  # cleared
    uart_out = trace_uart(cpu)

    steps = run_bounded(cpu, len(blob), 400_000)
    if cpu.pc >= len(blob) and cpu.pc != kernel:
        fails.append("core 0 (r4p1) branched to 0x%X in %d steps, and the "
                     "firmware's kernel_entry32 is 0x%X." % (cpu.pc, steps, kernel))
    elif cpu.pc < len(blob):
        fails.append("core 0 (r4p1) never left the stub in %d steps." % steps)
    else:
        print("   r4p1: branched to kernel_entry32 (0x%X) in %d steps" % (cpu.pc, steps))

    if cpu.x[0] != dtb:
        fails.append("x0 is 0x%X at the branch; the firmware's dtb_ptr32 is "
                     "0x%X." % (cpu.x[0], dtb))
    else:
        print("   x0 = dtb_ptr32, 0x%X" % cpu.x[0])
    for reg in (1, 2, 3):
        if cpu.x[reg] != 0:
            fails.append("x%d is 0x%X at the branch and must be zero." % (reg, cpu.x[reg]))
    if cpu.erets:
        fails.append("core 0 (r4p1) executed an eret: %r" % cpu.erets)
    else:
        print("   no eret executed")
    if cpu.current_el != 3:
        fails.append("core 0 (r4p1) branched at EL%d, not EL3." % cpu.current_el)
    else:
        print("   CurrentEL is 3 at the branch")

    # The erratum's LAST group is the only one an execution can still see
    # (see the module docstring on why); its presence is still the right
    # proof that the conditional guard let the whole sequence run at all.
    sel, v2, v3, v1 = (cpu.sysreg(ERR_SELECT), cpu.sysreg(ERR_VAL2),
                       cpu.sysreg(ERR_VAL3), cpu.sysreg(ERR_VAL1))
    want_sel, want_v2, want_v3, want_v1 = ERRATA_GROUPS[-1]
    if (sel, v2, v3, v1) != (want_sel, want_v2, want_v3, want_v1):
        fails.append("MIDR 0x414FD0B1 (r4p1) is inside the erratum-1946160 "
                     "range and the run left select=%r val2=%r val3=%r "
                     "val1=%r; the sequence should have executed and left "
                     "select=0x%X val2=0x%X val3=0x%X val1=0x%X."
                     % (sel, v2, v3, v1, want_sel, want_v2, want_v3, want_v1))
    else:
        print("   MIDR r4p1: the erratum-1946160 writes happened (final "
              "group select=0x%X)" % sel)

    for reg in (ELR_EL3, SPSR_EL3):
        if cpu.sysreg(reg) is not None:
            fails.append("elr_el3/spsr_el3 was written (0x%X). This stub "
                         "never erets, so preparing a return is dead code "
                         "or a drop somebody put back." % cpu.sysreg(reg))
    print("   elr_el3 / spsr_el3 untouched")

    # The debug UART, opened as the stock stub's console_pl011_core_init
    # does (this stub replaces the code that did it; the first silicon boot
    # with no UART setup put zero bytes on the wire). UARTCR is written
    # twice - off, then on - so its FINAL value is what is asserted here.
    for off, want, name in ((0x24, 24, "UARTIBRD"), (0x28, 0, "UARTFBRD"),
                            (0x2C, 0x70, "UARTLCR_H (FEN|WLEN_8)"),
                            (0x30, 0x301, "UARTCR (RXE|TXE|UARTEN)")):
        got = cpu.raw_load(UART_DR + off, 4)
        if got != want:
            fails.append("%s at 0x%X is 0x%X after core 0 ran; 115200 baud "
                         "from 44,236,800 Hz needs 0x%X." % (name, UART_DR + off, got, want))
    print("   debug UART: IBRD 24, FBRD 0, LCR_H 0x70, CR 0x301 (115200 8N1, FIFOs on)")
    if bytes(uart_out) != b"ANVIL EL3 STUB\r\n":
        fails.append("core 0 wrote %r to the UART before the branch; it must "
                     "say exactly b'ANVIL EL3 STUB\\r\\n'." % bytes(uart_out))
    else:
        print("   said %r before branching" % bytes(uart_out))

    igroups = [cpu.raw_load(GICD_IGROUPR + 4 * i, 4) for i in range(11)]
    beyond = cpu.raw_load(GICD_IGROUPR + 4 * 11, 4)
    if igroups != [0xFFFFFFFF] * 11 or beyond != 0:
        fails.append("with GICD_TYPER preset to 0x0000000A, GICD_IGROUPR0..10 "
                     "read %s and word 11 reads 0x%08X; expected eleven "
                     "0xFFFFFFFF words and nothing past them."
                     % (", ".join("0x%08X" % g for g in igroups), beyond))
    else:
        print("   GICD_TYPER=0x0000000A -> 11 GICD_IGROUPR words, all ones, "
              "nothing written past the 11th")

    # r2p0 - MIDR_EL1 $412FD050 - OUTSIDE the erratum's range (0x20 < 0x30).
    cpu2 = make_cpu(blob, mpidr=0x81000000, midr=0x412FD050)
    cpu2.memory.update({KERNEL_ENTRY_OFF + i: (kernel >> (8 * i)) & 0xFF
                        for i in range(4)})
    cpu2.memory.update({DTB_PTR_OFF + i: (dtb >> (8 * i)) & 0xFF
                        for i in range(4)})
    cpu2.memory.update({STUB_MAGIC_OFF + i: 0 for i in range(4)})
    steps2 = run_bounded(cpu2, len(blob), 400_000)
    if cpu2.pc != kernel:
        fails.append("core 0 (r2p0) branched to 0x%X in %d steps, not "
                     "kernel_entry32 0x%X." % (cpu2.pc, steps2, kernel))
    if cpu2.sysreg(ERR_SELECT) is not None:
        fails.append("MIDR 0x412FD050 (r2p0) is OUTSIDE the erratum-1946160 "
                     "range and the run still wrote the selector register "
                     "(0x%X); the variant.revision guard did not skip it."
                     % cpu2.sysreg(ERR_SELECT))
    else:
        print("   MIDR r2p0: the erratum-1946160 writes did NOT happen")

    return fails


def check_secondary(blob: bytes) -> list[str]:
    fails: list[str] = []
    print()
    print("C.2. core 2: parks, then releases through its spin slot")

    core = 2
    mpidr = 0x81000000 | (core << 8)
    target = 0x00080000
    cpu = make_cpu(blob, mpidr=mpidr)

    for _ in range(300):
        if cpu.pc >= len(blob):
            break
        cpu.step()
    if cpu.pc >= len(blob):
        fails.append("core 2 left the stub with spin_cpu2 still zero, "
                     "branching to 0x%X." % cpu.pc)
        return fails
    print("   parked (still inside the stub after 300 steps with "
          "spin_cpu2 == 0)")

    slot = SPIN_CPU[core]
    for i in range(8):
        cpu.memory[slot + i] = (target >> (8 * i)) & 0xFF
    steps = run_bounded(cpu, len(blob), 400_000)
    if cpu.pc != target:
        fails.append("core 2 was released to 0x%X via spin_cpu2 (0x%02X) "
                     "and branched to 0x%X in %d steps."
                     % (target, slot, cpu.pc, steps))
    else:
        print("   released through 0x%02X, branched to 0x%X in %d steps"
              % (slot, cpu.pc, steps))
    if cpu.x[0] != 0:
        fails.append("core 2 branched with x0 = 0x%X; a secondary carries "
                     "x0 = 0, only the primary carries the device tree."
                     % cpu.x[0])
    else:
        print("   x0 = 0, as a secondary must")
    if cpu.erets:
        fails.append("core 2 executed an eret: %r" % cpu.erets)
    if cpu.current_el != 3:
        fails.append("core 2 branched at EL%d, not EL3." % cpu.current_el)
    return fails


def check_magic_not_cleared(blob: bytes) -> list[str]:
    fails: list[str] = []
    print()
    print("C.3. core 0: the firmware never cleared the magic")

    cpu = make_cpu(blob, mpidr=0x81000000, midr=0x414FD0B1)
    # dtb_ptr32/kernel_entry32/stub_magic are left exactly as the compiler
    # built them: magic is $5AFE570B (uncleared), the two words are zero.
    # UART FR (+0x18) is never written here, so it reads zero from this
    # flat model's default - which is the "always ready to transmit" case
    # the task asked for.
    captured = trace_uart(cpu)

    visited: list[int] = []
    limit = 260_000
    for _ in range(limit):
        if cpu.pc >= len(blob):
            fails.append("core 0 left the stub (pc=0x%X) instead of parking "
                         "after finding the magic not cleared." % cpu.pc)
            return fails
        visited.append(cpu.pc)
        cpu.step()

    got = bytes(captured)
    want = b"ANVIL EL3 STUB\r\nSTUB MAGIC\r\n"
    if got != want:
        fails.append("the UART DR trace is %r and must be %r." % (got, want))
    else:
        print("   wrote %r to UART DR (0x%X)" % (want, UART_DR))

    tail = visited[-6:]
    distinct = sorted(set(tail))
    if len(distinct) != 2 or distinct[1] - distinct[0] != 4:
        fails.append("core 0 should be parked in a tight two-instruction "
                     "loop (wfe / b) by now; the last program counters seen "
                     "are %s." % [hex(x) for x in tail])
    else:
        print("   parked in a two-instruction loop at 0x%X/0x%X, never "
              "reaching kernel_entry32" % (distinct[0], distinct[1]))
    if cpu.x[0] == 0x2EFF0000:
        fails.append("x0 was loaded from dtb_ptr32; the magic-not-cleared "
                     "path must never read the firmware's words.")
    return fails


def check_mutation(blob: bytes) -> list[str]:
    fails: list[str] = []
    print()
    print("C.4. negative control: the core-number extraction, mutated")

    target = struct.pack("<I", LSR_X6_X6_8)
    where = blob.find(target)
    if where < 0:
        return ["the built bytes do not contain the expected "
                "`lsr x6, x6, #8` word (0x%08X); the mutation this gate "
                "relies on cannot be applied." % LSR_X6_X6_8]
    if blob.find(target, where + 1) >= 0:
        return ["`lsr x6, x6, #8` (0x%08X) appears more than once; the "
                "mutation would be ambiguous about which core-number "
                "extraction it patches." % LSR_X6_X6_8]

    mutant = bytearray(blob)
    mutant[where:where + 4] = struct.pack("<I", LSR_X6_X6_0)
    mutant = bytes(mutant)
    print("   patched `lsr x6, x6, #8` -> `lsr x6, x6, #0` at 0x%X" % where)

    core = 2
    mpidr = 0x81000000 | (core << 8)
    kernel = 0x00080000
    dtb = 0x2EFF0000
    cpu = make_cpu(mutant, mpidr=mpidr)
    cpu.memory.update({KERNEL_ENTRY_OFF + i: (kernel >> (8 * i)) & 0xFF
                       for i in range(4)})
    cpu.memory.update({DTB_PTR_OFF + i: (dtb >> (8 * i)) & 0xFF
                       for i in range(4)})
    cpu.memory.update({STUB_MAGIC_OFF + i: 0 for i in range(4)})
    run_bounded(cpu, len(mutant), 400_000)

    # THE MUTATION MUST GO WRONG, AND THIS GATE MUST SEE IT.
    #
    # With the shift zeroed, `and x6, x6, #0xFF` reads MPIDR's Aff0 field
    # instead of Aff1 - which is 0 for every core on this board, since
    # Aff0 carries the cluster/thread id the A76 never sets here. Core 2
    # (MPIDR Aff1=2, Aff0=0) is therefore misread as core 0 and takes the
    # PRIMARY path: it reaches kernel_entry32 directly, with the device
    # tree in x0, exactly as core 0 would - instead of parking in its
    # spin slot. If this run does NOT show that, the mutation escaped and
    # this whole check is a check with no teeth.
    went_wrong = (cpu.pc == kernel and cpu.x[0] == dtb)
    if not went_wrong:
        fails.append(
            "MUTATION ESCAPED DETECTION: with the core-number shift "
            "zeroed, core 2 was expected to boot as a primary (branch to "
            "kernel_entry32 with x0 = dtb_ptr32) and instead reached "
            "pc=0x%X x0=0x%X. A check that cannot tell this mutant from "
            "the real stub is not proving anything about the real one."
            % (cpu.pc, cpu.x[0]))
    else:
        print("   confirmed: the mutant makes core 2 boot as a primary "
              "(pc=0x%X, x0=0x%X) - the gate goes red on this mutation"
              % (cpu.pc, cpu.x[0]))
    return fails


def run(args: list[str], *, expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args, cwd=ROOT, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, check=False,
    )
    if result.returncode != expect:
        raise AssertionError(
            f"command returned {result.returncode}, expected {expect}:\n"
            f"{' '.join(args)}\n{result.stdout}"
        )
    return result


def locate_compiler(explicit: str | None) -> Path:
    requested = explicit or os.environ.get("PMF_COMPILER")
    if requested:
        return Path(_pmf_resolve_compiler(requested))
    found = (shutil.which("PureMetalForge.exe") or
             shutil.which("PureMetalForge.linux") or
             shutil.which("PureMetalForge"))
    if found:
        return Path(found).resolve()
    raise SystemExit("EL3 pi5 gate: pass --compiler, set PMF_COMPILER, or "
                     "put PureMetalForge on PATH")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", help="external PureMetal compiler (or set PMF_COMPILER)")
    parser.add_argument(
        "--image", type=Path,
        help="verify an existing armstub8-2712.bin; skips the rebuild")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="pmf_el3_pi5_") as td:
        temp = Path(td)
        if args.image:
            stub = args.image.expanduser().resolve()
            if not stub.is_file():
                raise SystemExit("EL3 pi5 gate: image not found: %s" % stub)
            print("[gate] verifying supplied image; source rebuild not claimed",
                  file=sys.stderr)
        else:
            compiler = locate_compiler(args.compiler)
            stub = temp / "armstub8-2712.bin"
            # The stub's own header documents this exact invocation: the
            # firmware-stub door, target pi4 - there is no pi5 target in
            # the compiler yet (--list-targets), and --armstub mode does
            # not depend on one; it is the same A64 assembler door the
            # Pi 4 stub uses.
            run([str(compiler), "--compile", "--armstub", "-t", "pi4", STUB_SRC,
                 "-o", str(stub)])
        blob = stub.read_bytes()

        fails = check_layout(blob)
        fails += check_constants(blob)
        fails += check_primary(blob)
        fails += check_secondary(blob)
        fails += check_magic_not_cleared(blob)
        fails += check_mutation(blob)

    print()
    if fails:
        print("a64_el3_pi5_check: FAIL")
        for line in fails:
            print("   %s" % line)
        return 1
    print("a64_el3_pi5_check: PASS - the stub's layout, every documented "
          "constant decoded from the built bytes, both dispatch paths, "
          "the uncleared-magic path, no ERET, and the mutation control.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

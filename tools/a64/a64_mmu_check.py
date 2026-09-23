#!/usr/bin/env python3
"""Executable gate for RaspberryPi4/Lib/mmu.pi4 - stages 0 and 1.

    python tools/a64/a64_mmu_check.py --compiler <PureMetalForge.exe>

WHAT THIS GATE CAN AND CANNOT DO. Read this before extending it.

CANNOT: prove that enabling the MMU works.  tools/a64/a64_interp.py has
one flat byte-addressed memory with no caches and no TLB, and it performs
NO ADDRESS TRANSLATION AT ALL.  It could not tell a correct page table
from a table of zeroes.  The system-register reads this probe makes are
shimmed below.  So no gate on this machine can say the board will survive
stage 1.  Only the board can.

CAN, and all three are worth having:

  1. THE TABLE BUILDER IS RUN AND EVERY DESCRIPTOR IS CHECKED.  This is
     the real content of the gate.  MmuBuildTables() is ordinary code
     writing ordinary memory - no system registers, no translation - so
     the model runs it exactly as the silicon would.  All 64 level-1 and
     all 512 level-2 descriptors are then read out of the model's memory
     and compared against a map recomputed HERE, independently of
     mmu.pi4.  A wrong attribute, a missing Access Flag, a 32-bit store
     where a 64-bit one was needed, an off-by-one at the DRAM/peripheral
     boundary, or a missing PCIe slot all go red.

     THE TWO THAT MATTER MOST are asserted by name rather than left to
     the bulk comparison, because they are the two whose absence is
     silent on the bench: level-1 slot 24, without which the VL805 XHCI
     controller is unreachable and USB dies, and the level-2 slot
     covering $FF800000, without which core 1 can never be released.

  2. THE CONSTANTS ARE RE-DERIVED FROM THE VENDOR DEFINITIONS.
     #MMU_TCR_EL2, #MMU_MAIR_EL2, #MMU_ATTR_DEVICE, #MMU_ATTR_NORMAL_NC,
     #MMU_ATTR_NORMAL_WB and #MMU_SCTLR_M are parsed out of mmu.pi4 and
     recomputed from the memory-type indices and the SCTLR bit that
     Das U-Boot defines.  Those headers are third-party source and are not
     copied into this tree: the five indices and the one bit are pinned
     below with the upstream file and line.  The library and the gate
     state the same facts independently and can disagree.

  3. THE STAGE 0 CITATION IS RE-CHECKED.  #MMU_SCTLR_EL2_STUB is compared
     against the value the Raspberry Pi firmware stub writes (pinned from
     raspberrypi/tools armstubs/armstub8.S, cited not copied), AND against
     the value Anvil's own stub RaspberryPi4/Board/armstub8.asm loads
     before its `msr sctlr_el2` and `msr sctlr_el3`, which is also what
     #MMU_SCTLR_EL3_STUB must equal.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(__file__).resolve().parents[2]
LIB = ROOT / "RaspberryPi4" / "Lib" / "mmu.pi4"
PROBE = ROOT / "RaspberryPi4" / "Examples" / "Diagnostics" / "pi4MmuIdentity.pi4"
ANVIL_STUB = ROOT / "RaspberryPi4" / "Board" / "armstub8.asm"

sys.path.insert(0, str(HERE))
from a64_interp import A64, attach_symbols  # noqa: E402

LOAD = 0x400000
LOADER_SP = 0x3000000
LOADER_LR = 0xDEADBEE0
TABLES = 0x600000
CNTFRQ = 54_000_000

# ----------------------------------------------------------------------
#  PINNED THIRD-PARTY FACTS (cited, not copied)
# ----------------------------------------------------------------------
# raspberrypi/tools, revision 439b6198a9b340de5998dd14a26a0d9d38a6bcac,
# armstubs/armstub8.S:136-141:
#     "Set up SCTLR_EL2 / All set bits below are res1. LE, no
#      WXN/I/SA/C/A/M"   ldr x0, =0x30c50830 ; msr SCTLR_EL2, x0
RPI_ARMSTUB8_SCTLR_EL2 = 0x30C50830
SCTLR_EL2_AT_ENTRY = RPI_ARMSTUB8_SCTLR_EL2

# Das U-Boot v2025.01, revision 6d41f0a39d6423c8e57e92ebbe9f8c0333a63f72,
# arch/arm/include/asm/armv8/mmu.h:28-32 - the memory-type indices.
UBOOT_ARMV8_MMU_MT = {
    "MT_DEVICE_NGNRNE": 0,      # :28
    "MT_DEVICE_NGNRE": 1,       # :29
    "MT_DEVICE_GRE": 2,         # :30
    "MT_NORMAL_NC": 3,          # :31
    "MT_NORMAL": 4,             # :32
}
# The same revision, arch/arm/include/asm/system.h:12 (and :337):
#     #define CR_M (1 << 0)   /* MMU enable */
UBOOT_SYSTEM_CR_M_SHIFT = 0


def expected_map(dev: int, nc: int) -> tuple[list[int], list[int]]:
    """The map, recomputed here.  See mmu.pi4's THE MAP, ENTRY BY ENTRY."""
    l1 = []
    for i in range(64):
        pa = i << 30
        if i == 3:
            l1.append((TABLES + 4096) | 3)          # PTE_TYPE_TABLE
        elif i < 3:
            l1.append(pa | nc)
        elif 24 <= i <= 31:
            l1.append(pa | dev)
        else:
            l1.append(0)                            # PTE_TYPE_FAULT
    l2 = []
    for i in range(512):
        pa = 0xC0000000 + (i << 21)
        l2.append(pa | (nc if pa < 0xFC000000 else dev))
    return l1, l2


def lib_constant(name: str) -> int:
    text = LIB.read_text(errors="replace")
    m = re.search(r"^#" + re.escape(name) +
                  r"\s*=\s*(-?)\$?([0-9A-Fa-f]+)\s*(?:;.*)?$",
                  text, re.MULTILINE)
    if not m:
        raise SystemExit("a64_mmu_check: #%s was not found in %s." % (name, LIB))
    v = int(m.group(2), 16)
    return -v if m.group(1) else v


def anvil_stub_sctlr() -> tuple[int, bool]:
    """The value RaspberryPi4/Board/armstub8.asm loads into x0 immediately
    before `msr sctlr_el2, x0`, and whether the same x0 then goes into
    SCTLR_EL3."""
    text = ANVIL_STUB.read_text(errors="replace")
    m = re.search(
        r"movz\s+x0\s*,\s*#(0x[0-9A-Fa-f]+|\d+)\s*\n\s*"
        r"movk\s+x0\s*,\s*#(0x[0-9A-Fa-f]+|\d+)\s*,\s*lsl\s+#16\s*\n\s*"
        r"msr\s+sctlr_el2\s*,\s*x0\s*\n((?:\s*;[^\n]*\n)*)\s*msr\s+sctlr_el3\s*,\s*x0",
        text, re.IGNORECASE)
    if not m:
        raise SystemExit(
            "a64_mmu_check: the movz/movk x0 then `msr sctlr_el2, x0` and "
            "`msr sctlr_el3, x0` sequence is not in %s. The stub has changed "
            "shape. Do NOT relax this pattern to make the gate pass - read "
            "the new stub and decide what it means for #MMU_SCTLR_EL2_STUB "
            "and #MMU_SCTLR_EL3_STUB." % ANVIL_STUB)
    return int(m.group(1), 0) | (int(m.group(2), 0) << 16), True


def build(compiler: str, source: pathlib.Path, img: pathlib.Path) -> None:
    r = subprocess.run(
        [compiler, "--compile", str(source), "-t", "pi4",
         "--load-addr", hex(LOAD), "--stack-addr", hex(LOADER_SP),
         "--entry-returns", "-o", str(img)],
        cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
        capture_output=True, text=True)
    if r.returncode != 0 or not img.exists():
        raise SystemExit("The MMU probe did not build:\n" + r.stdout + r.stderr)


def run(img: pathlib.Path, limit: int = 200_000_000):
    """Run the probe.  Returns (memory, uart bytes, recorded MSR writes)."""
    cpu = A64()
    for i, b in enumerate(img.read_bytes()):
        cpu.memory[LOAD + i] = b
    attach_symbols(cpu, img, LOAD)
    cpu.pc = LOAD
    cpu.sp = LOADER_SP
    cpu.x[30] = LOADER_LR
    mem = cpu.memory
    uart = bytearray()

    def load(addr: int, size: int) -> int:
        # THE ALIGNMENT RULE: this closure replaces A64.load, so the guard
        # has to be called here.
        cpu.align_guard(addr, size, False)
        if addr >= 0xFC000000:
            # PL011 flag register: never busy, nothing waiting to read.
            if addr == 0xFE201018:
                return 0
            # Everything else in the peripheral aperture reads as zero.
            # The probe only writes there - UART setup, the GPIO mux, the
            # PM watchdog - and nothing it does depends on reading one
            # back, so a zero is a faithful enough model for this gate.
            return 0
        return sum(mem.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr: int, value: int, size: int) -> None:
        cpu.align_guard(addr, size, True)
        if addr >= 0xFC000000:
            if addr == 0xFE201000:
                uart.append(value & 0xFF)
            return
        for i in range(size):
            mem[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    plain_step = A64.step.__get__(cpu)

    # Shim exactly the system-register reads this probe makes.  Each key
    # is the MRS base with the read bit set; Rt is the low five bits.
    SHIM = {
        0xD53BE000: CNTFRQ,                 # cntfrq_el0
        0xD53BE020: 0,                      # cntpct_el0
        0xD5384240: 8,                      # currentel -> EL2
        0xD53C1000: SCTLR_EL2_AT_ENTRY,     # sctlr_el2
        0xD5381000: 0,                      # sctlr_el1
        0xD53C1100: 0,                      # hcr_el2
    }

    # SWALLOWING THE MSRs IS HONEST HERE.  This gate has never claimed to
    # prove the enable: what it proves is that MmuBuildTables() writes the
    # right 576 descriptors, which is ordinary code writing ordinary
    # memory.  A system-register write neither helps nor hinders that.
    # Writes are RECORDED rather than merely skipped, so a shim that
    # silently discards cannot become a gate that passes because nothing
    # happened.
    MSR_WATCH = {
        0xD51C2000: "ttbr0_el2",
        0xD51C2040: "tcr_el2",
        0xD51CA200: "mair_el2",
        0xD51C1000: "sctlr_el2",
    }
    msr_writes: list = []

    def step() -> None:
        # cpu.fetch, not load: an instruction fetch is not a data access.
        ins = cpu.fetch(cpu.pc)
        base = ins & 0xFFFFFFE0
        if base in SHIM:
            cpu.x[ins & 31] = SHIM[base]
            cpu.pc += 4
            return
        if base in MSR_WATCH:
            name, value = MSR_WATCH[base], cpu.x[ins & 31]
            msr_writes.append((name, value))
            # THE ONE PLACE WHERE THE REGIME CHANGES.  Once SCTLR_EL2.M is
            # set, DRAM is mapped Normal and an unaligned access to Normal
            # memory is architecturally legal while SCTLR.A is clear.  The
            # model is told by the payload's own action, and the relaxation
            # stops at a64_interp.DEVICE_FLOOR because mmu.pi4 maps the
            # peripheral aperture Device in both regimes.  #MMU_SCTLR_M is
            # read from the library rather than written as a literal.
            if name == "sctlr_el2":
                cpu.mmu_enabled(bool(value & lib_constant("MMU_SCTLR_M")))
            cpu.pc += 4
            return
        plain_step()

    for _ in range(limit):
        if cpu.pc == LOADER_LR:
            break
        step()
    else:
        raise SystemExit("a64_mmu_check: the probe did not return.")
    return mem, uart, msr_writes


def read_u64(mem, addr: int) -> int:
    return sum(mem.get(addr + i, 0) << (8 * i) for i in range(8))


def run_gate(compiler: str, probe: pathlib.Path = PROBE) -> int:
    fails: list[str] = []
    count = 0

    def expect(cond: bool, what: str) -> None:
        nonlocal count
        count += 1
        if not cond:
            fails.append(what)

    # -- the stage 0 citation, checked two ways -------------------------
    expect(RPI_ARMSTUB8_SCTLR_EL2 == lib_constant("MMU_SCTLR_EL2_STUB"),
           "#MMU_SCTLR_EL2_STUB is $%X but armstub8.S writes $%X"
           % (lib_constant("MMU_SCTLR_EL2_STUB"), RPI_ARMSTUB8_SCTLR_EL2))
    ours, _ = anvil_stub_sctlr()
    expect(ours == RPI_ARMSTUB8_SCTLR_EL2,
           "RaspberryPi4/Board/armstub8.asm loads $%X into SCTLR_EL2; the "
           "firmware stub it cites writes $%X" % (ours, RPI_ARMSTUB8_SCTLR_EL2))
    expect(ours == lib_constant("MMU_SCTLR_EL3_STUB"),
           "#MMU_SCTLR_EL3_STUB is $%X but RaspberryPi4/Board/armstub8.asm "
           "writes $%X into SCTLR_EL3" % (lib_constant("MMU_SCTLR_EL3_STUB"), ours))
    print("stage 0 citation: armstub8.S writes SCTLR_EL2 = $%08X; "
          "armstub8.asm writes $%08X to SCTLR_EL2 and SCTLR_EL3"
          % (RPI_ARMSTUB8_SCTLR_EL2, ours))
    print()

    # -- the constants, recomputed from the pinned vendor definitions ---
    mt = UBOOT_ARMV8_MMU_MT
    mair = 0
    for name, byte in (("MT_DEVICE_NGNRNE", 0x00), ("MT_DEVICE_NGNRE", 0x04),
                       ("MT_DEVICE_GRE", 0x0C), ("MT_NORMAL_NC", 0x44),
                       ("MT_NORMAL", 0xFF)):
        mair |= byte << (mt[name] * 8)
    expect(mair == lib_constant("MMU_MAIR_EL2"),
           "#MMU_MAIR_EL2 is $%X, the headers give $%X"
           % (lib_constant("MMU_MAIR_EL2"), mair))

    # TCR_EL2 for ips=1, va_bits=36, per U-Boot v2025.01
    # arch/arm/cpu/armv8/cache_v8.c:94-103 and armv8/mmu.h:83-104.
    tcr = (1 << 31) | (1 << 23)              # TCR_EL2_RSVD
    tcr |= 1 << 16                           # ips = 1
    tcr |= 0 << 14                           # TCR_TG0_4K
    tcr |= 3 << 12                           # TCR_SHARED_INNER
    tcr |= 1 << 10                           # TCR_ORGN_WBWA
    tcr |= 1 << 8                            # TCR_IRGN_WBWA
    tcr |= 64 - 36                           # TCR_T0SZ(36)
    expect(tcr == lib_constant("MMU_TCR_EL2"),
           "#MMU_TCR_EL2 is $%X, the headers give $%X"
           % (lib_constant("MMU_TCR_EL2"), tcr))

    dev = (1 << 0) | (mt["MT_DEVICE_NGNRNE"] << 2) | (0 << 8) | (1 << 10)
    nc = (1 << 0) | (mt["MT_NORMAL_NC"] << 2) | (3 << 8) | (1 << 10)
    expect(dev == lib_constant("MMU_ATTR_DEVICE"),
           "#MMU_ATTR_DEVICE is $%X, the headers give $%X"
           % (lib_constant("MMU_ATTR_DEVICE"), dev))
    expect(nc == lib_constant("MMU_ATTR_NORMAL_NC"),
           "#MMU_ATTR_NORMAL_NC is $%X, the headers give $%X"
           % (lib_constant("MMU_ATTR_NORMAL_NC"), nc))

    # Normal Write-Back Cacheable: the same descriptor with the memory-type
    # index moved from MT_NORMAL_NC to MT_NORMAL.
    wb = (1 << 0) | (mt["MT_NORMAL"] << 2) | (3 << 8) | (1 << 10)
    expect(wb == lib_constant("MMU_ATTR_NORMAL_WB"),
           "#MMU_ATTR_NORMAL_WB is $%X, the headers give $%X"
           % (lib_constant("MMU_ATTR_NORMAL_WB"), wb))

    # WHICH ONE DRAM ACTUALLY GETS IS A CONFIGURATION, so the gate follows
    # #MMU_DRAM_ATTR - BUT IT IS NOT A RUBBER STAMP.  The value must be ONE
    # OF THE TWO the definitions derive.
    dram = lib_constant("MMU_DRAM_ATTR")
    expect(dram in (nc, wb),
           "#MMU_DRAM_ATTR is $%X, which is neither Normal NC $%X nor "
           "Normal WB $%X - DRAM must be one of the two" % (dram, nc, wb))

    cr_m = 1 << UBOOT_SYSTEM_CR_M_SHIFT
    expect(cr_m == lib_constant("MMU_SCTLR_M"),
           "#MMU_SCTLR_M is %d, arm system.h gives %d"
           % (lib_constant("MMU_SCTLR_M"), cr_m))

    print("constants recomputed from the pinned U-Boot v2025.01 definitions:")
    print("   MAIR_EL2        $%016X" % mair)
    print("   TCR_EL2         $%016X" % tcr)
    print("   attr Device     $%03X" % dev)
    print("   attr Normal NC  $%03X" % nc)
    print("   attr Normal WB  $%03X" % wb)
    print("   DRAM is mapped  $%03X   (%s)"
          % (dram, "CACHEABLE" if dram == wb else "non-cacheable"))
    print("   SCTLR CR_M      %d" % cr_m)
    print()

    # -- run the probe and check every descriptor ----------------------
    with tempfile.TemporaryDirectory(prefix="mmucheck-") as td:
        img = pathlib.Path(td) / "mmucheck.img"
        build(compiler, probe, img)
        mem, uart, msr_writes = run(img)
    text = uart.decode("utf-8", "replace")
    l1_want, l2_want = expected_map(dev, dram)

    bad = 0
    for i, want in enumerate(l1_want):
        got = read_u64(mem, TABLES + i * 8)
        if got != want:
            bad += 1
            if bad <= 5:
                fails.append("L1 slot %d is $%016X, expected $%016X"
                             % (i, got, want))
    for i, want in enumerate(l2_want):
        got = read_u64(mem, TABLES + 4096 + i * 8)
        if got != want:
            bad += 1
            if bad <= 5:
                fails.append("L2 slot %d is $%016X, expected $%016X"
                             % (i, got, want))
    if bad > 5:
        fails.append("...and %d more wrong descriptors" % (bad - 5))
    count += 576
    print("descriptors: 64 level-1 + 512 level-2 checked, %d wrong" % bad)

    # -- the two whose absence is silent on the bench ------------------
    pcie = read_u64(mem, TABLES + 24 * 8)
    expect(pcie == (24 << 30) | dev,
           "L1 slot 24 is $%016X - the PCIe outbound window at CPU "
           "$6_0000_0000 is NOT mapped Device. USB would die silently."
           % pcie)
    print("PCIe outbound   L1 slot 24   $%016X" % pcie)

    al_slot = (0xFF800000 - 0xC0000000) >> 21
    armlocal = read_u64(mem, TABLES + 4096 + al_slot * 8)
    expect(armlocal == (0xFF800000 | dev),
           "the ARM-local window at $FF800000 is $%016X, not Device. "
           "Core 1 could never be released." % armlocal)
    print("ARM-local       L2 slot %-4d $%016X" % (al_slot, armlocal))

    expect(read_u64(mem, TABLES + 4096 + 479 * 8) == (0xFBE00000 | dram),
           "L2 slot 479, the top of DRAM, does not carry #MMU_DRAM_ATTR")
    expect(read_u64(mem, TABLES + 4096 + 480 * 8) == (0xFC000000 | dev),
           "L2 slot 480, the first peripheral slot, is not Device")
    print("DRAM/periph     L2 479/480   $%016X / $%016X"
          % (read_u64(mem, TABLES + 4096 + 479 * 8),
             read_u64(mem, TABLES + 4096 + 480 * 8)))
    print()

    # -- what the probe itself said ------------------------------------
    expect("build returned    $0000000000000000" in text,
           "MmuBuildTables() did not return 0")
    expect(("SCTLR_EL2 before  $%016X" % SCTLR_EL2_AT_ENTRY) in text,
           "the probe did not report the entry SCTLR_EL2")
    print("probe output, last lines:")
    for line in text.rstrip().splitlines()[-5:]:
        print("   " + line)
    print("system-register writes recorded: %s"
          % ", ".join(n for n, _ in msr_writes))
    print()

    if fails:
        print("a64_mmu_check: FAIL %d of %d" % (len(fails), count))
        for f in fails:
            print("   " + f)
        return 1
    print("a64_mmu_check: PASS %d checks - the table builder is proven; the "
          "ENABLE is not, and no gate on this machine can prove it. See the "
          "docstring." % count)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"),
                    help="PureMetalForge.exe (default: $PMF_COMPILER)")
    args = ap.parse_args(argv)
    if not args.compiler:
        ap.error("No compiler was named. Pass --compiler with the path to "
                 "PureMetalForge.exe, or set PMF_COMPILER.")
    return run_gate(args.compiler)


if __name__ == "__main__":
    raise SystemExit(main())

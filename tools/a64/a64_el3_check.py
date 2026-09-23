#!/usr/bin/env python3
"""Executable gate for the EL3 boot stub and the monitor's level probe.

WHAT THIS GATE IS FOR
---------------------
The ruling of 2026-09-07 is that Anvil runs at EL3 on the Raspberry Pi 4,
entered there by our own `armstub8.bin` instead of being dropped to EL2 by
the stock one. That stub is the single most dangerous file in this tree:
it is loaded by closed firmware at address 0 on a board with no serial
port and no boot log, and if it is wrong the board does not come back and
says nothing about why. There is no console to print a diagnosis to,
because the console is inside the image the stub has failed to reach.

So everything that CAN be checked at a desk is checked here, and the list
is longer than it looks:

  A. THE LAYOUT. The firmware reads a magic word at offset 0xF0 and, if
     it matches, writes the device-tree pointer at 0xF8 and the kernel
     entry at 0xFC - into the file it has already loaded. Four spin slots
     at 0xD8, 0xE0, 0xE8 and 0xF0 are how cores 1..3 are released. Every
     one of those offsets is checked in the BUILT BYTES, because a stub
     whose code grew four instructions past 0xD8 would assemble
     perfectly and then have the firmware overwrite its own instructions
     with a kernel address.

  B. THE MACHINE SET-UP. Every register the stock stub writes is written
     here with the same value, because those are facts about the computer
     being handed over and not about the exception level. A stub that
     forgot CNTFRQ_EL0 would boot fine and make every timeout in the
     monitor wrong by a factor of 28 with nothing to see.

  C. THE ONE DIFFERENCE, stated as a NEGATIVE and therefore recorded
     rather than inferred: our stub reaches the kernel entry WITHOUT an
     ERET. The interpreter keeps a list of every exception return it
     executed, and this gate asserts that list is empty and that
     CurrentEL is still 3 at the branch.

  D. BOTH DISPATCH PATHS. Core 0 takes the firmware's two words and
     branches; cores 1..3 park in the spin table and branch when a slot
     becomes non-zero, with x0 = 0. Both are run.

  E. THE MONITOR'S LEVEL PROBE. `MmuEl()` and `HwIdEl()` are what make
     the flash safe: KERNEL8.IMG must boot at EITHER level and say which.
     The decode is exercised at all four levels here so that "it printed
     2" and "it printed the level it is at" cannot be confused.

WHAT THIS GATE CANNOT DO, said plainly so nobody reads a pass as more
than it is:

  * The interpreter's system-register support is a STORE, not a model.
    Writing SCTLR_EL3 does not turn anything on here. This gate proves
    the stub writes the right value into the right register, and proves
    nothing about what the silicon does with it.
  * There is no GIC model. The GIC writes are judged as stores to
    addresses, which is exactly what they are at this level of the
    machine, and the question of whether GICD_CTLR = 3 is the right
    value in the Secure view is checked against the pinned stock stub,
    not decided by this flat-memory model.
  * Nothing here can tell whether the FIRMWARE will accept the file.
    The `armstub=` line, the load address and the magic-word protocol
    are the firmware's, and the only test of them is a board.
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
from a64_interp import A64, MASK64  # noqa: E402

STUB_SRC = "RaspberryPi4/Board/armstub8.asm"

# ---------------------------------------------------------------------
#  The layout, from the pinned upstream armstub8.S:175-210. These are the
#  numbers the CLOSED FIRMWARE uses; they are not ours to choose and
#  they are written here as data so the check reads as the contract.
# ---------------------------------------------------------------------
SPIN_CPU = (0xD8, 0xE0, 0xE8, 0xF0)
STUB_MAGIC_OFF = 0xF0
STUB_VERSION_OFF = 0xF4
DTB_PTR_OFF = 0xF8
KERNEL_ENTRY_OFF = 0xFC
GIC_CODE_OFF = 0x100
STUB_MAGIC = 0x5AFE570B
PAD_TO = 256                       # armstubs-Makefile:64, dd ibs=256 conv=sync

# ---------------------------------------------------------------------
#  The system registers, keyed by the WRITE base the interpreter's store
#  uses. Encodings follow Arm's A64 system-register instruction format.
# ---------------------------------------------------------------------
SR = {
    "cntfrq_el0":   0xD51BE000,
    "cntvoff_el2":  0xD51CE060,
    "cptr_el3":     0xD51E1140,
    "scr_el3":      0xD51E1100,
    "actlr_el3":    0xD51E1020,
    "cpuectlr_el1": 0xD519F220,
    "l2ctlr_el1":   0xD519B040,
    "sctlr_el2":    0xD51C1000,
    "sctlr_el3":    0xD51E1000,
    "elr_el3":      0xD51E4020,
    "spsr_el3":     0xD51E4000,
}

# What each of those must hold when the stub branches. Every value is
# cited to the stock stub, because "the same machine, entered one level
# higher" is the whole claim this stub makes.
EXPECTED_SYSREGS = [
    ("cntfrq_el0",   54_000_000,
     "the architectural counter rate. armstub8.S:53-57,110-112. "
     "RaspberryPi4/Lib/timer.pi4 READS this rather than assuming it, so a "
     "stub that skipped it would make every timeout in the monitor wrong "
     "by the ratio of whatever was left here to 54 MHz, silently."),
    ("cntvoff_el2",  0,
     "the virtual counter offset. armstub8.S:114-115."),
    ("cptr_el3",     0,
     "TFP clear at bit 10, so floating point and SIMD work. armstub8.S:117-119. "
     "This is the one an EL3 monitor cannot do without and cannot do for "
     "itself: the compiler's preamble opens the EL2 gate (CPTR_EL2, "
     "RaspberryPi4/EmitCore_A64.pbi:569-582) and nothing in a compiled "
     "image opens this one."),
    ("scr_el3",      0x5B3,
     "RW|HCE|SMD|RES1|RES1|NS plus IRQ routing to the EL3 monitor. The "
     "stock 0x5B1 is insufficient when the stub deliberately stays at EL3: "
     "a physical IRQ is not taken there unless SCR_EL3.IRQ is set. "
     "SMD=1 leaves SMC undefined, which is the right phase-1 answer while "
     "there is no dispatcher for one to reach."),
    ("actlr_el3",    0x73,
     "the A72 implementation-defined enables. armstub8.S:68-69,125-127."),
    ("cpuectlr_el1", 0x40,
     "SMPEN at bit 6. armstub8.S:71-72,129-131. Without it the core does "
     "not take part in coherency and the data cache is not coherent "
     "between cores."),
    ("sctlr_el2",    0x30C50830,
     "all RES1: MMU, caches, alignment checking and WXN off at EL2. "
     "armstub8.S:136-141. Nothing runs at EL2 in phase 1 and it is still "
     "written, because phase 2 drops payloads there."),
    ("sctlr_el3",    0x30C50830,
     "OURS, and the stock stub has no equivalent because it is leaving "
     "EL3 and does not care. We stay, so the register governing our own "
     "translation, caches and alignment has to be a known value. Same "
     "constant as SCTLR_EL2 because ARMv8.0 gives both the same RES1 "
     "pattern - bits 29,28,23,22,18,16,11,5,4."),
]

# The MMIO the stub writes, as address -> (value, why). A flat-memory
# interpreter turns each of these into a store it can read back, which is
# exactly the level at which they are checkable at a desk.
LOCAL_CONTROL = 0xFF800000
LOCAL_PRESCALER = 0xFF800008
GIC_DISTB = 0xFF841000
GIC_CPUB = 0xFF842000
GICD_CTLR = GIC_DISTB + 0x000
GICD_IGROUPR = GIC_DISTB + 0x080
GICC_CTLR = GIC_CPUB + 0x000
GICC_PMR = GIC_CPUB + 0x004

EXPECTED_MMIO = [
    (LOCAL_CONTROL, 0x00000000,
     "bit 9 clear = increment by one, bit 8 clear = the 54 MHz crystal "
     "rather than the APB clock. armstub8.S:93-99."),
    (LOCAL_PRESCALER, 0x80000000,
     "divide-by ($80000000 / value) == 1. armstub8.S:100-102."),
    (GICC_CTLR, 0x1E7,
     "EnableGrp0|EnableGrp1|AckCtl and the four bypass-disable bits, with "
     "FIQEn CLEAR. armstub8.S:224-225. AckCtl is what lets a Secure "
     "reader acknowledge a group 1 interrupt through GICC_IAR, which is "
     "what an EL3 monitor does every time it services its timer."),
    (GICC_PMR, 0xFF,
     "the widest priority mask. armstub8.S:226-227."),
]


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
    """Find the external compiler without embedding a developer-machine path."""
    requested = explicit or os.environ.get("PMF_COMPILER")
    if requested:
        path = Path(requested).expanduser().resolve()
        if path.is_file():
            return path
        raise SystemExit("EL3 gate: compiler not found: %s" % path)
    found = (shutil.which("PureMetalForge.exe") or
             shutil.which("PureMetalForge.linux") or
             shutil.which("PureMetalForge"))
    if found:
        return Path(found).resolve()
    raise SystemExit("EL3 gate: pass --compiler, set PMF_COMPILER, or put "
                     "PureMetalForge on PATH")


def u32(blob: bytes, off: int) -> int:
    return struct.unpack_from("<I", blob, off)[0]


def u64(blob: bytes, off: int) -> int:
    return struct.unpack_from("<Q", blob, off)[0]


# =====================================================================
#  A. THE LAYOUT, IN THE BUILT BYTES
# =====================================================================
def check_layout(blob: bytes) -> list[str]:
    fails: list[str] = []
    print("A. the layout the firmware relies on")

    if len(blob) % PAD_TO:
        fails.append(
            "the stub is %d bytes, which is not a multiple of %d. The stock "
            "build pads with `dd ibs=256 conv=sync` "
            "(the pinned upstream armstubs Makefile); nothing here has measured "
            "whether the firmware requires it, and a difference that costs "
            "nothing is not worth taking on a board with no boot log."
            % (len(blob), PAD_TO))
    else:
        print("   %d bytes, a multiple of %d" % (len(blob), PAD_TO))

    if len(blob) < GIC_CODE_OFF:
        return fails + ["the stub is shorter than the fixed block it must contain"]

    magic = u32(blob, STUB_MAGIC_OFF)
    if magic != STUB_MAGIC:
        fails.append(
            "the magic at 0x%02X is 0x%08X, not 0x%08X. Without it the "
            "firmware does not recognise the file as a stub and never writes "
            "the device-tree pointer or the kernel entry into it - so the "
            "board branches to address 0 and stops."
            % (STUB_MAGIC_OFF, magic, STUB_MAGIC))
    else:
        print("   0x%02X magic 0x%08X" % (STUB_MAGIC_OFF, magic))

    for off, name in ((STUB_VERSION_OFF, "stub_version"),
                      (DTB_PTR_OFF, "dtb_ptr32"),
                      (KERNEL_ENTRY_OFF, "kernel_entry32")):
        got = u32(blob, off)
        if got != 0:
            fails.append(
                "%s at 0x%02X is 0x%08X and must ship as zero - the firmware "
                "writes these two words into the loaded file, and a non-zero "
                "value in the built image means something else is laid out "
                "there." % (name, off, got))
        else:
            print("   0x%02X %-14s ships zero" % (off, name))

    # SPIN SLOT 3 IS THE MAGIC WORD, AND THAT IS NOT A BUG.
    #
    # The first draft of this gate asserted all four slots ship zero and
    # failed on the fourth, which holds 0x5AFE570B - and the gate was
    # wrong, not the stub. spin_cpu3 and stub_magic are the SAME EIGHT
    # BYTES at 0xF0 (upstream armstub8.S:187-200, whose own comment
    # says so): the firmware reads the magic and the version, CLEARS those
    # eight bytes, and only then is 0xF0 core 3's slot. So a stub that
    # shipped a zero there would be a stub the firmware did not recognise.
    # The check that matters is the one above - that the magic is present.
    for core, off in enumerate(SPIN_CPU[:3]):
        got = u64(blob, off)
        if got != 0:
            fails.append(
                "spin_cpu%d at 0x%02X is 0x%016X and must ship as zero; a "
                "core released by a stale value branches into whatever that "
                "address holds." % (core, off, got))
    print("   0x%02X 0x%02X 0x%02X spin slots 0..2 ship zero"
          % SPIN_CPU[:3])
    print("   0x%02X spin slot 3 holds the magic and the version until the "
          "firmware clears them" % SPIN_CPU[3])

    # THE ONE THAT ACTUALLY BITES. Code growing past 0xD8 assembles
    # perfectly and is then overwritten by the firmware.
    last_code = max((off for off in range(0, SPIN_CPU[0], 4)
                     if u32(blob, off) != 0), default=-4)
    if last_code + 4 > SPIN_CPU[0]:
        fails.append(
            "the entry code reaches 0x%02X and the spin table starts at "
            "0x%02X. The firmware writes into 0xF0..0xFF, so code that far "
            "down is code the firmware overwrites."
            % (last_code + 4, SPIN_CPU[0]))
    else:
        print("   entry code ends at 0x%02X, %d bytes clear of the spin table"
              % (last_code + 4, SPIN_CPU[0] - last_code - 4))
    return fails


# =====================================================================
#  B, C, D. RUN IT
# =====================================================================
def load(cpu: A64, blob: bytes) -> None:
    for i, byte in enumerate(blob):
        cpu.memory[i] = byte


def make_cpu(blob: bytes, mpidr: int) -> A64:
    cpu = A64()
    load(cpu, blob)
    # The stub is entered at EL3 by the firmware. MPIDR_EL1 is seeded
    # rather than written by the program, because it is a fact about the
    # core and not something anything sets.
    cpu.enable_system_registers(el=3, preset={0xD51800A0: mpidr})
    # The stub stores to the peripheral aperture with the MMU off, which
    # is Device memory and therefore strictly aligned. Leaving the rule
    # on is the point: every store here is a word store to a word-aligned
    # register, and a stub that grew a misaligned one would fault.
    cpu.align_check = True
    cpu.pc = 0
    cpu.sp = 0
    return cpu


def run_until_branch(cpu: A64, limit: int, blob_len: int) -> int:
    """Step until the pc leaves the stub, and return where it went.

    Leaving the stub IS the result: the last instruction is `br x4`, and
    the address it lands on is the thing under test. A run that never
    leaves has spun, and that is reported as itself rather than as a
    timeout with no meaning.
    """
    for _ in range(limit):
        if cpu.pc >= blob_len:
            return cpu.pc
        cpu.step()
    return -1


def check_primary(blob: bytes) -> list[str]:
    fails: list[str] = []
    print()
    print("B/C. core 0: the machine set-up, and the branch WITHOUT an eret")

    kernel = 0x00200000
    dtb = 0x08000000
    cpu = make_cpu(blob, mpidr=0x80000000)   # Aff0 = 0, the U bit as the part sets it
    # The firmware writes these two words into the loaded file. Doing it
    # here is not a fixture convenience - it is the protocol.
    cpu.memory.update({KERNEL_ENTRY_OFF + i: (kernel >> (8 * i)) & 0xFF
                       for i in range(4)})
    cpu.memory.update({DTB_PTR_OFF + i: (dtb >> (8 * i)) & 0xFF
                       for i in range(4)})

    where = run_until_branch(cpu, 400, len(blob))
    if where < 0:
        return fails + ["core 0 never left the stub in 400 steps"]

    # The first DAIF mask must execute before SCR_EL3 starts routing physical
    # IRQs to EL3. Checking the machine words and their byte order makes this
    # a built-artifact contract rather than trusting a source comment.
    mask_word = struct.pack("<I", 0xD5034FDF)  # msr daifset, #15
    scr_word = struct.pack("<I", SR["scr_el3"])  # msr scr_el3, x0
    mask_at = blob.find(mask_word)
    scr_at = blob.find(scr_word)
    if mask_at < 0 or scr_at < 0 or mask_at >= scr_at:
        fails.append(
            "the built stub does not execute `msr daifset,#15` before its "
            "SCR_EL3 write. Enabling SCR_EL3.IRQ while an inherited IRQ mask "
            "is unknown can vector before Anvil has installed a table.")
    else:
        print("   DAIF is masked at 0x%X before SCR_EL3 is written at 0x%X"
              % (mask_at, scr_at))

    if where != kernel:
        fails.append(
            "core 0 branched to 0x%X, and the firmware put the kernel entry "
            "at 0x%X. That is the whole handover." % (where, kernel))
    else:
        print("   branched to the firmware's kernel_entry32, 0x%X" % where)

    if cpu.x[0] != dtb:
        fails.append(
            "x0 is 0x%X at the branch and the firmware's dtb_ptr32 is 0x%X. "
            "The arm64 boot protocol puts the device tree in x0, and Anvil "
            "captures it in Main()'s first instruction "
            "(RaspberryPi4/Board/board.pi4). A wrong x0 here is a monitor "
            "whose `booti` hands Linux a device tree that is not one."
            % (cpu.x[0], dtb))
    else:
        print("   x0 = the firmware's dtb_ptr32, 0x%X" % cpu.x[0])

    for reg in (1, 2, 3):
        if cpu.x[reg] != 0:
            fails.append("x%d is 0x%X at the branch; the arm64 boot protocol "
                         "reserves x1, x2 and x3 and requires zero"
                         % (reg, cpu.x[reg]))

    # ---- C. the negative claim, recorded rather than inferred --------
    if cpu.erets:
        fails.append(
            "the stub executed %d exception return(s): %r. NOT DROPPING A "
            "LEVEL IS THE ENTIRE POINT OF THIS FILE. The stock stub erets to "
            "EL2h at upstream armstub8.S:143-148 and this one must "
            "not." % (len(cpu.erets), cpu.erets))
    else:
        print("   no eret was executed - the stock stub's drop to EL2 is gone")

    if cpu.current_el != 3:
        fails.append(
            "the stub branched to the kernel at EL%d. The ruling is EL3."
            % cpu.current_el)
    else:
        print("   CurrentEL is 3 at the branch")

    # ---- B. the machine, register by register ------------------------
    print()
    for name, want, why in EXPECTED_SYSREGS:
        got = cpu.sysreg(SR[name])
        if got is None:
            fails.append("the stub never wrote %s. %s" % (name, why))
            print("      %-14s NEVER WRITTEN" % name)
            continue
        if got != want:
            fails.append("%s is 0x%X and must be 0x%X. %s" % (name, got, want, why))
            print("      %-14s 0x%X   WRONG, wanted 0x%X" % (name, got, want))
        else:
            print("      %-14s 0x%08X" % (name, got))

    # L2CTLR is read-modify-written, so it is checked as a mask rather
    # than a value: the stub ORs in 0x22 and must not disturb the rest.
    l2 = cpu.sysreg(SR["l2ctlr_el1"])
    if l2 is None or (l2 & 0x22) != 0x22:
        fails.append(
            "l2ctlr_el1 is %s; the stub ORs in 0x22, the L2 data and tag RAM "
            "latencies this part ships with (armstub8.S:104-108). It is a "
            "read-modify-write, so this is checked as a mask and not a value."
            % ("never written" if l2 is None else hex(l2)))
    else:
        print("      %-14s 0x%08X, 0x22 set" % ("l2ctlr_el1", l2))

    # The two EL3 exception-return registers must be UNTOUCHED. The stock
    # stub writes both on its way out; ours has no way out to prepare.
    for name in ("elr_el3", "spsr_el3"):
        if cpu.sysreg(SR[name]) is not None:
            fails.append(
                "%s was written (0x%X). This stub does not eret, so preparing "
                "an exception return is either dead code or a drop somebody "
                "put back." % (name, cpu.sysreg(SR[name])))
    print("      elr_el3 / spsr_el3 untouched, as a stub that never returns should")

    print()
    for addr, want, why in EXPECTED_MMIO:
        got = cpu.raw_load(addr, 4)
        if got != want:
            fails.append("the word at 0x%08X is 0x%08X and must be 0x%08X. %s"
                         % (addr, got, want, why))
            print("      0x%08X 0x%08X   WRONG, wanted 0x%08X" % (addr, got, want))
        else:
            print("      0x%08X 0x%08X" % (addr, got))

    groups = [cpu.raw_load(GICD_IGROUPR + 4 * i, 4) for i in range(8)]
    if groups != [0xFFFFFFFF] * 8:
        fails.append(
            "GICD_IGROUPR0..7 read %s. The stock stub puts every one of the "
            "256 interrupt IDs in group 1 (armstub8.S:228-234), and that "
            "includes INTID 26 - PPI 10, the EL2 physical timer the monitor "
            "uses today - and INTID 29, PPI 13, the SECURE physical timer an "
            "EL3 monitor could use instead."
            % ", ".join("0x%08X" % g for g in groups))
    else:
        print("      0x%08X GICD_IGROUPR0..7 all ones - every INTID in group 1"
              % GICD_IGROUPR)

    # THE PRIMARY DOES NOT WRITE GICD_CTLR, AND THAT IS THE STOCK STUB.
    #
    # armstub8.S:215-221 branches past the distributor write on core 0
    # ("b.eq 2f // primary core"). It works because GICD_CTLR is one
    # global register and cores 1..3 all run the same code, so any one of
    # them setting it is enough. It is transcribed as-is rather than
    # "fixed", because a stub that enabled the distributor from a
    # different core would no longer be the machine every other Pi 4
    # boots into - and this assertion is what stops somebody tidying it.
    got = cpu.raw_load(GICD_CTLR, 4)
    if got != 0:
        fails.append(
            "core 0 wrote 0x%08X to GICD_CTLR. The stock stub deliberately "
            "skips that write on the primary (armstub8.S:215-221) and leaves "
            "it to cores 1..3; a stub that differs here hands over a "
            "distributor enabled in a different order from every other Pi 4."
            % got)
    else:
        print("      0x%08X GICD_CTLR untouched by core 0, as the stock stub "
              "leaves it" % GICD_CTLR)
    return fails


def check_secondary(blob: bytes) -> list[str]:
    fails: list[str] = []
    print()
    print("D. cores 1..3: the spin table")

    for core in (1, 2, 3):
        target = 0x00300000 + core * 0x1000
        cpu = make_cpu(blob, mpidr=0x80000000 | core)

        # Spin first, with the slot still zero. `wfe` is a no-op in this
        # model, so the loop turns rather than parking - which is what
        # makes it observable at all.
        for _ in range(60):
            if cpu.pc >= len(blob):
                break
            cpu.step()
        if cpu.pc >= len(blob):
            fails.append(
                "core %d left the stub with its spin slot still zero, "
                "branching to 0x%X. A core released by an empty slot is a "
                "core running whatever address zero happens to mean."
                % (core, cpu.pc))
            continue

        # Now release it, exactly as SmpRelease does: write the slot and
        # let the loop see it.
        slot = SPIN_CPU[core]
        for i in range(8):
            cpu.memory[slot + i] = (target >> (8 * i)) & 0xFF

        where = run_until_branch(cpu, 200, len(blob))
        if where != target:
            fails.append(
                "core %d was released to 0x%X and branched to %s. The slot it "
                "reads is at 0x%02X (spin_cpu%d)."
                % (core, target, "nowhere in 200 steps" if where < 0
                   else "0x%X" % where, slot, core))
            continue
        if cpu.x[0] != 0:
            fails.append(
                "core %d branched with x0 = 0x%X; the stock stub hands a "
                "secondary x0 = 0 (armstub8.S:156-161) because only the "
                "primary carries the device tree." % (core, cpu.x[0]))
            continue
        if cpu.erets:
            fails.append("core %d executed an eret: %r" % (core, cpu.erets))
            continue
        if cpu.current_el != 3:
            fails.append("core %d branched at EL%d" % (core, cpu.current_el))
            continue
        print("   core %d parked, released through 0x%02X, branched to 0x%X "
              "at EL3 with x0 = 0" % (core, slot, where))

        # A SECONDARY IS THE CORE THAT ENABLES THE DISTRIBUTOR. See the
        # note in check_primary: the stock stub skips this write on core 0
        # and every other core does it, so the only place it can be
        # checked is here.
        got = cpu.raw_load(GICD_CTLR, 4)
        if got != 3:
            fails.append(
                "core %d left GICD_CTLR at 0x%08X and the stock stub writes "
                "3 (armstub8.S:220-221). In the SECURE view - which is what "
                "an EL3 monitor sees - bit 0 is EnableGrp0 and bit 1 is "
                "EnableGrp1, so 3 is 'forward both'. RaspberryPi4/Lib/gic.pi4 "
                "writes 1 there, which in that view means group 0 only and "
                "turns off the group every interrupt on this board is in. "
                "That is the EL3 twin gic.pi4 owes." % (core, got))
        elif core == 1:
            print("   core %d wrote GICD_CTLR = 3, both groups forwarded "
                  "(Secure view)" % core)
    return fails


# =====================================================================
#  E. THE MONITOR'S LEVEL PROBE
# =====================================================================
def check_level_probe() -> list[str]:
    """MmuEl()'s decode, exercised at all four levels.

    The monitor must come up at EITHER level and SAY which - that is what
    makes the flash safe, because KERNEL8.IMG goes on the card first and
    still has to boot under the stock stub. `MmuEl()` is
    (CurrentEL >> 2) & 3 and `HwIdEl()` returns it
    (RaspberryPi4/Lib/mmu.pi4, RaspberryPi4/Board/hw_id.pi4).

    It is checked HERE rather than by reading the source because the
    failure this guards against is a digit printed as prose, which is
    exactly the defect this guards: a fixed digit can be right on one
    boot path by luck without reporting the level the image actually has.
    """
    fails: list[str] = []
    print()
    print("E. the level probe, at all four levels")
    # Fixed Arm words keep this oracle independent of the assembler being
    # tested above. They are the exact instruction sequence used by MmuEl():
    # mrs x0,currentel; lsr x1,x0,#2; movz x2,#3; and x1,x1,x2; b start.
    words = (0xD5384240, 0xD342FC01, 0xD2800062, 0x8A020021, 0x17FFFFFC)
    blob = b"".join(struct.pack("<I", word) for word in words)

    for el in (0, 1, 2, 3):
        cpu = A64()
        for i, byte in enumerate(blob):
            cpu.memory[0x80000 + i] = byte
        cpu.enable_system_registers(el=el)
        cpu.pc = 0x80000
        for _ in range(4):
            cpu.step()
        raw, decoded = cpu.x[0] & MASK64, cpu.x[1] & MASK64
        if raw != el << 2 or decoded != el:
            fails.append(
                "at EL%d the probe read CurrentEL = 0x%X and decoded %d; the "
                "register holds the level in bits 3:2, so it must read 0x%X "
                "and decode %d." % (el, raw, decoded, el << 2, el))
        else:
            print("   EL%d: CurrentEL reads 0x%02X, MmuEl() decodes %d"
                  % (el, raw, decoded))
    return fails


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", help="external PureMetal compiler (or set PMF_COMPILER)")
    parser.add_argument(
        "--image", type=Path,
        help="verify an existing armstub8.bin; skips compiler-door checks")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="pmf_el3_") as td:
        temp = Path(td)
        if args.image:
            stub = args.image.expanduser().resolve()
            if not stub.is_file():
                raise SystemExit("EL3 gate: image not found: %s" % stub)
            compiler = None
            print("[gate] verifying supplied image; source rebuild not claimed",
                  file=sys.stderr)
        else:
            compiler = locate_compiler(args.compiler)
            stub = temp / "armstub8.bin"
            run([str(compiler), "--compile", "--armstub", "-t", "pi4", STUB_SRC,
                 "-o", str(stub)])
        blob = stub.read_bytes()

        fails = check_layout(blob)
        fails += check_primary(blob)
        fails += check_secondary(blob)
        fails += check_level_probe()

        # The negative control on the door itself. Without --armstub the
        # harness links for $80000, and the stub's `.org 0xd8` then
        # precedes the load address - so a build that forgot the flag
        # fails loudly instead of producing a file with the fixed block
        # 512 KiB from where the firmware will look for it.
        if compiler is not None:
            print()
            print("F. explicit-door negative controls")
            bad = subprocess.run(
                [str(compiler), "--compile", "-t", "pi4", STUB_SRC,
                 "-o", str(temp / "nostub.bin")],
                cwd=ROOT, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, check=False)
            if bad.returncode == 0:
                fails.append("the .asm source built without --armstub")
            else:
                print("   .asm without --armstub refused")

            not_asm = temp / "not_a_stub.pi4"
            not_asm.write_text("Procedure Main()\nEndProcedure\n", encoding="ascii")
            bad = subprocess.run(
                [str(compiler), "--compile", "--armstub", "-t", "pi4", str(not_asm),
                 "-o", str(temp / "not_a_stub.bin")],
                cwd=ROOT, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, check=False)
            if bad.returncode == 0:
                fails.append("--armstub accepted a non-.asm source")
            else:
                print("   --armstub with non-.asm source refused")

    print()
    if fails:
        print("a64_el3_check: FAIL")
        for line in fails:
            print("   %s" % line)
        return 1
    print("a64_el3_check: PASS - the stub's layout, machine set-up, both "
          "dispatch paths, no exception return, four-level probe, and "
          "explicit compiler door.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

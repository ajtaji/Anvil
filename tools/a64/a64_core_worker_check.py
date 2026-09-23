#!/usr/bin/env python3
"""Gate the inactive BCM2711 cache-coherent raw-secondary milestone.

This compiles the real fixture, inspects emitted A64, and runs independent A64
interpreter instances over one shared byte dictionary.  The interpreter has no
cache, TLB, store buffer, WFE/SEV timing or simultaneous execution; therefore a
PASS is not physical proof of coherency or parallelism.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
import build as anvil_build  # noqa: E402
from pmf_compiler import resolve_compiler  # noqa: E402

CORE = ROOT / "RaspberryPi4" / "Lib" / "core_worker_impl.pi4"
MMUSEC = ROOT / "RaspberryPi4" / "Lib" / "mmu_secondary.pi4"
MEMMAP = ROOT / "RaspberryPi4" / "Board" / "memmap.pi4"
FIXTURE = ROOT / "RaspberryPi4" / "Tests" / "core_worker_emitted_gate.pi4"
SCRATCH_FIXTURE = ROOT / "RaspberryPi4" / "Tests" / "core_worker_scratch_gate.pi4"
STUB = ROOT / "RaspberryPi4" / "Board" / "armstub8.asm"
INTERP = ROOT / "tools" / "a64" / "a64_interp.py"
LOAD = 0x00400000
STACK = 0x03000000
RETURN_PC = 0xDEAD0000
STRIDE = 256
ALIGN = 256
MAGIC = 0x43525742
PREPARED = 1
READY = 2
SCTLR_CACHED = 0x30C51835
MPIDR_EL1_KEY = 0xD51800A0
SCTLR_EL2_KEY = 0xD51C1000
SCTLR_EL3_KEY = 0xD51E1000
CPUECTLR_EL1_KEY = 0xD519F220
CCSIDR_EL1_KEY = 0xD5190000
SMPEN = 0x40
A72_L1D_CCSIDR = 2 | (1 << 3) | (255 << 13)  # 64-byte, 2-way, 256-set


class Checks:
    def __init__(self) -> None:
        self.count = 0

    def yes(self, value: bool, message: str) -> None:
        self.count += 1
        if not value:
            raise AssertionError(message)


def proc(text: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^Procedure(?:Naked|\.i)?\s+{re.escape(name)}\([^\n]*\)\s*$"
        rf"(.*?)^EndProcedure\s*$", text)
    if not match:
        raise AssertionError(f"missing procedure {name}")
    return match.group(0)


def mon_regions(memmap):
    """The board's own region count, read from memmap.pi4 rather than typed here: the
    reservation this gate protects is one region among however many the map has today,
    and a gate that counts them stops being about the reservation."""
    m = re.search(r"Procedure\.i HwMonRegions\(\)\s*\r?\n\s*ProcedureReturn (\d+)", memmap)
    if not m:
        raise SystemExit("memmap.pi4 no longer declares HwMonRegions() with a literal count")
    return int(m.group(1))


def stack_region(memmap):
    """The region index the map gives the raw-secondary stack reservation, read from
    HwMonRegionLo's own Case list. The mutants below shrink the count to exactly this
    index, which drops the reservation from the enumeration and nothing else."""
    m = re.search(r"Case (\d+) : ProcedureReturn #CORE_RAW_STACK_LO", memmap)
    if not m:
        raise SystemExit("memmap.pi4 no longer enumerates #CORE_RAW_STACK_LO as a region")
    return int(m.group(1))


def in_order(c: Checks, text: str, needles: list[str], where: str) -> None:
    cursor = -1
    for needle in needles:
        found = text.find(needle, cursor + 1)
        c.yes(found >= 0, f"{where}: missing {needle}")
        c.yes(found > cursor, f"{where}: out of order at {needle}")
        cursor = found


def source_checks(c: Checks, core: str, mmu: str, memmap: str) -> None:
    secondary = proc(core, "CoreRawSecondary")
    prepare = proc(core, "CoreRawPrepare")
    release = proc(core, "CoreRawRelease")
    wait = proc(core, "CoreRawWaitReady")
    result = proc(core, "CoreRawResult")
    acquire = proc(core, "coreRaw_LoadAcquire")
    stack_owned = proc(core, "CoreRawStackOwned")
    join = proc(mmu, "MmuSecondaryJoinRaw")

    c.yes(re.search(r"ProcedureNaked CoreRawSecondary\(\)", secondary) is not None,
          "secondary entry must be naked and parameterless")
    c.yes(re.search(r"ProcedureNaked MmuSecondaryJoinRaw\(\)", join) is not None,
          "MMU join must be naked and parameterless")
    c.yes("global_" not in join.lower(), "raw MMU join must not touch BSS")
    c.yes(not re.search(r"\b(?:sp|x30)\b", join, re.I),
          "raw MMU join must not touch stack or link register")
    c.yes("bl " not in join.lower(), "raw MMU join must not call anything")
    c.yes(secondary.lower().count("bl   mmusecondaryjoinraw") == 1,
          "secondary may make exactly one allowlisted raw join call")
    c.yes(len(re.findall(r"(?mi)^\s*bl\s+", secondary)) == 1,
          "secondary contains an unapproved call")

    for token in ("dc   isw", "ic   iallu", "tlbi alle3",
                  "ttbr0_el3", "tcr_el3", "mair_el3", "sctlr_el3"):
        c.yes(token in join, f"raw MMU join is missing {token}")
    for token in ("clidr_el1", "tlbi alle2", "ttbr0_el2", "sctlr_el2"):
        c.yes(token not in join, f"EL3/private-L1 join unexpectedly contains {token}")
    c.yes("movz x9, #4101" in join, "secondary join must require M/C/I")
    in_order(c, join,
             ["cmp  x9, #3", "movz x9, #4101",
              "mrs  x10, sctlr_el3", "and  x10, x10, x9",
              "cbnz x10, mmuSecJoinFail", "mrs  x10, cpuectlr_el1",
              "movz x9, #64", "cbz  x10, mmuSecJoinFail",
              "movz x14, #0", "msr  csselr_el1, x14", "dc   isw, x8"],
             "as-found cold SCTLR guard")
    c.yes(join.count("b.ne mmuSecJoinFail") >= 7,
          "EL/register/coherency mismatches must fail closed")

    in_order(c, secondary,
             ["mrs  x9, currentel", "cmp  x9, #3",
              "mrs  x10, sctlr_el3",
              "cbnz x10, coreRawSecondaryFail",
              "mrs  x10, cpuectlr_el1", "movz x11, #64",
              "cbz  x10, coreRawSecondaryFail",
              "adrp x9, global_core_raw_boot"],
             "register-only pre-DRAM cold guard")
    c.yes("If el <> 3" in prepare, "primary prepare must refuse non-EL3 callers")

    c.yes("Global Dim core_raw_boot.i" in core and
          "Global Dim core_raw_row.i" in core,
          "cold records and control rows must be separate allocations")
    c.yes("#CORE_RAW_ALIGN          = 256" in core and
          "#CORE_RAW_STRIDE         = 256" in core,
          "records and rows need distinct 256-byte strides")
    c.yes("add  x9, x9, #255" in secondary and
          "lsl  x10, x27, #8" in secondary,
          "secondary must independently align/index the cold record")
    c.yes("and  x27, x9, x10" in secondary and "mov  x1, x27" in secondary,
          "core ID must live in the join-preserved x27 register")
    c.yes("ldr  x26, [x9, #32]" in secondary,
          "secondary must load its explicit control-row address")

    in_order(c, prepare,
             ["PokeI(boot + #CORE_RAW_B_MAGIC", "MmuSecondaryTtbr0()",
              "MmuSecondaryTcr()", "MmuSecondaryMair()",
              "MmuCleanRange(boot, #CORE_RAW_STRIDE)",
              "MmuCleanRange(row, #CORE_RAW_STRIDE)"],
             "primary prepare")
    in_order(c, release,
             ["PokeI(box, entry)", "MmuCleanRange(box, 8)",
              "a64_barrier()", "a64_send_event()"],
             "spin release")
    c.yes("ldar x0, [x0]" in acquire, "primary must consume state with acquire")
    c.yes("stlr x9, [x2]" in secondary, "secondary must publish READY with release")
    c.yes(secondary.find("stlr x9, [x2]") > secondary.find("str  x9, [x2, #72]"),
          "READY must follow the final mapping/stack witness")
    c.yes(secondary.find("bl   MmuSecondaryJoinRaw") < secondary.find("stlr x9, [x2]"),
          "READY must follow successful mapping join")
    c.yes("For i = 1 To spins" in wait and "Safety" not in wait,
          "join wait must be bounded and must not pet the watchdog")
    c.yes("CoreRawState(core) <> #CORE_RAW_STATE_READY" in result,
          "result loads must be ordered by observing READY with acquire")
    c.yes("coreRaw_Sp() >= stackBase" in prepare and
          "CoreRawBootBase() < top" in prepare and "CoreRawRowBase() < top" in prepare,
          "stack must not overlap the primary or raw-core allocations")
    c.yes("HwCoreRawStackBase(core)" in stack_owned and
          "HwCoreRawStackBytes(core)" in stack_owned and
          "stackBase <> owned Or stackBytes <> bytes" in stack_owned,
          "raw stack ownership must be the board's exact core/page pair")
    in_order(c, prepare,
             ["If CoreRawStackOwned(core, stackBase, stackBytes) = 0",
              "If stackBase <= HwMonHi() And HwMonLo() < top",
              "boot = CoreRawBootAddr(core)", "PeekI(box)",
              "PokeI(row + slot * 8", "MmuCleanRange(boot"],
             "stack ownership before prepare side effects")
    for token in (
        "#CORE_RAW_STACK_LO    = $001FC000",
        "#CORE_RAW_STACK_PAGE  = $00001000",
        "#CORE_RAW_STACK_HI    = $001FEFFF",
        "Case 1 : ProcedureReturn #CORE_RAW_STACK_LO",
        "Case 2 : ProcedureReturn #CORE_RAW_STACK_LO + #CORE_RAW_STACK_PAGE",
        "Case 3 : ProcedureReturn #CORE_RAW_STACK_LO + (#CORE_RAW_STACK_PAGE * 2)",
        "Case 4 : ProcedureReturn #CORE_RAW_STACK_LO",
        "Case 4 : ProcedureReturn #CORE_RAW_STACK_HI",
    ):
        c.yes(token in memmap, f"board stack reservation missing {token}")
    c.yes(stack_region(memmap) < mon_regions(memmap), "the board map must still count the raw-secondary stack reservation among its regions")
    for forbidden in ("Print", "Uart", "Safety", "Genet", "Dma", "Display"):
        c.yes(forbidden not in secondary + join,
              f"secondary path must not touch {forbidden}")


def asm_proc(asm: str, name: str, next_name: str) -> str:
    start = asm.find(f"\n{name}:\n")
    end = asm.find(f"\n{next_name}:\n", start + 1)
    if start < 0 or end < 0:
        raise AssertionError(f"missing emitted boundary {name}..{next_name}")
    return asm[start + 1:end]


def emitted_checks(c: Checks, asm: str) -> None:
    join = asm_proc(asm, "MmuSecondaryJoinRaw", "CoreRawBootBase")
    secondary = asm_proc(asm, "CoreRawSecondary", "Main")
    prepare = asm_proc(asm, "CoreRawPrepare", "CoreRawRelease")
    release = asm_proc(asm, "CoreRawRelease", "CoreRawWaitReady")
    wait = asm_proc(asm, "CoreRawWaitReady", "Main")

    for name, body in (("join", join), ("secondary", secondary)):
        c.yes("sub sp" not in body and "str x30" not in body,
              f"emitted {name} grew a generated frame")
    calls = re.findall(r"(?m)^\s*bl\s+(\S+)", secondary)
    c.yes([x.lower() for x in calls] == ["mmusecondaryjoinraw"],
          f"secondary call list is not the raw allowlist: {calls}")
    c.yes("adrp" not in join and "global_" not in join,
          "emitted join must be register-only")
    for token in ("dc isw,x8", "ic iallu", "tlbi alle3",
                  "msr ttbr0_el3,x20", "msr sctlr_el3,x23"):
        c.yes(token in join, f"emitted join missing {token}")
    for token in ("clidr_el1", "tlbi alle2", "ttbr0_el2", "sctlr_el2"):
        c.yes(token not in join, f"emitted join unexpectedly contains {token}")
    c.yes(join.find("mrs x9,sctlr_el3") > join.find("msr sctlr_el3,x23"),
          "EL3 SCTLR must be read back")
    c.yes("movz x9,#4101" in join, "emitted join lacks M/C/I refusal")
    for token in ("mrs x10,sctlr_el3",
                  "and x10,x10,x9", "cbnz x10,mmuSecJoinFail"):
        c.yes(token in join, f"emitted join lacks cold-state guard {token}")
    c.yes(join.find("cbnz x10,mmuSecJoinFail") < join.find("dc isw,x8"),
          "as-found SCTLR guard runs after destructive cache invalidation")
    for token in ("mrs x9,currentel", "mrs x10,sctlr_el3",
                  "mrs x10,cpuectlr_el1", "cbz x10,coreRawSecondaryFail"):
        c.yes(token in secondary, f"emitted pre-DRAM guard lacks {token}")
    c.yes(secondary.find("cbz x10,coreRawSecondaryFail") <
          secondary.find("adrp x9,global_core_raw_boot"),
          "secondary touches DRAM before the cold EL/SCTLR/SMPEN refusal")
    c.yes("mrs x10,cpuectlr_el1" in join and "movz x9,#64" in join,
          "emitted join lacks defensive SMPEN readback")
    c.yes("movz x14,#0" in join and "msr csselr_el1,x14" in join,
          "emitted join does not select private L1 explicitly")
    c.yes(secondary.find("stlr x9,[x2]") > secondary.find("str x9,[x2,#72]"),
          "emitted READY is premature")
    c.yes("ldar x0,[x0]" in asm, "emitted consumer lacks LDAR")

    in_order(c, prepare,
             ["bl mmusecondaryttbr0", "bl mmusecondarytcr",
              "bl mmusecondarymair", "bl mmucleanrange", "bl mmucleanrange"],
             "emitted prepare")
    in_order(c, release,
             ["str x12, [x13]", "bl mmucleanrange",
              "; --- INTRINSIC: a64_barrier ---", "dsb sy", "isb",
              "; --- INTRINSIC: a64_send_event ---", "sev"],
             "emitted release")
    c.yes("safety" not in wait.lower(), "emitted bounded wait touches watchdog")


def model_checks(c: Checks) -> None:
    slots = [0xD8, 0xE0, 0xE8, 0xF0]
    stub = STUB.read_text(encoding="utf-8")
    found = [int(x, 16) for x in re.findall(
        r"(?m)^\.org 0x([0-9a-f]+)\n(?:;[^\n]*\n)*spin_cpu[0-3]:", stub)]
    c.yes(found == slots, f"stub spin slots changed: {found}")
    c.yes("lsl  x7, x6, #3" in stub, "stub no longer indexes quadword slots")
    in_order(c, stub, ["movz x0, #0x0040", "msr  cpuectlr_el1, x0",
                       "secondary_spin:"], "pinned armstub SMPEN prerequisite")
    for core in range(4):
        c.yes(0xD8 + core * 8 == slots[core], f"slot arithmetic wrong for core {core}")

    boot0 = 0x480100
    row0 = 0x481100
    boots = [boot0 + i * STRIDE for i in range(4)]
    rows = [row0 + i * STRIDE for i in range(4)]
    stacks = [0, 0x001FC000, 0x001FD000, 0x001FE000]
    c.yes(len(set(boots + rows)) == 8, "boot/control rows must all be distinct")
    for addr in boots + rows:
        c.yes(addr % ALIGN == 0, f"row is not aligned: {addr:#x}")
    c.yes(len(set(stacks[1:])) == 3 and all(x % 16 == 0 for x in stacks[1:]),
          "secondary stacks must be distinct and aligned")

    def prepare_allowed(core: int, primary: int, el: int, sctlr: int,
                        busy: bool, stack: int, size: int = 0x1000) -> bool:
        return (primary == 0 and 1 <= core <= 3 and core != primary and
                el == 3 and (sctlr & 0x1005) == 0x1005 and
                not busy and stack == stacks[core] and size == 0x1000)

    c.yes(prepare_allowed(1, 0, 3, SCTLR_CACHED, False, stacks[1]),
          "valid EL3 setup was refused")
    for args, label in (
        ((0, 0, 3, SCTLR_CACHED, False, stacks[1]), "core zero"),
        ((1, 1, 3, SCTLR_CACHED, False, stacks[1]), "self"),
        ((1, 0, 2, SCTLR_CACHED, False, stacks[1]), "EL2"),
        ((1, 0, 3, 0x30C50830, False, stacks[1]), "missing M/C/I"),
        ((1, 0, 3, SCTLR_CACHED, True, stacks[1]), "busy slot"),
        ((1, 0, 3, SCTLR_CACHED, False, 0), "missing stack"),
        ((1, 0, 3, SCTLR_CACHED, False, stacks[2]), "other core's page"),
        ((1, 0, 3, SCTLR_CACHED, False, stacks[1], 0x800), "partial page"),
        ((1, 0, 3, SCTLR_CACHED, False, stacks[1], 0x2000), "shared pages"),
        ((1, 0, 3, SCTLR_CACHED, False, 0x01000000), "unrelated page"),
    ):
        c.yes(not prepare_allowed(*args), f"model failed to refuse {label}")

    reserved_lo, reserved_hi = stacks[1], stacks[3] + 0xFFF
    monitor_stack, monitor_image, autoboot = 0x00100000, 0x00200000, 0x001FF000
    c.yes(monitor_stack < reserved_lo and reserved_hi < autoboot and
          reserved_hi < monitor_image,
          "reserved pages overlap primary stack, autoboot or image base")
    c.yes(reserved_hi + 1 == autoboot,
          "reserved pages are not the exact band below autoboot")
    for image_end in (0x00200001, 0x00402918, 0x02000000, 0x07EFFFFF):
        c.yes(reserved_hi < monitor_image <= image_end,
              f"image growth reached fixed raw stacks at {image_end:#x}")


def parse_symbols(image: Path) -> dict[str, int]:
    out: dict[str, int] = {}
    for line in Path(str(image) + ".sym").read_text(encoding="utf-8").splitlines():
        if "=" in line:
            name, value = line.split("=", 1)
            out[name.strip().lower()] = int(value.strip())
    return out


def u64(mem: dict[int, int], addr: int) -> int:
    return sum(mem.get(addr + i, 0) << (8 * i) for i in range(8))


def put64(mem: dict[int, int], addr: int, value: int) -> None:
    for i in range(8):
        mem[addr + i] = (value >> (8 * i)) & 0xFF


def load_interp(path: Path):
    spec = importlib.util.spec_from_file_location("anvil_core_worker_a64", path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load interpreter {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def interpreter_checks(c: Checks, a64, image: Path) -> None:
    sym = parse_symbols(image)
    mem = {LOAD + i: b for i, b in enumerate(image.read_bytes())}
    boot0 = (sym["global_core_raw_boot"] + ALIGN - 1) & -ALIGN
    row0 = (sym["global_core_raw_row"] + ALIGN - 1) & -ALIGN
    entry = LOAD + sym["corerawsecondaryentry"]

    ttbr, tcr, mair = 0x00900000, 0x0000000080803520, 0x00000000FF440400
    contexts = [0, 0x1111222233334444, 0x5555666677778888, 0x9999AAAABBBBCCCC]

    class TracingA64(a64.A64):
        def __init__(self) -> None:
            super().__init__()
            self.dc_isw_levels: list[int] = []
            self.cache_dirty = {0: True, 1: True}  # private L1, shared L2
            self.sysreg_reads: list[int] = []

        def step(self) -> None:
            ins = self.fetch(self.pc)
            top = ins & 0xFFF00000
            if top == 0xD5300000:
                base = (ins & self.SYSREG_WRITE_MASK) & ~self.SYSREG_READ_BIT
                if base != self.CURRENTEL_WRITE_BASE:
                    self.sysreg_reads.append(base)
            if (ins & 0xFFF80000) == 0xD5080000:
                key = ((((ins >> 16) & 7) << 12) |
                       (((ins >> 12) & 15) << 8) |
                       (((ins >> 8) & 15) << 4) |
                       ((ins >> 5) & 7))
                if key == 0x0762:  # DC ISW
                    rt = ins & 31
                    operand = self.x[rt] if rt != 31 else 0
                    level = (operand >> 1) & 7
                    self.dc_isw_levels.append(level)
                    if level in self.cache_dirty:
                        self.cache_dirty[level] = False
            super().step()

    cpus = []
    for core in (1, 2, 3):
        boot = boot0 + core * STRIDE
        row = row0 + core * STRIDE
        stack = 0x01000000 + core * 0x10000
        values = [MAGIC, 3, stack, contexts[core], row,
                  ttbr, tcr, mair, SCTLR_CACHED]
        for slot, value in enumerate(values):
            put64(mem, boot + slot * 8, value)
        put64(mem, row, PREPARED)

        cpu = TracingA64()
        cpu.memory = mem                 # independent PE, deliberately shared bytes
        cpu.enable_system_registers(
            el=3, preset={MPIDR_EL1_KEY: core, SCTLR_EL3_KEY: 0,
                          CPUECTLR_EL1_KEY: SMPEN,
                          CCSIDR_EL1_KEY: A72_L1D_CCSIDR})
        cpu.pc = entry
        cpu.sp = 0x7BADFACE7BADF000
        for _ in range(5000):
            cpu.step()
            if u64(mem, row) == READY:
                break
        c.yes(u64(mem, row) == READY, f"core {core} did not publish READY")
        c.yes(cpu.sp == stack, f"core {core} installed wrong stack")
        c.yes(cpu.x[0] == contexts[core] and cpu.x[1] == core and cpu.x[2] == row,
              f"core {core} raw x0/x1/x2 ABI is wrong")
        witness = [u64(mem, row + i * 8) for i in range(10)]
        c.yes(witness == [READY, core, contexts[core], row, 12,
                          SCTLR_CACHED, ttbr, tcr, mair, stack],
              f"core {core} mapping witness mismatch: {witness}")
        c.yes(cpu.dc_isw_levels and set(cpu.dc_isw_levels) == {0},
              f"core {core} selected non-L1 cache levels: {cpu.dc_isw_levels}")
        c.yes(cpu.cache_dirty == {0: False, 1: True},
              f"core {core} disturbed the modeled shared-L2 dirty sentinel")
        cpus.append(cpu)
    c.yes(len({id(x) for x in cpus}) == 3 and all(x.memory is mem for x in cpus),
          "gate did not use independent interpreters over shared bytes")

    class TracedMemory(dict[int, int]):
        def __init__(self, initial: dict[int, int], watch_lo: int,
                     watch_hi: int) -> None:
            super().__init__(initial)
            self.watch_lo = watch_lo
            self.watch_hi = watch_hi
            self.watched_reads = 0

        def get(self, key: int, default: int = 0) -> int:
            if self.watch_lo <= key < self.watch_hi:
                self.watched_reads += 1
            return super().get(key, default)

    def negative(expected_el: int, actual_el: int, sctlr: int,
                 as_found_sctlr: int = 0,
                 smpen: int = SMPEN) -> tuple[int, int, list[int]]:
        core = 1
        boot, row = boot0 + core * STRIDE, row0 + core * STRIDE
        local = TracedMemory(mem, boot, boot + STRIDE)
        for i in range(STRIDE):
            local.pop(row + i, None)
        for slot, value in enumerate(
                [MAGIC, expected_el, 0x01100000, 0x77, row,
                 ttbr, tcr, mair, sctlr]):
            put64(local, boot + slot * 8, value)
        put64(local, row, PREPARED)
        cpu = TracingA64()
        cpu.memory = local
        bank = SCTLR_EL3_KEY if actual_el == 3 else SCTLR_EL2_KEY
        cpu.enable_system_registers(
            el=actual_el, preset={MPIDR_EL1_KEY: core, bank: as_found_sctlr,
                                  CPUECTLR_EL1_KEY: smpen,
                                  CCSIDR_EL1_KEY: A72_L1D_CCSIDR})
        cpu.pc = entry
        cpu.sp = 0x7BADFACE7BADF000
        for _ in range(500):
            cpu.step()
        return u64(local, row), local.watched_reads, cpu.sysreg_reads

    state, boot_reads, sys_reads = negative(3, 1, SCTLR_CACHED)
    c.yes((state, boot_reads) == (PREPARED, 0) and
          CPUECTLR_EL1_KEY not in sys_reads,
          "unexpected EL touched the cold record before parking")
    state, boot_reads, sys_reads = negative(3, 2, SCTLR_CACHED)
    c.yes((state, boot_reads) == (PREPARED, 0) and
          CPUECTLR_EL1_KEY not in sys_reads,
          "EL2 secondary touched the cold record before parking")
    c.yes(negative(3, 3, 0x30C50830)[0] == PREPARED,
          "secondary missing M/C/I published READY")
    for bit, name in ((1, "M"), (4, "C"), (0x1000, "I")):
        result, boot_reads, _ = negative(3, 3, SCTLR_CACHED, bit)
        c.yes(result == PREPARED and boot_reads == 0,
              f"warm EL3 secondary with SCTLR.{name} published READY")
    result, boot_reads, _ = negative(2, 2, SCTLR_CACHED, 4)
    c.yes(result == PREPARED and boot_reads == 0,
          "warm EL2 secondary with SCTLR.C published READY")
    result, boot_reads, _ = negative(3, 3, SCTLR_CACHED, 0, 0)
    c.yes(result == PREPARED and boot_reads == 0,
          "secondary without SMPEN touched the cold record or published READY")


def scratch_clobber_checks(c: Checks, a64, image: Path, asm: str) -> None:
    """Prove the caller survives the join's complete x0..x18 clobber set."""
    join = asm_proc(asm, "MmuSecondaryJoinRaw", "CoreRawBootBase")
    secondary = asm_proc(asm, "CoreRawSecondary", "Main")
    for reg in range(19):
        c.yes(f"movz x{reg},#0" in join,
              f"scratch fixture does not clobber x{reg}")
    c.yes("movz x0,#1" in join and "ret" in join,
          "scratch fixture does not return success")
    c.yes("mov x1,x27" in secondary and
          secondary.find("mov x1,x27") > secondary.find("bl MmuSecondaryJoinRaw"),
          "secondary does not recover core ID from preserved x27 after join")

    sym = parse_symbols(image)
    mem = {LOAD + i: b for i, b in enumerate(image.read_bytes())}
    boot0 = (sym["global_core_raw_boot"] + ALIGN - 1) & -ALIGN
    row0 = (sym["global_core_raw_row"] + ALIGN - 1) & -ALIGN
    entry = LOAD + sym["corerawsecondaryentry"]
    core, context = 2, 0xA55A1234DEADBEEF
    boot, row = boot0 + core * STRIDE, row0 + core * STRIDE
    stack = 0x01200000
    for slot, value in enumerate(
            [MAGIC, 3, stack, context, row, 0, 0, 0, SCTLR_CACHED]):
        put64(mem, boot + slot * 8, value)
    put64(mem, row, PREPARED)
    cpu = a64.A64()
    cpu.memory = mem
    cpu.enable_system_registers(
        el=3, preset={MPIDR_EL1_KEY: core, SCTLR_EL3_KEY: 0,
                      CPUECTLR_EL1_KEY: SMPEN})
    cpu.pc = entry
    cpu.sp = 0x7BADFACE7BADF000
    for _ in range(1000):
        cpu.step()
        if u64(mem, row) == READY:
            break
    c.yes(u64(mem, row) == READY, "scratch-clobbering join blocked READY")
    c.yes(u64(mem, row + 8) == core and cpu.x[1] == core,
          "join scratch clobber destroyed the core ID")
    c.yes(u64(mem, row + 16) == context and cpu.x[0] == context,
          "join scratch clobber destroyed the context")
    c.yes(u64(mem, row + 24) == row and cpu.x[2] == row,
          "join scratch clobber destroyed the control-row address")


def mutation_checks(c: Checks, core: str, mmu: str, memmap: str) -> None:
    mutations = [
        ("cold record clean", "MmuCleanRange(boot, #CORE_RAW_STRIDE)", "MmuCleanRange(boot, 0)"),
        ("control row clean", "MmuCleanRange(row, #CORE_RAW_STRIDE)", "MmuCleanRange(row, 0)"),
        ("spin-slot clean", "MmuCleanRange(box, 8)", "MmuCleanRange(box, 0)"),
        ("slot completion barrier", "a64_barrier()\n  a64_send_event()", "a64_send_event()"),
        ("slot event", "  a64_send_event()", "  ; event removed"),
        ("acquire", "    ldar x0, [x0]", "    ldr  x0, [x0]"),
        ("release", "    stlr x9, [x2]", "    str  x9, [x2, #0]"),
        ("premature READY", "    str  x1, [x2, #8]", "    stlr x9, [x2]\n    str  x1, [x2, #8]"),
        ("MMU join", "    bl   MmuSecondaryJoinRaw", "    nop"),
        ("row stride", "    lsl  x10, x27, #8", "    lsl  x10, x27, #7"),
        ("cold invalidate", "    dc   isw, x8", "    nop"),
        ("EL3 TLB", "    tlbi alle3", "    tlbi alle2"),
        ("MCI refusal", "    movz x9, #4101", "    movz x9, #0"),
        ("pre-DRAM cold SCTLR refusal", "    cbnz x10, coreRawSecondaryFail", "    nop"),
        ("pre-DRAM SMPEN refusal", "    cbz  x10, coreRawSecondaryFail", "    nop"),
        ("as-found cold SCTLR refusal", "    cbnz x10, mmuSecJoinFail", "    nop"),
        ("join SMPEN refusal", "    cbz  x10, mmuSecJoinFail", "    nop"),
        ("all-level cache discovery", "    movz x14, #0", "    mrs  x14, clidr_el1"),
        ("raw parameters", "ProcedureNaked MmuSecondaryJoinRaw()", "ProcedureNaked MmuSecondaryJoinRaw(bad.i)"),
        ("stack owner check", "If CoreRawStackOwned(core, stackBase, stackBytes) = 0", "If 0 = 1"),
        ("exact stack pair", "If stackBase <> owned Or stackBytes <> bytes", "If 0 = 1"),
        ("running monitor overlap", "If stackBase <= HwMonHi() And HwMonLo() < top", "If 0 = 1"),
        ("monitor reservation", "  ProcedureReturn %d\nEndProcedure" % mon_regions(memmap), "  ProcedureReturn %d\nEndProcedure" % stack_region(memmap)),
    ]
    for name, old, new in mutations:
        owner = core if old in core else (mmu if old in mmu else memmap)
        c.yes(old in owner, f"mutation pattern disappeared: {name}")
        changed = owner.replace(old, new, 1)
        try:
            if owner is core:
                source_checks(Checks(), changed, mmu, memmap)
            elif owner is mmu:
                source_checks(Checks(), core, changed, memmap)
            else:
                source_checks(Checks(), core, mmu, changed)
        except AssertionError:
            c.yes(True, f"mutation killed: {name}")
        else:
            c.yes(False, f"mutation survived: {name}")


def build(compiler: str, work: Path, fixture: Path = FIXTURE,
          stem: str = "core_worker", source_root: Path = ROOT,
          load_addr: int = LOAD) -> tuple[Path, str]:
    compiler_dir = work / "compiler"
    compiler_dir.mkdir(parents=True, exist_ok=True)
    staged = anvil_build.staged_compiler(compiler, compiler_dir)
    image = work / f"{stem}.img"
    env = os.environ.copy()
    env["PMF_ROOT"] = str(source_root)
    cmd = [staged, "--compile", str(fixture.relative_to(source_root)).replace("\\", "/"),
           "-t", "pi4", "--load-addr", hex(load_addr), "--stack-addr", hex(STACK),
           "--entry-returns", "-S", "-s", "-o", str(image)]
    result = subprocess.run(cmd, cwd=source_root, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode or not image.is_file():
        raise AssertionError("fixture build failed:\n" + result.stdout)
    return image, Path(str(image) + ".asm").read_text(encoding="utf-8")


def main_fixture_check(c: Checks, a64, image: Path,
                       expected_return: int = 0, load_addr: int = LOAD,
                       refused_calls: frozenset[int] | None = None) -> tuple[int, int]:
    blob = image.read_bytes()
    sym = parse_symbols(image)
    required = (
        "__image_start__", "__image_end__", "__bss_start__", "__bss_end__",
        "main", "corerawprepare", "global_core_raw_boot",
        "global_core_raw_row", "global_core_raw_prepared",
        "global_core_raw_released", "global_core_raw_stackbase",
        "global_core_raw_stacktop", "global_core_raw_err",
    )
    missing = [name for name in required if name not in sym]
    c.yes(not missing, "main fixture symbols missing: " + ", ".join(missing))
    code = (load_addr, load_addr + len(blob))
    bss = (sym["__bss_start__"], sym["__bss_end__"])
    stack = (STACK - 0x10000, STACK)

    def inside(span: tuple[int, int], address: int, size: int) -> bool:
        return size > 0 and span[0] <= address and address + size <= span[1]

    c.yes(sym["__image_start__"] == 0 and sym["__image_end__"] == len(blob),
          "main fixture symbol/image extent mismatch")
    c.yes(bss[1] > bss[0], "main fixture BSS is empty or reversed")
    spans = (code, bss, stack)
    c.yes(all(not (left[0] < right[1] and right[0] < left[1])
              for index, left in enumerate(spans)
              for right in spans[index + 1:]),
          "main fixture code/BSS/stack admission overlaps")
    for name in ("main", "corerawprepare"):
        c.yes(0 <= sym[name] < len(blob) and sym[name] % 4 == 0,
              f"invalid emitted procedure offset: {name}")
    for name in required[6:]:
        c.yes(sym[name] % 8 == 0 and inside(bss, sym[name], 8),
              f"invalid emitted BSS symbol: {name}")

    cpu = a64.A64()
    for offset, byte in enumerate(blob):
        cpu.memory[load_addr + offset] = byte
    a64.attach_symbols(cpu, image, load_addr)
    spin_slots = (0xD8, 0xE0, 0xE8, 0xF0)
    boot = (sym["global_core_raw_boot"] + ALIGN - 1) & -ALIGN
    row = (sym["global_core_raw_row"] + ALIGN - 1) & -ALIGN
    watched = {
        "boot": (boot, boot + 4 * STRIDE),
        "row": (row, row + 4 * STRIDE),
        "prepared": (sym["global_core_raw_prepared"],
                     sym["global_core_raw_prepared"] + 32),
        "released": (sym["global_core_raw_released"],
                     sym["global_core_raw_released"] + 32),
        "stackbase": (sym["global_core_raw_stackbase"],
                      sym["global_core_raw_stackbase"] + 32),
        "stacktop": (sym["global_core_raw_stacktop"],
                     sym["global_core_raw_stacktop"] + 32),
    }
    for label, span in watched.items():
        c.yes(inside(bss, span[0], span[1] - span[0]),
              f"complete protected {label} extent escapes exact BSS")
    protected_rows = list(watched.items())
    c.yes(all(not (left[0] < right[1] and right[0] < left[1])
              for index, (_, left) in enumerate(protected_rows)
              for _, right in protected_rows[index + 1:]),
          "protected record/metadata extents overlap")
    watched.update({f"spin_{address:x}": (address, address + 8)
                    for address in spin_slots})
    watched_writes: list[tuple[str, int, int]] = []
    spin_reads: list[int] = []

    def overlap(span: tuple[int, int], address: int, size: int) -> bool:
        return address < span[1] and span[0] < address + size

    def load(address: int, size: int) -> int:
        cpu.align_guard(address, size, False)
        if cpu.fetching:
            if not inside(code, address, size):
                raise AssertionError("instruction fetch outside admitted image")
        elif not (inside(code, address, size) or inside(bss, address, size) or
                  inside(stack, address, size) or
                  (address in spin_slots and size == 8)):
            raise AssertionError(f"read outside admitted RAM/spin slot: {address:#x}+{size}")
        if address in spin_slots:
            spin_reads.append(address)
        return sum(cpu.memory.get(address + i, 0) << (8 * i) for i in range(size))

    def store(address: int, value: int, size: int) -> None:
        cpu.align_guard(address, size, True)
        if not (inside(bss, address, size) or inside(stack, address, size) or
                (address in spin_slots and size == 8)):
            raise AssertionError(f"write outside admitted BSS/stack/spin slot: {address:#x}+{size}")
        for label, span in watched.items():
            if overlap(span, address, size):
                watched_writes.append((label, address, size))
        for i in range(size):
            cpu.memory[address + i] = (value >> (8 * i)) & 0xFF

    cpu.load, cpu.store = load, store

    def must_refuse(action, diagnostic: str) -> None:
        try:
            action()
        except AssertionError as error:
            c.yes(diagnostic in str(error),
                  f"wrong guard diagnostic for {diagnostic}: {error}")
        else:
            c.yes(False, f"guard failed to reject {diagnostic}")

    must_refuse(lambda: load(0x10000000, 8), "outside admitted RAM")
    must_refuse(lambda: store(code[0], 0, 4), "outside admitted BSS")
    must_refuse(lambda: store(stack[0] - 8, 0, 8), "outside admitted BSS")
    must_refuse(lambda: load(0xD0, 8), "outside admitted RAM")
    must_refuse(lambda: load(0xE0, 4), "outside admitted RAM")
    cpu.fetching = True
    try:
        must_refuse(lambda: load(bss[0], 4), "fetch outside admitted image")
        must_refuse(lambda: load(stack[0], 4), "fetch outside admitted image")
    finally:
        cpu.fetching = False

    cpu.enable_system_registers(
        el=3,
        preset={
            MPIDR_EL1_KEY: 0,
            SCTLR_EL3_KEY: SCTLR_CACHED,
            0xD51E2000: 0x00900000,  # TTBR0_EL3
            0xD51E2040: 0x0000000080803520,  # TCR_EL3
            0xD51EA200: 0x00000000FF440400,  # MAIR_EL3
        },
    )
    cpu.pc = load_addr
    cpu.sp = STACK
    cpu.x[29] = 0x2929292929292929
    cpu.x[30] = RETURN_PC
    main_pc = load_addr + sym["main"]
    prepare_pc = load_addr + sym["corerawprepare"]
    poisoned = False
    calls = 0
    active = None
    dc_ops: list[int] = []

    def snapshot() -> bytes:
        spans = list(watched.values())
        return bytes(cpu.memory.get(address, 0)
                     for lo, hi in spans for address in range(lo, hi))

    for steps in range(500_000):
        if cpu.pc == main_pc and not poisoned:
            for offset in range(0, 4 * STRIDE, 8):
                cpu.raw_store(boot + offset, 0x1122334455667788, 8)
                cpu.raw_store(row + offset, 0x2233445566778899, 8)
            cpu.raw_store(0xE0, 0x33445566778899AA, 8)
            poisoned = True
        if cpu.pc == prepare_pc and active is None:
            calls += 1
            active = (cpu.x[30], snapshot(), len(watched_writes), len(dc_ops),
                      len(spin_reads))
        if active is not None and cpu.pc == active[0]:
            before = active
            call_writes = watched_writes[before[2]:]
            call_dc = len(dc_ops) - before[3]
            required_refusals = (frozenset(range(1, 5)) if refused_calls is None
                                 and expected_return == 0 else
                                 (refused_calls or frozenset()))
            if calls in required_refusals:
                c.yes(not call_writes,
                      f"refused Prepare {calls} wrote protected state: {call_writes}")
                c.yes(snapshot() == before[1],
                      f"refused Prepare {calls} changed protected bytes")
                c.yes(call_dc == 0,
                      f"refused Prepare {calls} issued {call_dc} cache operations")
                c.yes(len(spin_reads) == before[4],
                      f"refused Prepare {calls} read a firmware spin slot")
            elif expected_return == 0:
                labels = {item[0] for item in call_writes}
                c.yes({"boot", "row", "prepared", "stackbase",
                       "stacktop"}.issubset(labels),
                      f"valid Prepare did not publish every protected field: {labels}")
                c.yes("released" not in labels,
                      "Prepare changed release ownership before release")
                c.yes(not any(label.startswith("spin_") for label in labels),
                      "Prepare wrote a firmware spin slot")
                c.yes(call_dc == 8,
                      f"valid Prepare issued {call_dc} cache operations, expected 8")
            active = None
        if cpu.pc == RETURN_PC:
            c.yes(cpu.x[0] == expected_return,
                  f"primary ownership fixture returned {cpu.x[0]}")
            if expected_return == 0:
                c.yes(poisoned, "real Main entry was not observed")
                c.yes(active is None and calls == 5,
                      f"expected five completed Prepare routes, observed {calls}")
            elif refused_calls:
                c.yes(active is None and calls == max(refused_calls),
                      f"expected {max(refused_calls)} completed refused routes, observed {calls}")
            c.yes(cpu.sp == STACK and cpu.x[29] == 0x2929292929292929,
                  "entry-return stack/frame-pointer contract was not preserved")
            return steps, 7
        ins = sum(cpu.memory.get(cpu.pc + i, 0) << (8 * i) for i in range(4))
        if (ins & 0xFFF80000) == 0xD5080000:
            dc_ops.append(ins)
        cpu.step()
    raise AssertionError("primary ownership fixture did not return")


def build_ownership_mutant(compiler: str, work: Path, label: str,
                           owner: str, old: str, new: str,
                           load_addr: int = LOAD) -> tuple[Path, str]:
    root = work / f"ownership-mutant-{label}"
    for relative in (
        Path("RaspberryPi4/Board/memmap.pi4"),
        Path("RaspberryPi4/Lib/mmu.pi4"),
        Path("RaspberryPi4/Lib/mmu_secondary.pi4"),
        Path("RaspberryPi4/Lib/core_worker.pi4"),
        Path("RaspberryPi4/Lib/core_worker_impl.pi4"),
        Path("RaspberryPi4/Tests/core_worker_emitted_gate.pi4"),
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    shutil.copytree(ROOT / "Boards", root / "Boards")
    shutil.copytree(
        ROOT / "RaspberryPi4" / "Intrinsics",
        root / "RaspberryPi4" / "Intrinsics",
    )
    path = root / owner
    source = path.read_text(encoding="utf-8")
    if source.count(old) != 1:
        raise AssertionError(
            f"emitted mutant {label} expected one source match, found {source.count(old)}"
        )
    path.write_text(source.replace(old, new, 1), encoding="utf-8", newline="\n")
    return build(
        compiler,
        root / "out",
        root / "RaspberryPi4" / "Tests" / "core_worker_emitted_gate.pi4",
        f"core_worker_{label}",
        root,
        load_addr,
    )


def main() -> int:
    if not __debug__:
        print("a64_core_worker_check: FAIL - Python -O disables interpreter assertions")
        return 1
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", default=str(INTERP))
    args = parser.parse_args()
    checks = Checks()
    try:
        core = CORE.read_text(encoding="utf-8")
        mmu = MMUSEC.read_text(encoding="utf-8")
        memmap = MEMMAP.read_text(encoding="utf-8")
        source_checks(checks, core, mmu, memmap)
        model_checks(checks)
        mutation_checks(checks, core, mmu, memmap)
        compiler = (resolve_compiler(args.compiler)
                    if (args.compiler or os.environ.get("PMF_COMPILER"))
                    else anvil_build.find_compiler(args.compiler))
        with tempfile.TemporaryDirectory(prefix="anvil-core-worker-") as name:
            work = Path(name)
            image, asm = build(compiler, work / "real")
            emitted_checks(checks, asm)
            a64 = load_interp(Path(args.interp))
            primary_steps, primary_guards = main_fixture_check(checks, a64, image)
            relocated_load = 0x001FC000
            relocated_image, _ = build(
                compiler, work / "relocated", stem="core_worker_relocated",
                load_addr=relocated_load)
            relocated_steps, _ = main_fixture_check(
                checks, a64, relocated_image, expected_return=0,
                load_addr=relocated_load, refused_calls=frozenset(range(1, 6)))
            interpreter_checks(checks, a64, image)
            scratch_image, scratch_asm = build(
                compiler, work / "scratch", SCRATCH_FIXTURE, "core_worker_scratch")
            scratch_clobber_checks(
                checks, load_interp(Path(args.interp)), scratch_image, scratch_asm)
            emitted_mutants = (
                (
                    "prepare_guard",
                    "RaspberryPi4/Lib/core_worker_impl.pi4",
                    "If CoreRawStackOwned(core, stackBase, stackBytes) = 0",
                    "If 0 = 1",
                    14,
                    LOAD,
                ),
                (
                    "exact_pair",
                    "RaspberryPi4/Lib/core_worker_impl.pi4",
                    "If stackBase <> owned Or stackBytes <> bytes",
                    "If 0 = 1",
                    7,
                    LOAD,
                ),
                (
                    "monitor_region",
                    "RaspberryPi4/Board/memmap.pi4",
                    "Procedure.i HwMonRegions()\n  ProcedureReturn %d" % mon_regions(memmap),
                    "Procedure.i HwMonRegions()\n  ProcedureReturn %d" % stack_region(memmap),
                    5,
                    LOAD,
                ),
                (
                    "shared_page",
                    "RaspberryPi4/Board/memmap.pi4",
                    "Case 2 : ProcedureReturn #CORE_RAW_STACK_LO + #CORE_RAW_STACK_PAGE",
                    "Case 2 : ProcedureReturn #CORE_RAW_STACK_LO",
                    3,
                    LOAD,
                ),
                (
                    "running_image_overlap",
                    "RaspberryPi4/Lib/core_worker_impl.pi4",
                    "If stackBase <= HwMonHi() And HwMonLo() < top",
                    "If 0 = 1",
                    23,
                    relocated_load,
                ),
            )
            mutant_steps = 0
            for label, owner, old, new, expected, mutant_load in emitted_mutants:
                mutant_image, _ = build_ownership_mutant(
                    compiler, work, label, owner, old, new, mutant_load
                )
                before = checks.count
                try:
                    used, _ = main_fixture_check(
                        checks, a64, mutant_image, expected_return=expected,
                        load_addr=mutant_load)
                except AssertionError as error:
                    raise AssertionError(
                        f"emitted mutant {label} failed before its expected route: {error}"
                    ) from error
                else:
                    mutant_steps += used
                    checks.count = before + 1
    except (AssertionError, OSError, subprocess.SubprocessError, RuntimeError) as error:
        print(f"a64_core_worker_check: FAIL after {checks.count} checks: {error}")
        return 1
    print(f"a64_core_worker_check: PASS - {checks.count} source/model/emitted/interpreter checks")
    print(f"Primary ownership fixture returned in {primary_steps:,} instructions; "
          f"5 Prepare routes and {primary_guards} active memory guards; "
          "5 emitted ownership mutants rejected.")
    print(f"Relocated-image overlap fixture refused the fifth Prepare route in "
          f"{relocated_steps:,} instructions.")
    print("No board was contacted; caches, WFE/SEV, coherency and parallelism remain silicon checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

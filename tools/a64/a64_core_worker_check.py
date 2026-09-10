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
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
import build as anvil_build  # noqa: E402

CORE = ROOT / "RaspberryPi4" / "Lib" / "core_worker.pi4"
MMUSEC = ROOT / "RaspberryPi4" / "Lib" / "mmu_secondary.pi4"
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


def in_order(c: Checks, text: str, needles: list[str], where: str) -> None:
    cursor = -1
    for needle in needles:
        found = text.find(needle, cursor + 1)
        c.yes(found >= 0, f"{where}: missing {needle}")
        c.yes(found > cursor, f"{where}: out of order at {needle}")
        cursor = found


def source_checks(c: Checks, core: str, mmu: str) -> None:
    secondary = proc(core, "CoreRawSecondary")
    prepare = proc(core, "CoreRawPrepare")
    release = proc(core, "CoreRawRelease")
    wait = proc(core, "CoreRawWaitReady")
    result = proc(core, "CoreRawResult")
    acquire = proc(core, "coreRaw_LoadAcquire")
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
    stacks = [0, 0x1004000, 0x1014000, 0x1024000]
    c.yes(len(set(boots + rows)) == 8, "boot/control rows must all be distinct")
    for addr in boots + rows:
        c.yes(addr % ALIGN == 0, f"row is not aligned: {addr:#x}")
    c.yes(len(set(stacks[1:])) == 3 and all(x % 16 == 0 for x in stacks[1:]),
          "secondary stacks must be distinct and aligned")

    def prepare_allowed(core: int, primary: int, el: int, sctlr: int,
                        busy: bool, stack: int) -> bool:
        return (primary == 0 and 1 <= core <= 3 and core != primary and
                el == 3 and (sctlr & 0x1005) == 0x1005 and
                not busy and stack != 0 and stack % 16 == 0)

    c.yes(prepare_allowed(1, 0, 3, SCTLR_CACHED, False, stacks[1]),
          "valid EL3 setup was refused")
    for args, label in (
        ((0, 0, 3, SCTLR_CACHED, False, stacks[1]), "core zero"),
        ((1, 1, 3, SCTLR_CACHED, False, stacks[1]), "self"),
        ((1, 0, 2, SCTLR_CACHED, False, stacks[1]), "EL2"),
        ((1, 0, 3, 0x30C50830, False, stacks[1]), "missing M/C/I"),
        ((1, 0, 3, SCTLR_CACHED, True, stacks[1]), "busy slot"),
        ((1, 0, 3, SCTLR_CACHED, False, 0), "missing stack"),
    ):
        c.yes(not prepare_allowed(*args), f"model failed to refuse {label}")


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


def mutation_checks(c: Checks, core: str, mmu: str) -> None:
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
    ]
    for name, old, new in mutations:
        owner = core if old in core else mmu
        c.yes(old in owner, f"mutation pattern disappeared: {name}")
        changed = owner.replace(old, new, 1)
        try:
            if owner is core:
                source_checks(Checks(), changed, mmu)
            else:
                source_checks(Checks(), core, changed)
        except AssertionError:
            c.yes(True, f"mutation killed: {name}")
        else:
            c.yes(False, f"mutation survived: {name}")


def build(pmfc: str, work: Path, fixture: Path = FIXTURE,
          stem: str = "core_worker") -> tuple[Path, str]:
    compiler_dir = work / "compiler"
    compiler_dir.mkdir(parents=True, exist_ok=True)
    staged = anvil_build.staged_compiler(pmfc, compiler_dir)
    image = work / f"{stem}.img"
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    cmd = [staged, str(fixture.relative_to(ROOT)).replace("\\", "/"),
           "-t", "pi4", "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
           "--entry-returns", "-S", "-s", "-o", str(image)]
    result = subprocess.run(cmd, cwd=ROOT, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode or not image.is_file():
        raise AssertionError("fixture build failed:\n" + result.stdout)
    return image, Path(str(image) + ".asm").read_text(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pmfc", default=os.environ.get("PMFC"))
    parser.add_argument("--interp", default=str(INTERP))
    args = parser.parse_args()
    checks = Checks()
    try:
        core = CORE.read_text(encoding="utf-8")
        mmu = MMUSEC.read_text(encoding="utf-8")
        source_checks(checks, core, mmu)
        model_checks(checks)
        mutation_checks(checks, core, mmu)
        compiler = anvil_build.find_compiler(args.pmfc)
        with tempfile.TemporaryDirectory(prefix="anvil-core-worker-") as name:
            work = Path(name)
            image, asm = build(compiler, work / "real")
            emitted_checks(checks, asm)
            interpreter_checks(checks, load_interp(Path(args.interp)), image)
            scratch_image, scratch_asm = build(
                compiler, work / "scratch", SCRATCH_FIXTURE, "core_worker_scratch")
            scratch_clobber_checks(
                checks, load_interp(Path(args.interp)), scratch_image, scratch_asm)
    except (AssertionError, OSError, subprocess.SubprocessError, RuntimeError) as error:
        print(f"a64_core_worker_check: FAIL after {checks.count} checks: {error}")
        return 1
    print(f"a64_core_worker_check: PASS - {checks.count} source/model/emitted/interpreter checks")
    print("No board was contacted; caches, WFE/SEV, coherency and parallelism remain silicon checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

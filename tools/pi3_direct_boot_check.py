#!/usr/bin/env python3
"""Independent checks for the Pi 3 direct kernel8.img startup contract.

The normal card path is a Pi 3 armstub8.bin followed by the complete monitor
as kernel8.img. This gate is deliberately separate from the optional legacy
A/B recovery gates. It validates the emitted stub and the early monitor
startup without emulating SD-card I/O.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "a64"))
import a64_interp  # noqa: E402
sys.path.insert(0, str(ROOT / "tools"))
from pi3_slot import BSS_ADDRESS, LOAD_ADDRESS, STACK_ADDRESS, SlotError, validate_pmf  # noqa: E402

LOAD = 0x00200000
BSS = 0x01100000
DTB = 0x01000000
STACK = 0x01F00000
DTB_SLOT = 0xF8
KERNEL_SLOT = 0xFC
SPIN_SLOTS = (0xD8, 0xE0, 0xE8, 0xF0)
STUB_MAGIC = 0x5AFE570B
STUB_VERSION = 0
MASK64 = (1 << 64) - 1


def fail(message: str) -> None:
    raise SystemExit("pi3_direct_boot_check: FAIL: " + message)


def read_symbols(path: Path) -> dict[str, int]:
    result: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        try:
            result[name] = int(value, 0)
        except ValueError:
            continue
    return result


def u32(blob: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(blob):
        fail(f"stub is too short for the firmware word at {offset:#x}")
    return struct.unpack_from("<I", blob, offset)[0]


def source_contract() -> dict[str, str]:
    board_path = ROOT / "RaspberryPi3" / "Board" / "board.pi3"
    board = board_path.read_text(encoding="utf-8")
    for directive, expected in (("LoadAddress", LOAD), ("BssAddress", BSS),
                                ("StackAddress", STACK)):
        found = re.findall(rf"^\s*{directive}\s+\$([0-9a-fA-F]+)\s*$",
                           board, re.MULTILINE)
        if len(found) != 1 or int(found[0], 16) != expected:
            fail(f"{directive} must be declared once at {expected:#x}")

    main = re.search(r"(?ims)^Procedure\s+Main\s*\(\)(.*?)(?=^EndProcedure)", board)
    if not main:
        fail("board.pi3 has no Main procedure")
    body = main.group(1)
    forbidden = ("Pi3StorageConfirmSlot", "Pi3UpdateMount", "Pi3UpdateConfirmHandoff",
                 "Pi3UpdateBootStart", "Pi3UpHashSlot", "Pi3LoaderMount")
    present = [name for name in forbidden if name.casefold() in body.casefold()]
    if present:
        fail("normal Main path still depends on A/B selector/storage work: " +
             ", ".join(present))
    if not re.search(r"(?is)If\s+MmuEl\(\)\s*<>\s*3.*?Pi3Park\(\)", body):
        fail("normal Main must fail closed unless firmware startup remains at EL3")
    entry = re.search(r"(?is)ASM\s+(.*?)EndASM", body)
    if not entry or not re.search(r"(?is)str\s+x0\s*,\s*\[x1\]", entry.group(1)):
        fail("Main must capture firmware x0 into the saved DTB before runtime calls")
    first_runtime = re.search(r"(?im)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(", body)
    if first_runtime and first_runtime.start() < entry.start():
        fail("a runtime call occurs before the firmware DTB capture")
    banner = re.search(r"(?im)^\s*Banner\s*\(", body)
    mmu = re.search(r"(?im)^\s*(?:If\s+)?MmuUp\s*\(", body)
    if not banner or not mmu or mmu.start() > banner.start():
        fail("direct startup must establish the MMU before the console banner")
    if re.search(r"(?im)^\s*Pi3SdInit\s*\(", body[:banner.start()]):
        fail("normal startup initializes SD before the console banner")

    stub = ROOT / "RaspberryPi3" / "Board" / "armstub8.asm"
    if not stub.is_file():
        fail("Pi 3 armstub source is missing")
    stub_code = "\n".join(line.split(";", 1)[0] for line in stub.read_text(encoding="utf-8").splitlines())
    if re.search(r"(?im)^\s*eret\b|\bspsr_el3\b|\belr_el3\b", stub_code):
        fail("Pi 3 stub must branch at EL3 without preparing a lower-level ERET")
    if not re.search(r"(?im)^\s*b\s+el3_dispatch\s*$", stub_code):
        fail("Pi 3 stub must dispatch directly at EL3")
    if not re.search(r"(?im)^\s*msr\s+spsel\s*,\s*#1\s*$", stub_code):
        fail("Pi 3 stub must select SP_EL3 before entering the compiler")
    config = (ROOT / "RaspberryPi3" / "Boot" / "config.txt").read_text(encoding="utf-8").lower()
    for exact in ("arm_64bit=1", "kernel=kernel8.img", "kernel_address=0x200000",
                  "armstub=armstub8.bin", "device_tree_address=0x1000000"):
        if sum(line.strip() == exact for line in config.splitlines()) != 1:
            fail(f"config.txt must contain exactly one {exact}")
    if any(re.match(r"(?im)^\s*device_tree\s*=", line) for line in config.splitlines()):
        fail("Pi 3 family config must let firmware choose the DTB from board revision")
    firmware_manifest = json.loads((ROOT / "RaspberryPi3" / "Boot" / "firmware.json").read_text(encoding="utf-8"))
    for dtb in ("bcm2710-rpi-3-b.dtb", "bcm2710-rpi-3-b-plus.dtb"):
        if dtb not in firmware_manifest.get("files", {}):
            fail(f"Pi 3 firmware manifest is missing automatic-DTB candidate {dtb}")

    build = (ROOT / "tools" / "build.py").read_text(encoding="utf-8")
    if '"pi3-stub"' not in build or '"pi3-monitor"' not in build:
        fail("build.py must keep separate Pi 3 stub and full-monitor targets")
    if '"pi3": ("pi3-stub", "pi3-monitor")' not in build:
        fail("the normal pi3 build alias must build only stub + full monitor")
    if '"pi3-ab-recovery"' in build or "pi3-ab-recovery" in build:
        fail("the normal build registry must not expose the old A/B selector target")

    stage = (ROOT / "tools" / "pi3_boot_stage.py").read_text(encoding="utf-8")
    provision_path = ROOT / "tools" / "pi3_provision.py"
    if not provision_path.is_file():
        fail("direct bundle provisioning tool is missing")
    provision = provision_path.read_text(encoding="utf-8")
    if "armstub8.bin" not in stage or "kernel8.img" not in stage:
        fail("boot staging does not validate the direct boot artifacts")
    if "--bundle" not in provision or "--manifest-sha256" not in provision:
        fail("provisioner lacks the reviewed direct-bundle manifest interface")
    if "P3SLOT" in provision or "anvil-slot.img" in provision:
        fail("normal Pi 3 provisioner still mentions legacy A/B slot files")

    # The direct composition must keep the ordinary payload loader. These
    # checks intentionally do not imply that booti/bootm support is enabled.
    bootfile = (ROOT / "Anvil" / "Core" / "bootfile_cmd.pbi").read_text(encoding="utf-8")
    stubs = (ROOT / "RaspberryPi3" / "Board" / "pi3stubs.pi3").read_text(encoding="utf-8")
    if "Procedure CmdBoot()" not in bootfile or "Procedure RunAt(a.i)" not in stubs:
        fail("Anvil payload `boot`/RunAt support disappeared from the board tree")
    return {"board": str(board_path), "stub": str(stub)}


def check_stub_layout(stub: bytes) -> None:
    if len(stub) < 0x200 or len(stub) % 0x100 != 0:
        fail(f"armstub8.bin must include code after the 0x100-byte firmware header and be 256-byte aligned, got {len(stub)}")
    if u32(stub, 0xF0) != STUB_MAGIC or u32(stub, 0xF4) != STUB_VERSION:
        fail("firmware armstub magic/version ABI at 0xF0/0xF4 is incorrect")
    if u32(stub, DTB_SLOT) != 0 or u32(stub, KERNEL_SLOT) != 0:
        fail("firmware DTB/kernel-entry slots at 0xF8/0xFC must ship as zero")
    for slot in SPIN_SLOTS[:3]:
        if struct.unpack_from("<Q", stub, slot)[0] != 0:
            fail(f"secondary spin slot {slot:#x} must ship zero")
    code_end = max((offset for offset in range(0, SPIN_SLOTS[0], 4)
                    if u32(stub, offset) != 0), default=-4) + 4
    if code_end > SPIN_SLOTS[0]:
        fail("stub instruction bytes overlap the firmware spin slots")


def load(cpu: a64_interp.A64, data: bytes, base: int = 0) -> None:
    for offset, byte in enumerate(data):
        cpu.memory[base + offset] = byte


class StubCPU(a64_interp.A64):
    def __init__(self) -> None:
        super().__init__()
        self.mmio_stores: list[tuple[int, int, int]] = []

    def store(self, addr: int, value: int, size: int) -> None:
        self.mmio_stores.append((addr, value, size))
        super().store(addr, value, size)


def firmware_cpu(stub: bytes, core: int) -> StubCPU:
    cpu = StubCPU()
    load(cpu, stub)
    # Firmware enters the Pi 3 armstub at EL3. The MPIDR value is supplied by
    # the model, not fabricated by the code being tested.
    cpu.enable_system_registers(el=3, preset={
        0xD51800A0: 0x80000000 | core,
        0xD51C1140: 0x400,  # irrelevant lower-level state must not be entered
        0xD51E1140: 0x400,  # hostile firmware TFP state; stub must clear it
        0xD51E1000: 0x1005, # hostile translation/cache state; stub resets EL3
    })
    cpu.align_check = True
    cpu.pc = 0
    cpu.sp = 0
    return cpu


def firmware_slots(cpu: a64_interp.A64, dtb: int = DTB, kernel: int = LOAD) -> None:
    cpu.raw_store(0xF0, STUB_MAGIC, 4)
    cpu.raw_store(0xF4, STUB_VERSION, 4)
    cpu.raw_store(DTB_SLOT, dtb, 4)
    cpu.raw_store(KERNEL_SLOT, kernel, 4)
    # Firmware validates the magic/version and clears the shared slot before
    # it releases control to the entry stub; core 3's slot therefore starts
    # empty, just like the three other release words.
    cpu.raw_store(0xF0, 0, 4)
    cpu.raw_store(0xF4, 0, 4)


def run_stub(stub: bytes, core: int, expected_pc: int, dtb: int) -> a64_interp.A64:
    cpu = firmware_cpu(stub, core)
    firmware_slots(cpu, dtb=dtb)
    cpu.x[1] = 0x1111111111111111
    cpu.x[2] = 0x2222222222222222
    cpu.x[3] = 0x3333333333333333
    for _ in range(2000):
        if cpu.pc == expected_pc:
            break
        if 0xD8 <= cpu.pc < 0x100:
            fail(f"stub attempted to execute inside firmware-owned header at {cpu.pc:#x}")
        # The interpreter treats WFE as a no-op, so a secondary with an empty
        # release slot stays in the loop and remains observable here.
        cpu.step()
        if cpu.current_el != 3:
            fail(f"core {core} left EL3 during stub startup (now EL{cpu.current_el})")
    else:
        fail(f"core {core} did not reach expected entry {expected_pc:#x}")
    return cpu


def check_stub(stub: bytes) -> None:
    check_stub_layout(stub)
    primary = run_stub(stub, 0, LOAD, DTB)
    for register in (1, 2, 3):
        if primary.x[register] != 0:
            fail(f"firmware argument register x{register} was not cleared")
    if primary.current_el != 3 or primary.pstate_sp != 1:
        fail("primary did not remain at EL3 using SP_EL3")
    if primary.x[0] != DTB or any(primary.x[n] != 0 for n in (1, 2, 3)):
        fail("primary handoff must be x0=DTB and x1-x3=0")
    if primary.erets:
        fail(f"primary must branch directly at EL3; unexpected exception return {primary.erets}")

    # The monitor remains at EL3. SCR_EL3 describes the lower-level state,
    # while this direct branch itself neither changes security state nor
    # constructs an EL2 return context.
    scr = primary.sysreg(0xD51E1100)
    if scr is None or (scr & (1 << 10)) == 0 or (scr & (1 << 7)) == 0:
        fail("SCR_EL3 does not select AArch64 lower-level state and secure-monitor call trapping")
    if primary.pstate() & 0x3C0 != 0x3C0:
        fail("EL3 was not handed off with DAIF masked")
    if primary.sp != STACK:
        fail(f"stub must establish the configured EL3 stack before branch; got {primary.sp:#x}")
    sctlr = primary.sysreg(0xD51E1000)
    if sctlr is None or (sctlr & 0x1005) != 0:
        fail("SCTLR_EL3 must leave MMU, data cache and instruction cache off")
    cntfrq = primary.sysreg(0xD51BE000)
    if cntfrq != 19_200_000:
        fail(f"Pi 3 stub must declare the BCM2837 19.2 MHz counter; got {cntfrq}")

    # The Pi 3 must use its local control window, never the Pi 4's GIC block.
    if any(0xFF800000 <= addr < 0xFF900000 for addr, _, _ in primary.mmio_stores):
        fail("stub touched the Pi 4 local/GIC aperture")
    local_writes = [(addr, value) for addr, value, _ in primary.mmio_stores
                    if 0x40000000 <= addr < 0x40100000]
    if (0x40000000, 0) not in local_writes or (0x40000008, 0x80000000) not in local_writes:
        fail("stub did not initialize the BCM2837 local timer controls")
    if not local_writes:
        fail("stub did not configure any BCM2837 local-control register")

    expected_sysregs = {
        0xD51BE000: 19_200_000,  # CNTFRQ_EL0
        0xD51E1140: 0,           # CPTR_EL3.TFP clear before compiled entry
        0xD519F220: 0x40,        # CPUECTLR_EL1.SMPEN
        0xD519B040: None,        # L2CTLR, read-modify-write
        0xD51E1100: 0x5B3,        # SCR_EL3 lower-level controls; remain EL3
        0xD51E1020: 0x73,        # ACTLR_EL3
        0xD51E1000: 0x30C50830, # SCTLR_EL3
    }
    for register, expected in expected_sysregs.items():
        actual = primary.sysreg(register)
        if actual is None or (expected is not None and actual != expected):
            fail(f"EL3 stub register {register:#x} is {actual!r}, expected {expected!r}")
    l2ctlr = primary.sysreg(0xD519B040)
    if l2ctlr is None or (l2ctlr & 0x22) != 0x22:
        fail("CPUECTLR SMPEN/L2 setup did not enable L2 data and tag RAM")

    for core in (1, 2, 3):
        cpu = firmware_cpu(stub, core)
        firmware_slots(cpu, dtb=DTB)
        cpu.x[1] = 0x1111111111111111
        cpu.x[2] = 0x2222222222222222
        cpu.x[3] = 0x3333333333333333
        entered = False
        for _ in range(200):
            if 0xD8 <= cpu.pc < 0x100:
                fail(f"secondary core {core} executed inside the firmware header at {cpu.pc:#x}")
            cpu.step()
            if cpu.current_el != 3:
                fail(f"secondary core {core} transiently left EL3 while parking")
            if cpu.current_el == 3:
                entered = True
        if not entered or cpu.current_el != 3 or cpu.pstate_sp != 1:
            fail(f"secondary core {core} did not park at EL3 on SP_EL3")
        if cpu.erets:
            fail(f"secondary core {core} unexpectedly left EL3 by ERET: {cpu.erets}")
        if cpu.sp != STACK:
            fail(f"secondary core {core} did not select the configured EL3 stack")
        if cpu.pc >= 0x200000:
            fail(f"secondary core {core} escaped its empty firmware spin slot")
        target = 0x00280000 + core * 0x1000
        cpu.raw_store(SPIN_SLOTS[core], target, 8)
        for _ in range(200):
            if cpu.pc == target:
                break
            if 0xD8 <= cpu.pc < 0x100:
                fail(f"released secondary core {core} executed inside the firmware header at {cpu.pc:#x}")
            cpu.step()
            if cpu.current_el != 3:
                fail(f"released secondary core {core} transiently left EL3")
        else:
            fail(f"released secondary core {core} did not branch to {target:#x}")
        if cpu.current_el != 3 or cpu.pstate_sp != 1:
            fail(f"released secondary core {core} did not remain at EL3")
        if cpu.x[0] != 0 or any(cpu.x[n] != 0 for n in (1, 2, 3)):
            fail(f"secondary core {core} arguments must be x0-x3=0")
        if cpu.erets:
            fail(f"released secondary core {core} unexpectedly executed ERET: {cpu.erets}")


def check_emitted_main_capture(stub: bytes, kernel: bytes,
                               symbols: dict[str, int]) -> int:
    """Run the real firmware-stub -> compiler _start -> Main handoff."""
    main_offset = next((value for name, value in symbols.items()
                        if name.casefold() == "main"), None)
    dtb_address = next((value for name, value in symbols.items()
                        if name.casefold() == "global_pi3_dtb"), None)
    if main_offset is None or dtb_address is None:
        fail("kernel symbol map needs Main and global_pi3_dtb")
    if not BSS <= dtb_address < 0x01E00000:
        fail(f"global_pi3_dtb symbol {dtb_address:#x} is outside the declared BSS")

    folded = {name.casefold(): value for name, value in symbols.items()}
    bss_start = folded.get("__bss_start__")
    bss_end = folded.get("__bss_end__")
    if bss_start is None or bss_end is None or bss_end < bss_start:
        fail("kernel symbol map needs a valid __bss_start__/__bss_end__ range")
    # The emitted compiler startup clears BSS in an 8-byte loop with five
    # instructions per slot (CMP, conditional branch, STR, ADD, back branch),
    # followed by two instructions for the final compare/exit. Derive the
    # startup budget from this exact image's BSS span instead of reusing the
    # old one-megainstruction allowance from tiny non-TTF monitors.
    clear_slots = (bss_end - bss_start + 7) // 8
    capture_budget = clear_slots * 5 + 4096

    test_dtb = 0x01234000
    cpu = run_stub(stub, 0, LOAD, test_dtb)
    load(cpu, kernel, LOAD)
    # The stub establishes SP_EL3 before branching. The emitted compiler
    # startup must preserve that stack bank, clear BSS, retain EL3 FP/SIMD
    # access, and carry x0 all the way to Main.
    cpu.raw_store(dtb_address, 0xA5A5A5A5A5A5A5A5, 8)
    cpu.pc = LOAD
    initial_x0 = cpu.x[0]
    if initial_x0 != test_dtb or any(cpu.x[n] != 0 for n in (1, 2, 3)):
        fail("stub did not hand the firmware DTB and cleared argument registers to _start")
    if cpu.current_el != 3 or cpu.pstate_sp != 1 or cpu.sp != STACK:
        fail("stub did not hand _start the configured active EL3 stack")
    first_call: tuple[int, int, int] | None = None
    for steps in range(capture_budget):
        if cpu.raw_load(dtb_address, 8) == test_dtb:
            if not LOAD + main_offset <= cpu.pc <= LOAD + main_offset + 256:
                fail(f"firmware DTB was captured outside Main near PC {cpu.pc:#x}")
            cptr3 = cpu.sysreg(0xD51E1140)
            if cptr3 != 0:
                fail(f"EL3 FP/SIMD access was not preserved through compiler startup/Main (value={cptr3!r}, firstBL={first_call}, Main={LOAD + main_offset:#x})")
            if first_call is None or first_call[1] != LOAD + main_offset or first_call[2] != test_dtb:
                fail(f"_start did not call Main directly with preserved firmware x0: {first_call}")
            if cpu.current_el != 3 or cpu.pstate_sp != 1:
                fail("monitor Main was not entered at masked EL3 using SP_EL3")
            if cpu.pstate() & 0x3C0 != 0x3C0:
                fail("compiler startup did not keep DAIF masked through Main entry")
            if cpu.sp == 0 or cpu.sp % 16 != 0 or cpu.sp > STACK:
                fail(f"compiler startup did not establish the declared stack: {cpu.sp:#x}")
            if first_call:
                print(f"  startup BL first at {first_call[0]:#x} -> {first_call[1]:#x}, x0={first_call[2]:#x}; Main captured {test_dtb:#x}")
            return steps
        instruction = cpu.fetch(cpu.pc)
        if instruction & 0xFC000000 == 0x94000000 and first_call is None:
            immediate = instruction & 0x03FF_FFFF
            if immediate & 0x0200_0000:
                immediate -= 0x0400_0000
            first_call = (cpu.pc, cpu.pc + (immediate << 2), cpu.x[0])
        elif instruction & 0xFC000000 == 0x94000000:
            fail(f"compiled startup made another call before Main captured x0 at {cpu.pc:#x}")
        cpu.step()
        if cpu.current_el != 3:
            fail(f"compiler startup left EL3 before Main capture (now EL{cpu.current_el})")
    fail(f"firmware DTB did not reach Main through compiled _start within derived {capture_budget:,}-instruction BSS budget; PC={cpu.pc:#x}, x0={cpu.x[0]:#x}, x1={cpu.x[1]:#x}, x2={cpu.x[2]:#x}, x3={cpu.x[3]:#x}, SP={cpu.sp:#x}")


def check_emitted_el3_runtime(kernel: bytes, symbols: dict[str, int]) -> tuple[int, int, int]:
    """Exercise this exact image's EL3 MMU, exception-vector and payload-return code."""
    def addr(name: str) -> int:
        value = next((v for n, v in symbols.items() if n.casefold() == name.casefold()), None)
        if value is None:
            fail(f"kernel symbol map needs {name}")
        return value if name.casefold().startswith("global_") else LOAD + value

    def fresh(*, sctlr: int = 0x30C50830, cptr: int = 0x400) -> a64_interp.A64:
        cpu = a64_interp.A64()
        load(cpu, kernel, LOAD)
        cpu.enable_system_registers(el=3, preset={
            0xD51800A0: 0x80000000,  # primary MPIDR
            0xD51B4220: 0x3C0,      # DAIF masked like the firmware handoff
            0xD51E1000: sctlr,
            0xD51E1140: cptr,
            # Sentinels: EL3 procedures must not select or modify EL2 banks.
            0xD51C1000: 0xA5A5A5A5,
            0xD51C2000: 0x1111222233334444,
            0xD51C2040: 0x5555666677778888,
            0xD51CA200: 0x9999AAAABBBBCCCC,
        })
        cpu.sp = STACK
        return cpu

    # Execute actual MmuUp, not a parallel model of its register selection.
    mmu = fresh()
    mmu.pc = addr("MmuUp")
    mmu.x[30] = 0x600000
    tlbi3 = 0
    for mmu_steps in range(1_000_000):
        if mmu.pc == 0x600000:
            break
        if mmu.current_el != 3:
            fail(f"MmuUp dropped out of EL3 at PC {mmu.pc:#x}")
        word = mmu.fetch(mmu.pc)
        if word == 0xD50E871F:  # TLBI ALLE3
            tlbi3 += 1
        if word == 0xD50C871F:  # TLBI ALLE2
            fail("EL3 MmuUp emitted an EL2-wide TLB invalidation")
        mmu.step()
    else:
        fail("actual monitor MmuUp did not return within 1,000,000 instructions")
    if mmu.current_el != 3 or mmu.erets or mmu.x[0] != 0:
        fail(f"EL3 MmuUp did not return successfully at EL3: EL={mmu.current_el}, rc={mmu.x[0]}, ERETs={mmu.erets}")
    if tlbi3 != 1:
        fail(f"EL3 MmuUp must issue one TLBI ALLE3, saw {tlbi3}")
    expected_translation = (
        (0xD51E2000, addr("global_mmu3_ttbr")),
        (0xD51E2040, addr("global_mmu3_tcr")),
        (0xD51EA200, addr("global_mmu3_mair")),
    )
    for register, source in expected_translation:
        expected = sum(mmu.memory.get(source + i, 0) << (8 * i) for i in range(8))
        if expected == 0 or mmu.sysreg(register) != expected:
            fail(f"EL3 MmuUp wrote the wrong translation bank register {register:#x}")
    if mmu.sysreg(0xD51E1000) != 0x30C51835:
        fail("EL3 MmuUp did not enable the current EL3 MMU and caches")
    if (mmu.sysreg(0xD51C1000), mmu.sysreg(0xD51C2000),
            mmu.sysreg(0xD51C2040), mmu.sysreg(0xD51CA200)) != (
            0xA5A5A5A5, 0x1111222233334444,
            0x5555666677778888, 0x9999AAAABBBBCCCC):
        fail("EL3 MmuUp touched an EL2 SCTLR/translation register")

    # Exercise the real ExceptionInstall procedure under the monitor EL. This
    # proves the compiled Pi3 image publishes VBAR_EL3 rather than relying on
    # a source-only claim or an EL2 vector bank.
    exc = fresh(sctlr=0x30C51835)
    exc.pc = addr("ExceptionInstall")
    exc.x[30] = 0x600000
    for exception_steps in range(100_000):
        if exc.pc == 0x600000:
            break
        if exc.current_el != 3:
            fail(f"ExceptionInstall dropped out of EL3 at PC {exc.pc:#x}")
        exc.step()
    else:
        fail("actual ExceptionInstall did not return within 100,000 instructions")
    if exc.x[0] != 3 or exc.current_el != 3 or exc.erets:
        fail("ExceptionInstall did not return at EL3")
    if exc.sysreg(0xD51EC000) != addr("exception_vectors_3"):
        fail("ExceptionInstall did not publish the EL3 vector table to VBAR_EL3")
    if exc.sysreg(0xD51CC000) is not None:
        fail("EL3 ExceptionInstall unexpectedly selected VBAR_EL2")
    if exc.sysreg(0xD51E1140) != 0:
        fail("EL3 ExceptionInstall did not clear CPTR_EL3.TFP")

    # The normal `run` trampoline is a call/return at the active privilege
    # level, including with the EL3 MMU/caches on. A return must restore the
    # monitor's stack and must not silently enter EL2.
    payload = fresh(sctlr=0x30C51835, cptr=0)
    payload_address = 0x00500000
    return_pc = 0x00600000
    payload.raw_store(payload_address, 0xD65F03C0, 4)  # A64 RET
    payload.pc = addr("Pi3EnterPayload")
    payload.sp = STACK
    payload.x[0] = payload_address
    payload.x[30] = return_pc
    seen_payload = False
    for payload_steps in range(10_000):
        if payload.pc == return_pc:
            break
        if payload.current_el != 3:
            fail(f"Pi3EnterPayload or returning payload changed EL at PC {payload.pc:#x}")
        if payload.pc == payload_address:
            seen_payload = True
        payload.step()
    else:
        fail("Pi3EnterPayload did not return from the test payload")
    if (not seen_payload or payload.current_el != 3 or payload.erets or
            payload.sp != STACK or payload.pstate_sp != 1 or
            payload.sysreg(0xD51E1000) != 0x30C51835):
        fail("payload return did not preserve EL3, SP_EL3, and MMU/cache state")
    return mmu_steps + 1, exception_steps + 1, payload_steps + 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stub", type=Path, default=ROOT / "build" / "pi3" / "armstub8.bin")
    parser.add_argument("--kernel", type=Path, default=ROOT / "build" / "pi3" / "kernel8.img")
    parser.add_argument("--sym", type=Path, help="kernel .sym file (default: <kernel>.sym)")
    parser.add_argument("--source-only", action="store_true",
                        help="check source/config contract without emitted artifacts")
    parser.add_argument("--stub-only", action="store_true",
                        help="check the emitted stub without requiring a full kernel build")
    args = parser.parse_args()
    source_contract()
    if args.stub_only:
        if not args.stub.is_file():
            fail(f"stub artifact is missing: {args.stub}")
        stub = args.stub.read_bytes()
        check_stub(stub)
        print(f"stub {len(stub)} bytes sha256 {hashlib.sha256(stub).hexdigest()}")
    elif not args.source_only:
        if not args.stub.is_file() or not args.kernel.is_file():
            fail("direct stub/kernel artifacts are missing; use --source-only for source/config checks")
        stub = args.stub.read_bytes()
        check_stub(stub)
        kernel = args.kernel.read_bytes()
        sym_path = args.sym or Path(str(args.kernel) + ".sym")
        if not sym_path.is_file():
            fail(f"kernel symbol map is missing: {sym_path}")
        symbols = read_symbols(sym_path)
        main_symbol = next((value for name, value in symbols.items()
                            if name.casefold() == "main"), None)
        if main_symbol is None:
            fail("kernel symbol map has no Main entry")
        if len(kernel) == 0 or len(kernel) > 0x00E00000:
            fail("kernel8.img size is empty or exceeds the monitor image reservation")
        pmf_path = Path(str(args.kernel) + ".pmf")
        if not pmf_path.is_file():
            fail(f"kernel PMF sidecar is missing: {pmf_path}")
        try:
            meta = validate_pmf(pmf_path.read_bytes(), name="direct Pi 3 monitor",
                                load_address=LOAD_ADDRESS, image_limit=DTB,
                                bss_address=BSS_ADDRESS, bss_limit=0x01E00000,
                                stack_address=STACK_ADDRESS)
        except SlotError as exc:
            fail(str(exc))
        if pmf_path.read_bytes()[128:] != kernel:
            fail("kernel image is not the exact raw image recorded in its PMF sidecar")
        if meta.get("target") != 2837:
            fail("kernel PMF target is not the BCM2837 Pi 3 target")
        capture_steps = check_emitted_main_capture(stub, kernel, symbols)
        mmu_steps, exception_steps, payload_steps = check_emitted_el3_runtime(kernel, symbols)
        print(f"Pi 3 direct boot emitted gate: stub {len(stub)} bytes sha256 {hashlib.sha256(stub).hexdigest()}")
        print(f"  kernel {len(kernel)} bytes sha256 {hashlib.sha256(kernel).hexdigest()}; Main offset {main_symbol:#x}; PMF {meta}")
        print(f"  stub -> _start -> Main preserved and captured arbitrary firmware DTB in {capture_steps} instructions")
        print(f"  actual EL3 MmuUp/ExceptionInstall/payload-return probes: {mmu_steps}/{exception_steps}/{payload_steps} instructions")
    print("pi3_direct_boot_check: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

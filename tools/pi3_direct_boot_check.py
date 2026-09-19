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
    config = (ROOT / "RaspberryPi3" / "Boot" / "config.txt").read_text(encoding="utf-8").lower()
    for exact in ("arm_64bit=1", "kernel=kernel8.img", "kernel_address=0x200000",
                  "armstub=armstub8.bin", "device_tree_address=0x1000000"):
        if sum(line.strip() == exact for line in config.splitlines()) != 1:
            fail(f"config.txt must contain exactly one {exact}")

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
        0xD51C1140: 0x400,  # reset EL2 trap state; compiler must enable FP/SIMD
        0xD51E1140: 0,      # stub enables FP/SIMD access below EL3
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
    else:
        fail(f"core {core} did not reach expected entry {expected_pc:#x}")
    return cpu


def check_stub(stub: bytes) -> None:
    check_stub_layout(stub)
    primary = run_stub(stub, 0, LOAD, DTB)
    for register in (1, 2, 3):
        if primary.x[register] != 0:
            fail(f"firmware argument register x{register} was not cleared")
    if primary.current_el != 2 or primary.pstate_sp != 1:
        fail("primary did not enter EL2h")
    if primary.x[0] != DTB or any(primary.x[n] != 0 for n in (1, 2, 3)):
        fail("primary handoff must be x0=DTB and x1-x3=0")
    if (not primary.erets or primary.erets[-1][0:2] != (3, 2)
            or not 0 <= primary.erets[-1][2] < len(stub)):
        fail(f"primary must ERET from EL3 to the in-stub EL2 dispatch; got {primary.erets}")

    # ERET target configuration: AArch64 non-secure EL2h, all DAIF masked,
    # translation and data/instruction caches disabled for the compiled entry.
    scr = primary.sysreg(0xD51E1100)
    spsr = primary.sysreg(0xD51E4000)
    if scr is None or (scr & (1 << 0)) == 0 or (scr & (1 << 10)) == 0:
        fail("SCR_EL3 does not select non-secure AArch64 execution")
    if spsr is None or (spsr & 0x3FF) != 0x3C9:
        fail("SPSR_EL3 does not select masked EL2h")
    if primary.pstate() & 0x3C0 != 0x3C0:
        fail("EL2 was not handed off with DAIF masked")
    sctlr = primary.sysreg(0xD51C1000)
    if sctlr is None or (sctlr & 0x1005) != 0:
        fail("SCTLR_EL2 must leave MMU, data cache and instruction cache off")
    cntfrq = primary.sysreg(0xD51BE000)
    if cntfrq != 19_200_000:
        fail(f"Pi 3 stub must declare the BCM2837 19.2 MHz counter; got {cntfrq}")
    if primary.sysreg(0xD51CE060) != 0:
        fail("CNTVOFF_EL2 must be cleared")

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
        0xD51CE060: 0,           # CNTVOFF_EL2
        0xD51E1140: 0,           # CPTR_EL3
        0xD51C1140: 0x33FF,      # CPTR_EL2 FP/SIMD enabled before ERET
        0xD519F220: 0x40,        # CPUECTLR_EL1.SMPEN
        0xD519B040: None,        # L2CTLR, read-modify-write
        0xD51E1100: None,        # SCR_EL3, checked for NS/RW below
        0xD51E1020: 0x73,        # ACTLR_EL3
        0xD51C1000: 0x30C50830, # SCTLR_EL2
        0xD51E4000: 0x3C9,       # SPSR_EL3
        0xD51C1100: 0x80000000,  # HCR_EL2.RW
        0xD51CE100: 0x3,         # CNTHCTL_EL2 EL1 counter/timer access
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
            if cpu.current_el == 2:
                entered = True
        if not entered or cpu.current_el != 2 or cpu.pstate_sp != 1:
            fail(f"secondary core {core} did not park at EL2h")
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
        else:
            fail(f"released secondary core {core} did not branch to {target:#x}")
        if cpu.current_el != 2 or cpu.pstate_sp != 1:
            fail(f"released secondary core {core} did not remain in EL2h")
        if cpu.x[0] != 0 or any(cpu.x[n] != 0 for n in (1, 2, 3)):
            fail(f"secondary core {core} arguments must be x0-x3=0")
        if not cpu.erets or cpu.erets[-1][0:2] != (3, 2):
            fail(f"released secondary core {core} did not enter EL2 through ERET")


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

    test_dtb = 0x01234000
    cpu = run_stub(stub, 0, LOAD, test_dtb)
    load(cpu, kernel, LOAD)
    # Firmware enters the custom stub without promising a monitor stack. The
    # emitted compiler startup must establish its own stack, clear BSS, enable
    # the EL2 FP/SIMD bank, and carry x0 all the way to Main.
    cpu.raw_store(dtb_address, 0xA5A5A5A5A5A5A5A5, 8)
    cpu.pc = LOAD
    cpu.sp = 0
    initial_x0 = cpu.x[0]
    if initial_x0 != test_dtb or any(cpu.x[n] != 0 for n in (1, 2, 3)):
        fail("stub did not hand the firmware DTB and cleared argument registers to _start")
    first_call: tuple[int, int, int] | None = None
    for steps in range(1_000_000):
        if cpu.raw_load(dtb_address, 8) == test_dtb:
            if not LOAD + main_offset <= cpu.pc <= LOAD + main_offset + 256:
                fail(f"firmware DTB was captured outside Main near PC {cpu.pc:#x}")
            cptr2 = cpu.sysreg(0xD51C1140)
            if cptr2 != 0x33FF:
                fail(f"stub FP/SIMD access was not preserved through compiler startup/Main (value={cptr2!r}, firstBL={first_call}, Main={LOAD + main_offset:#x})")
            if first_call is None or first_call[1] != LOAD + main_offset or first_call[2] != test_dtb:
                fail(f"_start did not call Main directly with preserved firmware x0: {first_call}")
            if cpu.current_el != 2 or cpu.pstate_sp != 1:
                fail("monitor Main was not entered at masked EL2h")
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
    fail("firmware DTB did not reach Main through compiled _start within 1,000,000 instructions")


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
        print(f"Pi 3 direct boot emitted gate: stub {len(stub)} bytes sha256 {hashlib.sha256(stub).hexdigest()}")
        print(f"  kernel {len(kernel)} bytes sha256 {hashlib.sha256(kernel).hexdigest()}; Main offset {main_symbol:#x}; PMF {meta}")
        print(f"  stub -> _start -> Main preserved and captured arbitrary firmware DTB in {capture_steps} instructions")
    print("pi3_direct_boot_check: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Compile and execute the SDIO receive-readiness register-model gate."""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "RaspberryPi4" / "Tests" / "sdio_rx_readiness_emitted_gate.pi4"
LOAD = 0x00400000
STACK = 0x03000000
STACK_BYTES = 0x00100000
LOADER_LR = 0xDEAD0000
STEP_LIMIT = 5_000_000

SDIO = 0xFE300000
GPIO = 0xFE200000
ARG1 = SDIO + 0x08
CMDTM = SDIO + 0x0C
RESP0 = SDIO + 0x10
STATUS = SDIO + 0x24
CONTROL1 = SDIO + 0x2C
INT_STATUS = SDIO + 0x30
INT_ENABLE = SDIO + 0x34
SIGNAL_ENABLE = SDIO + 0x38

INT_RESPONSE = 0x00000001
INT_CARD = 0x00000100
INT_TIMEOUT = 0x00010000
RESET_BITS = 0x07000000

CTL = 0x10000000
CTL_IOEX = 0x00
CTL_IORX = 0x04
CTL_IENX = 0x08
CTL_HOST = 0x0C
CTL_SIGNAL = 0x10
CTL_CARD_PENDING = 0x14
CTL_FAIL_IEN_WRITE = 0x18
CTL_FAIL_HOST_MASK = 0x1C
CTL_FAIL_COMMAND = 0x20
CTL_CARD_W1C_WRITES = 0x24
CTL_SIGNAL_WRITES = 0x28
CTL_LAST_INT_WRITE = 0x2C
CTL_INT_WRITES = 0x30
CTL_HOST_WRITES = 0x34
CTL_DESTRUCTIVE = 0x38
CTL_IEN_ARM_WRITES = 0x3C
CTL_BYTES = 0x40

CCCR_IOEX = 0x02
CCCR_IORX = 0x03
CCCR_IENX = 0x04


def required_path(value: str | None, env_name: str) -> Path:
    if not value:
        raise SystemExit(f"SDIO readiness gate: set {env_name} or pass its option")
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"SDIO readiness gate: {env_name} file not found: {path}")
    return path


def load_interpreter(path: Path):
    spec = importlib.util.spec_from_file_location("anvil_sdio_ready_a64", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"SDIO readiness gate: cannot load interpreter: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def symbol_bounds(sym_path: Path) -> tuple[int, int]:
    values: dict[str, int] = {}
    for line in sym_path.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        name, raw = line.split("=", 1)
        if name in ("__bss_start__", "__bss_end__"):
            values[name] = int(raw, 0)
    try:
        return values["__bss_start__"], values["__bss_end__"]
    except KeyError as exc:
        raise SystemExit("SDIO readiness gate: compiler symbol map has no BSS bounds") from exc


def build(compiler: Path, work: Path, source_root: Path = ROOT, probe: Path = PROBE) -> Path:
    staged = work / compiler.name
    shutil.copy2(compiler, staged)
    boards = ROOT / "Boards"
    if boards.is_dir():
        shutil.copytree(boards, work / "Boards")
    image = work / "sdio_rx_readiness_gate.img"
    command = [
        str(staged), "--compile", probe.relative_to(source_root).as_posix(), "-t", "pi4",
        "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
        "--entry-returns", "-o", str(image), "-s",
    ]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(source_root)
    run = subprocess.run(
        command, cwd=source_root, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise SystemExit("SDIO readiness gate: compile failed\n" + run.stdout)
    if not image.is_file() or not image.with_suffix(image.suffix + ".sym").is_file():
        raise SystemExit("SDIO readiness gate: compiler omitted image or symbol map")
    return image


def replace_once(source: str, old: str, new: str, label: str) -> str:
    if source.count(old) != 1:
        raise SystemExit(
            f"SDIO readiness gate: mutant {label} expected one source match, "
            f"found {source.count(old)}"
        )
    return source.replace(old, new, 1)


def build_mask_mutant(compiler: Path, work: Path) -> Path:
    root = work / "first-mask-mutant"
    lib = root / "RaspberryPi4" / "Lib"
    tests = root / "RaspberryPi4" / "Tests"
    lib.mkdir(parents=True)
    tests.mkdir(parents=True)
    shutil.copy2(ROOT / "keywords.def", root / "keywords.def")
    shutil.copytree(
        ROOT / "RaspberryPi4" / "Intrinsics",
        root / "RaspberryPi4" / "Intrinsics",
    )
    source = (ROOT / "RaspberryPi4" / "Lib" / "sdio.pi4").read_text(encoding="utf-8")
    checked = """  If sdio_Rd(#SDIO_INT_ENABLE) <> (host & (~#SDIO_INT_CARD_INT))
    sdio_rxIrqArmFailed = sdio_rxIrqArmFailed + 1
    sdio_rxIrqLastError = #SDIO_RXIRQ_ERR_HOST_WRITE
    If sdio_RxIrqRestore() <> 0
      sdio_rxIrqLastError = #SDIO_RXIRQ_ERR_HOST_WRITE
    EndIf
    ProcedureReturn 0
  EndIf
"""
    source = replace_once(source, checked, "", "unchecked-first-host-mask")
    (lib / "sdio.pi4").write_text(source, encoding="utf-8", newline="\n")
    probe = tests / PROBE.name
    shutil.copy2(PROBE, probe)
    return build(compiler, root, root, probe)


class SdioModel:
    def __init__(self) -> None:
        self.control: dict[int, int] = {}
        self.argument = 0
        self.response = 0
        self.int_status = 0
        self.control1 = 0

    def ctl_get(self, offset: int) -> int:
        return self.control.get(offset, 0) & 0xFFFFFFFF

    def ctl_set(self, offset: int, value: int) -> None:
        self.control[offset] = value & 0xFFFFFFFF

    def cmd52(self) -> None:
        if self.ctl_get(CTL_FAIL_COMMAND):
            self.ctl_set(CTL_FAIL_COMMAND, self.ctl_get(CTL_FAIL_COMMAND) - 1)
            self.int_status |= INT_TIMEOUT
            return

        arg = self.argument
        fn = (arg >> 28) & 7
        address = (arg >> 9) & 0x1FFFF
        write = bool(arg & 0x80000000)
        value = arg & 0xFF
        register = {CCCR_IOEX: CTL_IOEX, CCCR_IORX: CTL_IORX, CCCR_IENX: CTL_IENX}.get(address)
        if fn != 0 or register is None:
            self.response = 0
        elif write:
            if address == CCCR_IENX:
                if value & 0x07 == 0x07:
                    self.ctl_set(
                        CTL_IEN_ARM_WRITES,
                        self.ctl_get(CTL_IEN_ARM_WRITES) + 1,
                    )
                mask = self.ctl_get(CTL_FAIL_IEN_WRITE)
                fail = bool(mask & 1)
                self.ctl_set(CTL_FAIL_IEN_WRITE, mask >> 1)
                if fail:
                    self.int_status |= INT_TIMEOUT
                    return
            self.ctl_set(register, value)
            self.response = value
        else:
            self.response = self.ctl_get(register) & 0xFF
        self.int_status |= INT_RESPONSE

    def read32(self, address: int) -> int:
        if CTL <= address < CTL + CTL_BYTES:
            return self.ctl_get(address - CTL)
        if address == RESP0:
            return self.response
        if address == STATUS:
            return 0
        if address == CONTROL1:
            return self.control1
        if address == INT_STATUS:
            card = INT_CARD if self.ctl_get(CTL_CARD_PENDING) else 0
            return (self.int_status | card) & 0xFFFFFFFF
        if address == INT_ENABLE:
            return self.ctl_get(CTL_HOST)
        if address == SIGNAL_ENABLE:
            return self.ctl_get(CTL_SIGNAL)
        if SDIO <= address < SDIO + 0x100:
            return 0
        if GPIO <= address < GPIO + 0x100:
            return 0
        raise SystemExit(f"SDIO readiness gate: unsupported MMIO read at ${address:08X}")

    def write32(self, address: int, value: int) -> None:
        value &= 0xFFFFFFFF
        if CTL <= address < CTL + CTL_BYTES:
            self.ctl_set(address - CTL, value)
            return
        if SDIO <= address < SDIO + 0x100 or GPIO <= address < GPIO + 0x100:
            self.ctl_set(CTL_DESTRUCTIVE, self.ctl_get(CTL_DESTRUCTIVE) + 1)
        if address == ARG1:
            self.argument = value
            return
        if address == CMDTM:
            command = (value >> 24) & 0x3F
            if command != 52:
                raise SystemExit(f"SDIO readiness gate: unexpected command {command}")
            self.cmd52()
            return
        if address == CONTROL1:
            # Model bounded command/data reset completion immediately.
            self.control1 = value & ~RESET_BITS
            return
        if address == INT_STATUS:
            self.ctl_set(CTL_INT_WRITES, self.ctl_get(CTL_INT_WRITES) + 1)
            self.ctl_set(CTL_LAST_INT_WRITE, value)
            if value & INT_CARD:
                self.ctl_set(CTL_CARD_W1C_WRITES, self.ctl_get(CTL_CARD_W1C_WRITES) + 1)
            self.int_status &= ~(value & ~INT_CARD)
            return
        if address == INT_ENABLE:
            self.ctl_set(CTL_HOST_WRITES, self.ctl_get(CTL_HOST_WRITES) + 1)
            mask = self.ctl_get(CTL_FAIL_HOST_MASK)
            fail = bool(mask & 1)
            self.ctl_set(CTL_FAIL_HOST_MASK, mask >> 1)
            if not fail:
                self.ctl_set(CTL_HOST, value)
            return
        if address == SIGNAL_ENABLE:
            self.ctl_set(CTL_SIGNAL_WRITES, self.ctl_get(CTL_SIGNAL_WRITES) + 1)
            self.ctl_set(CTL_SIGNAL, value)
            return
        if SDIO <= address < SDIO + 0x100:
            return
        if GPIO <= address < GPIO + 0x100:
            return
        raise SystemExit(f"SDIO readiness gate: unsupported MMIO write at ${address:08X}")


def execute(a64, image: Path) -> tuple[int, int]:
    blob = image.read_bytes()
    bss_lo, bss_hi = symbol_bounds(image.with_suffix(image.suffix + ".sym"))
    image_range = (LOAD, LOAD + len(blob))
    bss_range = (bss_lo, bss_hi)
    stack_range = (STACK - STACK_BYTES, STACK + 16)
    readable = (image_range, bss_range, stack_range)
    writable = (bss_range, stack_range)
    model = SdioModel()

    def contains(ranges: tuple[tuple[int, int], ...], address: int, size: int) -> bool:
        return size > 0 and any(lo <= address and address + size <= hi for lo, hi in ranges)

    cpu = a64.A64()
    for offset, byte in enumerate(blob):
        cpu.memory[LOAD + offset] = byte
    a64.attach_symbols(cpu, image, LOAD)
    cpu.pc = LOAD
    cpu.sp = STACK
    cpu.x[30] = LOADER_LR

    def load(address: int, size: int) -> int:
        cpu.align_guard(address, size, False)
        if size == 4 and (SDIO <= address < SDIO + 0x100 or GPIO <= address < GPIO + 0x100 or CTL <= address < CTL + CTL_BYTES):
            return model.read32(address)
        if not contains(readable, address, size):
            raise SystemExit(
                f"SDIO readiness gate: read outside image/BSS/stack/model at ${address:08X}+{size}"
            )
        return sum(cpu.memory.get(address + i, 0) << (8 * i) for i in range(size))

    def store(address: int, value: int, size: int) -> None:
        cpu.align_guard(address, size, True)
        if size == 4 and (SDIO <= address < SDIO + 0x100 or GPIO <= address < GPIO + 0x100 or CTL <= address < CTL + CTL_BYTES):
            model.write32(address, value)
            return
        if not contains(writable, address, size):
            raise SystemExit(
                f"SDIO readiness gate: write outside BSS/stack/model at ${address:08X}+{size}"
            )
        for i in range(size):
            cpu.memory[address + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    ticks = 0
    plain_step = a64.A64.step.__get__(cpu)
    for steps in range(STEP_LIMIT):
        if cpu.pc == LOADER_LR:
            return cpu.x[0], steps
        ticks += 1
        ins = load(cpu.pc, 4)
        if (ins & 0xFFFFFFE0) == 0xD53BE000:  # mrs Xt,cntfrq_el0
            cpu.x[ins & 31] = 54_000_000
            cpu.pc += 4
        elif (ins & 0xFFFFFFE0) == 0xD53BE020:  # mrs Xt,cntpct_el0
            cpu.x[ins & 31] = ticks
            cpu.pc += 4
        else:
            plain_step()
    raise SystemExit(f"SDIO readiness gate: no return in {STEP_LIMIT} instructions")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"))
    args = parser.parse_args()
    compiler = required_path(args.compiler, "PMF_COMPILER")
    interp = required_path(args.interp, "PMF_A64_INTERP")
    a64 = load_interpreter(interp)
    with tempfile.TemporaryDirectory(prefix="anvil-sdio-ready-") as temporary:
        work = Path(temporary)
        image = build(compiler, work)
        result, steps = execute(a64, image)
        mutant = build_mask_mutant(compiler, work)
        mutant_result, mutant_steps = execute(a64, mutant)
    if result:
        print(
            f"sdio_rx_readiness_emitted_check: FAIL assertion {result} "
            f"after {steps:,} A64 instructions"
        )
        return 1
    if mutant_result != 57:
        print(
            "sdio_rx_readiness_emitted_check: FAIL unchecked-first-host-mask "
            f"mutant returned {mutant_result}, expected 57"
        )
        return 1
    print(
        f"sdio_rx_readiness_emitted_check: PASS - 59 labeled assertions, "
        f"{steps:,} A64 instructions; first-mask mutant rejected at 57 "
        f"in {mutant_steps:,} instructions"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Compile exact production EL3 event-wake helpers and model register edges."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "Anvil" / "Core" / "parse.pbi"
FIXTURE = ROOT / "RaspberryPi3" / "Tests" / "idle_wake_probe_gate.pi3"
INTERP = ROOT / "tools" / "a64" / "a64_interp.py"
LOAD, STACK, RETURN = 0x400000, 0x3000000, 0x7000000
NATIVE_LOAD, NATIVE_BSS, NATIVE_STACK = 0x02E00000, 0x02E10000, 0x03000000
NATIVE_STACK_RESERVE_LO = 0x02F00000
MRS_CNTFRQ = 0xD53BE000
MRS_CNTPCT = 0xD53BE020
MRS_CNTKCTL = 0xD538E100
MSR_CNTKCTL = 0xD518E100


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def extract(pattern: str, source: str, label: str) -> str:
    match = re.search(pattern, source, re.MULTILINE | re.DOTALL)
    require(match is not None, f"production {label} not found")
    return match.group(0)


def make_fixture() -> str:
    source = SOURCE.read_text(encoding="utf-8")
    globals_block = "\n".join(
        line for line in source.splitlines()
        if line.startswith("Global anvil_prompt")
    )
    prepare = extract(r"^Procedure\.i AnvilSchedulerPrepareWfe\(\).*?^EndProcedure$",
                      source, "AnvilSchedulerPrepareWfe")
    wake = extract(r"^Procedure\.i AnvilSchedulerWakeProbe\(samples\.i\).*?^EndProcedure$",
                   source, "AnvilSchedulerWakeProbe")
    verified = extract(r"^Procedure AnvilSchedulerWfeVerified\(enabled\.i\).*?^EndProcedure$",
                       source, "AnvilSchedulerWfeVerified")
    qualify = extract(r"^Procedure\.i AnvilSchedulerQualifyPi3Wfe\(\).*?^EndProcedure$",
                      source, "AnvilSchedulerQualifyPi3Wfe")
    sysreg_helpers = "\n\n".join(
        extract(rf"^Procedure(?:\.i)? {name}\(.*?^EndProcedure$", source, name)
        for name in ("AnvilSchedulerCounterHz", "AnvilSchedulerCounterValue",
                     "AnvilSchedulerReadControl", "AnvilSchedulerWriteControl",
                     "AnvilSchedulerAccount", "AnvilSchedulerIdleIfSafe")
    )
    text = FIXTURE.read_text(encoding="utf-8")
    require(text.count(";@@SCHEDULER_GLOBALS@@") == 1 and
            text.count(";@@SCHEDULER_PROCS@@") == 1,
            "idle wake fixture marker missing or duplicated")
    return (text.replace(";@@SCHEDULER_GLOBALS@@", globals_block)
            .replace(";@@SCHEDULER_PROCS@@", sysreg_helpers + "\n\n" + prepare + "\n\n" + wake + "\n\n" + verified + "\n\n" + qualify))


def make_native_fixture() -> str:
    source = SOURCE.read_text(encoding="utf-8")
    globals_block = "\n".join(
        line for line in source.splitlines()
        if line.startswith("Global anvil_prompt")
    )
    helpers = "\n\n".join(
        extract(rf"^Procedure(?:\.i)? {name}\(.*?^EndProcedure$", source, name)
        for name in ("AnvilSchedulerCounterHz", "AnvilSchedulerCounterValue",
                     "AnvilSchedulerReadControl", "AnvilSchedulerWriteControl",
                     "AnvilSchedulerPrepareWfe", "AnvilSchedulerWakeProbe",
                     "AnvilSchedulerWfeVerified", "AnvilSchedulerQualifyPi3Wfe")
    )
    text = (ROOT / "RaspberryPi3" / "Tests" / "idle_wake_probe_native.pi3").read_text(encoding="utf-8")
    require(text.count(";@@SCHEDULER_GLOBALS@@") == 1 and
            text.count(";@@SCHEDULER_PROCS@@") == 1,
            "native idle probe fixture marker missing or duplicated")
    return (text.replace(";@@SCHEDULER_GLOBALS@@", globals_block)
            .replace(";@@SCHEDULER_PROCS@@", helpers))


def load_interpreter():
    spec = importlib.util.spec_from_file_location("idle_wake_a64", INTERP)
    require(spec is not None and spec.loader is not None, "cannot load A64 interpreter")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def symbols(path: Path) -> dict[str, int]:
    out: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        try:
            out[name.lower()] = int(value, 0)
        except ValueError:
            continue
    return out


def read64(memory: dict[int, int], address: int) -> int:
    return sum(memory.get(address + index, 0) << (8 * index) for index in range(8))


def write64(memory: dict[int, int], address: int, value: int) -> None:
    for index in range(8):
        memory[address + index] = (value >> (8 * index)) & 0xFF


def compile_image(compiler: Path, directory: Path) -> tuple[bytes, dict[str, int]]:
    generated = directory / "idle_wake_probe.pi3"
    image = directory / "idle_wake_probe.img"
    generated.write_text(make_fixture(), encoding="utf-8")
    command = [str(compiler), "--compile", str(generated), "-t", "pi3",
               "--entry-returns", "--load-addr", hex(LOAD), "--stack-addr",
               hex(STACK), "-s", "-o", str(image)]
    result = subprocess.run(command, cwd=ROOT,
                            env=dict(os.environ, PMF_ROOT=str(ROOT)),
                            capture_output=True, text=True)
    if result.returncode or not image.is_file():
        raise SystemExit("idle wake fixture compile failed\n" + result.stdout + result.stderr)
    return image.read_bytes(), symbols(Path(str(image) + ".sym"))


def compile_native_probe(compiler: Path, image: Path) -> tuple[bytes, dict[str, int]]:
    image.parent.mkdir(parents=True, exist_ok=True)
    generated = image.with_suffix(".generated.pi3")
    generated.write_text(make_native_fixture(), encoding="utf-8")
    command = [str(compiler), "--compile", str(generated), "-t", "pi3",
               "--entry-returns", "--load-addr", hex(NATIVE_LOAD), "--bss-addr",
               hex(NATIVE_BSS), "--stack-addr", hex(NATIVE_STACK), "-s", "-o", str(image)]
    result = subprocess.run(command, cwd=ROOT,
                            env=dict(os.environ, PMF_ROOT=str(ROOT)),
                            capture_output=True, text=True)
    if result.returncode or not image.is_file():
        raise SystemExit("native idle wake probe compile failed\n" + result.stdout + result.stderr)
    return image.read_bytes(), symbols(Path(str(image) + ".sym"))


def execute(a64, image: bytes, syms: dict[str, int]) -> tuple[int, int, int, int, int, int]:
    class CPU(a64.A64):
        def __init__(self):
            super().__init__()
            self.cntvct = 0x100
            self.wfe_count = 0
            self.mrs_frq_count = 0
            self.mrs_kctl_count = 0
            self.msr_kctl_count = 0
            self._syms = syms

        def global_value(self, name: str) -> int:
            return read64(self.memory, self._syms["global_" + name.lower()])

        def set_global(self, name: str, value: int) -> None:
            write64(self.memory, self._syms["global_" + name.lower()], value)

        def step(self):
            ins = self.fetch(self.pc)
            mrs = ins & 0xFFFFFFE0
            if mrs in (MRS_CNTFRQ, MRS_CNTPCT, MRS_CNTKCTL):
                self.this_instr = self.pc
                self.pc += 4
                self.cntpct = (self.cntpct + self.cntpct_per_instruction) & ((1 << 64) - 1)
                rt = ins & 31
                if mrs == MRS_CNTFRQ:
                    self.mrs_frq_count += 1
                    value = self.global_value("gate_hz")
                elif mrs == MRS_CNTPCT:
                    if self.global_value("gate_freezeCounter") == 0:
                        self.cntvct += 192
                    value = self.cntvct
                else:
                    self.mrs_kctl_count += 1
                    value = self.global_value("gate_kctl")
                    if (self.global_value("gate_badReadback") != 0 and
                            self.global_value("gate_kctlWrites") != 0):
                        value ^= 4
                if rt != 31:
                    self.x[rt] = value & ((1 << 64) - 1)
                return
            if (ins & 0xFFFFFFE0) == MSR_CNTKCTL:
                self.this_instr = self.pc
                self.pc += 4
                self.cntpct = (self.cntpct + self.cntpct_per_instruction) & ((1 << 64) - 1)
                rt = ins & 31
                written = 0 if rt == 31 else self.x[rt]
                self.msr_kctl_count += 1
                self.set_global("gate_kctl", written)
                self.set_global("gate_kctlWrites", self.global_value("gate_kctlWrites") + 1)
                return
            if ins == 0xD503205F:
                self.wfe_count += 1
                self.set_global("gate_wfeCount", self.wfe_count)
            return super().step()

    cpu = CPU()
    for offset, byte in enumerate(image):
        cpu.memory[LOAD + offset] = byte
    for byte in range(0x100):
        cpu.memory[0x6000000 + byte] = 0
    cpu.pc = LOAD + syms["main"]
    cpu.sp = STACK
    cpu.x[30] = RETURN
    limit = 250000
    for steps in range(1, limit + 1):
        if cpu.pc == RETURN:
            return (cpu.x[0], steps, cpu.wfe_count, cpu.mrs_frq_count,
                    cpu.mrs_kctl_count, cpu.msr_kctl_count,
                    cpu.global_value("gate_el"), cpu.global_value("gate_hz"),
                    cpu.global_value("gate_kctl"),
                    cpu.global_value("anvil_promptWfePeriod"),
                    cpu.global_value("anvil_promptWfeReady"))
        cpu.step()
    raise AssertionError("EL3 wake gate exceeded instruction bound")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--native-output", type=Path,
                        help="also emit a small real-counter, real-WFE returning probe PMF here")
    args = parser.parse_args()
    compiler = args.compiler.resolve()
    require(compiler.is_file(), f"compiler not found: {compiler}")
    a64 = load_interpreter()
    with tempfile.TemporaryDirectory(prefix="anvil-idle-wake-") as temporary:
        image, syms = compile_image(compiler, Path(temporary))
        require("main" in syms, "compiler omitted fixture Main")
        result, steps, wfe_count, frqs, mrs_k, msr_k, el, hz, kctl, period, ready = execute(a64, image, syms)
    if result:
        print(f"DEBUG: return={result} el={el} hz={hz} cntfrqReads={frqs} kctlReads={mrs_k} kctlWrites={msr_k} reg={kctl:#x} period={period} ready={ready} WFE={wfe_count}")
    require(result == 0, f"emitted EL3 event-wake assertion {result} failed")
    require(wfe_count == 67, f"expected 67 WFE instructions (32 samples + drains + slow-wake failure + one safe idle turn), got {wfe_count}")
    print(f"PASS: emitted exact EL3 scheduler helpers, 22 assertions / {steps:,} instructions")
    print("  Pi3 qualification requires EL3/19.2MHz + event-stream readback; failed qualification stays polling; UART/editor backlog suppresses WFE")
    if args.native_output:
        image, native_syms = compile_native_probe(compiler, args.native_output.resolve())
        required = ("main", "global_nativeprobeel", "global_nativeprobehz",
                    "global_nativeproberesult", "global_nativeproberestoredcontrol",
                    "global_anvil_promptprobesamples", "global_anvil_promptprobeminticks",
                    "global_anvil_promptprobemaxticks", "global_anvil_promptprobetotalticks")
        missing = [name for name in required if name not in native_syms]
        require(not missing, "native PMF lacks report symbols: " + ", ".join(missing))
        image_end = native_syms.get("__image_end__", 0)
        bss_start = native_syms.get("__bss_start__", 0)
        bss_end = native_syms.get("__bss_end__", 0)
        require(image_end > 0 and NATIVE_LOAD >= 0x02E00000,
                "native image is outside Pi3 payload window or empty")
        require(bss_start == NATIVE_BSS and bss_end > bss_start,
                "native BSS does not match explicit separated placement")
        require(NATIVE_LOAD + image_end < bss_start and bss_end < NATIVE_STACK_RESERVE_LO,
                "native image/BSS intersects each other or reserved stack extent")
        require(NATIVE_STACK == 0x03000000 and NATIVE_STACK_RESERVE_LO < NATIVE_STACK,
                "native stack placement is not the reserved Pi3 probe stack")
        print(f"NATIVE PMF: {args.native_output.resolve()}")
        print(f"  bytes={len(image)} sha256={hashlib.sha256(image).hexdigest()}")
        print(f"  image=0x{NATIVE_LOAD:08X}..0x{NATIVE_LOAD + image_end - 1:08X}; BSS=0x{bss_start:08X}..0x{bss_end - 1:08X}; stack reserve=0x{NATIVE_STACK_RESERVE_LO:08X}..0x{NATIVE_STACK - 1:08X}; stack top=0x{NATIVE_STACK:08X}")
        print("  Main performs real EL3/CNTFRQ/CNTPCT/CNTKCTL reads and 32 WFE samples.")
        print("  BSS reports EL, CNTFRQ, result, sample/min/max/total ticks, and CNTKCTL restoration; WFE is disabled on return.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

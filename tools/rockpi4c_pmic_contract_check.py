#!/usr/bin/env python3
"""Compile and fake-MMIO test the direct-EL3 RK808 HDMI rail preflight."""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import sys
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler


ROOT = Path(__file__).resolve().parents[1]
LOAD = 0x00041000
RETURN = 0x07000000
STACK = 0x07100000
I2C = 0xFF3C0000
PMUCRU = 0xFF750000
PMUGRF = 0xFF320000
PMIC_REGS = {0x17: 0, 0x18: 0, 0x24: 0x25, 0x3D: 0, 0x41: 0xFF, 0x47: 0}


def interpreter():
    path = ROOT / "tools" / "a64" / "a64_interp.py"
    spec = importlib.util.spec_from_file_location("rockpi4c_pmic_a64", path)
    if not spec or not spec.loader:
        raise AssertionError(f"cannot load interpreter at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.A64


HARNESS = r'''#ANVIL_BUILD = 1
#ANVIL_BUILD_DATE = 20260921
#ANVIL_BUILD_TIME = 120000
Global rock_timer_frequency.i
Global rock_uart_ready.i
Global pmic_ticks.i
Procedure.i RockTimerTicks()
  pmic_ticks + 2000
  ProcedureReturn pmic_ticks
EndProcedure
Procedure RockUartText(text.i) : EndProcedure
Procedure RockUartByte(value.i) : EndProcedure
Procedure RockDisplayHexByte(value.i) : EndProcedure
Procedure RockDisplayHexLong(value.i) : EndProcedure
Procedure RockDisplayDecimal(value.i) : EndProcedure
XIncludeFile "RockPi4C/Lib/pmic.pbi"
Procedure.i PmicTestReadReg()
  Protected value.i
  ProcedureReturn RockPmicI2cReadReg($17,@value)
EndProcedure
Procedure.i PmicTestRails()
  rock_timer_frequency=1000000
  ProcedureReturn RockPmicHdmiRailsEnsure()
EndProcedure
Procedure.i Main(mode.i)
  If mode=1 : ProcedureReturn PmicTestReadReg() : EndIf
  ProcedureReturn PmicTestRails()
EndProcedure
'''


def build(compiler: str, out: Path) -> dict[str, int]:
    source = out.with_suffix(".pb")
    source.write_text(HARNESS, encoding="utf-8")
    cmd = [compiler, "--compile", str(source), "-t", "rockpi4c",
           "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
           "--entry-returns", "-o", str(out), "-s"]
    result = subprocess.run(cmd, cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
                            text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    if result.returncode or "pmfc: OK" not in result.stdout or not out.is_file():
        raise AssertionError("isolated PMIC harness did not compile:\n" + result.stdout)
    symbols = {}
    for line in Path(str(out) + ".sym").read_text(encoding="utf-8-sig").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            symbols[key.lower()] = int(value, 0)
    return symbols


class Machine:
    def __init__(self, a64, image: Path, symbols: dict[str, int], mode: str):
        self.cpu = a64()
        blob = image.read_bytes()
        self.cpu.memory.update({LOAD + i: b for i, b in enumerate(blob)})
        self.symbols = symbols
        self.mode = mode
        self.i2c: dict[int, int] = {0x100: 0, 0x200: 0}
        self.pmucru: dict[int, int] = {0: 100, 4: 0x1101, 8: 0x80000000, 12: 0x108}
        if mode == "slow-ppll":
            self.pmucru[8] = 0
            self.pmucru[12] = 0
        self.pmugrf: dict[int, int] = {}
        self.pmic = dict(PMIC_REGS)
        self.writes: list[tuple[int, int]] = []
        self.control_writes: list[int] = []
        self.original_load, self.original_store = self.cpu.load, self.cpu.store
        self.cpu.load, self.cpu.store = self.load, self.store

    @staticmethod
    def masked_write(old: int, value: int) -> int:
        mask, data = (value >> 16) & 0xFFFF, value & 0xFFFF
        return ((old & ~mask) | (data & mask)) & 0xFFFFFFFF

    def load(self, address: int, size: int) -> int:
        self.cpu.align_guard(address, size, False)
        if address & 0xFFFFF000 == I2C:
            offset = address - I2C
            if offset == 0x200 and self.i2c.get(0x200, 0) == 0:
                reg = self.i2c.get(0x0C, 0) & 0xFF
                return self.pmic.get(reg, 0xFF)
            return self.i2c.get(offset, 0)
        if address & 0xFFFFF000 == PMUCRU:
            return self.pmucru.get(address - PMUCRU, 0)
        if address & 0xFFFFF000 == PMUGRF:
            return self.pmugrf.get(address - PMUGRF, 0)
        return self.original_load(address, size)

    def store(self, address: int, value: int, size: int) -> None:
        self.cpu.align_guard(address, size, True)
        value &= 0xFFFFFFFF
        if address & 0xFFFFF000 == I2C:
            offset = address - I2C
            if offset == 0x1C:  # interrupt-pending is W1C
                self.i2c[offset] = self.i2c.get(offset, 0) & ~value
                return
            self.i2c[offset] = value
            if offset == 0x00:
                self.control_writes.append(value)
                if value == 0x09:
                    self.i2c[0x1C] = self.i2c.get(0x1C, 0) | 0x10
                elif value == 0x23:
                    if self.mode == "nak":
                        self.i2c[0x1C] = self.i2c.get(0x1C, 0) | 0x40
                    else:
                        reg = self.i2c.get(0x0C, 0) & 0xFF
                        self.i2c[0x200] = self.pmic.get(reg, 0xFF)
                        self.i2c[0x1C] = self.i2c.get(0x1C, 0) | 0x08
                elif value == 0x01:
                    word = self.i2c.get(0x100, 0)
                    reg, datum = (word >> 8) & 0xFF, (word >> 16) & 0xFF
                    self.pmic[reg] = datum
                    self.writes.append((reg, datum))
                    self.i2c[0x1C] = self.i2c.get(0x1C, 0) | 0x04
                elif value == 0x11 and self.mode != "stop-timeout":
                    self.i2c[0x1C] = self.i2c.get(0x1C, 0) | 0x20
            return
        if address & 0xFFFFF000 == PMUCRU:
            offset = address - PMUCRU
            old = self.pmucru.get(offset, 0)
            self.pmucru[offset] = self.masked_write(old, value)
            return
        if address & 0xFFFFF000 == PMUGRF:
            offset = address - PMUGRF
            old = self.pmugrf.get(offset, 0)
            self.pmugrf[offset] = self.masked_write(old, value)
            return
        self.original_store(address, value, size)

    def call(self, name: str, argument: int = 0) -> int:
        cpu = self.cpu
        if name not in self.symbols:
            raise AssertionError(f"missing emitted symbol {name}; found {sorted(self.symbols)}")
        cpu.pc = LOAD + self.symbols[name]
        cpu.sp = STACK
        cpu.x[0] = argument
        cpu.x[30] = RETURN
        for _ in range(2_000_000):
            if cpu.pc == RETURN:
                return cpu.x[0]
            cpu.step()
        raise AssertionError(f"{name} did not return")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True)
    args = parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    with tempfile.TemporaryDirectory(prefix="rockpi4c-pmic-") as tmp:
        image = Path(tmp) / "pmic_contract.img"
        symbols = build(args.compiler, image)
        a64 = interpreter()

        nak = Machine(a64, image, symbols, "nak")
        if nak.call("main", 1) != 0:
            raise AssertionError("I2C NAK was incorrectly accepted as a register read")
        if 0x11 not in nak.control_writes:
            raise AssertionError("I2C NAK path did not issue STOP cleanup")

        timeout = Machine(a64, image, symbols, "stop-timeout")
        if timeout.call("main", 1) != 0:
            raise AssertionError("STOP timeout was incorrectly accepted as a successful read")

        rails = Machine(a64, image, symbols, "rails")
        rails_result = rails.call("main", 0)
        if rails_result != 1:
            pmic_error = rails.cpu.raw_load(symbols["global_rock_pmic_error"], 8)
            raise AssertionError(f"rail preflight failed (result={rails_result}, error={pmic_error}, regs={rails.pmic}, i2c={rails.i2c})")
        if rails.pmic[0x24] != 0x67:
            raise AssertionError(f"rail RMW clobbered unrelated LDO bits: {rails.pmic[0x24]:#x}")
        if rails.pmic[0x41] != 0xFF:
            raise AssertionError("LDO4 SDIO voltage was modified")
        if rails.pmic[0x47] != 1:
            raise AssertionError("LDO7 did not move from 0.8V to the DTS 0.9V selector")
        if rails.writes != [(0x47, 0x01), (0x24, 0x67)]:
            raise AssertionError(f"unexpected PMIC writes: {rails.writes}")

        # Rockchip's PLL mux defines slow mode as the live xin24m parent. The
        # direct-SD miniloader may leave PPLL in this mode; PMU I2C must remain
        # usable without rewriting a shared PLL merely to reach the RK808.
        slow = Machine(a64, image, symbols, "slow-ppll")
        slow_result = slow.call("main", 0)
        if slow_result != 1:
            pmic_error = slow.cpu.raw_load(symbols["global_rock_pmic_error"], 8)
            raise AssertionError(f"slow-mode PPLL rail preflight failed: {pmic_error}")
        ppll_rate = slow.cpu.raw_load(symbols["global_rock_pmic_ppll_rate"], 8)
        i2c_rate = slow.cpu.raw_load(symbols["global_rock_pmic_i2c_rate"], 8)
        if ppll_rate != 24_000_000 or i2c_rate != 24_000_000:
            raise AssertionError(
                f"slow-mode PPLL parent rates are wrong: {ppll_rate}/{i2c_rate}"
            )
    print("rockpi4c PMIC contract: PASS (compiled; NAK, STOP-timeout, rail-bit preservation)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Desk gate for the RK3399 VOPL -> CDN DP clock/reset contract."""

from __future__ import annotations

from pathlib import Path
import argparse
import importlib.util
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
CRU = ROOT / "RockPi4C" / "Lib" / "cru.pbi"
LOAD = 0x02000040
RETURN = 0x07000000
STACK = 0x07100000
CRU_BASE = 0xFF760000
CLKSEL = 0x100
CLKGATE = 0x300


def require(source: str, pattern: str, description: str) -> None:
    if re.search(pattern, source, re.MULTILINE) is None:
        raise AssertionError(f"missing {description}: /{pattern}/")


def divider(parent: int, ceiling: int) -> int:
    return (parent + ceiling - 1) // ceiling


def check_rate_plan(parent: int) -> None:
    vio_aclk_div = divider(parent, 400_000_000)
    hdcp_aclk_div = divider(parent, 400_000_000)
    vop_aclk_div = divider(parent, 400_000_000)
    vio_aclk = parent // vio_aclk_div
    hdcp_aclk = parent // hdcp_aclk_div
    vop_aclk = parent // vop_aclk_div

    rates = {
        "TCPHY core": parent // divider(parent, 50_000_000),
        "DP core": parent // divider(parent, 100_000_000),
        "SPDIF_REC_DPTX": parent // divider(parent, 200_000_000),
        "VIO ACLK": vio_aclk,
        "VIO PCLK": vio_aclk // divider(vio_aclk, 100_000_000),
        "HDCP ACLK": hdcp_aclk,
        "HDCP HCLK": hdcp_aclk // divider(hdcp_aclk, 200_000_000),
        "HDCP PCLK": hdcp_aclk // divider(hdcp_aclk, 100_000_000),
        "VOP ACLK": vop_aclk,
        "VOP HCLK": vop_aclk // divider(vop_aclk, 200_000_000),
    }
    limits = {
        "TCPHY core": 50_000_000,
        "DP core": 100_000_000,
        "SPDIF_REC_DPTX": 200_000_000,
        "VIO ACLK": 400_000_000,
        "VIO PCLK": 100_000_000,
        "HDCP ACLK": 400_000_000,
        "HDCP HCLK": 200_000_000,
        "HDCP PCLK": 100_000_000,
        "VOP ACLK": 400_000_000,
        "VOP HCLK": 200_000_000,
    }
    for name, rate in rates.items():
        if rate <= 0 or rate > limits[name]:
            raise AssertionError(
                f"{parent} Hz plan gives invalid {name}={rate} (limit {limits[name]})"
            )


def load_interpreter():
    path = ROOT / "tools" / "a64" / "a64_interp.py"
    spec = importlib.util.spec_from_file_location("rockpi4c_cru_a64", path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load A64 interpreter from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def emitted_contract(image: Path) -> None:
    sidecar = Path(str(image) + ".sym")
    if not image.is_file() or not sidecar.is_file():
        raise AssertionError(f"missing image or symbol sidecar: {image}")
    symbols = {}
    for line in sidecar.read_text(encoding="utf-8-sig").splitlines():
        if "=" in line:
            name, value = line.split("=", 1)
            symbols[name.lower()] = int(value, 0)
    required = {
        "rockcrudisplayclocks", "rockcruvpllmode", "rockcrupllrate",
        "rockcruvpll65", "rockcruvpllset", "global_rock_cru_error",
        "global_rock_mode_valid", "global_rock_cru_dp_core_rate",
        "global_rock_cru_vio_aclk_rate", "global_rock_cru_vio_pclk_rate",
        "global_rock_cru_hdcp_aclk_rate", "global_rock_cru_hdcp_hclk_rate",
        "global_rock_cru_hdcp_pclk_rate", "global_rock_cru_vop_aclk_rate",
        "global_rock_cru_vop_hclk_rate",
    }
    missing = required - symbols.keys()
    if missing:
        raise AssertionError(f"emitted image lacks symbols: {sorted(missing)}")

    a64 = load_interpreter()
    blob = image.read_bytes()
    hooks = {
        LOAD + symbols[name]: name
        for name in ("rockcrupllrate", "rockcruvpll65", "rockcruvpllset")
    }

    class Machine:
        def __init__(self, parent: int, stuck_ones: dict[int, int] | None = None):
            self.parent = parent
            self.stuck_ones = stuck_ones or {}
            self.cru: dict[int, int] = {}
            self.writes: list[tuple[int, int, int]] = []
            self.cpu = a64.A64()
            self.cpu.memory.update({LOAD + index: byte for index, byte in enumerate(blob)})
            original_load, original_store = self.cpu.load, self.cpu.store

            def load(addr: int, size: int) -> int:
                if CRU_BASE <= addr < CRU_BASE + 0x1000:
                    if size != 4 or addr & 3:
                        raise AssertionError(f"bad CRU read {addr:#x}/{size}")
                    return self.cru.get(addr - CRU_BASE, 0xFFFF)
                return original_load(addr, size)

            def store(addr: int, value: int, size: int) -> None:
                if CRU_BASE <= addr < CRU_BASE + 0x1000:
                    if size != 4 or addr & 3:
                        raise AssertionError(f"bad CRU write {addr:#x}/{size}")
                    offset = addr - CRU_BASE
                    word = value & 0xFFFFFFFF
                    mask = (word >> 16) & 0xFFFF
                    data = word & 0xFFFF
                    old = self.cru.get(offset, 0xFFFF)
                    new = (old & ~mask) | (data & mask)
                    new |= self.stuck_ones.get(offset, 0) & mask
                    self.cru[offset] = new & 0xFFFF
                    self.writes.append((offset, mask, data))
                    return
                original_store(addr, value, size)

            self.cpu.load, self.cpu.store = load, store

        def call(self, name: str) -> int:
            cpu = self.cpu
            cpu.pc = LOAD + symbols[name]
            cpu.sp = STACK
            cpu.x[30] = RETURN
            for _ in range(500_000):
                if cpu.pc == RETURN:
                    return cpu.x[0]
                hook = hooks.get(cpu.pc)
                if hook == "rockcrupllrate":
                    cpu.x[0] = self.parent
                    cpu.pc = cpu.x[30]
                elif hook in ("rockcruvpll65", "rockcruvpllset"):
                    # PLL sequencing/rate arithmetic have their own emitted
                    # gates.  This test owns the downstream clock contract.
                    cpu.x[0] = 1
                    cpu.pc = cpu.x[30]
                else:
                    cpu.step()
            raise AssertionError(f"emitted {name} did not return")

        def reg(self, offset: int, mask: int = 0xFFFF) -> int:
            return self.cru.get(offset, 0xFFFF) & mask

        def glob(self, name: str) -> int:
            return self.cpu.raw_load(symbols["global_" + name], 8)

    def expected(parent: int) -> tuple[dict[int, tuple[int, int]], dict[str, int]]:
        aclk_div = divider(parent, 400_000_000)
        aclk = parent // aclk_div
        pclk_div = divider(aclk, 100_000_000)
        hclk_div = divider(aclk, 200_000_000)
        registers = {
            CLKSEL + 42 * 4: (0xDFDF, 0x0040 | (aclk_div - 1) |
                              0x4000 | ((aclk_div - 1) << 8)),
            CLKSEL + 43 * 4: (0x7FFF, (pclk_div - 1) |
                              ((hclk_div - 1) << 5) | ((pclk_div - 1) << 10)),
            CLKSEL + 64 * 4: (0x9FDF, 0x00C0 | (divider(parent, 50_000_000) - 1)),
            CLKSEL + 46 * 4: (0x00DF, 0x0080 | (divider(parent, 100_000_000) - 1)),
            CLKSEL + 32 * 4: (0x9F00, 0x8000 | ((divider(parent, 200_000_000) - 1) << 8)),
            CLKSEL + 48 * 4: (0x1FDF, 0x0080 | (aclk_div - 1) |
                              ((hclk_div - 1) << 8)),
            CLKSEL + 50 * 4: (0x0BFF, 0),
        }
        rates = {
            "rock_cru_dp_core_rate": parent // divider(parent, 100_000_000),
            "rock_cru_vio_aclk_rate": aclk,
            "rock_cru_vio_pclk_rate": aclk // pclk_div,
            "rock_cru_hdcp_aclk_rate": aclk,
            "rock_cru_hdcp_hclk_rate": aclk // hclk_div,
            "rock_cru_hdcp_pclk_rate": aclk // pclk_div,
            "rock_cru_vop_aclk_rate": aclk,
            "rock_cru_vop_hclk_rate": aclk // hclk_div,
        }
        return registers, rates

    gate_masks = {
        10: 0x2C40,
        11: 0x050B,
        13: 0x0030,
        21: 0x0060,
        28: 0x00F0,
        29: 0x10B9,
    }
    for parent in (800_000_000, 594_000_000):
        machine = Machine(parent)
        if machine.call("rockcrudisplayclocks") != 1:
            raise AssertionError(
                f"emitted display clocks refused {parent}: error {machine.glob('rock_cru_error')}"
            )
        registers, rates = expected(parent)
        for offset, (mask, value) in registers.items():
            actual = machine.reg(offset, mask)
            if actual != value:
                raise AssertionError(
                    f"{parent} CLK/SEL {offset:#x}: {actual:#x} != {value:#x} mask {mask:#x}"
                )
        for bank, mask in gate_masks.items():
            actual = machine.reg(CLKGATE + bank * 4, mask)
            if actual:
                raise AssertionError(f"{parent} gate{bank}: enabled mask remains {actual:#x}")
        if machine.reg(CLKGATE + 11 * 4, 1 << 12) != 1 << 12:
            raise AssertionError("emitted code touched reserved gate11.bit12")
        for name, value in rates.items():
            if machine.glob(name) != value:
                raise AssertionError(f"{parent} {name}: {machine.glob(name)} != {value}")

    # A stuck CLKSEL42 parent bit must refuse before power with error 67.
    clock42 = CLKSEL + 42 * 4
    machine = Machine(800_000_000, {clock42: 1 << 7})
    if machine.call("rockcrudisplayclocks") != 0 or machine.glob("rock_cru_error") != 67:
        raise AssertionError("emitted CLKSEL42 readback did not fail closed with error 67")

    # The selected-mode wrapper must independently own and verify CLKSEL50
    # and its DCLK gate, even after initial display preparation.
    clock50 = CLKSEL + 50 * 4
    machine = Machine(800_000_000)
    machine.cpu.raw_store(symbols["global_rock_mode_valid"], 1, 8)
    if machine.call("rockcruvpllmode") != 1:
        raise AssertionError("emitted selected-mode clock wrapper refused valid setup")
    if machine.reg(clock50, 0x0BFF) != 0 or machine.reg(CLKGATE + 10 * 4, 0x2000):
        raise AssertionError("emitted selected-mode wrapper did not select/enable VPLL DCLK")

    machine = Machine(800_000_000, {clock50: 1 << 8})
    machine.cpu.raw_store(symbols["global_rock_mode_valid"], 1, 8)
    if machine.call("rockcruvpllmode") != 0 or machine.glob("rock_cru_error") != 73:
        raise AssertionError("emitted selected-mode CLKSEL50 failure did not return error 73")

    gate10 = CLKGATE + 10 * 4
    machine = Machine(800_000_000, {gate10: 1 << 13})
    machine.cpu.raw_store(symbols["global_rock_mode_valid"], 1, 8)
    if machine.call("rockcruvpllmode") != 0 or machine.glob("rock_cru_error") != 74:
        raise AssertionError("emitted selected-mode DCLK gate failure did not return error 74")

    print("ROCK Pi 4C emitted CRU contract: PASS (GPLL 800/594 and refusal paths)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, help="execute the exact emitted image contract")
    args = parser.parse_args()
    source = CRU.read_text(encoding="utf-8")

    # The two real handoff rates accepted by the product must both produce a
    # complete, bounded tree.  This models the exact ceiling-divider policy.
    check_rate_plan(594_000_000)
    check_rate_plan(800_000_000)

    # Exact RK3399 CRU fields from the pinned shipping clock driver.
    require(source, r"RockCruField\(#ROCK_CRU_CLKSEL\+\$A8,\$DFDF,clock42\)",
            "CLKSEL42 VIO+HDCP roots")
    require(source, r"RockCruField\(#ROCK_CRU_CLKSEL\+\$AC,\$7FFF,clock43\)",
            "CLKSEL43 VIO/HDCP children")
    require(source, r"RockCruField\(#ROCK_CRU_CLKSEL\+\$C0,\$1FDF,clock48\)",
            "CLKSEL48 VOPL ACLK/HCLK")
    require(source, r"RockCruField\(#ROCK_CRU_CLKSEL\+\$C8,\$0BFF,\$0000\)",
            "CLKSEL50 VPLL DIV/1 DCLK")
    require(source, r"RockCruExpect\(#ROCK_CRU_CLKSEL\+\$C8,\$0BFF,\$0000,73\)",
            "selected-mode CLKSEL50 readback")
    require(source, r"RockCruExpect\(#ROCK_CRU_CLKGATE\+10\*4,\$2000,0,74\)",
            "selected-mode DCLK gate readback")

    # Parent/NoC/leaf gates required by the pinned DT and genpd hierarchy.
    required_gates = {
        (11, 0): "ACLK_VIO",
        (11, 1): "PCLK_VIO",
        (11, 3): "HCLK_HDCP",
        (11, 8): "SCLK_DP_CORE",
        (11, 10): "PCLK_HDCP",
        (29, 0): "ACLK_VIO_NOC",
        (29, 3): "PCLK_HDCP_NOC",
        (29, 4): "ACLK_HDCP_NOC",
        (29, 5): "HCLK_HDCP_NOC",
        (29, 7): "PCLK_DP_CTRL",
        (29, 12): "PCLK_VIO_GRF",
        (28, 4): "HCLK_VOP1_NOC",
        (28, 5): "ACLK_VOP1_NOC",
        (28, 6): "HCLK_VOP1",
        (28, 7): "ACLK_VOP1",
    }
    for (bank, bit), name in required_gates.items():
        require(source, rf"RockCruGate\({bank},{bit},1\)", name)

    if re.search(r"RockCruGate\(11,12,1\)", source):
        raise AssertionError("reserved CRU gate11.bit12 reintroduced as ACLK_HDCP")

    # Deterministic ownership: all blocks are held before clock and power
    # setup, and the shipped CDN pulse is released core -> DPTX -> APB.
    prepare = source.index("Procedure.i RockCruDisplayPrepare()")
    clocks = source.index("If RockCruDisplayClocks()", prepare)
    power = source.index("If RockCruDisplayPower()", prepare)
    for reset_id in (275, 279, 281, 253, 259, 328, 330):
        pos = source.index(f"RockCruReset({reset_id},1)", prepare)
        if pos > clocks:
            raise AssertionError(f"reset {reset_id} is not asserted before clocks")
    if not clocks < power:
        raise AssertionError("clock contract must precede power-domain transitions")

    cadence = source[source.index("Procedure.i RockCruCadenceRelease()"):]
    release = [cadence.index(f"RockCruReset({reset_id},0)") for reset_id in (253, 328, 330)]
    if release != sorted(release):
        raise AssertionError("CDN release is not core -> DPTX -> APB")
    spdif_release = cadence.index("RockCruReset(259,0)")
    if spdif_release < release[-1]:
        raise AssertionError("SPDIF reset changed before the CDN video reset trio")

    if args.image:
        emitted_contract(args.image.resolve())
    print("ROCK Pi 4C CRU contract gate: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"ROCK Pi 4C CRU contract gate: FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)

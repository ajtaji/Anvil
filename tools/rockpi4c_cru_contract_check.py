#!/usr/bin/env python3
"""Desk gate for the RK3399 VOPL -> CDN DP clock/reset contract."""

from __future__ import annotations

from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
CRU = ROOT / "RockPi4C" / "Lib" / "cru.pbi"


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


def main() -> int:
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

    print("ROCK Pi 4C CRU contract gate: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"ROCK Pi 4C CRU contract gate: FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)

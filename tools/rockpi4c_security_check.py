#!/usr/bin/env python3
"""Gate the RK3399 BootROM-security release required by Anvil DMA."""
from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"rockpi4c_security_check: FAIL: {message}")


def procedure(source: str, name: str) -> str:
    match = re.search(
        rf"procedure(?:\.i)?\s+{re.escape(name)}\([^\n]*\)(.*?)endprocedure",
        source,
        re.DOTALL,
    )
    require(match is not None, f"missing {name} procedure")
    return match.group(1)


def main() -> None:
    security = (ROOT / "RockPi4C/Lib/security.pbi").read_text(
        encoding="utf-8"
    ).lower()
    board = (ROOT / "RockPi4C/Board/board.rockpi4c").read_text(
        encoding="utf-8"
    ).lower()

    for token in (
        "#rock_pmusgrf = $ff330000",
        "#rock_pmusgrf_ddr_rgn_con16 = $0040",
        "#rock_pmusgrf_slv_secure_con4 = $e3d4",
        "#rock_pmusgrf_ddr_region_mask = $01ff",
        "#rock_pmusgrf_slv_secure_mask = $2000",
    ):
        require(token in security, f"missing pinned PMUSGRF token: {token}")

    release = procedure(security, "rocksecurityreleasedma")
    order = (
        "rock_security_ddr_before=peekl(",
        "rock_security_slave_before=peekl(",
        "pokel(#rock_pmusgrf+#rock_pmusgrf_ddr_rgn_con16,#rock_pmusgrf_ddr_region_mask << 16)",
        "pokel(#rock_pmusgrf+#rock_pmusgrf_slv_secure_con4,#rock_pmusgrf_slv_secure_mask << 16)",
        "dsb sy",
        "rock_security_ddr_after=peekl(",
        "rock_security_slave_after=peekl(",
        "rock_security_ddr_after & #rock_pmusgrf_ddr_region_mask",
        "rock_security_slave_after & #rock_pmusgrf_slv_secure_mask",
        "procedurereturn 1",
    )
    positions = []
    for token in order:
        require(token in release, f"DMA-security release omits: {token}")
        positions.append(release.index(token))
    require(positions == sorted(positions), "DMA-security release order drifted")

    require('xincludefile "rockpi4c/lib/security.pbi"' in board,
            "board composition omits security.pbi")
    main_body = procedure(board, "main")
    validate = main_body.index("rockvalidateentry()")
    release_pos = main_body.index("rocksecurityreleasedma()")
    recovery = main_body.index("rockrecoveryloop()")
    require(validate < release_pos < recovery,
            "security regions must be released after entry validation and before recovery services")
    require("rocksecuritytelemetry()" in main_body,
            "startup omits security-state telemetry")
    require("rocksecurityreleasedma()" not in procedure(board, "rockrecoveryloop"),
            "security release must be one-time startup ownership, not a command-loop action")

    print("rockpi4c_security_check: PASS")


if __name__ == "__main__":
    main()

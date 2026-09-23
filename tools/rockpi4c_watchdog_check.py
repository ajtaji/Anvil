#!/usr/bin/env python3
"""Source/model gate for the RK3399 EL3 DesignWare watchdog deadman."""

from pathlib import Path
import argparse
import os
import re
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "RockPi4C/Lib/watchdog.pbi"
RECOVERY = ROOT / "RockPi4C/Lib/recovery.pbi"
BOARD = ROOT / "RockPi4C/Board/board.rockpi4c"

HARNESS = r'''#ANVIL_BUILD = 1
#ANVIL_BUILD_DATE = 20260921
#ANVIL_BUILD_TIME = 190000
#ROCK_CRU_CLKSEL = $100
Global rock_cru_error.i
Global rock_current_el.i
Procedure.i RockCruPllRate(offset.i, integerOnly.i, errorCode.i)
  ProcedureReturn 400000000
EndProcedure
Procedure.i RockCruRead(offset.i)
  ProcedureReturn 7
EndProcedure
Procedure RockUartText(text.i) : EndProcedure
Procedure RockUartByte(value.i) : EndProcedure
Procedure RockDisplayHexLong(value.i) : EndProcedure
XIncludeFile "RockPi4C/Lib/watchdog.pbi"
Procedure.i Main()
  rock_current_el=12
  If RockWatchdogArm()=0 : ProcedureReturn 0 : EndIf
  RockWatchdogPet()
  ProcedureReturn 1
EndProcedure
'''


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def body(source: str, name: str) -> str:
    match = re.search(
        rf"(?ims)^Procedure(?:\.i)?\s+{name}\([^\n]*\)\s*$(.*?)^EndProcedure\s*$",
        source,
    )
    require(match is not None, f"missing {name}")
    return match.group(1)


def designware_top(timeout_ms: int, clock_hz: int) -> int:
    cycles = timeout_ms * (clock_hz // 1000) - 1
    selector = cycles.bit_length() - 16
    return min(15, max(0, selector))


def rockchip_start_model(existing_cr: int, top: int) -> list[tuple[str, int]]:
    """Model local rockchip_wdt.c's timeout/enable/restart writes."""
    control = (existing_cr & ~0x02) | 0x01
    timeout = top | (top << 4)
    writes = []
    if existing_cr & 0x01:
        writes.append(("CRR", 0x76))
    writes.extend((("TORR", timeout), ("CR", control), ("CRR", 0x76)))
    return writes


def rk3399_torr_readback_ok(wanted: int, observed: int) -> bool:
    """RK3399 exposes TOP[3:0]; TOP_INIT and reserved bits read as zero."""
    return (observed & 0x0F) == (wanted & 0x0F) and (observed & 0xFFFFFFF0) == 0


def compile_harness(compiler: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="rockpi4c-watchdog-") as temp_name:
        temp = Path(temp_name)
        source = temp / "watchdog_contract.pb"
        output = temp / "watchdog_contract.bin"
        source.write_text(HARNESS, encoding="utf-8")
        command = [str(compiler), "--compile", str(source), "-t", "rockpi4c",
                   "--load-addr", "0x00041000", "--stack-addr", "0x05000000",
                   "--entry-returns", "-s", "-o", str(output)]
        run = subprocess.run(command, cwd=ROOT,
                             env=dict(os.environ, PMF_ROOT=str(ROOT)),
                             text=True, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, timeout=120)
        require(run.returncode == 0 and "pmfc: OK" in run.stdout,
                "isolated watchdog harness did not compile:\n" + run.stdout)
        require(output.is_file() and output.stat().st_size > 0,
                "isolated watchdog harness emitted no code")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path)
    args = parser.parse_args()
    source = SOURCE.read_text(encoding="utf-8")
    recovery = RECOVERY.read_text(encoding="utf-8")
    board = BOARD.read_text(encoding="utf-8")
    arm = body(source, "RockWatchdogArm")
    pet = body(source, "RockWatchdogPet")

    require("#ROCK_WATCHDOG_BASE = $FF848000" in source,
            "RK3399 watchdog MMIO base drifted")
    require("#ROCK_WATCHDOG_SGRF_SOC_CON3 = $E00C" in source,
            "RK3399 secure SOC_CON3 offset drifted")
    require("PokeL(#ROCK_WATCHDOG_SGRF+#ROCK_WATCHDOG_SGRF_SOC_CON3,$05000000)" in arm,
            "TF-A CA53/CM0 watchdog clocks are not ungated with a write mask")
    require("rock_watchdog_clksel57=RockCruRead(#ROCK_CRU_CLKSEL+57*4)" in arm and
            "divider=(rock_watchdog_clksel57 & $1F)+1" in arm,
            "watchdog rate is not derived from live pclk_alive")
    cr_read = "rock_watchdog_cr_before=PeekL(#ROCK_WATCHDOG_BASE+#ROCK_WATCHDOG_CR)"
    torr_write = "PokeL(#ROCK_WATCHDOG_BASE+#ROCK_WATCHDOG_TORR,rock_watchdog_torr)"
    cr_write = "PokeL(#ROCK_WATCHDOG_BASE+#ROCK_WATCHDOG_CR,value)"
    restart = "PokeL(#ROCK_WATCHDOG_BASE+#ROCK_WATCHDOG_CRR,#ROCK_WATCHDOG_RESTART)"
    require("value=(rock_watchdog_cr_before & $FFFFFFFD) | 1" in arm,
            "watchdog CR is not preserved with RMOD clear and enable set")
    cr_read_at = arm.index(cr_read)
    torr_at = arm.index(torr_write)
    cr_write_at = arm.index(cr_write)
    require("If (rock_watchdog_cr_before & 1)<>0" in arm and
            cr_read_at < arm.index(restart, cr_read_at) < torr_at,
            "live inherited watchdog is not fed before timeout programming")
    require(cr_read_at < torr_at < cr_write_at < arm.rindex(restart),
            "Rockchip watchdog read/pre-feed/TORR/CR/restart order drifted")
    require("PokeL(#ROCK_WATCHDOG_BASE+#ROCK_WATCHDOG_CR,0)" not in arm,
            "watchdog is disabled before Rockchip start sequence")
    require(restart in arm,
            "arm path omits the DesignWare restart key")
    require("RockCruReset" not in source,
            "watchdog invented a reset absent from the RK3399 DT node")
    require("If rock_current_el<>12" in arm,
            "secure watchdog gate is reachable below EL3")
    require("rock_watchdog_active=1" in arm and
            arm.index("rock_watchdog_active=1") < arm.index("rock_watchdog_cr=PeekL"),
            "hardware-active state is not published before readback refusal")
    require("If rock_watchdog_active<>0" in pet,
            "an inactive pet can modify watchdog hardware")
    require("#ROCK_WATCHDOG_ERROR_CR = 5" in source and
            "#ROCK_WATCHDOG_ERROR_TORR = 6" in source,
            "post-enable failure codes drifted")
    require("rock_watchdog_error=#ROCK_WATCHDOG_ERROR_CR" in arm and
            "rock_watchdog_error=#ROCK_WATCHDOG_ERROR_TORR" in arm,
            "post-enable readbacks lack exact failure codes")
    require("(rock_watchdog_torr_read & $0F)<>(rock_watchdog_torr & $0F)" in arm and
            "(rock_watchdog_torr_read & $FFFFFFF0)<>0" in arm,
            "TORR validation does not match RK3399's implemented low nibble")
    for telemetry in ("rock_watchdog_sgrf", "rock_watchdog_clksel57",
                      "rock_watchdog_gpll_hz", "rock_watchdog_clock_hz",
                      "rock_watchdog_cr_before", "rock_watchdog_cr",
                      "rock_watchdog_torr_read",
                      "rock_watchdog_torr"):
        require(telemetry in source, f"missing watchdog telemetry: {telemetry}")
    refusal = recovery[recovery.index("If RockWatchdogArm()=0"):]
    require(refusal.index("RockWatchdogTelemetry()") < refusal.index("ProcedureReturn"),
            "recovery refusal omits watchdog telemetry")
    auto_refusal = board[board.index("If RockWatchdogArm()=0"):]
    require("RockWatchdogTelemetry()" in auto_refusal,
            "automatic HDMI refusal omits watchdog telemetry")

    # U-Boot's fls(cycles - 1) - 16 formula, including clamp endpoints.
    cases = ((8_000, 24_000_000, 12), (8_000, 49_500_000, 13),
             (8_000, 100_000_000, 14), (1, 1_000_000, 0))
    for timeout_ms, clock_hz, expected in cases:
        actual = designware_top(timeout_ms, clock_hz)
        require(actual == expected,
                f"timeout model mismatch at {clock_hz}: {actual} != {expected}")

    writes = rockchip_start_model(0xA7, 13)
    require(writes == [("CRR", 0x76), ("TORR", 0xDD),
                       ("CR", 0xA5), ("CRR", 0x76)],
            f"Rockchip CR preserve/mode/enable model drifted: {writes}")
    require(rk3399_torr_readback_ok(0xDD, 0x0D),
            "physical build 104 TOP readback was rejected")
    for invalid in (0x0C, 0x1D, 0xED, 0x1000000D):
        require(not rk3399_torr_readback_ok(0xDD, invalid),
                f"invalid TORR readback accepted: {invalid:#x}")

    if args.compiler:
        compile_harness(args.compiler.resolve())

    print("Rock Pi 4C RK3399 watchdog contract: PASS" +
          (" (compiled)" if args.compiler else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

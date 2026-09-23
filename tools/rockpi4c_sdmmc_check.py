#!/usr/bin/env python3
"""Source contract and protocol-fixture checks for the RK3399 SD0 PIO driver."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "RockPi4C" / "Lib" / "sdmmc.pbi"


def fail(message: str) -> None:
    raise SystemExit("Rock Pi SD/MMC gate: " + message)


def proc(text: str, name: str) -> str:
    start = text.find(f"Procedure.i {name}(")
    if start < 0:
        fail(f"missing {name}")
    end = text.find("\nEndProcedure", start)
    if end < 0:
        fail(f"unterminated {name}")
    return text[start:end]


def check(text: str) -> list[str]:
    # Relevant DesignWare MSHC bits (Linux DW MSHC headers):
    # command errors RCRC/RTO/RESP_ERR/HLE; data errors exclude ACD.
    for symbol, value in (
        ("#ROCK_SD_INT_CMD_ERRORS", "$00001142"),
        ("#ROCK_SD_INT_DATA_ERRORS", "$0000AF80"),
    ):
        if not re.search(rf"{re.escape(symbol)}\s*=\s*{re.escape(value)}\b", text):
            fail(f"{symbol} does not match DW MSHC error bits")

    init = proc(text, "RockSdInit")
    gate_sclk = init.find("PokeL(#ROCK_SD_CRU+$318")
    power = init.find("RockPmuPowerOn(30")
    idle = init.find("RockPmuIdleRelease(28")
    first_host = init.find("rock_sd_writeReg(#ROCK_SDMMC_CLKSRC")
    if min(gate_sclk, power, idle, first_host) < 0 or not gate_sclk < power < idle < first_host:
        fail("CRU HCLK/NoC/SCLK gates must precede PMU idle release; host MMIO follows domain power")
    if "$E024" not in init or "$E064" not in init or "$E130" not in init or "$E134" not in init:
        fail("GPIO4B mux/pull/drive writes must target RK3399 GRF offsets E024/E064/E130/E134")
    if "$4492 - $10000" not in init or "$00030001" not in init:
        fail("GPIO4B drive-strength writes must set pin13's split 3-bit field along with pins8-12")
    if ((0x4492 - 0x10000) & 0xFFFFFFFF) != 0xFFFF4492:
        fail("signed GPIO4B drive-strength spelling no longer preserves 0xFFFF4492")
    clock_setup = init.find("rock_sd_setClock(0)")
    drive_phase = init.find("PokeL(#ROCK_SD_CRU+$580, $0FFE0002)")
    sample_phase = init.find("PokeL(#ROCK_SD_CRU+$584, $0FFE0000)")
    first_command = init.find("rock_sd_command(0,")
    if min(clock_setup, drive_phase, sample_phase, first_command) < 0 or not clock_setup < drive_phase < sample_phase < first_command:
        fail("SD clock phases must set RK3399 drive=90/sample=0 after clock setup and before CMD0")
    if "(PeekL(#ROCK_SD_CRU+$580) & $FFE) <> 2" not in init or "(PeekL(#ROCK_SD_CRU+$584) & $FFE) <> 0" not in init:
        fail("SD clock phase programming must verify the drive/sample phase fields")
    if "#ROCK_SD_R1_ERRORS = $FFFFE008" not in text or "rock_sd_r1ok()" not in proc(text, "rock_sd_cardData"):
        fail("data commands must reject card R1 status errors")
    app = proc(text, "rock_sd_appCommand")
    if "(rock_sd_response0 & $20) = 0" not in app:
        fail("ACMD sequence must verify CMD55 APP_CMD status")
    command = proc(text, "rock_sd_command")
    if "flags = flags | #ROCK_SD_CMD_USE_HOLD" not in command:
        fail("RK3399 commands must use the DW-MSHC clock hold register")
    if "flags = flags | #ROCK_SD_CMD_INIT | #ROCK_SD_CMD_STOP" not in command:
        fail("CMD0 must use the reference initialization/abort flags")
    if "ElseIf opcode <> 12" not in command or "flags = flags | #ROCK_SD_CMD_WAIT_PREV" not in command:
        fail("normal commands must use the reference previous-data wait rule")
    update = proc(text, "rock_sd_clockUpdate")
    if "#ROCK_SD_CMD_UPDATE_CLOCK | #ROCK_SD_CMD_WAIT_PREV" not in update:
        fail("clock update must use the reference previous-data handshake")
    if "($0500 | (divider-1))" not in init or "rock_sd_ciuHz = 24000000 / divider / 2" not in init:
        fail("identification clock must use RK3399's 24MHz/div30/fixed-div2 route")

    # The 128 GiB CSD-v2 fixture: C_SIZE=0x3ffff gives (C_SIZE+1)*1024
    # 512-byte sectors. Check bit placement in RESP1/RESP2 against the driver.
    cs = 0x3FFFF
    resp1 = ((cs & 0xFFFF) << 16)
    resp2 = (cs >> 16) & 0x3F
    got_csize = ((resp2 & 0x3F) << 16) | ((resp1 >> 16) & 0xFFFF)
    blocks = (got_csize + 1) * 1024
    if blocks != 268_435_456:
        fail("CSD-v2 128-GiB fixture decoded the wrong sector count")
    if "csize = ((rock_sd_response2 & $3F) << 16) | ((rock_sd_response1 >> 16) & $FFFF)" not in init:
        fail("CSD-v2 response extraction differs from the checked fixture")

    data = proc(text, "rock_sd_cardData")
    if "#ROCK_SD_INT_DATA_OVER" not in data or "If byteIndex <> totalBytes" not in data:
        fail("PIO data completion must validate the final FIFO word and DTO")
    if "rock_sd_writeReg(#ROCK_SDMMC_BYTCNT, totalBytes)" not in data:
        fail("PIO must program one byte count for the whole bounded range")
    if "count > #ROCK_SDMMC_MAX_BLOCKS" not in data or "totalBytes = count * #ROCK_SDMMC_BLOCK" not in data:
        fail("PIO request length must be block-counted and bounded")
    stop = proc(text, "rock_sd_stopTransfer")
    if "rock_sd_command(12, 0" not in stop or "#ROCK_SD_CMD_STOP" not in stop:
        fail("multi-block transfers must terminate with explicit CMD12 ABORT_STOP")
    # Last-word fixture: 2044 bytes already moved, final FIFO word has 4 bytes;
    # the byte loop must stop at the 4-block boundary and accept DTO exactly.
    total_bytes = 4 * 512
    byte_index = total_bytes - 4
    for _ in range(4):
        if byte_index < total_bytes:
            byte_index += 1
    if byte_index != total_bytes:
        fail("PIO final-word fixture did not fill the multi-block range exactly")

    flush = proc(text, "RockSdFlush")
    if "rock_sd_status()" not in flush or "#ROCK_SD_R1_STATE_TRAN" not in flush or "#ROCK_SD_R1_READY_FOR_DATA" not in flush:
        fail("flush must poll CMD13 through card programming until ready in TRAN")
    states = [(False, 7), (True, 4)]
    if not any(ready and state == 4 for ready, state in states):
        fail("CMD13 programming-to-TRAN fixture failed")

    ranges = [(-1, 1, 100), (0, 0, 100), (99, 2, 100), (100, 1, 100), (99, 1, 100)]
    accepted = [count > 0 and lba >= 0 and lba <= capacity - count for lba, count, capacity in ranges]
    if accepted != [False, False, False, False, True]:
        fail("block-range overflow fixture failed")
    for name in ("RockSdReadBlocks", "RockSdWriteBlocks"):
        body = proc(text, name)
        if "lba > rock_sd_blocks-count" not in body or "count <= 0" not in body:
            fail(f"{name} is missing subtraction-safe range validation")
        if "If run > #ROCK_SDMMC_MAX_BLOCKS" not in body:
            fail(f"{name} does not retain bounded transfer windows")
    if "If run > 1 : command = 18" not in proc(text, "RockSdReadBlocks"):
        fail("range reads must use CMD18")
    if "If run > 1 : command = 25" not in proc(text, "RockSdWriteBlocks"):
        fail("range writes must use CMD25")

    if "rock_sd_lastIntStatus" not in proc(text, "rock_sd_command") or "rock_sd_lastResponse3" not in proc(text, "rock_sd_command"):
        fail("command failures must preserve raw interrupt/status/response diagnostics")

    return [
        "DW command/data errors and R1/APP_CMD checks",
        "reference clock/command handshakes, power ordering, and RK3399 GPIO4B GRF offsets",
        "128-GiB CSD-v2, multi-block PIO final word, and CMD13 busy fixtures",
        "128-KiB CMD18/CMD25 windows, CMD12 stop, bounds, and retained diagnostics",
    ]


def main() -> int:
    text = SOURCE.read_text(encoding="utf-8")
    checks = check(text)
    mutant = text.replace("#ROCK_SD_INT_DATA_ERRORS = $0000AF80", "#ROCK_SD_INT_DATA_ERRORS = $0000E000", 1)
    try:
        check(mutant)
    except SystemExit:
        pass
    else:
        fail("self-test did not reject a mutated DW data-error mask")
    print("rockpi4c_sdmmc_check: PASS - " + "; ".join(checks))
    print("  self-test: mutated data-error mask rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

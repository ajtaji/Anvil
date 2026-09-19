#!/usr/bin/env python3
"""Focused desk gate for the Rock Pi 4C FTDI recovery/reset path."""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
ROCK = ROOT / "RockPi4C"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def procedure(source: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^Procedure(?:Naked)?(?:\.i)?\s+{re.escape(name)}\([^\n]*\)"
        rf".*?^EndProcedure\s*$",
        source,
    )
    require(match is not None, f"missing production procedure {name}")
    return match.group(0)


def source_contract() -> None:
    uart = (ROCK / "Lib/uart2.pbi").read_text(encoding="utf-8")
    recovery = (ROCK / "Lib/recovery.pbi").read_text(encoding="utf-8")
    exceptions = (ROCK / "Lib/exceptions_el2.pbi").read_text(encoding="utf-8")
    board = (ROCK / "Board/board.rockpi4c").read_text(encoding="utf-8")
    uart_l = uart.lower()
    recovery_l = recovery.lower()
    board_l = board.lower()

    for token in (
        "#rock_uart_lsr_dr = $01", "#rock_uart_lsr_rx_errors = $1e",
        "#rock_uart_lsr_temt = $40", "procedure.i rockuartreceive()",
        "procedure.i rockuartdrain()",
    ):
        require(token in uart_l, f"UART recovery contract drifted: {token}")
    receive = procedure(uart, "RockUartReceive").lower()
    require("peekl(#rock_uart2+#rock_uart_lsr)" in receive,
            "UART receive no longer uses a 32-bit LSR access")
    require("#rock_uart_lsr_rx_errors" in receive and
            "procedurereturn -2" in receive,
            "UART receive errors are no longer distinct from no-data")
    require(receive.index("#rock_uart_lsr_rx_errors") <
            receive.index("#rock_uart_lsr_dr)=0"),
            "UART exposes a byte before checking OE/PE/FE/BI")
    require("peekl(#rock_uart2+#rock_uart_thr) & 255" in receive,
            "UART RBR is not consumed with the RK3399 32-bit access contract")
    drain = procedure(uart, "RockUartDrain").lower()
    require("#rock_uart_lsr_temt" in drain and
            "#rock_uart_lsr_thre" not in drain,
            "reset drain does not wait for the transmitter shift register")
    require("for attempt=0 to 999999" in drain and
            "rock_timer_frequency/10" in drain,
            "UART TEMT drain lost its finite iteration/time bounds")

    psci = procedure(recovery, "RockRecoveryPsciReset").lower()
    for token in ("movz x0, #0x0009", "movk x0, #0x8400, lsl #16",
                  "mov x1, xzr", "mov x2, xzr", "mov x3, xzr",
                  "dsb sy", "smc #0"):
        require(token in psci, f"PSCI SYSTEM_RESET ABI drifted: {token}")
    require("hvc" not in psci, "NS-EL2 reset regressed from SMC to HVC")
    require("#rock_cru" not in recovery_l and
            not re.search(r"\bpokel\s*\(", recovery_l),
            "recovery gained an unsafe direct-MMIO reset fallback")

    reset = procedure(recovery, "RockRecoveryReset").lower()
    reset_order = [
        "msr daifset", 'rockuartline("reset: psci system_reset")',
        "rockuartdrain()", "rockrecoverypscireset()",
        'rockuarttext("reset failed psci x0=")', "rockrecoveryhex64(status)",
        "rockuartdrain()", "rockrecoveryfailstop()",
    ]
    cursor = 0
    for token in reset_order:
        position = reset.find(token, cursor)
        require(position >= 0,
                f"reset announce/drain/SMC/failure order drifted at {token}")
        cursor = position + len(token)
    require("if rockuartdrain" not in reset.split(
        "rockrecoverypscireset()", 1)[0],
        "UART drain failure can suppress the terminal PSCI request")

    reboot = procedure(recovery, "RockRecoveryLineIsReboot").lower()
    help_ = procedure(recovery, "RockRecoveryLineIsHelp").lower()
    require("rock_recovery_length<>6" in reboot and
            all(f")={value}" in reboot for value in (114, 101, 98, 111, 111, 116)),
            "reboot predicate no longer requires exact lowercase `reboot`")
    require("rock_recovery_length<>4" in help_ and
            all(f")={value}" in help_ for value in (104, 101, 108, 112)),
            "help predicate no longer requires exact lowercase `help`")
    finish = procedure(recovery, "RockRecoveryFinishLine").lower()
    finish_order = ["if rock_recovery_discard<>0",
                    "elseif rock_recovery_length=0",
                    "elseif rockrecoverylineisreboot()<>0",
                    "elseif rockrecoverylineishelp()<>0"]
    finish_positions = [finish.index(token) for token in finish_order]
    require(finish_positions == sorted(finish_positions),
            "discard/empty/exact-command parser order drifted")
    require(finish.count("rockrecoveryreset()") == 1,
            "parser has another path into system reset")
    poll = procedure(recovery, "RockRecoveryPoll").lower()
    for token in ("for attempt=0 to #rock_recovery_poll_bytes-1",
                  "if value=-1 : break", "if value=-2",
                  "rock_recovery_discard=1",
                  "elseif rock_recovery_length>=#rock_recovery_line_bytes"):
        require(token in poll, f"bounded/error parser contract drifted: {token}")

    require('xincludefile "rockpi4c/lib/recovery.pbi"' in board_l,
            "Rock Pi composition root omits recovery.pbi")
    entry_failure = board_l.split("if rockvalidateentry() = 0", 1)[1].split(
        "if rockexceptioninstall() = 0", 1)[0]
    require("rockpark()" in entry_failure and "rockrecoveryloop()" not in entry_failure,
            "untrusted early handoff can enter the recovery command parser")
    require("procedure rockrecoveryloop()" in board_l and
            "rockrecoverypoll()" in board_l,
            "trusted late FTDI polling loop is not wired")
    fatal_loop = procedure(recovery, "RockRecoveryFatalLoop").lower()
    for token in ("rockrecoveryinit()", "rockrecoverypoll()",
                  "rocktimerwaitus(1000)"):
        require(token in fatal_loop,
                f"fatal FTDI recovery loop drifted: {token}")
    fatal = procedure(exceptions, "RockExceptionFatal").lower()
    require(fatal.index("mov sp, x9") < fatal.index("bl rockexceptionreport") <
            fatal.index("bl rockrecoveryfatalloop") < fatal.index("rock_exception_park:"),
            "fatal vector does not enter recovery from the emergency stack")
    require("there is no prefix execution, abbreviation or network transport" in
            recovery_l and not re.search(r"\b(?:rocknet|netrecv|dhcp)[a-z0-9_]*\s*\(",
                                         recovery_l),
            "recovery advertises or calls a nonexistent Rock Pi network path")


def reference_parser_contract() -> None:
    def parse(line: bytes, *, contaminated: bool = False) -> str:
        if contaminated or len(line) > 16 or any(b < 32 or b > 126 for b in line):
            return "discard"
        if line == b"reboot":
            return "reboot"
        if line == b"help":
            return "help"
        return "empty" if not line else "error"

    accepted = [value for value in (
        b"reboot", b"reboo", b"rebootx", b" reboot", b"reboot ", b"Reboot",
        b"REBOOT", b"reboot\x00", b"help", b"helpful", b"r" * 16,
        b"r" * 17,
    ) if parse(value) == "reboot"]
    require(accepted == [b"reboot"],
            f"reference grammar admits non-exact reboot strings: {accepted}")
    require(parse(b"reboot", contaminated=True) == "discard",
            "a UART error can preserve an executable command")
    require(parse(b"r" * 17) == "discard",
            "line overflow can preserve an executable prefix")


def emitted_parser_contract(compiler: Path) -> None:
    load = 0x02000040
    bss = 0x02800000
    stack = 0x05000000
    returned = 0x06000000
    with tempfile.TemporaryDirectory(prefix="anvil-rockpi4c-recovery-") as temp_name:
        work = Path(temp_name)
        fixture = work / "recovery_fixture.rockpi4c"
        fixture.write_text(
            "; Desk-only recovery-parser fixture. It must never be booted.\n"
            'XIncludeFile "RockPi4C/Lib/soc.pbi"\n'
            'XIncludeFile "RockPi4C/Lib/arch_timer.pbi"\n'
            'XIncludeFile "RockPi4C/Lib/uart2.pbi"\n'
            'XIncludeFile "RockPi4C/Lib/recovery.pbi"\n\n'
            "Procedure.i Main()\n"
            "  RockRecoveryInit()\n"
            "  RockRecoveryPoll()\n"
            "  ProcedureReturn 0\n"
            "EndProcedure\n",
            encoding="utf-8", newline="\n",
        )
        image = work / "recovery.img"
        command = [
            str(compiler), "--compile", str(fixture), "-t", "rockpi4c",
            "--entry-returns", "--load-addr", hex(load), "--bss-addr", hex(bss),
            "--stack-addr", hex(stack), "-S", "-s", "-o", str(image),
        ]
        run = subprocess.run(
            command, cwd=ROOT, env={**os.environ, "PMF_ROOT": str(ROOT)},
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=120,
        )
        require(run.returncode == 0 and image.is_file(),
                "recovery fixture compile failed:\n" + run.stdout)
        symbol_file = Path(str(image) + ".sym")
        assembly_file = Path(str(image) + ".asm")
        require(symbol_file.is_file() and assembly_file.is_file(),
                "recovery fixture omitted symbols or emitted assembly")
        symbols = {key.lower(): int(value, 0) for key, value in (
            line.split("=", 1) for line in symbol_file.read_text().splitlines()
            if "=" in line
        )}
        required = (
            "rockrecoverylineisreboot", "rockrecoverylineishelp",
            "rockrecoveryfinishline", "rockrecoveryreset",
            "global_rock_recovery_line", "global_rock_recovery_length",
            "global_rock_recovery_discard", "global_rock_uart_ready",
        )
        require(not [name for name in required if name not in symbols],
                "recovery fixture symbol map is incomplete")
        blob = image.read_bytes()
        asm = assembly_file.read_text(encoding="utf-8", errors="replace").lower()
        psci_asm = asm.split("rockrecoverypscireset:", 1)[1].split(
            "rockrecoveryfailstop:", 1)[0]
        require("hvc" not in psci_asm,
                "emitted reset uses HVC instead of the retained EL3 SMC")
        psci_offset = symbols.get("rockrecoverypscireset")
        require(psci_offset is not None, "recovery fixture omitted PSCI reset symbol")
        words = tuple(int.from_bytes(blob[psci_offset + index * 4:
                                          psci_offset + index * 4 + 4], "little")
                      for index in range(8))
        require(words == (
            0xD2800120, 0xF2B08000, 0xAA1F03E1, 0xAA1F03E2,
            0xAA1F03E3, 0xD5033F9F, 0xD4000003, 0xD65F03C0,
        ), f"emitted PSCI register/SMC words drifted: {words!r}")

        spec = importlib.util.spec_from_file_location(
            "rockpi4c_recovery_a64", ROOT / "tools/a64/a64_interp.py")
        require(spec is not None and spec.loader is not None,
                "cannot load repository A64 interpreter")
        a64 = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = a64
        spec.loader.exec_module(a64)

        def cpu_for(line: bytes, length: int | None = None,
                    discard: int = 0):
            cpu = a64.A64()
            for offset, byte in enumerate(blob):
                cpu.memory[load + offset] = byte
            a64.attach_symbols(cpu, image, load)
            for offset, byte in enumerate(line[:16]):
                cpu.memory[symbols["global_rock_recovery_line"] + offset] = byte
            cpu.store(symbols["global_rock_recovery_length"],
                      len(line) if length is None else length, 8)
            cpu.store(symbols["global_rock_recovery_discard"], discard, 8)
            cpu.store(symbols["global_rock_uart_ready"], 0, 8)
            cpu.sp = stack
            cpu.x[30] = returned
            return cpu

        def run_predicate(name: str, line: bytes) -> int:
            cpu = cpu_for(line)
            cpu.pc = load + symbols[name]
            for _ in range(20_000):
                if cpu.pc == returned:
                    return cpu.x[0]
                cpu.step()
            raise AssertionError(f"emitted {name} did not return")

        reboot_cases = {
            b"reboot": 1, b"reboo": 0, b"rebootx": 0, b" reboot": 0,
            b"reboot ": 0, b"Reboot": 0, b"help": 0,
            b"reboot\x00": 0, b"r" * 16: 0,
        }
        for line, expected in reboot_cases.items():
            require(run_predicate("rockrecoverylineisreboot", line) == expected,
                    f"emitted reboot predicate drifted for {line!r}")
        require(run_predicate("rockrecoverylineishelp", b"help") == 1 and
                run_predicate("rockrecoverylineishelp", b"helpful") == 0,
                "emitted help predicate accepts a prefix/suffix")

        reset_pc = load + symbols["rockrecoveryreset"]

        def finish_route(line: bytes, *, length: int | None = None,
                         discard: int = 0) -> tuple[str, object]:
            cpu = cpu_for(line, length, discard)
            cpu.pc = load + symbols["rockrecoveryfinishline"]
            for _ in range(100_000):
                if cpu.pc == reset_pc:
                    return "reset", cpu
                if cpu.pc == returned:
                    return "return", cpu
                cpu.step()
            raise AssertionError("emitted RockRecoveryFinishLine did not settle")

        route, _ = finish_route(b"reboot")
        require(route == "reset", "exact emitted reboot does not reach PSCI path")
        for line in (b"reboo", b"rebootx", b" reboot", b"Reboot", b"help"):
            route, _ = finish_route(line)
            require(route == "return", f"non-exact command reached reset: {line!r}")
        for label, line, length in (
            ("UART-error", b"reboot", 6),
            ("overflow", b"reboot" + b"x" * 10, 16),
        ):
            route, cpu = finish_route(line, length=length, discard=1)
            require(route == "return", f"{label} line reached reset")
            require(cpu.load(symbols["global_rock_recovery_length"], 8) == 0 and
                    cpu.load(symbols["global_rock_recovery_discard"], 8) == 0,
                    f"{label} line did not reset parser state")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path)
    args = parser.parse_args()
    source_contract()
    reference_parser_contract()
    if args.compiler:
        emitted_parser_contract(args.compiler.resolve())
    print("ROCK Pi 4C FTDI recovery desk gate: PASS")
    print("network: NOT IMPLEMENTED; silicon: NOT RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

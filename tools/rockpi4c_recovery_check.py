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
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler


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
    exceptions = (ROCK / "Lib/exceptions_el3.pbi").read_text(encoding="utf-8")
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

    warm_reset = procedure(recovery, "RockRecoveryWarmReset").lower()
    for token in ("movz x9, #0x0300", "movk x9, #0xff32, lsl #16",
                  "str wzr, [x9]", "movz x9, #0x0504",
                  "movk x9, #0xff76, lsl #16", "movz w10, #0xeca8",
                  "dsb sy", "str w10, [x9]", "rock_reset_wait:", "wfe"):
        require(token in warm_reset, f"RK3399 warm-reset sequence drifted: {token}")
    require("smc #0" not in warm_reset and "hvc" not in warm_reset,
            "direct-EL3 warm reset unexpectedly relies on a PSCI monitor")
    require("#rock_cru" not in recovery_l and
            not re.search(r"\bpokel\s*\(", recovery_l),
            "recovery gained an unsafe direct-MMIO reset fallback")

    reset = procedure(recovery, "RockRecoveryReset").lower()
    reset_order = [
        "msr daifset", 'rockuartline("reset: rk3399 cru warm reset")',
        "rockuartdrain()", "rockrecoverywarmreset()",
        'rockuarttext("reset request returned x0=")', "rockrecoveryhex64(status)",
        "rockuartdrain()", "rockrecoveryfailstop()",
    ]
    cursor = 0
    for token in reset_order:
        position = reset.find(token, cursor)
        require(position >= 0,
                f"reset announce/drain/warm-reset/failure order drifted at {token}")
        cursor = position + len(token)
    require("if rockuartdrain" not in reset.split(
        "rockrecoverywarmreset()", 1)[0],
        "UART drain failure can suppress the terminal warm-reset request")

    reboot = procedure(recovery, "RockRecoveryLineIsReboot").lower()
    help_ = procedure(recovery, "RockRecoveryLineIsHelp").lower()
    hdmi = procedure(recovery, "RockRecoveryLineIsHdmi").lower()
    gpuinfo = procedure(recovery, "RockRecoveryLineIsGpuInfo").lower()
    require("rock_recovery_length<>6" in reboot and
            all(f")={value}" in reboot for value in (114, 101, 98, 111, 111, 116)),
            "reboot predicate no longer requires exact lowercase `reboot`")
    require("rock_recovery_length<>4" in help_ and
            all(f")={value}" in help_ for value in (104, 101, 108, 112)),
            "help predicate no longer requires exact lowercase `help`")
    require("rock_recovery_length<>4" in hdmi and
            all(f")={value}" in hdmi for value in (104, 100, 109, 105)),
            "HDMI predicate no longer requires exact lowercase `hdmi`")
    require("rock_recovery_length<>7" in gpuinfo and
            all(f")={value}" in gpuinfo for value in
                (103, 112, 117, 105, 110, 102, 111)),
            "GPU info predicate no longer requires exact lowercase `gpuinfo`")
    hdmi_command = procedure(recovery, "RockRecoveryHdmi").lower()
    arm_at = hdmi_command.index("rockwatchdogarm()")
    pet_at = hdmi_command.index("rockwatchdogpet()")
    attempted_at = hdmi_command.index("rock_recovery_hdmi_attempted=1")
    display_at = hdmi_command.index("rockhdmidisplayup()")
    require(arm_at < pet_at < attempted_at < display_at,
            "HDMI command can touch display state before the deadman is armed")
    require("if rockwatchdogarm()=0" in hdmi_command and
            "hdmi refused: deadman not armed" in hdmi_command,
            "HDMI command does not fail closed when watchdog setup fails")
    finish = procedure(recovery, "RockRecoveryFinishLine").lower()
    finish_order = ["if rock_recovery_discard<>0",
                    "elseif rock_recovery_length=0",
                    "elseif rockrecoverylineisreboot()<>0",
                    "elseif rockrecoverylineishelp()<>0",
                    "elseif rockrecoverylineishdmi()<>0",
                    "elseif rockrecoverylineisgpuinfo()<>0"]
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
    require('xincludefile "rockpi4c/lib/watchdog.pbi"' in board_l,
            "Rock Pi composition root omits the HDMI deadman implementation")
    entry_failure = board_l.split("if rockvalidateentry() = 0", 1)[1].split(
        "; el3 gic/timer", 1)[0]
    require("rockpark()" in entry_failure and "rockrecoveryloop()" not in entry_failure,
            "untrusted early handoff can enter the recovery command parser")
    require("procedure rockrecoveryloop()" in board_l and
            "rockrecoverypoll()" in board_l,
            "trusted late FTDI polling loop is not wired")
    recovery_loop = procedure(board, "RockRecoveryLoop").lower()
    require(recovery_loop.count("rockwatchdogpet()") >= 2 and
            recovery_loop.index("rockwatchdogpet()") <
            recovery_loop.index("rockrecoverypoll()") <
            recovery_loop.rindex("rockwatchdogpet()"),
            "healthy recovery loop does not pet the deadman around command polling")
    auto_hdmi = board_l.split(
        "if #rock_directsd_hdmi_enabled <> 0 and #rock_directsd_hdmi_auto <> 0",
        1,
    )[1].split("if rock_uart_ready <> 0", 1)[0]
    require("if rockwatchdogarm()=0" in auto_hdmi and
            auto_hdmi.index("rockwatchdogarm()") <
            auto_hdmi.index("rockhdmidisplayup()"),
            "automatic HDMI can run before the deadman is armed")
    fatal_loop = procedure(recovery, "RockRecoveryFatalLoop").lower()
    for token in ("rockrecoveryinit()", "rockrecoverypoll()",
                  "rocktimerwaitus(1000)"):
        require(token in fatal_loop,
                f"fatal FTDI recovery loop drifted: {token}")
    require("rockwatchdogpet()" not in fatal_loop,
            "fatal recovery can pet the watchdog and conceal a stalled subsystem")
    finish = procedure(recovery, "RockRecoveryFinishLine").lower()
    require("if rock_recovery_fatal_mode<>0" in finish and
            "err hdmi disabled in fatal recovery" in finish and
            "err gpuinfo disabled in fatal recovery" in finish and
            "err storage disabled in fatal recovery" in finish,
            "fatal recovery must allow only non-MMIO help/reset paths")
    fatal = procedure(exceptions, "RockExceptionFatal").lower()
    require(fatal.index("mov sp, x9") < fatal.index("bl rockexceptionreport") <
            fatal.index("bl rockrecoveryfatalloop") < fatal.index("rock_exception_park:"),
            "fatal vector does not enter recovery from the emergency stack")
    require("there is no prefix execution" in recovery_l and
            "abbreviation or network transport" in recovery_l and
            not re.search(r"\b(?:rocknet|netrecv|dhcp)[a-z0-9_]*\s*\(",
                          recovery_l),
            "recovery advertises or calls a nonexistent Rock Pi network path")


def reference_parser_contract() -> None:
    def parse(line: bytes, *, contaminated: bool = False) -> str:
        if contaminated or len(line) > 512 or any(b < 32 or b > 126 for b in line):
            return "discard"
        if line == b"reboot":
            return "reboot"
        if line == b"help":
            return "help"
        if line == b"hdmi":
            return "hdmi"
        return "empty" if not line else "error"

    accepted = [value for value in (
        b"reboot", b"reboo", b"rebootx", b" reboot", b"reboot ", b"Reboot",
        b"REBOOT", b"reboot\x00", b"help", b"helpful", b"r" * 512,
        b"r" * 513,
    ) if parse(value) == "reboot"]
    require(accepted == [b"reboot"],
            f"reference grammar admits non-exact reboot strings: {accepted}")
    require(parse(b"hdmi") == "hdmi" and parse(b"HDMI") == "error" and
            parse(b"hdmix") == "error" and parse(b"help") == "help",
            "reference grammar does not keep HDMI exact and lowercase")
    require(parse(b"reboot", contaminated=True) == "discard",
            "a UART error can preserve an executable command")
    require(parse(b"r" * 513) == "discard",
            "line overflow can preserve an executable prefix")


def emitted_parser_contract(compiler: Path) -> None:
    load = 0x00041000
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
            "Global rock_display_error.i\n"
            "Global rock_display_stage.i\n"
            "Global rock_exception_vbar.i\n"
            "Global rock_recovery_skip_lf.i\n"
            "Global rock_watchdog_armed.i\n"
            "Global rock_watchdog_active.i\n"
            "Global rock_gpu_error.i\n"
            "Global rock_gpu_pmu_pwrdn_con.i\n"
            "Global rock_gpu_pmu_pwrdn_st.i\n"
            "Global rock_gpu_pmu_idle_req.i\n"
            "Global rock_gpu_pmu_idle_st.i\n"
            "Global rock_gpu_pmu_idle_ack.i\n"
            "Global rock_gpu_clksel13.i\n"
            "Global rock_gpu_clkgate13.i\n"
            "Global rock_gpu_clkgate30.i\n"
            "Global rock_gpu_softrst18.i\n"
            "Global rock_gpu_id.i\n"
            "Global rock_gpu_mmu_features.i\n"
            "Global rock_gpu_as_present.i\n"
            "Global rock_gpu_js_present.i\n"
            "Global rock_gpu_status.i\n"
            "Global rock_gpu_job_int_js_state.i\n"
            "Global rock_gpu_mmu_int_stat.i\n"
            "#ROCK_STORAGE_STAGE_BYTES = 64\n"
            "Global Dim rock_storage_stage.a[#ROCK_STORAGE_STAGE_BYTES]\n"
            "Procedure.i rock_storage_parseHexToken(*line, lineLength.i, *position, *value)\n"
            "  ProcedureReturn 0\n"
            "EndProcedure\n"
            "Procedure.i rock_storage_onlySpace(*line, lineLength.i, position.i)\n"
            "  ProcedureReturn 0\n"
            "EndProcedure\n"
            "Procedure.i RockStorageReceive(length.i, checksum.i)\n"
            "  ProcedureReturn 0\n"
            "EndProcedure\n"
            "Procedure.i RockStorageCommand(*line, lineLength.i)\n"
            "  ProcedureReturn 0\n"
            "EndProcedure\n"
            "Procedure RockStorageHex8(value.i)\n"
            "EndProcedure\n"
            "Procedure.i RockHdmiDisplayUp()\n"
            "  ProcedureReturn 1\n"
            "EndProcedure\n"
            "Procedure.i RockGpuProbeReachability()\n"
            "  ProcedureReturn 1\n"
            "EndProcedure\n"
            "Procedure.i RockWatchdogArm()\n"
            "  ProcedureReturn 1\n"
            "EndProcedure\n"
            "Procedure RockWatchdogPet()\n"
            "EndProcedure\n"
            "Procedure RockWatchdogTelemetry()\n"
            "EndProcedure\n"
            "ProcedureNaked RockExceptionInstallRaw()\n"
            "  ASM\n"
            "    ret\n"
            "  ENDASM\n"
            "EndProcedure\n"
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
            "rockrecoverylineishdmi", "rockrecoverylineisgpuinfo",
            "global_rock_recovery_hdmi_attempted",
            "rockrecoveryfinishline", "rockrecoveryreset", "rockrecoverypoll",
            "rockrecoveryhdmi", "rockhdmidisplayup", "rockuartreceive",
            "rockuartline", "global_rock_recovery_ready",
            "global_rock_recovery_line", "global_rock_recovery_length",
            "global_rock_recovery_discard", "global_rock_uart_ready",
        )
        require(not [name for name in required if name not in symbols],
                "recovery fixture symbol map is incomplete")
        blob = image.read_bytes()
        asm = assembly_file.read_text(encoding="utf-8", errors="replace").lower()
        uart_byte_asm = asm.split("rockuartbyte:", 1)[1].split(
            "rockuartreceive:", 1)[0]
        require("blr x10" in uart_byte_asm,
                "emitted UART mirror seam is not an indirect call")
        callback_tail = uart_byte_asm.split("blr x10", 1)[1].split("__l", 1)[0]
        require(not re.search(r"\bldr\s+x\d+,\s*\[x11\]", callback_tail),
                "emitted UART mirror call dereferences its void return value")
        reset_asm = asm.split("rockrecoverywarmreset:", 1)[1].split(
            "rockrecoveryfailstop:", 1)[0]
        require("smc" not in reset_asm and "hvc" not in reset_asm,
                "emitted direct-EL3 warm reset calls an unrelated PSCI conduit")
        require("rockrecoverywarmreset" in symbols,
                "recovery fixture omitted warm-reset entry symbol")

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
        require(run_predicate("rockrecoverylineishdmi", b"hdmi") == 1 and
                run_predicate("rockrecoverylineishdmi", b"HDMI") == 0 and
                run_predicate("rockrecoverylineishdmi", b"hdmix") == 0,
                "emitted HDMI predicate is not exact lowercase")
        require(run_predicate("rockrecoverylineisgpuinfo", b"gpuinfo") == 1 and
                run_predicate("rockrecoverylineisgpuinfo", b"GPUINFO") == 0 and
                run_predicate("rockrecoverylineisgpuinfo", b"gpuinfox") == 0,
                "emitted GPU info predicate is not exact lowercase")

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
        require(route == "reset", "exact emitted reboot does not reach warm-reset path")
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

        # Exercise the emitted Poll -> FinishLine -> HDMI command chain with
        # a synthetic UART stream. Intercept only RockUartReceive so the
        # generated frames, nested calls, epilogues and return addresses all
        # execute unchanged, then prove an idle poll cannot replay the command.
        poll_pc = load + symbols["rockrecoverypoll"]
        receive_pc = load + symbols["rockuartreceive"]
        finish_pc = load + symbols["rockrecoveryfinishline"]
        hdmi_pc = load + symbols["rockrecoveryhdmi"]
        display_pc = load + symbols["rockhdmidisplayup"]
        uart_line_pc = load + symbols["rockuartline"]

        def c_string(cpu, address: int, limit: int = 128) -> bytes:
            value = bytearray()
            for offset in range(limit):
                byte = cpu.load(address + offset, 1)
                if byte == 0:
                    break
                value.append(byte)
            return bytes(value)

        cpu = cpu_for(b"")
        cpu.store(symbols["global_rock_recovery_ready"], 1, 8)
        cpu.pc = poll_pc
        incoming = [*b"hdmi\r", -1]
        visits = {"finish": 0, "hdmi": 0, "display": 0}
        lines: list[bytes] = []
        for _ in range(500_000):
            if cpu.pc == returned:
                break
            if cpu.pc == receive_pc:
                require(incoming, "emitted recovery poll over-read its UART stream")
                cpu.x[0] = incoming.pop(0) & ((1 << 64) - 1)
                cpu.pc = cpu.x[30]
                continue
            if cpu.pc == finish_pc:
                visits["finish"] += 1
            elif cpu.pc == hdmi_pc:
                visits["hdmi"] += 1
            elif cpu.pc == display_pc:
                visits["display"] += 1
            elif cpu.pc == uart_line_pc:
                lines.append(c_string(cpu, cpu.x[0]))
            cpu.step()
        else:
            raise AssertionError("emitted recovery HDMI command did not return")
        require(cpu.pc == returned and not incoming,
                "emitted recovery HDMI command did not consume one bounded line")
        require(visits == {"finish": 1, "hdmi": 1, "display": 1},
                f"emitted recovery command replayed a nested call: {visits}")
        require(lines.count(b"HDMI INIT BEGIN; DEADMAN ARMED; UART OUTPUT SYNCHRONOUS") == 1 and
                lines.count(b"HDMI INIT READY") == 1,
                f"emitted recovery command repeated its post-call output: {lines!r}")
        require(cpu.load(symbols["global_rock_recovery_length"], 8) == 0 and
                cpu.load(symbols["global_rock_recovery_discard"], 8) == 0,
                "emitted recovery command returned with live parser state")

        # A later empty poll must not redispatch the completed command.
        prior_lines = list(lines)
        prior_visits = dict(visits)
        cpu.x[30] = returned
        cpu.pc = poll_pc
        incoming = [-1]
        for _ in range(50_000):
            if cpu.pc == returned:
                break
            if cpu.pc == receive_pc:
                cpu.x[0] = incoming.pop(0) & ((1 << 64) - 1)
                cpu.pc = cpu.x[30]
                continue
            if cpu.pc == finish_pc:
                visits["finish"] += 1
            elif cpu.pc == hdmi_pc:
                visits["hdmi"] += 1
            elif cpu.pc == display_pc:
                visits["display"] += 1
            elif cpu.pc == uart_line_pc:
                lines.append(c_string(cpu, cpu.x[0]))
            cpu.step()
        else:
            raise AssertionError("emitted empty recovery poll did not return")
        require(cpu.pc == returned and not incoming and cpu.x[0] == 0,
                "emitted empty recovery poll did not report zero consumption")
        require(visits == prior_visits and lines == prior_lines,
                "emitted empty recovery poll replayed the completed command")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path)
    args = parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    source_contract()
    reference_parser_contract()
    if args.compiler:
        emitted_parser_contract(args.compiler.resolve())
    print("ROCK Pi 4C FTDI recovery desk gate: PASS")
    print("network: NOT IMPLEMENTED; silicon: NOT RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

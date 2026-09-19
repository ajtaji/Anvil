#!/usr/bin/env python3
"""Gate: a message for the user is never written to the command line.

Forum 791. Background services - the network console arming, a lease, the
radio rekeying or recovering, the mouse search - used to print through the
ordinary console path, which put their sentences straight after `pmf> ` and
into the middle of the line being typed. The rule since 2026-09-16 is that
such a message never reaches the command line at all: it goes to the message
log, the banner caption shows the newest, and `messages` prints them.

Two halves.

EXECUTED. RaspberryPi4/Tests/console_messages_emitted_gate.pi4 compiles the
real console write (RaspberryPi4/Lib/uart.pi4), the real line editor, the
real message log and the real banner caption, and runs them on the A64
model. This harness maps the PL011's flag and data registers and records
every byte the real UartWrite puts on the wire. One command line is typed
twice with the same keystrokes, the second time with background messages
fired between them - empty line, text before the caret, caret in the middle,
nested, no newline - and the whole wire stream must be exactly the bytes of
the quiet pass, twice. The screen mirror and the network tap are compared
inside the fixture. Mutants that route message bytes back into the stream,
or keep the banner quiet, must each be caught.

SOURCE. The bracket has to be where the background work actually runs, and
that is a property of the callers, so it is read from them: every call in
ReadLine's service loop outside a bracket must be one of the editor's own
input calls (so a service added to the loop later fails this gate unless it
is bracketed); the network poll a printing command makes, the mid-session
rekey entry, the payload-return housekeeping, the fatal exception report,
the diversion's position in both boards' console writes, the boards' start
of the log before the first prompt, and the five prompt bytes.

Requires external tools; neither is copied into the product tree:
  PMF_COMPILER=<path-to-PureMetalForge.exe> PMF_A64_INTERP=<path-to-a64_interp.py> \\
      python tools/console_messages_emitted_check.py
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import tcp_multiif_emitted_check as emitted


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "RaspberryPi4" / "Tests" / "console_messages_emitted_gate.pi4"
LOAD = emitted.LOAD
STACK = emitted.STACK
STACK_BYTES = emitted.STACK_BYTES
LOADER_LR = emitted.LOADER_LR
STEP_LIMIT = 80_000_000

UART_BASE = 0xFE201000
UART_DR = UART_BASE + 0x00
UART_FR = UART_BASE + 0x18

UART = "RaspberryPi4/Lib/uart.pi4"
BANNER = "RaspberryPi4/Board/banner_status.pi4"
PARSE = "Anvil/Core/parse.pbi"
RXBREAK = "Anvil/Core/rxbreak.pbi"
WIFI = "RaspberryPi4/Lib/wifi.pi4"
RUNAT = "RaspberryPi4/Board/cache.pi4"
EXCEPTION = "RaspberryPi4/Board/exception_support.pi4"
QCON = "ArduinoQ/Board/qcon_q.unoq"
PI4_BOARD = "RaspberryPi4/Board/board.pi4"
Q_BOARD = "ArduinoQ/Board/board.unoq"

# The quiet pass, byte for byte: the prompt, "vesion" typed, four Lefts, an
# "r" inserted with its tail re-sent and walked back, End re-sending the
# tail, and the newline after Enter. Nothing else may ever appear.
LINE = b"pmf> vesion\x08\x08\x08\x08rsion\x08\x08\x08\x08sion\r\n"

# Emitted mutants: (file, fixed text, broken text, assertion that must fire).
MUTATIONS = {
    "newline_leaks": (
        UART,
        "    If *uart_msgDrain <> 0\n      uart_MessagePut(c)\n",
        "    If *uart_msgDrain <> 0 And c <> 10\n      uart_MessagePut(c)\n",
        10,
        "a message's newline let through to the wire - one byte routed back "
        "onto the command line",
    ),
    "no_diversion": (
        UART,
        "  If uart_msgDepth > 0\n    If *uart_msgDrain <> 0\n",
        "  If uart_msgDepth > 1000000\n    If *uart_msgDrain <> 0\n",
        10,
        "the message context ignored, which is the defect as reported",
    ),
    "blank_kept": (
        "Anvil/Core/messages.pbi",
        "  If seen = 0\n    gMsgCurLen = 0\n    ProcedureReturn\n  EndIf\n",
        "",
        72,
        "a line with nothing visible in it kept as a message (forum 892)",
    ),
    "banner_silent": (
        BANNER,
        "  n = MessagesUnread()\n",
        "  n = 0\n",
        30,
        "messages kept off the command line and then shown nowhere",
    ),
}

# Calls ReadLine's loop may make OUTSIDE a message bracket: taking input in
# and applying it to the one edited line, and the bracket itself. Anything
# else in that loop is a service and must be inside one.
READLINE_OUTSIDE = {
    "InputEventsPop", "PeekL", "NetConsoleClaimLocal", "TextEditInsert",
    "TextEditKey", "TextEditKeyRelease", "TextEditCancelNotice", "TextEditDone",
    "InputErrText", "UartReadReady", "UartRead", "InputFeedByte",
    "KeyboardChar", "NetConsoleGetc", "UartMessageBegin", "UartMessageEnd",
}
# And the services that must be found inside one - so the check cannot pass
# by the loop having been emptied.
READLINE_SERVICES = [
    "NetConsoleRearm", "NetConsolePump", "NetConsoleLlTick", "HttpServerPoll",
    "TcpTick", "MouseTick", "TouchTick", "TouchKeyboardServiceTick",
    "ScreenServiceTick", "WifiLinkTick", "NetDhcpTick", "NtpServiceTick",
    "FanTick", "HwTempSampleTick",
]

SOURCE_MUTATIONS = {
    "readline_service_outside": (
        PARSE,
        "    UartMessageBegin()\n    NetConsoleRearm()\n",
        "    NetConsoleRearm()\n",
        "a service in the prompt's loop running outside the message context",
    ),
    "rekey_outside": (
        WIFI,
        "  UartMessageBegin()\n  wifi_ServiceEapol(*frame, len)\n  UartMessageEnd()\n",
        "  wifi_ServiceEapol(*frame, len)\n",
        "a mid-session rekey printing into whatever command's pump delivered it",
    ),
    "fault_diverted": (
        EXCEPTION,
        "  UartMessageAbandon()\n",
        "",
        "a fault inside a background service diverted into the message log",
    ),
}


class GateFailure(Exception):
    pass


def code_of(line: str) -> str:
    """The line without its comment. No string in these files holds a ';'
    that matters to a call scan, but strings are blanked first anyway."""
    blanked = re.sub(r'"[^"]*"', '""', line)
    return blanked.split(";", 1)[0]


def body_of(text: str, header: str) -> list[str]:
    start = text.find(header)
    if start < 0:
        raise GateFailure(f"cannot find `{header}`")
    end = text.find("EndProcedure", start)
    return text[start:end].splitlines()


def bracket_walk(lines: list[str], where: str):
    """Yield (depth, code) for each line, refusing a leak out of a bracket."""
    depth = 0
    for raw in lines:
        code = code_of(raw)
        if re.search(r"\bUartMessageBegin\s*\(", code):
            depth += 1
            continue
        if re.search(r"\bUartMessageEnd\s*\(", code):
            if depth == 0:
                raise GateFailure(f"{where}: a bracket is closed that was never opened")
            depth -= 1
            continue
        if depth and re.search(r"\b(Continue|Break|ProcedureReturn)\b", code):
            raise GateFailure(
                f"{where}: `{code.strip()}` leaves a message bracket open - every "
                "later byte of the monitor would be diverted"
            )
        yield depth, code
    if depth:
        raise GateFailure(f"{where}: a message bracket is never closed")


def calls_in(code: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r"\b([A-Za-z_]\w*)\s*\(", code)
            if m.group(1) not in {"If", "ElseIf", "While", "Until", "Bool", "Select", "Case"}]


def require_bracketed(text: str, header: str, names: list[str], where: str) -> None:
    seen = {name: None for name in names}
    for depth, code in bracket_walk(body_of(text, header), where):
        for name in calls_in(code):
            if name in seen:
                if depth == 0:
                    raise GateFailure(f"{where}: {name}() runs outside the message context")
                seen[name] = depth
    missing = [name for name, depth in seen.items() if depth is None]
    if missing:
        raise GateFailure(f"{where}: expected call(s) not found: {', '.join(missing)}")


def source_checks(read) -> int:
    count = 0
    # 1. ReadLine: the loop's services are all inside a bracket, and nothing
    #    but input handling is outside one.
    parse = read(PARSE)
    lines = body_of(parse, "Procedure ReadLine()")
    loop_at = next(i for i, l in enumerate(lines) if code_of(l).strip() == "Repeat")
    loop_end = max(i for i, l in enumerate(lines) if code_of(l).strip() == "ForEver")
    found = set()
    for depth, code in bracket_walk(lines[:loop_end + 1], "ReadLine"):
        for name in calls_in(code):
            if name in READLINE_SERVICES:
                if depth == 0:
                    raise GateFailure(f"ReadLine: {name}() runs outside the message context")
                found.add(name)
    missing = [n for n in READLINE_SERVICES if n not in found]
    if missing:
        raise GateFailure(f"ReadLine: services not found in the loop: {', '.join(missing)}")
    for depth, code in bracket_walk(lines[loop_at:loop_end + 1], "ReadLine loop"):
        if depth:
            continue
        for name in calls_in(code):
            if name not in READLINE_OUTSIDE:
                raise GateFailure(
                    f"ReadLine: {name}() is called in the prompt's loop outside the "
                    "message context. Only input handling may be; bracket the "
                    "service, or add it to the input list here with a reason."
                )
    # The mouse search and the first screen service after the prompt.
    head = lines[:loop_at]
    require_bracketed("\n".join(head) + "\nEndProcedure", "Procedure ReadLine()",
                      ["MouseTryAttach", "ScreenServiceTick"], "ReadLine prologue")
    count += 3
    # 2. The network poll a printing command makes to notice Ctrl-C.
    require_bracketed(read(RXBREAK), "Procedure.i OutBreakByte()", ["NetConsolePump"], "OutBreakByte")
    # 3. The one entry every pump delivers a mid-session key frame through.
    require_bracketed(read(WIFI), "Procedure.i WifiServiceEapolFrame(", ["wifi_ServiceEapol"],
                      "WifiServiceEapolFrame")
    # 4. The payload-return housekeeping, before the result lines.
    require_bracketed(read(RUNAT), "Procedure RunAt(", ["NetDhcpTick", "NetConsoleRearm"], "RunAt")
    count += 3
    # 5. A fault leaves every bracket before its first mirrored line.
    report = "\n".join(body_of(read(EXCEPTION), "Procedure HwExceptionReport()"))
    abandon = report.find("UartMessageAbandon()")
    first_print = report.find("PrintN(")
    if abandon < 0 or first_print < 0 or abandon > first_print:
        raise GateFailure("HwExceptionReport: the fault is not taken out of the message context "
                          "before it prints")
    count += 1
    # 6. Both boards' console writes decide diversion before any transport.
    uart = "\n".join(body_of(read(UART), "Procedure UartWrite(c.i)"))
    if not (0 <= uart.find("uart_MessagePut(c)") < uart.find("PokeL(")):
        raise GateFailure("uart.pi4 UartWrite: the message diversion is not ahead of the PL011 write")
    qcon = "\n".join(body_of(read(QCON), "Procedure UartWrite(c.i)"))
    if not (0 <= qcon.find("qcon_MessagePut(") < qcon.find("gQLog[gQLogLen] = c")):
        raise GateFailure("qcon_q.unoq UartWrite: the message diversion is not ahead of the transcript")
    count += 2
    # 7. Each board starts the log before its first prompt, dispatches the
    #    command, and keeps the five protocol bytes.
    for board in (PI4_BOARD, Q_BOARD):
        text = read(board)
        main = "\n".join(body_of(text, "Procedure Main()"))
        start = main.find("MessagesStart()")
        prompt = main.find('Print("pmf> ")')
        if start < 0 or prompt < 0 or start > prompt:
            raise GateFailure(f"{board}: MessagesStart() does not come before the first prompt")
        if main.count('Print("pmf> ")') != 1:
            raise GateFailure(f"{board}: the five-byte prompt is not printed exactly once")
        if not re.search(r'ElseIf WordIs\("messages"\) <> 0\s*\n\s*CmdMessages\(\)', main):
            raise GateFailure(f"{board}: `messages` is not dispatched to CmdMessages()")
        count += 3
    return count


def build(compiler: Path, work: Path, mutation: str = "") -> Path:
    staged = work / compiler.name
    shutil.copy2(compiler, staged)
    boards = ROOT / "Boards"
    if boards.is_dir():
        shutil.copytree(boards, work / "Boards")
    probe = PROBE
    if mutation:
        path, fixed, broken, _, _ = MUTATIONS[mutation]
        original = (ROOT / path).read_text(encoding="utf-8").replace("\r\n", "\n")
        if original.count(fixed) != 1:
            raise SystemExit(f"console messages mutation {mutation}: site drifted in {path}")
        mutated = work / ("mutant_" + Path(path).name)
        mutated.write_text(original.replace(fixed, broken, 1), encoding="utf-8")
        source = PROBE.read_text(encoding="utf-8")
        include = f'XIncludeFile "{path}"'
        if source.count(include) != 1:
            raise SystemExit(f"console messages mutation {mutation}: include drifted")
        probe = work / "console_messages_mutant.pi4"
        probe.write_text(source.replace(include, f'XIncludeFile "{mutated.as_posix()}"'),
                         encoding="utf-8")
    image = work / "console_messages_gate.img"
    command = [
        str(staged), "--compile", str(probe), "-t", "pi4",
        "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
        "--entry-returns", "-o", str(image), "-s",
    ]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    run = subprocess.run(command, cwd=ROOT, env=env, text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise SystemExit("console messages gate: compile failed\n" + run.stdout)
    if not image.is_file() or not image.with_suffix(image.suffix + ".sym").is_file():
        raise SystemExit("console messages gate: compiler omitted image or symbol map")
    return image


def execute(a64, image: Path) -> tuple[int, int, bytes]:
    blob = image.read_bytes()
    bss_lo, bss_hi = emitted.symbol_bounds(image.with_suffix(image.suffix + ".sym"))
    image_range = (LOAD, LOAD + len(blob))
    bss_range = (bss_lo, bss_hi)
    stack_range = (STACK - STACK_BYTES, STACK + 16)
    readable = (image_range, bss_range, stack_range)
    writable = (bss_range, stack_range)
    wire = bytearray()

    def contains(ranges, addr: int, size: int) -> bool:
        return size > 0 and any(lo <= addr and addr + size <= hi for lo, hi in ranges)

    cpu = a64.A64()
    for offset, byte in enumerate(blob):
        cpu.memory[LOAD + offset] = byte
    a64.attach_symbols(cpu, image, LOAD)
    cpu.pc = LOAD
    cpu.sp = STACK
    cpu.x[30] = LOADER_LR

    def load(addr: int, size: int) -> int:
        if addr == UART_FR:
            return 0                       # transmit FIFO never full
        cpu.align_guard(addr, size, False)
        if not contains(readable, addr, size):
            raise SystemExit(f"console messages gate: read outside image/BSS/stack at ${addr:08X}+{size}")
        return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr: int, value: int, size: int) -> None:
        if addr == UART_DR:
            wire.append(value & 0xFF)
            return
        cpu.align_guard(addr, size, True)
        if not contains(writable, addr, size):
            raise SystemExit(f"console messages gate: write outside BSS/stack at ${addr:08X}+{size}")
        for i in range(size):
            cpu.memory[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    for steps in range(STEP_LIMIT):
        if cpu.pc == LOADER_LR:
            return cpu.x[0], steps, bytes(wire)
        cpu.step()
    raise SystemExit(f"console messages gate: no return in {STEP_LIMIT} instructions")


def check_wire(wire: bytes) -> str:
    """'' when the whole stream is exactly what it must be, else why not."""
    # ... then a discarded line: "ab", Left, the tail re-sent, two erasures.
    expected_head = (b"standalone\r\n" + LINE + LINE + b"fatal\r\n"
                     + b"ab\x08b\x08 \x08\x08 \x08")
    if not wire.startswith(expected_head):
        return ("the command-line stream differs from the quiet pass typed twice:\n"
                f"  expected head {expected_head!r}\n  wire          {wire[:len(expected_head) + 40]!r}")
    listing = wire[len(expected_head):].decode("ascii", "replace")
    pattern = (
        r"messages 3 kept 4 lost 0\r\n"
        r"Messages from background services, oldest first\. These are never\r\n"
        r"printed on the command line; this is where they are read\.\r\n"
        r"  #1  at \d+ s\r\n"
        r"      The network console is now listening on:\r\n"
        r"          192\.168\.137\.1 port 5555, over the wired Ethernet\r\n"
        r"  #2  at \d+ s\r\n"
        r"      Wi-Fi: group key rekeyed\.\r\n"
        r"  #3  at \d+ s\r\n"
        r"      Wi-Fi: lease renewed, 7200 s\r\n"
    )
    if not re.fullmatch(pattern, listing):
        return f"`messages` did not print the log as its own output, and nothing after it:\n{listing!r}"
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"))
    parser.add_argument("--source-only", action="store_true",
                        help="run the source half only (no compiler or interpreter)")
    parser.add_argument("--print-wire", action="store_true",
                        help="also print the recorded wire stream of the passing run")
    args = parser.parse_args()

    def read_real(path: str) -> str:
        return (ROOT / path).read_text(encoding="utf-8").replace("\r\n", "\n")

    try:
        source_count = source_checks(read_real)
    except GateFailure as failure:
        print(f"console_messages_emitted_check: FAIL source - {failure}")
        return 1
    for name, (path, fixed, broken, why) in SOURCE_MUTATIONS.items():
        original = read_real(path)
        if original.count(fixed) != 1:
            print(f"console_messages_emitted_check: FAIL source mutant {name}: site drifted in {path}")
            return 1

        def read_mutant(p: str, _path=path, _fixed=fixed, _broken=broken) -> str:
            text = read_real(p)
            return text.replace(_fixed, _broken, 1) if p == _path else text

        try:
            source_checks(read_mutant)
        except GateFailure:
            continue
        print(f"console_messages_emitted_check: FAIL source mutant {name} was not caught ({why})")
        return 1
    if args.source_only:
        print(f"console_messages_emitted_check: SOURCE PASS - {source_count} checks, "
              f"{len(SOURCE_MUTATIONS)} mutants caught")
        return 0

    compiler = emitted.required_path(args.compiler, "PMF_COMPILER")
    interp = emitted.required_path(args.interp, "PMF_A64_INTERP")
    a64 = emitted.load_interpreter(interp)
    with tempfile.TemporaryDirectory(prefix="anvil-console-messages-") as temporary:
        image = build(compiler, Path(temporary))
        result, steps, wire = execute(a64, image)
    if result:
        print(f"console_messages_emitted_check: FAIL assertion {result} after {steps:,} A64 instructions")
        print(f"  wire so far: {wire[:200]!r}")
        return 1
    if args.print_wire:
        sys.stdout.write(wire.decode("ascii", "replace").replace("", "<BS>"))
    why = check_wire(wire)
    if why:
        print(f"console_messages_emitted_check: FAIL {why}")
        return 1
    for name, (_, _, _, expected, why_mutant) in MUTATIONS.items():
        with tempfile.TemporaryDirectory(prefix=f"anvil-console-messages-{name}-") as temporary:
            mutant = build(compiler, Path(temporary), mutation=name)
            mresult, _, mwire = execute(a64, mutant)
        if mresult != expected:
            print(f"console_messages_emitted_check: FAIL mutant {name} returned {mresult}; "
                  f"expected assertion {expected} ({why_mutant})")
            return 1
        if name in ("newline_leaks", "no_diversion") and not check_wire(mwire):
            print(f"console_messages_emitted_check: FAIL mutant {name} left the wire stream looking correct")
            return 1
    print(f"console_messages_emitted_check: PASS - wire stream exact across both passes, "
          f"{steps:,} A64 instructions; {source_count} source checks; "
          f"{len(MUTATIONS)} emitted and {len(SOURCE_MUTATIONS)} source mutants caught")
    return 0


if __name__ == "__main__":
    sys.exit(main())

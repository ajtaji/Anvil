#!/usr/bin/env python3
"""Compile and execute the production input dispatcher / line editor gate.

The real Anvil/Core/input_events.pbi and Anvil/Core/text_edit.pbi are built
and run; only the tick counter, the echo port and one board global are
scripted. Eight mutants of the real sources must each be rejected, and a
set of source checks covers the seams the emitted gate cannot see (the
contact-state vocabulary shared with the HAL, the single hardware drain,
and the network console's local-claim asymmetry).

Requires external tools; neither is copied into the product tree:
  PMF_COMPILER=<path-to-PureMetalForge.exe> PMF_A64_INTERP=<path-to-a64_interp.py> \
      python tools/input_editor_emitted_check.py
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_count  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "RaspberryPi4" / "Tests" / "input_editor_emitted_gate.pi4"

EVENTS = "Anvil/Core/input_events.pbi"
EDITOR = "Anvil/Core/text_edit.pbi"

# Each mutant restores a defect the extraction had to avoid, in the real
# source, and names the assertion that must catch it.
MUTATIONS = {
    "caret_append": (
        EDITOR,
        "  gLine[gTeCaret] = c\n",
        "  gLine[gLineLen] = c\n",
        204,
        "an insertion that ignores the caret and appends at the end",
    ),
    "esc_byte": (
        EVENTS,
        "  If c = 3\n",
        "  If c = 3 Or c = 27\n",
        50 + 1,
        "mapping the Esc BYTE onto the Esc KEY, which would discard a line "
        "every time a terminal sent an arrow key",
    ),
    "drop_oldest": (
        EVENTS,
        "  If gInCount >= #AIE_QMAX\n    InputCancelAll(#AIC_QUEUE_FULL)\n    ProcedureReturn #AIE_ERR_FULL\n  EndIf\n",
        "  If gInCount >= #AIE_QMAX\n    gInTail = (gInTail + 1) % #AIE_QMAX\n    gInCount = gInCount - 1\n  EndIf\n",
        411,
        "a saturated queue that silently overwrites its oldest event, which "
        "is as likely as not the key release that stops a repeat",
    ),
    "deliver_stale": (
        EVENTS,
        "    If PeekL(*e + #AIE_EV_GEN) <> gInGen\n",
        "    If 1 = 0\n",
        507,
        "delivering an event stamped with a focus generation that has been "
        "left behind",
    ),
    "move_rehit": (
        EVENTS,
        "    Case #AIT_MOVE\n      owner = InputCaptureOwner(contactId)\n",
        "    Case #AIT_MOVE\n      owner = InputRegionOwnerAt(x, y)\n",
        715,
        "re-deciding ownership on every MOVE, so a finger dragged off a soft "
        "key starts clicking what is underneath",
    ),
    "cancel_clears": (
        EDITOR,
        "Procedure TextEditCancelNotice(reason.i)\n  gTeCancels",
        "Procedure TextEditCancelNotice(reason.i)\n  gLineLen = 0\n  gLine[0] = 0\n  gTeCancels",
        425,
        "throwing away a half-typed command because a screen rotated",
    ),
    "capture_steal": (
        EVENTS,
        "    If gIcOwner[s] = ownerId\n      ProcedureReturn #AIE_OK\n    EndIf\n    ProcedureReturn #AIE_ERR_CAPTURED\n",
        "    gIcOwner[s] = ownerId\n    ProcedureReturn #AIE_OK\n",
        737,
        "letting a second surface take a contact away mid-gesture",
    ),
    "tab_ok": (
        EDITOR,
        "    Case #AIK_TAB\n      ProcedureReturn #AIE_ERR_NO_TAB\n",
        "    Case #AIK_TAB\n      ProcedureReturn #AIE_OK\n",
        228,
        "a Tab key that reports success from an editor with no completion",
    ),
}

# The order ReadLine services the monitor in. It is asserted rather than
# trusted because the extraction rewrote the loop around these calls, and a
# service that quietly moved would show up on a bench as a stalled protocol
# months later.
SERVICE_ORDER = [
    "ScreenServiceTick",       # the prompt and the last command's output
    "FanTick",                  # software PWM, kept ahead of idle service
    "AnvilPromptAdmitUart",    # admit PL011 data before queue work
    "InputEventsPop",          # deliver oldest already-accepted event
    "NetConsoleClaimLocal",    # ... an ACCEPTED soft keystroke is local input
    "KeyboardChar",
    "NetConsoleClaimLocal",
    "InputFeedByte",
    "NetConsoleGetc",
    "InputFeedByte",           # ... and a peer's byte claims nothing
]

SERVICE_NAMES = set(SERVICE_ORDER)

# THE PAYLOAD-ENTRY SEAM, ONE ROW PER BOARD. The file that holds RunAt, the
# call inside it that actually hands the machine over, and the files a
# cancelling wrapper is allowed to be defined in. Nothing here names the
# wrapper: the check finds any procedure in those files whose own body
# reaches InputCancelAll(#AIC_PAYLOAD), so the Pi 4's touch-keyboard
# handover and the Q's core seam are both recognised for what they do
# rather than for what they are called.
PAYLOAD_ENTRY = {
    "ArduinoQ/Board/qstubs_q.unoq": (
        "QCall(",
        ("Anvil/Core/input_events.pbi",),
    ),
    "RaspberryPi4/Board/cache.pi4": (
        "CallAddr(",
        ("RaspberryPi4/Board/banner_clock.pi4", "Anvil/Core/input_events.pbi"),
    ),
}

# Source mutants for the checks above, which no emitted assertion can reach:
# the gate image is built from the portable core alone and never links a
# board's RunAt. Each one restores a defect that WOULD have shipped - the
# Q entering a payload with the dispatcher live is exactly the state main
# was in before this seam existed - and names the board whose failure
# sentence must catch it.
SOURCE_MUTATIONS = {
    "q_no_cancel": (
        "ArduinoQ/Board/qstubs_q.unoq",
        "  InputPayloadSuspend()\n  QCall(a, 0, 0, 0, 0, 0)\n",
        "  QCall(a, 0, 0, 0, 0, 0)\n",
        "ArduinoQ/Board/qstubs_q.unoq",
        "the UNO Q entering a payload with the input dispatcher still holding "
        "queued bytes and captures",
    ),
    "q_cancel_too_late": (
        "ArduinoQ/Board/qstubs_q.unoq",
        "  InputPayloadSuspend()\n  QCall(a, 0, 0, 0, 0, 0)\n",
        "  QCall(a, 0, 0, 0, 0, 0)\n  InputPayloadSuspend()\n",
        "ArduinoQ/Board/qstubs_q.unoq",
        "a cancellation moved to the far side of the jump, where it cancels "
        "nothing that was ever at risk",
    ),
    "q_seam_hollow": (
        EVENTS,
        "Procedure InputPayloadSuspend()\n  InputCancelAll(#AIC_PAYLOAD)\nEndProcedure\n",
        "Procedure InputPayloadSuspend()\nEndProcedure\n",
        "ArduinoQ/Board/qstubs_q.unoq",
        "a core seam gutted to a no-op, which leaves every board's call site "
        "reading correctly and doing nothing",
    ),
    "pi_no_cancel": (
        "RaspberryPi4/Board/cache.pi4",
        "  TouchKeyboardPayloadSuspend()\n",
        "",
        "RaspberryPi4/Board/cache.pi4",
        "the Pi 4 entering a payload without standing its touch keyboard and "
        "its dispatcher down",
    ),
}


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def strip_comments(text: str) -> str:
    """Drop ; comments without cutting a semicolon out of a printed sentence."""
    out: list[str] = []
    for line in text.splitlines():
        quoted = False
        cut = len(line)
        for i, ch in enumerate(line):
            if ch == '"':
                quoted = not quoted
            elif ch == ";" and not quoted:
                cut = i
                break
        out.append(line[:cut])
    return "\n".join(out)


def constant(text: str, name: str) -> int:
    match = re.search(rf"^{re.escape(name)}\s*=\s*(-?\d+)", text, re.M)
    if match is None:
        raise SystemExit(f"input editor gate: {name} is not declared where it was")
    return int(match.group(1))


def procedure_body(text: str, name: str) -> str | None:
    """The body of one procedure, from its header to its EndProcedure.

    Procedures do not nest in this language, so the first EndProcedure after
    the header is the right one.
    """
    match = re.search(rf"^Procedure(?:\.\w+)?\s+{re.escape(name)}\s*\(", text, re.M)
    if match is None:
        return None
    end = text.find("EndProcedure", match.end())
    if end < 0:
        return None
    return text[match.end() : end]


def payload_cancel_checks(rd) -> list[str]:
    """Every board stands the input dispatcher down before it jumps.

    A payload takes the whole machine. Anything the dispatcher is still
    holding when it goes - a queued byte, a captured contact, a key-down
    whose release will never arrive - would be delivered to an editor that
    is not running, or executed as a command the moment the prompt came
    back. The Pi 4 has done this since the touch keyboard landed; the Q's
    RunAt could not name the reason at all until the cancellation became a
    seam of its own, so the two boards are checked by ONE rule rather than
    one board being checked and the other trusted.

    The rule is not "the file contains the call". It is that the entry
    procedure calls something that REACHES InputCancelAll(#AIC_PAYLOAD),
    and that it does so BEFORE the instruction that hands the machine over.
    A cancellation after the jump is a cancellation of the wrong machine.
    """
    fails: list[str] = []
    for board, (entry_call, wrapper_files) in sorted(PAYLOAD_ENTRY.items()):
        board_text = strip_comments(rd(board))
        body = procedure_body(board_text, "RunAt")
        if body is None:
            fails.append(
                f"{board} has no RunAt procedure, so the payload-entry seam this "
                f"check is about no longer exists where every caller expects it."
            )
            continue

        # Which names reach the cancellation. InputCancelAll itself counts
        # only when it carries THIS reason; a wrapper counts when its own
        # body carries it, which is how the Pi 4's touch-keyboard handover
        # and the Q's core seam are both recognised without naming either.
        cancelling = {"InputCancelAll(#AIC_PAYLOAD)"}
        for wrapper_file in wrapper_files:
            wrapper_text = strip_comments(rd(wrapper_file))
            for match in re.finditer(
                r"^Procedure(?:\.\w+)?\s+([A-Za-z_]\w*)\s*\(", wrapper_text, re.M
            ):
                inner = procedure_body(wrapper_text, match.group(1))
                if inner and "InputCancelAll(#AIC_PAYLOAD)" in inner:
                    cancelling.add(match.group(1) + "(")

        entry_at = body.find(entry_call)
        if entry_at < 0:
            fails.append(
                f"{board}'s RunAt no longer hands the machine over with "
                f"{entry_call.rstrip('(')}, so this check cannot tell which side "
                f"of the jump the payload cancellation is on."
            )
            continue

        found = [body.find(name) for name in cancelling if name in body]
        found = [at for at in found if at >= 0]
        if not found:
            fails.append(
                f"{board}'s RunAt enters a payload without cancelling the input "
                f"dispatcher first. A byte or a contact queued before the jump "
                f"would be delivered to a line editor that is not running, and "
                f"could execute a command the moment the payload handed the "
                f"prompt back. Call the seam that reaches "
                f"InputCancelAll(#AIC_PAYLOAD) - {EVENTS}'s InputPayloadSuspend "
                f"on a board with no touch surface."
            )
            continue
        if min(found) > entry_at:
            fails.append(
                f"{board}'s RunAt cancels the input dispatcher AFTER "
                f"{entry_call.rstrip('(')} instead of before it, which cancels "
                f"nothing that mattered: the stale events were live for the whole "
                f"time the payload owned the machine."
            )
    return fails


def source_checks(override: dict[str, str] | None = None) -> list[str]:
    """The seams the emitted gate cannot reach. Returns failure sentences."""

    def rd(rel: str) -> str:
        if override and rel in override:
            return override[rel]
        return read(rel)

    fails: list[str] = []
    hal = rd("Anvil/Hal/hal.pbi")
    events = rd(EVENTS)
    hw_touch = rd("RaspberryPi4/Board/hw_touch.pi4")
    cursor = strip_comments(rd("RaspberryPi4/Board/cursor_input.pi4"))
    parse = strip_comments(rd("Anvil/Core/parse.pbi"))

    # 1. The dispatcher re-declares the four contact states so that it can
    #    compile on a board with no touch HAL. They must stay equal to the
    #    HAL's, because the board hands them over as a straight copy.
    for hal_name, ait_name in (
        ("#HW_TOUCH_DOWN", "#AIT_DOWN"),
        ("#HW_TOUCH_MOVE", "#AIT_MOVE"),
        ("#HW_TOUCH_UP", "#AIT_UP"),
        ("#HW_TOUCH_CANCEL", "#AIT_CANCEL"),
    ):
        a = constant(hal, hal_name)
        b = constant(events, ait_name)
        if a != b:
            fails.append(
                f"{hal_name} is {a} in Anvil/Hal/hal.pbi but {ait_name} is {b} in "
                f"{EVENTS}. RaspberryPi4/Board/cursor_input.pi4 copies the state "
                f"straight across, so a finger going down would be reported as a "
                f"different gesture entirely."
            )

    # 2. The record the board copies from must still be 32 bytes with the
    #    offsets cursor_input.pi4 reads.
    if constant(hw_touch, "#HW_TOUCH_EVSZ") != 32:
        fails.append(
            "RaspberryPi4/Board/hw_touch.pi4's #HW_TOUCH_EVSZ is no longer 32, so "
            "the record cursor_input.pi4 unpacks for the dispatcher has changed "
            "shape; check the layout hal.pbi documents."
        )

    # 3. THERE IS EXACTLY ONE DRAIN OF THE HARDWARE QUEUE, and it dispatches.
    drains = cursor.count("HwTouchPoll(")
    if drains != 1:
        fails.append(
            f"RaspberryPi4/Board/cursor_input.pi4 calls HwTouchPoll {drains} times; "
            f"there must be exactly one drain of the controller's ring, because two "
            f"consumers polling one queue is a coin toss over which of them sees "
            f"each event."
        )
    if "InputTouchDispatch(" not in cursor:
        fails.append(
            "RaspberryPi4/Board/cursor_input.pi4 drains the touch ring without "
            "handing the events to InputTouchDispatch, so every contact is thrown "
            "away again and nothing else can ever receive one."
        )
    if "InputCaptureReconcileEnd(" not in cursor:
        fails.append(
            "RaspberryPi4/Board/cursor_input.pi4 no longer reconciles captures "
            "against the contacts the controller reports now, so a release lost to "
            "a flush or a full ring would leave a finger held down forever."
        )
    if "InputCancelAll(#AIC_TOUCH_LOST)" not in cursor:
        fails.append(
            "RaspberryPi4/Board/cursor_input.pi4 stands the touch surface down "
            "without cancelling held contacts, so a modifier held when the ribbon "
            "was pulled would stay latched for the rest of the session."
        )

    # 4. THE NETWORK CONSOLE'S LOCAL CLAIM. Three claims and no more: the
    #    UART read, the USB keyboard read, and an ACCEPTED soft keystroke.
    #    A byte from the peer must not claim, and neither must drawing a
    #    keyboard.
    body = parse[parse.index("Procedure ReadLine()") : parse.index("EndProcedure", parse.index("Procedure ReadLine()"))]
    admission_source = procedure_body(parse, "AnvilPromptAdmitUart") or ""
    claims = body.count("NetConsoleClaimLocal()") + admission_source.count("NetConsoleClaimLocal()")
    if claims != 3:
        fails.append(
            f"Anvil/Core/parse.pbi's ReadLine claims local console ownership "
            f"{claims} times; it must be exactly three - the serial read, the USB "
            f"keyboard read, and an accepted soft keystroke - so that a byte from "
            f"the remote peer never displaces its own session."
        )
    network = body[body.index("NetConsoleGetc()") :]
    if "InputFeedByte(#AIS_NETWORK" not in network:
        fails.append(
            "Anvil/Core/parse.pbi no longer tags the network console's bytes as "
            "network input, so the console's ownership rules cannot tell a remote "
            "byte from a local keystroke."
        )
    if "NetConsoleClaimLocal()" in network:
        fails.append(
            "Anvil/Core/parse.pbi claims LOCAL console ownership on a byte that "
            "came from the network peer, which would end the peer's own session on "
            "its own keystroke."
        )
    if "#AIS_TOUCH_KEYBOARD" not in body:
        fails.append(
            "Anvil/Core/parse.pbi never recognises a soft keystroke as local "
            "input, so typing on the touch keyboard would leave a stale remote "
            "session owning the console."
        )

    # UART admission is bounded by free queue capacity, precedes event
    # delivery, and never invokes screen/render code on the serial path.
    admit = procedure_body(parse, "AnvilPromptAdmitUart")
    if admit is None:
        fails.append("AnvilPromptAdmitUart is missing from the prompt scheduler")
    else:
        guard = admit.find("InputEventsQueued() >= #AIE_QMAX")
        read_pos = admit.find("UartRead()")
        if guard < 0 or read_pos < 0 or guard > read_pos:
            fails.append("UART admission can consume a byte before proving event-queue capacity")
        if "InputFeedByte(#AIS_PHYSICAL, c)" not in admit:
            fails.append("UART admission no longer routes accepted bytes through InputFeedByte")
        if any(name in admit for name in ("ScreenServiceTick(", "Pi3Screen", "HwCon")):
            fails.append("UART admission calls display/render work synchronously")
    loop = body[body.index("Repeat") : body.rindex("ForEver")]
    if loop.find("AnvilPromptAdmitUart()") < 0 or loop.find("InputEventsPop(") < 0 or loop.find("AnvilPromptAdmitUart()") > loop.find("InputEventsPop("):
        fails.append("ReadLine must admit ready UART data before delivering queued events")

    # 5. The old inline editor is gone, not merely bypassed.
    for ghost in ("gLine[n] = c", "gLine[n] = 0", "gLineLen = n"):
        if ghost in parse:
            fails.append(
                f"Anvil/Core/parse.pbi still contains the old inline line editor "
                f"({ghost!r}), so there are two editors and they will disagree the "
                f"first time one of them is changed."
            )

    # 6. The service order.
    calls = re.findall(r"\b([A-Z][A-Za-z0-9_]*)\s*\(", body)
    seen = [c for c in calls if c in SERVICE_NAMES]
    if seen != SERVICE_ORDER:
        fails.append(
            "Anvil/Core/parse.pbi's ReadLine no longer services the monitor in the "
            "order it did before the editor was extracted.\n"
            f"      expected: {' '.join(SERVICE_ORDER)}\n"
            f"      found:    {' '.join(seen)}"
        )

    # 7. Both boards include the new seam ahead of the reader that sits on it.
    for board in ("RaspberryPi4/Board/board.pi4", "ArduinoQ/Board/board.unoq"):
        text = rd(board)
        try:
            ev = text.index(f'XIncludeFile "{EVENTS}"')
            ed = text.index(f'XIncludeFile "{EDITOR}"')
            pa = text.index('XIncludeFile "Anvil/Core/parse.pbi"')
        except ValueError:
            fails.append(
                f"{board} does not include the input seam and the line editor; the "
                f"line reader would have nothing to stand on."
            )
            continue
        if not ev < ed < pa:
            fails.append(
                f"{board} includes the input seam, the editor and the line reader "
                f"out of order; each one declares what the next uses."
            )

    # 8. Both boards cancel the dispatcher with #AIC_PAYLOAD before they jump.
    fails.extend(payload_cancel_checks(rd))
    return fails


def build(compiler: Path, work: Path, mutation: str = "") -> Path:
    staged = work / compiler.name
    shutil.copy2(compiler, staged)
    boards = ROOT / "Boards"
    if boards.is_dir():
        shutil.copytree(boards, work / "Boards")
    image = work / "input_editor_gate.img"
    probe = work / PROBE.name
    probe.write_text(PROBE.read_text(encoding="utf-8"), encoding="utf-8")
    if mutation:
        rel, fixed, broken, _, _ = MUTATIONS[mutation]
        text = read(rel)
        if text.count(fixed) != 1:
            raise SystemExit(
                f"input editor mutation: the {mutation} site in {rel} has drifted; "
                f"the mutant would prove nothing."
            )
        mutated = work / (Path(rel).stem + "_" + mutation + ".pbi")
        mutated.write_text(text.replace(fixed, broken, 1), encoding="utf-8")
        source = PROBE.read_text(encoding="utf-8")
        include = f'XIncludeFile "{rel}"'
        if source.count(include) != 1:
            raise SystemExit(f"input editor mutation: the gate's {rel} include has drifted")
        probe = work / f"input_editor_{mutation}.pi4"
        probe.write_text(
            source.replace(include, f'XIncludeFile "{mutated.as_posix()}"'),
            encoding="utf-8",
        )
    probe_text = probe.read_text(encoding="utf-8")
    parse_source = read("Anvil/Core/parse.pbi")
    globals_marker = ";@@PROMPT_SCHEDULER_GLOBALS@@"
    idle_marker = ";@@PROMPT_IDLE_PROC@@"
    if probe_text.count(globals_marker) != 1 or probe_text.count(idle_marker) != 1:
        raise SystemExit("input editor gate: prompt-idle fixture marker missing/duplicated")
    scheduler_globals = "\n".join(
        line for line in parse_source.splitlines()
        if line.startswith("Global anvil_prompt")
    )
    probe_text = probe_text.replace(globals_marker, scheduler_globals)
    marker = ";@@UART_ADMISSION_PROC@@"
    if probe_text.count(marker) != 1:
        raise SystemExit("input editor gate: UART-admission fixture marker missing/duplicated")
    admission = procedure_body(parse_source, "AnvilPromptAdmitUart")
    if admission is None:
        raise SystemExit("input editor gate: production UART-admission procedure is missing")
    # procedure_body returns the text following the opening parenthesis,
    # including the closing `)`; reuse it verbatim to preserve the signature.
    admission = "Procedure.i AnvilPromptAdmitUart(" + admission + "\nEndProcedure"
    probe_text = probe_text.replace(marker, admission)
    account = procedure_body(parse_source, "AnvilSchedulerAccount")
    idle = procedure_body(parse_source, "AnvilSchedulerIdleIfSafe")
    cpu_whole = procedure_body(parse_source, "AnvilCpuUsagePercent")
    cpu_hundredths = procedure_body(parse_source, "AnvilCpuUsageHundredths")
    if account is None or idle is None or cpu_whole is None or cpu_hundredths is None:
        raise SystemExit("input editor gate: production prompt idle accounting/guard is missing")
    idle_proc = "Procedure.i AnvilCpuUsagePercent(" + cpu_whole + "\nEndProcedure\n\n"
    idle_proc += "Procedure.i AnvilCpuUsageHundredths(" + cpu_hundredths + "\nEndProcedure\n\n"
    idle_proc += "Procedure AnvilSchedulerAccount(" + account + "\nEndProcedure\n\n"
    idle_proc += "Procedure AnvilSchedulerIdleIfSafe(" + idle + "\nEndProcedure"
    idle_proc, replaced = re.subn(
        r"Asm\s+wfe\s+EndAsm", "GateWfe()", idle_proc, count=1,
        flags=re.IGNORECASE,
    )
    if replaced != 1:
        raise SystemExit("input editor gate: production idle WFE site changed unexpectedly")
    probe.write_text(probe_text.replace(idle_marker, idle_proc), encoding="utf-8")
    command = [
        str(staged), "--compile",
        str(probe),
        "-t", "pi4",
        "--load-addr", hex(emitted.LOAD),
        "--stack-addr", hex(emitted.STACK),
        "--entry-returns",
        "-o", str(image),
        "-s",
    ]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    run = subprocess.run(
        command, cwd=ROOT, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise SystemExit("input editor gate: compile failed\n" + run.stdout)
    if not image.is_file() or not image.with_suffix(image.suffix + ".sym").is_file():
        raise SystemExit("input editor gate: compiler omitted image or symbol map")
    # EVERY COMPILE IN tools/ ASKS THE COUNTER. This one builds a fixture,
    # so record_build() answers "not a board file" and nothing moves - but the
    # decision about what is a build of the monitor belongs to one module, not
    # to each gate's own reading of its fixture. The day this gate compiles a
    # board file instead, the count follows it without anyone remembering to.
    build_count.record_build(probe, "pi4", image,
                             by="tools/input_editor_emitted_check.py", compiler=staged)
    return image


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"))
    args = parser.parse_args()
    compiler = emitted.required_path(args.compiler, "PMF_COMPILER")
    interp = emitted.required_path(args.interp, "PMF_A64_INTERP")

    fails = source_checks()
    if fails:
        for sentence in fails:
            print(f"input_editor_emitted_check: FAIL - {sentence}")
        return 1

    # THE SOURCE CHECKS ARE MUTANT-TESTED TOO. A source check that reads a
    # file and finds what it hoped for proves nothing until something has
    # been shown to make it fail; the include-order rule above sat green for
    # a day while the Q's RunAt had no cancellation in it at all, because
    # nothing asked that question.
    for mutation, (rel, fixed, broken, board, why) in SOURCE_MUTATIONS.items():
        text = read(rel)
        if text.count(fixed) != 1:
            print(
                f"input_editor_emitted_check: FAIL - the {mutation} site in {rel} "
                f"has drifted, so the mutant would prove nothing."
            )
            return 1
        caught = source_checks({rel: text.replace(fixed, broken, 1)})
        if not any(sentence.startswith(board) for sentence in caught):
            print(
                f"input_editor_emitted_check: FAIL - the {mutation} mutant ({why}) "
                f"was not caught by a {board} failure, so that check is not doing "
                f"its job."
            )
            for sentence in caught:
                print(f"    it reported instead: {sentence}")
            return 1

    a64 = emitted.load_interpreter(interp)
    with tempfile.TemporaryDirectory(prefix="anvil-input-editor-") as temporary:
        image = build(compiler, Path(temporary))
        result, steps = emitted.execute(a64, image)
    if result:
        print(
            f"input_editor_emitted_check: FAIL assertion {result} after "
            f"{steps:,} A64 instructions"
        )
        return 1

    for mutation in MUTATIONS:
        _, _, _, expected, why = MUTATIONS[mutation]
        with tempfile.TemporaryDirectory(prefix=f"anvil-input-{mutation}-") as temporary:
            mutant = build(compiler, Path(temporary), mutation=mutation)
            got, mutant_steps = emitted.execute(a64, mutant)
        if got != expected:
            print(
                f"input_editor_emitted_check: FAIL - the {mutation} mutant "
                f"({why}) returned assertion {got}; assertion {expected} was "
                f"expected to catch it, so that check is not doing its job."
            )
            return 1

    print(
        f"input_editor_emitted_check: PASS - 163 numbered assertions in "
        f"{steps:,} A64 instructions"
    )
    print(
        "  nine console scenarios, each run through the pre-change editor and "
        "then through the real code twice - once as serial bytes and once as "
        "network bytes - and compared on buffer, length, NUL, truncation, "
        "Ctrl-C and the whole echo byte sequence (18 runs, 7 comparisons each)"
    )
    print(
        "  caret, bounds, queue saturation, focus generation, key-release "
        "delivery, capture and one-drain dispatch"
    )
    print(
        f"  source checks: {len(SERVICE_ORDER)} service calls in order, the four "
        f"contact states shared with the HAL, one hardware drain, the console's "
        f"local-claim asymmetry, no surviving inline editor, include order on "
        f"both boards, and #AIC_PAYLOAD cancellation before the jump in both "
        f"boards' RunAt"
    )
    print(f"  {len(MUTATIONS)} mutants of the real sources rejected, each by its own assertion")
    print(
        f"  {len(SOURCE_MUTATIONS)} source mutants rejected by the source checks: "
        f"each board's payload entry losing its cancellation, the Q's moved to "
        f"the far side of the jump, and the core seam gutted to a no-op"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

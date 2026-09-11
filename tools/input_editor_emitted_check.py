#!/usr/bin/env python3
"""Compile and execute the production input dispatcher / line editor gate.

The real Anvil/Core/input_events.pbi and Anvil/Core/text_edit.pbi are built
and run; only the tick counter, the echo port and one board global are
scripted. Eight mutants of the real sources must each be rejected, and a
set of source checks covers the seams the emitted gate cannot see (the
contact-state vocabulary shared with the HAL, the single hardware drain,
and the network console's local-claim asymmetry).

Requires external tools; neither is copied into the product tree:
  PMFC=<path-to-pmfc> PMF_A64_INTERP=<path-to-a64_interp.py> \
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
    "InputEventsPop",          # the queue, before any new byte is taken in
    "NetConsoleClaimLocal",    # ... an ACCEPTED soft keystroke is local input
    "UartReadReady",
    "UartRead",
    "NetConsoleClaimLocal",
    "InputFeedByte",
    "KeyboardChar",
    "NetConsoleClaimLocal",
    "InputFeedByte",
    "NetConsoleRearm",
    "NetConsolePump",
    "NetConsoleLlTick",
    "TcpTick",
    "NetConsoleGetc",
    "InputFeedByte",           # ... and a peer's byte claims nothing
    "MouseTick",
    "TouchTick",
    "ScreenServiceTick",
    "WifiLinkTick",
    "NetDhcpTick",
    "NtpServiceTick",
    "FanTick",
]

SERVICE_NAMES = set(SERVICE_ORDER)


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


def source_checks() -> list[str]:
    """The seams the emitted gate cannot reach. Returns failure sentences."""
    fails: list[str] = []
    hal = read("Anvil/Hal/hal.pbi")
    events = read(EVENTS)
    hw_touch = read("RaspberryPi4/Board/hw_touch.pi4")
    cursor = strip_comments(read("RaspberryPi4/Board/cursor_input.pi4"))
    parse = strip_comments(read("Anvil/Core/parse.pbi"))

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
    claims = body.count("NetConsoleClaimLocal()")
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
        text = read(board)
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
    return fails


def build(pmfc: Path, work: Path, mutation: str = "") -> Path:
    staged = work / pmfc.name
    shutil.copy2(pmfc, staged)
    boards = ROOT / "Boards"
    if boards.is_dir():
        shutil.copytree(boards, work / "Boards")
    image = work / "input_editor_gate.img"
    probe = PROBE
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
    command = [
        str(staged),
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
    return image


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pmfc", default=os.environ.get("PMFC"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"))
    args = parser.parse_args()
    pmfc = emitted.required_path(args.pmfc, "PMFC")
    interp = emitted.required_path(args.interp, "PMF_A64_INTERP")

    fails = source_checks()
    if fails:
        for sentence in fails:
            print(f"input_editor_emitted_check: FAIL - {sentence}")
        return 1

    a64 = emitted.load_interpreter(interp)
    with tempfile.TemporaryDirectory(prefix="anvil-input-editor-") as temporary:
        image = build(pmfc, Path(temporary))
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
            mutant = build(pmfc, Path(temporary), mutation=mutation)
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
        f"both boards"
    )
    print(f"  {len(MUTATIONS)} mutants of the real sources rejected, each by its own assertion")
    return 0


if __name__ == "__main__":
    sys.exit(main())

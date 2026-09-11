#!/usr/bin/env python3
"""touch_keyboard_integration_emitted_check.py - the touch keyboard JOIN,
compiled with the real compiler and executed on the A64 interpreter.

      PMFC=<path-to-pmfc.exe> PMF_A64_INTERP=<path-to-a64_interp.py> \
          py -3.12 tools/touch_keyboard_integration_emitted_check.py

WHAT THIS PROVES

  Four production files are compiled UNCHANGED and run against each other:
  the input dispatcher, the shared line editor, the touch keyboard model
  and the keyboard's view (through the real console core).  So is the
  board adapter that joins them: the two fenced sections of
  RaspberryPi4/Board/banner_clock.pi4 are LIFTED VERBATIM out of the
  shipped file and compiled into the gate.  Nothing is transcribed.

  A finger is put on the glass by calling InputTouchDispatch with
  coordinates - exactly what the board's one drain of the hardware ring
  does with the fields of a HAL record - and from there every decision is
  the production one: who owns the contact, which key it is on, what the
  key means, which event that becomes, and what the editor does with it.

WHAT IT CANNOT PROVE

  * No panel, no controller and no pixels.  Where a key is on the glass
    is the view gate's subject and the bench's.
  * TouchKeyboardScreenShow/Hide are stubbed, because the real ones read
    the display and the panel's density over I2C.  The source checks
    below require the real ones to do what the stubs do.
  * The editor's apply loop lives inside ReadLine, which cannot be
    compiled without the whole monitor.  The source checks require
    ReadLine's mapping to be exactly the gate's.
  * Latency and frame budget are hardware measurements.  None is claimed.

THE MUTANTS

  Each one restores a plausible wrong version of a single line of the
  LIFTED integration and requires the gate to go red at a named
  assertion.  A join that still passes with the event pump removed is a
  join nothing was testing.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile


HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent

GATE = ROOT / "RaspberryPi4" / "Tests" / "touch_keyboard_integration_emitted_gate.pi4"
ADAPTER = ROOT / "RaspberryPi4" / "Board" / "banner_clock.pi4"
PARSE = ROOT / "Anvil" / "Core" / "parse.pbi"
BOARD = ROOT / "RaspberryPi4" / "Board" / "board.pi4"
CACHE = ROOT / "RaspberryPi4" / "Board" / "cache.pi4"
CURSOR = ROOT / "RaspberryPi4" / "Board" / "cursor_input.pi4"

STATE_BEGIN = "; ANVIL-TOUCH-KEYBOARD-STATE-BEGIN"
STATE_END = "; ANVIL-TOUCH-KEYBOARD-STATE-END"
JOIN_BEGIN = "; ANVIL-TOUCH-KEYBOARD-INTEGRATION-BEGIN"
JOIN_END = "; ANVIL-TOUCH-KEYBOARD-INTEGRATION-END"

LIFT_NAME = "_touch_keyboard_integration_lift.pbi"

LOAD = 0x00400000
STACK = 0x03000000
LOADER_LR = 0xDEAD0000
STEP_LIMIT = 60_000_000
MMIO = 0xFC000000

# name -> (site in the lifted integration, the wrong version, expected assertion)
MUTATIONS = {
    # The clock is injected once a pass and everything in the model is
    # arithmetic on it. Without it the keyboard never finishes opening.
    "clock_never_advances": (
        "  TouchKeyboardTick(millis())\n",
        "  TouchKeyboardTick(0)\n",
        26,
    ),
    # The chevron is asked FIRST, so the contact is never armed and the
    # editor never sees a keystroke. Routing it to the model instead hides
    # on the release rather than on the press.
    "chevron_not_asked_first": (
        "  If st = #AIT_DOWN\n    If TouchKeyboardHideHit(x, y) <> 0\n      TouchKeyboardHide()\n      ProcedureReturn\n    EndIf\n  EndIf\n",
        "",
        51,
    ),
    # A tap on the editable prompt line is the design's one auto-open
    # trigger. Asking only about the button leaves the line dead.
    "prompt_tap_ignored": (
        "    If TouchKeyboardButtonHit(x, y) <> 0 Or TouchKeyboardPromptHit(x, y) <> 0\n",
        "    If TouchKeyboardButtonHit(x, y) <> 0\n",
        21,
    ),
    # The model's ring is drained but nothing is pushed, so a key is
    # pressed and nothing is typed.
    "events_never_pumped": (
        "    If rc = #AIE_OK\n      rc = InputEventsPush(@ev[0])\n    EndIf\n",
        "",
        34,
    ),
    # A layout generation change must release every contact before the new
    # hit geometry is installed.
    "generation_change_ignored": (
        "  If TouchKeyboardContactCount() > 0\n    TouchKeyboardCancelAll(#TK_CANCEL_VIEW)\n  EndIf\n",
        "",
        74,
    ),
    # ... and the dispatcher's own captures with them.
    "generation_change_keeps_captures": (
        "  If InputCaptureCount() > 0\n    InputCancelAll(#AIC_LAYOUT_CHANGE)\n  EndIf\n",
        "",
        75,
    ),
    # The payload handover must clear the dispatcher, not only the model.
    "payload_leaves_the_dispatcher_armed": (
        "  InputCancelAll(#AIC_PAYLOAD)\n",
        "",
        85,
    ),
    # The band's rectangle has to be installed for the dispatcher to route
    # anything to this layer at all.
    "band_region_never_installed": (
        "    InputRegionSet(#AIO_KEYBOARD, TouchKeyboardBandX(), TouchKeyboardBandY(), TouchKeyboardBandW(), TouchKeyboardBandH())\n",
        "    InputRegionClear(#AIO_KEYBOARD)\n",
        25,
    ),
    # And the idle one, or the prompt line belongs to nobody.
    "idle_region_never_installed": (
        "    InputRegionSet(#AIO_KEYBOARD, TouchKeyboardIdleX(), TouchKeyboardIdleY(), TouchKeyboardIdleW(), TouchKeyboardIdleH())\n",
        "    InputRegionClear(#AIO_KEYBOARD)\n",
        10,
    ),
    # The handover has three halves besides the dispatcher's queue, and
    # every one of them is load bearing: the model's contacts and
    # modifiers, the band on the glass, and this layer's rectangle.
    "payload_leaves_the_model_armed": (
        "  TouchKeyboardCancelAll(#TK_CANCEL_CLIENT)\n",
        "",
        83,
    ),
    "payload_leaves_the_band_on_the_glass": (
        "  If TouchKeyboardViewVisible() <> 0\n    TouchKeyboardScreenHide()\n  EndIf\n",
        "",
        87,
    ),
    "payload_leaves_the_region_installed": (
        "  TouchKeyboardRegionInstall(0)\n",
        "",
        88,
    ),
}


def fail(message: str) -> None:
    raise SystemExit("touch keyboard integration gate: " + message)


def between(text: str, begin: str, end: str, what: str) -> str:
    if text.count(begin) != 1 or text.count(end) != 1:
        fail(
            f"{what} is not fenced exactly once in {ADAPTER.name}; the gate "
            "refuses to test a copy of the integration, so the fence comments "
            f"{begin} and {end} must both be present exactly once"
        )
    a = text.index(begin) + len(begin)
    b = text.index(end)
    if b <= a:
        fail(f"{what}: the fence comments are in the wrong order in {ADAPTER.name}")
    return text[a:b]


def lift() -> str:
    text = ADAPTER.read_text(encoding="utf-8")
    state = between(text, STATE_BEGIN, STATE_END, "the layer's state")
    join = between(text, JOIN_BEGIN, JOIN_END, "the integration")
    return (
        "; ======================================================================\n"
        ";  LIFTED VERBATIM from RaspberryPi4/Board/banner_clock.pi4 between its\n"
        ";  ANVIL-TOUCH-KEYBOARD fence comments, by\n"
        ";  tools/touch_keyboard_integration_emitted_check.py. Do not edit this\n"
        ";  file and do not commit it: it is generated for one compile and\n"
        ";  thrown away. The gate executes the shipped text.\n"
        "; ======================================================================\n"
        + state + "\n" + join
    )


# ---------------------------------------------------------------- source
class Checks:
    def __init__(self) -> None:
        self.count = 0
        self.failures: list[str] = []

    def yes(self, condition: bool, message: str) -> None:
        self.count += 1
        if not condition:
            self.failures.append(message)


def uncommented(source: str) -> str:
    """The code, with whole-line comments removed.

    A source check that counts calls has to count CALLS.  This file's own
    prose quotes the line it is talking about more than once, and a gate
    that went red because a comment mentioned a procedure would be a gate
    nobody could keep green.
    """
    return "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith(";")
    )


def procedure(source: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^Procedure(?:\.\w+)?\s+{re.escape(name)}\s*\(.*?^EndProcedure", source
    )
    if not match:
        fail(f"no procedure named {name} was found where one was expected")
    return match.group(0)


def source_checks(c: Checks) -> None:
    parse = PARSE.read_text(encoding="utf-8")
    board = BOARD.read_text(encoding="utf-8")
    cache = CACHE.read_text(encoding="utf-8")
    cursor = CURSOR.read_text(encoding="utf-8")
    gate = GATE.read_text(encoding="utf-8")

    read_line = procedure(parse, "ReadLine")
    apply_loop = procedure(gate, "GateApply")

    # THE EDITOR MAPPING. The gate reproduces ReadLine's Select because
    # ReadLine cannot be compiled without the whole monitor; this is what
    # stops the reproduction drifting into a different editor.
    for kind, entry in (
        ("#AIE_TEXT", "TextEditInsert("),
        ("#AIE_KEY_DOWN", "TextEditKey("),
        ("#AIE_KEY_UP", "TextEditKeyRelease("),
        ("#AIE_CANCEL", "TextEditCancelNotice("),
    ):
        in_read = read_line.find(f"Case {kind}")
        in_gate = apply_loop.find(f"Case {kind}")
        c.yes(in_read >= 0, f"ReadLine no longer handles {kind}")
        c.yes(in_gate >= 0, f"the gate's apply loop no longer handles {kind}")
        if in_read < 0 or in_gate < 0:
            continue
        c.yes(
            entry in read_line[in_read:in_read + 400],
            f"ReadLine no longer sends {kind} to {entry.rstrip('(')}",
        )
        c.yes(
            entry in apply_loop[in_gate:in_gate + 400],
            f"the gate's apply loop no longer sends {kind} to {entry.rstrip('(')}",
        )

    # A SOFT KEYSTROKE IS LOCAL INPUT, and a byte from the peer is not.
    c.yes(
        "If src = #AIS_TOUCH_KEYBOARD" in read_line and "NetConsoleClaimLocal()" in read_line,
        "ReadLine no longer claims the console for an applied soft keystroke",
    )

    # THE SERVICE RUNS AT THE PROMPT, AFTER THE ONE DRAIN, AND NOWHERE ELSE.
    c.yes("TouchTick()" in read_line, "ReadLine no longer services touch")
    c.yes(
        read_line.find("TouchTick()") < read_line.find("TouchKeyboardServiceTick()"),
        "the keyboard's service must run after the one drain of the hardware ring",
    )
    c.yes(
        "CompilerIf #CAP_TOUCH = 1" in read_line,
        "the keyboard service call must be compiled out on a board with no touch surface",
    )
    calls = len(re.findall(r"\bTouchKeyboardServiceTick\s*\(", parse))
    c.yes(calls == 1, f"parse.pbi calls the keyboard service {calls} times; it must be once")

    # ONE DRAIN OF THE HARDWARE, AND ONE DRAIN OF THE KEYBOARD'S LANE.
    c.yes(
        len(re.findall(r"\bHwTouchPoll\s*\(", uncommented(cursor))) == 1,
        "cursor_input.pi4 must hold the ONE drain of the hardware touch ring",
    )
    adapter = ADAPTER.read_text(encoding="utf-8")
    join = between(adapter, JOIN_BEGIN, JOIN_END, "the integration")
    c.yes(
        len(re.findall(r"InputTouchPop\(#AIO_KEYBOARD", adapter)) == 1
        and "InputTouchPop(#AIO_KEYBOARD" in join,
        "the keyboard's routed lane must be drained exactly once, inside the fenced integration",
    )

    # THE INCLUDE ORDER. The view asks the model for its keys, so the model
    # has to be in the build and it has to precede the file that includes
    # the view.
    model_at = board.find('XIncludeFile "Anvil/Core/touch_keyboard.pbi"')
    console_at = board.find('XIncludeFile "RaspberryPi4/Board/console.pi4"')
    c.yes(model_at >= 0, "board.pi4 does not include the touch keyboard model")
    c.yes(console_at >= 0, "board.pi4 does not include the console core")
    c.yes(
        0 <= model_at < console_at,
        "board.pi4 must include the touch keyboard model before the console core, "
        "which is what includes the keyboard's view",
    )

    # THE PAYLOAD HANDOVER, ON BOTH SIDES OF THE JUMP.
    run_at = procedure(cache, "RunAt")
    suspend = run_at.find("TouchKeyboardPayloadSuspend()")
    call = run_at.find("CallAddr()")
    resume = run_at.find("TouchKeyboardPayloadResume()")
    c.yes(suspend >= 0, "RunAt does not put the touch keyboard away before the jump")
    c.yes(resume >= 0, "RunAt does not restore the touch keyboard after the payload returns")
    c.yes(0 <= suspend < call, "the keyboard must be put away BEFORE control leaves the monitor")
    c.yes(call < resume, "the keyboard must be restored only after the payload returns")
    c.yes(
        run_at.find("EthPayloadReclaim()") < resume,
        "the keyboard must be restored only after the untrusted bus master is reclaimed",
    )

    # THE STUBBED SHOW AND HIDE. The gate stands in for these two; what it
    # stands in for has to be what they do.
    show = procedure(adapter, "TouchKeyboardScreenShow")
    hide = procedure(adapter, "TouchKeyboardScreenHide")
    for needle in ("TouchKeyboardLayout(", "TouchKeyboardViewSetVisible(1)", "ConSetViewRows("):
        c.yes(needle in show, f"the real TouchKeyboardScreenShow no longer calls {needle}")
    for needle in ("TouchKeyboardViewSetVisible(0)", "ConViewRelease()"):
        c.yes(needle in hide, f"the real TouchKeyboardScreenHide no longer calls {needle}")

    # THE LAYER TURNS ITSELF ON ONLY WHERE THERE IS A FINGER TO REACH IT.
    attach = procedure(adapter, "TouchKeyboardScreenAttach")
    c.yes(
        "gTkbEnabled = 1" in attach and "HwTouchReady() <> 0" in attach,
        "the keyboard layer must enable itself at attach, and only on a board that can be touched",
    )


# ---------------------------------------------------------------- build
def locate(env_name: str, explicit: str | None, fallbacks) -> pathlib.Path:
    choices = []
    if explicit:
        choices.append(pathlib.Path(explicit))
    if os.environ.get(env_name):
        choices.append(pathlib.Path(os.environ[env_name]))
    choices.extend(fallbacks)
    for path in choices:
        if path.is_file():
            return path.resolve()
    fail(f"{env_name} was not found; set it or pass its option")


def load_interpreter(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("anvil_tki_a64_interp", path)
    if spec is None or spec.loader is None:
        fail(f"cannot load the interpreter: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SOURCES = (
    "Anvil/Core/state.pbi",
    "Anvil/Core/input_events.pbi",
    "Anvil/Core/text_edit.pbi",
    "Anvil/Core/touch_keyboard.pbi",
    "Anvil/Graphics/touch_keyboard_view.pbi",
    # console.pi4 includes the bounded boot transcript beside the drain that
    # feeds it, so the staged tree needs it to resolve. It is pure storage
    # and nothing in this gate exercises it.
    "Anvil/Core/boot_transcript.pbi",
    "RaspberryPi4/Board/console.pi4",
)


def stage(work: pathlib.Path, lifted: str) -> pathlib.Path:
    for rel in SOURCES:
        dst = work / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dst)
    (work / "RaspberryPi4" / "Tests").mkdir(parents=True, exist_ok=True)
    shutil.copy2(GATE, work / "RaspberryPi4" / "Tests" / GATE.name)
    (work / "RaspberryPi4" / "Tests" / LIFT_NAME).write_text(lifted, encoding="utf-8")
    src = ROOT / "RaspberryPi4" / "Intrinsics"
    if src.is_dir():
        shutil.copytree(src, work / "RaspberryPi4" / "Intrinsics", dirs_exist_ok=True)
    if (ROOT / "Boards").is_dir():
        shutil.copytree(ROOT / "Boards", work / "Boards", dirs_exist_ok=True)
    if (ROOT / "keywords.def").is_file():
        shutil.copy2(ROOT / "keywords.def", work / "keywords.def")
    return work / "RaspberryPi4" / "Tests" / GATE.name


def build(compiler: pathlib.Path, work: pathlib.Path, source: pathlib.Path) -> pathlib.Path:
    image = work / "touch_keyboard_integration_gate.img"
    command = [
        str(compiler),
        source.relative_to(work).as_posix(),
        "-t", "pi4",
        "--load-addr", hex(LOAD),
        "--stack-addr", hex(STACK),
        "--entry-returns",
        "-o", str(image),
        "-s",
    ]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(work)
    run = subprocess.run(
        command, cwd=work, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise SystemExit("touch keyboard integration gate: compile failed\n" + run.stdout)
    return image


def execute(a64, image: pathlib.Path):
    cpu = a64.A64()
    for i, byte in enumerate(image.read_bytes()):
        cpu.memory[LOAD + i] = byte
    a64.attach_symbols(cpu, image, LOAD)
    cpu.pc = LOAD
    cpu.sp = STACK
    cpu.x[30] = LOADER_LR

    def guard(addr: int, write: bool) -> None:
        if addr >= MMIO:
            kind = "write" if write else "read"
            fail(
                f"unexpected MMIO {kind} at ${addr:08X} - the join is supposed "
                "to touch no hardware at all"
            )

    def load(addr: int, size: int) -> int:
        cpu.align_guard(addr, size, False)
        guard(addr, False)
        return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr: int, value: int, size: int) -> None:
        cpu.align_guard(addr, size, True)
        guard(addr, True)
        for i in range(size):
            cpu.memory[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    for steps in range(STEP_LIMIT):
        if cpu.pc == LOADER_LR:
            return cpu.x[0] & 0xFFFFFFFF, steps
        cpu.step()
    fail(f"the probe did not return in {STEP_LIMIT} instructions")


def run_once(a64, compiler, lifted: str):
    with tempfile.TemporaryDirectory(prefix="anvil-tki-") as td:
        work = pathlib.Path(td)
        source = stage(work, lifted)
        image = build(compiler, work, source)
        return execute(a64, image)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pmfc", default=os.environ.get("PMFC"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"))
    args = parser.parse_args()
    compiler = locate("PMFC", args.pmfc, [ROOT / "pmfc.exe", ROOT / "pmfc"])
    a64 = load_interpreter(locate("PMF_A64_INTERP", args.interp,
                                  [ROOT / "tools" / "a64" / "a64_interp.py"]))

    c = Checks()
    source_checks(c)
    if c.failures:
        print(f"touch_keyboard_integration_emitted_check: FAIL ({c.count} source checks)")
        for failure in c.failures:
            print("  " + failure)
        return 1

    lifted = lift()
    result, steps = run_once(a64, compiler, lifted)
    if result:
        print(
            f"touch_keyboard_integration_emitted_check: FAIL assertion {result} "
            f"after {steps:,} A64 instructions"
        )
        return 1

    for name, (site, broken, expected) in MUTATIONS.items():
        if lifted.count(site) != 1:
            print(
                f"touch_keyboard_integration_emitted_check: FAIL the {name} site is "
                f"not unique in the lifted integration, so the mutant would prove "
                f"nothing and was refused"
            )
            return 1
        mutant = lifted.replace(site, broken, 1)
        try:
            got, msteps = run_once(a64, compiler, mutant)
        except SystemExit as exc:
            print(f"touch_keyboard_integration_emitted_check: FAIL the {name} mutant")
            print(f"  did not build or run, so the gate's checks were never exercised:")
            print("  " + str(exc).splitlines()[0][:120])
            return 1
        if got == 0:
            print(
                f"touch_keyboard_integration_emitted_check: FAIL the {name} mutant "
                f"survived; the gate is not testing what it claims to test"
            )
            return 1
        if got != expected:
            print(
                f"touch_keyboard_integration_emitted_check: FAIL the {name} mutant "
                f"returned assertion {got}; expected {expected}"
            )
            return 1
        print(f"  mutant {name}: rejected at assertion {got} in {msteps:,} A64 instructions")

    print(
        f"touch_keyboard_integration_emitted_check: PASS - the real dispatcher, "
        f"editor, key model, view and the lifted board integration ran together "
        f"for {steps:,} A64 instructions with an MMIO hard stop armed"
    )
    print(
        f"  {c.count} source checks; open by prompt tap, one finger one character, "
        f"slide-off, the chevron, two fingers one Enter, a layout generation change, "
        f"the payload handover, two producers one buffer, Esc, and a held Backspace; "
        f"{len(MUTATIONS)} mutants of the shipped integration rejected"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

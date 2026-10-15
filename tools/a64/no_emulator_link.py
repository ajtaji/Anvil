"""THE FIRST RULE, FOR ANVIL'S TOOLS: NO EMULATOR RUNS WHILE A BOARD OF ITS FAMILY IS AVAILABLE.

Ron, 2026-10-13: "the rule is for AI to not ... run emulators when the boards are installed and
available. not users". On 2026-10-15 an assistant ran this repository's crypto gates on the A64
model (a64_interp) with the Pi 4 at its prompt on WiFi, because nothing here asked. Now every
in-process emulator in Anvil's tools asks first, as a statement of its module:

    import no_emulator_link; no_emulator_link.require('pi', 'a64_interp (the Python A64 core)')

THE QUESTION IS ASKED OF ONE PLACE: the compiler repository's tools/no_emulator.py, the project's
single table of "is a board of this family connected or installed right now?" (USB identities, and
since 2026-10-15 the network bench: a board whose BOARD-SHARE.md is in the vault and not marked
REMOVED). It is not copied here, so the two can never disagree. It is found beside the compiler
these tools are pointed at (PMF_COMPILER), else in the shared layout (C:\\Embedded Compiler, or the
same drive from the Linux boot).

IF IT CANNOT BE FOUND, NOTHING RUNS: it then cannot be shown that no board is available, so the
tool stops as NOT RUN (exit 2: "this told you nothing" - not a pass, not a failure).
"""
import os
import sys
from pathlib import Path

NOT_RUN_EXIT = 2
SUFFIX = "(no emulator when a board is available)"

COMPILER_TOOLS = [
    Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\tools"),
    Path("/run/media/ajtaji/Windows-SSD/Embedded Compiler/PureBasicCode/OpenGl Work/ArduinoBasic/tools"),
]


def _candidates():
    out = []
    named = os.environ.get("PMF_COMPILER", "").strip()
    if named:
        out.append(Path(named).expanduser().parent / "tools")
    return out + COMPILER_TOOLS


def _guard():
    for d in _candidates():
        if (d / "no_emulator.py").is_file():
            if str(d) not in sys.path:
                sys.path.append(str(d))       # appended: never shadows a module of the tool's own
            import no_emulator
            return no_emulator
    return None


def require(families, what):
    """Ask before the first instruction of `what` runs; a refusal ends the tool as NOT RUN (exit 2)."""
    guard = _guard()
    if guard is None:
        msg = ("not run: the compiler's tools/no_emulator.py was not found (looked in %s), so it cannot be "
               "shown that no board of family %s is available %s\n    (%s was NOT started; this is not a "
               "pass and not a failure)" % (" ; ".join(str(d) for d in _candidates()), families, SUFFIX, what))
        try:
            sys.stdout.write(msg + "\n")
            sys.stdout.flush()
        except Exception:                     # noqa: BLE001
            pass
        raise SystemExit(NOT_RUN_EXIT)
    guard.require(families, what)

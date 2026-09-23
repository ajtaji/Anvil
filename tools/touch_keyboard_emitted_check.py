#!/usr/bin/env python3
"""touch_keyboard_emitted_check.py - the layout-independent touch keyboard,
compiled with the real compiler and executed on the A64 interpreter.

      PMF_COMPILER=<path-to-PureMetalForge.exe> PMF_A64_INTERP=<path-to-a64_interp.py> \
          py -3.12 tools/touch_keyboard_emitted_check.py

WHAT THIS PROVES

  Anvil/Core/touch_keyboard.pbi is compiled UNCHANGED and its emitted A64
  is executed. RaspberryPi4/Tests/touch_keyboard_emitted_gate.pi4 supplies
  the one thing the model asks the view for - a hit test - as an identity,
  and supplies the clock as scripted numbers. Nothing sleeps and nothing
  is measured with a stopwatch, so every timing rule in the keyboard is
  checked as the arithmetic it actually is.

  The ASCII coverage walk is the headline: every key, on every page, under
  no modifier, one-shot Shift, Caps Lock and a physically held Shift. All
  95 printable characters 32..126 must be produced at least once, and no
  code outside that window may ever be emitted. A missing character comes
  back as assertion 1000 + its code, so the failure names the character
  instead of the line.

WHAT IT CANNOT PROVE

  * No finger, no panel and no screen are involved. The hit test is an
    identity, so nothing here says a key rectangle is where it looks.
    That belongs to the view lane and to a bench check.
  * The dispatcher lane's record layout is not exercised; this gate
    drains the keyboard's own bounded ring and reads the six contract
    fields through accessors.
  * Latency, frame budget and touch-to-feedback time are hardware
    measurements and are not claimed anywhere in this file.

THE MUTANTS

  Each one restores a plausible wrong version of a single line in the
  production file and requires the gate to go RED at a named assertion.
  A gate that still passes with the chord snapshot removed is a gate that
  was not testing the chord snapshot.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile

import tcp_multiif_emitted_check as emitted
from pmf_compiler import resolve_compiler


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "Anvil" / "Core" / "touch_keyboard.pbi"
GATE = ROOT / "RaspberryPi4" / "Tests" / "touch_keyboard_emitted_gate.pi4"

# name -> (site in the production file, the wrong version, expected assertion)
MUTATIONS = {
    "no_repeat_suppression": (
        "    If gTkCtKey[c] >= 0 And gTkCtReps[c] = 0",
        "    If gTkCtKey[c] >= 0",
        117,
    ),
    # The commit reads the chord snapshot taken when the key was armed.
    # Reading the live modifiers instead is the classic wrong version and
    # it is caught by the first assertion that depends on the snapshot at
    # all - a one-shot Shift, already consumed by the time the finger
    # lifts. The same break is what makes assertion 87, the held-Shift
    # chord released modifier-first, go red.
    "commit_reads_live_modifiers": (
        "      ch = TkEffChar(f, gTkCtShift[c], gTkCtCaps[c])",
        "      ch = TkEffChar(f, TkShiftNow(), TkCapsNow())",
        74,
    ),
    # A held Shift that modified another finger's key is spent. Without
    # the mark, lifting it leaves a one-shot armed and the letter after
    # a chord is capitalised too.
    "chord_not_marked_spent": (
        "    If gTkShiftHeld > 0\n      gTkShiftChord = 1\n    EndIf",
        "    If gTkShiftHeld > 0\n      gTkShiftChord = 0\n    EndIf",
        88,
    ),
    "no_duplicate_key_guard": (
        "  If TkKeyHeldByOther(f, c) <> 0",
        "  If 0 <> 0",
        142,
    ),
    "sym_backslash_key_missing": (
        "  TkAddKey(#TK_PAGE_SYM, 2, 1, #TK_KIND_CHAR, 92, 124, 0)     ; \\  |",
        "  TkAddKey(#TK_PAGE_SYM, 2, 1, #TK_KIND_CHAR, 47, 63, 0)      ; mutated",
        1092,
    ),
    "text_reports_shift": (
        "      TkEmitText(ch, mods)",
        "      If gTkCtShift[c] <> 0 : mods = mods | #AIM_SHIFT : EndIf\n      TkEmitText(ch, mods)",
        43,
    ),
    "oneshot_never_consumed": (
        "    If gTkShift = #TK_SHIFT_ONESHOT\n      gTkShift = #TK_SHIFT_OFF\n      gTkShiftTapSeen = 0\n    EndIf",
        "    If gTkShift = #TK_SHIFT_ONESHOT\n      gTkShiftTapSeen = 0\n    EndIf",
        75,
    ),
    "generation_change_ignored": (
        "  TouchKeyboardCancelAll(#TK_CANCEL_GENERATION)\n  gTkGeneration = gen",
        "  gTkGeneration = gen",
        186,
    ),
    "queue_reserves_nothing": (
        "  room = #TK_QUEUE_MAX - 1",
        "  room = #TK_QUEUE_MAX",
        224,
    ),
    "repeat_starts_early": (
        "        If (now - gTkCtArmMs[i]) >= #TK_REPEAT_DELAY_MS",
        "        If (now - gTkCtArmMs[i]) >= 400",
        111,
    ),
    "hide_without_cancel": (
        "      gTkTransitionMs = now\n      TouchKeyboardCancelAll(#TK_CANCEL_HIDDEN)",
        "      gTkTransitionMs = now",
        193,
    ),
}


def build(compiler: Path, work: Path, mutation: str = "") -> Path:
    """Compile the gate, optionally against a mutated copy of the product."""
    gate_source = GATE.read_text(encoding="utf-8")
    include = 'XIncludeFile "Anvil/Core/touch_keyboard.pbi"'
    if gate_source.count(include) != 1:
        raise SystemExit("touch keyboard gate: the product include drifted")
    if mutation:
        site, broken, _ = MUTATIONS[mutation]
        product = PRODUCT.read_text(encoding="utf-8")
        if product.count(site) != 1:
            raise SystemExit(
                f"touch keyboard mutation: the {mutation} site is not unique in "
                f"{PRODUCT.name}; the mutation would prove nothing, so it was refused"
            )
        mutated = work / f"touch_keyboard_{mutation}.pbi"
        mutated.write_text(product.replace(site, broken, 1), encoding="utf-8")
        gate_source = gate_source.replace(
            include, f'XIncludeFile "{mutated.as_posix()}"', 1
        )
    probe = work / f"touch_keyboard_gate{('_' + mutation) if mutation else ''}.pi4"
    probe.write_text(gate_source, encoding="utf-8")
    emitted.PROBE = probe
    return emitted.build(compiler, work)


def describe(result: int) -> str:
    if result >= 1000:
        return f"assertion {result} (printable ASCII {result - 1000} was never produced)"
    return f"assertion {result}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"))
    args = parser.parse_args()
    compiler = Path(resolve_compiler(args.compiler))
    interp = emitted.required_path(args.interp, "PMF_A64_INTERP")
    a64 = emitted.load_interpreter(interp)

    with tempfile.TemporaryDirectory(prefix="anvil-touch-kb-") as temporary:
        image = build(compiler, Path(temporary))
        result, steps = emitted.execute(a64, image)
    if result:
        print(
            f"touch_keyboard_emitted_check: FAIL {describe(result)} "
            f"after {steps:,} A64 instructions"
        )
        return 1

    for mutation, (_, _, expected) in MUTATIONS.items():
        with tempfile.TemporaryDirectory(prefix=f"anvil-touch-kb-{mutation}-") as temporary:
            mutant = build(compiler, Path(temporary), mutation=mutation)
            mutant_result, mutant_steps = emitted.execute(a64, mutant)
        if mutant_result == 0:
            print(
                f"touch_keyboard_emitted_check: FAIL the {mutation} mutant survived; "
                f"the gate is not testing what it claims to test"
            )
            return 1
        if mutant_result != expected:
            print(
                f"touch_keyboard_emitted_check: FAIL the {mutation} mutant returned "
                f"{describe(mutant_result)}; expected {describe(expected)}"
            )
            return 1
        print(
            f"  mutant {mutation}: rejected at {describe(mutant_result)} "
            f"in {mutant_steps:,} A64 instructions"
        )

    print(
        f"touch_keyboard_emitted_check: PASS - 95 of 95 printable ASCII characters "
        f"produced across 2 pages and 4 modifier states, nothing outside 32..126 "
        f"ever emitted, {steps:,} A64 instructions"
    )
    print(
        "  modifiers, repeat on an injected clock, two fingers one key, sliding, "
        f"cancellation, contact and queue saturation; {len(MUTATIONS)} mutants rejected"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

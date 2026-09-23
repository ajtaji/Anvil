#!/usr/bin/env python3
"""The per-target facts an A64 gate needs, in one place.

WHY THIS FILE EXISTS
--------------------
Every gate under tools/a64/ was written when there was one AArch64 board.
Its harness is compiled `-t pi4`, linked at the Pi 4's load address, and
prints through RaspberryPi4/Lib/uart.pi4 - a PL011 driver at $FE201000.

There are now TWO AArch64 boards.  The Arduino UNO Q is a Cortex-A53
running the same ARMv8.0-A backend the Pi 4's A72 runs, so the pure
libraries - the IP stack, the crypto floor - are the SAME FILES, not
copies of them.  What differs is only the image contract: where the
image is linked, where the stack starts, and what a `UartWriteStr` does.

So a gate does not need a second copy of itself either.  It needs this
table, a `--target` flag, and three substitutions.

WHAT A GATE MUST DO TO GAIN A TARGET
------------------------------------
1.  `from a64_target import TARGETS, apply_target`
2.  `ap.add_argument("--target", choices=sorted(TARGETS), default="pi4")`
3.  `apply_target(globals(), args.target)` as the FIRST thing main() does.
    That rebinds the module-level LOAD, STACK, H_SCRIPT, H_RESULT,
    UART_LO, UART_HI, UART_DR and TFLAG - which the gate's own build()
    and run() read at call time, so nothing else has to change.
4.  build() passes `"-t", TFLAG` instead of `"-t", "pi4"`.
5.  write_harness() substitutes CONSOLE_INCLUDE for the uart include and
    the two `#H_SCRIPT` / `#H_RESULT` literals in the harness text.
    `patch_harness()` below does all three in one call.

WHERE THE UNO Q'S NUMBERS COME FROM - every one is a confirmed fact,
not a guess:

  load  $70000000   ArduinoQ/Board/board.pi4's own LoadAddress line, the
                    address tools/unoq_efi_wrap.py wraps the image for.
  stack $68000000   the same file's StackAddress line.
  free  $63900000..$7D9FFFFF
                    the contiguous free block read off the running board
                    from /proc/iomem, recorded in
                    ArduinoQ/Board/memmap_q.pi4:42-43.  The script and
                    result windows below sit at $72000000 / $72800000,
                    which is inside that block and ABOVE the image and
                    its BSS - the Pi 4 puts them BELOW its image because
                    the Pi 4's image is near the bottom of DRAM and the
                    Q's is not.  Putting them at the Pi 4's addresses
                    would place them outside the Q's confirmed-free
                    region, which is exactly the sort of quiet
                    difference this table exists to stop.
  sink  $6F000000   the console sink, also inside the free block.  See
                    tools/a64/q_console_gate.pi4 for why it is one
                    address and not a device.

THE UNO Q HAS NO PL011 AND NO MEMORY-MAPPED CONSOLE AT ALL.  Under UEFI
Anvil reaches the operator through ConOut, which cannot be called with
no firmware underneath, so the Q harnesses use a gate fixture instead of
a driver.  Including the Pi 4's PL011 in a `-t unoq` image would compile
and would even work here, and it would put a chip that is not on this
board into an image that claims to be this board's.
"""
from __future__ import annotations

TARGETS = {
    "pi4": {
        "flag": "pi4",
        "load": 0x00400000,
        "stack": 0x03000000,
        "script": 0x06000000,
        "console": 'XIncludeFile "RaspberryPi4/Lib/uart.pi4"',
        "uart_lo": 0xFE201000,
        "uart_hi": 0xFE201048,
        "uart_dr": 0xFE201000,
        "what": "Raspberry Pi 4, BCM2711 Cortex-A72, PL011 console",
    },
    "unoq": {
        "flag": "unoq",
        "load": 0x70000000,
        "stack": 0x68000000,
        "script": 0x72000000,
        "console": 'XIncludeFile "tools/a64/q_console_gate.pi4"',
        "uart_lo": 0x6F000000,
        "uart_hi": 0x6F000000,
        "uart_dr": 0x6F000000,
        "what": "Arduino UNO Q, QCM2290 Cortex-A53, no console under the emulator",
    },
}

# The gates do not agree on where the RESULT window goes - some put it
# 8 MB above the script window, some 64 MB - so the offset is read from
# the gate rather than dictated to it.  Only the BASE moves per target.
PI4_SCRIPT = TARGETS["pi4"]["script"]


def apply_target(g: dict, name: str) -> dict:
    """Rebind a gate module's target constants in place.  Returns the row.

    `g` is the gate's `globals()`.  Only names the gate already defines
    are touched: a gate with no H_RESULT keeps not having one.  The
    result window keeps whatever offset from the script window the gate
    chose for itself.
    """
    if name not in TARGETS:
        raise SystemExit(
            "unknown target %r for an A64 gate.  This toolchain builds "
            "AArch64 for %s; a new board is added to TARGETS in "
            "tools/a64/a64_target.py, not by editing a gate."
            % (name, ", ".join(sorted(TARGETS))))
    row = TARGETS[name]
    offset = None
    if "H_SCRIPT" in g and "H_RESULT" in g:
        offset = g["H_RESULT"] - g["H_SCRIPT"]
    g["TFLAG"] = row["flag"]
    g["TARGET_NAME"] = name
    g["TARGET_WHAT"] = row["what"]
    g["CONSOLE_INCLUDE"] = row["console"]
    if "LOAD" in g:
        g["LOAD"] = row["load"]
    if "STACK" in g:
        g["STACK"] = row["stack"]
    if "H_SCRIPT" in g:
        g["H_SCRIPT"] = row["script"]
    if "H_RESULT" in g and offset is not None:
        g["H_RESULT"] = row["script"] + offset
    for key, name_ in (("uart_lo", "UART_LO"), ("uart_hi", "UART_HI"),
                       ("uart_dr", "UART_DR")):
        if name_ in g:
            g[name_] = row[key]
    return row


def patch_harness(text: str, g: dict) -> str:
    """Apply the target's console and window addresses to a harness.

    Called by every gate's write_harness().  It is deliberately a
    REPLACEMENT of exact strings rather than a template: if the harness
    ever stops carrying one of them the substitution silently doing
    nothing would be a gate quietly testing the wrong addresses, so each
    one is checked and a miss is loud.
    """
    subs = [('XIncludeFile "RaspberryPi4/Lib/uart.pi4"',
             g.get("CONSOLE_INCLUDE",
                   'XIncludeFile "RaspberryPi4/Lib/uart.pi4"'))]
    if "H_SCRIPT" in g:
        subs.append(("#H_SCRIPT = $%08X" % PI4_SCRIPT,
                     "#H_SCRIPT = $%08X" % g["H_SCRIPT"]))
    if "H_RESULT" in g:
        # The Pi 4 literal is whatever the gate wrote; recover it from
        # the text rather than assuming, so a gate with an unusual
        # result window still substitutes correctly.
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("#H_RESULT = $"):
                subs.append((s, "#H_RESULT = $%08X" % g["H_RESULT"]))
                break
    for old, new in subs:
        if old == new:
            continue
        if old not in text:
            raise SystemExit(
                "a64_target.patch_harness could not find %r in the "
                "harness.  The harness and this substitution have "
                "drifted apart; fix them together rather than dropping "
                "the substitution, or the gate will build for one "
                "target and grade another." % old)
        text = text.replace(old, new)
    return text

#!/usr/bin/env python3
"""The Raspberry Pi 3 monitor's boot does five things in an order that is not
negotiable, and this is the gate that says so.

TWO FACTS ABOUT THIS BOARD DECIDE THE ORDER, and both were found by reading
the boot chain rather than by running it:

  THE FIRMWARE MAILBOX STOPS ANSWERING ONCE TRANSLATION IS ON.
  RaspberryPi3/Lib/mailbox.pbi's context check reads SCTLR, masks it with
  the MMU bit and the data-cache bit, and REFUSES the transaction if either
  is set - its property buffer has to be memory the graphics processor and
  the main processor agree about. So every question this monitor will ever
  ask the firmware has to be asked BEFORE the page tables go up: the
  console's clock, the memory extent, the device tree, the card's clock and
  the board revision code.

  THE LOADER'S DEADMAN IS ARMED AND IS NOT FED. Fifteen seconds from the
  branch. A monitor that has not confirmed its slot by then is reset, and
  the loader falls back - which from the other end of a serial cable looks
  exactly like the new image having crashed.

Neither is visible in the code that would break if it were violated. Move
HwMemAsk() below MmuUp() and the build still succeeds, the gates still
pass, and `info` says the board cannot state its memory size for a reason
nobody will guess. Delete the watchdog release and the board resets every
fifteen seconds with a prompt on the screen. THAT is what this gate is
for: both mistakes are silent, and both are one line.

IT IS A SOURCE-SHAPE GATE AND SAYS SO. It reads the order of calls in
Main() and the shape of the confirm path; it does not execute anything.
That is the right instrument for an ORDERING claim - the emitted-code gate
beside it (tools/pi3_memory_guard_check.py) is the right one for a
DECISION - and neither is a substitute for the other.

SEVEN MUTANTS, every one a single line moved or deleted:

  mmu-before-mailbox    the page tables raised before the memory size is
                        asked - the mailbox then refuses and the board
                        cannot say what it has
  mmu-before-confirm    translation on before the slot is confirmed; the
                        card work then happens with the mailbox shut and
                        the confirm's own clock question would fail
  no-watchdog-stop      the deadman never released: a reset every fifteen
                        seconds, with a working prompt
  confirm-after-stop    the watchdog stopped before the slot is confirmed,
                        which throws away the fallback the trial exists for
  uart-late             the console brought up after the firmware
                        questions, so a failure in them prints nothing
  confirm-mounts-all    the confirm path mounting every partition instead
                        of the boot one - fine on a fast card, fifteen
                        seconds on a slow one
  confirm-raw-lba       the control record reached by block address rather
                        than by name, which is the private-filesystem
                        shape rule 30 exists to stop

Usage:
  python tools/pi3_confirm_order_check.py
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "RaspberryPi3" / "Board" / "board.pi3"
STORAGE = ROOT / "RaspberryPi3" / "Board" / "storage.pi3"

ASSERTIONS = 25


def fail(message: str) -> None:
    raise SystemExit("pi3 confirm order gate: " + message)


def procedure(text: str, header: str, label: str) -> str:
    if text.count(header) != 1:
        fail(f"{label} start count {text.count(header)}")
    start = text.index(header)
    end = text.find("\nEndProcedure", start)
    if end < 0:
        fail(f"{label} has no end")
    return text[start : end + len("\nEndProcedure")]


def at(body: str, needle: str, label: str) -> int:
    if body.count(needle) < 1:
        fail(f"{label} is not in Main() at all - looked for {needle!r}")
    return body.index(needle)


def check(board: str, storage: str) -> list[str]:
    """Every ordering claim, as a list of the ones that held."""
    held: list[str] = []
    main = procedure(board, "Procedure Main()", "Main")

    # ---- the five stages, in the one order that works ---------------
    uart = at(main, "Pi3UartInit(", "the console bring-up")
    mem = at(main, "Pi3MonitorBootMemory()", "the memory and device-tree question")
    ask = at(main, "HwMemAsk()", "the revision-code question")
    clock = at(main, "Pi3BootMaxCoreClock()", "the card-clock question")
    sd = at(main, "Pi3SdInit(", "the card bring-up")
    confirm = at(main, "Pi3StorageConfirmSlot()", "the slot confirm")
    dog = at(main, "Pi3MonWatchdogStop()", "the watchdog release")
    mmu = at(main, "MmuUp()", "the page tables")

    order = [
        ("the console comes up before the firmware is questioned", uart, mem),
        ("the memory extent is asked before the revision code", mem, ask),
        ("the revision code is asked before the card clock", ask, clock),
        ("the card clock is asked before the card is brought up", clock, sd),
        ("the card is up before the slot is confirmed", sd, confirm),
        ("the slot is confirmed before the deadman is released", confirm, dog),
        ("the deadman is released before the page tables go up", dog, mmu),
    ]
    for label, first, second in order:
        if not first < second:
            fail(f"{label} - and it does not")
        held.append(label)

    # EVERY firmware question is above the page tables. Stated separately
    # from the chain above because the chain would still hold if one of
    # them were moved past MmuUp on its own.
    for label, where in (("the console clock", uart),
                         ("the memory extent", mem),
                         ("the revision code", ask),
                         ("the card clock", clock),
                         ("the card bring-up", sd)):
        if not where < mmu:
            fail(f"{label} is asked after the page tables go up, and the "
                 "mailbox refuses once translation is on")
        held.append(f"{label} is asked while the firmware still answers")

    # ---- the console is first, and it prints before anything waits --
    say = at(main, 'PrintN("Anvil starting.")', "the first line printed")
    if not uart < say:
        fail("the first line is printed before the console is up")
    held.append("the first line is printed, and after the console is up")
    if not say < mem:
        fail("the board questions the firmware before it has said anything - "
             "a failure there would print nothing at all")
    held.append("something is printed before anything can fail silently")

    # ---- nothing that waits on the card happens before the release --
    for banned in ("StorageUp()", "SettingsLoad(", "Banner()"):
        if banned in main and main.index(banned) < dog:
            fail(f"{banned} runs before the deadman is released; on a card "
                 "where a block read costs milliseconds that is how fifteen "
                 "seconds goes")
        held.append(f"{banned} does not run inside the trial window")

    # ---- the confirm path itself -----------------------------------
    body = procedure(storage, "Procedure.i Pi3StorageForConfirm()",
                     "Pi3StorageForConfirm")
    if "FsMount(1)" not in body:
        fail("the confirm path does not mount partition 1 by name")
    held.append("the confirm mounts partition 1 by name")
    for banned, why in (
        ("pi3StorageMountAny", "it would try every partition"),
        ("FsSelectPartition", "it would be free to land on another volume"),
        ("HwStorageReport", "it would print a paragraph against the clock"),
    ):
        if banned in body:
            fail(f"the confirm path calls {banned} and {why}")
        held.append(f"the confirm path does not call {banned}")

    # THE RECORD IS REACHED BY NAME. Rule 30: one filesystem, and a board
    # that walked to its own records by block address would be carrying a
    # second one.
    reader = procedure(storage, "Procedure.i Pi3BootReadRecord(slot.i, buffer.i)",
                       "Pi3BootReadRecord")
    writer = procedure(storage, "Procedure.i Pi3BootWriteRecord(slot.i, buffer.i)",
                       "Pi3BootWriteRecord")
    for label, body2 in (("the record reader", reader), ("the record writer", writer)):
        if ("FsOpen(" if body2 == reader else "FsExtentOf(") not in body2:
            fail(f"{label} does not open the record by name")
        for banned in ("Pi3SdReadBlock", "Pi3SdWriteBlock", "fat_ClusterLba",
                       "fat_NextCluster", "pi3_up_lba"):
            if re.search(r'\b'+re.escape(banned)+r'\s*\(', body2):
                fail(f"{label} reaches the medium through {banned} rather "
                     "than through the shared filesystem - that is the private "
                     "path rule 30 exists to stop")
        held.append(f"{label} opens by name and touches no block address")

    # The record file names are on the boot partition, explicitly.
    names = procedure(storage, "Procedure.i Pi3BootRecordName(slot.i)",
                      "Pi3BootRecordName")
    if '"1:P3CTRLA.BIN"' not in names or '"1:P3CTRLB.BIN"' not in names:
        fail("the control records are not named with the boot partition's "
             "prefix - a monitor that had fallen back to another volume "
             "would confirm against the wrong record, or none")
    held.append("the control records carry the boot partition's prefix")

    # The writer arms and disarms around its one write.
    if writer.count("FsSetRangeWriter(0)") != 2 or writer.count("FsSetRangeWriter(@Pi3SdWriteBlocks)") != 1:
        fail("the record writer does not arm and disarm exactly once - "
             "between A/B writes the filesystem must have no writer at all")
    held.append("the record writer arms and disarms around its one write")
    return held


# A MUTATION MOVES A LINE; IT DOES NOT DELETE ONE. Deleting a call makes
# the gate fail because the call is missing, which proves only that the
# gate can find it. Moving it past the line it must stay above is the
# mistake somebody would actually make, and it is the one worth catching.
# A five-part entry cuts the line out and pastes it back where it must
# not be.
MUTATIONS = {
    "mmu-before-mailbox": ("board", "  HwMemAsk()\n", "",
                           "  MmuAddNc(",
                           "  HwMemAsk()\n  MmuAddNc("),
    "mmu-before-confirm": ("board", "  If Pi3StorageConfirmSlot() = 0\n",
                           "  MmuUp()\n  If Pi3StorageConfirmSlot() = 0\n"),
    "no-watchdog-stop": ("board", "  If Pi3MonWatchdogStop() = 0\n",
                         "  If 0 = 1\n"),
    "confirm-after-stop": ("board",
                           "  If Pi3StorageConfirmSlot() = 0\n",
                           "  Pi3MonWatchdogStop()\n  If Pi3StorageConfirmSlot() = 0\n"),
    "uart-late": ("board", '  PrintN("Anvil starting.")\n', "",
                  "  If Pi3MailboxContext() = 0",
                  '  PrintN("Anvil starting.")\n  If Pi3MailboxContext() = 0'),
    "confirm-mounts-all": ("storage", "  If FsMount(1) = 0\n",
                           "  If pi3StorageMountAny() = 0\n"),
    "confirm-raw-lba": ("storage", "  If FsOpen(Pi3BootRecordName(slot)) = 0 : ProcedureReturn 0 : EndIf\n",
                        "  If Pi3SdReadBlock(slot, buffer) = 0 : ProcedureReturn 0 : EndIf\n"),
}


def mutate(board: str, storage: str, name: str) -> tuple[str, str]:
    spec = MUTATIONS[name]
    which, old, new = spec[0], spec[1], spec[2]
    text = board if which == "board" else storage
    if text.count(old) < 1:
        fail(f"{name} anchor not found: {old!r}")
    text = text.replace(old, new, 1)
    if len(spec) == 5:
        anchor, replacement = spec[3], spec[4]
        if text.count(anchor) < 1:
            fail(f"{name} paste anchor not found: {anchor!r}")
        text = text.replace(anchor, replacement, 1)
    return (text, storage) if which == "board" else (board, text)


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    board = BOARD.read_text(encoding="utf-8")
    storage = STORAGE.read_text(encoding="utf-8") + '\n' + (ROOT / 'RaspberryPi3/Lib/boot_record.pbi').read_text(encoding='utf-8')

    held = check(board, storage)
    if len(held) != ASSERTIONS:
        fail(f"{len(held)} ordering claims held; this gate is written for "
             f"{ASSERTIONS}. A claim was added or removed without the count "
             "moving with it")

    killed = []
    for name in MUTATIONS:
        mb, ms = mutate(board, storage, name)
        try:
            check(mb, ms)
        except SystemExit as caught:
            killed.append((name, str(caught)))
            continue
        print(f"pi3_confirm_order_check: FAIL - the {name} mutation was not "
              "caught. The gate accepts a boot order that does not work.")
        return 1

    digest = hashlib.sha256(
        (procedure(board, "Procedure Main()", "Main") + storage).encode("utf-8")
    ).hexdigest()

    print(f"pi3_confirm_order_check: PASS - {ASSERTIONS} ordering claims, "
          f"{len(killed)} mutants rejected")
    print("  every firmware question is asked while the firmware still")
    print("  answers; the console is up before anything can fail silently;")
    print("  the slot is confirmed and the deadman released before the page")
    print("  tables go up; nothing that waits on the card runs inside the")
    print("  trial window; and the control records are opened BY NAME on the")
    print("  boot partition, through the shared filesystem, with the writer")
    print("  armed for exactly one write")
    for name, why in killed:
        short = why.split(" - ")[0].replace("pi3 confirm order gate: ", "")
        print(f"  {name} mutation rejected: {short[:96]}")
    print(f"  Main() + the confirm path sha256 {digest}")
    print("No hardware was contacted and nothing was compiled: this is an")
    print("ordering claim, and the order is a property of the source.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

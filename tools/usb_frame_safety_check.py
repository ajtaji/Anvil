#!/usr/bin/env python3
"""NOTHING THE USB HOST HANDS TO HARDWARE MAY LIVE IN AN INVOCATION FRAME.

Automatic storage stopped being a fixed address on 2026-09-11. A procedure's
locals used to be static slots in BSS: they had an address inline assembly
could name, they survived the call that made them, and two live calls of one
procedure shared them. They now live in the frame of one invocation, which is
reused by the next call and gone when the call returns.

That is the right model and it closes a real defect, but it turns four shapes
that used to work into silent corruption, and every one of them is in the USB
host bring-up if it is anywhere:

  a local's address handed     a ring, a TRB, a descriptor or a command block
  to the controller            built in a frame and given to a bus master. The
                               CPU-side view stays perfect; the controller
                               reads or writes a frame the next call has
                               already taken back.
  inline assembly naming       the name means a different place on every call.
  a local                      The compiler refuses this one outright, so this
                               gate exists to say the path is clean rather than
                               to catch it - a refusal is a build failure and
                               this is a reminder of why.
  a local read before it is    it used to hold the previous call's value and
  written                      now holds zero. A retry counter, a "have I done
                               this" flag or a cached classification kept this
                               way changes behaviour without changing source.
  recursion                    it used to overwrite one static slot set and now
                               costs a frame per level. Both are defects; the
                               second one is a stack the monitor has to have
                               budgeted for.

WHAT THIS GATE CHECKS, AND WHAT IT DOES NOT. It checks direct address spelling,
selected ASM symbol spelling, and syntactic recursion in the listed files.
It does NOT track pointer aliases, reads before writes, dynamic calls, or the
complete pre-USB call graph. The four historical risks above are motivation,
not four implemented proofs. Use usb_local_flow_check.py for a conservative
source-flow review report; its unresolved cases must not be called clean.
When a listing is offered, this script also checks selected emitted frame shapes. It
compiles nothing by itself, runs nothing on hardware, and says nothing about
whether a controller answers. It is the gate for the CLASS, not for the board.

Usage:
    python tools/usb_frame_safety_check.py [--listing build/pi4/anvil.img.asm]

Exit 0 and a one-line verdict per section, or an assertion naming the site.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]

# THE PATH. Every file the USB host bring-up reaches, and the cache walk the
# rings depend on. cursor_input.pi4 owns UsbEnumerate(), which is the one
# bring-up; hw_usb.pi4 is the diagnostics wrapper over the same stack.
USB_PATH = (
    "RaspberryPi4/Lib/xhci.pi4",
    "RaspberryPi4/Lib/hid.pi4",
    "RaspberryPi4/Lib/pcie.pi4",
    "RaspberryPi4/Lib/usbmsc.pi4",
    "RaspberryPi4/Lib/mailbox.pi4",
    "RaspberryPi4/Lib/dma.pi4",
    "RaspberryPi4/Board/cursor_input.pi4",
    "RaspberryPi4/Board/hw_usb.pi4",
    # The phase record's own two files, added 2026-09-11 evening. They are
    # in the list for the same reason as the rest and for one more: the
    # record exists to be read by a DIFFERENT image after a reset, so a
    # marker that lived in a frame would not merely be wrong, it would be
    # wrong in the one direction nobody could check afterwards.
    "RaspberryPi4/Board/memmap.pi4",
    "RaspberryPi4/Board/boot.pi4",
)

# THE SINKS - the calls that hand an address to something other than this CPU,
# or that keep it past the call. An address of a frame slot reaching any of
# these is the defect this gate exists for.
#
# msc_Command is NOT a sink and the distinction is the whole point: it COPIES
# the sixteen CDB bytes into the file-scope CBW before any transfer starts
# (usbmsc.pi4, "PokeA(msc_Cbw() + 15 + i, PeekA(*cdb + i))"), so a caller may
# build a CDB in a frame. Anything that forwards the pointer instead would
# belong in this list.
HARDWARE_SINKS = (
    "XhciBulkIn", "XhciBulkOut", "XhciCopyIn", "XhciCopyOut",
    "XhciControlIn", "XhciControlOut", "XhciQueueTrb",
    "DmaCacheRange", "DmaCacheRect", "DmaCacheLines",
    "DmaCopy", "DmaFill", "DmaStart",
    "MailboxSetWord", "MailboxListSetWord",
    "FatSetBlockReader", "FatSetBlockWriter",
)

PROC = re.compile(r"^\s*Procedure(?:\.\w+)?\s+(\w+)\s*\(([^)]*)\)", re.I)
ENDPROC = re.compile(r"^\s*EndProcedure", re.I)
DECL = re.compile(r"^\s*(Protected|Define|Static|Dim)\s+(.*)$", re.I)
ASMOPEN = re.compile(r"^\s*ASM\s*$", re.I)
ASMCLOSE = re.compile(r"^\s*EndASM\s*$", re.I)
CALL = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
ADDROF = re.compile(r"@([A-Za-z_]\w*)")
# A symbol an ASM block materialises with adrp. Legal ones: a file-scope
# variable (global_*), a linker symbol (__*), and a label the same block
# defines.
ADRP = re.compile(r"^\s*adrp\s+\w+\s*,\s*([A-Za-z_][\w]*)", re.I)
ASMLABEL = re.compile(r"^\s*([A-Za-z_]\w*)\s*:\s*$")


STRING = re.compile(r'"[^"]*"')


def code_of(line: str) -> str:
    """The executable part of a line: no comment, and no string body.

    A string body is emptied rather than removed so that column-sensitive
    nothing depends on it - and it must go, because this tree writes
    sentences that name procedures ("call DmaErrorText() again"), and a
    scanner that reads those as calls invents a recursion that is a
    full stop in a help message.
    """
    return STRING.sub('""', line.split(";")[0])


def procedures(text: str):
    """Yield (name, params, [(lineno, source_line)]) for each procedure."""
    name = None
    params = ()
    body = []
    for number, line in enumerate(text.split(chr(10)), 1):
        found = PROC.match(code_of(line))
        if found:
            name = found.group(1)
            params = tuple(p.split(".")[0].strip().lower()
                           for p in found.group(2).split(",") if p.strip())
            body = []
            continue
        if ENDPROC.match(code_of(line)):
            if name:
                yield name, params, body
            name = None
            continue
        if name:
            body.append((number, line))


def locals_of(params, body):
    """Every automatic name in the procedure, and whether it is an array."""
    names = {}
    for _, line in body:
        found = DECL.match(code_of(line))
        if not found:
            continue
        rest = found.group(2)
        head = rest.split("=")[0] if "=" in rest else rest
        for word, bracket in re.findall(r"\b([A-Za-z_]\w*)\s*(?:\.\w+)?\s*(\[)?", head):
            low = word.lower()
            if low in ("dim", "protected", "define", "static", "newlist", "shared", "global"):
                continue
            names[low] = bool(bracket)
    for p in params:
        names.setdefault(p, False)
    return names


def check_addresses(reports):
    """Reject direct @local spelling on a line containing a named sink."""
    hits = 0
    for path, text in reports:
        for name, params, body in procedures(text):
            names = locals_of(params, body)
            for number, line in body:
                source = code_of(line)
                taken = {m.group(1).lower() for m in ADDROF.finditer(source)}
                if not taken & set(names):
                    continue
                for callee in CALL.findall(source):
                    if callee in HARDWARE_SINKS:
                        raise AssertionError(
                            "%s:%d %s() hands the address of automatic storage to %s: %s"
                            % (path, number, name, callee, source.strip()))
                hits += 1
    return hits


def check_assembly(reports):
    """No ASM block in the path materialises a name that is not file-scope."""
    blocks = 0
    for path, text in reports:
        for name, params, body in procedures(text):
            names = locals_of(params, body)
            inside = False
            labels = set()
            pending = []
            for number, line in body:
                source = code_of(line)
                if ASMOPEN.match(source):
                    inside, labels, pending = True, set(), []
                    blocks += 1
                    continue
                if ASMCLOSE.match(source):
                    for lineno, symbol in pending:
                        if symbol.startswith("global_") or symbol.startswith("__"):
                            continue
                        if symbol in labels:
                            continue
                        raise AssertionError(
                            "%s:%d %s()'s inline assembly materialises '%s', which is "
                            "neither file-scope storage nor a linker symbol nor a label "
                            "of its own block. Automatic storage is invocation-relative."
                            % (path, lineno, name, symbol))
                        # (a flattened local would read <proc>_<local>)
                    inside = False
                    continue
                if not inside:
                    continue
                mark = ASMLABEL.match(source)
                if mark:
                    labels.add(mark.group(1))
                    continue
                found = ADRP.match(source)
                if found:
                    pending.append((number, found.group(1)))
                    _ = names  # a local's flattened name would land here
    return blocks


def call_graph(reports):
    defined = set()
    edges = {}
    for _, text in reports:
        for name, _params, body in procedures(text):
            defined.add(name)
            out = edges.setdefault(name, set())
            for _number, line in body:
                for callee in CALL.findall(code_of(line)):
                    out.add(callee)
    return {k: {c for c in v if c in defined} for k, v in edges.items()}


def check_recursion(reports):
    edges = call_graph(reports)
    colour = {}

    def walk(node, path):
        colour[node] = 1
        for nxt in sorted(edges.get(node, ())):
            if colour.get(nxt) == 1:
                raise AssertionError(
                    "recursion in the USB path: " + " -> ".join(path + [nxt]))
            if colour.get(nxt) is None:
                walk(nxt, path + [nxt])
        colour[node] = 2

    for node in sorted(edges):
        if colour.get(node) is None:
            walk(node, [node])
    return len(edges)


# ----------------------------------------------------------------------
#  The emitted half. Offered a listing, it proves the frames themselves.
# ----------------------------------------------------------------------
LABEL = re.compile(r"^([A-Za-z_]\w*):$")
SUBSP = re.compile(r"^sub sp, sp, #(\d+)$")
ADDSP = re.compile(r"^add sp, sp, #(\d+)$")
X29OFF = re.compile(r"x29, #(\d+)")


def listing_procedures(listing: Path):
    name = None
    body = []
    for line in listing.read_text(encoding="utf-8", errors="replace").split(chr(10)):
        line = line.strip()
        mark = LABEL.match(line)
        if mark and not mark.group(1).startswith("__"):
            if name:
                yield name, body
            name, body = mark.group(1), []
            continue
        if name is not None and line:
            body.append(line)
    if name:
        yield name, body


def check_emitted(listing: Path):
    """Three facts about every frame in the image, not only the USB path.

    the frame holds its own slots   a slot addressed below sp is memory the
                                    next call owns
    the frame is 16-byte aligned    AArch64 faults on a misaligned SP the
                                    instant it is used as a base
    a loop never leaks sp           a staging push a branch skips is a stack
                                    that grows by an iteration, which reaches
                                    the bottom in a loop long enough
    """
    frames = 0
    for name, body in listing_procedures(listing):
        size = 0
        for index, line in enumerate(body[:6]):
            if line == "mov x29, sp":
                nxt = body[index + 1] if index + 1 < len(body) else ""
                found = SUBSP.match(nxt)
                size = int(found.group(1)) if found else 0
                break
        frames += 1
        if size % 16:
            raise AssertionError("%s has a %d-byte frame, which is not 16-byte aligned"
                                 % (name, size))
        worst = max([int(m) for line in body for m in X29OFF.findall(line)] or [0])
        if worst > size:
            raise AssertionError(
                "%s addresses a slot %d bytes below x29 but allocates %d: the slot is "
                "outside the frame and the next call owns it" % (name, worst, size))
        leak(name, body)
    return frames


def leak(name, body):
    labels = {}
    for index, line in enumerate(body):
        mark = LABEL.match(line)
        if mark:
            labels[mark.group(1)] = index
    start = 0
    for index, line in enumerate(body[:14]):
        if line == "mov x29, sp":
            start = index + 1
            if start < len(body) and SUBSP.match(body[start]):
                start += 1
                probe = start
                while probe < min(start + 8, len(body)):
                    if body[probe].startswith("b.lo __a64_frame_zero"):
                        start = probe + 1
                        break
                    probe += 1
            break
    seen = {}
    work = [(start, 0)]
    while work:
        at, delta = work.pop()
        while at < len(body):
            if at in seen:
                if seen[at] != delta:
                    raise AssertionError(
                        "%s reaches one instruction with two stack depths (%d and %d): "
                        "a loop leaks the stack it pushes" % (name, seen[at], delta))
                break
            seen[at] = delta
            line = body[at]
            if LABEL.match(line):
                at += 1
                continue
            found = SUBSP.match(line)
            if found:
                delta += int(found.group(1))
                at += 1
                continue
            found = ADDSP.match(line)
            if found:
                delta -= int(found.group(1))
                at += 1
                continue
            if line == "mov sp, x29" or line == "ret":
                break
            found = re.match(r"b (__\w+)$", line)
            if found:
                target = labels.get(found.group(1))
                if target is None:
                    break
                at = target
                continue
            found = re.match(r"b\.[a-z]+ (__\w+)$", line)
            if found and found.group(1) in labels:
                work.append((labels[found.group(1)], delta))
            at += 1


def read_path():
    return [(name, (ROOT / name).read_text(encoding="utf-8", errors="replace"))
            for name in USB_PATH]


def mutants():
    """Negative controls. Each is a defect somebody can actually write."""
    base = ("Global g.i = 0" + chr(10) +
            "Procedure Ring()" + chr(10) +
            "  Dim trb.a[16]" + chr(10) +
            "  DmaCacheRange(@trb[0], 16)" + chr(10) +
            "EndProcedure" + chr(10))
    yield "address of a frame array handed to the cache walk", [("mutant.pi4", base)], check_addresses
    asm = ("Procedure Walk()" + chr(10) +
           "  Protected a.i" + chr(10) +
           "  a = 0" + chr(10) +
           "  ASM" + chr(10) +
           "    adrp x9, walk_a" + chr(10) +
           "  EndASM" + chr(10) +
           "EndProcedure" + chr(10))
    yield "inline assembly naming a local", [("mutant.pi4", asm)], check_assembly
    rec = ("Procedure.i Down(n.i)" + chr(10) +
           "  If n > 0" + chr(10) +
           "    ProcedureReturn Down(n - 1)" + chr(10) +
           "  EndIf" + chr(10) +
           "  ProcedureReturn 0" + chr(10) +
           "EndProcedure" + chr(10))
    yield "recursion", [("mutant.pi4", rec)], check_recursion


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listing", default=None,
                        help="an emitted -S listing to prove the frames themselves")
    args = parser.parse_args()

    reports = read_path()
    taken = check_addresses(reports)
    print("addresses   direct-spelling check only - %d local-address site(s); "
          "none on a line with a listed sink; aliases NOT checked" % taken)
    blocks = check_assembly(reports)
    print("assembly    ok - %d inline block(s) in the path, every materialised symbol "
          "file-scope or a linker symbol" % blocks)
    nodes = check_recursion(reports)
    print("recursion   ok - %d procedure(s) in the path's call graph, no cycle" % nodes)

    for label, mutant, check in mutants():
        try:
            check(mutant)
        except AssertionError:
            pass
        else:
            raise AssertionError("the negative control survived: " + label)
    print("mutants     ok - three injected defects, three refusals")

    if args.listing:
        listing = Path(args.listing)
        if not listing.is_file():
            raise SystemExit("no such listing: " + str(listing))
        frames = check_emitted(listing)
        print("emitted     ok - %d frame(s): every slot inside its frame, every frame "
              "16-byte aligned, no loop leaks the stack" % frames)
    else:
        print("emitted     skipped - pass --listing <image>.img.asm to prove the frames")
    return 0


if __name__ == "__main__":
    sys.exit(main())

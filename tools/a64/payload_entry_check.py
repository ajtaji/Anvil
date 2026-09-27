#!/usr/bin/env python3
"""payload_entry_check.py - a payload is ENTERED with the service table, on every board.

Anvil/Hal/abi.pbi promises a payload x0 = the service table (or 0) and
x1..x7 = 0 at its first instruction, and the monitor its own sp back when
the payload returns. Until 2026-09-27 only the Pi 4 kept that promise: the
Pi 3 entered with x0 = the entry address, the UNO Q with x0 = 0, and every
gate modelled the table instead of entering through the board, so nothing
noticed. Anvil/Kernel/payload_call.pbi is now the one entry, and this gate
proves it ON THE REAL MONITOR IMAGES:

  For each of board.pi3 and board.unoq, the monitor is
  compiled exactly as tools/build.py compiles it and loaded into the A64
  interpreter at its own link address. Then, calling the monitor's own
  procedures:
    1. BuildServiceTable() fills the REAL table and SvcTableAddr() answers
       where it is; gGoX0 is set to it, as PmfEnter() does.
    2. A probe payload, compiled separately for the same target with
       --wants-services --entry-returns and placed in that board's payload
       window, is entered through the board's own RunAt(). The probe
       captures x0..x7 at its first statement, checks the table's magic,
       calls the REAL SvcBoardId slot through it and returns $5A00 plus
       the answer.
    3. The gate reads back: gGoRc = $5A00 + that board's #SVC_BOARD_ID, the
       probe saw x1..x7 = 0, gGoX0 is cleared, the monitor's sp is exactly
       what it was, DAIF is what it was, and HwPayloadReturned ran.
    4. A second payload, eight hand-assembled words that DESTROY sp and
       return 0x77, is entered the same way: RunAt must still return to its
       caller with the caller's sp, which only the monitor's own restore
       can do (a compiled --entry-returns payload restores sp itself, so
       it cannot prove the monitor does).
  Registers x1..x18 are POISONED before each RunAt, so a register the
  entry forgets to clear arrives non-zero rather than accidentally zero.

  System registers are answered here, above step(), as the interpreter
  requires: a plain register file for every MRS/MSR the path reaches
  (DAIF, VBAR, CPTR, SCTLR, CurrentEL = the board's level), and
  MSR DAIFSet/DAIFClr on the modelled DAIF.

--mutate: the gate must go red for each of
    payload_call.pbi  x0 = the entry address       (the Pi 3's old defect)
    payload_call.pbi  x5..x7 not cleared
    payload_call.pbi  the monitor's sp not restored
    payload_call.pbi  DAIF not restored
    payload_call.pbi  interrupts not masked until the vectors are back
    hw_board.pi3      the old `blr x0` entry
    qstubs_q.unoq     the old QCall(a, 0, 0, 0, 0, 0) entry

    py -3 tools/a64/payload_entry_check.py --compiler <PureMetalForge.exe> [--mutate]
"""
from __future__ import annotations

import argparse
import concurrent.futures
import os
import pathlib
import shutil
import struct
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import pi5_desk as d                                   # noqa: E402

# (target, board source, build args, payload load, payload stack, current EL,
#  the files whose procedures the entry path runs)
BOARDS = {
    "pi3": ("RaspberryPi3/Board/board.pi3", [], 0x03A00000, 0x03E00000, 12,
            "RaspberryPi3/Board/board.pi3"),
    "unoq": ("ArduinoQ/Board/board.unoq", ["--entry-returns"], 0x46200000, 0x4A000000, 4,
             "ArduinoQ/Board/board.unoq"),
}
BOARD_ID_SOURCE = {"pi3": "RaspberryPi3/Board/board.pi3",
                   "unoq": "ArduinoQ/Board/board.unoq"}
TREES = ("Anvil", "RaspberryPi3", "ArduinoQ")
RETURN = d.RETURN
DRIVER_STACK_GAP = 0x4000          # the gate's own frame below the monitor stack
POISON = 0xD1ED_0000_0000_0000

PROBE = r"""; payload_entry_probe - built by tools/a64/payload_entry_check.py.
; Names no chip. Captures x0..x7 at its first statement, checks the table,
; calls one real slot through it, and returns $5A00 plus its answer.
Global gR0.i
Global gR1.i
Global gR2.i
Global gR3.i
Global gR4.i
Global gR5.i
Global gR6.i
Global gR7.i
Global *svc_boardid

Procedure Capture()
  ASM
    adrp x9, global_gr0
    add  x9, x9, #:lo12:global_gr0
    str  x0, [x9]
    adrp x9, global_gr1
    add  x9, x9, #:lo12:global_gr1
    str  x1, [x9]
    adrp x9, global_gr2
    add  x9, x9, #:lo12:global_gr2
    str  x2, [x9]
    adrp x9, global_gr3
    add  x9, x9, #:lo12:global_gr3
    str  x3, [x9]
    adrp x9, global_gr4
    add  x9, x9, #:lo12:global_gr4
    str  x4, [x9]
    adrp x9, global_gr5
    add  x9, x9, #:lo12:global_gr5
    str  x5, [x9]
    adrp x9, global_gr6
    add  x9, x9, #:lo12:global_gr6
    str  x6, [x9]
    adrp x9, global_gr7
    add  x9, x9, #:lo12:global_gr7
    str  x7, [x9]
  EndASM
EndProcedure

Procedure.i Main()
  Capture()
  If gR0 = 0
    ProcedureReturn 1
  EndIf
  If (PeekI(gR0) & $FFFFFFFF) <> #MAGIC
    ProcedureReturn 2
  EndIf
  If (gR1 | gR2 | gR3 | gR4 | gR5 | gR6 | gR7) <> 0
    ProcedureReturn 3
  EndIf
  *svc_boardid = PeekI(gR0 + #HDR + #SLOT * 8)
  ProcedureReturn $5A00 + svc_boardid()
EndProcedure

Main()
"""


class Fail(d.GateFail):
    pass


def check(ok: bool, what: str, notes: list) -> None:
    if not ok:
        raise Fail(what)
    notes.append(what)


def overlay(override: dict, work: pathlib.Path) -> pathlib.Path:
    """A private copy of the four source trees with `override` applied, so a
    build never touches the real tree and a mutant never races another."""
    tree = work / "tree"
    if tree.exists():
        shutil.rmtree(tree)
    for top in TREES:
        shutil.copytree(ROOT / top, tree / top,
                        ignore=shutil.ignore_patterns("Examples", "Tests", "*.img", "*.bin"))
    for rel, text in override.items():
        (tree / rel).write_bytes(text.encode("utf-8"))
    return tree


def compile_(cc: str, tree: pathlib.Path, src: str, target: str, args: list,
             out: pathlib.Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([cc, "--compile", src, "-t", target, *args, "-o", str(out)],
                       cwd=str(tree), env=dict(os.environ, PMF_ROOT=str(tree)),
                       capture_output=True, text=True)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout or not out.exists():
        tail = "\n".join(l for l in r.stdout.splitlines()
                         if "DEBUG" not in l and "TRACE" not in l)[-2500:]
        raise Fail("%s would not build for -t %s:\n%s" % (src, target, tail))


def header(img: pathlib.Path) -> tuple:
    h = pathlib.Path(str(img) + ".pmf").read_bytes()[:128]
    load, entry = struct.unpack_from("<QQ", h, 16)
    stack = struct.unpack_from("<Q", h, 104)[0]
    return load, entry, stack


def symbols(img: pathlib.Path) -> dict:
    out = {}
    for line in pathlib.Path(str(img) + ".sym").read_text(
            encoding="utf-8", errors="replace").splitlines():
        k, _, v = line.strip().partition("=")
        if v.lstrip("-").isdigit():
            out[k.lower()] = int(v)
    return out


def procs_of(img: pathlib.Path, load: int) -> dict:
    procs = {}
    for line in pathlib.Path(str(img) + ".dbg").read_text(
            encoding="utf-8", errors="replace").splitlines():
        f = line.split("|")
        if len(f) >= 3 and f[0] == "1" and f[1].isdigit():
            procs[f[2].lower()] = load + int(f[1])
    return procs


WRECK_SP = 0x1230                  # where the wrecker leaves sp
WRECK_WATCH = (0x1000, 0x1240)     # a monitor that did not restore sp writes here


def raw_sp_wrecker(el: int) -> bytes:
    """movz x1,#0x1230 ; [msr vbar_el3, x1] ; add sp, x1, #0 ; movz x0,#0x77 ; ret

    A payload that breaks the callee-saved contract twice over: it points the
    vectors at nonsense and returns with sp destroyed. The monitor must come
    back whole anyway - its sp from gSp, its vectors from HwPayloadReturned."""
    words = [0xD2800000 | (WRECK_SP << 5) | 1]
    if el == 12:
        words.append(0xD51EC001)                         # msr vbar_el3, x1
    words += [0x9100003F, 0xD2800000 | (0x77 << 5) | 0, 0xD65F03C0]
    return b"".join(struct.pack("<I", w) for w in words)


class SysRegs:
    """The system-register file the entry path reaches, answered above
    step() as a64_interp.py requires."""

    VBAR_EL3 = (1 << 14) | (6 << 11) | (12 << 7)                 # S3_6_C12_C0_0
    DAIF = (1 << 14) | (3 << 11) | (4 << 7) | (2 << 3) | 1      # S3_3_C4_C2_1 (op0 3 is bit 14 = 1)
    CURRENTEL = (1 << 14) | (0 << 11) | (4 << 7) | (2 << 3) | 2  # S3_0_C4_C2_2

    def __init__(self, el: int):
        # DAIF starts UNMASKED, so a path that masks and forgets to put it
        # back is visible (every board here runs masked; the entry must not
        # care which).
        self.regs = {self.CURRENTEL: el, self.DAIF: 0}
        self.writes = []

    def hook(self, cpu, plain):
        def step():
            ins = cpu.fetch(cpu.pc)
            if (ins & 0xFFF00000) in (0xD5100000, 0xD5300000):
                key = (ins >> 5) & 0x7FFF
                rt = ins & 31
                if ins & 0x00200000:
                    if rt != 31:
                        cpu.x[rt] = self.regs.get(key, 0)
                else:
                    v = 0 if rt == 31 else cpu.x[rt]
                    self.regs[key] = v
                    self.writes.append(key)
                cpu.pc += 4
                return
            if (ins & 0xFFFFF0FF) == 0xD50340DF:                 # msr daifset, #imm
                self.regs[self.DAIF] |= ((ins >> 8) & 15) << 6
                cpu.pc += 4
                return
            if (ins & 0xFFFFF0FF) == 0xD50340FF:                 # msr daifclr, #imm
                self.regs[self.DAIF] &= ~(((ins >> 8) & 15) << 6)
                cpu.pc += 4
                return
            plain()
        return step


def gate_board(cc: str, target: str, override: dict, work: pathlib.Path) -> list:
    src, args, pload, pstack, el, _ = BOARDS[target]
    # ALWAYS a private copy, the unmutated run too: a board whose source
    # carries `; pmf:build` has its build count raised by every successful
    # compile, and a gate must not edit the tree it is judging.
    tree = overlay(override, work)
    notes = []
    mon = work / ("%s.img" % target)
    compile_(cc, tree, src, target, args, mon)
    probe_src = work / "payload_entry_probe.pi4"
    abi = (tree / "Anvil/Hal/abi.pbi").read_text(encoding="utf-8")
    ver = (tree / "Anvil/Hal/abi_version.pbi").read_text(encoding="utf-8")
    magic = d.const_in(abi, "#SVC_MAGIC", "abi.pbi")
    hdr = 8 * d.const_in(abi, "#SVC_HDR_WORDS", "abi.pbi")
    slot = d.const_in(abi, "#SLOT_BOARDID", "abi.pbi") if "#SLOT_BOARDID" in abi else None
    if slot is None:
        base = d.const_in(abi, "#SVC_BASE_CORE", "abi.pbi")
        slot = base + 2          # BuildServiceTable: core + 2 = @SvcBoardId
    board_id = d.const_in((tree / BOARD_ID_SOURCE[target]).read_text(encoding="utf-8"),
                          "#SVC_BOARD_ID", BOARD_ID_SOURCE[target])
    probe_src.write_text(("#MAGIC = $%X\n#HDR = %d\n#SLOT = %d\n" % (magic, hdr, slot)) + PROBE,
                         encoding="utf-8")
    probe = work / "probe.img"
    compile_(cc, ROOT, str(probe_src), target,
             ["--load-addr", hex(pload), "--stack-addr", hex(pstack),
              "--entry-returns", "--wants-services"], probe)

    load, entry, mstack = header(mon)
    procs = procs_of(mon, load)
    sym = symbols(mon)
    for need in ("buildservicetable", "svctableaddr", "runat", "svcboardid"):
        if need not in procs:
            raise Fail("the %s monitor has no procedure %s" % (target, need))
    for need in ("global_ggox0", "global_ggorc", "global_gsp"):
        if need not in sym:
            raise Fail("the %s monitor has no global %s" % (target, need))

    driver_sp = mstack - DRIVER_STACK_GAP
    m = d.Machine(mon, procs, lambda a, s, v: 0, load=load, stack=driver_sp)
    regs = SysRegs(el)
    m.step = regs.hook(m.cpu, m.step)
    # DAIF at the instant the board's HwPayloadReturned() is entered: the
    # vectors may still be the payload's, so every interrupt must be masked.
    daif_at_return = []
    # Absent only when nothing reaches it - an entry that bypasses
    # PayloadCall - and the behavioural checks below say so first.
    watched, inner = procs.get("hwpayloadreturned", -1), m.step

    def watch():
        if m.cpu.pc == watched:
            daif_at_return.append(regs.regs[SysRegs.DAIF])
        inner()
    m.step = watch
    for i, b in enumerate(probe.read_bytes()):
        m.cpu.memory[pload + i] = b

    def poke64(name, v):
        m.poke(sym[name], struct.pack("<Q", v & (1 << 64) - 1))

    def peek64(name):
        return struct.unpack("<Q", m.peek(sym[name], 8))[0]

    m.call("BuildServiceTable")
    table = m.call("SvcTableAddr")
    check(table != 0 and (struct.unpack("<Q", m.peek(table, 8))[0] & 0xFFFFFFFF) == magic,
          "%s: the monitor's own BuildServiceTable filled a table with the ABI magic" % target,
          notes)
    check(struct.unpack("<Q", m.peek(table + hdr + slot * 8, 8))[0] == procs["svcboardid"],
          "%s: the probe's slot is the monitor's SvcBoardId" % target, notes)

    def enter(addr, what):
        poke64("global_ggox0", table)
        poke64("global_ggorc", 0x5EED)
        for i in range(1, 19):
            m.cpu.x[i] = POISON | i
        daif_before = regs.regs[SysRegs.DAIF]
        c = m.cpu
        c.pc = procs["runat"]
        c.sp = driver_sp
        c.x[30] = RETURN
        c.x[0] = addr
        n = 0
        while c.pc != RETURN:
            n += 1
            if n > 5_000_000:
                raise Fail("%s: RunAt never came back from the %s" % (target, what))
            m.step()
        after = (c.sp, regs.regs[SysRegs.DAIF], peek64("global_ggox0"))

        def rest():
            check(after[0] == driver_sp,
                  "%s: RunAt returned to its caller with the caller's sp after the %s" % (target, what),
                  notes)
            check(after[1] == daif_before,
                  "%s: DAIF is what it was before the %s" % (target, what), notes)
            check(after[2] == 0,
                  "%s: gGoX0 is cleared on the way out of the %s" % (target, what), notes)
        return peek64("global_ggorc"), rest

    rc, rest = enter(pload, "compiled probe")
    got = [struct.unpack("<Q", m.peek(symbols(probe)["global_gr%d" % i], 8))[0] for i in range(8)]
    check(got[0] == table, "%s: the probe was entered with x0 = the table (%#x)" % (target, table),
          notes)
    check(all(v == 0 for v in got[1:]),
          "%s: the probe was entered with x1..x7 = 0 (poisoned before RunAt)" % target, notes)
    check(rc == 0x5A00 + board_id,
          "%s: gGoRc = $5A00 + SvcBoardId() = %#x, the payload's own answer through the real slot"
          % (target, 0x5A00 + board_id), notes)
    rest()
    check(daif_at_return and all(v == 0x3C0 for v in daif_at_return),
          "%s: every interrupt was masked when HwPayloadReturned began (DAIF %s), because the "
          "vectors may still be the payload's" % (target, [hex(v) for v in daif_at_return]), notes)
    wreck = pload + 0x100000
    m.poke(wreck, raw_sp_wrecker(el))
    m.poke(WRECK_WATCH[0], bytes([0xA5]) * (WRECK_WATCH[1] - WRECK_WATCH[0]))
    rc, rest = enter(wreck, "payload that destroys sp")
    check(rc == 0x77, "%s: gGoRc = 0x77 from a payload that returned with sp destroyed" % target,
          notes)
    rest()
    check(m.peek(WRECK_WATCH[0], WRECK_WATCH[1] - WRECK_WATCH[0])
          == bytes([0xA5]) * (WRECK_WATCH[1] - WRECK_WATCH[0]),
          "%s: nothing was written through the payload's destroyed sp - the monitor ran "
          "on its own stack as soon as it was back" % target, notes)
    if el == 12:
        check(regs.regs.get(SysRegs.VBAR_EL3, 0) not in (0, WRECK_SP),
              "%s: VBAR_EL3 is the monitor's vectors again (%#x), not the payload's %#x"
              % (target, regs.regs.get(SysRegs.VBAR_EL3, 0), WRECK_SP), notes)
    return notes


MUTANTS = [
    ("Anvil/Kernel/payload_call.pbi", "x0 = the entry address (the Pi 3's old defect)",
     "    adrp x0, global_ggox0\n    add  x0, x0, #:lo12:global_ggox0\n    ldr  x0, [x0]\n",
     "    mov  x0, x9\n", None),
    ("Anvil/Kernel/payload_call.pbi", "x5..x7 not cleared",
     "    movz x5, #0\n    movz x6, #0\n    movz x7, #0\n", "", None),
    ("Anvil/Kernel/payload_call.pbi", "the monitor's sp not restored",
     "    ldr  x11, [x10]\n    mov  sp, x11\n", "    ldr  x11, [x10]\n", None),
    ("Anvil/Kernel/payload_call.pbi", "DAIF not restored",
     "    msr  daif, x11\n", "", None),
    ("Anvil/Kernel/payload_call.pbi", "DAIF restored BEFORE the vectors are reinstalled",
     "    msr  daifset, #15\n", "", None),
    ("RaspberryPi3/Board/hw_board.pi3", "the Pi 3's old `blr x0` entry",
     "Procedure Pi3EnterPayload(a.i)\n  PayloadEnter(a)\nEndProcedure",
     "Procedure Pi3EnterPayload(a.i)\n  ASM\n    blr x0\n  EndASM\nEndProcedure", "pi3"),
    ("ArduinoQ/Board/qstubs_q.unoq", "the UNO Q's old QCall(a, 0, 0, 0, 0, 0) entry",
     "  PayloadEnter(a)\nEndProcedure", "  QCall(a, 0, 0, 0, 0, 0)\nEndProcedure", "unoq"),
]


def text_of(rel: str) -> str:
    return (ROOT / rel).read_bytes().decode("utf-8").replace("\r\n", "\n")


def run_all(cc: str, work: pathlib.Path, override: dict, targets) -> list:
    notes = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(targets)) as ex:
        futs = {t: ex.submit(gate_board, cc, t, override, work / t) for t in targets}
        for t in targets:
            notes += futs[t].result()
    return notes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compiler", required=True)
    ap.add_argument("--mutate", action="store_true")
    ap.add_argument("--work", default=str(ROOT / "_work" / "payload_entry"))
    a = ap.parse_args()
    work = pathlib.Path(a.work)
    try:
        notes = run_all(a.compiler, work / "real", {}, list(BOARDS))
    except d.GateFail as exc:
        print("FAIL: %s" % exc)
        return 1
    for n in notes:
        print("  ok  %s" % n)
    print("PASS %d checks on %d boards" % (len(notes), len(BOARDS)))
    if not a.mutate:
        return 0
    survived = 0
    for i, (rel, why, old, new, only) in enumerate(MUTANTS):
        text = text_of(rel)
        if text.count(old) != 1:
            print("  %2d  SURVIVED  %s: %s (the edit matched %d times)" % (i, rel, why, text.count(old)))
            survived += 1
            continue
        targets = [only] if only else list(BOARDS)
        try:
            run_all(a.compiler, work / ("m%02d" % i), {rel: text.replace(old, new)}, targets)
        except d.GateFail as exc:
            print("  %2d  KILLED    %s: %s (%s)" % (i, rel, why, str(exc).replace("\n", " ")[:120]))
            continue
        except Exception as exc:                          # noqa: BLE001
            print("  %2d  KILLED    %s: %s (%r)" % (i, rel, why, str(exc)[:120]))
            continue
        print("  %2d  SURVIVED  %s: %s" % (i, rel, why))
        survived += 1
    print("mutations: %d killed, %d survived" % (len(MUTANTS) - survived, survived))
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Execute the Pi 4 mass-storage block-range transport against fakes.

Two production procedures carry every byte between the filesystems and the
USB stick, and until 2026-09-17 both were shaped by one block per command
(forum 895):

  msc_BlockIo (RaspberryPi4/Lib/usbmsc.pi4)  READ (10) / WRITE (10) of a run
              of blocks, cut into commands of #MSC_XFER_BLOCKS, the data phase
              straight to the caller's memory when it starts on a cache line
              and the controller can reach it, bounced otherwise, and a
              command that moved less than it asked for refused.
  xh_Bulk     (RaspberryPi4/Lib/xhci.pi4)    one bulk transfer as ONE chained
              transfer descriptor: cut at 64 KiB address boundaries, CHAIN on
              all but the last TRB, IOC on the last, TD Size counting down and
              capped at 31, the head written with its cycle bit inverted and
              handed over last, and the bytes moved worked out from whichever
              TRB the completion event names.

The production bodies are extracted verbatim and compiled with fakes for what
sits under them (the Bulk-Only exchange, the ring, the event wait), then run
in tools/a64/a64_interp.py. Nothing here touches hardware; the board proves
the speed. What this proves is the arithmetic and the refusals, and that each
mutant below is caught.

One substitution is made on purpose and checked separately: the probe runs
msc_BlockIo with #MSC_XFER_BLOCKS = 4 so that chunking is exercised in a few
thousand emitted instructions instead of megabytes of fake medium. The real
value is asserted against the transfer limit it depends on.

Usage:
  PMF_COMPILER=<PureMetalForge.exe> python tools/usb_bulk_range_emitted_check.py
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
USBMSC = ROOT / "RaspberryPi4" / "Lib" / "usbmsc.pi4"
XHCI = ROOT / "RaspberryPi4" / "Lib" / "xhci.pi4"
LOCAL_INTERP = ROOT / "tools" / "a64" / "a64_interp.py"

PROBE_XFER_BLOCKS = 4


def procedure(source: str, name: str) -> str:
    starts = (f"Procedure {name}(", f"Procedure.i {name}(")
    lines = source.splitlines()
    first = next((i for i, line in enumerate(lines) if line.startswith(starts)), None)
    if first is None:
        raise SystemExit(f"usb bulk range gate: production procedure {name} not found")
    last = next((i for i in range(first + 1, len(lines)) if lines[i] == "EndProcedure"), None)
    if last is None:
        raise SystemExit(f"usb bulk range gate: production procedure {name} has no end")
    return "\n".join(lines[first : last + 1])


def constants(source: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in source.splitlines():
        m = re.match(r"^#(\w+)\s*=\s*([^;]+?)\s*(;.*)?$", line)
        if m:
            found[m.group(1)] = m.group(2)
    return found


def number(text: str) -> int:
    text = text.strip()
    return int(text[1:], 16) if text.startswith("$") else int(text)


def replace_once(source: str, old: str, new: str, label: str) -> str:
    if source.count(old) != 1:
        raise SystemExit(
            f"usb bulk range gate: mutant {label} expected one source match, "
            f"found {source.count(old)}"
        )
    return source.replace(old, new, 1)


def audit_constants(msc: str, xhci: str) -> None:
    m = constants(msc)
    x = constants(xhci)
    blocks = number(m["MSC_XFER_BLOCKS"])
    xfer = number(m["MSC_XFER_BYTES"])
    if blocks * number(m["MSC_BLOCK_BYTES"]) != xfer:
        raise SystemExit("usb bulk range gate: #MSC_XFER_BYTES is not #MSC_XFER_BLOCKS blocks")
    if xfer > number(x["XHCI_BULK_MAX"]):
        raise SystemExit("usb bulk range gate: one command's data phase exceeds #XHCI_BULK_MAX")
    if blocks > 0xFFFF:
        raise SystemExit("usb bulk range gate: READ (10) carries a 16-bit block count")
    if number(m["MSC_POOL_USED"]) != number(m["MSC_OFF_BOUNCE"]) + xfer:
        raise SystemExit("usb bulk range gate: the bounce buffer is not one whole command")
    if number(x["XHCI_TRB_BUF"]) != 0x10000:
        raise SystemExit("usb bulk range gate: a TRB buffer is 64 KiB (xHCI 1.2 section 6.4.1)")


PRELUDE_MSC = r'''
#MSC_BLOCK_BYTES = 512
#MSC_DIR_IN = $80
#SCSI_READ10 = $28
#SCSI_WRITE10 = $2A
#MSC_ERR_ARG = -12
#MSC_ERR_NOT_READY = -1
#MSC_ERR_RANGE = -13
#MSC_ERR_SHORT = -14
#MSC_ALIGN = 64
#MSC_OFF_BOUNCE = 640
#MSC_XFER_BLOCKS = PROBE_XFER_BLOCKS
#MSC_POOL_BYTES = 8192
#GATE_DMA_LIMIT = GATE_DMA_LIMIT_VALUE
#GATE_MAX_CMDS = 64

Global Dim msc_pool.a[#MSC_POOL_BYTES]
Global msc_base.i = 0
Global msc_err.i = 0
Global msc_ready.i = 1
Global msc_blocks.i = 1000
Global msc_lastData.i = 0
Global msc_lastResidue.i = 0

; Reads come from a pattern; writes land in blocks 490..521 only.
Global Dim gateDisk.a[32 * 512]
Global Dim gateBuf.a[64 * 512 + 128]
Global Dim gateCmdOp.i[#GATE_MAX_CMDS]
Global Dim gateCmdLba.i[#GATE_MAX_CMDS]
Global Dim gateCmdCount.i[#GATE_MAX_CMDS]
Global Dim gateCmdBuf.i[#GATE_MAX_CMDS]
Global gateCmds.i
Global gateShortAt.i = -1
Global gateResidueAt.i = -1

Procedure MscBuffers()
  If msc_base <> 0
    ProcedureReturn
  EndIf
  msc_base = (@msc_pool[0] + (#MSC_ALIGN - 1)) / #MSC_ALIGN
  msc_base = msc_base * #MSC_ALIGN
EndProcedure

Procedure.i msc_Bounce()
  MscBuffers()
  ProcedureReturn msc_base + #MSC_OFF_BOUNCE
EndProcedure

Procedure.i msc_Fail(code.i)
  msc_err = code
  ProcedureReturn 0
EndProcedure

Procedure xh_Trace(p.i)
EndProcedure

Procedure msc_PutBe32(*p, off.i, v.i)
  PokeA(*p + off + 0, (v >> 24) & $FF)
  PokeA(*p + off + 1, (v >> 16) & $FF)
  PokeA(*p + off + 2, (v >> 8) & $FF)
  PokeA(*p + off + 3, v & $FF)
EndProcedure

; The controller can reach memory below #GATE_DMA_LIMIT only.
Procedure.i PcieDmaOk(addr.i, len.i)
  If len <= 0 Or addr < 0 Or addr + len > #GATE_DMA_LIMIT
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i GatePattern(lba.i, off.i)
  ProcedureReturn (lba * 7 + (off / 512) * 7 + (off % 512) * 3) & $FF
EndProcedure

; THE FAKE DEVICE. Decodes the CDB the production code built, records it,
; and moves blocks between *buf and gateDisk - so an LBA or count encoded
; wrongly moves the wrong bytes, not merely a wrong counter.
Procedure.i msc_Command(*cdb, cdbLen.i, dir.i, *buf, len.i)
  Define op.i
  Define lba.i
  Define n.i
  Define i.i
  op = PeekA(*cdb)
  lba = (PeekA(*cdb + 2) << 24) | (PeekA(*cdb + 3) << 16) | (PeekA(*cdb + 4) << 8) | PeekA(*cdb + 5)
  n = (PeekA(*cdb + 7) << 8) | PeekA(*cdb + 8)
  If gateCmds < #GATE_MAX_CMDS
    gateCmdOp[gateCmds] = op
    gateCmdLba[gateCmds] = lba
    gateCmdCount[gateCmds] = n
    gateCmdBuf[gateCmds] = *buf
  EndIf
  gateCmds = gateCmds + 1
  If gateCmds > 50
    ProcedureReturn msc_Fail(-97)
  EndIf
  If cdbLen <> 10 Or len <> n * 512
    ProcedureReturn msc_Fail(-99)
  EndIf
  If op = $28 And dir <> $80 : ProcedureReturn msc_Fail(-98) : EndIf
  If op = $2A And dir <> 0 : ProcedureReturn msc_Fail(-98) : EndIf
  i = 0
  While i < len
    If op = $28
      PokeA(*buf + i, GatePattern(lba, i))
    ElseIf lba >= 490 And lba + n <= 522
      gateDisk[(lba - 490) * 512 + i] = PeekA(*buf + i)
    EndIf
    i = i + 1
  Wend
  msc_lastData = len
  msc_lastResidue = 0
  If gateCmds - 1 = gateShortAt
    msc_lastData = len - 512
  EndIf
  If gateCmds - 1 = gateResidueAt
    msc_lastResidue = 512
  EndIf
  ProcedureReturn 1
EndProcedure

; The caller's memory holds what the medium holds: the read pattern, or for
; the write window, what the fake device stored.
Procedure.i GateSame(*mem, lba.i, count.i)
  Define i.i
  Define want.i
  i = 0
  While i < count * 512
    If lba >= 490 And lba + count <= 522
      want = gateDisk[(lba - 490) * 512 + i]
    Else
      want = GatePattern(lba, i)
    EndIf
    If PeekA(*mem + i) <> want
      ProcedureReturn 0
    EndIf
    i = i + 1
  Wend
  ProcedureReturn 1
EndProcedure

Procedure GateReset()
  gateCmds = 0
  gateShortAt = -1
  gateResidueAt = -1
  msc_err = 0
EndProcedure
'''


MAIN_MSC = r'''
Procedure.i Main()
  Define *aligned
  Define i.i
  *aligned = ((@gateBuf[0] + 63) / 64) * 64

  ; 1. Eleven blocks into an aligned buffer: commands of 4, 4, 3 at the
  ;    right LBAs, the data phase straight into the caller's memory.
  GateReset()
  If MscReadBlocks(100, 11, *aligned) <> 1 : ProcedureReturn 1 : EndIf
  If gateCmds <> 3 : ProcedureReturn 2 : EndIf
  If gateCmdCount[0] <> 4 Or gateCmdCount[1] <> 4 Or gateCmdCount[2] <> 3 : ProcedureReturn 3 : EndIf
  If gateCmdLba[0] <> 100 Or gateCmdLba[1] <> 104 Or gateCmdLba[2] <> 108 : ProcedureReturn 4 : EndIf
  If gateCmdOp[0] <> $28 : ProcedureReturn 5 : EndIf
  If gateCmdBuf[0] <> *aligned Or gateCmdBuf[1] <> *aligned + 2048 : ProcedureReturn 6 : EndIf
  If GateSame(*aligned, 100, 11) = 0 : ProcedureReturn 7 : EndIf

  ; 2. The same read one byte off a cache line: bounced, bytes identical.
  GateReset()
  If MscReadBlocks(300, 6, *aligned + 1) <> 1 : ProcedureReturn 10 : EndIf
  If gateCmds <> 2 : ProcedureReturn 11 : EndIf
  If gateCmdBuf[0] <> msc_Bounce() Or gateCmdBuf[1] <> msc_Bounce() : ProcedureReturn 12 : EndIf
  If GateSame(*aligned + 1, 300, 6) = 0 : ProcedureReturn 13 : EndIf

  ; 3. A write from an odd address goes out through the bounce, whole.
  i = 0
  While i < 5 * 512
    PokeA(*aligned + 3 + i, (i * 11 + 5) & $FF)
    i = i + 1
  Wend
  GateReset()
  If MscWriteBlocks(500, 5, *aligned + 3) <> 1 : ProcedureReturn 20 : EndIf
  If gateCmds <> 2 Or gateCmdOp[0] <> $2A Or gateCmdCount[1] <> 1 Or gateCmdLba[1] <> 504 : ProcedureReturn 21 : EndIf
  If GateSame(*aligned + 3, 500, 5) = 0 : ProcedureReturn 22 : EndIf

  ; 4. A command that moved less, or reported a residue, fails the run.
  GateReset()
  gateShortAt = 1
  If MscReadBlocks(10, 8, *aligned) <> 0 Or msc_err <> #MSC_ERR_SHORT : ProcedureReturn 30 : EndIf
  If gateCmds <> 2 : ProcedureReturn 31 : EndIf
  GateReset()
  gateResidueAt = 0
  If MscWriteBlocks(10, 2, *aligned) <> 0 Or msc_err <> #MSC_ERR_SHORT : ProcedureReturn 32 : EndIf

  ; 5. Range and argument refusals issue no command at all.
  GateReset()
  If MscReadBlocks(998, 3, *aligned) <> 0 Or msc_err <> #MSC_ERR_RANGE Or gateCmds <> 0 : ProcedureReturn 40 : EndIf
  ; A count whose sum with the LBA wraps negative must still be refused.
  If MscReadBlocks(500, $7FFFFFFFFFFFFFFF, *aligned) <> 0 Or msc_err <> #MSC_ERR_RANGE Or gateCmds <> 0 : ProcedureReturn 41 : EndIf
  If MscReadBlocks(5, 0, *aligned) <> 0 Or msc_err <> #MSC_ERR_ARG Or gateCmds <> 0 : ProcedureReturn 42 : EndIf
  If MscReadBlock(999, *aligned) <> 1 Or gateCmds <> 1 Or GateSame(*aligned, 999, 1) = 0 : ProcedureReturn 43 : EndIf
  ProcedureReturn 0
EndProcedure
'''


PRELUDE_XHCI = r'''
#XHCI_TRB_BYTES = 16
#XHCI_TRB_CYCLE = $0001
#XHCI_TRB_ISP = $0004
#XHCI_TRB_CHAIN = $0010
#XHCI_TRB_IOC = $0020
#XHCI_TRB_NORMAL = 1
#XHCI_TRB_TRANSFER = 32
#XHCI_RING_BULK_OUT = 9
#XHCI_RING_BULK_IN = 10
#XHCI_RING_N = 11
#XHCI_ERR_NO_EPS = 36
#XHCI_ERR_ARG = 30
#XHCI_ERR_DMA_RANGE = 10
#XHCI_ERR_EP_HALTED = 50
#XHCI_ERR_STALL = 51
#XHCI_ERR_XFER = 52
#XHCI_COMP_SUCCESS = 1
#XHCI_COMP_SHORT_TX = 13
#XHCI_COMP_STALL = 6
#XHCI_EP_STATE_HALTED = 2
#XHCI_TMO_EVENT_MS = 5000
#XHCI_BULK_FLOOR_KBPS = 1024
#XHCI_TMO_BULK_MAX_MS = 30000
#XHCI_BULK_MAX = $100000
#XHCI_TRB_BUF = $10000

Global xh_mscSlot.i = 3
Global xh_mpsOut.i = 1024
Global xh_mpsIn.i = 1024
Global xh_err.i
Global xh_lastComp.i
Global xh_lastResid.i
Global xh_evTrb.i
Global Dim xh_ringBase.i[#XHCI_RING_N]
Global Dim xh_ringEnq.i[#XHCI_RING_N]
Global Dim xh_ringCycle.i[#XHCI_RING_N]
Global Dim gateRing.l[256]
Global gateWaitLo.i
Global gateWaitHi.i
Global gateEventIndex.i       ; which TRB of the descriptor the event names
Global gateEventComp.i
Global gateEventResid.i
Global gateDoorbells.i
Global gateOwnedEarly.i       ; the head was owned before the doorbell
Global gateWaitMs.i           ; the budget xh_Bulk asked the wait for
Global xh_hz.i = 54000000

Procedure.i xh_Fail(code.i)
  xh_err = code
  ProcedureReturn 0
EndProcedure

Procedure.i PcieDmaOk(addr.i, len.i)
  If len <= 0 Or addr < 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure xh_Clean(addr.i, len.i)
EndProcedure

Procedure xh_RingRoom(r.i, n.i)
EndProcedure

Procedure.i xh_TrbAddr(r.i, idx.i)
  ProcedureReturn xh_ringBase[r] + (idx * #XHCI_TRB_BYTES)
EndProcedure

Procedure.i xh_QueueTrbCy(r.i, f0.i, f1.i, f2.i, f3.i, cyc.i)
  Define at.i
  at = xh_TrbAddr(r, xh_ringEnq[r])
  PokeN(at + 0, f0 & $FFFFFFFF)
  PokeN(at + 4, f1 & $FFFFFFFF)
  PokeN(at + 8, f2 & $FFFFFFFF)
  PokeN(at + 12, (f3 | (cyc & 1)) & $FFFFFFFF)
  ; A controller that owned the head now would run a half-built TD.
  If (PeekN(xh_ringBase[r] + xh_ringEnq[r] * 0 + 12) & 1) = xh_ringCycle[r]
    If xh_ringEnq[r] > 0
      gateOwnedEarly = gateOwnedEarly + 1
    EndIf
  EndIf
  xh_ringEnq[r] = xh_ringEnq[r] + 1
  ProcedureReturn at
EndProcedure

Procedure xh_Doorbell(slot.i, value.i)
  gateDoorbells = gateDoorbells + 1
EndProcedure

Procedure.i xh_WaitEventFor(expect.i, wantLo.i, wantHi.i, ms.i)
  gateWaitLo = wantLo
  gateWaitHi = wantHi
  gateWaitMs = ms
  xh_evTrb = wantLo + gateEventIndex * #XHCI_TRB_BYTES
  If xh_evTrb < wantLo Or xh_evTrb > wantHi
    ProcedureReturn xh_Fail(99)
  EndIf
  xh_lastComp = gateEventComp
  xh_lastResid = gateEventResid
  ProcedureReturn 1
EndProcedure

Procedure.i xh_EpStateAt(slot.i, dci.i)
  ProcedureReturn 1
EndProcedure

Procedure.i xh_ClearHalt(slot.i, ring.i, dci.i)
  ProcedureReturn 1
EndProcedure

Procedure GateReset(eventIndex.i, comp.i, resid.i)
  xh_ringBase[#XHCI_RING_BULK_IN] = @gateRing[0]
  xh_ringEnq[#XHCI_RING_BULK_IN] = 0
  xh_ringCycle[#XHCI_RING_BULK_IN] = 1
  gateEventIndex = eventIndex
  gateEventComp = comp
  gateEventResid = resid
  gateDoorbells = 0
  gateOwnedEarly = 0
EndProcedure

Procedure.i GateTrbLen(k.i)
  ProcedureReturn PeekN(@gateRing[0] + k * 16 + 8) & $1FFFF
EndProcedure

Procedure.i GateTdSize(k.i)
  ProcedureReturn (PeekN(@gateRing[0] + k * 16 + 8) >> 17) & $1F
EndProcedure

Procedure.i GateFlags(k.i)
  ProcedureReturn PeekN(@gateRing[0] + k * 16 + 12)
EndProcedure

Procedure.i GateAddr(k.i)
  ProcedureReturn PeekN(@gateRing[0] + k * 16) | (PeekN(@gateRing[0] + k * 16 + 4) << 32)
EndProcedure
'''


MAIN_XHCI = r'''
Procedure.i Main()
  Define n.i
  Define k.i

  ; 1. 70,000 bytes starting 100 bytes below a 64 KiB boundary: three TRBs
  ;    of 100, 65536 and 4364, at the right addresses.
  GateReset(2, #XHCI_COMP_SUCCESS, 0)
  n = xh_Bulk(#XHCI_RING_BULK_IN, 5, $4000FF9C, 70000)
  If n <> 70000 : ProcedureReturn 1 : EndIf
  If xh_ringEnq[#XHCI_RING_BULK_IN] <> 3 : ProcedureReturn 2 : EndIf
  If GateTrbLen(0) <> 100 Or GateTrbLen(1) <> 65536 Or GateTrbLen(2) <> 4364 : ProcedureReturn 3 : EndIf
  If GateAddr(0) <> $4000FF9C Or GateAddr(1) <> $40010000 Or GateAddr(2) <> $40020000 : ProcedureReturn 4 : EndIf
  ; CHAIN on all but the last, IOC on the last only, all Normal TRBs.
  If (GateFlags(0) & #XHCI_TRB_CHAIN) = 0 Or (GateFlags(1) & #XHCI_TRB_CHAIN) = 0 : ProcedureReturn 5 : EndIf
  If (GateFlags(2) & #XHCI_TRB_CHAIN) <> 0 Or (GateFlags(2) & #XHCI_TRB_IOC) = 0 : ProcedureReturn 6 : EndIf
  If (GateFlags(0) & #XHCI_TRB_IOC) <> 0 Or (GateFlags(1) & #XHCI_TRB_IOC) <> 0 : ProcedureReturn 7 : EndIf
  If ((GateFlags(1) >> 10) & $3F) <> #XHCI_TRB_NORMAL : ProcedureReturn 8 : EndIf
  ; TD Size: 69 packets in all; after TRB 0 still 69 (capped 31), after
  ; TRB 1 69 - 64 = 5, and 0 on the last.
  If GateTdSize(0) <> 31 Or GateTdSize(1) <> 5 Or GateTdSize(2) <> 0 : ProcedureReturn 9 : EndIf
  ; The wait covers exactly this descriptor.
  If gateWaitLo <> @gateRing[0] Or gateWaitHi <> @gateRing[0] + 32 : ProcedureReturn 10 : EndIf
  ; The head carries the ring's cycle once handed over, and was not owned
  ; while the rest was being written.
  If (GateFlags(0) & 1) <> 1 Or (GateFlags(1) & 1) <> 1 Or gateOwnedEarly <> 0 : ProcedureReturn 11 : EndIf
  If gateDoorbells <> 1 : ProcedureReturn 12 : EndIf

  ; 2. A short packet on the middle TRB ends the descriptor there.
  GateReset(1, #XHCI_COMP_SHORT_TX, 1000)
  n = xh_Bulk(#XHCI_RING_BULK_IN, 5, $4000FF9C, 70000)
  If n <> 100 + 65536 - 1000 : ProcedureReturn 20 : EndIf
  GateReset(2, #XHCI_COMP_SHORT_TX, 64)
  n = xh_Bulk(#XHCI_RING_BULK_IN, 5, $4000FF9C, 70000)
  If n <> 70000 - 64 : ProcedureReturn 21 : EndIf

  ; 3. A whole megabyte on a boundary is sixteen full TRBs; one more byte
  ;    is refused, and so is nothing.
  GateReset(15, #XHCI_COMP_SUCCESS, 0)
  n = xh_Bulk(#XHCI_RING_BULK_IN, 5, $40000000, $100000)
  If n <> $100000 Or xh_ringEnq[#XHCI_RING_BULK_IN] <> 16 : ProcedureReturn 30 : EndIf
  k = 0
  While k < 16
    If GateTrbLen(k) <> 65536 : ProcedureReturn 31 : EndIf
    k = k + 1
  Wend
  GateReset(0, #XHCI_COMP_SUCCESS, 0)
  If xh_Bulk(#XHCI_RING_BULK_IN, 5, $40000000, $100001) <> 0 Or xh_err <> #XHCI_ERR_ARG : ProcedureReturn 32 : EndIf
  If xh_Bulk(#XHCI_RING_BULK_IN, 5, $40000000, 0) <> 0 Or xh_err <> #XHCI_ERR_ARG : ProcedureReturn 33 : EndIf
  If xh_ringEnq[#XHCI_RING_BULK_IN] <> 0 Or gateDoorbells <> 0 : ProcedureReturn 34 : EndIf

  ; 4. One small transfer - a status wrapper - is still one TRB with IOC.
  GateReset(0, #XHCI_COMP_SHORT_TX, 51)
  n = xh_Bulk(#XHCI_RING_BULK_IN, 5, $08200040, 64)
  If n <> 13 Or xh_ringEnq[#XHCI_RING_BULK_IN] <> 1 : ProcedureReturn 40 : EndIf
  If (GateFlags(0) & #XHCI_TRB_IOC) = 0 Or (GateFlags(0) & #XHCI_TRB_CHAIN) <> 0 Or GateTdSize(0) <> 0 : ProcedureReturn 41 : EndIf
  ; And the budget that 64-byte wrapper was given is the fixed part alone,
  ; to the millisecond: a status wrapper must not inherit a data phase's
  ; patience, or a wedged device is waited on for half a minute.
  If gateWaitMs <> #XHCI_TMO_EVENT_MS : ProcedureReturn 42 : EndIf

  ; 5. THE BUDGET GROWS WITH THE TRANSFER AND STOPS AT LINUX'S CEILING.
  ;    A 1 MiB data phase given a status wrapper's five seconds is the
  ;    defect this replaced: at five seconds a stick that pauses six
  ;    inside a write is reported as a failed transfer and the recovery
  ;    fires on a write that was going to succeed.
  If xh_BulkMs(0) <> #XHCI_TMO_EVENT_MS : ProcedureReturn 50 : EndIf
  If xh_BulkMs(64) <> #XHCI_TMO_EVENT_MS : ProcedureReturn 51 : EndIf
  ;    1 MiB at the 1,024 KB/s floor is 1,024 ms on top of the fixed part.
  If xh_BulkMs($100000) <> #XHCI_TMO_EVENT_MS + 1024 : ProcedureReturn 52 : EndIf
  ;    It is monotonic - a longer transfer never gets less patience.
  If xh_BulkMs($100000) <= xh_BulkMs($80000) : ProcedureReturn 53 : EndIf
  ;    And it stops at Linux's SCSI command timeout however big the ask.
  If xh_BulkMs($7FFFFFF) <> #XHCI_TMO_BULK_MAX_MS : ProcedureReturn 54 : EndIf
  ;    A 1 MiB transfer really does receive that budget, through xh_Bulk
  ;    itself and not only through the helper read on its own.
  GateReset(15, #XHCI_COMP_SUCCESS, 0)
  n = xh_Bulk(#XHCI_RING_BULK_IN, 5, $40000000, $100000)
  If n <> $100000 : ProcedureReturn 55 : EndIf
  If gateWaitMs <> #XHCI_TMO_EVENT_MS + 1024 : ProcedureReturn 56 : EndIf
  ProcedureReturn 0
EndProcedure
'''


MSC_MUTANTS = (
    ("command not capped at #MSC_XFER_BLOCKS",
     "    If n > #MSC_XFER_BLOCKS\n      n = #MSC_XFER_BLOCKS\n    EndIf",
     "    If n > 1000000\n      n = #MSC_XFER_BLOCKS\n    EndIf"),
    ("the LBA does not advance between commands",
     "    msc_PutBe32(@cdb[0], 2, lba + done)",
     "    msc_PutBe32(@cdb[0], 2, lba)"),
    ("a short command is accepted",
     "    If msc_lastData <> len Or msc_lastResidue <> 0",
     "    If msc_lastData < 0"),
    ("an odd address is DMA'd directly",
     "    If (*at & (#MSC_ALIGN - 1)) <> 0 Or PcieDmaOk(*at, len) = 0",
     "    If PcieDmaOk(*at, len) = 0"),
    ("a bounced read is not copied back",
     "    If opcode = #SCSI_READ10 And *io <> *at\n      msc_Copy(*at, *io, len)",
     "    If opcode = #SCSI_READ10 And *io <> *at And 1 = 0\n      msc_Copy(*at, *io, len)"),
    ("the range check can wrap",
     "  If lba < 0 Or lba >= msc_blocks Or count > msc_blocks - lba",
     "  If lba < 0 Or lba + count > msc_blocks"),
)

XHCI_MUTANTS = (
    ("cut at 64 KiB of length, not at the address boundary",
     "  firstSeg = #XHCI_TRB_BUF - (addr & (#XHCI_TRB_BUF - 1))",
     "  firstSeg = #XHCI_TRB_BUF"),
    ("the last TRB carries CHAIN too",
     "      f3 = f3 | #XHCI_TRB_IOC\n",
     "      f3 = f3 | #XHCI_TRB_IOC | #XHCI_TRB_CHAIN\n"),
    ("TD Size is not capped at 31",
     "      If tdSize > 31\n        tdSize = 31\n      EndIf",
     "      If tdSize > 1000\n        tdSize = 31\n      EndIf"),
    ("the head is written owned",
     "    If k = 0\n      cyc = startCycle ! 1\n    EndIf",
     "    If k = 0\n      cyc = startCycle\n    EndIf"),
    ("a mid-descriptor short packet counted as the whole length",
     "  If xh_evTrb = lastTrb\n    moved = len - xh_lastResid",
     "  If 1 = 1\n    moved = len - xh_lastResid"),
    ("the wait matches only the last TRB",
     "  If xh_WaitEventFor(#XHCI_TRB_TRANSFER, firstTrb, lastTrb, xh_BulkMs(len)) = 0",
     "  If xh_WaitEventFor(#XHCI_TRB_TRANSFER, lastTrb, lastTrb, xh_BulkMs(len)) = 0"),
    ("a megabyte gets a status wrapper's five seconds",
     "  If xh_WaitEventFor(#XHCI_TRB_TRANSFER, firstTrb, lastTrb, xh_BulkMs(len)) = 0",
     "  If xh_WaitEventFor(#XHCI_TRB_TRANSFER, firstTrb, lastTrb, #XHCI_TMO_EVENT_MS) = 0"),
    ("the budget does not grow with the bytes",
     "    ms = ms + (len / #XHCI_BULK_FLOOR_KBPS)",
     "    ms = ms + 0"),
    ("the budget has no ceiling",
     "  If ms > #XHCI_TMO_BULK_MAX_MS\n    ms = #XHCI_TMO_BULK_MAX_MS\n  EndIf",
     "  If ms > #XHCI_TMO_BULK_MAX_MS And 1 = 0\n    ms = #XHCI_TMO_BULK_MAX_MS\n  EndIf"),
)


def build(compiler: Path, work: Path, source: Path, stem: str) -> Path:
    staged = work / compiler.name
    if not staged.exists():
        shutil.copy2(compiler, staged)
    if (ROOT / "Boards").is_dir():
        shutil.copytree(ROOT / "Boards", work / "Boards", dirs_exist_ok=True)
    image = work / f"{stem}.img"
    command = [
        str(staged), "--compile", str(source), "-t", "pi4",
        "--load-addr", hex(emitted.LOAD),
        "--stack-addr", hex(emitted.STACK),
        "--entry-returns", "-o", str(image), "-s",
    ]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    run = subprocess.run(command, cwd=ROOT, env=env, text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if run.returncode or not image.is_file() or "COMPILER ERROR" in run.stdout:
        raise SystemExit("usb bulk range gate: compile failed\n" + run.stdout)
    return image


def run(a64, compiler: Path, work: Path, text: str, stem: str) -> tuple[int, int]:
    source = work / f"{stem}.pi4"
    source.write_text(text, encoding="utf-8", newline="\n")
    return emitted.execute(a64, build(compiler, work, source, stem))


def msc_program(msc: str) -> str:
    bodies = "\n\n".join(procedure(msc, name) for name in (
        "msc_Copy", "msc_BlockIo", "MscReadBlocks", "MscWriteBlocks", "MscReadBlock", "MscWriteBlock"))
    prelude = PRELUDE_MSC.replace("PROBE_XFER_BLOCKS", str(PROBE_XFER_BLOCKS))
    prelude = prelude.replace("GATE_DMA_LIMIT_VALUE", "$7FFFFFFF")
    return "EnableExplicit\n" + prelude + "\n" + bodies + "\n" + MAIN_MSC


def xhci_program(xhci: str) -> str:
    return ("EnableExplicit\n" + PRELUDE_XHCI + "\n"
            + procedure(xhci, "xh_BulkMs") + "\n"
            + procedure(xhci, "xh_Bulk") + "\n" + MAIN_XHCI)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP") or str(LOCAL_INTERP))
    args = parser.parse_args()
    compiler = emitted.required_path(args.compiler, "PMF_COMPILER")
    interp = emitted.required_path(args.interp, "PMF_A64_INTERP")
    a64 = emitted.load_interpreter(interp)
    emitted.STEP_LIMIT = 60_000_000

    msc = USBMSC.read_text(encoding="utf-8")
    xhci = XHCI.read_text(encoding="utf-8")
    audit_constants(msc, xhci)

    with tempfile.TemporaryDirectory(prefix="anvil-usb-bulk-range-") as temporary:
        work = Path(temporary)
        msc_result, msc_steps = run(a64, compiler, work, msc_program(msc), "msc_blocks_gate")
        if msc_result:
            print(f"usb_bulk_range_emitted_check: FAIL msc_BlockIo assertion {msc_result} after {msc_steps:,} instructions")
            return 1
        x_result, x_steps = run(a64, compiler, work, xhci_program(xhci), "xh_bulk_gate")
        if x_result:
            print(f"usb_bulk_range_emitted_check: FAIL xh_Bulk assertion {x_result} after {x_steps:,} instructions")
            return 1

        caught = 0
        for index, (label, old, new) in enumerate(MSC_MUTANTS):
            text = msc_program(replace_once(msc, old, new, label))
            result, _ = run(a64, compiler, work, text, f"msc_mutant_{index}")
            if result == 0:
                print(f"usb_bulk_range_emitted_check: FAIL mutant escaped: {label}")
                return 1
            print(f"  RED as required ({result}): {label}")
            caught += 1
        for index, (label, old, new) in enumerate(XHCI_MUTANTS):
            text = xhci_program(replace_once(xhci, old, new, label))
            result, _ = run(a64, compiler, work, text, f"xhci_mutant_{index}")
            if result == 0:
                print(f"usb_bulk_range_emitted_check: FAIL mutant escaped: {label}")
                return 1
            print(f"  RED as required ({result}): {label}")
            caught += 1

    print(f"usb_bulk_range_emitted_check: PASS - msc_BlockIo {msc_steps:,} and xh_Bulk {x_steps:,} emitted instructions")
    print(f"  {caught} mutants rejected; constants: {PROBE_XFER_BLOCKS}-block probe, production limits audited")
    return 0


if __name__ == "__main__":
    sys.exit(main())

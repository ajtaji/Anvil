#!/usr/bin/env python3
"""Reproduce build 173's silicon failure on the desk, and prove its fix.

WHAT HAPPENED (forum 916). Build 173 sent USB mass-storage transfers straight
into memory at $40000000 and $60000000. `load` of a 324 MB file said it had
loaded every byte, in 1.6 s, and the bytes were wrong; a `save` out of that
memory hung the stick; every storage command after it failed, the device
flush included. The medium was fine.

THE CAUSE. PcieResetAndTrain programmed the root complex's inbound window as
1 GiB (size code 15) while PcieDmaOk - the only question the USB driver asks
before handing memory to the controller - answered from the 3 GiB erratum.
A buffer above 1 GiB passed the check and lay outside the window. None of the
earlier gates modelled the window: their fake controllers accepted every
address PcieDmaOk accepted.

WHAT THIS GATE RUNS. The production window programming (the RC_BAR2 and SCB0
register writes, extracted from PcieResetAndTrain), the production PcieDmaOk,
and the production mass-storage command code (msc_BlockIo, MscReadBlocks,
MscWriteBlocks, MscFlush, MscRequestSense), compiled and executed under
tools/a64/a64_interp.py against a fake root complex and stick that behave
like the silicon did:

  * the window is decoded from the register values the production code
    WROTE, never from its constants;
  * a READ whose buffer is outside the window completes with good status and
    delivers nothing - memory keeps what it held (the board's RAM survives a
    reset, which is how 173's first 16 MiB looked right at one address);
  * a WRITE out of memory outside the window wedges the device, and every
    later command fails, SYNCHRONIZE CACHE included;
  * SYNCHRONIZE CACHE can be refused with CHECK CONDITION and ILLEGAL REQUEST
    (a stick with no cache) or with a real error;
  * a READ (10) longer than the device's transfer limit is refused;
  * every byte a read claims is compared with the medium's known content.

Main returns a bitmask of what went wrong. THE GATE REQUIRES BOTH: the tree
under test returns 0, AND the same probe built from commit 7db5b0a's
pcie.pi4 (build 173) returns exactly the silicon failure - wrong-data read,
failed write, rejected flush, dead device, and a PcieDmaOk that approves an
unreachable buffer. A gate that could not have caught 173 does not get to say
the next build is safe.

Usage:
  PMF_COMPILER=<PureMetalForge.exe> python tools/usb_dma_window_emitted_check.py
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
PCIE = "RaspberryPi4/Lib/pcie.pi4"
USBMSC = "RaspberryPi4/Lib/usbmsc.pi4"
XHCI = "RaspberryPi4/Lib/xhci.pi4"
LOCAL_INTERP = ROOT / "tools" / "a64" / "a64_interp.py"
BROKEN_REV = "7db5b0a"          # build 173
DRAM_LO, DRAM_HI = 0x40000000, 0x40100000
STEP_LIMIT = 40_000_000

F_READ_WRONG = 1
F_WRITE_FAILED = 2
F_FLUSH_FAILED = 4
F_DEAD_AFTER = 8
F_DMAOK_UNREACHABLE = 32
F_SYNC_REFUSAL = 64
F_LIMIT_IGNORED = 128
F_SHORT_ACCEPTED = 256
F_BOUNCE_WRONG = 512
F_STALL_DESYNC = 1024
F_NO_RECOVERY = 2048
F_UNIT_ATTENTION = 4096
F_LATE_EVENT = 8192
F_SIZE_WRONG = 16384
SILICON_173 = F_READ_WRONG | F_WRITE_FAILED | F_FLUSH_FAILED | F_DEAD_AFTER | F_DMAOK_UNREACHABLE


def procedure(source: str, name: str) -> str:
    starts = (f"Procedure {name}(", f"Procedure.i {name}(")
    lines = source.splitlines()
    first = next((i for i, line in enumerate(lines) if line.startswith(starts)), None)
    if first is None:
        raise SystemExit(f"dma window gate: production procedure {name} not found")
    last = next(i for i in range(first + 1, len(lines)) if lines[i] == "EndProcedure")
    return "\n".join(lines[first:last + 1])


def pcie_constants(source: str) -> str:
    out = []
    for line in source.splitlines():
        m = re.match(r"^#(PCIE_\w+)\s*=\s*(\$[0-9A-Fa-f]+|-?\d+)\s*(;.*)?$", line)
        if m:
            out.append(f"#{m.group(1)} = {m.group(2)}")
    return "\n".join(out)


def inbound_programming(source: str) -> str:
    """The register writes that size the inbound window, as PcieResetAndTrain
    makes them. Taken line by line so the gate follows the source, whatever
    constants it spells them with.

    The size is derived into a local in the production procedure - one call,
    written to both registers and compared against both readbacks - so that
    line comes too when it is there. A source that has no such line (build
    173's, and anything before the window was sized from the memory fitted)
    simply has none to take, and the three writes stand on their own."""
    body = procedure(source, "PcieResetAndTrain")
    keep = []
    derive = []
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("code = "):
            derive.append("  " + s)
        elif s.startswith(("pcie_Poke(#PCIE_MISC_RC_BAR2_CONFIG_LO", "pcie_Poke(#PCIE_MISC_RC_BAR2_CONFIG_HI")):
            keep.append("  " + s)
        elif s.startswith("pcie_Modify(#PCIE_MISC_MISC_CTRL") and "SCB0_SIZE_MASK" in s:
            keep.append("  " + s)
    if len(keep) != 3:
        raise SystemExit(f"dma window gate: expected 3 inbound window writes in PcieResetAndTrain, found {len(keep)}")
    head = "Procedure GateProgramInbound()\n"
    if derive:
        head += "  Define code.i\n" + "\n".join(derive) + "\n"
    return head + "\n".join(keep) + "\nEndProcedure"


PRELUDE = r'''
; ---- the wait ledger the production bodies account into ----------------
; Not inert: XhciAccountWait counts, and the fixture asserts the count.
#XHCI_W_HALT      =  0
#XHCI_W_HCRST     =  1
#XHCI_W_CNR       =  2
#XHCI_W_RUN       =  3
#XHCI_W_ADOPT     =  4
#XHCI_W_PORTPWR   =  5
#XHCI_W_PORTRESET =  6
#XHCI_W_CMD       =  7
#XHCI_W_XFER      =  8
#XHCI_W_CTRL      =  9
#XHCI_W_BULK      = 10
#XHCI_W_HUBRESET  = 11
#XHCI_W_HUBRECOV  = 12
#XHCI_W_HUBPGOOD  = 13
#XHCI_W_HUBSETTLE = 14
#XHCI_W_HUBDEB    = 15
#XHCI_W_MSCCONF   = 16
#XHCI_W_MSCREADY  = 17
#XHCI_W_MSCRESET  = 18
#XHCI_W_PORTDEB   = 19
#XHCI_W_PORTRCVY  = 20
#XHCI_W_SETADDR   = 21
#XHCI_W_N         = 22
Global Dim gateWaitRow.i[#XHCI_W_N]
Procedure.i XhciWaitMark()
  ProcedureReturn 0
EndProcedure
Procedure XhciAccountWait(site.i, t0.i)
  If site >= 0 And site < #XHCI_W_N
    gateWaitRow[site] = gateWaitRow[site] + 1
  EndIf
EndProcedure
Procedure XhciAccountBulkBytes(n.i)
EndProcedure
Procedure.i GateWaitVisits(site.i)
  If site < 0 Or site >= #XHCI_W_N
    ProcedureReturn -1
  EndIf
  ProcedureReturn gateWaitRow[site]
EndProcedure
; ---- the probe's own sizes: four blocks per command keeps it small -------
#MSC_ALIGN     = 64
#MSC_OFF_CBW   = 0
#MSC_OFF_CSW   = 64
#MSC_OFF_DATA  = 128
#MSC_OFF_BOUNCE = 640
#MSC_XFER_BLOCKS = 4
#MSC_POOL_BYTES = 8192

#XHCI_ERR_ARG = 30
#XHCI_ERR_STALL = 29
#XHCI_ERR_NO_EPS = 36
#XHCI_RING_BULK_OUT = 9
#XHCI_RING_BULK_IN = 10
#XHCI_TRB_BYTES = 16
#XHCI_TRBS_PER_SEG = 64
#XHCI_TRB_TRANSFER = 32
#XHCI_TRB_STOP_RING = 15
#XHCI_TMO_EVENT_MS = 5000
#XHCI_EP_STATE_RUNNING = 1
#XHCI_EP_STATE_STOPPED = 3

Global Dim msc_pool.a[#MSC_POOL_BYTES]
Global msc_base.i = 0
Global msc_tag.i = 0
Global msc_err.i = 0
Global msc_ready.i = 1
Global msc_blocks.i = 1000
Global msc_blockSz.i = 512
Global msc_lastStatus.i = 0
Global msc_senseKey.i = 0
Global msc_senseAsc.i = 0
Global msc_lastIn.i = 0
Global msc_lastData.i = 0
Global msc_lastResidue.i = 0
Global msc_needReset.i = 0
Global msc_senseValid.i = 0
Global msc_uaRetries.i = 0
Global msc_resets.i = 0
Global msc_iface.i = 0
Global xh_dciOut.i = 2
Global xh_dciIn.i = 3
Global xh_mscSlot.i = 1
Global xh_err.i = 0
Global xh_lastComp.i = 1
Global xh_drained.i = 0
Global xh_drainedXfer.i = 0

; ---- the fake root complex: what the production code wrote ---------------
Global gRcBar2Lo.i
Global gRcBar2Hi.i
; How much memory the board told the driver it has. 0 is nobody said,
; which is the state build 173's source and every diagnostic stay in.
Global pcie_memBytes.i
Global gMiscCtrl.i

; ---- the fake stick, a Bulk-Only state machine ----------------------------
#G_WANT_CBW = 0
#G_DATA_IN = 1
#G_DATA_OUT = 2
#G_STATUS = 3
Global gState.i
Global gTag.i
Global gOp.i
Global gLba.i
Global gBlocks.i
Global gXferLen.i
Global gStatus.i
Global gResidue.i
Global gDead.i
Global gDropped.i
Global gMaxBlocks.i = 65535
Global gShortBy.i               ; the next data IN phase sends this many bytes less
Global gSyncRefuse.i            ; 0 accepts, 1 ILLEGAL REQUEST/$20, 2 MEDIUM ERROR
Global gSenseKey.i
Global gSenseAsc.i
Global gHaltIn.i                ; the device has halted bulk IN
Global gRefusedData.i           ; a refused command's data phase is still to stall
Global gLoseCsw.i               ; drop the next status wrapper (a lost exchange)
Global gDesync.i                ; host and device out of step until a class reset
Global gResets.i
Global gUnitAttention.i         ; the next command is answered 6/$29, not done
Global gSenseFail.i             ; REQUEST SENSE itself is refused
Global gPendingLate.i           ; a transfer this host gave up on; the device
                                ; still owes its transfer event
Global gLateEvents.i            ; stale transfer events sitting on the ring
Global gStaleTaken.i            ; times a stale event was taken as a completion
Global gEpState.i = #XHCI_EP_STATE_STOPPED
Global gStops.i
Global Dim gEvTrb.a[#XHCI_TRB_BYTES]
Global xh_evBase.i
Global xh_evDeq.i = 0
Global Dim gStore.a[64 * 512]   ; WRITEs to blocks 500..563
Global Dim gBss.a[64 * 512 + 128]

; ---- THE CPU CACHE: device writes land here and reach what the CPU reads
; only when the driver invalidates those lines (dc civac). A driver that
; forgets reads stale memory - the other way 173's symptom can arise.
Global Dim gShadow.a[65536]
Global gShadowAddr.i
Global gShadowLen.i

Procedure xh_Trace(p.i)
EndProcedure

Procedure.i xh_Fail(code.i)
  xh_err = code
  ProcedureReturn 0
EndProcedure

Procedure.i XhciBulkReady()
  ProcedureReturn 1
EndProcedure

Procedure.i XhciLastComp()
  ProcedureReturn xh_lastComp
EndProcedure

Procedure.i XhciLastError()
  ProcedureReturn xh_err
EndProcedure

Procedure delay(ms.i)
EndProcedure

Procedure.i XhciBulkEpIn()
  ProcedureReturn $81
EndProcedure

Procedure.i XhciBulkEpOut()
  ProcedureReturn $02
EndProcedure

; The recovery requests, as the stick answers them. A controller wedged by
; DMA outside its window (gDead) answers nothing; a device merely out of
; step (gDesync) is put right by the class reset.
Procedure.i XhciMscClassReset(iface.i)
  If gDead <> 0
    ProcedureReturn 0
  EndIf
  gResets = gResets + 1
  gDesync = 0
  gHaltIn = 0
  gRefusedData = 0
  gState = #G_WANT_CBW
  ; A Bulk-Only reset IS a state change, and the standard answer to the next
  ; command is CHECK CONDITION / UNIT ATTENTION / $29 "power on, reset, or
  ; bus device reset occurred", with the command NOT performed. Sticks really
  ; do this; it is the ordinary consequence of recovering.
  gUnitAttention = 1
  ProcedureReturn 1
EndProcedure

Procedure.i XhciClearEndpointHalt(ep.i)
  If gDead <> 0
    ProcedureReturn 0
  EndIf
  If (ep & $80) <> 0
    gHaltIn = 0
  EndIf
  ProcedureReturn 1
EndProcedure

; ---- the controller side of a reconfigure --------------------------------
; XhciBulkReconfigure and xh_DrainEvents are PRODUCTION here. What is faked
; is the command ring, the endpoint state and the event ring itself.
;
; THE EVENT RING IS MODELLED AS A COUNT, not as memory: the ring mechanics
; (cycle bits, the dequeue pointer, ERDP) have their own gate in the wait
; path. What is under test here is whether anything empties it, and when.
Procedure.i xh_EventReady()
  If gLateEvents > 0
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure xh_AckEvent()
  If gLateEvents > 0
    gLateEvents = gLateEvents - 1
  EndIf
EndProcedure

; The endpoint state the CONTROLLER reports. Deliberately not RUNNING: an
; endpoint whose transfer descriptor timed out can read STOPPED or HALTED
; and still have the device answer it later, which is why Stop Endpoint may
; not be made conditional on this.
Procedure.i xh_EpStateAt(slot.i, dci.i)
  ProcedureReturn gEpState
EndProcedure

Procedure.i xh_CommandEp(cmd.i, f0.i, f1.i, slot.i, dci.i, ms.i)
  If gDead <> 0
    ProcedureReturn 0
  EndIf
  If cmd = #XHCI_TRB_STOP_RING
    gStops = gStops + 1
    ; Stopping the endpoint is what makes the abandoned transfer descriptor
    ; report: the controller posts its transfer event now, before the
    ; command completion. That event is the stale one.
    If gPendingLate <> 0
      gPendingLate = 0
      gLateEvents = gLateEvents + 1
    EndIf
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i xh_BulkContexts(slot.i, drop.i)
  If gDead <> 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure xh_Clean(addr.i, len.i)
EndProcedure

Procedure xh_Inval(addr.i, len.i)
  Define a.i
  Define i.i
  a = (addr >> 6) << 6
  While a < addr + len
    i = 0
    While i < 64
      If a + i >= gShadowAddr And a + i < gShadowAddr + gShadowLen
        PokeA(a + i, gShadow[a + i - gShadowAddr])
      EndIf
      i = i + 1
    Wend
    a = a + 64
  Wend
EndProcedure

Procedure pcie_Poke(off.i, v.i)
  If off = #PCIE_MISC_RC_BAR2_CONFIG_LO
    gRcBar2Lo = v & $FFFFFFFF
  ElseIf off = #PCIE_MISC_RC_BAR2_CONFIG_HI
    gRcBar2Hi = v & $FFFFFFFF
  ElseIf off = #PCIE_MISC_MISC_CTRL
    gMiscCtrl = v & $FFFFFFFF
  EndIf
EndProcedure

Procedure pcie_Modify(off.i, clearMask.i, setMask.i)
  If off = #PCIE_MISC_MISC_CTRL
    gMiscCtrl = ((gMiscCtrl & ~clearMask) | setMask) & $FFFFFFFF
  EndIf
EndProcedure

; What the controller reaches, decoded as the silicon decodes the registers
; (U-Boot brcm_pcie_encode_ibar_size): RC_BAR2 and SCB0 both bound it, and a
; non-zero offset means a CPU address is not a bus address at all.
Procedure.i GateWindowBytes()
  Define code.i
  Define bar.i
  Define scb.i
  code = gRcBar2Lo & $1F
  If code < 1 Or code > 22
    ProcedureReturn 0
  EndIf
  If (gRcBar2Lo & ~$1F) <> 0 Or gRcBar2Hi <> 0
    ProcedureReturn 0
  EndIf
  bar = 1 << (code + 15)
  code = (gMiscCtrl >> 27) & $1F
  If code < 1 Or code > 22
    ProcedureReturn 0
  EndIf
  scb = 1 << (code + 15)
  If scb < bar
    bar = scb
  EndIf
  ProcedureReturn bar
EndProcedure

Procedure.i GateReachable(addr.i, len.i)
  If addr < 0 Or len <= 0 Or addr + len > GateWindowBytes()
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
; GateSizeCase - one board's memory size, end to end.
;
; Tells the driver how much memory there is, runs the PRODUCTION window
; programming, and then checks three things that have to agree:
;
;   * the window the registers actually decode to is the one this size
;     should produce - computed here from the size, never read out of the
;     procedure under test;
;   * PcieDmaOk's last yes and first no sit exactly on the smallest of the
;     erratum, that window and the memory, which is recomputed here too;
;   * nothing PcieDmaOk approves lies outside the window the silicon
;     decoded. That is forum 916 stated as an invariant.
;
; THE 1.5 GB CASE IS THE ONE THAT NEEDS THE MEMORY LIMIT. Every size the
; Pi's own revision code can report is a power of two, so the window comes
; out exactly the size of the memory and the memory limit never binds. A
; seam is not a revision field, though - it is whatever a board answers,
; and the UNO Q's three banks total less than four gigabytes - so a size
; between two powers of two is asked for here, where the window rounds UP
; past the memory and the memory is the only limit left standing.
; ----------------------------------------------------------------------
Procedure.i GateSizeCase(mem.i, wantWindow.i)
  Define top.i
  pcie_memBytes = mem
  GateProgramInbound()
  If GateWindowBytes() <> wantWindow
    ProcedureReturn 16384
  EndIf
  top = $C0000000
  If wantWindow < top
    top = wantWindow
  EndIf
  If mem > 0 And mem < top
    top = mem
  EndIf
  If PcieDmaOk(top - 512, 512) <> 1
    ProcedureReturn 16384
  EndIf
  If PcieDmaOk(top, 512) <> 0
    ProcedureReturn 16384
  EndIf
  If PcieDmaOk(top - 256, 512) <> 0
    ProcedureReturn 16384
  EndIf
  If GateReachable(top - 512, 512) = 0
    ProcedureReturn 16384
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i GatePattern(lba.i, off.i)
  ProcedureReturn (lba * 29 + (off / 512) * 29 + (off % 512) * 7 + 3) & $FF
EndProcedure

Procedure.i GateU32(addr.i)
  ProcedureReturn PeekA(addr) | (PeekA(addr + 1) << 8) | (PeekA(addr + 2) << 16) | (PeekA(addr + 3) << 24)
EndProcedure

Procedure GatePut32(addr.i, v.i)
  PokeA(addr, v & $FF)
  PokeA(addr + 1, (v >> 8) & $FF)
  PokeA(addr + 2, (v >> 16) & $FF)
  PokeA(addr + 3, (v >> 24) & $FF)
EndProcedure

; THE STICK. One bulk transfer at a time, as the controller would carry it.
; Returns bytes moved, or -1 for a transfer that never completed.
Procedure.i xh_Bulk(ring.i, dci.i, addr.i, len.i)
  Define i.i
  Define n.i
  Define cdb.i
  xh_err = 0
  ; A transfer this host gave up on is still owed an answer. If nobody
  ; stopped the endpoint, the device gets round to it now - just as the
  ; next transfer starts.
  If gPendingLate <> 0
    gPendingLate = 0
    gLateEvents = gLateEvents + 1
  EndIf
  ; And an event left on the ring falls inside THIS transfer's TRB range,
  ; because the reconfigure started the rings again at index 0. The wait
  ; takes it as this transfer's completion: good status, the old residual,
  ; and not one byte moved.
  If gLateEvents > 0
    gLateEvents = gLateEvents - 1
    gStaleTaken = gStaleTaken + 1
    xh_lastComp = 1
    ProcedureReturn len
  EndIf
  If gDead <> 0 Or gDesync <> 0
    xh_lastComp = 4
    ProcedureReturn -1
  EndIf
  If ring = #XHCI_RING_BULK_IN And gHaltIn <> 0
    xh_lastComp = 6
    xh_err = #XHCI_ERR_STALL
    ProcedureReturn -1
  EndIf
  If ring = #XHCI_RING_BULK_IN And gRefusedData <> 0
    ; BOT 6.7.2: the device refuses the data it was asked for by halting
    ; the pipe, and keeps its status wrapper for afterwards.
    gRefusedData = 0
    gHaltIn = 1
    xh_lastComp = 6
    xh_err = #XHCI_ERR_STALL
    ProcedureReturn -1
  EndIf
  If GateReachable(addr, len) = 0
    If ring = #XHCI_RING_BULK_IN
      ; GOOD STATUS, NOTHING DELIVERED - the silicon symptom on 173.
      gDropped = gDropped + 1
      If gState = #G_DATA_IN
        gState = #G_STATUS
      ElseIf gState = #G_STATUS
        gState = #G_WANT_CBW
      EndIf
      xh_lastComp = 1
      ProcedureReturn len
    EndIf
    gDead = 1
    xh_lastComp = 4
    ProcedureReturn -1
  EndIf
  xh_lastComp = 1
  If ring = #XHCI_RING_BULK_OUT And gState = #G_WANT_CBW
    If len <> 31 Or GateU32(addr) <> $43425355
      gDead = 1
      ProcedureReturn -1
    EndIf
    gTag = GateU32(addr + 4)
    gXferLen = GateU32(addr + 8)
    cdb = addr + 15
    gOp = PeekA(cdb)
    gLba = (PeekA(cdb + 2) << 24) | (PeekA(cdb + 3) << 16) | (PeekA(cdb + 4) << 8) | PeekA(cdb + 5)
    gBlocks = (PeekA(cdb + 7) << 8) | PeekA(cdb + 8)
    gStatus = 0
    gResidue = 0
    ; UNIT ATTENTION: a state change the initiator is being told about, and
    ; the command was NOT performed. REQUEST SENSE is exempt - it is how the
    ; host is supposed to find out - and reporting the condition clears it.
    If gUnitAttention <> 0 And gOp <> $03
      gUnitAttention = 0
      gStatus = 1 : gSenseKey = 6 : gSenseAsc = $29
      gResidue = gXferLen
      If gOp = $28
        gRefusedData = 1
      EndIf
      If gOp = $2A
        gState = #G_DATA_OUT
      Else
        gState = #G_STATUS
      EndIf
      ProcedureReturn 31
    EndIf
    If gOp = $35
      If gSyncRefuse = 1
        gStatus = 1 : gSenseKey = 5 : gSenseAsc = $20
      ElseIf gSyncRefuse = 2
        gStatus = 1 : gSenseKey = 3 : gSenseAsc = $0C
      ElseIf gSyncRefuse = 3
        ; the other "no such command": the opcode exists, this shape of it
        ; does not. Several USB bridges answer a whole-medium flush this way.
        gStatus = 1 : gSenseKey = 5 : gSenseAsc = $24
      EndIf
      gState = #G_STATUS
    ElseIf gOp = $03
      If gSenseFail <> 0
        gStatus = 1
        gState = #G_STATUS
      Else
        gState = #G_DATA_IN
      EndIf
    ElseIf (gOp = $28 Or gOp = $2A) And gBlocks > gMaxBlocks
      gStatus = 1 : gSenseKey = 5 : gSenseAsc = $24
      gResidue = gXferLen
      If gOp = $28
        gRefusedData = 1
      EndIf
      gState = #G_STATUS
    ElseIf gOp = $28
      gState = #G_DATA_IN
    ElseIf gOp = $2A
      gState = #G_DATA_OUT
    Else
      gState = #G_STATUS
    EndIf
    ProcedureReturn 31
  EndIf
  If ring = #XHCI_RING_BULK_IN And gState = #G_DATA_IN
    n = len
    If n > gXferLen
      n = gXferLen
    EndIf
    If gOp = $28 And gShortBy > 0
      n = n - gShortBy
      gResidue = gShortBy
      gShortBy = 0
    EndIf
    gShadowAddr = addr
    gShadowLen = n
    i = 0
    While i < n
      If gOp = $03
        gShadow[i] = 0
        If i = 2 : gShadow[i] = gSenseKey : EndIf
        If i = 12 : gShadow[i] = gSenseAsc : EndIf
      Else
        gShadow[i] = GatePattern(gLba, i)
      EndIf
      i = i + 1
    Wend
    gState = #G_STATUS
    ProcedureReturn n
  EndIf
  If ring = #XHCI_RING_BULK_OUT And gState = #G_DATA_OUT
    i = 0
    While i < len
      ; A refused command takes the data off the wire and throws it away.
      If gStatus = 0 And gLba >= 500 And gLba + gBlocks <= 564
        gStore[(gLba - 500) * 512 + i] = PeekA(addr + i)
      EndIf
      i = i + 1
    Wend
    gState = #G_STATUS
    ProcedureReturn len
  EndIf
  If ring = #XHCI_RING_BULK_IN And gState = #G_STATUS And gLoseCsw <> 0
    ; The status wrapper never arrives: the host times out waiting.
    ; A TIMED-OUT TRANSFER IS NOT A CANCELLED ONE. The device still owes the
    ; controller this transfer's event, and will deliver it whenever it gets
    ; round to it - seconds later, after the host has moved on.
    gLoseCsw = 0
    gPendingLate = 1
    gDesync = 1
    xh_lastComp = 4
    ProcedureReturn -1
  EndIf
  If ring = #XHCI_RING_BULK_IN And gState = #G_STATUS
    GatePut32(addr, $53425355)
    GatePut32(addr + 4, gTag)
    GatePut32(addr + 8, gResidue)
    PokeA(addr + 12, gStatus)
    gState = #G_WANT_CBW
    ProcedureReturn 13
  EndIf
  ; The host asked for a phase the device is not in: out of step until reset.
  gDesync = 1
  xh_lastComp = 4
  ProcedureReturn -1
EndProcedure

Procedure.i GateReadOk(*mem, lba.i, count.i)
  Define i.i
  i = 0
  While i < count * 512
    If PeekA(*mem + i) <> GatePattern(lba, i)
      ProcedureReturn 0
    EndIf
    i = i + 1
  Wend
  ProcedureReturn 1
EndProcedure

Procedure.i GateStoredOk(*src, lba.i, count.i)
  Define i.i
  i = 0
  While i < count * 512
    If gStore[(lba - 500) * 512 + i] <> PeekA(*src + i)
      ProcedureReturn 0
    EndIf
    i = i + 1
  Wend
  ProcedureReturn 1
EndProcedure

Procedure GateRestart()
  gDead = 0
  gDesync = 0
  gHaltIn = 0
  gRefusedData = 0
  gState = #G_WANT_CBW
  gUnitAttention = 0
  gSenseFail = 0
  gPendingLate = 0
  gLateEvents = 0
  gStaleTaken = 0
  gStops = 0
  xh_drainedXfer = 0
  xh_lastComp = 1
EndProcedure

Procedure GateEventInit()
  xh_evBase = @gEvTrb[0]
  ; Word 3 of a TRB carries its type in bits 15:10. This one is a Transfer
  ; Event, which is what a drain has to recognise and count.
  PokeN(xh_evBase + 12, #XHCI_TRB_TRANSFER << 10)
EndProcedure
'''

MAIN = r'''
Procedure.i Main()
  Define fails.i
  Define i.i
  Define a.i
  GateProgramInbound()
  GateEventInit()

  ; 1-4. BUILD 173'S SEQUENCE: load into high memory, save out of it, flush,
  ; then any read at all.
  i = 0
  While i < 12 * 512
    PokeA($40000000 + i, $EE)                 ; what RAM held before
    PokeA($40010000 + i, (i * 13 + 1) & $FF)  ; what `save` writes
    i = i + 1
  Wend
  If MscReadBlocks(100, 12, $40000000) <> 1 Or GateReadOk($40000000, 100, 12) = 0
    fails = fails | 1
  EndIf
  If MscWriteBlocks(500, 8, $40010000) <> 1 Or GateStoredOk($40010000, 500, 8) = 0
    fails = fails | 2
  EndIf
  If MscFlush() <> 1
    fails = fails | 4
  EndIf
  If MscReadBlocks(200, 8, @gBss[64]) <> 1 Or GateReadOk(@gBss[64], 200, 8) = 0
    fails = fails | 8
  EndIf
  GateRestart()

  ; 5. PcieDmaOk may never approve memory the programmed window cannot reach,
  ; nor memory past the 3 GiB erratum.
  a = $3FFFF000
  While a <= $C0000000
    If PcieDmaOk(a, $2000) = 1 And GateReachable(a, $2000) = 0
      fails = fails | 32
    EndIf
    a = a + $20000000
  Wend
  If PcieDmaOk($BFFFF000, $2000) <> 0 Or PcieDmaOk($C0000000, 512) <> 0
    fails = fails | 32
  EndIf

  ; 6. SYNCHRONIZE CACHE refused: "no cache" (ILLEGAL REQUEST / INVALID
  ; COMMAND OPERATION CODE) is a flush; a medium error is not; and the next
  ; command still works either way - the refusal must not leave the two ends
  ; out of step.
  gSyncRefuse = 1
  If MscFlush() <> 1
    fails = fails | 64
  EndIf
  gSyncRefuse = 2
  If MscFlush() <> 0
    fails = fails | 64
  EndIf
  gSyncRefuse = 0
  If MscReadBlocks(210, 4, @gBss[64]) <> 1 Or GateReadOk(@gBss[64], 210, 4) = 0
    fails = fails | 64
  EndIf

  ; 7. a transfer longer than the device allows fails, and never as data.
  gMaxBlocks = 2
  i = gResets
  If MscReadBlocks(300, 12, @gBss[64]) <> 0
    fails = fails | 128
  EndIf
  gMaxBlocks = 65535
  ; 10. ...and the refusal's stalled data phase left nothing queued: the very
  ; next command works with no restart of the model.
  ; A refusal is an ANSWER: it must not have cost a reset recovery either.
  If MscReadBlocks(310, 4, @gBss[64]) <> 1 Or GateReadOk(@gBss[64], 310, 4) = 0 Or gResets <> i
    fails = fails | 1024
  EndIf
  GateRestart()

  ; 11. a lost status wrapper costs a reset recovery and a retry, not the
  ; stick: the read still returns the medium's bytes.
  gLoseCsw = 1
  i = gResets
  If MscReadBlocks(420, 4, @gBss[64]) <> 1 Or GateReadOk(@gBss[64], 420, 4) = 0 Or gResets <> i + 1
    fails = fails | 2048
  EndIf
  GateRestart()

  ; 8. a short data phase with its residue fails the read.
  gShortBy = 512
  If MscReadBlocks(320, 4, @gBss[64]) <> 0
    fails = fails | 256
  EndIf
  gShortBy = 0
  GateRestart()

  ; 9. the bounced path (an address the controller cannot reach) delivers
  ; exactly the medium's bytes: odd address inside the probe's memory.
  If MscReadBlocks(400, 6, @gBss[64] + 1) <> 1 Or GateReadOk(@gBss[64] + 1, 400, 6) = 0
    fails = fails | 512
  EndIf
  GateRestart()

  ; 12. THE OTHER "no such command". A device that has the SYNCHRONIZE CACHE
  ; opcode but not this shape of it answers ILLEGAL REQUEST / INVALID FIELD
  ; IN CDB. Nothing is pending, because nothing was attempted: that is a
  ; flush, exactly as $20 is.
  gSyncRefuse = 3
  If MscFlush() <> 1
    fails = fails | 64
  EndIf
  gSyncRefuse = 0

  ; 13. AND A REFUSAL NOBODY COULD READ IS NOT ACCEPTED. The device fails
  ; the flush AND refuses to say why; the sense data left over from case 12
  ; would say "no such command" if anybody looked at it. A flush must not be
  ; reported on the strength of an older command's answer.
  gSyncRefuse = 2
  gSenseFail = 1
  If MscFlush() <> 0
    fails = fails | 64
  EndIf
  gSenseFail = 0
  gSyncRefuse = 0
  GateRestart()

  ; 14. A WRITE THROUGH A HICCUP, WHICH IS THE ONE THAT MATTERS. Twelve
  ; blocks is three commands at this probe's transfer size. The first
  ; command's status wrapper is lost, so the driver recovers - and the
  ; recovery makes the device answer the retry with UNIT ATTENTION, command
  ; not performed. A driver that spends its only retry on the attention
  ; condition writes the first four blocks and none of the rest: a file that
  ; is part old and part new, with no error anywhere near the DMA window.
  i = 0
  While i < 12 * 512
    PokeA($40020000 + i, (i * 7 + 5) & $FF)
    i = i + 1
  Wend
  gLoseCsw = 1
  a = gResets
  If MscWriteBlocks(520, 12, $40020000) <> 1 Or GateStoredOk($40020000, 520, 12) = 0
    fails = fails | 4096
  EndIf
  ; and the recovery really happened, or the case proves nothing
  If gResets <> a + 1
    fails = fails | 4096
  EndIf
  GateRestart()

  ; 15. THE LATE ANSWER. Same lost status wrapper, and this time what is
  ; measured is the event ring: the abandoned transfer's event arrives when
  ; the endpoints are stopped, and must be off the ring before the retry
  ; builds its TRBs on the same addresses. If it is not, the retry reads its
  ; own completion out of the old transfer and reports success over memory
  ; nothing wrote.
  gLoseCsw = 1
  If MscReadBlocks(430, 4, @gBss[64]) <> 1 Or GateReadOk(@gBss[64], 430, 4) = 0
    fails = fails | 8192
  EndIf
  ; The proof that this case is not vacuous: both endpoints were stopped,
  ; the stale event was counted by the drain, and none was ever mistaken for
  ; a completion.
  If gStops <> 2 Or xh_drainedXfer <> 1 Or gStaleTaken <> 0
    fails = fails | 8192
  EndIf

  ; 16. THE WINDOW IS SIZED TO THE MEMORY THE BOARD HAS. Last, and
  ; deliberately so: it reprograms the inbound window and leaves the
  ; driver believing in a different board, so nothing above it may run
  ; afterwards. Everything before this point ran on a board that never
  ; said what size it was, which is exactly build 173's world and the
  ; state every diagnostic that includes the library on its own stays in.
  fails = fails | GateSizeCase(0, $100000000)            ; nobody said
  fails = fails | GateSizeCase(-1, $100000000)           ; asked, not told
  fails = fails | GateSizeCase($40000000, $40000000)     ; 1 GB  -> code 15
  fails = fails | GateSizeCase($80000000, $80000000)     ; 2 GB  -> code 16
  fails = fails | GateSizeCase($100000000, $100000000)   ; 4 GB  -> code 17
  fails = fails | GateSizeCase($200000000, $100000000)   ; 8 GB  -> 17, capped
  fails = fails | GateSizeCase($60000000, $80000000)     ; 1.5 GB, rounded up
  ProcedureReturn fails
EndProcedure
'''


OVERRIDDEN = {"MSC_ALIGN", "MSC_OFF_CBW", "MSC_OFF_CSW", "MSC_OFF_DATA", "MSC_OFF_BOUNCE",
              "MSC_XFER_BLOCKS", "MSC_XFER_BYTES", "MSC_POOL_USED", "MSC_POOL_BYTES"}


def msc_constants(source: str) -> str:
    out = []
    for line in source.splitlines():
        m = re.match(r"^#((?:MSC|SCSI)_\w+)\s*=\s*(\$[0-9A-Fa-f]+|-?\d+)\s*(;.*)?$", line)
        if m and m.group(1) not in OVERRIDDEN:
            out.append(f"#{m.group(1)} = {m.group(2)}")
    return "\n".join(out)


MSC_PROCS = ("MscBuffers", "msc_Cbw", "msc_Csw", "msc_Data", "msc_Bounce", "msc_Fail",
             "msc_PutLe32", "msc_GetLe32", "msc_PutBe32", "msc_Exchange", "msc_ResetRecovery",
             "msc_Sense", "msc_Command", "msc_Copy",
             "msc_BlockIo", "MscReadBlocks", "MscWriteBlocks", "MscRequestSense", "MscFlush")

# Production procedures on the controller side of a recovery. Build 173 has
# none of them, which is the point; the probe takes what the source under
# test actually has.
XHCI_PROCS = ("XhciBulkOut", "XhciBulkIn", "xh_DrainEvents", "XhciBulkReconfigure")


def program(pcie_src: str, msc_src: str, xhci_src: str) -> str:
    # Before PcieDmaOk, because it calls them, and in dependency order.
    # A source that predates the memory-sized window has none of them and
    # its PcieDmaOk asks for none.
    bodies = [procedure(pcie_src, name)
              for name in ("PcieInboundSizeCode", "PcieInboundBytes", "PcieDmaTop")
              if re.search(r"^Procedure(\.\w+)? " + name + r"\(", pcie_src, re.M)]
    bodies += [procedure(pcie_src, "PcieDmaOk"), inbound_programming(pcie_src)]
    bodies += [procedure(xhci_src, name) for name in XHCI_PROCS
               if re.search(r"^Procedure(\.\w+)? " + name + r"\(", xhci_src, re.M)]
    # Build 173's source has no msc_Exchange or msc_ResetRecovery; the probe
    # takes what the source under test actually has.
    bodies += [procedure(msc_src, name) for name in MSC_PROCS
               if re.search(r"^Procedure(\.\w+)? " + name + r"\(", msc_src, re.M)]
    return ("EnableExplicit\n" + pcie_constants(pcie_src) + "\n" + msc_constants(msc_src) + "\n"
            + PRELUDE + "\n" + "\n\n".join(bodies) + "\n" + MAIN)


def build(compiler: Path, work: Path, text: str, stem: str) -> Path:
    source = work / f"{stem}.pi4"
    source.write_text(text, encoding="utf-8", newline="\n")
    staged = work / compiler.name
    if not staged.exists():
        shutil.copy2(compiler, staged)
    if (ROOT / "Boards").is_dir():
        shutil.copytree(ROOT / "Boards", work / "Boards", dirs_exist_ok=True)
    image = work / f"{stem}.img"
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    run = subprocess.run([str(staged), "--compile", str(source), "-t", "pi4",
                          "--load-addr", hex(emitted.LOAD), "--stack-addr", hex(emitted.STACK),
                          "--entry-returns", "-o", str(image), "-s"],
                         cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if run.returncode or not image.is_file() or "COMPILER ERROR" in run.stdout:
        raise SystemExit("dma window gate: compile failed\n" + run.stdout[-4000:])
    return image


def execute(a64, image: Path) -> tuple[int, int]:
    """tcp_multiif_emitted_check.execute, with one more admitted range: a
    megabyte of DRAM at $40000000, where build 173 loaded and saved."""
    blob = image.read_bytes()
    bss_lo, bss_hi = emitted.symbol_bounds(image.with_suffix(image.suffix + ".sym"))
    stack = (emitted.STACK - emitted.STACK_BYTES, emitted.STACK + 16)
    readable = ((emitted.LOAD, emitted.LOAD + len(blob)), (bss_lo, bss_hi), stack, (DRAM_LO, DRAM_HI))
    writable = ((bss_lo, bss_hi), stack, (DRAM_LO, DRAM_HI))

    def inside(ranges, addr, size):
        return size > 0 and any(lo <= addr and addr + size <= hi for lo, hi in ranges)

    cpu = a64.A64()
    for off, b in enumerate(blob):
        cpu.memory[emitted.LOAD + off] = b
    a64.attach_symbols(cpu, image, emitted.LOAD)
    cpu.pc = emitted.LOAD
    cpu.sp = emitted.STACK
    cpu.x[30] = emitted.LOADER_LR

    def load(addr, size):
        cpu.align_guard(addr, size, False)
        if not inside(readable, addr, size):
            raise SystemExit(f"dma window gate: read outside admitted memory at ${addr:X}+{size}")
        return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr, value, size):
        cpu.align_guard(addr, size, True)
        if not inside(writable, addr, size):
            raise SystemExit(f"dma window gate: write outside admitted memory at ${addr:X}+{size}")
        for i in range(size):
            cpu.memory[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    for steps in range(STEP_LIMIT):
        if cpu.pc == emitted.LOADER_LR:
            return cpu.x[0], steps
        cpu.step()
    raise SystemExit(f"dma window gate: no return in {STEP_LIMIT:,} instructions")


def describe(mask: int) -> str:
    names = {F_READ_WRONG: "wrong-data read", F_WRITE_FAILED: "write failed",
             F_FLUSH_FAILED: "flush rejected", F_DEAD_AFTER: "device dead afterwards",
             F_DMAOK_UNREACHABLE: "PcieDmaOk approves unreachable memory",
             F_SYNC_REFUSAL: "SYNCHRONIZE CACHE refusal mishandled",
             F_LIMIT_IGNORED: "transfer limit ignored", F_SHORT_ACCEPTED: "short data phase accepted",
             F_BOUNCE_WRONG: "bounced read wrong", F_STALL_DESYNC: "stalled data phase left the CSW queued",
             F_NO_RECOVERY: "no reset recovery",
             F_UNIT_ATTENTION: "UNIT ATTENTION after a reset ate the retry - a part-written file",
             F_LATE_EVENT: "a late transfer event was taken as the next transfer's completion",
             F_SIZE_WRONG: "the inbound window or the DMA check does not follow the memory fitted"}
    return ", ".join(v for k, v in names.items() if mask & k) or "none"


def git_show(rev: str, path: str) -> str:
    return subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT, check=True,
                          capture_output=True, text=True, encoding="utf-8").stdout.replace("\r\n", "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP") or str(LOCAL_INTERP))
    args = ap.parse_args()
    compiler = emitted.required_path(args.compiler, "PMF_COMPILER")
    a64 = emitted.load_interpreter(emitted.required_path(args.interp, "PMF_A64_INTERP"))

    pcie = (ROOT / PCIE).read_text(encoding="utf-8").replace("\r\n", "\n")
    msc = (ROOT / USBMSC).read_text(encoding="utf-8").replace("\r\n", "\n")
    m = re.search(r"^#PCIE_INBOUND_SIZE_CODE\s*=\s*(\d+)", pcie, re.M)
    b = re.search(r"^#PCIE_INBOUND_BYTES\s*=\s*\$([0-9A-Fa-f]+)", pcie, re.M)
    if not m or not b or (1 << (int(m.group(1)) + 15)) != int(b.group(1), 16):
        raise SystemExit("dma window gate: #PCIE_INBOUND_BYTES is not 1 << (#PCIE_INBOUND_SIZE_CODE + 15)")

    xhci = (ROOT / XHCI).read_text(encoding="utf-8").replace("\r\n", "\n")
    mutants = (
        ("PcieDmaOk answers from the programmed window alone, forgetting the 3 GiB erratum", PCIE,
         "  limit = #PCIE_DMA_LIMIT\n  If PcieInboundBytes() < limit\n", "  limit = PcieInboundBytes()\n  If PcieInboundBytes() < limit\n"),
        ("the window is programmed 1 GiB again (build 173)", PCIE,
         "  pcie_Poke(#PCIE_MISC_RC_BAR2_CONFIG_LO, code)", "  pcie_Poke(#PCIE_MISC_RC_BAR2_CONFIG_LO, 15)"),
        ("SCB0 left at 1 GiB", PCIE,
         "code << 27)", "15 << 27)"),
        # The window stops following the memory: back to one constant for
        # every board, which is a gigabyte too wide on a 1 GB one.
        ("the inbound size code is the constant again, not the memory fitted", PCIE,
         "  code = PcieInboundSizeCode()", "  code = #PCIE_INBOUND_SIZE_CODE"),
        # And the DMA check stops following it: on a board whose window is
        # rounded up past its memory, the only limit that knows where memory
        # ends is gone, and buffers past the end of DRAM are approved.
        ("PcieDmaOk ignores the memory fitted and answers from the window alone", PCIE,
         "  If pcie_memBytes > 0 And pcie_memBytes < limit\n    limit = pcie_memBytes\n  EndIf\n", ""),
        ("no cache invalidate after a read", XHCI,
         "  If n > 0\n    xh_Inval(*buf, n)\n  EndIf", ""),
        ("a refused SYNCHRONIZE CACHE always counts as a flush", USBMSC,
         "  If msc_senseKey = #SCSI_SENSE_ILLEGAL_REQUEST\n    If msc_senseAsc = #SCSI_ASC_INVALID_OPCODE\n",
         "  If 1 = 1\n    If 1 = 1\n"),
        ("only one of the two 'no such command' answers is accepted", USBMSC,
         "    If msc_senseAsc = #SCSI_ASC_INVALID_CDB_FIELD\n      msc_err = #MSC_ERR_NONE\n      ProcedureReturn 1\n    EndIf\n", ""),
        ("the flush decides on an older command's sense data", USBMSC,
         "  If msc_senseValid = 0\n    ProcedureReturn 0\n  EndIf\n", ""),
        ("UNIT ATTENTION is read and then ignored - the command is not repeated", USBMSC,
         "              again = 1\n", ""),
        ("the event ring is not drained before the rings are reset", XHCI,
         "  xh_DrainEvents()\n", ""),
        ("Stop Endpoint only when the endpoint reads RUNNING", XHCI,
         "  xh_CommandEp(#XHCI_TRB_STOP_RING, 0, 0, xh_mscSlot, xh_dciOut, #XHCI_TMO_EVENT_MS)\n"
         "  xh_CommandEp(#XHCI_TRB_STOP_RING, 0, 0, xh_mscSlot, xh_dciIn, #XHCI_TMO_EVENT_MS)\n",
         "  If xh_EpStateAt(xh_mscSlot, xh_dciOut) = #XHCI_EP_STATE_RUNNING\n"
         "    xh_CommandEp(#XHCI_TRB_STOP_RING, 0, 0, xh_mscSlot, xh_dciOut, #XHCI_TMO_EVENT_MS)\n"
         "  EndIf\n"
         "  If xh_EpStateAt(xh_mscSlot, xh_dciIn) = #XHCI_EP_STATE_RUNNING\n"
         "    xh_CommandEp(#XHCI_TRB_STOP_RING, 0, 0, xh_mscSlot, xh_dciIn, #XHCI_TMO_EVENT_MS)\n"
         "  EndIf\n"),
        # "a failed command is ignored and its buffer taken as data" was tried
        # and is EQUIVALENT here: the same chunk then fails the byte-count and
        # residue check a line later, which the residue mutant covers.
        ("a stalled data phase returns without reading the status wrapper", USBMSC,
         "      If XhciLastError() <> #XHCI_ERR_STALL\n        msc_needReset = 1\n        ProcedureReturn msc_Fail(#MSC_ERR_DATA)\n      EndIf",
         "      If 1 = 1\n        msc_needReset = 1\n        ProcedureReturn msc_Fail(#MSC_ERR_DATA)\n      EndIf"),
        ("no reset recovery (build 173's msc_Command)", USBMSC,
         "    If msc_ResetRecovery() = 0\n", "    If 1 = 1\n"),
        ("the residue is not checked", USBMSC,
         "    If msc_lastData <> len Or msc_lastResidue <> 0", "    If msc_lastData < 0"),
    )

    with tempfile.TemporaryDirectory(prefix="anvil-dma-window-") as td:
        work = Path(td)
        result, steps = execute(a64, build(compiler, work, program(pcie, msc, xhci), "fixed"))
        print(f"  tree under test: {describe(result)} ({steps:,} instructions)")
        if result != 0:
            print("usb_dma_window_emitted_check: FAIL - the tree under test fails: " + describe(result))
            return 1
        broken, _ = execute(a64, build(compiler, work, program(git_show(BROKEN_REV, PCIE), git_show(BROKEN_REV, USBMSC), git_show(BROKEN_REV, XHCI)), "b173"))
        print(f"  build 173 ({BROKEN_REV}): {describe(broken)}")
        if broken & SILICON_173 != SILICON_173:
            print(f"usb_dma_window_emitted_check: FAIL - build 173's code gives {broken} ({describe(broken)}), "
                  f"not the silicon failure {SILICON_173} ({describe(SILICON_173)}): this gate would not have caught it")
            return 1
        caught = 0
        for index, (label, rel, old, new) in enumerate(mutants):
            srcs = {PCIE: pcie, USBMSC: msc, XHCI: xhci}
            if srcs[rel].count(old) != 1:
                raise SystemExit(f"dma window gate: mutant anchor broken: {label}")
            srcs[rel] = srcs[rel].replace(old, new)
            p_src, m_src, x_src = srcs[PCIE], srcs[USBMSC], srcs[XHCI]
            r, _ = execute(a64, build(compiler, work, program(p_src, m_src, x_src), f"mut{index}"))
            if r == 0:
                print(f"usb_dma_window_emitted_check: FAIL - mutant escaped: {label}")
                return 1
            print(f"  RED as required ({describe(r)}): {label}")
            caught += 1
    print(f"usb_dma_window_emitted_check: PASS - the tree gives no failure; build 173's code reproduces "
          f"the silicon failure exactly; {caught} mutants rejected")
    return 0


if __name__ == "__main__":
    sys.exit(main())

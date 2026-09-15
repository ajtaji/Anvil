#!/usr/bin/env python3
r"""Executable gate for RaspberryPi4/Lib/link.pi4 - THE NET PUMP, driven
through a FIXTURE LINK.

      python tools/a64/a64_netpump_check.py
      python tools/a64/a64_netpump_check.py --mutate      (all cores)

WHY THIS FILE EXISTS
--------------------
link.pi4 is the one IP layer's pump: one frame in, through NetInput, and
its reply out, over whichever link the policy chose.  Every network
command in the monitor rides it - net, ping, dns, dhcp, get, put, tcp and
http get - and until this file was written NO GATE ANYWHERE TOUCHED IT.
tools/a64/a64_anvil_check.py says so out loud in its own "what is not
covered" list: "the pump ... which needs a modelled MAC, PHY, mailbox and
TFTP server all at once, and no such harness exists in this tree".

That sentence was true of the pump as it stood in 2026-08-27, when it was
written out by hand at seventeen call sites against one MAC driver.  It
stopped being true on 2026-09-04, when the drivers went behind
Anvil/Hal/hal.pbi's HwLink* seam - and nobody wrote the gate the seam had
just made possible.  A seam whose whole justification is that the thing
above it can now be tested without the hardware, and then is not tested,
has bought nothing.

SO THERE IS NO MODELLED MAC HERE, AND NO PHY, AND NO MAILBOX.  The
sixteen HwLink* names are answered by a FIXTURE inside the generated
harness: a queue of frames this file pushes in, a capture buffer it reads
back, and three switches for the board hooks.  That is the entire device
model, and it is enough, because the pump's job is not to drive a
controller - it is to get the ORDER right.

WHAT IS PROVEN, AND WHY EACH IS DIFFERENT EVIDENCE
--------------------------------------------------
  A. ONE FRAME IN, THROUGH NetInput, AND THE REPLY OUT.  A real ICMP echo
     request, built here from the RFC's field layout and not copied out
     of the library, goes in through the fixture link; the pump must
     hand it to net.pi4, tell the board #NET_IN_REPLY, and offer the
     frame to the automatic dispatcher (NetServiceInput), which puts
     net.pi4's staged echo reply on the wire of the interface the
     request arrived on.  The dispatcher OWNS that frame, so the pump
     answers its own caller #NET_IN_IGNORED and counts it as consumed.  The reply is
     graded byte for byte and both counters - frames in, frames out -
     must have moved by exactly one.  This is the whole point of the
     file in one case.

  B. LinkTxStaged PUTS EXACTLY WHAT net.pi4 STAGED, AND NOTHING WHEN
     NOTHING IS STAGED.  The staged bytes are read out of NetOutBuf() in
     one script step and the wire is captured in the next, and the two
     are compared HERE - the harness never compares them, so a library
     that transmitted a truncated or padded frame cannot agree with
     itself into a pass.  The empty case is separate and is checked by
     capturing the wire and requiring it EMPTY, not by trusting a return
     code: "nothing staged" is the normal answer after a NetInput with no
     reply to make, and an unforced empty frame is the Sorcerer's
     Apprentice bug wearing a different hat.

  C. LinkTxMax IS THE SELECTED KIND'S CEILING AND MOVES WITH THE
     SELECTION.  The two fixture kinds are given deliberately different
     ceilings, the selection is changed underneath, and the answer must
     follow.  A ceiling that is right for one link and stale for the
     other is a TCP segment built too long for the wire it goes out of,
     which presents as a transfer that works on the bench and fails
     through one switch.  The 1514 clamp is checked too, by giving a
     fixture kind a ceiling ABOVE it.

  D. LinkUp IS FALSE BEFORE A SELECTION AND AFTER LinkForget.  Both, and
     they are different facts: the first is the state at reset and the
     second is the state after `net link auto`, and a policy layer that
     conflated them would keep sending over an interface that
     had just been released.

  E. THE BOARD'S FIRST REFUSAL COMES BEFORE THE IP LAYER, AND A CONSUMED
     FRAME NEVER REACHES NetInput.  The same echo request is fed twice,
     with one fixture switch changed: consumed, the wire must be EMPTY,
     the return must be #NET_IN_IGNORED and net.pi4's ARP cache must not
     have learned the sender.  That last one is the airtight half - it is
     a side effect only NetInput has, so an unchanged cache is proof the
     frame never got there, rather than proof that no reply was staged.

  F. HwLinkNoteRx IS TOLD THE IP LAYER'S VERDICT FOR EVERY FRAME.  The
     fixture counts the calls and remembers the last verdict and kind.
     The case that matters is the UDP datagram the board's OfferUdp hook
     takes back: the pump returns #NET_IN_IGNORED to its caller and must
     still have told the board #NET_IN_UDP, because the verdict the board
     is owed is the IP layer's and not the pump's.  Getting that wrong
     made a self-heal fire in the middle of a working `http get` on
     silicon.

  G. THE RASPBERRY PI 4 ONLY.  This tree has no HwLink* backend for the
     Arduino UNO Q (nothing under ArduinoQ/Board or ArduinoQ/Lib defines
     the seam), so there is no second board to build the harness for.
     The day one is added, a --target for it belongs here.

WHAT IS NOT COVERED, said here rather than left to be assumed
-------------------------------------------------------------
  * ANY REAL DRIVER.  GENET, CYW43, SLIP and the file channel are all
    absent.  This gate proves the pump's order and arithmetic, not that
    any board can move a byte.  Those are gated separately and pass:
    a64_genet_check.py, a64_qslip_check.py, a64_qnetproof_check.py.
  * THE POLICY'S FACTS.  LinkSelect is exercised with the four numbers as
    arguments; whether a board reports its carrier and its address
    correctly is the board's, and HwLinkOpen is where that lives.
  * TIMING.  The receive deadline is passed to the fixture and recorded,
    but nothing here blocks: a fixture with a frame ready returns it at
    once.  A driver that ignored its deadline would not be caught here.
  * THE DISPATCHER ITSELF.  NetServiceInput lives in
    Anvil/Core/netconsole.pbi and pulls the console, the DHCP client, NTP
    and TCP with it; the harness supplies a stand-in that keeps the two
    decisions graded here (a staged reply goes out, a UDP datagram the
    board's hook takes is consumed).  The console side of the real one is
    graded by tools/a64/a64_wificon_check.py.
  * THE COMMANDS.  net, ping, dns, dhcp, get and put are above this file
    and print; they are not in this image.

THE CLOCK IS A FIXTURE AND SAYS SO.  link.pi4 uses millis() for exactly
one thing - the timestamp on a change of link - so the harness supplies a
counter the script advances rather than pulling a board's timer driver
into the image.  net.pi4 reads CNTPCT_EL0 itself, in assembly, for its
ARP expiry, and the emulator answers that: one tick per STEPS_PER_TICK
instructions, so a run is reproducible.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import struct
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
# THE TREE UNDER TEST IS THE ONE THIS SCRIPT LIVES IN. A root pinned into
# the file made another gate build a DIFFERENT working copy with that
# copy's compiler and print the answer as this tree's.
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))

from a64_interp import A64, attach_symbols                       # noqa: E402
from a64_target import TARGETS, apply_target, patch_harness      # noqa: E402

PMFC = os.environ.get("PMF_COMPILER") or "PureMetalForge.exe"  # rebound from --compiler
# Every compile resolves includes from THIS tree only.
BUILD_ENV = dict(os.environ, PMF_ROOT=str(ROOT))
LIB = ROOT / "RaspberryPi4" / "Lib" / "link.pi4"
WORK = ROOT / "_work" / "netpump"

# ---- the image contract. apply_target() rebinds every one of these as
# ---- the first thing main() does, so a gate run with --target unoq
# ---- builds and grades the Q's image and never the Pi 4's.
TFLAG = "pi4"
TARGET_NAME = "pi4"
TARGET_WHAT = TARGETS["pi4"]["what"]
LOAD = TARGETS["pi4"]["load"]
STACK = TARGETS["pi4"]["stack"]
H_SCRIPT = TARGETS["pi4"]["script"]
H_RESULT = TARGETS["pi4"]["script"] + 0x00800000
CONSOLE_INCLUDE = TARGETS["pi4"]["console"]
SINK_LO = TARGETS["pi4"]["uart_lo"]
SINK_HI = TARGETS["pi4"]["uart_hi"]

LOADER_LR = 0xDEADBEE0

# The Pi 4's counter runs at 54 MHz and the Q's at 19.2 MHz. net.pi4's
# ARP expiry is the only thing in this image that reads it and the gate
# never runs long enough to expire an entry, so one figure serves both -
# but it is set from the target rather than written down, because a gate
# that quietly modelled the wrong clock would still pass and would stop
# being evidence about the board it names.
CNTFRQ_BY_TARGET = {"pi4": 54_000_000}
STEPS_PER_TICK = 8
STEP_LIMIT = 200_000_000

# ---- net.pi4's own vocabulary, restated INDEPENDENTLY. If the two ever
# ---- disagree this gate goes red and one of them is wrong.
NET_IN_IGNORED = 0
NET_IN_REPLY = 1
NET_IN_UDP = 2
NET_IN_PONG = 3
NET_IN_LEARNED = 4
NET_IN_TCP = 5

# hal.pi4's link kinds, likewise restated.
HW_LINK_NONE = 0
HW_LINK_WIRED = 1
HW_LINK_WIFI = 2

# link.pi4's own two, likewise.
LINK_RX_NONE = -1
LINK_ETH_MAX = 1514

ET_IPV4 = 0x0800
ET_ARP = 0x0806
ET_EAPOL = 0x888E


# =====================================================================
#  THE FRAMES, WRITTEN FROM THE RFCs AND NOT FROM THE LIBRARY
# =====================================================================
def ip4(a: int, b: int, c: int, d: int) -> int:
    return (a << 24) | (b << 16) | (c << 8) | d


def eth(dst: bytes, src: bytes, ethertype: int, payload: bytes) -> bytes:
    return dst + src + struct.pack(">H", ethertype) + payload


def ones_complement(data: bytes, seed: int = 0) -> int:
    total = seed
    if len(data) % 2:
        data = data + b"\x00"
    for i in range(0, len(data), 2):
        total += (data[i] << 8) | data[i + 1]
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def ipv4(src: int, dst: int, proto: int, payload: bytes, ident: int) -> bytes:
    hdr = bytearray(20)
    hdr[0] = 0x45
    struct.pack_into(">H", hdr, 2, 20 + len(payload))
    struct.pack_into(">H", hdr, 4, ident)
    hdr[8] = 64
    hdr[9] = proto
    struct.pack_into(">I", hdr, 12, src)
    struct.pack_into(">I", hdr, 16, dst)
    struct.pack_into(">H", hdr, 10, ones_complement(bytes(hdr)))
    return bytes(hdr) + payload


def icmp_echo(msg_type: int, ident: int, seq: int, payload: bytes) -> bytes:
    body = bytearray(8)
    body[0] = msg_type
    struct.pack_into(">H", body, 4, ident)
    struct.pack_into(">H", body, 6, seq)
    body += payload
    struct.pack_into(">H", body, 2, ones_complement(bytes(body)))
    return bytes(body)


def udp(src: int, dst: int, sport: int, dport: int, payload: bytes) -> bytes:
    body = bytearray(8)
    struct.pack_into(">H", body, 0, sport)
    struct.pack_into(">H", body, 2, dport)
    struct.pack_into(">H", body, 4, 8 + len(payload))
    body += payload
    # THE UDP CHECKSUM IS OPTIONAL OVER IPv4 AND ZERO MEANS "NOT
    # COMPUTED" [RFC 768]. It is left zero here on purpose: a datagram
    # this gate builds is not evidence about checksums, and a wrong one
    # would make the case fail for a reason that is this file's fault.
    return bytes(body)


def arp(op: int, sha: bytes, spa: int, tha: bytes, tpa: int) -> bytes:
    """RFC 826's payload, in the order the wire carries it."""
    return (struct.pack(">HHBBH", 1, ET_IPV4, 6, 4, op)
            + sha + struct.pack(">I", spa)
            + tha + struct.pack(">I", tpa))


# =====================================================================
#  THE HARNESS
# =====================================================================
# A fixed source file.  Everything that varies arrives as DATA in memory,
# so this text is identical for the clean library and for every mutant
# and no test case is ever expressed in the source language.
(OP_RESET, OP_HAS, OP_TXMAX_SET, OP_SELECT, OP_USEKIND, OP_FORGET,
 OP_STATE, OP_FEED, OP_PUMP, OP_STAGED, OP_TXCLEAR, OP_TXSTAGED,
 OP_HOOKS, OP_NOTE, OP_COUNTS, OP_NETCFG, OP_ARPCOUNT, OP_RXSEEN,
 OP_STAGEARP, OP_STAGEUDP, OP_BIND, OP_TICK, OP_IDENT, OP_TXC,
 OP_WIRE, OP_WIREMODE) = range(1, 27)

HARNESS = r'''
; ======================================================================
;  netpumpharness.pi4 - GENERATED BY tools/a64/a64_netpump_check.py.
;                       DO NOT EDIT.
; ======================================================================
;  It reads a script of library calls out of memory at #H_SCRIPT, runs
;  them, and writes a result record for each into #H_RESULT.
;
;  SCRIPT RECORD, 24 bytes then `ln` bytes of blob, padded to 4:
;     +0 op  +4 a  +8 b  +12 c  +16 d  +20 ln  +24 blob
;  op 0 ends the script.
;
;  RESULT RECORD, 20 bytes then `n` bytes of blob, padded to 4:
;     +0 op  +4 result  +8 extra1  +12 extra2  +16 n  +20 blob
;
;  THE FIXTURE LINK IS THE FIRST BLOCK BELOW. It is all sixteen HwLink*
;  names from Anvil/Hal/hal.pbi, backed by a queue of frames and a
;  capture buffer this file's caller fills and reads. It is a GATE
;  FIXTURE and it never goes near a board; the real backend is
;  RaspberryPi4/Board/hw_link.pi4.
;
;  TWO KINDS, AND THEY BEHAVE DIFFERENTLY ON PURPOSE. #HW_LINK_WIRED
;  fills the caller's buffer and hands that address back, the way a MAC
;  that reads a descriptor ring does; #HW_LINK_WIFI keeps its own frame
;  buffer and hands THAT back, copying nothing, the way a radio with one
;  receive buffer does. hal.pi4 calls that the seam's one asymmetry and
;  it is deliberate, so a pump that ignored HwLinkRxPtr and always read
;  the buffer it offered would pass on one kind and fail on the other.
;
;  millis() IS A FIXTURE COUNTER. link.pi4 uses it for one thing - the
;  timestamp on a change of link - and pulling a board's timer driver in
;  to supply it would put a chip in an image that is testing a policy.
;  net.pi4 reads CNTPCT_EL0 itself, in assembly, and the emulator
;  answers that.
; ======================================================================
XIncludeFile "RaspberryPi4/Lib/uart.pi4"

#H_SCRIPT = $06000000
#H_RESULT = $06800000

#FX_FRAME_MAX = 2048
#FX_QUEUE_MAX = 16
#FX_TX_MAX    = 16384

; The receive queue: whole 802.3 frames, one slot each.
Global Dim fxQ.a[#FX_QUEUE_MAX * #FX_FRAME_MAX]
Global Dim fxQLen.i[#FX_QUEUE_MAX]
Global fxQHead.i
Global fxQTail.i

; The radio-shaped kind's own receive buffer - the one it hands a
; pointer to instead of copying.
Global Dim fxOwn.a[#FX_FRAME_MAX]

; The wire.
Global Dim fxTx.a[#FX_TX_MAX]
Global fxTxLen.i
Global fxTxKind.i                  ; which kind the last frame went out of
Global fxTxCalls.i

; What this fixture board HAS, and what each kind will carry.
Global fxHasWired.i = 1
Global fxHasWifi.i = 1
Global fxMaxWired.i = 1514
Global fxMaxWifi.i = 1500

; The three hooks. fxRawEat is an ethertype to consume before the IP
; layer sees it, or 0 for none; fxUdpEat is 1 to take every UDP datagram
; back the way a wireless console does.
Global fxRawEat.i
Global fxUdpEat.i

; TWO SWITCHES THAT MAKE THE FIXTURE A WORSE BACKEND ON PURPOSE.
;
; fxNoMax = 1 makes the wire accept a frame longer than the kind's
; ceiling. A REAL BACKEND MAY OR MAY NOT REFUSE ONE - genet.pi4 does,
; and a driver that truncated instead would be within its rights as far
; as this seam is concerned - so the ceiling has to be enforced by the
; POLICY layer as well, which is what link.pi4's own comment says. With
; the fixture also refusing, a link.pi4 that dropped its check would
; look identical from outside and the gate would prove nothing.
;
; fxSendFail = 1 makes the wire refuse a frame that is perfectly legal.
; That is a stuck transmit engine, and it is the only way to reach the
; path where a send fails for a reason the length does not explain.
Global fxNoMax.i
Global fxSendFail.i
Global fxRawCalls.i
Global fxUdpCalls.i
Global fxNoteCalls.i
Global fxNoteLastR.i = -999
Global fxNoteLastKind.i = -999

; The two synthetic hardware addresses, one per kind, so that a pump
; handing back the wrong one is visible.
Global Dim fxMacWired.a[6]
Global Dim fxMacWifi.a[6]

; The fixture clock. Advanced by the script, never by itself.
Global fxMs.i

; Where the last received frame actually landed, per the seam's RxPtr.
Global fxRxPtr.i

Procedure.i millis()
  ProcedureReturn fxMs
EndProcedure

XIncludeFile "Anvil/Hal/hal.pbi"

Procedure.i HwLinkHas(kind.i)
  If kind = #HW_LINK_WIRED
    ProcedureReturn fxHasWired
  EndIf
  If kind = #HW_LINK_WIFI
    ProcedureReturn fxHasWifi
  EndIf
  ProcedureReturn 0
EndProcedure

; HwLinkReady - CAN THIS LINK CARRY A FRAME RIGHT NOW. Added to this
; harness on 2026-09-07 with Anvil/Core/netif.pbi, which asks it before
; it will call an interface usable. Both of this fixture's links are
; always ready: this gate is about what the PUMP does with a frame, and
; a link that could not carry one would simply remove every case.
Procedure.i HwLinkReady(kind.i)
  ProcedureReturn HwLinkHas(kind)
EndProcedure

; netif.pi4 also reads LinkPin(), and RaspberryPi4/Lib/link.pi4 - the
; library UNDER TEST - defines it, so nothing is supplied for it here:
; the call is resolved forward to the real one, which is what should be
; graded anyway.

Procedure.i HwLinkName(kind.i)
  If kind = #HW_LINK_WIRED
    ProcedureReturn "the fixture wired link"
  EndIf
  If kind = #HW_LINK_WIFI
    ProcedureReturn "the fixture radio link"
  EndIf
  ProcedureReturn "an interface this fixture does not have"
EndProcedure

Procedure.i HwLinkTxMax(kind.i)
  If kind = #HW_LINK_WIRED
    ProcedureReturn fxMaxWired
  EndIf
  If kind = #HW_LINK_WIFI
    ProcedureReturn fxMaxWifi
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i HwLinkSend(kind.i, buf.i, n.i, ms.i)
  Define i.i
  fxTxCalls = fxTxCalls + 1
  If fxSendFail <> 0
    ProcedureReturn 0
  EndIf
  If n <= 0
    ProcedureReturn 0
  EndIf
  If HwLinkHas(kind) = 0
    ProcedureReturn 0
  EndIf
  If fxNoMax = 0
    If n > HwLinkTxMax(kind)
      ProcedureReturn 0
    EndIf
  EndIf
  i = 0
  While i < n
    If fxTxLen < #FX_TX_MAX
      fxTx[fxTxLen] = PeekA(buf + i)
      fxTxLen = fxTxLen + 1
    EndIf
    i = i + 1
  Wend
  fxTxKind = kind
  ProcedureReturn 1
EndProcedure

Procedure.i HwLinkRecv(kind.i, buf.i, max.i, ms.i)
  Define n.i
  Define i.i
  Define src.i
  fxRxPtr = 0
  If HwLinkHas(kind) = 0
    ProcedureReturn 0
  EndIf
  If fxQHead >= fxQTail
    ProcedureReturn 0
  EndIf
  n = fxQLen[fxQHead]
  src = @fxQ[fxQHead * #FX_FRAME_MAX]
  fxQHead = fxQHead + 1
  If n > max
    n = max
  EndIf
  If kind = #HW_LINK_WIFI
    ; A driver with its own single receive buffer. Nothing is copied
    ; into the caller's; the pointer is handed back instead.
    i = 0
    While i < n
      fxOwn[i] = PeekA(src + i)
      i = i + 1
    Wend
    fxRxPtr = @fxOwn[0]
    ProcedureReturn n
  EndIf
  i = 0
  While i < n
    PokeB(buf + i, PeekA(src + i))
    i = i + 1
  Wend
  fxRxPtr = buf
  ProcedureReturn n
EndProcedure

Procedure.i HwLinkRxPtr(kind.i)
  ProcedureReturn fxRxPtr
EndProcedure

Procedure.i HwLinkMacPtr(kind.i)
  If kind = #HW_LINK_WIRED
    ProcedureReturn @fxMacWired[0]
  EndIf
  If kind = #HW_LINK_WIFI
    ProcedureReturn @fxMacWifi[0]
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i HwLinkOfferRaw(kind.i, p.i, n.i)
  Define et.i
  fxRawCalls = fxRawCalls + 1
  If fxRawEat = 0
    ProcedureReturn 0
  EndIf
  If n < 14
    ProcedureReturn 0
  EndIf
  et = (PeekA(p + 12) << 8) | PeekA(p + 13)
  If et = fxRawEat
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i HwLinkOfferUdp(kind.i, p.i)
  fxUdpCalls = fxUdpCalls + 1
  ProcedureReturn fxUdpEat
EndProcedure

Procedure HwLinkNoteRx(kind.i, r.i)
  fxNoteCalls = fxNoteCalls + 1
  fxNoteLastR = r
  fxNoteLastKind = kind
EndProcedure

Procedure.i HwLinkSpeed(kind.i)
  If kind = #HW_LINK_WIRED
    ProcedureReturn 1000
  EndIf
  ProcedureReturn #HW_LINK_SPEED_UNKNOWN
EndProcedure

Procedure.i HwLinkDuplex(kind.i)
  If kind = #HW_LINK_WIRED
    ProcedureReturn #HW_LINK_DUPLEX_FULL
  EndIf
  ProcedureReturn #HW_LINK_DUPLEX_UNKNOWN
EndProcedure

Procedure.i HwLinkWhyText(kind.i)
  If kind = #HW_LINK_WIRED
    ProcedureReturn "the fixture wired link has nothing wrong with it"
  EndIf
  ProcedureReturn ""
EndProcedure

Procedure.i HwLinkOpen(needIp.i)
  ProcedureReturn 0
EndProcedure

Procedure.i HwLinkClose()
  ProcedureReturn 0
EndProcedure

Procedure HwLinkSayDetail()
EndProcedure

; The seam's seventeenth name. This fixture has no board state behind an
; address, so it records the call and nothing else - a name a board must
; define even when it has nothing to do (Anvil/Hal/hal.pbi). It is not
; exercised by this file's cases; the arming it exists for is graded by
; tools/a64/a64_wificon_check.py, over a fixture RADIO.
Global fxAddrBoundCalls.i
Global fxAddrBoundKind.i = -999
Procedure HwLinkAddressBound(kind.i, ip.i, mask.i, gw.i)
  fxAddrBoundCalls = fxAddrBoundCalls + 1
  fxAddrBoundKind = kind
EndProcedure

XIncludeFile "Anvil/Network/net.pbi"
; ONE ADDRESS RECORD PER INTERFACE. The library under test hands every
; frame it takes off the wire to NetInput, and since 2026-09-07 it must
; point the one IP layer at the interface that frame arrived on first -
; so the table is in this image rather than stubbed, because a stub
; would grade a copy of that rule instead of the rule. The pin it reads
; is the fixture LinkPin below.
XIncludeFile "Anvil/Core/netif.pbi"

; THE AUTOMATIC DISPATCHER, AS A FIXTURE. link.pi4 offers every frame it
; delivered to NetServiceInput, which on the board lives in
; Anvil/Core/netconsole.pbi and owns ARP and ICMP replies, TCP, the DHCP
; client and console UDP. That file brings the console, the DHCP client,
; NTP and TCP with it, so this stand-in keeps exactly the two decisions
; this gate grades: a staged reply leaves by the interface the frame
; arrived on (through link.pi4's own LinkTxStagedOn), and a UDP datagram
; the board's hook takes back is consumed. Everything else is left to
; the caller, which is what the real one does with command-owned UDP.
Procedure.i NetServiceInput(kind.i, *frame, rc.i)
  If rc = #NET_IN_REPLY
    LinkTxStagedOn(kind)
    ProcedureReturn 1
  EndIf
  If rc = #NET_IN_UDP
    If HwLinkOfferUdp(kind, *frame) <> 0
      ProcedureReturn 1
    EndIf
  EndIf
  ProcedureReturn 0
EndProcedure

XIncludeFile "__LIB__"

Procedure fxReset()
  Define i.i
  fxQHead = 0
  fxQTail = 0
  fxTxLen = 0
  fxTxKind = -1
  fxTxCalls = 0
  fxRawEat = 0
  fxUdpEat = 0
  fxNoMax = 0
  fxSendFail = 0
  fxRawCalls = 0
  fxUdpCalls = 0
  fxNoteCalls = 0
  fxNoteLastR = -999
  fxNoteLastKind = -999
  fxHasWired = 1
  fxHasWifi = 1
  fxMaxWired = 1514
  fxMaxWifi = 1500
  fxRxPtr = 0
  fxMs = 0
  For i = 0 To 5
    fxMacWired[i] = 0
    fxMacWifi[i] = 0
  Next
  fxMacWired[0] = $02 : fxMacWired[1] = $11 : fxMacWired[2] = $22
  fxMacWired[3] = $33 : fxMacWired[4] = $44 : fxMacWired[5] = $55
  fxMacWifi[0] = $02 : fxMacWifi[1] = $AA : fxMacWifi[2] = $BB
  fxMacWifi[3] = $CC : fxMacWifi[4] = $DD : fxMacWifi[5] = $EE
  NetInit()
  LinkForget()
EndProcedure

Procedure.i Main()
  Define p.i
  Define q.i
  Define op.i
  Define a.i
  Define b.i
  Define c.i
  Define d.i
  Define ln.i
  Define blob.i
  Define r.i
  Define e1.i
  Define e2.i
  Define n.i
  Define src.i
  Define i.i

  fxReset()
  p = #H_SCRIPT
  q = #H_RESULT

  Repeat
    op = PeekN(p)
    If op = 0
      Break
    EndIf
    a    = PeekN(p + 4)
    b    = PeekN(p + 8)
    c    = PeekN(p + 12)
    d    = PeekN(p + 16)
    ln   = PeekN(p + 20)
    blob = p + 24

    r = 0
    e1 = 0
    e2 = 0
    n = 0
    src = 0

    If op = 1
      fxReset()
      r = 1
    ElseIf op = 2
      If a = #HW_LINK_WIRED
        fxHasWired = b
      Else
        fxHasWifi = b
      EndIf
      r = HwLinkHas(a)
    ElseIf op = 3
      If a = #HW_LINK_WIRED
        fxMaxWired = b
      Else
        fxMaxWifi = b
      EndIf
      r = HwLinkTxMax(a)
    ElseIf op = 4
      r = LinkSelect(#HW_LINK_NONE, a, b, c, d)
      e1 = LinkWhy()
      e2 = LinkKind()
    ElseIf op = 5
      r = LinkUseKind(a)
      e1 = LinkWhy()
      e2 = LinkKind()
    ElseIf op = 6
      LinkForget()
      r = LinkUp()
      e1 = LinkKind()
    ElseIf op = 7
      r = LinkUp()
      e1 = LinkKind()
      e2 = LinkTxMax()
    ElseIf op = 8
      ; queue one frame for the fixture link
      If fxQTail < #FX_QUEUE_MAX
        src = fxQTail * #FX_FRAME_MAX
        i = 0
        While i < ln
          If i < #FX_FRAME_MAX
            fxQ[src + i] = PeekA(blob + i)
          EndIf
          i = i + 1
        Wend
        fxQLen[fxQTail] = ln
        fxQTail = fxQTail + 1
        r = 1
      EndIf
    ElseIf op = 9
      r = LinkPumpNet(a)
      e1 = LinkRxLen()
      e2 = LinkRxFrames()
      ; the wire, as it stands after the pump
      n = fxTxLen
      src = @fxTx[0]
    ElseIf op = 10
      ; what net.pi4 has staged right now, byte for byte
      r = NetOutLen()
      n = r
      src = NetOutBuf()
    ElseIf op = 11
      fxTxLen = 0
      fxTxKind = -1
      fxTxCalls = 0
      r = 1
    ElseIf op = 12
      r = LinkTxStaged()
      e1 = LinkTxCount()
      e2 = LinkTxFails()
      n = fxTxLen
      src = @fxTx[0]
    ElseIf op = 13
      fxRawEat = a
      fxUdpEat = b
      r = 1
    ElseIf op = 14
      r = fxNoteCalls
      e1 = fxNoteLastR
      e2 = fxNoteLastKind
    ElseIf op = 15
      r = LinkRxFrames()
      e1 = LinkEapolCount()
      e2 = LinkConsoleCount()
    ElseIf op = 16
      ; d is the interface the address belongs to
      NetInit()
      NetSetMac(d, blob)
      r = NetSetIPv4(d, a, b, c)
      e1 = NetError()
    ElseIf op = 17
      r = NetArpCount(a)
    ElseIf op = 18
      ; the bytes the pump says the last frame occupied, read back
      ; through LinkRxPtr - which is how a caller reaches a frame that
      ; landed in a driver's own buffer.
      r = LinkRxLen()
      e1 = LinkRxPtr()
      n = r
      src = LinkRxPtr()
      If src = 0
        n = 0
      EndIf
    ElseIf op = 19
      r = NetArpRequest(b, a)
      e1 = NetOutLen()
    ElseIf op = 20
      r = NetUdpBuild(d, a, b, c, blob, ln)
      e1 = NetOutLen()
      e2 = NetError()
    ElseIf op = 21
      r = NetUdpBind(b, a)
    ElseIf op = 22
      fxMs = fxMs + a
      r = fxMs
      e1 = LinkSwaps()
      e2 = LinkSince()
    ElseIf op = 23
      ; who does the seam say we are, and what can this link say
      r = LinkSpeed()
      e1 = LinkDuplex()
      e2 = LinkTxCount()
      src = LinkMacPtr()
      If src = 0
        n = 0
      Else
        n = 6
      EndIf
    ElseIf op = 24
      ; THE TRANSMIT COUNTERS ARE CUMULATIVE FOR THE WHOLE RUN and
      ; link.pi4 offers no way to zero them, which is right - a monitor
      ; that reset its own tally between commands could not answer "how
      ; many frames has this board ever refused". So the gate takes a
      ; baseline here and grades DIFFERENCES.
      r = LinkTxCount()
      e1 = LinkTxFails()
      e2 = fxNoteCalls
    ElseIf op = 25
      ; the wire as it stands, and what net.pi4 still has staged, so the
      ; two can be compared by the caller rather than by the harness
      r = fxTxLen
      e1 = NetOutLen()
      n = NetOutLen()
      src = NetOutBuf()
    ElseIf op = 26
      fxNoMax = a
      fxSendFail = b
      r = 1
    EndIf

    PokeN(q, op)
    PokeN(q + 4, r)
    PokeN(q + 8, e1)
    PokeN(q + 12, e2)
    PokeN(q + 16, n)
    If n > 0
      i = 0
      While i < n
        PokeB(q + 20 + i, PeekA(src + i))
        i = i + 1
      Wend
    EndIf

    p = p + 24 + (((ln + 3) / 4) * 4)
    q = q + 20 + (((n + 3) / 4) * 4)
  ForEver

  PokeN(q, 0)
  UartWriteStr("netpumpharness done")
  ProcedureReturn 0
EndProcedure
'''


class Script:
    def __init__(self) -> None:
        self.buf = bytearray()
        self.labels: list[str] = []

    def add(self, op: int, a: int = 0, b: int = 0, c: int = 0,
            d: int = 0, blob: bytes = b"", label: str = "") -> int:
        idx = len(self.labels)
        self.labels.append(label)
        self.buf += struct.pack("<6I", op, a & 0xFFFFFFFF, b & 0xFFFFFFFF,
                                c & 0xFFFFFFFF, d & 0xFFFFFFFF, len(blob))
        self.buf += blob
        while len(self.buf) % 4:
            self.buf.append(0)
        return idx

    def finish(self) -> bytes:
        return bytes(self.buf) + struct.pack("<I", 0)


class Result:
    __slots__ = ("op", "r", "e1", "e2", "blob", "label")

    def __init__(self, op, r, e1, e2, blob, label):
        self.op, self.r, self.e1, self.e2 = op, r, e1, e2
        self.blob, self.label = blob, label


def _signed(raw: int) -> int:
    return raw - 0x100000000 if raw & 0x80000000 else raw


def read_results(mem, labels: list[str]) -> list[Result]:
    out: list[Result] = []
    addr = H_RESULT
    while True:
        def w(off):
            return sum(mem.get(addr + off + i, 0) << (8 * i) for i in range(4))
        op = w(0)
        if op == 0:
            break
        n = w(16)
        if n > 32768:
            raise SystemExit(
                "a result record claims %d bytes, which is longer than any "
                "buffer in this harness.  The result stream is corrupt." % n)
        blob = bytes(mem.get(addr + 20 + i, 0) for i in range(n))
        i = len(out)
        out.append(Result(op, _signed(w(4)), _signed(w(8)), _signed(w(12)),
                          blob, labels[i] if i < len(labels) else "?"))
        addr += 20 + ((n + 3) // 4) * 4
    return out


# =====================================================================
#  BUILD AND RUN
# =====================================================================
def write_harness(lib_include: str, path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = HARNESS.replace("__LIB__", lib_include)
    text = patch_harness(text, globals())
    path.write_text(text, encoding="utf-8")


def build(source: pathlib.Path, out: pathlib.Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [str(PMFC), "--compile", str(source), "-t", TFLAG,
           "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
           "--entry-returns", "-o", str(out)]
    r = subprocess.run(cmd, cwd=ROOT, env=BUILD_ENV, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout:
        raise SystemExit("build failed:\n" + r.stdout)


def run(img: pathlib.Path, script: bytes):
    blob = img.read_bytes()
    cpu = A64()
    mem = cpu.memory
    for i, b in enumerate(blob):
        mem[LOAD + i] = b
    attach_symbols(cpu, img, LOAD)
    for i, b in enumerate(script):
        mem[H_SCRIPT + i] = b
    cpu.pc = LOAD
    cpu.sp = STACK
    cpu.x[30] = LOADER_LR

    console = bytearray()
    steps = [0]
    cntfrq = CNTFRQ_BY_TARGET[TARGET_NAME]

    def load(addr, size):
        # THE ALIGNMENT RULE. This closure replaces A64.load, so the guard
        # has to be called here or the gate models a machine more
        # permissive than the part it certifies.
        cpu.align_guard(addr, size, False)
        return sum(mem.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr, value, size):
        cpu.align_guard(addr, size, True)
        if SINK_LO <= addr <= SINK_HI:
            console.append(value & 0xFF)
        for i in range(size):
            mem[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    plain_step = A64.step.__get__(cpu)

    def step():
        steps[0] += 1
        ins = cpu.fetch(cpu.pc)
        if (ins & 0xFFFFFFE0) == 0xD53BE000:        # MRS Xt, CNTFRQ_EL0
            cpu.x[ins & 31] = cntfrq
            cpu.pc += 4
            return
        if (ins & 0xFFFFFFE0) == 0xD53BE020:        # MRS Xt, CNTPCT_EL0
            cpu.x[ins & 31] = steps[0] // STEPS_PER_TICK
            cpu.pc += 4
            return
        plain_step()

    cpu.step = step
    for _ in range(STEP_LIMIT):
        if cpu.pc == LOADER_LR:
            return cpu, console, steps[0]
        step()
    raise SystemExit("the harness never returned (%d steps)\n%s"
                     % (steps[0], console.decode("latin-1")))


# =====================================================================
#  THE TEST CASES
# =====================================================================
OUR_IP = ip4(192, 168, 7, 20)
MASK = ip4(255, 255, 255, 0)
GW_IP = ip4(192, 168, 7, 1)
PEER_IP = ip4(192, 168, 7, 9)
OTHER_IP = ip4(192, 168, 7, 33)

OUR_MAC = bytes([0x02, 0x11, 0x22, 0x33, 0x44, 0x55])     # fxMacWired
WIFI_MAC = bytes([0x02, 0xAA, 0xBB, 0xCC, 0xDD, 0xEE])    # fxMacWifi
PEER_MAC = bytes([0x02, 0x99, 0x88, 0x77, 0x66, 0x01])
OTHER_MAC = bytes([0x02, 0x99, 0x88, 0x77, 0x66, 0x02])
BCAST = b"\xFF" * 6

PING_ID = 0x4321
PING_SEQ = 7
PING_DATA = bytes((i * 5 + 1) & 0xFF for i in range(24))

UDP_PORT = 5310
UDP_DATA = b"the pump does not read this"


def echo_request(dst_mac: bytes, src_mac: bytes, src_ip: int,
                 dst_ip: int) -> bytes:
    return eth(dst_mac, src_mac, ET_IPV4,
               ipv4(src_ip, dst_ip, 1,
                    icmp_echo(8, PING_ID, PING_SEQ, PING_DATA), 0x1234))


def udp_to_us(sport: int, dport: int) -> bytes:
    return eth(OUR_MAC, PEER_MAC, ET_IPV4,
               ipv4(PEER_IP, OUR_IP, 17,
                    udp(PEER_IP, OUR_IP, sport, dport, UDP_DATA), 0x1235))


def build_script() -> tuple[Script, dict]:
    s = Script()
    at: dict[str, int] = {}

    def a(name, *args, **kw):
        at[name] = s.add(*args, label=name, **kw)

    # =================================================================
    #  D. LinkUp IS FALSE BEFORE A SELECTION
    # =================================================================
    a("reset0", OP_RESET)
    a("up_at_reset", OP_STATE)

    # A pump with no link selected must not touch the fixture at all and
    # must answer #LINK_RX_NONE - not zero, which is a length.
    a("feed_before_select", OP_FEED,
      blob=echo_request(OUR_MAC, PEER_MAC, PEER_IP, OUR_IP))
    a("pump_before_select", OP_PUMP, 10)

    # =================================================================
    #  C. LinkTxMax IS THE SELECTED KIND'S CEILING
    # =================================================================
    a("reset1", OP_RESET)
    a("max_wired_set", OP_TXMAX_SET, HW_LINK_WIRED, 1400)
    a("max_wifi_set", OP_TXMAX_SET, HW_LINK_WIFI, 900)
    a("sel_wired", OP_SELECT, 1, 1, 1, 1)
    a("max_on_wired", OP_STATE)
    a("sel_wifi", OP_SELECT, 0, 0, 1, 1)
    a("max_on_wifi", OP_STATE)
    # A backend that answers above the classic Ethernet maximum must be
    # clamped by the policy layer, not believed.
    a("max_wifi_huge", OP_TXMAX_SET, HW_LINK_WIFI, 9000)
    a("max_clamped", OP_STATE)
    # And a kind with nothing to promise ends up as no link at all.
    a("forget_after_max", OP_FORGET)

    # =================================================================
    #  D (second half). LinkUp IS FALSE AFTER LinkForget
    # =================================================================
    a("reset2", OP_RESET)
    a("sel_for_forget", OP_SELECT, 1, 1, 0, 0)
    a("up_before_forget", OP_STATE)
    a("forget", OP_FORGET)
    a("up_after_forget", OP_STATE)

    # =================================================================
    #  A. ONE FRAME IN, THROUGH NetInput, AND THE REPLY OUT
    # =================================================================
    a("reset3", OP_RESET)
    a("cfg3", OP_NETCFG, OUR_IP, MASK, GW_IP, HW_LINK_WIRED, blob=OUR_MAC)
    a("sel3", OP_SELECT, 1, 1, 0, 0)
    a("base3", OP_COUNTS)
    a("txclear3", OP_TXCLEAR)
    a("feed_ping", OP_FEED,
      blob=echo_request(OUR_MAC, PEER_MAC, PEER_IP, OUR_IP))
    a("pump_ping", OP_PUMP, 10)
    a("staged_ping", OP_WIRE)
    a("rxseen_ping", OP_RXSEEN)
    a("note_ping", OP_NOTE)
    a("counts_ping", OP_COUNTS)
    a("ident_ping", OP_IDENT)

    # The same exchange over the OTHER kind, whose fixture driver keeps
    # its own receive buffer and copies nothing. A pump that read the
    # buffer it offered rather than the one HwLinkRxPtr names would pass
    # the case above and fail this one.
    a("reset3b", OP_RESET)
    a("cfg3b", OP_NETCFG, OUR_IP, MASK, GW_IP, HW_LINK_WIFI, blob=WIFI_MAC)
    a("sel3b", OP_SELECT, 0, 0, 1, 1)
    a("base3b", OP_COUNTS)
    a("txclear3b", OP_TXCLEAR)
    a("feed_ping_wifi", OP_FEED,
      blob=echo_request(WIFI_MAC, PEER_MAC, PEER_IP, OUR_IP))
    a("pump_ping_wifi", OP_PUMP, 10)
    a("staged_ping_wifi", OP_WIRE)
    a("rxseen_wifi", OP_RXSEEN)
    a("note_wifi", OP_NOTE)
    a("counts_ping_wifi", OP_COUNTS)
    a("ident_wifi", OP_IDENT)

    # =================================================================
    #  B. LinkTxStaged PUTS EXACTLY WHAT net.pi4 STAGED
    # =================================================================
    a("reset4", OP_RESET)
    a("cfg4", OP_NETCFG, OUR_IP, MASK, GW_IP, HW_LINK_WIRED, blob=OUR_MAC)
    a("sel4", OP_SELECT, 1, 1, 0, 0)
    # nothing staged yet: the wire must stay empty and no counter move
    a("base4", OP_TXC)
    a("txclear4a", OP_TXCLEAR)
    a("tx_nothing", OP_TXSTAGED)
    # an ARP request is a real thing net.pi4 stages
    a("stage_arp", OP_STAGEARP, GW_IP, HW_LINK_WIRED)
    a("staged_bytes", OP_STAGED)
    a("base4b", OP_TXC)
    a("txclear4b", OP_TXCLEAR)
    a("tx_arp", OP_TXSTAGED)

    # A FRAME LONGER THAN THE LINK WILL CARRY IS REFUSED, NOT TRUNCATED.
    # The ceiling is dropped under a staged frame and the same staged
    # bytes must now be refused, the wire must stay empty, and the
    # FAILURE counter must move rather than the success one.
    a("reset5", OP_RESET)
    a("cfg5", OP_NETCFG, OUR_IP, MASK, GW_IP, HW_LINK_WIRED, blob=OUR_MAC)
    a("sel5", OP_SELECT, 1, 1, 0, 0)
    a("stage_arp5", OP_STAGEARP, GW_IP, HW_LINK_WIRED)
    a("max_tiny", OP_TXMAX_SET, HW_LINK_WIRED, 20)
    # THE WIRE IS MADE PERMISSIVE FOR THIS CASE. The ceiling has to be
    # enforced by the POLICY layer and not only by whatever backend
    # happens to be underneath, and with the fixture also refusing, a
    # link.pi4 that dropped its own check would look identical.
    a("permissive_wire", OP_WIREMODE, 1, 0)
    a("base5", OP_TXC)
    a("txclear5", OP_TXCLEAR)
    a("tx_too_long", OP_TXSTAGED)

    # A STUCK TRANSMIT ENGINE: the frame is legal and the wire refuses it
    # anyway. The counters must record a FAILURE, and the success count
    # must not move - a send that did not happen and was counted as one
    # is a transfer that reports itself healthy while nothing leaves.
    a("reset5b", OP_RESET)
    a("cfg5b", OP_NETCFG, OUR_IP, MASK, GW_IP, HW_LINK_WIRED, blob=OUR_MAC)
    a("sel5b", OP_SELECT, 1, 1, 0, 0)
    a("stage_arp5b", OP_STAGEARP, GW_IP, HW_LINK_WIRED)
    a("stuck_wire", OP_WIREMODE, 0, 1)
    a("base5b", OP_TXC)
    a("txclear5b", OP_TXCLEAR)
    a("tx_stuck", OP_TXSTAGED)

    # =================================================================
    #  E. THE BOARD'S FIRST REFUSAL COMES BEFORE THE IP LAYER
    # =================================================================
    # The control: an ARP request from a stranger, NOT consumed. net.pi4
    # answers it and learns the sender, so the cache grows by one.
    a("reset6", OP_RESET)
    a("cfg6", OP_NETCFG, OUR_IP, MASK, GW_IP, HW_LINK_WIRED, blob=OUR_MAC)
    a("sel6", OP_SELECT, 1, 1, 0, 0)
    a("arp_before", OP_ARPCOUNT, HW_LINK_WIRED)
    a("txclear6", OP_TXCLEAR)
    a("feed_arp", OP_FEED,
      blob=eth(BCAST, OTHER_MAC, ET_ARP,
               arp(1, OTHER_MAC, OTHER_IP, b"\x00" * 6, OUR_IP)))
    a("pump_arp", OP_PUMP, 10)
    a("arp_after", OP_ARPCOUNT, HW_LINK_WIRED)
    a("note_arp", OP_NOTE)

    # The experiment: the identical frame, with the board's raw hook set
    # to consume ethertype $0806. The wire must be EMPTY, the pump must
    # answer #NET_IN_IGNORED, the EAPOL-shaped counter must move, and -
    # the airtight half - THE ARP CACHE MUST NOT HAVE GROWN, because
    # learning the sender is a side effect only NetInput has.
    a("reset7", OP_RESET)
    a("cfg7", OP_NETCFG, OUR_IP, MASK, GW_IP, HW_LINK_WIRED, blob=OUR_MAC)
    a("sel7", OP_SELECT, 1, 1, 0, 0)
    a("hooks7", OP_HOOKS, ET_ARP, 0)
    a("arp_before7", OP_ARPCOUNT, HW_LINK_WIRED)
    a("base7", OP_COUNTS)
    a("txclear7", OP_TXCLEAR)
    a("feed_arp7", OP_FEED,
      blob=eth(BCAST, OTHER_MAC, ET_ARP,
               arp(1, OTHER_MAC, OTHER_IP, b"\x00" * 6, OUR_IP)))
    a("pump_arp7", OP_PUMP, 10)
    a("arp_after7", OP_ARPCOUNT, HW_LINK_WIRED)
    a("counts7", OP_COUNTS)
    a("note7", OP_NOTE)

    # =================================================================
    #  F. HwLinkNoteRx IS TOLD THE IP LAYER'S VERDICT
    # =================================================================
    # A UDP datagram to a bound port, with the board's UDP hook TAKING
    # it. The pump answers #NET_IN_IGNORED to its caller and must still
    # have told the board #NET_IN_UDP.
    a("reset8", OP_RESET)
    a("cfg8", OP_NETCFG, OUR_IP, MASK, GW_IP, HW_LINK_WIRED, blob=OUR_MAC)
    a("bind8", OP_BIND, UDP_PORT, HW_LINK_WIRED)
    a("sel8", OP_SELECT, 1, 1, 0, 0)
    a("hooks8", OP_HOOKS, 0, 1)
    a("base8", OP_COUNTS)
    a("feed_udp8", OP_FEED, blob=udp_to_us(4000, UDP_PORT))
    a("pump_udp8", OP_PUMP, 10)
    a("note_udp8", OP_NOTE)
    a("counts_udp8", OP_COUNTS)

    # The same datagram with the hook OFF: the pump must answer
    # #NET_IN_UDP and the console counter must NOT move.
    a("reset9", OP_RESET)
    a("cfg9", OP_NETCFG, OUR_IP, MASK, GW_IP, HW_LINK_WIRED, blob=OUR_MAC)
    a("bind9", OP_BIND, UDP_PORT, HW_LINK_WIRED)
    a("sel9", OP_SELECT, 1, 1, 0, 0)
    a("base9", OP_COUNTS)
    a("feed_udp9", OP_FEED, blob=udp_to_us(4000, UDP_PORT))
    a("pump_udp9", OP_PUMP, 10)
    a("note_udp9", OP_NOTE)
    a("counts_udp9", OP_COUNTS)

    # A RUNT IS NOT A FRAME AND MUST NOT REACH NetInput. Shorter than an
    # Ethernet header, so nothing above can parse it.
    a("reset10", OP_RESET)
    a("cfg10", OP_NETCFG, OUR_IP, MASK, GW_IP, HW_LINK_WIRED, blob=OUR_MAC)
    a("sel10", OP_SELECT, 1, 1, 0, 0)
    a("base10", OP_COUNTS)
    a("feed_runt", OP_FEED, blob=b"\x01\x02\x03\x04\x05")
    a("pump_runt", OP_PUMP, 10)
    a("note_runt", OP_NOTE)
    a("counts_runt", OP_COUNTS)

    # AN EMPTY LINK ANSWERS #LINK_RX_NONE AND TELLS THE BOARD NOTHING.
    a("pump_empty", OP_PUMP, 10)
    a("note_empty", OP_NOTE)

    # =================================================================
    #  THE POLICY, AND THE CLOCK ON A CHANGE OF LINK
    # =================================================================
    a("reset11", OP_RESET)
    a("tick11", OP_TICK, 1000)
    a("pol_both", OP_SELECT, 1, 1, 1, 1)
    a("tick11b", OP_TICK, 500)
    a("pol_wired_only", OP_SELECT, 1, 1, 0, 0)
    a("pol_wifi_nocable", OP_SELECT, 0, 0, 1, 1)
    a("pol_wifi_noip", OP_SELECT, 1, 0, 1, 1)
    a("pol_wired_bare", OP_SELECT, 1, 0, 0, 0)
    a("pol_none", OP_SELECT, 0, 0, 0, 0)
    a("swaps", OP_TICK, 0)

    # LinkUseKind REFUSES A KIND THE BOARD HAS NOT GOT, rather than
    # accepting it and finding it empty at the first Send.
    a("reset12", OP_RESET)
    a("no_wifi", OP_HAS, HW_LINK_WIFI, 0)
    a("use_absent", OP_USEKIND, HW_LINK_WIFI)
    a("use_present", OP_USEKIND, HW_LINK_WIRED)
    a("state_after_use", OP_STATE)

    return s, at


def expect(cond, what, fails):
    if not cond:
        fails.append(what)


def hexdiff(got: bytes, want: bytes) -> str:
    lines = []
    for i in range(0, max(len(got), len(want)), 16):
        g = got[i:i + 16]
        w = want[i:i + 16]
        if g != w:
            lines.append("      @%-4d got  %s" % (i, g.hex(" ")))
            lines.append("            want %s" % w.hex(" "))
    if len(got) != len(want):
        lines.insert(0, "      length got %d, want %d" % (len(got), len(want)))
    return "\n".join(lines[:12])


def check(res: list[Result], at: dict, fails: list[str]) -> None:
    def R(name) -> Result:
        return res[at[name]]

    # ---- D. before a selection ---------------------------------------
    expect(R("up_at_reset").r == 0,
           "LinkUp() answered %d at reset, before anything had been "
           "selected. Nothing is carrying traffic then and a command that "
           "believed otherwise would send into a link that is not there"
           % R("up_at_reset").r, fails)
    expect(R("up_at_reset").e1 == HW_LINK_NONE,
           "LinkKind() at reset is %d, not #HW_LINK_NONE"
           % R("up_at_reset").e1, fails)
    expect(R("up_at_reset").e2 == 0,
           "LinkTxMax() with no link selected is %d; a link that is not "
           "there cannot promise to carry anything"
           % R("up_at_reset").e2, fails)
    expect(R("pump_before_select").r == LINK_RX_NONE,
           "the pump answered %d with no link selected, and #LINK_RX_NONE "
           "is %d. Zero is a LENGTH and a caller counting frames must be "
           "able to tell the two apart"
           % (R("pump_before_select").r, LINK_RX_NONE), fails)
    expect(R("pump_before_select").blob == b"",
           "the pump put %d bytes on the wire with no link selected"
           % len(R("pump_before_select").blob), fails)

    # ---- C. the ceiling follows the selection ------------------------
    expect(R("max_on_wired").e2 == 1400,
           "LinkTxMax() on the wired kind is %d and that kind's fixture "
           "ceiling is 1400" % R("max_on_wired").e2, fails)
    expect(R("max_on_wifi").e2 == 900,
           "LinkTxMax() did not follow the selection: it is %d after the "
           "choice moved to a kind whose ceiling is 900. A ceiling that is "
           "right for one link and stale for the other builds a segment "
           "too long for the wire it goes out of"
           % R("max_on_wifi").e2, fails)
    expect(R("max_clamped").e2 == LINK_ETH_MAX,
           "a backend answering 9000 was believed: LinkTxMax() is %d and "
           "the classic Ethernet maximum without the FCS is %d. The clamp "
           "belongs in the policy layer so no backend can raise it by "
           "accident" % (R("max_clamped").e2, LINK_ETH_MAX), fails)

    # ---- D. after LinkForget -----------------------------------------
    expect(R("up_before_forget").r == 1,
           "LinkUp() is %d after a successful LinkSelect"
           % R("up_before_forget").r, fails)
    expect(R("up_after_forget").r == 0,
           "LinkUp() is still %d after LinkForget(). `net link auto` "
           "releases the choice and the next command must make it again"
           % R("up_after_forget").r, fails)
    expect(R("up_after_forget").e1 == HW_LINK_NONE,
           "LinkKind() after LinkForget() is %d, not #HW_LINK_NONE"
           % R("up_after_forget").e1, fails)

    # ---- A. one frame in, the reply out ------------------------------
    #  THE REPLY IS GRADED TWICE, AGAINST TWO DIFFERENT THINGS.
    #
    #  Against net.pi4's STAGING BUFFER, byte for byte: that is the
    #  pump's own promise - whatever the IP layer staged goes out
    #  unchanged - and it is the half that is about link.pi4.
    #
    #  And against an echo reply's SHAPE, composed here: the addresses
    #  exchanged, ICMP type 0, and the identifier, sequence and payload
    #  carried back. That is the half that proves the frame went through
    #  a real IP layer rather than being echoed by a pump that
    #  short-circuited it. IT IS NOT GRADED BYTE FOR BYTE, deliberately:
    #  the IPv4 identification field and the Don't Fragment flag are
    #  net.pi4's to choose (RFC 791 leaves them to the sender), they are
    #  graded in a64_net_check.py where net.pi4 is the thing under test,
    #  and asserting them here would turn this gate red for a change in
    #  a file it is not testing.
    for tag, mac in (("ping", OUR_MAC), ("ping_wifi", WIFI_MAC)):
        pr = R("pump_" + tag)
        base = R("base3" if tag == "ping" else "base3b")
        which = ("the wired fixture kind, which fills the caller's buffer"
                 if tag == "ping"
                 else "the radio-shaped fixture kind, which keeps its own "
                      "receive buffer and hands a pointer back")
        expect(pr.r == NET_IN_IGNORED,
               "an ICMP echo request addressed to this board came in over "
               "%s and the pump answered its caller %d. The automatic "
               "dispatcher owns an echo reply and sends it itself, so the "
               "caller must be told #NET_IN_IGNORED (%d); a command waiting "
               "for its own reply would otherwise take this frame as one"
               % (which, pr.r, NET_IN_IGNORED), fails)
        req = echo_request(mac, PEER_MAC, PEER_IP, OUR_IP)
        expect(pr.e1 == len(req),
               "%s: the pump recorded a received length of %d and the frame "
               "fed in is %d bytes" % (tag, pr.e1, len(req)), fails)
        expect(pr.e2 - base.r == 1,
               "%s: the frame counter moved by %d for exactly one frame"
               % (tag, pr.e2 - base.r), fails)

        staged = R("staged_" + tag).blob
        if pr.blob != staged:
            fails.append(
                "%s: THE PUMP DID NOT PUT WHAT net.pi4 STAGED ON THE WIRE. "
                "The staged bytes and the captured wire are read out of the "
                "image in two separate script steps and compared here, so "
                "neither was shown to the other.\n%s"
                % (tag, hexdiff(pr.blob, staged)))
        _grade_echo_reply(tag, pr.blob, mac, fails)

        seen = R("rxseen_ping" if tag == "ping" else "rxseen_wifi")
        expect(seen.blob == req,
               "%s: LinkRxPtr()/LinkRxLen() do not describe the frame that "
               "arrived. A caller reading the frame through the seam's own "
               "pointer must see the bytes the driver received.\n%s"
               % (tag, hexdiff(seen.blob, req)), fails)
        note = R("note_" + ("ping" if tag == "ping" else "wifi"))
        expect(note.r == 1,
               "%s: HwLinkNoteRx was called %d times for one frame; the "
               "board is owed the IP layer's verdict on every one"
               % (tag, note.r), fails)
        expect(note.e1 == NET_IN_REPLY,
               "%s: HwLinkNoteRx was told %d and net.pi4 answered "
               "#NET_IN_REPLY (%d)" % (tag, note.e1, NET_IN_REPLY), fails)
        expect(note.e2 == (HW_LINK_WIRED if tag == "ping" else HW_LINK_WIFI),
               "%s: HwLinkNoteRx was told kind %d, and the kind carrying "
               "the frame was %d"
               % (tag, note.e2,
                  HW_LINK_WIRED if tag == "ping" else HW_LINK_WIFI), fails)

    expect(R("counts_ping").r - R("base3").r == 1,
           "LinkRxFrames() moved by %d for one frame"
           % (R("counts_ping").r - R("base3").r), fails)
    expect(R("counts_ping").e2 - R("base3").e2 == 1,
           "the dispatcher-owned counter (LinkConsoleCount) moved by %d for "
           "one echo request the dispatcher answered"
           % (R("counts_ping").e2 - R("base3").e2), fails)
    expect(R("counts_ping").e1 == R("base3").e1,
           "the board-consumed counter moved for a frame the board did not "
           "consume", fails)

    ident = R("ident_ping")
    expect(ident.r == 1000,
           "LinkSpeed() on the wired fixture kind is %d and its backend "
           "answers 1000 Mbit/s" % ident.r, fails)
    expect(ident.e1 == 1,
           "LinkDuplex() on the wired fixture kind is %d and its backend "
           "answers #HW_LINK_DUPLEX_FULL (1)" % ident.e1, fails)
    expect(ident.blob == OUR_MAC,
           "LinkMacPtr() names %s and the wired fixture kind's address is "
           "%s. DHCP puts this in the packet as the client hardware address "
           "and a reply addressed to the other kind's MAC is answered by "
           "nobody" % (ident.blob.hex(":"), OUR_MAC.hex(":")), fails)
    identw = R("ident_wifi")
    expect(identw.blob == WIFI_MAC,
           "LinkMacPtr() names %s while the radio-shaped kind carries the "
           "traffic; its address is %s"
           % (identw.blob.hex(":"), WIFI_MAC.hex(":")), fails)
    expect(identw.r == -1,
           "LinkSpeed() is %d on a kind whose backend has no measurable "
           "rate; #HW_LINK_SPEED_UNKNOWN is -1 and zero would be a "
           "measurement of a link running at no speed" % identw.r, fails)
    expect(identw.e1 == -1,
           "LinkDuplex() is %d on a kind with no duplex state to report; "
           "#HW_LINK_DUPLEX_UNKNOWN is -1 and 0 is HALF, which is a "
           "measurement" % identw.e1, fails)

    # ---- B. staged is what goes out ----------------------------------
    b4 = R("base4")
    expect(R("tx_nothing").r == 0,
           "LinkTxStaged() answered %d with nothing staged"
           % R("tx_nothing").r, fails)
    expect(R("tx_nothing").blob == b"",
           "LinkTxStaged() put %d bytes on the wire with nothing staged. "
           "An empty frame instead of silence is an unforced packet that "
           "fills a switch's counters and nothing else"
           % len(R("tx_nothing").blob), fails)
    expect(R("tx_nothing").e1 == b4.r and R("tx_nothing").e2 == b4.e1,
           "LinkTxStaged() with nothing staged moved a counter: ok %d->%d, "
           "fail %d->%d, and neither happened"
           % (b4.r, R("tx_nothing").e1, b4.e1, R("tx_nothing").e2), fails)

    staged = R("staged_bytes").blob
    expect(len(staged) > 0,
           "net.pi4 staged nothing for an ARP request, so the case that "
           "compares the wire against the staging buffer has nothing to "
           "compare", fails)
    wire = R("tx_arp").blob
    b4b = R("base4b")
    expect(R("tx_arp").r == 1,
           "LinkTxStaged() refused a staged ARP request that is inside the "
           "link's ceiling", fails)
    if wire != staged:
        fails.append(
            "LinkTxStaged() did not put the staged frame on the wire "
            "unchanged. The comparison is made in this file and neither "
            "buffer was shown to the other, so a library that truncated or "
            "padded cannot agree with itself into a pass.\n%s"
            % hexdiff(wire, staged))
    expect(R("tx_arp").e1 - b4b.r == 1 and R("tx_arp").e2 == b4b.e1,
           "after one successful send the counters moved ok +%d fail +%d"
           % (R("tx_arp").e1 - b4b.r, R("tx_arp").e2 - b4b.e1), fails)

    b5 = R("base5")
    expect(R("tx_too_long").r == 0,
           "LinkTxStaged() sent a frame longer than the link's ceiling. A "
           "truncated segment is not a shorter message, it is a corrupt one",
           fails)
    expect(R("tx_too_long").blob == b"",
           "a frame over the ceiling put %d bytes on the wire; the refusal "
           "must transmit nothing at all"
           % len(R("tx_too_long").blob), fails)
    expect(R("tx_too_long").e2 - b5.e1 == 1,
           "the refusal counter moved by %d after one refused frame; a send "
           "that did not happen and was not counted is a transfer that "
           "fails with no number anywhere to say why"
           % (R("tx_too_long").e2 - b5.e1), fails)
    expect(R("tx_too_long").e1 == b5.r,
           "the SUCCESS counter moved by %d for a frame that was refused"
           % (R("tx_too_long").e1 - b5.r), fails)

    b5b = R("base5b")
    expect(R("tx_stuck").r == 0,
           "LinkTxStaged() answered %d for a frame the backend refused. The "
           "seam says 1 sent, 0 not, and a caller told a frame went out "
           "when it did not will wait for a reply to a question nobody "
           "heard" % R("tx_stuck").r, fails)
    expect(R("tx_stuck").e2 - b5b.e1 == 1,
           "a send the backend refused moved the failure counter by %d"
           % (R("tx_stuck").e2 - b5b.e1), fails)
    expect(R("tx_stuck").e1 == b5b.r,
           "THE SUCCESS COUNTER MOVED BY %d FOR A SEND THAT DID NOT HAPPEN. "
           "`net` prints these two side by side and anyone reading "
           "\"out 40, refused 0\" on a board that has transmitted nothing "
           "has been told the network is working"
           % (R("tx_stuck").e1 - b5b.r), fails)

    # ---- E. first refusal, and a consumed frame never reaches the IP --
    expect(R("arp_after").r == R("arp_before").r + 1,
           "the control case: an ARP request from a stranger that the board "
           "did NOT consume left the neighbour count at %d, and it was %d "
           "before. If NetInput never learned the sender this case proves "
           "nothing about the one below it"
           % (R("arp_after").r, R("arp_before").r), fails)
    expect(len(R("pump_arp").blob) > 0,
           "the control case: net.pi4 answered a request for this board's "
           "own address with nothing on the wire", fails)

    expect(R("pump_arp7").r == NET_IN_IGNORED,
           "a frame the board consumed through HwLinkOfferRaw was reported "
           "as %d; #NET_IN_IGNORED is %d and the caller must not treat a "
           "consumed frame as one of its own"
           % (R("pump_arp7").r, NET_IN_IGNORED), fails)
    expect(R("pump_arp7").blob == b"",
           "a frame the board consumed still produced %d bytes on the wire, "
           "so the IP layer saw it after all"
           % len(R("pump_arp7").blob), fails)
    expect(R("arp_after7").r == R("arp_before7").r,
           "THE CONSUMED FRAME REACHED NetInput. The neighbour count went "
           "from %d to %d, and learning a sender is a side effect only "
           "NetInput has - so the board's first refusal was asked AFTER the "
           "IP layer, or not at all"
           % (R("arp_before7").r, R("arp_after7").r), fails)
    expect(R("counts7").e1 - R("base7").e1 == 1,
           "the board-consumed counter moved by %d after one consumed frame"
           % (R("counts7").e1 - R("base7").e1), fails)
    expect(R("counts7").r == R("base7").r,
           "LinkRxFrames() moved by %d for a frame the board consumed "
           "before the IP layer saw it; a frame the pump never delivered "
           "is not a frame it received"
           % (R("counts7").r - R("base7").r), fails)
    expect(R("note7").r == 0,
           "HwLinkNoteRx was called %d times for a frame that never reached "
           "the IP layer. There is no verdict to report on a frame nobody "
           "graded" % R("note7").r, fails)

    # ---- F. the verdict the board is owed ----------------------------
    expect(R("pump_udp8").r == NET_IN_IGNORED,
           "a UDP datagram the dispatcher took (the fixture HwLinkOfferUdp hook) was "
           "reported to the caller as %d; it must be #NET_IN_IGNORED (%d), "
           "because handing a console's keystrokes to a command looking for "
           "a reply drops them" % (R("pump_udp8").r, NET_IN_IGNORED), fails)
    expect(R("note_udp8").r == 1,
           "HwLinkNoteRx was called %d times for the taken datagram"
           % R("note_udp8").r, fails)
    expect(R("note_udp8").e1 == NET_IN_UDP,
           "HwLinkNoteRx was told %d for a datagram the IP layer classified "
           "as UDP (%d). THE VERDICT THE BOARD IS OWED IS THE IP LAYER'S "
           "AND NOT THE PUMP'S: a radio uses it to wind the clock that says "
           "the association is alive in both directions, and getting this "
           "wrong made a self-heal fire in the middle of a working transfer"
           % (R("note_udp8").e1, NET_IN_UDP), fails)
    expect(R("counts_udp8").e2 - R("base8").e2 == 1,
           "the taken-datagram counter moved by %d after one"
           % (R("counts_udp8").e2 - R("base8").e2), fails)

    expect(R("pump_udp9").r == NET_IN_UDP,
           "with the board's UDP hook off, a datagram to a bound port was "
           "reported as %d and not #NET_IN_UDP (%d)"
           % (R("pump_udp9").r, NET_IN_UDP), fails)
    expect(R("counts_udp9").e2 == R("base9").e2,
           "the taken-datagram counter moved by %d with the hook off"
           % (R("counts_udp9").e2 - R("base9").e2), fails)
    expect(R("note_udp9").e1 == NET_IN_UDP,
           "HwLinkNoteRx was told %d and not #NET_IN_UDP with the hook off"
           % R("note_udp9").e1, fails)

    # ---- the runt and the silent slice --------------------------------
    expect(R("pump_runt").r == LINK_RX_NONE,
           "a five-byte runt was reported as %d; shorter than an Ethernet "
           "header is not a frame and #LINK_RX_NONE is %d"
           % (R("pump_runt").r, LINK_RX_NONE), fails)
    expect(R("note_runt").r == 0,
           "HwLinkNoteRx was called %d times for a runt that never reached "
           "the IP layer" % R("note_runt").r, fails)
    expect(R("counts_runt").r == R("base10").r,
           "LinkRxFrames() counted a runt: it moved by %d"
           % (R("counts_runt").r - R("base10").r), fails)
    expect(R("pump_empty").r == LINK_RX_NONE,
           "a slice that expired in silence was reported as %d, not "
           "#LINK_RX_NONE (%d)" % (R("pump_empty").r, LINK_RX_NONE), fails)
    expect(R("note_empty").r == 0,
           "HwLinkNoteRx was called for a slice with no frame in it", fails)

    # ---- the policy ---------------------------------------------------
    # #LINK_WHY_* restated here, from link.pi4's own list.
    for name, want_kind, want_why, english in (
            ("pol_both", HW_LINK_WIRED, 1, "wired, and Wi-Fi was also usable"),
            ("pol_wired_only", HW_LINK_WIRED, 2, "wired, Wi-Fi had nothing"),
            ("pol_wifi_nocable", HW_LINK_WIFI, 4, "Wi-Fi, no cable"),
            ("pol_wifi_noip", HW_LINK_WIFI, 5,
             "Wi-Fi, the wired side has no address"),
            ("pol_wired_bare", HW_LINK_WIRED, 3,
             "wired with no address, nothing else at all"),
            ("pol_none", HW_LINK_NONE, 6, "neither")):
        rec = R(name)
        expect(rec.r == want_kind,
               "the preference order chose kind %d for the case '%s'; it "
               "must be %d. THE ORDER IS THE RULING'S: wired when it has a "
               "carrier AND an address, then Wi-Fi, then wired with no "
               "address, then nothing" % (rec.r, english, want_kind), fails)
        expect(rec.e1 == want_why,
               "the stored reason for '%s' is %d and it must be %d. The "
               "reason is stored at the moment the choice is made, so that "
               "`net` describes the decision that was actually taken"
               % (english, rec.e1, want_why), fails)

    expect(R("swaps").e1 >= 4,
           "the link changed kind at least four times across the policy "
           "cases and LinkSwaps() counted %d" % R("swaps").e1, fails)
    expect(R("swaps").e2 > 0,
           "LinkSince() is %d after a change of link; the timestamp is the "
           "only thing that says how long the current choice has stood"
           % R("swaps").e2, fails)

    # ---- LinkUseKind refuses what the board has not got ---------------
    expect(R("use_absent").r == HW_LINK_NONE,
           "LinkUseKind() accepted kind %d on a board whose HwLinkHas says "
           "it does not have one. Nothing can go right after that point and "
           "the failure presents as a network that silently drops "
           "everything" % R("use_absent").r, fails)
    expect(R("use_absent").e1 == 8,
           "the stored reason after refusing an absent kind is %d and "
           "#LINK_WHY_NOT_HERE is 8" % R("use_absent").e1, fails)
    expect(R("use_present").r == HW_LINK_WIRED,
           "LinkUseKind() refused a kind the board does have (answered %d)"
           % R("use_present").r, fails)
    expect(R("use_present").e1 == 7,
           "the stored reason for a one-link board is %d and "
           "#LINK_WHY_ONLY_ONE is 7" % R("use_present").e1, fails)
    expect(R("state_after_use").r == 1,
           "LinkUp() is %d after LinkUseKind() accepted a kind"
           % R("state_after_use").r, fails)


def _grade_echo_reply(tag, blob, our_mac, fails):
    """The reply's SHAPE, composed here from the RFC field layout.

    Not byte for byte: the IPv4 identification field and the Don't
    Fragment flag are the sender's to choose (RFC 791) and are graded in
    a64_net_check.py, where net.pi4 is the thing under test. What is
    checked here is everything that must be true for the frame to be an
    ANSWER TO THE REQUEST THAT CAME IN - which is what proves the pump
    put it through a real IP layer instead of echoing it back.
    """
    want_icmp = icmp_echo(0, PING_ID, PING_SEQ, PING_DATA)
    if len(blob) != 14 + 20 + len(want_icmp):
        fails.append("%s: the reply on the wire is %d bytes and an echo "
                     "reply to this request is %d"
                     % (tag, len(blob), 14 + 20 + len(want_icmp)))
        return
    checks = (
        ("the destination address", blob[0:6], PEER_MAC),
        ("the source address", blob[6:12], our_mac),
        ("the ethertype", blob[12:14], struct.pack(">H", ET_IPV4)),
        ("the source IPv4 address", blob[26:30], struct.pack(">I", OUR_IP)),
        ("the destination IPv4 address", blob[30:34],
         struct.pack(">I", PEER_IP)),
        ("the ICMP body", blob[34:], want_icmp),
    )
    for what, got, want in checks:
        if got != want:
            fails.append(
                "%s: %s of the reply is %s and an answer to this request "
                "carries %s. The addresses are exchanged, the type is 0, "
                "and the identifier, sequence and payload come back "
                "unchanged." % (tag, what, got.hex(" "), want.hex(" ")))
    if blob[23] != 1:
        fails.append("%s: the reply's IP protocol is %d and ICMP is 1"
                     % (tag, blob[23]))


# =====================================================================
#  THE NEGATIVE CONTROL - a gate nobody has seen go red is a gate nobody
#  should believe.  Every edit below is a plausible mistake in link.pi4,
#  and each one MUST turn this gate red.
# =====================================================================
MUTATIONS = [
    ("the dispatcher is never offered the frame, so no reply is sent",
     "  o = NetServiceInput(kind, p, r)", "  o = 0"),
    ("the board's first refusal is asked AFTER the IP layer",
     "  If HwLinkOfferRaw(kind, p, n) <> 0",
     "  If NetInput(kind, p, n) = -12345 Or HwLinkOfferRaw(kind, p, n) <> 0"),
    ("the board is never told the IP layer's verdict",
     "  HwLinkNoteRx(kind, r)\n", "\n"),
    ("the board is told the pump's answer instead of the IP layer's",
     "  r = NetInput(kind, p, n)", "  r = NetInput(kind, p, n)\n  If r = #NET_IN_UDP\n"
     "    If HwLinkOfferUdp(kind, p) <> 0\n      r = #NET_IN_IGNORED\n"
     "    EndIf\n  EndIf"),
    ("the transmit ceiling is not applied",
     "  If n > LinkTxMaxOn(kind)\n    gLinkTxFail = gLinkTxFail + 1\n"
     "    ProcedureReturn 0\n  EndIf", "  "),
    ("the 1514 clamp is dropped and a backend is believed",
     "  If m > #LINK_ETH_MAX\n    m = #LINK_ETH_MAX\n  EndIf", "  "),
    ("the ceiling is asked of the WIRED kind whatever is selected",
     "  m = HwLinkTxMax(kind)", "  m = HwLinkTxMax(#HW_LINK_WIRED)"),
    ("a zero-length staging buffer is sent anyway",
     "  n = NetOutLen()\n  If n <= 0\n    ProcedureReturn 0\n  EndIf",
     "  n = NetOutLen()\n  If n < 0\n    ProcedureReturn 0\n  EndIf"),
    ("LinkUp is true with no link selected",
     "Procedure.i LinkUp()\n  If gLinkKind = #HW_LINK_NONE\n"
     "    ProcedureReturn 0\n  EndIf\n  ProcedureReturn 1",
     "Procedure.i LinkUp()\n  ProcedureReturn 1"),
    ("LinkForget leaves the kind in place",
     "Procedure LinkForget()\n  gLinkKind = #HW_LINK_NONE",
     "Procedure LinkForget()\n  gLinkWhy = #LINK_WHY_UNSET"),
    ("the backend's receive pointer is ignored",
     "  p = HwLinkRxPtr(kind)\n  If p = 0\n    p = @gLinkRx[0]\n  EndIf",
     "  p = @gLinkRx[0]"),
    ("a runt is handed to the IP layer",
     "  If n < 14", "  If n < 0"),
    ("Wi-Fi is preferred over a usable wired link",
     "  If wiredLink <> 0 And wiredIp <> 0\n    k = #HW_LINK_WIRED",
     "  If wifiUp <> 0 And wifiIp <> 0\n    k = #HW_LINK_WIFI"),
    ("a kind the board has not got is accepted",
     "    If HwLinkHas(kind) <> 0\n      k = kind\n    EndIf",
     "    k = kind"),
    ("the frame counter is not wound",
     "  gLinkRxFrames = gLinkRxFrames + 1\n  gLinkRxLen = n",
     "  gLinkRxLen = n"),
    ("a refused send is counted as a success",
     "  If HwLinkSend(kind, NetOutBuf(), n, 100) <> 1\n"
     "    gLinkTxFail = gLinkTxFail + 1\n    ProcedureReturn 0\n  EndIf",
     "  HwLinkSend(kind, NetOutBuf(), n, 100)"),
]


def mutate_one(job) -> tuple[str, bool, str]:
    """One mutation, in its own directory.  Returns (name, went_red, note)."""
    idx, name, old, new, target, pmfc = job
    # A worker process starts from this module's defaults, so the compiler
    # resolved in main() has to travel with the job.
    globals()["PMFC"] = pmfc
    apply_target(globals(), target)
    d = WORK / "mut" / target / str(idx)
    d.mkdir(parents=True, exist_ok=True)
    src = LIB.read_text(encoding="utf-8", errors="replace")
    if src.count(old) != 1:
        return (name, False,
                "the anchor text appears %d times in link.pi4, not once - "
                "the mutation could not be applied and proves nothing"
                % src.count(old))
    mut = d / "link_mut.pi4"
    mut.write_text(src.replace(old, new), encoding="utf-8")
    rel = mut.relative_to(ROOT).as_posix()
    harness = d / "netpumpharness.pi4"
    img = d / "netpumpcheck.img"
    try:
        write_harness(rel, harness)
        build(harness, img)
        s, at = build_script()
        cpu, _con, _steps = run(img, s.finish())
        res = read_results(cpu.memory, s.labels)
    except SystemExit as e:
        return (name, True, "the toolchain refused it: %s"
                % str(e).splitlines()[0][:90])
    except OSError as e:
        # The compiler never started. That is not the gate noticing the
        # defect, so it must not be counted as red.
        return (name, False, "the compiler could not be started (%s); this "
                "mutation proves nothing - check --compiler" % str(e)[:60])
    except Exception as e:                                # noqa: BLE001
        return (name, True, "the run did not complete: %s" % str(e)[:90])
    fails: list[str] = []
    try:
        check(res, at, fails)
    except Exception as e:                                # noqa: BLE001
        return (name, True, "the grading could not finish: %s" % str(e)[:90])
    return (name, bool(fails), fails[0].splitlines()[0][:90] if fails else "")


def run_mutations(target: str) -> int:
    from concurrent.futures import ProcessPoolExecutor
    jobs = [(i, n, o, w, target, str(PMFC))
            for i, (n, o, w) in enumerate(MUTATIONS)]
    # Capped: other gates share this machine. PMF_MUTATE_JOBS overrides.
    workers = max(1, min(len(jobs), int(os.environ.get("PMF_MUTATE_JOBS", "6"))))
    print("negative control: %d mutations across %d workers"
          % (len(jobs), workers))
    bad = 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for name, red, note in pool.map(mutate_one, jobs):
            if red:
                print("  RED   %s" % name)
                if note:
                    print("        %s" % note)
            else:
                bad += 1
                print("  GREEN %s  <-- THE GATE DID NOT NOTICE" % name)
                if note:
                    print("        %s" % note)
    if bad:
        print("\na64_netpump_check --mutate: FAIL - %d mutation(s) passed a "
              "gate that should have refused them" % bad)
        return 1
    print("\na64_netpump_check --mutate: PASS - every mutation went red")
    return 0


def fail_out(fails: list[str]) -> int:
    print("\na64_netpump_check: FAIL - %d" % len(fails))
    for f in fails:
        print("  * %s" % f)
    return 1


def resolve_compiler(requested):
    """Resolve the PureMetal compiler the way tools/build.py does."""
    sys.path.insert(0, str(ROOT / "tools"))
    import build as anvil_build  # noqa: E402
    return anvil_build.find_compiler(requested)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"),
                    help="path of PureMetalForge.exe (or set PMF_COMPILER); "
                         "it is run with --compile")
    # Pi 4 only: this tree has no HwLink* backend for another board.
    ap.add_argument("--target", choices=["pi4"], default="pi4")
    ap.add_argument("--mutate", action="store_true",
                    help="run the negative control (all cores)")
    args = ap.parse_args()
    globals()["PMFC"] = resolve_compiler(args.compiler)
    row = apply_target(globals(), args.target)

    print("[gate] tree under test: %s" % ROOT, file=sys.stderr)
    print("a64_netpump_check: grading %s" % row["what"])
    print("                   RaspberryPi4/Lib/link.pi4 over a FIXTURE link,")
    print("                   with no MAC, no PHY and no radio in the image")

    work = WORK / args.target
    work.mkdir(parents=True, exist_ok=True)
    harness = work / "netpumpharness.pi4"
    img = work / "netpumpcheck.img"
    write_harness("RaspberryPi4/Lib/link.pi4", harness)
    build(harness, img)

    s, at = build_script()
    cpu, console, steps = run(img, s.finish())
    res = read_results(cpu.memory, s.labels)
    if b"netpumpharness done" not in bytes(console) and args.target == "pi4":
        return fail_out(["the harness did not reach its last line, so the "
                         "results below are from an incomplete run"])
    if len(res) != len(s.labels):
        return fail_out(["the harness wrote %d result records for %d script "
                         "steps, so the run stopped part way through"
                         % (len(res), len(s.labels))])

    fails: list[str] = []
    check(res, at, fails)
    cases = len(at)

    if fails:
        return fail_out(fails)

    print("\na64_netpump_check: PASS - %d cases on %s, %s model instructions"
          % (cases, args.target, "{:,}".format(steps)))
    print("""
  WHAT IS NOT COVERED, and it is the half that needs a board:
   * ANY REAL DRIVER. GENET, CYW43, SLIP and the file channel are all
     absent from this image. This proves the pump's ORDER, not that any
     board can move a byte. Those are gated separately and pass:
     a64_genet_check.py, a64_qslip_check.py, a64_qnetproof_check.py.
   * THE POLICY'S FACTS. LinkSelect is driven with the four numbers as
     arguments; whether a board reports its own carrier and address
     honestly is HwLinkOpen's, in the board file.
   * TIMING. The fixture answers at once, so a driver that ignored its
     receive deadline would not be caught here.
""")
    if args.mutate:
        return run_mutations(args.target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

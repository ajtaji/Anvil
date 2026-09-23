#!/usr/bin/env python3
r"""Executable gate for THE NETWORK CONSOLE'S ARMING - the one question
"should this board be listening on UDP 5555 right now, and on WHICH
interface" - asked of Anvil/Core/netconsole.pbi over a SCRIPTED LINK SEAM
with two links in it.

      python tools/a64/a64_wificon_check.py
      python tools/a64/a64_wificon_check.py --mutate

THE FILE KEEPS ITS NAME AND THE NAME IS NOW HISTORY.  It was written on
2026-09-06 against the WIRELESS console, which is what the thing was
called while it could only ride a radio.  It rides the Ethernet cable too
from 2026-09-07, and the name stays so that every script that already
says `a64_wificon_check` still finds it.

WHY THIS FILE EXISTS
--------------------
Measured on the bench 2026-09-06: the monitor auto-joined from its
settings at boot, took a DHCP lease, ANSWERED PING on it - and the UDP
console stayed deaf until a human typed `wifi join` a second time on the
serial line.  The serial cable was dead that day, so the board was
unreachable while sitting on the network it had joined.

Measured on the bench 2026-09-07, with that fixed: the PC moved to
another subnet, the serial adapter failed enumeration, and an Ethernet
cable ran straight from the PC to the board with an address at both ends.
The board had NO CONSOLE AT ALL, because the console was a property of
the radio.

Both are the same defect wearing different hats, and it is a SHAPE.
Arming was decided by something that could only ever be half right: first
by whichever path completed DHCP ("I got the address, so I will arm"),
then, after that was cured, by which INTERFACE the code happened to live
next to.  The cure is that arming is RE-DERIVED from the board's actual
state on every spin of the prompt - is there an address, and whose is it -
and that the answer names an interface rather than assuming one.

WHAT IS PROVEN, AND WHY EACH IS DIFFERENT EVIDENCE
--------------------------------------------------
  A. AN ADDRESS ON A LINK THAT CANNOT CARRY A FRAME DOES NOT ARM.  A
     console announced on an interface that is not up says it is
     listening and answers nobody, which is the failure this whole line
     of work exists to end.

  B. AN ADDRESS BOUND BY A PATH THE CONSOLE KNOWS NOTHING ABOUT ARMS IT
     ANYWAY, within one spin, with nobody typing.  This is the portable
     `dhcp` command, `net ip`, the settings-driven configuration and
     anything added later - from inside the console they all look
     identical: the IP layer is configured and no flag was set.

  C. THE CONSOLE ANSWERS A DATAGRAM OVER THE WIRED LINK, and the answer
     LEAVES THROUGH THE WIRED LINK.  Built here from the RFC 791/768
     field layouts and never copied out of the library, graded field by
     field, and the fixture records which of its two links the frame was
     handed to.  This is the case that did not exist before 2026-09-07
     and could not have passed.

  D. AND OVER THE RADIO, identically.  One console, two links, one
     implementation - so a fix to one is a fix to both by construction
     rather than by somebody remembering.

  E. WIRED IS PREFERRED WHEN BOTH LINKS ARE UP, and when the stack moves
     to the other interface THE CONSOLE MOVES WITH IT and forgets its
     peer.  The peer's hardware address belongs to the segment it was
     learned on; replying to it out of the other link would send frames
     to a machine that is not there.

  F. IDEMPOTENT, AND THE LISTENING LINE IS PRINTED EXACTLY ONCE PER
     ARMING.  Ten spins of the prompt, one line.  A console that
     re-announced itself every 5 ms would be unusable.

  G. THE BOUND PORT IS PUT BACK.  ping, dns and dhcp each bind a port of
     their own and none of them restores it; after one of those the
     console must still be delivered its next datagram.

  H. THE CONSOLE READS ONLY THE LINK IT ARMED ON.  A frame waiting on the
     other interface is not the console's and must not be consumed by it -
     the other link's pump owns that frame, and a console that ate it
     would be dropping somebody else's traffic silently.

  I. THE BOARD IS TOLD WHICH LINK THE CONSOLE ARMED ON.  On the Pi 4 the
     radio's own receive pump stands down only when the console is on the
     RADIO; if the console said nothing, or said "armed" without saying
     where, that pump would either eat the console's keystrokes or stop
     servicing rekeys.

  L0. ONE TURN OF THE PUMP EMPTIES THE RING, NOT ONE FRAME.  Three
     console datagrams are queued on the radio with no pump between them,
     then the pump runs ONCE: the fixture must hold 3 before and 0 after,
     all three payloads must be in the keystroke ring in arrival order,
     and the console's own drain counters must agree.  A pump that took
     one frame per call capped the board's receive rate at one frame per
     turn of the prompt, and on a segment with any traffic on it the
     datagram that mattered queued behind the chatter and was lost.  The
     fixture used to hold ONE pending frame, which cannot tell a one-frame
     pump from a draining one; it holds a queue now for that reason.

  T. THE CONSOLE'S PUMP HANDS A TCP SEGMENT TO TCP.  Both links hold an
     address, outbound traffic is pinned to the cable, and a
     checksum-valid segment arrives on the radio - the link the link's
     own pump is not reading, so the console's pump is the only reader.
     NetServiceInput must enter TcpInput exactly once with NetRxKind()
     naming the radio, put nothing in the keystroke ring, and still
     deliver the next console datagram on the same link.

  L7. AND THE CHECKSUM UNDER EVERY VERDICT, which became a 256-entry
     table the same day: all 256 entries, six lengths and a split feed,
     against Python's zlib.crc32.

  L. A BULK READBACK GOES TO THE CONSOLE THAT ASKED FOR IT, AND ONLY
     THERE.  Measured 2026-09-16: `memory` read memory back over this
     console at 1,730 bytes a second on a gigabit cable, because every
     byte the monitor prints goes through the PL011 at 115200 baud before
     the console's tap sees it.  Anvil/Core/readback.pbi is driven here
     through the REAL console output path with a peer that typed the
     command, and graded on the wire: the header, then EXACTLY
     ceil(n / 720) payload datagrams of 15 base64 lines each, then the
     verdict line with the byte count and the crc32 - both computed here
     with Python's base64 and zlib, not read out of the library.  And on
     the SERIAL capture: the header and the verdict are there and not one
     base64 line is, which is the measured defect stated as an assertion.
     Typed on the local console instead, the same stream goes out the
     serial port and nothing goes on the wire.  A stopped stream says
     `stopped`, with the count and checksum of what really went.

THE NEGATIVE CONTROLS (--mutate).  The first reverts NetConsoleRearm to the
pre-fix body - re-bind the port, arm nothing - in a COPY of the library,
builds a second image from it and runs the same script.  B, C, D and E must
all go red there.  The second puts the readback's payload back through
UartWrite, the way every console byte went before 2026-09-16, in a copy of
Anvil/Core/readback.pbi; L must go red on the datagram count AND on the
serial capture.  The third puts a `Break` back at the bottom of
netcon_PumpOne's drain loop in a copy of the library - one frame per call -
and L0 must go red there with 2 of 3 frames still queued and only the first
payload in the ring, while the console still arms.  The fourth removes the
`If rc = #NET_IN_TCP` arm from NetServiceInput in a copy of the library;
T must go red there - the segment is taken off the wire and TCP is never
entered - while the drain and the console datagram still work.  A gate
that cannot fail on demand is a gate that has not been read.

NO RADIO, NO MAC, NO SDIO, NO CREDENTIALS IN THIS IMAGE.  The HwLink*
seam is answered by a FIXTURE below: two links, each with a hardware
address and a readiness flag the script sets, one receive queue, one
capture of the wire, and a clock the script advances.  That is the entire
device model, and it is enough, because what is under test is not a wire -
it is the decision about which wire the console belongs on, and the
datagram that comes out of it.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import pathlib
import re
import struct
import subprocess
import sys
import zlib

HERE = pathlib.Path(__file__).resolve().parent
# THE TREE UNDER TEST IS THE ONE THIS SCRIPT LIVES IN.
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))

from a64_interp import A64, attach_symbols                       # noqa: E402
from a64_target import TARGETS, apply_target, patch_harness      # noqa: E402

PMFC = os.environ.get("PMF_COMPILER") or "PureMetalForge.exe"  # rebound from --compiler
# Every compile resolves includes from THIS tree only.
BUILD_ENV = dict(os.environ, PMF_ROOT=str(ROOT))
LIB = ROOT / "Anvil" / "Core" / "netconsole.pbi"
WORK = ROOT / "_work" / "wificon"

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
CNTFRQ = 54_000_000
STEPS_PER_TICK = 8
STEP_LIMIT = 200_000_000

# ---- the vocabulary of the files under test, restated INDEPENDENTLY.
# ---- If the two ever disagree this gate goes red and one is wrong.
NET_IN_UDP = 2
NETCON_PORT = 5555
ET_IPV4 = 0x0800
IPPROTO_UDP = 17
LINK_WIRED = 1
LINK_WIFI = 2

# The constants the console takes from the HAL.  They are NOT restated -
# borrow_constants() lifts each definition out of the real file at
# harness-generation time and fails loudly if one has gone, so there is
# no second copy of a value to rot.  #NETCON_PORT is deliberately in BOTH
# places: borrowed here so the image compiles, and written out above as
# an independent number so a port that silently moved turns this red.
BORROWED = {
    "Anvil/Hal/hal.pbi": [
        "#HW_LINK_NONE", "#HW_LINK_WIRED", "#HW_LINK_WIFI",
        "#HW_LINK_SERIAL", "#HW_LINK_FIRMWARE", "#HW_LINK_FILE",
        "#NETCON_PORT",
        # how many frames one drain of an interface ring may take
        "#LINK_RX_BUDGET",
    ],
    # The two console styles the network console switches between;
    # the screen console that consumes them is not in this image.
    "Anvil/Core/console_style.pbi": [
        "#UART_SCREEN_STYLE_NORMAL", "#UART_SCREEN_STYLE_PROMPT",
    ],
    # The readback's length ceiling and the one CRC polynomial, both of
    # which live with the monitor's shared state rather than with the
    # file that uses them.
    "Anvil/Core/state.pbi": [
        "#LEN_MAX", "#CRC_POLY",
    ],
}


def borrow_constants() -> str:
    """Lift the named constant DEFINITIONS out of the real HAL."""
    out = ["; ---- constants lifted verbatim from the real HAL by",
           "; ---- tools/a64/a64_wificon_check.py. Values are never typed",
           "; ---- here; a missing one fails the gate."]
    for rel, names in BORROWED.items():
        text = (ROOT / rel).read_text(encoding="utf-8", errors="ignore")
        for name in names:
            m = re.search(r"(?m)^\s*(%s\s*=[^\r\n]*)$" % re.escape(name),
                          text)
            if not m:
                raise SystemExit(
                    "a64_wificon_check: %s is no longer defined in %s, so "
                    "the harness cannot be generated. Either the constant "
                    "was renamed - in which case fix this gate - or it was "
                    "deleted, in which case the console no longer compiles."
                    % (name, rel))
            out.append(m.group(1).strip())
    return "\n".join(out)


# =====================================================================
#  THE FRAMES, WRITTEN FROM THE RFCs AND NOT FROM THE LIBRARY
# =====================================================================
def ip4(a: int, b: int, c: int, d: int) -> int:
    return (a << 24) | (b << 16) | (c << 8) | d


def ones_complement(data: bytes, seed: int = 0) -> int:
    total = seed
    if len(data) % 2:
        data += b"\0"
    for i in range(0, len(data), 2):
        total += (data[i] << 8) | data[i + 1]
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def ipv4(src: int, dst: int, proto: int, payload: bytes,
         ident: int) -> bytes:
    hdr = bytearray(20)
    hdr[0] = 0x45
    hdr[2:4] = struct.pack(">H", 20 + len(payload))
    hdr[4:6] = struct.pack(">H", ident)
    hdr[8] = 64
    hdr[9] = proto
    hdr[12:16] = struct.pack(">I", src)
    hdr[16:20] = struct.pack(">I", dst)
    hdr[10:12] = struct.pack(">H", ones_complement(bytes(hdr)))
    return bytes(hdr) + payload


def udp(src: int, dst: int, sport: int, dport: int,
        payload: bytes) -> bytes:
    u = struct.pack(">HHHH", sport, dport, 8 + len(payload), 0) + payload
    return ipv4(src, dst, IPPROTO_UDP, u, 0x1234)


def eth(dst: bytes, src: bytes, ethertype: int, payload: bytes) -> bytes:
    return dst + src + struct.pack(">H", ethertype) + payload


# =====================================================================
#  THE HARNESS
# =====================================================================
HARNESS = r'''
; ======================================================================
;  netconharness.pi4 - GENERATED BY tools/a64/a64_wificon_check.py.
;                      DO NOT EDIT.
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
;  THE FIXTURE LINK SEAM IS THE FIRST BLOCK BELOW: TWO links, each with a
;  hardware address and a readiness flag the script sets, one receive
;  queue with the kind each frame arrived on, one capture of the wire with the
;  kind it left through, and a clock the script advances. That is the
;  entire device model, and it is enough, because what is under test is
;  not a wire - it is which wire the console belongs on.
;
;  THERE IS NO RADIO AND NO MAC IN THIS IMAGE. Anvil/Core/netconsole.pbi
;  names no chip; every wire access in it is HwLink*(kind, ...), which is
;  exactly the property that lets this harness answer for it in sixty
;  lines instead of a device model.
; ======================================================================
XIncludeFile "RaspberryPi4/Lib/uart.pi4"

; THE CONSTANTS COME FIRST. A procedure may be called before it is seen,
; but a constant may not be USED before it is declared - and the fixture
; seam below is written in #HW_LINK_* from its first line.
__BORROWED__

#H_SCRIPT = $06000000
#H_RESULT = $06800000

#FX_FRAME_MAX = 2048
#FX_TX_MAX    = 16384

; ----------------------------------------------------------------------
;  A RECEIVE QUEUE, NOT A SINGLE SLOT - AND THE QUEUE IS THE POINT.
;
;  This fixture used to hold exactly ONE pending frame, which is a model
;  of a wire that never has two frames on it at once. No such wire
;  exists: a board joined to a live network is handed that network's
;  broadcast and multicast traffic, so the datagram that matters arrives
;  with others in front of it.
;
;  A ONE-SLOT FIXTURE CANNOT SEE A PUMP THAT STOPS AFTER ONE FRAME. It
;  hands back one frame, the console consumes it, and a pump that takes
;  one frame per call and a pump that drains to empty look identical.
;  Section L0 stages several frames and pumps once, which needs this.
;
;  Each slot keeps its own bytes, length and arriving link, and
;  HwLinkRxPtr answers the slot just popped - the way a driver with
;  several buffers of its own does, with nothing copied.
; ----------------------------------------------------------------------
#FX_RXQ = 8
Global Dim fxRx.a[#FX_RXQ * #FX_FRAME_MAX]
Global Dim fxRxSlotLen.i[#FX_RXQ]
Global Dim fxRxSlotKind.i[#FX_RXQ]
Global fxRxHead.i                  ; next slot to hand out
Global fxRxCount.i                 ; how many are waiting
Global fxRxLast.i                  ; base of the slot just popped
; The one-slot names the existing cases read, kept meaning what they
; meant: the frame at the head of the queue (fxRxPending is the count).
Global fxRxLen.i
Global fxRxPending.i
Global fxRxKind.i

Procedure fxRxSync()
  ; The head of the queue, restated in the three globals the cases read.
  ; One place does it, so a case cannot see a length from one frame and
  ; a link from another.
  If fxRxCount <= 0
    fxRxLen = 0
    fxRxPending = 0
    fxRxKind = 0
    ProcedureReturn
  EndIf
  fxRxLen = fxRxSlotLen[fxRxHead]
  fxRxPending = fxRxCount
  fxRxKind = fxRxSlotKind[fxRxHead]
EndProcedure

; The wire, and which link carried it.
Global Dim fxTx.a[#FX_TX_MAX]
Global fxTxLen.i
Global fxTxCalls.i
Global fxTxKind.i

; AND EVERY FRAME, NOT ONLY THE LAST. fxTx above keeps the most recent
; frame and every case written before 2026-09-16 grades that one. A bulk
; stream is several frames whose ORDER and COUNT are the claim, so each
; accepted frame is also appended here behind ONE BYTE naming the link it left
; through and a big-endian 16-bit length.
; fxLogFrames counts every accepted frame even if the log is full, so a
; log that ran out of room reads as a count that disagrees with its
; contents rather than as a short stream.
#FX_LOG_MAX = 24576
Global Dim fxLog.a[#FX_LOG_MAX]
Global fxLogLen.i
Global fxLogFrames.i

; The two links.
Global Dim fxWiredMac.a[6]
Global Dim fxWifiMac.a[6]
Global fxWiredReady.i
Global fxWifiReady.i

; What the console last told the board through HwLinkConsoleArmed.
Global fxArmedKind.i
Global fxArmedOn.i
Global fxArmedCalls.i

; What HwLinkNoteRx was told, and how often.
Global fxNoteRx.i
Global fxNoteCalls.i

; The fixture clock. Advanced by the script, never by itself.
Global fxMs.i

Procedure.i millis()
  ProcedureReturn fxMs
EndProcedure

Procedure delay(ms.i)
  fxMs = fxMs + ms
EndProcedure

Procedure delayMicroseconds(us.i)
EndProcedure

; ---- the interface pin -----------------------------------------------
; Anvil/Core/netif.pbi READS the pin rather than owning it, because `net
; link wired` is one decision and must not have two homes. On the board
; it lives in RaspberryPi4/Lib/link.pi4, which would drag the whole
; policy layer and both drivers into this image; here it is two lines,
; and the script can set it.
Global fxPin.i

Procedure.i LinkPin()
  ProcedureReturn fxPin
EndProcedure

; ---- the fixture link seam ------------------------------------------
Procedure.i HwLinkHas(kind.i)
  If kind = #HW_LINK_WIRED
    ProcedureReturn 1
  EndIf
  If kind = #HW_LINK_WIFI
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i HwLinkReady(kind.i)
  If kind = #HW_LINK_WIRED
    ProcedureReturn fxWiredReady
  EndIf
  If kind = #HW_LINK_WIFI
    ProcedureReturn fxWifiReady
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i HwLinkMacPtr(kind.i)
  If kind = #HW_LINK_WIRED
    ProcedureReturn @fxWiredMac[0]
  EndIf
  If kind = #HW_LINK_WIFI
    ProcedureReturn @fxWifiMac[0]
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i HwLinkTxMax(kind.i)
  If kind = #HW_LINK_WIRED
    ProcedureReturn 1514
  EndIf
  If kind = #HW_LINK_WIFI
    ProcedureReturn 1460
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i HwLinkName(kind.i)
  If kind = #HW_LINK_WIRED
    ProcedureReturn "the wired Ethernet"
  EndIf
  If kind = #HW_LINK_WIFI
    ProcedureReturn "the Wi-Fi radio"
  EndIf
  ProcedureReturn "an interface this board does not have"
EndProcedure

Procedure.i HwLinkSend(kind.i, buf.i, n.i, ms.i)
  Define i.i
  fxTxCalls = fxTxCalls + 1
  fxTxKind = kind
  If n <= 0 Or n > #FX_TX_MAX
    ProcedureReturn 0
  EndIf
  If n > HwLinkTxMax(kind)
    ProcedureReturn 0
  EndIf
  i = 0
  While i < n
    fxTx[i] = PeekA(buf + i)
    i = i + 1
  Wend
  fxTxLen = n
  fxLogFrames = fxLogFrames + 1
  If fxLogLen + 3 + n <= #FX_LOG_MAX
    fxLog[fxLogLen] = kind & $FF
    fxLog[fxLogLen + 1] = (n >> 8) & $FF
    fxLog[fxLogLen + 2] = n & $FF
    i = 0
    While i < n
      fxLog[fxLogLen + 3 + i] = PeekA(buf + i)
      i = i + 1
    Wend
    fxLogLen = fxLogLen + 3 + n
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i HwLinkRecv(kind.i, buf.i, max.i, ms.i)
  Define n.i
  If fxRxCount <= 0
    ProcedureReturn 0
  EndIf
  If kind <> fxRxSlotKind[fxRxHead]
    ; The frame at the head is waiting on the OTHER interface. A driver
    ; asked for a frame on a link that has none answers nothing, and the
    ; frame stays queued for whoever owns it. IT IS NOT SKIPPED OVER: a
    ; fixture that quietly reordered would model a wire nobody has.
    ProcedureReturn 0
  EndIf
  n = fxRxSlotLen[fxRxHead]
  fxRxLast = @fxRx[fxRxHead * #FX_FRAME_MAX]
  fxRxHead = fxRxHead + 1
  If fxRxHead >= #FX_RXQ
    fxRxHead = 0
  EndIf
  fxRxCount = fxRxCount - 1
  fxRxSync()
  ProcedureReturn n
EndProcedure

Procedure.i HwLinkRxPtr(kind.i)
  ; The slot the last HwLinkRecv handed out, not slot zero. With a queue
  ; those stop being the same address, and returning the wrong one would
  ; make every frame after the first parse as a copy of the first.
  If fxRxLast = 0
    ProcedureReturn @fxRx[0]
  EndIf
  ProcedureReturn fxRxLast
EndProcedure

Procedure.i HwLinkOfferRaw(kind.i, p.i, n.i)
  ; No EAPOL and no supplicant in this image, so the board consumes
  ; nothing and every frame reaches the IP layer.
  ProcedureReturn 0
EndProcedure

Procedure HwLinkNoteRx(kind.i, r.i)
  fxNoteRx = r
  fxNoteCalls = fxNoteCalls + 1
EndProcedure

Procedure HwLinkConsoleArmed(kind.i, on.i)
  fxArmedKind = kind
  fxArmedOn = on
  fxArmedCalls = fxArmedCalls + 1
EndProcedure

; netfmt.pi4's diagnostics name the wired driver and the TFTP client,
; neither of which is in this image.
Procedure.i GenetErrorText() : ProcedureReturn "no wired driver in this image" : EndProcedure
Procedure.i TftpErrorText() : ProcedureReturn "no tftp client in this image" : EndProcedure

XIncludeFile "Anvil/Network/net.pbi"
XIncludeFile "Anvil/Core/netfmt.pbi"
; PutHex8, for the lease worker's report line.
XIncludeFile "Anvil/Core/format.pbi"
; ONE ADDRESS RECORD PER INTERFACE. The console asks it which interfaces
; hold an address, and asks it to point the one IP layer at the one a
; frame arrived on - so it is under test here as much as the console is,
; and the two are meaningless apart.
XIncludeFile "Anvil/Core/netif.pbi"
; AND THE DHCP SERVER, because the console's pump is what feeds it: a
; DISCOVER arrives at a prompt with nothing typed on it, so the pump is
; the only thing running when it does.
; THE DHCP MESSAGE LAYOUT AND THE PER-INTERFACE CLIENT. The server takes
; its field offsets and the client's state names from this file, and the
; console's automatic dispatcher hands port-68 datagrams to the client, so
; the real file is in the image rather than a copy of its constants. It
; needs nothing but net.pbi.
XIncludeFile "Anvil/Network/dhcp.pbi"
XIncludeFile "Anvil/Core/dhcpd.pbi"

; FOUR NAMES THE CONSOLE REACHES THAT ARE NOT IN THIS IMAGE. The lease
; worker binds and drops an address through Anvil/Core/netcfg.pbi, and
; the dispatcher offers a datagram to Anvil/Core/ntp_service.pbi and a
; segment to RaspberryPi4/Lib/tcp.pi4 before the console sees it. Each
; of those files brings the settings store or a transport with it. No
; DHCP client is started here and no datagram is SNTP, so the first three
; are empty. TCP IS NOT: section T hands the pump a verified segment.
Procedure NetAddressBound(kind.i, ip.i, mask.i, gw.i, src.i) : EndProcedure
Procedure NetAddressLost(kind.i) : EndProcedure
Procedure.i NtpServiceInput(kind.i) : ProcedureReturn 0 : EndProcedure

; ----------------------------------------------------------------------
;  THE FIXTURE'S TCP, WHICH IS A COUNTER AND NOT A PROTOCOL.
;
;  What section T grades is that a verified segment the console's pump
;  takes off the wire REACHES the transport through NetServiceInput,
;  rather than falling out of the bottom of the dispatcher. A real TCP
;  state machine here would prove nothing extra about that and would
;  drag sockets and timers into an image that has neither a radio nor a
;  MAC. fxTcpKind records NetRxKind() at the moment of the call - the
;  interface the segment arrived on, which is the one the transport must
;  answer through.
; ----------------------------------------------------------------------
Global fxTcpCalls.i
Global fxTcpKind.i
Procedure TcpInput()
  fxTcpCalls = fxTcpCalls + 1
  fxTcpKind = NetRxKind()
EndProcedure

XIncludeFile "__LIB__"

; ---- THE READBACK, over the same seam -------------------------------
; Anvil/Core/readback.pbi is included whole. The harness drives
; ReadbackRun, which is everything that reaches a console; CmdReadback's
; parser and address guard must still COMPILE, so the three names it
; reaches that live in the command layer are answered here and never
; called. OutBreakCtrlC is the fixture's: it answers 1 on the call the
; script names, which is how a stopped stream is produced without a
; keyboard.
Global gParseOk.i
Global gParseOver.i
Procedure.i ParseHex()
  gParseOk = 0
  ProcedureReturn 0
EndProcedure
Procedure.i AddrAllowed(lo.i, hi.i, forWrite.i, *cmd, *nothing)
  ProcedureReturn 1
EndProcedure
Global fxBreakAt.i
Global fxBreakCalls.i
Procedure.i OutBreakCtrlC()
  fxBreakCalls = fxBreakCalls + 1
  If fxBreakAt <> 0 And fxBreakCalls >= fxBreakAt
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure
XIncludeFile "Anvil/Core/crc.pbi"
XIncludeFile "__RBLIB__"

Procedure fxSetMacs(p.i)
  Define i.i
  For i = 0 To 5
    fxWiredMac[i] = PeekA(p + i)
    fxWifiMac[i] = PeekA(p + 6 + i)
  Next
EndProcedure

Procedure fxReset()
  Define i.i
  fxRxHead = 0
  fxRxCount = 0
  fxRxLast = 0
  For i = 0 To #FX_RXQ - 1
    fxRxSlotLen[i] = 0
    fxRxSlotKind[i] = 0
  Next
  fxRxSync()
  fxTxLen = 0
  fxTxCalls = 0
  fxTxKind = 0
  fxLogLen = 0
  fxLogFrames = 0
  fxBreakAt = 0
  fxBreakCalls = 0
  fxWiredReady = 0
  fxWifiReady = 0
  fxArmedKind = 0
  fxArmedOn = 0
  fxArmedCalls = 0
  fxNoteRx = 0
  fxNoteCalls = 0
  fxTcpCalls = 0
  fxTcpKind = 0
  fxMs = 1000
  For i = 0 To 5
    fxWiredMac[i] = 0
    fxWifiMac[i] = 0
  Next
  fxPin = #HW_LINK_NONE
  gConOn = 0
  gConKind = #HW_LINK_NONE
  gConIp = 0
  gConPeerOk = 0
  gConPeerIp = 0
  gConPeerPort = 0
  gConPeerKind = #HW_LINK_NONE
  gConPeerDstIp = 0
  gConInHead = 0
  gConInTail = 0
  gConArms = 0
  gConOwner = #NETCON_OWNER_NONE
  gConMemberMask = 0
  ; THE PUMP'S RATE LIMIT IS A CLOCK READING AND THE CLOCK GOES BACK
  ; HERE. NetConsolePump does nothing until 5 ms after its last turn,
  ; and fxMs is set back to 1000 below - so a section that had already
  ; advanced the clock past that would leave the pump refusing to run
  ; for the whole of the next section, silently, and every case in it
  ; would fail for a reason that has nothing to do with the console.
  gConLastPump = 0
  UartAuxMirror(0)
  DhcpdStop()
  NetIfReset()
  NetInit()
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
  Define ch.i

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
      ; reset, and give the two fixture links their addresses
      fxReset()
      fxSetMacs(blob)
      r = 1
    ElseIf op = 2
      ; a link comes up, or goes down
      If a = #HW_LINK_WIRED
        fxWiredReady = b
      ElseIf a = #HW_LINK_WIFI
        fxWifiReady = b
      EndIf
      r = HwLinkReady(a)
    ElseIf op = 3
      ; AN ADDRESS ARRIVES ON A PATH THE CONSOLE KNOWS NOTHING ABOUT.
      ; This is what the portable dhcp command, net ip and the
      ; settings-driven configuration all look like from inside the
      ; console: the IP layer ends up configured for one interface's
      ; hardware address and no flag anywhere was set.
      ;   d = the interface
      r = NetSetMac(d, blob)
      e1 = NetSetIPv4(d, a, b, c)
      e2 = NetError()
    ElseIf op = 4
      ; ONE SPIN OF THE PROMPT.
      NetConsoleRearm()
      r = NetConsoleOn()
      e1 = NetConsoleKind()
      e2 = NetConsoleIp()
    ElseIf op = 5
      ; arming asked for directly, naming a kind
      NetConsoleStart(a)
      r = NetConsoleOn()
      e1 = NetConsoleKind()
    ElseIf op = 6
      ; A FRAME ARRIVES ON LINK `a`, BEHIND ANYTHING ALREADY WAITING.
      ; Staging twice with no pump in between is how a case puts two
      ; frames on the wire at once, which is the ordinary state of a
      ; real segment.
      If fxRxCount >= #FX_RXQ Or ln > #FX_FRAME_MAX
        ; Refused loudly rather than silently dropping a frame a case
        ; believes it staged. -1 is not a length.
        r = -1
      Else
        n = fxRxHead + fxRxCount
        If n >= #FX_RXQ
          n = n - #FX_RXQ
        EndIf
        i = 0
        While i < ln
          fxRx[n * #FX_FRAME_MAX + i] = PeekA(blob + i)
          i = i + 1
        Wend
        fxRxSlotLen[n] = ln
        fxRxSlotKind[n] = a
        fxRxCount = fxRxCount + 1
        fxRxSync()
        r = ln
        n = 0
      EndIf
      e1 = fxRxCount
    ElseIf op = 7
      ; one turn of the console pump
      NetConsolePump()
      r = fxTxCalls
      e1 = fxTxLen
      e2 = NetConsolePeerOk()
    ElseIf op = 8
      ; drain the keystroke ring into the result blob
      n = 0
      Repeat
        ch = NetConsoleGetc()
        If ch < 0
          Break
        EndIf
        PokeB(#H_RESULT + $00400000 + n, ch)
        n = n + 1
      ForEver
      r = n
      src = #H_RESULT + $00400000
    ElseIf op = 9
      ; the wire, the link it left through, and then clear it
      n = fxTxLen
      src = @fxTx[0]
      r = fxTxLen
      e1 = fxTxCalls
      e2 = fxTxKind
      fxTxLen = 0
    ElseIf op = 10
      ; print the blob and flush it to the peer
      i = 0
      While i < ln
        UartWrite(PeekA(blob + i))
        i = i + 1
      Wend
      NetConsoleFlush()
      r = fxTxCalls
      e1 = fxTxLen
      e2 = fxTxKind
    ElseIf op = 11
      r = NetConsoleOn()
      e1 = gConPeerIp
      e2 = gConPeerPort
    ElseIf op = 12
      fxMs = fxMs + a
      r = fxMs
    ElseIf op = 13
      ; a command binds a port of its own (ping, dns, dhcp)
      ; every interface, the widest a command can take it
      r = NetUdpBind(#HW_LINK_NONE, a)
    ElseIf op = 14
      ; what hardware address is the IP layer configured with
      r = NetMacSet(a)
      n = 6
      src = #H_RESULT + $00400000
      NetGetMac(a, src)
    ElseIf op = 15
      ; how many times the console has armed, and where it is now
      r = NetConsoleArmCount()
      e1 = NetConsoleKind()
      e2 = NetConsoleIp()
    ElseIf op = 16
      ; what the console last told the board through the seam
      r = fxArmedCalls
      e1 = fxArmedKind
      e2 = fxArmedOn
    ElseIf op = 17
      ; is a frame still waiting on the fixture, unconsumed
      r = fxRxPending
      e1 = fxRxKind
    ElseIf op = 18
      ; AN ADDRESS ARRIVES ON AN INTERFACE. This is what every path that
      ; binds an address looks like from inside the console since
      ; 2026-09-07: a record against a KIND, which leaves every other
      ; interface's record exactly as it was.
      ;   a = kind, b = ip, c = mask, d = gateway, blob = the source code
      ;   an address of zero is the interface forgetting its address
      If b = 0
        NetIfClear(a)
        r = 1
      Else
        r = NetIfSet(a, b, c, d, PeekA(blob))
      EndIf
      e1 = NetIfCount()
      e2 = NetIPv4(a)
    ElseIf op = 19
      ; the board takes the DHCP server role on link `a`, or gives it up
      If b <> 0
        r = DhcpdStart(a)
      Else
        DhcpdStop()
        r = 0
      EndIf
      e1 = DhcpdOn()
      e2 = NetIPv4Alt(a)
    ElseIf op = 20
      ; the table, as `net` reads it
      r = NetIfCount()
      e1 = NetIPv4(a)
      e2 = NetIfSrc(a)
    ElseIf op = 21
      ; what the DHCP server has done so far
      r = DhcpdOn()
      e1 = DhcpdOffers()
      e2 = DhcpdAcks()
    ElseIf op = 22
      ; an interface is pinned, or the board is left to choose
      fxPin = a
      r = NetIfPreferred()
    ElseIf op = 23
      ; which interface the peer is on, and which of our addresses it
      ; spoke to
      r = NetConsolePeerOk()
      e1 = gConPeerKind
      e2 = gConPeerDstIp
    ElseIf op = 24
      ; A COMMAND COMPLETED. The console has ONE owner at a time: the
      ; first host to send a datagram owns the session until the command
      ; it typed has run, and every other host is answered BUSY. This is
      ; the normal release point the monitor calls after each command.
      NetConsoleCommandDone()
      r = NetConsolePeerOk()
    ElseIf op = 25
      ; bytes for a readback to read, copied to address a
      i = 0
      While i < ln
        PokeB(a + i, PeekA(blob + i))
        i = i + 1
      Wend
      r = ln
    ElseIf op = 26
      ; THE READBACK, through the real console output path
      r = ReadbackRun(a, b)
      e1 = gRbDatagrams
      e2 = gRbFails
    ElseIf op = 27
      ; every frame since the last read, length-prefixed, then clear it
      n = fxLogLen
      src = @fxLog[0]
      r = fxLogFrames
      fxLogLen = 0
      fxLogFrames = 0
    ElseIf op = 28
      ; OutBreakCtrlC answers 1 from call `a` on; 0 is never
      fxBreakAt = a
      fxBreakCalls = 0
      r = a
    ElseIf op = 29
      ; the finished CRC-32 of b bytes at a
      r = Crc32(a, b) & $FFFFFFFF
    ElseIf op = 30
      ; the RUNNING accumulator: c fed b more bytes at a, not finalised
      r = Crc32Part(c, a, b) & $FFFFFFFF
    ElseIf op = 31
      ; WHAT THE PUMP LEFT ON THE WIRE, AND WHAT IT SAYS IT TOOK.
      ; r is frames still queued in the fixture, which is the number that
      ; grades the drain: 0 when one pump emptied the ring, and whatever
      ; was behind the first frame when a pump stopped after one.
      r = fxRxCount
      e1 = NetConsoleRxFrames()
      e2 = NetConsoleRxFull()
    ElseIf op = 32
      ; DID A SEGMENT REACH THE TRANSPORT, AND FROM WHICH INTERFACE.
      ; r = times TcpInput was entered, e1 = NetRxKind() at that call.
      ; Both go back to zero on op 1.
      r = fxTcpCalls
      e1 = fxTcpKind
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
  UartWriteStr("netconharness done")
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
            return sum(mem.get(addr + off + i, 0) << (8 * i)
                       for i in range(4))
        op = w(0)
        if op == 0:
            break
        n = w(16)
        if n > 32768:
            raise SystemExit(
                "a result record claims %d bytes, which is longer than any "
                "buffer in this harness. The result stream is corrupt." % n)
        blob = bytes(mem.get(addr + 20 + i, 0) for i in range(n))
        i = len(out)
        out.append(Result(op, _signed(w(4)), _signed(w(8)), _signed(w(12)),
                          blob, labels[i] if i < len(labels) else "?"))
        addr += 20 + ((n + 3) // 4) * 4
    return out


# =====================================================================
#  BUILD AND RUN
# =====================================================================
def write_harness(lib_include: str, path: pathlib.Path,
                  rb_include: str = "Anvil/Core/readback.pbi") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = HARNESS.replace("__BORROWED__", borrow_constants())
    text = text.replace("__LIB__", lib_include)
    text = text.replace("__RBLIB__", rb_include)
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

    def load(addr, size):
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
            cpu.x[ins & 31] = CNTFRQ
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
#  THE SCRIPT
# =====================================================================
WIRED_MAC = bytes([0x02, 0x11, 0x22, 0x33, 0x44, 0x55])
RADIO_MAC = bytes([0x02, 0xAA, 0xBB, 0xCC, 0xDD, 0xEE])
MACS = WIRED_MAC + RADIO_MAC
PEER_MAC = bytes([0x02, 0x99, 0x88, 0x77, 0x66, 0x01])

# The cable straight between a PC and a board, which is where this work
# came from: Windows connection sharing hands out 192.168.137.x.
WIRED_IP = ip4(192, 168, 137, 2)
WIRED_MASK = ip4(255, 255, 255, 0)
WIRED_GW = ip4(192, 168, 137, 1)
WIRED_PEER = ip4(192, 168, 137, 1)

RADIO_IP = ip4(192, 168, 1, 25)
RADIO_MASK = ip4(255, 255, 255, 0)
RADIO_GW = ip4(192, 168, 1, 1)
RADIO_PEER = ip4(192, 168, 1, 9)

PEER_PORT = 41234

# The three ways an address gets onto an interface, from
# Anvil/Core/netcfg.pbi. Written here as plain numbers on purpose: the
# gate must not read its expectations out of the thing it is grading.
ADDR_LEASE = 1
ADDR_SAVED = 2
ADDR_LINKLOCAL = 3

# The link-local address a board gives itself on a bare cable, and the
# one a laptop at the other end has already given itself. Both ends of
# the bench cable on 2026-09-07 looked exactly like this.
WIRED_LL = ip4(169, 254, 170, 250)
LL_MASK = ip4(255, 255, 0, 0)
LL_PEER = ip4(169, 254, 183, 67)

# The subnet this board serves when nothing else on the cable does.
DHCPD_SELF = ip4(192, 168, 137, 1)
DHCPD_POOL_LO = ip4(192, 168, 137, 2)
DHCPD_POOL_HI = ip4(192, 168, 137, 20)

TYPED = b"info\n"
TYPED2 = b"uptime\n"
TYPED3 = b"version\n"
ANSWERED = b"Anvil answers over the cable.\r\n"
ANSWERED2 = b"Anvil answers over the air.\r\n"

# The announcement, matched as a PREFIX. It names no interface any
# more: since 2026-09-07 the console lists every interface it is
# listening on, one to a line, because a board that listens on two
# and reports one sends whoever is connecting to the wrong address.
LISTENING = b"Network console listening on UDP"

# ---- L. the readback. Three ranges so each run's header is unique in
# ---- the serial capture, and one pattern that holds every byte value.
RB_ADDR_NET = 0x07000000
RB_ADDR_LOCAL = 0x07010000
RB_ADDR_STOP = 0x07020000
# 2000 bytes: two full 720-byte blocks and a 560-byte third, 41 full
# 48-byte lines and a 32-byte last line that carries one '='.
RB_NET_BYTES = 2000
# 721 bytes: one full block, then a block of ONE byte, which is the
# two-'=' branch of the encoder.
RB_LOCAL_BYTES = 721
# A DIFFERENT pattern at each address, so a base64 line found on the
# serial capture can only have come from the run that owns that range.
# Hash-derived, NOT an affine sequence: `i * 131 + seed` with two seeds is
# the same sequence shifted, so one run's first line turns up inside the
# other run's stream and the serial assertion fails on a pattern that was
# never on the wrong path. That happened on this gate's first run.
def rb_pattern(seed: int) -> bytes:
    out = b""
    counter = 0
    while len(out) < 2000:
        out += hashlib.sha256(b"readback %d %d" % (seed, counter)).digest()
        counter += 1
    return out[:2000]


RB_PATTERNS = {RB_ADDR_NET: rb_pattern(7), RB_ADDR_LOCAL: rb_pattern(61),
               RB_ADDR_STOP: rb_pattern(113)}
# The monitor's numbers, restated independently: 48 bytes of memory a
# base64 line, 720 bytes a datagram. If the file changes either without
# this changing too, the count below goes red, which is the point.
RB_LINE = 48
RB_BLOCK = 720

# ---- L7. the checksum under every verdict
CRC_ADDR = 0x07030000
CRC_LENGTHS = (0, 1, 2, 3, 255, 256)
CRC_SPLIT = 100
# The running accumulator after the first CRC_SPLIT bytes, computed here
# so the second feed can be handed it in the SAME script - the harness has
# no way to pass one step's answer into the next. zlib's value is the
# FINISHED one, so the running one is its complement.
CRC_PART1_PLACEHOLDER = zlib.crc32(bytes(range(CRC_SPLIT))) ^ 0xFFFFFFFF


def datagram(peer_ip: int, board_ip: int, board_mac: bytes,
             payload: bytes) -> bytes:
    return eth(board_mac, PEER_MAC, ET_IPV4,
               udp(peer_ip, board_ip, PEER_PORT, NETCON_PORT, payload))


# ---- T. a TCP segment. Built with a real pseudo-header checksum, because
# ---- the IP layer VERIFIES it before it answers #NET_IN_TCP; a segment
# ---- that failed the checksum is not TCP to the dispatcher, and the
# ---- positive case and the negative control would then agree for the
# ---- same wrong reason.
IPPROTO_TCP = 6
TCP_SYN = 0x02


def tcp_segment(src_ip: int, dst_ip: int, sport: int, dport: int,
                seq: int, flags: int) -> bytes:
    seg = bytearray(20)
    seg[0:2] = struct.pack(">H", sport)
    seg[2:4] = struct.pack(">H", dport)
    seg[4:8] = struct.pack(">I", seq)
    seg[12] = 5 << 4                        # data offset: five words
    seg[13] = flags
    seg[14:16] = struct.pack(">H", 8192)
    pseudo = (struct.pack(">II", src_ip, dst_ip)
              + bytes([0, IPPROTO_TCP]) + struct.pack(">H", len(seg)))
    seg[16:18] = struct.pack(">H", ones_complement(pseudo + bytes(seg)))
    return ipv4(src_ip, dst_ip, IPPROTO_TCP, bytes(seg), 0x2345)


def segment_frame(peer_ip: int, board_ip: int, board_mac: bytes,
                  dport: int = 80) -> bytes:
    return eth(board_mac, PEER_MAC, ET_IPV4,
               tcp_segment(peer_ip, board_ip, PEER_PORT, dport,
                           0x11223344, TCP_SYN))


BCAST_MAC = bytes([0xFF] * 6)


def dhcp_msg(msg_type: int, mac: bytes, req_ip: int = 0,
             op: int = 1, xid: int = 0x5A5A0001) -> bytes:
    """A BOOTP message, written from RFC 2131 and not from the library."""
    m = bytearray(240)
    m[0] = op
    m[1] = 1                                   # htype ether
    m[2] = 6                                   # hlen
    m[4:8] = xid.to_bytes(4, "big")
    m[28:34] = mac
    m[236:240] = (0x63825363).to_bytes(4, "big")
    m += bytes([53, 1, msg_type])
    if req_ip:
        m += bytes([50, 4]) + req_ip.to_bytes(4, "big")
    m += bytes([255])
    return bytes(m)


def dhcp_frame(mac: bytes, msg_type: int, req_ip: int = 0,
               op: int = 1) -> bytes:
    """That message on the wire: a broadcast from 0.0.0.0, as a client
    with no address of its own has to send it."""
    return eth(BCAST_MAC, mac, ET_IPV4,
               udp(0, 0xFFFFFFFF, DHCP_CLIENT_PORT, DHCP_SERVER_PORT,
                   dhcp_msg(msg_type, mac, req_ip, op)))


DHCP_SERVER_PORT = 67
DHCP_CLIENT_PORT = 68
CLIENT_MAC = bytes([0x02, 0x77, 0x66, 0x55, 0x44, 0x33])


def dhcp_request_naming(mac: bytes, server_id: int, req_ip: int) -> bytes:
    """A DHCPREQUEST that names the server the client chose (option 54)."""
    m = bytearray(dhcp_msg(3, mac, req_ip))
    assert m[-1] == 255
    del m[-1]
    m += bytes([54, 4]) + server_id.to_bytes(4, "big")
    m += bytes([255])
    return bytes(m)


def build_script() -> tuple[Script, dict]:
    s = Script()
    at: dict[str, int] = {}

    # ==== A. an address on a link that cannot carry a frame ==========
    #  The record is made against the WIRED interface with the cable
    #  out. NetIfUsable is HAS AN ADDRESS **AND** CAN CARRY A FRAME, and
    #  a console announced on an interface that cannot transmit is a
    #  board that says it is listening and answers nobody.
    at["reset_a"] = s.add(1, blob=MACS, label="reset")
    at["addr_a"] = s.add(18, LINK_WIRED, WIRED_IP, WIRED_MASK, WIRED_GW,
                         blob=bytes([ADDR_SAVED]),
                         label="the wired side is given an address")
    at["deaf_down"] = s.add(4, label="a prompt spin with the link down")
    at["direct_down"] = s.add(5, LINK_WIRED,
                              label="arming asked for on a down link")

    # ==== B. the cable comes up: one spin arms, nobody typed =========
    at["wired_up"] = s.add(2, LINK_WIRED, 1, label="the cable is plugged in")
    at["armed_wired"] = s.add(4, label="the next prompt spin")

    # ==== C. a datagram over the CABLE, and the answer back out =====
    at["rx_wired"] = s.add(6, LINK_WIRED,
                           blob=datagram(WIRED_PEER, WIRED_IP, WIRED_MAC,
                                         TYPED),
                           label="a datagram over the cable")
    at["pump_wired"] = s.add(7, label="one turn of the pump")
    # The board is told which links the console is on by the PUMP, as it
    # walks the addressed interfaces - not by the arming itself.
    at["told_board"] = s.add(16, label="what the board was told")
    at["ring_wired"] = s.add(8, label="the keystroke ring")
    at["peer_wired"] = s.add(11, label="the peer the board learned")
    at["clear_w"] = s.add(9, label="clear the wire")
    at["answer_w"] = s.add(10, blob=ANSWERED, label="the board answers")
    at["wire_wired"] = s.add(9, label="the datagram on the wire")

    # ==== H. A DATAGRAM ON THE SECOND ADDRESSED INTERFACE ===========
    #  The radio comes up and takes an address of its own, and a console
    #  datagram arrives on it while the console announces the cable. It
    #  must be CONSUMED and it must reach the ring: the console listens
    #  on every interface that holds an address. Before 2026-09-07 this
    #  case required the opposite, and it was right then - see the
    #  grading, which says what it used to measure and why.
    at["wifi_up_h"] = s.add(2, LINK_WIFI, 1, label="the radio comes up")
    at["wifi_addr_h"] = s.add(18, LINK_WIFI, RADIO_IP, RADIO_MASK, RADIO_GW,
                              blob=bytes([ADDR_LEASE]),
                              label="the radio takes an address")
    #  THE HOST ON THE CABLE STILL OWNS THE SESSION. A second host is
    #  answered BUSY on the interface it spoke on, and its bytes must not
    #  reach the keystroke ring - two hosts typing into one command line
    #  is two half-commands.
    at["rx_busy"] = s.add(6, LINK_WIFI,
                          blob=datagram(RADIO_PEER, RADIO_IP, RADIO_MAC,
                                        TYPED3),
                          label="a second host speaks on the radio")
    at["tick_hb"] = s.add(12, 50, label="50 ms of prompt spinning")
    at["pump_busy"] = s.add(7, label="one turn of the pump")
    at["ring_busy"] = s.add(8, label="the ring - must be empty")
    at["wire_busy"] = s.add(9, label="the answer to the second host")
    at["done_h"] = s.add(24, label="the cable host's command completes")
    at["rx_other"] = s.add(6, LINK_WIFI,
                           blob=datagram(RADIO_PEER, RADIO_IP, RADIO_MAC,
                                         TYPED3),
                           label="a datagram on the radio")
    at["tick_h"] = s.add(12, 50, label="50 ms of prompt spinning")
    at["pump_other"] = s.add(7, label="one turn of the pump")
    at["still_there"] = s.add(17, label="is that frame still queued")
    at["ring_other"] = s.add(8, label="the ring after that pump")
    #  and the radio is put back down, so section E can bring it up as
    #  the join it is modelling.
    at["wifi_down_h"] = s.add(2, LINK_WIFI, 0, label="the radio drops again")
    at["wifi_clear_h"] = s.add(18, LINK_WIFI, 0, 0, 0, blob=bytes([0]),
                               label="and forgets its address")

    # ==== F. idempotent, and the line prints once ====================
    for i in range(10):
        at["spin%d" % i] = s.add(4, label="prompt spin %d" % i)
    at["arms_f"] = s.add(15, label="how many times it has armed")

    # ==== G. a command steals the port; the next spin puts it back ===
    at["steal"] = s.add(13, 53, label="dns binds port 53")
    at["rearm"] = s.add(4, label="the prompt puts the port back")
    at["tick_g"] = s.add(12, 50, label="50 ms of prompt spinning")
    at["rx_g"] = s.add(6, LINK_WIRED,
                       blob=datagram(WIRED_PEER, WIRED_IP, WIRED_MAC,
                                     TYPED2),
                       label="a second datagram over the cable")
    at["pump_g"] = s.add(7, label="pump after the port was stolen")
    at["ring_g"] = s.add(8, label="the ring after the port was stolen")

    # ==== E. THE RADIO JOINS, AND TAKES NOTHING FROM THE CABLE =======
    #  This is the sequence that was measured on silicon on 2026-09-07
    #  and it is the reason this whole layer exists. The cable is up and
    #  answering; the radio finishes joining and takes its lease. Before
    #  the per-interface table that lease became the board's ONLY
    #  address, the console re-armed onto the radio, and the laptop on
    #  the cable lost the board mid-session with nothing touched.
    #
    #  NOTHING MAY MOVE, AND NOTHING MAY BE FORGOTTEN. The cable keeps
    #  its address, the console keeps announcing the cable (the wire is
    #  preferred whenever it is up), the peer on the cable is still the
    #  peer, and the console has NOT re-armed.
    at["wifi_up"] = s.add(2, LINK_WIFI, 1, label="the radio joins as well")
    at["radio_lease"] = s.add(18, LINK_WIFI, RADIO_IP, RADIO_MASK, RADIO_GW,
                              blob=bytes([ADDR_LEASE]),
                              label="the radio takes its lease")
    at["spin_both"] = s.add(4, label="a prompt spin with both links up")
    at["wired_still"] = s.add(20, LINK_WIRED,
                              label="the cable's own record afterwards")
    at["radio_rec"] = s.add(20, LINK_WIFI,
                            label="the radio's own record")
    at["peer_kept"] = s.add(11, label="the peer after the radio joined")
    at["arms_e"] = s.add(15, label="armings after the radio joined")

    # ==== D. AND THE CONSOLE ANSWERS ON THE RADIO TOO, AT THE SAME
    #         TIME, WITHOUT THE CABLE HAVING GONE ANYWHERE.
    at["clear_r"] = s.add(9, label="clear the wire")
    at["done_d"] = s.add(24, label="the cable host's command completes")
    at["rx_radio"] = s.add(6, LINK_WIFI,
                           blob=datagram(RADIO_PEER, RADIO_IP, RADIO_MAC,
                                         TYPED),
                           label="a datagram over the radio")
    at["tick_d"] = s.add(12, 50, label="50 ms of prompt spinning")
    at["pump_radio"] = s.add(7, label="one turn of the pump")
    at["ring_radio"] = s.add(8, label="the keystroke ring")
    at["peer_radio"] = s.add(23, label="which interface the peer is on now")
    at["clear_r2"] = s.add(9, label="clear the wire again")
    at["answer_r"] = s.add(10, blob=ANSWERED2, label="the board answers")
    at["wire_radio"] = s.add(9, label="the datagram on the wire")

    # ==== J. AND STRAIGHT BACK OUT OF THE CABLE, SAME BOOT, NO SPIN
    #         IN BETWEEN. A console that can only answer whichever link
    #         spoke last is a console on one link with extra steps.
    at["clear_w2"] = s.add(9, label="clear the wire")
    at["done_j"] = s.add(24, label="the radio host's command completes")
    at["rx_wired2"] = s.add(6, LINK_WIRED,
                            blob=datagram(WIRED_PEER, WIRED_IP, WIRED_MAC,
                                          TYPED3),
                            label="a datagram over the cable again")
    at["tick_j"] = s.add(12, 50, label="50 ms of prompt spinning")
    at["pump_wired2"] = s.add(7, label="one turn of the pump")
    at["ring_wired2"] = s.add(8, label="the keystroke ring")
    at["peer_wired2"] = s.add(23, label="which interface the peer is on now")
    at["clear_w3"] = s.add(9, label="clear the wire again")
    at["answer_w2"] = s.add(10, blob=ANSWERED, label="the board answers")
    at["wire_wired2"] = s.add(9, label="the datagram on the wire")

    # ==== K. THE BOARD AS THE DHCP SERVER ON A BARE CABLE ============
    #  A fresh board: the cable is in, nothing answered its discovers,
    #  so it holds a link-local address AND serves 192.168.137.0/24. A
    #  laptop whose Ethernet port is a DHCP client - which is what an
    #  Ethernet port is by default - must get a real lease with nothing
    #  changed on it, and that exchange has to happen at an idle prompt,
    #  where the console's pump is the only thing running.
    at["reset_k"] = s.add(1, blob=MACS, label="a fresh board")
    at["wired_up_k"] = s.add(2, LINK_WIRED, 1, label="the cable is in")
    at["ll_k"] = s.add(18, LINK_WIRED, WIRED_LL, LL_MASK, 0,
                       blob=bytes([ADDR_LINKLOCAL]),
                       label="it gives itself a link-local address")
    at["serve_k"] = s.add(19, LINK_WIRED, 1,
                          label="and takes the DHCP server role")
    at["arm_k"] = s.add(4, label="a prompt spin")
    at["rx_disc"] = s.add(6, LINK_WIRED,
                          blob=dhcp_frame(CLIENT_MAC, 1),
                          label="a DHCPDISCOVER arrives on the cable")
    at["clear_k"] = s.add(9, label="clear the wire")
    at["pump_disc"] = s.add(7, label="the pump at an idle prompt")
    at["wire_offer"] = s.add(9, label="the OFFER on the wire")
    at["ring_k"] = s.add(8, label="the keystroke ring - must be empty")
    at["counts_k"] = s.add(21, label="what the server has done")

    #  ... and a real server appearing ends the role at once.
    #  A RIVAL SERVER, AS THIS BOARD CAN ACTUALLY SEE ONE. The rival's
    #  OFFER is addressed to port 68 - the CLIENT's - and never reaches
    #  a server listening on 67. What DOES reach it is what the client
    #  does next: RFC 2131 4.3.2 has a client in SELECTING broadcast its
    #  REQUEST to port 67 with option 54 naming the server it chose,
    #  precisely so that every other server on the segment learns it
    #  lost. A client cannot name a server identifier it was not
    #  offered, so this is conclusive rather than circumstantial.
    at["rx_real"] = s.add(6, LINK_WIRED,
                          blob=eth(BCAST_MAC, CLIENT_MAC, ET_IPV4,
                                   udp(0, 0xFFFFFFFF,
                                       DHCP_CLIENT_PORT, DHCP_SERVER_PORT,
                                       dhcp_request_naming(
                                           CLIENT_MAC,
                                           ip4(192, 168, 137, 254),
                                           ip4(192, 168, 137, 50)))),
                          label="a client accepts ANOTHER server's offer")
    at["tick_k"] = s.add(12, 50, label="50 ms of prompt spinning")
    at["pump_real"] = s.add(7, label="the pump sees it")
    at["stood_down"] = s.add(21, label="the server role afterwards")
    at["alias_gone"] = s.add(20, LINK_WIRED,
                             label="the cable's record afterwards")

    # ==== L0. THE DRAIN. ONE PUMP EMPTIES THE RING, NOT ONE FRAME =====
    #  WHAT IT MODELS is not exotic: three frames arrive on the radio
    #  between two turns of the prompt, which is a quiet second on a home
    #  network. On silicon, with a pump that took one frame per call, the
    #  console answered 5 probes of 20 while ICMP answered 19 of 20 in the
    #  same seconds - a ping is answered inside the slice that took its
    #  frame, and a console datagram had to survive the queue first.
    #
    #  NO RECEIVE CLAIM IS HELD. netcon_PumpOne stands down on an
    #  interface a running command has claimed; the reset below releases
    #  any claim (NetIfReset), so the pump is free to read the radio.
    #
    #  THE ASSERTIONS ARE INDEPENDENT: the ring must be EMPTY after one
    #  pump (frames left behind are the defect itself), and all three
    #  payloads must be in the keystroke ring IN ORDER (a pump that handed
    #  back one slot's bytes three times would satisfy the first and fail
    #  this one).
    at["reset_d"] = s.add(1, blob=MACS, label="a clean fixture")
    at["wifi_up_d"] = s.add(2, LINK_WIFI, 1, label="the radio is up")
    at["wifi_addr_d"] = s.add(18, LINK_WIFI, RADIO_IP, RADIO_MASK, RADIO_GW,
                              blob=bytes([ADDR_LEASE]),
                              label="the radio holds an address")
    at["arm_d"] = s.add(4, label="a prompt spin arms the console")
    for i, payload in enumerate((TYPED, TYPED2, TYPED3)):
        at["rx_d%d" % i] = s.add(
            6, LINK_WIFI,
            blob=datagram(RADIO_PEER, RADIO_IP, RADIO_MAC, payload),
            label="datagram %d of 3 arrives with no pump in between"
                  % (i + 1))
    at["queued_d"] = s.add(31, label="three frames waiting, none consumed")
    at["tick_d0"] = s.add(12, 50, label="50 ms of prompt spinning")
    at["pump_d"] = s.add(7, label="ONE turn of the pump")
    at["drained_d"] = s.add(31, label="what one pump left behind")
    at["ring_d"] = s.add(8, label="the keystroke ring after one pump")

    # ==== T. THE CONSOLE'S PUMP HANDS A TCP SEGMENT TO TCP ============
    #  netcon_PumpOne gives every verdict to NetServiceInput, and a
    #  verified segment must leave there through TcpInput. On a branch
    #  where the pump had no arm for it, the segment fell out of the
    #  bottom of the procedure with no counter and no trace - and since
    #  the console's pump and the link's own pump race for every frame,
    #  that cost a share of every connection even on a one-link board.
    #
    #  WHY THE CABLE IS PINNED AND THE SEGMENT ARRIVES ON THE RADIO. The
    #  link's own pump reads the SELECTED link, so a segment on the other
    #  interface is seen by this pump and by nothing else: that is the
    #  shape in which a lost segment is lost completely.
    #
    #  THE ASSERTIONS: the transport is entered exactly once, with the
    #  receive kind naming the radio; nothing lands in the keystroke ring;
    #  and afterwards a console datagram on the same link still arrives.
    at["reset_t"] = s.add(1, blob=MACS, label="a clean fixture")
    at["wifi_up_t"] = s.add(2, LINK_WIFI, 1, label="the radio is up")
    at["wifi_addr_t"] = s.add(18, LINK_WIFI, RADIO_IP, RADIO_MASK, RADIO_GW,
                              blob=bytes([ADDR_LEASE]),
                              label="the radio holds an address")
    at["wired_up_t"] = s.add(2, LINK_WIRED, 1, label="the cable is in too")
    at["wired_addr_t"] = s.add(18, LINK_WIRED, WIRED_IP, WIRED_MASK,
                               WIRED_GW, blob=bytes([ADDR_SAVED]),
                               label="the cable holds an address")
    at["pin_t"] = s.add(22, LINK_WIRED,
                        label="outbound traffic is pinned to the cable")
    at["arm_t"] = s.add(4, label="a prompt spin arms the console")
    at["before_t"] = s.add(32, label="no segment has arrived yet")
    at["rx_seg_t"] = s.add(
        6, LINK_WIFI,
        blob=segment_frame(RADIO_PEER, RADIO_IP, RADIO_MAC),
        label="a TCP segment arrives on the NON-selected link")
    at["tick_t"] = s.add(12, 50, label="50 ms of prompt spinning")
    at["pump_t"] = s.add(7, label="one turn of the console pump")
    at["left_t"] = s.add(31, label="what the pump left on the wire")
    at["fed_t"] = s.add(32, label="did the segment reach TCP")
    at["ring_t"] = s.add(8, label="the keystroke ring - a segment is not typing")
    #  AND THE CONSOLE STILL WORKS ON THE SAME WIRE AFTERWARDS. A fix
    #  that fed TCP by breaking the datagram path passes everything above.
    at["rx_udp_t"] = s.add(6, LINK_WIFI,
                           blob=datagram(RADIO_PEER, RADIO_IP, RADIO_MAC,
                                         TYPED2),
                           label="a console datagram on the same link")
    at["tick_t2"] = s.add(12, 50, label="50 ms of prompt spinning")
    at["pump_t2"] = s.add(7, label="one more turn of the pump")
    at["ring_t2"] = s.add(8, label="the keystroke ring after the datagram")
    at["fed_t2"] = s.add(32, label="and TCP was not entered for a datagram")

    # ==== L. A BULK READBACK =========================================
    #  A fresh board on the cable, a host that types `readback`, and the
    #  range read back through Anvil/Core/readback.pbi's ReadbackRun -
    #  which is every line of that file that reaches a console. Then the
    #  same stream typed on the LOCAL console, and then a stopped one.
    at["reset_l"] = s.add(1, blob=MACS, label="a fresh board")
    at["wired_up_l"] = s.add(2, LINK_WIRED, 1, label="the cable is in")
    at["addr_l"] = s.add(18, LINK_WIRED, WIRED_IP, WIRED_MASK, WIRED_GW,
                         blob=bytes([ADDR_SAVED]),
                         label="the cable holds an address")
    at["arm_l"] = s.add(4, label="a prompt spin arms the console")
    at["load_l"] = s.add(25, RB_ADDR_NET, blob=RB_PATTERNS[RB_ADDR_NET],
                         label="bytes for the network readback")
    at["load_l_local"] = s.add(25, RB_ADDR_LOCAL,
                               blob=RB_PATTERNS[RB_ADDR_LOCAL],
                               label="bytes for the local readback")
    at["load_l_stop"] = s.add(25, RB_ADDR_STOP,
                              blob=RB_PATTERNS[RB_ADDR_STOP],
                              label="bytes for the stopped readback")
    at["rx_l"] = s.add(6, LINK_WIRED,
                       blob=datagram(WIRED_PEER, WIRED_IP, WIRED_MAC,
                                     b"readback %X %X\n"
                                     % (RB_ADDR_NET, RB_NET_BYTES)),
                       label="the host on the cable types readback")
    at["pump_l"] = s.add(7, label="the pump takes the line")
    at["clear_l"] = s.add(27, label="clear the wire log")
    at["run_l"] = s.add(26, RB_ADDR_NET, RB_NET_BYTES,
                        label="THE READBACK, for the network peer")
    at["wire_l"] = s.add(27, label="every frame the readback sent")
    at["done_l"] = s.add(24, label="the command completes")
    #  TYPED ON THE LOCAL CONSOLE. No network peer owns this command, so
    #  the payload is the serial port's and the wire must see none of it.
    at["run_l_local"] = s.add(26, RB_ADDR_LOCAL, RB_LOCAL_BYTES,
                              label="the readback, typed locally")
    at["wire_l_local"] = s.add(27, label="the wire - must be silent")
    #  AND STOPPED BEFORE ITS THIRD BLOCK.
    at["rx_l_stop"] = s.add(6, LINK_WIRED,
                            blob=datagram(WIRED_PEER, WIRED_IP, WIRED_MAC,
                                          b"readback %X %X\n"
                                          % (RB_ADDR_STOP, RB_NET_BYTES)),
                            label="the host types readback again")
    #  The pump runs at most once every 5 ms and the fixture clock only
    #  moves when told to, so without this the second line is never read.
    at["tick_l_stop"] = s.add(12, 50, label="50 ms of prompt spinning")
    at["pump_l_stop"] = s.add(7, label="the pump takes the line")
    at["clear_l_stop"] = s.add(27, label="clear the wire log")
    at["break_l"] = s.add(28, 3, label="Ctrl-C arrives before block three")
    at["run_l_stop"] = s.add(26, RB_ADDR_STOP, RB_NET_BYTES,
                             label="the readback that is stopped")
    at["wire_l_stop"] = s.add(27, label="every frame the stopped one sent")
    at["done_l_stop"] = s.add(24, label="the command completes")

    # ==== L7. THE CHECKSUM ITSELF ====================================
    #  Every verdict above rests on Anvil/Core/crc.pbi, which became a
    #  table on the same day. A one-byte CRC of value n indexes the table
    #  at 255 - n, so the 256 single-byte cases touch every entry exactly
    #  once; the lengths and the split feed cover the loop and the
    #  running-accumulator contract the crc32 command relies on.
    at["load_crc"] = s.add(25, CRC_ADDR, blob=bytes(range(256)),
                           label="the 256 byte values")
    for v in range(256):
        at["crc1_%d" % v] = s.add(29, CRC_ADDR + v, 1,
                                  label="crc32 of the byte %02X" % v)
    for n in CRC_LENGTHS:
        at["crcn_%d" % n] = s.add(29, CRC_ADDR, n,
                                  label="crc32 of the first %d bytes" % n)
    at["crc_part1"] = s.add(30, CRC_ADDR, CRC_SPLIT, 0xFFFFFFFF,
                            label="the running accumulator, first part")
    at["crc_part2"] = s.add(30, CRC_ADDR + CRC_SPLIT, 256 - CRC_SPLIT,
                            CRC_PART1_PLACEHOLDER,
                            label="... fed the rest")

    return s, at


# =====================================================================
#  THE GRADING
# =====================================================================
def expect(cond, what, fails):
    if not cond:
        fails.append(what)


def hexdiff(got: bytes, want: bytes) -> str:
    lines = ["      got  %s" % got.hex(),
             "      want %s" % want.hex()]
    for i in range(min(len(got), len(want))):
        if got[i] != want[i]:
            lines.append("      first difference at byte %d: %02x vs %02x"
                         % (i, got[i], want[i]))
            break
    else:
        if len(got) != len(want):
            lines.append("      lengths differ: %d vs %d"
                         % (len(got), len(want)))
    return "\n".join(lines)


def grade_answer(tag: str, blob: bytes, board_mac: bytes, board_ip: int,
                 peer_ip: int, want_payload: bytes,
                 fails: list[str]) -> None:
    """The datagram the board sent back, field by field."""
    total = 14 + 20 + 8 + len(want_payload)
    if len(blob) != total:
        fails.append(
            "%s the answer on the wire is %d bytes and a UDP datagram "
            "carrying %d bytes of payload is %d"
            % (tag, len(blob), len(want_payload), total))
        return
    expect(blob[0:6] == PEER_MAC,
           "%s the answer is addressed to %s and the host that spoke is %s "
           "- the com-port model replies to whoever sent the datagram, "
           "using the hardware address out of that very frame"
           % (tag, blob[0:6].hex(), PEER_MAC.hex()), fails)
    expect(blob[6:12] == board_mac,
           "%s the answer leaves as %s and the interface it is on is %s"
           % (tag, blob[6:12].hex(), board_mac.hex()), fails)
    expect(blob[12:14] == b"\x08\x00",
           "%s the answer's ethertype is %s, not IPv4"
           % (tag, blob[12:14].hex()), fails)
    ip = blob[14:34]
    expect(ip[0] == 0x45,
           "%s the answer's IP version/IHL byte is %02x, not 45"
           % (tag, ip[0]), fails)
    expect(ip[9] == IPPROTO_UDP,
           "%s the answer's IP protocol is %d, not %d (UDP)"
           % (tag, ip[9], IPPROTO_UDP), fails)
    src = int.from_bytes(ip[12:16], "big")
    dst = int.from_bytes(ip[16:20], "big")
    expect(src == board_ip,
           "%s the answer's source address is %08x and the address the "
           "console armed on is %08x - it is announcing an address the "
           "board does not have" % (tag, src, board_ip), fails)
    expect(dst == peer_ip,
           "%s the answer's destination is %08x, not the host's %08x"
           % (tag, dst, peer_ip), fails)
    expect(ones_complement(ip[:20]) == 0,
           "%s the answer's IPv4 header checksum does not verify" % tag,
           fails)
    u = blob[34:42]
    sport = int.from_bytes(u[0:2], "big")
    dport = int.from_bytes(u[2:4], "big")
    ulen = int.from_bytes(u[4:6], "big")
    expect(sport == NETCON_PORT,
           "%s the answer leaves from port %d and the console's port is %d"
           % (tag, sport, NETCON_PORT), fails)
    expect(dport == PEER_PORT,
           "%s the answer goes to port %d and the host spoke from %d"
           % (tag, dport, PEER_PORT), fails)
    expect(ulen == 8 + len(want_payload),
           "%s the answer's UDP length is %d and 8 + %d is %d"
           % (tag, ulen, len(want_payload), 8 + len(want_payload)), fails)
    got = blob[42:]
    expect(got == want_payload,
           "%s the answer's payload is not what the board printed\n%s"
           % (tag, hexdiff(got, want_payload)), fails)


def check(res, at, console: bytes, fails: list[str], mutated: str) -> None:
    """`mutated` names the negative control the image was built from:
    "" for the real library, "rearm", "drain" or "tcp"."""
    def R(name):
        return res[at[name]]

    # ---- A ----------------------------------------------------------
    expect(R("addr_a").r == 1 and R("addr_a").e1 == 1,
           "A. the fixture could not configure the IP layer, so nothing "
           "below proves anything (net error %d)" % R("addr_a").e2, fails)
    expect(R("deaf_down").r == 0,
           "A. THE CONSOLE ARMED ON A LINK THAT CANNOT CARRY A FRAME. The "
           "IP layer holds the wired address and the cable is not in. A "
           "board that announces a console it cannot answer on is the "
           "whole defect this gate exists for", fails)
    expect(R("direct_down").r == 0,
           "A. NetConsoleStart armed a kind that is not ready when asked "
           "for it by name", fails)

    # ---- B ----------------------------------------------------------
    armed = R("armed_wired").r
    if mutated == "rearm":
        expect(armed == 0,
               "NEGATIVE CONTROL: the console armed anyway with the fix "
               "reverted. The mutation did not reach the code under test, "
               "so the positive run is not evidence", fails)
        return
    if mutated == "drain":
        # ONE FRAME PER CALL. Nothing else in the library moves, so the
        # console still arms and still answers - which is exactly how a
        # one-frame pump lives beside a green gate. What must go wrong is
        # L0's count and L0's ring.
        expect(armed == 1,
               "NEGATIVE CONTROL: reverting the DRAIN also stopped the "
               "console arming, so the mutation is too broad to prove "
               "anything about section L0", fails)
        expect(R("queued_d").r == 3,
               "NEGATIVE CONTROL: the fixture held %d of 3 staged frames "
               "before the pump, so the control grades nothing"
               % R("queued_d").r, fails)
        expect(R("drained_d").r == 2,
               "NEGATIVE CONTROL: one turn of the one-frame-per-call pump "
               "left %d of 3 frames on the wire and it must leave 2. The "
               "mutation did not reach netcon_PumpOne, so section L0 "
               "passing on the real library is not evidence"
               % R("drained_d").r, fails)
        expect(R("ring_d").blob == TYPED,
               "NEGATIVE CONTROL: the one-frame pump put %r in the "
               "keystroke ring and it should have put only the first "
               "datagram there" % R("ring_d").blob, fails)
        return
    if mutated == "tcp":
        # NetServiceInput WITH NO TCP ARM. Nothing else moves, so the
        # console arms, the drain still empties the ring and the console's
        # datagram still arrives. What must go wrong is T: the transport
        # is never entered and the segment vanishes.
        expect(armed == 1,
               "NEGATIVE CONTROL: removing the TCP arm also stopped the "
               "console arming, so the mutation is too broad to prove "
               "anything about section T", fails)
        expect(R("drained_d").r == 0,
               "NEGATIVE CONTROL: removing the TCP arm left %d of 3 frames "
               "on the wire in section L0, so the mutation reached the "
               "drain as well" % R("drained_d").r, fails)
        expect(R("fed_t").r == 0,
               "NEGATIVE CONTROL: TcpInput was still entered %d times with "
               "the dispatch arm removed. The mutation did not reach "
               "NetServiceInput, so section T passing on the real library "
               "is not evidence" % R("fed_t").r, fails)
        expect(R("left_t").r == 0,
               "NEGATIVE CONTROL: the segment was not taken off the wire "
               "(%d still queued), so the control is not the silent drop "
               "it models" % R("left_t").r, fails)
        expect(R("ring_t2").blob == TYPED2,
               "NEGATIVE CONTROL: the console's datagram stopped reaching "
               "the ring too, so the mutation is broader than the one arm "
               "under test", fails)
        return
    if mutated:
        raise SystemExit("a64_wificon_check: no grading for the negative "
                         "control %r" % mutated)

    expect(armed == 1,
           "B. A BOARD ON A CABLE STILL HAS NO CONSOLE. The IP layer is "
           "configured for the wired interface, the cable is in, and one "
           "spin of the prompt left the console DEAF. This is the bench on "
           "2026-09-07: a board wired straight to the machine trying to "
           "reach it, with no way in at all", fails)
    expect(R("armed_wired").e1 == LINK_WIRED,
           "B. the console armed on kind %d and the address belongs to the "
           "wired interface (kind %d)"
           % (R("armed_wired").e1, LINK_WIRED), fails)
    expect(R("armed_wired").e2 & 0xFFFFFFFF == WIRED_IP,
           "B. the console armed at %08x and the address is %08x"
           % (R("armed_wired").e2 & 0xFFFFFFFF, WIRED_IP), fails)

    # ---- I ----------------------------------------------------------
    expect(R("told_board").r >= 1 and R("told_board").e1 == LINK_WIRED
           and R("told_board").e2 == 1,
           "I. the board was told (%d calls) that the console armed on "
           "kind %d, on=%d, and it armed on the wired link. A radio whose "
           "own receive pump reads that answer would either eat the "
           "console's keystrokes or stop servicing rekeys"
           % (R("told_board").r, R("told_board").e1, R("told_board").e2),
           fails)

    # ---- C ----------------------------------------------------------
    expect(R("ring_wired").blob == TYPED,
           "C. the datagram's payload did not arrive in the keystroke "
           "ring\n%s" % hexdiff(R("ring_wired").blob, TYPED), fails)
    expect(R("peer_wired").e1 & 0xFFFFFFFF == WIRED_PEER
           and R("peer_wired").e2 == PEER_PORT,
           "C. the board learned peer %08x:%d and the host is %08x:%d"
           % (R("peer_wired").e1 & 0xFFFFFFFF, R("peer_wired").e2,
              WIRED_PEER, PEER_PORT), fails)
    expect(R("wire_wired").e2 == LINK_WIRED,
           "C. the answer left through kind %d and the console is on the "
           "wired link (kind %d) - a reply out of the wrong interface is a "
           "reply nobody receives" % (R("wire_wired").e2, LINK_WIRED),
           fails)
    grade_answer("C.", R("wire_wired").blob, WIRED_MAC, WIRED_IP,
                 WIRED_PEER, ANSWERED, fails)

    # ---- H. THE PUMP READS EVERY ADDRESSED INTERFACE ----------------
    #  WHAT THIS CASE USED TO SAY, AND WHY IT SAID IT. Until 2026-09-07
    #  it required a frame queued on the OTHER interface to be left
    #  UNTOUCHED by a console armed on the cable - because the console
    #  was on exactly one link, so a frame on the other one belonged to
    #  the link layer's own pump and swallowing it dropped somebody
    #  else's traffic. That was correct for a console that could only be
    #  in one place.
    #
    #  IT IS NOW THE OPPOSITE, and the reversal is the feature. The
    #  console listens on every interface that holds an address, so a
    #  datagram on the radio IS its business, and a pump that left it
    #  sitting there would be a console on one link wearing the paint of
    #  a console on two.
    expect(R("ring_busy").r == 0,
           "H. a second host's datagram reached the keystroke ring while the "
           "host on the cable owned the session (%d bytes). One command line "
           "has one owner; a second host is answered BUSY and its bytes are "
           "discarded, never queued" % R("ring_busy").r, fails)
    busy = R("wire_busy").blob
    expect(R("wire_busy").e2 == LINK_WIFI
           and len(busy) >= 48 and busy[42:48] == b"BUSY\r\n"
           and int.from_bytes(busy[38:40], "big") == 14
           and busy[0:6] == PEER_MAC,
           "H. the second host was not answered BUSY on the radio it spoke "
           "on (kind %d, payload %r). A host that is refused and told "
           "nothing retries into silence"
           % (R("wire_busy").e2, busy[42:48]), fails)
    expect(R("done_h").r == 0,
           "H. the session was still owned after the command completed", fails)
    expect(R("still_there").r == 0,
           "H. a console datagram on the OTHER addressed interface was "
           "left unconsumed by the pump. The console listens on every "
           "interface that holds an address; an interface it does not "
           "read is an interface it cannot be reached on", fails)
    expect(R("ring_other").blob == TYPED3,
           "H. the datagram that arrived on the second interface did not "
           "reach the keystroke ring\n%s"
           % hexdiff(R("ring_other").blob, TYPED3), fails)

    # ---- F ----------------------------------------------------------
    for i in range(10):
        expect(R("spin%d" % i).r == 1,
               "F. prompt spin %d turned the console off again" % i, fails)
    expect(R("arms_f").r == 1,
           "F. the console has armed %d times and it has been up "
           "continuously since one arming" % R("arms_f").r, fails)
    seen = console.count(LISTENING)
    expect(seen >= 1,
           "F. the listening line was never printed, so nothing announced "
           "where the board can be reached", fails)

    # ---- G ----------------------------------------------------------
    expect(R("steal").r == 1,
           "G. the fixture could not bind port 53, so the case below "
           "proves nothing", fails)
    expect(R("ring_g").blob == TYPED2,
           "G. after a command bound a port of its own, the console's next "
           "datagram was not delivered - which is the console going "
           "permanently deaf after the first ping\n%s"
           % hexdiff(R("ring_g").blob, TYPED2), fails)

    # ---- E. THE RADIO JOINS AND TAKES NOTHING FROM THE CABLE --------
    #  MEASURED ON SILICON 2026-09-07: the access point idled the board
    #  out, the radio re-associated and re-leased, that lease became the
    #  board's ONE address, the console re-armed onto the radio, and the
    #  laptop on the cable lost the board mid-session with no cable
    #  touched and nothing typed.
    expect(R("radio_lease").r == 1 and R("radio_lease").e1 == 2,
           "E. the radio's lease was not recorded as a SECOND interface "
           "(NetIfCount answered %d). If binding an address on one link "
           "does not leave the other's record standing, there is nothing "
           "below this worth measuring" % R("radio_lease").e1, fails)
    expect(R("wired_still").e1 & 0xFFFFFFFF == WIRED_IP,
           "E. THE RADIO'S LEASE TOOK THE CABLE'S ADDRESS. The wired "
           "interface holds %08x and it was given %08x. This is the "
           "2026-09-07 defect exactly, and from the bench it looks like "
           "the board vanishing in the middle of a session"
           % (R("wired_still").e1 & 0xFFFFFFFF, WIRED_IP), fails)
    expect(R("wired_still").e2 == ADDR_SAVED,
           "E. the cable's record lost the source of its address when the "
           "radio bound its lease", fails)
    expect(R("radio_rec").e1 & 0xFFFFFFFF == RADIO_IP,
           "E. the radio does not hold its own lease (%08x, want %08x)"
           % (R("radio_rec").e1 & 0xFFFFFFFF, RADIO_IP), fails)
    expect(R("spin_both").r == 1
           and R("spin_both").e1 == LINK_WIRED
           and R("spin_both").e2 & 0xFFFFFFFF == WIRED_IP,
           "E. the radio joining moved the console's announced interface "
           "off the cable (kind %d at %08x). The wire is preferred "
           "whenever the cable is up, and a second link coming up adds an "
           "interface - it does not move the board"
           % (R("spin_both").e1, R("spin_both").e2 & 0xFFFFFFFF), fails)
    expect(R("peer_kept").e1 & 0xFFFFFFFF == WIRED_PEER,
           "E. THE PEER ON THE CABLE WAS FORGOTTEN when the radio joined "
           "(peer is now %08x). Nothing about that peer changed: it is "
           "still on the cable, the cable still holds its address, and on "
           "2026-09-07 that peer was a laptop in the middle of a transfer"
           % (R("peer_kept").e1 & 0xFFFFFFFF), fails)
    expect(R("arms_e").r == 1,
           "E. the console has armed %d times. A second interface coming "
           "up must not re-arm it: an arming forgets the peer and reprints "
           "the announcement, and neither is true of a board that has not "
           "moved" % R("arms_e").r, fails)

    # ---- D. AND IT ANSWERS ON THE RADIO AT THE SAME TIME ------------
    expect(R("ring_radio").blob == TYPED,
           "D. over the radio, the datagram's payload did not arrive in "
           "the keystroke ring - so the second interface is addressed and "
           "deaf\n%s" % hexdiff(R("ring_radio").blob, TYPED), fails)
    expect(R("peer_radio").e1 == LINK_WIFI
           and R("peer_radio").e2 & 0xFFFFFFFF == RADIO_IP,
           "D. the board recorded the peer as being on kind %d at address "
           "%08x, and it spoke to the radio's %08x. The reply leaves by "
           "the interface the request arrived on, sourced from the address "
           "it was addressed to, or it does not arrive"
           % (R("peer_radio").e1, R("peer_radio").e2 & 0xFFFFFFFF,
              RADIO_IP), fails)
    expect(R("wire_radio").e2 == LINK_WIFI,
           "D. the answer left through kind %d and the peer is on the "
           "radio (kind %d)" % (R("wire_radio").e2, LINK_WIFI), fails)
    grade_answer("D.", R("wire_radio").blob, RADIO_MAC, RADIO_IP,
                 RADIO_PEER, ANSWERED2, fails)

    # ---- J. AND STRAIGHT BACK OUT OF THE CABLE, SAME BOOT -----------
    #  No prompt spin in between, no re-arming, no reconfiguration: the
    #  previous datagram came in on the radio and was answered there, and
    #  this one comes in on the cable and must be answered there. A
    #  console that can only answer whichever link spoke last is a
    #  console on one link with extra steps.
    expect(R("ring_wired2").blob == TYPED3,
           "J. after answering on the radio, a datagram on the CABLE did "
           "not reach the keystroke ring\n%s"
           % hexdiff(R("ring_wired2").blob, TYPED3), fails)
    expect(R("peer_wired2").e1 == LINK_WIRED
           and R("peer_wired2").e2 & 0xFFFFFFFF == WIRED_IP,
           "J. the board recorded the peer as kind %d at %08x and it spoke "
           "to the cable's %08x"
           % (R("peer_wired2").e1, R("peer_wired2").e2 & 0xFFFFFFFF,
              WIRED_IP), fails)
    expect(R("wire_wired2").e2 == LINK_WIRED,
           "J. the answer left through kind %d and the peer is on the "
           "cable (kind %d) - both links were addressed and the board "
           "answered out of the wrong one"
           % (R("wire_wired2").e2, LINK_WIRED), fails)
    grade_answer("J.", R("wire_wired2").blob, WIRED_MAC, WIRED_IP,
                 WIRED_PEER, ANSWERED, fails)

    # ---- K. THE BOARD AS THE DHCP SERVER ON A BARE CABLE ------------
    expect(R("serve_k").e1 == 1 and R("serve_k").e2 & 0xFFFFFFFF == DHCPD_SELF,
           "K. the board did not take the DHCP server role on a cable "
           "where nothing answered its discovers (on=%d, alias=%08x). "
           "Without it a laptop set to DHCP at the other end gets nothing "
           "from this board at all"
           % (R("serve_k").e1, R("serve_k").e2 & 0xFFFFFFFF), fails)
    expect(R("arm_k").r == 1 and R("arm_k").e2 & 0xFFFFFFFF == WIRED_LL,
           "K. the console did not arm on the link-local address the "
           "board gave itself (on=%d at %08x). The served address is a "
           "SECOND address on the same interface; the link-local one is "
           "still the one a peer that is not a DHCP client reaches"
           % (R("arm_k").r, R("arm_k").e2 & 0xFFFFFFFF), fails)
    expect(R("ring_k").r == 0,
           "K. %d bytes of a DHCP client's DISCOVER were fed into the "
           "keystroke ring as if somebody had typed them. Port 67 is the "
           "server's and not the console's" % R("ring_k").r, fails)
    grade_offer(R("wire_offer").blob, fails)
    expect(R("wire_offer").e2 == LINK_WIRED,
           "K. the OFFER left through kind %d and the DISCOVER arrived on "
           "the cable (kind %d)" % (R("wire_offer").e2, LINK_WIRED), fails)
    expect(R("counts_k").r == 1 and R("counts_k").e1 == 1,
           "K. the server reports on=%d and %d offers sent after answering "
           "one DISCOVER" % (R("counts_k").r, R("counts_k").e1), fails)

    expect(R("stood_down").r == 0,
           "K. a client accepting ANOTHER server's offer on this cable did "
           "not end this board's server role. That REQUEST is the only "
           "proof of a rival a server on port 67 can receive - the rival's "
           "OFFER goes to the client's port and never arrives here - and "
           "standing down on it is what makes the feature safe to leave "
           "switched on: carry the board to an office network and it "
           "becomes a client again by itself", fails)
    expect(R("alias_gone").e1 & 0xFFFFFFFF == WIRED_LL,
           "K. standing down as the server took the interface's own "
           "link-local address with it (%08x). The board must still be "
           "reachable where it was"
           % (R("alias_gone").e1 & 0xFFFFFFFF), fails)

    # ---- L0. THE DRAIN ----------------------------------------------
    #  The fixture must have held all three, or the rest of this section
    #  grades nothing. Checked first and separately so that a fixture
    #  regression cannot be read as a library regression.
    staged = [R("rx_d%d" % i).r for i in range(3)]
    expect(R("queued_d").r == 3 and all(n > 0 for n in staged),
           "L0. the fixture holds %d of the 3 frames that were staged "
           "(staging answered %r), so this section is not testing what it "
           "says it is - the queue in the harness is broken, not the console"
           % (R("queued_d").r, staged), fails)
    expect(R("arm_d").r == 1 and R("arm_d").e1 == LINK_WIFI,
           "L0. the console did not arm on the radio (on=%d, kind %d), so "
           "no pump below reads anything" % (R("arm_d").r, R("arm_d").e1),
           fails)
    #  THE DEFECT ITSELF.
    expect(R("drained_d").r == 0,
           "L0. one turn of the pump left %d of 3 frames on the wire. A "
           "pump that takes one frame per call caps this board's whole "
           "receive rate at one frame per turn of the prompt, and on a "
           "segment with any traffic on it the datagram that was actually "
           "sent queues behind the chatter and is gone before the pump "
           "reaches it. netcon_PumpOne drains to #LINK_RX_BUDGET"
           % R("drained_d").r, fails)
    #  ORDER AND IDENTITY, which the count alone cannot show.
    want_d = TYPED + TYPED2 + TYPED3
    expect(R("ring_d").blob == want_d,
           "L0. the three queued datagrams did not all reach the keystroke "
           "ring in the order they arrived\n%s"
           % hexdiff(R("ring_d").blob, want_d), fails)
    #  AND THE BOARD'S OWN COUNTERS AGREE WITH THE FIXTURE. `net link`
    #  prints these, so a bench with no gate reads the same fact.
    took = R("drained_d").e1 - R("queued_d").e1
    expect(took >= 3,
           "L0. the console's drain counter moved by %d over one pump and "
           "the fixture handed it 3 frames. `net link` prints that counter; "
           "one that disagrees with the wire is worse than none" % took,
           fails)
    expect(R("drained_d").e2 == 0,
           "L0. the drain reports %d budget-limited passes, over traffic of "
           "a few frames at a time. That counter stays 0 until the budget "
           "really is the ceiling" % R("drained_d").e2, fails)

    # ---- T. THE PUMP HANDS A TCP SEGMENT TO TCP ----------------------
    #  The fixture's own preconditions first.
    expect(R("before_t").r == 0,
           "T. TcpInput had already been entered %d times before a segment "
           "was staged, so this section is grading leftovers"
           % R("before_t").r, fails)
    expect(R("pin_t").r == LINK_WIRED,
           "T. the pin did not take: outbound traffic is on kind %d and the "
           "section needs the cable (kind %d), so that the segment arrives "
           "on the link the link's own pump is NOT reading"
           % (R("pin_t").r, LINK_WIRED), fails)
    expect(R("arm_t").r == 1 and R("rx_seg_t").r > 0,
           "T. the console did not arm (on=%d) or the segment was not "
           "staged (%d), so the pump below reads nothing"
           % (R("arm_t").r, R("rx_seg_t").r), fails)
    expect(R("left_t").r == 0,
           "T. the pump left %d frames on the wire; the segment was never "
           "taken, so nothing below grades the dispatch" % R("left_t").r,
           fails)
    #  THE DISPATCH ITSELF.
    expect(R("fed_t").r == 1,
           "T. a verified TCP segment arrived on the radio, the console's "
           "pump took it off the wire, and TcpInput was entered %d times. "
           "The link's own pump reads the SELECTED link, which is the cable "
           "here, so nothing else could have seen this segment: a pump that "
           "does not hand it to TCP drops it with no counter and no trace"
           % R("fed_t").r, fails)
    expect(R("fed_t").e1 == LINK_WIFI,
           "T. TcpInput was entered with NetRxKind() = %d and the segment "
           "arrived on the radio (kind %d). A transport told the wrong "
           "receive interface answers out of the wrong one"
           % (R("fed_t").e1, LINK_WIFI), fails)
    expect(R("ring_t").r == 0,
           "T. %d bytes of a TCP segment were fed into the KEYSTROKE ring "
           "as if they had been typed" % R("ring_t").r, fails)
    #  THE CONSOLE STILL WORKS ON THE SAME WIRE.
    expect(R("ring_t2").blob == TYPED2,
           "T. the console's own datagram no longer reaches the keystroke "
           "ring on a link that has just carried a TCP segment\n%s"
           % hexdiff(R("ring_t2").blob, TYPED2), fails)
    expect(R("fed_t2").r == 1,
           "T. TcpInput has now been entered %d times, and the only frame "
           "since the segment was a console datagram" % R("fed_t2").r,
           fails)


def grade_offer(blob: bytes, fails: list[str]) -> None:
    """The DHCPOFFER this board put on the wire, field by field, read
    against RFC 2131 rather than against the library that built it."""
    if len(blob) < 14 + 20 + 8 + 240:
        fails.append("K. the OFFER on the wire is %d bytes, which is "
                     "shorter than a BOOTP message" % len(blob))
        return
    expect(blob[0:6] == BCAST_MAC,
           "K. the OFFER is not broadcast (%s). The client does not have "
           "the offered address yet, so a unicast reply is a frame "
           "addressed to an address nobody holds" % blob[0:6].hex(), fails)
    ip = blob[14:34]
    src = int.from_bytes(ip[12:16], "big")
    expect(src == DHCPD_SELF,
           "K. the OFFER is sourced from %08x and the server identifier "
           "inside it is %08x. A reply whose source does not match the "
           "server identifier is one every client throws away - and this "
           "interface holds two addresses, so nothing in a broadcast "
           "destination can pick between them" % (src, DHCPD_SELF), fails)
    expect(ones_complement(ip[:20]) == 0,
           "K. the OFFER's IPv4 header checksum does not verify", fails)
    u = blob[34:42]
    expect(int.from_bytes(u[0:2], "big") == 67
           and int.from_bytes(u[2:4], "big") == 68,
           "K. the OFFER goes from port %d to port %d, and RFC 2131 says "
           "67 to 68" % (int.from_bytes(u[0:2], "big"),
                         int.from_bytes(u[2:4], "big")), fails)
    m = blob[42:]
    expect(m[0] == 2, "K. the OFFER is not a BOOTREPLY (op=%d)" % m[0], fails)
    expect(m[28:34] == CLIENT_MAC,
           "K. the OFFER does not carry the client's own hardware address "
           "back (%s)" % m[28:34].hex(), fails)
    expect(m[4:8] == (0x5A5A0001).to_bytes(4, "big"),
           "K. the OFFER does not echo the client's transaction id (%s). A "
           "client matches the reply to its request on the xid and drops "
           "anything else" % m[4:8].hex(), fails)
    yi = int.from_bytes(m[16:20], "big")
    expect(DHCPD_POOL_LO <= yi <= DHCPD_POOL_HI,
           "K. the OFFER hands out %08x, which is outside the pool "
           "%08x .. %08x" % (yi, DHCPD_POOL_LO, DHCPD_POOL_HI), fails)
    expect(m[236:240] == (0x63825363).to_bytes(4, "big"),
           "K. the OFFER has no magic cookie", fails)
    opts = {}
    i = 240
    while i < len(m) and m[i] != 255:
        if m[i] == 0:
            i += 1
            continue
        if i + 1 >= len(m):
            break
        ln = m[i + 1]
        opts[m[i]] = m[i + 2:i + 2 + ln]
        i += 2 + ln
    expect(opts.get(53) == b"\x02",
           "K. the reply to a DISCOVER is not a DHCPOFFER (option 53 = %r)"
           % opts.get(53), fails)
    expect(opts.get(54) == DHCPD_SELF.to_bytes(4, "big"),
           "K. the OFFER carries no server identifier, or the wrong one "
           "(option 54 = %r)" % opts.get(54), fails)
    expect(opts.get(1) == b"\xff\xff\xff\x00",
           "K. the OFFER carries no 255.255.255.0 netmask (option 1 = %r)"
           % opts.get(1), fails)
    expect(opts.get(51) == (3600).to_bytes(4, "big"),
           "K. the OFFER's lease is not one hour (option 51 = %r)"
           % opts.get(51), fails)
    expect(3 not in opts,
           "K. the OFFER carries a router option (%r). This board does not "
           "forward packets, so it is not a router: advertising itself as one "
           "installs a default route to a machine that drops everything sent "
           "through it (Anvil/Core/dhcpd.pbi, NO ROUTER OPTION IS SENT)"
           % opts.get(3), fails)
    expect(6 not in opts,
           "K. the OFFER carries a DNS server option. This board is not a "
           "resolver and has no upstream to name; offering itself would "
           "make every name lookup on the client time out", fails)


def rb_lines(data: bytes) -> bytes:
    """The payload as the monitor must write it, from RFC 4648 via
    Python's base64 and never from the library under test."""
    out = b""
    for i in range(0, len(data), RB_LINE):
        out += base64.b64encode(data[i:i + RB_LINE]) + b"\r\n"
    return out


def rb_frames(blob: bytes, count: int, tag: str,
              fails: list[str]) -> list[tuple[int, bytes, bytes]]:
    """Split the fixture's wire log into (kind, frame, udp payload)."""
    frames = []
    i = 0
    while i + 3 <= len(blob):
        kind = blob[i]
        n = (blob[i + 1] << 8) | blob[i + 2]
        frame = blob[i + 3:i + 3 + n]
        i += 3 + n
        payload = b""
        if len(frame) >= 42:
            ulen = int.from_bytes(frame[38:40], "big")
            payload = frame[42:42 + max(0, ulen - 8)]
        frames.append((kind, frame, payload))
    if len(frames) != count:
        fails.append("%s the fixture counted %d frames and its log holds %d, "
                     "so the log ran out of room and nothing below can be "
                     "trusted" % (tag, count, len(frames)))
    return frames


def check_readback(res, at, console: bytes, fails: list[str]) -> None:
    def R(name):
        return res[at[name]]

    data = RB_PATTERNS[RB_ADDR_NET][:RB_NET_BYTES]
    crc = zlib.crc32(data) & 0xFFFFFFFF
    header = b"readback %08X %d bytes base64\r\n" % (RB_ADDR_NET, RB_NET_BYTES)
    verdict = b"readback end %d bytes crc32 %08X\r\n" % (RB_NET_BYTES, crc)
    blocks = [rb_lines(data[k:k + RB_BLOCK])
              for k in range(0, len(data), RB_BLOCK)]
    want = [header] + blocks + [verdict]

    # ---- L1. the wire, datagram by datagram -------------------------
    wire = R("wire_l")
    frames = rb_frames(wire.blob, wire.r, "L1.", fails)
    got = [f[2] for f in frames]
    if got != want:
        lines = ["L1. THE READBACK ON THE WIRE IS NOT ONE HEADER, %d PAYLOAD "
                 "DATAGRAMS AND ONE VERDICT. It sent %d datagrams for a "
                 "%d-byte range; the stream must be 15 base64 lines to a "
                 "datagram, so %d bytes is exactly %d of them. A datagram "
                 "per line is the hex dump's shape and it is what a payload "
                 "sent through the serial path looks like."
                 % (len(blocks), len(got), RB_NET_BYTES, RB_NET_BYTES,
                    len(blocks))]
        for idx in range(max(len(got), len(want))):
            g = got[idx] if idx < len(got) else None
            w = want[idx] if idx < len(want) else None
            if g != w:
                lines.append("      first difference at datagram %d:\n"
                             "        got  %r\n        want %r"
                             % (idx, (g or b"")[:90], (w or b"")[:90]))
                break
        fails.append("\n".join(lines))

    # ---- L2. and NOT ONE BYTE of the payload through the PL011 ------
    expect(header + verdict in console,
           "L2. THE PAYLOAD WENT THROUGH THE SERIAL PORT. On the PL011 the "
           "network readback's header must be followed IMMEDIATELY by its "
           "verdict line, with no base64 between them. Every byte a network "
           "readback puts through UartWrite is a byte shifted out at "
           "115200 baud before the network sees it - which is exactly the "
           "1,730 bytes a second measured on 2026-09-16", fails)
    expect(blocks[0].split(b"\r\n")[0] not in console,
           "L2. the first base64 line of the network readback is on the "
           "serial capture", fails)

    # ---- L3. every frame back to the peer, out of the cable ---------
    for idx, (kind, frame, payload) in enumerate(frames):
        if kind != LINK_WIRED:
            fails.append("L3. datagram %d of the readback left through kind "
                         "%d and the peer is on the cable (kind %d)"
                         % (idx, kind, LINK_WIRED))
            break
        if len(frame) < 42:
            fails.append("L3. datagram %d is %d bytes, shorter than a UDP "
                         "header" % (idx, len(frame)))
            break
        if len(frame) != 14 + 20 + 8 + len(payload) and len(frame) != 60:
            fails.append("L3. datagram %d is %d bytes and carries %d bytes "
                         "of payload" % (idx, len(frame), len(payload)))
            break
        grade_answer("L3. datagram %d:" % idx, frame[:42 + len(payload)],
                     WIRED_MAC, WIRED_IP, WIRED_PEER, payload, fails)

    # ---- L4. the counts the command itself keeps ---------------------
    run = R("run_l")
    expect(run.r == RB_NET_BYTES and run.e1 == len(blocks) and run.e2 == 0,
           "L4. ReadbackRun answered %d bytes sent, %d blocks, %d refused; "
           "the range is %d bytes, %d blocks, and the fixture refuses "
           "nothing" % (run.r, run.e1, run.e2, RB_NET_BYTES, len(blocks)),
           fails)

    # ---- L5. typed on the LOCAL console ------------------------------
    local = RB_PATTERNS[RB_ADDR_LOCAL][:RB_LOCAL_BYTES]
    local_stream = (b"readback %08X %d bytes base64\r\n"
                    % (RB_ADDR_LOCAL, RB_LOCAL_BYTES)
                    + rb_lines(local)
                    + b"readback end %d bytes crc32 %08X\r\n"
                    % (RB_LOCAL_BYTES, zlib.crc32(local) & 0xFFFFFFFF))
    expect(local_stream in console,
           "L5. a readback typed on the local console did not put its whole "
           "stream - header, every base64 line including the two-'=' last "
           "one, and the verdict - on the serial port. That console asked "
           "for it and the serial port is where its answer goes", fails)
    expect(R("wire_l_local").r == 0,
           "L5. a readback typed on the LOCAL console put %d frames on the "
           "wire. No network peer asked for those bytes"
           % R("wire_l_local").r, fails)
    expect(R("run_l_local").r == RB_LOCAL_BYTES,
           "L5. the local readback sent %d of %d bytes"
           % (R("run_l_local").r, RB_LOCAL_BYTES), fails)

    # ---- L6. stopped before the third block --------------------------
    part = RB_PATTERNS[RB_ADDR_STOP][:2 * RB_BLOCK]
    stop_want = [
        b"readback %08X %d bytes base64\r\n" % (RB_ADDR_STOP, RB_NET_BYTES),
        rb_lines(part[:RB_BLOCK]),
        rb_lines(part[RB_BLOCK:]),
        b"readback stopped after %d of %d bytes crc32 %08X\r\n"
        % (len(part), RB_NET_BYTES, zlib.crc32(part) & 0xFFFFFFFF),
    ]
    stop = R("wire_l_stop")
    sframes = rb_frames(stop.blob, stop.r, "L6.", fails)
    sgot = [f[2] for f in sframes]
    expect(sgot[:len(stop_want)] == stop_want,
           "L6. a readback stopped before its third block did not send the "
           "header, exactly two payload datagrams, and a STOPPED line with "
           "the count and crc32 of the %d bytes that really went. A stopped "
           "stream that said `end`, or a checksum of the whole range, is a "
           "partial read a host would accept as whole\n      got  %r"
           % (len(part), [x[:60] for x in sgot[:5]]), fails)
    expect(not any(x.startswith(b"readback end") for x in sgot),
           "L6. the stopped readback also printed an `end` line", fails)
    expect(R("run_l_stop").r == len(part),
           "L6. the stopped readback reports %d bytes sent and %d went"
           % (R("run_l_stop").r, len(part)), fails)

    # ---- L7. the checksum, against zlib ------------------------------
    wrong = [v for v in range(256)
             if (R("crc1_%d" % v).r & 0xFFFFFFFF)
             != zlib.crc32(bytes([v]))]
    expect(not wrong,
           "L7. THE CRC-32 TABLE IS WRONG at %d of 256 entries - the "
           "one-byte checksum of %s disagrees with zlib.crc32. Every "
           "transfer this board verifies, and its radio firmware check at "
           "boot, rest on that table" % (len(wrong), ", ".join(
               "%02X" % v for v in wrong[:8])), fails)
    for n in CRC_LENGTHS:
        got = R("crcn_%d" % n).r & 0xFFFFFFFF
        want = zlib.crc32(bytes(range(n)))
        expect(got == want,
               "L7. crc32 of the first %d byte values is %08X and zlib says "
               "%08X" % (n, got, want), fails)
    p1 = R("crc_part1").r & 0xFFFFFFFF
    expect(p1 == CRC_PART1_PLACEHOLDER,
           "L7. the running accumulator after %d bytes is %08X and it must "
           "be %08X - the value the crc32 command feeds into its next chunk"
           % (CRC_SPLIT, p1, CRC_PART1_PLACEHOLDER), fails)
    fin = (R("crc_part2").r ^ 0xFFFFFFFF) & 0xFFFFFFFF
    expect(fin == zlib.crc32(bytes(range(256))),
           "L7. a checksum fed in two parts finishes as %08X and fed whole "
           "it is %08X, so a chunked crc32 would disagree with an unchunked "
           "one" % (fin, zlib.crc32(bytes(range(256)))), fails)


# =====================================================================
#  THE NEGATIVE CONTROLS
# =====================================================================
#  THE SHIPPED SHAPE, for the readback: every console byte went through
#  UartWrite. Taking the peer branch out of ConsoleWriteBulk puts the
#  payload back on that path while leaving the command, the encoder and
#  the checksum exactly as they are, so what goes red is the routing and
#  nothing else.
RB_PEER_BRANCH = """  If toPeer <> 0
    ProcedureReturn NetConsoleWriteBulk(*p, n)
  EndIf
"""


def write_rb_mutant(dest: pathlib.Path) -> None:
    src = ROOT / "Anvil" / "Core" / "readback.pbi"
    text = src.read_text(encoding="utf-8", errors="ignore")
    if text.count(RB_PEER_BRANCH) != 1:
        raise SystemExit(
            "a64_wificon_check: ConsoleWriteBulk in Anvil/Core/readback.pbi "
            "no longer has the peer branch this negative control removes, so "
            "the control cannot be built. Update the mutation with the file.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text.replace(RB_PEER_BRANCH, ""), encoding="utf-8")


PRE_FIX_REARM = """Procedure NetConsoleRearm()
  If gConOn = 0
    ProcedureReturn
  EndIf
  NetUdpBind(#HW_LINK_NONE, #NETCON_PORT)
EndProcedure"""


def write_mutant(dest: pathlib.Path) -> None:
    """A copy of netconsole.pi4 with the re-derivation taken back out.

    The mutation is the PRE-FIX shape: put the bound port back, arm
    nothing.  Everything else in the file is left exactly as it is, so
    what goes red below is the one behaviour this gate names and not a
    library that stopped compiling.
    """
    text = LIB.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"(?ms)^Procedure NetConsoleRearm\(\).*?^EndProcedure",
                  text)
    if not m:
        raise SystemExit(
            "a64_wificon_check: NetConsoleRearm is no longer a procedure in "
            "Anvil/Core/netconsole.pbi, so the negative control cannot be "
            "built. A gate whose mutation silently does nothing is worse "
            "than no gate.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text[:m.start()] + PRE_FIX_REARM + text[m.end():],
                    encoding="utf-8")


def write_drain_mutant(dest: pathlib.Path) -> None:
    """A copy of netconsole.pbi whose netcon_PumpOne takes ONE frame a call.

    The mutation is one line: a `Break` immediately before the drain
    loop's `Wend`, after the last statement of the body, so it is reached
    on every iteration.  Nothing else in the file moves, so the console
    still arms, still answers and still passes every other section - and
    section L0 is the only thing that can say the drain has gone.
    """
    text = LIB.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"(?ms)^Procedure netcon_PumpOne\(kind\.i\).*?^EndProcedure",
                  text)
    if not m:
        raise SystemExit(
            "a64_wificon_check: netcon_PumpOne is no longer a procedure in "
            "Anvil/Core/netconsole.pbi, so the drain's negative control "
            "cannot be built.")
    body = m.group(0)
    nl = "\r\n" if "\r\n" in body else "\n"
    if body.count("  Wend" + nl) != 1:
        raise SystemExit(
            "a64_wificon_check: netcon_PumpOne no longer contains exactly "
            "one drain loop for this negative control to revert. Either the "
            "drain has gone - in which case section L0 is about to go red "
            "anyway - or it has been rewritten and this mutation must be "
            "rewritten with it. A mutation that silently does nothing is "
            "worse than no gate.")
    mutated = body.replace("  Wend" + nl, "  Break" + nl + "  Wend" + nl, 1)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text[:m.start()] + mutated + text[m.end():],
                    encoding="utf-8")


def write_tcp_mutant(dest: pathlib.Path) -> None:
    """A copy of netconsole.pbi whose NetServiceInput has no TCP arm.

    The whole `If rc = #NET_IN_TCP ... EndIf` block is removed rather than
    its body emptied, so the verified segment falls through to the UDP
    test and the dispatcher returns 0 with nothing entered - the silent
    drop section T exists to catch.  The drain, the arming and the UDP
    path are untouched.
    """
    text = LIB.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"(?ms)^Procedure\.i NetServiceInput\(.*?^EndProcedure",
                  text)
    if not m:
        raise SystemExit(
            "a64_wificon_check: NetServiceInput is no longer a procedure in "
            "Anvil/Core/netconsole.pbi, so the TCP arm's negative control "
            "cannot be built.")
    body = m.group(0)
    arms = list(re.finditer(r"(?m)^  If rc = #NET_IN_TCP\r?\n.*?^  EndIf\r?\n",
                            body, re.S))
    if len(arms) != 1:
        raise SystemExit(
            "a64_wificon_check: NetServiceInput no longer contains exactly "
            "one `If rc = #NET_IN_TCP` arm for this negative control to "
            "remove. Either the dispatch has gone - in which case section T "
            "is about to go red anyway - or it has been rewritten and this "
            "mutation must be rewritten with it.")
    arm = arms[0]
    mutated = body[:arm.start()] + body[arm.end():]
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text[:m.start()] + mutated + text[m.end():],
                    encoding="utf-8")


def fail_out(fails: list[str]) -> int:
    print("\na64_wificon_check: FAIL - %d" % len(fails))
    for f in fails:
        print("  * %s" % f)
    return 1


def one_run(lib_include: str, tag: str, mutated: str,
            fails: list[str],
            rb_include: str = "Anvil/Core/readback.pbi",
            rb_fails: list[str] | None = None) -> int:
    """One build and one run of the script.

    `mutated` names a library control: "rearm" inverts the arming cases
    and cannot grade L at all (nothing arms); "drain" grades L0 inverted
    and nothing else; "tcp" grades T inverted. "" is the real library.
    `rb_fails`, when given, collects L's failures separately from everything else -
    that is the readback control, where L MUST fail and nothing else may.
    """
    work = WORK / tag
    work.mkdir(parents=True, exist_ok=True)
    harness = work / "netconharness.pi4"
    img = work / "netconcheck.img"
    write_harness(lib_include, harness, rb_include)
    build(harness, img)
    s, at = build_script()
    cpu, console, steps = run(img, s.finish())
    if b"netconharness done" not in bytes(console):
        fails.append("the harness did not reach its last line, so the "
                     "results are from an incomplete run")
        return steps
    res = read_results(cpu.memory, s.labels)
    if len(res) != len(s.labels):
        fails.append("the harness wrote %d result records for %d script "
                     "steps, so the run stopped part way through"
                     % (len(res), len(s.labels)))
        return steps
    # Every result record, when WIFICON_DUMP is set in the environment.
    # A failing case names what it wanted; this names what every step
    # of the script actually answered, which is the difference between
    # 'the OFFER is 0 bytes' and 'the pump never ran'.
    if __import__('os').environ.get('WIFICON_DUMP'):
        for i, rr in enumerate(res):
            print('  %3d op=%-3d r=%-12d e1=%-12d e2=%-12d %s'
                  % (i, rr.op, rr.r, rr.e1, rr.e2, rr.label))
    check(res, at, bytes(console), fails, mutated)
    if not mutated:
        check_readback(res, at, bytes(console),
                       fails if rb_fails is None else rb_fails)
    return steps


def resolve_compiler(requested):
    """Resolve the PureMetal compiler. A named compiler (explicit or
    PMF_COMPILER) is routed through the shared, validating resolver
    (tools/pmf_compiler.py): refuses a missing, retired, or
    untracked/stale executable (forum 977). With nothing named, this
    falls back to tools/build.py's bare-PATH search, unchanged."""
    sys.path.insert(0, str(ROOT / "tools"))
    import build as anvil_build  # noqa: E402
    if requested or os.environ.get("PMF_COMPILER"):
        from pmf_compiler import resolve_compiler as _pmf_resolve_compiler  # noqa: E402
        return _pmf_resolve_compiler(requested)
    return anvil_build.find_compiler(requested)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"),
                    help="path of PureMetalForge.exe (or set PMF_COMPILER); "
                         "it is run with --compile")
    ap.add_argument("--target", choices=["pi4"], default="pi4")
    ap.add_argument("--mutate", action="store_true",
                    help="run the negative control as well")
    args = ap.parse_args()
    globals()["PMFC"] = resolve_compiler(args.compiler)
    row = apply_target(globals(), args.target)

    print("[gate] tree under test: %s" % ROOT, file=sys.stderr)
    print("a64_wificon_check: grading %s" % row["what"])
    print("                   the NETWORK console's arming in "
          "Anvil/Core/netconsole.pbi,")
    print("                   over a scripted TWO-LINK seam - no radio, "
          "no MAC, no credentials")

    fails: list[str] = []
    steps = one_run("Anvil/Core/netconsole.pbi", "fixed", "", fails)
    if fails:
        return fail_out(fails)

    cases = 25 + 7
    if args.mutate:
        mutant = WORK / "mutant" / "netconsole_prefix_rearm.pi4"
        write_mutant(mutant)
        rel = mutant.relative_to(ROOT).as_posix()
        mfails: list[str] = []
        one_run(rel, "mutant", "rearm", mfails)
        if mfails:
            return fail_out(mfails)
        print("  negative control: the pre-fix NetConsoleRearm leaves the "
              "console DEAF on the same script")
        cases += 1

        # THE DRAIN IS A DIFFERENT DEFECT AND NEEDS ITS OWN MUTATION.
        # Reverting the arming says nothing about how many frames one pump
        # takes, and L0 would pass against a one-frame pump if one were
        # never built to check.
        dmutant = WORK / "mutant_drain" / "netconsole_one_frame_pump.pi4"
        write_drain_mutant(dmutant)
        drel = dmutant.relative_to(ROOT).as_posix()
        dfails: list[str] = []
        one_run(drel, "mutant_drain", "drain", dfails)
        if dfails:
            return fail_out(dfails)
        print("  negative control: a one-frame pump leaves 2 of 3 queued "
              "frames on the wire and only the first in the ring (L0)")
        cases += 1

        # AND THE TCP ARM, a third distinct defect: neither mutation above
        # touches what the dispatcher does with a segment.
        tmutant = WORK / "mutant_tcp" / "netconsole_no_tcp_arm.pi4"
        write_tcp_mutant(tmutant)
        trel = tmutant.relative_to(ROOT).as_posix()
        tfails: list[str] = []
        one_run(trel, "mutant_tcp", "tcp", tfails)
        if tfails:
            return fail_out(tfails)
        print("  negative control: with the dispatcher's TCP arm removed the "
              "segment is taken off the wire and TCP is never entered (T)")
        cases += 1

        rb_mutant = WORK / "mutant_rb" / "readback_through_uart.pbi"
        write_rb_mutant(rb_mutant)
        rb_rel = rb_mutant.relative_to(ROOT).as_posix()
        other: list[str] = []
        lfails: list[str] = []
        one_run("Anvil/Core/netconsole.pbi", "mutant_rb", "", other,
                rb_rel, lfails)
        if other:
            return fail_out(["READBACK CONTROL: a case other than L went red "
                             "when only the readback's routing was changed"]
                            + other)
        missing = [tag for tag in ("L1.", "L2.")
                   if not any(f.startswith(tag) for f in lfails)]
        if missing:
            return fail_out(["READBACK CONTROL: with the payload put back "
                             "through UartWrite, %s stayed GREEN. A gate "
                             "that cannot see the measured defect is not "
                             "grading it." % " and ".join(missing)])
        print("  negative control: the payload put back through UartWrite "
              "goes red on the datagram count (L1) and on the serial "
              "capture (L2)")
        cases += 1

    print("\na64_wificon_check: PASS - %d cases on %s, %s model instructions"
          % (cases, args.target, "{:,}".format(steps)))
    print("""
  WHAT IS NOT COVERED, and it is the half that needs a board:
   * THE WIRES. No CYW43 firmware, no SDIO, no association, no key, no
     GENET, no PHY, no auto-negotiation. This proves the DECISION and the
     datagram, not that a Pi 4 can put a frame on a cable or in the air.
     That is a64_genet_check.py, a64_wpa2sup_check.py, a64_sdio_check.py
     and a cold boot on the part.
   * DHCP ITSELF. No client is run here; the case that matters is
     precisely the one where somebody ELSE bound the lease.
   * THE BOOT ORDER. RaspberryPi4/Board/boot.pi4 brings the wired link up
     before the wireless auto-join and Anvil/Core/parse.pbi re-derives the
     arming on every spin; that it works from cold
     needs a board.""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

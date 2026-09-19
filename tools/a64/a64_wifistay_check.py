#!/usr/bin/env python3
"""a64_wifistay_check - THE LINK STAYS JOINED.

The standing rule for every board with a radio: auto-join at boot, and
stay joined until told not to - a connection is not to be dropped unless
something asked for it.  This gate is the short, aimed proof of the
second half.  It runs RaspberryPi4/Lib/wifi.pi4 and
RaspberryPi4/Lib/wpa2sup.pi4 - the real ones, with the real crypto under
them - over a scripted radio in the A64 model, and puts each of the ways
the link was found to die in front of them:

    1. an access point's GROUP KEY rekey            the link stays up
    2. a PAIRWISE (PTK) rekey                       the link stays up
    4. a firmware DEAUTH event                      the backstop
                                                    reconnects AND SAYS SO
    5. a firmware LINK-DOWN event                   the same
    6. a rekey with the console NOT armed           still serviced
    7. inbound traffic during a TX-only death       the detector still
                                                    fires

Each of the three fixes still in wifi.pi4 and hw_link.pi4 has a
MUTATION CONTROL: the gate reverts exactly that one procedure body in a
COPY of the library, rebuilds, and requires the matching case to go RED.

THERE IS NO CASE 3 ANY MORE, AND THAT IS NOT A GAP IN THIS FILE. Case 3
was a DHCP lease reaching T1 and being renewed by wifi.pi4. The radio no
longer runs a DHCP client of its own: every interface uses the common
per-interface client in Anvil/Network/dhcp.pbi, driven by the lease
worker in Anvil/Core/netconsole.pbi, and that client is graded by
RaspberryPi4/Tests/dhcp_emitted_gate.pi4. The cases below bind the
radio's address the way the board does once a lease exists
(WifiAdoptAddress), because what they grade is the association, not the
lease.  A mutation that fails to reach the code
fails the gate rather than passing quietly.

WHAT IS NOT COVERED, and it is said here rather than left to be assumed:
no CYW43 firmware, no SDIO, no air.  The association, the scan and the
firmware's own behaviour are the board's job, not this gate's.
"""

import argparse
import os
import pathlib
import re
import struct
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))

from a64_interp import A64, attach_symbols                       # noqa: E402
from a64_target import TARGETS, patch_harness                    # noqa: E402
from a64_wpa2sup_check import (Handshake, have_wrap)             # noqa: E402

PMFC = os.environ.get("PMF_COMPILER") or "PureMetalForge.exe"  # rebound from --compiler
# Every compile resolves includes from THIS tree only.
BUILD_ENV = dict(os.environ, PMF_ROOT=str(ROOT))
LIB = ROOT / "RaspberryPi4" / "Lib" / "wifi.pi4"
HWLINK = ROOT / "RaspberryPi4" / "Board" / "hw_link.pi4"
WORK = ROOT / "_work" / "wifistay"

TFLAG = "pi4"
LOAD = TARGETS["pi4"]["load"]
STACK = TARGETS["pi4"]["stack"]
H_SCRIPT = TARGETS["pi4"]["script"]
H_RESULT = TARGETS["pi4"]["script"] + 0x00800000
SINK_LO = TARGETS["pi4"]["uart_lo"]
SINK_HI = TARGETS["pi4"]["uart_hi"]

LOADER_LR = 0xDEADBEE0
CNTFRQ = 54_000_000
STEPS_PER_TICK = 8
STEP_LIMIT = 400_000_000

# ---- the vocabulary, restated INDEPENDENTLY of the files under test.
WIFI_CON_PORT = 5555
ET_IPV4 = 0x0800
ET_EAPOL = 0x888E
IPPROTO_UDP = 17
EV_DEAUTH = 5
EV_DEAUTH_IND = 6
EV_DISASSOC = 11
EV_DISASSOC_IND = 12
EV_LINK = 16
EV_ROAM = 19
LINK_UP_FLAG = 1
WPA2SUP_SENT_M2 = 1
WPA2SUP_SENT_M4 = 2
WPA2SUP_SENT_G2 = 3

# The constants the harness needs to COMPILE wifi.pi4 with no radio in
# the image.  They are lifted out of the real libraries, never typed
# here, so there is no second copy of a value to rot.
BORROWED = {
    "RaspberryPi4/Lib/cyw43.pi4": [
        "#CYW43_CRYPTO_ALGO_AES_CCM", "#CYW43_EVMASK_JOIN",
        "#CYW43_EV_DEAUTH", "#CYW43_EV_DEAUTH_IND",
        "#CYW43_EV_DISASSOC", "#CYW43_EV_DISASSOC_IND",
        "#CYW43_EV_LINK", "#CYW43_EV_LINK_UP_FLAG", "#CYW43_EV_ROAM",
        "#CYW43_JOINEXP_NOKEY", "#CYW43_JOIN_JOINED",
        "#CYW43_JOIN_RUNNING", "#CYW43_SCAN_DONE", "#CYW43_SCAN_FAILED",
        "#CYW43_PM_OFF",
        "#CYW43_IO_OK", "#CYW43_IO_STATUS", "#CYW43_JOIN_FAILED",
    ],
    "RaspberryPi4/Lib/entropy.pi4": ["#ENTROPY_SPINS", "#ENTROPY_OK"],
    # The link kinds and the two link-property sentinels. hw_link.pi4 and
    # link.pi4 are IN this image - the seam that winds the round-trip
    # clock is the thing case 7 is about, and a gate that stubbed it
    # would be grading a copy of the defect rather than the defect.
    "Anvil/Hal/hal.pbi": [
        "#HW_LINK_NONE", "#HW_LINK_WIRED", "#HW_LINK_WIFI",
        "#HW_LINK_SERIAL", "#HW_LINK_FIRMWARE", "#HW_LINK_FILE",
        "#HW_LINK_SPEED_UNKNOWN", "#HW_LINK_DUPLEX_UNKNOWN",
        "#HW_LINK_DUPLEX_HALF", "#HW_LINK_DUPLEX_FULL",
        # Added 2026-09-07: the console left wifi.pi4 for
        # Anvil/Core/netconsole.pbi and its port went to the HAL, which
        # is the one place both files can read it. wifi.pi4 still
        # prints it in its status line, so this image needs it.
        "#NETCON_PORT",
        # how many frames one drain of an interface ring may take
        "#LINK_RX_BUDGET",
    ],
    # The two console styles the network console switches between; the
    # screen console that consumes them is not in this image.
    "Anvil/Core/console_style.pbi": [
        "#UART_SCREEN_STYLE_NORMAL", "#UART_SCREEN_STYLE_PROMPT",
    ],
}


def borrow_constants() -> str:
    out = ["; ---- constants lifted verbatim from the real libraries by",
           "; ---- tools/a64/a64_wifistay_check.py.  A missing one fails",
           "; ---- the gate rather than being retyped here."]
    for rel, names in BORROWED.items():
        text = (ROOT / rel).read_text(encoding="utf-8", errors="ignore")
        for name in names:
            m = re.search(r"(?m)^\s*(%s\s*=[^\r\n]*)$" % re.escape(name),
                          text)
            if not m:
                raise SystemExit(
                    "a64_wifistay_check: %s is no longer defined in %s, so "
                    "the harness cannot be generated.  Either it was "
                    "renamed - fix this gate - or deleted, in which case "
                    "wifi.pi4 no longer compiles." % (name, rel))
            out.append(m.group(1).strip())
    return "\n".join(out)


# =====================================================================
#  FRAMES, WRITTEN FROM THE RFCs AND NOT FROM THE LIBRARY
# =====================================================================
def ip4(a, b, c, d):
    return (a << 24) | (b << 16) | (c << 8) | d


def ones_complement(data, seed=0):
    s = seed
    if len(data) & 1:
        data = bytes(data) + b"\x00"
    for i in range(0, len(data), 2):
        s += (data[i] << 8) | data[i + 1]
    while s >> 16:
        s = (s & 0xFFFF) + (s >> 16)
    return (~s) & 0xFFFF


def ipv4(src, dst, proto, payload, ident=0xB00B):
    hdr = bytearray(20)
    hdr[0] = 0x45
    struct.pack_into(">H", hdr, 2, 20 + len(payload))
    struct.pack_into(">H", hdr, 4, ident)
    hdr[8] = 64
    hdr[9] = proto
    struct.pack_into(">I", hdr, 12, src)
    struct.pack_into(">I", hdr, 16, dst)
    struct.pack_into(">H", hdr, 10, ones_complement(bytes(hdr)))
    return bytes(hdr) + bytes(payload)


def udp(sport, dport, payload):
    h = bytearray(8)
    struct.pack_into(">H", h, 0, sport)
    struct.pack_into(">H", h, 2, dport)
    struct.pack_into(">H", h, 4, 8 + len(payload))
    return bytes(h) + bytes(payload)


def eth(dst, src, et, payload):
    return bytes(dst) + bytes(src) + struct.pack(">H", et) + bytes(payload)


# ---- the fixture's addresses ----------------------------------------
# RADIO_MAC and AP_MAC ARE THE AUTHENTICATOR'S OWN, filled in main() from
# the Handshake: every EAPOL frame it builds is addressed with them and
# every key it derives is bound to them, so a gate that used addresses of
# its own would be grading a MIC over the wrong two stations.
RADIO_MAC = bytes(6)
AP_MAC = bytes(6)
SRV_MAC = bytes([0x02, 0x31, 0x41, 0x59, 0x26, 0x53])
PEER_MAC = bytes([0x02, 0x99, 0x88, 0x77, 0x66, 0x01])
LEASE_IP = ip4(192, 168, 1, 25)
MASK = ip4(255, 255, 255, 0)
GW_IP = ip4(192, 168, 1, 1)
SRV_IP = ip4(192, 168, 1, 1)
PEER_IP = ip4(192, 168, 1, 9)
PEER_PORT = 41234
LEASE_SECS = 3600
# Anvil/Core/netif.pbi's source code for an address that came from a lease.
NET_ADDR_LEASE = 1
TYPED = b"info\n"

# The fixture's entropy is deterministic, and BOTH sides know it: the
# harness's EntropyBytes fills this pattern and the authenticator here
# derives the rekey PTK from the same bytes.  A random nonce in a gate is
# a gate that cannot check the key it produced.
FX_SNONCE = bytes(((i * 7 + 13) & 0xFF) for i in range(32))


def bootp(kind, yiaddr, xid, srv, lease=LEASE_SECS, t1=None, t2=None,
          include_lease=True):
    """One BOOTP reply, option 53 = kind (2 OFFER, 5 ACK, 6 NAK)."""
    b = bytearray(300)
    b[0] = 2
    b[1] = 1
    b[2] = 6
    b[4:8] = xid
    struct.pack_into(">I", b, 16, yiaddr)
    b[28:34] = RADIO_MAC
    b[236:240] = bytes([99, 130, 83, 99])
    o = 240
    for opt, val in ((53, bytes([kind])),
                     (1, struct.pack(">I", MASK)),
                     (3, struct.pack(">I", GW_IP)),
                     (54, struct.pack(">I", srv))):
        b[o] = opt
        b[o + 1] = len(val)
        b[o + 2:o + 2 + len(val)] = val
        o += 2 + len(val)
    if include_lease:
        for opt, val in ((51, struct.pack(">I", lease)),
                         (58, struct.pack(">I", t1 if t1 else lease // 2)),
                         (59, struct.pack(">I", t2 if t2 else lease * 7 // 8))):
            b[o] = opt
            b[o + 1] = 4
            b[o + 2:o + 6] = val
            o += 6
    b[o] = 255
    return bytes(b)


def dhcp_frame(kind, xid, **kw):
    return eth(RADIO_MAC, SRV_MAC, ET_IPV4,
               ipv4(SRV_IP, 0xFFFFFFFF, IPPROTO_UDP,
                    udp(67, 68, bootp(kind, LEASE_IP, xid, SRV_IP, **kw))))


def console_datagram(payload):
    return eth(RADIO_MAC, PEER_MAC, ET_IPV4,
               ipv4(PEER_IP, LEASE_IP, IPPROTO_UDP,
                    udp(PEER_PORT, WIFI_CON_PORT, payload)))


def arp_reply(sender_ip, sender_mac):
    """The gateway answering the keepalive - the ONE solicited inbound."""
    p = bytearray(28)
    struct.pack_into(">HHBBH", p, 0, 1, ET_IPV4, 6, 4, 2)
    p[8:14] = sender_mac
    struct.pack_into(">I", p, 14, sender_ip)
    p[18:24] = RADIO_MAC
    struct.pack_into(">I", p, 24, LEASE_IP)
    return eth(RADIO_MAC, sender_mac, 0x0806, bytes(p))


# =====================================================================
#  THE STUBS ARE GENERATED FROM THE REAL SIGNATURES
# =====================================================================
#  Everything wifi.pi4, hw_link.pi4 and link.pi4 reach for that is not
#  in this image - the radio transport, the SDIO bus, the settings
#  store, the wired MAC - is answered by a one-line stub.  THE STUBS ARE
#  NOT TYPED HERE.  Each name is looked up in the library that really
#  declares it and the stub is emitted with THAT signature, so a
#  procedure that gains or loses a parameter cannot leave a stub behind
#  carrying the old arity.
#
#  A name that cannot be found at all fails the gate loudly rather than
#  having a signature invented for it.
#
#  A stub that was actually REACHED would show up at once: a join that
#  succeeded with no access point in the room, a settings store that
#  answered with no card in the slot.  Nothing in the script goes near
#  those paths.
STUB_SOURCES = [
    "RaspberryPi4/Lib/cyw43.pi4",
    "RaspberryPi4/Lib/sdio.pi4",
    "RaspberryPi4/Lib/genet.pi4",
    "RaspberryPi4/Lib/mailbox.pi4",
    # RaspberryPi4/Lib/fat.pi4 is an include list; the declarations are here.
    "Anvil/Storage/fat32.pbi",
    "Anvil/Storage/exfat.pbi",
    "Anvil/Storage/filesystem.pbi",
    "RaspberryPi4/Lib/usbmsc.pi4",
    "RaspberryPi4/Lib/entropy.pi4",
    "RaspberryPi4/Lib/tftp.pi4",
    "Anvil/Core/settings.pbi",
    "RaspberryPi4/Board/storage.pi4",
    "RaspberryPi4/Board/eth.pi4",
    "RaspberryPi4/Board/eth_mac.pi4",
    "Anvil/Core/crc.pbi",
]

# What the fixture implements itself, and must therefore NOT be stubbed.
FIXTURE_OWNS = {
    "Cyw43Receive", "Cyw43ReceivePtr", "Cyw43DataPtr", "Cyw43Send",
    "Cyw43PopEvent", "Cyw43JoinEventType", "Cyw43JoinEventStatus",
    "Cyw43JoinEventReason", "Cyw43JoinEventFlags", "Cyw43EventsDropped",
    "Cyw43EventsSeen", "Cyw43EventName", "Cyw43ReadBssid",
    "Cyw43SetWsecKey", "Cyw43ScanStart", "EntropyBytes",
    "EntropyBegin", "EntropyWarmupWait",
}

# The handful whose ZERO would be read as something rather than as
# nothing.  A "not found" slot index is -1; 0 is a valid slot.
STUB_RETURNS = {"SettingsWifiFindSsid": "-1"}

# A text accessor's result is PRINTED, so a zero there is a jump into
# address zero and not a quiet nothing.  There is no declared string
# type to key off, so the name is the signal - and in these files that
# is the whole of the family.
TEXT_RE = re.compile(r"(Text|Name|Means|Why)")

EXT_PREFIX = (r"(?:Cyw43|Sdio|Genet|Mailbox|Fat|Msc|Settings|Storage|Eth"
              r"|Tftp|Entropy|Crc32)[A-Za-z0-9_]*")
CALL_RE = re.compile(r"\b(" + EXT_PREFIX + r")\s*\(")
# A PROCEDURE HANDED OVER AS A POINTER IS STILL A NAME THAT MUST
# EXIST, and it does not carry parentheses:
#     Cyw43SetIo(@SdioCmd52Read, @SdioCmd52Write, ...)
# Missing this form cost a build, and the compiler reports it as
# "cannot read from undeclared variable", which does not read like a
# missing procedure at all.
PTR_RE = re.compile(r"@(" + EXT_PREFIX + r")\b")
DECL_TMPL = r"(?m)^Procedure(\.\w+)?\s+%s\s*\(([^)]*)\)"


def borrow_stubs() -> str:
    wanted = set()
    for rel in ("RaspberryPi4/Lib/wifi.pi4",
                "RaspberryPi4/Board/hw_link.pi4",
                "RaspberryPi4/Lib/link.pi4",
                "Anvil/Network/net.pbi",
                "Anvil/Core/netfmt.pbi"):
        text = (ROOT / rel).read_text(encoding="utf-8", errors="ignore")
        # Comment lines are dropped first: a name that appears only in
        # prose is not a call, and stubbing it would hide a real gap.
        code = "\n".join(l for l in text.splitlines()
                         if not l.lstrip().startswith(";"))
        wanted |= set(CALL_RE.findall(code))
        wanted |= set(PTR_RE.findall(code))
    # Whatever those files, and the ones already in the image, define
    # themselves is not external.
    for rel in ("RaspberryPi4/Lib/wifi.pi4",
                "RaspberryPi4/Board/hw_link.pi4",
                "RaspberryPi4/Lib/link.pi4",
                "Anvil/Network/net.pbi",
                "Anvil/Core/netfmt.pbi",
                "RaspberryPi4/Lib/wpa2sup.pi4",
                "RaspberryPi4/Lib/sha1.pi4",
                "RaspberryPi4/Lib/hmacsha1.pi4",
                "RaspberryPi4/Lib/pbkdf2.pi4",
                "RaspberryPi4/Lib/aes.pi4",
                "RaspberryPi4/Lib/keywrap.pi4",
                "RaspberryPi4/Lib/uart.pi4"):
        text = (ROOT / rel).read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r"(?m)^Procedure(?:\.\w+)?\s+([A-Za-z0-9_]+)",
                             text):
            wanted.discard(m.group(1))
    wanted -= FIXTURE_OWNS

    sources = [(rel, (ROOT / rel).read_text(encoding="utf-8",
                                            errors="ignore"))
               for rel in STUB_SOURCES if (ROOT / rel).exists()]

    out = ["; ---- stubs GENERATED from the real declarations by",
           "; ---- tools/a64/a64_wifistay_check.py.  Never typed by hand:",
           "; ---- each signature is lifted from the library that declares",
           "; ---- the name, so an arity cannot drift out from under it."]
    missing = []
    for name in sorted(wanted):
        found = None
        for rel, text in sources:
            m = re.search(DECL_TMPL % re.escape(name), text)
            if m:
                found = (m.group(1) or "", m.group(2).strip())
                break
        if found is None:
            missing.append(name)
            continue
        rt, args = found
        if rt == "":
            out.append("Procedure %s(%s) : EndProcedure" % (name, args))
            continue
        if TEXT_RE.search(name):
            body = '""'
        else:
            body = STUB_RETURNS.get(name, "0")
        out.append("Procedure%s %s(%s) : ProcedureReturn %s : EndProcedure"
                   % (rt, name, args, body))
    if missing:
        raise SystemExit(
            "a64_wifistay_check: no declaration found for %s.  Either the "
            "name moved to a library not in STUB_SOURCES, or it is gone - "
            "and this gate will not invent a signature for it."
            % ", ".join(sorted(missing)))
    return "\n".join(out)


# =====================================================================
#  THE HARNESS
# =====================================================================
HARNESS = r'''
; ======================================================================
;  wifistayharness.pi4 - GENERATED BY tools/a64/a64_wifistay_check.py.
;                        DO NOT EDIT.
; ======================================================================
;  SCRIPT RECORD, 24 bytes then `ln` bytes of blob, padded to 4:
;     +0 op  +4 a  +8 b  +12 c  +16 d  +20 ln  +24 blob     (op 0 ends)
;  RESULT RECORD, 20 bytes then `n` bytes of blob, padded to 4:
;     +0 op  +4 result  +8 extra1  +12 extra2  +16 n  +20 blob
;
;  THE FIXTURE RADIO. A four-deep receive queue (a real rekey arrives
;  while other frames are in flight, and a DHCP exchange is two frames),
;  a staging buffer, a log of every frame that went out, an event ring,
;  a record of every key installed, and a clock the script advances.
;
;  Cyw43Receive ADVANCES THE CLOCK BY ITS TIMEOUT WHEN THE QUEUE IS
;  EMPTY, which is what a blocking read on a real radio does. Without
;  that, every timed loop in the library - the DHCP wait, the renewal
;  wait - would spin for ever against a clock that never moves.
;
;  THE SUPPLICANT AND ITS CRYPTO ARE THE REAL ONES. That is the point:
;  a rekey case run against a stubbed supplicant proves nothing about a
;  rekey. Only the radio, the storage and the settings store are stubs.
; ======================================================================
XIncludeFile "RaspberryPi4/Lib/uart.pi4"

#H_SCRIPT = $06000000
#H_RESULT = $06800000

#FX_FRAME_MAX = 2048
#FX_RXQ       = 4
#FX_TX_MAX    = 32768
#FX_TXQ       = 16
#FX_EVQ       = 8

Global Dim fxRx.a[#FX_FRAME_MAX * #FX_RXQ]
Global Dim fxRxLen.i[#FX_RXQ]
Global fxRxHead.i
Global fxRxTail.i
Global fxRxCur.i                    ; which slot Cyw43ReceivePtr points at

Global Dim fxStage.a[#FX_FRAME_MAX]
Global Dim fxTx.a[#FX_TX_MAX]
Global Dim fxTxOff.i[#FX_TXQ]
Global Dim fxTxLenA.i[#FX_TXQ]
Global fxTxN.i
Global fxTxUsed.i

Global Dim fxEvT.i[#FX_EVQ]
Global Dim fxEvS.i[#FX_EVQ]
Global Dim fxEvR.i[#FX_EVQ]
Global Dim fxEvF.i[#FX_EVQ]
Global fxEvHead.i
Global fxEvTail.i
Global fxEvT0.i
Global fxEvS0.i
Global fxEvR0.i
Global fxEvF0.i

; What the last Cyw43SetWsecKey was handed. The group rekey's whole
; visible effect on the radio is this call, so the gate reads it back.
Global Dim fxKeyData.a[64]
Global Dim fxKeyRsc.a[8]
Global fxKeyIndex.i
Global fxKeyLen.i
Global fxKeyAlgo.i
Global fxKeyEaSet.i
Global fxKeyCalls.i
Global fxKeyPairCalls.i

Global fxAssoc.i                    ; what Cyw43ReadBssid answers
Global fxScanRc.i                   ; what Cyw43ScanStart answers
Global fxMs.i

Procedure.i millis()
  ProcedureReturn fxMs
EndProcedure

Procedure delay(ms.i)
  fxMs = fxMs + ms
EndProcedure

Procedure delayMicroseconds(us.i)
EndProcedure

; ---- the fixture radio ----------------------------------------------
Procedure.i Cyw43Receive(ms.i)
  Define n.i
  If fxRxHead = fxRxTail
    ; Nothing waiting. A blocking read burns its timeout; so does this.
    fxMs = fxMs + ms
    ProcedureReturn 0
  EndIf
  fxRxCur = fxRxTail
  n = fxRxLen[fxRxTail]
  fxRxTail = (fxRxTail + 1) % #FX_RXQ
  ProcedureReturn n
EndProcedure

Procedure.i Cyw43ReceivePtr()
  ProcedureReturn @fxRx[fxRxCur * #FX_FRAME_MAX]
EndProcedure

Procedure.i Cyw43DataPtr()
  ProcedureReturn @fxStage[0]
EndProcedure

Procedure.i Cyw43Send(n.i)
  Define i.i
  ; THE DRIVER'S RETURN CONVENTION: #CYW43_IO_OK (zero) when the frame
  ; went, a nonzero #CYW43_IO_* code when it was refused. wifi_SendSup and
  ; hw_link.pi4 both test "<> 0". The two values are lifted out of
  ; cyw43.pi4 when the harness is generated, because a constant may not be
  ; used above the borrowed block.
  If n <= 0 Or (fxTxUsed + n) > #FX_TX_MAX Or fxTxN >= #FX_TXQ
    ProcedureReturn __CYW43_IO_TOOBIG__
  EndIf
  fxTxOff[fxTxN] = fxTxUsed
  fxTxLenA[fxTxN] = n
  i = 0
  While i < n
    fxTx[fxTxUsed + i] = fxStage[i]
    i = i + 1
  Wend
  fxTxUsed = fxTxUsed + n
  fxTxN = fxTxN + 1
  ProcedureReturn __CYW43_IO_OK__
EndProcedure

Procedure.i Cyw43PopEvent()
  If fxEvHead = fxEvTail
    ProcedureReturn 0
  EndIf
  fxEvT0 = fxEvT[fxEvTail]
  fxEvS0 = fxEvS[fxEvTail]
  fxEvR0 = fxEvR[fxEvTail]
  fxEvF0 = fxEvF[fxEvTail]
  fxEvTail = (fxEvTail + 1) % #FX_EVQ
  ProcedureReturn 1
EndProcedure

Procedure.i Cyw43JoinEventType() : ProcedureReturn fxEvT0 : EndProcedure
Procedure.i Cyw43JoinEventStatus() : ProcedureReturn fxEvS0 : EndProcedure
Procedure.i Cyw43JoinEventReason() : ProcedureReturn fxEvR0 : EndProcedure
Procedure.i Cyw43JoinEventFlags() : ProcedureReturn fxEvF0 : EndProcedure
Procedure.i Cyw43EventsDropped() : ProcedureReturn 0 : EndProcedure
Procedure.i Cyw43EventsSeen() : ProcedureReturn 0 : EndProcedure

; The names the backstop prints. Spelled out here so that a gate reading
; the console is reading a name and not a number.
Procedure.i Cyw43EventName(t.i)
  Select t
    Case 5
      ProcedureReturn "DEAUTH"
    Case 6
      ProcedureReturn "DEAUTH_IND"
    Case 11
      ProcedureReturn "DISASSOC"
    Case 12
      ProcedureReturn "DISASSOC_IND"
    Case 16
      ProcedureReturn "LINK"
    Case 19
      ProcedureReturn "ROAM"
  EndSelect
  ProcedureReturn "EVENT"
EndProcedure

Procedure.i Cyw43ReadBssid(ms.i)
  ProcedureReturn fxAssoc
EndProcedure

Procedure.i Cyw43SetWsecKey(index.i, *key, keylen.i, algo.i, *ea, *rsc, ms.i)
  Define i.i
  fxKeyCalls = fxKeyCalls + 1
  fxKeyIndex = index
  fxKeyLen = keylen
  fxKeyAlgo = algo
  fxKeyEaSet = 0
  If *ea <> 0
    fxKeyEaSet = 1
    fxKeyPairCalls = fxKeyPairCalls + 1
  EndIf
  i = 0
  While i < keylen And i < 64
    fxKeyData[i] = PeekA(*key + i)
    i = i + 1
  Wend
  For i = 0 To 7
    fxKeyRsc[i] = 0
  Next
  If *rsc <> 0
    For i = 0 To 7
      fxKeyRsc[i] = PeekA(*rsc + i)
    Next
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i Cyw43ScanStart(a.i, ms.i) : ProcedureReturn fxScanRc : EndProcedure

; ENTROPY IS DETERMINISTIC HERE AND THE GATE KNOWS THE PATTERN. A PTK
; rekey's SNonce comes from this, and a nonce the authenticator cannot
; predict is a key the gate cannot check.
Procedure EntropyBegin() : EndProcedure
Procedure.i EntropyWarmupWait(a.i) : ProcedureReturn 0 : EndProcedure
Procedure.i EntropyBytes(dst.i, n.i, spins.i)
  Define i.i
  i = 0
  While i < n
    PokeB(dst + i, (i * 7 + 13) & $FF)
    i = i + 1
  Wend
  ProcedureReturn n
EndProcedure

__STUBS__

__BORROWED__

XIncludeFile "Anvil/Network/net.pbi"
XIncludeFile "Anvil/Core/netfmt.pbi"
; PutHex8, for the console's lease report line.
XIncludeFile "Anvil/Core/format.pbi"
XIncludeFile "RaspberryPi4/Lib/sha1.pi4"
XIncludeFile "RaspberryPi4/Lib/hmacsha1.pi4"
XIncludeFile "RaspberryPi4/Lib/pbkdf2.pi4"
XIncludeFile "RaspberryPi4/Lib/aes.pi4"
XIncludeFile "RaspberryPi4/Lib/keywrap.pi4"
XIncludeFile "RaspberryPi4/Lib/wpa2sup.pi4"
; ONE ADDRESS RECORD PER INTERFACE. It is ABOVE the library under test
; because wifi.pi4 names the #NET_ADDR_* codes when it binds the radio's
; boot lease, and a constant may not be used before it is declared -
; which is exactly the order the board file uses, for the same reason.
XIncludeFile "Anvil/Core/netif.pbi"
; THE DHCP MESSAGE LAYOUT AND THE PER-INTERFACE CLIENT. wifi.pi4 names
; the client's states, the server takes its field offsets from here, and
; the console's dispatcher hands port-68 datagrams to the client - so the
; real file is in the image rather than a copy of its constants. It needs
; nothing but net.pbi.
XIncludeFile "Anvil/Network/dhcp.pbi"
XIncludeFile "__LIB__"
XIncludeFile "__HWLINK__"
XIncludeFile "RaspberryPi4/Lib/link.pi4"
; AND THE DHCP SERVER the console's pump feeds. It is in this image for
; the same reason the console is: the radio's own receive pump stands
; down only while the console is reading that radio's frames, and the
; console decides that from the per-interface table. A stub would grade
; a copy of the decision instead of the decision.
XIncludeFile "Anvil/Core/dhcpd.pbi"
; THE NETWORK CONSOLE. It moved out of wifi.pi4 on 2026-09-07 and it
; is in this image rather than stubbed because the radio's own
; receive pump stands down only when the console is on THIS RADIO -
; a stub would grade a copy of that decision instead of the decision.
; FOUR NAMES THE CONSOLE REACHES THAT ARE NOT IN THIS IMAGE. The lease
; worker binds and drops an address through Anvil/Core/netcfg.pbi, and
; the dispatcher offers a datagram to Anvil/Core/ntp_service.pbi and a
; segment to RaspberryPi4/Lib/tcp.pi4 before the console sees it. Each
; brings the settings store or a transport with it; no datagram in this
; script is SNTP and no frame is TCP. The address a DHCP exchange binds
; on the radio is graded through wifi.pi4's own path, not these.
Procedure NetAddressBound(kind.i, ip.i, mask.i, gw.i, src.i) : EndProcedure
Procedure NetAddressLost(kind.i) : EndProcedure
Procedure.i NtpServiceInput(kind.i) : ProcedureReturn 0 : EndProcedure
Procedure TcpInput() : EndProcedure
XIncludeFile "Anvil/Core/netconsole.pbi"

Procedure fxSetOurMac(p.i)
  Define i.i
  For i = 0 To 5
    wifi_ourMac[i] = PeekA(p + i)
  Next
EndProcedure

Procedure fxReset()
  Define i.i
  fxRxHead = 0
  fxRxTail = 0
  fxRxCur = 0
  fxTxN = 0
  fxTxUsed = 0
  fxEvHead = 0
  fxEvTail = 0
  fxKeyCalls = 0
  fxKeyPairCalls = 0
  fxKeyIndex = -1
  fxKeyLen = 0
  fxKeyEaSet = 0
  fxAssoc = 1
  fxScanRc = -1
  fxMs = 100000
  For i = 0 To 5
    wifi_ourMac[i] = 0
    wifi_apMac[i] = 0
  Next
  ; The RADIO stands down from its own receive pump only while the
  ; console is armed ON IT (HwLinkConsoleArmed -> WifiSetConsoleOwnsRx).
  ; A board reset re-initialises that flag; this harness resets by hand,
  ; so it has to say so - leaving it set made case 6 report a rekey that
  ; was never read when the reason was a stale bit in the fixture.
  WifiSetConsoleOwnsRx(0)
  gConOn = 0
  gConKind = #HW_LINK_NONE
  gConIp = 0
  gConArms = 0
  gConPeerOk = 0
  gConPeerIp = 0
  gConPeerPort = 0
  gConPeerKind = #HW_LINK_NONE
  gConPeerDstIp = 0
  gConInHead = 0
  gConInTail = 0
  ; THE PER-INTERFACE TABLE IS BOARD STATE AND A RESET FORGETS IT. The
  ; console arms on the interfaces that HOLD AN ADDRESS since
  ; 2026-09-07, so a table left standing from the previous case is a
  ; board that comes up already addressed - and case 6, which is about
  ; a board with no address at all, would then be measuring nothing.
  ; The clock going back matters for the same reason it does in
  ; a64_wificon_check: NetConsolePump refuses to run for 5 ms after its
  ; last turn, and fxMs is set back below.
  gConLastPump = 0
  DhcpdStop()
  NetIfReset()
  ; The radio's lease state lives in the common per-interface client now.
  DhcpClientReset(#HW_LINK_WIFI)
  gWifiKeyed = 0
  gWifiSecDone = 0
  gWifiHaveIp = 0
  gWifiIp = 0
  gWifiMask = 0
  gWifiGw = 0
  gWifiUp = 1
  gWifiRejoins = 0
  gWifiHealPend = 0
  gWifiKaLast = 0
  gWifiKaProbes = 0
  gWifiRxProof = 0
  gWifiBadReads = 0
  gWifiDeauths = 0
  gWifiTeardown = 0
  gWifiVerify = 0
  gWifiRoams = 0
  gWifiGrpKeyed = 0
  gWifiPtkKeyed = 0
  gWifiEapolErr = 0
  gWifiEapolSeen = 0
  gWifiRadioLast = 0
  gConLastPump = 0
  ; THE RECOVERY STATE MACHINE IS BOARD STATE TOO. A teardown in one case
  ; starts WifiRecoveryStart; left standing, the next case's WifiLinkTick
  ; runs the recovery step and returns before WifiRadioPump, so that
  ; case's events are never drained. A board reset re-initialises it.
  gWifiRecPhase = #WIFI_REC_IDLE
  gWifiRinitPhase = #WIFI_RINIT_IDLE
  gWifiEapolRecover = 0
  UartAuxMirror(0)
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
  Define slot.i

  p = #H_SCRIPT
  q = #H_RESULT
  fxReset()

  Repeat
    op = PeekL(p)
    If op = 0
      Break
    EndIf
    a = PeekL(p + 4)
    b = PeekL(p + 8)
    c = PeekL(p + 12)
    d = PeekL(p + 16)
    ln = PeekL(p + 20)
    blob = p + 24
    r = 0
    e1 = 0
    e2 = 0
    n = 0
    src = #H_RESULT + $00400000

    If op = 1
      fxReset()
      fxSetOurMac(blob)
      r = 1

    ElseIf op = 2
      gWifiKeyed = a
      gWifiSecDone = b
      r = gWifiKeyed
      e1 = gWifiHaveIp

    ElseIf op = 3
      ; THE RADIO IS GIVEN AN ADDRESS. Since 2026-09-07 that means a
      ; record against the RADIO's #HW_LINK_* kind rather than a write
      ; into the one IP layer: the console arms on the interfaces that
      ; hold an address, not on whatever the stack happens to be
      ; configured for, which is what let a second link steal the first
      ; one's identity. NetIfSet points the stack at the radio as part
      ; of recording it, so this op does what it always did as well.
      r = NetSetMac(#HW_LINK_WIFI, blob)
      e1 = NetIfSet(#HW_LINK_WIFI, a, b, c, 1)
      e2 = NetError()

    ElseIf op = 4
      NetConsoleRearm()
      r = NetConsoleOn()
      e1 = gWifiHaveIp
      e2 = gWifiIp

    ElseIf op = 5
      slot = fxRxHead
      i = 0
      While i < ln And i < #FX_FRAME_MAX
        fxRx[slot * #FX_FRAME_MAX + i] = PeekA(blob + i)
        i = i + 1
      Wend
      fxRxLen[slot] = ln
      fxRxHead = (fxRxHead + 1) % #FX_RXQ
      r = ln

    ElseIf op = 6
      NetConsolePump()
      r = fxTxN
      e1 = gConPeerOk
      e2 = gWifiEapolSeen

    ElseIf op = 7
      If a < fxTxN
        n = fxTxLenA[a]
        i = 0
        While i < n
          PokeB(src + i, fxTx[fxTxOff[a] + i])
          i = i + 1
        Wend
      EndIf
      r = n
      e1 = fxTxN

    ElseIf op = 8
      n = 0
      Repeat
        i = NetConsoleGetc()
        If i < 0
          Break
        EndIf
        PokeB(src + n, i)
        n = n + 1
      ForEver
      r = n

    ElseIf op = 9
      fxMs = fxMs + a
      r = fxMs

    ElseIf op = 10
      WifiLinkTick()
      r = gWifiRejoins
      e1 = gWifiHealPend
      e2 = gWifiKeyed

    ElseIf op = 11
      slot = fxEvHead
      fxEvT[slot] = a
      fxEvS[slot] = b
      fxEvR[slot] = c
      fxEvF[slot] = d
      fxEvHead = (fxEvHead + 1) % #FX_EVQ
      r = 1

    ElseIf op = 12
      r = gWifiGrpKeyed
      e1 = gWifiPtkKeyed
      e2 = gWifiEapolErr

    ElseIf op = 13
      n = 0
      i = 0
      While i < fxKeyLen And i < 64
        PokeB(src + n, fxKeyData[i])
        n = n + 1
        i = i + 1
      Wend
      For i = 0 To 7
        PokeB(src + n, fxKeyRsc[i])
        n = n + 1
      Next
      r = fxKeyIndex
      e1 = fxKeyLen
      e2 = fxKeyEaSet

    ElseIf op = 14
      ; blob: 32 PMK, 6 our MAC, 6 AP MAC, 32 SNonce, then the RSN
      ; element. The SNonce comes from the caller because the
      ; authenticator on the other side derived its PTK with it.
      For i = 0 To 5
        wifi_apMac[i] = PeekA(blob + 38 + i)
      Next
      r = Wpa2SupBegin(blob, blob + 32, blob + 38, blob + 76, ln - 76)
      Wpa2SupSetSnonce(blob + 44)
      e1 = Wpa2SupState()

    ElseIf op = 15
      r = Wpa2SupHandle(blob, ln)
      n = Wpa2SupTxLen()
      If n > 0
        i = 0
        While i < n
          PokeB(src + i, PeekA(Wpa2SupTxPtr() + i))
          i = i + 1
        Wend
      EndIf
      e1 = n
      e2 = Wpa2SupLastError()

    ElseIf op = 16
      Wpa2SupSessionArm()
      r = Wpa2SupState()

    ElseIf op = 17
      fxAssoc = a
      r = fxAssoc

    ElseIf op = 18
      r = gWifiRxProof
      e1 = gWifiKaProbes
      e2 = gWifiDeauths

    ElseIf op = 19
      r = DhcpClientLease(#HW_LINK_WIFI)
      e1 = DhcpClientState(#HW_LINK_WIFI)
      e2 = gWifiIp

    ElseIf op = 20
      ; THE RADIO TAKES AN ADDRESS, through the same procedure the board
      ; calls once a lease exists: a = ip, b = mask, c = gateway.
      WifiAdoptAddress(a, b, c)
      r = gWifiHaveIp
      e1 = gWifiIp
      e2 = NetIfSrc(#HW_LINK_WIFI)

    ElseIf op = 21
      r = 0
      e1 = 0
      e2 = gWifiRoams

    ElseIf op = 22
      ; The fixture's own SNonce, so the authenticator can derive the
      ; same rekey PTK the board will.
      n = 32
      i = 0
      While i < 32
        PokeB(src + i, (i * 7 + 13) & $FF)
        i = i + 1
      Wend
      r = n

    ElseIf op = 23
      WifiRadioPump()
      r = gWifiEapolSeen
      e1 = gWifiTeardown
      e2 = fxTxN

    ElseIf op = 24
      ; Forget the frames sent so far, so the next case reads a clean
      ; wire without a reset.
      fxTxN = 0
      fxTxUsed = 0
      r = 0

    ElseIf op = 25
      r = LinkUseKind(a)
      e1 = LinkUp()

    ElseIf op = 26
      ; ONE SLICE OF THE REAL PUMP - the same call the prompt's TcpTick
      ; makes and every network command makes. This is the path whose
      ; HwLinkNoteRx used to wind the round-trip clock for a frame that
      ; had merely arrived.
      r = LinkPumpNet(0)
      e1 = gWifiRxProof
      e2 = gWifiKaProbes

    EndIf

    PokeL(q, op)
    PokeL(q + 4, r)
    PokeL(q + 8, e1)
    PokeL(q + 12, e2)
    PokeL(q + 16, n)
    i = 0
    While i < n
      PokeB(q + 20 + i, PeekA(src + i))
      i = i + 1
    Wend
    q = q + 20 + ((n + 3) / 4) * 4
    p = p + 24 + ((ln + 3) / 4) * 4
  ForEver

  PokeL(q, 0)
  UartWriteStr("wifistayharness done")
  ProcedureReturn 0
EndProcedure

Main()
'''


# =====================================================================
#  SCRIPT / RESULT PLUMBING
# =====================================================================
class Script:
    def __init__(self):
        self.buf = bytearray()
        self.labels = []

    def add(self, op, a=0, b=0, c=0, d=0, blob=b"", label=""):
        self.buf += struct.pack("<6I", op, a & 0xFFFFFFFF, b & 0xFFFFFFFF,
                                c & 0xFFFFFFFF, d & 0xFFFFFFFF, len(blob))
        self.buf += bytes(blob)
        while len(self.buf) % 4:
            self.buf += b"\x00"
        self.labels.append(label or ("op %d" % op))
        return len(self.labels) - 1

    def finish(self):
        return bytes(self.buf) + struct.pack("<I", 0)


class Result:
    def __init__(self, op, r, e1, e2, blob, label):
        self.op, self.r, self.e1, self.e2 = op, r, e1, e2
        self.blob, self.label = blob, label


def _signed(v):
    return v - 0x100000000 if v & 0x80000000 else v


def read_results(mem, labels):
    out = []
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
                "a64_wifistay_check: a result record claims %d bytes, longer "
                "than any buffer in this harness. The stream is corrupt." % n)
        blob = bytes(mem.get(addr + 20 + i, 0) for i in range(n))
        i = len(out)
        out.append(Result(op, _signed(w(4)), _signed(w(8)), _signed(w(12)),
                          blob, labels[i] if i < len(labels) else "?"))
        addr += 20 + ((n + 3) // 4) * 4
    return out


def build(source, out):
    cmd = [str(PMFC), "--compile", str(source), "-t", TFLAG,
           "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
           "--entry-returns", "-o", str(out)]
    r = subprocess.run(cmd, cwd=ROOT, env=BUILD_ENV, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout:
        tail = "\n".join(r.stdout.splitlines()[-25:])
        raise SystemExit("build failed:\n" + tail)


def run(img, script):
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
            return mem, bytes(console), steps[0]
        step()
    raise SystemExit("a64_wifistay_check: the harness never returned "
                     "(%d steps)" + chr(10) + "%s"
                     % (steps[0], console.decode("latin-1")))


def lift_value(rel, name):
    """The right-hand side of one constant definition in a real library."""
    text = (ROOT / rel).read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"(?m)^\s*%s\s*=\s*([^\s;]+)" % re.escape(name), text)
    if not m:
        raise SystemExit("a64_wifistay_check: %s is no longer defined in %s, "
                         "so the fixture radio cannot answer with the "
                         "driver's own return codes. Fix this gate." % (name, rel))
    return m.group(1)


def write_harness(lib_include, hwlink_include, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = HARNESS.replace("__BORROWED__", borrow_constants())
    text = text.replace("__STUBS__", borrow_stubs())
    text = text.replace("__LIB__", lib_include)
    text = text.replace("__HWLINK__", hwlink_include)
    for name in ("CYW43_IO_OK", "CYW43_IO_TOOBIG"):
        text = text.replace("__%s__" % name,
                            lift_value("RaspberryPi4/Lib/cyw43.pi4", "#" + name))
    text = patch_harness(text, globals())
    path.write_text(text, encoding="utf-8")


# =====================================================================
#  THE MUTATIONS - one per fix, each reverting exactly that fix
# =====================================================================
PRE_FIX_RADIO_PUMP = """Procedure WifiRadioPump()
  WifiDrainEvents()
EndProcedure"""

PRE_FIX_DRAIN_LINK = """    ElseIf et = #CYW43_EV_LINK
      down = 0"""

PRE_FIX_NOTE_RX = """Procedure HwLinkNoteRx(kind.i, r.i)
  If kind <> #HW_LINK_WIFI
    ProcedureReturn
  EndIf
  If r = #NET_IN_LEARNED
    WifiNoteRxProof()
  ElseIf r = #NET_IN_PONG
    WifiNoteRxProof()
  ElseIf r = #NET_IN_TCP
    WifiNoteRxProof()
  ElseIf r = #NET_IN_UDP
    WifiNoteRxProof()
  EndIf
EndProcedure"""


def mutate_lib(kind, dest):
    """Write a copy of wifi.pi4 with exactly one fix reverted."""
    text = LIB.read_text(encoding="utf-8", errors="ignore")
    if kind == "pump":
        m = re.search(r"(?ms)^Procedure WifiRadioPump\(\).*?^EndProcedure",
                      text)
        if not m:
            raise SystemExit("a64_wifistay_check: WifiRadioPump is no longer "
                             "a procedure in wifi.pi4 - the mutation cannot "
                             "reach the code, so the gate refuses to pass.")
        text = text[:m.start()] + PRE_FIX_RADIO_PUMP + text[m.end():]
    elif kind == "link":
        m = re.search(r"(?m)^    ElseIf et = #CYW43_EV_LINK\n"
                      r"(?:^.*\n)*?^      If \(ef & #CYW43_EV_LINK_UP_FLAG\)"
                      r" = 0\n^        down = 1\n^      EndIf", text)
        if not m:
            raise SystemExit("a64_wifistay_check: the LINK-down arm is no "
                             "longer where the mutation expects it in "
                             "WifiDrainEvents - fix this gate.")
        text = text[:m.start()] + PRE_FIX_DRAIN_LINK + text[m.end():]
    else:
        raise SystemExit("unknown mutation %r" % kind)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")


def mutate_hwlink(dest):
    """A copy of hw_link.pi4 with HwLinkNoteRx back to winding the
    round-trip clock for a frame that merely ARRIVED."""
    text = HWLINK.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"(?ms)^Procedure HwLinkNoteRx\(kind\.i, r\.i\).*?"
                  r"^EndProcedure", text)
    if not m:
        raise SystemExit("a64_wifistay_check: HwLinkNoteRx is no longer a "
                         "procedure in hw_link.pi4 - the mutation cannot "
                         "reach the code, so the gate refuses to pass.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text[:m.start()] + PRE_FIX_NOTE_RX + text[m.end():],
                    encoding="utf-8")


# =====================================================================
#  THE SCRIPT
# =====================================================================
def bind_lease(s, at, tag):
    """The radio takes its address through the REAL WifiAdoptAddress."""
    at[tag + "_dhcp"] = s.add(20, LEASE_IP, MASK, GW_IP,
                              label=tag + " the radio adopts its address")


def wire_reads(s, at, key, n=4):
    """Read the first n frames off the captured wire.

    A PUMP TURN CAN SEND MORE THAN ONE FRAME, and once the console has a
    peer it sends the board's own log lines as datagrams too - so the
    supplicant's reply is not reliably frame zero.  The gate reads
    several and picks the EAPOL one rather than assuming an order that
    depends on how chatty the board happened to be.
    """
    for i in range(n):
        at["%s%d" % (key, i)] = s.add(7, a=i, label="%s frame %d" % (key, i))


def pick_eapol(R, key, n=4):
    """The one frame on the wire that is an EAPOL-Key frame."""
    for i in range(n):
        b = R("%s%d" % (key, i)).blob
        if len(b) >= 14 and b[12:14] == bytes([0x88, 0x8E]):
            return b
    return b""


def build_script(hs, wrap):
    s = Script()
    at = {}

    from a64_wpa2sup_check import RSN_IE

    # ---- a live association, built the way the board builds one -----
    s.add(1, blob=RADIO_MAC, label="reset")
    at["begin"] = s.add(14, blob=hs.pmk + RADIO_MAC + AP_MAC + hs.snonce
                        + RSN_IE, label="Wpa2SupBegin")
    at["m1"] = s.add(15, blob=hs.m1(), label="join message 1 in")
    at["m3"] = s.add(15, blob=hs.m3(wrap), label="join message 3 in")
    at["arm"] = s.add(16, label="the session is armed")
    s.add(2, a=1, b=1, label="keyed")
    bind_lease(s, at, "A")
    at["A_arm"] = s.add(4, label="the console arms")
    s.add(24, label="clear the wire")

    # ---- CASE 1: a GROUP KEY REKEY --------------------------------
    s.add(9, a=50, label="tick")
    s.add(5, blob=hs.gm1(wrap), label="the group rekey arrives")
    at["G_pump"] = s.add(6, label="one pump turn")
    at["G_count"] = s.add(12, label="the rekey counters")
    at["G_key"] = s.add(13, label="the key the radio was given")
    wire_reads(s, at, "G_wire")
    at["G_lease"] = s.add(19, label="the address after the rekey")
    s.add(24, label="clear the wire")
    # ... and the console still answers, which is the whole point.
    s.add(9, a=50, label="tick")
    s.add(5, blob=console_datagram(TYPED), label="a datagram after the rekey")
    at["G_pump2"] = s.add(6, label="pump")
    at["G_ring"] = s.add(8, label="the keystroke ring after the rekey")
    at["G_tick"] = s.add(10, label="the health tick after the rekey")

    # ---- CASE 2: a PAIRWISE (PTK) REKEY ---------------------------
    s.add(24, label="clear the wire")
    s.add(9, a=50, label="tick")
    s.add(5, blob=hs.rk_m1(), label="PTK rekey message 1")
    at["P_pump1"] = s.add(6, label="pump")
    wire_reads(s, at, "P_m2")
    s.add(24, label="clear the wire")
    s.add(9, a=50, label="tick")
    s.add(5, blob=hs.rk_m3(wrap), label="PTK rekey message 3")
    at["P_pump2"] = s.add(6, label="pump")
    wire_reads(s, at, "P_m4")
    at["P_count"] = s.add(12, label="the rekey counters")
    at["P_key"] = s.add(13, label="the key the radio was given")
    at["P_tick"] = s.add(10, label="the health tick after the PTK rekey")

    # ---- CASE 6: A REKEY WITH THE CONSOLE NOT ARMED ---------------
    s.add(1, blob=RADIO_MAC, label="reset")
    s.add(14, blob=hs.pmk + RADIO_MAC + AP_MAC + hs.snonce + RSN_IE,
          label="begin")
    s.add(15, blob=hs.m1(), label="message 1")
    s.add(15, blob=hs.m3(wrap), label="message 3")
    s.add(16, label="armed")
    s.add(2, a=1, b=1, label="keyed, and NOT addressed")
    at["N_armed"] = s.add(4, label="the console cannot arm - no address")
    s.add(9, a=50, label="tick")
    s.add(5, blob=hs.gm1(wrap, replay=hs.replay_g), label="the rekey arrives")
    at["N_tick"] = s.add(10, label="one health tick, nothing else")
    at["N_count"] = s.add(12, label="was the rekey serviced")
    wire_reads(s, at, "N_wire")

    # ---- CASE 4: A FIRMWARE DEAUTH --------------------------------
    s.add(1, blob=RADIO_MAC, label="reset")
    s.add(2, a=1, b=1, label="keyed")
    bind_lease(s, at, "D")
    s.add(4, label="arm")
    s.add(24, label="clear the wire")
    s.add(11, a=EV_DEAUTH_IND, c=16, label="the AP deauthenticates, reason 16")
    at["X_tick"] = s.add(10, label="the tick that must reconnect")
    at["X_count"] = s.add(18, label="the deauth counter")

    # ---- CASE 5: A FIRMWARE LINK-DOWN -----------------------------
    s.add(1, blob=RADIO_MAC, label="reset")
    s.add(2, a=1, b=1, label="keyed")
    bind_lease(s, at, "K")
    s.add(4, label="arm")
    s.add(11, a=EV_LINK, d=0, label="LINK with the up bit CLEAR")
    at["K_tick"] = s.add(10, label="the tick that must reconnect")
    at["K_count"] = s.add(18, label="the deauth counter")

    # ---- CASE 7: INBOUND TRAFFIC DURING A TX-ONLY DEATH -----------
    # The host keeps knocking.  Every datagram arriving used to wind the
    # round-trip clock, so the backstop never fired.  Here the ONLY
    # thing that never comes back is the keepalive's ARP reply.
    s.add(1, blob=RADIO_MAC, label="reset")
    s.add(2, a=1, b=1, label="keyed")
    bind_lease(s, at, "T")
    s.add(4, label="arm")
    at["T_link"] = s.add(25, a=2, label="the radio is the link")
    at["T_seed"] = s.add(10, label="the tick that seeds the keepalive clock")
    for k in range(4):
        s.add(9, a=21000, label="21 s")
        s.add(5, blob=console_datagram(b"are you there" + bytes([10])),
              label="the host knocks %d" % k)
        # THROUGH THE REAL SEAM. LinkPumpNet -> NetInput -> HwLinkNoteRx,
        # which is where an arriving datagram used to be counted as proof
        # that our own transmissions were landing.
        at["T_seam%d" % k] = s.add(26, label="LinkPumpNet %d" % k)
        at["T_tick%d" % k] = s.add(10, label="tick %d" % k)
    at["T_end"] = s.add(18, label="the round-trip clock at the end")
    at["T_rejoin"] = s.add(10, label="the state after")

    return s, at


# =====================================================================
#  GRADING
# =====================================================================
def expect(cond, msg, fails):
    if not cond:
        fails.append(msg)


def hexdiff(got, want):
    return ("      got  %s\n      want %s"
            % (got[:64].hex(), want[:64].hex()))


def be16(b, off):
    return (b[off] << 8) | b[off + 1]


def grade_group_m2(frame, hs, fails, tag="1"):
    """Group message 2, field by field, from IEEE 802.11 12.7.7 and not
    from the library."""
    if len(frame) < 113:
        fails.append("%s. group message 2 is %d bytes, shorter than an "
                     "EAPOL-Key frame with no key data" % (tag, len(frame)))
        return
    expect(frame[0:6] == AP_MAC,
           "%s. group message 2 is not addressed to the access point\n%s"
           % (tag, hexdiff(frame[0:6], AP_MAC)), fails)
    expect(frame[6:12] == RADIO_MAC,
           "%s. group message 2 does not come from the radio" % tag, fails)
    expect(frame[12:14] == b"\x88\x8e",
           "%s. group message 2 is not ethertype 0x888E" % tag, fails)
    expect(frame[15] == 3, "%s. not an EAPOL-Key frame (802.1X type %d)"
           % (tag, frame[15]), fails)
    expect(frame[18] == 2, "%s. descriptor type is %d, not 2 (RSN)"
           % (tag, frame[18]), fails)
    ki = be16(frame, 19)
    expect(ki & 0x0008 == 0,
           "%s. the PAIRWISE bit is SET in group message 2 (key-info $%04X) "
           "- this is a group handshake and the access point will not "
           "accept it" % (tag, ki), fails)
    expect(ki & 0x0100 != 0,
           "%s. the MIC bit is clear in group message 2 (key-info $%04X)"
           % (tag, ki), fails)
    expect(ki & 0x0200 != 0,
           "%s. the SECURE bit is clear in group message 2 (key-info $%04X)"
           % (tag, ki), fails)
    expect(be16(frame, 21) == 0,
           "%s. the Key Length field is %d, not 0 - wpa_supplicant writes 0 "
           "for RSN and some access points reject the echo"
           % (tag, be16(frame, 21)), fails)
    expect(frame[23:31] == hs.replay_g,
           "%s. the replay counter is not the one the access point sent\n%s"
           % (tag, hexdiff(frame[23:31], hs.replay_g)), fails)
    expect(be16(frame, 111) == 0,
           "%s. group message 2 carries %d bytes of key data and should "
           "carry none" % (tag, be16(frame, 111)), fails)
    from a64_wpa2sup_check import check_mic
    expect(check_mic(bytearray(frame), hs.kck),
           "%s. the MIC on group message 2 does not verify under an "
           "independently derived KCK" % tag, fails)


def check(res, console, hs, at, fails, mutation=None):
    def R(k):
        return res[at[k]]

    text = console.decode("latin-1")

    # ---- the association was really built -------------------------
    if mutation is None:
        expect(R("m1").r == WPA2SUP_SENT_M2,
               "the join four-way did not produce message 2 (code %d) - "
               "nothing downstream of it proves anything" % R("m1").r, fails)
        expect(R("m3").r == WPA2SUP_SENT_M4,
               "the join four-way did not produce message 4 (code %d)"
               % R("m3").r, fails)
        expect(R("A_dhcp").r == 1 and (R("A_dhcp").e1 & 0xFFFFFFFF) == LEASE_IP,
               "the radio did not take the address %s (r=%d ip=%08X)"
               % ("192.168.1.25", R("A_dhcp").r, R("A_dhcp").e1 & 0xFFFFFFFF),
               fails)
        expect(R("A_dhcp").e2 == NET_ADDR_LEASE,
               "the radio's address is recorded with source %d, and an "
               "address the radio adopts from its lease is #NET_ADDR_LEASE "
               "(%d). `net` reports it from that record"
               % (R("A_dhcp").e2, NET_ADDR_LEASE), fails)
        expect(R("A_arm").r == 1,
               "the console did not arm after the bind, so every case below "
               "is measuring the wrong thing", fails)

    # ---- CASE 1: the group rekey ----------------------------------
    if mutation is None:
        expect(R("G_count").r == 1,
               "1. the GROUP rekey was not serviced (grpKeyed=%d, errors=%d)"
               % (R("G_count").r, R("G_count").e2), fails)
        expect(R("G_count").e2 == 0,
               "1. the group rekey reported %d EAPOL errors"
               % R("G_count").e2, fails)
        expect(R("G_key").r == hs.key_id2,
               "1. the new GTK went in at key index %d, the access point "
               "said %d - a group key at the wrong index decrypts nothing"
               % (R("G_key").r, hs.key_id2), fails)
        expect(R("G_key").e1 == len(hs.gtk2),
               "1. the new GTK is %d bytes, the access point sent %d"
               % (R("G_key").e1, len(hs.gtk2)), fails)
        expect(R("G_key").e2 == 0,
               "1. the group key was installed with a unicast address - a "
               "station's group key takes none (brcmf sets no `ea` and "
               "flags = BRCMF_PRIMARY_KEY)", fails)
        got_gtk = R("G_key").blob[:R("G_key").e1]
        expect(got_gtk == hs.gtk2,
               "1. the installed GTK is not the one the access point "
               "wrapped\n%s" % hexdiff(got_gtk, hs.gtk2), fails)
        got_rsc = R("G_key").blob[R("G_key").e1:R("G_key").e1 + 6]
        expect(got_rsc == hs.rsc2[:6],
               "1. the group key's receive sequence counter was not carried "
               "across, so the access point's first broadcast under the new "
               "key is dropped as a replay\n%s"
               % hexdiff(got_rsc, hs.rsc2[:6]), fails)
        grade_group_m2(pick_eapol(R, "G_wire"), hs, fails, "1")
        expect((R("G_lease").e2 & 0xFFFFFFFF) == LEASE_IP,
               "1. the address changed across a group rekey", fails)
        expect(R("G_ring").blob == TYPED,
               "1. the console stopped answering after the rekey: the "
               "keystroke ring holds %r, not %r"
               % (R("G_ring").blob, TYPED), fails)
        expect(R("G_tick").r == 0,
               "1. the board re-associated across a group rekey "
               "(%d re-associations). A rekey is not permission to drop "
               "the link" % R("G_tick").r, fails)

        # ---- CASE 2: the PTK rekey --------------------------------
        m2 = pick_eapol(R, "P_m2")
        expect(len(m2) >= 113 and (be16(m2, 19) & 0x0108) == 0x0108,
               "2. the PTK rekey did not put a pairwise message 2 with a MIC "
               "on the wire (%d bytes, key-info $%04X, head %s)"
               % (len(m2), be16(m2, 19) if len(m2) >= 21 else 0,
                  m2[:24].hex()), fails)
        m4 = pick_eapol(R, "P_m4")
        expect(len(m4) >= 113 and (be16(m4, 19) & 0x0108) == 0x0108,
               "2. the PTK rekey did not put message 4 on the wire "
               "(%d bytes, key-info $%04X)"
               % (len(m4), be16(m4, 19) if len(m4) >= 21 else 0), fails)
        from a64_wpa2sup_check import check_mic
        expect(len(m4) >= 113 and check_mic(bytearray(m4), hs.kck2),
               "2. message 4's MIC does not verify under the NEW KCK, so the "
               "board and the access point did not derive the same PTK",
               fails)
        expect(R("P_count").e1 == 1,
               "2. the PAIRWISE rekey was not completed (ptkKeyed=%d, "
               "errors=%d)" % (R("P_count").e1, R("P_count").e2), fails)
        expect(R("P_tick").r == 0,
               "2. the board re-associated across a PTK rekey (%d)"
               % R("P_tick").r, fails)

    # ---- CASE 6: a rekey with no console --------------------------
    if mutation in (None, "pump"):
        expect(R("N_armed").r == 0,
               "6. the console armed with no address, so this case is not "
               "testing what it says it is", fails)
        serviced = R("N_count").r >= 1
        if mutation == "pump":
            expect(not serviced,
                   "NEGATIVE CONTROL (pump): the rekey was serviced anyway "
                   "with WifiRadioPump reduced to the event drain. The "
                   "mutation did not reach the code, so the positive run is "
                   "not evidence", fails)
        else:
            expect(serviced,
                   "6. THE REKEY WAS NEVER READ. With the wireless console "
                   "not armed and no network command ever run, nothing in "
                   "the monitor consumes a frame from the radio - which is "
                   "exactly the board of 2026-09-06, whose rekey line "
                   "printed during the manual re-join half an hour later",
                   fails)
            grade_group_m2(pick_eapol(R, "N_wire"), hs, fails, "6")

    # ---- CASES 4 and 5: the backstop acts, and says so ------------
    if mutation is None:
        expect(R("X_count").e2 >= 1,
               "4. a DEAUTH_IND was not counted as a teardown", fails)
        expect("the radio reports DEAUTH_IND" in text,
               "4. the backstop did not name the event on the console. "
               "The standing rule: when the backstop acts it says so on "
               "every console", fails)
        expect("reason 16" in text,
               "4. the console does not carry the access point's own reason "
               "code (16 = Group Key Handshake timeout)", fails)
        expect("starting cooperative re-association" in text,
               "4. the backstop did not start re-association: a teardown "
               "must reach WifiRecoveryStart, which says so on the console",
               fails)
        expect(R("X_tick").e1 == 1,
               "4. the failed re-association was not left pending, so "
               "nothing would ever retry it", fails)

    if mutation in (None, "link"):
        acted = R("K_count").e2 >= 1
        if mutation == "link":
            expect(not acted,
                   "NEGATIVE CONTROL (link): a LINK-down was treated as a "
                   "teardown anyway with that arm removed. The mutation did "
                   "not reach the code", fails)
        else:
            expect(acted,
                   "5. a LINK event with the up bit CLEAR was not treated as "
                   "a teardown. That is brcmf_is_linkdown's canonical case - "
                   "what the firmware sends when it loses the beacon - and "
                   "it was being recorded and ignored", fails)
            expect("the radio reports LINK" in text,
                   "5. the backstop did not announce the LINK-down", fails)
            # Cases 4, 5 and 7 each start one re-association.
            expect(text.count("starting cooperative re-association") >= 3,
                   "5. the LINK-down did not start a re-association (%d "
                   "announcements over cases 4, 5 and 7)"
                   % text.count("starting cooperative re-association"), fails)

    # ---- CASE 7: the detector is not muted by inbound traffic -----
    if mutation == "notrx":
        # HwLinkNoteRx reverted to winding the clock for a frame that
        # merely arrived.  The four datagrams the host sends must now
        # hold the backstop off, and the detector must go silent.
        moved = R("T_seam0").e1 != R("T_seam3").e1
        expect(moved,
               "NEGATIVE CONTROL (notrx): the round-trip clock did NOT move "
               "even with HwLinkNoteRx winding on an arrival. The mutation "
               "did not reach the code, so the positive run is not evidence",
               fails)
        expect("nothing sent out is" not in text,
               "NEGATIVE CONTROL (notrx): the detector fired anyway. The "
               "mutation did not reach the code", fails)
    if mutation is None:
        expect(R("T_link").e1 == 1,
               "7. the radio was not selected as the link, so LinkPumpNet "
               "returned at its first line and nothing was measured", fails)
        # THE CLOCK MUST NOT HAVE MOVED. Four datagrams arrived through
        # the real seam over 84 seconds and not one of them is evidence
        # that anything this board sent got out.
        expect(R("T_seam0").e1 == R("T_seam3").e1,
               "7. the round-trip clock MOVED while only inbound traffic "
               "arrived: %d at the first datagram, %d at the fourth. An "
               "arriving datagram proves the receive half and nothing else, "
               "and counting it is what held the backstop off for half an "
               "hour on 2026-09-06"
               % (R("T_seam0").e1, R("T_seam3").e1), fails)
        expect("nothing sent out is" in text,
               "7. THE DETECTOR NEVER FIRED. Four keepalives went out with "
               "no answer over 84 seconds while the host kept sending - and "
               "every arriving datagram used to wind the round-trip clock, "
               "which is why the board answered 0 of 20 pings for half an "
               "hour on 2026-09-06 with the health check silent", fails)
        expect("the backstop" in text,
               "7. the detector fired without saying it was reconnecting",
               fails)


# =====================================================================
args_dump_console = [False]


def one_run(lib_include, tag, mutation, hs, wrap, fails,
            hwlink_include="RaspberryPi4/Board/hw_link.pi4"):
    work = WORK / tag
    src = work / "wifistayharness.pi4"
    img = work / "wifistaycheck.img"
    write_harness(lib_include, hwlink_include, src)
    build(src, img)
    s, at = build_script(hs, wrap)
    mem, console, steps = run(img, s.finish())
    if b"wifistayharness done" not in console:
        fails.append("%s: the harness did not run to the end:\n%s"
                     % (tag, console.decode("latin-1")[-2000:]))
        return 0
    # WIFISTAY_CONSOLE=1 dumps what the board printed. Kept because a
    # failure in this gate is almost always answered by reading the
    # board's own narration of what it did.
    if os.environ.get("WIFISTAY_CONSOLE") or args_dump_console[0]:
        sys.stderr.write("---- console (" + tag + ") ----" + chr(10)
                         + console.decode("latin-1") + chr(10))
    res = read_results(mem, s.labels)
    if len(res) != len(s.labels):
        fails.append("%s: %d results for %d script records"
                     % (tag, len(res), len(s.labels)))
        return steps
    check(res, console, hs, at, fails, mutation)
    return steps


def resolve_compiler(requested):
    """Resolve the PureMetal compiler the way tools/build.py does."""
    sys.path.insert(0, str(ROOT / "tools"))
    import build as anvil_build  # noqa: E402
    return anvil_build.find_compiler(requested)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"),
                    help="path of PureMetalForge.exe (or set PMF_COMPILER); "
                         "it is run with --compile")
    ap.add_argument("--target", default="pi4", choices=["pi4"])
    ap.add_argument("--no-mutate", action="store_true",
                    help="skip the negative controls (development only)")
    ap.add_argument("--dump-console", action="store_true",
                    help="print what the board printed, per run")
    args = ap.parse_args()
    globals()["PMFC"] = resolve_compiler(args.compiler)
    args_dump_console[0] = args.dump_console

    print("a64_wifistay_check: grading THE LINK STAYS JOINED")
    print("  library under test : %s" % LIB)
    print("  supplicant         : %s"
          % (ROOT / "RaspberryPi4" / "Lib" / "wpa2sup.pi4"))
    print("  over a scripted radio - no CYW43 firmware, no SDIO, no air")

    wrap = have_wrap()
    if wrap is None:
        raise SystemExit(
            "a64_wifistay_check: this gate needs AES key wrap to build a "
            "group rekey the way an access point does. Install the "
            "`cryptography` package, or run it where it is available - a "
            "rekey case with the key data in the clear is not a rekey.")

    hs = Handshake(seed=0x5741, gtk_len=16, key_id=2)

    # THE FIXTURE'S ENTROPY IS DETERMINISTIC AND THE AUTHENTICATOR USES
    # THE SAME BYTES. wifi_ServiceEapol asks EntropyBytes for a fresh
    # SNonce before it hands a PTK rekey to the supplicant, exactly as
    # wpa_supplicant does; the harness's EntropyBytes fills FX_SNONCE, so
    # the rekey PTK is re-derived here from those bytes and message 4's
    # MIC can be checked against it. A gate that could not predict the
    # nonce could not check the key it produced.
    from a64_wpa2sup_check import derive_ptk
    hs.snonce2 = FX_SNONCE
    hs.ptk2 = derive_ptk(hs.pmk, hs.aa, hs.spa, hs.anonce2, hs.snonce2)
    hs.kck2 = hs.ptk2[0:16]
    hs.kek2 = hs.ptk2[16:32]
    hs.tk2 = hs.ptk2[32:48]

    global RADIO_MAC, AP_MAC
    RADIO_MAC = hs.spa
    AP_MAC = hs.aa

    fails = []
    steps = one_run("RaspberryPi4/Lib/wifi.pi4", "fixed", None, hs, wrap,
                    fails)

    if not args.no_mutate and not fails:
        for kind in ("pump", "link"):
            mut = WORK / ("mutant_" + kind) / ("wifi_prefix_%s.pi4" % kind)
            mutate_lib(kind, mut)
            rel = mut.relative_to(ROOT).as_posix()
            one_run(rel, "mutant_" + kind, kind, hs, wrap, fails)
        mut = WORK / "mutant_notrx" / "hw_link_prefix_noterx.pi4"
        mutate_hwlink(mut)
        one_run("RaspberryPi4/Lib/wifi.pi4", "mutant_notrx", "notrx", hs,
                wrap, fails, mut.relative_to(ROOT).as_posix())

    if fails:
        print("\na64_wifistay_check: FAIL - %d" % len(fails))
        for f in fails:
            print("  * %s" % f)
        return 1

    cases = 6
    print("\na64_wifistay_check: PASS - %d cases on %s, %s model instructions"
          % (cases, args.target, "{:,}".format(steps)))
    print("  with 3 negative controls (WifiRadioPump, the LINK-down arm,")
    print("  and HwLinkNoteRx winding on an arrival)")
    print("""
WHAT IS NOT COVERED
  The air. No frame here is transmitted, nothing associates, and the
  firmware's own behaviour - power save, roaming, the SDIO bus - is the
  board's to prove, not this gate's. What IS covered is every decision
  the host makes when a rekey or a teardown arrives. Lease renewal is
  the common DHCP client's, graded by RaspberryPi4/Tests/dhcp_emitted_gate.pi4.""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

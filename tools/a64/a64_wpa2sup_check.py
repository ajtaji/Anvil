#!/usr/bin/env python3
"""Executable gate for RaspberryPi4/Lib/wpa2sup.pi4 - the WPA2-PSK
four-way handshake, run in the host.

WHY THIS FILE IS WRITTEN THE WAY IT IS

  THE ORACLE PLAYS THE AUTHENTICATOR, IT DOES NOT COMPARE CONSTANTS.
  A gate that fed the library a captured message 1 and compared its
  message 2 against a captured one would only ever test the case it
  was captured from.  This one implements the OTHER HALF of the
  exchange in Python - PRF-384 over hmac/hashlib, the MIC, the AES key
  wrap - and drives a complete handshake.  It builds message 1 from a
  nonce it chose, VERIFIES the message 2 that comes back the way
  hostapd would (MIC under a KCK it derived independently, the SNonce
  echoed, the RSN element byte-identical to the one the station said it
  would send), builds message 3 with a GTK wrapped under the KEK, and
  then checks the message 4 and the two keys the library produced.

  So the pass condition is "two independent implementations agreed on a
  384-bit key derivation" and not "these bytes match those bytes".

  THE PYTHON SIDE IS INDEPENDENT WHERE IT MATTERS.  Its SHA-1 and HMAC
  come from the standard library, not from this tree, so a defect
  shared between sha1.pi4 and hmacsha1.pi4 cannot hide.  Its AES key
  wrap comes from `cryptography` (OpenSSL) when that is installed, and
  a64_keywrap_check.py already validates that package against RFC 3394
  before trusting it; when it is absent this gate says so and skips the
  cases that need it rather than falling back to keywrap.pi4, which is
  the code under test's own dependency and therefore no oracle at all.

  THE REFUSALS ARE TESTED HARDER THAN THE SUCCESS PATH, because every
  one of them is a security property and every one of them fails
  SILENTLY if it is wrong:

    * a message 3 with a corrupted MIC must be refused.  This is the
      only thing that authenticates the access point.  A supplicant
      that installed the keys anyway would associate happily with any
      radio broadcasting the right name.
    * a message 3 whose wrapped key data has been altered must be
      refused, and RFC 3394's integrity check is what catches it.
    * a REPLAYED message 3 - same replay counter as the one already
      accepted - must be refused.
    * key descriptor version 1 (HMAC-MD5 and RC4) must be refused by
      name, not mis-verified.  Its MIC is a different function; a
      library that computed HMAC-SHA1 over a version 1 frame would
      reject it as a MIC failure and send somebody to check a
      passphrase that was never wrong.
    * a handshake with no SNonce set must refuse to derive.  A zero
      SNonce produces a link that works perfectly and a session key
      anyone who captured the handshake can reproduce, which is the
      worst failure shape there is.
    * a message 3 with no GTK key data element must be refused rather
      than installing a zero-length group key.

  THE PRF IS TESTED ON ITS OWN as well as inside the handshake, at
  three output lengths, because 384 bits is exactly three SHA-1 blocks
  and a truncation defect would be invisible at that length.  512 bits
  is four blocks with the last one cut, and 160 is one block exactly.

WHAT THIS GATE DOES NOT SAY

  * That any of this works against a real access point.  It cannot:
    there is no radio in the model and no authenticator on the other
    side of it.  The only evidence for that is a bench log.
  * Anything about timing or constant-time behaviour.
  * Anything about the key INSTALLATION path - Cyw43SetWsecKey builds a
    164-byte struct and sends it over SDIO, which this model has no
    way to observe.  a64_sdio_check.py is where that would go.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import os
import pathlib
import struct
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
# THE TREE UNDER TEST IS THE ONE THIS SCRIPT LIVES IN. A root pinned into
# the file made this gate build a DIFFERENT working copy, with that copy's
# compiler, and print the answer as this tree's. Override deliberately with
# PMF_REPO; the tree actually read is printed below so a wrong one is visible.
ROOT = pathlib.Path(__file__).resolve().parents[2]
print("[gate] tree under test: %s" % ROOT, file=sys.stderr)
sys.path.insert(0, str(HERE))
from a64_interp import A64, attach_symbols  # noqa: E402
from a64_target import (TARGETS, apply_target,  # noqa: E402
                        patch_harness)

PMFC = os.environ.get("PMF_COMPILER") or "PureMetalForge.exe"  # rebound from --compiler
# Every compile resolves includes from THIS tree only.
BUILD_ENV = dict(os.environ, PMF_ROOT=str(ROOT))
LIB = ROOT / "RaspberryPi4" / "Lib" / "wpa2sup.pi4"
WORK = ROOT / "_work"

LOAD = 0x00400000
LOADER_SP = 0x00100000
LOADER_LR = 0xDEADBEE0
STACK = 0x03000000

# The board this run builds for.  Rebound by apply_target() from the
# --target flag before anything else runs; see tools/a64/a64_target.py.
# Two AArch64 boards now share these libraries - the Pi 4's A72 and the
# Arduino UNO Q's A53 - and they share the FILES, not copies of them, so
# this gate grades both rather than being duplicated.
TFLAG = "pi4"
TARGET_NAME = "pi4"
TARGET_WHAT = TARGETS["pi4"]["what"]
CONSOLE_INCLUDE = TARGETS["pi4"]["console"]


UART_LO = 0xFE201000
UART_HI = 0xFE201048
UART_DR = 0xFE201000

H_SCRIPT = 0x06000000
H_RESULT = 0x0A000000

STEP_LIMIT = 40_000_000_000

# SCRIPT RECORD: six 32-bit words then the payload, padded to 8.
REC_HEAD = 24
# RESULT RECORD: the verdict, three lengths, the two keys, the RSC and
# whatever frame the library staged.
#  THE THREE MUST AGREE WITH THE HARNESS'S OWN 792 AND 800, and the
#  first version of this file had 288/360/368 against the harness's
#  792/800.  Every record after the first read the sentinel and the
#  gate reported -1515870811 - which is $A5A5A5A5 - thirty-five times.
#  A stride mismatch always looks like a total library failure, so:
#  RES_STRIDE is what the harness adds to q, and RES_DATA is what it
#  fills with the sentinel.
RES_TX = 720
RES_DATA = 792
RES_STRIDE = 8 + RES_DATA
SENTINEL = 0xA5

OP_END = 0
OP_PRF = 1
OP_BEGIN = 2
OP_NONCE = 3
OP_FRAME = 4
OP_ARM = 5          # Wpa2SupSessionArm - hold the keys for a rekey
OP_SFRAME = 6       # Wpa2SupHandleSession - one frame during a session

PKE = b"Pairwise key expansion"

# The RSN element the station offers.  Identical to pi4WifiKey.pi4's,
# and it is a published shape rather than a secret: id 48, version 1,
# CCMP group, one CCMP pairwise, one PSK AKM, no capabilities.
RSN_IE = bytes.fromhex("3014010000" "0fac04" "0100" "000fac04"
                       "0100" "000fac02" "0000".replace(" ", ""))
assert len(RSN_IE) == 22, len(RSN_IE)


# =====================================================================
#  THE HARNESS
# =====================================================================
HARNESS = r'''
; ======================================================================
;  wpaharness.pi4 - GENERATED BY tools/a64/a64_wpa2sup_check.py.
;  NOT A SOURCE FILE. DO NOT EDIT.
;
;  Every PMK, nonce and frame it runs is handed to it in memory by the
;  gate and every one of them is a made-up test value. There is no
;  credential in this file and none can reach it: it has no filesystem,
;  no settings and no radio.
; ======================================================================
XIncludeFile "RaspberryPi4/Lib/uart.pi4"
XIncludeFile "RaspberryPi4/Lib/sha1.pi4"
XIncludeFile "RaspberryPi4/Lib/hmacsha1.pi4"
XIncludeFile "RaspberryPi4/Lib/aes.pi4"
XIncludeFile "RaspberryPi4/Lib/keywrap.pi4"
XIncludeFile "__LIB__"

#H_SCRIPT = $06000000
#H_RESULT = $0A000000
#H_FRAME  = $0C000000

Procedure.i Main()
  Define p.i
  Define q.i
  Define op.i
  Define n0.i
  Define n1.i
  Define n2.i
  Define n3.i
  Define total.i
  Define i.i
  Define r.i
  Define pay.i

  p = #H_SCRIPT
  q = #H_RESULT

  Repeat
    op    = PeekN(p)
    n0    = PeekL(p + 4)
    n1    = PeekL(p + 8)
    n2    = PeekL(p + 12)
    n3    = PeekL(p + 16)
    total = PeekL(p + 20)
    If op = 0
      Break
    EndIf
    pay = p + 24

    i = 0
    While i < 792
      PokeB(q + 8 + i, $A5)
      i = i + 1
    Wend

    r = 0
    If op = 1
      ; PRF. n0 = key length, n1 = label length, n2 = data length,
      ; n3 = wanted output length. The output lands where the result
      ; record's frame field would be, which is idle for this op.
      r = Wpa2Prf(pay, n0, pay + n0, n1, pay + n0 + n1, n2, q + 8 + 72, n3)
    ElseIf op = 2
      ; BEGIN. pmk 32, ourMac 6, apMac 6, then n0 bytes of RSN element.
      r = Wpa2SupBegin(pay, pay + 32, pay + 38, pay + 44, n0)
    ElseIf op = 3
      ; The SNonce, 32 bytes.
      Wpa2SupSetSnonce(pay)
      r = 1
    ElseIf op = 5
      ; ARM THE SESSION HOLD - keep the keys for a mid-session rekey.
      Wpa2SupSessionArm()
      r = 1
    ElseIf op = 4 Or op = 6
      ; ONE RECEIVED FRAME. Copied out of the script into a separate
      ; buffer first, because the handler WRITES to the frame it is
      ; given - it zeroes the MIC field to compute over it and puts it
      ; back - and a script the harness walks by length must not be
      ; written through. op 4 is the join four-way (Wpa2SupHandle); op 6
      ; is the mid-session path (Wpa2SupHandleSession).
      i = 0
      While i < n0
        PokeB(#H_FRAME + i, PeekA(pay + i) & 255)
        i = i + 1
      Wend
      If op = 4
        r = Wpa2SupHandle(#H_FRAME, n0)
      Else
        r = Wpa2SupHandleSession(#H_FRAME, n0)
      EndIf
      ; The staged reply, if any.
      PokeN(q + 4, Wpa2SupTxLen())
      i = 0
      While i < Wpa2SupTxLen()
        PokeB(q + 8 + 72 + i, PeekA(Wpa2SupTxPtr() + i) & 255)
        i = i + 1
      Wend
      ; The results a caller installs. Written on EVERY frame, not just
      ; a successful message 3, so that a library which filled them in
      ; too early would be caught.
      PokeL(q + 8 + 0, Wpa2SupGtkLen())
      PokeL(q + 8 + 4, Wpa2SupGtkIndex())
      i = 0
      While i < 16
        PokeB(q + 8 + 8 + i, PeekA(Wpa2SupTk() + i) & 255)
        i = i + 1
      Wend
      i = 0
      While i < 32
        PokeB(q + 8 + 24 + i, PeekA(Wpa2SupGtk() + i) & 255)
        i = i + 1
      Wend
      i = 0
      While i < 8
        PokeB(q + 8 + 56 + i, PeekA(Wpa2SupGtkRsc() + i) & 255)
        i = i + 1
      Wend
      PokeL(q + 8 + 64, Wpa2SupState())
      PokeL(q + 8 + 68, Wpa2SupLastError())
    EndIf
    PokeN(q, r)

    p = p + 24 + (((total + 7) / 8) * 8)
    q = q + 800
  ForEver

  UartWriteStr("wpaharness done")
  ProcedureReturn 0
EndProcedure
'''


# =====================================================================
#  THE ORACLE - the authenticator's half, in Python
# =====================================================================
def prf(key: bytes, label: bytes, data: bytes, nbytes: int) -> bytes:
    out = b""
    i = 0
    while len(out) < nbytes:
        out += hmac.new(key, label + b"\x00" + data + bytes([i]),
                        hashlib.sha1).digest()
        i += 1
    return out[:nbytes]


def derive_ptk(pmk: bytes, aa: bytes, spa: bytes,
               anonce: bytes, snonce: bytes) -> bytes:
    b = (min(aa, spa) + max(aa, spa)
         + min(anonce, snonce) + max(anonce, snonce))
    return prf(pmk, PKE, b, 48)


def eapol(da: bytes, sa: bytes, ver: int, key_info: int, key_len: int,
          replay: bytes, nonce: bytes, rsc: bytes, mic: bytes,
          kd: bytes) -> bytearray:
    body = (bytes([2])
            + struct.pack(">H", key_info)
            + struct.pack(">H", key_len)
            + replay
            + nonce
            + b"\x00" * 16          # EAPOL Key IV
            + rsc
            + b"\x00" * 8           # Key ID, reserved
            + mic
            + struct.pack(">H", len(kd))
            + kd)
    assert len(body) == 95 + len(kd)
    return bytearray(da + sa + b"\x88\x8e"
                     + bytes([ver, 3]) + struct.pack(">H", len(body))
                     + body)


def set_mic(frame: bytearray, kck: bytes) -> None:
    for i in range(16):
        frame[95 + i] = 0
    mac = hmac.new(kck, bytes(frame[14:]), hashlib.sha1).digest()[:16]
    frame[95:111] = mac


def check_mic(frame: bytes, kck: bytes) -> bool:
    f = bytearray(frame)
    got = bytes(f[95:111])
    for i in range(16):
        f[95 + i] = 0
    want = hmac.new(kck, bytes(f[14:]), hashlib.sha1).digest()[:16]
    return hmac.compare_digest(got, want)


def gtk_kde(gtk: bytes, key_id: int, tx: int = 0) -> bytes:
    body = bytes([(key_id & 3) | ((tx & 1) << 2), 0]) + gtk
    return bytes([0xDD, 4 + len(body), 0x00, 0x0F, 0xAC, 0x01]) + body


def pad_kd(kd: bytes) -> bytes:
    if len(kd) % 8 == 0 and len(kd) >= 16:
        return kd
    out = kd + b"\xdd"
    while len(out) % 8:
        out += b"\x00"
    while len(out) < 16:
        out += b"\x00" * 8
    return out


def have_wrap():
    try:
        from cryptography.hazmat.primitives.keywrap import aes_key_wrap
        return aes_key_wrap
    except Exception:
        return None


# =====================================================================
#  SCRIPT AND RESULT PLUMBING
# =====================================================================
class Script:
    def __init__(self) -> None:
        self.buf = bytearray()
        self.labels: list[str] = []
        self.want: list = []

    def add(self, op: int, label: str, payload: bytes,
            n0: int = 0, n1: int = 0, n2: int = 0, n3: int = 0,
            want=None) -> None:
        self.labels.append(label)
        self.want.append(want)
        total = len(payload)
        self.buf += struct.pack("<Iiiiii", op, n0, n1, n2, n3, total)
        pad = (total + 7) // 8 * 8
        self.buf += payload + b"\x00" * (pad - total)

    def done(self) -> bytes:
        return bytes(self.buf) + struct.pack("<Iiiiii", OP_END, 0, 0, 0, 0, 0)

    def __len__(self) -> int:
        return len(self.labels)


class Result:
    """One decoded result record."""

    def __init__(self, blob: bytes) -> None:
        self.ret = struct.unpack("<i", blob[0:4])[0]
        self.txlen = struct.unpack("<i", blob[4:8])[0]
        d = blob[8:]
        self.gtklen = struct.unpack("<i", d[0:4])[0]
        self.gtkindex = struct.unpack("<i", d[4:8])[0]
        self.tk = d[8:24]
        self.gtk = d[24:56]
        self.rsc = d[56:64]
        self.state = struct.unpack("<i", d[64:68])[0]
        self.lasterr = struct.unpack("<i", d[68:72])[0]
        self.frame = d[72:72 + RES_TX]
        self.tx = self.frame[:max(0, self.txlen)]


def build(harness: pathlib.Path, img: pathlib.Path) -> None:
    WORK.mkdir(exist_ok=True)
    harness.write_text(patch_harness(HARNESS.replace(
        "__LIB__", "Anvil/Net/wpa2sup.pbi"), globals()),
                       encoding="utf-8")
    cmd = [str(PMFC), "--compile", str(harness), "-t", TFLAG,
           "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
           "--entry-returns", "-o", str(img)]
    r = subprocess.run(cmd, cwd=ROOT, env=BUILD_ENV, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout:
        raise SystemExit("build failed:\n" + r.stdout)


def run(img: pathlib.Path, script: bytes, count: int):
    blob = img.read_bytes()
    cpu = A64()
    mem = cpu.memory
    for i, b in enumerate(blob):
        mem[LOAD + i] = b
    for i, b in enumerate(script):
        mem[H_SCRIPT + i] = b
    cpu.pc = LOAD
    cpu.sp = LOADER_SP
    cpu.x[30] = LOADER_LR
    attach_symbols(cpu, img, LOAD)

    uart = bytearray()

    def load(addr, size):
        cpu.align_guard(addr, size, False)
        if UART_LO <= addr <= UART_HI:
            return 0
        return sum(mem.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr, value, size):
        cpu.align_guard(addr, size, True)
        if UART_LO <= addr <= UART_HI:
            if addr == UART_DR:
                uart.append(value & 0xFF)
            return
        for i in range(size):
            mem[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store

    steps = 0
    while cpu.pc != LOADER_LR:
        cpu.step()
        steps += 1
        if steps > STEP_LIMIT:
            raise SystemExit("the harness never returned (%d steps)\n%s"
                             % (steps, uart.decode("latin-1")))
    if b"wpaharness done" not in uart:
        raise SystemExit("the harness returned without finishing:\n"
                         + uart.decode("latin-1"))

    out = []
    for i in range(count):
        a = H_RESULT + i * RES_STRIDE
        out.append(Result(bytes(mem.get(a + j, 0)
                                for j in range(RES_STRIDE))))
    return out, steps


# =====================================================================
#  THE CASES
# =====================================================================
def case_prf(s: Script) -> None:
    """Wpa2Prf on its own, at three output lengths.

    384 bits is exactly three SHA-1 blocks, so a truncation defect
    cannot show there.  512 asks for four blocks with the last one cut
    to 4 bytes; 160 is one block with nothing to cut."""
    rng = 0x5EED
    for keylen, lab, datalen, outlen in ((32, PKE, 76, 48),
                                         (32, PKE, 76, 64),
                                         (32, PKE, 76, 20),
                                         (16, b"x", 1, 20),
                                         (64, b"Group key expansion", 20, 32)):
        key = bytes((rng * (i + 3) + 11) & 0xFF for i in range(keylen))
        data = bytes((rng * (i + 7) + 29) & 0xFF for i in range(datalen))
        rng = (rng * 1103515245 + 12345) & 0xFFFFFFFF
        want = prf(key, lab, data, outlen)
        s.add(OP_PRF, "PRF key=%d label=%d data=%d out=%d"
              % (keylen, len(lab), datalen, outlen),
              key + lab + data, keylen, len(lab), datalen, outlen,
              want=("prf", outlen, want))


class Handshake:
    """One synthetic association, from the authenticator's side."""

    def __init__(self, seed: int, gtk_len: int = 16, key_id: int = 2) -> None:
        r = hashlib.sha256(b"wpa2sup-gate-%d" % seed).digest()
        r2 = hashlib.sha256(r).digest()
        self.pmk = r
        self.aa = bytes([0x02]) + r2[1:6]        # locally administered
        self.spa = bytes([0x06]) + r2[7:12]
        self.anonce = hashlib.sha256(r2 + b"a").digest()
        self.snonce = hashlib.sha256(r2 + b"s").digest()
        self.gtk = hashlib.sha256(r2 + b"g").digest()[:gtk_len]
        self.key_id = key_id
        self.rsc = bytes([0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0, 0])
        self.replay1 = bytes(7) + bytes([1])
        self.replay3 = bytes(7) + bytes([2])
        self.ptk = derive_ptk(self.pmk, self.aa, self.spa,
                              self.anonce, self.snonce)
        self.kck = self.ptk[0:16]
        self.kek = self.ptk[16:32]
        self.tk = self.ptk[32:48]
        # A mid-session GROUP rekey: a NEW GTK under the same KEK, a
        # counter past message 3's, and its own RSC and key id.
        self.gtk2 = hashlib.sha256(r2 + b"g2").digest()[:16]
        self.key_id2 = 1
        self.rsc2 = bytes([0xaa, 0xbb, 0xcc, 0xdd, 0xee, 0xff, 0, 0])
        self.replay_g = bytes(7) + bytes([3])
        # A mid-session PTK rekey: a fresh ANonce/SNonce and the PTK they
        # derive, with counters past the group rekey's.
        self.anonce2 = hashlib.sha256(self.anonce + b"re").digest()
        self.snonce2 = hashlib.sha256(self.snonce + b"re").digest()
        self.replay_r1 = bytes(7) + bytes([4])
        self.replay_r3 = bytes(7) + bytes([5])
        self.ptk2 = derive_ptk(self.pmk, self.aa, self.spa,
                               self.anonce2, self.snonce2)
        self.kck2 = self.ptk2[0:16]
        self.kek2 = self.ptk2[16:32]
        self.tk2 = self.ptk2[32:48]

    def gm1(self, wrap, replay: bytes | None = None) -> bytearray:
        """The authenticator's GROUP message 1: a new GTK wrapped under
        the KEK, group (pairwise clear), Ack, MIC, Secure, Encrypted."""
        kd = gtk_kde(self.gtk2, self.key_id2)
        wrapped = wrap(self.kek, pad_kd(kd))
        info = 2 | 0x0080 | 0x0100 | 0x0200 | 0x1000
        f = eapol(self.spa, self.aa, 2, info, 0,
                  replay or self.replay_g, bytes(32), self.rsc2,
                  bytes(16), wrapped)
        set_mic(f, self.kck)
        return f

    def rk_m1(self, replay: bytes | None = None) -> bytearray:
        """PTK rekey message 1: pairwise, Ack, no MIC, a fresh ANonce."""
        info = 2 | 0x0008 | 0x0080
        return eapol(self.spa, self.aa, 2, info, 16,
                     replay or self.replay_r1, self.anonce2, bytes(8),
                     bytes(16), b"")

    def rk_m3(self, wrap, replay: bytes | None = None) -> bytearray:
        """PTK rekey message 3, MIC'd under the NEW KCK."""
        kd = RSN_IE + gtk_kde(self.gtk2, self.key_id2)
        wrapped = wrap(self.kek2, pad_kd(kd))
        info = 2 | 0x0008 | 0x0040 | 0x0080 | 0x0100 | 0x0200 | 0x1000
        f = eapol(self.spa, self.aa, 2, info, 16,
                  replay or self.replay_r3, self.anonce2, self.rsc2,
                  bytes(16), wrapped)
        set_mic(f, self.kck2)
        return f

    def m1(self, ver: int = 2, kdv: int = 2) -> bytearray:
        info = kdv | 0x0008 | 0x0080        # pairwise | ack
        return eapol(self.spa, self.aa, ver, info, 16, self.replay1,
                     self.anonce, bytes(8), bytes(16), b"")

    def m3(self, wrap, ver: int = 2, replay: bytes | None = None,
           include_gtk: bool = True) -> bytearray:
        kd = RSN_IE + (gtk_kde(self.gtk, self.key_id) if include_gtk else b"")
        wrapped = wrap(self.kek, pad_kd(kd))
        info = 2 | 0x0008 | 0x0040 | 0x0080 | 0x0100 | 0x0200 | 0x1000
        f = eapol(self.spa, self.aa, ver, info, 16,
                  replay or self.replay3, self.anonce, self.rsc,
                  bytes(16), wrapped)
        set_mic(f, self.kck)
        return f


def add_handshake(s: Script, hs: Handshake, wrap, tag: str) -> None:
    s.add(OP_BEGIN, tag + "  begin",
          hs.pmk + hs.spa + hs.aa + RSN_IE, len(RSN_IE), want=("ret", 1))
    s.add(OP_NONCE, tag + "  snonce", hs.snonce, want=("ret", 1))

    m1 = bytes(hs.m1())
    s.add(OP_FRAME, tag + "  message 1 in, message 2 out",
          m1, len(m1), want=("m2", hs))

    m3 = bytes(hs.m3(wrap))
    s.add(OP_FRAME, tag + "  message 3 in, message 4 out",
          m3, len(m3), want=("m4", hs))


def verify_m2(hs: Handshake, res: Result) -> list[str]:
    bad = []
    if res.ret != 1:
        return ["      returned %d, expected 1 (message 2 staged)" % res.ret]
    f = res.tx
    if len(f) != 113 + len(RSN_IE):
        bad.append("      message 2 is %d bytes, expected %d"
                   % (len(f), 113 + len(RSN_IE)))
        return bad
    if f[0:6] != hs.aa:
        bad.append("      addressed to %s, expected the authenticator %s"
                   % (f[0:6].hex(), hs.aa.hex()))
    if f[6:12] != hs.spa:
        bad.append("      sent from %s, expected %s"
                   % (f[6:12].hex(), hs.spa.hex()))
    if f[12:14] != b"\x88\x8e":
        bad.append("      ethertype %s, expected 888e" % f[12:14].hex())
    if f[15] != 3:
        bad.append("      802.1X type %d, expected 3" % f[15])
    if struct.unpack(">H", f[16:18])[0] != 95 + len(RSN_IE):
        bad.append("      802.1X length %d, expected %d"
                   % (struct.unpack(">H", f[16:18])[0], 95 + len(RSN_IE)))
    if f[18] != 2:
        bad.append("      descriptor type %d, expected 2 (RSN)" % f[18])
    info = struct.unpack(">H", f[19:21])[0]
    if info != (2 | 0x0008 | 0x0100):
        bad.append("      key info $%04X, expected $010A "
                   "(version 2 | pairwise | MIC)" % info)
    if struct.unpack(">H", f[21:23])[0] != 0:
        bad.append("      key length %d, expected 0 - that is the RSN rule "
                   "and it is NOT the 16 message 1 carries"
                   % struct.unpack(">H", f[21:23])[0])
    if f[23:31] != hs.replay1:
        bad.append("      replay counter %s, expected message 1's %s"
                   % (f[23:31].hex(), hs.replay1.hex()))
    if f[31:63] != hs.snonce:
        bad.append("      SNonce is not the one that was set")
    if struct.unpack(">H", f[111:113])[0] != len(RSN_IE):
        bad.append("      key data length %d, expected %d"
                   % (struct.unpack(">H", f[111:113])[0], len(RSN_IE)))
    if f[113:113 + len(RSN_IE)] != RSN_IE:
        bad.append("      the RSN element in message 2 is not the one the "
                   "association request carried - hostapd deauthenticates "
                   "on exactly this")
    if not check_mic(f, hs.kck):
        bad.append("      THE MIC DOES NOT VERIFY against a KCK derived "
                   "independently. The PTK derivation disagrees.")
    return bad


def verify_m4(hs: Handshake, res: Result) -> list[str]:
    bad = []
    if res.ret != 2:
        return ["      returned %d (%s), expected 2 (message 4 staged)"
                % (res.ret, res.lasterr)]
    f = res.tx
    if len(f) != 113:
        bad.append("      message 4 is %d bytes, expected 113" % len(f))
        return bad
    info = struct.unpack(">H", f[19:21])[0]
    if info != (2 | 0x0008 | 0x0100 | 0x0200):
        bad.append("      key info $%04X, expected $030A "
                   "(version 2 | pairwise | MIC | secure)" % info)
    if struct.unpack(">H", f[21:23])[0] != 0:
        bad.append("      key length is not 0")
    if f[23:31] != hs.replay3:
        bad.append("      replay counter %s, expected message 3's %s"
                   % (f[23:31].hex(), hs.replay3.hex()))
    if struct.unpack(">H", f[111:113])[0] != 0:
        bad.append("      message 4 carries key data and must not")
    if not check_mic(f, hs.kck):
        bad.append("      THE MIC ON MESSAGE 4 DOES NOT VERIFY")
    if res.tk != hs.tk:
        bad.append("      the TK is not PTK[32..47]")
    if res.gtklen != len(hs.gtk):
        bad.append("      GTK length %d, expected %d"
                   % (res.gtklen, len(hs.gtk)))
    elif res.gtk[:res.gtklen] != hs.gtk:
        bad.append("      the GTK does not match the one message 3 wrapped")
    if res.gtkindex != hs.key_id:
        bad.append("      GTK key id %d, expected %d"
                   % (res.gtkindex, hs.key_id))
    if res.rsc != hs.rsc:
        bad.append("      the key RSC was not carried through - broadcast "
                   "traffic would be dropped as replay, silently")
    return bad


def verify_g2(hs: Handshake, res: Result) -> list[str]:
    """Group message 2, and the new GTK the library installed."""
    bad = []
    if res.ret != 3:
        return ["      returned %d (%s), expected 3 (group message 2 staged)"
                % (res.ret, res.lasterr)]
    f = res.tx
    if len(f) != 113:
        bad.append("      group message 2 is %d bytes, expected 113" % len(f))
        return bad
    if f[0:6] != hs.aa:
        bad.append("      addressed to %s, expected the authenticator %s"
                   % (f[0:6].hex(), hs.aa.hex()))
    info = struct.unpack(">H", f[19:21])[0]
    if info != (2 | 0x0100 | 0x0200):
        bad.append("      key info $%04X, expected $0302 "
                   "(version 2 | MIC | secure, GROUP)" % info)
    if info & 0x0008:
        bad.append("      the PAIRWISE bit is set on a GROUP message 2 - "
                   "this is exactly the half-handling the join path refuses")
    if struct.unpack(">H", f[21:23])[0] != 0:
        bad.append("      key length is not 0")
    if f[23:31] != hs.replay_g:
        bad.append("      replay counter %s, expected group message 1's %s"
                   % (f[23:31].hex(), hs.replay_g.hex()))
    if struct.unpack(">H", f[111:113])[0] != 0:
        bad.append("      group message 2 carries key data and must not")
    if not check_mic(f, hs.kck):
        bad.append("      THE MIC ON GROUP MESSAGE 2 DOES NOT VERIFY")
    if res.gtklen != len(hs.gtk2):
        bad.append("      new GTK length %d, expected %d"
                   % (res.gtklen, len(hs.gtk2)))
    elif res.gtk[:res.gtklen] != hs.gtk2:
        bad.append("      the installed GTK is not the one the rekey wrapped")
    if res.gtkindex != hs.key_id2:
        bad.append("      new GTK key id %d, expected %d"
                   % (res.gtkindex, hs.key_id2))
    if res.rsc != hs.rsc2:
        bad.append("      the new key RSC was not carried through")
    return bad


def verify_m2_rk(hs: Handshake, res: Result) -> list[str]:
    """PTK rekey message 2: MIC under the NEW KCK, the new SNonce echoed."""
    bad = []
    if res.ret != 1:
        return ["      returned %d (%s), expected 1 (rekey message 2)"
                % (res.ret, res.lasterr)]
    f = res.tx
    if len(f) != 113 + len(RSN_IE):
        bad.append("      rekey message 2 is %d bytes, expected %d"
                   % (len(f), 113 + len(RSN_IE)))
        return bad
    info = struct.unpack(">H", f[19:21])[0]
    if info != (2 | 0x0008 | 0x0100):
        bad.append("      key info $%04X, expected $010A" % info)
    if f[23:31] != hs.replay_r1:
        bad.append("      replay counter %s, expected the rekey's %s"
                   % (f[23:31].hex(), hs.replay_r1.hex()))
    if f[31:63] != hs.snonce2:
        bad.append("      the FRESH SNonce was not used in the rekey")
    if f[113:113 + len(RSN_IE)] != RSN_IE:
        bad.append("      the RSN element in rekey message 2 is wrong")
    if not check_mic(f, hs.kck2):
        bad.append("      rekey message 2's MIC does not verify against the "
                   "NEW KCK - the rekey PTK derivation disagrees")
    return bad


def verify_m4_rk(hs: Handshake, res: Result) -> list[str]:
    """PTK rekey message 4, and the freshly reinstalled pairwise key."""
    bad = []
    if res.ret != 2:
        return ["      returned %d (%s), expected 2 (rekey message 4)"
                % (res.ret, res.lasterr)]
    f = res.tx
    if len(f) != 113:
        bad.append("      rekey message 4 is %d bytes, expected 113" % len(f))
        return bad
    info = struct.unpack(">H", f[19:21])[0]
    if info != (2 | 0x0008 | 0x0100 | 0x0200):
        bad.append("      key info $%04X, expected $030A" % info)
    if f[23:31] != hs.replay_r3:
        bad.append("      replay counter %s, expected %s"
                   % (f[23:31].hex(), hs.replay_r3.hex()))
    if not check_mic(f, hs.kck2):
        bad.append("      rekey message 4's MIC does not verify")
    if res.tk != hs.tk2:
        bad.append("      the reinstalled TK is not the NEW PTK[32..47] - "
                   "the rekey installed a stale pairwise key")
    return bad


def check(img: pathlib.Path, s: Script, note: str) -> list[str]:
    if len(s) == 0:
        return []
    got, steps = run(img, s.done(), len(s))
    bad = []
    for i, label in enumerate(s.labels):
        want = s.want[i]
        res = got[i]
        rows: list[str] = []
        if want is None:
            pass
        elif want[0] == "ret":
            if res.ret != want[1]:
                rows.append("      returned %d, expected %d"
                            % (res.ret, want[1]))
        elif want[0] == "prf":
            n, expect = want[1], want[2]
            if res.ret != n:
                rows.append("      returned %d, expected %d" % (res.ret, n))
            elif res.frame[:n] != expect:
                k = 0
                while k < n and res.frame[k] == expect[k]:
                    k += 1
                rows.append("      first difference at byte %d\n"
                            "        expected %s\n        got      %s"
                            % (k, expect[k:k + 16].hex(),
                               res.frame[k:k + 16].hex()))
            elif res.frame[n] != SENTINEL:
                rows.append("      wrote past the %d bytes it was asked for"
                            % n)
        elif want[0] == "m2":
            rows = verify_m2(want[1], res)
        elif want[0] == "m4":
            rows = verify_m4(want[1], res)
        elif want[0] == "g2":
            rows = verify_g2(want[1], res)
        elif want[0] == "m2re":
            rows = verify_m2_rk(want[1], res)
        elif want[0] == "m4re":
            rows = verify_m4_rk(want[1], res)
        elif want[0] == "refuse":
            code, why = want[1], want[2]
            if res.ret != code:
                rows.append("      returned %d, expected %d - %s"
                            % (res.ret, code, why))
            elif res.txlen != 0 and code < 0:
                # A refusal that also staged a reply would send a frame
                # the caller thought was legitimate.
                pass
        if rows:
            bad.append("  " + label + "\n" + "\n".join(rows))
    print("  %-52s %4d vectors, %-9s %11d steps"
          % (note, len(s), "ALL PASS" if not bad else
             "%d FAILED" % len(bad), steps))
    return bad


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
    ap.add_argument("--target", choices=sorted(TARGETS),
                    default="pi4",
                    help="which AArch64 board's image contract "
                         "to build and grade against")
    ap.add_argument("--keep", action="store_true",
                    help="leave the generated harness in _work")
    args = ap.parse_args()
    globals()["PMFC"] = resolve_compiler(args.compiler)
    apply_target(globals(), args.target)
    # A GATE THAT DOES NOT SAY WHICH BOARD IT GRADED IS A RESULT
    # THAT CAN BE FILED AGAINST THE WRONG ONE.  Printed before any
    # work, so it is at the top of the transcript even on a failure.
    print("[gate] target %s - %s, image at $%08X, stack $%08X"
          % (TARGET_NAME, TARGET_WHAT, LOAD, STACK))

    print("a64_wpa2sup_check - the WPA2 four-way handshake, in the host")
    print("  library   %s" % LIB)
    wrap = have_wrap()
    if wrap is None:
        print("  ORACLE    `cryptography` is not installed. The PRF cases")
        print("            still run; every case that needs an AES key wrap")
        print("            is SKIPPED rather than run against keywrap.pi4,")
        print("            which is the code under test's own dependency.")
    else:
        print("  oracle    hashlib/hmac for SHA-1, `cryptography` for the")
        print("            RFC 3394 wrap (validated by a64_keywrap_check)")

    harness = WORK / "wpaharness.pi4"
    img = WORK / "wpaharness.img"
    build(harness, img)

    failures: list[str] = []

    s = Script()
    case_prf(s)
    failures += check(img, s, "PRF against hashlib")

    if wrap is not None:
        s = Script()
        for seed, gtklen, kid in ((1, 16, 1), (2, 16, 2), (3, 32, 3)):
            add_handshake(s, Handshake(seed, gtklen, kid), wrap,
                          "handshake %d (GTK %d, id %d)" % (seed, gtklen, kid))
        failures += check(img, s, "complete handshakes")

        # -------------------------------------------------------------
        #  THE REFUSALS. Each one is a security property.
        # -------------------------------------------------------------
        s = Script()

        hs = Handshake(11)
        s.add(OP_BEGIN, "bad MIC  begin", hs.pmk + hs.spa + hs.aa + RSN_IE,
              len(RSN_IE), want=("ret", 1))
        s.add(OP_NONCE, "bad MIC  snonce", hs.snonce, want=("ret", 1))
        m1 = bytes(hs.m1())
        s.add(OP_FRAME, "bad MIC  message 1", m1, len(m1), want=("m2", hs))
        f = bytearray(hs.m3(wrap))
        f[100] ^= 0x01
        s.add(OP_FRAME,
              "bad MIC  message 3 with one MIC bit flipped MUST be refused",
              bytes(f), len(f),
              want=("refuse", -5, "E_MIC. This is the ONLY thing that "
                                  "authenticates the access point."))

        hs = Handshake(12)
        s.add(OP_BEGIN, "bad wrap  begin", hs.pmk + hs.spa + hs.aa + RSN_IE,
              len(RSN_IE), want=("ret", 1))
        s.add(OP_NONCE, "bad wrap  snonce", hs.snonce, want=("ret", 1))
        m1 = bytes(hs.m1())
        s.add(OP_FRAME, "bad wrap  message 1", m1, len(m1), want=("m2", hs))
        f = bytearray(hs.m3(wrap))
        f[120] ^= 0x80          # inside the wrapped key data
        set_mic(f, hs.kck)      # ... and re-MIC it, so only the wrap fails
        s.add(OP_FRAME,
              "bad wrap  altered key data, MIC still good, MUST be refused",
              bytes(f), len(f),
              want=("refuse", -6, "E_UNWRAP. RFC 3394's integrity check."))

        hs = Handshake(13)
        s.add(OP_BEGIN, "replay  begin", hs.pmk + hs.spa + hs.aa + RSN_IE,
              len(RSN_IE), want=("ret", 1))
        s.add(OP_NONCE, "replay  snonce", hs.snonce, want=("ret", 1))
        m1 = bytes(hs.m1())
        s.add(OP_FRAME, "replay  message 1", m1, len(m1), want=("m2", hs))
        f = bytes(hs.m3(wrap, replay=hs.replay1))
        s.add(OP_FRAME,
              "replay  message 3 reusing message 1's counter MUST be refused",
              f, len(f),
              want=("refuse", -10, "E_REPLAY. The counter must advance."))

        hs = Handshake(14)
        s.add(OP_BEGIN, "no gtk  begin", hs.pmk + hs.spa + hs.aa + RSN_IE,
              len(RSN_IE), want=("ret", 1))
        s.add(OP_NONCE, "no gtk  snonce", hs.snonce, want=("ret", 1))
        m1 = bytes(hs.m1())
        s.add(OP_FRAME, "no gtk  message 1", m1, len(m1), want=("m2", hs))
        f = bytes(hs.m3(wrap, include_gtk=False))
        s.add(OP_FRAME,
              "no gtk  message 3 with no GTK element MUST be refused",
              f, len(f),
              want=("refuse", -7, "E_NOGTK. A zero group key installed "
                                  "silently is worse than a refusal."))

        hs = Handshake(15)
        s.add(OP_BEGIN, "kdv1  begin", hs.pmk + hs.spa + hs.aa + RSN_IE,
              len(RSN_IE), want=("ret", 1))
        s.add(OP_NONCE, "kdv1  snonce", hs.snonce, want=("ret", 1))
        f = bytes(hs.m1(kdv=1))
        s.add(OP_FRAME,
              "kdv1  key descriptor version 1 MUST be refused BY NAME",
              f, len(f),
              want=("refuse", -4, "E_KDV. Version 1 is HMAC-MD5 and RC4; "
                                  "verifying it as SHA-1 would report a "
                                  "MIC failure and blame the passphrase."))

        # A frame that is not EAPOL at all must be IGNORED, not refused:
        # the caller hands this every frame off the wire.
        arp = bytes(6) + bytes(6) + b"\x08\x06" + bytes(28)
        s.add(OP_FRAME, "an ARP frame must be ignored, not refused",
              arp, len(arp), want=("refuse", 0, "IGNORED"))

        failures += check(img, s, "refusals")

        # -------------------------------------------------------------
        #  NO SNonce. Begin, then message 1, with no nonce in between.
        # -------------------------------------------------------------
        s = Script()
        hs = Handshake(21)
        s.add(OP_BEGIN, "no nonce  begin", hs.pmk + hs.spa + hs.aa + RSN_IE,
              len(RSN_IE), want=("ret", 1))
        m1 = bytes(hs.m1())
        s.add(OP_FRAME,
              "no nonce  message 1 with no SNonce set MUST be refused",
              m1, len(m1),
              want=("refuse", -8, "E_NONONCE. A zero SNonce makes every "
                                  "session key reproducible from a capture "
                                  "and the link still works."))
        failures += check(img, s, "the SNonce is not optional")

        # -------------------------------------------------------------
        #  THE MID-SESSION REKEY - the cure for the TX-only death.
        #  Complete a four-way, ARM the session hold, then drive the
        #  rekeys the access point starts on its own. The oracle is the
        #  authenticator's half again, so a pass is two implementations
        #  agreeing - not a captured frame replayed.
        # -------------------------------------------------------------
        s = Script()
        hs = Handshake(31)
        add_handshake(s, hs, wrap, "group rekey  base four-way")
        s.add(OP_ARM, "group rekey  arm the session hold", b"",
              want=("ret", 1))
        gm = bytes(hs.gm1(wrap))
        s.add(OP_SFRAME,
              "group rekey  group message 1 in -> group message 2 out, GTK installed",
              gm, len(gm), want=("g2", hs))
        failures += check(img, s, "group-key rekey (was refused, now serviced)")

        s = Script()
        hs = Handshake(32)
        add_handshake(s, hs, wrap, "PTK rekey  base four-way")
        s.add(OP_ARM, "PTK rekey  arm the session hold", b"",
              want=("ret", 1))
        s.add(OP_NONCE, "PTK rekey  fresh SNonce", hs.snonce2,
              want=("ret", 1))
        m1r = bytes(hs.rk_m1())
        s.add(OP_SFRAME, "PTK rekey  message 1 in -> message 2 out",
              m1r, len(m1r), want=("m2re", hs))
        m3r = bytes(hs.rk_m3(wrap))
        s.add(OP_SFRAME,
              "PTK rekey  message 3 in -> message 4 out, pairwise key reinstalled",
              m3r, len(m3r), want=("m4re", hs))
        failures += check(img, s, "PTK rekey (fresh four-way mid-session)")

        # A group rekey with a REPLAYED counter (not past message 3's)
        # must be refused, the same security property as message 3's.
        s = Script()
        hs = Handshake(33)
        add_handshake(s, hs, wrap, "group replay  base four-way")
        s.add(OP_ARM, "group replay  arm", b"", want=("ret", 1))
        gmr = bytes(hs.gm1(wrap, replay=hs.replay3))
        s.add(OP_SFRAME,
              "group replay  group message 1 reusing message 3's counter MUST be refused",
              gmr, len(gmr),
              want=("refuse", -10, "E_REPLAY. A group rekey counter must "
                                   "advance past the four-way's."))
        # A group message 1 whose MIC is wrong must be refused - it is the
        # only thing that proves the frame came from our access point.
        hs = Handshake(34)
        add_handshake(s, hs, wrap, "group badmic  base four-way")
        s.add(OP_ARM, "group badmic  arm", b"", want=("ret", 1))
        gmb = bytearray(hs.gm1(wrap))
        gmb[100] ^= 0x01
        s.add(OP_SFRAME,
              "group badmic  group message 1 with a flipped MIC bit MUST be refused",
              bytes(gmb), len(gmb),
              want=("refuse", -5, "E_MIC. It authenticates the rekey."))
        failures += check(img, s, "group rekey refusals")

    print()
    if failures:
        print("FAILED - %d" % len(failures))
        for f in failures:
            print(f)
        return 1
    print("ALL PASS")
    print()
    print("  What this does NOT say: nothing here ran on silicon, and no")
    print("  access point was involved. The evidence for that is a bench")
    print("  log from a real Raspberry Pi 4 joining a real access point.")
    if not args.keep:
        for p in (harness,):
            try:
                os.unlink(p)
            except OSError:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

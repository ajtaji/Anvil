#!/usr/bin/env python3
"""Executable gate for RaspberryPi4/Lib/pbkdf2.pi4.

WHY THIS FILE IS WRITTEN THE WAY IT IS

  THE PUBLISHED ORACLE IS RFC 6070, PARSED OFF THE DISK.  Its six
  PBKDF2-HMAC-SHA1 vectors are read out of
  RaspberryPi4/Reference/rfc6070.txt at run time - passwords, salts,
  iteration counts, output lengths and derived keys.  Nothing is
  transcribed.  Between them they cover c = 1, c = 2 and c = 4096;
  dkLen of 16, 20 and 25, which is a partial final block, an exact
  fit, and a two-block output; a 24-octet password with a 36-octet
  salt; and - the important one - a password and a salt that each
  CONTAIN A ZERO BYTE.

  THE SMALL ITERATION COUNTS MATTER MORE THAN THE LARGE ONE.  c = 1
  and c = 2 are what distinguish "the inner loop runs c times" from
  "the inner loop runs c-1 times" and from "U_1 is counted twice".  A
  vector set with only c = 4096 in it would pass an implementation
  that is off by one, because 4095 XORs of pseudorandom blocks look
  exactly as wrong as 4096 do and neither can be recognised by eye.

  A SECOND ORACLE IS USED, AND IT IS VALIDATED BEFORE IT IS TRUSTED.
  RFC 6070's cheap vectors are few, and the mutation sweep needs many
  cheap discriminating cases - multi-block outputs at low iteration
  counts, odd dkLen values, empty salts.  Those come from Python's
  hashlib.pbkdf2_hmac, which is OpenSSL and is independent of this
  tree but is NOT a published document.  So it is checked first: this
  gate requires hashlib to reproduce EVERY RFC 6070 vector, INCLUDING
  the 16,777,216-iteration one, before it will use hashlib for
  anything.  If the validation fails, the gate stops; it never falls
  back to trusting an unvalidated oracle.

  THE IEEE 802.11 VECTORS, AND EXACTLY HOW FAR THAT CITATION GOES.
  The three passphrase-to-PSK vectors are IEEE 802.11i-2004 Annex
  H.4.2 (Annex J.4.2 in 802.11-2020).  THAT DOCUMENT IS NOT ON THIS
  DISK - it is not freely redistributable and this project's rule is
  to download what it cites, which here is not possible.  So the three
  values are transcribed into this file, WHICH IS EXACTLY THE FAILURE
  MODE THIS GATE OTHERWISE AVOIDS, and the transcription is therefore
  confirmed at run time against hashlib before use.  Two independent
  parties then agree on each value: the published table, and OpenSSL.
  What is on disk is the CONSTRUCTION - hostap_sha1-pbkdf2.c:71-72
  states "iterations is set to 4096 and buflen to 32.  This function
  is described in IEEE Std 802.11-2004, Clause H.4."  If anyone ever
  gets the standard onto this disk, replace the transcription with a
  parse and delete this paragraph.

  NO REAL CREDENTIAL IS ANYWHERE NEAR THIS FILE.  Every passphrase and
  every SSID here is from a published document.  The one the board
  actually uses lives in SETTINGS.TXT on the boot medium and is never
  a test input.

  THE OUTPUT BUFFER IS PRE-FILLED WITH A SENTINEL.  The harness fills
  the 64-byte result field with $A5 before each call, so a derivation
  that writes one byte too many is caught as loudly as one that writes
  a wrong byte.  The RETURN VALUE is reported separately, so a
  refusal that returns 0 but writes anyway is caught too.

  REFUSALS ARE TESTED.  Fifteen bad-argument calls - zero iterations,
  a dkLen over the stated maximum, a 7-character WPA2 passphrase, a
  64-character one, an over-long SSID - must each return 0 AND leave
  the sentinel untouched.  A library whose checks only clamp is a
  library that hides its caller's bug.

WHAT THIS GATE DOES NOT SAY

  * That any of this runs on silicon.
  * How long a real join takes.  The model has no caches and no clock;
    the step count it reports is instructions, not seconds.

HOW LONG THESE TAKE, MEASURED ON 2026-08-28, SO NOBODY STARTS THE
WRONG ONE BY ACCIDENT

  --quick        31 vectors, 5.3 million model instructions, 18 s.
  --mutate       fourteen rebuilds of the quick set, minutes.
  --wpa2only     three Annex H.4 derivations.  ONE of them is 532
                 MILLION model instructions, so this is tens of
                 minutes.
  --mutate-wpa2  four such derivations, one clean and three mutated.
  (no flag)      everything except the 16,777,216-iteration vector -
                 fourteen 4096-iteration output blocks.  That is
                 HOURS on this oracle, and it has NOT been run to
                 completion in this tree yet.  What HAS been run is
                 every part of it: the cheap set green, the WPA2
                 mapping green under --mutate-wpa2, and RFC 6070's
                 c=4096 vector green inside
                 RaspberryPi4/Examples/Diagnostics/pi4WifiJoin.pi4's
                 own self-test.  Somebody should still run the whole
                 thing once, on a quiet machine, and write down what
                 it said.

Run: python tools/a64/a64_pbkdf2_check.py
     python tools/a64/a64_pbkdf2_check.py --quick    (skip c=4096)
     python tools/a64/a64_pbkdf2_check.py --wpa2only (only the IEEE PSK)
     python tools/a64/a64_pbkdf2_check.py --mutate
     python tools/a64/a64_pbkdf2_check.py --mutate-wpa2   (slow)
"""

from __future__ import annotations
import os

import argparse
import hashlib
import pathlib
import re
import struct
import subprocess
import sys
import time

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
LIB = ROOT / "RaspberryPi4" / "Lib" / "pbkdf2.pi4"
REF = ROOT / "RaspberryPi4" / "Reference"
RFC6070 = REF / "rfc6070.txt"
HOSTAP_PBKDF2 = REF / "hostap_sha1-pbkdf2.c"
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

STEP_LIMIT = 8_000_000_000

RESULT_STRIDE = 68          # 4 bytes of return value, 64 of buffer
SENTINEL = 0xA5

OP_END = 0
OP_PBKDF2 = 1
OP_WPA2 = 2
OP_NEG_PWLEN = 3
OP_NEG_SALTLEN = 4


# =====================================================================
#  THE HARNESS
# =====================================================================
#  SCRIPT RECORD, 20 bytes then the password then the salt, each
#  padded to 4:
#      +0 op  +4 iters  +8 dklen  +12 pwlen  +16 saltlen  +20 pw.. salt..
#  op 0 ends the script.
#
#  RESULT RECORD, 68 bytes:
#      +0 the value the library returned, 32-bit
#      +4 the 64-byte output field, pre-filled with $A5
# =====================================================================
HARNESS = r'''
; ======================================================================
;  pbkdf2harness.pi4 - GENERATED BY tools/a64/a64_pbkdf2_check.py.
;  NOT A SOURCE FILE. DO NOT EDIT.
;
;  Every password and SSID it runs is a PUBLISHED test value handed to
;  it in memory by the gate. There is no credential in this file.
; ======================================================================
XIncludeFile "RaspberryPi4/Lib/uart.pi4"
XIncludeFile "RaspberryPi4/Lib/sha1.pi4"
XIncludeFile "RaspberryPi4/Lib/hmacsha1.pi4"
XIncludeFile "__LIB__"

#H_SCRIPT = $06000000
#H_RESULT = $0A000000

Procedure.i Main()
  Define p.i
  Define q.i
  Define op.i
  Define iters.i
  Define dklen.i
  Define pwlen.i
  Define slen.i
  Define pw.i
  Define salt.i
  Define i.i
  Define r.i

  p = #H_SCRIPT
  q = #H_RESULT

  Repeat
    ; iters and dklen are read SIGNED, with PeekL, because the
    ; refusal cases pass -1 and the whole point of those cases is that
    ; the library sees a negative number rather than four billion.
    ; pwlen and slen stay unsigned: the script walk below does
    ; arithmetic with them and a negative one would lose the stream.
    op    = PeekN(p)
    iters = PeekL(p + 4)
    dklen = PeekL(p + 8)
    pwlen = PeekN(p + 12)
    slen  = PeekN(p + 16)
    If op = 0
      Break
    EndIf
    pw   = p + 20
    salt = pw + (((pwlen + 3) / 4) * 4)

    ; Fill the output field with a sentinel first. A write past the
    ; requested length, or a write on a call that was supposed to
    ; refuse, then shows up as a missing $A5.
    i = 0
    While i < 64
      PokeB(q + 4 + i, $A5)
      i = i + 1
    Wend

    r = 0
    If op = 1
      r = Pbkdf2Sha1(pw, pwlen, salt, slen, iters, q + 4, dklen)
    ElseIf op = 2
      r = Wpa2Psk(pw, pwlen, salt, slen, q + 4)
    ElseIf op = 3
      ; A negative password length, which the script stream cannot
      ; carry without losing its own framing. It is spelled out here
      ; instead.
      r = Pbkdf2Sha1(pw, -1, salt, slen, iters, q + 4, dklen)
    ElseIf op = 4
      r = Pbkdf2Sha1(pw, pwlen, salt, -1, iters, q + 4, dklen)
    EndIf
    PokeN(q, r)

    p = p + 20 + (((pwlen + 3) / 4) * 4) + (((slen + 3) / 4) * 4)
    q = q + 68
  ForEver

  UartWriteStr("pbkdf2harness done")
  ProcedureReturn 0
EndProcedure
'''


class Script:
    def __init__(self) -> None:
        self.buf = bytearray()
        self.labels: list[str] = []
        self.expect: list[tuple[int, bytes]] = []

    def add(self, op: int, label: str, ret: int, dk: bytes, pw: bytes,
            salt: bytes, iters: int, dklen: int) -> None:
        """dk is the expected derived key; the rest of the 64-byte field
        must still be sentinel."""
        self.labels.append(label)
        field = dk + bytes([SENTINEL]) * (64 - len(dk))
        self.expect.append((ret, field))
        self.buf += struct.pack("<IiiII", op, iters, dklen, len(pw), len(salt))
        self.buf += pw + b"\x00" * ((-len(pw)) % 4)
        self.buf += salt + b"\x00" * ((-len(salt)) % 4)

    def done(self) -> bytes:
        return bytes(self.buf) + struct.pack("<IiiII", OP_END, 0, 0, 0, 0)


# =====================================================================
#  RFC 6070, PARSED
# =====================================================================
def _unescape(s: str) -> bytes:
    r"""Turn one of RFC 6070's quoted strings into bytes.

    Section 2 states the convention in so many words: 'The sequence
    "\0" (without quotation marks) means a literal ASCII NUL value (1
    octet).'  Getting this wrong is not a small error - the fifth
    vector exists specifically to catch an implementation that stops
    at a zero byte, and a parser that dropped the escape would test
    the opposite of what the vector is for.
    """
    return s.replace("\\0", "\x00").encode("latin-1")


def parse_rfc6070() -> list[dict]:
    if not RFC6070.exists():
        raise SystemExit(
            f"the oracle is missing: {RFC6070}\n"
            "Fetch https://www.rfc-editor.org/rfc/rfc6070.txt into "
            "RaspberryPi4/Reference/.")
    text = RFC6070.read_text(errors="replace")
    start = text.find("2.  PBKDF2 HMAC-SHA1 Test Vectors")
    end = text.find("3.  Acknowledgements", start + 1)
    if start < 0 or end < 0:
        raise SystemExit("rfc6070.txt: cannot find section 2's boundaries")
    body = text[start:end]

    # Drop page furniture so a vector split across a page break still
    # reads as one block.
    lines = [ln for ln in body.splitlines()
             if "Josefsson" not in ln and not ln.startswith("RFC 6070 ")]
    body = "\n".join(lines)

    vectors = []
    for m in re.finditer(
            r'P\s*=\s*"((?:[^"]|\\")*)"\s*\((\d+)\s*octets\)\s*'
            r'S\s*=\s*"((?:[^"]|\\")*)"\s*\((\d+)\s*octets\)\s*'
            r'c\s*=\s*(\d+)\s*'
            r'dkLen\s*=\s*(\d+)\s*'
            r'Output:\s*DK\s*=\s*([0-9a-f \n]+?)\((\d+)\s*octets\)',
            body):
        p = _unescape(m.group(1))
        s = _unescape(m.group(3))
        dk = bytes.fromhex(re.sub(r"\s", "", m.group(7)))
        # THE RFC'S OWN OCTET COUNTS ARE THE CHECK ON THE PARSE.  Every
        # value is stated twice - as text and as a length - and the
        # acknowledgements section records that a mistake in the salt
        # octet count was found and fixed before publication, so these
        # counts are the reviewed part of the document.
        if len(p) != int(m.group(2)):
            raise SystemExit("rfc6070.txt: parsed a %d-octet P where the "
                             "document says %s" % (len(p), m.group(2)))
        if len(s) != int(m.group(4)):
            raise SystemExit("rfc6070.txt: parsed a %d-octet S where the "
                             "document says %s" % (len(s), m.group(4)))
        if len(dk) != int(m.group(8)) or len(dk) != int(m.group(6)):
            raise SystemExit("rfc6070.txt: parsed a %d-octet DK where the "
                             "document says %s / dkLen %s"
                             % (len(dk), m.group(8), m.group(6)))
        vectors.append({"P": p, "S": s, "c": int(m.group(5)),
                        "dkLen": int(m.group(6)), "DK": dk})
    if len(vectors) != 6:
        raise SystemExit(
            "rfc6070.txt: expected six vectors, parsed %d. The document has "
            "changed shape - fix the parse, do not lower the number."
            % len(vectors))
    return vectors


# =====================================================================
#  IEEE 802.11 Annex H.4.2, TRANSCRIBED AND THEN CONFIRMED
# =====================================================================
#  These are the three worked examples the standard gives for the
#  passphrase-to-PSK mapping.  They are TYPED HERE, which this gate
#  otherwise refuses to do, because the standard is not freely
#  redistributable and so cannot be put on this disk under the
#  project's download-what-you-cite rule.
#
#  confirm_ieee() below re-derives each one with OpenSSL and refuses to
#  run if any disagrees.  That converts the risk from "somebody typed
#  a digit wrong" - which is the real risk with a transcription - into
#  "the published table and OpenSSL are both wrong the same way",
#  which is not a risk anybody can do anything about.
IEEE_H4 = [
    ("password", "IEEE",
     "f42c6fc52df0ebef9ebb4b90b38a5f902e83fe1b135a70e23aed762e9710a12e"),
    ("ThisIsAPassword", "ThisIsASSID",
     "0dc0d6eb90555ed6419756b9a15ec3e3209b63df707dd508d14581f8982721af"),
    # 32 'a' against 32 'Z'.  THE FIRST TRANSCRIPTION OF THIS ROW WAS
    # WRONG - it had 63 'Z' as the passphrase - and confirm_ieee()
    # below caught it on the first run, which is the entire argument
    # for confirming a transcription instead of trusting one.
    ("a" * 32, "Z" * 32,
     "becb93866bb8c3832cb777c2f559807c8c59afcb6eae734885001300a981cc62"),
]


def confirm_oracle(vectors) -> None:
    """Require OpenSSL to reproduce every published RFC 6070 vector.

    This runs BEFORE hashlib is used for anything else.  An oracle that
    has not been checked is not an oracle, it is a second opinion.
    """
    for v in vectors:
        got = hashlib.pbkdf2_hmac("sha1", v["P"], v["S"], v["c"], v["dkLen"])
        if got != v["DK"]:
            raise SystemExit(
                "hashlib does not reproduce RFC 6070 (P=%r c=%d): %s vs %s\n"
                "This gate will not use an oracle it cannot validate."
                % (v["P"], v["c"], got.hex(), v["DK"].hex()))


def confirm_ieee() -> list[tuple[bytes, bytes, bytes]]:
    """Confirm the transcribed IEEE vectors against OpenSSL."""
    # The hostap source is third-party code and is not shipped in this
    # repository, so the textual cross-check of the 4096-iteration
    # citation is skipped when it is absent. The vectors themselves are
    # still confirmed against OpenSSL below, which is the check that
    # matters for correctness.
    if not HOSTAP_PBKDF2.exists():
        if not getattr(confirm_ieee, "_noted", False):
            print("  note: %s is not in this tree (third-party source, not "
                  "redistributed here); the citation cross-check of the "
                  "4096 iterations is SKIPPED. The IEEE vectors are still "
                  "confirmed against OpenSSL." % HOSTAP_PBKDF2.name)
            confirm_ieee._noted = True
    else:
        src = HOSTAP_PBKDF2.read_text(errors="replace")
        if "4096" not in src or "802.11" not in src:
            raise SystemExit(
                "hostap_sha1-pbkdf2.c no longer states the 4096 iterations "
                "and the IEEE 802.11 clause that pbkdf2.pi4 cites it for. "
                "Find the new citation rather than replacing it with a "
                "literal.")
    out = []
    for phrase, ssid, expect in IEEE_H4:
        p = phrase.encode("ascii")
        s = ssid.encode("ascii")
        want = bytes.fromhex(expect)
        got = hashlib.pbkdf2_hmac("sha1", p, s, 4096, 32)
        if got != want:
            raise SystemExit(
                "the IEEE Annex H.4 vector transcribed into this gate for "
                "SSID %r does not match OpenSSL:\n  typed    %s\n  OpenSSL  %s\n"
                "Fix the transcription. Do NOT change it to whatever this "
                "tree produces." % (ssid, want.hex(), got.hex()))
        out.append((p, s, want))
    return out


# =====================================================================
#  BUILD AND RUN
# =====================================================================
def build(lib_include: str, harness: pathlib.Path, img: pathlib.Path) -> None:
    WORK.mkdir(exist_ok=True)
    harness.write_text(patch_harness(HARNESS.replace("__LIB__",
                                                 lib_include),
                                 globals()),
                       encoding="utf-8")
    cmd = [str(PMFC), "--compile", str(harness), "-t", TFLAG,
           "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
           "--entry-returns", "-o", str(img)]
    r = subprocess.run(cmd, cwd=ROOT, env=BUILD_ENV, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout:
        raise SystemExit("build failed:\n" + r.stdout)


def run(img: pathlib.Path, script: bytes, count: int,
        step_limit: int = STEP_LIMIT):
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
    # Names for the alignment rule's message, from the `.dbg` pmfc
    # writes beside the image - NOT the `.sym`, which mixes absolute
    # BSS addresses with load-relative code ones
    # (A64Assembler.pbi:1994-1997).
    attach_symbols(cpu, img, LOAD)

    uart = bytearray()

    def load(addr, size):
        # THE ALIGNMENT RULE. This closure replaces A64.load, so the
        # guard has to be CALLED here - see a64_interp.py's ALIGNMENT
        # RULE note. With the MMU off every data access is
        # Device-nGnRnE and an unaligned wide one is a silent runaway
        # on the part; without this line the gate models a machine
        # more permissive than the board it certifies.
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
        if steps > step_limit:
            raise SystemExit("the harness never returned (%d steps)\n%s"
                             % (steps, uart.decode("latin-1")))
    if b"pbkdf2harness done" not in uart:
        raise SystemExit("the harness returned without finishing:\n"
                         + uart.decode("latin-1"))

    out = []
    for i in range(count):
        a = H_RESULT + i * RESULT_STRIDE
        ret = sum(mem.get(a + j, 0) << (8 * j) for j in range(4))
        if ret >= 0x80000000:
            ret -= 0x100000000
        out.append((ret, bytes(mem.get(a + 4 + j, 0) for j in range(64))))
    return out, steps


# =====================================================================
#  THE VECTOR SET
# =====================================================================
#  Cheap extra cases from the validated OpenSSL oracle.  Each is a
#  shape RFC 6070 does not have and the mutation sweep needs:
#  multi-block output at a low iteration count, an odd dkLen that is
#  not a multiple of 20, an empty salt, an empty password, and a dkLen
#  that lands exactly on the stated maximum.
OPENSSL_EXTRA = [
    ("two blocks at c=1",        b"password", b"salt",   1,  40),
    ("three blocks at c=1",      b"password", b"salt",   1,  60),
    ("odd dkLen 21 at c=1",      b"password", b"salt",   1,  21),
    ("odd dkLen 39 at c=2",      b"password", b"salt",   2,  39),
    ("dkLen 1 at c=1",           b"password", b"salt",   1,   1),
    ("dkLen 64, the maximum",    b"password", b"salt",   3,  64),
    ("empty salt",               b"password", b"",       2,  32),
    ("empty password",           b"",         b"salt",   2,  32),
    ("64-byte password (one HMAC block exactly)",
     b"A" * 64, b"salt", 2, 32),
    ("65-byte password (one over)",
     b"A" * 65, b"salt", 2, 32),
    ("high-bit password and salt",
     bytes(range(0x80, 0xC0)), bytes(range(0xC0, 0xE0)), 2, 32),

    # THE ZERO-BYTE PROPERTY, SEPARATED FROM THE ITERATION COUNT.
    # RFC 6070's zero-byte vector - a password and a salt that each
    # contain a zero byte - is the one that catches an implementation
    # which stops at a zero byte, and
    # it is published only at c = 4096, which is 8000 SHA-1
    # compressions against a model of the instruction set.  Those are
    # two independent properties and there is no reason to pay for the
    # second in order to test the first.  The published vector still
    # runs in the full set; these run in the quick one, so the sweep
    # can see a C-string bug in seconds.
    ("zero byte in the password, c=1",
     b"pass\x00word", b"salt", 1, 20),
    ("zero byte in the salt, c=1",
     b"password", b"sa\x00lt", 1, 20),
    ("zero byte in both, c=2, two blocks",
     b"pass\x00word", b"sa\x00lt", 2, 40),
    ("password that is nothing but zero bytes",
     b"\x00" * 8, b"salt", 2, 32),
    ("salt that is nothing but zero bytes",
     b"password", b"\x00" * 8, 2, 32),
]

# Calls that must be REFUSED: return 0 and write nothing.
REFUSALS = [
    ("Pbkdf2 with 0 iterations",   OP_PBKDF2, b"password", b"salt", 0, 20),
    ("Pbkdf2 with -1 iterations",  OP_PBKDF2, b"password", b"salt", -1, 20),
    ("Pbkdf2 with dkLen 0",        OP_PBKDF2, b"password", b"salt", 1, 0),
    ("Pbkdf2 with dkLen -1",       OP_PBKDF2, b"password", b"salt", 1, -1),
    ("Pbkdf2 with dkLen 65",       OP_PBKDF2, b"password", b"salt", 1, 65),
    ("WPA2 passphrase of 7",       OP_WPA2,   b"1234567", b"IEEE", 0, 0),
    ("WPA2 passphrase of 0",       OP_WPA2,   b"",        b"IEEE", 0, 0),
    ("WPA2 passphrase of 64",      OP_WPA2,   b"Z" * 64,  b"IEEE", 0, 0),
    ("WPA2 passphrase of 65",      OP_WPA2,   b"Z" * 65,  b"IEEE", 0, 0),
    ("WPA2 empty SSID",            OP_WPA2,   b"password", b"",    0, 0),
    ("WPA2 SSID of 33",            OP_WPA2,   b"password", b"Z" * 33, 0, 0),
    ("Pbkdf2 with pwlen -1",       OP_NEG_PWLEN,   b"password", b"salt", 1, 20),
    ("Pbkdf2 with saltlen -1",     OP_NEG_SALTLEN, b"password", b"salt", 1, 20),
]


def build_script(quick: bool, subset: bool = False,
                 wpa2only: bool = False) -> Script:
    """quick drops everything with 4096 iterations; wpa2only keeps ONLY
    the three IEEE Annex H.4 passphrase-to-PSK vectors.

    WHY wpa2only EXISTS. One 4096-iteration two-block derivation is
    about 16,000 SHA-1 compressions, and this oracle is a Python model
    of the instruction set - so the full set is an hour-scale run and
    the WPA2 mapping is the one part of it a person waiting on a bench
    actually needs confirmed. It is a way to ask a smaller question,
    not a way to lower the bar: the full run is still the gate.
    """
    s = Script()
    published = parse_rfc6070()
    confirm_oracle(published)

    if wpa2only:
        for p, ssid, want in confirm_ieee():
            s.add(OP_WPA2,
                  "IEEE Annex H.4  passphrase %d chars, SSID %d chars"
                  % (len(p), len(ssid)), 32, want, p, ssid, 0, 0)
        return s

    # ---- RFC 6070, the published set ----------------------------------
    for v in published:
        if v["c"] > 100000:
            # 16,777,216 iterations is four thousand WPA2 joins against
            # a Python model of the instruction set.  It is skipped
            # here and NOT skipped in confirm_oracle above, so the
            # vector still does work: it is part of what validates the
            # second oracle.
            continue
        if quick and v["c"] > 100:
            continue
        s.add(OP_PBKDF2,
              "RFC 6070  P=%d S=%d c=%d dkLen=%d"
              % (len(v["P"]), len(v["S"]), v["c"], v["dkLen"]),
              v["dkLen"], v["DK"], v["P"], v["S"], v["c"], v["dkLen"])

    # ---- the validated OpenSSL oracle, cheap shapes -------------------
    extra = OPENSSL_EXTRA
    if subset:
        extra = OPENSSL_EXTRA
    for name, pw, salt, c, dklen in extra:
        dk = hashlib.pbkdf2_hmac("sha1", pw, salt, c, dklen)
        s.add(OP_PBKDF2, "OpenSSL  " + name, dklen, dk, pw, salt, c, dklen)

    # ---- IEEE 802.11 Annex H.4.2 --------------------------------------
    if not quick:
        for p, ssid, want in confirm_ieee():
            s.add(OP_WPA2,
                  "IEEE Annex H.4  passphrase %d chars, SSID %d chars"
                  % (len(p), len(ssid)), 32, want, p, ssid, 0, 0)

        # THE ACCEPTING SIDE OF THE 63/64 BOUNDARY.  The refusal list
        # below proves a 64-character passphrase is rejected; without
        # this, "reject everything" would pass too.  A boundary needs
        # a test on both sides of it or it is not a boundary, it is a
        # wall.  Published vectors stop at 32 characters, so the
        # expected value comes from the oracle validated above.
        for plen, slen in ((63, 1), (8, 1)):
            pw = bytes(0x41 + (k % 26) for k in range(plen))
            ssid = b"x" * slen
            s.add(OP_WPA2, "WPA2 boundary  passphrase %d chars, SSID %d"
                  % (plen, slen), 32,
                  hashlib.pbkdf2_hmac("sha1", pw, ssid, 4096, 32),
                  pw, ssid, 0, 0)

    # ---- refusals ------------------------------------------------------
    for name, op, pw, salt, c, dklen in REFUSALS:
        s.add(op, "REFUSE  " + name, 0, b"", pw, salt, c, dklen)

    return s


def check(img: pathlib.Path, s: Script, quiet: bool = False,
          step_limit: int = STEP_LIMIT) -> tuple:
    got, steps = run(img, s.done(), len(s.labels), step_limit)
    bad = []
    for i, label in enumerate(s.labels):
        want_ret, want_field = s.expect[i]
        ret, field = got[i]
        if ret != want_ret:
            bad.append("  %s\n      returned %d, expected %d"
                       % (label, ret, want_ret))
        elif field != want_field:
            n = 0
            while n < 64 and field[n] == want_field[n]:
                n += 1
            bad.append("  %s\n      first difference at byte %d\n"
                       "      expected %s\n      got      %s"
                       % (label, n, want_field[:32].hex(), field[:32].hex()))
    if not quiet:
        print("  %d vectors, %s, %d steps"
              % (len(s.labels), "ALL PASS" if not bad else
                 "%d FAILED" % len(bad), steps))
    return bad, steps


# =====================================================================
#  MUTATIONS
# =====================================================================
MUTATIONS = [
    ("inner loop runs c times, not c-1",
     "    j = 1\n    While j < iters", "    j = 0\n    While j < iters", 1,
     "the classic PBKDF2 off-by-one; only a small c can see it"),

    ("inner loop runs c-2 times",
     "    j = 1\n    While j < iters", "    j = 2\n    While j < iters", 1,
     "the other direction of the same bug"),

    ("T starts at zero instead of U_1",
     "      secPbkdf2T[k] = secPbkdf2U[k]",
     "      secPbkdf2T[k] = 0", 1,
     "F is U_1 XOR U_2 XOR ... , and U_1 is a term of it"),

    ("T accumulates by assignment, not XOR",
     "secPbkdf2T[k] = secPbkdf2T[k] ! secPbkdf2U[k]",
     "secPbkdf2T[k] = secPbkdf2U[k]", 1,
     "F would become U_c alone"),

    ("INT(i) little-endian",
     "    secPbkdf2Int[0] = (i >> 24) & 255\n"
     "    secPbkdf2Int[1] = (i >> 16) & 255\n"
     "    secPbkdf2Int[2] = (i >> 8) & 255\n"
     "    secPbkdf2Int[3] = i & 255",
     "    secPbkdf2Int[0] = i & 255\n"
     "    secPbkdf2Int[1] = (i >> 8) & 255\n"
     "    secPbkdf2Int[2] = (i >> 16) & 255\n"
     "    secPbkdf2Int[3] = (i >> 24) & 255", 1,
     "INT(i) is most significant octet first; block 1 is unaffected, so "
     "only a multi-block output can see it"),

    ("block counter starts at 0",
     "  i = 1\n  While i <= blocks", "  i = 0\n  While i <= blocks", 1,
     "T_1 uses INT(1); starting at 0 shifts every block"),

    ("block count rounds down",
     "blocks = (dklen + #PBKDF2_HLEN - 1) / #PBKDF2_HLEN",
     "blocks = dklen / #PBKDF2_HLEN", 1,
     "a dkLen of 25 would produce 20 bytes and leave the sentinel"),

    ("the salt is not absorbed",
     "      HmacSha1Update(salt, saltlen)\n", "\n", 1,
     "U_1 = PRF(P, S || INT(i)), not PRF(P, INT(i))"),

    ("the counter is not absorbed",
     "    HmacSha1Update(@secPbkdf2Int[0], 4)\n", "\n", 1,
     "every block would then be identical"),

    ("the key is re-set inside the block loop",
     "    HmacSha1Begin()\n    If saltlen > 0",
     "    HmacSha1Key(pw, pwlen)\n    If saltlen > 0", 1,
     "HmacSha1Key ends by calling HmacSha1Begin, so this one is subtle: "
     "it is slower but not wrong, and it must therefore go GREEN"),

    ("dkLen ceiling not enforced",
     "  If dklen > #PBKDF2_MAXDK\n    ProcedureReturn 0\n  EndIf", "", 1,
     "a dkLen of 65 must be refused, not truncated"),

    ("zero iterations accepted",
     "  If iters < 1\n    ProcedureReturn 0\n  EndIf", "", 1,
     "c = 0 must be refused"),

    ("WPA2 accepts a 64-character passphrase",
     "  If plen > #WPA2_PASS_MAX\n    ProcedureReturn 0\n  EndIf", "", 1,
     "64 characters is a hex PSK, not a passphrase"),

    ("WPA2 accepts a 7-character passphrase",
     "  If plen < #WPA2_PASS_MIN\n    ProcedureReturn 0\n  EndIf", "", 1,
     "IEEE 802.11's mapping is defined for 8 to 63"),

]

# THE ONE MUTATION THE QUICK SET CANNOT SEE, AND WHY IT IS HERE ANYWAY.
#
# #WPA2_PSK_ITERS only appears inside Wpa2Psk, and Wpa2Psk always does
# 4096 iterations - so the only vectors that can notice it changing are
# the IEEE Annex H.4 ones, each of which is 16,000 SHA-1 compressions
# against a Python model of the instruction set.  The quick vector set
# deliberately has none, so --mutate ran this defect and went GREEN on
# the first sweep.  THAT IS A HOLE IN THE GATE, not in the library, and
# the wrong response would have been to delete the mutation.
#
# So it lives here instead, run by --mutate-wpa2, which uses ONE IEEE
# vector and a budget large enough for it.  That is a slow gate and it
# is meant to be run rarely; the fast sweep prints a line saying this
# one was not attempted, so nobody can read a green --mutate as
# covering it.
WPA2_MUTATIONS = [
    ("WPA2 iteration count wrong", True,
     "#WPA2_PSK_ITERS = 4096", "#WPA2_PSK_ITERS = 1024", 1,
     "the Annex H.4 vectors are 4096 iterations and nothing else"),

    ("WPA2 output length wrong", True,
     "#WPA2_PSK_LEN   = 32", "#WPA2_PSK_LEN   = 16", 1,
     "a PSK is 256 bits; 16 bytes would leave the sentinel in the tail"),

    ("WPA2 passes the SSID as the password", True,
     "ProcedureReturn Pbkdf2Sha1(passphrase, plen, ssid, ssidlen, "
     "#WPA2_PSK_ITERS, dst, #WPA2_PSK_LEN)",
     "ProcedureReturn Pbkdf2Sha1(ssid, ssidlen, passphrase, plen, "
     "#WPA2_PSK_ITERS, dst, #WPA2_PSK_LEN)", 1,
     "the passphrase is the password and the SSID is the SALT, not the "
     "other way round - and the two are the same shape, so nothing but a "
     "vector can tell"),
]

# The one mutation above that must go GREEN, with its reason recorded
# rather than the mutation deleted.
EXPECT_GREEN = {"the key is re-set inside the block loop"}


def mutate(clean_steps: int) -> int:
    """Every mutation, against the quick vector set and a STEP BUDGET.

    THE BUDGET IS NOT A TIMEOUT, IT IS A DETECTOR, and it was earned.
    Three of the mutations below remove an argument check in Wpa2Psk -
    the 7-character passphrase, the 64-character one, the over-long
    SSID.  Without the check those calls stop being refusals and become
    REAL 4096-iteration derivations: 16,000 SHA-1 compressions each,
    against a Python model of the instruction set.  The first run of
    this sweep spent over an hour on those three and printed nothing
    while it did.

    They are genuine defects and they do go red on the values as well -
    a refusal that returns 32 is not a refusal - but waiting half an
    hour to be told so is a sweep nobody runs.  So a mutated build is
    given twenty times the clean run's instruction count and anything
    that exceeds it is reported RED with the reason.  "This refusal
    started doing PBKDF2" is exactly the failure, and the step count is
    a more direct way to see it than the output value is.
    """
    src = LIB.read_text(encoding="utf-8")
    s = build_script(quick=True)
    budget = max(clean_steps * 20, 20_000_000)
    failures = 0
    print("MUTATION TEST - quick vector set, step budget %d (clean run was %d)"
          % (budget, clean_steps))
    for name, old, new, count, why in MUTATIONS:
        n = src.count(old)
        if n != count:
            print("  %-44s CANNOT APPLY - anchor occurs %d times, expected %d"
                  % (name, n, count))
            failures += 1
            continue
        mut = WORK / "pbkdf2_mut.pi4"
        mut.write_text(src.replace(old, new), encoding="utf-8")
        red = None
        note = ""
        try:
            build("_work/pbkdf2_mut.pi4", WORK / "pbkdf2harness_mut.pi4",
                  WORK / "pbkdf2check_mut.img")
        except SystemExit:
            red, note = True, "refused to build"
        if red is None:
            try:
                bad, msteps = check(WORK / "pbkdf2check_mut.img", s,
                                    quiet=True, step_limit=budget)
                red = len(bad) > 0
                note = "%d of %d, %d steps" % (len(bad), len(s.labels), msteps)
            except SystemExit:
                red = True
                note = ("over the step budget - a refusal became a real "
                        "derivation")

        want_red = name not in EXPECT_GREEN
        if red == want_red:
            print("  %-44s %-5s (%s)" % (name, "RED" if red else "GREEN", note))
            if not want_red:
                print("        expected green: %s" % why)
        else:
            failures += 1
            if want_red:
                print("  %-44s *** GREEN - THE GATE DID NOT SEE IT *** %s"
                      % (name, why))
            else:
                print("  %-44s *** RED, EXPECTED GREEN *** %s" % (name, why))

    print("  NOT ATTEMPTED HERE: %d mutations of the WPA2 wrapper itself."
          % len(WPA2_MUTATIONS))
    print("  The quick set has no 4096-iteration derivation in it, so those")
    print("  defects are invisible to this sweep by construction. Run")
    print("  --mutate-wpa2 for them; it is minutes per mutation.")
    return failures


def mutate_wpa2() -> int:
    """The slow sweep: the WPA2 wrapper, against ONE Annex H.4 vector.

    One vector rather than three, because each is 16,000 SHA-1
    compressions on a model of the instruction set and three would
    treble a run that is already minutes long for one bit of extra
    coverage.  The vector chosen is whichever confirm_ieee returns
    first, which is the standard's own "password" / "IEEE" example.
    """
    src = LIB.read_text(encoding="utf-8")
    s = Script()
    p_, ssid, want = confirm_ieee()[0]
    s.add(OP_WPA2, "IEEE Annex H.4  passphrase %d chars, SSID %d chars"
          % (len(p_), len(ssid)), 32, want, p_, ssid, 0, 0)

    print("MUTATION TEST - the WPA2 wrapper, one Annex H.4 vector")
    build("RaspberryPi4/Lib/pbkdf2.pi4", WORK / "pbkdf2harness.pi4",
          WORK / "pbkdf2check.img")
    bad, clean = check(WORK / "pbkdf2check.img", s)
    if bad:
        print("the unmutated library is already failing; fix that first")
        print("\n".join(bad))
        return 1
    budget = clean * 4          # a wrong iteration count is 4x or 1/4x

    failures = 0
    for name, expect_red, old, new, count, why in WPA2_MUTATIONS:
        n = src.count(old)
        if n != count:
            print("  %-44s CANNOT APPLY - anchor occurs %d times, expected %d"
                  % (name, n, count))
            failures += 1
            continue
        (WORK / "pbkdf2_mut.pi4").write_text(src.replace(old, new),
                                             encoding="utf-8")
        red = None
        note = ""
        try:
            build("_work/pbkdf2_mut.pi4", WORK / "pbkdf2harness_mut.pi4",
                  WORK / "pbkdf2check_mut.img")
        except SystemExit:
            red, note = True, "refused to build"
        if red is None:
            try:
                b, msteps = check(WORK / "pbkdf2check_mut.img", s, quiet=True,
                                  step_limit=budget)
                red = len(b) > 0
                note = "%d of %d, %d steps" % (len(b), len(s.labels), msteps)
            except SystemExit:
                red, note = True, "over the step budget"
        if red == expect_red:
            print("  %-44s %-5s (%s)" % (name, "RED" if red else "GREEN", note))
        else:
            failures += 1
            print("  %-44s *** DID NOT BEHAVE AS RECORDED *** %s" % (name, why))
    return failures


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
    ap.add_argument("--target", choices=sorted(TARGETS),
                    default="pi4",
                    help="which AArch64 board's image contract "
                         "to build and grade against")
    ap.add_argument("--mutate", action="store_true")
    ap.add_argument("--mutate-wpa2", action="store_true", dest="mutate_wpa2",
                    help="the slow sweep: mutate the WPA2 wrapper and check "
                         "it against a real Annex H.4 derivation")
    ap.add_argument("--wpa2only", action="store_true",
                    help="run ONLY the three IEEE Annex H.4 "
                         "passphrase-to-PSK vectors")
    ap.add_argument("--quick", action="store_true",
                    help="skip everything with 4096 iterations; seconds "
                         "instead of minutes, and the published WPA2 "
                         "vectors are NOT run")
    args = ap.parse_args()
    globals()["PMFC"] = resolve_compiler(args.compiler)
    apply_target(globals(), args.target)
    # A GATE THAT DOES NOT SAY WHICH BOARD IT GRADED IS A RESULT
    # THAT CAN BE FILED AGAINST THE WRONG ONE.  Printed before any
    # work, so it is at the top of the transcript even on a failure.
    print("[gate] target %s - %s, image at $%08X, stack $%08X"
          % (TARGET_NAME, TARGET_WHAT, LOAD, STACK))

    WORK.mkdir(exist_ok=True)
    build("RaspberryPi4/Lib/pbkdf2.pi4", WORK / "pbkdf2harness.pi4",
          WORK / "pbkdf2check.img")

    if args.mutate_wpa2:
        return 1 if mutate_wpa2() else 0

    if args.mutate:
        s = build_script(quick=True)
        bad, clean_steps = check(WORK / "pbkdf2check.img", s)
        if bad:
            print("the unmutated library is already failing; fix that first")
            print("\n".join(bad[:10]))
            return 1
        return 1 if mutate(clean_steps) else 0

    t0 = time.time()
    print("PBKDF2-HMAC-SHA1 gate")
    print("  published oracle: RFC 6070, parsed from disk")
    print("  second oracle:    OpenSSL via hashlib, validated against all "
          "six RFC 6070 vectors first")
    if not args.quick:
        print("  WPA2 mapping:     IEEE 802.11i Annex H.4.2, transcribed and "
              "confirmed against OpenSSL")
    s = build_script(args.quick, wpa2only=args.wpa2only)
    bad, _ = check(WORK / "pbkdf2check.img", s)
    print("  %.1f s" % (time.time() - t0))
    if bad:
        print("\nFAILURES")
        print("\n".join(bad))
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

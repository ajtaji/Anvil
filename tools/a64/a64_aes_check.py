#!/usr/bin/env python3
"""Executable gate for RaspberryPi4/Lib/aes.pi4.

WHY THIS FILE IS WRITTEN THE WAY IT IS

  EVERY EXPECTED VALUE IS PARSED OFF THE DISK.  Nothing in this file
  is a transcribed hex string, and no expectation was ever produced by
  running the library under test.  There are three oracles and all
  three are documents or NIST-generated files sitting in
  RaspberryPi4/Reference/:

    fips197-2001.txt   FIPS-197 (2001), Appendix C - the worked
                       examples WITH INTERMEDIATE VALUES, for AES-128,
                       AES-192 and AES-256, for the cipher and the
                       inverse cipher, one hex string per round step.
    fips197.txt        FIPS-197 upd1 (2023), Appendix B - the
                       round-by-round state table for one AES-128
                       encryption, in the CURRENT normative document.
    cavp_ECB*.rsp      NIST CAVP AESAVS known-answer vectors, ECB, at
                       all three key lengths: GFSbox, KeySbox, VarKey
                       and VarTxt, each with an ENCRYPT and a DECRYPT
                       section.

  WHY BOTH FIPS-197 DOCUMENTS.  The 2023 update DELETED Appendix C's
  vectors and replaced them with a pointer to a NIST web page
  (fips197.txt:1893-1897).  The intermediate values are the whole point
  here, so the 2001 document is parsed for those; Appendix B survives in
  both and is read from the CURRENT one, so the gate is not resting
  entirely on a superseded text.

  THE INTERMEDIATES ARE THE POINT.  A cipher that is wrong in round 3
  and right at the end is not a thing that happens by accident - but a
  cipher wrong in round 3 that nobody checked is.  Round-by-round
  checking also localises a failure: a red line saying "AES-192
  round[7].m_col" names the procedure to look at, where a red line
  saying "ciphertext differs" names the file.

  HOW THE INTERMEDIATES ARE OBTAINED, AND WHAT THAT DOES AND DOES NOT
  PROVE.  The library exposes no stop-in-the-middle entry point and it
  should not: a library that carries test scaffolding is a library that
  ships it.  So the generated harness runs its OWN copy of the round
  loop, built from the library's step procedures - AesSbox,
  AesShiftRows, AesMixColumns, AesAddRoundKey and their inverses -
  stopping where the vector asks.

    * That gates the STEP PROCEDURES against the document, per round.
    * It does NOT gate the library's own round loop, because it is not
      the library's loop.

  So every Appendix C vector is ALSO run through the real
  AesEncryptBlock / AesDecryptBlock, and both must produce round[Nr]'s
  published output.  The two loops therefore have to agree with each
  other and with NIST, on every vector, at every step.  A mutation that
  puts MixColumns back into the final round is caught by the real
  entry point while the trace stays green, and the mutation table below
  records exactly that.

  THE LANE CHECK IS FREE AND IT IS KEPT.  The bitslice carries two
  blocks at once and this library fills both with the same input, so
  the second lane must come out identical to the first.  The harness
  reports it and the gate requires it.  A mask off by one bit anywhere
  in AesSwapN would show up here as a lane mismatch, which is a much
  more specific complaint than a wrong ciphertext.

  REFUSALS ARE TESTED.  A key length of 0, 15, 20 or 33 must be
  refused, must leave NO key installed, and must make the next
  AesEncryptBlock refuse as well.  A library whose checks only clamp is
  a library that hides its caller's bug.

  THE OUTPUT FIELD IS PRE-FILLED WITH A SENTINEL, so a refusal that
  returns 0 and writes anyway is caught as loudly as a wrong byte.

  MUTATIONS RUN ON A COPY.  This gate NEVER opens aes.pi4 for writing.
  It reads the source, writes the mutant to _work/, and points the
  generated harness's XIncludeFile at the copy.  A mutation runner
  that restores the file in a `finally` loses that race the first time
  it is killed by a timeout, and a commit can then pick up the mutant.

WHAT THIS GATE DOES NOT SAY

  * That any of this runs on silicon.  The oracle is a model of the
    instruction set: no caches, no memory system, no clock.
  * That the implementation is constant time ON HARDWARE.  --timing
    checks that the MODEL executes the identical number of
    instructions for keys and plaintexts of very different Hamming
    weight, which rules out a data-dependent branch or a
    secret-indexed access in the compiled code.  It says nothing about
    what a real Cortex-A72 does with those instructions.

HOW LONG THESE TAKE, MEASURED ON 2026-08-28 UNDER THIS MODEL AT ABOUT
450,000 INSTRUCTIONS A SECOND, SO NOBODY STARTS THE WRONG ONE BY
ACCIDENT

  --fips         FIPS-197 Appendix B and C only.  About a minute.
  --quick        FIPS plus a sampled CAVP set.  A few minutes.
  --mutate       a small vector set, rebuilt once per mutation, FANNED
                 OUT across os.cpu_count() - 2 workers.  70 s for all
                 twenty-four on 2026-08-28, where serial was about
                 821 s.  See tools/a64/a64_mutate_pool.py.
  (no flag)      everything, including all 1,553 CAVP vectors in both
                 directions.  ABOUT TWENTY MINUTES.  It prints a line
                 per file so it is visibly alive.
  --timing       the constant-instruction-count check.  Seconds.

Run: python tools/a64/a64_aes_check.py
     python tools/a64/a64_aes_check.py --fips
     python tools/a64/a64_aes_check.py --quick
     python tools/a64/a64_aes_check.py --timing
     python tools/a64/a64_aes_check.py --mutate
"""

from __future__ import annotations

import argparse
import os
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
from a64_interp import A64, AlignmentFault, attach_symbols  # noqa: E402
from a64_target import (TARGETS, apply_target,  # noqa: E402
                        patch_harness)
import a64_mutate_pool as pool  # noqa: E402

PMFC = os.environ.get("PMF_COMPILER") or "PureMetalForge.exe"  # rebound from --compiler
# Every compile resolves includes from THIS tree only.
BUILD_ENV = dict(os.environ, PMF_ROOT=str(ROOT))
LIB = ROOT / "RaspberryPi4" / "Lib" / "aes.pi4"
REF = ROOT / "RaspberryPi4" / "Reference"
FIPS_2001 = REF / "fips197-2001.txt"
FIPS_UPD1 = REF / "fips197.txt"
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

REC_STRIDE = 64             # one script record
RES_STRIDE = 40             # one result record
SENTINEL = 0xA5

OP_END = 0
OP_SETKEY = 1
OP_ENC = 2
OP_DEC = 3
OP_KSCH = 4
OP_TRACE_ENC = 5
OP_TRACE_DEC = 6
OP_WIPE = 7

# Trace phases.  The names are FIPS-197 Appendix C's own labels.
PH_INPUT = 0                # cipher input / iinput
PH_START = 1                # start / istart
PH_SBOX = 2                 # s_box   (encrypt) / is_row (decrypt)
PH_SROW = 3                 # s_row   (encrypt) / is_box (decrypt)
PH_MCOL = 4                 # m_col   (encrypt) / ik_add (decrypt)
PH_OUTPUT = 5               # output / ioutput


# =====================================================================
#  THE HARNESS
# =====================================================================
#  SCRIPT RECORD, 64 bytes:
#      +0  op   +4 keylen   +8 arg0   +12 arg1   +16 key[32]  +48 blk[16]
#  op 0 ends the script.
#
#  RESULT RECORD, 40 bytes:
#      +0  the value the library returned, 32-bit
#      +4  the 16-byte output field, pre-filled with $A5
#      +20 lane 1's 16 bytes, pre-filled with $A5
#
#  THE TWO TRACE PROCEDURES BELOW ARE THE HARNESS'S OWN ROUND LOOPS.
#  They are written to mirror FIPS-197 sections 5.1 and 5.3 step for
#  step so that a stop point has a name in Appendix C, and they call
#  nothing but the library's own step procedures.  See the gate's
#  header for what that does and does not prove.
# =====================================================================
HARNESS = r'''
; ======================================================================
;  aesharness.pi4 - GENERATED BY tools/a64/a64_aes_check.py.
;  NOT A SOURCE FILE. DO NOT EDIT.
;
;  Every key and block it runs is a PUBLISHED test value handed to it
;  in memory by the gate. There is no credential in this file.
; ======================================================================
XIncludeFile "RaspberryPi4/Lib/uart.pi4"
XIncludeFile "__LIB__"

#H_SCRIPT = $06000000
#H_RESULT = $0A000000

Global Dim hKsch.i[8]

; ----------------------------------------------------------------------
;  KschRead(r, dst) - read round key r back out of the expanded
;  schedule as sixteen plain bytes.
;
;  AesOrtho is its own inverse, so applying it to the eight bitsliced
;  planes of round r recovers the pre-slice arrangement, which is the
;  four round-key words duplicated across the two lanes:
;  [w0 w0 w1 w1 w2 w2 w3 w3].  Even indices are lane 0.
; ----------------------------------------------------------------------
Procedure KschRead(r.i, dst.i)
  Define i.i
  i = 0
  While i < 8
    hKsch[i] = secAesSkExp[r * 8 + i]
    i = i + 1
  Wend
  AesOrtho(@hKsch[0])
  AesEnc32le(dst,      hKsch[0])
  AesEnc32le(dst + 4,  hKsch[2])
  AesEnc32le(dst + 8,  hKsch[4])
  AesEnc32le(dst + 12, hKsch[6])
EndProcedure

; ----------------------------------------------------------------------
;  TraceEnc(src, dst, wantR, wantP) - FIPS-197 section 5.1's Cipher,
;  stopping at round wantR, phase wantP, and writing the state there.
; ----------------------------------------------------------------------
Procedure TraceEnc(src.i, dst.i, wantR.i, wantP.i)
  Define r.i
  AesLoadBlock(src)
  If wantR = 0
    AesStoreBlock(dst)
    ProcedureReturn
  EndIf
  AesAddRoundKey(@AesQ[0], @secAesSkExp[0])
  r = 1
  While r <= AesNumRounds
    If r = wantR And wantP = 1
      AesStoreBlock(dst)
      ProcedureReturn
    EndIf
    AesSbox(@AesQ[0])
    If r = wantR And wantP = 2
      AesStoreBlock(dst)
      ProcedureReturn
    EndIf
    AesShiftRows(@AesQ[0])
    If r = wantR And wantP = 3
      AesStoreBlock(dst)
      ProcedureReturn
    EndIf
    If r < AesNumRounds
      AesMixColumns(@AesQ[0])
      If r = wantR And wantP = 4
        AesStoreBlock(dst)
        ProcedureReturn
      EndIf
    EndIf
    AesAddRoundKey(@AesQ[0], @secAesSkExp[0] + r * 8 * 8)
    r = r + 1
  Wend
  AesStoreBlock(dst)
EndProcedure

; ----------------------------------------------------------------------
;  TraceDec(src, dst, wantR, wantP) - FIPS-197 section 5.3's
;  InvCipher.  Appendix C's inverse-cipher round r corresponds to
;  BearSSL's loop counter u = Nr - r, and round r's ik_sch is the
;  FORWARD round key w[Nr - r] - which is what the k_sch checks below
;  assert.
; ----------------------------------------------------------------------
Procedure TraceDec(src.i, dst.i, wantR.i, wantP.i)
  Define u.i
  Define r.i
  AesLoadBlock(src)
  If wantR = 0
    AesStoreBlock(dst)
    ProcedureReturn
  EndIf
  AesAddRoundKey(@AesQ[0], @secAesSkExp[0] + AesNumRounds * 8 * 8)
  u = AesNumRounds - 1
  While u > 0
    r = AesNumRounds - u
    If r = wantR And wantP = 1
      AesStoreBlock(dst)
      ProcedureReturn
    EndIf
    AesInvShiftRows(@AesQ[0])
    If r = wantR And wantP = 2
      AesStoreBlock(dst)
      ProcedureReturn
    EndIf
    AesInvSbox(@AesQ[0])
    If r = wantR And wantP = 3
      AesStoreBlock(dst)
      ProcedureReturn
    EndIf
    AesAddRoundKey(@AesQ[0], @secAesSkExp[0] + u * 8 * 8)
    If r = wantR And wantP = 4
      AesStoreBlock(dst)
      ProcedureReturn
    EndIf
    AesInvMixColumns(@AesQ[0])
    u = u - 1
  Wend
  If wantR = AesNumRounds And wantP = 1
    AesStoreBlock(dst)
    ProcedureReturn
  EndIf
  AesInvShiftRows(@AesQ[0])
  If wantR = AesNumRounds And wantP = 2
    AesStoreBlock(dst)
    ProcedureReturn
  EndIf
  AesInvSbox(@AesQ[0])
  If wantR = AesNumRounds And wantP = 3
    AesStoreBlock(dst)
    ProcedureReturn
  EndIf
  AesAddRoundKey(@AesQ[0], @secAesSkExp[0])
  AesStoreBlock(dst)
EndProcedure

Procedure.i Main()
  Define p.i
  Define q.i
  Define op.i
  Define keylen.i
  Define a0.i
  Define a1.i
  Define i.i
  Define r.i

  p = #H_SCRIPT
  q = #H_RESULT

  Repeat
    op     = PeekN(p)
    keylen = PeekL(p + 4)
    a0     = PeekL(p + 8)
    a1     = PeekL(p + 12)
    If op = 0
      Break
    EndIf

    i = 0
    While i < 32
      PokeB(q + 4 + i, $A5)
      i = i + 1
    Wend

    r = 0
    If op = 1
      r = AesSetKey(p + 16, keylen)
    ElseIf op = 2
      r = AesEncryptBlock(p + 48, q + 4)
      ; The lane-1 readback is written ONLY when the call actually ran.
      ; A refusal must leave the whole result field at its sentinel, and
      ; writing the lanes unconditionally would erase the evidence that
      ; the refusal wrote nothing at all.
      If r <> 0
        AesEnc32le(q + 20, AesQ[1])
        AesEnc32le(q + 24, AesQ[3])
        AesEnc32le(q + 28, AesQ[5])
        AesEnc32le(q + 32, AesQ[7])
      EndIf
    ElseIf op = 3
      r = AesDecryptBlock(p + 48, q + 4)
      ; The lane-1 readback is written ONLY when the call actually ran.
      ; A refusal must leave the whole result field at its sentinel, and
      ; writing the lanes unconditionally would erase the evidence that
      ; the refusal wrote nothing at all.
      If r <> 0
        AesEnc32le(q + 20, AesQ[1])
        AesEnc32le(q + 24, AesQ[3])
        AesEnc32le(q + 28, AesQ[5])
        AesEnc32le(q + 32, AesQ[7])
      EndIf
    ElseIf op = 4
      KschRead(a0, q + 4)
      r = AesKeyBits()
    ElseIf op = 5
      TraceEnc(p + 48, q + 4, a0, a1)
      r = AesKeyBits()
    ElseIf op = 6
      TraceDec(p + 48, q + 4, a0, a1)
      r = AesKeyBits()
    ElseIf op = 7
      AesWipe()
      r = AesKeyBits()
    EndIf
    PokeN(q, r)

    p = p + 64
    q = q + 40
  ForEver

  UartWriteStr("aesharness done")
  ProcedureReturn 0
EndProcedure
'''


class Script:
    """A stream of harness records with the expectations beside them."""

    def __init__(self) -> None:
        self.buf = bytearray()
        self.labels: list[str] = []
        self.expect: list[tuple[int, bytes | None, bool]] = []

    def add(self, op: int, label: str, ret: int, out: bytes | None,
            key: bytes = b"", blk: bytes = b"", keylen: int | None = None,
            a0: int = 0, a1: int = 0, lanes: bool = False) -> None:
        """out is the expected 16 bytes, or None when nothing is written
        (in which case the whole 32-byte field must still be sentinel).
        lanes asks for the two bitslice lanes to be compared."""
        if keylen is None:
            keylen = len(key)
        self.labels.append(label)
        if out is None:
            field = bytes([SENTINEL]) * 32
        elif lanes:
            field = out + out
        else:
            field = out + bytes([SENTINEL]) * 16
        self.expect.append((ret, field, lanes))
        self.buf += struct.pack("<Iiii", op, keylen, a0, a1)
        self.buf += key + b"\x00" * (32 - len(key))
        self.buf += blk + b"\x00" * (16 - len(blk))

    def done(self) -> bytes:
        return bytes(self.buf) + struct.pack("<Iiii", OP_END, 0, 0, 0) \
            + b"\x00" * 48

    def __len__(self) -> int:
        return len(self.labels)


# =====================================================================
#  FIPS-197 APPENDIX C, PARSED
# =====================================================================
#  The 2001 document prints, for each of AES-128/192/256:
#
#      PLAINTEXT: ...
#      KEY: ...
#      CIPHER (ENCRYPT):
#      round[ 0].input   ...
#      round[ 0].k_sch   ...
#      round[ 1].start   ...
#      ...
#      INVERSE CIPHER (DECRYPT):
#      round[ 0].iinput ...
#      ...
#      EQUIVALENT INVERSE CIPHER (DECRYPT):
#      ...
#
#  Only the first two sections are used.  The EQUIVALENT inverse cipher
#  is a DIFFERENT algorithm with a different key schedule, and this
#  library implements the straight one - see aes.pi4's
#  AesBitsliceDecrypt.  Parsing it and then not checking against it
#  would be a trap for the next reader, so it is skipped explicitly and
#  the parse asserts that it found the boundary.
def parse_fips_appendix_c() -> list[dict]:
    if not FIPS_2001.exists():
        raise SystemExit(
            f"the oracle is missing: {FIPS_2001}\n"
            "Fetch https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.197.pdf "
            "into RaspberryPi4/Reference/ as fips197-2001.pdf and run\n"
            "  pdftotext fips197-2001.pdf fips197-2001.txt\n"
            "WITHOUT -layout.  With it, Appendix C's columns are "
            "interleaved differently on different pages and C.2's "
            "round[0] values come out attached to the wrong labels.")
    text = FIPS_2001.read_text(errors="replace")
    # ANCHOR ON THE LEGEND, NOT ON "C.1".  The table of contents carries
    # a line reading "C.1 AES-128 (NK=4, NR=10)" thirty pages earlier,
    # and a plain find() lands on that - which produced a chunk one line
    # long and an error message ("no PLAINTEXT") that pointed at the
    # document rather than at the parse.  The legend text appears once.
    start = text.find("Legend for CIPHER (ENCRYPT)")
    if start < 0:
        raise SystemExit("fips197-2001.txt: cannot find Appendix C's legend")
    body = text[start:]

    out = []
    for name, nk, nr in (("C.1 AES-128", 4, 10),
                         ("C.2 AES-192", 6, 12),
                         ("C.3 AES-256", 8, 14)):
        i = body.find(name)
        if i < 0:
            raise SystemExit("fips197-2001.txt: cannot find %r" % name)
        j = len(body)
        for nxt in ("C.2 AES-192", "C.3 AES-256", "Appendix D - References"):
            k = body.find(nxt, i + 1)
            if k > 0:
                j = min(j, k)
        chunk = body[i:j]

        # Split the three sections.  The boundaries are asserted rather
        # than assumed: if NIST ever reformats this, the parse must stop
        # rather than silently read the equivalent inverse cipher's
        # numbers as the inverse cipher's.
        ie = chunk.find("CIPHER (ENCRYPT):")
        ii = chunk.find("INVERSE CIPHER (DECRYPT):")
        iq = chunk.find("EQUIVALENT INVERSE CIPHER (DECRYPT):")
        if not (0 <= ie < ii < iq):
            raise SystemExit(
                "%s: the three sections are not in the expected order "
                "(%d, %d, %d). Fix the parse; do not guess." % (name, ie, ii, iq))

        # ---- the header: the plaintext and the key -------------------
        # Taken as the two hex tokens between the section heading and
        # "CIPHER (ENCRYPT):", in that order, rather than by matching
        # "PLAINTEXT:" and "KEY:" - because C.1's extraction puts BOTH
        # labels on one line and both values on the two lines after it,
        # so a label-anchored regex reads the plaintext as the key.
        head = [t for t in re.findall(r"\b[0-9a-f]{32,64}\b", chunk[:ie])]
        if len(head) != 2:
            raise SystemExit("%s: expected a plaintext and a key before "
                             "CIPHER (ENCRYPT):, found %d hex values"
                             % (name, len(head)))
        pt = bytes.fromhex(head[0])
        key = bytes.fromhex(head[1])
        if len(pt) != 16 or len(key) != nk * 4:
            raise SystemExit("%s: header gave a %d-byte plaintext and a "
                             "%d-byte key; expected 16 and %d"
                             % (name, len(pt), len(key), nk * 4))

        # ---- the round steps -----------------------------------------
        # PAIRED BY POSITION, NOT BY PROXIMITY.  pdftotext lays this
        # appendix out differently on different pages: sometimes a label
        # and its value share a line, sometimes a whole page of labels is
        # followed by a whole page of values.  Both preserve ORDER, so
        # the labels and the values are collected separately and zipped,
        # and the counts must match exactly.  Every cross-check below
        # then has to hold, which is what makes a mis-pairing loud.
        def steps(seg: str, tag: str) -> dict:
            labels = re.findall(r"round\[\s*(\d+)\]\.(\w+)", seg)
            values = re.findall(r"\b[0-9a-f]{32}\b", seg)
            if len(labels) != len(values):
                raise SystemExit(
                    "%s %s: %d labels but %d values. The extraction has "
                    "changed shape - fix the parse, do not lower the number."
                    % (name, tag, len(labels), len(values)))
            d = {}
            for (r, what), v in zip(labels, values):
                d[(int(r), what)] = bytes.fromhex(v)
            if len(d) != len(labels):
                raise SystemExit("%s %s: a label occurs twice" % (name, tag))
            return d

        enc = steps(chunk[ie:ii], "CIPHER")
        dec = steps(chunk[ii:iq], "INVERSE CIPHER")

        # THE KEY, DERIVED A SECOND WAY.  Round key 0 is the first
        # sixteen key bytes and, for the longer keys, round key 1
        # carries the rest - FIPS-197 section 5.2, the schedule starts
        # as a copy of the key.  Deriving it from the printed k_sch
        # values and requiring agreement with the header check catches a
        # mis-paired parse that happened to keep the counts equal.
        derived = enc[(0, "k_sch")]
        if nk == 6:
            derived += enc[(1, "k_sch")][:8]
        elif nk == 8:
            derived += enc[(1, "k_sch")]
        if derived != key:
            raise SystemExit(
                "%s: the printed KEY and round[0..1].k_sch disagree:\n"
                "  header  %s\n  k_sch   %s\nThe parse is wrong."
                % (name, key.hex(), derived.hex()))

        # The document states the answer twice - the cipher's output and
        # the inverse cipher's input - so the parse can check itself.
        if enc[(nr, "output")] != dec[(0, "iinput")]:
            raise SystemExit("%s: the cipher output and the inverse cipher "
                             "input disagree; the parse is wrong" % name)
        if dec[(nr, "ioutput")] != pt:
            raise SystemExit("%s: the inverse cipher does not return the "
                             "stated plaintext; the parse is wrong" % name)
        if enc[(0, "input")] != pt:
            raise SystemExit("%s: round[0].input is not the stated "
                             "plaintext; the parse is wrong" % name)

        # Every round key must have been found, in both directions, and
        # inverse round r's ik_sch must be forward round Nr-r's k_sch.
        for r in range(nr + 1):
            if (r, "k_sch") not in enc:
                raise SystemExit("%s: no round[%d].k_sch" % (name, r))
            if (r, "ik_sch") not in dec:
                raise SystemExit("%s: no round[%d].ik_sch" % (name, r))
            if dec[(r, "ik_sch")] != enc[(nr - r, "k_sch")]:
                raise SystemExit(
                    "%s: round[%d].ik_sch is not round[%d].k_sch - the "
                    "parse has picked up the equivalent inverse cipher"
                    % (name, r, nr - r))

        out.append({"name": name, "nk": nk, "nr": nr, "key": key, "pt": pt,
                    "ct": enc[(nr, "output")], "enc": enc, "dec": dec})
    if len(out) != 3:
        raise SystemExit("fips197-2001.txt: expected three key sizes")
    return out


# =====================================================================
#  FIPS-197 APPENDIX B, PARSED OUT OF THE 2023 DOCUMENT
# =====================================================================
#  Appendix B prints the state as a 4x4 array, column-major, spread
#  across four text lines per round with five columns of numbers: start
#  of round, after SubBytes, after ShiftRows, after MixColumns, and the
#  round key.  Reading it is fiddly and worth doing anyway, because it
#  is the ONE worked example still present in the normative document.
#
#  THE PARSE VALIDATES ITSELF AGAINST APPENDIX C.  Both documents work
#  the same key and the same plaintext, so every value Appendix B
#  yields must equal the corresponding Appendix C value.  If the layout
#  ever defeats the reader below, that check fires rather than the gate
#  quietly testing against nonsense.
def parse_fips_appendix_b() -> dict:
    if not FIPS_UPD1.exists():
        raise SystemExit(f"the oracle is missing: {FIPS_UPD1}")
    text = FIPS_UPD1.read_text(errors="replace")
    # rfind, not find - the same two headings appear in the table of
    # contents thirty pages earlier and a forward search lands on those,
    # giving a two-line body and an error that blames the document.
    i = text.rfind("Appendix B -- Cipher Example")
    j = text.rfind("Appendix C -- Example Vectors")
    if i < 0 or j < 0 or j <= i:
        raise SystemExit("fips197.txt: cannot find Appendix B's boundaries")
    body = text[i:j]

    m = re.search(r"Input\s*=\s*((?:[0-9a-f]{2}\s+){15}[0-9a-f]{2})", body)
    if not m:
        raise SystemExit("fips197.txt: no Appendix B Input line")
    pt = bytes.fromhex(re.sub(r"\s", "", m.group(1)))
    m = re.search(r"Key\s*=\s*((?:[0-9a-f]{2}\s+){15}[0-9a-f]{2})", body)
    if not m:
        raise SystemExit("fips197.txt: no Appendix B Key line")
    key = bytes.fromhex(re.sub(r"\s", "", m.group(1)))

    # Collect every line that is NOTHING BUT groups of four hex bytes,
    # allowing the words "input" and "output" which the table prints in
    # the middle of two of its rows.  Page numbers and round numbers sit
    # on their own lines with fewer than four byte pairs, so they never
    # produce a group and are dropped without a special case; the
    # running-head line has letters in it and is dropped by the
    # leftover test.
    rows = []
    for ln in body.splitlines():
        groups = re.findall(r"(?:[0-9a-f]{2} ){3}[0-9a-f]{2}", ln)
        if not groups:
            continue
        rest = ln
        for g in groups:
            rest = rest.replace(g, "", 1)
        rest = rest.replace("input", "").replace("output", "").strip()
        if rest:
            continue
        rows.append(groups)

    # The table is read as: four consecutive rows with the same number
    # of columns are one round block, top row first.  Column c of the
    # block is one 4x4 state printed ROW-major, so the byte sequence is
    # column-major - state[col*4 + row].
    blocks: list[list[bytes]] = []
    k = 0
    while k + 3 < len(rows):
        w = len(rows[k])
        if not all(len(rows[k + d]) == w for d in range(1, 4)):
            k += 1
            continue
        block = []
        for c in range(w):
            state = bytearray(16)
            for r in range(4):
                cells = rows[k + r][c].split()
                for col in range(4):
                    state[col * 4 + r] = int(cells[col], 16)
            block.append(bytes(state))
        blocks.append(block)
        k += 4

    # THE SHAPE IS ASSERTED, NOT ASSUMED.  What comes out cleanly is the
    # input row (state and round key, two columns) followed by rounds 1
    # to 9 (five columns each).
    #
    # ROUND 10 AND THE OUTPUT BLOCK ARE NOT READ AND THAT IS DELIBERATE.
    # pdftotext breaks those two blocks across lines of one, three and
    # four columns - the round key spills onto its own line and the
    # round number lands inside the table - and a reader clever enough
    # to reassemble them would be a reader nobody could check.  Appendix
    # C carries the same two values (round[10].s_row, round[10].k_sch,
    # round[10].output) and the gate checks them there, so nothing is
    # lost except the pleasure of having read them twice.
    want = [2] + [5] * 9
    got = [len(b) for b in blocks[:len(want)]]
    if got != want:
        raise SystemExit(
            "fips197.txt Appendix B: expected column counts %s, read %s "
            "(%d blocks in all).\nThe extraction has changed shape - fix "
            "the parse, do not lower the number." % (want, got, len(blocks)))

    states = [(0, PH_INPUT, blocks[0][0]), (0, None, blocks[0][1])]
    for r in range(1, 10):
        b = blocks[r]
        for c, ph in enumerate((PH_START, PH_SBOX, PH_SROW, PH_MCOL, None)):
            states.append((r, ph, b[c]))
    return {"pt": pt, "key": key, "states": states}


# =====================================================================
#  NIST CAVP, PARSED
# =====================================================================
CAVP_FILES = [(kind, bits)
              for kind in ("GFSbox", "KeySbox", "VarKey", "VarTxt")
              for bits in (128, 192, 256)]


def parse_cavp(kind: str, bits: int) -> tuple[list[dict], list[dict]]:
    path = REF / ("cavp_ECB%s%d.rsp" % (kind, bits))
    if not path.exists():
        raise SystemExit(
            f"the oracle is missing: {path}\n"
            "Fetch https://csrc.nist.gov/CSRC/media/Projects/"
            "Cryptographic-Algorithm-Validation-Program/documents/aes/"
            "KAT_AES.zip and extract the ECB*.rsp files into "
            "RaspberryPi4/Reference/ with a cavp_ prefix.")
    enc, dec = [], []
    cur = None
    rec: dict = {}
    for ln in path.read_text(errors="replace").splitlines():
        s = ln.strip()
        if s == "[ENCRYPT]":
            cur = enc
            continue
        if s == "[DECRYPT]":
            cur = dec
            continue
        m = re.match(r"(\w+)\s*=\s*([0-9a-fA-F]*)$", s)
        if not m or cur is None:
            continue
        tag, val = m.group(1).upper(), m.group(2)
        if tag == "COUNT":
            rec = {"count": int(val)}
            cur.append(rec)
        elif tag in ("KEY", "PLAINTEXT", "CIPHERTEXT") and rec is not None:
            rec[tag] = bytes.fromhex(val)
    for name, lst in (("ENCRYPT", enc), ("DECRYPT", dec)):
        if not lst:
            raise SystemExit("%s: no %s section" % (path.name, name))
        for r in lst:
            if len(r.get("KEY", b"")) != bits // 8:
                raise SystemExit("%s: COUNT %d has a %d-byte key, expected %d"
                                 % (path.name, r["count"],
                                    len(r.get("KEY", b"")), bits // 8))
            if len(r.get("PLAINTEXT", b"")) != 16 or \
               len(r.get("CIPHERTEXT", b"")) != 16:
                raise SystemExit("%s: COUNT %d has a short block"
                                 % (path.name, r["count"]))
    return enc, dec


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
    attach_symbols(cpu, img, LOAD)

    uart = bytearray()

    def load(addr, size):
        # THE ALIGNMENT RULE.  With the MMU off every data access is
        # Device-nGnRnE and an unaligned wide one is a silent runaway on
        # the part; without this the gate models a machine more
        # permissive than the board it certifies.
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
    if b"aesharness done" not in uart:
        raise SystemExit("the harness returned without finishing:\n"
                         + uart.decode("latin-1"))

    out = []
    for i in range(count):
        a = H_RESULT + i * RES_STRIDE
        ret = sum(mem.get(a + j, 0) << (8 * j) for j in range(4))
        if ret >= 0x80000000:
            ret -= 0x100000000
        out.append((ret, bytes(mem.get(a + 4 + j, 0) for j in range(32))))
    return out, steps


def check(img: pathlib.Path, s: Script, quiet: bool = False,
          step_limit: int = STEP_LIMIT, note: str = "") -> tuple:
    if len(s) == 0:
        return [], 0
    got, steps = run(img, s.done(), len(s), step_limit)
    bad = []
    for i, label in enumerate(s.labels):
        want_ret, want_field, lanes = s.expect[i]
        ret, field = got[i]
        if ret != want_ret:
            bad.append("  %s\n      returned %d, expected %d"
                       % (label, ret, want_ret))
        elif field[:16] != want_field[:16]:
            bad.append("  %s\n      expected %s\n      got      %s"
                       % (label, want_field[:16].hex(), field[:16].hex()))
        elif lanes and field[16:32] != want_field[16:32]:
            bad.append("  %s\n      THE TWO BITSLICE LANES DISAGREE\n"
                       "      lane 0 %s\n      lane 1 %s"
                       % (label, field[:16].hex(), field[16:32].hex()))
        elif not lanes and field[16:32] != bytes([SENTINEL]) * 16:
            bad.append("  %s\n      the sentinel past the output was "
                       "overwritten: %s" % (label, field[16:32].hex()))
    if not quiet:
        print("  %-46s %4d vectors, %-9s %11d steps"
              % (note, len(s), "ALL PASS" if not bad else
                 "%d FAILED" % len(bad), steps))
    return bad, steps


# =====================================================================
#  THE VECTOR SETS
# =====================================================================
ENC_PHASES = [("start", PH_START), ("s_box", PH_SBOX),
              ("s_row", PH_SROW), ("m_col", PH_MCOL)]
DEC_PHASES = [("istart", PH_START), ("is_row", PH_SBOX),
              ("is_box", PH_SROW), ("ik_add", PH_MCOL)]


def script_fips_c(vectors, full: bool = True) -> Script:
    """FIPS-197 Appendix C: the key schedule, every intermediate, and
    the real entry points on the same vector."""
    s = Script()
    for v in vectors:
        nr, key, pt, ct = v["nr"], v["key"], v["pt"], v["ct"]
        tag = v["name"].split()[1]
        s.add(OP_SETKEY, "%s  AesSetKey" % tag, nr, None, key=key)

        # ---- the key schedule, read back round by round --------------
        for r in range(nr + 1):
            s.add(OP_KSCH, "%s  round[%d].k_sch" % (tag, r),
                  len(key) * 8, v["enc"][(r, "k_sch")], a0=r)

        # ---- the real entry points -----------------------------------
        s.add(OP_ENC, "%s  AesEncryptBlock" % tag, 16, ct, blk=pt, lanes=True)
        s.add(OP_DEC, "%s  AesDecryptBlock" % tag, 16, pt, blk=ct, lanes=True)

        # ---- the trace, step by step ---------------------------------
        s.add(OP_TRACE_ENC, "%s  round[0].input" % tag, len(key) * 8,
              v["enc"][(0, "input")], blk=pt, a0=0, a1=PH_INPUT)
        s.add(OP_TRACE_ENC, "%s  round[%d].output" % (tag, nr), len(key) * 8,
              ct, blk=pt, a0=nr, a1=PH_OUTPUT)
        s.add(OP_TRACE_DEC, "%s  round[0].iinput" % tag, len(key) * 8,
              v["dec"][(0, "iinput")], blk=ct, a0=0, a1=PH_INPUT)
        s.add(OP_TRACE_DEC, "%s  round[%d].ioutput" % (tag, nr), len(key) * 8,
              pt, blk=ct, a0=nr, a1=PH_OUTPUT)
        if not full:
            continue
        for r in range(1, nr + 1):
            for name, ph in ENC_PHASES:
                want = v["enc"].get((r, name))
                if want is None:
                    continue          # round Nr has no m_col, by design
                s.add(OP_TRACE_ENC, "%s  round[%d].%s" % (tag, r, name),
                      len(key) * 8, want, blk=pt, a0=r, a1=ph)
            for name, ph in DEC_PHASES:
                want = v["dec"].get((r, name))
                if want is None:
                    continue          # round Nr has no ik_add
                s.add(OP_TRACE_DEC, "%s  round[%d].%s" % (tag, r, name),
                      len(key) * 8, want, blk=ct, a0=r, a1=ph)
    return s


PH_NAME = {PH_INPUT: "input", PH_START: "start", PH_SBOX: "s_box",
           PH_SROW: "s_row", PH_MCOL: "m_col", PH_OUTPUT: "output"}

DIAG = (ROOT / "RaspberryPi4" / "Examples" / "Diagnostics"
        / "pi4AesSelfTest.pi4")


def check_diagnostic_vectors(fips) -> list:
    """The board diagnostic's typed vectors must match the document.

    RaspberryPi4/Examples/Diagnostics/pi4AesSelfTest.pi4 runs on bare
    metal, where there is no disk to parse from, so its vectors are
    TRANSCRIBED - which is the one thing these gates otherwise refuse to
    do.  This closes that hole from the desktop side: every AesKat call
    in that file is looked up in FIPS-197 Appendix C by its key, and its
    plaintext and ciphertext must match.

    A mistyped digit in the board program is a bad afternoon.  It fails
    on silicon, it looks like a silicon problem, and it is not one."""
    if not DIAG.exists():
        return ["  the board diagnostic %s is missing" % DIAG.name]
    src = DIAG.read_text(errors="replace")
    tri = re.findall(r'AesKat\(\s*"([0-9a-fA-F]+)",\s*"([0-9a-fA-F]+)",'
                     r'\s*"([0-9a-fA-F]+)"\)', src, re.S)
    bad = []
    if len(tri) != len(fips):
        bad.append("  %s has %d AesKat calls; Appendix C has %d vectors and "
                   "the diagnostic is meant to run all of them"
                   % (DIAG.name, len(tri), len(fips)))
    for k, p, c in tri:
        hit = [v for v in fips if v["key"].hex() == k.lower()]
        if not hit:
            bad.append("  %s: AesKat key %s is in no Appendix C vector"
                       % (DIAG.name, k))
            continue
        v = hit[0]
        if v["pt"].hex() != p.lower():
            bad.append("  %s: the %d-bit AesKat's plaintext\n"
                       "      typed    %s\n      document %s"
                       % (DIAG.name, len(v["key"]) * 8, p.lower(),
                          v["pt"].hex()))
        if v["ct"].hex() != c.lower():
            bad.append("  %s: the %d-bit AesKat's ciphertext\n"
                       "      typed    %s\n      document %s"
                       % (DIAG.name, len(v["key"]) * 8, c.lower(),
                          v["ct"].hex()))
    return bad


def validate_appendix_b(b) -> None:
    """Check the Appendix B reader against the table's own arithmetic,
    using nothing but XOR and a byte permutation.

    APPENDIX B AND APPENDIX C DO NOT SHARE AN EXAMPLE.  B works
    3243f6a8..., the AES submission's original demonstration vector,
    while C works 00112233...  So the two documents cannot check each
    other, and this reader - which has to cope with a five-column table
    that pdftotext lays out inconsistently - needs a check of its own.
    The first version of it was off by one round and produced forty
    plausible-looking wrong expectations.

    Three properties hold for ANY correct reading and are computable
    here without an AES implementation:

      1. round[1].start = input XOR round[0].k_sch
      2. round[r+1].start = round[r].m_col XOR round[r].k_sch
      3. round[r].s_row is round[r].s_box with row i rotated left by i

    A shift of one row, one column or one round breaks all three."""
    st = {}
    for r, ph, val in b["states"]:
        st[(r, ph)] = val

    if st[(0, PH_INPUT)] != b["pt"]:
        raise SystemExit("Appendix B: the input state is %s but the Input "
                         "line says %s"
                         % (st[(0, PH_INPUT)].hex(), b["pt"].hex()))
    if st[(0, None)] != b["key"]:
        raise SystemExit("Appendix B: round[0].k_sch is %s but the Key line "
                         "says %s" % (st[(0, None)].hex(), b["key"].hex()))

    def x(a, c):
        return bytes(p ^ q for p, q in zip(a, c))

    if st[(1, PH_START)] != x(st[(0, PH_INPUT)], st[(0, None)]):
        raise SystemExit("Appendix B: round[1].start is not input XOR "
                         "round[0].k_sch - the reader is misaligned")
    for r in range(1, 9):
        if st[(r + 1, PH_START)] != x(st[(r, PH_MCOL)], st[(r, None)]):
            raise SystemExit(
                "Appendix B: round[%d].start is not round[%d].m_col XOR "
                "round[%d].k_sch - the reader is misaligned" % (r + 1, r, r))
    for r in range(1, 10):
        sb, sr = st[(r, PH_SBOX)], st[(r, PH_SROW)]
        want = bytes(sb[((c + i) % 4) * 4 + i] for c in range(4)
                     for i in range(4))
        if sr != want:
            raise SystemExit(
                "Appendix B: round[%d].s_row is not ShiftRows of "
                "round[%d].s_box - the reader is misaligned" % (r, r))


def script_fips_b(b) -> Script:
    """FIPS-197 (2023) Appendix B, one AES-128 encryption, run against
    the trace at every step the table states."""
    s = Script()
    s.add(OP_SETKEY, "AppB  AesSetKey", 10, None, key=b["key"])
    for r, ph, want in b["states"]:
        if ph is None:
            s.add(OP_KSCH, "AppB  round[%d].k_sch" % r, 128, want, a0=r)
        else:
            s.add(OP_TRACE_ENC, "AppB  round[%d].%s" % (r, PH_NAME[ph]),
                  128, want, blk=b["pt"], a0=r, a1=ph)
    return s


def script_cavp(kind: str, bits: int, stride: int = 1) -> Script:
    enc, dec = parse_cavp(kind, bits)
    s = Script()
    for direction, lst in (("ENCRYPT", enc), ("DECRYPT", dec)):
        last_key = None
        for rec in lst[::stride]:
            if rec["KEY"] != last_key:
                s.add(OP_SETKEY, "CAVP %s%d %s COUNT %d  AesSetKey"
                      % (kind, bits, direction, rec["count"]),
                      {128: 10, 192: 12, 256: 14}[bits], None, key=rec["KEY"])
                last_key = rec["KEY"]
            if direction == "ENCRYPT":
                s.add(OP_ENC, "CAVP %s%d ENCRYPT COUNT %d"
                      % (kind, bits, rec["count"]), 16, rec["CIPHERTEXT"],
                      blk=rec["PLAINTEXT"], lanes=True)
            else:
                s.add(OP_DEC, "CAVP %s%d DECRYPT COUNT %d"
                      % (kind, bits, rec["count"]), 16, rec["PLAINTEXT"],
                      blk=rec["CIPHERTEXT"], lanes=True)
    return s


# ---------------------------------------------------------------------
#  REFUSALS.  A bad key length must be refused, must install nothing,
#  and must leave the block entries refusing too.
# ---------------------------------------------------------------------
def script_refusals(vectors) -> Script:
    v = vectors[0]
    s = Script()
    for bad in (0, 1, 8, 15, 17, 20, 23, 25, 31, 33, 64, -1):
        s.add(OP_WIPE, "REFUSE  wipe before keylen %d" % bad, 0, None)
        s.add(OP_SETKEY, "REFUSE  AesSetKey keylen %d" % bad, 0, None,
              key=b"\x11" * 32, keylen=bad)
        s.add(OP_ENC, "REFUSE  AesEncryptBlock after keylen %d" % bad,
              0, None, blk=v["pt"])
        s.add(OP_DEC, "REFUSE  AesDecryptBlock after keylen %d" % bad,
              0, None, blk=v["ct"])
    # AesWipe must actually forget: a good key, then a wipe, then the
    # block entries must refuse.
    s.add(OP_SETKEY, "WIPE  install a good key", 10, None, key=v["key"])
    s.add(OP_ENC, "WIPE  it works before the wipe", 16, v["ct"],
          blk=v["pt"], lanes=True)
    s.add(OP_WIPE, "WIPE  AesWipe", 0, None)
    s.add(OP_ENC, "WIPE  AesEncryptBlock refuses after", 0, None, blk=v["pt"])
    s.add(OP_DEC, "WIPE  AesDecryptBlock refuses after", 0, None, blk=v["ct"])
    # And a good key after a bad one must work, so a refusal does not
    # wedge the module.
    s.add(OP_SETKEY, "RECOVER  bad key length", 0, None,
          key=b"\x22" * 32, keylen=20)
    s.add(OP_SETKEY, "RECOVER  good key after it", 10, None, key=v["key"])
    s.add(OP_ENC, "RECOVER  and it encrypts", 16, v["ct"],
          blk=v["pt"], lanes=True)
    return s


# =====================================================================
#  THE CONSTANT-TIME CHECK
# =====================================================================
#  Two keys and two plaintexts of wildly different Hamming weight, each
#  run on its own, and the instruction counts must be EXACTLY equal.
#
#  WHAT THIS CATCHES: a branch on a key or data bit, a secret-indexed
#  access with a variable cost, a compiler transformation that turned a
#  masked select into a conditional branch.  Any of those changes the
#  count.
#
#  WHAT IT DOES NOT CATCH: anything about real hardware.  The model
#  counts instructions retired; a Cortex-A72 has caches, a store
#  buffer, and a branch predictor, none of which are here.  An equal
#  instruction count is necessary for constant time and nowhere near
#  sufficient - it is simply the strongest statement obtainable without
#  a board, and it is a genuine regression detector.
def timing_check(img: pathlib.Path) -> int:
    cases = [
        ("all-zero key, all-zero block", b"\x00" * 16, b"\x00" * 16),
        ("all-ones key, all-ones block", b"\xFF" * 16, b"\xFF" * 16),
        ("all-zero key, all-ones block", b"\x00" * 16, b"\xFF" * 16),
        ("all-ones key, all-zero block", b"\xFF" * 16, b"\x00" * 16),
        ("counting key, counting block", bytes(range(16)),
         bytes(range(240, 256))),
        ("one-bit key, one-bit block", b"\x80" + b"\x00" * 15,
         b"\x00" * 15 + b"\x01"),
    ]
    print("CONSTANT-TIME CHECK - instruction counts under the model")
    counts = []
    for name, key, blk in cases:
        s = Script()
        s.add(OP_SETKEY, name, 10, None, key=key)
        s.add(OP_ENC, name, 16, None, blk=blk, lanes=True)
        s.add(OP_DEC, name, 16, None, blk=blk, lanes=True)
        # The expectations are unknown here on purpose - this measures,
        # it does not verify - so run() is used directly.
        _, steps = run(img, s.done(), len(s))
        counts.append((name, steps))
        print("  %-34s %11d steps" % (name, steps))
    base = counts[0][1]
    bad = [n for n, c in counts if c != base]
    if bad:
        print("  *** THE COUNTS DIFFER.  Something in the compiled code "
              "depends on key or data bits:")
        for n in bad:
            print("        %s" % n)
        return 1
    print("  all %d cases identical at %d steps" % (len(counts), base))
    return 0


# =====================================================================
#  MUTATIONS
# =====================================================================
#  Each entry is (name, anchor, replacement, expected occurrences, why).
#  The anchor must occur exactly the stated number of times or the
#  mutation is reported as unappliable and counted as a failure - an
#  anchor that has silently stopped matching is a mutation that has
#  stopped testing anything.
MUTATIONS = [
    ("MixColumns in the final round",
     "  AesSbox(q)\n  AesShiftRows(q)\n  AesAddRoundKey(q, @secAesSkExp[0] + AesNumRounds",
     "  AesSbox(q)\n  AesShiftRows(q)\n  AesMixColumns(q)\n  AesAddRoundKey(q, @secAesSkExp[0] + AesNumRounds", 1,
     "the single most commonly mistranslated line in AES.  The TRACE "
     "cannot see it - the harness runs its own loop - so this is the "
     "mutation that proves the real entry points are being checked too"),

    # ---- THE MASK SCOREBOARD, MEASURED RATHER THAN ARGUED ------------
    #
    #   AesLsl's output mask removed .................... 0 of 290
    #   AesLsr masking after the shift instead of before . 0 of 290
    #   BOTH at once .................................... red
    #
    # NEITHER WIDTH MASK IS INDIVIDUALLY OBSERVABLE AND TOGETHER THEY
    # ARE, and the reason is worth knowing rather than being surprised
    # by twice.  The only call site that can spill is AesRotr's left
    # half, and the rubbish it leaves lives in bits 32..62.  Nothing in
    # the file brings a bit back DOWN except a right shift, and AesLsr
    # masks its input before shifting - so with EITHER mask in place the
    # dirt is unreachable by any caller.  Remove both and it lands in
    # the answer.
    #
    # KEEP BOTH.  They are not belt and braces, they are two halves of
    # one argument, and the invariant "every 32-bit value is clean at
    # the point it is produced" is what makes this file checkable a line
    # at a time instead of by tracing where rubbish can travel.  The
    # first sweep reported the AesLsl entry as a hole in the gate; it is
    # not, and the third entry below is the proof.  sha1.pi4's header
    # records the identical shape for its rotate.
    ("the left-shift mask in AesLsl removed",
     "  ProcedureReturn (x << n) & #AES_W32",
     "  ProcedureReturn (x << n)", 1,
     "EXPECTED GREEN, half of the mask scoreboard.  The spill can only "
     "travel upward and AesLsr masks its input before shifting, so no "
     "bit any caller reads is affected"),

    ("AesLsr masks AFTER the shift instead of before",
     "  ProcedureReturn (x & #AES_W32) >> n",
     "  ProcedureReturn (x >> n) & #AES_W32", 1,
     "EXPECTED GREEN, the other half.  Under the invariant every value "
     "reaching AesLsr is already clean, so the two spellings are the "
     "same function.  The order matters only for a dirty input - which "
     "is what the next mutation creates"),

    ("BOTH width masks removed at once",
     ("  ProcedureReturn (x & #AES_W32) >> n",
      "  ProcedureReturn (x << n) & #AES_W32"),
     ("  ProcedureReturn (x >> n) & #AES_W32",
      "  ProcedureReturn (x << n)"), (1, 1),
     "THE PAIR IS OBSERVABLE EVEN THOUGH NEITHER HALF IS.  With AesLsl "
     "no longer discarding the spill and AesLsr no longer refusing to "
     "read it, bits 32..62 come back down into the digest"),

    ("AesRotr rotates the wrong way",
     "  ProcedureReturn AesLsl(x, 32 - n) | AesLsr(x, n)",
     "  ProcedureReturn AesLsl(x, n) | AesLsr(x, 32 - n)", 1,
     "MixColumns, InvMixColumns and the key schedule all go through "
     "this one procedure"),

    ("the stride constant is 4, as it is on the 32-bit families",
     "#AES_WORD     = 8", "#AES_WORD     = 4", 1,
     "reads the top half of q[0] as if it were q[1] - the trap "
     "sha1.pi4's header names as point 1"),

    ("AddRoundKey indexes the schedule without the plane stride",
     "@secAesSkExp[0] + u * #AES_QWORDS * #AES_WORD",
     "@secAesSkExp[0] + u * #AES_WORD", 2,
     "every round after the first would use the wrong key"),

    ("Rcon[8] is $80, not $1B",
     "  AesRcon[8] = $1B", "  AesRcon[8] = $80", 1,
     "$1B is where the round constant wraps in GF(2^8); doubling to "
     "$80 and then to $100 without reduction is the classic mistake, "
     "and it only shows from round 9"),

    ("the round constant is always Rcon[0]",
     "tmp = AesSubWord(tmp) ! AesRcon[k]",
     "tmp = AesSubWord(tmp) ! AesRcon[0]", 1,
     "the key schedule would repeat"),

    ("RotWord rotates by 24 instead of 8",
     "      tmp = AesRotr(tmp, 8)", "      tmp = AesRotr(tmp, 24)", 1,
     "RotWord on a little-endian word is a rotate right by 8"),

    ("the AES-256 second SubWord is applied at nk > 4",
     "      If nk > 6 And j = 4", "      If nk > 4 And j = 4", 1,
     "this clause exists only for AES-256; firing it for AES-192 "
     "breaks the 192-bit schedule and leaves 128 and 256 correct"),

    ("the second key-schedule lane is not filled",
     "    secAesKeyTmp[i * 2 + 1] = tmp\n    j = j + 1",
     "    secAesKeyTmp[i * 2 + 1] = 0\n    j = j + 1", 1,
     "the compression keeps lane 0's even bits and lane 1's odd bits, "
     "so half of every round key would be zero"),

    ("InvShiftRows is ShiftRows",
     "    PokeI(q + i * #AES_WORD, (x & $000000FF) | AesLsl(x & $00003F00, 2) | AesLsr(x & $0000C000, 6) | AesLsl(x & $000F0000, 4) | AesLsr(x & $00F00000, 4) | AesLsl(x & $03000000, 6) | AesLsr(x & $FC000000, 2))",
     "    PokeI(q + i * #AES_WORD, (x & $000000FF) | AesLsr(x & $0000FC00, 2) | AesLsl(x & $00000300, 6) | AesLsr(x & $00F00000, 4) | AesLsl(x & $000F0000, 4) | AesLsr(x & $C0000000, 6) | AesLsl(x & $3F000000, 2))", 1,
     "rows 1 and 3 shift the other way in the inverse; only decrypt "
     "can see this"),

    ("the inverse S-box drops its second B() transform",
     "  AesSbox(q)\n\n  ; ---- and B() again, on the way out",
     "  AesSbox(q)\n  ProcedureReturn\n\n  ; ---- and B() again, on the way out", 1,
     "iS(x) = B(S(B(x ^ 63)) ^ 63) needs B on both sides"),

    ("the inverse S-box complements the wrong bit-plane",
     "  q5 = PeekI(q + 5 * #AES_WORD) ! #AES_W32\n  q6 = PeekI(q + 6 * #AES_WORD) ! #AES_W32\n  q7 = PeekI(q + 7 * #AES_WORD)\n  PokeI(q + 7 * #AES_WORD, (q1 ! q4) ! q6)\n  PokeI(q + 6 * #AES_WORD, (q0 ! q3) ! q5)\n  PokeI(q + 5 * #AES_WORD, (q7 ! q2) ! q4)\n  PokeI(q + 4 * #AES_WORD, (q6 ! q1) ! q3)\n  PokeI(q + 3 * #AES_WORD, (q5 ! q0) ! q2)\n  PokeI(q + 2 * #AES_WORD, (q4 ! q7) ! q1)\n  PokeI(q + 1 * #AES_WORD, (q3 ! q6) ! q0)\n  PokeI(q + 0 * #AES_WORD, (q2 ! q5) ! q7)\n\n  AesSbox(q)",
     "  q5 = PeekI(q + 5 * #AES_WORD)\n  q6 = PeekI(q + 6 * #AES_WORD) ! #AES_W32\n  q7 = PeekI(q + 7 * #AES_WORD) ! #AES_W32\n  PokeI(q + 7 * #AES_WORD, (q1 ! q4) ! q6)\n  PokeI(q + 6 * #AES_WORD, (q0 ! q3) ! q5)\n  PokeI(q + 5 * #AES_WORD, (q7 ! q2) ! q4)\n  PokeI(q + 4 * #AES_WORD, (q6 ! q1) ! q3)\n  PokeI(q + 3 * #AES_WORD, (q5 ! q0) ! q2)\n  PokeI(q + 2 * #AES_WORD, (q4 ! q7) ! q1)\n  PokeI(q + 1 * #AES_WORD, (q3 ! q6) ! q0)\n  PokeI(q + 0 * #AES_WORD, (q2 ! q5) ! q7)\n\n  AesSbox(q)", 1,
     "the ^ $63 is four specific planes - 0, 1, 5 and 6, because $63 "
     "is 0110 0011"),

    ("the decrypt loop uses the equivalent inverse cipher's order",
     "    AesAddRoundKey(q, @secAesSkExp[0] + u * #AES_QWORDS * #AES_WORD)\n    AesInvMixColumns(q)",
     "    AesInvMixColumns(q)\n    AesAddRoundKey(q, @secAesSkExp[0] + u * #AES_QWORDS * #AES_WORD)", 1,
     "FIPS-197 5.3.5's equivalent inverse cipher swaps these two and "
     "compensates with a DIFFERENT key schedule; swapping them alone is "
     "simply wrong"),

    ("MixColumns loses one term",
     "  PokeI(q + 3 * #AES_WORD, q2 ! r2 ! q7 ! r7 ! r3 ! AesRotr(q3 ! r3, 16))",
     "  PokeI(q + 3 * #AES_WORD, q2 ! r2 ! q7 ! r3 ! AesRotr(q3 ! r3, 16))", 1,
     "one dropped XOR in one plane of one row"),

    ("InvMixColumns loses one term",
     "  PokeI(q + 6 * #AES_WORD, q3 ! q4 ! q5 ! q7 ! r3 ! r5 ! r6 ! r7 ! AesRotr(q3 ! q4 ! q6 ! q7 ! r3 ! r6 ! r7, 16))",
     "  PokeI(q + 6 * #AES_WORD, q3 ! q4 ! q5 ! q7 ! r3 ! r5 ! r6 ! AesRotr(q3 ! q4 ! q6 ! q7 ! r3 ! r6 ! r7, 16))", 1,
     "the same, on the decrypt side"),

    ("the orthogonalisation loses its last stage",
     "  AesSwapN(q, 3, 7, $0F0F0F0F, $F0F0F0F0, 4)",
     "", 1,
     "one of twelve swaps; the bitslice would be half transposed"),

    ("AesEncryptBlock does not refuse without a key",
     "Procedure.i AesEncryptBlock(src.i, dst.i)\n  If AesNumRounds = 0\n    ProcedureReturn 0\n  EndIf",
     "Procedure.i AesEncryptBlock(src.i, dst.i)", 1,
     "encrypting with no key must be refused, not done with whatever "
     "the schedule happens to contain"),

    ("a bad key length is accepted",
     "  If numRounds = 0\n    ProcedureReturn 0\n  EndIf",
     "  If numRounds = 0\n    numRounds = 10\n  EndIf", 1,
     "a 20-byte key must be refused, not silently treated as 128-bit"),

    ("AesWipe does not forget the round count",
     "  AesNumRounds = 0\n  AesKeyLen = 0\nEndProcedure",
     "  AesKeyLen = 0\nEndProcedure", 1,
     "a wipe that leaves the module willing to encrypt has not wiped"),

    ("the second bitslice lane gets a different block",
     "  AesQ[0] = w0\n  AesQ[1] = w0",
     "  AesQ[0] = w0\n  AesQ[1] = w0 ! 1", 1,
     "lane 1 must be an exact copy of lane 0; this is what the lane "
     "check is for, and lane 0's answer is unaffected"),

    ("AesStoreBlock emits lane 1 instead of lane 0",
     "  AesEnc32le(dst,      AesQ[0])\n  AesEnc32le(dst + 4,  AesQ[2])\n  AesEnc32le(dst + 8,  AesQ[4])\n  AesEnc32le(dst + 12, AesQ[6])",
     "  AesEnc32le(dst,      AesQ[1])\n  AesEnc32le(dst + 4,  AesQ[3])\n  AesEnc32le(dst + 8,  AesQ[5])\n  AesEnc32le(dst + 12, AesQ[7])", 1,
     "EXPECTED GREEN.  AesLoadBlock puts the same block in both lanes, "
     "so the two are equal by construction and reading either is "
     "correct.  It is recorded rather than deleted because the day "
     "somebody adds a two-block entry point, this stops being harmless "
     "and the gate should be the thing that says so"),
]

EXPECT_GREEN = {
    "the left-shift mask in AesLsl removed",
    "AesLsr masks AFTER the shift instead of before",
    "AesStoreBlock emits lane 1 instead of lane 0",
}


def script_mutation_set(fips, cavp_sample) -> Script:
    """A small set with wide reach: all three key sizes, every
    intermediate for AES-128, the real entry points and the key
    schedule for all three, a handful of CAVP blocks, and the
    refusals."""
    s = Script()
    for v in fips:
        nr, key, pt, ct = v["nr"], v["key"], v["pt"], v["ct"]
        tag = v["name"].split()[1]
        s.add(OP_SETKEY, "%s  AesSetKey" % tag, nr, None, key=key)
        for r in range(nr + 1):
            s.add(OP_KSCH, "%s  round[%d].k_sch" % (tag, r),
                  len(key) * 8, v["enc"][(r, "k_sch")], a0=r)
        s.add(OP_ENC, "%s  AesEncryptBlock" % tag, 16, ct, blk=pt, lanes=True)
        s.add(OP_DEC, "%s  AesDecryptBlock" % tag, 16, pt, blk=ct, lanes=True)
        if v["nk"] == 4:
            for r in range(1, nr + 1):
                for name, ph in ENC_PHASES:
                    want = v["enc"].get((r, name))
                    if want is not None:
                        s.add(OP_TRACE_ENC, "%s  round[%d].%s" % (tag, r, name),
                              128, want, blk=pt, a0=r, a1=ph)
                for name, ph in DEC_PHASES:
                    want = v["dec"].get((r, name))
                    if want is not None:
                        s.add(OP_TRACE_DEC, "%s  round[%d].%s" % (tag, r, name),
                              128, want, blk=ct, a0=r, a1=ph)
    for label, bits, key, pt, ct in cavp_sample:
        s.add(OP_SETKEY, label + "  AesSetKey",
              {128: 10, 192: 12, 256: 14}[bits], None, key=key)
        s.add(OP_ENC, label + "  ENCRYPT", 16, ct, blk=pt, lanes=True)
        s.add(OP_DEC, label + "  DECRYPT", 16, pt, blk=ct, lanes=True)
    for r in script_refusals(fips).labels:
        pass
    ref = script_refusals(fips)
    s.buf += ref.buf
    s.labels += ref.labels
    s.expect += ref.expect
    return s


def cavp_sample() -> list:
    """A few CAVP blocks per key size, taken from the ends and the
    middle of each file so that a mutation which only shows for some
    keys still has something to fail on."""
    out = []
    for bits in (128, 192, 256):
        for kind in ("GFSbox", "KeySbox", "VarKey", "VarTxt"):
            enc, _ = parse_cavp(kind, bits)
            for idx in (0, len(enc) // 2, len(enc) - 1):
                r = enc[idx]
                out.append(("CAVP %s%d COUNT %d" % (kind, bits, r["count"]),
                            bits, r["KEY"], r["PLAINTEXT"], r["CIPHERTEXT"]))
    return out


def mutation_budget(clean_steps: int) -> int:
    """A tight budget: no mutation here can loop, and the most expensive
    legitimate one is barely above the clean run, so four times is
    generous and turns any accidental runaway into a fast RED."""
    return max(clean_steps * 4, 50_000_000)


def mutate_one(idx: int, workdir: pathlib.Path) -> int:
    """Score ONE mutation, in a directory of this worker's own, and
    print a single machine-readable verdict line for the parent.

    This is the entry point a64_mutate_pool.run_parallel spawns.  It
    reads the library, writes the MUTATED COPY into workdir, and never
    opens the library for writing."""
    name, old, new, count, why = MUTATIONS[idx]
    src = LIB.read_text(encoding="utf-8")
    mutated, why_not = pool.apply_edits(src, old, new, count)
    if why_not:
        print("%sERROR	CANNOT APPLY - %s" % (pool.VERDICT, why_not))
        return 1

    fips = parse_fips_appendix_c()
    s = script_mutation_set(fips, cavp_sample())

    # RESOLVE FIRST.  The parent hands down whatever path it built;
    # XIncludeFile wants a ROOT-relative POSIX path and relative_to
    # needs both sides absolute.
    workdir = pathlib.Path(workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    mut = workdir / "aes_mut.pi4"
    mut.write_text(mutated, encoding="utf-8")
    include = mut.relative_to(ROOT).as_posix()

    # The clean step count is measured once by the parent and handed
    # down; recomputing it per worker would double the sweep's cost for
    # a number that cannot change.
    budget = int(os.environ.get("AES_MUT_BUDGET", "60000000"))

    red = None
    note = ""
    try:
        build(include, workdir / "aesharness_mut.pi4",
              workdir / "aescheck_mut.img")
    except SystemExit:
        red, note = True, "refused to build"
    if red is None:
        try:
            bad, msteps = check(workdir / "aescheck_mut.img", s, quiet=True,
                                step_limit=budget)
            red = len(bad) > 0
            note = "%d of %d wrong" % (len(bad), len(s))
        except SystemExit:
            red, note = True, "over the step budget"
        except AlignmentFault:
            # A MUTANT THAT FAULTS IS RED, NOT A CRASH.  The stride
            # mutation reads a 64-bit word four bytes off a boundary,
            # which with the MMU off is a fault with no vector
            # installed - on the board, silence.
            red, note = True, "unaligned access - on the board, silence"
    print("%s%s	%s" % (pool.VERDICT, "RED" if red else "GREEN", note))
    return 0


def mutate(fips, sample, clean_steps: int) -> int:
    """The control has already passed.  Fan the mutations out across the
    machine and collect the verdicts in index order.

    ONE WORKER PER MUTATION, ONE DIRECTORY PER WORKER.  See
    a64_mutate_pool for why it is subprocesses and why the directories
    matter."""
    budget = mutation_budget(clean_steps)
    os.environ["AES_MUT_BUDGET"] = str(budget)
    procs = pool.worker_count()
    root = WORK / "aes"
    t0 = time.time()
    print("MUTATION TEST - %d mutations, %d vectors each, step budget %d "
          "(clean run was %d)"
          % (len(MUTATIONS), len(script_mutation_set(fips, sample)), budget,
             clean_steps))
    print("  %d workers on %d logical CPUs; each mutant is a COPY in "
          "%s/<n>/ and the library is never opened for writing"
          % (procs, os.cpu_count() or 0, root.relative_to(ROOT).as_posix()))

    lines = pool.run_parallel(pathlib.Path(__file__).resolve(), ROOT,
                              len(MUTATIONS), root, procs, label="mutation",
                              extra_args=["--compiler", PMFC])

    failures = 0
    print()
    for (name, old, new, count, why), line in zip(MUTATIONS, lines):
        parts = line.split("	")
        verdict = parts[1] if len(parts) > 1 else "ERROR"
        note = parts[2] if len(parts) > 2 else ""
        if verdict == "ERROR":
            print("  %-52s *** %s ***" % (name[:52], note))
            failures += 1
            continue
        red = verdict == "RED"
        want_red = name not in EXPECT_GREEN
        if red == want_red:
            print("  %-52s %-5s (%s)" % (name[:52], verdict, note))
            if not want_red:
                print("        expected green: %s" % why)
        else:
            failures += 1
            print("  %-52s *** %s ***"
                  % (name[:52], "GREEN - THE GATE DID NOT SEE IT"
                     if want_red else "RED, EXPECTED GREEN"))
            print("        %s" % why)

    alive = pool.report_reaped(root)
    print()
    print("  %d mutations across %d workers in %.0f s (serial would have "
          "been about %.0f s)"
          % (len(MUTATIONS), procs, time.time() - t0,
             len(MUTATIONS) * (clean_steps / 445000.0)))
    print("  pool reaped: %s build processes still alive"
          % ("could not check" if alive < 0 else alive))
    if alive > 0:
        print("  *** WORKERS WERE LEFT BEHIND - that is a defect, not noise")
        failures += 1
    return failures


# =====================================================================
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
    ap.add_argument("--fips", action="store_true",
                    help="FIPS-197 Appendix B and C only; no CAVP")
    ap.add_argument("--quick", action="store_true",
                    help="FIPS plus every 8th CAVP vector")
    ap.add_argument("--timing", action="store_true",
                    help="the constant-instruction-count check")
    ap.add_argument("--mutate", action="store_true")
    # The two below are how a64_mutate_pool spawns one worker; they are
    # not meant to be typed by hand.
    ap.add_argument("--mutate-one", type=int, default=None, dest="mutate_one",
                    help="score a single mutation by index and print one "
                         "verdict line (used by the parallel sweep)")
    ap.add_argument("--mutate-dir", default=None, dest="mutate_dir",
                    help="the directory that worker owns")
    args = ap.parse_args()
    globals()["PMFC"] = resolve_compiler(args.compiler)
    apply_target(globals(), args.target)
    # A GATE THAT DOES NOT SAY WHICH BOARD IT GRADED IS A RESULT
    # THAT CAN BE FILED AGAINST THE WRONG ONE.  Printed before any
    # work, so it is at the top of the transcript even on a failure.
    print("[gate] target %s - %s, image at $%08X, stack $%08X"
          % (TARGET_NAME, TARGET_WHAT, LOAD, STACK))

    # LINE-BUFFER STDOUT.  These gates run for minutes and print a line
    # per group so that somebody watching can see they are alive; piped
    # into a file or a pager, Python block-buffers and the progress
    # arrives all at once at the end, which is the same as no progress.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, ValueError):
        pass

    WORK.mkdir(exist_ok=True)

    # ONE WORKER OF A PARALLEL SWEEP.  It builds in its own directory
    # and prints exactly one verdict line; it must not touch the shared
    # _work/aescheck.img the parent is using.
    if args.mutate_one is not None:
        if not args.mutate_dir:
            raise SystemExit("--mutate-one needs --mutate-dir")
        return mutate_one(args.mutate_one, pathlib.Path(args.mutate_dir))

    t0 = time.time()
    build("RaspberryPi4/Lib/aes.pi4", WORK / "aesharness.pi4",
          WORK / "aescheck.img")
    img = WORK / "aescheck.img"

    if args.timing:
        return timing_check(img)

    fips = parse_fips_appendix_c()

    if args.mutate:
        sample = cavp_sample()
        s = script_mutation_set(fips, sample)
        bad, clean = check(img, s, note="the unmutated library")
        if bad:
            print("the unmutated library is already failing; fix that first")
            print("\n".join(bad[:10]))
            return 1
        return 1 if mutate(fips, sample, clean) else 0

    print("AES gate - RaspberryPi4/Lib/aes.pi4")
    print("  oracles, all parsed from disk:")
    print("    FIPS-197 Appendix C intermediates  fips197-2001.txt")
    print("    FIPS-197 Appendix B state table    fips197.txt (2023)")
    if not args.fips:
        print("    NIST CAVP AESAVS ECB known answers cavp_ECB*.rsp")
    print()

    failures = []
    total = 0

    dbad = check_diagnostic_vectors(fips)
    print("  %-46s %4d vectors, %s"
          % ("the board diagnostic's typed vectors",
             len(fips), "ALL MATCH THE DOCUMENT" if not dbad
             else "%d DISAGREE" % len(dbad)))
    failures += dbad

    b = parse_fips_appendix_b()
    validate_appendix_b(b)
    sb = script_fips_b(b)
    bad, st = check(img, sb, note="FIPS-197 (2023) Appendix B")
    failures += bad
    total += st

    for v in fips:
        s = script_fips_c([v])
        bad, st = check(img, s, note="FIPS-197 Appendix C  " + v["name"])
        failures += bad
        total += st

    s = script_refusals(fips)
    bad, st = check(img, s, note="refusals and wipes")
    failures += bad
    total += st

    if not args.fips:
        stride = 8 if args.quick else 1
        for kind, bits in CAVP_FILES:
            s = script_cavp(kind, bits, stride)
            bad, st = check(img, s,
                            note="CAVP ECB%s%d%s"
                                 % (kind, bits,
                                    "  (every 8th)" if stride > 1 else ""))
            failures += bad
            total += st

    print()
    print("  %d model instructions, %.1f s" % (total, time.time() - t0))
    if failures:
        print("\nFAILURES")
        print("\n".join(failures[:40]))
        if len(failures) > 40:
            print("  ... and %d more" % (len(failures) - 40))
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

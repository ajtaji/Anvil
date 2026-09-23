#!/usr/bin/env python3
"""Executable gate for RaspberryPi4/Lib/keywrap.pi4 - RFC 3394 AES Key
Wrap and Key Unwrap.

WHY THIS FILE IS WRITTEN THE WAY IT IS

  THE PUBLISHED ORACLE IS RFC 3394 SECTION 4, PARSED OFF THE DISK.  All
  six vectors are read out of RaspberryPi4/Reference/rfc3394.txt at run
  time: the KEK, the key data, the ciphertext, AND every intermediate
  the document prints.  Nothing is transcribed.  This tree has been
  bitten by a bad transcription before and caught it the same way.

  THE SIX COVER EVERY COMBINATION THE DOCUMENT STATES: 128-bit key data
  under a 128-, 192- and 256-bit KEK; 192-bit key data under a 192- and
  a 256-bit KEK; and 256-bit key data under a 256-bit KEK.  That is
  n = 2, 3 and 4 registers and all three AES key lengths.

  THE INTERMEDIATES ARE USED, NOT JUST THE ANSWER.  RFC 3394 prints, for
  every one of the 6n steps, the integrity register A and every R
  register - "In", "Enc" and "XorT" on the wrap side, "In", "XorT" and
  "Dec" on the unwrap side.  The harness can stop after any number of
  completed steps and report A || R[1..n], so a wrap that goes wrong at
  step 5 is reported at step 5.

  HOW THE PARSE CHECKS ITSELF.  Four things the document states twice
  must agree, and the parse stops if any of them does not:

    * the last XorT row of the wrap IS the ciphertext, and the document
      also prints the ciphertext in its Output block;
    * the last Dec row of the unwrap has A = A6A6A6A6A6A6A6A6 and its R
      registers are the key data, which the document also prints;
    * the first In row of the wrap is IV || key data;
    * the first In row of the unwrap is the ciphertext.

  Between them those pin the row ordering, the register ordering and
  the continuation-line handling, which is where a table parser goes
  wrong.

  A SECOND ORACLE IS USED, AND IT IS VALIDATED BEFORE IT IS TRUSTED.
  RFC 3394's six vectors stop at n = 4, and some defects only show for
  larger n - see THE BIG-n VECTOR below.  The extra shapes come from
  OpenSSL, through Python's `cryptography` package, which is
  independent of this tree but is not a published document.  So it is
  checked first: this gate requires it to reproduce all six RFC vectors,
  wrap and unwrap, before it will use it for anything.  If that fails
  the gate stops; it never falls back to an unvalidated oracle.

  THE BIG-n VECTOR, AND WHY IT IS WORTH THE MINUTE IT COSTS.  The step
  counter t runs from 1 to 6n and is XORed into A as a 64-bit
  big-endian integer.  Every published vector has n <= 4, so t never
  exceeds 24 and ONLY THE LOWEST BYTE OF A IS EVER TOUCHED.  An
  implementation that XORed one byte instead of eight would pass all
  six RFC vectors, pass its own round trips, and then disagree with
  every other implementation in the world the first time it met key
  data longer than 340 bytes.  So the gate carries a 344-byte case
  (n = 43, t up to 258) from the validated oracle, and the mutation
  table has the one-byte defect in it precisely to show that the
  published set alone would have gone green.

  THE FAILURE PATH IS TESTED HARDER THAN THE SUCCESS PATH.  RFC 3394
  section 5 says an unwrap that fails its integrity check "MUST return
  an error, and it MUST NOT return any key data".  A corrupted blob must
  return 0 AND leave the output buffer entirely zero.  A library that
  returned the plaintext-shaped garbage anyway would be a decryption
  oracle, and it would pass a gate that only checked the return value.

  THE CORRUPTED BITS ARE CHOSEN, NOT SWEPT.  Flipping all 8n + 64 of
  them would be thousands of unwraps under this model for no extra
  coverage.  What is flipped is three bits of the integrity register A,
  one bit in EVERY R register - so a register the loop never visited
  would show up - the last bit of the blob, and, where n > 2, a
  truncation by one register, which is a length change that still
  parses.

  IN-PLACE IS TESTED, because both entry points document that dst may
  equal the input buffer and both rely on a copy running in the right
  direction to make that true.  A forward copy in the wrap would
  silently corrupt exactly the in-place case and nothing else.

  MUTATIONS RUN ON A COPY.  This gate NEVER opens keywrap.pi4 for
  writing.  A runner that edits the real file and restores it
  afterwards leaves the mutant in place the first time it is killed.

WHAT THIS GATE DOES NOT SAY

  * That any of this runs on silicon.
  * Anything about the constant-time property of the integrity compare.
    The compare has no early exit, which is visible in the source; no
    timing measurement is attempted here.

HOW LONG THESE TAKE, MEASURED ON 2026-08-28

  --quick        the six RFC vectors and the refusals, no traces and
                 no big-n case.  Under a minute.
  (no flag)      everything, including every printed intermediate and
                 the 344-byte case.  SEVERAL MINUTES.
  --mutate       a reduced set, rebuilt once per mutation, FANNED OUT
                 across os.cpu_count() - 2 workers.  402 s for all
                 fifteen on 2026-08-28, where serial was about 2,366 s.
                 The two non-terminating mutants each burn the full
                 step budget, which is what sets that wall clock.

Run: python tools/a64/a64_keywrap_check.py
     python tools/a64/a64_keywrap_check.py --quick
     python tools/a64/a64_keywrap_check.py --mutate
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
LIB = ROOT / "RaspberryPi4" / "Lib" / "keywrap.pi4"
REF = ROOT / "RaspberryPi4" / "Reference"
RFC3394 = REF / "rfc3394.txt"
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

REC_HEAD = 48               # op, keklen, datalen, arg, kek[32]
RES_DATA = 560              # the output field
RES_STRIDE = 4 + RES_DATA
SENTINEL = 0xA5

OP_END = 0
OP_WRAP = 1
OP_UNWRAP = 2
OP_WRAP_INPLACE = 3
OP_UNWRAP_INPLACE = 4
OP_WRAP_TRACE = 5
OP_UNWRAP_TRACE = 6

KW_IV = bytes([0xA6] * 8)


# =====================================================================
#  THE HARNESS
# =====================================================================
#  SCRIPT RECORD:
#      +0 op  +4 keklen  +8 datalen  +12 arg  +16 kek[32]  +48 data..
#  data is padded to a multiple of 8; op 0 ends the script.
#
#  RESULT RECORD, 564 bytes:
#      +0 the value the library returned, 32-bit
#      +4 a 560-byte output field, pre-filled with $A5
#
#  THE TWO TRACE PROCEDURES ARE THE HARNESS'S OWN COPY OF THE LOOP, and
#  they are written FLAT - one loop over t = 1..6n - where the library
#  writes the RFC's nested pair.  That is deliberate: i = ((t-1) mod n)
#  + 1 and j = (t-1) div n reproduce the same sequence, so the flat form
#  is an independent statement of the same indexing.  If the library's
#  nested loops and this flat one ever disagree about which register a
#  step touches, the traces go red while the final answers may not.
HARNESS = r'''
; ======================================================================
;  kwharness.pi4 - GENERATED BY tools/a64/a64_keywrap_check.py.
;  NOT A SOURCE FILE. DO NOT EDIT.
;
;  Every KEK and every block of key data it runs is a PUBLISHED test
;  value handed to it in memory by the gate. There is no credential in
;  this file.
; ======================================================================
XIncludeFile "RaspberryPi4/Lib/uart.pi4"
XIncludeFile "RaspberryPi4/Lib/aes.pi4"
XIncludeFile "__LIB__"

#H_SCRIPT = $06000000
#H_RESULT = $0A000000

; ----------------------------------------------------------------------
;  WrapTrace(kek, keklen, plain, plainlen, out, steps)
;
;  Runs the RFC 3394 wrap for exactly `steps` of its 6n steps and
;  leaves A || R[1..n] at out.  steps = 0 is the initial state, which
;  is the RFC's "In" row for step 1; steps = t is its "XorT" row for
;  step t.
; ----------------------------------------------------------------------
Procedure.i WrapTrace(kek.i, keklen.i, plain.i, plainlen.i, out.i, steps.i)
  Define n.i
  Define t.i
  Define i.i
  Define k.i

  n = kw_Blocks(plainlen)
  If n = 0
    ProcedureReturn 0
  EndIf
  If AesSetKey(kek, keklen) = 0
    ProcedureReturn 0
  EndIf

  k = plainlen - 1
  While k >= 0
    PokeB(out + 8 + k, PeekA(plain + k) & 255)
    k = k - 1
  Wend
  k = 0
  While k < 8
    secKwA[k] = $A6
    k = k + 1
  Wend

  t = 1
  While t <= steps
    i = ((t - 1) % n) + 1
    kw_CopyIn(out + i * 8)
    AesEncryptBlock(@secKwB[0], @secKwB[0])
    kw_CopyOut(out + i * 8)
    kw_XorT(t)
    t = t + 1
  Wend

  k = 0
  While k < 8
    PokeB(out + k, secKwA[k] & 255)
    k = k + 1
  Wend
  ProcedureReturn plainlen + 8
EndProcedure

; ----------------------------------------------------------------------
;  UnwrapTrace(kek, keklen, wrapped, wraplen, out, steps)
;
;  The same, backwards.  steps = 0 is the RFC's "In" row for step 6n;
;  steps = k is its "Dec" row for step 6n - k + 1.
; ----------------------------------------------------------------------
Procedure.i UnwrapTrace(kek.i, keklen.i, wrapped.i, wraplen.i, out.i, steps.i)
  Define n.i
  Define s.i
  Define t.i
  Define i.i
  Define k.i

  n = kw_Blocks(wraplen - 8)
  If n = 0
    ProcedureReturn 0
  EndIf
  If AesSetKey(kek, keklen) = 0
    ProcedureReturn 0
  EndIf

  k = 0
  While k < wraplen
    PokeB(out + k, PeekA(wrapped + k) & 255)
    k = k + 1
  Wend
  k = 0
  While k < 8
    secKwA[k] = PeekA(wrapped + k) & 255
    k = k + 1
  Wend

  s = 6 * n
  k = 0
  While k < steps
    t = s - k
    i = ((t - 1) % n) + 1
    kw_XorT(t)
    kw_CopyIn(out + i * 8)
    AesDecryptBlock(@secKwB[0], @secKwB[0])
    kw_CopyOut(out + i * 8)
    k = k + 1
  Wend

  k = 0
  While k < 8
    PokeB(out + k, secKwA[k] & 255)
    k = k + 1
  Wend
  ProcedureReturn wraplen
EndProcedure

Procedure.i Main()
  Define p.i
  Define q.i
  Define op.i
  Define keklen.i
  Define dlen.i
  Define arg.i
  Define i.i
  Define r.i

  p = #H_SCRIPT
  q = #H_RESULT

  Repeat
    op     = PeekN(p)
    keklen = PeekL(p + 4)
    dlen   = PeekL(p + 8)
    arg    = PeekL(p + 12)
    If op = 0
      Break
    EndIf

    i = 0
    While i < 560
      PokeB(q + 4 + i, $A5)
      i = i + 1
    Wend

    r = 0
    If op = 1
      r = KwWrap(p + 16, keklen, p + 48, dlen, q + 4)
    ElseIf op = 2
      r = KwUnwrap(p + 16, keklen, p + 48, dlen, q + 4)
    ElseIf op = 3
      ; IN PLACE, AND dst MUST EQUAL plain.
      ;
      ; THE FIRST VERSION OF THIS PUT THE PLAINTEXT AT q+4+8 AND PASSED
      ; dst = q+4, WHICH IS NOT AN IN-PLACE TEST AT ALL. KwWrap writes
      ; R[i] to dst + 8*i, so with plain = dst + 8 the copy's source and
      ; destination are the SAME ADDRESS and its direction cannot
      ; matter. The mutation "the wrap copies its plaintext forwards"
      ; went GREEN against it, which is how the hole was found.
      ;
      ; The case keywrap.pi4 documents is dst = plain: the caller holds
      ; a plainlen+8 buffer with the plaintext at the FRONT and asks for
      ; the wrap over it, so every byte shifts UP by eight and only a
      ; BACKWARD copy is correct.
      i = 0
      While i < dlen
        PokeB(q + 4 + i, PeekA(p + 48 + i) & 255)
        i = i + 1
      Wend
      r = KwWrap(p + 16, keklen, q + 4, dlen, q + 4)
    ElseIf op = 4
      ; IN PLACE, the other direction: the wrapped blob is copied into
      ; the output buffer at the front and unwrapped over itself.
      i = 0
      While i < dlen
        PokeB(q + 4 + i, PeekA(p + 48 + i) & 255)
        i = i + 1
      Wend
      r = KwUnwrap(p + 16, keklen, q + 4, dlen, q + 4)
    ElseIf op = 5
      r = WrapTrace(p + 16, keklen, p + 48, dlen, q + 4, arg)
    ElseIf op = 6
      r = UnwrapTrace(p + 16, keklen, p + 48, dlen, q + 4, arg)
    EndIf
    PokeN(q, r)

    p = p + 48 + (((dlen + 7) / 8) * 8)
    q = q + 564
  ForEver

  UartWriteStr("kwharness done")
  ProcedureReturn 0
EndProcedure
'''


class Script:
    def __init__(self) -> None:
        self.buf = bytearray()
        self.labels: list[str] = []
        self.expect: list[tuple[int, bytes]] = []

    def add(self, op: int, label: str, ret: int, out: bytes,
            kek: bytes, data: bytes, arg: int = 0,
            keklen: int | None = None, datalen: int | None = None,
            zero_tail: int = 0) -> None:
        """out is what must appear at the front of the result field.
        zero_tail asks for that many bytes of zero after it (the
        must-not-return-key-data rule); everything after that must
        still be sentinel."""
        if keklen is None:
            keklen = len(kek)
        if datalen is None:
            datalen = len(data)
        self.labels.append(label)
        field = out + b"\x00" * zero_tail
        field += bytes([SENTINEL]) * (RES_DATA - len(field))
        self.expect.append((ret, field))
        self.buf += struct.pack("<Iiii", op, keklen, datalen, arg)
        self.buf += kek + b"\x00" * (32 - len(kek))
        # THE RECORD'S DATA IS SIZED BY datalen, NOT BY len(data).  The
        # harness walks the script by adding 48 + round-up-8(datalen),
        # so a refusal case that declares a length of 12 while carrying
        # 8 bytes would put every later record one word out and the
        # failure would look like a library bug.
        want = (max(datalen, 0) + 7) // 8 * 8
        self.buf += (data + b"\x00" * want)[:want]

    def done(self) -> bytes:
        return bytes(self.buf) + struct.pack("<Iiii", OP_END, 0, 0, 0) \
            + b"\x00" * 32

    def __len__(self) -> int:
        return len(self.labels)


# =====================================================================
#  RFC 3394 SECTION 4, PARSED
# =====================================================================
SECTION_RE = re.compile(
    r"^4\.(\d) Wrap (\d+) bits of Key Data with a (\d+)-bit KEK\s*$",
    re.MULTILINE)


def _hexblob(text: str) -> bytes:
    return bytes.fromhex(re.sub(r"[^0-9A-Fa-f]", "", text))


#  THE DOCUMENT HAS A TYPOGRAPHICAL ERROR IN IT, AND THE PARSE REPAIRS
#  IT FROM THE DOCUMENT'S OWN REDUNDANCY RATHER THAN FROM AN OPINION.
#
#  rfc3394.txt:1468, section 4.5 (192-bit key data, 256-bit KEK), step
#  17's XorT row reads
#
#      XorT 39128CE5E4325F3B1 F6E6F4FBE30E71E4 769C8B80A32CB895
#
#  - SEVENTEEN hex digits in the A register.  It is the only malformed
#  token in the whole of section 4; everything else is exactly sixteen.
#
#  The document states that same value twice more and both agree:
#  step 18's In row (:1472) and the unwrap's step-17 Dec row (:1491)
#  both give 39128CE5E435F3B1.  The arithmetic agrees as well - step
#  17's Enc row ends A0 and t = 17 = $11, and $A0 XOR $11 = $B1.
#
#  So the row is REPAIRED, not skipped and not typed in: the parse pairs
#  every XorT row with the following step's In row, and every Dec row
#  with the following step's In row, requires the two to agree wherever
#  both are well formed, and takes the well-formed one where only one
#  is.  If the two ever disagree the parse stops.  That check runs over
#  every step of every vector, so it is worth having for its own sake -
#  the typo is what made it necessary and what proves it works.
_HEXTOK = re.compile(r"[0-9A-F]{15,18}")


def _rows(seg: str, tags: tuple, n: int, what: str) -> list[list]:
    """Collect every A || R[1..n] row of the named kinds, in order.

    A row starts on a line whose first word is one of `tags` and
    continues onto following lines that hold nothing but hex groups,
    until n + 1 groups have been gathered - the 256-bit vectors need
    that continuation, since four registers do not fit on one line.
    A group that is not exactly sixteen digits becomes None and is
    resolved later."""
    out = []
    lines = seg.splitlines()
    k = 0
    while k < len(lines):
        parts = lines[k].split()
        if not parts or parts[0] not in tags:
            k += 1
            continue
        vals = [t for t in parts[1:] if _HEXTOK.fullmatch(t)]
        if len(vals) != len(parts) - 1:
            raise SystemExit("rfc3394.txt %s: unexpected token on %r"
                             % (what, lines[k]))
        k += 1
        while len(vals) < n + 1 and k < len(lines):
            more = lines[k].split()
            if not more or not all(_HEXTOK.fullmatch(t) for t in more):
                break
            vals += more
            k += 1
        if len(vals) != n + 1:
            raise SystemExit(
                "rfc3394.txt %s: a %s row has %d registers, expected %d"
                % (what, parts[0], len(vals), n + 1))
        out.append([bytes.fromhex(v) if len(v) == 16 else None for v in vals])
    return out


def _reconcile(after: list, before: list, what: str) -> int:
    """`after[k]` and `before[k+1]` are the same machine state printed
    twice.  Merge them, and count the repairs."""
    repaired = 0
    for k in range(len(after) - 1):
        for c in range(len(after[k])):
            a, b = after[k][c], before[k + 1][c]
            if a is None and b is None:
                continue
            if a is None:
                after[k][c] = b
                repaired += 1
            elif b is None:
                before[k + 1][c] = a
                repaired += 1
            elif a != b:
                raise SystemExit(
                    "rfc3394.txt %s: step %d register %d is printed twice "
                    "and the two disagree:\n  %s\n  %s"
                    % (what, k + 1, c, a.hex(), b.hex()))
    return repaired


def _joined(row: list, what: str) -> bytes:
    if any(v is None for v in row):
        raise SystemExit(
            "rfc3394.txt %s: a register is malformed and the document does "
            "not print it anywhere else, so it cannot be repaired. Read the "
            "document and fix the parse; do not guess the value." % what)
    return b"".join(row)


def parse_rfc3394() -> list[dict]:
    if not RFC3394.exists():
        raise SystemExit(
            f"the oracle is missing: {RFC3394}\n"
            "Fetch https://www.rfc-editor.org/rfc/rfc3394.txt into "
            "RaspberryPi4/Reference/.")
    text = RFC3394.read_text(errors="replace")
    # Drop page furniture so a table split across a page break still
    # reads as one run of rows.
    text = "\n".join(ln for ln in text.splitlines()
                     if "Schaad & Housley" not in ln
                     and not ln.startswith("RFC 3394 "))

    # The default IV is read from the document, not typed here.
    m = re.search(r"A\[0\]\s*=\s*IV\s*=\s*([0-9A-F]{16})", text)
    if not m:
        raise SystemExit("rfc3394.txt: cannot find the default IV in 2.2.3.1")
    if bytes.fromhex(m.group(1)) != KW_IV:
        raise SystemExit("rfc3394.txt states a default IV of %s, not %s"
                         % (m.group(1), KW_IV.hex().upper()))

    marks = list(SECTION_RE.finditer(text))
    if len(marks) != 6:
        raise SystemExit(
            "rfc3394.txt: expected six section-4 vectors, found %d. The "
            "document has changed shape - fix the parse, do not lower the "
            "number." % len(marks))

    out = []
    for idx, m in enumerate(marks):
        end = marks[idx + 1].start() if idx + 1 < len(marks) else \
            text.find("5. Security Considerations", m.end())
        chunk = text[m.start():end]
        name = "RFC 3394 4.%s  %s-bit key data, %s-bit KEK" % m.groups()
        kd_bits, kek_bits = int(m.group(2)), int(m.group(3))
        n = kd_bits // 64

        iw = chunk.find("Wrap:")
        iu = chunk.find("Unwrap:")
        if not (0 < iw < iu):
            raise SystemExit("%s: cannot find the Wrap/Unwrap boundary" % name)

        # ---- inputs --------------------------------------------------
        head = chunk[:iw]
        ki = head.find("KEK:")
        di = head.find("Key Data:")
        if not (0 <= ki < di):
            raise SystemExit("%s: cannot find KEK: and Key Data:" % name)
        kek = _hexblob(head[ki + 4:di])
        kd = _hexblob(head[di + 9:])
        if len(kek) * 8 != kek_bits:
            raise SystemExit("%s: parsed a %d-bit KEK" % (name, len(kek) * 8))
        if len(kd) * 8 != kd_bits:
            raise SystemExit("%s: parsed %d bits of key data"
                             % (name, len(kd) * 8))

        # ---- the step tables -----------------------------------------
        wrap_in = _rows(chunk[iw:iu], ("In",), n, name + " wrap")
        wrap_xt = _rows(chunk[iw:iu], ("XorT",), n, name + " wrap")
        unw_in = _rows(chunk[iu:], ("In",), n, name + " unwrap")
        unw_dec = _rows(chunk[iu:], ("Dec",), n, name + " unwrap")
        for what, rows in (("wrap In", wrap_in), ("wrap XorT", wrap_xt),
                           ("unwrap In", unw_in), ("unwrap Dec", unw_dec)):
            if len(rows) != 6 * n:
                raise SystemExit(
                    "%s: %d %s rows, expected 6n = %d"
                    % (name, len(rows), what, 6 * n))

        # ---- reconcile the rows the document prints twice ------------
        repairs = _reconcile(wrap_xt, wrap_in, name + " wrap")
        repairs += _reconcile(unw_dec, unw_in, name + " unwrap")
        # THE UNWRAP TABLE PRINTS THE SAME STATES A THIRD TIME, and the
        # index relation is worth writing down because it is easy to get
        # off by one: the unwrap's Dec row for step t is the state after
        # step t has been UNDONE, which is the wrap's state after step
        # t - 1.  Both tables are in document order, so with j = t - 1
        # counting the wrap's rows from zero and k = 6n - t counting the
        # unwrap's,
        #     wrap_xt[j]  ==  unw_dec[6n - j - 2]     for j = 0..6n-2
        # and the wrap's last XorT row has no Dec counterpart (it is the
        # unwrap's first In row, already checked below).
        for j in range(6 * n - 1):
            a = wrap_xt[j]
            b = unw_dec[6 * n - j - 2]
            for c in range(n + 1):
                if a[c] is None and b[c] is not None:
                    a[c] = b[c]
                    repairs += 1
                elif b[c] is None and a[c] is not None:
                    b[c] = a[c]
                    repairs += 1
                elif a[c] is not None and a[c] != b[c]:
                    raise SystemExit(
                        "%s: the wrap's XorT row for step %d and the "
                        "unwrap's Dec row for step %d disagree in "
                        "register %d:\n  %s\n  %s"
                        % (name, j + 1, j + 2, c, a[c].hex(), b[c].hex()))
        if repairs:
            print("  NOTE: %s - %d malformed register(s) in the document "
                  "repaired from rows it prints elsewhere. See _rows()."
                  % (name, repairs))

        # ---- the four self-checks ------------------------------------
        # 1. the wrap starts at IV || P
        if _joined(wrap_in[0], name) != KW_IV + kd:
            raise SystemExit("%s: the wrap's first In row is not IV || key "
                             "data; the parse is wrong" % name)
        ct = _joined(wrap_xt[-1], name)
        # 2. and ends at the ciphertext the Output block states
        m2 = re.search(r"Ciphertext:?\s*((?:[0-9A-F]{16}\s+)*[0-9A-F]{16})",
                       chunk[iw:iu])
        if not m2:
            raise SystemExit("%s: no Ciphertext in the wrap's Output" % name)
        if _hexblob(m2.group(1)) != ct:
            raise SystemExit(
                "%s: the last XorT row and the stated ciphertext disagree:\n"
                "  XorT %s\n  Output %s\nThe parse is wrong."
                % (name, ct.hex(), _hexblob(m2.group(1)).hex()))
        # 3. the unwrap starts at the ciphertext
        if _joined(unw_in[0], name) != ct:
            raise SystemExit("%s: the unwrap's first In row is not the "
                             "ciphertext; the parse is wrong" % name)
        # 4. and ends at IV || P
        if _joined(unw_dec[-1], name) != KW_IV + kd:
            raise SystemExit("%s: the unwrap's last Dec row is not IV || key "
                             "data; the parse is wrong" % name)

        out.append({"name": name, "n": n, "kek": kek, "kd": kd, "ct": ct,
                    "wrap_xt": wrap_xt, "unw_dec": unw_dec,
                    "wrap_in0": _joined(wrap_in[0], name),
                    "unw_in0": _joined(unw_in[0], name)})
    return out


DIAG = (ROOT / "RaspberryPi4" / "Examples" / "Diagnostics"
        / "pi4AesSelfTest.pi4")


def check_diagnostic_vectors(vectors) -> list:
    """The board diagnostic's typed vectors must match the RFC.

    RaspberryPi4/Examples/Diagnostics/pi4AesSelfTest.pi4 runs on bare
    metal, where there is no disk to parse from, so its six RFC 3394
    vectors are TRANSCRIBED - the one thing these gates otherwise refuse
    to do.  This closes that hole from the desktop side: every KwKat
    call in that file is looked up in the parsed document by its KEK and
    key data, and its ciphertext must match.

    A mistyped digit in the board program fails on silicon, looks like a
    silicon problem, and is not one."""
    if not DIAG.exists():
        return ["  the board diagnostic %s is missing" % DIAG.name]
    src = DIAG.read_text(errors="replace")
    tri = re.findall(r'KwKat\(\s*"([0-9a-fA-F]+)",\s*"([0-9a-fA-F]+)",'
                     r'\s*"([0-9a-fA-F]+)"\)', src, re.S)
    bad = []
    if len(tri) != len(vectors):
        bad.append("  %s has %d KwKat calls; RFC 3394 section 4 has %d "
                   "vectors and the diagnostic is meant to run all of them"
                   % (DIAG.name, len(tri), len(vectors)))
    for kek, kd, ct in tri:
        hit = [v for v in vectors if v["kek"].hex() == kek.lower()
               and v["kd"].hex() == kd.lower()]
        if not hit:
            bad.append("  %s: a KwKat's KEK and key data are in no RFC 3394 "
                       "section 4 vector:\n      KEK %s\n      KD  %s"
                       % (DIAG.name, kek.lower(), kd.lower()))
            continue
        if hit[0]["ct"].hex() != ct.lower():
            bad.append("  %s: %s ciphertext\n      typed    %s\n"
                       "      document %s"
                       % (DIAG.name, hit[0]["name"], ct.lower(),
                          hit[0]["ct"].hex()))
    return bad


def confirm_oracle(vectors) -> None:
    """Require OpenSSL to reproduce every published vector, wrap and
    unwrap, before this gate will use it for anything else."""
    try:
        from cryptography.hazmat.primitives.keywrap import (
            aes_key_wrap, aes_key_unwrap)
    except ImportError:
        raise SystemExit(
            "python's `cryptography` package is not installed, so the "
            "second oracle is unavailable.  Run with --quick, which uses "
            "only the published RFC 3394 vectors, or install it.")
    for v in vectors:
        got = aes_key_wrap(v["kek"], v["kd"])
        if got != v["ct"]:
            raise SystemExit(
                "OpenSSL does not reproduce %s: %s vs %s\n"
                "This gate will not use an oracle it cannot validate."
                % (v["name"], got.hex(), v["ct"].hex()))
        back = aes_key_unwrap(v["kek"], v["ct"])
        if back != v["kd"]:
            raise SystemExit("OpenSSL does not unwrap %s back to its key "
                             "data" % v["name"])


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
    if b"kwharness done" not in uart:
        raise SystemExit("the harness returned without finishing:\n"
                         + uart.decode("latin-1"))

    out = []
    for i in range(count):
        a = H_RESULT + i * RES_STRIDE
        ret = sum(mem.get(a + j, 0) << (8 * j) for j in range(4))
        if ret >= 0x80000000:
            ret -= 0x100000000
        out.append((ret, bytes(mem.get(a + 4 + j, 0)
                               for j in range(RES_DATA))))
    return out, steps


def check(img: pathlib.Path, s: Script, quiet: bool = False,
          step_limit: int = STEP_LIMIT, note: str = "") -> tuple:
    if len(s) == 0:
        return [], 0
    got, steps = run(img, s.done(), len(s), step_limit)
    bad = []
    for i, label in enumerate(s.labels):
        want_ret, want_field = s.expect[i]
        ret, field = got[i]
        if ret != want_ret:
            bad.append("  %s\n      returned %d, expected %d"
                       % (label, ret, want_ret))
        elif field != want_field:
            k = 0
            while k < RES_DATA and field[k] == want_field[k]:
                k += 1
            bad.append("  %s\n      first difference at byte %d\n"
                       "      expected %s\n      got      %s"
                       % (label, k, want_field[max(0, k - 8):k + 24].hex(),
                          field[max(0, k - 8):k + 24].hex()))
    if not quiet:
        print("  %-52s %4d vectors, %-9s %11d steps"
              % (note, len(s), "ALL PASS" if not bad else
                 "%d FAILED" % len(bad), steps))
    return bad, steps


# =====================================================================
#  THE VECTOR SETS
# =====================================================================
def script_published(vectors, traces: bool) -> Script:
    s = Script()
    for v in vectors:
        n, kek, kd, ct = v["n"], v["kek"], v["kd"], v["ct"]
        s.add(OP_WRAP, v["name"] + "  wrap", len(ct), ct, kek, kd)
        s.add(OP_UNWRAP, v["name"] + "  unwrap", len(kd), kd, kek, ct)
        s.add(OP_WRAP_INPLACE, v["name"] + "  wrap in place",
              len(ct), ct, kek, kd)
        # AN IN-PLACE UNWRAP DOES NOT LEAVE THE TAIL AT ITS SENTINEL.
        # The harness copies the whole wrapped blob into the output
        # buffer and unwraps it over itself, so the last eight bytes
        # still hold the copy's tail - the ciphertext's own last
        # register.  That is stated here rather than excused, because
        # "the bytes past the answer are undefined" is exactly the
        # phrase under which a buffer overrun hides.
        s.add(OP_UNWRAP_INPLACE, v["name"] + "  unwrap in place",
              len(kd), kd + ct[-8:], kek, ct)
        if not traces:
            continue
        s.add(OP_WRAP_TRACE, v["name"] + "  wrap step 0 (the In row)",
              len(ct), v["wrap_in0"], kek, kd, arg=0)
        for t in range(1, 6 * n + 1):
            s.add(OP_WRAP_TRACE, v["name"] + "  wrap step %d XorT" % t,
                  len(ct), b"".join(v["wrap_xt"][t - 1]), kek, kd, arg=t)
        s.add(OP_UNWRAP_TRACE, v["name"] + "  unwrap step 0 (the In row)",
              len(ct), v["unw_in0"], kek, ct, arg=0)
        for k in range(1, 6 * n + 1):
            s.add(OP_UNWRAP_TRACE,
                  "%s  unwrap step %d Dec" % (v["name"], 6 * n - k + 1),
                  len(ct), b"".join(v["unw_dec"][k - 1]), kek, ct, arg=k)
    return s


REFUSALS = [
    # (label, op, key data / wrapped length to pass, why)
    ("wrap of 8 bytes (n = 1)", OP_WRAP, 8),
    ("wrap of 0 bytes", OP_WRAP, 0),
    ("wrap of 12 bytes (not a multiple of 8)", OP_WRAP, 12),
    ("wrap of 17 bytes", OP_WRAP, 17),
    ("unwrap of 16 bytes (n = 1)", OP_UNWRAP, 16),
    ("unwrap of 8 bytes", OP_UNWRAP, 8),
    ("unwrap of 0 bytes", OP_UNWRAP, 0),
    ("unwrap of 20 bytes (not a multiple of 8)", OP_UNWRAP, 20),
]


def script_refusals(vectors) -> Script:
    v = vectors[0]
    s = Script()
    for label, op, ln in REFUSALS:
        s.add(op, "REFUSE  " + label, 0, b"", v["kek"], b"\x5A" * max(ln, 8),
              datalen=ln)
    # A bad KEK length must be refused for both directions.
    for bad in (0, 15, 20, 33):
        s.add(OP_WRAP, "REFUSE  wrap with a %d-byte KEK" % bad, 0, b"",
              b"\x33" * 32, v["kd"], keklen=bad)
        s.add(OP_UNWRAP, "REFUSE  unwrap with a %d-byte KEK" % bad, 0, b"",
              b"\x33" * 32, v["ct"], keklen=bad)
    return s


def script_corruption(vectors, small: bool = False) -> Script:
    """RFC 3394 section 5: a failed integrity check MUST return an error
    and MUST NOT return any key data.  A corrupted blob must give 0 AND
    a buffer of zeroes - the return value alone is not the test.

    THE BITS ARE CHOSEN, NOT SWEPT.  Flipping all 8n+64 bits would be
    several thousand unwraps under this model for no extra coverage;
    what matters is that a flip anywhere in A is caught, that a flip in
    EVERY R register is caught (a register the loop never visits would
    otherwise go unnoticed), and that a length change is caught."""
    s = Script()
    for v in (vectors[:2] if small else vectors):
        ct = v["ct"]
        n = v["n"]
        bits = [0, 7, 63]                       # first, last-in-byte, last of A
        bits += [64 + 8 * 8 * i + 3 for i in range(n)]   # one per R register
        bits += [len(ct) * 8 - 1]               # the very last bit
        for bit in bits:
            bad = bytearray(ct)
            bad[bit // 8] ^= 1 << (7 - (bit % 8))
            s.add(OP_UNWRAP,
                  "%s  bit %d flipped must be refused" % (v["name"], bit),
                  0, b"", v["kek"], bytes(bad), zero_tail=n * 8)
        # And truncation - a blob one register short still parses as a
        # legal length and must fail the integrity check.
        if n > 2:
            s.add(OP_UNWRAP, "%s  truncated by one register" % v["name"],
                  0, b"", v["kek"], ct[:-8], zero_tail=(n - 1) * 8)
    return s


# The extra shapes, from the oracle validated above.  n = 43 is the
# smallest that drives t past 255; see the header.
EXTRA = [
    ("n = 2 under a 128-bit KEK", 16, 16),
    ("n = 5 under a 128-bit KEK", 16, 40),
    ("n = 7 under a 192-bit KEK", 24, 56),
    ("n = 8 under a 256-bit KEK", 32, 64),
    ("n = 14, a plausible EAPOL Key Data", 16, 112),
]
BIG_N = ("n = 43, so the step counter passes 255", 16, 344)


def script_extra(cases) -> Script:
    from cryptography.hazmat.primitives.keywrap import aes_key_wrap
    s = Script()
    for label, keklen, kdlen in cases:
        kek = bytes((0x40 + i) & 0xFF for i in range(keklen))
        kd = bytes((i * 7 + 3) & 0xFF for i in range(kdlen))
        ct = aes_key_wrap(kek, kd)
        s.add(OP_WRAP, "OpenSSL  " + label + "  wrap", len(ct), ct, kek, kd)
        s.add(OP_UNWRAP, "OpenSSL  " + label + "  unwrap", len(kd), kd,
              kek, ct)
    return s


def script_extra_wraponly(cases) -> Script:
    from cryptography.hazmat.primitives.keywrap import aes_key_wrap
    s = Script()
    for label, keklen, kdlen in cases:
        kek = bytes((0x40 + i) & 0xFF for i in range(keklen))
        kd = bytes((i * 7 + 3) & 0xFF for i in range(kdlen))
        ct = aes_key_wrap(kek, kd)
        s.add(OP_WRAP, "OpenSSL  " + label + "  wrap", len(ct), ct, kek, kd)
    return s


# =====================================================================
#  MUTATIONS
# =====================================================================
MUTATIONS = [
    # THE TWO t ANCHORS HAVE TO NAME THEIR NEIGHBOURS.  `t = n * j + i`
    # followed by `kw_XorT(t)` appears in BOTH procedures - the wrap
    # XORs after the codebook call, the unwrap XORs before it - so a
    # two-line anchor matches twice, and the runner refuses that rather
    # than mutating both at once and calling it one experiment.
    ("the wrap's step counter is the register index",
     "      kw_CopyOut(dst + i * #KW_SEMI)\n      t = n * j + i\n      kw_XorT(t)",
     "      kw_CopyOut(dst + i * #KW_SEMI)\n      t = i\n      kw_XorT(t)", 1,
     "t counts 1..6n across the whole double loop, not 1..n six times"),

    ("the unwrap's step counter is the register index",
     "      t = n * j + i\n      kw_XorT(t)\n      kw_CopyIn",
     "      t = i\n      kw_XorT(t)\n      kw_CopyIn", 1,
     "the same on the way back"),

    ("only the low byte of t is XORed into A",
     "  k = 0\n  While k < #KW_SEMI\n    secKwA[7 - k] = (secKwA[7 - k] & 255) ! ((t >> (k * 8)) & 255)",
     "  k = 0\n  While k < 1\n    secKwA[7 - k] = (secKwA[7 - k] & 255) ! ((t >> (k * 8)) & 255)", 1,
     "EVERY PUBLISHED VECTOR HAS n <= 4, so t never exceeds 24 and this "
     "defect is invisible to all six of them. It is caught only by the "
     "n = 43 case, which is why that case is in the gate"),

    # THESE TWO ARE CAUGHT BY THE STEP BUDGET, NOT BY A WRONG ANSWER,
    # and that is worth saying out loud.  Turning either loop round
    # leaves the tail decrementing a counter the new condition expects
    # to increase - `i = 1; While i <= n; ... i = i - 1` runs forever -
    # so the budget is what makes them RED, and the printed note reads
    # "over the step budget" rather than a count of wrong vectors.  On
    # the board, with nothing armed to notice, this defect would be a
    # hang with no output at all.
    ("the unwrap runs its registers forwards",
     "    i = n\n    While i >= 1", "    i = 1\n    While i <= n", 1,
     "the unwrap is the mirror image; turning the register loop round "
     "does not terminate"),

    ("the unwrap runs its passes forwards",
     "  j = #KW_PASSES - 1\n  While j >= 0", "  j = 0\n  While j < #KW_PASSES", 1,
     "the same, one level out, and it does not terminate either"),

    ("five passes instead of six",
     "#KW_PASSES  = 6", "#KW_PASSES  = 5", 1,
     "s = 6n, rfc3394.txt:144"),

    ("the default IV is A5, not A6",
     "#KW_IV_BYTE = $A6", "#KW_IV_BYTE = $A5", 1,
     "rfc3394.txt:362.  The wrap produces a different ciphertext "
     "and the unwrap refuses everything"),

    ("the integrity check is not enforced",
     "  If diff <> 0\n    k = 0", "  If diff <> 1\n    k = 0", 1,
     "an unwrap that returns key data on a failed check is a decryption "
     "oracle - RFC 3394 section 5 says MUST NOT"),

    ("a failed unwrap returns the buffer instead of zeroing it",
     "    KwWipe()\n    ProcedureReturn 0\n  EndIf\n\n  ProcedureReturn n * #KW_SEMI",
     "    KwWipe()\n    ProcedureReturn n * #KW_SEMI\n  EndIf\n\n  ProcedureReturn n * #KW_SEMI", 1,
     "the same rule, the other half of it"),

    ("the codebook input is R | A, not A | R",
     "    secKwB[k] = secKwA[k] & 255\n    secKwB[#KW_SEMI + k] = PeekA(r + k) & 255",
     "    secKwB[k] = PeekA(r + k) & 255\n    secKwB[#KW_SEMI + k] = secKwA[k] & 255", 1,
     "A is the MOST significant half, rfc3394.txt:144-145"),

    ("the codebook output halves are swapped",
     "    secKwA[k] = secKwB[k] & 255\n    PokeB(r + k, secKwB[#KW_SEMI + k] & 255)",
     "    secKwA[k] = secKwB[#KW_SEMI + k] & 255\n    PokeB(r + k, secKwB[k] & 255)", 1,
     "A = MSB(64, B) and R = LSB(64, B), not the other way round"),

    ("n = 1 is accepted",
     "  If len < #KW_MIN_N * #KW_SEMI\n    ProcedureReturn 0\n  EndIf",
     "  If len < #KW_SEMI\n    ProcedureReturn 0\n  EndIf", 1,
     "rfc3394.txt:119-121 - the one restriction the algorithm places on "
     "n is that it be at least two"),

    ("a length that is not a multiple of 8 is accepted",
     "  If (len % #KW_SEMI) <> 0\n    ProcedureReturn 0\n  EndIf", "", 1,
     "the key data is parsed into n blocks of 64 bits"),

    ("the wrap copies its plaintext forwards",
     "  k = plainlen - 1\n  While k >= 0\n    PokeB(dst + #KW_SEMI + k, PeekA(plain + k) & 255)\n    k = k - 1\n  Wend",
     "  k = 0\n  While k < plainlen\n    PokeB(dst + #KW_SEMI + k, PeekA(plain + k) & 255)\n    k = k + 1\n  Wend", 1,
     "only the IN-PLACE case can see this: the plaintext shifts up by "
     "eight, so a forward copy overwrites bytes it has not read"),

    ("the unwrap copies its ciphertext backwards",
     "  k = 0\n  While k < n * #KW_SEMI\n    PokeB(dst + k, PeekA(wrapped + #KW_SEMI + k) & 255)\n    k = k + 1\n  Wend",
     "  k = n * #KW_SEMI - 1\n  While k >= 0\n    PokeB(dst + k, PeekA(wrapped + #KW_SEMI + k) & 255)\n    k = k - 1\n  Wend", 1,
     "the mirror of the above; the ciphertext shifts DOWN by eight so "
     "the copy must run forwards"),
]

EXPECT_GREEN: set = set()


def script_mutation_set(vectors) -> Script:
    s = Script()
    base = script_published(vectors, traces=False)
    s.buf += base.buf
    s.labels += base.labels
    s.expect += base.expect
    for part in (script_corruption(vectors, small=True),
                 script_refusals(vectors),
                 script_extra_wraponly([BIG_N])):
        s.buf += part.buf
        s.labels += part.labels
        s.expect += part.expect
    return s


def mutation_budget(clean_steps: int) -> int:
    """THE BUDGET IS A DETECTOR, NOT A TIMEOUT, AND IT IS DELIBERATELY
    TIGHT.  Two mutations below - the unwrap's register loop and its
    pass loop, each turned round - leave the loop tail decrementing a
    counter the new condition expects to increase, so neither
    terminates; the budget is the only thing that ends them.  A
    legitimate mutation cannot need more than about 1.2x the clean run,
    so twice is generous, and ten times was twenty wasted minutes on the
    first sweep that met one."""
    return max(clean_steps * 2, 50_000_000)


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

    vectors = parse_rfc3394()
    s = script_mutation_set(vectors)
    # RESOLVE FIRST.  The parent hands down whatever path it built,
    # which may be relative to ROOT; XIncludeFile wants a ROOT-relative
    # POSIX path and relative_to needs both sides absolute.
    workdir = pathlib.Path(workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    mut = workdir / "keywrap_mut.pi4"
    mut.write_text(mutated, encoding="utf-8")
    include = mut.relative_to(ROOT).as_posix()

    # The clean step count is not recomputed per worker - that would
    # double the sweep's cost for a number that cannot change.  It is
    # measured once by the parent and handed down.
    budget = int(os.environ.get("KW_MUT_BUDGET", "140000000"))

    red = None
    note = ""
    try:
        build(include, workdir / "kwharness_mut.pi4",
              workdir / "kwcheck_mut.img")
    except SystemExit:
        red, note = True, "refused to build"
    if red is None:
        try:
            bad, msteps = check(workdir / "kwcheck_mut.img", s, quiet=True,
                                step_limit=budget)
            red = len(bad) > 0
            note = "%d of %d wrong" % (len(bad), len(s))
        except SystemExit:
            red, note = True, "over the step budget"
        except AlignmentFault:
            # A MUTANT THAT FAULTS IS RED, NOT A CRASH.  With the MMU
            # off an unaligned wide access is a fault with no vector
            # installed - on the board, silence.
            red, note = True, "unaligned access - on the board, silence"
    print("%s%s	%s" % (pool.VERDICT, "RED" if red else "GREEN", note))
    return 0


def mutate(vectors, clean_steps: int) -> int:
    """The control has already passed.  Fan the mutations out across the
    machine and collect the verdicts in index order.

    ONE WORKER PER MUTATION, ONE DIRECTORY PER WORKER.  See
    a64_mutate_pool for why it is subprocesses and why the directories
    matter."""
    budget = mutation_budget(clean_steps)
    os.environ["KW_MUT_BUDGET"] = str(budget)
    procs = pool.worker_count()
    root = WORK / "keywrap"
    t0 = time.time()
    print("MUTATION TEST - %d mutations, %d vectors each, step budget %d "
          "(clean run was %d)"
          % (len(MUTATIONS), len(script_mutation_set(vectors)), budget,
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
    ap.add_argument("--quick", action="store_true",
                    help="the six published vectors and the refusals; no "
                         "per-step traces and no big-n case")
    ap.add_argument("--mutate", action="store_true")
    # The two below are how a64_mutate_pool spawns one worker.  They are
    # not meant to be typed by hand, and the sweep prints the command it
    # used if a worker fails so that one CAN be re-run on its own.
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

    # ONE WORKER OF A PARALLEL SWEEP.  It does its own build in its own
    # directory and prints exactly one verdict line; it must not touch
    # the shared _work/kwcheck.img the parent is using.
    if args.mutate_one is not None:
        if not args.mutate_dir:
            raise SystemExit("--mutate-one needs --mutate-dir")
        return mutate_one(args.mutate_one, pathlib.Path(args.mutate_dir))

    t0 = time.time()
    build("RaspberryPi4/Lib/keywrap.pi4", WORK / "kwharness.pi4",
          WORK / "kwcheck.img")
    img = WORK / "kwcheck.img"

    vectors = parse_rfc3394()

    if args.mutate:
        confirm_oracle(vectors)
        s = script_mutation_set(vectors)
        bad, clean = check(img, s, note="the unmutated library")
        if bad:
            print("the unmutated library is already failing; fix that first")
            print("\n".join(bad[:10]))
            return 1
        return 1 if mutate(vectors, clean) else 0

    print("AES Key Wrap gate - RaspberryPi4/Lib/keywrap.pi4")
    print("  published oracle: RFC 3394 section 4, parsed from disk, all "
          "six vectors")
    if not args.quick:
        confirm_oracle(vectors)
        print("  second oracle:    OpenSSL via `cryptography`, validated "
              "against all six first")
    print()

    failures = []
    total = 0

    dbad = check_diagnostic_vectors(vectors)
    print("  %-52s %4d vectors, %s"
          % ("the board diagnostic's typed vectors", len(vectors),
             "ALL MATCH THE DOCUMENT" if not dbad
             else "%d DISAGREE" % len(dbad)))
    failures += dbad

    for v in vectors:
        s = script_published([v], traces=not args.quick)
        bad, st = check(img, s, note=v["name"])
        failures += bad
        total += st

    s = script_refusals(vectors)
    bad, st = check(img, s, note="refusals")
    failures += bad
    total += st

    s = script_corruption(vectors, small=args.quick)
    bad, st = check(img, s, note="corrupted blobs must return nothing")
    failures += bad
    total += st

    if not args.quick:
        s = script_extra(EXTRA)
        bad, st = check(img, s, note="OpenSSL  extra shapes")
        failures += bad
        total += st

        s = script_extra_wraponly([BIG_N])
        bad, st = check(img, s, note="OpenSSL  " + BIG_N[0])
        failures += bad
        total += st

    print()
    print("  %d model instructions, %.1f s" % (total, time.time() - t0))
    if failures:
        print("\nFAILURES")
        print("\n".join(failures[:30]))
        if len(failures) > 30:
            print("  ... and %d more" % (len(failures) - 30))
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

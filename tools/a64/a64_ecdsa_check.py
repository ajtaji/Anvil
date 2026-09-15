#!/usr/bin/env python3
"""Executable gate for RaspberryPi4/Lib/ecdsa.pi4 - ECDSA P-256 signature
VERIFY on AArch64.

WHY THIS FILE IS WRITTEN THE WAY IT IS

  THE VECTORS ARE THE ONES THE PICO GATES ALREADY USE.  They are not
  transcribed here and they are not generated here: this gate IMPORTS
  the three case tables out of tools/gen_ecdsa_vectors.py, the file that
  emits ecdsaVectors.pico2 / .pico / .unor4 for the three 32-bit
  families.  That generator anchors its pure-python P-256 oracle, before
  it emits a byte, to the published RFC 6979 A.2.5 signatures, the P-256
  generator-multiply known answer and two real certificate signatures
  made by a different implementation; the anchor is re-run here every
  time this gate starts, so a wrong expectation would have to be wrong
  in RFC 6979 as well.  One table, four families.

  ALL 46 RECORDS RUN, AND THE 37 NEGATIVES ARE THE POINT.  9 signatures
  must verify and 37 must be refused.  A verify gate with only positives
  goes green against an implementation that returns "good" for
  everything, which is the single most useless thing a signature gate
  can do.  The negatives here are the CAVP SigVer failure taxonomy (r
  changed, s changed, message changed, wrong public key, r or s zero, r
  or s at or beyond the group order, a wrong-length public point, a bad
  prefix, an off-curve point, an odd raw length) plus fifteen malformed
  DER shapes.

  THE REASON IS CHECKED, NOT JUST THE VERDICT.  Every record also
  asserts EcdsaLastErr, exactly as ecdsaSelfTest.pico2 does: a malformed
  encoding must be refused BY THE ENCODING WALK (error 3) and not
  stumbled over by the arithmetic afterwards (error 1).  Those two
  outcomes are identical in the return value and are not the same thing.

  THE OPERATIONS ARE THE ONES ecdsaSelfTest.pico2 PERFORMS, call for
  call: CheckRaw (EcdsaVrfyRaw), CheckAsn1 (through the certificate-path
  seam EcdsaVrfy with curve 23, plus one EcdsaVrfyAsn1 agreement check),
  CheckDer (EcdsaVrfyAsn1), CheckCurves (P-384, P-521 and two unknown
  ids must answer -1, never 0) and CheckConvert (the caller's buffer is
  not modified, EcdsaAsn1ToRaw yields 64 bytes, and the converted raw
  form verifies).  A difference in an answer is then a difference in the
  library and not in how it was driven.

  ONE THING IS CHECKED HERE THAT NO 32-BIT COPY CHECKS.  Job 0 of every
  shard is a COLD verify: it reads EcdsaReady first (which must be 0,
  because nothing has initialised yet) and then verifies a published
  signature without anyone having called EcdsaInit.  That is the
  self-initialisation path the header promises, and mutation M17 is the
  line that would silently answer from an all-zero curve order instead.

  EVERY VERDICT IS STORED AND CHECKED AT FULL 64-BIT WIDTH (PokeI on the
  way in, "<Q" on the way out).  The A64 GCM gate stored a verdict with
  PokeN and the one mutation it existed to catch survived, because the
  wrong value's set bits were all above bit 31 and the low half read
  back clean.  It also matters for the plain answers here: EcdsaVrfy
  returns -1 for a curve it cannot compute, which is
  $FFFFFFFFFFFFFFFF at this width and $FFFFFFFF at the other, and a
  gate that truncated could not tell -1 from a 32-bit mask.

  IT RUNS ON ALL CORES.  One P-256 verify is two scalar multiplies and a
  modular inversion - tens of millions of model instructions - and the
  full set runs dozens of them.  The image is built ONCE and the job
  list is sharded across a process pool.  --jobs overrides; use it while
  other work is on the machine.

WHY THERE IS NO --timing

  BECAUSE NOBODY CLAIMS THE PROPERTY.  ecdsa.pico2's header says in as
  many words that this module is not constant time and does not need to
  be: the signature travelled in clear, the public key is published in
  the certificate, and the hash is computed from data both peers hold.
  There is no CT gate for ecdsa on the Pico side either - the 32-bit
  families' constant-time A/B tool is wired to bignum, ec256, x25519,
  hmac, hkdf, drbg and tls13, and to ecdsa nowhere.  The two scalar multiplies underneath ARE constant time
  and are gated as such in ec256's own gate; the order inversion rides
  bignum's ladder and is gated in bignum's.  Inventing a --timing here
  would be measuring a property this module does not offer, on code
  whose branches read public lengths on purpose.

WHAT THIS GATE DOES NOT SAY

  * That any of this runs on silicon.  The oracle is a model of the
    instruction set: no caches, no memory system, no clock.
  * That a hash longer than the curve order is handled correctly.  Every
    record in the shared table is SHA-256 over P-256, where the hash
    length equals the order length exactly, so EcdsaBits2Int's
    right-truncation branch never fires.  That is recorded as an
    EXPECTED SURVIVOR (M16) rather than papered over with a vector this
    gate invented.

Run: python tools/a64/a64_ecdsa_check.py
     python tools/a64/a64_ecdsa_check.py --jobs 6
     python tools/a64/a64_ecdsa_check.py --mutate
"""

from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import os
import pathlib
import struct
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent

# THE TREE UNDER TEST IS THE ONE THIS SCRIPT LIVES IN.  A root pinned
# into the file made another gate build a DIFFERENT working copy, with
# that copy's compiler, and print the answer as this tree's.  The tree
# actually read is printed below.
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))

PMFC = os.environ.get("PMF_COMPILER") or "PureMetalForge.exe"  # rebound from --compiler
# Every compile resolves includes from THIS tree only.
BUILD_ENV = dict(os.environ, PMF_ROOT=str(ROOT))
# --jobs, remembered for the pools that are not handed it directly.
JOBS_CAP = None
ECDSA = ROOT / "RaspberryPi4" / "Lib" / "ecdsa.pi4"
WORK = ROOT / "_work"

LOAD = 0x00400000
LOADER_SP = 0x00100000
LOADER_LR = 0xDEADBEE0
STACK = 0x03000000

UART_LO = 0xFE201000
UART_HI = 0xFE201048
UART_DR = 0xFE201000

H_SCRIPT = 0x06000000
H_RESULT = 0x0A000000
H_OUT = 0x0B000000

# A RUNAWAY MUST STOP IN HOURS, NOT IN DAYS.  The model runs at
# roughly 200k instructions a second in one process, so this cap is
# about four hours - three times the worst shard of a full run
# (around one billion: six verifies at roughly 155 million each) and
# ten times a mutant subset.  A mutation that loops forever is a
# real outcome of a sweep and it has to be reported, not waited on.
STEP_LIMIT = 3_000_000_000

RESULT_STRIDE = 32          # verdict, lasterr, outlen, spare - all i64
SENTINEL = 0xA5
M64 = 0xFFFFFFFFFFFFFFFF

(OP_END, OP_COLD, OP_INIT, OP_RAW, OP_ASN1, OP_SEAM, OP_CONVERT,
 OP_NOCLOBBER, OP_CONVVRFY) = range(9)

# EcdsaLastErr values, out of the library.
ERR_OK, ERR_BADSIG, ERR_CURVE, ERR_MALFORMED = 0, 1, 2, 3


# =====================================================================
#  THE HARNESS
# =====================================================================
#  It reads a script of jobs out of memory at #H_SCRIPT, runs each one,
#  and writes a fixed 32-byte record per job at #H_RESULT plus any
#  produced bytes at #H_OUT.  Every vector is DATA, so adding one never
#  changes this file.
#
#  SCRIPT RECORD - a 28-byte header, then q || hash || sig, padded to 4:
#      +0 op  +4 a0 (curve id)  +8 qlen  +12 hashlen  +16 siglen
#      +20 outlen  +24 (spare)
#  op 0 ends the script.
#
#  RESULT RECORD - 32 bytes, FOUR 64-BIT FIELDS:
#      +0  verdict    the entry point's return value, AT FULL WIDTH
#      +8  lasterr    EcdsaLastErr after the call
#      +16 outlen     the byte count written to #H_OUT for this job
#      +24 spare
# =====================================================================
HARNESS = r'''
; ======================================================================
;  ecdsaharness.pi4 - GENERATED BY tools/a64/a64_ecdsa_check.py.
;  NOT A SOURCE FILE. DO NOT EDIT.
; ======================================================================
XIncludeFile "RaspberryPi4/Lib/uart.pi4"
XIncludeFile "RaspberryPi4/Lib/bignum.pi4"
XIncludeFile "RaspberryPi4/Lib/ec256.pi4"
XIncludeFile "__ECDSA__"

#H_SCRIPT = $06000000
#H_RESULT = $0A000000
#H_OUT    = $0B000000

; Byte buffers, `.a` on purpose: the vectors are bytes and the library
; reads them with PeekA.  Sized past the largest record the shared
; generator emits (a 65-byte point, a 32-byte hash, a 72-byte DER
; signature) with room for the malformed shapes that are longer.
Global Dim VecQ.a[96]
Global Dim VecHash.a[80]
Global Dim VecSig.a[320]
Global Dim ConvBuf.a[320]
Global Dim KeepBuf.a[320]

Procedure BhCopy(dst.i, src.i, n.i)
  Define i.i
  i = 0
  While i < n
    PokeB(dst + i, PeekA(src + i) & 255)
    i = i + 1
  Wend
EndProcedure

Procedure.i Main()
  Define p.i
  Define q.i
  Define o.i
  Define op.i
  Define a0.i
  Define ql.i
  Define hl.i
  Define sl.i
  Define outlen.i
  Define bq.i
  Define bh.i
  Define bs.i
  Define s0.i
  Define s1.i
  Define i.i
  Define n.i
  Define same.i

  p = #H_SCRIPT
  q = #H_RESULT
  o = #H_OUT

  Repeat
    op     = PeekN(p)
    a0     = PeekN(p + 4)
    ql     = PeekN(p + 8)
    hl     = PeekN(p + 12)
    sl     = PeekN(p + 16)
    outlen = PeekN(p + 20)
    If op = 0
      Break
    EndIf
    bq = p + 28
    bh = bq + ql
    bs = bh + hl
    BhCopy(@VecQ, bq, ql)
    BhCopy(@VecHash, bh, hl)
    BhCopy(@VecSig, bs, sl)

    s0 = 0
    s1 = 0

    If op = 1
      ; COLD - the self-initialisation path, from a standing start.
      ; EcdsaReady must still be 0 here, so this job has to be FIRST in
      ; every shard; then a published signature is verified without
      ; anyone having called EcdsaInit.  s0 packs both answers so the
      ; one record carries the whole claim.
      s0 = EcdsaReady
      s1 = EcdsaVrfyRaw(@VecHash, hl, @VecQ, ql, @VecSig, sl)

    ElseIf op = 2
      ; INIT - call it explicitly and report what it built: the curve
      ; order's announced length, its Montgomery constant, and the whole
      ; inversion exponent n-2 as bytes.
      EcdsaInit()
      s0 = BnGw(@EcdsaN, 0)
      s1 = EcdsaN0i
      BhCopy(o, @EcdsaExp, outlen)

    ElseIf op = 3
      ; RAW - r||s, the CAVP record shape.
      s0 = EcdsaVrfyRaw(@VecHash, hl, @VecQ, ql, @VecSig, sl)
      s1 = EcdsaLastErr

    ElseIf op = 4
      ; ASN1 - the direct DER entry point.
      s0 = EcdsaVrfyAsn1(@VecHash, hl, @VecQ, ql, @VecSig, sl)
      s1 = EcdsaLastErr

    ElseIf op = 5
      ; SEAM - the shape the X.509 path validator calls.  a0 is the
      ; named curve id, so the same job drives P-256 and the curves this
      ; module must refuse to answer about.
      s0 = EcdsaVrfy(a0, @VecHash, hl, @VecQ, ql, @VecSig, sl)
      s1 = EcdsaLastErr

    ElseIf op = 6
      ; CONVERT - DER -> raw in place, on a copy the caller owns.
      BhCopy(@ConvBuf, @VecSig, sl)
      s0 = EcdsaAsn1ToRaw(@ConvBuf, sl)
      s1 = EcdsaLastErr
      BhCopy(o, @ConvBuf, outlen)

    ElseIf op = 7
      ; NOCLOBBER - the verify entry point must not touch the caller's
      ; signature bytes.  s0 is 1 only if every byte survived.
      BhCopy(@KeepBuf, @VecSig, sl)
      s1 = EcdsaVrfyAsn1(@VecHash, hl, @VecQ, ql, @VecSig, sl)
      same = 1
      i = 0
      While i < sl
        If (PeekA(@KeepBuf + i) & 255) <> (PeekA(@VecSig + i) & 255)
          same = 0
        EndIf
        i = i + 1
      Wend
      s0 = same

    ElseIf op = 8
      ; CONVVRFY - convert, then verify the converted raw form.
      BhCopy(@ConvBuf, @VecSig, sl)
      n = EcdsaAsn1ToRaw(@ConvBuf, sl)
      s0 = n
      s1 = EcdsaVrfyRaw(@VecHash, hl, @VecQ, ql, @ConvBuf, n)
    EndIf

    PokeI(q, s0)
    PokeI(q + 8, s1)
    PokeI(q + 16, outlen)
    PokeI(q + 24, 0)

    p = p + 28 + ql + hl + sl
    p = ((p + 3) / 4) * 4
    q = q + 32
    o = o + (((outlen + 3) / 4) * 4)
  ForEver

  UartWriteStr("ecdsaharness done")
  ProcedureReturn 0
EndProcedure
'''


# =====================================================================
#  THE VECTOR SET, IMPORTED FROM THE GENERATOR THE PICO GATES USE
# =====================================================================
def load_tables():
    """Import the case tables out of tools/gen_ecdsa_vectors.py.

    The generator already guards its emit behind `if __name__ ==
    "__main__":`, so importing it runs the ORACLE ANCHOR and nothing
    else - no files are written into any family's Diagnostics folder by
    this gate.
    """
    gen_path = ROOT / "tools" / "gen_ecdsa_vectors.py"
    if not gen_path.exists():
        raise SystemExit(
            "the vector tables are missing: %s\n"
            "This gate deliberately has no vectors of its own - it reads\n"
            "the same tables that emit ecdsaVectors.pico2 for the Pico\n"
            "gates." % gen_path)
    spec = importlib.util.spec_from_file_location("gen_ecdsa_vectors",
                                                  gen_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for name in ("anchor", "build", "der_split", "N"):
        if not hasattr(mod, name):
            raise SystemExit(
                "gen_ecdsa_vectors.py no longer defines %r; this gate "
                "reads its tables BY NAME and must be updated WITH it, "
                "not around it" % name)
    # Re-run the published anchor here.  It costs a second and it means
    # this gate cannot go green against a generator whose oracle has
    # drifted away from RFC 6979.
    mod.anchor()
    return mod


class Script:
    """The job list, in the order the harness will walk it."""

    def __init__(self):
        self.buf = bytearray()
        self.jobs = []            # (label, op, (v, e), expected_bytes)
        self.records = []
        self.out_off = []
        self._o = 0

    def add(self, op, label, curve=0, q=b"", h=b"", sig=b"",
            out=None, verdict=None, err=None):
        outlen = 0 if out is None else len(out)
        rec = struct.pack("<IIIIIII", op, curve & 0xFFFFFFFF,
                          len(q), len(h), len(sig), outlen, 0)
        rec += q + h + sig
        rec += b"\x00" * ((-len(rec)) % 4)
        self._append(rec, label, op, (verdict, err), out)

    def _append(self, rec, label, op, scalars, out):
        self.jobs.append((label, op, scalars, out))
        self.records.append(rec)
        self.out_off.append(self._o)
        self._o += ((0 if out is None else len(out)) + 3) // 4 * 4
        self.buf += rec

    def done(self):
        return bytes(self.buf) + struct.pack("<IIIIIII", OP_END,
                                             0, 0, 0, 0, 0, 0)

    def __len__(self):
        return len(self.jobs)


def raw_of(g, der):
    """The r||s form EcdsaAsn1ToRaw must produce from a DER signature.

    Both integers are re-emitted at the WIDER of the two widths after
    minimal leading zeros are dropped, left-padded - which is what the
    raw form means.  Derived from the generator's own splitter, so it
    cannot drift from the DER the generator built.
    """
    r, s = g.der_split(der)
    w = max(1, (r.bit_length() + 7) // 8, (s.bit_length() + 7) // 8)
    return r.to_bytes(w, "big") + s.to_bytes(w, "big")


def head_jobs(g, s, raw, asn1):
    """Job 0 and job 1 of EVERY shard.

    THE COLD JOB HAS TO BE FIRST OR IT IS NOT COLD.  It asserts
    EcdsaReady is still 0 and then verifies a published RFC 6979
    signature anyway, which is the self-initialisation promise in the
    header.  The INIT job after it calls EcdsaInit explicitly and checks
    the table it builds, so a wrong Montgomery constant shows up here
    rather than as "every signature is bad".
    """
    q, h, sig, expect, tag, note = raw[0]
    s.add(OP_COLD, "cold self-init then verify (case %d, %s)" % (tag, note),
          q=q, h=h, sig=sig, verdict=0, err=1)

    n = g.N
    words = (n.bit_length() + 14) // 15
    enc = ((words - 1) << 4) + (n >> (15 * (words - 1))).bit_length()
    n0i = (-pow(n & 0x7FFF, -1, 1 << 15)) % (1 << 15)
    s.add(OP_INIT, "EcdsaInit: order announced length, m0i and the "
                   "inversion exponent n-2",
          out=(n - 2).to_bytes(32, "big"), verdict=enc, err=n0i)


def build_script(g, level="full"):
    """level: "full" or "mutant".

    THERE IS NO --quick AND THERE WILL NOT BE ONE.  Thirty-seven of
    these forty-six records are NEGATIVES, and a signature gate that
    thins them out can go green against a verifier that answers "good"
    to everything - which is the exact failure this file exists to make
    impossible.  The full set is the small set.  Use --jobs to spread it
    across more workers instead.

    THE MUTANT SUBSET IS A TIME DECISION WITH ONE HARD REQUIREMENT: it
    must still reach every line a mutation can be planted in.  A P-256
    verify is two scalar multiplies and a modular inversion, so the
    expensive jobs are the ones that reach EcdsaMuladd and the cheap
    ones are the records refused by a length check or the DER walk
    before any arithmetic happens.  The subset therefore keeps EVERY
    cheap record - fourteen of the fifteen malformed-DER shapes, the
    whole curve gate, and the out-of-range and bad-framing raw
    negatives - and keeps only these expensive ones:

      * the cold verify (job 0), which M17 needs;
      * one raw negative that goes the whole way to the curve and back,
        which M6 needs - M6 only means anything against a record that
        must be REFUSED by the line it respells.

    THAT IS TWO SCALAR MULTIPLIES PER MUTATION instead of thirty-odd,
    which is the difference between a sweep of hours and a sweep of an
    hour, and everything cut is covered more cheaply somewhere else: a
    valid DER signature is parsed and its 64 converted bytes compared by
    the OP_CONVERT job without touching the curve, the seam is driven by
    the four curve-gate records, the arithmetic behind the last
    malformed-DER record is the path the raw jobs already run, and the
    off-curve record cannot distinguish M7 anyway (see MUTANT_RAW).
    Which lines the subset reaches is CHECKED rather than assumed - see
    --coverage, which reports the mutation anchors that no job in the
    subset can reach.
    """
    raw, asn1, der = g.build()
    s = Script()
    head_jobs(g, s, raw, asn1)
    mutant = (level == "mutant")

    # ---- CheckRaw: EcdsaVrfyRaw over the raw table -------------------
    for i, (q, h, sig, expect, tag, note) in enumerate(raw):
        if mutant and not (i in MUTANT_RAW):
            continue
        s.add(OP_RAW, "raw case %d: %s" % (tag, note), q=q, h=h, sig=sig,
              verdict=expect, err=ERR_OK if expect else ERR_BADSIG)

    # ---- CheckAsn1: through the certificate-path seam ----------------
    for i, (q, h, sig, expect, tag, note) in enumerate(asn1):
        # NO DER POSITIVE IN THE MUTANT SUBSET, ON PURPOSE.  What it
        # would prove - that a valid DER signature still parses - is
        # proved for free by the OP_CONVERT job below, which runs
        # EcdsaAsn1ToRaw on this same record and compares all 64 output
        # bytes without touching the curve.  A scalar multiply to learn
        # the same thing is eight-figure instruction counts for nothing.
        if mutant:
            continue
        s.add(OP_SEAM, "asn1 case %d via the seam: %s" % (tag, note),
              curve=23, q=q, h=h, sig=sig,
              verdict=expect, err=ERR_OK if expect else ERR_BADSIG)

    # The seam and the direct DER entry must agree.  Proving it once on
    # a valid record is enough: the seam is a two-line dispatch and a
    # point multiply is tens of millions of model instructions.
    if not mutant:
        q, h, sig, expect, tag, note = asn1[0]
        # NOT labelled "asn1 case ...": this is a SECOND run of a record
        # that already has its own job, and record_counts() counts labels
        # to prove all 46 ran. Naming it that way made the count read 47.
        s.add(OP_ASN1, "agreement: EcdsaVrfyAsn1 answers what the seam "
                       "answered for record %d" % tag,
              q=q, h=h, sig=sig, verdict=expect, err=ERR_OK)

    # ---- CheckDer: malformed shapes, refused BY THE ENCODING WALK ----
    # Fourteen of the fifteen are cheap - the DER walk refuses them
    # before any arithmetic - so the mutant subset keeps those.  The
    # LAST record is the generator's documented exception: well-formed
    # DER carrying r = s = 1, which must be refused as a bad SIGNATURE
    # rather than as a bad encoding, and is therefore the only one of
    # the fifteen that reaches the curve.  The mutant subset drops it.
    for i, (q, h, sig, expect, tag, note) in enumerate(der):
        last = (i == len(der) - 1)
        if mutant and last:
            continue
        s.add(OP_ASN1, "malformed der case %d: %s" % (tag, note),
              q=q, h=h, sig=sig, verdict=0,
              err=ERR_BADSIG if last else ERR_MALFORMED)

    # ---- CheckCurves: -1 is not 0, and that distinction is the point -
    q, h, sig, expect, tag, note = asn1[0]
    for cid, name in ((24, "P-384"), (25, "P-521"), (0, "curve id 0"),
                      (29, "curve id 29")):
        s.add(OP_SEAM, "curve gate: %s must answer -1 (cannot answer), "
                       "never 0 (a verdict)" % name,
              curve=cid, q=q, h=h, sig=sig, verdict=M64, err=ERR_CURVE)
    if not mutant:
        s.add(OP_SEAM, "curve gate: P-256 on the same record still answers "
                       "a real verdict",
              curve=23, q=q, h=h, sig=sig, verdict=1, err=ERR_OK)

    # ---- CheckConvert ------------------------------------------------
    s.add(OP_CONVERT, "EcdsaAsn1ToRaw on case %d yields 64 raw bytes" % tag,
          q=q, h=h, sig=sig, out=raw_of(g, sig),
          verdict=len(raw_of(g, sig)), err=ERR_OK)
    if not mutant:
        s.add(OP_NOCLOBBER, "EcdsaVrfyAsn1 leaves the caller's signature "
                            "bytes untouched", q=q, h=h, sig=sig,
              verdict=1, err=1)
        s.add(OP_CONVVRFY, "the converted raw form verifies the same way",
              q=q, h=h, sig=sig, verdict=len(raw_of(g, sig)), err=1)
    return s


# Which raw records the mutant subset keeps, by index into the generator's
# raw table.  ONE OF THESE IS EXPENSIVE AND THE REST ARE REFUSED BEFORE
# ANY CURVE ARITHMETIC RUNS.  Record 0, the first published RFC 6979
# signature, is NOT in the list because the cold job at the head of every
# shard already runs it - listing it again would buy a second identical
# scalar multiply, which at roughly 155 million model instructions a
# verify is the whole cost of the sweep.
#
#    5  "R changed (low bit of r)" - a negative that goes the whole way
#       to the curve and comes back with an X that does not match r.
#       THE SWEEP NEEDS A REJECT THAT GETS THAT FAR: M6 respells the
#       line that turns that mismatch into a 0, and against a record
#       refused earlier (or one that verifies) that line is never the
#       deciding one.
#   13  S = 0        15  S = n            18  public point 64 bytes
#   14  R = n        16  R = 2^256-1      20  odd raw signature length
#                    17  S = 2^256-1
#
# The off-curve record (21) is deliberately NOT here.  It looks like the
# natural companion to M7's point-at-infinity guard and it is not: with
# an off-curve point EcPointDecode already returns 0, so `r & BnNot(z&t)`
# is 0 whichever way the second operand is spelled and the record cannot
# distinguish the mutation.  EcdsaMuladd is reached by the cold job
# anyway, which is what --coverage checks.
MUTANT_RAW = {5, 13, 14, 15, 16, 17, 18, 20}


# =====================================================================
#  BUILD AND RUN
# =====================================================================
def build(ecdsa_include, harness, img):
    WORK.mkdir(exist_ok=True)
    src = HARNESS.replace("__ECDSA__", ecdsa_include)
    harness.write_text(src, encoding="utf-8")
    cmd = [str(PMFC), "--compile", str(harness), "-t", "pi4",
           "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
           "--entry-returns", "-o", str(img)]
    r = subprocess.run(cmd, cwd=ROOT, env=BUILD_ENV, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout:
        raise SystemExit("build failed:\n" + r.stdout)
    return img.stat().st_size


def run_raw(img_bytes, script, count, out_bytes):
    """Execute one script under the model.  Returns (records, out, steps)."""
    from a64_interp import A64
    cpu = A64()
    mem = cpu.memory
    for i, b in enumerate(img_bytes):
        mem[LOAD + i] = b
    for i, b in enumerate(script):
        mem[H_SCRIPT + i] = b
    for i in range(count * RESULT_STRIDE):
        mem[H_RESULT + i] = SENTINEL
    for i in range(out_bytes):
        mem[H_OUT + i] = SENTINEL

    cpu.pc = LOAD
    cpu.sp = LOADER_SP
    cpu.x[30] = LOADER_LR
    uart = bytearray()

    def load(addr, size):
        if UART_LO <= addr <= UART_HI:
            return 0                       # a PL011 that is never busy
        return sum(mem.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr, value, size):
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

    if b"ecdsaharness done" not in uart:
        raise SystemExit("the harness returned without finishing its "
                         "script:\n" + uart.decode("latin-1"))

    recs = [bytes(mem.get(H_RESULT + i * RESULT_STRIDE + j, 0)
                  for j in range(RESULT_STRIDE))
            for i in range(count)]
    out = bytes(mem.get(H_OUT + i, 0) for i in range(out_bytes))
    return recs, out, steps


def check_shard(script, recs, out):
    bad = []
    for i, (label, op, scalars, expect) in enumerate(script.jobs):
        rec = recs[i]
        s0, s1, outlen, _ = struct.unpack("<QQQQ", rec)
        if rec == bytes([SENTINEL]) * RESULT_STRIDE:
            bad.append("%s: no record was written at all" % label)
            continue
        v, e = scalars
        if v is not None and s0 != (v & M64):
            bad.append("%s: the verdict is %d (%016x at full width), want "
                       "%d - check that the record's expectation and the "
                       "library's answer are both 64 bits wide"
                       % (label, s0, s0, v))
        if e is not None and s1 != (e & M64):
            bad.append("%s: the second answer is %d (%016x at full width), "
                       "want %d" % (label, s1, s1, e))
        if expect is not None:
            off = script.out_off[i]
            got = out[off:off + len(expect)]
            if got != expect:
                bad.append("%s: %d bytes differ\n    want %s\n    got  %s"
                           % (label, len(expect), expect.hex(), got.hex()))
    return bad


def shard(script, n):
    """Split a Script into n Scripts, keeping every job's expectations.

    JOB 0 AND JOB 1 GO IN EVERY SHARD.  Job 0 is the COLD verify and it
    is only cold if nothing ran before it; job 1 builds the curve order
    every later job reads.  A shard without them would not be a smaller
    run of the same thing - it would be a different program.
    """
    head = [i for i, j in enumerate(script.jobs)
            if j[1] in (OP_COLD, OP_INIT)]
    nhead = len(head)
    body = list(range(nhead, len(script.jobs)))
    if n <= 1 or not body:
        return [script]

    # Interleave rather than block, so the scalar-multiply jobs are
    # spread across workers instead of landing in one.
    buckets = [body[i::n] for i in range(n)]
    out = []
    for b in buckets:
        if not b:
            continue
        s = Script()
        for idx in list(range(nhead)) + b:
            label, op, scalars, expect = script.jobs[idx]
            s._append(script.records[idx], label, op, scalars, expect)
        out.append(s)
    return out


def _worker(args):
    img_bytes, blob, count, out_bytes = args
    return run_raw(img_bytes, blob, count, out_bytes)


# =====================================================================
#  THE MUTATIONS
# =====================================================================
#  Each is (label, file, find, replace, verdict).  The verdict is what
#  the mutation is EXPECTED to earn:
#
#    "kill"     the vector set must catch it.  A survivor is a hole.
#    a string   an EXPECTED survivor, and the string is the argument for
#               why no known-answer test can see it.  These are NOT
#               deleted: the day one of them starts being caught is the
#               day its argument stopped being true, and that is as loud
#               a failure as an unexpected survivor.
#
#  There is no "timing" verdict in this table, because there is no
#  --timing - see the module docstring.
#
#  "harness" as the file mutates the GENERATED harness instead of the
#  library.  Nothing here needs it yet; the hook is kept because the
#  bignum gate needs it and the two files are read side by side.
#
#  WHY THIS TABLE CARRIES THE WHOLE AUDIT.  ecdsa.pi4's portable core is
#  BYTE-IDENTICAL to ecdsa.pico2's: all five 64-bit shapes were looked
#  for and none of them is present.  With no diff to read, the only
#  honest way to show the shapes were looked for is to PLANT each one
#  and record what happens.  M1-M2 are shape 1, M3-M4 are shape 2, M5 is
#  shape 3, M9 is shape 4's nearest reachable relative, and M6-M8 are
#  the fifth shape - the `>> 31` / `! $FFFFFFFF` family that made
#  GcmDecrypt accept a forged tag.  M10-M17 are ordinary defect
#  mutations, there so the gate is not only a width test.
#
#  SHAPE 4 HAS NO MUTATION AND THAT IS DELIBERATE.  There is no counter
#  in this file that is allowed anywhere near 2^32 - every loop index is
#  bounded by a public length under 300 - so any "wrapping counter"
#  mutation would be fiction planted to be killed.  The finding is
#  recorded in the header and left at that.
# =====================================================================
MUTATIONS = [
    # ---- SHAPE 1: an array element is EIGHT bytes, not four ---------
    ("M1  the curve-order buffer is tidied from .w to .i", "ecdsa",
     "Global Dim EcdsaN.w[#ECDSA_NWORDS]",
     "Global Dim EcdsaN.i[#ECDSA_NWORDS]",
     "kill"),

    ("M2  an ec256 point register is tidied from .w to .i", "ecdsa",
     "Global Dim EcdsaPpt.w[3 * #EC_WORDS]",
     "Global Dim EcdsaPpt.i[3 * #EC_WORDS]",
     "kill"),

    # ---- SHAPE 2: PeekL / PeekB sign-extend --------------------------
    ("M3  EcdsaDecodeMod reads its bytes signed and unmasked", "ecdsa",
     "      bb = PeekA(src + len - 1 - u) & 255",
     "      bb = PeekB(src + len - 1 - u)",
     "kill"),

    ("M4  the DER SEQUENCE length byte is read signed and unmasked",
     "ecdsa",
     "  zlen = PeekA(bufAddr + 1) & 255",
     "  zlen = PeekB(bufAddr + 1)",
     "THE STRICT PARSER'S DEFAULT IS REFUSAL, AND THAT IS WHAT ABSORBS "
     "IT. A sign-extended length byte only differs from an unsigned one "
     "at $80 and above, and every such encoding in the shared table - "
     "the 0x81 long form, the 0x82 over-long form, the 0x80 indefinite "
     "marker - is one this module must refuse anyway. The mutation "
     "changes WHICH line refuses them (the `zlen <> sigLen - 2` "
     "comparison instead of the explicit long-form checks) and not the "
     "verdict, and EcdsaLastErr is MALFORMED either way. Every valid "
     "P-256 signature has a body under 127 bytes, so the short form is "
     "all the positives ever use. It would stop being absorbed for a "
     "curve whose DER body exceeds 127 bytes - P-521 - which this "
     "module refuses by curve id before the parser is reached."),

    # ---- SHAPE 3: `<<` does not discard at bit 31 --------------------
    ("M5  the DER walk gains the lenient multi-byte length assembly",
     "ecdsa",
     # THE ANCHOR HAS TO SWALLOW THE `zlen <> $81` GUARD TOO. Planted
     # below it, the loop can only ever run once - the guard refuses
     # 0x82 before the shift is reached - and a shift that iterates once
     # is not the shape being demonstrated. Taking the guard as well is
     # exactly what a lenient parser looks like.
     "    If zlen <> $81\n"
     "      ProcedureReturn 0\n"
     "    EndIf\n"
     "    zlen = PeekA(bufAddr + 2) & 255\n"
     "    If zlen < $80\n"
     "      ProcedureReturn 0\n"
     "    EndIf\n"
     "    If zlen <> sigLen - 3\n"
     "      ProcedureReturn 0\n"
     "    EndIf\n"
     "    off = 3",
     # rlen and i are already Protected at the top of EcdsaAsn1ToRaw and
     # are both dead here (the r block below reassigns rlen before
     # reading it), so the planted loop needs no new declaration and
     # cannot turn into a NOBUILD for a reason unrelated to the shape.
     "    rlen = (PeekA(bufAddr + 1) & 255) - $80\n"
     "    zlen = 0\n"
     "    i = 0\n"
     "    While i < rlen\n"
     "      zlen = (zlen << 8) | (PeekA(bufAddr + 2 + i) & 255)\n"
     "      i = i + 1\n"
     "    Wend\n"
     "    If zlen <> sigLen - 2 - rlen\n"
     "      ProcedureReturn 0\n"
     "    EndIf\n"
     "    off = 2 + rlen",
     "kill"),

    # ---- SHAPE 5: `x ! $FFFFFFFF` as a logical NOT --------------------
    ("M6  EcdsaVrfyRaw's final BnNot becomes the GcmDecrypt complement",
     "ecdsa",
     "  res = res & BnNot(BnSub(@EcdsaT1, @EcdsaR, 1))",
     "  res = res & (BnSub(@EcdsaT1, @EcdsaR, 1) ! $FFFFFFFF)",
     "THE SAME SHAPE THAT MADE GcmDecrypt ACCEPT A FORGED TAG, PLANTED "
     "IN THE LINE THAT DECIDES WHETHER A SIGNATURE IS VALID - AND IT "
     "SURVIVES. Worth knowing exactly, rather than assuming either way. "
     "The reason is the operand on the LEFT: res is 0 or 1, so `res & "
     "(borrow ! $FFFFFFFF)` is res & $FFFFFFFF = res when borrow is 0 "
     "and res & $FFFFFFFE = 0 when borrow is 1 - which is the same "
     "truth table BnNot gives. The 64-bit half of the complement is "
     "never read because nothing to its left has a bit above 0. That is "
     "the identical finding ec256.pi4 recorded for its two real sites, "
     "and it is exactly why the header insists a reader cannot tell the "
     "safe instance of this shape from the fatal one without redoing "
     "the analysis. M8 is the fatal one, one line away."),

    ("M7  EcdsaMuladd's point-at-infinity guard uses the complement",
     "ecdsa",
     "  ProcedureReturn r & BnNot(z & t)",
     "  ProcedureReturn r & ((z & t) ! $FFFFFFFF)",
     "SAME ARGUMENT AS M6, on the guard that decides whether the two "
     "ladders summed to the point at infinity. r comes out of "
     "EcPointDecode as 0 or 1 and it is on the left, so the complement's "
     "high half is masked away before anything reads it. Recorded "
     "separately from M6 because this one's answer feeds a DIFFERENT "
     "caller path and a reader should not have to assume the two "
     "arguments are the same argument."),

    ("M8  the conditional-subtraction control uses a 32-bit complement",
     "ecdsa",
     "  BnSub(@EcdsaT1, @EcdsaN, borrow ! 1)\n\n  ; ty := hash/s",
     "  BnSub(@EcdsaT1, @EcdsaN, borrow ! $FFFFFFFF)\n\n  ; ty := hash/s",
     "kill"),

    # ---- SHAPE 4's nearest reachable relative ------------------------
    ("M9  EcdsaAsn1ToRaw drops the output-buffer bound check", "ecdsa",
     "  outLen = zlen << 1\n  If outLen > #ECDSA_RAWMAX\n"
     "    ProcedureReturn 0\n  EndIf",
     "  outLen = zlen << 1",
     "UNREACHABLE FROM THIS BENCH, AND THAT IS THE WHOLE POINT OF IT. "
     "outLen is at most twice the wider DER integer, each of which the "
     "parser has already capped at 127 by refusing the long form, so "
     "outLen cannot exceed 254 and #ECDSA_RAWMAX is 300. Nothing in the "
     "shared table comes close, and nothing could without a DER "
     "signature longer than #ECDSA_SIGMAX = 150, which EcdsaVrfyAsn1 "
     "refuses first. The check is defence in depth against a future "
     "SIGMAX change and against a caller reaching EcdsaAsn1ToRaw "
     "directly with its own buffer. Reasoning, not a reproduction, and "
     "labelled as such."),

    # ---- ORDINARY DEFECTS, so the gate is not only a width test ------
    ("M10 an unimplemented curve answers 0 instead of -1", "ecdsa",
     "    EcdsaLastErr = #ECDSA_ERR_CURVE\n    ProcedureReturn -1",
     "    EcdsaLastErr = #ECDSA_ERR_CURVE\n    ProcedureReturn 0",
     "kill"),

    ("M11 EcdsaAsn1ToRaw accepts a negative INTEGER for r", "ecdsa",
     "  rp = bufAddr + off\n  If (PeekA(rp) & 128) <> 0\n"
     "    ProcedureReturn 0\n  EndIf",
     "  rp = bufAddr + off",
     "kill"),

    ("M12 EcdsaAsn1ToRaw accepts a non-minimal leading zero on s",
     "ecdsa",
     "  If slen > 1\n    If (PeekA(sp) & 255) = 0\n"
     "      If (PeekA(sp + 1) & 128) = 0\n        ProcedureReturn 0\n"
     "      EndIf\n    EndIf\n  EndIf",
     "",
     "kill"),

    ("M13 EcdsaAsn1ToRaw accepts an INTEGER with no content bytes",
     "ecdsa",
     "  If rlen = 0\n    ProcedureReturn 0\n  EndIf",
     "",
     "kill"),

    ("M14 EcdsaVrfyRaw stops refusing s = 0", "ecdsa",
     "  If BnIsZero(@EcdsaS) <> 0\n    ProcedureReturn 0\n  EndIf",
     "",
     "THE ARITHMETIC REFUSES IT ANYWAY, WHICH IS NOT THE SAME AS THE "
     "CHECK BEING POINTLESS. With the check gone, s = 0 leaves "
     "Montgomery form as 0, the modular ladder computes 0^(n-2) = 0, "
     "both scalars become 0, both ladders land on the point at infinity "
     "and EcdsaMuladd reports 0 - so the record is still refused, with "
     "the same EcdsaLastErr, and no known-answer test can tell. The "
     "check stays because FIPS 186-4 requires 1 <= s < n as a RANGE "
     "CHECK, and because relying on 1/0 falling out of a Montgomery "
     "ladder as 0 is relying on an accident of BnModpow rather than on "
     "anything this file states. It is also the difference between "
     "refusing a signature and spending two scalar multiplies on it."),

    ("M15 EcdsaDecodeMod stops requiring the value to be below the order",
     "ecdsa",
     "  ProcedureReturn below & BnNot(over)",
     "  ProcedureReturn BnNot(over)",
     "THE FINAL X-COORDINATE COMPARISON IS A BACKSTOP AND IT CATCHES "
     "ALL FOUR OUT-OF-RANGE RECORDS BY ITSELF. r = n, s = n, r = "
     "2^256-1 and s = 2^256-1 all reduce mod n inside the Montgomery "
     "routines, so the verify equation is computed for some OTHER "
     "signature and the resulting X does not match the r that was "
     "handed in - refused, with the same EcdsaLastErr. What the range "
     "check buys is refusing the encoding rather than reinterpreting "
     "it, which is FIPS 186-4's requirement and is the same argument "
     "the DER walk's strictness rests on. No known-answer test can see "
     "the difference; a signature-malleability argument can."),

    ("M16 EcdsaBits2Int stops truncating a hash longer than the order",
     "ecdsa",
     "  If hbitlen > bitlen\n    len = (bitlen + 7) >> 3\n"
     "    sc = (hbitlen - bitlen) & 7\n  EndIf",
     "",
     "THE SHARED VECTOR SET CANNOT REACH THIS BRANCH AND THIS GATE WILL "
     "NOT INVENT A VECTOR THAT DOES. Every record in "
     "tools/gen_ecdsa_vectors.py is SHA-256 over P-256, where the hash "
     "is 256 bits and the order announces 256 bits, so hbitlen > bitlen "
     "is false in all 46 of them and the branch is dead code here. It "
     "fires for SHA-384 or SHA-512 against P-256, which TLS 1.3 does "
     "permit. THIS IS A REAL COVERAGE GAP, not a safe line: the fix is "
     "a longer-hash record in the SHARED generator, where all four "
     "families would get it, and not a one-off expectation computed in "
     "this file. Recorded here so it is visible rather than absent."),

    ("M17 EcdsaEnsureInit never initialises from cold", "ecdsa",
     "  If EcdsaReady = 0\n    EcdsaInit()\n  EndIf",
     "  If EcdsaReady = 1\n    EcdsaInit()\n  EndIf",
     "kill"),
]


def mutate_source(idx, which, find, replace, harness_text):
    """Write a mutated COPY into _work/ and return (include, harness).

    THIS NEVER OPENS THE REAL SOURCE FOR WRITING, and every mutation
    gets its OWN filename.  When the A64 GCM sweep let every mutant of
    one file share a name, four of them raced, the compiler read a
    half-written file, and the pool reported four survivors that were
    nothing of the kind.
    """
    WORK.mkdir(exist_ok=True)
    if which == "harness":
        if harness_text.count(find) != 1:
            raise SystemExit("mutation anchor not unique in the harness:\n%r"
                             % find)
        return "RaspberryPi4/Lib/ecdsa.pi4", harness_text.replace(
            find, replace, 1)
    text = ECDSA.read_text(encoding="utf-8")
    if text.count(find) != 1:
        raise SystemExit("mutation anchor found %d times in %s (want 1):\n%r"
                         % (text.count(find), ECDSA.name, find))
    out = WORK / ("mut%02d_%s" % (idx, ECDSA.name))
    out.write_text(text.replace(find, replace, 1), encoding="utf-8")
    return "_work/" + out.name, harness_text


def build_mutant(idx, include, harness_text, img):
    WORK.mkdir(exist_ok=True)
    src = harness_text.replace("__ECDSA__", include)
    hp = WORK / ("ecdsaharness_mut%02d.pi4" % idx)
    hp.write_text(src, encoding="utf-8")
    cmd = [str(PMFC), "--compile", str(hp), "-t", "pi4",
           "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
           "--entry-returns", "-o", str(img)]
    r = subprocess.run(cmd, cwd=ROOT, env=BUILD_ENV, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout:
        raise SystemExit("build failed:\n" + r.stdout)
    return img.stat().st_size


def coverage(g):
    """Does the mutant subset still reach every mutated line?

    A SUBSET THAT QUIETLY STOPS REACHING A LINE IS HOW A MUTATION
    SURVIVES FOR THE WRONG REASON.  This does not run the model: it
    reports, per mutation, which entry points the mutated procedure sits
    behind and whether the mutant subset contains a job that calls one.
    It is a structural claim about the job list, printed so a reader can
    check it against the table above rather than trust the caps.
    """
    s = build_script(g, level="mutant")
    ops = set(op for _, op, _, _ in s.jobs)
    # entry points each mutation's procedure sits behind
    need = {
        "M1": {OP_COLD, OP_RAW, OP_SEAM}, "M2": {OP_COLD, OP_RAW, OP_SEAM},
        "M3": {OP_COLD, OP_RAW, OP_SEAM}, "M4": {OP_ASN1, OP_SEAM,
                                                 OP_CONVERT},
        "M5": {OP_ASN1, OP_CONVERT}, "M6": {OP_COLD, OP_RAW, OP_SEAM},
        "M7": {OP_COLD, OP_RAW, OP_SEAM}, "M8": {OP_COLD, OP_RAW, OP_SEAM},
        "M9": {OP_ASN1, OP_SEAM, OP_CONVERT},
        "M10": {OP_SEAM}, "M11": {OP_ASN1, OP_SEAM, OP_CONVERT},
        "M12": {OP_ASN1, OP_SEAM, OP_CONVERT},
        "M13": {OP_ASN1, OP_SEAM, OP_CONVERT}, "M14": {OP_COLD, OP_RAW},
        "M15": {OP_COLD, OP_RAW, OP_SEAM}, "M16": {OP_COLD, OP_RAW, OP_SEAM},
        "M17": {OP_COLD},
    }
    print("[coverage] the mutant subset is %d jobs using ops %s"
          % (len(s), sorted(ops)))
    gaps = 0
    for label, _, _, _, _ in [(m[0], 0, 0, 0, 0) for m in MUTATIONS]:
        key = label.split()[0]
        if not (need.get(key, set()) & ops):
            gaps += 1
            print("  UNREACHED %s - no job in the mutant subset calls it"
                  % label)
    if gaps == 0:
        print("[coverage] every mutation anchor is reachable from the "
              "mutant subset")
    return 1 if gaps else 0



def record_counts(g, s):
    """How many of the SHARED table's records this script actually runs.

    THE GENERATOR PRINTS "9 must verify, 37 must reject" AND THIS GATE
    HAS TO AGREE WITH IT OR SAY SO.  Counting jobs is not the same as
    counting records - the script adds a cold verify, an init check, a
    seam/direct agreement check, a curve gate and three converter jobs
    on top - so the two are counted separately, and a full run that has
    dropped a record fails here rather than quietly reporting a smaller
    number as a pass.
    """
    raw, asn1, der = g.build()
    npos = (sum(1 for c in raw if c[3] == 1)
            + sum(1 for c in asn1 if c[3] == 1))
    nneg = len(raw) + len(asn1) + len(der) - npos
    seen = sum(1 for lab, op, sc, _ in s.jobs
               if lab.startswith(("raw case ", "asn1 case ",
                                  "malformed der case ")))
    ncannot = sum(1 for lab, op, sc, _ in s.jobs
                  if op == OP_SEAM and sc[0] == M64)
    nextra = len(s) - seen - ncannot
    if seen != npos + nneg:
        raise SystemExit(
            "the script runs %d of the shared table's %d records and a "
            "full run must run all of them - 37 of them are NEGATIVES, "
            "which is the half a signature gate exists for. Check "
            "build_script's filters before trusting any green above."
            % (seen, npos + nneg))
    return npos, nneg, ncannot, nextra


# =====================================================================
#  RUNNING A WHOLE SCRIPT, SHARDED
# =====================================================================
def run_all(img, script, jobs=None, quiet=False):
    """Run every job, across a process pool.  Returns (failures, steps)."""
    img_bytes = img.read_bytes()
    n = jobs or max(1, (os.cpu_count() or 2) - 2)
    shards = shard(script, n)
    if len(shards) == 1:
        recs, out, steps = run_raw(img_bytes, shards[0].done(),
                                   len(shards[0]), shards[0]._o)
        return check_shard(shards[0], recs, out), steps

    if not quiet:
        print("[gate] %d jobs across %d workers" % (len(script), len(shards)),
              file=sys.stderr)
    args = [(img_bytes, s.done(), len(s), s._o) for s in shards]
    bad = []
    steps = 0
    with concurrent.futures.ProcessPoolExecutor(max_workers=len(shards)) as ex:
        for s, (recs, out, st) in zip(shards, ex.map(_worker, args)):
            bad += check_shard(s, recs, out)
            steps += st
    return bad, steps


# =====================================================================
#  MAIN
# =====================================================================
def resolve_compiler(requested):
    """Resolve the PureMetal compiler the way tools/build.py does."""
    sys.path.insert(0, str(ROOT / "tools"))
    import build as anvil_build  # noqa: E402
    return anvil_build.find_compiler(requested)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"),
                    help="path of PureMetalForge.exe (or set PMF_COMPILER); "
                         "it is run with --compile")
    ap.add_argument("--mutate", action="store_true", help="the mutation sweep")
    ap.add_argument("--mutation", type=int, default=None,
                    help="run ONE mutation by index (used by the pool)")
    ap.add_argument("--coverage", action="store_true",
                    help="report which mutation anchors the mutant subset "
                         "can reach")
    ap.add_argument("--jobs", type=int, default=None,
                    help="worker processes (default: cores - 2)")
    args = ap.parse_args(argv)
    globals()["PMFC"] = resolve_compiler(args.compiler)
    globals()["JOBS_CAP"] = args.jobs

    print("[gate] tree under test: %s" % ROOT, file=sys.stderr)

    g = load_tables()

    if args.coverage:
        return coverage(g)

    if args.mutation is not None:
        i = args.mutation
        label, which, find, repl, verdict = MUTATIONS[i]
        inc, harness_text = mutate_source(i, which, find, repl, HARNESS)
        img = WORK / ("ecdsa_mut%02d.img" % i)
        try:
            build_mutant(i, inc, harness_text, img)
        except SystemExit as e:
            # A MUTANT THAT WILL NOT BUILD IS KILLED BY THE COMPILER, and
            # that is a legitimate kill - but it is a DIFFERENT verdict
            # from "the vectors caught it" and is printed as one.
            print("NOBUILD  %s\n         %s" % (label, str(e).splitlines()[0]))
            return 0
        s = build_script(g, level="mutant")
        bad, _ = run_all(img, s, jobs=args.jobs, quiet=True)

        if verdict == "kill":
            if bad:
                print("KILLED   %s\n         first: %s"
                      % (label, bad[0].splitlines()[0]))
                return 0
            print("SURVIVED %s\n         (the vector set was expected to "
                  "catch this one)" % label)
            return 1

        if bad:
            print("UNEXPECTED-KILL %s\n         the vector set now catches "
                  "this, so the recorded argument is stale:\n         %s"
                  % (label, verdict))
            return 1
        print("EXPECTED-SURVIVOR %s" % label)
        return 0

    if args.mutate:
        n = args.jobs or max(1, (os.cpu_count() or 2) - 2)
        print("[gate] %d mutations across %d workers" % (len(MUTATIONS), n))
        t0 = time.time()
        survivors = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=n) as ex:
            futs = {ex.submit(subprocess.run,
                              [sys.executable, __file__, "--mutation",
                               str(i), "--jobs", "1",
                               "--compiler", str(PMFC)],
                              cwd=ROOT, env=BUILD_ENV,
                              capture_output=True, text=True): i
                    for i in range(len(MUTATIONS))}
            for f in concurrent.futures.as_completed(futs):
                i = futs[f]
                r = f.result()
                sys.stdout.write(r.stdout)
                if r.returncode != 0:
                    sys.stdout.write(r.stderr)
                    survivors.append(MUTATIONS[i][0])
        expected = sum(1 for m in MUTATIONS if m[4] != "kill")
        print("[gate] sweep took %.0f s" % (time.time() - t0))
        if survivors:
            print("MUTATION SWEEP RED: %d unexpected outcome(s):\n  %s"
                  % (len(survivors), "\n  ".join(survivors)))
            return 1
        print("MUTATION SWEEP GREEN: 0 unexpected outcomes of %d "
              "(%d of them are EXPECTED survivors, each with its recorded "
              "argument in the table)" % (len(MUTATIONS), expected))
        return 0

    s = build_script(g, level="full")
    img = WORK / "ecdsaharness.img"
    size = build("RaspberryPi4/Lib/ecdsa.pi4", WORK / "ecdsaharness.pi4", img)
    npos, nneg, ncannot, nextra = record_counts(g, s)
    print("[gate] image %d bytes, %d jobs: all %d records of the shared "
          "table run - %d signatures must verify, %d must be refused; "
          "plus %d curves that must answer -1 and %d extra jobs (the cold "
          "self-init verify, the EcdsaInit table check, the seam/direct "
          "agreement check and the three converter checks)"
          % (size, len(s), npos + nneg, npos, nneg, ncannot, nextra))
    t0 = time.time()
    bad, steps = run_all(img, s, jobs=args.jobs)
    for b in bad:
        print("FAIL: " + b)
    print("[gate] %d jobs, %d model instructions, %.0f s"
          % (len(s), steps, time.time() - t0))
    if bad:
        print("ECDSA GATE RED: %d of %d jobs wrong" % (len(bad), len(s)))
        return 1

    print("ECDSA GATE GREEN: %d jobs on the shared P-256 vector set - "
          "%d signatures verified, %d refused, %d unimplemented curves "
          "answered -1; %d model instructions"
          % (len(s), npos, nneg, ncannot, steps))
    return 0


if __name__ == "__main__":
    sys.exit(main())

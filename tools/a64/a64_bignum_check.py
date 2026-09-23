#!/usr/bin/env python3
"""Executable gate for RaspberryPi4/Lib/bignum.pi4 - the i15 big-integer
core on AArch64.

WHY THIS FILE IS WRITTEN THE WAY IT IS

  THE VECTORS ARE THE ONES THE PICO GATES ALREADY USE.  They are not
  transcribed here and they are not generated here: this gate IMPORTS
  the case tables out of tools/gen_bignum_vectors.py, the file that
  emits bignumVectors.pico2 / .pico / .unor4 for the three 32-bit
  families and whose expected values all come from Python's
  arbitrary-precision integers.  One table, four families - so "the
  Pi 4 passes the same vectors" is a fact about the source rather than
  a claim about two lists that were once eyeballed.

  THE OPERATIONS ARE THE ONES bignumSelfTest.pico2 PERFORMS.  Each op
  below mirrors one Check* procedure of the 32-bit self-test, call for
  call, so a difference in an answer is a difference in the library and
  not in how it was driven.

  THREE THINGS ARE CHECKED HERE THAT NO 32-BIT COPY CHECKS, and each
  exists because of something the 64-bit port touched:

    * BnMulAcc.  The plain (non-modular) multiply-accumulate has no
      case in the shared table, and its announced-length line is one of
      the six sites where a `>> 31` sign test was rewritten.  Its
      expectation is a Python product, computed here from the shared
      table's own operands.
    * THE WORD HELPERS at full 32-bit width.  BnGt was REWRITTEN for
      this part - a 64-bit register does the unsigned compare exactly,
      where the 32-bit copies must reconstruct the borrow out of a
      subtraction that wrapped.  Nothing in the shared vector set ever
      hands BnGt an operand above 2^15, so the rewrite would have been
      completely untested by it.
    * A `.i` CALLER BUFFER.  Shape 1 of the four-shape audit says an
      array element is EIGHT bytes here and this core addresses word i
      at base + i*2.  The core itself declares no array, so the shape
      lands on the CALLER - and mutation M1 is the harness declaring
      one buffer `.i`, so the sweep proves the note in the header is
      about something real.

  IT RUNS ON ALL CORES.  A 3072-bit modular exponentiation is tens of
  millions of model instructions and the whole set is hundreds of
  millions, which is hours in one process.  The image is built ONCE and
  the job list is sharded across a process pool; every worker runs the
  same image over its own slice of the script.  --jobs overrides.

WHAT THIS GATE DOES NOT SAY

  * That any of this runs on silicon.  The oracle is a model of the
    instruction set: no caches, no memory system, no clock.
  * That the implementation is constant time ON HARDWARE.  --timing
    checks that the MODEL executes the identical number of instructions
    for exponents and bases of wholly different content at the same
    lengths, which rules out a data-dependent branch or a
    secret-indexed access in the compiled code.  It says nothing about
    what a real Cortex-A72 does with those instructions.

Run: python tools/a64/a64_bignum_check.py
     python tools/a64/a64_bignum_check.py --quick
     python tools/a64/a64_bignum_check.py --timing
     python tools/a64/a64_bignum_check.py --mutate
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
BIGNUM = ROOT / "RaspberryPi4" / "Lib" / "bignum.pi4"
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

STEP_LIMIT = 40_000_000_000

RESULT_STRIDE = 32          # scalar0, scalar1, outlen, spare - all i64
SENTINEL = 0xA5

(OP_END, OP_MODLOAD, OP_ROUNDTRIP, OP_ISZERO, OP_BITLEN, OP_RSHIFT,
 OP_ADD, OP_SUB, OP_REDUCE, OP_DECRED, OP_MONTMUL, OP_MODPOW,
 OP_MODPOW2, OP_MULACC, OP_WORDS) = range(15)


# =====================================================================
#  THE HARNESS
# =====================================================================
#  It reads a script of jobs out of memory at #H_SCRIPT, runs each one,
#  and writes a fixed 32-byte record per job at #H_RESULT plus any
#  produced bytes at #H_OUT.  Every vector is DATA, so adding one never
#  changes this file.
#
#  SCRIPT RECORD - a 28-byte header, then blob0 || blob1, padded to 4:
#      +0 op  +4 a0  +8 a1  +12 n0  +16 n1  +20 outlen  +24 (spare)
#  op 0 ends the script.
#
#  RESULT RECORD - 32 bytes, FOUR 64-BIT FIELDS:
#      +0  scalar0   the job's numeric answer (carry, verdict, flags)
#      +8  scalar1   a second answer where the job has one
#      +16 outlen    the byte count written to #H_OUT for this job
#      +24 spare
#
#  THE FIELDS ARE 64 BITS AND THAT IS NOT DECORATION.  The A64 GCM gate
#  stored its verdicts with PokeN and the one mutation it existed to
#  catch survived, because the wrong value's set bits were all above
#  bit 31 and the low half read back clean.  Every scalar this file
#  reports is stored at full width for the same reason.
# =====================================================================
HARNESS = r'''
; ======================================================================
;  bnharness.pi4 - GENERATED BY tools/a64/a64_bignum_check.py.
;  NOT A SOURCE FILE. DO NOT EDIT.
; ======================================================================
XIncludeFile "RaspberryPi4/Lib/uart.pi4"
XIncludeFile "__BIGNUM__"

#H_SCRIPT = $06000000
#H_RESULT = $0A000000
#H_OUT    = $0B000000

#MODSLOTS  = 5                       ; four shared + one derived, see DERIVED_MOD
#MODSTRIDE = 512                     ; 16-bit words between moduli

; EVERY BUFFER IS `.u`, NOT `.i`, AND THAT IS THE POINT OF MUTATION M1.
; A `Dim x.i[n]` element is EIGHT bytes on this part; bignum.pi4
; addresses word i at base + i*2.  The library declares no array of its
; own, so this is the only place the shape can be got wrong, and it is
; the caller's mistake to make.
Global Dim ModStore.u[#MODSLOTS * #MODSTRIDE]
Global Dim ModM0i.i[#MODSLOTS]
Global Dim ModEnc.i[#MODSLOTS]

Global Dim Xa.u[600]
Global Dim Aa.u[600]
Global Dim Ba.u[600]
Global Dim Ta.u[600]
Global Dim Tb.u[600]
Global Dim Da.u[1200]
Global Dim BigA.u[1200]
Global Dim Tmp.u[4096]

Procedure.i ModPtr(idx.i)
  ProcedureReturn @ModStore[0] + idx * (#MODSTRIDE << 1)
EndProcedure

; Clear words 0..n of a buffer, so nothing survives from a previous job.
Procedure BhZero(x.i, n.i)
  Define i.i
  i = 0
  While i <= n
    PokeW(x + (i << 1), 0)
    i = i + 1
  Wend
EndProcedure

; Fill words 0..n with a value.  Used to POISON a destination buffer, so
; that a procedure which fails to write a word it promised to write is
; caught instead of reading back a zero the harness put there.
Procedure BhFill(x.i, n.i, v.i)
  Define i.i
  i = 0
  While i <= n
    PokeW(x + (i << 1), v & $FFFF)
    i = i + 1
  Wend
EndProcedure

; Load a fixed-width value: clear, decode, then force the announced
; length to W full 15-bit limbs - what add/sub need so both operands
; share a length.  This is LoadFixed() out of bignumSelfTest, unchanged.
Procedure BhLoadFixed(x.i, srcbuf.i, nbytes.i, W.i)
  BhZero(x, W + 2)
  BnDecode(x, srcbuf, nbytes)
  BnSw(x, 0, ((W - 1) << 4) + 15)
EndProcedure

Procedure.i Main()
  Define p.i
  Define q.i
  Define o.i
  Define op.i
  Define a0.i
  Define a1.i
  Define n0.i
  Define n1.i
  Define outlen.i
  Define b0.i
  Define b1.i
  Define mp.i
  Define enc.i
  Define s0.i
  Define s1.i
  Define i.i
  Define alen.i
  Define blen.i

  p = #H_SCRIPT
  q = #H_RESULT
  o = #H_OUT

  Repeat
    op     = PeekN(p)
    a0     = PeekN(p + 4)
    a1     = PeekN(p + 8)
    n0     = PeekN(p + 12)
    n1     = PeekN(p + 16)
    outlen = PeekN(p + 20)
    If op = 0
      Break
    EndIf
    b0 = p + 28
    b1 = b0 + n0

    s0 = 0
    s1 = 0

    If op = 1
      ; MODLOAD - decode a modulus into its slot and derive m0i.
      mp = ModPtr(a0)
      BhZero(mp, #MODSTRIDE - 1)
      BnDecode(mp, b0, n0)
      ModEnc[a0] = BnGw(mp, 0)
      ModM0i[a0] = BnNinv15(BnGw(mp, 1))
      s0 = ModEnc[a0]
      s1 = ModM0i[a0]

    ElseIf op = 2
      ; ROUNDTRIP - decode then re-encode to the same length.
      BhZero(@Xa[0], 599)
      BnDecode(@Xa[0], b0, n0)
      BnEncode(o, outlen, @Xa[0])

    ElseIf op = 3
      ; ISZERO
      BhZero(@Xa[0], 599)
      BnDecode(@Xa[0], b0, n0)
      s0 = BnIsZero(@Xa[0])

    ElseIf op = 4
      ; BITLEN - the true bit length, out of the encoded announced one.
      BhZero(@Xa[0], 599)
      BnDecode(@Xa[0], b0, n0)
      ; READ BY INDEX, NOT THROUGH BnGw, AND THAT IS DELIBERATE.  This is
      ; the one place the harness touches a big integer the way a CALLER
      ; naturally would - `Xa[0]` - instead of going through the
      ; library's own word accessor.  With a `.u` buffer the two agree.
      ; With a `.i` buffer they do not, because an element is eight
      ; bytes and the library wrote word 0 at base + 0 as sixteen bits.
      ; That is shape 1, and mutation M1 is exactly this buffer declared
      ; `.i`.  Without this line M1 survives: declaring the buffer wider
      ; only OVER-ALLOCATES it, and a harness that never indexes cannot
      ; tell.  The sweep is what said so.
      enc = Xa[0]
      s0 = (enc >> 4) * 15 + (enc & 15)

    ElseIf op = 5
      ; RSHIFT by a0 bits, re-encoded to the input length.
      BhZero(@Xa[0], 599)
      BnDecode(@Xa[0], b0, n0)
      BnRshift(@Xa[0], a0)
      BnEncode(o, outlen, @Xa[0])

    ElseIf op = 6
      ; ADD at a fixed width of a0 limbs; s0 is the carry out.
      BhLoadFixed(@Aa[0], b0, n0, a0)
      BhLoadFixed(@Ba[0], b1, n1, a0)
      s0 = BnAdd(@Aa[0], @Ba[0], 1)
      BnEncode(o, outlen, @Aa[0])

    ElseIf op = 7
      ; SUB at a fixed width of a0 limbs; s0 is the borrow out.
      BhLoadFixed(@Aa[0], b0, n0, a0)
      BhLoadFixed(@Ba[0], b1, n1, a0)
      s0 = BnSub(@Aa[0], @Ba[0], 1)
      BnEncode(o, outlen, @Aa[0])

    ElseIf op = 8
      ; REDUCE - x = a mod m through the decode-then-reduce path.
      ;
      ; THE DESTINATION IS POISONED, NOT CLEARED, and that is the whole
      ; difference between this job catching BnReduce's `BnSw(x, mlen, 0)`
      ; and not.  Clearing it first makes that line redundant, so a
      ; mutation removing it survived - the harness was quietly doing
      ; the library's work.  BnReduce promises to write every word up to
      ; the modulus length; poison proves it.
      mp = ModPtr(a0)
      BhZero(@BigA[0], 1199)
      BhFill(@Xa[0], 599, $5A5A)
      BnDecode(@BigA[0], b0, n0)
      BnReduce(@Xa[0], @BigA[0], mp)
      BnEncode(o, outlen, @Xa[0])

    ElseIf op = 9
      ; DECODEREDUCE - the same answer by the one-pass route, which is
      ; what ecdsa and rsa actually call.  Same expectation as op 8, so
      ; a fault in either shows up as a disagreement with Python and
      ; not merely as the two of them agreeing with each other.
      mp = ModPtr(a0)
      BhZero(@Xa[0], 599)
      BnDecodeReduce(@Xa[0], b0, n0, mp)
      BnEncode(o, outlen, @Xa[0])

    ElseIf op = 10
      ; MONTMUL - (a*b) mod m, through to-Montgomery and back.
      mp = ModPtr(a0)
      BhZero(@Aa[0], 599)
      BhZero(@Ba[0], 599)
      BhZero(@Ta[0], 599)
      BnDecodeReduce(@Aa[0], b0, n0, mp)
      BnDecodeReduce(@Ba[0], b1, n1, mp)
      BnToMonty(@Aa[0], mp)
      BnToMonty(@Ba[0], mp)
      BnMontmul(@Ta[0], @Aa[0], @Ba[0], mp, ModM0i[a0])
      BnFromMonty(@Ta[0], mp, ModM0i[a0])
      BnEncode(o, outlen, @Ta[0])

    ElseIf op = 11
      ; MODPOW - the Montgomery ladder.
      mp = ModPtr(a0)
      BhZero(@Xa[0], 599)
      BhZero(@Ta[0], 599)
      BhZero(@Tb[0], 599)
      BnDecodeReduce(@Xa[0], b0, n0, mp)
      BnModpow(@Xa[0], b1, n1, mp, ModM0i[a0], @Ta[0], @Tb[0])
      BnEncode(o, outlen, @Xa[0])

    ElseIf op = 12
      ; MODPOW2 - the windowed exponentiation; s0 is its 1/0 verdict.
      mp = ModPtr(a0)
      BhZero(@Xa[0], 599)
      BhZero(@Tmp[0], 4095)
      BnDecodeReduce(@Xa[0], b0, n0, mp)
      s0 = BnModpow2(@Xa[0], b1, n1, mp, ModM0i[a0], @Tmp[0], 4096)
      BnEncode(o, outlen, @Xa[0])

    ElseIf op = 13
      ; MULACC - plain d = a*b, with d cleared first.
      BhZero(@Aa[0], 599)
      BhZero(@Ba[0], 599)
      BnDecode(@Aa[0], b0, n0)
      BnDecode(@Ba[0], b1, n1)
      alen = (BnGw(@Aa[0], 0) + 15) >> 4
      blen = (BnGw(@Ba[0], 0) + 15) >> 4
      BhZero(@Da[0], alen + blen + 2)
      BnMulAcc(@Da[0], @Aa[0], @Ba[0])
      BnEncode(o, outlen, @Da[0])

    ElseIf op = 14
      ; WORDS - the branchless comparison helpers at FULL 32-BIT WIDTH,
      ; which nothing in the shared vector set reaches.  a0 and a1 are
      ; read with PeekN, so they arrive as 0..$FFFFFFFF unsigned.
      s0 = BnEq(a0, a1)
      s0 = s0 | (BnNeq(a0, a1) << 1)
      s0 = s0 | (BnGt(a0, a1) << 2)
      s0 = s0 | (BnGe(a0, a1) << 3)
      s0 = s0 | (BnLt(a0, a1) << 4)
      s0 = s0 | (BnLe(a0, a1) << 5)
      s0 = s0 | (BnNot(BnEq(a0, a1)) << 6)
      s1 = BnBitLen32(a0) | (BnMux(BnGt(a0, a1), a0, a1) << 8)
    EndIf

    PokeI(q, s0)
    PokeI(q + 8, s1)
    PokeI(q + 16, outlen)
    PokeI(q + 24, 0)

    p = p + 28 + n0 + n1
    p = ((p + 3) / 4) * 4
    q = q + 32
    o = o + (((outlen + 3) / 4) * 4)
  ForEver

  UartWriteStr("bnharness done")
  ProcedureReturn 0
EndProcedure
'''


# =====================================================================
#  THE VECTOR SET, IMPORTED FROM THE GENERATOR THE PICO GATES USE
# =====================================================================
def load_tables():
    """Import the case tables out of tools/gen_bignum_vectors.py."""
    gen_path = ROOT / "tools" / "gen_bignum_vectors.py"
    if not gen_path.exists():
        raise SystemExit(
            "the vector tables are missing: %s\n"
            "This gate deliberately has no vectors of its own - it reads\n"
            "the same tables that emit bignumVectors.pico2 for the Pico\n"
            "gates." % gen_path)
    spec = importlib.util.spec_from_file_location("gen_bignum_vectors",
                                                  gen_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for name in ("MODS", "roundtrip", "iszero", "bitlen", "rshift", "add",
                 "sub", "reduce", "montmul", "modpow", "modpow2",
                 "mod_bytes", "bytelen", "be"):
        if not hasattr(mod, name):
            raise SystemExit(
                "gen_bignum_vectors.py no longer defines %r; this gate "
                "reads its tables BY NAME and must be updated WITH it, "
                "not around it" % name)
    return mod


class Script:
    """The job list, in the order the harness will walk it."""

    def __init__(self):
        self.buf = bytearray()
        self.jobs = []            # (label, op, expected_scalars, expected_bytes)
        self.records = []         # the raw script bytes, per job, for sharding
        self.out_off = []
        self._o = 0

    def add(self, op, label, a0=0, a1=0, b0=b"", b1=b"",
            out=None, scalars=None):
        outlen = 0 if out is None else len(out)
        rec = struct.pack("<IIIIIII", op, a0 & 0xFFFFFFFF, a1 & 0xFFFFFFFF,
                          len(b0), len(b1), outlen, 0)
        rec += b0 + b1
        rec += b"\x00" * ((-len(rec)) % 4)
        self._append(rec, label, op, scalars, out)

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


# =====================================================================
#  THE DERIVED MODULUS, AND THE SWEEP THAT FORCED IT
# =====================================================================
#  Added 2026-09-05 after --mutate went RED and --mutation-full confirmed
#  it: M22 - BnMontmul skips its FINAL CONDITIONAL SUBTRACTION, a real
#  correctness bug - survived all 148 jobs of the complete shared set.
#
#  THE REASON IS ARITHMETIC AND IT IS WORTH WRITING DOWN.  Every modulus
#  in the shared table is 256, 2048 or 3072 bits, and the i15 announced
#  length rounds each of them UP to a whole number of 15-bit words: a
#  256-bit modulus is carried in 18 limbs, so R = 2^270 and R is about
#  2^14 TIMES the modulus.  The Montgomery loop's value before the final
#  correction is bounded by m + a*b/R < m + m*(m/R), so it exceeds m only
#  about once in 2^14 multiplies.  The whole shared set runs on the order
#  of ten thousand of them, so whether it catches a missing correction is
#  a coin toss - and it lost.  That is not a subset that was cut too
#  small; it is a vector set whose moduli never fill their words.
#
#  ONE DERIVED MODULUS FIXES BOTH HALVES OF THAT.  2^270 - 3 is odd, is
#  exactly 18 limbs, and has SEVENTEEN OF ITS EIGHTEEN LIMBS AT $7FFF:
#    * R/m = 1.0, so the final correction fires on 22% of random
#      multiplies instead of one in sixteen thousand - and the derived
#      (m-1)^2 case below was CHECKED to need it, so M22 dies by
#      construction rather than by luck;
#    * every limb is maximal, which is the hardest input BnMulAddSmall's
#      carry chain and BnMontmul's inner carry can be given.
#
#  It is DERIVED, not transcribed: the value, its announced length and
#  its m0i are all computed here by the same three lines modload_jobs
#  uses for the shared four, and every expectation below is ordinary
#  Python integer arithmetic, which is what the generator uses for its
#  own mulacc expectations.
DERIVED_MOD = (1 << 270) - 3


def modload_jobs(g, s):
    """The four shared moduli plus the derived one, loaded into their
    slots and checked as they go."""
    for i, n in enumerate(list(g.MODS) + [DERIVED_MOD]):
        bl = g.bytelen(n)
        # The announced length and m0i are both derivable here, so they
        # are checked rather than merely installed: a wrong BnNinv15
        # would otherwise show up only as every montmul being wrong.
        words = (n.bit_length() + 14) // 15
        top = (n >> (15 * (words - 1)))
        enc = ((words - 1) << 4) + top.bit_length()
        m0i = (-pow(n & 0x7FFF, -1, 1 << 15)) % (1 << 15)
        s.add(OP_MODLOAD, "modulus %d (%d bits%s)"
              % (i, n.bit_length(),
                 ", DERIVED - every limb full" if n is DERIVED_MOD else ""),
              a0=i, b0=g.be(n, bl), scalars=(enc, m0i))


def derived_jobs(g, s):
    """The cases the 2026-09-05 sweep proved were missing.

    In EVERY level, including the mutant subset: they are 270-bit, so
    they cost about what the 256-bit cases cost, and they are the only
    jobs in the gate that reach BnMontmul's final conditional
    subtraction with any regularity.
    """
    n = DERIVED_MOD
    mi = len(g.MODS)
    mb = g.mod_bytes(n)

    # (m-1)^2 THROUGH THE MONTGOMERY MULTIPLY.  This exact pair was
    # checked to leave the loop's value at or above m, so the final
    # conditional subtraction MUST fire - which is what makes M22 a kill
    # instead of a coin toss.  The expectation is the generator's own
    # convention for this op: the plain product mod m.
    a = b = n - 1
    s.add(OP_MONTMUL, "montmul DERIVED (m-1)^2 mod the full-limb modulus "
                      "- needs BnMontmul's final conditional subtraction",
          a0=mi, b0=g.be(a, g.bytelen(a)), b1=g.be(b, g.bytelen(b)),
          out=g.be((a * b) % n, mb))

    # A second, ordinary pair on the same modulus, so the case above is
    # not the only thing holding the slot open.
    a2, b2 = (n - 1) // 3, (n - 2) // 5
    s.add(OP_MONTMUL, "montmul DERIVED (two ordinary operands, full-limb "
                      "modulus)",
          a0=mi, b0=g.be(a2, g.bytelen(a2)), b1=g.be(b2, g.bytelen(b2)),
          out=g.be((a2 * b2) % n, mb))

    # (m-1)^2 THROUGH BnReduce, which is the path BnMulAddSmall is on.
    # Maximal limbs on both sides is the hardest input its carry chain
    # can be given.
    x = (n - 1) * (n - 1)
    s.add(OP_REDUCE, "reduce DERIVED (m-1)^2 mod the full-limb modulus",
          a0=mi, b0=g.be(x, g.bytelen(x)), out=g.be(x % n, mb))
    s.add(OP_DECRED, "decodereduce DERIVED (m-1)^2 mod the full-limb "
                     "modulus",
          a0=mi, b0=g.be(x, g.bytelen(x)), out=g.be(x % n, mb))


def build_script(g, subset=False, level=None):
    """level: None/"full", "quick" (every third), "mutant" (see below)."""
    level = level or ("quick" if subset else "full")
    s = Script()
    modload_jobs(g, s)

    # THE MUTANT SUBSET IS A TIME DECISION WITH ONE HARD REQUIREMENT:
    # it must still reach every branch a mutation can be planted in.
    # It keeps every CHEAP case in full (they cost nothing) and drops
    # only the 2048- and 3072-bit modular work, which is where all the
    # model instructions are and none of the extra coverage: the same
    # code runs at 256 bits.  Two things were checked before dropping
    # them - BnMontmul's inner carry does exceed 16 bits at 18 limbs,
    # and BnModpow2 still picks a 5-bit window at 256 bits - because a
    # subset that quietly stops reaching a line is how a mutation
    # survives for the wrong reason.
    mutant = (level == "mutant")
    step = 3 if level == "quick" else 1

    # ---------------------------------------------------------------
    #  THE MUTANT SUBSET PICKS THE EXTREME CASES, NOT THE FIRST ONES,
    #  AND THE FIRST VERSION OF IT DID THE OPPOSITE.
    # ---------------------------------------------------------------
    #  It used to keep "the first N cases of modulus 0", which are the
    #  RANDOM ones, and drop the edges - (m-1)^2, a = m, a = m-1, base 0,
    #  base 1.  SIX MUTATIONS SURVIVED IT: the two 17-bit carries
    #  (BnMontmul, BnMulAddSmall), BnMontmul's final conditional
    #  subtraction, BnReduce's top-word clear, and two others.  None of
    #  them was a hole in the LIBRARY; every one was a case the subset
    #  had dropped.  A carry only reaches 2^16 when the limbs are near
    #  $7FFF, and random operands rarely are - the P-256 prime and m-1
    #  always are.
    #
    #  This is the same lesson the A64 GCM sweep learned when a subset of
    #  every sixth vector turned out to be all empty-plaintext cases.
    #  The selection is therefore BY INDEX and by intent:
    #
    #    reduce   ALL FOUR of modulus 0 - a >> m, a = m, a = m+1, a = m-1.
    #             Cheap, and they are the whole point.
    #    montmul  ALL SEVEN of modulus 0 - four random, a zero operand, a
    #             one operand, and (m-1)^2, which maximises every limb and
    #             is what drives the inner carry past 16 bits.  About a
    #             million model instructions each.
    #    modpow   index 0 (a random 256-bit exponent, the full ladder),
    #             index 4 (base 0, which exercises BnCcopy from zero) and
    #             index 6 ((m-1)^2 with the one-byte exponent 2, an edge
    #             that costs almost nothing).  The other 256-bit-exponent
    #             cases are 26 million instructions each and reach no
    #             line these do not.
    #    modpow2  index 0.
    # ---------------------------------------------------------------
    MUTANT_PICK = {"reduce": None, "montmul": None,
                   "modpow": (0, 4, 6), "modpow2": (0,)}
    seen = {}

    def keep(kind, mi):
        if not mutant:
            return True
        if mi != 0:
            return False
        n = seen.get(kind, 0)
        seen[kind] = n + 1
        pick = MUTANT_PICK[kind]
        return True if pick is None else (n in pick)

    for i, b in enumerate(g.roundtrip[::step]):
        s.add(OP_ROUNDTRIP, "roundtrip %d (%d bytes)" % (i, len(b)),
              b0=b, out=b)

    for i, (b, ex) in enumerate(g.iszero[::step]):
        s.add(OP_ISZERO, "iszero %d" % i, b0=b, scalars=(ex, None))

    for i, (b, ex) in enumerate(g.bitlen[::step]):
        s.add(OP_BITLEN, "bitlen %d" % i, b0=b, scalars=(ex, None))

    for i, (b, c, r) in enumerate(g.rshift[::step]):
        s.add(OP_RSHIFT, "rshift %d by %d" % (i, c), a0=c, b0=b, out=r)

    for i, (W, nb, a, b, r, carry) in enumerate(g.add[::step]):
        s.add(OP_ADD, "add %d (%d limbs)" % (i, W), a0=W, b0=a, b1=b,
              out=r, scalars=(carry, None))

    for i, (W, nb, a, b, r, borrow) in enumerate(g.sub[::step]):
        s.add(OP_SUB, "sub %d (%d limbs)" % (i, W), a0=W, b0=a, b1=b,
              out=r, scalars=(borrow, None))

    for i, (mi, a, mb, r) in enumerate(g.reduce[::step]):
        if not keep("reduce", mi):
            continue
        s.add(OP_REDUCE, "reduce %d (mod %d)" % (i, mi), a0=mi, b0=a, out=r)
        s.add(OP_DECRED, "decodereduce %d (mod %d)" % (i, mi), a0=mi,
              b0=a, out=r)

    for i, (mi, a, b, mb, r) in enumerate(g.montmul[::step]):
        if not keep("montmul", mi):
            continue
        s.add(OP_MONTMUL, "montmul %d (mod %d)" % (i, mi), a0=mi,
              b0=a, b1=b, out=r)
        # THE SAME OPERANDS THROUGH THE PLAIN MULTIPLY.  BnMulAcc has no
        # case in the shared table; here it gets one for free, with a
        # Python product as the expectation.
        av = int.from_bytes(a, "big")
        bv = int.from_bytes(b, "big")
        pv = av * bv
        pl = max(1, (pv.bit_length() + 7) // 8)
        s.add(OP_MULACC, "mulacc %d (%d x %d bits)"
              % (i, av.bit_length(), bv.bit_length()),
              b0=a, b1=b, out=g.be(pv, pl))

    for i, (mi, base, e, mb, r) in enumerate(g.modpow[::step]):
        if not keep("modpow", mi):
            continue
        s.add(OP_MODPOW, "modpow %d (mod %d, %d-bit exponent)"
              % (i, mi, int.from_bytes(e, "big").bit_length()),
              a0=mi, b0=base, b1=e, out=r)

    for i, (mi, base, e, mb, r) in enumerate(g.modpow2[::step]):
        if not keep("modpow2", mi):
            continue
        s.add(OP_MODPOW2, "modpow2 %d (mod %d)" % (i, mi), a0=mi,
              b0=base, b1=e, out=r, scalars=(1, None))

    derived_jobs(g, s)
    add_word_jobs(s)
    return s


WORD_PAIRS = [
    (0, 0), (0, 1), (1, 0), (1, 1), (7, 7),
    (0x7FFF, 0x8000), (0x8000, 0x7FFF),
    (0x7FFFFFFF, 0x80000000), (0x80000000, 0x7FFFFFFF),
    (0xFFFFFFFF, 0), (0, 0xFFFFFFFF), (0xFFFFFFFF, 0xFFFFFFFF),
    (0xFFFFFFFF, 0xFFFFFFFE), (0xFFFFFFFE, 0xFFFFFFFF),
    (0x80000000, 0x80000000), (0x00010000, 0x0000FFFF),
    (0xFFFF, 0x10000), (0x12345678, 0x87654321),
    (0x87654321, 0x12345678), (0xF, 0x10), (0x10, 0xF), (3, 2), (2, 3),
]


def add_word_jobs(s):
    """The branchless helpers across the whole 32-bit range.

    THE SHARED VECTOR SET CANNOT REACH THIS.  Every operand it hands
    BnGt is a 15-bit limb, so the rewrite that lets a 64-bit register
    do the unsigned compare exactly would have been untested by it -
    and so would the `>> 63` sign tests, whose 32-bit spellings survive
    small operands and stop surviving large ones.
    """
    for x, y in WORD_PAIRS:
        eq = 1 if x == y else 0
        gt = 1 if x > y else 0
        flags = (eq | ((1 - eq) << 1) | (gt << 2)
                 | ((1 if x >= y else 0) << 3)
                 | ((1 if x < y else 0) << 4)
                 | ((1 if x <= y else 0) << 5)
                 | ((1 - eq) << 6))
        s1 = x.bit_length() | ((x if gt else y) << 8)
        s.add(OP_WORDS, "words %08x vs %08x" % (x, y), a0=x, a1=y,
              scalars=(flags, s1))


# =====================================================================
#  BUILD AND RUN
# =====================================================================
def build(bignum_include, harness, img):
    WORK.mkdir(exist_ok=True)
    src = HARNESS.replace("__BIGNUM__", bignum_include)
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

    if b"bnharness done" not in uart:
        raise SystemExit("the harness returned without finishing its "
                         "script:\n" + uart.decode("latin-1"))

    recs = [bytes(mem.get(H_RESULT + i * RESULT_STRIDE + j, 0)
                  for j in range(RESULT_STRIDE))
            for i in range(count)]
    out = bytes(mem.get(H_OUT + i, 0) for i in range(out_bytes))
    return recs, out, steps


def check_shard(script, recs, out, base_job, base_out):
    bad = []
    for i, (label, op, scalars, expect) in enumerate(script.jobs):
        rec = recs[i]
        s0, s1, outlen, _ = struct.unpack("<QQQQ", rec)
        if rec == bytes([SENTINEL]) * RESULT_STRIDE:
            bad.append("%s: no record was written at all" % label)
            continue
        if scalars is not None:
            e0, e1 = scalars
            if e0 is not None and s0 != e0:
                bad.append("%s: scalar0 is %d (%016x at full width), want %d"
                           % (label, s0, s0, e0))
            if e1 is not None and s1 != e1:
                bad.append("%s: scalar1 is %d (%016x at full width), want %d"
                           % (label, s1, s1, e1))
        if expect is not None:
            off = script.out_off[i]
            got = out[off:off + len(expect)]
            if got != expect:
                bad.append("%s: %d bytes differ\n    want %s\n    got  %s"
                           % (label, len(expect), expect.hex(), got.hex()))
    return bad


def shard(script, n):
    """Split a Script into n Scripts, keeping every job's expectations.

    THE MODULI GO IN EVERY SHARD.  They are state the later jobs read,
    so a shard that did not load them would not be a smaller run of the
    same thing - it would be a different program.
    """
    head = [j for j in script.jobs if j[1] == OP_MODLOAD]
    nhead = len(head)
    body = list(range(nhead, len(script.jobs)))
    if n <= 1 or not body:
        return [script]

    # Interleave rather than block, so the expensive 3072-bit jobs are
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
#    "timing"   the answers stay right and --timing must catch it.
#    a string   an EXPECTED survivor, and the string is the argument for
#               why no known-answer test can see it.  These are NOT
#               deleted: the day one of them starts being caught is the
#               day its argument stopped being true, and that is as loud
#               a failure as an unexpected survivor.
#
#  "harness" as the file mutates the GENERATED harness instead of the
#  library, which is the only way to test a claim this module's header
#  makes about its CALLERS.
# =====================================================================
MUTATIONS = [
    ("M1  a caller declares a bignum buffer .i instead of .u", "harness",
     "Global Dim Xa.u[600]",
     "Global Dim Xa.i[600]",
     "kill"),

    ("M2  BnGt reverts to reading bit 31 of the exact difference",
     "bignum",
     "  ProcedureReturn ((((y & #BN_W32) - (x & #BN_W32)) >> 63) & 1)",
     "  ProcedureReturn ((((y & #BN_W32) - (x & #BN_W32)) >> 31) & 1)",
     "kill"),

    ("M3  BnGt reverts to the 32-bit three-XOR borrow reconstruction",
     "bignum",
     "  ProcedureReturn ((((y & #BN_W32) - (x & #BN_W32)) >> 63) & 1)",
     "  Protected z.i\n  z = y - x\n  z = z ! ((x ! y) & (x ! z))\n"
     "  ProcedureReturn (z >> 31) & 1",
     "THE 32-BIT COMPARE IS CORRECT HERE, and the sweep is what "
     "established that - it was written as a 'kill' and survived. The "
     "construction reads ONE BIT: bit 31 of z. Addition, subtraction "
     "and XOR all agree with their mod-2^32 results in bits 0..31 "
     "whatever width they were computed at, so bit 31 of the EXACT "
     "64-bit difference IS bit 31 of the wrapped 32-bit one, and the "
     "whole dance still lands on the right answer for any operands "
     "under 2^32. BnGt was rewritten for the WIDER register anyway - "
     "fewer operations, and it stops depending on an operand bound "
     "that nothing enforces - but this table must not claim it fixed "
     "a bug it did not fix. Compare M2, which reads bit 31 of the "
     "MASKED difference and IS caught, because masking to 32 bits "
     "first destroys the borrow bit 31 was standing in for."),

    ("M4  BnEq / BnNeq revert to shifting 31", "bignum",
     "  q = (q | (0 - q)) >> 63\n  ProcedureReturn (q & 1) ! 1",
     "  q = (q | (0 - q)) >> 31\n  ProcedureReturn (q & 1) ! 1",
     "THE 32-BIT SPELLING SURVIVES FOR EVERY OPERAND THIS CORE PRODUCES, "
     "and that is worth knowing rather than assuming. For 0 < q < 2^32, "
     "q | -q has bit 31 set whichever half q lives in, so `>> 31 & 1` "
     "still reads 1. It stops being true for a q above 2^32, which "
     "nothing here has - but nothing ENFORCES that, and the two "
     "spellings look identical to a reviewer. Written at 63 because the "
     "sign bit IS 63; kept in this table because it is honest to say "
     "the vectors cannot tell."),

    ("M5  BnIsZero reverts to the 32-bit complement-and-shift", "bignum",
     "  q = z | (0 - z)\n  ProcedureReturn (((q >> 63) & 1) ! 1)",
     "  q = z | (0 - z)\n  q = q ! $FFFFFFFF\n"
     "  ProcedureReturn (q >> 31) & 1",
     "SAME ARGUMENT AS M4, and it was written into this file's header "
     "the other way round before the sweep was run - the header claimed "
     "this one does NOT survive. It does: the 32-bit complement leaves "
     "bits 32..63 set, the value stays negative, and `>> 31 & 1` still "
     "reads bit 31, which the complement cleared. Two wrongs. The claim "
     "was corrected from this run, which is the whole reason the table "
     "records an expected verdict per mutation."),

    ("M6  BnMulAcc reverts to the 32-bit complement for dl >= 15",
     "bignum",
     "  BnSw(d, 0, (dh << 4) + dl + BnGe(dl, 15))",
     "  BnSw(d, 0, (dh << 4) + dl + ((((dl - 15) ! $FFFFFFFF) >> 31) & 1))",
     "SAME FAMILY AS M4 AND M5. dl is 0..30, so dl - 15 is a small "
     "signed value; XOR-ing it with a 32-bit all-ones flips bit 31 but "
     "not bits 32..63, and the arithmetic `>> 31` still delivers bit 31 "
     "to bit 0. Correct by accident, on operands that happen to be "
     "small. BnGe says the same thing without the accident."),

    ("M7  BnNinv15 drops the per-step 32-bit mask", "bignum",
     "  y = (y * (2 - x * y)) & #BN_W32\n"
     "  y = (y * (2 - x * y)) & #BN_W32\n"
     "  y = (y * (2 - x * y)) & #BN_W32",
     "  y = y * (2 - x * y)\n  y = y * (2 - x * y)\n"
     "  y = y * (2 - x * y)",
     "REVIEWABILITY, NOT CORRECTNESS - and the reason is the whole point "
     "of a 2-adic Newton iteration. Every step is +, - and *, all of "
     "which agree with the 32-bit computation in their low bits, and "
     "only the low 15 bits are ever read. Unmasked the iterates reach "
     "about 2^105 and wrap mod 2^64 instead of mod 2^32; masked they are "
     "the SAME NUMBERS the three 32-bit copies compute, which is what "
     "makes the two files comparable line by line."),

    ("M8  BnNinv15 does one Newton step fewer", "bignum",
     "  y = (y * (2 - x * y)) & #BN_W32\n"
     "  y = (y * (2 - x * y)) & #BN_W32\n"
     "  y = (y * (2 - x * y)) & #BN_W32",
     "  y = (y * (2 - x * y)) & #BN_W32\n"
     "  y = (y * (2 - x * y)) & #BN_W32",
     "kill"),

    ("M9  BnSub's borrow reverts to shifting 31", "bignum",
     "    naw = aw - bw - cc\n    cc = (naw >> 63) & 1",
     "    naw = aw - bw - cc\n    cc = (naw >> 31) & 1",
     "SAME ARGUMENT AS M4. naw is in -(2^15+1)..2^15-1, so an arithmetic "
     "`>> 31` of a negative naw is still all-ones and `& 1` still reads "
     "1. The claim it rests on - that naw can never be large - is true "
     "and unenforced."),

    ("M10 BnSub stores the raw difference, unmasked", "bignum",
     "    cc = (naw >> 63) & 1\n    BnSw(a, u, BnMux(ctl, naw & $7FFF, aw))",
     "    cc = (naw >> 63) & 1\n    BnSw(a, u, BnMux(ctl, naw, aw))",
     "kill"),

    ("M11 BnAdd stores the raw sum, unmasked", "bignum",
     "    cc = (naw >> 15) & 1\n    BnSw(a, u, BnMux(ctl, naw & $7FFF, aw))",
     "    cc = (naw >> 15) & 1\n    BnSw(a, u, BnMux(ctl, naw, aw))",
     "kill"),

    ("M12 BnMontmul's inner carry keeps 16 bits instead of 17", "bignum",
     "      r = (z >> 15) & $1FFFF",
     "      r = (z >> 15) & $FFFF",
     "THE SEVENTEENTH BIT IS NEVER SET, AND THAT IS ARITHMETIC RATHER "
     "THAN AN OBSERVATION - this mutation is a no-op and could not die "
     "however many vectors it were shown. The inner line is "
     "z = d[v] + xu*y[v] + f*m[v] + r with every limb at most $7FFF, so "
     "z <= 32767 + 2*32767^2 + r = 2147385345 + r, and r = z >> 15 has "
     "the fixed point r = 65535 EXACTLY: 2147385345 + 65535 = 2147450880 "
     "and 2147450880 >> 15 = 65535. The carry tops out at $FFFF, so "
     "`& $FFFF` is bit-for-bit identical to `& $1FFFF`. The wider mask "
     "is REVIEWABILITY, the same case gcm.pi4 makes for GhLsl's. The "
     "same bound is also what makes i15 work on a 32-bit `.i` at all: "
     "2147450880 is just under 2^31, so z never goes negative there "
     "either. ESTABLISHED BY --mutation-full 2026-09-05 - written as a "
     "'kill', survived the mutant subset, then survived --mutation-full "
     "against all 148 jobs of the complete set. The subset was not the "
     "problem; the verdict was."),

    ("M13 BnMulAddSmall's multiply-subtract carry keeps 15 bits", "bignum",
     "    cc = (zl >> 15) & $1FFFF\n    zl = zl & $7FFF",
     "    cc = (zl >> 15) & $7FFF\n    zl = zl & $7FFF",
     "A SURVIVOR WITH AN HONEST ARGUMENT AND AN OPEN QUESTION - NOT a "
     "proof of safety like M12's, and the difference is recorded because "
     "it matters. THE MASK IS LOAD-BEARING IN PRINCIPLE: cc = "
     "((mw*q + cc) >> 15) + borrow, with mw and q at most $7FFF, has the "
     "fixed point 32768 - ONE MORE than 15 bits hold - so unlike M12 "
     "this narrowing is not arithmetically dead. WHAT IT WOULD TAKE: cc "
     "= 32768 needs (mw*q + cc) >> 15 to be exactly 32767 together with "
     "a borrow, and since the largest product 32767^2 = 1073676289 is "
     "32766*32768 + 1, that needs cc to ALREADY be 32767 with mw = q = "
     "$7FFF - two consecutive steps pinned at the exact maximum. WHAT "
     "WAS TRIED, 2026-09-05: it survived the mutant subset; then "
     "--mutation-full against all 148 jobs of the complete shared set; "
     "then the DERIVED full-limb modulus 2^270 - 3, seventeen of whose "
     "eighteen limbs are $7FFF, reducing (m-1)^2 - the hardest input "
     "this gate can build. q is bounded by the remainder state rather "
     "than by the limb size and does not sit at $7FFF across consecutive "
     "limbs in any of them. SO: the mask stays, it is defensive rather "
     "than demonstrably dead, and whether any REACHABLE state drives cc "
     "to 32768 is an OPEN QUESTION. Do not quietly downgrade this to "
     "M12's argument - that one is a proof and this one is not."),

    ("M14 BnDecode loses a bit out of the accumulator", "bignum",
     "      acc = (acc >> 15) & $FFFF",
     "      acc = (acc >> 15) & $7FFF",
     "THE MASK IS DEAD CODE, ON BOTH WIDTHS, and the sweep found it "
     "by surviving a mutation written as a 'kill'. In BnDecode "
     "acc_len is under 15 before each byte is folded in, so acc is "
     "under 2^22 and acc >> 15 is at most 127 - $FFFF, $7FFF and no "
     "mask at all are the same three things. That is a fact about "
     "the accumulator's range, not about 64 bits; the 32-bit copies "
     "carry the same dead mask. Kept, because deleting it would make "
     "the four copies differ for no reason - and recorded here so "
     "nobody spends an afternoon working out why it cannot be "
     "killed."),

    ("M15 BnEncode's accumulator keeps 16 bits instead of 24", "bignum",
     "    acc = (acc >> 8) & $FFFFFF",
     "    acc = (acc >> 8) & $FFFF",
     "THE MASK IS DEAD CODE, the same shape as M14. BnEncode folds "
     "in a limb only while acc_len is under 8, so acc is at most "
     "2^22 + 2^15 and acc >> 8 is under 2^15 - both masks are "
     "no-ops. Established by this mutation surviving, not by reading "
     "the code."),

    ("M16 BnRshift drops the top word", "bignum",
     "  BnSw(x, len, r)\nEndProcedure",
     "EndProcedure",
     "kill"),

    ("M17 BnCcopy's mask is the control bit, not its negation", "bignum",
     "  mask = 0 - ctl",
     "  mask = ctl",
     "kill"),

    ("M18 BnModpow reads two exponent bits at a time", "bignum",
     "    ctl = (byte >> (k & 7)) & 1",
     "    ctl = (byte >> (k & 7)) & 3",
     "kill"),

    ("M19 BnDivrem16 drops the mask on the divisor's right shift",
     "bignum",
     "    d = (d >> 1) & $7FFFFFFF",
     "    d = (d >> 1)",
     "UNREACHABLE ON THIS WIDTH, AND LOAD-BEARING ON THE OTHER. On a "
     "32-bit `.i` the shifted divisor has bit 31 set, `>>` is "
     "arithmetic, and without the mask the sign smears down - so the "
     "32-bit copies need it. Here d is at most $FFFF0000 held in a "
     "64-bit register, which is positive, so the shift is already "
     "logical and the mask is a no-op. Kept so the two files read the "
     "same way, and recorded here so nobody deletes it from the copy "
     "where it matters."),

    ("M20 BnModpow2's window table selection loses its mask", "bignum",
     "        mask = 0 - BnEq(u, bits)",
     "        mask = 0 - BnNeq(u, bits)",
     "kill"),

    ("M21 BnReduce forgets to clear the top word", "bignum",
     "  BnSw(x, mlen, 0)\n  u = 1 + alen - mlen",
     "  u = 1 + alen - mlen",
     "kill"),

    ("M22 BnMontmul skips the final conditional subtraction", "bignum",
     "  BnSub(d, m, BnNeq(dh, 0) | (c0 ! 1))",
     "  BnSub(d, m, 0)",
     "kill"),

    ("M23 BnBitLen32 loses the mask on its 16-bit fold", "bignum",
     "  x = BnMux(c, (x >> 16) & $FFFF, x)",
     "  x = BnMux(c, x >> 16, x)",
     "the operand is already masked to 32 bits by every caller in this "
     "core and `>>` of a non-negative value cannot produce bits above "
     "31, so the mask is defensive. THE WORDS JOBS FEED IT $FFFFFFFF "
     "DIRECTLY, so if this ever starts being caught the argument has "
     "changed and the line was doing real work."),

    ("M24 BnMulAddSmall's 'q was zero' correction shifts 31", "bignum",
     "  q = BnMux(BnEq(b, aHi), $7FFF, q - 1 + (((q - 1) >> 63) & 1))",
     "  q = BnMux(BnEq(b, aHi), $7FFF, q - 1 + (((q - 1) >> 31) & 1))",
     "SAME ARGUMENT AS M4: q - 1 is -1 at worst, and an arithmetic "
     "`>> 31` of -1 is still -1."),

    ("M25 BnMulAddSmall's multiply-subtract borrow shifts 31", "bignum",
     "    nxw = xw - zl\n    cc = cc + ((nxw >> 63) & 1)",
     "    nxw = xw - zl\n    cc = cc + ((nxw >> 31) & 1)",
     "SAME ARGUMENT AS M4: nxw is in -(2^15-1)..2^15-1."),

    ("M26 BnMoveUp copies bottom-up over the overlap", "bignum",
     "  u = mlen\n  While u >= 2\n    BnSw(x, u, BnGw(x, u - 1))\n"
     "    u = u - 1\n  Wend",
     "  u = 2\n  While u <= mlen\n    BnSw(x, u, BnGw(x, u - 1))\n"
     "    u = u + 1\n  Wend",
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
        return "RaspberryPi4/Lib/bignum.pi4", harness_text.replace(
            find, replace, 1)
    text = BIGNUM.read_text(encoding="utf-8")
    if text.count(find) != 1:
        raise SystemExit("mutation anchor found %d times in %s (want 1):\n%r"
                         % (text.count(find), BIGNUM.name, find))
    out = WORK / ("mut%02d_%s" % (idx, BIGNUM.name))
    out.write_text(text.replace(find, replace, 1), encoding="utf-8")
    return "_work/" + out.name, harness_text


def build_mutant(idx, include, harness_text, img):
    WORK.mkdir(exist_ok=True)
    src = harness_text.replace("__BIGNUM__", include)
    hp = WORK / ("bnharness_mut%02d.pi4" % idx)
    hp.write_text(src, encoding="utf-8")
    cmd = [str(PMFC), "--compile", str(hp), "-t", "pi4",
           "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
           "--entry-returns", "-o", str(img)]
    r = subprocess.run(cmd, cwd=ROOT, env=BUILD_ENV, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout:
        raise SystemExit("build failed:\n" + r.stdout)
    return img.stat().st_size


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
        return check_shard(shards[0], recs, out, 0, 0), steps

    if not quiet:
        print("[gate] %d jobs across %d workers" % (len(script), len(shards)),
              file=sys.stderr)
    args = [(img_bytes, s.done(), len(s), s._o) for s in shards]
    bad = []
    steps = 0
    with concurrent.futures.ProcessPoolExecutor(max_workers=len(shards)) as ex:
        for s, (recs, out, st) in zip(shards, ex.map(_worker, args)):
            bad += check_shard(s, recs, out, 0, 0)
            steps += st
    return bad, steps


# =====================================================================
#  THE CONSTANT-TIME CHECK
# =====================================================================
def timing(img, quiet=False):
    """A/B instruction counts at equal lengths and different content.

    THE LENGTHS ARE THE SAME AND EVERYTHING ELSE IS AS DIFFERENT AS IT
    CAN BE.  The exponent is the secret in an RSA or an ECDSA private
    operation, so the cases below hold the modulus and every length
    fixed and vary the exponent from all-zero bits to all-one bits, and
    the base with it.  A difference in the count is a branch or an
    index that read a secret.
    """
    g = load_tables()
    m = g.MODS[0]
    mb = g.mod_bytes(m)
    bl = g.bytelen(m)

    # EVERY BASE IS ENCODED IN 32 BYTES, AND THE FIRST VERSION OF THIS
    # FUNCTION DID NOT DO THAT.  It wrote each base in its own minimal
    # byte length, so base 1 arrived as ONE byte and base m-1 as
    # thirty-two; BnDecodeReduce then walked a different number of bytes
    # and the counts split into two groups 28,952 instructions apart.
    # The gate was RED on a difference IT had introduced.  The reading
    # that mattered was already visible in the same table: within each
    # group all four EXPONENTS - the actual secret - cost exactly the
    # same, which is the property this check exists to test.  A
    # constant-time check whose own inputs differ in length is not a
    # constant-time check, and the failure looked exactly like a real
    # leak, so it is written down rather than quietly fixed.
    bases = [1, 2, m - 1, int.from_bytes(b"\x5a" * 32, "big") % m]
    exps = [b"\x00" * 32, b"\xff" * 32, b"\x01" + b"\x00" * 31,
            bytes(range(32))]

    # SIXTEEN INDEPENDENT RUNS, SO THEY GO ACROSS THE POOL.  Each is a
    # 256-bit modular exponentiation - about 26 million model
    # instructions - and sixteen of them in one process is a quarter of
    # a billion, which is the kind of serial gate that gets killed for
    # running for hours.  Nothing is shared between them.
    args = []
    labels = []
    for base in bases:
        for e in exps:
            s = Script()
            modload_jobs(g, s)
            s.add(OP_MODPOW, "ct", a0=0,
                  b0=g.be(base, 32), b1=e,
                  out=g.be(pow(base, int.from_bytes(e, "big"), m), mb))
            args.append((img.read_bytes(), s.done(), len(s), s._o))
            labels.append("base %-6s exponent %s"
                          % (("%d..." % (base % 1000)), e[:4].hex()))

    nw = max(1, min(len(args), JOBS_CAP or (os.cpu_count() or 2) - 2))
    if nw == 1:
        counts = [run_raw(*a)[2] for a in args]
    else:
        with concurrent.futures.ProcessPoolExecutor(max_workers=nw) as ex:
            counts = [r[2] for r in ex.map(_worker, args)]

    if len(set(counts)) != 1:
        if not quiet:
            print("FAIL: the model executed %s instructions for %d modular "
                  "exponentiations that differ only in the value of the "
                  "base and the exponent, at identical lengths"
                  % (counts, len(counts)))
            for lab, c in zip(labels, counts):
                print("        %-44s %d" % (lab, c))
            print("CT GATE RED")
        return 1
    if not quiet:
        print("CT GATE GREEN: %d instructions for all %d combinations of "
              "base and exponent at the same lengths"
              % (counts[0], len(counts)))
    return 0


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
    ap.add_argument("--quick", action="store_true",
                    help="every third vector of each kind")
    ap.add_argument("--timing", action="store_true",
                    help="also run the constant-time check")
    ap.add_argument("--mutate", action="store_true", help="the mutation sweep")
    ap.add_argument("--mutation", type=int, default=None,
                    help="run ONE mutation by index (used by the pool)")
    ap.add_argument("--mutation-full", action="store_true",
                    help="run --mutation against the FULL vector set rather "
                         "than the mutant subset. When a "
                         "mutation survives the subset, this says whether "
                         "the subset was too small or the mutation is "
                         "genuinely unreachable, and the answer goes into "
                         "the table as a measurement instead of an argument.")
    ap.add_argument("--jobs", type=int, default=None,
                    help="worker processes (default: cores - 2)")
    args = ap.parse_args(argv)
    globals()["PMFC"] = resolve_compiler(args.compiler)
    globals()["JOBS_CAP"] = args.jobs

    print("[gate] tree under test: %s" % ROOT, file=sys.stderr)

    g = load_tables()

    if args.mutation is not None:
        i = args.mutation
        label, which, find, repl, verdict = MUTATIONS[i]
        inc, harness_text = mutate_source(i, which, find, repl, HARNESS)
        img = WORK / ("bn_mut%02d.img" % i)
        try:
            build_mutant(i, inc, harness_text, img)
        except SystemExit as e:
            # A MUTANT THAT WILL NOT BUILD IS KILLED BY THE COMPILER, and
            # that is a legitimate kill - but it is a DIFFERENT verdict
            # from "the vectors caught it" and is printed as one.
            print("NOBUILD  %s\n         %s" % (label, str(e).splitlines()[0]))
            return 0
        s = build_script(g, level=("full" if args.mutation_full else "mutant"))
        bad, _ = run_all(img, s, jobs=args.jobs, quiet=True)

        if verdict == "timing":
            if bad:
                print("MISLABELLED %s\n         the vector set caught a "
                      "mutation marked 'timing'" % label)
                return 1
            if timing(img, quiet=True) != 0:
                print("KILLED   %s  (by the constant-time check)" % label)
                return 0
            print("SURVIVED %s\n         (a timing-only mutation the "
                  "constant-time check did not see)" % label)
            return 1

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
        expected = sum(1 for m in MUTATIONS if m[4] not in ("kill", "timing"))
        print("[gate] sweep took %.0f s" % (time.time() - t0))
        if survivors:
            print("MUTATION SWEEP RED: %d unexpected outcome(s):\n  %s"
                  % (len(survivors), "\n  ".join(survivors)))
            return 1
        print("MUTATION SWEEP GREEN: 0 unexpected outcomes of %d "
              "(%d of them are EXPECTED survivors, each with its recorded "
              "argument in the table)" % (len(MUTATIONS), expected))
        return 0

    s = build_script(g, subset=args.quick)
    img = WORK / "bnharness.img"
    size = build("RaspberryPi4/Lib/bignum.pi4", WORK / "bnharness.pi4", img)
    print("[gate] image %d bytes, %d jobs" % (size, len(s)))
    t0 = time.time()
    bad, steps = run_all(img, s, jobs=args.jobs)
    for b in bad:
        print("FAIL: " + b)
    print("[gate] %d jobs, %d model instructions, %.0f s"
          % (len(s), steps, time.time() - t0))
    if bad:
        print("BIGNUM GATE RED: %d of %d jobs wrong" % (len(bad), len(s)))
        return 1

    if args.timing:
        rc = timing(img)
        if rc:
            return rc

    print("BIGNUM GATE GREEN: %d jobs on the shared i15 vector set, "
          "%d model instructions" % (len(s), steps))
    return 0


if __name__ == "__main__":
    sys.exit(main())

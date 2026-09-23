#!/usr/bin/env python3
"""The third column of the Pi 4 floating-point differential gate.

WHAT THIS IS FOR

RaspberryPi4/Examples/Diagnostics/pi4FpGate.pi4 runs every binary32
operation twice on the board - once through the Cortex-A72's FPU and
once through the software core in RaspberryPi4/Lib/math.pi4 - and
requires the two to agree bit for bit.  Two implementations agreeing is
a strong statement.  Three is stronger, and it costs one printed line
per path, because the board cannot send tens of thousands of results
over a 115200 line in a sensible time.

So the board accumulates a rolling 64-bit hash of every result it
produced, in a fixed order, and prints two sixteen-digit numbers.  This
file reproduces the same vector order, the same pseudo-random sequence
and the same hash from a THIRD implementation written here, and prints
the two numbers it expects.  If they match, every result in the run was
right - not merely self-consistent.

WHY THE ORACLE HERE IS EXACT ARITHMETIC AND NOT PYTHON FLOATS

The obvious implementation computes in Python's binary64 and rounds the
answer to binary32.  For +, -, * and / that is provably correct, because
binary64 carries more than 2p+2 bits relative to binary32 and the double
rounding is therefore innocuous.  It is provably correct and it is an
ARGUMENT, and an argument is a thing that can be wrong - about
subnormals, about the overflow boundary, about a Python implementation
detail in struct.pack.

Fractions are not an argument.  Every binary32 value is an exact
rational; the sum, difference, product and quotient of two rationals are
exact rationals; and rounding an exact rational to binary32 with ties to
even is fifteen lines with no floating point anywhere in it.  It is
slower and it needs no reasoning to trust, which is the correct trade
for an oracle.

WHY TWO EXPECTED HASHES

The two paths on the board are NOT expected to produce identical result
streams, and pi4FpGate.pi4's header says exactly where they diverge:

  * NaN payloads.  With FPCR.DN clear the hardware propagates an input
    NaN's payload after quieting it; math.pi4 returns the default NaN
    $7FC00000 for any NaN input.
  * The negative rail of float -> int.  fcvtzs saturates at INT64_MIN;
    MathFToIntB saturates at INT64_MIN + 1.

So this file computes the IEEE-754 answer once and then derives two
streams from it: the hardware stream, which is the IEEE answer, and the
software stream, which is the IEEE answer with those two documented
deviations applied.  A run in which the hardware hash matches and the
software hash matches has confirmed BOTH implementations independently,
and has confirmed that the only differences between them are the two
that were predicted in writing before the run.

THE VECTORS ARE READ OUT OF THE .pi4 FILE, NOT COPIED

One source of truth.  If somebody adds a vector to the DataSection and
forgets this file, this file notices, because it parses the table and
cross-checks the count against the #FPGATE_VECTORS constant in the same
file.  A copied table would silently answer the old question.

Run: python tools/a64/a64_f32_gate.py
     python tools/a64/a64_f32_gate.py --self-test
"""

from __future__ import annotations
import os

import argparse
import pathlib
import re
import sys
from fractions import Fraction

# THE TREE UNDER TEST IS THE ONE THIS SCRIPT LIVES IN. A root pinned into
# the file made this gate build a DIFFERENT working copy, with that copy's
# compiler, and print the answer as this tree's. Override deliberately with
# PMF_REPO; the tree actually read is printed below so a wrong one is visible.
ROOT = pathlib.Path(os.environ.get("PMF_REPO")
            or pathlib.Path(__file__).resolve().parents[2])
print("[gate] tree under test: %s" % ROOT, file=sys.stderr)
GATE = ROOT / "RaspberryPi4" / "Examples" / "Diagnostics" / "pi4FpGate.pi4"

MASK32 = 0xFFFFFFFF
MASK64 = 0xFFFFFFFFFFFFFFFF

# binary32 shape.  Named rather than inlined so the rounder reads as the
# standard does.
P = 24                  # precision, including the implicit bit
E_MIN = -126            # exponent of the smallest normal
E_MAX = 127             # exponent of the largest normal
SUBNORMAL_SCALE = -149  # E_MIN - (P - 1): the exponent of the smallest subnormal
DEFAULT_NAN = 0x7FC00000
QUIET_BIT = 1 << 22


# ======================================================================
#  binary32, from first principles
# ======================================================================

def unpack(bits: int):
    """(sign, kind, exact_value) where kind is one of the four classes.

    exact_value is a Fraction for finite values and None otherwise, so a
    caller that forgets to handle infinity gets a TypeError rather than a
    plausible number.
    """
    bits &= MASK32
    sign = (bits >> 31) & 1
    exp = (bits >> 23) & 0xFF
    frac = bits & 0x7FFFFF
    if exp == 0xFF:
        if frac == 0:
            return sign, "inf", None
        return sign, ("snan" if (frac & QUIET_BIT) == 0 else "qnan"), None
    if exp == 0:
        if frac == 0:
            return sign, "zero", Fraction(0)
        return sign, "finite", Fraction(frac) * Fraction(1, 1 << 149)
    value = Fraction(frac + (1 << 23)) * Fraction(2) ** (exp - 127 - 23)
    return sign, "finite", value


def round_half_even(num: int, den: int) -> int:
    """Round the positive rational num/den to the nearest integer, ties to even."""
    q, rem = divmod(num, den)
    twice = 2 * rem
    if twice > den or (twice == den and (q & 1) == 1):
        q += 1
    return q


def pack(sign: int, value: Fraction) -> int:
    """Round an exact non-negative rational to binary32 and encode it.

    Round to nearest, ties to even, with correct gradual underflow and
    correct overflow to infinity.  No floating point is used.
    """
    if value == 0:
        return (sign << 31)

    # The exponent e with 2^e <= value < 2^(e+1).  The bit_length estimate
    # is off by at most one in either direction, so two while loops settle
    # it exactly and neither can run more than once.
    e = value.numerator.bit_length() - value.denominator.bit_length() - 1
    while Fraction(2) ** e > value:
        e -= 1
    while Fraction(2) ** (e + 1) <= value:
        e += 1

    scale_exp = e - (P - 1)
    if scale_exp < SUBNORMAL_SCALE:
        scale_exp = SUBNORMAL_SCALE

    scaled = value / (Fraction(2) ** scale_exp)
    q = round_half_even(scaled.numerator, scaled.denominator)

    # Rounding can carry out of the bucket, and only ever to exactly 2^P.
    if q == (1 << P):
        q >>= 1
        scale_exp += 1

    # Overflow: the largest finite is (2^24 - 1) * 2^(127-23).
    if scale_exp > E_MAX - (P - 1):
        return (sign << 31) | 0x7F800000

    if scale_exp == SUBNORMAL_SCALE and q < (1 << 23):
        return (sign << 31) | q             # subnormal, exponent field 0
    biased = scale_exp + (P - 1) + 127
    return (sign << 31) | (biased << 23) | (q - (1 << 23))


def is_nan(bits: int) -> bool:
    bits &= MASK32
    return ((bits >> 23) & 0xFF) == 0xFF and (bits & 0x7FFFFF) != 0


def quiet(bits: int) -> int:
    return (bits | QUIET_BIT) & MASK32


def process_nans(a: int, b: int):
    """Arm's NaN propagation, or None when neither operand is a NaN.

    Transcribed from FPProcessNaNs, shared pseudocode at
    Datasheets/arm-a64-instruction-set.txt:506010-506031: a signalling
    NaN in either operand wins over a quiet one, and within each class
    the FIRST operand wins.  A signalling NaN is quieted on the way out
    (FPProcessNaN, :505965).  FEAT_AFP's alternative ordering does not
    apply - the Cortex-A72 does not implement it.
    """
    sa, ka, _ = unpack(a)
    sb, kb, _ = unpack(b)
    if ka == "snan":
        return quiet(a)
    if kb == "snan":
        return quiet(b)
    if ka == "qnan":
        return a & MASK32
    if kb == "qnan":
        return b & MASK32
    return None


def f_add(a: int, b: int, subtract: bool = False) -> int:
    # NaN PROCESSING RUNS ON THE OPERANDS AS WRITTEN, BEFORE THE NEGATION.
    #
    # This was wrong until 2026-08-26 and it is worth spelling out,
    # because it is the only defect the board found and the board found
    # it in the only way it could have been found.
    #
    # FPSub (Datasheets/arm-a64-instruction-set.txt:506956-506988) reads
    #
    #     let (type1,...) = FPUnpack(op1, ...);
    #     let (type2,...) = FPUnpack(op2, ...);
    #     var (done,result) = FPProcessNaNs(type1, type2, op1, op2, ...);
    #     if !done then ... value1 - value2 ...
    #
    # so the NaN is selected and propagated from op2 AS WRITTEN; the
    # negation happens afterwards and only to the VALUE.  This function
    # implemented subtraction by flipping the sign bit of b and calling
    # the adder, which is exactly right for the arithmetic and wrong for
    # the NaN: a NaN propagated out of operand two came back with its
    # sign bit inverted.
    #
    # NOTHING BUT A REAL A72 COULD HAVE CAUGHT IT.  The software core in
    # math.pi4 returns the default NaN for any NaN input, so the whole
    # soft column is blind to payloads and signs; the soft hash matched
    # on the first run.  Only the hardware column carries the propagated
    # value, and only a board produces it.
    orig_b = b & MASK32
    if subtract:
        b = (b ^ 0x80000000) & MASK32
    n = process_nans(a, orig_b)
    if n is not None:
        return n
    sa, ka, va = unpack(a)
    sb, kb, vb = unpack(b)
    if ka == "inf" and kb == "inf":
        return DEFAULT_NAN if sa != sb else (a & MASK32)
    if ka == "inf":
        return a & MASK32
    if kb == "inf":
        return b & MASK32
    if ka == "zero" and kb == "zero":
        # (-0) + (-0) is -0; every other combination of zeros is +0
        # under round to nearest.
        return 0x80000000 if (sa == 1 and sb == 1) else 0
    total = (-va if sa else va) + (-vb if sb else vb)
    if total == 0:
        # An exact cancellation of two non-zero values is +0 in round to
        # nearest, whatever the operand signs were.
        return 0
    return pack(1 if total < 0 else 0, abs(total))


def f_sub(a: int, b: int) -> int:
    return f_add(a, b, subtract=True)


def f_mul(a: int, b: int) -> int:
    n = process_nans(a, b)
    if n is not None:
        return n
    sa, ka, va = unpack(a)
    sb, kb, vb = unpack(b)
    sign = sa ^ sb
    if ka == "inf" or kb == "inf":
        if ka == "zero" or kb == "zero":
            return DEFAULT_NAN
        return (sign << 31) | 0x7F800000
    if ka == "zero" or kb == "zero":
        return sign << 31
    return pack(sign, va * vb)


def f_div(a: int, b: int) -> int:
    n = process_nans(a, b)
    if n is not None:
        return n
    sa, ka, va = unpack(a)
    sb, kb, vb = unpack(b)
    sign = sa ^ sb
    if ka == "inf" and kb == "inf":
        return DEFAULT_NAN
    if ka == "zero" and kb == "zero":
        return DEFAULT_NAN
    if ka == "inf" or kb == "zero":
        return (sign << 31) | 0x7F800000
    if kb == "inf" or ka == "zero":
        return sign << 31
    return pack(sign, va / vb)


def f_rel(rel: int, a: int, b: int) -> int:
    """0 lt, 1 le, 2 gt, 3 ge, 4 eq, 5 ne.  Unordered makes every ordered
    relation false and `ne` true - the IEEE-754 rule, stated once."""
    if is_nan(a) or is_nan(b):
        return 1 if rel == 5 else 0
    sa, ka, va = unpack(a)
    sb, kb, vb = unpack(b)
    x = None if ka == "inf" else (-va if sa else va)
    y = None if kb == "inf" else (-vb if sb else vb)
    # Infinities are compared by rank so that no sentinel magnitude has to
    # be invented: -inf < every finite < +inf, and like infinities are
    # equal.
    if x is None or y is None:
        rank_a = (1 if (x is None and sa == 0) else (-1 if x is None else 0))
        rank_b = (1 if (y is None and sb == 0) else (-1 if y is None else 0))
        if rank_a != rank_b:
            less = rank_a < rank_b
            greater = rank_a > rank_b
            equal = False
        else:
            if x is None and y is None:
                less = greater = False
                equal = True
            else:
                # one infinity, one finite, same rank cannot happen
                raise AssertionError("unreachable comparison ranking")
    else:
        less = x < y
        greater = x > y
        equal = x == y
    if rel == 0:
        return 1 if less else 0
    if rel == 1:
        return 1 if (less or equal) else 0
    if rel == 2:
        return 1 if greater else 0
    if rel == 3:
        return 1 if (greater or equal) else 0
    if rel == 4:
        return 1 if equal else 0
    return 0 if equal else 1


def i2f(n: int) -> int:
    """scvtf s, x - a signed 64-bit integer, correctly rounded to binary32."""
    if n == 0:
        return 0
    return pack(1 if n < 0 else 0, Fraction(abs(n)))


INT64_MIN = -(1 << 63)
INT64_MAX = (1 << 63) - 1


def f2i_hw(bits: int) -> int:
    """fcvtzs x, s - truncate toward zero, saturate at the 64-bit rails."""
    if is_nan(bits):
        return 0
    sign, kind, value = unpack(bits)
    if kind == "inf":
        return INT64_MIN if sign else INT64_MAX
    if kind == "zero":
        return 0
    mag = int(value)                       # Fraction -> int truncates toward zero
    n = -mag if sign else mag
    if n > INT64_MAX:
        return INT64_MAX
    if n < INT64_MIN:
        return INT64_MIN
    return n


def f2i_soft(bits: int) -> int:
    """MathFToIntB - the same, except that the negative rail is one higher.

    math.pi4:886-916 returns -9223372036854775807 rather than INT64_MIN.
    Reproduced rather than corrected: this function's job is to predict
    what the board's software path will print, not to be right.
    """
    n = f2i_hw(bits)
    if n == INT64_MIN:
        return INT64_MIN + 1
    return n


# ======================================================================
#  READING THE VECTORS OUT OF THE GATE SOURCE
# ======================================================================

def parse_gate(text: str):
    """(vectors, ints, random_pairs, seed), cross-checked against the
    constants declared in the same file."""
    def const(name: str) -> int:
        m = re.search(r"#%s\s*=\s*(-?\d+)" % name, text)
        if not m:
            raise SystemExit("cannot find #%s in %s" % (name, GATE.name))
        return int(m.group(1))

    n_declared = const("FPGATE_VECTORS")
    pairs = const("FPGATE_RANDOM_PAIRS")
    seed = const("FPGATE_SEED")

    body = text.split("FpGateVectors:", 1)
    if len(body) != 2:
        raise SystemExit("cannot find the FpGateVectors label")
    vec_text = body[1].split("EndDataSection", 1)[0]
    vectors = [int(v, 16) & MASK32
               for v in re.findall(r"Data\.l\s+\$([0-9A-Fa-f]+)", vec_text)]

    body = text.split("FpGateInts:", 1)
    if len(body) != 2:
        raise SystemExit("cannot find the FpGateInts label")
    int_text = body[1].split("EndDataSection", 1)[0]
    ints = [int(v) for v in re.findall(r"Data\.q\s+(-?\d+)", int_text)]

    if len(vectors) != n_declared:
        raise SystemExit(
            "#FPGATE_VECTORS says %d but the DataSection holds %d. The board "
            "would read past the end of the table; fix one of them."
            % (n_declared, len(vectors)))

    # An odd vector count misaligns the integer table that follows it.
    # The two DataSections are laid down consecutively after one .align 8;
    # this one is 4 bytes per entry and the next is read with Read.q, so
    # an odd count leaves the second table on a 4-byte boundary and the
    # first doubleword load takes a data abort on Device memory - which,
    # with the MMU off, is all of DRAM.  There is no exception vector, so
    # that presents as a silent hang.  Refused here because it is
    # invisible in the source and expensive on the bench.
    if len(vectors) % 2 != 0:
        raise SystemExit(
            "the vector table holds %d entries, which is odd. That leaves "
            "FpGateInts on a 4-byte boundary and its first Read.q would be a "
            "misaligned doubleword load - a data abort with no vector "
            "installed, i.e. a silent hang. Add a padding vector."
            % len(vectors))

    # RunI2F's loop bound is written out in the source as "For i = 0 To N".
    m = re.search(r"Restore FpGateInts\s*\n\s*For i = 0 To (\d+)", text)
    if m:
        bound = int(m.group(1))
        if bound + 1 != len(ints):
            raise SystemExit(
                "RunI2F reads %d integers but FpGateInts holds %d"
                % (bound + 1, len(ints)))
    return vectors, ints, pairs, seed


# ======================================================================
#  THE SEQUENCE - it must match the board's, step for step
# ======================================================================

class Lcg:
    """The board's NextRandom32, reproduced.

    31-bit state; two draws per 32-bit pattern, taking bits 23:8 of each.
    The multiply is at most 2^61 and cannot overflow a signed 64-bit
    register, which is exactly why the board's generator is 31-bit: the
    sequence is then reproducible here without knowing anything about
    that backend's overflow behaviour.
    """

    def __init__(self, seed: int):
        self.s = seed

    def _step(self) -> int:
        self.s = (self.s * 1103515245 + 12345) & 0x7FFFFFFF
        return (self.s >> 8) & 0xFFFF

    def next32(self) -> int:
        a = self._step()
        b = self._step()
        return ((a << 16) | b) & MASK32


class Hasher:
    """h = h * 31 + value, wrapping at 64 bits, in the board's order."""

    def __init__(self):
        self.h = 0

    def add(self, v: int):
        self.h = (self.h * 31 + (v & MASK64)) & MASK64


def run(vectors, ints, pairs, seed):
    """Produce the two expected hashes and the predicted difference counts.

    THE ORDER HERE IS THE CONTRACT.  It mirrors pi4FpGate.pi4's Main()
    exactly: RunArithmetic, RunRelations, RunI2F, RunF2I, RunRandom - and
    within Judge, the software result is hashed before the hardware one.
    """
    soft = Hasher()
    hw = Hasher()
    agree = Hasher()
    nan_rows = 0
    rail_rows = 0
    agreed = 0
    total = 0

    def judge(s: int, h: int, nan_class: bool, rail_class: bool):
        nonlocal nan_rows, rail_rows, agreed, total
        soft.add(s)
        hw.add(h)
        total += 1
        if s == h:
            agreed += 1
            agree.add(s)
        elif nan_class:
            nan_rows += 1
        elif rail_class:
            rail_rows += 1

    ops = (lambda a, b: f_add(a, b), f_sub, f_mul, f_div)

    # phase 1 - arithmetic, full cross product
    for a in vectors:
        for b in vectors:
            for op in ops:
                r = op(a, b)
                s = DEFAULT_NAN if (is_nan(a) or is_nan(b)) else r
                judge(s, r, is_nan(a) or is_nan(b), False)

    # phase 2 - the six relations
    for a in vectors:
        for b in vectors:
            for rel in range(6):
                r = f_rel(rel, a, b)
                judge(r, r, False, False)

    # phase 3 - integer to float
    #
    # No predicted divergence here.  math.pi4's MathFFromIntB is expected
    # to match the hardware exactly, INT64_MIN included - which it does
    # only because writing this file found that it did not.  Before
    # 2026-08-26 that one input made MathFRound spin forever; the fix and
    # the reasoning are at math.pi4's MathFFromIntB.  The value stays in
    # the vector table because it is exactly the kind of boundary a gate
    # exists to cover.
    for n in ints:
        r = i2f(n)
        judge(r, r, False, False)

    # phase 4 - float to integer
    for a in vectors:
        h = f2i_hw(a)
        s = f2i_soft(a)
        judge(s, h, False, s != h)

    # phase 5 - the pseudo-random sweep
    lcg = Lcg(seed)
    for _ in range(pairs):
        a = lcg.next32()
        b = lcg.next32()
        for op in ops:
            r = op(a, b)
            s = DEFAULT_NAN if (is_nan(a) or is_nan(b)) else r
            judge(s, r, is_nan(a) or is_nan(b), False)

    return agree.h, soft.h, hw.h, agreed, nan_rows, rail_rows, total


# ======================================================================
#  SELF-TEST - the oracle has to be checked too
# ======================================================================
#  Values whose binary32 encoding is known independently, chosen to
#  exercise the parts of the rounder that an ordinary value never
#  reaches.  If this list passes, the rounder handles gradual underflow,
#  the carry out of the top of the mantissa, overflow to infinity and
#  ties to even.
# ======================================================================
SELF_TEST = [
    ("1.0 + 1.0 = 2.0", lambda: f_add(0x3F800000, 0x3F800000), 0x40000000),
    ("3.0 * 7.0 = 21.0", lambda: f_mul(0x40400000, 0x40E00000), 0x41A80000),
    ("1.0 / 2.0 = 0.5", lambda: f_div(0x3F800000, 0x40000000), 0x3F000000),
    ("(+0) + (-0) = +0", lambda: f_add(0x00000000, 0x80000000), 0x00000000),
    ("(-0) + (-0) = -0", lambda: f_add(0x80000000, 0x80000000), 0x80000000),
    ("1.0 - 1.0 = +0", lambda: f_sub(0x3F800000, 0x3F800000), 0x00000000),
    ("0 * -1 = -0", lambda: f_mul(0x00000000, 0xBF800000), 0x80000000),
    ("Inf - Inf = default NaN", lambda: f_sub(0x7F800000, 0x7F800000), DEFAULT_NAN),
    ("Inf / Inf = default NaN", lambda: f_div(0x7F800000, 0x7F800000), DEFAULT_NAN),
    ("0 * Inf = default NaN", lambda: f_mul(0x00000000, 0x7F800000), DEFAULT_NAN),
    ("1 / 0 = +Inf", lambda: f_div(0x3F800000, 0x00000000), 0x7F800000),
    ("1 / -0 = -Inf", lambda: f_div(0x3F800000, 0x80000000), 0xFF800000),
    # gradual underflow: smallest normal minus smallest subnormal is the
    # largest subnormal, which flush-to-zero would turn into zero.
    ("min normal - min subnormal = max subnormal",
     lambda: f_sub(0x00800000, 0x00000001), 0x007FFFFF),
    ("min subnormal + min subnormal", lambda: f_add(1, 1), 2),
    ("max subnormal + min subnormal = min normal",
     lambda: f_add(0x007FFFFF, 0x00000001), 0x00800000),
    # overflow: the largest finite doubled is infinity
    ("max finite * 2 = +Inf", lambda: f_mul(0x7F7FFFFF, 0x40000000), 0x7F800000),
    ("-max finite * 2 = -Inf", lambda: f_mul(0xFF7FFFFF, 0x40000000), 0xFF800000),
    # ties to even, on both sides of the 2^24 cliff
    ("2^24 + 1 rounds to even (down)",
     lambda: f_add(0x4B800000, 0x3F800000), 0x4B800000),
    ("2^24+2 + 1 rounds to even (up)",
     lambda: f_add(0x4B800001, 0x3F800000), 0x4B800002),
    ("1.0 + 2^-24 is a tie, rounds to even",
     lambda: f_add(0x3F800000, 0x33800000), 0x3F800000),
    ("1.0+ulp + 2^-24 is a tie, rounds up to even",
     lambda: f_add(0x3F800001, 0x33800000), 0x3F800002),
    # NaN propagation, which is the part that differs from the software core
    ("qNaN payload propagates",
     lambda: f_add(0x7FC12345, 0x3F800000), 0x7FC12345),
    ("sNaN is quieted on the way out",
     lambda: f_add(0x7F800001, 0x3F800000), 0x7FC00001),
    ("first operand wins between two qNaNs",
     lambda: f_add(0x7FC12345, 0x7FC00099), 0x7FC12345),
    ("an sNaN beats a qNaN in the second position",
     lambda: f_add(0x7FC12345, 0x7F800001), 0x7FC00001),
    # --- the regression that a real A72 found, 2026-08-26 -------------
    # Subtraction is implemented here as `a + (-b)`, and the negation
    # must NOT be visible to NaN selection: FPSub hands FPProcessNaNs
    # op1 and op2 AS WRITTEN and negates only the value
    # (arm-a64-instruction-set.txt:506956-506988).  Before the fix these
    # four returned the NaN with its sign bit inverted, the board's
    # hardware checksum did not match, and the gate's decision table
    # blamed the compiler.  Cheap to check, so it is checked.
    ("sub propagates op2's NaN WITHOUT flipping its sign",
     lambda: f_sub(0x3F800000, 0x7FC12345), 0x7FC12345),
    ("sub propagates a negative op2 NaN unchanged",
     lambda: f_sub(0x3F800000, 0xFFC12345), 0xFFC12345),
    ("sub quiets an op2 sNaN without flipping its sign",
     lambda: f_sub(0x3F800000, 0x7F800001), 0x7FC00001),
    ("sub: an op2 sNaN still beats an op1 qNaN, sign intact",
     lambda: f_sub(0x7FC12345, 0x7F800001), 0x7FC00001),
    # conversions
    ("i2f 2^24 + 1 rounds to even", lambda: i2f(16777217), 0x4B800000),
    ("i2f 2^24 + 3 rounds to even", lambda: i2f(16777219), 0x4B800002),
    ("i2f INT64_MAX", lambda: i2f(INT64_MAX), 0x5F000000),
    ("f2i of 2.9 truncates", lambda: f2i_hw(0x4039999A), 2),
    ("f2i of -2.9 truncates toward zero", lambda: f2i_hw(0xC039999A), -2),
    ("f2i of NaN is zero", lambda: f2i_hw(DEFAULT_NAN), 0),
    ("f2i of +Inf saturates high", lambda: f2i_hw(0x7F800000), INT64_MAX),
    ("f2i of -Inf saturates low", lambda: f2i_hw(0xFF800000), INT64_MIN),
    # relations against a NaN
    ("NaN < 1 is false", lambda: f_rel(0, DEFAULT_NAN, 0x3F800000), 0),
    ("NaN <= 1 is false", lambda: f_rel(1, DEFAULT_NAN, 0x3F800000), 0),
    ("NaN > 1 is false", lambda: f_rel(2, DEFAULT_NAN, 0x3F800000), 0),
    ("NaN >= 1 is false", lambda: f_rel(3, DEFAULT_NAN, 0x3F800000), 0),
    ("NaN = 1 is false", lambda: f_rel(4, DEFAULT_NAN, 0x3F800000), 0),
    ("NaN <> 1 is TRUE", lambda: f_rel(5, DEFAULT_NAN, 0x3F800000), 1),
    ("NaN <> NaN is TRUE", lambda: f_rel(5, DEFAULT_NAN, DEFAULT_NAN), 1),
    ("+0 = -0 is TRUE", lambda: f_rel(4, 0x00000000, 0x80000000), 1),
    ("-Inf < +Inf", lambda: f_rel(0, 0xFF800000, 0x7F800000), 1),
    ("+Inf = +Inf", lambda: f_rel(4, 0x7F800000, 0x7F800000), 1),
    ("-Inf < smallest negative normal",
     lambda: f_rel(0, 0xFF800000, 0x80800000), 1),
]


def self_test() -> int:
    bad = 0
    for name, fn, expect in SELF_TEST:
        got = fn()
        if got != expect:
            bad += 1
            if isinstance(expect, int) and expect >= 0 and expect <= MASK32:
                print("   FAIL %-46s expected $%08X got $%08X"
                      % (name, expect, got & MASK32))
            else:
                print("   FAIL %-46s expected %d got %d" % (name, expect, got))
    if bad == 0:
        print("   %d oracle vectors, all correct" % len(SELF_TEST))
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--self-test", action="store_true",
                    help="check the oracle against known encodings and stop")
    args = ap.parse_args()

    print("gate source : %s" % GATE)
    print()
    print("--- the oracle checked against known binary32 encodings ----------")
    bad = self_test()
    print()
    if bad:
        print("a64_f32_gate: FAIL - the oracle itself is wrong; fix it before")
        print("using anything it says about the board.")
        return 1
    if args.self_test:
        print("a64_f32_gate: oracle PASS")
        return 0

    if not GATE.exists():
        print("a64_f32_gate: %s is missing" % GATE)
        return 1
    text = GATE.read_text(encoding="utf-8", errors="replace")
    vectors, ints, pairs, seed = parse_gate(text)

    print("--- the run the board will make ----------------------------------")
    print("   %d fixed vectors, %d integers, %d random pairs, seed %d"
          % (len(vectors), len(ints), pairs, seed))
    agree, soft, hw, agreed, nan_rows, rail_rows, total = run(vectors, ints, pairs, seed)
    print("   %d results in the stream" % total)
    print()
    print("--- what the board should print ----------------------------------")
    print("   hash agree = $%016X" % agree)
    print("   hash soft  = $%016X" % soft)
    print("   hash hw    = $%016X" % hw)
    print()
    print("   agreed bit for bit : %d" % agreed)
    print("   REAL MISMATCHES    : 0")
    print("   NaN payload rows   : %d" % nan_rows)
    print("   f2i rail rows      : %d" % rail_rows)
    print()
    print("HOW TO READ THE RESULT - COUNTERS FIRST, HASHES SECOND")
    print()
    print("   THE ORDER IS THE POINT.  On the first silicon run, 2026-08-26,")
    print("   the board printed REAL MISMATCHES: 0 and a hardware hash that")
    print("   did not match this file, and the decision table that used to be")
    print("   here said that meant the lowering was wrong.  It did not.  A")
    print("   hash can differ for a reason the row-level classification has")
    print("   already accepted, so a hash may narrow down WHERE a difference")
    print("   lives but must never be what declares one.")
    print()
    print("   REAL MISMATCHES > 0   something is genuinely wrong. Nothing")
    print("                         below matters until it is 0.")
    print()
    print("   Then, with REAL MISMATCHES at 0:")
    print("   AGREE matches         all three implementations agree on every")
    print("                         row where agreement was expected. THIS is")
    print("                         the line that clears the lowering and the")
    print("                         encodings.")
    print("   AGREE differs         the encodings or the lowering are suspect.")
    print("                         Run tools/a64/a64_fp_check.py first.")
    print("   SOFT differs          math.pi4's core changed or has a bug; the")
    print("                         hardware is not implicated.")
    print("   HW differs, AGREE ok  the difference is confined to NaN PAYLOAD")
    print("                         VALUES. The hardware is producing a NaN,")
    print("                         this oracle predicted a different one.")
    print("                         A model question, not a lowering defect -")
    print("                         and exactly what happened on the first")
    print("                         run, where this file was the wrong one.")
    return 0

if __name__ == "__main__":
    sys.exit(main())

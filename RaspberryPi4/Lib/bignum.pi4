; ======================================================================
;  bignum.pi4 - i15 big-integer core, ON THE RASPBERRY PI 4
;               (BCM2711, AArch64)
; ======================================================================
;
;  Translated from BearSSL (c) 2016 Thomas Pornin - MIT licence.
;  The notice ships as licenses/BearSSL-LICENSE.txt (release condition).
;
;     XIncludeFile "RaspberryPi4/Lib/bignum.pi4"
;
;  Constant-time modular big integers on 15-bit limbs, translated from
;  the BearSSL "i15" core to the house dialect.  Reads-and-translates
;  only: no C is linked, no foreign ABI is followed.
;
;  WHY 15-BIT LIMBS, ON A 64-BIT PART.  The 32-bit families chose i15
;  because a 15x15 product fits a signed 32-bit word and they have no
;  wider multiply.  THIS PART HAS ONE, and i31 or a 64-bit limb core
;  would be faster.  It is deliberately NOT taken:
;
;    * everything above this file - ec256, ecdsa, rsa, x509 - is written
;      against the i15 representation, limb for limb.  A different limb
;      width is not a port of this module, it is a rewrite of six;
;    * the i15 representation is what the twins gate compares.  Changing
;      it here would leave the Pi 4 with no counterpart to check against
;      and no way to see a procedure that drifted;
;    * the products are the SAME NUMBERS at 64 bits as at 32.  A 15-bit
;      limb product is at most $3FFF0001 and the accumulated sums in
;      BnMontmul and BnMulAcc stay under 2^32, so nothing in this core
;      ever relied on the 32-bit wrap to be correct.  See the audit.
;
;  A wider core belongs in its own module with its own gate, the day
;  something measures that RSA-2048 verification is too slow here.
;
;  REPRESENTATION (load-bearing, identical to the 32-bit copies).  A big
;  integer is an array of 16-BIT words x[]:
;    x[0]      the ENCODED announced bit length: if the top set bit lives
;              in value word j (0-based) with that word's own bit length
;              b (1..15), then x[0] = (j << 4) + b. The value word count
;              is (x[0] + 15) >> 4; a loop wanting one guard word beyond
;              the top uses (x[0] + 31) >> 4.
;    x[1..]    the value, little-endian, 15 bits per word, upper bit clear
;              (x[1] is the least significant limb).
;
;  > CALLERS MUST DECLARE THEIR BUFFERS `.u`, NOT `.i`.  On this part a
;  > `Dim x.i[n]` element is EIGHT bytes and this core addresses word i
;  > at base + i*2.  `Dim x.u[n]` is the only correct spelling, and it is
;  > the same spelling the 32-bit families use.
;
;  API (arrays are passed by ADDRESS; @yourArray gives the base):
;    Word helpers a reviewer may reuse:
;      BnMux(ctl,x,y) BnEq/BnNeq/BnGt/BnGe/BnLt/BnLe(a,b) BnNot(c)
;      BnBitLen32(x)          32-bit bit length, branchless
;    Core:
;      BnZero(x, encbitlen)        set announced length, clear the words
;      BnIsZero(x)                 1 if zero, else 0 (constant-time)
;      BnNinv15(m1)                -1/m1 mod 2^15, the Montgomery m0i
;      BnAdd(a, b, ctl) / BnSub(a, b, ctl)   returns the carry/borrow;
;                                  a is modified only when ctl = 1
;      BnBitLength(valptr, nwords) encoded announced length of nwords limbs
;      BnRshift(x, count)          shift right by count (< 15) bits
;      BnDecode(x, src, len)       big-endian bytes -> integer
;      BnEncode(dst, len, x)       integer -> len big-endian bytes
;      BnReduce(x, a, m)           x = a mod m, announced length of m
;      BnDecodeReduce(x, src, len, m)  decode then reduce mod m
;      BnMulAddSmall(x, z, m)      x = (x*2^15 + z) mod m
;      BnMulAcc(d, a, b)           d = d + a*b (plain, not modular)
;      BnMontmul(d, x, y, m, m0i)  d = x*y/2^(15*len) mod m (Montgomery)
;      BnToMonty(x, m) / BnFromMonty(x, m, m0i)
;      BnModpow(x, e, elen, m, m0i, t1, t2)      x = x^e mod m (ladder)
;      BnModpow2(x, e, elen, m, m0i, tmp, twlen) windowed; returns 1/0
;
;  This is the VERIFY-ONLY subset: moddiv, decode-mod and key generation
;  are deliberately absent - a TLS client that only verifies never needs
;  them.
;
;  REQUIRES NOTHING.  This file includes no other file (house rule: a
;  library never includes a library - the MAIN file lists them) and uses
;  only PeekA/PokeB, PeekU/PokeW and arithmetic.
;
;  THIS FILE TURNS EnableExplicit ON FOR YOUR PROGRAM TOO.  The pragma
;  below is not file-scoped; every variable compiled after this include
;  must be declared before use.
;
;  ======================================================================
;   .i IS 64 BITS HERE.  THE FOUR-SHAPE AUDIT, PROCEDURE BY PROCEDURE
;  ======================================================================
;
;  The four ways a 32-bit portable core breaks on this part were measured
;  in Anvil/Core/sha256.pbi and RaspberryPi4/Lib/gcm.pi4.  Every one was
;  looked for here and the finding is recorded either way - "not present"
;  is a result, not a silence.
;
;  SHAPE 1 - AN ARRAY ELEMENT IS EIGHT BYTES, NOT FOUR.
;      NOT PRESENT IN THIS FILE.  The core declares no array at all: a
;      big integer is a caller's buffer reached through PeekU/PokeW at
;      base + i*2, and the only global is the scalar BnRem.  What the
;      shape DOES reach is the CALLER, which is why the note above
;      insists on `.u` buffers; the gate's harness declares every one
;      that way and a `.i` buffer is mutation M1.
;
;  SHAPE 2 - PeekL SIGN-EXTENDS.
;      NOT PRESENT.  There is no PeekL here and never was.  Words come
;      in through PeekU (unsigned 16-bit) and bytes through PeekA
;      (unsigned 8-bit), both of which zero-extend on every backend
;      since the 2026-08-25 ruling.  The 32-bit copies already used the
;      unsigned spellings because a 15-bit limb read signed would have
;      been wrong on them too.
;
;  SHAPE 3 - `<<` DOES NOT DISCARD AT BIT 31.
;      PRESENT IN TWO PLACES AND NOWHERE ELSE, and the reason so few is
;      worth stating: an i15 limb is 15 bits, so every product is at
;      most $3FFF0001 and every accumulated sum in BnMontmul, BnMulAcc
;      and BnMulAddSmall stays under 2^32.  NOTHING IN THIS CORE EVER
;      WRAPPED, so nothing here depended on the wrap.  That is a fact
;      about the limb size, not luck, and it is why i15 ports across a
;      width change when a 32-bit-word core like SHA-256 does not.
;        * BnNinv15's Newton iteration is the exception - it is defined
;          modulo a power of two and the 32-bit copies let the multiply
;          wrap.  Masked to #BN_W32 at every step here, so the
;          intermediates are the same values, not merely congruent.
;        * BnDivrem16 shifts the divisor up by 16 - at most $FFFF0000,
;          which fits 32 bits on both widths - and then only ever shifts
;          it back down through an explicit `& $7FFFFFFF`.
;
;  SHAPE 4 - A 32-BIT COUNTER NEVER WRAPS.
;      NOT PRESENT.  There is no counter here that is allowed to wrap;
;      every loop bound is a small public word count.
;
;  ---- THE FIFTH THING, WHICH IS THE ONE THAT ACTUALLY BITES ----------
;
;  `>> 31` AS A SIGN TEST.  This core is built out of branchless
;  comparisons, and the 32-bit copies write every one of them as "shift
;  the sign bit down to bit 0".  ON THIS PART THE SIGN BIT IS BIT 63.
;  This is the same defect that made GcmDecrypt hand back
;  $FFFFFFFF00000000 for a forged tag, and it is more dangerous here
;  because these helpers return the 0/1 flags that every mask in the
;  file is built from - a wrong flag does not look like a wrong answer,
;  it looks like the other branch.
;
;  Six sites, all corrected, all of them mutations in the gate:
;      BnEq, BnNeq   (q | -q) >> 63
;      BnSub         the borrow
;      BnMulAddSmall the "q was zero" correction and the
;                    multiply-subtract borrow
;      BnIsZero      which ALSO dropped a `! $FFFFFFFF` complement:
;                    XOR-ing a 64-bit value against a 32-bit all-ones
;                    leaves bits 32..63 untouched, which is precisely
;                    the tag-verdict shape.
;      BnMulAcc      the announced-length round-up, which spelled
;                    "dl >= 15" as the sign bit of a 32-bit complement.
;                    Written as BnGe(dl, 15) - the core's own word for
;                    it - rather than a wider complement.
;
;  > MEASURED, NOT ASSUMED, AND THE FIRST DRAFT OF THIS PARAGRAPH WAS
;  > WRONG.  It said two of the six - BnIsZero's complement and
;  > BnMulAcc's - would break outright while the other four survived.
;  > The mutation sweep says ALL SIX SURVIVE the naive width change, and
;  > working out why is the useful part: an arithmetic `>> 31` of a
;  > small negative is still all-ones, so `& 1` still reads 1; and in
;  > BnIsZero the 32-bit complement clears bit 31 but leaves bits 32..63
;  > set, so the value stays negative and the shift delivers the
;  > CLEARED bit 31 to bit 0 - two errors that cancel.  Every one of the
;  > six is in the gate's table as an EXPECTED SURVIVOR with that
;  > argument written out.
;
;  SO WHY CHANGE LINES THAT WORK?  Because each of the six is a silent
;  claim about the range of its operand, enforced by nothing, in a file
;  whose whole job is to be reviewable a line at a time.  The
;  correctness of `>> 31` here depends on facts three procedures away.
;  `>> 63` depends on the definition of a sign bit.  And the shape they
;  share with the GcmDecrypt defect is exactly why a reader cannot skim
;  them: the fatal instance and the harmless one are typographically
;  identical.  The day one of these operands grows - a caller passing a
;  wider value, a limb size that changes - the wrong ones would start
;  failing silently and the sweep would go from EXPECTED-SURVIVOR to
;  UNEXPECTED-KILL, which is the loud signal that the argument expired.
;
;  ---- BnGt IS WRITTEN DIFFERENTLY, ON PURPOSE ------------------------
;
;  The 32-bit unsigned compare is a three-XOR reconstruction of the
;  borrow out of a subtraction that WRAPPED.  Nothing wraps here, so the
;  difference of two masked 32-bit values is exact and its sign is the
;  answer directly.  Shorter, still branchless, and it no longer depends
;  on every caller keeping its operands under 2^32.  BnGe, BnLt and BnLe
;  are unchanged: they are defined in terms of BnGt.
;
;  ======================================================================
;   CONSTANT TIME
;  ======================================================================
;
;  Branchless BY DESIGN and unchanged by the port: no branch and no array
;  index depends on a secret value; every conditional is a mask.  The
;  Montgomery ladder in BnModpow does a fixed two multiplies per exponent
;  bit.  The only branches read PUBLIC lengths (the announced bit length
;  of the modulus is allowed to leak).  Forbidden on secret data, and
;  absent here: / and %.
;
;  The gate measures this rather than asserting it: --timing runs the
;  same operation at the same lengths with wholly different values and
;  requires the identical model instruction count.
;
;  PROVEN: builds clean for pi4 and passes tools/a64/a64_bignum_check.py
;  on the SAME vectors as the three 32-bit families (the gate imports
;  tools/gen_bignum_vectors.py rather than carrying a copy), cycle-equal
;  under that gate's --timing, mutation-swept under --mutate, and
;  structurally twinned under tools/check_tls_twins.py --cross bignum.
;  NOTHING HERE HAS RUN ON SILICON.
; ======================================================================
; ==== PORTABLE CORE A64 BEGIN ====
EnableExplicit

; A 32-bit word mask.  `.i` is 64 bits here, so anything that must stay
; inside 32 bits says so.  Only two places need it (BnGt and BnNinv15);
; every other value in this core is a 15-bit limb or a bounded sum and
; cannot leave its range - see the header's audit.
#BN_W32 = $FFFFFFFF

Global BnRem.i                       ; remainder out of BnDivrem16

; ----------------------------------------------------------------------
;  WORD ACCESS. A big integer word i lives at base + i*2 (16-bit words).
;  PeekU reads it unsigned (no sign extension); every value word is <=
;  0x7FFF so the read is exact. PokeW stores the low 16 bits.
; ----------------------------------------------------------------------
Procedure.i BnGw(p.i, i.i)
  ProcedureReturn PeekU(p + (i << 1))
EndProcedure

Procedure BnSw(p.i, i.i, v.i)
  PokeW(p + (i << 1), v & $FFFF)
EndProcedure

; ----------------------------------------------------------------------
;  CONSTANT-TIME WORD HELPERS. Translated from the reference inner.h.
;  Right shift is arithmetic here too, but THE SIGN BIT IS BIT 63, NOT
;  BIT 31, so every sign-bit test below is `>> 63` and not the `>> 31`
;  the 32-bit copies use. Bitwise NOT is NOT written 'v ! $FFFFFFFF'
;  here - a 32-bit all-ones leaves bits 32..63 alone, which is the
;  shape that made a forged AES-GCM tag read as authentic. XOR is
;  written '!' and negation as (0 - v), as in the 32-bit copies.
; ----------------------------------------------------------------------
Procedure.i BnNot(ctl.i)             ; logical NOT of a 0/1 flag
  ProcedureReturn ctl ! 1
EndProcedure

Procedure.i BnMux(ctl.i, x.i, y.i)   ; x if ctl = 1, y if ctl = 0
  ProcedureReturn y ! ((0 - ctl) & (x ! y))
EndProcedure

Procedure.i BnEq(x.i, y.i)           ; 1 if x = y
  Protected q.i
  q = x ! y
  q = (q | (0 - q)) >> 63
  ProcedureReturn (q & 1) ! 1
EndProcedure

Procedure.i BnNeq(x.i, y.i)          ; 1 if x <> y
  Protected q.i
  q = x ! y
  q = (q | (0 - q)) >> 63
  ProcedureReturn q & 1
EndProcedure

Procedure.i BnGt(x.i, y.i)           ; 1 if x > y (unsigned)
  ; A 64-BIT REGISTER CAN DO THIS DIRECTLY.  The three-XOR dance in the
  ; 32-bit copies exists because a 32-bit subtraction of two 32-bit
  ; values wraps and the borrow has to be recovered from the sign bits.
  ; Here both operands are masked into 0..$FFFFFFFF and the difference
  ; is EXACT in the range -(2^32-1)..(2^32-1), so its sign IS the
  ; answer.  Fewer operations, branchless as before, and it does not
  ; depend on a caller never handing in a value above 2^32.
  ProcedureReturn ((((y & #BN_W32) - (x & #BN_W32)) >> 63) & 1)
EndProcedure

Procedure.i BnGe(x.i, y.i)           ; 1 if x >= y (unsigned)
  ProcedureReturn BnGt(y, x) ! 1
EndProcedure

Procedure.i BnLt(x.i, y.i)           ; 1 if x < y (unsigned)
  ProcedureReturn BnGt(y, x)
EndProcedure

Procedure.i BnLe(x.i, y.i)           ; 1 if x <= y (unsigned)
  ProcedureReturn BnGt(x, y) ! 1
EndProcedure

; ----------------------------------------------------------------------
;  BnBitLen32(x) - bit length of a 32-bit word, 0..32, branchless. Every
;  logical shift here is masked because a large x has its sign bit set.
; ----------------------------------------------------------------------
Procedure.i BnBitLen32(x.i)
  Protected k.i
  Protected c.i
  k = BnNeq(x, 0)
  c = BnGt(x, $FFFF)
  x = BnMux(c, (x >> 16) & $FFFF, x)
  k = k + (c << 4)
  c = BnGt(x, $FF)
  x = BnMux(c, (x >> 8) & $FFFFFF, x)
  k = k + (c << 3)
  c = BnGt(x, $F)
  x = BnMux(c, (x >> 4) & $FFFFFFF, x)
  k = k + (c << 2)
  c = BnGt(x, 3)
  x = BnMux(c, (x >> 2) & $3FFFFFFF, x)
  k = k + (c << 1)
  k = k + BnGt(x, 1)
  ProcedureReturn k
EndProcedure

; ----------------------------------------------------------------------
;  BnZero(x, encbitlen) - set the announced length and clear the words.
; ----------------------------------------------------------------------
Procedure BnZero(x.i, encbitlen.i)
  Protected n.i
  Protected i.i
  BnSw(x, 0, encbitlen)
  n = (encbitlen + 15) >> 4
  i = 1
  While i <= n
    BnSw(x, i, 0)
    i = i + 1
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  BnIsZero(x) - 1 if the integer is zero, else 0. Constant-time: it ORs
;  every value word and tests the accumulator once.
; ----------------------------------------------------------------------
Procedure.i BnIsZero(x.i)
  Protected z.i
  Protected u.i
  Protected q.i
  z = 0
  u = (BnGw(x, 0) + 15) >> 4
  While u > 0
    z = z | BnGw(x, u)
    u = u - 1
  Wend
  q = z | (0 - z)
  ProcedureReturn (((q >> 63) & 1) ! 1)
EndProcedure

; ----------------------------------------------------------------------
;  BnNinv15(x) - -1/x mod 2^15 for an odd 15-bit low word x (the m0i the
;  Montgomery routines need). Newton iteration; only the low bits matter,
;  and 32-bit multiply preserves them exactly.
; ----------------------------------------------------------------------
Procedure.i BnNinv15(x.i)
  Protected y.i
  ; MASKED AT EVERY STEP.  The 32-bit copies get this for free: their
  ; multiply wraps mod 2^32 and only the low 15 bits are ever read.
  ; Here the iterates would reach about 2^105 and wrap mod 2^64 - still
  ; congruent mod 2^15, so still the right answer, but the intermediate
  ; values would no longer be the ones the proven copies compute.  The
  ; mask makes them identical rather than merely equivalent.
  y = 2 - x
  y = (y * (2 - x * y)) & #BN_W32
  y = (y * (2 - x * y)) & #BN_W32
  y = (y * (2 - x * y)) & #BN_W32
  ProcedureReturn BnMux(x & 1, 0 - y, 0) & $7FFF
EndProcedure

; ----------------------------------------------------------------------
;  BnAdd(a, b, ctl) - a = a + b when ctl = 1 (the carry is computed and
;  returned regardless). a and b must share the announced bit length.
; ----------------------------------------------------------------------
Procedure.i BnAdd(a.i, b.i, ctl.i)
  Protected cc.i
  Protected m.i
  Protected u.i
  Protected aw.i
  Protected bw.i
  Protected naw.i
  cc = 0
  m = (BnGw(a, 0) + 31) >> 4
  u = 1
  While u < m
    aw = BnGw(a, u)
    bw = BnGw(b, u)
    naw = aw + bw + cc
    cc = (naw >> 15) & 1
    BnSw(a, u, BnMux(ctl, naw & $7FFF, aw))
    u = u + 1
  Wend
  ProcedureReturn cc
EndProcedure

; ----------------------------------------------------------------------
;  BnSub(a, b, ctl) - a = a - b when ctl = 1 (the borrow is computed and
;  returned regardless). a and b must share the announced bit length.
; ----------------------------------------------------------------------
Procedure.i BnSub(a.i, b.i, ctl.i)
  Protected cc.i
  Protected m.i
  Protected u.i
  Protected aw.i
  Protected bw.i
  Protected naw.i
  cc = 0
  m = (BnGw(a, 0) + 31) >> 4
  u = 1
  While u < m
    aw = BnGw(a, u)
    bw = BnGw(b, u)
    naw = aw - bw - cc
    cc = (naw >> 63) & 1
    BnSw(a, u, BnMux(ctl, naw & $7FFF, aw))
    u = u + 1
  Wend
  ProcedureReturn cc
EndProcedure

; ----------------------------------------------------------------------
;  BnBitLength(valptr, nwords) - encoded announced length of an integer
;  given as nwords value limbs at valptr (which points at the first limb,
;  i.e. &x[1]). Constant-time in the values.
; ----------------------------------------------------------------------
Procedure.i BnBitLength(valptr.i, nwords.i)
  Protected tw.i
  Protected twk.i
  Protected c.i
  Protected w.i
  tw = 0
  twk = 0
  While nwords > 0
    nwords = nwords - 1
    c = BnEq(tw, 0)
    w = BnGw(valptr, nwords)
    tw = BnMux(c, w, tw)
    twk = BnMux(c, nwords, twk)
  Wend
  ProcedureReturn (twk << 4) + BnBitLen32(tw)
EndProcedure

; ----------------------------------------------------------------------
;  BnRshift(x, count) - shift the whole integer right by count bits,
;  0 <= count < 15. count is public; the announced length is unchanged.
; ----------------------------------------------------------------------
Procedure BnRshift(x.i, count.i)
  Protected len.i
  Protected u.i
  Protected r.i
  Protected w.i
  len = (BnGw(x, 0) + 15) >> 4
  If len = 0
    ProcedureReturn
  EndIf
  r = BnGw(x, 1) >> count
  u = 2
  While u <= len
    w = BnGw(x, u)
    BnSw(x, u - 1, ((w << (15 - count)) | r) & $7FFF)
    r = w >> count
    u = u + 1
  Wend
  BnSw(x, len, r)
EndProcedure

; ----------------------------------------------------------------------
;  BnDivrem16(x, d) - constant-time 32/16 division. The divisor must be
;  at most 16 bits and the quotient at most 17 bits. Returns the quotient
;  and leaves the remainder in BnRem. Branchless: it conditionally
;  subtracts a shifted divisor at every step through a mask.
; ----------------------------------------------------------------------
Procedure.i BnDivrem16(x.i, d.i)
  Protected i.i
  Protected q.i
  Protected ctl.i
  q = 0
  d = d << 16
  i = 16
  While i >= 0
    ctl = BnLe(d, x)
    q = q | (ctl << i)
    x = x - ((0 - ctl) & d)
    d = (d >> 1) & $7FFFFFFF
    i = i - 1
  Wend
  BnRem = x
  ProcedureReturn q
EndProcedure

; ----------------------------------------------------------------------
;  BnMoveUp(x, mlen) - the in-place word shift muladd needs: move value
;  words [1 .. mlen-1] up to [2 .. mlen]. Copied top-down because the
;  ranges overlap and the destination is higher.
; ----------------------------------------------------------------------
Procedure BnMoveUp(x.i, mlen.i)
  Protected u.i
  u = mlen
  While u >= 2
    BnSw(x, u, BnGw(x, u - 1))
    u = u - 1
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  BnMulAddSmall(x, z, m) - x = (x*2^15 + z) mod m. The value in x must
;  already be lower than m and share m's announced length. This is the
;  workhorse behind reduce, decode-reduce and to-Montgomery.
;
;  It estimates the top quotient word by a 30/15 division of the two top
;  words, then does a multiply-subtract of q*m, correcting by at most one
;  add or subtract of m. Every step is branchless; only m's announced
;  length (public) drives control.
; ----------------------------------------------------------------------
Procedure BnMulAddSmall(x.i, z.i, m.i)
  Protected menc.i
  Protected mblr.i
  Protected mlen.i
  Protected hi.i
  Protected aHi.i
  Protected a.i
  Protected b.i
  Protected q.i
  Protected cc.i
  Protected tb.i
  Protected over.i
  Protected under.i
  Protected u.i
  Protected mw.i
  Protected zl.i
  Protected xw.i
  Protected nxw.i

  menc = BnGw(m, 0)
  If menc = 0
    ProcedureReturn
  EndIf
  If menc <= 15
    q = BnDivrem16((BnGw(x, 1) << 15) | z, BnGw(m, 1))
    BnSw(x, 1, BnRem)
    ProcedureReturn
  EndIf
  mlen = (menc + 15) >> 4
  mblr = menc & 15

  hi = BnGw(x, mlen)
  If mblr = 0
    aHi = BnGw(x, mlen)
    BnMoveUp(x, mlen)
    BnSw(x, 1, z)
    a = (aHi << 15) + BnGw(x, mlen)
    b = BnGw(m, mlen)
  Else
    aHi = (BnGw(x, mlen) << (15 - mblr)) | (BnGw(x, mlen - 1) >> mblr)
    BnMoveUp(x, mlen)
    BnSw(x, 1, z)
    a = (aHi << 15) | (((BnGw(x, mlen) << (15 - mblr)) | (BnGw(x, mlen - 1) >> mblr)) & $7FFF)
    b = (BnGw(m, mlen) << (15 - mblr)) | (BnGw(m, mlen - 1) >> mblr)
  EndIf
  q = BnDivrem16(a, b)

  q = BnMux(BnEq(b, aHi), $7FFF, q - 1 + (((q - 1) >> 63) & 1))

  cc = 0
  tb = 1
  u = 1
  While u <= mlen
    mw = BnGw(m, u)
    zl = mw * q + cc
    cc = (zl >> 15) & $1FFFF
    zl = zl & $7FFF
    xw = BnGw(x, u)
    nxw = xw - zl
    cc = cc + ((nxw >> 63) & 1)
    nxw = nxw & $7FFF
    BnSw(x, u, nxw)
    tb = BnMux(BnEq(nxw, mw), tb, BnGt(nxw, mw))
    u = u + 1
  Wend

  over = BnGt(cc, hi)
  under = (over ! 1) & (tb | BnLt(cc, hi))
  BnAdd(x, m, over)
  BnSub(x, m, under)
EndProcedure

; ----------------------------------------------------------------------
;  BnMulAcc(d, a, b) - d = d + a*b, plain (non-modular) schoolbook. d's
;  announced length starts equal to a's and grows to the sum of a's and
;  b's announced lengths. d must be disjoint from a and b.
; ----------------------------------------------------------------------
Procedure BnMulAcc(d.i, a.i, b.i)
  Protected alen.i
  Protected blen.i
  Protected dl.i
  Protected dh.i
  Protected u.i
  Protected v.i
  Protected f.i
  Protected cc.i
  Protected z.i
  Protected aenc.i
  Protected benc.i

  aenc = BnGw(a, 0)
  benc = BnGw(b, 0)
  alen = (aenc + 15) >> 4
  blen = (benc + 15) >> 4

  dl = (aenc & 15) + (benc & 15)
  dh = (aenc >> 4) + (benc >> 4)
  ; +1 when dl >= 15.  The 32-bit copies spell that as the sign bit of
  ; NOT(dl - 15), which needs the complement and the shift to be the
  ; same width; they are not here, and the 32-bit all-ones would leave
  ; bits 32..63 set on a negative dl - 15.  BnGe says the same thing in
  ; the core's own vocabulary.
  BnSw(d, 0, (dh << 4) + dl + BnGe(dl, 15))

  u = 0
  While u < blen
    f = BnGw(b, 1 + u)
    cc = 0
    v = 0
    While v < alen
      z = BnGw(d, 1 + u + v) + f * BnGw(a, 1 + v) + cc
      cc = (z >> 15) & $1FFFF
      BnSw(d, 1 + u + v, z & $7FFF)
      v = v + 1
    Wend
    BnSw(d, 1 + u + alen, cc)
    u = u + 1
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  BnMontmul(d, x, y, m, m0i) - Montgomery multiply: d = x*y/2^(15*len)
;  mod m, where len is m's value-word count and m0i = -1/m mod 2^15. x and
;  y must be lower than m and share its announced length; d is distinct.
;  The inner accumulation loop runs on raw pointers for speed; its sums
;  can set bit 31, so the >>15 carry is masked & $1FFFF (the true logical
;  shift). Nothing here branches on a value.
; ----------------------------------------------------------------------
Procedure BnMontmul(d.i, x.i, y.i, m.i, m0i.i)
  Protected menc.i
  Protected len.i
  Protected u.i
  Protected v.i
  Protected dh.i
  Protected xu.i
  Protected f.i
  Protected r.i
  Protected zh.i
  Protected z.i
  Protected dp.i
  Protected yp.i
  Protected mp.i
  Protected wp.i
  Protected c0.i

  menc = BnGw(m, 0)
  len = (menc + 15) >> 4
  BnZero(d, menc)
  dh = 0
  u = 0
  While u < len
    xu = BnGw(x, u + 1)
    f = ((BnGw(d, 1) + xu * BnGw(y, 1)) & $7FFF) * m0i
    f = f & $7FFF
    r = 0
    dp = d + 2                       ; &d[1] (16-bit words, 2 bytes each)
    yp = y + 2                       ; &y[1]
    mp = m + 2                       ; &m[1]
    wp = d                           ; &d[0], where d[v] is written
    v = 0
    While v < len
      z = PeekU(dp) + xu * PeekU(yp) + f * PeekU(mp) + r
      r = (z >> 15) & $1FFFF
      PokeW(wp, z & $7FFF)
      dp = dp + 2
      yp = yp + 2
      mp = mp + 2
      wp = wp + 2
      v = v + 1
    Wend
    zh = dh + r
    BnSw(d, len, zh & $7FFF)
    dh = (zh >> 15) & $1FFFF
    u = u + 1
  Wend
  BnSw(d, 0, menc)
  c0 = BnSub(d, m, 0)
  BnSub(d, m, BnNeq(dh, 0) | (c0 ! 1))
EndProcedure

; ----------------------------------------------------------------------
;  BnToMonty(x, m) - convert x into Montgomery representation (x*R mod m,
;  R = 2^(15*len)). x must be lower than m and share its announced length.
; ----------------------------------------------------------------------
Procedure BnToMonty(x.i, m.i)
  Protected k.i
  k = (BnGw(m, 0) + 15) >> 4
  While k > 0
    BnMulAddSmall(x, 0, m)
    k = k - 1
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  BnFromMonty(x, m, m0i) - convert x back out of Montgomery form.
; ----------------------------------------------------------------------
Procedure BnFromMonty(x.i, m.i, m0i.i)
  Protected len.i
  Protected u.i
  Protected v.i
  Protected f.i
  Protected cc.i
  Protected z.i
  Protected c0.i
  len = (BnGw(m, 0) + 15) >> 4
  u = 0
  While u < len
    f = (BnGw(x, 1) * m0i) & $7FFF
    cc = 0
    v = 0
    While v < len
      z = BnGw(x, v + 1) + f * BnGw(m, v + 1) + cc
      cc = (z >> 15) & $1FFFF
      If v <> 0
        BnSw(x, v, z & $7FFF)
      EndIf
      v = v + 1
    Wend
    BnSw(x, len, cc)
    u = u + 1
  Wend
  c0 = BnSub(x, m, 0)
  BnSub(x, m, c0 ! 1)
EndProcedure

; ----------------------------------------------------------------------
;  BnReduce(x, a, m) - x = a mod m, announced length set to m's. x must be
;  distinct from a and m. The comparison of announced lengths is public.
; ----------------------------------------------------------------------
Procedure BnReduce(x.i, a.i, m.i)
  Protected menc.i
  Protected mlen.i
  Protected aenc.i
  Protected alen.i
  Protected u.i
  Protected j.i
  Protected off.i
  menc = BnGw(m, 0)
  mlen = (menc + 15) >> 4
  BnSw(x, 0, menc)
  If menc = 0
    ProcedureReturn
  EndIf
  aenc = BnGw(a, 0)
  alen = (aenc + 15) >> 4
  If aenc < menc
    j = 0
    While j < alen
      BnSw(x, 1 + j, BnGw(a, 1 + j))
      j = j + 1
    Wend
    u = alen
    While u < mlen
      BnSw(x, u + 1, 0)
      u = u + 1
    Wend
    ProcedureReturn
  EndIf
  off = 2 + (alen - mlen)
  j = 0
  While j < mlen - 1
    BnSw(x, 1 + j, BnGw(a, off + j))
    j = j + 1
  Wend
  BnSw(x, mlen, 0)
  u = 1 + alen - mlen
  While u >= 1
    BnMulAddSmall(x, BnGw(a, u), m)
    u = u - 1
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  BnDecode(x, src, len) - big-endian byte string -> integer, computing
;  the true announced length. All len source bytes are consumed.
; ----------------------------------------------------------------------
Procedure BnDecode(x.i, src.i, len.i)
  Protected v.i
  Protected acc.i
  Protected acc_len.i
  Protected b.i
  v = 1
  acc = 0
  acc_len = 0
  While len > 0
    len = len - 1
    b = PeekA(src + len) & 255
    acc = acc | (b << acc_len)
    acc_len = acc_len + 8
    If acc_len >= 15
      BnSw(x, v, acc & $7FFF)
      v = v + 1
      acc_len = acc_len - 15
      acc = (acc >> 15) & $FFFF
    EndIf
  Wend
  If acc_len <> 0
    BnSw(x, v, acc)
    v = v + 1
  EndIf
  BnSw(x, 0, BnBitLength(x + 2, v - 1))
EndProcedure

; ----------------------------------------------------------------------
;  BnEncode(dst, len, x) - integer -> len big-endian bytes. A short len
;  truncates; a long one is zero-padded on the left.
; ----------------------------------------------------------------------
Procedure BnEncode(dst.i, len.i, x.i)
  Protected xlen.i
  Protected u.i
  Protected acc.i
  Protected acc_len.i
  Protected i.i
  xlen = (BnGw(x, 0) + 15) >> 4
  If xlen = 0
    i = 0
    While i < len
      PokeB(dst + i, 0)
      i = i + 1
    Wend
    ProcedureReturn
  EndIf
  u = 1
  acc = 0
  acc_len = 0
  While len > 0
    len = len - 1
    If acc_len < 8
      If u <= xlen
        acc = acc + (BnGw(x, u) << acc_len)
        u = u + 1
      EndIf
      acc_len = acc_len + 15
    EndIf
    PokeB(dst + len, acc & 255)
    acc = (acc >> 8) & $FFFFFF
    acc_len = acc_len - 8
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  BnDecodeReduce(x, src, len, m) - decode a big-endian byte string and
;  reduce it modulo m in one pass; announced length set to m's. The bulk
;  of the bytes decode directly, the remainder is injected 15 bits at a
;  time through BnMulAddSmall.
; ----------------------------------------------------------------------
Procedure BnDecodeReduce(x.i, src.i, len.i, m.i)
  Protected menc.i
  Protected idx.i
  Protected mrbits.i
  Protected mblen.i
  Protected k.i
  Protected acc.i
  Protected acc_len.i
  Protected v.i
  Protected zval.i
  menc = BnGw(m, 0)
  If menc = 0
    BnSw(x, 0, 0)
    ProcedureReturn
  EndIf
  BnZero(x, menc)
  idx = menc >> 4
  mrbits = (menc & 15) + (idx << 4) - idx
  mblen = (mrbits + 7) >> 3
  k = mblen - 1
  If k >= len
    BnDecode(x, src, len)
    BnSw(x, 0, menc)
    ProcedureReturn
  EndIf
  BnDecode(x, src, k)
  BnSw(x, 0, menc)
  acc = 0
  acc_len = 0
  While k < len
    v = PeekA(src + k) & 255
    k = k + 1
    acc = (acc << 8) | v
    acc_len = acc_len + 8
    If acc_len >= 15
      zval = (acc >> (acc_len - 15)) & $7FFF
      BnMulAddSmall(x, zval, m)
      acc_len = acc_len - 15
      acc = acc & ((1 << acc_len) - 1)
    EndIf
  Wend
  If acc_len <> 0
    acc = (acc | (BnGw(x, 1) << acc_len)) & $7FFF
    BnRshift(x, 15 - acc_len)
    BnMulAddSmall(x, acc, m)
  EndIf
EndProcedure

; ----------------------------------------------------------------------
;  BnCopyWords(dst, src, n) - copy n whole limbs (word 0 included, so the
;  announced length travels with the value).
; ----------------------------------------------------------------------
Procedure BnCopyWords(dst.i, src.i, n.i)
  Protected i.i
  i = 0
  While i < n
    BnSw(dst, i, BnGw(src, i))
    i = i + 1
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  BnCcopy(ctl, dst, src, n) - constant-time conditional copy of n limbs:
;  dst becomes src when ctl = 1, is left as-is when ctl = 0. It always
;  reads and writes every word, selecting through a mask, so the timing
;  and access pattern never depend on ctl (the secret exponent bit).
; ----------------------------------------------------------------------
Procedure BnCcopy(ctl.i, dst.i, src.i, n.i)
  Protected i.i
  Protected mask.i
  Protected dv.i
  Protected sv.i
  mask = 0 - ctl
  i = 0
  While i < n
    dv = BnGw(dst, i)
    sv = BnGw(src, i)
    BnSw(dst, i, dv ! (mask & (dv ! sv)))
    i = i + 1
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  BnModpow(x, e, elen, m, m0i, t1, t2) - x = x^e mod m by a Montgomery
;  ladder: a fixed two multiplies per exponent bit, the result word kept
;  by a constant-time conditional copy. e is a big-endian byte buffer of
;  elen bytes. t1 and t2 are scratch each (m[0]+31)>>4 words wide. x holds
;  the base on entry and the result on exit, both in normal domain.
;
;  Constant-time: the access pattern and the two multiplies are the same
;  for every bit; only the CCOPY mask carries the (secret) bit value.
; ----------------------------------------------------------------------
Procedure BnModpow(x.i, e.i, elen.i, m.i, m0i.i, t1.i, t2.i)
  Protected wp1.i
  Protected kbits.i
  Protected k.i
  Protected ctl.i
  Protected byte.i
  wp1 = (BnGw(m, 0) + 31) >> 4
  BnCopyWords(t1, x, wp1)
  BnToMonty(t1, m)
  BnZero(x, BnGw(m, 0))
  BnSw(x, 1, 1)
  kbits = elen << 3
  k = 0
  While k < kbits
    byte = PeekA(e + (elen - 1 - (k >> 3))) & 255
    ctl = (byte >> (k & 7)) & 1
    BnMontmul(t2, x, t1, m, m0i)
    BnCcopy(ctl, x, t2, wp1)
    BnMontmul(t2, t1, t1, m, m0i)
    BnCopyWords(t1, t2, wp1)
    k = k + 1
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  BnModpow2(x, e, elen, m, m0i, tmp, twlen) - windowed modular
;  exponentiation. tmp is a scratch area of twlen 16-bit words; the window
;  size (up to 5 bits) is chosen from how much scratch is provided. A
;  window of k bits needs (2^k + 1) strides; the fallback of 1 bit needs
;  two. Returns 1 on success, 0 if tmp is too small. x holds the base on
;  entry and the result on exit. Constant-time in the exponent value.
; ----------------------------------------------------------------------
Procedure.i BnModpow2(x.i, e.i, elen.i, m.i, m0i.i, tmp.i, twlen.i)
  Protected menc.i
  Protected cw.i
  Protected stride.i
  Protected t1.i
  Protected t2.i
  Protected base.i
  Protected win_len.i
  Protected found.i
  Protected u.i
  Protected v.i
  Protected k.i
  Protected i.i
  Protected acc.i
  Protected acc_len.i
  Protected bits.i
  Protected mask.i

  menc = BnGw(m, 0)
  cw = (menc + 31) >> 4
  stride = cw
  If (stride & 1) <> 0
    stride = stride + 1
  EndIf
  t1 = tmp
  t2 = tmp + (stride << 1)

  If twlen < (stride << 1)
    ProcedureReturn 0
  EndIf
  win_len = 5
  found = 0
  While win_len > 1 And found = 0
    If (((1 << win_len) + 1) * stride) <= twlen
      found = 1
    Else
      win_len = win_len - 1
    EndIf
  Wend

  BnToMonty(x, m)

  If win_len = 1
    BnCopyWords(t2, x, cw)
  Else
    BnCopyWords(t2 + (stride << 1), x, cw)
    base = t2 + (stride << 1)
    u = 2
    While u < (1 << win_len)
      BnMontmul(base + (stride << 1), base, x, m, m0i)
      base = base + (stride << 1)
      u = u + 1
    Wend
  EndIf

  BnZero(x, menc)
  BnSw(x, (menc + 15) >> 4, 1)
  BnMulAddSmall(x, 0, m)

  acc = 0
  acc_len = 0
  While acc_len > 0 Or elen > 0
    k = win_len
    If acc_len < win_len
      If elen > 0
        acc = (acc << 8) | (PeekA(e) & 255)
        e = e + 1
        elen = elen - 1
        acc_len = acc_len + 8
      Else
        k = acc_len
      EndIf
    EndIf
    bits = (acc >> (acc_len - k)) & ((1 << k) - 1)
    acc_len = acc_len - k

    i = 0
    While i < k
      BnMontmul(t1, x, x, m, m0i)
      BnCopyWords(x, t1, cw)
      i = i + 1
    Wend

    If win_len > 1
      BnZero(t2, menc)
      base = t2 + (stride << 1)
      u = 1
      While u < (1 << k)
        mask = 0 - BnEq(u, bits)
        v = 1
        While v < stride
          BnSw(t2, v, BnGw(t2, v) | (mask & BnGw(base, v)))
          v = v + 1
        Wend
        base = base + (stride << 1)
        u = u + 1
      Wend
    EndIf

    BnMontmul(t1, x, t2, m, m0i)
    BnCcopy(BnNeq(bits, 0), x, t1, cw)
  Wend

  BnFromMonty(x, m, m0i)
  ProcedureReturn 1
EndProcedure

; ==== PORTABLE CORE A64 END ====

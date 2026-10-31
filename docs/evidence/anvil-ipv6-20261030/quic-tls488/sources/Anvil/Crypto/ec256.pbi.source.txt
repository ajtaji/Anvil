; ======================================================================
;  ec256.pi4 - P-256 (secp256r1) scalar multiplication, ON THE
;              RASPBERRY PI 4 (BCM2711, AArch64)
; ======================================================================
;
;  Translated from BearSSL (c) 2017 Thomas Pornin - MIT licence.
;  The notice ships as licenses/BearSSL-LICENSE.txt (release condition).
;
;     XIncludeFile "RaspberryPi4/Lib/bignum.pi4"    ; REQUIRED, before this
;     XIncludeFile "RaspberryPi4/Lib/ec256.pi4"
;
;  The ECDH scalar-multiply primitive on the NIST P-256 curve, translated
;  from the BearSSL generic-prime "ec_prime_i15" core.  Reads-and-
;  translates only: no C is linked, no foreign ABI is followed.
;
;  REQUIRES bignum.pi4 FIRST.  This library is built on the i15
;  big-integer core and calls its Bn* procedures (BnMontmul, BnAdd,
;  BnSub, BnModpow, BnReduce, BnDecode, BnEncode, BnIsZero, BnCcopy,
;  BnCopyWords, BnZero, BnGw, BnSw, BnEq, BnNeq, BnNot).  A library never
;  includes a library (house rule): the MAIN file lists them, in order.
;  EcInit() must be called once before any other Ec procedure.  A missing
;  dependency fails loudly at compile time (undefined procedure).
;
;  API (points are uncompressed 0x04 || X || Y, 65 bytes; scalars are
;  big-endian byte buffers; X and Y are each 32 big-endian bytes):
;    EcInit()                       load curve constants once, at startup
;    EcP256Mul(pt.i, ptlen.i, sec.i, seclen.i)
;                                   pt = sec * pt, IN PLACE (65 bytes);
;                                   returns 1 if the input point was a
;                                   valid on-curve uncompressed point,
;                                   else 0.  The ECDH shared secret is
;                                   the X coordinate, pt[1..32], after
;                                   the multiply by the private scalar.
;    EcP256Mulgen(dst.i, sec.i, seclen.i)
;                                   dst = sec * G (the curve generator),
;                                   65 bytes; returns the point length 65.
;
;  > THE VERDICT OF EcP256Mul IS 1 OR 0 AND MUST BE TESTED AS `= 1`.
;  > It is a flag, not a mask - unlike GcmDecrypt's, which is a mask and
;  > must be tested as `= $FFFFFFFF`.  Two verdict conventions in one
;  > crypto family is a trap, so it is written here as well as there.
;
;  CONSTANT TIME.  The scalar multiply is a fixed double-and-add ladder
;  with a 2-bit window: for every scalar byte it performs exactly two
;  doublings and one addition per window, and selects the addend and the
;  running point with branchless mask copies, never with a branch or an
;  index derived from the scalar.  The formula interpreter branches only
;  on the PUBLIC opcode.  EC leaks the private key otherwise, so this
;  shape is the whole point.  Field inversion (only in the final affine
;  conversion) uses the constant-time BnModpow ladder.
;
;  THIS FILE RELIES ON EnableExplicit being ON (bignum.pi4 turns it on
;  for the whole program).
;
;  This is the GENERIC-PRIME core (the BearSSL "ec_prime_i15" path).  A
;  P-256-specialised speed path behind this same API is a later
;  per-family optimisation; it is NOT in this module.
;
;  ======================================================================
;   .i IS 64 BITS HERE.  THE FOUR-SHAPE AUDIT
;  ======================================================================
;
;  SHAPE 1 - AN ARRAY ELEMENT IS EIGHT BYTES, NOT FOUR.
;      LOOKED FOR, AND THE FILE WAS ALREADY SAFE.  Every array here is
;      declared `.w` (16-bit) or `.a` (8-bit), and both are the same
;      width on this part as on a Pico - only `.i`, `.l` and `.n` change.
;      That matters more than it looks: EcRegP and EcCoord do their own
;      address arithmetic (`r * (#EC_WORDS << 1)`) on the assumption
;      that a word is two bytes, and a single `.i` array among them
;      would have made every register address wrong by a factor of four
;      while still compiling.  THE DECLARATIONS ARE LOAD-BEARING AND
;      MUST NOT BE "TIDIED" TO `.i`.  Mutation M1 in the gate is exactly
;      that tidy-up.
;
;  SHAPE 2 - PeekL SIGN-EXTENDS.
;      NOT PRESENT.  Words come in through PeekU and bytes through
;      PeekA; there is no PeekL and no PeekB outside the `Read.b`
;      DataSection walk, which masks every byte with `& 255`.
;
;  SHAPE 3 - `<<` DOES NOT DISCARD AT BIT 31.
;      NOT PRESENT.  The only shifts here build 16-bit opcodes (at most
;      `<< 12`), index arrays, or extract two scalar bits.  All the
;      field arithmetic is delegated to bignum.pi4, which carries its
;      own audit.
;
;  SHAPE 4 - A 32-BIT COUNTER NEVER WRAPS.
;      NOT PRESENT.
;
;  ---- THE FIFTH SHAPE, AND IT IS HERE TWICE -------------------------
;
;  `x ! $FFFFFFFF` AS A LOGICAL NOT.  This is the complement half of the
;  tag-verdict defect: XOR-ing a 64-bit value against a 32-bit all-ones
;  leaves bits 32..63 untouched, which is how GcmDecrypt came to return
;  $FFFFFFFF00000000 for a forged tag.  The 32-bit copies use it twice,
;  and BOTH of them are in the point-validity path:
;
;      RunCode   r = r & (BnIsZero(dp) ! $FFFFFFFF)      the MTZ flag
;      EcPointDecode
;                r = r & (RunCode(... EcCodeChk) ! $FFFFFFFF)
;                                                   the on-curve verdict
;
;  BOTH STILL PRODUCE THE RIGHT ANSWER unchanged, because r is 0 or 1
;  and only bit 0 is ever read - and both are written as BnNot() here
;  anyway.  The argument for rewriting a line that works is that a
;  reader cannot tell this instance of the shape from the fatal one
;  without redoing the analysis, and the thing being decided is whether
;  an attacker-chosen point is on the curve.  The gate carries both
;  reversions as mutations and records them as EXPECTED SURVIVORS with
;  this argument, so a future reader gets the measurement rather than
;  the assertion.
;
;  ---- WHAT IS *NOT* DIFFERENT, AND IS WORTH SAYING -----------------
;
;  Nothing else in this file changed at all.  That is a consequence of
;  where the width lives: ec256 is pointer arithmetic, opcode dispatch
;  and calls into bignum, and every quantity it computes itself is
;  either an address or a value under 2^16.  The width question was
;  paid for once, in bignum.pi4.
;
;  PROVEN: builds clean for pi4 and passes tools/a64/a64_ec_check.py on
;  the SAME vectors as the three 32-bit families (the gate imports
;  tools/gen_ec_vectors.py rather than carrying a copy) - NIST CAVP ECDH
;  and point-multiply, the generator KAT, and the off-curve /
;  wrong-prefix / coordinate >= p / point-at-infinity negatives -
;  cycle-equal under that gate's --timing, mutation-swept under
;  --mutate, and structurally twinned under
;  tools/check_tls_twins.py --cross ec256.
;  NOTHING HERE HAS RUN ON SILICON.
; ======================================================================
; ==== PORTABLE CORE A64 BEGIN ====

; 20 16-bit words per field element: word 0 is the announced bit length,
; words 1..18 are the 15-bit value limbs of a 256-bit number, word 19 is
; a guard. A P-256 field element announces 273 bits (18 limbs).
#EC_WORDS  = 20
#EC_PWORDS = 18
#EC_MENC   = 273                     ; (17 << 4) + 1, P-256 announced length
#EC_P0I    = 1                       ; -1/p mod 2^15 for P-256

; Register indices of the little formula interpreter (matches the source).
#EcP1x = 0
#EcP1y = 1
#EcP1z = 2
#EcP2x = 3
#EcP2y = 4
#EcP2z = 5
#EcT1  = 6
#EcT2  = 7
#EcT3  = 8
#EcT4  = 9
#EcT5  = 10
#EcT6  = 11
#EcT7  = 12

; Curve constants, in i15 limb form (word 0 + 18 limbs).
Global Dim EcConstP.w[#EC_WORDS]      ; field prime p
Global Dim EcConstR2.w[#EC_WORDS]     ; R^2 mod p
Global Dim EcConstB.w[#EC_WORDS]      ; b*R mod p (Montgomery form of b)
Global Dim EcGen.a[65]                ; uncompressed generator 0x04||Gx||Gy
Global Dim EcExp.a[32]                ; p-2, big-endian, the inversion exponent

; The 13 interpreter registers, contiguous.
Global Dim EcRegs.w[13 * #EC_WORDS]

; The four formula programs (opcode streams), built once by EcInit.
Global Dim EcCodeDbl.w[48]
Global Dim EcCodeAdd.w[80]
Global Dim EcCodeChk.w[48]
Global Dim EcCodeAff.w[48]

; Ladder working points (each three field elements: x, y, z).
Global Dim EcWork.w[3 * #EC_WORDS]    ; the point being multiplied
Global Dim EcQpt.w[3 * #EC_WORDS]     ; running accumulator Q
Global Dim EcP2pt.w[3 * #EC_WORDS]    ; 2P
Global Dim EcP3pt.w[3 * #EC_WORDS]    ; 3P
Global Dim EcTpt.w[3 * #EC_WORDS]     ; ladder scratch T
Global Dim EcUpt.w[3 * #EC_WORDS]     ; ladder scratch U
Global Dim EcCheckQ.w[3 * #EC_WORDS]  ; the (R2, b*R, 1) point for on-curve check
Global Dim EcAffT.w[3 * #EC_WORDS]    ; the (_, _, 1) point for affine convert

; Decode scratch: raw 256-bit value and a copy for the < p comparison.
Global Dim EcRaw.w[#EC_WORDS]
Global Dim EcRaw2.w[#EC_WORDS]

Global EcEmitP.i                      ; byte cursor while building a program

; ----------------------------------------------------------------------
;  Address of interpreter register r (16-bit words, 2 bytes each).
; ----------------------------------------------------------------------
Procedure.i EcRegP(r.i)
  ProcedureReturn @EcRegs + r * (#EC_WORDS << 1)
EndProcedure

; ----------------------------------------------------------------------
;  Address of coordinate c (0=x,1=y,2=z) of a point at base pt.
; ----------------------------------------------------------------------
Procedure.i EcCoord(pt.i, c.i)
  ProcedureReturn pt + c * (#EC_WORDS << 1)
EndProcedure

; ----------------------------------------------------------------------
;  Opcode encoders (mirroring the source's MSET/MADD/... macros).
; ----------------------------------------------------------------------
Procedure.i OpMSET(d.i, a.i)
  ProcedureReturn (d << 8) + (a << 4)
EndProcedure
Procedure.i OpMADD(d.i, a.i)
  ProcedureReturn $1000 + (d << 8) + (a << 4)
EndProcedure
Procedure.i OpMSUB(d.i, a.i)
  ProcedureReturn $2000 + (d << 8) + (a << 4)
EndProcedure
Procedure.i OpMMUL(d.i, a.i, b.i)
  ProcedureReturn $3000 + (d << 8) + (a << 4) + b
EndProcedure
Procedure.i OpMINV(d.i, a.i, b.i)
  ProcedureReturn $4000 + (d << 8) + (a << 4) + b
EndProcedure
Procedure.i OpMTZ(d.i)
  ProcedureReturn $5000 + (d << 8)
EndProcedure

Procedure Emit(arr.i, op.i)
  PokeW(arr + EcEmitP, op & $FFFF)
  EcEmitP = EcEmitP + 2
EndProcedure

; ----------------------------------------------------------------------
;  Read n 16-bit words from the Data cursor as low/high byte pairs into a
;  word array (longhand, width-explicit; avoids any wide-Read stepping).
; ----------------------------------------------------------------------
Procedure EcReadWords(dst.i, n.i)
  Protected i.i
  Protected lo.i
  Protected hi.i
  i = 0
  While i < n
    Read.b lo
    Read.b hi
    PokeW(dst + (i << 1), ((lo & 255) | ((hi & 255) << 8)) & $FFFF)
    i = i + 1
  Wend
EndProcedure

Procedure EcReadBytes(dst.i, n.i)
  Protected i.i
  Protected bb.i
  i = 0
  While i < n
    Read.b bb
    PokeB(dst + i, bb & 255)
    i = i + 1
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  Modular field operations on interpreter registers (absolute pointers).
;  These are the six primitives the interpreter dispatches to; p is the
;  P-256 field prime, p0i = 1.
; ----------------------------------------------------------------------

; d = d + a mod p
Procedure EcMAdd(dp.i, ap.i)
  Protected ctl.i
  ctl = BnAdd(dp, ap, 1)
  ctl = ctl | BnNot(BnSub(dp, @EcConstP, 0))
  BnSub(dp, @EcConstP, ctl)
EndProcedure

; d = d - a mod p
Procedure EcMSub(dp.i, ap.i)
  BnAdd(dp, @EcConstP, BnSub(dp, ap, 1))
EndProcedure

; ----------------------------------------------------------------------
;  RunCode - the formula interpreter. Copies P1 and P2 into the register
;  file, executes the opcode stream at codeptr, copies P1 back, and
;  returns the accumulated flag (cleared by any MTZ whose operand is
;  zero). Control flow depends only on the PUBLIC opcodes.
; ----------------------------------------------------------------------
Procedure.i RunCode(p1.i, p2.i, codeptr.i)
  Protected r.i
  Protected u.i
  Protected op.i
  Protected d.i
  Protected a.i
  Protected b.i
  Protected opc.i
  Protected dp.i
  Protected ap.i
  Protected bp.i

  BnCopyWords(EcRegP(#EcP1x), EcCoord(p1, 0), 3 * #EC_WORDS)
  BnCopyWords(EcRegP(#EcP2x), EcCoord(p2, 0), 3 * #EC_WORDS)

  r = 1
  u = 0
  Repeat
    op = PeekU(codeptr + (u << 1))
    If op = 0
      Break
    EndIf
    d = (op >> 8) & $0F
    a = (op >> 4) & $0F
    b = op & $0F
    opc = (op >> 12) & $0F
    dp = EcRegP(d)
    ap = EcRegP(a)
    bp = EcRegP(b)
    If opc = 0
      BnCopyWords(dp, ap, #EC_WORDS)
    ElseIf opc = 1
      EcMAdd(dp, ap)
    ElseIf opc = 2
      EcMSub(dp, ap)
    ElseIf opc = 3
      BnMontmul(dp, ap, bp, @EcConstP, #EC_P0I)
    ElseIf opc = 4
      BnModpow(dp, @EcExp, 32, @EcConstP, #EC_P0I, ap, bp)
    Else
      r = r & BnNot(BnIsZero(dp))
    EndIf
    u = u + 1
  ForEver

  BnCopyWords(EcCoord(p1, 0), EcRegP(#EcP1x), 3 * #EC_WORDS)
  ProcedureReturn r
EndProcedure

; ----------------------------------------------------------------------
;  Point helpers.
; ----------------------------------------------------------------------

; Set a point to the point at infinity (all limbs zero, each announced).
Procedure EcPointZero(pt.i)
  BnZero(EcCoord(pt, 0), #EC_MENC)
  BnZero(EcCoord(pt, 1), #EC_MENC)
  BnZero(EcCoord(pt, 2), #EC_MENC)
EndProcedure

; Set a field element to 1 (normal representation).
Procedure EcSetOne(x.i)
  BnZero(x, #EC_MENC)
  BnSw(x, 1, 1)
EndProcedure

Procedure EcPointCopy(dst.i, src.i)
  BnCopyWords(dst, src, 3 * #EC_WORDS)
EndProcedure

; Constant-time conditional copy of a whole point: dst <- src when ctl=1.
Procedure EcPointCcopy(ctl.i, dst.i, src.i)
  BnCcopy(ctl, dst, src, 3 * #EC_WORDS)
EndProcedure

Procedure EcPointDouble(pt.i)
  RunCode(pt, pt, @EcCodeDbl)
EndProcedure

Procedure.i EcPointAdd(p1.i, p2.i)
  ProcedureReturn RunCode(p1, p2, @EcCodeAdd)
EndProcedure

; ----------------------------------------------------------------------
;  EcDecodeCoord - decode 32 big-endian bytes at src into a field element
;  reduced mod p, and return 1 if the raw value was already < p (a valid,
;  canonically encoded coordinate), else 0.
; ----------------------------------------------------------------------
Procedure.i EcDecodeCoord(dst.i, src.i)
  Protected i.i
  Protected borrow.i
  i = 0
  While i <= #EC_PWORDS + 1
    BnSw(@EcRaw, i, 0)
    i = i + 1
  Wend
  BnDecode(@EcRaw, src, 32)
  BnCopyWords(@EcRaw2, @EcRaw, #EC_WORDS)
  BnSw(@EcRaw2, 0, #EC_MENC)          ; announce full width for the compare
  borrow = BnSub(@EcRaw2, @EcConstP, 0)
  BnReduce(dst, @EcRaw, @EcConstP)
  ProcedureReturn borrow
EndProcedure

; ----------------------------------------------------------------------
;  EcPointDecode - decode an uncompressed 0x04||X||Y point (65 bytes) at
;  src into pt (Jacobian, Montgomery x/y after the on-curve check). Does
;  not support the point at infinity. Returns 1 if the point is a valid
;  on-curve point, else 0 (the coordinates are still well-formed).
; ----------------------------------------------------------------------
Procedure.i EcPointDecode(pt.i, src.i, len.i)
  Protected r.i
  EcPointZero(pt)
  If len <> 65
    ProcedureReturn 0
  EndIf
  r = EcDecodeCoord(EcCoord(pt, 0), src + 1)
  r = r & EcDecodeCoord(EcCoord(pt, 1), src + 1 + 32)
  r = r & BnEq(PeekA(src) & 255, $04)

  ; Q = (R2, b*R, 1); on-curve check converts x,y to Montgomery and
  ; verifies y^2 = x^3 - 3x + b, clearing the flag on failure.
  BnCopyWords(EcCoord(@EcCheckQ, 0), @EcConstR2, #EC_WORDS)
  BnCopyWords(EcCoord(@EcCheckQ, 1), @EcConstB, #EC_WORDS)
  EcSetOne(EcCoord(@EcCheckQ, 2))
  r = r & BnNot(RunCode(pt, @EcCheckQ, @EcCodeChk))
  ProcedureReturn r
EndProcedure

; ----------------------------------------------------------------------
;  EcPointEncode - convert pt to affine and write 0x04||X||Y (65 bytes)
;  at dst. Assumes pt is a correct, non-infinity point.
; ----------------------------------------------------------------------
Procedure EcPointEncode(dst.i, pt.i)
  PokeB(dst, $04)
  EcPointCopy(@EcAffT, pt)            ; reuse EcAffT to hold Q = copy of pt
  ; the affine code needs P2z = 1 (normal); build that in EcCheckQ.
  EcSetOne(EcCoord(@EcCheckQ, 2))
  RunCode(@EcAffT, @EcCheckQ, @EcCodeAff)
  BnEncode(dst + 1, 32, EcCoord(@EcAffT, 0))
  BnEncode(dst + 1 + 32, 32, EcCoord(@EcAffT, 1))
EndProcedure

; ----------------------------------------------------------------------
;  EcPointMul - the constant-time scalar multiply: pt = sec * pt, with
;  sec a big-endian byte buffer of seclen bytes. Double-and-add ladder
;  with a 2-bit window; two doublings and one addition per window, the
;  addend and the running point selected by branchless mask copies.
; ----------------------------------------------------------------------
Procedure EcPointMul(pt.i, sec.i, seclen.i)
  Protected qz.i
  Protected idx.i
  Protected k.i
  Protected secByte.i
  Protected secBits.i
  Protected bnz.i

  EcPointCopy(@EcP2pt, pt)
  EcPointDouble(@EcP2pt)             ; 2P
  EcPointCopy(@EcP3pt, pt)
  EcPointAdd(@EcP3pt, @EcP2pt)       ; 3P

  EcPointZero(@EcQpt)
  qz = 1
  idx = 0
  While idx < seclen
    secByte = PeekA(sec + idx) & 255
    k = 6
    While k >= 0
      EcPointDouble(@EcQpt)
      EcPointDouble(@EcQpt)
      EcPointCopy(@EcTpt, pt)
      EcPointCopy(@EcUpt, @EcQpt)
      secBits = (secByte >> k) & 3
      bnz = BnNeq(secBits, 0)
      EcPointCcopy(BnEq(secBits, 2), @EcTpt, @EcP2pt)
      EcPointCcopy(BnEq(secBits, 3), @EcTpt, @EcP3pt)
      EcPointAdd(@EcUpt, @EcTpt)
      EcPointCcopy(bnz & qz, @EcQpt, @EcTpt)
      EcPointCcopy(bnz & BnNot(qz), @EcQpt, @EcUpt)
      qz = qz & BnNot(bnz)
      k = k - 2
    Wend
    idx = idx + 1
  Wend
  EcPointCopy(pt, @EcQpt)
EndProcedure

; ----------------------------------------------------------------------
;  EcP256Mul(pt, ptlen, sec, seclen) - pt = sec * pt in place. Returns 1
;  if the input point was valid on-curve, else 0. The ECDH shared secret
;  is the resulting X coordinate, pt[1..32].
; ----------------------------------------------------------------------
Procedure.i EcP256Mul(pt.i, ptlen.i, sec.i, seclen.i)
  Protected r.i
  If ptlen <> 65
    ProcedureReturn 0
  EndIf
  r = EcPointDecode(@EcWork, pt, ptlen)
  EcPointMul(@EcWork, sec, seclen)
  EcPointEncode(pt, @EcWork)
  ProcedureReturn r
EndProcedure

; ----------------------------------------------------------------------
;  EcP256Mulgen(dst, sec, seclen) - dst = sec * G. Returns 65.
; ----------------------------------------------------------------------
Procedure.i EcP256Mulgen(dst.i, sec.i, seclen.i)
  Protected i.i
  i = 0
  While i < 65
    PokeB(dst + i, PeekA(@EcGen + i) & 255)
    i = i + 1
  Wend
  EcP256Mul(dst, 65, sec, seclen)
  ProcedureReturn 65
EndProcedure

; ----------------------------------------------------------------------
;  EcInit - load the curve constants and build the four formula programs.
;  Call once before any other Ec procedure.
; ----------------------------------------------------------------------
Procedure EcInit()
  ; Curve constants (limb form, word 0 + 18 limbs).
  Restore EcDataP
  EcReadWords(@EcConstP, #EC_WORDS - 1)
  Restore EcDataR2
  EcReadWords(@EcConstR2, #EC_WORDS - 1)
  Restore EcDataB
  EcReadWords(@EcConstB, #EC_WORDS - 1)
  Restore EcDataGen
  EcReadBytes(@EcGen, 65)

  ; Inversion exponent p-2 (big-endian, 32 bytes).
  BnEncode(@EcExp, 32, @EcConstP)
  PokeB(@EcExp + 31, (PeekA(@EcExp + 31) & 255) - 2)

  ; code_double
  EcEmitP = 0
  Emit(@EcCodeDbl, OpMMUL(#EcT1, #EcP1z, #EcP1z))
  Emit(@EcCodeDbl, OpMSET(#EcT2, #EcP1x))
  Emit(@EcCodeDbl, OpMSUB(#EcT2, #EcT1))
  Emit(@EcCodeDbl, OpMADD(#EcT1, #EcP1x))
  Emit(@EcCodeDbl, OpMMUL(#EcT3, #EcT1, #EcT2))
  Emit(@EcCodeDbl, OpMSET(#EcT1, #EcT3))
  Emit(@EcCodeDbl, OpMADD(#EcT1, #EcT3))
  Emit(@EcCodeDbl, OpMADD(#EcT1, #EcT3))
  Emit(@EcCodeDbl, OpMMUL(#EcT3, #EcP1y, #EcP1y))
  Emit(@EcCodeDbl, OpMADD(#EcT3, #EcT3))
  Emit(@EcCodeDbl, OpMMUL(#EcT2, #EcP1x, #EcT3))
  Emit(@EcCodeDbl, OpMADD(#EcT2, #EcT2))
  Emit(@EcCodeDbl, OpMMUL(#EcP1x, #EcT1, #EcT1))
  Emit(@EcCodeDbl, OpMSUB(#EcP1x, #EcT2))
  Emit(@EcCodeDbl, OpMSUB(#EcP1x, #EcT2))
  Emit(@EcCodeDbl, OpMMUL(#EcT4, #EcP1y, #EcP1z))
  Emit(@EcCodeDbl, OpMSET(#EcP1z, #EcT4))
  Emit(@EcCodeDbl, OpMADD(#EcP1z, #EcT4))
  Emit(@EcCodeDbl, OpMSUB(#EcT2, #EcP1x))
  Emit(@EcCodeDbl, OpMMUL(#EcP1y, #EcT1, #EcT2))
  Emit(@EcCodeDbl, OpMMUL(#EcT4, #EcT3, #EcT3))
  Emit(@EcCodeDbl, OpMSUB(#EcP1y, #EcT4))
  Emit(@EcCodeDbl, OpMSUB(#EcP1y, #EcT4))
  Emit(@EcCodeDbl, 0)

  ; code_add
  EcEmitP = 0
  Emit(@EcCodeAdd, OpMMUL(#EcT3, #EcP2z, #EcP2z))
  Emit(@EcCodeAdd, OpMMUL(#EcT1, #EcP1x, #EcT3))
  Emit(@EcCodeAdd, OpMMUL(#EcT4, #EcP2z, #EcT3))
  Emit(@EcCodeAdd, OpMMUL(#EcT3, #EcP1y, #EcT4))
  Emit(@EcCodeAdd, OpMMUL(#EcT4, #EcP1z, #EcP1z))
  Emit(@EcCodeAdd, OpMMUL(#EcT2, #EcP2x, #EcT4))
  Emit(@EcCodeAdd, OpMMUL(#EcT5, #EcP1z, #EcT4))
  Emit(@EcCodeAdd, OpMMUL(#EcT4, #EcP2y, #EcT5))
  Emit(@EcCodeAdd, OpMSUB(#EcT2, #EcT1))
  Emit(@EcCodeAdd, OpMSUB(#EcT4, #EcT3))
  Emit(@EcCodeAdd, OpMTZ(#EcT4))
  Emit(@EcCodeAdd, OpMMUL(#EcT7, #EcT2, #EcT2))
  Emit(@EcCodeAdd, OpMMUL(#EcT6, #EcT1, #EcT7))
  Emit(@EcCodeAdd, OpMMUL(#EcT5, #EcT7, #EcT2))
  Emit(@EcCodeAdd, OpMMUL(#EcP1x, #EcT4, #EcT4))
  Emit(@EcCodeAdd, OpMSUB(#EcP1x, #EcT5))
  Emit(@EcCodeAdd, OpMSUB(#EcP1x, #EcT6))
  Emit(@EcCodeAdd, OpMSUB(#EcP1x, #EcT6))
  Emit(@EcCodeAdd, OpMSUB(#EcT6, #EcP1x))
  Emit(@EcCodeAdd, OpMMUL(#EcP1y, #EcT4, #EcT6))
  Emit(@EcCodeAdd, OpMMUL(#EcT1, #EcT5, #EcT3))
  Emit(@EcCodeAdd, OpMSUB(#EcP1y, #EcT1))
  Emit(@EcCodeAdd, OpMMUL(#EcT1, #EcP1z, #EcP2z))
  Emit(@EcCodeAdd, OpMMUL(#EcP1z, #EcT1, #EcT2))
  Emit(@EcCodeAdd, 0)

  ; code_check
  EcEmitP = 0
  Emit(@EcCodeChk, OpMMUL(#EcT1, #EcP1x, #EcP2x))
  Emit(@EcCodeChk, OpMMUL(#EcT2, #EcP1y, #EcP2x))
  Emit(@EcCodeChk, OpMSET(#EcP1x, #EcT1))
  Emit(@EcCodeChk, OpMSET(#EcP1y, #EcT2))
  Emit(@EcCodeChk, OpMMUL(#EcT2, #EcP1x, #EcP1x))
  Emit(@EcCodeChk, OpMMUL(#EcT1, #EcP1x, #EcT2))
  Emit(@EcCodeChk, OpMSUB(#EcT1, #EcP1x))
  Emit(@EcCodeChk, OpMSUB(#EcT1, #EcP1x))
  Emit(@EcCodeChk, OpMSUB(#EcT1, #EcP1x))
  Emit(@EcCodeChk, OpMADD(#EcT1, #EcP2y))
  Emit(@EcCodeChk, OpMMUL(#EcT2, #EcP1y, #EcP1y))
  Emit(@EcCodeChk, OpMSUB(#EcT1, #EcT2))
  Emit(@EcCodeChk, OpMTZ(#EcT1))
  Emit(@EcCodeChk, OpMMUL(#EcP1z, #EcP2x, #EcP2z))
  Emit(@EcCodeChk, 0)

  ; code_affine
  EcEmitP = 0
  Emit(@EcCodeAff, OpMSET(#EcT1, #EcP1z))
  Emit(@EcCodeAff, OpMMUL(#EcT2, #EcP1z, #EcP1z))
  Emit(@EcCodeAff, OpMMUL(#EcT3, #EcP1z, #EcT2))
  Emit(@EcCodeAff, OpMMUL(#EcT2, #EcT3, #EcP2z))
  Emit(@EcCodeAff, OpMINV(#EcT2, #EcT3, #EcT4))
  Emit(@EcCodeAff, OpMSET(#EcT3, #EcP1y))
  Emit(@EcCodeAff, OpMMUL(#EcP1y, #EcT2, #EcT3))
  Emit(@EcCodeAff, OpMMUL(#EcT3, #EcT2, #EcT1))
  Emit(@EcCodeAff, OpMSET(#EcT2, #EcP1x))
  Emit(@EcCodeAff, OpMMUL(#EcP1x, #EcT2, #EcT3))
  Emit(@EcCodeAff, 0)
EndProcedure

; ----------------------------------------------------------------------
;  Curve constants for P-256 (secp256r1). The limb tables (p, R^2 mod p,
;  b*R mod p) are the i15 representation; the generator is the standard
;  uncompressed encoding. Stored low/high byte per 16-bit word so no wide
;  Read and no alignment assumption is made.
; ----------------------------------------------------------------------
DataSection
EcDataP:
  Data.b $11,$01, $FF,$7F, $FF,$7F, $FF,$7F, $FF,$7F, $FF,$7F, $FF,$7F, $3F,$00, $00,$00
  Data.b $00,$00, $00,$00, $00,$00, $00,$00, $00,$10, $00,$00, $00,$40, $FF,$7F, $FF,$7F, $01,$00
EcDataR2:
  Data.b $11,$01, $00,$00, $00,$60, $00,$00, $00,$00, $00,$00, $00,$00, $FC,$7F, $FF,$7F
  Data.b $BF,$7F, $FF,$7F, $BF,$7F, $FF,$7F, $FF,$7F, $FF,$7F, $FF,$77, $FF,$7F, $FF,$4F, $00,$00
EcDataB:
  Data.b $11,$01, $0C,$77, $EF,$5E, $C4,$29, $C4,$3E, $73,$62, $86,$04, $43,$45, $93,$39
  Data.b $01,$3C, $56,$6B, $2E,$21, $EE,$57, $82,$48, $4B,$20, $83,$74, $16,$3C, $87,$01, $00,$00
EcDataGen:
  Data.b $04, $6B,$17,$D1,$F2, $E1,$2C,$42,$47, $F8,$BC,$E6,$E5, $63,$A4,$40,$F2
  Data.b $77,$03,$7D,$81, $2D,$EB,$33,$A0, $F4,$A1,$39,$45, $D8,$98,$C2,$96
  Data.b $4F,$E3,$42,$E2, $FE,$1A,$7F,$9B, $8E,$E7,$EB,$4A, $7C,$0F,$9E,$16
  Data.b $2B,$CE,$33,$57, $6B,$31,$5E,$CE, $CB,$B6,$40,$68, $37,$BF,$51,$F5
EndDataSection
; ==== PORTABLE CORE A64 END ====

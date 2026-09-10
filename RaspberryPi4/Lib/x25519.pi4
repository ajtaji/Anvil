; ======================================================================
;  x25519.pi4 - X25519 (Curve25519 ECDH), ON THE RASPBERRY PI 4
;               (BCM2711, AArch64)
; ======================================================================
;
;  Translated from BearSSL (c) 2017 Thomas Pornin - MIT licence.
;  The notice ships as licenses/BearSSL-LICENSE.txt (release condition).
;
;     XIncludeFile "RaspberryPi4/Lib/bignum.pi4"     ; REQUIRED, before this
;     XIncludeFile "RaspberryPi4/Lib/x25519.pi4"
;
;  The X25519 function of RFC 7748 (scalar multiplication on Curve25519),
;  translated from the BearSSL "ec_c25519_i15" core.  Reads-and-
;  translates only: no C is linked, no foreign ABI is followed.
;
;  REQUIRES bignum.pi4 FIRST.  It calls BnMontmul, BnAdd, BnSub, BnZero,
;  BnDecodeReduce, BnEncode, BnNot, BnGw and BnSw.  A library never
;  includes a library (house rule): the MAIN file lists them, in order.
;  X25519Init() must be called once before X25519().
;
;  API (all buffers little-endian, 32 bytes, per RFC 7748):
;    X25519Init()                   load field constants once, at startup
;    X25519(out.i, secScalar.i, point.i)
;                                   out = secScalar * point on Curve25519.
;                                   The scalar is CLAMPED per RFC 7748
;                                   (bits 0..2 and 255 cleared, bit 254
;                                   set); the high bit of the point's
;                                   last byte is ignored.  Always
;                                   returns 1.  For a base-point
;                                   multiply, pass the 32-byte generator
;                                   u = 9 as the point.
;
;  > IT ALWAYS RETURNS 1, SO THE RETURN VALUE IS NOT A VERDICT.  RFC 7748
;  > has no invalid-point rejection: every 32-byte string is a valid u
;  > coordinate.  A caller that wants to refuse the small-order points
;  > must check the OUTPUT for all-zero, which is a separate decision and
;  > belongs to the caller.  The gate carries the all-zero cases.
;
;  CONSTANT TIME.  The Montgomery ladder runs a FIXED 255 iterations
;  regardless of the scalar; the two ladder points are conditionally
;  swapped each step with a branchless mask (XCswap), never with a branch
;  or an index derived from the scalar - EC leaks the private key
;  otherwise, so this shape is the whole point.  Every field operation is
;  the constant-time i15 core.  Forbidden on secret data, and absent
;  here: / and %.
;
;  THIS FILE RELIES ON EnableExplicit being ON (bignum.pi4 turns it on
;  for the whole program).
;
;  ======================================================================
;   .i IS 64 BITS HERE.  THE FOUR-SHAPE AUDIT, AND ITS ANSWER
;  ======================================================================
;
;  THE BODY BETWEEN THE MARKERS BELOW IS UNCHANGED FROM x25519.pico2 -
;  not "mostly unchanged", not "unchanged except".  Not one line moved.
;  That is a measured result and it is written here because an unchanged
;  copy is exactly what a careless port also looks like, and a reader is
;  entitled to know which of the two this is.
;
;  SHAPE 1 - AN ARRAY ELEMENT IS EIGHT BYTES, NOT FOUR.
;      LOOKED FOR, ALREADY SAFE.  Every array is `.w` (16-bit) or `.a`
;      (8-bit), and neither changes width on this part; only `.i`, `.l`
;      and `.n` do.  XCopy and XCswap walk their operands with
;      `+ (i << 1)`, so a single `.i` array among the field elements
;      would have made every stride wrong by a factor of four AND STILL
;      COMPILED.  THE DECLARATIONS ARE LOAD-BEARING.  Mutation M1 in the
;      gate is a field element declared `.i`.
;
;  SHAPE 2 - PeekL SIGN-EXTENDS.
;      NOT PRESENT.  Words come in through PeekU and bytes through
;      PeekA.  The only PeekB is the `Read.b` DataSection walk in
;      XReadWords, whose bytes are masked with `& 255` before use - so
;      even a sign-extended read of $FF cannot escape it.
;
;  SHAPE 3 - `<<` DOES NOT DISCARD AT BIT 31.
;      NOT PRESENT.  Every shift here is an array index, a byte
;      assembly (`(hi & 255) << 8`), a scalar bit extraction, or the
;      fixed `$FFEB >> i` of the inversion chain.  Nothing reaches bit
;      31, let alone crosses it.  All the modular arithmetic is
;      delegated to bignum.pi4, which carries its own audit.
;
;  SHAPE 4 - A 32-BIT COUNTER NEVER WRAPS.
;      NOT PRESENT.  The ladder counter runs 254 down to 0.
;
;  THE FIFTH SHAPE - `>> 31` AS A SIGN TEST, or `! $FFFFFFFF` AS A
;  LOGICAL NOT - is also absent, and for a reason worth recording: this
;  file already spells its logical NOT as BnNot(), the core's own word
;  for it.  ec256.pico2 spells the same idea as `! $FFFFFFFF` in two
;  places and those two had to be rewritten.  The habit is what made the
;  difference, not the arithmetic.
;
;  The one thing to watch, and it is a CALLER's problem rather than this
;  file's: `mask = 0 - ctl` in XCswap is all SIXTY-FOUR bits here.  It
;  is used only to select between two words that are then stored through
;  PokeW, which keeps the low 16 - so the extra bits are computed and
;  discarded, the same way GhBmul32's extra 28 are.
;
;  PROVEN: builds clean for pi4 and passes tools/a64/a64_ec_check.py on
;  the SAME vectors as the three 32-bit families (the gate imports
;  tools/gen_ec_vectors.py rather than carrying a copy) - the RFC 7748
;  KATs and the iterated tests - cycle-equal under that gate's --timing,
;  mutation-swept under --mutate, and structurally twinned under
;  tools/check_tls_twins.py --cross x25519.
;  NOTHING HERE HAS RUN ON SILICON.
; ======================================================================
; ==== PORTABLE CORE A64 BEGIN ====

; 20 16-bit words per field element (word 0 announced length + up to 18
; value limbs + guard). A Curve25519 field element announces 272 bits (17
; limbs); the decode temporaries a/b use an 18th limb, so 20 words gives
; room for all of them with a common stride.
#X_WORDS = 20
#X_ILEN  = 18                        ; words moved by a field copy/swap
#X_MENC  = 272                       ; (16 << 4), Curve25519 announced length
#X_P0I   = $4A1B                     ; -1/p mod 2^15 for 2^255-19

; Field constants (i15 limb form: word 0 + 17 limbs).
Global Dim XConstP.w[#X_WORDS]        ; p = 2^255 - 19
Global Dim XConstR2.w[#X_WORDS]       ; R^2 mod p
Global Dim XConstA24.w[#X_WORDS]      ; (a-2)/4 = 121665

; Ladder working field elements.
Global Dim Xx1.w[#X_WORDS]
Global Dim Xx2.w[#X_WORDS]
Global Dim Xx3.w[#X_WORDS]
Global Dim Xz2.w[#X_WORDS]
Global Dim Xz3.w[#X_WORDS]
Global Dim Xfa.w[#X_WORDS]
Global Dim Xaa.w[#X_WORDS]
Global Dim Xfb.w[#X_WORDS]
Global Dim Xbb.w[#X_WORDS]
Global Dim Xfc.w[#X_WORDS]
Global Dim Xfd.w[#X_WORDS]
Global Dim Xfe.w[#X_WORDS]
Global Dim Xda.w[#X_WORDS]
Global Dim Xcb.w[#X_WORDS]
Global Dim Xsyn.w[#X_WORDS]           ; synthetic 2^255 modulus for decode
Global Dim XTmp.w[#X_WORDS]           ; add/sub/mul scratch

Global Dim XWG.a[32]                  ; working point copy (big-endian after swap)
Global Dim SecK.a[32]                 ; clamped scalar, big-endian

; ----------------------------------------------------------------------
;  Read n 16-bit words from the Data cursor as low/high byte pairs.
; ----------------------------------------------------------------------
Procedure XReadWords(dst.i, n.i)
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

; Copy #X_ILEN words (a whole field element incl. announced length word).
Procedure XCopy(dst.i, src.i)
  Protected i.i
  i = 0
  While i < #X_ILEN
    PokeW(dst + (i << 1), PeekU(src + (i << 1)))
    i = i + 1
  Wend
EndProcedure

; Constant-time conditional swap of two field elements (#X_ILEN words).
Procedure XCswap(ctl.i, ap.i, bp.i)
  Protected i.i
  Protected mask.i
  Protected aw.i
  Protected bw.i
  Protected tw.i
  mask = 0 - ctl
  i = 0
  While i < #X_ILEN
    aw = PeekU(ap + (i << 1))
    bw = PeekU(bp + (i << 1))
    tw = mask & (aw ! bw)
    PokeW(ap + (i << 1), (aw ! tw) & $FFFF)
    PokeW(bp + (i << 1), (bw ! tw) & $FFFF)
    i = i + 1
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  Field ops modulo p = 2^255-19. Each writes into d (which may alias an
;  operand), computing via a temporary so the i15 "d distinct" rule for
;  montmul is honoured.
; ----------------------------------------------------------------------

; d = a + b mod p
Procedure XAdd(d.i, a.i, b.i)
  Protected ctl.i
  XCopy(@XTmp, a)
  ctl = BnAdd(@XTmp, b, 1)
  ctl = ctl | BnNot(BnSub(@XTmp, @XConstP, 0))
  BnSub(@XTmp, @XConstP, ctl)
  XCopy(d, @XTmp)
EndProcedure

; d = a - b mod p
Procedure XSub(d.i, a.i, b.i)
  XCopy(@XTmp, a)
  BnAdd(@XTmp, @XConstP, BnSub(@XTmp, b, 1))
  XCopy(d, @XTmp)
EndProcedure

; d = a * b mod p (Montgomery domain in, Montgomery domain out)
Procedure XMul(d.i, a.i, b.i)
  BnMontmul(@XTmp, a, b, @XConstP, #X_P0I)
  XCopy(d, @XTmp)
EndProcedure

; Reverse the 32 bytes of a point/scalar buffer in place.
Procedure XByteswap(g.i)
  Protected i.i
  Protected t.i
  i = 0
  While i < 16
    t = PeekA(g + i) & 255
    PokeB(g + i, PeekA(g + 31 - i) & 255)
    PokeB(g + 31 - i, t)
    i = i + 1
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  X25519(out, secScalar, point) - out = secScalar * point on Curve25519.
;  All buffers are 32-byte little-endian per RFC 7748. Returns 1.
; ----------------------------------------------------------------------
Procedure.i X25519(out.i, secScalar.i, point.i)
  Protected i.i
  Protected j.i
  Protected secSwap.i
  Protected secKt.i

  ; Copy the point, clear its high bit, and byteswap to big-endian for the
  ; generic decoder.
  i = 0
  While i < 32
    PokeB(@XWG + i, PeekA(point + i) & 255)
    i = i + 1
  Wend
  PokeB(@XWG + 31, PeekA(@XWG + 31) & $7F)
  XByteswap(@XWG)

  ; Decode the u coordinate modulo a synthetic 2^255 (avoids a dependency
  ; on a decode-reduce against p), then subtract p once if needed.
  BnZero(@Xsyn, $111)
  BnSw(@Xsyn, 18, 1)
  BnDecodeReduce(@Xfa, @XWG, 32, @Xsyn)
  BnSw(@Xfa, 0, #X_MENC)
  BnSub(@Xfa, @XConstP, BnNot(BnSub(@Xfa, @XConstP, 0)))

  ; Initialise the ladder in Montgomery representation. Montgomery 1 is
  ; R mod p = 19 here (R = 2^255, and 2^255 = p + 19).
  BnMontmul(@Xx1, @Xfa, @XConstR2, @XConstP, #X_P0I)
  XCopy(@Xx3, @Xx1)
  BnZero(@Xz2, #X_MENC)
  XCopy(@Xx2, @Xz2)
  BnSw(@Xx2, 1, 19)
  XCopy(@Xz3, @Xx2)

  ; Build the clamped scalar (RFC 7748) in big-endian order. The incoming
  ; scalar is little-endian, so reverse it, then apply the clamp: on the
  ; big-endian buffer that is the last byte &= 0xF8, first byte &= 0x7F,
  ; first byte |= 0x40.
  i = 0
  While i < 32
    PokeB(@SecK + i, PeekA(secScalar + 31 - i) & 255)
    i = i + 1
  Wend
  PokeB(@SecK + 31, PeekA(@SecK + 31) & $F8)
  PokeB(@SecK + 0, PeekA(@SecK + 0) & $7F)
  PokeB(@SecK + 0, PeekA(@SecK + 0) | $40)

  secSwap = 0
  i = 254
  While i >= 0
    secKt = (PeekA(@SecK + 31 - (i >> 3)) >> (i & 7)) & 1
    secSwap = secSwap ! secKt
    XCswap(secSwap, @Xx2, @Xx3)
    XCswap(secSwap, @Xz2, @Xz3)
    secSwap = secKt

    XAdd(@Xfa, @Xx2, @Xz2)
    XMul(@Xaa, @Xfa, @Xfa)
    XSub(@Xfb, @Xx2, @Xz2)
    XMul(@Xbb, @Xfb, @Xfb)
    XSub(@Xfe, @Xaa, @Xbb)
    XAdd(@Xfc, @Xx3, @Xz3)
    XSub(@Xfd, @Xx3, @Xz3)
    XMul(@Xda, @Xfd, @Xfa)
    XMul(@Xcb, @Xfc, @Xfb)

    XAdd(@Xx3, @Xda, @Xcb)
    XMul(@Xx3, @Xx3, @Xx3)
    XSub(@Xz3, @Xda, @Xcb)
    XMul(@Xz3, @Xz3, @Xz3)
    XMul(@Xz3, @Xz3, @Xx1)
    XMul(@Xx2, @Xaa, @Xbb)
    XMul(@Xz2, @XConstA24, @Xfe)
    XAdd(@Xz2, @Xz2, @Xaa)
    XMul(@Xz2, @Xfe, @Xz2)

    i = i - 1
  Wend
  XCswap(secSwap, @Xx2, @Xx3)
  XCswap(secSwap, @Xz2, @Xz3)

  ; Invert z2 by a square-and-multiply chain over the fixed exponent p-2,
  ; mutualising the long runs of one bits (translated as-is).
  XCopy(@Xfa, @Xz2)
  i = 0
  While i < 15
    XMul(@Xfa, @Xfa, @Xfa)
    XMul(@Xfa, @Xfa, @Xz2)
    i = i + 1
  Wend
  XCopy(@Xfb, @Xfa)
  i = 0
  While i < 14
    j = 0
    While j < 16
      XMul(@Xfb, @Xfb, @Xfb)
      j = j + 1
    Wend
    XMul(@Xfb, @Xfb, @Xfa)
    i = i + 1
  Wend
  i = 14
  While i >= 0
    XMul(@Xfb, @Xfb, @Xfb)
    If (($FFEB >> i) & 1) <> 0
      XMul(@Xfb, @Xz2, @Xfb)
    EndIf
    i = i - 1
  Wend
  XMul(@Xfb, @Xx2, @Xfb)

  ; Leave Montgomery form via a Montgomery multiply by 1.
  BnZero(@Xfa, #X_MENC)
  BnSw(@Xfa, 1, 1)
  BnMontmul(@Xx2, @Xfa, @Xfb, @XConstP, #X_P0I)

  ; Encode big-endian, byteswap back to little-endian, deliver.
  BnEncode(@XWG, 32, @Xx2)
  XByteswap(@XWG)
  i = 0
  While i < 32
    PokeB(out + i, PeekA(@XWG + i) & 255)
    i = i + 1
  Wend
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  X25519Init - load the field constants once, before X25519().
; ----------------------------------------------------------------------
Procedure X25519Init()
  Restore XDataP
  XReadWords(@XConstP, 18)
  Restore XDataR2
  XReadWords(@XConstR2, 18)
  Restore XDataA24
  XReadWords(@XConstA24, 18)
EndProcedure

; ----------------------------------------------------------------------
;  Curve25519 field constants (i15 limb form, word 0 + 17 limbs), stored
;  low/high byte per 16-bit word so no wide Read and no alignment
;  assumption is made.
; ----------------------------------------------------------------------
DataSection
XDataP:
  Data.b $10,$01, $ED,$7F, $FF,$7F, $FF,$7F, $FF,$7F, $FF,$7F, $FF,$7F, $FF,$7F, $FF,$7F
  Data.b $FF,$7F, $FF,$7F, $FF,$7F, $FF,$7F, $FF,$7F, $FF,$7F, $FF,$7F, $FF,$7F, $FF,$7F
XDataR2:
  Data.b $10,$01, $69,$01, $00,$00, $00,$00, $00,$00, $00,$00, $00,$00, $00,$00, $00,$00
  Data.b $00,$00, $00,$00, $00,$00, $00,$00, $00,$00, $00,$00, $00,$00, $00,$00, $00,$00
XDataA24:
  Data.b $10,$01, $D3,$45, $46,$00, $00,$00, $00,$00, $00,$00, $00,$00, $00,$00, $00,$00
  Data.b $00,$00, $00,$00, $00,$00, $00,$00, $00,$00, $00,$00, $00,$00, $00,$00, $00,$00
EndDataSection
; ==== PORTABLE CORE A64 END ====

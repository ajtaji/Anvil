; Shared integer-to-binary32 bit conversion used by graphics renderers.
; This preserves the existing Neon conversion, including its bounded fixed-
; point quotient and nearest/ties-away mantissa rounding. It is not a general
; IEEE division implementation. On 64-bit targets, |num| and |den| must not
; exceed 2147483647. A zero denominator returns zero; exact zero has no sign.
; Small numerators use forty quotient fraction bits, larger ones thirty-one.
; No renderer state, allocation, hardware address or device dependency.

Procedure.i GraphicsF32RatioBits(num.i, den.i)
  Protected neg.i
  Protected bias.i
  Protected m.i
  Protected p.i
  Protected e.i
  Protected sh.i
  Protected mant.i
  Protected half.i

  If den = 0
    ProcedureReturn 0
  EndIf
  neg = 0
  If num < 0
    neg = 1
    num = 0 - num
  EndIf
  If den < 0
    If neg = 1
      neg = 0
    Else
      neg = 1
    EndIf
    den = 0 - den
  EndIf
  If num = 0
    ProcedureReturn 0
  EndIf

  ; m = num * 2^bias / den.
  ;
  ; THE BIAS IS 40 AND NOT 31, AND THE DIFFERENCE IS ONE ULP. With 31
  ; the quotient can land with EXACTLY twenty-four significant bits -
  ; that happens whenever num/den is in [2^-8, 2^-7) - and then there
  ; is nothing left below the mantissa to round with, so the answer
  ; comes out truncated. The clip coordinate 2/320 is in that band, and
  ; a rectangle two pixels from the viewport centre got $BBCCCCCC where
  ; IEEE 754 says $BBCCCCCD. FOUND BY tools/a64/a64_neon_check.py, not
  ; by the board: the 2,073,600-pixel run in pi4NeonBox.pi4 has no
  ; geometry and no colour in that band.
  ;
  ; With 40 the quotient carries at least seven bits below the mantissa
  ; for every denominator this engine uses - 255 for a colour channel,
  ; half the surface width or height for a coordinate - so the rounding
  ; below always has something to round.
  ;
  ; THE SHIFT CANNOT OVERFLOW. .i is 64 bits and signed; 40 bits of
  ; headroom leaves 23 for the numerator, so anything below 4194304 is
  ; safe. A caller with a bigger one drops back to 31, which is the
  ; behaviour that was correct to within one ulp anyway.
  bias = 40
  If num >= 4194304
    bias = 31
  EndIf
  m = (num << bias) / den
  If m = 0
    ProcedureReturn 0
  EndIf

  ; p = index of the highest set bit of m, by halving rather than by
  ; counting. THE LOOP THIS REPLACED WAS UP TO 62 ITERATIONS AND IT IS
  ; ON THE PER-VERTEX PATH: with the ARM MMU off every instruction
  ; fetch is Device memory, so sixty iterations is tens of
  ; microseconds, and a text-heavy frame has a hundred thousand
  ; vertices in it. Six shifts instead.
  p = 0
  If (m >> 32) <> 0
    p = p + 32
  EndIf
  If (m >> (p + 16)) <> 0
    p = p + 16
  EndIf
  If (m >> (p + 8)) <> 0
    p = p + 8
  EndIf
  If (m >> (p + 4)) <> 0
    p = p + 4
  EndIf
  If (m >> (p + 2)) <> 0
    p = p + 2
  EndIf
  If (m >> (p + 1)) <> 0
    p = p + 1
  EndIf

  ; The value is m * 2^-bias, so its exponent is p - bias.
  e = p - bias

  If p > 23
    sh = p - 23
    half = 1 << (sh - 1)
    mant = (m + half) >> sh
    ; A carry out of the mantissa's top bit means the value rounded up
    ; to the next binade.
    If (mant >> 24) <> 0
      mant = mant >> 1
      e = e + 1
    EndIf
  ElseIf p = 23
    ; EXACTLY TWENTY-FOUR SIGNIFICANT BITS: nothing to round off and
    ; nothing to shift.
    ;
    ; UNREACHABLE WITH A BIAS OF 40 and every denominator this engine
    ; uses, and it is here anyway because the arm above CANNOT HANDLE
    ; IT: at p = 23 the shift is zero and `1 << (sh - 1)` is a shift by
    ; MINUS ONE. On AArch64 a variable shift is taken modulo the
    ; register width, so that is a shift by 63 - the rounding constant
    ; becomes $8000000000000000, the carry test fires, and the exponent
    ; comes out one too big. A silently wrong float, from a shift the
    ; compiler cannot warn about.
    ;
    ; A backstop that is labelled as unreachable is honest; one
    ; described as doing work it does not do is the beginning of a
    ; wrong belief about where the guard lives.
    mant = m
  Else
    mant = m << (23 - p)
  EndIf
  mant = mant & $7FFFFF

  e = e + 127
  If e <= 0
    ; Underflow to zero. Nothing this file computes can reach it - the
    ; smallest ratio is 1/255 - and a denormal would be worse than a
    ; zero because the vertex fetcher may flush it.
    ProcedureReturn 0
  EndIf
  If e > 254
    ; Overflow. Saturate to the largest finite value rather than
    ; produce an infinity that would propagate silently.
    e = 254
    mant = $7FFFFF
  EndIf

  If neg = 1
    ProcedureReturn ($80000000 | (e << 23) | mant) & $FFFFFFFF
  EndIf
  ProcedureReturn ((e << 23) | mant) & $FFFFFFFF
EndProcedure

Procedure.i GraphicsF32IntBits(n.i)
  ProcedureReturn GraphicsF32RatioBits(n, 1)
EndProcedure

; Caller supplies a channel in 0..255 for a result in 0..1.
Procedure.i GraphicsF32ByteBits(n.i)
  ProcedureReturn GraphicsF32RatioBits(n, 255)
EndProcedure

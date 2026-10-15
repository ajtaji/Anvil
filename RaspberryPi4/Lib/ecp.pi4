; ======================================================================
;  ecp.pi4 - ECDSA signature VERIFY on the NIST P-384 and P-521 curves,
;            ON THE RASPBERRY PI 4 (BCM2711, AArch64) AND EVERY OTHER
;            64-BIT ANVIL BOARD
; ======================================================================
;
;     XIncludeFile "RaspberryPi4/Lib/ecp.pi4"
;
;  Generic short-Weierstrass arithmetic over the NIST prime fields, with
;  a = -3, and the FIPS 186-4 section 6.4 ECDSA verification built on it.
;  Two curves are loaded from the tables at the bottom of this file:
;
;      curve id 24   secp384r1 (P-384)   12 limbs of 32 bits
;      curve id 25   secp521r1 (P-521)   17 limbs of 32 bits
;
;  The ids are the TLS NamedCurve registry values, which is also what the
;  X.509 engine reports for a certificate's curve. P-256 (23) is NOT
;  here: ec256.pi4 computes it and ecdsa.pi4 routes it there. One curve,
;  one implementation.
;
;  WHO CALLS THIS. ecdsa.pi4's EcdsaVrfy - the certificate seam - turns a
;  DER signature into r||s with its own strict parser and hands curves 24
;  and 25 to EcpVrfyRaw below. A program may also call EcpVrfyRaw
;  directly with a raw r||s signature (the CAVP record shape).
;
;  API:
;    EcpVrfyRaw(curve, hashAddr, hashLen, qAddr, qLen, sigAddr, sigLen)
;        -> 1 valid / 0 rejected / -1 curve not computed here.
;        qAddr/qLen is the uncompressed point 0x04 || X || Y (97 bytes for
;        P-384, 133 for P-521). sigAddr/sigLen is r || s, two equal-width
;        big-endian integers; leading zero bytes are allowed, a value
;        wider than the curve order is refused. The hash is truncated to
;        the order's bit length (bits2int), so any hash length works.
;    EcpLastErr  0 valid, 1 rejected, 2 curve not computed here - the
;        same numbering as EcdsaLastErr, which ecdsa.pi4 copies it into.
;    EcpRefusedAt  which check refused the last signature (#ECP_AT_*):
;        shape, scalar range, key encoding, on-curve, infinity, mismatch.
;    EcpLoadCurve(curve) -> 1 / 0 - load (once) a curve's constants and
;        derived Montgomery values; EcpVrfyRaw calls it itself.
;
;  DEPENDENCIES: NONE (house rule - the MAIN file lists what it needs).
;  ecdsa.pi4 requires THIS file before it. EnableExplicit is ON.
;
;  ======================================================================
;   WHY THIS IS NOT BUILT ON bignum.pi4's i15 CORE
;  ======================================================================
;
;  bignum.pi4 is BearSSL's 15-bit-limb core, kept limb-for-limb with the
;  32-bit families. It is correct here and it is slow here: P-256 ECDSA
;  on it costs about 155 million model instructions, and a P-384 verify
;  on the same core would be roughly three times that - per certificate,
;  and a chain to a P-384 root has two. bignum.pi4's own header says what
;  to do about that: "A wider core belongs in its own module with its own
;  gate, the day something measures that ... is too slow here." This is
;  that module, for the two curves that need it.
;
;  THE LIMB IS 32 BITS AND THE PRODUCT IS 64. AArch64 `mul` gives the low
;  64 bits of a product, and a 32x32 product never needs more. The
;  Montgomery multiply (CIOS) accumulates t[j] + a*b + carry, which is at
;  most (2^32-1) + (2^32-1)^2 + (2^32-1) = 2^64 - 1: it FITS 64 bits
;  exactly, as an unsigned number. .i is signed, so a sum above 2^63 is a
;  negative .i - the right BIT PATTERN, and `+` and `*` wrap modulo 2^64
;  on this register, so nothing is lost. What is NOT free is the read of
;  the high half: `>>` is ARITHMETIC here, so every carry is taken as
;  (s >> 32) & #ECP_W32, never s >> 32 alone. The gate's mutation sweep
;  removes that mask and watches the answers go wrong.
;
;  A limb is never stored negative: every stored limb is masked to
;  0..$FFFFFFFF, so a comparison of two limbs is an ordinary signed
;  comparison of two non-negative numbers.
;
;  ======================================================================
;   NOT CONSTANT TIME, ON PURPOSE
;  ======================================================================
;
;  Verification handles public data only: the signature crossed the wire
;  in clear, the key is in a certificate, the hash is of public bytes.
;  So the scalar loop branches on scalar bits and the point addition
;  branches on the special cases (infinity, equal points), which is what
;  a correct variable-time verifier does. There is NO signing, NO private
;  key and NO nonce anywhere in this file, and none must ever be added on
;  top of this arithmetic - a signer needs a constant-time core.
;
;  ======================================================================
;   THE ALGORITHM, AND WHERE EACH CHECK COMES FROM (FIPS 186-4 6.4.2)
;  ======================================================================
;
;    1. r and s in [1, n-1]                          else rejected
;    2. Q decodes: 0x04 prefix, both coordinates < p, ON the curve
;       y^2 = x^3 - 3x + b                            else rejected
;    3. e = the leftmost bitlen(n) bits of the hash, reduced mod n
;    4. w = s^-1 mod n (Fermat: s^(n-2)); u1 = e*w, u2 = r*w mod n
;    5. R = u1*G + u2*Q by one interleaved (Shamir) double-and-add over
;       Jacobian coordinates; R at infinity           rejected
;    6. v = x(R) mod n (one conditional subtraction - p < 2n for both
;       curves, checked by the gate); valid iff v = r.
;  The field and order inversions are both Fermat exponentiations in
;  Montgomery form; both moduli are prime (checked by the gate).
;
;  ======================================================================
;   WHAT HAS BEEN PROVEN, AND WHAT HAS NOT
;  ======================================================================
;
;  PROVEN 2026-10-14 under the A64 model by tools/a64/a64_ecp_check.py,
;  68 jobs, ALL PASS:
;    * the curve tables equal OpenSSL's own `ecparam -param_enc explicit`
;      output byte for byte; p and n prime, G on the curve, n*G at
;      infinity and p < 2n, all computed by the gate in Python;
;    * the Montgomery setup EcpLoadCurve derives (-1/p and -1/n mod
;      2^32, R^2 and R mod p and n, b and G in Montgomery form, the bit
;      length of n) equals the gate's own Python integers, and no stored
;      limb has a bit above 31;
;    * 47 records of tools/fixtures/ecp_vectors.json on each entry point
;      they apply to: OpenSSL signatures over SHA-256/384/512 verify on
;      both curves, as does the malleated (r, n - s) and r || s with a
;      leading zero byte; the CAVP SigVer failure shapes are refused
;      (message, r, s or key changed; r or s zero or n; r + n on P-521;
;      off-curve, x >= p, compressed and truncated keys; an odd raw
;      length; a raw half wider than the curve); the keys Q = G and
;      Q = -G drive the point addition into its doubling and infinity
;      cases and verify; the DER seam EcdsaVrfy agrees, with the signature
;      exactly as OpenSSL wrote it (0x81 long form on P-521) and with its
;      last byte flipped; an unknown curve id still answers -1.
;  MEASURED COST OF ONE VERIFY (model instructions, this file as it
;  stands): P-384 115,402,297 to 139,869,750; P-521 284,677,721 to
;  355,268,205 (the spread is the Hamming weight of u1, u2). The first
;  spelling of this file cost 203,419,623 / 526,266,220; the pointer-walk
;  fused multiply, the windowed inversion and the affine shortcut in
;  EcpAddPt took off 31% / 32%. For scale, P-256 on ec256.pi4's i15 core
;  is about 155 million.
;  Real chains through the X.509 engine: tools/a64/a64_x509_check.py
;  mode D. NOTHING HERE HAS RUN ON SILICON from the session that wrote
;  it.
; ======================================================================
EnableExplicit

#ECP_W32  = $FFFFFFFF
#ECP_S    = 18                      ; limbs per register slot (17 + 1)
#ECP_NREG = 64                      ; registers in the file

; EcpLastErr, numbered as ecdsa.pi4's EcdsaLastErr.
#ECP_ERR_OK     = 0
#ECP_ERR_BADSIG = 1
#ECP_ERR_CURVE  = 2

; EcpRefusedAt - WHICH CHECK refused the last signature, for diagnosis and
; for the gate. Every refusal answers 0 with EcpLastErr = 1, so without
; this a check that was skipped is invisible whenever a later check
; refuses the same input anyway (an off-curve key also fails the final
; comparison; r = n also never matches x(R)). The gate's mutation sweep
; found exactly that: three range/key/curve checks deleted one at a time
; and every verdict unchanged. Naming the stage makes each check
; observable on its own.
#ECP_AT_NONE     = 0                 ; not refused (valid, or curve unknown)
#ECP_AT_SHAPE    = 1                 ; r || s of zero or odd length
#ECP_AT_SCALAR   = 2                 ; r or s wider than the curve, 0, or >= n
#ECP_AT_KEY      = 3                 ; key length, prefix, or a coordinate >= p
#ECP_AT_CURVE    = 4                 ; the key is not on the curve
#ECP_AT_INFINITY = 5                 ; u1*G + u2*Q is the point at infinity
#ECP_AT_MISMATCH = 6                 ; x(R) mod n is not r

; ----------------------------------------------------------------------
;  THE REGISTER FILE. A register is #ECP_S consecutive .i cells of the
;  one array EcpV, holding a little-endian number in 32-bit limbs (limb 0
;  least significant), each limb 0..$FFFFFFFF. Field values live in
;  Montgomery form (x * R mod p, R = 2^(32 * EcpNL)) unless the name says
;  otherwise. Registers are named by index; a procedure turns an index
;  into a base with `* #ECP_S`.
; ----------------------------------------------------------------------
#ECP_RP     = 0                     ; p, plain - modulus slot 0
#ECP_RN     = 1                     ; n, plain - modulus slot 1
#ECP_RB     = 2                     ; b, Montgomery (mod p)
#ECP_RONE1  = 3                     ; the plain integer 1
#ECP_R2P    = 4                     ; R^2 mod p
#ECP_R2N    = 5                     ; R^2 mod n
#ECP_RONEP  = 6                     ; 1 in Montgomery form mod p (R mod p)
#ECP_RONEN  = 7                     ; 1 in Montgomery form mod n (R mod n)
#ECP_GX     = 8                     ; generator, Jacobian, Montgomery
#ECP_GY     = 9
#ECP_GZ     = 10
#ECP_QX     = 11                    ; public key, Jacobian, Montgomery
#ECP_QY     = 12
#ECP_QZ     = 13
#ECP_SX     = 14                    ; G + Q, Jacobian, Montgomery
#ECP_SY     = 15
#ECP_SZ     = 16
#ECP_AX     = 17                    ; the accumulator R
#ECP_AY     = 18
#ECP_AZ     = 19
#ECP_T1     = 20                    ; T1..T12 point-formula scratch
#ECP_T12    = 31
#ECP_RR     = 32                    ; signature r, plain
#ECP_RS     = 33                    ; signature s, plain
#ECP_RE     = 34                    ; hash as an integer mod n, plain
#ECP_RW     = 35                    ; 1/s mod n, Montgomery
#ECP_RU1    = 36                    ; u1, plain
#ECP_RU2    = 37                    ; u2, plain
#ECP_REXP   = 38                    ; an exponent (m - 2)
#ECP_RACC   = 39                    ; exponentiation accumulator
#ECP_RX     = 40                    ; scratch
#ECP_RY     = 41                    ; scratch
#ECP_RZ     = 42                    ; scratch
#ECP_RWIN   = 48                    ; 48..62: a^1..a^15 for EcpInv

Global Dim EcpV.i[#ECP_NREG * #ECP_S]
Global Dim EcpT.i[#ECP_S + 2]       ; Montgomery / add / sub workspace
Global Dim EcpU.i[#ECP_S + 2]       ; trial-subtraction workspace
Global Dim EcpM0.i[2]               ; -1/m mod 2^32 for slot 0 (p), 1 (n)

Global EcpNL.i                      ; limbs per value for the loaded curve
Global EcpCurve.i                   ; the curve loaded, 0 for none
Global EcpPLen.i                    ; coordinate / scalar byte length
Global EcpNBits.i                   ; bit length of the order n
Global EcpLastErr.i
Global EcpRefusedAt.i               ; #ECP_AT_*, see above

; ----------------------------------------------------------------------
;  Limb-level helpers.
; ----------------------------------------------------------------------
Procedure EcpZero(r.i)
  Protected j.i
  Protected b.i
  b = r * #ECP_S
  j = 0
  While j < #ECP_S
    EcpV[b + j] = 0
    j = j + 1
  Wend
EndProcedure

Procedure EcpCopy(rd.i, ra.i)
  Protected j.i
  Protected d.i
  Protected a.i
  d = rd * #ECP_S
  a = ra * #ECP_S
  j = 0
  While j < #ECP_S
    EcpV[d + j] = EcpV[a + j]
    j = j + 1
  Wend
EndProcedure

Procedure.i EcpIsZero(ra.i)
  Protected j.i
  Protected a.i
  a = ra * #ECP_S
  j = 0
  While j < EcpNL
    If EcpV[a + j] <> 0
      ProcedureReturn 0
    EndIf
    j = j + 1
  Wend
  ProcedureReturn 1
EndProcedure

Procedure.i EcpEqual(ra.i, rb.i)
  Protected j.i
  Protected a.i
  Protected b.i
  a = ra * #ECP_S
  b = rb * #ECP_S
  j = 0
  While j < EcpNL
    If EcpV[a + j] <> EcpV[b + j]
      ProcedureReturn 0
    EndIf
    j = j + 1
  Wend
  ProcedureReturn 1
EndProcedure

; 1 if a < b as unsigned EcpNL-limb numbers. Limbs are stored
; non-negative, so a signed limb compare is the unsigned one.
Procedure.i EcpLess(ra.i, rb.i)
  Protected j.i
  Protected a.i
  Protected b.i
  a = ra * #ECP_S
  b = rb * #ECP_S
  j = EcpNL - 1
  While j >= 0
    If EcpV[a + j] < EcpV[b + j]
      ProcedureReturn 1
    EndIf
    If EcpV[a + j] > EcpV[b + j]
      ProcedureReturn 0
    EndIf
    j = j - 1
  Wend
  ProcedureReturn 0
EndProcedure

Procedure.i EcpBit(ra.i, i.i)
  ProcedureReturn (EcpV[ra * #ECP_S + (i >> 5)] >> (i & 31)) & 1
EndProcedure

; Plain subtraction a - b into d (no modulus); the caller knows a >= b.
Procedure EcpSubPlain(rd.i, ra.i, rb.i)
  Protected j.i
  Protected s.i
  Protected borrow.i
  Protected d.i
  Protected a.i
  Protected b.i
  d = rd * #ECP_S
  a = ra * #ECP_S
  b = rb * #ECP_S
  borrow = 0
  j = 0
  While j < EcpNL
    s = EcpV[a + j] - EcpV[b + j] - borrow
    EcpV[d + j] = s & #ECP_W32
    borrow = (s >> 63) & 1
    j = j + 1
  Wend
EndProcedure

; Shift right by cnt bits, 0 < cnt < 32.
Procedure EcpShr(ra.i, cnt.i)
  Protected j.i
  Protected a.i
  a = ra * #ECP_S
  j = 0
  While j < EcpNL
    EcpV[a + j] = ((EcpV[a + j] >> cnt) | (EcpV[a + j + 1] << (32 - cnt))) & #ECP_W32
    j = j + 1
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  EcpDecode(rd, src, len) - big-endian bytes into a register. Leading
;  zero bytes are skipped; a value needing more than EcpNL limbs is
;  refused (returns 0) rather than truncated.
; ----------------------------------------------------------------------
Procedure.i EcpDecode(rd.i, src.i, len.i)
  Protected k.i
  Protected d.i
  Protected bv.i
  While len > 0 And (PeekA(src) & 255) = 0
    src = src + 1
    len = len - 1
  Wend
  If len > EcpNL * 4
    ProcedureReturn 0
  EndIf
  EcpZero(rd)
  d = rd * #ECP_S
  k = 0
  While k < len
    bv = PeekA(src + len - 1 - k) & 255
    EcpV[d + (k >> 2)] = EcpV[d + (k >> 2)] | (bv << ((k & 3) << 3))
    k = k + 1
  Wend
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  EcpReduceT(rd, ms) - T[0..n] holds a value below 2m; write it, less m
;  if it is at least m, to register rd. ms is the modulus slot: 0 = p,
;  1 = n (the register index of the modulus is the slot number).
;  T >= m exactly when T[n] - borrow >= 0, where borrow is what the
;  n-limb trial subtraction T - m left over.
; ----------------------------------------------------------------------
Procedure EcpReduceT(rd.i, ms.i)
  Protected j.i
  Protected s.i
  Protected borrow.i
  Protected n.i
  Protected m.i
  Protected d.i
  n = EcpNL
  m = ms * #ECP_S
  d = rd * #ECP_S
  borrow = 0
  j = 0
  While j < n
    s = EcpT[j] - EcpV[m + j] - borrow
    EcpU[j] = s & #ECP_W32
    borrow = (s >> 63) & 1
    j = j + 1
  Wend
  If EcpT[n] - borrow >= 0
    j = 0
    While j < n
      EcpV[d + j] = EcpU[j]
      j = j + 1
    Wend
  Else
    j = 0
    While j < n
      EcpV[d + j] = EcpT[j]
      j = j + 1
    Wend
  EndIf
  EcpV[d + n] = 0
EndProcedure

; ----------------------------------------------------------------------
;  EcpMul(rd, ra, rb, ms) - Montgomery product a*b/R mod m.
;  a and b must be below m. rd may be ra or rb: the product is built in
;  T and written last.
;
;  FUSED CIOS: for each limb a[i], ONE inner loop both adds a[i]*b[j]
;  and the reduction multiple mq*m[j], shifting the running total down
;  one limb as it goes - mq is fixed from limb 0 before the loop starts.
;  Two carries travel the loop, c1 for the product and c2 for the
;  reduction; each partial sum is at most (2^32-1) + (2^32-1)^2 +
;  (2^32-1) = 2^64 - 1, so each fits 64 bits as an unsigned number, and
;  each carry is read with the masked shift (`>>` is arithmetic here).
;  T[n] and T[n+1] are the top: T = (T + a[i]*b + mq*m) / 2^32 stays
;  below 2m, which EcpReduceT finishes.
;
;  THE OPERANDS ARE WALKED BY POINTER (PeekI/PokeI at a stride of 8, the
;  size of one .i), not by index: measured under the model, the indexed
;  spelling of the same arithmetic costs 20.6k instructions per P-384
;  product against 15.9k for this one, and products are 90% of a verify.
; ----------------------------------------------------------------------
Procedure EcpMul(rd.i, ra.i, rb.i, ms.i)
  Protected n.i
  Protected i.i
  Protected j.i
  Protected ai.i
  Protected s.i
  Protected c1.i
  Protected c2.i
  Protected mq.i
  Protected m0.i
  Protected t0.i
  Protected ap.i
  Protected bp.i
  Protected mp.i
  Protected tp.i
  Protected b0.i
  Protected mb.i
  n = EcpNL
  m0 = EcpM0[ms]
  ap = @EcpV[ra * #ECP_S]
  b0 = @EcpV[rb * #ECP_S]
  mb = @EcpV[ms * #ECP_S]
  tp = @EcpT[0]
  j = 0
  While j < n + 2
    PokeI(tp + j * 8, 0)
    j = j + 1
  Wend
  i = 0
  While i < n
    ai = PeekI(ap)
    bp = b0
    mp = mb
    tp = @EcpT[0]
    s = PeekI(tp) + ai * PeekI(bp)
    t0 = s & #ECP_W32
    c1 = (s >> 32) & #ECP_W32
    mq = (t0 * m0) & #ECP_W32
    s = t0 + mq * PeekI(mp)
    c2 = (s >> 32) & #ECP_W32
    j = 1
    While j < n
      bp = bp + 8
      mp = mp + 8
      s = PeekI(tp + 8) + ai * PeekI(bp) + c1
      c1 = (s >> 32) & #ECP_W32
      s = (s & #ECP_W32) + mq * PeekI(mp) + c2
      c2 = (s >> 32) & #ECP_W32
      PokeI(tp, s & #ECP_W32)
      tp = tp + 8
      j = j + 1
    Wend
    s = PeekI(tp + 8) + c1
    c1 = (s >> 32) & #ECP_W32
    s = (s & #ECP_W32) + c2
    c2 = (s >> 32) & #ECP_W32
    PokeI(tp, s & #ECP_W32)
    PokeI(tp + 8, PeekI(tp + 16) + c1 + c2)
    PokeI(tp + 16, 0)
    ap = ap + 8
    i = i + 1
  Wend
  EcpReduceT(rd, ms)
EndProcedure

; a + b mod m; both below m.
Procedure EcpAddMod(rd.i, ra.i, rb.i, ms.i)
  Protected j.i
  Protected s.i
  Protected c.i
  Protected a.i
  Protected b.i
  a = ra * #ECP_S
  b = rb * #ECP_S
  c = 0
  j = 0
  While j < EcpNL
    s = EcpV[a + j] + EcpV[b + j] + c
    EcpT[j] = s & #ECP_W32
    c = (s >> 32) & 1
    j = j + 1
  Wend
  EcpT[EcpNL] = c
  EcpReduceT(rd, ms)
EndProcedure

; a - b mod m; both below m.
Procedure EcpSubMod(rd.i, ra.i, rb.i, ms.i)
  Protected j.i
  Protected s.i
  Protected c.i
  Protected borrow.i
  Protected a.i
  Protected b.i
  Protected m.i
  Protected d.i
  a = ra * #ECP_S
  b = rb * #ECP_S
  m = ms * #ECP_S
  d = rd * #ECP_S
  borrow = 0
  j = 0
  While j < EcpNL
    s = EcpV[a + j] - EcpV[b + j] - borrow
    EcpT[j] = s & #ECP_W32
    borrow = (s >> 63) & 1
    j = j + 1
  Wend
  If borrow <> 0
    c = 0
    j = 0
    While j < EcpNL
      s = EcpT[j] + EcpV[m + j] + c
      EcpT[j] = s & #ECP_W32
      c = (s >> 32) & 1
      j = j + 1
    Wend
  EndIf
  j = 0
  While j < EcpNL
    EcpV[d + j] = EcpT[j]
    j = j + 1
  Wend
  EcpV[d + EcpNL] = 0
EndProcedure

; ----------------------------------------------------------------------
;  EcpInv(rd, ra, ms) - the modular inverse of a Montgomery value, as a
;  Montgomery value: a^(m-2), m prime (Fermat). A fixed 4-bit window:
;  a^1..a^15 are tabulated in #ECP_RWIN.., then for every nibble of
;  m - 2 from the top, four squarings and at most one product. Leading
;  zero nibbles square the Montgomery one and leave it one. 32*EcpNL is
;  a multiple of 4, so a nibble never straddles two limbs. rd must not be
;  #ECP_RACC, #ECP_REXP or #ECP_RX; ra must not be #ECP_RACC.
; ----------------------------------------------------------------------
Procedure EcpInv(rd.i, ra.i, ms.i)
  Protected i.i
  Protected k.i
  Protected w.i
  EcpCopy(#ECP_REXP, ms)
  ; m - 2. Every modulus here is odd and above 2, so the borrow stops.
  EcpZero(#ECP_RX)
  EcpV[#ECP_RX * #ECP_S] = 2
  EcpSubPlain(#ECP_REXP, #ECP_REXP, #ECP_RX)
  EcpCopy(#ECP_RWIN, ra)
  k = 1
  While k < 15
    EcpMul(#ECP_RWIN + k, #ECP_RWIN + k - 1, ra, ms)
    k = k + 1
  Wend
  If ms = 0
    EcpCopy(#ECP_RACC, #ECP_RONEP)
  Else
    EcpCopy(#ECP_RACC, #ECP_RONEN)
  EndIf
  i = EcpNL * 32 - 4
  While i >= 0
    EcpMul(#ECP_RACC, #ECP_RACC, #ECP_RACC, ms)
    EcpMul(#ECP_RACC, #ECP_RACC, #ECP_RACC, ms)
    EcpMul(#ECP_RACC, #ECP_RACC, #ECP_RACC, ms)
    EcpMul(#ECP_RACC, #ECP_RACC, #ECP_RACC, ms)
    w = (EcpV[#ECP_REXP * #ECP_S + (i >> 5)] >> (i & 31)) & 15
    If w <> 0
      EcpMul(#ECP_RACC, #ECP_RACC, #ECP_RWIN + w - 1, ms)
    EndIf
    i = i - 4
  Wend
  EcpCopy(rd, #ECP_RACC)
EndProcedure

; ----------------------------------------------------------------------
;  Montgomery constants for one modulus slot: m0 = -1/m mod 2^32 by
;  Newton (each step doubles the correct low bits: 3, 6, 12, 24, 48), and
;  R^2 mod m by doubling 1 modulo m, 64 * EcpNL times. Each Newton
;  product is masked: only its low 32 bits mean anything.
; ----------------------------------------------------------------------
Procedure EcpSetupSlot(ms.i)
  Protected x.i
  Protected inv.i
  Protected k.i
  Protected r2.i
  x = EcpV[ms * #ECP_S]
  inv = x
  k = 0
  While k < 4
    inv = (inv * (2 - ((x * inv) & #ECP_W32))) & #ECP_W32
    k = k + 1
  Wend
  EcpM0[ms] = (0 - inv) & #ECP_W32
  If ms = 0
    r2 = #ECP_R2P
  Else
    r2 = #ECP_R2N
  EndIf
  EcpCopy(r2, #ECP_RONE1)
  k = 0
  While k < 64 * EcpNL
    EcpAddMod(r2, r2, r2, ms)
    k = k + 1
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  EcpLoadCurve(curve) -> 1 loaded / 0 not a curve this file computes.
;  Loads p, n, b, G from the tables, sets up both Montgomery slots and
;  puts b and G into Montgomery form. Cached: a second call for the same
;  curve does nothing.
; ----------------------------------------------------------------------
Procedure.i EcpLoadCurve(curve.i)
  Protected base.i
  Protected L.i
  Protected k.i
  Protected top.i
  If curve = EcpCurve
    ProcedureReturn 1
  EndIf
  If curve = 24
    base = ?EcpDataP384
    L = 48
    EcpNL = 12
  ElseIf curve = 25
    base = ?EcpDataP521
    L = 66
    EcpNL = 17
  Else
    ProcedureReturn 0
  EndIf
  EcpCurve = 0
  EcpPLen = L
  k = 0
  While k < #ECP_NREG
    EcpZero(k)
    k = k + 1
  Wend
  EcpDecode(#ECP_RP, base, L)
  EcpDecode(#ECP_RN, base + L, L)
  EcpDecode(#ECP_RX, base + 2 * L, L)          ; b, plain
  EcpDecode(#ECP_RY, base + 3 * L, L)          ; Gx, plain
  EcpDecode(#ECP_RZ, base + 4 * L, L)          ; Gy, plain
  EcpV[#ECP_RONE1 * #ECP_S] = 1

  ; the bit length of n
  k = EcpNL - 1
  While k > 0 And EcpV[#ECP_RN * #ECP_S + k] = 0
    k = k - 1
  Wend
  top = EcpV[#ECP_RN * #ECP_S + k]
  EcpNBits = k * 32
  While top <> 0
    EcpNBits = EcpNBits + 1
    top = top >> 1
  Wend

  EcpSetupSlot(0)
  EcpSetupSlot(1)
  EcpMul(#ECP_RONEP, #ECP_R2P, #ECP_RONE1, 0)  ; R mod p
  EcpMul(#ECP_RONEN, #ECP_R2N, #ECP_RONE1, 1)  ; R mod n
  EcpMul(#ECP_RB, #ECP_RX, #ECP_R2P, 0)
  EcpMul(#ECP_GX, #ECP_RY, #ECP_R2P, 0)
  EcpMul(#ECP_GY, #ECP_RZ, #ECP_R2P, 0)
  EcpCopy(#ECP_GZ, #ECP_RONEP)
  EcpCurve = curve
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  EcpDbl(x, y, z) - point doubling in place, Jacobian, a = -3
;  (Bernstein-Lange "dbl-2001-b"):
;    delta = Z^2, gamma = Y^2, beta = X*gamma,
;    alpha = 3*(X - delta)*(X + delta)
;    X3 = alpha^2 - 8*beta
;    Z3 = (Y + Z)^2 - gamma - delta
;    Y3 = alpha*(4*beta - X3) - 8*gamma^2
;  The point at infinity (Z = 0) doubles to Z3 = Y^2 - gamma = 0: it
;  stays at infinity with no special case.
; ----------------------------------------------------------------------
Procedure EcpDbl(x.i, y.i, z.i)
  EcpMul(#ECP_T1, z, z, 0)                     ; delta
  EcpMul(#ECP_T1 + 1, y, y, 0)                 ; gamma
  EcpMul(#ECP_T1 + 2, x, #ECP_T1 + 1, 0)       ; beta
  EcpSubMod(#ECP_T1 + 3, x, #ECP_T1, 0)
  EcpAddMod(#ECP_T1 + 4, x, #ECP_T1, 0)
  EcpMul(#ECP_T1 + 3, #ECP_T1 + 3, #ECP_T1 + 4, 0)
  EcpAddMod(#ECP_T1 + 5, #ECP_T1 + 3, #ECP_T1 + 3, 0)
  EcpAddMod(#ECP_T1 + 5, #ECP_T1 + 5, #ECP_T1 + 3, 0)    ; alpha
  ; Z3
  EcpAddMod(#ECP_T1 + 6, y, z, 0)
  EcpMul(#ECP_T1 + 6, #ECP_T1 + 6, #ECP_T1 + 6, 0)
  EcpSubMod(#ECP_T1 + 6, #ECP_T1 + 6, #ECP_T1 + 1, 0)
  EcpSubMod(z, #ECP_T1 + 6, #ECP_T1, 0)
  ; X3
  EcpAddMod(#ECP_T1 + 7, #ECP_T1 + 2, #ECP_T1 + 2, 0)    ; 2 beta
  EcpAddMod(#ECP_T1 + 7, #ECP_T1 + 7, #ECP_T1 + 7, 0)    ; 4 beta
  EcpAddMod(#ECP_T1 + 8, #ECP_T1 + 7, #ECP_T1 + 7, 0)    ; 8 beta
  EcpMul(#ECP_T1 + 9, #ECP_T1 + 5, #ECP_T1 + 5, 0)
  EcpSubMod(x, #ECP_T1 + 9, #ECP_T1 + 8, 0)
  ; Y3
  EcpSubMod(#ECP_T1 + 10, #ECP_T1 + 7, x, 0)
  EcpMul(#ECP_T1 + 10, #ECP_T1 + 5, #ECP_T1 + 10, 0)
  EcpMul(#ECP_T1 + 11, #ECP_T1 + 1, #ECP_T1 + 1, 0)       ; gamma^2
  EcpAddMod(#ECP_T1 + 11, #ECP_T1 + 11, #ECP_T1 + 11, 0)
  EcpAddMod(#ECP_T1 + 11, #ECP_T1 + 11, #ECP_T1 + 11, 0)
  EcpAddMod(#ECP_T1 + 11, #ECP_T1 + 11, #ECP_T1 + 11, 0)  ; 8 gamma^2
  EcpSubMod(y, #ECP_T1 + 10, #ECP_T1 + 11, 0)
EndProcedure

; ----------------------------------------------------------------------
;  EcpAddPt(x1, y1, z1, x2, y2, z2) - P1 = P1 + P2 in place, Jacobian
;  ("add-1998-cmo-2"), with every special case handled by name:
;    P2 at infinity -> P1 unchanged; P1 at infinity -> P1 = P2;
;    H = 0 and r = 0 (the same point) -> doubling;
;    H = 0 and r <> 0 (opposite points) -> the point at infinity.
;  P2 is not modified. The two triples must not overlap.
; ----------------------------------------------------------------------
Procedure EcpAddPt(x1.i, y1.i, z1.i, x2.i, y2.i, z2.i)
  Protected z2one.i
  If EcpIsZero(z2)
    ProcedureReturn
  EndIf
  If EcpIsZero(z1)
    EcpCopy(x1, x2)
    EcpCopy(y1, y2)
    EcpCopy(z1, z2)
    ProcedureReturn
  EndIf
  ; P2 AFFINE (its Z is the Montgomery one - G and Q always are): Z2Z2 = 1,
  ; U1 = X1 and S1 = Y1, five products fewer. Same formula otherwise.
  z2one = EcpEqual(z2, #ECP_RONEP)
  EcpMul(#ECP_T1, z1, z1, 0)                   ; Z1Z1
  If z2one
    EcpCopy(#ECP_T1 + 2, x1)                   ; U1
    EcpCopy(#ECP_T1 + 4, y1)                   ; S1
  Else
    EcpMul(#ECP_T1 + 1, z2, z2, 0)             ; Z2Z2
    EcpMul(#ECP_T1 + 2, x1, #ECP_T1 + 1, 0)    ; U1
    EcpMul(#ECP_T1 + 4, y1, z2, 0)
    EcpMul(#ECP_T1 + 4, #ECP_T1 + 4, #ECP_T1 + 1, 0)   ; S1
  EndIf
  EcpMul(#ECP_T1 + 3, x2, #ECP_T1, 0)          ; U2
  EcpMul(#ECP_T1 + 5, y2, z1, 0)
  EcpMul(#ECP_T1 + 5, #ECP_T1 + 5, #ECP_T1, 0)       ; S2
  EcpSubMod(#ECP_T1 + 6, #ECP_T1 + 3, #ECP_T1 + 2, 0) ; H
  EcpSubMod(#ECP_T1 + 7, #ECP_T1 + 5, #ECP_T1 + 4, 0) ; r
  If EcpIsZero(#ECP_T1 + 6)
    If EcpIsZero(#ECP_T1 + 7)
      EcpDbl(x1, y1, z1)
    Else
      EcpZero(z1)
    EndIf
    ProcedureReturn
  EndIf
  EcpMul(#ECP_T1 + 8, #ECP_T1 + 6, #ECP_T1 + 6, 0)   ; HH
  EcpMul(#ECP_T1 + 9, #ECP_T1 + 6, #ECP_T1 + 8, 0)   ; HHH
  EcpMul(#ECP_T1 + 10, #ECP_T1 + 2, #ECP_T1 + 8, 0)  ; V = U1*HH
  ; X3 = r^2 - HHH - 2V
  EcpMul(#ECP_T1 + 11, #ECP_T1 + 7, #ECP_T1 + 7, 0)
  EcpSubMod(#ECP_T1 + 11, #ECP_T1 + 11, #ECP_T1 + 9, 0)
  EcpSubMod(#ECP_T1 + 11, #ECP_T1 + 11, #ECP_T1 + 10, 0)
  EcpSubMod(#ECP_T1 + 11, #ECP_T1 + 11, #ECP_T1 + 10, 0)
  ; Y3 = r*(V - X3) - S1*HHH
  EcpSubMod(#ECP_T1 + 10, #ECP_T1 + 10, #ECP_T1 + 11, 0)
  EcpMul(#ECP_T1 + 10, #ECP_T1 + 7, #ECP_T1 + 10, 0)
  EcpMul(#ECP_T1 + 9, #ECP_T1 + 4, #ECP_T1 + 9, 0)
  EcpSubMod(y1, #ECP_T1 + 10, #ECP_T1 + 9, 0)
  ; Z3 = Z1*Z2*H
  If z2one
    EcpMul(z1, z1, #ECP_T1 + 6, 0)
  Else
    EcpMul(#ECP_T1, z1, z2, 0)
    EcpMul(z1, #ECP_T1, #ECP_T1 + 6, 0)
  EndIf
  EcpCopy(x1, #ECP_T1 + 11)
EndProcedure

; ----------------------------------------------------------------------
;  EcpOnCurve(x, y) - 1 if y^2 = x^3 - 3x + b (Montgomery values).
; ----------------------------------------------------------------------
Procedure.i EcpOnCurve(x.i, y.i)
  EcpMul(#ECP_T1, y, y, 0)                     ; y^2
  EcpMul(#ECP_T1 + 1, x, x, 0)
  EcpMul(#ECP_T1 + 1, #ECP_T1 + 1, x, 0)       ; x^3
  EcpSubMod(#ECP_T1 + 1, #ECP_T1 + 1, x, 0)
  EcpSubMod(#ECP_T1 + 1, #ECP_T1 + 1, x, 0)
  EcpSubMod(#ECP_T1 + 1, #ECP_T1 + 1, x, 0)    ; x^3 - 3x
  EcpAddMod(#ECP_T1 + 1, #ECP_T1 + 1, #ECP_RB, 0)
  ProcedureReturn EcpEqual(#ECP_T1, #ECP_T1 + 1)
EndProcedure

; ----------------------------------------------------------------------
;  EcpScalarRange(r) - 1 if 0 < r < n (plain).
; ----------------------------------------------------------------------
Procedure.i EcpScalarRange(r.i)
  If EcpIsZero(r)
    ProcedureReturn 0
  EndIf
  ProcedureReturn EcpLess(r, #ECP_RN)
EndProcedure

; ----------------------------------------------------------------------
;  EcpVrfyRaw(curve, hashAddr, hashLen, qAddr, qLen, sigAddr, sigLen)
;  -> 1 valid / 0 rejected / -1 curve not computed here. See the header.
; ----------------------------------------------------------------------
Procedure.i EcpVrfyRaw(curve.i, hashAddr.i, hashLen.i, qAddr.i, qLen.i, sigAddr.i, sigLen.i)
  Protected half.i
  Protected nbytes.i
  Protected k.i
  Protected i.i
  Protected b1.i
  Protected b2.i

  EcpRefusedAt = #ECP_AT_NONE
  If EcpLoadCurve(curve) = 0
    EcpLastErr = #ECP_ERR_CURVE
    ProcedureReturn -1
  EndIf
  EcpLastErr = #ECP_ERR_BADSIG

  ; ---- 1. r and s, each in [1, n-1] ----
  EcpRefusedAt = #ECP_AT_SHAPE
  If sigLen <= 0 Or (sigLen & 1) <> 0
    ProcedureReturn 0
  EndIf
  EcpRefusedAt = #ECP_AT_SCALAR
  half = sigLen >> 1
  If EcpDecode(#ECP_RR, sigAddr, half) = 0
    ProcedureReturn 0
  EndIf
  If EcpDecode(#ECP_RS, sigAddr + half, half) = 0
    ProcedureReturn 0
  EndIf
  If EcpScalarRange(#ECP_RR) = 0 Or EcpScalarRange(#ECP_RS) = 0
    ProcedureReturn 0
  EndIf

  ; ---- 2. the public key: 0x04 || X || Y, both below p, on the curve ----
  EcpRefusedAt = #ECP_AT_KEY
  If qLen <> 1 + 2 * EcpPLen
    ProcedureReturn 0
  EndIf
  If (PeekA(qAddr) & 255) <> 4
    ProcedureReturn 0
  EndIf
  If EcpDecode(#ECP_RX, qAddr + 1, EcpPLen) = 0 Or EcpDecode(#ECP_RY, qAddr + 1 + EcpPLen, EcpPLen) = 0
    ProcedureReturn 0
  EndIf
  If EcpLess(#ECP_RX, #ECP_RP) = 0 Or EcpLess(#ECP_RY, #ECP_RP) = 0
    ProcedureReturn 0
  EndIf
  EcpMul(#ECP_QX, #ECP_RX, #ECP_R2P, 0)
  EcpMul(#ECP_QY, #ECP_RY, #ECP_R2P, 0)
  EcpCopy(#ECP_QZ, #ECP_RONEP)
  EcpRefusedAt = #ECP_AT_CURVE
  If EcpOnCurve(#ECP_QX, #ECP_QY) = 0
    ProcedureReturn 0
  EndIf

  ; ---- 3. e = bits2int(hash) mod n ----
  nbytes = (EcpNBits + 7) >> 3
  k = hashLen
  If k > nbytes
    k = nbytes
  EndIf
  If k < 0
    k = 0
  EndIf
  EcpZero(#ECP_RE)
  If k > 0
    EcpDecode(#ECP_RE, hashAddr, k)
  EndIf
  If k * 8 > EcpNBits
    EcpShr(#ECP_RE, k * 8 - EcpNBits)
  EndIf
  If EcpLess(#ECP_RE, #ECP_RN) = 0
    EcpSubPlain(#ECP_RE, #ECP_RE, #ECP_RN)
  EndIf

  ; ---- 4. w = 1/s, u1 = e*w, u2 = r*w (mod n) ----
  EcpMul(#ECP_RZ, #ECP_RS, #ECP_R2N, 1)          ; s, Montgomery
  EcpInv(#ECP_RW, #ECP_RZ, 1)                    ; 1/s, Montgomery
  EcpMul(#ECP_RU1, #ECP_RE, #ECP_RW, 1)          ; e * w, plain
  EcpMul(#ECP_RU2, #ECP_RR, #ECP_RW, 1)          ; r * w, plain

  ; ---- 5. R = u1*G + u2*Q, interleaved double-and-add ----
  EcpCopy(#ECP_SX, #ECP_GX)
  EcpCopy(#ECP_SY, #ECP_GY)
  EcpCopy(#ECP_SZ, #ECP_GZ)
  EcpAddPt(#ECP_SX, #ECP_SY, #ECP_SZ, #ECP_QX, #ECP_QY, #ECP_QZ)
  EcpCopy(#ECP_AX, #ECP_RONEP)
  EcpCopy(#ECP_AY, #ECP_RONEP)
  EcpZero(#ECP_AZ)                               ; at infinity
  i = EcpNBits - 1
  While i >= 0
    EcpDbl(#ECP_AX, #ECP_AY, #ECP_AZ)
    b1 = EcpBit(#ECP_RU1, i)
    b2 = EcpBit(#ECP_RU2, i)
    If b1 <> 0 And b2 <> 0
      EcpAddPt(#ECP_AX, #ECP_AY, #ECP_AZ, #ECP_SX, #ECP_SY, #ECP_SZ)
    ElseIf b1 <> 0
      EcpAddPt(#ECP_AX, #ECP_AY, #ECP_AZ, #ECP_GX, #ECP_GY, #ECP_GZ)
    ElseIf b2 <> 0
      EcpAddPt(#ECP_AX, #ECP_AY, #ECP_AZ, #ECP_QX, #ECP_QY, #ECP_QZ)
    EndIf
    i = i - 1
  Wend
  EcpRefusedAt = #ECP_AT_INFINITY
  If EcpIsZero(#ECP_AZ)
    ProcedureReturn 0
  EndIf

  ; ---- 6. x(R) = X / Z^2, out of Montgomery form, mod n; compare ----
  EcpInv(#ECP_RZ, #ECP_AZ, 0)
  EcpMul(#ECP_RZ, #ECP_RZ, #ECP_RZ, 0)
  EcpMul(#ECP_RX, #ECP_AX, #ECP_RZ, 0)
  EcpMul(#ECP_RX, #ECP_RX, #ECP_RONE1, 0)        ; leave Montgomery form
  If EcpLess(#ECP_RX, #ECP_RN) = 0
    EcpSubPlain(#ECP_RX, #ECP_RX, #ECP_RN)
  EndIf
  If EcpEqual(#ECP_RX, #ECP_RR)
    EcpLastErr = #ECP_ERR_OK
    EcpRefusedAt = #ECP_AT_NONE
    ProcedureReturn 1
  EndIf
  EcpRefusedAt = #ECP_AT_MISMATCH
  ProcedureReturn 0
EndProcedure

; ----------------------------------------------------------------------
;  THE CURVE TABLES - p, n, b, Gx, Gy, each L big-endian bytes (48 for
;  P-384, 66 for P-521), from SEC 2 / FIPS 186-4 D.1.2. Reached with
;  ?label and PeekA - no Read cursor moves. tools/a64/a64_ecp_check.py
;  compares every byte with OpenSSL's `ecparam -param_enc explicit` and
;  checks G on the curve and n*G at infinity before it runs anything.
; ----------------------------------------------------------------------
DataSection
  EcpDataP384:
  ; p
  Data.a $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF
  Data.a $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FE
  Data.a $FF, $FF, $FF, $FF, $00, $00, $00, $00, $00, $00, $00, $00, $FF, $FF, $FF, $FF
  ; n
  Data.a $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF
  Data.a $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $C7, $63, $4D, $81, $F4, $37, $2D, $DF
  Data.a $58, $1A, $0D, $B2, $48, $B0, $A7, $7A, $EC, $EC, $19, $6A, $CC, $C5, $29, $73
  ; b
  Data.a $B3, $31, $2F, $A7, $E2, $3E, $E7, $E4, $98, $8E, $05, $6B, $E3, $F8, $2D, $19
  Data.a $18, $1D, $9C, $6E, $FE, $81, $41, $12, $03, $14, $08, $8F, $50, $13, $87, $5A
  Data.a $C6, $56, $39, $8D, $8A, $2E, $D1, $9D, $2A, $85, $C8, $ED, $D3, $EC, $2A, $EF
  ; Gx
  Data.a $AA, $87, $CA, $22, $BE, $8B, $05, $37, $8E, $B1, $C7, $1E, $F3, $20, $AD, $74
  Data.a $6E, $1D, $3B, $62, $8B, $A7, $9B, $98, $59, $F7, $41, $E0, $82, $54, $2A, $38
  Data.a $55, $02, $F2, $5D, $BF, $55, $29, $6C, $3A, $54, $5E, $38, $72, $76, $0A, $B7
  ; Gy
  Data.a $36, $17, $DE, $4A, $96, $26, $2C, $6F, $5D, $9E, $98, $BF, $92, $92, $DC, $29
  Data.a $F8, $F4, $1D, $BD, $28, $9A, $14, $7C, $E9, $DA, $31, $13, $B5, $F0, $B8, $C0
  Data.a $0A, $60, $B1, $CE, $1D, $7E, $81, $9D, $7A, $43, $1D, $7C, $90, $EA, $0E, $5F
  EcpDataP521:
  ; p
  Data.a $01, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF
  Data.a $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF
  Data.a $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF
  Data.a $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF
  Data.a $FF, $FF
  ; n
  Data.a $01, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF
  Data.a $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF
  Data.a $FF, $FA, $51, $86, $87, $83, $BF, $2F, $96, $6B, $7F, $CC, $01, $48, $F7, $09
  Data.a $A5, $D0, $3B, $B5, $C9, $B8, $89, $9C, $47, $AE, $BB, $6F, $B7, $1E, $91, $38
  Data.a $64, $09
  ; b
  Data.a $00, $51, $95, $3E, $B9, $61, $8E, $1C, $9A, $1F, $92, $9A, $21, $A0, $B6, $85
  Data.a $40, $EE, $A2, $DA, $72, $5B, $99, $B3, $15, $F3, $B8, $B4, $89, $91, $8E, $F1
  Data.a $09, $E1, $56, $19, $39, $51, $EC, $7E, $93, $7B, $16, $52, $C0, $BD, $3B, $B1
  Data.a $BF, $07, $35, $73, $DF, $88, $3D, $2C, $34, $F1, $EF, $45, $1F, $D4, $6B, $50
  Data.a $3F, $00
  ; Gx
  Data.a $00, $C6, $85, $8E, $06, $B7, $04, $04, $E9, $CD, $9E, $3E, $CB, $66, $23, $95
  Data.a $B4, $42, $9C, $64, $81, $39, $05, $3F, $B5, $21, $F8, $28, $AF, $60, $6B, $4D
  Data.a $3D, $BA, $A1, $4B, $5E, $77, $EF, $E7, $59, $28, $FE, $1D, $C1, $27, $A2, $FF
  Data.a $A8, $DE, $33, $48, $B3, $C1, $85, $6A, $42, $9B, $F9, $7E, $7E, $31, $C2, $E5
  Data.a $BD, $66
  ; Gy
  Data.a $01, $18, $39, $29, $6A, $78, $9A, $3B, $C0, $04, $5C, $8A, $5F, $B4, $2C, $7D
  Data.a $1B, $D9, $98, $F5, $44, $49, $57, $9B, $44, $68, $17, $AF, $BD, $17, $27, $3E
  Data.a $66, $2C, $97, $EE, $72, $99, $5E, $F4, $26, $40, $C5, $50, $B9, $01, $3F, $AD
  Data.a $07, $61, $35, $3C, $70, $86, $A2, $72, $C2, $40, $88, $BE, $94, $76, $9F, $D1
  Data.a $66, $50
EndDataSection

; ======================================================================
;  rsa.pi4 - RSA signature VERIFY (PKCS#1 v1.5 and PSS), ON THE
;            RASPBERRY PI 4 (BCM2711, AArch64)
; ======================================================================
;
;  Translated from BearSSL (c) 2017-2018 Thomas Pornin - MIT licence.
;  The notice ships as licenses/BearSSL-LICENSE.txt (release condition).
;
;     XIncludeFile "RaspberryPi4/Lib/rsa.pi4"
;
;  RSA signature verification for a TLS client: the two schemes a chain
;  can carry - PKCS#1 v1.5 (RFC 8017 EMSA-PKCS1-v1_5) and PSS (EMSA-PSS,
;  mandatory to verify in TLS 1.3).  VERIFY ONLY: there is no private
;  key, no signing, no key generation.  Moduli up to 4096 bits.
;  Translated from the BearSSL "i15" public-key path to the house
;  dialect.  Reads-and-translates only: no C is linked, no foreign ABI
;  is followed.
;
;  API (buffers are passed by ADDRESS; @yourArray gives the base).
;  INSTALL THE KEY FIRST - see "THE NINTH ARGUMENT" below for why this
;  family's entry points take four arguments fewer than the Picos':
;
;    RsaSetPubKey(nPtr, nLen, ePtr, eLen)
;        Install the public key the next verification uses.  Big-endian
;        byte strings, NOT copied - both must stay valid until the
;        verify returns.  With nothing installed every verify returns 0.
;
;    RsaVrfy(sigAddr, sigLen, hashOidAddr, hashLen, outAddr) -> 1 / 0
;        The CERTIFICATE SEAM entry point.  PKCS#1 v1.5 signature
;        RECOVERY: writes the recovered hash (hashLen bytes) to outAddr
;        and leaves the comparison to the caller, which already holds
;        the hash it computed.  hashOidAddr is length-prefixed
;        ({len, oid...}) - the same encoding the chain engine's bytecode
;        data block uses - or 0 for the raw form.  Never returns -1:
;        that value is the chain engine's own answer from the stub it
;        compiles in when this module is not in the build.
;    RsaPkcs1Vrfy(sig, sigLen, hashOid, hashLen, expectedHash) -> 1 / 0
;        Recovers the padded hash from sig via the public operation,
;        checks the PKCS#1 v1.5 DigestInfo wrapper against hashOid, and
;        compares the recovered hash to expectedHash (hashLen bytes).
;        hashOid is a length-prefixed encoded OID ({len, oid...}); pass
;        0 for the raw (no DigestInfo) mode.  RsaOidSha256() returns the
;        SHA-256 OID for the common case.
;    RsaPssVrfy(sig, sigLen, msgHash, hashLen, saltLen) -> 1 / 0
;        Recovers the EM and runs EMSA-PSS verification with SHA-256 as
;        both the data hash and the MGF1 hash (the TLS profile's only
;        choice).  msgHash is the caller's message hash (hashLen bytes);
;        saltLen is the expected salt length.
;    RsaOidSha256() -> address of the length-prefixed SHA-256 DigestInfo
;        OID {09 60 86 48 01 65 03 04 02 01}.
;
;  > EVERY ONE OF THOSE VERDICTS IS A PLAIN 0 OR 1, AT FULL 64-BIT
;  > WIDTH, and a caller may test it as "= 1" or as "<> 0" and get the
;  > same answer.  That is a property of this file worth stating out
;  > loud, because gcm.pi4's GcmDecrypt hands back a MASK and cannot be
;  > tested that way.  See the fifth shape below for how it is proven.
;
;  REQUIRES bignum AND sha256, INCLUDED BEFORE THIS FILE.  A library
;  never includes a library (house rule 10 - the MAIN file lists them,
;  one per line, in order):
;      XIncludeFile "Anvil/Core/sha256.pbi"
;      XIncludeFile "RaspberryPi4/Lib/bignum.pi4"
;      XIncludeFile "RaspberryPi4/Lib/rsa.pi4"
;  NOTE THE FIRST PATH.  On this family sha256 lives in Anvil/Core, not
;  RaspberryPi4/Lib: it is pure computation with no chip in it and the
;  Arduino UNO Q includes the same file.  The public operation rides
;  bignum's i15 core (BnDecode, BnNinv15, BnModpow, BnEncode, and the
;  word helpers BnGw/BnSw/BnGt/BnLt/BnEq/BnMux/BnBitLen32); PSS mask
;  generation and H' recomputation ride sha256 (Sha256Begin/Update/End).
;  If either is missing the build fails loudly with an
;  undefined-procedure error, which names the gap.
;
;  VERIFY OPERATES ON PUBLIC DATA.  A signature and a public key are
;  public; there is no secret to leak, so the padding walk here uses
;  ordinary length-driven control flow rather than the branchless
;  masking the secret-key core demands.  The heavy lifting (the modular
;  exponentiation) is bignum's constant-time ladder regardless.
;
;  THIS FILE TURNS EnableExplicit ON FOR YOUR PROGRAM TOO.  The pragma
;  below is not file-scoped; every variable compiled after this include
;  must be declared before use.  (sha256 and bignum, included before
;  this file, already set it.)
;
;  ======================================================================
;   THE NINTH ARGUMENT - THE ONLY REASON THIS FILE DIVERGES AT ALL
;  ======================================================================
;
;  rsa.pico2's three public entry points each declare NINE parameters.
;  THE AArch64 BACKEND PASSES EIGHT, a0 through a7, and refuses the
;  ninth outright - RaspberryPi4/IRCore_A64.pbi:3100 for a declaration
;  and :4926 for a call:
;
;      "phase 1 passes at most 8 - a0 through a7 (ds p. 236).
;       Parameters 9 and up would have to travel on the stack, and that
;       path is not implemented on this backend yet.  Pass a structure
;       by address instead, or split the procedure."
;
;  That refusal is deliberate and the backend argues it in place: the
;  ARM file spills to the stack and has been exercised on silicon, this
;  one has not, and "a second calling convention that nothing has
;  tested is a wrong answer with two places to hide".
;
;  rsa IS THE FIRST MODULE IN THE TREE TO CROSS THAT LINE.  Nothing
;  else, on any target, declares more than eight parameters - the next
;  widest are GcmEncrypt, GcmDecrypt and HkdfExpandLabel at exactly
;  eight.  So this is a real lane finding and not a local nuisance: the
;  day the A64 stack path lands, this file can go back to nine and the
;  split below can be deleted.
;
;  THE REMEDY IS THE SECOND ONE THE COMPILER NAMES: split the procedure.
;  The first - a structure by address - is closed twice over, by the
;  house rule against structures and by the fact that a four-word block
;  on this part has EIGHT-BYTE elements, which is shape 1 aimed at
;  exactly the caller least likely to expect it.
;
;  The four PUBLIC KEY arguments are the same four in all three entry
;  points and contiguous in all three, so they move together:
;
;      RsaSetPubKey(nPtr, nLen, ePtr, eLen)   <- the ONE addition
;      RsaVrfy      loses nAddr, nLen, eAddr, eLen   9 -> 5
;      RsaPkcs1Vrfy loses nPtr,  nLen, ePtr,  eLen   9 -> 5
;      RsaPssVrfy   loses nPtr,  nLen, ePtr,  eLen   9 -> 5
;
;  Nothing else moves.  RsaPublic (six parameters) and RsaPssVrfyUnpad
;  (six) still take the key EXPLICITLY, because six is under the limit
;  and an internal procedure reading a Global it did not have to would
;  be a gratuitous divergence.  The declaration order of all eleven
;  shared procedures is unchanged.
;
;  WHAT IT COSTS.  The module becomes stateful in the key, which costs
;  nothing it had not already spent: RsaSig, RsaM, RsaA, RsaT1, RsaT2,
;  RsaHashOut, RsaPad2 and RsaTmp are all Globals in every family, so
;  no copy of this module has ever been re-entrant and no caller could
;  ever have had two verifications in flight.  The key is public, so
;  the four new Globals need no wipe.  Forgetting RsaSetPubKey is safe
;  rather than silent: RsaKeyNLen stays 0, RsaPublic refuses a
;  zero-length modulus, and the verify returns 0.
;
;  All four divergences are declared in tools/check_tls_twins.py's
;  A64_MODULES, where a reviewer reading the twins will see them.
;
;  ======================================================================
;   .i IS 64 BITS HERE.  THE FOUR-SHAPE AUDIT, PLUS THE FIFTH
;  ======================================================================
;
;  THE HEADLINE: NOT ONE LINE OF THIS FILE CHANGED FOR THE WORD SIZE.
;  Every edit against rsa.pico2's core is the arity split above and
;  nothing else.  That is a measured finding rather than an untried
;  assumption - the five shapes were looked for one at a time and every
;  finding is written down here, "not present" included, because a
;  silence is not a result.  For contrast: 35% of sha256's core
;  diverges, gcm needed a shift primitive and a rewritten verdict, and
;  bignum needed six sign tests moved from bit 31 to bit 63.  This file
;  needed none of it, and the reasons below are specific.
;
;  SHAPE 1 - AN ARRAY ELEMENT IS EIGHT BYTES, NOT FOUR.
;      NOT PRESENT.  The core declares eleven arrays and not one of them
;      is `.i`.  The i15 big integers - RsaM, RsaA, RsaT1, RsaT2 - are
;      `.w`, a 2-byte stride on this part exactly as on the Picos, which
;      is what bignum.pi4's PeekU/PokeW accessors address.  Everything
;      else (RsaSig, RsaHashOut, RsaPad2, RsaTmp, RsaMgfCnt, RsaMgfDig,
;      RsaOid) is `.a`, one byte on every family.  The only `.i` here
;      are scalars: RsaOidReady and the four key Globals.  RsaClear's
;      own stride is written `PokeW(x + (idx << 1), 0)`, which is two
;      bytes by construction and not by inference from a type.
;        > IT IS THE LIBRARY'S OWN DECLARATION THAT MATTERS, NOT YOURS.
;        > Every buffer this API takes is a plain BYTE string, so a
;        > caller cannot get the i15 stride wrong even by trying.  The
;        > shape lands inside this file, and mutations M0 and M1 in the
;        > gate are exactly that - RsaM declared `.i`, and RsaClear
;        > striding four bytes - so the finding is swept, not asserted.
;
;  SHAPE 2 - PeekL SIGN-EXTENDS.
;      NOT PRESENT.  There is no PeekL and no PeekB in this file.  Every
;      byte arrives as `PeekA(p) & 255` and every 16-bit word arrives
;      through bignum's BnGw, which is PeekU.  The `& 255` is redundant
;      after PeekA and is kept because it is what the 32-bit copies
;      write and the copies are meant to read side by side.
;
;  SHAPE 3 - `<<` DOES NOT DISCARD AT BIT 31.
;      PRESENT NOWHERE THAT MATTERS, and here is every left shift in the
;      file with its bound:
;        idx << 1     RsaClear's word stride, idx < 300.
;        mlen << 1    a word count, at most 274 for 4096 bits.
;        byteVal << accLen   RsaDecodeMod's accumulator.  accLen at the
;                     shift is one of 0,8,1,9,2,10,3,11,4,12,5,13,6,14,7
;                     - never above 14 - and byteVal is a byte, so the
;                     widest value in the whole file is 255 << 14, under
;                     2^23.
;        r << 1       RsaDecodeMod's comparison collapse.  See below;
;                     this is the ONE that is interesting.
;        (nLen - u - 1) << 3    a bit length, at most 32768.
;        $FF << (nBitlen & 7)   at most $7F80, and it is immediately
;                     ANDed with a byte.
;      Nothing here ever depended on a shift falling off the top of a
;      32-bit register, so nothing needed a mask added.
;
;  SHAPE 4 - A 32-BIT COUNTER NEVER WRAPS.
;      NOT PRESENT.  The only counter is RsaMgf1Xor's MGF1 block index,
;      which reaches 15 for a 4096-bit modulus.  Nothing is waiting for
;      it to wrap.
;
;  ---- THE FIFTH THING, WHICH IS THE ONE THAT ACTUALLY BITES ----------
;
;  `>> 31` AS A SIGN TEST and `x ! $FFFFFFFF` AS A LOGICAL NOT.  This is
;  what made gcm's 32-bit `neq ! $FFFFFFFF` return $FFFFFFFF00000000 -
;  "not zero" - for a FORGED TAG, and RSA verify is a verdict function,
;  so it was searched for first and hardest.
;
;      NEITHER SPELLING OCCURS ANYWHERE IN THIS FILE.  There is no
;      `>> 31`, no `>> 63`, and no `$FFFFFFFF` at all.  Every verdict in
;      the core is built the other way round: an accumulator is ORed up
;      out of byte-masked differences and then tested against zero with
;      an ordinary `If`, which yields a literal 1 or a literal 0.  The
;      eight verdict sites, all checked:
;        RsaMemEq          diff is an OR of `(byte ! byte)`, so it can
;                          never exceed 255; `If diff = 0` then returns
;                          the literal 1 or 0.
;        RsaDecodeMod      returns `r & 1`.  r is 0 or an all-ones mask;
;                          the mask is what the second pass ANDs into
;                          the words, and `& 1` narrows the answer.
;        RsaPublic         `r = m0i & 1` ANDed with the above - two 0/1
;                          values.
;        RsaPkcs1SigUnpad  literal 0 or 1 on every path.
;        RsaVrfy           literal 0, or RsaPkcs1SigUnpad's 0/1.
;        RsaPkcs1Vrfy      literal 0, or RsaMemEq's 0/1.
;        RsaPssVrfyUnpad   r is an OR of byte-masked values; `If r = 0`
;                          returns the literal 1 or 0.
;        RsaPssVrfy        literal 0, or RsaPssVrfyUnpad's 0/1.
;
;      SO THE DANGEROUS SHAPE IS ABSENT, AND THAT IS ASSERTED BY A
;      MUTATION AND NOT BY THIS PARAGRAPH.  tools/a64/a64_rsa_check.py
;      PLANTS the gcm shape into two of those sites - RsaPssVrfyUnpad's
;      reject path (M2) and RsaMemEq's mismatch path (M3) - and the
;      sweep must kill both.  M2 is the exact defect the first A64 GCM
;      gate could not see: it returns $FFFFFFFF00000000, whose LOW 32
;      BITS ARE ZERO, so a gate that stored the verdict with PokeN would
;      read a clean 0 and call the forgery correctly rejected.  This
;      gate stores every verdict with PokeI and unpacks it with "<Q".
;
;  ---- RsaDecodeMod's COMPARISON COLLAPSE, WHICH SURVIVES BY A MASK ---
;
;  The one place in this file where a 32-bit assumption is close enough
;  to the surface to be worth a paragraph:
;
;      r = (r >> 1) & $7FFFFFFF
;      r = r | (r << 1)
;
;  r arrives as -1, 0 or +1 (source below, equal to, or above the
;  modulus) and must leave as an all-ones MASK for "below", zero
;  otherwise, because the second pass writes `r & xw` into every word.
;  On a 32-bit `.i` that runs -1 -> $7FFFFFFF -> $FFFFFFFF, which is -1
;  again.  On this part it runs -1 -> $000000007FFFFFFF ->
;  $00000000FFFFFFFF, a DIFFERENT bit pattern that is nonetheless the
;  same mask everywhere it is used: xw is 15 bits, so `r & xw` is xw
;  either way, and `r & 1` is 1 either way.  Mutation M4 removes the
;  `& $7FFFFFFF`; it is a RECORDED EXPECTED SURVIVOR with its argument
;  written out in the table, because -1 >> 1 is still -1 and -1 & xw is
;  still xw.  Recorded rather than deleted, because the 32-bit copies
;  need that mask for a different reason - there the shift would smear
;  the sign - and the two files are meant to read the same way.
;
;  ======================================================================
;   CONSTANT TIME - DELIBERATELY NOT GATED, AND HERE IS WHY
;  ======================================================================
;
;  A signature and a public key are public data.  There is no secret in
;  a verify, so there is nothing for a timing channel to carry, and the
;  32-bit families have no constant-time gate for this module either -
;  tools/ct_ab.py is driven for the record layer and the AEAD, and rsa
;  appears in tools/gen_tls13_ct.py only as an include, never as a
;  measured primitive.  tools/a64/a64_rsa_check.py therefore has NO
;  --timing flag: an invented one would measure something nobody has
;  claimed, and would suggest a property this code does not promise -
;  the padding walk branches on lengths and on byte values, on purpose,
;  exactly as the .pico2 copy does.  The part of this path that DOES
;  touch a secret in other protocols is the modular exponentiation, and
;  it is cycle-equal under tools/a64/a64_bignum_check.py --timing.
;
;  PROVEN: builds clean for pi4 and passes tools/a64/a64_rsa_check.py on
;  the SAME vectors as the three 32-bit families (the gate imports
;  tools/gen_rsa_vectors.py rather than carrying a copy), mutation-swept
;  under --mutate, and structurally twinned under
;  tools/check_tls_twins.py --cross rsa.  NOTHING HERE HAS RUN ON
;  SILICON.
; ======================================================================
; ==== PORTABLE CORE A64 BEGIN ====
EnableExplicit

; The largest modulus handled: 4096 bits = 512 bytes. An i15 buffer needs
; one header word plus ceil(bits/15) value words plus a guard word; 300
; 16-bit words covers 4096 bits with room to spare.
#RsaMaxBytes = 512
#RsaMaxWords = 300

; ----------------------------------------------------------------------
;  STATE - flat Global arrays, house style (no structures). Every buffer
;  is sized for the 4096-bit worst case. i15 big integers are 16-bit-word
;  arrays (.w, 2-byte stride) shared with bignum's PeekU/PokeW accessors.
; ----------------------------------------------------------------------
Global Dim RsaSig.a[#RsaMaxBytes]    ; recovered signature / working bytes
Global Dim RsaM.w[#RsaMaxWords]      ; modulus, i15
Global Dim RsaA.w[#RsaMaxWords]      ; value to exponentiate, then result
Global Dim RsaT1.w[#RsaMaxWords]     ; modpow scratch
Global Dim RsaT2.w[#RsaMaxWords]     ; modpow scratch
Global Dim RsaHashOut.a[64]          ; hash recovered from a PKCS#1 wrapper
Global Dim RsaPad2.a[64]             ; PKCS#1 DigestInfo template to match
Global Dim RsaTmp.a[64]             ; PSS H' recomputation scratch
Global Dim RsaMgfCnt.a[4]           ; MGF1 big-endian block counter
Global Dim RsaMgfDig.a[32]          ; MGF1 per-block digest
Global Dim RsaOid.a[16]             ; SHA-256 DigestInfo OID, filled once
Global RsaOidReady.i

; ----------------------------------------------------------------------
;  THE INSTALLED PUBLIC KEY - FOUR GLOBALS THE 32-BIT COPIES DO NOT HAVE.
;  RsaSetPubKey() writes them and the three entry points read them; see
;  the header's "THE NINTH ARGUMENT" for why they exist. Nothing here is
;  secret - a public key is public - so they are plain Globals with no
;  wipe, unlike the key material in aes.pi4.
; ----------------------------------------------------------------------
Global RsaKeyN.i                     ; modulus, big-endian bytes
Global RsaKeyNLen.i
Global RsaKeyE.i                     ; public exponent, big-endian bytes
Global RsaKeyELen.i

; ----------------------------------------------------------------------
;  RsaClear(x, nwords) - zero nwords 16-bit words of an i15 buffer. The
;  modpow scratch and the value buffer are cleared before each public
;  operation so the guard word beyond the decoded value is a real zero
;  (bignum's ladder reads one word past the announced length).
; ----------------------------------------------------------------------
Procedure RsaClear(x.i, nwords.i)
  Protected idx.i
  idx = 0
  While idx < nwords
    PokeW(x + (idx << 1), 0)
    idx = idx + 1
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  RsaMemEq(pa, pb, n) - 1 if the n bytes at pa and pb are all equal, else
;  0. Reads every byte (the difference is accumulated, not short-circuited)
;  so a match and a near-match cost the same.
; ----------------------------------------------------------------------
Procedure.i RsaMemEq(pa.i, pb.i, n.i)
  Protected idx.i
  Protected diff.i
  diff = 0
  idx = 0
  While idx < n
    diff = diff | ((PeekA(pa + idx) & 255) ! (PeekA(pb + idx) & 255))
    idx = idx + 1
  Wend
  If diff = 0
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

; ----------------------------------------------------------------------
;  RsaOidSha256() - address of the length-prefixed encoded SHA-256 OID
;  {09 60 86 48 01 65 03 04 02 01}: the first byte is the OID content
;  length (9), the rest is 2.16.840.1.101.3.4.2.1. Filled once and cached;
;  no DataSection, so it never disturbs a Read cursor the caller may hold.
; ----------------------------------------------------------------------
Procedure.i RsaOidSha256()
  If RsaOidReady = 0
    RsaOid[0] = $09
    RsaOid[1] = $60
    RsaOid[2] = $86
    RsaOid[3] = $48
    RsaOid[4] = $01
    RsaOid[5] = $65
    RsaOid[6] = $03
    RsaOid[7] = $04
    RsaOid[8] = $02
    RsaOid[9] = $01
    RsaOidReady = 1
  EndIf
  ProcedureReturn @RsaOid
EndProcedure

; ----------------------------------------------------------------------
;  RsaMgf1Xor(dataPtr, dataLen, seedPtr, seedLen) - MGF1 with SHA-256,
;  XORed into the data in place (RFC 8017 MGF1). Blocks are SHA-256 of
;  seed || I2OSP(counter, 4), counter big-endian from 0. hlen is fixed at
;  32 (this profile's only hash).
; ----------------------------------------------------------------------
Procedure RsaMgf1Xor(dataPtr.i, dataLen.i, seedPtr.i, seedLen.i)
  Protected off.i
  Protected cnt.i
  Protected v.i
  Protected hlen.i
  hlen = 32
  off = 0
  cnt = 0
  While off < dataLen
    Sha256Begin()
    Sha256Update(seedPtr, seedLen)
    RsaMgfCnt[0] = (cnt >> 24) & 255
    RsaMgfCnt[1] = (cnt >> 16) & 255
    RsaMgfCnt[2] = (cnt >> 8) & 255
    RsaMgfCnt[3] = cnt & 255
    Sha256Update(@RsaMgfCnt, 4)
    Sha256End(@RsaMgfDig)
    v = 0
    While v < hlen
      If (off + v) < dataLen
        PokeB(dataPtr + off + v, (PeekA(dataPtr + off + v) & 255) ! (RsaMgfDig[v] & 255))
      EndIf
      v = v + 1
    Wend
    off = off + hlen
    cnt = cnt + 1
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  RsaDecodeMod(x, src, len, m) - decode the big-endian byte string src
;  into i15 integer x, reduced modulo m, with x's announced length set to
;  m's. Returns 1 if the source value was strictly lower than m (a proper
;  signature representative), 0 otherwise. Two passes: the first decides
;  whether the value fits, the second writes the (masked) words.
;
;  This is the one i15 primitive the RSA public operation needs that the
;  verify-only bignum core does not expose (BnDecodeReduce reduces but
;  does not report the < m result), so it is translated here, on top of
;  bignum's word helpers. The comparison-collapse shift touches only
;  values 0/1/-1, for which arithmetic and logical >> agree.
; ----------------------------------------------------------------------
Procedure.i RsaDecodeMod(x.i, src.i, len.i, m.i)
  Protected mlen.i
  Protected tlen.i
  Protected pass.i
  Protected r.i
  Protected u.i
  Protected v.i
  Protected acc.i
  Protected accLen.i
  Protected byteVal.i
  Protected xw.i
  Protected cc.i
  mlen = (BnGw(m, 0) + 15) >> 4
  tlen = mlen << 1
  If tlen < len
    tlen = len
  EndIf
  tlen = tlen + 4
  r = 0
  pass = 0
  While pass < 2
    v = 1
    acc = 0
    accLen = 0
    u = 0
    While u < tlen
      If u < len
        byteVal = PeekA(src + len - 1 - u) & 255
      Else
        byteVal = 0
      EndIf
      acc = acc | (byteVal << accLen)
      accLen = accLen + 8
      If accLen >= 15
        xw = acc & $7FFF
        accLen = accLen - 15
        acc = (byteVal >> (8 - accLen)) & $FF
        If v <= mlen
          If pass <> 0
            BnSw(x, v, r & xw)
          Else
            cc = BnGt(xw, BnGw(m, v)) - BnLt(xw, BnGw(m, v))
            r = BnMux(BnEq(cc, 0), r, cc)
          EndIf
        Else
          If pass = 0
            r = BnMux(BnEq(xw, 0), r, 1)
          EndIf
        EndIf
        v = v + 1
      EndIf
      u = u + 1
    Wend
    r = (r >> 1) & $7FFFFFFF
    r = r | (r << 1)
    pass = pass + 1
  Wend
  BnSw(x, 0, BnGw(m, 0))
  ProcedureReturn r & 1
EndProcedure

; ----------------------------------------------------------------------
;  RsaPublic(x, xlen, nPtr, nLen, ePtr, eLen) - the RSA public operation:
;  x[] (xlen big-endian bytes) is replaced in place by x^e mod n, and the
;  return is 1 only if x was a proper representative (0 <= x < n) and the
;  modulus was odd. Leading zero bytes of the modulus are stripped; xlen
;  must equal the resulting modulus length. e is a big-endian byte string.
; ----------------------------------------------------------------------
Procedure.i RsaPublic(x.i, xlen.i, nPtr.i, nLen.i, ePtr.i, eLen.i)
  Protected r.i
  Protected m0i.i
  While nLen > 0 And (PeekA(nPtr) & 255) = 0
    nPtr = nPtr + 1
    nLen = nLen - 1
  Wend
  If nLen = 0 Or nLen > #RsaMaxBytes Or xlen <> nLen
    ProcedureReturn 0
  EndIf
  RsaClear(@RsaM, #RsaMaxWords)
  RsaClear(@RsaA, #RsaMaxWords)
  RsaClear(@RsaT1, #RsaMaxWords)
  RsaClear(@RsaT2, #RsaMaxWords)
  BnDecode(@RsaM, nPtr, nLen)
  m0i = BnNinv15(BnGw(@RsaM, 1))
  r = m0i & 1
  r = r & RsaDecodeMod(@RsaA, x, xlen, @RsaM)
  BnModpow(@RsaA, ePtr, eLen, @RsaM, m0i, @RsaT1, @RsaT2)
  BnEncode(x, xlen, @RsaA)
  ProcedureReturn r
EndProcedure

; ----------------------------------------------------------------------
;  RsaPkcs1SigUnpad(sig, sigLen, hashOid, hashLen, hashOut) - check the
;  PKCS#1 v1.5 wrapper on a recovered padded value and extract the hash.
;  Expected format:
;    00 01 FF..FF 00 30 x1 30 x2 06 x3 OID [05 00] 04 x4 HASH
;  hashOid is {len, oid...} or 0 for the raw form. Returns 1 on a good
;  wrapper. sig is the value AFTER the public operation. Public data, so
;  the walk uses plain control flow.
; ----------------------------------------------------------------------
Procedure.i RsaPkcs1SigUnpad(sig.i, sigLen.i, hashOid.i, hashLen.i, hashOut.i)
  Protected u.i
  Protected x2.i
  Protected x3.i
  Protected padLen.i
  Protected zlen.i
  Protected idx.i
  Protected done.i
  If sigLen < 11
    ProcedureReturn 0
  EndIf
  ; 00 01 then eight 0xFF bytes (the fixed pad1 prefix).
  If (PeekA(sig) & 255) <> $00
    ProcedureReturn 0
  EndIf
  If (PeekA(sig + 1) & 255) <> $01
    ProcedureReturn 0
  EndIf
  idx = 2
  While idx < 10
    If (PeekA(sig + idx) & 255) <> $FF
      ProcedureReturn 0
    EndIf
    idx = idx + 1
  Wend
  ; count the remaining 0xFF bytes.
  u = 10
  done = 0
  While u < sigLen And done = 0
    If (PeekA(sig + u) & 255) <> $FF
      done = 1
    Else
      u = u + 1
    EndIf
  Wend
  If hashOid = 0
    If (sigLen - u) <> (hashLen + 1) Or (PeekA(sig + u) & 255) <> $00
      ProcedureReturn 0
    EndIf
  Else
    x3 = PeekA(hashOid) & 255
    ; The template is assembled in RsaPad2 (65 bytes); the highest index it
    ; touches is x3 + 10. Refuse an OID length that would run past the end
    ; rather than writing over whatever follows.
    If x3 > 48
      ProcedureReturn 0
    EndIf
    padLen = x3 + 9
    idx = 0
    While idx < padLen
      RsaPad2[idx] = 0
      idx = idx + 1
    Wend
    zlen = sigLen - u - hashLen
    If zlen = padLen
      x2 = x3 + 2
    Else
      If zlen = (padLen + 2)
        x2 = x3 + 4
        padLen = zlen
        RsaPad2[padLen - 4] = $05
      Else
        ProcedureReturn 0
      EndIf
    EndIf
    RsaPad2[1] = $30
    RsaPad2[2] = x2 + hashLen + 4
    RsaPad2[3] = $30
    RsaPad2[4] = x2
    RsaPad2[5] = $06
    idx = 0
    While idx <= x3
      RsaPad2[6 + idx] = PeekA(hashOid + idx) & 255
      idx = idx + 1
    Wend
    RsaPad2[padLen - 2] = $04
    RsaPad2[padLen - 1] = hashLen
    If RsaMemEq(@RsaPad2, sig + u, padLen) = 0
      ProcedureReturn 0
    EndIf
  EndIf
  idx = 0
  While idx < hashLen
    PokeB(hashOut + idx, PeekA(sig + sigLen - hashLen + idx) & 255)
    idx = idx + 1
  Wend
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  RsaSetPubKey(nPtr, nLen, ePtr, eLen) - install the public key the next
;  verification will use. THE ONLY PROCEDURE THIS FILE ADDS, and it is
;  here because the AArch64 backend passes eight arguments and the three
;  entry points below need nine. See "THE NINTH ARGUMENT" in the header.
;
;  It COPIES NOTHING: both pointers must stay valid until the verify
;  returns. That is the same contract the 32-bit copies have for the same
;  two pointers - they were arguments there and they are stored here -
;  and it keeps a 512-byte modulus out of a second buffer.
;
;  CALL IT BEFORE EVERY VERIFY. Forgetting is safe rather than silent:
;  with nothing installed RsaKeyNLen is 0, RsaPublic refuses a
;  zero-length modulus, and the verify returns 0.
; ----------------------------------------------------------------------
Procedure RsaSetPubKey(nPtr.i, nLen.i, ePtr.i, eLen.i)
  RsaKeyN = nPtr
  RsaKeyNLen = nLen
  RsaKeyE = ePtr
  RsaKeyELen = eLen
EndProcedure

; ----------------------------------------------------------------------
;  RsaVrfy(sigAddr, sigLen, hashOidAddr, hashLen, outAddr) - the
;  CERTIFICATE SEAM entry point. PKCS#1 v1.5 signature RECOVERY: runs the
;  public operation ON THE KEY RsaSetPubKey INSTALLED, checks the
;  DigestInfo wrapper, and writes the recovered hash (hashLen bytes) to
;  outAddr. Returns 1 when the recovery succeeded, 0 when it did not. It
;  never returns -1; -1 is the chain engine's own "this seam is not
;  linked" answer, produced by the stub it compiles in when this module
;  is absent from the build.
;
;  > FOUR ARGUMENTS FEWER THAN THE 32-BIT COPIES. nAddr, nLen, eAddr and
;  > eLen moved into RsaSetPubKey because this backend passes eight
;  > arguments and this procedure declared nine. Everything else is
;  > unchanged, in the same order. See "THE NINTH ARGUMENT".
;
;  The caller compares outAddr against its own computed hash - it already
;  holds that hash, so handing it the recovered bytes saves a copy and keeps
;  the comparison at the layer that knows what was hashed. hashOidAddr is a
;  length-prefixed encoded OID ({len, oid...}), which is exactly how the
;  chain engine's bytecode data block stores them; pass 0 for the raw (no
;  DigestInfo) form.
; ----------------------------------------------------------------------
Procedure.i RsaVrfy(sigAddr.i, sigLen.i, hashOidAddr.i, hashLen.i, outAddr.i)
  Protected idx.i
  If sigLen > #RsaMaxBytes
    ProcedureReturn 0
  EndIf
  idx = 0
  While idx < sigLen
    RsaSig[idx] = PeekA(sigAddr + idx) & 255
    idx = idx + 1
  Wend
  If RsaPublic(@RsaSig, sigLen, RsaKeyN, RsaKeyNLen, RsaKeyE, RsaKeyELen) = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn RsaPkcs1SigUnpad(@RsaSig, sigLen, hashOidAddr, hashLen, outAddr)
EndProcedure

; ----------------------------------------------------------------------
;  RsaPkcs1Vrfy(sig, sigLen, hashOid, hashLen, expectedHash) - full PKCS#1
;  v1.5 verification for a caller that already knows the hash it expects:
;  recover through RsaVrfy, then compare the recovered digest to
;  expectedHash. Returns 1 only if every step holds. The key is the one
;  RsaSetPubKey installed - four arguments fewer than the 32-bit copies,
;  for the reason in "THE NINTH ARGUMENT".
; ----------------------------------------------------------------------
Procedure.i RsaPkcs1Vrfy(sig.i, sigLen.i, hashOid.i, hashLen.i, expectedHash.i)
  If hashLen > 64
    ProcedureReturn 0
  EndIf
  If RsaVrfy(sig, sigLen, hashOid, hashLen, @RsaHashOut) = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn RsaMemEq(@RsaHashOut, expectedHash, hashLen)
EndProcedure

; ----------------------------------------------------------------------
;  RsaPssVrfyUnpad(xPtr, msgHash, hashLen, saltLen, nPtr, nLen) - EMSA-PSS
;  verification (RFC 8017, SHA-256 for both the data hash and MGF1) on the
;  recovered EM at xPtr (nLen bytes). r accumulates every failure; the
;  result is 1 only if r stays zero. n is needed to find the encoded-
;  message bit length (emBits = modBits - 1).
; ----------------------------------------------------------------------
Procedure.i RsaPssVrfyUnpad(xPtr.i, msgHash.i, hashLen.i, saltLen.i, nPtr.i, nLen.i)
  Protected u.i
  Protected r.i
  Protected nBitlen.i
  Protected xlen.i
  Protected emBase.i
  Protected seed.i
  Protected salt.i
  Protected idx.i
  Protected shift.i
  r = 0
  u = 0
  While u < nLen And (PeekA(nPtr + u) & 255) = 0
    u = u + 1
  Wend
  If u = nLen
    ProcedureReturn 0
  EndIf
  nBitlen = BnBitLen32(PeekA(nPtr + u) & 255) + ((nLen - u - 1) << 3)
  nBitlen = nBitlen - 1
  emBase = 0
  If (nBitlen & 7) = 0
    r = r | (PeekA(xPtr) & 255)
    emBase = 1
  Else
    r = r | ((PeekA(xPtr) & 255) & ($FF << (nBitlen & 7)))
  EndIf
  xlen = (nBitlen + 7) >> 3
  If hashLen > xlen Or saltLen > xlen Or (hashLen + saltLen + 2) > xlen
    ProcedureReturn 0
  EndIf
  r = r | ((PeekA(xPtr + emBase + xlen - 1) & 255) ! $BC)
  seed = xPtr + emBase + xlen - hashLen - 1
  RsaMgf1Xor(xPtr + emBase, xlen - hashLen - 1, seed, hashLen)
  If (nBitlen & 7) <> 0
    shift = 8 - (nBitlen & 7)
    PokeB(xPtr + emBase, (PeekA(xPtr + emBase) & 255) & (($FF >> shift) & $FF))
  EndIf
  idx = 0
  While idx < (xlen - hashLen - saltLen - 2)
    r = r | (PeekA(xPtr + emBase + idx) & 255)
    idx = idx + 1
  Wend
  r = r | ((PeekA(xPtr + emBase + xlen - hashLen - saltLen - 2) & 255) ! $01)
  salt = xPtr + emBase + xlen - hashLen - saltLen - 1
  Sha256Begin()
  idx = 0
  While idx < 8
    RsaTmp[idx] = 0
    idx = idx + 1
  Wend
  Sha256Update(@RsaTmp, 8)
  Sha256Update(msgHash, hashLen)
  Sha256Update(salt, saltLen)
  Sha256End(@RsaTmp)
  idx = 0
  While idx < hashLen
    r = r | ((RsaTmp[idx] & 255) ! (PeekA(xPtr + emBase + xlen - hashLen - 1 + idx) & 255))
    idx = idx + 1
  Wend
  If r = 0
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

; ----------------------------------------------------------------------
;  RsaPssVrfy(sig, sigLen, msgHash, hashLen, saltLen) - full RSA-PSS
;  verification. Copies sig, runs the public operation on the key
;  RsaSetPubKey installed, then EMSA-PSS verification with SHA-256.
;  Returns 1 only if the signature is valid for msgHash at the given salt
;  length. Four arguments fewer than the 32-bit copies, for the reason in
;  "THE NINTH ARGUMENT".
; ----------------------------------------------------------------------
Procedure.i RsaPssVrfy(sig.i, sigLen.i, msgHash.i, hashLen.i, saltLen.i)
  Protected idx.i
  If sigLen > #RsaMaxBytes
    ProcedureReturn 0
  EndIf
  idx = 0
  While idx < sigLen
    RsaSig[idx] = PeekA(sig + idx) & 255
    idx = idx + 1
  Wend
  If RsaPublic(@RsaSig, sigLen, RsaKeyN, RsaKeyNLen, RsaKeyE, RsaKeyELen) = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn RsaPssVrfyUnpad(@RsaSig, msgHash, hashLen, saltLen, RsaKeyN, RsaKeyNLen)
EndProcedure
; ==== PORTABLE CORE A64 END ====

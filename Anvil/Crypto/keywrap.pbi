; ======================================================================
;  keywrap.pbi - AES KEY WRAP AND KEY UNWRAP (RFC 3394), RASPBERRY PI 4
; ======================================================================
;
;     XIncludeFile "Anvil/Crypto/keywrap.pbi"
;
;  RFC 3394, "Advanced Encryption Standard (AES) Key Wrap Algorithm",
;  Schaad and Housley, September 2002.  THE DOCUMENT IS ON THIS DISK at
;  RaspberryPi4/Reference/rfc3394.txt and every line number below is a
;  line of that file.  The index-based formulations are the ones
;  implemented, because they are the ones the RFC's own test vectors
;  were generated with (rfc3394.txt:416-419).
;
;  API:
;    KwWrap(kek, keklen, plain, plainlen, dst)
;        Wrap plainlen bytes at plain under the KEK.  Writes
;        plainlen + 8 bytes at dst and returns that count, or returns 0
;        and writes nothing.
;    KwUnwrap(kek, keklen, wrapped, wraplen, dst)
;        Unwrap wraplen bytes at wrapped.  On success writes
;        wraplen - 8 bytes at dst and returns that count.  ON ANY
;        FAILURE - a bad argument, or an integrity check that does not
;        hold - RETURNS 0 AND LEAVES NO KEY DATA AT dst.
;    KwWipe()
;        Zero this file's scratch.  Does NOT wipe aes.pi4's schedule;
;        call AesWipe() for that.
;
;  keklen is 16, 24 or 32.  plainlen and wraplen are byte counts.
;
;  DEPENDENCIES: aes.pi4, WHICH THIS FILE DOES NOT INCLUDE.  House rule
;  - a library never includes a library; the MAIN file lists what it
;  needs, in order:
;
;     XIncludeFile "RaspberryPi4/Lib/aes.pi4"
;     XIncludeFile "Anvil/Crypto/keywrap.pbi"
;
;  It calls AesSetKey, AesEncryptBlock and AesDecryptBlock and nothing
;  else.  Getting the order wrong is a compile error, not a runtime
;  surprise.
;
;  THIS FILE TURNS EnableExplicit ON FOR YOUR PROGRAM TOO (via aes.pi4,
;  which must precede it, and again here so that this file is honest on
;  its own).
;
;  ======================================================================
;   WHY THIS EXISTS: EAPOL MESSAGE 3
;  ======================================================================
;
;  This is the last primitive the WPA2 four-way handshake was missing.
;  Message 3 from the access point carries its Key Data field - the GTK
;  among other things - encrypted, and for the AES cipher suite the
;  encryption is exactly this: NIST AES Key Wrap with the default IV,
;  keyed with the KEK, which is the first 16 bytes of the PTK.  So the
;  UNWRAP is the operation that actually matters here; the wrap is
;  implemented too because RFC 3394's vectors state both directions and
;  because a wrap/unwrap round trip is a property the board can check
;  without a table.
;
;  ======================================================================
;   THE ALGORITHM, AND THE TWO THINGS IT IS EASY TO GET WRONG
;  ======================================================================
;
;  Wrap - rfc3394.txt:231-253:
;
;      A = IV
;      R[i] = P[i]                       for i = 1..n
;      for j = 0 to 5:
;          for i = 1 to n:
;              B = AES(K, A | R[i])
;              A = MSB(64, B) ^ t        where t = n*j + i
;              R[i] = LSB(64, B)
;      C[0] = A;  C[i] = R[i]
;
;  Unwrap - rfc3394.txt:302-327, the mirror image, run backwards:
;
;      A = C[0];  R[i] = C[i]
;      for j = 5 downto 0:
;          for i = n downto 1:
;              B = AES-1(K, (A ^ t) | R[i])   where t = n*j + i
;              A = MSB(64, B);  R[i] = LSB(64, B)
;      if A = IV then P[i] = R[i] else ERROR
;
;  ---- 1. t COUNTS THE STEPS, AND IT IS NOT THE LOOP INDEX. -----------
;
;  t = n*j + i, so it runs 1, 2, ... 6n across the whole double loop and
;  NOT 1..n six times.  On the unwrap side the loops run backwards and t
;  therefore counts DOWN from 6n to 1, but it is still n*j+i with the
;  same j and i - it is not "6n minus something".  A wrap that used i
;  alone, or an unwrap that recomputed t from a step counter that ran
;  the other way, would both still round-trip against themselves
;  perfectly and fail every published vector.  That is precisely why the
;  vectors are parsed from the RFC rather than generated here.
;
;  ---- 2. THE FAILURE PATH MUST PRODUCE NOTHING. ----------------------
;
;  rfc3394.txt:2164-2165, section 5: "If unwrapping produces an
;  unexpected value, then the algorithm implementation MUST return an
;  error, and it MUST NOT return any key data."  MUST NOT, in a
;  standards document, and it is not a formality: unwrap works in place
;  on the caller's buffer, so at the moment the check fails that buffer
;  is full of the attacker's chosen-ciphertext transformed under the
;  KEK.  Handing that back is a decryption oracle.  KwUnwrap zeroes the
;  whole output buffer before returning 0.
;
;  THE CHECK ITSELF IS CONSTANT TIME.  The eight bytes of A are compared
;  against the IV by accumulating differences and testing once, with no
;  early exit.  A byte-at-a-time compare that returned on the first
;  mismatch would tell a forger how many leading bytes of A were right,
;  and A is a function of the ciphertext they control - that is a
;  practical oracle, not a theoretical one, and it is the same shape of
;  mistake as a non-constant-time MAC compare.
;
;  ---- WHAT IS DELIBERATELY NOT HERE ----------------------------------
;
;  ALTERNATIVE INITIAL VALUES.  rfc3394.txt:370-381 allows for them and
;  RFC 5649's key wrap with padding uses one, together with a length
;  field, so that key data which is not a multiple of 64 bits can be
;  wrapped.  Neither is implemented.  IEEE 802.11 pads the EAPOL Key
;  Data to a multiple of 8 bytes itself and then uses the DEFAULT IV, so
;  the caller this file was written for does not need either, and an
;  untested second IV path is worse than no second IV path.  If RFC 5649
;  is ever wanted, it is a new entry point in this file with its own
;  vectors - not a flag on these two.
;
;  n = 1 IS REFUSED.  rfc3394.txt:119-121: "The only restriction the key
;  wrap algorithm places on n is that n be at least two.  (For key data
;  with length less than or equal to 64 bits, the constant field used in
;  this specification and the key data form a single 128-bit codebook
;  input making this key wrap unnecessary.)"  So an 8-byte plaintext is
;  outside the specification and is rejected rather than quietly
;  producing something no other implementation will agree with.
;
;  NO UPPER BOUND ON n IS IMPOSED HERE EITHER (rfc3394.txt:127-128 says
;  none should be).  This file allocates nothing that scales with n - it
;  works in the caller's own dst buffer - so the only limit is the
;  buffer the caller passes.  See the aliasing note on each procedure.
;
;  ======================================================================
;   WHAT HAS BEEN PROVEN, AND WHAT HAS NOT - 2026-08-28
;  ======================================================================
;
;  PROVEN under the project's A64 oracle tools/a64/a64_interp.py, on a
;  real image built by pmfc.exe for -t pi4.  The gate is
;  tools/a64/a64_keywrap_check.py:
;
;    * ALL SIX RFC 3394 section 4 vectors, wrap AND unwrap, PARSED OUT
;      OF rfc3394.txt at run time - KEK, key data and ciphertext.
;      Nothing is transcribed.  They cover 128-, 192- and 256-bit KEKs
;      against 128-, 192- and 256-bit key data, so every combination the
;      document states.
;    * The per-step intermediate values the RFC prints for each of those
;      six, also parsed: the harness reports A and every R[i] after each
;      of the 6n steps, so a wrap that is wrong at step 5 is caught at
;      step 5.
;    * Integrity: a corrupted wrapped blob must be refused AND must
;      leave the output buffer zero. The bits flipped are chosen rather
;      than swept - three in the integrity register A, one in EVERY R
;      register (so a register the loop never visited would show), the
;      last bit of the blob, and a truncation by one register.
;    * Round trips at lengths the RFC does not publish, against the
;      OpenSSL implementation in Python's `cryptography`, which is
;      validated against all six RFC vectors before it is used for
;      anything.
;
;  MUTATION-TESTED.  --mutate rebuilds a COPY of this file in
;  _work/keywrap/<n>/ with one deliberate defect at a time and requires
;  the gate to go red for each.  FIFTEEN mutations on 2026-08-28 and
;  ALL FIFTEEN WENT RED.  The sweep fans out across os.cpu_count() - 2
;  workers, one per mutation - 402 s rather than the 2,366 s it was on
;  one core; the wall clock is set by the two mutants that do not
;  terminate and burn the whole step budget.
;
;  It never opens this file for writing, and _work/ is in .gitignore,
;  so a mutant cannot reach a commit even if the sweep is killed
;  mid-run.
;
;  ONE OF THOSE MUTATIONS IS WORTH KNOWING ABOUT BY NAME.  "only the low
;  byte of t is XORed into A" went RED with exactly ONE failing vector
;  out of fifty-three, and that one is the 344-byte case.  All six
;  published RFC 3394 vectors, both in-place variants and every
;  corruption test passed the defective build - because every published
;  vector has n <= 4, so t never exceeds 24 and the other seven bytes of
;  A are never touched.  That is the whole argument for carrying a
;  vector the document does not publish.
;
;  NOT PROVEN: nothing here has run on silicon.
;  RaspberryPi4/Examples/Diagnostics/pi4AesSelfTest.pi4 is where that
;  will come from.
; ======================================================================
EnableExplicit

; ----------------------------------------------------------------------
;  #KW_IV_BYTE is $A6 because the default initial value is the
;  hexadecimal constant A6A6A6A6A6A6A6A6 - rfc3394.txt:362.  It is
;  held as ONE repeated byte rather than as a 64-bit literal because
;  everything here is byte-addressed: the buffers arrive at whatever
;  alignment the caller has, and with the MMU off an unaligned 64-bit
;  access on this part is a silent runaway (see the vault's "Unaligned
;  access with the MMU off 2026-08-27").
;
;  #KW_SEMI is 8: the key wrap operates on blocks of 64 bits
;  (rfc3394.txt:108-109) and pairs them into the 128-bit codebook input
;  (rfc3394.txt:161-162).  #KW_BLOCK is the codebook input, two of them.
;
;  #KW_PASSES is 6 because s = 6n (rfc3394.txt:150, and :201 in the algorithm) - six passes over
;  the n registers.
; ----------------------------------------------------------------------
#KW_IV_BYTE = $A6
#KW_SEMI    = 8
#KW_BLOCK   = 16
#KW_PASSES  = 6
#KW_MIN_N   = 2

; ----------------------------------------------------------------------
;  STATE - two small buffers, both key material.
;
;  secKwA is the 64-bit integrity check register A.  secKwB is the
;  128-bit codebook input and output, A | R[i] on the way in and
;  MSB|LSB on the way out.  NEITHER SCALES WITH n: the R registers live
;  in the caller's dst buffer and are updated in place, which is what
;  the RFC's index-based formulation is for (rfc3394.txt:212-217).
; ----------------------------------------------------------------------
Global Dim secKwA.a[8]              ; the integrity register A
Global Dim secKwB.a[16]             ; the AES codebook block

; ----------------------------------------------------------------------
;  KwWipe() - zero this file's scratch.
;
;  It does NOT touch aes.pi4's key schedule, and saying so here is the
;  honest thing rather than implying a clean-up this cannot deliver.
;  Call AesWipe() as well when the KEK is finished with.
; ----------------------------------------------------------------------
Procedure KwWipe()
  Protected i.i
  i = 0
  While i < #KW_BLOCK
    secKwB[i] = 0
    i = i + 1
  Wend
  i = 0
  While i < #KW_SEMI
    secKwA[i] = 0
    i = i + 1
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  kw_XorT(t) - A = A ^ t, with t as a 64-bit big-endian integer.
;
;  ALL EIGHT BYTES ARE WRITTEN even though t never exceeds 6n and the
;  top six are therefore always zero for any n a caller will ever pass.
;  The XOR is defined over the whole 64-bit register (rfc3394.txt:246),
;  and a two-byte version would be a different function that happens to
;  agree for small n - the same argument pbkdf2.pi4 makes for writing
;  out all four octets of INT(i).
;
;  t is a STEP NUMBER and is public: it depends on n and on how far
;  through the loops we are, never on a key or data byte.
; ----------------------------------------------------------------------
Procedure kw_XorT(t.i)
  Protected k.i
  k = 0
  While k < #KW_SEMI
    secKwA[7 - k] = (secKwA[7 - k] & 255) ! ((t >> (k * 8)) & 255)
    k = k + 1
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  kw_CopyIn(r) - build the codebook input A | R[i] at secKwB.
;  kw_CopyOut(r) - split the codebook output: A = MSB(64, B),
;                  R[i] = LSB(64, B).
;
;  r is the ADDRESS of the R register in the caller's buffer.  Two
;  eight-byte loops rather than one sixteen-byte memcpy, because the two
;  halves come from and go to different places and writing that out is
;  what makes the MSB/LSB split checkable against rfc3394.txt:144-145.
; ----------------------------------------------------------------------
Procedure kw_CopyIn(r.i)
  Protected k.i
  k = 0
  While k < #KW_SEMI
    secKwB[k] = secKwA[k] & 255
    secKwB[#KW_SEMI + k] = PeekA(r + k) & 255
    k = k + 1
  Wend
EndProcedure

Procedure kw_CopyOut(r.i)
  Protected k.i
  k = 0
  While k < #KW_SEMI
    secKwA[k] = secKwB[k] & 255
    PokeB(r + k, secKwB[#KW_SEMI + k] & 255)
    k = k + 1
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  kw_Blocks(len) - the shared argument check.  Returns n, the number of
;  64-bit registers, or 0 if the length is not a legal key data size.
;
;  len must be a positive multiple of 8 and at least 16 - see the n = 1
;  paragraph in the header.
; ----------------------------------------------------------------------
Procedure.i kw_Blocks(len.i)
  If len < #KW_MIN_N * #KW_SEMI
    ProcedureReturn 0
  EndIf
  If (len % #KW_SEMI) <> 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn len / #KW_SEMI
EndProcedure

; ----------------------------------------------------------------------
;  KwWrap(kek, keklen, plain, plainlen, dst)
;
;  Returns plainlen + 8, or 0.  dst must have room for plainlen + 8
;  bytes.
;
;  ALIASING: dst MAY BE THE SAME ADDRESS AS plain, in which case the
;  buffer must still be plainlen + 8 bytes long and the plaintext is
;  shifted up by eight.  THE COPY BELOW RUNS BACKWARD FOR EXACTLY THAT
;  REASON - a forward copy would overwrite bytes it had not read yet.
;  Any other partial overlap is not supported and cannot be detected
;  from here.
;
;  THE KEK IS LEFT INSTALLED IN aes.pi4 when this returns, the same way
;  pbkdf2.pi4 leaves hmacsha1.pi4 keyed.  Call AesWipe() when done.
; ----------------------------------------------------------------------
Procedure.i KwWrap(kek.i, keklen.i, plain.i, plainlen.i, dst.i)
  Protected n.i
  Protected i.i
  Protected j.i
  Protected t.i
  Protected k.i

  n = kw_Blocks(plainlen)
  If n = 0
    ProcedureReturn 0
  EndIf
  If AesSetKey(kek, keklen) = 0
    ProcedureReturn 0
  EndIf

  ; ---- 1) Initialize variables - rfc3394.txt:235-239 -----------------
  ; R[i] = P[i].  BACKWARD, see the aliasing note above.
  k = plainlen - 1
  While k >= 0
    PokeB(dst + #KW_SEMI + k, PeekA(plain + k) & 255)
    k = k - 1
  Wend
  ; A = IV
  k = 0
  While k < #KW_SEMI
    secKwA[k] = #KW_IV_BYTE
    k = k + 1
  Wend

  ; ---- 2) Calculate intermediate values - rfc3394.txt:241-247 --------
  j = 0
  While j < #KW_PASSES
    i = 1
    While i <= n
      kw_CopyIn(dst + i * #KW_SEMI)
      AesEncryptBlock(@secKwB[0], @secKwB[0])
      kw_CopyOut(dst + i * #KW_SEMI)
      t = n * j + i
      kw_XorT(t)
      i = i + 1
    Wend
    j = j + 1
  Wend

  ; ---- 3) Output the results - rfc3394.txt:249-253 -------------------
  ; C[0] = A.  C[1..n] are already in place.
  k = 0
  While k < #KW_SEMI
    PokeB(dst + k, secKwA[k] & 255)
    k = k + 1
  Wend

  ProcedureReturn plainlen + #KW_SEMI
EndProcedure

; ----------------------------------------------------------------------
;  KwUnwrap(kek, keklen, wrapped, wraplen, dst)
;
;  Returns wraplen - 8 on success, or 0.  dst must have room for
;  wraplen - 8 bytes.
;
;  ALIASING: dst MAY BE THE SAME ADDRESS AS wrapped.  The ciphertext
;  shifts DOWN by eight, so the copy below runs FORWARD.  Any other
;  partial overlap is not supported.
;
;  ON FAILURE dst IS ZEROED, ALL wraplen - 8 BYTES OF IT.  See point 2
;  of the header - this is a MUST in RFC 3394 section 5 and it is the
;  difference between a key wrap and a decryption oracle.
; ----------------------------------------------------------------------
Procedure.i KwUnwrap(kek.i, keklen.i, wrapped.i, wraplen.i, dst.i)
  Protected n.i
  Protected i.i
  Protected j.i
  Protected t.i
  Protected k.i
  Protected diff.i

  ; wraplen carries n+1 registers, so the plaintext is 8 shorter.
  n = kw_Blocks(wraplen - #KW_SEMI)
  If n = 0
    ProcedureReturn 0
  EndIf
  If AesSetKey(kek, keklen) = 0
    ProcedureReturn 0
  EndIf

  ; ---- 1) Initialize variables - rfc3394.txt:306-310 -----------------
  ; A = C[0]
  k = 0
  While k < #KW_SEMI
    secKwA[k] = PeekA(wrapped + k) & 255
    k = k + 1
  Wend
  ; R[i] = C[i].  FORWARD, see the aliasing note above.
  k = 0
  While k < n * #KW_SEMI
    PokeB(dst + k, PeekA(wrapped + #KW_SEMI + k) & 255)
    k = k + 1
  Wend

  ; ---- 2) Compute intermediate values - rfc3394.txt:312-318 ----------
  ; Both loops run backwards; t is still n*j+i.
  j = #KW_PASSES - 1
  While j >= 0
    i = n
    While i >= 1
      t = n * j + i
      kw_XorT(t)
      kw_CopyIn(dst + (i - 1) * #KW_SEMI)
      AesDecryptBlock(@secKwB[0], @secKwB[0])
      kw_CopyOut(dst + (i - 1) * #KW_SEMI)
      i = i - 1
    Wend
    j = j - 1
  Wend

  ; ---- 3) Output results - rfc3394.txt:320-327 -----------------------
  ; The integrity check, accumulated and tested once.  No early exit:
  ; see point 2 of the header.
  diff = 0
  k = 0
  While k < #KW_SEMI
    diff = diff | ((secKwA[k] & 255) ! #KW_IV_BYTE)
    k = k + 1
  Wend

  If diff <> 0
    k = 0
    While k < n * #KW_SEMI
      PokeB(dst + k, 0)
      k = k + 1
    Wend
    KwWipe()
    ProcedureReturn 0
  EndIf

  ProcedureReturn n * #KW_SEMI
EndProcedure

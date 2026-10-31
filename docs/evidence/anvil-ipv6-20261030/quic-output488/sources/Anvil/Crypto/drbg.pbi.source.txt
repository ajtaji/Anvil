; Shared HMAC-SHA256 DRBG algorithm.
; Original provenance and security discussion retained in RaspberryPi4/Lib/drbg.pi4.
; Caller supplies entropy through DrbgInit/DrbgReseed; this file has no hardware access.
; ==== PORTABLE CORE A64 BEGIN ====
#DRBG_SEED_STRENGTH = 32

#DRBG_OK               =  1
#DRBG_WARN_SHORT_SEED  = -1
#DRBG_ERR_NOSEED       = -2
#DRBG_ERR_CONSTSEED    = -3
#DRBG_ERR_UNSEEDED     = -4
#DRBG_ERR_NOSOURCE     = -5
#DRBG_ERR_ENTROPY      = -6   ; the hardware source refused - ask
                              ; DrbgEntropyStatus() which way

; ----------------------------------------------------------------------
;  THE AUTO-SEED SIZES. See WHAT THE SEEDING CONTRACT IS in the header
;  for the citation behind each one; they are spelled as literals
;  because a constant declaration in this language may not contain
;  arithmetic, so #DRBG_AUTOSEED_BYTES cannot be written as the sum.
; ----------------------------------------------------------------------
#DRBG_NONCE_BYTES    = 16     ; SP 800-90A 8.6.7, strength/2 bits
#DRBG_AUTOSEED_BYTES = 48     ; = #DRBG_SEED_STRENGTH + #DRBG_NONCE_BYTES
#DRBG_RESEED_BYTES   = 32     ; a reseed needs strength bits, no nonce

; ----------------------------------------------------------------------
;  STATE - the two 32-byte HMAC-DRBG working registers, plus a one-byte
;  buffer for the $00 / $01 domain separators the update mixes in. K and
;  V are secret; DrbgOne carries only a public constant.
;
;  gDrbgSeeded and drbgSeedLen are the instantiate gate. They are
;  ordinary Globals and therefore zero at reset (the __a64_bss_zero loop
;  in the standard prologue), which is the safe state: not seeded.
; ----------------------------------------------------------------------
Global Dim secDrbgK.a[32]            ; the DRBG Key register
Global Dim secDrbgV.a[32]            ; the DRBG Value register
Global Dim DrbgOne.a[1]              ; single-byte separator ($00 or $01)
Global gDrbgSeeded.i                  ; 0 until a seed was accepted
Global drbgSeedLen.i                 ; how many seed bytes were accepted

; ----------------------------------------------------------------------
;  DrbgSeedUsable(seed, slen) - the gate, in one place.
;
;  Returns #DRBG_OK, #DRBG_WARN_SHORT_SEED, or a negative refusal.
;  Instantiation is allowed for the first two.
;
;  THE DEGENERATE TEST IS CONSTANT TIME. It ORs every byte's difference
;  from the first byte into one accumulator and tests that accumulator
;  once, so it never returns early and never reveals WHERE the seed
;  stopped being constant. Same shape as CtEqual in hmac.pi4, and for
;  the same reason.
; ----------------------------------------------------------------------
Procedure.i DrbgSeedUsable(seed.i, slen.i)
  Protected i.i
  Protected first.i
  Protected diff.i

  If seed = 0
    ProcedureReturn #DRBG_ERR_NOSEED
  EndIf
  If slen <= 0
    ProcedureReturn #DRBG_ERR_NOSEED
  EndIf

  first = PeekA(seed) & 255
  diff = 0
  i = 1
  While i < slen
    diff = diff | ((PeekA(seed + i) & 255) ! first)
    i = i + 1
  Wend
  If diff = 0
    ; every byte the same - all zeros, all $FF, or a buffer somebody
    ; memset and never filled. Not entropy under any reading.
    ProcedureReturn #DRBG_ERR_CONSTSEED
  EndIf

  If slen < #DRBG_SEED_STRENGTH
    ProcedureReturn #DRBG_WARN_SHORT_SEED
  EndIf
  ProcedureReturn #DRBG_OK
EndProcedure

; ----------------------------------------------------------------------
;  DrbgUpdate(seed, slen) - the SP 800-90A HMAC_DRBG_Update
;  (section 10.1.2.2).
;
;    K = HMAC(K, V || $00 || seed) ; V = HMAC(K, V)
;    if seed non-empty:
;    K = HMAC(K, V || $01 || seed) ; V = HMAC(K, V)
;
;  Each HMAC completes before the next begins; the key is re-derived from
;  the new K after each K assignment (HmacKey caches the ipad/opad states,
;  and the running HMAC uses those cached states, so writing the new K into
;  secDrbgK after HmacEnd never disturbs the MAC that just produced it).
;
;  INTERNAL. It does no gating - the callers do that. It is not part of
;  the API and a caller reaching past DrbgInit/DrbgReseed to it is
;  bypassing the seed checks.
; ----------------------------------------------------------------------
Procedure.i DrbgUpdate(seed.i, slen.i)
  ; 1. K = HMAC(K, V || $00 || seed)
  HmacKey(@secDrbgK[0], 32)
  HmacBegin()
  HmacUpdate(@secDrbgV[0], 32)
  DrbgOne[0] = $00
  HmacUpdate(@DrbgOne[0], 1)
  HmacUpdate(seed, slen)
  HmacEnd(@secDrbgK[0], 32)
  HmacKey(@secDrbgK[0], 32)

  ; 2. V = HMAC(K, V)
  HmacBegin()
  HmacUpdate(@secDrbgV[0], 32)
  HmacEnd(@secDrbgV[0], 32)

  ; 3. an empty seed stops here
  If slen = 0
    ProcedureReturn 0
  EndIf

  ; 4. K = HMAC(K, V || $01 || seed)
  HmacBegin()
  HmacUpdate(@secDrbgV[0], 32)
  DrbgOne[0] = $01
  HmacUpdate(@DrbgOne[0], 1)
  HmacUpdate(seed, slen)
  HmacEnd(@secDrbgK[0], 32)
  HmacKey(@secDrbgK[0], 32)

  ; 5. V = HMAC(K, V)
  HmacBegin()
  HmacUpdate(@secDrbgV[0], 32)
  HmacEnd(@secDrbgV[0], 32)
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  DrbgInit(seed, slen) - instantiate (SP 800-90A section 10.1.2.3).
;  K = $00*32, V = $01*32, then the first Update mixes the seed material
;  in.
;
;  The seed is entropy_input || nonce || personalization_string, already
;  concatenated by the caller - this file does not gather any of the
;  three and cannot.
;
;  A REFUSAL LEAVES THE STATE UNTOUCHED AND UNSEEDED. It does not zero
;  K and V and then fail, because a half-instantiated DRBG whose
;  DrbgSeeded() says 0 but whose registers look plausible is a trap for
;  the next reader.
; ----------------------------------------------------------------------
Procedure.i DrbgInit(seed.i, slen.i)
  Protected i.i
  Protected verdict.i

  verdict = DrbgSeedUsable(seed, slen)
  If verdict < 0 And verdict <> #DRBG_WARN_SHORT_SEED
    ProcedureReturn verdict
  EndIf

  i = 0
  While i < 32
    secDrbgK[i] = $00
    secDrbgV[i] = $01
    i = i + 1
  Wend
  DrbgUpdate(seed, slen)
  gDrbgSeeded = 1
  drbgSeedLen = slen
  ProcedureReturn verdict
EndProcedure

; ----------------------------------------------------------------------
;  DrbgReseed(seed, slen) - reseed (SP 800-90A section 10.1.2.4). A
;  reseed is exactly an Update with the new entropy (+ any additional
;  input) as its seed material.
;
;  RESEEDING AN UNSEEDED DRBG IS REFUSED rather than treated as an
;  instantiate. The two are different operations with different
;  starting states, and quietly promoting one to the other would let a
;  program that never called DrbgInit look like it had.
;
;  A REFUSED RESEED LEAVES A WORKING DRBG WORKING. It is a failure to
;  add entropy, not a reason to stop generating; the caller is told and
;  decides.
; ----------------------------------------------------------------------
Procedure.i DrbgReseed(seed.i, slen.i)
  Protected verdict.i

  If gDrbgSeeded = 0
    ProcedureReturn #DRBG_ERR_UNSEEDED
  EndIf

  verdict = DrbgSeedUsable(seed, slen)
  If verdict < 0 And verdict <> #DRBG_WARN_SHORT_SEED
    ProcedureReturn verdict
  EndIf

  DrbgUpdate(seed, slen)
  If slen > drbgSeedLen
    drbgSeedLen = slen
  EndIf
  ProcedureReturn verdict
EndProcedure

; ----------------------------------------------------------------------
;  DrbgGenerate(dst, len) - produce len pseudorandom bytes
;  (SP 800-90A section 10.1.2.5), then roll the state forward with an
;  empty-additional Update (inlined here, exactly as BearSSL does, to
;  avoid re-deriving the key context an extra time).
;
;    while len: V = HMAC(K, V); emit V (or its head on the last block)
;    K = HMAC(K, V || $00) ; V = HMAC(K, V)
;
;  Control is length-driven only; the state bytes are never branched on.
;  Returns len, or #DRBG_ERR_UNSEEDED having written nothing at all.
;
;  THERE IS NO reseed_interval CHECK. See the header - this
;  implementation, like all three of its siblings, keeps no
;  reseed_counter and will generate forever from one seed.
; ----------------------------------------------------------------------
Procedure.i DrbgGenerate(dst.i, len.i)
  Protected off.i
  Protected rem.i
  Protected clen.i
  Protected i.i

  If gDrbgSeeded = 0
    ProcedureReturn #DRBG_ERR_UNSEEDED
  EndIf
  If len <= 0
    ProcedureReturn 0
  EndIf

  HmacKey(@secDrbgK[0], 32)

  off = 0
  rem = len
  While rem > 0
    ; V = HMAC(K, V)
    HmacBegin()
    HmacUpdate(@secDrbgV[0], 32)
    HmacEnd(@secDrbgV[0], 32)

    clen = 32
    If clen > rem
      clen = rem
    EndIf
    i = 0
    While i < clen
      PokeB(dst + off + i, secDrbgV[i] & 255)
      i = i + 1
    Wend
    off = off + clen
    rem = rem - clen
  Wend

  ; roll forward: K = HMAC(K, V || $00) ; V = HMAC(K, V)
  HmacBegin()
  HmacUpdate(@secDrbgV[0], 32)
  DrbgOne[0] = $00
  HmacUpdate(@DrbgOne[0], 1)
  HmacEnd(@secDrbgK[0], 32)
  HmacKey(@secDrbgK[0], 32)
  HmacBegin()
  HmacUpdate(@secDrbgV[0], 32)
  HmacEnd(@secDrbgV[0], 32)
  ProcedureReturn len
EndProcedure

; ----------------------------------------------------------------------
;  DrbgSeeded() / DrbgSeedBytes() - the instantiate state, readable.
;
;  Print DrbgSeedBytes() at bring-up. A program that thinks it seeded a
;  DRBG and reports 0 has found a real bug in one line, which is the
;  same argument SafetyBoot() makes for returning its boot number.
; ----------------------------------------------------------------------
Procedure.i DrbgSeeded()
  ProcedureReturn gDrbgSeeded
EndProcedure

Procedure.i DrbgSeedBytes()
  ProcedureReturn drbgSeedLen
EndProcedure

; ==== PORTABLE CORE A64 END ====

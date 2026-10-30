; ======================================================================
;  tls13_record.pbi - the TLS 1.3 RECORD LAYER (RFC 8446 section 5),
;                     ON 64-BIT ANVIL TARGETS
; ======================================================================
;
;  Ported from RP2350/Lib/tls13_record.pico2 (own-written against RFC
;  8446 section 5; there is no BearSSL TLS 1.3 to translate). The design,
;  the names and the refusal table are the Pico core's; what changed for
;  this part is listed under "WHAT THE PORT CHANGED" below, each with its
;  reason.
;
;     XIncludeFile "Anvil/Crypto/aes.pbi"            ; REQUIRED, in order
;     XIncludeFile "Anvil/Crypto/gcm.pbi"        ; REQUIRED
;     XIncludeFile "Anvil/Crypto/tls13_record.pbi"
;
;  (Anvil/Crypto/aes.pbi is the AES the Pi 4 board links; gcm.pi4 is
;  built on its AesCtrCore. A library never includes a library - the MAIN
;  file lists them, one per line. Either missing is a loud compile-time
;  undefined-procedure error naming the gap.)
;
;  SECURITY POSTURE. A VERIFY THAT CAN BE SKIPPED IS WORSE THAN NO TLS AT
;  ALL, BECAUSE IT LIES. There is NO path in Tls13RecUnprotect that
;  returns a length when the GCM tag did not verify, and no path that
;  returns a length when no key is installed. Every failure sets
;  Tls13RecErr to a NAMED code and returns -1 (or 0 from the protect
;  side); nothing here fails open.
;
;  API (module-global state - ONE connection at a time):
;    Tls13RecReset()                    forget both keys, zero both
;                                       sequence numbers, clear the error
;    Tls13RecSetWriteKey(key.i, iv.i)   16-byte key, 12-byte iv; seq := 0
;    Tls13RecSetReadKey(key.i, iv.i)    16-byte key, 12-byte iv; seq := 0
;    Tls13RecInvalidateCipher()         something else called GcmInit;
;                                       re-install on the next record
;    Tls13RecProtect(ctype, plain, plen, padlen, dst, dstmax)
;        -> total record length written at dst, or 0 on refusal. The
;        OUTER type is always application_data (23) and the outer version
;        0x0303 - the content-type hiding of RFC 8446 5.2.
;    Tls13RecUnprotect(rec, reclen)
;        -> plaintext length, or -1 on refusal. Decrypts IN PLACE: on
;        success the plaintext is at rec + 5 and TlsRecInnerType holds the
;        real content type. On -1 the buffer holds unauthenticated bytes
;        that MUST NOT be read.
;    Tls13RecPlainAddr(rec)             rec + 5
;    Tls13RecBuildPlainHeader(dst, ctype, len, minorver)
;    TlsRecInnerType / Tls13RecErr
;
;  THE AEAD NONCE (RFC 8446 5.3): the 64-bit sequence number, LEFT-padded
;  to 12 bytes and XORed with the iv - the eight sequence bytes land in
;  nonce[4..11]. Gated against the RFC 8448 published records, because a
;  wrong-way nonce round-trips against itself and fails against everyone
;  else.
;
;  SEQUENCE-NUMBER OVERFLOW is a refusal, not a wrap (RFC 8446 5.3).
;  RECORD SIZE LIMITS (RFC 8446 5.1/5.2) are enforced both ways, BEFORE
;  any crypto runs.
;
;  CONSTANT TIME. Nothing here branches on key, plaintext or tag bytes.
;  The tag comparison is gcm.pi4's own OR-accumulated single test. The
;  scan back over the padding is bounded by the PADDING LENGTH, which the
;  sender chose and which is not a secret of ours.
;
; ======================================================================
;  WHAT THE PORT CHANGED, AND WHY - the four places this file differs
;  from the Pico core
; ======================================================================
;
;  1. THE GCM VERDICT IS A MASK HERE, AND IT IS TESTED AT FULL WIDTH.
;     gcm.pi4's GcmDecrypt returns $FFFFFFFF for an authentic tag and 0
;     for a forged one. The Pico core tests `ok = 0` and refuses; that
;     spelling would still refuse a forgery against this gcm.pi4, but it
;     ACCEPTS anything non-zero - and the 32-bit families' `>> 31` mask
;     spelling returns $FFFFFFFF00000000 for a BAD tag on this target
;     (see gcm.pi4's header and Anvil/Core/crypto_cmd.pbi). So the test
;     here is `ok <> #TLSREC_W32` -> refuse: only the exact authentic mask
;     is accepted, and any other value, including a verdict from a gcm
;     that regressed to the 32-bit spelling, refuses.
;
;  2. THE SEQUENCE NUMBER CARRY IS MASKED. The Pico core keeps the 64-bit
;     sequence number as two 32-bit .i words and relies on the low word
;     wrapping from $FFFFFFFF to 0 to carry into the high word, and on
;     "-1" meaning "all ones". .i IS 64 BITS HERE: the low word would
;     count on to $100000000, never carry, and never equal -1, so the
;     nonce would repeat after 2^32 records and the overflow refusal
;     could never fire. Each half is therefore kept in 0..$FFFFFFFF with
;     an explicit `& #TLSREC_W32`, and the all-ones test compares against
;     #TLSREC_W32. The nonce bytes are taken from each half exactly as
;     before.
;
;  3. THE AES INCLUDE IS Anvil/Crypto/aes.pbi, the copy the Pi 4 board
;     links (see RaspberryPi4/Board/board.pi4), not an RP2350 file.
;
;  4. TlsRecNonce and the sequence-number helpers keep their names so the
;     gate and the handshake read the same on both families.
;
;  Everything else - the refusal codes, their numbers, the order of the
;  checks (size limits, then the tag, then the padding scan) - is the
;  Pico core unchanged.
;
;  PROOF STATUS - STATED PLAINLY. DESK-PROVEN ONLY. NOTHING IN THIS FILE
;  HAS RUN ON SILICON. It builds for -t pi4 and passes
;  tools/tls13_rfc8448_check.py under the AArch64 model
;  (tools/a64/a64_interp.py): the RFC 8448 section 3 records reproduced
;  byte for byte in both directions, the right-aligned nonce, sequence
;  stepping, the size limits, padding, the all-zero inner plaintext and
;  a tampered tag as negatives, plus the sequence-number carry at 2^32
;  and the overflow refusal at 2^64 - 1 in both directions (66 checks in
;  the gate's record job, all green on 2026-10-14). The model and the code generator can
;  share a bug that only the part exposes; until a Pi 4 has run the same
;  checks, this is a desk result.
; ======================================================================
; ==== PORTABLE CORE A64 BEGIN ====

; ----------------------------------------------------------------------
;  Content types (RFC 8446 appendix B.1) and record geometry (5.1/5.2).
; ----------------------------------------------------------------------
#TLS_CT_CHANGE_CIPHER_SPEC = 20
#TLS_CT_ALERT              = 21
#TLS_CT_HANDSHAKE          = 22
#TLS_CT_APPDATA            = 23

#TLS_REC_HDR        = 5          ; type(1) version(2) length(2)
#TLS_TAG_LEN        = 16         ; AES-128-GCM tag
#TLS_MAX_PLAINTEXT  = 16384      ; 2^14, RFC 8446 5.1
#TLS_MAX_CIPHERTEXT = 16640      ; 2^14 + 256, RFC 8446 5.2

; One 32-bit half of the sequence number, and gcm.pi4's "authentic" mask.
#TLSREC_W32 = $FFFFFFFF

; ----------------------------------------------------------------------
;  Named refusals. Every one is a REASON; the caller drops the connection.
; ----------------------------------------------------------------------
#TLSREC_OK                 = 0
#TLSREC_ERR_CRYPTO         = 10  ; cooperative protection job refused
#TLSREC_ERR_NO_KEY         = 1   ; asked to protect/unprotect unkeyed
#TLSREC_ERR_TOO_LONG       = 2   ; over an RFC 8446 5.1/5.2 size limit
#TLSREC_ERR_SEQ_OVERFLOW   = 3   ; 64-bit sequence number would wrap
#TLSREC_ERR_BAD_TAG        = 4   ; AEAD authentication FAILED
#TLSREC_ERR_SHORT_RECORD   = 5   ; record cannot even hold a tag
#TLSREC_ERR_ALL_ZERO_INNER = 6   ; no non-zero octet in the inner plaintext
#TLSREC_ERR_BAD_OUTER_TYPE = 7   ; protected record not application_data
#TLSREC_ERR_BUF_TOO_SMALL  = 8   ; caller's output buffer will not hold it
#TLSREC_ERR_LEN_MISMATCH   = 9   ; header length disagrees with the bytes

; ----------------------------------------------------------------------
;  STATE. Traffic keys and ivs carry the sec prefix. The sequence-number
;  halves are each kept in 0..$FFFFFFFF (see change 2 in the header).
; ----------------------------------------------------------------------
Global Dim secTlsWKey.a[16]          ; write traffic key            (secret)
Global Dim secTlsWIv.a[12]           ; write traffic iv             (secret)
Global TlsWSeqLo.i                   ; write sequence number, low 32
Global TlsWSeqHi.i                   ; write sequence number, high 32
Global TlsWKeyed.i                   ; 0 until a write key is installed

Global Dim secTlsRKey.a[16]          ; read traffic key             (secret)
Global Dim secTlsRIv.a[12]           ; read traffic iv              (secret)
Global TlsRSeqLo.i                   ; read sequence number, low 32
Global TlsRSeqHi.i                   ; read sequence number, high 32
Global TlsRKeyed.i                   ; 0 until a read key is installed

Global Dim TlsNonce.a[12]            ; the per-record AEAD nonce   (public)
Global Dim TlsAad.a[5]               ; the 5-byte additional data  (public)
Global Dim TlsTag.a[16]              ; tag scratch                 (public)

Global TlsRecInnerType.i             ; recovered content type of the last record
Global Tls13RecErr.i                 ; named reason for the last refusal
; Optional serialized decrypt driver; key/nonce spans are borrowed for the call.
Global *TlsRecDecryptHook,*TlsRecEncryptHook
Global TlsCipherInstalled.i          ; 0 none, 1 write key loaded, 2 read key

; ----------------------------------------------------------------------
;  Tls13RecReset() - forget everything. Both directions unkeyed, both
;  sequence numbers zero, no error, and the GCM key cache marked stale.
; ----------------------------------------------------------------------
Procedure Tls13RecReset()
  Protected i.i
  i = 0
  While i < 16
    secTlsWKey[i] = 0
    secTlsRKey[i] = 0
    i = i + 1
  Wend
  i = 0
  While i < 12
    secTlsWIv[i] = 0
    secTlsRIv[i] = 0
    i = i + 1
  Wend
  TlsWSeqLo = 0
  TlsWSeqHi = 0
  TlsRSeqLo = 0
  TlsRSeqHi = 0
  TlsWKeyed = 0
  TlsRKeyed = 0
  TlsRecInnerType = 0
  Tls13RecErr = #TLSREC_OK
  TlsCipherInstalled = 0
EndProcedure

; ----------------------------------------------------------------------
;  Tls13RecInvalidateCipher() - the cached "which key is in the GCM
;  context" flag is stale; force a re-install on the next record.
; ----------------------------------------------------------------------
Procedure Tls13RecInvalidateCipher()
  TlsCipherInstalled = 0
EndProcedure

; ----------------------------------------------------------------------
;  Tls13RecSetWriteKey / Tls13RecSetReadKey - install 16 key bytes and 12
;  iv bytes for one direction and RESET that direction's sequence number
;  to zero (RFC 8446 5.3).
; ----------------------------------------------------------------------
Procedure Tls13RecSetWriteKey(key.i, iv.i)
  Protected i.i
  i = 0
  While i < 16
    secTlsWKey[i] = PeekA(key + i) & 255
    i = i + 1
  Wend
  i = 0
  While i < 12
    secTlsWIv[i] = PeekA(iv + i) & 255
    i = i + 1
  Wend
  TlsWSeqLo = 0
  TlsWSeqHi = 0
  TlsWKeyed = 1
  TlsCipherInstalled = 0
EndProcedure

; Installs the key (16 bytes at key) and the IV (12 bytes at iv) for records
; being received, and starts their sequence number at 0.
Procedure Tls13RecSetReadKey(key.i, iv.i)
  Protected i.i
  i = 0
  While i < 16
    secTlsRKey[i] = PeekA(key + i) & 255
    i = i + 1
  Wend
  i = 0
  While i < 12
    secTlsRIv[i] = PeekA(iv + i) & 255
    i = i + 1
  Wend
  TlsRSeqLo = 0
  TlsRSeqHi = 0
  TlsRKeyed = 1
  TlsCipherInstalled = 0
EndProcedure

; ----------------------------------------------------------------------
;  TlsRecUseWriteKey / TlsRecUseReadKey - make sure the one global GCM
;  context holds the key this direction needs. The flag is PUBLIC (which
;  direction we are working on), so branching on it leaks nothing.
; ----------------------------------------------------------------------
Procedure TlsRecUseWriteKey()
  If TlsCipherInstalled <> 1
    GcmInit(@secTlsWKey[0], 16)
    TlsCipherInstalled = 1
  EndIf
EndProcedure

; Makes the receive key the one the AES-GCM engine is set up with, if it is
; not already.
Procedure TlsRecUseReadKey()
  If TlsCipherInstalled <> 2
    GcmInit(@secTlsRKey[0], 16)
    TlsCipherInstalled = 2
  EndIf
EndProcedure

; ----------------------------------------------------------------------
;  TlsRecNonce(iv, seqHi, seqLo) - RFC 8446 5.3 per-record nonce: the
;  eight sequence bytes, big-endian, land in nonce[4..11] - RIGHT-ALIGNED
;  - XORed with the iv. seqHi and seqLo are each 0..$FFFFFFFF, so a right
;  shift brings in zeros and & 255 keeps the byte the shift landed.
; ----------------------------------------------------------------------
Procedure TlsRecNonce(iv.i, seqHi.i, seqLo.i)
  Protected i.i
  i = 0
  While i < 4
    TlsNonce[i] = PeekA(iv + i) & 255
    i = i + 1
  Wend
  TlsNonce[4]  = (PeekA(iv + 4)  & 255) ! ((seqHi >> 24) & 255)
  TlsNonce[5]  = (PeekA(iv + 5)  & 255) ! ((seqHi >> 16) & 255)
  TlsNonce[6]  = (PeekA(iv + 6)  & 255) ! ((seqHi >> 8) & 255)
  TlsNonce[7]  = (PeekA(iv + 7)  & 255) ! (seqHi & 255)
  TlsNonce[8]  = (PeekA(iv + 8)  & 255) ! ((seqLo >> 24) & 255)
  TlsNonce[9]  = (PeekA(iv + 9)  & 255) ! ((seqLo >> 16) & 255)
  TlsNonce[10] = (PeekA(iv + 10) & 255) ! ((seqLo >> 8) & 255)
  TlsNonce[11] = (PeekA(iv + 11) & 255) ! (seqLo & 255)
EndProcedure

; ----------------------------------------------------------------------
;  TlsRecAad(fraglen) - the RFC 8446 5.2 additional data: the record
;  header exactly as it goes on the wire, with the length of the
;  ENCRYPTED fragment (plaintext + type byte + padding + tag).
; ----------------------------------------------------------------------
Procedure TlsRecAad(fraglen.i)
  TlsAad[0] = #TLS_CT_APPDATA
  TlsAad[1] = $03
  TlsAad[2] = $03
  TlsAad[3] = (fraglen >> 8) & 255
  TlsAad[4] = fraglen & 255
EndProcedure

; ----------------------------------------------------------------------
;  TlsRecWriteSeqNext() / TlsRecReadSeqNext() - step a 64-bit sequence
;  number kept as two 32-bit halves, REFUSING to wrap (RFC 8446 5.3).
;  Returns 1, or 0 when the counter is already all ones. Both halves are
;  masked to 32 bits so the carry happens on this 64-bit target exactly
;  where it happens on a 32-bit one (change 2 in the header).
; ----------------------------------------------------------------------
Procedure.i TlsRecWriteSeqNext()
  If TlsWSeqLo = #TLSREC_W32 And TlsWSeqHi = #TLSREC_W32
    Tls13RecErr = #TLSREC_ERR_SEQ_OVERFLOW
    ProcedureReturn 0
  EndIf
  TlsWSeqLo = (TlsWSeqLo + 1) & #TLSREC_W32
  If TlsWSeqLo = 0
    TlsWSeqHi = (TlsWSeqHi + 1) & #TLSREC_W32
  EndIf
  ProcedureReturn 1
EndProcedure

; Adds one to the 64-bit sequence number of received records. Returns 1, or
; 0 with Tls13RecErr = #TLSREC_ERR_SEQ_OVERFLOW if the number is already at
; its maximum.
Procedure.i TlsRecReadSeqNext()
  If TlsRSeqLo = #TLSREC_W32 And TlsRSeqHi = #TLSREC_W32
    Tls13RecErr = #TLSREC_ERR_SEQ_OVERFLOW
    ProcedureReturn 0
  EndIf
  TlsRSeqLo = (TlsRSeqLo + 1) & #TLSREC_W32
  If TlsRSeqLo = 0
    TlsRSeqHi = (TlsRSeqHi + 1) & #TLSREC_W32
  EndIf
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  Tls13RecProtect(ctype, plain, plen, padlen, dst, dstmax)
;      -> record length written at dst, or 0 on refusal.
;
;  Output: header(5) || ciphertext(plen + 1 + padlen) || tag(16).
;  The real content type goes INSIDE the sealed data; the outer type is
;  always 23. plain and dst may NOT overlap.
; ----------------------------------------------------------------------
Procedure.i Tls13RecProtect(ctype.i, plain.i, plen.i, padlen.i, dst.i, dstmax.i)
  Protected i.i
  Protected innerlen.i
  Protected fraglen.i
  Protected protectedOk.i

  Tls13RecErr = #TLSREC_OK

  If TlsWKeyed = 0
    Tls13RecErr = #TLSREC_ERR_NO_KEY
    ProcedureReturn 0
  EndIf
  If plen < 0 Or padlen < 0
    Tls13RecErr = #TLSREC_ERR_TOO_LONG
    ProcedureReturn 0
  EndIf
  If plen > #TLS_MAX_PLAINTEXT
    Tls13RecErr = #TLSREC_ERR_TOO_LONG
    ProcedureReturn 0
  EndIf

  innerlen = plen + 1 + padlen
  If innerlen > #TLS_MAX_CIPHERTEXT - #TLS_TAG_LEN
    Tls13RecErr = #TLSREC_ERR_TOO_LONG
    ProcedureReturn 0
  EndIf
  fraglen = innerlen + #TLS_TAG_LEN
  If #TLS_REC_HDR + fraglen > dstmax
    Tls13RecErr = #TLSREC_ERR_BUF_TOO_SMALL
    ProcedureReturn 0
  EndIf

  ; ---- build the TLSInnerPlaintext straight into the output fragment
  i = 0
  While i < plen
    PokeB(dst + #TLS_REC_HDR + i, PeekA(plain + i) & 255)
    i = i + 1
  Wend
  PokeB(dst + #TLS_REC_HDR + plen, ctype & 255)
  i = 0
  While i < padlen
    PokeB(dst + #TLS_REC_HDR + plen + 1 + i, 0)
    i = i + 1
  Wend

  ; ---- header (which is also the additional data)
  TlsRecAad(fraglen)
  i = 0
  While i < #TLS_REC_HDR
    PokeB(dst + i, TlsAad[i])
    i = i + 1
  Wend

  ; ---- seal in place, tag straight after the ciphertext
  TlsRecUseWriteKey()
  TlsRecNonce(@secTlsWIv[0], TlsWSeqHi, TlsWSeqLo)
  If TlsRecEncryptHook<>0
    protectedOk=TlsRecEncryptHook(@secTlsWKey[0],@TlsNonce[0],@TlsAad[0],#TLS_REC_HDR,dst+#TLS_REC_HDR,innerlen,dst+#TLS_REC_HDR,dst+#TLS_REC_HDR+innerlen)
    Tls13RecInvalidateCipher()
    If protectedOk<>1 : Tls13RecErr=#TLSREC_ERR_CRYPTO : ProcedureReturn 0 : EndIf
  Else
  GcmEncrypt(@TlsNonce[0], 12, @TlsAad[0], #TLS_REC_HDR, dst + #TLS_REC_HDR, innerlen, dst + #TLS_REC_HDR, dst + #TLS_REC_HDR + innerlen)
  EndIf

  If TlsRecWriteSeqNext() = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn #TLS_REC_HDR + fraglen
EndProcedure

; ----------------------------------------------------------------------
;  Tls13RecUnprotect(rec, reclen) -> plaintext length, or -1.
;
;  ORDER: size limits first, then the tag, then the padding scan. Nothing
;  is parsed out of a record whose tag has not verified.
; ----------------------------------------------------------------------
Procedure.i Tls13RecUnprotect(rec.i, reclen.i)
  Protected fraglen.i
  Protected innerlen.i
  Protected hdrlen.i
  Protected ok.i
  Protected i.i

  Tls13RecErr = #TLSREC_OK
  TlsRecInnerType = 0

  If TlsRKeyed = 0
    Tls13RecErr = #TLSREC_ERR_NO_KEY
    ProcedureReturn -1
  EndIf
  If reclen < #TLS_REC_HDR + #TLS_TAG_LEN + 1
    Tls13RecErr = #TLSREC_ERR_SHORT_RECORD
    ProcedureReturn -1
  EndIf
  If (PeekA(rec) & 255) <> #TLS_CT_APPDATA
    ; A protected record MUST be labelled application_data (RFC 8446 5.2).
    Tls13RecErr = #TLSREC_ERR_BAD_OUTER_TYPE
    ProcedureReturn -1
  EndIf

  fraglen = reclen - #TLS_REC_HDR
  hdrlen = ((PeekA(rec + 3) & 255) << 8) | (PeekA(rec + 4) & 255)
  If hdrlen <> fraglen
    Tls13RecErr = #TLSREC_ERR_LEN_MISMATCH
    ProcedureReturn -1
  EndIf
  If fraglen > #TLS_MAX_CIPHERTEXT
    Tls13RecErr = #TLSREC_ERR_TOO_LONG
    ProcedureReturn -1
  EndIf

  innerlen = fraglen - #TLS_TAG_LEN

  ; the additional data is the header exactly as received
  i = 0
  While i < #TLS_REC_HDR
    TlsAad[i] = PeekA(rec + i) & 255
    i = i + 1
  Wend

  TlsRecUseReadKey()
  TlsRecNonce(@secTlsRIv[0], TlsRSeqHi, TlsRSeqLo)
  ; in-place: gcm hashes the ciphertext before it writes the plaintext
  If TlsRecDecryptHook<>0
    ok=TlsRecDecryptHook(@secTlsRKey[0],@TlsNonce[0],@TlsAad[0],#TLS_REC_HDR,rec+#TLS_REC_HDR,innerlen,rec+#TLS_REC_HDR,rec+#TLS_REC_HDR+innerlen)
    Tls13RecInvalidateCipher()
  Else
  ok = GcmDecrypt(@TlsNonce[0], 12, @TlsAad[0], #TLS_REC_HDR, rec + #TLS_REC_HDR, innerlen, rec + #TLS_REC_HDR, rec + #TLS_REC_HDR + innerlen)
  EndIf
  If ok <> #TLSREC_W32
    ; THE TAG DID NOT VERIFY - or the verdict is not the exact authentic
    ; mask, which is treated the same way (change 1 in the header). The
    ; buffer holds GCM's plaintext anyway; nothing downstream may see it.
    Tls13RecErr = #TLSREC_ERR_BAD_TAG
    ProcedureReturn -1
  EndIf

  ; the sequence number advances on every record we ACCEPT
  If TlsRecReadSeqNext() = 0
    ProcedureReturn -1
  EndIf

  ; scan back over the zero padding for the content type
  i = innerlen - 1
  While i >= 0
    If (PeekA(rec + #TLS_REC_HDR + i) & 255) <> 0
      Break
    EndIf
    i = i - 1
  Wend
  If i < 0
    Tls13RecErr = #TLSREC_ERR_ALL_ZERO_INNER
    ProcedureReturn -1
  EndIf

  TlsRecInnerType = PeekA(rec + #TLS_REC_HDR + i) & 255
  If i > #TLS_MAX_PLAINTEXT
    Tls13RecErr = #TLSREC_ERR_TOO_LONG
    ProcedureReturn -1
  EndIf
  ProcedureReturn i
EndProcedure

; ----------------------------------------------------------------------
;  Tls13RecPlainAddr(rec) - where Tls13RecUnprotect left the plaintext.
; ----------------------------------------------------------------------
Procedure.i Tls13RecPlainAddr(rec.i)
  ProcedureReturn rec + #TLS_REC_HDR
EndProcedure

; ----------------------------------------------------------------------
;  Tls13RecBuildPlainHeader(dst, ctype, len, minorver) - a five-byte
;  header for an UNPROTECTED record: the ClientHello (minorver 1, RFC 8446
;  5.1 middlebox compatibility) and a pre-key alert (minorver 3).
; ----------------------------------------------------------------------
Procedure Tls13RecBuildPlainHeader(dst.i, ctype.i, len.i, minorver.i)
  PokeB(dst,     ctype & 255)
  PokeB(dst + 1, $03)
  PokeB(dst + 2, minorver & 255)
  PokeB(dst + 3, (len >> 8) & 255)
  PokeB(dst + 4, len & 255)
EndProcedure

; ==== PORTABLE CORE A64 END ====

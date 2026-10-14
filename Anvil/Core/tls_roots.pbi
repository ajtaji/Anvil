; ======================================================================
;  tls_roots.pbi - THE ROOT STORE. Every trust anchor a TLS connection
;  may chain to, read at run time from a PEM bundle on the stick and
;  decoded on the board.
;
;  WHY A FILE AND NOT COMPILED-IN ROOTS (Ron, 2026-10-14: "anvil should be
;  able to join any https" ... "anvil is to be a full service kernel").
;  The bundle is the Mozilla root store - the same file curl, Git and
;  most Linux systems carry as ca-bundle.crt / cacert.pem - so a payload
;  or a monitor command reaches any public HTTPS server, and the store is
;  updated by copying a newer file, not by rebuilding the monitor.
;
;  WHAT IS DONE HERE, ON THE BOARD, FOR EVERY CERTIFICATE IN THE FILE:
;  the PEM armour is found, the base64 decoded, the DER walked to the
;  subject Name and the subjectPublicKeyInfo, and the anchor handed to
;  x509 as BearSSL's br_x509_trust_anchor would carry it: the subject DN
;  (the whole SEQUENCE, which x509 compares to an issuer) and the public
;  key - an RSA modulus and exponent, or an EC curve and point. The chain
;  a server sends, its signatures, the host name and the dates are x509's
;  and tls13_hs's work, per connection.
;
;  WHAT x509 CAN AND CANNOT VERIFY, SAID HERE SO A COUNT IS NOT MISREAD.
;  RSA roots and EC P-256 roots verify. ecdsa.pi4 does not implement
;  P-384 or P-521 (it says so by name), and the Mozilla store has ~38
;  such roots. They ARE registered, so a chain ending at one is refused
;  as "curve not implemented" - a named gap - rather than as an unknown
;  CA. `tls roots` prints the counts by kind.
;
;  x509 KEEPS EVERY ANCHOR BY ADDRESS, so the DN and key bytes are copied
;  into tlsroot_arena, which lives for the life of the monitor. The PEM
;  text and one certificate's DER are scratch.
; ======================================================================

EnableExplicit

#TLSROOT_PEM_MAX   = 393216        ; the bundle; Mozilla's is ~190 KB
#TLSROOT_DER_MAX   = 8192          ; one certificate's DER
#TLSROOT_ARENA_MAX = 196608        ; DN + key of every anchor kept

#TLSROOT_OK          = 0
#TLSROOT_ERR_NOFILE  = -1          ; the bundle could not be opened
#TLSROOT_ERR_BIG     = -2          ; larger than #TLSROOT_PEM_MAX
#TLSROOT_ERR_READ    = -3
#TLSROOT_ERR_NONE    = -4          ; the file held no usable certificate
#TLSROOT_ERR_ARENA   = -5          ; the anchors outgrew the arena
#TLSROOT_ERR_STORAGE = -6          ; no medium mounted

Global Dim tlsroot_pem.a[#TLSROOT_PEM_MAX]
Global Dim tlsroot_der.a[#TLSROOT_DER_MAX]
Global Dim tlsroot_arena.a[#TLSROOT_ARENA_MAX]
Global Dim tlsroot_path.a[128]
Global tlsroot_arenaUsed.i
Global tlsroot_loaded.i            ; 1 once a load succeeded
Global tlsroot_err.i
Global tlsroot_certs.i             ; certificates seen in the file
Global tlsroot_rsa.i
Global tlsroot_p256.i
Global tlsroot_ecOther.i           ; P-384 / P-521: registered, not verifiable
Global tlsroot_bad.i               ; armour or DER this file would not parse
Global tlsroot_full.i              ; certificates past x509's table
Global tlsroot_bytes.i             ; size of the bundle read

; DER cursor - the last element read by tlsroot_Tlv.
Global tlsroot_tag.i
Global tlsroot_hdr.i
Global tlsroot_len.i

; ----------------------------------------------------------------------
;  BASE64 (RFC 4648). Whitespace is skipped; anything else outside the
;  alphabet ends the block as malformed.
; ----------------------------------------------------------------------
Procedure.i tlsroot_B64Val(c.i)
  If c >= 65 And c <= 90
    ProcedureReturn c - 65
  EndIf
  If c >= 97 And c <= 122
    ProcedureReturn c - 71
  EndIf
  If c >= 48 And c <= 57
    ProcedureReturn c + 4
  EndIf
  If c = 43
    ProcedureReturn 62
  EndIf
  If c = 47
    ProcedureReturn 63
  EndIf
  If c = 61
    ProcedureReturn -2               ; '=' padding
  EndIf
  If c = 32 Or c = 9 Or c = 10 Or c = 13
    ProcedureReturn -3               ; whitespace
  EndIf
  ProcedureReturn -1
EndProcedure

; Decodes pem[from..to) into tlsroot_der. Returns the byte count, or -1.
Procedure.i tlsroot_B64Decode(from.i, upto.i)
  Define i.i
  Define v.i
  Define acc.i
  Define bits.i
  Define n.i
  acc = 0
  bits = 0
  n = 0
  For i = from To upto - 1
    v = tlsroot_B64Val(tlsroot_pem[i])
    If v = -1
      ProcedureReturn -1
    EndIf
    If v = -2
      Break
    EndIf
    If v >= 0
      acc = ((acc << 6) | v) & $FFFFFF
      bits = bits + 6
      If bits >= 8
        bits = bits - 8
        If n >= #TLSROOT_DER_MAX
          ProcedureReturn -1
        EndIf
        tlsroot_der[n] = (acc >> bits) & $FF
        n = n + 1
      EndIf
    EndIf
  Next
  ProcedureReturn n
EndProcedure

; ----------------------------------------------------------------------
;  DER. tlsroot_Tlv reads the element at `at` inside der[0..lim) and
;  returns its END offset (at + header + length), or -1 if the header or
;  the length runs past lim. Lengths of up to four bytes are accepted.
; ----------------------------------------------------------------------
Procedure.i tlsroot_Tlv(at.i, lim.i)
  Define b.i
  Define k.i
  Define i.i
  Define ln.i
  If at + 2 > lim
    ProcedureReturn -1
  EndIf
  tlsroot_tag = tlsroot_der[at]
  b = tlsroot_der[at + 1]
  If b < $80
    tlsroot_hdr = 2
    ln = b
  Else
    k = b & $7F
    If k < 1 Or k > 4 Or at + 2 + k > lim
      ProcedureReturn -1
    EndIf
    ln = 0
    For i = 0 To k - 1
      ln = (ln << 8) | tlsroot_der[at + 2 + i]
    Next
    tlsroot_hdr = 2 + k
  EndIf
  tlsroot_len = ln
  If at + tlsroot_hdr + ln > lim
    ProcedureReturn -1
  EndIf
  ProcedureReturn at + tlsroot_hdr + ln
EndProcedure

; der[at..at+n) equals the n bytes at *lit.
Procedure.i tlsroot_Same(at.i, *lit, n.i)
  Define i.i
  For i = 0 To n - 1
    If tlsroot_der[at + i] <> PeekA(*lit + i)
      ProcedureReturn 0
    EndIf
  Next
  ProcedureReturn 1
EndProcedure

; Copies der[at..at+n) into the arena; its address, or 0 when full.
Procedure.i tlsroot_Keep(at.i, n.i)
  Define a.i
  Define i.i
  If n < 1 Or tlsroot_arenaUsed + n > #TLSROOT_ARENA_MAX
    ProcedureReturn 0
  EndIf
  a = @tlsroot_arena[tlsroot_arenaUsed]
  For i = 0 To n - 1
    tlsroot_arena[tlsroot_arenaUsed + i] = tlsroot_der[at + i]
  Next
  tlsroot_arenaUsed = tlsroot_arenaUsed + n
  ProcedureReturn a
EndProcedure

; ----------------------------------------------------------------------
;  One certificate (DER in tlsroot_der[0..n)) to one x509 anchor.
;  1 registered, 0 not parsed, -1 the arena is full.
;
;    Certificate  ::= SEQUENCE { tbsCertificate, signatureAlgorithm, sig }
;    TBSCertificate ::= SEQUENCE { [0] version OPTIONAL, serialNumber,
;        signature, issuer, validity, subject, subjectPublicKeyInfo, ... }
;    SubjectPublicKeyInfo ::= SEQUENCE { AlgorithmIdentifier, BIT STRING }
;    RSAPublicKey ::= SEQUENCE { modulus INTEGER, publicExponent INTEGER }
; ----------------------------------------------------------------------
Procedure.i tlsroot_Add(n.i)
  Define p.i
  Define e.i
  Define tbsEnd.i
  Define i.i
  Define dnAt.i
  Define dnLen.i
  Define algEnd.i
  Define keyKind.i
  Define curve.i
  Define bitAt.i
  Define bitEnd.i
  Define nAt.i
  Define nLen.i
  Define eAt.i
  Define eLen.i
  Define aDn.i
  Define aN.i
  Define aE.i
  Define rsaEnd.i

  ; Certificate, then TBSCertificate
  If tlsroot_Tlv(0, n) < 0 Or tlsroot_tag <> $30
    ProcedureReturn 0
  EndIf
  p = tlsroot_hdr
  tbsEnd = tlsroot_Tlv(p, n)
  If tbsEnd < 0 Or tlsroot_tag <> $30
    ProcedureReturn 0
  EndIf
  p = p + tlsroot_hdr
  ; [0] version, if present
  e = tlsroot_Tlv(p, tbsEnd)
  If e < 0
    ProcedureReturn 0
  EndIf
  If tlsroot_tag = $A0
    p = e
  EndIf
  ; serialNumber, signature, issuer, validity
  For i = 1 To 4
    e = tlsroot_Tlv(p, tbsEnd)
    If e < 0
      ProcedureReturn 0
    EndIf
    p = e
  Next
  ; subject - the whole SEQUENCE, header included
  e = tlsroot_Tlv(p, tbsEnd)
  If e < 0 Or tlsroot_tag <> $30
    ProcedureReturn 0
  EndIf
  dnAt = p
  dnLen = e - p
  p = e
  ; subjectPublicKeyInfo
  e = tlsroot_Tlv(p, tbsEnd)
  If e < 0 Or tlsroot_tag <> $30
    ProcedureReturn 0
  EndIf
  p = p + tlsroot_hdr
  algEnd = tlsroot_Tlv(p, e)
  If algEnd < 0 Or tlsroot_tag <> $30
    ProcedureReturn 0
  EndIf
  ; the algorithm OID, and for EC the curve OID after it
  p = p + tlsroot_hdr
  If tlsroot_Tlv(p, algEnd) < 0 Or tlsroot_tag <> $06
    ProcedureReturn 0
  EndIf
  keyKind = 0
  curve = 0
  If tlsroot_len = 9 And tlsroot_Same(p + tlsroot_hdr, ?tlsroot_oidRsa, 9) <> 0
    keyKind = 1
  ElseIf tlsroot_len = 7 And tlsroot_Same(p + tlsroot_hdr, ?tlsroot_oidEc, 7) <> 0
    keyKind = 2
    p = p + tlsroot_hdr + tlsroot_len
    If tlsroot_Tlv(p, algEnd) < 0 Or tlsroot_tag <> $06
      ProcedureReturn 0
    EndIf
    If tlsroot_len = 8 And tlsroot_Same(p + tlsroot_hdr, ?tlsroot_oidP256, 8) <> 0
      curve = 23
    ElseIf tlsroot_len = 5 And tlsroot_Same(p + tlsroot_hdr, ?tlsroot_oidP384, 5) <> 0
      curve = 24
    ElseIf tlsroot_len = 5 And tlsroot_Same(p + tlsroot_hdr, ?tlsroot_oidP521, 5) <> 0
      curve = 25
    Else
      ProcedureReturn 0
    EndIf
  Else
    ProcedureReturn 0
  EndIf
  ; the BIT STRING; whole bytes only
  bitAt = algEnd
  bitEnd = tlsroot_Tlv(bitAt, e)
  If bitEnd < 0 Or tlsroot_tag <> $03 Or tlsroot_len < 2
    ProcedureReturn 0
  EndIf
  If tlsroot_der[bitAt + tlsroot_hdr] <> 0
    ProcedureReturn 0
  EndIf
  p = bitAt + tlsroot_hdr + 1

  If keyKind = 1
    rsaEnd = tlsroot_Tlv(p, bitEnd)
    If rsaEnd < 0 Or tlsroot_tag <> $30
      ProcedureReturn 0
    EndIf
    p = p + tlsroot_hdr
    e = tlsroot_Tlv(p, rsaEnd)
    If e < 0 Or tlsroot_tag <> $02
      ProcedureReturn 0
    EndIf
    nAt = p + tlsroot_hdr
    nLen = tlsroot_len
    While nLen > 1 And tlsroot_der[nAt] = 0
      nAt = nAt + 1
      nLen = nLen - 1
    Wend
    p = e
    e = tlsroot_Tlv(p, rsaEnd)
    If e < 0 Or tlsroot_tag <> $02
      ProcedureReturn 0
    EndIf
    eAt = p + tlsroot_hdr
    eLen = tlsroot_len
    While eLen > 1 And tlsroot_der[eAt] = 0
      eAt = eAt + 1
      eLen = eLen - 1
    Wend
    aDn = tlsroot_Keep(dnAt, dnLen)
    aN = tlsroot_Keep(nAt, nLen)
    aE = tlsroot_Keep(eAt, eLen)
    If aDn = 0 Or aN = 0 Or aE = 0
      ProcedureReturn -1
    EndIf
    X509AddAnchorRSA(1, aDn, dnLen, aN, nLen, aE, eLen)
    tlsroot_rsa = tlsroot_rsa + 1
    ProcedureReturn 1
  EndIf

  ; EC: the point is the BIT STRING's bytes after the unused-bits octet
  nAt = p
  nLen = bitEnd - p
  aDn = tlsroot_Keep(dnAt, dnLen)
  aN = tlsroot_Keep(nAt, nLen)
  If aDn = 0 Or aN = 0
    ProcedureReturn -1
  EndIf
  X509AddAnchorEC(1, aDn, dnLen, curve, aN, nLen)
  If curve = 23
    tlsroot_p256 = tlsroot_p256 + 1
  Else
    tlsroot_ecOther = tlsroot_ecOther + 1
  EndIf
  ProcedureReturn 1
EndProcedure

; pem[at..at+n) equals the n bytes at *lit.
Procedure.i tlsroot_PemIs(at.i, *lit, n.i, lim.i)
  Define i.i
  If at + n > lim
    ProcedureReturn 0
  EndIf
  For i = 0 To n - 1
    If tlsroot_pem[at + i] <> PeekA(*lit + i)
      ProcedureReturn 0
    EndIf
  Next
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  TlsRootsLoad(*path) - read the bundle and register every root. *path
;  0 means the `tls.roots` setting, or 2:/tls/roots.pem without one.
;  Returns the number of anchors registered (> 0), or a negative
;  #TLSROOT_ERR_*. The previous store is replaced only by a load that
;  registered at least one root.
; ----------------------------------------------------------------------
Procedure.i TlsRootsLoad(*path)
  Define size.i
  Define got.i
  Define off.i
  Define i.i
  Define j.i
  Define n.i
  Define r.i
  Define k.i
  Define src.i

  src = *path
  If src = 0
    src = SettingsGet("tls.roots")
  EndIf
  If src = 0
    src = ?tlsroot_defPath
  EndIf
  k = 0
  While k < 127 And PeekA(src + k) <> 0
    tlsroot_path[k] = PeekA(src + k)
    k = k + 1
  Wend
  tlsroot_path[k] = 0

  If HwStorageUp() = 0
    tlsroot_err = #TLSROOT_ERR_STORAGE
    ProcedureReturn tlsroot_err
  EndIf
  If HwFileOpen(@tlsroot_path[0]) = 0
    tlsroot_err = #TLSROOT_ERR_NOFILE
    ProcedureReturn tlsroot_err
  EndIf
  size = HwFileSize()
  If size > #TLSROOT_PEM_MAX
    HwFileClose()
    tlsroot_err = #TLSROOT_ERR_BIG
    ProcedureReturn tlsroot_err
  EndIf
  off = 0
  While off < size
    n = size - off
    If n > 32768
      n = 32768
    EndIf
    got = HwFileReadAt(off, @tlsroot_pem[off], n)
    If got <= 0
      HwFileClose()
      tlsroot_err = #TLSROOT_ERR_READ
      ProcedureReturn tlsroot_err
    EndIf
    off = off + got
  Wend
  HwFileClose()
  tlsroot_bytes = size

  X509ResetAnchors()
  tlsroot_arenaUsed = 0
  tlsroot_certs = 0
  tlsroot_rsa = 0
  tlsroot_p256 = 0
  tlsroot_ecOther = 0
  tlsroot_bad = 0
  tlsroot_full = 0
  tlsroot_loaded = 0

  i = 0
  While i < size
    If tlsroot_PemIs(i, ?tlsroot_begin, 27, size) <> 0
      j = i + 27
      While j < size And tlsroot_PemIs(j, ?tlsroot_end, 25, size) = 0
        j = j + 1
      Wend
      If j >= size
        Break
      EndIf
      tlsroot_certs = tlsroot_certs + 1
      n = tlsroot_B64Decode(i + 27, j)
      If n <= 0
        tlsroot_bad = tlsroot_bad + 1
      ElseIf xNumAnchors >= #X_MAX_ANCHORS
        tlsroot_full = tlsroot_full + 1
      Else
        r = tlsroot_Add(n)
        If r = 0
          tlsroot_bad = tlsroot_bad + 1
        ElseIf r < 0
          tlsroot_err = #TLSROOT_ERR_ARENA
          ProcedureReturn tlsroot_err
        EndIf
      EndIf
      i = j + 25
    Else
      i = i + 1
    EndIf
  Wend
  For i = 0 To #TLSROOT_DER_MAX - 1
    tlsroot_der[i] = 0
  Next
  If xNumAnchors = 0
    tlsroot_err = #TLSROOT_ERR_NONE
    ProcedureReturn tlsroot_err
  EndIf
  tlsroot_loaded = 1
  tlsroot_err = #TLSROOT_OK
  ProcedureReturn xNumAnchors
EndProcedure

; Loads the store once; later calls answer from the first load.
Procedure.i TlsRootsEnsure()
  If tlsroot_loaded <> 0
    ProcedureReturn xNumAnchors
  EndIf
  ProcedureReturn TlsRootsLoad(0)
EndProcedure

Procedure.i TlsRootsLoaded() : ProcedureReturn tlsroot_loaded : EndProcedure
Procedure.i TlsRootsError() : ProcedureReturn tlsroot_err : EndProcedure

Procedure.i TlsRootsErrorText(code.i)
  Select code
    Case #TLSROOT_OK
      ProcedureReturn "the root store is loaded"
    Case #TLSROOT_ERR_NOFILE
      ProcedureReturn "the root bundle file could not be opened - copy a PEM CA bundle (cacert.pem) to the stick at the tls.roots path"
    Case #TLSROOT_ERR_BIG
      ProcedureReturn "the root bundle is larger than 384 KB"
    Case #TLSROOT_ERR_READ
      ProcedureReturn "the root bundle could not be read"
    Case #TLSROOT_ERR_NONE
      ProcedureReturn "the root bundle holds no certificate this board could parse"
    Case #TLSROOT_ERR_ARENA
      ProcedureReturn "the roots outgrew the 192 KB anchor store"
    Case #TLSROOT_ERR_STORAGE
      ProcedureReturn "no storage medium is mounted"
  EndSelect
  ProcedureReturn "unknown root-store error"
EndProcedure

; `tls roots` - what the store holds, by kind.
Procedure TlsRootsShow()
  Print("Root store: ")
  str_print_at(@tlsroot_path[0])
  If tlsroot_loaded = 0
    Print(" - not loaded: ")
    str_print_at(TlsRootsErrorText(tlsroot_err)) : PrintNl()
    ProcedureReturn
  EndIf
  Print(", ")
  PrintDec(tlsroot_bytes)
  PrintN(" bytes")
  Print("  certificates in the file  ")
  PrintDec(tlsroot_certs)
  PrintNl()
  Print("  RSA roots                 ")
  PrintDec(tlsroot_rsa)
  PrintN("   verifiable")
  Print("  EC P-256 roots            ")
  PrintDec(tlsroot_p256)
  PrintN("   verifiable")
  Print("  EC P-384 / P-521 roots    ")
  PrintDec(tlsroot_ecOther)
  PrintN("   registered; ecdsa.pi4 cannot verify these curves yet")
  If tlsroot_bad > 0
    Print("  not parsed                ")
    PrintDec(tlsroot_bad)
    PrintNl()
  EndIf
  If tlsroot_full > 0
    Print("  past x509's table         ")
    PrintDec(tlsroot_full)
    PrintNl()
  EndIf
  Print("  anchor bytes kept         ")
  PrintDec(tlsroot_arenaUsed)
  PrintNl()
EndProcedure

DataSection
  tlsroot_defPath:   ; 2:/tls/roots.pem
    Data.a 50, 58, 47, 116, 108, 115, 47, 114, 111, 111, 116, 115, 46, 112, 101, 109, 0
  tlsroot_begin:     ; -----BEGIN CERTIFICATE-----
    Data.a 45, 45, 45, 45, 45, 66, 69, 71, 73, 78, 32, 67, 69, 82, 84, 73, 70, 73, 67, 65, 84, 69, 45, 45, 45, 45, 45
  tlsroot_end:       ; -----END CERTIFICATE-----
    Data.a 45, 45, 45, 45, 45, 69, 78, 68, 32, 67, 69, 82, 84, 73, 70, 73, 67, 65, 84, 69, 45, 45, 45, 45, 45
  tlsroot_oidRsa:    ; 1.2.840.113549.1.1.1 rsaEncryption
    Data.a $2A, $86, $48, $86, $F7, $0D, $01, $01, $01
  tlsroot_oidEc:     ; 1.2.840.10045.2.1 id-ecPublicKey
    Data.a $2A, $86, $48, $CE, $3D, $02, $01
  tlsroot_oidP256:   ; 1.2.840.10045.3.1.7 prime256v1
    Data.a $2A, $86, $48, $CE, $3D, $03, $01, $07
  tlsroot_oidP384:   ; 1.3.132.0.34 secp384r1
    Data.a $2B, $81, $04, $00, $22
  tlsroot_oidP521:   ; 1.3.132.0.35 secp521r1
    Data.a $2B, $81, $04, $00, $23
EndDataSection

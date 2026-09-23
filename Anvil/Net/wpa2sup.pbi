; ======================================================================
;  wpa2sup.pi4 - THE WPA2-PSK FOUR-WAY HANDSHAKE, IN THE HOST.
;
;  ======================================================================
;  WHY THIS FILE EXISTS, AND WHY IT SHOULD NOT HAVE HAD TO
;  ======================================================================
;  On the Pico and on the Uno R4 the radio firmware runs the supplicant
;  and the host hands it an ASCII passphrase. That is not a property of
;  the CYW43 family - IT IS A PROPERTY OF THE FIRMWARE IMAGE, and the
;  two images on this bench say so themselves. Their build strings, in
;  full, extracted from the blobs:
;
;    Firmware/CYW43439/wb43439A0-7.95.49.00.combined.bin
;      43439a0-roml/sdio-g-pool-p2p-IDSUP-IDAUTH-pktfilter-keepalive-
;      aoe-lpc-swdiv-srfast-fuart-btcx-noclminc-clm_min-fbt-mfp-SAE-
;      wowlpf-tko-nvd-btsdio   Version: 7.95.61 (abcd531 CY)
;
;    RaspberryPi4/Reference/firmware/brcmfmac43455-sdio.bin
;      43455c0-roml/43455_sdio-pno-aoe-pktfilter-pktctx-wfds-mfp-
;      dfsradar-wowlpf-noclminc-clm_min-obss-obssdump-swdiv-gtkoe-
;      roamprof-txbf-ve-EXTSAE-dpp-sr-okc-bpd   Version: 7.45.265
;      (28bca26 CY)   Date: Tue 2023-08-29 01:51:02 PDT
;
;  `idsup` is the in-dongle supplicant. The Pico's image HAS it; the
;  Pi 4's image DOES NOT, and where the Pico's says `sae` this one says
;  `extsae` - external SAE, meaning the host does it. That single word
;  is the reason this file exists, and it is why the bench's four
;  refusals on 2026-08-27 (`bsscfg:sup_wpa`, `bsscfg:sup_wpa2_eapver`,
;  `bsscfg:sup_wpa_tmo` all -23, WLC_SET_WSEC_PMK -2 at both struct
;  sizes) were one fact arriving four times rather than four bugs.
;
;  IT IS ALSO WHAT EVERY RASPBERRY PI ON EARTH DOES. brcmfmac with this
;  image has no firmware supplicant either; wpa_supplicant in userspace
;  runs the four-way handshake over the data path and plumbs the
;  finished keys down with `bsscfg:wsec_key`. This file is that, minus
;  the operating system.
;
;  ======================================================================
;  WHAT IT IS NOT
;  ======================================================================
;  NOT a general 802.1X implementation. WPA2-PSK with CCMP only:
;  key descriptor version 2 (HMAC-SHA1-128 MIC, NIST AES key wrap),
;  descriptor type 2 (RSN). No TKIP - the MIC would be HMAC-MD5 and the
;  key data RC4, neither of which exists on this target and both of
;  which are deprecated. No WPA1, no 802.1X/EAP, no PMKSA caching, no
;  SAE, no group-key-only rekey handshake yet.
;
;  A frame it does not understand is REFUSED WITH A NAMED CODE. It is
;  never quietly dropped, because a supplicant that silently ignores
;  something produces a link that "just does not come up".
;
;  NO I/O AND NO PRINTING. Exactly net.pi4's shape: the caller hands it
;  a received 802.3 frame and takes back a frame to send. That is what
;  makes it testable off the board, and it is also why a library that
;  handles key material cannot choose somebody's transport for them.
;
;  ======================================================================
;  WHAT THE CALLER MUST INCLUDE FIRST
;  ======================================================================
;      RaspberryPi4/Lib/sha1.pi4
;      RaspberryPi4/Lib/hmacsha1.pi4        (the PRF and the MIC)
;      RaspberryPi4/Lib/aes.pi4
;      RaspberryPi4/Lib/keywrap.pi4         (message 3's key data)
;
;  pbkdf2.pi4 is NOT one of them. The PMK arrives ready-made, because
;  deriving it costs about ten seconds on this part with the MMU off
;  and therefore happens in its own payload - see pi4WifiPmk.pi4.
;
;  ======================================================================
;  THE SHAPE OF THE EXCHANGE, SO THE CODE BELOW READS AS A STORY
;  ======================================================================
;    M1  AP -> us    ANonce, no MIC.
;                    We pick SNonce, derive
;                      PTK = PRF-384(PMK, "Pairwise key expansion",
;                                    Min(AA,SPA) || Max(AA,SPA) ||
;                                    Min(ANonce,SNonce) || Max(...))
;                    KCK = PTK[0..15]   KEK = PTK[16..31]
;                    TK  = PTK[32..47]
;    M2  us -> AP    SNonce, our RSN IE as key data, MIC under KCK.
;    M3  AP -> us    MIC under KCK - VERIFY IT, this is the step that
;                    proves the AP knows the PMK - and key data wrapped
;                    under KEK holding the AP's RSN IE and the GTK.
;    M4  us -> AP    MIC, empty key data. The AP installs the PTK when
;                    it arrives; we install ours just before sending it,
;                    because after M4 the AP may encrypt immediately.
;
;  ======================================================================
;  THE REPLAY COUNTER IS ECHOED, NEVER INVENTED
;  ======================================================================
;  A supplicant's replies carry the counter from the message they
;  answer. It is 8 bytes and it is copied, not parsed into an integer:
;  it is an opaque 64-bit value on the wire and turning it into a number
;  is one endianness argument nobody needs.
;
;  M3 IS ACCEPTED ONLY WITH A COUNTER GREATER THAN M1's, compared as
;  eight big-endian bytes. That is what stops a replayed message 3.
;
;  ======================================================================
;  WHAT IS DELIBERATELY NOT CHECKED, SAID OUT LOUD
;  ======================================================================
;  THE AP's RSN IE IN MESSAGE 3 IS PARSED PAST BUT NOT COMPARED WITH
;  THE BEACON'S. In a full supplicant that comparison is what defeats a
;  downgrade attack by a man in the middle: an attacker who could edit
;  the beacon into offering a weaker cipher would be caught here,
;  because message 3 is protected by a MIC and the beacon is not. This
;  file does not have the beacon's RSN IE - the scan table keeps a
;  privacy bit and not the element - so the check cannot be written
;  honestly yet, and a check that compares nothing would be worse than
;  its absence. WHAT IS STILL TRUE WITHOUT IT: the MIC on message 3
;  proves the far end holds the PMK, so the passphrase still
;  authenticates the access point. The gap is narrower than it sounds
;  and it is a gap. Recorded rather than glossed.
; ======================================================================

; ----------------------------------------------------------------------
;  802.3 and 802.1X framing. Offsets from the first byte of the frame.
; ----------------------------------------------------------------------
#WPA2_ETH_DA      = 0
#WPA2_ETH_SA      = 6
#WPA2_ETH_TYPE    = 12
#WPA2_ETH_HDR     = 14

#WPA2_1X_VER      = 14        ; 802.1X: version, type, length
#WPA2_1X_TYPE     = 15
#WPA2_1X_LEN      = 16
#WPA2_1X_HDR      = 4
#WPA2_1X_KEY      = 3         ; type 3 = EAPOL-Key

; The EAPOL-Key body, offsets from the first byte of the FRAME (so they
; already include the 14 Ethernet and 4 802.1X bytes). Written this way
; on purpose: every access in this file is against the frame, and a
; second base to add in is a second thing to forget.
#WPA2_K_DESC      = 18        ; 1   descriptor type, 2 = RSN
#WPA2_K_INFO      = 19        ; 2   key information, BIG endian
#WPA2_K_LEN       = 21        ; 2   key length, big endian
#WPA2_K_REPLAY    = 23        ; 8   replay counter, opaque
#WPA2_K_NONCE     = 31        ; 32
#WPA2_K_IV        = 63        ; 16
#WPA2_K_RSC       = 79        ; 8
#WPA2_K_ID        = 87        ; 8
#WPA2_K_MIC       = 95        ; 16
#WPA2_K_DATALEN   = 111       ; 2   big endian
#WPA2_K_DATA      = 113
#WPA2_K_BODY      = 95        ; the body's own length without key data
#WPA2_FRAME_MIN   = 113       ; 14 + 4 + 95, a key frame with no data

; Key Information, IEEE 802.11 table 12-8.
#WPA2_KI_VERSION  = $0007
#WPA2_KI_PAIRWISE = $0008
#WPA2_KI_INSTALL  = $0040
#WPA2_KI_ACK      = $0080
#WPA2_KI_MIC      = $0100
#WPA2_KI_SECURE   = $0200
#WPA2_KI_ERROR    = $0400
#WPA2_KI_REQUEST  = $0800
#WPA2_KI_ENCRYPTED = $1000

; Key descriptor version 2 is HMAC-SHA1-128 for the MIC and NIST AES
; key wrap for the key data. Version 1 is HMAC-MD5 + RC4 (TKIP) and
; version 3 is AES-128-CMAC (used with PSK-SHA256 and with management
; frame protection). Only 2 is implemented and the other two are
; refused by name rather than mis-handled.
#WPA2_KDV_SHA1    = 2

#WPA2_DESC_RSN    = 2

; Sizes.
#WPA2_PMK_LEN     = 32
#WPA2_NONCE_LEN   = 32
#WPA2_PTK_LEN     = 48        ; KCK 16 + KEK 16 + TK 16, for CCMP
#WPA2_KCK_OFF     = 0
#WPA2_KEK_OFF     = 16
#WPA2_TK_OFF      = 32
#WPA2_KCK_LEN     = 16
#WPA2_KEK_LEN     = 16
#WPA2_TK_LEN      = 16
#WPA2_MIC_LEN     = 16
#WPA2_RSC_LEN     = 8
#WPA2_GTK_MAX     = 32
#WPA2_IE_MAX      = 64        ; our RSN IE, with room to spare
#WPA2_KD_MAX      = 256       ; unwrapped key data
#WPA2_TX_MAX      = 256       ; the largest reply this file builds

; The PRF's message is label || 0x00 || data || counter. The longest is
; 22 + 1 + 76 + 1 = 100 bytes; 128 is the next power of two and leaves
; the bound obviously true rather than exactly true.
#WPA2_PRF_MAX     = 128

; States.
#WPA2SUP_IDLE     = 0
#WPA2SUP_WAIT_M1  = 1
#WPA2SUP_WAIT_M3  = 2
#WPA2SUP_DONE     = 3
#WPA2SUP_FAILED   = 4
; SESSION - the four-way is done and the keys are installed, but the key
; material is DELIBERATELY KEPT so a mid-session rekey the access point
; starts on its own can be answered. Entered by Wpa2SupSessionArm instead
; of Wpa2SupWipe. See the MID-SESSION REKEY section for why this is the
; cure for the TX-only death and not a leak.
#WPA2SUP_SESSION  = 5

; What Wpa2SupHandle returns.
#WPA2SUP_IGNORED  = 0         ; not an EAPOL-Key frame for us
#WPA2SUP_SENT_M2  = 1         ; message 2 is in the reply buffer
#WPA2SUP_SENT_M4  = 2         ; message 4 is in the reply buffer AND the
                              ; keys are ready - install them BEFORE
                              ; sending, see the note on Wpa2SupTk
#WPA2SUP_SENT_G2  = 3         ; GROUP message 2 is in the reply buffer AND
                              ; a fresh GTK is ready (Wpa2SupGtk/GtkLen/
                              ; GtkIndex/GtkRsc) - install it and send.
                              ; The PAIRWISE key is UNCHANGED by a group
                              ; rekey and must not be reinstalled.
#WPA2SUP_E_SHORT     = -1
#WPA2SUP_E_NOTEAPOL  = -2
#WPA2SUP_E_DESC      = -3
#WPA2SUP_E_KDV       = -4
#WPA2SUP_E_MIC       = -5
#WPA2SUP_E_UNWRAP    = -6
#WPA2SUP_E_NOGTK     = -7
#WPA2SUP_E_NONONCE   = -8
#WPA2SUP_E_STATE     = -9
#WPA2SUP_E_REPLAY    = -10
#WPA2SUP_E_BIG       = -11
#WPA2SUP_E_NOTREADY  = -12

; ----------------------------------------------------------------------
;  STATE. Flat Global arrays, house style. Everything with a `sec`
;  prefix is key material and Wpa2SupWipe clears all of it.
; ----------------------------------------------------------------------
Global Dim secWpaPmk.a[#WPA2_PMK_LEN]
Global Dim secWpaPtk.a[#WPA2_PTK_LEN]
Global Dim secWpaGtk.a[#WPA2_GTK_MAX]
Global Dim secWpaPrfIn.a[#WPA2_PRF_MAX]
Global Dim secWpaPrfOut.a[20]
Global Dim secWpaKd.a[#WPA2_KD_MAX]
Global Dim secWpaMic.a[20]
; THE SAVE AND THE ANSWER MUST NOT SHARE A BUFFER. See wpa_Mic.
Global Dim secWpaSave.a[16]
Global Dim secWpaCalc.a[20]

Global Dim wpaSnonce.a[#WPA2_NONCE_LEN]
Global Dim wpaAnonce.a[#WPA2_NONCE_LEN]
Global Dim wpaOurMac.a[6]
Global Dim wpaApMac.a[6]
Global Dim wpaRsnIe.a[#WPA2_IE_MAX]
Global Dim wpaReplay.a[8]
Global Dim wpaGtkRsc.a[#WPA2_RSC_LEN]
Global Dim wpaTx.a[#WPA2_TX_MAX]

Global wpaState.i    = #WPA2SUP_IDLE
Global wpaRsnIeLen.i = 0
Global wpaHaveNonce.i = 0
Global wpaTxLen.i    = 0
Global wpaGtkLen.i   = 0
Global wpaGtkIndex.i = 0
Global wpaGtkTx.i    = 0
Global wpaKdv.i      = 0
Global wpaEapolVer.i = 2
Global wpaM1Seen.i   = 0
Global wpaM3Seen.i   = 0
Global wpaLastErr.i  = 0
Global wpaGrpSeen.i  = 0      ; group-key rekeys serviced this session
Global wpaPtkRe.i    = 0      ; mid-session PTK rekeys serviced this session

; ----------------------------------------------------------------------
;  Little helpers. Big-endian, because everything in 802.1X is.
; ----------------------------------------------------------------------
Procedure.i wpa_Be16(p.i)
  ProcedureReturn (PeekA(p) << 8) | PeekA(p + 1)
EndProcedure

Procedure wpa_PutBe16(p.i, v.i)
  PokeB(p, (v >> 8) & $FF)
  PokeB(p + 1, v & $FF)
EndProcedure

; memcmp over n bytes: -1, 0 or 1. Used for the Min/Max ordering in the
; PTK derivation and for the replay counter, and it is UNSIGNED because
; PeekA returns 0..255 and a MAC address byte above $7F is common.
Procedure.i wpa_Cmp(a.i, b.i, n.i)
  Define i.i
  For i = 0 To n - 1
    If PeekA(a + i) < PeekA(b + i)
      ProcedureReturn -1
    EndIf
    If PeekA(a + i) > PeekA(b + i)
      ProcedureReturn 1
    EndIf
  Next
  ProcedureReturn 0
EndProcedure

Procedure wpa_Copy(dst.i, src.i, n.i)
  Define i.i
  For i = 0 To n - 1
    PokeB(dst + i, PeekA(src + i))
  Next
EndProcedure

Procedure wpa_Zero(dst.i, n.i)
  Define i.i
  For i = 0 To n - 1
    PokeB(dst + i, 0)
  Next
EndProcedure

; ----------------------------------------------------------------------
;  Wpa2Prf(key, keylen, label, labellen, data, datalen, out, outlen)
;
;  IEEE 802.11 clause 12.7.1.2. The construction is
;
;      for i = 0, 1, 2, ...
;          R = R || HMAC-SHA1(K, label || 0x00 || data || i)
;      take the leftmost outlen bytes of R
;
;  THE COUNTER IS ONE BYTE AND THE NUL IS NOT PART OF THE LABEL. Both
;  are the classic places to get this wrong: the separator is a single
;  zero octet after the label text, and the label is not
;  NUL-terminated in its own right. Get either wrong and the PTK is
;  wrong, message 2's MIC is rejected, and the access point simply
;  stops answering - which is indistinguishable from a radio problem.
;
;  Returns outlen, or 0 if the message would not fit.
; ----------------------------------------------------------------------
Procedure.i Wpa2Prf(key.i, keylen.i, label.i, labellen.i, data.i, datalen.i, out.i, outlen.i)
  Define n.i
  Define i.i
  Define off.i
  Define want.i
  Define k.i

  n = labellen + 1 + datalen + 1
  If n > #WPA2_PRF_MAX
    ProcedureReturn 0
  EndIf
  If outlen < 1
    ProcedureReturn 0
  EndIf

  For i = 0 To labellen - 1
    secWpaPrfIn[i] = PeekA(label + i)
  Next
  secWpaPrfIn[labellen] = 0
  For i = 0 To datalen - 1
    secWpaPrfIn[labellen + 1 + i] = PeekA(data + i)
  Next

  ; One key schedule for the whole derivation. HmacSha1Of would rebuild
  ; the pad states on every block; three blocks is not a loop worth
  ; being sloppy in, and pbkdf2.pi4 sets the precedent.
  HmacSha1Key(key, keylen)

  off = 0
  i = 0
  While off < outlen
    secWpaPrfIn[n - 1] = i & $FF
    HmacSha1Begin()
    HmacSha1Update(@secWpaPrfIn[0], n)
    HmacSha1End(@secWpaPrfOut[0], 20)
    want = outlen - off
    If want > 20
      want = 20
    EndIf
    k = 0
    While k < want
      PokeB(out + off + k, secWpaPrfOut[k] & 255)
      k = k + 1
    Wend
    off = off + want
    i = i + 1
  Wend
  ProcedureReturn outlen
EndProcedure

; ----------------------------------------------------------------------
;  wpa_DerivePtk - PTK = PRF-384 over the two MACs and the two nonces,
;  each pair in Min-then-Max order.
;
;  THE ORDERING IS THE WHOLE POINT AND IT IS WHY BOTH ENDS AGREE. The
;  authenticator and the supplicant each know both MACs and both
;  nonces, but neither knows which of them the other calls "mine", so
;  the standard sorts each pair bytewise. Sorting the MACs but not the
;  nonces, or comparing them as signed bytes, gives a PTK that is
;  perfectly self-consistent and rejected by the far end.
; ----------------------------------------------------------------------
Procedure.i wpa_DerivePtk()
  Define b.i
  Define off.i

  ; The 76-byte B: Min(AA,SPA) || Max(AA,SPA) || Min(nonces) || Max.
  ; Assembled in the key-data scratch, which is idle at this point in
  ; the exchange and is wiped with everything else.
  b = @secWpaKd[0]
  off = 0
  If wpa_Cmp(@wpaApMac[0], @wpaOurMac[0], 6) < 0
    wpa_Copy(b + 0, @wpaApMac[0], 6)
    wpa_Copy(b + 6, @wpaOurMac[0], 6)
  Else
    wpa_Copy(b + 0, @wpaOurMac[0], 6)
    wpa_Copy(b + 6, @wpaApMac[0], 6)
  EndIf
  off = 12
  If wpa_Cmp(@wpaAnonce[0], @wpaSnonce[0], #WPA2_NONCE_LEN) < 0
    wpa_Copy(b + off, @wpaAnonce[0], #WPA2_NONCE_LEN)
    wpa_Copy(b + off + #WPA2_NONCE_LEN, @wpaSnonce[0], #WPA2_NONCE_LEN)
  Else
    wpa_Copy(b + off, @wpaSnonce[0], #WPA2_NONCE_LEN)
    wpa_Copy(b + off + #WPA2_NONCE_LEN, @wpaAnonce[0], #WPA2_NONCE_LEN)
  EndIf

  If Wpa2Prf(@secWpaPmk[0], #WPA2_PMK_LEN, ?wpaPkeLabel, 22, b, 76, @secWpaPtk[0], #WPA2_PTK_LEN) <> #WPA2_PTK_LEN
    ProcedureReturn 0
  EndIf
  wpa_Zero(b, 76)
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  wpa_Mic - HMAC-SHA1(KCK, the whole 802.1X PDU with the MIC field
;  zeroed), truncated to 16 bytes, written to *dst.
;
;  THE PDU, NOT THE ETHERNET FRAME. It starts at the 802.1X version
;  byte - frame offset 14 - and runs to the end of the key data. The
;  fourteen bytes of Ethernet header are NOT covered, which is correct
;  and is also why a supplicant that MICs from offset 0 fails with no
;  clue: the arithmetic is right, the input is not.
;
;  THE MIC FIELD MUST READ AS SIXTEEN ZEROS while it is computed, so
;  this saves the sixteen bytes, zeroes them, computes, and puts them
;  back - the caller's frame is unchanged on return.
;
;  ======================================================================
;  THREE BUFFERS, AND THE FIRST VERSION USED ONE. IT PASSED NOTHING AND
;  LOOKED LIKE IT PASSED EVERYTHING.
;  ======================================================================
;  The first version saved the frame's MIC into secWpaMic, computed the
;  new one into `dst`, and restored from secWpaMic. Both callers pass a
;  dst that ALIASES one of those:
;
;    BUILDING A REPLY passes dst = frame + #WPA2_K_MIC, so the restore
;    wrote the saved zeros straight back over the MIC that had just
;    been computed. Every message 2 and message 4 went out with
;    SIXTEEN ZERO BYTES where the MIC belongs.
;
;    CHECKING A MESSAGE passes dst = secWpaMic, which is the SAVE
;    BUFFER. The computed MIC overwrote the saved one, the restore then
;    wrote the COMPUTED value into the frame, and the caller compared
;    the computed value against itself. THE VERIFICATION ALWAYS PASSED
;    - including on a frame with a deliberately flipped MIC bit, which
;    is how tools/a64/a64_wpa2sup_check.py found it.
;
;  That second half is the one that matters. A supplicant whose MIC
;  check cannot fail will install keys handed to it by anything on the
;  air that knows the SSID, and the link comes up perfectly every time.
;  Neither half is visible on a bench: the first shows as "the access
;  point never sent message 3" and points at the PTK derivation.
;
;  So: SAVE into secWpaSave, COMPUTE into secWpaCalc, RESTORE the
;  frame, and only then copy the answer to dst. Three buffers, no
;  aliasing possible, and the order is load-bearing.
; ----------------------------------------------------------------------
Procedure wpa_Mic(frame.i, keyDataLen.i, dst.i)
  Define pduLen.i
  Define i.i

  pduLen = #WPA2_1X_HDR + #WPA2_K_BODY + keyDataLen

  For i = 0 To #WPA2_MIC_LEN - 1
    secWpaSave[i] = PeekA(frame + #WPA2_K_MIC + i)
    PokeB(frame + #WPA2_K_MIC + i, 0)
  Next

  HmacSha1Key(@secWpaPtk[0] + #WPA2_KCK_OFF, #WPA2_KCK_LEN)
  HmacSha1Begin()
  HmacSha1Update(frame + #WPA2_1X_VER, pduLen)
  HmacSha1End(@secWpaCalc[0], #WPA2_MIC_LEN)

  For i = 0 To #WPA2_MIC_LEN - 1
    PokeB(frame + #WPA2_K_MIC + i, secWpaSave[i] & 255)
  Next
  For i = 0 To #WPA2_MIC_LEN - 1
    PokeB(dst + i, secWpaCalc[i] & 255)
  Next
EndProcedure

; ----------------------------------------------------------------------
;  wpa_BuildReply - the common skeleton of messages 2 and 4.
;
;  Everything is zero unless it is set here: IV, RSC, key id and (for
;  message 4) the nonce are all zeros on the wire, and the reply buffer
;  is cleared rather than reused, so a stale ANonce from the previous
;  handshake cannot leak into a field nobody sets.
;
;  KEY LENGTH IS ZERO IN BOTH REPLIES. That is the RSN rule -
;  wpa_supplicant writes 0 for WPA_PROTO_RSN in both
;  wpa_supplicant_send_2_of_4 and _4_of_4 - and it is NOT the 16 that
;  message 1 and message 3 carry. Echoing the AP's 16 here is a
;  one-character mistake that some access points tolerate and others
;  reject, which is the worst kind.
; ----------------------------------------------------------------------
Procedure wpa_BuildReply(keyInfo.i, keyDataLen.i)
  Define total.i
  Define i.i

  total = #WPA2_FRAME_MIN + keyDataLen

  For i = 0 To total - 1
    wpaTx[i] = 0
  Next

  wpa_Copy(@wpaTx[0] + #WPA2_ETH_DA, @wpaApMac[0], 6)
  wpa_Copy(@wpaTx[0] + #WPA2_ETH_SA, @wpaOurMac[0], 6)
  wpaTx[#WPA2_ETH_TYPE]     = $88
  wpaTx[#WPA2_ETH_TYPE + 1] = $8E

  wpaTx[#WPA2_1X_VER]  = wpaEapolVer & $FF
  wpaTx[#WPA2_1X_TYPE] = #WPA2_1X_KEY
  wpa_PutBe16(@wpaTx[0] + #WPA2_1X_LEN, #WPA2_K_BODY + keyDataLen)

  wpaTx[#WPA2_K_DESC] = #WPA2_DESC_RSN
  wpa_PutBe16(@wpaTx[0] + #WPA2_K_INFO, keyInfo)
  wpa_PutBe16(@wpaTx[0] + #WPA2_K_LEN, 0)
  wpa_Copy(@wpaTx[0] + #WPA2_K_REPLAY, @wpaReplay[0], 8)
  wpa_PutBe16(@wpaTx[0] + #WPA2_K_DATALEN, keyDataLen)

  wpaTxLen = total
EndProcedure

; ======================================================================
;  THE PUBLIC SURFACE
; ======================================================================

; ----------------------------------------------------------------------
;  Wpa2SupBegin - arm the supplicant for one association.
;
;  *pmk32 is the 32-byte PMK, *ourMac and *apMac six bytes each, and
;  *rsnIe is the COMPLETE element - id byte, length byte and body - as
;  it was given to the firmware's `wpaie` iovar. Those exact bytes go
;  into message 2 and the authenticator compares them with what the
;  association request carried.
;
;  IT DOES NOT PICK THE SNonce. Wpa2SupSetSnonce does, from the
;  caller's entropy source, because a library that reached for a
;  hardware RNG would be a library that cannot run in a test harness -
;  and a supplicant whose nonce is not random is a supplicant whose
;  session key can be replayed.
; ----------------------------------------------------------------------
Procedure.i Wpa2SupBegin(*pmk32, *ourMac, *apMac, *rsnIe, rsnIeLen.i)
  If rsnIeLen < 2 Or rsnIeLen > #WPA2_IE_MAX
    wpaState = #WPA2SUP_FAILED
    wpaLastErr = #WPA2SUP_E_BIG
    ProcedureReturn 0
  EndIf
  wpa_Copy(@secWpaPmk[0], *pmk32, #WPA2_PMK_LEN)
  wpa_Copy(@wpaOurMac[0], *ourMac, 6)
  wpa_Copy(@wpaApMac[0], *apMac, 6)
  wpa_Copy(@wpaRsnIe[0], *rsnIe, rsnIeLen)
  wpaRsnIeLen = rsnIeLen
  wpa_Zero(@wpaAnonce[0], #WPA2_NONCE_LEN)
  wpa_Zero(@wpaReplay[0], 8)
  wpa_Zero(@wpaGtkRsc[0], #WPA2_RSC_LEN)
  wpaGtkLen = 0
  wpaGtkIndex = 0
  wpaGtkTx = 0
  wpaTxLen = 0
  wpaM1Seen = 0
  wpaM3Seen = 0
  wpaKdv = 0
  wpaEapolVer = 2
  wpaLastErr = 0
  wpaState = #WPA2SUP_WAIT_M1
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  Wpa2SupSetSnonce - 32 bytes of the caller's randomness.
;
;  MUST BE CALLED BEFORE MESSAGE 1 ARRIVES, and Wpa2SupHandle refuses
;  with #WPA2SUP_E_NONONCE rather than deriving a PTK from a buffer of
;  zeros. A zero SNonce would "work" against most access points and
;  would make every session key on this board derivable by anyone who
;  captured the handshake, which is exactly the sort of failure that
;  never announces itself.
; ----------------------------------------------------------------------
Procedure Wpa2SupSetSnonce(*n32)
  wpa_Copy(@wpaSnonce[0], *n32, #WPA2_NONCE_LEN)
  wpaHaveNonce = 1
EndProcedure

; ----------------------------------------------------------------------
;  Wpa2SupHandle - feed one received 802.3 frame.
;
;  Returns #WPA2SUP_IGNORED for anything that is not an EAPOL-Key frame
;  addressed to us - so a caller can hand it every frame off the wire
;  without pre-filtering - #WPA2SUP_SENT_M2 or #WPA2SUP_SENT_M4 when a
;  reply is waiting in Wpa2SupTxPtr(), or a negative code.
;
;  THE FRAME IS WRITTEN TO. wpa_Mic zeroes the MIC field to compute
;  over it and puts it back, so the buffer is unchanged on return - but
;  it is not const, and a caller must not be holding a second pointer
;  into it expecting immutability.
; ----------------------------------------------------------------------
Procedure.i Wpa2SupHandle(*frame, len.i)
  Define info.i
  Define kdl.i
  Define kdv.i
  Define plain.i
  Define i.i
  Define p.i
  Define t.i
  Define l.i
  Define keyInfo.i

  If len < #WPA2_ETH_HDR
    ProcedureReturn #WPA2SUP_IGNORED
  EndIf
  If PeekA(*frame + #WPA2_ETH_TYPE) <> $88 Or PeekA(*frame + #WPA2_ETH_TYPE + 1) <> $8E
    ProcedureReturn #WPA2SUP_IGNORED
  EndIf
  If PeekA(*frame + #WPA2_1X_TYPE) <> #WPA2_1X_KEY
    ProcedureReturn #WPA2SUP_IGNORED
  EndIf
  If len < #WPA2_FRAME_MIN
    wpaLastErr = #WPA2SUP_E_SHORT
    ProcedureReturn #WPA2SUP_E_SHORT
  EndIf
  If PeekA(*frame + #WPA2_K_DESC) <> #WPA2_DESC_RSN
    wpaLastErr = #WPA2SUP_E_DESC
    ProcedureReturn #WPA2SUP_E_DESC
  EndIf

  info = wpa_Be16(*frame + #WPA2_K_INFO)
  kdv  = info & #WPA2_KI_VERSION
  If kdv <> #WPA2_KDV_SHA1
    wpaLastErr = #WPA2SUP_E_KDV
    ProcedureReturn #WPA2SUP_E_KDV
  EndIf
  wpaKdv = kdv

  kdl = wpa_Be16(*frame + #WPA2_K_DATALEN)
  If (#WPA2_FRAME_MIN + kdl) > len
    wpaLastErr = #WPA2SUP_E_SHORT
    ProcedureReturn #WPA2SUP_E_SHORT
  EndIf
  If kdl > #WPA2_KD_MAX
    wpaLastErr = #WPA2SUP_E_BIG
    ProcedureReturn #WPA2SUP_E_BIG
  EndIf

  ; Follow the far end down to 802.1X version 1 if that is what it
  ; speaks. wpa_supplicant does the same; an RSN authenticator that
  ; sends version 1 has been seen to reject a version 2 reply.
  If PeekA(*frame + #WPA2_1X_VER) < wpaEapolVer
    wpaEapolVer = PeekA(*frame + #WPA2_1X_VER)
  EndIf

  ; ------------------------------------------------------------------
  ;  MESSAGE 1: pairwise, Ack, no MIC.
  ; ------------------------------------------------------------------
  If (info & #WPA2_KI_MIC) = 0
    If (info & #WPA2_KI_PAIRWISE) = 0 Or (info & #WPA2_KI_ACK) = 0
      wpaLastErr = #WPA2SUP_E_STATE
      ProcedureReturn #WPA2SUP_E_STATE
    EndIf
    If wpaState <> #WPA2SUP_WAIT_M1 And wpaState <> #WPA2SUP_WAIT_M3
      wpaLastErr = #WPA2SUP_E_STATE
      ProcedureReturn #WPA2SUP_E_STATE
    EndIf
    If wpaHaveNonce = 0
      wpaState = #WPA2SUP_FAILED
      wpaLastErr = #WPA2SUP_E_NONONCE
      ProcedureReturn #WPA2SUP_E_NONONCE
    EndIf

    wpa_Copy(@wpaAnonce[0], *frame + #WPA2_K_NONCE, #WPA2_NONCE_LEN)
    wpa_Copy(@wpaReplay[0], *frame + #WPA2_K_REPLAY, 8)
    ; The authenticator's address is the frame's source, not whatever
    ; the caller thought the BSSID was. On a network where the two
    ; differ the PTK must be derived from what actually spoke to us.
    wpa_Copy(@wpaApMac[0], *frame + #WPA2_ETH_SA, 6)

    If wpa_DerivePtk() = 0
      wpaState = #WPA2SUP_FAILED
      wpaLastErr = #WPA2SUP_E_BIG
      ProcedureReturn #WPA2SUP_E_BIG
    EndIf

    keyInfo = #WPA2_KDV_SHA1 | #WPA2_KI_PAIRWISE | #WPA2_KI_MIC
    wpa_BuildReply(keyInfo, wpaRsnIeLen)
    wpa_Copy(@wpaTx[0] + #WPA2_K_NONCE, @wpaSnonce[0], #WPA2_NONCE_LEN)
    wpa_Copy(@wpaTx[0] + #WPA2_K_DATA, @wpaRsnIe[0], wpaRsnIeLen)
    wpa_Mic(@wpaTx[0], wpaRsnIeLen, @wpaTx[0] + #WPA2_K_MIC)

    wpaM1Seen = wpaM1Seen + 1
    wpaState = #WPA2SUP_WAIT_M3
    ProcedureReturn #WPA2SUP_SENT_M2
  EndIf

  ; ------------------------------------------------------------------
  ;  MESSAGE 3: pairwise, Ack, MIC, Secure, Encrypted key data.
  ; ------------------------------------------------------------------
  If wpaState <> #WPA2SUP_WAIT_M3 And wpaState <> #WPA2SUP_DONE
    wpaLastErr = #WPA2SUP_E_STATE
    ProcedureReturn #WPA2SUP_E_STATE
  EndIf
  If (info & #WPA2_KI_ACK) = 0
    ; A MIC'd frame with no Ack is an error report or the second half
    ; of somebody else's exchange. Named, not swallowed.
    wpaLastErr = #WPA2SUP_E_STATE
    ProcedureReturn #WPA2SUP_E_STATE
  EndIf
  If (info & #WPA2_KI_PAIRWISE) = 0
    ; A GROUP KEY HANDSHAKE, and it is refused ON PURPOSE rather than
    ; fallen into. Without this test the code below would run: the MIC
    ; verifies (it is under the same KCK), the key data unwraps, the
    ; GTK KDE parses, and a perfectly plausible-looking message 4 goes
    ; out with the PAIRWISE bit set - which is not what a group
    ; handshake's reply looks like, so the access point rejects it and
    ; eventually deauthenticates. Half-handling a rekey is worse than
    ; refusing it, because the refusal is printed and the half-handling
    ; is a link that drops minutes later for no stated reason.
    wpaLastErr = #WPA2SUP_E_STATE
    ProcedureReturn #WPA2SUP_E_STATE
  EndIf
  If wpa_Cmp(*frame + #WPA2_K_REPLAY, @wpaReplay[0], 8) <= 0
    wpaLastErr = #WPA2SUP_E_REPLAY
    ProcedureReturn #WPA2SUP_E_REPLAY
  EndIf

  ; THE MIC IS CHECKED BEFORE ANYTHING IN THE FRAME IS BELIEVED. It is
  ; what proves the far end holds the PMK, and everything below - a
  ; length, an offset, a key - comes out of bytes an attacker could
  ; otherwise choose.
  wpa_Mic(*frame, kdl, @secWpaMic[0])
  For i = 0 To #WPA2_MIC_LEN - 1
    If (secWpaMic[i] & 255) <> PeekA(*frame + #WPA2_K_MIC + i)
      wpaState = #WPA2SUP_FAILED
      wpaLastErr = #WPA2SUP_E_MIC
      ProcedureReturn #WPA2SUP_E_MIC
    EndIf
  Next

  wpa_Copy(@wpaReplay[0], *frame + #WPA2_K_REPLAY, 8)

  ; The key data. Encrypted under the KEK with NIST AES key wrap when
  ; bit 12 is set, which for a WPA2 message 3 it always is.
  plain = 0
  If (info & #WPA2_KI_ENCRYPTED) <> 0
    If kdl < 24 Or (kdl & 7) <> 0
      wpaLastErr = #WPA2SUP_E_UNWRAP
      ProcedureReturn #WPA2SUP_E_UNWRAP
    EndIf
    plain = KwUnwrap(@secWpaPtk[0] + #WPA2_KEK_OFF, #WPA2_KEK_LEN, *frame + #WPA2_K_DATA, kdl, @secWpaKd[0])
    If plain = 0
      wpaState = #WPA2SUP_FAILED
      wpaLastErr = #WPA2SUP_E_UNWRAP
      ProcedureReturn #WPA2SUP_E_UNWRAP
    EndIf
  Else
    wpa_Copy(@secWpaKd[0], *frame + #WPA2_K_DATA, kdl)
    plain = kdl
  EndIf

  ; Walk the key data. It is a run of 802.11 elements and KDEs: id,
  ; length, body. A KDE is id $DD with the OUI 00-0F-AC, and data type
  ; 1 inside it is the GTK - two bytes of key id and flags, then the
  ; key itself.
  wpaGtkLen = 0
  p = @secWpaKd[0]
  i = 0
  While i + 2 <= plain
    t = PeekA(p + i)
    l = PeekA(p + i + 1)
    If t = 0 Or (i + 2 + l) > plain
      Break                       ; padding, or a length that lies
    EndIf
    If t = $DD And l >= 6
      If PeekA(p + i + 2) = $00 And PeekA(p + i + 3) = $0F And PeekA(p + i + 4) = $AC And PeekA(p + i + 5) = $01
        wpaGtkLen = l - 6
        If wpaGtkLen > #WPA2_GTK_MAX
          wpaGtkLen = 0
          wpaLastErr = #WPA2SUP_E_BIG
          ProcedureReturn #WPA2SUP_E_BIG
        EndIf
        wpaGtkIndex = PeekA(p + i + 6) & 3
        wpaGtkTx    = (PeekA(p + i + 6) >> 2) & 1
        wpa_Copy(@secWpaGtk[0], p + i + 8, wpaGtkLen)
      EndIf
    EndIf
    i = i + 2 + l
  Wend

  If wpaGtkLen = 0
    wpaState = #WPA2SUP_FAILED
    wpaLastErr = #WPA2SUP_E_NOGTK
    ProcedureReturn #WPA2SUP_E_NOGTK
  EndIf

  ; The group key's receive sequence counter travels in message 3's
  ; Key RSC field, six meaningful bytes of eight. Without it the
  ; firmware treats the AP's first broadcast as a replay and drops it,
  ; silently, for ever.
  wpa_Copy(@wpaGtkRsc[0], *frame + #WPA2_K_RSC, #WPA2_RSC_LEN)

  keyInfo = #WPA2_KDV_SHA1 | #WPA2_KI_PAIRWISE | #WPA2_KI_MIC | #WPA2_KI_SECURE
  wpa_BuildReply(keyInfo, 0)
  wpa_Mic(@wpaTx[0], 0, @wpaTx[0] + #WPA2_K_MIC)

  ; The unwrapped key data held the GTK in the clear. It is copied out;
  ; the scratch does not keep a second copy.
  wpa_Zero(@secWpaKd[0], #WPA2_KD_MAX)

  wpaM3Seen = wpaM3Seen + 1
  wpaState = #WPA2SUP_DONE
  ProcedureReturn #WPA2SUP_SENT_M4
EndProcedure

; ======================================================================
;  MID-SESSION REKEY - the cure for the Pi 4 Anvil TX-only death.
; ======================================================================
;  WHAT THE DEATH WAS. Both natural deaths on silicon struck on the
;  hour, TX-only: the board kept HEARING traffic while nothing it
;  transmitted arrived, and Cyw43ReadBssid kept answering "associated"
;  the whole time. That is the exact signature of an access point that
;  has rotated its group key (a ~3600 s hostapd timer) and stopped
;  treating this station as keyed for it - no deauthentication, so the
;  firmware never learns, and the round-trip heal was the only thing
;  that noticed.
;
;  WHY THE HOST HAS TO ANSWER IT. This board's radio firmware
;  (brcmfmac43455-sdio.bin) carries NO in-dongle supplicant - the build
;  string is `extsae`, not `idsup`, and the `sup_wpa` iovar it needs is
;  refused -23 BCME_UNSUPPORTED (measured 2026-08-27). So the firmware
;  delivers a mid-session rekey EAPOL frame UP to the host exactly like
;  the four-way at join, and if nobody answers it the rekey never
;  completes. The reference driver (v6.12_brcmfmac_cfg80211.c) confirms
;  the shape: its GTK-rekey OFFLOAD (brcmf_cfg80211_set_rekey_data, the
;  `gtk_key_info` iovar) is gated `#ifdef CONFIG_PM` behind
;  BRCMF_FEAT_WOWL_GTK - it exists only to answer rekeys WHILE THE HOST
;  IS SUSPENDED. While awake, Linux answers them in wpa_supplicant, in
;  the host. Anvil is always awake, so it must do the same.
;
;  THE KEYS MUST STILL BE HERE. The join used to Wpa2SupWipe the moment
;  the keys were installed. A supplicant that must answer a rekey cannot
;  throw away the KCK (to verify and MIC), the KEK (to unwrap a new GTK)
;  or the PMK (to re-derive a PTK), so the caller now calls
;  Wpa2SupSessionArm instead and the material lives for the association -
;  which is exactly what wpa_supplicant keeps in RAM, for this reason.
;
;  Two rekeys an access point starts on its own are serviced:
;    * the GROUP key handshake (2 messages). Wpa2SupHandle REFUSES this
;      during a join on purpose; here it is the whole point. Verify the
;      MIC under the KCK, unwrap the GTK under the KEK, and send group
;      message 2 with the PAIRWISE BIT CLEAR. The pairwise key is not
;      touched.
;    * a PTK rekey (a fresh four-way, pairwise message 1 mid-session).
;      Delegated to Wpa2SupHandle by re-arming the state, so the exact
;      same, gate-tested four-way runs again.
; ----------------------------------------------------------------------

; Arm the session hold. Called by the join once both keys are installed,
; IN PLACE OF Wpa2SupWipe, so the key material survives to answer a rekey.
Procedure Wpa2SupSessionArm()
  wpaState = #WPA2SUP_SESSION
EndProcedure

Procedure.i Wpa2SupInSession()
  If wpaState = #WPA2SUP_SESSION
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

; 1 if this is an EAPOL-Key PAIRWISE message 1 (Ack, no MIC): the start
; of a PTK rekey, for which the caller should install a FRESH SNonce with
; Wpa2SupSetSnonce before handing the frame to Wpa2SupHandleSession.
; Reusing a stale SNonce with the AP's fresh ANonce still derives a
; unique PTK, but a fresh one matches wpa_supplicant and costs nothing.
Procedure.i Wpa2SupPeekPtkM1(*frame, len.i)
  Define info.i
  If len < #WPA2_FRAME_MIN
    ProcedureReturn 0
  EndIf
  If PeekA(*frame + #WPA2_ETH_TYPE) <> $88 Or PeekA(*frame + #WPA2_ETH_TYPE + 1) <> $8E
    ProcedureReturn 0
  EndIf
  If PeekA(*frame + #WPA2_1X_TYPE) <> #WPA2_1X_KEY
    ProcedureReturn 0
  EndIf
  info = wpa_Be16(*frame + #WPA2_K_INFO)
  If (info & #WPA2_KI_MIC) <> 0
    ProcedureReturn 0
  EndIf
  If (info & #WPA2_KI_PAIRWISE) = 0 Or (info & #WPA2_KI_ACK) = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  Wpa2SupHandleSession - feed one received 802.3 frame DURING a live
;  association. Returns #WPA2SUP_IGNORED for anything that is not an
;  EAPOL-Key frame (so the caller can hand it every frame), #WPA2SUP_
;  SENT_M2 / SENT_M4 for a PTK rekey, #WPA2SUP_SENT_G2 for a serviced
;  group rekey, or a negative code.
;
;  LIKE Wpa2SupHandle, THE FRAME IS WRITTEN TO (wpa_Mic zeroes the MIC
;  field and restores it) and left unchanged on return.
; ----------------------------------------------------------------------
Procedure.i Wpa2SupHandleSession(*frame, len.i)
  Define info.i
  Define kdl.i
  Define kdv.i
  Define plain.i
  Define i.i
  Define p.i
  Define t.i
  Define l.i
  Define keyInfo.i

  ; Classify exactly as Wpa2SupHandle does, so a non-EAPOL frame is
  ; ignored rather than refused.
  If len < #WPA2_ETH_HDR
    ProcedureReturn #WPA2SUP_IGNORED
  EndIf
  If PeekA(*frame + #WPA2_ETH_TYPE) <> $88 Or PeekA(*frame + #WPA2_ETH_TYPE + 1) <> $8E
    ProcedureReturn #WPA2SUP_IGNORED
  EndIf
  If PeekA(*frame + #WPA2_1X_TYPE) <> #WPA2_1X_KEY
    ProcedureReturn #WPA2SUP_IGNORED
  EndIf
  If len < #WPA2_FRAME_MIN
    wpaLastErr = #WPA2SUP_E_SHORT
    ProcedureReturn #WPA2SUP_E_SHORT
  EndIf
  If PeekA(*frame + #WPA2_K_DESC) <> #WPA2_DESC_RSN
    wpaLastErr = #WPA2SUP_E_DESC
    ProcedureReturn #WPA2SUP_E_DESC
  EndIf

  info = wpa_Be16(*frame + #WPA2_K_INFO)
  kdv  = info & #WPA2_KI_VERSION
  If kdv <> #WPA2_KDV_SHA1
    wpaLastErr = #WPA2SUP_E_KDV
    ProcedureReturn #WPA2SUP_E_KDV
  EndIf
  wpaKdv = kdv

  kdl = wpa_Be16(*frame + #WPA2_K_DATALEN)
  If (#WPA2_FRAME_MIN + kdl) > len
    wpaLastErr = #WPA2SUP_E_SHORT
    ProcedureReturn #WPA2SUP_E_SHORT
  EndIf
  If kdl > #WPA2_KD_MAX
    wpaLastErr = #WPA2SUP_E_BIG
    ProcedureReturn #WPA2SUP_E_BIG
  EndIf

  If PeekA(*frame + #WPA2_1X_VER) < wpaEapolVer
    wpaEapolVer = PeekA(*frame + #WPA2_1X_VER)
  EndIf

  ; ------------------------------------------------------------------
  ;  A PTK REKEY: a fresh pairwise message 1 (Ack, NO MIC). Re-arm and
  ;  hand it to the SAME four-way Wpa2SupHandle runs at join - that code
  ;  is the one the offline gate exercises, so a rekey takes the tested
  ;  path rather than a second copy of it.
  ; ------------------------------------------------------------------
  If (info & #WPA2_KI_MIC) = 0
    If (info & #WPA2_KI_PAIRWISE) = 0 Or (info & #WPA2_KI_ACK) = 0
      wpaLastErr = #WPA2SUP_E_STATE
      ProcedureReturn #WPA2SUP_E_STATE
    EndIf
    wpaState = #WPA2SUP_WAIT_M1
    i = Wpa2SupHandle(*frame, len)
    If i = #WPA2SUP_SENT_M2
      wpaPtkRe = wpaPtkRe + 1
    EndIf
    ProcedureReturn i
  EndIf

  ; From here the MIC bit is set. A MIC'd frame with no Ack is an error
  ; report or the second half of somebody else's exchange.
  If (info & #WPA2_KI_ACK) = 0
    wpaLastErr = #WPA2SUP_E_STATE
    ProcedureReturn #WPA2SUP_E_STATE
  EndIf

  ; ------------------------------------------------------------------
  ;  A PTK REKEY, continued: pairwise message 3 (Ack + MIC). Wpa2Sup
  ;  Handle accepts message 3 in WAIT_M3 (which the message 1 above set)
  ;  or DONE, verifies the MIC, unwraps, and stages message 4.
  ; ------------------------------------------------------------------
  If (info & #WPA2_KI_PAIRWISE) <> 0
    ProcedureReturn Wpa2SupHandle(*frame, len)
  EndIf

  ; ------------------------------------------------------------------
  ;  THE GROUP KEY HANDSHAKE: group message 1 (Ack + MIC, PAIRWISE
  ;  CLEAR). This is the frame Wpa2SupHandle names and refuses; here it
  ;  is serviced. IEEE 802.11 12.7.7.
  ; ------------------------------------------------------------------
  If wpa_Cmp(*frame + #WPA2_K_REPLAY, @wpaReplay[0], 8) <= 0
    wpaLastErr = #WPA2SUP_E_REPLAY
    ProcedureReturn #WPA2SUP_E_REPLAY
  EndIf

  ; THE MIC IS CHECKED BEFORE ANYTHING IN THE FRAME IS BELIEVED - the
  ; same rule as message 3. It is under the same KCK the association
  ; installed, so a group message 1 that verifies proves it came from
  ; the access point we are keyed to.
  wpa_Mic(*frame, kdl, @secWpaMic[0])
  For i = 0 To #WPA2_MIC_LEN - 1
    If (secWpaMic[i] & 255) <> PeekA(*frame + #WPA2_K_MIC + i)
      wpaLastErr = #WPA2SUP_E_MIC
      ProcedureReturn #WPA2SUP_E_MIC
    EndIf
  Next

  wpa_Copy(@wpaReplay[0], *frame + #WPA2_K_REPLAY, 8)

  ; The key data holds the new GTK, wrapped under the KEK with NIST AES
  ; key wrap when bit 12 is set - which for a group message 1 it is.
  plain = 0
  If (info & #WPA2_KI_ENCRYPTED) <> 0
    If kdl < 24 Or (kdl & 7) <> 0
      wpaLastErr = #WPA2SUP_E_UNWRAP
      ProcedureReturn #WPA2SUP_E_UNWRAP
    EndIf
    plain = KwUnwrap(@secWpaPtk[0] + #WPA2_KEK_OFF, #WPA2_KEK_LEN, *frame + #WPA2_K_DATA, kdl, @secWpaKd[0])
    If plain = 0
      wpaLastErr = #WPA2SUP_E_UNWRAP
      ProcedureReturn #WPA2SUP_E_UNWRAP
    EndIf
  Else
    wpa_Copy(@secWpaKd[0], *frame + #WPA2_K_DATA, kdl)
    plain = kdl
  EndIf

  ; Walk the key data for the GTK KDE, exactly as message 3 does.
  wpaGtkLen = 0
  p = @secWpaKd[0]
  i = 0
  While i + 2 <= plain
    t = PeekA(p + i)
    l = PeekA(p + i + 1)
    If t = 0 Or (i + 2 + l) > plain
      Break
    EndIf
    If t = $DD And l >= 6
      If PeekA(p + i + 2) = $00 And PeekA(p + i + 3) = $0F And PeekA(p + i + 4) = $AC And PeekA(p + i + 5) = $01
        wpaGtkLen = l - 6
        If wpaGtkLen > #WPA2_GTK_MAX
          wpaGtkLen = 0
          wpaLastErr = #WPA2SUP_E_BIG
          ProcedureReturn #WPA2SUP_E_BIG
        EndIf
        wpaGtkIndex = PeekA(p + i + 6) & 3
        wpaGtkTx    = (PeekA(p + i + 6) >> 2) & 1
        wpa_Copy(@secWpaGtk[0], p + i + 8, wpaGtkLen)
      EndIf
    EndIf
    i = i + 2 + l
  Wend

  If wpaGtkLen = 0
    wpaLastErr = #WPA2SUP_E_NOGTK
    ProcedureReturn #WPA2SUP_E_NOGTK
  EndIf

  ; The group key's receive sequence counter travels in group message
  ; 1's Key RSC, six meaningful bytes of eight - without it the firmware
  ; drops the AP's first broadcast under the new key as a replay.
  wpa_Copy(@wpaGtkRsc[0], *frame + #WPA2_K_RSC, #WPA2_RSC_LEN)

  ; GROUP MESSAGE 2: group (PAIRWISE CLEAR), MIC, Secure. Key length 0,
  ; no key data, replay counter echoed - wpa_supplicant_send_2_of_2.
  keyInfo = #WPA2_KDV_SHA1 | #WPA2_KI_MIC | #WPA2_KI_SECURE
  wpa_BuildReply(keyInfo, 0)
  wpa_Mic(@wpaTx[0], 0, @wpaTx[0] + #WPA2_K_MIC)

  ; The unwrapped key data held the GTK in the clear. Wipe the scratch.
  wpa_Zero(@secWpaKd[0], #WPA2_KD_MAX)

  wpaGrpSeen = wpaGrpSeen + 1
  ProcedureReturn #WPA2SUP_SENT_G2
EndProcedure

Procedure.i Wpa2SupGrpCount()
  ProcedureReturn wpaGrpSeen
EndProcedure

Procedure.i Wpa2SupPtkReCount()
  ProcedureReturn wpaPtkRe
EndProcedure

; ----------------------------------------------------------------------
;  The reply, and the results.
;
;  Wpa2SupTk RETURNS A POINTER INTO KEY MATERIAL and the caller is
;  expected to install it and then call Wpa2SupWipe.
;
;  ======================================================================
;  SEND MESSAGE 4 FIRST. INSTALL AFTERWARDS. THIS COMMENT SAID THE
;  OPPOSITE AND THE BOARD DISAGREED.
;  ======================================================================
;  It read: "INSTALL BEFORE SENDING MESSAGE 4 ... wpa_supplicant orders
;  it the same way." Both halves were wrong.
;
;  IEEE 802.11-2016 12.7.6.5 has the Authenticator install the PTK ON
;  RECEPTION OF MESSAGE 4 - so it does not hold the pairwise key while
;  message 4 is in the air. A station that plumbs first has its radio
;  encrypt message 4 under a key the far end cannot use, and the frame
;  arrives as noise. wpa_supplicant_process_3_of_4 calls
;  wpa_supplicant_send_4_of_4 and only then wpa_supplicant_install_ptk.
;
;  MEASURED 2026-08-28: installing first produced a verified message 3
;  followed by TWO RETRANSMISSIONS of message 3, which is what an
;  authenticator does when message 4 never arrives valid. The same
;  mistake silently killed the DHCP exchange after it.
;
;  There is no window to worry about in the other direction: the
;  authenticator cannot encrypt to us until it has our message 4, and
;  by then we have installed.
; ----------------------------------------------------------------------
Procedure.i Wpa2SupTxPtr()
  ProcedureReturn @wpaTx[0]
EndProcedure

Procedure.i Wpa2SupTxLen()
  ProcedureReturn wpaTxLen
EndProcedure

Procedure.i Wpa2SupState()
  ProcedureReturn wpaState
EndProcedure

Procedure.i Wpa2SupLastError()
  ProcedureReturn wpaLastErr
EndProcedure

Procedure.i Wpa2SupTk()
  ProcedureReturn @secWpaPtk[0] + #WPA2_TK_OFF
EndProcedure

Procedure.i Wpa2SupTkLen()
  ProcedureReturn #WPA2_TK_LEN
EndProcedure

Procedure.i Wpa2SupGtk()
  ProcedureReturn @secWpaGtk[0]
EndProcedure

Procedure.i Wpa2SupGtkLen()
  ProcedureReturn wpaGtkLen
EndProcedure

Procedure.i Wpa2SupGtkIndex()
  ProcedureReturn wpaGtkIndex
EndProcedure

Procedure.i Wpa2SupGtkRsc()
  ProcedureReturn @wpaGtkRsc[0]
EndProcedure

Procedure.i Wpa2SupApMac()
  ProcedureReturn @wpaApMac[0]
EndProcedure

Procedure.i Wpa2SupM1Count()
  ProcedureReturn wpaM1Seen
EndProcedure

Procedure.i Wpa2SupM3Count()
  ProcedureReturn wpaM3Seen
EndProcedure

; ----------------------------------------------------------------------
;  Wpa2SupErrorText - one English sentence per code, because these are
;  the strings somebody will meet on a bench at midnight.
; ----------------------------------------------------------------------
Procedure.i Wpa2SupErrorText(code.i)
  Select code
    Case 0
      ProcedureReturn "wpa2sup: ok"
    Case #WPA2SUP_E_SHORT
      ProcedureReturn "wpa2sup: the frame is shorter than the fields it claims to carry"
    Case #WPA2SUP_E_NOTEAPOL
      ProcedureReturn "wpa2sup: not an EAPOL-Key frame"
    Case #WPA2SUP_E_DESC
      ProcedureReturn "wpa2sup: descriptor type is not 2 (RSN) - a WPA1 access point, which this file does not implement"
    Case #WPA2SUP_E_KDV
      ProcedureReturn "wpa2sup: key descriptor version is not 2 - version 1 is HMAC-MD5 and RC4 (TKIP) and version 3 is AES-CMAC (PSK-SHA256 or management frame protection); only 2 is implemented"
    Case #WPA2SUP_E_MIC
      ProcedureReturn "wpa2sup: MESSAGE 3's MIC DOES NOT VERIFY. The access point does not hold the same PMK - which means the passphrase is wrong, or the SSID used as the PBKDF2 salt was not the one we associated with"
    Case #WPA2SUP_E_UNWRAP
      ProcedureReturn "wpa2sup: the wrapped key data failed its RFC 3394 integrity check - the KEK is wrong, which after a good MIC would mean the PTK split is wrong"
    Case #WPA2SUP_E_NOGTK
      ProcedureReturn "wpa2sup: message 3 carried no GTK key data element - nothing to install for broadcast traffic"
    Case #WPA2SUP_E_NONONCE
      ProcedureReturn "wpa2sup: no SNonce was supplied - call Wpa2SupSetSnonce with 32 random bytes before the handshake starts"
    Case #WPA2SUP_E_STATE
      ProcedureReturn "wpa2sup: that message does not belong at this point in the exchange"
    Case #WPA2SUP_E_REPLAY
      ProcedureReturn "wpa2sup: the replay counter did not advance - a replayed or duplicated message"
    Case #WPA2SUP_E_BIG
      ProcedureReturn "wpa2sup: a field is larger than this file's buffers"
    Case #WPA2SUP_E_NOTREADY
      ProcedureReturn "wpa2sup: the handshake has not finished"
  EndSelect
  ProcedureReturn "wpa2sup: no such code"
EndProcedure

; ----------------------------------------------------------------------
;  Wpa2SupWipe - every byte of key material in this file.
;
;  CALL IT ONCE THE KEYS ARE IN THE FIRMWARE. The PMK, the PTK and the
;  GTK are all here and all of them are within reach of Anvil's `d`
;  memory dump - which is a command somebody types when something has
;  gone wrong, which is exactly when a handshake has just failed.
;
;  IT DOES NOT WIPE hmacsha1.pi4's CACHED PAD STATES or aes.pi4's key
;  schedule; those are their files' business and both have their own
;  wipes. Saying so is more use than implying a clean-up this cannot
;  deliver: a caller that wants the lot calls HmacSha1 nothing (there
;  is no wipe there), AesWipe and KwWipe as well.
; ----------------------------------------------------------------------
Procedure Wpa2SupWipe()
  Define i.i
  For i = 0 To #WPA2_PMK_LEN - 1
    secWpaPmk[i] = 0
  Next
  For i = 0 To #WPA2_PTK_LEN - 1
    secWpaPtk[i] = 0
  Next
  For i = 0 To #WPA2_GTK_MAX - 1
    secWpaGtk[i] = 0
  Next
  For i = 0 To #WPA2_PRF_MAX - 1
    secWpaPrfIn[i] = 0
  Next
  For i = 0 To 19
    secWpaPrfOut[i] = 0
    secWpaMic[i] = 0
    secWpaCalc[i] = 0
  Next
  For i = 0 To #WPA2_MIC_LEN - 1
    secWpaSave[i] = 0
  Next
  For i = 0 To #WPA2_KD_MAX - 1
    secWpaKd[i] = 0
  Next
  For i = 0 To #WPA2_TX_MAX - 1
    wpaTx[i] = 0
  Next
  wpaTxLen = 0
  wpaGtkLen = 0
  wpaHaveNonce = 0
  For i = 0 To #WPA2_NONCE_LEN - 1
    wpaSnonce[i] = 0
  Next
EndProcedure

DataSection
  ;        P    a    i    r    w    i    s    e         k    e    y         e    x    p    a    n    s    i    o    n
  ;  Twenty-two characters, no terminator. IEEE 802.11 clause 12.7.1.2.
  wpaPkeLabel:
    Data.b  80,  97, 105, 114, 119, 105, 115, 101,  32, 107, 101, 121,  32, 101, 120, 112,  97, 110, 115, 105, 111, 110
EndDataSection

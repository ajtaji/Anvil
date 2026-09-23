; ======================================================================
; sntp_codec.pbi - bounded SNTPv4 request and reply validation.
;
; Dependency: wallclock.pbi is included first for era-aware conversion.
; This is a packet codec, not a socket owner. The service supplies the exact
; received IPv4/UDP tuple and the nonce placed in the request. Plain SNTP is
; not cryptographically authenticated; matching the tuple and originate
; timestamp rejects stray/replayed datagrams but not an on-path attacker.
;
; RFC 5905 sections 6-8 define the 48-byte header, mode/version, timestamps,
; leap indicator and strata. RFC 4330 section 5 supplies the client sanity
; checks; verified erratum 2263 corrects its LI=0 typo. This client accepts
; only solicited unicast server replies (mode 4), never broadcasts.
; ======================================================================

EnableExplicit

#SNTP_PACKET_BYTES = 48
#SNTP_PORT = 123
#SNTP_VERSION = 4
#SNTP_MODE_CLIENT = 3
#SNTP_MODE_SERVER = 4
#SNTP_LEAP_UNSYNC = 3

#SNTP_OK = 1
#SNTP_ERR_ARG = -1
#SNTP_ERR_SHORT = -2
#SNTP_ERR_TUPLE = -3
#SNTP_ERR_VERSION = -4
#SNTP_ERR_MODE = -5
#SNTP_ERR_UNSYNC = -6
#SNTP_ERR_STRATUM = -7
#SNTP_ERR_NONCE = -8
#SNTP_ERR_ZERO_TIME = -9
#SNTP_ERR_ERA = -10

Global sntp_err.i
Global sntp_replyEpoch.i
Global sntp_replyFraction.i
Global sntp_replyStratum.i
Global sntp_nonceSeconds.i
Global sntp_nonceFraction.i

Procedure sntp_Put32(*p, v.i)
  PokeB(*p, (v >> 24) & $FF)
  PokeB(*p + 1, (v >> 16) & $FF)
  PokeB(*p + 2, (v >> 8) & $FF)
  PokeB(*p + 3, v & $FF)
EndProcedure

Procedure.i sntp_Get32(*p)
  ProcedureReturn ((PeekB(*p) & $FF) << 24) | ((PeekB(*p + 1) & $FF) << 16) | ((PeekB(*p + 2) & $FF) << 8) | (PeekB(*p + 3) & $FF)
EndProcedure

Procedure.i SntpBuildRequest(*p, n.i, nonceSeconds.i, nonceFraction.i)
  Define i.i
  sntp_err = 0
  If *p = 0 Or n < #SNTP_PACKET_BYTES
    sntp_err = #SNTP_ERR_ARG
    ProcedureReturn 0
  EndIf
  If nonceSeconds < 0 Or nonceSeconds > 4294967295 Or nonceFraction < 0 Or nonceFraction > 4294967295
    sntp_err = #SNTP_ERR_ARG
    ProcedureReturn 0
  EndIf
  If nonceSeconds = 0 And nonceFraction = 0
    sntp_err = #SNTP_ERR_ARG
    ProcedureReturn 0
  EndIf
  i = 0
  While i < #SNTP_PACKET_BYTES
    PokeB(*p + i, 0)
    i = i + 1
  Wend
  ; LI=0, VN=4, mode=3.
  PokeB(*p, (#SNTP_VERSION << 3) | #SNTP_MODE_CLIENT)
  sntp_Put32(*p + 40, nonceSeconds)
  sntp_Put32(*p + 44, nonceFraction)
  sntp_nonceSeconds = nonceSeconds
  sntp_nonceFraction = nonceFraction
  ProcedureReturn #SNTP_PACKET_BYTES
EndProcedure

; Validate one UDP payload and retain its transmitted time. src/dst ports
; and src IP are arguments so this codec cannot accidentally accept an
; unsolicited payload merely because its 48 bytes look like NTP.
Procedure.i SntpParseReply(*p, n.i, srcIp.i, srcPort.i, dstPort.i, expectedIp.i, expectedLocalPort.i)
  Define first.i
  Define version.i
  Define mode.i
  Define leap.i
  Define stratum.i
  Define orgSeconds.i
  Define orgFraction.i
  Define txSeconds.i
  Define txFraction.i
  Define epoch.i

  sntp_err = 0
  sntp_replyEpoch = #WALLCLOCK_UNKNOWN
  sntp_replyFraction = 0
  sntp_replyStratum = 0

  If *p = 0
    sntp_err = #SNTP_ERR_ARG
    ProcedureReturn 0
  EndIf
  If n < #SNTP_PACKET_BYTES
    sntp_err = #SNTP_ERR_SHORT
    ProcedureReturn 0
  EndIf
  If srcIp <> expectedIp Or srcPort <> #SNTP_PORT Or dstPort <> expectedLocalPort
    sntp_err = #SNTP_ERR_TUPLE
    ProcedureReturn 0
  EndIf

  first = PeekB(*p) & $FF
  leap = (first >> 6) & 3
  version = (first >> 3) & 7
  mode = first & 7
  If version <> #SNTP_VERSION
    sntp_err = #SNTP_ERR_VERSION
    ProcedureReturn 0
  EndIf
  If mode <> #SNTP_MODE_SERVER
    sntp_err = #SNTP_ERR_MODE
    ProcedureReturn 0
  EndIf
  If leap = #SNTP_LEAP_UNSYNC
    sntp_err = #SNTP_ERR_UNSYNC
    ProcedureReturn 0
  EndIf
  stratum = PeekB(*p + 1) & $FF
  If stratum < 1 Or stratum > 15
    sntp_err = #SNTP_ERR_STRATUM
    ProcedureReturn 0
  EndIf

  orgSeconds = sntp_Get32(*p + 24)
  orgFraction = sntp_Get32(*p + 28)
  If orgSeconds <> sntp_nonceSeconds Or orgFraction <> sntp_nonceFraction
    sntp_err = #SNTP_ERR_NONCE
    ProcedureReturn 0
  EndIf

  txSeconds = sntp_Get32(*p + 40)
  txFraction = sntp_Get32(*p + 44)
  If txSeconds = 0 And txFraction = 0
    sntp_err = #SNTP_ERR_ZERO_TIME
    ProcedureReturn 0
  EndIf
  epoch = WallClockNtp32ToEpoch(txSeconds)
  If epoch = #WALLCLOCK_UNKNOWN
    sntp_err = #SNTP_ERR_ERA
    ProcedureReturn 0
  EndIf

  sntp_replyEpoch = epoch
  sntp_replyFraction = txFraction
  sntp_replyStratum = stratum
  ProcedureReturn #SNTP_OK
EndProcedure

Procedure.i SntpReplyEpoch()
  ProcedureReturn sntp_replyEpoch
EndProcedure

Procedure.i SntpReplyFraction()
  ProcedureReturn sntp_replyFraction
EndProcedure

Procedure.i SntpReplyStratum()
  ProcedureReturn sntp_replyStratum
EndProcedure

Procedure.i SntpLastError()
  ProcedureReturn sntp_err
EndProcedure

Procedure.i SntpErrorText()
  Select sntp_err
    Case 0
      ProcedureReturn "SNTP status 0: no packet refusal is recorded."
    Case #SNTP_ERR_ARG
      ProcedureReturn "SNTP error -1: request arguments are invalid; check the packet buffer and nonce."
    Case #SNTP_ERR_SHORT
      ProcedureReturn "SNTP error -2: reply is shorter than 48 bytes; check the server response."
    Case #SNTP_ERR_TUPLE
      ProcedureReturn "SNTP error -3: reply came from the wrong IP address or UDP port; check the selected server."
    Case #SNTP_ERR_VERSION
      ProcedureReturn "SNTP error -4: reply is not version 4; check the selected server."
    Case #SNTP_ERR_MODE
      ProcedureReturn "SNTP error -5: reply is not a unicast server response; check the selected server."
    Case #SNTP_ERR_UNSYNC
      ProcedureReturn "SNTP error -6: server reports an unsynchronized clock; try again or choose another server."
    Case #SNTP_ERR_STRATUM
      ProcedureReturn "SNTP error -7: server stratum is outside 1 through 15; try again or choose another server."
    Case #SNTP_ERR_NONCE
      ProcedureReturn "SNTP error -8: reply does not echo this request nonce; discard the unsolicited packet."
    Case #SNTP_ERR_ZERO_TIME
      ProcedureReturn "SNTP error -9: server transmit timestamp is zero; try again after the server synchronizes."
    Case #SNTP_ERR_ERA
      ProcedureReturn "SNTP error -10: server time is outside 1980 through 2099; check the selected server."
  EndSelect
  ProcedureReturn "SNTP error: an unknown packet refusal occurred; inspect the last error code."
EndProcedure

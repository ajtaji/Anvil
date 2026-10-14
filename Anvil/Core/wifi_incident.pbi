; ======================================================================
;  wifi_incident.pbi - the Wi-Fi flight recorder and its incident file.
;
;  Ron, 2026-10-14: "you need to build into anvil a wifi network reset when it
;  drops but save what happened to make it fail in the first place, this cant
;  happen, its a huge flaw" - and, of the death that day, "rejoin wouldnt work,
;  so there's a real failure somewhere".
;
;  WHAT IT KEEPS. A ring of the last #WIFI_REC_N radio and network events, each
;  with the millisecond it happened, a code and two numbers: every EAPOL-Key
;  frame in and every one answered (group or pairwise, its key-info), a key
;  installed (and the firmware's answer), a teardown or disassociation event
;  (its type and 802.11 reason), the association poll's answer when it was not
;  "associated", every keepalive probe and the round trip that proves it, every
;  DHCP packet out and every answer in, each recovery phase and its result, a
;  payload entered and returned (how long the radio went unserviced), and the
;  frames and SDIO credits the host saw. Cheap enough to record always.
;
;  WHEN IT IS SAVED. The moment a failure is DETECTED - before any recovery step
;  changes anything - the ring and a snapshot of the counters are written to
;  WIFILOG.TXT on the boot partition (the same FAT the settings live on), so the
;  evidence of what made the link fail survives the recovery, a reset and a
;  power cycle. Each recovery outcome is saved after it too, so the file shows
;  whether a rejoin restored traffic or only an association. The newest
;  incidents are kept (#WIFI_LOG_MAX bytes). `wifi incidents` reads it back.
;
;  WHAT IT IS NOT. It never decides anything: the link health check and the
;  recovery own every action. A recorder that also acted would be a second
;  owner of the radio, which wifi.pi4's whole ownership design exists to stop.
;
;  Depends on: millis(), wallclock.pbi (WallClockLocalNow, WallClockZoneConfigured),
;  hwfile.pbi (HwFileWriteAll and the read path), the console's Print family.
; ======================================================================

#WIFI_REC_N = 256                       ; events kept in RAM
#WIFI_LOG_MAX = 49152                   ; bytes of WIFILOG.TXT kept on the stick (newest)
#WIFI_LOG_TXT = 16384                   ; the text one incident may take

; the event codes, and what a and b carry
#WR_EAPOL_IN = 1                        ; a = key-info, b = length
#WR_EAPOL_OUT = 2                       ; a = key-info answered, b = 1 group / 2 pairwise
#WR_EAPOL_FAIL = 3                      ; a = the step, b = the code
#WR_KEY_SET = 4                         ; a = 1 group / 2 pairwise, b = the firmware's answer
#WR_TEARDOWN = 5                        ; a = event type, b = 802.11 reason
#WR_ASSOC_POLL = 6                      ; a = the poll's answer (0 not associated, -1 failed)
#WR_KA_PROBE = 7                        ; a = probes outstanding
#WR_KA_PROOF = 8                        ; a = ms since the last proof
#WR_TXONLY = 9                          ; a = probes unanswered, b = ms without proof
#WR_REC_START = 10                      ; a = generation, b = why (1 forced/teardown, 0 retry)
#WR_REC_PHASE = 11                      ; a = phase, b = result
#WR_REC_OK = 12                         ; a = the address
#WR_REC_FAIL = 13                       ; a = phase, b = result
#WR_DHCP_OUT = 14                       ; a = message type, b = attempt
#WR_DHCP_IN = 15                        ; a = message type, b = 1 accepted / 0 dropped
#WR_PAYLOAD_IN = 16                     ; a = run number
#WR_PAYLOAD_OUT = 17                    ; a = seconds the radio was not serviced, b = x0 low bits
#WR_RADIO_RESET = 18                    ; a = step, b = result
#WR_COUNTS = 19                         ; a = frames in since the last mark, b = frames out
#WR_CREDIT = 20                         ; a = the host's tx sequence, b = the dongle's max sequence
#WR_JOIN = 21                           ; a = step, b = result
#WR_NOTE = 22                           ; a, b as the caller says (free)

Global Dim wrec_t.i[#WIFI_REC_N] : Global Dim wrec_c.i[#WIFI_REC_N] : Global Dim wrec_a.i[#WIFI_REC_N] : Global Dim wrec_b.i[#WIFI_REC_N]
Global wrec_head.i, wrec_n.i, wrec_total.i, wrec_saved.i, wrec_saveErr.i, wrec_incidents.i
Global Dim wrec_txt.a[#WIFI_LOG_TXT]
Global Dim wrec_file.a[#WIFI_LOG_MAX + #WIFI_LOG_TXT + 16]
Global wrec_at.i

; One event into the ring. Never fails, never prints, never touches a bus.
Procedure WifiRec(code.i, a.i, b.i)
  wrec_t[wrec_head] = millis() : wrec_c[wrec_head] = code : wrec_a[wrec_head] = a : wrec_b[wrec_head] = b
  wrec_head = (wrec_head + 1) % #WIFI_REC_N
  If wrec_n < #WIFI_REC_N : wrec_n = wrec_n + 1 : EndIf
  wrec_total = wrec_total + 1
EndProcedure

Procedure.i WifiRecIncidents() : ProcedureReturn wrec_incidents : EndProcedure
Procedure.i WifiRecSaved() : ProcedureReturn wrec_saved : EndProcedure
Procedure.i WifiRecSaveError() : ProcedureReturn wrec_saveErr : EndProcedure

; ---------------------------------------------------------------- the text
Procedure wrec_Ch(c.i)
  If wrec_at < #WIFI_LOG_TXT - 2 : wrec_txt[wrec_at] = c : wrec_at = wrec_at + 1 : EndIf
EndProcedure

Procedure wrec_Str(*s)
  Define i.i, c.i
  If *s = 0
    ProcedureReturn
  EndIf
  c = PeekA(*s)
  While c <> 0 And i < 200
    wrec_Ch(c) : i = i + 1 : c = PeekA(*s + i)
  Wend
EndProcedure

Procedure wrec_Dec(v.i)
  Define Dim d.a[24]
  Define n.i
  If v < 0 : wrec_Ch(45) : v = 0 - v : EndIf
  Repeat
    d[n] = 48 + v % 10 : v = v / 10 : n = n + 1
  Until v = 0 Or n >= 20
  While n > 0 : n = n - 1 : wrec_Ch(d[n]) : Wend
EndProcedure

Procedure wrec_Dec2(v.i)
  wrec_Ch(48 + (v / 10) % 10) : wrec_Ch(48 + v % 10)
EndProcedure

Procedure wrec_Hex(v.i, digits.i)
  Define k.i, x.i
  wrec_Ch(36)
  For k = digits - 1 To 0 Step -1
    x = (v >> (k * 4)) & 15
    If x < 10 : wrec_Ch(48 + x) : Else : wrec_Ch(55 + x) : EndIf
  Next
EndProcedure

Procedure wrec_NL()
  wrec_Ch(13) : wrec_Ch(10)
EndProcedure

; The local date and time, "2026-10-14 14:10:17", or the uptime when the clock is not set.
Procedure wrec_When()
  Define t.i, days.i, y.i, m.i, d.i, sod.i, mdays.i, leap.i
  t = WallClockLocalNow()
  If t <= 1600000000
    wrec_Str("uptime ") : wrec_Dec(millis() / 1000) : wrec_Str(" s")
    ProcedureReturn
  EndIf
  days = t / 86400 : sod = t % 86400
  y = 1970
  Repeat
    leap = 0
    If (y % 4 = 0 And y % 100 <> 0) Or y % 400 = 0 : leap = 1 : EndIf
    If days < 365 + leap : Break : EndIf
    days = days - 365 - leap : y = y + 1
  ForEver
  m = 1
  Repeat
    mdays = 31
    If m = 4 Or m = 6 Or m = 9 Or m = 11 : mdays = 30 : EndIf
    If m = 2 : mdays = 28 + leap : EndIf
    If days < mdays : Break : EndIf
    days = days - mdays : m = m + 1
  ForEver
  d = days + 1
  wrec_Dec(y) : wrec_Ch(45) : wrec_Dec2(m) : wrec_Ch(45) : wrec_Dec2(d) : wrec_Ch(32)
  wrec_Dec2(sod / 3600) : wrec_Ch(58) : wrec_Dec2((sod / 60) % 60) : wrec_Ch(58) : wrec_Dec2(sod % 60)
EndProcedure

Procedure wrec_Name(c.i)
  Select c
    Case #WR_EAPOL_IN : wrec_Str("EAPOL-Key in")
    Case #WR_EAPOL_OUT : wrec_Str("EAPOL-Key answered")
    Case #WR_EAPOL_FAIL : wrec_Str("EAPOL handshake FAILED")
    Case #WR_KEY_SET : wrec_Str("key installed")
    Case #WR_TEARDOWN : wrec_Str("TEARDOWN event")
    Case #WR_ASSOC_POLL : wrec_Str("association poll NOT associated")
    Case #WR_KA_PROBE : wrec_Str("keepalive probe out")
    Case #WR_KA_PROOF : wrec_Str("round trip proven")
    Case #WR_TXONLY : wrec_Str("TX-ONLY DEAD detected")
    Case #WR_REC_START : wrec_Str("recovery start")
    Case #WR_REC_PHASE : wrec_Str("recovery phase")
    Case #WR_REC_OK : wrec_Str("recovery reached an address")
    Case #WR_REC_FAIL : wrec_Str("recovery FAILED")
    Case #WR_DHCP_OUT : wrec_Str("DHCP out")
    Case #WR_DHCP_IN : wrec_Str("DHCP in")
    Case #WR_PAYLOAD_IN : wrec_Str("payload entered (radio unserviced)")
    Case #WR_PAYLOAD_OUT : wrec_Str("payload returned")
    Case #WR_RADIO_RESET : wrec_Str("RADIO RESET")
    Case #WR_COUNTS : wrec_Str("frames in/out since last mark")
    Case #WR_CREDIT : wrec_Str("SDIO credit: host seq / dongle max")
    Case #WR_JOIN : wrec_Str("join step")
    Default : wrec_Str("note")
  EndSelect
EndProcedure

; ---------------------------------------------------------------- saving
; The ring, newest last, with a heading and the caller's counters line, appended to WIFILOG.TXT (the
; newest #WIFI_LOG_MAX bytes kept). why: a short sentence. 1 saved, 0 not (wrec_saveErr says why).
Procedure.i WifiRecSave(*why, *counters)
  Define i.i, k.i, now.i, n.i, old.i, keep.i, total.i
  wrec_at = 0 : now = millis()
  wrec_incidents = wrec_incidents + 1
  wrec_Str("===== Wi-Fi incident ") : wrec_Dec(wrec_incidents) : wrec_Str(" at ") : wrec_When()
  wrec_Str(" (uptime ") : wrec_Dec(now / 1000) : wrec_Str(" s): ") : wrec_Str(*why) : wrec_NL()
  If *counters <> 0 : wrec_Str("  state: ") : wrec_Str(*counters) : wrec_NL() : EndIf
  wrec_Str("  the last ") : wrec_Dec(wrec_n) : wrec_Str(" events of ") : wrec_Dec(wrec_total) : wrec_Str(", seconds before now:") : wrec_NL()
  For i = 0 To wrec_n - 1
    k = (wrec_head - wrec_n + i + #WIFI_REC_N) % #WIFI_REC_N
    wrec_Str("  -") : wrec_Dec((now - wrec_t[k]) / 1000) : wrec_Ch(46) : wrec_Dec(((now - wrec_t[k]) % 1000) / 100) : wrec_Str("  ")
    wrec_Name(wrec_c[k]) : wrec_Str("  ") : wrec_Dec(wrec_a[k])
    wrec_Str(" / ") : wrec_Dec(wrec_b[k])
    If wrec_c[k] = #WR_EAPOL_IN Or wrec_c[k] = #WR_EAPOL_OUT : wrec_Str("  (key-info ") : wrec_Hex(wrec_a[k], 4) : wrec_Ch(41) : EndIf
    wrec_NL()
  Next
  wrec_NL()
  ; the file: what is there, the newest part of it kept, this incident after it
  old = 0
  If HwFileOpen("WIFILOG.TXT") <> 0
    old = HwFileSize()
    If old > #WIFI_LOG_MAX : keep = #WIFI_LOG_MAX : Else : keep = old : EndIf
    If keep > 0
      If HwFileReadAt(old - keep, @wrec_file[0], keep) <> keep : keep = 0 : EndIf
    EndIf
    HwFileClose()
  EndIf
  For i = 0 To wrec_at - 1 : wrec_file[keep + i] = wrec_txt[i] : Next
  total = keep + wrec_at
  If HwFileWriteAll("WIFILOG.TXT", @wrec_file[0], total) = 0
    wrec_saveErr = HwFileLastError()
    ProcedureReturn 0
  EndIf
  wrec_saved = wrec_saved + 1 : wrec_saveErr = 0
  ProcedureReturn 1
EndProcedure

; `wifi incidents`: the file, as it is on the stick.
Procedure WifiRecShow()
  Define n.i, i.i, c.i, at.i, chunk.i
  If HwFileOpen("WIFILOG.TXT") = 0
    PrintN("No Wi-Fi incident has been recorded on this stick (there is no WIFILOG.TXT).")
    ProcedureReturn
  EndIf
  n = HwFileSize()
  Print("WIFILOG.TXT, ") : PrintDec(n) : PrintN(" bytes - every Wi-Fi failure detected, the events that led to it, and each recovery step:")
  at = 0
  While at < n
    chunk = n - at : If chunk > 4096 : chunk = 4096 : EndIf
    If HwFileReadAt(at, @wrec_file[0], chunk) <> chunk : Break : EndIf
    For i = 0 To chunk - 1
      c = wrec_file[i]
      If c = 10 : PrintNl() : ElseIf c >= 32 And c < 127 : UartWrite(c) : EndIf
    Next
    at = at + chunk
    If OutBreak() <> 0 : Break : EndIf
  Wend
  HwFileClose()
  Print("Recorded this boot: ") : PrintDec(wrec_incidents) : Print(" incidents, ") : PrintDec(wrec_saved) : PrintN(" saved.")
EndProcedure

; ======================================================================
;  msglog.pbi - THE MESSAGE LOG, ON THE STICK TOO (Ron, 2026-10-14: "you
;  need to log messages too until things are solved"). Every line the
;  message log keeps (Anvil/Core/messages.pbi) is also written to
;  MSGLOG.TXT on the boot medium, stamped with the uptime, the wall clock
;  when it is set, and its message number - so what the background
;  services said survives a reset or a power-off, beside WIFILOG.TXT.
;
;  NOT WRITTEN WHERE THE MESSAGE IS MADE. Messages come from inside the
;  Wi-Fi library, the DHCP worker and the console - places a file write
;  must not start. The lines are kept in RAM (#MLOG_PEND) and written out
;  from the prompt's idle service (MsgLogTick) at most every #MLOG_EVERY_MS
;  or once #MLOG_SOON bytes wait, and at once before an incident is saved
;  (WifiRecSave calls MsgLogFlush), so the two files tell one story.
;
;  BOUNDED. There is no append in this Anvil (SvcFileAppend says so), so a
;  flush reads the file's newest part back and writes it whole with the new
;  lines after it, keeping the newest #MLOG_KEEP bytes. A line that does
;  not fit the RAM buffer is counted and said in the file, never dropped
;  silently.
; ======================================================================

EnableExplicit

#MLOG_PEND = 32768
#MLOG_KEEP = 131072
#MLOG_SOON = 8192
#MLOG_EVERY_MS = 30000

Global Dim gMlPend.a[#MLOG_PEND]
Global Dim gMlFile.a[#MLOG_KEEP + #MLOG_PEND + 256]
Global gMlPendN.i, gMlLast.i, gMlLost.i, gMlBusy.i, gMlFails.i

Procedure mlog_Ch(c.i)
  If gMlPendN < #MLOG_PEND - 2
    gMlPend[gMlPendN] = c
    gMlPendN = gMlPendN + 1
  EndIf
EndProcedure

Procedure mlog_Dec(v.i)
  Define Dim d.a[24]
  Define n.i
  If v < 0
    mlog_Ch(45)
    v = 0 - v
  EndIf
  n = 0
  Repeat
    d[n] = 48 + v % 10
    v = v / 10
    n = n + 1
  Until v = 0
  While n > 0
    n = n - 1
    mlog_Ch(d[n])
  Wend
EndProcedure

Procedure mlog_Dec2(v.i)
  mlog_Ch(48 + (v / 10) % 10)
  mlog_Ch(48 + v % 10)
EndProcedure

; The line hook: "<uptime> s  HH:MM:SS  #n  text"
Procedure MsgLogLine(p.i, n.i, msgNo.i)
  Define i.i, t.i, sod.i
  If gMlPendN + n + 48 >= #MLOG_PEND
    gMlLost = gMlLost + 1
    ProcedureReturn
  EndIf
  mlog_Dec(millis() / 1000)
  mlog_Ch(115)
  mlog_Ch(32)
  t = WallClockLocalNow()
  If t > 1600000000
    sod = t % 86400
    mlog_Ch(32)
    mlog_Dec2(sod / 3600)
    mlog_Ch(58)
    mlog_Dec2((sod / 60) % 60)
    mlog_Ch(58)
    mlog_Dec2(sod % 60)
  EndIf
  mlog_Ch(32)
  mlog_Ch(32)
  mlog_Ch(35)
  mlog_Dec(msgNo)
  mlog_Ch(32)
  mlog_Ch(32)
  For i = 0 To n - 1
    mlog_Ch(PeekA(p + i))
  Next
  mlog_Ch(13)
  mlog_Ch(10)
EndProcedure

; Writes what waits to MSGLOG.TXT. force <> 0: now, whatever the clock says.
Procedure MsgLogFlush(force.i)
  Define old.i, keep.i, total.i, i.i
  If gMlPendN = 0 And gMlLost = 0
    ProcedureReturn
  EndIf
  If force = 0 And gMlPendN < #MLOG_SOON And ((millis() - gMlLast) & $FFFFFFFF) < #MLOG_EVERY_MS
    ProcedureReturn
  EndIf
  If gMlBusy <> 0 Or StorageUp() = 0
    ProcedureReturn
  EndIf
  gMlBusy = 1
  gMlLast = millis()
  keep = 0
  If HwFileOpen("MSGLOG.TXT") <> 0
    old = HwFileSize()
    keep = old
    If keep > #MLOG_KEEP - gMlPendN
      keep = #MLOG_KEEP - gMlPendN
    EndIf
    If keep < 0
      keep = 0
    EndIf
    If keep > 0
      If HwFileReadAt(old - keep, @gMlFile[0], keep) <> keep
        keep = 0
      EndIf
    EndIf
    HwFileClose()
  EndIf
  total = keep
  For i = 0 To gMlPendN - 1
    gMlFile[total + i] = gMlPend[i]
  Next
  total = total + gMlPendN
  If gMlLost > 0
    For i = 0 To 33
      gMlFile[total + i] = PeekA(?mlog_lostText + i)
    Next
    total = total + 34
  EndIf
  If HwFileWriteAll("MSGLOG.TXT", @gMlFile[0], total) <> 0
    gMlPendN = 0
    gMlLost = 0
  Else
    gMlFails = gMlFails + 1
  EndIf
  gMlBusy = 0
EndProcedure

; The prompt's idle service: the rate-limited flush.
Procedure MsgLogTick()
  MsgLogFlush(0)
EndProcedure

Procedure MsgLogStart()
  gMlLast = millis()
  gMsgLineHook = @MsgLogLine
  gAnvilIdleHook = @MsgLogTick
EndProcedure

DataSection
  mlog_lostText:   ; "!! lines lost: the RAM buffer filled\r\n" in 34 bytes
    Data.a 33,33,32,108,105,110,101,115,32,108,111,115,116,58,32,98,117,102,102,101,114,32,102,117,108,108,32,104,101,114,101,46,13,10
EndDataSection

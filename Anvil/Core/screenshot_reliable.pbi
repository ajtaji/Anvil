; Shared live screenshot wire format consumed by tools/pmfshot_wifi.py.
; The caller guarantees a stable, readable front buffer through both passes.
#PICR_RUNS_MAX = 127             ; 4 + 127*8 = 1020 bytes, under the 1024 cap
#PICR_TAG_HDR  = $FFFFFFFE
#PICR_TAG_END  = $FFFFFFFF
#PICR_TRIES    = 8               ; resends before declaring the host gone
#PICR_ACK_MS   = 600             ; wait per try for the echoed tag
#PICR_SHOT_MAGIC = $31525350     ; "PSR1" in little-endian byte order
#PICR_SHOT_VERSION = 1

Global Dim gPicrBuf.a[1024]      ; [tag:4][payload up to 1020]
Global gPicrN.i                  ; run records in the buffer, not yet sent
Global gPicrOff.i                ; byte offset of the buffer's first record
Global gPicrRuns.i               ; total runs emitted
Global gPicrCrc.i                ; rolling CRC32 (pre-inversion form)
Global gPicrOk.i                 ; 0 the moment the peer stops answering

; Send gPicrBuf (tag + len payload bytes) and wait for the tag echoed
; back. Stop-and-wait, wb's discipline: a datagram whose ack does not
; come back is simply resent, and a stale ack (a resend's twin) is
; ignored rather than trusted.
Procedure.i picr_SendWait(tag.i, len.i)
  Define try.i
  Define plen.i
  Define got.i
  PokeL(@gPicrBuf[0], tag & $FFFFFFFF)
  try = 0
  While try < #PICR_TRIES
    NetConsoleSendPeer(@gPicrBuf[0], 4 + len)
    plen = NetConsolePollUdp(#PICR_ACK_MS)
    While plen >= 0
      If plen = 4
        got = PeekN(NetUdpRxData()) & $FFFFFFFF
        If got = (tag & $FFFFFFFF)
          ProcedureReturn 1
        EndIf
      EndIf
      ; Not our ack (a stale one, or a stray keystroke datagram): keep
      ; listening briefly before spending a resend on it.
      plen = NetConsolePollUdp(100)
    Wend
    try = try + 1
  Wend
  ProcedureReturn 0
EndProcedure

; Append one run record; when the datagram is full, CRC it and send it.
Procedure picr_PushRun(cnt.i, px.i)
  If gPicrOk = 0
    ProcedureReturn
  EndIf
  PokeL(@gPicrBuf[4 + (gPicrN * 8)], cnt & $FFFFFFFF)
  PokeL(@gPicrBuf[8 + (gPicrN * 8)], px & $FFFFFFFF)
  gPicrN = gPicrN + 1
  gPicrRuns = gPicrRuns + 1
  If gPicrN >= #PICR_RUNS_MAX
    gPicrCrc = Crc32Part(gPicrCrc, @gPicrBuf[4], gPicrN * 8)
    If picr_SendWait(gPicrOff, gPicrN * 8) = 0
      gPicrOk = 0
    EndIf
    gPicrOff = gPicrOff + (gPicrN * 8)
    gPicrN = 0
  EndIf
EndProcedure

Procedure AnvilScreenshotReliable(fb.i,w.i,h.i,pitch.i,rot.i,panelW.i,panelH.i)
  Define x.i
  Define y.i
  Define px.i
  Define run.i
  Define cur.i
  Define runs1.i
  Define wasMirror.i
  Define wasAux.i
  Define aborted.i

  ; ---- pass 1: count the runs, touching nothing -----------------------
  runs1 = 0
  y = 0
  While y < h
    If OutBreakCtrlC() <> 0
      Break
    EndIf
    x = 0
    cur = ScrCapturePixel(fb, pitch, rot, panelW, panelH, 0, y)
    run = 0
    While x < w
      px = ScrCapturePixel(fb, pitch, rot, panelW, panelH, x, y)
      If px <> cur
        runs1 = runs1 + 1
        cur = px
      EndIf
      x = x + 1
    Wend
    runs1 = runs1 + 1                ; the row's last run; rows never merge
    y = y + 1
  Wend
  If OutBroke() <> 0
    PrintN("Screenshot aborted before anything was sent.")
    ProcedureReturn
  EndIf

  ; ---- go quiet: binary only between the header and the end marker ----
  wasMirror = UartMirrorOn()
  UartMirror(0)                      ; same feedback rule as p
  NetConsoleFlush()                  ; the command's own echo reaches the host first
  wasAux = UartAuxOn()
  UartAuxMirror(0)

  gPicrN = 0
  gPicrOff = 0
  gPicrRuns = 0
  gPicrCrc = $FFFFFFFF
  gPicrOk = 1
  aborted = 0

  ; ---- the header ------------------------------------------------------
  PokeL(@gPicrBuf[4], w)
  PokeL(@gPicrBuf[8], h)
  PokeL(@gPicrBuf[12], runs1)
  PokeL(@gPicrBuf[16], 8)
  If picr_SendWait(#PICR_TAG_HDR, 16) = 0
    gPicrOk = 0
  EndIf

  ; ---- pass 2: emit the same runs, acknowledged ------------------------
  If gPicrOk <> 0
    y = 0
    While y < h
      If OutBreakCtrlC() <> 0
        aborted = 1
        Break
      EndIf
      If gPicrOk = 0
        Break
      EndIf
      x = 0
      cur = ScrCapturePixel(fb, pitch, rot, panelW, panelH, 0, y)
      run = 0
      While x < w
        px = ScrCapturePixel(fb, pitch, rot, panelW, panelH, x, y)
        If px = cur
          run = run + 1
        Else
          picr_PushRun(run, cur)
          cur = px
          run = 1
        EndIf
        x = x + 1
      Wend
      If run > 0
        picr_PushRun(run, cur)
      EndIf
      y = y + 1
    Wend
  EndIf

  ; The tail that has not filled a datagram yet.
  If gPicrOk <> 0 And aborted = 0 And gPicrN > 0
    gPicrCrc = Crc32Part(gPicrCrc, @gPicrBuf[4], gPicrN * 8)
    If picr_SendWait(gPicrOff, gPicrN * 8) = 0
      gPicrOk = 0
    EndIf
    gPicrOff = gPicrOff + (gPicrN * 8)
    gPicrN = 0
  EndIf

  ; ---- the end marker - sent even after a Ctrl-C, so the host is told
  ; the stream is over (status 0) rather than left to time out.
  If gPicrOk <> 0
    PokeL(@gPicrBuf[4], gPicrRuns)
    PokeL(@gPicrBuf[8], (gPicrCrc ! $FFFFFFFF) & $FFFFFFFF)
    If aborted <> 0
      PokeL(@gPicrBuf[12], 0)
    Else
      PokeL(@gPicrBuf[12], 1)
    EndIf
    If picr_SendWait(#PICR_TAG_END, 12) = 0
      gPicrOk = 0
    EndIf
  EndIf

  ; ---- text flows again, then say what happened ------------------------
  If wasAux <> 0
    UartAuxMirror(1)
  EndIf
  If wasMirror <> 0
    UartMirror(0)
    UartMirror(1)
  EndIf
  If gPicrOk = 0
    PrintN("!! the peer stopped acknowledging, so the reliable screenshot did")
    PrintN("   not complete. Nothing half-made is left on either side - run it")
    PrintN("   again.")
  ElseIf aborted <> 0
    PrintN("Screenshot aborted by Ctrl-C; the host was told so.")
  Else
    Print("Sent ")
    PrintDec(gPicrRuns)
    Print(" runs (")
    PrintDec(gPicrOff)
    PrintN(" bytes), every datagram acknowledged, CRC32 checked host-side.")
  EndIf
EndProcedure

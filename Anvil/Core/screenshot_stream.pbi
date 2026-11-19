; Shared live screenshot protocol. Each board provides ScrCapturePixel for its scanout.
Procedure AnvilScreenshotStream(fb.i,w.i,h.i,pitch.i,rot.i,panelW.i,panelH.i,bpp.i)
  Define x.i
  Define y.i
  Define px.i
  Define run.i
  Define cur.i
  Define runs.i
  Define wasMirror.i

  ; See the header: dumping to the UART would feed the screen console.
  wasMirror = UartMirrorOn()
  UartMirror(0)

  ; ------------------------------------------------------------------
  ; EVERYTHING FROM HERE TO "END" IS A MACHINE FORMAT, NOT PROSE.
  ; tools/pmfshot.py parses it with three regular expressions and
  ; nothing else, and all three are anchored to the whole line:
  ;
  ;   ^PIC ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{2})$   the header
  ;   ^([0-9A-F]{6}) ([0-9A-F]{8})$                     one run
  ;   ^END ([0-9A-F]{8})$                               the terminator
  ;
  ; So the word PIC, the single spaces, the exact digit counts and the
  ; upper-case hex are all fixed. A friendlier header would make the
  ; script report "no PIC header in the reply" and refuse to write a
  ; PNG. This was audited during the plain-English sweep on 2026-08-26
  ; and deliberately left exactly as it was.
  ; ------------------------------------------------------------------
  Print("PIC ")
  PutHexN(w, 8)
  Print(" ")
  PutHexN(h, 8)
  Print(" ")
  PutHexN(bpp, 2)
  PrintNl()
  UartDrain()

  ; COALESCE THE RUN STREAM. A busy screen is tens of thousands of short
  ; run-lines; flushed one datagram per line over Wi-Fi that firehose
  ; overruns buffers and drops a datagram mid-stream, which strips the
  ; capture of a run (an unrecoverable gap) or its END (no PNG at all). Bulk
  ; mode lets the aux tap fill full ~1 KB datagrams instead - same bytes,
  ; ~16x fewer packets - which is what makes a full busy-screen capture
  ; decode cleanly. The header above went out first, at its line boundary,
  ; so the host sees PIC without waiting for a datagram to fill. The serial
  ; screenshot path does not use the aux tap and is unaffected.
  UartAuxBulk(1)

  runs = 0
  y = 0
  While y < h
    ; ONE CHECK PER SCREEN ROW, and Ctrl-C ONLY - see OutBreakCtrlC()
    ; for why this path does not take the any-byte rule. A row is a few
    ; runs, so this is far finer-grained than the once-a-line the text
    ; commands get, and it costs one MMIO read out of a seven-minute
    ; transfer.
    If OutBreakCtrlC() <> 0
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
        PutHexN(run, 6)
        UartWrite(32)
        PutHexN(cur, 8)
        PrintNl()
        runs = runs + 1
        cur = px
        run = 1
      EndIf
      x = x + 1
    Wend
    ; The last run of the row. Rows never merge - see the header.
    If run > 0
      PutHexN(run, 6)
      UartWrite(32)
      PutHexN(cur, 8)
      PrintNl()
      runs = runs + 1
    EndIf
    y = y + 1
  Wend

  ; "END <count>" ONLY IF IT REALLY ENDED. An aborted stream says ABORT
  ; instead, and that spelling is load-bearing: tools/pmfshot.py matches
  ; "^END ([0-9A-F]{8})$" and nothing else, so a truncated capture makes
  ; the script report "the stream stopped before END" and refuse to
  ; write a PNG. A short stream that still said END would parse, the run
  ; count would disagree, and the script would blame the wire. The count
  ; is printed either way, because knowing how far it got is worth a
  ; line.
  ; Leave bulk mode so the terminator and the last coalesced runs are
  ; flushed by the per-line rule, and send the terminator THREE TIMES.
  ; Losing the one datagram that carried END would otherwise waste the whole
  ; capture (the host would decode nothing); with the marker repeated, a
  ; single drop cannot strip it. The host stops at the first well-formed
  ; terminator, so the extra lines are harmless. The run COUNT is what proves
  ; the stream arrived whole, so a surviving END still validates the capture.
  Define termI.i
  UartAuxBulk(0)
  termI = 0
  While termI < 3
    If OutBroke() <> 0
      Print("ABORT ")
    Else
      Print("END ")
    EndIf
    PutHexN(runs, 8)
    PrintNl()
    termI = termI + 1
  Wend
  UartDrain()

  ; The mirror buffer filled with the dump while it was off, so putting
  ; it back also empties it - otherwise the next prompt would replay
  ; several thousand lines of hex onto the screen.
  If wasMirror <> 0
    UartMirror(0)
    UartMirror(1)
  EndIf
EndProcedure

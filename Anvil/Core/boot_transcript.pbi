; Bounded boot transcript for rebuilding an early console after its final
; geometry is known. Capture is storage only: this file never prints and has
; no UART, network, settings, display or console dependency.
;
; Overflow preserves the complete prefix and counts every later byte. The
; caller must report BootTranscriptLost() visibly before claiming the replay
; is complete.
;
; THERE IS NO CURSOR AND THAT IS THE POINT. Replay is the caller walking
; BootTranscriptAt(0..Count-1) and handing each byte to whatever rebuilt
; surface it owns, so a failed reconstruction can clear that surface and
; walk again from byte zero without duplicating a prefix - and nothing in
; here has to know whether the last attempt got half way.
;
; THE CALLER STOPS CAPTURE BEFORE IT REPLAYS. Otherwise the replayed bytes
; arrive back at whatever tap fed this buffer and the transcript doubles
; itself every time a geometry change is applied.

#BOOT_TRANSCRIPT_BYTES = 16384

Global Dim gBootTranscript.a[#BOOT_TRANSCRIPT_BYTES]
Global gBootTranscriptCount.i
Global gBootTranscriptLost.i
Global gBootTranscriptActive.i

Procedure BootTranscriptReset()
  gBootTranscriptCount = 0
  gBootTranscriptLost = 0
  gBootTranscriptActive = 0
EndProcedure

Procedure BootTranscriptStart()
  BootTranscriptReset()
  gBootTranscriptActive = 1
EndProcedure

Procedure.i BootTranscriptPut(c.i)
  If gBootTranscriptActive = 0
    ProcedureReturn 0
  EndIf
  If gBootTranscriptCount >= #BOOT_TRANSCRIPT_BYTES
    gBootTranscriptLost = gBootTranscriptLost + 1
    ProcedureReturn 0
  EndIf
  gBootTranscript[gBootTranscriptCount] = c & $FF
  gBootTranscriptCount = gBootTranscriptCount + 1
  ProcedureReturn 1
EndProcedure

Procedure.i BootTranscriptStop()
  gBootTranscriptActive = 0
  ProcedureReturn gBootTranscriptCount
EndProcedure

Procedure.i BootTranscriptActive()
  ProcedureReturn gBootTranscriptActive
EndProcedure

Procedure.i BootTranscriptCount()
  ProcedureReturn gBootTranscriptCount
EndProcedure

Procedure.i BootTranscriptLost()
  ProcedureReturn gBootTranscriptLost
EndProcedure

; One retained byte, or -1 for an index outside the prefix. -1 cannot be
; confused with data: a byte is masked to 0..255 on the way in and on the
; way out, so every real answer is non-negative.
Procedure.i BootTranscriptAt(index.i)
  If index < 0 Or index >= gBootTranscriptCount
    ProcedureReturn -1
  EndIf
  ProcedureReturn gBootTranscript[index] & $FF
EndProcedure

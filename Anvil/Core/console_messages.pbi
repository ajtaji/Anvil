; Shared background-message byte routing. A serialized monitor context owns
; registration and writes. A drain must not print; the busy guard prevents
; recursive callback entry. With no drain, brackets do not divert output.
#ANVIL_CONSOLE_MESSAGE_BYTES = 8192
Global Dim anvilConsoleMsg.a[#ANVIL_CONSOLE_MESSAGE_BYTES]
Global anvilConsoleMsgDepth.i
Global anvilConsoleMsgHead.i
Global anvilConsoleMsgTail.i
Global anvilConsoleMsgLost.i
Global anvilConsoleMsgBytes.i         ; bytes ever diverted, for the gate and `messages`
; A concrete unbound target keeps optional callback signatures defined even in
; standalone diagnostics. The bound flag, not this target, admits diversion.
Procedure AnvilConsoleNoMessageDrain() : EndProcedure
Global *anvilConsoleMsgDrain = @AnvilConsoleNoMessageDrain
Global anvilConsoleMsgBound.i
Global anvilConsoleMsgBusy.i

; Register the message log's drain, or 0 to stop diverting. The drain MUST
; NOT print: it runs inside UartWrite. It is re-entry guarded regardless.
Procedure UartMessageSetDrain(*fn)
  If *fn
    *anvilConsoleMsgDrain = *fn : anvilConsoleMsgBound = 1
  Else
    *anvilConsoleMsgDrain = @AnvilConsoleNoMessageDrain : anvilConsoleMsgBound = 0
  EndIf
EndProcedure

Procedure UartMessageBegin()
  anvilConsoleMsgDepth = anvilConsoleMsgDepth + 1
EndProcedure

; Close one bracket. Leaving the outermost one hands whatever the context
; wrote to the drain, so a message that did not end in a newline is not
; left sitting in the ring until the next one arrives and joins it.
Procedure UartMessageEnd()
  If anvilConsoleMsgDepth <= 0
    anvilConsoleMsgDepth = 0
    ProcedureReturn
  EndIf
  anvilConsoleMsgDepth = anvilConsoleMsgDepth - 1
  If anvilConsoleMsgDepth = 0 And anvilConsoleMsgBound <> 0 And anvilConsoleMsgBusy = 0
    anvilConsoleMsgBusy = 1
    anvilConsoleMsgDrain()
    anvilConsoleMsgBusy = 0
  EndIf
EndProcedure

; Leave every bracket at once. For the fatal-exception path only.
Procedure UartMessageAbandon()
  anvilConsoleMsgDepth = 0
EndProcedure

Procedure.i UartMessageDepth()
  ProcedureReturn anvilConsoleMsgDepth
EndProcedure

; 1 while a byte written now would be diverted.
Procedure.i UartMessageActive()
  If anvilConsoleMsgDepth > 0 And anvilConsoleMsgBound <> 0
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i UartMessageGet()
  Define c.i
  If anvilConsoleMsgTail = anvilConsoleMsgHead
    ProcedureReturn -1
  EndIf
  c = anvilConsoleMsg[anvilConsoleMsgTail] & $FF
  anvilConsoleMsgTail = anvilConsoleMsgTail + 1
  If anvilConsoleMsgTail >= #ANVIL_CONSOLE_MESSAGE_BYTES
    anvilConsoleMsgTail = 0
  EndIf
  ProcedureReturn c
EndProcedure

Procedure.i UartMessageLost()
  ProcedureReturn anvilConsoleMsgLost
EndProcedure

Procedure.i UartMessageBytes()
  ProcedureReturn anvilConsoleMsgBytes
EndProcedure

Procedure UartMessagePut(c.i)
  Define nxt.i
  Define n.i
  anvilConsoleMsgBytes = anvilConsoleMsgBytes + 1
  nxt = anvilConsoleMsgHead + 1
  If nxt >= #ANVIL_CONSOLE_MESSAGE_BYTES
    nxt = 0
  EndIf
  If nxt = anvilConsoleMsgTail
    anvilConsoleMsgLost = anvilConsoleMsgLost + 1
    ProcedureReturn
  EndIf
  anvilConsoleMsg[anvilConsoleMsgHead] = c & $FF
  anvilConsoleMsgHead = nxt
  n = anvilConsoleMsgHead - anvilConsoleMsgTail
  If n < 0
    n = n + #ANVIL_CONSOLE_MESSAGE_BYTES
  EndIf
  If anvilConsoleMsgBusy = 0
    If c = 10 Or n > (#ANVIL_CONSOLE_MESSAGE_BYTES - 2048)
      anvilConsoleMsgBusy = 1
      anvilConsoleMsgDrain()
      anvilConsoleMsgBusy = 0
    EndIf
  EndIf
EndProcedure

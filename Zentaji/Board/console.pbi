; Serial port 0 is the monitor console. No reset, RX drain, baud change or
; counter clear occurs on adoption. The owner must exclude block/DMA users.
; Background-message routing is shared monitor policy above the transport.
XIncludeFile "Zentaji/Board/prompt_idle.pbi"
XIncludeFile "Anvil/Core/console_messages.pbi"
XIncludeFile "Zentaji/Board/text.pbi"
#ZEN_CONSOLE = $FFFF000000100000
#ZEN_CONSOLE_POLLS = 4096
Global zenConsoleUp.i=0
Global zenConsoleDropped.i=0
Global zenConsoleDropBase.q=0
Global zenConsoleHardwareDropped.q=0
Global zenConsoleFaultCount.i=0

Procedure.i UartAttach()
  If (PeekQ(#ZEN_CONSOLE)&$FFFF)<>17 Or (PeekQ(#ZEN_CONSOLE+$08)&$30)<>0
    ProcedureReturn 0
  EndIf
  If zenConsoleUp=0
    zenConsoleDropBase=PeekQ(#ZEN_CONSOLE+$98)
    zenConsoleDropped=0
    zenConsoleHardwareDropped=0
    zenConsoleFaultCount=0
    zenConsoleUp=1
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i UartRunning() : ProcedureReturn zenConsoleUp : EndProcedure
Procedure.i ZentajiConsoleFaults() : ProcedureReturn zenConsoleFaultCount : EndProcedure

Procedure.i UartInit(baud.i)
  If baud<0 Or (PeekQ(#ZEN_CONSOLE+$08)&$32)<>2
    ProcedureReturn 0
  EndIf
  If UartAttach()=0 : ProcedureReturn 0 : EndIf
  ; The machine directly accepts the nominal baud. Zero selects unpaced TX.
  PokeQ(#ZEN_CONSOLE+$60,baud)
  ProcedureReturn 1
EndProcedure

Procedure.i UartInitClk(baud.i,hz.i)
  If hz<>TickHz() : ProcedureReturn 0 : EndIf
  ProcedureReturn UartInit(baud)
EndProcedure

Procedure.i ZentajiConsolePut(c.i)
  Protected n.i, start.q, limit.q
  If zenConsoleUp=0 Or (PeekQ(#ZEN_CONSOLE+$08)&16)<>0
    ProcedureReturn 0
  EndIf
  start=Ticks() : limit=TickHz()/10
  For n=1 To #ZEN_CONSOLE_POLLS
    If (PeekQ(#ZEN_CONSOLE+$08)&16)<>0 : ProcedureReturn 0 : EndIf
    If PeekQ(#ZEN_CONSOLE+$58)>0
      PokeQ(#ZEN_CONSOLE+$40,c&$FF)
      ProcedureReturn 1
    EndIf
    If limit<1 Or Ticks()-start>=limit : ProcedureReturn 0 : EndIf
    If HwPromptIdleReady()<>0 : HwPromptIdleWait() : EndIf
  Next
  ProcedureReturn 0
EndProcedure

Procedure UartWrite(c.i)
  If UartMessageActive()<>0 : UartMessagePut(c) : ProcedureReturn : EndIf
  ZentajiTextByte(c)
  If ZentajiConsolePut(c)=0 : zenConsoleDropped=zenConsoleDropped+1 : EndIf
EndProcedure

XIncludeFile "Anvil/Core/console_bytes.pbi"

Procedure.i UartDropped()
  If zenConsoleUp<>0 : zenConsoleHardwareDropped=PeekQ(#ZEN_CONSOLE+$98)-zenConsoleDropBase : EndIf
  ProcedureReturn zenConsoleDropped+zenConsoleHardwareDropped
EndProcedure

Procedure.i UartReadReady()
  If zenConsoleUp=0 Or (PeekQ(#ZEN_CONSOLE+$08)&32)<>0 : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool(PeekQ(#ZEN_CONSOLE+$50)>0)
EndProcedure

Procedure.i UartReadWait(spins.i)
  Protected n.i, start.q, limit.q
  If spins<1 Or zenConsoleUp=0 : ProcedureReturn -1 : EndIf
  If spins>#ZEN_CONSOLE_POLLS : spins=#ZEN_CONSOLE_POLLS : EndIf
  start=Ticks() : limit=TickHz()/10
  For n=1 To spins
    If (PeekQ(#ZEN_CONSOLE+$08)&32)<>0 : ProcedureReturn -1 : EndIf
    If UartReadReady()<>0 : ProcedureReturn PeekQ(#ZEN_CONSOLE+$48) : EndIf
    If limit<1 Or Ticks()-start>=limit : Break : EndIf
  Next
  ProcedureReturn -1
EndProcedure

Procedure.i UartRead()
  ; Healthy blocking input uses the qualified idle backend. Loss of ownership
  ; or a missing wait source is an error, never an unbounded busy-spin.
  While zenConsoleUp<>0
    If (PeekQ(#ZEN_CONSOLE+$08)&32)<>0 : Break : EndIf
    If UartReadReady()<>0 : ProcedureReturn PeekQ(#ZEN_CONSOLE+$48) : EndIf
    If HwPromptIdleReady()=0 : Break : EndIf
    HwPromptIdleWait()
  Wend
  zenConsoleFaultCount=zenConsoleFaultCount+1
  ProcedureReturn -1
EndProcedure

Procedure.i ZentajiConsoleDrain()
  Protected n.i, start.q, limit.q
  If zenConsoleUp=0 : ProcedureReturn 0 : EndIf
  start=Ticks() : limit=TickHz()/10
  For n=1 To #ZEN_CONSOLE_POLLS
    ; In this device TX empty means the final timed byte has completed,
    ; including its ten-bit frame. A pending block send is not drained.
    If (PeekQ(#ZEN_CONSOLE+$08)&18)=2 : ProcedureReturn 1 : EndIf
    If limit<1 Or Ticks()-start>=limit : Break : EndIf
    If HwPromptIdleReady()<>0 : HwPromptIdleWait() : EndIf
  Next
  zenConsoleFaultCount=zenConsoleFaultCount+1
  ProcedureReturn 0
EndProcedure

Procedure UartDrain() : ZentajiConsoleDrain() : EndProcedure

Procedure UartOff()
  ; Logical detach: preserve queued input/output and all hardware settings.
  Define ignored.i=UartDropped()
  zenConsoleUp=0
EndProcedure

; Compiler-routed formatting is the existing transport-neutral guest library.
Procedure PrintChar(c.i) : UartWrite(c) : EndProcedure
XIncludeFile "Shared/A64/string_out.pmi"

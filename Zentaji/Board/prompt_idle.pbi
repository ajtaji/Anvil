; Bounded prompt idle for the Zentaji machine, entered in supervisor mode.
; The board reserves the calling core's timer and configures line 1 as a
; level interrupt, enabled above that core's threshold, before Prepare.
; No global timer, other core's timer, IRQ enable, route or threshold is changed.
; Other users must not access the reserved timer until Release succeeds.
XIncludeFile "Zentaji/Board/clock.pbi"

Global zenIdleOwner.i=-1
Global zenIdlePeriod.q=0
Global zenIdleOldCompare.q=0

Procedure.i ZentajiPromptIdleContext()
  ; STATUS itself is supervisor-only: this is an Anvil backend, not a user
  ; entry gate. Busy block/step/NMI contexts and nested IRQ service cannot wait.
  If (ZenCpuStatus()&$1E)<>0 Or PeekQ(#ZEN_IDLE_INTC+$F028)<>0
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i ZentajiPromptIdleInterrupt()
  Protected config.i=PeekQ(#ZEN_IDLE_INTC+$120)
  Protected threshold.i=PeekQ(#ZEN_IDLE_INTC+$F010)
  If (config&$FF00)<>0 Or (config&$FF)<1 Or (config&$FF)>15
    ProcedureReturn 0
  EndIf
  If threshold>=(config&$FF) Or (PeekQ(#ZEN_IDLE_INTC+$F008)&2)=0
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i ZentajiPromptIdleTimerFree()
  If PeekQ(#ZEN_IDLE_TIMER+$10)<>0 Or PeekQ(#ZEN_IDLE_TIMER+$08)<>0 Or PeekQ(#ZEN_IDLE_TIMER+$18)<>0
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i ZentajiPromptIdlePrepare(maxMicroseconds.i)
  Protected hz.q
  If zenIdleOwner>=0 Or maxMicroseconds<50 Or maxMicroseconds>2000
    ProcedureReturn 0
  EndIf
  If ZentajiPromptIdleContext()=0
    ProcedureReturn 0
  EndIf
  If (PeekQ(#ZEN_IDLE_TIMERS)&$FFFF)<>6 Or (PeekQ(#ZEN_IDLE_INTC)&$FFFF)<>5
    ProcedureReturn 0
  EndIf
  hz=TickHz()
  If hz<1 Or hz>($7FFFFFFFFFFFFFFF/maxMicroseconds) Or ZentajiPromptIdleInterrupt()=0 Or ZentajiPromptIdleTimerFree()=0
    ProcedureReturn 0
  EndIf
  ; Round down to stay within the requested deadline; refuse sub-tick waits.
  zenIdlePeriod=(hz*maxMicroseconds)/1000000
  If zenIdlePeriod<1 : ProcedureReturn 0 : EndIf
  zenIdleOldCompare=PeekQ(#ZEN_IDLE_TIMER)
  zenIdleOwner=ZenCpuCoreId()
  ProcedureReturn 1
EndProcedure

Procedure.i HwPromptIdleReady()
  If zenIdleOwner<0 Or ZenCpuCoreId()<>zenIdleOwner
    ProcedureReturn 0
  EndIf
  If ZentajiPromptIdleContext()=0 Or ZentajiPromptIdleInterrupt()=0 Or ZentajiPromptIdleTimerFree()=0
    ProcedureReturn 0
  EndIf
  If PeekQ(#ZEN_IDLE_TIMER)<>zenIdleOldCompare
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure HwPromptIdleWait()
  Protected status.i
  If HwPromptIdleReady()=0
    ProcedureReturn
  EndIf
  status=ZenCpuIrqDisable()
  ; An IRQ may have run after the first check. Recheck before taking any
  ; timer ownership. WFI wakes with IE=0, so no timer handler is necessary.
  If HwPromptIdleReady()=0
    ZenCpuSwapStatus(status)
    ProcedureReturn
  EndIf
  PokeQ(#ZEN_IDLE_TIMER,Ticks()+zenIdlePeriod)
  PokeQ(#ZEN_IDLE_TIMER+$10,3)
  ZenCpuWait()
  ; An earlier device interrupt can wake us before the timer. Disarm first,
  ; clear only our FIRED reason, and restore the idle compare before IE.
  PokeQ(#ZEN_IDLE_TIMER+$10,0)
  PokeQ(#ZEN_IDLE_TIMER+$18,1)
  PokeQ(#ZEN_IDLE_TIMER,zenIdleOldCompare)
  ZenCpuSwapStatus(status)
EndProcedure

Procedure.i ZentajiPromptIdleRelease()
  If zenIdleOwner<0 Or ZenCpuCoreId()<>zenIdleOwner
    ProcedureReturn 0
  EndIf
  If ZentajiPromptIdleContext()=0 Or ZentajiPromptIdleTimerFree()=0 Or PeekQ(#ZEN_IDLE_TIMER)<>zenIdleOldCompare
    ProcedureReturn 0
  EndIf
  zenIdleOwner=-1
  zenIdlePeriod=0
  ProcedureReturn 1
EndProcedure

Procedure HwPromptBoardService()
  ; No optional board maintenance hook is installed by this backend.
EndProcedure

; Prompt-only event sleep. Borrow only unconfigured interrupt lines and disabled
; device sources, with IE off, then restore them before returning. Device waits
; retain their original 2ms bound. Foreign ownership uses that same safe wait.
#ZEN_IDLE_SERIAL=$FFFF000000100000
#ZEN_IDLE_INPUT=$FFFF0000000A0000
Procedure.i ZentajiPromptEventIdleReady()
 If PeekQ(#ZEN_IDLE_INTC+$200)<>0 Or PeekQ(#ZEN_IDLE_INTC+$208)<>0 Or PeekQ(#ZEN_IDLE_INTC+$2C0)<>0 Or PeekQ(#ZEN_IDLE_INTC+$2C8)<>0 : ProcedureReturn 0 : EndIf
 If (PeekQ(#ZEN_IDLE_SERIAL)&$FFFF)<>17 Or PeekQ(#ZEN_IDLE_SERIAL+$20)<>0 Or (PeekQ(#ZEN_IDLE_SERIAL+8)&$30)<>0 : ProcedureReturn 0 : EndIf
 If (PeekQ(#ZEN_IDLE_INPUT)&$FFFF)<>11 Or PeekQ(#ZEN_IDLE_INPUT+$10)<>0 Or PeekQ(#ZEN_IDLE_INPUT+$20)<>0 Or PeekQ(#ZEN_IDLE_INPUT+$B0)<>0 : ProcedureReturn 0 : EndIf
 If PeekQ(#ZEN_IDLE_INTC+$F010)>=15 Or TickHz()>$7FFFFFFFFFFFFFFF/16000 : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure

Procedure ZentajiPromptEventIdleWait()
 Protected status.i,enabled.q,priority.i,route.q,period.q
 If HwPromptIdleReady()=0 : ProcedureReturn : EndIf
 status=ZenCpuIrqDisable()
 If HwPromptIdleReady()=0 : ZenCpuSwapStatus(status) : ProcedureReturn : EndIf
 If ZentajiPromptEventIdleReady()=0
  ZenCpuSwapStatus(status) : HwPromptIdleWait() : ProcedureReturn
 EndIf
 enabled=PeekQ(#ZEN_IDLE_INTC+$F008)
 priority=PeekQ(#ZEN_IDLE_INTC+$F010)+1 : route=1<<ZenCpuCoreId()
 period=(TickHz()*16000)/1000000
 ; RX reasons are latched. Acknowledge only an already drained console RX
 ; reason, then recheck its FIFO after arming so an arrival cannot be lost.
 If PeekQ(#ZEN_IDLE_SERIAL+$50)=0 : PokeQ(#ZEN_IDLE_SERIAL+$18,1) : EndIf
 PokeQ(#ZEN_IDLE_INTC+$200,priority) : PokeQ(#ZEN_IDLE_INTC+$208,route)
 PokeQ(#ZEN_IDLE_INTC+$2C0,priority) : PokeQ(#ZEN_IDLE_INTC+$2C8,route)
 PokeQ(#ZEN_IDLE_INTC+$F008,enabled|$4100)
 PokeQ(#ZEN_IDLE_SERIAL+$20,1) : PokeQ(#ZEN_IDLE_INPUT+$20,3)
 PokeQ(#ZEN_IDLE_TIMER,Ticks()+period) : PokeQ(#ZEN_IDLE_TIMER+$10,3)
 If PeekQ(#ZEN_IDLE_SERIAL+$50)=0 And PeekQ(#ZEN_IDLE_INPUT+$48)=0 And (PeekQ(#ZEN_IDLE_INPUT+$18)&3)=0 : ZenCpuWait() : EndIf
 PokeQ(#ZEN_IDLE_SERIAL+$20,0) : PokeQ(#ZEN_IDLE_INPUT+$20,0)
 PokeQ(#ZEN_IDLE_TIMER+$10,0) : PokeQ(#ZEN_IDLE_TIMER+$18,1) : PokeQ(#ZEN_IDLE_TIMER,zenIdleOldCompare)
 PokeQ(#ZEN_IDLE_INTC+$F008,enabled)
 PokeQ(#ZEN_IDLE_INTC+$208,0) : PokeQ(#ZEN_IDLE_INTC+$200,0)
 PokeQ(#ZEN_IDLE_INTC+$2C8,0) : PokeQ(#ZEN_IDLE_INTC+$2C0,0)
 ZenCpuSwapStatus(status)
EndProcedure

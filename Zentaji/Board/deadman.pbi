; A positive shared word is a hardware TIME deadline. Zero cancels it and
; -1 commits the reset. A service pet can extend only an unexpired deadline.
Global zenDeadSeconds.i,zenDeadCore.i,zenDeadDeadline.q,zenDeadPeriod.q,zenDeadCompare.q
ProcedureNaked.i ZentajiDeadCas(address.i,expected.q,replacement.q)
 ASM
  CAS r1,r1,r2,r3,3,4
  JR r254
 EndASM
EndProcedure
ProcedureNaked ZentajiDeadWorker()
 ASM
  LIQ r16,$FFFF00000005F000
  LIQ r17,$FFFF00000004F000
  LI r18,1
  LI r19,2
  LI r20,3
  LI r21,-1
  ST64 r19,[r17+8]
zen_dead_wait:
  LD64 r22,[r1]
  BEQI r22,0,zen_dead_done
  MFCR r23,TIME
  BGEU r23,r22,zen_dead_expire
  ST64 r0,[r16+16]
  ST64 r18,[r16+24]
  ST64 r22,[r16]
  ST64 r20,[r16+16]
  WFI
  JMP zen_dead_wait
zen_dead_expire:
  CAS r23,r1,r22,r21,3,4
  BNE r23,r22,zen_dead_wait
  ST64 r0,[r16+16]
  ST64 r0,[r17+8]
  LIQ r24,$FFFF000000050800
  LI r25,100000
  ST64 r25,[r24+8]
  ST64 r18,[r24]
  ST64 r0,[r24+16]
zen_dead_reset_pending:
  WFI
  JMP zen_dead_reset_pending
zen_dead_done:
  HALT 0
 EndASM
EndProcedure

Procedure.i ZentajiDeadFree()
 Protected id.i,base.i,timer.i,irq.i
 If PeekQ(#ZEN_IDLE_TIMERS+$800)<>0 Or (PeekQ(#ZEN_IDLE_INTC+$120)&$FF)=0 : ProcedureReturn 0 : EndIf
 For id=ZentajiCoreCount()-1 To 1 Step -1
  base=ZentajiCoreWindow(id)
  timer=#ZEN_IDLE_TIMERS+$1000+id*$40 : irq=#ZEN_IDLE_INTC+$1000+id*$100
  If PeekQ(base)=0 And PeekQ(base+8)=0 And PeekQ(base+16)=0 And PeekQ(base+24)=0 And PeekQ(base+32)=0
   If PeekQ(timer+8)=0 And PeekQ(timer+16)=0 And PeekQ(timer+24)=0 And PeekQ(irq)=0 And PeekQ(irq+8)=0 And PeekQ(irq+16)=0 And PeekQ(irq+40)=0
    ProcedureReturn id
   EndIf
  EndIf
 Next
 ProcedureReturn 0
EndProcedure
Procedure ZentajiDeadBegin(id.i)
 Protected base.i,timer.i
 If id=0 : ProcedureReturn : EndIf
 base=ZentajiCoreWindow(id) : timer=#ZEN_IDLE_TIMERS+$1000+id*$40
 zenDeadCore=id : zenDeadCompare=PeekQ(timer) : zenDeadPeriod=zenDeadSeconds*TickHz()
 zenDeadDeadline=Ticks()+zenDeadPeriod : zenDeadSeconds=0
 PokeQ(base+8,@ZentajiDeadWorker) : PokeQ(base+16,@zenDeadDeadline)
 PokeQ(base+40,1)
EndProcedure
Procedure ZentajiDeadPet()
 Protected old.q=zenDeadDeadline,now.q=Ticks()
 If old>0 And now<old : ZentajiDeadCas(@zenDeadDeadline,old,now+zenDeadPeriod) : EndIf
EndProcedure
ProcedureNaked ZentajiDeadAwaitReset()
 ASM
zen_dead_return_late:
  WFI
  JMP zen_dead_return_late
 EndASM
EndProcedure
Procedure.i ZentajiDeadEnd()
 Protected old.q,base.i,timer.i,irq.i
 If zenDeadCore=0 : ProcedureReturn 1 : EndIf
 base=ZentajiCoreWindow(zenDeadCore) : timer=#ZEN_IDLE_TIMERS+$1000+zenDeadCore*$40
 irq=#ZEN_IDLE_INTC+$1000+zenDeadCore*$100
 If PeekQ(base+8)<>@ZentajiDeadWorker Or PeekQ(base+16)<>@zenDeadDeadline Or PeekQ(base+24)<>0 Or PeekQ(base+32)<>0
  ProcedureReturn 0
 EndIf
 old=zenDeadDeadline
 If old<=0 Or Ticks()>=old Or ZentajiDeadCas(@zenDeadDeadline,old,0)<>old
  ZentajiDeadAwaitReset()
 EndIf
 PokeQ(base+40,3)
 If PeekQ(base)<>0 : ProcedureReturn 0 : EndIf
 PokeQ(base+8,0) : PokeQ(base+16,0)
 PokeQ(irq+8,0) : PokeQ(timer+16,0) : PokeQ(timer+24,1) : PokeQ(timer,zenDeadCompare)
 zenDeadCore=0 : zenDeadPeriod=0
 ProcedureReturn 1
EndProcedure


XIncludeFile "Anvil/Core/deadman_arg.pbi"
Procedure ZentajiCmdDeadman()
 Protected n.i=DeadmanArgument()
 SkipSpace()
 If gLine[gPos]<>0 Or n=#DEADMAN_BAD_WORD Or n=-1
  PrintN("Use deadman, deadman off, or deadman <whole seconds>. The setting was preserved.") : ProcedureReturn
 EndIf
 If n=#DEADMAN_REPORT
  If zenDeadSeconds=0
   PrintN("Deadman is off.")
  Else
   Print("Deadman for next payload: ") : PrintDec(zenDeadSeconds) : PrintN(" seconds.")
  EndIf
  If PeekQ(#ZEN_MONITOR_POWER+$58)=2 : PrintN("The hardware watchdog caused the last machine reset.") : EndIf
  ProcedureReturn
 EndIf
 If n=#DEADMAN_OFF Or n=0 : zenDeadSeconds=0 : PrintN("Deadman is off.") : ProcedureReturn : EndIf
 If n>15 : n=15 : PrintN("Maximum monitor deadman interval is 15 seconds.") : EndIf
 zenDeadSeconds=n
 Print("Deadman for next payload: ") : PrintDec(n) : PrintN(" seconds. A free secondary supervises the run.")
EndProcedure

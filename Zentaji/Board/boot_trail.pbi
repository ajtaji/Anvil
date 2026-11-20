; Upper 128 bytes of the native RTC NVRAM. Alternate two 64-byte records on
; soft reset. Each aligned qword update is one MMIO transaction. Publish a
; milestone by advancing the header count only after storing its timestamp.
#ZEN_TRAIL_BASE = #ZEN_RTC+$180
#ZEN_TRAIL_TAG = $5A545231
#MON_TRAIL_N = 7
#MON_TRAIL_OFF_PREV = 1
Global zenTrailCurrent.i,zenTrailPrevious.i,zenTrailBoot.i,zenTrailStarted.i
Procedure.i ZentajiTrailOwned(base.i)
 Protected header.q=PeekQ(base)
 ProcedureReturn Bool((header >> 32)=#ZEN_TRAIL_TAG And ((header >> 8) & $FFFFFF)>0 And (header & $FF)<=#MON_TRAIL_N)
EndProcedure
Procedure.i ZentajiTrailFree(base.i)
 Protected offset.i
 For offset=0 To 56 Step 8
  If PeekQ(base+offset)<>0 : ProcedureReturn 0 : EndIf
 Next
 ProcedureReturn 1
EndProcedure
Procedure ZentajiTrailBegin()
 Protected first.i=#ZEN_TRAIL_BASE,second.i=#ZEN_TRAIL_BASE+64
 Protected a.i,b.i,numberA.i,numberB.i
 If (PeekQ(#ZEN_RTC)&$FFFF)<>7 : ProcedureReturn : EndIf
 a=ZentajiTrailOwned(first) : b=ZentajiTrailOwned(second)
 If a=0 And ZentajiTrailFree(first)=0 : ProcedureReturn : EndIf
 If b=0 And ZentajiTrailFree(second)=0 : ProcedureReturn : EndIf
 zenTrailCurrent=first
 If a<>0
  zenTrailPrevious=first : zenTrailCurrent=second
 EndIf
 If b<>0
  numberA=(PeekQ(first) >> 8) & $FFFFFF
  numberB=(PeekQ(second) >> 8) & $FFFFFF
  If a=0 Or numberB=numberA+1 Or (numberB=1 And numberA=$FFFFFF)
   zenTrailPrevious=second : zenTrailCurrent=first
  ElseIf numberA<>numberB+1 And (numberA<>1 Or numberB<>$FFFFFF)
   zenTrailPrevious=0 : zenTrailCurrent=0 : ProcedureReturn
  EndIf
 EndIf
 zenTrailBoot=1
 If zenTrailPrevious<>0
  zenTrailBoot=((PeekQ(zenTrailPrevious) >> 8) & $FFFFFF)+1
  If zenTrailBoot>$FFFFFF : zenTrailBoot=1 : EndIf
 EndIf
 zenTrailStarted=millis()
 PokeQ(zenTrailCurrent,(#ZEN_TRAIL_TAG << 32) | (zenTrailBoot << 8))
EndProcedure
Procedure ZentajiTrailStep(code.i)
 Protected header.q,count.i
 If zenTrailCurrent=0 : ProcedureReturn : EndIf
 header=PeekQ(zenTrailCurrent) : count=header & $FF
 If count>=#MON_TRAIL_N : ProcedureReturn : EndIf
 PokeQ(zenTrailCurrent+8+count*8,(((millis()-zenTrailStarted)&$FFFFFFFF) << 16) | code)
 PokeQ(zenTrailCurrent,header+1)
EndProcedure
Procedure.i MonTrailValid(which.i)
 If which=#MON_TRAIL_OFF_PREV : ProcedureReturn Bool(zenTrailPrevious<>0) : EndIf
 ProcedureReturn Bool(zenTrailCurrent<>0)
EndProcedure
Procedure.i MonTrailCount(which.i)
 Protected base.i=zenTrailCurrent
 If which<>0 : base=zenTrailPrevious : EndIf
 If base=0 : ProcedureReturn 0 : EndIf
 ProcedureReturn PeekQ(base) & $FF
EndProcedure
Procedure.i MonTrailAt(which.i,index.i,ms.i)
 Protected base.i=zenTrailCurrent,entry.q
 If which<>0 : base=zenTrailPrevious : EndIf
 If base=0 Or index<0 Or index>=MonTrailCount(which) : ProcedureReturn 0 : EndIf
 entry=PeekQ(base+8+index*8)
 If ms<>0 : ProcedureReturn (entry >> 16) & $FFFFFFFF : EndIf
 ProcedureReturn entry & $FFFF
EndProcedure
Procedure.i MonTrailPrevBoot()
 If zenTrailPrevious=0 : ProcedureReturn 0 : EndIf
 ProcedureReturn (PeekQ(zenTrailPrevious) >> 8) & $FFFFFF
EndProcedure
Procedure.i MonTrailPrevFinished()
 ProcedureReturn Bool(MonTrailAt(1,MonTrailCount(1)-1,0)=$5A07)
EndProcedure
Procedure.i MonPhaseBoots()
 ProcedureReturn zenTrailBoot
EndProcedure
Procedure MonPhaseSay(code.i)
 Select code
  Case $5A01 : Print("ROM handoff and memory validated")
  Case $5A02 : Print("Display memory selected")
  Case $5A03 : Print("Console and UART attached")
  Case $5A04 : Print("Storage probed and settings checked")
  Case $5A05 : Print("Clock and entropy providers checked")
  Case $5A06 : Print("Network and input services initialized")
  Case $5A07 : Print("Monitor ready")
 EndSelect
EndProcedure

; SPDX-License-Identifier: MIT
; Real resident service boundary and lifetime. No synthetic device events.
XIncludeFile "Anvil/Hal/input_service_client.pbi"
Global nrChecks.i,nrFailure.i
Procedure NrCheck(actual.i,expected.i)
  nrChecks=nrChecks+1
  PokeI(#NIP_REPORT+112+nrChecks*16,actual)
  PokeI(#NIP_REPORT+120+nrChecks*16,expected)
  If actual<>expected And nrFailure=0 : nrFailure=nrChecks : EndIf
  PokeI(#NIP_REPORT+16,nrChecks) : PokeI(#NIP_REPORT+24,nrFailure)
EndProcedure
Procedure.i NrUnbound(op.i,context.i,request.i,bytes.i)
  ProcedureReturn -22406
EndProcedure
Procedure.i NrTouchUnbound()
  ProcedureReturn -100
EndProcedure
Procedure.i Main(services.i)
  Protected raw.i=@NrUnbound,touchQueued.i=@NrTouchUnbound,context.i,oldContext.i,rc.i,i.i
  Protected api.NativeInputApi,request.NativeInputOpenRequest,event.NativeInputEvent
  For i=0 To 8191 Step 8 : PokeI(#NIP_REPORT+i,0) : Next
  PokeI(#NIP_REPORT,$4E495231) : PokeI(#NIP_REPORT+8,1)
  If services=0 : ProcedureReturn 999 : EndIf
  raw=PeekI(services+16+39*8)
  touchQueued=PeekI(services+16+41*8)
  NrCheck(raw(0,0,0,32),-22400)
  NrCheck(raw(0,0,@api+1,32),-22400)
  NrCheck(raw(0,0,$7FFFFFFFFFFFFFE0,32),-22400)
  NrCheck(raw(0,0,$200000,32),-22400)
  NrCheck(raw(0,0,@api,31),-22400)
  NrCheck(raw(0,0,@api,32),0)
  NrCheck(api\magic,1313428273)
  NrCheck(api\major,1)
  NrCheck(api\minor,0)
  NrCheck(api\bytes,32)
  NrCheck(api\flags,7)
  request\required=8 : request\capabilities=98765
  NrCheck(raw(1,0,@request,40),-22400)
  NrCheck(request\capabilities,98765)
  NrCheck(AnvilInputBind(services,0),0)
  NrCheck(AnvilInputOpen(),0)
  NrCheck(Bool(AnvilInputContext()>0),1)
  NrCheck(Bool(AnvilInputCapabilities()>0 And AnvilInputCapabilities()<=7),1)
  NrCheck(Bool(AnvilInputWidth()>0 And AnvilInputWidth()<=8192),1)
  NrCheck(Bool(AnvilInputHeight()>0 And AnvilInputHeight()<=8192),1)
  context=AnvilInputContext()
  PokeI(#NIP_REPORT+64,AnvilInputCapabilities())
  PokeI(#NIP_REPORT+72,AnvilInputWidth()) : PokeI(#NIP_REPORT+80,AnvilInputHeight())
  NrCheck(AnvilInputOpen(),-22402)
  NrCheck(raw(2,context+1,@event,48),-22401)
  NrCheck(raw(2,context,0,48),-22400)
  NrCheck(raw(2,context,@event,47),-22400)
  NrCheck(raw(3,context,@event,0),-22400)
  NrCheck(touchQueued(),-103)
  NrCheck(AnvilInputFlush(),0)
  NrCheck(AnvilInputPoll(@event),1)
  NrCheck(event\kind,4)
  NrCheck(event\code,7)
  NrCheck(Bool(event\generation=AnvilInputGeneration()),1)
  NrCheck(NativeInputEventValid(@event),1)
  For i=1 To 64
    rc=AnvilInputPoll(@event)
    If rc<0 : NrCheck(rc,0) : Break : EndIf
    If rc=1
      If NativeInputEventValid(@event)=0 : NrCheck(-99,0) : Break : EndIf
      PokeI(#NIP_REPORT+88,PeekI(#NIP_REPORT+88)+1)
    EndIf
  Next
  NrCheck(AnvilInputClose(),0)
  NrCheck(AnvilInputContext(),0)
  NrCheck(raw(2,context,@event,48),-22401)
  NrCheck(AnvilInputClose(),0)
  oldContext=context
  NrCheck(AnvilInputOpen(),0)
  NrCheck(Bool(AnvilInputContext()>oldContext),1)
  NrCheck(touchQueued(),-103)
  ; Deliberately leave this scope open: kernel return must release it.
  PokeI(#NIP_REPORT+96,AnvilInputContext())
  ProcedureReturn nrFailure
EndProcedure

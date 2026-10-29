; SPDX-License-Identifier: MIT
; Real resident Vulkan loop. Scripted contact records are an explicit test mode;
; real touch is always polled through Anvil, never through a copied driver.
EnableFloatingPoint
XIncludeFile "Anvil/Graphics/neon_retained_ui.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_retained.pbi"
XIncludeFile "Anvil/Graphics/neon_service_touch.pbi"
XIncludeFile "Anvil/Graphics/neon_service_version.pbi"
Procedure.i NslNoClock()
  ProcedureReturn -1
EndProcedure
Procedure.i NslNoText(x.i,y.i,text.i,colour.i,pixels.i,background.i)
  ProcedureReturn -1
EndProcedure
Procedure.i NslNoEnd()
  ProcedureReturn -1
EndProcedure
Global nslClock.i=@NslNoClock,nslText.i=@NslNoText,nslFrameEnd.i=@NslNoEnd
Global Dim nslArena.q[4096]
Global nslFailure.i,nslStage.i
Procedure.i NslStep(status.i)
  nslStage=nslStage+1
  If status<>0 And nslFailure=0
    nslFailure=nslStage
    PokeI(#NSL_REPORT+16,nslFailure) : PokeI(#NSL_REPORT+24,status)
  EndIf
  ProcedureReturn status
EndProcedure
Procedure.i Main(services.i)
  Define i.i,rc.i,font.i,button.i,frames.i,ends.i,began.i,frameStart.i,now.i
  Define touchResult.i,drained.i,eventId.i,eventType.i,eventTag.i,scriptEvents.i,realEvents.i
  Define event.AnvilTouchEvent
  For i=0 To 4095 Step 8 : PokeI(#NSL_REPORT+i,0) : Next
  PokeI(#NSL_REPORT,$4E534C31) : PokeI(#NSL_REPORT+8,1)
  rc=NeonServiceBind(services,#NEON_SERVICE_VULKAN | #NEON_SERVICE_FONT_REFS)
  If rc<>0
    NeonServiceBindingMessage(services,rc,#NSL_REPORT+2048,192)
    If services<>0 And (services & 7)=0
      If (PeekL(services)&$FFFFFFFF)=$53564E41 And PeekL(services+4)=1 And PeekL(services+12)>30
        nslText=PeekI(services+16+30*8) : nslFrameEnd=PeekI(services+16+28*8)
        nslText(10,140,#NSL_REPORT+2048,$FFFFFFFF,16,$FF000000) : nslFrameEnd()
      EndIf
    EndIf
    NslStep(rc) : ProcedureReturn nslFailure
  EndIf
  nslClock=PeekI(services+16+11*8)
  If NslStep(NeonServiceOpen())<>0 : ProcedureReturn nslFailure : EndIf
  PokeI(#NSL_REPORT+32,NeonServiceContext())
  font=NeonServiceFontRegister(4,0,24)
  If font<4 : NslStep(font) : ProcedureReturn nslFailure : EndIf
  If NslStep(NeonRetainedConfigure(@nslArena[0],32768,16,128))<>0 : ProcedureReturn nslFailure : EndIf
  If NslStep(NeonServiceRetainedInstall())<>0 : ProcedureReturn nslFailure : EndIf
  If NslStep(NeonRetainedViewport(0.0,0.0,MathFFromInt(NeonServiceWidth()),MathFFromInt(NeonServiceHeight()),MathFFromInt(NeonServiceWidth()),MathFFromInt(NeonServiceHeight())))<>0 : ProcedureReturn nslFailure : EndIf
  If NslStep(NeonRetainedFontSet(font))<>0 : ProcedureReturn nslFailure : EndIf
  If NeonRetainedAddLabel(1,60.0,60.0,"Neon on Anvil - live application loop")=0 : NslStep(-1) : ProcedureReturn nslFailure : EndIf
  button=NeonRetainedAddButton(2,60.0,140.0,360.0,64.0,"Start",0,0)
  If button=0 : NslStep(-1) : ProcedureReturn nslFailure : EndIf
  touchResult=NeonServiceTouchBind(services) : PokeI(#NSL_REPORT+40,touchResult)
  If NslStep(touchResult)<>0 : ProcedureReturn nslFailure : EndIf
  began=nslClock()
  If began<0 : NslStep(began) : ProcedureReturn nslFailure : EndIf
  For i=0 To 89
    frameStart=nslClock()
    If frameStart<began Or frameStart-began>6000000 : NslStep(-2) : Break : EndIf
    CompilerIf #NSL_SCRIPTED_TEST=1
    If i=10 Or i=12 Or i=13 Or i=20 Or i=21 Or i=22 Or i=23 Or i=30 Or i=40 Or i=41 Or i=45 Or i=46
      event\x=200 : event\y=170 : event\id=7 : event\pressure=64 : event\reserved=0
      event\ticks=i : event\state=#HW_TOUCH_UP
      If i=12 Or i=20 : event\state=#HW_TOUCH_DOWN : EndIf
      If i=13 : event\state=#HW_TOUCH_CANCEL : EndIf
      If i=21 : event\id=9 : EndIf
      If i=22 : event\state=#HW_TOUCH_MOVE : EndIf
      If i=40 : event\x=900 : event\y=500 : event\state=#HW_TOUCH_DOWN : EndIf
      If i=45 : event\state=#HW_TOUCH_DOWN : EndIf
      If i=46 : event\x=600 : EndIf
      If NslStep(NeonServiceTouchFeed(@event))<>0 : Break : EndIf
      If NeonRetainedEventGet(@eventId,@eventType,@eventTag)<>0
        If eventId<>2 Or eventType<>1 : NslStep(-3) : Break : EndIf
        scriptEvents=scriptEvents+1
        If NslStep(NeonRetainedTextSet(button,"Started"))<>0 : Break : EndIf
      EndIf
    EndIf
    CompilerEndIf
    rc=NeonServiceTouchDrain(32)
    If rc<0 : NslStep(rc) : Break : EndIf
    drained=drained+rc
    If NeonRetainedEventGet(@eventId,@eventType,@eventTag)<>0
      realEvents=realEvents+1
      If eventId=2
        If NslStep(NeonRetainedTextSet(button,"Started"))<>0 : Break : EndIf
      EndIf
    EndIf
    If NslStep(NeonRetainedPrepare())<>0 : Break : EndIf
    If NslStep(NeonServiceBegin(0.02,0.04,0.08,1.0))<>0 : Break : EndIf
    If NslStep(NeonServiceBox(MathFFromInt(500+i*2),280.0,100.0,80.0,0.0,0.75,0.5,1.0))<>0 : Break : EndIf
    If NslStep(NeonRetainedDrawUI(1.0/30.0))<>0 : Break : EndIf
    rc=NeonServiceEnd() : PokeI(#NSL_REPORT+256+i*16,frameStart-began) : PokeI(#NSL_REPORT+264+i*16,rc)
    PokeI(#NSL_REPORT+2304+i*8,nslClock()-frameStart)
    If NslStep(rc)<>0 : Break : EndIf
    ends=ends+1 : frames=frames+1
    Repeat
      now=nslClock()
    Until now-frameStart>=33333 Or now<frameStart
    If now<frameStart : NslStep(-4) : Break : EndIf
  Next
  now=nslClock()
  PokeI(#NSL_REPORT+48,frames) : PokeI(#NSL_REPORT+56,ends)
  PokeI(#NSL_REPORT+64,drained) : PokeI(#NSL_REPORT+72,scriptEvents)
  PokeI(#NSL_REPORT+80,realEvents) : PokeI(#NSL_REPORT+88,now-began)
  PokeI(#NSL_REPORT+96,nslStage) : PokeI(#NSL_REPORT+104,#NSL_SCRIPTED_TEST)
  ; Return with a displayed final frame; the kernel captures before cleanup.
  ProcedureReturn nslFailure
EndProcedure

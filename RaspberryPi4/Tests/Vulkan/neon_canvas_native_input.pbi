; SPDX-License-Identifier: MIT
; Actual existing Neon widget scene, virtual canvas and physical DSI transfer.
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_canvas.pbi"
XIncludeFile "Anvil/Graphics/neon_canvas_input.pbi"
XIncludeFile "Anvil/Graphics/neon_legacy_keys.pbi"
XIncludeFile "Anvil/Hal/input_service_client.pbi"
Global NcdFailure.i,NcdChecks.i,NcdCanvas.NeonVkCanvas
Global Dim NcdScratch.q[240000]
Global Dim NcdClear.l[4]
Procedure NcdCheck(actual.i,expected.i)
  PokeI($E1C00400+NcdChecks*16,actual)
  PokeI($E1C00408+NcdChecks*16,expected)
  NcdChecks=NcdChecks+1
  If actual<>expected And NcdFailure=0 : NcdFailure=NcdChecks : EndIf
  PokeI($E1C00010,NcdFailure) : PokeI($E1C00018,NcdChecks)
EndProcedure

Global NlvServices.i,nlvInput.NeonCanvasInput,nlvEvent.NativeInputEvent
Global nlvCaps.i,nlvClicks.i,nlvSubmits.i,nlvFresh.i
Global Dim nlvText.a[64]
Global Dim nlvKinds.i[8]
Procedure.i NlvCompose()
  Protected key.i,hit.i
  If nlvFresh<>0 And nlvEvent\kind=#AIE_KEY_DOWN : key=NeonLegacyKeyFromNative(nlvEvent\code) : EndIf
  If nlvInput\pointer\cancelled<>0
    Neon_FocusID=0 : Neon_MousePrev=0
  EndIf
  NeonSetUIScale(1000)
  Neon_ChromeBeginFrame(MathFToInt(nlvInput\pointer\x),MathFToInt(nlvInput\pointer\y),nlvInput\pointer\down,nlvInput\input\wheel,key,nlvInput\input\scalar,16)
  Neon_Box(0,0,800,600,Neon_C_Bg)
  Neon_Panel(24,60,752,400,"live canvas input",Neon_C_Acc,26)
  hit=Neon_Button(80,120,180,44,"Activate",Bool(nlvClicks>0),1)
  If hit<>0 : nlvClicks=nlvClicks+1 : EndIf
  If (nlvCaps & #NUI_KEYBOARD)<>0
    Neon_Text(#NEON_FONT_UI,80,180,"KEYBOARD READY",Neon_C_Text)
  ElseIf (nlvCaps & #NUI_TOUCH)<>0
    Neon_Text(#NEON_FONT_UI,80,180,"TOUCH INPUT; NO KEYBOARD",Neon_C_Text)
  Else
    Neon_Text(#NEON_FONT_UI,80,180,"POINTER INPUT; NO KEYBOARD",Neon_C_Text)
  EndIf
  hit=Neon_TextInput(77,80,220,300,36,@nlvText[0],64,"Type here")
  If hit<>0 : nlvSubmits=nlvSubmits+1 : EndIf
  Neon_Box(400,220,80,36,$FF20A0F0)
  Neon_ChromeEndFrame()
  ProcedureReturn 0
EndProcedure
Procedure.i NcdFrame(dev.i,renderPass.i,framebuffer.i,base.i,pitch.i)
  Protected rc.i,i.i,scratch.i,ops.i,fallbacks.i,refusals.i,k.i,mismatches.i,t0.i,t1.i,t2.i,t3.i,started.i,elapsed.i,frames.i,events.i,polls.i,idles.i,dirty.i,done.i,openGeneration.i,openContext.i,closeRc.i,pollStart.i,pollTicks.i,renderTicks.i,mouseEvents.i,touchEvents.i
  Protected image.i,memory.i,view.i,target.NeonVkTargetInfo,point.NeonCanvasPoint
  PokeI($E1C00040,TickHz()) : PokeI($E1C00048,0)
  PokeI($E1C00050,0) : PokeI($E1C00058,800) : PokeI($E1C00060,600)
  PokeI($E1C000B0,4096000) : PokeI($E1C000E0,1920000)

  NcdCheck(NeonVkChromeRebind(framebuffer,1280,800,800,1280,pitch,90),0)
  NcdCheck(NeonVkCanvasInit(@NcdCanvas,SizeOf(NeonVkCanvas)),0)
  t0=Ticks()
  NcdCheck(NeonVkCanvasCreate(@NcdCanvas,800,600,1,@NcdScratch[0],1920000),0)
  PokeI($E1C000C0,Ticks()-t0)
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  image=NcdCanvas\image : memory=NcdCanvas\memory : view=NcdCanvas\view
  PokeI($E1C00068,NcdCanvas\viewport\x) : PokeI($E1C00070,NcdCanvas\viewport\y)
  PokeI($E1C00078,NcdCanvas\viewport\width) : PokeI($E1C00080,NcdCanvas\viewport\height)

  NcdCheck(NeonVkCanvasMapPoint(@NcdCanvas,640,400,@point),1)
  NcdCheck(point\xQ16,26214400)
  NcdCheck(point\yQ16,19660800)
  NcdCheck(DisplayAdopt(#NW_DSI_SCAN,#NW_SURFACE_PITCH,#NVWA_WIDTH,#NVWA_HEIGHT,32),1)
  scratch=@nwDmaScratch[0]+255 : scratch=scratch-(scratch%256)
  NcdCheck(DmaSetScratch(scratch,512),1)
  NcdCheck(DisplayDmaBind(),1)
  NcdCheck(DmaInit(),1)
  DisplayDmaReadback(1) : DisplayUseDma(1)
  NcdCheck(NeonVkChromeAsync(1),0)
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  nlvText[0]=76 : nlvText[1]=73 : nlvText[2]=86 : nlvText[3]=69
  NcdCheck(AnvilInputBind(NlvServices,0),0)
  NcdCheck(AnvilInputOpen(),0)
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  openContext=AnvilInputContext() : openGeneration=AnvilInputGeneration()
  nlvCaps=AnvilInputCapabilities()
  NcdCheck(Bool(openContext>0),1)
  NcdCheck(Bool(nlvCaps>0 And nlvCaps<=7),1)
  NcdCheck(AnvilInputWidth(),1280)
  NcdCheck(AnvilInputHeight(),800)
  NcdCheck(NeonCanvasInputConfigure(@nlvInput,@NcdCanvas\viewport),0)
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  PokeI($E1C000A0,nlvCaps) : PokeI($E1C000E8,openContext)
  started=Ticks() : dirty=1
  While Ticks()-started<5*TickHz() And frames<20 And events<128 And done=0
    nlvFresh=0 : pollStart=Ticks()
    rc=AnvilInputPoll(@nlvEvent)
    pollTicks=pollTicks+Ticks()-pollStart : polls=polls+1
    If rc<0 : NcdCheck(rc,0) : Goto NcdCleanup : EndIf
    If rc=1
      For k=0 To SizeOf(NativeInputEvent)-8 Step 8
        PokeI($E1C02800+events*48+k,PeekI(@nlvEvent+k))
      Next
      events=events+1 : nlvKinds[nlvEvent\kind]=nlvKinds[nlvEvent\kind]+1
      If nlvEvent\source=#NUI_SOURCE_MOUSE : mouseEvents=mouseEvents+1 : EndIf
      If nlvEvent\source=#NUI_SOURCE_TOUCH : touchEvents=touchEvents+1 : EndIf
      rc=NeonCanvasInputFeed(@nlvInput,@nlvEvent)
      If rc<>0 : NcdCheck(rc,0) : Goto NcdCleanup : EndIf
      nlvFresh=1
      If nlvInput\pointer\changed<>0 Or nlvInput\input\scalar<>0 Or nlvInput\input\wheel<>0 : dirty=1 : EndIf
      If nlvEvent\kind=#AIE_KEY_DOWN
        If NeonLegacyKeyFromNative(nlvEvent\code)<>0 : dirty=1 : EndIf
        If nlvEvent\code=#AIK_ESC : done=1 : EndIf
      EndIf
    Else
      idles=idles+1
    EndIf
    If dirty<>0
      i=frames : t0=Ticks()
  NcdCheck(NeonVkCanvasBegin(@NcdCanvas,@NcdClear[0]),0)
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  NcdCheck(NlvCompose(),0)
  NcdCheck(Bool(NeonVkChromeDrawCount()>=8),1)
  NcdCheck(NeonVkChromeError(),0)
  PokeI($E1C000B8,NeonVkChromeVertexCount())
  NcdCheck(NeonVkCanvasEnd(@NcdCanvas),0)
  t1=Ticks()
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  NcdCheck(NeonVkChromeBegin(@NcdClear[0]),0)
  NcdCheck(NeonVkCanvasDrawPassthrough(@NcdCanvas),0)
  NcdCheck(NeonVkChromeEnd(),0)
  NcdCheck(NeonVkChromeFinish(),0)
  NcdCheck(NeonVkChromePresentValidate(),1)
  t2=Ticks()
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  ops=DisplayDmaOps() : fallbacks=DisplayDmaFallbacks() : refusals=DisplayDmaRefusals()
  DisplayBlit(base,pitch,0,0,800,1280)
  NcdCheck(DisplayDmaOps()-ops,1)
  NcdCheck(DisplayDmaFallbacks()-fallbacks,0)
  NcdCheck(DisplayDmaRefusals()-refusals,0)
  NcdCheck(NeonVkChromePresentConsume(),1)
  t3=Ticks()
  PokeI($E1C00100+i*32,t0) : PokeI($E1C00108+i*32,t1)
  PokeI($E1C00110+i*32,t2) : PokeI($E1C00118+i*32,t3)
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
      renderTicks=renderTicks+Ticks()-t0
      frames=frames+1 : dirty=0
    EndIf
    rc=NeonCanvasInputIdle(@nlvInput)
    If rc<>0 : NcdCheck(rc,0) : Goto NcdCleanup : EndIf
    delayMicroseconds(1000)
  Wend
  elapsed=Ticks()-started
  PokeI($E1C00048,frames) : PokeI($E1C00050,events)
  PokeI($E1C000A8,AnvilInputGeneration())
  PokeI($E1C000D0,polls) : PokeI($E1C000D8,idles)
  PokeI($E1C02000,$4E4C4931) : PokeI($E1C02008,nlvClicks)
  PokeI($E1C02010,nlvSubmits) : PokeI($E1C02018,events)
  PokeI($E1C02020,nlvInput\pointer\down) : PokeI($E1C02028,Neon_FocusID)
  PokeI($E1C02030,openGeneration) : PokeI($E1C02038,nlvInput\input\generation)
  PokeI($E1C02040,nlvInput\pointer\lastTicks)
  PokeI($E1C02048,MathBitsOf(nlvInput\pointer\x)) : PokeI($E1C02050,MathBitsOf(nlvInput\pointer\y))
  PokeI($E1C02058,5*TickHz()) : PokeI($E1C02060,elapsed)
  PokeI($E1C02068,pollTicks) : PokeI($E1C02070,renderTicks)
  PokeI($E1C02078,128)
  For k=0 To 63 : PokeA($E1C02080+k,nlvText[k]) : Next
  PokeI($E1C020C0,nlvCaps) : PokeI($E1C020C8,20)
  PokeI($E1C020D0,frames) : PokeI($E1C020E8,events*48)
  For k=1 To 7 : PokeI($E1C02100+k*8,nlvKinds[k]) : Next
  PokeI($E1C02140,mouseEvents) : PokeI($E1C02148,touchEvents)
  NcdCheck(Bool(NcdCanvas\image=image),1)
  NcdCheck(Bool(NcdCanvas\memory=memory),1)
  NcdCheck(Bool(NcdCanvas\view=view),1)
  ; Compare the entire completed attachment/scanout directly. Three full
  ; checksum passes exceeded the bounded payload's watchdog on this board.
  For k=0 To 4095999 Step 8
    If PeekI(base+k)<>PeekI(#NW_DSI_SCAN+k) : mismatches=mismatches+1 : EndIf
  Next
  PokeI($E1C00088,512000) : PokeI($E1C00090,mismatches)
  NcdCheck(mismatches,0)
  closeRc=AnvilInputClose()
  NcdCheck(closeRc,0)
  NcdCheck(AnvilInputContext(),0)
  NcdCheck(NeonVkCanvasClose(@NcdCanvas),0)
  NcdCheck(NeonVkChromeImageSpriteAllocatedId(1),0)
  NcdCheck(AnvilVkFaultCode(),0)
  NcdCleanup:
  If AnvilInputContext()>0
    closeRc=AnvilInputClose()
    If closeRc<>0 And NcdFailure=0 : NcdFailure=9005 : PokeI($E1C00010,NcdFailure) : EndIf
  EndIf
  PokeI($E1C000F0,AnvilInputContext())
  PokeI($E1C020D8,closeRc) : PokeI($E1C020E0,AnvilInputContext())
  ; This fixture owns the final frame too. On failure, abandon only completed
  ; work and preserve a refusal rather than reporting a successful present.
  If NeonVkChromeFramePending()<>0 : NeonVkChromeFinish() : EndIf
  If NeonVkChromeFrameAbortable()<>0 : NeonVkChromeAbort() : EndIf
  If NeonVkChromePresentPending()<>0 : NeonVkChromePresentConsume() : EndIf
  If NcdCanvas\phase<>#NEON_VK_CANVAS_CLOSED
    rc=NeonVkCanvasClose(@NcdCanvas)
    If rc<>0 And NcdFailure=0 : NcdFailure=9001 : EndIf
  EndIf
  DisplayUseDma(0) : DisplayFlush()
  PokeI($E1C00098,AnvilVkFaultCount()) : PokeI($E1C000C8,AnvilVkFaultCode())
  ProcedureReturn NcdFailure
EndProcedure

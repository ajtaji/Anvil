; SPDX-License-Identifier: MIT
; Actual existing Neon widget scene, virtual canvas and physical DSI transfer.
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_canvas.pbi"
XIncludeFile "Anvil/Graphics/neon_canvas_input.pbi"
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

Global ncuInput.NeonCanvasInput,ncuEvent.NativeInputEvent,ncuClicks.i
Procedure.i NcuCompose()
  Protected hit.i,colour.i
  NeonSetUIScale(1000)
  Neon_ChromeBeginFrame(MathFToInt(ncuInput\pointer\x),MathFToInt(ncuInput\pointer\y),ncuInput\pointer\down,ncuInput\input\wheel,0,ncuInput\input\scalar,16)
  Neon_Box(0,0,800,600,Neon_C_Bg)
  Neon_Panel(24,60,752,400,"canvas input",Neon_C_Acc,26)
  hit=Neon_Button(80,120,180,44,"Capture test",Bool(ncuClicks>0),1)
  If hit<>0 : ncuClicks=ncuClicks+1 : EndIf
  colour=$FFCC3030
  If ncuClicks=1 : colour=$FFCCAA20 : EndIf
  If ncuClicks=2 : colour=$FF20A0F0 : EndIf
  Neon_Box(400,120,80,44,colour)
  Neon_ChromeEndFrame()
  ProcedureReturn 0
EndProcedure
Procedure.i NcdFrame(dev.i,renderPass.i,framebuffer.i,base.i,pitch.i)
  Protected rc.i,i.i,scratch.i,ops.i,fallbacks.i,refusals.i,k.i,mismatches.i,t0.i,t1.i,t2.i,t3.i
  Protected image.i,memory.i,view.i,target.NeonVkTargetInfo,point.NeonCanvasPoint
  PokeI($E1C00040,TickHz()) : PokeI($E1C00048,8)
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
  NcdCheck(NeonCanvasInputConfigure(@ncuInput,@NcdCanvas\viewport),0)
  i=0 : t0=Ticks()
  ncuEvent\kind=5 : ncuEvent\source=4 : ncuEvent\code=0 : ncuEvent\modifiers=0
  ncuEvent\x=50 : ncuEvent\y=189 : ncuEvent\buttons=1 : ncuEvent\value=0
  ncuEvent\ticks=1 : ncuEvent\generation=1 : ncuEvent\reserved=0
  NcdCheck(NeonCanvasInputFeed(@ncuInput,@ncuEvent),0)
  NcdCheck(NeonVkCanvasBegin(@NcdCanvas,@NcdClear[0]),0)
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  NcdCheck(NcuCompose(),0)
  NcdCheck(ncuClicks,0)
  NcdCheck(ncuInput\pointer\pressed,0)
  NcdCheck(ncuInput\pointer\released,0)
  NcdCheck(Neon_MouseReleased,0)
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
  i=1 : t0=Ticks()
  ncuEvent\kind=5 : ncuEvent\source=4 : ncuEvent\code=0 : ncuEvent\modifiers=0
  ncuEvent\x=320 : ncuEvent\y=189 : ncuEvent\buttons=1 : ncuEvent\value=1
  ncuEvent\ticks=2 : ncuEvent\generation=1 : ncuEvent\reserved=0
  NcdCheck(NeonCanvasInputFeed(@ncuInput,@ncuEvent),0)
  NcdCheck(NeonVkCanvasBegin(@NcdCanvas,@NcdClear[0]),0)
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  NcdCheck(NcuCompose(),0)
  NcdCheck(ncuClicks,0)
  NcdCheck(ncuInput\pointer\pressed,0)
  NcdCheck(ncuInput\pointer\released,0)
  NcdCheck(Neon_MouseReleased,0)
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
  i=2 : t0=Ticks()
  ncuEvent\kind=5 : ncuEvent\source=4 : ncuEvent\code=0 : ncuEvent\modifiers=0
  ncuEvent\x=320 : ncuEvent\y=189 : ncuEvent\buttons=0 : ncuEvent\value=2
  ncuEvent\ticks=3 : ncuEvent\generation=1 : ncuEvent\reserved=0
  NcdCheck(NeonCanvasInputFeed(@ncuInput,@ncuEvent),0)
  NcdCheck(NeonVkCanvasBegin(@NcdCanvas,@NcdClear[0]),0)
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  NcdCheck(NcuCompose(),0)
  NcdCheck(ncuClicks,0)
  NcdCheck(ncuInput\pointer\pressed,0)
  NcdCheck(ncuInput\pointer\released,0)
  NcdCheck(Neon_MouseReleased,0)
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
  i=3 : t0=Ticks()
  ncuEvent\kind=5 : ncuEvent\source=4 : ncuEvent\code=0 : ncuEvent\modifiers=0
  ncuEvent\x=320 : ncuEvent\y=189 : ncuEvent\buttons=1 : ncuEvent\value=0
  ncuEvent\ticks=4 : ncuEvent\generation=1 : ncuEvent\reserved=0
  NcdCheck(NeonCanvasInputFeed(@ncuInput,@ncuEvent),0)
  NcdCheck(NeonVkCanvasBegin(@NcdCanvas,@NcdClear[0]),0)
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  NcdCheck(NcuCompose(),0)
  NcdCheck(ncuClicks,1)
  NcdCheck(ncuInput\pointer\pressed,1)
  NcdCheck(ncuInput\pointer\released,0)
  NcdCheck(Neon_MouseReleased,0)
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
  i=4 : t0=Ticks()
  ncuEvent\kind=5 : ncuEvent\source=4 : ncuEvent\code=0 : ncuEvent\modifiers=0
  ncuEvent\x=50 : ncuEvent\y=189 : ncuEvent\buttons=1 : ncuEvent\value=1
  ncuEvent\ticks=5 : ncuEvent\generation=1 : ncuEvent\reserved=0
  NcdCheck(NeonCanvasInputFeed(@ncuInput,@ncuEvent),0)
  NcdCheck(NeonVkCanvasBegin(@NcdCanvas,@NcdClear[0]),0)
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  NcdCheck(NcuCompose(),0)
  NcdCheck(ncuClicks,1)
  NcdCheck(ncuInput\pointer\pressed,0)
  NcdCheck(ncuInput\pointer\released,0)
  NcdCheck(Neon_MouseReleased,0)
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
  i=5 : t0=Ticks()
  ncuEvent\kind=5 : ncuEvent\source=4 : ncuEvent\code=0 : ncuEvent\modifiers=0
  ncuEvent\x=50 : ncuEvent\y=189 : ncuEvent\buttons=0 : ncuEvent\value=2
  ncuEvent\ticks=6 : ncuEvent\generation=1 : ncuEvent\reserved=0
  NcdCheck(NeonCanvasInputFeed(@ncuInput,@ncuEvent),0)
  NcdCheck(NeonVkCanvasBegin(@NcdCanvas,@NcdClear[0]),0)
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  NcdCheck(NcuCompose(),0)
  NcdCheck(ncuClicks,1)
  NcdCheck(ncuInput\pointer\pressed,0)
  NcdCheck(ncuInput\pointer\released,1)
  NcdCheck(Neon_MouseReleased,1)
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
  i=6 : t0=Ticks()
  ncuEvent\kind=5 : ncuEvent\source=4 : ncuEvent\code=0 : ncuEvent\modifiers=0
  ncuEvent\x=320 : ncuEvent\y=189 : ncuEvent\buttons=1 : ncuEvent\value=0
  ncuEvent\ticks=7 : ncuEvent\generation=1 : ncuEvent\reserved=0
  NcdCheck(NeonCanvasInputFeed(@ncuInput,@ncuEvent),0)
  NcdCheck(NeonVkCanvasBegin(@NcdCanvas,@NcdClear[0]),0)
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  NcdCheck(NcuCompose(),0)
  NcdCheck(ncuClicks,2)
  NcdCheck(ncuInput\pointer\pressed,1)
  NcdCheck(ncuInput\pointer\released,0)
  NcdCheck(Neon_MouseReleased,0)
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
  i=7 : t0=Ticks()
  ncuEvent\kind=5 : ncuEvent\source=4 : ncuEvent\code=0 : ncuEvent\modifiers=0
  ncuEvent\x=50 : ncuEvent\y=189 : ncuEvent\buttons=0 : ncuEvent\value=2
  ncuEvent\ticks=8 : ncuEvent\generation=1 : ncuEvent\reserved=0
  NcdCheck(NeonCanvasInputFeed(@ncuInput,@ncuEvent),0)
  NcdCheck(NeonVkCanvasBegin(@NcdCanvas,@NcdClear[0]),0)
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  NcdCheck(NcuCompose(),0)
  NcdCheck(ncuClicks,2)
  NcdCheck(ncuInput\pointer\pressed,0)
  NcdCheck(ncuInput\pointer\released,1)
  NcdCheck(Neon_MouseReleased,1)
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
  NcdCheck(NeonVkCanvasClose(@NcdCanvas),0)
  NcdCheck(NeonVkChromeImageSpriteAllocatedId(1),0)
  NcdCheck(AnvilVkFaultCode(),0)
  NcdCleanup:
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

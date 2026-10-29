; SPDX-License-Identifier: MIT
; Actual existing Neon widget scene, virtual canvas and physical DSI transfer.
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_canvas.pbi"
XIncludeFile "Anvil/Graphics/neon_canvas_input.pbi"
XIncludeFile "Anvil/Graphics/neon_legacy_keys.pbi"
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

Global nkbInput.NeonCanvasInput,nkbEvent.NativeInputEvent,nkbSubmits.i
Global Dim nkbText.a[64]
Procedure.i NkbCompose()
  Protected key.i,submitted.i,colour.i
  If nkbEvent\kind=#AIE_KEY_DOWN : key=NeonLegacyKeyFromNative(nkbEvent\code) : EndIf
  NeonSetUIScale(1000)
  Neon_ChromeBeginFrame(MathFToInt(nkbInput\pointer\x),MathFToInt(nkbInput\pointer\y),nkbInput\pointer\down,nkbInput\input\wheel,key,nkbInput\input\scalar,16)
  Neon_Box(0,0,800,600,Neon_C_Bg)
  Neon_Panel(24,60,752,400,"canvas keyboard",Neon_C_Acc,26)
  submitted=Neon_TextInput(77,80,220,300,36,@nkbText[0],64,"Type here")
  If submitted<>0 : nkbSubmits=nkbSubmits+1 : EndIf
  colour=$FFCC3030
  If nkbSubmits=1 And nkbText[0]=90 And nkbText[1]=65 And nkbText[2]=0 : colour=$FF20A0F0 : EndIf
  Neon_Box(400,220,80,36,colour)
  Neon_ChromeEndFrame()
  ProcedureReturn 0
EndProcedure
Procedure.i NcdFrame(dev.i,renderPass.i,framebuffer.i,base.i,pitch.i)
  Protected rc.i,i.i,scratch.i,ops.i,fallbacks.i,refusals.i,k.i,mismatches.i,t0.i,t1.i,t2.i,t3.i
  Protected image.i,memory.i,view.i,target.NeonVkTargetInfo,point.NeonCanvasPoint
  PokeI($E1C00040,TickHz()) : PokeI($E1C00048,13)
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
  NcdCheck(NeonCanvasInputConfigure(@nkbInput,@NcdCanvas\viewport),0)
  nkbText[0]=65 : nkbText[1]=66
  NcdCheck(NeonLegacyKeyFromNative(-1),0)
  NcdCheck(NeonLegacyKeyFromNative(0),0)
  NcdCheck(NeonLegacyKeyFromNative(1),13)
  NcdCheck(NeonLegacyKeyFromNative(2),8)
  NcdCheck(NeonLegacyKeyFromNative(3),127)
  NcdCheck(NeonLegacyKeyFromNative(4),256)
  NcdCheck(NeonLegacyKeyFromNative(5),257)
  NcdCheck(NeonLegacyKeyFromNative(6),260)
  NcdCheck(NeonLegacyKeyFromNative(7),261)
  NcdCheck(NeonLegacyKeyFromNative(8),9)
  NcdCheck(NeonLegacyKeyFromNative(9),27)
  NcdCheck(NeonLegacyKeyFromNative(10),0)
  NcdCheck(NeonLegacyKeyFromNative(11),258)
  NcdCheck(NeonLegacyKeyFromNative(12),259)
  NcdCheck(NeonLegacyKeyFromNative(13),0)
  NcdCheck(NeonLegacyKeyFromNative(14),0)
  NcdCheck(NeonLegacyKeyFromNative(15),0)
  NcdCheck(NeonLegacyKeyFromNative(16),0)
  NcdCheck(NeonLegacyKeyFromNative(65),0)
  i=0 : t0=Ticks()
  nkbEvent\kind=5 : nkbEvent\source=4 : nkbEvent\code=0 : nkbEvent\modifiers=0
  nkbEvent\x=320 : nkbEvent\y=317 : nkbEvent\buttons=1 : nkbEvent\value=0
  nkbEvent\ticks=1 : nkbEvent\generation=1 : nkbEvent\reserved=0
  NcdCheck(NeonCanvasInputFeed(@nkbInput,@nkbEvent),0)
  NcdCheck(NeonVkCanvasBegin(@NcdCanvas,@NcdClear[0]),0)
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  NcdCheck(NkbCompose(),0)
  NcdCheck(nkbText[0],65)
  NcdCheck(nkbText[1],66)
  NcdCheck(nkbText[2],0)
  NcdCheck(Neon_CaretPos(77),0)
  NcdCheck(Neon_FocusID,77)
  NcdCheck(nkbSubmits,0)
  NcdCheck(Bool(NeonVkChromeDrawCount()>=8),1)
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
  nkbEvent\kind=5 : nkbEvent\source=4 : nkbEvent\code=0 : nkbEvent\modifiers=0
  nkbEvent\x=320 : nkbEvent\y=317 : nkbEvent\buttons=0 : nkbEvent\value=2
  nkbEvent\ticks=2 : nkbEvent\generation=1 : nkbEvent\reserved=0
  NcdCheck(NeonCanvasInputFeed(@nkbInput,@nkbEvent),0)
  NcdCheck(NeonVkCanvasBegin(@NcdCanvas,@NcdClear[0]),0)
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  NcdCheck(NkbCompose(),0)
  NcdCheck(nkbText[0],65)
  NcdCheck(nkbText[1],66)
  NcdCheck(nkbText[2],0)
  NcdCheck(Neon_CaretPos(77),0)
  NcdCheck(Neon_FocusID,77)
  NcdCheck(nkbSubmits,0)
  NcdCheck(Bool(NeonVkChromeDrawCount()>=8),1)
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
  nkbEvent\kind=2 : nkbEvent\source=1 : nkbEvent\code=7 : nkbEvent\modifiers=0
  nkbEvent\x=-1 : nkbEvent\y=-1 : nkbEvent\buttons=0 : nkbEvent\value=0
  nkbEvent\ticks=3 : nkbEvent\generation=1 : nkbEvent\reserved=0
  NcdCheck(NeonCanvasInputFeed(@nkbInput,@nkbEvent),0)
  NcdCheck(NeonVkCanvasBegin(@NcdCanvas,@NcdClear[0]),0)
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  NcdCheck(NkbCompose(),0)
  NcdCheck(nkbText[0],65)
  NcdCheck(nkbText[1],66)
  NcdCheck(nkbText[2],0)
  NcdCheck(Neon_CaretPos(77),2)
  NcdCheck(Neon_FocusID,77)
  NcdCheck(nkbSubmits,0)
  NcdCheck(Bool(NeonVkChromeDrawCount()>=8),1)
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
  nkbEvent\kind=2 : nkbEvent\source=1 : nkbEvent\code=4 : nkbEvent\modifiers=0
  nkbEvent\x=-1 : nkbEvent\y=-1 : nkbEvent\buttons=0 : nkbEvent\value=0
  nkbEvent\ticks=4 : nkbEvent\generation=1 : nkbEvent\reserved=0
  NcdCheck(NeonCanvasInputFeed(@nkbInput,@nkbEvent),0)
  NcdCheck(NeonVkCanvasBegin(@NcdCanvas,@NcdClear[0]),0)
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  NcdCheck(NkbCompose(),0)
  NcdCheck(nkbText[0],65)
  NcdCheck(nkbText[1],66)
  NcdCheck(nkbText[2],0)
  NcdCheck(Neon_CaretPos(77),1)
  NcdCheck(Neon_FocusID,77)
  NcdCheck(nkbSubmits,0)
  NcdCheck(Bool(NeonVkChromeDrawCount()>=8),1)
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
  nkbEvent\kind=1 : nkbEvent\source=1 : nkbEvent\code=88 : nkbEvent\modifiers=0
  nkbEvent\x=-1 : nkbEvent\y=-1 : nkbEvent\buttons=0 : nkbEvent\value=0
  nkbEvent\ticks=5 : nkbEvent\generation=1 : nkbEvent\reserved=0
  NcdCheck(NeonCanvasInputFeed(@nkbInput,@nkbEvent),0)
  NcdCheck(NeonVkCanvasBegin(@NcdCanvas,@NcdClear[0]),0)
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  NcdCheck(NkbCompose(),0)
  NcdCheck(nkbText[0],65)
  NcdCheck(nkbText[1],88)
  NcdCheck(nkbText[2],66)
  NcdCheck(nkbText[3],0)
  NcdCheck(Neon_CaretPos(77),2)
  NcdCheck(Neon_FocusID,77)
  NcdCheck(nkbSubmits,0)
  NcdCheck(Bool(NeonVkChromeDrawCount()>=8),1)
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
  nkbEvent\kind=2 : nkbEvent\source=1 : nkbEvent\code=2 : nkbEvent\modifiers=0
  nkbEvent\x=-1 : nkbEvent\y=-1 : nkbEvent\buttons=0 : nkbEvent\value=0
  nkbEvent\ticks=6 : nkbEvent\generation=1 : nkbEvent\reserved=0
  NcdCheck(NeonCanvasInputFeed(@nkbInput,@nkbEvent),0)
  NcdCheck(NeonVkCanvasBegin(@NcdCanvas,@NcdClear[0]),0)
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  NcdCheck(NkbCompose(),0)
  NcdCheck(nkbText[0],65)
  NcdCheck(nkbText[1],66)
  NcdCheck(nkbText[2],0)
  NcdCheck(Neon_CaretPos(77),1)
  NcdCheck(Neon_FocusID,77)
  NcdCheck(nkbSubmits,0)
  NcdCheck(Bool(NeonVkChromeDrawCount()>=8),1)
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
  nkbEvent\kind=2 : nkbEvent\source=1 : nkbEvent\code=3 : nkbEvent\modifiers=0
  nkbEvent\x=-1 : nkbEvent\y=-1 : nkbEvent\buttons=0 : nkbEvent\value=0
  nkbEvent\ticks=7 : nkbEvent\generation=1 : nkbEvent\reserved=0
  NcdCheck(NeonCanvasInputFeed(@nkbInput,@nkbEvent),0)
  NcdCheck(NeonVkCanvasBegin(@NcdCanvas,@NcdClear[0]),0)
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  NcdCheck(NkbCompose(),0)
  NcdCheck(nkbText[0],65)
  NcdCheck(nkbText[1],0)
  NcdCheck(Neon_CaretPos(77),1)
  NcdCheck(Neon_FocusID,77)
  NcdCheck(nkbSubmits,0)
  NcdCheck(Bool(NeonVkChromeDrawCount()>=8),1)
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
  nkbEvent\kind=2 : nkbEvent\source=1 : nkbEvent\code=6 : nkbEvent\modifiers=0
  nkbEvent\x=-1 : nkbEvent\y=-1 : nkbEvent\buttons=0 : nkbEvent\value=0
  nkbEvent\ticks=8 : nkbEvent\generation=1 : nkbEvent\reserved=0
  NcdCheck(NeonCanvasInputFeed(@nkbInput,@nkbEvent),0)
  NcdCheck(NeonVkCanvasBegin(@NcdCanvas,@NcdClear[0]),0)
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  NcdCheck(NkbCompose(),0)
  NcdCheck(nkbText[0],65)
  NcdCheck(nkbText[1],0)
  NcdCheck(Neon_CaretPos(77),0)
  NcdCheck(Neon_FocusID,77)
  NcdCheck(nkbSubmits,0)
  NcdCheck(Bool(NeonVkChromeDrawCount()>=8),1)
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
  i=8 : t0=Ticks()
  nkbEvent\kind=1 : nkbEvent\source=1 : nkbEvent\code=90 : nkbEvent\modifiers=0
  nkbEvent\x=-1 : nkbEvent\y=-1 : nkbEvent\buttons=0 : nkbEvent\value=0
  nkbEvent\ticks=9 : nkbEvent\generation=1 : nkbEvent\reserved=0
  NcdCheck(NeonCanvasInputFeed(@nkbInput,@nkbEvent),0)
  NcdCheck(NeonVkCanvasBegin(@NcdCanvas,@NcdClear[0]),0)
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  NcdCheck(NkbCompose(),0)
  NcdCheck(nkbText[0],90)
  NcdCheck(nkbText[1],65)
  NcdCheck(nkbText[2],0)
  NcdCheck(Neon_CaretPos(77),1)
  NcdCheck(Neon_FocusID,77)
  NcdCheck(nkbSubmits,0)
  NcdCheck(Bool(NeonVkChromeDrawCount()>=8),1)
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
  i=9 : t0=Ticks()
  nkbEvent\kind=2 : nkbEvent\source=1 : nkbEvent\code=5 : nkbEvent\modifiers=0
  nkbEvent\x=-1 : nkbEvent\y=-1 : nkbEvent\buttons=0 : nkbEvent\value=0
  nkbEvent\ticks=10 : nkbEvent\generation=1 : nkbEvent\reserved=0
  NcdCheck(NeonCanvasInputFeed(@nkbInput,@nkbEvent),0)
  NcdCheck(NeonVkCanvasBegin(@NcdCanvas,@NcdClear[0]),0)
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  NcdCheck(NkbCompose(),0)
  NcdCheck(nkbText[0],90)
  NcdCheck(nkbText[1],65)
  NcdCheck(nkbText[2],0)
  NcdCheck(Neon_CaretPos(77),2)
  NcdCheck(Neon_FocusID,77)
  NcdCheck(nkbSubmits,0)
  NcdCheck(Bool(NeonVkChromeDrawCount()>=8),1)
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
  i=10 : t0=Ticks()
  nkbEvent\kind=2 : nkbEvent\source=1 : nkbEvent\code=1 : nkbEvent\modifiers=0
  nkbEvent\x=-1 : nkbEvent\y=-1 : nkbEvent\buttons=0 : nkbEvent\value=0
  nkbEvent\ticks=11 : nkbEvent\generation=1 : nkbEvent\reserved=0
  NcdCheck(NeonCanvasInputFeed(@nkbInput,@nkbEvent),0)
  NcdCheck(NeonVkCanvasBegin(@NcdCanvas,@NcdClear[0]),0)
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  NcdCheck(NkbCompose(),0)
  NcdCheck(nkbText[0],90)
  NcdCheck(nkbText[1],65)
  NcdCheck(nkbText[2],0)
  NcdCheck(Neon_CaretPos(77),2)
  NcdCheck(Neon_FocusID,77)
  NcdCheck(nkbSubmits,1)
  NcdCheck(Bool(NeonVkChromeDrawCount()>=8),1)
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
  i=11 : t0=Ticks()
  nkbEvent\kind=2 : nkbEvent\source=1 : nkbEvent\code=9 : nkbEvent\modifiers=0
  nkbEvent\x=-1 : nkbEvent\y=-1 : nkbEvent\buttons=0 : nkbEvent\value=0
  nkbEvent\ticks=12 : nkbEvent\generation=1 : nkbEvent\reserved=0
  NcdCheck(NeonCanvasInputFeed(@nkbInput,@nkbEvent),0)
  NcdCheck(NeonVkCanvasBegin(@NcdCanvas,@NcdClear[0]),0)
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  NcdCheck(NkbCompose(),0)
  NcdCheck(nkbText[0],90)
  NcdCheck(nkbText[1],65)
  NcdCheck(nkbText[2],0)
  NcdCheck(Neon_CaretPos(77),2)
  NcdCheck(Neon_FocusID,0)
  NcdCheck(nkbSubmits,1)
  NcdCheck(Bool(NeonVkChromeDrawCount()>=8),1)
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
  i=12 : t0=Ticks()
  nkbEvent\kind=1 : nkbEvent\source=1 : nkbEvent\code=81 : nkbEvent\modifiers=0
  nkbEvent\x=-1 : nkbEvent\y=-1 : nkbEvent\buttons=0 : nkbEvent\value=0
  nkbEvent\ticks=13 : nkbEvent\generation=1 : nkbEvent\reserved=0
  NcdCheck(NeonCanvasInputFeed(@nkbInput,@nkbEvent),0)
  NcdCheck(NeonVkCanvasBegin(@NcdCanvas,@NcdClear[0]),0)
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  NcdCheck(NkbCompose(),0)
  NcdCheck(nkbText[0],90)
  NcdCheck(nkbText[1],65)
  NcdCheck(nkbText[2],0)
  NcdCheck(Neon_CaretPos(77),2)
  NcdCheck(Neon_FocusID,0)
  NcdCheck(nkbSubmits,1)
  NcdCheck(Bool(NeonVkChromeDrawCount()>=8),1)
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

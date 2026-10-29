; SPDX-License-Identifier: MIT
; Composed resident Vulkan application. Native input and scripted injection are explicit modes.
EnableFloatingPoint
XIncludeFile "Anvil/Graphics/neon_retained_ui.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_mapping.pbi"
XIncludeFile "Anvil/Graphics/neon_service_sprite.pbi"
XIncludeFile "Anvil/Graphics/neon_service_particles.pbi"
XIncludeFile "Anvil/Graphics/neon_service_retained.pbi"
XIncludeFile "Anvil/Graphics/neon_chrome_menu.pbi"
XIncludeFile "Anvil/Graphics/neon_service_chrome_menu.pbi"
XIncludeFile "Anvil/Graphics/neon_chrome_tabs.pbi"
XIncludeFile "Anvil/Graphics/neon_service_chrome_tabs.pbi"
XIncludeFile "Anvil/Graphics/neon_chrome_edit.pbi"
XIncludeFile "Anvil/Graphics/neon_service_chrome_edit.pbi"
XIncludeFile "Anvil/Graphics/neon_chrome_list.pbi"
XIncludeFile "Anvil/Graphics/neon_service_chrome_list.pbi"
XIncludeFile "Anvil/Graphics/neon_service_pointer.pbi"
CompilerIf #NCA_NATIVE=1
XIncludeFile "Anvil/Hal/input_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_native_input.pbi"
Global ncaNative.NeonNativeInputState,ncaNativeEvent.NativeInputEvent
CompilerIf #NCA_RETRO=1
XIncludeFile "Anvil/Graphics/neon_service_targets.pbi"
XIncludeFile "Anvil/Graphics/neon_canvas_input.pbi"
Global ncaCanvasInput.NeonCanvasInput,ncaViewport.NeonCanvasViewport,ncaTarget.i

CompilerEndIf

Global Dim ncaClipboard.a[256]
CompilerEndIf
CompilerIf #NCA_ASSETS=1
#CRC_POLY=$EDB88320
XIncludeFile "Anvil/Core/crc.pbi"
XIncludeFile "Anvil/Graphics/neon_service_png.pbi"
XIncludeFile "Anvil/Graphics/neon_service_font.pbi"
XIncludeFile "Anvil/Graphics/neon_service_font_spacing.pbi"
XIncludeFile "Anvil/Graphics/neon_service_font_snap.pbi"
XIncludeFile "Anvil/Graphics/neon_service_font_controls.pbi"
XIncludeFile "Anvil/Graphics/neon_service_font_derive.pbi"
Global Dim ncaFontSource.q[131072]
Global Dim ncaPngSource.q[2048]
Global Dim ncaPngRgba.q[1024]
Global Dim ncaPngWork.q[8192]
Global ncaPngTexture.i,ncaShowFont.i,ncaFractionFont.i,ncaPngWidth.i,ncaPngHeight.i
CompilerEndIf
Global ncaPointer.NeonPointerState,ncaTestPointer.NeonPointerState
Global ncaEvent.AnvilTouchEvent,ncaMockEvent.AnvilTouchEvent
Global ncaMenu.NeonChromeMenuState,ncaTabs.NeonChromeTabState,ncaEdit.NeonChromeEditState,ncaList.NeonChromeListState
Global ncaScroll.NeonChromeScrollState
Global ncaTabConfig.NeonChromeTabConfig,ncaEditConfig.NeonChromeEditConfig,ncaListConfig.NeonChromeListConfig,ncaEditEvent.NeonChromeEditInput
Global Dim ncaMenuArena.q[2048]
Global Dim ncaTabArena.q[1024]
Global Dim ncaEditArena.q[256]
Global Dim ncaListArena.q[2048]
Global Dim ncaRetainedArena.q[4096]
Global Dim ncaPixels.l[16]
Global Dim ncaParticles.NeonParticleRecord[32]
Global Dim ncaLines.f[16]
Global Dim ncaMockServices.q[50]
Global ncaRunning.i=1,ncaPhase.f
Global ncaEndStart.i
Global ncaFrame.i,ncaBoxCount.i
Global ncaFailure.i,ncaStage.i,ncaChecks.i,ncaCoreFailure.i,ncaMockResult.i,ncaFlushResult.i,ncaMockBusy.i
Global ncaFont.i,ncaSmall.i,ncaButton.i,ncaToggle.i,ncaSlider.i,ncaTexture.i
Global ncaOwner.i,ncaCapture.i,ncaSelected.i=1,ncaButtonEvents.i,ncaToggleEvents.i,ncaListEvents.i,ncaMenuEvents.i,ncaBlockedPresses.i
Global ncaKey.i,ncaScalar.i,ncaCtrl.i,ncaWheel.i,ncaScriptRecords.i,ncaRealRecords.i,ncaCloses.i,ncaPins.i,ncaClosedMask.i
CompilerIf #NCA_RETRO=1
Procedure.i NcaRetroFeed()
 Protected i.i,rc.i
 rc=NeonCanvasInputFeed(@ncaCanvasInput,@ncaNativeEvent)
 If rc<>0 : ProcedureReturn rc : EndIf
 For i=0 To SizeOf(NeonPointerState)-8 Step 8 : PokeI(@ncaPointer+i,PeekI(@ncaCanvasInput\pointer+i)) : Next
 ncaNative\key=ncaCanvasInput\input\key : ncaNative\scalar=ncaCanvasInput\input\scalar
 ncaNative\ctrl=ncaCanvasInput\input\ctrl : ncaNative\wheel=ncaCanvasInput\input\wheel
 ProcedureReturn 0
EndProcedure
CompilerEndIf
Procedure.i NcaNoClock()
  ProcedureReturn -1
EndProcedure
Global ncaClock.i=@NcaNoClock
Procedure.i NcaStep(rc.i)
  ncaStage=ncaStage+1
  If rc<>0 And ncaFailure=0 : ncaFailure=1000+ncaStage : PokeI(#NCA_REPORT+16,ncaFailure) : PokeI(#NCA_REPORT+24,rc) : EndIf
  ProcedureReturn rc
EndProcedure
Procedure NcaCheck(actual.i,expected.i)
  ncaChecks=ncaChecks+1
  PokeI(#NCA_REPORT+496+ncaChecks*16,actual) : PokeI(#NCA_REPORT+504+ncaChecks*16,expected)
  If actual<>expected And ncaFailure=0 : ncaFailure=ncaChecks : ncaCoreFailure=ncaChecks : EndIf
  PokeI(#NCA_REPORT+16,ncaFailure) : PokeI(#NCA_REPORT+64,ncaChecks) : PokeI(#NCA_REPORT+72,ncaCoreFailure)
EndProcedure
Procedure.i NcaMockPoll(dest.i)
  Protected i.i
  If ncaMockResult=1 : For i=0 To 31 Step 8 : PokeI(dest+i,PeekI(@ncaMockEvent+i)) : Next : EndIf
  ProcedureReturn ncaMockResult
EndProcedure
Procedure.i NcaMockFlush()
  ncaMockBusy=NeonServicePointerUnbind(@ncaTestPointer)
  ProcedureReturn ncaFlushResult
EndProcedure
Procedure NcaPointerChecks()
  NcaCheck(SizeOf(NeonPointerState),104)
  NcaCheck(NeonPointerConfigure(@ncaTestPointer,0,800,640,400),#NPT_ERR_ARGS)
  NcaCheck(NeonPointerConfigure(@ncaTestPointer,1280,800,640,400),0)
  ncaEvent\x=200 : ncaEvent\y=100 : ncaEvent\id=7 : ncaEvent\state=#HW_TOUCH_DOWN : ncaEvent\ticks=10
  NcaCheck(NeonPointerFeed(@ncaTestPointer,@ncaEvent),0) : NcaCheck(ncaTestPointer\x,100) : NcaCheck(ncaTestPointer\y,50)
  NcaCheck(ncaTestPointer\pressed,1) : NcaCheck(ncaTestPointer\down,1)
  NcaCheck(NeonPointerConfigure(@ncaTestPointer,1280,800,640,400),#NPT_ERR_BUSY)
  ncaEvent\id=8 : ncaEvent\state=#HW_TOUCH_UP : ncaEvent\ticks=11
  NcaCheck(NeonPointerFeed(@ncaTestPointer,@ncaEvent),0) : NcaCheck(ncaTestPointer\changed,0) : NcaCheck(ncaTestPointer\down,1)
  ncaEvent\id=7 : ncaEvent\state=#HW_TOUCH_MOVE : ncaEvent\ticks=9
  NcaCheck(NeonPointerFeed(@ncaTestPointer,@ncaEvent),0) : NcaCheck(ncaTestPointer\changed,0)
  ncaEvent\state=#HW_TOUCH_CANCEL
  NcaCheck(NeonPointerFeed(@ncaTestPointer,@ncaEvent),0) : NcaCheck(ncaTestPointer\down,1)
  ncaEvent\ticks=12 : ncaEvent\state=#HW_TOUCH_MOVE : ncaEvent\x=400
  NcaCheck(NeonPointerFeed(@ncaTestPointer,@ncaEvent),0) : NcaCheck(ncaTestPointer\x,200) : NcaCheck(ncaTestPointer\pressed,0)
  ncaEvent\state=#HW_TOUCH_UP : ncaEvent\ticks=13
  NcaCheck(NeonPointerFeed(@ncaTestPointer,@ncaEvent),0) : NcaCheck(ncaTestPointer\released,1) : NcaCheck(ncaTestPointer\down,0)
  NcaCheck(NeonPointerIdle(@ncaTestPointer),0) : NcaCheck(ncaTestPointer\released,0)
  ncaEvent\state=#HW_TOUCH_DOWN : ncaEvent\ticks=14
  NcaCheck(NeonPointerFeed(@ncaTestPointer,@ncaEvent),0)
  ncaEvent\id=-1 : ncaEvent\state=#HW_TOUCH_CANCEL
  NcaCheck(NeonPointerFeed(@ncaTestPointer,@ncaEvent),0) : NcaCheck(ncaTestPointer\cancelled,1) : NcaCheck(ncaTestPointer\released,0)
  ncaEvent\id=7 : ncaEvent\state=4
  NcaCheck(NeonPointerFeed(@ncaTestPointer,@ncaEvent),#NPT_ERR_ARGS)
  PokeL(@ncaMockServices[0],$53564E41) : PokeL(@ncaMockServices[0]+4,1) : PokeL(@ncaMockServices[0]+8,8) : PokeL(@ncaMockServices[0]+12,44)
  PokeI(@ncaMockServices[0]+16+40*8,@NcaMockPoll) : PokeI(@ncaMockServices[0]+16+42*8,@NcaMockFlush)
  NcaCheck(NeonServicePointerBind(@ncaTestPointer,@ncaMockServices[0],1280,800,640,400),0)
  NcaCheck(ncaMockBusy,#NPT_ERR_BUSY)
  ncaFlushResult=1
  NcaCheck(NeonServicePointerBind(@ncaTestPointer,@ncaMockServices[0],1280,800,320,200),#NPT_ERR_PROVIDER)
  NcaCheck(ncaTestPointer\canvasW,640)
  ncaFlushResult=0 : ncaMockResult=0
  NcaCheck(NeonServicePointerPoll(@ncaTestPointer),0)
  ncaMockResult=1 : ncaMockEvent\x=800 : ncaMockEvent\y=400 : ncaMockEvent\id=4 : ncaMockEvent\state=#HW_TOUCH_DOWN : ncaMockEvent\ticks=20
  NcaCheck(NeonServicePointerPoll(@ncaTestPointer),1) : NcaCheck(ncaTestPointer\x,400) : NcaCheck(ncaTestPointer\down,1)
  NcaCheck(NeonServicePointerBind(@ncaTestPointer,@ncaMockServices[0],1280,800,640,400),#NPT_ERR_BUSY)
  ncaMockResult=2
  NcaCheck(NeonServicePointerPoll(@ncaTestPointer),#NPT_ERR_PROVIDER) : NcaCheck(ncaTestPointer\cancelled,1) : NcaCheck(ncaTestPointer\down,0)
  NcaCheck(NeonServicePointerUnbind(@ncaTestPointer),0)
  NcaCheck(NeonServicePointerPoll(@ncaTestPointer),#NPT_ERR_STATE)
EndProcedure
Procedure.i NcaBuildTabs()
  Protected rc.i
  rc=NeonChromeTabsBeginBuild(@ncaTabs) : If rc<>0 : ProcedureReturn rc : EndIf
  If (ncaClosedMask & 1)=0 : rc=NeonChromeTabsAdd(@ncaTabs,10,"Scene",#NCT_NORMAL) : If rc<>0 : ProcedureReturn rc : EndIf : EndIf
  If (ncaClosedMask & 2)=0 : rc=NeonChromeTabsAdd(@ncaTabs,20,"Assets",#NCT_PINNED) : If rc<>0 : ProcedureReturn rc : EndIf : EndIf
  If (ncaClosedMask & 4)=0 : rc=NeonChromeTabsAdd(@ncaTabs,30,"Preview",#NCT_ITALIC) : If rc<>0 : ProcedureReturn rc : EndIf : EndIf
  ProcedureReturn NeonChromeTabsSeal(@ncaTabs)
EndProcedure
Procedure.i NcaRetainedBox(x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
  Protected p.i
  If ncaFrame=89 And ncaBoxCount<32
    p=#NCA_REPORT+10240+ncaBoxCount*64
    PokeL(p,MathBitsOf(x)) : PokeL(p+4,MathBitsOf(y)) : PokeL(p+8,MathBitsOf(w)) : PokeL(p+12,MathBitsOf(h))
    PokeL(p+16,MathBitsOf(r)) : PokeL(p+20,MathBitsOf(g)) : PokeL(p+24,MathBitsOf(b)) : PokeL(p+28,MathBitsOf(a))
  EndIf
  ncaBoxCount=ncaBoxCount+1
  ProcedureReturn NeonServiceBox(x,y,w,h,r,g,b,a)
EndProcedure
CompilerIf #NCA_ASSETS=1
Procedure.i NcaOldGraphics(op.i,context.i,request.i,bytes.i)
  ProcedureReturn #NEON_SERVICE_ERR_PROVIDER
EndProcedure
Procedure.i NcaAssetLoad(services.i)
  Protected bytes.i,i.i,info.NeonPngInfo,request.NeonServiceFontDeriveRequest,api.NeonServiceApi
  api\magic=#NEON_SERVICE_MAGIC : api\major=1 : api\minor=7 : api\bytes=SizeOf(NeonServiceApi)
  api\flags=1023 : api\maxFonts=32 : api\dispatch=@NcaOldGraphics
  NcaCheck(NeonServiceBindApi(@api,SizeOf(NeonServiceApi),512),#NEON_SERVICE_ERR_ABI)
  If NcaStep(AnvilFileBind(services))<>0 : ProcedureReturn -1 : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i NcaAssetFonts()
  Protected bytes.i,i.i,request.NeonServiceFontDeriveRequest
  bytes=AnvilFileReadWhole("2:/fonts/Lato-Regular.ttf",@ncaFontSource[0],1048576)
  If bytes<0 : NcaStep(bytes) : ProcedureReturn -1 : EndIf
  ncaFont=NeonServiceFontLoadMemory(@ncaFontSource[0],bytes,0,16)
  If ncaFont=0 : NcaStep(NeonServiceError()) : ProcedureReturn -1 : EndIf
  NcaCheck(NeonServiceFontSetShowControls(ncaFont,0),0)
  ncaSmall=NeonServiceFontDerive(ncaFont,1,14)
  ncaShowFont=NeonServiceFontDerive(ncaFont,2,16)
  If ncaSmall=0 Or ncaShowFont=0 : NcaStep(NeonServiceError()) : ProcedureReturn -1 : EndIf
  NcaCheck(NeonServiceFontSetFixedAdvance(ncaShowFont,16.0),0)
  NcaCheck(NeonServiceFontSetShowControls(ncaShowFont,1),0)
  ncaFractionFont=NeonServiceFontDerive(ncaShowFont,3,16)
  If ncaFractionFont=0 : NcaStep(NeonServiceError()) : ProcedureReturn -1 : EndIf
  NcaCheck(NeonServiceFontSetFixedAdvance(ncaShowFont,18.0),0)
  NcaCheck(MathBitsOf(NeonServiceTextWidth(ncaFractionFont,?ncaControlText)),MathBitsOf(48.0))
  NcaCheck(MathBitsOf(NeonServiceTextWidth(ncaShowFont,?ncaControlText)),MathBitsOf(54.0))
  NcaCheck(NeonServiceFontSetFixedAdvance(ncaShowFont,16.0),0)
  NcaCheck(NeonServiceFontSetFixedAdvance(ncaFractionFont,15.5),0)
  NcaCheck(NeonServiceFontSetSnapToPixel(ncaFractionFont,0),0)
  NcaCheck(MathBitsOf(NeonServiceTextWidth(ncaFractionFont,?ncaControlText)),MathBitsOf(46.5))
  NcaCheck(MathBitsOf(NeonServiceTextWidth(ncaFont,?ncaControlText)),MathBitsOf(NeonServiceTextWidth(ncaFont,"AV")))
  NcaCheck(NeonServiceFontDerive(1,0,16),0)
  NcaCheck(NeonServiceError(),#NEON_SERVICE_ERR_ARGS)
  request\font=ncaFont : request\role=0 : request\pixels=16
  NcaCheck(NeonServiceRequestExtension(37,@request,16,0,512,8,0),#NEON_SERVICE_ERR_ARGS)
  request\role=4
  NcaCheck(NeonServiceRequestExtension(37,@request,24,0,512,8,0),#NEON_SERVICE_ERR_ARGS)
  request\role=0 : request\pixels=0
  NcaCheck(NeonServiceRequestExtension(37,@request,24,0,512,8,0),#NEON_SERVICE_ERR_ARGS)
  request\pixels=16 : request\font=ncaFont+1000
  NcaCheck(NeonServiceRequestExtension(37,@request,24,0,512,8,0),#NEON_SERVICE_ERR_ARGS)
  For i=0 To 131071 : ncaFontSource[i]=0 : Next
  For i=0 To 131071 : If ncaFontSource[i]<>0 : NcaStep(-60) : ProcedureReturn -1 : EndIf : Next
  PokeI(#NCA_REPORT+12800,$4E434132) : PokeI(#NCA_REPORT+12816,ncaShowFont) : PokeI(#NCA_REPORT+12824,ncaFractionFont)
  PokeI(#NCA_REPORT+12864,bytes)
  ProcedureReturn 0
EndProcedure
Procedure.i NcaAssetPng()
  Protected bytes.i,i.i,info.NeonPngInfo
  bytes=AnvilFileReadWhole("1:/NPNG457.PNG",@ncaPngSource[0],16384)
  If bytes<0 : NcaStep(bytes) : ProcedureReturn -1 : EndIf
  If NcaStep(NeonPngInspect(@info,@ncaPngSource[0],bytes))<>0 : ProcedureReturn -1 : EndIf
  ncaPngWidth=info\width : ncaPngHeight=info\height
  ncaPngTexture=NeonServiceSpriteLoadPNGMemory(2,@ncaPngSource[0],bytes,@ncaPngRgba[0],8192,-1,0,0,@ncaPngWork[0],65536)
  If ncaPngTexture=0 : NcaStep(NeonServiceError()) : ProcedureReturn -1 : EndIf
  PokeI(#NCA_REPORT+12808,ncaPngTexture) : PokeI(#NCA_REPORT+12832,info\width) : PokeI(#NCA_REPORT+12840,info\height)
  PokeI(#NCA_REPORT+12848,bytes) : PokeI(#NCA_REPORT+12856,info\width*info\height*4)
  For i=0 To 2047 : ncaPngSource[i]=0 : Next
  For i=0 To 1023 : ncaPngRgba[i]=0 : Next
  For i=0 To 8191 : ncaPngWork[i]=0 : Next
  For i=0 To 2047 : If ncaPngSource[i]<>0 : NcaStep(-61) : ProcedureReturn -1 : EndIf : Next
  For i=0 To 1023 : If ncaPngRgba[i]<>0 : NcaStep(-62) : ProcedureReturn -1 : EndIf : Next
  PokeI(#NCA_REPORT+12872,1)
  If NcaStep(NeonServicePrepare(ncaFont,?ncaControlText))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServicePrepare(ncaFont,"AV"))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServicePrepare(ncaShowFont,?ncaControlText))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServicePrepare(ncaFractionFont,?ncaControlText))<>0 : ProcedureReturn -1 : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i NcaAssetBox(x.f,y.f)
  If NcaStep(NeonServiceBoxMapped(x,y,9.0,1.0,1.0,1.0,1.0,1.0,1,1))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServiceBoxMapped(x,y+15.0,9.0,1.0,1.0,1.0,1.0,1.0,1,1))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServiceBoxMapped(x,y+1.0,1.0,14.0,1.0,1.0,1.0,1.0,1,1))<>0 : ProcedureReturn -1 : EndIf
  ProcedureReturn NcaStep(NeonServiceBoxMapped(x+8.0,y+1.0,1.0,14.0,1.0,1.0,1.0,1.0,1,1))
EndProcedure
Procedure.i NcaAssetPaint()
  Protected sx.f=MathFFromInt(NeonServiceWidth())/640.0,sy.f=MathFFromInt(NeonServiceHeight())/400.0
  If NcaStep(NeonServiceSpriteBatchBegin(ncaPngTexture))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServiceSpriteBatchAdd(12.0*sx,306.0*sy,MathFFromInt(ncaPngWidth)*3.0*sx,MathFFromInt(ncaPngHeight)*3.0*sy,0.0,1.0,1.0,1.0,1.0,1))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServiceSpriteBatchEnd())<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServiceText(ncaShowFont,92.0,306.0,?ncaControlText,1.0,1.0,1.0,1.0))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServiceText(ncaFont,156.0,306.0,"A",1.0,1.0,1.0,1.0))<>0 : ProcedureReturn -1 : EndIf
  If NcaAssetBox(172.0,306.0)<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServiceText(ncaFont,188.0,306.0,"V",1.0,1.0,1.0,1.0))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServiceText(ncaFont,92.0,332.0,?ncaControlText,1.0,1.0,1.0,1.0))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServiceText(ncaFont,156.0,332.0,"AV",1.0,1.0,1.0,1.0))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServiceText(ncaFractionFont,92.375,360.375,?ncaControlText,1.0,1.0,1.0,1.0))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServiceText(ncaFractionFont,156.375,360.375,"A",1.0,1.0,1.0,1.0))<>0 : ProcedureReturn -1 : EndIf
  If NcaAssetBox(171.875,360.375)<>0 : ProcedureReturn -1 : EndIf
  ProcedureReturn NcaStep(NeonServiceText(ncaFractionFont,187.375,360.375,"V",1.0,1.0,1.0,1.0))
EndProcedure
DataSection
ncaControlText:
  Data.a 65,9,86,0
EndDataSection
CompilerEndIf
Procedure.i NcaSetup(services.i)
  Protected i.i,rc.i,retroStart.i
  CompilerIf #NCA_ASSETS=1
  If NcaAssetLoad(services)<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServiceBind(services,1023 | #NEON_SERVICE_FONT_CARETS | (#NCA_RETRO*(#NEON_SERVICE_TARGETS | #NEON_SERVICE_TARGET_RETRO))))<>0 : ProcedureReturn -1 : EndIf
  CompilerElse
  If NcaStep(NeonServiceBind(services,55 | #NEON_SERVICE_FONT_CARETS | (#NCA_RETRO*(#NEON_SERVICE_TARGETS | #NEON_SERVICE_TARGET_RETRO))))<>0 : ProcedureReturn -1 : EndIf
  CompilerEndIf
  ncaClock=PeekI(services+16+11*8)
  If NcaStep(NeonServiceOpen())<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServiceCanvas(640,400))<>0 : ProcedureReturn -1 : EndIf
  CompilerIf #NCA_ASSETS=1
  If NcaAssetFonts()<>0 : ProcedureReturn -1 : EndIf
  CompilerElse
  ncaFont=NeonServiceFontRegister(0,0,16) : ncaSmall=NeonServiceFontRegister(0,1,14)
  CompilerEndIf
  If ncaFont<1 Or ncaSmall<1 : NcaStep(-20) : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServiceChromeMenuInstall())<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonChromeMenuConfigure(@ncaMenu,@ncaMenuArena[0],16384,16,128,640,400,1.0,ncaFont,ncaSmall))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonChromeMenuBarRect(@ncaMenu,0.0,0.0,640.0,26.0))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonChromeMenuAddRoot(@ncaMenu,10,"File"))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonChromeMenuAddItem(@ncaMenu,100,10,"Reset scene","",1,0))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonChromeMenuAddSeparator(@ncaMenu,10))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonChromeMenuAddItem(@ncaMenu,101,10,"Export capture","",0,0))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonChromeMenuAddRoot(@ncaMenu,20,"Simulation"))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonChromeMenuAddItem(@ncaMenu,200,20,"Particles","",1,1))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonChromeMenuSeal(@ncaMenu))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServiceChromeTabsInstall())<>0 : ProcedureReturn -1 : EndIf
  ncaTabConfig\x=0.0 : ncaTabConfig\y=26.0 : ncaTabConfig\w=640.0 : ncaTabConfig\h=30.0 : ncaTabConfig\scale=1.0
  ncaTabConfig\font=ncaFont : ncaTabConfig\smallFont=ncaSmall : ncaTabConfig\italicFont=-1 : ncaTabConfig\withClose=1 : ncaTabConfig\flags=#NCT_SCROLL : ncaTabConfig\activeId=10
  If NcaStep(NeonChromeTabsConfigure(@ncaTabs,@ncaTabArena[0],8192,8,128,@ncaTabConfig))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NcaBuildTabs())<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServiceChromeEditInstall())<>0 : ProcedureReturn -1 : EndIf
  ncaEditConfig\id=1 : ncaEditConfig\font=ncaFont : ncaEditConfig\text="" : ncaEditConfig\placeholder="Search assets"
  ncaEditConfig\x=244.0 : ncaEditConfig\y=70.0 : ncaEditConfig\w=380.0 : ncaEditConfig\h=32.0 : ncaEditConfig\scale=1.0
  If NcaStep(NeonChromeEditConfigure(@ncaEdit,@ncaEditArena[0],2048,256,@ncaEditConfig))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonChromeScrollConfigure(@ncaScroll,1.0))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServiceChromeListInstall())<>0 : ProcedureReturn -1 : EndIf
  ncaListConfig\id=1 : ncaListConfig\font=ncaSmall : ncaListConfig\scrollState=@ncaScroll
  ncaListConfig\x=12.0 : ncaListConfig\y=68.0 : ncaListConfig\w=216.0 : ncaListConfig\h=230.0 : ncaListConfig\rowH=24.0 : ncaListConfig\scale=1.0
  If NcaStep(NeonChromeListConfigure(@ncaList,@ncaListArena[0],16384,16,128,@ncaListConfig))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonChromeListAdd(@ncaList,1,"Scene assets",0,1,1,0))<>0 : ProcedureReturn -1 : EndIf
  For i=2 To 12
    If NcaStep(NeonChromeListAdd(@ncaList,i,"Resident sprite",1,0,0,"RGBA"))<>0 : ProcedureReturn -1 : EndIf
  Next
  If NcaStep(NeonChromeListSeal(@ncaList))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonRetainedConfigure(@ncaRetainedArena[0],32768,16,128))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServiceRetainedInstall())<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonRetainedRendererInstall(@NcaRetainedBox,@NeonServiceText,@NeonServiceTextWidth,@NeonServiceLineHeight,@NeonServicePolygon,@NeonServicePrepare))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonRetainedViewport(0.0,0.0,640.0,400.0,640.0,400.0))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonRetainedFontSet(ncaFont))<>0 : ProcedureReturn -1 : EndIf
  ncaButton=NeonRetainedAddButton(1,244.0,120.0,136.0,30.0,"Pause",0,0)
  ncaToggle=NeonRetainedAddToggle(2,400.0,120.0,224.0,30.0,"Particles",1,0)
  ncaSlider=NeonRetainedAddSlider(3,244.0,178.0,360.0,24.0,0.35,"Speed",0)
  If ncaButton=0 Or ncaToggle=0 Or ncaSlider=0 : NcaStep(-21) : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServicePrepare(ncaSmall,"Sprites and particles"))<>0 : ProcedureReturn -1 : EndIf
  For i=0 To 15
    ncaPixels[i]=$FF00FF00 : If (i % 2)=0 : ncaPixels[i]=$FF0000FF : EndIf
  Next
  ncaTexture=NeonServiceSpriteUpload(1,@ncaPixels[0],64,4,4,0)
  If ncaTexture=0 : NcaStep(NeonServiceError()) : ProcedureReturn -1 : EndIf
  For i=0 To 15 : ncaPixels[i]=0 : Next
  CompilerIf #NCA_ASSETS=1
  If NcaAssetPng()<>0 : ProcedureReturn -1 : EndIf
  CompilerEndIf
  ncaLines[0]=246.0 : ncaLines[1]=220.0 : ncaLines[2]=622.0 : ncaLines[3]=220.0
  ncaLines[4]=622.0 : ncaLines[5]=220.0 : ncaLines[6]=622.0 : ncaLines[7]=382.0
  ncaLines[8]=622.0 : ncaLines[9]=382.0 : ncaLines[10]=246.0 : ncaLines[11]=382.0
  ncaLines[12]=246.0 : ncaLines[13]=382.0 : ncaLines[14]=246.0 : ncaLines[15]=220.0
  If NcaStep(NeonServiceCamera(0.0,0.0,1.0))<>0 : ProcedureReturn -1 : EndIf
  CompilerIf #NCA_NATIVE=1
  If NcaStep(AnvilInputBind(services,0))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(AnvilInputOpen())<>0 : ProcedureReturn -1 : EndIf
  If (AnvilInputCapabilities() & 6)=0 : NcaStep(#NUI_ERR_CAPABILITY) : ProcedureReturn -1 : EndIf
  If NcaStep(NeonPointerConfigure(@ncaPointer,AnvilInputWidth(),AnvilInputHeight(),640,400))<>0 : ProcedureReturn -1 : EndIf
  ncaNative\generation=AnvilInputGeneration()
  CompilerIf #NCA_RETRO=1
  If NcaStep(NeonCanvasFit(@ncaViewport,640,400,AnvilInputWidth(),AnvilInputHeight()))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonCanvasInputConfigureRetro(@ncaCanvasInput,@ncaViewport))<>0 : ProcedureReturn -1 : EndIf
  ncaCanvasInput\input\generation=AnvilInputGeneration()
  ncaTarget=NeonServiceTargetCreate(1280,800,0)
  If ncaTarget=0 : NcaStep(NeonServiceError()) : ProcedureReturn -1 : EndIf
  ; Measure preparation separately: moving it out of frame does not remove its cost.
  retroStart=ncaClock()
  If NcaStep(NeonServiceTargetRetroPrepare(ncaTarget))<>0 : ProcedureReturn -1 : EndIf
  PokeI(#NCA_REPORT+13336,ncaClock()-retroStart)
  PokeI(#NCA_REPORT+13344,$50524531)
  If NcaStep(NeonServiceTargetBind(ncaTarget))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServiceCanvas(640,400))<>0 : ProcedureReturn -1 : EndIf
  CompilerEndIf

  CompilerElse
  If NcaStep(NeonServicePointerBind(@ncaPointer,services,NeonServiceWidth(),NeonServiceHeight(),640,400))<>0 : ProcedureReturn -1 : EndIf
  CompilerEndIf
  ProcedureReturn 0
EndProcedure
Procedure.i NcaRoute(dt.f)
  Protected x.f=ncaPointer\x,y.f=ncaPointer\y,down.i=ncaPointer\down,block.i,id.i,hit.i,rc.i,released.i,eventId.i,eventType.i,eventTag.i,i.i
  Protected *g.NeonRetainedGadget
  CompilerIf #NCA_NATIVE=0
  If ncaPointer\changed=0 And down=0 : x=-1.0 : y=-1.0 : EndIf
  CompilerEndIf
  CompilerIf #NCA_SCRIPTED=1
  If ncaWheel<>0 : x=80.0 : y=150.0 : EndIf
  CompilerEndIf
  If NcaStep(NeonChromeMenuInput(@ncaMenu,x,y,down,ncaWheel,ncaPointer\cancelled))<>0 : ProcedureReturn -1 : EndIf
  block=NeonChromeMenuBlocksMouse(@ncaMenu)
  If ncaPointer\pressed<>0
    ncaOwner=6 : ncaCapture=0
    If block<>0 : ncaOwner=1 : ncaBlockedPresses=ncaBlockedPresses+1
    ElseIf y>=26.0 And y<56.0 : ncaOwner=2
    ElseIf x>=12.0 And x<228.0 And y>=68.0 And y<298.0 : ncaOwner=3
    ElseIf x>=244.0 And x<624.0 And y>=70.0 And y<102.0 : ncaOwner=4
    Else
      hit=NeonRetainedHit(x,y) : If hit<>0 : ncaOwner=5 : ncaCapture=hit : EndIf
    EndIf
  EndIf
  If ncaOwner=1 : block=1 : EndIf
  If ncaPointer\cancelled<>0 : ncaOwner=0 : ncaCapture=0 : block=1 : EndIf
  If NcaStep(NeonChromeTabsInput(@ncaTabs,x,y,down,0,Bool(block<>0 Or (down<>0 And ncaOwner<>2)),dt))<>0 : ProcedureReturn -1 : EndIf
  id=NeonChromeTabsCloseGet(@ncaTabs)
  If id<>0
    ncaCloses=ncaCloses+1 : ncaClosedMask=ncaClosedMask | (1 << (id/10-1))
    If NcaStep(NcaBuildTabs())<>0 : ProcedureReturn -1 : EndIf
  EndIf
  If NeonChromeTabsPinGet(@ncaTabs)<>0 : ncaPins=ncaPins+1 : EndIf
  If NcaStep(NeonChromeScrollInput(@ncaScroll,x,y,down))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonChromeListInput(@ncaList,ncaMenu\wheelRemaining,Bool(block<>0 Or (down<>0 And ncaOwner<>3)),dt))<>0 : ProcedureReturn -1 : EndIf
  id=NeonChromeListEventGet(@ncaList)
  If id<>0
    ncaListEvents=ncaListEvents+1
    If NcaStep(NeonChromeListItemState(@ncaList,ncaSelected,0,Bool(ncaSelected=1)))<>0 : ProcedureReturn -1 : EndIf
    ncaSelected=id
    If NcaStep(NeonChromeListItemState(@ncaList,id,1,Bool(id=1)))<>0 : ProcedureReturn -1 : EndIf
  EndIf
  ncaEditEvent\x=x : ncaEditEvent\y=y : ncaEditEvent\down=down : ncaEditEvent\blocked=block : ncaEditEvent\key=ncaKey : ncaEditEvent\scalar=ncaScalar : ncaEditEvent\ctrl=ncaCtrl : ncaEditEvent\dt=dt
  CompilerIf #NCA_NATIVE=1
  ncaEditEvent\paste=@ncaClipboard[0] : ncaEditEvent\pasteBudget=256
  CompilerEndIf
  If NcaStep(NeonChromeEditInput(@ncaEdit,@ncaEditEvent))<>0 : ProcedureReturn -1 : EndIf
  CompilerIf #NCA_NATIVE=1
  rc=NeonChromeEditClipboard(@ncaEdit)
  If rc<>0
    For i=0 To 255
      PokeA(@ncaClipboard[0]+i,PeekA(rc+i))
      If PeekA(rc+i)=0 : Break : EndIf
    Next
  EndIf
  CompilerEndIf
  released=0
  If block=0 And ncaOwner=5 And ncaCapture<>0 And NeonRetainedHit(x,y)=ncaCapture
    released=ncaPointer\released
    If NcaStep(NeonRetainedUpdateInput(x,y,down,released,0,0,0))<>0 : ProcedureReturn -1 : EndIf
  Else
    If NcaStep(NeonRetainedUpdateInput(-1.0,-1.0,down,0,0,0,0))<>0 : ProcedureReturn -1 : EndIf
  EndIf
  If NeonRetainedEventGet(@eventId,@eventType,@eventTag)<>0
    If eventId=1
      ncaButtonEvents=ncaButtonEvents+1
      ncaRunning=1-ncaRunning
      If ncaRunning<>0
        If NcaStep(NeonRetainedTextSet(ncaButton,"Pause"))<>0 : ProcedureReturn -1 : EndIf
      Else
        If NcaStep(NeonRetainedTextSet(ncaButton,"Start"))<>0 : ProcedureReturn -1 : EndIf
      EndIf
    ElseIf eventId=2
      ncaToggleEvents=ncaToggleEvents+1 : *g=NeonRetainedGet(ncaToggle)
      If NcaStep(NeonChromeMenuItemState(@ncaMenu,200,1,*g\isActive))<>0 : ProcedureReturn -1 : EndIf
    EndIf
  EndIf
  id=NeonChromeMenuEventGet(@ncaMenu)
  If id<>0
    ncaMenuEvents=ncaMenuEvents+1
    If id=100
      ncaPhase=0.0
      If NcaStep(NeonRetainedValueSet(ncaSlider,0.35))<>0 : ProcedureReturn -1 : EndIf
    ElseIf id=200
      *g=NeonRetainedGet(ncaToggle)
      If NcaStep(NeonRetainedActiveSet(ncaToggle,1-*g\isActive))<>0 : ProcedureReturn -1 : EndIf
      *g=NeonRetainedGet(ncaToggle)
      If NcaStep(NeonChromeMenuItemState(@ncaMenu,200,1,*g\isActive))<>0 : ProcedureReturn -1 : EndIf
    EndIf
  EndIf
  If ncaPointer\released<>0 Or ncaPointer\cancelled<>0 : ncaOwner=0 : ncaCapture=0 : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i NcaPulse(frame.i,state.i,x.i,y.i)
  ncaEvent\x=MathFToI32(MathFFromInt(x)*(MathFFromInt(ncaPointer\sourceW)/640.0)+0.5) : ncaEvent\y=MathFToI32(MathFFromInt(y)*(MathFFromInt(ncaPointer\sourceH)/400.0)+0.5) : ncaEvent\id=7 : ncaEvent\state=state : ncaEvent\ticks=ncaClock() : ncaEvent\pressure=64 : ncaEvent\reserved=0
  If NcaStep(NeonPointerFeed(@ncaPointer,@ncaEvent))<>0 : ProcedureReturn -1 : EndIf
  ncaScriptRecords=ncaScriptRecords+1
  If NcaStep(NcaRoute(0.0))<>0 : ProcedureReturn -1 : EndIf
  ProcedureReturn NeonPointerIdle(@ncaPointer)
EndProcedure
Procedure.i NcaScript(frame.i)
  Select frame
    Case 8 : ProcedureReturn NcaPulse(frame,#HW_TOUCH_DOWN,20,12)
    Case 80 : ProcedureReturn NcaPulse(frame,#HW_TOUCH_DOWN,20,12)
    Case 9 : ProcedureReturn NcaPulse(frame,#HW_TOUCH_UP,20,12)
    Case 81 : ProcedureReturn NcaPulse(frame,#HW_TOUCH_UP,20,12)
    Case 12 : ProcedureReturn NcaPulse(frame,#HW_TOUCH_DOWN,40,150)
    Case 16 : ProcedureReturn NcaPulse(frame,#HW_TOUCH_DOWN,40,150)
    Case 13 : ProcedureReturn NcaPulse(frame,#HW_TOUCH_UP,40,150)
    Case 17 : ProcedureReturn NcaPulse(frame,#HW_TOUCH_UP,40,150)
    Case 22 : ProcedureReturn NcaPulse(frame,#HW_TOUCH_DOWN,125,40)
    Case 23 : ProcedureReturn NcaPulse(frame,#HW_TOUCH_UP,125,40)
    Case 28 : ProcedureReturn NcaPulse(frame,#HW_TOUCH_DOWN,300,86)
    Case 29 : ProcedureReturn NcaPulse(frame,#HW_TOUCH_UP,300,86)
    Case 30 : ncaKey=#NCE_A : ncaCtrl=1
    Case 31 : ncaScalar=65
    Case 32 : ncaScalar=114
    Case 33 : ncaScalar=99
    Case 34 : ncaScalar=97
    Case 35 : ncaScalar=100
    Case 36 : ncaScalar=101
    Case 40 : ProcedureReturn NcaPulse(frame,#HW_TOUCH_DOWN,300,135)
    Case 66 : ProcedureReturn NcaPulse(frame,#HW_TOUCH_DOWN,300,135)
    Case 41 : ProcedureReturn NcaPulse(frame,#HW_TOUCH_UP,300,135)
    Case 46 : ProcedureReturn NcaPulse(frame,#HW_TOUCH_DOWN,580,135)
    Case 50 : ProcedureReturn NcaPulse(frame,#HW_TOUCH_DOWN,580,135)
    Case 47 : ProcedureReturn NcaPulse(frame,#HW_TOUCH_UP,580,135)
    Case 51 : ProcedureReturn NcaPulse(frame,#HW_TOUCH_UP,580,135)
    Case 56 : ProcedureReturn NcaPulse(frame,#HW_TOUCH_DOWN,360,190)
    Case 57 : ProcedureReturn NcaPulse(frame,#HW_TOUCH_MOVE,520,190)
    Case 58 : ProcedureReturn NcaPulse(frame,#HW_TOUCH_UP,520,190)
    Case 62 : ProcedureReturn NcaPulse(frame,#HW_TOUCH_DOWN,630,390)
    Case 63 : ProcedureReturn NcaPulse(frame,#HW_TOUCH_UP,300,135)
    Case 67 : ProcedureReturn NcaPulse(frame,#HW_TOUCH_UP,630,390)
    Case 70 : ncaWheel=-1
    Case 72 : ProcedureReturn NcaPulse(frame,#HW_TOUCH_DOWN,300,135)
    Case 73 : ProcedureReturn NcaPulse(frame,#HW_TOUCH_UP,300,135)
  EndSelect
  ProcedureReturn 0
EndProcedure
Procedure.i NcaPrepare(frame.i)
  Protected i.i,*p.NeonParticleRecord,*g.NeonRetainedGadget,sx.f=MathFFromInt(NeonServiceWidth())/640.0,sy.f=MathFFromInt(NeonServiceHeight())/400.0,uniform.f
  uniform=sx : If sy<uniform : uniform=sy : EndIf
  *g=NeonRetainedGet(ncaSlider)
  If ncaRunning<>0 : ncaPhase=ncaPhase+(0.2+*g\value*1.8)*(1.0/30.0) : EndIf
  If ncaEdit\ready=0 : If NcaStep(NeonChromeEditSeal(@ncaEdit))<>0 : ProcedureReturn -1 : EndIf : EndIf
  If NcaStep(NeonRetainedPrepare())<>0 : ProcedureReturn -1 : EndIf
  For i=0 To 31
    *p=@ncaParticles[i] : *p\x=(290.0+MathFFromInt(i % 8)*40.0)*sx : *p\y=(245.0+MathFFromInt(i/8)*32.0)*sy
    *p\size=8.0*uniform : *p\angle=ncaPhase*0.3 : *p\r=0.25 : *p\g=0.75 : *p\b=1.0 : *p\a=0.8
  Next
  If NcaStep(NeonServiceParticlesPrepare(@ncaParticles[0],1024,32))<>0 : ProcedureReturn -1 : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i NcaDraw(frame.i)
  Protected *g.NeonRetainedGadget,sx.f=MathFFromInt(NeonServiceWidth())/640.0,sy.f=MathFFromInt(NeonServiceHeight())/400.0
  If NcaStep(NeonServiceBegin(0.045,0.055,0.075,1.0))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServiceBox(244.0,218.0,380.0,166.0,0.025,0.035,0.05,1.0))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServiceScissorSet(244.0,218.0,380.0,166.0))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServiceStaticLines(@ncaLines[0],64,8,0.2,0.4,0.65,1.0,0))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServiceSpriteBatchBegin(ncaTexture))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServiceSpriteBatchAdd((388.0+Sin(ncaPhase*2.0)*40.0)*sx,248.0*sy,64.0*sx,64.0*sy,ncaPhase*0.7,1.0,1.0,1.0,1.0,1))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServiceSpriteBatchAdd(544.0*sx,304.0*sy,32.0*sx,32.0*sy,-ncaPhase*0.7,0.5,0.7,1.0,1.0,1))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServiceSpriteBatchEnd())<>0 : ProcedureReturn -1 : EndIf
  *g=NeonRetainedGet(ncaToggle)
  If *g\isActive<>0 : If NcaStep(NeonServiceParticlesDrawPrepared())<>0 : ProcedureReturn -1 : EndIf : EndIf
  If NcaStep(NeonServiceScissorClear())<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServiceText(ncaSmall,244.0,202.0,"Sprites and particles",0.6,0.8,1.0,1.0))<>0 : ProcedureReturn -1 : EndIf
  CompilerIf #NCA_ASSETS=1
  If NcaAssetPaint()<>0 : ProcedureReturn -1 : EndIf
  CompilerEndIf
  If NcaStep(NeonRetainedDrawUI(1.0/30.0))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonChromeListDraw(@ncaList))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonChromeEditDraw(@ncaEdit))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonChromeTabsDraw(@ncaTabs))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonChromeMenuDraw(@ncaMenu))<>0 : ProcedureReturn -1 : EndIf
  ncaEndStart=ncaClock()
  If NcaStep(NeonServiceEnd())<>0 : ProcedureReturn -1 : EndIf
  CompilerIf #NCA_RETRO=1
  PokeI(#NCA_REPORT+13440+frame*32,ncaClock()-ncaEndStart)
  If NcaStep(NeonServiceTargetUnbind(ncaTarget))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServiceTargetRetroPrepare(ncaTarget))<>0 : ProcedureReturn -1 : EndIf
  PokeI(#NCA_REPORT+13448+frame*32,ncaClock()-ncaEndStart)
  If NcaStep(NeonServiceBegin(0.0,0.0,0.0,1.0))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServiceTargetDrawRetro(ncaTarget,0.0))<>0 : ProcedureReturn -1 : EndIf
  If NcaStep(NeonServiceEnd())<>0 : ProcedureReturn -1 : EndIf
  PokeI(#NCA_REPORT+13456+frame*32,ncaClock()-ncaEndStart)
  If frame<89
    If NcaStep(NeonServiceTargetBind(ncaTarget))<>0 : ProcedureReturn -1 : EndIf
    If NcaStep(NeonServiceCanvas(640,400))<>0 : ProcedureReturn -1 : EndIf
  EndIf
  PokeI(#NCA_REPORT+13464+frame*32,ncaClock()-ncaEndStart)
  CompilerEndIf
  ProcedureReturn 0
EndProcedure
Procedure.i Main(services.i)
  Protected i.i,j.i,rc.i,started.i,frameStart.i,now.i,inputEnd.i,prepareEnd.i,drawEnd.i,frames.i,ends.i,n.i,p.i
  Protected *g.NeonRetainedGadget
  For i=0 To 16383 Step 8 : PokeI(#NCA_REPORT+i,0) : Next
  PokeI(#NCA_REPORT,$4E434131) : PokeI(#NCA_REPORT+8,1) : PokeI(#NCA_REPORT+48,#NCA_SCRIPTED)
  CompilerIf #NCA_RETRO=1
  PokeI(#NCA_REPORT+13312,$4E435031) : PokeI(#NCA_REPORT+13320,90) : PokeI(#NCA_REPORT+13328,#NCA_PRESENT_PACED)
  CompilerEndIf
  NcaPointerChecks() : If ncaFailure<>0 : ProcedureReturn ncaFailure : EndIf
  If NcaSetup(services)<>0 : ProcedureReturn ncaFailure : EndIf
  started=ncaClock() : If started<0 : NcaStep(started) : ProcedureReturn ncaFailure : EndIf
  For i=0 To 89
    frameStart=ncaClock() : ncaFrame=i : ncaBoxCount=0 : ncaKey=0 : ncaScalar=0 : ncaCtrl=0 : ncaWheel=0
    If frameStart<started Or frameStart-started>8000000 : NcaStep(-30) : Break : EndIf
    CompilerIf #NCA_NATIVE=1
    For j=1 To 32
      rc=AnvilInputPoll(@ncaNativeEvent)
      If rc<0 : NcaStep(rc) : Break : EndIf
      If rc=0 : Break : EndIf
      ncaRealRecords=ncaRealRecords+1
      CompilerIf #NCA_RETRO=1
      If NcaStep(NcaRetroFeed())<>0 : Break : EndIf
      CompilerElse
      If NcaStep(NeonNativeInputFeed(@ncaPointer,@ncaNative,@ncaNativeEvent))<>0 : Break : EndIf
      CompilerEndIf
      ncaKey=ncaNative\key : ncaScalar=ncaNative\scalar : ncaCtrl=ncaNative\ctrl : ncaWheel=ncaNative\wheel
      If NcaStep(NcaRoute(0.0))<>0 : Break : EndIf
      NeonNativeInputIdle(@ncaPointer,@ncaNative)
      CompilerIf #NCA_RETRO=1
      NeonCanvasInputIdle(@ncaCanvasInput)
      CompilerEndIf
      ncaKey=0 : ncaScalar=0 : ncaCtrl=0 : ncaWheel=0
    Next
    CompilerElse
    For j=1 To 32
      rc=NeonServicePointerPoll(@ncaPointer)
      If rc<0 : NcaStep(rc) : Break : EndIf
      If rc=0 : Break : EndIf
      ncaRealRecords=ncaRealRecords+1
      If ncaPointer\changed<>0 : If NcaStep(NcaRoute(0.0))<>0 : Break : EndIf : EndIf
    Next
    CompilerEndIf
    If ncaFailure<>0 : Break : EndIf
    CompilerIf #NCA_SCRIPTED=1
      If NcaStep(NcaScript(i))<>0 : Break : EndIf
    CompilerEndIf
    If NcaStep(NcaRoute(1.0/30.0))<>0 : Break : EndIf
    NeonPointerIdle(@ncaPointer)
    inputEnd=ncaClock()
    If NcaStep(NcaPrepare(i))<>0 : Break : EndIf
    prepareEnd=ncaClock()
    If NcaDraw(i)<>0 : Break : EndIf
    drawEnd=ncaClock() : frames=frames+1 : ends=ends+1
    p=#NCA_REPORT+4096+i*64
    PokeI(p,frameStart-started) : PokeI(p+8,inputEnd-frameStart) : PokeI(p+16,prepareEnd-inputEnd) : PokeI(p+24,drawEnd-prepareEnd) : PokeI(p+32,drawEnd-frameStart) : PokeI(p+40,0)
    PokeI(#NCA_REPORT+11264+i*16,ncaEndStart-prepareEnd) : PokeI(#NCA_REPORT+11272+i*16,drawEnd-ncaEndStart)
    PokeI(p+48,ncaTabs\activeId+100*ncaList\top+1000*ncaRunning) : PokeI(p+56,NeonChromeMenuIsOpen(@ncaMenu))
    CompilerIf #NCA_PRESENT_PACED=1
    ; A synchronized provider already controls cadence. Do not add a drifting timer.
    now=ncaClock()
    CompilerElse
    Repeat : now=ncaClock() : Until now-frameStart>=33333 Or now<frameStart
    CompilerEndIf
    If now<frameStart : NcaStep(-31) : Break : EndIf
  Next
  If NeonServiceFrameOpen()<>0 : NcaStep(NeonServiceAbort()) : EndIf
  CompilerIf #NCA_RETRO=1
  If frames<90 : NeonServiceTargetUnbind(ncaTarget) : EndIf
  If NcaStep(NeonServiceTargetFree(ncaTarget))<>0 : ProcedureReturn ncaFailure : EndIf
  CompilerEndIf
  PokeI(#NCA_REPORT+32,frames) : PokeI(#NCA_REPORT+40,ends) : PokeI(#NCA_REPORT+56,ncaRealRecords)
  PokeI(#NCA_REPORT+80,ncaScriptRecords) : PokeI(#NCA_REPORT+88,ncaClock()-started) : PokeI(#NCA_REPORT+96,ncaStage)
  PokeI(#NCA_REPORT+104,ncaButtonEvents) : PokeI(#NCA_REPORT+112,ncaToggleEvents) : PokeI(#NCA_REPORT+120,ncaListEvents)
  PokeI(#NCA_REPORT+128,ncaTabs\activeId) : PokeI(#NCA_REPORT+136,ncaList\top) : PokeI(#NCA_REPORT+144,ncaSelected) : PokeI(#NCA_REPORT+152,ncaMenuEvents)
  PokeI(#NCA_REPORT+160,ncaBlockedPresses) : PokeI(#NCA_REPORT+168,NeonChromeMenuIsOpen(@ncaMenu))
  *g=NeonRetainedGet(ncaToggle) : PokeI(#NCA_REPORT+176,*g\isActive)
  *g=NeonRetainedGet(ncaSlider) : PokeL(#NCA_REPORT+184,MathBitsOf(*g\value))
  PokeI(#NCA_REPORT+192,ncaCloses) : PokeI(#NCA_REPORT+200,ncaPins) : PokeI(#NCA_REPORT+208,ncaEdit\length)
  n=NeonUtf8Length(NeonChromeEditText(@ncaEdit),256) : For i=0 To n : PokeA(#NCA_REPORT+2048+i,PeekA(NeonChromeEditText(@ncaEdit)+i)) : Next
  *g=NeonRetainedGet(ncaButton) : n=NeonUtf8Length(*g\text,128) : For i=0 To n : PokeA(#NCA_REPORT+2304+i,PeekA(*g\text+i)) : Next
  PokeI(#NCA_REPORT+256,ncaBoxCount) : PokeI(#NCA_REPORT+264,ncaRunning) : PokeL(#NCA_REPORT+272,MathBitsOf(ncaPhase))
  PokeI(#NCA_REPORT+216,ncaTexture) : PokeI(#NCA_REPORT+224,ncaFont) : PokeI(#NCA_REPORT+232,ncaSmall)
  If NcaStep(NeonServiceSpriteClear(ncaTexture))<>0 : ProcedureReturn ncaFailure : EndIf
  CompilerIf #NCA_ASSETS=1
  If NcaStep(NeonServiceSpriteClear(ncaPngTexture))<>0 : ProcedureReturn ncaFailure : EndIf
  If NcaStep(NeonServiceFontUnload(ncaFont))<>0 : ProcedureReturn ncaFailure : EndIf
  NcaCheck(MathBitsOf(NeonServiceTextWidth(ncaShowFont,?ncaControlText)),MathBitsOf(-1.0))
  NcaCheck(NeonServiceError(),#NEON_SERVICE_ERR_PROVIDER)
  NcaCheck(NeonServiceFontDerive(ncaShowFont,0,16),0)
  NcaCheck(NeonServiceError(),-21310)
  PokeI(#NCA_REPORT+12880,1)
  CompilerEndIf
  CompilerIf #NCA_NATIVE=1
  PokeI(#NCA_REPORT+13120,$4E4E4131)
  PokeI(#NCA_REPORT+13128,AnvilInputCapabilities())
  PokeI(#NCA_REPORT+13136,AnvilInputGeneration())
  PokeI(#NCA_REPORT+13144,ncaRealRecords)
  If NcaStep(AnvilInputClose())<>0 : ProcedureReturn ncaFailure : EndIf
  CompilerElse
  If NcaStep(NeonServicePointerUnbind(@ncaPointer))<>0 : ProcedureReturn ncaFailure : EndIf
  CompilerEndIf
  CompilerIf #NCA_ASSETS=1
  PokeI(#NCA_REPORT+240,15)
  CompilerElse
  PokeI(#NCA_REPORT+240,3)
  CompilerEndIf
  PokeI(#NCA_REPORT+248,NeonServiceFrameOpen()) : PokeI(#NCA_REPORT+96,ncaStage)
  ProcedureReturn ncaFailure
EndProcedure

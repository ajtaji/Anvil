; SPDX-License-Identifier: MIT
; Controlled service provider, no GPU, display, MMIO or native driver.
EnableFloatingPoint
XIncludeFile "Anvil/Graphics/neon_retained_ui.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_retained.pbi"
Global nstChecks.i,nstFailure.i,nstContext.i=730,nstContextErrors.i
Global nstCloseFail.i,nstEndFail.i,nstAbortFail.i,nstBadSurface.i,nstBadMetrics.i,nstPartial.i,nstPositive.i,nstReentrant.i
Global Dim nstCalls.i[13]
Global Dim nstTable.q[43]
Global Dim nstArena.q[128]
Global nstApi.NeonServiceApi
Procedure NstCheck(actual.i,expected.i)
  nstChecks=nstChecks+1
  If actual<>expected And nstFailure=0 : nstFailure=nstChecks : EndIf
EndProcedure
Procedure NstContextCheck(context.i,op.i)
  nstCalls[op]=nstCalls[op]+1
  If context<>nstContext : nstContextErrors=nstContextErrors+1 : EndIf
EndProcedure
Procedure.i NstOpen(*out.NeonServiceSurface,capacity.i)
  nstReentrant=NeonServiceUnbind()
  nstCalls[0]=nstCalls[0]+1 : nstContext=nstContext+1
  *out\bytes=SizeOf(NeonServiceSurface) : *out\logicalW=1280 : *out\logicalH=800
  *out\flags=#NEON_SERVICE_VULKAN | #NEON_SERVICE_FONT_REFS : *out\maxFonts=8
  If nstBadSurface<>0 : *out\logicalW=0 : EndIf
  ProcedureReturn nstContext
EndProcedure
Procedure.i NstClose(context.i)
  NstContextCheck(context,1) : ProcedureReturn nstCloseFail
EndProcedure
Procedure.i NstBegin(context.i,r.f,g.f,b.f,a.f)
  NstContextCheck(context,2)
  PokeI(#NST_REPORT+528,MathBitsOf(r)) : PokeI(#NST_REPORT+536,MathBitsOf(g))
  PokeI(#NST_REPORT+544,MathBitsOf(b)) : PokeI(#NST_REPORT+552,MathBitsOf(a))
  nstReentrant=NeonServiceUnbind()
  ProcedureReturn nstPositive
EndProcedure
Procedure.i NstEnd(context.i)
  NstContextCheck(context,3)
  If nstPositive<>0 : ProcedureReturn nstPositive : EndIf
  ProcedureReturn nstEndFail
EndProcedure
Procedure.i NstAbort(context.i)
  NstContextCheck(context,4) : ProcedureReturn nstAbortFail
EndProcedure
Procedure.i NstBox(context.i,x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
  NstContextCheck(context,5)
  PokeI(#NST_REPORT+256,MathBitsOf(x)) : PokeI(#NST_REPORT+264,MathBitsOf(y))
  PokeI(#NST_REPORT+272,MathBitsOf(w)) : PokeI(#NST_REPORT+280,MathBitsOf(h))
  PokeI(#NST_REPORT+288,MathBitsOf(r)) : PokeI(#NST_REPORT+296,MathBitsOf(g))
  PokeI(#NST_REPORT+304,MathBitsOf(b)) : PokeI(#NST_REPORT+312,MathBitsOf(a))
  ProcedureReturn 0
EndProcedure
Procedure.i NstText(context.i,font.i,x.f,y.f,*text,r.f,g.f,b.f,a.f)
  NstContextCheck(context,6)
  If nstCalls[6]=1
    PokeI(#NST_REPORT+384,font) : PokeI(#NST_REPORT+392,MathBitsOf(x))
    PokeI(#NST_REPORT+400,MathBitsOf(y)) : PokeI(#NST_REPORT+408,PeekA(*text))
    PokeI(#NST_REPORT+416,MathBitsOf(r)) : PokeI(#NST_REPORT+424,MathBitsOf(g))
    PokeI(#NST_REPORT+432,MathBitsOf(b)) : PokeI(#NST_REPORT+440,MathBitsOf(a))
  EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i NstWidth(context.i,font.i,*text)
  NstContextCheck(context,7)
  If nstBadMetrics<>0 : ProcedureReturn #NEON_SERVICE_ERR_PROVIDER : EndIf
  ProcedureReturn 2457600
EndProcedure
Procedure.i NstHeight(context.i,font.i)
  NstContextCheck(context,8)
  If nstBadMetrics<>0 : ProcedureReturn #NEON_SERVICE_ERR_PROVIDER : EndIf
  ProcedureReturn 1196032
EndProcedure
Procedure.i NstPolygon(context.i,x.f,y.f,rx.f,ry.f,sides.i,r.f,g.f,b.f,a.f,solid.i)
  NstContextCheck(context,9)
  If nstCalls[9]=1
    PokeI(#NST_REPORT+448,MathBitsOf(x)) : PokeI(#NST_REPORT+456,MathBitsOf(y))
    PokeI(#NST_REPORT+464,MathBitsOf(rx)) : PokeI(#NST_REPORT+472,MathBitsOf(ry))
    PokeI(#NST_REPORT+480,sides) : PokeI(#NST_REPORT+488,MathBitsOf(r))
    PokeI(#NST_REPORT+496,MathBitsOf(g)) : PokeI(#NST_REPORT+504,MathBitsOf(b))
    PokeI(#NST_REPORT+512,MathBitsOf(a)) : PokeI(#NST_REPORT+520,solid)
  EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i NstPrepare(context.i,font.i,*text)
  NstContextCheck(context,10) : ProcedureReturn 0
EndProcedure
Procedure.i NstRegister(context.i,slot.i,role.i,pixels.i)
  NstContextCheck(context,11) : ProcedureReturn 65537
EndProcedure
Procedure.i NstError(context.i)
  NstContextCheck(context,12) : ProcedureReturn 0
EndProcedure
Declare.i NstDispatch(op.i,context.i,request.i,bytes.i)
Procedure NstMakeApi(*api.NeonServiceApi)
  *api\magic=#NEON_SERVICE_MAGIC : *api\major=1 : *api\minor=0
  *api\bytes=SizeOf(NeonServiceApi) : *api\flags=#NEON_SERVICE_VULKAN | #NEON_SERVICE_FONT_REFS : *api\maxFonts=8
  *api\dispatch=@NstDispatch
EndProcedure
Procedure.i NstDispatch(op.i,context.i,request.i,bytes.i)
  Protected *api.NeonServiceApi=request
  Protected *colour.NeonServiceColour=request
  Protected *box.NeonServiceBoxRequest=request
  Protected *text.NeonServiceTextRequest=request
  Protected *measure.NeonServiceMeasureRequest=request
  Protected *polygon.NeonServicePolygonRequest=request
  Protected *font.NeonServiceFontRequest=request
  Select op
    Case #NEON_SERVICE_QUERY
      If request=0 Or bytes<>48 Or context<>0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      NstMakeApi(*api)
      If nstPartial<>0 : *api\dispatch=0 : EndIf
      ProcedureReturn nstPositive
    Case #NEON_SERVICE_OPEN
      If request=0 Or bytes<>40 Or context<>0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      ProcedureReturn NstOpen(request,bytes)
    Case #NEON_SERVICE_CLOSE
      If request<>0 Or bytes<>0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      ProcedureReturn NstClose(context)
    Case #NEON_SERVICE_BEGIN
      If request=0 Or bytes<>16 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      ProcedureReturn NstBegin(context,*colour\r,*colour\g,*colour\b,*colour\a)
    Case #NEON_SERVICE_END
      If request<>0 Or bytes<>0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      ProcedureReturn NstEnd(context)
    Case #NEON_SERVICE_ABORT
      If request<>0 Or bytes<>0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      ProcedureReturn NstAbort(context)
    Case #NEON_SERVICE_BOX
      If request=0 Or bytes<>32 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      ProcedureReturn NstBox(context,*box\x,*box\y,*box\w,*box\h,*box\r,*box\g,*box\b,*box\a)
    Case #NEON_SERVICE_TEXT
      If request=0 Or bytes<>40 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      ProcedureReturn NstText(context,*text\font,*text\x,*text\y,*text\text,*text\r,*text\g,*text\b,*text\a)
    Case #NEON_SERVICE_WIDTH
      If request=0 Or bytes<>16 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      ProcedureReturn NstWidth(context,*measure\font,*measure\text)
    Case #NEON_SERVICE_HEIGHT
      If request=0 Or bytes<>16 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      ProcedureReturn NstHeight(context,*measure\font)
    Case #NEON_SERVICE_POLYGON
      If request=0 Or bytes<>48 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      ProcedureReturn NstPolygon(context,*polygon\x,*polygon\y,*polygon\rx,*polygon\ry,*polygon\sides,*polygon\r,*polygon\g,*polygon\b,*polygon\a,*polygon\solid)
    Case #NEON_SERVICE_PREPARE
      If request=0 Or bytes<>16 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      ProcedureReturn NstPrepare(context,*measure\font,*measure\text)
    Case #NEON_SERVICE_FONT_REGISTER
      If request=0 Or bytes<>24 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      ProcedureReturn NstRegister(context,*font\slot,*font\role,*font\pixels)
    Case #NEON_SERVICE_ERROR
      If request<>0 Or bytes<>0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      ProcedureReturn NstError(context)
  EndSelect
  ProcedureReturn #NEON_SERVICE_ERR_ARGS
EndProcedure
Procedure.i Main(services.i)
  Protected i.i,before.i,old.i,realResult.i=999,actualMinor.i=-1
  For i=0 To 4095 : PokeA(#NST_REPORT+i,0) : Next
  NstCheck(SizeOf(NeonServiceApi),48) : NstCheck(SizeOf(NeonServiceSurface),40)
  NstCheck(NeonServiceOpen(),#NEON_SERVICE_ERR_UNBOUND)
  NstCheck(NeonServiceRetainedInstall(),#NRU_ERR_RENDERER)
  If services<>0
    actualMinor=PeekL(services+8)
    If PeekL(services+4)=1 And actualMinor<8 : realResult=NeonServiceBind(services,#NEON_SERVICE_VULKAN) : EndIf
  EndIf
  PokeI(#NST_REPORT+192,actualMinor) : PokeI(#NST_REPORT+200,realResult)
  PokeL(@nstTable[0],$53564E41) : PokeL(@nstTable[0]+4,1)
  PokeL(@nstTable[0]+8,7) : PokeL(@nstTable[0]+12,200)
  PokeI(@nstTable[0]+16+38*8,@NstDispatch)
  NstCheck(NeonServiceBind(@nstTable[0],1),#NEON_SERVICE_ERR_ABI)
  PokeL(@nstTable[0]+8,8) : PokeL(@nstTable[0]+12,38)
  NstCheck(NeonServiceBind(@nstTable[0],1),#NEON_SERVICE_ERR_ABI)
  PokeL(@nstTable[0]+12,39) : PokeI(@nstTable[0]+16+38*8,0)
  NstCheck(NeonServiceBind(@nstTable[0],1),#NEON_SERVICE_ERR_UNBOUND)
  PokeI(@nstTable[0]+16+38*8,@NstDispatch) : nstPartial=1
  NstCheck(NeonServiceBind(@nstTable[0],1),#NEON_SERVICE_ERR_PROVIDER)
  nstPartial=0 : nstPositive=1
  NstCheck(NeonServiceBind(@nstTable[0],1),#NEON_SERVICE_ERR_PROVIDER)
  nstPositive=0 : NstCheck(NeonServiceBind(@nstTable[0],1),0)
  NstMakeApi(@nstApi) : nstApi\dispatch=0
  NstCheck(NeonServiceBindApi(@nstApi,48,1),#NEON_SERVICE_ERR_PROVIDER)
  NstCheck(NeonServiceOpen(),0)
  NstCheck(nstReentrant,#NEON_SERVICE_ERR_BUSY)
  NstCheck(NeonServiceWidth(),1280) : NstCheck(NeonServiceHeight(),800)
  NstCheck(NeonServiceReady(),1) : old=NeonServiceContext()
  NstCheck(NeonServiceBind(@nstTable[0],1),#NEON_SERVICE_ERR_BUSY)
  nstCloseFail=-444
  NstCheck(NeonServiceClose(),-444) : NstCheck(NeonServiceContext(),old)
  NstCheck(NeonServiceReady(),0) : NstCheck(NeonServiceUnbind(),#NEON_SERVICE_ERR_BUSY)
  NstCheck(NeonServiceBegin(0.0,0.0,0.0,1.0),#NEON_SERVICE_ERR_STATE)
  nstCloseFail=0 : NstCheck(NeonServiceClose(),0)
  nstBadSurface=1 : nstCloseFail=-445
  NstCheck(NeonServiceOpen(),-445) : NstCheck(Bool(NeonServiceContext()>0),1)
  NstCheck(NeonServiceReady(),0) : NstCheck(NeonServiceOpen(),#NEON_SERVICE_ERR_BUSY)
  nstCloseFail=0 : NstCheck(NeonServiceClose(),0) : nstBadSurface=0
  NstCheck(NeonServiceOpen(),0)
  NstCheck(NeonServiceFontRegister(4,1,16),65537)
  NstCheck(NeonServicePrepare(0,"route"),0)
  NstCheck(MathBitsOf(NeonServiceTextWidth(0,"route")),MathBitsOf(37.5))
  NstCheck(MathBitsOf(NeonServiceLineHeight(0)),MathBitsOf(18.25))
  nstBadMetrics=1
  NstCheck(MathBitsOf(NeonServiceTextWidth(0,"route")),MathBitsOf(-1.0))
  NstCheck(NeonServiceError(),#NEON_SERVICE_ERR_PROVIDER)
  NstCheck(MathBitsOf(NeonServiceLineHeight(0)),MathBitsOf(-1.0)) : nstBadMetrics=0
  NstCheck(NeonServiceBegin(0.0,0.0,0.0,1.0),0)
  NstCheck(nstReentrant,#NEON_SERVICE_ERR_BUSY) : NstCheck(NeonServiceFrameOpen(),1)
  before=nstCalls[2]
  NstCheck(NeonServiceBegin(0.0,0.0,0.0,1.0),#NEON_SERVICE_ERR_STATE) : NstCheck(nstCalls[2],before)
  NstCheck(NeonServicePrepare(0,"route"),#NEON_SERVICE_ERR_STATE)
  NstCheck(NeonServiceFontRegister(4,0,24),0)
  NstCheck(NeonServiceBox(0.25,0.5,3.75,4.125,0.1,0.2,0.3,0.4),0)
  NstCheck(NeonServiceText(0,1.25,2.5,"route",1.0,0.5,0.25,1.0),0)
  NstCheck(NeonServicePolygon(4.0,5.0,6.0,7.0,16,0.1,0.2,0.3,1.0,1),0)
  ; Preserve the independently checked direct-call float arguments before UI.
  For i=0 To 7 : PokeI(#NST_REPORT+320+i*8,PeekI(#NST_REPORT+256+i*8)) : Next
  nstEndFail=-446 : NstCheck(NeonServiceEnd(),-446)
  NstCheck(NeonServiceFrameOpen(),1)
  before=nstCalls[5] : NstCheck(NeonServiceBox(0.0,0.0,1.0,1.0,1.0,1.0,1.0,1.0),#NEON_SERVICE_ERR_STATE)
  NstCheck(nstCalls[5],before) : NstCheck(NeonServiceEnd(),#NEON_SERVICE_ERR_STATE)
  nstAbortFail=-447 : NstCheck(NeonServiceAbort(),-447) : NstCheck(NeonServiceFrameOpen(),1)
  nstCloseFail=-448 : old=NeonServiceContext()
  NstCheck(NeonServiceClose(),-448) : NstCheck(NeonServiceContext(),old)
  NstCheck(NeonServiceReady(),0)
  nstCloseFail=0 : nstAbortFail=0 : nstEndFail=0 : NstCheck(NeonServiceClose(),0)
  NstCheck(NeonServiceOpen(),0) : nstPositive=1
  NstCheck(NeonServiceBegin(0.0,0.0,0.0,1.0),#NEON_SERVICE_ERR_PROVIDER)
  NstCheck(NeonServiceFrameOpen(),0) : nstPositive=0
  NstCheck(NeonServiceBegin(0.0,0.0,0.0,1.0),0)
  nstPositive=1 : NstCheck(NeonServiceEnd(),#NEON_SERVICE_ERR_PROVIDER)
  nstPositive=0 : NstCheck(NeonServiceAbort(),0) : NstCheck(NeonServiceFrameOpen(),0)
  NstCheck(NeonServiceRetainedInstall(),0)
  NstCheck(NeonRetainedConfigure(@nstArena[0],1024,2,64),0)
  NstCheck(NeonRetainedViewport(0.0,0.0,1280.0,800.0,1280.0,800.0),0)
  NstCheck(NeonRetainedFontSet(0),0)
  NstCheck(Bool(NeonRetainedAddLabel(1,20.0,20.0,"pure service UI")<>0),1)
  NstCheck(Bool(NeonRetainedAddButton(2,40.0,120.0,200.0,40.0,"Start",0,0)<>0),1)
  NstCheck(NeonRetainedPrepare(),0)
  NstCheck(NeonServiceBegin(0.0,0.0,0.0,1.0),0)
  NstCheck(NeonRetainedDrawUI(0.0),0)
  NstCheck(NeonServiceEnd(),0) : NstCheck(NeonServiceProviderError(),0)
  NstCheck(NeonServiceClose(),0) : NstCheck(NeonServiceUnbind(),0)
  NstCheck(NeonServiceOpen(),#NEON_SERVICE_ERR_UNBOUND)
  NstCheck(NeonServiceContext(),0) : NstCheck(NeonServiceReady(),0) : NstCheck(NeonServiceFrameOpen(),0)
  NstCheck(nstContextErrors,0)
  PokeI(#NST_REPORT,$4E534331) : PokeI(#NST_REPORT+8,1)
  PokeI(#NST_REPORT+16,nstFailure) : PokeI(#NST_REPORT+24,nstChecks)
  PokeI(#NST_REPORT+32,SizeOf(NeonServiceApi)) : PokeI(#NST_REPORT+40,SizeOf(NeonServiceSurface))
  For i=0 To 12 : PokeI(#NST_REPORT+48+i*8,nstCalls[i]) : Next
  PokeI(#NST_REPORT+152,nstContextErrors)
  PokeI(#NST_REPORT+160,NeonServiceContext()) : PokeI(#NST_REPORT+168,NeonServiceReady()) : PokeI(#NST_REPORT+176,NeonServiceFrameOpen())
  PokeI(#NST_REPORT+184,#PMF_CHIP)
  ProcedureReturn nstFailure
EndProcedure

; SPDX-License-Identifier: MIT
EnableFloatingPoint
XIncludeFile "Anvil/Math/float32.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_mapping.pbi"
XIncludeFile "Anvil/Graphics/neon_service_font_spacing.pbi"
XIncludeFile "Anvil/Graphics/neon_service_font_controls.pbi"
Global ncfChecks.i,ncfFailure.i,ncfMockCalls.i
Procedure NcfCheck(actual.i,expected.i)
 PokeI(#NCF_REPORT+256+ncfChecks*16,actual) : PokeI(#NCF_REPORT+264+ncfChecks*16,expected)
 ncfChecks=ncfChecks+1
 If actual<>expected And ncfFailure=0 : ncfFailure=ncfChecks : EndIf
EndProcedure
Procedure.i NcfMock(op.i,context.i,request.i,bytes.i)
 Protected *surface.NeonServiceSurface
 If op=#NEON_SERVICE_OPEN
  *surface=request : *surface\bytes=40 : *surface\logicalW=1280 : *surface\logicalH=800
  *surface\flags=511 : *surface\maxFonts=32 : ProcedureReturn 55
 EndIf
 If op=#NEON_SERVICE_CLOSE : ProcedureReturn 0 : EndIf
 ncfMockCalls=ncfMockCalls+1 : ProcedureReturn #NEON_SERVICE_ERR_PROVIDER
EndProcedure

Procedure.i NcfPoison(op.i,context.i,request.i,bytes.i)
 ProcedureReturn #NEON_SERVICE_ERR_PROVIDER
EndProcedure

Global ncfPlain.i
Procedure NcfBox(x.f,y.f,gold.i)
 Protected r.f=1.0,g.f=1.0,b.f=1.0
 If gold<>0 : g=0.8 : b=0.2 : EndIf
 NcfCheck(NeonServiceBoxMapped(x+0.0,y+0.0,7.0,1.0,r,g,b,1.0,1,1),0)
 NcfCheck(NeonServiceBoxMapped(x+0.0,y+11.0,7.0,1.0,r,g,b,1.0,1,1),0)
 NcfCheck(NeonServiceBoxMapped(x+0.0,y+1.0,1.0,10.0,r,g,b,1.0,1,1),0)
 NcfCheck(NeonServiceBoxMapped(x+6.0,y+1.0,1.0,10.0,r,g,b,1.0,1,1),0)
EndProcedure
Procedure.i Main(services.i)
 Protected i.i,p.i,f.i,h.i,api.NeonServiceApi,request.NeonServiceFontControlsRequest
 For i=0 To #NCF_REPORT_BYTES-1 : PokeA(#NCF_REPORT+i,0) : Next
 PokeI(#NCF_REPORT,$4E434631) : PokeI(#NCF_REPORT+8,1)
 api\magic=#NEON_SERVICE_MAGIC : api\major=1 : api\minor=6 : api\bytes=48
 api\flags=511 : api\maxFonts=32 : api\dispatch=@NcfMock
 NcfCheck(SizeOf(NeonServiceFontControlsRequest),16)
 NcfCheck(NeonServiceBindApi(@api,48,256),-21501)
 NcfCheck(NeonServiceBindApi(@api,48,2),0)
 api\dispatch=@NcfPoison
 NcfCheck(NeonServiceBindApi(@api,48,256),-21501)
 api\dispatch=@NcfMock
 NcfCheck(NeonServiceOpen(),0)
 NcfCheck(NeonServiceFontSetShowControls(65537,1),-21501)
 NcfCheck(ncfMockCalls,0)
 NcfCheck(NeonServiceClose(),0)
 NcfCheck(NeonServiceUnbind(),0)
 NcfCheck(NeonServiceBind(services,511),0)
 NcfCheck(NeonServiceOpen(),0)
 NcfCheck(NeonServiceCanvas(640,400),0)
 p=NeonServiceFontRegister(0,1,12)
 NcfCheck(Bool(p>3),1)
 NcfCheck(NeonServiceFontSetFixedAdvance(p,16.0),0)
 f=NeonServiceFontRegister(0,1,12)
 NcfCheck(Bool(f>3),1)
 NcfCheck(NeonServiceFontSetFixedAdvance(f,16.0),0)
 h=NeonServiceFontRegister(0,1,12)
 NcfCheck(Bool(h>3),1)
 NcfCheck(NeonServiceFontSetFixedAdvance(h,16.0),0)
 NcfCheck(NeonServiceFontSetShowControls(f,0),0)
 NcfCheck(NeonServiceFontSetShowControls(h,1),0)
 NcfCheck(NeonServiceFontSetControlMode(h,0),0)
 NcfCheck(NeonServiceFontSetControlMode(h,2),0)
 NcfCheck(NeonServiceFontSetShowControls(1,0),-21500)
 NcfCheck(NeonServiceFontSetShowControls(h,2),-21500)
 NcfCheck(NeonServiceFontSetControlMode(h,-1),-21500)
 NcfCheck(NeonServiceFontSetControlMode(h,3),-21500)
 request\font=h : request\mode=2
 NcfCheck(NeonServiceRequestExtension(36,@request,8,0,256,7,0),-21500)
 request\mode=-1
 NcfCheck(NeonServiceRequestExtension(36,@request,16,0,256,7,0),-21500)
 request\mode=3
 NcfCheck(NeonServiceRequestExtension(36,@request,16,0,256,7,0),-21500)
 request\mode=2 : request\font=1
 NcfCheck(NeonServiceRequestExtension(36,@request,16,0,256,7,0),-21500)
 request\mode=2 : request\font=h+1000
 NcfCheck(NeonServiceRequestExtension(36,@request,16,0,256,7,0),-21500)
 request\font=h
 NcfCheck(MathBitsOf(NeonServiceTextWidth(f,?ncfMixed)),1119879168)
 NcfCheck(MathBitsOf(NeonServiceTextWidth(f,?ncfControls)),0)
 NcfCheck(MathBitsOf(NeonServiceTextWidth(h,?ncfShowText)),1111490560)
 NcfCheck(MathBitsOf(NeonServiceTextWidth(h,?ncfBreaks)),1115684864)
 NcfCheck(NeonServicePrepare(p,?ncfPlainText),0)
 NcfCheck(NeonServicePrepare(p,?ncfAV),0)
 NcfCheck(NeonServicePrepare(f,?ncfMixed),0)
 NcfCheck(NeonServicePrepare(f,?ncfControls),0)
 NcfCheck(NeonServicePrepare(f,?ncfShowText),0)
 NcfCheck(NeonServicePrepare(h,?ncfShowText),0)
 NcfCheck(NeonServicePrepare(h,?ncfBreaks),0)
 NcfCheck(NeonServicePrepare(h,?ncfDelText),0)
 NcfCheck(NeonServiceBegin(0.04,0.05,0.07,1.0),0)
 NcfCheck(NeonServiceFontSetShowControls(h,0),-21503)
 NcfCheck(NeonServiceRequestExtension(36,@request,16,1,256,7,0),-21503)
 NcfCheck(NeonServiceTextMapped(f,10.0,20.0,?ncfMixed,1.0,1.0,1.0,1.0,1,1),0)
 NcfCheck(NeonServiceTextMapped(p,200.0,20.0,?ncfPlainText,1.0,1.0,1.0,1.0,1,1),0)
 NcfCheck(NeonServiceTextMapped(h,10.0,50.0,?ncfShowText,1.0,1.0,1.0,1.0,1,1),0)
 NcfCheck(NeonServiceTextMapped(p,200.0,50.0,?ncfA,1.0,1.0,1.0,1.0,1,1),0)
 NcfBox(216.0,50.0,0)
 NcfCheck(NeonServiceTextMapped(p,232.0,50.0,?ncfV,1.0,1.0,1.0,1.0,1,1),0)
 NcfCheck(NeonServiceTextMapped(h,10.0,80.0,?ncfBreaks,1.0,1.0,1.0,1.0,1,1),0)
 NcfCheck(NeonServiceTextMapped(p,200.0,80.0,?ncfA,1.0,1.0,1.0,1.0,1,1),0)
 NcfBox(216.0,80.0,0)
 NcfBox(232.0,80.0,0)
 NcfCheck(NeonServiceTextMapped(p,248.0,80.0,?ncfV,1.0,1.0,1.0,1.0,1,1),0)
 NcfCheck(NeonServiceTextMapped(h,10.0,110.0,?ncfDelText,1.0,0.8,0.2,1.0,1,1),0)
 NcfCheck(NeonServiceTextMapped(p,200.0,110.0,?ncfA,1.0,0.8,0.2,1.0,1,1),0)
 NcfBox(216.0,110.0,1)
 NcfCheck(NeonServiceTextMapped(p,232.0,110.0,?ncfV,1.0,0.8,0.2,1.0,1,1),0)
 NcfCheck(NeonServiceTextMapped(f,10.0,140.0,?ncfControls,1.0,1.0,1.0,1.0,1,1),0)
 NcfCheck(NeonServiceTextMapped(f,10.0,170.0,?ncfShowText,1.0,1.0,1.0,1.0,1,1),0)
 NcfCheck(NeonServiceTextMapped(p,200.0,170.0,?ncfAV,1.0,1.0,1.0,1.0,1,1),0)
 NcfCheck(NeonServiceEnd(),0)
 NcfCheck(NeonServiceFontSetControlMode(h,0),0)
 PokeI(#NCF_REPORT+16,ncfFailure) : PokeI(#NCF_REPORT+24,ncfChecks)
 ProcedureReturn ncfFailure
EndProcedure
DataSection
ncfMixed:
 Data.a 65,9,86,10,65,13,84,127,65,1,82,0
ncfControls:
 Data.a 9,10,13,127,1,0
ncfShowText:
 Data.a 65,9,86,0
ncfBreaks:
 Data.a 65,13,10,86,0
ncfDelText:
 Data.a 65,127,86,0
ncfPlainText:
 Data.a 65,86,65,84,65,82,0
ncfAV:
 Data.a 65,86,0
ncfA:
 Data.a 65,0
ncfV:
 Data.a 86,0
EndDataSection

; SPDX-License-Identifier: MIT
EnableFloatingPoint
XIncludeFile "Anvil/Math/float32.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_mapping.pbi"
XIncludeFile "Anvil/Graphics/neon_service_font_spacing.pbi"
XIncludeFile "Anvil/Graphics/neon_service_font_snap.pbi"
Global nsfChecks.i,nsfFailure.i,nsfMockCalls.i
Procedure NsfCheck(actual.i,expected.i)
 PokeI(#NSF_REPORT+256+nsfChecks*16,actual) : PokeI(#NSF_REPORT+264+nsfChecks*16,expected)
 nsfChecks=nsfChecks+1
 If actual<>expected And nsfFailure=0 : nsfFailure=nsfChecks : EndIf
EndProcedure
Procedure.i NsfMock(op.i,context.i,request.i,bytes.i)
 Protected *surface.NeonServiceSurface
 If op=#NEON_SERVICE_OPEN
  *surface=request : *surface\bytes=40 : *surface\logicalW=1280 : *surface\logicalH=800
  *surface\flags=255 : *surface\maxFonts=32 : ProcedureReturn 55
 EndIf
 If op=#NEON_SERVICE_CLOSE : ProcedureReturn 0 : EndIf
 nsfMockCalls=nsfMockCalls+1 : ProcedureReturn #NEON_SERVICE_ERR_PROVIDER
EndProcedure

Procedure.i NsfPoison(op.i,context.i,request.i,bytes.i)
 ProcedureReturn #NEON_SERVICE_ERR_PROVIDER
EndProcedure
Procedure.i Main(services.i)
 Protected i.i,p.i,f.i,h.i,rc.i,api.NeonServiceApi,request.NeonServiceFontSnapRequest
 For i=0 To #NSF_REPORT_BYTES-1 : PokeA(#NSF_REPORT+i,0) : Next
 PokeI(#NSF_REPORT,$4E534631) : PokeI(#NSF_REPORT+8,1)
 api\magic=#NEON_SERVICE_MAGIC : api\major=1 : api\minor=5 : api\bytes=48
 api\flags=255 : api\maxFonts=32 : api\dispatch=@NsfMock
 NsfCheck(SizeOf(NeonServiceFontSnapRequest),16)
 NsfCheck(NeonServiceBindApi(@api,48,128),-21501)
 NsfCheck(NeonServiceBindApi(@api,48,2),0)
 api\dispatch=@NsfPoison
 NsfCheck(NeonServiceBindApi(@api,48,128),-21501)
 api\dispatch=@NsfMock
 ; A refused BindApi must preserve the last accepted dispatcher.
 NsfCheck(NeonServiceOpen(),0)
 NsfCheck(NeonServiceFontSetSnapToPixel(65537,0),-21501)
 NsfCheck(nsfMockCalls,0)
 NsfCheck(NeonServiceClose(),0)
 NsfCheck(NeonServiceUnbind(),0)
 NsfCheck(NeonServiceBind(services,255),0)
 NsfCheck(NeonServiceOpen(),0)
 NsfCheck(NeonServiceCanvas(640,400),0)
 p=NeonServiceFontRegister(0,1,12)
 NsfCheck(Bool(p>3),1)
 NsfCheck(NeonServiceFontSetFixedAdvance(p,16.0),0)
 f=NeonServiceFontRegister(0,1,12)
 NsfCheck(Bool(f>3),1)
 NsfCheck(NeonServiceFontSetFixedAdvance(f,16.0),0)
 h=NeonServiceFontRegister(0,1,12)
 NsfCheck(Bool(h>3),1)
 NsfCheck(NeonServiceFontSetFixedAdvance(h,16.0),0)
 NsfCheck(NeonServiceFontSetSnapToPixel(f,0),0)
 NsfCheck(NeonServiceFontSetSnapToPixel(h,0),0)
 NsfCheck(NeonServiceFontSetSnapToPixel(1,0),-21500)
 NsfCheck(NeonServiceFontSetSnapToPixel(f,-1),-21500)
 NsfCheck(NeonServiceFontSetSnapToPixel(f,2),-21500)
 request\font=f : request\enabled=0
 NsfCheck(NeonServiceRequestExtension(35,@request,8,0,128,6,0),-21500)
 request\enabled=-1
 NsfCheck(NeonServiceRequestExtension(35,@request,16,0,128,6,0),-21500)
 request\enabled=2
 NsfCheck(NeonServiceRequestExtension(35,@request,16,0,128,6,0),-21500)
 request\enabled=0 : request\font=1
 NsfCheck(NeonServiceRequestExtension(35,@request,16,0,128,6,0),-21500)
 request\font=f+1000
 NsfCheck(NeonServiceRequestExtension(35,@request,16,0,128,6,0),-21500)
 request\font=f
 NsfCheck(MathBitsOf(NeonServiceTextWidth(p,?nsfText)),1119879168)
 NsfCheck(NeonServicePrepare(p,?nsfText),0)
 NsfCheck(MathBitsOf(NeonServiceTextWidth(f,?nsfText)),1119879168)
 NsfCheck(NeonServicePrepare(f,?nsfText),0)
 NsfCheck(MathBitsOf(NeonServiceTextWidth(h,?nsfText)),1119879168)
 NsfCheck(NeonServicePrepare(h,?nsfText),0)
 NsfCheck(NeonServiceBegin(0.04,0.05,0.07,1.0),0)
 NsfCheck(NeonServiceFontSetSnapToPixel(f,1),-21503)
 NsfCheck(NeonServiceRequestExtension(35,@request,16,1,128,6,0),-21503)
 NsfCheck(NeonServiceTextMapped(p,10.375,20.375,?nsfText,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(p,200.0,20.0,?nsfChar0,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(p,216.0,20.0,?nsfChar1,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(p,232.0,20.0,?nsfChar2,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(p,248.0,20.0,?nsfChar3,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(p,264.0,20.0,?nsfChar4,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(p,280.0,20.0,?nsfChar5,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(f,10.375,50.375,?nsfText,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(h,200.375,50.375,?nsfChar0,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(h,216.375,50.375,?nsfChar1,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(h,232.375,50.375,?nsfChar2,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(h,248.375,50.375,?nsfChar3,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(h,264.375,50.375,?nsfChar4,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(h,280.375,50.375,?nsfChar5,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(f,10.0,80.0,?nsfText,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(p,200.0,80.0,?nsfChar0,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(p,216.0,80.0,?nsfChar1,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(p,232.0,80.0,?nsfChar2,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(p,248.0,80.0,?nsfChar3,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(p,264.0,80.0,?nsfChar4,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(p,280.0,80.0,?nsfChar5,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(f,10.375,110.375,?nsfText,1.0,0.8,0.2,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(h,200.375,110.375,?nsfChar0,1.0,0.8,0.2,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(h,216.375,110.375,?nsfChar1,1.0,0.8,0.2,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(h,232.375,110.375,?nsfChar2,1.0,0.8,0.2,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(h,248.375,110.375,?nsfChar3,1.0,0.8,0.2,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(h,264.375,110.375,?nsfChar4,1.0,0.8,0.2,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(h,280.375,110.375,?nsfChar5,1.0,0.8,0.2,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(f,10.375,140.375,?nsfText,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(h,200.375,140.375,?nsfChar0,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(h,216.375,140.375,?nsfChar1,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(h,232.375,140.375,?nsfChar2,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(h,248.375,140.375,?nsfChar3,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(h,264.375,140.375,?nsfChar4,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(h,280.375,140.375,?nsfChar5,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(f,10.375,170.375,?nsfText,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(h,200.375,170.375,?nsfChar0,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(h,216.375,170.375,?nsfChar1,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(h,232.375,170.375,?nsfChar2,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(h,248.375,170.375,?nsfChar3,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(h,264.375,170.375,?nsfChar4,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceTextMapped(h,280.375,170.375,?nsfChar5,1.0,1.0,1.0,1.0,1,1),0)
 NsfCheck(NeonServiceEnd(),0)
 NsfCheck(NeonServiceFontSetSnapToPixel(f,1),0)
 NsfCheck(MathBitsOf(NeonServiceTextWidth(f,?nsfText)),1119879168)
 ; Preserve the final GPU frame for the monitor return capture.
 ; Loader return cleanup closes and restores the resident service afterwards.
 PokeI(#NSF_REPORT+16,nsfFailure) : PokeI(#NSF_REPORT+24,nsfChecks)
 ProcedureReturn nsfFailure
EndProcedure
DataSection
nsfText:
 Data.a 65,86,65,84,65,82,0
nsfChar0:
 Data.a 65,0
nsfChar1:
 Data.a 86,0
nsfChar2:
 Data.a 65,0
nsfChar3:
 Data.a 84,0
nsfChar4:
 Data.a 65,0
nsfChar5:
 Data.a 82,0
EndDataSection

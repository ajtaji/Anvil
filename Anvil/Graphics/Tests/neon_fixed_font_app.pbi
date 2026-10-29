; SPDX-License-Identifier: MIT
EnableFloatingPoint
XIncludeFile "Anvil/Math/float32.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_mapping.pbi"
XIncludeFile "Anvil/Graphics/neon_service_font_spacing.pbi"
Global nfxChecks.i,nfxFailure.i,nfxMockCalls.i
Procedure NfxCheck(actual.i,expected.i)
 PokeI(#NFX_REPORT+256+nfxChecks*16,actual) : PokeI(#NFX_REPORT+264+nfxChecks*16,expected)
 nfxChecks=nfxChecks+1
 If actual<>expected And nfxFailure=0 : nfxFailure=nfxChecks : EndIf
EndProcedure
Procedure.i NfxMock(op.i,context.i,request.i,bytes.i)
 Protected *surface.NeonServiceSurface
 If op=#NEON_SERVICE_OPEN
  *surface=request : *surface\bytes=40 : *surface\logicalW=1280 : *surface\logicalH=800
  *surface\flags=127 : *surface\maxFonts=32 : ProcedureReturn 55
 EndIf
 If op=#NEON_SERVICE_CLOSE : ProcedureReturn 0 : EndIf
 nfxMockCalls=nfxMockCalls+1 : ProcedureReturn #NEON_SERVICE_ERR_PROVIDER
EndProcedure
Procedure.i Main(services.i)
 Protected i.i,p.i,f.i,h.i,rc.i,width.f,api.NeonServiceApi,request.NeonServiceFontAdvanceRequest
 For i=0 To #NFX_REPORT_BYTES-1 : PokeA(#NFX_REPORT+i,0) : Next
 PokeI(#NFX_REPORT,$4E465831) : PokeI(#NFX_REPORT+8,1)
 api\magic=#NEON_SERVICE_MAGIC : api\major=1 : api\minor=4 : api\bytes=48
 api\flags=127 : api\maxFonts=32 : api\dispatch=@NfxMock
 NfxCheck(SizeOf(NeonServiceFontAdvanceRequest),16)
 NfxCheck(NeonServiceBindApi(@api,48,64),-21501)
 NfxCheck(NeonServiceBindApi(@api,48,2),0)
 NfxCheck(NeonServiceOpen(),0)
 NfxCheck(NeonServiceFontSetFixedAdvance(65537,14.0),-21501)
 NfxCheck(nfxMockCalls,0)
 NfxCheck(NeonServiceClose(),0)
 NfxCheck(NeonServiceUnbind(),0)
 NfxCheck(NeonServiceBind(services,127),0)
 NfxCheck(NeonServiceOpen(),0)
 NfxCheck(NeonServiceCanvas(640,400),0)
 p=NeonServiceFontRegister(0,1,14)
 NfxCheck(Bool(p>3),1)
 f=NeonServiceFontRegister(0,1,14)
 NfxCheck(Bool(f>3),1)
 h=NeonServiceFontRegister(0,1,14)
 NfxCheck(Bool(h>3),1)
 width=NeonServiceTextWidth(p,?nfxText) : PokeL(#NFX_REPORT+128,MathBitsOf(width))
 NfxCheck(Bool(width>0.0),1)
 NfxCheck(NeonServiceFontSetFixedAdvance(f,14.0),0)
 NfxCheck(NeonServiceFontSetFixedAdvance(h,7.5),0)
 NfxCheck(MathBitsOf(NeonServiceTextWidth(f,?nfxText)),1125777408)
 NfxCheck(MathBitsOf(NeonServiceTextWidth(h,?nfxText)),1118109696)
 PokeL(#NFX_REPORT+132,MathBitsOf(NeonServiceTextWidth(p,?nfxText)))
 PokeL(#NFX_REPORT+136,MathBitsOf(NeonServiceTextWidth(1,?nfxText)))
 NfxCheck(NeonServiceFontSetFixedAdvance(1,7.0),-21500)
 NfxCheck(NeonServiceFontSetFixedAdvance(f,-1.0),-21500)
 NfxCheck(NeonServiceFontSetFixedAdvance(f,MathFromBits($7FC00000)),-21500)
 NfxCheck(NeonServiceFontSetFixedAdvance(f,MathFromBits($7F800000)),-21500)
 NfxCheck(NeonServiceFontSetFixedAdvance(f,0.00000001),-21500)
 request\font=f : request\advanceQ16=917504
 NfxCheck(NeonServiceRequestExtension(34,@request,8,0,64,5,0),-21500)
 request\advanceQ16=-1
 NfxCheck(NeonServiceRequestExtension(34,@request,16,0,64,5,0),-21500)
 request\advanceQ16=536870913
 NfxCheck(NeonServiceRequestExtension(34,@request,16,0,64,5,0),-21500)
 request\advanceQ16=917504 : request\font=1
 NfxCheck(NeonServiceRequestExtension(34,@request,16,0,64,5,0),-21500)
 request\font=f+1000
 NfxCheck(NeonServiceRequestExtension(34,@request,16,0,64,5,0),-21500)
 request\font=f
 NfxCheck(MathBitsOf(NeonServiceTextWidth(f,?nfxText)),1125777408)
 NfxCheck(NeonServicePrepare(p,?nfxText),0)
 NfxCheck(NeonServicePrepare(f,?nfxText),0)
 NfxCheck(NeonServicePrepare(h,?nfxText),0)
 NfxCheck(NeonServiceBegin(0.04,0.05,0.07,1.0),0)
 NfxCheck(NeonServiceFontSetFixedAdvance(f,99.0),-21503)
 NfxCheck(NeonServiceRequestExtension(34,@request,16,1,64,5,0),-21503)
 NfxCheck(NeonServiceText(p,20,40,?nfxText,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(1,340,40,?nfxText,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(f,20,96,?nfxText,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,340,96,?nfxChar0,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,354,96,?nfxChar1,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,368,96,?nfxChar2,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,382,96,?nfxChar3,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,396,96,?nfxChar4,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,410,96,?nfxChar5,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,424,96,?nfxChar6,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,438,96,?nfxChar7,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,452,96,?nfxChar8,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,466,96,?nfxChar9,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,480,96,?nfxChar10,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(h,20.25,152.25,?nfxText,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,340.25,152.25,?nfxChar0,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,347.75,152.25,?nfxChar1,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,355.25,152.25,?nfxChar2,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,362.75,152.25,?nfxChar3,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,370.25,152.25,?nfxChar4,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,377.75,152.25,?nfxChar5,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,385.25,152.25,?nfxChar6,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,392.75,152.25,?nfxChar7,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,400.25,152.25,?nfxChar8,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,407.75,152.25,?nfxChar9,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,415.25,152.25,?nfxChar10,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(f,20,208,?nfxText,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,340,208,?nfxChar0,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,354,208,?nfxChar1,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,368,208,?nfxChar2,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,382,208,?nfxChar3,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,396,208,?nfxChar4,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,410,208,?nfxChar5,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,424,208,?nfxChar6,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,438,208,?nfxChar7,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,452,208,?nfxChar8,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,466,208,?nfxChar9,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,480,208,?nfxChar10,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,20,264,?nfxText,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(1,340,264,?nfxText,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(h,20.25,320.25,?nfxText,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,340.25,320.25,?nfxChar0,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,347.75,320.25,?nfxChar1,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,355.25,320.25,?nfxChar2,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,362.75,320.25,?nfxChar3,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,370.25,320.25,?nfxChar4,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,377.75,320.25,?nfxChar5,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,385.25,320.25,?nfxChar6,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,392.75,320.25,?nfxChar7,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,400.25,320.25,?nfxChar8,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,407.75,320.25,?nfxChar9,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceText(p,415.25,320.25,?nfxChar10,1.0,1.0,1.0,1.0),0)
 NfxCheck(NeonServiceEnd(),0)
 NfxCheck(NeonServiceFontSetFixedAdvance(f,0.0),0)
 PokeL(#NFX_REPORT+140,MathBitsOf(NeonServiceTextWidth(f,?nfxText)))
 NfxCheck(NeonServiceFontSetFixedAdvance(f,14.0),0)
 NfxCheck(MathBitsOf(NeonServiceTextWidth(f,?nfxText)),1125777408)
 PokeI(#NFX_REPORT+16,nfxFailure) : PokeI(#NFX_REPORT+24,nfxChecks)
 ProcedureReturn nfxFailure
EndProcedure
DataSection
nfxText:
 Data.a 65,86,65,84,65,82,32,99,97,102,195,169,0
nfxChar0:
 Data.a 65,0
nfxChar1:
 Data.a 86,0
nfxChar2:
 Data.a 65,0
nfxChar3:
 Data.a 84,0
nfxChar4:
 Data.a 65,0
nfxChar5:
 Data.a 82,0
nfxChar6:
 Data.a 32,0
nfxChar7:
 Data.a 99,0
nfxChar8:
 Data.a 97,0
nfxChar9:
 Data.a 102,0
nfxChar10:
 Data.a 195,169,0
EndDataSection

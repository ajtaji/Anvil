; SPDX-License-Identifier: MIT
; Real owned-font service test. The existing Lato file face in slot0 must
; survive all three application slots and context/return cleanup.
EnableFloatingPoint
XIncludeFile "Anvil/Math/float32.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Hal/file_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_font.pbi"
Global Dim nfbInput.q[131072]
Global Dim nfbFonts.i[3]
Global nfbChecks.i,nfbFailure.i,nfbBad.l
Procedure NfbCheck(actual.i,expected.i)
  nfbChecks=nfbChecks+1
  PokeI(#NFB_REPORT+128+nfbChecks*16,actual) : PokeI(#NFB_REPORT+136+nfbChecks*16,expected)
  If actual<>expected And nfbFailure=0 : nfbFailure=nfbChecks : EndIf
  PokeI(#NFB_REPORT+16,nfbFailure) : PokeI(#NFB_REPORT+24,nfbChecks)
EndProcedure
Procedure.i NfbUnavailable(op.i,context.i,request.i,bytes.i)
  ProcedureReturn #NEON_SERVICE_ERR_UNBOUND
EndProcedure
Procedure.i Main(services.i)
  Protected i.i,old.i,font.i,boot.i,prior.i,context.i,api.NeonServiceApi
  Protected load.NeonServiceFontLoadRequest,width.i
  For i=0 To 4095 Step 8 : PokeI(#NFB_REPORT+i,0) : Next
  PokeI(#NFB_REPORT,$4E464231) : PokeI(#NFB_REPORT+8,1)
  NfbCheck(SizeOf(NeonServiceFontLoadRequest),32)
  NfbCheck(SizeOf(NeonServiceFontUnloadRequest),8)
  api\magic=#NEON_SERVICE_MAGIC : api\major=1 : api\minor=1 : api\bytes=48
  api\flags=15 : api\maxFonts=32 : api\dispatch=@NfbUnavailable
  NfbCheck(NeonServiceBindApi(@api,48,8),#NEON_SERVICE_ERR_ABI)
  NfbCheck(NeonServiceBind(services,#NEON_SERVICE_VULKAN | #NEON_SERVICE_FONT_REFS | #NEON_SERVICE_FONT_BYTES),0)
  NfbCheck(AnvilFileBind(services),0)
  NfbCheck(NeonServiceOpen(),0)
  If nfbFailure<>0 : ProcedureReturn nfbFailure : EndIf
  context=NeonServiceContext()
  boot=NeonServiceFontRegister(4,0,28) : NfbCheck(Bool(boot>3),1)
  prior=NeonServiceFontRegister(0,0,28) : NfbCheck(Bool(prior>boot),1)
  NfbCheck(NeonServiceFontUnload(prior),#NEON_SERVICE_ERR_STALE)
  NfbCheck(NeonServiceFontLoadMemory(@nfbBad,4,0,28),0)
  NfbCheck(NeonServiceError(),#NEON_SERVICE_ERR_FORMAT)
  load\data=$FE000000 : load\bytes=656568 : load\role=0 : load\pixels=28
  NfbCheck(NeonServiceRequestExtension(#NEON_SERVICE_FONT_LOAD,@load,32,0,8,2,0),#NEON_SERVICE_ERR_ARGS)
  nfbFonts[0]=NeonServiceFontLoadFile("2:/fonts/Lato-Regular.ttf",@nfbInput[0],1048576,0,28)
  NfbCheck(Bool(nfbFonts[0]>prior),1)
  nfbFonts[1]=NeonServiceFontLoadMemory(@nfbInput[0],656568,1,42)
  NfbCheck(Bool(nfbFonts[1]>nfbFonts[0]),1)
  nfbFonts[2]=NeonServiceFontLoadMemory(@nfbInput[0],656568,2,28)
  NfbCheck(Bool(nfbFonts[2]>nfbFonts[1]),1)
  NfbCheck(NeonServiceFontLoadMemory(@nfbInput[0],656568,3,28),0)
  NfbCheck(NeonServiceError(),#NEON_SERVICE_ERR_CAPACITY)
  width=MathBitsOf(NeonServiceTextWidth(nfbFonts[0],"Neon owned font bytes"))
  NfbCheck(Bool(width>0),1)
  For i=0 To 1048575 : PokeA(@nfbInput[0]+i,0) : Next
  NfbCheck(MathBitsOf(NeonServiceTextWidth(nfbFonts[0],"Neon owned font bytes")),width)
  NfbCheck(NeonServicePrepare(nfbFonts[2],"Retire the selected owned face"),0)
  old=nfbFonts[2]
  NfbCheck(NeonServiceFontUnload(old),0)
  NfbCheck(NeonServiceFontUnload(old),#NEON_SERVICE_ERR_STALE)
  NfbCheck(NeonServicePrepare(old,"stale"),-21310)
  NfbCheck(NeonServicePrepare(prior,"Preexisting face survives"),0)
  NfbCheck(AnvilFileReadWhole("2:/fonts/Lato-Regular.ttf",@nfbInput[0],1048576),656568)
  nfbFonts[2]=NeonServiceFontLoadMemory(@nfbInput[0],656568,2,28)
  NfbCheck(Bool(nfbFonts[2]>old),1)
  For i=0 To 1048575 : PokeA(@nfbInput[0]+i,0) : Next
  NfbCheck(NeonServicePrepare(nfbFonts[0],"Neon owned font bytes"),0)
  NfbCheck(NeonServiceBegin(0.0,0.0,0.0,1.0),0)
  NfbCheck(NeonServiceFontUnload(nfbFonts[0]),#NEON_SERVICE_ERR_STATE)
  NfbCheck(NeonServiceText(nfbFonts[0],60.0,100.0,"Neon owned font bytes",1.0,1.0,1.0,1.0),0)
  NfbCheck(NeonServiceEnd(),0)
  NfbCheck(NeonServiceClose(),0)
  NfbCheck(NeonServiceOpen(),0)
  NfbCheck(Bool(NeonServiceContext()>context),1)
  NfbCheck(NeonServicePrepare(nfbFonts[0],"stale context"),#NEON_SERVICE_ERR_ARGS)
  boot=NeonServiceFontRegister(4,0,28) : NfbCheck(Bool(boot>3),1)
  prior=NeonServiceFontRegister(0,0,28) : NfbCheck(Bool(prior>boot),1)
  NfbCheck(AnvilFileReadWhole("2:/fonts/Lato-Regular.ttf",@nfbInput[0],1048576),656568)
  For i=0 To 2
    nfbFonts[i]=NeonServiceFontLoadMemory(@nfbInput[0],656568,i,28)
    NfbCheck(Bool(nfbFonts[i]>prior),1)
  Next
  NfbCheck(NeonServiceFontLoadMemory(@nfbInput[0],656568,3,28),0)
  NfbCheck(NeonServiceError(),#NEON_SERVICE_ERR_CAPACITY)
  For i=0 To 1048575 : PokeA(@nfbInput[0]+i,0) : Next
  NfbCheck(AnvilFileRetainedHandle(),0) : NfbCheck(AnvilFileUnbind(),0)
  NfbCheck(NeonServicePrepare(nfbFonts[0],"Neon owned font bytes"),0)
  NfbCheck(NeonServicePrepare(prior,"Neon owned font bytes"),0)
  NfbCheck(NeonServicePrepare(boot,"Neon owned font bytes"),0)
  NfbCheck(NeonServiceBegin(0.0,0.0,0.0,1.0),0)
  NfbCheck(NeonServiceText(nfbFonts[0],60.0,140.0,"Neon owned font bytes",1.0,1.0,1.0,1.0),0)
  NfbCheck(NeonServiceText(prior,60.0,220.0,"Neon owned font bytes",1.0,1.0,1.0,1.0),0)
  NfbCheck(NeonServiceText(boot,60.0,300.0,"Neon owned font bytes",1.0,1.0,1.0,1.0),0)
  NfbCheck(NeonServiceEnd(),0)
  PokeI(#NFB_REPORT+32,NeonServiceContext())
  PokeI(#NFB_REPORT+40,width)
  ProcedureReturn nfbFailure
EndProcedure

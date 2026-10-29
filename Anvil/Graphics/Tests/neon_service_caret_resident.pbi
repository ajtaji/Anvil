; SPDX-License-Identifier: MIT
; Pure application: all font layout and rendering live in the monitor.
EnableFloatingPoint
XIncludeFile "Anvil/Math/float32.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_font_spacing.pbi"
XIncludeFile "Anvil/Graphics/neon_service_font_controls.pbi"
XIncludeFile "Anvil/Graphics/neon_service_font_caret.pbi"
Global nrcCount.i,nrcFailure.i,nrcFont.i,nrcOld.i,nrcContext.i
Global nrc.NeonServiceFontCaretRequest
Procedure NrcCheck(value.i,expected.i)
 PokeI($E1C00400+nrcCount*16,value) : PokeI($E1C00408+nrcCount*16,expected)
 nrcCount=nrcCount+1
 If value<>expected And nrcFailure=0 : nrcFailure=nrcCount : EndIf
 PokeI($E1C00010,nrcFailure) : PokeI($E1C00018,nrcCount)
EndProcedure
Procedure.i Main(services.i)
 Protected i.i,position.f
 For i=0 To 16383 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$4E435231) : PokeI($E1C00008,1)

 NrcCheck(NeonServiceBind(services,#NEON_SERVICE_FONT_CARETS|#NEON_SERVICE_FONT_REFS),0)
 If nrcFailure<>0 : ProcedureReturn nrcFailure : EndIf
 NrcCheck(NeonServiceOpen(),0)
 If nrcFailure<>0 : ProcedureReturn nrcFailure : EndIf
 nrcContext=NeonServiceContext() : nrcFont=NeonServiceFontRegister(4,1,12)
 NrcCheck(Bool(nrcFont>3),1)
 If nrcFailure<>0 : NeonServiceClose() : ProcedureReturn nrcFailure : EndIf
 NrcCheck(NeonServiceFontSetFixedAdvance(nrcFont,16.0),0)
 NrcCheck(NeonServiceFontSetShowControls(nrcFont,0),0)
 nrc\font=nrcFont : nrc\text=?text : nrc\textBytes=7 : nrc\column=3
 NrcCheck(NeonServiceFontCaretQuery(48,@nrc),0)
 NrcCheck(nrc\resultX,3145728)
 NrcCheck(nrc\resultByte,3)
 nrc\xQ16=1572864
 NrcCheck(NeonServiceFontCaretQuery(49,@nrc),0)
 NrcCheck(nrc\resultColumn,2)
 nrc\column=8
 NrcCheck(NeonServiceFontCaretQuery(50,@nrc),0)
 NrcCheck(nrc\resultX,8388608)
 NrcCheck(NeonServiceFontCaretQuery(51,@nrc),0)
 NrcCheck(nrc\resultColumn,2)
 nrc\text=?hidden : nrc\textBytes=8 : nrc\column=3
 NrcCheck(NeonServiceFontCaretQuery(48,@nrc),0)
 NrcCheck(nrc\resultX,2097152)
 NrcCheck(nrc\resultByte,6)
 nrc\text=?text : nrc\textBytes=7 : nrc\resultX=123 : nrc\resultY=456 : nrc\resultByte=789 : nrc\resultColumn=17
 NrcCheck(nscDispatch(48,nrcContext,0,80),-21500)
 NrcCheck(nscDispatch(48,nrcContext,@nrc+1,80),-21500)
 NrcCheck(nscDispatch(48,nrcContext,@nrc,79),-21500)
 NrcCheck(nscDispatch(48,nrcContext,$200000,80),-21500)
 NrcCheck(nscDispatch(48,nrcContext,$7FFFFFFFFFFFFFF8,80),-21500)
 NrcCheck(nscDispatch(48,nrcContext+1,@nrc,80),-21503)
 nrc\font=nrcFont+65536
 NrcCheck(nscDispatch(48,nrcContext,@nrc,80),-21506)
 nrc\font=nrcFont : nrc\text=$200000
 NrcCheck(nscDispatch(48,nrcContext,@nrc,80),-21500)
 nrc\text=?text : nrc\textBytes=8
 NrcCheck(nscDispatch(48,nrcContext,@nrc,80),-21500)
 nrc\textBytes=6
 NrcCheck(nscDispatch(48,nrcContext,@nrc,80),-21500)
 nrc\textBytes=7 : nrc\column=7
 NrcCheck(nscDispatch(48,nrcContext,@nrc,80),-21312)
 NrcCheck(nrc\resultX,123)
 NrcCheck(nrc\resultY,456)
 NrcCheck(nrc\resultByte,789)
 NrcCheck(nrc\resultColumn,17)
 NrcCheck(NeonServicePrepare(nrcFont,?text),0)
 NrcCheck(NeonServiceBegin(0.0,0.0,0.0,1.0),0)
 NrcCheck(NeonServiceText(nrcFont,20.0,20.0,?text,1.0,1.0,1.0,1.0),0)
 nrc\column=0
 NrcCheck(NeonServiceFontCaretQuery(48,@nrc),0)
 NrcCheck(nrc\resultX,0)
 position=20.0+MathFFromInt(nrc\resultX)/65536.0
 NrcCheck(NeonServiceBox(position,34.0,2.0,2.0,0.0,1.0,0.0,1.0),0)
 nrc\column=1
 NrcCheck(NeonServiceFontCaretQuery(48,@nrc),0)
 NrcCheck(nrc\resultX,1048576)
 position=20.0+MathFFromInt(nrc\resultX)/65536.0
 NrcCheck(NeonServiceBox(position,34.0,2.0,2.0,0.0,1.0,0.0,1.0),0)
 nrc\column=2
 NrcCheck(NeonServiceFontCaretQuery(48,@nrc),0)
 NrcCheck(nrc\resultX,2097152)
 position=20.0+MathFFromInt(nrc\resultX)/65536.0
 NrcCheck(NeonServiceBox(position,34.0,2.0,2.0,0.0,1.0,0.0,1.0),0)
 nrc\column=3
 NrcCheck(NeonServiceFontCaretQuery(48,@nrc),0)
 NrcCheck(nrc\resultX,3145728)
 position=20.0+MathFFromInt(nrc\resultX)/65536.0
 NrcCheck(NeonServiceBox(position,34.0,2.0,2.0,0.0,1.0,0.0,1.0),0)
 nrc\column=4
 NrcCheck(NeonServiceFontCaretQuery(48,@nrc),0)
 NrcCheck(nrc\resultX,4194304)
 position=20.0+MathFFromInt(nrc\resultX)/65536.0
 NrcCheck(NeonServiceBox(position,34.0,2.0,2.0,0.0,1.0,0.0,1.0),0)
 nrc\column=5
 NrcCheck(NeonServiceFontCaretQuery(48,@nrc),0)
 NrcCheck(nrc\resultX,5242880)
 position=20.0+MathFFromInt(nrc\resultX)/65536.0
 NrcCheck(NeonServiceBox(position,34.0,2.0,2.0,0.0,1.0,0.0,1.0),0)
 nrc\column=6
 NrcCheck(NeonServiceFontCaretQuery(48,@nrc),0)
 NrcCheck(nrc\resultX,6291456)
 position=20.0+MathFFromInt(nrc\resultX)/65536.0
 NrcCheck(NeonServiceBox(position,34.0,2.0,2.0,0.0,1.0,0.0,1.0),0)
 NrcCheck(NeonServiceEnd(),0)
 nrcOld=nrcFont
 NrcCheck(NeonServiceClose(),0)
 NrcCheck(nscDispatch(48,nrcContext,@nrc,80),-21503)
 NrcCheck(NeonServiceOpen(),0)
 nrc\font=nrcOld
 NrcCheck(NeonServiceFontCaretQuery(48,@nrc),-21506)
 NrcCheck(NeonServiceClose(),0)
 ProcedureReturn nrcFailure
EndProcedure
DataSection
text: Data.a 65,86,65,84,65,82,0
hidden: Data.a 65,9,240,159,152,128,66,0
EndDataSection

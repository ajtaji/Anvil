; SPDX-License-Identifier: MIT
; Pure application: all font layout and rendering live in the monitor.
EnableFloatingPoint
XIncludeFile "Anvil/Math/float32.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_font_spacing.pbi"
XIncludeFile "Anvil/Graphics/neon_service_font_controls.pbi"
XIncludeFile "Anvil/Graphics/neon_service_font_caret.pbi"
XIncludeFile "Anvil/Graphics/neon_chrome_edit.pbi"
XIncludeFile "Anvil/Graphics/neon_service_mapping.pbi"
XIncludeFile "Anvil/Graphics/neon_service_chrome_edit.pbi"
Global nrcEdit.NeonChromeEditState,nrcConfig.NeonChromeEditConfig
Global Dim nrcArena.q[64]
Global nrcCount.i,nrcFailure.i,nrcFont.i,nrcOld.i,nrcContext.i,nrcRoleRef.i
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
 NrcCheck(NeonServiceFontSetFixedAdvance(nrcFont,0.0),0)
 NrcCheck(NeonServiceChromeEditInstall(),0)
 nrcConfig\id=123 : nrcConfig\font=nrcFont : nrcConfig\text=?text : nrcConfig\w=300.0 : nrcConfig\h=50.0 : nrcConfig\scale=1.0
 NrcCheck(NeonChromeEditConfigure(@nrcEdit,@nrcArena[0],512,64,@nrcConfig),0)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,0),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),0)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,1),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),555264)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,2),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),1110528)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,3),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),1658112)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,4),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),2133504)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,5),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),2742144)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,6),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),3347712)
 NrcCheck(MathFToInt(NeonServiceTextWidth(nrcFont,?prefix)*65536.0),608640)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,1),0)
 nscNativeMinor=12
 NrcCheck(NeonChromeEditSeal(@nrcEdit),-22105)
 NrcCheck(nrcEdit\ready,0)
 nscNativeMinor=13
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),555264)
 NrcCheck(NeonServiceFontSetFixedAdvance(nrcFont,16.0),0)
 NrcCheck(NeonChromeEditSetText(@nrcEdit,?astral,7),0)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,5),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),2097152)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,3),-22100)
 NrcCheck(NeonChromeEditRendererInstall(@NeonServiceBox,@NeonServiceText,@NeonServiceTextWidth,@NeonServiceLineHeight,@NeonServicePrepare,@NeonServiceScissorSet,@NeonServiceScissorClear),0)
 NrcCheck(nceCaretActive,0)
 NrcCheck(NeonServiceChromeEditInstall(),0)
 NrcCheck(nceCaretActive,1)
 nscNativeMinor=14
 nrcRoleRef=NeonServiceFontRegister(4,0,12)
 NrcCheck(Bool(nrcRoleRef>3),1)
 NrcCheck(NeonServicePrepare(nrcRoleRef,?text),0)
 nrcConfig\font=0 : nrcConfig\text=?text
 NrcCheck(NeonChromeEditConfigure(@nrcEdit,@nrcArena[0],512,64,@nrcConfig),0)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,0),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),0)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,1),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),555264)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,2),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),1110528)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,3),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),1658112)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,4),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),2133504)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,5),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),2742144)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,6),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),3347712)
 NrcCheck(MathFToInt(NeonServiceLineHeight(0)),14)
 nrc\font=0 : nrc\text=?text : nrc\textBytes=7 : nrc\column=3 : nrc\line=0 : nrc\xQ16=1384320
 NrcCheck(NeonServiceFontCaretQuery(48,@nrc),0)
 NrcCheck(nrc\resultX,1658112)
 NrcCheck(NeonServiceFontCaretQuery(49,@nrc),0)
 NrcCheck(nrc\resultColumn,3)
 NrcCheck(NeonServiceFontCaretQuery(50,@nrc),0)
 NrcCheck(nrc\resultX,1658112)
 NrcCheck(NeonServiceFontCaretQuery(51,@nrc),0)
 NrcCheck(nrc\resultColumn,3)
 NrcCheck(NeonServiceBegin(0.0,0.0,0.0,1.0),0)
 NrcCheck(NeonServiceFontCaretQuery(48,@nrc),0)
 NrcCheck(nrc\resultX,1658112)
 NrcCheck(NeonServiceText(0,20.0,20.0,?text,1.0,1.0,1.0,1.0),0)
 NrcCheck(NeonServiceEnd(),0)
 NrcCheck(MathFToInt(NeonServiceLineHeight(0)),14)
 nrcRoleRef=NeonServiceFontRegister(4,1,16)
 NrcCheck(Bool(nrcRoleRef>3),1)
 NrcCheck(NeonServicePrepare(nrcRoleRef,?text),0)
 nrcConfig\font=1 : nrcConfig\text=?text
 NrcCheck(NeonChromeEditConfigure(@nrcEdit,@nrcArena[0],512,64,@nrcConfig),0)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,0),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),0)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,1),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),740352)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,2),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),1480704)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,3),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),2210816)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,4),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),2844672)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,5),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),3656192)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,6),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),4463616)
 NrcCheck(MathFToInt(NeonServiceLineHeight(1)),18)
 nrc\font=1 : nrc\text=?text : nrc\textBytes=7 : nrc\column=3 : nrc\line=0 : nrc\xQ16=1845760
 NrcCheck(NeonServiceFontCaretQuery(48,@nrc),0)
 NrcCheck(nrc\resultX,2210816)
 NrcCheck(NeonServiceFontCaretQuery(49,@nrc),0)
 NrcCheck(nrc\resultColumn,3)
 NrcCheck(NeonServiceFontCaretQuery(50,@nrc),0)
 NrcCheck(nrc\resultX,2210816)
 NrcCheck(NeonServiceFontCaretQuery(51,@nrc),0)
 NrcCheck(nrc\resultColumn,3)
 NrcCheck(NeonServiceBegin(0.0,0.0,0.0,1.0),0)
 NrcCheck(NeonServiceFontCaretQuery(48,@nrc),0)
 NrcCheck(nrc\resultX,2210816)
 NrcCheck(NeonServiceText(1,20.0,20.0,?text,1.0,1.0,1.0,1.0),0)
 NrcCheck(NeonServiceEnd(),0)
 NrcCheck(MathFToInt(NeonServiceLineHeight(1)),18)
 nrcRoleRef=NeonServiceFontRegister(4,2,20)
 NrcCheck(Bool(nrcRoleRef>3),1)
 NrcCheck(NeonServicePrepare(nrcRoleRef,?text),0)
 nrcConfig\font=2 : nrcConfig\text=?text
 NrcCheck(NeonChromeEditConfigure(@nrcEdit,@nrcArena[0],512,64,@nrcConfig),0)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,0),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),0)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,1),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),925440)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,2),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),1850880)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,3),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),2763520)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,4),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),3555840)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,5),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),4570240)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,6),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),5579520)
 NrcCheck(MathFToInt(NeonServiceLineHeight(2)),22)
 nrc\font=2 : nrc\text=?text : nrc\textBytes=7 : nrc\column=3 : nrc\line=0 : nrc\xQ16=2307200
 NrcCheck(NeonServiceFontCaretQuery(48,@nrc),0)
 NrcCheck(nrc\resultX,2763520)
 NrcCheck(NeonServiceFontCaretQuery(49,@nrc),0)
 NrcCheck(nrc\resultColumn,3)
 NrcCheck(NeonServiceFontCaretQuery(50,@nrc),0)
 NrcCheck(nrc\resultX,2763520)
 NrcCheck(NeonServiceFontCaretQuery(51,@nrc),0)
 NrcCheck(nrc\resultColumn,3)
 NrcCheck(NeonServiceBegin(0.0,0.0,0.0,1.0),0)
 NrcCheck(NeonServiceFontCaretQuery(48,@nrc),0)
 NrcCheck(nrc\resultX,2763520)
 NrcCheck(NeonServiceText(2,20.0,20.0,?text,1.0,1.0,1.0,1.0),0)
 NrcCheck(NeonServiceEnd(),0)
 NrcCheck(MathFToInt(NeonServiceLineHeight(2)),22)
 nrcRoleRef=NeonServiceFontRegister(4,3,24)
 NrcCheck(Bool(nrcRoleRef>3),1)
 NrcCheck(NeonServicePrepare(nrcRoleRef,?text),0)
 nrcConfig\font=3 : nrcConfig\text=?text
 NrcCheck(NeonChromeEditConfigure(@nrcEdit,@nrcArena[0],512,64,@nrcConfig),0)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,0),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),0)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,1),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),1110528)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,2),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),2221056)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,3),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),3316224)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,4),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),4267008)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,5),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),5484288)
 NrcCheck(NeonChromeEditCaret(@nrcEdit,6),0)
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
 NrcCheck(MathFToInt(nrcEdit\caretW*65536.0),6695424)
 NrcCheck(MathFToInt(NeonServiceLineHeight(3)),26)
 nrc\font=3 : nrc\text=?text : nrc\textBytes=7 : nrc\column=3 : nrc\line=0 : nrc\xQ16=2768640
 NrcCheck(NeonServiceFontCaretQuery(48,@nrc),0)
 NrcCheck(nrc\resultX,3316224)
 NrcCheck(NeonServiceFontCaretQuery(49,@nrc),0)
 NrcCheck(nrc\resultColumn,3)
 NrcCheck(NeonServiceFontCaretQuery(50,@nrc),0)
 NrcCheck(nrc\resultX,3316224)
 NrcCheck(NeonServiceFontCaretQuery(51,@nrc),0)
 NrcCheck(nrc\resultColumn,3)
 NrcCheck(NeonServiceBegin(0.0,0.0,0.0,1.0),0)
 NrcCheck(NeonServiceFontCaretQuery(48,@nrc),0)
 NrcCheck(nrc\resultX,3316224)
 NrcCheck(NeonServiceText(3,20.0,20.0,?text,1.0,1.0,1.0,1.0),0)
 NrcCheck(NeonServiceEnd(),0)
 NrcCheck(MathFToInt(NeonServiceLineHeight(3)),26)
 nscNativeMinor=13
 NrcCheck(NeonChromeEditSeal(@nrcEdit),-22105)
 NrcCheck(nrcEdit\ready,0)
 nscNativeMinor=14
 NrcCheck(NeonChromeEditSeal(@nrcEdit),0)
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
prefix: Data.a 65,0
astral: Data.a 65,240,159,152,128,66,0
EndDataSection

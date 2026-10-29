; SPDX-License-Identifier: MIT
; Scripted native-event editing on an installed resident curved target.
; The payload owns UI/input state; Anvil owns every GPU object and presentation.
EnableFloatingPoint
XIncludeFile "Anvil/Math/float32.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_mapping.pbi"
XIncludeFile "Anvil/Graphics/neon_service_targets.pbi"
XIncludeFile "Anvil/Graphics/neon_canvas_input.pbi"
XIncludeFile "Anvil/Graphics/neon_service_chrome_edit.pbi"
Global nrrCount.i,nrrFailure.i,nrrSubmits.i
Global nrrInput.NeonCanvasInput,nrrViewport.NeonCanvasViewport,nrrEvent.NativeInputEvent
Global nrrEdit.NeonChromeEditState,nrrConfig.NeonChromeEditConfig,nrrEditInput.NeonChromeEditInput
Global Dim nrrArena.q[256]
Procedure NrrCheck(value.i,expected.i)
 PokeI($E1C00400+nrrCount*16,value) : PokeI($E1C00408+nrrCount*16,expected)
 nrrCount=nrrCount+1
 If value<>expected And nrrFailure=0 : nrrFailure=nrrCount : EndIf
 PokeI($E1C00010,nrrFailure) : PokeI($E1C00018,nrrCount)
EndProcedure
Procedure.i Main(services.i)
 Protected i.i,target.i,text.i
 For i=0 To 16383 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$4E524B31) : PokeI($E1C00008,1)
 NrrCheck(NeonServiceBind(services,#NEON_SERVICE_TARGETS|#NEON_SERVICE_TARGET_RETRO),0)
 If nrrFailure<>0 : ProcedureReturn nrrFailure : EndIf
 NrrCheck(NeonServiceOpen(),0)
 If nrrFailure<>0 : ProcedureReturn nrrFailure : EndIf
 NrrCheck(NeonServiceChromeEditInstall(),0)
 NrrCheck(NeonCanvasFit(@nrrViewport,800,600,NeonServiceWidth(),NeonServiceHeight()),0)
 NrrCheck(NeonCanvasInputConfigureRetro(@nrrInput,@nrrViewport),0)
 target=NeonServiceTargetCreate(800,600,0)
 PokeI($E1C00040,NeonServiceError())
 NrrCheck(Bool(target>0),1)
 If nrrFailure<>0 : Goto NrrDone : EndIf
 nrrConfig\id=77 : nrrConfig\font=0 : nrrConfig\text="AB" : nrrConfig\placeholder="Type here"
 nrrConfig\x=80.0 : nrrConfig\y=220.0 : nrrConfig\w=300.0 : nrrConfig\h=36.0 : nrrConfig\scale=1.0
 NrrCheck(NeonChromeEditConfigure(@nrrEdit,@nrrArena[0],2048,64,@nrrConfig),0)
 For i=0 To 4
  nrrEvent\kind=5 : nrrEvent\source=4 : nrrEvent\code=0 : nrrEvent\modifiers=0
  nrrEvent\x=320 : nrrEvent\y=317 : nrrEvent\buttons=0 : nrrEvent\value=0
  nrrEvent\ticks=i+1 : nrrEvent\generation=1 : nrrEvent\reserved=0
  If i=0 : nrrEvent\buttons=1 : EndIf
  If i=1 : nrrEvent\value=2 : EndIf
  If i>=2
   nrrEvent\source=1 : nrrEvent\x=-1 : nrrEvent\y=-1
   If i=2 : nrrEvent\kind=1 : nrrEvent\code=90 : EndIf
   If i=3 : nrrEvent\kind=2 : nrrEvent\code=1 : EndIf
   If i=4 : nrrEvent\kind=2 : nrrEvent\code=9 : EndIf
  EndIf
  NrrCheck(NeonCanvasInputFeed(@nrrInput,@nrrEvent),0)
  nrrEditInput\x=nrrInput\pointer\x : nrrEditInput\y=nrrInput\pointer\y
  nrrEditInput\down=nrrInput\pointer\down : nrrEditInput\key=nrrInput\input\key
  nrrEditInput\scalar=nrrInput\input\scalar : nrrEditInput\ctrl=nrrInput\input\ctrl
  nrrEditInput\dt=0.016
  NrrCheck(NeonChromeEditInput(@nrrEdit,@nrrEditInput),0)
  nrrSubmits=nrrSubmits+nrrEdit\submitted
  NrrCheck(NeonServiceTargetBind(target),0)
  NrrCheck(NeonChromeEditSeal(@nrrEdit),0)
  NrrCheck(NeonServiceBegin(0.5019608,0.5019608,0.5019608,1.0),0)
  NrrCheck(NeonChromeEditDraw(@nrrEdit),0)
  NrrCheck(NeonServiceBox(400.0,220.0,80.0,36.0,0.1254902,0.6274510,0.9411765,1.0),0)
  NrrCheck(NeonServiceEnd(),0)
  NrrCheck(NeonServiceTargetUnbind(target),0)
  NrrCheck(NeonServiceTargetRetroPrepare(target),0)
  NrrCheck(NeonServiceBegin(0.0,0.0,0.0,1.0),0)
  NrrCheck(NeonServiceTargetDrawRetro(target,0.0),0)
  NrrCheck(NeonServiceEnd(),0)
  text=NeonChromeEditText(@nrrEdit)
  PokeI($E1C00100+i*48,nrrEdit\length) : PokeI($E1C00108+i*48,nrrEdit\caret)
  PokeI($E1C00110+i*48,NeonChromeEditFocused(@nrrEdit)) : PokeI($E1C00118+i*48,nrrSubmits)
  PokeI($E1C00120+i*48,PeekA(text+2)) : PokeI($E1C00128+i*48,nrrEdit\submitted)
  If nrrFailure<>0 : Goto NrrDone : EndIf
 Next
 NrrCheck(nrrEdit\length,3) : NrrCheck(nrrEdit\caret,3)
 NrrCheck(PeekA(text),65) : NrrCheck(PeekA(text+1),66) : NrrCheck(PeekA(text+2),90) : NrrCheck(PeekA(text+3),0)
 NrrCheck(nrrSubmits,1) : NrrCheck(NeonChromeEditFocused(@nrrEdit),0)
 NrrDone:
 If nrrFailure<>0 : NeonServiceClose() : EndIf
 ProcedureReturn nrrFailure
EndProcedure

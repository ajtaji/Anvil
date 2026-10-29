; SPDX-License-Identifier: MIT
; Portable resident input protocol. No hardware, focus policy or queue storage.
XIncludeFile "Anvil/Hal/input_codes.pbi"
#NUI_SERVICE_SLOT=39
#NUI_SERVICE_ABI_MINOR=9
#NUI_MAGIC=$4E495331
#NUI_MAJOR=1
#NUI_MINOR=0
#NUI_KEYBOARD=1
#NUI_MOUSE=2
#NUI_TOUCH=4
#NUI_POINTER=5
#NUI_WHEEL=6
#NUI_PHYSICAL_KEY=7
#NUI_SOURCE_MOUSE=4
#NUI_SOURCE_TOUCH=5
#NUI_HOVER=4
#NUI_QUERY=0
#NUI_OPEN=1
#NUI_POLL=2
#NUI_FLUSH=3
#NUI_CLOSE=4
#NUI_ERR_ARGS=-22400
#NUI_ERR_STATE=-22401
#NUI_ERR_BUSY=-22402
#NUI_ERR_ABI=-22403
#NUI_ERR_PROVIDER=-22404
#NUI_ERR_FULL=-22405
#NUI_ERR_UNBOUND=-22406
#NUI_ERR_CAPABILITY=-22407
Structure NativeInputApi Align #PB_Structure_AlignC
  magic.l : major.l : minor.l : bytes.l
  flags.i : dispatch.i
EndStructure
Structure NativeInputOpenRequest Align #PB_Structure_AlignC
  required.i : capabilities.i : width.i : height.i : generation.i
EndStructure
; Kind1..4 reuse the normalized typed-event vocabulary. Pointer code is a
; stable contact id (mouse0, touch ids shifted by1). Pointer value is DOWN0,
; MOVE1, UP2, CANCEL3 or mouse-only HOVER4. Buttons are an absolute mask.
; Physical-key code is the HID keyboard usage (1..255), value DOWN1/UP0.
; Text and named navigation events remain separate for editors. Modifier-only
; edges may use usages224..231. Wheel value is signed steps.
; Coordinates are logical screen pixels, already
; rotated by the display owner; clients map to their canvas once.
Structure NativeInputEvent Align #PB_Structure_AlignC
  kind.l : source.l : code.l : modifiers.l
  x.l : y.l : buttons.l : value.l
  ticks.q
  generation.l : reserved.l
EndStructure
Procedure.i NativeInputEventValid(event.i)
  Protected *e.NativeInputEvent
  If event<=0 Or (event & 7)<>0 Or event+SizeOf(NativeInputEvent)<=event : ProcedureReturn 0 : EndIf
  *e=event
  If *e\reserved<>0 Or *e\generation<1 Or *e\ticks<0 Or *e\modifiers<0 Or *e\modifiers>15 : ProcedureReturn 0 : EndIf
  If *e\kind>=#AIE_TEXT And *e\kind<=#AIE_CANCEL
    If *e\source<1 Or *e\source>#AIS_MAX Or *e\x<>-1 Or *e\y<>-1 Or *e\buttons<>0 Or *e\value<>0 : ProcedureReturn 0 : EndIf
    If *e\kind=#AIE_TEXT : ProcedureReturn Bool(*e\code>=32 And *e\code<=126) : EndIf
    If *e\kind=#AIE_CANCEL : ProcedureReturn Bool(*e\code>=0 And *e\code<=#AIC_MAX) : EndIf
    ProcedureReturn Bool(*e\code>=1 And *e\code<=#AIK_MAX)
  EndIf
  If *e\kind=#NUI_PHYSICAL_KEY
    ProcedureReturn Bool(*e\source=#AIS_PHYSICAL And *e\code>=1 And *e\code<=255 And *e\x=-1 And *e\y=-1 And *e\buttons=0 And (*e\value=0 Or *e\value=1))
  EndIf
  If *e\source<>#NUI_SOURCE_MOUSE And *e\source<>#NUI_SOURCE_TOUCH : ProcedureReturn 0 : EndIf
  If *e\buttons<0 Or *e\buttons>7 : ProcedureReturn 0 : EndIf
  If *e\kind=#NUI_POINTER And *e\value=3
    If *e\source=#NUI_SOURCE_MOUSE And *e\code<>-1 And *e\code<>0 : ProcedureReturn 0 : EndIf
    If *e\source=#NUI_SOURCE_TOUCH And *e\code=0 : ProcedureReturn 0 : EndIf
    ProcedureReturn Bool(*e\code>=-1 And *e\code<=65535 And *e\x=-1 And *e\y=-1 And *e\buttons=0)
  EndIf
  If *e\x<0 Or *e\y<0 Or *e\x>1000000 Or *e\y>1000000 : ProcedureReturn 0 : EndIf
  If *e\kind=#NUI_WHEEL
    ProcedureReturn Bool(*e\source=#NUI_SOURCE_MOUSE And *e\code=0 And *e\value>=-32768 And *e\value<=32767)
  EndIf
  If *e\kind<>#NUI_POINTER Or *e\code<0 Or *e\code>65535 Or *e\value<0 Or *e\value>4 : ProcedureReturn 0 : EndIf
  If *e\source=#NUI_SOURCE_MOUSE And *e\code<>0 : ProcedureReturn 0 : EndIf
  If *e\source=#NUI_SOURCE_TOUCH And (*e\code=0 Or *e\value=#NUI_HOVER Or *e\buttons>1) : ProcedureReturn 0 : EndIf
  If *e\value=0 Or *e\value=1 : ProcedureReturn Bool(*e\buttons<>0) : EndIf
  ProcedureReturn Bool(*e\buttons=0)
EndProcedure

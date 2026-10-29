; SPDX-License-Identifier: MIT
; Pure resident-input to Neon UI translation. No device or service ownership.
XIncludeFile "Anvil/Hal/input_service_api.pbi"
XIncludeFile "Anvil/Graphics/neon_pointer.pbi"
XIncludeFile "Anvil/Graphics/neon_chrome_edit.pbi"
Structure NeonNativeInputState Align #PB_Structure_AlignC
  generation.i : key.i : scalar.i : ctrl.i : wheel.i
EndStructure
Procedure.i NeonNativeEditKey(key.i)
  Select key
    Case #AIK_ENTER : ProcedureReturn #NCE_RETURN
    Case #AIK_BACKSPACE : ProcedureReturn #NCE_BACK
    Case #AIK_DELETE : ProcedureReturn #NCE_DELETE
    Case #AIK_LEFT : ProcedureReturn #NCE_LEFT
    Case #AIK_RIGHT : ProcedureReturn #NCE_RIGHT
    Case #AIK_HOME : ProcedureReturn #NCE_HOME
    Case #AIK_END : ProcedureReturn #NCE_END
    Case #AIK_ESC : ProcedureReturn #NCE_ESCAPE
  EndSelect
  ProcedureReturn 0
EndProcedure
Procedure.i NeonNativeInputIdle(*p.NeonPointerState,*s.NeonNativeInputState)
  If nptValid(*p)=0 : ProcedureReturn #NPT_ERR_STATE : EndIf
  If *s<=0 Or (*s & 7)<>0 Or *s+SizeOf(NeonNativeInputState)<=*s : ProcedureReturn #NPT_ERR_ARGS : EndIf
  *s\key=0 : *s\scalar=0 : *s\ctrl=0 : *s\wheel=0
  ProcedureReturn NeonPointerIdle(*p)
EndProcedure
Procedure.i NeonNativeInputFeed(*p.NeonPointerState,*s.NeonNativeInputState,*e.NativeInputEvent)
  Protected event.AnvilTouchEvent,x.f,y.f,contact.i,leftDown.i
  If nptValid(*p)=0 : ProcedureReturn #NPT_ERR_STATE : EndIf
  If *s<=0 Or (*s & 7)<>0 Or *s+SizeOf(NeonNativeInputState)<=*s : ProcedureReturn #NPT_ERR_ARGS : EndIf
  If NativeInputEventValid(*e)=0 : ProcedureReturn #NPT_ERR_ARGS : EndIf
  If *s<*p+SizeOf(NeonPointerState) And *s+SizeOf(NeonNativeInputState)>*p : ProcedureReturn #NPT_ERR_ARGS : EndIf
  If *e<*p+SizeOf(NeonPointerState) And *e+SizeOf(NativeInputEvent)>*p : ProcedureReturn #NPT_ERR_ARGS : EndIf
  If *e<*s+SizeOf(NeonNativeInputState) And *e+SizeOf(NativeInputEvent)>*s : ProcedureReturn #NPT_ERR_ARGS : EndIf
  If *s\generation<>0 And *e\generation<>*s\generation
    If *e\kind<>#AIE_CANCEL Or *e\generation<*s\generation : ProcedureReturn #NPT_ERR_STATE : EndIf
  EndIf
  ; Refused input leaves transient output untouched.
  If *e\kind=#NUI_POINTER Or *e\kind=#NUI_WHEEL
    If *e\value<>3 Or *e\kind=#NUI_WHEEL
      If *e\x>=*p\sourceW Or *e\y>=*p\sourceH : ProcedureReturn #NPT_ERR_ARGS : EndIf
    EndIf
  EndIf
  NeonNativeInputIdle(*p,*s)
  *s\generation=*e\generation : *s\ctrl=Bool(*e\modifiers & #AIM_CTRL)
  If *e\kind=#NUI_POINTER Or *e\kind=#NUI_WHEEL
    If (*e\kind=#NUI_WHEEL Or *e\value<>3) And *e\ticks<*p\lastTicks : ProcedureReturn 0 : EndIf
  EndIf
  Select *e\kind
    Case #AIE_CANCEL
      ProcedureReturn NeonPointerCancel(*p)
    Case #AIE_TEXT
      *s\scalar=*e\code
    Case #AIE_KEY_DOWN
      *s\key=NeonNativeEditKey(*e\code)
    Case #NUI_PHYSICAL_KEY
      If *e\value=1 And *s\ctrl<>0
        ; The typed channel excludes shortcuts, so each command arrives once.
        Select *e\code
          Case 4 : *s\key=#NCE_A
          Case 6 : *s\key=#NCE_C
          Case 27 : *s\key=#NCE_X
          Case 25 : *s\key=#NCE_V
        EndSelect
      EndIf
    Case #NUI_WHEEL
      If *p\down=0 Or *p\contact=0
        *p\x=MathFFromInt(*e\x)*(MathFFromInt(*p\canvasW)/MathFFromInt(*p\sourceW))
        *p\y=MathFFromInt(*e\y)*(MathFFromInt(*p\canvasH)/MathFFromInt(*p\sourceH))
        *p\changed=1 : *s\wheel=*e\value
        *p\lastTicks=*e\ticks
      EndIf
    Case #NUI_POINTER
      If *e\value=3
        If *e\code=-1 Or *e\code=*p\contact : ProcedureReturn NeonPointerCancel(*p) : EndIf
        ProcedureReturn 0
      EndIf
      contact=*e\code
      event\x=*e\x : event\y=*e\y : event\id=contact : event\ticks=*e\ticks
      event\state=*e\value : event\pressure=0 : event\reserved=0
      If *e\source=#NUI_SOURCE_MOUSE
        If *p\down<>0 And *p\contact<>0 : ProcedureReturn 0 : EndIf
        leftDown=Bool(*e\buttons & 1)
        If leftDown<>0
          event\state=#HW_TOUCH_MOVE
          If *p\down=0 : event\state=#HW_TOUCH_DOWN : EndIf
        ElseIf *p\down<>0
          event\state=#HW_TOUCH_UP
        Else
          If *e\ticks<*p\lastTicks : ProcedureReturn 0 : EndIf
          *p\x=MathFFromInt(*e\x)*(MathFFromInt(*p\canvasW)/MathFFromInt(*p\sourceW))
          *p\y=MathFFromInt(*e\y)*(MathFFromInt(*p\canvasH)/MathFFromInt(*p\sourceH))
          *p\lastTicks=*e\ticks : *p\changed=1 : ProcedureReturn 0
        EndIf
      EndIf
      ProcedureReturn NeonPointerFeed(*p,@event)
  EndSelect
  ProcedureReturn 0
EndProcedure

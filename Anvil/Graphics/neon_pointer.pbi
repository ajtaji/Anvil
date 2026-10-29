; SPDX-License-Identifier: MIT
; Pure single-contact pointer tracking and logical-screen to canvas mapping.
XIncludeFile "Anvil/Math/float32.pbi"
XIncludeFile "Anvil/Hal/touch_event.pbi"
#NPT_MAGIC=$4E505431
#NPT_ERR_ARGS=-22300
#NPT_ERR_STATE=-22301
#NPT_ERR_BUSY=-22302
#NPT_ERR_ABI=-22303
#NPT_ERR_PROVIDER=-22304
Structure NeonPointerState Align #PB_Structure_AlignC
  magic.i : sourceW.i : sourceH.i : canvasW.i : canvasH.i : contact.i
  down.i : pressed.i : released.i : cancelled.i : changed.i : lastTicks.q
  x.f : y.f
EndStructure
Procedure.i nptValid(*s.NeonPointerState)
  If *s=0 Or (*s & 7)<>0 : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool(*s\magic=#NPT_MAGIC)
EndProcedure
Procedure.i NeonPointerConfigure(*s.NeonPointerState,sourceW.i,sourceH.i,canvasW.i,canvasH.i)
  Protected i.i
  If *s=0 Or (*s & 7)<>0 Or sourceW<1 Or sourceW>8192 Or sourceH<1 Or sourceH>8192 Or canvasW<1 Or canvasW>8192 Or canvasH<1 Or canvasH>8192 : ProcedureReturn #NPT_ERR_ARGS : EndIf
  If *s\magic<>0 And *s\magic<>#NPT_MAGIC : ProcedureReturn #NPT_ERR_STATE : EndIf
  If *s\magic=#NPT_MAGIC And *s\down<>0 : ProcedureReturn #NPT_ERR_BUSY : EndIf
  For i=0 To SizeOf(NeonPointerState)-8 Step 8 : PokeI(*s+i,0) : Next
  *s\magic=#NPT_MAGIC : *s\sourceW=sourceW : *s\sourceH=sourceH : *s\canvasW=canvasW : *s\canvasH=canvasH
  *s\contact=-1 : *s\x=-1.0 : *s\y=-1.0 : ProcedureReturn 0
EndProcedure
Procedure.i NeonPointerIdle(*s.NeonPointerState)
  If nptValid(*s)=0 : ProcedureReturn #NPT_ERR_STATE : EndIf
  *s\pressed=0 : *s\released=0 : *s\cancelled=0 : *s\changed=0 : ProcedureReturn 0
EndProcedure
Procedure.i NeonPointerCancel(*s.NeonPointerState)
  If nptValid(*s)=0 : ProcedureReturn #NPT_ERR_STATE : EndIf
  NeonPointerIdle(*s)
  *s\contact=-1 : *s\down=0 : *s\cancelled=1 : *s\changed=1 : *s\x=-1.0 : *s\y=-1.0 : ProcedureReturn 0
EndProcedure
Procedure.i NeonPointerFeed(*s.NeonPointerState,*event.AnvilTouchEvent)
  Protected x.f,y.f
  If nptValid(*s)=0 : ProcedureReturn #NPT_ERR_STATE : EndIf
  If *event=0 Or (*event & 7)<>0 : ProcedureReturn #NPT_ERR_ARGS : EndIf
  If *event<*s+SizeOf(NeonPointerState) And *event+SizeOf(AnvilTouchEvent)>*s : ProcedureReturn #NPT_ERR_ARGS : EndIf
  If *event\state<0 Or *event\state>3 Or *event\reserved<>0 Or *event\pressure < -1 Or *event\pressure>255 Or *event\ticks<0 : ProcedureReturn #NPT_ERR_ARGS : EndIf
  If *event\state=#HW_TOUCH_CANCEL
    NeonPointerIdle(*s)
    If *event\id=-1 : ProcedureReturn NeonPointerCancel(*s) : EndIf
    If *event\id=*s\contact And *s\down<>0 And *event\ticks>=*s\lastTicks : ProcedureReturn NeonPointerCancel(*s) : EndIf
    ProcedureReturn 0
  EndIf
  If *event\id<0 Or *event\x<0 Or *event\y<0 Or *event\x>1000000 Or *event\y>1000000 : ProcedureReturn #NPT_ERR_ARGS : EndIf
  x=MathFFromInt(*event\x)*(MathFFromInt(*s\canvasW)/MathFFromInt(*s\sourceW))
  y=MathFFromInt(*event\y)*(MathFFromInt(*s\canvasH)/MathFFromInt(*s\sourceH))
  If (MathBitsOf(x) & $7FFFFFFF)>$49742400 Or (MathBitsOf(y) & $7FFFFFFF)>$49742400 : ProcedureReturn #NPT_ERR_ARGS : EndIf
  NeonPointerIdle(*s)
  If *event\state=#HW_TOUCH_DOWN
    If *s\down<>0 : ProcedureReturn 0 : EndIf
    *s\contact=*event\id : *s\down=1 : *s\pressed=1
  Else
    If *s\down=0 Or *event\id<>*s\contact Or *event\ticks<*s\lastTicks : ProcedureReturn 0 : EndIf
    If *event\state=#HW_TOUCH_UP : *s\down=0 : *s\released=1 : *s\contact=-1 : EndIf
  EndIf
  *s\lastTicks=*event\ticks : *s\x=x : *s\y=y : *s\changed=1 : ProcedureReturn 0
EndProcedure

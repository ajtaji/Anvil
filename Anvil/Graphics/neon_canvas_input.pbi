; SPDX-License-Identifier: MIT
; Logical-screen events for an aspect-fit canvas. No device or focus owner.
XIncludeFile "Anvil/Graphics/neon_canvas_retro.pbi"
XIncludeFile "Anvil/Graphics/neon_native_input.pbi"
#NEON_CANVAS_INPUT_MAGIC=$4E434931
Structure NeonCanvasInput Align #PB_Structure_AlignC
  magic.i
  viewport.NeonCanvasViewport
  pointer.NeonPointerState
  input.NeonNativeInputState
  blockedMouse.i : retro.i
EndStructure
Procedure.i nciValid(*s.NeonCanvasInput)
  Protected v.NeonCanvasViewport
  If (*s & 7)<>0 Or NeonByteSpan(*s,SizeOf(NeonCanvasInput))=0 : ProcedureReturn 0 : EndIf
  If *s\magic<>#NEON_CANVAS_INPUT_MAGIC : ProcedureReturn 0 : EndIf
  If NeonCanvasFit(@v,*s\viewport\canvasW,*s\viewport\canvasH,*s\viewport\targetW,*s\viewport\targetH)<>0 : ProcedureReturn 0 : EndIf
  If v\x<>*s\viewport\x Or v\y<>*s\viewport\y Or v\width<>*s\viewport\width Or v\height<>*s\viewport\height : ProcedureReturn 0 : EndIf
  If *s\pointer\magic<>#NPT_MAGIC Or *s\pointer\sourceW<>v\targetW Or *s\pointer\sourceH<>v\targetH Or *s\pointer\canvasW<>v\targetW Or *s\pointer\canvasH<>v\targetH : ProcedureReturn 0 : EndIf
  If *s\retro<>0 And *s\retro<>1 : ProcedureReturn 0 : EndIf
  If *s\blockedMouse<>0 And *s\blockedMouse<>1 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure
Procedure.i nciConfigure(*s.NeonCanvasInput,*v.NeonCanvasViewport,retro.i)
  Protected candidate.NeonCanvasInput,i.i,rc.i
  If retro<0 Or retro>1 : ProcedureReturn #NPT_ERR_ARGS : EndIf
  If (*s & 7)<>0 Or (*v & 7)<>0 Or NeonByteSpan(*s,SizeOf(NeonCanvasInput))=0 Or NeonByteSpan(*v,SizeOf(NeonCanvasViewport))=0 : ProcedureReturn #NPT_ERR_ARGS : EndIf
  If NeonByteOverlap(*s,SizeOf(NeonCanvasInput),*v,SizeOf(NeonCanvasViewport))<>0 : ProcedureReturn #NPT_ERR_ARGS : EndIf
  If *s\magic<>0
    If nciValid(*s)=0 : ProcedureReturn #NPT_ERR_STATE : EndIf
    If *s\pointer\down<>0 Or *s\blockedMouse<>0 : ProcedureReturn #NPT_ERR_BUSY : EndIf
  EndIf
  rc=NeonCanvasFit(@candidate\viewport,*v\canvasW,*v\canvasH,*v\targetW,*v\targetH)
  If rc<>0 : ProcedureReturn rc : EndIf
  If candidate\viewport\x<>*v\x Or candidate\viewport\y<>*v\y Or candidate\viewport\width<>*v\width Or candidate\viewport\height<>*v\height : ProcedureReturn #NPT_ERR_ARGS : EndIf
  rc=NeonPointerConfigure(@candidate\pointer,*v\targetW,*v\targetH,*v\targetW,*v\targetH)
  If rc<>0 : ProcedureReturn rc : EndIf
  If *s\magic<>0
    candidate\input\generation=*s\input\generation : candidate\pointer\lastTicks=*s\pointer\lastTicks
  EndIf
  candidate\magic=#NEON_CANVAS_INPUT_MAGIC : candidate\retro=retro
  For i=0 To SizeOf(NeonCanvasInput)-8 Step 8 : PokeI(*s+i,PeekI(@candidate+i)) : Next
  ProcedureReturn 0
EndProcedure
; Existing callers retain linear mapping. Reconfiguration is refused during capture.
Procedure.i NeonCanvasInputConfigure(*s.NeonCanvasInput,*v.NeonCanvasViewport)
  ProcedureReturn nciConfigure(*s,*v,0)
EndProcedure
Procedure.i NeonCanvasInputConfigureRetro(*s.NeonCanvasInput,*v.NeonCanvasViewport)
  ProcedureReturn nciConfigure(*s,*v,1)
EndProcedure
Procedure.i NeonCanvasInputIdle(*s.NeonCanvasInput)
  If nciValid(*s)=0 : ProcedureReturn #NPT_ERR_STATE : EndIf
  ProcedureReturn NeonNativeInputIdle(@*s\pointer,@*s\input)
EndProcedure
Procedure.i NeonCanvasInputFeed(*s.NeonCanvasInput,*e.NativeInputEvent)
  Protected candidate.NeonCanvasInput,point.NeonCanvasPoint,i.i,inside.i,rc.i,current.i
  Protected nx.f,ny.f,radius.f
  If nciValid(*s)=0 : ProcedureReturn #NPT_ERR_STATE : EndIf
  If NativeInputEventValid(*e)=0 : ProcedureReturn #NPT_ERR_ARGS : EndIf
  If NeonByteOverlap(*s,SizeOf(NeonCanvasInput),*e,SizeOf(NativeInputEvent))<>0 : ProcedureReturn #NPT_ERR_ARGS : EndIf
  For i=0 To SizeOf(NeonCanvasInput)-8 Step 8 : PokeI(@candidate+i,PeekI(*s+i)) : Next
  rc=NeonNativeInputFeed(@candidate\pointer,@candidate\input,*e)
  If rc<>0 : ProcedureReturn rc : EndIf
  If *e\kind=#AIE_CANCEL
    candidate\blockedMouse=0
  ElseIf *e\kind=#NUI_POINTER And *e\value=#HW_TOUCH_CANCEL
    If *e\source=#NUI_SOURCE_MOUSE Or *e\code=-1 : candidate\blockedMouse=0 : EndIf
  ElseIf *e\kind=#NUI_POINTER Or *e\kind=#NUI_WHEEL
    current=Bool(*e\ticks>=*s\pointer\lastTicks)
    If candidate\retro<>0
      inside=NeonCanvasMapRetroPoint(@candidate\viewport,*e\x,*e\y,@point)
    Else
      inside=NeonCanvasMapPoint(@candidate\viewport,*e\x,*e\y,@point)
    EndIf
    If inside<0 : ProcedureReturn inside : EndIf
    If current<>0
      If *e\kind=#NUI_POINTER
        ; A press in a bar never captures. A mouse held across the edge
        ; must be released before it may start a new canvas press.
        If *s\pointer\down=0 And candidate\pointer\pressed<>0 And inside=0
          If *e\source=#NUI_SOURCE_MOUSE : candidate\blockedMouse=1 : EndIf
          candidate\pointer\down=0 : candidate\pointer\contact=-1
          candidate\pointer\pressed=0 : candidate\pointer\released=0
        EndIf
        If *e\source=#NUI_SOURCE_MOUSE And *s\blockedMouse<>0
          If *s\pointer\down=0
            candidate\pointer\down=0 : candidate\pointer\contact=-1
            candidate\pointer\pressed=0 : candidate\pointer\released=0
          EndIf
          If (*e\buttons & 1)=0 : candidate\blockedMouse=0 : EndIf
        EndIf
      ElseIf inside=0
        candidate\input\wheel=0
      EndIf
      If candidate\pointer\changed<>0 And candidate\pointer\cancelled=0
        ; Captured motion/release keeps signed out-of-canvas coordinates.
        ; Clamping to an edge could turn an outside release into a click.
        candidate\pointer\x=MathFFromInt((*e\x-candidate\viewport\x)*candidate\viewport\canvasW*65536/candidate\viewport\width)/65536.0
        candidate\pointer\y=MathFFromInt((*e\y-candidate\viewport\y)*candidate\viewport\canvasH*65536/candidate\viewport\height)/65536.0
        If candidate\retro<>0
          If inside<>0
            candidate\pointer\x=MathFFromInt(point\xQ16)/65536.0
            candidate\pointer\y=MathFFromInt(point\yQ16)/65536.0
          Else
            ; NativeInputFeed bounds coordinates to the logical target. Float
            ; intermediates retain signed captured motion outside the curved
            ; canvas, including narrow aspect fits, without integer overflow.
            nx=candidate\pointer\x*2.0/MathFFromInt(candidate\viewport\canvasW)-1.0
            ny=candidate\pointer\y*2.0/MathFFromInt(candidate\viewport\canvasH)-1.0
            radius=nx*nx+ny*ny
            nx=nx+nx*radius*0.015 : ny=ny+ny*radius*0.015
            candidate\pointer\x=(nx*0.5+0.5)*MathFFromInt(candidate\viewport\canvasW)
            candidate\pointer\y=(ny*0.5+0.5)*MathFFromInt(candidate\viewport\canvasH)
          EndIf
        EndIf
      EndIf
    EndIf
  EndIf
  For i=0 To SizeOf(NeonCanvasInput)-8 Step 8 : PokeI(*s+i,PeekI(@candidate+i)) : Next
  ProcedureReturn 0
EndProcedure

; SPDX-License-Identifier: MIT
; Aspect-preserving top-left viewport and inverse logical input mapping.
XIncludeFile "Anvil/Graphics/neon_byte_ranges.pbi"
#NEON_CANVAS_ERR_ARGS = -21341
#NEON_CANVAS_ERR_STATE = -21342
#NEON_CANVAS_ERR_STALE = -21343
#NEON_CANVAS_ERR_VIEWPORT = -21344
Structure NeonCanvasViewport Align #PB_Structure_AlignC
  x.i : y.i : width.i : height.i
  canvasW.i : canvasH.i : targetW.i : targetH.i
EndStructure
Structure NeonCanvasPoint Align #PB_Structure_AlignC
  xQ16.i : yQ16.i
EndStructure
Procedure.i NeonCanvasFit(*out.NeonCanvasViewport,canvasW.i,canvasH.i,targetW.i,targetH.i)
  Protected v.NeonCanvasViewport,i.i
  If (*out & 7)<>0 Or NeonByteSpan(*out,SizeOf(NeonCanvasViewport))=0 : ProcedureReturn #NEON_CANVAS_ERR_ARGS : EndIf
  If canvasW<1 Or canvasH<1 Or targetW<1 Or targetH<1 Or canvasW>8192 Or canvasH>8192 Or targetW>8192 Or targetH>8192 : ProcedureReturn #NEON_CANVAS_ERR_ARGS : EndIf
  If targetW*canvasH<=targetH*canvasW
    v\width=targetW : v\height=targetW*canvasH/canvasW
  Else
    v\height=targetH : v\width=targetH*canvasW/canvasH
  EndIf
  If v\width<1 Or v\height<1 : ProcedureReturn #NEON_CANVAS_ERR_VIEWPORT : EndIf
  v\x=(targetW-v\width)/2 : v\y=(targetH-v\height)/2
  v\canvasW=canvasW : v\canvasH=canvasH : v\targetW=targetW : v\targetH=targetH
  For i=0 To SizeOf(NeonCanvasViewport)-8 Step 8 : PokeI(*out+i,PeekI(@v+i)) : Next
  ProcedureReturn 0
EndProcedure
; Returns1 inside,0 in the bars/outside. Refusals/outside preserve output.
; Coordinates are logical target pixels, after the display's rotation mapping.
Procedure.i NeonCanvasMapPoint(*v.NeonCanvasViewport,x.i,y.i,*out.NeonCanvasPoint)
  Protected q.NeonCanvasViewport
  If (*v & 7)<>0 Or (*out & 7)<>0 Or NeonByteSpan(*v,SizeOf(NeonCanvasViewport))=0 Or NeonByteSpan(*out,SizeOf(NeonCanvasPoint))=0 : ProcedureReturn #NEON_CANVAS_ERR_ARGS : EndIf
  If NeonByteOverlap(*v,SizeOf(NeonCanvasViewport),*out,SizeOf(NeonCanvasPoint))<>0 : ProcedureReturn #NEON_CANVAS_ERR_ARGS : EndIf
  If NeonCanvasFit(@q,*v\canvasW,*v\canvasH,*v\targetW,*v\targetH)<>0 : ProcedureReturn #NEON_CANVAS_ERR_ARGS : EndIf
  If q\x<>*v\x Or q\y<>*v\y Or q\width<>*v\width Or q\height<>*v\height : ProcedureReturn #NEON_CANVAS_ERR_ARGS : EndIf
  If x<q\x Or y<q\y Or x>=q\x+q\width Or y>=q\y+q\height : ProcedureReturn 0 : EndIf
  *out\xQ16=(x-q\x)*q\canvasW*65536/q\width
  *out\yQ16=(y-q\y)*q\canvasH*65536/q\height
  ProcedureReturn 1
EndProcedure

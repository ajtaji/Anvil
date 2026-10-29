; SPDX-License-Identifier: MIT
; Continuous pointer mapping for the same .015 radial warp as the CRT shader.
XIncludeFile "Anvil/Graphics/neon_canvas_viewport.pbi"
; Return1 inside sampled canvas,0 in letterbox/opaque border. Preserve output
; on outside/refusal. Q24 intermediates keep the full 8192-pixel range bounded.
Procedure.i NeonCanvasMapRetroPoint(*v.NeonCanvasViewport,x.i,y.i,*out.NeonCanvasPoint)
  Protected q.NeonCanvasPoint,rc.i,nx.i,ny.i,radius.i,wx.i,wy.i
  If (*out & 7)<>0 Or NeonByteSpan(*out,SizeOf(NeonCanvasPoint))=0 : ProcedureReturn #NEON_CANVAS_ERR_ARGS : EndIf
  If NeonByteOverlap(*v,SizeOf(NeonCanvasViewport),*out,SizeOf(NeonCanvasPoint))<>0 : ProcedureReturn #NEON_CANVAS_ERR_ARGS : EndIf
  rc=NeonCanvasMapPoint(*v,x,y,@q)
  If rc<>1 : ProcedureReturn rc : EndIf
  nx=(x-*v\x)*33554432/*v\width-16777216
  ny=(y-*v\y)*33554432/*v\height-16777216
  radius=(nx*nx+ny*ny)/16777216
  wx=nx+(nx*radius*3)/3355443200
  wy=ny+(ny*radius*3)/3355443200
  If wx< -16777216 Or wy< -16777216 Or wx>16777216 Or wy>16777216 : ProcedureReturn 0 : EndIf
  *out\xQ16=(wx+16777216)* *v\canvasW/512
  *out\yQ16=(wy+16777216)* *v\canvasH/512
  ProcedureReturn 1
EndProcedure

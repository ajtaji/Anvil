; SPDX-License-Identifier: MIT
; Optional pure virtual-canvas, camera-aware drawing and clipping client.
; Surface Width/Height continue to report the physical logical target extent.
; Canvas changes are idle-only and reset the camera, matching the native port.
Procedure.i nsmRequest(op.i,request.i,bytes.i,phase.i)
  ProcedureReturn NeonServiceExtensionStatus(NeonServiceRequestExtension(op,request,bytes,phase,#NEON_SERVICE_MAPPING,#NEON_SERVICE_MAPPING_MINOR,0))
EndProcedure
Procedure.i NeonServiceCanvas(width.i,height.i)
  Protected request.NeonServiceCanvasRequest
  If width<1 Or height<1 Or width>8192 Or height>8192 : ProcedureReturn NeonServiceExtensionStatus(#NEON_SERVICE_ERR_ARGS) : EndIf
  request\width=width : request\height=height
  ProcedureReturn nsmRequest(#NEON_SERVICE_CANVAS,@request,SizeOf(NeonServiceCanvasRequest),0)
EndProcedure
Procedure.i NeonServiceScissorSet(x.f,y.f,w.f,h.f)
  Protected request.NeonServiceScissorRequest
  request\x=x : request\y=y : request\w=w : request\h=h
  ProcedureReturn nsmRequest(#NEON_SERVICE_SCISSOR_SET,@request,SizeOf(NeonServiceScissorRequest),1)
EndProcedure
Procedure.i NeonServiceScissorClear()
  ProcedureReturn nsmRequest(#NEON_SERVICE_SCISSOR_CLEAR,0,0,1)
EndProcedure
Procedure.i NeonServiceBoxMapped(x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f,scaled.i,ignoreCamera.i)
  Protected request.NeonServiceMappedBoxRequest
  request\x=x : request\y=y : request\w=w : request\h=h
  request\r=r : request\g=g : request\b=b : request\a=a
  request\scaled=scaled : request\ignoreCamera=ignoreCamera
  ProcedureReturn nsmRequest(#NEON_SERVICE_BOX_MAPPED,@request,SizeOf(NeonServiceMappedBoxRequest),1)
EndProcedure
Procedure.i NeonServicePolygonMapped(x.f,y.f,rx.f,ry.f,sides.i,r.f,g.f,b.f,a.f,solid.i,scaled.i,ignoreCamera.i)
  Protected request.NeonServiceMappedPolygonRequest
  request\x=x : request\y=y : request\rx=rx : request\ry=ry : request\sides=sides
  request\r=r : request\g=g : request\b=b : request\a=a : request\solid=solid
  request\scaled=scaled : request\ignoreCamera=ignoreCamera
  ProcedureReturn nsmRequest(#NEON_SERVICE_POLYGON_MAPPED,@request,SizeOf(NeonServiceMappedPolygonRequest),1)
EndProcedure
Procedure.i NeonServiceTextMapped(font.i,x.f,y.f,text.i,r.f,g.f,b.f,a.f,scaled.i,ignoreCamera.i)
  Protected request.NeonServiceMappedTextRequest
  request\font=font : request\x=x : request\y=y : request\text=text
  request\r=r : request\g=g : request\b=b : request\a=a
  request\scaled=scaled : request\ignoreCamera=ignoreCamera
  ProcedureReturn nsmRequest(#NEON_SERVICE_TEXT_MAPPED,@request,SizeOf(NeonServiceMappedTextRequest),1)
EndProcedure
Procedure.i NeonServiceStaticLines(data.i,sourceBytes.i,vertexCount.i,r.f,g.f,b.f,a.f,limitVertices.i)
  Protected request.NeonServiceStaticLinesRequest
  If vertexCount<0 Or vertexCount>#NEON_SERVICE_MAX_STATIC_LINE_VERTICES Or sourceBytes<vertexCount*8 Or limitVertices<0 : ProcedureReturn NeonServiceExtensionStatus(#NEON_SERVICE_ERR_ARGS) : EndIf
  If vertexCount>0 And (data<1 Or (data & 3)<>0) : ProcedureReturn NeonServiceExtensionStatus(#NEON_SERVICE_ERR_ARGS) : EndIf
  request\data=data : request\sourceBytes=sourceBytes : request\vertexCount=vertexCount
  request\r=r : request\g=g : request\b=b : request\a=a : request\limitVertices=limitVertices
  ProcedureReturn nsmRequest(#NEON_SERVICE_STATIC_LINES,@request,SizeOf(NeonServiceStaticLinesRequest),1)
EndProcedure

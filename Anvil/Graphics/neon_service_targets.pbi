; SPDX-License-Identifier: MIT
; Pure target client; the provider retains all renderer resources.
Procedure.i nstRequest(op.i,request.i,bytes.i,phase.i)
  ProcedureReturn NeonServiceRequestExtension(op,request,bytes,phase,#NEON_SERVICE_TARGETS,#NEON_SERVICE_TARGET_MINOR,0)
EndProcedure
Procedure.i NeonServiceTargetLimitsGet(*limits.NeonServiceTargetLimits)
  Protected rc.i
  If *limits=0 Or (*limits & 7)<>0 : ProcedureReturn NeonServiceExtensionStatus(#NEON_SERVICE_ERR_ARGS) : EndIf
  *limits\slots=0 : *limits\maxDimension=0
  rc=nstRequest(#NEON_SERVICE_TARGET_LIMITS,*limits,SizeOf(NeonServiceTargetLimits),-1)
  If rc<>0 : ProcedureReturn NeonServiceExtensionStatus(rc) : EndIf
  If *limits\slots<1 Or *limits\slots>#NEON_SERVICE_MAX_TARGETS Or *limits\maxDimension<1 Or *limits\maxDimension>#NEON_SERVICE_TARGET_DIMENSION : ProcedureReturn NeonServiceExtensionStatus(#NEON_SERVICE_ERR_PROVIDER) : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i NeonServiceTargetCreate(width.i,height.i,linear.i)
  Protected request.NeonServiceTargetCreateRequest,handle.i
  If width<1 Or height<1 Or width>#NEON_SERVICE_TARGET_DIMENSION Or height>#NEON_SERVICE_TARGET_DIMENSION Or (linear<>0 And linear<>1)
    NeonServiceExtensionStatus(#NEON_SERVICE_ERR_ARGS) : ProcedureReturn 0
  EndIf
  request\width=width : request\height=height : request\linear=linear
  handle=nstRequest(#NEON_SERVICE_TARGET_CREATE,@request,SizeOf(NeonServiceTargetCreateRequest),0)
  If handle<0 : ProcedureReturn 0 : EndIf
  If handle=0 : NeonServiceExtensionStatus(#NEON_SERVICE_ERR_PROVIDER) : ProcedureReturn 0 : EndIf
  ProcedureReturn handle
EndProcedure
Procedure.i NeonServiceTargetResize(handle.i,width.i,height.i)
  Protected request.NeonServiceTargetResizeRequest
  If handle<1 Or width<1 Or height<1 Or width>#NEON_SERVICE_TARGET_DIMENSION Or height>#NEON_SERVICE_TARGET_DIMENSION : ProcedureReturn NeonServiceExtensionStatus(#NEON_SERVICE_ERR_ARGS) : EndIf
  request\handle=handle : request\width=width : request\height=height
  ProcedureReturn NeonServiceExtensionStatus(nstRequest(#NEON_SERVICE_TARGET_RESIZE,@request,SizeOf(NeonServiceTargetResizeRequest),0))
EndProcedure
Procedure.i NeonServiceTargetFree(handle.i)
  Protected request.NeonServiceSpriteHandleRequest
  If handle<1 : ProcedureReturn NeonServiceExtensionStatus(#NEON_SERVICE_ERR_ARGS) : EndIf
  request\handle=handle
  ProcedureReturn NeonServiceExtensionStatus(nstRequest(#NEON_SERVICE_TARGET_FREE,@request,SizeOf(NeonServiceSpriteHandleRequest),0))
EndProcedure
Procedure.i NeonServiceTargetDraw(handle.i,x.f,y.f,angle.f,scale.f,r.f,g.f,b.f,a.f,scaled.i,srcX.f,srcY.f,srcW.f,srcH.f,ignoreCamera.i)
  Protected request.NeonServiceSpriteDrawRequest
  If handle<1 : ProcedureReturn NeonServiceExtensionStatus(#NEON_SERVICE_ERR_ARGS) : EndIf
  request\handle=handle : request\x=x : request\y=y : request\angle=angle : request\scale=scale
  request\r=r : request\g=g : request\b=b : request\a=a : request\scaled=scaled
  request\srcX=srcX : request\srcY=srcY : request\srcW=srcW : request\srcH=srcH : request\ignoreCamera=ignoreCamera
  ProcedureReturn NeonServiceExtensionStatus(nstRequest(#NEON_SERVICE_TARGET_DRAW,@request,SizeOf(NeonServiceSpriteDrawRequest),1))
EndProcedure

Procedure.i NeonServiceTargetRetroPrepare(handle.i)
  Protected request.NeonServiceSpriteHandleRequest
  If handle<1 : ProcedureReturn NeonServiceExtensionStatus(#NEON_SERVICE_ERR_ARGS) : EndIf
  request\handle=handle
  ProcedureReturn NeonServiceExtensionStatus(NeonServiceRequestExtension(#NEON_SERVICE_TARGET_RETRO_PREPARE,@request,SizeOf(NeonServiceSpriteHandleRequest),0,#NEON_SERVICE_TARGETS | #NEON_SERVICE_TARGET_RETRO,#NEON_SERVICE_TARGET_RETRO_MINOR,0))
EndProcedure
Procedure.i NeonServiceTargetDrawRetro(handle.i,time.f)
  Protected request.NeonServiceTargetRetroRequest
  If handle<1 Or (MathBitsOf(time) & $7F800000)=$7F800000 : ProcedureReturn NeonServiceExtensionStatus(#NEON_SERVICE_ERR_ARGS) : EndIf
  request\handle=handle : request\time=time : request\reserved=0
  ProcedureReturn NeonServiceExtensionStatus(NeonServiceRequestExtension(#NEON_SERVICE_TARGET_RETRO_DRAW,@request,SizeOf(NeonServiceTargetRetroRequest),1,#NEON_SERVICE_TARGETS | #NEON_SERVICE_TARGET_RETRO,#NEON_SERVICE_TARGET_RETRO_MINOR,0))
EndProcedure

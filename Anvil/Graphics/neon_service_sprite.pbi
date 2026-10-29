; SPDX-License-Identifier: MIT
; Pure sprite client. Include the HAL contract, float32 and base service client.
; The resident provider owns textures. Source pixel bytes are borrowed only
; for Upload; failed replacement leaves the prior opaque handle unchanged.
Procedure.i nssRequest(op.i,request.i,bytes.i,phase.i,retain.i)
  ProcedureReturn NeonServiceRequestExtension(op,request,bytes,phase,#NEON_SERVICE_SPRITES,#NEON_SERVICE_SPRITE_MINOR,retain)
EndProcedure
Procedure.i NeonServiceSpriteLimitsGet(*limits.NeonServiceSpriteLimits)
  Protected rc.i
  If *limits=0 Or (*limits & 7)<>0 : ProcedureReturn NeonServiceExtensionStatus(#NEON_SERVICE_ERR_ARGS) : EndIf
  *limits\slots=0 : *limits\maxDimension=0 : *limits\maxUploadBytes=0 : *limits\maxBatch=0
  rc=nssRequest(#NEON_SERVICE_SPRITE_LIMITS,*limits,SizeOf(NeonServiceSpriteLimits),-1,0)
  If rc<>0 : ProcedureReturn NeonServiceExtensionStatus(rc) : EndIf
  If *limits\slots<1 Or *limits\slots>#NEON_SERVICE_MAX_SPRITES Or *limits\maxDimension<1 Or *limits\maxDimension>#NEON_SERVICE_MAX_SPRITE_DIM Or *limits\maxUploadBytes<4 Or *limits\maxUploadBytes>#NEON_SERVICE_MAX_SPRITE_BYTES Or *limits\maxBatch<1 Or *limits\maxBatch>#NEON_SERVICE_MAX_SPRITE_BATCH
    ProcedureReturn NeonServiceExtensionStatus(#NEON_SERVICE_ERR_PROVIDER)
  EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i NeonServiceSpriteUpload(slot.i,pixels.i,sourceBytes.i,width.i,height.i,bgra.i)
  Protected request.NeonServiceSpriteUploadRequest,handle.i
  If slot<1 Or slot>#NEON_SERVICE_MAX_SPRITES Or pixels<1 Or width<1 Or height<1 Or width>#NEON_SERVICE_MAX_SPRITE_DIM Or height>#NEON_SERVICE_MAX_SPRITE_DIM Or (bgra<>0 And bgra<>1)
    NeonServiceExtensionStatus(#NEON_SERVICE_ERR_ARGS) : ProcedureReturn 0
  EndIf
  If sourceBytes<width*height*4
    NeonServiceExtensionStatus(#NEON_SERVICE_ERR_ARGS) : ProcedureReturn 0
  EndIf
  request\slot=slot : request\pixels=pixels : request\sourceBytes=sourceBytes
  request\width=width : request\height=height : request\bgra=bgra
  handle=nssRequest(#NEON_SERVICE_SPRITE_UPLOAD,@request,SizeOf(NeonServiceSpriteUploadRequest),0,0)
  If handle<0 : ProcedureReturn 0 : EndIf
  If handle=0 : NeonServiceExtensionStatus(#NEON_SERVICE_ERR_PROVIDER) : ProcedureReturn 0 : EndIf
  ProcedureReturn handle
EndProcedure
Procedure.i NeonServiceSpriteClear(handle.i)
  Protected request.NeonServiceSpriteHandleRequest
  If handle<1 : ProcedureReturn NeonServiceExtensionStatus(#NEON_SERVICE_ERR_ARGS) : EndIf
  request\handle=handle
  ProcedureReturn NeonServiceExtensionStatus(nssRequest(#NEON_SERVICE_SPRITE_CLEAR,@request,SizeOf(NeonServiceSpriteHandleRequest),0,0))
EndProcedure
Procedure.i NeonServiceSprite(handle.i,x.f,y.f,angle.f,scale.f,r.f,g.f,b.f,a.f,scaled.i,srcX.f,srcY.f,srcW.f,srcH.f,ignoreCamera.i)
  Protected request.NeonServiceSpriteDrawRequest
  If handle<1 : ProcedureReturn NeonServiceExtensionStatus(#NEON_SERVICE_ERR_ARGS) : EndIf
  request\handle=handle : request\x=x : request\y=y : request\angle=angle : request\scale=scale
  request\r=r : request\g=g : request\b=b : request\a=a : request\scaled=scaled
  request\srcX=srcX : request\srcY=srcY : request\srcW=srcW : request\srcH=srcH : request\ignoreCamera=ignoreCamera
  ProcedureReturn NeonServiceExtensionStatus(nssRequest(#NEON_SERVICE_SPRITE_DRAW,@request,SizeOf(NeonServiceSpriteDrawRequest),1,0))
EndProcedure
Procedure.i NeonServiceCamera(x.f,y.f,zoom.f)
  Protected request.NeonServiceCameraRequest
  request\x=x : request\y=y : request\zoom=zoom : request\reserved=0
  ProcedureReturn NeonServiceExtensionStatus(nssRequest(#NEON_SERVICE_CAMERA,@request,SizeOf(NeonServiceCameraRequest),-1,0))
EndProcedure
Procedure.i NeonServiceSpriteBatchBegin(handle.i)
  Protected request.NeonServiceSpriteHandleRequest
  If handle<1 : ProcedureReturn NeonServiceExtensionStatus(#NEON_SERVICE_ERR_ARGS) : EndIf
  request\handle=handle
  ProcedureReturn NeonServiceExtensionStatus(nssRequest(#NEON_SERVICE_SPRITE_BATCH_BEGIN,@request,SizeOf(NeonServiceSpriteHandleRequest),1,0))
EndProcedure
Procedure.i NeonServiceSpriteBatchAdd(x.f,y.f,w.f,h.f,angle.f,r.f,g.f,b.f,a.f,ignoreCamera.i)
  Protected request.NeonServiceSpriteBatchRequest
  request\x=x : request\y=y : request\w=w : request\h=h : request\angle=angle
  request\r=r : request\g=g : request\b=b : request\a=a : request\reserved=0 : request\ignoreCamera=ignoreCamera
  ProcedureReturn NeonServiceExtensionStatus(nssRequest(#NEON_SERVICE_SPRITE_BATCH_ADD,@request,SizeOf(NeonServiceSpriteBatchRequest),1,0))
EndProcedure
Procedure.i NeonServiceSpriteBatchEnd()
  ProcedureReturn NeonServiceExtensionStatus(nssRequest(#NEON_SERVICE_SPRITE_BATCH_END,0,0,1,1))
EndProcedure

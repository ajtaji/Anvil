; SPDX-License-Identifier: MIT
; Controlled packet/ownership proof. No GPU implementation is linked.
EnableFloatingPoint
XIncludeFile "Anvil/Math/float32.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_sprite.pbi"
Global nspChecks.i,nspFailure.i,nspCalls.i,nspResult.i,nspBadLimits.i,nspMinor.i=1
Global nspApi.NeonServiceApi
Global Dim nspPixels.l[4]
Procedure NspCheck(actual.i,expected.i)
  nspChecks=nspChecks+1
  If actual<>expected And nspFailure=0 : nspFailure=nspChecks : EndIf
EndProcedure
Procedure.i NspDispatch(op.i,context.i,request.i,bytes.i)
  Protected *surface.NeonServiceSurface=request,*limits.NeonServiceSpriteLimits=request
  Protected i.i,offset.i
  nspCalls=nspCalls+1
  If op=#NEON_SERVICE_OPEN
    If context<>0 Or bytes<>40 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    *surface\bytes=40 : *surface\logicalW=1280 : *surface\logicalH=800
    *surface\flags=7 : *surface\maxFonts=8 : ProcedureReturn 91
  EndIf
  If context<>91 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
  If op>=#NEON_SERVICE_SPRITE_LIMITS
    offset=256+(op-#NEON_SERVICE_SPRITE_LIMITS)*128
    PokeI(#NSP_REPORT+offset,bytes)
    For i=0 To bytes-1 : PokeA(#NSP_REPORT+offset+8+i,PeekA(request+i)) : Next
  EndIf
  If op=#NEON_SERVICE_SPRITE_LIMITS
    *limits\slots=16 : *limits\maxDimension=2048 : *limits\maxUploadBytes=16777216 : *limits\maxBatch=128
    If nspBadLimits<>0 : *limits\maxBatch=129 : EndIf
  EndIf
  If op=#NEON_SERVICE_SPRITE_UPLOAD And nspResult=0 : ProcedureReturn 701 : EndIf
  ProcedureReturn nspResult
EndProcedure
Procedure.i Main(services.i)
  Protected i.i,before.i,limits.NeonServiceSpriteLimits
  For i=0 To 4095 : PokeA(#NSP_REPORT+i,0) : Next
  NspCheck(SizeOf(NeonServiceSpriteLimits),32)
  NspCheck(SizeOf(NeonServiceSpriteUploadRequest),48)
  NspCheck(SizeOf(NeonServiceSpriteHandleRequest),8)
  NspCheck(SizeOf(NeonServiceSpriteDrawRequest),72)
  NspCheck(SizeOf(NeonServiceCameraRequest),16)
  NspCheck(SizeOf(NeonServiceSpriteBatchRequest),48)
  nspApi\magic=#NEON_SERVICE_MAGIC : nspApi\major=1 : nspApi\minor=0
  nspApi\bytes=48 : nspApi\flags=7 : nspApi\maxFonts=8 : nspApi\dispatch=@NspDispatch
  NspCheck(NeonServiceBindApi(@nspApi,48,4),#NEON_SERVICE_ERR_ABI)
  NspCheck(NeonServiceBindApi(@nspApi,48,1),0)
  NspCheck(NeonServiceOpen(),0)
  before=nspCalls
  NspCheck(NeonServiceSpriteLimitsGet(@limits),#NEON_SERVICE_ERR_ABI)
  NspCheck(nspCalls,before)
  NspCheck(NeonServiceClose(),0)
  NspCheck(NeonServiceUnbind(),0)
  nspApi\minor=1
  NspCheck(NeonServiceBindApi(@nspApi,48,4),0)
  NspCheck(NeonServiceOpen(),0)
  NspCheck(NeonServiceSpriteLimitsGet(@limits),0)
  NspCheck(limits\maxBatch,128)
  nspBadLimits=1
  NspCheck(NeonServiceSpriteLimitsGet(@limits),#NEON_SERVICE_ERR_PROVIDER)
  nspBadLimits=0
  NspCheck(NeonServiceSpriteLimitsGet(@limits),0)
  before=nspCalls
  NspCheck(NeonServiceSpriteUpload(0,@nspPixels[0],16,2,2,0),0)
  NspCheck(NeonServiceError(),#NEON_SERVICE_ERR_ARGS)
  NspCheck(NeonServiceSpriteUpload(1,@nspPixels[0],15,2,2,0),0)
  NspCheck(NeonServiceSpriteUpload(1,@nspPixels[0],16,2,2,2),0)
  NspCheck(nspCalls,before)
  NspCheck(NeonServiceSpriteUpload(3,@nspPixels[0],16,2,2,1),701)
  NspCheck(NeonServiceCamera(12.5,-3.25,2.0),0)
  NspCheck(NeonServiceBegin(0.0,0.0,0.0,1.0),0)
  before=nspCalls
  NspCheck(NeonServiceSpriteUpload(1,@nspPixels[0],16,2,2,0),0)
  NspCheck(NeonServiceError(),#NEON_SERVICE_ERR_STATE)
  NspCheck(NeonServiceSpriteClear(701),#NEON_SERVICE_ERR_STATE)
  NspCheck(NeonServiceSpriteBatchBegin(0),#NEON_SERVICE_ERR_ARGS)
  NspCheck(nspCalls,before)
  NspCheck(NeonServiceSprite(701,1.25,2.5,90.0,2.0,0.25,0.5,0.75,1.0,1,3.0,4.0,5.0,6.0,1),0)
  NspCheck(NeonServiceSpriteBatchBegin(701),0)
  NspCheck(NeonServiceSpriteBatchAdd(7.0,8.0,9.0,10.0,180.0,0.1,0.2,0.3,0.4,1),0)
  nspResult=-777
  NspCheck(NeonServiceSpriteBatchEnd(),-777)
  NspCheck(NeonServiceFrameOpen(),1)
  before=nspCalls
  NspCheck(NeonServiceCamera(0.0,0.0,1.0),#NEON_SERVICE_ERR_STATE)
  NspCheck(NeonServiceSpriteBatchBegin(701),#NEON_SERVICE_ERR_STATE)
  NspCheck(NeonServiceEnd(),#NEON_SERVICE_ERR_STATE)
  NspCheck(nspCalls,before)
  NspCheck(NeonServiceAbort(),-777)
  nspResult=0
  NspCheck(NeonServiceAbort(),0)
  NspCheck(NeonServiceFrameOpen(),0)
  nspResult=3
  NspCheck(NeonServiceSpriteClear(701),#NEON_SERVICE_ERR_PROVIDER)
  nspResult=-21506
  NspCheck(NeonServiceSpriteClear(701),#NEON_SERVICE_ERR_STALE)
  nspResult=0
  NspCheck(NeonServiceSpriteClear(701),0)
  NspCheck(NeonServiceClose(),0)
  NspCheck(NeonServiceUnbind(),0)
  NspCheck(NeonServiceContext(),0)
  PokeI(#NSP_REPORT,$4E535031) : PokeI(#NSP_REPORT+8,1)
  PokeI(#NSP_REPORT+16,nspFailure) : PokeI(#NSP_REPORT+24,nspChecks)
  PokeI(#NSP_REPORT+32,nspCalls) : PokeI(#NSP_REPORT+40,@nspPixels[0])
  ProcedureReturn nspFailure
EndProcedure

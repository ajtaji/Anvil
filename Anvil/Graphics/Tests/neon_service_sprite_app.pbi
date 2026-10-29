; SPDX-License-Identifier: MIT
; Pure application exercising resident-owned textures and display submission.
EnableFloatingPoint
XIncludeFile "Anvil/Math/float32.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_sprite.pbi"
Global Dim nsvPixels.l[16]
; Full declared backing for a legal-size upload that exceeds the device heap.
Global Dim nsvCapacity.q[2097152]
Global Dim nsvHandles.i[16]
Global nsvChecks.i,nsvFailure.i
Procedure NsvCheck(actual.i,expected.i)
  nsvChecks=nsvChecks+1
  PokeI(#NSV_REPORT+128+nsvChecks*16,actual)
  PokeI(#NSV_REPORT+136+nsvChecks*16,expected)
  If actual<>expected And nsvFailure=0 : nsvFailure=nsvChecks : EndIf
  PokeI(#NSV_REPORT+16,nsvFailure) : PokeI(#NSV_REPORT+24,nsvChecks)
EndProcedure
Procedure NsvFillPixels(bgra.i)
  Protected x.i,y.i,c.i
  For y=0 To 3
    For x=0 To 3
      c=$FFFFFFFF
      If y<2
        If x<2 : c=$FF0000FF : Else : c=$FF00FF00 : EndIf
      Else
        If x<2 : c=$FFFF0000 : EndIf
      EndIf
      If bgra<>0 : c=(c & $FF00FF00) | ((c & $FF)<<16) | ((c>>16)&$FF) : EndIf
      nsvPixels[y*4+x]=c
    Next
  Next
EndProcedure
Procedure.i Main(services.i)
  Protected i.i,old.i,limits.NeonServiceSpriteLimits,upload.NeonServiceSpriteUploadRequest
  For i=0 To 4095 Step 8 : PokeI(#NSV_REPORT+i,0) : Next
  PokeI(#NSV_REPORT,$4E535631) : PokeI(#NSV_REPORT+8,1)
  NsvCheck(NeonServiceBind(services,#NEON_SERVICE_VULKAN | #NEON_SERVICE_SPRITES),0)
  If nsvFailure<>0 : ProcedureReturn nsvFailure : EndIf
  NsvCheck(NeonServiceOpen(),0)
  If nsvFailure<>0 : ProcedureReturn nsvFailure : EndIf
  NsvCheck(NeonServiceSpriteLimitsGet(@limits),0)
  NsvCheck(limits\slots,16) : NsvCheck(limits\maxBatch,128)
  For i=1 To 16
    NsvFillPixels(i & 1)
    nsvHandles[i-1]=NeonServiceSpriteUpload(i,@nsvPixels[0],64,4,4,i & 1)
    NsvCheck(Bool(nsvHandles[i-1]>0),1)
  Next
  old=nsvHandles[0] : NsvFillPixels(0)
  nsvHandles[0]=NeonServiceSpriteUpload(1,@nsvPixels[0],64,4,4,0)
  NsvCheck(Bool(nsvHandles[0]>old),1)
  NsvCheck(NeonServiceSpriteClear(old),#NEON_SERVICE_ERR_STALE)
  upload\slot=1 : upload\pixels=$FE000000 : upload\sourceBytes=64
  upload\width=4 : upload\height=4 : upload\bgra=0
  NsvCheck(NeonServiceRequestExtension(#NEON_SERVICE_SPRITE_UPLOAD,@upload,48,0,4,1,0),#NEON_SERVICE_ERR_ARGS)
  upload\pixels=@nsvPixels[0] : upload\sourceBytes=63
  NsvCheck(NeonServiceRequestExtension(#NEON_SERVICE_SPRITE_UPLOAD,@upload,48,0,4,1,0),#NEON_SERVICE_ERR_ARGS)
  NsvCheck(NeonServiceSpriteClear(nsvHandles[15]),0)
  NsvCheck(NeonServiceSpriteClear(nsvHandles[15]),#NEON_SERVICE_ERR_STALE)
  ; The upload owns a copy: destroy all borrowed source bytes now.
  For i=0 To 15 : nsvPixels[i]=0 : Next
  NsvCheck(NeonServiceBegin(0.0,0.0,0.0,1.0),0)
  NsvCheck(NeonServiceSpriteBatchBegin(nsvHandles[0]),0)
  NsvCheck(NeonServiceSpriteBatchBegin(nsvHandles[0]),#NEON_SERVICE_ERR_STATE)
  NsvCheck(NeonServiceSpriteBatchEnd(),0)
  NsvCheck(NeonServiceSpriteBatchBegin(nsvHandles[0]),0)
  NsvCheck(NeonServiceEnd(),#NEON_SERVICE_ERR_STATE)
  NsvCheck(NeonServiceAbort(),0)
  NsvCheck(NeonServiceClose(),0)
  NsvCheck(NeonServiceOpen(),0)
  NsvCheck(NeonServiceSpriteClear(nsvHandles[0]),#NEON_SERVICE_ERR_STALE)
  NsvFillPixels(0) : old=nsvHandles[0]
  nsvHandles[0]=NeonServiceSpriteUpload(1,@nsvPixels[0],64,4,4,0)
  NsvCheck(Bool(nsvHandles[0]>old),1)
  NsvFillPixels(1)
  nsvHandles[1]=NeonServiceSpriteUpload(2,@nsvPixels[0],64,4,4,1)
  NsvCheck(Bool(nsvHandles[1]>nsvHandles[0]),1)
  ; Final screenshot checks the OLD pixels after a capacity refusal.
  NsvCheck(NeonServiceSpriteUpload(1,@nsvCapacity[0],16777216,2048,2048,0),0)
  NsvCheck(NeonServiceError(),-21203)
  For i=0 To 15 : nsvPixels[i]=0 : Next
  NsvCheck(NeonServiceCamera(100.0,50.0,2.0),0)
  NsvCheck(NeonServiceBegin(0.0,0.0,0.0,1.0),0)
  NsvCheck(NeonServiceSprite(nsvHandles[0],100.0,100.0,0.0,16.0,1.0,1.0,1.0,1.0,1,0.0,0.0,4.0,4.0,1),0)
  NsvCheck(NeonServiceSprite(nsvHandles[1],300.0,100.0,0.0,16.0,1.0,1.0,1.0,1.0,1,0.0,0.0,4.0,4.0,1),0)
  NsvCheck(NeonServiceSprite(nsvHandles[0],500.0,300.0,0.0,16.0,1.0,1.0,1.0,1.0,1,0.0,0.0,4.0,4.0,0),0)
  NsvCheck(NeonServiceSprite(nsvHandles[0],450.0,100.0,1.57079632679,16.0,1.0,1.0,1.0,1.0,1,0.0,0.0,4.0,4.0,1),0)
  NsvCheck(NeonServiceSprite(nsvHandles[0],600.0,100.0,0.0,32.0,0.5,0.25,1.0,1.0,1,2.0,2.0,2.0,2.0,1),0)
  NsvCheck(NeonServiceSprite(nsvHandles[0],800.0,100.0,0.0,32.0,1.0,1.0,1.0,0.5,1,2.0,2.0,2.0,2.0,1),0)
  NsvCheck(NeonServiceSpriteBatchBegin(nsvHandles[0]),0)
  For i=0 To 127
    NsvCheck(NeonServiceSpriteBatchAdd(MathFFromInt(80+(i % 16)*40),MathFFromInt(340+(i/16)*40),32.0,32.0,0.0,1.0,1.0,1.0,1.0,1),0)
  Next
  ; An immediate box must precede the deferred batch flush.
  NsvCheck(NeonServiceBox(80.0,340.0,32.0,32.0,1.0,0.0,1.0,1.0),0)
  NsvCheck(NeonServiceSpriteBatchEnd(),0)
  NsvCheck(NeonServiceEnd(),0)
  NsvCheck(NeonServiceProviderError(),0)
  PokeI(#NSV_REPORT+32,NeonServiceContext())
  ; Leave context open for capture-before-retirement by the monitor.
  ProcedureReturn nsvFailure
EndProcedure

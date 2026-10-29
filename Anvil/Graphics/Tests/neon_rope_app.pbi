; SPDX-License-Identifier: MIT
; Generated rope bytes, transactional argument refusals, resident GPU copies.
EnableFloatingPoint
XIncludeFile "Anvil/Math/float32.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_sprite.pbi"
XIncludeFile "Anvil/Graphics/neon_service_mapping.pbi"
XIncludeFile "Anvil/Graphics/neon_service_rope.pbi"
Global Dim nrtPixels.q[1027]
Global Dim nrtMask.q[259]
Global nrtChecks.i,nrtFailure.i
Procedure NrtCheck(actual.i,expected.i)
  PokeI(#NRT_REPORT+256+nrtChecks*16,actual) : PokeI(#NRT_REPORT+264+nrtChecks*16,expected)
  nrtChecks=nrtChecks+1
  If actual<>expected And nrtFailure=0 : nrtFailure=nrtChecks : EndIf
EndProcedure
Procedure NrtFill()
  Protected i.i
  For i=0 To 8215 : PokeA(@nrtPixels[0]+i,165) : Next
  For i=0 To 2071 : PokeA(@nrtMask[0]+i,90) : Next
EndProcedure
Procedure NrtUnchanged(*info.NeonSpriteAssetInfo)
  Protected i.i,bad.i
  NrtCheck(*info\width,991) : NrtCheck(*info\height,992)
  For i=0 To 8215 : If (PeekA(@nrtPixels[0]+i) & 255)<>165 : bad=bad+1 : EndIf : Next
  For i=0 To 2071 : If (PeekA(@nrtMask[0]+i) & 255)<>90 : bad=bad+1 : EndIf : Next
  NrtCheck(bad,0)
EndProcedure
Procedure NrtRecord(slot.i,*info.NeonSpriteAssetInfo)
  Protected p.i=#NRT_REPORT+8192+slot*12288,i.i
  PokeI(p,*info\width) : PokeI(p+8,*info\height)
  For i=0 To 8215 : PokeA(p+32+i,PeekA(@nrtPixels[0]+i)) : Next
  For i=0 To 2071 : PokeA(p+8248+i,PeekA(@nrtMask[0]+i)) : Next
EndProcedure
Procedure.i Main(services.i)
  Protected out.NeonSpriteAssetInfo,i.i,rc.i,h1.i,h2.i,badInfo.i,p.i,m.i
  For i=0 To #NRT_REPORT_BYTES-1 : PokeA(#NRT_REPORT+i,0) : Next
  PokeI(#NRT_REPORT,$4E525431) : PokeI(#NRT_REPORT+8,1)
  NrtFill() : out\width=991 : out\height=992
  p=@nrtPixels[1] : m=@nrtMask[1]
  For i=0 To 12
    If i=0 : rc=NeonSpriteCreateRope(0,p,8192,m,2048) : EndIf
    If i=1 : rc=NeonSpriteCreateRope(@out+1,p,8192,m,2048) : EndIf
    If i=2 : rc=NeonSpriteCreateRope(@out,0,8192,m,2048) : EndIf
    If i=3 : rc=NeonSpriteCreateRope(@out,p,8191,m,2048) : EndIf
    If i=4 : rc=NeonSpriteCreateRope(@out,p,8192,m,2047) : EndIf
    If i=5 : rc=NeonSpriteCreateRope(@out,-1,8192,m,2048) : EndIf
    If i=6 : rc=NeonSpriteCreateRope(@out,$7FFFFFFFFFFFFFFF,8192,m,2048) : EndIf
    If i=7 : rc=NeonSpriteCreateRope(@out,p,8192,p,2048) : EndIf
    If i=8 : rc=NeonSpriteCreateRope(p,p,8192,m,2048) : EndIf
    If i=9 : rc=NeonSpriteCreateRope(m,p,8192,m,2048) : EndIf
    If i=10 : rc=NeonSpriteCreateRope(@out,p,8192,-1,2048) : EndIf
    If i=11 : rc=NeonSpriteCreateRope(@out,p,8192,$7FFFFFFFFFFFFFFF,2048) : EndIf
    If i=12 : rc=NeonSpriteCreateRope($7FFFFFFFFFFFFFF8,p,8192,m,2048) : EndIf
    If i=3 Or i=4 : NrtCheck(rc,#NEON_ASSET_ERR_CAPACITY)
    Else : NrtCheck(rc,#NEON_ASSET_ERR_ARGUMENT) : EndIf
    NrtUnchanged(@out)
  Next
  NrtRecord(2,@out)
  NrtCheck(NeonServiceBind(services,5),0) : NrtCheck(NeonServiceOpen(),0)
  NrtCheck(NeonServiceCanvas(640,400),0)
  NrtCheck(NeonServiceSpriteCreateRope(0,p,8192,m,2048),0)
  NrtCheck(NeonServiceError(),#NEON_ASSET_ERR_ARGUMENT) : NrtUnchanged(@out)
  NrtCheck(NeonServiceSpriteCreateRope(1,p,8191,m,2048),0)
  NrtCheck(NeonServiceError(),#NEON_ASSET_ERR_CAPACITY) : NrtUnchanged(@out)
  NrtCheck(NeonSpriteCreateRope(@out,p,8192,m,2048),0)
  NrtRecord(0,@out)
  h1=NeonServiceSpriteCreateRope(1,p,8192,m,2048) : NrtCheck(Bool(h1>0),1)
  NrtFill()
  ; Byte-addressed outputs need no alignment. A missing optional mask is ignored.
  NrtCheck(NeonSpriteCreateRope(@out,p+1,8192,0,-1),0)
  h2=NeonServiceSpriteCreateRope(2,p+1,8192,0,-1) : NrtCheck(Bool(h2>0),1)
  NrtRecord(1,@out)
  ; Failed replacement must preserve the previously uploaded opaque handle.
  NrtCheck(NeonServiceSpriteCreateRope(1,p,0,m,2048),0)
  NrtCheck(NeonServiceError(),#NEON_ASSET_ERR_CAPACITY)
  For i=0 To 8215 : PokeA(@nrtPixels[0]+i,0) : Next
  For i=0 To 2071 : PokeA(@nrtMask[0]+i,0) : Next
  NrtCheck(NeonServiceBegin(0.04,0.05,0.07,1.0),0)
  NrtCheck(NeonServiceSprite(h1,40.0,40.0,0.0,1.0,1.0,1.0,1.0,1.0,1,-1.0,-1.0,-1.0,-1.0,1),0)
  NrtCheck(NeonServiceSprite(h2,120.0,40.0,0.0,3.0,1.0,1.0,1.0,1.0,1,-1.0,-1.0,-1.0,-1.0,1),0)
  NrtCheck(NeonServiceSprite(h1,280.0,40.0,0.0,4.0,1.0,1.0,1.0,1.0,1,8.0,8.0,16.0,16.0,1),0)
  NrtCheck(NeonServiceEnd(),0)
  PokeI(#NRT_REPORT+16,nrtFailure) : PokeI(#NRT_REPORT+24,nrtChecks)
  ProcedureReturn nrtFailure
EndProcedure

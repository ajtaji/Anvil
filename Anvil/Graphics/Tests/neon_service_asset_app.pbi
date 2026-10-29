; SPDX-License-Identifier: MIT
; Decode/file ownership faults followed by real resident image presentation.
EnableFloatingPoint
XIncludeFile "Anvil/Math/float32.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Hal/file_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_sprite.pbi"
XIncludeFile "Anvil/Graphics/neon_sprite_decode.pbi"
XIncludeFile "Anvil/Graphics/neon_service_asset.pbi"
Global naeChecks.i,naeFailure.i,naeCloseFail.i,naeReadMode.i,naeReadCalls.i,naeCloseCalls.i,naeReentry.i
Global Dim naeTable.q[202]
Global Dim naeEncoded.q[64]
Global Dim naeRgba.q[64]
Global Dim naeMask.q[16]
Procedure NaeCheck(actual.i,expected.i)
  naeChecks=naeChecks+1
  PokeI(#NAE_REPORT+128+naeChecks*16,actual) : PokeI(#NAE_REPORT+136+naeChecks*16,expected)
  If actual<>expected And naeFailure=0 : naeFailure=naeChecks : EndIf
  PokeI(#NAE_REPORT+16,naeFailure) : PokeI(#NAE_REPORT+24,naeChecks)
EndProcedure
Procedure.i NaeOpen(name.i)
  naeReentry=AnvilFileUnbind()
  ProcedureReturn 1
EndProcedure
Procedure.i NaeSize(h.i)
  ProcedureReturn 78
EndProcedure
Procedure.i NaeClose(h.i)
  naeCloseCalls=naeCloseCalls+1 : ProcedureReturn naeCloseFail
EndProcedure
Procedure.i NaeRead(h.i,offset.i,dst.i,bytes.i)
  Protected i.i,count.i=3
  naeReadCalls=naeReadCalls+1
  If naeReadMode=1 : ProcedureReturn bytes+1 : EndIf
  If naeReadMode=2 : ProcedureReturn 0 : EndIf
  If naeReadMode=3 : ProcedureReturn -105 : EndIf
  If count>bytes : count=bytes : EndIf
  For i=0 To count-1 : PokeA(dst+i,PeekA(?naeBmp24+offset+i)) : Next
  ProcedureReturn count
EndProcedure
Procedure.i Main(services.i)
  Protected i.i,h.i,first.i,second.i,info.NeonSpriteAssetInfo
  For i=0 To 4095 Step 8 : PokeI(#NAE_REPORT+i,0) : Next
  PokeI(#NAE_REPORT,$4E414531) : PokeI(#NAE_REPORT+8,1)
  ; A complete service-table header gates every borrowed function address.
  PokeL(@naeTable[0],$53564E41) : PokeL(@naeTable[0]+4,1)
  PokeL(@naeTable[0]+8,3) : PokeL(@naeTable[0]+12,200)
  NaeCheck(AnvilFileBind(@naeTable[0]),#ANVIL_FILE_EABI)
  PokeL(@naeTable[0]+8,4)
  NaeCheck(AnvilFileBind(@naeTable[0]),#ANVIL_FILE_ENOSYS)
  PokeI(@naeTable[0]+16+192*8,@NaeOpen) : PokeI(@naeTable[0]+16+193*8,@NaeSize)
  PokeI(@naeTable[0]+16+194*8,@NaeRead) : PokeI(@naeTable[0]+16+195*8,@NaeClose)
  NaeCheck(AnvilFileBind(@naeTable[0]),0)
  NaeCheck(AnvilFileReadWhole("fixture",@naeEncoded[0],512),78)
  NaeCheck(naeReadCalls,26) : NaeCheck(naeCloseCalls,1)
  NaeCheck(naeReentry,#ANVIL_FILE_EBUSY)
  For i=0 To 77 : NaeCheck(PeekA(@naeEncoded[0]+i),PeekA(?naeBmp24+i)) : Next
  naeCloseFail=-105
  NaeCheck(AnvilFileReadWhole("fixture",@naeEncoded[0],512),-105)
  NaeCheck(AnvilFileRetainedHandle(),1)
  NaeCheck(AnvilFileUnbind(),#ANVIL_FILE_EBUSY)
  NaeCheck(AnvilFileReadWhole("fixture",@naeEncoded[0],512),#ANVIL_FILE_EBUSY)
  naeCloseFail=0
  NaeCheck(AnvilFileClose(1),0) : NaeCheck(AnvilFileRetainedHandle(),0)
  naeCloseFail=1
  NaeCheck(AnvilFileReadWhole("fixture",@naeEncoded[0],512),#ANVIL_FILE_EIO)
  NaeCheck(AnvilFileRetainedHandle(),1)
  naeCloseFail=0 : NaeCheck(AnvilFileClose(1),0)
  naeReadMode=1 : NaeCheck(AnvilFileReadWhole("fixture",@naeEncoded[0],512),#ANVIL_FILE_EIO)
  naeReadMode=2 : NaeCheck(AnvilFileReadWhole("fixture",@naeEncoded[0],512),#ANVIL_FILE_EIO)
  naeReadMode=3 : NaeCheck(AnvilFileReadWhole("fixture",@naeEncoded[0],512),-105)
  NaeCheck(AnvilFileReadWhole("fixture",@naeEncoded[0],77),#ANVIL_FILE_EARG)
  NaeCheck(AnvilFileUnbind(),0)
  ; Decode failures must not publish new dimensions or touch output bytes.
  info\width=991 : info\height=992
  NaeCheck(NeonSpriteDecodeMemory(@info,?naeBmp24,77,@naeRgba[0],512,-1,@naeMask[0],128),#NEON_ASSET_ERR_TRUNCATED)
  NaeCheck(info\width,991) : NaeCheck(info\height,992)
  NaeCheck(NeonSpriteDecodeMemory(@info,?naeBmp24,78,@naeRgba[0],23,-1,0,0),#NEON_ASSET_ERR_CAPACITY)
  NaeCheck(NeonSpriteDecodeMemory(@info,?naeBmp24,78,@naeRgba[0],512,-1,@naeMask[0],5),#NEON_ASSET_ERR_CAPACITY)
  NaeCheck(NeonSpriteDecodeMemory(@info,?naeBmp24,78,?naeBmp24,78,-1,0,0),#NEON_ASSET_ERR_ARGUMENT)
  NaeCheck(NeonSpriteDecodeRGBA(@info,$7FFFFFFFFFFFFFFE,4,1,1,@naeRgba[0],512,-1,0,0),#NEON_ASSET_ERR_ARGUMENT)
  For i=0 To 77 : PokeA(@naeEncoded[0]+i,PeekA(?naeBmp24+i)) : Next
  PokeA(@naeEncoded[0],0)
  NaeCheck(NeonSpriteDecodeMemory(@info,@naeEncoded[0],78,@naeRgba[0],512,-1,0,0),#NEON_ASSET_ERR_FORMAT)
  PokeA(@naeEncoded[0],66) : PokeA(@naeEncoded[0]+18,0)
  NaeCheck(NeonSpriteDecodeMemory(@info,@naeEncoded[0],78,@naeRgba[0],512,-1,0,0),#NEON_ASSET_ERR_FORMAT)
  PokeA(@naeEncoded[0]+18,3) : PokeA(@naeEncoded[0]+30,1)
  NaeCheck(NeonSpriteDecodeMemory(@info,@naeEncoded[0],78,@naeRgba[0],512,-1,0,0),#NEON_ASSET_ERR_FORMAT)
  PokeA(@naeEncoded[0]+30,0) : PokeA(@naeEncoded[0]+10,53)
  NaeCheck(NeonSpriteDecodeMemory(@info,@naeEncoded[0],78,@naeRgba[0],512,-1,0,0),#NEON_ASSET_ERR_FORMAT)
  NaeCheck(info\width,991) : NaeCheck(info\height,992)
  NaeCheck(NeonSpriteDecodeMemory(@info,?naeBmp24,78,@naeRgba[0],512,$FF00FF,@naeMask[0],128),0)
  NaeCheck(info\width,3) : NaeCheck(info\height,2)
  For i=0 To 23 : PokeA(#NAE_REPORT+2304+i,PeekA(@naeRgba[0]+i)) : Next
  For i=0 To 5 : PokeA(#NAE_REPORT+2336+i,PeekA(@naeMask[0]+i)) : Next
  NaeCheck(NeonSpriteDecodeMemory(@info,?naeBmp32,70,@naeRgba[0],512,-1,@naeMask[0],128),0)
  NaeCheck(info\width,2) : NaeCheck(info\height,2)
  For i=0 To 15 : PokeA(#NAE_REPORT+2368+i,PeekA(@naeRgba[0]+i)) : Next
  For i=0 To 3 : PokeA(#NAE_REPORT+2400+i,PeekA(@naeMask[0]+i)) : Next
  ; Actual file handles and resident Vulkan from this point onwards.
  NaeCheck(AnvilFileBind(services),0)
  NaeCheck(NeonServiceBind(services,5),0) : NaeCheck(NeonServiceOpen(),0)
  If naeFailure<>0 : ProcedureReturn naeFailure : EndIf
  first=NeonServiceSpriteLoadFile(1,"1:/NS24A.BMP",@naeEncoded[0],512,@naeRgba[0],512,$FF00FF,@naeMask[0],128)
  NaeCheck(Bool(first>0),1)
  second=NeonServiceSpriteLoadMemory(2,?naeBmp32,70,@naeRgba[0],512,-1,@naeMask[0],128)
  NaeCheck(Bool(second>first),1)
  h=AnvilFileOpen("1:/NS24A.BMP") : NaeCheck(Bool(h>0),1)
  NaeCheck(AnvilFileSize(h),78)
  NaeCheck(AnvilFileReadAt(h,54,@naeEncoded[0],12),12)
  NaeCheck(AnvilFileClose(h),0)
  NaeCheck(AnvilFileRetainedHandle(),0) : NaeCheck(AnvilFileUnbind(),0)
  For i=0 To 511 : PokeA(@naeRgba[0]+i,0) : PokeA(@naeEncoded[0]+i,0) : Next
  NaeCheck(NeonServiceBegin(0.0,0.0,1.0,1.0),0)
  NaeCheck(NeonServiceSprite(first,80.0,100.0,0.0,40.0,1.0,1.0,1.0,1.0,1,0.0,0.0,3.0,2.0,1),0)
  NaeCheck(NeonServiceSprite(second,300.0,100.0,0.0,40.0,1.0,1.0,1.0,1.0,1,0.0,0.0,2.0,2.0,1),0)
  NaeCheck(NeonServiceEnd(),0)
  PokeI(#NAE_REPORT+32,NeonServiceContext())
  ProcedureReturn naeFailure
EndProcedure

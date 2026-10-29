; SPDX-License-Identifier: MIT
; Decode/file ownership faults followed by real resident image presentation.
EnableFloatingPoint
#CRC_POLY=$EDB88320
XIncludeFile "Anvil/Core/crc.pbi"
XIncludeFile "Anvil/Graphics/neon_sprite_decoder_png.pbi"
XIncludeFile "Anvil/Math/float32.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Hal/file_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_sprite.pbi"
XIncludeFile "Anvil/Graphics/neon_sprite_decode.pbi"
XIncludeFile "Anvil/Graphics/neon_service_asset.pbi"
Global nadChecks.i,nadFailure.i,nadCloseFail.i,nadReadMode.i,nadReadCalls.i,nadCloseCalls.i,nadReentry.i
Global Dim nadTable.q[202]
Global Dim nadEncoded.q[256]
Global Dim nadRgba.q[256]
Global Dim nadMask.q[32]
Procedure NadCheck(actual.i,expected.i)
  nadChecks=nadChecks+1
  PokeI(#NAE_REPORT+128+nadChecks*16,actual) : PokeI(#NAE_REPORT+136+nadChecks*16,expected)
  If actual<>expected And nadFailure=0 : nadFailure=nadChecks : EndIf
  PokeI(#NAE_REPORT+16,nadFailure) : PokeI(#NAE_REPORT+24,nadChecks)
EndProcedure
Procedure.i NadOpen(name.i)
  nadReentry=AnvilFileUnbind()
  ProcedureReturn 1
EndProcedure
Procedure.i NadSize(h.i)
  ProcedureReturn 78
EndProcedure
Procedure.i NadClose(h.i)
  nadCloseCalls=nadCloseCalls+1 : ProcedureReturn nadCloseFail
EndProcedure
Procedure.i NadRead(h.i,offset.i,dst.i,bytes.i)
  Protected i.i,count.i=3
  nadReadCalls=nadReadCalls+1
  If nadReadMode=1 : ProcedureReturn bytes+1 : EndIf
  If nadReadMode=2 : ProcedureReturn 0 : EndIf
  If nadReadMode=3 : ProcedureReturn -105 : EndIf
  If count>bytes : count=bytes : EndIf
  For i=0 To count-1 : PokeA(dst+i,PeekA(?nadBmp24+offset+i)) : Next
  ProcedureReturn count
EndProcedure

Global naiChecks.i,naiFailure.i,naiInstallBusy.i,naiPngBusy.i,naiResetBusy.i
Global naiThird.i,naiFourth.i
Global Dim naiScratch.q[8192]
Procedure NaiCheck(actual.i,expected.i)
  naiChecks=naiChecks+1
  PokeI(#NAE_REPORT+4080+naiChecks*16,actual)
  PokeI(#NAE_REPORT+4088+naiChecks*16,expected)
  If actual<>expected And naiFailure=0 : naiFailure=naiChecks : EndIf
  PokeI(#NAE_REPORT+64,naiChecks) : PokeI(#NAE_REPORT+72,naiFailure)
EndProcedure
Procedure.i NaiMock(info.i,encoded.i,bytes.i,rgba.i,capacity.i,key.i,mask.i,maskCapacity.i)
  naiInstallBusy=NeonSpriteDecoderInstall(@NaiMock,1024)
  naiPngBusy=NeonSpriteDecoderPngInstall(@naiScratch[0],65536)
  naiResetBusy=NeonSpriteDecoderReset()
  ProcedureReturn 17
EndProcedure
Procedure.i NaiExercise(services.i)
  Protected i.i,info.NeonSpriteAssetInfo,handle.i
  NaiCheck(NeonSpriteDecoderMaxSource(),4194432)
  NaiCheck(NeonSpriteDecoderInstall(0,1024),-21320)
  NaiCheck(NeonSpriteDecoderInstall(@NaiMock,0),-21320)
  NaiCheck(NeonSpriteDecoderInstall(@NaiMock,16777217),-21320)
  NaiCheck(NeonSpriteDecoderPngInstall(0,65536),-21320)
  NaiCheck(NeonSpriteDecoderPngInstall(@naiScratch[0]+1,65536),-21320)
  NaiCheck(NeonSpriteDecoderPngInstall(@naiScratch[0],8191),-21320)
  NaiCheck(NeonSpriteDecoderPngInstall($7FFFFFFFFFFFFFE0,8192),-21320)
  NaiCheck(NeonSpriteDecoderMaxSource(),4194432)
  NaiCheck(NeonSpriteDecoderInstall(@NaiMock,1024),0)
  NaiCheck(NeonSpriteDecodeAssetMemory(0,0,0,0,0,0,0,0),-21326)
  NaiCheck(naiInstallBusy,-21325)
  NaiCheck(naiPngBusy,-21325)
  NaiCheck(naiResetBusy,-21325)
  NaiCheck(NeonSpriteDecoderMaxSource(),1024)
  NaiCheck(NeonSpriteDecoderBusy(),0)
  NaiCheck(NeonSpriteDecoderPngInstall(@naiScratch[0],65536),0)
  NaiCheck(NeonSpriteDecoderMaxSource(),16777216)
  NaiCheck(NeonSpriteDecoderPngInstall(0,65536),-21320)
  NaiCheck(NeonSpriteDecoderMaxSource(),16777216)
  NaiCheck(AnvilFileBind(services),0)
  naiThird=NeonServiceSpriteLoadFile(3,"1:/NPNG457.PNG",@nadEncoded[0],2048,@nadRgba[0],2048,-1,@nadMask[0],256)
  NaiCheck(Bool(naiThird>0),1)
  NaiCheck(AnvilFileRetainedHandle(),0)
  info\width=991 : info\height=992
  NaiCheck(NeonSpriteDecodeAssetMemory(@info,@nadEncoded[0],943,@nadRgba[0],2048,-1,@nadMask[0],256),0)
  NaiCheck(info\width,13)
  NaiCheck(info\height,11)
  For i=0 To 571 : PokeA(#NAE_REPORT+6144+i,PeekA(@nadRgba[0]+i)) : Next
  For i=0 To 142 : PokeA(#NAE_REPORT+6720+i,PeekA(@nadMask[0]+i)) : Next
  naiFourth=NeonServiceSpriteLoadMemory(4,@nadEncoded[0],943,@nadRgba[0],2048,-1,@nadMask[0],256)
  NaiCheck(Bool(naiFourth>naiThird),1)
  info\width=991 : info\height=992
  For i=0 To 2047 : PokeA(@nadRgba[0]+i,123) : Next
  For i=0 To 255 : PokeA(@nadMask[0]+i,124) : Next
  NaiCheck(NeonSpriteDecoderPngInstall(@naiScratch[0],8192),0)
  NaiCheck(NeonSpriteDecodeAssetMemory(@info,@nadEncoded[0],943,@nadRgba[0],2048,-1,@nadMask[0],256),-23003)
  NaiCheck(info\width,991)
  NaiCheck(info\height,992)
  For i=0 To 2047 : If PeekA(@nadRgba[0]+i)<>123 : NaiCheck(-1,0) : Break : EndIf : Next
  For i=0 To 255 : If PeekA(@nadMask[0]+i)<>124 : NaiCheck(-2,0) : Break : EndIf : Next
  NaiCheck(NeonSpriteDecoderPngInstall(@naiScratch[0],65536),0)
  NaiCheck(NeonSpriteDecodeAssetMemory(@info,@nadEncoded[0],943,@naiScratch[0],2048,-1,@nadMask[0],256),-23000)
  NaiCheck(info\width,991)
  NaiCheck(info\height,992)
  NaiCheck(NeonSpriteDecoderPngReset(),0)
  NaiCheck(NeonSpriteDecoderMaxSource(),4194432)
  NaiCheck(NeonSpriteDecodeAssetMemory(@info,@nadEncoded[0],943,@nadRgba[0],2048,-1,@nadMask[0],256),-21321)
  NaiCheck(info\width,991)
  NaiCheck(info\height,992)
  handle=NeonServiceSpriteLoadMemory(5,?nadBmp32,70,@nadRgba[0],2048,-1,@nadMask[0],256)
  NaiCheck(Bool(handle>naiFourth),1)
  NaiCheck(AnvilFileUnbind(),0)
  NaiCheck(NeonSpriteDecoderPngReset(),0)
  For i=0 To 2047 : PokeA(@nadRgba[0]+i,0) : PokeA(@nadEncoded[0]+i,0) : Next
  For i=0 To 65535 : PokeA(@naiScratch[0]+i,0) : Next
  PokeI(#NAE_REPORT+80,$4E494431) : PokeI(#NAE_REPORT+88,naiThird) : PokeI(#NAE_REPORT+96,naiFourth)
  ProcedureReturn naiFailure
EndProcedure

Procedure.i Main(services.i)
  Protected i.i,h.i,first.i,second.i,info.NeonSpriteAssetInfo
  For i=0 To 8191 Step 8 : PokeI(#NAE_REPORT+i,0) : Next
  PokeI(#NAE_REPORT,$4E414531) : PokeI(#NAE_REPORT+8,1)
  ; A complete service-table header gates every borrowed function address.
  PokeL(@nadTable[0],$53564E41) : PokeL(@nadTable[0]+4,1)
  PokeL(@nadTable[0]+8,3) : PokeL(@nadTable[0]+12,200)
  NadCheck(AnvilFileBind(@nadTable[0]),#ANVIL_FILE_EABI)
  PokeL(@nadTable[0]+8,4)
  NadCheck(AnvilFileBind(@nadTable[0]),#ANVIL_FILE_ENOSYS)
  PokeI(@nadTable[0]+16+192*8,@NadOpen) : PokeI(@nadTable[0]+16+193*8,@NadSize)
  PokeI(@nadTable[0]+16+194*8,@NadRead) : PokeI(@nadTable[0]+16+195*8,@NadClose)
  NadCheck(AnvilFileBind(@nadTable[0]),0)
  NadCheck(AnvilFileReadWhole("fixture",@nadEncoded[0],512),78)
  NadCheck(nadReadCalls,26) : NadCheck(nadCloseCalls,1)
  NadCheck(nadReentry,#ANVIL_FILE_EBUSY)
  For i=0 To 77 : NadCheck(PeekA(@nadEncoded[0]+i),PeekA(?nadBmp24+i)) : Next
  nadCloseFail=-105
  NadCheck(AnvilFileReadWhole("fixture",@nadEncoded[0],512),-105)
  NadCheck(AnvilFileRetainedHandle(),1)
  NadCheck(AnvilFileUnbind(),#ANVIL_FILE_EBUSY)
  NadCheck(AnvilFileReadWhole("fixture",@nadEncoded[0],512),#ANVIL_FILE_EBUSY)
  nadCloseFail=0
  NadCheck(AnvilFileClose(1),0) : NadCheck(AnvilFileRetainedHandle(),0)
  nadCloseFail=1
  NadCheck(AnvilFileReadWhole("fixture",@nadEncoded[0],512),#ANVIL_FILE_EIO)
  NadCheck(AnvilFileRetainedHandle(),1)
  nadCloseFail=0 : NadCheck(AnvilFileClose(1),0)
  nadReadMode=1 : NadCheck(AnvilFileReadWhole("fixture",@nadEncoded[0],512),#ANVIL_FILE_EIO)
  nadReadMode=2 : NadCheck(AnvilFileReadWhole("fixture",@nadEncoded[0],512),#ANVIL_FILE_EIO)
  nadReadMode=3 : NadCheck(AnvilFileReadWhole("fixture",@nadEncoded[0],512),-105)
  NadCheck(AnvilFileReadWhole("fixture",@nadEncoded[0],77),#ANVIL_FILE_EARG)
  NadCheck(AnvilFileUnbind(),0)
  ; Decode failures must not publish new dimensions or touch output bytes.
  info\width=991 : info\height=992
  NadCheck(NeonSpriteDecodeMemory(@info,?nadBmp24,77,@nadRgba[0],512,-1,@nadMask[0],128),#NEON_ASSET_ERR_TRUNCATED)
  NadCheck(info\width,991) : NadCheck(info\height,992)
  NadCheck(NeonSpriteDecodeMemory(@info,?nadBmp24,78,@nadRgba[0],23,-1,0,0),#NEON_ASSET_ERR_CAPACITY)
  NadCheck(NeonSpriteDecodeMemory(@info,?nadBmp24,78,@nadRgba[0],512,-1,@nadMask[0],5),#NEON_ASSET_ERR_CAPACITY)
  NadCheck(NeonSpriteDecodeMemory(@info,?nadBmp24,78,?nadBmp24,78,-1,0,0),#NEON_ASSET_ERR_ARGUMENT)
  NadCheck(NeonSpriteDecodeRGBA(@info,$7FFFFFFFFFFFFFFE,4,1,1,@nadRgba[0],512,-1,0,0),#NEON_ASSET_ERR_ARGUMENT)
  For i=0 To 77 : PokeA(@nadEncoded[0]+i,PeekA(?nadBmp24+i)) : Next
  PokeA(@nadEncoded[0],0)
  NadCheck(NeonSpriteDecodeMemory(@info,@nadEncoded[0],78,@nadRgba[0],512,-1,0,0),#NEON_ASSET_ERR_FORMAT)
  PokeA(@nadEncoded[0],66) : PokeA(@nadEncoded[0]+18,0)
  NadCheck(NeonSpriteDecodeMemory(@info,@nadEncoded[0],78,@nadRgba[0],512,-1,0,0),#NEON_ASSET_ERR_FORMAT)
  PokeA(@nadEncoded[0]+18,3) : PokeA(@nadEncoded[0]+30,1)
  NadCheck(NeonSpriteDecodeMemory(@info,@nadEncoded[0],78,@nadRgba[0],512,-1,0,0),#NEON_ASSET_ERR_FORMAT)
  PokeA(@nadEncoded[0]+30,0) : PokeA(@nadEncoded[0]+10,53)
  NadCheck(NeonSpriteDecodeMemory(@info,@nadEncoded[0],78,@nadRgba[0],512,-1,0,0),#NEON_ASSET_ERR_FORMAT)
  NadCheck(info\width,991) : NadCheck(info\height,992)
  NadCheck(NeonSpriteDecodeMemory(@info,?nadBmp24,78,@nadRgba[0],512,$FF00FF,@nadMask[0],128),0)
  NadCheck(info\width,3) : NadCheck(info\height,2)
  For i=0 To 23 : PokeA(#NAE_REPORT+2304+i,PeekA(@nadRgba[0]+i)) : Next
  For i=0 To 5 : PokeA(#NAE_REPORT+2336+i,PeekA(@nadMask[0]+i)) : Next
  NadCheck(NeonSpriteDecodeMemory(@info,?nadBmp32,70,@nadRgba[0],512,-1,@nadMask[0],128),0)
  NadCheck(info\width,2) : NadCheck(info\height,2)
  For i=0 To 15 : PokeA(#NAE_REPORT+2368+i,PeekA(@nadRgba[0]+i)) : Next
  For i=0 To 3 : PokeA(#NAE_REPORT+2400+i,PeekA(@nadMask[0]+i)) : Next
  ; Actual file handles and resident Vulkan from this point onwards.
  NadCheck(AnvilFileBind(services),0)
  NadCheck(NeonServiceBind(services,5),0) : NadCheck(NeonServiceOpen(),0)
  If nadFailure<>0 : ProcedureReturn nadFailure : EndIf
  first=NeonServiceSpriteLoadFile(1,"1:/NS24A.BMP",@nadEncoded[0],512,@nadRgba[0],512,$FF00FF,@nadMask[0],128)
  NadCheck(Bool(first>0),1)
  second=NeonServiceSpriteLoadMemory(2,?nadBmp32,70,@nadRgba[0],512,-1,@nadMask[0],128)
  NadCheck(Bool(second>first),1)
  h=AnvilFileOpen("1:/NS24A.BMP") : NadCheck(Bool(h>0),1)
  NadCheck(AnvilFileSize(h),78)
  NadCheck(AnvilFileReadAt(h,54,@nadEncoded[0],12),12)
  NadCheck(AnvilFileClose(h),0)
  NadCheck(AnvilFileRetainedHandle(),0) : NadCheck(AnvilFileUnbind(),0)
  For i=0 To 511 : PokeA(@nadRgba[0]+i,0) : PokeA(@nadEncoded[0]+i,0) : Next
  If NaiExercise(services)<>0 : ProcedureReturn 1000+naiFailure : EndIf
  NadCheck(NeonServiceBegin(0.0,0.0,1.0,1.0),0)
  NadCheck(NeonServiceSprite(first,80.0,100.0,0.0,40.0,1.0,1.0,1.0,1.0,1,0.0,0.0,3.0,2.0,1),0)
  NadCheck(NeonServiceSprite(second,300.0,100.0,0.0,40.0,1.0,1.0,1.0,1.0,1,0.0,0.0,2.0,2.0,1),0)
  If NeonServiceSprite(naiThird,600.0,300.0,0.0,8.0,1.0,1.0,1.0,1.0,1,0.0,0.0,13.0,11.0,1)<>0 : ProcedureReturn 2001 : EndIf
  If NeonServiceSprite(naiFourth,760.0,300.0,0.0,8.0,1.0,1.0,1.0,1.0,1,0.0,0.0,13.0,11.0,1)<>0 : ProcedureReturn 2002 : EndIf
  NadCheck(NeonServiceEnd(),0)
  PokeI(#NAE_REPORT+32,NeonServiceContext())
  ProcedureReturn nadFailure
EndProcedure

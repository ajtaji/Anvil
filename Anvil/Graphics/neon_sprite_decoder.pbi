; SPDX-License-Identifier: MIT
; Shared encoded-image decoder selection. Default is the existing BMP decoder.
; Installers supply the same eight-argument transactional decode contract.
; maxSourceBytes bounds file reads; each decoder validates its own memory input.
XIncludeFile "Anvil/Graphics/neon_sprite_decode.pbi"
#NEON_ASSET_ERR_BUSY=-21325
#NEON_ASSET_ERR_PROVIDER=-21326
#NEON_ASSET_DECODER_MAX_SOURCE=16777216
Global nsdDecode.i=@NeonSpriteDecodeMemory,nsdMaxSource.i=#NEON_ASSET_MAX_BYTES,nsdBusy.i
Procedure.i NeonSpriteDecoderMaxSource()
  ProcedureReturn nsdMaxSource
EndProcedure
Procedure.i NeonSpriteDecoderBusy()
  ProcedureReturn nsdBusy
EndProcedure
Procedure.i NeonSpriteDecoderInstall(decoder.i,maxSourceBytes.i)
  If nsdBusy<>0 : ProcedureReturn #NEON_ASSET_ERR_BUSY : EndIf
  If decoder<=0 Or maxSourceBytes<1 Or maxSourceBytes>#NEON_ASSET_DECODER_MAX_SOURCE : ProcedureReturn #NEON_ASSET_ERR_ARGUMENT : EndIf
  nsdDecode=decoder : nsdMaxSource=maxSourceBytes
  ProcedureReturn 0
EndProcedure
Procedure.i NeonSpriteDecoderReset()
  ProcedureReturn NeonSpriteDecoderInstall(@NeonSpriteDecodeMemory,#NEON_ASSET_MAX_BYTES)
EndProcedure
Procedure.i NeonSpriteDecodeAssetMemory(info.i,encoded.i,encodedBytes.i,rgba.i,rgbaCapacity.i,colourKey.i,mask.i,maskCapacity.i)
  Protected rc.i
  If nsdBusy<>0 : ProcedureReturn #NEON_ASSET_ERR_BUSY : EndIf
  nsdBusy=1 : rc=nsdDecode(info,encoded,encodedBytes,rgba,rgbaCapacity,colourKey,mask,maskCapacity) : nsdBusy=0
  If rc>0 : ProcedureReturn #NEON_ASSET_ERR_PROVIDER : EndIf
  ProcedureReturn rc
EndProcedure

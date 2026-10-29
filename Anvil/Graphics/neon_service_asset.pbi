; SPDX-License-Identifier: MIT
; Pure application asset bridge: decode in caller-owned memory, then ask the
; resident owner to copy RGBA. Include sprite and file service clients.
XIncludeFile "Anvil/Graphics/neon_sprite_decoder.pbi"
Procedure.i NeonServiceSpriteLoadRGBA(slot.i,source.i,sourceBytes.i,width.i,height.i,rgba.i,rgbaCapacity.i,colourKey.i,mask.i,maskCapacity.i)
  Protected info.NeonSpriteAssetInfo,rc.i
  If slot<1 Or slot>#NEON_SERVICE_MAX_SPRITES : NeonServiceExtensionStatus(#NEON_ASSET_ERR_ARGUMENT) : ProcedureReturn 0 : EndIf
  rc=NeonSpriteDecodeRGBA(@info,source,sourceBytes,width,height,rgba,rgbaCapacity,colourKey,mask,maskCapacity)
  If rc<>0 : NeonServiceExtensionStatus(rc) : ProcedureReturn 0 : EndIf
  ProcedureReturn NeonServiceSpriteUpload(slot,rgba,info\width*info\height*4,info\width,info\height,0)
EndProcedure
Procedure.i NeonServiceSpriteLoadMemory(slot.i,encoded.i,encodedBytes.i,rgba.i,rgbaCapacity.i,colourKey.i,mask.i,maskCapacity.i)
  Protected info.NeonSpriteAssetInfo,rc.i
  If slot<1 Or slot>#NEON_SERVICE_MAX_SPRITES : NeonServiceExtensionStatus(#NEON_ASSET_ERR_ARGUMENT) : ProcedureReturn 0 : EndIf
  rc=NeonSpriteDecodeAssetMemory(@info,encoded,encodedBytes,rgba,rgbaCapacity,colourKey,mask,maskCapacity)
  If rc<>0 : NeonServiceExtensionStatus(rc) : ProcedureReturn 0 : EndIf
  ProcedureReturn NeonServiceSpriteUpload(slot,rgba,info\width*info\height*4,info\width,info\height,0)
EndProcedure
Procedure.i NeonServiceSpriteLoadFile(slot.i,path.i,encoded.i,encodedCapacity.i,rgba.i,rgbaCapacity.i,colourKey.i,mask.i,maskCapacity.i)
  Protected bytes.i
  If slot<1 Or slot>#NEON_SERVICE_MAX_SPRITES Or path=0 Or encodedCapacity<1
    NeonServiceExtensionStatus(#NEON_ASSET_ERR_ARGUMENT) : ProcedureReturn 0
  EndIf
  If encodedCapacity>NeonSpriteDecoderMaxSource() : encodedCapacity=NeonSpriteDecoderMaxSource() : EndIf
  bytes=AnvilFileReadWhole(path,encoded,encodedCapacity)
  If bytes<0 : NeonServiceExtensionStatus(bytes) : ProcedureReturn 0 : EndIf
  ProcedureReturn NeonServiceSpriteLoadMemory(slot,encoded,bytes,rgba,rgbaCapacity,colourKey,mask,maskCapacity)
EndProcedure

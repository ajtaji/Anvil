; Bounded native asset bridge; CPU decoding belongs to the pure Graphics owner.
XIncludeFile "Anvil/Graphics/neon_sprite_decoder.pbi"

#NEON_VK_ASSET_MAX_DIM = #NEON_ASSET_MAX_DIM
#NEON_VK_ASSET_MAX_BYTES = #NEON_ASSET_MAX_BYTES
#NEON_VK_ASSET_ERR_ARGUMENT = #NEON_ASSET_ERR_ARGUMENT
#NEON_VK_ASSET_ERR_FORMAT = #NEON_ASSET_ERR_FORMAT
#NEON_VK_ASSET_ERR_TRUNCATED = #NEON_ASSET_ERR_TRUNCATED
#NEON_VK_ASSET_ERR_CAPACITY = #NEON_ASSET_ERR_CAPACITY
#NEON_VK_ASSET_ERR_IO = #NEON_ASSET_ERR_IO

Procedure.i NeonVkPortSpriteLoadRGBA(*sprite.NeonVkPortSpriteRef, id.i, *source, sourceBytes.i, width.i, height.i, *rgba, rgbaCapacity.i, colourKey.i, *mask, maskCapacity.i)
  Protected info.NeonSpriteAssetInfo,rc.i
  If *sprite=0 Or id<1 Or id>16 : ProcedureReturn #NEON_VK_ASSET_ERR_ARGUMENT : EndIf
  If nvpBatchActive<>0 : ProcedureReturn #NEON_VK_PORT_ERR_BATCH : EndIf
  rc=NeonSpriteDecodeRGBA(@info,*source,sourceBytes,width,height,*rgba,rgbaCapacity,colourKey,*mask,maskCapacity)
  If rc<>0 : ProcedureReturn rc : EndIf
  ProcedureReturn NeonVkPortSpriteUpload(*sprite,id,*rgba,info\width,info\height,0)
EndProcedure

Procedure.i NeonVkPortSpriteLoadMemory(*sprite.NeonVkPortSpriteRef, id.i, *encoded, encodedBytes.i, *rgba, rgbaCapacity.i, colourKey.i, *mask, maskCapacity.i)
  Protected info.NeonSpriteAssetInfo,rc.i
  If *sprite=0 Or id<1 Or id>16 : ProcedureReturn #NEON_VK_ASSET_ERR_ARGUMENT : EndIf
  If nvpBatchActive<>0 : ProcedureReturn #NEON_VK_PORT_ERR_BATCH : EndIf
  rc=NeonSpriteDecodeAssetMemory(@info,*encoded,encodedBytes,*rgba,rgbaCapacity,colourKey,*mask,maskCapacity)
  If rc<>0 : ProcedureReturn rc : EndIf
  ProcedureReturn NeonVkPortSpriteUpload(*sprite,id,*rgba,info\width,info\height,0)
EndProcedure

; HwFile* is the board-neutral Anvil file seam. It does not mount storage.
; ReadAt can return a partial count; the loop checks progress and closes on
; every path. The encoded buffer may be reused after the call returns.
Procedure.i NeonVkPortSpriteLoadFile(*sprite.NeonVkPortSpriteRef, id.i, *path, *encoded, encodedCapacity.i, *rgba, rgbaCapacity.i, colourKey.i, *mask, maskCapacity.i)
  Protected size.i, offset.i, count.i, result.i
  If *sprite = 0 Or *path = 0 Or *encoded = 0 Or *rgba = 0 Or id < 1 Or id > 16 Or encodedCapacity < 1
    ProcedureReturn #NEON_VK_ASSET_ERR_ARGUMENT
  EndIf
  If nvpBatchActive <> 0 : ProcedureReturn #NEON_VK_PORT_ERR_BATCH : EndIf
  If NeonSpriteAssetSpan(*encoded,encodedCapacity)=0 : ProcedureReturn #NEON_VK_ASSET_ERR_ARGUMENT : EndIf
  If HwFileOpen(*path) = 0 : ProcedureReturn #NEON_VK_ASSET_ERR_IO : EndIf
  size = HwFileSize()
  If size < 1
    HwFileClose()
    ProcedureReturn #NEON_VK_ASSET_ERR_FORMAT
  EndIf
  If size > encodedCapacity Or size > NeonSpriteDecoderMaxSource()
    HwFileClose()
    ProcedureReturn #NEON_VK_ASSET_ERR_CAPACITY
  EndIf
  offset = 0
  While offset < size
    count = HwFileReadAt(offset, *encoded + offset, size - offset)
    If count < 0 Or count > size-offset
      HwFileClose()
      ProcedureReturn #NEON_VK_ASSET_ERR_IO
    EndIf
    If count = 0
      HwFileClose()
      ProcedureReturn #NEON_VK_ASSET_ERR_TRUNCATED
    EndIf
    offset = offset + count
  Wend
  HwFileClose()
  result = NeonVkPortSpriteLoadMemory(*sprite, id, *encoded, size, *rgba, rgbaCapacity, colourKey, *mask, maskCapacity)
  ProcedureReturn result
EndProcedure

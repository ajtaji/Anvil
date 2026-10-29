; SPDX-License-Identifier: MIT
; Explicit scratch-backed PNG memory/file loading into the resident sprite owner.
XIncludeFile "Anvil/Graphics/neon_png_decode.pbi"
XIncludeFile "Anvil/Hal/file_service_client.pbi"
Procedure.i NeonServiceSpriteLoadPNGMemory(slot.i,source.i,bytes.i,rgba.i,capacity.i,colourKey.i,mask.i,maskCapacity.i,scratch.i,scratchCapacity.i)
  Protected info.NeonSpriteAssetInfo,rc.i
  If slot<1 Or slot>#NEON_SERVICE_MAX_SPRITES : NeonServiceExtensionStatus(#NEON_PNG_ERR_ARGUMENT) : ProcedureReturn 0 : EndIf
  rc=NeonPngDecode(@info,source,bytes,rgba,capacity,colourKey,mask,maskCapacity,scratch,scratchCapacity)
  If rc<>0 : NeonServiceExtensionStatus(rc) : ProcedureReturn 0 : EndIf
  ProcedureReturn NeonServiceSpriteUpload(slot,rgba,info\width*info\height*4,info\width,info\height,0)
EndProcedure
Procedure.i NeonServiceSpriteLoadPNGFile(slot.i,path.i,encoded.i,encodedCapacity.i,rgba.i,capacity.i,colourKey.i,mask.i,maskCapacity.i,scratch.i,scratchCapacity.i)
  Protected bytes.i
  If slot<1 Or slot>#NEON_SERVICE_MAX_SPRITES Or path=0 Or encodedCapacity<1 : NeonServiceExtensionStatus(#NEON_PNG_ERR_ARGUMENT) : ProcedureReturn 0 : EndIf
  If encodedCapacity>#NEON_PNG_MAX_SOURCE : encodedCapacity=#NEON_PNG_MAX_SOURCE : EndIf
  bytes=AnvilFileReadWhole(path,encoded,encodedCapacity)
  If bytes<0 : NeonServiceExtensionStatus(bytes) : ProcedureReturn 0 : EndIf
  ProcedureReturn NeonServiceSpriteLoadPNGMemory(slot,encoded,bytes,rgba,capacity,colourKey,mask,maskCapacity,scratch,scratchCapacity)
EndProcedure

; SPDX-License-Identifier: MIT
; Create outside the frame; resident upload copies caller-owned rope pixels.
; Include the HAL, base service client and sprite client before this header.
XIncludeFile "Anvil/Graphics/neon_sprite_rope.pbi"
Procedure.i NeonServiceSpriteCreateRope(slot.i,rgba.i,capacity.i,mask.i,maskCapacity.i)
  Protected info.NeonSpriteAssetInfo,rc.i
  If slot<1 Or slot>#NEON_SERVICE_MAX_SPRITES
    NeonServiceExtensionStatus(#NEON_ASSET_ERR_ARGUMENT) : ProcedureReturn 0
  EndIf
  rc=NeonSpriteCreateRope(@info,rgba,capacity,mask,maskCapacity)
  If rc<>0 : NeonServiceExtensionStatus(rc) : ProcedureReturn 0 : EndIf
  ProcedureReturn NeonServiceSpriteUpload(slot,rgba,#NEON_ROPE_RGBA_BYTES,info\width,info\height,0)
EndProcedure

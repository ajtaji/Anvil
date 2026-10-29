; SPDX-License-Identifier: MIT
; The engine's fixed 32x64 procedural rope, in caller-owned straight RGBA8.
; No allocator, file, service, renderer or device dependency. Optional mask
; is one byte per opaque pixel. Metadata and output publish after preflight.
XIncludeFile "Anvil/Graphics/neon_sprite_decode.pbi"
#NEON_ROPE_WIDTH = 32
#NEON_ROPE_HEIGHT = 64
#NEON_ROPE_RGBA_BYTES = 8192
#NEON_ROPE_MASK_BYTES = 2048

Procedure.i NeonSpriteCreateRope(*info.NeonSpriteAssetInfo,rgba.i,capacity.i,mask.i,maskCapacity.i)
  Protected x.i,y.i,p.i,red.i,green.i,blue.i
  If *info=0 Or (*info & 7)<>0 Or rgba=0
    ProcedureReturn #NEON_ASSET_ERR_ARGUMENT
  EndIf
  If capacity<#NEON_ROPE_RGBA_BYTES Or (mask<>0 And maskCapacity<#NEON_ROPE_MASK_BYTES)
    ProcedureReturn #NEON_ASSET_ERR_CAPACITY
  EndIf
  If NeonSpriteAssetSpan(*info,16)=0 Or NeonSpriteAssetSpan(rgba,#NEON_ROPE_RGBA_BYTES)=0 Or (mask<>0 And NeonSpriteAssetSpan(mask,#NEON_ROPE_MASK_BYTES)=0)
    ProcedureReturn #NEON_ASSET_ERR_ARGUMENT
  EndIf
  If (*info<rgba+#NEON_ROPE_RGBA_BYTES And rgba<*info+16) Or (mask<>0 And *info<mask+#NEON_ROPE_MASK_BYTES And mask<*info+16)
    ProcedureReturn #NEON_ASSET_ERR_ARGUMENT
  EndIf
  If mask<>0 And mask<rgba+#NEON_ROPE_RGBA_BYTES And rgba<mask+#NEON_ROPE_MASK_BYTES
    ProcedureReturn #NEON_ASSET_ERR_ARGUMENT
  EndIf
  For y=0 To #NEON_ROPE_HEIGHT-1
    For x=0 To #NEON_ROPE_WIDTH-1
      red=180 : green=120 : blue=0
      If x>=8 And x<24 : red=255 : green=210 : blue=50 : EndIf
      If x<3 Or x>=29 : red=80 : green=50 : blue=0 : EndIf
      If (y % 8)<2
        ; Source-over ridge (100,60,0,150) onto an opaque base. Round to
        ; nearest byte; alpha stays255. The final desktop ridge at y64
        ; is clipped by its 64-row image and creates no extra row here.
        red=(red*105+100*150+127)/255
        green=(green*105+60*150+127)/255
        blue=(blue*105+127)/255
      EndIf
      p=y*#NEON_ROPE_WIDTH+x
      PokeA(rgba+p*4,red) : PokeA(rgba+p*4+1,green)
      PokeA(rgba+p*4+2,blue) : PokeA(rgba+p*4+3,255)
      If mask<>0 : PokeA(mask+p,1) : EndIf
    Next
  Next
  *info\width=#NEON_ROPE_WIDTH : *info\height=#NEON_ROPE_HEIGHT
  ProcedureReturn 0
EndProcedure

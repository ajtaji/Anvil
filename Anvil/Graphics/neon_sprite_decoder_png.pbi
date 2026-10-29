; SPDX-License-Identifier: MIT
; Optional PNG/BMP automatic selection for unchanged legacy asset signatures.
; Include the existing Core/crc.pbi and #CRC_POLY contract before this header.
; Scratch stays caller-owned and valid until reset or replacement. Serialize
; installation and decoding. No allocator, file access or GPU owner lives here.
XIncludeFile "Anvil/Graphics/neon_sprite_decoder.pbi"
XIncludeFile "Anvil/Graphics/neon_png_decode.pbi"
Global nsdpScratch.i,nsdpCapacity.i
Procedure.i nsdpDecode(info.i,encoded.i,encodedBytes.i,rgba.i,rgbaCapacity.i,colourKey.i,mask.i,maskCapacity.i)
  ; Inspect only a representable nonempty span. PNG validates the full signature
  ; and container; BMP retains its established errors and limits.
  If encodedBytes>0 And NeonSpriteAssetSpan(encoded,encodedBytes)<>0
    If (PeekA(encoded) & 255)=137
      ProcedureReturn NeonPngDecode(info,encoded,encodedBytes,rgba,rgbaCapacity,colourKey,mask,maskCapacity,nsdpScratch,nsdpCapacity)
    EndIf
  EndIf
  ProcedureReturn NeonSpriteDecodeMemory(info,encoded,encodedBytes,rgba,rgbaCapacity,colourKey,mask,maskCapacity)
EndProcedure
Procedure.i NeonSpriteDecoderPngInstall(scratch.i,capacity.i)
  Protected rc.i
  If NeonSpriteDecoderBusy()<>0 : ProcedureReturn #NEON_ASSET_ERR_BUSY : EndIf
  If scratch<=0 Or (scratch & 7)<>0 Or capacity<8192 Or NeonSpriteAssetSpan(scratch,capacity)=0 : ProcedureReturn #NEON_ASSET_ERR_ARGUMENT : EndIf
  rc=NeonSpriteDecoderInstall(@nsdpDecode,#NEON_PNG_MAX_SOURCE)
  If rc<>0 : ProcedureReturn rc : EndIf
  nsdpScratch=scratch : nsdpCapacity=capacity : ProcedureReturn 0
EndProcedure
Procedure.i NeonSpriteDecoderPngReset()
  Protected rc.i=NeonSpriteDecoderReset()
  If rc=0 : nsdpScratch=0 : nsdpCapacity=0 : EndIf
  ProcedureReturn rc
EndProcedure

; SPDX-License-Identifier: MIT
; Pure bounded sprite decoding. No driver, service table, file or GPU owner.
; Uncompressed Windows BMP24/32 only; PNG/JPEG require their own decoder.
; BMP32 BI_RGB byte four is straight alpha. Output info publishes on success.
#NEON_ASSET_MAX_DIM = 1024
#NEON_ASSET_MAX_BYTES = 4194432
#NEON_ASSET_ERR_ARGUMENT = -21320
#NEON_ASSET_ERR_FORMAT = -21321
#NEON_ASSET_ERR_TRUNCATED = -21322
#NEON_ASSET_ERR_CAPACITY = -21323
#NEON_ASSET_ERR_IO = -21324

Structure NeonSpriteAssetInfo Align #PB_Structure_AlignC
  width.i : height.i
EndStructure

; Exclusive range ends must be representable before overlap arithmetic.
Procedure.i NeonSpriteAssetSpan(pointer.i,bytes.i)
  If pointer<1 Or bytes<1 Or pointer>$7FFFFFFFFFFFFFFF-bytes : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

; BMP fields are not naturally aligned (file size starts at byte 2).
; Bare-metal Device memory faults on unaligned word loads.
Procedure.i nasAssetU16(*source)
  ProcedureReturn (PeekA(*source) & 255) | ((PeekA(*source + 1) & 255) << 8)
EndProcedure

Procedure.i nasAssetU32(*source)
  ProcedureReturn (PeekA(*source) & 255) | ((PeekA(*source + 1) & 255) << 8) | ((PeekA(*source + 2) & 255) << 16) | ((PeekA(*source + 3) & 255) << 24)
EndProcedure

; colourKey has PureBasic RGB() layout: $00BBGGRR; -1 disables it. Keyed
; pixels become transparent black. Non-key pixels retain straight alpha.
; A supplied mask receives one byte per pixel: 1 for alpha > 0, else 0.
Procedure.i NeonSpriteDecodeRGBA(*info.NeonSpriteAssetInfo, *source, sourceBytes.i, width.i, height.i, *rgba, rgbaCapacity.i, colourKey.i, *mask, maskCapacity.i)
  Protected pixels.i, bytes.i, i.i, sourceOffset.i, targetOffset.i
  Protected red.i, green.i, blue.i, alpha.i, key.i
  If *info = 0 Or (*info & 7)<>0 Or *source = 0 Or *rgba = 0 Or width < 1 Or height < 1 Or width > #NEON_ASSET_MAX_DIM Or height > #NEON_ASSET_MAX_DIM
    ProcedureReturn #NEON_ASSET_ERR_ARGUMENT
  EndIf
  pixels = width * height : bytes = pixels * 4
  If sourceBytes < bytes Or rgbaCapacity < bytes Or (*mask <> 0 And maskCapacity < pixels)
    ProcedureReturn #NEON_ASSET_ERR_CAPACITY
  EndIf
  If NeonSpriteAssetSpan(*info,16)=0 Or NeonSpriteAssetSpan(*source,bytes)=0 Or NeonSpriteAssetSpan(*rgba,bytes)=0 Or (*mask<>0 And NeonSpriteAssetSpan(*mask,pixels)=0)
    ProcedureReturn #NEON_ASSET_ERR_ARGUMENT
  EndIf
  If (*info < *source+bytes And *source < *info+16) Or (*info < *rgba+bytes And *rgba < *info+16) Or (*mask<>0 And *info < *mask+pixels And *mask < *info+16)
    ProcedureReturn #NEON_ASSET_ERR_ARGUMENT
  EndIf
  If *source <> *rgba And *source < *rgba + bytes And *rgba < *source + bytes
    ProcedureReturn #NEON_ASSET_ERR_ARGUMENT
  EndIf
  If *mask <> 0
    If (*mask < *source + bytes And *source < *mask + pixels) Or (*mask < *rgba + bytes And *rgba < *mask + pixels)
      ProcedureReturn #NEON_ASSET_ERR_ARGUMENT
    EndIf
  EndIf
  For i = 0 To pixels - 1
    sourceOffset = i * 4 : targetOffset = sourceOffset
    red = PeekA(*source + sourceOffset) & 255
    green = PeekA(*source + sourceOffset + 1) & 255
    blue = PeekA(*source + sourceOffset + 2) & 255
    alpha = PeekA(*source + sourceOffset + 3) & 255
    key = red | (green << 8) | (blue << 16)
    If colourKey <> -1 And key = colourKey
      red = 0 : green = 0 : blue = 0 : alpha = 0
    EndIf
    PokeA(*rgba + targetOffset, red)
    PokeA(*rgba + targetOffset + 1, green)
    PokeA(*rgba + targetOffset + 2, blue)
    PokeA(*rgba + targetOffset + 3, alpha)
    If *mask <> 0
      If alpha > 0 : PokeA(*mask + i, 1) : Else : PokeA(*mask + i, 0) : EndIf
    EndIf
  Next
  *info\width=width : *info\height=height
  ProcedureReturn 0
EndProcedure

; Decode a bounded BMP into top-down, tightly packed RGBA, then publish the
; metadata only after the complete decode succeeds.
Procedure.i NeonSpriteDecodeMemory(*info.NeonSpriteAssetInfo, *encoded, encodedBytes.i, *rgba, rgbaCapacity.i, colourKey.i, *mask, maskCapacity.i)
  Protected offset.i, dib.i, width.i, signedHeight.i, height.i, topDown.i
  Protected planes.i, depth.i, compression.i, rowBytes.i, required.i, pixels.i
  Protected x.i, y.i, sourceRow.i, sourcePixel.i, targetPixel.i, alpha.i
  If *info = 0 Or (*info & 7)<>0 Or *encoded = 0 Or *rgba = 0 Or encodedBytes < 0
    ProcedureReturn #NEON_ASSET_ERR_ARGUMENT
  EndIf
  If NeonSpriteAssetSpan(*info,16)=0 Or (encodedBytes>0 And NeonSpriteAssetSpan(*encoded,encodedBytes)=0) : ProcedureReturn #NEON_ASSET_ERR_ARGUMENT : EndIf
  If encodedBytes < 2 : ProcedureReturn #NEON_ASSET_ERR_TRUNCATED : EndIf
  If (PeekA(*encoded) & 255) <> 66 Or (PeekA(*encoded + 1) & 255) <> 77
    ProcedureReturn #NEON_ASSET_ERR_FORMAT
  EndIf
  If encodedBytes < 54 : ProcedureReturn #NEON_ASSET_ERR_TRUNCATED : EndIf
  If encodedBytes > #NEON_ASSET_MAX_BYTES
    ProcedureReturn #NEON_ASSET_ERR_CAPACITY
  EndIf
  offset = nasAssetU32(*encoded + 10) & $FFFFFFFF
  dib = nasAssetU32(*encoded + 14) & $FFFFFFFF
  width = nasAssetU32(*encoded + 18) & $FFFFFFFF
  signedHeight = nasAssetU32(*encoded + 22) & $FFFFFFFF
  planes = nasAssetU16(*encoded + 26)
  depth = nasAssetU16(*encoded + 28)
  compression = nasAssetU32(*encoded + 30) & $FFFFFFFF
  If dib <> 40 Or planes <> 1 Or (depth <> 24 And depth <> 32) Or compression <> 0
    ProcedureReturn #NEON_ASSET_ERR_FORMAT
  EndIf
  If width < 1 Or width > #NEON_ASSET_MAX_DIM Or signedHeight = 0 Or signedHeight = $80000000 Or offset < 54
    ProcedureReturn #NEON_ASSET_ERR_FORMAT
  EndIf
  topDown = 0 : height = signedHeight
  If signedHeight > $7FFFFFFF
    height = $100000000 - signedHeight : topDown = 1
  EndIf
  If height < 1 Or height > #NEON_ASSET_MAX_DIM
    ProcedureReturn #NEON_ASSET_ERR_FORMAT
  EndIf
  rowBytes = ((width * (depth / 8)) + 3) & $FFFFFFFC
  required = offset + rowBytes * height
  pixels = width * height
  If required > encodedBytes : ProcedureReturn #NEON_ASSET_ERR_TRUNCATED : EndIf
  If rgbaCapacity < pixels * 4 Or (*mask <> 0 And maskCapacity < pixels)
    ProcedureReturn #NEON_ASSET_ERR_CAPACITY
  EndIf
  If NeonSpriteAssetSpan(*rgba,pixels*4)=0 Or (*mask<>0 And NeonSpriteAssetSpan(*mask,pixels)=0) : ProcedureReturn #NEON_ASSET_ERR_ARGUMENT : EndIf
  If (*info < *encoded+encodedBytes And *encoded < *info+16) Or (*info < *rgba+pixels*4 And *rgba < *info+16) Or (*mask<>0 And *info < *mask+pixels And *mask < *info+16)
    ProcedureReturn #NEON_ASSET_ERR_ARGUMENT
  EndIf
  If *mask <> 0 And *mask < *rgba + pixels * 4 And *rgba < *mask + pixels
    ProcedureReturn #NEON_ASSET_ERR_ARGUMENT
  EndIf
  If *encoded < *rgba + pixels * 4 And *rgba < *encoded + encodedBytes
    ProcedureReturn #NEON_ASSET_ERR_ARGUMENT
  EndIf
  If *mask <> 0 And *mask < *encoded + encodedBytes And *encoded < *mask + pixels
    ProcedureReturn #NEON_ASSET_ERR_ARGUMENT
  EndIf
  For y = 0 To height - 1
    sourceRow = y
    If topDown = 0 : sourceRow = height - 1 - y : EndIf
    For x = 0 To width - 1
      sourcePixel = offset + sourceRow * rowBytes + x * (depth / 8)
      targetPixel = (y * width + x) * 4
      PokeA(*rgba + targetPixel, PeekA(*encoded + sourcePixel + 2) & 255)
      PokeA(*rgba + targetPixel + 1, PeekA(*encoded + sourcePixel + 1) & 255)
      PokeA(*rgba + targetPixel + 2, PeekA(*encoded + sourcePixel) & 255)
      alpha = 255
      If depth = 32 : alpha = PeekA(*encoded + sourcePixel + 3) & 255 : EndIf
      PokeA(*rgba + targetPixel + 3, alpha)
    Next
  Next
  ProcedureReturn NeonSpriteDecodeRGBA(*info, *rgba, pixels * 4, width, height, *rgba, rgbaCapacity, colourKey, *mask, maskCapacity)
EndProcedure

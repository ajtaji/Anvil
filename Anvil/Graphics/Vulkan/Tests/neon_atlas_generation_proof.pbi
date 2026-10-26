Global Dim atlasProofFont.a[1520]
Global Dim atlasProofMemory.i[#ANVIL_VK_MAX_MEMORY + 1]

Procedure.i atlasProofLiveMemory()
  Define i.i, count.i
  For i = 1 To #ANVIL_VK_MAX_MEMORY
    If avkMemLive[i] <> 0 : count = count + 1 : EndIf
  Next
  ProcedureReturn count
EndProcedure

Procedure.i atlasTransactionProof(imageBase.i, imagePitch.i)
  Define alloc.VkMemoryAllocateInfo
  Define oldImage.i, oldMemory.i, oldView.i, oldSet.i, oldGeneration.i
  Define oldFont.i = neon_fbits, oldW.i = neon_fw, oldH.i = neon_fh, oldFirst.i = neon_ffirst, oldLast.i = neon_flast
  Define base.i, bytes.i, i.i, j.i, rc.i, failure.i, freeRows.i, held.i, initialLive.i, changes.i, swaps.i
  Define sprite.i = $FF00FF00
  Define x.i, y.i, px.i, py.i
  rc = NeonVkChromeImageSpriteReplaceBGRAId(16, @sprite, 1, 1)
  If rc <> 0 : ProcedureReturn 180 : EndIf
  initialLive = atlasProofLiveMemory()
  oldImage = nvcAtlasImage : oldMemory = nvcAtlasMemory : oldView = nvcAtlasView : oldSet = nvcDescriptorSet
  oldGeneration = nvcAtlasGeneration
  base = AnvilVkImageAddress(oldImage) : bytes = AnvilVkImageSize(oldImage)
  If base = 0 Or bytes < 1 Or bytes > $400000 : ProcedureReturn 181 : EndIf
  For i = 0 To bytes - 4 Step 4 : PokeL($E2000000 + i, PeekL(base + i)) : Next
  For i = 0 To 1519 : atlasProofFont[i] = PeekA(oldFont + i) : Next
  For i = (65 - 32) * 16 To (65 - 32) * 16 + 15 : atlasProofFont[i] = atlasProofFont[i] ! $FF : Next
  For i = 0 To 15
    PokeA($E1C01800 + i, PeekA(oldFont + (65 - 32) * 16 + i))
    PokeA($E1C01810 + i, atlasProofFont[(65 - 32) * 16 + i])
  Next
  For i = 1 To #ANVIL_VK_MAX_MEMORY
    If avkMemLive[i] = 0 : freeRows = freeRows + 1 : EndIf
  Next
  alloc\sType = #VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO
  alloc\allocationSize = 64 : alloc\memoryTypeIndex = 0
  For i = 0 To freeRows - 1
    rc = vkAllocateMemory(nvcDevice, @alloc, 0, @atlasProofMemory[i])
    If rc <> 0 : failure = 182 : Break : EndIf
    held = held + 1
  Next
  If failure = 0
    rc = NeonFontUse(@atlasProofFont[0], 8, 16, 32, 126)
    If rc <> 0 : failure = 183 : EndIf
  EndIf
  If failure = 0
    rc = NeonVkChromeBegin(@nwClear[0])
    PokeI($E1C01008, rc)
    If rc = 0 : NeonVkChromeAbort() : failure = 191 : EndIf
    If rc <> #NEON_VK_CHROME_ERR_CAPACITY And failure = 0 : failure = 184 : EndIf
    If nvcAtlasImage <> oldImage Or nvcAtlasMemory <> oldMemory Or nvcAtlasView <> oldView Or nvcDescriptorSet <> oldSet Or nvcAtlasGeneration <> oldGeneration Or nvcAtlasFaulted <> 0
      If failure = 0 : failure = 185 : EndIf
    EndIf
    For i = 0 To bytes - 4 Step 4
      If PeekL($E2000000 + i) <> PeekL(base + i) : changes = changes + 1 : EndIf
    Next
    PokeI($E1C01010, changes)
    If changes <> 0 And failure = 0 : failure = 186 : EndIf
  EndIf
  For i = 0 To held - 1 : vkFreeMemory(nvcDevice, atlasProofMemory[i], 0) : atlasProofMemory[i] = 0 : Next
  If failure = 0 And atlasProofLiveMemory() <> initialLive : failure = 187 : EndIf
  If failure = 0
    For j = 0 To 2
      If j = 1
        rc = NeonFontUse(oldFont, oldW, oldH, oldFirst, oldLast)
      Else
        rc = NeonFontUse(@atlasProofFont[0], 8, 16, 32, 126)
      EndIf
      oldImage = nvcAtlasImage : oldSet = nvcDescriptorSet
      If rc = 0 : rc = NeonVkChromeBegin(@nwClear[0]) : EndIf
      If rc <> 0 : failure = 188 : Break : EndIf
      If nvcAtlasImage = oldImage Or nvcDescriptorSet = oldSet Or nvcAtlasGeneration <> Neon_AtlasRasterGeneration()
        failure = 189 : NeonVkChromeAbort() : Break
      EndIf
      NeonFontSetup(#NEON_FONT_UI, 1, 0)
      rc = Neon_Box(0, 0, 8, 8, Neon_RGBA(255, 255, 255, 255))
      If rc = 0 : rc = Neon_TextTex(Neon_FontUI(), 8, 8, "A", Neon_RGBA(255, 255, 255, 255)) : EndIf
      If rc = 0 : rc = NeonVkChromeImageSpriteDrawId(16, 32, 8, 0, 0, 1, 1, 8, 8, Neon_RGBA(255, 255, 255, 255)) : EndIf
      If rc = 0 : rc = NeonVkChromeEnd() : Else : NeonVkChromeAbort() : EndIf
      If rc <> 0 : failure = 190 : Break : EndIf
      If NeonVkChromePresentConsume() <> 1 : failure = 192 : Break : EndIf
      If atlasProofLiveMemory() <> initialLive : failure = 193 : Break : EndIf
      ; Observe completed GPU pixels in logical order; no CPU rasterization.
      For y = 0 To 63
        For x = 0 To 63
          If nvcRotation = 90
            px = nvcLogicalH - 1 - y : py = x
          ElseIf nvcRotation = 180
            px = nvcLogicalW - 1 - x : py = nvcLogicalH - 1 - y
          ElseIf nvcRotation = 270
            px = y : py = nvcLogicalW - 1 - x
          Else
            px = x : py = y
          EndIf
          PokeL($E2400000 + j * 16384 + (y * 64 + x) * 4, PeekL(imageBase + py * imagePitch + px * 4))
        Next
      Next
      swaps = swaps + 1
    Next
  EndIf
  rc = NeonFontUse(oldFont, oldW, oldH, oldFirst, oldLast)
  PokeI($E1C01018, swaps) : PokeI($E1C01020, initialLive) : PokeI($E1C01028, atlasProofLiveMemory())
  PokeI($E1C01030, held) : PokeI($E1C01038, bytes)
  ProcedureReturn failure
EndProcedure

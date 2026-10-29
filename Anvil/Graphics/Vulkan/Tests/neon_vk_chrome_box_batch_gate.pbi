; Emitted gate for the exact production box/span procedures. The draw spy
; records ordering and capacity without touching a Vulkan object or MMIO.
XIncludeFile "Anvil/Graphics/Vulkan/vk_core_1_0.pbi"
XIncludeFile "Anvil/Graphics/neon_colour.pbi"
#NEON_VK_CHROME_OK = 0
#NEON_VK_CHROME_ERR_STATE = -21202
#NEON_VK_CHROME_ERR_CAPACITY = -21203
#NVC_PATH_NONE = 0
#NEON_MAX_DRAWS=4096
#NEON_MAX_VERTS=262144
#NEON_MAX_TDRAWS=2048
#NEON_MAX_TVERTS=98304

Global nvcInFrame.i
Global nvcGridBatchActive.i
Global nvcPathKind.i
Global nvcMaxQuads.i
Global nvcMaxVertexQuads.i
Global nvcVertices.i
Global nvcDrawCount.i
Global nvcError.i
Global nvcBoxBatchActive.i
Global nvcBoxBatchFirst.i
Global nvcBoxBatchCount.i
Global nvcBoxBatchColour.i
Global nvcBoxBatchClipX.i
Global nvcBoxBatchClipY.i
Global nvcBoxBatchClipW.i
Global nvcBoxBatchClipH.i
Global nvcClipX.i
Global nvcClipY.i
Global nvcClipW.i
Global nvcClipH.i
Global nvcWhiteU0.i
Global nvcWhiteV0.i
Global nvcWhiteU1.i
Global nvcWhiteV1.i
Global nbgFirst.i
Global nbgCount.i
Global nbgColour.i
Global nbgLastX.i
Global nbgQuadCalls.i
Global nbgLastW.i,nbgLastH.i
Global nvcFlatDraws.i,nvcFlatVertices.i,nvcTexDraws.i,nvcTexVertices.i
Global nvcBoxes.i,nvcClipped.i,nvcRotation.i,nvcLogicalW.i,nvcLogicalH.i

Procedure.i nvcFail(code.i)
  nvcError = code
  ProcedureReturn code
EndProcedure

Procedure nvcQuad(index.i, x0.i, y0.i, x1.i, y1.i, u0.i, v0.i, u1.i, v1.i)
  nbgQuadCalls = nbgQuadCalls + 1
  nbgLastX = x0
  nbgLastW = x1-x0 : nbgLastH = y1-y0
EndProcedure

Procedure.i nvcDraw(first.i, count.i, colour.i)
  If nvcDrawCount >= nvcMaxQuads : ProcedureReturn nvcFail(#NEON_VK_CHROME_ERR_CAPACITY) : EndIf
  nbgFirst = first : nbgCount = count : nbgColour = colour
  nvcDrawCount = nvcDrawCount + 1
  nvcFlatDraws = nvcFlatDraws + 1
  ProcedureReturn #NEON_VK_CHROME_OK
EndProcedure

; @PRODUCTION_BOX_BATCH@

Procedure.i Main()
  Protected i.i
  nvcInFrame = 1 : nvcMaxQuads = 4096 : nvcMaxVertexQuads = 4096
  nvcClipW = 64 : nvcClipH = 64
  nvcLogicalW=64 : nvcLogicalH=64
  If NeonVkChromeBoxBatchBegin() <> #NEON_VK_CHROME_OK : ProcedureReturn 1 : EndIf
  For i = 0 To 3504
    If NeonVkChromeBox(i & 63, (i >> 6) & 63, 1, 1, $FF2846A0) <> #NEON_VK_CHROME_OK : ProcedureReturn 2 : EndIf
  Next
  If nvcDrawCount <> 0 Or nvcVertices <> 21030 Or nbgQuadCalls <> 3505 : ProcedureReturn 3 : EndIf
  If NeonVkChromeBoxBatchEnd() <> #NEON_VK_CHROME_OK : ProcedureReturn 4 : EndIf
  If nvcDrawCount <> 1 Or nbgFirst <> 0 Or nbgCount <> 21030 Or nbgColour <> $FF2846A0 : ProcedureReturn 5 : EndIf
  If NeonVkChromeBoxBatchEnd() <> #NEON_VK_CHROME_ERR_STATE : ProcedureReturn 6 : EndIf

  ; A tint mismatch refuses before a vertex or draw cursor advances.
  If NeonVkChromeBoxBatchBegin() <> #NEON_VK_CHROME_OK : ProcedureReturn 7 : EndIf
  If NeonVkChromeBox(1, 2, 1, 1, $FF010203) <> #NEON_VK_CHROME_OK : ProcedureReturn 8 : EndIf
  If NeonVkChromeBox(3, 4, 1, 1, $FF040506) <> #NEON_VK_CHROME_ERR_STATE : ProcedureReturn 9 : EndIf
  If nvcVertices <> 21036 Or nvcDrawCount <> 1 : ProcedureReturn 10 : EndIf
  If NeonVkChromeBoxBatchEnd() <> #NEON_VK_CHROME_OK : ProcedureReturn 11 : EndIf
  If nvcDrawCount <> 2 Or nbgFirst <> 21030 Or nbgCount <> 6 : ProcedureReturn 12 : EndIf

  ; Both the draw slot and vertex capacity are preflighted.
  nvcMaxVertexQuads = 3507
  If NeonVkChromeBoxBatchBegin() <> #NEON_VK_CHROME_OK : ProcedureReturn 13 : EndIf
  If NeonVkChromeBox(7, 8, 1, 1, $FF112233) <> #NEON_VK_CHROME_OK : ProcedureReturn 14 : EndIf
  If NeonVkChromeBox(9, 10, 1, 1, $FF112233) <> #NEON_VK_CHROME_ERR_CAPACITY : ProcedureReturn 15 : EndIf
  If nvcVertices <> 21042 Or nvcDrawCount <> 2 : ProcedureReturn 16 : EndIf
  If NeonVkChromeBoxBatchEnd() <> #NEON_VK_CHROME_OK : ProcedureReturn 17 : EndIf
  If nvcDrawCount <> 3 Or nbgCount <> 6 : ProcedureReturn 18 : EndIf
  nvcMaxQuads = 3
  If NeonVkChromeBoxBatchBegin() <> #NEON_VK_CHROME_ERR_CAPACITY : ProcedureReturn 19 : EndIf
  ; Logical budget refusal precedes any physical cursor or copied span write.
  nvcMaxQuads=4096 : nvcMaxVertexQuads=4096 : nvcFlatVertices=#NEON_MAX_VERTS
  If NeonVkChromeBoxBatchBegin() <> #NEON_VK_CHROME_OK : ProcedureReturn 20 : EndIf
  If NeonVkChromeBox(1,1,1,1,$FFFFFFFF) <> #NEON_VK_CHROME_ERR_CAPACITY : ProcedureReturn 21 : EndIf
  If nvcVertices<>21042 Or nbgQuadCalls<>3507 Or nvcDrawCount<>3 : ProcedureReturn 22 : EndIf
  If NeonVkChromeBoxBatchEnd() <> #NEON_VK_CHROME_OK : ProcedureReturn 23 : EndIf
  ; Complete and partial visibility use the production logical clip helpers.
  nvcFlatVertices=0
  If NeonVkChromeBox(64,0,10,10,$FFFFFFFF) <> 0 Or nvcVertices<>21042 : ProcedureReturn 24 : EndIf
  If NeonVkChromeBox(-2,0,4,2,$FFFFFFFF) <> 0 Or nvcVertices<>21048 : ProcedureReturn 25 : EndIf
  If nbgLastX<>0 Or nbgLastW<>2 Or nbgLastH<>2 Or nbgQuadCalls<>3508 : ProcedureReturn 26 : EndIf
  If NeonVkChromeBox(1,1,1,1,0) <> 0 : ProcedureReturn 27 : EndIf
  If nvcVertices<>21048 Or nvcDrawCount<>4 Or nbgQuadCalls<>3508 : ProcedureReturn 28 : EndIf
  ProcedureReturn 0
EndProcedure

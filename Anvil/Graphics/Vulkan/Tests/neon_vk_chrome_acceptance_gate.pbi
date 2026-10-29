; Independent emitted oracle for the Neon-to-Vulkan chrome adapter contract.
; This fixture owns no adapter code and touches no MMIO. The host checker also
; applies this oracle to hostile traces and inspects the production adapter.

#NVC_OK = 0
#NVC_ERR_OVERFLOW = 17
#NVC_MAX_DRAWS = 4096

#NVC_DRAW_BOX = 1
#NVC_DRAW_GLYPH = 2

; Atlas texel coordinates. Boxes sample the dedicated opaque-white texel.
#NVC_WHITE_X0 = 0
#NVC_WHITE_Y0 = 0
#NVC_WHITE_X1 = 1
#NVC_WHITE_Y1 = 1

; Exact Neon 16x1024 atlas UV words for ASCII 'A' (glyph 33, cell 8,256).
#NVC_A_UL = $3F000000
#NVC_A_UR = $3F800000
#NVC_A_VT = $3E800000
#NVC_A_VB = $3E880000

Structure NvcResourceSet
  device.i
  queue.i
  image.i
  vertex.i
  atlas.i
  descriptor.i
  pipeline.i
  command.i
  fence.i
EndStructure

Structure NvcDraw
  serial.i
  kind.i
  firstVertex.i
  vertexCount.i
  u0.i
  v0.i
  u1.i
  v1.i
  scissorX.i
  scissorY.i
  scissorW.i
  scissorH.i
  scissorGeneration.i
EndStructure

Global nvcFrame1.NvcResourceSet
Global nvcFrame2.NvcResourceSet
Global Dim nvcDraw.NvcDraw[3]
Global nvcCreateCount.i
Global nvcDestroyCount.i
Global nvcSubmitCount.i
Global nvcPresentCount.i
Global nvcOverflowResult.i
Global nvcOverflowDrawsBefore.i
Global nvcOverflowDrawsAfter.i
Global nvcOverflowSubmitDelta.i
Global nvcOverflowPresentDelta.i
Global nvcOverflowResource.i

Procedure NvcSeedResources(*r.NvcResourceSet)
  *r\device = $101
  *r\queue = $102
  *r\image = $103
  *r\vertex = $104
  *r\atlas = $105
  *r\descriptor = $106
  *r\pipeline = $107
  *r\command = $108
  *r\fence = $109
EndProcedure

Procedure.i NvcSameResources(*a.NvcResourceSet, *b.NvcResourceSet)
  ProcedureReturn Bool(*a\device = *b\device And *a\queue = *b\queue And *a\image = *b\image And *a\vertex = *b\vertex And *a\atlas = *b\atlas And *a\descriptor = *b\descriptor And *a\pipeline = *b\pipeline And *a\command = *b\command And *a\fence = *b\fence)
EndProcedure

Procedure NvcSeedTrace()
  NvcSeedResources(@nvcFrame1)
  NvcSeedResources(@nvcFrame2)
  nvcCreateCount = 1
  nvcDestroyCount = 1

  nvcDraw[0]\serial = 0 : nvcDraw[0]\kind = #NVC_DRAW_BOX
  nvcDraw[0]\firstVertex = 0 : nvcDraw[0]\vertexCount = 6
  nvcDraw[0]\u0 = #NVC_WHITE_X0 : nvcDraw[0]\v0 = #NVC_WHITE_Y0
  nvcDraw[0]\u1 = #NVC_WHITE_X1 : nvcDraw[0]\v1 = #NVC_WHITE_Y1
  nvcDraw[0]\scissorX = 0 : nvcDraw[0]\scissorY = 0
  nvcDraw[0]\scissorW = 800 : nvcDraw[0]\scissorH = 1280
  nvcDraw[0]\scissorGeneration = 1

  nvcDraw[1]\serial = 1 : nvcDraw[1]\kind = #NVC_DRAW_GLYPH
  nvcDraw[1]\firstVertex = 6 : nvcDraw[1]\vertexCount = 6
  nvcDraw[1]\u0 = #NVC_A_UL : nvcDraw[1]\v0 = #NVC_A_VT
  nvcDraw[1]\u1 = #NVC_A_UR : nvcDraw[1]\v1 = #NVC_A_VB
  nvcDraw[1]\scissorX = 20 : nvcDraw[1]\scissorY = 40
  nvcDraw[1]\scissorW = 300 : nvcDraw[1]\scissorH = 80
  nvcDraw[1]\scissorGeneration = 2

  nvcDraw[2]\serial = 2 : nvcDraw[2]\kind = #NVC_DRAW_BOX
  nvcDraw[2]\firstVertex = 12 : nvcDraw[2]\vertexCount = 6
  nvcDraw[2]\u0 = #NVC_WHITE_X0 : nvcDraw[2]\v0 = #NVC_WHITE_Y0
  nvcDraw[2]\u1 = #NVC_WHITE_X1 : nvcDraw[2]\v1 = #NVC_WHITE_Y1
  nvcDraw[2]\scissorX = 500 : nvcDraw[2]\scissorY = 600
  nvcDraw[2]\scissorW = 100 : nvcDraw[2]\scissorH = 120
  nvcDraw[2]\scissorGeneration = 3

  nvcSubmitCount = 1
  nvcPresentCount = 1

  nvcOverflowResult = #NVC_ERR_OVERFLOW
  nvcOverflowDrawsBefore = #NVC_MAX_DRAWS
  nvcOverflowDrawsAfter = #NVC_MAX_DRAWS
  nvcOverflowSubmitDelta = 0
  nvcOverflowPresentDelta = 0
  nvcOverflowResource = nvcFrame1\pipeline
EndProcedure

Procedure.i Main()
  NvcSeedTrace()

  ; Persistent allocation: one create owns both frames and one destroy retires it.
  If nvcCreateCount <> 1 : ProcedureReturn 1 : EndIf
  If nvcDestroyCount <> 1 : ProcedureReturn 2 : EndIf
  If NvcSameResources(@nvcFrame1, @nvcFrame2) = 0 : ProcedureReturn 3 : EndIf
  If nvcFrame1\device = 0 Or nvcFrame1\queue = 0 Or nvcFrame1\image = 0 : ProcedureReturn 4 : EndIf
  If nvcFrame1\vertex = 0 Or nvcFrame1\atlas = 0 Or nvcFrame1\descriptor = 0 : ProcedureReturn 5 : EndIf
  If nvcFrame1\pipeline = 0 Or nvcFrame1\command = 0 Or nvcFrame1\fence = 0 : ProcedureReturn 6 : EndIf

  ; Immutable ordered records: six vertices each, contiguous and never resorted.
  If nvcDraw[0]\serial <> 0 Or nvcDraw[1]\serial <> 1 Or nvcDraw[2]\serial <> 2 : ProcedureReturn 7 : EndIf
  If nvcDraw[0]\firstVertex <> 0 Or nvcDraw[1]\firstVertex <> 6 Or nvcDraw[2]\firstVertex <> 12 : ProcedureReturn 8 : EndIf
  If nvcDraw[0]\vertexCount <> 6 Or nvcDraw[1]\vertexCount <> 6 Or nvcDraw[2]\vertexCount <> 6 : ProcedureReturn 9 : EndIf

  ; Both boxes sample only the one opaque-white atlas texel.
  If nvcDraw[0]\kind <> #NVC_DRAW_BOX Or nvcDraw[2]\kind <> #NVC_DRAW_BOX : ProcedureReturn 10 : EndIf
  If nvcDraw[0]\u0 <> #NVC_WHITE_X0 Or nvcDraw[0]\v0 <> #NVC_WHITE_Y0 Or nvcDraw[0]\u1 <> #NVC_WHITE_X1 Or nvcDraw[0]\v1 <> #NVC_WHITE_Y1 : ProcedureReturn 11 : EndIf
  If nvcDraw[2]\u0 <> nvcDraw[0]\u0 Or nvcDraw[2]\v0 <> nvcDraw[0]\v0 Or nvcDraw[2]\u1 <> nvcDraw[0]\u1 Or nvcDraw[2]\v1 <> nvcDraw[0]\v1 : ProcedureReturn 12 : EndIf

  ; Text consumes the exact copied Neon glyph UV record, not the white texel.
  If nvcDraw[1]\kind <> #NVC_DRAW_GLYPH : ProcedureReturn 13 : EndIf
  If nvcDraw[1]\u0 <> #NVC_A_UL Or nvcDraw[1]\u1 <> #NVC_A_UR : ProcedureReturn 14 : EndIf
  If nvcDraw[1]\v0 <> #NVC_A_VT Or nvcDraw[1]\v1 <> #NVC_A_VB : ProcedureReturn 15 : EndIf
  If nvcDraw[1]\u0 >= nvcDraw[1]\u1 Or nvcDraw[1]\v0 >= nvcDraw[1]\v1 : ProcedureReturn 16 : EndIf

  ; Each record owns the scissor that was active when it was appended.
  If nvcDraw[0]\scissorGeneration <> 1 Or nvcDraw[1]\scissorGeneration <> 2 Or nvcDraw[2]\scissorGeneration <> 3 : ProcedureReturn 17 : EndIf
  If nvcDraw[1]\scissorX <> 20 Or nvcDraw[1]\scissorY <> 40 Or nvcDraw[1]\scissorW <> 300 Or nvcDraw[1]\scissorH <> 80 : ProcedureReturn 18 : EndIf
  If nvcDraw[2]\scissorX <> 500 Or nvcDraw[2]\scissorY <> 600 Or nvcDraw[2]\scissorW <> 100 Or nvcDraw[2]\scissorH <> 120 : ProcedureReturn 19 : EndIf

  ; A completed frame owns exactly one queue submission and one display DMA present.
  If nvcSubmitCount <> 1 : ProcedureReturn 20 : EndIf
  If nvcPresentCount <> 1 : ProcedureReturn 21 : EndIf

  ; Capacity refusal is failure-atomic: no wrap, submit, present or resource churn.
  If nvcOverflowResult <> #NVC_ERR_OVERFLOW : ProcedureReturn 22 : EndIf
  If nvcOverflowDrawsBefore <> #NVC_MAX_DRAWS : ProcedureReturn 23 : EndIf
  If nvcOverflowDrawsAfter <> nvcOverflowDrawsBefore : ProcedureReturn 24 : EndIf
  If nvcOverflowSubmitDelta <> 0 : ProcedureReturn 25 : EndIf
  If nvcOverflowPresentDelta <> 0 : ProcedureReturn 26 : EndIf
  If nvcOverflowResource <> nvcFrame1\pipeline : ProcedureReturn 27 : EndIf

  ProcedureReturn #NVC_OK
EndProcedure

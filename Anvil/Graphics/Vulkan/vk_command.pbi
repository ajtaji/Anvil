; ======================================================================
;  Vulkan command recording and queue submission -- portable engine
; ======================================================================
; SPDX-License-Identifier: MIT
;
; Target-neutral. It records a command stream, tracks what each command
; buffer assumes and leaves behind for every image it touches, retains
; every resource a submission references until that submission completes,
; and hands one closed draw or transfer job to the backend seam.
;
; Read from the Vulkan specification:
;   .../chapters/cmdbuffers.html      the five command-buffer states and
;                                     the rule that a recording error is
;                                     reported by vkEndCommandBuffer
;   .../chapters/synchronization.html image memory barriers, layout
;                                     transitions, queue-family ownership,
;                                     access and stage scopes
;   .../chapters/clears.html          vkCmdClearColorImage outside a
;                                     render pass: the permitted layouts,
;                                     the required usage, and the fact
;                                     that the clear value's components
;                                     are given in R, G, B, A order
;                                     whatever the image format is
; No implementation source was consulted or translated.
;
; WHAT IS NOT HERE, and is refused with a real code and a sentence:
; secondary execution, blits, dispatches,
; render passes, queries, events, timeline semaphores, memory and buffer
; barriers, multi-range clears, partial-rectangle clears, depth and
; stencil clears, and more than one outstanding submission.

XIncludeFile "Anvil/Graphics/Vulkan/vk_sync.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_semaphore.pbi"

; Ops are drawn from ONE pool rather than reserved per command buffer, so
; running out of them is a real VK_ERROR_OUT_OF_HOST_MEMORY that a test
; can provoke, and so a hundred idle command buffers cost nothing.
#ANVIL_VK_MAX_OPS = 32
#ANVIL_VK_MAX_UPDATE_BYTES = 65536
#ANVIL_VK_MAX_CB_REFS = 2

; One shared pool holds every non-empty vkCmdDraw snapshot recorded by every
; command buffer. 4096 is Neon's real per-frame draw ceiling; making this a
; shared pool preserves that complete capacity without charging each of the 32
; command buffers half a megabyte while it is idle.
#ANVIL_VK_MAX_RECORDED_DRAWS = 4096
#ANVIL_VK_RECORDED_DRAW_BYTES = 240

; Exactly 240 bytes on the AArch64 ABI. Pipeline, descriptor and buffer values
; remain generation-tagged Vulkan handles. They are deliberately not resolved
; to slots or addresses while recording: submission owns that later lifetime
; boundary. Binding count/strides and all other immutable graphics state remain
; pipeline-owned and therefore need not be duplicated in every snapshot.
Structure AnvilVkRecordedDraw Align #PB_Structure_AlignC
  next.i
  kind.i
  pipeline.i
  descriptorSet.i
  firstVertex.i
  vertexCount.i
  indexBuffer.i
  indexOffset.i
  indexType.i
  pushBytes.i
  viewportX.i
  viewportY.i
  viewportW.i
  viewportH.i
  scissorX.i
  scissorY.i
  scissorW.i
  scissorH.i
  vertexBuffer.i[4]
  vertexOffset.i[4]
  pushWord.l[4]
  instanceCount.i
  firstInstance.i
EndStructure

#ANVIL_VK_OP_NONE = 0
#ANVIL_VK_OP_BARRIER = 1
#ANVIL_VK_OP_CLEAR_COLOR = 2
#ANVIL_VK_OP_COPY_BUFFER_IMAGE = 3
#ANVIL_VK_OP_COPY_BUFFER = 4
#ANVIL_VK_OP_FILL_BUFFER = 5
#ANVIL_VK_OP_UPDATE_BUFFER = 6
#ANVIL_VK_OP_BUFFER_BARRIER = 7
#ANVIL_VK_OP_MEMORY_BARRIER = 8
#ANVIL_VK_OP_COPY_IMAGE = 9
#ANVIL_VK_OP_COPY_IMAGE_BUFFER = 10
#ANVIL_VK_BUFFER_TILED_RECT_TAG = 1 ; avkOpDstOffset marker for optimal buffer uploads
#ANVIL_VK_BUFFER_TILED_MICRO_TAG = 2 ; one-utile, byte-bounded optimal buffer upload
#ANVIL_VK_BUFFER_TILED_GRID_TAG = 3 ; at most two adjacent UIF tile rows and columns
#ANVIL_VK_BUFFER_TILED_GRID_4X4_TAG = 4 ; at most four adjacent UIF tile rows and columns

; "the tracker does not know yet" for a layout inside a recording.
#ANVIL_VK_LAYOUT_UNKNOWN = -2
; "this command buffer imposes no entry layout on that image".
#ANVIL_VK_LAYOUT_ANY = -1

Global Dim avkOpLive.a[#ANVIL_VK_MAX_OPS + 1]
Global Dim avkOpNext.i[#ANVIL_VK_MAX_OPS + 1]
Global Dim avkOpKind.i[#ANVIL_VK_MAX_OPS + 1]
Global Dim avkOpRef.i[#ANVIL_VK_MAX_OPS + 1]
Global Dim avkOpDstRef.i[#ANVIL_VK_MAX_OPS + 1]
Global Dim avkOpOldLayout.i[#ANVIL_VK_MAX_OPS + 1]
Global Dim avkOpNewLayout.i[#ANVIL_VK_MAX_OPS + 1]
Global Dim avkOpColor.i[#ANVIL_VK_MAX_OPS + 1]
Global Dim avkOpBuffer.i[#ANVIL_VK_MAX_OPS + 1]
Global Dim avkOpBufferOffset.i[#ANVIL_VK_MAX_OPS + 1]
Global Dim avkOpDstBuffer.i[#ANVIL_VK_MAX_OPS + 1]
Global Dim avkOpDstOffset.i[#ANVIL_VK_MAX_OPS + 1]
Global Dim avkOpImageX.i[#ANVIL_VK_MAX_OPS + 1]
Global Dim avkOpImageY.i[#ANVIL_VK_MAX_OPS + 1]
Global Dim avkOpSourceBytes.i[#ANVIL_VK_MAX_OPS + 1]
Global Dim avkOpSourcePitch.i[#ANVIL_VK_MAX_OPS + 1]
Global Dim avkOpBufferPitch.i[#ANVIL_VK_MAX_OPS + 1]
Global Dim avkOpRows.i[#ANVIL_VK_MAX_OPS + 1]
Global Dim avkOpCopyGroup.i[#ANVIL_VK_MAX_OPS + 1]
; Each possible update operation owns the complete Vulkan 1.0 maximum so
; its source bytes survive caller mutation until reset or submission.
Global Dim avkOpUpdateData.a[#ANVIL_VK_MAX_OPS * #ANVIL_VK_MAX_UPDATE_BYTES]

Global Dim avkCbOpHead.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbOpTail.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbRefCount.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbFailCode.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbFailText.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]

; Flattened [command buffer][reference] tables.
Global Dim avkRefImage.i[#ANVIL_VK_MAX_COMMAND_BUFFERS * #ANVIL_VK_MAX_CB_REFS]
Global Dim avkRefSlot.i[#ANVIL_VK_MAX_COMMAND_BUFFERS * #ANVIL_VK_MAX_CB_REFS]
Global Dim avkRefEntry.i[#ANVIL_VK_MAX_COMMAND_BUFFERS * #ANVIL_VK_MAX_CB_REFS]
Global Dim avkRefCur.i[#ANVIL_VK_MAX_COMMAND_BUFFERS * #ANVIL_VK_MAX_CB_REFS]

; ----------------------------------------------------------------------
;  THE RECORDED DRAW.
;
;  A render pass with a draw in it is not a list of ops: it is one job,
;  and the state below is what that job is made of. It lives here, next
;  to the rest of the command-buffer state, so that avkCbClear() cannot
;  forget a piece of it - the one failure this engine has already had
;  once, on a table that lived somewhere else.
;
;  It is FILLED by vk_pipeline.pbi, which owns the pipeline objects and
;  the recording rules, and it is READ here at submit time. The two
;  procedures that bridge the two files are declared here and defined
;  there, the same seam shape the backend uses.
; ----------------------------------------------------------------------
Global Dim avkCbPipe.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
; Passive compute binding and one immutable dispatch snapshot. Public compute
; recording and queue execution remain unavailable. Handles retain generation
; tokens; reset clears every field through avkCbClear.
Global Dim avkCbComputePipe.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbComputeSet.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbComputeRecorded.a[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbComputeRecordPipe.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbComputeRecordSet.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbComputeGroupsX.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbComputeInputBase.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbComputeInputBytes.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbComputeOutputBase.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbComputeOutputBytes.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbComputeOutputWrittenBytes.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbComputeItems.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
; ONE BOUND BUFFER PER BINDING. vkCmdBindVertexBuffers names a first
; binding and a count, so the state it sets is per binding and cannot be
; one buffer and one offset: a pipeline that reads position from binding
; zero and colour from binding one has two of each, at two strides.
Global Dim avkCbVtxBuf.i[(#ANVIL_VK_MAX_COMMAND_BUFFERS + 1) * #ANVIL_VK_MAX_BINDINGS]
Global Dim avkCbVtxOffset.i[(#ANVIL_VK_MAX_COMMAND_BUFFERS + 1) * #ANVIL_VK_MAX_BINDINGS]
; Index-buffer binding is independent command-buffer state. A zero handle
; means no binding. Each non-empty indexed draw snapshots all three values.
Global Dim avkCbIndexBuf.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbIndexOffset.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbIndexType.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbRpActive.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbRpDone.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbFb.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbFbHandle.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbClearWord.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbDrawCount.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbDrawFirst.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbDrawVerts.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
; The one descriptor set vkCmdBindDescriptorSets bound, plus the immutable
; compatibility signature copied from the pipeline layout at record time.
; Vulkan does not require that source layout handle to remain live, so a
; command buffer never retains or later resolves that destructible slot.
Global Dim avkCbDescSet.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbDescSetCount.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbDescBindingCount.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbDescPushBytes.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbDescType.i[(#ANVIL_VK_MAX_COMMAND_BUFFERS + 1) * #ANVIL_VK_MAX_SET_BINDINGS]
Global Dim avkCbDescStages.i[(#ANVIL_VK_MAX_COMMAND_BUFFERS + 1) * #ANVIL_VK_MAX_SET_BINDINGS]
Global Dim avkCbPushBytes.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbPushWord.i[(#ANVIL_VK_MAX_COMMAND_BUFFERS + 1) * 4]
; Dynamic viewport is command-buffer state just like dynamic scissor. Only an
; origin-zero, positive whole-pixel viewport with depth 0..1 is accepted.
Global Dim avkCbViewportSet.a[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbViewportX.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbViewportY.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbViewportW.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbViewportH.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
; Dynamic scissor is command-buffer state, independent of the pipeline bind.
; A reset clears the supplied bit; each non-empty dynamic-scissor draw copies
; these four values into its immutable recorded-draw slot.
Global Dim avkCbScissorSet.a[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbScissorX.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbScissorY.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbScissorW.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbScissorH.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]

; Slot zero is the null link. The live slots are 1..4096 and move between one
; deterministic free chain and at most one command-buffer chain. Allocation
; and append are O(1); clear validates the owned chain before splicing it back.
Global Dim avkRecordedDraw.AnvilVkRecordedDraw[#ANVIL_VK_MAX_RECORDED_DRAWS + 1]
Global Dim avkCbDrawHead.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCbDrawTail.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global avkRecordedDrawFreeHead.i = 0
Global avkRecordedDrawFreeCount.i = 0
Global avkRecordedDrawPoolReady.i = 0

Declare.i avkDrawListPreflight(c.i)
Declare avkDrawListRetain(c.i)
Declare avkDrawListRelease(c.i)
Declare avkDrawListDiscard()
Declare.i avkDrawListSubmit()
Declare.i avkRenderClearPreflight(c.i)
Declare avkRenderClearRetain(c.i)
Declare avkRenderClearRelease()
Declare avkRenderClearDiscard()
Declare.i avkRenderClearSubmit()
Declare.i avkCopyBufferResolve(buffer.i, deviceSlot.i, offset.i, bytes.i, *baseOut)
Declare.i AnvilVkBufferSize(buffer.i)
Declare.i avkTransferBufferResolve(buffer.i, deviceSlot.i, usage.i, offset.i, bytes.i, *baseOut)
Declare.i avkBufferBarrierResolve(buffer.i, deviceSlot.i, offset.i, bytes.i, *actualBytes)
Declare avkCopyBufferRetain(c.i)
Declare avkCopyBufferRelease(c.i)
Declare avkCbFail(c.i, code.i, text.i)
Declare.i avkCbRef(c.i, image.i, s.i)
Declare.i avkRefClaim(c.i, k.i, claim.i)
Declare.i avkOpAppend(c.i, kind.i)
Declare.i avkImageRowsOverlap(a.i, aPitch.i, aBytes.i, aRows.i, b.i, bPitch.i, bBytes.i, bRows.i)

; Build the free list once, in increasing slot order. Lazy initialisation keeps
; this include free of executable top-level setup and gives every target the
; same first allocation (slot 1) regardless of its startup path.
Procedure avkRecordedDrawPoolInit()
  Define s.i
  Define k.i
  If avkRecordedDrawPoolReady <> 0
    ProcedureReturn
  EndIf
  s = 1
  While s <= #ANVIL_VK_MAX_RECORDED_DRAWS
    If s < #ANVIL_VK_MAX_RECORDED_DRAWS
      avkRecordedDraw[s]\next = s + 1
    Else
      avkRecordedDraw[s]\next = 0
    EndIf
    avkRecordedDraw[s]\pipeline = 0
    avkRecordedDraw[s]\kind = #ANVIL_VK_RENDER_OP_DRAW
    avkRecordedDraw[s]\descriptorSet = 0
    avkRecordedDraw[s]\firstVertex = 0
    avkRecordedDraw[s]\vertexCount = 0
    avkRecordedDraw[s]\indexBuffer = 0
    avkRecordedDraw[s]\indexOffset = 0
    avkRecordedDraw[s]\indexType = 0
    avkRecordedDraw[s]\pushBytes = 0
    k = 0
    While k < 4
      avkRecordedDraw[s]\vertexBuffer[k] = 0
      avkRecordedDraw[s]\vertexOffset[k] = 0
      avkRecordedDraw[s]\pushWord[k] = 0
      k = k + 1
    Wend
    s = s + 1
  Wend
  avkRecordedDrawFreeHead = 1
  avkRecordedDrawFreeCount = #ANVIL_VK_MAX_RECORDED_DRAWS
  avkRecordedDrawPoolReady = 1
EndProcedure

; Snapshot the command buffer's current graphics bind state and append one
; non-empty draw. Returns its positive slot, zero for a zero-vertex or
; zero-instance no-op, or -1 when the aggregate pool refuses the draw. No pool or
; command-buffer field changes on either non-success path.
Procedure.i avkRecordedDrawAppend(c.i, firstVertex.i, vertexCount.i, viewportX.i, viewportY.i, viewportW.i, viewportH.i, scissorX.i, scissorY.i, scissorW.i, scissorH.i, indexBuffer.i, indexOffset.i, indexType.i, instanceCount.i, firstInstance.i)
  Define s.i
  Define nextFree.i
  Define k.i
  If c < 1 Or c > #ANVIL_VK_MAX_COMMAND_BUFFERS Or vertexCount < 0 Or firstVertex < 0 Or instanceCount < 0 Or firstInstance < 0
    ProcedureReturn -1
  EndIf
  If vertexCount = 0 Or instanceCount = 0 : ProcedureReturn 0 : EndIf
  avkRecordedDrawPoolInit()
  If avkCbDrawCount[c] < 0 Or avkCbDrawCount[c] >= #ANVIL_VK_MAX_RECORDED_DRAWS
    ProcedureReturn -1
  EndIf
  If (avkCbDrawCount[c] = 0 And (avkCbDrawHead[c] <> 0 Or avkCbDrawTail[c] <> 0)) Or (avkCbDrawCount[c] > 0 And (avkCbDrawHead[c] = 0 Or avkCbDrawTail[c] = 0))
    ProcedureReturn -1
  EndIf
  s = avkRecordedDrawFreeHead
  If s < 1 Or s > #ANVIL_VK_MAX_RECORDED_DRAWS Or avkRecordedDrawFreeCount < 1
    ProcedureReturn -1
  EndIf
  nextFree = avkRecordedDraw[s]\next

  ; Every field is assigned before publication into the command-buffer chain.
  ; A reused slot therefore cannot expose bytes from its earlier owner.
  avkRecordedDraw[s]\next = 0
  avkRecordedDraw[s]\kind = #ANVIL_VK_RENDER_OP_DRAW
  avkRecordedDraw[s]\pipeline = avkCbPipe[c]
  avkRecordedDraw[s]\descriptorSet = avkCbDescSet[c]
  avkRecordedDraw[s]\firstVertex = firstVertex
  avkRecordedDraw[s]\vertexCount = vertexCount
  avkRecordedDraw[s]\instanceCount = instanceCount
  avkRecordedDraw[s]\firstInstance = firstInstance
  avkRecordedDraw[s]\indexBuffer = indexBuffer
  avkRecordedDraw[s]\indexOffset = indexOffset
  avkRecordedDraw[s]\indexType = indexType
  avkRecordedDraw[s]\pushBytes = avkCbPushBytes[c]
  avkRecordedDraw[s]\viewportX = viewportX
  avkRecordedDraw[s]\viewportY = viewportY
  avkRecordedDraw[s]\viewportW = viewportW
  avkRecordedDraw[s]\viewportH = viewportH
  avkRecordedDraw[s]\scissorX = scissorX
  avkRecordedDraw[s]\scissorY = scissorY
  avkRecordedDraw[s]\scissorW = scissorW
  avkRecordedDraw[s]\scissorH = scissorH
  k = 0
  While k < 4
    avkRecordedDraw[s]\vertexBuffer[k] = avkCbVtxBuf[(c * #ANVIL_VK_MAX_BINDINGS) + k]
    avkRecordedDraw[s]\vertexOffset[k] = avkCbVtxOffset[(c * #ANVIL_VK_MAX_BINDINGS) + k]
    avkRecordedDraw[s]\pushWord[k] = avkCbPushWord[(c * 4) + k] & $FFFFFFFF
    k = k + 1
  Wend

  avkRecordedDrawFreeHead = nextFree
  avkRecordedDrawFreeCount = avkRecordedDrawFreeCount - 1
  If avkCbDrawCount[c] = 0
    avkCbDrawHead[c] = s
  Else
    avkRecordedDraw[avkCbDrawTail[c]]\next = s
  EndIf
  avkCbDrawTail[c] = s
  avkCbDrawCount[c] = avkCbDrawCount[c] + 1
  ProcedureReturn s
EndProcedure

; Append one already-validated in-pass colour rectangle. It owns no pipeline
; or descriptor state; its kind and five values are the entire clear snapshot.
Procedure.i avkRecordedClearRectAppend(c.i, x.i, y.i, w.i, h.i, bgra.i)
  Define s.i, nextFree.i, k.i
  If c < 1 Or c > #ANVIL_VK_MAX_COMMAND_BUFFERS Or x < 0 Or y < 0 Or w < 1 Or h < 1
    ProcedureReturn -1
  EndIf
  avkRecordedDrawPoolInit()
  If avkCbDrawCount[c] < 0 Or avkCbDrawCount[c] >= #ANVIL_VK_MAX_RECORDED_DRAWS
    ProcedureReturn -1
  EndIf
  If (avkCbDrawCount[c] = 0 And (avkCbDrawHead[c] <> 0 Or avkCbDrawTail[c] <> 0)) Or (avkCbDrawCount[c] > 0 And (avkCbDrawHead[c] = 0 Or avkCbDrawTail[c] = 0))
    ProcedureReturn -1
  EndIf
  s = avkRecordedDrawFreeHead
  If s < 1 Or s > #ANVIL_VK_MAX_RECORDED_DRAWS Or avkRecordedDrawFreeCount < 1
    ProcedureReturn -1
  EndIf
  nextFree = avkRecordedDraw[s]\next
  avkRecordedDraw[s]\next = 0
  avkRecordedDraw[s]\kind = #ANVIL_VK_RENDER_OP_CLEAR_RECT
  avkRecordedDraw[s]\pipeline = 0 : avkRecordedDraw[s]\descriptorSet = 0
  avkRecordedDraw[s]\firstVertex = 0 : avkRecordedDraw[s]\vertexCount = 0
  avkRecordedDraw[s]\instanceCount = 0 : avkRecordedDraw[s]\firstInstance = 0
  avkRecordedDraw[s]\indexBuffer = 0 : avkRecordedDraw[s]\indexOffset = 0 : avkRecordedDraw[s]\indexType = 0
  avkRecordedDraw[s]\pushBytes = 0
  avkRecordedDraw[s]\viewportX = x : avkRecordedDraw[s]\viewportY = y
  avkRecordedDraw[s]\viewportW = w : avkRecordedDraw[s]\viewportH = h
  avkRecordedDraw[s]\scissorX = 0 : avkRecordedDraw[s]\scissorY = 0
  avkRecordedDraw[s]\scissorW = 0 : avkRecordedDraw[s]\scissorH = 0
  k = 0
  While k < 4
    avkRecordedDraw[s]\vertexBuffer[k] = 0 : avkRecordedDraw[s]\vertexOffset[k] = 0
    avkRecordedDraw[s]\pushWord[k] = 0
    k = k + 1
  Wend
  avkRecordedDraw[s]\pushWord[0] = bgra & $FFFFFFFF
  avkRecordedDrawFreeHead = nextFree
  avkRecordedDrawFreeCount = avkRecordedDrawFreeCount - 1
  If avkCbDrawCount[c] = 0
    avkCbDrawHead[c] = s
  Else
    avkRecordedDraw[avkCbDrawTail[c]]\next = s
  EndIf
  avkCbDrawTail[c] = s
  avkCbDrawCount[c] = avkCbDrawCount[c] + 1
  ProcedureReturn s
EndProcedure

; Validate the complete owned chain before changing either owner. Only after
; head, tail, length and terminal link agree is the chain spliced back onto the
; free list. A corrupt chain is therefore refused without a partial return.
Procedure.i avkRecordedDrawRelease(c.i)
  Define count.i
  Define seen.i
  Define s.i
  Define n.i
  If c < 1 Or c > #ANVIL_VK_MAX_COMMAND_BUFFERS : ProcedureReturn 0 : EndIf
  avkRecordedDrawPoolInit()
  count = avkCbDrawCount[c]
  If count = 0
    If avkCbDrawHead[c] <> 0 Or avkCbDrawTail[c] <> 0 : ProcedureReturn 0 : EndIf
    ProcedureReturn 1
  EndIf
  If count < 1 Or count > #ANVIL_VK_MAX_RECORDED_DRAWS
    ProcedureReturn 0
  EndIf
  If avkCbDrawHead[c] < 1 Or avkCbDrawHead[c] > #ANVIL_VK_MAX_RECORDED_DRAWS Or avkCbDrawTail[c] < 1 Or avkCbDrawTail[c] > #ANVIL_VK_MAX_RECORDED_DRAWS
    ProcedureReturn 0
  EndIf
  s = avkCbDrawHead[c]
  seen = 0
  While seen < count
    If s < 1 Or s > #ANVIL_VK_MAX_RECORDED_DRAWS : ProcedureReturn 0 : EndIf
    n = avkRecordedDraw[s]\next
    seen = seen + 1
    If seen = count
      If s <> avkCbDrawTail[c] Or n <> 0 : ProcedureReturn 0 : EndIf
    Else
      If n < 1 Or n > #ANVIL_VK_MAX_RECORDED_DRAWS : ProcedureReturn 0 : EndIf
    EndIf
    s = n
  Wend
  If avkRecordedDrawFreeCount < 0 Or avkRecordedDrawFreeCount > (#ANVIL_VK_MAX_RECORDED_DRAWS - count)
    ProcedureReturn 0
  EndIf

  avkRecordedDraw[avkCbDrawTail[c]]\next = avkRecordedDrawFreeHead
  avkRecordedDrawFreeHead = avkCbDrawHead[c]
  avkRecordedDrawFreeCount = avkRecordedDrawFreeCount + count
  avkCbDrawHead[c] = 0
  avkCbDrawTail[c] = 0
  avkCbDrawCount[c] = 0
  ProcedureReturn 1
EndProcedure

; The single outstanding submission.
Global avkFlightActive.i = 0
Global avkFlightCb.i = 0
Global avkFlightFence.i = 0
Global avkFlightSemaphoreReservation.i = 0
Global avkSubmitCount.i = 0
Global avkCompleteCount.i = 0

Procedure.i avkRefIndex(c.i, k.i)
  ProcedureReturn ((c - 1) * #ANVIL_VK_MAX_CB_REFS) + k
EndProcedure

Procedure avkOpsRelease(c.i)
  Define o.i
  Define n.i
  o = avkCbOpHead[c]
  While o <> 0
    n = avkOpNext[o]
    avkOpLive[o] = 0
    avkOpNext[o] = 0
    avkOpKind[o] = #ANVIL_VK_OP_NONE
    avkOpBuffer[o] = 0
    avkOpBufferOffset[o] = 0
    avkOpDstBuffer[o] = 0
    avkOpDstOffset[o] = 0
    avkOpImageX[o] = 0
    avkOpImageY[o] = 0
    avkOpSourceBytes[o] = 0
    avkOpSourcePitch[o] = 0
    avkOpBufferPitch[o] = 0
    avkOpRows[o] = 0
    avkOpCopyGroup[o] = 0
    o = n
  Wend
  avkCbOpHead[c] = 0
  avkCbOpTail[c] = 0
EndProcedure

; A complete VkBufferCopy array is validated before any region is appended.
; All source regions must be disjoint from every destination region, and
; destination regions must be mutually disjoint within this one Vulkan call.
; Separate commands remain ordered and may use an earlier command's output.
Procedure AnvilVkCmdCopyBuffer(commandBuffer.i, srcBuffer.i, dstBuffer.i, regionCount.i, *regions.VkBufferCopy)
  Define c.i
  Define d.i
  Define o.i
  Define i.i
  Define j.i
  Define freeOps.i
  Define sourceBase.i
  Define destinationBase.i
  Define source.i
  Define destination.i
  Define priorSource.i
  Define priorDestination.i
  Define *r.VkBufferCopy
  Define *prior.VkBufferCopy
  c = avkCmdSlot(commandBuffer)
  If c = 0
    ProcedureReturn
  EndIf
  If avkCmdState[c] <> #ANVIL_VK_CB_RECORDING Or avkCbRpActive[c] <> 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdCopyBuffer requires a recording command buffer outside a render pass (Anvil code -20004, wrong recording state); begin recording and end the pass first.")
    ProcedureReturn
  EndIf
  If (avkBackendCaps() & #ANVIL_VK_CAP_BUFFER_TRANSFER) = 0
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyBuffer requires a backend that executes buffer transfers (Anvil code -20005, unsupported transfer); choose a transfer-capable device before recording this command.")
    ProcedureReturn
  EndIf
  If regionCount < 1 Or regionCount > #ANVIL_VK_MAX_OPS
    avkCbFail(c, #VK_ERROR_OUT_OF_HOST_MEMORY, "vkCmdCopyBuffer has more regions than the command pool can retain (VkResult -1, VK_ERROR_OUT_OF_HOST_MEMORY); split the transfer across command buffers.")
    ProcedureReturn
  EndIf
  freeOps = 0
  o = 1
  While o <= #ANVIL_VK_MAX_OPS
    If avkOpLive[o] = 0 : freeOps = freeOps + 1 : EndIf
    o = o + 1
  Wend
  If freeOps < regionCount
    avkCbFail(c, #VK_ERROR_OUT_OF_HOST_MEMORY, "vkCmdCopyBuffer cannot retain every region in the shared command pool (VkResult -1, VK_ERROR_OUT_OF_HOST_MEMORY); reset unused command buffers.")
    ProcedureReturn
  EndIf
  d = avkPoolDev[avkCmdPool[c]]
  sourceBase = AnvilVkBufferAddress(srcBuffer)
  destinationBase = AnvilVkBufferAddress(dstBuffer)
  i = 0
  While i < regionCount
    *r = *regions + (i * SizeOf(VkBufferCopy))
    If *r\size < 1 Or *r\srcOffset < 0 Or *r\dstOffset < 0
      avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyBuffer requires positive sizes and non-negative offsets (Anvil code -20001, invalid VkBufferCopy); correct every region before recording.")
      ProcedureReturn
    EndIf
    If avkTransferBufferResolve(srcBuffer, d, #VK_BUFFER_USAGE_TRANSFER_SRC_BIT, *r\srcOffset, *r\size, @source) = 0 Or avkTransferBufferResolve(dstBuffer, d, #VK_BUFFER_USAGE_TRANSFER_DST_BIT, *r\dstOffset, *r\size, @destination) = 0
      avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdCopyBuffer needs live, bound, same-device transfer buffers covering every region (Anvil code -20004, invalid buffer); repair the bindings or ranges.")
      ProcedureReturn
    EndIf
    If source < destination + *r\size And destination < source + *r\size
      avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyBuffer source and destination memory ranges overlap (Anvil code -20001, overlapping copy); use disjoint regions as Vulkan requires.")
      ProcedureReturn
    EndIf
    j = 0
    While j < i
      *prior = *regions + (j * SizeOf(VkBufferCopy))
      priorSource = sourceBase + *prior\srcOffset
      priorDestination = destinationBase + *prior\dstOffset
      If source < priorDestination + *prior\size And priorDestination < source + *r\size
        avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyBuffer has a source region overlapping an earlier destination region (Anvil code -20001, overlapping copy); every source and destination region in one call must be disjoint.")
        ProcedureReturn
      EndIf
      If destination < priorSource + *prior\size And priorSource < destination + *r\size
        avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyBuffer has a destination region overlapping an earlier source region (Anvil code -20001, overlapping copy); every source and destination region in one call must be disjoint.")
        ProcedureReturn
      EndIf
      If destination < priorDestination + *prior\size And priorDestination < destination + *r\size
        avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyBuffer has two overlapping destination regions (Anvil code -20001, overlapping destinations); each destination byte may be written only once in one call.")
        ProcedureReturn
      EndIf
      j = j + 1
    Wend
    i = i + 1
  Wend
  i = 0
  While i < regionCount
    *r = *regions + (i * SizeOf(VkBufferCopy))
    o = avkOpAppend(c, #ANVIL_VK_OP_COPY_BUFFER)
    If o = 0
      avkCbFail(c, #VK_ERROR_OUT_OF_HOST_MEMORY, "the command pool ran out of recorded-command storage while appending vkCmdCopyBuffer (VkResult -1, VK_ERROR_OUT_OF_HOST_MEMORY); reset the invalid command buffer.")
      ProcedureReturn
    EndIf
    avkOpBuffer[o] = srcBuffer
    avkOpBufferOffset[o] = *r\srcOffset
    avkOpDstBuffer[o] = dstBuffer
    avkOpDstOffset[o] = *r\dstOffset
    avkOpSourceBytes[o] = *r\size
    i = i + 1
  Wend
EndProcedure

; A fill is a transfer into one bound coherent buffer. VK_WHOLE_SIZE is
; rounded down to complete four-byte words, as required by core Vulkan.
Procedure AnvilVkCmdFillBuffer(commandBuffer.i, dstBuffer.i, dstOffset.i, size.i, data.i)
  Define c.i
  Define d.i
  Define bytes.i
  Define targetSize.i
  Define destination.i
  Define o.i
  c = avkCmdSlot(commandBuffer)
  If c = 0
    ProcedureReturn
  EndIf
  If avkCmdState[c] <> #ANVIL_VK_CB_RECORDING Or avkCbRpActive[c] <> 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdFillBuffer requires a recording command buffer outside a render pass (Anvil code -20004, wrong recording state); begin recording and end the pass first.")
    ProcedureReturn
  EndIf
  If (avkBackendCaps() & #ANVIL_VK_CAP_BUFFER_TRANSFER) = 0
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdFillBuffer requires a backend that executes buffer transfers (Anvil code -20005, unsupported transfer); choose a transfer-capable device before recording this command.")
    ProcedureReturn
  EndIf
  targetSize = AnvilVkBufferSize(dstBuffer)
  If dstOffset < 0 Or (dstOffset % 4) <> 0 Or dstOffset >= targetSize
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdFillBuffer requires a four-byte aligned offset inside the destination buffer (Anvil code -20001, invalid offset); correct the offset and buffer.")
    ProcedureReturn
  EndIf
  If size = #VK_WHOLE_SIZE
    bytes = ((targetSize - dstOffset) / 4) * 4
  Else
    bytes = size
    If bytes < 1 Or (bytes % 4) <> 0
      avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdFillBuffer requires a positive four-byte multiple or VK_WHOLE_SIZE (Anvil code -20001, invalid size); correct the fill range.")
      ProcedureReturn
    EndIf
  EndIf
  d = avkPoolDev[avkCmdPool[c]]
  ; A whole-size range can round to zero. Validate the destination's owner,
  ; usage and binding with one byte, then record no write.
  If bytes = 0
    If avkTransferBufferResolve(dstBuffer, d, #VK_BUFFER_USAGE_TRANSFER_DST_BIT, dstOffset, 1, @destination) = 0
      avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdFillBuffer needs a live, bound same-device transfer-destination buffer (Anvil code -20004, invalid buffer); bind the buffer and set TRANSFER_DST usage.")
    EndIf
    ProcedureReturn
  EndIf
  If avkTransferBufferResolve(dstBuffer, d, #VK_BUFFER_USAGE_TRANSFER_DST_BIT, dstOffset, bytes, @destination) = 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdFillBuffer needs a live, bound same-device transfer-destination buffer covering the complete range (Anvil code -20004, invalid buffer); repair the binding or range.")
    ProcedureReturn
  EndIf
  o = avkOpAppend(c, #ANVIL_VK_OP_FILL_BUFFER)
  If o = 0
    avkCbFail(c, #VK_ERROR_OUT_OF_HOST_MEMORY, "the command pool ran out of recorded-command storage for vkCmdFillBuffer (VkResult -1, VK_ERROR_OUT_OF_HOST_MEMORY); reset unused command buffers.")
    ProcedureReturn
  EndIf
  avkOpBuffer[o] = dstBuffer
  avkOpBufferOffset[o] = dstOffset
  avkOpSourceBytes[o] = bytes
  avkOpColor[o] = data & $FFFFFFFF
EndProcedure

; vkCmdUpdateBuffer copies pData at recording time. The operation's slot owns
; a private 64 KiB maximum payload; reset releases the slot for reuse.
Procedure AnvilVkCmdUpdateBuffer(commandBuffer.i, dstBuffer.i, dstOffset.i, dataSize.i, *pData)
  Define c.i
  Define d.i
  Define destination.i
  Define o.i
  Define i.i
  Define *payload
  c = avkCmdSlot(commandBuffer)
  If c = 0
    ProcedureReturn
  EndIf
  If avkCmdState[c] <> #ANVIL_VK_CB_RECORDING Or avkCbRpActive[c] <> 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdUpdateBuffer requires a recording command buffer outside a render pass (Anvil code -20004, wrong recording state); begin recording and end the pass first.")
    ProcedureReturn
  EndIf
  If (avkBackendCaps() & #ANVIL_VK_CAP_BUFFER_TRANSFER) = 0
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdUpdateBuffer requires a backend that executes buffer transfers (Anvil code -20005, unsupported transfer); choose a transfer-capable device before recording this command.")
    ProcedureReturn
  EndIf
  If dstOffset < 0 Or (dstOffset % 4) <> 0 Or dataSize < 1 Or dataSize > #ANVIL_VK_MAX_UPDATE_BYTES Or (dataSize % 4) <> 0 Or *pData = 0
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdUpdateBuffer needs a four-byte aligned destination, a non-null source, and a positive four-byte multiple of at most 65536 bytes (Anvil code -20001, invalid update); correct the arguments.")
    ProcedureReturn
  EndIf
  d = avkPoolDev[avkCmdPool[c]]
  If avkTransferBufferResolve(dstBuffer, d, #VK_BUFFER_USAGE_TRANSFER_DST_BIT, dstOffset, dataSize, @destination) = 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdUpdateBuffer needs a live, bound same-device transfer-destination buffer covering the complete range (Anvil code -20004, invalid buffer); repair the binding or range.")
    ProcedureReturn
  EndIf
  o = avkOpAppend(c, #ANVIL_VK_OP_UPDATE_BUFFER)
  If o = 0
    avkCbFail(c, #VK_ERROR_OUT_OF_HOST_MEMORY, "the command pool ran out of recorded-command storage for vkCmdUpdateBuffer (VkResult -1, VK_ERROR_OUT_OF_HOST_MEMORY); reset unused command buffers.")
    ProcedureReturn
  EndIf
  *payload = @avkOpUpdateData[(o - 1) * #ANVIL_VK_MAX_UPDATE_BYTES]
  i = 0
  While i < dataSize
    PokeA(*payload + i, PeekA(*pData + i))
    i = i + 1
  Wend
  avkOpBuffer[o] = dstBuffer
  avkOpBufferOffset[o] = dstOffset
  avkOpSourceBytes[o] = dataSize
EndProcedure

; One complete BGRA8 region uses TFU for an optimal destination. A bounded
; array of linear regions uses guarded DMA rows. The command captures handles
; and immutable region values here;
; the queue resolves and validates the live resources again before retaining
; them, as Vulkan lifetime belongs to submission rather than recording.
Procedure AnvilVkCmdCopyBufferToImage(commandBuffer.i, srcBuffer.i, dstImage.i, dstImageLayout.i, regionCount.i, *regions.VkBufferImageCopy)
  Define c.i
  Define d.i
  Define s.i
  Define k.i
  Define o.i
  Define sourceBytes.i
  Define sourcePitch.i
  Define bufferPitch.i
  Define rows.i
  Define copyAlign.i
  Define i.i, j.i, freeOps.i, group.i, sourceBase.i, destinationBase.i
  Define sourceBufferBytes.i, sourceBufferBase.i
  Define priorSource.i, priorDestination.i, priorBytes.i, priorPitch.i
  Define partialOptimal.i, tailOptimal.i, microOptimal.i, gridOptimal.i
  Define priorPartialOp.i, tileCount.i, tailCols.i, gridCols.i, gridRows.i, firstCols.i, lastCols.i, gridWide.i
  Define gridCopy.AnvilVkBackendLinearTiledRectCopy
  Define *r.VkBufferImageCopy, *prior.VkBufferImageCopy
  c = avkCmdSlot(commandBuffer)
  If c = 0
    avkFault(#ANVIL_VK_ERR_HANDLE, "vkCmdCopyBufferToImage was given a VkCommandBuffer handle that is not live (Anvil code -20002, stale or foreign handle); nothing was recorded.")
    ProcedureReturn
  EndIf
  If avkCmdState[c] <> #ANVIL_VK_CB_RECORDING
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdCopyBufferToImage was called on a command buffer that is not recording (Anvil code -20004, wrong command buffer state); call vkBeginCommandBuffer first.")
    ProcedureReturn
  EndIf
  If avkCbRpActive[c] <> 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdCopyBufferToImage was called inside a render pass (Anvil code -20004, transfer inside render pass); end the render pass before recording this transfer.")
    ProcedureReturn
  EndIf
  If regionCount < 1 Or regionCount > #ANVIL_VK_MAX_OPS Or *regions = 0
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyBufferToImage requires one to thirty-two non-null regions (Anvil code -20001); nothing was recorded.")
    ProcedureReturn
  EndIf
  o = avkCbOpHead[c]
  While o <> 0
    If avkOpKind[o] = #ANVIL_VK_OP_COPY_BUFFER_IMAGE And (avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_MICRO_TAG Or avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_GRID_TAG Or avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_GRID_4X4_TAG)
      avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyBufferToImage keeps a micro or grid upload in its own command buffer (Anvil code -20005); nothing was recorded.")
      ProcedureReturn
    EndIf
    o = avkOpNext[o]
  Wend
  freeOps = 0
  For o = 1 To #ANVIL_VK_MAX_OPS
    If avkOpLive[o] = 0 : freeOps = freeOps + 1 : EndIf
  Next
  If freeOps < regionCount
    avkCbFail(c, #VK_ERROR_OUT_OF_HOST_MEMORY, "vkCmdCopyBufferToImage cannot retain every region in the shared command pool (VkResult -1); reset unused command buffers.")
    ProcedureReturn
  EndIf
  s = avkImgSlot(dstImage)
  If s = 0
    avkCbFail(c, #ANVIL_VK_ERR_HANDLE, "vkCmdCopyBufferToImage was given a destination VkImage handle that is not live (Anvil code -20002, stale or foreign handle); the command buffer is invalid.")
    ProcedureReturn
  EndIf
  d = avkPoolDev[avkCmdPool[c]]
  If avkImgDev[s] <> d
    avkCbFail(c, #ANVIL_VK_ERR_OWNER, "vkCmdCopyBufferToImage was given a destination image owned by a different device (Anvil code -20003, wrong parent); source, destination and command buffer must share one VkDevice.")
    ProcedureReturn
  EndIf
  If avkImgBound[s] = 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdCopyBufferToImage was given a destination image with no memory bound (Anvil code -20004, image not bound); call vkBindImageMemory first.")
    ProcedureReturn
  EndIf
  If (avkImgTiling[s] <> #VK_IMAGE_TILING_OPTIMAL And avkImgTiling[s] <> #VK_IMAGE_TILING_LINEAR) Or (avkImgUsage[s] & #VK_IMAGE_USAGE_TRANSFER_DST_BIT) = 0
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyBufferToImage requires a linear or optimal BGRA8 destination with TRANSFER_DST usage (Anvil code -20001, wrong destination contract); nothing was recorded.")
    ProcedureReturn
  EndIf
  If avkImgTiling[s] = #VK_IMAGE_TILING_LINEAR And (avkBackendCaps() & #ANVIL_VK_CAP_LINEAR_TRANSFER) = 0
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyBufferToImage requires a backend that executes linear-image uploads (Anvil code -20005, unsupported transfer); choose a device with linear transfer support.")
    ProcedureReturn
  EndIf
  If avkImgTiling[s] = #VK_IMAGE_TILING_OPTIMAL And regionCount <> 1
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyBufferToImage supports one optimal-image region per call (Anvil code -20005); no region array was recorded.")
    ProcedureReturn
  EndIf
  If dstImageLayout <> #VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL And (avkImgTiling[s] <> #VK_IMAGE_TILING_LINEAR Or dstImageLayout <> #VK_IMAGE_LAYOUT_GENERAL)
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyBufferToImage requires TRANSFER_DST_OPTIMAL or, for a linear image, GENERAL layout (Anvil code -20001, wrong copy layout); transition the image before copying.")
    ProcedureReturn
  EndIf
  copyAlign = avkBackendImageCopySourceAlignment()
  If copyAlign < 1 Or (copyAlign & (copyAlign - 1)) <> 0
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyBufferToImage could not obtain a power-of-two source-alignment contract from the active backend (Anvil code -20005, incomplete copy backend); no transfer was recorded.")
    ProcedureReturn
  EndIf
  For i = 0 To regionCount - 1
  *r = *regions + i * SizeOf(VkBufferImageCopy)
  If (*r\bufferOffset % copyAlign) <> 0 Or *r\bufferOffset < 0
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyBufferToImage requires a non-negative bufferOffset aligned to the active backend's image-copy source requirement (Anvil code -20001, misaligned buffer offset); query and obey the target's published transfer contract.")
    ProcedureReturn
  EndIf
  If *r\imageSubresource\aspectMask <> #VK_IMAGE_ASPECT_COLOR_BIT Or *r\imageSubresource\mipLevel <> 0 Or *r\imageSubresource\baseArrayLayer <> 0 Or *r\imageSubresource\layerCount <> 1
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyBufferToImage was given a subresource other than colour mip zero, layer zero, count one (Anvil code -20005, unsupported subresource); every image in this subset has exactly that one subresource.")
    ProcedureReturn
  EndIf
  If *r\imageOffset\x < 0 Or *r\imageOffset\y < 0 Or *r\imageOffset\z <> 0 Or *r\imageExtent\width < 1 Or *r\imageExtent\height < 1 Or *r\imageExtent\depth <> 1
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyBufferToImage requires a positive two-dimensional region with non-negative XY offsets and zero Z offset (Anvil code -20001); nothing was recorded.")
    ProcedureReturn
  EndIf
  If *r\imageOffset\x > avkImgW[s] - *r\imageExtent\width Or *r\imageOffset\y > avkImgH[s] - *r\imageExtent\height
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyBufferToImage requires the complete rectangle to fit its destination image (Anvil code -20001); nothing was recorded.")
    ProcedureReturn
  EndIf
  If (*r\bufferRowLength <> 0 And *r\bufferRowLength < *r\imageExtent\width) Or (*r\bufferImageHeight <> 0 And *r\bufferImageHeight < *r\imageExtent\height)
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyBufferToImage requires an explicit bufferRowLength and bufferImageHeight to cover the copied rectangle (Anvil code -20001); nothing was recorded.")
    ProcedureReturn
  EndIf
  If *r\bufferRowLength > 536870911
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyBufferToImage bufferRowLength cannot be represented as a signed byte pitch (Anvil code -20001); nothing was recorded.")
    ProcedureReturn
  EndIf
  If avkImgTiling[s] = #VK_IMAGE_TILING_OPTIMAL And (*r\imageOffset\x <> 0 Or *r\imageOffset\y <> 0 Or *r\imageExtent\width <> avkImgW[s] Or *r\imageExtent\height <> avkImgH[s])
    partialOptimal = 1
    gridCols = (*r\imageOffset\x + *r\imageExtent\width - 1) / 4 - *r\imageOffset\x / 4 + 1
    gridRows = (*r\imageOffset\y + *r\imageExtent\height - 1) / 4 - *r\imageOffset\y / 4 + 1
    gridOptimal = Bool(gridCols <= 4 And gridRows <= 4 And gridCols * gridRows >= 2 And ((*r\imageOffset\x % 4) <> 0 Or (*r\imageOffset\y % 4) <> 0 Or ((*r\imageExtent\width % 4) <> 0 And *r\imageOffset\x <> avkImgW[s] - *r\imageExtent\width) Or ((*r\imageExtent\height % 4) <> 0 And *r\imageOffset\y <> avkImgH[s] - *r\imageExtent\height)))
    gridWide = Bool(gridOptimal <> 0 And (gridCols > 2 Or gridRows > 2))
    If *r\imageExtent\width <= 4 And *r\imageExtent\height <= 4 And (*r\imageOffset\x % 4) + *r\imageExtent\width <= 4 And (*r\imageOffset\y % 4) + *r\imageExtent\height <= 4 And ((*r\imageOffset\x % 4) <> 0 Or (*r\imageOffset\y % 4) <> 0 Or ((*r\imageExtent\width % 4) <> 0 And *r\imageOffset\x <> avkImgW[s] - *r\imageExtent\width) Or ((*r\imageExtent\height % 4) <> 0 And *r\imageOffset\y <> avkImgH[s] - *r\imageExtent\height))
      microOptimal = 1
      gridOptimal = 0
      If (avkBackendCaps() & (#ANVIL_VK_CAP_BUFFER_TO_TILED_RECT_COPY | #ANVIL_VK_CAP_BUFFER_TO_TILED_MICRO_COPY)) <> (#ANVIL_VK_CAP_BUFFER_TO_TILED_RECT_COPY | #ANVIL_VK_CAP_BUFFER_TO_TILED_MICRO_COPY)
        avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyBufferToImage one-utile micro upload requires the dedicated backend capability (Anvil code -20005); nothing was recorded.")
        ProcedureReturn
      EndIf
    ElseIf gridOptimal <> 0
      If gridWide <> 0 And (avkBackendCaps() & #ANVIL_VK_CAP_BUFFER_TO_TILED_GRID_4X4_COPY) = 0
        avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyBufferToImage extended UIF grid upload requires its dedicated guarded-DMA backend capability (Anvil code -20005); nothing was recorded.")
        ProcedureReturn
      EndIf
      If gridWide = 0 And (avkBackendCaps() & #ANVIL_VK_CAP_BUFFER_TO_TILED_GRID_COPY) = 0
        avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyBufferToImage interior UIF grid upload requires its dedicated guarded-DMA backend capability (Anvil code -20005); nothing was recorded.")
        ProcedureReturn
      EndIf
      If (avkBackendCaps() & (#ANVIL_VK_CAP_BUFFER_TRANSFER | #ANVIL_VK_CAP_LINEAR_TRANSFER | #ANVIL_VK_CAP_BUFFER_TO_TILED_RECT_COPY)) <> (#ANVIL_VK_CAP_BUFFER_TRANSFER | #ANVIL_VK_CAP_LINEAR_TRANSFER | #ANVIL_VK_CAP_BUFFER_TO_TILED_RECT_COPY)
        avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyBufferToImage interior UIF grid upload requires its dedicated guarded-DMA backend capability (Anvil code -20005); nothing was recorded.")
        ProcedureReturn
      EndIf
    ElseIf (*r\imageExtent\width % 4) <> 0 Or (*r\imageExtent\height % 4) <> 0
      tailOptimal = 1
      If (avkBackendCaps() & (#ANVIL_VK_CAP_BUFFER_TO_TILED_RECT_COPY | #ANVIL_VK_CAP_BUFFER_TO_TILED_TAIL_COPY)) <> (#ANVIL_VK_CAP_BUFFER_TO_TILED_RECT_COPY | #ANVIL_VK_CAP_BUFFER_TO_TILED_TAIL_COPY)
        avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyBufferToImage edge-tail optimal upload requires a backend that executes short UIF tiles (Anvil code -20005); nothing was recorded.")
        ProcedureReturn
      EndIf
    ElseIf (avkBackendCaps() & #ANVIL_VK_CAP_BUFFER_TO_TILED_RECT_COPY) = 0
      avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyBufferToImage partial optimal upload requires a buffer-to-tiled backend (Anvil code -20005); nothing was recorded.")
      ProcedureReturn
    EndIf
    o = avkCbOpHead[c]
    While o <> 0
      If (microOptimal <> 0 Or gridOptimal <> 0) And avkOpKind[o] = #ANVIL_VK_OP_COPY_BUFFER_IMAGE
        avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyBufferToImage keeps a micro upload in its own command buffer (Anvil code -20005); nothing was recorded.")
        ProcedureReturn
      EndIf
      If avkOpKind[o] = #ANVIL_VK_OP_COPY_BUFFER_IMAGE And (avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_RECT_TAG Or avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_MICRO_TAG Or avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_GRID_TAG Or avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_GRID_4X4_TAG)
        If microOptimal <> 0 Or gridOptimal <> 0 Or avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_MICRO_TAG Or avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_GRID_TAG Or avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_GRID_4X4_TAG
          avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyBufferToImage keeps a micro upload in its own command buffer (Anvil code -20005); nothing was recorded.")
          ProcedureReturn
        EndIf
        If priorPartialOp <> 0
          avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyBufferToImage supports at most two partial optimal uploads per command buffer (Anvil code -20005); nothing was recorded.")
          ProcedureReturn
        EndIf
        priorPartialOp = o
      EndIf
      o = avkOpNext[o]
    Wend
    If (microOptimal = 0 And gridOptimal = 0 And ((*r\imageOffset\x % 4) <> 0 Or (*r\imageOffset\y % 4) <> 0)) Or ((*r\imageExtent\width - 1) / 4 + 1) > #ANVIL_VK_TILED_RECT_MAX_UTILES Or ((*r\imageExtent\height - 1) / 4 + 1) > #ANVIL_VK_TILED_RECT_MAX_UTILES
      avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyBufferToImage partial optimal upload requires aligned XY, short extents only at image edges, and at most 256 tiles (Anvil code -20005); nothing was recorded.")
      ProcedureReturn
    EndIf
    If (microOptimal = 0 And gridOptimal = 0 And tailOptimal <> 0 And (*r\imageExtent\width % 4) <> 0 And *r\imageOffset\x <> avkImgW[s] - *r\imageExtent\width) Or (microOptimal = 0 And gridOptimal = 0 And tailOptimal <> 0 And (*r\imageExtent\height % 4) <> 0 And *r\imageOffset\y <> avkImgH[s] - *r\imageExtent\height)
      avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyBufferToImage short partial optimal dimensions must reach the corresponding image edge (Anvil code -20005); nothing was recorded.")
      ProcedureReturn
    EndIf
    tileCount = ((*r\imageExtent\width - 1) / 4 + 1) * ((*r\imageExtent\height - 1) / 4 + 1)
    If gridOptimal <> 0 : tileCount = gridCols * gridRows : EndIf
    If tileCount > #ANVIL_VK_TILED_RECT_MAX_UTILES
      avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyBufferToImage partial optimal upload exceeds 256 tiles (Anvil code -20005); nothing was recorded.")
      ProcedureReturn
    EndIf
    If priorPartialOp <> 0
      If avkRefImage[avkRefIndex(c, avkOpRef[priorPartialOp])] <> dstImage
        avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyBufferToImage orders two partial optimal uploads only to the same destination image (Anvil code -20005); nothing was recorded.")
        ProcedureReturn
      EndIf
      If tileCount + ((avkOpSourcePitch[priorPartialOp] - 4) / 16 + 1) * ((avkOpRows[priorPartialOp] - 1) / 4 + 1) > #ANVIL_VK_TILED_RECT_MAX_UTILES
        avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyBufferToImage ordered partial uploads exceed 256 tiles in total (Anvil code -20005); nothing was recorded.")
        ProcedureReturn
      EndIf
      If *r\imageOffset\x < avkOpImageX[priorPartialOp] + avkOpSourcePitch[priorPartialOp] / 4 And avkOpImageX[priorPartialOp] < *r\imageOffset\x + *r\imageExtent\width And *r\imageOffset\y < avkOpImageY[priorPartialOp] + avkOpRows[priorPartialOp] And avkOpImageY[priorPartialOp] < *r\imageOffset\y + *r\imageExtent\height
        avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyBufferToImage ordered partial destination rectangles overlap (Anvil code -20001); nothing was recorded.")
        ProcedureReturn
      EndIf
    EndIf
  EndIf
  sourcePitch = *r\imageExtent\width * #ANVIL_VK_BGRA8_TEXEL_BYTES
  rows = *r\imageExtent\height
  bufferPitch = sourcePitch
  If *r\bufferRowLength <> 0 : bufferPitch = *r\bufferRowLength * #ANVIL_VK_BGRA8_TEXEL_BYTES : EndIf
  sourceBytes = (rows - 1) * bufferPitch + sourcePitch
  If sourcePitch < 1 Or bufferPitch < sourcePitch Or sourceBytes < sourcePitch
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyBufferToImage computed a wrapped source span (Anvil code -20001, invalid extent); nothing was recorded.")
    ProcedureReturn
  EndIf
  tailCols = 4
  If (*r\imageExtent\width % 4) <> 0 : tailCols = *r\imageExtent\width % 4 : EndIf
  If microOptimal <> 0 : tailCols = *r\imageExtent\width : EndIf
  If gridOptimal <> 0
    firstCols = 4 - (*r\imageOffset\x % 4)
    If firstCols > *r\imageExtent\width : firstCols = *r\imageExtent\width : EndIf
    tailCols = firstCols
    If gridCols > 1
      lastCols = (*r\imageOffset\x + *r\imageExtent\width - 1) % 4 + 1
      If lastCols < tailCols : tailCols = lastCols : EndIf
    EndIf
  EndIf
  If partialOptimal <> 0 And bufferPitch - tailCols * 4 > 32767
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyBufferToImage partial optimal upload exceeds the backend DMA source stride (Anvil code -20005); nothing was recorded.")
    ProcedureReturn
  EndIf
  If avkImgTiling[s] = #VK_IMAGE_TILING_LINEAR And (sourcePitch > avkImgPitch[s] Or *r\imageOffset\y * avkImgPitch[s] + *r\imageOffset\x * #ANVIL_VK_BGRA8_TEXEL_BYTES + (*r\imageExtent\height - 1) * avkImgPitch[s] + sourcePitch > avkImgSize[s])
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdCopyBufferToImage found a linear image pitch or allocation too short for the requested rows (Anvil code -20004); nothing was recorded.")
    ProcedureReturn
  EndIf
  If avkCopyBufferResolve(srcBuffer, d, *r\bufferOffset, sourceBytes, @sourceBase) = 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdCopyBufferToImage could not resolve a live, bound VK_BUFFER_USAGE_TRANSFER_SRC_BIT buffer covering the complete source region (Anvil code -20004, invalid source buffer); bind sufficient memory and keep the buffer live.")
    ProcedureReturn
  EndIf
  If partialOptimal <> 0
    destinationBase = avkHeapBase + avkMemOffset[avkImgMemSlot[s]] + avkImgMemOffset[s]
    sourceBufferBytes = AnvilVkBufferSize(srcBuffer)
    sourceBufferBase = AnvilVkBufferAddress(srcBuffer)
    If sourceBufferBytes < 1 Or sourceBufferBase = 0 Or avkImageRowsOverlap(sourceBufferBase, sourceBufferBytes, sourceBufferBytes, 1, destinationBase, avkImgSize[s], avkImgSize[s], 1) <> 0
      avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyBufferToImage partial source buffer and optimal destination allocations overlap (Anvil code -20001); nothing was recorded.")
      ProcedureReturn
    EndIf
    If priorPartialOp <> 0
      priorBytes = avkOpSourceBytes[priorPartialOp]
      If avkCopyBufferResolve(avkOpBuffer[priorPartialOp], d, avkOpBufferOffset[priorPartialOp], priorBytes, @priorSource) = 0
        avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdCopyBufferToImage lost the earlier partial upload source (Anvil code -20004); nothing was recorded.")
        ProcedureReturn
      EndIf
      If avkImageRowsOverlap(sourceBase, sourceBytes, sourceBytes, 1, priorSource, priorBytes, priorBytes, 1) <> 0
        avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyBufferToImage ordered partial source spans overlap (Anvil code -20001); nothing was recorded.")
        ProcedureReturn
      EndIf
    EndIf
    If gridOptimal <> 0
      gridCopy\windowBase = avkHeapBase : gridCopy\windowBytes = avkHeapBytes
      gridCopy\sourceBase = sourceBase : gridCopy\sourceBytes = sourceBytes : gridCopy\sourcePitch = bufferPitch
      gridCopy\sourceViewWidth = *r\imageExtent\width : gridCopy\sourceViewHeight = *r\imageExtent\height
      gridCopy\destinationBase = destinationBase : gridCopy\destinationBytes = avkImgSize[s]
      gridCopy\width = avkImgW[s] : gridCopy\height = avkImgH[s]
      gridCopy\destinationLayout = avkImgBackendLayout[s]
      gridCopy\paddedWidth = avkImgPaddedW[s] : gridCopy\paddedHeight = avkImgPaddedH[s]
      gridCopy\sourceX = 0 : gridCopy\sourceY = 0
      gridCopy\destinationX = *r\imageOffset\x : gridCopy\destinationY = *r\imageOffset\y
      gridCopy\regionWidth = *r\imageExtent\width : gridCopy\regionHeight = *r\imageExtent\height
      If avkBackendLinearTiledGridCopyValidate(@gridCopy) <> 0
        avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyBufferToImage grid upload failed per-tile DMA preflight (Anvil code -20005); nothing was recorded.")
        ProcedureReturn
      EndIf
    EndIf
  EndIf
  If avkImgTiling[s] = #VK_IMAGE_TILING_LINEAR
    destinationBase = avkHeapBase + avkMemOffset[avkImgMemSlot[s]] + avkImgMemOffset[s] + *r\imageOffset\y * avkImgPitch[s] + *r\imageOffset\x * #ANVIL_VK_BGRA8_TEXEL_BYTES
    If avkImageRowsOverlap(sourceBase, bufferPitch, sourcePitch, rows, destinationBase, avkImgPitch[s], sourcePitch, rows) <> 0
      avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyBufferToImage source and destination memory overlap (Anvil code -20001); no array region was recorded.")
      ProcedureReturn
    EndIf
    For j = 0 To i - 1
      *prior = *regions + j * SizeOf(VkBufferImageCopy)
      priorBytes = *prior\imageExtent\width * #ANVIL_VK_BGRA8_TEXEL_BYTES
      priorPitch = priorBytes
      If *prior\bufferRowLength <> 0 : priorPitch = *prior\bufferRowLength * #ANVIL_VK_BGRA8_TEXEL_BYTES : EndIf
      If avkCopyBufferResolve(srcBuffer, d, *prior\bufferOffset, (*prior\imageExtent\height - 1) * priorPitch + priorBytes, @priorSource) = 0
        avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdCopyBufferToImage lost an earlier source while validating the array (Anvil code -20004); nothing was recorded.")
        ProcedureReturn
      EndIf
      priorDestination = avkHeapBase + avkMemOffset[avkImgMemSlot[s]] + avkImgMemOffset[s] + *prior\imageOffset\y * avkImgPitch[s] + *prior\imageOffset\x * #ANVIL_VK_BGRA8_TEXEL_BYTES
      If avkImageRowsOverlap(sourceBase, bufferPitch, sourcePitch, rows, priorDestination, avkImgPitch[s], priorBytes, *prior\imageExtent\height) <> 0 Or avkImageRowsOverlap(priorSource, priorPitch, priorBytes, *prior\imageExtent\height, destinationBase, avkImgPitch[s], sourcePitch, rows) <> 0 Or avkImageRowsOverlap(destinationBase, avkImgPitch[s], sourcePitch, rows, priorDestination, avkImgPitch[s], priorBytes, *prior\imageExtent\height) <> 0
        avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyBufferToImage regions overlap source and destination memory or two destinations (Anvil code -20001); no array region was recorded.")
        ProcedureReturn
      EndIf
    Next
  EndIf
  Next
  k = avkCbRef(c, dstImage, s)
  If k < 0
    avkCbFail(c, #VK_ERROR_OUT_OF_HOST_MEMORY, "vkCmdCopyBufferToImage exceeded this command buffer's retained-image capacity (VkResult -1, VK_ERROR_OUT_OF_HOST_MEMORY); split the work across command buffers.")
    ProcedureReturn
  EndIf
  If avkRefClaim(c, k, dstImageLayout) = 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdCopyBufferToImage claims a destination layout that earlier commands in this recording did not leave (Anvil code -20004, layout mismatch); record the transfer-destination barrier first.")
    ProcedureReturn
  EndIf
  group = 0
  For i = 0 To regionCount - 1
    *r = *regions + i * SizeOf(VkBufferImageCopy)
    o = avkOpAppend(c, #ANVIL_VK_OP_COPY_BUFFER_IMAGE)
    If o = 0
      avkCbFail(c, #VK_ERROR_OUT_OF_HOST_MEMORY, "the command pool ran out of recorded-command storage while recording vkCmdCopyBufferToImage (VkResult -1); reset the invalid command buffer.")
      ProcedureReturn
    EndIf
    If group = 0 : group = o : EndIf
    avkOpCopyGroup[o] = group
    avkOpRef[o] = k
    avkOpOldLayout[o] = dstImageLayout
    avkOpNewLayout[o] = dstImageLayout
    avkOpBuffer[o] = srcBuffer
    avkOpBufferOffset[o] = *r\bufferOffset
    If avkImgTiling[s] = #VK_IMAGE_TILING_LINEAR
      avkOpDstOffset[o] = *r\imageOffset\y * avkImgPitch[s] + *r\imageOffset\x * #ANVIL_VK_BGRA8_TEXEL_BYTES
    ElseIf partialOptimal <> 0
      avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_RECT_TAG
      If microOptimal <> 0 : avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_MICRO_TAG : EndIf
      If gridOptimal <> 0 : avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_GRID_TAG : EndIf
      If gridWide <> 0 : avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_GRID_4X4_TAG : EndIf
      avkOpImageX[o] = *r\imageOffset\x : avkOpImageY[o] = *r\imageOffset\y
    EndIf
    avkOpSourcePitch[o] = *r\imageExtent\width * #ANVIL_VK_BGRA8_TEXEL_BYTES
    avkOpBufferPitch[o] = avkOpSourcePitch[o]
    If *r\bufferRowLength <> 0 : avkOpBufferPitch[o] = *r\bufferRowLength * #ANVIL_VK_BGRA8_TEXEL_BYTES : EndIf
    avkOpRows[o] = *r\imageExtent\height
    avkOpSourceBytes[o] = (avkOpRows[o] - 1) * avkOpBufferPitch[o] + avkOpSourcePitch[o]
  Next
EndProcedure

; Two monotone row-interval streams overlap if any pair of byte intervals
; intersects. Image strides can differ, and distinct handles can alias memory.
Procedure.i avkImageRowsOverlap(a.i, aPitch.i, aBytes.i, aRows.i, b.i, bPitch.i, bBytes.i, bRows.i)
  Define ai.i = 0, bi.i = 0, ar.i, br.i
  While ai < aRows And bi < bRows
    ar = a + ai * aPitch
    br = b + bi * bPitch
    If ar < br + bBytes And br < ar + aBytes : ProcedureReturn 1 : EndIf
    If ar + aBytes <= br
      ai = ai + 1
    Else
      bi = bi + 1
    EndIf
  Wend
  ProcedureReturn 0
EndProcedure

; A complete bounded VkImageCopy array is validated before recording.
; Linear rectangles use guarded DMA; whole-image optimal transfers use TFU
; for tiled destinations. Partial linear-to-optimal and optimal-to-linear
; rectangles use guarded 2D DMA.
; The stream is preflighted before submission writes any image byte.
Procedure AnvilVkCmdCopyImage(commandBuffer.i, srcImage.i, srcLayout.i, dstImage.i, dstLayout.i, regionCount.i, *regions.VkImageCopy)
  Define c.i, d.i, src.i, dst.i, srcRef.i, dstRef.i, o.i, i.i, j.i, freeOps.i, group.i
  Define rowBytes.i, rows.i, srcOffset.i, dstOffset.i
  Define sourceBase.i, destinationBase.i, priorSource.i, priorDestination.i
  Define partialRead.i, partialTiled.i, partialLinearTiled.i, microTiled.i, microLinear.i, microLinearTiled.i, tailTiled.i
  Define edgeCopy.AnvilVkBackendTiledRectCopy
  Define *r.VkImageCopy, *prior.VkImageCopy
  c = avkCmdSlot(commandBuffer)
  If c = 0
    avkFault(#ANVIL_VK_ERR_HANDLE, "vkCmdCopyImage was given a stale command buffer (Anvil code -20002); nothing was recorded.")
    ProcedureReturn
  EndIf
  If avkCmdState[c] <> #ANVIL_VK_CB_RECORDING Or avkCbRpActive[c] <> 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdCopyImage requires a recording command buffer outside a render pass (Anvil code -20004); no copy was recorded.")
    ProcedureReturn
  EndIf
  If regionCount < 1 Or regionCount > #ANVIL_VK_MAX_OPS Or *regions = 0
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyImage requires one to thirty-two VkImageCopy regions and a non-null array (Anvil code -20001); no copy was recorded.")
    ProcedureReturn
  EndIf
  freeOps = 0
  For o = 1 To #ANVIL_VK_MAX_OPS
    If avkOpLive[o] = 0 : freeOps = freeOps + 1 : EndIf
  Next
  If freeOps < regionCount
    avkCbFail(c, #VK_ERROR_OUT_OF_HOST_MEMORY, "vkCmdCopyImage cannot retain every region in the shared command pool (VkResult -1); reset unused command buffers.")
    ProcedureReturn
  EndIf
  o = avkCbOpHead[c]
  While o <> 0
    If avkOpKind[o] = #ANVIL_VK_OP_COPY_IMAGE And (avkOpRows[o] = 4 Or avkOpRows[o] = 5 Or avkOpRows[o] = 6)
      avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyImage keeps a one-utile image micro copy in its own command buffer (Anvil code -20005); nothing was recorded.")
      ProcedureReturn
    EndIf
    o = avkOpNext[o]
  Wend
  src = avkImgSlot(srcImage)
  dst = avkImgSlot(dstImage)
  If src = 0 Or dst = 0
    avkCbFail(c, #ANVIL_VK_ERR_HANDLE, "vkCmdCopyImage requires live image handles (Anvil code -20002); no copy was recorded.")
    ProcedureReturn
  EndIf
  d = avkPoolDev[avkCmdPool[c]]
  If avkImgDev[src] <> d Or avkImgDev[dst] <> d
    avkCbFail(c, #ANVIL_VK_ERR_OWNER, "vkCmdCopyImage requires both images to belong to the command buffer's device (Anvil code -20003); no copy was recorded.")
    ProcedureReturn
  EndIf
  If avkImgBound[src] = 0 Or avkImgBound[dst] = 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdCopyImage requires bound source and destination images (Anvil code -20004); no copy was recorded.")
    ProcedureReturn
  EndIf
  If (avkImgTiling[src] <> #VK_IMAGE_TILING_LINEAR And avkImgTiling[src] <> #VK_IMAGE_TILING_OPTIMAL) Or (avkImgTiling[dst] <> #VK_IMAGE_TILING_LINEAR And avkImgTiling[dst] <> #VK_IMAGE_TILING_OPTIMAL)
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyImage requires linear or optimal BGRA8 images (Anvil code -20005); no copy was recorded.")
    ProcedureReturn
  EndIf
  If avkImgTiling[dst] = #VK_IMAGE_TILING_LINEAR And (avkBackendCaps() & #ANVIL_VK_CAP_LINEAR_TRANSFER) = 0
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyImage requires a backend that executes copies into linear images (Anvil code -20005, unsupported transfer); choose a device with linear transfer support.")
    ProcedureReturn
  EndIf
  If (avkImgUsage[src] & #VK_IMAGE_USAGE_TRANSFER_SRC_BIT) = 0 Or (avkImgUsage[dst] & #VK_IMAGE_USAGE_TRANSFER_DST_BIT) = 0
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyImage requires TRANSFER_SRC usage on the source and TRANSFER_DST usage on the destination (Anvil code -20001); no copy was recorded.")
    ProcedureReturn
  EndIf
  If Not (srcLayout = #VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL Or srcLayout = #VK_IMAGE_LAYOUT_GENERAL) Or Not (dstLayout = #VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL Or dstLayout = #VK_IMAGE_LAYOUT_GENERAL)
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyImage requires a transfer-source or GENERAL source layout and a transfer-destination or GENERAL destination layout (Anvil code -20001); no copy was recorded.")
    ProcedureReturn
  EndIf
  If srcImage = dstImage And (srcLayout <> #VK_IMAGE_LAYOUT_GENERAL Or dstLayout <> #VK_IMAGE_LAYOUT_GENERAL)
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyImage requires GENERAL layout for both roles when copying within one image (Anvil code -20001); no copy was recorded.")
    ProcedureReturn
  EndIf
  If avkImgTiling[src] = #VK_IMAGE_TILING_OPTIMAL Or avkImgTiling[dst] = #VK_IMAGE_TILING_OPTIMAL
    *r = *regions
    partialRead = Bool(avkImgTiling[src] = #VK_IMAGE_TILING_OPTIMAL And avkImgTiling[dst] = #VK_IMAGE_TILING_LINEAR)
    partialTiled = Bool(avkImgTiling[src] = #VK_IMAGE_TILING_OPTIMAL And avkImgTiling[dst] = #VK_IMAGE_TILING_OPTIMAL And (*r\srcOffset\x <> 0 Or *r\srcOffset\y <> 0 Or *r\dstOffset\x <> 0 Or *r\dstOffset\y <> 0 Or *r\extent\width <> avkImgW[src] Or *r\extent\height <> avkImgH[src]))
    microTiled = Bool(partialTiled <> 0 And *r\srcOffset\x >= 0 And *r\srcOffset\y >= 0 And *r\dstOffset\x >= 0 And *r\dstOffset\y >= 0 And *r\extent\width >= 1 And *r\extent\width <= 4 And *r\extent\height >= 1 And *r\extent\height <= 4 And (*r\srcOffset\x % 4) + *r\extent\width <= 4 And (*r\srcOffset\y % 4) + *r\extent\height <= 4 And (*r\dstOffset\x % 4) + *r\extent\width <= 4 And (*r\dstOffset\y % 4) + *r\extent\height <= 4 And ((*r\srcOffset\x % 4) <> 0 Or (*r\srcOffset\y % 4) <> 0 Or (*r\dstOffset\x % 4) <> 0 Or (*r\dstOffset\y % 4) <> 0 Or *r\extent\width <> 4 Or *r\extent\height <> 4))
    tailTiled = Bool(partialTiled <> 0 And microTiled = 0 And ((*r\extent\width % 4) <> 0 Or (*r\extent\height % 4) <> 0))
    partialLinearTiled = Bool(avkImgTiling[src] = #VK_IMAGE_TILING_LINEAR And avkImgTiling[dst] = #VK_IMAGE_TILING_OPTIMAL And (*r\srcOffset\x <> 0 Or *r\srcOffset\y <> 0 Or *r\dstOffset\x <> 0 Or *r\dstOffset\y <> 0 Or *r\extent\width <> avkImgW[src] Or *r\extent\height <> avkImgH[src]))
    microLinearTiled = Bool(partialLinearTiled <> 0 And *r\dstOffset\x >= 0 And *r\dstOffset\y >= 0 And *r\extent\width >= 1 And *r\extent\width <= 4 And *r\extent\height >= 1 And *r\extent\height <= 4 And (*r\dstOffset\x % 4) + *r\extent\width <= 4 And (*r\dstOffset\y % 4) + *r\extent\height <= 4 And ((*r\dstOffset\x % 4) <> 0 Or (*r\dstOffset\y % 4) <> 0 Or *r\extent\width <> 4 Or *r\extent\height <> 4))
    If regionCount <> 1 Or srcImage = dstImage Or avkImgW[src] <> avkImgW[dst] Or avkImgH[src] <> avkImgH[dst] Or (avkImgTiling[src] = #VK_IMAGE_TILING_OPTIMAL And avkImgBackendLayout[src] = 0) Or (avkImgTiling[dst] = #VK_IMAGE_TILING_OPTIMAL And avkImgBackendLayout[dst] = 0) Or (avkImgTiling[src] = #VK_IMAGE_TILING_OPTIMAL And avkImgTiling[dst] = #VK_IMAGE_TILING_OPTIMAL And (avkImgBackendLayout[src] <> avkImgBackendLayout[dst] Or avkImgPaddedW[src] <> avkImgPaddedW[dst] Or avkImgPaddedH[src] <> avkImgPaddedH[dst] Or avkImgSize[src] <> avkImgSize[dst]))
      avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyImage requires one region between distinct compatible images when either image is optimal-tiled (Anvil code -20005); nothing was recorded.")
      ProcedureReturn
    EndIf
    If avkImgTiling[src] = #VK_IMAGE_TILING_LINEAR And (avkImgPitch[src] < avkImgW[src] * #ANVIL_VK_BGRA8_TEXEL_BYTES Or (avkImgPitch[src] % #ANVIL_VK_BGRA8_TEXEL_BYTES) <> 0 Or avkImgSize[src] < avkImgPitch[src] * avkImgH[src])
      avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdCopyImage found an invalid linear source pitch or allocation for the TFU (Anvil code -20004); nothing was recorded.")
      ProcedureReturn
    EndIf
    If avkImgTiling[dst] = #VK_IMAGE_TILING_LINEAR And (avkImgPitch[dst] < avkImgW[dst] * #ANVIL_VK_BGRA8_TEXEL_BYTES Or (avkImgPitch[dst] % #ANVIL_VK_BGRA8_TEXEL_BYTES) <> 0 Or avkImgSize[dst] < avkImgPitch[dst] * avkImgH[dst])
      avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdCopyImage found an invalid linear destination pitch or allocation for tiled readback (Anvil code -20004); nothing was recorded.")
      ProcedureReturn
    EndIf
    If *r\srcSubresource\aspectMask <> #VK_IMAGE_ASPECT_COLOR_BIT Or *r\dstSubresource\aspectMask <> #VK_IMAGE_ASPECT_COLOR_BIT Or *r\srcSubresource\mipLevel <> 0 Or *r\dstSubresource\mipLevel <> 0 Or *r\srcSubresource\baseArrayLayer <> 0 Or *r\dstSubresource\baseArrayLayer <> 0 Or *r\srcSubresource\layerCount <> 1 Or *r\dstSubresource\layerCount <> 1 Or *r\srcOffset\z <> 0 Or *r\dstOffset\z <> 0 Or *r\extent\depth <> 1
      avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyImage requires colour mip zero and layer zero for an optimal-image transfer (Anvil code -20005); nothing was recorded.")
      ProcedureReturn
    EndIf
    If partialRead <> 0
      If *r\srcOffset\x < 0 Or *r\srcOffset\y < 0 Or *r\dstOffset\x < 0 Or *r\dstOffset\y < 0 Or *r\extent\width < 1 Or *r\extent\height < 1 Or *r\srcOffset\x > avkImgW[src] - *r\extent\width Or *r\srcOffset\y > avkImgH[src] - *r\extent\height Or *r\dstOffset\x > avkImgW[dst] - *r\extent\width Or *r\dstOffset\y > avkImgH[dst] - *r\extent\height
        avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyImage optimal-to-linear rectangle must fit both image extents (Anvil code -20001); nothing was recorded.")
        ProcedureReturn
      EndIf
      microLinear = Bool(*r\extent\width <= 4 And *r\extent\height <= 4 And (*r\srcOffset\x % 4) + *r\extent\width <= 4 And (*r\srcOffset\y % 4) + *r\extent\height <= 4 And ((*r\srcOffset\x % 4) <> 0 Or (*r\srcOffset\y % 4) <> 0 Or ((*r\extent\width % 4) <> 0 And *r\srcOffset\x <> avkImgW[src] - *r\extent\width) Or ((*r\extent\height % 4) <> 0 And *r\srcOffset\y <> avkImgH[src] - *r\extent\height)))
      If microLinear <> 0 And (avkBackendCaps() & #ANVIL_VK_CAP_TILED_TO_LINEAR_MICRO_COPY) = 0
        avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyImage optimal-to-linear one-utile micro copy requires its dedicated backend capability (Anvil code -20005); nothing was recorded.")
        ProcedureReturn
      EndIf
      If microLinear = 0 And ((*r\srcOffset\x % 4) <> 0 Or (*r\srcOffset\y % 4) <> 0 Or ((*r\extent\width % 4) <> 0 And *r\srcOffset\x <> avkImgW[src] - *r\extent\width) Or ((*r\extent\height % 4) <> 0 And *r\srcOffset\y <> avkImgH[src] - *r\extent\height))
        avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyImage optimal-to-linear source requires four-texel-aligned offsets and only right/bottom edge tails (Anvil code -20005); nothing was recorded.")
        ProcedureReturn
      EndIf
      If microLinear <> 0
        i = avkCbOpHead[c]
        While i <> 0
          If avkOpKind[i] = #ANVIL_VK_OP_COPY_IMAGE
            avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyImage keeps an optimal-to-linear one-utile micro copy in its own command buffer (Anvil code -20005); nothing was recorded.")
            ProcedureReturn
          EndIf
          i = avkOpNext[i]
        Wend
      EndIf
      rowBytes = *r\extent\width * #ANVIL_VK_BGRA8_TEXEL_BYTES
      rows = *r\extent\height
      dstOffset = *r\dstOffset\y * avkImgPitch[dst] + *r\dstOffset\x * #ANVIL_VK_BGRA8_TEXEL_BYTES
      If rowBytes > avkImgPitch[dst] Or dstOffset + (rows - 1) * avkImgPitch[dst] + rowBytes > avkImgSize[dst] Or (microLinear <> 0 And avkImgPitch[dst] - rowBytes > 32767)
        avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdCopyImage optimal-to-linear destination rows exceed its allocation (Anvil code -20004); nothing was recorded.")
        ProcedureReturn
      EndIf
    ElseIf partialTiled <> 0
      If (avkBackendCaps() & #ANVIL_VK_CAP_TILED_RECT_COPY) = 0
        avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyImage partial optimal-to-optimal copy requires a tiled-rectangle backend (Anvil code -20005); nothing was recorded.")
        ProcedureReturn
      EndIf
      If microTiled <> 0 And (avkBackendCaps() & #ANVIL_VK_CAP_TILED_MICRO_COPY) = 0
        avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyImage one-utile optimal copy requires the dedicated micro backend capability (Anvil code -20005); nothing was recorded.")
        ProcedureReturn
      EndIf
      If tailTiled <> 0 And (avkBackendCaps() & #ANVIL_VK_CAP_TILED_EDGE_TAIL_COPY) = 0
        avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyImage short optimal-image edge tiles require their dedicated backend capability (Anvil code -20005); nothing was recorded.")
        ProcedureReturn
      EndIf
      If tailTiled <> 0 And avkCbOpHead[c] <> 0
        avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyImage keeps an optimal-image edge-tail copy in its own command buffer (Anvil code -20005); nothing was recorded.")
        ProcedureReturn
      EndIf
      i = avkCbOpHead[c]
      While i <> 0
        If avkOpKind[i] = #ANVIL_VK_OP_COPY_IMAGE And (avkOpRows[i] = 1 Or avkOpRows[i] = 3 Or avkOpRows[i] = 6 Or microTiled <> 0 Or tailTiled <> 0)
          avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyImage supports one partial optimal-to-optimal rectangle per command buffer (Anvil code -20005); nothing was recorded.")
          ProcedureReturn
        EndIf
        i = avkOpNext[i]
      Wend
      If *r\srcOffset\x < 0 Or *r\srcOffset\y < 0 Or *r\dstOffset\x < 0 Or *r\dstOffset\y < 0 Or *r\extent\width < 1 Or *r\extent\height < 1 Or *r\srcOffset\x > avkImgW[src] - *r\extent\width Or *r\srcOffset\y > avkImgH[src] - *r\extent\height Or *r\dstOffset\x > avkImgW[dst] - *r\extent\width Or *r\dstOffset\y > avkImgH[dst] - *r\extent\height
        avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyImage partial optimal rectangles must fit both images (Anvil code -20001); nothing was recorded.")
        ProcedureReturn
      EndIf
      If tailTiled <> 0 And (((*r\extent\width % 4) <> 0 And (*r\srcOffset\x <> avkImgW[src] - *r\extent\width Or *r\dstOffset\x <> avkImgW[dst] - *r\extent\width)) Or ((*r\extent\height % 4) <> 0 And (*r\srcOffset\y <> avkImgH[src] - *r\extent\height Or *r\dstOffset\y <> avkImgH[dst] - *r\extent\height)))
        avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyImage short optimal-image tiles must reach both corresponding image edges (Anvil code -20005); nothing was recorded.")
        ProcedureReturn
      EndIf
      If microTiled = 0 And ((*r\srcOffset\x % 4) <> 0 Or (*r\srcOffset\y % 4) <> 0 Or (*r\dstOffset\x % 4) <> 0 Or (*r\dstOffset\y % 4) <> 0 Or (tailTiled = 0 And ((*r\extent\width % 4) <> 0 Or (*r\extent\height % 4) <> 0)) Or ((*r\extent\width - 1) / 4 + 1) * ((*r\extent\height - 1) / 4 + 1) > #ANVIL_VK_TILED_RECT_MAX_UTILES)
        avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyImage partial optimal rectangles require at most 256 complete aligned 4x4 tiles (Anvil code -20005); nothing was recorded.")
        ProcedureReturn
      EndIf
    ElseIf partialLinearTiled <> 0
      If (avkBackendCaps() & #ANVIL_VK_CAP_LINEAR_TO_TILED_RECT_COPY) = 0
        avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyImage partial linear-to-optimal copy requires a linear-to-tiled backend (Anvil code -20005); nothing was recorded.")
        ProcedureReturn
      EndIf
      If microLinearTiled <> 0 And (avkBackendCaps() & (#ANVIL_VK_CAP_LINEAR_TRANSFER | #ANVIL_VK_CAP_LINEAR_TO_TILED_MICRO_COPY)) <> (#ANVIL_VK_CAP_LINEAR_TRANSFER | #ANVIL_VK_CAP_LINEAR_TO_TILED_MICRO_COPY)
        avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyImage linear-to-optimal one-utile micro copy requires its dedicated backend capability (Anvil code -20005); nothing was recorded.")
        ProcedureReturn
      EndIf
      i = avkCbOpHead[c]
      While i <> 0
        If avkOpKind[i] = #ANVIL_VK_OP_COPY_IMAGE And (avkOpRows[i] = 2 Or avkOpRows[i] = 5 Or microLinearTiled <> 0)
          avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyImage supports one partial linear-to-optimal rectangle per command buffer (Anvil code -20005); nothing was recorded.")
          ProcedureReturn
        EndIf
        i = avkOpNext[i]
      Wend
      If *r\srcOffset\x < 0 Or *r\srcOffset\y < 0 Or *r\dstOffset\x < 0 Or *r\dstOffset\y < 0 Or *r\extent\width < 1 Or *r\extent\height < 1 Or *r\srcOffset\x > avkImgW[src] - *r\extent\width Or *r\srcOffset\y > avkImgH[src] - *r\extent\height Or *r\dstOffset\x > avkImgW[dst] - *r\extent\width Or *r\dstOffset\y > avkImgH[dst] - *r\extent\height
        avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyImage partial linear-to-optimal rectangle must fit both images (Anvil code -20001); nothing was recorded.")
        ProcedureReturn
      EndIf
      If microLinearTiled = 0 And ((*r\dstOffset\x % 4) <> 0 Or (*r\dstOffset\y % 4) <> 0 Or (*r\extent\width % 4) <> 0 Or (*r\extent\height % 4) <> 0 Or (*r\extent\width / 4) * (*r\extent\height / 4) > #ANVIL_VK_TILED_RECT_MAX_UTILES)
        avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyImage partial linear-to-optimal rectangles require at most 256 complete aligned destination tiles (Anvil code -20005); nothing was recorded.")
        ProcedureReturn
      EndIf
      rowBytes = *r\extent\width * 4
      srcOffset = *r\srcOffset\y * avkImgPitch[src] + *r\srcOffset\x * 4
      If (microLinearTiled <> 0 And avkImgPitch[src] - rowBytes > 32767) Or (microLinearTiled = 0 And avkImgPitch[src] - 16 > 32767) Or srcOffset + (*r\extent\height - 1) * avkImgPitch[src] + rowBytes > avkImgSize[src]
        avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdCopyImage partial linear source rows exceed its allocation or DMA stride (Anvil code -20004); nothing was recorded.")
        ProcedureReturn
      EndIf
    ElseIf *r\srcOffset\x <> 0 Or *r\srcOffset\y <> 0 Or *r\dstOffset\x <> 0 Or *r\dstOffset\y <> 0 Or *r\extent\width <> avkImgW[src] Or *r\extent\height <> avkImgH[src]
      avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyImage requires the complete level-zero colour subresource for this optimal-image transfer (Anvil code -20005); nothing was recorded.")
      ProcedureReturn
    EndIf
    sourceBase = avkHeapBase + avkMemOffset[avkImgMemSlot[src]] + avkImgMemOffset[src]
    destinationBase = avkHeapBase + avkMemOffset[avkImgMemSlot[dst]] + avkImgMemOffset[dst]
    If avkImageRowsOverlap(sourceBase, avkImgSize[src], avkImgSize[src], 1, destinationBase, avkImgSize[dst], avkImgSize[dst], 1) <> 0
      avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyImage source and destination allocations overlap (Anvil code -20001); no copy was recorded.")
      ProcedureReturn
    EndIf
    If tailTiled <> 0
      edgeCopy\windowBase = avkHeapBase : edgeCopy\windowBytes = avkHeapBytes
      edgeCopy\sourceBase = sourceBase : edgeCopy\sourceBytes = avkImgSize[src]
      edgeCopy\destinationBase = destinationBase : edgeCopy\destinationBytes = avkImgSize[dst]
      edgeCopy\width = avkImgW[src] : edgeCopy\height = avkImgH[src]
      edgeCopy\sourceLayout = avkImgBackendLayout[src] : edgeCopy\destinationLayout = avkImgBackendLayout[dst]
      edgeCopy\paddedWidth = avkImgPaddedW[src] : edgeCopy\paddedHeight = avkImgPaddedH[src]
      edgeCopy\sourceX = *r\srcOffset\x : edgeCopy\sourceY = *r\srcOffset\y
      edgeCopy\destinationX = *r\dstOffset\x : edgeCopy\destinationY = *r\dstOffset\y
      edgeCopy\regionWidth = *r\extent\width : edgeCopy\regionHeight = *r\extent\height
      If avkBackendTiledEdgeTailCopyValidate(@edgeCopy) <> 0
        avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyImage short optimal-image tiles failed complete DMA preflight (Anvil code -20005); nothing was recorded.")
        ProcedureReturn
      EndIf
    EndIf
    srcRef = avkCbRef(c, srcImage, src)
    dstRef = avkCbRef(c, dstImage, dst)
    If srcRef < 0 Or dstRef < 0
      avkCbFail(c, #VK_ERROR_OUT_OF_HOST_MEMORY, "vkCmdCopyImage exceeded the command buffer's image-reference capacity (VkResult -1); split the work across command buffers.")
      ProcedureReturn
    EndIf
    If avkRefClaim(c, srcRef, srcLayout) = 0 Or avkRefClaim(c, dstRef, dstLayout) = 0
      avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdCopyImage optimal-image layouts disagree with earlier commands (Anvil code -20004); transition both images first.")
      ProcedureReturn
    EndIf
    o = avkOpAppend(c, #ANVIL_VK_OP_COPY_IMAGE)
    If o = 0
      avkCbFail(c, #VK_ERROR_OUT_OF_HOST_MEMORY, "vkCmdCopyImage exhausted recorded-command storage (VkResult -1); reset the invalid command buffer.")
      ProcedureReturn
    EndIf
    avkOpCopyGroup[o] = o
    avkOpRef[o] = srcRef : avkOpDstRef[o] = dstRef
    If partialRead <> 0
      If microLinear <> 0 : avkOpRows[o] = 4 : EndIf
      avkOpImageX[o] = *r\srcOffset\x : avkOpImageY[o] = *r\srcOffset\y
      avkOpBufferOffset[o] = *r\dstOffset\x : avkOpBufferPitch[o] = *r\dstOffset\y
      avkOpDstOffset[o] = *r\dstOffset\y * avkImgPitch[dst] + *r\dstOffset\x * #ANVIL_VK_BGRA8_TEXEL_BYTES
      avkOpSourceBytes[o] = *r\extent\width * #ANVIL_VK_BGRA8_TEXEL_BYTES
      avkOpSourcePitch[o] = *r\extent\height
    ElseIf partialTiled <> 0
      avkOpRows[o] = 1
      If microTiled <> 0 : avkOpRows[o] = 3 : EndIf
      If tailTiled <> 0 : avkOpRows[o] = 6 : EndIf
      avkOpImageX[o] = *r\srcOffset\x : avkOpImageY[o] = *r\srcOffset\y
      avkOpBufferOffset[o] = *r\dstOffset\x : avkOpBufferPitch[o] = *r\dstOffset\y
      avkOpSourceBytes[o] = *r\extent\width * #ANVIL_VK_BGRA8_TEXEL_BYTES
      avkOpSourcePitch[o] = *r\extent\height
    ElseIf partialLinearTiled <> 0
      avkOpRows[o] = 2
      If microLinearTiled <> 0 : avkOpRows[o] = 5 : EndIf
      avkOpImageX[o] = *r\srcOffset\x : avkOpImageY[o] = *r\srcOffset\y
      avkOpBufferOffset[o] = *r\dstOffset\x : avkOpBufferPitch[o] = *r\dstOffset\y
      avkOpSourceBytes[o] = *r\extent\width * 4
      avkOpSourcePitch[o] = *r\extent\height
    Else
      avkOpSourceBytes[o] = avkImgSize[src]
      avkOpSourcePitch[o] = avkImgH[src]
    EndIf
    ProcedureReturn
  EndIf
  For i = 0 To regionCount - 1
  *r = *regions + i * SizeOf(VkImageCopy)
  If *r\srcSubresource\aspectMask <> #VK_IMAGE_ASPECT_COLOR_BIT Or *r\dstSubresource\aspectMask <> #VK_IMAGE_ASPECT_COLOR_BIT Or *r\srcSubresource\mipLevel <> 0 Or *r\dstSubresource\mipLevel <> 0 Or *r\srcSubresource\baseArrayLayer <> 0 Or *r\dstSubresource\baseArrayLayer <> 0 Or *r\srcSubresource\layerCount <> 1 Or *r\dstSubresource\layerCount <> 1
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyImage supports only the complete colour subresource at mip zero and layer zero (Anvil code -20005); no copy was recorded.")
    ProcedureReturn
  EndIf
  If *r\srcOffset\x < 0 Or *r\srcOffset\y < 0 Or *r\srcOffset\z <> 0 Or *r\dstOffset\x < 0 Or *r\dstOffset\y < 0 Or *r\dstOffset\z <> 0 Or *r\extent\width < 1 Or *r\extent\height < 1 Or *r\extent\depth <> 1
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyImage requires a positive two-dimensional region with non-negative XY offsets and zero Z offsets (Anvil code -20001); no copy was recorded.")
    ProcedureReturn
  EndIf
  If *r\srcOffset\x > avkImgW[src] - *r\extent\width Or *r\srcOffset\y > avkImgH[src] - *r\extent\height Or *r\dstOffset\x > avkImgW[dst] - *r\extent\width Or *r\dstOffset\y > avkImgH[dst] - *r\extent\height
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyImage requires the complete rectangle to fit both image extents (Anvil code -20001); no copy was recorded.")
    ProcedureReturn
  EndIf
  rowBytes = *r\extent\width * #ANVIL_VK_BGRA8_TEXEL_BYTES
  rows = *r\extent\height
  srcOffset = *r\srcOffset\y * avkImgPitch[src] + *r\srcOffset\x * #ANVIL_VK_BGRA8_TEXEL_BYTES
  dstOffset = *r\dstOffset\y * avkImgPitch[dst] + *r\dstOffset\x * #ANVIL_VK_BGRA8_TEXEL_BYTES
  If rowBytes < 1 Or rowBytes > avkImgPitch[src] Or rowBytes > avkImgPitch[dst] Or srcOffset + (rows - 1) * avkImgPitch[src] + rowBytes > avkImgSize[src] Or dstOffset + (rows - 1) * avkImgPitch[dst] + rowBytes > avkImgSize[dst]
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdCopyImage found an image pitch or allocation too short for the requested rows (Anvil code -20004); no copy was recorded.")
    ProcedureReturn
  EndIf
  sourceBase = avkHeapBase + avkMemOffset[avkImgMemSlot[src]] + avkImgMemOffset[src] + srcOffset
  destinationBase = avkHeapBase + avkMemOffset[avkImgMemSlot[dst]] + avkImgMemOffset[dst] + dstOffset
  If avkImageRowsOverlap(sourceBase, avkImgPitch[src], rowBytes, rows, destinationBase, avkImgPitch[dst], rowBytes, rows)
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyImage source and destination texels overlap (Anvil code -20001); no array region was recorded.")
    ProcedureReturn
  EndIf
  For j = 0 To i - 1
    *prior = *regions + j * SizeOf(VkImageCopy)
    priorSource = avkHeapBase + avkMemOffset[avkImgMemSlot[src]] + avkImgMemOffset[src] + *prior\srcOffset\y * avkImgPitch[src] + *prior\srcOffset\x * #ANVIL_VK_BGRA8_TEXEL_BYTES
    priorDestination = avkHeapBase + avkMemOffset[avkImgMemSlot[dst]] + avkImgMemOffset[dst] + *prior\dstOffset\y * avkImgPitch[dst] + *prior\dstOffset\x * #ANVIL_VK_BGRA8_TEXEL_BYTES
    If avkImageRowsOverlap(sourceBase, avkImgPitch[src], rowBytes, rows, priorDestination, avkImgPitch[dst], *prior\extent\width * #ANVIL_VK_BGRA8_TEXEL_BYTES, *prior\extent\height) <> 0 Or avkImageRowsOverlap(destinationBase, avkImgPitch[dst], rowBytes, rows, priorSource, avkImgPitch[src], *prior\extent\width * #ANVIL_VK_BGRA8_TEXEL_BYTES, *prior\extent\height) <> 0
      avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyImage has a source region overlapping a destination region in the same call (Anvil code -20001); no array region was recorded.")
      ProcedureReturn
    EndIf
    If avkImageRowsOverlap(destinationBase, avkImgPitch[dst], rowBytes, rows, priorDestination, avkImgPitch[dst], *prior\extent\width * #ANVIL_VK_BGRA8_TEXEL_BYTES, *prior\extent\height)
      avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyImage has two overlapping destination regions (Anvil code -20001); no array region was recorded.")
      ProcedureReturn
    EndIf
  Next
  Next
  srcRef = avkCbRef(c, srcImage, src)
  dstRef = avkCbRef(c, dstImage, dst)
  If srcRef < 0 Or dstRef < 0
    avkCbFail(c, #VK_ERROR_OUT_OF_HOST_MEMORY, "vkCmdCopyImage exceeded the command buffer's two-image reference capacity (VkResult -1); split the work across command buffers.")
    ProcedureReturn
  EndIf
  If avkRefClaim(c, srcRef, srcLayout) = 0 Or avkRefClaim(c, dstRef, dstLayout) = 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdCopyImage layouts disagree with earlier commands in this recording (Anvil code -20004); transition both images before copying.")
    ProcedureReturn
  EndIf
  group = 0
  For i = 0 To regionCount - 1
    *r = *regions + i * SizeOf(VkImageCopy)
    o = avkOpAppend(c, #ANVIL_VK_OP_COPY_IMAGE)
    If o = 0
      avkCbFail(c, #VK_ERROR_OUT_OF_HOST_MEMORY, "vkCmdCopyImage exhausted recorded-command storage (VkResult -1); reset the invalid command buffer.")
      ProcedureReturn
    EndIf
    If group = 0 : group = o : EndIf
    avkOpCopyGroup[o] = group
    avkOpRef[o] = srcRef
    avkOpDstRef[o] = dstRef
    avkOpBufferOffset[o] = *r\srcOffset\y * avkImgPitch[src] + *r\srcOffset\x * #ANVIL_VK_BGRA8_TEXEL_BYTES
    avkOpDstOffset[o] = *r\dstOffset\y * avkImgPitch[dst] + *r\dstOffset\x * #ANVIL_VK_BGRA8_TEXEL_BYTES
    avkOpSourceBytes[o] = *r\extent\width * #ANVIL_VK_BGRA8_TEXEL_BYTES
    avkOpSourcePitch[o] = *r\extent\height
  Next
EndProcedure

; Rectangular linear-image readbacks and one optimal-image readback use guarded
; DMA on Pi 4. Optimal partial regions start on 4-texel boundaries; a short
; final utile may reach the image's right or bottom edge. Preflight all regions.
Procedure AnvilVkCmdCopyImageToBuffer(commandBuffer.i, srcImage.i, srcLayout.i, dstBuffer.i, regionCount.i, *regions.VkBufferImageCopy)
  Define c.i, d.i, src.i, ref.i, o.i, i.i, j.i, freeOps.i, group.i
  Define rowBytes.i, rows.i, sourceOffset.i, bytes.i, bufferPitch.i
  Define microReadback.i, bufferBase.i, bufferBytes.i
  Define sourceBase.i, destinationBase.i, priorSource.i, priorDestination.i
  Define priorBytes.i, priorPitch.i
  Define *r.VkBufferImageCopy, *prior.VkBufferImageCopy
  c = avkCmdSlot(commandBuffer)
  If c = 0
    avkFault(#ANVIL_VK_ERR_HANDLE, "vkCmdCopyImageToBuffer was given a stale command buffer (Anvil code -20002); nothing was recorded.")
    ProcedureReturn
  EndIf
  If avkCmdState[c] <> #ANVIL_VK_CB_RECORDING Or avkCbRpActive[c] <> 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdCopyImageToBuffer requires a recording command buffer outside a render pass (Anvil code -20004); nothing was recorded.")
    ProcedureReturn
  EndIf
  If regionCount < 1 Or regionCount > #ANVIL_VK_MAX_OPS Or *regions = 0
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyImageToBuffer requires one to thirty-two non-null regions (Anvil code -20001); nothing was recorded.")
    ProcedureReturn
  EndIf
  freeOps = 0
  For o = 1 To #ANVIL_VK_MAX_OPS
    If avkOpLive[o] = 0 : freeOps = freeOps + 1 : EndIf
  Next
  If freeOps < regionCount
    avkCbFail(c, #VK_ERROR_OUT_OF_HOST_MEMORY, "vkCmdCopyImageToBuffer cannot retain every region in the shared command pool (VkResult -1); reset unused command buffers.")
    ProcedureReturn
  EndIf
  src = avkImgSlot(srcImage)
  If src = 0
    avkCbFail(c, #ANVIL_VK_ERR_HANDLE, "vkCmdCopyImageToBuffer requires a live source image (Anvil code -20002); nothing was recorded.")
    ProcedureReturn
  EndIf
  d = avkPoolDev[avkCmdPool[c]]
  If avkImgDev[src] <> d Or avkImgBound[src] = 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdCopyImageToBuffer requires a bound image owned by the command buffer's device (Anvil code -20004); nothing was recorded.")
    ProcedureReturn
  EndIf
  If (avkImgTiling[src] <> #VK_IMAGE_TILING_LINEAR And avkImgTiling[src] <> #VK_IMAGE_TILING_OPTIMAL) Or (avkImgUsage[src] & #VK_IMAGE_USAGE_TRANSFER_SRC_BIT) = 0
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyImageToBuffer requires a supported source with TRANSFER_SRC usage (Anvil code -20005); nothing was recorded.")
    ProcedureReturn
  EndIf
  If (avkBackendCaps() & #ANVIL_VK_CAP_LINEAR_TRANSFER) = 0
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyImageToBuffer requires a backend that executes image readback (Anvil code -20005, unsupported transfer); choose a device with linear transfer support.")
    ProcedureReturn
  EndIf
  If srcLayout <> #VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL And srcLayout <> #VK_IMAGE_LAYOUT_GENERAL
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyImageToBuffer requires TRANSFER_SRC_OPTIMAL or GENERAL source layout (Anvil code -20001); nothing was recorded.")
    ProcedureReturn
  EndIf
  For i = 0 To regionCount - 1
  *r = *regions + i * SizeOf(VkBufferImageCopy)
  microReadback = 0
  If *r\bufferOffset < 0 Or (*r\bufferOffset % 4) <> 0
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyImageToBuffer requires a non-negative four-byte-aligned destination buffer offset (Anvil code -20001); nothing was recorded.")
    ProcedureReturn
  EndIf
  If *r\imageSubresource\aspectMask <> #VK_IMAGE_ASPECT_COLOR_BIT Or *r\imageSubresource\mipLevel <> 0 Or *r\imageSubresource\baseArrayLayer <> 0 Or *r\imageSubresource\layerCount <> 1
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyImageToBuffer supports only colour aspect at mip zero and layer zero (Anvil code -20005); nothing was recorded.")
    ProcedureReturn
  EndIf
  If *r\imageOffset\x < 0 Or *r\imageOffset\y < 0 Or *r\imageOffset\z <> 0 Or *r\imageExtent\width < 1 Or *r\imageExtent\height < 1 Or *r\imageExtent\depth <> 1
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyImageToBuffer requires a positive two-dimensional region with non-negative XY offsets and zero Z offset (Anvil code -20001); nothing was recorded.")
    ProcedureReturn
  EndIf
  If *r\imageOffset\x > avkImgW[src] - *r\imageExtent\width Or *r\imageOffset\y > avkImgH[src] - *r\imageExtent\height
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyImageToBuffer requires the complete rectangle to fit the source image (Anvil code -20001); nothing was recorded.")
    ProcedureReturn
  EndIf
  If avkImgTiling[src] = #VK_IMAGE_TILING_OPTIMAL
    If *r\imageExtent\width <= 4 And *r\imageExtent\height <= 4 And (*r\imageOffset\x % 4) + *r\imageExtent\width <= 4 And (*r\imageOffset\y % 4) + *r\imageExtent\height <= 4 And ((*r\imageOffset\x % 4) <> 0 Or (*r\imageOffset\y % 4) <> 0 Or ((*r\imageExtent\width % 4) <> 0 And *r\imageOffset\x <> avkImgW[src] - *r\imageExtent\width) Or ((*r\imageExtent\height % 4) <> 0 And *r\imageOffset\y <> avkImgH[src] - *r\imageExtent\height))
      microReadback = 1
      If (avkBackendCaps() & #ANVIL_VK_CAP_TILED_MICRO_READBACK) = 0
        avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyImageToBuffer interior one-utile readback requires the dedicated backend capability (Anvil code -20005); nothing was recorded.")
        ProcedureReturn
      EndIf
    EndIf
    If regionCount <> 1 Or (microReadback = 0 And ((*r\imageOffset\x % 4) <> 0 Or (*r\imageOffset\y % 4) <> 0 Or ((*r\imageExtent\width % 4) <> 0 And *r\imageOffset\x <> avkImgW[src] - *r\imageExtent\width) Or ((*r\imageExtent\height % 4) <> 0 And *r\imageOffset\y <> avkImgH[src] - *r\imageExtent\height)))
      avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyImageToBuffer supports one optimal rectangle with four-texel-aligned source offsets and only right/bottom edge tails (Anvil code -20005); nothing was recorded.")
      ProcedureReturn
    EndIf
    o = avkCbOpHead[c]
    While o <> 0
      If avkOpKind[o] = #ANVIL_VK_OP_COPY_IMAGE_BUFFER And (microReadback <> 0 Or avkOpRows[o] = 1)
        avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyImageToBuffer keeps an interior one-utile readback in its own command buffer (Anvil code -20005); nothing was recorded.")
        ProcedureReturn
      EndIf
      o = avkOpNext[o]
    Wend
  EndIf
  If (*r\bufferRowLength <> 0 And *r\bufferRowLength < *r\imageExtent\width) Or (*r\bufferImageHeight <> 0 And *r\bufferImageHeight < *r\imageExtent\height)
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyImageToBuffer requires an explicit bufferRowLength and bufferImageHeight to cover the copied rectangle (Anvil code -20001); nothing was recorded.")
    ProcedureReturn
  EndIf
  rowBytes = *r\imageExtent\width * #ANVIL_VK_BGRA8_TEXEL_BYTES
  rows = *r\imageExtent\height
  bufferPitch = rowBytes
  If *r\bufferRowLength <> 0 : bufferPitch = *r\bufferRowLength * #ANVIL_VK_BGRA8_TEXEL_BYTES : EndIf
  bytes = (rows - 1) * bufferPitch + rowBytes
  sourceOffset = 0
  If avkImgTiling[src] = #VK_IMAGE_TILING_LINEAR : sourceOffset = *r\imageOffset\y * avkImgPitch[src] + *r\imageOffset\x * #ANVIL_VK_BGRA8_TEXEL_BYTES : EndIf
  If rowBytes < 1 Or bufferPitch < rowBytes Or bytes < rowBytes Or (avkImgTiling[src] = #VK_IMAGE_TILING_LINEAR And (rowBytes > avkImgPitch[src] Or sourceOffset + (rows - 1) * avkImgPitch[src] + rowBytes > avkImgSize[src])) Or (avkImgTiling[src] = #VK_IMAGE_TILING_OPTIMAL And (avkImgBackendLayout[src] = 0 Or avkImgSize[src] < rowBytes * rows))
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdCopyImageToBuffer found an image pitch or allocation too short for the requested rows (Anvil code -20004); nothing was recorded.")
    ProcedureReturn
  EndIf
  If microReadback <> 0 And bufferPitch - rowBytes > 32767
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyImageToBuffer interior one-utile readback exceeds the backend DMA destination stride (Anvil code -20005); nothing was recorded.")
    ProcedureReturn
  EndIf
  If avkTransferBufferResolve(dstBuffer, d, #VK_BUFFER_USAGE_TRANSFER_DST_BIT, *r\bufferOffset, bytes, @destinationBase) = 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdCopyImageToBuffer requires a live, bound TRANSFER_DST buffer covering the requested rectangle (Anvil code -20004); nothing was recorded.")
    ProcedureReturn
  EndIf
  sourceBase = avkHeapBase + avkMemOffset[avkImgMemSlot[src]] + avkImgMemOffset[src] + sourceOffset
  If microReadback <> 0
    bufferBase = AnvilVkBufferAddress(dstBuffer) : bufferBytes = AnvilVkBufferSize(dstBuffer)
    If bufferBase <= 0 Or bufferBytes < bytes Or sourceBase < bufferBase + bufferBytes And bufferBase < sourceBase + avkImgSize[src]
      avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyImageToBuffer interior readback requires disjoint full source-image and destination-buffer ranges (Anvil code -20001); nothing was recorded.")
      ProcedureReturn
    EndIf
  EndIf
  If (avkImgTiling[src] = #VK_IMAGE_TILING_OPTIMAL And sourceBase < destinationBase + bytes And destinationBase < sourceBase + avkImgSize[src]) Or (avkImgTiling[src] = #VK_IMAGE_TILING_LINEAR And avkImageRowsOverlap(sourceBase, avkImgPitch[src], rowBytes, rows, destinationBase, bufferPitch, rowBytes, rows) <> 0)
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyImageToBuffer source and destination memory overlap (Anvil code -20001); no array region was recorded.")
    ProcedureReturn
  EndIf
  If avkImgTiling[src] = #VK_IMAGE_TILING_LINEAR
  For j = 0 To i - 1
    *prior = *regions + j * SizeOf(VkBufferImageCopy)
    priorBytes = *prior\imageExtent\width * #ANVIL_VK_BGRA8_TEXEL_BYTES
    priorPitch = priorBytes
    If *prior\bufferRowLength <> 0 : priorPitch = *prior\bufferRowLength * #ANVIL_VK_BGRA8_TEXEL_BYTES : EndIf
    priorSource = avkHeapBase + avkMemOffset[avkImgMemSlot[src]] + avkImgMemOffset[src] + *prior\imageOffset\y * avkImgPitch[src] + *prior\imageOffset\x * #ANVIL_VK_BGRA8_TEXEL_BYTES
    If avkTransferBufferResolve(dstBuffer, d, #VK_BUFFER_USAGE_TRANSFER_DST_BIT, *prior\bufferOffset, (*prior\imageExtent\height - 1) * priorPitch + priorBytes, @priorDestination) = 0
      avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdCopyImageToBuffer lost an earlier destination while validating the region array (Anvil code -20004); nothing was recorded.")
      ProcedureReturn
    EndIf
    If avkImageRowsOverlap(sourceBase, avkImgPitch[src], rowBytes, rows, priorDestination, priorPitch, priorBytes, *prior\imageExtent\height) <> 0 Or avkImageRowsOverlap(priorSource, avkImgPitch[src], priorBytes, *prior\imageExtent\height, destinationBase, bufferPitch, rowBytes, rows) <> 0 Or avkImageRowsOverlap(priorDestination, priorPitch, priorBytes, *prior\imageExtent\height, destinationBase, bufferPitch, rowBytes, rows) <> 0
      avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyImageToBuffer regions overlap source and destination memory or two destinations (Anvil code -20001); no array region was recorded.")
      ProcedureReturn
    EndIf
  Next
  EndIf
  Next
  ref = avkCbRef(c, srcImage, src)
  If ref < 0
    avkCbFail(c, #VK_ERROR_OUT_OF_HOST_MEMORY, "vkCmdCopyImageToBuffer exceeded the command buffer's image-reference capacity (VkResult -1); nothing was recorded.")
    ProcedureReturn
  EndIf
  If avkRefClaim(c, ref, srcLayout) = 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdCopyImageToBuffer cannot retain its source image or match its recorded layout (Anvil code -20004); nothing was recorded.")
    ProcedureReturn
  EndIf
  group = 0
  For i = 0 To regionCount - 1
    *r = *regions + i * SizeOf(VkBufferImageCopy)
    o = avkOpAppend(c, #ANVIL_VK_OP_COPY_IMAGE_BUFFER)
    If o = 0
      avkCbFail(c, #VK_ERROR_OUT_OF_HOST_MEMORY, "vkCmdCopyImageToBuffer exhausted recorded-command storage (VkResult -1); reset the invalid command buffer.")
      ProcedureReturn
    EndIf
    If group = 0 : group = o : EndIf
    avkOpCopyGroup[o] = group
    avkOpRef[o] = ref
    avkOpBuffer[o] = dstBuffer
    avkOpBufferOffset[o] = *r\bufferOffset
    avkOpDstOffset[o] = *r\imageOffset\y * avkImgPitch[src] + *r\imageOffset\x * #ANVIL_VK_BGRA8_TEXEL_BYTES
    avkOpImageX[o] = *r\imageOffset\x
    avkOpImageY[o] = *r\imageOffset\y
    avkOpSourceBytes[o] = *r\imageExtent\width * #ANVIL_VK_BGRA8_TEXEL_BYTES
    avkOpSourcePitch[o] = *r\imageExtent\height
    If microReadback <> 0 : avkOpRows[o] = 1 : EndIf
    avkOpBufferPitch[o] = avkOpSourceBytes[o]
    If *r\bufferRowLength <> 0 : avkOpBufferPitch[o] = *r\bufferRowLength * #ANVIL_VK_BGRA8_TEXEL_BYTES : EndIf
  Next
EndProcedure

; Return a command buffer to the initial state: no ops, no references, no
; recorded failure. Every reset path goes through this one procedure, so
; a new piece of per-buffer state cannot be forgotten by one of them.
Procedure.i avkCbClear(c.i)
  Define k.i
  If avkRecordedDrawRelease(c) = 0
    avkCmdState[c] = #ANVIL_VK_CB_INVALID
    avkFault(#VK_ERROR_INITIALIZATION_FAILED, "the command buffer's recorded-draw chain is inconsistent (VkResult -3, VK_ERROR_INITIALIZATION_FAILED); no draw slot was returned and the command buffer was invalidated. This is an internal ownership fault, not an application recording error.")
    ProcedureReturn 0
  EndIf
  avkOpsRelease(c)
  k = 0
  While k < #ANVIL_VK_MAX_CB_REFS
    avkRefImage[avkRefIndex(c, k)] = 0
    avkRefSlot[avkRefIndex(c, k)] = 0
    avkRefEntry[avkRefIndex(c, k)] = #ANVIL_VK_LAYOUT_ANY
    avkRefCur[avkRefIndex(c, k)] = #ANVIL_VK_LAYOUT_UNKNOWN
    k = k + 1
  Wend
  avkCbRefCount[c] = 0
  avkCbFailCode[c] = #ANVIL_VK_OK
  avkCbFailText[c] = 0
  avkCmdBeginFlags[c] = 0
  avkCmdOps[c] = 0
  avkCmdState[c] = #ANVIL_VK_CB_INITIAL
  avkCbPipe[c] = 0
  avkCbComputePipe[c] = 0 : avkCbComputeSet[c] = 0
  avkCbComputeRecorded[c] = 0
  avkCbComputeRecordPipe[c] = 0 : avkCbComputeRecordSet[c] = 0
  avkCbComputeGroupsX[c] = 0 : avkCbComputeItems[c] = 0
  avkCbComputeInputBase[c] = 0 : avkCbComputeInputBytes[c] = 0
  avkCbComputeOutputBase[c] = 0 : avkCbComputeOutputBytes[c] = 0
  avkCbComputeOutputWrittenBytes[c] = 0
  k = 0
  While k < #ANVIL_VK_MAX_BINDINGS
    avkCbVtxBuf[(c * #ANVIL_VK_MAX_BINDINGS) + k] = 0
    avkCbVtxOffset[(c * #ANVIL_VK_MAX_BINDINGS) + k] = 0
    k = k + 1
  Wend
  avkCbIndexBuf[c] = 0
  avkCbIndexOffset[c] = 0
  avkCbIndexType[c] = 0
  avkCbRpActive[c] = 0
  avkCbRpDone[c] = 0
  avkCbFb[c] = 0
  avkCbFbHandle[c] = 0
  avkCbClearWord[c] = 0
  avkCbDrawCount[c] = 0
  avkCbDrawFirst[c] = 0
  avkCbDrawVerts[c] = 0
  avkCbDescSet[c] = 0
  avkCbDescSetCount[c] = 0
  avkCbDescBindingCount[c] = 0
  avkCbDescPushBytes[c] = 0
  avkCbPushBytes[c] = 0
  avkCbScissorSet[c] = 0
  avkCbViewportSet[c] = 0
  avkCbScissorX[c] = 0
  avkCbScissorY[c] = 0
  avkCbScissorW[c] = 0
  avkCbScissorH[c] = 0
  k = 0
  While k < #ANVIL_VK_MAX_SET_BINDINGS
    avkCbDescType[(c * #ANVIL_VK_MAX_SET_BINDINGS) + k] = -1
    avkCbDescStages[(c * #ANVIL_VK_MAX_SET_BINDINGS) + k] = 0
    k = k + 1
  Wend
  k = 0
  While k < 4
    avkCbPushWord[(c * 4) + k] = 0
    k = k + 1
  Wend
  ProcedureReturn 1
EndProcedure

; A RECORDING ERROR DOES NOT RETURN. vkCmd* commands are void, so the
; specification's answer is that the command buffer becomes invalid and
; vkEndCommandBuffer reports the failure. That is exactly what happens
; here, and the sentence is kept so a caller can print it.
Procedure avkCbFail(c.i, code.i, text.i)
  If avkCbFailCode[c] = #ANVIL_VK_OK
    avkCbFailCode[c] = code
    avkCbFailText[c] = text
  EndIf
  avkCmdState[c] = #ANVIL_VK_CB_INVALID
  avkFault(code, text)
EndProcedure

Procedure.i AnvilVkCommandBufferFailureText(commandBuffer.i)
  Define c.i
  c = avkCmdSlot(commandBuffer)
  If c = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkCbFailText[c]
EndProcedure

; Find, or add, this command buffer's reference to an image. Returns the
; reference index, or -1 when the buffer already references as many
; images as it can hold.
Procedure.i avkCbRef(c.i, image.i, s.i)
  Define k.i
  k = 0
  While k < avkCbRefCount[c]
    If avkRefImage[avkRefIndex(c, k)] = image : ProcedureReturn k : EndIf
    k = k + 1
  Wend
  If avkCbRefCount[c] >= #ANVIL_VK_MAX_CB_REFS : ProcedureReturn -1 : EndIf
  k = avkCbRefCount[c]
  avkRefImage[avkRefIndex(c, k)] = image
  avkRefSlot[avkRefIndex(c, k)] = s
  avkRefEntry[avkRefIndex(c, k)] = #ANVIL_VK_LAYOUT_ANY
  avkRefCur[avkRefIndex(c, k)] = #ANVIL_VK_LAYOUT_UNKNOWN
  avkCbRefCount[c] = k + 1
  ProcedureReturn k
EndProcedure

Procedure.i avkOpAppend(c.i, kind.i)
  Define o.i
  o = 1
  While o <= #ANVIL_VK_MAX_OPS And avkOpLive[o] <> 0 : o = o + 1 : Wend
  If o > #ANVIL_VK_MAX_OPS : ProcedureReturn 0 : EndIf
  avkOpLive[o] = 1
  avkOpNext[o] = 0
  avkOpKind[o] = kind
  If avkCbOpHead[c] = 0
    avkCbOpHead[c] = o
  Else
    avkOpNext[avkCbOpTail[c]] = o
  EndIf
  avkCbOpTail[c] = o
  avkCmdOps[c] = avkCmdOps[c] + 1
  ProcedureReturn o
EndProcedure

; ----------------------------------------------------------------------
;  binary32 to 8-bit UNORM, WITHOUT TOUCHING THE FLOATING-POINT UNIT.
;
;  VkClearColorValue's float32 arm is four IEEE-754 binary32 values, and
;  the conversion the specification asks for is a clamp to [0,1] followed
;  by round-to-nearest of v * 255. Doing that on the BIT PATTERN keeps
;  this file free of any floating-point state: the portable layer must
;  not decide whether FPEN is on, and a compare against 1.0f that needed
;  a live FPU would be the one line in the engine that failed at EL3 or
;  in a context that had not enabled it.
; ----------------------------------------------------------------------
Procedure.i avkUnorm8FromF32Bits(bits.i)
  Define exp.i
  Define man.i
  Define shift.i
  Define n.i
  Define r.i
  bits = bits & $FFFFFFFF
  If (bits >> 31) <> 0 : ProcedureReturn 0 : EndIf          ; negative, or -0
  exp = (bits >> 23) & $FF
  man = bits & $7FFFFF
  If exp = $FF
    ; An infinity clamps to 1.0; a NaN has no defined colour, so it is
    ; taken as 0 rather than as whatever its payload happens to be.
    If man <> 0 : ProcedureReturn 0 : EndIf
    ProcedureReturn 255
  EndIf
  If exp = 0 : ProcedureReturn 0 : EndIf                    ; zero or subnormal
  If exp >= 127 : ProcedureReturn 255 : EndIf               ; 1.0 or greater
  shift = 150 - exp                                         ; 24 .. 149
  If shift > 40 : ProcedureReturn 0 : EndIf                 ; below half a step
  n = ($800000 | man) * 255
  r = (n + (1 << (shift - 1))) >> shift
  If r > 255 : r = 255 : EndIf
  ProcedureReturn r
EndProcedure

; ----------------------------------------------------------------------
;  COMMAND BUFFER LIFECYCLE
; ----------------------------------------------------------------------
Procedure.i AnvilVkCommandBufferBegin(commandBuffer.i, flags.i)
  Define c.i
  c = avkCmdSlot(commandBuffer)
  If c = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkCmdState[c] = #ANVIL_VK_CB_PENDING
    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkBeginCommandBuffer was called on a command buffer that is still executing (Anvil code -20004, command buffer pending); wait on the submission's fence with vkWaitForFences before recording into it again.")
  EndIf
  If avkCmdState[c] <> #ANVIL_VK_CB_INITIAL
    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkBeginCommandBuffer was called on a command buffer that is not in the initial state (Anvil code -20004, wrong command buffer state); reset it with vkResetCommandBuffer, or reset its pool, before recording into it again.")
  EndIf
  If (flags & (~(#VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT | #VK_COMMAND_BUFFER_USAGE_RENDER_PASS_CONTINUE_BIT | #VK_COMMAND_BUFFER_USAGE_SIMULTANEOUS_USE_BIT))) <> 0
    ProcedureReturn #ANVIL_VK_ERR_ARGS
  EndIf
  If avkCmdLevel[c] = #VK_COMMAND_BUFFER_LEVEL_PRIMARY And (flags & #VK_COMMAND_BUFFER_USAGE_RENDER_PASS_CONTINUE_BIT) <> 0
    ProcedureReturn #ANVIL_VK_ERR_ARGS
  EndIf
  If avkCbClear(c) = 0 : ProcedureReturn #VK_ERROR_INITIALIZATION_FAILED : EndIf
  avkCmdBeginFlags[c] = flags
  avkCmdState[c] = #ANVIL_VK_CB_RECORDING
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkCommandBufferEnd(commandBuffer.i)
  Define c.i
  Define k.i
  c = avkCmdSlot(commandBuffer)
  If c = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkCmdState[c] = #ANVIL_VK_CB_INVALID And avkCbFailCode[c] <> #ANVIL_VK_OK
    ; The recording failed earlier. Report it now, which is the only
    ; place the specification gives a void vkCmd* a way to be heard.
    ProcedureReturn avkCbFailCode[c]
  EndIf
  If avkCmdState[c] <> #ANVIL_VK_CB_RECORDING : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
  If avkCbRpActive[c] <> 0
    avkCmdState[c] = #ANVIL_VK_CB_INVALID
    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkEndCommandBuffer was called inside a render pass (Anvil code -20004, render pass still open); the specification requires every vkCmdBeginRenderPass to be matched by a vkCmdEndRenderPass before the recording ends, and a pass left open would have had its store operation skipped.")
  EndIf
  If avkCbComputeRecorded[c] <> 0 And (avkCmdOps[c] <> 0 Or avkCbDrawCount[c] <> 0 Or avkCbRpDone[c] <> 0)
    avkCmdState[c] = #ANVIL_VK_CB_INVALID
    ProcedureReturn avkFault(#VK_ERROR_FEATURE_NOT_PRESENT, "vkEndCommandBuffer cannot mix the passive compute dispatch record with graphics or transfer work; no compute queue execution exists yet.")
  EndIf
  ; A reference whose layout was never established inside the recording
  ; leaves the image exactly as it found it.
  k = 0
  While k < avkCbRefCount[c]
    If avkRefCur[avkRefIndex(c, k)] = #ANVIL_VK_LAYOUT_UNKNOWN
      avkRefEntry[avkRefIndex(c, k)] = #ANVIL_VK_LAYOUT_ANY
    EndIf
    k = k + 1
  Wend
  avkCmdState[c] = #ANVIL_VK_CB_EXECUTABLE
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkCommandBufferReset(commandBuffer.i, flags.i)
  Define c.i
  Define p.i
  c = avkCmdSlot(commandBuffer)
  If c = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If (flags & (~#VK_COMMAND_BUFFER_RESET_RELEASE_RESOURCES_BIT)) <> 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  p = avkCmdPool[c]
  If (avkPoolFlags[p] & #VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT) = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkResetCommandBuffer was called on a command buffer from a pool that was not created with VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT (Anvil code -20004, individual reset not allowed); reset the whole pool with vkResetCommandPool, or create the pool with that bit.")
  EndIf
  If avkCmdState[c] = #ANVIL_VK_CB_PENDING
    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkResetCommandBuffer was called on a command buffer that is still executing (Anvil code -20004, command buffer pending); wait on the submission's fence with vkWaitForFences first.")
  EndIf
  If avkCbClear(c) = 0 : ProcedureReturn #VK_ERROR_INITIALIZATION_FAILED : EndIf
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkCommandPoolReset(device.i, pool.i, flags.i)
  Define d.i
  Define p.i
  Define c.i
  d = avkDevSlot(device)
  p = avkPoolSlot(pool)
  If d = 0 Or p = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If (flags & (~#VK_COMMAND_POOL_RESET_RELEASE_RESOURCES_BIT)) <> 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  If avkPoolDev[p] <> d : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
  c = 1
  While c <= #ANVIL_VK_MAX_COMMAND_BUFFERS
    If avkCmdLive[c] <> 0 And avkCmdPool[c] = p
      If avkCmdState[c] = #ANVIL_VK_CB_PENDING
        ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkResetCommandPool was called while one of the pool's command buffers is still executing (Anvil code -20004, command buffer pending); no buffer in the pool was reset. Wait on the submission's fence, or call vkDeviceWaitIdle, first.")
      EndIf
    EndIf
    c = c + 1
  Wend
  c = 1
  While c <= #ANVIL_VK_MAX_COMMAND_BUFFERS
    If avkCmdLive[c] <> 0 And avkCmdPool[c] = p
      If avkCbClear(c) = 0 : ProcedureReturn #VK_ERROR_INITIALIZATION_FAILED : EndIf
    EndIf
    c = c + 1
  Wend
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkCommandBufferFree(device.i, pool.i, commandBuffer.i)
  Define d.i
  Define p.i
  Define c.i
  d = avkDevSlot(device)
  p = avkPoolSlot(pool)
  c = avkCmdSlot(commandBuffer)
  If d = 0 Or p = 0 Or c = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkPoolDev[p] <> d Or avkCmdPool[c] <> p : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
  If avkCmdState[c] = #ANVIL_VK_CB_PENDING
    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkFreeCommandBuffers was called on a command buffer that is still executing (Anvil code -20004, command buffer pending); nothing was freed. Wait on the submission's fence, or call vkDeviceWaitIdle, first.")
  EndIf
  If avkCbClear(c) = 0 : ProcedureReturn #VK_ERROR_INITIALIZATION_FAILED : EndIf
  avkCmdLive[c] = 0
  avkCmdState[c] = #ANVIL_VK_CB_INVALID
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkCommandPoolDestroy(device.i, pool.i)
  Define d.i
  Define p.i
  Define c.i
  d = avkDevSlot(device)
  p = avkPoolSlot(pool)
  If d = 0 Or p = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkPoolDev[p] <> d : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
  c = 1
  While c <= #ANVIL_VK_MAX_COMMAND_BUFFERS
    If avkCmdLive[c] <> 0 And avkCmdPool[c] = p
      If avkCmdState[c] = #ANVIL_VK_CB_PENDING
        ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkDestroyCommandPool was called while one of the pool's command buffers is still executing (Anvil code -20004, command buffer pending); the pool was left alone. Wait on the submission's fence, or call vkDeviceWaitIdle, first.")
      EndIf
    EndIf
    c = c + 1
  Wend
  c = 1
  While c <= #ANVIL_VK_MAX_COMMAND_BUFFERS
    If avkCmdLive[c] <> 0 And avkCmdPool[c] = p
      If avkCbClear(c) = 0 : ProcedureReturn #VK_ERROR_INITIALIZATION_FAILED : EndIf
      avkCmdLive[c] = 0
      avkCmdState[c] = #ANVIL_VK_CB_INVALID
    EndIf
    c = c + 1
  Wend
  avkPoolLive[p] = 0
  ProcedureReturn #VK_SUCCESS
EndProcedure

; ----------------------------------------------------------------------
;  RECORDING
; ----------------------------------------------------------------------

; The layout the recording believes an image is in at this point, or the
; entry requirement it has just acquired. `claim` is the layout the caller
; asserted in the command. Returns 1 if the claim is consistent.
Procedure.i avkRefClaim(c.i, k.i, claim.i)
  Define idx.i
  idx = avkRefIndex(c, k)
  If avkRefCur[idx] = #ANVIL_VK_LAYOUT_UNKNOWN
    avkRefEntry[idx] = claim
    avkRefCur[idx] = claim
    ProcedureReturn 1
  EndIf
  If avkRefCur[idx] <> claim : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i avkStagesKnown(mask.i)
  If mask = 0 : ProcedureReturn 0 : EndIf
  If (mask & (~(#VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT | #VK_PIPELINE_STAGE_TRANSFER_BIT | #VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT | #VK_PIPELINE_STAGE_HOST_BIT | #VK_PIPELINE_STAGE_ALL_COMMANDS_BIT | #VK_PIPELINE_STAGE_VERTEX_INPUT_BIT | #VK_PIPELINE_STAGE_VERTEX_SHADER_BIT | #VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT | #VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT))) <> 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i avkAccessKnown(mask.i)
  If (mask & (~(#VK_ACCESS_TRANSFER_READ_BIT | #VK_ACCESS_TRANSFER_WRITE_BIT | #VK_ACCESS_SHADER_READ_BIT | #VK_ACCESS_HOST_READ_BIT | #VK_ACCESS_HOST_WRITE_BIT | #VK_ACCESS_MEMORY_READ_BIT | #VK_ACCESS_MEMORY_WRITE_BIT | #VK_ACCESS_VERTEX_ATTRIBUTE_READ_BIT | #VK_ACCESS_COLOR_ATTACHMENT_READ_BIT | #VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT))) <> 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i avkLayoutKnown(v.i)
  If v = #VK_IMAGE_LAYOUT_UNDEFINED : ProcedureReturn 1 : EndIf
  If v = #VK_IMAGE_LAYOUT_GENERAL : ProcedureReturn 1 : EndIf
  If v = #VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL : ProcedureReturn 1 : EndIf
  If v = #VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL : ProcedureReturn 1 : EndIf
  If v = #VK_IMAGE_LAYOUT_PREINITIALIZED : ProcedureReturn 1 : EndIf
  If v = #VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL : ProcedureReturn 1 : EndIf
  If v = #VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL : ProcedureReturn 1 : EndIf
  ProcedureReturn 0
EndProcedure

; One image memory barrier. Void, exactly like vkCmdPipelineBarrier.
Procedure AnvilVkCmdImageBarrier(commandBuffer.i, srcStageMask.i, dstStageMask.i, *b.VkImageMemoryBarrier)
  Define c.i
  Define s.i
  Define k.i
  Define o.i
  Define srcAccessMask.i
  Define dstAccessMask.i
  Define oldLayout.i
  Define newLayout.i
  Define srcQueueFamily.i
  Define dstQueueFamily.i
  Define image.i
  Define aspectMask.i
  Define baseMip.i
  Define levelCount.i
  Define baseLayer.i
  Define layerCount.i
  If *b = 0
    avkFault(#ANVIL_VK_ERR_ARGS, "vkCmdPipelineBarrier was given a null image memory barrier (Anvil code -20001, invalid argument); nothing was recorded.")
    ProcedureReturn
  EndIf
  srcAccessMask = *b\srcAccessMask & $FFFFFFFF
  dstAccessMask = *b\dstAccessMask & $FFFFFFFF
  oldLayout = *b\oldLayout
  newLayout = *b\newLayout
  srcQueueFamily = *b\srcQueueFamilyIndex & $FFFFFFFF
  dstQueueFamily = *b\dstQueueFamilyIndex & $FFFFFFFF
  image = *b\image
  aspectMask = *b\subresourceRange\aspectMask & $FFFFFFFF
  baseMip = *b\subresourceRange\baseMipLevel & $FFFFFFFF
  levelCount = *b\subresourceRange\levelCount & $FFFFFFFF
  baseLayer = *b\subresourceRange\baseArrayLayer & $FFFFFFFF
  layerCount = *b\subresourceRange\layerCount & $FFFFFFFF
  c = avkCmdSlot(commandBuffer)
  If c = 0
    avkFault(#ANVIL_VK_ERR_HANDLE, "vkCmdPipelineBarrier was given a VkCommandBuffer handle that is not live (Anvil code -20002, stale or foreign handle); nothing was recorded.")
    ProcedureReturn
  EndIf
  If avkCmdState[c] <> #ANVIL_VK_CB_RECORDING
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdPipelineBarrier was called on a command buffer that is not recording (Anvil code -20004, wrong command buffer state); call vkBeginCommandBuffer first.")
    ProcedureReturn
  EndIf
  s = avkImgSlot(image)
  If s = 0
    avkCbFail(c, #ANVIL_VK_ERR_HANDLE, "vkCmdPipelineBarrier was given a VkImage handle that is not live (Anvil code -20002, stale or foreign handle); the command buffer is now invalid and vkEndCommandBuffer will say so.")
    ProcedureReturn
  EndIf
  If avkImgDev[s] <> avkPoolDev[avkCmdPool[c]]
    avkCbFail(c, #ANVIL_VK_ERR_OWNER, "vkCmdPipelineBarrier was given an image that belongs to a different VkDevice from the command buffer's pool (Anvil code -20003, wrong parent); every object in one command buffer must share one device.")
    ProcedureReturn
  EndIf
  If avkImgBound[s] = 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdPipelineBarrier was given an image with no memory bound to it (Anvil code -20004, image not bound); call vkBindImageMemory before recording any command that touches the image.")
    ProcedureReturn
  EndIf
  If avkStagesKnown(srcStageMask) = 0 Or avkStagesKnown(dstStageMask) = 0
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdPipelineBarrier was given a pipeline stage this implementation does not have (Anvil code -20005, unsupported stage); the stages Anvil tracks are TOP_OF_PIPE, VERTEX_INPUT, VERTEX_SHADER, FRAGMENT_SHADER, COLOR_ATTACHMENT_OUTPUT, TRANSFER, BOTTOM_OF_PIPE, HOST and ALL_COMMANDS.")
    ProcedureReturn
  EndIf
  If avkAccessKnown(srcAccessMask) = 0 Or avkAccessKnown(dstAccessMask) = 0
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdPipelineBarrier was given an access flag this implementation does not have (Anvil code -20005, unsupported access); the access types Anvil tracks are shader reads, transfer reads/writes, colour-attachment writes, host reads/writes and generic memory reads/writes.")
    ProcedureReturn
  EndIf
  If avkLayoutKnown(oldLayout) = 0 Or avkLayoutKnown(newLayout) = 0
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdPipelineBarrier was given an image layout this implementation does not track (Anvil code -20005, unsupported layout); the layouts Anvil tracks are UNDEFINED, PREINITIALIZED, GENERAL, COLOR_ATTACHMENT_OPTIMAL, SHADER_READ_ONLY_OPTIMAL, TRANSFER_SRC_OPTIMAL and TRANSFER_DST_OPTIMAL.")
    ProcedureReturn
  EndIf
  ; Queue-family ownership. There is one family, so the only two legal
  ; spellings are "both ignored" and "both this family". An acquire or
  ; release between two families cannot be honoured by a device that has
  ; one, and saying nothing about it would be the silent wrong answer.
  If Not ((srcQueueFamily = #VK_QUEUE_FAMILY_IGNORED And dstQueueFamily = #VK_QUEUE_FAMILY_IGNORED) Or (srcQueueFamily = #ANVIL_VK_QUEUE_FAMILY And dstQueueFamily = #ANVIL_VK_QUEUE_FAMILY))
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdPipelineBarrier was asked for a queue-family ownership transfer (Anvil code -20005, unsupported ownership transfer); this device exposes one queue family, so srcQueueFamilyIndex and dstQueueFamilyIndex must both be VK_QUEUE_FAMILY_IGNORED or both be family 0.")
    ProcedureReturn
  EndIf
  If aspectMask <> #VK_IMAGE_ASPECT_COLOR_BIT
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdPipelineBarrier was given a subresource aspect that this image does not have (Anvil code -20005, unsupported aspect); a VK_FORMAT_B8G8R8A8_UNORM image has only VK_IMAGE_ASPECT_COLOR_BIT. Set the barrier's subresourceRange.aspectMask to VK_IMAGE_ASPECT_COLOR_BIT.")
    ProcedureReturn
  EndIf
  If baseMip <> 0 Or baseLayer <> 0 Or Not (levelCount = 1 Or levelCount = #VK_REMAINING_MIP_LEVELS) Or Not (layerCount = 1 Or layerCount = #VK_REMAINING_ARRAY_LAYERS)
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdPipelineBarrier was given a subresource range that is not the whole image (Anvil code -20005, unsupported subresource range); every image Anvil creates has one mip level and one array layer, so the range must start at zero and cover one of each.")
    ProcedureReturn
  EndIf
  ; The dependency that makes a following clear correct. A transition into
  ; TRANSFER_DST_OPTIMAL whose destination scope does not include the
  ; transfer stage and a transfer write is the classic silently-wrong
  ; barrier, so it is refused rather than recorded.
  If newLayout = #VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL
    If (dstAccessMask & (#VK_ACCESS_TRANSFER_WRITE_BIT | #VK_ACCESS_MEMORY_WRITE_BIT)) = 0
      avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdPipelineBarrier transitions an image into VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL without making transfer writes visible (Anvil code -20001, incomplete dependency); dstAccessMask must include VK_ACCESS_TRANSFER_WRITE_BIT for the transfer that follows the transition.")
      ProcedureReturn
    EndIf
    If (dstStageMask & (#VK_PIPELINE_STAGE_TRANSFER_BIT | #VK_PIPELINE_STAGE_ALL_COMMANDS_BIT)) = 0
      avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdPipelineBarrier transitions an image into VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL but its destination stage does not include the transfer stage (Anvil code -20001, incomplete dependency); dstStageMask must include VK_PIPELINE_STAGE_TRANSFER_BIT so the transition is ordered before the transfer.")
      ProcedureReturn
    EndIf
  EndIf
  If (dstStageMask & #VK_PIPELINE_STAGE_HOST_BIT) <> 0
    If (dstAccessMask & (#VK_ACCESS_HOST_READ_BIT | #VK_ACCESS_HOST_WRITE_BIT | #VK_ACCESS_MEMORY_READ_BIT | #VK_ACCESS_MEMORY_WRITE_BIT)) = 0
      avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdPipelineBarrier names the host stage in its destination scope but no host access (Anvil code -20001, incomplete dependency); a barrier that exists so the processor can read the pixels must include VK_ACCESS_HOST_READ_BIT.")
      ProcedureReturn
    EndIf
  EndIf
  k = avkCbRef(c, image, s)
  If k < 0
    avkCbFail(c, #VK_ERROR_OUT_OF_HOST_MEMORY, "one command buffer referenced more images than Anvil can retain for a submission (VkResult -1, VK_ERROR_OUT_OF_HOST_MEMORY); this slice retains two images per command buffer, so split the work across command buffers.")
    ProcedureReturn
  EndIf
  If oldLayout <> #VK_IMAGE_LAYOUT_UNDEFINED
    If avkRefClaim(c, k, oldLayout) = 0
      avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdPipelineBarrier claims the image is in a layout that earlier commands in this same command buffer did not leave it in (Anvil code -20004, layout mismatch); a barrier's oldLayout must be the layout the image is actually in at that point in the recording, or VK_IMAGE_LAYOUT_UNDEFINED to discard the contents.")
      ProcedureReturn
    EndIf
  EndIf
  o = avkOpAppend(c, #ANVIL_VK_OP_BARRIER)
  If o = 0
    avkCbFail(c, #VK_ERROR_OUT_OF_HOST_MEMORY, "the command pool ran out of recorded-command storage (VkResult -1, VK_ERROR_OUT_OF_HOST_MEMORY); the command buffer is now invalid. Reset command buffers that are no longer needed, or record fewer commands per buffer.")
    ProcedureReturn
  EndIf
  avkOpRef[o] = k
  avkOpOldLayout[o] = oldLayout
  avkOpNewLayout[o] = newLayout
  avkOpColor[o] = 0
  avkRefCur[avkRefIndex(c, k)] = newLayout
EndProcedure

; vkCmdClearColorImage over the whole of one image. Void, as the real
; command is. `r`, `g`, `b` and `a` are the caller's binary32 BIT
; PATTERNS in VkClearColorValue's R, G, B, A order - not packed bytes.
Procedure AnvilVkCmdClearColorImage(commandBuffer.i, image.i, imageLayout.i, *pColor, *pRange.VkImageSubresourceRange)
  Define c.i
  Define s.i
  Define k.i
  Define o.i
  Define red.i
  Define green.i
  Define blue.i
  Define alpha.i
  Define aspectMask.i
  Define baseMip.i
  Define levelCount.i
  Define baseLayer.i
  Define layerCount.i
  If *pColor = 0 Or *pRange = 0
    avkFault(#ANVIL_VK_ERR_ARGS, "vkCmdClearColorImage was given a null clear value or a null subresource range (Anvil code -20001, invalid argument); nothing was recorded.")
    ProcedureReturn
  EndIf
  aspectMask = *pRange\aspectMask & $FFFFFFFF
  baseMip = *pRange\baseMipLevel & $FFFFFFFF
  levelCount = *pRange\levelCount & $FFFFFFFF
  baseLayer = *pRange\baseArrayLayer & $FFFFFFFF
  layerCount = *pRange\layerCount & $FFFFFFFF
  c = avkCmdSlot(commandBuffer)
  If c = 0
    avkFault(#ANVIL_VK_ERR_HANDLE, "vkCmdClearColorImage was given a VkCommandBuffer handle that is not live (Anvil code -20002, stale or foreign handle); nothing was recorded.")
    ProcedureReturn
  EndIf
  If avkCmdState[c] <> #ANVIL_VK_CB_RECORDING
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdClearColorImage was called on a command buffer that is not recording (Anvil code -20004, wrong command buffer state); call vkBeginCommandBuffer first.")
    ProcedureReturn
  EndIf
  s = avkImgSlot(image)
  If s = 0
    avkCbFail(c, #ANVIL_VK_ERR_HANDLE, "vkCmdClearColorImage was given a VkImage handle that is not live (Anvil code -20002, stale or foreign handle); the command buffer is now invalid and vkEndCommandBuffer will say so.")
    ProcedureReturn
  EndIf
  If avkImgDev[s] <> avkPoolDev[avkCmdPool[c]]
    avkCbFail(c, #ANVIL_VK_ERR_OWNER, "vkCmdClearColorImage was given an image that belongs to a different VkDevice from the command buffer's pool (Anvil code -20003, wrong parent); every object in one command buffer must share one device.")
    ProcedureReturn
  EndIf
  If avkImgBound[s] = 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdClearColorImage was given an image with no memory bound to it (Anvil code -20004, image not bound); call vkBindImageMemory before recording a clear.")
    ProcedureReturn
  EndIf
  If (avkImgUsage[s] & #VK_IMAGE_USAGE_TRANSFER_DST_BIT) = 0
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdClearColorImage was given an image that was not created with VK_IMAGE_USAGE_TRANSFER_DST_BIT (Anvil code -20001, missing usage); a clear is a transfer write, so the image must name that usage in VkImageCreateInfo.")
    ProcedureReturn
  EndIf
  If imageLayout <> #VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL And imageLayout <> #VK_IMAGE_LAYOUT_GENERAL
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdClearColorImage was told the image is in a layout it may not be cleared in (Anvil code -20001, wrong layout); outside a render pass the specification permits only VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL and VK_IMAGE_LAYOUT_GENERAL. Record a vkCmdPipelineBarrier into that layout first, and then use the layout the image is actually in.")
    ProcedureReturn
  EndIf
  If aspectMask <> #VK_IMAGE_ASPECT_COLOR_BIT
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdClearColorImage was given a subresource aspect other than colour (Anvil code -20001, wrong aspect); a colour clear names VK_IMAGE_ASPECT_COLOR_BIT and nothing else.")
    ProcedureReturn
  EndIf
  If baseMip <> 0 Or baseLayer <> 0 Or Not (levelCount = 1 Or levelCount = #VK_REMAINING_MIP_LEVELS) Or Not (layerCount = 1 Or layerCount = #VK_REMAINING_ARRAY_LAYERS)
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdClearColorImage was given a subresource range that is not the whole image (Anvil code -20005, unsupported subresource range); every image Anvil creates has one mip level and one array layer, so the range must start at zero and cover one of each.")
    ProcedureReturn
  EndIf
  ; The backend has to be able to run it. Asking now, at record time,
  ; means an unsupported clear never reaches a queue at all.
  If avkBackendClearSupported(AnvilVkImageAddress(image), avkImgSize[s], avkImgW[s], avkImgH[s], avkImgPitch[s]) <> #VK_SUCCESS
    avkCbFail(c, #VK_ERROR_FEATURE_NOT_PRESENT, "the graphics backend cannot clear an image of this size (VkResult -8, VK_ERROR_FEATURE_NOT_PRESENT); the command buffer is now invalid. Create the image with an extent and row pitch supported by the selected backend.")
    ProcedureReturn
  EndIf
  k = avkCbRef(c, image, s)
  If k < 0
    avkCbFail(c, #VK_ERROR_OUT_OF_HOST_MEMORY, "one command buffer referenced more images than Anvil can retain for a submission (VkResult -1, VK_ERROR_OUT_OF_HOST_MEMORY); this slice retains two images per command buffer, so split the work across command buffers.")
    ProcedureReturn
  EndIf
  If avkRefClaim(c, k, imageLayout) = 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdClearColorImage claims the image is in a layout that earlier commands in this same command buffer did not leave it in (Anvil code -20004, layout mismatch); the imageLayout argument must be the layout the image is actually in at that point in the recording.")
    ProcedureReturn
  EndIf
  o = avkOpAppend(c, #ANVIL_VK_OP_CLEAR_COLOR)
  If o = 0
    avkCbFail(c, #VK_ERROR_OUT_OF_HOST_MEMORY, "the command pool ran out of recorded-command storage (VkResult -1, VK_ERROR_OUT_OF_HOST_MEMORY); the command buffer is now invalid. Reset command buffers that are no longer needed, or record fewer commands per buffer.")
    ProcedureReturn
  EndIf
  red = avkUnorm8FromF32Bits(avkU32(*pColor))
  green = avkUnorm8FromF32Bits(avkU32(*pColor + 4))
  blue = avkUnorm8FromF32Bits(avkU32(*pColor + 8))
  alpha = avkUnorm8FromF32Bits(avkU32(*pColor + 12))
  ; VK_FORMAT_B8G8R8A8_UNORM stores B, G, R, A in ascending byte order.
  ; On this little-endian part that is the word (A<<24)|(R<<16)|(G<<8)|B.
  avkOpRef[o] = k
  avkOpOldLayout[o] = imageLayout
  avkOpNewLayout[o] = imageLayout
  avkOpColor[o] = (alpha << 24) | (red << 16) | (green << 8) | blue
EndProcedure

; ----------------------------------------------------------------------
;  SUBMISSION
; ----------------------------------------------------------------------
Procedure avkFlightRetain(c.i)
  Define k.i
  Define s.i
  k = 0
  While k < avkCbRefCount[c]
    s = avkRefSlot[avkRefIndex(c, k)]
    avkImgInFlight[s] = avkImgInFlight[s] + 1
    avkMemInFlight[avkImgMemSlot[s]] = avkMemInFlight[avkImgMemSlot[s]] + 1
    k = k + 1
  Wend
EndProcedure

Procedure avkFlightReleaseRefs(c.i)
  Define k.i
  Define s.i
  avkDrawListRelease(c)
  avkRenderClearRelease()
  avkCopyBufferRelease(c)
  k = 0
  While k < avkCbRefCount[c]
    s = avkRefSlot[avkRefIndex(c, k)]
    If avkImgInFlight[s] > 0 : avkImgInFlight[s] = avkImgInFlight[s] - 1 : EndIf
    If avkMemInFlight[avkImgMemSlot[s]] > 0
      avkMemInFlight[avkImgMemSlot[s]] = avkMemInFlight[avkImgMemSlot[s]] - 1
    EndIf
    k = k + 1
  Wend
EndProcedure

; Apply the recorded layout results and let the retained resources go.
; `ok` is 0 when the device faulted, in which case the image's layout is
; NOT advanced: a clear that did not happen did not leave the image in
; the layout a completed clear would have.
Procedure avkFlightComplete(ok.i)
  Define c.i
  Define k.i
  Define s.i
  Define semRc.i
  If avkFlightActive = 0
    ProcedureReturn
  EndIf
  c = avkFlightCb
  If ok <> 0
    k = 0
    While k < avkCbRefCount[c]
      s = avkRefSlot[avkRefIndex(c, k)]
      If avkRefCur[avkRefIndex(c, k)] <> #ANVIL_VK_LAYOUT_UNKNOWN
        avkImgLayout[s] = avkRefCur[avkRefIndex(c, k)]
      EndIf
      k = k + 1
    Wend
  EndIf
  ; Semaphore state follows the same real completion boundary as images,
  ; buffers, command buffers and fences. A pending backend keeps the ticket
  ; committed until a later avkFlightPoll settles this flight.
  If avkFlightSemaphoreReservation <> #VK_NULL_HANDLE
    If ok <> 0
      semRc = avkSemaphoreComplete(avkFlightSemaphoreReservation)
      If semRc <> #VK_SUCCESS
        avkSemaphoreRollback(avkFlightSemaphoreReservation)
        ok = 0
        avkFault(#VK_ERROR_DEVICE_LOST, "the graphics device completed but its binary semaphore transaction could not be published (VkResult -4, VK_ERROR_DEVICE_LOST); the semaphore states were rolled back and the command buffer was invalidated.")
      EndIf
    Else
      avkSemaphoreRollback(avkFlightSemaphoreReservation)
    EndIf
  EndIf
  avkFlightReleaseRefs(c)
  If ok = 0
    avkCmdState[c] = #ANVIL_VK_CB_INVALID
  ElseIf (avkCmdBeginFlags[c] & #VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT) <> 0
    avkCmdState[c] = #ANVIL_VK_CB_INVALID
  Else
    avkCmdState[c] = #ANVIL_VK_CB_EXECUTABLE
  EndIf
  If avkFlightFence <> 0 : avkFenceSignal(avkFlightFence) : EndIf
  avkFlightActive = 0
  avkFlightCb = 0
  avkFlightFence = 0
  avkFlightSemaphoreReservation = 0
  avkCompleteCount = avkCompleteCount + 1
EndProcedure

; Submit one primary command buffer, optionally signalling one fence and
; carrying one already-reserved binary-semaphore transaction. The reservation
; is committed only after all resource/fence preflight succeeds, and is owned
; by the flight until immediate or polled completion.
Procedure.i AnvilVkQueueSubmitOne(queue.i, commandBuffer.i, fence.i, semaphoreReservation.i)
  Define q.i
  Define c.i
  Define d.i
  Define k.i
  Define s.i
  Define f.i
  Define o.i
  Define job.i
  Define clears.i
  Define copies.i
  Define copyOp.i
  Define copyGroup.i
  Define copyGroups.i
  Define imageCopies.i
  Define imageCopyOp.i
  Define imageCopyGroup.i
  Define imageCopyGroups.i
  Define tiledRectCount.i
  Define tiledEdgeTailCount.i
  Define tiledMicroCount.i
  Define tiledLinearMicroCount.i
  Define linearTiledMicroCount.i
  Define linearTiledRectCount.i
  Define partialBufferTiledCount.i
  Define partialBufferTiledTiles.i
  Define microBufferTiledCount.i
  Define gridBufferTiledCount.i
  Define readbacks.i
  Define microReadbackCount.i
  Define readbackGroup.i
  Define readbackGroups.i
  Define sourceImageSlot.i
  Define destinationImageSlot.i
  Define copyBytes.i
  Define copyRows.i
  Define sourcePitch.i
  Define sourceSpan.i
  Define sourceBufferBytes.i
  Define sourceBufferBase.i
  Define destinationBufferBase.i
  Define destinationBufferBytes.i
  Define destinationPitch.i
  Define sourceRow.i
  Define destinationRow.i
  Define sourceRowBase.i
  Define destinationRowBase.i
  Define other.i
  Define otherSourceBase.i
  Define otherDestinationBase.i
  Define otherBytes.i
  Define otherRows.i
  Define bufferCopies.i
  Define colour.i
  Define target.i
  Define sourceBase.i
  Define destinationBase.i
  Define copyAlign.i
  Define copy.AnvilVkBackendImageCopy
  Define tiledCopy.AnvilVkBackendTiledImageCopy
  Define tiledRect.AnvilVkBackendTiledRectCopy
  Define linearTiledRect.AnvilVkBackendLinearTiledRectCopy
  Define tiledRead.AnvilVkBackendTiledReadback
  q = avkQueueSlot(queue)
  If q = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  d = avkQueueDev[q]
  If avkFlightActive <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit was called while an earlier submission on this queue has not completed (Anvil code -20004, queue busy); this slice runs one submission at a time. Wait on the earlier submission's fence, or call vkDeviceWaitIdle, before submitting again.")
  EndIf
  ; A previous draw submission may have closed its private list and then
  ; refused a signalled fence or semaphore transaction before a flight owned
  ; that closure. Never let a later transfer/barrier submission inherit it.
  avkDrawListDiscard()
  avkRenderClearDiscard()
  If commandBuffer = #VK_NULL_HANDLE
    ; A submission with no command buffers is legal. Its wait/signal
    ; semaphore operations and fence complete synchronously because there is
    ; no backend work to wait for.
    f = 0
    If fence <> #VK_NULL_HANDLE
      f = avkFenceAcquire(d, fence)
      If f <= 0 : ProcedureReturn f : EndIf
    EndIf
    If semaphoreReservation <> #VK_NULL_HANDLE
      job = avkSemaphoreCommit(semaphoreReservation)
      If job <> #VK_SUCCESS
        If f > 0 : avkFenceRelease(f) : EndIf
        ProcedureReturn job
      EndIf
      job = avkSemaphoreComplete(semaphoreReservation)
      If job <> #VK_SUCCESS
        avkSemaphoreRollback(semaphoreReservation)
        If f > 0 : avkFenceRelease(f) : EndIf
        ProcedureReturn job
      EndIf
    EndIf
    If f > 0 : avkFenceSignal(f) : EndIf
    avkSubmitCount = avkSubmitCount + 1
    avkCompleteCount = avkCompleteCount + 1
    ProcedureReturn #VK_SUCCESS
  EndIf
  c = avkCmdSlot(commandBuffer)
  If c = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkPoolDev[avkCmdPool[c]] <> d
    ProcedureReturn avkFault(#ANVIL_VK_ERR_OWNER, "vkQueueSubmit was given a command buffer from a different VkDevice than the queue (Anvil code -20003, wrong parent); submit a command buffer to a queue of the device that allocated it.")
  EndIf
  If avkCmdLevel[c] <> #VK_COMMAND_BUFFER_LEVEL_PRIMARY
    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit was given a secondary command buffer (Anvil code -20004, wrong command buffer level); only primary command buffers may be submitted, and secondary execution is not implemented.")
  EndIf
  If avkCmdState[c] <> #ANVIL_VK_CB_EXECUTABLE
    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit was given a command buffer that is not in the executable state (Anvil code -20004, wrong command buffer state); record it and call vkEndCommandBuffer before submitting it.")
  EndIf
  If avkCbComputeRecorded[c] <> 0
    ProcedureReturn avkFault(#VK_ERROR_FEATURE_NOT_PRESENT, "vkQueueSubmit cannot execute a passive compute dispatch record while the compute queue and backend submission path are unavailable; nothing was submitted.")
  EndIf
  ; Every image the recording assumed something about must actually be
  ; in that layout now. This is the join between what was recorded and
  ; what the device holds, and it is checked before anything is claimed.
  k = 0
  While k < avkCbRefCount[c]
    ; The slot is only a recorded acceleration hint. Resolve the original
    ; generation-tagged handle again before looking at any slot-owned state.
    ; Otherwise destroying an image after recording and creating another in
    ; the same slot would silently redirect the old command to the replacement.
    s = avkImgSlot(avkRefImage[avkRefIndex(c, k)])
    If s = 0 Or s <> avkRefSlot[avkRefIndex(c, k)] Or avkImgBound[s] = 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit was given a command buffer that references an image which has since been destroyed, replaced or unbound (Anvil code -20004, stale resource reference); re-record the command buffer against the current live image generation.")
    EndIf
    If avkRefEntry[avkRefIndex(c, k)] <> #ANVIL_VK_LAYOUT_ANY
      If avkImgLayout[s] <> avkRefEntry[avkRefIndex(c, k)]
        ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit was given a command buffer that expects one of its images to already be in a layout the image is not in (Anvil code -20004, layout mismatch at submit); either transition the image with a barrier whose oldLayout is VK_IMAGE_LAYOUT_UNDEFINED, or submit the command buffer that leaves it in the expected layout first.")
      EndIf
    EndIf
    k = k + 1
  Wend
  ; Exactly one clear is what this backend seam carries. A command buffer
  ; with none is legal and does nothing; one with two is refused, because
  ; running only the first would be a silent wrong answer.
  clears = 0
  copies = 0
  copyOp = 0
  copyGroup = 0
  copyGroups = 0
  imageCopies = 0
  imageCopyOp = 0
  imageCopyGroup = 0
  imageCopyGroups = 0
  tiledRectCount = 0
  tiledEdgeTailCount = 0
  linearTiledRectCount = 0
  partialBufferTiledCount = 0
  tiledMicroCount = 0
  tiledLinearMicroCount = 0
  linearTiledMicroCount = 0
  partialBufferTiledTiles = 0
  microBufferTiledCount = 0
  gridBufferTiledCount = 0
  readbacks = 0
  microReadbackCount = 0
  readbackGroup = 0
  readbackGroups = 0
  bufferCopies = 0
  colour = 0
  target = 0
  o = avkCbOpHead[c]
  While o <> 0
    If avkOpKind[o] = #ANVIL_VK_OP_CLEAR_COLOR
      clears = clears + 1
      colour = avkOpColor[o]
      target = avkRefSlot[avkRefIndex(c, avkOpRef[o])]
    ElseIf avkOpKind[o] = #ANVIL_VK_OP_COPY_BUFFER_IMAGE
      copies = copies + 1
      If avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_RECT_TAG Or avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_MICRO_TAG Or avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_GRID_TAG Or avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_GRID_4X4_TAG
        partialBufferTiledCount = partialBufferTiledCount + 1
        If avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_MICRO_TAG
          microBufferTiledCount = microBufferTiledCount + 1
          partialBufferTiledTiles = partialBufferTiledTiles + 1
        ElseIf avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_GRID_TAG Or avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_GRID_4X4_TAG
          gridBufferTiledCount = gridBufferTiledCount + 1
          If avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_GRID_TAG
            partialBufferTiledTiles = partialBufferTiledTiles + 4
          Else
            partialBufferTiledTiles = partialBufferTiledTiles + 16
          EndIf
        ElseIf avkOpSourcePitch[o] > #ANVIL_VK_TILED_RECT_MAX_UTILES * 16 Or avkOpRows[o] > #ANVIL_VK_TILED_RECT_MAX_UTILES * 4
          partialBufferTiledTiles = #ANVIL_VK_TILED_RECT_MAX_UTILES + 1
        ElseIf avkOpSourcePitch[o] >= 4 And avkOpRows[o] >= 1
          partialBufferTiledTiles = partialBufferTiledTiles + ((avkOpSourcePitch[o] - 4) / 16 + 1) * ((avkOpRows[o] - 1) / 4 + 1)
        EndIf
      EndIf
      copyOp = o
      target = avkRefSlot[avkRefIndex(c, avkOpRef[o])]
      If copyGroup = 0
        copyGroup = avkOpCopyGroup[o]
        copyGroups = 1
      ElseIf avkOpCopyGroup[o] <> copyGroup
        copyGroups = copyGroups + 1
      EndIf
    ElseIf avkOpKind[o] = #ANVIL_VK_OP_COPY_IMAGE
      imageCopies = imageCopies + 1
      If avkOpRows[o] = 1 : tiledRectCount = tiledRectCount + 1 : EndIf
      If avkOpRows[o] = 6 : tiledEdgeTailCount = tiledEdgeTailCount + 1 : EndIf
      If avkOpRows[o] = 3 : tiledMicroCount = tiledMicroCount + 1 : EndIf
      If avkOpRows[o] = 4 : tiledLinearMicroCount = tiledLinearMicroCount + 1 : EndIf
      If avkOpRows[o] = 5 : linearTiledMicroCount = linearTiledMicroCount + 1 : EndIf
      If avkOpRows[o] = 2 : linearTiledRectCount = linearTiledRectCount + 1 : EndIf
      imageCopyOp = o
      If imageCopyGroup = 0
        imageCopyGroup = avkOpCopyGroup[o]
        imageCopyGroups = 1
      ElseIf avkOpCopyGroup[o] <> imageCopyGroup
        imageCopyGroups = imageCopyGroups + 1
      EndIf
    ElseIf avkOpKind[o] = #ANVIL_VK_OP_COPY_IMAGE_BUFFER
      readbacks = readbacks + 1
      If avkOpRows[o] = 1 : microReadbackCount = microReadbackCount + 1 : EndIf
      If readbackGroup = 0
        readbackGroup = avkOpCopyGroup[o]
        readbackGroups = 1
      ElseIf avkOpCopyGroup[o] <> readbackGroup
        readbackGroups = readbackGroups + 1
      EndIf
    ElseIf avkOpKind[o] = #ANVIL_VK_OP_COPY_BUFFER Or avkOpKind[o] = #ANVIL_VK_OP_FILL_BUFFER Or avkOpKind[o] = #ANVIL_VK_OP_UPDATE_BUFFER
      bufferCopies = bufferCopies + 1
    EndIf
    o = avkOpNext[o]
  Wend
  If tiledRectCount > 1
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkQueueSubmit supports one partial optimal-to-optimal rectangle per command buffer (Anvil code -20005); nothing was submitted.")
  EndIf
  If tiledRectCount > 0 And (avkBackendCaps() & #ANVIL_VK_CAP_TILED_RECT_COPY) = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkQueueSubmit requires a backend that executes partial optimal-image copies (Anvil code -20005); nothing was submitted.")
  EndIf
  If tiledMicroCount > 0 And (tiledMicroCount <> 1 Or imageCopies <> 1 Or copies <> 0 Or readbacks <> 0 Or bufferCopies <> 0 Or clears <> 0 Or avkCbDrawCount[c] <> 0)
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkQueueSubmit requires one optimal-image micro copy as the only transfer or draw job in its command buffer (Anvil code -20005); nothing was submitted.")
  EndIf
  If tiledMicroCount > 0 And (avkBackendCaps() & (#ANVIL_VK_CAP_TILED_RECT_COPY | #ANVIL_VK_CAP_TILED_MICRO_COPY)) <> (#ANVIL_VK_CAP_TILED_RECT_COPY | #ANVIL_VK_CAP_TILED_MICRO_COPY)
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkQueueSubmit requires the dedicated optimal-image micro backend capability (Anvil code -20005); nothing was submitted.")
  EndIf
  If tiledEdgeTailCount > 0 And (tiledEdgeTailCount <> 1 Or imageCopies <> 1 Or copies <> 0 Or readbacks <> 0 Or bufferCopies <> 0 Or clears <> 0 Or avkCbDrawCount[c] <> 0)
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkQueueSubmit requires one optimal-image edge-tail copy as its only transfer or draw job (Anvil code -20005); nothing was submitted.")
  EndIf
  If tiledEdgeTailCount > 0 And (avkBackendCaps() & (#ANVIL_VK_CAP_TILED_RECT_COPY | #ANVIL_VK_CAP_TILED_EDGE_TAIL_COPY)) <> (#ANVIL_VK_CAP_TILED_RECT_COPY | #ANVIL_VK_CAP_TILED_EDGE_TAIL_COPY)
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkQueueSubmit requires the dedicated optimal-image edge-tail backend capability (Anvil code -20005); nothing was submitted.")
  EndIf
  If tiledLinearMicroCount > 0 And (tiledLinearMicroCount <> 1 Or imageCopies <> 1 Or copies <> 0 Or readbacks <> 0 Or bufferCopies <> 0 Or clears <> 0 Or avkCbDrawCount[c] <> 0)
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkQueueSubmit requires one optimal-to-linear micro copy as its only transfer or draw job (Anvil code -20005); nothing was submitted.")
  EndIf
  If tiledLinearMicroCount > 0 And (avkBackendCaps() & (#ANVIL_VK_CAP_LINEAR_TRANSFER | #ANVIL_VK_CAP_TILED_TO_LINEAR_MICRO_COPY)) <> (#ANVIL_VK_CAP_LINEAR_TRANSFER | #ANVIL_VK_CAP_TILED_TO_LINEAR_MICRO_COPY)
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkQueueSubmit requires the dedicated optimal-to-linear micro copy backend capability (Anvil code -20005); nothing was submitted.")
  EndIf
  If microReadbackCount > 0 And (microReadbackCount <> 1 Or readbacks <> 1 Or copies <> 0 Or imageCopies <> 0 Or bufferCopies <> 0 Or clears <> 0 Or avkCbDrawCount[c] <> 0)
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkQueueSubmit requires one interior optimal-image micro readback as its only transfer or draw job (Anvil code -20005); nothing was submitted.")
  EndIf
  If microReadbackCount > 0 And (avkBackendCaps() & (#ANVIL_VK_CAP_LINEAR_TRANSFER | #ANVIL_VK_CAP_TILED_MICRO_READBACK)) <> (#ANVIL_VK_CAP_LINEAR_TRANSFER | #ANVIL_VK_CAP_TILED_MICRO_READBACK)
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkQueueSubmit requires the dedicated optimal-image micro readback backend capability (Anvil code -20005); nothing was submitted.")
  EndIf
  If linearTiledRectCount > 1
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkQueueSubmit supports one partial linear-to-optimal rectangle per command buffer (Anvil code -20005); nothing was submitted.")
  EndIf
  If linearTiledRectCount > 0 And (avkBackendCaps() & #ANVIL_VK_CAP_LINEAR_TO_TILED_RECT_COPY) = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkQueueSubmit requires a backend that executes partial linear-to-optimal copies (Anvil code -20005); nothing was submitted.")
  EndIf
  If linearTiledMicroCount > 0 And (linearTiledMicroCount <> 1 Or imageCopies <> 1 Or copies <> 0 Or readbacks <> 0 Or bufferCopies <> 0 Or clears <> 0 Or avkCbDrawCount[c] <> 0)
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkQueueSubmit requires one linear-to-optimal micro copy as its only transfer or draw job (Anvil code -20005); nothing was submitted.")
  EndIf
  If linearTiledMicroCount > 0 And (avkBackendCaps() & (#ANVIL_VK_CAP_LINEAR_TRANSFER | #ANVIL_VK_CAP_LINEAR_TO_TILED_RECT_COPY | #ANVIL_VK_CAP_LINEAR_TO_TILED_MICRO_COPY)) <> (#ANVIL_VK_CAP_LINEAR_TRANSFER | #ANVIL_VK_CAP_LINEAR_TO_TILED_RECT_COPY | #ANVIL_VK_CAP_LINEAR_TO_TILED_MICRO_COPY)
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkQueueSubmit requires the dedicated linear-to-optimal micro copy backend capability (Anvil code -20005); nothing was submitted.")
  EndIf
  If partialBufferTiledCount > 2 Or partialBufferTiledTiles > #ANVIL_VK_TILED_RECT_MAX_UTILES
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkQueueSubmit supports at most two partial optimal buffer uploads and 256 tiles per command buffer (Anvil code -20005); nothing was submitted.")
  EndIf
  If microBufferTiledCount > 0 And (microBufferTiledCount <> 1 Or copies <> 1 Or imageCopies <> 0 Or readbacks <> 0 Or bufferCopies <> 0 Or clears <> 0 Or avkCbDrawCount[c] <> 0)
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkQueueSubmit requires a one-utile micro upload to be the only transfer or draw job in its command buffer (Anvil code -20005); nothing was submitted.")
  EndIf
  If gridBufferTiledCount > 0 And (gridBufferTiledCount <> 1 Or copies <> 1 Or imageCopies <> 0 Or readbacks <> 0 Or bufferCopies <> 0 Or clears <> 0 Or avkCbDrawCount[c] <> 0)
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkQueueSubmit requires one UIF grid upload as its only transfer or draw job (Anvil code -20005); nothing was submitted.")
  EndIf
  If partialBufferTiledCount > 0
    o = avkCbOpHead[c]
    While o <> 0
      If avkOpKind[o] = #ANVIL_VK_OP_COPY_BUFFER_IMAGE And (avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_RECT_TAG Or avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_MICRO_TAG Or avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_GRID_TAG Or avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_GRID_4X4_TAG)
        If avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_MICRO_TAG
          If (avkBackendCaps() & (#ANVIL_VK_CAP_BUFFER_TO_TILED_RECT_COPY | #ANVIL_VK_CAP_BUFFER_TO_TILED_MICRO_COPY)) <> (#ANVIL_VK_CAP_BUFFER_TO_TILED_RECT_COPY | #ANVIL_VK_CAP_BUFFER_TO_TILED_MICRO_COPY)
            ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkQueueSubmit requires the one-utile micro upload backend capability (Anvil code -20005); nothing was submitted.")
          EndIf
        ElseIf avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_GRID_TAG Or avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_GRID_4X4_TAG
          If (avkBackendCaps() & (#ANVIL_VK_CAP_BUFFER_TRANSFER | #ANVIL_VK_CAP_LINEAR_TRANSFER | #ANVIL_VK_CAP_BUFFER_TO_TILED_RECT_COPY)) <> (#ANVIL_VK_CAP_BUFFER_TRANSFER | #ANVIL_VK_CAP_LINEAR_TRANSFER | #ANVIL_VK_CAP_BUFFER_TO_TILED_RECT_COPY) Or (avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_GRID_TAG And (avkBackendCaps() & #ANVIL_VK_CAP_BUFFER_TO_TILED_GRID_COPY) = 0) Or (avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_GRID_4X4_TAG And (avkBackendCaps() & #ANVIL_VK_CAP_BUFFER_TO_TILED_GRID_4X4_COPY) = 0)
            ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkQueueSubmit requires the dedicated UIF grid upload backend capability (Anvil code -20005); nothing was submitted.")
          EndIf
        ElseIf (avkOpSourcePitch[o] % 16) <> 0 Or (avkOpRows[o] % 4) <> 0
          If (avkBackendCaps() & (#ANVIL_VK_CAP_BUFFER_TO_TILED_RECT_COPY | #ANVIL_VK_CAP_BUFFER_TO_TILED_TAIL_COPY)) <> (#ANVIL_VK_CAP_BUFFER_TO_TILED_RECT_COPY | #ANVIL_VK_CAP_BUFFER_TO_TILED_TAIL_COPY)
            ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkQueueSubmit requires an edge-tail buffer-to-tiled backend for short optimal uploads (Anvil code -20005); nothing was submitted.")
          EndIf
        ElseIf (avkBackendCaps() & #ANVIL_VK_CAP_BUFFER_TO_TILED_RECT_COPY) = 0
          ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkQueueSubmit requires a buffer-to-tiled backend for complete-tile optimal uploads (Anvil code -20005); nothing was submitted.")
        EndIf
      EndIf
      o = avkOpNext[o]
    Wend
  EndIf
  If bufferCopies > 0 And (avkBackendCaps() & #ANVIL_VK_CAP_BUFFER_TRANSFER) = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkQueueSubmit found recorded buffer transfers but the backend no longer supports them (Anvil code -20005, unsupported transfer); restore a transfer-capable backend before submitting.")
  EndIf
  If (avkBackendCaps() & #ANVIL_VK_CAP_LINEAR_TRANSFER) = 0
    o = avkCbOpHead[c]
    While o <> 0
      If avkOpKind[o] = #ANVIL_VK_OP_COPY_IMAGE_BUFFER
        ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkQueueSubmit requires an image-readback backend for this recorded command (Anvil code -20005, unsupported transfer); use a device with linear transfer support.")
      ElseIf avkOpKind[o] = #ANVIL_VK_OP_COPY_BUFFER_IMAGE
        target = avkRefSlot[avkRefIndex(c, avkOpRef[o])]
        If avkImgTiling[target] = #VK_IMAGE_TILING_LINEAR
          ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkQueueSubmit requires a linear-image upload backend for this recorded command (Anvil code -20005, unsupported transfer); use a device with linear transfer support.")
        EndIf
      ElseIf avkOpKind[o] = #ANVIL_VK_OP_COPY_IMAGE
        target = avkRefSlot[avkRefIndex(c, avkOpDstRef[o])]
        If avkImgTiling[target] = #VK_IMAGE_TILING_LINEAR
          ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkQueueSubmit requires a linear-image copy backend for this recorded command (Anvil code -20005, unsupported transfer); use a device with linear transfer support.")
        EndIf
      EndIf
      o = avkOpNext[o]
    Wend
  EndIf
  If clears > 1
    ProcedureReturn avkFault(#VK_ERROR_FEATURE_NOT_PRESENT, "vkQueueSubmit was given a command buffer holding more than one clear (VkResult -8, VK_ERROR_FEATURE_NOT_PRESENT); nothing was submitted. This slice lowers one clear per submission, so record one clear per command buffer until the backend carries a command list.")
  EndIf
  If copies > 0 And (clears > 0 Or avkCbDrawCount[c] > 0 Or avkCbRpDone[c] <> 0)
    ProcedureReturn avkFault(#VK_ERROR_FEATURE_NOT_PRESENT, "vkQueueSubmit requires image transfers outside clear and render jobs (VkResult -8); no partial command stream was submitted.")
  EndIf
  If imageCopies > 0 And (clears > 0 Or avkCbDrawCount[c] > 0 Or avkCbRpDone[c] <> 0)
    ProcedureReturn avkFault(#VK_ERROR_FEATURE_NOT_PRESENT, "vkQueueSubmit requires image transfers outside clear and render jobs (VkResult -8); no partial command stream was submitted.")
  EndIf
  If readbacks > 0 And (clears > 0 Or avkCbDrawCount[c] > 0 Or avkCbRpDone[c] <> 0)
    ProcedureReturn avkFault(#VK_ERROR_FEATURE_NOT_PRESENT, "vkQueueSubmit requires image-to-buffer DMA readback commands outside clear and render jobs (VkResult -8); no partial command stream was submitted.")
  EndIf
  ; A command buffer is either a transfer or a render pass, never both.
  ; These mixed jobs have no ordered lowering; accepting only part of the
  ; recording would be a silent wrong answer.
  If avkCbDrawCount[c] > 0 And (clears > 0 Or copies > 0 Or bufferCopies > 0)
    ProcedureReturn avkFault(#VK_ERROR_FEATURE_NOT_PRESENT, "vkQueueSubmit was given a command buffer holding both a vkCmdClearColorImage and a render pass (VkResult -8, VK_ERROR_FEATURE_NOT_PRESENT); nothing was submitted. The backend seam carries one job per submission, so record the clear and the render pass in separate command buffers.")
  EndIf
  If clears > 0 And copies > 0
    ProcedureReturn avkFault(#VK_ERROR_FEATURE_NOT_PRESENT, "vkQueueSubmit was given both a clear and a buffer-to-image copy (VkResult -8, VK_ERROR_FEATURE_NOT_PRESENT); nothing was submitted. Record each backend job in its own command buffer until ordered multi-job submission exists.")
  EndIf
  If bufferCopies > 0 And clears > 0
    ProcedureReturn avkFault(#VK_ERROR_FEATURE_NOT_PRESENT, "vkQueueSubmit cannot mix a buffer transfer or fill with a clear in one backend job (VkResult -8, VK_ERROR_FEATURE_NOT_PRESENT); submit these jobs separately.")
  EndIf
  If avkCbRpDone[c] <> 0 And avkCbDrawCount[c] = 0
    If clears > 0 Or copies > 0 Or imageCopies > 0 Or readbacks > 0 Or bufferCopies > 0
      ProcedureReturn avkFault(#VK_ERROR_FEATURE_NOT_PRESENT, "vkQueueSubmit cannot mix a render-pass clear with a separate transfer in one backend job (VkResult -8, VK_ERROR_FEATURE_NOT_PRESENT); submit the jobs in separate command buffers.")
    EndIf
    job = avkRenderClearPreflight(c)
    If job <> #ANVIL_VK_OK : ProcedureReturn job : EndIf
  EndIf
  ; Resolve every generation-tagged draw dependency before the submission
  ; changes command/fence/resource state. A stale object is an application
  ; state error, not a device loss discovered after the flight has begun.
  If avkCbDrawCount[c] > 0
    job = avkDrawListPreflight(c)
    If job <> #ANVIL_VK_OK : ProcedureReturn job : EndIf
  EndIf
  If copies > 0
    o = avkCbOpHead[c]
    While o <> 0
      If avkOpKind[o] = #ANVIL_VK_OP_COPY_BUFFER_IMAGE
        copyOp = o
        target = avkRefSlot[avkRefIndex(c, avkOpRef[o])]
        If target < 1 Or avkImgBound[target] = 0
          ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found a stale or unbound buffer-to-image destination (Anvil code -20004); nothing was submitted.")
        EndIf
        copyAlign = avkBackendImageCopySourceAlignment()
        If copyAlign < 1 Or (copyAlign & (copyAlign - 1)) <> 0 Or (avkOpBufferOffset[o] % copyAlign) <> 0
          ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found that a recorded copy no longer satisfies the active backend's image-copy source alignment (Anvil code -20004); re-record against the current target contract.")
        EndIf
        If avkCopyBufferResolve(avkOpBuffer[o], d, avkOpBufferOffset[o], avkOpSourceBytes[o], @sourceBase) = 0
          ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found that a vkCmdCopyBufferToImage source buffer is no longer live, bound, owned, aligned or large enough (Anvil code -20004, stale source resource); re-record against a valid transfer-source buffer.")
        EndIf
        If avkImgTiling[target] = #VK_IMAGE_TILING_OPTIMAL
          If avkImgBackendLayout[target] = 0
            ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an incomplete optimal-image TFU transaction (Anvil code -20004); nothing was submitted.")
          EndIf
          If avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_RECT_TAG Or avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_MICRO_TAG Or avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_GRID_TAG Or avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_GRID_4X4_TAG
            copyBytes = avkOpSourcePitch[o] : copyRows = avkOpRows[o]
            sourcePitch = avkOpBufferPitch[o] : sourceSpan = avkOpSourceBytes[o]
            If copyBytes < 4 Or (copyBytes % 4) <> 0 Or copyRows < 1 Or sourcePitch < copyBytes Or (sourcePitch % 4) <> 0 Or sourceSpan <> (copyRows - 1) * sourcePitch + copyBytes
              ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an invalid partial buffer-to-optimal row span (Anvil code -20004); nothing was submitted.")
            EndIf
            If avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_MICRO_TAG
              If copyBytes > 16 Or copyRows > 4 Or sourcePitch - copyBytes > 32767 Or avkOpImageX[o] < 0 Or avkOpImageY[o] < 0 Or avkOpImageX[o] > avkImgW[target] - copyBytes / 4 Or avkOpImageY[o] > avkImgH[target] - copyRows Or (avkOpImageX[o] % 4) + copyBytes / 4 > 4 Or (avkOpImageY[o] % 4) + copyRows > 4
                ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found a micro upload crossing a UIF utile or exceeding its DMA stride (Anvil code -20004); nothing was submitted.")
              EndIf
            ElseIf avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_GRID_TAG Or avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_GRID_4X4_TAG
              If avkOpImageX[o] < 0 Or avkOpImageY[o] < 0 Or avkOpImageX[o] > avkImgW[target] - copyBytes / 4 Or avkOpImageY[o] > avkImgH[target] - copyRows Or (avkOpImageX[o] + copyBytes / 4 - 1) / 4 - avkOpImageX[o] / 4 > 3 Or (avkOpImageY[o] + copyRows - 1) / 4 - avkOpImageY[o] / 4 > 3 Or (avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_GRID_TAG And ((avkOpImageX[o] + copyBytes / 4 - 1) / 4 - avkOpImageX[o] / 4 > 1 Or (avkOpImageY[o] + copyRows - 1) / 4 - avkOpImageY[o] / 4 > 1)) Or (avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_GRID_4X4_TAG And (avkOpImageX[o] + copyBytes / 4 - 1) / 4 - avkOpImageX[o] / 4 <= 1 And (avkOpImageY[o] + copyRows - 1) / 4 - avkOpImageY[o] / 4 <= 1)
                ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an invalid or oversized interior UIF grid upload (Anvil code -20004); nothing was submitted.")
              EndIf
            Else
              If sourcePitch - 16 > 32767 Or ((copyBytes % 16) <> 0 And sourcePitch - (copyBytes % 16) > 32767) Or avkOpImageX[o] < 0 Or avkOpImageY[o] < 0 Or (avkOpImageX[o] % 4) <> 0 Or (avkOpImageY[o] % 4) <> 0 Or avkOpImageX[o] > avkImgW[target] - copyBytes / 4 Or avkOpImageY[o] > avkImgH[target] - copyRows Or ((copyBytes - 4) / 16 + 1) * ((copyRows - 1) / 4 + 1) > #ANVIL_VK_TILED_RECT_MAX_UTILES Or ((copyBytes % 16) <> 0 And avkOpImageX[o] <> avkImgW[target] - copyBytes / 4) Or ((copyRows % 4) <> 0 And avkOpImageY[o] <> avkImgH[target] - copyRows)
                ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an invalid partial buffer-to-optimal tile rectangle (Anvil code -20004); nothing was submitted.")
              EndIf
            EndIf
            destinationBase = avkHeapBase + avkMemOffset[avkImgMemSlot[target]] + avkImgMemOffset[target]
            sourceBufferBytes = AnvilVkBufferSize(avkOpBuffer[o]) : sourceBufferBase = AnvilVkBufferAddress(avkOpBuffer[o])
            If sourceBufferBytes < 1 Or sourceBufferBase = 0 Or avkImageRowsOverlap(sourceBufferBase, sourceBufferBytes, sourceBufferBytes, 1, destinationBase, avkImgSize[target], avkImgSize[target], 1) <> 0
              ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkQueueSubmit found overlapping partial source-buffer and optimal-image allocations (Anvil code -20001); nothing was submitted.")
            EndIf
            linearTiledRect\windowBase = avkHeapBase : linearTiledRect\windowBytes = avkHeapBytes
            linearTiledRect\sourceBase = sourceBase : linearTiledRect\sourceBytes = sourceSpan : linearTiledRect\sourcePitch = sourcePitch
            linearTiledRect\sourceViewWidth = copyBytes / 4 : linearTiledRect\sourceViewHeight = copyRows
            linearTiledRect\destinationBase = destinationBase : linearTiledRect\destinationBytes = avkImgSize[target]
            linearTiledRect\width = avkImgW[target] : linearTiledRect\height = avkImgH[target]
            linearTiledRect\destinationLayout = avkImgBackendLayout[target]
            linearTiledRect\paddedWidth = avkImgPaddedW[target] : linearTiledRect\paddedHeight = avkImgPaddedH[target]
            linearTiledRect\sourceX = 0 : linearTiledRect\sourceY = 0
            linearTiledRect\destinationX = avkOpImageX[o] : linearTiledRect\destinationY = avkOpImageY[o]
            linearTiledRect\regionWidth = copyBytes / 4 : linearTiledRect\regionHeight = copyRows
            If avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_MICRO_TAG
              If avkBackendLinearTiledMicroCopyValidate(@linearTiledRect) <> 0
                ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an invalid one-utile micro DMA copy (Anvil code -20004); nothing was submitted.")
              EndIf
            ElseIf avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_GRID_TAG Or avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_GRID_4X4_TAG
              If avkBackendLinearTiledGridCopyValidate(@linearTiledRect) <> 0
                ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an invalid per-tile UIF grid DMA copy (Anvil code -20004); nothing was submitted.")
              EndIf
            Else
              If avkBackendLinearTiledRectCopyValidate(@linearTiledRect) <> 0
                ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an invalid partial buffer-to-optimal DMA scatter (Anvil code -20004); nothing was submitted.")
              EndIf
            EndIf
            other = avkOpNext[o]
            While other <> 0
              If avkOpKind[other] = #ANVIL_VK_OP_COPY_BUFFER_IMAGE And avkOpDstOffset[other] = #ANVIL_VK_BUFFER_TILED_RECT_TAG
                If avkRefSlot[avkRefIndex(c, avkOpRef[other])] <> target
                  ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found partial optimal uploads targeting different images (Anvil code -20004); nothing was submitted.")
                EndIf
                otherBytes = avkOpSourcePitch[other] : otherRows = avkOpRows[other]
                If otherBytes < 4 Or (otherBytes % 4) <> 0 Or otherRows < 1 Or (avkOpImageX[o] < avkOpImageX[other] + otherBytes / 4 And avkOpImageX[other] < avkOpImageX[o] + copyBytes / 4 And avkOpImageY[o] < avkOpImageY[other] + otherRows And avkOpImageY[other] < avkOpImageY[o] + copyRows)
                  ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found overlapping or malformed ordered partial optimal destinations (Anvil code -20004); nothing was submitted.")
                EndIf
                If avkCopyBufferResolve(avkOpBuffer[other], d, avkOpBufferOffset[other], avkOpSourceBytes[other], @otherSourceBase) = 0
                  ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found a stale later partial upload source (Anvil code -20004); nothing was submitted.")
                EndIf
                If avkImageRowsOverlap(sourceBase, sourceSpan, sourceSpan, 1, otherSourceBase, avkOpSourceBytes[other], avkOpSourceBytes[other], 1) <> 0
                  ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkQueueSubmit found overlapping ordered partial source spans (Anvil code -20001); nothing was submitted.")
                EndIf
              EndIf
              other = avkOpNext[other]
            Wend
          Else
          If copies + imageCopies + bufferCopies + readbacks > 1 And avkBackendImageCopyBatchReady() = 0
            ProcedureReturn avkFault(#VK_ERROR_FEATURE_NOT_PRESENT, "vkQueueSubmit cannot order multiple optimal-image copies while the backend holds a pending transfer (VkResult -8); nothing was submitted.")
          EndIf
          copy\windowBase = avkHeapBase : copy\windowBytes = avkHeapBytes
          copy\sourceBase = sourceBase : copy\sourceBytes = avkOpSourceBytes[o]
          copy\sourcePitch = avkOpBufferPitch[o]
          copy\destinationBase = avkHeapBase + avkMemOffset[avkImgMemSlot[target]] + avkImgMemOffset[target]
          copy\destinationBytes = avkImgSize[target]
          copy\width = avkImgW[target] : copy\height = avkImgH[target]
          copy\destinationLayout = avkImgBackendLayout[target]
          copy\paddedWidth = avkImgPaddedW[target] : copy\paddedHeight = avkImgPaddedH[target]
          copy\timeoutUs = 250000
          If avkBackendImageCopyValidate(@copy) <> 0
            ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an invalid optimal-image TFU source, destination or layout (Anvil code -20004); nothing was submitted.")
          EndIf
          EndIf
        ElseIf avkImgTiling[target] = #VK_IMAGE_TILING_LINEAR
          copyBytes = avkOpSourcePitch[o]
          sourcePitch = avkOpBufferPitch[o]
          copyRows = avkOpRows[o]
          If copyBytes < 1 Or sourcePitch < copyBytes Or copyRows < 1 Or (copyRows - 1) * sourcePitch + copyBytes <> avkOpSourceBytes[o]
            ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an invalid linear buffer-to-image row shape (Anvil code -20004); nothing was submitted.")
          EndIf
          destinationPitch = avkImgPitch[target]
          If copyBytes > destinationPitch Or avkOpDstOffset[o] < 0 Or avkOpDstOffset[o] + (copyRows - 1) * destinationPitch + copyBytes > avkImgSize[target]
            ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an invalid linear buffer-to-image destination row span (Anvil code -20004); nothing was submitted.")
          EndIf
          destinationBase = avkHeapBase + avkMemOffset[avkImgMemSlot[target]] + avkImgMemOffset[target] + avkOpDstOffset[o]
          If avkImageRowsOverlap(sourceBase, sourcePitch, copyBytes, copyRows, destinationBase, destinationPitch, copyBytes, copyRows) <> 0
            ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkQueueSubmit found overlapping buffer-to-image source and destination memory (Anvil code -20001); nothing was submitted.")
          EndIf
          other = avkOpNext[o]
          While other <> 0
            If avkOpKind[other] = #ANVIL_VK_OP_COPY_BUFFER_IMAGE And avkOpCopyGroup[other] = avkOpCopyGroup[o]
              otherBytes = avkOpSourcePitch[other]
              otherRows = avkOpRows[other]
              If otherBytes < 1 Or otherRows < 1 Or avkCopyBufferResolve(avkOpBuffer[other], d, avkOpBufferOffset[other], avkOpSourceBytes[other], @otherSourceBase) = 0
                ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found a stale source in the buffer-to-image array (Anvil code -20004); nothing was submitted.")
              EndIf
              otherDestinationBase = avkHeapBase + avkMemOffset[avkImgMemSlot[target]] + avkImgMemOffset[target] + avkOpDstOffset[other]
              If avkImageRowsOverlap(sourceBase, sourcePitch, copyBytes, copyRows, otherDestinationBase, destinationPitch, otherBytes, otherRows) <> 0 Or avkImageRowsOverlap(otherSourceBase, avkOpBufferPitch[other], otherBytes, otherRows, destinationBase, destinationPitch, copyBytes, copyRows) <> 0 Or avkImageRowsOverlap(destinationBase, destinationPitch, copyBytes, copyRows, otherDestinationBase, destinationPitch, otherBytes, otherRows) <> 0
                ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkQueueSubmit found overlapping source and destination memory or two destinations in one buffer-to-image array (Anvil code -20001); no DMA was started.")
              EndIf
            EndIf
            other = avkOpNext[other]
          Wend
        Else
          ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an unsupported buffer-to-image destination tiling (Anvil code -20004); nothing was submitted.")
        EndIf
      EndIf
      o = avkOpNext[o]
    Wend
  EndIf
  o = avkCbOpHead[c]
  While o <> 0
  If avkOpKind[o] = #ANVIL_VK_OP_COPY_IMAGE
    imageCopyOp = o
    sourceImageSlot = avkRefSlot[avkRefIndex(c, avkOpRef[imageCopyOp])]
    destinationImageSlot = avkRefSlot[avkRefIndex(c, avkOpDstRef[imageCopyOp])]
    If sourceImageSlot < 1 Or destinationImageSlot < 1 Or avkImgBound[sourceImageSlot] = 0 Or avkImgBound[destinationImageSlot] = 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found a stale or incompatible image-copy resource (Anvil code -20004); nothing was submitted.")
    EndIf
    If avkImgTiling[sourceImageSlot] = #VK_IMAGE_TILING_OPTIMAL And avkImgTiling[destinationImageSlot] = #VK_IMAGE_TILING_OPTIMAL
      If avkOpRows[imageCopyOp] = 1 Or avkOpRows[imageCopyOp] = 3 Or avkOpRows[imageCopyOp] = 6
        copyBytes = avkOpSourceBytes[imageCopyOp]
        copyRows = avkOpSourcePitch[imageCopyOp]
        If copyBytes < 4 Or (copyBytes % 4) <> 0 Or copyRows < 1 Or avkOpImageX[imageCopyOp] < 0 Or avkOpImageY[imageCopyOp] < 0 Or avkOpBufferOffset[imageCopyOp] < 0 Or avkOpBufferPitch[imageCopyOp] < 0 Or avkOpImageX[imageCopyOp] > avkImgW[sourceImageSlot] - copyBytes / 4 Or avkOpImageY[imageCopyOp] > avkImgH[sourceImageSlot] - copyRows Or avkOpBufferOffset[imageCopyOp] > avkImgW[destinationImageSlot] - copyBytes / 4 Or avkOpBufferPitch[imageCopyOp] > avkImgH[destinationImageSlot] - copyRows
          ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an invalid partial optimal-image rectangle (Anvil code -20004); nothing was submitted.")
        EndIf
        If avkOpRows[imageCopyOp] = 3
          If copyBytes > 16 Or copyRows > 4 Or (avkOpImageX[imageCopyOp] % 4) + copyBytes / 4 > 4 Or (avkOpImageY[imageCopyOp] % 4) + copyRows > 4 Or (avkOpBufferOffset[imageCopyOp] % 4) + copyBytes / 4 > 4 Or (avkOpBufferPitch[imageCopyOp] % 4) + copyRows > 4
            ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found a micro copy crossing a source or destination UIF utile (Anvil code -20004); nothing was submitted.")
          EndIf
        ElseIf avkOpRows[imageCopyOp] = 6
          If (copyBytes % 16) = 0 And (copyRows % 4) = 0 Or (avkOpImageX[imageCopyOp] % 4) <> 0 Or (avkOpImageY[imageCopyOp] % 4) <> 0 Or (avkOpBufferOffset[imageCopyOp] % 4) <> 0 Or (avkOpBufferPitch[imageCopyOp] % 4) <> 0 Or ((copyBytes - 4) / 16 + 1) * ((copyRows - 1) / 4 + 1) > #ANVIL_VK_TILED_RECT_MAX_UTILES Or ((copyBytes % 16) <> 0 And (avkOpImageX[imageCopyOp] <> avkImgW[sourceImageSlot] - copyBytes / 4 Or avkOpBufferOffset[imageCopyOp] <> avkImgW[destinationImageSlot] - copyBytes / 4)) Or ((copyRows % 4) <> 0 And (avkOpImageY[imageCopyOp] <> avkImgH[sourceImageSlot] - copyRows Or avkOpBufferPitch[imageCopyOp] <> avkImgH[destinationImageSlot] - copyRows))
            ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found invalid short optimal-image edge tiles (Anvil code -20004); nothing was submitted.")
          EndIf
        ElseIf copyBytes < 16 Or (copyBytes % 16) <> 0 Or copyRows < 4 Or (copyRows % 4) <> 0 Or (avkOpImageX[imageCopyOp] % 4) <> 0 Or (avkOpImageY[imageCopyOp] % 4) <> 0 Or (avkOpBufferOffset[imageCopyOp] % 4) <> 0 Or (avkOpBufferPitch[imageCopyOp] % 4) <> 0 Or ((copyBytes / 16) * (copyRows / 4)) > #ANVIL_VK_TILED_RECT_MAX_UTILES
          ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found unaligned or excessive partial optimal-image tiles (Anvil code -20004); nothing was submitted.")
        EndIf
        sourceBase = avkHeapBase + avkMemOffset[avkImgMemSlot[sourceImageSlot]] + avkImgMemOffset[sourceImageSlot]
        destinationBase = avkHeapBase + avkMemOffset[avkImgMemSlot[destinationImageSlot]] + avkImgMemOffset[destinationImageSlot]
        If avkImageRowsOverlap(sourceBase, avkImgSize[sourceImageSlot], avkImgSize[sourceImageSlot], 1, destinationBase, avkImgSize[destinationImageSlot], avkImgSize[destinationImageSlot], 1) <> 0
          ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkQueueSubmit found overlapping optimal-image allocations (Anvil code -20001); nothing was submitted.")
        EndIf
        tiledRect\windowBase = avkHeapBase : tiledRect\windowBytes = avkHeapBytes
        tiledRect\sourceBase = sourceBase : tiledRect\sourceBytes = avkImgSize[sourceImageSlot]
        tiledRect\destinationBase = destinationBase : tiledRect\destinationBytes = avkImgSize[destinationImageSlot]
        tiledRect\width = avkImgW[sourceImageSlot] : tiledRect\height = avkImgH[sourceImageSlot]
        tiledRect\sourceLayout = avkImgBackendLayout[sourceImageSlot] : tiledRect\destinationLayout = avkImgBackendLayout[destinationImageSlot]
        tiledRect\paddedWidth = avkImgPaddedW[sourceImageSlot] : tiledRect\paddedHeight = avkImgPaddedH[sourceImageSlot]
        tiledRect\sourceX = avkOpImageX[imageCopyOp] : tiledRect\sourceY = avkOpImageY[imageCopyOp]
        tiledRect\destinationX = avkOpBufferOffset[imageCopyOp] : tiledRect\destinationY = avkOpBufferPitch[imageCopyOp]
        tiledRect\regionWidth = copyBytes / 4 : tiledRect\regionHeight = copyRows
        If avkImgW[sourceImageSlot] <> avkImgW[destinationImageSlot] Or avkImgH[sourceImageSlot] <> avkImgH[destinationImageSlot] Or avkImgPaddedW[sourceImageSlot] <> avkImgPaddedW[destinationImageSlot] Or avkImgPaddedH[sourceImageSlot] <> avkImgPaddedH[destinationImageSlot]
          ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an invalid partial optimal-image DMA copy or changed image layout (Anvil code -20004); nothing was submitted.")
        EndIf
        If avkOpRows[imageCopyOp] = 3
          If avkBackendTiledMicroCopyValidate(@tiledRect) <> 0 : ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an invalid one-utile optimal-image DMA copy (Anvil code -20004); nothing was submitted.") : EndIf
        ElseIf avkOpRows[imageCopyOp] = 6
          If avkBackendTiledEdgeTailCopyValidate(@tiledRect) <> 0 : ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found invalid optimal-image edge-tail DMA preflight (Anvil code -20004); nothing was submitted.") : EndIf
        Else
          If avkBackendTiledRectCopyValidate(@tiledRect) <> 0 : ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an invalid partial optimal-image DMA copy (Anvil code -20004); nothing was submitted.") : EndIf
        EndIf
      Else
      If copies + imageCopies + bufferCopies + readbacks > 1 And avkBackendImageCopyBatchReady() = 0
        ProcedureReturn avkFault(#VK_ERROR_FEATURE_NOT_PRESENT, "vkQueueSubmit cannot order optimal-image copies while the backend holds a pending transfer (VkResult -8); nothing was submitted.")
      EndIf
      tiledCopy\windowBase = avkHeapBase : tiledCopy\windowBytes = avkHeapBytes
      tiledCopy\sourceBase = avkHeapBase + avkMemOffset[avkImgMemSlot[sourceImageSlot]] + avkImgMemOffset[sourceImageSlot]
      tiledCopy\sourceBytes = avkImgSize[sourceImageSlot]
      tiledCopy\destinationBase = avkHeapBase + avkMemOffset[avkImgMemSlot[destinationImageSlot]] + avkImgMemOffset[destinationImageSlot]
      tiledCopy\destinationBytes = avkImgSize[destinationImageSlot]
      tiledCopy\width = avkImgW[sourceImageSlot] : tiledCopy\height = avkImgH[sourceImageSlot]
      tiledCopy\sourceLayout = avkImgBackendLayout[sourceImageSlot] : tiledCopy\destinationLayout = avkImgBackendLayout[destinationImageSlot]
      tiledCopy\paddedWidth = avkImgPaddedW[sourceImageSlot] : tiledCopy\paddedHeight = avkImgPaddedH[sourceImageSlot]
      tiledCopy\timeoutUs = 250000
      If avkImgW[sourceImageSlot] <> avkImgW[destinationImageSlot] Or avkImgH[sourceImageSlot] <> avkImgH[destinationImageSlot] Or avkImgPaddedW[sourceImageSlot] <> avkImgPaddedW[destinationImageSlot] Or avkImgPaddedH[sourceImageSlot] <> avkImgPaddedH[destinationImageSlot] Or avkBackendTiledImageCopyValidate(@tiledCopy) <> 0
        ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an invalid optimal-image TFU copy or changed resource layout (Anvil code -20004); nothing was submitted.")
      EndIf
      EndIf
    ElseIf avkImgTiling[sourceImageSlot] = #VK_IMAGE_TILING_OPTIMAL And avkImgTiling[destinationImageSlot] = #VK_IMAGE_TILING_LINEAR
      copyBytes = avkOpSourceBytes[imageCopyOp]
      copyRows = avkOpSourcePitch[imageCopyOp]
      destinationPitch = avkImgPitch[destinationImageSlot]
      If copyBytes < 4 Or (copyBytes % 4) <> 0 Or copyRows < 1 Or avkOpImageX[imageCopyOp] < 0 Or avkOpImageY[imageCopyOp] < 0 Or avkOpBufferOffset[imageCopyOp] < 0 Or avkOpBufferPitch[imageCopyOp] < 0 Or avkOpImageX[imageCopyOp] > avkImgW[sourceImageSlot] - copyBytes / 4 Or avkOpImageY[imageCopyOp] > avkImgH[sourceImageSlot] - copyRows Or avkOpBufferOffset[imageCopyOp] > avkImgW[destinationImageSlot] - copyBytes / 4 Or avkOpBufferPitch[imageCopyOp] > avkImgH[destinationImageSlot] - copyRows
        ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an invalid optimal-to-linear image-copy rectangle (Anvil code -20004); nothing was submitted.")
      EndIf
      If avkOpDstOffset[imageCopyOp] <> avkOpBufferPitch[imageCopyOp] * destinationPitch + avkOpBufferOffset[imageCopyOp] * #ANVIL_VK_BGRA8_TEXEL_BYTES
        ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an altered optimal-to-linear destination offset (Anvil code -20004); nothing was submitted.")
      EndIf
      If avkOpRows[imageCopyOp] = 4
        If copyBytes > 16 Or copyRows > 4 Or (avkOpImageX[imageCopyOp] % 4) + copyBytes / 4 > 4 Or (avkOpImageY[imageCopyOp] % 4) + copyRows > 4 Or destinationPitch - copyBytes > 32767
          ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an optimal-to-linear micro copy crossing a UIF utile or DMA stride (Anvil code -20004); nothing was submitted.")
        EndIf
      ElseIf (avkOpImageX[imageCopyOp] % 4) <> 0 Or (avkOpImageY[imageCopyOp] % 4) <> 0 Or ((copyBytes % 16) <> 0 And avkOpImageX[imageCopyOp] <> avkImgW[sourceImageSlot] - copyBytes / 4) Or ((copyRows % 4) <> 0 And avkOpImageY[imageCopyOp] <> avkImgH[sourceImageSlot] - copyRows)
        ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an unaligned optimal-to-linear image-copy rectangle (Anvil code -20004); nothing was submitted.")
      EndIf
      If copyBytes > destinationPitch Or avkOpDstOffset[imageCopyOp] + (copyRows - 1) * destinationPitch + copyBytes > avkImgSize[destinationImageSlot]
        ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found optimal-to-linear destination rows outside the image allocation (Anvil code -20004); nothing was submitted.")
      EndIf
      sourceBase = avkHeapBase + avkMemOffset[avkImgMemSlot[sourceImageSlot]] + avkImgMemOffset[sourceImageSlot]
      destinationBase = avkHeapBase + avkMemOffset[avkImgMemSlot[destinationImageSlot]] + avkImgMemOffset[destinationImageSlot]
      If avkImageRowsOverlap(sourceBase, avkImgSize[sourceImageSlot], avkImgSize[sourceImageSlot], 1, destinationBase, avkImgSize[destinationImageSlot], avkImgSize[destinationImageSlot], 1) <> 0
        ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkQueueSubmit found overlapping optimal-to-linear image allocations (Anvil code -20001); nothing was submitted.")
      EndIf
      tiledRead\windowBase = avkHeapBase : tiledRead\windowBytes = avkHeapBytes
      tiledRead\sourceBase = sourceBase
      tiledRead\sourceBytes = avkImgSize[sourceImageSlot]
      tiledRead\destinationBase = destinationBase + avkOpDstOffset[imageCopyOp]
      tiledRead\destinationBytes = (copyRows - 1) * destinationPitch + copyBytes
      tiledRead\destinationPitch = destinationPitch
      tiledRead\width = avkImgW[sourceImageSlot] : tiledRead\height = avkImgH[sourceImageSlot]
      tiledRead\sourceLayout = avkImgBackendLayout[sourceImageSlot]
      tiledRead\paddedWidth = avkImgPaddedW[sourceImageSlot] : tiledRead\paddedHeight = avkImgPaddedH[sourceImageSlot]
      tiledRead\sourceX = avkOpImageX[imageCopyOp] : tiledRead\sourceY = avkOpImageY[imageCopyOp]
      tiledRead\regionWidth = copyBytes / #ANVIL_VK_BGRA8_TEXEL_BYTES : tiledRead\regionHeight = copyRows
      If avkImgW[sourceImageSlot] <> avkImgW[destinationImageSlot] Or avkImgH[sourceImageSlot] <> avkImgH[destinationImageSlot]
        ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an invalid optimal-to-linear DMA readback or changed image layout (Anvil code -20004); nothing was submitted.")
      EndIf
      If avkOpRows[imageCopyOp] = 4
        If avkBackendTiledMicroReadbackValidate(@tiledRead) <> 0 : ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an invalid optimal-to-linear one-utile DMA copy (Anvil code -20004); nothing was submitted.") : EndIf
      Else
        If avkBackendTiledReadbackValidate(@tiledRead) <> 0 : ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an invalid optimal-to-linear DMA readback (Anvil code -20004); nothing was submitted.") : EndIf
      EndIf
    ElseIf avkImgTiling[sourceImageSlot] = #VK_IMAGE_TILING_LINEAR And avkImgTiling[destinationImageSlot] = #VK_IMAGE_TILING_OPTIMAL
      If avkOpRows[imageCopyOp] = 2 Or avkOpRows[imageCopyOp] = 5
        copyBytes = avkOpSourceBytes[imageCopyOp] : copyRows = avkOpSourcePitch[imageCopyOp]
        sourcePitch = avkImgPitch[sourceImageSlot]
        If copyBytes < 4 Or (copyBytes % 4) <> 0 Or copyRows < 1 Or avkOpImageX[imageCopyOp] < 0 Or avkOpImageY[imageCopyOp] < 0 Or avkOpBufferOffset[imageCopyOp] < 0 Or avkOpBufferPitch[imageCopyOp] < 0 Or avkOpImageX[imageCopyOp] > avkImgW[sourceImageSlot] - copyBytes / 4 Or avkOpImageY[imageCopyOp] > avkImgH[sourceImageSlot] - copyRows Or avkOpBufferOffset[imageCopyOp] > avkImgW[destinationImageSlot] - copyBytes / 4 Or avkOpBufferPitch[imageCopyOp] > avkImgH[destinationImageSlot] - copyRows
          ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an invalid partial linear-to-optimal rectangle (Anvil code -20004); nothing was submitted.")
        EndIf
        If sourcePitch < avkImgW[sourceImageSlot] * 4 Or (sourcePitch % 4) <> 0 Or avkImgSize[sourceImageSlot] < sourcePitch * avkImgH[sourceImageSlot] Or avkOpImageY[imageCopyOp] * sourcePitch + avkOpImageX[imageCopyOp] * 4 + (copyRows - 1) * sourcePitch + copyBytes > avkImgSize[sourceImageSlot]
          ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found changed linear source pitch or rows outside its allocation (Anvil code -20004); nothing was submitted.")
        EndIf
        If avkOpRows[imageCopyOp] = 5
          If copyBytes > 16 Or copyRows > 4 Or (avkOpBufferOffset[imageCopyOp] % 4) + copyBytes / 4 > 4 Or (avkOpBufferPitch[imageCopyOp] % 4) + copyRows > 4 Or sourcePitch - copyBytes > 32767
            ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found a linear-to-optimal micro copy crossing a UIF utile or DMA stride (Anvil code -20004); nothing was submitted.")
          EndIf
        ElseIf copyBytes < 16 Or (copyBytes % 16) <> 0 Or copyRows < 4 Or (copyRows % 4) <> 0 Or (avkOpBufferOffset[imageCopyOp] % 4) <> 0 Or (avkOpBufferPitch[imageCopyOp] % 4) <> 0 Or (copyBytes / 16) * (copyRows / 4) > #ANVIL_VK_TILED_RECT_MAX_UTILES Or sourcePitch - 16 > 32767
          ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found unaligned or excessive linear-to-optimal tiles or a changed source pitch (Anvil code -20004); nothing was submitted.")
        EndIf
        sourceBase = avkHeapBase + avkMemOffset[avkImgMemSlot[sourceImageSlot]] + avkImgMemOffset[sourceImageSlot]
        destinationBase = avkHeapBase + avkMemOffset[avkImgMemSlot[destinationImageSlot]] + avkImgMemOffset[destinationImageSlot]
        If avkImageRowsOverlap(sourceBase, avkImgSize[sourceImageSlot], avkImgSize[sourceImageSlot], 1, destinationBase, avkImgSize[destinationImageSlot], avkImgSize[destinationImageSlot], 1) <> 0
          ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkQueueSubmit found overlapping linear-to-optimal image allocations (Anvil code -20001); nothing was submitted.")
        EndIf
        linearTiledRect\windowBase = avkHeapBase : linearTiledRect\windowBytes = avkHeapBytes
        linearTiledRect\sourceBase = sourceBase : linearTiledRect\sourceBytes = avkImgSize[sourceImageSlot] : linearTiledRect\sourcePitch = sourcePitch
        linearTiledRect\sourceViewWidth = avkImgW[sourceImageSlot] : linearTiledRect\sourceViewHeight = avkImgH[sourceImageSlot]
        linearTiledRect\destinationBase = destinationBase : linearTiledRect\destinationBytes = avkImgSize[destinationImageSlot]
        linearTiledRect\width = avkImgW[sourceImageSlot] : linearTiledRect\height = avkImgH[sourceImageSlot]
        linearTiledRect\destinationLayout = avkImgBackendLayout[destinationImageSlot]
        linearTiledRect\paddedWidth = avkImgPaddedW[destinationImageSlot] : linearTiledRect\paddedHeight = avkImgPaddedH[destinationImageSlot]
        linearTiledRect\sourceX = avkOpImageX[imageCopyOp] : linearTiledRect\sourceY = avkOpImageY[imageCopyOp]
        linearTiledRect\destinationX = avkOpBufferOffset[imageCopyOp] : linearTiledRect\destinationY = avkOpBufferPitch[imageCopyOp]
        linearTiledRect\regionWidth = copyBytes / 4 : linearTiledRect\regionHeight = copyRows
        If avkImgW[sourceImageSlot] <> avkImgW[destinationImageSlot] Or avkImgH[sourceImageSlot] <> avkImgH[destinationImageSlot]
          ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found changed linear-to-optimal image extents (Anvil code -20004); nothing was submitted.")
        EndIf
        If avkOpRows[imageCopyOp] = 5
          If avkBackendLinearTiledMicroCopyValidate(@linearTiledRect) <> 0 : ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an invalid linear-to-optimal one-utile DMA copy (Anvil code -20004); nothing was submitted.") : EndIf
        ElseIf avkBackendLinearTiledRectCopyValidate(@linearTiledRect) <> 0
          ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an invalid linear-to-optimal DMA scatter or changed image layout (Anvil code -20004); nothing was submitted.")
        EndIf
      Else
      If copies + imageCopies + bufferCopies + readbacks > 1 And avkBackendImageCopyBatchReady() = 0
        ProcedureReturn avkFault(#VK_ERROR_FEATURE_NOT_PRESENT, "vkQueueSubmit cannot order linear-to-optimal image copies while the backend holds a pending transfer (VkResult -8); nothing was submitted.")
      EndIf
      copy\windowBase = avkHeapBase : copy\windowBytes = avkHeapBytes
      copy\sourceBase = avkHeapBase + avkMemOffset[avkImgMemSlot[sourceImageSlot]] + avkImgMemOffset[sourceImageSlot]
      copy\sourceBytes = avkImgSize[sourceImageSlot]
      copy\sourcePitch = avkImgPitch[sourceImageSlot]
      copy\destinationBase = avkHeapBase + avkMemOffset[avkImgMemSlot[destinationImageSlot]] + avkImgMemOffset[destinationImageSlot]
      copy\destinationBytes = avkImgSize[destinationImageSlot]
      copy\width = avkImgW[sourceImageSlot] : copy\height = avkImgH[sourceImageSlot]
      copy\destinationLayout = avkImgBackendLayout[destinationImageSlot]
      copy\paddedWidth = avkImgPaddedW[destinationImageSlot] : copy\paddedHeight = avkImgPaddedH[destinationImageSlot]
      copy\timeoutUs = 250000
      If avkImgW[sourceImageSlot] <> avkImgW[destinationImageSlot] Or avkImgH[sourceImageSlot] <> avkImgH[destinationImageSlot] Or avkBackendImageCopyValidate(@copy) <> 0
        ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an invalid linear-to-optimal TFU source, destination or layout (Anvil code -20004); nothing was submitted.")
      EndIf
      EndIf
    ElseIf avkImgTiling[sourceImageSlot] = #VK_IMAGE_TILING_LINEAR And avkImgTiling[destinationImageSlot] = #VK_IMAGE_TILING_LINEAR
    sourcePitch = avkImgPitch[sourceImageSlot]
    destinationPitch = avkImgPitch[destinationImageSlot]
    copyBytes = avkOpSourceBytes[imageCopyOp]
    copyRows = avkOpSourcePitch[imageCopyOp]
    If copyBytes < 1 Or copyRows < 1 Or copyBytes > sourcePitch Or copyBytes > destinationPitch Or avkOpBufferOffset[imageCopyOp] < 0 Or avkOpDstOffset[imageCopyOp] < 0 Or avkOpBufferOffset[imageCopyOp] + (copyRows - 1) * sourcePitch + copyBytes > avkImgSize[sourceImageSlot] Or avkOpDstOffset[imageCopyOp] + (copyRows - 1) * destinationPitch + copyBytes > avkImgSize[destinationImageSlot]
      ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an invalid image-copy rectangle or changed image pitch (Anvil code -20004); nothing was submitted.")
    EndIf
    sourceBase = avkHeapBase + avkMemOffset[avkImgMemSlot[sourceImageSlot]] + avkImgMemOffset[sourceImageSlot] + avkOpBufferOffset[imageCopyOp]
    destinationBase = avkHeapBase + avkMemOffset[avkImgMemSlot[destinationImageSlot]] + avkImgMemOffset[destinationImageSlot] + avkOpDstOffset[imageCopyOp]
    ; The accessed source and destination row intervals must be disjoint,
    ; including when two distinct VkImage handles alias one allocation.
    sourceRow = 0 : destinationRow = 0
    While sourceRow < copyRows And destinationRow < copyRows
      sourceRowBase = sourceBase + sourceRow * sourcePitch
      destinationRowBase = destinationBase + destinationRow * destinationPitch
      If sourceRowBase < destinationRowBase + copyBytes And destinationRowBase < sourceRowBase + copyBytes
        ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkQueueSubmit found overlapping image-copy source and destination texels (Anvil code -20001); nothing was submitted.")
      EndIf
      If sourceRowBase + copyBytes <= destinationRowBase
        sourceRow = sourceRow + 1
      Else
        destinationRow = destinationRow + 1
      EndIf
    Wend
    other = avkOpNext[o]
    While other <> 0
      If avkOpKind[other] = #ANVIL_VK_OP_COPY_IMAGE And avkOpCopyGroup[other] = avkOpCopyGroup[o]
        otherSourceBase = avkHeapBase + avkMemOffset[avkImgMemSlot[sourceImageSlot]] + avkImgMemOffset[sourceImageSlot] + avkOpBufferOffset[other]
        otherDestinationBase = avkHeapBase + avkMemOffset[avkImgMemSlot[destinationImageSlot]] + avkImgMemOffset[destinationImageSlot] + avkOpDstOffset[other]
        otherBytes = avkOpSourceBytes[other]
        otherRows = avkOpSourcePitch[other]
        If avkImageRowsOverlap(sourceBase, sourcePitch, copyBytes, copyRows, otherDestinationBase, destinationPitch, otherBytes, otherRows) <> 0 Or avkImageRowsOverlap(destinationBase, destinationPitch, copyBytes, copyRows, otherSourceBase, sourcePitch, otherBytes, otherRows) <> 0 Or avkImageRowsOverlap(destinationBase, destinationPitch, copyBytes, copyRows, otherDestinationBase, destinationPitch, otherBytes, otherRows) <> 0
          ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkQueueSubmit found overlapping accessed texels across one vkCmdCopyImage region array (Anvil code -20001); no DMA was started.")
        EndIf
      EndIf
      other = avkOpNext[other]
    Wend
    Else
      ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found mismatched image-copy tiling (Anvil code -20004); nothing was submitted.")
    EndIf
  EndIf
  o = avkOpNext[o]
  Wend
  If readbacks > 0
    o = avkCbOpHead[c]
    While o <> 0
      If avkOpKind[o] = #ANVIL_VK_OP_COPY_IMAGE_BUFFER
        sourceImageSlot = avkRefSlot[avkRefIndex(c, avkOpRef[o])]
        copyBytes = avkOpSourceBytes[o]
        copyRows = avkOpSourcePitch[o]
        If sourceImageSlot < 1 Or avkImgBound[sourceImageSlot] = 0
          ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found a stale image-to-buffer source (Anvil code -20004); nothing was submitted.")
        EndIf
        If avkImgTiling[sourceImageSlot] = #VK_IMAGE_TILING_OPTIMAL
          destinationPitch = avkOpBufferPitch[o]
          If copyBytes < 4 Or (copyBytes % 4) <> 0 Or copyRows < 1 Or destinationPitch < copyBytes Or avkOpImageX[o] < 0 Or avkOpImageY[o] < 0 Or avkOpImageX[o] > avkImgW[sourceImageSlot] - copyBytes / 4 Or avkOpImageY[o] > avkImgH[sourceImageSlot] - copyRows
            ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an invalid optimal-image readback rectangle (Anvil code -20004); nothing was submitted.")
          EndIf
          If avkOpRows[o] = 1
            If copyBytes > 16 Or copyRows > 4 Or (avkOpImageX[o] % 4) + copyBytes / 4 > 4 Or (avkOpImageY[o] % 4) + copyRows > 4 Or destinationPitch - copyBytes > 32767
              ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an interior readback crossing a UIF utile or DMA stride (Anvil code -20004); nothing was submitted.")
            EndIf
          ElseIf (avkOpImageX[o] % 4) <> 0 Or (avkOpImageY[o] % 4) <> 0 Or ((copyBytes % 16) <> 0 And avkOpImageX[o] <> avkImgW[sourceImageSlot] - copyBytes / 4) Or ((copyRows % 4) <> 0 And avkOpImageY[o] <> avkImgH[sourceImageSlot] - copyRows)
            ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an unaligned optimal-image readback rectangle (Anvil code -20004); nothing was submitted.")
          EndIf
          If avkTransferBufferResolve(avkOpBuffer[o], d, #VK_BUFFER_USAGE_TRANSFER_DST_BIT, avkOpBufferOffset[o], (copyRows - 1) * destinationPitch + copyBytes, @destinationBase) = 0
            ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found a stale optimal-image readback buffer (Anvil code -20004); nothing was submitted.")
          EndIf
          tiledRead\windowBase = avkHeapBase : tiledRead\windowBytes = avkHeapBytes
          tiledRead\sourceBase = avkHeapBase + avkMemOffset[avkImgMemSlot[sourceImageSlot]] + avkImgMemOffset[sourceImageSlot]
          tiledRead\sourceBytes = avkImgSize[sourceImageSlot]
          tiledRead\destinationBase = destinationBase
          tiledRead\destinationBytes = (copyRows - 1) * destinationPitch + copyBytes
          tiledRead\destinationPitch = destinationPitch
          tiledRead\width = avkImgW[sourceImageSlot] : tiledRead\height = avkImgH[sourceImageSlot]
          tiledRead\sourceLayout = avkImgBackendLayout[sourceImageSlot]
          tiledRead\paddedWidth = avkImgPaddedW[sourceImageSlot] : tiledRead\paddedHeight = avkImgPaddedH[sourceImageSlot]
          tiledRead\sourceX = avkOpImageX[o] : tiledRead\sourceY = avkOpImageY[o]
          tiledRead\regionWidth = copyBytes / 4 : tiledRead\regionHeight = copyRows
          If avkOpRows[o] = 1
            destinationBufferBase = AnvilVkBufferAddress(avkOpBuffer[o]) : destinationBufferBytes = AnvilVkBufferSize(avkOpBuffer[o])
            If destinationBufferBase <= 0 Or destinationBufferBytes < tiledRead\destinationBytes Or tiledRead\sourceBase < destinationBufferBase + destinationBufferBytes And destinationBufferBase < tiledRead\sourceBase + tiledRead\sourceBytes
              ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkQueueSubmit found overlapping full image and buffer ranges for an interior readback (Anvil code -20001); nothing was submitted.")
            EndIf
            If avkBackendTiledMicroReadbackValidate(@tiledRead) <> 0
              ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an invalid one-utile optimal-image DMA readback (Anvil code -20004); nothing was submitted.")
            EndIf
          Else
            If avkBackendTiledReadbackValidate(@tiledRead) <> 0
              ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an invalid optimal-image DMA readback (Anvil code -20004); nothing was submitted.")
            EndIf
          EndIf
          o = avkOpNext[o]
          Continue
        EndIf
        If avkImgTiling[sourceImageSlot] <> #VK_IMAGE_TILING_LINEAR
          ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an unsupported image-to-buffer tiling (Anvil code -20004); nothing was submitted.")
        EndIf
        sourcePitch = avkImgPitch[sourceImageSlot]
        destinationPitch = avkOpBufferPitch[o]
        If copyBytes < 1 Or copyRows < 1 Or copyBytes > sourcePitch Or destinationPitch < copyBytes Or avkOpDstOffset[o] < 0 Or avkOpDstOffset[o] + (copyRows - 1) * sourcePitch + copyBytes > avkImgSize[sourceImageSlot]
          ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an invalid image-to-buffer rectangle or changed image pitch (Anvil code -20004); nothing was submitted.")
        EndIf
        If avkTransferBufferResolve(avkOpBuffer[o], d, #VK_BUFFER_USAGE_TRANSFER_DST_BIT, avkOpBufferOffset[o], (copyRows - 1) * destinationPitch + copyBytes, @destinationBase) = 0
          ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found a stale or undersized image-to-buffer destination (Anvil code -20004); nothing was submitted.")
        EndIf
        sourceBase = avkHeapBase + avkMemOffset[avkImgMemSlot[sourceImageSlot]] + avkImgMemOffset[sourceImageSlot] + avkOpDstOffset[o]
        If avkImageRowsOverlap(sourceBase, sourcePitch, copyBytes, copyRows, destinationBase, destinationPitch, copyBytes, copyRows) <> 0
          ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkQueueSubmit found overlapping image-to-buffer source and destination memory (Anvil code -20001); nothing was submitted.")
        EndIf
        other = avkOpNext[o]
        While other <> 0
          If avkOpKind[other] = #ANVIL_VK_OP_COPY_IMAGE_BUFFER And avkOpCopyGroup[other] = avkOpCopyGroup[o]
            otherBytes = avkOpSourceBytes[other]
            otherRows = avkOpSourcePitch[other]
            otherSourceBase = avkHeapBase + avkMemOffset[avkImgMemSlot[sourceImageSlot]] + avkImgMemOffset[sourceImageSlot] + avkOpDstOffset[other]
            If avkTransferBufferResolve(avkOpBuffer[other], d, #VK_BUFFER_USAGE_TRANSFER_DST_BIT, avkOpBufferOffset[other], (otherRows - 1) * avkOpBufferPitch[other] + otherBytes, @otherDestinationBase) = 0
              ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found a stale image-to-buffer destination in the readback array (Anvil code -20004); nothing was submitted.")
            EndIf
            If avkImageRowsOverlap(sourceBase, sourcePitch, copyBytes, copyRows, otherDestinationBase, avkOpBufferPitch[other], otherBytes, otherRows) <> 0 Or avkImageRowsOverlap(otherSourceBase, sourcePitch, otherBytes, otherRows, destinationBase, destinationPitch, copyBytes, copyRows) <> 0 Or avkImageRowsOverlap(destinationBase, destinationPitch, copyBytes, copyRows, otherDestinationBase, avkOpBufferPitch[other], otherBytes, otherRows) <> 0
              ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkQueueSubmit found overlapping source and destination memory or two destinations in one readback array (Anvil code -20001); no DMA was started.")
            EndIf
          EndIf
          other = avkOpNext[other]
        Wend
      EndIf
      o = avkOpNext[o]
    Wend
  EndIf
  If bufferCopies > 0
    o = avkCbOpHead[c]
    While o <> 0
      If avkOpKind[o] = #ANVIL_VK_OP_COPY_BUFFER
        If avkTransferBufferResolve(avkOpBuffer[o], d, #VK_BUFFER_USAGE_TRANSFER_SRC_BIT, avkOpBufferOffset[o], avkOpSourceBytes[o], @sourceBase) = 0 Or avkTransferBufferResolve(avkOpDstBuffer[o], d, #VK_BUFFER_USAGE_TRANSFER_DST_BIT, avkOpDstOffset[o], avkOpSourceBytes[o], @destinationBase) = 0
          ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found that a recorded buffer copy now names a stale, unbound or wrong-device buffer or range (Anvil code -20004, stale resource); no copy was submitted.")
        EndIf
        If sourceBase < destinationBase + avkOpSourceBytes[o] And destinationBase < sourceBase + avkOpSourceBytes[o]
          ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkQueueSubmit found overlapping source and destination memory for vkCmdCopyBuffer (Anvil code -20001, overlapping copy); no copy was submitted.")
        EndIf
      ElseIf avkOpKind[o] = #ANVIL_VK_OP_FILL_BUFFER
        If avkTransferBufferResolve(avkOpBuffer[o], d, #VK_BUFFER_USAGE_TRANSFER_DST_BIT, avkOpBufferOffset[o], avkOpSourceBytes[o], @destinationBase) = 0
          ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found that a recorded buffer fill now names a stale, unbound or wrong-device destination (Anvil code -20004, stale resource); no transfer was submitted.")
        EndIf
      ElseIf avkOpKind[o] = #ANVIL_VK_OP_UPDATE_BUFFER
        If avkTransferBufferResolve(avkOpBuffer[o], d, #VK_BUFFER_USAGE_TRANSFER_DST_BIT, avkOpBufferOffset[o], avkOpSourceBytes[o], @destinationBase) = 0
          ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found that a recorded buffer update now names a stale, unbound or wrong-device destination (Anvil code -20004, stale resource); no transfer was submitted.")
        EndIf
      ElseIf avkOpKind[o] = #ANVIL_VK_OP_BUFFER_BARRIER
        If avkBufferBarrierResolve(avkOpBuffer[o], d, avkOpBufferOffset[o], avkOpSourceBytes[o], 0) = 0
          ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found that a recorded buffer memory barrier now names a stale, unbound or wrong-device buffer or range (Anvil code -20004, stale barrier resource); no transfer was submitted.")
        EndIf
      EndIf
      o = avkOpNext[o]
    Wend
  EndIf
  f = 0
  If fence <> #VK_NULL_HANDLE
    f = avkFenceAcquire(d, fence)
    If f <= 0
      avkDrawListDiscard()
      ProcedureReturn f
    EndIf
  EndIf
  If semaphoreReservation <> #VK_NULL_HANDLE
    job = avkSemaphoreCommit(semaphoreReservation)
    If job <> #VK_SUCCESS
      If f > 0 : avkFenceRelease(f) : EndIf
      avkDrawListDiscard()
      ProcedureReturn job
    EndIf
  EndIf
  avkFlightActive = 1
  avkFlightCb = c
  avkFlightFence = f
  avkFlightSemaphoreReservation = semaphoreReservation
  avkCmdState[c] = #ANVIL_VK_CB_PENDING
  avkFlightRetain(c)
  avkDrawListRetain(c)
  avkRenderClearRetain(c)
  avkCopyBufferRetain(c)
  avkSubmitCount = avkSubmitCount + 1
  If avkCbDrawCount[c] > 0
    job = avkDrawListSubmit()
    If job < 0
      avkFlightComplete(0)
      avkFault(#VK_ERROR_DEVICE_LOST, "the graphics device failed while executing a draw (VkResult -4, VK_ERROR_DEVICE_LOST); the command buffer is invalid and its fence is signalled. AnvilVkBackendNativeError() carries the backend's own diagnostic code; inspect that backend's fault and capacity telemetry before resubmitting.")
      ProcedureReturn #VK_ERROR_DEVICE_LOST
    EndIf
    If job = #ANVIL_VK_JOB_DONE
      avkFlightComplete(1)
    EndIf
    ProcedureReturn #VK_SUCCESS
  EndIf
  If avkCbRpDone[c] <> 0
    job = avkRenderClearSubmit()
    If job < 0
      avkFlightComplete(0)
      ProcedureReturn avkFault(#VK_ERROR_DEVICE_LOST, "the graphics device failed while clearing a render-pass attachment (VkResult -4, VK_ERROR_DEVICE_LOST); the command buffer is invalid and its fence is signalled. Inspect the selected backend's fault telemetry before retrying.")
    EndIf
    If job = #ANVIL_VK_JOB_DONE : avkFlightComplete(1) : EndIf
    ProcedureReturn #VK_SUCCESS
  EndIf
  If imageCopies > 0 Or copies > 0 Or bufferCopies > 0 Or readbacks > 0
    o = avkCbOpHead[c]
    While o <> 0
      If avkOpKind[o] = #ANVIL_VK_OP_COPY_IMAGE
        sourceImageSlot = avkRefSlot[avkRefIndex(c, avkOpRef[o])]
        destinationImageSlot = avkRefSlot[avkRefIndex(c, avkOpDstRef[o])]
        If avkImgTiling[sourceImageSlot] = #VK_IMAGE_TILING_OPTIMAL And avkImgTiling[destinationImageSlot] = #VK_IMAGE_TILING_LINEAR
          copyBytes = avkOpSourceBytes[o]
          copyRows = avkOpSourcePitch[o]
          destinationPitch = avkImgPitch[destinationImageSlot]
          tiledRead\windowBase = avkHeapBase : tiledRead\windowBytes = avkHeapBytes
          tiledRead\sourceBase = avkHeapBase + avkMemOffset[avkImgMemSlot[sourceImageSlot]] + avkImgMemOffset[sourceImageSlot]
          tiledRead\sourceBytes = avkImgSize[sourceImageSlot]
          tiledRead\destinationBase = avkHeapBase + avkMemOffset[avkImgMemSlot[destinationImageSlot]] + avkImgMemOffset[destinationImageSlot] + avkOpDstOffset[o]
          tiledRead\destinationBytes = (copyRows - 1) * destinationPitch + copyBytes
          tiledRead\destinationPitch = destinationPitch
          tiledRead\width = avkImgW[sourceImageSlot] : tiledRead\height = avkImgH[sourceImageSlot]
          tiledRead\sourceLayout = avkImgBackendLayout[sourceImageSlot]
          tiledRead\paddedWidth = avkImgPaddedW[sourceImageSlot] : tiledRead\paddedHeight = avkImgPaddedH[sourceImageSlot]
          tiledRead\sourceX = avkOpImageX[o] : tiledRead\sourceY = avkOpImageY[o]
          tiledRead\regionWidth = copyBytes / #ANVIL_VK_BGRA8_TEXEL_BYTES : tiledRead\regionHeight = copyRows
          If avkOpRows[o] = 4
            job = avkBackendSubmitTiledMicroReadback(@tiledRead)
          Else
            job = avkBackendSubmitTiledReadback(@tiledRead)
          EndIf
          If job <> #ANVIL_VK_JOB_DONE
            avkFlightComplete(0)
            ProcedureReturn avkFault(#VK_ERROR_DEVICE_LOST, "the DMA backend failed while copying an optimal Vulkan image to linear memory (VkResult -4); the command buffer was invalidated and its fence signalled.")
          EndIf
        ElseIf avkImgTiling[sourceImageSlot] = #VK_IMAGE_TILING_OPTIMAL
          If avkOpRows[o] = 1 Or avkOpRows[o] = 3 Or avkOpRows[o] = 6
            tiledRect\windowBase = avkHeapBase : tiledRect\windowBytes = avkHeapBytes
            tiledRect\sourceBase = avkHeapBase + avkMemOffset[avkImgMemSlot[sourceImageSlot]] + avkImgMemOffset[sourceImageSlot]
            tiledRect\sourceBytes = avkImgSize[sourceImageSlot]
            tiledRect\destinationBase = avkHeapBase + avkMemOffset[avkImgMemSlot[destinationImageSlot]] + avkImgMemOffset[destinationImageSlot]
            tiledRect\destinationBytes = avkImgSize[destinationImageSlot]
            tiledRect\width = avkImgW[sourceImageSlot] : tiledRect\height = avkImgH[sourceImageSlot]
            tiledRect\sourceLayout = avkImgBackendLayout[sourceImageSlot] : tiledRect\destinationLayout = avkImgBackendLayout[destinationImageSlot]
            tiledRect\paddedWidth = avkImgPaddedW[sourceImageSlot] : tiledRect\paddedHeight = avkImgPaddedH[sourceImageSlot]
            tiledRect\sourceX = avkOpImageX[o] : tiledRect\sourceY = avkOpImageY[o]
            tiledRect\destinationX = avkOpBufferOffset[o] : tiledRect\destinationY = avkOpBufferPitch[o]
            tiledRect\regionWidth = avkOpSourceBytes[o] / 4 : tiledRect\regionHeight = avkOpSourcePitch[o]
            If avkOpRows[o] = 3
              job = avkBackendSubmitTiledMicroCopy(@tiledRect)
            ElseIf avkOpRows[o] = 6
              job = avkBackendSubmitTiledEdgeTailCopy(@tiledRect)
            Else
              job = avkBackendSubmitTiledRectCopy(@tiledRect)
            EndIf
            If job <> #ANVIL_VK_JOB_DONE
              avkFlightComplete(0)
              ProcedureReturn avkFault(#VK_ERROR_DEVICE_LOST, "the guarded DMA backend failed while copying partial optimal-image tiles (VkResult -4); the command buffer was invalidated and its fence signalled.")
            EndIf
          Else
          tiledCopy\windowBase = avkHeapBase : tiledCopy\windowBytes = avkHeapBytes
          tiledCopy\sourceBase = avkHeapBase + avkMemOffset[avkImgMemSlot[sourceImageSlot]] + avkImgMemOffset[sourceImageSlot]
          tiledCopy\sourceBytes = avkImgSize[sourceImageSlot]
          tiledCopy\destinationBase = avkHeapBase + avkMemOffset[avkImgMemSlot[destinationImageSlot]] + avkImgMemOffset[destinationImageSlot]
          tiledCopy\destinationBytes = avkImgSize[destinationImageSlot]
          tiledCopy\width = avkImgW[sourceImageSlot] : tiledCopy\height = avkImgH[sourceImageSlot]
          tiledCopy\sourceLayout = avkImgBackendLayout[sourceImageSlot] : tiledCopy\destinationLayout = avkImgBackendLayout[destinationImageSlot]
          tiledCopy\paddedWidth = avkImgPaddedW[sourceImageSlot] : tiledCopy\paddedHeight = avkImgPaddedH[sourceImageSlot]
          tiledCopy\timeoutUs = 250000
          job = avkBackendSubmitTiledImageCopy(@tiledCopy)
          If job <> #ANVIL_VK_JOB_DONE
            avkFlightComplete(0)
            ProcedureReturn avkFault(#VK_ERROR_DEVICE_LOST, "the TFU backend failed while copying an optimal Vulkan image (VkResult -4); the command buffer was invalidated and its fence signalled.")
          EndIf
          EndIf
        ElseIf avkImgTiling[destinationImageSlot] = #VK_IMAGE_TILING_OPTIMAL
          If avkOpRows[o] = 2 Or avkOpRows[o] = 5
            linearTiledRect\windowBase = avkHeapBase : linearTiledRect\windowBytes = avkHeapBytes
            linearTiledRect\sourceBase = avkHeapBase + avkMemOffset[avkImgMemSlot[sourceImageSlot]] + avkImgMemOffset[sourceImageSlot]
            linearTiledRect\sourceBytes = avkImgSize[sourceImageSlot] : linearTiledRect\sourcePitch = avkImgPitch[sourceImageSlot]
            linearTiledRect\sourceViewWidth = avkImgW[sourceImageSlot] : linearTiledRect\sourceViewHeight = avkImgH[sourceImageSlot]
            linearTiledRect\destinationBase = avkHeapBase + avkMemOffset[avkImgMemSlot[destinationImageSlot]] + avkImgMemOffset[destinationImageSlot]
            linearTiledRect\destinationBytes = avkImgSize[destinationImageSlot]
            linearTiledRect\width = avkImgW[sourceImageSlot] : linearTiledRect\height = avkImgH[sourceImageSlot]
            linearTiledRect\destinationLayout = avkImgBackendLayout[destinationImageSlot]
            linearTiledRect\paddedWidth = avkImgPaddedW[destinationImageSlot] : linearTiledRect\paddedHeight = avkImgPaddedH[destinationImageSlot]
            linearTiledRect\sourceX = avkOpImageX[o] : linearTiledRect\sourceY = avkOpImageY[o]
            linearTiledRect\destinationX = avkOpBufferOffset[o] : linearTiledRect\destinationY = avkOpBufferPitch[o]
            linearTiledRect\regionWidth = avkOpSourceBytes[o] / 4 : linearTiledRect\regionHeight = avkOpSourcePitch[o]
            If avkOpRows[o] = 5
              job = avkBackendSubmitLinearTiledMicroCopy(@linearTiledRect)
            Else
              job = avkBackendSubmitLinearTiledRectCopy(@linearTiledRect)
            EndIf
            If job <> #ANVIL_VK_JOB_DONE
              avkFlightComplete(0)
              ProcedureReturn avkFault(#VK_ERROR_DEVICE_LOST, "the guarded DMA backend failed while copying partial linear-image rows to optimal tiles (VkResult -4); the command buffer was invalidated and its fence signalled.")
            EndIf
          Else
          copy\windowBase = avkHeapBase : copy\windowBytes = avkHeapBytes
          copy\sourceBase = avkHeapBase + avkMemOffset[avkImgMemSlot[sourceImageSlot]] + avkImgMemOffset[sourceImageSlot]
          copy\sourceBytes = avkImgSize[sourceImageSlot]
          copy\sourcePitch = avkImgPitch[sourceImageSlot]
          copy\destinationBase = avkHeapBase + avkMemOffset[avkImgMemSlot[destinationImageSlot]] + avkImgMemOffset[destinationImageSlot]
          copy\destinationBytes = avkImgSize[destinationImageSlot]
          copy\width = avkImgW[sourceImageSlot] : copy\height = avkImgH[sourceImageSlot]
          copy\destinationLayout = avkImgBackendLayout[destinationImageSlot]
          copy\paddedWidth = avkImgPaddedW[destinationImageSlot] : copy\paddedHeight = avkImgPaddedH[destinationImageSlot]
          copy\timeoutUs = 250000
          job = avkBackendSubmitImageCopy(@copy)
          If job <> #ANVIL_VK_JOB_DONE
            avkFlightComplete(0)
            ProcedureReturn avkFault(#VK_ERROR_DEVICE_LOST, "the TFU backend failed while copying a linear Vulkan image into an optimal image (VkResult -4); the command buffer was invalidated and its fence signalled.")
          EndIf
          EndIf
        Else
        sourcePitch = avkImgPitch[sourceImageSlot]
        destinationPitch = avkImgPitch[destinationImageSlot]
        copyBytes = avkOpSourceBytes[o]
        copyRows = avkOpSourcePitch[o]
        sourceBase = avkHeapBase + avkMemOffset[avkImgMemSlot[sourceImageSlot]] + avkImgMemOffset[sourceImageSlot] + avkOpBufferOffset[o]
        destinationBase = avkHeapBase + avkMemOffset[avkImgMemSlot[destinationImageSlot]] + avkImgMemOffset[destinationImageSlot] + avkOpDstOffset[o]
        If copyBytes = sourcePitch And copyBytes = destinationPitch
          job = avkBackendSubmitBufferCopy(sourceBase, destinationBase, copyBytes * copyRows)
        Else
          job = avkBackendSubmitBufferCopyRows(sourceBase, sourcePitch, destinationBase, destinationPitch, copyBytes, copyRows)
        EndIf
        If job <> #ANVIL_VK_JOB_DONE
          avkFlightComplete(0)
          ProcedureReturn avkFault(#VK_ERROR_DEVICE_LOST, "the DMA backend failed while copying a Vulkan image region (VkResult -4); the command buffer was invalidated and its fence signalled.")
        EndIf
        EndIf
      ElseIf avkOpKind[o] = #ANVIL_VK_OP_COPY_BUFFER_IMAGE
        target = avkRefSlot[avkRefIndex(c, avkOpRef[o])]
        If avkImgTiling[target] = #VK_IMAGE_TILING_LINEAR
          copyBytes = avkOpSourcePitch[o]
          sourcePitch = avkOpBufferPitch[o]
          copyRows = avkOpRows[o]
          destinationPitch = avkImgPitch[target]
          destinationBase = avkHeapBase + avkMemOffset[avkImgMemSlot[target]] + avkImgMemOffset[target] + avkOpDstOffset[o]
          If avkCopyBufferResolve(avkOpBuffer[o], d, avkOpBufferOffset[o], avkOpSourceBytes[o], @sourceBase) = 0
            avkFlightComplete(0)
            ProcedureReturn avkFault(#VK_ERROR_DEVICE_LOST, "the buffer-to-image source changed after submission preflight (VkResult -4); the command buffer was invalidated and its fence signalled.")
          EndIf
          If copyBytes = sourcePitch And copyBytes = destinationPitch
            job = avkBackendSubmitBufferCopy(sourceBase, destinationBase, copyBytes * copyRows)
            If job <> #ANVIL_VK_JOB_DONE
              avkFlightComplete(0)
              ProcedureReturn avkFault(#VK_ERROR_DEVICE_LOST, "the DMA backend failed while uploading a linear Vulkan image (VkResult -4); the command buffer was invalidated and its fence signalled.")
            EndIf
          Else
            job = avkBackendSubmitBufferCopyRows(sourceBase, sourcePitch, destinationBase, destinationPitch, copyBytes, copyRows)
            If job <> #ANVIL_VK_JOB_DONE
              avkFlightComplete(0)
              ProcedureReturn avkFault(#VK_ERROR_DEVICE_LOST, "the DMA backend failed while uploading linear Vulkan image rows (VkResult -4); the command buffer was invalidated and its fence signalled.")
            EndIf
          EndIf
        Else
          If avkCopyBufferResolve(avkOpBuffer[o], d, avkOpBufferOffset[o], avkOpSourceBytes[o], @sourceBase) = 0
            avkFlightComplete(0)
            ProcedureReturn avkFault(#VK_ERROR_DEVICE_LOST, "the optimal-image source changed after submission preflight (VkResult -4); the command buffer was invalidated and its fence signalled.")
          EndIf
          If avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_RECT_TAG Or avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_MICRO_TAG Or avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_GRID_TAG Or avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_GRID_4X4_TAG
            linearTiledRect\windowBase = avkHeapBase : linearTiledRect\windowBytes = avkHeapBytes
            linearTiledRect\sourceBase = sourceBase : linearTiledRect\sourceBytes = avkOpSourceBytes[o] : linearTiledRect\sourcePitch = avkOpBufferPitch[o]
            linearTiledRect\sourceViewWidth = avkOpSourcePitch[o] / 4 : linearTiledRect\sourceViewHeight = avkOpRows[o]
            linearTiledRect\destinationBase = avkHeapBase + avkMemOffset[avkImgMemSlot[target]] + avkImgMemOffset[target]
            linearTiledRect\destinationBytes = avkImgSize[target]
            linearTiledRect\width = avkImgW[target] : linearTiledRect\height = avkImgH[target]
            linearTiledRect\destinationLayout = avkImgBackendLayout[target]
            linearTiledRect\paddedWidth = avkImgPaddedW[target] : linearTiledRect\paddedHeight = avkImgPaddedH[target]
            linearTiledRect\sourceX = 0 : linearTiledRect\sourceY = 0
            linearTiledRect\destinationX = avkOpImageX[o] : linearTiledRect\destinationY = avkOpImageY[o]
            linearTiledRect\regionWidth = avkOpSourcePitch[o] / 4 : linearTiledRect\regionHeight = avkOpRows[o]
            If avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_MICRO_TAG
              job = avkBackendSubmitLinearTiledMicroCopy(@linearTiledRect)
            ElseIf avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_GRID_TAG Or avkOpDstOffset[o] = #ANVIL_VK_BUFFER_TILED_GRID_4X4_TAG
              job = avkBackendSubmitLinearTiledGridCopy(@linearTiledRect)
            Else
              job = avkBackendSubmitLinearTiledRectCopy(@linearTiledRect)
            EndIf
            If job <> #ANVIL_VK_JOB_DONE
              avkFlightComplete(0)
              ProcedureReturn avkFault(#VK_ERROR_DEVICE_LOST, "the guarded DMA backend failed while scattering buffer rows into optimal-image tiles (VkResult -4); the command buffer was invalidated and its fence signalled.")
            EndIf
          Else
          copy\windowBase = avkHeapBase : copy\windowBytes = avkHeapBytes
          copy\sourceBase = sourceBase : copy\sourceBytes = avkOpSourceBytes[o]
          copy\sourcePitch = avkOpBufferPitch[o]
          copy\destinationBase = avkHeapBase + avkMemOffset[avkImgMemSlot[target]] + avkImgMemOffset[target]
          copy\destinationBytes = avkImgSize[target]
          copy\width = avkImgW[target] : copy\height = avkImgH[target]
          copy\destinationLayout = avkImgBackendLayout[target]
          copy\paddedWidth = avkImgPaddedW[target] : copy\paddedHeight = avkImgPaddedH[target]
          copy\timeoutUs = 250000
          job = avkBackendSubmitImageCopy(@copy)
          If job < 0 Or (copies + imageCopies + bufferCopies + readbacks > 1 And job <> #ANVIL_VK_JOB_DONE)
            avkFlightComplete(0)
            ProcedureReturn avkFault(#VK_ERROR_DEVICE_LOST, "the graphics device failed while executing ordered vkCmdCopyBufferToImage transfers (VkResult -4); the destination layout was not advanced, the command buffer is invalid and its fence is signalled.")
          EndIf
          If job = #ANVIL_VK_JOB_PENDING : ProcedureReturn #VK_SUCCESS : EndIf
          EndIf
        EndIf
      ElseIf avkOpKind[o] = #ANVIL_VK_OP_COPY_BUFFER
        sourceBase = AnvilVkBufferAddress(avkOpBuffer[o]) + avkOpBufferOffset[o]
        destinationBase = AnvilVkBufferAddress(avkOpDstBuffer[o]) + avkOpDstOffset[o]
        job = avkBackendSubmitBufferCopy(sourceBase, destinationBase, avkOpSourceBytes[o])
        If job <> #ANVIL_VK_JOB_DONE
          avkFlightComplete(0)
          ProcedureReturn avkFault(#VK_ERROR_DEVICE_LOST, "the backend failed to complete an ordered vkCmdCopyBuffer transfer (VkResult -4, VK_ERROR_DEVICE_LOST); the command buffer was invalidated and its fence signalled.")
        EndIf
      ElseIf avkOpKind[o] = #ANVIL_VK_OP_FILL_BUFFER
        destinationBase = AnvilVkBufferAddress(avkOpBuffer[o]) + avkOpBufferOffset[o]
        job = avkBackendSubmitBufferFill(destinationBase, avkOpSourceBytes[o], avkOpColor[o])
        If job <> #ANVIL_VK_JOB_DONE
          avkFlightComplete(0)
          ProcedureReturn avkFault(#VK_ERROR_DEVICE_LOST, "the backend failed to complete an ordered vkCmdFillBuffer transfer (VkResult -4, VK_ERROR_DEVICE_LOST); the command buffer was invalidated and its fence signalled.")
        EndIf
      ElseIf avkOpKind[o] = #ANVIL_VK_OP_UPDATE_BUFFER
        destinationBase = AnvilVkBufferAddress(avkOpBuffer[o]) + avkOpBufferOffset[o]
        job = avkBackendSubmitBufferCopy(@avkOpUpdateData[(o - 1) * #ANVIL_VK_MAX_UPDATE_BYTES], destinationBase, avkOpSourceBytes[o])
        If job <> #ANVIL_VK_JOB_DONE
          avkFlightComplete(0)
          ProcedureReturn avkFault(#VK_ERROR_DEVICE_LOST, "the backend failed to complete an ordered vkCmdUpdateBuffer transfer (VkResult -4, VK_ERROR_DEVICE_LOST); the command buffer was invalidated and its fence signalled.")
        EndIf
      ElseIf avkOpKind[o] = #ANVIL_VK_OP_COPY_IMAGE_BUFFER
        sourceImageSlot = avkRefSlot[avkRefIndex(c, avkOpRef[o])]
        copyBytes = avkOpSourceBytes[o]
        copyRows = avkOpSourcePitch[o]
        destinationPitch = avkOpBufferPitch[o]
        If avkTransferBufferResolve(avkOpBuffer[o], d, #VK_BUFFER_USAGE_TRANSFER_DST_BIT, avkOpBufferOffset[o], (copyRows - 1) * destinationPitch + copyBytes, @destinationBase) = 0
          avkFlightComplete(0)
          ProcedureReturn avkFault(#VK_ERROR_DEVICE_LOST, "the image-to-buffer readback destination changed after submission preflight (VkResult -4); the command buffer was invalidated and its fence signalled.")
        EndIf
        If avkImgTiling[sourceImageSlot] = #VK_IMAGE_TILING_OPTIMAL
          tiledRead\windowBase = avkHeapBase : tiledRead\windowBytes = avkHeapBytes
          tiledRead\sourceBase = avkHeapBase + avkMemOffset[avkImgMemSlot[sourceImageSlot]] + avkImgMemOffset[sourceImageSlot]
          tiledRead\sourceBytes = avkImgSize[sourceImageSlot]
          tiledRead\destinationBase = destinationBase
          tiledRead\destinationBytes = (copyRows - 1) * destinationPitch + copyBytes
          tiledRead\destinationPitch = destinationPitch
          tiledRead\width = avkImgW[sourceImageSlot] : tiledRead\height = avkImgH[sourceImageSlot]
          tiledRead\sourceLayout = avkImgBackendLayout[sourceImageSlot]
          tiledRead\paddedWidth = avkImgPaddedW[sourceImageSlot] : tiledRead\paddedHeight = avkImgPaddedH[sourceImageSlot]
          tiledRead\sourceX = avkOpImageX[o] : tiledRead\sourceY = avkOpImageY[o]
          tiledRead\regionWidth = copyBytes / 4 : tiledRead\regionHeight = copyRows
          If avkOpRows[o] = 1
            job = avkBackendSubmitTiledMicroReadback(@tiledRead)
          Else
            job = avkBackendSubmitTiledReadback(@tiledRead)
          EndIf
          If job <> #ANVIL_VK_JOB_DONE
            avkFlightComplete(0)
            ProcedureReturn avkFault(#VK_ERROR_DEVICE_LOST, "the DMA backend failed while reading an optimal Vulkan image into a buffer (VkResult -4); the command buffer was invalidated and its fence signalled.")
          EndIf
          o = avkOpNext[o]
          Continue
        EndIf
        sourcePitch = avkImgPitch[sourceImageSlot]
        sourceBase = avkHeapBase + avkMemOffset[avkImgMemSlot[sourceImageSlot]] + avkImgMemOffset[sourceImageSlot] + avkOpDstOffset[o]
        If copyBytes = sourcePitch And copyBytes = destinationPitch
          job = avkBackendSubmitBufferCopy(sourceBase, destinationBase, copyBytes * copyRows)
          If job <> #ANVIL_VK_JOB_DONE
            avkFlightComplete(0)
            ProcedureReturn avkFault(#VK_ERROR_DEVICE_LOST, "the DMA backend failed while reading a Vulkan image into a buffer (VkResult -4); the command buffer was invalidated and its fence signalled.")
          EndIf
        Else
          job = avkBackendSubmitBufferCopyRows(sourceBase, sourcePitch, destinationBase, destinationPitch, copyBytes, copyRows)
          If job <> #ANVIL_VK_JOB_DONE
            avkFlightComplete(0)
            ProcedureReturn avkFault(#VK_ERROR_DEVICE_LOST, "the DMA backend failed while reading Vulkan image rows into a buffer (VkResult -4); the command buffer was invalidated and its fence signalled.")
          EndIf
        EndIf
      EndIf
      o = avkOpNext[o]
    Wend
    avkFlightComplete(1)
    ProcedureReturn #VK_SUCCESS
  EndIf
  If clears = 0
    ; Barriers alone. There is nothing for the device to do, so the
    ; submission completes here rather than being handed to a backend
    ; that would have to invent work to report.
    avkFlightComplete(1)
    ProcedureReturn #VK_SUCCESS
  EndIf
  job = avkBackendSubmitClear(avkHeapBase + avkMemOffset[avkImgMemSlot[target]] + avkImgMemOffset[target], avkImgSize[target], avkImgW[target], avkImgH[target], avkImgPitch[target], colour)
  If job < 0
    avkFlightComplete(0)
    avkFault(#VK_ERROR_DEVICE_LOST, "the graphics device failed while executing a clear (VkResult -4, VK_ERROR_DEVICE_LOST); the command buffer is invalid and its fence is signalled. AnvilVkBackendNativeError() carries the backend's own diagnostic code; inspect that backend's fault telemetry before resubmitting.")
    ProcedureReturn #VK_ERROR_DEVICE_LOST
  EndIf
  If job = #ANVIL_VK_JOB_DONE
    avkFlightComplete(1)
  EndIf
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkBackendNativeError()
  ProcedureReturn avkBackendLastNativeError()
EndProcedure

Procedure.i AnvilVkSubmitCount()
  ProcedureReturn avkSubmitCount
EndProcedure

Procedure.i AnvilVkCompleteCount()
  ProcedureReturn avkCompleteCount
EndProcedure

Procedure.i AnvilVkSubmissionOutstanding()
  ProcedureReturn avkFlightActive
EndProcedure

; Ask the backend once whether the outstanding job has finished, and
; settle the submission if it has. Returns 1 if nothing is outstanding.
Procedure.i avkFlightPoll()
  Define r.i
  If avkFlightActive = 0 : ProcedureReturn 1 : EndIf
  r = avkBackendPoll()
  If r < 0
    avkFlightComplete(0)
    avkFault(#VK_ERROR_DEVICE_LOST, "the graphics device reported a fault while a submitted clear was running (VkResult -4, VK_ERROR_DEVICE_LOST); the command buffer is invalid and its fence is signalled. AnvilVkBackendNativeError() carries the backend's own code.")
    ProcedureReturn -1
  EndIf
  If r = 0 : ProcedureReturn 0 : EndIf
  avkFlightComplete(1)
  ProcedureReturn 1
EndProcedure

; vkWaitForFences. `timeoutNs` is the caller's nanosecond timeout. -1 is
; the all-ones pattern the header spells UINT64_MAX. This single-threaded
; object engine cannot honestly promise an infinite wait which another host
; thread could satisfy: an already-satisfied UINT64_MAX wait succeeds, while
; an unsatisfied one is explicitly withheld instead of becoming a disguised
; bounded timeout.
Procedure.i AnvilVkWaitForFences(device.i, count.i, *handles, waitAll.i, timeoutNs.i)
  Define d.i
  Define s.i
  Define i.i
  Define timeoutUs.i
  Define t0.i
  Define polls.i
  Define signalled.i
  Define pollResult.i
  d = avkDevSlot(device)
  If d = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If count < 1 Or *handles = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  i = 0
  While i < count
    s = avkFenceSlot(PeekI(*handles + (i * 8)))
    If s = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
    If avkFenceDev[s] <> d : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
    i = i + 1
  Wend
  timeoutUs = 0
  If timeoutNs > 0
    timeoutUs = (timeoutNs + (#ANVIL_VK_NS_PER_US - 1)) / #ANVIL_VK_NS_PER_US
  EndIf
  t0 = avkBackendTicksUs()
  polls = 0
  While 1
    ; Count the fences that are signalled now, AFTER giving the device a
    ; chance to finish, so a zero timeout still observes work the backend
    ; has already completed.
    pollResult = avkFlightPoll()
    If pollResult < 0 : ProcedureReturn #VK_ERROR_DEVICE_LOST : EndIf
    signalled = 0
    i = 0
    While i < count
      s = avkFenceSlot(PeekI(*handles + (i * 8)))
      If s <> 0 And avkFenceSignaled[s] <> 0 : signalled = signalled + 1 : EndIf
      i = i + 1
    Wend
    If waitAll <> 0
      If signalled >= count : ProcedureReturn #VK_SUCCESS : EndIf
    Else
      If signalled > 0 : ProcedureReturn #VK_SUCCESS : EndIf
    EndIf
    If timeoutNs = -1
      ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkWaitForFences was given UINT64_MAX for an unsignalled fence (Anvil code -20005, unlimited host wait not implemented); use a finite timeout and wait again, because the current object engine has no reentrant host thread that can safely satisfy an infinite wait.")
    EndIf
    polls = polls + 1
    If polls >= #ANVIL_VK_WAIT_MAX_POLLS
      ProcedureReturn avkFault(#VK_TIMEOUT, "vkWaitForFences gave up after its bounded poll count without the fence being signalled (VkResult 2, VK_TIMEOUT); the wait is bounded twice so a backend whose clock never advances cannot hang the caller. Check that the device is still answering before waiting again.")
    EndIf
    If (avkBackendTicksUs() - t0) >= timeoutUs : ProcedureReturn #VK_TIMEOUT : EndIf
  Wend
EndProcedure

Procedure.i AnvilVkDeviceWaitIdle(device.i)
  Define d.i
  Define polls.i
  Define pollResult.i
  d = avkDevSlot(device)
  If d = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  polls = 0
  While avkFlightActive <> 0
    pollResult = avkFlightPoll()
    If pollResult < 0 : ProcedureReturn #VK_ERROR_DEVICE_LOST : EndIf
    polls = polls + 1
    If polls >= #ANVIL_VK_WAIT_MAX_POLLS
      ProcedureReturn avkFault(#VK_ERROR_DEVICE_LOST, "vkDeviceWaitIdle gave up after its bounded poll count with a submission still outstanding (VkResult -4, VK_ERROR_DEVICE_LOST); the device is not reporting completion. Check the backend's fault state before using the device again.")
    EndIf
  Wend
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkDeviceDestroy(device.i)
  Define d.i
  Define p.i
  Define q.i
  Define i.i
  Define rc.i
  d = avkDevSlot(device)
  If d = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkFlightActive <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkDestroyDevice was called with a submission still outstanding (Anvil code -20004, device busy); nothing was destroyed. Call vkDeviceWaitIdle before destroying a device.")
  EndIf
  ; Retire every generation-matched semaphore while the VkDevice handle is
  ; still live. A pending/reserved transaction aborts teardown atomically.
  rc = avkSemaphoreResetDevice(device)
  If rc <> #VK_SUCCESS
    ProcedureReturn avkFault(rc, "vkDestroyDevice found a binary semaphore reservation or submitted operation that is not quiescent (Anvil code -20004, semaphore in use); the device and all of its children were left alive. Wait for the queue to become idle before destroying the device.")
  EndIf
  p = 1
  While p <= #ANVIL_VK_MAX_COMMAND_POOLS
    If avkPoolLive[p] <> 0 And avkPoolDev[p] = d
      AnvilVkCommandPoolDestroy(device, avkToken(#ANVIL_VK_TYPE_COMMAND_POOL, p, avkPoolGen[p]))
    EndIf
    p = p + 1
  Wend
  i = 1
  While i <= #ANVIL_VK_MAX_IMAGES
    If avkImgLive[i] <> 0 And avkImgDev[i] = d : avkImgLive[i] = 0 : avkImgBound[i] = 0 : EndIf
    i = i + 1
  Wend
  i = 1
  While i <= #ANVIL_VK_MAX_MEMORY
    If avkMemLive[i] <> 0 And avkMemDev[i] = d : avkMemLive[i] = 0 : EndIf
    i = i + 1
  Wend
  i = 1
  While i <= #ANVIL_VK_MAX_FENCES
    If avkFenceLive[i] <> 0 And avkFenceDev[i] = d : avkFenceLive[i] = 0 : EndIf
    i = i + 1
  Wend
  i = 1
  While i <= #ANVIL_VK_MAX_EVENTS
    If avkEventLive[i] <> 0 And avkEventDev[i] = d : avkEventLive[i] = 0 : avkEventSet[i] = 0 : EndIf
    i = i + 1
  Wend
  i = 1
  While i <= #ANVIL_VK_MAX_PIPELINE_CACHES
    If avkCacheLive[i] <> 0 And avkCacheDev[i] = d : avkCacheLive[i] = 0 : EndIf
    i = i + 1
  Wend
  q = 1
  While q <= #ANVIL_VK_MAX_QUEUES
    If avkQueueLive[q] <> 0 And avkQueueDev[q] = d : avkQueueLive[q] = 0 : EndIf
    q = q + 1
  Wend
  avkDevLive[d] = 0
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkInstanceDestroy(instance.i)
  Define s.i
  Define p.i
  Define d.i
  s = avkInstSlot(instance)
  If s = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  d = 1
  While d <= #ANVIL_VK_MAX_DEVICES
    If avkDevLive[d] <> 0
      p = avkDevPhys[d]
      If avkPhysLive[p] <> 0 And avkPhysInst[p] = s
        AnvilVkDeviceDestroy(avkToken(#ANVIL_VK_TYPE_DEVICE, d, avkDevGen[d]))
      EndIf
    EndIf
    d = d + 1
  Wend
  p = 1
  While p <= #ANVIL_VK_MAX_PHYSICAL_DEVICES
    If avkPhysLive[p] <> 0 And avkPhysInst[p] = s : avkPhysLive[p] = 0 : EndIf
    p = p + 1
  Wend
  avkInstLive[s] = 0
  ProcedureReturn #VK_SUCCESS
EndProcedure

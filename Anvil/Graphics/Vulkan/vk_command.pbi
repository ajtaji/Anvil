; ======================================================================
;  Vulkan command recording and queue submission -- portable engine
; ======================================================================
; SPDX-License-Identifier: MIT
;
; Target-neutral. It records a command stream, tracks what each command
; buffer assumes and leaves behind for every image it touches, retains
; every resource a submission references until that submission completes,
; and hands ONE closed clear to the backend seam.
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
; secondary execution, buffer-to-buffer copies, blits, dispatches,
; render passes, queries, events, timeline semaphores, memory and buffer
; barriers, multi-range clears, partial-rectangle clears, depth and
; stencil clears, and more than one outstanding submission.

XIncludeFile "Anvil/Graphics/Vulkan/vk_sync.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_semaphore.pbi"

; Ops are drawn from ONE pool rather than reserved per command buffer, so
; running out of them is a real VK_ERROR_OUT_OF_HOST_MEMORY that a test
; can provoke, and so a hundred idle command buffers cost nothing.
#ANVIL_VK_MAX_OPS = 32
#ANVIL_VK_MAX_CB_REFS = 2

#ANVIL_VK_OP_NONE = 0
#ANVIL_VK_OP_BARRIER = 1
#ANVIL_VK_OP_CLEAR_COLOR = 2
#ANVIL_VK_OP_COPY_BUFFER_IMAGE = 3

; "the tracker does not know yet" for a layout inside a recording.
#ANVIL_VK_LAYOUT_UNKNOWN = -2
; "this command buffer imposes no entry layout on that image".
#ANVIL_VK_LAYOUT_ANY = -1

Global Dim avkOpLive.a[#ANVIL_VK_MAX_OPS + 1]
Global Dim avkOpNext.i[#ANVIL_VK_MAX_OPS + 1]
Global Dim avkOpKind.i[#ANVIL_VK_MAX_OPS + 1]
Global Dim avkOpRef.i[#ANVIL_VK_MAX_OPS + 1]
Global Dim avkOpOldLayout.i[#ANVIL_VK_MAX_OPS + 1]
Global Dim avkOpNewLayout.i[#ANVIL_VK_MAX_OPS + 1]
Global Dim avkOpColor.i[#ANVIL_VK_MAX_OPS + 1]
Global Dim avkOpBuffer.i[#ANVIL_VK_MAX_OPS + 1]
Global Dim avkOpBufferOffset.i[#ANVIL_VK_MAX_OPS + 1]
Global Dim avkOpSourceBytes.i[#ANVIL_VK_MAX_OPS + 1]
Global Dim avkOpSourcePitch.i[#ANVIL_VK_MAX_OPS + 1]

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
; ONE BOUND BUFFER PER BINDING. vkCmdBindVertexBuffers names a first
; binding and a count, so the state it sets is per binding and cannot be
; one buffer and one offset: a pipeline that reads position from binding
; zero and colour from binding one has two of each, at two strides.
Global Dim avkCbVtxBuf.i[(#ANVIL_VK_MAX_COMMAND_BUFFERS + 1) * #ANVIL_VK_MAX_BINDINGS]
Global Dim avkCbVtxOffset.i[(#ANVIL_VK_MAX_COMMAND_BUFFERS + 1) * #ANVIL_VK_MAX_BINDINGS]
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

Declare.i avkDrawSubmit(c.i)
Declare avkDrawRetain(c.i)
Declare avkDrawRelease(c.i)
Declare avkAttachmentViewRetain(c.i)
Declare avkAttachmentViewRelease(c.i)
Declare.i avkCopyBufferResolve(buffer.i, deviceSlot.i, offset.i, bytes.i, *baseOut)
Declare avkCopyBufferRetain(c.i)
Declare avkCopyBufferRelease(c.i)
Declare avkCbFail(c.i, code.i, text.i)
Declare.i avkCbRef(c.i, image.i, s.i)
Declare.i avkRefClaim(c.i, k.i, claim.i)
Declare.i avkOpAppend(c.i, kind.i)

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
    avkOpSourceBytes[o] = 0
    avkOpSourcePitch[o] = 0
    o = n
  Wend
  avkCbOpHead[c] = 0
  avkCbOpTail[c] = 0
EndProcedure

; Exact bounded vkCmdCopyBufferToImage semantics: one tightly packed whole
; BGRA8 level/layer from a TRANSFER_SRC buffer into an optimal TRANSFER_DST
; image. The command captures the handles and immutable region values here;
; the queue resolves and validates the live resources again before retaining
; them, as Vulkan lifetime belongs to submission rather than recording.
Procedure AnvilVkCmdCopyBufferToImage(commandBuffer.i, srcBuffer.i, dstImage.i, dstImageLayout.i, *r.VkBufferImageCopy)
  Define c.i
  Define d.i
  Define s.i
  Define k.i
  Define o.i
  Define sourceBytes.i
  Define sourcePitch.i
  Define copyAlign.i
  If *r = 0
    avkFault(#ANVIL_VK_ERR_ARGS, "vkCmdCopyBufferToImage was given a null VkBufferImageCopy pointer (Anvil code -20001, invalid argument); nothing was recorded.")
    ProcedureReturn
  EndIf
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
  If avkImgTiling[s] <> #VK_IMAGE_TILING_OPTIMAL Or (avkImgUsage[s] & #VK_IMAGE_USAGE_TRANSFER_DST_BIT) = 0
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyBufferToImage requires an optimal-tiled destination created with VK_IMAGE_USAGE_TRANSFER_DST_BIT (Anvil code -20001, wrong destination contract); this bounded transfer does not reinterpret a linear image as tiled.")
    ProcedureReturn
  EndIf
  If dstImageLayout <> #VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyBufferToImage was given a destination layout other than VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL (Anvil code -20001, wrong copy layout); transition the image before the copy and name that exact layout.")
    ProcedureReturn
  EndIf
  copyAlign = avkBackendImageCopySourceAlignment()
  If copyAlign < 1 Or (copyAlign & (copyAlign - 1)) <> 0
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyBufferToImage could not obtain a power-of-two source-alignment contract from the active backend (Anvil code -20005, incomplete copy backend); no transfer was recorded.")
    ProcedureReturn
  EndIf
  If (*r\bufferOffset % copyAlign) <> 0 Or *r\bufferOffset < 0
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyBufferToImage requires a non-negative bufferOffset aligned to the active backend's image-copy source requirement (Anvil code -20001, misaligned buffer offset); query and obey the target's published transfer contract.")
    ProcedureReturn
  EndIf
  If *r\bufferRowLength <> 0 Or *r\bufferImageHeight <> 0
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyBufferToImage was given an explicit buffer row length or image height (Anvil code -20005, strided copy not implemented); zero means tightly packed and is the supported core subset.")
    ProcedureReturn
  EndIf
  If *r\imageSubresource\aspectMask <> #VK_IMAGE_ASPECT_COLOR_BIT Or *r\imageSubresource\mipLevel <> 0 Or *r\imageSubresource\baseArrayLayer <> 0 Or *r\imageSubresource\layerCount <> 1
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyBufferToImage was given a subresource other than colour mip zero, layer zero, count one (Anvil code -20005, unsupported subresource); every image in this subset has exactly that one subresource.")
    ProcedureReturn
  EndIf
  If *r\imageOffset\x <> 0 Or *r\imageOffset\y <> 0 Or *r\imageOffset\z <> 0 Or *r\imageExtent\width <> avkImgW[s] Or *r\imageExtent\height <> avkImgH[s] Or *r\imageExtent\depth <> 1
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyBufferToImage was given a partial destination region (Anvil code -20005, partial copy not implemented); offset must be zero and extent must cover the complete one-level image.")
    ProcedureReturn
  EndIf
  sourcePitch = avkImgW[s] * #ANVIL_VK_BGRA8_TEXEL_BYTES
  sourceBytes = sourcePitch * avkImgH[s]
  If sourcePitch < 1 Or sourceBytes < sourcePitch
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdCopyBufferToImage computed a wrapped source span (Anvil code -20001, invalid extent); nothing was recorded.")
    ProcedureReturn
  EndIf
  If avkCopyBufferResolve(srcBuffer, d, *r\bufferOffset, sourceBytes, 0) = 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdCopyBufferToImage could not resolve a live, bound VK_BUFFER_USAGE_TRANSFER_SRC_BIT buffer covering the complete source region (Anvil code -20004, invalid source buffer); bind sufficient memory and keep the buffer live.")
    ProcedureReturn
  EndIf
  k = avkCbRef(c, dstImage, s)
  If k < 0
    avkCbFail(c, #VK_ERROR_OUT_OF_HOST_MEMORY, "vkCmdCopyBufferToImage exceeded this command buffer's retained-image capacity (VkResult -1, VK_ERROR_OUT_OF_HOST_MEMORY); split the work across command buffers.")
    ProcedureReturn
  EndIf
  If avkRefClaim(c, k, dstImageLayout) = 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdCopyBufferToImage claims a destination layout that earlier commands in this recording did not leave (Anvil code -20004, layout mismatch); record the transfer-destination barrier first.")
    ProcedureReturn
  EndIf
  o = avkOpAppend(c, #ANVIL_VK_OP_COPY_BUFFER_IMAGE)
  If o = 0
    avkCbFail(c, #VK_ERROR_OUT_OF_HOST_MEMORY, "the command pool ran out of recorded-command storage while recording vkCmdCopyBufferToImage (VkResult -1, VK_ERROR_OUT_OF_HOST_MEMORY); reset unused command buffers or record fewer commands.")
    ProcedureReturn
  EndIf
  avkOpRef[o] = k
  avkOpOldLayout[o] = dstImageLayout
  avkOpNewLayout[o] = dstImageLayout
  avkOpBuffer[o] = srcBuffer
  avkOpBufferOffset[o] = *r\bufferOffset
  avkOpSourceBytes[o] = sourceBytes
  avkOpSourcePitch[o] = sourcePitch
EndProcedure

; Return a command buffer to the initial state: no ops, no references, no
; recorded failure. Every reset path goes through this one procedure, so
; a new piece of per-buffer state cannot be forgotten by one of them.
Procedure avkCbClear(c.i)
  Define k.i
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
  k = 0
  While k < #ANVIL_VK_MAX_BINDINGS
    avkCbVtxBuf[(c * #ANVIL_VK_MAX_BINDINGS) + k] = 0
    avkCbVtxOffset[(c * #ANVIL_VK_MAX_BINDINGS) + k] = 0
    k = k + 1
  Wend
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
  avkCbClear(c)
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
  avkCbClear(c)
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
    If avkCmdLive[c] <> 0 And avkCmdPool[c] = p : avkCbClear(c) : EndIf
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
  avkCbClear(c)
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
      avkCbClear(c)
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
    avkCbFail(c, #VK_ERROR_FEATURE_NOT_PRESENT, "the graphics backend cannot clear an image of this size (VkResult -8, VK_ERROR_FEATURE_NOT_PRESENT); the command buffer is now invalid. The Pi 4 V3D backend clears only an image whose width, height and row pitch match the render geometry the engine was initialised with, so create the image at the surface's own extent.")
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
  avkAttachmentViewRetain(c)
EndProcedure

Procedure avkFlightReleaseRefs(c.i)
  Define k.i
  Define s.i
  avkDrawRelease(c)
  avkCopyBufferRelease(c)
  avkAttachmentViewRelease(c)
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
  Define colour.i
  Define target.i
  Define sourceBase.i
  Define copyAlign.i
  Define copy.AnvilVkBackendImageCopy
  q = avkQueueSlot(queue)
  If q = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  d = avkQueueDev[q]
  If avkFlightActive <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit was called while an earlier submission on this queue has not completed (Anvil code -20004, queue busy); this slice runs one submission at a time. Wait on the earlier submission's fence, or call vkDeviceWaitIdle, before submitting again.")
  EndIf
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
      copyOp = o
      target = avkRefSlot[avkRefIndex(c, avkOpRef[o])]
    EndIf
    o = avkOpNext[o]
  Wend
  If clears > 1
    ProcedureReturn avkFault(#VK_ERROR_FEATURE_NOT_PRESENT, "vkQueueSubmit was given a command buffer holding more than one clear (VkResult -8, VK_ERROR_FEATURE_NOT_PRESENT); nothing was submitted. This slice lowers one clear per submission, so record one clear per command buffer until the backend carries a command list.")
  EndIf
  If copies > 1
    ProcedureReturn avkFault(#VK_ERROR_FEATURE_NOT_PRESENT, "vkQueueSubmit was given a command buffer holding more than one buffer-to-image copy (VkResult -8, VK_ERROR_FEATURE_NOT_PRESENT); nothing was submitted. This bounded backend transaction executes exactly one complete TFU transfer.")
  EndIf
  ; A command buffer is either a transfer or a render pass, never both.
  ; The backend seam carries ONE job, and running the clear and throwing
  ; the draw away - or the other way round - would be a silent partial
  ; submission, which is the one answer this engine never gives.
  If avkCbDrawCount[c] > 0 And (clears > 0 Or copies > 0)
    ProcedureReturn avkFault(#VK_ERROR_FEATURE_NOT_PRESENT, "vkQueueSubmit was given a command buffer holding both a vkCmdClearColorImage and a render pass (VkResult -8, VK_ERROR_FEATURE_NOT_PRESENT); nothing was submitted. The backend seam carries one job per submission, so record the clear and the render pass in separate command buffers.")
  EndIf
  If clears > 0 And copies > 0
    ProcedureReturn avkFault(#VK_ERROR_FEATURE_NOT_PRESENT, "vkQueueSubmit was given both a clear and a buffer-to-image copy (VkResult -8, VK_ERROR_FEATURE_NOT_PRESENT); nothing was submitted. Record each backend job in its own command buffer until ordered multi-job submission exists.")
  EndIf
  If avkCbRpDone[c] <> 0 And avkCbDrawCount[c] = 0
    ProcedureReturn avkFault(#VK_ERROR_FEATURE_NOT_PRESENT, "vkQueueSubmit was given a command buffer whose render pass contains no draw (VkResult -8, VK_ERROR_FEATURE_NOT_PRESENT); nothing was submitted. A render pass with no draw would be a clear wearing a render pass's clothes, and vkCmdClearColorImage is the honest way to ask for that.")
  EndIf
  ; Resolve every generation-tagged draw dependency before the submission
  ; changes command/fence/resource state. A stale object is an application
  ; state error, not a device loss discovered after the flight has begun.
  If avkCbDrawCount[c] > 0
    job = avkDrawPreflight(c)
    If job <> #ANVIL_VK_OK : ProcedureReturn job : EndIf
  EndIf
  If copies = 1
    copyAlign = avkBackendImageCopySourceAlignment()
    If copyAlign < 1 Or (copyAlign & (copyAlign - 1)) <> 0 Or (avkOpBufferOffset[copyOp] % copyAlign) <> 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found that the recorded copy no longer satisfies the active backend's image-copy source alignment (Anvil code -20004, backend contract changed); re-record against the current target contract.")
    EndIf
    If avkCopyBufferResolve(avkOpBuffer[copyOp], d, avkOpBufferOffset[copyOp], avkOpSourceBytes[copyOp], @sourceBase) = 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found that a vkCmdCopyBufferToImage source buffer is no longer live, bound, owned, aligned or large enough (Anvil code -20004, stale source resource); re-record against a valid transfer-source buffer.")
    EndIf
    If target < 1 Or avkImgTiling[target] <> #VK_IMAGE_TILING_OPTIMAL Or avkImgBackendLayout[target] = 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found that a recorded buffer-to-image copy no longer resolves to a complete optimal-image backend plan (Anvil code -20004, invalid destination resource); nothing was submitted.")
    EndIf
  EndIf
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
  EndIf
  avkFlightActive = 1
  avkFlightCb = c
  avkFlightFence = f
  avkFlightSemaphoreReservation = semaphoreReservation
  avkCmdState[c] = #ANVIL_VK_CB_PENDING
  avkFlightRetain(c)
  avkDrawRetain(c)
  avkCopyBufferRetain(c)
  avkSubmitCount = avkSubmitCount + 1
  If avkCbDrawCount[c] > 0
    job = avkDrawSubmit(c)
    If job < 0
      avkFlightComplete(0)
      avkFault(#VK_ERROR_DEVICE_LOST, "the graphics device failed while executing a draw (VkResult -4, VK_ERROR_DEVICE_LOST); the command buffer is invalid and its fence is signalled. AnvilVkBackendNativeError() carries the backend's own code, and on the Pi 4 that is the Neon/V3D error - check the bin and render fault registers, the binner overflow count and the MMU violation address before resubmitting.")
      ProcedureReturn #VK_ERROR_DEVICE_LOST
    EndIf
    If job = #ANVIL_VK_JOB_DONE
      avkFlightComplete(1)
    EndIf
    ProcedureReturn #VK_SUCCESS
  EndIf
  If copies = 1
    copy\windowBase = avkHeapBase
    copy\windowBytes = avkHeapBytes
    copy\sourceBase = sourceBase
    copy\sourceBytes = avkOpSourceBytes[copyOp]
    copy\sourcePitch = avkOpSourcePitch[copyOp]
    copy\destinationBase = avkHeapBase + avkMemOffset[avkImgMemSlot[target]] + avkImgMemOffset[target]
    copy\destinationBytes = avkImgSize[target]
    copy\width = avkImgW[target]
    copy\height = avkImgH[target]
    copy\destinationLayout = avkImgBackendLayout[target]
    copy\paddedWidth = avkImgPaddedW[target]
    copy\paddedHeight = avkImgPaddedH[target]
    copy\timeoutUs = 250000
    job = avkBackendSubmitImageCopy(@copy)
    If job < 0
      avkFlightComplete(0)
      avkFault(#VK_ERROR_DEVICE_LOST, "the graphics device failed while executing vkCmdCopyBufferToImage (VkResult -4, VK_ERROR_DEVICE_LOST); the destination layout was not advanced, the command buffer is invalid and its fence is signalled. Inspect the backend's TFU and MMU fault evidence before retrying.")
      ProcedureReturn #VK_ERROR_DEVICE_LOST
    EndIf
    If job = #ANVIL_VK_JOB_DONE : avkFlightComplete(1) : EndIf
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
    avkFault(#VK_ERROR_DEVICE_LOST, "the graphics device failed while executing a clear (VkResult -4, VK_ERROR_DEVICE_LOST); the command buffer is invalid and its fence is signalled. AnvilVkBackendNativeError() carries the backend's own code, and on the Pi 4 that is the Neon/V3D error - check the bin and render fault registers before resubmitting.")
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

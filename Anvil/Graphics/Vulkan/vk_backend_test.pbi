; ======================================================================
;  The explicit test backend -- state and a call log, and NO PIXELS
; ======================================================================
; SPDX-License-Identifier: MIT
;
; This backend owns no GPU and it DOES NOT WRITE ONE BYTE OF ANY IMAGE.
; It records what the engine asked it to do - the address, the extent,
; the pitch and the exact clear word - so a desk gate can check the call
; stream, the ordering and the state machine without a board, and can
; then check that the image memory is still exactly as the test left it.
;
; That last property is the point. A test backend that filled the image
; would make a green gate that proved the GATE writes pixels, not that
; the driver does. The only thing that may ever write an image here is
; real V3D, and that proof lives on the board.
;
; It can also HOLD a submission, so the fence state machine, the pending
; command-buffer state, the resource retention and the refusal to
; destroy in-flight objects are all reachable from a desk gate. Real
; asynchrony on the Pi is the V3D backend's own bounded wait; holding
; here models the observable contract, not the hardware.

XIncludeFile "Anvil/Graphics/Vulkan/vk_foundation.pbi"

Global avkTbHeapBase.i = 0
Global avkTbHeapBytes.i = 0
Global avkTbMaxDim.i = 4096
Global avkTbRowAlign.i = 64
Global avkTbCopyAlign.i = 64
Global avkTbClearW.i = 0
Global avkTbClearH.i = 0
Global avkTbHold.i = 0
Global avkTbBusy.i = 0
Global avkTbFail.i = 0
Global avkTbPollFail.i = 0
Global avkTbTicks.i = 0
Global avkTbCalls.i = 0
Global avkTbTiledRectCopies.i = 0
Global avkTbTiledMicroCopies.i = 0
Global avkTbTiledEdgeTailCopies.i = 0
Global avkTbTiledMicroReadbacks.i = 0
Global avkTbLastMicroReadSourceX.i = 0
Global avkTbLastMicroReadSourceY.i = 0
Global avkTbLastMicroReadWidth.i = 0
Global avkTbLastMicroReadHeight.i = 0
Global avkTbLastMicroReadPitch.i = 0
Global avkTbLastMicroReadSpan.i = 0
Global avkTbLinearTiledRectCopies.i = 0
Global avkTbLinearTiledMicroCopies.i = 0
Global avkTbLinearTiledGridCopies.i = 0
Global avkTbLastLinearGridIntersections.i = 0
Global avkTbLastLinearRectSourceX.i = 0
Global avkTbLastLinearRectSourceY.i = 0
Global avkTbLastLinearRectDestinationX.i = 0
Global avkTbLastLinearRectDestinationY.i = 0
Global avkTbLastLinearRectWidth.i = 0
Global avkTbLastLinearRectHeight.i = 0
Global avkTbLastLinearRectSourcePitch.i = 0
Global avkTbLastLinearRectSourceBytes.i = 0
Global avkTbLastLinearRectSourceViewWidth.i = 0
Global avkTbLastLinearRectSourceViewHeight.i = 0
Global avkTbLastRectSourceX.i = 0
Global avkTbLastRectSourceY.i = 0
Global avkTbLastRectDestinationX.i = 0
Global avkTbLastRectDestinationY.i = 0
Global avkTbLastRectWidth.i = 0
Global avkTbLastRectHeight.i = 0
; Optional test-only retain observer. The pipeline gate registers addresses of
; exact in-flight counters; other gates leave every pointer zero. Sampling
; inside the backend callback proves acquisition happened before dispatch,
; which a post-submit snapshot alone cannot establish.
Global Dim avkTbRetainPtr.i[9]
Global Dim avkTbRetainSeen.i[9]
; The test backend reports a draw capability as well as a clear one, so
; a desk gate can drive the whole pipeline path. It is still not a GPU
; and it still writes no pixels.
Global avkTbPolls.i = 0
Global avkTbLastBase.i = 0
Global avkTbLastBytes.i = 0
Global avkTbLastW.i = 0
Global avkTbLastH.i = 0
Global avkTbLastPitch.i = 0
Global avkTbLastColor.i = 0
Global avkTbLastKind.i = #ANVIL_VK_RENDER_OP_DRAW
Global avkTbLastClearX.i = 0
Global avkTbLastClearY.i = 0
Global avkTbLastClearW.i = 0
Global avkTbLastClearH.i = 0
Global avkTbLastClearBgra.i = 0
Global avkTbNative.i = 0
Global avkTbCaps.i = #ANVIL_VK_CAP_DEVICE | #ANVIL_VK_CAP_CLEAR_COLOR | #ANVIL_VK_CAP_DRAW | #ANVIL_VK_CAP_BLEND_SRC_OVER | #ANVIL_VK_CAP_DRAW_LIST | #ANVIL_VK_CAP_CLEAR_ATTACHMENT_RECT | #ANVIL_VK_CAP_BUFFER_TRANSFER | #ANVIL_VK_CAP_LINEAR_TRANSFER

; Declare the window this backend suballocates. It is ordinary DRAM the
; caller owns; the backend never touches it.
Procedure AnvilVkTestBackendHeap(base.i, bytes.i)
  avkTbHeapBase = base
  avkTbHeapBytes = bytes
  avkTbPollFail = 0
EndProcedure

; Let the foundation gate model distinct honest backends without making
; a second copy of the backend seam. Production never links this file.
; DEVICE still depends on a real declared heap in avkBackendCaps below.
Procedure AnvilVkTestBackendCapabilities(caps.i)
  avkTbCaps = caps
EndProcedure

Procedure AnvilVkTestBackendLimits(maxDim.i, rowAlign.i)
  If maxDim > 0 : avkTbMaxDim = maxDim : EndIf
  If rowAlign > 0 : avkTbRowAlign = rowAlign : EndIf
EndProcedure

; Publish the source-address contract of this backend's image-copy engine.
; Tests deliberately change it to prove the target-neutral recorder follows
; backend truth rather than carrying a V3D-specific cache-line constant.
Procedure AnvilVkTestBackendCopyAlignment(alignment.i)
  If alignment > 0 : avkTbCopyAlign = alignment : EndIf
EndProcedure

; Restrict the extent this backend will clear, the way the Pi 4 backend
; is restricted to the render geometry Neon was initialised with. Zero
; means "any extent that fits".
Procedure AnvilVkTestBackendClearExtent(w.i, h.i)
  avkTbClearW = w
  avkTbClearH = h
EndProcedure

; While hold is 1 a submitted job stays outstanding until it is cleared.
Procedure AnvilVkTestBackendHold(on.i)
  If on <> 0 : avkTbHold = 1 : Else : avkTbHold = 0 : EndIf
EndProcedure

; Make the next submission fail with this native code, as a device fault.
Procedure AnvilVkTestBackendFailNext(code.i)
  avkTbFail = code
EndProcedure

Procedure AnvilVkTestBackendObserveRetains(uboBuffer.i, uboMemory.i, sampleSampler.i, sampleView.i, sampleImage.i, sampleMemory.i, attachmentView.i, attachmentImage.i, attachmentMemory.i)
  avkTbRetainPtr[0] = uboBuffer : avkTbRetainPtr[1] = uboMemory
  avkTbRetainPtr[2] = sampleSampler : avkTbRetainPtr[3] = sampleView
  avkTbRetainPtr[4] = sampleImage : avkTbRetainPtr[5] = sampleMemory
  avkTbRetainPtr[6] = attachmentView : avkTbRetainPtr[7] = attachmentImage
  avkTbRetainPtr[8] = attachmentMemory
EndProcedure

Procedure.i AnvilVkTestBackendObservedRetain(index.i)
  If index < 0 Or index > 8 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkTbRetainSeen[index]
EndProcedure

Procedure AnvilVkTestBackendPoisonObservedRetains(value.i)
  Define i.i = 0
  While i < 9
    avkTbRetainSeen[i] = value
    i = i + 1
  Wend
EndProcedure

; Make the next poll of a held submission fail once. This is test-only fault
; injection for proving that every owner rolls back on deferred device loss.
Procedure AnvilVkTestBackendFailPollNext(code.i)
  avkTbPollFail = code
EndProcedure

Procedure.i AnvilVkTestBackendCalls()
  ProcedureReturn avkTbCalls
EndProcedure

Procedure.i AnvilVkTestBackendPolls()
  ProcedureReturn avkTbPolls
EndProcedure

Procedure.i AnvilVkTestBackendLastBase()
  ProcedureReturn avkTbLastBase
EndProcedure

Procedure.i AnvilVkTestBackendLastBytes()
  ProcedureReturn avkTbLastBytes
EndProcedure

Procedure.i AnvilVkTestBackendLastWidth()
  ProcedureReturn avkTbLastW
EndProcedure

Procedure.i AnvilVkTestBackendLastHeight()
  ProcedureReturn avkTbLastH
EndProcedure

Procedure.i AnvilVkTestBackendLastPitch()
  ProcedureReturn avkTbLastPitch
EndProcedure

Procedure.i AnvilVkTestBackendLastColor()
  ProcedureReturn avkTbLastColor
EndProcedure

Procedure.i avkBackendCaps()
  If avkTbHeapBase <= 0 Or avkTbHeapBytes <= 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkTbCaps
EndProcedure

Procedure.i avkBackendName()
  ProcedureReturn "the explicit Anvil test backend: it models Vulkan object and submission state, owns no GPU, and never writes a pixel of any image"
EndProcedure

Procedure.i avkBackendPrepare()
  If avkTbHeapBase <= 0 Or avkTbHeapBytes <= 0 : ProcedureReturn #VK_ERROR_INITIALIZATION_FAILED : EndIf
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkBackendComputeCanLower(*ir)
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendHeapBase()
  ProcedureReturn avkTbHeapBase
EndProcedure

Procedure.i avkBackendHeapBytes()
  ProcedureReturn avkTbHeapBytes
EndProcedure

; Two types over one heap: the plain device-local one, and a host-visible
; host-coherent view of the same memory. That is the truth on a part
; where the GPU and the processor share DRAM, and it lets a test choose
; an index and be refused for a wrong one.
Procedure.i avkBackendMemoryTypeCount()
  ProcedureReturn 2
EndProcedure

Procedure.i avkBackendMemoryTypeFlags(index.i)
  If index = 0 : ProcedureReturn #VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT : EndIf
  If index = 1
    ProcedureReturn #VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT | #VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | #VK_MEMORY_PROPERTY_HOST_COHERENT_BIT
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendMemoryTypeHeap(index.i)
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendHeapCount()
  ProcedureReturn 1
EndProcedure

Procedure.i avkBackendHeapSizeOf(index.i)
  If index <> 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkTbHeapBytes
EndProcedure

Procedure.i avkBackendHeapFlagsOf(index.i)
  If index <> 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn #VK_MEMORY_HEAP_DEVICE_LOCAL_BIT
EndProcedure

Procedure.i avkBackendImageAlignment()
  ProcedureReturn 4096
EndProcedure

Procedure.i avkBackendImageCopySourceAlignment()
  ProcedureReturn avkTbCopyAlign
EndProcedure

Procedure.i avkBackendRowPitchFor(width.i)
  ProcedureReturn (((width * 4) + avkTbRowAlign - 1) / avkTbRowAlign) * avkTbRowAlign
EndProcedure

Procedure.i avkBackendMaxImageDimension2D()
  ProcedureReturn avkTbMaxDim
EndProcedure

; The explicit state backend has no hardware tile cost.
Procedure avkBackendRenderAreaGranularity(*out.VkExtent2D)
  *out\width = 1
  *out\height = 1
EndProcedure

; The state backend models the portable contract over its full declared
; extent. It never claims a pixel; the V3D emitter gate is the execution-side
; oracle for a real texture request.
Procedure.i avkBackendSampledMaxDimension2D(tiling.i)
  If tiling <> #VK_IMAGE_TILING_LINEAR And tiling <> #VK_IMAGE_TILING_OPTIMAL : ProcedureReturn 0 : EndIf
  ProcedureReturn avkTbMaxDim
EndProcedure

Procedure.i avkBackendImagePlan(width.i, height.i, format.i, tiling.i, usage.i, *plan.AnvilVkBackendImagePlan)
  Define pw.i
  Define ph.i
  If *plan = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  *plan\bytes = 0 : *plan\alignment = 0 : *plan\rowPitch = 0
  *plan\backendLayout = 0 : *plan\paddedWidth = 0 : *plan\paddedHeight = 0
  If width < 1 Or height < 1 Or width > avkTbMaxDim Or height > avkTbMaxDim : ProcedureReturn #VK_ERROR_FORMAT_NOT_SUPPORTED : EndIf
  If format <> #VK_FORMAT_B8G8R8A8_UNORM : ProcedureReturn #VK_ERROR_FORMAT_NOT_SUPPORTED : EndIf
  *plan\alignment = 4096
  If tiling = #VK_IMAGE_TILING_LINEAR
    *plan\rowPitch = avkBackendRowPitchFor(width)
    *plan\bytes = *plan\rowPitch * height
    *plan\paddedWidth = width : *plan\paddedHeight = height
    ProcedureReturn #VK_SUCCESS
  EndIf
  If tiling <> #VK_IMAGE_TILING_OPTIMAL : ProcedureReturn #VK_ERROR_FORMAT_NOT_SUPPORTED : EndIf
  If (usage & (~(#VK_IMAGE_USAGE_TRANSFER_SRC_BIT | #VK_IMAGE_USAGE_TRANSFER_DST_BIT | #VK_IMAGE_USAGE_SAMPLED_BIT))) <> 0 : ProcedureReturn #VK_ERROR_FORMAT_NOT_SUPPORTED : EndIf
  pw = ((width + 31) / 32) * 32
  ph = ((height + 7) / 8) * 8
  *plan\bytes = pw * ph * 4
  *plan\backendLayout = 4
  *plan\paddedWidth = pw : *plan\paddedHeight = ph
  ProcedureReturn #VK_SUCCESS
EndProcedure

Global avkTbCopies.i = 0
Global avkTbLastCopySource.i = 0
Global avkTbLastCopyDestination.i = 0
Global avkTbLastCopyBytes.i = 0
Global avkTbLastCopySourcePitch.i = 0
Global avkTbTiledCopies.i = 0

Procedure.i avkBackendImageCopyValidate(*copy.AnvilVkBackendImageCopy)
  If *copy = 0 : ProcedureReturn -1 : EndIf
  If *copy\windowBase <= 0 Or *copy\windowBytes < 1 Or *copy\sourceBytes < 1 Or *copy\destinationBytes < 1 Or *copy\width < 1 Or *copy\height < 1 Or *copy\sourcePitch < *copy\width * 4 Or *copy\destinationLayout = 0
    ProcedureReturn -1
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendImageCopyBatchReady()
  If avkTbHold <> 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i avkBackendSubmitImageCopy(*copy.AnvilVkBackendImageCopy)
  If *copy = 0 : ProcedureReturn -1 : EndIf
  avkTbCalls = avkTbCalls + 1
  avkTbTicks = avkTbTicks + 1
  If avkTbFail <> 0
    avkTbNative = avkTbFail
    avkTbFail = 0
    ProcedureReturn -1
  EndIf
  avkTbCopies = avkTbCopies + 1
  avkTbLastCopySource = *copy\sourceBase
  avkTbLastCopyDestination = *copy\destinationBase
  avkTbLastCopyBytes = *copy\destinationBytes
  avkTbLastCopySourcePitch = *copy\sourcePitch
  avkTbNative = 0
  If avkTbHold <> 0
    avkTbBusy = 1
    ProcedureReturn #ANVIL_VK_JOB_PENDING
  EndIf
  avkTbBusy = 0
  ProcedureReturn #ANVIL_VK_JOB_DONE
EndProcedure

Procedure.i AnvilVkTestBackendCopies()
  ProcedureReturn avkTbCopies
EndProcedure

Procedure.i AnvilVkTestBackendLastCopySource()
  ProcedureReturn avkTbLastCopySource
EndProcedure

Procedure.i AnvilVkTestBackendLastCopyDestination()
  ProcedureReturn avkTbLastCopyDestination
EndProcedure

Procedure.i AnvilVkTestBackendLastCopyBytes()
  ProcedureReturn avkTbLastCopyBytes
EndProcedure

Procedure.i avkBackendTiledImageCopyValidate(*copy.AnvilVkBackendTiledImageCopy)
  If *copy = 0 : ProcedureReturn -1 : EndIf
  If *copy\sourceBase <= 0 Or *copy\destinationBase <= 0 Or *copy\sourceBytes < 1 Or *copy\destinationBytes < 1 Or *copy\width < 1 Or *copy\height < 1 Or *copy\sourceLayout = 0 Or *copy\destinationLayout = 0
    ProcedureReturn -1
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendSubmitTiledImageCopy(*copy.AnvilVkBackendTiledImageCopy)
  If avkBackendTiledImageCopyValidate(*copy) <> 0 : ProcedureReturn -1 : EndIf
  avkTbCalls = avkTbCalls + 1
  If avkTbFail <> 0
    avkTbNative = avkTbFail : avkTbFail = 0
    ProcedureReturn -1
  EndIf
  avkTbTiledCopies = avkTbTiledCopies + 1
  avkTbNative = 0
  ProcedureReturn #ANVIL_VK_JOB_DONE
EndProcedure

Procedure.i avkBackendTiledRectCopyValidate(*copy.AnvilVkBackendTiledRectCopy)
  If *copy = 0 : ProcedureReturn -1 : EndIf
  If *copy\sourceBase <= 0 Or *copy\destinationBase <= 0 Or *copy\sourceBytes < 64 Or *copy\destinationBytes < 64 Or *copy\sourceLayout = 0 Or *copy\destinationLayout = 0
    ProcedureReturn -1
  EndIf
  If *copy\regionWidth < 4 Or *copy\regionHeight < 4 Or (*copy\regionWidth % 4) <> 0 Or (*copy\regionHeight % 4) <> 0 Or (*copy\sourceX % 4) <> 0 Or (*copy\sourceY % 4) <> 0 Or (*copy\destinationX % 4) <> 0 Or (*copy\destinationY % 4) <> 0
    ProcedureReturn -1
  EndIf
  If *copy\sourceX < 0 Or *copy\sourceY < 0 Or *copy\destinationX < 0 Or *copy\destinationY < 0 Or *copy\sourceX > *copy\width - *copy\regionWidth Or *copy\sourceY > *copy\height - *copy\regionHeight Or *copy\destinationX > *copy\width - *copy\regionWidth Or *copy\destinationY > *copy\height - *copy\regionHeight
    ProcedureReturn -1
  EndIf
  If (*copy\regionWidth / 4) * (*copy\regionHeight / 4) > #ANVIL_VK_TILED_RECT_MAX_UTILES : ProcedureReturn -1 : EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendSubmitTiledRectCopy(*copy.AnvilVkBackendTiledRectCopy)
  If avkBackendTiledRectCopyValidate(*copy) <> 0 : ProcedureReturn -1 : EndIf
  avkTbCalls = avkTbCalls + 1
  avkTbTiledRectCopies = avkTbTiledRectCopies + 1
  avkTbLastRectSourceX = *copy\sourceX : avkTbLastRectSourceY = *copy\sourceY
  avkTbLastRectDestinationX = *copy\destinationX : avkTbLastRectDestinationY = *copy\destinationY
  avkTbLastRectWidth = *copy\regionWidth : avkTbLastRectHeight = *copy\regionHeight
  ProcedureReturn #ANVIL_VK_JOB_DONE
EndProcedure

Procedure.i avkBackendTiledEdgeTailCopyValidate(*copy.AnvilVkBackendTiledRectCopy)
  Define tile.AnvilVkBackendTiledRectCopy, x.i, y.i
  If *copy = 0 : ProcedureReturn -1 : EndIf
  If *copy\sourceBase <= 0 Or *copy\destinationBase <= 0 Or *copy\sourceLayout = 0 Or *copy\destinationLayout = 0 Or *copy\sourceBytes < 64 Or *copy\destinationBytes < 64 : ProcedureReturn -1 : EndIf
  If *copy\regionWidth < 1 Or *copy\regionHeight < 1 Or ((*copy\regionWidth % 4) = 0 And (*copy\regionHeight % 4) = 0) : ProcedureReturn -1 : EndIf
  If *copy\sourceX < 0 Or *copy\sourceY < 0 Or *copy\destinationX < 0 Or *copy\destinationY < 0 Or (*copy\sourceX % 4) <> 0 Or (*copy\sourceY % 4) <> 0 Or (*copy\destinationX % 4) <> 0 Or (*copy\destinationY % 4) <> 0 : ProcedureReturn -1 : EndIf
  If *copy\sourceX > *copy\width - *copy\regionWidth Or *copy\sourceY > *copy\height - *copy\regionHeight Or *copy\destinationX > *copy\width - *copy\regionWidth Or *copy\destinationY > *copy\height - *copy\regionHeight : ProcedureReturn -1 : EndIf
  If ((*copy\regionWidth % 4) <> 0 And (*copy\sourceX <> *copy\width - *copy\regionWidth Or *copy\destinationX <> *copy\width - *copy\regionWidth)) Or ((*copy\regionHeight % 4) <> 0 And (*copy\sourceY <> *copy\height - *copy\regionHeight Or *copy\destinationY <> *copy\height - *copy\regionHeight)) : ProcedureReturn -1 : EndIf
  If ((*copy\regionWidth - 1) / 4 + 1) * ((*copy\regionHeight - 1) / 4 + 1) > #ANVIL_VK_TILED_RECT_MAX_UTILES : ProcedureReturn -1 : EndIf
  tile\sourceBase = *copy\sourceBase : tile\destinationBase = *copy\destinationBase
  tile\sourceBytes = *copy\sourceBytes : tile\destinationBytes = *copy\destinationBytes
  tile\sourceLayout = *copy\sourceLayout : tile\destinationLayout = *copy\destinationLayout
  tile\width = *copy\width : tile\height = *copy\height
  For y = 0 To *copy\regionHeight - 1 Step 4
    For x = 0 To *copy\regionWidth - 1 Step 4
      tile\sourceX = *copy\sourceX + x : tile\sourceY = *copy\sourceY + y
      tile\destinationX = *copy\destinationX + x : tile\destinationY = *copy\destinationY + y
      tile\regionWidth = *copy\regionWidth - x : If tile\regionWidth > 4 : tile\regionWidth = 4 : EndIf
      tile\regionHeight = *copy\regionHeight - y : If tile\regionHeight > 4 : tile\regionHeight = 4 : EndIf
      If avkBackendTiledMicroCopyValidate(@tile) <> 0 : ProcedureReturn -1 : EndIf
    Next
  Next
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendSubmitTiledEdgeTailCopy(*copy.AnvilVkBackendTiledRectCopy)
  If avkBackendTiledEdgeTailCopyValidate(*copy) <> 0 : ProcedureReturn -1 : EndIf
  avkTbCalls = avkTbCalls + 1 : avkTbTiledEdgeTailCopies = avkTbTiledEdgeTailCopies + 1
  avkTbLastRectSourceX = *copy\sourceX : avkTbLastRectSourceY = *copy\sourceY
  avkTbLastRectDestinationX = *copy\destinationX : avkTbLastRectDestinationY = *copy\destinationY
  avkTbLastRectWidth = *copy\regionWidth : avkTbLastRectHeight = *copy\regionHeight
  ProcedureReturn #ANVIL_VK_JOB_DONE
EndProcedure

Procedure.i avkBackendTiledMicroCopyValidate(*copy.AnvilVkBackendTiledRectCopy)
  If *copy = 0 : ProcedureReturn -1 : EndIf
  If *copy\sourceBase <= 0 Or *copy\destinationBase <= 0 Or *copy\sourceLayout = 0 Or *copy\destinationLayout = 0 Or *copy\sourceBytes < 64 Or *copy\destinationBytes < 64 : ProcedureReturn -1 : EndIf
  If *copy\regionWidth < 1 Or *copy\regionWidth > 4 Or *copy\regionHeight < 1 Or *copy\regionHeight > 4 : ProcedureReturn -1 : EndIf
  If *copy\sourceX < 0 Or *copy\sourceY < 0 Or *copy\destinationX < 0 Or *copy\destinationY < 0 Or *copy\sourceX > *copy\width - *copy\regionWidth Or *copy\sourceY > *copy\height - *copy\regionHeight Or *copy\destinationX > *copy\width - *copy\regionWidth Or *copy\destinationY > *copy\height - *copy\regionHeight : ProcedureReturn -1 : EndIf
  If (*copy\sourceX % 4) + *copy\regionWidth > 4 Or (*copy\sourceY % 4) + *copy\regionHeight > 4 Or (*copy\destinationX % 4) + *copy\regionWidth > 4 Or (*copy\destinationY % 4) + *copy\regionHeight > 4 : ProcedureReturn -1 : EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendSubmitTiledMicroCopy(*copy.AnvilVkBackendTiledRectCopy)
  If avkBackendTiledMicroCopyValidate(*copy) <> 0 : ProcedureReturn -1 : EndIf
  avkTbCalls = avkTbCalls + 1
  avkTbTiledMicroCopies = avkTbTiledMicroCopies + 1
  avkTbLastRectSourceX = *copy\sourceX : avkTbLastRectSourceY = *copy\sourceY
  avkTbLastRectDestinationX = *copy\destinationX : avkTbLastRectDestinationY = *copy\destinationY
  avkTbLastRectWidth = *copy\regionWidth : avkTbLastRectHeight = *copy\regionHeight
  ProcedureReturn #ANVIL_VK_JOB_DONE
EndProcedure

Procedure.i avkBackendLinearTiledRectCopyValidate(*copy.AnvilVkBackendLinearTiledRectCopy)
  If *copy = 0 : ProcedureReturn -1 : EndIf
  If *copy\sourceBase <= 0 Or *copy\destinationBase <= 0 Or *copy\width < 1 Or *copy\height < 1 Or *copy\sourceViewWidth < 1 Or *copy\sourceViewHeight < 1 Or *copy\sourcePitch < *copy\sourceViewWidth * 4 Or (*copy\sourcePitch % 4) <> 0 Or *copy\sourcePitch - 16 > 32767 Or *copy\sourceBytes < (*copy\sourceViewHeight - 1) * *copy\sourcePitch + *copy\sourceViewWidth * 4 Or *copy\destinationLayout = 0 : ProcedureReturn -1 : EndIf
  If *copy\paddedWidth < *copy\width Or *copy\paddedHeight < *copy\height Or (*copy\paddedWidth % 32) <> 0 Or (*copy\paddedHeight % 8) <> 0 Or *copy\destinationBytes < *copy\paddedWidth * *copy\paddedHeight * 4 : ProcedureReturn -1 : EndIf
  If *copy\regionWidth < 1 Or *copy\regionHeight < 1 Or (*copy\destinationX % 4) <> 0 Or (*copy\destinationY % 4) <> 0 : ProcedureReturn -1 : EndIf
  If *copy\sourceX < 0 Or *copy\sourceY < 0 Or *copy\destinationX < 0 Or *copy\destinationY < 0 Or *copy\sourceX > *copy\sourceViewWidth - *copy\regionWidth Or *copy\sourceY > *copy\sourceViewHeight - *copy\regionHeight Or *copy\destinationX > *copy\width - *copy\regionWidth Or *copy\destinationY > *copy\height - *copy\regionHeight : ProcedureReturn -1 : EndIf
  If ((*copy\regionWidth % 4) <> 0 And *copy\destinationX <> *copy\width - *copy\regionWidth) Or ((*copy\regionHeight % 4) <> 0 And *copy\destinationY <> *copy\height - *copy\regionHeight) : ProcedureReturn -1 : EndIf
  If ((*copy\regionWidth - 1) / 4 + 1) * ((*copy\regionHeight - 1) / 4 + 1) > #ANVIL_VK_TILED_RECT_MAX_UTILES : ProcedureReturn -1 : EndIf
  If (*copy\regionWidth % 4) <> 0 And *copy\sourcePitch - (*copy\regionWidth % 4) * 4 > 32767 : ProcedureReturn -1 : EndIf
  If (*copy\sourceBase % 4) <> 0 Or (*copy\destinationBase % 4) <> 0 Or *copy\windowBase <= 0 Or *copy\windowBytes < 1 : ProcedureReturn -1 : EndIf
  If *copy\sourceBase < *copy\windowBase Or *copy\sourceBase - *copy\windowBase > *copy\windowBytes - *copy\sourceBytes Or *copy\destinationBase < *copy\windowBase Or *copy\destinationBase - *copy\windowBase > *copy\windowBytes - *copy\destinationBytes : ProcedureReturn -1 : EndIf
  If *copy\sourceBase < *copy\destinationBase + *copy\destinationBytes And *copy\destinationBase < *copy\sourceBase + *copy\sourceBytes : ProcedureReturn -1 : EndIf
  If (*copy\sourceY + *copy\regionHeight - 1) * *copy\sourcePitch + (*copy\sourceX + *copy\regionWidth) * 4 > *copy\sourceBytes : ProcedureReturn -1 : EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendSubmitLinearTiledRectCopy(*copy.AnvilVkBackendLinearTiledRectCopy)
  If avkBackendLinearTiledRectCopyValidate(*copy) <> 0 : ProcedureReturn -1 : EndIf
  avkTbCalls = avkTbCalls + 1
  avkTbLinearTiledRectCopies = avkTbLinearTiledRectCopies + 1
  avkTbLastLinearRectSourceX = *copy\sourceX : avkTbLastLinearRectSourceY = *copy\sourceY
  avkTbLastLinearRectDestinationX = *copy\destinationX : avkTbLastLinearRectDestinationY = *copy\destinationY
  avkTbLastLinearRectWidth = *copy\regionWidth : avkTbLastLinearRectHeight = *copy\regionHeight
  avkTbLastLinearRectSourcePitch = *copy\sourcePitch
  avkTbLastLinearRectSourceBytes = *copy\sourceBytes
  avkTbLastLinearRectSourceViewWidth = *copy\sourceViewWidth : avkTbLastLinearRectSourceViewHeight = *copy\sourceViewHeight
  ProcedureReturn #ANVIL_VK_JOB_DONE
EndProcedure

Procedure.i avkBackendLinearTiledMicroCopyValidate(*copy.AnvilVkBackendLinearTiledRectCopy)
  If *copy = 0 : ProcedureReturn -1 : EndIf
  If *copy\regionWidth < 1 Or *copy\regionWidth > 4 Or *copy\regionHeight < 1 Or *copy\regionHeight > 4 Or *copy\destinationX < 0 Or *copy\destinationY < 0 Or *copy\sourceX < 0 Or *copy\sourceY < 0 : ProcedureReturn -1 : EndIf
  If (*copy\destinationX % 4) + *copy\regionWidth > 4 Or (*copy\destinationY % 4) + *copy\regionHeight > 4 Or *copy\destinationX > *copy\width - *copy\regionWidth Or *copy\destinationY > *copy\height - *copy\regionHeight : ProcedureReturn -1 : EndIf
  If *copy\sourceViewWidth < *copy\regionWidth Or *copy\sourceViewHeight < *copy\regionHeight Or *copy\sourceX > *copy\sourceViewWidth - *copy\regionWidth Or *copy\sourceY > *copy\sourceViewHeight - *copy\regionHeight Or *copy\sourcePitch < *copy\sourceViewWidth * 4 Or (*copy\sourcePitch % 4) <> 0 Or *copy\sourcePitch - *copy\regionWidth * 4 > 32767 : ProcedureReturn -1 : EndIf
  If *copy\sourceBytes < (*copy\sourceViewHeight - 1) * *copy\sourcePitch + *copy\sourceViewWidth * 4 Or *copy\destinationLayout = 0 Or *copy\paddedWidth < *copy\width Or *copy\paddedHeight < *copy\height Or *copy\destinationBytes < *copy\paddedWidth * *copy\paddedHeight * 4 : ProcedureReturn -1 : EndIf
  If *copy\sourceBase < *copy\windowBase Or *copy\destinationBase < *copy\windowBase Or *copy\windowBytes < *copy\sourceBytes Or *copy\sourceBase - *copy\windowBase > *copy\windowBytes - *copy\sourceBytes Or *copy\windowBytes < *copy\destinationBytes Or *copy\destinationBase - *copy\windowBase > *copy\windowBytes - *copy\destinationBytes : ProcedureReturn -1 : EndIf
  If *copy\sourceBase < *copy\destinationBase + *copy\destinationBytes And *copy\destinationBase < *copy\sourceBase + *copy\sourceBytes : ProcedureReturn -1 : EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendSubmitLinearTiledMicroCopy(*copy.AnvilVkBackendLinearTiledRectCopy)
  If avkBackendLinearTiledMicroCopyValidate(*copy) <> 0 : ProcedureReturn -1 : EndIf
  avkTbCalls = avkTbCalls + 1
  avkTbLinearTiledMicroCopies = avkTbLinearTiledMicroCopies + 1
  avkTbLastLinearRectDestinationX = *copy\destinationX : avkTbLastLinearRectDestinationY = *copy\destinationY
  avkTbLastLinearRectWidth = *copy\regionWidth : avkTbLastLinearRectHeight = *copy\regionHeight
  avkTbLastLinearRectSourcePitch = *copy\sourcePitch : avkTbLastLinearRectSourceBytes = *copy\sourceBytes
  ProcedureReturn #ANVIL_VK_JOB_DONE
EndProcedure

Procedure.i avkBackendLinearTiledGridCopyValidate(*copy.AnvilVkBackendLinearTiledRectCopy)
  Define columns.i, rows.i, firstCols.i, lastCols.i, minCols.i
  If *copy = 0 : ProcedureReturn -1 : EndIf
  If *copy\regionWidth < 1 Or *copy\regionHeight < 1 Or *copy\destinationX < 0 Or *copy\destinationY < 0 Or *copy\sourceX <> 0 Or *copy\sourceY <> 0 Or *copy\sourceViewWidth <> *copy\regionWidth Or *copy\sourceViewHeight <> *copy\regionHeight : ProcedureReturn -1 : EndIf
  If *copy\destinationX > *copy\width - *copy\regionWidth Or *copy\destinationY > *copy\height - *copy\regionHeight Or *copy\sourcePitch < *copy\regionWidth * 4 Or (*copy\sourcePitch % 4) <> 0 Or *copy\sourceBytes <> (*copy\regionHeight - 1) * *copy\sourcePitch + *copy\regionWidth * 4 : ProcedureReturn -1 : EndIf
  columns = (*copy\destinationX + *copy\regionWidth - 1) / 4 - *copy\destinationX / 4 + 1
  rows = (*copy\destinationY + *copy\regionHeight - 1) / 4 - *copy\destinationY / 4 + 1
  firstCols = 4 - (*copy\destinationX % 4)
  If firstCols > *copy\regionWidth : firstCols = *copy\regionWidth : EndIf
  minCols = firstCols
  If columns > 1
    lastCols = (*copy\destinationX + *copy\regionWidth - 1) % 4 + 1
    If lastCols < minCols : minCols = lastCols : EndIf
  EndIf
  If *copy\sourcePitch - minCols * 4 > 32767 : ProcedureReturn -1 : EndIf
  If columns < 1 Or columns > 4 Or rows < 1 Or rows > 4 Or columns * rows < 2 Or *copy\destinationLayout = 0 Or *copy\paddedWidth < *copy\width Or *copy\paddedHeight < *copy\height Or *copy\destinationBytes < *copy\paddedWidth * *copy\paddedHeight * 4 : ProcedureReturn -1 : EndIf
  If *copy\windowBase <= 0 Or *copy\windowBytes < *copy\sourceBytes Or *copy\windowBytes < *copy\destinationBytes Or *copy\sourceBase < *copy\windowBase Or *copy\destinationBase < *copy\windowBase Or *copy\sourceBase - *copy\windowBase > *copy\windowBytes - *copy\sourceBytes Or *copy\destinationBase - *copy\windowBase > *copy\windowBytes - *copy\destinationBytes : ProcedureReturn -1 : EndIf
  If *copy\sourceBase < *copy\destinationBase + *copy\destinationBytes And *copy\destinationBase < *copy\sourceBase + *copy\sourceBytes : ProcedureReturn -1 : EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendSubmitLinearTiledGridCopy(*copy.AnvilVkBackendLinearTiledRectCopy)
  If avkBackendLinearTiledGridCopyValidate(*copy) <> 0 : ProcedureReturn -1 : EndIf
  avkTbCalls = avkTbCalls + 1
  avkTbLinearTiledGridCopies = avkTbLinearTiledGridCopies + 1
  avkTbLastLinearGridIntersections = ((*copy\destinationX + *copy\regionWidth - 1) / 4 - *copy\destinationX / 4 + 1) * ((*copy\destinationY + *copy\regionHeight - 1) / 4 - *copy\destinationY / 4 + 1)
  avkTbLastLinearRectDestinationX = *copy\destinationX : avkTbLastLinearRectDestinationY = *copy\destinationY
  avkTbLastLinearRectWidth = *copy\regionWidth : avkTbLastLinearRectHeight = *copy\regionHeight
  avkTbLastLinearRectSourcePitch = *copy\sourcePitch : avkTbLastLinearRectSourceBytes = *copy\sourceBytes
  ProcedureReturn #ANVIL_VK_JOB_DONE
EndProcedure

Procedure.i avkBackendTiledReadbackValidate(*copy.AnvilVkBackendTiledReadback)
  Define regionWidth.i, regionHeight.i
  If *copy = 0 : ProcedureReturn -1 : EndIf
  regionWidth = *copy\regionWidth : regionHeight = *copy\regionHeight
  If regionWidth = 0 And regionHeight = 0 And *copy\sourceX = 0 And *copy\sourceY = 0
    regionWidth = *copy\width : regionHeight = *copy\height
  EndIf
  If *copy\sourceBase <= 0 Or *copy\destinationBase <= 0 Or *copy\sourceBytes < 1 Or *copy\destinationBytes < 1 Or regionWidth < 1 Or regionHeight < 1 Or *copy\destinationPitch < regionWidth * 4 Or *copy\sourceLayout = 0
    ProcedureReturn -1
  EndIf
  If *copy\sourceX < 0 Or *copy\sourceY < 0 Or *copy\sourceX > *copy\width - regionWidth Or *copy\sourceY > *copy\height - regionHeight
    ProcedureReturn -1
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendSubmitTiledReadback(*copy.AnvilVkBackendTiledReadback)
  If avkBackendTiledReadbackValidate(*copy) <> 0 : ProcedureReturn -1 : EndIf
  avkTbCalls = avkTbCalls + 1
  ProcedureReturn #ANVIL_VK_JOB_DONE
EndProcedure

Procedure.i avkBackendTiledMicroReadbackValidate(*copy.AnvilVkBackendTiledReadback)
  If *copy = 0 : ProcedureReturn -1 : EndIf
  If *copy\sourceBase <= 0 Or *copy\destinationBase <= 0 Or *copy\sourceLayout = 0 Or *copy\regionWidth < 1 Or *copy\regionWidth > 4 Or *copy\regionHeight < 1 Or *copy\regionHeight > 4 : ProcedureReturn -1 : EndIf
  If *copy\sourceX < 0 Or *copy\sourceY < 0 Or *copy\sourceX > *copy\width - *copy\regionWidth Or *copy\sourceY > *copy\height - *copy\regionHeight Or (*copy\sourceX % 4) + *copy\regionWidth > 4 Or (*copy\sourceY % 4) + *copy\regionHeight > 4 : ProcedureReturn -1 : EndIf
  If *copy\destinationPitch < *copy\regionWidth * 4 Or (*copy\destinationPitch % 4) <> 0 Or *copy\destinationPitch - *copy\regionWidth * 4 > 32767 Or *copy\destinationBytes < (*copy\regionHeight - 1) * *copy\destinationPitch + *copy\regionWidth * 4 : ProcedureReturn -1 : EndIf
  If *copy\paddedWidth < *copy\width Or *copy\paddedHeight < *copy\height Or *copy\sourceBytes < *copy\paddedWidth * *copy\paddedHeight * 4 : ProcedureReturn -1 : EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendSubmitTiledMicroReadback(*copy.AnvilVkBackendTiledReadback)
  If avkBackendTiledMicroReadbackValidate(*copy) <> 0 : ProcedureReturn -1 : EndIf
  avkTbCalls = avkTbCalls + 1 : avkTbTiledMicroReadbacks = avkTbTiledMicroReadbacks + 1
  avkTbLastMicroReadSourceX = *copy\sourceX : avkTbLastMicroReadSourceY = *copy\sourceY
  avkTbLastMicroReadWidth = *copy\regionWidth : avkTbLastMicroReadHeight = *copy\regionHeight
  avkTbLastMicroReadPitch = *copy\destinationPitch : avkTbLastMicroReadSpan = *copy\destinationBytes
  ProcedureReturn #ANVIL_VK_JOB_DONE
EndProcedure

Procedure.i AnvilVkTestBackendTiledCopies()
  ProcedureReturn avkTbTiledCopies
EndProcedure

Procedure.i AnvilVkTestBackendLastCopySourcePitch()
  ProcedureReturn avkTbLastCopySourcePitch
EndProcedure

Procedure.i avkBackendClearSupported(base.i, bytes.i, w.i, h.i, pitch.i)
  If base <= 0 Or bytes <= 0 : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
  If pitch < (w * 4) Or (pitch * h) > bytes : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
  If avkTbClearW <> 0 And w <> avkTbClearW : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
  If avkTbClearH <> 0 And h <> avkTbClearH : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkBackendSubmitClear(base.i, bytes.i, w.i, h.i, pitch.i, bgra.i)
  avkTbCalls = avkTbCalls + 1
  avkTbLastBase = base
  avkTbLastBytes = bytes
  avkTbLastW = w
  avkTbLastH = h
  avkTbLastPitch = pitch
  avkTbLastColor = bgra
  avkTbTicks = avkTbTicks + 1
  If avkTbFail <> 0
    avkTbNative = avkTbFail
    avkTbFail = 0
    ProcedureReturn -1
  EndIf
  avkTbNative = 0
  ; NOTHING IS WRITTEN TO `base`. See the header.
  If avkTbHold <> 0
    avkTbBusy = 1
    ProcedureReturn #ANVIL_VK_JOB_PENDING
  EndIf
  avkTbBusy = 0
  ProcedureReturn #ANVIL_VK_JOB_DONE
EndProcedure

Procedure.i avkBackendSubmitBufferCopy(source.i, destination.i, bytes.i)
  Define i.i
  If source = 0 Or destination = 0 Or bytes < 1 : ProcedureReturn -1 : EndIf
  i = 0
  While i < bytes
    PokeA(destination + i, PeekA(source + i))
    i = i + 1
  Wend
  ProcedureReturn #ANVIL_VK_JOB_DONE
EndProcedure

Global avkTbCopyRowsCalls.i = 0

Procedure.i avkBackendSubmitBufferCopyRows(source.i, sourcePitch.i, destination.i, destinationPitch.i, rowBytes.i, rows.i)
  Define row.i, column.i
  If source = 0 Or destination = 0 Or rowBytes < 1 Or rows < 1 Or sourcePitch < rowBytes Or destinationPitch < rowBytes
    ProcedureReturn -1
  EndIf
  avkTbCopyRowsCalls = avkTbCopyRowsCalls + 1
  For row = 0 To rows - 1
    For column = 0 To rowBytes - 1
      PokeA(destination + row * destinationPitch + column, PeekA(source + row * sourcePitch + column))
    Next
  Next
  ProcedureReturn #ANVIL_VK_JOB_DONE
EndProcedure

Procedure.i AnvilVkTestBackendCopyRowsCalls()
  ProcedureReturn avkTbCopyRowsCalls
EndProcedure

Procedure.i avkBackendSubmitBufferFill(destination.i, bytes.i, data.i)
  Define i.i
  If destination = 0 Or bytes < 1 Or (bytes % 4) <> 0 : ProcedureReturn -1 : EndIf
  i = 0
  While i < bytes
    PokeL(destination + i, data & $FFFFFFFF)
    i = i + 4
  Wend
  ProcedureReturn #ANVIL_VK_JOB_DONE
EndProcedure

Procedure.i avkBackendPoll()
  avkTbPolls = avkTbPolls + 1
  avkTbTicks = avkTbTicks + 1
  If avkTbPollFail <> 0
    avkTbNative = avkTbPollFail
    avkTbPollFail = 0
    avkTbBusy = 0
    ProcedureReturn -1
  EndIf
  If avkTbBusy <> 0 And avkTbHold <> 0 : ProcedureReturn 0 : EndIf
  avkTbBusy = 0
  ProcedureReturn 1
EndProcedure

Procedure.i avkBackendLastNativeError()
  ProcedureReturn avkTbNative
EndProcedure

; A counter, not a clock. It advances one microsecond per backend call,
; so a gate's timeouts are deterministic and a wait cannot spin forever.
Procedure.i avkBackendTicksUs()
  avkTbTicks = avkTbTicks + 1
  ProcedureReturn avkTbTicks
EndProcedure

; ======================================================================
;  THE GRAPHICS HALF -- still no pixels
; ======================================================================
;  It records what a pipeline was compiled from and what a draw asked
;  for, and it writes NOTHING into the render target or the vertex
;  buffer. A gate can therefore check that the whole public path from
;  vkCreateShaderModule to vkQueueSubmit reaches the backend with the
;  right numbers, and then check that the image still holds its poison.
Global avkTbPipelines.i = 0
Global avkTbDraws.i = 0
Global avkTbPipeBytes.i = 8192
Global avkTbDrawFail.i = 0
Global avkTbLastPipe.i = 0
Global avkTbLastPipeBase.i = 0
Global avkTbLastBindCount.i = 0
Global Dim avkTbLastVertexBase.i[#ANVIL_VK_MAX_BINDINGS]
Global Dim avkTbLastStride.i[#ANVIL_VK_MAX_BINDINGS]
Global avkTbLastVertexCount.i = 0
Global avkTbLastFirstVertex.i = 0
Global avkTbLastSampleMask.i = 0
Global avkTbLastBlendMode.i = #ANVIL_VK_BLEND_DISABLED
Global avkTbLastPushBase.i = 0
Global avkTbLastUniformBase.i = 0
Global avkTbLastUniformBytes.i = 0
Global avkTbLastSampledBase.i = 0
Global avkTbLastSampledWidth.i = 0
Global avkTbLastSampledHeight.i = 0
Global avkTbLastDrawColour.i = 0
Global Dim avkTbPipeBase.i[8]

Procedure AnvilVkTestBackendDrawFailNext()
  avkTbDrawFail = 1
EndProcedure

Procedure.i AnvilVkTestBackendPipelines()
  ProcedureReturn avkTbPipelines
EndProcedure

Procedure.i AnvilVkTestBackendDraws()
  ProcedureReturn avkTbDraws
EndProcedure

Procedure.i AnvilVkTestBackendLastBindingCount()
  ProcedureReturn avkTbLastBindCount
EndProcedure

; PER BINDING, because the record now carries one address and one stride
; for each. A reader that only ever showed binding zero would have been
; green on the day a second binding started pointing at nothing.
Procedure.i AnvilVkTestBackendLastVertexBase(b.i)
  If b < 0 Or b >= #ANVIL_VK_MAX_BINDINGS : ProcedureReturn 0 : EndIf
  ProcedureReturn avkTbLastVertexBase[b]
EndProcedure

Procedure.i AnvilVkTestBackendLastStride(b.i)
  If b < 0 Or b >= #ANVIL_VK_MAX_BINDINGS : ProcedureReturn 0 : EndIf
  ProcedureReturn avkTbLastStride[b]
EndProcedure

Procedure.i AnvilVkTestBackendLastVertexCount()
  ProcedureReturn avkTbLastVertexCount
EndProcedure

Procedure.i AnvilVkTestBackendLastFirstVertex()
  ProcedureReturn avkTbLastFirstVertex
EndProcedure

Procedure.i AnvilVkTestBackendLastSampleMask()
  ProcedureReturn avkTbLastSampleMask
EndProcedure

Procedure.i AnvilVkTestBackendLastBlendMode()
  ProcedureReturn avkTbLastBlendMode
EndProcedure

Procedure.i AnvilVkTestBackendLastPushBase()
  ProcedureReturn avkTbLastPushBase
EndProcedure

Procedure.i AnvilVkTestBackendLastUniformBase()
  ProcedureReturn avkTbLastUniformBase
EndProcedure

Procedure.i AnvilVkTestBackendLastUniformBytes()
  ProcedureReturn avkTbLastUniformBytes
EndProcedure

Procedure.i AnvilVkTestBackendLastSampledBase()
  ProcedureReturn avkTbLastSampledBase
EndProcedure

Procedure.i AnvilVkTestBackendLastSampledWidth()
  ProcedureReturn avkTbLastSampledWidth
EndProcedure

Procedure.i AnvilVkTestBackendLastSampledHeight()
  ProcedureReturn avkTbLastSampledHeight
EndProcedure

Procedure.i AnvilVkTestBackendLastDrawColor()
  ProcedureReturn avkTbLastDrawColour
EndProcedure

Procedure.i AnvilVkTestBackendLastPipelineBase()
  ProcedureReturn avkTbLastPipeBase
EndProcedure

Procedure.i avkBackendPipelineBytes()
  ProcedureReturn avkTbPipeBytes
EndProcedure

Procedure.i avkBackendPipelineBuild(*build.AnvilVkBackendPipelineBuildInfo)
  If *build = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  If *build\pipeline < 1 Or *build\pipeline > 7 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  If *build\base <= 0 Or *build\bytes < avkTbPipeBytes : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  If *build\vertexIr = 0 Or *build\fragmentIr = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  avkTbPipeBase[*build\pipeline] = *build\base
  avkTbLastPipe = *build\pipeline
  avkTbLastPipeBase = *build\base
  avkTbPipelines = avkTbPipelines + 1
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure avkBackendPipelineRelease(pipe.i)
  If pipe < 1 Or pipe > 7
    ProcedureReturn
  EndIf
  avkTbPipeBase[pipe] = 0
  If avkTbPipelines > 0 : avkTbPipelines = avkTbPipelines - 1 : EndIf
EndProcedure

Procedure.i avkBackendDrawSupported(base.i, bytes.i, w.i, h.i, pitch.i)
  ProcedureReturn avkBackendClearSupported(base, bytes, w, h, pitch)
EndProcedure

Procedure.i avkBackendSubmitDraw(*payload)
  Define *list.AnvilVkBackendDrawList
  Define legacyList.AnvilVkBackendDrawList
  Define *d.AnvilVkBackendDraw
  Define draw.i
  Define tbk.i
  Define *tbb.AnvilVkBackendBinding
  Define *tbs.AnvilVkBackendSampledImage
  If *payload = 0 : ProcedureReturn -1 : EndIf
  If (avkTbCaps & #ANVIL_VK_CAP_DRAW_LIST) <> 0
    *list = *payload
  Else
    legacyList\drawCount = 1
    legacyList\draws = *payload
    *list = @legacyList
  EndIf
  If *list\drawCount < 1 Or *list\drawCount > #ANVIL_VK_MAX_RECORDED_DRAWS Or *list\draws = 0 : ProcedureReturn -1 : EndIf
  ; Validate the complete closed transaction before publishing even the first
  ; draw observation. The test backend executes no pixels, but it preserves the
  ; same all-or-nothing admission boundary a hardware list backend must own.
  draw = 0
  While draw < *list\drawCount
    *d = *list\draws + (draw * SizeOf(AnvilVkBackendDraw))
    If *d\targetBase = 0 Or *d\targetBytes < 1 Or *d\bindingCount < 0 Or *d\bindingCount > #ANVIL_VK_MAX_BINDINGS
      ProcedureReturn -1
    EndIf
    If *d\kind = #ANVIL_VK_RENDER_OP_CLEAR_RECT
      If (avkTbCaps & #ANVIL_VK_CAP_CLEAR_ATTACHMENT_RECT) = 0 Or *d\clearRectX < 0 Or *d\clearRectY < 0 Or *d\clearRectW < 1 Or *d\clearRectH < 1 Or *d\clearRectW > *d\width Or *d\clearRectH > *d\height Or *d\clearRectX > *d\width - *d\clearRectW Or *d\clearRectY > *d\height - *d\clearRectH
        ProcedureReturn -1
      EndIf
    ElseIf *d\kind <> #ANVIL_VK_RENDER_OP_DRAW Or *d\pipeline < 1
      ProcedureReturn -1
    EndIf
    draw = draw + 1
  Wend
  avkTbCalls = avkTbCalls + 1
  avkTbDraws = avkTbDraws + *list\drawCount
  draw = 0
  While draw < *list\drawCount
    *d = *list\draws + (draw * SizeOf(AnvilVkBackendDraw))
    avkTbLastBase = *d\targetBase
    avkTbLastBytes = *d\targetBytes
    avkTbLastW = *d\width
    avkTbLastH = *d\height
    avkTbLastPitch = *d\pitch
    avkTbLastDrawColour = *d\clearBgra
    avkTbLastKind = *d\kind
    avkTbLastClearX = *d\clearRectX : avkTbLastClearY = *d\clearRectY
    avkTbLastClearW = *d\clearRectW : avkTbLastClearH = *d\clearRectH
    avkTbLastClearBgra = *d\clearRectBgra
    avkTbLastBindCount = *d\bindingCount
    tbk = 0
    While tbk < #ANVIL_VK_MAX_BINDINGS
      avkTbLastVertexBase[tbk] = 0
      avkTbLastStride[tbk] = 0
      If *d\bindings <> 0 And tbk < *d\bindingCount
        *tbb = *d\bindings + (tbk * SizeOf(AnvilVkBackendBinding))
        avkTbLastVertexBase[tbk] = *tbb\base
        avkTbLastStride[tbk] = *tbb\stride
      EndIf
      tbk = tbk + 1
    Wend
    avkTbLastVertexCount = *d\vertexCount
    avkTbLastFirstVertex = *d\firstVertex
    avkTbLastSampleMask = *d\sampleMask
    avkTbLastBlendMode = *d\blendMode
    avkTbLastPushBase = *d\pushBase
    avkTbLastUniformBase = *d\uniformBase
    avkTbLastUniformBytes = *d\uniformBytes
    avkTbLastSampledBase = 0
    avkTbLastSampledWidth = 0
    avkTbLastSampledHeight = 0
    If *d\sampledImage <> 0
      *tbs = *d\sampledImage
      avkTbLastSampledBase = *tbs\base
      avkTbLastSampledWidth = *tbs\width
      avkTbLastSampledHeight = *tbs\height
    EndIf
    draw = draw + 1
  Wend
  avkTbTicks = avkTbTicks + 1
  tbk = 0
  While tbk < 9
    avkTbRetainSeen[tbk] = 0
    If avkTbRetainPtr[tbk] <> 0
      avkTbRetainSeen[tbk] = PeekI(avkTbRetainPtr[tbk])
    EndIf
    tbk = tbk + 1
  Wend
  If avkTbDrawFail <> 0
    avkTbNative = -777
    avkTbDrawFail = 0
    ProcedureReturn -1
  EndIf
  avkTbNative = 0
  ; NOTHING IS WRITTEN TO targetBase. See the header.
  If avkTbHold <> 0
    avkTbBusy = 1
    ProcedureReturn #ANVIL_VK_JOB_PENDING
  EndIf
  avkTbBusy = 0
  ProcedureReturn #ANVIL_VK_JOB_DONE
EndProcedure

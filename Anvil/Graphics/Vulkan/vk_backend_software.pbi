; ======================================================================
;  Software Vulkan backend
; ======================================================================
; SPDX-License-Identifier: MIT
;
; This executor implements the bounded public Vulkan command subset on a
; processor. A board supplies display memory and presentation separately.
; The backend owns a fixed host-visible heap, and never advertises GPU work.

XIncludeFile "Anvil/Graphics/Vulkan/vk_foundation.pbi"

#AVK_SW_HEAP_BYTES = 67108864
#AVK_SW_MAX_DIMENSION = 4096
#AVK_SW_IMAGE_LAYOUT = 1
Global Dim avkSwStorage.a[#AVK_SW_HEAP_BYTES]
Global avkSwHeap.i = 0
Global avkSwJobs.i = 0
Global avkSwDraws.i = 0
Global avkSwNativeError.i = 0

Procedure.i avkSwEnsureHeap()
  If avkSwHeap = 0 : avkSwHeap = @avkSwStorage[0] : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i avkSwRange(base.i, bytes.i)
  If avkSwHeap = 0 Or base < avkSwHeap Or bytes < 1 Or bytes > #AVK_SW_HEAP_BYTES
    ProcedureReturn 0
  EndIf
  ProcedureReturn Bool(base - avkSwHeap <= #AVK_SW_HEAP_BYTES - bytes)
EndProcedure

Procedure avkSwCopy(source.i, destination.i, bytes.i)
  Define k.i
  If source = destination Or bytes < 1
    ProcedureReturn
  EndIf
  If destination > source And destination - source < bytes
    For k = bytes - 1 To 0 Step -1
      PokeA(destination + k, PeekA(source + k))
    Next
  Else
    For k = 0 To bytes - 1
      PokeA(destination + k, PeekA(source + k))
    Next
  EndIf
EndProcedure

Procedure.i avkBackendCaps()
  If avkSwEnsureHeap() = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn #ANVIL_VK_CAP_DEVICE | #ANVIL_VK_CAP_CLEAR_COLOR | #ANVIL_VK_CAP_DRAW | #ANVIL_VK_CAP_BLEND_SRC_OVER | #ANVIL_VK_CAP_DRAW_LIST | #ANVIL_VK_CAP_BUFFER_TRANSFER | #ANVIL_VK_CAP_LINEAR_TRANSFER | #ANVIL_VK_CAP_CLEAR_ATTACHMENT_RECT | #ANVIL_VK_CAP_TILED_RECT_COPY | #ANVIL_VK_CAP_TILED_EDGE_TAIL_COPY | #ANVIL_VK_CAP_TILED_MICRO_COPY | #ANVIL_VK_CAP_TILED_MICRO_READBACK | #ANVIL_VK_CAP_TILED_TO_LINEAR_MICRO_COPY | #ANVIL_VK_CAP_LINEAR_TO_TILED_RECT_COPY | #ANVIL_VK_CAP_LINEAR_TO_TILED_MICRO_COPY | #ANVIL_VK_CAP_BUFFER_TO_TILED_RECT_COPY | #ANVIL_VK_CAP_BUFFER_TO_TILED_TAIL_COPY | #ANVIL_VK_CAP_BUFFER_TO_TILED_MICRO_COPY | #ANVIL_VK_CAP_BUFFER_TO_TILED_GRID_COPY | #ANVIL_VK_CAP_BUFFER_TO_TILED_GRID_4X4_COPY
EndProcedure

Procedure.i avkBackendName()
  ProcedureReturn "software BGRA8 Vulkan backend"
EndProcedure

Procedure.i avkBackendPrepare()
  If avkSwEnsureHeap() = 0 : ProcedureReturn #VK_ERROR_OUT_OF_HOST_MEMORY : EndIf
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkBackendComputeCanLower(*ir)
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendComputeScratchBytes()
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendSubmitCompute(*job.AnvilVkBackendComputeJob, *result.AnvilVkBackendComputeResult)
  ProcedureReturn -1
EndProcedure

; No V3D is owned by this backend; refuse GPU lease requests.
Procedure.i avkBackendGpuLeaseAcquire(owner.i)
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendGpuLeaseRelease(owner.i)
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendGpuLeaseQuarantine(owner.i)
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendGpuLeaseState()
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendGpuLeaseRequired()
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendHeapBase()
  ProcedureReturn avkSwHeap
EndProcedure

Procedure.i avkBackendHeapBytes()
  ProcedureReturn #AVK_SW_HEAP_BYTES
EndProcedure

Procedure.i avkBackendMemoryTypeCount()
  ProcedureReturn 1
EndProcedure

Procedure.i avkBackendMemoryTypeFlags(index.i)
  If index <> 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn #VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT | #VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | #VK_MEMORY_PROPERTY_HOST_COHERENT_BIT
EndProcedure

Procedure.i avkBackendMemoryTypeHeap(index.i)
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendHeapCount()
  ProcedureReturn 1
EndProcedure

Procedure.i avkBackendHeapSizeOf(index.i)
  If index <> 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn #AVK_SW_HEAP_BYTES
EndProcedure

Procedure.i avkBackendHeapFlagsOf(index.i)
  If index <> 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn #VK_MEMORY_HEAP_DEVICE_LOCAL_BIT
EndProcedure

Procedure.i avkBackendImageAlignment()
  ProcedureReturn 64
EndProcedure

Procedure.i avkBackendImageCopySourceAlignment()
  ProcedureReturn 1
EndProcedure

Procedure.i avkBackendRowPitchFor(width.i)
  ProcedureReturn width * 4
EndProcedure

Procedure.i avkBackendMaxImageDimension2D()
  ProcedureReturn #AVK_SW_MAX_DIMENSION
EndProcedure

Procedure avkBackendRenderAreaGranularity(*out.VkExtent2D)
  *out\width = 1
  *out\height = 1
EndProcedure

Procedure.i avkBackendSampledMaxDimension2D(tiling.i)
  If tiling = #VK_IMAGE_TILING_LINEAR Or tiling = #VK_IMAGE_TILING_OPTIMAL
    ProcedureReturn #AVK_SW_MAX_DIMENSION
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendImagePlan(width.i, height.i, format.i, tiling.i, usage.i, *plan.AnvilVkBackendImagePlan)
  If *plan = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  *plan\bytes = 0 : *plan\alignment = 0 : *plan\rowPitch = 0
  *plan\backendLayout = 0 : *plan\paddedWidth = 0 : *plan\paddedHeight = 0
  If format <> #VK_FORMAT_B8G8R8A8_UNORM Or width < 1 Or height < 1 Or width > #AVK_SW_MAX_DIMENSION Or height > #AVK_SW_MAX_DIMENSION
    ProcedureReturn #VK_ERROR_FORMAT_NOT_SUPPORTED
  EndIf
  If tiling <> #VK_IMAGE_TILING_LINEAR And tiling <> #VK_IMAGE_TILING_OPTIMAL
    ProcedureReturn #VK_ERROR_FORMAT_NOT_SUPPORTED
  EndIf
  *plan\bytes = width * height * 4
  *plan\alignment = 64
  *plan\paddedWidth = width : *plan\paddedHeight = height
  If tiling = #VK_IMAGE_TILING_LINEAR
    *plan\rowPitch = width * 4
  Else
    ; Optimal layout is private even when this executor stores tight rows.
    *plan\backendLayout = #AVK_SW_IMAGE_LAYOUT
  EndIf
  ProcedureReturn #VK_SUCCESS
EndProcedure

  Procedure.i avkBackendImageCopyValidate(*copy.AnvilVkBackendImageCopy)
    If *copy = 0 Or *copy\destinationLayout <> #AVK_SW_IMAGE_LAYOUT : ProcedureReturn -1 : EndIf
    If *copy\width < 1 Or *copy\height < 1 Or *copy\width > #AVK_SW_MAX_DIMENSION Or *copy\height > #AVK_SW_MAX_DIMENSION : ProcedureReturn -1 : EndIf
    If *copy\sourcePitch < *copy\width * 4 Or *copy\sourceBytes < (*copy\height - 1) * *copy\sourcePitch + *copy\width * 4 : ProcedureReturn -1 : EndIf
    If *copy\destinationBytes < *copy\width * *copy\height * 4 : ProcedureReturn -1 : EndIf
    If avkSwRange(*copy\destinationBase, *copy\destinationBytes) = 0 : ProcedureReturn -1 : EndIf
    ProcedureReturn 0
  EndProcedure

  Procedure.i avkBackendImageCopyBatchReady()
    ProcedureReturn 1
  EndProcedure

  Procedure.i avkBackendSubmitImageCopy(*copy.AnvilVkBackendImageCopy)
    Define row.i
    If avkBackendImageCopyValidate(*copy) <> 0 : ProcedureReturn -1 : EndIf
    For row = 0 To *copy\height - 1
      avkSwCopy(*copy\sourceBase + row * *copy\sourcePitch, *copy\destinationBase + row * *copy\width * 4, *copy\width * 4)
    Next
    avkSwJobs = avkSwJobs + 1
    ProcedureReturn #ANVIL_VK_JOB_DONE
  EndProcedure

  Procedure.i avkBackendTiledImageCopyValidate(*copy.AnvilVkBackendTiledImageCopy)
    If *copy = 0 Or *copy\sourceLayout <> #AVK_SW_IMAGE_LAYOUT Or *copy\destinationLayout <> #AVK_SW_IMAGE_LAYOUT : ProcedureReturn -1 : EndIf
    If *copy\width < 1 Or *copy\height < 1 Or *copy\width > #AVK_SW_MAX_DIMENSION Or *copy\height > #AVK_SW_MAX_DIMENSION : ProcedureReturn -1 : EndIf
    If *copy\sourceBytes < *copy\width * *copy\height * 4 Or *copy\destinationBytes < *copy\width * *copy\height * 4 : ProcedureReturn -1 : EndIf
    If avkSwRange(*copy\sourceBase, *copy\sourceBytes) = 0 Or avkSwRange(*copy\destinationBase, *copy\destinationBytes) = 0 : ProcedureReturn -1 : EndIf
    ProcedureReturn 0
  EndProcedure

  Procedure.i avkBackendSubmitTiledImageCopy(*copy.AnvilVkBackendTiledImageCopy)
    If avkBackendTiledImageCopyValidate(*copy) <> 0 : ProcedureReturn -1 : EndIf
    avkSwCopy(*copy\sourceBase, *copy\destinationBase, *copy\width * *copy\height * 4)
    avkSwJobs = avkSwJobs + 1
    ProcedureReturn #ANVIL_VK_JOB_DONE
  EndProcedure

  Procedure.i avkBackendTiledRectCopyValidate(*copy.AnvilVkBackendTiledRectCopy)
    If *copy = 0 Or *copy\sourceLayout <> #AVK_SW_IMAGE_LAYOUT Or *copy\destinationLayout <> #AVK_SW_IMAGE_LAYOUT : ProcedureReturn -1 : EndIf
    If *copy\width < 1 Or *copy\height < 1 Or *copy\width > #AVK_SW_MAX_DIMENSION Or *copy\height > #AVK_SW_MAX_DIMENSION : ProcedureReturn -1 : EndIf
    If *copy\regionWidth < 1 Or *copy\regionHeight < 1 Or *copy\sourceX < 0 Or *copy\sourceY < 0 Or *copy\destinationX < 0 Or *copy\destinationY < 0 : ProcedureReturn -1 : EndIf
    If *copy\sourceX > *copy\width - *copy\regionWidth Or *copy\destinationX > *copy\width - *copy\regionWidth : ProcedureReturn -1 : EndIf
    If *copy\sourceY > *copy\height - *copy\regionHeight Or *copy\destinationY > *copy\height - *copy\regionHeight : ProcedureReturn -1 : EndIf
    If *copy\sourceBytes < *copy\width * *copy\height * 4 Or *copy\destinationBytes < *copy\width * *copy\height * 4 : ProcedureReturn -1 : EndIf
    If avkSwRange(*copy\sourceBase, *copy\sourceBytes) = 0 Or avkSwRange(*copy\destinationBase, *copy\destinationBytes) = 0 : ProcedureReturn -1 : EndIf
    ProcedureReturn 0
  EndProcedure

  Procedure.i avkBackendSubmitTiledRectCopy(*copy.AnvilVkBackendTiledRectCopy)
    Define row.i
    If avkBackendTiledRectCopyValidate(*copy) <> 0 : ProcedureReturn -1 : EndIf
    For row = 0 To *copy\regionHeight - 1
      avkSwCopy(*copy\sourceBase + ((*copy\sourceY + row) * *copy\width + *copy\sourceX) * 4, *copy\destinationBase + ((*copy\destinationY + row) * *copy\width + *copy\destinationX) * 4, *copy\regionWidth * 4)
    Next
    avkSwJobs = avkSwJobs + 1
    ProcedureReturn #ANVIL_VK_JOB_DONE
  EndProcedure

  Procedure.i avkBackendTiledEdgeTailCopyValidate(*copy.AnvilVkBackendTiledRectCopy)
    ProcedureReturn avkBackendTiledRectCopyValidate(*copy)
  EndProcedure

  Procedure.i avkBackendSubmitTiledEdgeTailCopy(*copy.AnvilVkBackendTiledRectCopy)
    ProcedureReturn avkBackendSubmitTiledRectCopy(*copy)
  EndProcedure

  Procedure.i avkBackendTiledMicroCopyValidate(*copy.AnvilVkBackendTiledRectCopy)
    ProcedureReturn avkBackendTiledRectCopyValidate(*copy)
  EndProcedure

  Procedure.i avkBackendSubmitTiledMicroCopy(*copy.AnvilVkBackendTiledRectCopy)
    ProcedureReturn avkBackendSubmitTiledRectCopy(*copy)
  EndProcedure

  Procedure.i avkBackendLinearTiledRectCopyValidate(*copy.AnvilVkBackendLinearTiledRectCopy)
    If *copy = 0 Or *copy\destinationLayout <> #AVK_SW_IMAGE_LAYOUT : ProcedureReturn -1 : EndIf
    If *copy\width < 1 Or *copy\height < 1 Or *copy\width > #AVK_SW_MAX_DIMENSION Or *copy\height > #AVK_SW_MAX_DIMENSION : ProcedureReturn -1 : EndIf
    If *copy\regionWidth < 1 Or *copy\regionHeight < 1 Or *copy\sourcePitch < *copy\regionWidth * 4 : ProcedureReturn -1 : EndIf
    If *copy\sourceX < 0 Or *copy\sourceY < 0 Or *copy\destinationX < 0 Or *copy\destinationY < 0 : ProcedureReturn -1 : EndIf
    If *copy\sourceX > *copy\sourceViewWidth - *copy\regionWidth Or *copy\sourceY > *copy\sourceViewHeight - *copy\regionHeight : ProcedureReturn -1 : EndIf
    If *copy\destinationX > *copy\width - *copy\regionWidth Or *copy\destinationY > *copy\height - *copy\regionHeight : ProcedureReturn -1 : EndIf
    If *copy\sourceBytes < (*copy\sourceY + *copy\regionHeight - 1) * *copy\sourcePitch + (*copy\sourceX + *copy\regionWidth) * 4 : ProcedureReturn -1 : EndIf
    If *copy\destinationBytes < *copy\width * *copy\height * 4 : ProcedureReturn -1 : EndIf
    If avkSwRange(*copy\destinationBase, *copy\destinationBytes) = 0 : ProcedureReturn -1 : EndIf
    ProcedureReturn 0
  EndProcedure

  Procedure.i avkBackendSubmitLinearTiledRectCopy(*copy.AnvilVkBackendLinearTiledRectCopy)
    Define row.i
    If avkBackendLinearTiledRectCopyValidate(*copy) <> 0 : ProcedureReturn -1 : EndIf
    For row = 0 To *copy\regionHeight - 1
      avkSwCopy(*copy\sourceBase + (*copy\sourceY + row) * *copy\sourcePitch + *copy\sourceX * 4, *copy\destinationBase + ((*copy\destinationY + row) * *copy\width + *copy\destinationX) * 4, *copy\regionWidth * 4)
    Next
    avkSwJobs = avkSwJobs + 1
    ProcedureReturn #ANVIL_VK_JOB_DONE
  EndProcedure

  Procedure.i avkBackendLinearTiledMicroCopyValidate(*copy.AnvilVkBackendLinearTiledRectCopy)
    ProcedureReturn avkBackendLinearTiledRectCopyValidate(*copy)
  EndProcedure

  Procedure.i avkBackendSubmitLinearTiledMicroCopy(*copy.AnvilVkBackendLinearTiledRectCopy)
    ProcedureReturn avkBackendSubmitLinearTiledRectCopy(*copy)
  EndProcedure

  Procedure.i avkBackendLinearTiledGridCopyValidate(*copy.AnvilVkBackendLinearTiledRectCopy)
    ProcedureReturn avkBackendLinearTiledRectCopyValidate(*copy)
  EndProcedure

  Procedure.i avkBackendSubmitLinearTiledGridCopy(*copy.AnvilVkBackendLinearTiledRectCopy)
    ProcedureReturn avkBackendSubmitLinearTiledRectCopy(*copy)
  EndProcedure

  Procedure.i avkBackendTiledReadbackValidate(*copy.AnvilVkBackendTiledReadback)
    If *copy = 0 Or *copy\sourceLayout <> #AVK_SW_IMAGE_LAYOUT : ProcedureReturn -1 : EndIf
    If *copy\width < 1 Or *copy\height < 1 Or *copy\width > #AVK_SW_MAX_DIMENSION Or *copy\height > #AVK_SW_MAX_DIMENSION : ProcedureReturn -1 : EndIf
    If *copy\regionWidth < 1 Or *copy\regionHeight < 1 Or *copy\sourceX < 0 Or *copy\sourceY < 0 : ProcedureReturn -1 : EndIf
    If *copy\sourceX > *copy\width - *copy\regionWidth Or *copy\sourceY > *copy\height - *copy\regionHeight : ProcedureReturn -1 : EndIf
    If *copy\destinationPitch < *copy\regionWidth * 4 Or *copy\destinationBytes < (*copy\regionHeight - 1) * *copy\destinationPitch + *copy\regionWidth * 4 : ProcedureReturn -1 : EndIf
    If *copy\sourceBytes < *copy\width * *copy\height * 4 : ProcedureReturn -1 : EndIf
    If avkSwRange(*copy\sourceBase, *copy\sourceBytes) = 0 Or avkSwRange(*copy\destinationBase, *copy\destinationBytes) = 0 : ProcedureReturn -1 : EndIf
    ProcedureReturn 0
  EndProcedure

  Procedure.i avkBackendSubmitTiledReadback(*copy.AnvilVkBackendTiledReadback)
    Define row.i
    If avkBackendTiledReadbackValidate(*copy) <> 0 : ProcedureReturn -1 : EndIf
    For row = 0 To *copy\regionHeight - 1
      avkSwCopy(*copy\sourceBase + ((*copy\sourceY + row) * *copy\width + *copy\sourceX) * 4, *copy\destinationBase + row * *copy\destinationPitch, *copy\regionWidth * 4)
    Next
    avkSwJobs = avkSwJobs + 1
    ProcedureReturn #ANVIL_VK_JOB_DONE
  EndProcedure

  Procedure.i avkBackendTiledMicroReadbackValidate(*copy.AnvilVkBackendTiledReadback)
    ProcedureReturn avkBackendTiledReadbackValidate(*copy)
  EndProcedure

  Procedure.i avkBackendSubmitTiledMicroReadback(*copy.AnvilVkBackendTiledReadback)
    ProcedureReturn avkBackendSubmitTiledReadback(*copy)
  EndProcedure

Procedure.i avkBackendSubmitBufferCopy(source.i, destination.i, bytes.i)
  If source = 0 Or avkSwRange(destination, bytes) = 0 : ProcedureReturn -1 : EndIf
  avkSwCopy(source, destination, bytes)
  avkSwJobs = avkSwJobs + 1
  ProcedureReturn #ANVIL_VK_JOB_DONE
EndProcedure

Procedure.i avkBackendSubmitBufferCopyRows(source.i, sourcePitch.i, destination.i, destinationPitch.i, rowBytes.i, rows.i)
  Define row.i
  If source = 0 Or rowBytes < 1 Or rows < 1 Or sourcePitch < rowBytes Or destinationPitch < rowBytes : ProcedureReturn -1 : EndIf
  If avkSwRange(destination, (rows - 1) * destinationPitch + rowBytes) = 0 : ProcedureReturn -1 : EndIf
  For row = 0 To rows - 1
    avkSwCopy(source + row * sourcePitch, destination + row * destinationPitch, rowBytes)
  Next
  avkSwJobs = avkSwJobs + 1
  ProcedureReturn #ANVIL_VK_JOB_DONE
EndProcedure

Procedure.i avkBackendSubmitBufferFill(destination.i, bytes.i, data.i)
  Define k.i
  If avkSwRange(destination, bytes) = 0 Or (bytes % 4) <> 0 : ProcedureReturn -1 : EndIf
  For k = 0 To bytes - 1 Step 4
    PokeL(destination + k, data)
  Next
  avkSwJobs = avkSwJobs + 1
  ProcedureReturn #ANVIL_VK_JOB_DONE
EndProcedure

Procedure.i avkBackendClearSupported(base.i, bytes.i, w.i, h.i, pitch.i)
  If w < 1 Or h < 1 Or w > #AVK_SW_MAX_DIMENSION Or h > #AVK_SW_MAX_DIMENSION Or pitch < w * 4 Or bytes < (h - 1) * pitch + w * 4
    ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT
  EndIf
  If avkSwRange(base, bytes) = 0 : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkBackendSubmitClear(base.i, bytes.i, w.i, h.i, pitch.i, bgra.i)
  Define x.i, y.i
  If avkBackendClearSupported(base, bytes, w, h, pitch) <> #VK_SUCCESS : ProcedureReturn -1 : EndIf
  For y = 0 To h - 1
    For x = 0 To w - 1
      PokeL(base + y * pitch + x * 4, bgra)
    Next
  Next
  avkSwJobs = avkSwJobs + 1
  ProcedureReturn #ANVIL_VK_JOB_DONE
EndProcedure

Procedure.i avkBackendPoll()
  ProcedureReturn 1
EndProcedure

Procedure.i avkBackendLastNativeError()
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendTicksUs()
  ; Every software job completes before the submit call returns.
  ProcedureReturn 0
EndProcedure

; Pipeline metadata is retained by the portable pipeline slot. Only the
; verified front-end's current single-block vertex/fragment plans are used.
Procedure.i avkBackendPipelineBytes()
  ProcedureReturn 64
EndProcedure

Procedure.i avkBackendPipelineBuild(*build.AnvilVkBackendPipelineBuildInfo)
  Define *vs.AvkIrModule
  Define *fs.AvkIrModule
  If *build = 0 Or *build\pipeline < 1 Or *build\pipeline > #ANVIL_VK_MAX_PIPELINES Or *build\base = 0 Or *build\bytes < 64
    ProcedureReturn #ANVIL_VK_ERR_ARGS
  EndIf
  *vs = *build\vertexIr : *fs = *build\fragmentIr
  If *vs = 0 Or *fs = 0 Or *vs\stage <> #ANVIL_IR_STAGE_VERTEX Or *fs\stage <> #ANVIL_IR_STAGE_FRAGMENT
    ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT
  EndIf
  If AnvilVkPipelineTopology(*build\pipeline) <> #VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST And AnvilVkPipelineTopology(*build\pipeline) <> #VK_PRIMITIVE_TOPOLOGY_TRIANGLE_STRIP
    ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT
  EndIf
  If AnvilVkPipelineAttrComponents(*build\pipeline, AnvilVkPipelinePositionAttr(*build\pipeline)) < 2
    ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT
  EndIf
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure avkBackendPipelineRelease(pipe.i)
EndProcedure

Procedure.i avkBackendDrawSupported(base.i, bytes.i, w.i, h.i, pitch.i)
  ProcedureReturn avkBackendClearSupported(base, bytes, w, h, pitch)
EndProcedure

; Convert finite IEEE-754 float32 bits to signed Q16 without a floating
; point runtime. The front end bounds positions, UVs and colour inputs.
Procedure.i avkSwFixed(bits.i)
  Define magnitude.i, exponent.i, shift.i
  If (bits & $7FFFFFFF) = 0 : ProcedureReturn 0 : EndIf
  exponent = (bits >> 23) & $FF
  If exponent = 0 Or exponent = $FF : ProcedureReturn 0 : EndIf
  magnitude = (bits & $7FFFFF) | $800000
  shift = exponent - 134
  If shift >= 0
    If shift > 30 : ProcedureReturn 0 : EndIf
    magnitude = magnitude << shift
  Else
    If shift < -63 : ProcedureReturn 0 : EndIf
    magnitude = magnitude >> (0 - shift)
  EndIf
  If (bits & $80000000) <> 0 : magnitude = 0 - magnitude : EndIf
  ProcedureReturn magnitude
EndProcedure

Procedure.i avkSwAttr(*d.AnvilVkBackendDraw, vertex.i, attr.i, component.i)
  Define b.i
  Define *binding.AnvilVkBackendBinding
  If attr < 0 Or attr >= AnvilVkPipelineAttrCount(*d\pipeline) : ProcedureReturn 0 : EndIf
  If component < 0 Or component >= AnvilVkPipelineAttrComponents(*d\pipeline, attr) : ProcedureReturn 0 : EndIf
  b = AnvilVkPipelineAttrBinding(*d\pipeline, attr)
  If b < 0 Or b >= *d\bindingCount : ProcedureReturn 0 : EndIf
  *binding = *d\bindings + b * SizeOf(AnvilVkBackendBinding)
  ProcedureReturn avkSwFixed(PeekL(*binding\base + vertex * *binding\stride + AnvilVkPipelineAttrOffset(*d\pipeline, attr) + component * 4))
EndProcedure

Procedure.i avkSwIndex(*d.AnvilVkBackendDraw, ordinal.i)
  Define at.i
  If *d\indexBase = 0 : ProcedureReturn *d\firstVertex + ordinal : EndIf
  If *d\indexType = #VK_INDEX_TYPE_UINT16
    at = *d\indexBase + (*d\firstVertex + ordinal) * 2
    ProcedureReturn PeekU(at) & $FFFF
  EndIf
  at = *d\indexBase + (*d\firstVertex + ordinal) * 4
  ProcedureReturn PeekL(at) & $FFFFFFFF
EndProcedure

Structure AvkSwVertex
  x.i
  y.i
  u.i
  v.i
  r.i
  g.i
  b.i
  a.i
EndStructure

Procedure avkSwVertex(*d.AnvilVkBackendDraw, ordinal.i, *out.AvkSwVertex)
  Define vertex.i
  Define attr.i
  Define p.i
  vertex = avkSwIndex(*d, ordinal)
  p = AnvilVkPipelinePositionAttr(*d\pipeline)
  *out\x = *d\viewportX * 256 + (avkSwAttr(*d, vertex, p, 0) + 65536) * *d\viewportW / 512
  *out\y = *d\viewportY * 256 + (avkSwAttr(*d, vertex, p, 1) + 65536) * *d\viewportH / 512
  attr = AnvilVkPipelineVaryingSource(*d\pipeline, 0)
  *out\u = avkSwAttr(*d, vertex, attr, 0)
  *out\v = avkSwAttr(*d, vertex, attr, 1)
  *out\r = avkSwAttr(*d, vertex, attr, 0)
  *out\g = avkSwAttr(*d, vertex, attr, 1)
  *out\b = avkSwAttr(*d, vertex, attr, 2)
  *out\a = avkSwAttr(*d, vertex, attr, 3)
EndProcedure

Procedure.i avkSwClamp(value.i)
  If value < 0 : ProcedureReturn 0 : EndIf
  If value > 65536 : ProcedureReturn 65536 : EndIf
  ProcedureReturn value
EndProcedure

Procedure.i avkSwPack(r.i, g.i, b.i, a.i)
  Define ri.i, gi.i, bi.i, ai.i
  ri = (avkSwClamp(r) * 255 + 32768) / 65536
  gi = (avkSwClamp(g) * 255 + 32768) / 65536
  bi = (avkSwClamp(b) * 255 + 32768) / 65536
  ai = (avkSwClamp(a) * 255 + 32768) / 65536
  ProcedureReturn bi | (gi << 8) | (ri << 16) | (ai << 24)
EndProcedure

Procedure.i avkSwEdge(ax.i, ay.i, bx.i, by.i, px.i, py.i)
  ProcedureReturn (bx - ax) * (py - ay) - (by - ay) * (px - ax)
EndProcedure

Procedure.i avkSwEdgeInside(e.i, ax.i, ay.i, bx.i, by.i, sign.i)
  Define dx.i, dy.i
  If e > 0 : ProcedureReturn 1 : EndIf
  If e < 0 : ProcedureReturn 0 : EndIf
  dx = (bx - ax) * sign : dy = (by - ay) * sign
  ProcedureReturn Bool(dy < 0 Or (dy = 0 And dx > 0))
EndProcedure

Procedure.i avkSwSamplePixel(*sample.AnvilVkBackendSampledImage, x.i, y.i)
  If x < 0 : x = 0 : EndIf
  If y < 0 : y = 0 : EndIf
  If x >= *sample\width : x = *sample\width - 1 : EndIf
  If y >= *sample\height : y = *sample\height - 1 : EndIf
  If *sample\tiling = #VK_IMAGE_TILING_LINEAR
    ProcedureReturn PeekL(*sample\base + y * *sample\pitch + x * 4)
  EndIf
  ProcedureReturn PeekL(*sample\base + (y * *sample\width + x) * 4)
EndProcedure

Procedure.i avkSwBilerp(c00.i, c10.i, c01.i, c11.i, shift.i, fx.i, fy.i)
  Define upper.i, lower.i
  upper = (((c00 >> shift) & $FF) * (65536 - fx) + ((c10 >> shift) & $FF) * fx) / 65536
  lower = (((c01 >> shift) & $FF) * (65536 - fx) + ((c11 >> shift) & $FF) * fx) / 65536
  ProcedureReturn (upper * (65536 - fy) + lower * fy + 32768) / 65536
EndProcedure

Procedure.i avkSwSample(*sample.AnvilVkBackendSampledImage, u.i, v.i)
  Define x.i, y.i, tx.i, ty.i, fx.i, fy.i
  Define c00.i, c10.i, c01.i, c11.i
  If *sample = 0 Or *sample\base = 0 Or *sample\width < 1 Or *sample\height < 1 : ProcedureReturn 0 : EndIf
  u = avkSwClamp(u) : v = avkSwClamp(v)
  If *sample\magFilter = #VK_FILTER_NEAREST And *sample\minFilter = #VK_FILTER_NEAREST
    x = (u * *sample\width) / 65536 : y = (v * *sample\height) / 65536
    ProcedureReturn avkSwSamplePixel(*sample, x, y)
  EndIf
  tx = u * *sample\width - 32768 : ty = v * *sample\height - 32768
  If tx < 0 : tx = 0 : EndIf
  If ty < 0 : ty = 0 : EndIf
  If tx > (*sample\width - 1) * 65536 : tx = (*sample\width - 1) * 65536 : EndIf
  If ty > (*sample\height - 1) * 65536 : ty = (*sample\height - 1) * 65536 : EndIf
  x = tx / 65536 : y = ty / 65536
  fx = tx - x * 65536 : fy = ty - y * 65536
  c00 = avkSwSamplePixel(*sample, x, y)
  c10 = avkSwSamplePixel(*sample, x + 1, y)
  c01 = avkSwSamplePixel(*sample, x, y + 1)
  c11 = avkSwSamplePixel(*sample, x + 1, y + 1)
  ProcedureReturn avkSwBilerp(c00, c10, c01, c11, 0, fx, fy) | (avkSwBilerp(c00, c10, c01, c11, 8, fx, fy) << 8) | (avkSwBilerp(c00, c10, c01, c11, 16, fx, fy) << 16) | (avkSwBilerp(c00, c10, c01, c11, 24, fx, fy) << 24)
EndProcedure

Procedure.i avkSwMin(a.i, b.i)
  If a < b : ProcedureReturn a : EndIf
  ProcedureReturn b
EndProcedure

Procedure.i avkSwMax(a.i, b.i)
  If a > b : ProcedureReturn a : EndIf
  ProcedureReturn b
EndProcedure

Procedure avkSwTriangle(*d.AnvilVkBackendDraw, *a.AvkSwVertex, *b.AvkSwVertex, *c.AvkSwVertex)
  Define area.i, e0.i, e1.i, e2.i, px.i, py.i
  Define u.i, v.i, r.i, g.i, blue.i, alpha.i
  Define x0.i, x1.i, y0.i, y1.i, x.i, y.i, sign.i, word.i, dest.i
  Define sample.i, colourKind.i
  Define *tex.AnvilVkBackendSampledImage
  area = avkSwEdge(*a\x, *a\y, *b\x, *b\y, *c\x, *c\y)
  If area = 0
    ProcedureReturn
  EndIf
  sign = 1 : If area < 0 : sign = -1 : area = 0 - area : EndIf
  x0 = avkSwMin(*a\x, avkSwMin(*b\x, *c\x)) / 256
  y0 = avkSwMin(*a\y, avkSwMin(*b\y, *c\y)) / 256
  x1 = (avkSwMax(*a\x, avkSwMax(*b\x, *c\x)) + 255) / 256
  y1 = (avkSwMax(*a\y, avkSwMax(*b\y, *c\y)) + 255) / 256
  If x0 < 0 : x0 = 0 : EndIf
  If y0 < 0 : y0 = 0 : EndIf
  If x1 > *d\width : x1 = *d\width : EndIf
  If y1 > *d\height : y1 = *d\height : EndIf
  If *d\scissorX > x0 : x0 = *d\scissorX : EndIf
  If *d\scissorY > y0 : y0 = *d\scissorY : EndIf
  If *d\scissorX + *d\scissorW < x1 : x1 = *d\scissorX + *d\scissorW : EndIf
  If *d\scissorY + *d\scissorH < y1 : y1 = *d\scissorY + *d\scissorH : EndIf
  If x0 >= x1 Or y0 >= y1
    ProcedureReturn
  EndIf
  colourKind = AnvilVkPipelineColourSource(*d\pipeline)
  *tex = *d\sampledImage
  For y = y0 To y1 - 1
    py = y * 256 + 128
    For x = x0 To x1 - 1
      px = x * 256 + 128
      e0 = avkSwEdge(*b\x, *b\y, *c\x, *c\y, px, py) * sign
      e1 = avkSwEdge(*c\x, *c\y, *a\x, *a\y, px, py) * sign
      e2 = avkSwEdge(*a\x, *a\y, *b\x, *b\y, px, py) * sign
      If avkSwEdgeInside(e0, *b\x, *b\y, *c\x, *c\y, sign) = 0 Or avkSwEdgeInside(e1, *c\x, *c\y, *a\x, *a\y, sign) = 0 Or avkSwEdgeInside(e2, *a\x, *a\y, *b\x, *b\y, sign) = 0
        Continue
      EndIf
      r = 0 : g = 0 : blue = 0 : alpha = 0
      Select colourKind
        Case #ANVIL_SPV_COLOUR_PUSH
          r = avkSwFixed(PeekL(*d\pushBase)) : g = avkSwFixed(PeekL(*d\pushBase + 4))
          blue = avkSwFixed(PeekL(*d\pushBase + 8)) : alpha = avkSwFixed(PeekL(*d\pushBase + 12))
        Case #ANVIL_SPV_COLOUR_UNIFORM
          r = avkSwFixed(PeekL(*d\uniformBase)) : g = avkSwFixed(PeekL(*d\uniformBase + 4))
          blue = avkSwFixed(PeekL(*d\uniformBase + 8)) : alpha = avkSwFixed(PeekL(*d\uniformBase + 12))
        Case #ANVIL_SPV_COLOUR_CONST
          r = avkSwFixed(AnvilVkPipelineColourConstant(*d\pipeline, 0))
          g = avkSwFixed(AnvilVkPipelineColourConstant(*d\pipeline, 1))
          blue = avkSwFixed(AnvilVkPipelineColourConstant(*d\pipeline, 2))
          alpha = avkSwFixed(AnvilVkPipelineColourConstant(*d\pipeline, 3))
        Case #ANVIL_SPV_COLOUR_VARYING
          r = (*a\r * e0 + *b\r * e1 + *c\r * e2) / area
          g = (*a\g * e0 + *b\g * e1 + *c\g * e2) / area
          blue = (*a\b * e0 + *b\b * e1 + *c\b * e2) / area
          alpha = (*a\a * e0 + *b\a * e1 + *c\a * e2) / area
        Case #ANVIL_SPV_COLOUR_SAMPLED
          u = (*a\u * e0 + *b\u * e1 + *c\u * e2) / area
          v = (*a\v * e0 + *b\v * e1 + *c\v * e2) / area
          sample = avkSwSample(*tex, u, v)
          r = ((sample >> 16) & $FF) * 65536 / 255
          g = ((sample >> 8) & $FF) * 65536 / 255
          blue = (sample & $FF) * 65536 / 255
          alpha = ((sample >> 24) & $FF) * 65536 / 255
          If AnvilVkPipelineUsesPushConstants(*d\pipeline) <> 0 And *d\pushBase <> 0
            r = r * avkSwFixed(PeekL(*d\pushBase)) / 65536
            g = g * avkSwFixed(PeekL(*d\pushBase + 4)) / 65536
            blue = blue * avkSwFixed(PeekL(*d\pushBase + 8)) / 65536
            alpha = alpha * avkSwFixed(PeekL(*d\pushBase + 12)) / 65536
          EndIf
          If AnvilVkPipelineUsesUniformBuffer(*d\pipeline) <> 0 And *d\uniformBase <> 0
            r = r + avkSwFixed(PeekL(*d\uniformBase))
            g = g + avkSwFixed(PeekL(*d\uniformBase + 4))
            blue = blue + avkSwFixed(PeekL(*d\uniformBase + 8))
            alpha = alpha + avkSwFixed(PeekL(*d\uniformBase + 12))
          EndIf
      EndSelect
      dest = *d\targetBase + y * *d\pitch + x * 4
      If *d\blendMode = #ANVIL_VK_BLEND_SRC_OVER
        word = PeekL(dest)
        alpha = avkSwClamp(alpha)
        r = (r * alpha + ((word >> 16) & $FF) * 257 * (65536 - alpha)) / 65536
        g = (g * alpha + ((word >> 8) & $FF) * 257 * (65536 - alpha)) / 65536
        blue = (blue * alpha + (word & $FF) * 257 * (65536 - alpha)) / 65536
        alpha = alpha + ((word >> 24) & $FF) * 257 * (65536 - alpha) / 65536
      EndIf
      PokeL(dest, avkSwPack(r, g, blue, alpha))
    Next
  Next
EndProcedure
Procedure avkSwClearRect(*d.AnvilVkBackendDraw)
  Define x0.i, y0.i, x1.i, y1.i, x.i, y.i
  x0 = avkSwMax(0, *d\clearRectX) : y0 = avkSwMax(0, *d\clearRectY)
  x1 = avkSwMin(*d\width, *d\clearRectX + *d\clearRectW)
  y1 = avkSwMin(*d\height, *d\clearRectY + *d\clearRectH)
  If x1 <= x0 Or y1 <= y0
    ProcedureReturn
  EndIf
  For y = y0 To y1 - 1
    For x = x0 To x1 - 1
      PokeL(*d\targetBase + y * *d\pitch + x * 4, *d\clearRectBgra)
    Next
  Next
EndProcedure

Procedure.i avkBackendSubmitDraw(*payload)
  Define *list.AnvilVkBackendDrawList
  Define *d.AnvilVkBackendDraw
  Define *first.AnvilVkBackendDraw
  Define *binding.AnvilVkBackendBinding
  Define n.i, tri.i, count.i, topology.i, bindIndex.i, needed.i, attr.i, attrEnd.i
  Define a.AvkSwVertex, b.AvkSwVertex, c.AvkSwVertex
  If *payload = 0 : ProcedureReturn -1 : EndIf
  *list = *payload
  If *list\drawCount < 1 Or *list\drawCount > #ANVIL_VK_MAX_RECORDED_DRAWS Or *list\draws = 0 : ProcedureReturn -1 : EndIf
  *first = *list\draws
  If avkBackendDrawSupported(*first\targetBase, *first\targetBytes, *first\width, *first\height, *first\pitch) <> #VK_SUCCESS : ProcedureReturn -1 : EndIf
  ; Complete transaction preflight precedes the first target write.
  For n = 0 To *list\drawCount - 1
    *d = *list\draws + n * SizeOf(AnvilVkBackendDraw)
    If *d\targetBase <> *first\targetBase Or *d\targetBytes <> *first\targetBytes Or *d\width <> *first\width Or *d\height <> *first\height Or *d\pitch <> *first\pitch
      ProcedureReturn -1
    EndIf
    If *d\kind = #ANVIL_VK_RENDER_OP_DRAW
      If *d\pipeline < 1 Or *d\pipeline > #ANVIL_VK_MAX_PIPELINES Or *d\bindings = 0 Or *d\bindingCount < 1 : ProcedureReturn -1 : EndIf
      ; Reject unsupported instance fetch before clearing the target. A
      ; multi-draw submission must not leave a partially updated image.
      If *d\instanceCount <> 1 Or *d\firstInstance <> 0 : ProcedureReturn -1 : EndIf
      topology = AnvilVkPipelineTopology(*d\pipeline)
      If topology <> #VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST And topology <> #VK_PRIMITIVE_TOPOLOGY_TRIANGLE_STRIP : ProcedureReturn -1 : EndIf
      If *d\vertexCount < 3 Or *d\maxVertex < 0 : ProcedureReturn -1 : EndIf
      For bindIndex = 0 To *d\bindingCount - 1
        If AnvilVkPipelineBindingRate(*d\pipeline, bindIndex) <> #VK_VERTEX_INPUT_RATE_VERTEX : ProcedureReturn -1 : EndIf
        *binding = *d\bindings + bindIndex * SizeOf(AnvilVkBackendBinding)
        If *binding\stride < 4 Or *d\maxVertex > (#AVK_SW_HEAP_BYTES / *binding\stride)
          ProcedureReturn -1
        EndIf
        attrEnd = 0
        For attr = 0 To AnvilVkPipelineAttrCount(*d\pipeline) - 1
          If AnvilVkPipelineAttrBinding(*d\pipeline, attr) = bindIndex
            needed = AnvilVkPipelineAttrOffset(*d\pipeline, attr) + AnvilVkPipelineAttrComponents(*d\pipeline, attr) * 4
            If needed > attrEnd : attrEnd = needed : EndIf
          EndIf
        Next
        If attrEnd < 1 Or attrEnd > *binding\stride : ProcedureReturn -1 : EndIf
        needed = *d\maxVertex * *binding\stride + attrEnd
        If avkSwRange(*binding\base, needed) = 0 : ProcedureReturn -1 : EndIf
      Next
      If *d\indexBase <> 0
        If avkSwRange(*d\indexBase, *d\indexBytes) = 0 : ProcedureReturn -1 : EndIf
      EndIf
      If AnvilVkPipelineColourSource(*d\pipeline) = #ANVIL_SPV_COLOUR_SAMPLED And *d\sampledImage = 0 : ProcedureReturn -1 : EndIf
    ElseIf *d\kind <> #ANVIL_VK_RENDER_OP_CLEAR_RECT
      ProcedureReturn -1
    EndIf
  Next
  If avkBackendSubmitClear(*first\targetBase, *first\targetBytes, *first\width, *first\height, *first\pitch, *first\clearBgra) <> #ANVIL_VK_JOB_DONE : ProcedureReturn -1 : EndIf
  For n = 0 To *list\drawCount - 1
    *d = *list\draws + n * SizeOf(AnvilVkBackendDraw)
    If *d\kind = #ANVIL_VK_RENDER_OP_CLEAR_RECT
      avkSwClearRect(*d)
      Continue
    EndIf
    If *d\sampleMask = 0 : Continue : EndIf
    topology = AnvilVkPipelineTopology(*d\pipeline)
    If topology = #VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST
      count = *d\vertexCount / 3
      For tri = 0 To count - 1
        avkSwVertex(*d, tri * 3, @a) : avkSwVertex(*d, tri * 3 + 1, @b) : avkSwVertex(*d, tri * 3 + 2, @c)
        avkSwTriangle(*d, @a, @b, @c)
      Next
    Else
      count = *d\vertexCount - 2
      For tri = 0 To count - 1
        If (tri & 1) = 0
          avkSwVertex(*d, tri, @a) : avkSwVertex(*d, tri + 1, @b)
        Else
          avkSwVertex(*d, tri + 1, @a) : avkSwVertex(*d, tri, @b)
        EndIf
        avkSwVertex(*d, tri + 2, @c)
        avkSwTriangle(*d, @a, @b, @c)
      Next
    EndIf
    avkSwDraws = avkSwDraws + 1
  Next
  ProcedureReturn #ANVIL_VK_JOB_DONE
EndProcedure

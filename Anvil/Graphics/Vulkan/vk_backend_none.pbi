; ======================================================================
;  The absent graphics backend
; ======================================================================
; SPDX-License-Identifier: MIT
;
; This is what a target with no GPU driver links. It enumerates no
; physical device, so vkCreateInstance returns VK_ERROR_INCOMPATIBLE_
; DRIVER and nothing downstream can be reached at all. It exists so that
; "no device here" is a linked, tested answer rather than the absence of
; a file, and so the UNO Q and a Pi build without V3D compile the whole
; portable surface and then honestly report nothing.
;
; Every procedure below answers with the emptiest true value. None of
; them can be called through the public API, because no VkDevice can
; exist to reach them - but they answer safely if a diagnostic asks.

XIncludeFile "Anvil/Graphics/Vulkan/vk_foundation.pbi"

Procedure.i avkBackendCaps()
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendName()
  ProcedureReturn "no graphics backend is linked into this build, so this target enumerates no Vulkan physical device"
EndProcedure

Procedure.i avkBackendPrepare()
  ProcedureReturn #VK_ERROR_INCOMPATIBLE_DRIVER
EndProcedure

Procedure.i avkBackendHeapBase()
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendHeapBytes()
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendMemoryTypeCount()
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendMemoryTypeFlags(index.i)
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendMemoryTypeHeap(index.i)
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendHeapCount()
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendHeapSizeOf(index.i)
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendHeapFlagsOf(index.i)
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendImageAlignment()
  ProcedureReturn 4096
EndProcedure

Procedure.i avkBackendImageCopySourceAlignment()
  ProcedureReturn 1
EndProcedure

Procedure.i avkBackendRowPitchFor(width.i)
  ProcedureReturn width * 4
EndProcedure

Procedure.i avkBackendMaxImageDimension2D()
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendSampledMaxDimension2D(tiling.i)
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendImagePlan(width.i, height.i, format.i, tiling.i, usage.i, *plan.AnvilVkBackendImagePlan)
  If *plan <> 0
    *plan\bytes = 0 : *plan\alignment = 0 : *plan\rowPitch = 0
    *plan\backendLayout = 0 : *plan\paddedWidth = 0 : *plan\paddedHeight = 0
  EndIf
  ProcedureReturn #VK_ERROR_FORMAT_NOT_SUPPORTED
EndProcedure

Procedure.i avkBackendSubmitImageCopy(*copy.AnvilVkBackendImageCopy)
  ProcedureReturn -1
EndProcedure

Procedure.i avkBackendSubmitBufferCopy(source.i, destination.i, bytes.i)
  ProcedureReturn -1
EndProcedure

Procedure.i avkBackendClearSupported(base.i, bytes.i, w.i, h.i, pitch.i)
  ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT
EndProcedure

Procedure.i avkBackendSubmitClear(base.i, bytes.i, w.i, h.i, pitch.i, bgra.i)
  ProcedureReturn #VK_ERROR_DEVICE_LOST
EndProcedure

Procedure.i avkBackendPoll()
  ProcedureReturn 1
EndProcedure

Procedure.i avkBackendLastNativeError()
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendTicksUs()
  ProcedureReturn 0
EndProcedure

; The graphics half of the seam. There is no device here, so there is no
; pipeline either, and each of the four says so rather than being absent.
Procedure.i avkBackendPipelineBytes()
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendPipelineBuild(*build.AnvilVkBackendPipelineBuildInfo)
  ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT
EndProcedure

Procedure avkBackendPipelineRelease(pipe.i)
EndProcedure

Procedure.i avkBackendDrawSupported(base.i, bytes.i, w.i, h.i, pitch.i)
  ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT
EndProcedure

Procedure.i avkBackendSubmitDraw(*d.AnvilVkBackendDraw)
  ProcedureReturn -1
EndProcedure

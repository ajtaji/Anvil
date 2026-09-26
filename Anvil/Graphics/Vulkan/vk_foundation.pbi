; ======================================================================
;  Native Vulkan object/lifecycle foundation for Anvil
; ======================================================================
; SPDX-License-Identifier: MIT
;
; This is the executable ownership and command-buffer state engine beneath
; Anvil's public vk* entry points (vk_api.pbi). It owns handles, parents,
; generations and command-buffer states, and it contains no V3D register,
; packet, address or display assumption of any kind.
;
; THE BACKEND IS A SEAM AND IT IS STATIC. Exactly one backend file must be
; included by the program:
;
;   Anvil/Graphics/Vulkan/vk_backend_none.pbi   no device is enumerated
;   Anvil/Graphics/Vulkan/vk_backend_test.pbi   state only, owns no GPU
;   Anvil/Graphics/Vulkan/vk_v3d_backend.pi4    the real Pi 4 V3D backend
;
; The seam is Declared here and defined there, so a build that forgets a
; backend fails to link rather than quietly enumerating nothing. Including
; two backends declares the same procedures twice and fails as well: there
; is no run-time registration to get wrong.
;
; Semantics come from the Vulkan specification, read at
; https://docs.vulkan.org/spec/latest/chapters/fundamentals.html (object
; model, valid usage, return codes) and .../cmdbuffers.html (the command
; buffer lifecycle). Nothing is copied from any implementation.

XIncludeFile "Anvil/Graphics/Vulkan/vk_core_1_0.pbi"

; ----------------------------------------------------------------------
;  Anvil result codes.
;
;  Core Vulkan leaves most invalid usage UNDEFINED and gives a command no
;  result code for it. Anvil will not have undefined behaviour, so every
;  such case returns one of these instead. They are far outside VkResult's
;  core-1.0 range (-12 .. 5), so no caller can confuse one with a Vulkan
;  code and none of them can ever be mistaken for success.
; ----------------------------------------------------------------------
#ANVIL_VK_OK = 0
#ANVIL_VK_ERR_ARGS = -20001
#ANVIL_VK_ERR_HANDLE = -20002
#ANVIL_VK_ERR_OWNER = -20003
#ANVIL_VK_ERR_STATE = -20004
#ANVIL_VK_ERR_UNSUPPORTED = -20005

; Backend capability bits, reported by avkBackendCaps().
#ANVIL_VK_CAP_DEVICE = $0001        ; a physical device may be enumerated
#ANVIL_VK_CAP_CLEAR_COLOR = $0002   ; vkCmdClearColorImage can be executed
#ANVIL_VK_CAP_GPU = $0004           ; that execution is real GPU work

; avkBackendSubmitClear() answers.
#ANVIL_VK_JOB_DONE = 0
#ANVIL_VK_JOB_PENDING = 1

#ANVIL_VK_TYPE_INSTANCE = 1
#ANVIL_VK_TYPE_PHYSICAL_DEVICE = 2
#ANVIL_VK_TYPE_DEVICE = 3
#ANVIL_VK_TYPE_QUEUE = 4
#ANVIL_VK_TYPE_COMMAND_POOL = 5
#ANVIL_VK_TYPE_COMMAND_BUFFER = 6
#ANVIL_VK_TYPE_DEVICE_MEMORY = 7
#ANVIL_VK_TYPE_IMAGE = 8
#ANVIL_VK_TYPE_FENCE = 9
#ANVIL_VK_TYPE_BUFFER = 10
#ANVIL_VK_TYPE_SHADER_MODULE = 11
#ANVIL_VK_TYPE_PIPELINE_LAYOUT = 12
#ANVIL_VK_TYPE_RENDER_PASS = 13
#ANVIL_VK_TYPE_IMAGE_VIEW = 14
#ANVIL_VK_TYPE_FRAMEBUFFER = 15
#ANVIL_VK_TYPE_PIPELINE = 16
#ANVIL_VK_TYPE_DESCRIPTOR_SET_LAYOUT = 17
#ANVIL_VK_TYPE_DESCRIPTOR_POOL = 18
#ANVIL_VK_TYPE_DESCRIPTOR_SET = 19
#ANVIL_VK_TYPE_SAMPLER = 20
#ANVIL_VK_TYPE_EVENT = 21

#ANVIL_VK_CB_INITIAL = 0
#ANVIL_VK_CB_RECORDING = 1
#ANVIL_VK_CB_EXECUTABLE = 2
#ANVIL_VK_CB_PENDING = 3
#ANVIL_VK_CB_INVALID = 4

#ANVIL_VK_MAX_INSTANCES = 4
#ANVIL_VK_MAX_PHYSICAL_DEVICES = 4
#ANVIL_VK_MAX_DEVICES = 4
#ANVIL_VK_MAX_QUEUES = 4
#ANVIL_VK_MAX_COMMAND_POOLS = 16
#ANVIL_VK_MAX_COMMAND_BUFFERS = 32
#ANVIL_VK_MAX_EVENTS = 16

; HOW MANY VERTEX INPUT BINDINGS one pipeline may describe, and therefore
; how many vertex buffers one draw may read. It lives here rather than in
; vk_pipeline.pbi because the command layer sizes its per-binding bind
; state by it and must not include the pipeline layer to learn it.
;
; FOUR, because the front end accepts at most four Location inputs and a
; binding nothing reads is refused: there can be no fifth binding for a
; fifth attribute that cannot exist.
#ANVIL_VK_MAX_BINDINGS = 4

; THE DESCRIPTOR FAMILY. One set layout of at most two bindings, one
; pool, and the sets allocated from it. These live here for the same
; reason #ANVIL_VK_MAX_BINDINGS does: the command layer holds the bound
; set and the draw record carries what it resolved to, and neither may
; include the descriptor layer to learn the shape.
#ANVIL_VK_MAX_SET_LAYOUTS = 4
#ANVIL_VK_MAX_DESCRIPTOR_POOLS = 2
#ANVIL_VK_MAX_DESCRIPTOR_SETS = 4
#ANVIL_VK_MAX_SET_BINDINGS = 2
#ANVIL_VK_MAX_SAMPLERS = 8

; The block a uniform-buffer descriptor supplies: one four-component
; colour, the same sixteen bytes the push-constant path carries, so the
; two are interchangeable at the fragment output and the picture is the
; only thing that tells them apart.
#ANVIL_VK_UNIFORM_BYTES = 16

; The alignment vkUpdateDescriptorSets requires of a uniform buffer's
; offset. It is reported as minUniformBufferOffsetAlignment and it is
; sixteen here because that is the size of the block and the natural
; alignment of a four-component binary32 vector.
#ANVIL_VK_UNIFORM_ALIGN = 16

; The one queue family this slice exposes. It is always transfer-capable.
; vkGetPhysicalDeviceQueueFamilyProperties adds VK_QUEUE_GRAPHICS_BIT
; only when the linked backend owns #ANVIL_VK_CAP_DRAW. Compute remains
; absent until a backend can actually execute dispatches.
#ANVIL_VK_QUEUE_FAMILY = 0

#ANVIL_VK_TOKEN_MAGIC = $564B000000000000
#ANVIL_VK_TOKEN_MAGIC_MASK = $FFFF000000000000
#ANVIL_VK_TOKEN_TYPE_MASK = $0000FF0000000000
#ANVIL_VK_TOKEN_GEN_MASK = $00000000FFFF0000
#ANVIL_VK_TOKEN_SLOT_MASK = $000000000000FFFF

; The capability bit a backend sets when it can execute a graphics
; pipeline: a vertex fetch, a rasterised primitive and a fragment shader.
; It is separate from CLEAR_COLOR because a backend that clears is not
; thereby a backend that draws, and the first one written could do one
; and not the other for a whole evening.
#ANVIL_VK_CAP_DRAW = $0008
; The backend can execute the one blend equation this bounded Vulkan slice
; accepts: straight source-over on colour and alpha. It is separate from DRAW
; so format-property reporting never promises blending for a backend that only
; knows how to replace a colour attachment.
#ANVIL_VK_CAP_BLEND_SRC_OVER = $0010
; The backend accepts one closed array of draws as one submission transaction.
; A backend without this bit still consumes the original single-draw record;
; portable submission refuses a list longer than one before claiming a fence,
; semaphore, lifetime counter or backend job.
#ANVIL_VK_CAP_DRAW_LIST = $0020

; Target-neutral closed-draw blend semantics. A backend maps these values to
; its own packet vocabulary; V3D blend-factor numbers never cross this seam.
#ANVIL_VK_BLEND_DISABLED = 0
#ANVIL_VK_BLEND_SRC_OVER = 1

; ----------------------------------------------------------------------
;  ONE CLOSED DRAW, handed to the backend.
;
;  The portable layer validates everything in this record and the backend
;  executes it or reports a device loss. It is a record and not thirteen
;  arguments because a gate compares its bytes against an expectation
;  built independently, and because the AArch64 calling convention has
;  eight argument registers.
; ----------------------------------------------------------------------
;  ONE VERTEX BUFFER PER BINDING, and that is not a generalisation for
;  its own sake. Position in one buffer and colour in another, at
;  different strides, is what an application that streams one attribute
;  and keeps the other static actually does, and it is the layout a
;  single base address cannot express. The attribute records V3D reads
;  carry an address and a stride EACH, so the hardware never wanted one
;  base; the single `vertexBase` this replaces was the portable layer's
;  limit.
;
;  A COUNT AND A POINTER TO AN ARRAY OF RECORDS, which is the shape every
;  Vulkan create-info already uses for a list. The array is storage the
;  portable layer owns and keeps alive across the submission, exactly as
;  `pushBase` points at a staged copy of the push-constant block rather
;  than at a caller's frame.
Structure AnvilVkBackendBinding Align #PB_Structure_AlignC
  ; The exact byte interval read by one draw is
  ;   [base + firstVertex*stride, base + (firstVertex+vertexCount)*stride).
  ; Keeping the bind base and draw range separate preserves the hardware's
  ; firstVertex semantics while still giving a list backend all information
  ; needed to merge exact cache spans.
  base.i              ; the bound buffer's first byte, plus its bind offset
  stride.i            ; that binding's own stride, in bytes
EndStructure

; ONE CLOSED SAMPLED IMAGE. The descriptor layer resolves Vulkan handles
; into this target-neutral record at the point a backend is about to consume
; them. No backend is allowed to retain an application handle or infer a
; missing image property from a global table later.
Structure AnvilVkBackendSampledImage Align #PB_Structure_AlignC
  base.i
  bytes.i
  width.i
  height.i
  pitch.i
  format.i
  layout.i
  magFilter.i
  minFilter.i
  tiling.i
  backendLayout.i
  paddedWidth.i
  paddedHeight.i
EndStructure

; Closed resource plan returned by the backend that owns the physical image
; layout. Portable Vulkan code retains the values but never interprets the
; opaque layout tag. A linear image has a real rowPitch; an optimal image has
; rowPitch zero because Vulkan exposes no linear row layout for it.
Structure AnvilVkBackendImagePlan Align #PB_Structure_AlignC
  bytes.i
  alignment.i
  rowPitch.i
  backendLayout.i
  paddedWidth.i
  paddedHeight.i
EndStructure

; One already-validated whole-image transfer. No Vulkan handles cross the
; backend boundary: the portable layer resolves them again at submission and
; retains both resources until this operation has completed or failed.
Structure AnvilVkBackendImageCopy Align #PB_Structure_AlignC
  windowBase.i
  windowBytes.i
  sourceBase.i
  sourceBytes.i
  sourcePitch.i
  destinationBase.i
  destinationBytes.i
  width.i
  height.i
  destinationLayout.i
  paddedWidth.i
  paddedHeight.i
  timeoutUs.i
EndStructure

Structure AnvilVkBackendDraw Align #PB_Structure_AlignC
  pipeline.i          ; the backend's own pipeline slot
  targetBase.i        ; the colour attachment's first byte
  targetBytes.i
  width.i
  height.i
  pitch.i
  clearBgra.i         ; the render pass's clear value, already packed
  bindingCount.i      ; how many AnvilVkBackendBinding records follow
  bindings.i          ; the address of the first of them
  vertexCount.i
  firstVertex.i
  ; Zero indexBase is a non-indexed draw. Otherwise it names the first byte
  ; of the bound index-buffer range, indexBytes bounds that range, firstVertex
  ; is firstIndex, and maxVertex is the largest uint16/uint32 index observed
  ; during whole-list preflight. The backend independently checks that value
  ; before using it to bound vertex fetch.
  indexBase.i
  indexBytes.i
  indexType.i
  maxVertex.i
  sampleMask.i        ; bit zero is the one rasterisation sample's coverage
  blendMode.i         ; #ANVIL_VK_BLEND_*, already validated and normalized
  ; One origin-zero, positive whole-pixel viewport captured for this draw.
  ; The V3D backend currently requires it to equal the live target geometry.
  viewportX.i
  viewportY.i
  viewportW.i
  viewportH.i
  ; The exact scissor captured for this draw. Offsets remain signed and
  ; extents remain the registry's uint32 values until the target-owning
  ; backend intersects them with the live framebuffer without overflow.
  scissorX.i
  scissorY.i
  scissorW.i
  scissorH.i
  pushBase.i          ; the push-constant block, or 0
  pushBytes.i
  ; THE UNIFORM BUFFER THE BOUND DESCRIPTOR SET RESOLVED TO, already
  ; validated: live, bound, big enough, and named by a set layout that
  ; matches what the fragment shader asked for. Zero when the pipeline's
  ; colour does not come from a descriptor.
  uniformBase.i
  uniformBytes.i
  ; One sampled image, resolved from the bound descriptor at submit time.
  ; The pointer names staging owned by the portable pipeline layer and remains
  ; valid until the submission completes. Zero when the shader has no texture.
  sampledImage.i
EndStructure

; One already-closed ordered draw list. `draws` points to `drawCount`
; contiguous AnvilVkBackendDraw records whose nested pointers all remain live
; until the one outstanding submission completes. A list-capable backend must
; accept or reject the complete list before executing its first element. It
; must merge overlapping/adjacent exact binding intervals across the list and
; only then apply target cache-line rounding; repeatedly cleaning from each
; binding base through its largest vertex is an O(N^2) prefix walk. Likewise,
; pipeline cache work consumes the target's exact live record/template and
; dynamic CS/VS-uniform spans, never an unconditional fixed pipeline prefix.
Structure AnvilVkBackendDrawList Align #PB_Structure_AlignC
  drawCount.i
  draws.i
EndStructure

; One closed, synchronous pipeline-build transaction. Both IR pointers name
; live VkShaderModules only for the duration of avkBackendPipelineBuild; a
; successful backend must retain executable bytes and exact patch metadata,
; never either pointer. The portable layer validates both module slots and IR
; generations immediately before this synchronous call; the backend therefore
; receives no unverifiable lifetime token of its own.
Structure AnvilVkBackendPipelineBuildInfo Align #PB_Structure_AlignC
  pipeline.i
  dynamicViewport.i   ; nonzero when CS/VS viewport uniforms are per draw
  base.i
  bytes.i
  vertexIr.i
  fragmentIr.i
EndStructure

; ----------------------------------------------------------------------
;  THE BACKEND SEAM.
; ----------------------------------------------------------------------
Declare.i avkBackendCaps()
Declare.i avkBackendName()
Declare.i avkBackendPrepare()
Declare.i avkBackendHeapBase()
Declare.i avkBackendHeapBytes()
Declare.i avkBackendMemoryTypeCount()
Declare.i avkBackendMemoryTypeFlags(index.i)
Declare.i avkBackendMemoryTypeHeap(index.i)
Declare.i avkBackendHeapCount()
Declare.i avkBackendHeapSizeOf(index.i)
Declare.i avkBackendHeapFlagsOf(index.i)
Declare.i avkBackendImageAlignment()
Declare.i avkBackendImageCopySourceAlignment()
Declare.i avkBackendRowPitchFor(width.i)
Declare.i avkBackendMaxImageDimension2D()
; Largest dimension this backend can truthfully consume through an actual
; sampled-image instruction. Zero means no sampling path is implemented.
Declare.i avkBackendSampledMaxDimension2D(tiling.i)
Declare.i avkBackendImagePlan(width.i, height.i, format.i, tiling.i, usage.i, *plan.AnvilVkBackendImagePlan)
Declare.i avkBackendSubmitImageCopy(*copy.AnvilVkBackendImageCopy)
Declare.i avkBackendClearSupported(base.i, bytes.i, w.i, h.i, pitch.i)
Declare.i avkBackendSubmitClear(base.i, bytes.i, w.i, h.i, pitch.i, bgra.i)
Declare.i avkBackendPoll()
Declare.i avkBackendLastNativeError()
Declare.i avkBackendTicksUs()

; The graphics half of the seam. A backend with no #ANVIL_VK_CAP_DRAW bit
; still defines all four: they answer "not on this backend" rather than
; being absent, so a build that reaches one links and refuses instead of
; failing to resolve a symbol at the worst possible moment.
Declare.i avkBackendPipelineBytes()
Declare.i avkBackendPipelineBuild(*build.AnvilVkBackendPipelineBuildInfo)
Declare avkBackendPipelineRelease(pipe.i)
Declare.i avkBackendDrawSupported(base.i, bytes.i, w.i, h.i, pitch.i)
; The payload is AnvilVkBackendDraw on the legacy single-draw capability and
; AnvilVkBackendDrawList when #ANVIL_VK_CAP_DRAW_LIST is advertised.
Declare.i avkBackendSubmitDraw(*payload)

; EVERY SLOT TABLE IS ONE ELEMENT LONGER THAN ITS MAXIMUM. Slot 0 means
; "no object", so live slots run 1..MAX and a table dimensioned to MAX
; would have its last slot land one element past the end. That is exactly
; what the first version of this file did, on every object type at once,
; and it is invisible until the table is full - the allocator only ever
; reaches the last slot when everything before it is taken.
Global Dim avkInstLive.a[#ANVIL_VK_MAX_INSTANCES + 1]
Global Dim avkInstGen.i[#ANVIL_VK_MAX_INSTANCES + 1]
Global Dim avkPhysLive.a[#ANVIL_VK_MAX_PHYSICAL_DEVICES + 1]
Global Dim avkPhysGen.i[#ANVIL_VK_MAX_PHYSICAL_DEVICES + 1]
Global Dim avkPhysInst.i[#ANVIL_VK_MAX_PHYSICAL_DEVICES + 1]
Global Dim avkDevLive.a[#ANVIL_VK_MAX_DEVICES + 1]
Global Dim avkDevGen.i[#ANVIL_VK_MAX_DEVICES + 1]
Global Dim avkDevPhys.i[#ANVIL_VK_MAX_DEVICES + 1]
Global Dim avkQueueLive.a[#ANVIL_VK_MAX_QUEUES + 1]
Global Dim avkQueueGen.i[#ANVIL_VK_MAX_QUEUES + 1]
Global Dim avkQueueDev.i[#ANVIL_VK_MAX_QUEUES + 1]
Global Dim avkPoolLive.a[#ANVIL_VK_MAX_COMMAND_POOLS + 1]
Global Dim avkPoolGen.i[#ANVIL_VK_MAX_COMMAND_POOLS + 1]
Global Dim avkPoolDev.i[#ANVIL_VK_MAX_COMMAND_POOLS + 1]
Global Dim avkPoolFlags.i[#ANVIL_VK_MAX_COMMAND_POOLS + 1]
Global Dim avkCmdLive.a[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCmdGen.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCmdPool.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCmdLevel.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCmdState.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCmdBeginFlags.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCmdOps.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkEventLive.a[#ANVIL_VK_MAX_EVENTS + 1]
Global Dim avkEventGen.i[#ANVIL_VK_MAX_EVENTS + 1]
Global Dim avkEventDev.i[#ANVIL_VK_MAX_EVENTS + 1]
Global Dim avkEventSet.a[#ANVIL_VK_MAX_EVENTS + 1]

; ----------------------------------------------------------------------
;  THE VALIDATION FAULT RECORD.
;
;  Vulkan's void commands - vkCmdPipelineBarrier, vkCmdClearColorImage,
;  vkFreeMemory, vkDestroyImage, vkDestroyFence - have no return value,
;  and the specification's answer to misuse is undefined behaviour. Anvil
;  records a numeric code and a WHOLE SENTENCE here instead, and where the
;  specification allows it (a recording error) the command buffer is moved
;  to the invalid state so vkEndCommandBuffer reports the failure. Nothing
;  in this engine ever proceeds as though a refused call had succeeded.
; ----------------------------------------------------------------------
Global avkFaultCode.i = #ANVIL_VK_OK
Global avkFaultText.i = 0
Global avkFaultCount.i = 0

Procedure.i avkFault(code.i, text.i)
  avkFaultCode = code
  avkFaultText = text
  avkFaultCount = avkFaultCount + 1
  ProcedureReturn code
EndProcedure

Procedure AnvilVkFaultClear()
  avkFaultCode = #ANVIL_VK_OK
  avkFaultText = 0
EndProcedure

Procedure.i AnvilVkFaultCode()
  ProcedureReturn avkFaultCode
EndProcedure

; A whole sentence naming the numeric code, what it means and the first
; thing to check, or 0 if no call has been refused.
Procedure.i AnvilVkFaultText()
  ProcedureReturn avkFaultText
EndProcedure

Procedure.i AnvilVkFaultCount()
  ProcedureReturn avkFaultCount
EndProcedure

Procedure.i avkNextGen(v.i)
  v = (v + 1) & $FFFF
  If v = 0 : v = 1 : EndIf
  ProcedureReturn v
EndProcedure

Procedure.i avkToken(kind.i, slot.i, gen.i)
  ProcedureReturn #ANVIL_VK_TOKEN_MAGIC | ((kind & $FF) << 40) | ((gen & $FFFF) << 16) | (slot & $FFFF)
EndProcedure

Procedure.i avkTokenKind(h.i)
  ProcedureReturn (h >> 40) & $FF
EndProcedure

Procedure.i avkTokenSlot(h.i)
  ProcedureReturn h & $FFFF
EndProcedure

Procedure.i avkTokenGen(h.i)
  ProcedureReturn (h >> 16) & $FFFF
EndProcedure

Procedure.i avkTokenShape(h.i, kind.i, cap.i)
  Define s.i
  If (h & #ANVIL_VK_TOKEN_MAGIC_MASK) <> #ANVIL_VK_TOKEN_MAGIC
    ProcedureReturn 0
  EndIf
  If avkTokenKind(h) <> kind
    ProcedureReturn 0
  EndIf
  s = avkTokenSlot(h)
  If s < 1 Or s > cap
    ProcedureReturn 0
  EndIf
  ProcedureReturn s
EndProcedure

; Read a uint32_t member without the sign of PeekL's signed 32-bit load
; leaking into a 64-bit comparison. VK_QUEUE_FAMILY_IGNORED is $FFFFFFFF
; and must compare equal to the constant of the same name.
Procedure.i avkU32(*p)
  ProcedureReturn PeekL(*p) & $FFFFFFFF
EndProcedure

; A binary32 bit pattern as a whole number, or -1 when it is not one.
;
; VkViewport's four fields are floats and this slice renders at whole
; pixel viewports, so a viewport of 799.5 has to be refused rather than
; rounded - the emitted coordinate shader would scale by a number the
; caller did not ask for and the triangle would land half a pixel out.
; Done on the BIT PATTERN for the same reason avkUnorm8FromF32Bits is:
; the portable layer must not need a live floating-point unit.
Procedure.i avkIntFromF32Bits(bits.i)
  Define exp.i
  Define man.i
  Define e.i
  Define shift.i
  bits = bits & $FFFFFFFF
  If bits = 0 : ProcedureReturn 0 : EndIf
  If (bits >> 31) <> 0 : ProcedureReturn -1 : EndIf
  exp = (bits >> 23) & $FF
  man = bits & $7FFFFF
  If exp = 0 : ProcedureReturn -1 : EndIf                 ; subnormal
  If exp = $FF : ProcedureReturn -1 : EndIf               ; infinity or NaN
  e = exp - 127
  If e < 0 : ProcedureReturn -1 : EndIf                   ; below one
  If e > 15 : ProcedureReturn -1 : EndIf                  ; above 65535
  man = $800000 | man
  shift = 23 - e
  If (man & ((1 << shift) - 1)) <> 0 : ProcedureReturn -1 : EndIf
  ProcedureReturn man >> shift
EndProcedure

Procedure.i avkInstSlot(h.i)
  Define s.i
  s = avkTokenShape(h, #ANVIL_VK_TYPE_INSTANCE, #ANVIL_VK_MAX_INSTANCES)
  If s = 0 Or avkInstLive[s] = 0 Or avkInstGen[s] <> avkTokenGen(h) : ProcedureReturn 0 : EndIf
  ProcedureReturn s
EndProcedure

Procedure.i avkPhysSlot(h.i)
  Define s.i
  s = avkTokenShape(h, #ANVIL_VK_TYPE_PHYSICAL_DEVICE, #ANVIL_VK_MAX_PHYSICAL_DEVICES)
  If s = 0 Or avkPhysLive[s] = 0 Or avkPhysGen[s] <> avkTokenGen(h) : ProcedureReturn 0 : EndIf
  ProcedureReturn s
EndProcedure

Procedure.i avkDevSlot(h.i)
  Define s.i
  s = avkTokenShape(h, #ANVIL_VK_TYPE_DEVICE, #ANVIL_VK_MAX_DEVICES)
  If s = 0 Or avkDevLive[s] = 0 Or avkDevGen[s] <> avkTokenGen(h) : ProcedureReturn 0 : EndIf
  ProcedureReturn s
EndProcedure

Procedure.i avkQueueSlot(h.i)
  Define s.i
  s = avkTokenShape(h, #ANVIL_VK_TYPE_QUEUE, #ANVIL_VK_MAX_QUEUES)
  If s = 0 Or avkQueueLive[s] = 0 Or avkQueueGen[s] <> avkTokenGen(h) : ProcedureReturn 0 : EndIf
  ProcedureReturn s
EndProcedure

Procedure.i avkPoolSlot(h.i)
  Define s.i
  s = avkTokenShape(h, #ANVIL_VK_TYPE_COMMAND_POOL, #ANVIL_VK_MAX_COMMAND_POOLS)
  If s = 0 Or avkPoolLive[s] = 0 Or avkPoolGen[s] <> avkTokenGen(h) : ProcedureReturn 0 : EndIf
  ProcedureReturn s
EndProcedure

Procedure.i avkCmdSlot(h.i)
  Define s.i
  s = avkTokenShape(h, #ANVIL_VK_TYPE_COMMAND_BUFFER, #ANVIL_VK_MAX_COMMAND_BUFFERS)
  If s = 0 Or avkCmdLive[s] = 0 Or avkCmdGen[s] <> avkTokenGen(h) : ProcedureReturn 0 : EndIf
  ProcedureReturn s
EndProcedure

; ----------------------------------------------------------------------
;  Capability answers.
;
;  AnvilVkBackendAvailable() is the production question and it is answered
;  by the linked backend, not by a flag any caller can set. A build that
;  links vk_backend_none.pbi answers 0 here and refuses instance creation
;  with VK_ERROR_INCOMPATIBLE_DRIVER, exactly as a loader does when no ICD
;  is installed.
; ----------------------------------------------------------------------
Procedure.i AnvilVkBackendAvailable()
  If (avkBackendCaps() & #ANVIL_VK_CAP_DEVICE) <> 0
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

; 1 when the linked backend executes clears on a GPU, 0 when it models
; state only. A gate uses this to refuse to call a state-only backend's
; result silicon.
Procedure.i AnvilVkBackendIsGpu()
  If (avkBackendCaps() & #ANVIL_VK_CAP_GPU) <> 0
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

; 1 when the linked backend executes a graphics pipeline. A backend that
; only clears answers 0 here and vkCreateGraphicsPipelines refuses.
Procedure.i AnvilVkBackendCanDraw()
  If (avkBackendCaps() & #ANVIL_VK_CAP_DRAW) <> 0
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

; Blend is useful only together with a graphics draw path. Requiring both
; bits here prevents a malformed backend capability word from advertising a
; format feature no queue can execute.
Procedure.i AnvilVkBackendCanBlendSourceOver()
  If (avkBackendCaps() & (#ANVIL_VK_CAP_DRAW | #ANVIL_VK_CAP_BLEND_SRC_OVER)) = (#ANVIL_VK_CAP_DRAW | #ANVIL_VK_CAP_BLEND_SRC_OVER)
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i AnvilVkBackendName()
  ProcedureReturn avkBackendName()
EndProcedure

Procedure.i AnvilVkInstanceCreate(*out)
  Define s.i
  Define p.i
  If *out = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, #VK_NULL_HANDLE)
  If AnvilVkBackendAvailable() = 0 : ProcedureReturn #VK_ERROR_INCOMPATIBLE_DRIVER : EndIf
  s = 1
  While s <= #ANVIL_VK_MAX_INSTANCES And avkInstLive[s] <> 0 : s = s + 1 : Wend
  If s > #ANVIL_VK_MAX_INSTANCES : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf
  p = 1
  While p <= #ANVIL_VK_MAX_PHYSICAL_DEVICES And avkPhysLive[p] <> 0 : p = p + 1 : Wend
  If p > #ANVIL_VK_MAX_PHYSICAL_DEVICES : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf
  avkInstGen[s] = avkNextGen(avkInstGen[s])
  avkInstLive[s] = 1
  avkPhysGen[p] = avkNextGen(avkPhysGen[p])
  avkPhysLive[p] = 1
  avkPhysInst[p] = s
  PokeI(*out, avkToken(#ANVIL_VK_TYPE_INSTANCE, s, avkInstGen[s]))
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkPhysicalEnumerate(instance.i, *count, *out)
  Define s.i
  Define p.i
  Define cap.i
  s = avkInstSlot(instance)
  If s = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If *count = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  p = 1
  While p <= #ANVIL_VK_MAX_PHYSICAL_DEVICES
    If avkPhysLive[p] <> 0 And avkPhysInst[p] = s : Break : EndIf
    p = p + 1
  Wend
  If *out = 0
    If p <= #ANVIL_VK_MAX_PHYSICAL_DEVICES : PokeL(*count, 1) : Else : PokeL(*count, 0) : EndIf
    ProcedureReturn #VK_SUCCESS
  EndIf
  cap = PeekL(*count)
  If cap < 1
    PokeL(*count, 0)
    ProcedureReturn #VK_INCOMPLETE
  EndIf
  If p > #ANVIL_VK_MAX_PHYSICAL_DEVICES
    PokeL(*count, 0)
    ProcedureReturn #VK_SUCCESS
  EndIf
  PokeI(*out, avkToken(#ANVIL_VK_TYPE_PHYSICAL_DEVICE, p, avkPhysGen[p]))
  PokeL(*count, 1)
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkDeviceCreate(physical.i, *out)
  Define p.i
  Define s.i
  Define q.i
  Define rc.i
  If *out = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, 0)
  p = avkPhysSlot(physical)
  If p = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  ; The backend gets its one chance to refuse before any object exists.
  rc = avkBackendPrepare()
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  s = 1
  While s <= #ANVIL_VK_MAX_DEVICES And avkDevLive[s] <> 0 : s = s + 1 : Wend
  q = 1
  While q <= #ANVIL_VK_MAX_QUEUES And avkQueueLive[q] <> 0 : q = q + 1 : Wend
  If s > #ANVIL_VK_MAX_DEVICES Or q > #ANVIL_VK_MAX_QUEUES : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf
  avkDevGen[s] = avkNextGen(avkDevGen[s])
  avkDevLive[s] = 1
  avkDevPhys[s] = p
  avkQueueGen[q] = avkNextGen(avkQueueGen[q])
  avkQueueLive[q] = 1
  avkQueueDev[q] = s
  PokeI(*out, avkToken(#ANVIL_VK_TYPE_DEVICE, s, avkDevGen[s]))
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkDeviceQueue(device.i, *out)
  Define d.i
  Define q.i
  If *out = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, 0)
  d = avkDevSlot(device)
  If d = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  q = 1
  While q <= #ANVIL_VK_MAX_QUEUES
    If avkQueueLive[q] <> 0 And avkQueueDev[q] = d
      PokeI(*out, avkToken(#ANVIL_VK_TYPE_QUEUE, q, avkQueueGen[q]))
      ProcedureReturn #VK_SUCCESS
    EndIf
    q = q + 1
  Wend
  ProcedureReturn #VK_ERROR_INITIALIZATION_FAILED
EndProcedure

; Host event state. GPU event commands are withheld until a submission path
; can honor their stage masks and memory dependencies.
Procedure.i avkEventSlot(event.i)
  Define s.i
  s = avkTokenShape(event, #ANVIL_VK_TYPE_EVENT, #ANVIL_VK_MAX_EVENTS)
  If s = 0 Or avkEventLive[s] = 0 Or avkEventGen[s] <> avkTokenGen(event) : ProcedureReturn 0 : EndIf
  ProcedureReturn s
EndProcedure

Procedure.i AnvilVkEventCreate(device.i, *out)
  Define d.i
  Define s.i
  If *out = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, #VK_NULL_HANDLE)
  d = avkDevSlot(device)
  If d = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If (avkBackendCaps() & #ANVIL_VK_CAP_DRAW) = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateEvent needs a graphics-capable queue family (Anvil code -20005, transfer-only backend); no event was created.")
  EndIf
  s = 1
  While s <= #ANVIL_VK_MAX_EVENTS And avkEventLive[s] <> 0 : s = s + 1 : Wend
  If s > #ANVIL_VK_MAX_EVENTS : ProcedureReturn #VK_ERROR_OUT_OF_HOST_MEMORY : EndIf
  avkEventGen[s] = avkNextGen(avkEventGen[s])
  avkEventDev[s] = d
  avkEventSet[s] = 0
  avkEventLive[s] = 1
  PokeI(*out, avkToken(#ANVIL_VK_TYPE_EVENT, s, avkEventGen[s]))
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkEventDestroy(device.i, event.i)
  Define d.i
  Define s.i
  If event = #VK_NULL_HANDLE : ProcedureReturn #VK_SUCCESS : EndIf
  d = avkDevSlot(device)
  s = avkEventSlot(event)
  If d = 0 Or s = 0 Or avkEventDev[s] <> d : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  avkEventLive[s] = 0
  avkEventSet[s] = 0
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkEventState(device.i, event.i, action.i)
  Define d.i
  Define s.i
  d = avkDevSlot(device)
  s = avkEventSlot(event)
  If d = 0 Or s = 0 Or avkEventDev[s] <> d
    ProcedureReturn avkFault(#ANVIL_VK_ERR_HANDLE, "a host event command was given a stale, foreign or wrong-device VkEvent (Anvil code -20002, invalid handle); event state was not changed.")
  EndIf
  If action = 1 : avkEventSet[s] = 1 : ProcedureReturn #VK_SUCCESS : EndIf
  If action = 2 : avkEventSet[s] = 0 : ProcedureReturn #VK_SUCCESS : EndIf
  If avkEventSet[s] <> 0 : ProcedureReturn #VK_EVENT_SET : EndIf
  ProcedureReturn #VK_EVENT_RESET
EndProcedure

Procedure.i AnvilVkCommandPoolCreate(device.i, flags.i, *out)
  Define d.i
  Define p.i
  If *out = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, 0)
  d = avkDevSlot(device)
  If d = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If (flags & (~(#VK_COMMAND_POOL_CREATE_TRANSIENT_BIT | #VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT))) <> 0
    ProcedureReturn #ANVIL_VK_ERR_ARGS
  EndIf
  p = 1
  While p <= #ANVIL_VK_MAX_COMMAND_POOLS And avkPoolLive[p] <> 0 : p = p + 1 : Wend
  If p > #ANVIL_VK_MAX_COMMAND_POOLS : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf
  avkPoolGen[p] = avkNextGen(avkPoolGen[p])
  avkPoolLive[p] = 1
  avkPoolDev[p] = d
  avkPoolFlags[p] = flags
  PokeI(*out, avkToken(#ANVIL_VK_TYPE_COMMAND_POOL, p, avkPoolGen[p]))
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkCommandBufferAllocate(device.i, pool.i, level.i, *out)
  Define d.i
  Define p.i
  Define c.i
  If *out = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, 0)
  d = avkDevSlot(device)
  p = avkPoolSlot(pool)
  If d = 0 Or p = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkPoolDev[p] <> d : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
  If level <> #VK_COMMAND_BUFFER_LEVEL_PRIMARY And level <> #VK_COMMAND_BUFFER_LEVEL_SECONDARY
    ProcedureReturn #ANVIL_VK_ERR_ARGS
  EndIf
  c = 1
  While c <= #ANVIL_VK_MAX_COMMAND_BUFFERS And avkCmdLive[c] <> 0 : c = c + 1 : Wend
  If c > #ANVIL_VK_MAX_COMMAND_BUFFERS : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf
  avkCmdGen[c] = avkNextGen(avkCmdGen[c])
  avkCmdLive[c] = 1
  avkCmdPool[c] = p
  avkCmdLevel[c] = level
  avkCmdState[c] = #ANVIL_VK_CB_INITIAL
  avkCmdBeginFlags[c] = 0
  avkCmdOps[c] = 0
  PokeI(*out, avkToken(#ANVIL_VK_TYPE_COMMAND_BUFFER, c, avkCmdGen[c]))
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkCommandBufferState(commandBuffer.i)
  Define c.i
  c = avkCmdSlot(commandBuffer)
  If c = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  ProcedureReturn avkCmdState[c]
EndProcedure

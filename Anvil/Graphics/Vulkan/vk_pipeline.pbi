; ======================================================================
;  Buffers, shader modules, render passes and the graphics pipeline
; ======================================================================
; SPDX-License-Identifier: MIT
;
; Target-neutral. Nothing here knows a QPU instruction, a VPM slot, a
; control-list packet or a tile. It owns the objects a draw needs, it
; joins the SPIR-V front end's two plans into one pipeline, and it hands
; the backend seam ONE closed draw.
;
; Read from the Vulkan specification:
;   .../chapters/pipelines.html      graphics pipeline creation, the
;                                    shader stages, and which state a
;                                    pipeline owns
;   .../chapters/fxvertex.html       vertex input bindings, attributes
;                                    and the formats they may take
;   .../chapters/renderpass.html     attachments, subpasses, load and
;                                    store operations, framebuffers
;   .../chapters/drawing.html        vkCmdDraw, the primitive topologies
;                                    and the instancing rules
;   .../chapters/resources.html      buffers, their usage flags and
;                                    their memory requirements
; No implementation source was consulted or translated.
;
; ======================================================================
;  WHAT THIS SLICE IMPLEMENTS
; ======================================================================
;   * one vertex input binding, VK_VERTEX_INPUT_RATE_VERTEX
;   * attributes at locations 0..n-1 (n <= 4), R32G32_SFLOAT,
;     R32G32B32_SFLOAT or R32G32B32A32_SFLOAT, all from binding 0
;   * VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST, no primitive restart
;   * one viewport and one scissor; either or both may be dynamic, with a
;     dynamic viewport paired with dynamic scissor for resize-safe state
;   * VK_POLYGON_MODE_FILL, VK_CULL_MODE_NONE, no depth bias, line width
;     1.0, no depth clamp, no rasteriser discard
;   * one sample, no sample shading, no alpha to coverage
;   * one colour attachment, every channel written, with blending either
;     disabled or straight source-over (SRC_ALPHA / ONE_MINUS_SRC_ALPHA,
;     ADD for colour and alpha)
;   * no depth-stencil state, no other dynamic state, no pipeline cache, no
;     derivative pipelines
;   * a render pass of exactly one colour attachment, one subpass, no
;     subpass dependencies, loadOp CLEAR and storeOp STORE
;   * a pipeline layout of no descriptor sets and at most one push
;     constant range, in the fragment stage, at offset 0, of 16 bytes
;
; Everything else is refused with a real code and a whole sentence.

XIncludeFile "Anvil/Graphics/Vulkan/vk_command.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_descriptor.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_spirv.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_ir.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_spirv_ir_adapter.pbi"

; A fragment whose stored value is a typed arithmetic graph is no longer one
; of the five legacy single-source shapes. This is an observation for gates
; and diagnostics only; resource validation uses the independent flags below.
#ANVIL_SPV_COLOUR_IR = 5

; EIGHT BUFFERS AND EIGHT SHADER MODULES, raised from four when the
; split vertex layout and the descriptor path arrived: one diagnostic
; now holds an interleaved array, a position array, a colour array and
; a uniform buffer at once, and five shader modules - three fragment
; shapes and two vertex ones. A limit that the instruments themselves
; sit exactly on is a limit that refuses the next honest use of it.
#ANVIL_VK_MAX_BUFFERS = 8
#ANVIL_VK_MAX_SHADER_MODULES = 8
; EIGHT PIPELINE LAYOUTS. The desk gate alone now needs four - one with
; no descriptor set, one with a push-constant range, one for each of
; two different descriptor set layouts - and a limit an instrument sits
; exactly on refuses the next honest use of it.
#ANVIL_VK_MAX_LAYOUTS = 8
#ANVIL_VK_MAX_RENDER_PASSES = 4
#ANVIL_VK_MAX_IMAGE_VIEWS = 4
#ANVIL_VK_MAX_FRAMEBUFFERS = 4
#ANVIL_VK_MAX_PIPELINES = 4

; The push-constant block this slice carries: one four-component colour.
#ANVIL_VK_PUSH_BYTES = 16

; ----------------------------------------------------------------------
;  BUFFERS
; ----------------------------------------------------------------------
Global Dim avkBufLive.a[#ANVIL_VK_MAX_BUFFERS + 1]
Global Dim avkBufGen.i[#ANVIL_VK_MAX_BUFFERS + 1]
Global Dim avkBufDev.i[#ANVIL_VK_MAX_BUFFERS + 1]
Global Dim avkBufSize.i[#ANVIL_VK_MAX_BUFFERS + 1]
Global Dim avkBufUsage.i[#ANVIL_VK_MAX_BUFFERS + 1]
Global Dim avkBufMemSlot.i[#ANVIL_VK_MAX_BUFFERS + 1]
Global Dim avkBufMemOffset.i[#ANVIL_VK_MAX_BUFFERS + 1]
Global Dim avkBufBound.a[#ANVIL_VK_MAX_BUFFERS + 1]
Global Dim avkBufInFlight.i[#ANVIL_VK_MAX_BUFFERS + 1]

; ----------------------------------------------------------------------
;  SHADER MODULES. One module owns one verified, immutable typed IR image.
;
;  The legacy coordinate/vertex plan remains beside it until typed IR can
;  represent gl_Position and multiple stores. Fragment compilation never
;  reads parser globals: it consumes the slot-owned IR below. `valid` and the
;  matching generation are published before the handle and invalidated on
;  destroy, so a recycled module slot cannot expose yesterday's semantics.
; ----------------------------------------------------------------------
Global Dim avkShLive.a[#ANVIL_VK_MAX_SHADER_MODULES + 1]
Global Dim avkShGen.i[#ANVIL_VK_MAX_SHADER_MODULES + 1]
Global Dim avkShDev.i[#ANVIL_VK_MAX_SHADER_MODULES + 1]
Global Dim avkShIr.AvkSpirvIrStorage[#ANVIL_VK_MAX_SHADER_MODULES + 1]
Global Dim avkShIrGen.i[#ANVIL_VK_MAX_SHADER_MODULES + 1]
Global Dim avkShIrLive.a[193]
Global Dim avkShStage.i[#ANVIL_VK_MAX_SHADER_MODULES + 1]
Global Dim avkShWords.i[#ANVIL_VK_MAX_SHADER_MODULES + 1]
Global Dim avkShInstr.i[#ANVIL_VK_MAX_SHADER_MODULES + 1]
Global Dim avkShInCount.i[#ANVIL_VK_MAX_SHADER_MODULES + 1]
Global Dim avkShOutCount.i[#ANVIL_VK_MAX_SHADER_MODULES + 1]
Global Dim avkShPosAttr.i[#ANVIL_VK_MAX_SHADER_MODULES + 1]
Global Dim avkShColourSrc.i[#ANVIL_VK_MAX_SHADER_MODULES + 1]
Global Dim avkShColourIdx.i[#ANVIL_VK_MAX_SHADER_MODULES + 1]
Global Dim avkShPush.i[#ANVIL_VK_MAX_SHADER_MODULES + 1]
Global Dim avkShUniform.i[#ANVIL_VK_MAX_SHADER_MODULES + 1]
Global Dim avkShUniformSet.i[#ANVIL_VK_MAX_SHADER_MODULES + 1]
Global Dim avkShUniformBinding.i[#ANVIL_VK_MAX_SHADER_MODULES + 1]
Global Dim avkShSample.i[#ANVIL_VK_MAX_SHADER_MODULES + 1]
Global Dim avkShSampleSet.i[#ANVIL_VK_MAX_SHADER_MODULES + 1]
Global Dim avkShSampleBinding.i[#ANVIL_VK_MAX_SHADER_MODULES + 1]
Global Dim avkShSampleCoord.i[#ANVIL_VK_MAX_SHADER_MODULES + 1]
Global Dim avkShUsesVarying.a[#ANVIL_VK_MAX_SHADER_MODULES + 1]
Global Dim avkShInComp.i[(#ANVIL_VK_MAX_SHADER_MODULES + 1) * #ANVIL_SPV_MAX_ATTRS]
Global Dim avkShOutComp.i[(#ANVIL_VK_MAX_SHADER_MODULES + 1) * #ANVIL_SPV_MAX_VARYINGS]
Global Dim avkShOutSrc.i[(#ANVIL_VK_MAX_SHADER_MODULES + 1) * #ANVIL_SPV_MAX_VARYINGS]
Global Dim avkShConst.i[(#ANVIL_VK_MAX_SHADER_MODULES + 1) * 4]

; ----------------------------------------------------------------------
;  PIPELINE LAYOUTS, RENDER PASSES, IMAGE VIEWS, FRAMEBUFFERS
; ----------------------------------------------------------------------
Global Dim avkLayLive.a[#ANVIL_VK_MAX_LAYOUTS + 1]
Global Dim avkLayGen.i[#ANVIL_VK_MAX_LAYOUTS + 1]
Global Dim avkLayDev.i[#ANVIL_VK_MAX_LAYOUTS + 1]
Global Dim avkLayPushBytes.i[#ANVIL_VK_MAX_LAYOUTS + 1]
Global Dim avkLaySetCount.i[#ANVIL_VK_MAX_LAYOUTS + 1]
Global Dim avkLayBindingCount.i[#ANVIL_VK_MAX_LAYOUTS + 1]
Global Dim avkLayBindingType.i[(#ANVIL_VK_MAX_LAYOUTS + 1) * #ANVIL_VK_MAX_SET_BINDINGS]
Global Dim avkLayBindingStages.i[(#ANVIL_VK_MAX_LAYOUTS + 1) * #ANVIL_VK_MAX_SET_BINDINGS]

Global Dim avkRpLive.a[#ANVIL_VK_MAX_RENDER_PASSES + 1]
Global Dim avkRpGen.i[#ANVIL_VK_MAX_RENDER_PASSES + 1]
Global Dim avkRpDev.i[#ANVIL_VK_MAX_RENDER_PASSES + 1]
Global Dim avkRpFormat.i[#ANVIL_VK_MAX_RENDER_PASSES + 1]
Global Dim avkRpFinalLayout.i[#ANVIL_VK_MAX_RENDER_PASSES + 1]
Global Dim avkRpInFlight.i[#ANVIL_VK_MAX_RENDER_PASSES + 1]

Global Dim avkIvLive.a[#ANVIL_VK_MAX_IMAGE_VIEWS + 1]
Global Dim avkIvGen.i[#ANVIL_VK_MAX_IMAGE_VIEWS + 1]
Global Dim avkIvDev.i[#ANVIL_VK_MAX_IMAGE_VIEWS + 1]
Global Dim avkIvImage.i[#ANVIL_VK_MAX_IMAGE_VIEWS + 1]
Global Dim avkIvImgSlot.i[#ANVIL_VK_MAX_IMAGE_VIEWS + 1]
Global Dim avkIvInFlight.i[#ANVIL_VK_MAX_IMAGE_VIEWS + 1]

; Samplers are target-neutral Vulkan state. The V3D backend will translate
; these values into its sampler-state record when the combined-image
; descriptor path lands; object ownership does not belong in that backend.
Global Dim avkSampLive.a[#ANVIL_VK_MAX_SAMPLERS + 1]
Global Dim avkSampGen.i[#ANVIL_VK_MAX_SAMPLERS + 1]
Global Dim avkSampDev.i[#ANVIL_VK_MAX_SAMPLERS + 1]
Global Dim avkSampMag.i[#ANVIL_VK_MAX_SAMPLERS + 1]
Global Dim avkSampMin.i[#ANVIL_VK_MAX_SAMPLERS + 1]
Global Dim avkSampInFlight.i[#ANVIL_VK_MAX_SAMPLERS + 1]

Global Dim avkFbLive.a[#ANVIL_VK_MAX_FRAMEBUFFERS + 1]
Global Dim avkFbGen.i[#ANVIL_VK_MAX_FRAMEBUFFERS + 1]
Global Dim avkFbDev.i[#ANVIL_VK_MAX_FRAMEBUFFERS + 1]
Global Dim avkFbRp.i[#ANVIL_VK_MAX_FRAMEBUFFERS + 1]
Global Dim avkFbRpHandle.i[#ANVIL_VK_MAX_FRAMEBUFFERS + 1]
Global Dim avkFbView.i[#ANVIL_VK_MAX_FRAMEBUFFERS + 1]
Global Dim avkFbViewHandle.i[#ANVIL_VK_MAX_FRAMEBUFFERS + 1]
Global Dim avkFbW.i[#ANVIL_VK_MAX_FRAMEBUFFERS + 1]
Global Dim avkFbH.i[#ANVIL_VK_MAX_FRAMEBUFFERS + 1]
Global Dim avkFbInFlight.i[#ANVIL_VK_MAX_FRAMEBUFFERS + 1]

; ----------------------------------------------------------------------
;  PIPELINES. The plan the backend compiles from.
; ----------------------------------------------------------------------
Global Dim avkPipeLive.a[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeGen.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeDev.i[#ANVIL_VK_MAX_PIPELINES + 1]
; A pipeline owns the complete layout compatibility signature it was created
; against. It does not chase a pipeline-layout slot that may be destroyed and
; reused before an already-created pipeline is submitted.
Global Dim avkPipePushBytes.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeSetCount.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeBindingCount.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeBindingType.i[(#ANVIL_VK_MAX_PIPELINES + 1) * #ANVIL_VK_MAX_SET_BINDINGS]
Global Dim avkPipeBindingStages.i[(#ANVIL_VK_MAX_PIPELINES + 1) * #ANVIL_VK_MAX_SET_BINDINGS]
Global Dim avkPipeRp.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeBindCount.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeBindStride.i[(#ANVIL_VK_MAX_PIPELINES + 1) * #ANVIL_VK_MAX_BINDINGS]
Global Dim avkPipeAttrBinding.i[(#ANVIL_VK_MAX_PIPELINES + 1) * #ANVIL_SPV_MAX_ATTRS]
Global Dim avkPipeAttrCount.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipePosAttr.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeVaryCount.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeColourSrc.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeColourIdx.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeUsesPush.a[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeUsesUniform.a[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeUsesSample.a[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeUsesVarying.a[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeUniformBinding.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeSampleBinding.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeSampleCoord.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeViewX.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeViewY.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeViewW.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeViewH.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeDynamicViewport.a[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeDynamicScissor.a[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeScissorX.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeScissorY.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeScissorW.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeScissorH.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeSampleMask.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeBlendMode.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeCodeBase.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeCodeBytes.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeCodeMem.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeInFlight.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeAttrComp.i[(#ANVIL_VK_MAX_PIPELINES + 1) * #ANVIL_SPV_MAX_ATTRS]
Global Dim avkPipeAttrOffset.i[(#ANVIL_VK_MAX_PIPELINES + 1) * #ANVIL_SPV_MAX_ATTRS]
Global Dim avkPipeVaryComp.i[(#ANVIL_VK_MAX_PIPELINES + 1) * #ANVIL_SPV_MAX_VARYINGS]
Global Dim avkPipeVarySrc.i[(#ANVIL_VK_MAX_PIPELINES + 1) * #ANVIL_SPV_MAX_VARYINGS]
Global Dim avkPipeConst.i[(#ANVIL_VK_MAX_PIPELINES + 1) * 4]

; The per-command-buffer recording state lives in vk_command.pbi, beside
; the rest of it, so that one reset procedure clears all of it. This file
; fills it and reads it back at submit time.
;
; The push-constant block handed to the backend is staged here, because
; the backend needs an address and a recorded command must not point at
; a caller's stack frame that is long gone by the time it is submitted.
; One closed record plus pointer-owned payload per recorded draw. No pointer in
; the list aliases current command-buffer bind state, and later draws cannot
; overwrite earlier push, binding or sampled-image records.
Global Dim avkFlightDraw.AnvilVkBackendDraw[#ANVIL_VK_MAX_RECORDED_DRAWS + 1]
Global Dim avkFlightBinding.AnvilVkBackendBinding[(#ANVIL_VK_MAX_RECORDED_DRAWS + 1) * #ANVIL_VK_MAX_BINDINGS]
Global Dim avkFlightPush.l[(#ANVIL_VK_MAX_RECORDED_DRAWS + 1) * 4]
Global Dim avkFlightSample.AnvilVkBackendSampledImage[#ANVIL_VK_MAX_RECORDED_DRAWS + 1]
Global avkFlightDrawList.AnvilVkBackendDrawList
Global avkFlightDrawCount.i = 0
Global avkFlightLedgerCommitted.i = 0
Global avkFlightDrawPreparedCb.i = 0
Global avkFlightDrawOwnerCb.i = 0

; Generation-tagged handles are resolved once during whole-list preflight.
; Retain and release use only these captured slots, including the memory slot
; behind each buffer/image. Rewriting or recycling a descriptor can therefore
; never redirect completion to a different generation. Repeated slots remain
; repeated in the ledger so aliases increment and decrement additively.
Global Dim avkFlightPipe.i[#ANVIL_VK_MAX_RECORDED_DRAWS + 1]
Global Dim avkFlightSet.i[#ANVIL_VK_MAX_RECORDED_DRAWS + 1]
Global Dim avkFlightFb.i[#ANVIL_VK_MAX_RECORDED_DRAWS + 1]
Global Dim avkFlightRp.i[#ANVIL_VK_MAX_RECORDED_DRAWS + 1]
Global Dim avkFlightTargetView.i[#ANVIL_VK_MAX_RECORDED_DRAWS + 1]
Global Dim avkFlightTargetImage.i[#ANVIL_VK_MAX_RECORDED_DRAWS + 1]
Global Dim avkFlightTargetMem.i[#ANVIL_VK_MAX_RECORDED_DRAWS + 1]
Global Dim avkFlightVertexBuf.i[(#ANVIL_VK_MAX_RECORDED_DRAWS + 1) * #ANVIL_VK_MAX_BINDINGS]
Global Dim avkFlightVertexMem.i[(#ANVIL_VK_MAX_RECORDED_DRAWS + 1) * #ANVIL_VK_MAX_BINDINGS]
Global Dim avkFlightIndexBuf.i[#ANVIL_VK_MAX_RECORDED_DRAWS + 1]
Global Dim avkFlightIndexMem.i[#ANVIL_VK_MAX_RECORDED_DRAWS + 1]
Global Dim avkFlightUniformBuf.i[#ANVIL_VK_MAX_RECORDED_DRAWS + 1]
Global Dim avkFlightUniformMem.i[#ANVIL_VK_MAX_RECORDED_DRAWS + 1]
Global Dim avkFlightSampleImage.i[#ANVIL_VK_MAX_RECORDED_DRAWS + 1]
Global Dim avkFlightSampleMem.i[#ANVIL_VK_MAX_RECORDED_DRAWS + 1]
Global Dim avkFlightSampler.i[#ANVIL_VK_MAX_RECORDED_DRAWS + 1]
Global Dim avkFlightSampleView.i[#ANVIL_VK_MAX_RECORDED_DRAWS + 1]
Global Dim avkDsInFlight.i[#ANVIL_VK_MAX_DESCRIPTOR_SETS + 1]

; Recording-time sampled-descriptor validation scratch. Closed submission
; owns one immutable sampled record per draw in avkFlightSample above.
Global avkSampleStage.AnvilVkBackendSampledImage

Procedure.i avkBufSlot(h.i)
  Define s.i
  s = avkTokenShape(h, #ANVIL_VK_TYPE_BUFFER, #ANVIL_VK_MAX_BUFFERS)
  If s = 0 Or avkBufLive[s] = 0 Or avkBufGen[s] <> avkTokenGen(h) : ProcedureReturn 0 : EndIf
  ProcedureReturn s
EndProcedure

Procedure.i avkShSlot(h.i)
  Define s.i
  s = avkTokenShape(h, #ANVIL_VK_TYPE_SHADER_MODULE, #ANVIL_VK_MAX_SHADER_MODULES)
  If s = 0 Or avkShLive[s] = 0 Or avkShGen[s] <> avkTokenGen(h) : ProcedureReturn 0 : EndIf
  ProcedureReturn s
EndProcedure

Procedure.i avkLaySlot(h.i)
  Define s.i
  s = avkTokenShape(h, #ANVIL_VK_TYPE_PIPELINE_LAYOUT, #ANVIL_VK_MAX_LAYOUTS)
  If s = 0 Or avkLayLive[s] = 0 Or avkLayGen[s] <> avkTokenGen(h) : ProcedureReturn 0 : EndIf
  ProcedureReturn s
EndProcedure

Procedure.i avkRpSlot(h.i)
  Define s.i
  s = avkTokenShape(h, #ANVIL_VK_TYPE_RENDER_PASS, #ANVIL_VK_MAX_RENDER_PASSES)
  If s = 0 Or avkRpLive[s] = 0 Or avkRpGen[s] <> avkTokenGen(h) : ProcedureReturn 0 : EndIf
  ProcedureReturn s
EndProcedure

Procedure.i avkIvSlot(h.i)
  Define s.i
  s = avkTokenShape(h, #ANVIL_VK_TYPE_IMAGE_VIEW, #ANVIL_VK_MAX_IMAGE_VIEWS)
  If s = 0 Or avkIvLive[s] = 0 Or avkIvGen[s] <> avkTokenGen(h) : ProcedureReturn 0 : EndIf
  ProcedureReturn s
EndProcedure

Procedure.i avkFbSlot(h.i)
  Define s.i
  s = avkTokenShape(h, #ANVIL_VK_TYPE_FRAMEBUFFER, #ANVIL_VK_MAX_FRAMEBUFFERS)
  If s = 0 Or avkFbLive[s] = 0 Or avkFbGen[s] <> avkTokenGen(h) : ProcedureReturn 0 : EndIf
  ProcedureReturn s
EndProcedure

Procedure.i avkSamplerSlot(h.i)
  Define s.i
  s = avkTokenShape(h, #ANVIL_VK_TYPE_SAMPLER, #ANVIL_VK_MAX_SAMPLERS)
  If s = 0 Or avkSampLive[s] = 0 Or avkSampGen[s] <> avkTokenGen(h) : ProcedureReturn 0 : EndIf
  ProcedureReturn s
EndProcedure

; Descriptor-side views of the two object tables owned here. Returning the
; device SLOT makes zero the complete stale-handle answer and lets the
; descriptor owner compare all objects without retaining private table slots.
Procedure.i avkDescImageViewDevice(view.i)
  Define s.i
  s = avkIvSlot(view)
  If s = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkIvDev[s]
EndProcedure

Procedure.i avkDescImageViewImage(view.i)
  Define s.i
  Define image.i
  s = avkIvSlot(view)
  If s = 0 : ProcedureReturn 0 : EndIf
  image = avkIvImage[s]
  If avkImgSlot(image) <> avkIvImgSlot[s] : ProcedureReturn 0 : EndIf
  ProcedureReturn image
EndProcedure

Procedure.i avkDescSamplerDevice(sampler.i)
  Define s.i
  s = avkSamplerSlot(sampler)
  If s = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkSampDev[s]
EndProcedure

Procedure.i avkDescSamplerMagFilter(sampler.i)
  Define s.i
  s = avkSamplerSlot(sampler)
  If s = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkSampMag[s]
EndProcedure

Procedure.i avkDescSamplerMinFilter(sampler.i)
  Define s.i
  s = avkSamplerSlot(sampler)
  If s = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkSampMin[s]
EndProcedure

; ======================================================================
;  SAMPLERS -- the object/lifecycle half of the sampled-image path
; ======================================================================
Procedure.i AnvilVkSamplerCreate(device.i, *ci.VkSamplerCreateInfo, *out)
  Define d.i
  Define s.i
  If *ci = 0 Or *out = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, #VK_NULL_HANDLE)
  d = avkDevSlot(device)
  If d = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If (*ci\sType & $FFFFFFFF) <> #VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateSampler was given a VkSamplerCreateInfo whose sType is wrong (Anvil code -20001, wrong sType); it must be VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO.")
  EndIf
  If *ci\pNext <> 0 Or (*ci\flags & $FFFFFFFF) <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateSampler was given a pNext chain or creation flags (Anvil code -20005, unsupported sampler extension); use the core structure with pNext null and flags zero.")
  EndIf
  If Not ((*ci\magFilter & $FFFFFFFF) = #VK_FILTER_NEAREST Or (*ci\magFilter & $FFFFFFFF) = #VK_FILTER_LINEAR) Or Not ((*ci\minFilter & $FFFFFFFF) = #VK_FILTER_NEAREST Or (*ci\minFilter & $FFFFFFFF) = #VK_FILTER_LINEAR)
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateSampler was given a minification or magnification filter outside VkFilter (Anvil code -20001, invalid filter); use VK_FILTER_NEAREST or VK_FILTER_LINEAR.")
  EndIf
  If (*ci\mipmapMode & $FFFFFFFF) <> #VK_SAMPLER_MIPMAP_MODE_NEAREST Or (PeekL(@*ci\minLod) & $7FFFFFFF) <> 0 Or (PeekL(@*ci\maxLod) & $7FFFFFFF) <> 0 Or (PeekL(@*ci\mipLodBias) & $7FFFFFFF) <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateSampler requested mip filtering or a nonzero LOD range or bias (Anvil code -20005, mipmaps not implemented); this image slice has one mip level, so use NEAREST mip mode and zero for minLod, maxLod and mipLodBias.")
  EndIf
  If (*ci\addressModeU & $FFFFFFFF) <> #VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE Or (*ci\addressModeV & $FFFFFFFF) <> #VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE Or (*ci\addressModeW & $FFFFFFFF) <> #VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateSampler requested an address mode other than VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE (Anvil code -20005, unsupported address mode); use clamp-to-edge on U, V and W for this 2D texture slice.")
  EndIf
  If *ci\anisotropyEnable <> #VK_FALSE Or *ci\compareEnable <> #VK_FALSE Or *ci\unnormalizedCoordinates <> #VK_FALSE
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateSampler requested anisotropy, comparison sampling or unnormalized coordinates (Anvil code -20005, unsupported sampler mode); leave all three disabled for normalized colour sampling.")
  EndIf
  s = 1
  While s <= #ANVIL_VK_MAX_SAMPLERS And avkSampLive[s] <> 0 : s = s + 1 : Wend
  If s > #ANVIL_VK_MAX_SAMPLERS : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf
  avkSampGen[s] = avkNextGen(avkSampGen[s])
  avkSampDev[s] = d
  avkSampMag[s] = *ci\magFilter & $FFFFFFFF
  avkSampMin[s] = *ci\minFilter & $FFFFFFFF
  avkSampInFlight[s] = 0
  avkSampLive[s] = 1
  PokeI(*out, avkToken(#ANVIL_VK_TYPE_SAMPLER, s, avkSampGen[s]))
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure AnvilVkSamplerDestroy(device.i, sampler.i)
  Define d.i
  Define s.i
  If sampler = #VK_NULL_HANDLE
    ProcedureReturn
  EndIf
  d = avkDevSlot(device)
  s = avkSamplerSlot(sampler)
  If s = 0
    avkFault(#ANVIL_VK_ERR_HANDLE, "vkDestroySampler was given a VkSampler handle that is not live (Anvil code -20002, stale or foreign handle); nothing was destroyed.")
    ProcedureReturn
  EndIf
  If d = 0 Or avkSampDev[s] <> d
    avkFault(#ANVIL_VK_ERR_OWNER, "vkDestroySampler was called through a device that does not own it (Anvil code -20003, wrong parent); destroy the sampler through the VkDevice that created it.")
    ProcedureReturn
  EndIf
  If avkSampInFlight[s] <> 0
    avkFault(#ANVIL_VK_ERR_STATE, "vkDestroySampler was called while a submission is reading it (Anvil code -20004, resource in use); wait for the submission fence or call vkDeviceWaitIdle before destroying it.")
    ProcedureReturn
  EndIf
  avkSampLive[s] = 0
EndProcedure

Procedure.i avkPipeSlot(h.i)
  Define s.i
  s = avkTokenShape(h, #ANVIL_VK_TYPE_PIPELINE, #ANVIL_VK_MAX_PIPELINES)
  If s = 0 Or avkPipeLive[s] = 0 Or avkPipeGen[s] <> avkTokenGen(h) : ProcedureReturn 0 : EndIf
  ProcedureReturn s
EndProcedure

; ======================================================================
;  BUFFERS
; ======================================================================
Procedure.i AnvilVkBufferCreate(device.i, size.i, usage.i, sharing.i, *out)
  Define d.i
  Define s.i
  If *out = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, #VK_NULL_HANDLE)
  d = avkDevSlot(device)
  If d = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If size <= 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateBuffer was asked for a buffer of zero or negative bytes (Anvil code -20001, invalid argument); VkBufferCreateInfo.size must be greater than zero.")
  EndIf
  If sharing <> #VK_SHARING_MODE_EXCLUSIVE
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateBuffer was asked for VK_SHARING_MODE_CONCURRENT (Anvil code -20005, unsupported sharing mode); there is one queue family on this device, so concurrent sharing has no second family to share with.")
  EndIf
  If usage = 0 Or (usage & (~(#VK_BUFFER_USAGE_TRANSFER_SRC_BIT | #VK_BUFFER_USAGE_TRANSFER_DST_BIT | #VK_BUFFER_USAGE_VERTEX_BUFFER_BIT | #VK_BUFFER_USAGE_INDEX_BUFFER_BIT | #VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT))) <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateBuffer was asked for a buffer usage Anvil does not implement (Anvil code -20005, unsupported usage); the implemented bits are VERTEX_BUFFER, INDEX_BUFFER, UNIFORM_BUFFER, TRANSFER_SRC and TRANSFER_DST. Storage, indirect and texel-buffer usage remain unsupported.")
  EndIf
  s = 1
  While s <= #ANVIL_VK_MAX_BUFFERS And avkBufLive[s] <> 0 : s = s + 1 : Wend
  If s > #ANVIL_VK_MAX_BUFFERS : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf
  avkBufGen[s] = avkNextGen(avkBufGen[s])
  avkBufLive[s] = 1
  avkBufDev[s] = d
  avkBufSize[s] = size
  avkBufUsage[s] = usage
  avkBufMemSlot[s] = 0
  avkBufMemOffset[s] = 0
  avkBufBound[s] = 0
  avkBufInFlight[s] = 0
  PokeI(*out, avkToken(#ANVIL_VK_TYPE_BUFFER, s, avkBufGen[s]))
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkBufferSize(buffer.i)
  Define s.i
  s = avkBufSlot(buffer)
  If s = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkBufSize[s]
EndProcedure

; A buffer's alignment is the page granularity the backend reports, the
; same rule an image follows: the GPU reaches both through one page
; table, so both are placed on a page.
Procedure.i AnvilVkBufferAlignment(buffer.i)
  Define s.i
  s = avkBufSlot(buffer)
  If s = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkBackendImageAlignment()
EndProcedure

Procedure.i AnvilVkBufferAddress(buffer.i)
  Define s.i
  s = avkBufSlot(buffer)
  If s = 0 Or avkBufBound[s] = 0 : ProcedureReturn 0 : EndIf
  If avkHeapReady = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkHeapBase + avkMemOffset[avkBufMemSlot[s]] + avkBufMemOffset[s]
EndProcedure

Procedure.i AnvilVkBufferBindMemory(device.i, buffer.i, memory.i, memoryOffset.i)
  Define d.i
  Define s.i
  Define m.i
  Define align.i
  d = avkDevSlot(device)
  s = avkBufSlot(buffer)
  m = avkMemSlot(memory)
  If d = 0 Or s = 0 Or m = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkBufDev[s] <> d Or avkMemDev[m] <> d
    ProcedureReturn avkFault(#ANVIL_VK_ERR_OWNER, "vkBindBufferMemory was given a buffer and an allocation that do not both belong to the VkDevice it was called on (Anvil code -20003, wrong parent); bind a buffer to memory allocated from the same device.")
  EndIf
  If avkBufBound[s] <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkBindBufferMemory was called on a buffer that is already bound (Anvil code -20004, already bound); a non-sparse buffer may be bound exactly once, and rebinding is not a way to move it.")
  EndIf
  align = avkBackendImageAlignment()
  If align < 1 Or (memoryOffset % align) <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkBindBufferMemory was given a memoryOffset that is not a multiple of the alignment vkGetBufferMemoryRequirements reported (Anvil code -20001, misaligned bind); round the offset up to VkMemoryRequirements.alignment before binding.")
  EndIf
  If memoryOffset < 0 Or memoryOffset > avkMemSize[m]
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkBindBufferMemory was given a memoryOffset outside the allocation (Anvil code -20001, offset out of range); the offset must be inside the VkDeviceMemory it names.")
  EndIf
  If (avkMemSize[m] - memoryOffset) < avkBufSize[s]
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkBindBufferMemory was asked to place a buffer past the end of its allocation (Anvil code -20001, allocation too small); VkMemoryRequirements.size bytes must fit between memoryOffset and the end of the VkDeviceMemory.")
  EndIf
  avkBufMemSlot[s] = m
  avkBufMemOffset[s] = memoryOffset
  avkBufBound[s] = 1
  avkMemBinds[m] = avkMemBinds[m] + 1
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure AnvilVkBufferDestroy(device.i, buffer.i)
  Define d.i
  Define s.i
  d = avkDevSlot(device)
  s = avkBufSlot(buffer)
  If s = 0
    If buffer <> #VK_NULL_HANDLE
      avkFault(#ANVIL_VK_ERR_HANDLE, "vkDestroyBuffer was given a VkBuffer handle that is not live on this device (Anvil code -20002, stale or foreign handle); nothing was destroyed. A buffer handle does not come back after it is destroyed, so check for a double destroy.")
    EndIf
    ProcedureReturn
  EndIf
  If d = 0 Or avkBufDev[s] <> d
    avkFault(#ANVIL_VK_ERR_OWNER, "vkDestroyBuffer was called with a device that does not own this buffer (Anvil code -20003, wrong parent); nothing was destroyed. Destroy a buffer through the VkDevice that created it.")
    ProcedureReturn
  EndIf
  If avkBufInFlight[s] <> 0
    avkFault(#ANVIL_VK_ERR_STATE, "vkDestroyBuffer was called while a submitted command buffer still reads this buffer (Anvil code -20004, resource in use); nothing was destroyed. Wait on the submission's fence with vkWaitForFences, or call vkDeviceWaitIdle, before destroying it.")
    ProcedureReturn
  EndIf
  If avkBufBound[s] <> 0
    avkMemBinds[avkBufMemSlot[s]] = avkMemBinds[avkBufMemSlot[s]] - 1
  EndIf
  avkBufLive[s] = 0
  avkBufBound[s] = 0
EndProcedure

; Resolve a transfer source both while recording and immediately before
; submission. The handle, generation, binding, usage, owner and exact range
; are checked every time; recording never turns a resource into a borrowed
; raw address that can survive destruction or slot reuse.
Procedure.i avkCopyBufferResolve(buffer.i, deviceSlot.i, offset.i, bytes.i, *baseOut)
  Define b.i
  Define base.i
  Define alignment.i
  If *baseOut <> 0 : PokeI(*baseOut, 0) : EndIf
  b = avkBufSlot(buffer)
  If b = 0 Or avkBufDev[b] <> deviceSlot Or avkBufBound[b] = 0 : ProcedureReturn 0 : EndIf
  If (avkBufUsage[b] & #VK_BUFFER_USAGE_TRANSFER_SRC_BIT) = 0 : ProcedureReturn 0 : EndIf
  If offset < 0 Or bytes < 1 Or offset > avkBufSize[b] Or bytes > (avkBufSize[b] - offset) : ProcedureReturn 0 : EndIf
  base = AnvilVkBufferAddress(buffer)
  alignment = avkBackendImageCopySourceAlignment()
  If alignment < 1 Or (alignment & (alignment - 1)) <> 0 : ProcedureReturn 0 : EndIf
  If base = 0 Or ((base + offset) % alignment) <> 0 : ProcedureReturn 0 : EndIf
  If *baseOut <> 0 : PokeI(*baseOut, base + offset) : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i avkTransferBufferResolve(buffer.i, deviceSlot.i, usage.i, offset.i, bytes.i, *baseOut)
  Define b.i
  Define base.i
  If *baseOut <> 0 : PokeI(*baseOut, 0) : EndIf
  b = avkBufSlot(buffer)
  If b = 0 Or avkBufDev[b] <> deviceSlot Or avkBufBound[b] = 0 : ProcedureReturn 0 : EndIf
  If (avkBufUsage[b] & usage) = 0 : ProcedureReturn 0 : EndIf
  If offset < 0 Or bytes < 1 Or offset >= avkBufSize[b] Or bytes > (avkBufSize[b] - offset) : ProcedureReturn 0 : EndIf
  base = AnvilVkBufferAddress(buffer)
  If base = 0 : ProcedureReturn 0 : EndIf
  If *baseOut <> 0 : PokeI(*baseOut, base + offset) : EndIf
  ProcedureReturn 1
EndProcedure

Procedure avkCopyBufferRetain(c.i)
  Define o.i
  Define b.i
  o = avkCbOpHead[c]
  While o <> 0
    If avkOpKind[o] = #ANVIL_VK_OP_COPY_BUFFER_IMAGE Or avkOpKind[o] = #ANVIL_VK_OP_COPY_BUFFER
      b = avkBufSlot(avkOpBuffer[o])
      If b <> 0
        avkBufInFlight[b] = avkBufInFlight[b] + 1
        avkMemInFlight[avkBufMemSlot[b]] = avkMemInFlight[avkBufMemSlot[b]] + 1
      EndIf
      If avkOpKind[o] = #ANVIL_VK_OP_COPY_BUFFER
        b = avkBufSlot(avkOpDstBuffer[o])
        If b <> 0
          avkBufInFlight[b] = avkBufInFlight[b] + 1
          avkMemInFlight[avkBufMemSlot[b]] = avkMemInFlight[avkBufMemSlot[b]] + 1
        EndIf
      EndIf
    EndIf
    o = avkOpNext[o]
  Wend
EndProcedure

Procedure avkCopyBufferRelease(c.i)
  Define o.i
  Define b.i
  o = avkCbOpHead[c]
  While o <> 0
    If avkOpKind[o] = #ANVIL_VK_OP_COPY_BUFFER_IMAGE Or avkOpKind[o] = #ANVIL_VK_OP_COPY_BUFFER
      b = avkBufSlot(avkOpBuffer[o])
      If b <> 0
        If avkBufInFlight[b] > 0 : avkBufInFlight[b] = avkBufInFlight[b] - 1 : EndIf
        If avkMemInFlight[avkBufMemSlot[b]] > 0 : avkMemInFlight[avkBufMemSlot[b]] = avkMemInFlight[avkBufMemSlot[b]] - 1 : EndIf
      EndIf
      If avkOpKind[o] = #ANVIL_VK_OP_COPY_BUFFER
        b = avkBufSlot(avkOpDstBuffer[o])
        If b <> 0
          If avkBufInFlight[b] > 0 : avkBufInFlight[b] = avkBufInFlight[b] - 1 : EndIf
          If avkMemInFlight[avkBufMemSlot[b]] > 0 : avkMemInFlight[avkBufMemSlot[b]] = avkMemInFlight[avkBufMemSlot[b]] - 1 : EndIf
        EndIf
      EndIf
    EndIf
    o = avkOpNext[o]
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  THE SEAM vk_descriptor.pbi DECLARED. Five questions about a VkBuffer,
;  answered here because the buffer objects live in this file and the
;  descriptor objects are included before it and must not reach into it.
; ----------------------------------------------------------------------
Procedure.i avkDescBufferLive(buffer.i)
  Define s.i
  s = avkBufSlot(buffer)
  If s = 0 Or avkBufBound[s] = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i avkDescBufferUniform(buffer.i)
  Define s.i
  s = avkBufSlot(buffer)
  If s = 0 : ProcedureReturn 0 : EndIf
  If (avkBufUsage[s] & #VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT) = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i avkDescBufferSize(buffer.i)
  Define s.i
  s = avkBufSlot(buffer)
  If s = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkBufSize[s]
EndProcedure

Procedure.i avkDescBufferAddress(buffer.i)
  ProcedureReturn AnvilVkBufferAddress(buffer)
EndProcedure

Procedure.i avkDescBufferDevice(buffer.i)
  Define s.i
  s = avkBufSlot(buffer)
  If s = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkBufDev[s]
EndProcedure

; ======================================================================
;  SHADER MODULES
; ======================================================================
Procedure.i avkShIrDecoration(*m.AvkIrModule, id.i, kind.i)
  Define i.i
  Define *d.AvkIrDecoration
  i = 0
  While i < *m\decorationCount
    *d = avkIrDecorationAt(*m, i)
    If *d\sourceId = id And *d\member = -1 And *d\kind = kind
      ProcedureReturn *d\value
    EndIf
    i = i + 1
  Wend
  ProcedureReturn -1
EndProcedure

Procedure.i avkShIrMemberDecoration(*m.AvkIrModule, id.i, member.i, kind.i)
  Define i.i
  Define *d.AvkIrDecoration
  i = 0
  While i < *m\decorationCount
    *d = avkIrDecorationAt(*m, i)
    If *d\sourceId = id And *d\member = member And *d\kind = kind
      ProcedureReturn *d\value
    EndIf
    i = i + 1
  Wend
  ProcedureReturn -1
EndProcedure

Procedure.i avkShIrBlockSelectionValid(*m.AvkIrModule, variableId.i, member.i)
  Define *v.AvkIrVariable = avkIrFindVariable(*m, variableId)
  Define *pointer.AvkIrType
  Define *block.AvkIrType
  Define *memberType.AvkIrType
  Define *scalar.AvkIrType
  Define typeId.i
  If *v = 0 Or member <> 0 : ProcedureReturn 0 : EndIf
  *pointer = avkIrFindType(*m, *v\pointerType)
  If *pointer = 0 Or *pointer\kind <> #ANVIL_IR_TYPE_POINTER : ProcedureReturn 0 : EndIf
  *block = avkIrFindType(*m, *pointer\pointeeType)
  If *block = 0 Or *block\kind <> #ANVIL_IR_TYPE_STRUCT Or *block\memberCount < 1 : ProcedureReturn 0 : EndIf
  If avkShIrDecoration(*m, *block\sourceId, #ANVIL_IR_DEC_BLOCK) < 0 : ProcedureReturn 0 : EndIf
  If avkShIrMemberDecoration(*m, *block\sourceId, 0, #ANVIL_IR_DEC_OFFSET) <> 0 : ProcedureReturn 0 : EndIf
  typeId = avkIrMemberType(*block, 0)
  *memberType = avkIrFindType(*m, typeId)
  If *memberType = 0 Or *memberType\kind <> #ANVIL_IR_TYPE_VECTOR Or *memberType\componentCount <> 4 : ProcedureReturn 0 : EndIf
  *scalar = avkIrFindType(*m, *memberType\componentType)
  If *scalar = 0 Or *scalar\kind <> #ANVIL_IR_TYPE_FLOAT Or *scalar\width <> 32 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i avkShIrComponents(*m.AvkIrModule, variableId.i)
  Define *v.AvkIrVariable = avkIrFindVariable(*m, variableId)
  Define *p.AvkIrType
  If *v = 0 : ProcedureReturn 0 : EndIf
  *p = avkIrFindType(*m, *v\pointerType)
  If *p = 0 Or *p\kind <> #ANVIL_IR_TYPE_POINTER : ProcedureReturn 0 : EndIf
  ProcedureReturn avkIrFloatLanes(*m, *p\pointeeType)
EndProcedure

Procedure.i avkShIrPointerSelection(*m.AvkIrModule, pointerId.i, *variableOut, *memberOut)
  Define *v.AvkIrVariable = avkIrFindVariable(*m, pointerId)
  Define *n.AvkIrNode
  Define *c.AvkIrConstant
  If *v <> 0
    PokeI(*variableOut, *v\sourceId)
    PokeI(*memberOut, -1)
    ProcedureReturn *v\pointerType
  EndIf
  *n = avkIrFindNode(*m, pointerId)
  If *n = 0 Or *n\kind <> #ANVIL_IR_OP_ACCESS_CHAIN : ProcedureReturn 0 : EndIf
  *v = avkIrFindVariable(*m, *n\operand0)
  *c = avkIrFindConstant(*m, *n\operand1)
  If *v = 0 Or *c = 0 : ProcedureReturn 0 : EndIf
  PokeI(*variableOut, *v\sourceId)
  PokeI(*memberOut, *c\word0)
  ProcedureReturn *n\resultType
EndProcedure

Procedure.i avkShIrInputIndex(*m.AvkIrModule, variableId.i)
  ProcedureReturn avkShIrDecoration(*m, variableId, #ANVIL_IR_DEC_LOCATION)
EndProcedure

Procedure avkShIrBuildLive(*m.AvkIrModule, rootId.i)
  Define i.i
  Define k.i
  Define changed.i
  Define id.i
  Define *n.AvkIrNode
  i = 0
  While i < 193 : avkShIrLive[i] = 0 : i = i + 1 : Wend
  If rootId > 0 And rootId < 193 : avkShIrLive[rootId] = 1 : EndIf
  changed = 1
  While changed <> 0
    changed = 0
    i = 0
    While i < *m\nodeCount
      *n = avkIrNodeAt(*m, i)
      If *n\sourceId > 0 And *n\sourceId < 193 And avkShIrLive[*n\sourceId] <> 0
        k = 0
        While k < *n\operandCount
          id = avkIrOperand(*n, k)
          If id > 0 And id < 193 And avkShIrLive[id] = 0
            avkShIrLive[id] = 1
            changed = 1
          EndIf
          k = k + 1
        Wend
      EndIf
      i = i + 1
    Wend
  Wend
EndProcedure

; Derive the fragment interface and every runtime resource independently from
; immutable typed IR. Arithmetic can combine a varying with one resource, so
; an exclusive "colour source" is insufficient for correctness.
Procedure.i avkShIrSummarizeFragment(slot.i)
  Define *m.AvkIrModule = @avkShIr[slot]\module
  Define *v.AvkIrVariable
  Define *n.AvkIrNode
  Define *load.AvkIrNode
  Define *c.AvkIrConstant
  Define *lane.AvkIrConstant
  Define i.i
  Define k.i
  Define location.i
  Define comps.i
  Define variableId.i
  Define member.i
  Define valueId.i
  Define outputVariableId.i
  Define base.i

  avkShInCount[slot] = 0
  avkShOutCount[slot] = 0
  avkShPosAttr[slot] = -1
  avkShColourSrc[slot] = #ANVIL_SPV_COLOUR_IR
  avkShColourIdx[slot] = -1
  avkShPush[slot] = 0
  avkShUniform[slot] = 0
  avkShUniformSet[slot] = -1
  avkShUniformBinding[slot] = -1
  avkShSample[slot] = 0
  avkShSampleSet[slot] = -1
  avkShSampleBinding[slot] = -1
  avkShSampleCoord[slot] = -1
  avkShUsesVarying[slot] = 0
  base = slot * #ANVIL_SPV_MAX_ATTRS
  k = 0
  While k < #ANVIL_SPV_MAX_ATTRS
    avkShInComp[base + k] = 0
    k = k + 1
  Wend
  base = slot * #ANVIL_SPV_MAX_VARYINGS
  k = 0
  While k < #ANVIL_SPV_MAX_VARYINGS
    avkShOutComp[base + k] = 0
    avkShOutSrc[base + k] = -1
    k = k + 1
  Wend
  base = slot * 4
  k = 0
  While k < 4
    avkShConst[base + k] = 0
    k = k + 1
  Wend

  ; The executable interface is rooted at the sole final Store value. SPIR-V
  ; may legally retain declared inputs and dead loads which do not contribute
  ; to that value; advertising those dead inputs to the backend would make its
  ; strict target validation reject an otherwise unchanged legacy shader.
  i = 0 : valueId = 0 : outputVariableId = 0
  While i < *m\nodeCount
    *n = avkIrNodeAt(*m, i)
    If *n\kind = #ANVIL_IR_OP_STORE
      valueId = *n\operand1
      member = -1
      avkShIrPointerSelection(*m, *n\operand0, @outputVariableId, @member)
    EndIf
    i = i + 1
  Wend
  avkShIrBuildLive(*m, valueId)

  i = 0
  While i < *m\variableCount
    *v = avkIrVariableAt(*m, i)
    location = avkShIrDecoration(*m, *v\sourceId, #ANVIL_IR_DEC_LOCATION)
    If location >= 0
      comps = avkShIrComponents(*m, *v\sourceId)
      If comps < 1 Or location >= #ANVIL_SPV_MAX_ATTRS
        ProcedureReturn #ANVIL_VK_ERR_UNSUPPORTED
      EndIf
      If *v\storageClass = #ANVIL_IR_STORAGE_INPUT And avkShIrLive[*v\sourceId] <> 0
        avkShInComp[(slot * #ANVIL_SPV_MAX_ATTRS) + location] = comps
        If avkShInCount[slot] < location + 1 : avkShInCount[slot] = location + 1 : EndIf
      ElseIf *v\storageClass = #ANVIL_IR_STORAGE_OUTPUT And *v\sourceId = outputVariableId
        avkShOutComp[(slot * #ANVIL_SPV_MAX_VARYINGS) + location] = comps
        If avkShOutCount[slot] < location + 1 : avkShOutCount[slot] = location + 1 : EndIf
      EndIf
    EndIf
    i = i + 1
  Wend

  ; Live loads name push/uniform use. A sampled image is counted only by the sample
  ; operation, not merely because its semantic handle was loaded.
  i = 0
  While i < *m\nodeCount
    *n = avkIrNodeAt(*m, i)
    If *n\sourceId > 0 And avkShIrLive[*n\sourceId] <> 0 And *n\kind = #ANVIL_IR_OP_LOAD
      variableId = 0 : member = -1
      If avkShIrPointerSelection(*m, *n\operand0, @variableId, @member) <> 0
        *v = avkIrFindVariable(*m, variableId)
        If *v <> 0 And *v\storageClass = #ANVIL_IR_STORAGE_PUSH_CONSTANT
          If avkShIrBlockSelectionValid(*m, variableId, member) = 0 : ProcedureReturn #ANVIL_VK_ERR_UNSUPPORTED : EndIf
          avkShPush[slot] = 1
        ElseIf *v <> 0 And *v\storageClass = #ANVIL_IR_STORAGE_UNIFORM
          If avkShIrBlockSelectionValid(*m, variableId, member) = 0 : ProcedureReturn #ANVIL_VK_ERR_UNSUPPORTED : EndIf
          avkShUniform[slot] = 1
          avkShUniformSet[slot] = avkShIrDecoration(*m, variableId, #ANVIL_IR_DEC_DESCRIPTOR_SET)
          avkShUniformBinding[slot] = avkShIrDecoration(*m, variableId, #ANVIL_IR_DEC_BINDING)
        ElseIf *v <> 0 And *v\storageClass = #ANVIL_IR_STORAGE_INPUT
          avkShUsesVarying[slot] = 1
        EndIf
      EndIf
    ElseIf *n\sourceId > 0 And avkShIrLive[*n\sourceId] <> 0 And *n\kind = #ANVIL_IR_OP_IMAGE_SAMPLE_IMPLICIT_LOD
      avkShSample[slot] = 1
      *load = avkIrFindNode(*m, *n\operand0)
      If *load = 0 Or *load\kind <> #ANVIL_IR_OP_LOAD
        ProcedureReturn #ANVIL_VK_ERR_UNSUPPORTED
      EndIf
      variableId = 0 : member = -1
      If avkShIrPointerSelection(*m, *load\operand0, @variableId, @member) = 0
        ProcedureReturn #ANVIL_VK_ERR_UNSUPPORTED
      EndIf
      avkShSampleSet[slot] = avkShIrDecoration(*m, variableId, #ANVIL_IR_DEC_DESCRIPTOR_SET)
      avkShSampleBinding[slot] = avkShIrDecoration(*m, variableId, #ANVIL_IR_DEC_BINDING)
      *load = avkIrFindNode(*m, *n\operand1)
      If *load = 0 Or *load\kind <> #ANVIL_IR_OP_LOAD
        ProcedureReturn #ANVIL_VK_ERR_UNSUPPORTED
      EndIf
      variableId = 0 : member = -1
      If avkShIrPointerSelection(*m, *load\operand0, @variableId, @member) = 0
        ProcedureReturn #ANVIL_VK_ERR_UNSUPPORTED
      EndIf
      avkShSampleCoord[slot] = avkShIrInputIndex(*m, variableId)
    EndIf
    i = i + 1
  Wend

  ; Preserve the five observable legacy source names only when the final store
  ; is exactly that shape. A computed graph is #ANVIL_SPV_COLOUR_IR even when
  ; it happens to read one of the same resources.
  *n = avkIrFindNode(*m, valueId)
  If *n <> 0 And *n\kind = #ANVIL_IR_OP_LOAD
    variableId = 0 : member = -1
    If avkShIrPointerSelection(*m, *n\operand0, @variableId, @member) <> 0
      *v = avkIrFindVariable(*m, variableId)
      If *v <> 0 And *v\storageClass = #ANVIL_IR_STORAGE_INPUT
        avkShColourSrc[slot] = #ANVIL_SPV_COLOUR_VARYING
        avkShColourIdx[slot] = avkShIrInputIndex(*m, variableId)
      ElseIf *v <> 0 And *v\storageClass = #ANVIL_IR_STORAGE_PUSH_CONSTANT
        avkShColourSrc[slot] = #ANVIL_SPV_COLOUR_PUSH
        avkShColourIdx[slot] = 0
      ElseIf *v <> 0 And *v\storageClass = #ANVIL_IR_STORAGE_UNIFORM
        avkShColourSrc[slot] = #ANVIL_SPV_COLOUR_UNIFORM
        avkShColourIdx[slot] = 0
      EndIf
    EndIf
  ElseIf *n <> 0 And *n\kind = #ANVIL_IR_OP_IMAGE_SAMPLE_IMPLICIT_LOD
    avkShColourSrc[slot] = #ANVIL_SPV_COLOUR_SAMPLED
    avkShColourIdx[slot] = avkShSampleCoord[slot]
  Else
    *c = avkIrFindConstant(*m, valueId)
    If *c <> 0 And *c\componentCount = 4
      avkShColourSrc[slot] = #ANVIL_SPV_COLOUR_CONST
      k = 0
      While k < 4
        *lane = avkIrFindConstant(*m, avkIrConstantComponent(*c, k))
        If *lane = 0 Or *lane\wordCount <> 1 : ProcedureReturn #ANVIL_VK_ERR_UNSUPPORTED : EndIf
        avkShConst[(slot * 4) + k] = *lane\word0
        k = k + 1
      Wend
    EndIf
  EndIf
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkShaderModuleCreate(device.i, *code, bytes.i, *out)
  Define d.i
  Define s.i
  Define rc.i
  Define k.i
  Define base.i
  If *out = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, #VK_NULL_HANDLE)
  d = avkDevSlot(device)
  If d = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  rc = AnvilVkSpirvWalkIr(*code, bytes)
  If rc <> #ANVIL_VK_OK : ProcedureReturn rc : EndIf
  s = 1
  While s <= #ANVIL_VK_MAX_SHADER_MODULES And avkShLive[s] <> 0 : s = s + 1 : Wend
  If s > #ANVIL_VK_MAX_SHADER_MODULES : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf
  rc = AnvilVkSpirvIrAdapt(@avkShIr[s])
  If rc <> #ANVIL_IR_OK
    ProcedureReturn avkFault(#VK_ERROR_INITIALIZATION_FAILED, "vkCreateShaderModule could not retain the accepted SPIR-V as verified typed IR (VkResult -3, VK_ERROR_INITIALIZATION_FAILED); no shader module was published and the adapter's last-error fields identify the semantic record that failed.")
  EndIf
  avkShGen[s] = avkNextGen(avkShGen[s])
  avkShDev[s] = d
  If avkShIr[s]\module\stage = #ANVIL_IR_STAGE_VERTEX
    avkShStage[s] = 0
  Else
    avkShStage[s] = 4
  EndIf
  avkShWords[s] = bytes / 4
  avkShInstr[s] = AnvilVkSpirvInstructions()
  avkShInCount[s] = AnvilVkSpirvInputCount()
  avkShOutCount[s] = AnvilVkSpirvOutputCount()
  avkShPosAttr[s] = AnvilVkSpirvPositionAttr()
  avkShColourSrc[s] = AnvilVkSpirvColourSource()
  avkShColourIdx[s] = AnvilVkSpirvColourIndex()
  avkShPush[s] = AnvilVkSpirvUsesPushConstants()
  avkShUniform[s] = AnvilVkSpirvUsesUniformBlock()
  avkShUniformSet[s] = AnvilVkSpirvUniformSet()
  avkShUniformBinding[s] = AnvilVkSpirvUniformBinding()
  avkShSample[s] = AnvilVkSpirvUsesSampledImage()
  avkShSampleSet[s] = AnvilVkSpirvSampleSet()
  avkShSampleBinding[s] = AnvilVkSpirvSampleBinding()
  avkShSampleCoord[s] = AnvilVkSpirvSampleCoordInput()
  base = s * #ANVIL_SPV_MAX_ATTRS
  k = 0
  While k < #ANVIL_SPV_MAX_ATTRS
    avkShInComp[base + k] = AnvilVkSpirvInputComponents(k)
    k = k + 1
  Wend
  base = s * #ANVIL_SPV_MAX_VARYINGS
  k = 0
  While k < #ANVIL_SPV_MAX_VARYINGS
    avkShOutComp[base + k] = AnvilVkSpirvOutputComponents(k)
    avkShOutSrc[base + k] = AnvilVkSpirvOutputSourceAttr(k)
    k = k + 1
  Wend
  base = s * 4
  k = 0
  While k < 4
    avkShConst[base + k] = AnvilVkSpirvColourConstant(k)
    k = k + 1
  Wend
  If avkShIr[s]\module\stage = #ANVIL_IR_STAGE_FRAGMENT
    rc = avkShIrSummarizeFragment(s)
    If rc <> #VK_SUCCESS
      avkShIr[s]\valid = 0
      ProcedureReturn avkFault(#VK_ERROR_INITIALIZATION_FAILED, "vkCreateShaderModule could not derive a complete fragment interface and resource summary from verified typed IR (VkResult -3, VK_ERROR_INITIALIZATION_FAILED); no shader module was published.")
    EndIf
  EndIf
  avkShIrGen[s] = avkShGen[s]
  avkShLive[s] = 1
  PokeI(*out, avkToken(#ANVIL_VK_TYPE_SHADER_MODULE, s, avkShGen[s]))
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure AnvilVkShaderModuleDestroy(device.i, module.i)
  Define d.i
  Define s.i
  d = avkDevSlot(device)
  s = avkShSlot(module)
  If s = 0
    If module <> #VK_NULL_HANDLE
      avkFault(#ANVIL_VK_ERR_HANDLE, "vkDestroyShaderModule was given a VkShaderModule handle that is not live on this device (Anvil code -20002, stale or foreign handle); nothing was destroyed.")
    EndIf
    ProcedureReturn
  EndIf
  If d = 0 Or avkShDev[s] <> d
    avkFault(#ANVIL_VK_ERR_OWNER, "vkDestroyShaderModule was called with a device that does not own this module (Anvil code -20003, wrong parent); nothing was destroyed.")
    ProcedureReturn
  EndIf
  avkShIr[s]\valid = 0
  avkShIrGen[s] = 0
  avkShLive[s] = 0
EndProcedure

Procedure.i AnvilVkShaderModuleIr(module.i)
  Define s.i = avkShSlot(module)
  If s = 0 : ProcedureReturn 0 : EndIf
  If avkShIrGen[s] <> avkShGen[s] Or avkShIr[s]\valid = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn @avkShIr[s]\module
EndProcedure

Procedure.i AnvilVkShaderModuleIrGeneration(module.i)
  Define s.i = avkShSlot(module)
  If s = 0 Or avkShIr[s]\valid = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkShIrGen[s]
EndProcedure

Procedure.i AnvilVkShaderModuleStage(module.i)
  Define s.i
  s = avkShSlot(module)
  If s = 0 : ProcedureReturn -1 : EndIf
  ProcedureReturn avkShStage[s]
EndProcedure

Procedure.i AnvilVkShaderModuleInstructions(module.i)
  Define s.i
  s = avkShSlot(module)
  If s = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkShInstr[s]
EndProcedure

; ======================================================================
;  PIPELINE LAYOUT
; ======================================================================
Procedure.i AnvilVkPipelineLayoutCreate(device.i, setCount.i, *setLayouts, pushCount.i, *ranges.VkPushConstantRange, *out)
  Define d.i
  Define s.i
  Define bytes.i
  Define dsl.i
  Define bindingCount.i
  Define k.i
  If *out = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, #VK_NULL_HANDLE)
  d = avkDevSlot(device)
  If d = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  dsl = 0
  If setCount < 0 Or setCount > 1
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreatePipelineLayout was given more than one descriptor set layout (Anvil code -20005, unsupported layout); vkCmdBindDescriptorSets binds one set here and its index is zero, so a second set layout would declare bindings nothing could ever supply.")
  EndIf
  If setCount = 1
    If *setLayouts = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
    dsl = PeekI(*setLayouts)
    bindingCount = AnvilVkSetLayoutBindingCountOf(dsl)
    If bindingCount < 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
    If AnvilVkSetLayoutDeviceSlotOf(dsl) <> d
      ProcedureReturn avkFault(#ANVIL_VK_ERR_OWNER, "vkCreatePipelineLayout was given a descriptor set layout from a different VkDevice (Anvil code -20003, wrong parent); no pipeline layout was created.")
    EndIf
  EndIf
  bytes = 0
  If pushCount > 1
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreatePipelineLayout was given more than one push constant range (Anvil code -20005, unsupported layout); this slice carries one range, in the fragment stage, at offset zero.")
  EndIf
  If pushCount = 1
    If *ranges = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
    If (*ranges\stageFlags & $FFFFFFFF) <> #VK_SHADER_STAGE_FRAGMENT_BIT
      ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreatePipelineLayout was given a push constant range for a stage other than the fragment stage alone (Anvil code -20005, unsupported layout); the uniform colour this slice lowers is read by the fragment shader, and the vertex shader has no uniform path.")
    EndIf
    If (*ranges\offset & $FFFFFFFF) <> 0 Or (*ranges\size & $FFFFFFFF) <> #ANVIL_VK_PUSH_BYTES
      ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreatePipelineLayout was given a push constant range that is not sixteen bytes at offset zero (Anvil code -20005, unsupported layout); the one push-constant block this slice supplies is a four-component colour at offset zero.")
    EndIf
    bytes = #ANVIL_VK_PUSH_BYTES
  EndIf
  s = 1
  While s <= #ANVIL_VK_MAX_LAYOUTS And avkLayLive[s] <> 0 : s = s + 1 : Wend
  If s > #ANVIL_VK_MAX_LAYOUTS : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf
  avkLayGen[s] = avkNextGen(avkLayGen[s])
  avkLayDev[s] = d
  avkLayPushBytes[s] = bytes
  avkLaySetCount[s] = setCount
  avkLayBindingCount[s] = bindingCount
  k = 0
  While k < #ANVIL_VK_MAX_SET_BINDINGS
    avkLayBindingType[(s * #ANVIL_VK_MAX_SET_BINDINGS) + k] = -1
    avkLayBindingStages[(s * #ANVIL_VK_MAX_SET_BINDINGS) + k] = 0
    If k < bindingCount
      avkLayBindingType[(s * #ANVIL_VK_MAX_SET_BINDINGS) + k] = AnvilVkSetLayoutBindingTypeOf(dsl, k)
      avkLayBindingStages[(s * #ANVIL_VK_MAX_SET_BINDINGS) + k] = AnvilVkSetLayoutBindingStagesOf(dsl, k)
    EndIf
    k = k + 1
  Wend
  avkLayLive[s] = 1
  PokeI(*out, avkToken(#ANVIL_VK_TYPE_PIPELINE_LAYOUT, s, avkLayGen[s]))
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure AnvilVkPipelineLayoutDestroy(device.i, layout.i)
  Define d.i
  Define s.i
  d = avkDevSlot(device)
  s = avkLaySlot(layout)
  If s = 0
    If layout <> #VK_NULL_HANDLE
      avkFault(#ANVIL_VK_ERR_HANDLE, "vkDestroyPipelineLayout was given a VkPipelineLayout handle that is not live on this device (Anvil code -20002, stale or foreign handle); nothing was destroyed.")
    EndIf
    ProcedureReturn
  EndIf
  If d = 0 Or avkLayDev[s] <> d
    avkFault(#ANVIL_VK_ERR_OWNER, "vkDestroyPipelineLayout was called with a device that does not own this layout (Anvil code -20003, wrong parent); nothing was destroyed.")
    ProcedureReturn
  EndIf
  avkLayLive[s] = 0
EndProcedure

Procedure.i avkLayHasBinding(lay.i, binding.i, descriptorType.i)
  If lay < 1 Or lay > #ANVIL_VK_MAX_LAYOUTS Or avkLayLive[lay] = 0 : ProcedureReturn 0 : EndIf
  If binding < 0 Or binding >= avkLayBindingCount[lay] : ProcedureReturn 0 : EndIf
  If avkLayBindingType[(lay * #ANVIL_VK_MAX_SET_BINDINGS) + binding] <> descriptorType : ProcedureReturn 0 : EndIf
  If avkLayBindingStages[(lay * #ANVIL_VK_MAX_SET_BINDINGS) + binding] <> #VK_SHADER_STAGE_FRAGMENT_BIT : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i avkSetMatchesLayout(set.i, lay.i)
  Define k.i
  If AnvilVkDescriptorSetSchemaCount(set) <> avkLayBindingCount[lay] : ProcedureReturn 0 : EndIf
  k = 0
  While k < avkLayBindingCount[lay]
    If AnvilVkDescriptorSetSchemaType(set, k) <> avkLayBindingType[(lay * #ANVIL_VK_MAX_SET_BINDINGS) + k] : ProcedureReturn 0 : EndIf
    If AnvilVkDescriptorSetSchemaStages(set, k) <> avkLayBindingStages[(lay * #ANVIL_VK_MAX_SET_BINDINGS) + k] : ProcedureReturn 0 : EndIf
    k = k + 1
  Wend
  ProcedureReturn 1
EndProcedure

Procedure.i avkCbMatchesPipe(c.i, p.i)
  Define k.i
  If avkCbDescSetCount[c] <> avkPipeSetCount[p] Or avkCbDescBindingCount[c] <> avkPipeBindingCount[p] Or avkCbDescPushBytes[c] <> avkPipePushBytes[p] : ProcedureReturn 0 : EndIf
  k = 0
  While k < avkPipeBindingCount[p]
    If avkCbDescType[(c * #ANVIL_VK_MAX_SET_BINDINGS) + k] <> avkPipeBindingType[(p * #ANVIL_VK_MAX_SET_BINDINGS) + k] : ProcedureReturn 0 : EndIf
    If avkCbDescStages[(c * #ANVIL_VK_MAX_SET_BINDINGS) + k] <> avkPipeBindingStages[(p * #ANVIL_VK_MAX_SET_BINDINGS) + k] : ProcedureReturn 0 : EndIf
    k = k + 1
  Wend
  ProcedureReturn 1
EndProcedure

; ======================================================================
;  RENDER PASS
; ======================================================================
Procedure.i AnvilVkRenderPassCreate(device.i, *att.VkAttachmentDescription, *sub.VkSubpassDescription, *out)
  Define d.i
  Define s.i
  Define ref.i
  If *out = 0 Or *att = 0 Or *sub = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, #VK_NULL_HANDLE)
  d = avkDevSlot(device)
  If d = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If (*att\format & $FFFFFFFF) <> #VK_FORMAT_B8G8R8A8_UNORM
    ProcedureReturn avkFault(#VK_ERROR_FORMAT_NOT_SUPPORTED, "vkCreateRenderPass was given a colour attachment in a format this implementation does not render (VkResult -11, VK_ERROR_FORMAT_NOT_SUPPORTED); the only attachment format Anvil implements is VK_FORMAT_B8G8R8A8_UNORM, which is the format the display scans.")
  EndIf
  If (*att\samples & $FFFFFFFF) <> #VK_SAMPLE_COUNT_1_BIT
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateRenderPass was given a multisampled colour attachment (Anvil code -20005, multisampling not implemented); the render target this backend configures has one sample per pixel and there is no resolve path.")
  EndIf
  If (*att\loadOp & $FFFFFFFF) <> #VK_ATTACHMENT_LOAD_OP_CLEAR
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateRenderPass was given a colour attachment whose loadOp is not VK_ATTACHMENT_LOAD_OP_CLEAR (Anvil code -20005, unsupported load operation); this backend begins every frame by clearing the tile buffer, so LOAD would need a tile load this slice does not emit and DONT_CARE would leave the tile holding whatever the last frame left.")
  EndIf
  If (*att\storeOp & $FFFFFFFF) <> #VK_ATTACHMENT_STORE_OP_STORE
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateRenderPass was given a colour attachment whose storeOp is not VK_ATTACHMENT_STORE_OP_STORE (Anvil code -20005, unsupported store operation); a render pass that does not store its colour would produce nothing a reader could check.")
  EndIf
  If (*att\initialLayout & $FFFFFFFF) <> #VK_IMAGE_LAYOUT_UNDEFINED
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateRenderPass was given a colour attachment whose initialLayout is not VK_IMAGE_LAYOUT_UNDEFINED (Anvil code -20005, unsupported layout); the loadOp is CLEAR, so the previous contents are discarded and the only honest initial layout is UNDEFINED.")
  EndIf
  If (*att\finalLayout & $FFFFFFFF) <> #VK_IMAGE_LAYOUT_GENERAL And (*att\finalLayout & $FFFFFFFF) <> #VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateRenderPass was given a colour attachment whose finalLayout is neither VK_IMAGE_LAYOUT_GENERAL nor VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL (Anvil code -20005, unsupported layout); there is no swapchain here, so PRESENT_SRC does not exist, and those two are the layouts a host readback or a copy can follow.")
  EndIf
  If (*sub\pipelineBindPoint & $FFFFFFFF) <> #VK_PIPELINE_BIND_POINT_GRAPHICS
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateRenderPass was given a subpass whose bind point is not VK_PIPELINE_BIND_POINT_GRAPHICS (Anvil code -20005, unsupported bind point); there is no compute pipeline in this implementation.")
  EndIf
  If (*sub\colorAttachmentCount & $FFFFFFFF) <> 1 Or *sub\pColorAttachments = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateRenderPass was given a subpass that does not have exactly one colour attachment (Anvil code -20005, unsupported subpass); this slice renders to one target, so a subpass must name one and only one.")
  EndIf
  If *sub\pDepthStencilAttachment <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateRenderPass was given a subpass with a depth-stencil attachment (Anvil code -20005, depth and stencil not implemented); there is no depth buffer in this pipeline and the emitted shader record turns depth off.")
  EndIf
  If (*sub\inputAttachmentCount & $FFFFFFFF) <> 0 Or *sub\pResolveAttachments <> 0 Or (*sub\preserveAttachmentCount & $FFFFFFFF) <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateRenderPass was given a subpass with input, resolve or preserve attachments (Anvil code -20005, unsupported subpass); one subpass writing one colour attachment is the whole of what this slice renders.")
  EndIf
  ref = PeekL(*sub\pColorAttachments) & $FFFFFFFF
  If ref <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateRenderPass was given a colour attachment reference that does not name attachment zero (Anvil code -20001, invalid attachment reference); there is one attachment in this render pass and its index is zero.")
  EndIf
  ref = PeekL(*sub\pColorAttachments + 4) & $FFFFFFFF
  If ref <> #VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL And ref <> #VK_IMAGE_LAYOUT_GENERAL
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateRenderPass was given a colour attachment reference in a layout a colour attachment may not be used in (Anvil code -20001, wrong layout); the specification permits VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL and VK_IMAGE_LAYOUT_GENERAL here.")
  EndIf
  s = 1
  While s <= #ANVIL_VK_MAX_RENDER_PASSES And avkRpLive[s] <> 0 : s = s + 1 : Wend
  If s > #ANVIL_VK_MAX_RENDER_PASSES : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf
  avkRpGen[s] = avkNextGen(avkRpGen[s])
  avkRpLive[s] = 1
  avkRpDev[s] = d
  avkRpFormat[s] = *att\format & $FFFFFFFF
  avkRpFinalLayout[s] = *att\finalLayout & $FFFFFFFF
  PokeI(*out, avkToken(#ANVIL_VK_TYPE_RENDER_PASS, s, avkRpGen[s]))
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure AnvilVkRenderPassDestroy(device.i, renderPass.i)
  Define d.i
  Define s.i
  d = avkDevSlot(device)
  s = avkRpSlot(renderPass)
  If s = 0
    If renderPass <> #VK_NULL_HANDLE
      avkFault(#ANVIL_VK_ERR_HANDLE, "vkDestroyRenderPass was given a VkRenderPass handle that is not live on this device (Anvil code -20002, stale or foreign handle); nothing was destroyed.")
    EndIf
    ProcedureReturn
  EndIf
  If d = 0 Or avkRpDev[s] <> d
    avkFault(#ANVIL_VK_ERR_OWNER, "vkDestroyRenderPass was called with a device that does not own this render pass (Anvil code -20003, wrong parent); nothing was destroyed.")
    ProcedureReturn
  EndIf
  If avkRpInFlight[s] <> 0
    avkFault(#ANVIL_VK_ERR_STATE, "vkDestroyRenderPass was called while one or more submitted draws still use this render pass (Anvil code -20004, resource in use); nothing was destroyed. Wait on the submission's fence, or call vkDeviceWaitIdle, first.")
    ProcedureReturn
  EndIf
  avkRpLive[s] = 0
EndProcedure

; ======================================================================
;  IMAGE VIEW and FRAMEBUFFER
; ======================================================================
Procedure.i AnvilVkImageViewCreate(device.i, image.i, viewType.i, format.i, *out)
  Define d.i
  Define s.i
  Define img.i
  If *out = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, #VK_NULL_HANDLE)
  d = avkDevSlot(device)
  img = avkImgSlot(image)
  If d = 0 Or img = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkImgDev[img] <> d
    ProcedureReturn avkFault(#ANVIL_VK_ERR_OWNER, "vkCreateImageView was given an image that belongs to a different VkDevice (Anvil code -20003, wrong parent); create the view on the device that created the image.")
  EndIf
  If viewType <> #VK_IMAGE_VIEW_TYPE_2D
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateImageView was asked for a view type other than VK_IMAGE_VIEW_TYPE_2D (Anvil code -20005, unsupported view type); every image this implementation creates is a single-layer two-dimensional image.")
  EndIf
  If format <> #VK_FORMAT_B8G8R8A8_UNORM
    ProcedureReturn avkFault(#VK_ERROR_FORMAT_NOT_SUPPORTED, "vkCreateImageView was asked for a format other than VK_FORMAT_B8G8R8A8_UNORM (VkResult -11, VK_ERROR_FORMAT_NOT_SUPPORTED); a view may not reinterpret an image's format here, so it must name the format the image was created with.")
  EndIf
  s = 1
  While s <= #ANVIL_VK_MAX_IMAGE_VIEWS And avkIvLive[s] <> 0 : s = s + 1 : Wend
  If s > #ANVIL_VK_MAX_IMAGE_VIEWS : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf
  avkIvGen[s] = avkNextGen(avkIvGen[s])
  avkIvLive[s] = 1
  avkIvDev[s] = d
  avkIvImage[s] = image
  avkIvImgSlot[s] = img
  avkIvInFlight[s] = 0
  PokeI(*out, avkToken(#ANVIL_VK_TYPE_IMAGE_VIEW, s, avkIvGen[s]))
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure AnvilVkImageViewDestroy(device.i, view.i)
  Define d.i
  Define s.i
  d = avkDevSlot(device)
  s = avkIvSlot(view)
  If s = 0
    If view <> #VK_NULL_HANDLE
      avkFault(#ANVIL_VK_ERR_HANDLE, "vkDestroyImageView was given a VkImageView handle that is not live on this device (Anvil code -20002, stale or foreign handle); nothing was destroyed.")
    EndIf
    ProcedureReturn
  EndIf
  If d = 0 Or avkIvDev[s] <> d
    avkFault(#ANVIL_VK_ERR_OWNER, "vkDestroyImageView was called with a device that does not own this view (Anvil code -20003, wrong parent); nothing was destroyed.")
    ProcedureReturn
  EndIf
  If avkIvInFlight[s] <> 0
    avkFault(#ANVIL_VK_ERR_STATE, "vkDestroyImageView was called while a submission is using it as an attachment or sampled view (Anvil code -20004, resource in use); wait for the submission fence or call vkDeviceWaitIdle before destroying it.")
    ProcedureReturn
  EndIf
  avkIvLive[s] = 0
EndProcedure

Procedure.i AnvilVkFramebufferCreate(device.i, renderPass.i, view.i, width.i, height.i, layers.i, *out)
  Define d.i
  Define s.i
  Define rp.i
  Define iv.i
  Define img.i
  If *out = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, #VK_NULL_HANDLE)
  d = avkDevSlot(device)
  rp = avkRpSlot(renderPass)
  iv = avkIvSlot(view)
  If d = 0 Or rp = 0 Or iv = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkRpDev[rp] <> d Or avkIvDev[iv] <> d
    ProcedureReturn avkFault(#ANVIL_VK_ERR_OWNER, "vkCreateFramebuffer was given a render pass or an attachment view from a different VkDevice (Anvil code -20003, wrong parent); every object in a framebuffer must share one device.")
  EndIf
  If layers <> 1
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateFramebuffer was asked for more than one layer (Anvil code -20005, layered rendering not implemented); every image here has one array layer.")
  EndIf
  img = avkImgSlot(avkIvImage[iv])
  If img = 0 Or img <> avkIvImgSlot[iv]
    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkCreateFramebuffer was given an image view whose image has since been destroyed or replaced (Anvil code -20004, stale image-view dependency); create a new view from the current live image first.")
  EndIf
  If width <> avkImgW[img] Or height <> avkImgH[img]
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateFramebuffer was given a width or height that is not the attachment image's own extent (Anvil code -20001, framebuffer does not match its attachment); a smaller framebuffer over a larger image would render into part of it, and this backend renders the whole render target at one geometry.")
  EndIf
  If (avkImgUsage[img] & #VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT) = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateFramebuffer was given an attachment image that was not created with VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT (Anvil code -20001, missing usage); rendering through a framebuffer writes a colour attachment, while transfer usages authorize only transfer commands.")
  EndIf
  s = 1
  While s <= #ANVIL_VK_MAX_FRAMEBUFFERS And avkFbLive[s] <> 0 : s = s + 1 : Wend
  If s > #ANVIL_VK_MAX_FRAMEBUFFERS : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf
  avkFbGen[s] = avkNextGen(avkFbGen[s])
  avkFbDev[s] = d
  avkFbRp[s] = rp
  avkFbRpHandle[s] = renderPass
  avkFbView[s] = iv
  avkFbViewHandle[s] = view
  avkFbW[s] = width
  avkFbH[s] = height
  avkFbLive[s] = 1
  PokeI(*out, avkToken(#ANVIL_VK_TYPE_FRAMEBUFFER, s, avkFbGen[s]))
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure AnvilVkFramebufferDestroy(device.i, framebuffer.i)
  Define d.i
  Define s.i
  d = avkDevSlot(device)
  s = avkFbSlot(framebuffer)
  If s = 0
    If framebuffer <> #VK_NULL_HANDLE
      avkFault(#ANVIL_VK_ERR_HANDLE, "vkDestroyFramebuffer was given a VkFramebuffer handle that is not live on this device (Anvil code -20002, stale or foreign handle); nothing was destroyed.")
    EndIf
    ProcedureReturn
  EndIf
  If d = 0 Or avkFbDev[s] <> d
    avkFault(#ANVIL_VK_ERR_OWNER, "vkDestroyFramebuffer was called with a device that does not own this framebuffer (Anvil code -20003, wrong parent); nothing was destroyed.")
    ProcedureReturn
  EndIf
  If avkFbInFlight[s] <> 0
    avkFault(#ANVIL_VK_ERR_STATE, "vkDestroyFramebuffer was called while a submitted command buffer still uses this framebuffer (Anvil code -20004, resource in use); nothing was destroyed. Wait on the submission's fence, or call vkDeviceWaitIdle, first.")
    ProcedureReturn
  EndIf
  avkFbLive[s] = 0
EndProcedure

; ======================================================================
;  THE GRAPHICS PIPELINE
; ======================================================================

; How many components a vertex-attribute format carries, or 0 when this
; implementation does not fetch it.
Procedure.i avkFormatComponents(fmt.i)
  If fmt = #VK_FORMAT_R32G32_SFLOAT : ProcedureReturn 2 : EndIf
  If fmt = #VK_FORMAT_R32G32B32_SFLOAT : ProcedureReturn 3 : EndIf
  If fmt = #VK_FORMAT_R32G32B32A32_SFLOAT : ProcedureReturn 4 : EndIf
  ProcedureReturn 0
EndProcedure

; The fixed-function state this slice accepts, checked one create-info at
; a time so a refusal names the structure the caller has to look at.
Procedure.i avkPipeCheckInputAssembly(*ia.VkPipelineInputAssemblyStateCreateInfo)
  If *ia = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given no pInputAssemblyState (Anvil code -20001, missing state); a graphics pipeline that rasterises must declare its primitive topology.")
  EndIf
  If (*ia\sType & $FFFFFFFF) <> #VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a VkPipelineInputAssemblyStateCreateInfo whose sType is wrong (Anvil code -20001, wrong sType).")
  EndIf
  If (*ia\topology & $FFFFFFFF) <> #VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was asked for a primitive topology other than VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST (Anvil code -20005, unsupported topology); the one primitive mode this slice writes into the control list is a triangle list, and a strip or a fan would change the vertex order the binner reads.")
  EndIf
  If (*ia\primitiveRestartEnable & $FFFFFFFF) <> #VK_FALSE
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was asked for primitive restart (Anvil code -20005, unsupported state); primitive restart only has meaning for an indexed draw, and there is no index buffer here.")
  EndIf
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkPipeCheckRasterization(*rs.VkPipelineRasterizationStateCreateInfo)
  If *rs = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given no pRasterizationState (Anvil code -20001, missing state); a graphics pipeline must declare it.")
  EndIf
  If (*rs\sType & $FFFFFFFF) <> #VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a VkPipelineRasterizationStateCreateInfo whose sType is wrong (Anvil code -20001, wrong sType).")
  EndIf
  If (*rs\depthClampEnable & $FFFFFFFF) <> #VK_FALSE Or (*rs\rasterizerDiscardEnable & $FFFFFFFF) <> #VK_FALSE
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was asked for depth clamp or rasteriser discard (Anvil code -20005, unsupported state); neither is emitted into the control list, so enabling one would change nothing and the picture would not match what was asked for.")
  EndIf
  If (*rs\polygonMode & $FFFFFFFF) <> #VK_POLYGON_MODE_FILL
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was asked for a polygon mode other than VK_POLYGON_MODE_FILL (Anvil code -20005, unsupported state); wireframe and point rendering need a different primitive list format than the one this slice writes.")
  EndIf
  If (*rs\cullMode & $FFFFFFFF) <> #VK_CULL_MODE_NONE
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was asked to cull faces (Anvil code -20005, unsupported state); the emitted configuration bits enable both facings, so a culled pipeline would draw triangles the caller asked to be discarded.")
  EndIf
  If (*rs\depthBiasEnable & $FFFFFFFF) <> #VK_FALSE
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was asked for depth bias (Anvil code -20005, unsupported state); there is no depth buffer in this render pass for a bias to apply to.")
  EndIf
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkPipeCheckMultisample(*ms.VkPipelineMultisampleStateCreateInfo, *outMask)
  If *ms = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given no pMultisampleState (Anvil code -20001, missing state); a graphics pipeline must declare it.")
  EndIf
  If (*ms\sType & $FFFFFFFF) <> #VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a VkPipelineMultisampleStateCreateInfo whose sType is wrong (Anvil code -20001, wrong sType).")
  EndIf
  If (*ms\rasterizationSamples & $FFFFFFFF) <> #VK_SAMPLE_COUNT_1_BIT
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was asked for more than one rasterisation sample (Anvil code -20005, multisampling not implemented); the tile configuration this backend writes is single sampled and there is no resolve.")
  EndIf
  If (*ms\sampleShadingEnable & $FFFFFFFF) <> #VK_FALSE Or (*ms\alphaToCoverageEnable & $FFFFFFFF) <> #VK_FALSE Or (*ms\alphaToOneEnable & $FFFFFFFF) <> #VK_FALSE
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was asked for sample shading, alpha to coverage or alpha to one (Anvil code -20005, unsupported state); none of the three is emitted, so enabling one would change nothing at all.")
  EndIf
  PokeI(*outMask, 1)
  If *ms\pSampleMask <> 0
    PokeI(*outMask, PeekL(*ms\pSampleMask) & 1)
  EndIf
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkPipeCheckColorBlend(*cb.VkPipelineColorBlendStateCreateInfo, *outMode)
  Define *a.VkPipelineColorBlendAttachmentState
  If *outMode = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*outMode, #ANVIL_VK_BLEND_DISABLED)
  If *cb = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given no pColorBlendState (Anvil code -20001, missing state); a pipeline with a colour attachment must declare it.")
  EndIf
  If (*cb\sType & $FFFFFFFF) <> #VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a VkPipelineColorBlendStateCreateInfo whose sType is wrong (Anvil code -20001, wrong sType).")
  EndIf
  If (*cb\logicOpEnable & $FFFFFFFF) <> #VK_FALSE
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was asked for a logic operation (Anvil code -20005, unsupported state); no logic op is emitted into the tile configuration.")
  EndIf
  If (*cb\attachmentCount & $FFFFFFFF) <> 1 Or *cb\pAttachments = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a colour blend state that does not describe exactly one attachment (Anvil code -20001, attachment count mismatch); the render pass has one colour attachment, so the blend state must have one too.")
  EndIf
  *a = *cb\pAttachments
  If (*a\colorWriteMask & $FFFFFFFF) <> (#VK_COLOR_COMPONENT_R_BIT | #VK_COLOR_COMPONENT_G_BIT | #VK_COLOR_COMPONENT_B_BIT | #VK_COLOR_COMPONENT_A_BIT)
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was asked to mask out a colour channel (Anvil code -20005, unsupported write mask); every channel is written here, and a partial mask would leave the untouched channels holding the clear value rather than the caller's.")
  EndIf
  If (*a\blendEnable & $FFFFFFFF) = #VK_FALSE
    ProcedureReturn #VK_SUCCESS
  EndIf
  If (*a\blendEnable & $FFFFFFFF) <> #VK_TRUE
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given blendEnable other than VK_FALSE or VK_TRUE (Anvil code -20001, invalid boolean); no pipeline was created.")
  EndIf
  If (*a\srcColorBlendFactor & $FFFFFFFF) <> #VK_BLEND_FACTOR_SRC_ALPHA Or (*a\dstColorBlendFactor & $FFFFFFFF) <> #VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA Or (*a\colorBlendOp & $FFFFFFFF) <> #VK_BLEND_OP_ADD Or (*a\srcAlphaBlendFactor & $FFFFFFFF) <> #VK_BLEND_FACTOR_SRC_ALPHA Or (*a\dstAlphaBlendFactor & $FFFFFFFF) <> #VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA Or (*a\alphaBlendOp & $FFFFFFFF) <> #VK_BLEND_OP_ADD
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was asked for a blend equation other than straight source-over (Anvil code -20005, unsupported blend equation); the supported equation is SRC_ALPHA plus ONE_MINUS_SRC_ALPHA with ADD for both colour and alpha, matching Neon's measured V3D path.")
  EndIf
  If AnvilVkBackendCanBlendSourceOver() = 0
    ProcedureReturn avkFault(#VK_ERROR_FEATURE_NOT_PRESENT, "vkCreateGraphicsPipelines requested straight source-over blending on a backend that does not advertise that operation (VkResult -8, VK_ERROR_FEATURE_NOT_PRESENT); vkGetPhysicalDeviceFormatProperties therefore omits COLOR_ATTACHMENT_BLEND for this device.")
  EndIf
  PokeI(*outMode, #ANVIL_VK_BLEND_SRC_OVER)
  ProcedureReturn #VK_SUCCESS
EndProcedure

; The vertex input state, joined against the vertex shader's own inputs.
; A pipeline whose attributes do not match its shader is refused here,
; which is the one place where both are in view at the same time.
;
; ONE OR MORE BINDINGS, each with its OWN stride. Position in one buffer
; and colour in another is the layout an application that streams one
; attribute and keeps the other static writes, and it is the reason the
; bindings and the attributes are two lists in the specification rather
; than one. Nothing in V3D ever wanted a single base address: every
; attribute record it reads carries an address and a stride of its own.
;
; EVERY REFUSAL BELOW NAMES THE THING IT REFUSED - the binding number,
; the location, the format, the offset - because a caller who has just
; split one buffer into two is looking at eight numbers and needs to be
; told which one is wrong, not that "the vertex input" is.
Procedure.i avkPipeVertexInput(pipe.i, vs.i, *vi.VkPipelineVertexInputStateCreateInfo)
  Define n.i
  Define nb.i
  Define k.i
  Define j.i
  Define loc.i
  Define bidx.i
  Define fmt.i
  Define comps.i
  Define stride.i
  Define *bind.VkVertexInputBindingDescription
  Define *attr.VkVertexInputAttributeDescription
  Define base.i
  Define bbase.i
  Define seen.i
  Define seenBind.i
  Define usedBind.i

  If *vi = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given no pVertexInputState (Anvil code -20001, missing state); a pipeline whose vertex shader reads attributes must declare where they come from.")
  EndIf
  If (*vi\sType & $FFFFFFFF) <> #VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a VkPipelineVertexInputStateCreateInfo whose sType is wrong (Anvil code -20001, wrong sType).")
  EndIf
  nb = *vi\vertexBindingDescriptionCount & $FFFFFFFF
  If nb < 1 Or nb > #ANVIL_VK_MAX_BINDINGS Or *vi\pVertexBindingDescriptions = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was given no vertex input bindings or more than four (Anvil code -20005, unsupported vertex input); this slice reads between one and four vertex buffers, one per binding, because it fetches at most four attributes and refuses a binding no attribute reads.")
  EndIf
  bbase = pipe * #ANVIL_VK_MAX_BINDINGS
  k = 0
  While k < #ANVIL_VK_MAX_BINDINGS
    avkPipeBindStride[bbase + k] = 0
    k = k + 1
  Wend
  seenBind = 0
  k = 0
  While k < nb
    *bind = *vi\pVertexBindingDescriptions + (k * SizeOf(VkVertexInputBindingDescription))
    bidx = *bind\binding & $FFFFFFFF
    If bidx < 0 Or bidx >= nb
      ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was given a vertex input binding whose number is not less than the binding count (Anvil code -20005, unsupported vertex input); the bindings this slice implements are numbered 0 to one less than vertexBindingDescriptionCount, with no gaps, so that vkCmdBindVertexBuffers needs no lookup to find one.")
    EndIf
    If (seenBind & (1 << bidx)) <> 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given two vertex input bindings with the same binding number (Anvil code -20001, duplicate binding); each binding is described exactly once, and a second description of one would silently replace the stride the first declared.")
    EndIf
    seenBind = seenBind | (1 << bidx)
    If (*bind\inputRate & $FFFFFFFF) <> #VK_VERTEX_INPUT_RATE_VERTEX
      ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was given a vertex input binding at VK_VERTEX_INPUT_RATE_INSTANCE (Anvil code -20005, instancing not implemented); vkCmdDraw here takes one instance, so a per-instance attribute would be fetched once and would look like a per-vertex one.")
    EndIf
    stride = *bind\stride & $FFFFFFFF
    If stride <= 0 Or (stride % 4) <> 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a vertex input binding whose stride is zero, negative or not a multiple of four (Anvil code -20001, invalid stride); every component is a four-byte binary32 and the vertex fetcher advances by whole components.")
    EndIf
    avkPipeBindStride[bbase + bidx] = stride
    k = k + 1
  Wend

  n = *vi\vertexAttributeDescriptionCount & $FFFFFFFF
  If n < 1 Or n > #ANVIL_SPV_MAX_ATTRS Or *vi\pVertexAttributeDescriptions = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was given no vertex attributes or more than four (Anvil code -20005, unsupported vertex input); this slice fetches between one and four attributes.")
  EndIf
  If n <> avkShInCount[vs]
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a different number of vertex attributes from the number of Location inputs its vertex shader declares (Anvil code -20001, interface mismatch); every attribute the shader reads must be supplied, and an attribute nothing reads would be fetched and thrown away.")
  EndIf
  base = pipe * #ANVIL_SPV_MAX_ATTRS
  seen = 0
  usedBind = 0
  k = 0
  While k < n
    *attr = *vi\pVertexAttributeDescriptions + (k * SizeOf(VkVertexInputAttributeDescription))
    bidx = *attr\binding & $FFFFFFFF
    If bidx < 0 Or bidx >= nb
      ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a vertex attribute that reads a binding this pipeline does not describe (Anvil code -20001, interface mismatch); VkVertexInputAttributeDescription.binding must name one of the bindings in pVertexBindingDescriptions, and an attribute pointed at a binding nothing declares has no buffer and no stride to be fetched with.")
    EndIf
    usedBind = usedBind | (1 << bidx)
    loc = *attr\location & $FFFFFFFF
    If loc < 0 Or loc >= n
      ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a vertex attribute at a location its vertex shader does not declare (Anvil code -20001, interface mismatch); the locations must be 0 to one less than the attribute count, with no gaps.")
    EndIf
    If (seen & (1 << loc)) <> 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given two vertex attributes at the same location (Anvil code -20001, duplicate location); each location is described exactly once.")
    EndIf
    seen = seen | (1 << loc)
    fmt = *attr\format & $FFFFFFFF
    comps = avkFormatComponents(fmt)
    If comps = 0
      ProcedureReturn avkFault(#VK_ERROR_FORMAT_NOT_SUPPORTED, "vkCreateGraphicsPipelines was given a vertex attribute in a format this implementation does not fetch (VkResult -11, VK_ERROR_FORMAT_NOT_SUPPORTED); the three formats it reads are VK_FORMAT_R32G32_SFLOAT, VK_FORMAT_R32G32B32_SFLOAT and VK_FORMAT_R32G32B32A32_SFLOAT, because every value the emitted shader moves is a binary32.")
    EndIf
    If comps <> avkShInComp[(vs * #ANVIL_SPV_MAX_ATTRS) + loc]
      ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a vertex attribute whose format has a different number of components from the shader input at the same location (Anvil code -20001, interface mismatch); a vec2 input needs a two-component format, and a mismatch would feed the shader components that were never fetched.")
    EndIf
    j = *attr\offset & $FFFFFFFF
    If j < 0 Or (j % 4) <> 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a vertex attribute at an offset that is negative or not a multiple of four (Anvil code -20001, misaligned attribute); every component is a four-byte binary32 and the vertex fetcher reads them aligned.")
    EndIf
    If (j + (comps * 4)) > avkPipeBindStride[bbase + bidx]
      ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a vertex attribute that runs past the end of one vertex of ITS OWN binding (Anvil code -20001, attribute outside the stride); the stride that has to cover an attribute is the stride of the binding that attribute names, which is not the same number once a pipeline has two bindings.")
    EndIf
    avkPipeAttrComp[base + loc] = comps
    avkPipeAttrOffset[base + loc] = j
    avkPipeAttrBinding[base + loc] = bidx
    k = k + 1
  Wend
  ; A BINDING NOTHING READS IS REFUSED, not ignored. A buffer bound to it
  ; would be retained across the submission and fetched from never, and
  ; the usual cause is an attribute whose `binding` was left at zero after
  ; the buffer was split in two - which is a mistake worth naming rather
  ; than a layout worth supporting.
  k = 0
  While k < nb
    If (usedBind & (1 << k)) = 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a vertex input binding that no attribute reads (Anvil code -20001, unused binding); every binding described must be named by at least one attribute. The usual cause is an attribute left at binding zero after the vertex data was split across two buffers.")
    EndIf
    k = k + 1
  Wend
  avkPipeBindCount[pipe] = nb
  avkPipeAttrCount[pipe] = n
  ProcedureReturn #VK_SUCCESS
EndProcedure

; Validate the registry dynamic-state list and publish the bounded VIEWPORT
; and SCISSOR pair. A non-null structure is not enough: flags, pNext, count,
; pointer, duplicates and every unsupported state are refused.
Procedure.i avkPipeDynamicState(*ds.VkPipelineDynamicStateCreateInfo, *dynamicViewport, *dynamicScissor)
  Define k.i
  Define state.i
  Define viewport.i
  Define scissor.i
  If *dynamicViewport = 0 Or *dynamicScissor = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*dynamicViewport, 0) : PokeI(*dynamicScissor, 0)
  If *ds = 0 : ProcedureReturn #VK_SUCCESS : EndIf
  If (*ds\sType & $FFFFFFFF) <> #VK_STRUCTURE_TYPE_PIPELINE_DYNAMIC_STATE_CREATE_INFO
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a VkPipelineDynamicStateCreateInfo whose sType is wrong (Anvil code -20001, wrong sType).")
  EndIf
  If *ds\pNext <> 0 Or (*ds\flags & $FFFFFFFF) <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was given a dynamic-state pNext chain or nonzero flags (Anvil code -20005, unsupported dynamic state create info); no extension or flags are implemented here.")
  EndIf
  If (*ds\dynamicStateCount & $FFFFFFFF) < 1 Or (*ds\dynamicStateCount & $FFFFFFFF) > 2 Or *ds\pDynamicStates = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines must name one or two dynamic states with a non-null pDynamicStates array (Anvil code -20005, unsupported dynamic state set); this implementation supports VIEWPORT and SCISSOR.")
  EndIf
  k = 0
  While k < (*ds\dynamicStateCount & $FFFFFFFF)
    state = PeekL(*ds\pDynamicStates + (k * 4)) & $FFFFFFFF
    If state = #VK_DYNAMIC_STATE_VIEWPORT
      If viewport <> 0 : ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines named VK_DYNAMIC_STATE_VIEWPORT more than once (Anvil code -20005, duplicate dynamic state); every dynamic state must be unique.") : EndIf
      viewport = 1
    ElseIf state = #VK_DYNAMIC_STATE_SCISSOR
      If scissor <> 0 : ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines named VK_DYNAMIC_STATE_SCISSOR more than once (Anvil code -20005, duplicate dynamic state); every dynamic state must be unique.") : EndIf
      scissor = 1
    Else
      ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines requested dynamic line, depth, blend or stencil state (Anvil code -20005, unsupported dynamic state); only VIEWPORT and SCISSOR are implemented.")
    EndIf
    k = k + 1
  Wend
  If viewport <> 0 And scissor = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines requested a dynamic viewport without dynamic scissor (Anvil code -20005, unsupported dynamic state pair); resize-safe viewport pipelines must supply both per draw.")
  EndIf
  PokeI(*dynamicViewport, viewport) : PokeI(*dynamicScissor, scissor)
  ProcedureReturn #VK_SUCCESS
EndProcedure

; The viewport is either a fixed full target or a per-draw full target. The
; scissor is likewise static or dynamic. Vulkan ignores the corresponding
; pointer when state is dynamic, so null is legal in that case.
Procedure.i avkPipeViewport(pipe.i, *vp.VkPipelineViewportStateCreateInfo, dynamicViewport.i, dynamicScissor.i)
  Define *v.VkViewport
  Define *sc.VkRect2D
  Define x.i
  Define y.i
  Define w.i
  Define h.i
  If *vp = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given no pViewportState (Anvil code -20001, missing state); a pipeline that rasterises must declare its viewport and scissor.")
  EndIf
  If (*vp\sType & $FFFFFFFF) <> #VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a VkPipelineViewportStateCreateInfo whose sType is wrong (Anvil code -20001, wrong sType).")
  EndIf
  If (*vp\viewportCount & $FFFFFFFF) <> 1 Or (*vp\scissorCount & $FFFFFFFF) <> 1
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was given other than exactly one viewport and one scissor (Anvil code -20005, unsupported viewport state); multiple viewports need a capability this device does not report.")
  EndIf
  If dynamicViewport = 0 And *vp\pViewports = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was given a null pViewports without enabling VK_DYNAMIC_STATE_VIEWPORT (Anvil code -20005, missing static viewport); supply one viewport or make viewport and scissor dynamic.")
  EndIf
  If dynamicScissor = 0 And *vp\pScissors = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was given a null pScissors without enabling VK_DYNAMIC_STATE_SCISSOR (Anvil code -20005, missing static scissor); supply one full-viewport scissor or make scissor dynamic.")
  EndIf
  If dynamicViewport <> 0
    avkPipeViewX[pipe] = 0 : avkPipeViewY[pipe] = 0
    avkPipeViewW[pipe] = 1 : avkPipeViewH[pipe] = 1
  Else
  *v = *vp\pViewports
  ; The viewport's floats are read as integers on purpose: this slice
  ; renders at whole-pixel viewports and the coordinate shader's scale
  ; comes out of them, so a fractional viewport would be silently
  ; rounded. It is refused instead.
  x = PeekL(@*v\x) & $FFFFFFFF
  y = PeekL(@*v\y) & $FFFFFFFF
  w = PeekL(@*v\width) & $FFFFFFFF
  h = PeekL(@*v\height) & $FFFFFFFF
  avkPipeViewX[pipe] = avkIntFromF32Bits(x)
  avkPipeViewY[pipe] = avkIntFromF32Bits(y)
  avkPipeViewW[pipe] = avkIntFromF32Bits(w)
  avkPipeViewH[pipe] = avkIntFromF32Bits(h)
  If avkPipeViewW[pipe] < 1 Or avkPipeViewH[pipe] < 1
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was given a viewport whose width or height is not a positive whole number of pixels (Anvil code -20005, unsupported viewport); the emitted coordinate shader scales clip space by half the viewport in whole pixels, so a fractional or a flipped viewport would not be carried out as asked.")
  EndIf
  If avkPipeViewX[pipe] <> 0 Or avkPipeViewY[pipe] <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was given a viewport that does not start at the origin (Anvil code -20005, unsupported viewport); this slice renders one viewport covering the whole render target.")
  EndIf
  If dynamicScissor = 0
    *sc = *vp\pScissors
    If *sc\offset\x <> 0 Or *sc\offset\y <> 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was given a static scissor that does not start at the origin (Anvil code -20005, unsupported static scissor); use VK_DYNAMIC_STATE_SCISSOR for per-draw clipping.")
    EndIf
    If (*sc\extent\width & $FFFFFFFF) <> avkPipeViewW[pipe] Or (*sc\extent\height & $FFFFFFFF) <> avkPipeViewH[pipe]
      ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was given a static scissor that is not the whole viewport (Anvil code -20005, unsupported static scissor); use VK_DYNAMIC_STATE_SCISSOR for per-draw clipping.")
    EndIf
    avkPipeScissorX[pipe] = 0 : avkPipeScissorY[pipe] = 0
    avkPipeScissorW[pipe] = avkPipeViewW[pipe] : avkPipeScissorH[pipe] = avkPipeViewH[pipe]
  Else
    avkPipeScissorX[pipe] = 0 : avkPipeScissorY[pipe] = 0
    avkPipeScissorW[pipe] = 0 : avkPipeScissorH[pipe] = 0
  EndIf
  If (PeekL(@*v\minDepth) & $FFFFFFFF) <> 0 Or (PeekL(@*v\maxDepth) & $FFFFFFFF) <> $3F800000
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was given a viewport depth range other than exactly zero through one (Anvil code -20005, unsupported viewport depth); depth buffering is not implemented.")
  EndIf
  EndIf
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkGraphicsPipelineCreate(device.i, *ci.VkGraphicsPipelineCreateInfo, *out)
  Define d.i
  Define s.i
  Define rc.i
  Define vs.i
  Define fs.i
  Define lay.i
  Define rp.i
  Define k.i
  Define base.i
  Define need.i
  Define mem.i
  Define sampleMask.i
  Define blendMode.i
  Define dynamicViewport.i
  Define dynamicScissor.i
  Define *st.VkPipelineShaderStageCreateInfo
  Define build.AnvilVkBackendPipelineBuildInfo

  If *out = 0 Or *ci = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, #VK_NULL_HANDLE)
  d = avkDevSlot(device)
  If d = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If AnvilVkBackendCanDraw() = 0
    ProcedureReturn avkFault(#VK_ERROR_FEATURE_NOT_PRESENT, "vkCreateGraphicsPipelines was called on a device whose backend executes no graphics pipeline (VkResult -8, VK_ERROR_FEATURE_NOT_PRESENT); the linked backend reports no draw capability, so a pipeline created here could never be submitted. A backend that only clears is not a backend that draws.")
  EndIf
  If (*ci\sType & $FFFFFFFF) <> #VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a VkGraphicsPipelineCreateInfo whose sType is wrong (Anvil code -20001, wrong sType); it must be VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO.")
  EndIf
  If *ci\pNext <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was given a VkGraphicsPipelineCreateInfo with a pNext chain (Anvil code -20005, no pNext extension is implemented); no pipeline was created.")
  EndIf
  If *ci\pTessellationState <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was given a tessellation state (Anvil code -20005, tessellation not implemented); there are no tessellation stages in this implementation.")
  EndIf
  If *ci\pDepthStencilState <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was given a depth-stencil state (Anvil code -20005, depth and stencil not implemented); the render pass has no depth attachment, so the specification does not require this structure and this implementation cannot honour it.")
  EndIf
  rc = avkPipeDynamicState(*ci\pDynamicState, @dynamicViewport, @dynamicScissor)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  If *ci\basePipelineHandle <> #VK_NULL_HANDLE Or (*ci\basePipelineIndex & $FFFFFFFF) <> $FFFFFFFF
    If (*ci\basePipelineIndex & $FFFFFFFF) <> 0 Or *ci\basePipelineHandle <> #VK_NULL_HANDLE
      ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was asked to derive a pipeline from another (Anvil code -20005, pipeline derivatives not implemented); create each pipeline independently.")
    EndIf
  EndIf
  If (*ci\subpass & $FFFFFFFF) <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a subpass index other than zero (Anvil code -20001, invalid subpass); the render pass this slice creates has one subpass and its index is zero.")
  EndIf
  lay = avkLaySlot(*ci\layout)
  rp = avkRpSlot(*ci\renderPass)
  If lay = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_HANDLE, "vkCreateGraphicsPipelines was given a stale or foreign VkPipelineLayout (Anvil code -20002, invalid layout handle); create a live layout on this device before building the pipeline.")
  EndIf
  If rp = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_HANDLE, "vkCreateGraphicsPipelines was given a stale or foreign VkRenderPass (Anvil code -20002, invalid render-pass handle); create a live render pass on this device before building the pipeline.")
  EndIf
  If avkLayDev[lay] <> d Or avkRpDev[rp] <> d
    ProcedureReturn avkFault(#ANVIL_VK_ERR_OWNER, "vkCreateGraphicsPipelines was given a pipeline layout or a render pass from a different VkDevice (Anvil code -20003, wrong parent); every object in one pipeline must share a device.")
  EndIf

  ; The two stages, in either order.
  If (*ci\stageCount & $FFFFFFFF) <> 2 Or *ci\pStages = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was given other than exactly two shader stages (Anvil code -20005, unsupported pipeline); a graphics pipeline here is one vertex shader and one fragment shader.")
  EndIf
  vs = 0
  fs = 0
  k = 0
  While k < 2
    *st = *ci\pStages + (k * SizeOf(VkPipelineShaderStageCreateInfo))
    If (*st\sType & $FFFFFFFF) <> #VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO
      ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a VkPipelineShaderStageCreateInfo whose sType is wrong (Anvil code -20001, wrong sType).")
    EndIf
    If *st\pSpecializationInfo <> 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was given specialization constants (Anvil code -20005, specialization not implemented); the front end walks the module as it was compiled, so a constant substituted at pipeline creation would never reach the emitted shader.")
    EndIf
    s = avkShSlot(*st\module)
    If s = 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_HANDLE, "vkCreateGraphicsPipelines was given a stale or foreign VkShaderModule (Anvil code -20002, invalid shader-module handle); keep every stage module live through pipeline creation.")
    EndIf
    If avkShDev[s] <> d
      ProcedureReturn avkFault(#ANVIL_VK_ERR_OWNER, "vkCreateGraphicsPipelines was given a shader module from a different VkDevice (Anvil code -20003, wrong parent); every object in one pipeline must share a device.")
    EndIf
    If (*st\stage & $FFFFFFFF) = #VK_SHADER_STAGE_VERTEX_BIT
      If avkShStage[s] <> 0
        ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a module at the vertex stage whose SPIR-V entry point is not a Vertex entry point (Anvil code -20001, stage mismatch); the stage named in VkPipelineShaderStageCreateInfo must be the module's own execution model.")
      EndIf
      vs = s
    ElseIf (*st\stage & $FFFFFFFF) = #VK_SHADER_STAGE_FRAGMENT_BIT
      If avkShStage[s] <> 4
        ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a module at the fragment stage whose SPIR-V entry point is not a Fragment entry point (Anvil code -20001, stage mismatch); the stage named in VkPipelineShaderStageCreateInfo must be the module's own execution model.")
      EndIf
      fs = s
    Else
      ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was given a shader stage that is neither vertex nor fragment (Anvil code -20005, unsupported stage); geometry, tessellation and compute stages are not implemented.")
    EndIf
    k = k + 1
  Wend
  If vs = 0 Or fs = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given two stages that are not one vertex and one fragment (Anvil code -20001, unsupported stage set); a graphics pipeline here has exactly one of each.")
  EndIf

  rc = avkPipeCheckInputAssembly(*ci\pInputAssemblyState)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  rc = avkPipeCheckRasterization(*ci\pRasterizationState)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  rc = avkPipeCheckMultisample(*ci\pMultisampleState, @sampleMask)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  rc = avkPipeCheckColorBlend(*ci\pColorBlendState, @blendMode)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf

  ; The stage interface. Every varying the vertex shader writes must be
  ; the input the fragment shader reads, at the same location and the
  ; same width; the specification calls this interface matching and it is
  ; the one check that can only be made with both modules in view.
  If avkShOutCount[vs] <> avkShInCount[fs]
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a vertex shader and a fragment shader whose interfaces do not match in the number of varyings (Anvil code -20001, interface mismatch); every Location output of the vertex stage must be a Location input of the fragment stage.")
  EndIf
  k = 0
  While k < avkShOutCount[vs]
    If avkShOutComp[(vs * #ANVIL_SPV_MAX_VARYINGS) + k] <> avkShInComp[(fs * #ANVIL_SPV_MAX_ATTRS) + k]
      ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a varying whose width differs between the vertex and the fragment stage (Anvil code -20001, interface mismatch); a vec4 written by the vertex shader must be a vec4 read by the fragment shader.")
    EndIf
    k = k + 1
  Wend
  If avkShPush[fs] <> 0 And avkLayPushBytes[lay] <> #ANVIL_VK_PUSH_BYTES
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a fragment shader that reads the push-constant block through a pipeline layout that declares no push constant range (Anvil code -20001, layout mismatch); declare a sixteen-byte fragment-stage range at offset zero.")
  EndIf
  If avkShUsesVarying[fs] <> 0 And avkShOutCount[vs] < 1
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a fragment shader that interpolates a varying its vertex shader never writes (Anvil code -20001, interface mismatch); the vertex stage must write the Location the fragment stage reads.")
  EndIf
  ; THE DESCRIPTOR INTERFACE. A fragment shader that reads a uniform
  ; block named a set and a binding in its own SPIR-V; the pipeline
  ; layout has to declare a descriptor set layout that actually has a
  ; uniform buffer there, in the fragment stage. This is the one place
  ; the module and the layout are both in view, and a mismatch caught
  ; anywhere later is a draw reading an address nothing wrote.
  If avkShUniform[fs] <> 0
    If avkLaySetCount[lay] <> 1 Or avkLayBindingCount[lay] = 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a fragment shader that reads a uniform block through a pipeline layout that declares no descriptor set layout (Anvil code -20001, layout mismatch); create a VkDescriptorSetLayout with a VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER binding at the fragment stage and name it in VkPipelineLayoutCreateInfo.")
    EndIf
    If avkShUniformSet[fs] <> 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a fragment shader whose uniform block is at a descriptor set other than zero (Anvil code -20001, layout mismatch); one set is bound here and its index is zero.")
    EndIf
    If avkLayHasBinding(lay, avkShUniformBinding[fs], #VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER) = 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a fragment shader whose uniform block names a binding its pipeline layout's descriptor set layout does not declare as a fragment-stage uniform buffer (Anvil code -20001, layout mismatch); the Binding decoration in the SPIR-V and the binding number in VkDescriptorSetLayoutBinding are the same number and they must agree.")
    EndIf
  EndIf
  If avkShSample[fs] <> 0
    If avkLaySetCount[lay] <> 1 Or avkLayBindingCount[lay] = 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a fragment shader that samples an image through a pipeline layout that declares no descriptor set layout (Anvil code -20001, layout mismatch); create a VkDescriptorSetLayout with a VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER binding at the fragment stage and name it in VkPipelineLayoutCreateInfo.")
    EndIf
    If avkShSampleSet[fs] <> 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a fragment shader whose sampled image is at a descriptor set other than zero (Anvil code -20001, layout mismatch); one set is bound here and its index is zero.")
    EndIf
    If avkLayHasBinding(lay, avkShSampleBinding[fs], #VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER) = 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a fragment shader whose sampled image names a binding its pipeline layout does not declare as a fragment-stage combined image sampler (Anvil code -20001, layout mismatch); the Binding decoration in SPIR-V and the descriptor-set-layout binding must agree.")
    EndIf
  EndIf
  If avkShUniform[fs] = 0 And avkShSample[fs] = 0 And avkLaySetCount[lay] <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a pipeline layout that declares a descriptor set layout for a fragment shader that reads no descriptor (Anvil code -20001, layout mismatch); a declared set has to be allocated, written and bound before every draw, so one nothing reads is work with no picture at the end of it.")
  EndIf

  s = 1
  While s <= #ANVIL_VK_MAX_PIPELINES And avkPipeLive[s] <> 0 : s = s + 1 : Wend
  If s > #ANVIL_VK_MAX_PIPELINES : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf

  ; Fill the plan BEFORE the backend is asked to compile it, and mark the
  ; slot live only once the backend has said yes. A half-built pipeline
  ; that a later call could find is worse than no pipeline at all.
  avkPipeDev[s] = d
  avkPipePushBytes[s] = avkLayPushBytes[lay]
  avkPipeSetCount[s] = avkLaySetCount[lay]
  avkPipeBindingCount[s] = avkLayBindingCount[lay]
  k = 0
  While k < #ANVIL_VK_MAX_SET_BINDINGS
    avkPipeBindingType[(s * #ANVIL_VK_MAX_SET_BINDINGS) + k] = avkLayBindingType[(lay * #ANVIL_VK_MAX_SET_BINDINGS) + k]
    avkPipeBindingStages[(s * #ANVIL_VK_MAX_SET_BINDINGS) + k] = avkLayBindingStages[(lay * #ANVIL_VK_MAX_SET_BINDINGS) + k]
    k = k + 1
  Wend
  avkPipeRp[s] = rp
  avkPipeDynamicViewport[s] = dynamicViewport
  avkPipeDynamicScissor[s] = dynamicScissor
  avkPipePosAttr[s] = avkShPosAttr[vs]
  avkPipeVaryCount[s] = avkShOutCount[vs]
  avkPipeColourSrc[s] = avkShColourSrc[fs]
  avkPipeColourIdx[s] = avkShColourIdx[fs]
  avkPipeUsesPush[s] = avkShPush[fs]
  avkPipeUsesUniform[s] = avkShUniform[fs]
  avkPipeUsesSample[s] = avkShSample[fs]
  avkPipeUsesVarying[s] = avkShUsesVarying[fs]
  avkPipeUniformBinding[s] = avkShUniformBinding[fs]
  avkPipeSampleBinding[s] = avkShSampleBinding[fs]
  avkPipeSampleCoord[s] = avkShSampleCoord[fs]
  avkPipeSampleMask[s] = sampleMask
  avkPipeBlendMode[s] = blendMode
  base = s * #ANVIL_SPV_MAX_VARYINGS
  k = 0
  While k < #ANVIL_SPV_MAX_VARYINGS
    avkPipeVaryComp[base + k] = avkShOutComp[(vs * #ANVIL_SPV_MAX_VARYINGS) + k]
    avkPipeVarySrc[base + k] = avkShOutSrc[(vs * #ANVIL_SPV_MAX_VARYINGS) + k]
    k = k + 1
  Wend
  base = s * 4
  k = 0
  While k < 4
    avkPipeConst[base + k] = avkShConst[(fs * 4) + k]
    k = k + 1
  Wend
  base = s * #ANVIL_SPV_MAX_ATTRS
  k = 0
  While k < #ANVIL_SPV_MAX_ATTRS
    avkPipeAttrComp[base + k] = 0
    avkPipeAttrOffset[base + k] = 0
    avkPipeAttrBinding[base + k] = 0
    k = k + 1
  Wend
  avkPipeBindCount[s] = 0
  base = s * #ANVIL_VK_MAX_BINDINGS
  k = 0
  While k < #ANVIL_VK_MAX_BINDINGS
    avkPipeBindStride[base + k] = 0
    k = k + 1
  Wend
  rc = avkPipeVertexInput(s, vs, *ci\pVertexInputState)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  rc = avkPipeViewport(s, *ci\pViewportState, dynamicViewport, dynamicScissor)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  If avkPipePosAttr[s] < 0 Or avkPipePosAttr[s] >= avkPipeAttrCount[s]
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a vertex shader whose position attribute is not one of the pipeline's vertex attributes (Anvil code -20001, interface mismatch); the attribute gl_Position is built from must be described in the vertex input state.")
  EndIf

  ; The backend's own memory for this pipeline, out of the same device
  ; heap the application allocates from. It is an internal allocation:
  ; no VkDeviceMemory handle names it and vkFreeMemory cannot reach it.
  need = avkBackendPipelineBytes()
  If need <= 0
    ProcedureReturn avkFault(#VK_ERROR_INITIALIZATION_FAILED, "the graphics backend reported that a pipeline needs no memory at all (VkResult -3, VK_ERROR_INITIALIZATION_FAILED); no pipeline was created. This is a backend defect, not a caller error.")
  EndIf
  rc = avkHeapBind()
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  mem = avkInternalAlloc(need)
  If mem <= 0
    ProcedureReturn avkFault(#VK_ERROR_OUT_OF_DEVICE_MEMORY, "vkCreateGraphicsPipelines could not reserve device memory for the compiled shaders and their shader record (VkResult -2, VK_ERROR_OUT_OF_DEVICE_MEMORY); no pipeline was created. Free an allocation, or declare a larger Vulkan window, and create the pipeline before the application's own allocations fill the heap.")
  EndIf
  avkPipeCodeMem[s] = mem
  avkPipeCodeBase[s] = avkHeapBase + avkMemOffset[mem]
  avkPipeCodeBytes[s] = need
  If avkShIr[vs]\valid = 0 Or avkShIrGen[vs] <> avkShGen[vs] Or avkShIr[fs]\valid = 0 Or avkShIrGen[fs] <> avkShGen[fs]
    avkInternalFree(mem)
    avkPipeCodeMem[s] = 0
    ProcedureReturn avkFault(#VK_ERROR_INITIALIZATION_FAILED, "vkCreateGraphicsPipelines found that a vertex or fragment module's verified typed IR lifetime ended before backend lowering (VkResult -3, VK_ERROR_INITIALIZATION_FAILED); no pipeline was published.")
  EndIf
  build\pipeline = s
  build\dynamicViewport = dynamicViewport
  build\base = avkPipeCodeBase[s]
  build\bytes = need
  build\vertexIr = @avkShIr[vs]\module
  build\fragmentIr = @avkShIr[fs]\module
  rc = avkBackendPipelineBuild(@build)
  If rc <> #VK_SUCCESS
    avkInternalFree(mem)
    avkPipeCodeMem[s] = 0
    ProcedureReturn rc
  EndIf
  avkPipeGen[s] = avkNextGen(avkPipeGen[s])
  avkPipeLive[s] = 1
  PokeI(*out, avkToken(#ANVIL_VK_TYPE_PIPELINE, s, avkPipeGen[s]))
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure AnvilVkPipelineDestroy(device.i, pipeline.i)
  Define d.i
  Define s.i
  d = avkDevSlot(device)
  s = avkPipeSlot(pipeline)
  If s = 0
    If pipeline <> #VK_NULL_HANDLE
      avkFault(#ANVIL_VK_ERR_HANDLE, "vkDestroyPipeline was given a VkPipeline handle that is not live on this device (Anvil code -20002, stale or foreign handle); nothing was destroyed.")
    EndIf
    ProcedureReturn
  EndIf
  If d = 0 Or avkPipeDev[s] <> d
    avkFault(#ANVIL_VK_ERR_OWNER, "vkDestroyPipeline was called with a device that does not own this pipeline (Anvil code -20003, wrong parent); nothing was destroyed.")
    ProcedureReturn
  EndIf
  If avkPipeInFlight[s] <> 0
    avkFault(#ANVIL_VK_ERR_STATE, "vkDestroyPipeline was called while a submitted command buffer still uses this pipeline (Anvil code -20004, resource in use); nothing was destroyed. Wait on the submission's fence, or call vkDeviceWaitIdle, first.")
    ProcedureReturn
  EndIf
  avkBackendPipelineRelease(s)
  If avkPipeCodeMem[s] <> 0
    avkInternalFree(avkPipeCodeMem[s])
    avkPipeCodeMem[s] = 0
  EndIf
  avkPipeLive[s] = 0
  avkPipeDynamicViewport[s] = 0
  avkPipeDynamicScissor[s] = 0
  avkPipeScissorX[s] = 0 : avkPipeScissorY[s] = 0
  avkPipeScissorW[s] = 0 : avkPipeScissorH[s] = 0
EndProcedure

; ----------------------------------------------------------------------
;  The plan, as the backend reads it. Every one of these takes the
;  backend's own slot number, which is what avkBackendPipelineBuild was
;  handed, so a stale handle cannot reach one.
; ----------------------------------------------------------------------
Procedure.i AnvilVkPipelineAttrCount(pipe.i)
  If pipe < 1 Or pipe > #ANVIL_VK_MAX_PIPELINES : ProcedureReturn 0 : EndIf
  ProcedureReturn avkPipeAttrCount[pipe]
EndProcedure

Procedure.i AnvilVkPipelineAttrComponents(pipe.i, k.i)
  If pipe < 1 Or pipe > #ANVIL_VK_MAX_PIPELINES : ProcedureReturn 0 : EndIf
  If k < 0 Or k >= #ANVIL_SPV_MAX_ATTRS : ProcedureReturn 0 : EndIf
  ProcedureReturn avkPipeAttrComp[(pipe * #ANVIL_SPV_MAX_ATTRS) + k]
EndProcedure

Procedure.i AnvilVkPipelineAttrOffset(pipe.i, k.i)
  If pipe < 1 Or pipe > #ANVIL_VK_MAX_PIPELINES : ProcedureReturn 0 : EndIf
  If k < 0 Or k >= #ANVIL_SPV_MAX_ATTRS : ProcedureReturn 0 : EndIf
  ProcedureReturn avkPipeAttrOffset[(pipe * #ANVIL_SPV_MAX_ATTRS) + k]
EndProcedure

; Which binding attribute k is fetched from, and that binding's stride.
; The two together are what an attribute record needs, and they are read
; per attribute rather than per pipeline because two attributes of one
; pipeline can now come out of two buffers at two strides.
Procedure.i AnvilVkPipelineAttrBinding(pipe.i, k.i)
  If pipe < 1 Or pipe > #ANVIL_VK_MAX_PIPELINES : ProcedureReturn 0 : EndIf
  If k < 0 Or k >= #ANVIL_SPV_MAX_ATTRS : ProcedureReturn 0 : EndIf
  ProcedureReturn avkPipeAttrBinding[(pipe * #ANVIL_SPV_MAX_ATTRS) + k]
EndProcedure

Procedure.i AnvilVkPipelineBindingCount(pipe.i)
  If pipe < 1 Or pipe > #ANVIL_VK_MAX_PIPELINES : ProcedureReturn 0 : EndIf
  ProcedureReturn avkPipeBindCount[pipe]
EndProcedure

Procedure.i AnvilVkPipelineBindingStride(pipe.i, b.i)
  If pipe < 1 Or pipe > #ANVIL_VK_MAX_PIPELINES : ProcedureReturn 0 : EndIf
  If b < 0 Or b >= #ANVIL_VK_MAX_BINDINGS : ProcedureReturn 0 : EndIf
  ProcedureReturn avkPipeBindStride[(pipe * #ANVIL_VK_MAX_BINDINGS) + b]
EndProcedure

Procedure.i AnvilVkPipelinePositionAttr(pipe.i)
  If pipe < 1 Or pipe > #ANVIL_VK_MAX_PIPELINES : ProcedureReturn -1 : EndIf
  ProcedureReturn avkPipePosAttr[pipe]
EndProcedure

Procedure.i AnvilVkPipelineVaryingCount(pipe.i)
  If pipe < 1 Or pipe > #ANVIL_VK_MAX_PIPELINES : ProcedureReturn 0 : EndIf
  ProcedureReturn avkPipeVaryCount[pipe]
EndProcedure

Procedure.i AnvilVkPipelineVaryingComponents(pipe.i, k.i)
  If pipe < 1 Or pipe > #ANVIL_VK_MAX_PIPELINES : ProcedureReturn 0 : EndIf
  If k < 0 Or k >= #ANVIL_SPV_MAX_VARYINGS : ProcedureReturn 0 : EndIf
  ProcedureReturn avkPipeVaryComp[(pipe * #ANVIL_SPV_MAX_VARYINGS) + k]
EndProcedure

Procedure.i AnvilVkPipelineVaryingSource(pipe.i, k.i)
  If pipe < 1 Or pipe > #ANVIL_VK_MAX_PIPELINES : ProcedureReturn -1 : EndIf
  If k < 0 Or k >= #ANVIL_SPV_MAX_VARYINGS : ProcedureReturn -1 : EndIf
  ProcedureReturn avkPipeVarySrc[(pipe * #ANVIL_SPV_MAX_VARYINGS) + k]
EndProcedure

Procedure.i AnvilVkPipelineColourSource(pipe.i)
  If pipe < 1 Or pipe > #ANVIL_VK_MAX_PIPELINES : ProcedureReturn -1 : EndIf
  ProcedureReturn avkPipeColourSrc[pipe]
EndProcedure

Procedure.i AnvilVkPipelineUsesPushConstants(pipe.i)
  If pipe < 1 Or pipe > #ANVIL_VK_MAX_PIPELINES : ProcedureReturn 0 : EndIf
  ProcedureReturn avkPipeUsesPush[pipe]
EndProcedure

Procedure.i AnvilVkPipelineUsesUniformBuffer(pipe.i)
  If pipe < 1 Or pipe > #ANVIL_VK_MAX_PIPELINES : ProcedureReturn 0 : EndIf
  ProcedureReturn avkPipeUsesUniform[pipe]
EndProcedure

Procedure.i AnvilVkPipelineUsesSampledImage(pipe.i)
  If pipe < 1 Or pipe > #ANVIL_VK_MAX_PIPELINES : ProcedureReturn 0 : EndIf
  ProcedureReturn avkPipeUsesSample[pipe]
EndProcedure

Procedure.i AnvilVkPipelineUsesVarying(pipe.i)
  If pipe < 1 Or pipe > #ANVIL_VK_MAX_PIPELINES : ProcedureReturn 0 : EndIf
  ProcedureReturn avkPipeUsesVarying[pipe]
EndProcedure

Procedure.i AnvilVkPipelineSampleBinding(pipe.i)
  If pipe < 1 Or pipe > #ANVIL_VK_MAX_PIPELINES : ProcedureReturn -1 : EndIf
  ProcedureReturn avkPipeSampleBinding[pipe]
EndProcedure

Procedure.i AnvilVkPipelineSampleCoord(pipe.i)
  If pipe < 1 Or pipe > #ANVIL_VK_MAX_PIPELINES : ProcedureReturn -1 : EndIf
  ProcedureReturn avkPipeSampleCoord[pipe]
EndProcedure

Procedure.i AnvilVkPipelineColourConstant(pipe.i, k.i)
  If pipe < 1 Or pipe > #ANVIL_VK_MAX_PIPELINES : ProcedureReturn 0 : EndIf
  If k < 0 Or k > 3 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkPipeConst[(pipe * 4) + k]
EndProcedure

Procedure.i AnvilVkPipelineViewportWidth(pipe.i)
  If pipe < 1 Or pipe > #ANVIL_VK_MAX_PIPELINES : ProcedureReturn 0 : EndIf
  ProcedureReturn avkPipeViewW[pipe]
EndProcedure

Procedure.i AnvilVkPipelineViewportHeight(pipe.i)
  If pipe < 1 Or pipe > #ANVIL_VK_MAX_PIPELINES : ProcedureReturn 0 : EndIf
  ProcedureReturn avkPipeViewH[pipe]
EndProcedure

Procedure.i AnvilVkPipelineDynamicViewport(pipe.i)
  If pipe < 1 Or pipe > #ANVIL_VK_MAX_PIPELINES : ProcedureReturn 0 : EndIf
  ProcedureReturn avkPipeDynamicViewport[pipe]
EndProcedure

Procedure.i AnvilVkPipelineBlendMode(pipe.i)
  If pipe < 1 Or pipe > #ANVIL_VK_MAX_PIPELINES : ProcedureReturn #ANVIL_VK_BLEND_DISABLED : EndIf
  ProcedureReturn avkPipeBlendMode[pipe]
EndProcedure

Procedure.i AnvilVkPipelineCodeBase(pipeline.i)
  Define s.i
  s = avkPipeSlot(pipeline)
  If s = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkPipeCodeBase[s]
EndProcedure

Procedure.i AnvilVkPipelineCodeBytes(pipeline.i)
  Define s.i
  s = avkPipeSlot(pipeline)
  If s = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkPipeCodeBytes[s]
EndProcedure

; ======================================================================
;  RECORDING A RENDER PASS
; ======================================================================
;  The five commands below record ONE render pass holding ONE draw. They
;  are void, exactly as the registry declares them, so a refusal moves
;  the command buffer to the invalid state and vkEndCommandBuffer reports
;  it - the same contract vkCmdClearColorImage already follows.

; vkCmdBeginRenderPass. The attachment's image becomes a reference of
; this command buffer, so the submission retains it and the layout the
; render pass ends in reaches the image when the submission completes.
;
; THE ENTRY LAYOUT IS "ANY" AND THAT IS NOT A SHORTCUT. The attachment's
; initialLayout is VK_IMAGE_LAYOUT_UNDEFINED, which the specification
; defines as "the previous contents may be discarded"; a render pass that
; began that way imposes nothing on the image it is handed, so demanding
; a layout at submit time would refuse a perfectly legal program.
Procedure AnvilVkCmdBeginRenderPass(commandBuffer.i, renderPass.i, framebuffer.i, *area.VkRect2D, clearCount.i, *pClearValues)
  Define c.i
  Define rp.i
  Define fb.i
  Define iv.i
  Define img.i
  Define k.i
  Define red.i
  Define green.i
  Define blue.i
  Define alpha.i

  c = avkCmdSlot(commandBuffer)
  If c = 0
    avkFault(#ANVIL_VK_ERR_HANDLE, "vkCmdBeginRenderPass was given a VkCommandBuffer handle that is not live (Anvil code -20002, stale or foreign handle); nothing was recorded.")
    ProcedureReturn
  EndIf
  If avkCmdState[c] <> #ANVIL_VK_CB_RECORDING
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdBeginRenderPass was called on a command buffer that is not recording (Anvil code -20004, wrong command buffer state); call vkBeginCommandBuffer first.")
    ProcedureReturn
  EndIf
  If avkCbRpActive[c] <> 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdBeginRenderPass was called inside a render pass that is already begun (Anvil code -20004, render pass already open); render passes do not nest, so end the first one with vkCmdEndRenderPass.")
    ProcedureReturn
  EndIf
  If avkCbRpDone[c] <> 0
    avkCbFail(c, #VK_ERROR_FEATURE_NOT_PRESENT, "vkCmdBeginRenderPass was called a second time in one command buffer (VkResult -8, VK_ERROR_FEATURE_NOT_PRESENT); the backend seam carries one render pass per submission, so record the second pass in its own command buffer.")
    ProcedureReturn
  EndIf
  rp = avkRpSlot(renderPass)
  fb = avkFbSlot(framebuffer)
  If rp = 0 Or fb = 0
    avkCbFail(c, #ANVIL_VK_ERR_HANDLE, "vkCmdBeginRenderPass was given a VkRenderPass or VkFramebuffer handle that is not live (Anvil code -20002, stale or foreign handle); the command buffer is now invalid and vkEndCommandBuffer will say so.")
    ProcedureReturn
  EndIf
  If avkFbRp[fb] <> rp
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdBeginRenderPass was given a framebuffer that was not created for this render pass (Anvil code -20001, incompatible framebuffer); a framebuffer is compatible only with the render pass whose attachment description it was created against.")
    ProcedureReturn
  EndIf
  ; A framebuffer retains Vulkan handles, not authority over whichever
  ; objects later reuse the same slots. Resolve both recorded generations
  ; before reading the cached slots or attachment state.
  If avkRpSlot(avkFbRpHandle[fb]) <> avkFbRp[fb] Or avkIvSlot(avkFbViewHandle[fb]) <> avkFbView[fb]
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdBeginRenderPass was given a framebuffer whose render pass or attachment view has since been destroyed or replaced (Anvil code -20004, stale framebuffer dependency); rebuild the framebuffer from current live handles.")
    ProcedureReturn
  EndIf
  If avkRpDev[rp] <> avkPoolDev[avkCmdPool[c]]
    avkCbFail(c, #ANVIL_VK_ERR_OWNER, "vkCmdBeginRenderPass was given a render pass that belongs to a different VkDevice from the command buffer's pool (Anvil code -20003, wrong parent); every object in one command buffer must share one device.")
    ProcedureReturn
  EndIf
  If *area = 0 Or (*area\offset\x & $FFFFFFFF) <> 0 Or (*area\offset\y & $FFFFFFFF) <> 0
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdBeginRenderPass was given a render area that does not start at the framebuffer's origin (Anvil code -20005, unsupported render area); this backend renders whole tiles over the whole render target, so a partial render area would clear and store pixels outside it.")
    ProcedureReturn
  EndIf
  If (*area\extent\width & $FFFFFFFF) <> avkFbW[fb] Or (*area\extent\height & $FFFFFFFF) <> avkFbH[fb]
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdBeginRenderPass was given a render area that is not the whole framebuffer (Anvil code -20005, unsupported render area); see above - the tile geometry covers the whole target.")
    ProcedureReturn
  EndIf
  If clearCount <> 1 Or *pClearValues = 0
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdBeginRenderPass was given other than exactly one clear value (Anvil code -20001, clear value count mismatch); the render pass has one attachment whose loadOp is VK_ATTACHMENT_LOAD_OP_CLEAR, so it needs one and only one.")
    ProcedureReturn
  EndIf
  iv = avkFbView[fb]
  img = avkImgSlot(avkIvImage[iv])
  If img = 0 Or img <> avkIvImgSlot[iv] Or avkImgBound[img] = 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdBeginRenderPass was given a framebuffer whose attachment image has no memory bound to it (Anvil code -20004, image not bound); call vkBindImageMemory before recording a render pass against it.")
    ProcedureReturn
  EndIf
  If (avkImgUsage[img] & #VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT) = 0
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdBeginRenderPass reached an attachment image that was not created with VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT (Anvil code -20001, missing usage); framebuffer creation normally owns this refusal, and transfer usage cannot authorize rendering.")
    ProcedureReturn
  EndIf
  k = avkCbRef(c, avkIvImage[iv], img)
  If k < 0
    avkCbFail(c, #VK_ERROR_OUT_OF_HOST_MEMORY, "one command buffer referenced more images than Anvil can retain for a submission (VkResult -1, VK_ERROR_OUT_OF_HOST_MEMORY); this slice retains two images per command buffer.")
    ProcedureReturn
  EndIf
  ; VkClearValue is a union; its colour arm is four binary32 components in
  ; R, G, B, A order whatever the attachment's format is. The packing into
  ; VK_FORMAT_B8G8R8A8_UNORM's byte order is exactly what
  ; vkCmdClearColorImage does, and for the same reason.
  red = avkUnorm8FromF32Bits(avkU32(*pClearValues))
  green = avkUnorm8FromF32Bits(avkU32(*pClearValues + 4))
  blue = avkUnorm8FromF32Bits(avkU32(*pClearValues + 8))
  alpha = avkUnorm8FromF32Bits(avkU32(*pClearValues + 12))
  avkCbClearWord[c] = (alpha << 24) | (red << 16) | (green << 8) | blue
  avkCbFb[c] = fb
  avkCbFbHandle[c] = framebuffer
  avkCbRpActive[c] = 1
  avkRefCur[avkRefIndex(c, k)] = avkRpFinalLayout[rp]
EndProcedure

Procedure AnvilVkCmdBindPipeline(commandBuffer.i, bindPoint.i, pipeline.i)
  Define c.i
  Define p.i
  c = avkCmdSlot(commandBuffer)
  If c = 0
    avkFault(#ANVIL_VK_ERR_HANDLE, "vkCmdBindPipeline was given a VkCommandBuffer handle that is not live (Anvil code -20002, stale or foreign handle); nothing was recorded.")
    ProcedureReturn
  EndIf
  If avkCmdState[c] <> #ANVIL_VK_CB_RECORDING
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdBindPipeline was called on a command buffer that is not recording (Anvil code -20004, wrong command buffer state); call vkBeginCommandBuffer first.")
    ProcedureReturn
  EndIf
  If bindPoint <> #VK_PIPELINE_BIND_POINT_GRAPHICS
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdBindPipeline was given a bind point that is not VK_PIPELINE_BIND_POINT_GRAPHICS (Anvil code -20005, unsupported bind point); there is no compute pipeline in this implementation.")
    ProcedureReturn
  EndIf
  p = avkPipeSlot(pipeline)
  If p = 0
    avkCbFail(c, #ANVIL_VK_ERR_HANDLE, "vkCmdBindPipeline was given a VkPipeline handle that is not live (Anvil code -20002, stale or foreign handle); the command buffer is now invalid and vkEndCommandBuffer will say so.")
    ProcedureReturn
  EndIf
  If avkPipeDev[p] <> avkPoolDev[avkCmdPool[c]]
    avkCbFail(c, #ANVIL_VK_ERR_OWNER, "vkCmdBindPipeline was given a pipeline that belongs to a different VkDevice from the command buffer's pool (Anvil code -20003, wrong parent); every object in one command buffer must share one device.")
    ProcedureReturn
  EndIf
  avkCbPipe[c] = pipeline
EndProcedure

; Registry-exact dynamic viewport recording for the one bounded viewport.
Procedure AnvilVkCmdSetViewport(commandBuffer.i, firstViewport.i, viewportCount.i, *viewports.VkViewport)
  Define c.i
  Define x.i, y.i, w.i, h.i
  c = avkCmdSlot(commandBuffer)
  If c = 0
    avkFault(#ANVIL_VK_ERR_HANDLE, "vkCmdSetViewport was given a VkCommandBuffer handle that is not live (Anvil code -20002, stale or foreign handle); nothing was recorded.")
    ProcedureReturn
  EndIf
  If avkCmdState[c] <> #ANVIL_VK_CB_RECORDING
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdSetViewport was called on a command buffer that is not recording (Anvil code -20004, wrong command buffer state); call vkBeginCommandBuffer first.")
    ProcedureReturn
  EndIf
  If firstViewport <> 0 Or viewportCount <> 1 Or *viewports = 0
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdSetViewport requires firstViewport zero, viewportCount one and one non-null VkViewport (Anvil code -20005, unsupported viewport array); this device exposes one viewport.")
    ProcedureReturn
  EndIf
  x = avkIntFromF32Bits(PeekL(@*viewports\x) & $FFFFFFFF)
  y = avkIntFromF32Bits(PeekL(@*viewports\y) & $FFFFFFFF)
  w = avkIntFromF32Bits(PeekL(@*viewports\width) & $FFFFFFFF)
  h = avkIntFromF32Bits(PeekL(@*viewports\height) & $FFFFFFFF)
  If x <> 0 Or y <> 0 Or w < 1 Or w > 32767 Or h < 1 Or h > 32767 Or (PeekL(@*viewports\minDepth) & $FFFFFFFF) <> 0 Or (PeekL(@*viewports\maxDepth) & $FFFFFFFF) <> $3F800000
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdSetViewport requires an origin-zero positive whole-pixel viewport no larger than 32767 with depth exactly zero through one (Anvil code -20005, unsupported viewport); fractional, flipped, translated and depth-remapped viewports are not implemented.")
    ProcedureReturn
  EndIf
  avkCbViewportX[c] = x : avkCbViewportY[c] = y
  avkCbViewportW[c] = w : avkCbViewportH[c] = h
  avkCbViewportSet[c] = 1
EndProcedure

; Registry-exact dynamic scissor recording. Bounds belong to the eventual
; framebuffer, which need not be active when this state is set; the target
; backend performs the overflow-safe intersection during atomic preflight.
Procedure AnvilVkCmdSetScissor(commandBuffer.i, firstScissor.i, scissorCount.i, *scissors.VkRect2D)
  Define c.i
  c = avkCmdSlot(commandBuffer)
  If c = 0
    avkFault(#ANVIL_VK_ERR_HANDLE, "vkCmdSetScissor was given a VkCommandBuffer handle that is not live (Anvil code -20002, stale or foreign handle); nothing was recorded.")
    ProcedureReturn
  EndIf
  If avkCmdState[c] <> #ANVIL_VK_CB_RECORDING
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdSetScissor was called on a command buffer that is not recording (Anvil code -20004, wrong command buffer state); call vkBeginCommandBuffer first.")
    ProcedureReturn
  EndIf
  If firstScissor <> 0 Or scissorCount <> 1 Or *scissors = 0
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdSetScissor requires firstScissor zero, scissorCount one and one non-null VkRect2D (Anvil code -20005, unsupported scissor array); this device exposes one viewport and one scissor.")
    ProcedureReturn
  EndIf
  avkCbScissorX[c] = *scissors\offset\x
  avkCbScissorY[c] = *scissors\offset\y
  avkCbScissorW[c] = *scissors\extent\width & $FFFFFFFF
  avkCbScissorH[c] = *scissors\extent\height & $FFFFFFFF
  avkCbScissorSet[c] = 1
EndProcedure

Procedure AnvilVkCmdBindVertexBuffer(commandBuffer.i, binding.i, buffer.i, offset.i)
  Define c.i
  Define b.i
  c = avkCmdSlot(commandBuffer)
  If c = 0
    avkFault(#ANVIL_VK_ERR_HANDLE, "vkCmdBindVertexBuffers was given a VkCommandBuffer handle that is not live (Anvil code -20002, stale or foreign handle); nothing was recorded.")
    ProcedureReturn
  EndIf
  If avkCmdState[c] <> #ANVIL_VK_CB_RECORDING
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdBindVertexBuffers was called on a command buffer that is not recording (Anvil code -20004, wrong command buffer state); call vkBeginCommandBuffer first.")
    ProcedureReturn
  EndIf
  If binding < 0 Or binding >= #ANVIL_VK_MAX_BINDINGS
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdBindVertexBuffers was asked to bind a binding number this slice does not have (Anvil code -20005, unsupported binding); the bindings are numbered 0 to 3, and a pipeline's own binding count is checked again at vkCmdDraw.")
    ProcedureReturn
  EndIf
  b = avkBufSlot(buffer)
  If b = 0
    avkCbFail(c, #ANVIL_VK_ERR_HANDLE, "vkCmdBindVertexBuffers was given a VkBuffer handle that is not live (Anvil code -20002, stale or foreign handle); the command buffer is now invalid and vkEndCommandBuffer will say so.")
    ProcedureReturn
  EndIf
  If avkBufDev[b] <> avkPoolDev[avkCmdPool[c]]
    avkCbFail(c, #ANVIL_VK_ERR_OWNER, "vkCmdBindVertexBuffers was given a buffer that belongs to a different VkDevice from the command buffer's pool (Anvil code -20003, wrong parent); every object in one command buffer must share one device.")
    ProcedureReturn
  EndIf
  If avkBufBound[b] = 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdBindVertexBuffers was given a buffer with no memory bound to it (Anvil code -20004, buffer not bound); call vkBindBufferMemory before binding it as a vertex buffer.")
    ProcedureReturn
  EndIf
  If (avkBufUsage[b] & #VK_BUFFER_USAGE_VERTEX_BUFFER_BIT) = 0
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdBindVertexBuffers was given a buffer that was not created with VK_BUFFER_USAGE_VERTEX_BUFFER_BIT (Anvil code -20001, missing usage); a buffer the vertex fetcher reads must name that usage in VkBufferCreateInfo.")
    ProcedureReturn
  EndIf
  If offset < 0 Or offset >= avkBufSize[b] Or (offset % 4) <> 0
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdBindVertexBuffers was given an offset that is negative, past the end of the buffer or not a multiple of four (Anvil code -20001, invalid bind offset); every attribute component is a four-byte binary32 and the vertex fetcher reads them aligned.")
    ProcedureReturn
  EndIf
  avkCbVtxBuf[(c * #ANVIL_VK_MAX_BINDINGS) + binding] = buffer
  avkCbVtxOffset[(c * #ANVIL_VK_MAX_BINDINGS) + binding] = offset
EndProcedure

; vkCmdBindDescriptorSets. One set, at index zero, through the layout the
; pipeline was created with, and no dynamic offsets.
Procedure AnvilVkCmdBindDescriptorSet(commandBuffer.i, bindPoint.i, layout.i, firstSet.i, set.i, dynamicCount.i)
  Define c.i
  Define lay.i
  Define d.i
  Define k.i
  c = avkCmdSlot(commandBuffer)
  If c = 0
    avkFault(#ANVIL_VK_ERR_HANDLE, "vkCmdBindDescriptorSets was given a VkCommandBuffer handle that is not live (Anvil code -20002, stale or foreign handle); nothing was recorded.")
    ProcedureReturn
  EndIf
  If avkCmdState[c] <> #ANVIL_VK_CB_RECORDING
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdBindDescriptorSets was called on a command buffer that is not recording (Anvil code -20004, wrong command buffer state); call vkBeginCommandBuffer first.")
    ProcedureReturn
  EndIf
  If bindPoint <> #VK_PIPELINE_BIND_POINT_GRAPHICS
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdBindDescriptorSets was given a bind point that is not VK_PIPELINE_BIND_POINT_GRAPHICS (Anvil code -20005, unsupported bind point); there is no compute pipeline in this implementation.")
    ProcedureReturn
  EndIf
  If firstSet <> 0
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdBindDescriptorSets was asked to bind a set at an index other than zero (Anvil code -20005, unsupported set index); a pipeline layout here declares one descriptor set layout and its index is zero.")
    ProcedureReturn
  EndIf
  If dynamicCount <> 0
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdBindDescriptorSets was given dynamic offsets (Anvil code -20005, dynamic descriptors not implemented); the dynamic descriptor types are refused where a set layout is created, so there is nothing here for an offset to apply to.")
    ProcedureReturn
  EndIf
  lay = avkLaySlot(layout)
  If lay = 0
    avkCbFail(c, #ANVIL_VK_ERR_HANDLE, "vkCmdBindDescriptorSets was given a VkPipelineLayout handle that is not live (Anvil code -20002, stale or foreign handle); the command buffer is now invalid and vkEndCommandBuffer will say so.")
    ProcedureReturn
  EndIf
  d = avkPoolDev[avkCmdPool[c]]
  If avkLayDev[lay] <> d
    avkCbFail(c, #ANVIL_VK_ERR_OWNER, "vkCmdBindDescriptorSets was given a pipeline layout from a different VkDevice from the command buffer (Anvil code -20003, wrong parent); no descriptor binding state was changed.")
    ProcedureReturn
  EndIf
  If avkLaySetCount[lay] <> 1 Or avkLayBindingCount[lay] = 0
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdBindDescriptorSets was given a pipeline layout that declares no descriptor set layout (Anvil code -20001, layout mismatch); a set can only be bound through a layout that says what set zero is.")
    ProcedureReturn
  EndIf
  If AnvilVkDescriptorSetDeviceSlot(set) = 0
    avkCbFail(c, #ANVIL_VK_ERR_HANDLE, "vkCmdBindDescriptorSets was given a VkDescriptorSet handle that is not live (Anvil code -20002, stale or foreign handle); the command buffer is now invalid and vkEndCommandBuffer will say so.")
    ProcedureReturn
  EndIf
  If AnvilVkDescriptorSetDeviceSlot(set) <> d
    avkCbFail(c, #ANVIL_VK_ERR_OWNER, "vkCmdBindDescriptorSets was given a descriptor set from a different VkDevice from the command buffer and pipeline layout (Anvil code -20003, wrong parent); no descriptor binding state was changed.")
    ProcedureReturn
  EndIf
  If avkSetMatchesLayout(set, lay) = 0
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdBindDescriptorSets was given a descriptor set whose immutable binding schema is incompatible with the pipeline layout (Anvil code -20001, incompatible descriptor set); binding types, stages and binding count must match, but the source layout handles need not be identical.")
    ProcedureReturn
  EndIf
  avkCbDescSet[c] = set
  avkCbDescSetCount[c] = avkLaySetCount[lay]
  avkCbDescBindingCount[c] = avkLayBindingCount[lay]
  avkCbDescPushBytes[c] = avkLayPushBytes[lay]
  k = 0
  While k < #ANVIL_VK_MAX_SET_BINDINGS
    avkCbDescType[(c * #ANVIL_VK_MAX_SET_BINDINGS) + k] = avkLayBindingType[(lay * #ANVIL_VK_MAX_SET_BINDINGS) + k]
    avkCbDescStages[(c * #ANVIL_VK_MAX_SET_BINDINGS) + k] = avkLayBindingStages[(lay * #ANVIL_VK_MAX_SET_BINDINGS) + k]
    k = k + 1
  Wend
EndProcedure

Procedure AnvilVkCmdPushConstants(commandBuffer.i, layout.i, stageFlags.i, offset.i, size.i, *values)
  Define c.i
  Define lay.i
  Define k.i
  c = avkCmdSlot(commandBuffer)
  If c = 0
    avkFault(#ANVIL_VK_ERR_HANDLE, "vkCmdPushConstants was given a VkCommandBuffer handle that is not live (Anvil code -20002, stale or foreign handle); nothing was recorded.")
    ProcedureReturn
  EndIf
  If avkCmdState[c] <> #ANVIL_VK_CB_RECORDING
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdPushConstants was called on a command buffer that is not recording (Anvil code -20004, wrong command buffer state); call vkBeginCommandBuffer first.")
    ProcedureReturn
  EndIf
  lay = avkLaySlot(layout)
  If lay = 0
    avkCbFail(c, #ANVIL_VK_ERR_HANDLE, "vkCmdPushConstants was given a VkPipelineLayout handle that is not live (Anvil code -20002, stale or foreign handle); the command buffer is now invalid and vkEndCommandBuffer will say so.")
    ProcedureReturn
  EndIf
  If avkLayDev[lay] <> avkPoolDev[avkCmdPool[c]]
    avkCbFail(c, #ANVIL_VK_ERR_OWNER, "vkCmdPushConstants was given a pipeline layout from a different VkDevice from the command buffer (Anvil code -20003, wrong parent); no push-constant words were copied.")
    ProcedureReturn
  EndIf
  If avkLayPushBytes[lay] <> #ANVIL_VK_PUSH_BYTES
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdPushConstants was given a pipeline layout that declares no push constant range (Anvil code -20001, layout mismatch); declare a sixteen-byte fragment-stage range at offset zero when creating the layout.")
    ProcedureReturn
  EndIf
  If stageFlags <> #VK_SHADER_STAGE_FRAGMENT_BIT
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdPushConstants was given stage flags other than VK_SHADER_STAGE_FRAGMENT_BIT alone (Anvil code -20001, stage mismatch); the flags must be exactly the stages the layout's range declares, and that range is the fragment stage.")
    ProcedureReturn
  EndIf
  If offset <> 0 Or size <> #ANVIL_VK_PUSH_BYTES Or *values = 0
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdPushConstants was given other than the whole sixteen-byte block at offset zero (Anvil code -20001, invalid push range); a partial update would leave the rest of the block holding whatever the last pipeline left, and this slice does not keep it.")
    ProcedureReturn
  EndIf
  k = 0
  While k < 4
    avkCbPushWord[(c * 4) + k] = PeekL(*values + (k * 4)) & $FFFFFFFF
    k = k + 1
  Wend
  avkCbPushBytes[c] = #ANVIL_VK_PUSH_BYTES
EndProcedure

Procedure AnvilVkCmdDraw(commandBuffer.i, vertexCount.i, instanceCount.i, firstVertex.i, firstInstance.i)
  Define c.i
  Define p.i
  Define fb.i
  Define b.i
  Define k.i
  Define stride.i
  Define need.i
  Define sx.i
  Define sy.i
  Define sw.i
  Define sh.i
  Define vx.i
  Define vy.i
  Define vw.i
  Define vh.i
  c = avkCmdSlot(commandBuffer)
  If c = 0
    avkFault(#ANVIL_VK_ERR_HANDLE, "vkCmdDraw was given a VkCommandBuffer handle that is not live (Anvil code -20002, stale or foreign handle); nothing was recorded.")
    ProcedureReturn
  EndIf
  If avkCmdState[c] <> #ANVIL_VK_CB_RECORDING
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdDraw was called on a command buffer that is not recording (Anvil code -20004, wrong command buffer state); call vkBeginCommandBuffer first.")
    ProcedureReturn
  EndIf
  If avkCbRpActive[c] = 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdDraw was called outside a render pass (Anvil code -20004, no render pass); a draw belongs between vkCmdBeginRenderPass and vkCmdEndRenderPass, because the render pass is what says where the pixels go.")
    ProcedureReturn
  EndIf
  If vertexCount < 0
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdDraw was given a negative vertexCount (Anvil code -20001, invalid argument); vertexCount is an unsigned count in the Vulkan ABI.")
    ProcedureReturn
  EndIf
  ; A zero-vertex draw generates no work. In particular, it must not use
  ; the backend seam's one real-draw slot and make a following non-empty
  ; draw look like an unsupported second draw.
  If vertexCount = 0
    ProcedureReturn
  EndIf
  p = avkPipeSlot(avkCbPipe[c])
  If p = 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdDraw was called with no graphics pipeline bound (Anvil code -20004, no pipeline bound); call vkCmdBindPipeline before drawing, because the pipeline is what says which shaders run.")
    ProcedureReturn
  EndIf
  ; EVERY binding the pipeline describes must have a buffer bound to it.
  ; One bound buffer and two bindings is the shape that used to be
  ; impossible to write and is now easy to: the draw would fetch position
  ; from a live buffer and colour from address zero.
  k = 0
  While k < avkPipeBindCount[p]
    If avkBufSlot(avkCbVtxBuf[(c * #ANVIL_VK_MAX_BINDINGS) + k]) = 0
      avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdDraw was called with a binding this pipeline reads that has no vertex buffer bound to it (Anvil code -20004, no vertex buffer bound); call vkCmdBindVertexBuffers for every binding in the pipeline's vertex input state, not only for binding zero.")
      ProcedureReturn
    EndIf
    k = k + 1
  Wend
  fb = avkFbSlot(avkCbFbHandle[c])
  If fb = 0 Or fb <> avkCbFb[c]
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdDraw was called after its framebuffer was destroyed or replaced (Anvil code -20004, stale framebuffer reference); begin a new render pass against a current live framebuffer.")
    ProcedureReturn
  EndIf
  If avkPipeRp[p] <> avkFbRp[fb]
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdDraw was called with a pipeline created for a different render pass from the one that is begun (Anvil code -20001, incompatible render pass); a pipeline may only be used inside a render pass compatible with the one it was created against.")
    ProcedureReturn
  EndIf
  If instanceCount <> 1 Or firstInstance <> 0
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdDraw was asked for other than exactly one instance starting at instance zero (Anvil code -20005, instancing not implemented); the control list this backend writes draws one instance, so a second one would be declared and never drawn.")
    ProcedureReturn
  EndIf
  If firstVertex < 0
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdDraw was given a negative firstVertex (Anvil code -20001, invalid argument); the index of the first vertex is an unsigned count from the start of the bound buffer.")
    ProcedureReturn
  EndIf
  If avkPipeDynamicViewport[p] <> 0
    If avkCbViewportSet[c] = 0
      avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdDraw used a pipeline with VK_DYNAMIC_STATE_VIEWPORT before vkCmdSetViewport supplied that state (Anvil code -20004, dynamic viewport not set); command-buffer reset deliberately makes dynamic state undefined again.")
      ProcedureReturn
    EndIf
    vx = avkCbViewportX[c] : vy = avkCbViewportY[c]
    vw = avkCbViewportW[c] : vh = avkCbViewportH[c]
    If vw <> avkFbW[fb] Or vh <> avkFbH[fb]
      avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdDraw used a dynamic viewport that does not equal the active framebuffer geometry (Anvil code -20005, unsupported viewport); this bounded path supports resize by reusing a pipeline with one full-target viewport.")
      ProcedureReturn
    EndIf
  Else
    vx = avkPipeViewX[p] : vy = avkPipeViewY[p]
    vw = avkPipeViewW[p] : vh = avkPipeViewH[p]
  EndIf
  If avkPipeDynamicScissor[p] <> 0
    If avkCbScissorSet[c] = 0
      avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdDraw used a pipeline with VK_DYNAMIC_STATE_SCISSOR before vkCmdSetScissor supplied that state (Anvil code -20004, dynamic scissor not set); command-buffer reset deliberately makes dynamic state undefined again.")
      ProcedureReturn
    EndIf
    sx = avkCbScissorX[c] : sy = avkCbScissorY[c]
    sw = avkCbScissorW[c] : sh = avkCbScissorH[c]
  Else
    sx = avkPipeScissorX[p] : sy = avkPipeScissorY[p]
    sw = avkPipeScissorW[p] : sh = avkPipeScissorH[p]
  EndIf
  ; Every vertex the draw names must be inside EVERY bound buffer, each
  ; against its own binding's stride. Written as a difference so that an
  ; offset plus a length which wraps cannot pass, the same shape the image
  ; binder uses. Checking only binding zero would let a short colour
  ; buffer be fetched past its end for every vertex after the first few.
  k = 0
  While k < avkPipeBindCount[p]
    b = avkBufSlot(avkCbVtxBuf[(c * #ANVIL_VK_MAX_BINDINGS) + k])
    stride = avkPipeBindStride[(p * #ANVIL_VK_MAX_BINDINGS) + k]
    need = (firstVertex + vertexCount) * stride
    If stride <= 0 Or need <= 0 Or (avkBufSize[b] - avkCbVtxOffset[(c * #ANVIL_VK_MAX_BINDINGS) + k]) < need
      avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdDraw names vertices past the end of one of the bound vertex buffers (Anvil code -20001, vertex range outside the buffer); for every binding, firstVertex plus vertexCount multiplied by THAT binding's stride must fit between its bind offset and the end of its VkBuffer. Reading past it would be a GPU fetch from memory this allocation does not own.")
      ProcedureReturn
    EndIf
    k = k + 1
  Wend
  If avkPipeUsesPush[p] <> 0 And avkCbPushBytes[c] <> #ANVIL_VK_PUSH_BYTES
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdDraw was called with a pipeline whose fragment shader reads the push-constant block, and no push constants were recorded (Anvil code -20004, push constants not set); call vkCmdPushConstants before the draw, because an unset block would be whatever the memory happened to hold.")
    ProcedureReturn
  EndIf
  ; A UNIFORM COLOUR NEEDS A SET BOUND AND THAT SET'S BINDING WRITTEN.
  ; Three separate ways to arrive with nothing to read, and each is
  ; named: no set bound at all, a set bound through the wrong layout,
  ; and a set whose binding vkUpdateDescriptorSets never filled.
  If avkPipeUsesUniform[p] <> 0
    If avkCbDescSet[c] = 0
      avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdDraw was called with a pipeline whose fragment shader reads a uniform buffer, and no descriptor set was bound (Anvil code -20004, no descriptor set bound); call vkCmdBindDescriptorSets before the draw, because the set is what says which buffer the shader reads.")
      ProcedureReturn
    EndIf
    If avkCbMatchesPipe(c, p) = 0
      avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdDraw was called with descriptor state whose immutable set and push-range compatibility signature differs from the pipeline's (Anvil code -20001, incompatible layout); rebind through a compatible pipeline layout.")
      ProcedureReturn
    EndIf
    If AnvilVkDescriptorSetAddress(avkCbDescSet[c], avkPipeUniformBinding[p]) = 0
      avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdDraw was called with a descriptor set whose binding has no buffer written into it, or whose buffer has since been destroyed (Anvil code -20004, descriptor not written); call vkUpdateDescriptorSets for the binding the fragment shader's Binding decoration names.")
      ProcedureReturn
    EndIf
    If AnvilVkDescriptorSetRange(avkCbDescSet[c], avkPipeUniformBinding[p]) < #ANVIL_VK_UNIFORM_BYTES
      avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdDraw was called with a descriptor whose range is shorter than the sixteen-byte block the fragment shader reads (Anvil code -20001, range too short); the block is one four-component colour.")
      ProcedureReturn
    EndIf
  EndIf
  If avkPipeUsesSample[p] <> 0
    If avkCbDescSet[c] = 0
      avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdDraw was called with a pipeline whose fragment shader samples an image, and no descriptor set was bound (Anvil code -20004, no descriptor set bound); bind the set that owns the combined image sampler before the draw.")
      ProcedureReturn
    EndIf
    If avkCbMatchesPipe(c, p) = 0
      avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdDraw was called with sampled descriptor state whose immutable set and push-range compatibility signature differs from the pipeline's (Anvil code -20001, incompatible layout); rebind through a compatible pipeline layout.")
      ProcedureReturn
    EndIf
    If AnvilVkDescriptorSetSampledImage(avkCbDescSet[c], avkPipeSampleBinding[p], @avkSampleStage) = 0
      avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdDraw was called with a combined image sampler that is unwritten, stale, unbound or no longer in VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL (Anvil code -20004, sampled descriptor not ready); update the binding and transition the live sampled image before drawing.")
      ProcedureReturn
    EndIf
  EndIf
  If avkRecordedDrawAppend(c, firstVertex, vertexCount, vx, vy, vw, vh, sx, sy, sw, sh, 0, 0, 0) < 1
    avkCbFail(c, #VK_ERROR_OUT_OF_HOST_MEMORY, "vkCmdDraw exhausted the shared 4096-entry recorded-draw pool (VkResult -1, VK_ERROR_OUT_OF_HOST_MEMORY); no partial draw was linked. Reset or free command buffers that own older draws before recording more.")
    ProcedureReturn
  EndIf
EndProcedure

Procedure AnvilVkCmdBindIndexBuffer(commandBuffer.i, buffer.i, offset.i, indexType.i)
  Define c.i
  Define b.i
  Define indexBytes.i
  c = avkCmdSlot(commandBuffer)
  If c = 0
    avkFault(#ANVIL_VK_ERR_HANDLE, "vkCmdBindIndexBuffer was given a VkCommandBuffer handle that is not live (Anvil code -20002, stale or foreign handle); nothing was recorded.")
    ProcedureReturn
  EndIf
  If avkCmdState[c] <> #ANVIL_VK_CB_RECORDING
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdBindIndexBuffer was called on a command buffer that is not recording (Anvil code -20004, wrong command buffer state); call vkBeginCommandBuffer first.")
    ProcedureReturn
  EndIf
  If indexType = #VK_INDEX_TYPE_UINT16
    indexBytes = 2
  ElseIf indexType = #VK_INDEX_TYPE_UINT32
    indexBytes = 4
  Else
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdBindIndexBuffer was given an index type other than VK_INDEX_TYPE_UINT16 or VK_INDEX_TYPE_UINT32 (Anvil code -20005, unsupported index type); eight-bit and extension index types are not implemented.")
    ProcedureReturn
  EndIf
  b = avkBufSlot(buffer)
  If b = 0
    avkCbFail(c, #ANVIL_VK_ERR_HANDLE, "vkCmdBindIndexBuffer was given a VkBuffer handle that is not live (Anvil code -20002, stale or foreign handle); no index binding state was changed.")
    ProcedureReturn
  EndIf
  If avkBufDev[b] <> avkPoolDev[avkCmdPool[c]]
    avkCbFail(c, #ANVIL_VK_ERR_OWNER, "vkCmdBindIndexBuffer was given a buffer from a different VkDevice (Anvil code -20003, wrong parent); every object recorded into one command buffer must share one device.")
    ProcedureReturn
  EndIf
  If avkBufBound[b] = 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdBindIndexBuffer was given a buffer with no memory bound (Anvil code -20004, buffer not bound); call vkBindBufferMemory first.")
    ProcedureReturn
  EndIf
  If (avkBufUsage[b] & #VK_BUFFER_USAGE_INDEX_BUFFER_BIT) = 0
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdBindIndexBuffer was given a buffer not created with VK_BUFFER_USAGE_INDEX_BUFFER_BIT (Anvil code -20001, missing usage); recreate it with index-buffer usage.")
    ProcedureReturn
  EndIf
  If offset < 0 Or offset >= avkBufSize[b] Or (offset % indexBytes) <> 0
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdBindIndexBuffer was given an offset outside the buffer or misaligned for its index type (Anvil code -20001, invalid bind offset); UINT16 needs two-byte alignment and UINT32 needs four-byte alignment.")
    ProcedureReturn
  EndIf
  avkCbIndexBuf[c] = buffer
  avkCbIndexOffset[c] = offset
  avkCbIndexType[c] = indexType
EndProcedure

; Core indexed drawing, deliberately bounded to one instance, zero base
; vertex/base instance and the pipeline's triangle-list topology. Index bytes
; remain application memory: submission preflight re-resolves and scans the
; live uint16/uint32 range before any fence, retain counter or backend job
; changes state.
Procedure AnvilVkCmdDrawIndexed(commandBuffer.i, indexCount.i, instanceCount.i, firstIndex.i, vertexOffset.i, firstInstance.i)
  Define c.i
  Define p.i
  Define fb.i
  Define b.i
  Define k.i
  Define indexBytes.i
  Define available.i
  Define sx.i
  Define sy.i
  Define sw.i
  Define sh.i
  Define vx.i
  Define vy.i
  Define vw.i
  Define vh.i
  c = avkCmdSlot(commandBuffer)
  If c = 0
    avkFault(#ANVIL_VK_ERR_HANDLE, "vkCmdDrawIndexed was given a VkCommandBuffer handle that is not live (Anvil code -20002, stale or foreign handle); nothing was recorded.")
    ProcedureReturn
  EndIf
  If avkCmdState[c] <> #ANVIL_VK_CB_RECORDING
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdDrawIndexed was called on a command buffer that is not recording (Anvil code -20004, wrong command buffer state); call vkBeginCommandBuffer first.")
    ProcedureReturn
  EndIf
  If avkCbRpActive[c] = 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdDrawIndexed was called outside a render pass (Anvil code -20004, no render pass); begin a compatible render pass first.")
    ProcedureReturn
  EndIf
  If indexCount < 0
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdDrawIndexed was given a negative indexCount (Anvil code -20001, invalid argument); indexCount is unsigned in the Vulkan ABI.")
    ProcedureReturn
  EndIf
  If indexCount = 0
    ProcedureReturn
  EndIf
  p = avkPipeSlot(avkCbPipe[c])
  If p = 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdDrawIndexed was called with no graphics pipeline bound (Anvil code -20004, no pipeline bound); call vkCmdBindPipeline first.")
    ProcedureReturn
  EndIf
  k = 0
  While k < avkPipeBindCount[p]
    If avkBufSlot(avkCbVtxBuf[(c * #ANVIL_VK_MAX_BINDINGS) + k]) = 0
      avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdDrawIndexed has no live vertex buffer for a binding the pipeline reads (Anvil code -20004, no vertex buffer bound); bind every declared vertex binding.")
      ProcedureReturn
    EndIf
    k = k + 1
  Wend
  fb = avkFbSlot(avkCbFbHandle[c])
  If fb = 0 Or fb <> avkCbFb[c]
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdDrawIndexed was called after its framebuffer was destroyed or replaced (Anvil code -20004, stale framebuffer reference); begin a new render pass.")
    ProcedureReturn
  EndIf
  If avkPipeRp[p] <> avkFbRp[fb]
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdDrawIndexed used a pipeline incompatible with the active render pass (Anvil code -20001, incompatible render pass); bind a compatible pipeline.")
    ProcedureReturn
  EndIf
  If instanceCount <> 1 Or firstInstance <> 0
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdDrawIndexed was asked for instancing or a nonzero firstInstance (Anvil code -20005, instancing not implemented); this backend executes exactly one instance starting at zero.")
    ProcedureReturn
  EndIf
  If vertexOffset <> 0
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdDrawIndexed was given a nonzero vertexOffset (Anvil code -20005, base vertex not implemented); this tranche accepts indices relative to vertex zero.")
    ProcedureReturn
  EndIf
  If firstIndex < 0
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdDrawIndexed was given a negative firstIndex (Anvil code -20001, invalid argument); firstIndex is unsigned in the Vulkan ABI.")
    ProcedureReturn
  EndIf
  b = avkBufSlot(avkCbIndexBuf[c])
  If b = 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdDrawIndexed was called with no live index buffer bound (Anvil code -20004, no index buffer bound); call vkCmdBindIndexBuffer first.")
    ProcedureReturn
  EndIf
  If avkBufDev[b] <> avkPoolDev[avkCmdPool[c]] Or avkBufBound[b] = 0 Or (avkBufUsage[b] & #VK_BUFFER_USAGE_INDEX_BUFFER_BIT) = 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdDrawIndexed found an unbound, wrong-device or non-index-usage buffer in index state (Anvil code -20004, invalid index buffer); bind a live INDEX_BUFFER buffer owned by this device.")
    ProcedureReturn
  EndIf
  If avkCbIndexType[c] = #VK_INDEX_TYPE_UINT16
    indexBytes = 2
  ElseIf avkCbIndexType[c] = #VK_INDEX_TYPE_UINT32
    indexBytes = 4
  Else
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdDrawIndexed found unsupported index type state (Anvil code -20004, invalid index binding); rebind UINT16 or UINT32 indices.")
    ProcedureReturn
  EndIf
  If avkCbIndexOffset[c] < 0 Or avkCbIndexOffset[c] >= avkBufSize[b] Or (avkCbIndexOffset[c] % indexBytes) <> 0
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdDrawIndexed found a misaligned or out-of-range index-buffer bind offset (Anvil code -20001, invalid index range); rebind the buffer at an aligned byte inside it.")
    ProcedureReturn
  EndIf
  available = avkBufSize[b] - avkCbIndexOffset[c]
  If firstIndex > (available / indexBytes) Or indexCount > ((available / indexBytes) - firstIndex)
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdDrawIndexed names indices past the bound VkBuffer (Anvil code -20001, index range outside buffer); firstIndex plus indexCount must fit at the selected index width.")
    ProcedureReturn
  EndIf
  If avkPipeDynamicViewport[p] <> 0
    If avkCbViewportSet[c] = 0
      avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdDrawIndexed used dynamic viewport before vkCmdSetViewport supplied it (Anvil code -20004, dynamic viewport not set); set the viewport first.")
      ProcedureReturn
    EndIf
    vx = avkCbViewportX[c] : vy = avkCbViewportY[c]
    vw = avkCbViewportW[c] : vh = avkCbViewportH[c]
    If vw <> avkFbW[fb] Or vh <> avkFbH[fb]
      avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdDrawIndexed used a dynamic viewport that does not equal the active framebuffer geometry (Anvil code -20005, unsupported viewport); this bounded path supports one full-target viewport.")
      ProcedureReturn
    EndIf
  Else
    vx = avkPipeViewX[p] : vy = avkPipeViewY[p]
    vw = avkPipeViewW[p] : vh = avkPipeViewH[p]
  EndIf
  If avkPipeDynamicScissor[p] <> 0
    If avkCbScissorSet[c] = 0
      avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdDrawIndexed used dynamic scissor before vkCmdSetScissor supplied it (Anvil code -20004, dynamic scissor not set); set the scissor first.")
      ProcedureReturn
    EndIf
    sx = avkCbScissorX[c] : sy = avkCbScissorY[c]
    sw = avkCbScissorW[c] : sh = avkCbScissorH[c]
  Else
    sx = avkPipeScissorX[p] : sy = avkPipeScissorY[p]
    sw = avkPipeScissorW[p] : sh = avkPipeScissorH[p]
  EndIf
  If avkPipeUsesPush[p] <> 0 And avkCbPushBytes[c] <> #ANVIL_VK_PUSH_BYTES
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdDrawIndexed is missing the push-constant block its fragment shader reads (Anvil code -20004, push constants not set); set the complete block first.")
    ProcedureReturn
  EndIf
  If avkPipeUsesUniform[p] <> 0
    If avkCbDescSet[c] = 0 Or avkCbMatchesPipe(c, p) = 0 Or AnvilVkDescriptorSetAddress(avkCbDescSet[c], avkPipeUniformBinding[p]) = 0
      avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdDrawIndexed has no compatible written uniform descriptor (Anvil code -20004, descriptor not ready); bind and update the pipeline's set.")
      ProcedureReturn
    EndIf
    If AnvilVkDescriptorSetRange(avkCbDescSet[c], avkPipeUniformBinding[p]) < #ANVIL_VK_UNIFORM_BYTES
      avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdDrawIndexed has a uniform descriptor shorter than the block its shader reads (Anvil code -20001, range too short); update it with at least sixteen bytes.")
      ProcedureReturn
    EndIf
  EndIf
  If avkPipeUsesSample[p] <> 0
    If avkCbDescSet[c] = 0 Or avkCbMatchesPipe(c, p) = 0 Or AnvilVkDescriptorSetSampledImage(avkCbDescSet[c], avkPipeSampleBinding[p], @avkSampleStage) = 0
      avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdDrawIndexed has no compatible ready sampled-image descriptor (Anvil code -20004, sampled descriptor not ready); bind a live sampled image in SHADER_READ_ONLY_OPTIMAL.")
      ProcedureReturn
    EndIf
  EndIf
  If avkRecordedDrawAppend(c, firstIndex, indexCount, vx, vy, vw, vh, sx, sy, sw, sh, avkCbIndexBuf[c], avkCbIndexOffset[c], avkCbIndexType[c]) < 1
    avkCbFail(c, #VK_ERROR_OUT_OF_HOST_MEMORY, "vkCmdDrawIndexed exhausted the shared 4096-entry recorded-draw pool (VkResult -1, VK_ERROR_OUT_OF_HOST_MEMORY); no partial draw was linked.")
  EndIf
EndProcedure

Procedure AnvilVkCmdEndRenderPass(commandBuffer.i)
  Define c.i
  c = avkCmdSlot(commandBuffer)
  If c = 0
    avkFault(#ANVIL_VK_ERR_HANDLE, "vkCmdEndRenderPass was given a VkCommandBuffer handle that is not live (Anvil code -20002, stale or foreign handle); nothing was recorded.")
    ProcedureReturn
  EndIf
  If avkCmdState[c] <> #ANVIL_VK_CB_RECORDING
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdEndRenderPass was called on a command buffer that is not recording (Anvil code -20004, wrong command buffer state); call vkBeginCommandBuffer first.")
    ProcedureReturn
  EndIf
  If avkCbRpActive[c] = 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdEndRenderPass was called outside a render pass (Anvil code -20004, no render pass is open); every vkCmdEndRenderPass matches one vkCmdBeginRenderPass.")
    ProcedureReturn
  EndIf
  avkCbRpActive[c] = 0
  avkCbRpDone[c] = 1
EndProcedure

; ======================================================================
;  THE DRAW, AS THE BACKEND RECEIVES IT
; ======================================================================
CompilerIf 0
;  These three are declared in vk_command.pbi and defined here, because
;  the submission engine must not know what a pipeline is and this file
;  must not own the flight.

; The VkBuffer this draw's descriptor names, or 0. One procedure, so the
; retain and the release cannot ever disagree about which buffer it was.
Procedure.i avkDrawUniformBuffer(c.i, p.i)
  If avkPipeUsesUniform[p] = 0 : ProcedureReturn 0 : EndIf
  If avkCbDescSet[c] = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn AnvilVkDescriptorSetBuffer(avkCbDescSet[c], avkPipeUniformBinding[p])
EndProcedure

; The VkImage this draw's combined sampler names, or 0. As with the uniform
; helper, retain and release share this one owner lookup so they cannot drift.
Procedure.i avkDrawSampleImage(c.i, p.i)
  If avkPipeUsesSample[p] = 0 : ProcedureReturn 0 : EndIf
  If avkCbDescSet[c] = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn AnvilVkDescriptorSetSampledImageHandle(avkCbDescSet[c], avkPipeSampleBinding[p])
EndProcedure

; The render-target view belongs to the submission flight, not specifically
; to shader resource retention. Keeping this pair at the flight boundary also
; covers a render-pass submission whose backend work does not read descriptors.
Procedure avkAttachmentViewRetain(c.i)
  Define fb.i = avkCbFb[c]
  Define iv.i
  If fb > 0
    iv = avkFbView[fb]
    If iv > 0 : avkIvInFlight[iv] = avkIvInFlight[iv] + 1 : EndIf
  EndIf
EndProcedure

Procedure avkAttachmentViewRelease(c.i)
  Define fb.i = avkCbFb[c]
  Define iv.i
  If fb > 0
    iv = avkFbView[fb]
    If iv > 0 And avkIvInFlight[iv] > 0 : avkIvInFlight[iv] = avkIvInFlight[iv] - 1 : EndIf
  EndIf
EndProcedure

; EVERY buffer the draw reads is retained, not just the first. A colour
; buffer destroyed while the submission is in flight is exactly as fatal
; as a position buffer destroyed then, and the count that stops that is
; per buffer.
Procedure avkDrawRetain(c.i)
  Define b.i
  Define p.i
  Define k.i
  Define image.i
  Define img.i
  Define sampler.i
  Define samp.i
  Define view.i
  Define iv.i
  If avkCbDrawCount[c] = 0
    ProcedureReturn
  EndIf
  p = avkPipeSlot(avkCbPipe[c])
  If p = 0
    ProcedureReturn
  EndIf
  k = 0
  While k < avkPipeBindCount[p]
    b = avkBufSlot(avkCbVtxBuf[(c * #ANVIL_VK_MAX_BINDINGS) + k])
    If b <> 0
      avkBufInFlight[b] = avkBufInFlight[b] + 1
      avkMemInFlight[avkBufMemSlot[b]] = avkMemInFlight[avkBufMemSlot[b]] + 1
    EndIf
    k = k + 1
  Wend
  ; The uniform buffer a bound descriptor names is read by this draw too,
  ; so it is retained the same way - vkDestroyBuffer refuses while the
  ; count is up, and that is what stops a colour being read out of an
  ; allocation the application has already freed.
  b = avkBufSlot(avkDrawUniformBuffer(c, p))
  If b <> 0
    avkBufInFlight[b] = avkBufInFlight[b] + 1
    avkMemInFlight[avkBufMemSlot[b]] = avkMemInFlight[avkBufMemSlot[b]] + 1
  EndIf
  image = avkDrawSampleImage(c, p)
  img = avkImgSlot(image)
  If img <> 0
    avkImgInFlight[img] = avkImgInFlight[img] + 1
    avkMemInFlight[avkImgMemSlot[img]] = avkMemInFlight[avkImgMemSlot[img]] + 1
  EndIf
  If avkPipeUsesSample[p] <> 0
    sampler = AnvilVkDescriptorSetSamplerHandle(avkCbDescSet[c], avkPipeSampleBinding[p])
    samp = avkSamplerSlot(sampler)
    If samp <> 0 : avkSampInFlight[samp] = avkSampInFlight[samp] + 1 : EndIf
    view = AnvilVkDescriptorSetImageViewHandle(avkCbDescSet[c], avkPipeSampleBinding[p])
    iv = avkIvSlot(view)
    If iv <> 0 : avkIvInFlight[iv] = avkIvInFlight[iv] + 1 : EndIf
  EndIf
EndProcedure

Procedure avkDrawRelease(c.i)
  Define b.i
  Define p.i
  Define k.i
  Define image.i
  Define img.i
  Define sampler.i
  Define samp.i
  Define view.i
  Define iv.i
  If avkCbDrawCount[c] = 0
    ProcedureReturn
  EndIf
  p = avkPipeSlot(avkCbPipe[c])
  If p = 0
    ProcedureReturn
  EndIf
  k = 0
  While k < avkPipeBindCount[p]
    b = avkBufSlot(avkCbVtxBuf[(c * #ANVIL_VK_MAX_BINDINGS) + k])
    If b <> 0
      If avkBufInFlight[b] > 0 : avkBufInFlight[b] = avkBufInFlight[b] - 1 : EndIf
      If avkMemInFlight[avkBufMemSlot[b]] > 0
        avkMemInFlight[avkBufMemSlot[b]] = avkMemInFlight[avkBufMemSlot[b]] - 1
      EndIf
    EndIf
    k = k + 1
  Wend
  b = avkBufSlot(avkDrawUniformBuffer(c, p))
  If b <> 0
    If avkBufInFlight[b] > 0 : avkBufInFlight[b] = avkBufInFlight[b] - 1 : EndIf
    If avkMemInFlight[avkBufMemSlot[b]] > 0
      avkMemInFlight[avkBufMemSlot[b]] = avkMemInFlight[avkBufMemSlot[b]] - 1
    EndIf
  EndIf
  image = avkDrawSampleImage(c, p)
  img = avkImgSlot(image)
  If img <> 0
    If avkImgInFlight[img] > 0 : avkImgInFlight[img] = avkImgInFlight[img] - 1 : EndIf
    If avkMemInFlight[avkImgMemSlot[img]] > 0
      avkMemInFlight[avkImgMemSlot[img]] = avkMemInFlight[avkImgMemSlot[img]] - 1
    EndIf
  EndIf
  If avkPipeUsesSample[p] <> 0
    sampler = AnvilVkDescriptorSetSamplerHandle(avkCbDescSet[c], avkPipeSampleBinding[p])
    samp = avkSamplerSlot(sampler)
    If samp <> 0 And avkSampInFlight[samp] > 0 : avkSampInFlight[samp] = avkSampInFlight[samp] - 1 : EndIf
    view = AnvilVkDescriptorSetImageViewHandle(avkCbDescSet[c], avkPipeSampleBinding[p])
    iv = avkIvSlot(view)
    If iv <> 0 And avkIvInFlight[iv] > 0 : avkIvInFlight[iv] = avkIvInFlight[iv] - 1 : EndIf
  EndIf
EndProcedure

; Resolve the exact generations of every retained render-target dependency
; before vkQueueSubmit changes any observable state. Slots remain caches only.
Procedure.i avkDrawPreflight(c.i)
  Define p.i
  Define b.i
  Define fb.i
  Define img.i
  Define iv.i
  Define rp.i
  Define k.i

  p = avkPipeSlot(avkCbPipe[c])
  fb = avkFbSlot(avkCbFbHandle[c])
  If p = 0 Or fb = 0 Or fb <> avkCbFb[c]
    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit was given a command buffer whose pipeline or framebuffer has since been destroyed or replaced (Anvil code -20004, stale resource reference); re-record the command buffer against live objects.")
  EndIf
  ; Resolve BOTH descriptor families before vkQueueSubmit acquires a fence,
  ; commits semaphores, raises in-flight counts or calls the backend. A mixed
  ; draw is one transaction: a valid UBO cannot make a stale sampler a late
  ; partial submission, and the reverse is equally true.
  If avkPipeUsesUniform[p] <> 0 Or avkPipeUsesSample[p] <> 0
    If avkCbDescSet[c] = 0 Or AnvilVkDescriptorSetDeviceSlot(avkCbDescSet[c]) <> avkPipeDev[p]
      ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit was given a draw whose descriptor set is stale or belongs to a different device (Anvil code -20004, stale descriptor state); nothing was submitted.")
    EndIf
    If avkCbMatchesPipe(c, p) = 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit was given descriptor state incompatible with the recorded pipeline's immutable layout signature (Anvil code -20004, incompatible descriptor state); nothing was submitted.")
    EndIf
  EndIf
  If avkPipeUsesUniform[p] <> 0
    If AnvilVkDescriptorSetAddress(avkCbDescSet[c], avkPipeUniformBinding[p]) = 0 Or AnvilVkDescriptorSetRange(avkCbDescSet[c], avkPipeUniformBinding[p]) < #ANVIL_VK_UNIFORM_BYTES
      ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found the recorded uniform-buffer descriptor unwritten or stale (Anvil code -20004, descriptor not ready); nothing was submitted.")
    EndIf
  EndIf
  If avkPipeUsesSample[p] <> 0
    If AnvilVkDescriptorSetSampledImage(avkCbDescSet[c], avkPipeSampleBinding[p], @avkSampleStage) = 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found the recorded combined-image-sampler descriptor unwritten or stale (Anvil code -20004, sampled descriptor not ready); nothing was submitted.")
    EndIf
  EndIf
  rp = avkRpSlot(avkFbRpHandle[fb])
  iv = avkIvSlot(avkFbViewHandle[fb])
  If rp = 0 Or rp <> avkFbRp[fb] Or iv = 0 Or iv <> avkFbView[fb]
    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit was given a command buffer whose framebuffer dependencies have since been destroyed or replaced (Anvil code -20004, stale render pass or image view); re-record against a framebuffer built from current live handles.")
  EndIf
  k = 0
  While k < avkPipeBindCount[p]
    If avkBufSlot(avkCbVtxBuf[(c * #ANVIL_VK_MAX_BINDINGS) + k]) = 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit was given a command buffer one of whose bound vertex buffers has since been destroyed (Anvil code -20004, stale resource reference); re-record the command buffer against live objects.")
    EndIf
    k = k + 1
  Wend
  img = avkImgSlot(avkIvImage[iv])
  If img = 0 Or img <> avkIvImgSlot[iv] Or avkImgBound[img] = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit was given a command buffer whose colour attachment has since been destroyed, replaced or unbound (Anvil code -20004, stale resource reference); re-record the command buffer against live resources.")
  EndIf
  ProcedureReturn #ANVIL_VK_OK
EndProcedure

; Build the one closed draw and hand it over. Returns the backend's
; answer, or -1 when the backend refused or faulted.
Procedure.i avkDrawSubmit(c.i)
  Define p.i
  Define b.i
  Define fb.i
  Define img.i
  Define iv.i
  Define k.i
  Define rc.i

  If avkDrawPreflight(c) <> #ANVIL_VK_OK : ProcedureReturn -1 : EndIf
  p = avkPipeSlot(avkCbPipe[c])
  ; Preflight above resolved every generation-tagged handle. From this point
  ; the cached slots are safe for this externally synchronized submission.
  fb = avkCbFb[c]
  iv = avkFbView[fb]
  img = avkIvImgSlot[iv]
  ; The push-constant block is copied out of the recording into storage
  ; this file owns, so the address handed to the backend outlives the
  ; caller's own buffer.
  k = 0
  While k < 4
    avkPushStage[k] = avkCbPushWord[(c * 4) + k]
    k = k + 1
  Wend

  avkDrawRecord\pipeline = p
  avkDrawRecord\targetBase = avkHeapBase + avkMemOffset[avkImgMemSlot[img]] + avkImgMemOffset[img]
  avkDrawRecord\targetBytes = avkImgSize[img]
  avkDrawRecord\width = avkImgW[img]
  avkDrawRecord\height = avkImgH[img]
  avkDrawRecord\pitch = avkImgPitch[img]
  avkDrawRecord\clearBgra = avkCbClearWord[c]
  avkDrawRecord\bindingCount = avkPipeBindCount[p]
  avkDrawRecord\bindings = @avkBindStage[0]
  k = 0
  While k < #ANVIL_VK_MAX_BINDINGS
    If k < avkPipeBindCount[p]
      b = avkBufSlot(avkCbVtxBuf[(c * #ANVIL_VK_MAX_BINDINGS) + k])
      avkBindStage[(k * 2) + 0] = avkHeapBase + avkMemOffset[avkBufMemSlot[b]] + avkBufMemOffset[b] + avkCbVtxOffset[(c * #ANVIL_VK_MAX_BINDINGS) + k]
      avkBindStage[(k * 2) + 1] = avkPipeBindStride[(p * #ANVIL_VK_MAX_BINDINGS) + k]
    Else
      ; A BINDING THIS PIPELINE DOES NOT HAVE IS ZERO, every time. The
      ; record's bytes are compared against an independent expectation,
      ; and a stale address left over from the previous draw would make
      ; that comparison depend on what ran before it.
      avkBindStage[(k * 2) + 0] = 0
      avkBindStage[(k * 2) + 1] = 0
    EndIf
    k = k + 1
  Wend
  avkDrawRecord\vertexCount = avkCbDrawVerts[c]
  avkDrawRecord\firstVertex = avkCbDrawFirst[c]
  avkDrawRecord\sampleMask = avkPipeSampleMask[p]
  avkDrawRecord\blendMode = avkPipeBlendMode[p]
  avkDrawRecord\viewportX = avkRecordedDraw[avkCbDrawHead[c]]\viewportX
  avkDrawRecord\viewportY = avkRecordedDraw[avkCbDrawHead[c]]\viewportY
  avkDrawRecord\viewportW = avkRecordedDraw[avkCbDrawHead[c]]\viewportW
  avkDrawRecord\viewportH = avkRecordedDraw[avkCbDrawHead[c]]\viewportH
  If avkPipeDynamicScissor[p] <> 0
    avkDrawRecord\scissorX = avkCbScissorX[c] : avkDrawRecord\scissorY = avkCbScissorY[c]
    avkDrawRecord\scissorW = avkCbScissorW[c] : avkDrawRecord\scissorH = avkCbScissorH[c]
  Else
    avkDrawRecord\scissorX = avkPipeScissorX[p] : avkDrawRecord\scissorY = avkPipeScissorY[p]
    avkDrawRecord\scissorW = avkPipeScissorW[p] : avkDrawRecord\scissorH = avkPipeScissorH[p]
  EndIf
  If avkCbPushBytes[c] = #ANVIL_VK_PUSH_BYTES
    avkDrawRecord\pushBase = @avkPushStage[0]
    avkDrawRecord\pushBytes = #ANVIL_VK_PUSH_BYTES
  Else
    avkDrawRecord\pushBase = 0
    avkDrawRecord\pushBytes = 0
  EndIf
  ; THE DESCRIPTOR IS RESOLVED HERE, at submit time and not at bind time:
  ; a VkBuffer can be rebound to different memory between the two, so an
  ; address captured earlier would be the one number in this record that
  ; was not current. It is zero unless this pipeline's colour comes from
  ; a uniform buffer, so a backend cannot read a stale one by accident.
  avkDrawRecord\uniformBase = 0
  avkDrawRecord\uniformBytes = 0
  If avkPipeUsesUniform[p] <> 0 And avkCbDescSet[c] <> 0
    avkDrawRecord\uniformBase = AnvilVkDescriptorSetAddress(avkCbDescSet[c], avkPipeUniformBinding[p])
    avkDrawRecord\uniformBytes = AnvilVkDescriptorSetRange(avkCbDescSet[c], avkPipeUniformBinding[p])
  EndIf
  If avkPipeUsesUniform[p] <> 0 And avkDrawRecord\uniformBase = 0
    avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit was given a command buffer whose descriptor set, or the buffer written into it, has since been destroyed (Anvil code -20004, stale resource reference); re-record the command buffer against live objects.")
    ProcedureReturn -1
  EndIf
  avkDrawRecord\sampledImage = 0
  If avkPipeUsesSample[p] <> 0
    If avkCbDescSet[c] = 0 Or AnvilVkDescriptorSetSampledImage(avkCbDescSet[c], avkPipeSampleBinding[p], @avkSampleStage) = 0
      avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit was given a command buffer whose combined image sampler, image view, sampler or sampled image is no longer live and ready (Anvil code -20004, stale sampled descriptor); re-record the command buffer against live objects in shader-read layout.")
      ProcedureReturn -1
    EndIf
    avkDrawRecord\sampledImage = @avkSampleStage
  EndIf

  rc = avkBackendDrawSupported(avkDrawRecord\targetBase, avkDrawRecord\targetBytes, avkDrawRecord\width, avkDrawRecord\height, avkDrawRecord\pitch)
  If rc <> #VK_SUCCESS
    avkFault(rc, "the graphics backend cannot render into an attachment of this size or at this address (VkResult or Anvil code in AnvilVkFaultCode(); nothing was submitted). The Pi 4 V3D backend renders only at the geometry the engine was initialised with, and never into the buffer the display is scanning out.")
    ProcedureReturn -1
  EndIf
  ProcedureReturn avkBackendSubmitDraw(@avkDrawRecord)
EndProcedure

CompilerEndIf

; ======================================================================
;  CLOSED MULTI-DRAW FLIGHT
; ======================================================================
Procedure.i avkFlightVertexIndex(draw.i, binding.i)
  ProcedureReturn (draw * #ANVIL_VK_MAX_BINDINGS) + binding
EndProcedure

Procedure.i avkDrawSetMatchesPipe(set.i, p.i)
  Define k.i
  If avkPipeSetCount[p] = 0 : ProcedureReturn 1 : EndIf
  If AnvilVkDescriptorSetDeviceSlot(set) <> avkPipeDev[p] : ProcedureReturn 0 : EndIf
  If AnvilVkDescriptorSetSchemaCount(set) <> avkPipeBindingCount[p] : ProcedureReturn 0 : EndIf
  k = 0
  While k < avkPipeBindingCount[p]
    If AnvilVkDescriptorSetSchemaType(set, k) <> avkPipeBindingType[(p * #ANVIL_VK_MAX_SET_BINDINGS) + k] : ProcedureReturn 0 : EndIf
    If AnvilVkDescriptorSetSchemaStages(set, k) <> avkPipeBindingStages[(p * #ANVIL_VK_MAX_SET_BINDINGS) + k] : ProcedureReturn 0 : EndIf
    k = k + 1
  Wend
  ProcedureReturn 1
EndProcedure

; Close every recorded draw before the submission acquires or commits
; anything. This procedure only writes private staging. Every public lifetime
; counter, fence, semaphore, command state and backend job remains untouched
; until every generation-tagged handle in the list has resolved successfully.
Procedure.i avkDrawListPreflight(c.i)
  Define count.i
  Define draw.i
  Define slot.i
  Define nextSlot.i
  Define p.i
  Define fb.i
  Define rp.i
  Define iv.i
  Define img.i
  Define mem.i
  Define set.i
  Define ds.i
  Define b.i
  Define ub.i
  Define simg.i
  Define samp.i
  Define siv.i
  Define k.i
  Define idx.i
  Define baseIdx.i
  Define stride.i
  Define bindingMem.i
  Define available.i
  Define indexBytes.i
  Define indexAddress.i
  Define indexValue.i
  Define maxVertex.i
  Define indexMem.i
  Define address.i
  Define range.i
  Define image.i
  Define sampler.i
  Define view.i
  Define rc.i

  avkFlightDrawCount = 0
  avkFlightLedgerCommitted = 0
  avkFlightDrawPreparedCb = 0
  avkFlightDrawOwnerCb = 0
  count = avkCbDrawCount[c]
  If count < 1 Or count > #ANVIL_VK_MAX_RECORDED_DRAWS
    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found an invalid recorded-draw count (Anvil code -20004, corrupt draw list); nothing was submitted.")
  EndIf
  If count > 1 And (avkBackendCaps() & #ANVIL_VK_CAP_DRAW_LIST) = 0
    ProcedureReturn avkFault(#VK_ERROR_FEATURE_NOT_PRESENT, "vkQueueSubmit contains more than one draw but the active graphics backend does not advertise an atomic draw-list transaction (VkResult -8, VK_ERROR_FEATURE_NOT_PRESENT); nothing was submitted. The backend must consume one closed list with one frame begin and end.")
  EndIf
  fb = avkFbSlot(avkCbFbHandle[c])
  If fb = 0 Or fb <> avkCbFb[c]
    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit was given a draw list whose framebuffer has since been destroyed or replaced (Anvil code -20004, stale framebuffer); nothing was submitted.")
  EndIf
  rp = avkRpSlot(avkFbRpHandle[fb])
  iv = avkIvSlot(avkFbViewHandle[fb])
  If rp = 0 Or rp <> avkFbRp[fb] Or iv = 0 Or iv <> avkFbView[fb]
    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit was given a draw list whose render pass or attachment view has since been destroyed or replaced (Anvil code -20004, stale framebuffer dependency); nothing was submitted.")
  EndIf
  image = avkIvImage[iv]
  img = avkImgSlot(image)
  If img = 0 Or img <> avkIvImgSlot[iv] Or avkImgBound[img] = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit was given a draw list whose colour attachment image is stale or unbound (Anvil code -20004, stale attachment); nothing was submitted.")
  EndIf
  mem = avkImgMemSlot[img]
  If mem < 1
    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found no live memory behind the draw-list attachment (Anvil code -20004, attachment memory missing); nothing was submitted.")
  EndIf

  slot = avkCbDrawHead[c]
  draw = 0
  While draw < count
    If slot < 1 Or slot > #ANVIL_VK_MAX_RECORDED_DRAWS
      ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found a recorded-draw link outside the bounded pool (Anvil code -20004, corrupt draw list); nothing was submitted.")
    EndIf
    nextSlot = avkRecordedDraw[slot]\next
    If draw = count - 1
      If slot <> avkCbDrawTail[c] Or nextSlot <> 0
        ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found a recorded-draw tail or terminal link inconsistent with its count (Anvil code -20004, corrupt draw list); nothing was submitted.")
      EndIf
    ElseIf nextSlot < 1 Or nextSlot > #ANVIL_VK_MAX_RECORDED_DRAWS
      ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found a truncated recorded-draw chain (Anvil code -20004, corrupt draw list); nothing was submitted.")
    EndIf

    p = avkPipeSlot(avkRecordedDraw[slot]\pipeline)
    If p = 0 Or avkPipeDev[p] <> avkFbDev[fb]
      ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found a recorded draw whose pipeline is stale or belongs to another device (Anvil code -20004, stale pipeline); nothing was submitted.")
    EndIf
    If avkPipeRp[p] <> avkFbRp[fb]
      ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found a recorded draw whose pipeline is incompatible with the list's render pass (Anvil code -20004, incompatible render pass); nothing was submitted.")
    EndIf

    set = avkRecordedDraw[slot]\descriptorSet
    ds = 0
    If avkPipeUsesUniform[p] <> 0 Or avkPipeUsesSample[p] <> 0
      ds = avkDsSlot(set)
      If ds = 0 Or avkDrawSetMatchesPipe(set, p) = 0
        ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found a recorded draw whose descriptor set is stale or incompatible with its pipeline (Anvil code -20004, stale descriptor state); nothing was submitted.")
      EndIf
    EndIf

    avkFlightPipe[draw] = p
    avkFlightSet[draw] = ds
    avkFlightFb[draw] = fb
    avkFlightRp[draw] = rp
    avkFlightTargetView[draw] = iv
    avkFlightTargetImage[draw] = img
    avkFlightTargetMem[draw] = mem
    avkFlightUniformBuf[draw] = 0
    avkFlightUniformMem[draw] = 0
    avkFlightIndexBuf[draw] = 0
    avkFlightIndexMem[draw] = 0
    avkFlightSampleImage[draw] = 0
    avkFlightSampleMem[draw] = 0
    avkFlightSampler[draw] = 0
    avkFlightSampleView[draw] = 0

    avkFlightDraw[draw]\pipeline = p
    avkFlightDraw[draw]\targetBase = avkHeapBase + avkMemOffset[mem] + avkImgMemOffset[img]
    avkFlightDraw[draw]\targetBytes = avkImgSize[img]
    avkFlightDraw[draw]\width = avkImgW[img]
    avkFlightDraw[draw]\height = avkImgH[img]
    avkFlightDraw[draw]\pitch = avkImgPitch[img]
    avkFlightDraw[draw]\clearBgra = avkCbClearWord[c]
    avkFlightDraw[draw]\bindingCount = avkPipeBindCount[p]
    baseIdx = draw * #ANVIL_VK_MAX_BINDINGS
    avkFlightDraw[draw]\bindings = @avkFlightBinding[baseIdx]
    avkFlightDraw[draw]\vertexCount = avkRecordedDraw[slot]\vertexCount
    avkFlightDraw[draw]\firstVertex = avkRecordedDraw[slot]\firstVertex
    avkFlightDraw[draw]\indexBase = 0
    avkFlightDraw[draw]\indexBytes = 0
    avkFlightDraw[draw]\indexType = 0
    avkFlightDraw[draw]\maxVertex = 0
    avkFlightDraw[draw]\sampleMask = avkPipeSampleMask[p]
    avkFlightDraw[draw]\blendMode = avkPipeBlendMode[p]
    avkFlightDraw[draw]\viewportX = avkRecordedDraw[slot]\viewportX
    avkFlightDraw[draw]\viewportY = avkRecordedDraw[slot]\viewportY
    avkFlightDraw[draw]\viewportW = avkRecordedDraw[slot]\viewportW
    avkFlightDraw[draw]\viewportH = avkRecordedDraw[slot]\viewportH
    avkFlightDraw[draw]\scissorX = avkRecordedDraw[slot]\scissorX
    avkFlightDraw[draw]\scissorY = avkRecordedDraw[slot]\scissorY
    avkFlightDraw[draw]\scissorW = avkRecordedDraw[slot]\scissorW
    avkFlightDraw[draw]\scissorH = avkRecordedDraw[slot]\scissorH
    avkFlightDraw[draw]\uniformBase = 0
    avkFlightDraw[draw]\uniformBytes = 0
    avkFlightDraw[draw]\sampledImage = 0

    ; Close indexed input from the live buffer generation. This CPU read is
    ; validation only: pixels and primitives remain exclusively GPU work. It
    ; is repeated for every submission because mapped coherent index bytes may
    ; legally change after command recording.
    If avkRecordedDraw[slot]\indexBuffer <> 0
      b = avkBufSlot(avkRecordedDraw[slot]\indexBuffer)
      If b = 0 Or avkBufDev[b] <> avkPipeDev[p] Or avkBufBound[b] = 0 Or (avkBufUsage[b] & #VK_BUFFER_USAGE_INDEX_BUFFER_BIT) = 0
        ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found a recorded indexed draw whose index buffer is stale, unbound, wrong-device or lacks INDEX_BUFFER usage (Anvil code -20004, stale index binding); nothing was submitted.")
      EndIf
      If avkRecordedDraw[slot]\indexType = #VK_INDEX_TYPE_UINT16
        indexBytes = 2
      ElseIf avkRecordedDraw[slot]\indexType = #VK_INDEX_TYPE_UINT32
        indexBytes = 4
      Else
        ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found unsupported recorded index type state (Anvil code -20004, corrupt index binding); nothing was submitted.")
      EndIf
      If avkRecordedDraw[slot]\indexOffset < 0 Or avkRecordedDraw[slot]\indexOffset >= avkBufSize[b] Or (avkRecordedDraw[slot]\indexOffset % indexBytes) <> 0
        ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found a recorded index bind offset misaligned or outside its live buffer (Anvil code -20004, stale index range); nothing was submitted.")
      EndIf
      available = avkBufSize[b] - avkRecordedDraw[slot]\indexOffset
      If avkRecordedDraw[slot]\firstVertex > (available / indexBytes) Or avkRecordedDraw[slot]\vertexCount > ((available / indexBytes) - avkRecordedDraw[slot]\firstVertex)
        ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found a recorded index range outside its live buffer (Anvil code -20004, stale index range); nothing was submitted.")
      EndIf
      indexMem = avkBufMemSlot[b]
      indexAddress = avkHeapBase + avkMemOffset[indexMem] + avkBufMemOffset[b] + avkRecordedDraw[slot]\indexOffset
      maxVertex = 0
      k = 0
      While k < avkRecordedDraw[slot]\vertexCount
        If indexBytes = 2
          indexValue = PeekU(indexAddress + ((avkRecordedDraw[slot]\firstVertex + k) * 2)) & $FFFF
        Else
          indexValue = PeekL(indexAddress + ((avkRecordedDraw[slot]\firstVertex + k) * 4)) & $FFFFFFFF
        EndIf
        If indexValue > maxVertex : maxVertex = indexValue : EndIf
        k = k + 1
      Wend
      avkFlightIndexBuf[draw] = b
      avkFlightIndexMem[draw] = indexMem
      avkFlightDraw[draw]\indexBase = indexAddress
      avkFlightDraw[draw]\indexBytes = available
      avkFlightDraw[draw]\indexType = avkRecordedDraw[slot]\indexType
      avkFlightDraw[draw]\maxVertex = maxVertex
    Else
      If (avkRecordedDraw[slot]\vertexCount - 1) > ($FFFFFFFF - avkRecordedDraw[slot]\firstVertex)
        ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found a recorded non-indexed vertex range that overflows uint32 (Anvil code -20004, corrupt vertex range); nothing was submitted.")
      EndIf
      maxVertex = avkRecordedDraw[slot]\firstVertex + avkRecordedDraw[slot]\vertexCount - 1
      avkFlightDraw[draw]\maxVertex = maxVertex
    EndIf

    k = 0
    While k < avkPipeBindCount[p]
      idx = baseIdx + k
      b = avkBufSlot(avkRecordedDraw[slot]\vertexBuffer[k])
      stride = avkPipeBindStride[(p * #ANVIL_VK_MAX_BINDINGS) + k]
      If b = 0 Or avkBufDev[b] <> avkPipeDev[p] Or avkBufBound[b] = 0 Or stride < 1
        ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found a recorded draw whose vertex buffer is stale, unbound or incompatible (Anvil code -20004, stale vertex binding); nothing was submitted.")
      EndIf
      If avkRecordedDraw[slot]\vertexOffset[k] < 0 Or avkRecordedDraw[slot]\vertexOffset[k] > avkBufSize[b]
        ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found a recorded vertex offset outside its live buffer (Anvil code -20004, stale vertex range); nothing was submitted.")
      EndIf
      available = avkBufSize[b] - avkRecordedDraw[slot]\vertexOffset[k]
      If available < stride Or maxVertex > ((available / stride) - 1)
        ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found a recorded vertex range outside its live buffer (Anvil code -20004, stale vertex range); nothing was submitted.")
      EndIf
      bindingMem = avkBufMemSlot[b]
      avkFlightVertexBuf[idx] = b
      avkFlightVertexMem[idx] = bindingMem
      avkFlightBinding[idx]\base = avkHeapBase + avkMemOffset[bindingMem] + avkBufMemOffset[b] + avkRecordedDraw[slot]\vertexOffset[k]
      avkFlightBinding[idx]\stride = stride
      k = k + 1
    Wend

    If avkPipeUsesPush[p] <> 0
      If avkRecordedDraw[slot]\pushBytes <> #ANVIL_VK_PUSH_BYTES
        ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found a recorded draw missing the push block its pipeline reads (Anvil code -20004, push state missing); nothing was submitted.")
      EndIf
      k = 0
      While k < 4
        avkFlightPush[(draw * 4) + k] = avkRecordedDraw[slot]\pushWord[k]
        k = k + 1
      Wend
      avkFlightDraw[draw]\pushBase = @avkFlightPush[draw * 4]
      avkFlightDraw[draw]\pushBytes = #ANVIL_VK_PUSH_BYTES
    Else
      avkFlightDraw[draw]\pushBase = 0
      avkFlightDraw[draw]\pushBytes = 0
    EndIf

    If avkPipeUsesUniform[p] <> 0
      address = AnvilVkDescriptorSetAddress(set, avkPipeUniformBinding[p])
      range = AnvilVkDescriptorSetRange(set, avkPipeUniformBinding[p])
      ub = avkBufSlot(AnvilVkDescriptorSetBuffer(set, avkPipeUniformBinding[p]))
      If address = 0 Or range < #ANVIL_VK_UNIFORM_BYTES Or ub = 0 Or avkBufBound[ub] = 0
        ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found a recorded uniform descriptor unwritten or stale (Anvil code -20004, descriptor not ready); nothing was submitted.")
      EndIf
      avkFlightDraw[draw]\uniformBase = address
      avkFlightDraw[draw]\uniformBytes = range
      avkFlightUniformBuf[draw] = ub
      avkFlightUniformMem[draw] = avkBufMemSlot[ub]
    EndIf

    If avkPipeUsesSample[p] <> 0
      If AnvilVkDescriptorSetSampledImage(set, avkPipeSampleBinding[p], @avkFlightSample[draw]) = 0
        ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit found a recorded sampled descriptor unwritten, stale or in the wrong layout (Anvil code -20004, sampled descriptor not ready); nothing was submitted.")
      EndIf
      image = AnvilVkDescriptorSetSampledImageHandle(set, avkPipeSampleBinding[p])
      sampler = AnvilVkDescriptorSetSamplerHandle(set, avkPipeSampleBinding[p])
      view = AnvilVkDescriptorSetImageViewHandle(set, avkPipeSampleBinding[p])
      simg = avkImgSlot(image)
      samp = avkSamplerSlot(sampler)
      siv = avkIvSlot(view)
      If simg = 0 Or samp = 0 Or siv = 0
        ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit could not capture every generation behind a sampled descriptor (Anvil code -20004, stale sampled dependency); nothing was submitted.")
      EndIf
      avkFlightDraw[draw]\sampledImage = @avkFlightSample[draw]
      avkFlightSampleImage[draw] = simg
      avkFlightSampleMem[draw] = avkImgMemSlot[simg]
      avkFlightSampler[draw] = samp
      avkFlightSampleView[draw] = siv
    EndIf

    slot = nextSlot
    draw = draw + 1
  Wend

  rc = avkBackendDrawSupported(avkFlightDraw[0]\targetBase, avkFlightDraw[0]\targetBytes, avkFlightDraw[0]\width, avkFlightDraw[0]\height, avkFlightDraw[0]\pitch)
  If rc <> #VK_SUCCESS
    ProcedureReturn avkFault(rc, "the graphics backend cannot render the closed draw list into this attachment (VkResult or Anvil code in AnvilVkFaultCode(); nothing was submitted).")
  EndIf
  avkFlightDrawCount = count
  avkFlightDrawList\drawCount = count
  avkFlightDrawList\draws = @avkFlightDraw[0]
  avkFlightDrawPreparedCb = c
  ProcedureReturn #ANVIL_VK_OK
EndProcedure

Procedure avkDrawListRetain(c.i)
  Define draw.i
  Define k.i
  Define idx.i
  Define baseIdx.i
  Define s.i
  If avkFlightDrawCount < 1 Or avkFlightLedgerCommitted <> 0 Or avkFlightDrawPreparedCb <> c Or avkFlightActive = 0 Or avkFlightCb <> c
    ProcedureReturn
  EndIf
  draw = 0
  While draw < avkFlightDrawCount
    s = avkFlightPipe[draw] : avkPipeInFlight[s] = avkPipeInFlight[s] + 1
    s = avkFlightSet[draw] : If s > 0 : avkDsInFlight[s] = avkDsInFlight[s] + 1 : EndIf
    s = avkFlightFb[draw] : avkFbInFlight[s] = avkFbInFlight[s] + 1
    s = avkFlightRp[draw] : avkRpInFlight[s] = avkRpInFlight[s] + 1
    s = avkFlightTargetView[draw] : avkIvInFlight[s] = avkIvInFlight[s] + 1
    ; The attachment image and memory are already retained once by the command
    ; layer's captured image-reference ledger. Do not double-charge that same
    ; ownership path here; sampled aliases below remain additive per draw.
    baseIdx = draw * #ANVIL_VK_MAX_BINDINGS
    k = 0
    While k < avkFlightDraw[draw]\bindingCount
      idx = baseIdx + k
      s = avkFlightVertexBuf[idx]
      If s > 0
        avkBufInFlight[s] = avkBufInFlight[s] + 1
        avkMemInFlight[avkFlightVertexMem[idx]] = avkMemInFlight[avkFlightVertexMem[idx]] + 1
      EndIf
      k = k + 1
    Wend
    s = avkFlightIndexBuf[draw]
    If s > 0
      avkBufInFlight[s] = avkBufInFlight[s] + 1
      avkMemInFlight[avkFlightIndexMem[draw]] = avkMemInFlight[avkFlightIndexMem[draw]] + 1
    EndIf
    s = avkFlightUniformBuf[draw]
    If s > 0
      avkBufInFlight[s] = avkBufInFlight[s] + 1
      avkMemInFlight[avkFlightUniformMem[draw]] = avkMemInFlight[avkFlightUniformMem[draw]] + 1
    EndIf
    s = avkFlightSampleImage[draw]
    If s > 0
      avkImgInFlight[s] = avkImgInFlight[s] + 1
      avkMemInFlight[avkFlightSampleMem[draw]] = avkMemInFlight[avkFlightSampleMem[draw]] + 1
    EndIf
    s = avkFlightSampler[draw] : If s > 0 : avkSampInFlight[s] = avkSampInFlight[s] + 1 : EndIf
    s = avkFlightSampleView[draw] : If s > 0 : avkIvInFlight[s] = avkIvInFlight[s] + 1 : EndIf
    draw = draw + 1
  Wend
  avkFlightDrawOwnerCb = c
  avkFlightDrawPreparedCb = 0
  avkFlightLedgerCommitted = 1
EndProcedure

; Release only captured slots. There is deliberately no descriptor lookup in
; this procedure: completion cannot follow a rewritten set to a replacement
; buffer, image, view or sampler generation.
Procedure avkDrawListRelease(c.i)
  Define draw.i
  Define k.i
  Define idx.i
  Define baseIdx.i
  Define s.i
  If avkFlightLedgerCommitted = 0 Or avkFlightDrawOwnerCb <> c Or avkFlightActive = 0 Or avkFlightCb <> c
    ProcedureReturn
  EndIf
  draw = 0
  While draw < avkFlightDrawCount
    s = avkFlightPipe[draw] : If avkPipeInFlight[s] > 0 : avkPipeInFlight[s] = avkPipeInFlight[s] - 1 : EndIf
    s = avkFlightSet[draw] : If s > 0 And avkDsInFlight[s] > 0 : avkDsInFlight[s] = avkDsInFlight[s] - 1 : EndIf
    s = avkFlightFb[draw] : If avkFbInFlight[s] > 0 : avkFbInFlight[s] = avkFbInFlight[s] - 1 : EndIf
    s = avkFlightRp[draw] : If avkRpInFlight[s] > 0 : avkRpInFlight[s] = avkRpInFlight[s] - 1 : EndIf
    s = avkFlightTargetView[draw] : If avkIvInFlight[s] > 0 : avkIvInFlight[s] = avkIvInFlight[s] - 1 : EndIf
    baseIdx = draw * #ANVIL_VK_MAX_BINDINGS
    k = 0
    While k < avkFlightDraw[draw]\bindingCount
      idx = baseIdx + k
      s = avkFlightVertexBuf[idx]
      If s > 0
        If avkBufInFlight[s] > 0 : avkBufInFlight[s] = avkBufInFlight[s] - 1 : EndIf
        If avkMemInFlight[avkFlightVertexMem[idx]] > 0 : avkMemInFlight[avkFlightVertexMem[idx]] = avkMemInFlight[avkFlightVertexMem[idx]] - 1 : EndIf
      EndIf
      k = k + 1
    Wend
    s = avkFlightIndexBuf[draw]
    If s > 0
      If avkBufInFlight[s] > 0 : avkBufInFlight[s] = avkBufInFlight[s] - 1 : EndIf
      If avkMemInFlight[avkFlightIndexMem[draw]] > 0 : avkMemInFlight[avkFlightIndexMem[draw]] = avkMemInFlight[avkFlightIndexMem[draw]] - 1 : EndIf
    EndIf
    s = avkFlightUniformBuf[draw]
    If s > 0
      If avkBufInFlight[s] > 0 : avkBufInFlight[s] = avkBufInFlight[s] - 1 : EndIf
      If avkMemInFlight[avkFlightUniformMem[draw]] > 0 : avkMemInFlight[avkFlightUniformMem[draw]] = avkMemInFlight[avkFlightUniformMem[draw]] - 1 : EndIf
    EndIf
    s = avkFlightSampleImage[draw]
    If s > 0
      If avkImgInFlight[s] > 0 : avkImgInFlight[s] = avkImgInFlight[s] - 1 : EndIf
      If avkMemInFlight[avkFlightSampleMem[draw]] > 0 : avkMemInFlight[avkFlightSampleMem[draw]] = avkMemInFlight[avkFlightSampleMem[draw]] - 1 : EndIf
    EndIf
    s = avkFlightSampler[draw] : If s > 0 And avkSampInFlight[s] > 0 : avkSampInFlight[s] = avkSampInFlight[s] - 1 : EndIf
    s = avkFlightSampleView[draw] : If s > 0 And avkIvInFlight[s] > 0 : avkIvInFlight[s] = avkIvInFlight[s] - 1 : EndIf
    draw = draw + 1
  Wend
  avkFlightLedgerCommitted = 0
  avkFlightDrawOwnerCb = 0
  avkFlightDrawPreparedCb = 0
  avkFlightDrawCount = 0
  avkFlightDrawList\drawCount = 0
  avkFlightDrawList\draws = 0
EndProcedure

; Drop only an uncommitted closure. Once retain has committed the ledger, the
; owning flight must release it through avkDrawListRelease with the same CB.
Procedure avkDrawListDiscard()
  If avkFlightLedgerCommitted <> 0
    ProcedureReturn
  EndIf
  avkFlightDrawPreparedCb = 0
  avkFlightDrawOwnerCb = 0
  avkFlightDrawCount = 0
  avkFlightDrawList\drawCount = 0
  avkFlightDrawList\draws = 0
EndProcedure

Procedure.i avkDrawListSubmit()
  If avkFlightDrawCount < 1 : ProcedureReturn -1 : EndIf
  If (avkBackendCaps() & #ANVIL_VK_CAP_DRAW_LIST) <> 0
    ProcedureReturn avkBackendSubmitDraw(@avkFlightDrawList)
  EndIf
  If avkFlightDrawCount <> 1 : ProcedureReturn -1 : EndIf
  ProcedureReturn avkBackendSubmitDraw(@avkFlightDraw[0])
EndProcedure

; The address of the record the last draw was submitted with. A gate
; compares its bytes against an expectation it builds independently, so
; it is readable and it is never written from outside this file.
Procedure.i AnvilVkLastDrawRecord()
  ProcedureReturn @avkFlightDraw[0]
EndProcedure

Procedure.i AnvilVkLastDrawList()
  ProcedureReturn @avkFlightDrawList
EndProcedure

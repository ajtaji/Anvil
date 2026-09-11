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
;   * one viewport and one scissor, neither dynamic
;   * VK_POLYGON_MODE_FILL, VK_CULL_MODE_NONE, no depth bias, line width
;     1.0, no depth clamp, no rasteriser discard
;   * one sample, no sample shading, no alpha to coverage
;   * one colour attachment, blending disabled, every channel written
;   * no depth-stencil state, no dynamic state, no pipeline cache, no
;     derivative pipelines
;   * a render pass of exactly one colour attachment, one subpass, no
;     subpass dependencies, loadOp CLEAR and storeOp STORE
;   * a pipeline layout of no descriptor sets and at most one push
;     constant range, in the fragment stage, at offset 0, of 16 bytes
;
; Everything else is refused with a real code and a whole sentence.

XIncludeFile "Anvil/Graphics/Vulkan/vk_command.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_spirv.pbi"

#ANVIL_VK_MAX_BUFFERS = 4
#ANVIL_VK_MAX_SHADER_MODULES = 4
#ANVIL_VK_MAX_LAYOUTS = 4
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
;  SHADER MODULES. One module holds one walked plan.
; ----------------------------------------------------------------------
Global Dim avkShLive.a[#ANVIL_VK_MAX_SHADER_MODULES + 1]
Global Dim avkShGen.i[#ANVIL_VK_MAX_SHADER_MODULES + 1]
Global Dim avkShDev.i[#ANVIL_VK_MAX_SHADER_MODULES + 1]
Global Dim avkShStage.i[#ANVIL_VK_MAX_SHADER_MODULES + 1]
Global Dim avkShWords.i[#ANVIL_VK_MAX_SHADER_MODULES + 1]
Global Dim avkShInstr.i[#ANVIL_VK_MAX_SHADER_MODULES + 1]
Global Dim avkShInCount.i[#ANVIL_VK_MAX_SHADER_MODULES + 1]
Global Dim avkShOutCount.i[#ANVIL_VK_MAX_SHADER_MODULES + 1]
Global Dim avkShPosAttr.i[#ANVIL_VK_MAX_SHADER_MODULES + 1]
Global Dim avkShColourSrc.i[#ANVIL_VK_MAX_SHADER_MODULES + 1]
Global Dim avkShColourIdx.i[#ANVIL_VK_MAX_SHADER_MODULES + 1]
Global Dim avkShPush.i[#ANVIL_VK_MAX_SHADER_MODULES + 1]
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

Global Dim avkRpLive.a[#ANVIL_VK_MAX_RENDER_PASSES + 1]
Global Dim avkRpGen.i[#ANVIL_VK_MAX_RENDER_PASSES + 1]
Global Dim avkRpDev.i[#ANVIL_VK_MAX_RENDER_PASSES + 1]
Global Dim avkRpFormat.i[#ANVIL_VK_MAX_RENDER_PASSES + 1]
Global Dim avkRpFinalLayout.i[#ANVIL_VK_MAX_RENDER_PASSES + 1]

Global Dim avkIvLive.a[#ANVIL_VK_MAX_IMAGE_VIEWS + 1]
Global Dim avkIvGen.i[#ANVIL_VK_MAX_IMAGE_VIEWS + 1]
Global Dim avkIvDev.i[#ANVIL_VK_MAX_IMAGE_VIEWS + 1]
Global Dim avkIvImage.i[#ANVIL_VK_MAX_IMAGE_VIEWS + 1]
Global Dim avkIvImgSlot.i[#ANVIL_VK_MAX_IMAGE_VIEWS + 1]

Global Dim avkFbLive.a[#ANVIL_VK_MAX_FRAMEBUFFERS + 1]
Global Dim avkFbGen.i[#ANVIL_VK_MAX_FRAMEBUFFERS + 1]
Global Dim avkFbDev.i[#ANVIL_VK_MAX_FRAMEBUFFERS + 1]
Global Dim avkFbRp.i[#ANVIL_VK_MAX_FRAMEBUFFERS + 1]
Global Dim avkFbView.i[#ANVIL_VK_MAX_FRAMEBUFFERS + 1]
Global Dim avkFbW.i[#ANVIL_VK_MAX_FRAMEBUFFERS + 1]
Global Dim avkFbH.i[#ANVIL_VK_MAX_FRAMEBUFFERS + 1]

; ----------------------------------------------------------------------
;  PIPELINES. The plan the backend compiles from.
; ----------------------------------------------------------------------
Global Dim avkPipeLive.a[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeGen.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeDev.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeLayout.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeRp.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeStride.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeAttrCount.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipePosAttr.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeVaryCount.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeColourSrc.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeColourIdx.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeViewX.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeViewY.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeViewW.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeViewH.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeCodeBase.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeCodeBytes.i[#ANVIL_VK_MAX_PIPELINES + 1]
Global Dim avkPipeCodeMem.i[#ANVIL_VK_MAX_PIPELINES + 1]
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
Global Dim avkPushStage.l[4]

Global avkDrawRecord.AnvilVkBackendDraw

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
  If usage = 0 Or (usage & (~(#VK_BUFFER_USAGE_TRANSFER_SRC_BIT | #VK_BUFFER_USAGE_TRANSFER_DST_BIT | #VK_BUFFER_USAGE_VERTEX_BUFFER_BIT))) <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateBuffer was asked for a buffer usage Anvil does not implement (Anvil code -20005, unsupported usage); only VK_BUFFER_USAGE_VERTEX_BUFFER_BIT, VK_BUFFER_USAGE_TRANSFER_SRC_BIT and VK_BUFFER_USAGE_TRANSFER_DST_BIT exist here, because there is no index buffer, no uniform buffer and no descriptor to reach one through.")
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

; ======================================================================
;  SHADER MODULES
; ======================================================================
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
  rc = AnvilVkSpirvWalk(*code, bytes)
  If rc <> #ANVIL_VK_OK : ProcedureReturn rc : EndIf
  s = 1
  While s <= #ANVIL_VK_MAX_SHADER_MODULES And avkShLive[s] <> 0 : s = s + 1 : Wend
  If s > #ANVIL_VK_MAX_SHADER_MODULES : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf
  avkShGen[s] = avkNextGen(avkShGen[s])
  avkShLive[s] = 1
  avkShDev[s] = d
  avkShStage[s] = AnvilVkSpirvStage()
  avkShWords[s] = bytes / 4
  avkShInstr[s] = AnvilVkSpirvInstructions()
  avkShInCount[s] = AnvilVkSpirvInputCount()
  avkShOutCount[s] = AnvilVkSpirvOutputCount()
  avkShPosAttr[s] = AnvilVkSpirvPositionAttr()
  avkShColourSrc[s] = AnvilVkSpirvColourSource()
  avkShColourIdx[s] = AnvilVkSpirvColourIndex()
  avkShPush[s] = AnvilVkSpirvUsesPushConstants()
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
  avkShLive[s] = 0
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
Procedure.i AnvilVkPipelineLayoutCreate(device.i, setCount.i, pushCount.i, *ranges.VkPushConstantRange, *out)
  Define d.i
  Define s.i
  Define bytes.i
  If *out = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, #VK_NULL_HANDLE)
  d = avkDevSlot(device)
  If d = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If setCount <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreatePipelineLayout was given descriptor set layouts (Anvil code -20005, descriptor sets not implemented); there is no VkDescriptorSetLayout, no VkDescriptorPool and no vkCmdBindDescriptorSets in this implementation, so a bound set could never be supplied to a shader. Use the push-constant range instead.")
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
  avkLayLive[s] = 1
  avkLayDev[s] = d
  avkLayPushBytes[s] = bytes
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
  img = avkIvImgSlot[iv]
  If width <> avkImgW[img] Or height <> avkImgH[img]
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateFramebuffer was given a width or height that is not the attachment image's own extent (Anvil code -20001, framebuffer does not match its attachment); a smaller framebuffer over a larger image would render into part of it, and this backend renders the whole render target at one geometry.")
  EndIf
  s = 1
  While s <= #ANVIL_VK_MAX_FRAMEBUFFERS And avkFbLive[s] <> 0 : s = s + 1 : Wend
  If s > #ANVIL_VK_MAX_FRAMEBUFFERS : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf
  avkFbGen[s] = avkNextGen(avkFbGen[s])
  avkFbLive[s] = 1
  avkFbDev[s] = d
  avkFbRp[s] = rp
  avkFbView[s] = iv
  avkFbW[s] = width
  avkFbH[s] = height
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

Procedure.i avkPipeCheckMultisample(*ms.VkPipelineMultisampleStateCreateInfo)
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
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkPipeCheckColorBlend(*cb.VkPipelineColorBlendStateCreateInfo)
  Define *a.VkPipelineColorBlendAttachmentState
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
  If (*a\blendEnable & $FFFFFFFF) <> #VK_FALSE
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was asked to enable blending (Anvil code -20005, blending not implemented); this pipeline writes the shader's colour straight into the tile buffer, so a blend equation would be declared and not carried out.")
  EndIf
  If (*a\colorWriteMask & $FFFFFFFF) <> (#VK_COLOR_COMPONENT_R_BIT | #VK_COLOR_COMPONENT_G_BIT | #VK_COLOR_COMPONENT_B_BIT | #VK_COLOR_COMPONENT_A_BIT)
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was asked to mask out a colour channel (Anvil code -20005, unsupported write mask); every channel is written here, and a partial mask would leave the untouched channels holding the clear value rather than the caller's.")
  EndIf
  ProcedureReturn #VK_SUCCESS
EndProcedure

; The vertex input state, joined against the vertex shader's own inputs.
; A pipeline whose attributes do not match its shader is refused here,
; which is the one place where both are in view at the same time.
Procedure.i avkPipeVertexInput(pipe.i, vs.i, *vi.VkPipelineVertexInputStateCreateInfo)
  Define n.i
  Define k.i
  Define j.i
  Define loc.i
  Define fmt.i
  Define comps.i
  Define stride.i
  Define *bind.VkVertexInputBindingDescription
  Define *attr.VkVertexInputAttributeDescription
  Define base.i
  Define seen.i

  If *vi = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given no pVertexInputState (Anvil code -20001, missing state); a pipeline whose vertex shader reads attributes must declare where they come from.")
  EndIf
  If (*vi\sType & $FFFFFFFF) <> #VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a VkPipelineVertexInputStateCreateInfo whose sType is wrong (Anvil code -20001, wrong sType).")
  EndIf
  If (*vi\vertexBindingDescriptionCount & $FFFFFFFF) <> 1 Or *vi\pVertexBindingDescriptions = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was given other than exactly one vertex input binding (Anvil code -20005, unsupported vertex input); this slice binds one vertex buffer, so every attribute must come out of binding zero.")
  EndIf
  *bind = *vi\pVertexBindingDescriptions
  If (*bind\binding & $FFFFFFFF) <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was given a vertex input binding whose number is not zero (Anvil code -20005, unsupported vertex input); the one binding this slice implements is binding zero.")
  EndIf
  If (*bind\inputRate & $FFFFFFFF) <> #VK_VERTEX_INPUT_RATE_VERTEX
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was given a vertex input binding at VK_VERTEX_INPUT_RATE_INSTANCE (Anvil code -20005, instancing not implemented); vkCmdDraw here takes one instance, so a per-instance attribute would be fetched once and would look like a per-vertex one.")
  EndIf
  stride = *bind\stride & $FFFFFFFF
  n = *vi\vertexAttributeDescriptionCount & $FFFFFFFF
  If n < 1 Or n > #ANVIL_SPV_MAX_ATTRS Or *vi\pVertexAttributeDescriptions = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was given no vertex attributes or more than four (Anvil code -20005, unsupported vertex input); this slice fetches between one and four attributes.")
  EndIf
  If n <> avkShInCount[vs]
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a different number of vertex attributes from the number of Location inputs its vertex shader declares (Anvil code -20001, interface mismatch); every attribute the shader reads must be supplied, and an attribute nothing reads would be fetched and thrown away.")
  EndIf
  base = pipe * #ANVIL_SPV_MAX_ATTRS
  seen = 0
  k = 0
  While k < n
    *attr = *vi\pVertexAttributeDescriptions + (k * SizeOf(VkVertexInputAttributeDescription))
    If (*attr\binding & $FFFFFFFF) <> 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was given a vertex attribute that reads a binding other than zero (Anvil code -20005, unsupported vertex input); there is one binding here and every attribute comes out of it.")
    EndIf
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
    If (j + (comps * 4)) > stride
      ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a vertex attribute that runs past the end of one vertex (Anvil code -20001, attribute outside the stride); the binding's stride must cover every attribute's offset plus its size.")
    EndIf
    avkPipeAttrComp[base + loc] = comps
    avkPipeAttrOffset[base + loc] = j
    k = k + 1
  Wend
  avkPipeStride[pipe] = stride
  avkPipeAttrCount[pipe] = n
  ProcedureReturn #VK_SUCCESS
EndProcedure

; The viewport, which is what the emitted coordinate shader scales clip
; space by. One viewport, one scissor, and the scissor must be the whole
; viewport: a smaller scissor would need a clip window this slice does
; not emit per pipeline.
Procedure.i avkPipeViewport(pipe.i, *vp.VkPipelineViewportStateCreateInfo)
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
  If *vp\pViewports = 0 Or *vp\pScissors = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was given a null pViewports or pScissors (Anvil code -20005, dynamic viewport not implemented); there is no dynamic state here, so the viewport and the scissor must be supplied at creation.")
  EndIf
  *v = *vp\pViewports
  *sc = *vp\pScissors
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
  If (*sc\offset\x & $FFFFFFFF) <> 0 Or (*sc\offset\y & $FFFFFFFF) <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was given a scissor that does not start at the origin (Anvil code -20005, unsupported scissor); the clip window this backend emits covers the whole render target.")
  EndIf
  If (*sc\extent\width & $FFFFFFFF) <> avkPipeViewW[pipe] Or (*sc\extent\height & $FFFFFFFF) <> avkPipeViewH[pipe]
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was given a scissor that is not the whole viewport (Anvil code -20005, unsupported scissor); a partial scissor needs a clip window emitted per pipeline, and this slice emits one for the whole target.")
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
  Define *st.VkPipelineShaderStageCreateInfo

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
  If *ci\pDynamicState <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was given a dynamic state (Anvil code -20005, dynamic state not implemented); every piece of state this pipeline uses is baked at creation, and there is no vkCmdSetViewport or vkCmdSetScissor to supply one later.")
  EndIf
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
  If lay = 0 Or rp = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
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
    If s = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
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
  rc = avkPipeCheckMultisample(*ci\pMultisampleState)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  rc = avkPipeCheckColorBlend(*ci\pColorBlendState)
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
  If avkShColourSrc[fs] = #ANVIL_SPV_COLOUR_PUSH And avkLayPushBytes[lay] <> #ANVIL_VK_PUSH_BYTES
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a fragment shader that reads the push-constant block through a pipeline layout that declares no push constant range (Anvil code -20001, layout mismatch); declare a sixteen-byte fragment-stage range at offset zero.")
  EndIf
  If avkShColourSrc[fs] = #ANVIL_SPV_COLOUR_VARYING And avkShOutCount[vs] < 1
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateGraphicsPipelines was given a fragment shader that interpolates a varying its vertex shader never writes (Anvil code -20001, interface mismatch); the vertex stage must write the Location the fragment stage reads.")
  EndIf

  s = 1
  While s <= #ANVIL_VK_MAX_PIPELINES And avkPipeLive[s] <> 0 : s = s + 1 : Wend
  If s > #ANVIL_VK_MAX_PIPELINES : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf

  ; Fill the plan BEFORE the backend is asked to compile it, and mark the
  ; slot live only once the backend has said yes. A half-built pipeline
  ; that a later call could find is worse than no pipeline at all.
  avkPipeDev[s] = d
  avkPipeLayout[s] = lay
  avkPipeRp[s] = rp
  avkPipePosAttr[s] = avkShPosAttr[vs]
  avkPipeVaryCount[s] = avkShOutCount[vs]
  avkPipeColourSrc[s] = avkShColourSrc[fs]
  avkPipeColourIdx[s] = avkShColourIdx[fs]
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
    k = k + 1
  Wend
  rc = avkPipeVertexInput(s, vs, *ci\pVertexInputState)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  rc = avkPipeViewport(s, *ci\pViewportState)
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
  rc = avkBackendPipelineBuild(s, avkPipeCodeBase[s], need)
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
  If avkFlightActive <> 0 And avkCbPipe[avkFlightCb] = pipeline
    avkFault(#ANVIL_VK_ERR_STATE, "vkDestroyPipeline was called while a submitted command buffer still uses this pipeline (Anvil code -20004, resource in use); nothing was destroyed. Wait on the submission's fence, or call vkDeviceWaitIdle, first.")
    ProcedureReturn
  EndIf
  avkBackendPipelineRelease(s)
  If avkPipeCodeMem[s] <> 0
    avkInternalFree(avkPipeCodeMem[s])
    avkPipeCodeMem[s] = 0
  EndIf
  avkPipeLive[s] = 0
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

Procedure.i AnvilVkPipelineStride(pipe.i)
  If pipe < 1 Or pipe > #ANVIL_VK_MAX_PIPELINES : ProcedureReturn 0 : EndIf
  ProcedureReturn avkPipeStride[pipe]
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
  img = avkIvImgSlot[iv]
  If avkImgLive[img] = 0 Or avkImgBound[img] = 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdBeginRenderPass was given a framebuffer whose attachment image has no memory bound to it (Anvil code -20004, image not bound); call vkBindImageMemory before recording a render pass against it.")
    ProcedureReturn
  EndIf
  If (avkImgUsage[img] & #VK_IMAGE_USAGE_TRANSFER_DST_BIT) = 0
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdBeginRenderPass was given an attachment image that was not created with VK_IMAGE_USAGE_TRANSFER_DST_BIT (Anvil code -20001, missing usage); this slice has no separate colour-attachment usage bit path, so the render target must name the transfer destination usage the image engine implements.")
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
  If binding <> 0
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdBindVertexBuffers was asked to bind a binding other than zero (Anvil code -20005, unsupported binding); this slice has one vertex input binding and its number is zero.")
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
  avkCbVtxBuf[c] = buffer
  avkCbVtxOffset[c] = offset
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
  Define b.i
  Define need.i
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
  If avkCbDrawCount[c] > 0
    avkCbFail(c, #VK_ERROR_FEATURE_NOT_PRESENT, "vkCmdDraw was called a second time in one render pass (VkResult -8, VK_ERROR_FEATURE_NOT_PRESENT); the backend seam carries one draw per submission, so record the second draw in its own command buffer until the backend carries a command list.")
    ProcedureReturn
  EndIf
  p = avkPipeSlot(avkCbPipe[c])
  If p = 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdDraw was called with no graphics pipeline bound (Anvil code -20004, no pipeline bound); call vkCmdBindPipeline before drawing, because the pipeline is what says which shaders run.")
    ProcedureReturn
  EndIf
  b = avkBufSlot(avkCbVtxBuf[c])
  If b = 0
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdDraw was called with no vertex buffer bound (Anvil code -20004, no vertex buffer bound); call vkCmdBindVertexBuffers before drawing, because this pipeline's vertex shader reads attributes.")
    ProcedureReturn
  EndIf
  If avkPipeRp[p] <> avkFbRp[avkCbFb[c]]
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdDraw was called with a pipeline created for a different render pass from the one that is begun (Anvil code -20001, incompatible render pass); a pipeline may only be used inside a render pass compatible with the one it was created against.")
    ProcedureReturn
  EndIf
  If instanceCount <> 1 Or firstInstance <> 0
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdDraw was asked for other than exactly one instance starting at instance zero (Anvil code -20005, instancing not implemented); the control list this backend writes draws one instance, so a second one would be declared and never drawn.")
    ProcedureReturn
  EndIf
  If vertexCount < 3 Or (vertexCount % 3) <> 0
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdDraw was given a vertex count that is not a positive multiple of three (Anvil code -20001, incomplete triangle); the topology is VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST, so the leftover vertices would form no primitive and would be silently dropped.")
    ProcedureReturn
  EndIf
  If firstVertex < 0
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdDraw was given a negative firstVertex (Anvil code -20001, invalid argument); the index of the first vertex is an unsigned count from the start of the bound buffer.")
    ProcedureReturn
  EndIf
  ; Every vertex the draw names must be inside the bound buffer. Written
  ; as a difference so that an offset plus a length which wraps cannot
  ; pass, the same shape the image binder uses.
  need = (firstVertex + vertexCount) * avkPipeStride[p]
  If avkPipeStride[p] <= 0 Or need <= 0 Or (avkBufSize[b] - avkCbVtxOffset[c]) < need
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdDraw names vertices past the end of the bound vertex buffer (Anvil code -20001, vertex range outside the buffer); firstVertex plus vertexCount, multiplied by the binding's stride, must fit between the bind offset and the end of the VkBuffer. Reading past it would be a GPU fetch from memory this allocation does not own.")
    ProcedureReturn
  EndIf
  If avkPipeColourSrc[p] = #ANVIL_SPV_COLOUR_PUSH And avkCbPushBytes[c] <> #ANVIL_VK_PUSH_BYTES
    avkCbFail(c, #ANVIL_VK_ERR_STATE, "vkCmdDraw was called with a pipeline whose fragment shader reads the push-constant block, and no push constants were recorded (Anvil code -20004, push constants not set); call vkCmdPushConstants before the draw, because an unset block would be whatever the memory happened to hold.")
    ProcedureReturn
  EndIf
  avkCbDrawVerts[c] = vertexCount
  avkCbDrawFirst[c] = firstVertex
  avkCbDrawCount[c] = 1
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
;  These three are declared in vk_command.pbi and defined here, because
;  the submission engine must not know what a pipeline is and this file
;  must not own the flight.

Procedure avkDrawRetain(c.i)
  Define b.i
  If avkCbDrawCount[c] = 0
    ProcedureReturn
  EndIf
  b = avkBufSlot(avkCbVtxBuf[c])
  If b = 0
    ProcedureReturn
  EndIf
  avkBufInFlight[b] = avkBufInFlight[b] + 1
  avkMemInFlight[avkBufMemSlot[b]] = avkMemInFlight[avkBufMemSlot[b]] + 1
EndProcedure

Procedure avkDrawRelease(c.i)
  Define b.i
  If avkCbDrawCount[c] = 0
    ProcedureReturn
  EndIf
  b = avkBufSlot(avkCbVtxBuf[c])
  If b = 0
    ProcedureReturn
  EndIf
  If avkBufInFlight[b] > 0 : avkBufInFlight[b] = avkBufInFlight[b] - 1 : EndIf
  If avkMemInFlight[avkBufMemSlot[b]] > 0
    avkMemInFlight[avkBufMemSlot[b]] = avkMemInFlight[avkBufMemSlot[b]] - 1
  EndIf
EndProcedure

; Build the one closed draw and hand it over. Returns the backend's
; answer, or -1 when the backend refused or faulted.
Procedure.i avkDrawSubmit(c.i)
  Define p.i
  Define b.i
  Define fb.i
  Define img.i
  Define k.i
  Define rc.i

  p = avkPipeSlot(avkCbPipe[c])
  b = avkBufSlot(avkCbVtxBuf[c])
  fb = avkCbFb[c]
  If p = 0 Or b = 0 Or fb = 0
    avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit was given a command buffer whose pipeline, vertex buffer or framebuffer has since been destroyed (Anvil code -20004, stale resource reference); re-record the command buffer against live objects.")
    ProcedureReturn -1
  EndIf
  img = avkIvImgSlot[avkFbView[fb]]
  If avkImgLive[img] = 0 Or avkImgBound[img] = 0
    avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit was given a command buffer whose colour attachment has since been destroyed or unbound (Anvil code -20004, stale resource reference); re-record the command buffer against live resources.")
    ProcedureReturn -1
  EndIf
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
  avkDrawRecord\vertexBase = avkHeapBase + avkMemOffset[avkBufMemSlot[b]] + avkBufMemOffset[b] + avkCbVtxOffset[c]
  avkDrawRecord\vertexStride = avkPipeStride[p]
  avkDrawRecord\vertexCount = avkCbDrawVerts[c]
  avkDrawRecord\firstVertex = avkCbDrawFirst[c]
  If avkCbPushBytes[c] = #ANVIL_VK_PUSH_BYTES
    avkDrawRecord\pushBase = @avkPushStage[0]
    avkDrawRecord\pushBytes = #ANVIL_VK_PUSH_BYTES
  Else
    avkDrawRecord\pushBase = 0
    avkDrawRecord\pushBytes = 0
  EndIf

  rc = avkBackendDrawSupported(avkDrawRecord\targetBase, avkDrawRecord\targetBytes, avkDrawRecord\width, avkDrawRecord\height, avkDrawRecord\pitch)
  If rc <> #VK_SUCCESS
    avkFault(rc, "the graphics backend cannot render into an attachment of this size or at this address (VkResult or Anvil code in AnvilVkFaultCode(); nothing was submitted). The Pi 4 V3D backend renders only at the geometry the engine was initialised with, and never into the buffer the display is scanning out.")
    ProcedureReturn -1
  EndIf
  ProcedureReturn avkBackendSubmitDraw(@avkDrawRecord)
EndProcedure

; The address of the record the last draw was submitted with. A gate
; compares its bytes against an expectation it builds independently, so
; it is readable and it is never written from outside this file.
Procedure.i AnvilVkLastDrawRecord()
  ProcedureReturn @avkDrawRecord
EndProcedure

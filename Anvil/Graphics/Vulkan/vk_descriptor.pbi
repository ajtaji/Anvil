; ======================================================================
;  Descriptor set layouts, pools and sets
; ======================================================================
; SPDX-License-Identifier: MIT
;
; Target neutral. Nothing here knows a QPU register, a VPM slot, a
; control-list packet or a display. It owns the three objects that stand
; between resources and shaders that read them. It resolves a bound uniform
; buffer into one address and one length, and a bounded combined image sampler
; into a closed state record for the future texture backend.
;
; Read from the Khronos Vulkan specification and its registry:
;   .../chapters/descriptorsets.html   descriptor set layouts, pools,
;                                      allocation, and the update rules
;   .../chapters/pipelines.html        how a pipeline layout is built
;                                      out of set layouts
;   registry.khronos.org               the structure member names, their
;                                      order and their widths, and the
;                                      VkDescriptorType enumerants
; Both were CONSULTED, in the sense docs/PROVENANCE_INVENTORY.md defines:
; the names and values are the registry's own, transcribed the way a
; header's values are. No implementation source was read or translated.
;
; ======================================================================
;  WHAT THIS SLICE IMPLEMENTS
; ======================================================================
;   * a descriptor set layout of one or two bindings, each either a
;     uniform buffer or a combined image sampler;
;     every binding has descriptorCount 1 at VK_SHADER_STAGE_FRAGMENT_BIT
;   * a descriptor pool whose rows are accumulated per supported type,
;     including duplicate rows, with optional FREE_DESCRIPTOR_SET_BIT
;   * vkAllocateDescriptorSets of a bounded array, with whole-call preflight
;   * vkFreeDescriptorSets of an atomically checked array, returning each
;     freed set's type budget to its owning pool
;   * vkUpdateDescriptorSets of up to sixteen ordered writes and copies
;   * a uniform buffer of at least sixteen bytes at an offset that is a
;     multiple of sixteen, or one bound linear BGRA8 sampled image view and
;     one sampler in VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL
;
; EVERY OTHER DESCRIPTOR TYPE IS REFUSED BY NAME. A sampler, a separate
; sampled or storage image, a texel buffer, a storage
; buffer, either dynamic variant and an input attachment each get their
; own sentence, because a caller who wrote one of them needs to be told
; which of the eleven this implementation has - not that "6" is the only
; number that works.
;
; ======================================================================
;  THE SEAM TO THE BUFFER OBJECTS
; ======================================================================
;  A uniform buffer is a VkBuffer, and VkBuffers live in vk_pipeline.pbi
;  beside the pipeline objects. This file is included BEFORE that one, so
;  the three things it needs to know about a buffer arrive through
;  declarations here and definitions there - the same seam shape
;  vk_command.pbi already uses for avkDrawSubmit, and for the same
;  reason: the dependency is one way and it is written down.

XIncludeFile "Anvil/Graphics/Vulkan/vk_command.pbi"

Declare.i avkDescBufferLive(buffer.i)     ; 1 when live and bound on this device
Declare.i avkDescBufferUniform(buffer.i)  ; 1 when it named the uniform usage
Declare.i avkDescBufferSize(buffer.i)
Declare.i avkDescBufferAddress(buffer.i)
Declare.i avkDescBufferDevice(buffer.i)
Declare.i avkDescImageViewDevice(view.i)
Declare.i avkDescImageViewImage(view.i)
Declare.i avkDescSamplerDevice(sampler.i)
Declare.i avkDescSamplerMagFilter(sampler.i)
Declare.i avkDescSamplerMinFilter(sampler.i)

; ----------------------------------------------------------------------
;  DESCRIPTOR SET LAYOUTS
; ----------------------------------------------------------------------
Global Dim avkDslLive.a[#ANVIL_VK_MAX_SET_LAYOUTS + 1]
Global Dim avkDslGen.i[#ANVIL_VK_MAX_SET_LAYOUTS + 1]
Global Dim avkDslDev.i[#ANVIL_VK_MAX_SET_LAYOUTS + 1]
Global Dim avkDslCount.i[#ANVIL_VK_MAX_SET_LAYOUTS + 1]
Global Dim avkDslType.i[(#ANVIL_VK_MAX_SET_LAYOUTS + 1) * #ANVIL_VK_MAX_SET_BINDINGS]
Global Dim avkDslStages.i[(#ANVIL_VK_MAX_SET_LAYOUTS + 1) * #ANVIL_VK_MAX_SET_BINDINGS]

; ----------------------------------------------------------------------
;  DESCRIPTOR POOLS
; ----------------------------------------------------------------------
Global Dim avkDpLive.a[#ANVIL_VK_MAX_DESCRIPTOR_POOLS + 1]
Global Dim avkDpGen.i[#ANVIL_VK_MAX_DESCRIPTOR_POOLS + 1]
Global Dim avkDpDev.i[#ANVIL_VK_MAX_DESCRIPTOR_POOLS + 1]
Global Dim avkDpFlags.i[#ANVIL_VK_MAX_DESCRIPTOR_POOLS + 1]
Global Dim avkDpMaxSets.i[#ANVIL_VK_MAX_DESCRIPTOR_POOLS + 1]
Global Dim avkDpSetsOut.i[#ANVIL_VK_MAX_DESCRIPTOR_POOLS + 1]
Global Dim avkDpUboCapacity.i[#ANVIL_VK_MAX_DESCRIPTOR_POOLS + 1]
Global Dim avkDpSampleCapacity.i[#ANVIL_VK_MAX_DESCRIPTOR_POOLS + 1]
Global Dim avkDpUboOut.i[#ANVIL_VK_MAX_DESCRIPTOR_POOLS + 1]
Global Dim avkDpSampleOut.i[#ANVIL_VK_MAX_DESCRIPTOR_POOLS + 1]

; ----------------------------------------------------------------------
;  DESCRIPTOR SETS. One row of bindings each, holding what a write put
;  there: a buffer handle, an offset and a range, resolved to an address
;  only at draw time so a buffer rebound to different memory in between
;  cannot leave a stale address behind.
; ----------------------------------------------------------------------
Global Dim avkDsLive.a[#ANVIL_VK_MAX_DESCRIPTOR_SETS + 1]
Global Dim avkDsGen.i[#ANVIL_VK_MAX_DESCRIPTOR_SETS + 1]
Global Dim avkDsDev.i[#ANVIL_VK_MAX_DESCRIPTOR_SETS + 1]
Global Dim avkDsPool.i[#ANVIL_VK_MAX_DESCRIPTOR_SETS + 1]
; A descriptor set consumes its source layout at allocation. Vulkan permits
; that layout to be destroyed afterwards, so the set owns this immutable
; canonical copy and never follows the destructible source slot again.
Global Dim avkDsCount.i[#ANVIL_VK_MAX_DESCRIPTOR_SETS + 1]
Global Dim avkDsType.i[(#ANVIL_VK_MAX_DESCRIPTOR_SETS + 1) * #ANVIL_VK_MAX_SET_BINDINGS]
Global Dim avkDsStages.i[(#ANVIL_VK_MAX_DESCRIPTOR_SETS + 1) * #ANVIL_VK_MAX_SET_BINDINGS]
Global Dim avkDsBuf.i[(#ANVIL_VK_MAX_DESCRIPTOR_SETS + 1) * #ANVIL_VK_MAX_SET_BINDINGS]
Global Dim avkDsOffset.i[(#ANVIL_VK_MAX_DESCRIPTOR_SETS + 1) * #ANVIL_VK_MAX_SET_BINDINGS]
Global Dim avkDsRange.i[(#ANVIL_VK_MAX_DESCRIPTOR_SETS + 1) * #ANVIL_VK_MAX_SET_BINDINGS]
Global Dim avkDsSampler.i[(#ANVIL_VK_MAX_DESCRIPTOR_SETS + 1) * #ANVIL_VK_MAX_SET_BINDINGS]
Global Dim avkDsView.i[(#ANVIL_VK_MAX_DESCRIPTOR_SETS + 1) * #ANVIL_VK_MAX_SET_BINDINGS]
Global Dim avkDsImageLayout.i[(#ANVIL_VK_MAX_DESCRIPTOR_SETS + 1) * #ANVIL_VK_MAX_SET_BINDINGS]

Procedure.i avkDslSlot(h.i)
  Define s.i
  s = avkTokenShape(h, #ANVIL_VK_TYPE_DESCRIPTOR_SET_LAYOUT, #ANVIL_VK_MAX_SET_LAYOUTS)
  If s = 0 Or avkDslLive[s] = 0 Or avkDslGen[s] <> avkTokenGen(h) : ProcedureReturn 0 : EndIf
  ProcedureReturn s
EndProcedure

Procedure.i avkDpSlot(h.i)
  Define s.i
  s = avkTokenShape(h, #ANVIL_VK_TYPE_DESCRIPTOR_POOL, #ANVIL_VK_MAX_DESCRIPTOR_POOLS)
  If s = 0 Or avkDpLive[s] = 0 Or avkDpGen[s] <> avkTokenGen(h) : ProcedureReturn 0 : EndIf
  ProcedureReturn s
EndProcedure

Procedure.i avkDsSlot(h.i)
  Define s.i
  s = avkTokenShape(h, #ANVIL_VK_TYPE_DESCRIPTOR_SET, #ANVIL_VK_MAX_DESCRIPTOR_SETS)
  If s = 0 Or avkDsLive[s] = 0 Or avkDsGen[s] <> avkTokenGen(h) : ProcedureReturn 0 : EndIf
  ProcedureReturn s
EndProcedure

; Every descriptor type that is neither a uniform buffer nor the bounded
; combined image sampler, each named.
Procedure.i avkDescRefuseType(t.i)
  If t = #VK_DESCRIPTOR_TYPE_SAMPLER Or t = #VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE Or t = #VK_DESCRIPTOR_TYPE_STORAGE_IMAGE
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "Anvil was asked for a separate sampler, sampled image or storage image descriptor (Anvil code -20005, unsupported descriptor type); this bounded slice accepts VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER so the image and sampler are validated as one state record. No SPIR-V texture instruction is accepted yet.")
  EndIf
  If t = #VK_DESCRIPTOR_TYPE_UNIFORM_TEXEL_BUFFER Or t = #VK_DESCRIPTOR_TYPE_STORAGE_TEXEL_BUFFER
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "Anvil was asked for a texel buffer descriptor - VK_DESCRIPTOR_TYPE_UNIFORM_TEXEL_BUFFER or STORAGE_TEXEL_BUFFER (Anvil code -20005, unsupported descriptor type); a texel buffer is reached through a VkBufferView and there is no VkBufferView object here. Use a supported uniform-buffer or bounded combined-image-sampler layout.")
  EndIf
  If t = #VK_DESCRIPTOR_TYPE_STORAGE_BUFFER
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "Anvil was asked for VK_DESCRIPTOR_TYPE_STORAGE_BUFFER (Anvil code -20005, unsupported descriptor type); a storage buffer is written by the shader as well as read, and this implementation has no shader store, no memory barrier between a shader and the host, and no coherence rule to make one correct.")
  EndIf
  If t = #VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER_DYNAMIC Or t = #VK_DESCRIPTOR_TYPE_STORAGE_BUFFER_DYNAMIC
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "Anvil was asked for a dynamic buffer descriptor - VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER_DYNAMIC or STORAGE_BUFFER_DYNAMIC (Anvil code -20005, unsupported descriptor type); a dynamic descriptor takes its offset from vkCmdBindDescriptorSets, and this implementation takes no dynamic offsets. Use VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER and put the offset in the write.")
  EndIf
  If t = #VK_DESCRIPTOR_TYPE_INPUT_ATTACHMENT
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "Anvil was asked for VK_DESCRIPTOR_TYPE_INPUT_ATTACHMENT (Anvil code -20005, unsupported descriptor type); an input attachment is read by a later subpass, and the render pass this slice creates has exactly one subpass.")
  EndIf
  ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "Anvil was given a descriptor type that is not one of the eleven VkDescriptorType values (Anvil code -20001, invalid descriptor type); check the value against the registry's own enumeration.")
EndProcedure

; ======================================================================
;  vkCreateDescriptorSetLayout
; ======================================================================
Procedure.i AnvilVkDescriptorSetLayoutCreate(device.i, *ci.VkDescriptorSetLayoutCreateInfo, *out)
  Define d.i
  Define s.i
  Define n.i
  Define k.i
  Define seen.i
  Define b.i
  Define *bind.VkDescriptorSetLayoutBinding

  If *out = 0 Or *ci = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, #VK_NULL_HANDLE)
  d = avkDevSlot(device)
  If d = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If (*ci\sType & $FFFFFFFF) <> #VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateDescriptorSetLayout was given a VkDescriptorSetLayoutCreateInfo whose sType is wrong (Anvil code -20001, wrong sType); it must be VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO.")
  EndIf
  If *ci\pNext <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateDescriptorSetLayout was given a pNext chain (Anvil code -20005, no pNext extension is implemented); no set layout was created.")
  EndIf
  If (*ci\flags & $FFFFFFFF) <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateDescriptorSetLayout was given creation flags (Anvil code -20005, unsupported flags); push descriptors and update-after-bind both need machinery this implementation does not have, and no flag is accepted.")
  EndIf
  n = *ci\bindingCount & $FFFFFFFF
  If n < 1 Or n > #ANVIL_VK_MAX_SET_BINDINGS Or *ci\pBindings = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateDescriptorSetLayout was given no bindings or more than two (Anvil code -20005, unsupported set layout); one set holds one or two fragment-stage uniform-buffer or combined-image-sampler bindings.")
  EndIf
  seen = 0
  k = 0
  While k < n
    *bind = *ci\pBindings + (k * SizeOf(VkDescriptorSetLayoutBinding))
    b = *bind\binding & $FFFFFFFF
    If b < 0 Or b >= #ANVIL_VK_MAX_SET_BINDINGS
      ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateDescriptorSetLayout was given a binding number this implementation's set cannot hold (Anvil code -20005, unsupported binding number); the bindings of one set are numbered 0 and 1, with no gaps, so that a shader's Binding decoration indexes the set directly.")
    EndIf
    If (seen & (1 << b)) <> 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateDescriptorSetLayout was given two bindings with the same binding number (Anvil code -20001, duplicate binding); each binding of a set is described exactly once.")
    EndIf
    seen = seen | (1 << b)
    If (*bind\descriptorType & $FFFFFFFF) <> #VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER And (*bind\descriptorType & $FFFFFFFF) <> #VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER
      ProcedureReturn avkDescRefuseType(*bind\descriptorType & $FFFFFFFF)
    EndIf
    If (*bind\descriptorCount & $FFFFFFFF) <> 1
      ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateDescriptorSetLayout was given a descriptorCount other than one (Anvil code -20005, unsupported descriptor array); an array of descriptors is indexed in the shader, and the SPIR-V front end refuses arrays and non-constant indices. A count of zero would declare a binding nothing can be written to.")
    EndIf
    If (*bind\stageFlags & $FFFFFFFF) <> #VK_SHADER_STAGE_FRAGMENT_BIT
      ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateDescriptorSetLayout was given stage flags other than VK_SHADER_STAGE_FRAGMENT_BIT alone (Anvil code -20005, unsupported stage); the descriptor path in this implementation supplies the fragment colour, and the emitted vertex programs' uniform stream carries the viewport transform and nothing else.")
    EndIf
    If *bind\pImmutableSamplers <> 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateDescriptorSetLayout was given immutable samplers (Anvil code -20005, immutable samplers not implemented); provide the live sampler in VkDescriptorImageInfo when updating the combined image sampler.")
    EndIf
    k = k + 1
  Wend
  ; The binding numbers must be 0..n-1, which `seen` now decides in one
  ; comparison: a set of n bindings whose numbers have no gap has
  ; exactly the low n bits set.
  If seen <> ((1 << n) - 1)
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateDescriptorSetLayout was given binding numbers with a gap in them (Anvil code -20005, unsupported set layout); a set of n bindings is numbered 0 to n-1 here, so that a shader's Binding decoration indexes the set directly.")
  EndIf

  s = 1
  While s <= #ANVIL_VK_MAX_SET_LAYOUTS And avkDslLive[s] <> 0 : s = s + 1 : Wend
  If s > #ANVIL_VK_MAX_SET_LAYOUTS : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf
  avkDslGen[s] = avkNextGen(avkDslGen[s])
  avkDslDev[s] = d
  avkDslCount[s] = n
  k = 0
  While k < #ANVIL_VK_MAX_SET_BINDINGS
    avkDslType[(s * #ANVIL_VK_MAX_SET_BINDINGS) + k] = -1
    avkDslStages[(s * #ANVIL_VK_MAX_SET_BINDINGS) + k] = 0
    k = k + 1
  Wend
  k = 0
  While k < n
    *bind = *ci\pBindings + (k * SizeOf(VkDescriptorSetLayoutBinding))
    b = *bind\binding & $FFFFFFFF
    avkDslType[(s * #ANVIL_VK_MAX_SET_BINDINGS) + b] = *bind\descriptorType & $FFFFFFFF
    avkDslStages[(s * #ANVIL_VK_MAX_SET_BINDINGS) + b] = *bind\stageFlags & $FFFFFFFF
    k = k + 1
  Wend
  avkDslLive[s] = 1
  PokeI(*out, avkToken(#ANVIL_VK_TYPE_DESCRIPTOR_SET_LAYOUT, s, avkDslGen[s]))
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure AnvilVkDescriptorSetLayoutDestroy(device.i, layout.i)
  Define d.i
  Define s.i
  d = avkDevSlot(device)
  s = avkDslSlot(layout)
  If s = 0
    If layout <> #VK_NULL_HANDLE
      avkFault(#ANVIL_VK_ERR_HANDLE, "vkDestroyDescriptorSetLayout was given a VkDescriptorSetLayout handle that is not live on this device (Anvil code -20002, stale or foreign handle); nothing was destroyed.")
    EndIf
    ProcedureReturn
  EndIf
  If d = 0 Or avkDslDev[s] <> d
    avkFault(#ANVIL_VK_ERR_OWNER, "vkDestroyDescriptorSetLayout was called with a device that does not own this set layout (Anvil code -20003, wrong parent); nothing was destroyed.")
    ProcedureReturn
  EndIf
  ; Sets and pipeline layouts copied the complete schema when they consumed
  ; this object. They therefore remain valid after this source slot is freed
  ; and reused, exactly as Vulkan's create/allocation lifetime rules require.
  avkDslLive[s] = 0
EndProcedure

Procedure.i AnvilVkDescriptorSetLayoutBindingCount(layout.i)
  Define s.i
  s = avkDslSlot(layout)
  If s = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkDslCount[s]
EndProcedure

; ======================================================================
;  vkCreateDescriptorPool
; ======================================================================
Procedure.i AnvilVkDescriptorPoolCreate(device.i, *ci.VkDescriptorPoolCreateInfo, *out)
  Define d.i
  Define s.i
  Define n.i
  Define k.i
  Define t.i
  Define count.i
  Define uboCapacity.i
  Define sampleCapacity.i
  Define *size.VkDescriptorPoolSize

  If *out = 0 Or *ci = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, #VK_NULL_HANDLE)
  d = avkDevSlot(device)
  If d = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If (*ci\sType & $FFFFFFFF) <> #VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateDescriptorPool was given a VkDescriptorPoolCreateInfo whose sType is wrong (Anvil code -20001, wrong sType); it must be VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO.")
  EndIf
  If *ci\pNext <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateDescriptorPool was given a pNext chain (Anvil code -20005, no pNext extension is implemented); no pool was created.")
  EndIf
  If ((*ci\flags & $FFFFFFFF) & (~#VK_DESCRIPTOR_POOL_CREATE_FREE_DESCRIPTOR_SET_BIT)) <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateDescriptorPool was given a creation flag this implementation does not have (Anvil code -20005, unsupported flags); no pool was created.")
  EndIf
  If (*ci\maxSets & $FFFFFFFF) < 1 Or (*ci\maxSets & $FFFFFFFF) > #ANVIL_VK_MAX_DESCRIPTOR_SETS
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateDescriptorPool was given a maxSets of zero or more than four (Anvil code -20005, unsupported pool size); this implementation holds four descriptor sets in total.")
  EndIf
  n = *ci\poolSizeCount & $FFFFFFFF
  If n < 1 Or *ci\pPoolSizes = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateDescriptorPool was given no pool-size rows (Anvil code -20001, empty pool); describe at least one supported descriptor type and a nonzero capacity.")
  EndIf
  ; VkDescriptorPoolSize is an input array, not stored object state. Walk every
  ; row once, validate it, and add duplicate types exactly as Vulkan defines.
  ; Wide integer totals make the explicit UINT32 overflow check independent of
  ; host wrapping, and no pool slot is touched until the whole array is valid.
  uboCapacity = 0
  sampleCapacity = 0
  k = 0
  While k < n
    *size = *ci\pPoolSizes + (k * SizeOf(VkDescriptorPoolSize))
    t = *size\type & $FFFFFFFF
    count = *size\descriptorCount & $FFFFFFFF
    If t <> #VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER And t <> #VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER
      ProcedureReturn avkDescRefuseType(t)
    EndIf
    If count < 1
      ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateDescriptorPool was given a pool-size row with zero descriptors (Anvil code -20001, empty pool-size row); every row must contribute a nonzero capacity.")
    EndIf
    If t = #VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER
      If count > ($FFFFFFFF - uboCapacity)
        ProcedureReturn avkFault(#VK_ERROR_OUT_OF_HOST_MEMORY, "vkCreateDescriptorPool could not represent the sum of its uniform-buffer pool-size rows (VkResult -1, VK_ERROR_OUT_OF_HOST_MEMORY); duplicate rows are added, but their total must fit VkDescriptorPoolSize.descriptorCount. No pool was created.")
      EndIf
      uboCapacity = uboCapacity + count
    Else
      If count > ($FFFFFFFF - sampleCapacity)
        ProcedureReturn avkFault(#VK_ERROR_OUT_OF_HOST_MEMORY, "vkCreateDescriptorPool could not represent the sum of its combined-image-sampler pool-size rows (VkResult -1, VK_ERROR_OUT_OF_HOST_MEMORY); duplicate rows are added, but their total must fit VkDescriptorPoolSize.descriptorCount. No pool was created.")
      EndIf
      sampleCapacity = sampleCapacity + count
    EndIf
    k = k + 1
  Wend

  s = 1
  While s <= #ANVIL_VK_MAX_DESCRIPTOR_POOLS And avkDpLive[s] <> 0 : s = s + 1 : Wend
  If s > #ANVIL_VK_MAX_DESCRIPTOR_POOLS : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf
  avkDpGen[s] = avkNextGen(avkDpGen[s])
  avkDpDev[s] = d
  avkDpFlags[s] = *ci\flags & $FFFFFFFF
  avkDpMaxSets[s] = *ci\maxSets & $FFFFFFFF
  avkDpSetsOut[s] = 0
  avkDpUboCapacity[s] = uboCapacity
  avkDpSampleCapacity[s] = sampleCapacity
  avkDpUboOut[s] = 0
  avkDpSampleOut[s] = 0
  avkDpLive[s] = 1
  PokeI(*out, avkToken(#ANVIL_VK_TYPE_DESCRIPTOR_POOL, s, avkDpGen[s]))
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure avkDescClearSet(s.i)
  Define j.i
  avkDsLive[s] = 0
  avkDsDev[s] = 0
  avkDsPool[s] = 0
  avkDsCount[s] = 0
  j = 0
  While j < #ANVIL_VK_MAX_SET_BINDINGS
    avkDsType[(s * #ANVIL_VK_MAX_SET_BINDINGS) + j] = -1
    avkDsStages[(s * #ANVIL_VK_MAX_SET_BINDINGS) + j] = 0
    avkDsBuf[(s * #ANVIL_VK_MAX_SET_BINDINGS) + j] = 0
    avkDsOffset[(s * #ANVIL_VK_MAX_SET_BINDINGS) + j] = 0
    avkDsRange[(s * #ANVIL_VK_MAX_SET_BINDINGS) + j] = 0
    avkDsSampler[(s * #ANVIL_VK_MAX_SET_BINDINGS) + j] = 0
    avkDsView[(s * #ANVIL_VK_MAX_SET_BINDINGS) + j] = 0
    avkDsImageLayout[(s * #ANVIL_VK_MAX_SET_BINDINGS) + j] = 0
    j = j + 1
  Wend
EndProcedure

Procedure avkDescFreePoolSets(p.i)
  Define k.i
  k = 1
  While k <= #ANVIL_VK_MAX_DESCRIPTOR_SETS
    If avkDsLive[k] <> 0 And avkDsPool[k] = p
      avkDescClearSet(k)
    EndIf
    k = k + 1
  Wend
  avkDpSetsOut[p] = 0
  avkDpUboOut[p] = 0
  avkDpSampleOut[p] = 0
EndProcedure

Procedure.i AnvilVkDescriptorPoolReset(device.i, pool.i)
  Define d.i
  Define p.i
  d = avkDevSlot(device)
  p = avkDpSlot(pool)
  If d = 0 Or p = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkDpDev[p] <> d
    ProcedureReturn avkFault(#ANVIL_VK_ERR_OWNER, "vkResetDescriptorPool was called with a device that does not own this pool (Anvil code -20003, wrong parent); nothing was reset.")
  EndIf
  If avkFlightActive <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkResetDescriptorPool was called while a submission is still in flight (Anvil code -20004, resource in use); nothing was reset. A set this pool holds may be the one the running draw is reading its uniform buffer through. Wait on the submission's fence, or call vkDeviceWaitIdle, first.")
  EndIf
  avkDescFreePoolSets(p)
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure AnvilVkDescriptorPoolDestroy(device.i, pool.i)
  Define d.i
  Define p.i
  d = avkDevSlot(device)
  p = avkDpSlot(pool)
  If p = 0
    If pool <> #VK_NULL_HANDLE
      avkFault(#ANVIL_VK_ERR_HANDLE, "vkDestroyDescriptorPool was given a VkDescriptorPool handle that is not live on this device (Anvil code -20002, stale or foreign handle); nothing was destroyed.")
    EndIf
    ProcedureReturn
  EndIf
  If d = 0 Or avkDpDev[p] <> d
    avkFault(#ANVIL_VK_ERR_OWNER, "vkDestroyDescriptorPool was called with a device that does not own this pool (Anvil code -20003, wrong parent); nothing was destroyed.")
    ProcedureReturn
  EndIf
  If avkFlightActive <> 0
    avkFault(#ANVIL_VK_ERR_STATE, "vkDestroyDescriptorPool was called while a submission is still in flight (Anvil code -20004, resource in use); nothing was destroyed. Wait on the submission's fence, or call vkDeviceWaitIdle, first.")
    ProcedureReturn
  EndIf
  ; Destroying a pool frees every set it handed out - the specification
  ; says so, and this is where that happens.
  avkDescFreePoolSets(p)
  avkDpLive[p] = 0
  avkDpFlags[p] = 0
EndProcedure

; Preflight the complete array before returning a single slot or budget.
; Vulkan permits null entries. A stale, duplicate, foreign or wrong-pool
; non-null entry leaves every live set and counter untouched.
Procedure.i AnvilVkDescriptorSetsFree(device.i, pool.i, count.i, *sets)
  Define d.i
  Define p.i
  Define i.i
  Define j.i
  Define s.i
  Define handle.i
  Define idx.i
  Define needUbo.i
  Define needSample.i
  Define liveCount.i
  d = avkDevSlot(device)
  p = avkDpSlot(pool)
  If d = 0 Or p = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkDpDev[p] <> d
    ProcedureReturn avkFault(#ANVIL_VK_ERR_OWNER, "vkFreeDescriptorSets was given a pool owned by another device (Anvil code -20003, wrong parent); no set was freed.")
  EndIf
  If (avkDpFlags[p] & #VK_DESCRIPTOR_POOL_CREATE_FREE_DESCRIPTOR_SET_BIT) = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkFreeDescriptorSets requires VK_DESCRIPTOR_POOL_CREATE_FREE_DESCRIPTOR_SET_BIT on its pool (Anvil code -20005, pool does not support individual free); no set was freed.")
  EndIf
  If count < 1 Or count > #ANVIL_VK_MAX_DESCRIPTOR_SETS Or *sets = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkFreeDescriptorSets requires a positive bounded descriptorSetCount and an array (Anvil code -20001, invalid array); no set was freed.")
  EndIf
  If avkFlightActive <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkFreeDescriptorSets was called while a submission is in flight (Anvil code -20004, possible descriptor use); wait for its fence or device idle before freeing.")
  EndIf
  needUbo = 0 : needSample = 0 : liveCount = 0
  i = 0
  While i < count
    handle = PeekI(*sets + (i * SizeOf(.i)))
    If handle <> #VK_NULL_HANDLE
      s = avkDsSlot(handle)
      If s = 0
        ProcedureReturn avkFault(#ANVIL_VK_ERR_HANDLE, "vkFreeDescriptorSets was given a stale or invalid set handle (Anvil code -20002, invalid handle); no set was freed.")
      EndIf
      If avkDsDev[s] <> d Or avkDsPool[s] <> p
        ProcedureReturn avkFault(#ANVIL_VK_ERR_OWNER, "vkFreeDescriptorSets was given a set from another device or pool (Anvil code -20003, wrong parent); no set was freed.")
      EndIf
      j = 0
      While j < i
        If PeekI(*sets + (j * SizeOf(.i))) = handle
          ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkFreeDescriptorSets was given a duplicate non-null handle (Anvil code -20001, duplicate set); no set was freed.")
        EndIf
        j = j + 1
      Wend
      liveCount = liveCount + 1
      j = 0
      While j < avkDsCount[s]
        idx = (s * #ANVIL_VK_MAX_SET_BINDINGS) + j
        If avkDsType[idx] = #VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER : needUbo = needUbo + 1 : EndIf
        If avkDsType[idx] = #VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER : needSample = needSample + 1 : EndIf
        j = j + 1
      Wend
    EndIf
    i = i + 1
  Wend
  If liveCount > avkDpSetsOut[p] Or needUbo > avkDpUboOut[p] Or needSample > avkDpSampleOut[p]
    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkFreeDescriptorSets found inconsistent pool accounting (Anvil code -20004, internal pool state); no set was freed.")
  EndIf
  i = 0
  While i < count
    handle = PeekI(*sets + (i * SizeOf(.i)))
    If handle <> #VK_NULL_HANDLE
      avkDescClearSet(avkDsSlot(handle))
    EndIf
    i = i + 1
  Wend
  avkDpSetsOut[p] = avkDpSetsOut[p] - liveCount
  avkDpUboOut[p] = avkDpUboOut[p] - needUbo
  avkDpSampleOut[p] = avkDpSampleOut[p] - needSample
  ProcedureReturn #VK_SUCCESS
EndProcedure

; ======================================================================
;  vkAllocateDescriptorSets
; ======================================================================
Procedure.i AnvilVkDescriptorSetsAllocate(device.i, *ai.VkDescriptorSetAllocateInfo, *out)
  Define d.i
  Define p.i
  Define lay.i
  Define s.i
  Define k.i
  Define idx.i
  Define i.i
  Define count.i
  Define found.i
  Define needUbo.i
  Define needSample.i
  Define Dim layouts.i(#ANVIL_VK_MAX_DESCRIPTOR_SETS - 1)
  Define Dim slots.i(#ANVIL_VK_MAX_DESCRIPTOR_SETS - 1)

  If *out = 0 Or *ai = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  count = *ai\descriptorSetCount & $FFFFFFFF
  If count = 0 Or count > #ANVIL_VK_MAX_DESCRIPTOR_SETS
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkAllocateDescriptorSets needs between one and the bounded global descriptor-set capacity per call (Anvil code -20005, unsupported allocation count).")
  EndIf
  For i = 0 To count - 1
    PokeI(*out + i * SizeOf(.i), #VK_NULL_HANDLE)
  Next

  d = avkDevSlot(device)
  If d = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If (*ai\sType & $FFFFFFFF) <> #VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkAllocateDescriptorSets was given a VkDescriptorSetAllocateInfo whose sType is wrong (Anvil code -20001, wrong sType); it must be VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO.")
  EndIf
  If *ai\pNext <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkAllocateDescriptorSets was given a pNext chain (Anvil code -20005, no pNext extension is implemented); no set was allocated.")
  EndIf
  If *ai\pSetLayouts = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkAllocateDescriptorSets needs a layout for every requested set (Anvil code -20001, null pSetLayouts).")
  EndIf

  p = avkDpSlot(*ai\descriptorPool)
  If p = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkDpDev[p] <> d
    ProcedureReturn avkFault(#ANVIL_VK_ERR_OWNER, "vkAllocateDescriptorSets was given a descriptor pool from a different VkDevice (Anvil code -20003, wrong parent).")
  EndIf

  ; Validate the complete layout array and sum both descriptor budgets before
  ; publishing any set. No failed call can leave a partially allocated array.
  needUbo = 0
  needSample = 0
  For i = 0 To count - 1
    lay = avkDslSlot(PeekI(*ai\pSetLayouts + i * SizeOf(.i)))
    If lay = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
    If avkDslDev[lay] <> d
      ProcedureReturn avkFault(#ANVIL_VK_ERR_OWNER, "vkAllocateDescriptorSets was given a set layout from a different VkDevice (Anvil code -20003, wrong parent).")
    EndIf
    layouts(i) = lay
    For k = 0 To avkDslCount[lay] - 1
      idx = (lay * #ANVIL_VK_MAX_SET_BINDINGS) + k
      If avkDslType[idx] = #VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER
        needUbo = needUbo + 1
      ElseIf avkDslType[idx] = #VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER
        needSample = needSample + 1
      Else
        ProcedureReturn #ANVIL_VK_ERR_STATE
      EndIf
    Next
  Next

  If count > (avkDpMaxSets[p] - avkDpSetsOut[p])
    ProcedureReturn avkFault(#VK_ERROR_OUT_OF_POOL_MEMORY, "vkAllocateDescriptorSets needs more set slots than this pool has left (VkResult -1000069000, VK_ERROR_OUT_OF_POOL_MEMORY); no set was allocated.")
  EndIf
  If needUbo > (avkDpUboCapacity[p] - avkDpUboOut[p]) Or needSample > (avkDpSampleCapacity[p] - avkDpSampleOut[p])
    ProcedureReturn avkFault(#VK_ERROR_OUT_OF_POOL_MEMORY, "vkAllocateDescriptorSets needs more uniform-buffer or combined-image-sampler descriptors than this pool has left (VkResult -1000069000, VK_ERROR_OUT_OF_POOL_MEMORY); no set or per-type counter was changed.")
  EndIf

  found = 0
  For s = 1 To #ANVIL_VK_MAX_DESCRIPTOR_SETS
    If avkDsLive[s] = 0
      slots(found) = s
      found = found + 1
      If found = count : Break : EndIf
    EndIf
  Next
  If found <> count : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf

  ; Every operation after preflight is a non-failing table write.
  For i = 0 To count - 1
    s = slots(i)
    lay = layouts(i)
    avkDsGen[s] = avkNextGen(avkDsGen[s])
    avkDsDev[s] = d
    avkDsPool[s] = p
    avkDsCount[s] = avkDslCount[lay]
    For k = 0 To #ANVIL_VK_MAX_SET_BINDINGS - 1
      idx = (s * #ANVIL_VK_MAX_SET_BINDINGS) + k
      avkDsType[idx] = -1
      avkDsStages[idx] = 0
      If k < avkDslCount[lay]
        avkDsType[idx] = avkDslType[(lay * #ANVIL_VK_MAX_SET_BINDINGS) + k]
        avkDsStages[idx] = avkDslStages[(lay * #ANVIL_VK_MAX_SET_BINDINGS) + k]
      EndIf
      avkDsBuf[idx] = 0
      avkDsOffset[idx] = 0
      avkDsRange[idx] = 0
      avkDsSampler[idx] = 0
      avkDsView[idx] = 0
      avkDsImageLayout[idx] = 0
    Next
    avkDsLive[s] = 1
    PokeI(*out + i * SizeOf(.i), avkToken(#ANVIL_VK_TYPE_DESCRIPTOR_SET, s, avkDsGen[s]))
  Next
  avkDpSetsOut[p] = avkDpSetsOut[p] + count
  avkDpUboOut[p] = avkDpUboOut[p] + needUbo
  avkDpSampleOut[p] = avkDpSampleOut[p] + needSample
  ProcedureReturn #VK_SUCCESS
EndProcedure

; ======================================================================
;  vkUpdateDescriptorSets
; ======================================================================
;  Each bounded write is validated against its destination schema. All writes
;  commit in array order, or an invalid later write restores the prior state.
;  Copies then execute in order, with matching source/destination schemas.
Procedure.i AnvilVkDescriptorSetWriteOne(device.i, *pWrites.VkWriteDescriptorSet)
  Define d.i
  Define s.i
  Define b.i
  Define t.i
  Define idx.i
  Define buf.i
  Define off.i
  Define range.i
  Define size.i
  Define sampler.i
  Define view.i
  Define image.i
  Define img.i
  Define *info.VkDescriptorBufferInfo
  Define *imageInfo.VkDescriptorImageInfo

  d = avkDevSlot(device)
  If d = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If (*pWrites\sType & $FFFFFFFF) <> #VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkUpdateDescriptorSets was given a VkWriteDescriptorSet whose sType is wrong (Anvil code -20001, wrong sType); it must be VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET.")
  EndIf
  If *pWrites\pNext <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkUpdateDescriptorSets was given a pNext chain on its write (Anvil code -20005, no pNext extension is implemented); nothing was written.")
  EndIf
  s = avkDsSlot(*pWrites\dstSet)
  If s = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkDsDev[s] <> d
    ProcedureReturn avkFault(#ANVIL_VK_ERR_OWNER, "vkUpdateDescriptorSets was given a descriptor set from a different VkDevice (Anvil code -20003, wrong parent); nothing was written.")
  EndIf
  If avkFlightActive <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkUpdateDescriptorSets was called while a submission is still in flight (Anvil code -20004, resource in use); nothing was written. The specification forbids updating a descriptor set a pending command buffer uses, and this slice has one submission at a time, so every set is in use while one is running.")
  EndIf
  b = *pWrites\dstBinding & $FFFFFFFF
  If b < 0 Or b >= avkDsCount[s]
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkUpdateDescriptorSets was given a dstBinding this set's layout does not declare (Anvil code -20001, no such binding); the bindings a set has are the ones its VkDescriptorSetLayout described.")
  EndIf
  If (*pWrites\dstArrayElement & $FFFFFFFF) <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkUpdateDescriptorSets was given a dstArrayElement other than zero (Anvil code -20001, no descriptor array); every binding here has a descriptorCount of one, so element zero is the only element there is.")
  EndIf
  If (*pWrites\descriptorCount & $FFFFFFFF) <> 1
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkUpdateDescriptorSets was given a descriptorCount other than one (Anvil code -20001, no descriptor array); one write fills one binding here.")
  EndIf
  t = *pWrites\descriptorType & $FFFFFFFF
  If t <> avkDsType[(s * #ANVIL_VK_MAX_SET_BINDINGS) + b]
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkUpdateDescriptorSets was given a descriptorType different from the type declared for dstBinding (Anvil code -20001, descriptor type mismatch); use the VkDescriptorType from the VkDescriptorSetLayoutBinding that created this set's layout.")
  EndIf
  idx = (s * #ANVIL_VK_MAX_SET_BINDINGS) + b
  If t = #VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER
    If *pWrites\pImageInfo <> 0 Or *pWrites\pTexelBufferView <> 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkUpdateDescriptorSets was given a pImageInfo or a pTexelBufferView on a uniform-buffer write (Anvil code -20001, wrong descriptor arm); a VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER write is described by pBufferInfo and by nothing else.")
    EndIf
    If *pWrites\pBufferInfo = 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkUpdateDescriptorSets was given a uniform-buffer write with no pBufferInfo (Anvil code -20001, missing buffer info); nothing was written.")
    EndIf
    *info = *pWrites\pBufferInfo
    buf = *info\buffer
    If avkDescBufferLive(buf) = 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_HANDLE, "vkUpdateDescriptorSets was given a VkBuffer handle that is not live, or has no memory bound to it (Anvil code -20002, stale handle or unbound buffer); call vkBindBufferMemory before writing a buffer into a descriptor, because the descriptor is what the shader reads through.")
    EndIf
    If avkDescBufferDevice(buf) <> d
      ProcedureReturn avkFault(#ANVIL_VK_ERR_OWNER, "vkUpdateDescriptorSets was given a buffer from a different VkDevice from the descriptor set (Anvil code -20003, wrong parent); nothing was written.")
    EndIf
    If avkDescBufferUniform(buf) = 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkUpdateDescriptorSets was given a buffer that was not created with VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT (Anvil code -20001, missing usage); a buffer a shader reads through a uniform-buffer descriptor must name that usage in VkBufferCreateInfo.")
    EndIf
    size = avkDescBufferSize(buf)
    off = *info\offset
    range = *info\range
    If off < 0 Or off >= size Or (off % #ANVIL_VK_UNIFORM_ALIGN) <> 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkUpdateDescriptorSets was given a uniform-buffer offset that is negative, past the end of the buffer, or not a multiple of sixteen (Anvil code -20001, misaligned descriptor); sixteen is this device's minUniformBufferOffsetAlignment and it is the size of the block as well.")
    EndIf
    If range = #VK_WHOLE_SIZE
      range = size - off
    EndIf
    ; Avoid off+range: an adversarial near-UINT64 range must not wrap into
    ; this buffer. `off` is already inside `size`, so subtraction is exact.
    If range < #ANVIL_VK_UNIFORM_BYTES Or range > (size - off)
      ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkUpdateDescriptorSets was given a uniform-buffer range shorter than the sixteen-byte block, or one that runs past the end of the buffer (Anvil code -20001, range outside the buffer); the block a fragment shader reads here is one four-component colour.")
    EndIf
    avkDsBuf[idx] = buf
    avkDsOffset[idx] = off
    avkDsRange[idx] = range
    avkDsSampler[idx] = 0
    avkDsView[idx] = 0
    avkDsImageLayout[idx] = 0
    ProcedureReturn #VK_SUCCESS
  EndIf

  If t = #VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER
    If *pWrites\pBufferInfo <> 0 Or *pWrites\pTexelBufferView <> 0 Or *pWrites\pImageInfo = 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkUpdateDescriptorSets was given the wrong information arm for a combined image sampler (Anvil code -20001, wrong descriptor arm); provide exactly one VkDescriptorImageInfo through pImageInfo and leave pBufferInfo and pTexelBufferView null.")
    EndIf
    *imageInfo = *pWrites\pImageInfo
    If (*imageInfo\imageLayout & $FFFFFFFF) <> #VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL
      ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkUpdateDescriptorSets was given a combined image sampler whose imageLayout is not VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL (Anvil code -20001, wrong sampled layout); transition the image with vkCmdPipelineBarrier and name that layout in VkDescriptorImageInfo.")
    EndIf
    sampler = *imageInfo\sampler
    view = *imageInfo\imageView
    If avkDescSamplerDevice(sampler) = 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_HANDLE, "vkUpdateDescriptorSets was given a VkSampler handle that is not live (Anvil code -20002, stale sampler); create the bounded sampler before writing the combined image sampler descriptor.")
    EndIf
    If avkDescImageViewDevice(view) = 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_HANDLE, "vkUpdateDescriptorSets was given a VkImageView handle that is not live (Anvil code -20002, stale image view); create a full single-level colour view before writing the combined image sampler descriptor.")
    EndIf
    If avkDescSamplerDevice(sampler) <> d Or avkDescImageViewDevice(view) <> d
      ProcedureReturn avkFault(#ANVIL_VK_ERR_OWNER, "vkUpdateDescriptorSets was given a sampler or image view from a different VkDevice from the descriptor set (Anvil code -20003, wrong parent); all three objects must be created by one device.")
    EndIf
    image = avkDescImageViewImage(view)
    img = avkImgSlot(image)
    If img = 0 Or avkImgBound[img] = 0 Or AnvilVkImageAddress(image) = 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_HANDLE, "vkUpdateDescriptorSets was given an image view whose image is stale or has no memory bound (Anvil code -20002, stale or unbound sampled image); bind the image's memory before writing its view into a descriptor.")
    EndIf
    If avkImgDev[img] <> d
      ProcedureReturn avkFault(#ANVIL_VK_ERR_OWNER, "vkUpdateDescriptorSets reached an image from a different VkDevice (Anvil code -20003, wrong parent); create the image, view, sampler and descriptor set through one device.")
    EndIf
    If (avkImgUsage[img] & #VK_IMAGE_USAGE_SAMPLED_BIT) = 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkUpdateDescriptorSets was given an image not created with VK_IMAGE_USAGE_SAMPLED_BIT (Anvil code -20001, missing sampled usage); image views do not add usage rights, so recreate the image with sampled usage.")
    EndIf
    avkDsBuf[idx] = 0
    avkDsOffset[idx] = 0
    avkDsRange[idx] = 0
    avkDsSampler[idx] = sampler
    avkDsView[idx] = view
    avkDsImageLayout[idx] = #VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL
    ProcedureReturn #VK_SUCCESS
  EndIf

  ProcedureReturn avkDescRefuseType(t)
EndProcedure

Procedure.i AnvilVkDescriptorSetCopyOne(device.i, *copy.VkCopyDescriptorSet)
  Define d.i
  Define src.i
  Define dst.i
  Define srcBinding.i
  Define dstBinding.i
  Define count.i
  Define j.i
  Define srcIdx.i
  Define dstIdx.i

  d = avkDevSlot(device)
  If d = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If (*copy\sType & $FFFFFFFF) <> #VK_STRUCTURE_TYPE_COPY_DESCRIPTOR_SET
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkUpdateDescriptorSets received a VkCopyDescriptorSet with the wrong sType (Anvil code -20001); nothing was copied.")
  EndIf
  If *copy\pNext <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkUpdateDescriptorSets received an unsupported descriptor-copy pNext chain (Anvil code -20005); nothing was copied.")
  EndIf
  src = avkDsSlot(*copy\srcSet)
  dst = avkDsSlot(*copy\dstSet)
  If src = 0 Or dst = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkDsDev[src] <> d Or avkDsDev[dst] <> d
    ProcedureReturn avkFault(#ANVIL_VK_ERR_OWNER, "vkUpdateDescriptorSets copy source and destination must belong to the same VkDevice (Anvil code -20003); nothing was copied.")
  EndIf
  If avkFlightActive <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkUpdateDescriptorSets cannot copy into a descriptor set while a submission is in flight (Anvil code -20004); nothing was copied.")
  EndIf
  srcBinding = *copy\srcBinding & $FFFFFFFF
  dstBinding = *copy\dstBinding & $FFFFFFFF
  count = *copy\descriptorCount & $FFFFFFFF
  If (*copy\srcArrayElement & $FFFFFFFF) <> 0 Or (*copy\dstArrayElement & $FFFFFFFF) <> 0 Or count < 1 Or count > #ANVIL_VK_MAX_SET_BINDINGS
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkUpdateDescriptorSets copies only whole one-element bindings in the bounded descriptor schema (Anvil code -20001); nothing was copied.")
  EndIf
  If srcBinding >= avkDsCount[src] Or dstBinding >= avkDsCount[dst] Or count > (avkDsCount[src] - srcBinding) Or count > (avkDsCount[dst] - dstBinding)
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkUpdateDescriptorSets copy range exceeds a source or destination set binding (Anvil code -20001); nothing was copied.")
  EndIf
  If src = dst And srcBinding < (dstBinding + count) And dstBinding < (srcBinding + count)
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkUpdateDescriptorSets cannot copy overlapping descriptor ranges within one set (Anvil code -20001); nothing was copied.")
  EndIf
  For j = 0 To count - 1
    srcIdx = (src * #ANVIL_VK_MAX_SET_BINDINGS) + srcBinding + j
    dstIdx = (dst * #ANVIL_VK_MAX_SET_BINDINGS) + dstBinding + j
    If avkDsType[srcIdx] <> avkDsType[dstIdx]
      ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkUpdateDescriptorSets copy source and destination descriptor types differ (Anvil code -20001); nothing was copied.")
    EndIf
    If j <> 0
      If avkDsType[srcIdx] <> avkDsType[srcIdx - j] Or avkDsStages[srcIdx] <> avkDsStages[srcIdx - j] Or avkDsType[dstIdx] <> avkDsType[dstIdx - j] Or avkDsStages[dstIdx] <> avkDsStages[dstIdx - j]
        ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkUpdateDescriptorSets copy crosses bindings with different descriptor types or stage flags (Anvil code -20001); nothing was copied.")
      EndIf
    EndIf
  Next
  For j = 0 To count - 1
    srcIdx = (src * #ANVIL_VK_MAX_SET_BINDINGS) + srcBinding + j
    dstIdx = (dst * #ANVIL_VK_MAX_SET_BINDINGS) + dstBinding + j
    avkDsBuf[dstIdx] = avkDsBuf[srcIdx]
    avkDsOffset[dstIdx] = avkDsOffset[srcIdx]
    avkDsRange[dstIdx] = avkDsRange[srcIdx]
    avkDsSampler[dstIdx] = avkDsSampler[srcIdx]
    avkDsView[dstIdx] = avkDsView[srcIdx]
    avkDsImageLayout[dstIdx] = avkDsImageLayout[srcIdx]
  Next
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkDescriptorSetsUpdate(device.i, writeCount.i, *pWrites.VkWriteDescriptorSet, copyCount.i, *pCopies.VkCopyDescriptorSet)
  Define i.i
  Define rc.i
  ; PMF's current A64 lowering can lose the fifth parameter after nested
  ; calls; capture its entry value before any validation calls.
  Define copyBase.i = *pCopies
  Define Dim priorBuf.i[(#ANVIL_VK_MAX_DESCRIPTOR_SETS + 1) * #ANVIL_VK_MAX_SET_BINDINGS - 1]
  Define Dim priorOffset.i[(#ANVIL_VK_MAX_DESCRIPTOR_SETS + 1) * #ANVIL_VK_MAX_SET_BINDINGS - 1]
  Define Dim priorRange.i[(#ANVIL_VK_MAX_DESCRIPTOR_SETS + 1) * #ANVIL_VK_MAX_SET_BINDINGS - 1]
  Define Dim priorSampler.i[(#ANVIL_VK_MAX_DESCRIPTOR_SETS + 1) * #ANVIL_VK_MAX_SET_BINDINGS - 1]
  Define Dim priorView.i[(#ANVIL_VK_MAX_DESCRIPTOR_SETS + 1) * #ANVIL_VK_MAX_SET_BINDINGS - 1]
  Define Dim priorImageLayout.i[(#ANVIL_VK_MAX_DESCRIPTOR_SETS + 1) * #ANVIL_VK_MAX_SET_BINDINGS - 1]

  If avkDevSlot(device) = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If writeCount < 0 Or writeCount > 16 Or copyCount < 0 Or copyCount > 16 Or (writeCount <> 0 And *pWrites = 0) Or (copyCount <> 0 And copyBase = 0)
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkUpdateDescriptorSets needs bounded write and copy arrays of at most sixteen operations each (Anvil code -20005, unsupported update).")
  EndIf
  If writeCount = 0 And copyCount = 0 : ProcedureReturn #VK_SUCCESS : EndIf

  ; Snapshot the complete bounded payload table. Sequential writes see earlier
  ; writes, but a refused later write restores every earlier destination.
  For i = 0 To ((#ANVIL_VK_MAX_DESCRIPTOR_SETS + 1) * #ANVIL_VK_MAX_SET_BINDINGS) - 1
    priorBuf(i) = avkDsBuf[i]
    priorOffset(i) = avkDsOffset[i]
    priorRange(i) = avkDsRange[i]
    priorSampler(i) = avkDsSampler[i]
    priorView(i) = avkDsView[i]
    priorImageLayout(i) = avkDsImageLayout[i]
  Next
  If writeCount <> 0
  For i = 0 To writeCount - 1
    rc = AnvilVkDescriptorSetWriteOne(device, *pWrites + i * SizeOf(VkWriteDescriptorSet))
    If rc <> #VK_SUCCESS
      For i = 0 To ((#ANVIL_VK_MAX_DESCRIPTOR_SETS + 1) * #ANVIL_VK_MAX_SET_BINDINGS) - 1
        avkDsBuf[i] = priorBuf(i)
        avkDsOffset[i] = priorOffset(i)
        avkDsRange[i] = priorRange(i)
        avkDsSampler[i] = priorSampler(i)
        avkDsView[i] = priorView(i)
        avkDsImageLayout[i] = priorImageLayout(i)
      Next
      ProcedureReturn rc
    EndIf
  Next
  EndIf
  If copyCount <> 0
  For i = 0 To copyCount - 1
    rc = AnvilVkDescriptorSetCopyOne(device, copyBase + i * SizeOf(VkCopyDescriptorSet))
    If rc <> #VK_SUCCESS
      For i = 0 To ((#ANVIL_VK_MAX_DESCRIPTOR_SETS + 1) * #ANVIL_VK_MAX_SET_BINDINGS) - 1
        avkDsBuf[i] = priorBuf(i)
        avkDsOffset[i] = priorOffset(i)
        avkDsRange[i] = priorRange(i)
        avkDsSampler[i] = priorSampler(i)
        avkDsView[i] = priorView(i)
        avkDsImageLayout[i] = priorImageLayout(i)
      Next
      ProcedureReturn rc
    EndIf
  Next
  EndIf
  ProcedureReturn #VK_SUCCESS
EndProcedure

; ======================================================================
;  WHAT A BOUND SET RESOLVES TO
; ======================================================================
;  Read at draw time and not at write time. A VkBuffer can be rebound to
;  different memory between the update and the draw, so an address
;  captured in vkUpdateDescriptorSets would be the one thing in the
;  record that was not current.
Procedure.i AnvilVkDescriptorSetAddress(set.i, binding.i)
  Define s.i
  Define buf.i
  s = avkDsSlot(set)
  If s = 0 : ProcedureReturn 0 : EndIf
  If binding < 0 Or binding >= avkDsCount[s] : ProcedureReturn 0 : EndIf
  If avkDsType[(s * #ANVIL_VK_MAX_SET_BINDINGS) + binding] <> #VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER : ProcedureReturn 0 : EndIf
  buf = avkDsBuf[(s * #ANVIL_VK_MAX_SET_BINDINGS) + binding]
  If buf = 0 Or avkDescBufferLive(buf) = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkDescBufferAddress(buf) + avkDsOffset[(s * #ANVIL_VK_MAX_SET_BINDINGS) + binding]
EndProcedure

Procedure.i AnvilVkDescriptorSetRange(set.i, binding.i)
  Define s.i
  s = avkDsSlot(set)
  If s = 0 : ProcedureReturn 0 : EndIf
  If binding < 0 Or binding >= avkDsCount[s] : ProcedureReturn 0 : EndIf
  If avkDsType[(s * #ANVIL_VK_MAX_SET_BINDINGS) + binding] <> #VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER : ProcedureReturn 0 : EndIf
  ProcedureReturn avkDsRange[(s * #ANVIL_VK_MAX_SET_BINDINGS) + binding]
EndProcedure

Procedure.i AnvilVkDescriptorSetBuffer(set.i, binding.i)
  Define s.i
  s = avkDsSlot(set)
  If s = 0 : ProcedureReturn 0 : EndIf
  If binding < 0 Or binding >= avkDsCount[s] : ProcedureReturn 0 : EndIf
  If avkDsType[(s * #ANVIL_VK_MAX_SET_BINDINGS) + binding] <> #VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER : ProcedureReturn 0 : EndIf
  ProcedureReturn avkDsBuf[(s * #ANVIL_VK_MAX_SET_BINDINGS) + binding]
EndProcedure

; Resolve the state-only combined image sampler into the one closed record the
; texture backend will consume. Resolution happens here, not at update time:
; destroying an image view or sampler, destroying/reusing its image slot, or
; transitioning the image away from the descriptor's promised layout can
; never leave a stale address or stale state in a later draw.
Procedure.i AnvilVkDescriptorSetSampledImage(set.i, binding.i, *out.AnvilVkBackendSampledImage)
  Define s.i
  Define idx.i
  Define sampler.i
  Define view.i
  Define image.i
  Define img.i
  If *out = 0 : ProcedureReturn 0 : EndIf
  *out\base = 0
  *out\bytes = 0
  *out\width = 0
  *out\height = 0
  *out\pitch = 0
  *out\format = 0
  *out\layout = 0
  *out\magFilter = 0
  *out\minFilter = 0
  *out\tiling = 0
  *out\backendLayout = 0
  *out\paddedWidth = 0
  *out\paddedHeight = 0
  s = avkDsSlot(set)
  If s = 0 Or binding < 0 Or binding >= avkDsCount[s] : ProcedureReturn 0 : EndIf
  If avkDsType[(s * #ANVIL_VK_MAX_SET_BINDINGS) + binding] <> #VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER : ProcedureReturn 0 : EndIf
  idx = (s * #ANVIL_VK_MAX_SET_BINDINGS) + binding
  sampler = avkDsSampler[idx]
  view = avkDsView[idx]
  If avkDescSamplerDevice(sampler) <> avkDsDev[s] Or avkDescImageViewDevice(view) <> avkDsDev[s] : ProcedureReturn 0 : EndIf
  image = avkDescImageViewImage(view)
  img = avkImgSlot(image)
  If img = 0 Or avkImgDev[img] <> avkDsDev[s] Or avkImgBound[img] = 0 : ProcedureReturn 0 : EndIf
  If (avkImgUsage[img] & #VK_IMAGE_USAGE_SAMPLED_BIT) = 0 : ProcedureReturn 0 : EndIf
  If avkImgLayout[img] <> avkDsImageLayout[idx] Or avkImgLayout[img] <> #VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL : ProcedureReturn 0 : EndIf
  *out\base = AnvilVkImageAddress(image)
  If *out\base = 0 : ProcedureReturn 0 : EndIf
  *out\bytes = avkImgSize[img]
  *out\width = avkImgW[img]
  *out\height = avkImgH[img]
  *out\pitch = avkImgPitch[img]
  *out\format = #VK_FORMAT_B8G8R8A8_UNORM
  *out\layout = avkImgLayout[img]
  *out\magFilter = avkDescSamplerMagFilter(sampler)
  *out\minFilter = avkDescSamplerMinFilter(sampler)
  *out\tiling = avkImgTiling[img]
  *out\backendLayout = avkImgBackendLayout[img]
  *out\paddedWidth = avkImgPaddedW[img]
  *out\paddedHeight = avkImgPaddedH[img]
  ProcedureReturn 1
EndProcedure

; The live VkImage behind a sampled descriptor, for submission retention.
; The closed record above owns all backend-visible properties; this handle is
; used only by the portable lifetime counters and is never handed to a backend.
Procedure.i AnvilVkDescriptorSetSampledImageHandle(set.i, binding.i)
  Define s.i
  Define idx.i
  Define view.i
  Define image.i
  s = avkDsSlot(set)
  If s = 0 Or binding < 0 Or binding >= avkDsCount[s] : ProcedureReturn 0 : EndIf
  If avkDsType[(s * #ANVIL_VK_MAX_SET_BINDINGS) + binding] <> #VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER : ProcedureReturn 0 : EndIf
  idx = (s * #ANVIL_VK_MAX_SET_BINDINGS) + binding
  view = avkDsView[idx]
  If avkDescImageViewDevice(view) <> avkDsDev[s] : ProcedureReturn 0 : EndIf
  image = avkDescImageViewImage(view)
  If avkImgSlot(image) = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn image
EndProcedure

Procedure.i AnvilVkDescriptorSetSamplerHandle(set.i, binding.i)
  Define s.i = avkDsSlot(set)
  If s = 0 Or binding < 0 Or binding >= avkDsCount[s] : ProcedureReturn 0 : EndIf
  If avkDsType[(s * #ANVIL_VK_MAX_SET_BINDINGS) + binding] <> #VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER : ProcedureReturn 0 : EndIf
  ProcedureReturn avkDsSampler[(s * #ANVIL_VK_MAX_SET_BINDINGS) + binding]
EndProcedure

Procedure.i AnvilVkDescriptorSetImageViewHandle(set.i, binding.i)
  Define s.i = avkDsSlot(set)
  If s = 0 Or binding < 0 Or binding >= avkDsCount[s] : ProcedureReturn 0 : EndIf
  If avkDsType[(s * #ANVIL_VK_MAX_SET_BINDINGS) + binding] <> #VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER : ProcedureReturn 0 : EndIf
  ProcedureReturn avkDsView[(s * #ANVIL_VK_MAX_SET_BINDINGS) + binding]
EndProcedure

; Canonical immutable schema accessors. Layout accessors consume a live source
; during creation/allocation; set accessors read the private copy afterwards.
Procedure.i AnvilVkSetLayoutDeviceSlotOf(layout.i)
  Define s.i = avkDslSlot(layout)
  If s = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkDslDev[s]
EndProcedure

Procedure.i AnvilVkSetLayoutBindingCountOf(layout.i)
  Define s.i = avkDslSlot(layout)
  If s = 0 : ProcedureReturn -1 : EndIf
  ProcedureReturn avkDslCount[s]
EndProcedure

Procedure.i AnvilVkSetLayoutBindingTypeOf(layout.i, binding.i)
  Define s.i = avkDslSlot(layout)
  If s = 0 Or binding < 0 Or binding >= avkDslCount[s] : ProcedureReturn -1 : EndIf
  ProcedureReturn avkDslType[(s * #ANVIL_VK_MAX_SET_BINDINGS) + binding]
EndProcedure

Procedure.i AnvilVkSetLayoutBindingStagesOf(layout.i, binding.i)
  Define s.i = avkDslSlot(layout)
  If s = 0 Or binding < 0 Or binding >= avkDslCount[s] : ProcedureReturn 0 : EndIf
  ProcedureReturn avkDslStages[(s * #ANVIL_VK_MAX_SET_BINDINGS) + binding]
EndProcedure

Procedure.i AnvilVkDescriptorSetDeviceSlot(set.i)
  Define s.i = avkDsSlot(set)
  If s = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkDsDev[s]
EndProcedure

Procedure.i AnvilVkDescriptorSetSchemaCount(set.i)
  Define s.i = avkDsSlot(set)
  If s = 0 : ProcedureReturn -1 : EndIf
  ProcedureReturn avkDsCount[s]
EndProcedure

Procedure.i AnvilVkDescriptorSetSchemaType(set.i, binding.i)
  Define s.i = avkDsSlot(set)
  If s = 0 Or binding < 0 Or binding >= avkDsCount[s] : ProcedureReturn -1 : EndIf
  ProcedureReturn avkDsType[(s * #ANVIL_VK_MAX_SET_BINDINGS) + binding]
EndProcedure

Procedure.i AnvilVkDescriptorSetSchemaStages(set.i, binding.i)
  Define s.i = avkDsSlot(set)
  If s = 0 Or binding < 0 Or binding >= avkDsCount[s] : ProcedureReturn 0 : EndIf
  ProcedureReturn avkDsStages[(s * #ANVIL_VK_MAX_SET_BINDINGS) + binding]
EndProcedure

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
;   * a descriptor set layout of one or two uniform-buffer bindings, or
;     one VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER at binding zero;
;     every binding has descriptorCount 1 at VK_SHADER_STAGE_FRAGMENT_BIT
;   * a descriptor pool of one pool size, matching its set layout, with no
;     VK_DESCRIPTOR_POOL_CREATE_FREE_DESCRIPTOR_SET_BIT
;   * vkAllocateDescriptorSets of one set at a time
;   * vkUpdateDescriptorSets of one write at a time, no copies
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
Global Dim avkDpMaxSets.i[#ANVIL_VK_MAX_DESCRIPTOR_POOLS + 1]
Global Dim avkDpCapacity.i[#ANVIL_VK_MAX_DESCRIPTOR_POOLS + 1]
Global Dim avkDpType.i[#ANVIL_VK_MAX_DESCRIPTOR_POOLS + 1]
Global Dim avkDpSetsOut.i[#ANVIL_VK_MAX_DESCRIPTOR_POOLS + 1]
Global Dim avkDpDescOut.i[#ANVIL_VK_MAX_DESCRIPTOR_POOLS + 1]

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
Global Dim avkDsLayout.i[#ANVIL_VK_MAX_DESCRIPTOR_SETS + 1]
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
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateDescriptorSetLayout was given no bindings or more than two (Anvil code -20005, unsupported set layout); one set holds one or two uniform-buffer bindings, or one combined image sampler at binding zero.")
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
    If (*bind\descriptorType & $FFFFFFFF) = #VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER And (n <> 1 Or b <> 0)
      ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateDescriptorSetLayout placed a combined image sampler anywhere other than the only binding in set zero (Anvil code -20005, unsupported sampled-image layout); this first sampled state record is exactly one VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER at binding zero.")
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
  avkDslLive[s] = 1
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
  PokeI(*out, avkToken(#ANVIL_VK_TYPE_DESCRIPTOR_SET_LAYOUT, s, avkDslGen[s]))
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure AnvilVkDescriptorSetLayoutDestroy(device.i, layout.i)
  Define d.i
  Define s.i
  Define k.i
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
  ; A LAYOUT A LIVE SET WAS ALLOCATED FROM IS NOT DESTROYED. The
  ; specification lets a set outlive its layout; this implementation
  ; reads the layout back at bind time to check the shader's binding, so
  ; destroying it under a live set would leave that check reading a slot
  ; that had been handed to somebody else.
  k = 1
  While k <= #ANVIL_VK_MAX_DESCRIPTOR_SETS
    If avkDsLive[k] <> 0 And avkDsLayout[k] = s
      avkFault(#ANVIL_VK_ERR_STATE, "vkDestroyDescriptorSetLayout was called while a descriptor set allocated from it is still live (Anvil code -20004, resource in use); nothing was destroyed. Reset or destroy the descriptor pool first. This implementation reads the layout back when a set is bound, so it may not outlive its sets.")
      ProcedureReturn
    EndIf
    k = k + 1
  Wend
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
  If (*ci\flags & #VK_DESCRIPTOR_POOL_CREATE_FREE_DESCRIPTOR_SET_BIT) <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateDescriptorPool was asked for VK_DESCRIPTOR_POOL_CREATE_FREE_DESCRIPTOR_SET_BIT (Anvil code -20005, individual descriptor-set freeing not implemented); vkFreeDescriptorSets has nothing to return a set to. Destroy or reset the whole pool instead.")
  EndIf
  If (*ci\flags & $FFFFFFFF) <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateDescriptorPool was given a creation flag this implementation does not have (Anvil code -20005, unsupported flags); no pool was created.")
  EndIf
  If (*ci\maxSets & $FFFFFFFF) < 1 Or (*ci\maxSets & $FFFFFFFF) > #ANVIL_VK_MAX_DESCRIPTOR_SETS
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateDescriptorPool was given a maxSets of zero or more than four (Anvil code -20005, unsupported pool size); this implementation holds four descriptor sets in total.")
  EndIf
  If (*ci\poolSizeCount & $FFFFFFFF) <> 1 Or *ci\pPoolSizes = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateDescriptorPool was given other than exactly one pool size (Anvil code -20005, unsupported pool); there is one descriptor type here, so one VkDescriptorPoolSize describes the whole pool.")
  EndIf
  *size = *ci\pPoolSizes
  If (*size\type & $FFFFFFFF) <> #VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER And (*size\type & $FFFFFFFF) <> #VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER
    ProcedureReturn avkDescRefuseType(*size\type & $FFFFFFFF)
  EndIf
  If (*size\descriptorCount & $FFFFFFFF) < 1
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateDescriptorPool was given a pool size of zero descriptors (Anvil code -20001, empty pool); a pool that can supply nothing would refuse the first vkAllocateDescriptorSets, which is a failure better reported here.")
  EndIf

  s = 1
  While s <= #ANVIL_VK_MAX_DESCRIPTOR_POOLS And avkDpLive[s] <> 0 : s = s + 1 : Wend
  If s > #ANVIL_VK_MAX_DESCRIPTOR_POOLS : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf
  avkDpGen[s] = avkNextGen(avkDpGen[s])
  avkDpLive[s] = 1
  avkDpDev[s] = d
  avkDpMaxSets[s] = *ci\maxSets & $FFFFFFFF
  avkDpCapacity[s] = *size\descriptorCount & $FFFFFFFF
  avkDpType[s] = *size\type & $FFFFFFFF
  avkDpSetsOut[s] = 0
  avkDpDescOut[s] = 0
  PokeI(*out, avkToken(#ANVIL_VK_TYPE_DESCRIPTOR_POOL, s, avkDpGen[s]))
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure avkDescFreePoolSets(p.i)
  Define k.i
  Define j.i
  k = 1
  While k <= #ANVIL_VK_MAX_DESCRIPTOR_SETS
    If avkDsLive[k] <> 0 And avkDsPool[k] = p
      avkDsLive[k] = 0
      j = 0
      While j < #ANVIL_VK_MAX_SET_BINDINGS
        avkDsBuf[(k * #ANVIL_VK_MAX_SET_BINDINGS) + j] = 0
        avkDsOffset[(k * #ANVIL_VK_MAX_SET_BINDINGS) + j] = 0
        avkDsRange[(k * #ANVIL_VK_MAX_SET_BINDINGS) + j] = 0
        avkDsSampler[(k * #ANVIL_VK_MAX_SET_BINDINGS) + j] = 0
        avkDsView[(k * #ANVIL_VK_MAX_SET_BINDINGS) + j] = 0
        avkDsImageLayout[(k * #ANVIL_VK_MAX_SET_BINDINGS) + j] = 0
        j = j + 1
      Wend
    EndIf
    k = k + 1
  Wend
  avkDpSetsOut[p] = 0
  avkDpDescOut[p] = 0
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

  If *out = 0 Or *ai = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, #VK_NULL_HANDLE)
  d = avkDevSlot(device)
  If d = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If (*ai\sType & $FFFFFFFF) <> #VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkAllocateDescriptorSets was given a VkDescriptorSetAllocateInfo whose sType is wrong (Anvil code -20001, wrong sType); it must be VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO.")
  EndIf
  If *ai\pNext <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkAllocateDescriptorSets was given a pNext chain (Anvil code -20005, no pNext extension is implemented); no set was allocated.")
  EndIf
  If (*ai\descriptorSetCount & $FFFFFFFF) <> 1 Or *ai\pSetLayouts = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkAllocateDescriptorSets was asked for other than exactly one descriptor set (Anvil code -20005, unsupported allocation); allocate one set per call here, so that a partial failure cannot leave some of an array written and the rest not.")
  EndIf
  p = avkDpSlot(*ai\descriptorPool)
  If p = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  lay = avkDslSlot(PeekI(*ai\pSetLayouts))
  If lay = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkDpDev[p] <> d Or avkDslDev[lay] <> d
    ProcedureReturn avkFault(#ANVIL_VK_ERR_OWNER, "vkAllocateDescriptorSets was given a descriptor pool or a set layout from a different VkDevice (Anvil code -20003, wrong parent); every object in one allocation must share a device.")
  EndIf
  If avkDpSetsOut[p] >= avkDpMaxSets[p]
    ProcedureReturn avkFault(#VK_ERROR_OUT_OF_POOL_MEMORY, "vkAllocateDescriptorSets has already handed out every set this pool declared (VkResult -1000069000, VK_ERROR_OUT_OF_POOL_MEMORY); no set was allocated. Raise VkDescriptorPoolCreateInfo.maxSets, or reset the pool.")
  EndIf
  If (avkDpDescOut[p] + avkDslCount[lay]) > avkDpCapacity[p]
    ProcedureReturn avkFault(#VK_ERROR_OUT_OF_POOL_MEMORY, "vkAllocateDescriptorSets needs more descriptors than this pool declared (VkResult -1000069000, VK_ERROR_OUT_OF_POOL_MEMORY); no set was allocated. The pool's VkDescriptorPoolSize.descriptorCount counts DESCRIPTORS and not sets, so a set of two bindings costs two.")
  EndIf
  k = 0
  While k < avkDslCount[lay]
    If avkDslType[(lay * #ANVIL_VK_MAX_SET_BINDINGS) + k] <> avkDpType[p]
      ProcedureReturn avkFault(#VK_ERROR_OUT_OF_POOL_MEMORY, "vkAllocateDescriptorSets was given a set layout whose descriptor type is absent from this pool (VkResult -1000069000, VK_ERROR_OUT_OF_POOL_MEMORY); create the pool with a VkDescriptorPoolSize.type matching every binding in the layout.")
    EndIf
    k = k + 1
  Wend

  s = 1
  While s <= #ANVIL_VK_MAX_DESCRIPTOR_SETS And avkDsLive[s] <> 0 : s = s + 1 : Wend
  If s > #ANVIL_VK_MAX_DESCRIPTOR_SETS : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf
  avkDsGen[s] = avkNextGen(avkDsGen[s])
  avkDsLive[s] = 1
  avkDsDev[s] = d
  avkDsPool[s] = p
  avkDsLayout[s] = lay
  k = 0
  While k < #ANVIL_VK_MAX_SET_BINDINGS
    avkDsBuf[(s * #ANVIL_VK_MAX_SET_BINDINGS) + k] = 0
    avkDsOffset[(s * #ANVIL_VK_MAX_SET_BINDINGS) + k] = 0
    avkDsRange[(s * #ANVIL_VK_MAX_SET_BINDINGS) + k] = 0
    avkDsSampler[(s * #ANVIL_VK_MAX_SET_BINDINGS) + k] = 0
    avkDsView[(s * #ANVIL_VK_MAX_SET_BINDINGS) + k] = 0
    avkDsImageLayout[(s * #ANVIL_VK_MAX_SET_BINDINGS) + k] = 0
    k = k + 1
  Wend
  avkDpSetsOut[p] = avkDpSetsOut[p] + 1
  avkDpDescOut[p] = avkDpDescOut[p] + avkDslCount[lay]
  PokeI(*out, avkToken(#ANVIL_VK_TYPE_DESCRIPTOR_SET, s, avkDsGen[s]))
  ProcedureReturn #VK_SUCCESS
EndProcedure

; ======================================================================
;  vkUpdateDescriptorSets
; ======================================================================
;  ONE WRITE PER CALL and no copies. A descriptor copy moves a binding
;  from one set to another and would let a set hold a descriptor whose
;  type its own layout never declared; there is no reason to have it
;  here and every reason not to guess at its rules.
Procedure.i AnvilVkDescriptorSetsUpdate(device.i, writeCount.i, *pWrites.VkWriteDescriptorSet, copyCount.i, *pCopies)
  Define d.i
  Define s.i
  Define lay.i
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
  If copyCount <> 0 Or *pCopies <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkUpdateDescriptorSets was given descriptor copies (Anvil code -20005, descriptor copies not implemented); nothing was written. A copy would move a descriptor between sets without either set's layout being consulted, and this implementation checks a write against the layout every time.")
  EndIf
  If writeCount <> 1 Or *pWrites = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkUpdateDescriptorSets was given other than exactly one write (Anvil code -20005, unsupported update); write one descriptor per call here, so a refusal names the write that failed and no earlier write in the same array has already landed.")
  EndIf
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
  lay = avkDsLayout[s]
  b = *pWrites\dstBinding & $FFFFFFFF
  If b < 0 Or b >= avkDslCount[lay]
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkUpdateDescriptorSets was given a dstBinding this set's layout does not declare (Anvil code -20001, no such binding); the bindings a set has are the ones its VkDescriptorSetLayout described.")
  EndIf
  If (*pWrites\dstArrayElement & $FFFFFFFF) <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkUpdateDescriptorSets was given a dstArrayElement other than zero (Anvil code -20001, no descriptor array); every binding here has a descriptorCount of one, so element zero is the only element there is.")
  EndIf
  If (*pWrites\descriptorCount & $FFFFFFFF) <> 1
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkUpdateDescriptorSets was given a descriptorCount other than one (Anvil code -20001, no descriptor array); one write fills one binding here.")
  EndIf
  t = *pWrites\descriptorType & $FFFFFFFF
  If t <> avkDslType[(lay * #ANVIL_VK_MAX_SET_BINDINGS) + b]
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
    If range < #ANVIL_VK_UNIFORM_BYTES Or (off + range) > size
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
  If binding < 0 Or binding >= #ANVIL_VK_MAX_SET_BINDINGS : ProcedureReturn 0 : EndIf
  buf = avkDsBuf[(s * #ANVIL_VK_MAX_SET_BINDINGS) + binding]
  If buf = 0 Or avkDescBufferLive(buf) = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkDescBufferAddress(buf) + avkDsOffset[(s * #ANVIL_VK_MAX_SET_BINDINGS) + binding]
EndProcedure

Procedure.i AnvilVkDescriptorSetRange(set.i, binding.i)
  Define s.i
  s = avkDsSlot(set)
  If s = 0 : ProcedureReturn 0 : EndIf
  If binding < 0 Or binding >= #ANVIL_VK_MAX_SET_BINDINGS : ProcedureReturn 0 : EndIf
  ProcedureReturn avkDsRange[(s * #ANVIL_VK_MAX_SET_BINDINGS) + binding]
EndProcedure

Procedure.i AnvilVkDescriptorSetBuffer(set.i, binding.i)
  Define s.i
  s = avkDsSlot(set)
  If s = 0 : ProcedureReturn 0 : EndIf
  If binding < 0 Or binding >= #ANVIL_VK_MAX_SET_BINDINGS : ProcedureReturn 0 : EndIf
  ProcedureReturn avkDsBuf[(s * #ANVIL_VK_MAX_SET_BINDINGS) + binding]
EndProcedure

; Resolve the state-only combined image sampler into the one closed record the
; texture backend will consume. Resolution happens here, not at update time:
; destroying an image view or sampler, destroying/reusing its image slot, or
; transitioning the image away from the descriptor's promised layout can
; never leave a stale address or stale state in a later draw.
Procedure.i AnvilVkDescriptorSetSampledImage(set.i, binding.i, *out.AnvilVkBackendSampledImage)
  Define s.i
  Define lay.i
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
  If s = 0 Or binding < 0 Or binding >= #ANVIL_VK_MAX_SET_BINDINGS : ProcedureReturn 0 : EndIf
  lay = avkDsLayout[s]
  If binding >= avkDslCount[lay] : ProcedureReturn 0 : EndIf
  If avkDslType[(lay * #ANVIL_VK_MAX_SET_BINDINGS) + binding] <> #VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER : ProcedureReturn 0 : EndIf
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
  Define lay.i
  Define idx.i
  Define view.i
  Define image.i
  s = avkDsSlot(set)
  If s = 0 Or binding < 0 Or binding >= #ANVIL_VK_MAX_SET_BINDINGS : ProcedureReturn 0 : EndIf
  lay = avkDsLayout[s]
  If binding >= avkDslCount[lay] : ProcedureReturn 0 : EndIf
  If avkDslType[(lay * #ANVIL_VK_MAX_SET_BINDINGS) + binding] <> #VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER : ProcedureReturn 0 : EndIf
  idx = (s * #ANVIL_VK_MAX_SET_BINDINGS) + binding
  view = avkDsView[idx]
  If avkDescImageViewDevice(view) <> avkDsDev[s] : ProcedureReturn 0 : EndIf
  image = avkDescImageViewImage(view)
  If avkImgSlot(image) = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn image
EndProcedure

; The set layout a live set was allocated from, as a SLOT, so the
; pipeline layer can compare it against the one its pipeline layout
; declares without either of them holding a handle the other could
; invalidate.
Procedure.i AnvilVkDescriptorSetLayoutSlot(set.i)
  Define s.i
  s = avkDsSlot(set)
  If s = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkDsLayout[s]
EndProcedure

; Whether a set layout SLOT declares a uniform buffer at `binding`, in
; the fragment stage. The pipeline layer asks this about the layout its
; pipeline layout holds and about the binding the shader's Binding
; decoration named.
Procedure.i AnvilVkSetLayoutHasUniform(lay.i, binding.i)
  If lay < 1 Or lay > #ANVIL_VK_MAX_SET_LAYOUTS Or avkDslLive[lay] = 0 : ProcedureReturn 0 : EndIf
  If binding < 0 Or binding >= avkDslCount[lay] : ProcedureReturn 0 : EndIf
  If avkDslType[(lay * #ANVIL_VK_MAX_SET_BINDINGS) + binding] <> #VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER : ProcedureReturn 0 : EndIf
  If (avkDslStages[(lay * #ANVIL_VK_MAX_SET_BINDINGS) + binding] & #VK_SHADER_STAGE_FRAGMENT_BIT) = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i AnvilVkSetLayoutHasSampledImage(lay.i, binding.i)
  If lay < 1 Or lay > #ANVIL_VK_MAX_SET_LAYOUTS Or avkDslLive[lay] = 0 : ProcedureReturn 0 : EndIf
  If binding < 0 Or binding >= avkDslCount[lay] : ProcedureReturn 0 : EndIf
  If avkDslType[(lay * #ANVIL_VK_MAX_SET_BINDINGS) + binding] <> #VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER : ProcedureReturn 0 : EndIf
  If (avkDslStages[(lay * #ANVIL_VK_MAX_SET_BINDINGS) + binding] & #VK_SHADER_STAGE_FRAGMENT_BIT) = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i AnvilVkDescriptorSetLayoutSlotOf(layout.i)
  ProcedureReturn avkDslSlot(layout)
EndProcedure

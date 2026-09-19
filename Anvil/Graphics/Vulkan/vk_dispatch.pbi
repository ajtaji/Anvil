; ======================================================================
;  Vulkan core-1.0 procedure-address dispatch (target neutral)
; ======================================================================
; SPDX-License-Identifier: MIT
;
; Include seam: vk_api.pbi first, then this file.  This is deliberately a
; hand-reviewed semantic allowlist.  A public Procedure declaration is NOT
; enough to enter this table.  Names absent here resolve to null, including
; commands which merely exist to report a deterministic unsupported result.
;
; Vulkan 1.0 lookup domains used here:
;   GIPA(NULL)     - audited global commands only (currently vkCreateInstance)
;   GIPA(instance) - audited instance/device commands and both resolvers
;   GDPA(device)   - audited device commands and GDPA itself
; Handles are generation checked before any table lookup, so null, foreign and
; stale owners never disclose a pointer.

#AVK_DISPATCH_GLOBAL = 1
#AVK_DISPATCH_INSTANCE = 2
#AVK_DISPATCH_DEVICE = 4

#AVK_QUERY_GIPA_NULL = 1
#AVK_QUERY_GIPA_INSTANCE = 2
#AVK_QUERY_GDPA_DEVICE = 4

Declare.i vkGetInstanceProcAddr(instance.i, *pName)
Declare.i vkGetDeviceProcAddr(device.i, *pName)

; Byte-exact, case-sensitive, NUL-terminated match.  The explicit cap keeps a
; malformed non-terminated caller string from turning lookup into an unbounded
; read.  Vulkan core command names are far shorter than 128 bytes.
Procedure.i avkDispatchName(*actual, expected.i)
  Define n.i
  Define a.i
  Define b.i
  If *actual = 0 Or expected = 0 : ProcedureReturn 0 : EndIf
  n = 0
  While n < 128
    a = PeekA(*actual + n)
    b = PeekA(expected + n)
    If a <> b : ProcedureReturn 0 : EndIf
    If a = 0 : ProcedureReturn 1 : EndIf
    n = n + 1
  Wend
  ProcedureReturn 0
EndProcedure

Procedure.i avkDispatchAddress(commandDomain.i, address.i, queryDomain.i)
  If address = 0 : ProcedureReturn 0 : EndIf
  If commandDomain = #AVK_DISPATCH_GLOBAL And queryDomain = #AVK_QUERY_GIPA_NULL
    ProcedureReturn address
  EndIf
  If commandDomain = #AVK_DISPATCH_INSTANCE And queryDomain = #AVK_QUERY_GIPA_INSTANCE
    ProcedureReturn address
  EndIf
  If commandDomain = #AVK_DISPATCH_DEVICE And (queryDomain = #AVK_QUERY_GIPA_INSTANCE Or queryDomain = #AVK_QUERY_GDPA_DEVICE)
    ProcedureReturn address
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i avkDispatchLookup(*pName, domain.i)
  ; The two resolver entries are separately audited members of this layer.
  If avkDispatchName(*pName, "vkGetInstanceProcAddr") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_INSTANCE, @vkGetInstanceProcAddr, domain) : EndIf
  If avkDispatchName(*pName, "vkGetDeviceProcAddr") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkGetDeviceProcAddr, domain) : EndIf

  ; Semantic allowlist approved 2026-09-13. vkFreeDescriptorSets is withheld:
  ; every pool refuses its enabling flag, so the declaration is not usable
  ; semantics. The bounded whole-image vkCmdCopyBufferToImage transaction is
  ; exposed after its independent desk and Pi 4 silicon gates passed.
  If avkDispatchName(*pName, "vkAllocateCommandBuffers") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkAllocateCommandBuffers, domain) : EndIf
  If avkDispatchName(*pName, "vkAllocateDescriptorSets") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkAllocateDescriptorSets, domain) : EndIf
  If avkDispatchName(*pName, "vkAllocateMemory") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkAllocateMemory, domain) : EndIf
  If avkDispatchName(*pName, "vkBeginCommandBuffer") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkBeginCommandBuffer, domain) : EndIf
  If avkDispatchName(*pName, "vkBindBufferMemory") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkBindBufferMemory, domain) : EndIf
  If avkDispatchName(*pName, "vkBindImageMemory") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkBindImageMemory, domain) : EndIf
  If avkDispatchName(*pName, "vkCmdBeginRenderPass") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkCmdBeginRenderPass, domain) : EndIf
  If avkDispatchName(*pName, "vkCmdBindDescriptorSets") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkCmdBindDescriptorSets, domain) : EndIf
  If avkDispatchName(*pName, "vkCmdBindIndexBuffer") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkCmdBindIndexBuffer, domain) : EndIf
  If avkDispatchName(*pName, "vkCmdBindPipeline") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkCmdBindPipeline, domain) : EndIf
  If avkDispatchName(*pName, "vkCmdBindVertexBuffers") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkCmdBindVertexBuffers, domain) : EndIf
  If avkDispatchName(*pName, "vkCmdClearColorImage") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkCmdClearColorImage, domain) : EndIf
  If avkDispatchName(*pName, "vkCmdCopyBufferToImage") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkCmdCopyBufferToImage, domain) : EndIf
  If avkDispatchName(*pName, "vkCmdDraw") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkCmdDraw, domain) : EndIf
  If avkDispatchName(*pName, "vkCmdDrawIndexed") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkCmdDrawIndexed, domain) : EndIf
  If avkDispatchName(*pName, "vkCmdEndRenderPass") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkCmdEndRenderPass, domain) : EndIf
  If avkDispatchName(*pName, "vkCmdPipelineBarrier") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkCmdPipelineBarrier, domain) : EndIf
  If avkDispatchName(*pName, "vkCmdPushConstants") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkCmdPushConstants, domain) : EndIf
  If avkDispatchName(*pName, "vkCmdSetScissor") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkCmdSetScissor, domain) : EndIf
  If avkDispatchName(*pName, "vkCmdSetViewport") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkCmdSetViewport, domain) : EndIf
  If avkDispatchName(*pName, "vkCreateBuffer") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkCreateBuffer, domain) : EndIf
  If avkDispatchName(*pName, "vkCreateCommandPool") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkCreateCommandPool, domain) : EndIf
  If avkDispatchName(*pName, "vkCreateDescriptorPool") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkCreateDescriptorPool, domain) : EndIf
  If avkDispatchName(*pName, "vkCreateDescriptorSetLayout") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkCreateDescriptorSetLayout, domain) : EndIf
  If avkDispatchName(*pName, "vkCreateDevice") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_INSTANCE, @vkCreateDevice, domain) : EndIf
  If avkDispatchName(*pName, "vkCreateFence") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkCreateFence, domain) : EndIf
  If avkDispatchName(*pName, "vkCreateFramebuffer") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkCreateFramebuffer, domain) : EndIf
  If avkDispatchName(*pName, "vkCreateGraphicsPipelines") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkCreateGraphicsPipelines, domain) : EndIf
  If avkDispatchName(*pName, "vkCreateImage") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkCreateImage, domain) : EndIf
  If avkDispatchName(*pName, "vkCreateImageView") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkCreateImageView, domain) : EndIf
  If avkDispatchName(*pName, "vkCreateInstance") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_GLOBAL, @vkCreateInstance, domain) : EndIf
  If avkDispatchName(*pName, "vkCreatePipelineLayout") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkCreatePipelineLayout, domain) : EndIf
  If avkDispatchName(*pName, "vkCreateRenderPass") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkCreateRenderPass, domain) : EndIf
  If avkDispatchName(*pName, "vkCreateSampler") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkCreateSampler, domain) : EndIf
  If avkDispatchName(*pName, "vkCreateSemaphore") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkCreateSemaphore, domain) : EndIf
  If avkDispatchName(*pName, "vkCreateShaderModule") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkCreateShaderModule, domain) : EndIf
  If avkDispatchName(*pName, "vkDestroyBuffer") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkDestroyBuffer, domain) : EndIf
  If avkDispatchName(*pName, "vkDestroyCommandPool") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkDestroyCommandPool, domain) : EndIf
  If avkDispatchName(*pName, "vkDestroyDescriptorPool") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkDestroyDescriptorPool, domain) : EndIf
  If avkDispatchName(*pName, "vkDestroyDescriptorSetLayout") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkDestroyDescriptorSetLayout, domain) : EndIf
  If avkDispatchName(*pName, "vkDestroyDevice") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkDestroyDevice, domain) : EndIf
  If avkDispatchName(*pName, "vkDestroyFence") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkDestroyFence, domain) : EndIf
  If avkDispatchName(*pName, "vkDestroyFramebuffer") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkDestroyFramebuffer, domain) : EndIf
  If avkDispatchName(*pName, "vkDestroyImage") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkDestroyImage, domain) : EndIf
  If avkDispatchName(*pName, "vkDestroyImageView") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkDestroyImageView, domain) : EndIf
  If avkDispatchName(*pName, "vkDestroyInstance") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_INSTANCE, @vkDestroyInstance, domain) : EndIf
  If avkDispatchName(*pName, "vkDestroyPipeline") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkDestroyPipeline, domain) : EndIf
  If avkDispatchName(*pName, "vkDestroyPipelineLayout") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkDestroyPipelineLayout, domain) : EndIf
  If avkDispatchName(*pName, "vkDestroyRenderPass") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkDestroyRenderPass, domain) : EndIf
  If avkDispatchName(*pName, "vkDestroySampler") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkDestroySampler, domain) : EndIf
  If avkDispatchName(*pName, "vkDestroySemaphore") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkDestroySemaphore, domain) : EndIf
  If avkDispatchName(*pName, "vkDestroyShaderModule") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkDestroyShaderModule, domain) : EndIf
  If avkDispatchName(*pName, "vkDeviceWaitIdle") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkDeviceWaitIdle, domain) : EndIf
  If avkDispatchName(*pName, "vkEndCommandBuffer") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkEndCommandBuffer, domain) : EndIf
  If avkDispatchName(*pName, "vkEnumeratePhysicalDevices") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_INSTANCE, @vkEnumeratePhysicalDevices, domain) : EndIf
  If avkDispatchName(*pName, "vkFreeCommandBuffers") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkFreeCommandBuffers, domain) : EndIf
  If avkDispatchName(*pName, "vkFreeMemory") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkFreeMemory, domain) : EndIf
  If avkDispatchName(*pName, "vkGetBufferMemoryRequirements") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkGetBufferMemoryRequirements, domain) : EndIf
  If avkDispatchName(*pName, "vkGetDeviceQueue") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkGetDeviceQueue, domain) : EndIf
  If avkDispatchName(*pName, "vkGetFenceStatus") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkGetFenceStatus, domain) : EndIf
  If avkDispatchName(*pName, "vkGetImageMemoryRequirements") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkGetImageMemoryRequirements, domain) : EndIf
  If avkDispatchName(*pName, "vkGetPhysicalDeviceFeatures") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_INSTANCE, @vkGetPhysicalDeviceFeatures, domain) : EndIf
  If avkDispatchName(*pName, "vkGetPhysicalDeviceFormatProperties") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_INSTANCE, @vkGetPhysicalDeviceFormatProperties, domain) : EndIf
  If avkDispatchName(*pName, "vkGetPhysicalDeviceImageFormatProperties") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_INSTANCE, @vkGetPhysicalDeviceImageFormatProperties, domain) : EndIf
  If avkDispatchName(*pName, "vkGetPhysicalDeviceMemoryProperties") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_INSTANCE, @vkGetPhysicalDeviceMemoryProperties, domain) : EndIf
  If avkDispatchName(*pName, "vkGetPhysicalDeviceQueueFamilyProperties") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_INSTANCE, @vkGetPhysicalDeviceQueueFamilyProperties, domain) : EndIf
  If avkDispatchName(*pName, "vkMapMemory") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkMapMemory, domain) : EndIf
  If avkDispatchName(*pName, "vkQueueSubmit") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkQueueSubmit, domain) : EndIf
  If avkDispatchName(*pName, "vkResetCommandBuffer") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkResetCommandBuffer, domain) : EndIf
  If avkDispatchName(*pName, "vkResetCommandPool") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkResetCommandPool, domain) : EndIf
  If avkDispatchName(*pName, "vkResetDescriptorPool") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkResetDescriptorPool, domain) : EndIf
  If avkDispatchName(*pName, "vkResetFences") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkResetFences, domain) : EndIf
  If avkDispatchName(*pName, "vkUnmapMemory") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkUnmapMemory, domain) : EndIf
  If avkDispatchName(*pName, "vkUpdateDescriptorSets") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkUpdateDescriptorSets, domain) : EndIf
  If avkDispatchName(*pName, "vkWaitForFences") : ProcedureReturn avkDispatchAddress(#AVK_DISPATCH_DEVICE, @vkWaitForFences, domain) : EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i vkGetInstanceProcAddr(instance.i, *pName)
  If *pName = 0 : ProcedureReturn 0 : EndIf
  If instance = #VK_NULL_HANDLE
    ProcedureReturn avkDispatchLookup(*pName, #AVK_QUERY_GIPA_NULL)
  EndIf
  If avkInstSlot(instance) = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkDispatchLookup(*pName, #AVK_QUERY_GIPA_INSTANCE)
EndProcedure

Procedure.i vkGetDeviceProcAddr(device.i, *pName)
  If *pName = 0 Or avkDevSlot(device) = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkDispatchLookup(*pName, #AVK_QUERY_GDPA_DEVICE)
EndProcedure

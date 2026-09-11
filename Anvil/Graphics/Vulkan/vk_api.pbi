; ======================================================================
;  Anvil's public Vulkan entry points -- core 1.0, the implemented subset
; ======================================================================
; SPDX-License-Identifier: MIT
;
; These are the callable vk* names with the registry's own parameter
; lists and the registry's own return types. They validate sType, pNext,
; flags, counts, pointers, parents and host-synchronization rules, then
; enter the portable object engine. Nothing below invents a return value
; for a void command, and nothing reports unsupported work as success.
;
; THE SURFACE IS DELIBERATELY SMALL. Every core-1.0 command that is not
; declared in this file simply does not exist yet; a caller linking one
; gets a compile-time refusal naming it, which is the loudest possible
; answer and far better than a stub that returns VK_SUCCESS.
;
; There is no loader, no vkGetInstanceProcAddr, no dispatch table, no
; layer interface and no extension negotiation. A program calls these
; names directly, at link time. That is a real limitation and it is in
; the capability table.
;
; The include order is fixed and explicit:
;     XIncludeFile "Anvil/Graphics/Vulkan/vk_api.pbi"
;     XIncludeFile "<exactly one backend>"
; The backend defines the seam this engine calls; see vk_foundation.pbi.

XIncludeFile "Anvil/Graphics/Vulkan/vk_command.pbi"

; VkAllocationCallbacks is not implemented. A caller that passes one is
; refused rather than quietly ignored, because Vulkan's contract is that
; every allocation an implementation makes for that object goes through
; those callbacks, and Anvil's do not.
Procedure.i avkNoAllocator(*pAllocator, site.i)
  If *pAllocator = 0 : ProcedureReturn #VK_SUCCESS : EndIf
  ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "a Vulkan command was given host allocation callbacks (Anvil code -20005, VkAllocationCallbacks not implemented); nothing was created or destroyed. Anvil allocates from fixed internal tables, so it cannot honour pfnAllocation, and pretending to would be worse than refusing. Pass a null pAllocator.")
EndProcedure

Procedure.i avkNoPNext(*pNext)
  If *pNext = 0 : ProcedureReturn #VK_SUCCESS : EndIf
  ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "a Vulkan create-info carried a pNext chain (Anvil code -20005, no pNext extension is implemented); nothing was created. Every structure this implementation accepts must have pNext set to null, because an ignored extension structure is a silently different request.")
EndProcedure

; ----------------------------------------------------------------------
;  INSTANCE, PHYSICAL DEVICE, DEVICE, QUEUE
; ----------------------------------------------------------------------
Procedure.i vkCreateInstance(*pCreateInfo.VkInstanceCreateInfo, *pAllocator, *pInstance)
  Define rc.i
  If *pCreateInfo = 0 Or *pInstance = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  rc = avkNoAllocator(*pAllocator, 1)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  If *pCreateInfo\sType <> #VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateInstance was given a VkInstanceCreateInfo whose sType is not VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO (Anvil code -20001, wrong sType); set sType before filling the rest of the structure.")
  EndIf
  rc = avkNoPNext(*pCreateInfo\pNext)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  If *pCreateInfo\flags <> 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  If *pCreateInfo\enabledLayerCount <> 0
    ProcedureReturn avkFault(#VK_ERROR_LAYER_NOT_PRESENT, "vkCreateInstance was asked to enable an instance layer (VkResult -6, VK_ERROR_LAYER_NOT_PRESENT); no instance was created. Anvil has no layer interface, so vkEnumerateInstanceLayerProperties would report none.")
  EndIf
  If *pCreateInfo\enabledExtensionCount <> 0
    ProcedureReturn avkFault(#VK_ERROR_EXTENSION_NOT_PRESENT, "vkCreateInstance was asked to enable an instance extension (VkResult -7, VK_ERROR_EXTENSION_NOT_PRESENT); no instance was created. Anvil implements no instance extensions, including the surface extensions, so there is no presentation path through this API yet.")
  EndIf
  ProcedureReturn AnvilVkInstanceCreate(*pInstance)
EndProcedure

Procedure vkDestroyInstance(instance.i, *pAllocator)
  If avkNoAllocator(*pAllocator, 2) <> #VK_SUCCESS
    ProcedureReturn
  EndIf
  If instance = #VK_NULL_HANDLE
    ProcedureReturn
  EndIf
  If AnvilVkInstanceDestroy(instance) <> #VK_SUCCESS
    avkFault(#ANVIL_VK_ERR_HANDLE, "vkDestroyInstance was given a VkInstance handle that is not live (Anvil code -20002, stale or foreign handle); nothing was destroyed. Check for a double destroy.")
  EndIf
EndProcedure

Procedure.i vkEnumeratePhysicalDevices(instance.i, *pPhysicalDeviceCount, *pPhysicalDevices)
  ProcedureReturn AnvilVkPhysicalEnumerate(instance, *pPhysicalDeviceCount, *pPhysicalDevices)
EndProcedure

Procedure vkGetPhysicalDeviceMemoryProperties(physicalDevice.i, *pMemoryProperties.VkPhysicalDeviceMemoryProperties)
  Define i.i
  Define n.i
  Define h.i
  If *pMemoryProperties = 0
    ProcedureReturn
  EndIf
  If avkPhysSlot(physicalDevice) = 0
    avkFault(#ANVIL_VK_ERR_HANDLE, "vkGetPhysicalDeviceMemoryProperties was given a VkPhysicalDevice handle that is not live (Anvil code -20002, stale or foreign handle); the structure was left untouched, so do not read it.")
    ProcedureReturn
  EndIf
  n = avkBackendMemoryTypeCount()
  If n > #VK_MAX_MEMORY_TYPES : n = #VK_MAX_MEMORY_TYPES : EndIf
  *pMemoryProperties\memoryTypeCount = n
  i = 0
  While i < n
    *pMemoryProperties\memoryTypes[i]\propertyFlags = avkBackendMemoryTypeFlags(i)
    *pMemoryProperties\memoryTypes[i]\heapIndex = avkBackendMemoryTypeHeap(i)
    i = i + 1
  Wend
  h = avkBackendHeapCount()
  If h > #VK_MAX_MEMORY_HEAPS : h = #VK_MAX_MEMORY_HEAPS : EndIf
  *pMemoryProperties\memoryHeapCount = h
  i = 0
  While i < h
    *pMemoryProperties\memoryHeaps[i]\size = avkBackendHeapSizeOf(i)
    *pMemoryProperties\memoryHeaps[i]\flags = avkBackendHeapFlagsOf(i)
    i = i + 1
  Wend
EndProcedure

; One queue family, transfer only. Saying GRAPHICS here would be a claim
; about draws, and saying COMPUTE a claim about dispatches; neither
; exists, and a caller that filters families on those bits must find
; none rather than be handed a queue that cannot do the work.
Procedure vkGetPhysicalDeviceQueueFamilyProperties(physicalDevice.i, *pQueueFamilyPropertyCount, *pQueueFamilyProperties.VkQueueFamilyProperties)
  If *pQueueFamilyPropertyCount = 0
    ProcedureReturn
  EndIf
  If avkPhysSlot(physicalDevice) = 0
    avkFault(#ANVIL_VK_ERR_HANDLE, "vkGetPhysicalDeviceQueueFamilyProperties was given a VkPhysicalDevice handle that is not live (Anvil code -20002, stale or foreign handle); nothing was written, so do not read the count.")
    ProcedureReturn
  EndIf
  If *pQueueFamilyProperties = 0
    PokeL(*pQueueFamilyPropertyCount, 1)
    ProcedureReturn
  EndIf
  If PeekL(*pQueueFamilyPropertyCount) < 1
    PokeL(*pQueueFamilyPropertyCount, 0)
    ProcedureReturn
  EndIf
  *pQueueFamilyProperties\queueFlags = #VK_QUEUE_TRANSFER_BIT
  *pQueueFamilyProperties\queueCount = 1
  *pQueueFamilyProperties\timestampValidBits = 0
  *pQueueFamilyProperties\minImageTransferGranularity\width = 1
  *pQueueFamilyProperties\minImageTransferGranularity\height = 1
  *pQueueFamilyProperties\minImageTransferGranularity\depth = 1
  PokeL(*pQueueFamilyPropertyCount, 1)
EndProcedure

Procedure.i vkCreateDevice(physicalDevice.i, *pCreateInfo.VkDeviceCreateInfo, *pAllocator, *pDevice)
  Define rc.i
  Define *qi.VkDeviceQueueCreateInfo
  If *pCreateInfo = 0 Or *pDevice = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  rc = avkNoAllocator(*pAllocator, 3)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  If *pCreateInfo\sType <> #VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateDevice was given a VkDeviceCreateInfo whose sType is not VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO (Anvil code -20001, wrong sType); set sType before filling the rest of the structure.")
  EndIf
  rc = avkNoPNext(*pCreateInfo\pNext)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  If *pCreateInfo\flags <> 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  If *pCreateInfo\enabledExtensionCount <> 0
    ProcedureReturn avkFault(#VK_ERROR_EXTENSION_NOT_PRESENT, "vkCreateDevice was asked to enable a device extension (VkResult -7, VK_ERROR_EXTENSION_NOT_PRESENT); no device was created. Anvil implements no device extensions, so VK_KHR_swapchain in particular is not available.")
  EndIf
  If *pCreateInfo\pEnabledFeatures <> 0
    ProcedureReturn avkFault(#VK_ERROR_FEATURE_NOT_PRESENT, "vkCreateDevice was asked to enable device features (VkResult -8, VK_ERROR_FEATURE_NOT_PRESENT); no device was created. Every VkPhysicalDeviceFeatures member is false on this device, so pEnabledFeatures must be null or all-false; pass null.")
  EndIf
  If *pCreateInfo\queueCreateInfoCount <> 1 Or *pCreateInfo\pQueueCreateInfos = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateDevice was asked for a number of queue families this device does not have (Anvil code -20001, invalid queue request); there is exactly one queue family, so queueCreateInfoCount must be one.")
  EndIf
  *qi = *pCreateInfo\pQueueCreateInfos
  If *qi\sType <> #VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateDevice was given a VkDeviceQueueCreateInfo whose sType is wrong (Anvil code -20001, wrong sType); it must be VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO.")
  EndIf
  rc = avkNoPNext(*qi\pNext)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  If *qi\flags <> 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  If *qi\queueFamilyIndex <> #ANVIL_VK_QUEUE_FAMILY Or *qi\queueCount <> 1
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateDevice was asked for a queue family or queue count this device does not have (Anvil code -20001, invalid queue request); family 0 exposes exactly one queue, as vkGetPhysicalDeviceQueueFamilyProperties reports.")
  EndIf
  If *qi\pQueuePriorities = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  ProcedureReturn AnvilVkDeviceCreate(physicalDevice, *pDevice)
EndProcedure

Procedure vkDestroyDevice(device.i, *pAllocator)
  If avkNoAllocator(*pAllocator, 4) <> #VK_SUCCESS
    ProcedureReturn
  EndIf
  If device = #VK_NULL_HANDLE
    ProcedureReturn
  EndIf
  AnvilVkDeviceDestroy(device)
EndProcedure

Procedure vkGetDeviceQueue(device.i, queueFamilyIndex.i, queueIndex.i, *pQueue)
  If *pQueue = 0
    ProcedureReturn
  EndIf
  PokeI(*pQueue, #VK_NULL_HANDLE)
  If queueFamilyIndex <> #ANVIL_VK_QUEUE_FAMILY Or queueIndex <> 0
    avkFault(#ANVIL_VK_ERR_ARGS, "vkGetDeviceQueue was asked for a queue this device does not have (Anvil code -20001, no such queue); family 0 index 0 is the only queue, and the handle was left null rather than filled with something that does not exist.")
    ProcedureReturn
  EndIf
  If AnvilVkDeviceQueue(device, *pQueue) <> #VK_SUCCESS
    avkFault(#ANVIL_VK_ERR_HANDLE, "vkGetDeviceQueue was given a VkDevice handle that is not live (Anvil code -20002, stale or foreign handle); the handle was left null.")
  EndIf
EndProcedure

Procedure.i vkDeviceWaitIdle(device.i)
  ProcedureReturn AnvilVkDeviceWaitIdle(device)
EndProcedure

; ----------------------------------------------------------------------
;  DEVICE MEMORY
; ----------------------------------------------------------------------
Procedure.i vkAllocateMemory(device.i, *pAllocateInfo.VkMemoryAllocateInfo, *pAllocator, *pMemory)
  Define rc.i
  If *pAllocateInfo = 0 Or *pMemory = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  rc = avkNoAllocator(*pAllocator, 5)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  If *pAllocateInfo\sType <> #VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkAllocateMemory was given a VkMemoryAllocateInfo whose sType is not VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO (Anvil code -20001, wrong sType); set sType before filling the rest of the structure.")
  EndIf
  rc = avkNoPNext(*pAllocateInfo\pNext)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  ProcedureReturn AnvilVkMemoryAllocate(device, *pAllocateInfo\allocationSize, *pAllocateInfo\memoryTypeIndex, *pMemory)
EndProcedure

Procedure vkFreeMemory(device.i, memory.i, *pAllocator)
  If avkNoAllocator(*pAllocator, 6) <> #VK_SUCCESS
    ProcedureReturn
  EndIf
  AnvilVkMemoryFree(device, memory)
EndProcedure

; ----------------------------------------------------------------------
;  IMAGES
; ----------------------------------------------------------------------
Procedure.i vkCreateImage(device.i, *pCreateInfo.VkImageCreateInfo, *pAllocator, *pImage)
  Define rc.i
  If *pCreateInfo = 0 Or *pImage = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  rc = avkNoAllocator(*pAllocator, 7)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  If *pCreateInfo\sType <> #VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateImage was given a VkImageCreateInfo whose sType is not VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO (Anvil code -20001, wrong sType); set sType before filling the rest of the structure.")
  EndIf
  rc = avkNoPNext(*pCreateInfo\pNext)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  If *pCreateInfo\flags <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateImage was given VkImageCreateFlags (Anvil code -20005, unsupported image creation flags); sparse binding, aliasing, cube-compatible and mutable-format images are all unimplemented, so flags must be zero.")
  EndIf
  If *pCreateInfo\imageType <> #VK_IMAGE_TYPE_2D
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateImage was asked for an image type other than VK_IMAGE_TYPE_2D (Anvil code -20005, unsupported image type); only two-dimensional images exist in this implementation.")
  EndIf
  If *pCreateInfo\extent\depth <> 1
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateImage was given a two-dimensional image whose extent depth is not one (Anvil code -20001, invalid extent); VK_IMAGE_TYPE_2D requires extent.depth to be exactly 1.")
  EndIf
  If *pCreateInfo\mipLevels <> 1 Or *pCreateInfo\arrayLayers <> 1
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateImage was asked for more than one mip level or array layer (Anvil code -20005, unsupported image shape); this implementation creates single-level, single-layer images only, because there is no mip generation and no layered rendering.")
  EndIf
  If *pCreateInfo\samples <> #VK_SAMPLE_COUNT_1_BIT
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateImage was asked for a multisampled image (Anvil code -20005, unsupported sample count); only VK_SAMPLE_COUNT_1_BIT is implemented, and the device reports no other sample counts in its limits. Create the image with VK_SAMPLE_COUNT_1_BIT.")
  EndIf
  If *pCreateInfo\sharingMode <> #VK_SHARING_MODE_EXCLUSIVE
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateImage was asked for VK_SHARING_MODE_CONCURRENT (Anvil code -20005, unsupported sharing mode); this device has one queue family, so an image can only ever be exclusive to it.")
  EndIf
  ProcedureReturn AnvilVkImageCreate(device, *pCreateInfo\extent\width, *pCreateInfo\extent\height, *pCreateInfo\format, *pCreateInfo\tiling, *pCreateInfo\usage, *pCreateInfo\initialLayout, *pImage)
EndProcedure

Procedure vkGetImageMemoryRequirements(device.i, image.i, *pMemoryRequirements.VkMemoryRequirements)
  If *pMemoryRequirements = 0
    ProcedureReturn
  EndIf
  If avkDevSlot(device) = 0 Or avkImgSlot(image) = 0
    avkFault(#ANVIL_VK_ERR_HANDLE, "vkGetImageMemoryRequirements was given a device or image handle that is not live (Anvil code -20002, stale or foreign handle); the requirements structure was left untouched, so do not allocate from it.")
    ProcedureReturn
  EndIf
  *pMemoryRequirements\size = AnvilVkImageSize(image)
  *pMemoryRequirements\alignment = AnvilVkImageAlignment(image)
  *pMemoryRequirements\memoryTypeBits = avkImageMemoryTypeBits()
EndProcedure

Procedure.i vkBindImageMemory(device.i, image.i, memory.i, memoryOffset.i)
  ProcedureReturn AnvilVkImageBindMemory(device, image, memory, memoryOffset)
EndProcedure

Procedure vkDestroyImage(device.i, image.i, *pAllocator)
  If avkNoAllocator(*pAllocator, 8) <> #VK_SUCCESS
    ProcedureReturn
  EndIf
  AnvilVkImageDestroy(device, image)
EndProcedure

; ----------------------------------------------------------------------
;  COMMAND POOLS AND COMMAND BUFFERS
; ----------------------------------------------------------------------
Procedure.i vkCreateCommandPool(device.i, *pCreateInfo.VkCommandPoolCreateInfo, *pAllocator, *pCommandPool)
  Define rc.i
  If *pCreateInfo = 0 Or *pCommandPool = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  rc = avkNoAllocator(*pAllocator, 9)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  If *pCreateInfo\sType <> #VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateCommandPool was given a VkCommandPoolCreateInfo whose sType is wrong (Anvil code -20001, wrong sType); it must be VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO.")
  EndIf
  rc = avkNoPNext(*pCreateInfo\pNext)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  If *pCreateInfo\queueFamilyIndex <> #ANVIL_VK_QUEUE_FAMILY
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateCommandPool named a queue family this device does not have (Anvil code -20001, no such queue family); family 0 is the only one.")
  EndIf
  ProcedureReturn AnvilVkCommandPoolCreate(device, *pCreateInfo\flags, *pCommandPool)
EndProcedure

Procedure vkDestroyCommandPool(device.i, commandPool.i, *pAllocator)
  If avkNoAllocator(*pAllocator, 10) <> #VK_SUCCESS
    ProcedureReturn
  EndIf
  If commandPool = #VK_NULL_HANDLE
    ProcedureReturn
  EndIf
  AnvilVkCommandPoolDestroy(device, commandPool)
EndProcedure

Procedure.i vkResetCommandPool(device.i, commandPool.i, flags.i)
  ProcedureReturn AnvilVkCommandPoolReset(device, commandPool, flags)
EndProcedure

Procedure.i vkAllocateCommandBuffers(device.i, *pAllocateInfo.VkCommandBufferAllocateInfo, *pCommandBuffers)
  Define rc.i
  If *pAllocateInfo = 0 Or *pCommandBuffers = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  If *pAllocateInfo\sType <> #VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkAllocateCommandBuffers was given a VkCommandBufferAllocateInfo whose sType is wrong (Anvil code -20001, wrong sType); it must be VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO.")
  EndIf
  rc = avkNoPNext(*pAllocateInfo\pNext)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  If *pAllocateInfo\commandBufferCount <> 1
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkAllocateCommandBuffers was asked for more than one command buffer in a single call (Anvil code -20005, array allocation not implemented); allocate them one at a time, because a partially satisfied array allocation has no defined unwind here yet.")
  EndIf
  ProcedureReturn AnvilVkCommandBufferAllocate(device, *pAllocateInfo\commandPool, *pAllocateInfo\level, *pCommandBuffers)
EndProcedure

Procedure vkFreeCommandBuffers(device.i, commandPool.i, commandBufferCount.i, *pCommandBuffers)
  Define rc.i
  If *pCommandBuffers = 0 Or commandBufferCount <> 1
    avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkFreeCommandBuffers was asked to free a number of command buffers other than one (Anvil code -20005, array free not implemented); nothing was freed. Free them one at a time.")
    ProcedureReturn
  EndIf
  rc = AnvilVkCommandBufferFree(device, commandPool, PeekI(*pCommandBuffers))
  If rc <> #VK_SUCCESS And rc <> #ANVIL_VK_ERR_STATE
    avkFault(rc, "vkFreeCommandBuffers was given a device, pool or command buffer handle that do not belong together (Anvil code in the fault record); nothing was freed. Free a command buffer through the pool it was allocated from.")
  EndIf
EndProcedure

Procedure.i vkBeginCommandBuffer(commandBuffer.i, *pBeginInfo.VkCommandBufferBeginInfo)
  Define rc.i
  If *pBeginInfo = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  If *pBeginInfo\sType <> #VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkBeginCommandBuffer was given a VkCommandBufferBeginInfo whose sType is wrong (Anvil code -20001, wrong sType); it must be VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO.")
  EndIf
  rc = avkNoPNext(*pBeginInfo\pNext)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  If *pBeginInfo\pInheritanceInfo <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkBeginCommandBuffer was given inheritance information (Anvil code -20005, secondary command buffers are not executable); there is no render pass and no vkCmdExecuteCommands, so a secondary buffer cannot inherit anything.")
  EndIf
  ProcedureReturn AnvilVkCommandBufferBegin(commandBuffer, *pBeginInfo\flags)
EndProcedure

Procedure.i vkEndCommandBuffer(commandBuffer.i)
  ProcedureReturn AnvilVkCommandBufferEnd(commandBuffer)
EndProcedure

Procedure.i vkResetCommandBuffer(commandBuffer.i, flags.i)
  ProcedureReturn AnvilVkCommandBufferReset(commandBuffer, flags)
EndProcedure

; ----------------------------------------------------------------------
;  RECORDED COMMANDS
;
;  THE ONE COMMAND THAT CANNOT CARRY ITS REGISTRY SIGNATURE HERE.
;  vkCmdPipelineBarrier takes ten parameters. The PureMetal AArch64
;  backend passes at most eight, in a0 through a7, and refuses a ninth
;  at compile time - stack arguments are not emitted yet. So the nine
;  arguments after the command buffer travel in ONE record, in the
;  registry's own order and with the registry's own member names and
;  widths, and the entry point is named vkCmdPipelineBarrierArgs so no
;  reader can mistake it for the real prototype.
;
;  This is a toolchain limitation, not a design choice, and it is in the
;  capability table with the exact backend change that removes it. Every
;  other command in this file has its registry signature exactly; only
;  this one does not fit in eight registers.
; ----------------------------------------------------------------------
Structure AnvilVkPipelineBarrierArgs Align #PB_Structure_AlignC
  srcStageMask.l
  dstStageMask.l
  dependencyFlags.l
  memoryBarrierCount.l
  *pMemoryBarriers
  bufferMemoryBarrierCount.l
  *pBufferMemoryBarriers
  imageMemoryBarrierCount.l
  *pImageMemoryBarriers
EndStructure

Procedure vkCmdPipelineBarrierArgs(commandBuffer.i, *a.AnvilVkPipelineBarrierArgs)
  Define c.i
  Define srcStageMask.i
  Define dstStageMask.i
  Define dependencyFlags.i
  Define memoryBarrierCount.i
  Define bufferMemoryBarrierCount.i
  Define imageMemoryBarrierCount.i
  Define *pImageMemoryBarriers.VkImageMemoryBarrier
  If *a = 0
    avkFault(#ANVIL_VK_ERR_ARGS, "vkCmdPipelineBarrierArgs was given a null argument record (Anvil code -20001, invalid argument); nothing was recorded.")
    ProcedureReturn
  EndIf
  srcStageMask = *a\srcStageMask & $FFFFFFFF
  dstStageMask = *a\dstStageMask & $FFFFFFFF
  dependencyFlags = *a\dependencyFlags & $FFFFFFFF
  memoryBarrierCount = *a\memoryBarrierCount & $FFFFFFFF
  bufferMemoryBarrierCount = *a\bufferMemoryBarrierCount & $FFFFFFFF
  imageMemoryBarrierCount = *a\imageMemoryBarrierCount & $FFFFFFFF
  *pImageMemoryBarriers = *a\pImageMemoryBarriers
  c = avkCmdSlot(commandBuffer)
  If c = 0
    avkFault(#ANVIL_VK_ERR_HANDLE, "vkCmdPipelineBarrier was given a VkCommandBuffer handle that is not live (Anvil code -20002, stale or foreign handle); nothing was recorded.")
    ProcedureReturn
  EndIf
  If (dependencyFlags & (~#VK_DEPENDENCY_BY_REGION_BIT)) <> 0
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdPipelineBarrier was given a dependency flag that core Vulkan 1.0 does not define (Anvil code -20001, invalid argument); the only bit is VK_DEPENDENCY_BY_REGION_BIT.")
    ProcedureReturn
  EndIf
  If memoryBarrierCount <> 0 Or bufferMemoryBarrierCount <> 0
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdPipelineBarrier was given a global memory barrier or a buffer memory barrier (Anvil code -20005, unsupported barrier kind); only image memory barriers are implemented, because there are no VkBuffer objects yet.")
    ProcedureReturn
  EndIf
  If imageMemoryBarrierCount = 0
    ProcedureReturn
  EndIf
  If imageMemoryBarrierCount <> 1 Or *pImageMemoryBarriers = 0
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdPipelineBarrier was given more than one image memory barrier in a single call (Anvil code -20005, barrier arrays not implemented); record them one at a time, because executing only the first would be a silently different dependency.")
    ProcedureReturn
  EndIf
  If *pImageMemoryBarriers\sType <> #VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdPipelineBarrier was given a VkImageMemoryBarrier whose sType is wrong (Anvil code -20001, wrong sType); it must be VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER.")
    ProcedureReturn
  EndIf
  If *pImageMemoryBarriers\pNext <> 0
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdPipelineBarrier was given an image memory barrier with a pNext chain (Anvil code -20005, no pNext extension is implemented); nothing was recorded, because an ignored extension structure is a silently different dependency.")
    ProcedureReturn
  EndIf
  AnvilVkCmdImageBarrier(commandBuffer, srcStageMask, dstStageMask, *pImageMemoryBarriers)
EndProcedure

; pColor is a VkClearColorValue. Its float32 arm is read here, because
; the only format this implementation creates is a UNORM one and the
; specification says a UNORM image is cleared from float32. The four
; components are in R, G, B, A order whatever the format's byte order is.
Procedure vkCmdClearColorImage(commandBuffer.i, image.i, imageLayout.i, *pColor, rangeCount.i, *pRanges.VkImageSubresourceRange)
  Define c.i
  c = avkCmdSlot(commandBuffer)
  If c = 0
    avkFault(#ANVIL_VK_ERR_HANDLE, "vkCmdClearColorImage was given a VkCommandBuffer handle that is not live (Anvil code -20002, stale or foreign handle); nothing was recorded.")
    ProcedureReturn
  EndIf
  If *pColor = 0
    avkCbFail(c, #ANVIL_VK_ERR_ARGS, "vkCmdClearColorImage was given a null pColor (Anvil code -20001, invalid argument); a clear needs a VkClearColorValue to clear to.")
    ProcedureReturn
  EndIf
  If rangeCount <> 1 Or *pRanges = 0
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdClearColorImage was given a number of subresource ranges other than one (Anvil code -20005, multi-range clears not implemented); clearing only the first range would leave the rest silently untouched, so the whole command is refused.")
    ProcedureReturn
  EndIf
  AnvilVkCmdClearColorImage(commandBuffer, image, imageLayout, *pColor, *pRanges)
EndProcedure

; ----------------------------------------------------------------------
;  FENCES AND SUBMISSION
; ----------------------------------------------------------------------
Procedure.i vkCreateFence(device.i, *pCreateInfo.VkFenceCreateInfo, *pAllocator, *pFence)
  Define rc.i
  If *pCreateInfo = 0 Or *pFence = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  rc = avkNoAllocator(*pAllocator, 11)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  If *pCreateInfo\sType <> #VK_STRUCTURE_TYPE_FENCE_CREATE_INFO
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateFence was given a VkFenceCreateInfo whose sType is wrong (Anvil code -20001, wrong sType); it must be VK_STRUCTURE_TYPE_FENCE_CREATE_INFO.")
  EndIf
  rc = avkNoPNext(*pCreateInfo\pNext)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  ProcedureReturn AnvilVkFenceCreate(device, *pCreateInfo\flags, *pFence)
EndProcedure

Procedure vkDestroyFence(device.i, fence.i, *pAllocator)
  If avkNoAllocator(*pAllocator, 12) <> #VK_SUCCESS
    ProcedureReturn
  EndIf
  AnvilVkFenceDestroy(device, fence)
EndProcedure

Procedure.i vkResetFences(device.i, fenceCount.i, *pFences)
  ProcedureReturn AnvilVkFencesReset(device, fenceCount, *pFences)
EndProcedure

Procedure.i vkGetFenceStatus(device.i, fence.i)
  ; Give the device a chance to report completion first: a caller that
  ; only ever polls must still be able to see a finished submission.
  avkFlightPoll()
  ProcedureReturn AnvilVkFenceStatus(device, fence)
EndProcedure

Procedure.i vkWaitForFences(device.i, fenceCount.i, *pFences, waitAll.i, timeout.i)
  ProcedureReturn AnvilVkWaitForFences(device, fenceCount, *pFences, waitAll, timeout)
EndProcedure

Procedure.i vkQueueSubmit(queue.i, submitCount.i, *pSubmits.VkSubmitInfo, fence.i)
  If submitCount = 0
    ProcedureReturn AnvilVkQueueSubmitOne(queue, #VK_NULL_HANDLE, fence)
  EndIf
  If *pSubmits = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  If submitCount <> 1
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkQueueSubmit was given more than one VkSubmitInfo in a single call (Anvil code -20005, batched submission not implemented); submit them one at a time, because executing only the first batch would be a silent partial submission.")
  EndIf
  If *pSubmits\sType <> #VK_STRUCTURE_TYPE_SUBMIT_INFO
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkQueueSubmit was given a VkSubmitInfo whose sType is wrong (Anvil code -20001, wrong sType); it must be VK_STRUCTURE_TYPE_SUBMIT_INFO.")
  EndIf
  If *pSubmits\pNext <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkQueueSubmit was given a VkSubmitInfo with a pNext chain (Anvil code -20005, no pNext extension is implemented); nothing was submitted.")
  EndIf
  If *pSubmits\waitSemaphoreCount <> 0 Or *pSubmits\signalSemaphoreCount <> 0
    ProcedureReturn avkFault(#VK_ERROR_FEATURE_NOT_PRESENT, "vkQueueSubmit was given semaphores to wait on or signal (VkResult -8, VK_ERROR_FEATURE_NOT_PRESENT); nothing was submitted. Semaphores are not implemented - there is one queue and one outstanding submission, so use the submission's fence to order work against the host.")
  EndIf
  If *pSubmits\commandBufferCount = 0
    ProcedureReturn AnvilVkQueueSubmitOne(queue, #VK_NULL_HANDLE, fence)
  EndIf
  If *pSubmits\commandBufferCount <> 1 Or *pSubmits\pCommandBuffers = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkQueueSubmit was given more than one command buffer in a VkSubmitInfo (Anvil code -20005, multi-buffer submission not implemented); submit them one at a time, because executing only the first would be a silent partial submission.")
  EndIf
  ProcedureReturn AnvilVkQueueSubmitOne(queue, PeekI(*pSubmits\pCommandBuffers), fence)
EndProcedure

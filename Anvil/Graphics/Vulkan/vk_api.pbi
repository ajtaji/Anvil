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

XIncludeFile "Anvil/Graphics/Vulkan/vk_pipeline.pbi"

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

; Report only format behavior the implementation owns. Linear BGRA8 becomes a
; colour attachment only when the backend owns drawing. Optimal BGRA8 is a
; sampled image only when the backend owns both its layout plan and transfer.
Procedure vkGetPhysicalDeviceFormatProperties(physicalDevice.i, format.i, *pFormatProperties.VkFormatProperties)
  If *pFormatProperties = 0
    ProcedureReturn
  EndIf
  If avkPhysSlot(physicalDevice) = 0
    avkFault(#ANVIL_VK_ERR_HANDLE, "vkGetPhysicalDeviceFormatProperties was given a VkPhysicalDevice handle that is not live (Anvil code -20002, stale or foreign handle); the structure was left untouched, so do not read it.")
    ProcedureReturn
  EndIf
  *pFormatProperties\linearTilingFeatures = 0
  *pFormatProperties\optimalTilingFeatures = 0
  *pFormatProperties\bufferFeatures = 0
  If format = #VK_FORMAT_B8G8R8A8_UNORM
    If avkBackendSampledMaxDimension2D(#VK_IMAGE_TILING_LINEAR) > 0
      *pFormatProperties\linearTilingFeatures = #VK_FORMAT_FEATURE_SAMPLED_IMAGE_BIT
    EndIf
    If avkBackendSampledMaxDimension2D(#VK_IMAGE_TILING_OPTIMAL) > 0
      *pFormatProperties\optimalTilingFeatures = #VK_FORMAT_FEATURE_SAMPLED_IMAGE_BIT
    EndIf
    If AnvilVkBackendCanDraw() <> 0
      *pFormatProperties\linearTilingFeatures = *pFormatProperties\linearTilingFeatures | #VK_FORMAT_FEATURE_COLOR_ATTACHMENT_BIT
    EndIf
  EndIf
EndProcedure

; Exact core-1.0 query for the bounded VkImageCreateInfo family this
; implementation can create. Every maximum comes from the same backend geometry/row-pitch
; owners used by creation and submission; unsupported combinations return the
; registry's VK_ERROR_FORMAT_NOT_SUPPORTED and publish no invented capability.
Procedure.i vkGetPhysicalDeviceImageFormatProperties(physicalDevice.i, format.i, imageType.i, tiling.i, usage.i, flags.i, *pImageFormatProperties.VkImageFormatProperties)
  Define rc.i
  Define limit.i
  Define bytes.i
  Define plan.AnvilVkBackendImagePlan
  If *pImageFormatProperties = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  If avkPhysSlot(physicalDevice) = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_HANDLE, "vkGetPhysicalDeviceImageFormatProperties was given a VkPhysicalDevice handle that is not live (Anvil code -20002, stale or foreign handle); the properties structure was left untouched, so do not read it.")
  EndIf

  *pImageFormatProperties\maxExtent\width = 0
  *pImageFormatProperties\maxExtent\height = 0
  *pImageFormatProperties\maxExtent\depth = 0
  *pImageFormatProperties\maxMipLevels = 0
  *pImageFormatProperties\maxArrayLayers = 0
  *pImageFormatProperties\sampleCounts = 0
  *pImageFormatProperties\maxResourceSize = 0

  rc = AnvilVkImageFormatSupport(format, imageType, tiling, usage, flags)
  If rc <> #VK_SUCCESS : ProcedureReturn #VK_ERROR_FORMAT_NOT_SUPPORTED : EndIf
  limit = avkBackendMaxImageDimension2D()
  If (usage & #VK_IMAGE_USAGE_SAMPLED_BIT) <> 0 And avkBackendSampledMaxDimension2D(tiling) < limit
    limit = avkBackendSampledMaxDimension2D(tiling)
  EndIf
  If avkBackendImagePlan(limit, limit, format, tiling, usage, @plan) <> #VK_SUCCESS
    ProcedureReturn #VK_ERROR_FORMAT_NOT_SUPPORTED
  EndIf
  bytes = plan\bytes
  If limit < 1 Or bytes < 1 : ProcedureReturn #VK_ERROR_FORMAT_NOT_SUPPORTED : EndIf
  *pImageFormatProperties\maxExtent\width = limit
  *pImageFormatProperties\maxExtent\height = limit
  *pImageFormatProperties\maxExtent\depth = 1
  *pImageFormatProperties\maxMipLevels = 1
  *pImageFormatProperties\maxArrayLayers = 1
  *pImageFormatProperties\sampleCounts = #VK_SAMPLE_COUNT_1_BIT
  *pImageFormatProperties\maxResourceSize = bytes
  ProcedureReturn #VK_SUCCESS
EndProcedure

; One queue family. Transfer is implemented by every live backend.
; Graphics is advertised only when this particular backend can execute
; the draw record; compute remains absent because dispatch does not yet
; exist. Keeping this derived from the backend capability means a
; transfer-only target is not handed a queue it cannot use for drawing.
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
  If (avkBackendCaps() & #ANVIL_VK_CAP_DRAW) <> 0
    *pQueueFamilyProperties\queueFlags = *pQueueFamilyProperties\queueFlags | #VK_QUEUE_GRAPHICS_BIT
  EndIf
  *pQueueFamilyProperties\queueCount = 1
  *pQueueFamilyProperties\timestampValidBits = 0
  *pQueueFamilyProperties\minImageTransferGranularity\width = 1
  *pQueueFamilyProperties\minImageTransferGranularity\height = 1
  *pQueueFamilyProperties\minImageTransferGranularity\depth = 1
  PokeL(*pQueueFamilyPropertyCount, 1)
EndProcedure

; The structure is part of the core query contract even though this
; deliberately small device exposes no optional feature bit yet.
Procedure vkGetPhysicalDeviceFeatures(physicalDevice.i, *pFeatures.VkPhysicalDeviceFeatures)
  Define i.i
  If *pFeatures = 0
    ProcedureReturn
  EndIf
  If avkPhysSlot(physicalDevice) = 0
    avkFault(#ANVIL_VK_ERR_HANDLE, "vkGetPhysicalDeviceFeatures was given a VkPhysicalDevice handle that is not live (Anvil code -20002, stale or foreign handle); the structure was left untouched, so do not read it.")
    ProcedureReturn
  EndIf
  i = 0
  While i < SizeOf(VkPhysicalDeviceFeatures)
    PokeL(*pFeatures + i, #VK_FALSE)
    i = i + SizeOf(.l)
  Wend
EndProcedure

Procedure.i avkFeaturesAllFalse(*pFeatures.VkPhysicalDeviceFeatures)
  Define i.i
  If *pFeatures = 0 : ProcedureReturn 1 : EndIf
  i = 0
  While i < SizeOf(VkPhysicalDeviceFeatures)
    If PeekL(*pFeatures + i) <> #VK_FALSE : ProcedureReturn 0 : EndIf
    i = i + SizeOf(.l)
  Wend
  ProcedureReturn 1
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
  If avkFeaturesAllFalse(*pCreateInfo\pEnabledFeatures) = 0
    ProcedureReturn avkFault(#VK_ERROR_FEATURE_NOT_PRESENT, "vkCreateDevice was asked to enable a VkPhysicalDeviceFeatures bit this device reports false (VkResult -8, VK_ERROR_FEATURE_NOT_PRESENT); no device was created. Query vkGetPhysicalDeviceFeatures and leave every unsupported member false.")
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

Procedure.i vkMapMemory(device.i, memory.i, offset.i, size.i, flags.i, *ppData)
  ProcedureReturn AnvilVkMemoryMap(device, memory, offset, size, flags, *ppData)
EndProcedure

Procedure vkUnmapMemory(device.i, memory.i)
  AnvilVkMemoryUnmap(device, memory)
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
;  This is the exact Vulkan 1.0 registry signature. The AArch64 ABI puts
;  the first eight arguments in x0..x7 and the final two in the caller's
;  stack argument area. The compiler has owned that split since
;  a9f412a6; keeping the former argument-record surrogate here would now
;  make this API needlessly source-incompatible with Vulkan.
; ----------------------------------------------------------------------
Procedure vkCmdPipelineBarrier(commandBuffer.i, srcStageMask.i, dstStageMask.i, dependencyFlags.i, memoryBarrierCount.i, *pMemoryBarriers, bufferMemoryBarrierCount.i, *pBufferMemoryBarriers, imageMemoryBarrierCount.i, *pImageMemoryBarriers.VkImageMemoryBarrier)
  Define c.i
  srcStageMask = srcStageMask & $FFFFFFFF
  dstStageMask = dstStageMask & $FFFFFFFF
  dependencyFlags = dependencyFlags & $FFFFFFFF
  memoryBarrierCount = memoryBarrierCount & $FFFFFFFF
  bufferMemoryBarrierCount = bufferMemoryBarrierCount & $FFFFFFFF
  imageMemoryBarrierCount = imageMemoryBarrierCount & $FFFFFFFF
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
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdPipelineBarrier was given a global memory barrier or a buffer memory barrier (Anvil code -20005, unsupported barrier kind); only image memory barriers are implemented in this slice, so record image barriers only.")
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

; Exact core Vulkan 1.0 signature. The first executable tranche accepts one
; whole, tightly packed region; refusing an array is safer than executing its
; first member and silently leaving the rest uncopied.
Procedure vkCmdCopyBufferToImage(commandBuffer.i, srcBuffer.i, dstImage.i, dstImageLayout.i, regionCount.i, *pRegions.VkBufferImageCopy)
  Define c.i
  c = avkCmdSlot(commandBuffer)
  If c = 0
    avkFault(#ANVIL_VK_ERR_HANDLE, "vkCmdCopyBufferToImage was given a VkCommandBuffer handle that is not live (Anvil code -20002, stale or foreign handle); nothing was recorded.")
    ProcedureReturn
  EndIf
  If regionCount <> 1 Or *pRegions = 0
    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, "vkCmdCopyBufferToImage was given other than one copy region (Anvil code -20005, region arrays not implemented); nothing was recorded because a partial array copy would be a false success.")
    ProcedureReturn
  EndIf
  AnvilVkCmdCopyBufferToImage(commandBuffer, srcBuffer, dstImage, dstImageLayout, *pRegions)
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

; ----------------------------------------------------------------------
;  BUFFERS
; ----------------------------------------------------------------------
Procedure.i vkCreateBuffer(device.i, *pCreateInfo.VkBufferCreateInfo, *pAllocator, *pBuffer)
  Define rc.i
  If *pCreateInfo = 0 Or *pBuffer = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  rc = avkNoAllocator(*pAllocator, 0)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  If *pCreateInfo\sType <> #VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateBuffer was given a VkBufferCreateInfo whose sType is wrong (Anvil code -20001, wrong sType); it must be VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO.")
  EndIf
  If avkNoPNext(*pCreateInfo\pNext) <> #VK_SUCCESS
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateBuffer was given a VkBufferCreateInfo with a pNext chain (Anvil code -20005, no pNext extension is implemented); no buffer was created.")
  EndIf
  If (*pCreateInfo\flags & $FFFFFFFF) <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateBuffer was given creation flags (Anvil code -20005, unsupported flags); the sparse binding and residency flags are the only ones core 1.0 defines here and none of them is implemented.")
  EndIf
  ProcedureReturn AnvilVkBufferCreate(device, *pCreateInfo\size, *pCreateInfo\usage & $FFFFFFFF, *pCreateInfo\sharingMode & $FFFFFFFF, *pBuffer)
EndProcedure

Procedure vkDestroyBuffer(device.i, buffer.i, *pAllocator)
  If avkNoAllocator(*pAllocator, 0) <> #VK_SUCCESS
    ProcedureReturn
  EndIf
  AnvilVkBufferDestroy(device, buffer)
EndProcedure

Procedure vkGetBufferMemoryRequirements(device.i, buffer.i, *pMemoryRequirements.VkMemoryRequirements)
  If *pMemoryRequirements = 0
    ProcedureReturn
  EndIf
  *pMemoryRequirements\size = AnvilVkBufferSize(buffer)
  *pMemoryRequirements\alignment = AnvilVkBufferAlignment(buffer)
  *pMemoryRequirements\memoryTypeBits = avkImageMemoryTypeBits()
EndProcedure

Procedure.i vkBindBufferMemory(device.i, buffer.i, memory.i, memoryOffset.i)
  ProcedureReturn AnvilVkBufferBindMemory(device, buffer, memory, memoryOffset)
EndProcedure

; ----------------------------------------------------------------------
;  SHADER MODULES
; ----------------------------------------------------------------------
Procedure.i vkCreateShaderModule(device.i, *pCreateInfo.VkShaderModuleCreateInfo, *pAllocator, *pShaderModule)
  Define rc.i
  If *pCreateInfo = 0 Or *pShaderModule = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  rc = avkNoAllocator(*pAllocator, 0)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  If *pCreateInfo\sType <> #VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateShaderModule was given a VkShaderModuleCreateInfo whose sType is wrong (Anvil code -20001, wrong sType); it must be VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO.")
  EndIf
  If avkNoPNext(*pCreateInfo\pNext) <> #VK_SUCCESS
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateShaderModule was given a VkShaderModuleCreateInfo with a pNext chain (Anvil code -20005, no pNext extension is implemented); no shader module was created.")
  EndIf
  If (*pCreateInfo\flags & $FFFFFFFF) <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateShaderModule was given creation flags (Anvil code -20005, unsupported flags); VkShaderModuleCreateFlags is reserved in core 1.0 and must be zero.")
  EndIf
  ProcedureReturn AnvilVkShaderModuleCreate(device, *pCreateInfo\pCode, *pCreateInfo\codeSize, *pShaderModule)
EndProcedure

Procedure vkDestroyShaderModule(device.i, shaderModule.i, *pAllocator)
  If avkNoAllocator(*pAllocator, 0) <> #VK_SUCCESS
    ProcedureReturn
  EndIf
  AnvilVkShaderModuleDestroy(device, shaderModule)
EndProcedure

; ----------------------------------------------------------------------
;  DESCRIPTOR SET LAYOUTS, POOLS AND SETS
; ----------------------------------------------------------------------
Procedure.i vkCreateDescriptorSetLayout(device.i, *pCreateInfo.VkDescriptorSetLayoutCreateInfo, *pAllocator, *pSetLayout)
  Define rc.i
  If *pCreateInfo = 0 Or *pSetLayout = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  rc = avkNoAllocator(*pAllocator, 0)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  ProcedureReturn AnvilVkDescriptorSetLayoutCreate(device, *pCreateInfo, *pSetLayout)
EndProcedure

Procedure vkDestroyDescriptorSetLayout(device.i, descriptorSetLayout.i, *pAllocator)
  If avkNoAllocator(*pAllocator, 0) <> #VK_SUCCESS
    ProcedureReturn
  EndIf
  AnvilVkDescriptorSetLayoutDestroy(device, descriptorSetLayout)
EndProcedure

Procedure.i vkCreateDescriptorPool(device.i, *pCreateInfo.VkDescriptorPoolCreateInfo, *pAllocator, *pDescriptorPool)
  Define rc.i
  If *pCreateInfo = 0 Or *pDescriptorPool = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  rc = avkNoAllocator(*pAllocator, 0)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  ProcedureReturn AnvilVkDescriptorPoolCreate(device, *pCreateInfo, *pDescriptorPool)
EndProcedure

Procedure vkDestroyDescriptorPool(device.i, descriptorPool.i, *pAllocator)
  If avkNoAllocator(*pAllocator, 0) <> #VK_SUCCESS
    ProcedureReturn
  EndIf
  AnvilVkDescriptorPoolDestroy(device, descriptorPool)
EndProcedure

Procedure.i vkCreateSampler(device.i, *pCreateInfo.VkSamplerCreateInfo, *pAllocator, *pSampler)
  Define rc.i
  If *pCreateInfo = 0 Or *pSampler = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  rc = avkNoAllocator(*pAllocator, 0)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  ProcedureReturn AnvilVkSamplerCreate(device, *pCreateInfo, *pSampler)
EndProcedure

Procedure vkDestroySampler(device.i, sampler.i, *pAllocator)
  If avkNoAllocator(*pAllocator, 0) <> #VK_SUCCESS
    ProcedureReturn
  EndIf
  AnvilVkSamplerDestroy(device, sampler)
EndProcedure

Procedure.i vkResetDescriptorPool(device.i, descriptorPool.i, flags.i)
  If flags <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkResetDescriptorPool was given flags (Anvil code -20001, invalid argument); VkDescriptorPoolResetFlags is reserved and must be zero.")
  EndIf
  ProcedureReturn AnvilVkDescriptorPoolReset(device, descriptorPool)
EndProcedure

Procedure.i vkAllocateDescriptorSets(device.i, *pAllocateInfo.VkDescriptorSetAllocateInfo, *pDescriptorSets)
  If *pAllocateInfo = 0 Or *pDescriptorSets = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  ProcedureReturn AnvilVkDescriptorSetsAllocate(device, *pAllocateInfo, *pDescriptorSets)
EndProcedure

; vkFreeDescriptorSets EXISTS AND IT REFUSES, which is not the same as
; not being here: a caller who reaches for it is told that this pool was
; created without VK_DESCRIPTOR_POOL_CREATE_FREE_DESCRIPTOR_SET_BIT and
; what to do instead, rather than failing to link.
Procedure.i vkFreeDescriptorSets(device.i, descriptorPool.i, descriptorSetCount.i, *pDescriptorSets)
  ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkFreeDescriptorSets was called on a pool that was not created with VK_DESCRIPTOR_POOL_CREATE_FREE_DESCRIPTOR_SET_BIT (Anvil code -20005, individual descriptor-set freeing not implemented); no set was freed. That bit is refused at vkCreateDescriptorPool, so every pool here returns its sets together - call vkResetDescriptorPool or vkDestroyDescriptorPool.")
EndProcedure

Procedure vkUpdateDescriptorSets(device.i, descriptorWriteCount.i, *pDescriptorWrites.VkWriteDescriptorSet, descriptorCopyCount.i, *pDescriptorCopies)
  AnvilVkDescriptorSetsUpdate(device, descriptorWriteCount, *pDescriptorWrites, descriptorCopyCount, *pDescriptorCopies)
EndProcedure

Procedure vkCmdBindDescriptorSets(commandBuffer.i, pipelineBindPoint.i, layout.i, firstSet.i, descriptorSetCount.i, *pDescriptorSets, dynamicOffsetCount.i, *pDynamicOffsets)
  If *pDescriptorSets = 0
    avkFault(#ANVIL_VK_ERR_ARGS, "vkCmdBindDescriptorSets was given a null pDescriptorSets (Anvil code -20001, invalid argument); nothing was recorded.")
    ProcedureReturn
  EndIf
  If descriptorSetCount <> 1
    avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCmdBindDescriptorSets was asked to bind other than exactly one descriptor set (Anvil code -20005, unsupported set count); a pipeline layout here declares one set layout, so binding two would leave one of them unread.")
    ProcedureReturn
  EndIf
  If dynamicOffsetCount <> 0 Or *pDynamicOffsets <> 0
    avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCmdBindDescriptorSets was given dynamic offsets (Anvil code -20005, dynamic descriptors not implemented); nothing was recorded.")
    ProcedureReturn
  EndIf
  AnvilVkCmdBindDescriptorSet(commandBuffer, pipelineBindPoint, layout, firstSet, PeekI(*pDescriptorSets), dynamicOffsetCount)
EndProcedure

; ----------------------------------------------------------------------
;  PIPELINE LAYOUT, RENDER PASS, IMAGE VIEW, FRAMEBUFFER
; ----------------------------------------------------------------------
Procedure.i vkCreatePipelineLayout(device.i, *pCreateInfo.VkPipelineLayoutCreateInfo, *pAllocator, *pPipelineLayout)
  Define rc.i
  If *pCreateInfo = 0 Or *pPipelineLayout = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  rc = avkNoAllocator(*pAllocator, 0)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  If *pCreateInfo\sType <> #VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreatePipelineLayout was given a VkPipelineLayoutCreateInfo whose sType is wrong (Anvil code -20001, wrong sType); it must be VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO.")
  EndIf
  If avkNoPNext(*pCreateInfo\pNext) <> #VK_SUCCESS
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreatePipelineLayout was given a VkPipelineLayoutCreateInfo with a pNext chain (Anvil code -20005, no pNext extension is implemented); no layout was created.")
  EndIf
  ProcedureReturn AnvilVkPipelineLayoutCreate(device, *pCreateInfo\setLayoutCount & $FFFFFFFF, *pCreateInfo\pSetLayouts, *pCreateInfo\pushConstantRangeCount & $FFFFFFFF, *pCreateInfo\pPushConstantRanges, *pPipelineLayout)
EndProcedure

Procedure vkDestroyPipelineLayout(device.i, pipelineLayout.i, *pAllocator)
  If avkNoAllocator(*pAllocator, 0) <> #VK_SUCCESS
    ProcedureReturn
  EndIf
  AnvilVkPipelineLayoutDestroy(device, pipelineLayout)
EndProcedure

Procedure.i vkCreateRenderPass(device.i, *pCreateInfo.VkRenderPassCreateInfo, *pAllocator, *pRenderPass)
  Define rc.i
  If *pCreateInfo = 0 Or *pRenderPass = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  rc = avkNoAllocator(*pAllocator, 0)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  If *pCreateInfo\sType <> #VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateRenderPass was given a VkRenderPassCreateInfo whose sType is wrong (Anvil code -20001, wrong sType); it must be VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO.")
  EndIf
  If avkNoPNext(*pCreateInfo\pNext) <> #VK_SUCCESS
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateRenderPass was given a VkRenderPassCreateInfo with a pNext chain (Anvil code -20005, no pNext extension is implemented); no render pass was created.")
  EndIf
  If (*pCreateInfo\attachmentCount & $FFFFFFFF) <> 1 Or *pCreateInfo\pAttachments = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateRenderPass was given other than exactly one attachment (Anvil code -20005, unsupported render pass); this slice renders to one colour attachment and has no depth, no resolve and no second target.")
  EndIf
  If (*pCreateInfo\subpassCount & $FFFFFFFF) <> 1 Or *pCreateInfo\pSubpasses = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateRenderPass was given other than exactly one subpass (Anvil code -20005, unsupported render pass); multiple subpasses need the tile-buffer preservation rules this slice does not implement.")
  EndIf
  If (*pCreateInfo\dependencyCount & $FFFFFFFF) <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateRenderPass was given subpass dependencies (Anvil code -20005, subpass dependencies not implemented); with one subpass and one submission in flight there is nothing for a dependency to order, and honouring one would need a scheduler this implementation does not have.")
  EndIf
  ProcedureReturn AnvilVkRenderPassCreate(device, *pCreateInfo\pAttachments, *pCreateInfo\pSubpasses, *pRenderPass)
EndProcedure

Procedure vkDestroyRenderPass(device.i, renderPass.i, *pAllocator)
  If avkNoAllocator(*pAllocator, 0) <> #VK_SUCCESS
    ProcedureReturn
  EndIf
  AnvilVkRenderPassDestroy(device, renderPass)
EndProcedure

Procedure.i vkCreateImageView(device.i, *pCreateInfo.VkImageViewCreateInfo, *pAllocator, *pView)
  Define rc.i
  If *pCreateInfo = 0 Or *pView = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  rc = avkNoAllocator(*pAllocator, 0)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  If *pCreateInfo\sType <> #VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateImageView was given a VkImageViewCreateInfo whose sType is wrong (Anvil code -20001, wrong sType); it must be VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO.")
  EndIf
  If avkNoPNext(*pCreateInfo\pNext) <> #VK_SUCCESS
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateImageView was given a VkImageViewCreateInfo with a pNext chain (Anvil code -20005, no pNext extension is implemented); no view was created.")
  EndIf
  If (*pCreateInfo\components\r & $FFFFFFFF) <> #VK_COMPONENT_SWIZZLE_IDENTITY Or (*pCreateInfo\components\g & $FFFFFFFF) <> #VK_COMPONENT_SWIZZLE_IDENTITY Or (*pCreateInfo\components\b & $FFFFFFFF) <> #VK_COMPONENT_SWIZZLE_IDENTITY Or (*pCreateInfo\components\a & $FFFFFFFF) <> #VK_COMPONENT_SWIZZLE_IDENTITY
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateImageView was given a component swizzle (Anvil code -20005, unsupported swizzle); the tile store writes the shader's components in the attachment's own order, so a swizzle would be declared and not carried out.")
  EndIf
  If (*pCreateInfo\subresourceRange\aspectMask & $FFFFFFFF) <> #VK_IMAGE_ASPECT_COLOR_BIT
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateImageView was given a subresource aspect other than colour (Anvil code -20001, wrong aspect); a colour view names VK_IMAGE_ASPECT_COLOR_BIT and nothing else.")
  EndIf
  If (*pCreateInfo\subresourceRange\baseMipLevel & $FFFFFFFF) <> 0 Or (*pCreateInfo\subresourceRange\baseArrayLayer & $FFFFFFFF) <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateImageView was given a subresource range that does not start at mip level zero, array layer zero (Anvil code -20005, unsupported subresource range); every image here has one mip level and one array layer.")
  EndIf
  If (*pCreateInfo\subresourceRange\levelCount & $FFFFFFFF) <> 1 Or (*pCreateInfo\subresourceRange\layerCount & $FFFFFFFF) <> 1
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateImageView was given a subresource range that does not contain exactly one mip level and one array layer (Anvil code -20001, invalid subresource range); every image here has one mip level and one array layer, and the view must include both.")
  EndIf
  ProcedureReturn AnvilVkImageViewCreate(device, *pCreateInfo\image, *pCreateInfo\viewType & $FFFFFFFF, *pCreateInfo\format & $FFFFFFFF, *pView)
EndProcedure

Procedure vkDestroyImageView(device.i, imageView.i, *pAllocator)
  If avkNoAllocator(*pAllocator, 0) <> #VK_SUCCESS
    ProcedureReturn
  EndIf
  AnvilVkImageViewDestroy(device, imageView)
EndProcedure

Procedure.i vkCreateFramebuffer(device.i, *pCreateInfo.VkFramebufferCreateInfo, *pAllocator, *pFramebuffer)
  Define rc.i
  If *pCreateInfo = 0 Or *pFramebuffer = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  rc = avkNoAllocator(*pAllocator, 0)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  If *pCreateInfo\sType <> #VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateFramebuffer was given a VkFramebufferCreateInfo whose sType is wrong (Anvil code -20001, wrong sType); it must be VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO.")
  EndIf
  If avkNoPNext(*pCreateInfo\pNext) <> #VK_SUCCESS
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateFramebuffer was given a VkFramebufferCreateInfo with a pNext chain (Anvil code -20005, no pNext extension is implemented); no framebuffer was created.")
  EndIf
  If (*pCreateInfo\attachmentCount & $FFFFFFFF) <> 1 Or *pCreateInfo\pAttachments = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateFramebuffer was given other than exactly one attachment (Anvil code -20005, unsupported framebuffer); the render pass has one attachment, so a framebuffer for it has one view.")
  EndIf
  ProcedureReturn AnvilVkFramebufferCreate(device, *pCreateInfo\renderPass, PeekI(*pCreateInfo\pAttachments), *pCreateInfo\width & $FFFFFFFF, *pCreateInfo\height & $FFFFFFFF, *pCreateInfo\layers & $FFFFFFFF, *pFramebuffer)
EndProcedure

Procedure vkDestroyFramebuffer(device.i, framebuffer.i, *pAllocator)
  If avkNoAllocator(*pAllocator, 0) <> #VK_SUCCESS
    ProcedureReturn
  EndIf
  AnvilVkFramebufferDestroy(device, framebuffer)
EndProcedure

; ----------------------------------------------------------------------
;  THE GRAPHICS PIPELINE
;
;  vkCreateGraphicsPipelines takes an array and this slice creates one at
;  a time. A count above one is REFUSED rather than partly honoured: the
;  specification says a failure writes VK_NULL_HANDLE into the rest, and
;  creating the first and silently stopping would be exactly the silent
;  partial success this engine never gives.
; ----------------------------------------------------------------------
Procedure.i vkCreateGraphicsPipelines(device.i, pipelineCache.i, createInfoCount.i, *pCreateInfos.VkGraphicsPipelineCreateInfo, *pAllocator, *pPipelines)
  Define rc.i
  If *pCreateInfos = 0 Or *pPipelines = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  rc = avkNoAllocator(*pAllocator, 0)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  If pipelineCache <> #VK_NULL_HANDLE
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was given a VkPipelineCache (Anvil code -20005, pipeline cache not implemented); there is no vkCreatePipelineCache here, so pass VK_NULL_HANDLE.")
  EndIf
  If createInfoCount <> 1
    ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateGraphicsPipelines was asked to create other than exactly one pipeline in one call (Anvil code -20005, batched creation not implemented); create them one at a time, because creating the first and stopping would be a silent partial success.")
  EndIf
  ProcedureReturn AnvilVkGraphicsPipelineCreate(device, *pCreateInfos, *pPipelines)
EndProcedure

Procedure vkDestroyPipeline(device.i, pipeline.i, *pAllocator)
  If avkNoAllocator(*pAllocator, 0) <> #VK_SUCCESS
    ProcedureReturn
  EndIf
  AnvilVkPipelineDestroy(device, pipeline)
EndProcedure

; ----------------------------------------------------------------------
;  THE RENDER PASS COMMANDS. All void, exactly as the registry declares.
; ----------------------------------------------------------------------
Procedure vkCmdBeginRenderPass(commandBuffer.i, *pRenderPassBegin.VkRenderPassBeginInfo, contents.i)
  If *pRenderPassBegin = 0
    avkFault(#ANVIL_VK_ERR_ARGS, "vkCmdBeginRenderPass was given a null VkRenderPassBeginInfo (Anvil code -20001, invalid argument); nothing was recorded.")
    ProcedureReturn
  EndIf
  If *pRenderPassBegin\sType <> #VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO
    avkFault(#ANVIL_VK_ERR_ARGS, "vkCmdBeginRenderPass was given a VkRenderPassBeginInfo whose sType is wrong (Anvil code -20001, wrong sType); it must be VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO.")
    ProcedureReturn
  EndIf
  If *pRenderPassBegin\pNext <> 0
    avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCmdBeginRenderPass was given a VkRenderPassBeginInfo with a pNext chain (Anvil code -20005, no pNext extension is implemented); nothing was recorded.")
    ProcedureReturn
  EndIf
  If contents <> #VK_SUBPASS_CONTENTS_INLINE
    avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCmdBeginRenderPass was asked for VK_SUBPASS_CONTENTS_SECONDARY_COMMAND_BUFFERS (Anvil code -20005, secondary execution not implemented); record the draw inline in the primary command buffer.")
    ProcedureReturn
  EndIf
  AnvilVkCmdBeginRenderPass(commandBuffer, *pRenderPassBegin\renderPass, *pRenderPassBegin\framebuffer, @*pRenderPassBegin\renderArea, *pRenderPassBegin\clearValueCount & $FFFFFFFF, *pRenderPassBegin\pClearValues)
EndProcedure

Procedure vkCmdBindPipeline(commandBuffer.i, pipelineBindPoint.i, pipeline.i)
  AnvilVkCmdBindPipeline(commandBuffer, pipelineBindPoint, pipeline)
EndProcedure

; The registry's own signature: a first binding, a count, and two arrays.
; It binds them one at a time through the recording procedure, so one
; call binding two buffers and two calls binding one each leave the
; command buffer in exactly the same state - which is what an application
; that binds its static colour buffer once and restreams position every
; frame depends on.
Procedure vkCmdBindVertexBuffers(commandBuffer.i, firstBinding.i, bindingCount.i, *pBuffers, *pOffsets)
  Define k.i
  If *pBuffers = 0 Or *pOffsets = 0
    avkFault(#ANVIL_VK_ERR_ARGS, "vkCmdBindVertexBuffers was given a null pBuffers or pOffsets (Anvil code -20001, invalid argument); nothing was recorded.")
    ProcedureReturn
  EndIf
  If bindingCount < 1 Or firstBinding < 0 Or (firstBinding + bindingCount) > #ANVIL_VK_MAX_BINDINGS
    avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCmdBindVertexBuffers was asked to bind a range of bindings this slice does not have (Anvil code -20005, unsupported binding range); firstBinding plus bindingCount must be at least one and at most four, which is the number of vertex input bindings a pipeline here may describe.")
    ProcedureReturn
  EndIf
  ; VkDeviceSize is uint64_t and the native integer is 64 bits on this
  ; part, so one PeekI reads a whole offset.
  k = 0
  While k < bindingCount
    AnvilVkCmdBindVertexBuffer(commandBuffer, firstBinding + k, PeekI(*pBuffers + (k * 8)), PeekI(*pOffsets + (k * 8)))
    k = k + 1
  Wend
EndProcedure

Procedure vkCmdPushConstants(commandBuffer.i, layout.i, stageFlags.i, offset.i, size.i, *pValues)
  AnvilVkCmdPushConstants(commandBuffer, layout, stageFlags, offset, size, *pValues)
EndProcedure

Procedure vkCmdDraw(commandBuffer.i, vertexCount.i, instanceCount.i, firstVertex.i, firstInstance.i)
  AnvilVkCmdDraw(commandBuffer, vertexCount, instanceCount, firstVertex, firstInstance)
EndProcedure

Procedure vkCmdEndRenderPass(commandBuffer.i)
  AnvilVkCmdEndRenderPass(commandBuffer)
EndProcedure

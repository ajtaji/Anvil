; ======================================================================
;  Vulkan 1.0 vocabulary foundation -- registry-derived, not conformance
; ======================================================================
; Source registry: KhronosGroup/Vulkan-Headers tag v1.4.350
; Commit: a33416ed2ce6bf8ef48b4eda821825f66d1850d3
; registry/vk.xml SHA-256:
; 50BD8C0F316EABF73D1C5FE3ADD2D89EAA480DBDA9282C12C289E80E9D081E08
; SPDX-License-Identifier: Apache-2.0 OR MIT
;
; The selected schema target is the <feature name="VK_VERSION_1_0"> block.
; This file does NOT claim that Anvil implements Vulkan 1.0. See COVERAGE.md.
;
; ABI boundary: every public record below uses the compiler's explicit AArch64
; C-layout mode. No hand padding or flattened substitute members are used.

#VK_API_VERSION_1_0 = $00400000
#VK_HEADER_VERSION = 350
#VK_HEADER_VERSION_COMPLETE = $0040415E
#VK_NULL_HANDLE = 0
#VK_WHOLE_SIZE = -1
#VK_TRUE = 1
#VK_FALSE = 0
#VK_MAX_EXTENSION_NAME_SIZE = 256
#VK_MAX_DESCRIPTION_SIZE = 256
#VK_UUID_SIZE = 16

; Values used by the first development-only transfer lowering.
#VK_FORMAT_B8G8R8A8_UNORM = 44
#VK_IMAGE_LAYOUT_UNDEFINED = 0
#VK_IMAGE_LAYOUT_GENERAL = 1
#VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL = 7

; VkResult -- VK_VERSION_1_0 entries.
#VK_SUCCESS = 0
#VK_NOT_READY = 1
#VK_TIMEOUT = 2
#VK_EVENT_SET = 3
#VK_EVENT_RESET = 4
#VK_INCOMPLETE = 5
#VK_ERROR_OUT_OF_HOST_MEMORY = -1
#VK_ERROR_OUT_OF_DEVICE_MEMORY = -2
#VK_ERROR_INITIALIZATION_FAILED = -3
#VK_ERROR_DEVICE_LOST = -4
#VK_ERROR_MEMORY_MAP_FAILED = -5
#VK_ERROR_LAYER_NOT_PRESENT = -6
#VK_ERROR_EXTENSION_NOT_PRESENT = -7
#VK_ERROR_FEATURE_NOT_PRESENT = -8
#VK_ERROR_INCOMPATIBLE_DRIVER = -9
#VK_ERROR_TOO_MANY_OBJECTS = -10
#VK_ERROR_FORMAT_NOT_SUPPORTED = -11
#VK_ERROR_FRAGMENTED_POOL = -12

; VkStructureType values used by the stage-1 lifecycle surface.
#VK_STRUCTURE_TYPE_APPLICATION_INFO = 0
#VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO = 1
#VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO = 2
#VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO = 3
#VK_STRUCTURE_TYPE_SUBMIT_INFO = 4
#VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO = 39
#VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO = 40
#VK_STRUCTURE_TYPE_COMMAND_BUFFER_INHERITANCE_INFO = 41
#VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO = 42

; Command pool and command buffer vocabulary.
#VK_COMMAND_BUFFER_LEVEL_PRIMARY = 0
#VK_COMMAND_BUFFER_LEVEL_SECONDARY = 1
#VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT = $00000001
#VK_COMMAND_BUFFER_USAGE_RENDER_PASS_CONTINUE_BIT = $00000002
#VK_COMMAND_BUFFER_USAGE_SIMULTANEOUS_USE_BIT = $00000004
#VK_COMMAND_POOL_CREATE_TRANSIENT_BIT = $00000001
#VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT = $00000002
#VK_COMMAND_POOL_RESET_RELEASE_RESOURCES_BIT = $00000001
#VK_COMMAND_BUFFER_RESET_RELEASE_RESOURCES_BIT = $00000001

; Exact core structures. Names, member order and scalar/pointer widths are
; taken directly from the pinned vk.xml.
Structure VkExtent2D Align #PB_Structure_AlignC
  width.l
  height.l
EndStructure

Structure VkExtent3D Align #PB_Structure_AlignC
  width.l
  height.l
  depth.l
EndStructure

Structure VkOffset2D Align #PB_Structure_AlignC
  x.l
  y.l
EndStructure

Structure VkOffset3D Align #PB_Structure_AlignC
  x.l
  y.l
  z.l
EndStructure

Structure VkViewport Align #PB_Structure_AlignC
  x.f
  y.f
  width.f
  height.f
  minDepth.f
  maxDepth.f
EndStructure

Structure VkRect2D Align #PB_Structure_AlignC
  offset.VkOffset2D
  extent.VkExtent2D
EndStructure

Structure VkComponentMapping Align #PB_Structure_AlignC
  r.l
  g.l
  b.l
  a.l
EndStructure

Structure VkExtensionProperties Align #PB_Structure_AlignC
  extensionName.a[#VK_MAX_EXTENSION_NAME_SIZE]
  specVersion.l
EndStructure

Structure VkLayerProperties Align #PB_Structure_AlignC
  layerName.a[#VK_MAX_EXTENSION_NAME_SIZE]
  specVersion.l
  implementationVersion.l
  description.a[#VK_MAX_DESCRIPTION_SIZE]
EndStructure

Structure VkApplicationInfo Align #PB_Structure_AlignC
  sType.l
  *pNext
  *pApplicationName
  applicationVersion.l
  *pEngineName
  engineVersion.l
  apiVersion.l
EndStructure

Structure VkAllocationCallbacks Align #PB_Structure_AlignC
  *pUserData
  *pfnAllocation
  *pfnReallocation
  *pfnFree
  *pfnInternalAllocation
  *pfnInternalFree
EndStructure

Structure VkDeviceQueueCreateInfo Align #PB_Structure_AlignC
  sType.l
  *pNext
  flags.l
  queueFamilyIndex.l
  queueCount.l
  *pQueuePriorities
EndStructure

Structure VkDeviceCreateInfo Align #PB_Structure_AlignC
  sType.l
  *pNext
  flags.l
  queueCreateInfoCount.l
  *pQueueCreateInfos
  enabledLayerCount.l
  *ppEnabledLayerNames
  enabledExtensionCount.l
  *ppEnabledExtensionNames
  *pEnabledFeatures
EndStructure

Structure VkInstanceCreateInfo Align #PB_Structure_AlignC
  sType.l
  *pNext
  flags.l
  *pApplicationInfo
  enabledLayerCount.l
  *ppEnabledLayerNames
  enabledExtensionCount.l
  *ppEnabledExtensionNames
EndStructure

Structure VkCommandPoolCreateInfo Align #PB_Structure_AlignC
  sType.l
  *pNext
  flags.l
  queueFamilyIndex.l
EndStructure

Structure VkCommandBufferAllocateInfo Align #PB_Structure_AlignC
  sType.l
  *pNext
  commandPool.i
  level.l
  commandBufferCount.l
EndStructure

Structure VkCommandBufferInheritanceInfo Align #PB_Structure_AlignC
  sType.l
  *pNext
  renderPass.i
  subpass.l
  framebuffer.i
  occlusionQueryEnable.l
  queryFlags.l
  pipelineStatistics.l
EndStructure

Structure VkCommandBufferBeginInfo Align #PB_Structure_AlignC
  sType.l
  *pNext
  flags.l
  *pInheritanceInfo
EndStructure

Structure VkSubmitInfo Align #PB_Structure_AlignC
  sType.l
  *pNext
  waitSemaphoreCount.l
  *pWaitSemaphores
  *pWaitDstStageMask
  commandBufferCount.l
  *pCommandBuffers
  signalSemaphoreCount.l
  *pSignalSemaphores
EndStructure

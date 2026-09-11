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

; VkFormat -- only the two 8-bit-per-channel colour formats this slice names.
; B8G8R8A8_UNORM is the one it implements; R8G8B8A8_UNORM is declared so a
; caller asking for it is refused against a real registry value rather than
; against an unknown number.
#VK_FORMAT_UNDEFINED = 0
#VK_FORMAT_R8G8B8A8_UNORM = 37
#VK_FORMAT_B8G8R8A8_UNORM = 44

; VkImageLayout -- the core-1.0 entries the layout tracker understands.
#VK_IMAGE_LAYOUT_UNDEFINED = 0
#VK_IMAGE_LAYOUT_GENERAL = 1
#VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL = 2
#VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL = 6
#VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL = 7
#VK_IMAGE_LAYOUT_PREINITIALIZED = 8

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
#VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO = 5
#VK_STRUCTURE_TYPE_FENCE_CREATE_INFO = 8
#VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO = 14
#VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO = 39
#VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO = 40
#VK_STRUCTURE_TYPE_COMMAND_BUFFER_INHERITANCE_INFO = 41
#VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO = 42
#VK_STRUCTURE_TYPE_BUFFER_MEMORY_BARRIER = 44
#VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER = 45
#VK_STRUCTURE_TYPE_MEMORY_BARRIER = 46

; Image creation vocabulary.
#VK_IMAGE_TYPE_1D = 0
#VK_IMAGE_TYPE_2D = 1
#VK_IMAGE_TYPE_3D = 2
#VK_IMAGE_TILING_OPTIMAL = 0
#VK_IMAGE_TILING_LINEAR = 1
#VK_SHARING_MODE_EXCLUSIVE = 0
#VK_SHARING_MODE_CONCURRENT = 1
#VK_SAMPLE_COUNT_1_BIT = $00000001
#VK_SAMPLE_COUNT_2_BIT = $00000002
#VK_IMAGE_USAGE_TRANSFER_SRC_BIT = $00000001
#VK_IMAGE_USAGE_TRANSFER_DST_BIT = $00000002
#VK_IMAGE_USAGE_SAMPLED_BIT = $00000004
#VK_IMAGE_USAGE_STORAGE_BIT = $00000008
#VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT = $00000010
#VK_IMAGE_ASPECT_COLOR_BIT = $00000001
#VK_IMAGE_ASPECT_DEPTH_BIT = $00000002
#VK_IMAGE_ASPECT_STENCIL_BIT = $00000004
#VK_IMAGE_ASPECT_METADATA_BIT = $00000008

; Device memory vocabulary.
#VK_MAX_MEMORY_TYPES = 32
#VK_MAX_MEMORY_HEAPS = 16
#VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT = $00000001
#VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT = $00000002
#VK_MEMORY_PROPERTY_HOST_COHERENT_BIT = $00000004
#VK_MEMORY_PROPERTY_HOST_CACHED_BIT = $00000008
#VK_MEMORY_HEAP_DEVICE_LOCAL_BIT = $00000001

; Queue family vocabulary.
#VK_QUEUE_GRAPHICS_BIT = $00000001
#VK_QUEUE_COMPUTE_BIT = $00000002
#VK_QUEUE_TRANSFER_BIT = $00000004
#VK_QUEUE_SPARSE_BINDING_BIT = $00000008

; Synchronization vocabulary. The access and stage bits are the core-1.0
; values; this slice implements only the transfer-write dependency and the
; host read that follows it, and refuses every other combination out loud.
#VK_ACCESS_TRANSFER_READ_BIT = $00000800
#VK_ACCESS_TRANSFER_WRITE_BIT = $00001000
#VK_ACCESS_HOST_READ_BIT = $00002000
#VK_ACCESS_HOST_WRITE_BIT = $00004000
#VK_ACCESS_MEMORY_READ_BIT = $00008000
#VK_ACCESS_MEMORY_WRITE_BIT = $00010000
#VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT = $00000001
#VK_PIPELINE_STAGE_TRANSFER_BIT = $00001000
#VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT = $00002000
#VK_PIPELINE_STAGE_HOST_BIT = $00004000
#VK_PIPELINE_STAGE_ALL_COMMANDS_BIT = $00010000
#VK_DEPENDENCY_BY_REGION_BIT = $00000001
#VK_FENCE_CREATE_SIGNALED_BIT = $00000001

; The registry spells these (~0U). They are written here as the exact 32-bit
; pattern, because PureMetal's native integer is 64 bits on AArch64 and an
; unqualified ~0 would not compare equal to a uint32_t member read back.
#VK_QUEUE_FAMILY_IGNORED = $FFFFFFFF
#VK_REMAINING_MIP_LEVELS = $FFFFFFFF
#VK_REMAINING_ARRAY_LAYERS = $FFFFFFFF

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

; ----------------------------------------------------------------------
;  Resource, memory and synchronization records.
;
;  VkDeviceSize is uint64_t, so it is .q and not .i: .i is the target's
;  native width and would be four bytes on a 32-bit backend, which would
;  move every member after it.
; ----------------------------------------------------------------------
Structure VkMemoryAllocateInfo Align #PB_Structure_AlignC
  sType.l
  *pNext
  allocationSize.q
  memoryTypeIndex.l
EndStructure

Structure VkMemoryRequirements Align #PB_Structure_AlignC
  size.q
  alignment.q
  memoryTypeBits.l
EndStructure

Structure VkMemoryType Align #PB_Structure_AlignC
  propertyFlags.l
  heapIndex.l
EndStructure

Structure VkMemoryHeap Align #PB_Structure_AlignC
  size.q
  flags.l
EndStructure

Structure VkPhysicalDeviceMemoryProperties Align #PB_Structure_AlignC
  memoryTypeCount.l
  memoryTypes.VkMemoryType[#VK_MAX_MEMORY_TYPES]
  memoryHeapCount.l
  memoryHeaps.VkMemoryHeap[#VK_MAX_MEMORY_HEAPS]
EndStructure

Structure VkQueueFamilyProperties Align #PB_Structure_AlignC
  queueFlags.l
  queueCount.l
  timestampValidBits.l
  minImageTransferGranularity.VkExtent3D
EndStructure

Structure VkImageCreateInfo Align #PB_Structure_AlignC
  sType.l
  *pNext
  flags.l
  imageType.l
  format.l
  extent.VkExtent3D
  mipLevels.l
  arrayLayers.l
  samples.l
  tiling.l
  usage.l
  sharingMode.l
  queueFamilyIndexCount.l
  *pQueueFamilyIndices
  initialLayout.l
EndStructure

Structure VkImageSubresourceRange Align #PB_Structure_AlignC
  aspectMask.l
  baseMipLevel.l
  levelCount.l
  baseArrayLayer.l
  layerCount.l
EndStructure

Structure VkImageMemoryBarrier Align #PB_Structure_AlignC
  sType.l
  *pNext
  srcAccessMask.l
  dstAccessMask.l
  oldLayout.l
  newLayout.l
  srcQueueFamilyIndex.l
  dstQueueFamilyIndex.l
  image.i
  subresourceRange.VkImageSubresourceRange
EndStructure

Structure VkFenceCreateInfo Align #PB_Structure_AlignC
  sType.l
  *pNext
  flags.l
EndStructure

; VkClearColorValue IS A UNION and is deliberately NOT declared here.
; PureMetal has no union declaration, and a structure with one arm of it
; would silently be the wrong type for the other two. vkCmdClearColorImage
; takes `const VkClearColorValue*`, so the adapter reads the caller's
; sixteen bytes as four binary32 components - which is what the union's
; float32 arm is - and says so at the call site.

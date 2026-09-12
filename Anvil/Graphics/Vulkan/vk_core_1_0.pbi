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
; Promoted into Vulkan 1.1 from VK_KHR_maintenance1, and it is the code
; the specification requires when a descriptor pool has no room left -
; VK_ERROR_OUT_OF_HOST_MEMORY would say the host ran out of memory,
; which is a different thing and sends a caller somewhere else.
#VK_ERROR_OUT_OF_POOL_MEMORY = -1000069000

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

; ======================================================================
;  GRAPHICS PIPELINE VOCABULARY
; ======================================================================
;  Added when the first real pipeline landed. Every value and every
;  member below is the pinned registry's own, in the registry's order and
;  at the registry's width, the same rule the rest of this file follows.
;
;  VkClearValue IS A UNION, like VkClearColorValue above, and is
;  deliberately NOT declared. VkRenderPassBeginInfo.pClearValues points
;  at an array of them and the adapter reads each one's sixteen bytes as
;  the colour arm's four binary32 components, which is what a colour
;  attachment's clear value is, and says so at the call site.

; VkStructureType, the pipeline block.
#VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO = 12
#VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO = 15
#VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO = 16
#VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO = 18
#VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO = 19
#VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO = 20
#VK_STRUCTURE_TYPE_PIPELINE_TESSELLATION_STATE_CREATE_INFO = 21
#VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO = 22
#VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO = 23
#VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO = 24
#VK_STRUCTURE_TYPE_PIPELINE_DEPTH_STENCIL_STATE_CREATE_INFO = 25
#VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO = 26
#VK_STRUCTURE_TYPE_PIPELINE_DYNAMIC_STATE_CREATE_INFO = 27
#VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO = 28
#VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO = 30
#VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO = 37
#VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO = 38
#VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO = 43

; VkFormat, the vertex-attribute entries this slice names.
#VK_FORMAT_R32G32_SFLOAT = 103
#VK_FORMAT_R32G32B32_SFLOAT = 106
#VK_FORMAT_R32G32B32A32_SFLOAT = 109

; VkShaderStageFlagBits.
#VK_SHADER_STAGE_VERTEX_BIT = $00000001
#VK_SHADER_STAGE_TESSELLATION_CONTROL_BIT = $00000002
#VK_SHADER_STAGE_TESSELLATION_EVALUATION_BIT = $00000004
#VK_SHADER_STAGE_GEOMETRY_BIT = $00000008
#VK_SHADER_STAGE_FRAGMENT_BIT = $00000010
#VK_SHADER_STAGE_COMPUTE_BIT = $00000020
#VK_SHADER_STAGE_ALL_GRAPHICS = $0000001F

; VkPrimitiveTopology.
#VK_PRIMITIVE_TOPOLOGY_POINT_LIST = 0
#VK_PRIMITIVE_TOPOLOGY_LINE_LIST = 1
#VK_PRIMITIVE_TOPOLOGY_LINE_STRIP = 2
#VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST = 3
#VK_PRIMITIVE_TOPOLOGY_TRIANGLE_STRIP = 4
#VK_PRIMITIVE_TOPOLOGY_TRIANGLE_FAN = 5

; VkVertexInputRate, VkPolygonMode, VkCullModeFlagBits, VkFrontFace.
#VK_VERTEX_INPUT_RATE_VERTEX = 0
#VK_VERTEX_INPUT_RATE_INSTANCE = 1
#VK_POLYGON_MODE_FILL = 0
#VK_POLYGON_MODE_LINE = 1
#VK_POLYGON_MODE_POINT = 2
#VK_CULL_MODE_NONE = 0
#VK_CULL_MODE_FRONT_BIT = $00000001
#VK_CULL_MODE_BACK_BIT = $00000002
#VK_CULL_MODE_FRONT_AND_BACK = $00000003
#VK_FRONT_FACE_COUNTER_CLOCKWISE = 0
#VK_FRONT_FACE_CLOCKWISE = 1

; VkAttachmentLoadOp, VkAttachmentStoreOp, VkPipelineBindPoint,
; VkSubpassContents, VkImageViewType, VkComponentSwizzle.
#VK_ATTACHMENT_LOAD_OP_LOAD = 0
#VK_ATTACHMENT_LOAD_OP_CLEAR = 1
#VK_ATTACHMENT_LOAD_OP_DONT_CARE = 2
#VK_ATTACHMENT_STORE_OP_STORE = 0
#VK_ATTACHMENT_STORE_OP_DONT_CARE = 1
#VK_PIPELINE_BIND_POINT_GRAPHICS = 0
#VK_PIPELINE_BIND_POINT_COMPUTE = 1
#VK_SUBPASS_CONTENTS_INLINE = 0
#VK_SUBPASS_CONTENTS_SECONDARY_COMMAND_BUFFERS = 1
#VK_SUBPASS_EXTERNAL = $FFFFFFFF
#VK_IMAGE_VIEW_TYPE_1D = 0
#VK_IMAGE_VIEW_TYPE_2D = 1
#VK_IMAGE_VIEW_TYPE_3D = 2
#VK_COMPONENT_SWIZZLE_IDENTITY = 0

; VkBufferUsageFlagBits and VkColorComponentFlagBits.
#VK_BUFFER_USAGE_TRANSFER_SRC_BIT = $00000001
#VK_BUFFER_USAGE_TRANSFER_DST_BIT = $00000002
#VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT = $00000010
#VK_BUFFER_USAGE_STORAGE_BUFFER_BIT = $00000020
#VK_BUFFER_USAGE_INDEX_BUFFER_BIT = $00000040
#VK_BUFFER_USAGE_VERTEX_BUFFER_BIT = $00000080
#VK_BUFFER_USAGE_INDIRECT_BUFFER_BIT = $00000100
#VK_COLOR_COMPONENT_R_BIT = $00000001
#VK_COLOR_COMPONENT_G_BIT = $00000002
#VK_COLOR_COMPONENT_B_BIT = $00000004
#VK_COLOR_COMPONENT_A_BIT = $00000008

; The stage and access bits a colour attachment needs.
#VK_PIPELINE_STAGE_VERTEX_INPUT_BIT = $00000004
#VK_PIPELINE_STAGE_VERTEX_SHADER_BIT = $00000008
#VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT = $00000080
#VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT = $00000400
#VK_ACCESS_VERTEX_ATTRIBUTE_READ_BIT = $00000002
#VK_ACCESS_UNIFORM_READ_BIT = $00000008
#VK_ACCESS_COLOR_ATTACHMENT_READ_BIT = $00000080
#VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT = $00000100

Structure VkShaderModuleCreateInfo Align #PB_Structure_AlignC
  sType.l
  *pNext
  flags.l
  codeSize.i
  *pCode
EndStructure

Structure VkSpecializationMapEntry Align #PB_Structure_AlignC
  constantID.l
  offset.l
  size.i
EndStructure

Structure VkSpecializationInfo Align #PB_Structure_AlignC
  mapEntryCount.l
  *pMapEntries
  dataSize.i
  *pData
EndStructure

Structure VkPipelineShaderStageCreateInfo Align #PB_Structure_AlignC
  sType.l
  *pNext
  flags.l
  stage.l
  module.i
  *pName
  *pSpecializationInfo
EndStructure

Structure VkVertexInputBindingDescription Align #PB_Structure_AlignC
  binding.l
  stride.l
  inputRate.l
EndStructure

Structure VkVertexInputAttributeDescription Align #PB_Structure_AlignC
  location.l
  binding.l
  format.l
  offset.l
EndStructure

Structure VkPipelineVertexInputStateCreateInfo Align #PB_Structure_AlignC
  sType.l
  *pNext
  flags.l
  vertexBindingDescriptionCount.l
  *pVertexBindingDescriptions
  vertexAttributeDescriptionCount.l
  *pVertexAttributeDescriptions
EndStructure

Structure VkPipelineInputAssemblyStateCreateInfo Align #PB_Structure_AlignC
  sType.l
  *pNext
  flags.l
  topology.l
  primitiveRestartEnable.l
EndStructure

Structure VkPipelineViewportStateCreateInfo Align #PB_Structure_AlignC
  sType.l
  *pNext
  flags.l
  viewportCount.l
  *pViewports
  scissorCount.l
  *pScissors
EndStructure

Structure VkPipelineRasterizationStateCreateInfo Align #PB_Structure_AlignC
  sType.l
  *pNext
  flags.l
  depthClampEnable.l
  rasterizerDiscardEnable.l
  polygonMode.l
  cullMode.l
  frontFace.l
  depthBiasEnable.l
  depthBiasConstantFactor.f
  depthBiasClamp.f
  depthBiasSlopeFactor.f
  lineWidth.f
EndStructure

Structure VkPipelineMultisampleStateCreateInfo Align #PB_Structure_AlignC
  sType.l
  *pNext
  flags.l
  rasterizationSamples.l
  sampleShadingEnable.l
  minSampleShading.f
  *pSampleMask
  alphaToCoverageEnable.l
  alphaToOneEnable.l
EndStructure

Structure VkPipelineColorBlendAttachmentState Align #PB_Structure_AlignC
  blendEnable.l
  srcColorBlendFactor.l
  dstColorBlendFactor.l
  colorBlendOp.l
  srcAlphaBlendFactor.l
  dstAlphaBlendFactor.l
  alphaBlendOp.l
  colorWriteMask.l
EndStructure

Structure VkPipelineColorBlendStateCreateInfo Align #PB_Structure_AlignC
  sType.l
  *pNext
  flags.l
  logicOpEnable.l
  logicOp.l
  attachmentCount.l
  *pAttachments
  blendConstants.f[4]
EndStructure

Structure VkPushConstantRange Align #PB_Structure_AlignC
  stageFlags.l
  offset.l
  size.l
EndStructure

Structure VkPipelineLayoutCreateInfo Align #PB_Structure_AlignC
  sType.l
  *pNext
  flags.l
  setLayoutCount.l
  *pSetLayouts
  pushConstantRangeCount.l
  *pPushConstantRanges
EndStructure

Structure VkGraphicsPipelineCreateInfo Align #PB_Structure_AlignC
  sType.l
  *pNext
  flags.l
  stageCount.l
  *pStages
  *pVertexInputState
  *pInputAssemblyState
  *pTessellationState
  *pViewportState
  *pRasterizationState
  *pMultisampleState
  *pDepthStencilState
  *pColorBlendState
  *pDynamicState
  layout.i
  renderPass.i
  subpass.l
  basePipelineHandle.i
  basePipelineIndex.l
EndStructure

Structure VkAttachmentDescription Align #PB_Structure_AlignC
  flags.l
  format.l
  samples.l
  loadOp.l
  storeOp.l
  stencilLoadOp.l
  stencilStoreOp.l
  initialLayout.l
  finalLayout.l
EndStructure

Structure VkAttachmentReference Align #PB_Structure_AlignC
  attachment.l
  layout.l
EndStructure

Structure VkSubpassDescription Align #PB_Structure_AlignC
  flags.l
  pipelineBindPoint.l
  inputAttachmentCount.l
  *pInputAttachments
  colorAttachmentCount.l
  *pColorAttachments
  *pResolveAttachments
  *pDepthStencilAttachment
  preserveAttachmentCount.l
  *pPreserveAttachments
EndStructure

Structure VkSubpassDependency Align #PB_Structure_AlignC
  srcSubpass.l
  dstSubpass.l
  srcStageMask.l
  dstStageMask.l
  srcAccessMask.l
  dstAccessMask.l
  dependencyFlags.l
EndStructure

Structure VkRenderPassCreateInfo Align #PB_Structure_AlignC
  sType.l
  *pNext
  flags.l
  attachmentCount.l
  *pAttachments
  subpassCount.l
  *pSubpasses
  dependencyCount.l
  *pDependencies
EndStructure

Structure VkImageViewCreateInfo Align #PB_Structure_AlignC
  sType.l
  *pNext
  flags.l
  image.i
  viewType.l
  format.l
  components.VkComponentMapping
  subresourceRange.VkImageSubresourceRange
EndStructure

Structure VkFramebufferCreateInfo Align #PB_Structure_AlignC
  sType.l
  *pNext
  flags.l
  renderPass.i
  attachmentCount.l
  *pAttachments
  width.l
  height.l
  layers.l
EndStructure

Structure VkRenderPassBeginInfo Align #PB_Structure_AlignC
  sType.l
  *pNext
  renderPass.i
  framebuffer.i
  renderArea.VkRect2D
  clearValueCount.l
  *pClearValues
EndStructure

Structure VkBufferCreateInfo Align #PB_Structure_AlignC
  sType.l
  *pNext
  flags.l
  size.q
  usage.l
  sharingMode.l
  queueFamilyIndexCount.l
  *pQueueFamilyIndices
EndStructure

; ======================================================================
;  DESCRIPTOR VOCABULARY
; ======================================================================
;  Added when the first uniform buffer landed. Every value and every
;  member below is the pinned registry's own, in the registry's order
;  and at the registry's width, the same rule the rest of this file
;  follows.
;
;  THE WHOLE VkDescriptorType ENUMERATION IS DECLARED even though one
;  value is implemented. A refusal that names what it refused needs the
;  name, and a caller who writes VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER
;  should be told that Anvil does not implement it rather than that
;  "3" is not a descriptor type.

; VkStructureType, the descriptor block.
#VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO = 32
#VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO = 33
#VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO = 34
#VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET = 35
#VK_STRUCTURE_TYPE_COPY_DESCRIPTOR_SET = 36

; VkDescriptorType.
#VK_DESCRIPTOR_TYPE_SAMPLER = 0
#VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER = 1
#VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE = 2
#VK_DESCRIPTOR_TYPE_STORAGE_IMAGE = 3
#VK_DESCRIPTOR_TYPE_UNIFORM_TEXEL_BUFFER = 4
#VK_DESCRIPTOR_TYPE_STORAGE_TEXEL_BUFFER = 5
#VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER = 6
#VK_DESCRIPTOR_TYPE_STORAGE_BUFFER = 7
#VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER_DYNAMIC = 8
#VK_DESCRIPTOR_TYPE_STORAGE_BUFFER_DYNAMIC = 9
#VK_DESCRIPTOR_TYPE_INPUT_ATTACHMENT = 10

; VkDescriptorPoolCreateFlagBits.
#VK_DESCRIPTOR_POOL_CREATE_FREE_DESCRIPTOR_SET_BIT = $00000001

; VK_WHOLE_SIZE is declared once at the top of this file, as -1: the
; registry writes it (~0ULL) and a 64-bit field holding that reads back
; as -1 on this part. It is not redeclared here.

Structure VkDescriptorSetLayoutBinding Align #PB_Structure_AlignC
  binding.l
  descriptorType.l
  descriptorCount.l
  stageFlags.l
  *pImmutableSamplers
EndStructure

Structure VkDescriptorSetLayoutCreateInfo Align #PB_Structure_AlignC
  sType.l
  *pNext
  flags.l
  bindingCount.l
  *pBindings
EndStructure

Structure VkDescriptorPoolSize Align #PB_Structure_AlignC
  type.l
  descriptorCount.l
EndStructure

Structure VkDescriptorPoolCreateInfo Align #PB_Structure_AlignC
  sType.l
  *pNext
  flags.l
  maxSets.l
  poolSizeCount.l
  *pPoolSizes
EndStructure

Structure VkDescriptorSetAllocateInfo Align #PB_Structure_AlignC
  sType.l
  *pNext
  descriptorPool.i
  descriptorSetCount.l
  *pSetLayouts
EndStructure

Structure VkDescriptorBufferInfo Align #PB_Structure_AlignC
  buffer.i
  offset.q
  range.q
EndStructure

Structure VkDescriptorImageInfo Align #PB_Structure_AlignC
  sampler.i
  imageView.i
  imageLayout.l
EndStructure

Structure VkWriteDescriptorSet Align #PB_Structure_AlignC
  sType.l
  *pNext
  dstSet.i
  dstBinding.l
  dstArrayElement.l
  descriptorCount.l
  descriptorType.l
  *pImageInfo
  *pBufferInfo
  *pTexelBufferView
EndStructure

Structure VkCopyDescriptorSet Align #PB_Structure_AlignC
  sType.l
  *pNext
  srcSet.i
  srcBinding.l
  srcArrayElement.l
  dstSet.i
  dstBinding.l
  dstArrayElement.l
  descriptorCount.l
EndStructure

#!/usr/bin/env python3
"""Registry and emitted-A64 gate for Anvil's Vulkan ABI and lifecycle.

This gate answers two questions and no others:

  1. does every constant, structure member name, member order and member
     type in Anvil's vocabulary match the PINNED Khronos registry, and
  2. does the compiled AArch64 code give every one of those structures
     the exact size and offsets the C ABI requires, and does the public
     vk* surface refuse what it does not implement.

It does NOT prove GPU execution. The behavioural gate for the resource,
layout, fence and submission engine is tools/vulkan_resource_check.py,
and the backend link gate is tools/vulkan_v3d_backend_check.py.

  VULKAN_REGISTRY=<pinned v1.4.350 registry/vk.xml> PMF_COMPILER=<PureMetalForge.exe> \\
      py -3 Anvil/Graphics/Vulkan/Tests/vulkan_foundation_check.py
"""

from __future__ import annotations

import hashlib
import argparse
import importlib.util
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
VOCAB = HERE.parent / "vk_core_1_0.pbi"
PROBE = HERE / "vulkan_foundation.pi4"
PRODUCTION_PROBE = HERE / "vulkan_production_probe.pi4"
V3D_BACKEND = HERE.parent / "vk_v3d_backend.pi4"
API = HERE.parent / "vk_api.pbi"
MEMORY = HERE.parent / "vk_memory.pbi"
LOAD, STACK, RETURN = 0x400000, 0x3000000, 0xDEAD0000
OUT = 0x06000000
MMIO = 0xFC000000
REGISTRY_SHA256 = "50bd8c0f316eabf73d1c5fe3add2d89eaa480dbda9282c12c289e80e9d081e08"


CONSTANTS = {
    "VK_SUCCESS", "VK_NOT_READY", "VK_TIMEOUT", "VK_EVENT_SET",
    "VK_EVENT_RESET", "VK_INCOMPLETE", "VK_ERROR_OUT_OF_HOST_MEMORY",
    "VK_ERROR_OUT_OF_DEVICE_MEMORY", "VK_ERROR_INITIALIZATION_FAILED",
    "VK_ERROR_DEVICE_LOST", "VK_ERROR_MEMORY_MAP_FAILED",
    "VK_ERROR_LAYER_NOT_PRESENT", "VK_ERROR_EXTENSION_NOT_PRESENT",
    "VK_ERROR_FEATURE_NOT_PRESENT", "VK_ERROR_INCOMPATIBLE_DRIVER",
    "VK_ERROR_TOO_MANY_OBJECTS", "VK_ERROR_FORMAT_NOT_SUPPORTED",
    "VK_ERROR_FRAGMENTED_POOL", "VK_COMMAND_BUFFER_LEVEL_PRIMARY",
    "VK_COMMAND_BUFFER_LEVEL_SECONDARY",
    "VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT",
    "VK_COMMAND_BUFFER_USAGE_RENDER_PASS_CONTINUE_BIT",
    "VK_COMMAND_BUFFER_USAGE_SIMULTANEOUS_USE_BIT",
    "VK_COMMAND_POOL_CREATE_TRANSIENT_BIT",
    "VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT",
    "VK_COMMAND_POOL_RESET_RELEASE_RESOURCES_BIT",
    "VK_COMMAND_BUFFER_RESET_RELEASE_RESOURCES_BIT",
    "VK_STRUCTURE_TYPE_APPLICATION_INFO", "VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO",
    "VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO", "VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO",
    "VK_STRUCTURE_TYPE_SUBMIT_INFO", "VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO",
    "VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO",
    "VK_STRUCTURE_TYPE_COMMAND_BUFFER_INHERITANCE_INFO",
    "VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO",
    "VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO", "VK_STRUCTURE_TYPE_MAPPED_MEMORY_RANGE", "VK_STRUCTURE_TYPE_FENCE_CREATE_INFO",
    "VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO",
    "VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO", "VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO", "VK_STRUCTURE_TYPE_MEMORY_BARRIER",
    "VK_STRUCTURE_TYPE_BUFFER_MEMORY_BARRIER", "VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER",
    "VK_FORMAT_UNDEFINED", "VK_FORMAT_R8G8B8A8_UNORM", "VK_FORMAT_B8G8R8A8_UNORM",
    "VK_FORMAT_FEATURE_SAMPLED_IMAGE_BIT", "VK_FORMAT_FEATURE_COLOR_ATTACHMENT_BIT",
    "VK_FORMAT_FEATURE_COLOR_ATTACHMENT_BLEND_BIT",
    "VK_IMAGE_LAYOUT_UNDEFINED", "VK_IMAGE_LAYOUT_GENERAL",
    "VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL",
    "VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL",
    "VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL", "VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL",
    "VK_IMAGE_LAYOUT_PREINITIALIZED",
    "VK_IMAGE_TYPE_1D", "VK_IMAGE_TYPE_2D", "VK_IMAGE_TYPE_3D",
    "VK_IMAGE_TILING_OPTIMAL", "VK_IMAGE_TILING_LINEAR",
    "VK_SHARING_MODE_EXCLUSIVE", "VK_SHARING_MODE_CONCURRENT",
    "VK_SAMPLE_COUNT_1_BIT", "VK_SAMPLE_COUNT_2_BIT",
    "VK_IMAGE_USAGE_TRANSFER_SRC_BIT", "VK_IMAGE_USAGE_TRANSFER_DST_BIT",
    "VK_IMAGE_USAGE_SAMPLED_BIT", "VK_IMAGE_USAGE_STORAGE_BIT",
    "VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT",
    "VK_IMAGE_ASPECT_COLOR_BIT", "VK_IMAGE_ASPECT_DEPTH_BIT",
    "VK_IMAGE_ASPECT_STENCIL_BIT", "VK_IMAGE_ASPECT_METADATA_BIT",
    "VK_BLEND_FACTOR_ZERO", "VK_BLEND_FACTOR_ONE",
    "VK_BLEND_FACTOR_SRC_COLOR", "VK_BLEND_FACTOR_ONE_MINUS_SRC_COLOR",
    "VK_BLEND_FACTOR_DST_COLOR", "VK_BLEND_FACTOR_ONE_MINUS_DST_COLOR",
    "VK_BLEND_FACTOR_SRC_ALPHA", "VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA",
    "VK_BLEND_FACTOR_DST_ALPHA", "VK_BLEND_FACTOR_ONE_MINUS_DST_ALPHA",
    "VK_BLEND_FACTOR_CONSTANT_COLOR", "VK_BLEND_FACTOR_ONE_MINUS_CONSTANT_COLOR",
    "VK_BLEND_FACTOR_CONSTANT_ALPHA", "VK_BLEND_FACTOR_ONE_MINUS_CONSTANT_ALPHA",
    "VK_BLEND_FACTOR_SRC_ALPHA_SATURATE", "VK_BLEND_FACTOR_SRC1_COLOR",
    "VK_BLEND_FACTOR_ONE_MINUS_SRC1_COLOR", "VK_BLEND_FACTOR_SRC1_ALPHA",
    "VK_BLEND_FACTOR_ONE_MINUS_SRC1_ALPHA", "VK_BLEND_OP_ADD",
    "VK_BLEND_OP_SUBTRACT", "VK_BLEND_OP_REVERSE_SUBTRACT",
    "VK_BLEND_OP_MIN", "VK_BLEND_OP_MAX",
    "VK_FILTER_NEAREST", "VK_FILTER_LINEAR",
    "VK_SAMPLER_MIPMAP_MODE_NEAREST", "VK_SAMPLER_MIPMAP_MODE_LINEAR",
    "VK_SAMPLER_ADDRESS_MODE_REPEAT", "VK_SAMPLER_ADDRESS_MODE_MIRRORED_REPEAT",
    "VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE", "VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_BORDER",
    "VK_BORDER_COLOR_FLOAT_TRANSPARENT_BLACK", "VK_BORDER_COLOR_INT_TRANSPARENT_BLACK",
    "VK_BORDER_COLOR_FLOAT_OPAQUE_BLACK", "VK_BORDER_COLOR_INT_OPAQUE_BLACK",
    "VK_BORDER_COLOR_FLOAT_OPAQUE_WHITE", "VK_BORDER_COLOR_INT_OPAQUE_WHITE",
    "VK_MAX_MEMORY_TYPES", "VK_MAX_MEMORY_HEAPS",
    "VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT", "VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT",
    "VK_MEMORY_PROPERTY_HOST_COHERENT_BIT", "VK_MEMORY_PROPERTY_HOST_CACHED_BIT",
    "VK_MEMORY_HEAP_DEVICE_LOCAL_BIT",
    "VK_QUEUE_GRAPHICS_BIT", "VK_QUEUE_COMPUTE_BIT", "VK_QUEUE_TRANSFER_BIT",
    "VK_QUEUE_SPARSE_BINDING_BIT",
    "VK_ACCESS_TRANSFER_READ_BIT", "VK_ACCESS_TRANSFER_WRITE_BIT",
    "VK_ACCESS_SHADER_READ_BIT",
    "VK_ACCESS_HOST_READ_BIT", "VK_ACCESS_HOST_WRITE_BIT",
    "VK_ACCESS_MEMORY_READ_BIT", "VK_ACCESS_MEMORY_WRITE_BIT",
    "VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT", "VK_PIPELINE_STAGE_TRANSFER_BIT",
    "VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT", "VK_PIPELINE_STAGE_HOST_BIT",
    "VK_PIPELINE_STAGE_ALL_COMMANDS_BIT",
    "VK_DEPENDENCY_BY_REGION_BIT", "VK_FENCE_CREATE_SIGNALED_BIT",
    "VK_QUEUE_FAMILY_IGNORED", "VK_REMAINING_MIP_LEVELS",
    "VK_REMAINING_ARRAY_LAYERS",
    "VK_ERROR_OUT_OF_POOL_MEMORY",
    "VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO",
    "VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO",
    "VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO",
    "VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET",
    "VK_STRUCTURE_TYPE_COPY_DESCRIPTOR_SET",
    "VK_DESCRIPTOR_TYPE_SAMPLER", "VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER",
    "VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE", "VK_DESCRIPTOR_TYPE_STORAGE_IMAGE",
    "VK_DESCRIPTOR_TYPE_UNIFORM_TEXEL_BUFFER",
    "VK_DESCRIPTOR_TYPE_STORAGE_TEXEL_BUFFER",
    "VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER", "VK_DESCRIPTOR_TYPE_STORAGE_BUFFER",
    "VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER_DYNAMIC",
    "VK_DESCRIPTOR_TYPE_STORAGE_BUFFER_DYNAMIC",
    "VK_DESCRIPTOR_TYPE_INPUT_ATTACHMENT",
    "VK_DESCRIPTOR_POOL_CREATE_FREE_DESCRIPTOR_SET_BIT",
    "VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT",
}

STRUCTS = {
    "VkExtent2D": (("uint32_t", "width"), ("uint32_t", "height")),
    "VkExtent3D": (("uint32_t", "width"), ("uint32_t", "height"), ("uint32_t", "depth")),
    "VkOffset2D": (("int32_t", "x"), ("int32_t", "y")),
    "VkOffset3D": (("int32_t", "x"), ("int32_t", "y"), ("int32_t", "z")),
    "VkViewport": (("float", "x"), ("float", "y"), ("float", "width"),
                   ("float", "height"), ("float", "minDepth"), ("float", "maxDepth")),
    "VkComponentMapping": (("VkComponentSwizzle", "r"), ("VkComponentSwizzle", "g"),
                           ("VkComponentSwizzle", "b"), ("VkComponentSwizzle", "a")),
    "VkRect2D": (("VkOffset2D", "offset"), ("VkExtent2D", "extent")),
    "VkFormatProperties": (("VkFormatFeatureFlags", "linearTilingFeatures"),
                           ("VkFormatFeatureFlags", "optimalTilingFeatures"),
                           ("VkFormatFeatureFlags", "bufferFeatures")),
    "VkImageFormatProperties": (("VkExtent3D", "maxExtent"),
                                ("uint32_t", "maxMipLevels"),
                                ("uint32_t", "maxArrayLayers"),
                                ("VkSampleCountFlags", "sampleCounts"),
                                ("VkDeviceSize", "maxResourceSize")),
    "VkExtensionProperties": (("char", "extensionName"), ("uint32_t", "specVersion")),
    "VkLayerProperties": (("char", "layerName"), ("uint32_t", "specVersion"),
                          ("uint32_t", "implementationVersion"), ("char", "description")),
    "VkApplicationInfo": (("VkStructureType", "sType"), ("void", "pNext"),
                          ("char", "pApplicationName"), ("uint32_t", "applicationVersion"),
                          ("char", "pEngineName"), ("uint32_t", "engineVersion"),
                          ("uint32_t", "apiVersion")),
    "VkAllocationCallbacks": (("void", "pUserData"),
                              ("PFN_vkAllocationFunction", "pfnAllocation"),
                              ("PFN_vkReallocationFunction", "pfnReallocation"),
                              ("PFN_vkFreeFunction", "pfnFree"),
                              ("PFN_vkInternalAllocationNotification", "pfnInternalAllocation"),
                              ("PFN_vkInternalFreeNotification", "pfnInternalFree")),
    "VkDeviceQueueCreateInfo": (("VkStructureType", "sType"), ("void", "pNext"),
                                ("VkDeviceQueueCreateFlags", "flags"),
                                ("uint32_t", "queueFamilyIndex"),
                                ("uint32_t", "queueCount"), ("float", "pQueuePriorities")),
    "VkPhysicalDeviceFeatures": (
        ("VkBool32", "robustBufferAccess"), ("VkBool32", "fullDrawIndexUint32"),
        ("VkBool32", "imageCubeArray"), ("VkBool32", "independentBlend"),
        ("VkBool32", "geometryShader"), ("VkBool32", "tessellationShader"),
        ("VkBool32", "sampleRateShading"), ("VkBool32", "dualSrcBlend"),
        ("VkBool32", "logicOp"), ("VkBool32", "multiDrawIndirect"),
        ("VkBool32", "drawIndirectFirstInstance"), ("VkBool32", "depthClamp"),
        ("VkBool32", "depthBiasClamp"), ("VkBool32", "fillModeNonSolid"),
        ("VkBool32", "depthBounds"), ("VkBool32", "wideLines"),
        ("VkBool32", "largePoints"), ("VkBool32", "alphaToOne"),
        ("VkBool32", "multiViewport"), ("VkBool32", "samplerAnisotropy"),
        ("VkBool32", "textureCompressionETC2"),
        ("VkBool32", "textureCompressionASTC_LDR"),
        ("VkBool32", "textureCompressionBC"),
        ("VkBool32", "occlusionQueryPrecise"),
        ("VkBool32", "pipelineStatisticsQuery"),
        ("VkBool32", "vertexPipelineStoresAndAtomics"),
        ("VkBool32", "fragmentStoresAndAtomics"),
        ("VkBool32", "shaderTessellationAndGeometryPointSize"),
        ("VkBool32", "shaderImageGatherExtended"),
        ("VkBool32", "shaderStorageImageExtendedFormats"),
        ("VkBool32", "shaderStorageImageMultisample"),
        ("VkBool32", "shaderStorageImageReadWithoutFormat"),
        ("VkBool32", "shaderStorageImageWriteWithoutFormat"),
        ("VkBool32", "shaderUniformBufferArrayDynamicIndexing"),
        ("VkBool32", "shaderSampledImageArrayDynamicIndexing"),
        ("VkBool32", "shaderStorageBufferArrayDynamicIndexing"),
        ("VkBool32", "shaderStorageImageArrayDynamicIndexing"),
        ("VkBool32", "shaderClipDistance"), ("VkBool32", "shaderCullDistance"),
        ("VkBool32", "shaderFloat64"), ("VkBool32", "shaderInt64"),
        ("VkBool32", "shaderInt16"), ("VkBool32", "shaderResourceResidency"),
        ("VkBool32", "shaderResourceMinLod"), ("VkBool32", "sparseBinding"),
        ("VkBool32", "sparseResidencyBuffer"),
        ("VkBool32", "sparseResidencyImage2D"),
        ("VkBool32", "sparseResidencyImage3D"),
        ("VkBool32", "sparseResidency2Samples"),
        ("VkBool32", "sparseResidency4Samples"),
        ("VkBool32", "sparseResidency8Samples"),
        ("VkBool32", "sparseResidency16Samples"),
        ("VkBool32", "sparseResidencyAliased"),
        ("VkBool32", "variableMultisampleRate"),
        ("VkBool32", "inheritedQueries")),
    "VkDeviceCreateInfo": (("VkStructureType", "sType"), ("void", "pNext"),
                           ("VkDeviceCreateFlags", "flags"),
                           ("uint32_t", "queueCreateInfoCount"),
                           ("VkDeviceQueueCreateInfo", "pQueueCreateInfos"),
                           ("uint32_t", "enabledLayerCount"),
                           ("char", "ppEnabledLayerNames"),
                           ("uint32_t", "enabledExtensionCount"),
                           ("char", "ppEnabledExtensionNames"),
                           ("VkPhysicalDeviceFeatures", "pEnabledFeatures")),
    "VkInstanceCreateInfo": (("VkStructureType", "sType"), ("void", "pNext"),
                             ("VkInstanceCreateFlags", "flags"),
                             ("VkApplicationInfo", "pApplicationInfo"),
                             ("uint32_t", "enabledLayerCount"),
                             ("char", "ppEnabledLayerNames"),
                             ("uint32_t", "enabledExtensionCount"),
                             ("char", "ppEnabledExtensionNames")),
    "VkCommandPoolCreateInfo": (("VkStructureType", "sType"), ("void", "pNext"),
                                ("VkCommandPoolCreateFlags", "flags"),
                                ("uint32_t", "queueFamilyIndex")),
    "VkCommandBufferAllocateInfo": (("VkStructureType", "sType"), ("void", "pNext"),
                                    ("VkCommandPool", "commandPool"),
                                    ("VkCommandBufferLevel", "level"),
                                    ("uint32_t", "commandBufferCount")),
    "VkCommandBufferInheritanceInfo": (("VkStructureType", "sType"), ("void", "pNext"),
                                       ("VkRenderPass", "renderPass"),
                                       ("uint32_t", "subpass"),
                                       ("VkFramebuffer", "framebuffer"),
                                       ("VkBool32", "occlusionQueryEnable"),
                                       ("VkQueryControlFlags", "queryFlags"),
                                       ("VkQueryPipelineStatisticFlags", "pipelineStatistics")),
    "VkCommandBufferBeginInfo": (("VkStructureType", "sType"), ("void", "pNext"),
                                 ("VkCommandBufferUsageFlags", "flags"),
                                 ("VkCommandBufferInheritanceInfo", "pInheritanceInfo")),
    "VkSubmitInfo": (("VkStructureType", "sType"), ("void", "pNext"),
                     ("uint32_t", "waitSemaphoreCount"),
                     ("VkSemaphore", "pWaitSemaphores"),
                     ("VkPipelineStageFlags", "pWaitDstStageMask"),
                     ("uint32_t", "commandBufferCount"),
                     ("VkCommandBuffer", "pCommandBuffers"),
                     ("uint32_t", "signalSemaphoreCount"),
                     ("VkSemaphore", "pSignalSemaphores")),
    "VkSemaphoreCreateInfo": (("VkStructureType", "sType"), ("void", "pNext"),
                              ("VkSemaphoreCreateFlags", "flags")),
    "VkMemoryAllocateInfo": (("VkStructureType", "sType"), ("void", "pNext"),
                             ("VkDeviceSize", "allocationSize"),
                             ("uint32_t", "memoryTypeIndex")),
    "VkMemoryRequirements": (("VkDeviceSize", "size"), ("VkDeviceSize", "alignment"),
                             ("uint32_t", "memoryTypeBits")),
    "VkMemoryType": (("VkMemoryPropertyFlags", "propertyFlags"), ("uint32_t", "heapIndex")),
    "VkMemoryHeap": (("VkDeviceSize", "size"), ("VkMemoryHeapFlags", "flags")),
    "VkPhysicalDeviceMemoryProperties": (("uint32_t", "memoryTypeCount"),
                                         ("VkMemoryType", "memoryTypes"),
                                         ("uint32_t", "memoryHeapCount"),
                                         ("VkMemoryHeap", "memoryHeaps")),
    "VkQueueFamilyProperties": (("VkQueueFlags", "queueFlags"), ("uint32_t", "queueCount"),
                                ("uint32_t", "timestampValidBits"),
                                ("VkExtent3D", "minImageTransferGranularity")),
    "VkImageCreateInfo": (("VkStructureType", "sType"), ("void", "pNext"),
                          ("VkImageCreateFlags", "flags"), ("VkImageType", "imageType"),
                          ("VkFormat", "format"), ("VkExtent3D", "extent"),
                          ("uint32_t", "mipLevels"), ("uint32_t", "arrayLayers"),
                          ("VkSampleCountFlagBits", "samples"), ("VkImageTiling", "tiling"),
                          ("VkImageUsageFlags", "usage"), ("VkSharingMode", "sharingMode"),
                          ("uint32_t", "queueFamilyIndexCount"),
                          ("uint32_t", "pQueueFamilyIndices"),
                          ("VkImageLayout", "initialLayout")),
    "VkImageSubresourceRange": (("VkImageAspectFlags", "aspectMask"),
                                ("uint32_t", "baseMipLevel"), ("uint32_t", "levelCount"),
                                ("uint32_t", "baseArrayLayer"), ("uint32_t", "layerCount")),
    "VkImageSubresource": (("VkImageAspectFlags", "aspectMask"),
                           ("uint32_t", "mipLevel"), ("uint32_t", "arrayLayer")),
    "VkSubresourceLayout": (("VkDeviceSize", "offset"), ("VkDeviceSize", "size"),
                            ("VkDeviceSize", "rowPitch"), ("VkDeviceSize", "arrayPitch"),
                            ("VkDeviceSize", "depthPitch")),
    "VkMappedMemoryRange": (("VkStructureType", "sType"), ("void", "pNext"),
                            ("VkDeviceMemory", "memory"), ("VkDeviceSize", "offset"),
                            ("VkDeviceSize", "size")),
    "VkImageMemoryBarrier": (("VkStructureType", "sType"), ("void", "pNext"),
                             ("VkAccessFlags", "srcAccessMask"),
                             ("VkAccessFlags", "dstAccessMask"),
                             ("VkImageLayout", "oldLayout"), ("VkImageLayout", "newLayout"),
                             ("uint32_t", "srcQueueFamilyIndex"),
                             ("uint32_t", "dstQueueFamilyIndex"), ("VkImage", "image"),
                             ("VkImageSubresourceRange", "subresourceRange")),
    "VkFenceCreateInfo": (("VkStructureType", "sType"), ("void", "pNext"),
                          ("VkFenceCreateFlags", "flags")),
    "VkSamplerCreateInfo": (
        ("VkStructureType", "sType"), ("void", "pNext"),
        ("VkSamplerCreateFlags", "flags"), ("VkFilter", "magFilter"),
        ("VkFilter", "minFilter"), ("VkSamplerMipmapMode", "mipmapMode"),
        ("VkSamplerAddressMode", "addressModeU"),
        ("VkSamplerAddressMode", "addressModeV"),
        ("VkSamplerAddressMode", "addressModeW"), ("float", "mipLodBias"),
        ("VkBool32", "anisotropyEnable"), ("float", "maxAnisotropy"),
        ("VkBool32", "compareEnable"), ("VkCompareOp", "compareOp"),
        ("float", "minLod"), ("float", "maxLod"),
        ("VkBorderColor", "borderColor"), ("VkBool32", "unnormalizedCoordinates")),
}

# The graphics pipeline structures, added 2026-09-11. Written out here by
# hand, from the registry, so that this file and vk_core_1_0.pbi are two
# independent transcriptions of one layout and a typo in either is a
# failure rather than a silent agreement.
STRUCTS.update({
    "VkShaderModuleCreateInfo": (
        ("VkStructureType", "sType"), ("void", "pNext"),
        ("VkShaderModuleCreateFlags", "flags"), ("size_t", "codeSize"),
        ("uint32_t", "pCode")),
    "VkSpecializationMapEntry": (
        ("uint32_t", "constantID"), ("uint32_t", "offset"), ("size_t", "size")),
    "VkSpecializationInfo": (
        ("uint32_t", "mapEntryCount"), ("VkSpecializationMapEntry", "pMapEntries"),
        ("size_t", "dataSize"), ("void", "pData")),
    "VkPipelineShaderStageCreateInfo": (
        ("VkStructureType", "sType"), ("void", "pNext"),
        ("VkPipelineShaderStageCreateFlags", "flags"),
        ("VkShaderStageFlagBits", "stage"), ("VkShaderModule", "module"),
        ("char", "pName"), ("VkSpecializationInfo", "pSpecializationInfo")),
    "VkVertexInputBindingDescription": (
        ("uint32_t", "binding"), ("uint32_t", "stride"),
        ("VkVertexInputRate", "inputRate")),
    "VkVertexInputAttributeDescription": (
        ("uint32_t", "location"), ("uint32_t", "binding"),
        ("VkFormat", "format"), ("uint32_t", "offset")),
    "VkPipelineVertexInputStateCreateInfo": (
        ("VkStructureType", "sType"), ("void", "pNext"),
        ("VkPipelineVertexInputStateCreateFlags", "flags"),
        ("uint32_t", "vertexBindingDescriptionCount"),
        ("VkVertexInputBindingDescription", "pVertexBindingDescriptions"),
        ("uint32_t", "vertexAttributeDescriptionCount"),
        ("VkVertexInputAttributeDescription", "pVertexAttributeDescriptions")),
    "VkPipelineInputAssemblyStateCreateInfo": (
        ("VkStructureType", "sType"), ("void", "pNext"),
        ("VkPipelineInputAssemblyStateCreateFlags", "flags"),
        ("VkPrimitiveTopology", "topology"), ("VkBool32", "primitiveRestartEnable")),
    "VkPipelineViewportStateCreateInfo": (
        ("VkStructureType", "sType"), ("void", "pNext"),
        ("VkPipelineViewportStateCreateFlags", "flags"),
        ("uint32_t", "viewportCount"), ("VkViewport", "pViewports"),
        ("uint32_t", "scissorCount"), ("VkRect2D", "pScissors")),
    "VkPipelineRasterizationStateCreateInfo": (
        ("VkStructureType", "sType"), ("void", "pNext"),
        ("VkPipelineRasterizationStateCreateFlags", "flags"),
        ("VkBool32", "depthClampEnable"), ("VkBool32", "rasterizerDiscardEnable"),
        ("VkPolygonMode", "polygonMode"), ("VkCullModeFlags", "cullMode"),
        ("VkFrontFace", "frontFace"), ("VkBool32", "depthBiasEnable"),
        ("float", "depthBiasConstantFactor"), ("float", "depthBiasClamp"),
        ("float", "depthBiasSlopeFactor"), ("float", "lineWidth")),
    "VkPipelineMultisampleStateCreateInfo": (
        ("VkStructureType", "sType"), ("void", "pNext"),
        ("VkPipelineMultisampleStateCreateFlags", "flags"),
        ("VkSampleCountFlagBits", "rasterizationSamples"),
        ("VkBool32", "sampleShadingEnable"), ("float", "minSampleShading"),
        ("VkSampleMask", "pSampleMask"), ("VkBool32", "alphaToCoverageEnable"),
        ("VkBool32", "alphaToOneEnable")),
    "VkPipelineColorBlendAttachmentState": (
        ("VkBool32", "blendEnable"), ("VkBlendFactor", "srcColorBlendFactor"),
        ("VkBlendFactor", "dstColorBlendFactor"), ("VkBlendOp", "colorBlendOp"),
        ("VkBlendFactor", "srcAlphaBlendFactor"),
        ("VkBlendFactor", "dstAlphaBlendFactor"), ("VkBlendOp", "alphaBlendOp"),
        ("VkColorComponentFlags", "colorWriteMask")),
    "VkPipelineColorBlendStateCreateInfo": (
        ("VkStructureType", "sType"), ("void", "pNext"),
        ("VkPipelineColorBlendStateCreateFlags", "flags"),
        ("VkBool32", "logicOpEnable"), ("VkLogicOp", "logicOp"),
        ("uint32_t", "attachmentCount"),
        ("VkPipelineColorBlendAttachmentState", "pAttachments"),
        ("float", "blendConstants")),
    "VkPushConstantRange": (
        ("VkShaderStageFlags", "stageFlags"), ("uint32_t", "offset"),
        ("uint32_t", "size")),
    "VkPipelineLayoutCreateInfo": (
        ("VkStructureType", "sType"), ("void", "pNext"),
        ("VkPipelineLayoutCreateFlags", "flags"), ("uint32_t", "setLayoutCount"),
        ("VkDescriptorSetLayout", "pSetLayouts"),
        ("uint32_t", "pushConstantRangeCount"),
        ("VkPushConstantRange", "pPushConstantRanges")),
    "VkGraphicsPipelineCreateInfo": (
        ("VkStructureType", "sType"), ("void", "pNext"),
        ("VkPipelineCreateFlags", "flags"), ("uint32_t", "stageCount"),
        ("VkPipelineShaderStageCreateInfo", "pStages"),
        ("VkPipelineVertexInputStateCreateInfo", "pVertexInputState"),
        ("VkPipelineInputAssemblyStateCreateInfo", "pInputAssemblyState"),
        ("VkPipelineTessellationStateCreateInfo", "pTessellationState"),
        ("VkPipelineViewportStateCreateInfo", "pViewportState"),
        ("VkPipelineRasterizationStateCreateInfo", "pRasterizationState"),
        ("VkPipelineMultisampleStateCreateInfo", "pMultisampleState"),
        ("VkPipelineDepthStencilStateCreateInfo", "pDepthStencilState"),
        ("VkPipelineColorBlendStateCreateInfo", "pColorBlendState"),
        ("VkPipelineDynamicStateCreateInfo", "pDynamicState"),
        ("VkPipelineLayout", "layout"), ("VkRenderPass", "renderPass"),
        ("uint32_t", "subpass"), ("VkPipeline", "basePipelineHandle"),
        ("int32_t", "basePipelineIndex")),
    "VkAttachmentDescription": (
        ("VkAttachmentDescriptionFlags", "flags"), ("VkFormat", "format"),
        ("VkSampleCountFlagBits", "samples"), ("VkAttachmentLoadOp", "loadOp"),
        ("VkAttachmentStoreOp", "storeOp"), ("VkAttachmentLoadOp", "stencilLoadOp"),
        ("VkAttachmentStoreOp", "stencilStoreOp"),
        ("VkImageLayout", "initialLayout"), ("VkImageLayout", "finalLayout")),
    "VkAttachmentReference": (
        ("uint32_t", "attachment"), ("VkImageLayout", "layout")),
    "VkSubpassDescription": (
        ("VkSubpassDescriptionFlags", "flags"),
        ("VkPipelineBindPoint", "pipelineBindPoint"),
        ("uint32_t", "inputAttachmentCount"),
        ("VkAttachmentReference", "pInputAttachments"),
        ("uint32_t", "colorAttachmentCount"),
        ("VkAttachmentReference", "pColorAttachments"),
        ("VkAttachmentReference", "pResolveAttachments"),
        ("VkAttachmentReference", "pDepthStencilAttachment"),
        ("uint32_t", "preserveAttachmentCount"),
        ("uint32_t", "pPreserveAttachments")),
    "VkSubpassDependency": (
        ("uint32_t", "srcSubpass"), ("uint32_t", "dstSubpass"),
        ("VkPipelineStageFlags", "srcStageMask"),
        ("VkPipelineStageFlags", "dstStageMask"),
        ("VkAccessFlags", "srcAccessMask"), ("VkAccessFlags", "dstAccessMask"),
        ("VkDependencyFlags", "dependencyFlags")),
    "VkRenderPassCreateInfo": (
        ("VkStructureType", "sType"), ("void", "pNext"),
        ("VkRenderPassCreateFlags", "flags"), ("uint32_t", "attachmentCount"),
        ("VkAttachmentDescription", "pAttachments"), ("uint32_t", "subpassCount"),
        ("VkSubpassDescription", "pSubpasses"), ("uint32_t", "dependencyCount"),
        ("VkSubpassDependency", "pDependencies")),
    "VkImageViewCreateInfo": (
        ("VkStructureType", "sType"), ("void", "pNext"),
        ("VkImageViewCreateFlags", "flags"), ("VkImage", "image"),
        ("VkImageViewType", "viewType"), ("VkFormat", "format"),
        ("VkComponentMapping", "components"),
        ("VkImageSubresourceRange", "subresourceRange")),
    "VkFramebufferCreateInfo": (
        ("VkStructureType", "sType"), ("void", "pNext"),
        ("VkFramebufferCreateFlags", "flags"), ("VkRenderPass", "renderPass"),
        ("uint32_t", "attachmentCount"), ("VkImageView", "pAttachments"),
        ("uint32_t", "width"), ("uint32_t", "height"), ("uint32_t", "layers")),
    "VkRenderPassBeginInfo": (
        ("VkStructureType", "sType"), ("void", "pNext"),
        ("VkRenderPass", "renderPass"), ("VkFramebuffer", "framebuffer"),
        ("VkRect2D", "renderArea"), ("uint32_t", "clearValueCount"),
        ("VkClearValue", "pClearValues")),
    "VkBufferCreateInfo": (
        ("VkStructureType", "sType"), ("void", "pNext"),
        ("VkBufferCreateFlags", "flags"), ("VkDeviceSize", "size"),
        ("VkBufferUsageFlags", "usage"), ("VkSharingMode", "sharingMode"),
        ("uint32_t", "queueFamilyIndexCount"), ("uint32_t", "pQueueFamilyIndices")),
})

PB_SUFFIX = {
    "uint32_t": ".l", "int32_t": ".l", "VkBool32": ".l",
    "VkComponentSwizzle": ".l", "VkStructureType": ".l",
    "VkDeviceQueueCreateFlags": ".l", "VkDeviceCreateFlags": ".l",
    "VkInstanceCreateFlags": ".l", "VkCommandPoolCreateFlags": ".l",
    "VkCommandBufferLevel": ".l", "VkQueryControlFlags": ".l",
    "VkQueryPipelineStatisticFlags": ".l", "VkCommandBufferUsageFlags": ".l",
    "VkPipelineStageFlags": ".l", "float": ".f",
    "VkImageCreateFlags": ".l", "VkImageType": ".l", "VkFormat": ".l",
    "VkSampleCountFlagBits": ".l", "VkImageTiling": ".l",
    "VkImageUsageFlags": ".l", "VkSharingMode": ".l", "VkImageLayout": ".l",
    "VkImageAspectFlags": ".l", "VkAccessFlags": ".l",
    "VkFormatFeatureFlags": ".l",
    "VkSampleCountFlags": ".l",
    "VkMemoryPropertyFlags": ".l", "VkMemoryHeapFlags": ".l",
    "VkQueueFlags": ".l", "VkFenceCreateFlags": ".l", "VkSemaphoreCreateFlags": ".l",
    "VkDeviceSize": ".q", "uint64_t": ".q",
    "VkCommandPool": ".i", "VkRenderPass": ".i", "VkFramebuffer": ".i",
    "VkSemaphore": ".i", "VkCommandBuffer": ".i", "VkImage": ".i",
    "VkDeviceMemory": ".i", "VkFence": ".i",
    "VkOffset2D": ".VkOffset2D", "VkExtent2D": ".VkExtent2D",
    "VkExtent3D": ".VkExtent3D",
    "VkImageSubresourceRange": ".VkImageSubresourceRange",
    "VkMemoryType": ".VkMemoryType", "VkMemoryHeap": ".VkMemoryHeap",
    # The graphics pipeline vocabulary, added 2026-09-11. size_t is the
    # target's own width, which is what PureMetal's .i is.
    "size_t": ".i",
    "VkShaderModuleCreateFlags": ".l", "VkPipelineShaderStageCreateFlags": ".l",
    "VkShaderStageFlagBits": ".l", "VkShaderStageFlags": ".l",
    "VkShaderModule": ".i", "VkPipelineLayout": ".i", "VkPipeline": ".i",
    "VkImageView": ".i", "VkDescriptorSetLayout": ".i",
    "VkVertexInputRate": ".l",
    "VkPipelineVertexInputStateCreateFlags": ".l",
    "VkPipelineInputAssemblyStateCreateFlags": ".l",
    "VkPrimitiveTopology": ".l",
    "VkPipelineViewportStateCreateFlags": ".l",
    "VkPipelineRasterizationStateCreateFlags": ".l",
    "VkPolygonMode": ".l", "VkCullModeFlags": ".l", "VkFrontFace": ".l",
    "VkPipelineMultisampleStateCreateFlags": ".l", "VkSampleMask": ".l",
    "VkPipelineColorBlendStateCreateFlags": ".l",
    "VkBlendFactor": ".l", "VkBlendOp": ".l", "VkLogicOp": ".l",
    "VkColorComponentFlags": ".l",
    "VkPipelineLayoutCreateFlags": ".l", "VkPipelineCreateFlags": ".l",
    "VkAttachmentDescriptionFlags": ".l", "VkAttachmentLoadOp": ".l",
    "VkAttachmentStoreOp": ".l", "VkSubpassDescriptionFlags": ".l",
    "VkPipelineBindPoint": ".l", "VkRenderPassCreateFlags": ".l",
    "VkDependencyFlags": ".l",
    "VkImageViewCreateFlags": ".l", "VkImageViewType": ".l",
    "VkFramebufferCreateFlags": ".l", "VkBufferCreateFlags": ".l",
    "VkBufferUsageFlags": ".l",
    "VkComponentMapping": ".VkComponentMapping", "VkRect2D": ".VkRect2D",
    # The descriptor vocabulary, added 2026-09-11 with the first
    # descriptor type. VkSampler and VkBufferView appear only as pointer
    # members of structures this implementation refuses to fill, so they
    # are here to be REFUSED with a name rather than to be supported.
    "VkDescriptorType": ".l", "VkDescriptorSetLayoutCreateFlags": ".l",
    "VkDescriptorPoolCreateFlags": ".l",
    "VkDescriptorPool": ".i", "VkDescriptorSet": ".i",
    "VkSampler": ".i", "VkBufferView": ".i", "VkBuffer": ".i",
    "VkSamplerCreateFlags": ".l", "VkFilter": ".l",
    "VkSamplerMipmapMode": ".l", "VkSamplerAddressMode": ".l",
    "VkCompareOp": ".l", "VkBorderColor": ".l",
}

# The descriptor structures, added 2026-09-11 with the first descriptor
# type. Written out here by hand, from the registry, for the same reason
# the pipeline block above is: this file and vk_core_1_0.pbi have to be
# two independent transcriptions of one layout, so a typo in either is a
# failure rather than a silent agreement.
#
# VK_WHOLE_SIZE is deliberately NOT in CONSTANTS. The registry writes it
# (~0ULL) and the vocabulary declares it -1, which is the same sixty-four
# bits and is what a VkDeviceSize field holding it reads back as on this
# part - but the two spellings are not the same NUMBER, and a check that
# had to special-case one constant would be a check nobody trusts.
STRUCTS.update({
    "VkDescriptorSetLayoutBinding": (
        ("uint32_t", "binding"), ("VkDescriptorType", "descriptorType"),
        ("uint32_t", "descriptorCount"), ("VkShaderStageFlags", "stageFlags"),
        ("VkSampler", "pImmutableSamplers")),
    "VkDescriptorSetLayoutCreateInfo": (
        ("VkStructureType", "sType"), ("void", "pNext"),
        ("VkDescriptorSetLayoutCreateFlags", "flags"),
        ("uint32_t", "bindingCount"),
        ("VkDescriptorSetLayoutBinding", "pBindings")),
    "VkDescriptorPoolSize": (
        ("VkDescriptorType", "type"), ("uint32_t", "descriptorCount")),
    "VkDescriptorPoolCreateInfo": (
        ("VkStructureType", "sType"), ("void", "pNext"),
        ("VkDescriptorPoolCreateFlags", "flags"), ("uint32_t", "maxSets"),
        ("uint32_t", "poolSizeCount"), ("VkDescriptorPoolSize", "pPoolSizes")),
    "VkDescriptorSetAllocateInfo": (
        ("VkStructureType", "sType"), ("void", "pNext"),
        ("VkDescriptorPool", "descriptorPool"),
        ("uint32_t", "descriptorSetCount"),
        ("VkDescriptorSetLayout", "pSetLayouts")),
    "VkDescriptorBufferInfo": (
        ("VkBuffer", "buffer"), ("VkDeviceSize", "offset"),
        ("VkDeviceSize", "range")),
    "VkDescriptorImageInfo": (
        ("VkSampler", "sampler"), ("VkImageView", "imageView"),
        ("VkImageLayout", "imageLayout")),
    "VkWriteDescriptorSet": (
        ("VkStructureType", "sType"), ("void", "pNext"),
        ("VkDescriptorSet", "dstSet"), ("uint32_t", "dstBinding"),
        ("uint32_t", "dstArrayElement"), ("uint32_t", "descriptorCount"),
        ("VkDescriptorType", "descriptorType"),
        ("VkDescriptorImageInfo", "pImageInfo"),
        ("VkDescriptorBufferInfo", "pBufferInfo"),
        ("VkBufferView", "pTexelBufferView")),
    "VkCopyDescriptorSet": (
        ("VkStructureType", "sType"), ("void", "pNext"),
        ("VkDescriptorSet", "srcSet"), ("uint32_t", "srcBinding"),
        ("uint32_t", "srcArrayElement"), ("VkDescriptorSet", "dstSet"),
        ("uint32_t", "dstBinding"), ("uint32_t", "dstArrayElement"),
        ("uint32_t", "descriptorCount")),
})


# The registry writes its all-ones sentinels as C expressions.
C_SENTINELS = {"(~0U)": 0xFFFFFFFF, "(~0ULL)": 0xFFFFFFFFFFFFFFFF, "(~0U-1)": 0xFFFFFFFE}


def registry_path() -> pathlib.Path:
    value = os.environ.get("VULKAN_REGISTRY")
    if not value:
        raise SystemExit("set VULKAN_REGISTRY to pinned v1.4.350 registry/vk.xml")
    path = pathlib.Path(value)
    if not path.is_file():
        raise SystemExit("VULKAN_REGISTRY does not name a file: %s" % path)
    return path


def number(node: ET.Element, by_name: dict[str, ET.Element]) -> int:
    value = node.get("value")
    if value is not None:
        if value in C_SENTINELS:
            return C_SENTINELS[value]
        return int(value, 0)
    if node.get("bitpos") is not None:
        return 1 << int(node.get("bitpos"))
    alias = node.get("alias")
    if alias:
        return number(by_name[alias], by_name)
    # AN EXTENSION-NUMBERED ENUMERANT. A value promoted into core from an
    # extension keeps the extension's arithmetic in the registry rather
    # than a literal: base + (extension number - 1) * block + offset,
    # negated when dir is "-". VK_ERROR_OUT_OF_POOL_MEMORY is the first
    # such value this vocabulary needs, and computing it here is the only
    # way this gate can check it against the registry at all. The three
    # constants are the registry's own reservation scheme.
    offset = node.get("offset")
    if offset is not None and node.get("extnumber_resolved") is not None:
        extension = int(node.get("extnumber_resolved"))
        magnitude = 1000000000 + (extension - 1) * 1000 + int(offset)
        return -magnitude if node.get("dir") == "-" else magnitude
    raise ValueError("no core value for " + str(node.get("name")))


def parse_pbi_constants() -> dict[str, int]:
    found = {}
    for line in VOCAB.read_text(encoding="utf-8").splitlines():
        match = re.match(r"#(VK_[A-Z0-9_]+)\s*=\s*([^\s;]+)", line)
        if match:
            token = match.group(2)
            found[match.group(1)] = int(token[1:], 16) if token.startswith("$") else int(token)
    return found


def parse_pbi_structs() -> dict[str, tuple[str, ...]]:
    found: dict[str, tuple[str, ...]] = {}
    current = None
    members: list[str] = []
    for source_line in VOCAB.read_text(encoding="utf-8").splitlines():
        line = source_line.strip()
        match = re.fullmatch(r"Structure\s+(Vk\w+)\s+Align\s+#PB_Structure_AlignC", line)
        if match:
            current = match.group(1)
            members = []
        elif line == "EndStructure" and current:
            found[current] = tuple(members)
            current = None
        elif current and line and not line.startswith(";"):
            members.append(line)
    return found


def members(node):
    """The members of a structure AS THIS API SEES THEM.

    vk.xml carries Vulkan SC variants of some members side by side with
    the Vulkan ones, distinguished only by an `api` attribute - and
    VkGraphicsPipelineCreateInfo.pStages is one of them. Taking every
    <member> would give a structure two of it, so the wrong count is
    compared against the right one and a correct declaration fails.
    """
    out = []
    for m in node.findall("member"):
        api = m.get("api")
        if api is None or "vulkan" in api.split(","):
            out.append(m)
    return out


def expected_pbi_member(member: ET.Element) -> str:
    c_type = member.findtext("type")
    name = member.findtext("name")
    raw = "".join(member.itertext())
    if "*" in raw or c_type.startswith("PFN_"):
        return "*" + name
    # A LITERAL array extent. `float blendConstants[4]` carries its
    # extent in the member's own text and not as an <enum>, so the
    # branch below would silently expect a scalar and a four-element
    # array would pass as one float.
    if raw.endswith("]") and member.findtext("enum") is None:
        extent = raw[raw.rindex("[") + 1:-1]
        try:
            return "%s%s[%s]" % (name, PB_SUFFIX[c_type], extent)
        except KeyError as exc:
            raise ValueError("no expected PureMetal mapping for array of " + c_type) from exc
    enum = member.findtext("enum")
    if enum:
        # A fixed array keeps the registry's own extent constant, so a
        # changed VK_MAX_MEMORY_TYPES cannot be missed by this gate.
        if c_type == "char":
            return "%s.a[#%s]" % (name, enum)
        try:
            return "%s%s[#%s]" % (name, PB_SUFFIX[c_type], enum)
        except KeyError as exc:
            raise ValueError("no expected PureMetal mapping for array of " + c_type) from exc
    try:
        return name + PB_SUFFIX[c_type]
    except KeyError as exc:
        raise ValueError("no expected PureMetal mapping for " + c_type) from exc


def check_registry(failures: list[str]) -> int:
    path = registry_path()
    # A Windows Git checkout may transport the pinned XML with CRLF. Pin the
    # registry content after normalizing that one reversible checkout detail,
    # exactly as the dispatch inventory gate does; no XML node is rewritten.
    registry_bytes = path.read_bytes().replace(b"\r\n", b"\n")
    digest = hashlib.sha256(registry_bytes).hexdigest()
    if digest != REGISTRY_SHA256:
        failures.append("registry SHA-256 %s, wanted %s" % (digest, REGISTRY_SHA256))
        return 1
    root = ET.fromstring(registry_bytes)
    enums = {}
    for enum in root.findall(".//enum"):
        name = enum.get("name")
        if not name:
            continue
        if any(enum.get(key) is not None for key in ("value", "bitpos", "alias")):
            enums[name] = enum
    # AN ENUMERANT PROMOTED INTO CORE FROM AN EXTENSION keeps the
    # extension's arithmetic in the registry rather than a literal value,
    # and it appears in TWO places: inside the extension's own block,
    # where the number is on the <extension> element, and inside a
    # <feature> block's "Promoted from ..." require, where the <enum>
    # carries its own extnumber. Both are collected, the extension one
    # first so a feature block's copy cannot be missed.
    for extension in root.findall("./extensions/extension"):
        extnumber = extension.get("number")
        if not extnumber:
            continue
        for enum in extension.findall(".//enum"):
            name = enum.get("name")
            if not name or name in enums or enum.get("offset") is None:
                continue
            enum.set("extnumber_resolved", enum.get("extnumber") or extnumber)
            enums[name] = enum
    for enum in root.iter("enum"):
        name = enum.get("name")
        if not name or name in enums:
            continue
        if enum.get("offset") is None or enum.get("extnumber") is None:
            continue
        enum.set("extnumber_resolved", enum.get("extnumber"))
        enums[name] = enum
    pbi = parse_pbi_constants()
    checks = 1
    if pbi.get("VK_API_VERSION_1_0") != 0x00400000:
        failures.append("VK_API_VERSION_1_0 is not 1.0.0")
    if pbi.get("VK_HEADER_VERSION") != 350:
        failures.append("VK_HEADER_VERSION is not 350")
    if pbi.get("VK_HEADER_VERSION_COMPLETE") != 0x0040415E:
        failures.append("VK_HEADER_VERSION_COMPLETE is not 1.4.350")
    checks += 3
    for name in sorted(CONSTANTS):
        if name not in enums:
            failures.append("registry has no " + name)
        elif name not in pbi:
            failures.append("vocabulary has no " + name)
        else:
            want = number(enums[name], enums)
            if pbi[name] != want:
                failures.append("%s=%d, registry says %d" % (name, pbi[name], want))
        checks += 1
    types = {t.get("name"): t for t in root.findall("./types/type") if t.get("name")}
    pbi_structs = parse_pbi_structs()
    for name, want in STRUCTS.items():
        node = types.get(name)
        if node is None:
            failures.append("registry has no structure " + name)
        else:
            got = tuple((m.findtext("type"), m.findtext("name")) for m in members(node))
            if got != want:
                failures.append("%s members %r, wanted %r" % (name, got, want))
            expected_decl = tuple(expected_pbi_member(m) for m in members(node))
            if pbi_structs.get(name) != expected_decl:
                failures.append("%s declaration %r, registry requires %r" %
                                (name, pbi_structs.get(name), expected_decl))
        checks += 2
    # Anvil declares no Vulkan union, and must not: PureMetal has no
    # union, and one arm of VkClearColorValue masquerading as the whole
    # type is exactly the silent wrong answer this project refuses.
    if "VkClearColorValue" in pbi_structs:
        failures.append("vk_core_1_0.pbi declares VkClearColorValue as a structure; it is a union")
    checks += 1
    return checks


def locate(name: str, local: pathlib.Path) -> pathlib.Path:
    value = os.environ.get(name)
    if value and pathlib.Path(value).is_file():
        return pathlib.Path(value)
    if local.is_file():
        return local
    raise SystemExit("set %s or provide %s" % (name, local))


def build(probe: pathlib.Path, output_name: str) -> pathlib.Path:
    compiler = locate("PMF_COMPILER", ROOT / "PureMetalForge.exe")
    image = pathlib.Path(tempfile.gettempdir()) / output_name
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    run = subprocess.run(
        [str(compiler), "--compile", str(probe.relative_to(ROOT)).replace("\\", "/"),
         "-t", "pi4", "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
         "--entry-returns", "-o", str(image), "-s"],
        cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise SystemExit("Vulkan foundation build failed\n" + run.stdout)
    return image


def run_image(image: pathlib.Path):
    interp = locate("PMF_A64_INTERP", ROOT / "tools" / "a64" / "a64_interp.py")
    spec = importlib.util.spec_from_file_location("anvil_vk_a64", interp)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    cpu = module.A64()
    for i, byte in enumerate(image.read_bytes()):
        cpu.memory[LOAD + i] = byte
    module.attach_symbols(cpu, image, LOAD)
    cpu.pc, cpu.sp, cpu.x[30] = LOAD, STACK, RETURN

    # AN MMIO HARD STOP. Neither of these probes may touch hardware: one
    # links the test backend and one links no backend at all.
    def guard(addr: int, write: bool) -> None:
        if addr >= MMIO:
            kind = "write" if write else "read"
            raise SystemExit(
                "vulkan_foundation_check: unexpected MMIO %s at $%08X - this probe "
                "is supposed to touch no hardware at all" % (kind, addr))

    def load(addr: int, size: int) -> int:
        cpu.align_guard(addr, size, False)
        guard(addr, False)
        return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr: int, value: int, size: int) -> None:
        cpu.align_guard(addr, size, True)
        guard(addr, True)
        for i in range(size):
            cpu.memory[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    for steps in range(20_000_000):
        if cpu.pc == RETURN:
            return cpu, cpu.x[0], steps
        cpu.step()
    raise SystemExit("Vulkan foundation probe did not return")


def u64(cpu, addr: int) -> int:
    return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(8))


def queue_capability_mutation() -> tuple[bool, str]:
    """Remove GRAPHICS advertisement and require the public probe to notice.

    This mutates the capability owner, not the test backend. The source is
    restored in a finally block even when compilation or interpretation fails.
    Run it only on request because it temporarily rewrites a shared source file.
    """
    fixed = """  If (avkBackendCaps() & #ANVIL_VK_CAP_DRAW) <> 0
    *pQueueFamilyProperties\\queueFlags = *pQueueFamilyProperties\\queueFlags | #VK_QUEUE_GRAPHICS_BIT
  EndIf
"""
    broken = """  ; MUTANT: a draw-capable backend falsely advertises no graphics queue.
"""
    original = API.read_text(encoding="utf-8")
    if original.count(fixed) != 1:
        return False, "queue-capability mutation anchor is stale"
    try:
        API.write_text(original.replace(fixed, broken), encoding="utf-8")
        cpu, rc, _ = run_image(build(PROBE, "anvil_vk_foundation_queue_mutant.img"))
        count = u64(cpu, OUT + 8)
        failures = u64(cpu, OUT + 16)
        failed_rows = [i + 1 for i in range(count)
                       if u64(cpu, OUT + 0x100 + i * 8) == 0]
        if rc == 0 or failures == 0:
            return False, "removing GRAPHICS stayed green"
        return True, "removing GRAPHICS was rejected at emitted rows " + ",".join(map(str, failed_rows))
    finally:
        API.write_text(original, encoding="utf-8")


def feature_mutations() -> list[tuple[str, bool, str]]:
    """Require query zeroing, all-false acceptance and a complete enable scan."""
    mutants = (
        ("the feature query reports a true bit",
         "    PokeL(*pFeatures + i, #VK_FALSE)\n",
         "    PokeL(*pFeatures + i, #VK_TRUE)\n"),
        ("a non-null all-false feature record is refused",
         "  If avkFeaturesAllFalse(*pCreateInfo\\pEnabledFeatures) = 0\n",
         "  If *pCreateInfo\\pEnabledFeatures <> 0\n"),
        ("only the first feature bit is checked",
         "Procedure.i avkFeaturesAllFalse(*pFeatures.VkPhysicalDeviceFeatures)\n  Define i.i\n  If *pFeatures = 0 : ProcedureReturn 1 : EndIf\n  i = 0\n  While i < SizeOf(VkPhysicalDeviceFeatures)\n",
         "Procedure.i avkFeaturesAllFalse(*pFeatures.VkPhysicalDeviceFeatures)\n  Define i.i\n  If *pFeatures = 0 : ProcedureReturn 1 : EndIf\n  i = 0\n  While i < 4\n"),
    )
    original = API.read_text(encoding="utf-8")
    results = []
    for name, fixed, broken in mutants:
        if original.count(fixed) != 1:
            results.append((name, False, "mutation anchor is stale"))
            continue
        try:
            API.write_text(original.replace(fixed, broken, 1), encoding="utf-8")
            cpu, rc, _ = run_image(build(PROBE, "anvil_vk_foundation_feature_mutant.img"))
            count = u64(cpu, OUT + 8)
            failures = u64(cpu, OUT + 16)
            failed_rows = [i + 1 for i in range(count)
                           if u64(cpu, OUT + 0x100 + i * 8) == 0]
            caught = rc != 0 and failures != 0
            detail = ("rejected at emitted rows " + ",".join(map(str, failed_rows))
                      if caught else "stayed green")
            results.append((name, caught, detail))
        finally:
            API.write_text(original, encoding="utf-8")
    return results


def format_mutations() -> list[tuple[str, bool, str]]:
    """Require exact format output and backend-derived attachment support."""
    mutants = (
        ("linear BGRA8 falsely advertises storage-image support",
         "      *pFormatProperties\\linearTilingFeatures = *pFormatProperties\\linearTilingFeatures | #VK_FORMAT_FEATURE_COLOR_ATTACHMENT_BIT\n",
         "      *pFormatProperties\\linearTilingFeatures = *pFormatProperties\\linearTilingFeatures | #VK_FORMAT_FEATURE_COLOR_ATTACHMENT_BIT | $2\n"),
        ("linear BGRA8 falsely advertises depth-stencil support",
         "      *pFormatProperties\\linearTilingFeatures = *pFormatProperties\\linearTilingFeatures | #VK_FORMAT_FEATURE_COLOR_ATTACHMENT_BIT\n",
         "      *pFormatProperties\\linearTilingFeatures = *pFormatProperties\\linearTilingFeatures | #VK_FORMAT_FEATURE_COLOR_ATTACHMENT_BIT | $200\n"),
        ("a draw-only backend falsely advertises color-attachment blending",
         "    If AnvilVkBackendCanBlendSourceOver() <> 0\n",
         "    If AnvilVkBackendCanBlendSourceOver() >= 0\n"),
        ("a blend-capable backend omits color-attachment blending",
         "      *pFormatProperties\\linearTilingFeatures = *pFormatProperties\\linearTilingFeatures | #VK_FORMAT_FEATURE_COLOR_ATTACHMENT_BLEND_BIT\n",
         "      *pFormatProperties\\linearTilingFeatures = *pFormatProperties\\linearTilingFeatures | 0\n"),
        ("BGRA8 falsely advertises optimal-tiling support",
         "  *pFormatProperties\\optimalTilingFeatures = 0\n",
         "  *pFormatProperties\\optimalTilingFeatures = #VK_FORMAT_FEATURE_COLOR_ATTACHMENT_BIT\n"),
        ("an unsupported format inherits BGRA8 support",
         "  If format = #VK_FORMAT_B8G8R8A8_UNORM\n",
         "  If format >= 0\n"),
        ("a transfer-only backend advertises a color attachment",
         "    If AnvilVkBackendCanDraw() <> 0\n",
         "    If AnvilVkBackendCanDraw() >= 0\n"),
        ("a stale physical-device handle is accepted by the format query",
         "Procedure vkGetPhysicalDeviceFormatProperties(physicalDevice.i, format.i, *pFormatProperties.VkFormatProperties)\n  If *pFormatProperties = 0\n    ProcedureReturn\n  EndIf\n  If avkPhysSlot(physicalDevice) = 0\n",
         "Procedure vkGetPhysicalDeviceFormatProperties(physicalDevice.i, format.i, *pFormatProperties.VkFormatProperties)\n  If *pFormatProperties = 0\n    ProcedureReturn\n  EndIf\n  If avkPhysSlot(physicalDevice) < 0\n"),
    )
    original = API.read_text(encoding="utf-8")
    results = []
    for name, fixed, broken in mutants:
        if original.count(fixed) != 1:
            results.append((name, False, "mutation anchor is stale"))
            continue
        try:
            API.write_text(original.replace(fixed, broken, 1), encoding="utf-8")
            cpu, rc, _ = run_image(build(PROBE, "anvil_vk_foundation_format_mutant.img"))
            count = u64(cpu, OUT + 8)
            failures = u64(cpu, OUT + 16)
            failed_rows = [i + 1 for i in range(count)
                           if u64(cpu, OUT + 0x100 + i * 8) == 0]
            caught = rc != 0 and failures != 0
            detail = ("rejected at emitted rows " + ",".join(map(str, failed_rows))
                      if caught else "stayed green")
            results.append((name, caught, detail))
        finally:
            API.write_text(original, encoding="utf-8")
    return results


def image_format_mutations() -> list[tuple[str, bool, str]]:
    """Require every reported image limit and every accepted field to be real."""
    mutants = (
        ("the maximum extent is hard coded instead of backend owned", API,
         "  limit = avkBackendMaxImageDimension2D()\n",
         "  limit = 4096\n"),
        ("maxResourceSize ignores the backend-owned image plan", API,
         "  bytes = plan\\bytes\n",
         "  bytes = limit * limit * 4\n"),
        ("the query advertises mip levels the creator refuses", API,
         "  *pImageFormatProperties\\maxMipLevels = 1\n",
         "  *pImageFormatProperties\\maxMipLevels = 2\n"),
        ("the query advertises array layers the creator refuses", API,
         "  *pImageFormatProperties\\maxArrayLayers = 1\n",
         "  *pImageFormatProperties\\maxArrayLayers = 2\n"),
        ("the query advertises sample counts the creator refuses", API,
         "  *pImageFormatProperties\\sampleCounts = #VK_SAMPLE_COUNT_1_BIT\n",
         "  *pImageFormatProperties\\sampleCounts = #VK_SAMPLE_COUNT_2_BIT\n"),
        ("the query ignores the requested image type", API,
         "  rc = AnvilVkImageFormatSupport(format, imageType, tiling, usage, flags)\n",
         "  rc = AnvilVkImageFormatSupport(format, #VK_IMAGE_TYPE_2D, tiling, usage, flags)\n"),
        ("the query ignores the requested tiling", API,
         "  rc = AnvilVkImageFormatSupport(format, imageType, tiling, usage, flags)\n",
         "  rc = AnvilVkImageFormatSupport(format, imageType, #VK_IMAGE_TILING_LINEAR, usage, flags)\n"),
        ("the query ignores the requested usage", API,
         "  rc = AnvilVkImageFormatSupport(format, imageType, tiling, usage, flags)\n",
         "  rc = AnvilVkImageFormatSupport(format, imageType, tiling, #VK_IMAGE_USAGE_TRANSFER_DST_BIT, flags)\n"),
        ("the query ignores image creation flags", API,
         "  rc = AnvilVkImageFormatSupport(format, imageType, tiling, usage, flags)\n",
         "  rc = AnvilVkImageFormatSupport(format, imageType, tiling, usage, 0)\n"),
        ("a transfer-only backend advertises colour attachments", MEMORY,
         "  If (usage & (~(#VK_IMAGE_USAGE_TRANSFER_SRC_BIT | #VK_IMAGE_USAGE_TRANSFER_DST_BIT | #VK_IMAGE_USAGE_SAMPLED_BIT | #VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT))) <> 0\n    ProcedureReturn #VK_ERROR_FORMAT_NOT_SUPPORTED\n  EndIf\n  If (usage & #VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT) <> 0 And AnvilVkBackendCanDraw() = 0\n",
         "  If (usage & (~(#VK_IMAGE_USAGE_TRANSFER_SRC_BIT | #VK_IMAGE_USAGE_TRANSFER_DST_BIT | #VK_IMAGE_USAGE_SAMPLED_BIT | #VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT))) <> 0\n    ProcedureReturn #VK_ERROR_FORMAT_NOT_SUPPORTED\n  EndIf\n  If (usage & #VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT) <> 0 And AnvilVkBackendCanDraw() < 0\n"),
        ("a format refusal leaves a supported maximum behind", API,
         "  *pImageFormatProperties\\maxExtent\\width = 0\n",
         "  ; maxExtent.width deliberately left stale\n"),
        ("a stale physical-device handle reaches the image query", API,
         "Procedure.i vkGetPhysicalDeviceImageFormatProperties(physicalDevice.i, format.i, imageType.i, tiling.i, usage.i, flags.i, *pImageFormatProperties.VkImageFormatProperties)\n  Define rc.i\n  Define limit.i\n  Define bytes.i\n  If *pImageFormatProperties = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf\n  If avkPhysSlot(physicalDevice) = 0\n",
         "Procedure.i vkGetPhysicalDeviceImageFormatProperties(physicalDevice.i, format.i, imageType.i, tiling.i, usage.i, flags.i, *pImageFormatProperties.VkImageFormatProperties)\n  Define rc.i\n  Define limit.i\n  Define bytes.i\n  If *pImageFormatProperties = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf\n  If avkPhysSlot(physicalDevice) < 0\n"),
        ("vkCreateImage no longer enters the query's combination owner", MEMORY,
         "  rc = AnvilVkImageFormatSupport(format, #VK_IMAGE_TYPE_2D, tiling, usage, 0)\n",
         "  rc = #VK_SUCCESS\n"),
    )
    results = []
    for name, path, fixed, broken in mutants:
        original = path.read_text(encoding="utf-8")
        if original.count(fixed) != 1:
            results.append((name, False, "mutation anchor is stale"))
            continue
        try:
            path.write_text(original.replace(fixed, broken, 1), encoding="utf-8")
            memory_text = MEMORY.read_text(encoding="utf-8")
            shared_create = (
                "rc = AnvilVkImageFormatSupport(format, #VK_IMAGE_TYPE_2D, "
                "tiling, usage, 0)"
            )
            if shared_create not in memory_text:
                results.append((name, True, "source contract rejected the divergence"))
                continue
            cpu, rc, _ = run_image(build(PROBE, "anvil_vk_foundation_image_format_mutant.img"))
            count = u64(cpu, OUT + 8)
            failures = u64(cpu, OUT + 16)
            failed_rows = [i + 1 for i in range(count)
                           if u64(cpu, OUT + 0x100 + i * 8) == 0]
            caught = rc != 0 and failures != 0
            detail = ("rejected at emitted rows " + ",".join(map(str, failed_rows))
                      if caught else "stayed green")
            results.append((name, caught, detail))
        finally:
            path.write_text(original, encoding="utf-8")
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mutate-queue", action="store_true")
    parser.add_argument("--mutate-features", action="store_true")
    parser.add_argument("--mutate-formats", action="store_true")
    args = parser.parse_args()
    failures = []
    checks = check_registry(failures)

    # The Pi backend must lower through the engine this tree proves on
    # silicon, and must not contain a processor-side or DMA fallback: a
    # fallback would let a green board test be a test of memcpy.
    backend_source = V3D_BACKEND.read_text(encoding="utf-8")
    for required in ("NeonRebindSurface", "NeonFrameBegin", "NeonFrameEnd"):
        if required not in backend_source:
            failures.append("the Pi 4 V3D backend omits " + required)
        checks += 1
    for forbidden in ("PokeN(", "PokeI(", "PokeL(", "DspCopy", "DmaCopy", "DisplayClear",
                      "DspDmaFill"):
        if forbidden in backend_source:
            failures.append("the Pi 4 V3D backend contains the fallback token " + forbidden)
        checks += 1

    memory_source = MEMORY.read_text(encoding="utf-8")
    shared_create = (
        "rc = AnvilVkImageFormatSupport(format, #VK_IMAGE_TYPE_2D, "
        "tiling, usage, 0)"
    )
    if memory_source.count(shared_create) != 1:
        failures.append("vkCreateImage does not enter the image-format query's combination owner exactly once")
    checks += 1

    cpu, rc, steps = run_image(build(PROBE, "anvil_vk_foundation.img"))
    magic, model_checks, model_fails = u64(cpu, OUT), u64(cpu, OUT + 8), u64(cpu, OUT + 16)
    checks += 3 + model_checks
    if magic != 0x564B5445:
        failures.append("emitted probe magic is $%X" % magic)
    if rc != 0 or model_fails != 0:
        failures.append("emitted probe rc=%d failures=%d" % (rc, model_fails))
        failed_rows = [str(i + 1) for i in range(model_checks)
                       if u64(cpu, OUT + 0x100 + i * 8) == 0]
        failures.append("emitted failed check rows: " + ",".join(failed_rows))
        failures.append("handles: " + ",".join("$%016X" % u64(cpu, OUT + p)
                                               for p in (24, 32, 40, 48)))
    if model_checks < 100:
        failures.append("emitted probe ran only %d checks" % model_checks)

    prod_cpu, prod_rc, prod_steps = run_image(
        build(PRODUCTION_PROBE, "anvil_vk_production.img"))
    checks += 3
    if u64(prod_cpu, OUT) != 0x564B5052:
        failures.append("production probe magic is wrong")
    if prod_rc != 0 or u64(prod_cpu, OUT + 8) != 0:
        failures.append("production probe exposed a backend or a device")

    if failures:
        print("vulkan_foundation_check: FAIL")
        for failure in failures:
            print("  " + failure)
        return 1
    print("vulkan_foundation_check: PASS")
    print("  pinned registry values, member names, member order and member types checked")
    print("  %d emitted ABI and lifecycle checks, %d interpreted A64 instructions, no MMIO"
          % (model_checks, steps))
    print("  production boundary executed in %d A64 instructions; device count stays zero"
          % prod_steps)
    print("  the Pi 4 V3D backend lowers through Neon/V3D and holds no CPU or DMA fallback")
    if args.mutate_queue:
        caught, detail = queue_capability_mutation()
        if not caught:
            print("vulkan_foundation_check: GREEN queue capability mutant - " + detail)
            return 1
        print("  RED queue capability mutant - " + detail)
    if args.mutate_features:
        for name, caught, detail in feature_mutations():
            if not caught:
                print("vulkan_foundation_check: GREEN feature mutant - " + name + " - " + detail)
                return 1
            print("  RED feature mutant - " + name + " - " + detail)
    if args.mutate_formats:
        for name, caught, detail in format_mutations():
            if not caught:
                print("vulkan_foundation_check: GREEN format mutant - " + name + " - " + detail)
                return 1
            print("  RED format mutant - " + name + " - " + detail)
        for name, caught, detail in image_format_mutations():
            if not caught:
                print("vulkan_foundation_check: GREEN image-format mutant - " + name + " - " + detail)
                return 1
            print("  RED image-format mutant - " + name + " - " + detail)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

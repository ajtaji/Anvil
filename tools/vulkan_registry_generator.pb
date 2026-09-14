; Vulkan 1.0 foundation vocabulary generator for Anvil.
; SPDX-FileCopyrightText: 2026 Anvil contributors
; SPDX-FileCopyrightText: 2026 Booger of Purebasic Forums
; SPDX-License-Identifier: MIT
;
; This is a PureBasic BUILD TOOL, not product runtime. It reads the official
; Khronos vk.xml pinned in Anvil/Graphics/Vulkan/COVERAGE.md, verifies the
; byte-exact SHA-256, and emits the deliberately small, ABI-checked stage-1
; vocabulary slice. It also emits a loud gap inventory. Extending the whitelist
; is acceptable only when the PureMetal ABI can represent the type exactly.
;
; The XML traversal shape was informed by Booger's MIT-licensed
; `vkXMLDumper.pb` (2026), but this generator is a new console-only tool with
; a pinned-version/core-feature/ABI-gap contract. See the retained notice in
; Anvil/Graphics/Vulkan/THIRD_PARTY_NOTICES.md.

EnableExplicit
UseSHA2Fingerprint()

#PIN_SHA = "50BD8C0F316EABF73D1C5FE3ADD2D89EAA480DBDA9282C12C289E80E9D081E08"

Global NewMap WantedEnum.b()
Global WantedEnumOrder.s
Global NewMap WantedStruct.s()
Global WantedStructOrder.s
Global NewMap EnumNode.i()
Global NewMap EnumOwner.s()
Global NewMap TypeNode.i()
Global NewMap Core10Name.b()

Procedure Die(text.s)
  PrintN("vulkan_registry_generator: " + text)
  End 1
EndProcedure

Procedure.s ChildText(*node, wanted.s)
  Define *child = ChildXMLNode(*node)
  While *child
    If GetXMLNodeName(*child) = wanted
      ProcedureReturn Trim(GetXMLNodeText(*child))
    EndIf
    *child = NextXMLNode(*child)
  Wend
  ProcedureReturn ""
EndProcedure

Procedure SeedWanted()
  Define names.s
  Define i.i
  Define name.s
  names = "VK_SUCCESS,VK_NOT_READY,VK_TIMEOUT,VK_EVENT_SET,VK_EVENT_RESET,VK_INCOMPLETE," +
          "VK_ERROR_OUT_OF_HOST_MEMORY,VK_ERROR_OUT_OF_DEVICE_MEMORY,VK_ERROR_INITIALIZATION_FAILED," +
          "VK_ERROR_DEVICE_LOST,VK_ERROR_MEMORY_MAP_FAILED,VK_ERROR_LAYER_NOT_PRESENT," +
          "VK_ERROR_EXTENSION_NOT_PRESENT,VK_ERROR_FEATURE_NOT_PRESENT,VK_ERROR_INCOMPATIBLE_DRIVER," +
          "VK_ERROR_TOO_MANY_OBJECTS,VK_ERROR_FORMAT_NOT_SUPPORTED,VK_ERROR_FRAGMENTED_POOL," +
          "VK_COMMAND_BUFFER_LEVEL_PRIMARY,VK_COMMAND_BUFFER_LEVEL_SECONDARY," +
          "VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT,VK_COMMAND_BUFFER_USAGE_RENDER_PASS_CONTINUE_BIT," +
          "VK_COMMAND_BUFFER_USAGE_SIMULTANEOUS_USE_BIT,VK_COMMAND_POOL_CREATE_TRANSIENT_BIT," +
          "VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT,VK_COMMAND_POOL_RESET_RELEASE_RESOURCES_BIT," +
          "VK_COMMAND_BUFFER_RESET_RELEASE_RESOURCES_BIT,VK_STRUCTURE_TYPE_APPLICATION_INFO," +
          "VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO," +
          "VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,VK_STRUCTURE_TYPE_SUBMIT_INFO," +
          "VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO," +
          "VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO," +
          "VK_STRUCTURE_TYPE_COMMAND_BUFFER_INHERITANCE_INFO,VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO," +
          "VK_FORMAT_B8G8R8A8_UNORM,VK_FORMAT_FEATURE_COLOR_ATTACHMENT_BIT," +
          "VK_IMAGE_LAYOUT_UNDEFINED,VK_IMAGE_LAYOUT_GENERAL," +
          "VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL"
  WantedEnumOrder = names
  For i = 1 To CountString(names, ",") + 1
    name = StringField(names, i, ",")
    WantedEnum(name) = 1
  Next
  WantedStruct("VkExtent2D") = "uint32_t:width,uint32_t:height"
  WantedStruct("VkExtent3D") = "uint32_t:width,uint32_t:height,uint32_t:depth"
  WantedStruct("VkOffset2D") = "int32_t:x,int32_t:y"
  WantedStruct("VkOffset3D") = "int32_t:x,int32_t:y,int32_t:z"
  WantedStruct("VkViewport") = "float:x,float:y,float:width,float:height,float:minDepth,float:maxDepth"
  WantedStruct("VkComponentMapping") = "VkComponentSwizzle:r,VkComponentSwizzle:g,VkComponentSwizzle:b,VkComponentSwizzle:a"
  WantedStruct("VkRect2D") = "VkOffset2D:offset,VkExtent2D:extent"
  WantedStruct("VkFormatProperties") = "VkFormatFeatureFlags:linearTilingFeatures,VkFormatFeatureFlags:optimalTilingFeatures,VkFormatFeatureFlags:bufferFeatures"
  WantedStruct("VkImageFormatProperties") = "VkExtent3D:maxExtent,uint32_t:maxMipLevels,uint32_t:maxArrayLayers,VkSampleCountFlags:sampleCounts,VkDeviceSize:maxResourceSize"
  WantedStruct("VkExtensionProperties") = "char:extensionName,uint32_t:specVersion"
  WantedStruct("VkLayerProperties") = "char:layerName,uint32_t:specVersion,uint32_t:implementationVersion,char:description"
  WantedStruct("VkApplicationInfo") = "VkStructureType:sType,void:pNext,char:pApplicationName,uint32_t:applicationVersion,char:pEngineName,uint32_t:engineVersion,uint32_t:apiVersion"
  WantedStruct("VkAllocationCallbacks") = "void:pUserData,PFN_vkAllocationFunction:pfnAllocation,PFN_vkReallocationFunction:pfnReallocation,PFN_vkFreeFunction:pfnFree,PFN_vkInternalAllocationNotification:pfnInternalAllocation,PFN_vkInternalFreeNotification:pfnInternalFree"
  WantedStruct("VkDeviceQueueCreateInfo") = "VkStructureType:sType,void:pNext,VkDeviceQueueCreateFlags:flags,uint32_t:queueFamilyIndex,uint32_t:queueCount,float:pQueuePriorities"
  WantedStruct("VkPhysicalDeviceFeatures") = "VkBool32:robustBufferAccess,VkBool32:fullDrawIndexUint32,VkBool32:imageCubeArray,VkBool32:independentBlend,VkBool32:geometryShader,VkBool32:tessellationShader,VkBool32:sampleRateShading,VkBool32:dualSrcBlend,VkBool32:logicOp,VkBool32:multiDrawIndirect,VkBool32:drawIndirectFirstInstance,VkBool32:depthClamp,VkBool32:depthBiasClamp,VkBool32:fillModeNonSolid,VkBool32:depthBounds,VkBool32:wideLines,VkBool32:largePoints,VkBool32:alphaToOne,VkBool32:multiViewport,VkBool32:samplerAnisotropy,VkBool32:textureCompressionETC2,VkBool32:textureCompressionASTC_LDR,VkBool32:textureCompressionBC,VkBool32:occlusionQueryPrecise,VkBool32:pipelineStatisticsQuery,VkBool32:vertexPipelineStoresAndAtomics,VkBool32:fragmentStoresAndAtomics,VkBool32:shaderTessellationAndGeometryPointSize,VkBool32:shaderImageGatherExtended,VkBool32:shaderStorageImageExtendedFormats,VkBool32:shaderStorageImageMultisample,VkBool32:shaderStorageImageReadWithoutFormat,VkBool32:shaderStorageImageWriteWithoutFormat,VkBool32:shaderUniformBufferArrayDynamicIndexing,VkBool32:shaderSampledImageArrayDynamicIndexing,VkBool32:shaderStorageBufferArrayDynamicIndexing,VkBool32:shaderStorageImageArrayDynamicIndexing,VkBool32:shaderClipDistance,VkBool32:shaderCullDistance,VkBool32:shaderFloat64,VkBool32:shaderInt64,VkBool32:shaderInt16,VkBool32:shaderResourceResidency,VkBool32:shaderResourceMinLod,VkBool32:sparseBinding,VkBool32:sparseResidencyBuffer,VkBool32:sparseResidencyImage2D,VkBool32:sparseResidencyImage3D,VkBool32:sparseResidency2Samples,VkBool32:sparseResidency4Samples,VkBool32:sparseResidency8Samples,VkBool32:sparseResidency16Samples,VkBool32:sparseResidencyAliased,VkBool32:variableMultisampleRate,VkBool32:inheritedQueries"
  WantedStruct("VkDeviceCreateInfo") = "VkStructureType:sType,void:pNext,VkDeviceCreateFlags:flags,uint32_t:queueCreateInfoCount,VkDeviceQueueCreateInfo:pQueueCreateInfos,uint32_t:enabledLayerCount,char:ppEnabledLayerNames,uint32_t:enabledExtensionCount,char:ppEnabledExtensionNames,VkPhysicalDeviceFeatures:pEnabledFeatures"
  WantedStruct("VkInstanceCreateInfo") = "VkStructureType:sType,void:pNext,VkInstanceCreateFlags:flags,VkApplicationInfo:pApplicationInfo,uint32_t:enabledLayerCount,char:ppEnabledLayerNames,uint32_t:enabledExtensionCount,char:ppEnabledExtensionNames"
  WantedStruct("VkCommandPoolCreateInfo") = "VkStructureType:sType,void:pNext,VkCommandPoolCreateFlags:flags,uint32_t:queueFamilyIndex"
  WantedStruct("VkCommandBufferAllocateInfo") = "VkStructureType:sType,void:pNext,VkCommandPool:commandPool,VkCommandBufferLevel:level,uint32_t:commandBufferCount"
  WantedStruct("VkCommandBufferInheritanceInfo") = "VkStructureType:sType,void:pNext,VkRenderPass:renderPass,uint32_t:subpass,VkFramebuffer:framebuffer,VkBool32:occlusionQueryEnable,VkQueryControlFlags:queryFlags,VkQueryPipelineStatisticFlags:pipelineStatistics"
  WantedStruct("VkCommandBufferBeginInfo") = "VkStructureType:sType,void:pNext,VkCommandBufferUsageFlags:flags,VkCommandBufferInheritanceInfo:pInheritanceInfo"
  WantedStruct("VkSubmitInfo") = "VkStructureType:sType,void:pNext,uint32_t:waitSemaphoreCount,VkSemaphore:pWaitSemaphores,VkPipelineStageFlags:pWaitDstStageMask,uint32_t:commandBufferCount,VkCommandBuffer:pCommandBuffers,uint32_t:signalSemaphoreCount,VkSemaphore:pSignalSemaphores"
  WantedStruct("VkSemaphoreCreateInfo") = "VkStructureType:sType,void:pNext,VkSemaphoreCreateFlags:flags"
  WantedStructOrder = "VkExtent2D,VkExtent3D,VkOffset2D,VkOffset3D,VkViewport,VkRect2D,VkFormatProperties,VkImageFormatProperties," +
                      "VkComponentMapping,VkExtensionProperties,VkLayerProperties,VkApplicationInfo," +
                      "VkAllocationCallbacks,VkDeviceQueueCreateInfo,VkPhysicalDeviceFeatures,VkDeviceCreateInfo," +
                      "VkInstanceCreateInfo,VkCommandPoolCreateInfo,VkCommandBufferAllocateInfo," +
                      "VkCommandBufferInheritanceInfo,VkCommandBufferBeginInfo,VkSubmitInfo,VkSemaphoreCreateInfo"
EndProcedure

Procedure IndexRegistry(*root)
  Define *group = ChildXMLNode(*root)
  Define *node
  Define name.s
  While *group
    If GetXMLNodeName(*group) = "enums"
      *node = ChildXMLNode(*group)
      While *node
        If GetXMLNodeName(*node) = "enum"
          name = GetXMLAttribute(*node, "name")
          If name <> ""
            EnumNode(name) = *node
            EnumOwner(name) = GetXMLAttribute(*group, "name")
          EndIf
        EndIf
        *node = NextXMLNode(*node)
      Wend
    ElseIf GetXMLNodeName(*group) = "types"
      *node = ChildXMLNode(*group)
      While *node
        If GetXMLNodeName(*node) = "type"
          name = GetXMLAttribute(*node, "name")
          If name <> "" : TypeNode(name) = *node : EndIf
        EndIf
        *node = NextXMLNode(*node)
      Wend
    ElseIf GetXMLNodeName(*group) = "feature" And GetXMLAttribute(*group, "number") = "1.0" And FindString(GetXMLAttribute(*group, "api"), "vulkan")
      Define *require = ChildXMLNode(*group)
      Define *item
      While *require
        If GetXMLNodeName(*require) = "require"
          *item = ChildXMLNode(*require)
          While *item
            name = GetXMLAttribute(*item, "name")
            If name <> "" : Core10Name(name) = 1 : EndIf
            *item = NextXMLNode(*item)
          Wend
        EndIf
        *require = NextXMLNode(*require)
      Wend
    EndIf
    *group = NextXMLNode(*group)
  Wend
EndProcedure

Procedure.s EnumValue(name.s)
  Define *node
  Define value.s
  Define bit.s
  Define alias.s
  If Not FindMapElement(EnumNode(), name) : Die("registry has no " + name) : EndIf
  *node = EnumNode()
  value = GetXMLAttribute(*node, "value")
  bit = GetXMLAttribute(*node, "bitpos")
  alias = GetXMLAttribute(*node, "alias")
  If value <> "" : ProcedureReturn ReplaceString(UCase(value), "0X", "$") : EndIf
  If bit <> "" : ProcedureReturn "$" + Hex(1 << Val(bit)) : EndIf
  If alias <> "" : ProcedureReturn EnumValue(alias) : EndIf
  Die(name + " has no core value")
EndProcedure

Procedure.s PbSuffix(cType.s)
  Select cType
    Case "uint32_t", "int32_t", "VkBool32", "VkComponentSwizzle", "VkStructureType", "VkDeviceQueueCreateFlags", "VkDeviceCreateFlags", "VkInstanceCreateFlags", "VkCommandPoolCreateFlags", "VkSemaphoreCreateFlags", "VkCommandBufferLevel", "VkQueryControlFlags", "VkQueryPipelineStatisticFlags", "VkCommandBufferUsageFlags", "VkPipelineStageFlags", "VkFormatFeatureFlags", "VkSampleCountFlags" : ProcedureReturn ".l"
    Case "float" : ProcedureReturn ".f"
    Case "VkCommandPool", "VkRenderPass", "VkFramebuffer", "VkSemaphore", "VkCommandBuffer" : ProcedureReturn ".i"
    Case "VkOffset2D", "VkExtent2D", "VkExtent3D" : ProcedureReturn "." + cType
    Case "VkDeviceSize" : ProcedureReturn ".q"
  EndSelect
  Die("no exact PureMetal scalar mapping for " + cType)
EndProcedure

Procedure EmitStruct(file.i, name.s, signature.s)
  Define *node
  Define *member
  Define got.s
  Define cType.s
  Define memberName.s
  Define raw.s
  Define arrayName.s
  Define isPointer.i
  If Not FindMapElement(TypeNode(), name) : Die("registry has no " + name) : EndIf
  *node = TypeNode()
  *member = ChildXMLNode(*node)
  While *member
    If GetXMLNodeName(*member) = "member"
      cType = ChildText(*member, "type")
      memberName = ChildText(*member, "name")
      If got <> "" : got + "," : EndIf
      got + cType + ":" + memberName
    EndIf
    *member = NextXMLNode(*member)
  Wend
  If got <> signature : Die(name + " member signature changed to " + got) : EndIf
  WriteStringN(file, "Structure " + name + " Align #PB_Structure_AlignC")
  *member = ChildXMLNode(*node)
  While *member
    If GetXMLNodeName(*member) = "member"
      cType = ChildText(*member, "type")
      memberName = ChildText(*member, "name")
      raw = GetXMLNodeText(*member)
      arrayName = ChildText(*member, "enum")
      isPointer = Bool(FindString(raw, "*") <> 0 Or Left(cType, 4) = "PFN_")
      If isPointer
        WriteStringN(file, "  *" + memberName)
      ElseIf arrayName <> ""
        If cType <> "char" : Die("no fixed-array mapping for " + cType) : EndIf
        WriteStringN(file, "  " + memberName + ".a[#" + arrayName + "]")
      Else
        WriteStringN(file, "  " + memberName + PbSuffix(cType))
      EndIf
    EndIf
    *member = NextXMLNode(*member)
  Wend
  WriteStringN(file, "EndStructure" + #CRLF$)
EndProcedure

Procedure Main()
  Define source.s
  Define outDir.s
  Define digest.s
  Define *root
  Define file.i
  Define gaps.i
  If CountProgramParameters() <> 2
    Die("usage: vulkan_registry_generator <vk.xml> <output-directory>")
  EndIf
  source = ProgramParameter(0)
  outDir = ProgramParameter(1)
  If Right(outDir, 1) <> #PS$ : outDir + #PS$ : EndIf
  digest = UCase(FileFingerprint(source, #PB_Cipher_SHA2, 256))
  If digest <> #PIN_SHA : Die("vk.xml SHA-256 " + digest + ", wanted " + #PIN_SHA) : EndIf
  If LoadXML(0, source) = 0 : Die("cannot load " + source) : EndIf
  *root = MainXMLNode(0)
  SeedWanted()
  IndexRegistry(*root)
  ForEach WantedEnum()
    Define enumName.s = MapKey(WantedEnum())
    If Not FindMapElement(EnumNode(), enumName)
      Die(enumName + " is absent from the registry")
    EndIf
    Define enumOwnerName.s = EnumOwner(enumName)
    If Not FindMapElement(Core10Name(), enumName) And Not FindMapElement(Core10Name(), enumOwnerName)
      Die(MapKey(WantedEnum()) + " is not required by VK_VERSION_1_0")
    EndIf
  Next
  ForEach WantedStruct()
    If Not FindMapElement(Core10Name(), MapKey(WantedStruct()))
      Die(MapKey(WantedStruct()) + " is not required by VK_VERSION_1_0")
    EndIf
  Next
  file = CreateFile(#PB_Any, outDir + "vk_core_1_0.generated.pbi")
  If file = 0 : Die("cannot create generated vocabulary") : EndIf
  WriteStringN(file, "; Generated from Vulkan-Headers v1.4.350, core 1.0 stage-1 slice")
  WriteStringN(file, "; SPDX-License-Identifier: Apache-2.0 OR MIT" + #CRLF$)
  WriteStringN(file, "#VK_API_VERSION_1_0 = $00400000")
  WriteStringN(file, "#VK_HEADER_VERSION = 350")
  WriteStringN(file, "#VK_HEADER_VERSION_COMPLETE = $0040415E")
  WriteStringN(file, "#VK_NULL_HANDLE = 0")
  WriteStringN(file, "#VK_WHOLE_SIZE = -1")
  WriteStringN(file, "#VK_TRUE = 1")
  WriteStringN(file, "#VK_FALSE = 0")
  WriteStringN(file, "#VK_MAX_EXTENSION_NAME_SIZE = 256")
  WriteStringN(file, "#VK_MAX_DESCRIPTION_SIZE = 256")
  WriteStringN(file, "#VK_UUID_SIZE = 16")
  Define enumIndex.i
  Define outputEnumName.s
  For enumIndex = 1 To CountString(WantedEnumOrder, ",") + 1
    outputEnumName = StringField(WantedEnumOrder, enumIndex, ",")
    WriteStringN(file, "#" + outputEnumName + " = " + EnumValue(outputEnumName))
  Next
  WriteStringN(file, "")
  Define i.i
  Define structName.s
  For i = 1 To CountString(WantedStructOrder, ",") + 1
    structName = StringField(WantedStructOrder, i, ",")
    If Not FindMapElement(WantedStruct(), structName) : Die("missing selected structure " + structName) : EndIf
    EmitStruct(file, structName, WantedStruct())
  Next
  CloseFile(file)
  gaps = CreateFile(#PB_Any, outDir + "vk_core_1_0.gaps.txt")
  If gaps = 0 : Die("cannot create gap inventory") : EndIf
  WriteStringN(gaps, "TARGET VK_API_VERSION_1_0 -- NOT AN IMPLEMENTATION CLAIM")
  WriteStringN(gaps, "GENERATED VOCABULARY: CHECKED 21-STRUCT FOUNDATION SLICE, NOT COMPLETE CORE 1.0")
  WriteStringN(gaps, "SEMANTIC vk* ENTRY SURFACE: NOT YET EXPORTED")
  WriteStringN(gaps, "PRODUCTION PHYSICAL DEVICES / QUEUES: NONE")
  WriteStringN(gaps, "V3D EXECUTION: DEVELOPMENT-ONLY OFFSCREEN FULL BGRA8 CLEAR; NOT A PRODUCTION DEVICE")
  WriteStringN(gaps, "SPIR-V / PIPELINES / VULKAN RESOURCES / GENERAL SYNCHRONIZATION / WSI: NOT IMPLEMENTED")
  CloseFile(gaps)
  FreeXML(0)
  PrintN("vulkan_registry_generator: wrote exact stage-1 slice and gap inventory")
EndProcedure

OpenConsole()
Main()

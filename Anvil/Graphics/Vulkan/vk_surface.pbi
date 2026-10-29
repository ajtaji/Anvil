; VK_KHR_surface revision 25, over the target-neutral provider ownership engine.
; Contract: Khronos VK_KHR_surface and its five command/structure reference pages.
; No platform window creation, swapchain extension or implementation code copied.
; SPDX-License-Identifier: MIT
XIncludeFile "Anvil/Graphics/Vulkan/vk_wsi.pbi"

#VK_KHR_SURFACE_SPEC_VERSION = 25
#VK_KHR_SURFACE_EXTENSION_NAME$ = "VK_KHR_surface"

; Explicit byte-string address for the pointer-based Vulkan ABI.
Procedure.i avkSurfaceExtensionName()
  ProcedureReturn "VK_KHR_surface"
EndProcedure

Structure VkSurfaceCapabilitiesKHR Align #PB_Structure_AlignC
  minImageCount.l
  maxImageCount.l
  currentExtent.VkExtent2D
  minImageExtent.VkExtent2D
  maxImageExtent.VkExtent2D
  maxImageArrayLayers.l
  supportedTransforms.l
  currentTransform.l
  supportedCompositeAlpha.l
  supportedUsageFlags.l
EndStructure

Structure VkSurfaceFormatKHR Align #PB_Structure_AlignC
  format.l
  colorSpace.l
EndStructure

Procedure.i avkSurfaceEnabled(instance.i)
  Define s.i
  s = avkInstSlot(instance)
  If s = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkInstSurfaceEnabled[s]
EndProcedure

Procedure.i avkSurfaceRequireInstance(instance.i)
  If avkInstSlot(instance) = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkSurfaceEnabled(instance) = 0 : ProcedureReturn #VK_ERROR_EXTENSION_NOT_PRESENT : EndIf
  ProcedureReturn #VK_SUCCESS
EndProcedure

; Native Anvil provider binding, not an invented platform extension command.
; The internal constructor remains available to private non-extension callers.
Procedure.i AnvilVkSurfaceCreate(instance.i, provider.i, nativeKey.i, *out)
  Define rc.i
  rc = avkSurfaceRequireInstance(instance)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  ProcedureReturn avkWsiSurfaceCreate(instance, provider, nativeKey, *out)
EndProcedure

; Return a positive provider slot only for a current, enabled common parent.
Procedure.i avkSurfaceQueryProvider(physical.i, surface.i)
  Define p.i, s.i, inst.i, instance.i, rc.i, provider.i
  p = avkPhysSlot(physical) : s = avkWsiSurfaceSlot(surface)
  If p = 0 Or s = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  inst = avkPhysInst[p]
  If inst < 1 Or inst > #ANVIL_VK_MAX_INSTANCES : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
  If avkInstLive[inst] = 0 Or avkWsiSurfInst[s] <> inst Or avkWsiSurfInstGen[s] <> avkInstGen[inst]
    ProcedureReturn #ANVIL_VK_ERR_OWNER
  EndIf
  instance = avkToken(#ANVIL_VK_TYPE_INSTANCE, inst, avkInstGen[inst])
  rc = avkSurfaceRequireInstance(instance)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  provider = avkWsiSurfaceProvider(instance, surface)
  If provider = 0 : ProcedureReturn #VK_ERROR_SURFACE_LOST_KHR : EndIf
  ProcedureReturn provider
EndProcedure

Procedure.i vkGetPhysicalDeviceSurfaceSupportKHR(physicalDevice.i, queueFamilyIndex.i, surface.i, *pSupported)
  Define p.i
  If *pSupported = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  p = avkSurfaceQueryProvider(physicalDevice, surface)
  If p < 1 : ProcedureReturn p : EndIf
  If queueFamilyIndex <> #ANVIL_VK_QUEUE_FAMILY : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeL(*pSupported, #VK_TRUE)
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i vkGetPhysicalDeviceSurfaceCapabilitiesKHR(physicalDevice.i, surface.i, *pCapabilities.VkSurfaceCapabilitiesKHR)
  Define p.i, n.i, value.i
  If *pCapabilities = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  p = avkSurfaceQueryProvider(physicalDevice, surface)
  If p < 1 : ProcedureReturn p : EndIf
  ; Internal capabilities have thirteen integer fields; the C API has thirteen
  ; uint32 words in the same order. Preflight every word before writing any.
  For n = 0 To 12
    value = PeekI(@avkWsiProvCaps[p] + n * SizeOf(.i))
    If value < 0 Or value > $FFFFFFFF : ProcedureReturn #ANVIL_VK_ERR_UNSUPPORTED : EndIf
  Next
  For n = 0 To 12
    PokeL(*pCapabilities + n * 4, PeekI(@avkWsiProvCaps[p] + n * SizeOf(.i)))
  Next
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i vkGetPhysicalDeviceSurfaceFormatsKHR(physicalDevice.i, surface.i, *pCount, *pFormats.VkSurfaceFormatKHR)
  Define p.i, count.i, capacity.i, written.i, n.i, format.i, color.i
  If *pCount = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  p = avkSurfaceQueryProvider(physicalDevice, surface)
  If p < 1 : ProcedureReturn p : EndIf
  count = avkWsiProvFormatCount[p]
  For n = 0 To count - 1
    format = avkWsiProvFormat[avkWsiFormatIndex(p, n)]
    color = avkWsiProvColor[avkWsiFormatIndex(p, n)]
    If format < 1 Or format > $7FFFFFFF Or color < 0 Or color > $7FFFFFFF
      ProcedureReturn #ANVIL_VK_ERR_UNSUPPORTED
    EndIf
  Next
  If *pFormats = 0 : PokeL(*pCount, count) : ProcedureReturn #VK_SUCCESS : EndIf
  capacity = PeekL(*pCount) & $FFFFFFFF
  written = count : If capacity < written : written = capacity : EndIf
  For n = 0 To written - 1
    PokeL(*pFormats + n * SizeOf(VkSurfaceFormatKHR), avkWsiProvFormat[avkWsiFormatIndex(p, n)])
    PokeL(*pFormats + n * SizeOf(VkSurfaceFormatKHR) + 4, avkWsiProvColor[avkWsiFormatIndex(p, n)])
  Next
  PokeL(*pCount, written)
  If written < count : ProcedureReturn #VK_INCOMPLETE : EndIf
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i vkGetPhysicalDeviceSurfacePresentModesKHR(physicalDevice.i, surface.i, *pCount, *pModes)
  Define p.i, count.i, capacity.i, written.i, n.i
  If *pCount = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  p = avkSurfaceQueryProvider(physicalDevice, surface)
  If p < 1 : ProcedureReturn p : EndIf
  count = avkWsiProvModeCount[p]
  If *pModes = 0 : PokeL(*pCount, count) : ProcedureReturn #VK_SUCCESS : EndIf
  capacity = PeekL(*pCount) & $FFFFFFFF
  written = count : If capacity < written : written = capacity : EndIf
  For n = 0 To written - 1
    PokeL(*pModes + n * 4, avkWsiProvMode[avkWsiModeIndex(p, n)])
  Next
  PokeL(*pCount, written)
  If written < count : ProcedureReturn #VK_INCOMPLETE : EndIf
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure vkDestroySurfaceKHR(instance.i, surface.i, *pAllocator)
  Define rc.i
  If avkNoAllocator(*pAllocator, 30) <> #VK_SUCCESS : ProcedureReturn : EndIf
  If surface = #VK_NULL_HANDLE : ProcedureReturn : EndIf
  rc = avkSurfaceRequireInstance(instance)
  If rc = #VK_SUCCESS : rc = avkWsiSurfaceDestroy(instance, surface) : EndIf
  If rc <> #VK_SUCCESS
    avkFault(rc, "vkDestroySurfaceKHR retained the surface: check the enabled instance, surface owner and remaining swapchains.")
  EndIf
EndProcedure

Procedure.i avkSurfaceEnumerateExtensions(*pCount, *pProperties)
  Define n.i, name.i
  If *pCount = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  If *pProperties = 0 : PokeL(*pCount, 1) : ProcedureReturn #VK_SUCCESS : EndIf
  If (PeekL(*pCount) & $FFFFFFFF) = 0
    PokeL(*pCount, 0) : ProcedureReturn #VK_INCOMPLETE
  EndIf
  For n = 0 To SizeOf(VkExtensionProperties) - 1 : PokeA(*pProperties + n, 0) : Next
  name = avkSurfaceExtensionName() : n = 0
  While PeekA(name + n) <> 0
    PokeA(*pProperties + n, PeekA(name + n)) : n = n + 1
  Wend
  PokeL(*pProperties + OffsetOf(VkExtensionProperties\specVersion), #VK_KHR_SURFACE_SPEC_VERSION)
  PokeL(*pCount, 1)
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkSurfaceDispatch(instance.i, *pName)
  If avkSurfaceEnabled(instance) = 0 : ProcedureReturn 0 : EndIf
  If avkApiNameEquals(*pName, "vkDestroySurfaceKHR", 128) : ProcedureReturn @vkDestroySurfaceKHR : EndIf
  If avkApiNameEquals(*pName, "vkGetPhysicalDeviceSurfaceSupportKHR", 128) : ProcedureReturn @vkGetPhysicalDeviceSurfaceSupportKHR : EndIf
  If avkApiNameEquals(*pName, "vkGetPhysicalDeviceSurfaceCapabilitiesKHR", 128) : ProcedureReturn @vkGetPhysicalDeviceSurfaceCapabilitiesKHR : EndIf
  If avkApiNameEquals(*pName, "vkGetPhysicalDeviceSurfaceFormatsKHR", 128) : ProcedureReturn @vkGetPhysicalDeviceSurfaceFormatsKHR : EndIf
  If avkApiNameEquals(*pName, "vkGetPhysicalDeviceSurfacePresentModesKHR", 128) : ProcedureReturn @vkGetPhysicalDeviceSurfacePresentModesKHR : EndIf
  ProcedureReturn 0
EndProcedure

; Actual public surface API and ownership with an explicit state-only backend.
; No GPU, display controller, DMA or pixel operation is performed.
EnableFloatingPoint
XIncludeFile "Anvil/Graphics/Vulkan/vk_api.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_backend_test.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_dispatch.pbi"
Global si.i, sp.i, offInst.i, offPhys.i, foreignInst.i, foreignPhys.i
Global surface.i, privateSurface.i, foreignSurface.i, provider.i, testDevice.i
Global Dim surfaceBytes.i[64]
Global Dim surfaceFormats.AnvilVkWsiFormat[2]
Global Dim surfaceModes.i[2]

Procedure.i SurfaceProofInstance(enabled.i, *instance, *physical)
  Define ci.VkInstanceCreateInfo, name.i, count.i, rc.i, n.i
  For n = 0 To SizeOf(VkInstanceCreateInfo) - 1 : PokeA(@ci + n, 0) : Next
  ci\sType = #VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO
  name = avkSurfaceExtensionName()
  If enabled <> 0 : ci\enabledExtensionCount = 1 : ci\ppEnabledExtensionNames = @name : EndIf
  rc = vkCreateInstance(@ci, 0, *instance)
  If rc <> 0 : ProcedureReturn rc : EndIf
  count = 1
  ProcedureReturn vkEnumeratePhysicalDevices(PeekI(*instance), @count, *physical)
EndProcedure

Procedure.i SurfaceProofProvider()
  Define info.AnvilVkWsiProviderInfo
  info\cookie = 707
  info\capabilities\minImageCount = 1 : info\capabilities\maxImageCount = 2
  info\capabilities\currentWidth = 64 : info\capabilities\currentHeight = 65
  info\capabilities\minWidth = 32 : info\capabilities\minHeight = 33
  info\capabilities\maxWidth = 128 : info\capabilities\maxHeight = 129
  info\capabilities\maxImageArrayLayers = 1
  info\capabilities\supportedTransforms = 1 : info\capabilities\currentTransform = 1
  info\capabilities\supportedCompositeAlpha = 1
  info\capabilities\supportedUsageFlags = #VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT
  surfaceFormats[0]\format = #VK_FORMAT_B8G8R8A8_UNORM : surfaceFormats[0]\colorSpace = 0
  surfaceFormats[1]\format = #VK_FORMAT_R8G8B8A8_UNORM : surfaceFormats[1]\colorSpace = 0
  surfaceModes[0] = #VK_PRESENT_MODE_FIFO_KHR : surfaceModes[1] = #VK_PRESENT_MODE_IMMEDIATE_KHR
  info\formatCount = 2 : info\formats = @surfaceFormats[0]
  info\presentModeCount = 2 : info\presentModes = @surfaceModes[0]
  ProcedureReturn avkWsiProviderRegister(@info, @provider)
EndProcedure

Procedure.i SurfaceProofBadName()
  ProcedureReturn "VK_unavailable"
EndProcedure

Procedure SurfaceProofFill()
  Define n.i
  For n = 0 To 511 : PokeA(@surfaceBytes[0] + n, $A5) : Next
EndProcedure

Procedure.i SurfaceProofOutside(changed.i)
  Define n.i
  For n = 0 To 511
    If n < 8 Or n >= 8 + changed
      If PeekA(@surfaceBytes[0] + n) <> $A5 : ProcedureReturn 0 : EndIf
    EndIf
  Next
  ProcedureReturn 1
EndProcedure

; Independent semantic oracle for every C capabilities word, not just its size.
Procedure.i SurfaceProofCapsExact(p.i)
  If PeekL(p) <> 1 Or PeekL(p + 4) <> 2 Or PeekL(p + 8) <> 64 Or PeekL(p + 12) <> 65 : ProcedureReturn 0 : EndIf
  If PeekL(p + 16) <> 32 Or PeekL(p + 20) <> 33 Or PeekL(p + 24) <> 128 Or PeekL(p + 28) <> 129 : ProcedureReturn 0 : EndIf
  If PeekL(p + 32) <> 1 Or PeekL(p + 36) <> 1 Or PeekL(p + 40) <> 1 Or PeekL(p + 44) <> 1 Or PeekL(p + 48) <> 16 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

Procedure SurfaceProofRecord(id.i, rc.i, a.i, b.i, c.i, d.i, outside.i, extra.i)
  Define at.i
  at = #TC_REPORT + 64 + (id - 1) * 64
  PokeI(at, id) : PokeI(at + 8, rc) : PokeI(at + 16, a) : PokeI(at + 24, b)
  PokeI(at + 32, c) : PokeI(at + 40, d) : PokeI(at + 48, outside) : PokeI(at + 56, extra)
EndProcedure

Procedure.i Main(services.i)
  Define n.i, rc.i, count.i, at.i, names.i, ci.VkInstanceCreateInfo, bad.i
  Define pointerCount.i, old.i, fresh.i, tempPhys.i, slot.i, remaining.i
  For n = 0 To 4095 : PokeA(#TC_REPORT + n, 0) : Next
  avkTbHeapBase = $6200000 : avkTbHeapBytes = $100000
  at = @surfaceBytes[0] + 8
  count = $1122334400000000
  SurfaceProofFill() : rc = vkEnumerateInstanceExtensionProperties(0, @count, 0)
  SurfaceProofRecord(1, rc, PeekL(@count) & $FFFFFFFF, 0, 0, 0, SurfaceProofOutside(0), Bool(PeekL(@count + 4) = $11223344))
  PokeL(@count, 0) : rc = vkEnumerateInstanceExtensionProperties(0, @count, at)
  SurfaceProofRecord(2, rc, PeekL(@count) & $FFFFFFFF, 0, 0, 0, SurfaceProofOutside(0), 1)
  PokeL(@count, 1) : rc = vkEnumerateInstanceExtensionProperties(0, @count, at)
  SurfaceProofRecord(3, rc, PeekL(@count) & $FFFFFFFF, avkApiNameEquals(at, avkSurfaceExtensionName(), 256), PeekL(at + OffsetOf(VkExtensionProperties\specVersion)), 0, SurfaceProofOutside(SizeOf(VkExtensionProperties)), Bool(PeekL(@count + 4) = $11223344))
  ci\sType = #VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO : ci\enabledExtensionCount = 1
  names = SurfaceProofBadName() : ci\ppEnabledExtensionNames = @names : bad = 1234
  rc = vkCreateInstance(@ci, 0, @bad)
  SurfaceProofRecord(4, rc, Bool(bad = 1234), 0, 0, 0, 1, 1)
  rc = SurfaceProofInstance(1, @si, @sp) : If rc <> 0 : ProcedureReturn 501 : EndIf
  rc = SurfaceProofProvider() : If rc <> 0 : ProcedureReturn 502 : EndIf
  rc = AnvilVkSurfaceCreate(si, provider, 808, @surface) : If rc <> 0 : ProcedureReturn 503 : EndIf
  SurfaceProofRecord(5, rc, avkSurfaceEnabled(si), SizeOf(VkSurfaceCapabilitiesKHR), SizeOf(VkSurfaceFormatKHR), OffsetOf(VkSurfaceCapabilitiesKHR\supportedUsageFlags), 1, 25)
  rc = SurfaceProofInstance(0, @offInst, @offPhys)
  rc = avkWsiSurfaceCreate(offInst, provider, 810, @privateSurface)
  SurfaceProofFill() : rc = vkGetPhysicalDeviceSurfaceSupportKHR(offPhys, 0, privateSurface, at)
  SurfaceProofRecord(6, rc, 0, 0, 0, 0, SurfaceProofOutside(0), 1)
  rc = SurfaceProofInstance(1, @foreignInst, @foreignPhys)
  rc = AnvilVkSurfaceCreate(foreignInst, provider, 909, @foreignSurface)
  SurfaceProofFill() : rc = vkGetPhysicalDeviceSurfaceSupportKHR(sp, 0, surface, at)
  SurfaceProofRecord(7, rc, PeekL(at), 0, 0, 0, SurfaceProofOutside(4), 1)
  SurfaceProofFill() : rc = vkGetPhysicalDeviceSurfaceSupportKHR(sp, 1, surface, at)
  SurfaceProofRecord(8, rc, 0, 0, 0, 0, SurfaceProofOutside(0), 1)
  rc = vkGetPhysicalDeviceSurfaceSupportKHR(sp, 0, foreignSurface, at)
  SurfaceProofRecord(9, rc, 0, 0, 0, 0, SurfaceProofOutside(0), 1)
  SurfaceProofFill() : rc = vkGetPhysicalDeviceSurfaceCapabilitiesKHR(sp, surface, at)
  SurfaceProofRecord(10, rc, PeekL(at), PeekL(at + 4), PeekL(at + 8), PeekL(at + 12), SurfaceProofOutside(52), SurfaceProofCapsExact(at))
  SurfaceProofFill() : rc = vkGetPhysicalDeviceSurfaceCapabilitiesKHR(sp, surface, 0)
  SurfaceProofRecord(11, rc, 0, 0, 0, 0, SurfaceProofOutside(0), 1)
  PokeL(@count, 0) : rc = vkGetPhysicalDeviceSurfaceFormatsKHR(sp, surface, @count, 0)
  SurfaceProofRecord(12, rc, PeekL(@count) & $FFFFFFFF, 0, 0, 0, SurfaceProofOutside(0), Bool(PeekL(@count + 4) = $11223344))
  PokeL(@count, 1) : rc = vkGetPhysicalDeviceSurfaceFormatsKHR(sp, surface, @count, at)
  SurfaceProofRecord(13, rc, PeekL(@count) & $FFFFFFFF, PeekL(at), PeekL(at + 4), 0, SurfaceProofOutside(8), 1)
  SurfaceProofFill() : PokeL(@count, 2) : rc = vkGetPhysicalDeviceSurfaceFormatsKHR(sp, surface, @count, at)
  SurfaceProofRecord(14, rc, PeekL(@count) & $FFFFFFFF, PeekL(at), PeekL(at + 8), PeekL(at + 12), SurfaceProofOutside(16), 1)
  SurfaceProofFill() : PokeL(@count, $FFFFFFFF) : rc = vkGetPhysicalDeviceSurfaceFormatsKHR(sp, surface, @count, at)
  SurfaceProofRecord(24, rc, PeekL(@count) & $FFFFFFFF, PeekL(at), PeekL(at + 8), PeekL(at + 12), SurfaceProofOutside(16), Bool(PeekL(@count + 4) = $11223344))
  SurfaceProofFill() : PokeL(@count, 0) : rc = vkGetPhysicalDeviceSurfacePresentModesKHR(sp, surface, @count, 0)
  SurfaceProofRecord(15, rc, PeekL(@count) & $FFFFFFFF, 0, 0, 0, SurfaceProofOutside(0), Bool(PeekL(@count + 4) = $11223344))
  PokeL(@count, 1) : rc = vkGetPhysicalDeviceSurfacePresentModesKHR(sp, surface, @count, at)
  SurfaceProofRecord(16, rc, PeekL(@count) & $FFFFFFFF, PeekL(at), 0, 0, SurfaceProofOutside(4), 1)
  SurfaceProofFill() : PokeL(@count, 2) : rc = vkGetPhysicalDeviceSurfacePresentModesKHR(sp, surface, @count, at)
  SurfaceProofRecord(17, rc, PeekL(@count) & $FFFFFFFF, PeekL(at), PeekL(at + 4), 0, SurfaceProofOutside(8), 1)
  slot = avkWsiProviderSlot(provider) : avkWsiProvCaps[slot]\currentWidth = $100000000
  SurfaceProofFill() : rc = vkGetPhysicalDeviceSurfaceCapabilitiesKHR(sp, surface, at)
  SurfaceProofRecord(18, rc, 0, 0, 0, 0, SurfaceProofOutside(0), 1)
  avkWsiProvCaps[slot]\currentWidth = 64
  pointerCount = Bool(vkGetInstanceProcAddr(si, "vkDestroySurfaceKHR") <> 0)
  pointerCount = pointerCount + Bool(vkGetInstanceProcAddr(si, "vkGetPhysicalDeviceSurfaceSupportKHR") <> 0)
  pointerCount = pointerCount + Bool(vkGetInstanceProcAddr(si, "vkGetPhysicalDeviceSurfaceCapabilitiesKHR") <> 0)
  pointerCount = pointerCount + Bool(vkGetInstanceProcAddr(si, "vkGetPhysicalDeviceSurfaceFormatsKHR") <> 0)
  pointerCount = pointerCount + Bool(vkGetInstanceProcAddr(si, "vkGetPhysicalDeviceSurfacePresentModesKHR") <> 0)
  rc = AnvilVkDeviceCreate(sp, @testDevice)
  SurfaceProofRecord(19, rc, pointerCount, Bool(vkGetInstanceProcAddr(offInst, "vkDestroySurfaceKHR") <> 0), Bool(vkGetInstanceProcAddr(0, "vkDestroySurfaceKHR") <> 0), Bool(vkGetDeviceProcAddr(testDevice, "vkDestroySurfaceKHR") <> 0), 1, Bool(vkGetInstanceProcAddr(si, "vkCreateSwapchainKHR") = 0))
  rc = avkWsiProviderLose(provider)
  SurfaceProofFill() : rc = vkGetPhysicalDeviceSurfaceSupportKHR(sp, 0, surface, at)
  SurfaceProofRecord(20, rc, 0, 0, 0, 0, SurfaceProofOutside(0), 1)
  vkDestroySurfaceKHR(si, surface, 0)
  rc = vkGetPhysicalDeviceSurfaceSupportKHR(sp, 0, surface, at)
  SurfaceProofRecord(21, rc, 0, 0, 0, 0, SurfaceProofOutside(0), 1)
  rc = SurfaceProofInstance(1, @old, @tempPhys) : If rc <> 0 : ProcedureReturn 504 : EndIf
  rc = AnvilVkInstanceDestroy(old)
  rc = SurfaceProofInstance(0, @fresh, @tempPhys) : If rc <> 0 : ProcedureReturn 505 : EndIf
  SurfaceProofRecord(22, rc, Bool(vkGetInstanceProcAddr(old, "vkDestroySurfaceKHR") <> 0), Bool(vkGetInstanceProcAddr(fresh, "vkDestroySurfaceKHR") <> 0), avkSurfaceEnabled(fresh), Bool(old <> fresh), 1, 1)
  AnvilVkFaultClear() : vkDestroySurfaceKHR(foreignInst, foreignSurface, 0)
  rc = AnvilVkFaultCode()
  rc = rc | avkWsiSurfaceDestroy(offInst, privateSurface)
  rc = rc | AnvilVkDeviceDestroy(testDevice)
  rc = rc | AnvilVkInstanceDestroy(si) : rc = rc | AnvilVkInstanceDestroy(offInst)
  rc = rc | AnvilVkInstanceDestroy(foreignInst) : rc = rc | AnvilVkInstanceDestroy(fresh)
  rc = rc | avkWsiProviderDestroy(provider)
  remaining = 0
  For n = 1 To #ANVIL_VK_MAX_INSTANCES : remaining = remaining + avkInstLive[n] : Next
  SurfaceProofRecord(23, rc, remaining, 0, 0, 0, 1, 1)
  PokeI(#TC_REPORT, $53555246) : PokeI(#TC_REPORT + 8, 0)
  PokeI(#TC_REPORT + 16, 24) : PokeI(#TC_REPORT + 24, 8)
  ProcedureReturn 0
EndProcedure

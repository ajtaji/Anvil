; ======================================================================
;  Target-neutral Vulkan KHR surface/swapchain state engine
; ======================================================================
; SPDX-License-Identifier: MIT
;
; This file is deliberately NOT included by vk_api.pbi, advertised as an
; extension, or connected to a display driver.  It is the object, ownership
; and transaction layer a future HDMI/DSI WSI provider can call.  A provider
; completion is explicit: this module never claims a scanout or asynchronous
; presentation happened merely because state was queued.
;
; Contract source: Vulkan-Docs v1.4.350, commit 81b1d516, chapter
; VK_KHR_surface/wsi.adoc and the VK_KHR_surface/VK_KHR_swapchain reference
; pages.  Surface capabilities belong to the presentation provider; a
; swapchain owns provider-created presentable images; acquire transfers one
; available image to the application; present returns it to the presentation
; engine; oldSwapchain retirement stops new acquisitions but does not prevent
; already-acquired images being presented; resize and surface loss are loud.
;
; Future include seam: vk_api/backend first, then this file, then a provider
; adapter.  Nothing in this file calls HDMI, DSI, a GPU, DMA, or the CPU copy
; path.

#ANVIL_VK_TYPE_WSI_SURFACE = 23
#ANVIL_VK_TYPE_WSI_SWAPCHAIN = 24
#ANVIL_VK_TYPE_WSI_PRESENT = 25
#ANVIL_VK_TYPE_WSI_PROVIDER = 26

#ANVIL_VK_WSI_MAX_PROVIDERS = 4
#ANVIL_VK_WSI_MAX_SURFACES = 8
#ANVIL_VK_WSI_MAX_SWAPCHAINS = 8
#ANVIL_VK_WSI_MAX_IMAGES = 4
#ANVIL_VK_WSI_MAX_FORMATS = 4
#ANVIL_VK_WSI_MAX_MODES = 4
#ANVIL_VK_WSI_MAX_PRESENTS = 4
#ANVIL_VK_WSI_MAX_PRESENT_ITEMS = 8

#VK_NOT_READY = 1
#VK_TIMEOUT = 2
#VK_SUBOPTIMAL_KHR = 1000001003
#VK_ERROR_SURFACE_LOST_KHR = -1000000000
#VK_ERROR_NATIVE_WINDOW_IN_USE_KHR = -1000000001
#VK_ERROR_OUT_OF_DATE_KHR = -1000001004

#VK_COLOR_SPACE_SRGB_NONLINEAR_KHR = 0
#VK_PRESENT_MODE_IMMEDIATE_KHR = 0
#VK_PRESENT_MODE_MAILBOX_KHR = 1
#VK_PRESENT_MODE_FIFO_KHR = 2
#VK_PRESENT_MODE_FIFO_RELAXED_KHR = 3
#VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR = 1
#VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR = 1

#ANVIL_VK_WSI_IMAGE_AVAILABLE = 0
#ANVIL_VK_WSI_IMAGE_ACQUIRED = 1
#ANVIL_VK_WSI_IMAGE_RENDER_READY = 2
#ANVIL_VK_WSI_IMAGE_PRESENT_PENDING = 3

#ANVIL_VK_WSI_PRESENT_FREE = 0
#ANVIL_VK_WSI_PRESENT_RESERVED = 1
#ANVIL_VK_WSI_PRESENT_COMMITTED = 2

Structure AnvilVkWsiCapabilities Align #PB_Structure_AlignC
  minImageCount.i
  maxImageCount.i
  currentWidth.i
  currentHeight.i
  minWidth.i
  minHeight.i
  maxWidth.i
  maxHeight.i
  maxImageArrayLayers.i
  supportedTransforms.i
  currentTransform.i
  supportedCompositeAlpha.i
  supportedUsageFlags.i
EndStructure

Structure AnvilVkWsiFormat Align #PB_Structure_AlignC
  format.i
  colorSpace.i
EndStructure

Structure AnvilVkWsiProviderInfo Align #PB_Structure_AlignC
  cookie.i
  capabilities.AnvilVkWsiCapabilities
  formatCount.i
  *formats.AnvilVkWsiFormat
  presentModeCount.i
  *presentModes
EndStructure

Structure AnvilVkWsiSwapchainInfo Align #PB_Structure_AlignC
  surface.i
  minImageCount.i
  imageFormat.i
  imageColorSpace.i
  imageWidth.i
  imageHeight.i
  imageArrayLayers.i
  imageUsage.i
  imageSharingMode.i
  preTransform.i
  compositeAlpha.i
  presentMode.i
  clipped.i
  oldSwapchain.i
  providerImageCount.i
  *providerImages
EndStructure

Structure AnvilVkWsiPresentItem Align #PB_Structure_AlignC
  swapchain.i
  imageIndex.i
EndStructure

Global Dim avkWsiProvLive.a[#ANVIL_VK_WSI_MAX_PROVIDERS + 1]
Global Dim avkWsiProvGen.i[#ANVIL_VK_WSI_MAX_PROVIDERS + 1]
Global Dim avkWsiProvCookie.i[#ANVIL_VK_WSI_MAX_PROVIDERS + 1]
Global Dim avkWsiProvLost.a[#ANVIL_VK_WSI_MAX_PROVIDERS + 1]
Global Dim avkWsiProvEpoch.i[#ANVIL_VK_WSI_MAX_PROVIDERS + 1]
Global Dim avkWsiProvCaps.AnvilVkWsiCapabilities[#ANVIL_VK_WSI_MAX_PROVIDERS + 1]
Global Dim avkWsiProvFormatCount.i[#ANVIL_VK_WSI_MAX_PROVIDERS + 1]
Global Dim avkWsiProvFormat.i[(#ANVIL_VK_WSI_MAX_PROVIDERS + 1) * #ANVIL_VK_WSI_MAX_FORMATS]
Global Dim avkWsiProvColor.i[(#ANVIL_VK_WSI_MAX_PROVIDERS + 1) * #ANVIL_VK_WSI_MAX_FORMATS]
Global Dim avkWsiProvModeCount.i[#ANVIL_VK_WSI_MAX_PROVIDERS + 1]
Global Dim avkWsiProvMode.i[(#ANVIL_VK_WSI_MAX_PROVIDERS + 1) * #ANVIL_VK_WSI_MAX_MODES]

Global Dim avkWsiSurfLive.a[#ANVIL_VK_WSI_MAX_SURFACES + 1]
Global Dim avkWsiSurfGen.i[#ANVIL_VK_WSI_MAX_SURFACES + 1]
Global Dim avkWsiSurfInst.i[#ANVIL_VK_WSI_MAX_SURFACES + 1]
Global Dim avkWsiSurfInstGen.i[#ANVIL_VK_WSI_MAX_SURFACES + 1]
Global Dim avkWsiSurfProvider.i[#ANVIL_VK_WSI_MAX_SURFACES + 1]
Global Dim avkWsiSurfProvSlot.i[#ANVIL_VK_WSI_MAX_SURFACES + 1]
Global Dim avkWsiSurfNative.i[#ANVIL_VK_WSI_MAX_SURFACES + 1]
Global Dim avkWsiSurfLost.a[#ANVIL_VK_WSI_MAX_SURFACES + 1]
Global Dim avkWsiSurfSerial.i[#ANVIL_VK_WSI_MAX_SURFACES + 1]
Global Dim avkWsiSurfActiveSwap.i[#ANVIL_VK_WSI_MAX_SURFACES + 1]

Global Dim avkWsiSwapLive.a[#ANVIL_VK_WSI_MAX_SWAPCHAINS + 1]
Global Dim avkWsiSwapGen.i[#ANVIL_VK_WSI_MAX_SWAPCHAINS + 1]
Global Dim avkWsiSwapDev.i[#ANVIL_VK_WSI_MAX_SWAPCHAINS + 1]
Global Dim avkWsiSwapDevGen.i[#ANVIL_VK_WSI_MAX_SWAPCHAINS + 1]
Global Dim avkWsiSwapSurface.i[#ANVIL_VK_WSI_MAX_SWAPCHAINS + 1]
Global Dim avkWsiSwapSurfSlot.i[#ANVIL_VK_WSI_MAX_SWAPCHAINS + 1]
Global Dim avkWsiSwapSerial.i[#ANVIL_VK_WSI_MAX_SWAPCHAINS + 1]
Global Dim avkWsiSwapRetired.a[#ANVIL_VK_WSI_MAX_SWAPCHAINS + 1]
Global Dim avkWsiSwapOutOfDate.a[#ANVIL_VK_WSI_MAX_SWAPCHAINS + 1]
Global Dim avkWsiSwapImageCount.i[#ANVIL_VK_WSI_MAX_SWAPCHAINS + 1]
Global Dim avkWsiSwapCursor.i[#ANVIL_VK_WSI_MAX_SWAPCHAINS + 1]
Global Dim avkWsiSwapFormat.i[#ANVIL_VK_WSI_MAX_SWAPCHAINS + 1]
Global Dim avkWsiSwapColor.i[#ANVIL_VK_WSI_MAX_SWAPCHAINS + 1]
Global Dim avkWsiSwapWidth.i[#ANVIL_VK_WSI_MAX_SWAPCHAINS + 1]
Global Dim avkWsiSwapHeight.i[#ANVIL_VK_WSI_MAX_SWAPCHAINS + 1]
Global Dim avkWsiSwapMode.i[#ANVIL_VK_WSI_MAX_SWAPCHAINS + 1]
Global Dim avkWsiSwapImage.i[(#ANVIL_VK_WSI_MAX_SWAPCHAINS + 1) * #ANVIL_VK_WSI_MAX_IMAGES]
Global Dim avkWsiSwapImageState.a[(#ANVIL_VK_WSI_MAX_SWAPCHAINS + 1) * #ANVIL_VK_WSI_MAX_IMAGES]

Global Dim avkWsiPresentStage.a[#ANVIL_VK_WSI_MAX_PRESENTS + 1]
Global Dim avkWsiPresentGen.i[#ANVIL_VK_WSI_MAX_PRESENTS + 1]
Global Dim avkWsiPresentDev.i[#ANVIL_VK_WSI_MAX_PRESENTS + 1]
Global Dim avkWsiPresentDevGen.i[#ANVIL_VK_WSI_MAX_PRESENTS + 1]
Global Dim avkWsiPresentCount.i[#ANVIL_VK_WSI_MAX_PRESENTS + 1]
Global Dim avkWsiPresentSwap.i[(#ANVIL_VK_WSI_MAX_PRESENTS + 1) * #ANVIL_VK_WSI_MAX_PRESENT_ITEMS]
Global Dim avkWsiPresentSwapSlot.i[(#ANVIL_VK_WSI_MAX_PRESENTS + 1) * #ANVIL_VK_WSI_MAX_PRESENT_ITEMS]
Global Dim avkWsiPresentImage.i[(#ANVIL_VK_WSI_MAX_PRESENTS + 1) * #ANVIL_VK_WSI_MAX_PRESENT_ITEMS]

Procedure.i avkWsiFormatIndex(p.i, n.i) : ProcedureReturn p * #ANVIL_VK_WSI_MAX_FORMATS + n : EndProcedure
Procedure.i avkWsiModeIndex(p.i, n.i) : ProcedureReturn p * #ANVIL_VK_WSI_MAX_MODES + n : EndProcedure
Procedure.i avkWsiImageIndex(s.i, n.i) : ProcedureReturn s * #ANVIL_VK_WSI_MAX_IMAGES + n : EndProcedure
Procedure.i avkWsiPresentIndex(t.i, n.i) : ProcedureReturn t * #ANVIL_VK_WSI_MAX_PRESENT_ITEMS + n : EndProcedure

Procedure.i avkWsiProviderSlot(h.i)
  Define s.i
  s = avkTokenShape(h, #ANVIL_VK_TYPE_WSI_PROVIDER, #ANVIL_VK_WSI_MAX_PROVIDERS)
  If s = 0 : ProcedureReturn 0 : EndIf
  If avkWsiProvLive[s] = 0 Or avkWsiProvGen[s] <> avkTokenGen(h) : ProcedureReturn 0 : EndIf
  ProcedureReturn s
EndProcedure

Procedure.i avkWsiSurfaceSlot(h.i)
  Define s.i
  s = avkTokenShape(h, #ANVIL_VK_TYPE_WSI_SURFACE, #ANVIL_VK_WSI_MAX_SURFACES)
  If s = 0 : ProcedureReturn 0 : EndIf
  If avkWsiSurfLive[s] = 0 Or avkWsiSurfGen[s] <> avkTokenGen(h) : ProcedureReturn 0 : EndIf
  ProcedureReturn s
EndProcedure

Procedure.i avkWsiSwapchainSlot(h.i)
  Define s.i
  s = avkTokenShape(h, #ANVIL_VK_TYPE_WSI_SWAPCHAIN, #ANVIL_VK_WSI_MAX_SWAPCHAINS)
  If s = 0 : ProcedureReturn 0 : EndIf
  If avkWsiSwapLive[s] = 0 Or avkWsiSwapGen[s] <> avkTokenGen(h) : ProcedureReturn 0 : EndIf
  ProcedureReturn s
EndProcedure

Procedure.i avkWsiPresentSlot(h.i)
  Define s.i
  s = avkTokenShape(h, #ANVIL_VK_TYPE_WSI_PRESENT, #ANVIL_VK_WSI_MAX_PRESENTS)
  If s = 0 : ProcedureReturn 0 : EndIf
  If avkWsiPresentStage[s] = #ANVIL_VK_WSI_PRESENT_FREE Or avkWsiPresentGen[s] <> avkTokenGen(h) : ProcedureReturn 0 : EndIf
  ProcedureReturn s
EndProcedure

Procedure avkWsiPresentClear(t.i)
  Define n.i
  If t < 1 Or t > #ANVIL_VK_WSI_MAX_PRESENTS
    ProcedureReturn
  EndIf
  n = 0
  While n < #ANVIL_VK_WSI_MAX_PRESENT_ITEMS
    avkWsiPresentSwap[avkWsiPresentIndex(t, n)] = 0
    avkWsiPresentSwapSlot[avkWsiPresentIndex(t, n)] = 0
    avkWsiPresentImage[avkWsiPresentIndex(t, n)] = 0
    n = n + 1
  Wend
  avkWsiPresentDev[t] = 0
  avkWsiPresentDevGen[t] = 0
  avkWsiPresentCount[t] = 0
  avkWsiPresentStage[t] = #ANVIL_VK_WSI_PRESENT_FREE
EndProcedure

Procedure avkWsiCopyCapabilities(*dest.AnvilVkWsiCapabilities, *source.AnvilVkWsiCapabilities)
  *dest\minImageCount = *source\minImageCount
  *dest\maxImageCount = *source\maxImageCount
  *dest\currentWidth = *source\currentWidth
  *dest\currentHeight = *source\currentHeight
  *dest\minWidth = *source\minWidth
  *dest\minHeight = *source\minHeight
  *dest\maxWidth = *source\maxWidth
  *dest\maxHeight = *source\maxHeight
  *dest\maxImageArrayLayers = *source\maxImageArrayLayers
  *dest\supportedTransforms = *source\supportedTransforms
  *dest\currentTransform = *source\currentTransform
  *dest\supportedCompositeAlpha = *source\supportedCompositeAlpha
  *dest\supportedUsageFlags = *source\supportedUsageFlags
EndProcedure

Procedure.i avkWsiProviderInfoValid(*info.AnvilVkWsiProviderInfo)
  Define i.i
  Define j.i
  Define a.i
  Define b.i
  Define ac.i
  Define bc.i
  Define hasFifo.i
  If *info = 0 : ProcedureReturn 0 : EndIf
  If *info\cookie = 0 : ProcedureReturn 0 : EndIf
  If *info\capabilities\minImageCount < 1 Or *info\capabilities\minImageCount > #ANVIL_VK_WSI_MAX_IMAGES : ProcedureReturn 0 : EndIf
  If *info\capabilities\maxImageCount <> 0
    If *info\capabilities\maxImageCount < *info\capabilities\minImageCount Or *info\capabilities\maxImageCount > #ANVIL_VK_WSI_MAX_IMAGES : ProcedureReturn 0 : EndIf
  EndIf
  If *info\capabilities\currentWidth < 1 Or *info\capabilities\currentHeight < 1 : ProcedureReturn 0 : EndIf
  If *info\capabilities\minWidth < 1 Or *info\capabilities\minHeight < 1 : ProcedureReturn 0 : EndIf
  If *info\capabilities\currentWidth < *info\capabilities\minWidth Or *info\capabilities\currentWidth > *info\capabilities\maxWidth : ProcedureReturn 0 : EndIf
  If *info\capabilities\currentHeight < *info\capabilities\minHeight Or *info\capabilities\currentHeight > *info\capabilities\maxHeight : ProcedureReturn 0 : EndIf
  If *info\capabilities\maxImageArrayLayers < 1 : ProcedureReturn 0 : EndIf
  If *info\capabilities\supportedTransforms = 0 Or (*info\capabilities\supportedTransforms & *info\capabilities\currentTransform) = 0 : ProcedureReturn 0 : EndIf
  If *info\capabilities\supportedCompositeAlpha = 0 : ProcedureReturn 0 : EndIf
  If (*info\capabilities\supportedUsageFlags & #VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT) = 0 : ProcedureReturn 0 : EndIf
  If *info\formatCount < 1 Or *info\formatCount > #ANVIL_VK_WSI_MAX_FORMATS Or *info\formats = 0 : ProcedureReturn 0 : EndIf
  If *info\presentModeCount < 1 Or *info\presentModeCount > #ANVIL_VK_WSI_MAX_MODES Or *info\presentModes = 0 : ProcedureReturn 0 : EndIf
  i = 0
  While i < *info\formatCount
    a = PeekI(*info\formats + i * SizeOf(AnvilVkWsiFormat))
    ac = PeekI(*info\formats + i * SizeOf(AnvilVkWsiFormat) + OffsetOf(AnvilVkWsiFormat\colorSpace))
    If a = 0 : ProcedureReturn 0 : EndIf
    j = i + 1
    While j < *info\formatCount
      b = PeekI(*info\formats + j * SizeOf(AnvilVkWsiFormat))
      bc = PeekI(*info\formats + j * SizeOf(AnvilVkWsiFormat) + OffsetOf(AnvilVkWsiFormat\colorSpace))
      If a = b And ac = bc : ProcedureReturn 0 : EndIf
      j = j + 1
    Wend
    i = i + 1
  Wend
  i = 0
  hasFifo = 0
  While i < *info\presentModeCount
    a = PeekI(*info\presentModes + i * SizeOf(.i))
    If a < #VK_PRESENT_MODE_IMMEDIATE_KHR Or a > #VK_PRESENT_MODE_FIFO_RELAXED_KHR : ProcedureReturn 0 : EndIf
    If a = #VK_PRESENT_MODE_FIFO_KHR : hasFifo = 1 : EndIf
    j = i + 1
    While j < *info\presentModeCount
      b = PeekI(*info\presentModes + j * SizeOf(.i))
      If a = b : ProcedureReturn 0 : EndIf
      j = j + 1
    Wend
    i = i + 1
  Wend
  ; VK_KHR_surface requires FIFO support for every surface.  Reject an
  ; incomplete provider contract rather than advertising capabilities that
  ; cannot satisfy the extension's portable baseline.
  If hasFifo = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i avkWsiProviderRegister(*info.AnvilVkWsiProviderInfo, *out)
  Define p.i
  Define i.i
  If *out = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, #VK_NULL_HANDLE)
  If avkWsiProviderInfoValid(*info) = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "the WSI provider registration was incomplete or internally inconsistent (Anvil code -20001, invalid provider capabilities); no provider was registered.")
  EndIf
  p = 1
  While p <= #ANVIL_VK_WSI_MAX_PROVIDERS And avkWsiProvLive[p] <> 0 : p = p + 1 : Wend
  If p > #ANVIL_VK_WSI_MAX_PROVIDERS : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf
  avkWsiProvGen[p] = avkNextGen(avkWsiProvGen[p])
  avkWsiProvLive[p] = 1
  avkWsiProvCookie[p] = *info\cookie
  avkWsiProvLost[p] = 0
  avkWsiProvEpoch[p] = avkNextGen(avkWsiProvEpoch[p])
  avkWsiCopyCapabilities(@avkWsiProvCaps[p], @*info\capabilities)
  avkWsiProvFormatCount[p] = *info\formatCount
  i = 0
  While i < *info\formatCount
    avkWsiProvFormat[avkWsiFormatIndex(p, i)] = PeekI(*info\formats + i * SizeOf(AnvilVkWsiFormat))
    avkWsiProvColor[avkWsiFormatIndex(p, i)] = PeekI(*info\formats + i * SizeOf(AnvilVkWsiFormat) + OffsetOf(AnvilVkWsiFormat\colorSpace))
    i = i + 1
  Wend
  avkWsiProvModeCount[p] = *info\presentModeCount
  i = 0
  While i < *info\presentModeCount
    avkWsiProvMode[avkWsiModeIndex(p, i)] = PeekI(*info\presentModes + i * SizeOf(.i))
    i = i + 1
  Wend
  PokeI(*out, avkToken(#ANVIL_VK_TYPE_WSI_PROVIDER, p, avkWsiProvGen[p]))
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkWsiSurfaceCreate(instance.i, provider.i, nativeKey.i, *out)
  Define inst.i
  Define p.i
  Define s.i
  If *out = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, #VK_NULL_HANDLE)
  inst = avkInstSlot(instance)
  p = avkWsiProviderSlot(provider)
  If inst = 0 Or p = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkWsiProvLost[p] <> 0 : ProcedureReturn #VK_ERROR_SURFACE_LOST_KHR : EndIf
  If nativeKey = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  s = 1
  While s <= #ANVIL_VK_WSI_MAX_SURFACES
    If avkWsiSurfLive[s] <> 0 And avkWsiSurfProvider[s] = provider And avkWsiSurfNative[s] = nativeKey
      ProcedureReturn #VK_ERROR_NATIVE_WINDOW_IN_USE_KHR
    EndIf
    s = s + 1
  Wend
  s = 1
  While s <= #ANVIL_VK_WSI_MAX_SURFACES And avkWsiSurfLive[s] <> 0 : s = s + 1 : Wend
  If s > #ANVIL_VK_WSI_MAX_SURFACES : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf
  avkWsiSurfGen[s] = avkNextGen(avkWsiSurfGen[s])
  avkWsiSurfLive[s] = 1
  avkWsiSurfInst[s] = inst
  avkWsiSurfInstGen[s] = avkTokenGen(instance)
  avkWsiSurfProvider[s] = provider
  avkWsiSurfProvSlot[s] = p
  avkWsiSurfNative[s] = nativeKey
  avkWsiSurfLost[s] = 0
  avkWsiSurfSerial[s] = avkWsiProvEpoch[p]
  avkWsiSurfActiveSwap[s] = 0
  PokeI(*out, avkToken(#ANVIL_VK_TYPE_WSI_SURFACE, s, avkWsiSurfGen[s]))
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkWsiSurfaceProvider(instance.i, surface.i)
  Define inst.i
  Define s.i
  Define p.i
  inst = avkInstSlot(instance)
  s = avkWsiSurfaceSlot(surface)
  If inst = 0 Or s = 0 : ProcedureReturn 0 : EndIf
  If avkWsiSurfInst[s] <> inst Or avkWsiSurfInstGen[s] <> avkTokenGen(instance) : ProcedureReturn 0 : EndIf
  p = avkWsiProviderSlot(avkWsiSurfProvider[s])
  If p = 0 Or p <> avkWsiSurfProvSlot[s] : ProcedureReturn 0 : EndIf
  If avkWsiSurfLost[s] <> 0 Or avkWsiProvLost[p] <> 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn p
EndProcedure

Procedure.i avkWsiSurfaceCapabilities(instance.i, surface.i, *out.AnvilVkWsiCapabilities)
  Define p.i
  If *out = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  p = avkWsiSurfaceProvider(instance, surface)
  If p = 0 : ProcedureReturn #VK_ERROR_SURFACE_LOST_KHR : EndIf
  avkWsiCopyCapabilities(*out, @avkWsiProvCaps[p])
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkWsiSurfaceFormatCount(instance.i, surface.i)
  Define p.i
  p = avkWsiSurfaceProvider(instance, surface)
  If p = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkWsiProvFormatCount[p]
EndProcedure

Procedure.i avkWsiSurfaceFormatAt(instance.i, surface.i, index.i, *out.AnvilVkWsiFormat)
  Define p.i
  If *out = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  p = avkWsiSurfaceProvider(instance, surface)
  If p = 0 : ProcedureReturn #VK_ERROR_SURFACE_LOST_KHR : EndIf
  If index < 0 Or index >= avkWsiProvFormatCount[p] : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  *out\format = avkWsiProvFormat[avkWsiFormatIndex(p, index)]
  *out\colorSpace = avkWsiProvColor[avkWsiFormatIndex(p, index)]
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkWsiSurfacePresentModeCount(instance.i, surface.i)
  Define p.i
  p = avkWsiSurfaceProvider(instance, surface)
  If p = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkWsiProvModeCount[p]
EndProcedure

Procedure.i avkWsiSurfacePresentModeAt(instance.i, surface.i, index.i, *out)
  Define p.i
  If *out = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  p = avkWsiSurfaceProvider(instance, surface)
  If p = 0 : ProcedureReturn #VK_ERROR_SURFACE_LOST_KHR : EndIf
  If index < 0 Or index >= avkWsiProvModeCount[p] : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, avkWsiProvMode[avkWsiModeIndex(p, index)])
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkWsiSwapSurfaceCurrent(s.i)
  Define surf.i
  If s < 1 Or s > #ANVIL_VK_WSI_MAX_SWAPCHAINS : ProcedureReturn 0 : EndIf
  surf = avkWsiSurfaceSlot(avkWsiSwapSurface[s])
  If surf = 0 Or surf <> avkWsiSwapSurfSlot[s] : ProcedureReturn 0 : EndIf
  If avkWsiSurfLost[surf] <> 0 : ProcedureReturn 0 : EndIf
  If avkWsiSurfSerial[surf] <> avkWsiSwapSerial[s] : ProcedureReturn 0 : EndIf
  ProcedureReturn surf
EndProcedure

Procedure.i avkWsiSwapInfoValid(d.i, *info.AnvilVkWsiSwapchainInfo, *surfaceOut, *oldOut)
  Define surf.i
  Define p.i
  Define old.i
  Define i.i
  Define j.i
  Define found.i
  Define key.i
  If *info = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  surf = avkWsiSurfaceSlot(*info\surface)
  If surf = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkWsiSurfLost[surf] <> 0 : ProcedureReturn #VK_ERROR_SURFACE_LOST_KHR : EndIf
  p = avkWsiProviderSlot(avkWsiSurfProvider[surf])
  If p = 0 Or p <> avkWsiSurfProvSlot[surf] Or avkWsiProvLost[p] <> 0 : ProcedureReturn #VK_ERROR_SURFACE_LOST_KHR : EndIf
  If avkWsiSurfInst[surf] <> avkPhysInst[avkDevPhys[d]] Or avkWsiSurfInstGen[surf] <> avkInstGen[avkWsiSurfInst[surf]] : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
  If *info\minImageCount < avkWsiProvCaps[p]\minImageCount : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  If avkWsiProvCaps[p]\maxImageCount <> 0
    If *info\minImageCount > avkWsiProvCaps[p]\maxImageCount : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  EndIf
  If *info\providerImageCount < *info\minImageCount Or *info\providerImageCount > #ANVIL_VK_WSI_MAX_IMAGES Or *info\providerImages = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  If avkWsiProvCaps[p]\maxImageCount <> 0
    If *info\providerImageCount > avkWsiProvCaps[p]\maxImageCount : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  EndIf
  If *info\imageWidth <> avkWsiProvCaps[p]\currentWidth Or *info\imageHeight <> avkWsiProvCaps[p]\currentHeight : ProcedureReturn #VK_ERROR_OUT_OF_DATE_KHR : EndIf
  If *info\imageArrayLayers <> 1 Or *info\imageSharingMode <> #VK_SHARING_MODE_EXCLUSIVE : ProcedureReturn #ANVIL_VK_ERR_UNSUPPORTED : EndIf
  If *info\imageUsage = 0 Or (*info\imageUsage & (~avkWsiProvCaps[p]\supportedUsageFlags)) <> 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  ; VkSwapchainCreateInfoKHR selects one transform and one composite-alpha
  ; mode, not an arbitrary supported bit set.
  If *info\preTransform = 0 Or (*info\preTransform & (*info\preTransform - 1)) <> 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  If (*info\preTransform & avkWsiProvCaps[p]\supportedTransforms) = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  If *info\compositeAlpha = 0 Or (*info\compositeAlpha & (*info\compositeAlpha - 1)) <> 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  If (*info\compositeAlpha & avkWsiProvCaps[p]\supportedCompositeAlpha) = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  If *info\clipped <> 0 And *info\clipped <> 1 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  found = 0
  i = 0
  While i < avkWsiProvFormatCount[p]
    If avkWsiProvFormat[avkWsiFormatIndex(p, i)] = *info\imageFormat And avkWsiProvColor[avkWsiFormatIndex(p, i)] = *info\imageColorSpace : found = 1 : EndIf
    i = i + 1
  Wend
  If found = 0 : ProcedureReturn #ANVIL_VK_ERR_UNSUPPORTED : EndIf
  found = 0
  i = 0
  While i < avkWsiProvModeCount[p]
    If avkWsiProvMode[avkWsiModeIndex(p, i)] = *info\presentMode : found = 1 : EndIf
    i = i + 1
  Wend
  If found = 0 : ProcedureReturn #ANVIL_VK_ERR_UNSUPPORTED : EndIf
  old = 0
  If *info\oldSwapchain <> #VK_NULL_HANDLE
    old = avkWsiSwapchainSlot(*info\oldSwapchain)
    If old = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
    If avkWsiSwapDev[old] <> d Or avkWsiSwapDevGen[old] <> avkDevGen[d] : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
    If avkWsiSwapSurface[old] <> *info\surface Or avkWsiSwapRetired[old] <> 0 : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
    If avkWsiSurfActiveSwap[surf] <> *info\oldSwapchain : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
  ElseIf avkWsiSurfActiveSwap[surf] <> 0
    ProcedureReturn #VK_ERROR_NATIVE_WINDOW_IN_USE_KHR
  EndIf
  i = 0
  While i < *info\providerImageCount
    key = PeekI(*info\providerImages + i * SizeOf(.i))
    If key = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
    j = i + 1
    While j < *info\providerImageCount
      If key = PeekI(*info\providerImages + j * SizeOf(.i)) : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
      j = j + 1
    Wend
    j = 1
    While j <= #ANVIL_VK_WSI_MAX_SWAPCHAINS
      If avkWsiSwapLive[j] <> 0
        found = 0
        While found < avkWsiSwapImageCount[j]
          If avkWsiSwapImage[avkWsiImageIndex(j, found)] = key : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
          found = found + 1
        Wend
      EndIf
      j = j + 1
    Wend
    i = i + 1
  Wend
  PokeI(*surfaceOut, surf)
  PokeI(*oldOut, old)
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkWsiSwapchainCreate(device.i, *info.AnvilVkWsiSwapchainInfo, *out)
  Define d.i
  Define surf.i
  Define old.i
  Define s.i
  Define i.i
  Define rc.i
  If *out = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, #VK_NULL_HANDLE)
  d = avkDevSlot(device)
  If d = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  rc = avkWsiSwapInfoValid(d, *info, @surf, @old)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  s = 1
  While s <= #ANVIL_VK_WSI_MAX_SWAPCHAINS And avkWsiSwapLive[s] <> 0 : s = s + 1 : Wend
  If s > #ANVIL_VK_WSI_MAX_SWAPCHAINS : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf
  ; No externally visible state changes occur before this point.  Retiring the
  ; old chain and publishing the new active handle are one commit section.
  avkWsiSwapGen[s] = avkNextGen(avkWsiSwapGen[s])
  avkWsiSwapLive[s] = 1
  avkWsiSwapDev[s] = d
  avkWsiSwapDevGen[s] = avkTokenGen(device)
  avkWsiSwapSurface[s] = *info\surface
  avkWsiSwapSurfSlot[s] = surf
  avkWsiSwapSerial[s] = avkWsiSurfSerial[surf]
  avkWsiSwapRetired[s] = 0
  avkWsiSwapOutOfDate[s] = 0
  avkWsiSwapImageCount[s] = *info\providerImageCount
  avkWsiSwapCursor[s] = 0
  avkWsiSwapFormat[s] = *info\imageFormat
  avkWsiSwapColor[s] = *info\imageColorSpace
  avkWsiSwapWidth[s] = *info\imageWidth
  avkWsiSwapHeight[s] = *info\imageHeight
  avkWsiSwapMode[s] = *info\presentMode
  i = 0
  While i < #ANVIL_VK_WSI_MAX_IMAGES
    If i < *info\providerImageCount
      avkWsiSwapImage[avkWsiImageIndex(s, i)] = PeekI(*info\providerImages + i * SizeOf(.i))
    Else
      avkWsiSwapImage[avkWsiImageIndex(s, i)] = 0
    EndIf
    avkWsiSwapImageState[avkWsiImageIndex(s, i)] = #ANVIL_VK_WSI_IMAGE_AVAILABLE
    i = i + 1
  Wend
  If old <> 0 : avkWsiSwapRetired[old] = 1 : EndIf
  PokeI(*out, avkToken(#ANVIL_VK_TYPE_WSI_SWAPCHAIN, s, avkWsiSwapGen[s]))
  avkWsiSurfActiveSwap[surf] = PeekI(*out)
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkWsiAcquire(device.i, swapchain.i, timeout.i, *imageIndex)
  Define d.i
  Define s.i
  Define surf.i
  Define n.i
  Define i.i
  If *imageIndex = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeL(*imageIndex, $FFFFFFFF)
  d = avkDevSlot(device)
  s = avkWsiSwapchainSlot(swapchain)
  If d = 0 Or s = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkWsiSwapDev[s] <> d Or avkWsiSwapDevGen[s] <> avkTokenGen(device) : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
  surf = avkWsiSurfaceSlot(avkWsiSwapSurface[s])
  If surf = 0 Or avkWsiSurfLost[surf] <> 0 : ProcedureReturn #VK_ERROR_SURFACE_LOST_KHR : EndIf
  If avkWsiSwapRetired[s] <> 0 Or avkWsiSwapOutOfDate[s] <> 0 Or avkWsiSwapSurfaceCurrent(s) = 0 : ProcedureReturn #VK_ERROR_OUT_OF_DATE_KHR : EndIf
  i = 0
  While i < avkWsiSwapImageCount[s]
    n = (avkWsiSwapCursor[s] + i) % avkWsiSwapImageCount[s]
    If avkWsiSwapImageState[avkWsiImageIndex(s, n)] = #ANVIL_VK_WSI_IMAGE_AVAILABLE
      avkWsiSwapImageState[avkWsiImageIndex(s, n)] = #ANVIL_VK_WSI_IMAGE_ACQUIRED
      avkWsiSwapCursor[s] = (n + 1) % avkWsiSwapImageCount[s]
      PokeL(*imageIndex, n)
      ProcedureReturn #VK_SUCCESS
    EndIf
    i = i + 1
  Wend
  If timeout = 0 : ProcedureReturn #VK_NOT_READY : EndIf
  ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "swapchain acquisition would have to wait for a provider completion (Anvil code -20005, blocking acquire not integrated); no image was acquired and no timeout was faked.")
EndProcedure

Procedure.i avkWsiImageKey(device.i, swapchain.i, imageIndex.i)
  Define d.i
  Define s.i
  d = avkDevSlot(device)
  s = avkWsiSwapchainSlot(swapchain)
  If d = 0 Or s = 0 : ProcedureReturn 0 : EndIf
  If avkWsiSwapDev[s] <> d Or avkWsiSwapDevGen[s] <> avkTokenGen(device) : ProcedureReturn 0 : EndIf
  If imageIndex < 0 Or imageIndex >= avkWsiSwapImageCount[s] : ProcedureReturn 0 : EndIf
  ProcedureReturn avkWsiSwapImage[avkWsiImageIndex(s, imageIndex)]
EndProcedure

Procedure.i avkWsiImageState(device.i, swapchain.i, imageIndex.i)
  Define s.i
  If avkWsiImageKey(device, swapchain, imageIndex) = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  s = avkWsiSwapchainSlot(swapchain)
  ProcedureReturn avkWsiSwapImageState[avkWsiImageIndex(s, imageIndex)]
EndProcedure

Procedure.i avkWsiMarkRenderReady(device.i, swapchain.i, imageIndex.i)
  Define s.i
  If avkWsiImageKey(device, swapchain, imageIndex) = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  s = avkWsiSwapchainSlot(swapchain)
  If avkWsiSwapImageState[avkWsiImageIndex(s, imageIndex)] <> #ANVIL_VK_WSI_IMAGE_ACQUIRED : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
  avkWsiSwapImageState[avkWsiImageIndex(s, imageIndex)] = #ANVIL_VK_WSI_IMAGE_RENDER_READY
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkWsiReleaseImage(device.i, swapchain.i, imageIndex.i)
  Define s.i
  Define state.i
  If avkWsiImageKey(device, swapchain, imageIndex) = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  s = avkWsiSwapchainSlot(swapchain)
  state = avkWsiSwapImageState[avkWsiImageIndex(s, imageIndex)]
  If state <> #ANVIL_VK_WSI_IMAGE_ACQUIRED And state <> #ANVIL_VK_WSI_IMAGE_RENDER_READY : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
  If avkWsiPresentReservedByAny(s, imageIndex) <> 0 : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
  avkWsiSwapImageState[avkWsiImageIndex(s, imageIndex)] = #ANVIL_VK_WSI_IMAGE_AVAILABLE
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkWsiPresentReservedByAny(s.i, imageIndex.i)
  Define t.i
  Define n.i
  t = 1
  While t <= #ANVIL_VK_WSI_MAX_PRESENTS
    If avkWsiPresentStage[t] = #ANVIL_VK_WSI_PRESENT_RESERVED
      n = 0
      While n < avkWsiPresentCount[t]
        If avkWsiPresentSwapSlot[avkWsiPresentIndex(t, n)] = s And avkWsiPresentImage[avkWsiPresentIndex(t, n)] = imageIndex : ProcedureReturn 1 : EndIf
        n = n + 1
      Wend
    EndIf
    t = t + 1
  Wend
  ProcedureReturn 0
EndProcedure

Procedure.i avkWsiPresentReserve(device.i, count.i, *items.AnvilVkWsiPresentItem, *out)
  Define d.i
  Define t.i
  Define i.i
  Define j.i
  Define s.i
  Define surf.i
  Define index.i
  Define h.i
  If *out = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, #VK_NULL_HANDLE)
  d = avkDevSlot(device)
  If d = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If count < 1 Or count > #ANVIL_VK_WSI_MAX_PRESENT_ITEMS Or *items = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  t = 1
  While t <= #ANVIL_VK_WSI_MAX_PRESENTS And avkWsiPresentStage[t] <> #ANVIL_VK_WSI_PRESENT_FREE : t = t + 1 : Wend
  If t > #ANVIL_VK_WSI_MAX_PRESENTS : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf
  avkWsiPresentClear(t)
  avkWsiPresentDev[t] = d
  avkWsiPresentDevGen[t] = avkTokenGen(device)
  avkWsiPresentCount[t] = count
  i = 0
  While i < count
    h = PeekI(*items + i * SizeOf(AnvilVkWsiPresentItem))
    index = PeekI(*items + i * SizeOf(AnvilVkWsiPresentItem) + OffsetOf(AnvilVkWsiPresentItem\imageIndex))
    s = avkWsiSwapchainSlot(h)
    If s = 0 : avkWsiPresentClear(t) : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
    If avkWsiSwapDev[s] <> d Or avkWsiSwapDevGen[s] <> avkTokenGen(device) : avkWsiPresentClear(t) : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
    surf = avkWsiSurfaceSlot(avkWsiSwapSurface[s])
    If surf = 0 Or surf <> avkWsiSwapSurfSlot[s] : avkWsiPresentClear(t) : ProcedureReturn #VK_ERROR_SURFACE_LOST_KHR : EndIf
    If avkWsiSurfLost[surf] <> 0 : avkWsiPresentClear(t) : ProcedureReturn #VK_ERROR_SURFACE_LOST_KHR : EndIf
    If avkWsiSwapOutOfDate[s] <> 0 Or avkWsiSurfSerial[surf] <> avkWsiSwapSerial[s] : avkWsiPresentClear(t) : ProcedureReturn #VK_ERROR_OUT_OF_DATE_KHR : EndIf
    If index < 0 Or index >= avkWsiSwapImageCount[s] : avkWsiPresentClear(t) : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
    If avkWsiSwapImageState[avkWsiImageIndex(s, index)] <> #ANVIL_VK_WSI_IMAGE_RENDER_READY : avkWsiPresentClear(t) : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
    If avkWsiPresentReservedByAny(s, index) <> 0 : avkWsiPresentClear(t) : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
    j = 0
    While j < i
      If avkWsiPresentSwapSlot[avkWsiPresentIndex(t, j)] = s And avkWsiPresentImage[avkWsiPresentIndex(t, j)] = index : avkWsiPresentClear(t) : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
      j = j + 1
    Wend
    avkWsiPresentSwap[avkWsiPresentIndex(t, i)] = h
    avkWsiPresentSwapSlot[avkWsiPresentIndex(t, i)] = s
    avkWsiPresentImage[avkWsiPresentIndex(t, i)] = index
    i = i + 1
  Wend
  avkWsiPresentGen[t] = avkNextGen(avkWsiPresentGen[t])
  avkWsiPresentStage[t] = #ANVIL_VK_WSI_PRESENT_RESERVED
  PokeI(*out, avkToken(#ANVIL_VK_TYPE_WSI_PRESENT, t, avkWsiPresentGen[t]))
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkWsiPresentCommit(ticket.i)
  Define t.i
  Define i.i
  Define s.i
  Define index.i
  t = avkWsiPresentSlot(ticket)
  If t = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkWsiPresentStage[t] <> #ANVIL_VK_WSI_PRESENT_RESERVED : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
  If avkWsiPresentDev[t] < 1 Or avkWsiPresentDev[t] > #ANVIL_VK_MAX_DEVICES : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
  If avkDevLive[avkWsiPresentDev[t]] = 0 Or avkDevGen[avkWsiPresentDev[t]] <> avkWsiPresentDevGen[t] : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
  i = 0
  While i < avkWsiPresentCount[t]
    s = avkWsiSwapchainSlot(avkWsiPresentSwap[avkWsiPresentIndex(t, i)])
    index = avkWsiPresentImage[avkWsiPresentIndex(t, i)]
    If s = 0 Or s <> avkWsiPresentSwapSlot[avkWsiPresentIndex(t, i)] : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
    If avkWsiSwapDev[s] <> avkWsiPresentDev[t] Or avkWsiSwapDevGen[s] <> avkWsiPresentDevGen[t] : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
    If avkWsiSwapImageState[avkWsiImageIndex(s, index)] <> #ANVIL_VK_WSI_IMAGE_RENDER_READY : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
    i = i + 1
  Wend
  i = 0
  While i < avkWsiPresentCount[t]
    s = avkWsiPresentSwapSlot[avkWsiPresentIndex(t, i)]
    index = avkWsiPresentImage[avkWsiPresentIndex(t, i)]
    avkWsiSwapImageState[avkWsiImageIndex(s, index)] = #ANVIL_VK_WSI_IMAGE_PRESENT_PENDING
    i = i + 1
  Wend
  avkWsiPresentStage[t] = #ANVIL_VK_WSI_PRESENT_COMMITTED
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkWsiPresentComplete(ticket.i, providerSucceeded.i)
  Define t.i
  Define i.i
  Define s.i
  Define index.i
  t = avkWsiPresentSlot(ticket)
  If t = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkWsiPresentStage[t] <> #ANVIL_VK_WSI_PRESENT_COMMITTED : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
  If avkWsiPresentDev[t] < 1 Or avkWsiPresentDev[t] > #ANVIL_VK_MAX_DEVICES : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
  If avkDevLive[avkWsiPresentDev[t]] = 0 Or avkDevGen[avkWsiPresentDev[t]] <> avkWsiPresentDevGen[t] : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
  i = 0
  While i < avkWsiPresentCount[t]
    s = avkWsiSwapchainSlot(avkWsiPresentSwap[avkWsiPresentIndex(t, i)])
    index = avkWsiPresentImage[avkWsiPresentIndex(t, i)]
    If s = 0 Or s <> avkWsiPresentSwapSlot[avkWsiPresentIndex(t, i)] : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
    If avkWsiSwapImageState[avkWsiImageIndex(s, index)] <> #ANVIL_VK_WSI_IMAGE_PRESENT_PENDING : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
    i = i + 1
  Wend
  i = 0
  While i < avkWsiPresentCount[t]
    s = avkWsiPresentSwapSlot[avkWsiPresentIndex(t, i)]
    index = avkWsiPresentImage[avkWsiPresentIndex(t, i)]
    If providerSucceeded <> 0
      avkWsiSwapImageState[avkWsiImageIndex(s, index)] = #ANVIL_VK_WSI_IMAGE_AVAILABLE
    Else
      avkWsiSwapImageState[avkWsiImageIndex(s, index)] = #ANVIL_VK_WSI_IMAGE_RENDER_READY
    EndIf
    i = i + 1
  Wend
  avkWsiPresentClear(t)
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkWsiPresentRollback(ticket.i)
  Define t.i
  t = avkWsiPresentSlot(ticket)
  If t = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkWsiPresentStage[t] = #ANVIL_VK_WSI_PRESENT_RESERVED
    avkWsiPresentClear(t)
    ProcedureReturn #VK_SUCCESS
  EndIf
  ProcedureReturn avkWsiPresentComplete(ticket, 0)
EndProcedure

Procedure.i avkWsiProviderResize(provider.i, width.i, height.i)
  Define p.i
  Define s.i
  Define c.i
  p = avkWsiProviderSlot(provider)
  If p = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkWsiProvLost[p] <> 0 : ProcedureReturn #VK_ERROR_SURFACE_LOST_KHR : EndIf
  If width < avkWsiProvCaps[p]\minWidth Or width > avkWsiProvCaps[p]\maxWidth : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  If height < avkWsiProvCaps[p]\minHeight Or height > avkWsiProvCaps[p]\maxHeight : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  If width = avkWsiProvCaps[p]\currentWidth And height = avkWsiProvCaps[p]\currentHeight : ProcedureReturn #VK_SUCCESS : EndIf
  avkWsiProvCaps[p]\currentWidth = width
  avkWsiProvCaps[p]\currentHeight = height
  avkWsiProvEpoch[p] = avkNextGen(avkWsiProvEpoch[p])
  s = 1
  While s <= #ANVIL_VK_WSI_MAX_SURFACES
    If avkWsiSurfLive[s] <> 0 And avkWsiSurfProvider[s] = provider
      avkWsiSurfSerial[s] = avkWsiProvEpoch[p]
      c = 1
      While c <= #ANVIL_VK_WSI_MAX_SWAPCHAINS
        If avkWsiSwapLive[c] <> 0 And avkWsiSwapSurface[c] = avkToken(#ANVIL_VK_TYPE_WSI_SURFACE, s, avkWsiSurfGen[s])
          avkWsiSwapOutOfDate[c] = 1
        EndIf
        c = c + 1
      Wend
    EndIf
    s = s + 1
  Wend
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkWsiProviderLose(provider.i)
  Define p.i
  Define s.i
  Define c.i
  p = avkWsiProviderSlot(provider)
  If p = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  avkWsiProvLost[p] = 1
  s = 1
  While s <= #ANVIL_VK_WSI_MAX_SURFACES
    If avkWsiSurfLive[s] <> 0 And avkWsiSurfProvider[s] = provider
      avkWsiSurfLost[s] = 1
      c = 1
      While c <= #ANVIL_VK_WSI_MAX_SWAPCHAINS
        If avkWsiSwapLive[c] <> 0 And avkWsiSwapSurface[c] = avkToken(#ANVIL_VK_TYPE_WSI_SURFACE, s, avkWsiSurfGen[s]) : avkWsiSwapOutOfDate[c] = 1 : EndIf
        c = c + 1
      Wend
    EndIf
    s = s + 1
  Wend
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkWsiSwapchainRetire(device.i, swapchain.i)
  Define d.i
  Define s.i
  Define surf.i
  d = avkDevSlot(device)
  s = avkWsiSwapchainSlot(swapchain)
  If d = 0 Or s = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkWsiSwapDev[s] <> d Or avkWsiSwapDevGen[s] <> avkTokenGen(device) : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
  avkWsiSwapRetired[s] = 1
  surf = avkWsiSurfaceSlot(avkWsiSwapSurface[s])
  If surf <> 0
    If avkWsiSurfActiveSwap[surf] = swapchain : avkWsiSurfActiveSwap[surf] = 0 : EndIf
  EndIf
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkWsiSwapchainDestroy(device.i, swapchain.i)
  Define d.i
  Define s.i
  Define surf.i
  Define i.i
  If swapchain = #VK_NULL_HANDLE : ProcedureReturn #VK_SUCCESS : EndIf
  d = avkDevSlot(device)
  s = avkWsiSwapchainSlot(swapchain)
  If d = 0 Or s = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkWsiSwapDev[s] <> d Or avkWsiSwapDevGen[s] <> avkTokenGen(device) : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
  i = 0
  While i < avkWsiSwapImageCount[s]
    If avkWsiSwapImageState[avkWsiImageIndex(s, i)] <> #ANVIL_VK_WSI_IMAGE_AVAILABLE : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
    i = i + 1
  Wend
  surf = avkWsiSurfaceSlot(avkWsiSwapSurface[s])
  If surf <> 0
    If avkWsiSurfActiveSwap[surf] = swapchain : avkWsiSurfActiveSwap[surf] = 0 : EndIf
  EndIf
  avkWsiSwapLive[s] = 0
  avkWsiSwapDev[s] = 0
  avkWsiSwapDevGen[s] = 0
  avkWsiSwapImageCount[s] = 0
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkWsiSurfaceDestroy(instance.i, surface.i)
  Define inst.i
  Define s.i
  Define c.i
  If surface = #VK_NULL_HANDLE : ProcedureReturn #VK_SUCCESS : EndIf
  inst = avkInstSlot(instance)
  s = avkWsiSurfaceSlot(surface)
  If inst = 0 Or s = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkWsiSurfInst[s] <> inst Or avkWsiSurfInstGen[s] <> avkTokenGen(instance) : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
  c = 1
  While c <= #ANVIL_VK_WSI_MAX_SWAPCHAINS
    If avkWsiSwapLive[c] <> 0 And avkWsiSwapSurface[c] = surface : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
    c = c + 1
  Wend
  avkWsiSurfLive[s] = 0
  avkWsiSurfProvider[s] = 0
  avkWsiSurfActiveSwap[s] = 0
  ProcedureReturn #VK_SUCCESS
EndProcedure

; Device teardown seam.  The future vkDestroyDevice adapter calls this while
; the generation-tagged VkDevice is still live.  The scan is all-or-nothing:
; an acquired, render-ready or pending image, or any present transaction,
; leaves every swapchain untouched.  Only quiescent provider images return to
; the provider-owned pool.
Procedure.i avkWsiResetDevice(device.i)
  Define d.i
  Define t.i
  Define s.i
  Define i.i
  Define surf.i
  Define handle.i
  d = avkDevSlot(device)
  If d = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  t = 1
  While t <= #ANVIL_VK_WSI_MAX_PRESENTS
    If avkWsiPresentStage[t] <> #ANVIL_VK_WSI_PRESENT_FREE And avkWsiPresentDev[t] = d And avkWsiPresentDevGen[t] = avkTokenGen(device) : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
    t = t + 1
  Wend
  s = 1
  While s <= #ANVIL_VK_WSI_MAX_SWAPCHAINS
    If avkWsiSwapLive[s] <> 0 And avkWsiSwapDev[s] = d And avkWsiSwapDevGen[s] = avkTokenGen(device)
      i = 0
      While i < avkWsiSwapImageCount[s]
        If avkWsiSwapImageState[avkWsiImageIndex(s, i)] <> #ANVIL_VK_WSI_IMAGE_AVAILABLE : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
        i = i + 1
      Wend
    EndIf
    s = s + 1
  Wend
  s = 1
  While s <= #ANVIL_VK_WSI_MAX_SWAPCHAINS
    If avkWsiSwapLive[s] <> 0 And avkWsiSwapDev[s] = d And avkWsiSwapDevGen[s] = avkTokenGen(device)
      handle = avkToken(#ANVIL_VK_TYPE_WSI_SWAPCHAIN, s, avkWsiSwapGen[s])
      surf = avkWsiSurfaceSlot(avkWsiSwapSurface[s])
      If surf <> 0
        If avkWsiSurfActiveSwap[surf] = handle : avkWsiSurfActiveSwap[surf] = 0 : EndIf
      EndIf
      avkWsiSwapLive[s] = 0
      avkWsiSwapDev[s] = 0
      avkWsiSwapDevGen[s] = 0
      avkWsiSwapImageCount[s] = 0
    EndIf
    s = s + 1
  Wend
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkWsiProviderDestroy(provider.i)
  Define p.i
  Define s.i
  If provider = #VK_NULL_HANDLE : ProcedureReturn #VK_SUCCESS : EndIf
  p = avkWsiProviderSlot(provider)
  If p = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  s = 1
  While s <= #ANVIL_VK_WSI_MAX_SURFACES
    If avkWsiSurfLive[s] <> 0 And avkWsiSurfProvider[s] = provider : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
    s = s + 1
  Wend
  avkWsiProvLive[p] = 0
  avkWsiProvCookie[p] = 0
  ProcedureReturn #VK_SUCCESS
EndProcedure

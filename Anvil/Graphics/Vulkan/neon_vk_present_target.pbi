; Private single-image presentation source for the synchronous Neon adapter.
; The display owner supplies real image identity and confirms physical completion.
; This helper performs no display access and advertises no public extension.
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_chrome.pbi"

Structure NeonVkPresentTarget
  provider.i
  surface.i
  swapchain.i
  image.i
EndStructure

; Every handle is cleared only after its corresponding destruction succeeds.
; An acquired/pending image makes the first step refuse and retains all parents.
Procedure.i NeonVkPresentTargetDestroy(instance.i, device.i, *target.NeonVkPresentTarget)
  Define rc.i
  If *target = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  If *target\swapchain <> 0
    rc = avkWsiSwapchainDestroy(device, *target\swapchain)
    If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
    *target\swapchain = 0
  EndIf
  If *target\surface <> 0
    rc = avkWsiSurfaceDestroy(instance, *target\surface)
    If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
    *target\surface = 0
  EndIf
  If *target\provider <> 0
    rc = avkWsiProviderDestroy(*target\provider)
    If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
    *target\provider = 0
  EndIf
  *target\image = 0
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i NeonVkPresentTargetCreate(instance.i, device.i, image.i, nativeKey.i, width.i, height.i, *target.NeonVkPresentTarget)
  Define info.AnvilVkWsiProviderInfo, format.AnvilVkWsiFormat
  Define chain.AnvilVkWsiSwapchainInfo, mode.i, rc.i
  If *target = 0 Or instance = 0 Or device = 0 Or image = 0 Or nativeKey = 0 Or width < 1 Or height < 1
    ProcedureReturn #ANVIL_VK_ERR_ARGS
  EndIf
  If *target\provider <> 0 Or *target\surface <> 0 Or *target\swapchain <> 0 Or *target\image <> 0
    ProcedureReturn #ANVIL_VK_ERR_STATE
  EndIf
  info\cookie = nativeKey
  info\capabilities\minImageCount = 1 : info\capabilities\maxImageCount = 1
  info\capabilities\currentWidth = width : info\capabilities\currentHeight = height
  info\capabilities\minWidth = width : info\capabilities\minHeight = height
  info\capabilities\maxWidth = width : info\capabilities\maxHeight = height
  info\capabilities\maxImageArrayLayers = 1
  info\capabilities\supportedTransforms = #VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR
  info\capabilities\currentTransform = #VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR
  info\capabilities\supportedCompositeAlpha = #VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR
  info\capabilities\supportedUsageFlags = #VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | #VK_IMAGE_USAGE_TRANSFER_SRC_BIT
  format\format = #VK_FORMAT_B8G8R8A8_UNORM : format\colorSpace = #VK_COLOR_SPACE_SRGB_NONLINEAR_KHR
  mode = #VK_PRESENT_MODE_FIFO_KHR
  info\formatCount = 1 : info\formats = @format
  info\presentModeCount = 1 : info\presentModes = @mode
  rc = avkWsiProviderRegister(@info, @*target\provider)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  rc = avkWsiSurfaceCreate(instance, *target\provider, nativeKey, @*target\surface)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  chain\surface = *target\surface : chain\minImageCount = 1
  chain\imageFormat = format\format : chain\imageColorSpace = format\colorSpace
  chain\imageWidth = width : chain\imageHeight = height : chain\imageArrayLayers = 1
  chain\imageUsage = info\capabilities\supportedUsageFlags
  chain\imageSharingMode = #VK_SHARING_MODE_EXCLUSIVE
  chain\preTransform = #VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR
  chain\compositeAlpha = #VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR
  chain\presentMode = mode : chain\clipped = 1
  chain\providerImageCount = 1 : chain\providerImages = @image
  rc = avkWsiSwapchainCreate(device, @chain, @*target\swapchain)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  *target\image = image
  ProcedureReturn #VK_SUCCESS
EndProcedure

; Acquire is nonblocking. A failed attach releases only the image acquired here;
; a failed release remains owned by the chain and will refuse target destruction.
Procedure.i NeonVkPresentTargetAcquire(device.i, image.i, *target.NeonVkPresentTarget)
  Define index.i, rc.i, releaseRc.i
  If *target = 0 Or image = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  If *target\swapchain = 0 Or *target\image <> image : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
  ; The acquire API writes uint32; keep the upper half of its integer slot zero.
  index = 0
  rc = avkWsiAcquire(device, *target\swapchain, 0, @index)
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  If index <> 0 Or avkWsiImageKey(device, *target\swapchain, index) <> image
    rc = #ANVIL_VK_ERR_OWNER
  Else
    rc = NeonVkChromeWsiAttach(device, *target\swapchain, index)
  EndIf
  If rc <> #VK_SUCCESS
    releaseRc = avkWsiReleaseImage(device, *target\swapchain, index)
    If releaseRc <> #VK_SUCCESS : ProcedureReturn releaseRc : EndIf
  EndIf
  ProcedureReturn rc
EndProcedure

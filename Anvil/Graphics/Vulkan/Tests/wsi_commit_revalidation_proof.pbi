; Actual target-neutral WSI engine, state backend, no GPU or scanout provider.
; Provider resize/loss are public state inputs, not writes into engine arrays.
XIncludeFile "Anvil/Graphics/Vulkan/vk_api.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_backend_test.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_wsi.pbi"

Global Dim wcrHeap.a[65536]
Global wcrRecords.i,wcrFailures.i

Procedure WcrObserve(value.i,wanted.i)
 If wcrRecords>=252 : wcrFailures=wcrFailures+1 : ProcedureReturn : EndIf
 PokeI(#WCR_REPORT+64+wcrRecords*16,wcrRecords+1)
 PokeI(#WCR_REPORT+72+wcrRecords*16,value)
 wcrRecords=wcrRecords+1
 If value<>wanted : wcrFailures=wcrFailures+1 : EndIf
EndProcedure

Procedure WcrCreate(instance.i,device.i,seed.i,*provider,*surface,*swapchain)
 Define info.AnvilVkWsiProviderInfo,ci.AnvilVkWsiSwapchainInfo,fmt.AnvilVkWsiFormat
 Define mode.i=#VK_PRESENT_MODE_FIFO_KHR
 Define Dim images.i[2]
 fmt\format=#VK_FORMAT_B8G8R8A8_UNORM : fmt\colorSpace=#VK_COLOR_SPACE_SRGB_NONLINEAR_KHR
 info\cookie=seed
 info\capabilities\minImageCount=2 : info\capabilities\maxImageCount=2
 info\capabilities\currentWidth=64 : info\capabilities\currentHeight=64
 info\capabilities\minWidth=32 : info\capabilities\minHeight=32
 info\capabilities\maxWidth=128 : info\capabilities\maxHeight=128
 info\capabilities\maxImageArrayLayers=1
 info\capabilities\supportedTransforms=#VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR
 info\capabilities\currentTransform=#VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR
 info\capabilities\supportedCompositeAlpha=#VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR
 info\capabilities\supportedUsageFlags=#VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT
 info\formatCount=1 : info\formats=@fmt : info\presentModeCount=1 : info\presentModes=@mode
 WcrObserve(avkWsiProviderRegister(@info,*provider),0)
 WcrObserve(avkWsiSurfaceCreate(instance,PeekI(*provider),seed,*surface),0)
 images[0]=seed*65536+4096 : images[1]=seed*65536+8192
 ci\surface=PeekI(*surface) : ci\minImageCount=2
 ci\imageFormat=#VK_FORMAT_B8G8R8A8_UNORM : ci\imageColorSpace=#VK_COLOR_SPACE_SRGB_NONLINEAR_KHR
 ci\imageWidth=64 : ci\imageHeight=64 : ci\imageArrayLayers=1
 ci\imageUsage=#VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT : ci\imageSharingMode=#VK_SHARING_MODE_EXCLUSIVE
 ci\preTransform=#VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR : ci\compositeAlpha=#VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR
 ci\presentMode=#VK_PRESENT_MODE_FIFO_KHR : ci\clipped=1
 ci\providerImageCount=2 : ci\providerImages=@images[0]
 WcrObserve(avkWsiSwapchainCreate(device,@ci,*swapchain),0)
EndProcedure

Procedure.i WsiCommitRevalidationProof()
 Define instance.i,physical.i,device.i,ticket.i,mode.i,j.i,n.i,expected.i
 Define count.l=1
 Define Dim providers.i[2]
 Define Dim surfaces.i[2]
 Define Dim swaps.i[2]
 Define Dim indices.l[2]
 Define Dim items.AnvilVkWsiPresentItem[2]
 AnvilVkTestBackendHeap(@wcrHeap[0],65536)
 WcrObserve(AnvilVkInstanceCreate(@instance),0)
 WcrObserve(AnvilVkPhysicalEnumerate(instance,@count,@physical),0)
 WcrObserve(AnvilVkDeviceCreate(physical,@device),0)
 For mode=0 To 6
  For j=0 To 1
   WcrCreate(instance,device,100+mode*2+j,@providers[j],@surfaces[j],@swaps[j])
  Next
  For j=0 To 1
   WcrObserve(avkWsiAcquire(device,swaps[j],0,@indices[j]),0)
   WcrObserve(avkWsiMarkRenderReady(device,swaps[j],indices[j]),0)
   items[j]\swapchain=swaps[j] : items[j]\imageIndex=indices[j]
  Next
  n=1 : If mode=4 Or mode=5 : n=2 : EndIf
  WcrObserve(avkWsiPresentReserve(device,n,@items[0],@ticket),0)
  expected=0
  Select mode
   Case 1
    WcrObserve(avkWsiProviderResize(providers[0],80,64),0)
    expected=#VK_ERROR_OUT_OF_DATE_KHR
   Case 2
    WcrObserve(avkWsiProviderLose(providers[0]),0)
    expected=#VK_ERROR_SURFACE_LOST_KHR
   Case 3
    ; Retirement prevents new acquire, but an already-acquired image is valid.
    WcrObserve(avkWsiSwapchainRetire(device,swaps[0]),0)
   Case 4
    WcrObserve(avkWsiProviderResize(providers[1],80,64),0)
    expected=#VK_ERROR_OUT_OF_DATE_KHR
   Case 5
    WcrObserve(avkWsiProviderLose(providers[1]),0)
    expected=#VK_ERROR_SURFACE_LOST_KHR
   Case 6
    WcrObserve(avkWsiProviderResize(providers[0],64,64),0)
   Default
    WcrObserve(0,0)
  EndSelect
  WcrObserve(avkWsiPresentCommit(ticket),expected)
  For j=0 To 1
   If expected=0 And j<n
    WcrObserve(avkWsiImageState(device,swaps[j],indices[j]),#ANVIL_VK_WSI_IMAGE_PRESENT_PENDING)
   Else
    WcrObserve(avkWsiImageState(device,swaps[j],indices[j]),#ANVIL_VK_WSI_IMAGE_RENDER_READY)
   EndIf
  Next
  WcrObserve(Bool(avkWsiPresentSlot(ticket)<>0),1)
  If expected=0
   WcrObserve(avkWsiPresentCommit(ticket),#ANVIL_VK_ERR_STATE)
  Else
   WcrObserve(avkWsiPresentCommit(ticket),expected)
  EndIf
  WcrObserve(avkWsiPresentRollback(ticket),0)
  For j=0 To 1
   WcrObserve(avkWsiImageState(device,swaps[j],indices[j]),#ANVIL_VK_WSI_IMAGE_RENDER_READY)
  Next
  For j=0 To 1 : WcrObserve(avkWsiReleaseImage(device,swaps[j],indices[j]),0) : Next
  For j=0 To 1 : WcrObserve(avkWsiSwapchainDestroy(device,swaps[j]),0) : Next
  For j=0 To 1 : WcrObserve(avkWsiSurfaceDestroy(instance,surfaces[j]),0) : Next
  For j=0 To 1 : WcrObserve(avkWsiProviderDestroy(providers[j]),0) : Next
 Next
 WcrObserve(AnvilVkDeviceDestroy(device),0)
 WcrObserve(AnvilVkInstanceDestroy(instance),0)
 ProcedureReturn wcrFailures
EndProcedure

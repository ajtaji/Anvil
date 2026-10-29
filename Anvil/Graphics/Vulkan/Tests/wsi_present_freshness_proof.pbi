; Actual shared WSI/bridge/record state. Provider keys are opaque; no GPU or scanout.
XIncludeFile "Anvil/Graphics/Vulkan/vk_api.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_backend_test.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_wsi_bridge.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_display.pbi"
Global Dim wpfHeap.a[65536]
Global wpfRecords.i,wpfFailures.i

Procedure WpfObserve(value.i,wanted.i)
 If wpfRecords>=508 : wpfFailures=wpfFailures+1 : ProcedureReturn : EndIf
 PokeI(#WPF_REPORT+64+wpfRecords*16,wpfRecords+1)
 PokeI(#WPF_REPORT+72+wpfRecords*16,value)
 wpfRecords=wpfRecords+1
 If value<>wanted : wpfFailures=wpfFailures+1 : EndIf
EndProcedure

Procedure WpfCreate(instance.i,device.i,seed.i,*provider,*surface,*swapchain)
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
 WpfObserve(avkWsiProviderRegister(@info,*provider),0)
 WpfObserve(avkWsiSurfaceCreate(instance,PeekI(*provider),seed,*surface),0)
 images[0]=seed*65536+4096 : images[1]=seed*65536+8192
 ci\surface=PeekI(*surface) : ci\minImageCount=2
 ci\imageFormat=#VK_FORMAT_B8G8R8A8_UNORM : ci\imageColorSpace=#VK_COLOR_SPACE_SRGB_NONLINEAR_KHR
 ci\imageWidth=64 : ci\imageHeight=64 : ci\imageArrayLayers=1
 ci\imageUsage=#VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT : ci\imageSharingMode=#VK_SHARING_MODE_EXCLUSIVE
 ci\preTransform=#VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR : ci\compositeAlpha=#VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR
 ci\presentMode=#VK_PRESENT_MODE_FIFO_KHR : ci\clipped=1
 ci\providerImageCount=2 : ci\providerImages=@images[0]
 WpfObserve(avkWsiSwapchainCreate(device,@ci,*swapchain),0)
EndProcedure

Procedure.i WsiPresentFreshnessProof()
 Define instance.i,physical.i,device.i,provider.i,surface.i,swapchain.i
 Define mode.i,target.i,stale.i,published.i,ticket.i,j.i,wanted.i
 Define count.l=1,index.l
 Define Dim providers.i[2]
 Define Dim surfaces.i[2]
 Define Dim swaps.i[2]
 Define Dim indices.l[2]
 Define Dim items.AnvilVkWsiPresentItem[2]
 AnvilVkTestBackendHeap(@wpfHeap[0],65536)
 WpfObserve(AnvilVkInstanceCreate(@instance),0)
 WpfObserve(AnvilVkPhysicalEnumerate(instance,@count,@physical),0)
 WpfObserve(AnvilVkDeviceCreate(physical,@device),0)
 nvdWsiClear() : nvdPresentClear()
 For mode=0 To 6
  target=mode+1 : stale=Bool(mode>=1 And mode<=4)
  WpfCreate(instance,device,200+mode,@provider,@surface,@swapchain)
  WpfObserve(avkWsiAcquire(device,swapchain,0,@index),0)
  WpfObserve(nvdWsiAttach(device,swapchain,index,target),0)
  WpfObserve(nvdWsiMarkReady(),0)
  WpfObserve(nvdWsiReserve(),0)
  WpfObserve(nvdWsiCommit(),0)
  Select mode
   Case 1 : WpfObserve(avkWsiProviderLose(provider),0)
   Case 2 : WpfObserve(avkWsiProviderResize(provider,80,64),0)
   Default : WpfObserve(0,0)
  EndSelect
  published=1 : If mode=1 Or mode=2 : published=0 : EndIf
  WpfObserve(nvdPresentPublish(target,777,target,64,64,64,64,256,0),published)
  Select mode
   Case 3 : WpfObserve(avkWsiProviderLose(provider),0)
   Case 4 : WpfObserve(avkWsiProviderResize(provider,80,64),0)
   Case 5 : WpfObserve(avkWsiSwapchainRetire(device,swapchain),0)
   Case 6 : WpfObserve(avkWsiProviderResize(provider,64,64),0)
   Default : WpfObserve(0,0)
  EndSelect
  WpfObserve(nvdPresentMatches(target,777),1-stale)
  WpfObserve(nvdPresentMatches(target,777),1-stale)
  WpfObserve(nvdWsiState,4)
  WpfObserve(Bool(avkWsiPresentSlot(nvdWsiTicket)<>0),1)
  WpfObserve(avkWsiImageState(device,swapchain,index),3)
  WpfObserve(nvdPresentPending(),published)
  WpfObserve(nvdPresentConsume(target,777),1-stale)
  If stale<>0
   WpfObserve(nvdWsiState,4)
   WpfObserve(Bool(avkWsiPresentSlot(nvdWsiTicket)<>0),1)
   WpfObserve(avkWsiImageState(device,swapchain,index),3)
   WpfObserve(nvdPresentPending(),published)
  Else
   WpfObserve(nvdWsiState,0)
   WpfObserve(nvdWsiTicket,0)
   WpfObserve(avkWsiImageState(device,swapchain,index),0)
   WpfObserve(nvdPresentPending(),0)
  EndIf
  WpfObserve(nvdPresentInvalidate(target,777),1)
  WpfObserve(nvdWsiRollback(),0)
  WpfObserve(nvdWsiState,0)
  WpfObserve(nvdWsiTicket,0)
  WpfObserve(avkWsiImageState(device,swapchain,index),0)
  WpfObserve(nvdPresentPending(),0)
  WpfObserve(avkWsiSwapchainDestroy(device,swapchain),0)
  WpfObserve(avkWsiSurfaceDestroy(instance,surface),0)
  WpfObserve(avkWsiProviderDestroy(provider),0)
 Next
 CompilerIf #WPF_QUERY_AVAILABLE=1
  ; Captured identity mismatches cannot consume another committed record.
  target=100
  WpfCreate(instance,device,400,@provider,@surface,@swapchain)
  WpfObserve(avkWsiAcquire(device,swapchain,0,@index),0)
  WpfObserve(nvdWsiAttach(device,swapchain,index,target),0)
  WpfObserve(nvdWsiMarkReady(),0)
  WpfObserve(nvdWsiReserve(),0)
  WpfObserve(nvdWsiCommit(),0)
  WpfObserve(nvdPresentPublish(target,777,target,64,64,64,64,256,0),1)
  WpfObserve(nvdWsiPresentCurrent(target,nvdWsiTicket,swapchain,index,nvdWsiImageKey),1)
  WpfObserve(nvdWsiPresentCurrent(target+1,nvdWsiTicket,swapchain,index,nvdWsiImageKey),0)
  WpfObserve(nvdWsiPresentCurrent(target,nvdWsiTicket+1,swapchain,index,nvdWsiImageKey),0)
  WpfObserve(nvdWsiPresentCurrent(target,nvdWsiTicket,swapchain+1,index,nvdWsiImageKey),0)
  WpfObserve(nvdWsiPresentCurrent(target,nvdWsiTicket,swapchain,index+1,nvdWsiImageKey),0)
  WpfObserve(nvdWsiPresentCurrent(target,nvdWsiTicket,swapchain,index,nvdWsiImageKey+1),0)
  WpfObserve(nvdPresentPending(),1)
  WpfObserve(nvdWsiState,4)
  WpfObserve(Bool(avkWsiPresentSlot(nvdWsiTicket)<>0),1)
  WpfObserve(avkWsiImageState(device,swapchain,index),3)
  WpfObserve(nvdPresentMatches(target,777),1)
  WpfObserve(nvdPresentConsume(target,777),1)
  WpfObserve(avkWsiSwapchainDestroy(device,swapchain),0)
  WpfObserve(avkWsiSurfaceDestroy(instance,surface),0)
  WpfObserve(avkWsiProviderDestroy(provider),0)
  WpfObserve(avkWsiPresentValidate(0),#ANVIL_VK_ERR_HANDLE)
  For mode=0 To 2
   For j=0 To 1 : WpfCreate(instance,device,300+mode*2+j,@providers[j],@surfaces[j],@swaps[j]) : Next
   For j=0 To 1
    WpfObserve(avkWsiAcquire(device,swaps[j],0,@indices[j]),0)
    WpfObserve(avkWsiMarkRenderReady(device,swaps[j],indices[j]),0)
    items[j]\swapchain=swaps[j] : items[j]\imageIndex=indices[j]
   Next
   WpfObserve(avkWsiPresentReserve(device,2,@items[0],@ticket),0)
   WpfObserve(avkWsiPresentValidate(ticket),#ANVIL_VK_ERR_STATE)
   WpfObserve(avkWsiPresentCommit(ticket),0)
   WpfObserve(avkWsiPresentValidate(ticket),0)
   wanted=0
   Select mode
    Case 1
     WpfObserve(avkWsiProviderResize(providers[1],80,64),0) : wanted=#VK_ERROR_OUT_OF_DATE_KHR
    Case 2
     WpfObserve(avkWsiProviderLose(providers[1]),0) : wanted=#VK_ERROR_SURFACE_LOST_KHR
    Default
     WpfObserve(0,0)
   EndSelect
   WpfObserve(avkWsiPresentValidate(ticket),wanted)
   WpfObserve(avkWsiPresentValidate(ticket),wanted)
   For j=0 To 1 : WpfObserve(avkWsiImageState(device,swaps[j],indices[j]),3) : Next
   WpfObserve(Bool(avkWsiPresentSlot(ticket)<>0),1)
   WpfObserve(avkWsiPresentRollback(ticket),0)
   For j=0 To 1 : WpfObserve(avkWsiReleaseImage(device,swaps[j],indices[j]),0) : Next
   For j=0 To 1 : WpfObserve(avkWsiSwapchainDestroy(device,swaps[j]),0) : Next
   For j=0 To 1 : WpfObserve(avkWsiSurfaceDestroy(instance,surfaces[j]),0) : Next
   For j=0 To 1 : WpfObserve(avkWsiProviderDestroy(providers[j]),0) : Next
  Next
 CompilerEndIf
 WpfObserve(AnvilVkDeviceDestroy(device),0)
 WpfObserve(AnvilVkInstanceDestroy(instance),0)
 ProcedureReturn wpfFailures
EndProcedure

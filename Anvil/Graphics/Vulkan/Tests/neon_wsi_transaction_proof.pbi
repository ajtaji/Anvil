; Actual WSI state engine, adapter bridge and completed-frame record.
; No display provider, scanout, GPU, DMA or claimed asynchronous completion.
XIncludeFile "Anvil/Graphics/Vulkan/vk_api.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_backend_test.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_wsi_bridge.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_display.pbi"

Global Dim nwtHeap.a[65536]
Global nwtRecords.i,nwtFailures.i
Global nwtBeforeRecordingWork.i

; @NWT_BEGIN_COMPOSITION@

Procedure NwtObserve(tag.i,value.i,wanted.i)
 If nwtRecords>=252 : nwtFailures=nwtFailures+1 : ProcedureReturn : EndIf
 PokeI(#NWT_REPORT+64+nwtRecords*16,tag)
 PokeI(#NWT_REPORT+72+nwtRecords*16,value)
 nwtRecords=nwtRecords+1
 If value<>wanted : nwtFailures=nwtFailures+1 : EndIf
EndProcedure

; The exact production Begin body is composed with a rejecting atlas spy.
; Allowed admission reaches that spy; refused admission must reach no work.
Procedure NwtTryBegin(tag.i,device.i,generation.i,wanted.i,work.i)
 nvcReady=1 : nvcDevice=device : nvcTargetGeneration=generation
 nwtBeforeRecordingWork=0
 NwtObserve(tag,NeonVkChromeBegin(0),wanted)
 NwtObserve(tag+1,nwtBeforeRecordingWork,work)
EndProcedure

Procedure.i NeonWsiTransactionProof()
 Define inst.i,physical.i,device.i,provider.i,surface.i,swapchain.i,ticket.i,savedTicket.i
 Define count.l=1,index.l,index2.l,rc.i,i.i,stage.i
 Define info.AnvilVkWsiProviderInfo,ci.AnvilVkWsiSwapchainInfo,fmt.AnvilVkWsiFormat
 Define item.AnvilVkWsiPresentItem
 Define mode.i=#VK_PRESENT_MODE_FIFO_KHR
 Define Dim images.i[2]
 AnvilVkTestBackendHeap(@nwtHeap[0],65536)
 NwtObserve(100,AnvilVkInstanceCreate(@inst),0)
 NwtObserve(101,AnvilVkPhysicalEnumerate(inst,@count,@physical),0)
 NwtObserve(102,AnvilVkDeviceCreate(physical,@device),0)
 fmt\format=#VK_FORMAT_B8G8R8A8_UNORM : fmt\colorSpace=#VK_COLOR_SPACE_SRGB_NONLINEAR_KHR
 info\cookie=$4E575450
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
 NwtObserve(103,avkWsiProviderRegister(@info,@provider),0)
 NwtObserve(104,avkWsiSurfaceCreate(inst,provider,$4E5754,@surface),0)
 images[0]=$11110000 : images[1]=$22220000
 ci\surface=surface : ci\minImageCount=2
 ci\imageFormat=#VK_FORMAT_B8G8R8A8_UNORM : ci\imageColorSpace=#VK_COLOR_SPACE_SRGB_NONLINEAR_KHR
 ci\imageWidth=64 : ci\imageHeight=64 : ci\imageArrayLayers=1
 ci\imageUsage=#VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT : ci\imageSharingMode=#VK_SHARING_MODE_EXCLUSIVE
 ci\preTransform=#VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR : ci\compositeAlpha=#VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR
 ci\presentMode=#VK_PRESENT_MODE_FIFO_KHR : ci\clipped=1
 ci\providerImageCount=2 : ci\providerImages=@images[0]
 NwtObserve(105,avkWsiSwapchainCreate(device,@ci,@swapchain),0)
 nvdWsiClear() : nvdPresentClear()
 NwtObserve(106,nvdWsiRollback(),0)
 NwtObserve(107,nvdWsiEnabled(),0)
 NwtObserve(108,nvdWsiRecordingAllowed(device,1),1)
 NwtTryBegin(110,device,1,-29999,1)

 ; Each actual bridge phase must return the acquired image to AVAILABLE,
 ; retire any actual ticket and permit another acquisition. No seeded arrays.
 For stage=1 To 4
  i=200+stage*100
  NwtObserve(i,avkWsiAcquire(device,swapchain,0,@index),0)
  NwtObserve(i+1,nvdWsiAttach(device,swapchain,index,stage),0)
  NwtObserve(i+2,nvdWsiState,1)
  NwtObserve(i+3,Bool(nvdWsiImageKey=images[index]),1)
  NwtObserve(i+20,nvdWsiRecordingAllowed(device,stage),1)
  NwtObserve(i+21,nvdWsiRecordingAllowed(device+1,stage),0)
  NwtObserve(i+22,nvdWsiRecordingAllowed(device,stage+1),0)
  NwtTryBegin(i+40,device,stage,-29999,1)
  NwtTryBegin(i+42,device+1,stage,-21202,0)
  NwtTryBegin(i+44,device,stage+1,-21202,0)
  If stage>=2 : NwtObserve(i+4,nvdWsiMarkReady(),0) : EndIf
  If stage>=2 : NwtObserve(i+23,nvdWsiRecordingAllowed(device,stage),0) : EndIf
  If stage>=2 : NwtTryBegin(i+46,device,stage,-21202,0) : EndIf
  If stage>=3
   NwtObserve(i+5,nvdWsiReserve(),0) : savedTicket=nvdWsiTicket
   NwtObserve(i+6,Bool(savedTicket<>0),1)
   NwtObserve(i+25,nvdWsiRecordingAllowed(device,stage),0)
   NwtTryBegin(i+48,device,stage,-21202,0)
  EndIf
  If stage=4
   NwtObserve(i+7,nvdWsiCommit(),0)
   NwtObserve(i+8,avkWsiImageState(device,swapchain,index),3)
   NwtObserve(i+26,nvdWsiRecordingAllowed(device,stage),0)
   NwtTryBegin(i+50,device,stage,-21202,0)
   NwtObserve(i+9,nvdPresentPublish(stage,777,stage,64,64,64,64,256,0),1)
   NwtObserve(i+10,Bool(nvdPresent\wsiTicket=savedTicket),1)
   NwtObserve(i+11,nvdPresentInvalidate(stage,777),1)
  Else
   NwtObserve(i+11,nvdWsiRollback(),0)
  EndIf
  NwtObserve(i+12,nvdWsiState,0)
  NwtObserve(i+13,nvdWsiTicket,0)
  NwtObserve(i+14,nvdWsiImageIndex,-1)
  NwtObserve(i+15,nvdWsiImageKey,0)
  NwtObserve(i+16,avkWsiImageState(device,swapchain,index),0)
  NwtObserve(i+17,nvdPresentPending(),0)
  NwtObserve(i+18,nvdWsiRollback(),0)
  NwtObserve(i+24,nvdWsiRecordingAllowed(device,stage),1)
  NwtTryBegin(i+52,device,stage,-29999,1)
  If stage>=3 : NwtObserve(i+19,avkWsiPresentRollback(savedTicket),#ANVIL_VK_ERR_HANDLE) : EndIf
 Next

 ; A distinct valid reservation blocks release of a READY bridge image.
 ; The real core refuses it; the bridge must retain its identity for retry.
 NwtObserve(700,avkWsiAcquire(device,swapchain,0,@index),0)
 NwtObserve(701,nvdWsiAttach(device,swapchain,index,7),0)
 NwtObserve(702,nvdWsiMarkReady(),0)
 item\swapchain=swapchain : item\imageIndex=index
 NwtObserve(703,avkWsiPresentReserve(device,1,@item,@ticket),0)
 NwtObserve(704,nvdWsiRollback(),#ANVIL_VK_ERR_STATE)
 NwtObserve(705,nvdWsiState,2)
 NwtObserve(706,Bool(nvdWsiDevice=device),1)
 NwtObserve(707,Bool(nvdWsiSwapchain=swapchain),1)
 NwtObserve(708,Bool(nvdWsiImageIndex=index),1)
 NwtObserve(709,Bool(nvdWsiImageKey=images[index]),1)
 NwtObserve(710,nvdWsiTargetGeneration,7)
 NwtObserve(711,avkWsiImageState(device,swapchain,index),2)
 NwtObserve(717,nvdWsiRecordingAllowed(device,7),0)
 NwtTryBegin(718,device,7,-21202,0)
 NwtObserve(712,avkWsiSwapchainDestroy(device,swapchain),#ANVIL_VK_ERR_STATE)
 NwtObserve(713,avkWsiPresentRollback(ticket),0)
 NwtObserve(714,nvdWsiRollback(),0)
 NwtObserve(715,nvdWsiState,0)
 NwtObserve(716,avkWsiImageState(device,swapchain,index),0)

 ; A wrong consumer cannot complete the committed ticket or clear its record.
 NwtObserve(800,avkWsiAcquire(device,swapchain,0,@index),0)
 NwtObserve(801,nvdWsiAttach(device,swapchain,index,8),0)
 NwtObserve(802,nvdWsiMarkReady(),0)
 NwtObserve(803,nvdWsiReserve(),0)
 NwtObserve(804,nvdWsiCommit(),0) : savedTicket=nvdWsiTicket
 NwtObserve(805,nvdPresentPublish(8,888,8,64,64,64,64,256,0),1)
 NwtObserve(806,nvdPresentConsume(9,888),0)
 NwtObserve(807,nvdPresentInvalidate(8,889),0)
 NwtObserve(808,nvdWsiState,4)
 NwtObserve(809,Bool(nvdWsiTicket=savedTicket),1)
 NwtObserve(810,nvdPresentPending(),1)
 NwtObserve(811,avkWsiImageState(device,swapchain,index),3)
 NwtObserve(812,nvdPresentConsume(8,888),1)
 NwtObserve(813,nvdPresentPending(),0)
 NwtObserve(814,nvdWsiState,0)
 NwtObserve(815,avkWsiImageState(device,swapchain,index),0)

 ; Core ownership can change before the bridge receives the transition.
 ; A still-ACQUIRED bridge alone is insufficient authority to record.
 NwtObserve(850,avkWsiAcquire(device,swapchain,0,@index),0)
 NwtObserve(851,nvdWsiAttach(device,swapchain,index,85),0)
 NwtObserve(852,nvdWsiRecordingAllowed(device,85),1)
 NwtObserve(853,avkWsiMarkRenderReady(device,swapchain,index),0)
 NwtObserve(854,nvdWsiState,1)
 NwtObserve(855,nvdWsiRecordingAllowed(device,85),0)
 NwtTryBegin(858,device,85,-21202,0)
 NwtObserve(856,nvdWsiRollback(),0)
 NwtObserve(857,avkWsiImageState(device,swapchain,index),0)

 ; Provider loss invalidates future work but must not prevent ownership return.
 NwtObserve(900,avkWsiAcquire(device,swapchain,0,@index),0)
 NwtObserve(901,nvdWsiAttach(device,swapchain,index,9),0)
 NwtObserve(902,nvdWsiMarkReady(),0)
 NwtObserve(903,avkWsiProviderLose(provider),0)
 NwtObserve(904,nvdWsiReserve(),#ANVIL_VK_ERR_STATE)
 NwtObserve(905,nvdWsiState,2)
 NwtObserve(906,nvdWsiTicket,0)
 NwtObserve(907,nvdWsiRollback(),0)
 NwtObserve(908,avkWsiImageState(device,swapchain,index),0)
 NwtObserve(909,avkWsiAcquire(device,swapchain,0,@index2),#VK_ERROR_SURFACE_LOST_KHR)
 NwtObserve(910,avkWsiSwapchainDestroy(device,swapchain),0)
 NwtObserve(911,avkWsiSurfaceDestroy(inst,surface),0)
 NwtObserve(912,avkWsiProviderDestroy(provider),0)
 NwtObserve(913,AnvilVkDeviceDestroy(device),0)
 NwtObserve(914,AnvilVkInstanceDestroy(inst),0)
 ProcedureReturn nwtFailures
EndProcedure

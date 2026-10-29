; Actual core and WSI ownership, explicit state-only backend. No display/GPU.
EnableFloatingPoint
XIncludeFile "Anvil/Graphics/Vulkan/vk_api.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_backend_test.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_wsi.pbi"
Global ti.i,tp.i,td.i,provider.i,surface.i,chain.i
Procedure ParentProofReset()
 Define n.i
 For n=1 To #ANVIL_VK_MAX_INSTANCES : avkInstLive[n]=0 : Next
 For n=1 To #ANVIL_VK_MAX_PHYSICAL_DEVICES : avkPhysLive[n]=0 : Next
 For n=1 To #ANVIL_VK_MAX_DEVICES : avkDevLive[n]=0 : Next
 For n=1 To #ANVIL_VK_MAX_QUEUES : avkQueueLive[n]=0 : Next
 For n=1 To #ANVIL_VK_WSI_MAX_PROVIDERS : avkWsiProvLive[n]=0 : Next
 For n=1 To #ANVIL_VK_WSI_MAX_SURFACES : avkWsiSurfLive[n]=0 : Next
 For n=1 To #ANVIL_VK_WSI_MAX_SWAPCHAINS : avkWsiSwapLive[n]=0 : Next
 For n=0 To (#ANVIL_VK_WSI_MAX_SWAPCHAINS+1)*#ANVIL_VK_WSI_MAX_IMAGES-1 : avkWsiSwapImageState[n]=0 : Next
 For n=1 To #ANVIL_VK_MAX_SEMAPHORES : avkSemLive[n]=0 : Next
 avkFlightActive=0 : avkFlightQuarantined=0
 avkTbHeapBase=$6200000 : avkTbHeapBytes=$100000
 ti=0 : tp=0 : td=0 : provider=0 : surface=0 : chain=0
 AnvilVkFaultClear()
EndProcedure
Procedure.i ParentProofSetup(device.i)
 Define count.i,rc.i
 rc=AnvilVkInstanceCreate(@ti) : If rc<>0 : ProcedureReturn rc : EndIf
 count=1 : rc=AnvilVkPhysicalEnumerate(ti,@count,@tp) : If rc<>0 : ProcedureReturn rc : EndIf
 If device<>0 : rc=AnvilVkDeviceCreate(tp,@td) : EndIf
 ProcedureReturn rc
EndProcedure
Procedure.i ParentProofSource(chainWanted.i)
 Define info.AnvilVkWsiProviderInfo,fmt.AnvilVkWsiFormat,mode.i,ci.AnvilVkWsiSwapchainInfo,image.i,rc.i
 info\cookie=707 : info\capabilities\minImageCount=1 : info\capabilities\maxImageCount=1
 info\capabilities\currentWidth=64 : info\capabilities\currentHeight=64
 info\capabilities\minWidth=64 : info\capabilities\minHeight=64
 info\capabilities\maxWidth=64 : info\capabilities\maxHeight=64
 info\capabilities\maxImageArrayLayers=1 : info\capabilities\supportedTransforms=1
 info\capabilities\currentTransform=1 : info\capabilities\supportedCompositeAlpha=1
 info\capabilities\supportedUsageFlags=#VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT
 fmt\format=#VK_FORMAT_B8G8R8A8_UNORM : fmt\colorSpace=0 : mode=2
 info\formatCount=1 : info\formats=@fmt : info\presentModeCount=1 : info\presentModes=@mode
 rc=avkWsiProviderRegister(@info,@provider) : If rc<>0 : ProcedureReturn rc : EndIf
 rc=avkWsiSurfaceCreate(ti,provider,808,@surface) : If rc<>0 Or chainWanted=0 : ProcedureReturn rc : EndIf
 ci\surface=surface : ci\minImageCount=1 : ci\imageFormat=fmt\format : ci\imageColorSpace=0
 ci\imageWidth=64 : ci\imageHeight=64 : ci\imageArrayLayers=1 : ci\imageUsage=#VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT
 ci\imageSharingMode=0 : ci\preTransform=1 : ci\compositeAlpha=1 : ci\presentMode=2 : ci\clipped=1
 image=909 : ci\providerImageCount=1 : ci\providerImages=@image
 ProcedureReturn avkWsiSwapchainCreate(td,@ci,@chain)
EndProcedure
Procedure ParentProofRecord(id.i,rc.i)
 Define at.i
 at=#TC_REPORT+64+(id-1)*96
 PokeI(at,id) : PokeI(at+8,rc) : PokeI(at+16,avkInstLive[1]) : PokeI(at+24,avkPhysLive[1])
 PokeI(at+32,avkDevLive[1]) : PokeI(at+40,avkWsiSurfLive[1]) : PokeI(at+48,avkWsiSwapLive[1])
 PokeI(at+56,avkWsiSwapImageState[avkWsiImageIndex(1,0)]) : PokeI(at+64,avkInstLive[2])
 PokeI(at+72,avkSemLive[1]) : PokeI(at+80,avkFlightActive) : PokeI(at+88,AnvilVkFaultCode())
EndProcedure
Procedure.i Main(services.i)
 Define rc.i,n.i,index.i,other.i
 For n=0 To 4095 : PokeA(#TC_REPORT+n,0) : Next
 ParentProofReset() : rc=ParentProofSetup(1) : If rc<>0 : ProcedureReturn 101 : EndIf
 avkFlightActive=1 : rc=AnvilVkInstanceDestroy(ti) : ParentProofRecord(1,rc)
 ParentProofReset() : rc=ParentProofSetup(1) : rc=ParentProofSource(1) : If rc<>0 : ProcedureReturn 102 : EndIf
 avkSemLive[1]=1 : avkSemDev[1]=1 : avkSemDevGen[1]=avkTokenGen(td)
 rc=AnvilVkDeviceDestroy(td) : ParentProofRecord(2,rc)
 ParentProofReset() : rc=ParentProofSetup(0) : rc=ParentProofSource(0) : If rc<>0 : ProcedureReturn 103 : EndIf
 rc=AnvilVkInstanceDestroy(ti) : ParentProofRecord(3,rc)
 ParentProofReset() : rc=ParentProofSetup(0) : rc=AnvilVkInstanceDestroy(ti) : ParentProofRecord(4,rc)
 ParentProofReset() : rc=ParentProofSetup(1) : rc=AnvilVkInstanceDestroy(ti) : ParentProofRecord(5,rc)
 ParentProofReset() : rc=ParentProofSetup(1) : rc=ParentProofSource(1)
 rc=avkWsiSwapchainDestroy(td,chain) : rc=avkWsiSurfaceDestroy(ti,surface) : rc=avkWsiProviderDestroy(provider)
 rc=AnvilVkDeviceDestroy(td) : rc=AnvilVkInstanceDestroy(ti) : ParentProofRecord(6,rc)
 ParentProofReset() : rc=ParentProofSetup(0) : other=ti : rc=ParentProofSetup(0) : rc=ParentProofSource(0)
 rc=AnvilVkInstanceDestroy(other) : ParentProofRecord(7,rc)
 ParentProofReset() : rc=ParentProofSetup(1) : rc=ParentProofSource(1) : index=0 : rc=avkWsiAcquire(td,chain,0,@index)
 rc=AnvilVkDeviceDestroy(td) : ParentProofRecord(8,rc)
 ParentProofReset() : rc=ParentProofSetup(1) : avkFlightActive=1 : vkDestroyInstance(ti,0) : ParentProofRecord(9,AnvilVkFaultCode())
 ParentProofReset() : rc=AnvilVkInstanceDestroy(123) : ParentProofRecord(10,rc)
 ParentProofReset() : rc=AnvilVkDeviceDestroy(123) : ParentProofRecord(11,rc)
 PokeI(#TC_REPORT,$50415254) : PokeI(#TC_REPORT+8,0) : PokeI(#TC_REPORT+16,11) : PokeI(#TC_REPORT+24,12)
 ProcedureReturn 0
EndProcedure

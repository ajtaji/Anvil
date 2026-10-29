; Actual object engine over the explicit state-only backend. No GPU submission.
XIncludeFile "Anvil/Graphics/Vulkan/vk_api.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_backend_test.pbi"
Global Dim fbqHeap.a[65536]
Global fbqRecords.i,fbqFailures.i

Procedure FbqCheck(tag.i,value.i,wanted.i)
 PokeI(#FBQ_REPORT+64+fbqRecords*16,tag)
 PokeI(#FBQ_REPORT+72+fbqRecords*16,value)
 fbqRecords=fbqRecords+1
 If value<>wanted : fbqFailures=fbqFailures+1 : EndIf
EndProcedure

Procedure.i FbqDifferent(a.i,b.i)
 If a<>b : ProcedureReturn 1 : EndIf
 ProcedureReturn 0
EndProcedure

Procedure.i FbqPassFlags(device.i,flags.i,*out)
 Define att.VkAttachmentDescription,sub.VkSubpassDescription,ref.VkAttachmentReference
 att\flags=flags
 att\format=#VK_FORMAT_B8G8R8A8_UNORM : att\samples=#VK_SAMPLE_COUNT_1_BIT
 att\loadOp=#VK_ATTACHMENT_LOAD_OP_CLEAR : att\storeOp=#VK_ATTACHMENT_STORE_OP_STORE
 att\initialLayout=#VK_IMAGE_LAYOUT_UNDEFINED : att\finalLayout=#VK_IMAGE_LAYOUT_GENERAL
 ref\attachment=0 : ref\layout=#VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL
 sub\pipelineBindPoint=#VK_PIPELINE_BIND_POINT_GRAPHICS
 sub\colorAttachmentCount=1 : sub\pColorAttachments=@ref
 ProcedureReturn AnvilVkRenderPassCreate(device,@att,@sub,*out)
EndProcedure

Procedure.i FbqPass(device.i,*out)
 ProcedureReturn FbqPassFlags(device,0,*out)
EndProcedure

Procedure.i FbqImage(device.i,*image,*memory,bind.i)
 Define rc.i
 rc=AnvilVkImageCreate(device,32,16,#VK_FORMAT_B8G8R8A8_UNORM,#VK_IMAGE_TILING_LINEAR,#VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT,#VK_IMAGE_LAYOUT_UNDEFINED,*image)
 If rc<>0 Or bind=0 : ProcedureReturn rc : EndIf
 rc=AnvilVkMemoryAllocate(device,AnvilVkImageSize(PeekI(*image)),0,*memory)
 If rc<>0 : ProcedureReturn rc : EndIf
 ProcedureReturn AnvilVkImageBindMemory(device,PeekI(*image),PeekI(*memory),0)
EndProcedure

Procedure.i FramebufferTargetProof()
 Define inst.i,physical.i,dev.i,foreign.i,rp.i,otherPass.i,oldPass.i
 Define image.i,memory.i,view.i,fb.i,old.i,unbound.i,unboundView.i,unboundFb.i,unboundMemory.i
 Define padded.i,paddedMem.i,paddedView.i,paddedFb.i
 Define count.l=1
 Define i.i,n.i,mismatchPass.i
 AnvilVkTestBackendHeap(@fbqHeap[0],65536)
 FbqCheck(100,AnvilVkInstanceCreate(@inst),0)
 FbqCheck(101,AnvilVkPhysicalEnumerate(inst,@count,@physical),0)
 FbqCheck(102,AnvilVkDeviceCreate(physical,@dev),0)
 FbqCheck(103,AnvilVkDeviceCreate(physical,@foreign),0)
 FbqCheck(104,FbqPass(dev,@rp),0) : FbqCheck(105,FbqPass(dev,@otherPass),0)
 FbqCheck(106,FbqImage(dev,@image,@memory,1),0)
 FbqCheck(107,AnvilVkImageViewCreate(dev,image,#VK_IMAGE_VIEW_TYPE_2D,#VK_FORMAT_B8G8R8A8_UNORM,@view),0)
 FbqCheck(108,AnvilVkFramebufferCreate(dev,rp,view,32,16,1,@fb),0)
 AnvilVkFaultClear()
 FbqCheck(110,AnvilVkFramebufferTargetCheck(dev,rp,fb,32,16,128),0)
 FbqCheck(122,AnvilVkFramebufferTargetPitch(dev,rp,fb,32,16),128)
 FbqCheck(111,AnvilVkFramebufferTargetCheck(0,rp,fb,32,16,128),-20002)
 FbqCheck(112,AnvilVkFramebufferTargetCheck(dev,0,fb,32,16,128),-20002)
 FbqCheck(113,AnvilVkFramebufferTargetCheck(dev,rp,0,32,16,128),-20002)
 FbqCheck(114,AnvilVkFramebufferTargetCheck(foreign,rp,fb,32,16,128),-20003)
 FbqCheck(115,AnvilVkFramebufferTargetCheck(dev,otherPass,fb,32,16,128),0)
 ; Compatibility retains attachment flags; distinct objects alone do not differ.
 FbqCheck(223,FbqPassFlags(dev,1,@mismatchPass),0)
 FbqCheck(224,AnvilVkFramebufferTargetCheck(dev,mismatchPass,fb,32,16,128),-20001)
 AnvilVkRenderPassDestroy(dev,mismatchPass)
 FbqCheck(116,AnvilVkFramebufferTargetCheck(dev,rp,fb,31,16,128),-20001)
 FbqCheck(117,AnvilVkFramebufferTargetCheck(dev,rp,fb,32,15,128),-20001)
 FbqCheck(118,AnvilVkFramebufferTargetCheck(dev,rp,fb,32,16,132),-20001)
 FbqCheck(119,AnvilVkFramebufferTargetCheck(dev,rp,fb,0,16,128),-20001)
 FbqCheck(120,AnvilVkFramebufferTargetCheck(dev,rp,fb,32,16,128),0)
 FbqCheck(121,AnvilVkFaultCode(),0)
 ; Controlled retention-count injection, not a submitted or measured GPU flight.
 ; These are the first objects of each family in this isolated composition.
 avkFbInFlight[1]=1
 FbqCheck(130,AnvilVkFramebufferTargetCheck(dev,rp,fb,32,16,128),-20004)
 FbqCheck(139,AnvilVkFramebufferTargetPitch(dev,rp,fb,32,16),-20004)
 FbqCheck(131,avkFbInFlight[1],1) : avkFbInFlight[1]=0
 avkIvInFlight[1]=1
 FbqCheck(132,AnvilVkFramebufferTargetCheck(dev,rp,fb,32,16,128),-20004)
 FbqCheck(133,avkIvInFlight[1],1) : avkIvInFlight[1]=0
 avkImgInFlight[1]=1
 FbqCheck(134,AnvilVkFramebufferTargetCheck(dev,rp,fb,32,16,128),-20004)
 FbqCheck(135,avkImgInFlight[1],1) : avkImgInFlight[1]=0
 avkMemInFlight[1]=1
 FbqCheck(136,AnvilVkFramebufferTargetCheck(dev,rp,fb,32,16,128),-20004)
 FbqCheck(137,avkMemInFlight[1],1) : avkMemInFlight[1]=0
 FbqCheck(138,AnvilVkFramebufferTargetCheck(dev,rp,fb,32,16,128),0)
 old=fb : AnvilVkFramebufferDestroy(dev,fb)
 FbqCheck(140,AnvilVkFramebufferTargetCheck(dev,rp,old,32,16,128),-20002)
 FbqCheck(141,AnvilVkFramebufferCreate(dev,rp,view,32,16,1,@fb),0)
 FbqCheck(142,FbqDifferent(fb,old),1)
 FbqCheck(143,AnvilVkFramebufferTargetCheck(dev,rp,fb,32,16,128),0)
 old=view : AnvilVkImageViewDestroy(dev,view)
 FbqCheck(150,AnvilVkFramebufferTargetCheck(dev,rp,fb,32,16,128),-20004)
 FbqCheck(151,AnvilVkImageViewCreate(dev,image,#VK_IMAGE_VIEW_TYPE_2D,#VK_FORMAT_B8G8R8A8_UNORM,@view),0)
 FbqCheck(152,FbqDifferent(view,old),1)
 FbqCheck(153,AnvilVkFramebufferTargetCheck(dev,rp,fb,32,16,128),-20004)
 AnvilVkFramebufferDestroy(dev,fb)
 FbqCheck(154,AnvilVkFramebufferCreate(dev,rp,view,32,16,1,@fb),0)
 FbqCheck(155,AnvilVkFramebufferTargetCheck(dev,rp,fb,32,16,128),0)
 old=image : AnvilVkImageDestroy(dev,image) : AnvilVkMemoryFree(dev,memory)
 FbqCheck(160,AnvilVkFramebufferTargetCheck(dev,rp,fb,32,16,128),-20004)
 FbqCheck(161,FbqImage(dev,@image,@memory,1),0)
 FbqCheck(162,FbqDifferent(image,old),1)
 FbqCheck(163,AnvilVkFramebufferTargetCheck(dev,rp,fb,32,16,128),-20004)
 AnvilVkFramebufferDestroy(dev,fb) : AnvilVkImageViewDestroy(dev,view)
 FbqCheck(164,AnvilVkImageViewCreate(dev,image,#VK_IMAGE_VIEW_TYPE_2D,#VK_FORMAT_B8G8R8A8_UNORM,@view),0)
 FbqCheck(165,AnvilVkFramebufferCreate(dev,rp,view,32,16,1,@fb),0)
 FbqCheck(166,AnvilVkFramebufferTargetCheck(dev,rp,fb,32,16,128),0)
 oldPass=rp : AnvilVkRenderPassDestroy(dev,rp)
 FbqCheck(170,AnvilVkFramebufferTargetCheck(dev,oldPass,fb,32,16,128),-20002)
 FbqCheck(171,AnvilVkFramebufferTargetCheck(dev,otherPass,fb,32,16,128),0)
 FbqCheck(172,FbqPass(dev,@rp),0) : FbqCheck(173,FbqDifferent(rp,oldPass),1)
 FbqCheck(174,AnvilVkFramebufferTargetCheck(dev,rp,fb,32,16,128),0)
 AnvilVkFramebufferDestroy(dev,fb)
 FbqCheck(175,AnvilVkFramebufferCreate(dev,rp,view,32,16,1,@fb),0)
 FbqCheck(176,AnvilVkFramebufferTargetCheck(dev,rp,fb,32,16,128),0)
 FbqCheck(180,FbqImage(dev,@unbound,@unboundMemory,0),0)
 FbqCheck(181,AnvilVkImageViewCreate(dev,unbound,#VK_IMAGE_VIEW_TYPE_2D,#VK_FORMAT_B8G8R8A8_UNORM,@unboundView),0)
 FbqCheck(182,AnvilVkFramebufferCreate(dev,rp,unboundView,32,16,1,@unboundFb),0)
 FbqCheck(183,AnvilVkFramebufferTargetCheck(dev,rp,unboundFb,32,16,128),-20004)
 FbqCheck(187,AnvilVkFramebufferTargetPitch(dev,rp,unboundFb,32,16),-20004)
 FbqCheck(184,AnvilVkMemoryAllocate(dev,AnvilVkImageSize(unbound),0,@unboundMemory),0)
 FbqCheck(185,AnvilVkImageBindMemory(dev,unbound,unboundMemory,0),0)
 FbqCheck(186,AnvilVkFramebufferTargetCheck(dev,rp,unboundFb,32,16,128),0)
 ; An odd width has 124 pixel bytes but 128 backend-planned bytes per row.
 FbqCheck(200,AnvilVkImageCreate(dev,31,16,#VK_FORMAT_B8G8R8A8_UNORM,#VK_IMAGE_TILING_LINEAR,#VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT,#VK_IMAGE_LAYOUT_UNDEFINED,@padded),0)
 FbqCheck(201,AnvilVkMemoryAllocate(dev,AnvilVkImageSize(padded),0,@paddedMem),0)
 FbqCheck(202,AnvilVkImageBindMemory(dev,padded,paddedMem,0),0)
 FbqCheck(203,AnvilVkImageViewCreate(dev,padded,#VK_IMAGE_VIEW_TYPE_2D,#VK_FORMAT_B8G8R8A8_UNORM,@paddedView),0)
 FbqCheck(204,AnvilVkFramebufferCreate(dev,rp,paddedView,31,16,1,@paddedFb),0)
 FbqCheck(205,AnvilVkFramebufferTargetPitch(dev,rp,paddedFb,31,16),128)
 FbqCheck(206,AnvilVkFramebufferTargetCheck(dev,rp,paddedFb,31,16,124),-20001)
 FbqCheck(207,AnvilVkFramebufferTargetCheck(dev,rp,paddedFb,31,16,128),0)
 FbqCheck(208,AnvilVkFramebufferTargetPitch(dev,rp,paddedFb,32,16),-20001)
 FbqCheck(209,AnvilVkFramebufferTargetPitch(foreign,rp,paddedFb,31,16),-20003)
 FbqCheck(210,AnvilVkFramebufferTargetPitch(dev,rp,0,31,16),-20002)
 AnvilVkFramebufferDestroy(dev,paddedFb) : AnvilVkImageViewDestroy(dev,paddedView)
 AnvilVkImageDestroy(dev,padded) : AnvilVkMemoryFree(dev,paddedMem)
 AnvilVkFramebufferDestroy(dev,unboundFb) : AnvilVkFramebufferDestroy(dev,fb)
 AnvilVkImageViewDestroy(dev,unboundView) : AnvilVkImageViewDestroy(dev,view)
 AnvilVkImageDestroy(dev,unbound) : AnvilVkImageDestroy(dev,image)
 AnvilVkMemoryFree(dev,unboundMemory) : AnvilVkMemoryFree(dev,memory)
 AnvilVkRenderPassDestroy(dev,rp) : AnvilVkRenderPassDestroy(dev,otherPass)
 vkDestroyDevice(foreign,0) : vkDestroyDevice(dev,0) : vkDestroyInstance(inst,0)
 n=0 : For i=1 To #ANVIL_VK_MAX_FRAMEBUFFERS : n=n+avkFbLive[i] : Next : FbqCheck(190,n,0)
 n=0 : For i=1 To #ANVIL_VK_MAX_IMAGE_VIEWS : n=n+avkIvLive[i] : Next : FbqCheck(191,n,0)
 n=0 : For i=1 To #ANVIL_VK_MAX_IMAGES : n=n+avkImgLive[i] : Next : FbqCheck(192,n,0)
 n=0 : For i=1 To #ANVIL_VK_MAX_MEMORY : n=n+avkMemLive[i] : Next : FbqCheck(193,n,0)
 FbqCheck(194,AnvilVkTestBackendCalls(),0) : FbqCheck(195,AnvilVkFaultCode(),0)
 ProcedureReturn fbqFailures
EndProcedure

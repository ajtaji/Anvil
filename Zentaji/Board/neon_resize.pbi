; Resize only at the resident console's idle boundary. The old target stays
; allocated until its replacement is complete and the display accepts it.
Structure ZentajiResizeTarget
 image.i
 memory.i
 view.i
 framebuffer.i
EndStructure

Procedure znsResizeTargetFree(*t.ZentajiResizeTarget)
 If *t\framebuffer<>0 : vkDestroyFramebuffer(znsDev,*t\framebuffer,0) : EndIf
 If *t\view<>0 : vkDestroyImageView(znsDev,*t\view,0) : EndIf
 If *t\image<>0 : vkDestroyImage(znsDev,*t\image,0) : EndIf
 If *t\memory<>0 : vkFreeMemory(znsDev,*t\memory,0) : EndIf
EndProcedure

Procedure.i znsResizeTargetCreate(w.i,h.i,*t.ZentajiResizeTarget)
 Protected imageInfo.VkImageCreateInfo,req.VkMemoryRequirements,alloc.VkMemoryAllocateInfo
 Protected viewInfo.VkImageViewCreateInfo,frameInfo.VkFramebufferCreateInfo
 imageInfo\sType=#VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO
 imageInfo\imageType=#VK_IMAGE_TYPE_2D : imageInfo\format=#VK_FORMAT_B8G8R8A8_UNORM
 imageInfo\extent\width=w : imageInfo\extent\height=h : imageInfo\extent\depth=1
 imageInfo\mipLevels=1 : imageInfo\arrayLayers=1 : imageInfo\samples=#VK_SAMPLE_COUNT_1_BIT
 imageInfo\tiling=#VK_IMAGE_TILING_LINEAR
 imageInfo\usage=#VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | #VK_IMAGE_USAGE_TRANSFER_SRC_BIT
 imageInfo\sharingMode=#VK_SHARING_MODE_EXCLUSIVE : imageInfo\initialLayout=#VK_IMAGE_LAYOUT_UNDEFINED
 If vkCreateImage(znsDev,@imageInfo,0,@*t\image)<>#VK_SUCCESS : ProcedureReturn 0 : EndIf
 vkGetImageMemoryRequirements(znsDev,*t\image,@req)
 alloc\sType=#VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO : alloc\allocationSize=req\size : alloc\memoryTypeIndex=0
 If vkAllocateMemory(znsDev,@alloc,0,@*t\memory)<>#VK_SUCCESS : ProcedureReturn 0 : EndIf
 If vkBindImageMemory(znsDev,*t\image,*t\memory,0)<>#VK_SUCCESS : ProcedureReturn 0 : EndIf
 viewInfo\sType=#VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO
 viewInfo\image=*t\image : viewInfo\viewType=#VK_IMAGE_VIEW_TYPE_2D : viewInfo\format=#VK_FORMAT_B8G8R8A8_UNORM
 viewInfo\subresourceRange\aspectMask=#VK_IMAGE_ASPECT_COLOR_BIT
 viewInfo\subresourceRange\levelCount=1 : viewInfo\subresourceRange\layerCount=1
 If vkCreateImageView(znsDev,@viewInfo,0,@*t\view)<>#VK_SUCCESS : ProcedureReturn 0 : EndIf
 frameInfo\sType=#VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO
 frameInfo\renderPass=znsPass : frameInfo\attachmentCount=1 : frameInfo\pAttachments=@*t\view
 frameInfo\width=w : frameInfo\height=h : frameInfo\layers=1
 If vkCreateFramebuffer(znsDev,@frameInfo,0,@*t\framebuffer)<>#VK_SUCCESS : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure

; 1 unchanged/deferred, 2 resized, 0 ownership failure. Out-of-memory leaves
; the current image usable and the host request pending for a smaller size.
Procedure.i ZentajiNeonSurfaceResize()
 Protected wanted.q,w.i,h.i,pitch.i,enabled.i,faults.i
 Protected fresh.ZentajiResizeTarget,old.ZentajiResizeTarget
 wanted=PeekQ(#ZEN_GFX_DISPLAY+$B0)
 If wanted=0 : ProcedureReturn 1 : EndIf
 w=wanted&$FFFFFFFF : h=(wanted>>32)&$FFFFFFFF
 If w=znsWidth And h=znsHeight : ProcedureReturn 1 : EndIf
 If w<64 Or h<=128 Or w>8192 Or h>8192 : ProcedureReturn 1 : EndIf
 If znsState<>2 Or nvcInFrame<>0 Or NeonVkChromePresentPending()<>0 : ProcedureReturn 1 : EndIf
 If ZentajiGraphicsDisplayOwned()<>1 : ProcedureReturn 0 : EndIf
 If zgdPending<>0 Or zgdWriter<>0 Or avkZenPresentState<>0 : ProcedureReturn 1 : EndIf
 If ((w*h*4+4095)&-4096)>zgdSpan : ProcedureReturn 1 : EndIf
 If vkDeviceWaitIdle(znsDev)<>#VK_SUCCESS : ProcedureReturn 0 : EndIf
 If znsResizeTargetCreate(w,h,@fresh)<>1
  znsResizeTargetFree(@fresh) : ProcedureReturn 1
 EndIf
 pitch=AnvilVkImageRowPitch(fresh\image)
 If NeonVkChromeRebind(fresh\framebuffer,w,h,w,h,pitch,0)<>#VK_SUCCESS
  znsResizeTargetFree(@fresh) : ProcedureReturn 0
 EndIf
 enabled=zgdEnabled
 PokeQ(#ZEN_GFX_DISPLAY+$10,0) : zgdEnabled=0
 PokeQ(#ZEN_GFX_DISPLAY+$B8,wanted)
 If PeekQ(#ZEN_GFX_DISPLAY+$B8)<>wanted
  ; A newer host resize can supersede the request during allocation.
  PokeQ(#ZEN_GFX_DISPLAY+8,$FF00)
  PokeQ(#ZEN_GFX_DISPLAY+$10,enabled) : zgdEnabled=enabled
  If NeonVkChromeRebind(znsFramebuffer,znsWidth,znsHeight,znsWidth,znsHeight,znsImagePitch,0)<>#VK_SUCCESS : ProcedureReturn 0 : EndIf
  znsResizeTargetFree(@fresh) : ProcedureReturn 1
 EndIf
 old\image=znsImage : old\memory=znsMemory : old\view=znsView : old\framebuffer=znsFramebuffer
 znsImage=fresh\image : znsMemory=fresh\memory : znsView=fresh\view : znsFramebuffer=fresh\framebuffer
 znsWidth=w : znsHeight=h : znsImagePitch=pitch : znsImageBase=AnvilVkImageAddress(znsImage)
 zgdWidth=w : zgdHeight=h : zgdPitch=w*4
 PokeQ(#ZEN_GFX_DISPLAY+$70,zgdPitch)
 nvlFramebuffer=znsFramebuffer : nvlWidth=w : nvlHeight=h
 If NeonVkPortCanvas(w,h,w,h)<>#NEON_OK : ProcedureReturn 0 : EndIf
 faults=AnvilVkFaultCount() : znsResizeTargetFree(@old)
 If AnvilVkFaultCount()<>faults : ProcedureReturn 0 : EndIf
 ProcedureReturn 2
EndProcedure

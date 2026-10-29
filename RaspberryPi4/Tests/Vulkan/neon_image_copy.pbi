; SPDX-License-Identifier: MIT
; Real two-pass GPU render/copy/sample proof; no source readback or re-upload.
Global NciFailure.i,NciChecks.i
Global Dim NciZero.l[2048]
Global Dim NciClear.l[4]
Procedure NciCheck(actual.i,expected.i)
  NciChecks=NciChecks+1
  PokeI($E1C00100+(NciChecks-1)*16,actual)
  PokeI($E1C00108+(NciChecks-1)*16,expected)
  If actual<>expected And NciFailure=0 : NciFailure=NciChecks : EndIf
  PokeI($E1C00010,NciFailure) : PokeI($E1C00018,NciChecks)
EndProcedure
Procedure.i NciDraw(base.i,pitch.i,phase.i)
  Protected rc.i,x.i,y.i,dest.i
  rc=NeonVkChromeBegin(@NciClear[0])
  If rc=0 : rc=NeonVkChromeImageSpriteDrawId(1,20,20,0,0,64,32,128,64,$FFFFFFFF) : EndIf
  If rc=0 : rc=NeonVkChromeImageSpriteDrawId(16,180,20,0,0,64,32,128,64,$FFFFFFFF) : EndIf
  If rc=0 : rc=NeonVkChromeEnd() : EndIf
  If rc=0 And NeonVkChromePresentConsume()<>1 : rc=-21202 : EndIf
  If rc<>0 : ProcedureReturn rc : EndIf
  ; Only the FINAL sampled attachment is copied to a host oracle buffer.
  dest=$E2400000+phase*81920
  For y=0 To 63
    For x=0 To 319
      PokeL(dest+(y*320+x)*4,PeekL(base+(y+20)*pitch+(x+20)*4))
    Next
  Next
  ProcedureReturn 0
EndProcedure

Procedure.i NciFrame(dev.i,renderPass.i,mainFramebuffer.i,base.i,pitch.i)
  Protected info.VkImageCreateInfo,req.VkMemoryRequirements,alloc.VkMemoryAllocateInfo
  Protected vi.VkImageViewCreateInfo,fi.VkFramebufferCreateInfo
  Protected image.i,memory.i,view.i,framebuffer.i,rc.i
  info\sType=#VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO
  info\imageType=#VK_IMAGE_TYPE_2D : info\format=#VK_FORMAT_B8G8R8A8_UNORM
  info\extent\width=64 : info\extent\height=32 : info\extent\depth=1
  info\mipLevels=1 : info\arrayLayers=1 : info\samples=#VK_SAMPLE_COUNT_1_BIT
  info\tiling=#VK_IMAGE_TILING_LINEAR
  info\usage=#VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | #VK_IMAGE_USAGE_TRANSFER_SRC_BIT
  info\sharingMode=#VK_SHARING_MODE_EXCLUSIVE : info\initialLayout=#VK_IMAGE_LAYOUT_UNDEFINED
  rc=vkCreateImage(dev,@info,0,@image)
  NciCheck(rc,0)
  If NciFailure<>0 : Goto NciCleanup : EndIf
  vkGetImageMemoryRequirements(dev,image,@req)
  alloc\sType=#VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO
  alloc\allocationSize=req\size : alloc\memoryTypeIndex=0
  rc=vkAllocateMemory(dev,@alloc,0,@memory)
  NciCheck(rc,0)
  NciCheck(vkBindImageMemory(dev,image,memory,0),0)
  If NciFailure<>0 : Goto NciCleanup : EndIf
  vi\sType=#VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO
  vi\image=image : vi\viewType=#VK_IMAGE_VIEW_TYPE_2D : vi\format=#VK_FORMAT_B8G8R8A8_UNORM
  vi\subresourceRange\aspectMask=#VK_IMAGE_ASPECT_COLOR_BIT
  vi\subresourceRange\levelCount=1 : vi\subresourceRange\layerCount=1
  rc=vkCreateImageView(dev,@vi,0,@view)
  NciCheck(rc,0)
  fi\sType=#VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO
  fi\renderPass=renderPass : fi\attachmentCount=1 : fi\pAttachments=@view
  fi\width=64 : fi\height=32 : fi\layers=1
  rc=vkCreateFramebuffer(dev,@fi,0,@framebuffer)
  NciCheck(rc,0)
  If NciFailure<>0 : Goto NciCleanup : EndIf
  NciCheck(NeonVkChromeImageSpriteReplaceBGRAId(1,@NciZero[0],64,32),0)
  NciCheck(NeonVkChromeImageSpriteReplaceBGRAId(16,@NciZero[0],64,32),0)
  NciCheck(NeonVkChromeImageSpriteGenerationId(1),1)
  NciCheck(NeonVkChromeImageSpriteGenerationId(16),1)
  NciCheck(NeonVkChromeImageSpriteCopyId(0,image,#VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL),-21201)
  NciCheck(NeonVkChromeImageSpriteCopyId(17,image,#VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL),-21201)
  NciCheck(NeonVkChromeImageSpriteCopyId(1,0,#VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL),-21201)
  NciCheck(NeonVkChromeImageSpriteCopyId(1,image,#VK_IMAGE_LAYOUT_UNDEFINED),-21201)
  NciCheck(NeonVkChromeImageSpriteCopyId(2,image,#VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL),-21202)
  NciCheck(NeonVkChromeRebind(framebuffer,64,32,64,32,AnvilVkImageRowPitch(image),0),0)
  NciCheck(NeonVkChromeBegin(@NciClear[0]),0)
  NciCheck(NeonVkChromeImageSpriteCopy(image,#VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL),-21202)
  NciCheck(NeonVkChromeBox(0,0,32,32,$FFFF0000),0)
  NciCheck(NeonVkChromeBox(32,0,32,32,$FF00FF00),0)
  NciCheck(NeonVkChromeEnd(),0)
  NciCheck(NeonVkChromeImageSpriteCopy(image,#VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL),-21202)
  NciCheck(NeonVkChromePresentConsume(),1)
  NciCheck(NeonVkChromeImageSpriteCopy(image,#VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL),0)
  NciCheck(NeonVkChromeImageSpriteCopyId(16,image,#VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL),0)
  NciCheck(AnvilVkImageLayout(image),6)
  NciCheck(NeonVkChromeImageSpriteGenerationId(1),2)
  NciCheck(NeonVkChromeImageSpriteGenerationId(16),2)
  NciCheck(NeonVkChromeBegin(@NciClear[0]),0)
  NciCheck(NeonVkChromeBox(0,0,32,32,$FF0000FF),0)
  NciCheck(NeonVkChromeBox(32,0,32,32,$FFFFFF00),0)
  NciCheck(NeonVkChromeEnd(),0)
  NciCheck(NeonVkChromePresentConsume(),1)
  NciCheck(NeonVkChromeRebind(mainFramebuffer,#NVWA_WIDTH,#NVWA_HEIGHT,#NVWA_WIDTH,#NVWA_HEIGHT,pitch,0),0)
  NciCheck(NciDraw(base,pitch,0),0)
  NciCheck(NeonVkChromeImageSpriteCopy(image,#VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL),0)
  NciCheck(NeonVkChromeImageSpriteGenerationId(1),3)
  NciCheck(NeonVkChromeImageSpriteGenerationId(16),2)
  NciCheck(Bool(NeonVkChromeImageSpriteCopyId(1,$12345678,#VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL)<0),1)
  NciCheck(NeonVkChromeReady(),1)
  NciCheck(NeonVkChromeImageSpriteGenerationId(1),3)
  NciCheck(NciDraw(base,pitch,1),0)
  NciCheck(NeonVkChromeImageSpriteClearId(1),0)
  NciCheck(NeonVkChromeImageSpriteClearId(16),0)
  NciCheck(NeonVkChromeImageSpriteGenerationId(1),4)
  NciCheck(NeonVkChromeImageSpriteGenerationId(16),3)
  NciCleanup:
  If NeonVkChromePresentPending()=1 : NeonVkChromePresentConsume() : EndIf
  NeonVkChromeRebind(mainFramebuffer,#NVWA_WIDTH,#NVWA_HEIGHT,#NVWA_WIDTH,#NVWA_HEIGHT,pitch,0)
  vkDeviceWaitIdle(dev)
  If framebuffer<>0 : vkDestroyFramebuffer(dev,framebuffer,0) : EndIf
  If view<>0 : vkDestroyImageView(dev,view,0) : EndIf
  If image<>0 : vkDestroyImage(dev,image,0) : EndIf
  If memory<>0 : vkFreeMemory(dev,memory,0) : EndIf
  ProcedureReturn NciFailure
EndProcedure

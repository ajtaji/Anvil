; SPDX-License-Identifier: MIT
; Real fixed canvas, retained resources, aspect fit and final sampled pass.
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_canvas.pbi"
Global CnvFailure.i,CnvChecks.i,CnvCanvas.NeonVkCanvas
Global Dim CnvScratch.q[1024]
Global Dim CnvClear.l[4]
Procedure CnvCheck(actual.i,expected.i)
  CnvChecks=CnvChecks+1
  PokeI($E1C00100+(CnvChecks-1)*16,actual)
  PokeI($E1C00108+(CnvChecks-1)*16,expected)
  If actual<>expected And CnvFailure=0 : CnvFailure=CnvChecks : EndIf
  PokeI($E1C00010,CnvFailure) : PokeI($E1C00018,CnvChecks)
EndProcedure

Procedure.i CnvFrame(dev.i,renderPass.i,originalFramebuffer.i,base.i,pitch.i)
  Protected info.VkImageCreateInfo,req.VkMemoryRequirements,alloc.VkMemoryAllocateInfo
  Protected vi.VkImageViewCreateInfo,fi.VkFramebufferCreateInfo,target.NeonVkTargetInfo
  Protected v.NeonCanvasViewport,point.NeonCanvasPoint
  Protected image.i,memory.i,view.i,framebuffer.i,rc.i,sourcePitch.i,sourceBase.i
  Protected x.i,y.i,rotation.i,logicalW.i,logicalH.i,dest.i

  CnvCheck(SizeOf(NeonVkTargetInfo),88)
  CnvCheck(SizeOf(NeonVkCanvas),264)
  CnvCheck(NeonCanvasFit(@v,64,32,320,240),0)
  CnvCheck(v\x,0)
  CnvCheck(v\y,40)
  CnvCheck(v\width,320)
  CnvCheck(v\height,160)
  point\xQ16=12345 : point\yQ16=54321
  CnvCheck(NeonCanvasMapPoint(@v,0,39,@point),0)
  CnvCheck(point\xQ16,12345)
  CnvCheck(point\yQ16,54321)
  CnvCheck(NeonCanvasMapPoint(@v,160,120,@point),1)
  CnvCheck(point\xQ16,2097152)
  CnvCheck(point\yQ16,1048576)
  CnvCheck(NeonCanvasMapPoint(@v,320,120,@point),0)
  CnvCheck(NeonCanvasMapPoint(@v,0,200,@point),0)
  CnvCheck(NeonCanvasFit(@v,4,3,101,100),0)
  CnvCheck(v\x,0)
  CnvCheck(v\y,12)
  CnvCheck(v\width,101)
  CnvCheck(v\height,75)
  CnvCheck(NeonCanvasFit(@v,0,3,101,100),-21341)
  CnvCheck(v\height,75)
  CnvCheck(NeonCanvasFit(@v,8192,1,1,8192),-21344)
  CnvCheck(NeonCanvasMapPoint(@v,0,12,@v),-21341)
  info\sType=#VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO
  info\imageType=#VK_IMAGE_TYPE_2D : info\format=#VK_FORMAT_B8G8R8A8_UNORM
  info\extent\width=320 : info\extent\height=240 : info\extent\depth=1
  info\mipLevels=1 : info\arrayLayers=1 : info\samples=#VK_SAMPLE_COUNT_1_BIT
  info\tiling=#VK_IMAGE_TILING_LINEAR
  info\usage=#VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | #VK_IMAGE_USAGE_TRANSFER_SRC_BIT
  info\sharingMode=#VK_SHARING_MODE_EXCLUSIVE : info\initialLayout=#VK_IMAGE_LAYOUT_UNDEFINED
  rc=vkCreateImage(dev,@info,0,@image)
  CnvCheck(rc,0)
  If CnvFailure<>0 : Goto CnvCleanup : EndIf
  vkGetImageMemoryRequirements(dev,image,@req)
  alloc\sType=#VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO : alloc\allocationSize=req\size
  rc=vkAllocateMemory(dev,@alloc,0,@memory)
  CnvCheck(rc,0)
  CnvCheck(vkBindImageMemory(dev,image,memory,0),0)
  If CnvFailure<>0 : Goto CnvCleanup : EndIf
  sourceBase=AnvilVkImageAddress(image) : sourcePitch=AnvilVkImageRowPitch(image)
  vi\sType=#VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO
  vi\image=image : vi\viewType=#VK_IMAGE_VIEW_TYPE_2D : vi\format=#VK_FORMAT_B8G8R8A8_UNORM
  vi\subresourceRange\aspectMask=#VK_IMAGE_ASPECT_COLOR_BIT
  vi\subresourceRange\levelCount=1 : vi\subresourceRange\layerCount=1
  rc=vkCreateImageView(dev,@vi,0,@view)
  CnvCheck(rc,0)
  fi\sType=#VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO
  fi\renderPass=renderPass : fi\attachmentCount=1 : fi\pAttachments=@view
  fi\width=320 : fi\height=240 : fi\layers=1
  rc=vkCreateFramebuffer(dev,@fi,0,@framebuffer)
  CnvCheck(rc,0)
  CnvCheck(NeonVkChromeRebind(framebuffer,320,240,320,240,sourcePitch,0),0)
  CnvCheck(NeonVkCanvasInit(@CnvCanvas,SizeOf(NeonVkCanvas)),0)
  CnvCheck(NeonVkCanvasCreate(@CnvCanvas,0,32,1,@CnvScratch[0],8192),-21341)
  CnvCheck(NeonVkCanvasCreate(@CnvCanvas,64,32,1,@CnvScratch[0],8191),-21341)
  CnvCheck(NeonVkCanvasCreate(@CnvCanvas,64,32,1,@CnvScratch[0],8192),0)
  If CnvFailure<>0 : Goto CnvCleanup : EndIf
  CnvCheck(NeonVkChromeDestroyChecked(),-21202)
  CnvCheck(NeonVkChromeReady(),1)
  CnvCheck(NeonVkCanvasInit(@CnvCanvas,SizeOf(NeonVkCanvas)),-21342)
  CnvCheck(NeonVkCanvasInit(@CnvCanvas+8,SizeOf(NeonVkCanvas)),-21342)
  CnvCheck(NeonVkCanvasMapPoint(@CnvCanvas,160,120,@CnvCanvas),-21341)
  CnvCheck(Bool(CnvCanvas\magic=#NEON_VK_CANVAS_MAGIC),1)
  CnvCheck(NeonVkCanvasDrawPassthrough(@CnvCanvas),-21342)
  CnvCheck(NeonVkCanvasBegin(@CnvCanvas,0),-21341)
  CnvCheck(NeonVkCanvasBegin(@CnvCanvas,@CnvCanvas),-21341)
  CnvCheck(NeonVkChromeImageSpriteLinearId(1,2),-21201)
  CnvCheck(NeonVkCanvasBegin(@CnvCanvas,@CnvClear[0]),0)
  CnvCheck(NeonVkCanvasClose(@CnvCanvas),0)
  CnvCheck(NeonVkChromeImageSpriteAllocatedId(1),0)
  CnvCheck(NeonVkCanvasCreate(@CnvCanvas,64,32,1,@CnvScratch[0],8192),0)
  rotation=0 : logicalW=320 : logicalH=240
  CnvCheck(NeonVkChromeRebind(framebuffer,320,240,320,240,sourcePitch,0),0)
  CnvCheck(NeonVkCanvasBegin(@CnvCanvas,@CnvClear[0]),-21343)
  CnvCheck(NeonVkCanvasClose(@CnvCanvas),-21343)
  CnvCheck(NeonVkCanvasRetarget(@CnvCanvas),0)
  CnvCheck(NeonVkChromeAsync(0),0)
  CnvCheck(NeonVkCanvasBegin(@CnvCanvas,@CnvClear[0]),0)
  CnvCheck(NeonVkChromeBox(0,0,32,32,$FFFF0000),0)
  CnvCheck(NeonVkChromeBox(32,0,32,32,$FF00FF00),0)
  CnvCheck(NeonVkCanvasEnd(@CnvCanvas),0)
  CnvCheck(NeonVkChromeFramePending(),0)
  CnvCheck(NeonVkChromeTargetSnapshot(@target,SizeOf(NeonVkTargetInfo)),0)
  CnvCheck(Bool(target\framebuffer=framebuffer),1)
  CnvCheck(target\logicalW,320)
  CnvCheck(target\logicalH,240)
  CnvCheck(target\rotation,0)
  CnvCheck(NeonVkCanvasMapPoint(@CnvCanvas,160,120,@point),1)
  CnvCheck(point\xQ16,2097152)
  CnvCheck(point\yQ16,1048576)
  CnvCheck(NeonVkChromeBegin(@CnvClear[0]),0)
  CnvCheck(NeonVkCanvasDrawPassthrough(@CnvCanvas),0)
  CnvCheck(NeonVkChromeImageSpriteLinearId(1,0),-21202)
  CnvCheck(NeonVkCanvasClose(@CnvCanvas),-21342)
  CnvCheck(NeonVkChromeEnd(),0)
  CnvCheck(NeonVkChromeFramePending(),0)
  CnvCheck(NeonVkCanvasClose(@CnvCanvas),-21342)
  CnvCheck(NeonVkChromeFinish(),0)
  CnvCheck(NeonVkChromePresentConsume(),1)
  dest=$E2400000+0*307200
  For y=0 To 239
    For x=0 To 319
      PokeL(dest+(y*320+x)*4,PeekL(sourceBase+y*sourcePitch+x*4))
    Next
  Next
  rotation=90 : logicalW=240 : logicalH=320
  CnvCheck(NeonVkChromeRebind(framebuffer,240,320,320,240,sourcePitch,90),0)
  CnvCheck(NeonVkCanvasBegin(@CnvCanvas,@CnvClear[0]),-21343)
  CnvCheck(NeonVkCanvasClose(@CnvCanvas),-21343)
  CnvCheck(NeonVkCanvasRetarget(@CnvCanvas),0)
  CnvCheck(NeonVkChromeAsync(0),0)
  CnvCheck(NeonVkCanvasBegin(@CnvCanvas,@CnvClear[0]),0)
  CnvCheck(NeonVkChromeBox(0,0,32,32,$FFFF0000),0)
  CnvCheck(NeonVkChromeBox(32,0,32,32,$FF00FF00),0)
  CnvCheck(NeonVkCanvasEnd(@CnvCanvas),0)
  CnvCheck(NeonVkChromeFramePending(),0)
  CnvCheck(NeonVkChromeTargetSnapshot(@target,SizeOf(NeonVkTargetInfo)),0)
  CnvCheck(Bool(target\framebuffer=framebuffer),1)
  CnvCheck(target\logicalW,240)
  CnvCheck(target\logicalH,320)
  CnvCheck(target\rotation,90)
  CnvCheck(NeonVkCanvasMapPoint(@CnvCanvas,120,160,@point),1)
  CnvCheck(point\xQ16,2097152)
  CnvCheck(point\yQ16,1048576)
  CnvCheck(NeonVkChromeBegin(@CnvClear[0]),0)
  CnvCheck(NeonVkCanvasDrawPassthrough(@CnvCanvas),0)
  CnvCheck(NeonVkChromeImageSpriteLinearId(1,0),-21202)
  CnvCheck(NeonVkCanvasClose(@CnvCanvas),-21342)
  CnvCheck(NeonVkChromeEnd(),0)
  CnvCheck(NeonVkChromeFramePending(),0)
  CnvCheck(NeonVkCanvasClose(@CnvCanvas),-21342)
  CnvCheck(NeonVkChromeFinish(),0)
  CnvCheck(NeonVkChromePresentConsume(),1)
  dest=$E2400000+1*307200
  For y=0 To 239
    For x=0 To 319
      PokeL(dest+(y*320+x)*4,PeekL(sourceBase+y*sourcePitch+x*4))
    Next
  Next
  rotation=180 : logicalW=320 : logicalH=240
  CnvCheck(NeonVkChromeRebind(framebuffer,320,240,320,240,sourcePitch,180),0)
  CnvCheck(NeonVkCanvasBegin(@CnvCanvas,@CnvClear[0]),-21343)
  CnvCheck(NeonVkCanvasClose(@CnvCanvas),-21343)
  CnvCheck(NeonVkCanvasRetarget(@CnvCanvas),0)
  CnvCheck(NeonVkChromeAsync(1),0)
  CnvCheck(NeonVkCanvasBegin(@CnvCanvas,@CnvClear[0]),0)
  CnvCheck(NeonVkChromeBox(0,0,32,32,$FFFF0000),0)
  CnvCheck(NeonVkChromeBox(32,0,32,32,$FF00FF00),0)
  CnvCheck(NeonVkCanvasEnd(@CnvCanvas),0)
  CnvCheck(NeonVkChromeFramePending(),0)
  CnvCheck(NeonVkChromeTargetSnapshot(@target,SizeOf(NeonVkTargetInfo)),0)
  CnvCheck(Bool(target\framebuffer=framebuffer),1)
  CnvCheck(target\logicalW,320)
  CnvCheck(target\logicalH,240)
  CnvCheck(target\rotation,180)
  CnvCheck(NeonVkCanvasMapPoint(@CnvCanvas,160,120,@point),1)
  CnvCheck(point\xQ16,2097152)
  CnvCheck(point\yQ16,1048576)
  CnvCheck(NeonVkChromeBegin(@CnvClear[0]),0)
  CnvCheck(NeonVkCanvasDrawPassthrough(@CnvCanvas),0)
  CnvCheck(NeonVkChromeImageSpriteLinearId(1,0),-21202)
  CnvCheck(NeonVkCanvasClose(@CnvCanvas),-21342)
  CnvCheck(NeonVkChromeEnd(),0)
  CnvCheck(NeonVkChromeFramePending(),1)
  CnvCheck(NeonVkCanvasClose(@CnvCanvas),-21342)
  CnvCheck(NeonVkChromeFinish(),0)
  CnvCheck(NeonVkChromePresentConsume(),1)
  dest=$E2400000+2*307200
  For y=0 To 239
    For x=0 To 319
      PokeL(dest+(y*320+x)*4,PeekL(sourceBase+y*sourcePitch+x*4))
    Next
  Next
  rotation=270 : logicalW=240 : logicalH=320
  CnvCheck(NeonVkChromeRebind(framebuffer,240,320,320,240,sourcePitch,270),0)
  CnvCheck(NeonVkCanvasBegin(@CnvCanvas,@CnvClear[0]),-21343)
  CnvCheck(NeonVkCanvasClose(@CnvCanvas),-21343)
  CnvCheck(NeonVkCanvasRetarget(@CnvCanvas),0)
  CnvCheck(NeonVkChromeAsync(1),0)
  CnvCheck(NeonVkCanvasBegin(@CnvCanvas,@CnvClear[0]),0)
  CnvCheck(NeonVkChromeBox(0,0,32,32,$FFFF0000),0)
  CnvCheck(NeonVkChromeBox(32,0,32,32,$FF00FF00),0)
  CnvCheck(NeonVkCanvasEnd(@CnvCanvas),0)
  CnvCheck(NeonVkChromeFramePending(),0)
  CnvCheck(NeonVkChromeTargetSnapshot(@target,SizeOf(NeonVkTargetInfo)),0)
  CnvCheck(Bool(target\framebuffer=framebuffer),1)
  CnvCheck(target\logicalW,240)
  CnvCheck(target\logicalH,320)
  CnvCheck(target\rotation,270)
  CnvCheck(NeonVkCanvasMapPoint(@CnvCanvas,120,160,@point),1)
  CnvCheck(point\xQ16,2097152)
  CnvCheck(point\yQ16,1048576)
  CnvCheck(NeonVkChromeBegin(@CnvClear[0]),0)
  CnvCheck(NeonVkCanvasDrawPassthrough(@CnvCanvas),0)
  CnvCheck(NeonVkChromeImageSpriteLinearId(1,0),-21202)
  CnvCheck(NeonVkCanvasClose(@CnvCanvas),-21342)
  CnvCheck(NeonVkChromeEnd(),0)
  CnvCheck(NeonVkChromeFramePending(),1)
  CnvCheck(NeonVkCanvasClose(@CnvCanvas),-21342)
  CnvCheck(NeonVkChromeFinish(),0)
  CnvCheck(NeonVkChromePresentConsume(),1)
  dest=$E2400000+3*307200
  For y=0 To 239
    For x=0 To 319
      PokeL(dest+(y*320+x)*4,PeekL(sourceBase+y*sourcePitch+x*4))
    Next
  Next
  CnvCheck(NeonVkCanvasClose(@CnvCanvas),0)
  CnvCheck(NeonVkCanvasClose(@CnvCanvas),0)
  CnvCheck(NeonVkChromeImageSpriteAllocatedId(1),0)
  CnvCheck(NeonVkChromeExternalProducerAttach(),0)
  CnvCheck(NeonVkChromeExternalProducerDetach(),0)
  CnvCleanup:
  If CnvCanvas\phase<>#NEON_VK_CANVAS_CLOSED : NeonVkCanvasClose(@CnvCanvas) : EndIf
  NeonVkChromeAsync(0)
  NeonVkChromeRebind(originalFramebuffer,#NVWA_WIDTH,#NVWA_HEIGHT,#NVWA_WIDTH,#NVWA_HEIGHT,pitch,0)
  vkDeviceWaitIdle(dev)
  If framebuffer<>0 : vkDestroyFramebuffer(dev,framebuffer,0) : EndIf
  If view<>0 : vkDestroyImageView(dev,view,0) : EndIf
  If image<>0 : vkDestroyImage(dev,image,0) : EndIf
  If memory<>0 : vkFreeMemory(dev,memory,0) : EndIf
  ProcedureReturn CnvFailure
EndProcedure

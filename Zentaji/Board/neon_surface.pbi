; Zentaji resident Neon surface owner. Include after the public Vulkan/native
; presentation provider, ordinary Neon lifecycle and canvas/font ports.
; Memory, font/bitmap data and the prompt timer are admitted by the caller first.
; A failed acquisition or uncertain retirement pins the partial state until reset.
; 0 fresh, 1 acquiring, 2 ready, 3 quarantined, 4 cleanly stopped (no restart).
Global znsState.i,znsError.i,znsWidth.i,znsHeight.i
Global znsInst.i,znsPhys.i,znsDev.i,znsQueue.i,znsPool.i
Global znsImage.i,znsMemory.i,znsView.i,znsPass.i,znsFramebuffer.i
Global znsImageBase.i,znsImagePitch.i
Procedure.i znsFail(code.i)
 znsError=code : znsState=3 : ProcedureReturn 0
EndProcedure
Procedure.i znsObjectsCreate()
  Define rc.i, count.i, mapped.i
  Define priority.l
  Define ici.VkInstanceCreateInfo
  Define qci.VkDeviceQueueCreateInfo
  Define dci.VkDeviceCreateInfo
  Define pci.VkCommandPoolCreateInfo
  Define imageInfo.VkImageCreateInfo
  Define req.VkMemoryRequirements
  Define alloc.VkMemoryAllocateInfo
  Define viewInfo.VkImageViewCreateInfo
  Define attachment.VkAttachmentDescription
  Define attachmentRef.VkAttachmentReference
  Define subpass.VkSubpassDescription
  Define passInfo.VkRenderPassCreateInfo
  Define frameInfo.VkFramebufferCreateInfo

  ici\sType = #VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO
  rc = vkCreateInstance(@ici, 0, @znsInst)
  If rc <> #VK_SUCCESS : ProcedureReturn 0 : EndIf
  count = 1
  rc = vkEnumeratePhysicalDevices(znsInst, @count, @znsPhys)
  If rc <> #VK_SUCCESS Or count <> 1 Or znsPhys = 0 : ProcedureReturn 0 : EndIf
  priority = 0
  qci\sType = #VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO
  qci\queueCount = 1 : qci\pQueuePriorities = @priority
  dci\sType = #VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO
  dci\queueCreateInfoCount = 1 : dci\pQueueCreateInfos = @qci
  rc = vkCreateDevice(znsPhys, @dci, 0, @znsDev)
  If rc <> #VK_SUCCESS : ProcedureReturn 0 : EndIf
  vkGetDeviceQueue(znsDev, 0, 0, @znsQueue)
  pci\sType = #VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO
  pci\flags = #VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT
  rc = vkCreateCommandPool(znsDev, @pci, 0, @znsPool)
  If rc <> #VK_SUCCESS : ProcedureReturn 0 : EndIf

  imageInfo\sType = #VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO
  imageInfo\imageType = #VK_IMAGE_TYPE_2D
  imageInfo\format = #VK_FORMAT_B8G8R8A8_UNORM
  imageInfo\extent\width = znsWidth : imageInfo\extent\height = znsHeight : imageInfo\extent\depth = 1
  imageInfo\mipLevels = 1 : imageInfo\arrayLayers = 1
  imageInfo\samples = #VK_SAMPLE_COUNT_1_BIT
  imageInfo\tiling = #VK_IMAGE_TILING_LINEAR
  imageInfo\usage = #VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | #VK_IMAGE_USAGE_TRANSFER_SRC_BIT
  imageInfo\sharingMode = #VK_SHARING_MODE_EXCLUSIVE
  imageInfo\initialLayout = #VK_IMAGE_LAYOUT_UNDEFINED
  rc = vkCreateImage(znsDev, @imageInfo, 0, @znsImage)
  If rc <> #VK_SUCCESS : ProcedureReturn 0 : EndIf
  vkGetImageMemoryRequirements(znsDev, znsImage, @req)
  alloc\sType = #VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO
  alloc\allocationSize = req\size : alloc\memoryTypeIndex = 0
  rc = vkAllocateMemory(znsDev, @alloc, 0, @znsMemory)
  If rc <> #VK_SUCCESS : ProcedureReturn 0 : EndIf
  rc = vkBindImageMemory(znsDev, znsImage, znsMemory, 0)
  If rc <> #VK_SUCCESS : ProcedureReturn 0 : EndIf
  znsImageBase = AnvilVkImageAddress(znsImage)
  znsImagePitch = AnvilVkImageRowPitch(znsImage)
  If znsImageBase = 0 Or znsImagePitch < (znsWidth * 4) : ProcedureReturn 0 : EndIf
  mapped = 0
  rc = vkMapMemory(znsDev, znsMemory, 0, #VK_WHOLE_SIZE, 0, @mapped)
  If rc <> #VK_SUCCESS Or mapped <> znsImageBase : ProcedureReturn 0 : EndIf
  vkUnmapMemory(znsDev, znsMemory)

  viewInfo\sType = #VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO
  viewInfo\image = znsImage : viewInfo\viewType = #VK_IMAGE_VIEW_TYPE_2D
  viewInfo\format = #VK_FORMAT_B8G8R8A8_UNORM
  viewInfo\subresourceRange\aspectMask = #VK_IMAGE_ASPECT_COLOR_BIT
  viewInfo\subresourceRange\levelCount = 1 : viewInfo\subresourceRange\layerCount = 1
  rc = vkCreateImageView(znsDev, @viewInfo, 0, @znsView)
  If rc <> #VK_SUCCESS : ProcedureReturn 0 : EndIf

  attachment\format = #VK_FORMAT_B8G8R8A8_UNORM
  attachment\samples = #VK_SAMPLE_COUNT_1_BIT
  attachment\loadOp = #VK_ATTACHMENT_LOAD_OP_CLEAR
  attachment\storeOp = #VK_ATTACHMENT_STORE_OP_STORE
  attachment\stencilLoadOp = #VK_ATTACHMENT_LOAD_OP_DONT_CARE
  attachment\stencilStoreOp = #VK_ATTACHMENT_STORE_OP_DONT_CARE
  attachment\initialLayout = #VK_IMAGE_LAYOUT_UNDEFINED
  attachment\finalLayout = #VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL
  attachmentRef\attachment = 0 : attachmentRef\layout = #VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL
  subpass\pipelineBindPoint = #VK_PIPELINE_BIND_POINT_GRAPHICS
  subpass\colorAttachmentCount = 1 : subpass\pColorAttachments = @attachmentRef
  passInfo\sType = #VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO
  passInfo\attachmentCount = 1 : passInfo\pAttachments = @attachment
  passInfo\subpassCount = 1 : passInfo\pSubpasses = @subpass
  rc = vkCreateRenderPass(znsDev, @passInfo, 0, @znsPass)
  If rc <> #VK_SUCCESS : ProcedureReturn 0 : EndIf
  frameInfo\sType = #VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO
  frameInfo\renderPass = znsPass : frameInfo\attachmentCount = 1
  frameInfo\pAttachments = @znsView : frameInfo\width = znsWidth
  frameInfo\height = znsHeight : frameInfo\layers = 1
  rc = vkCreateFramebuffer(znsDev, @frameInfo, 0, @znsFramebuffer)
  If rc <> #VK_SUCCESS : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i ZentajiNeonSurfaceStartCapacities(maxQuads.i,maxVertexQuads.i)
 Protected cfg.NeonVkLifecycleConfig
 If znsState<>0 Or maxQuads<1 Or maxQuads>#NEON_VK_CHROME_MAX_QUADS Or Neon_Ready()<>0 Or NeonVkLifecycleConfigured()<>0 : ProcedureReturn 0 : EndIf
 If maxVertexQuads<0 Or maxVertexQuads>#NEON_VK_CHROME_MAX_VERTEX_QUADS : ProcedureReturn 0 : EndIf
 If zenMemoryGraphicsBase=0 Or HwPromptIdleReady()=0 Or ZenCpuCoreId()<>0 Or ZenCpuStatus()<>0 : ProcedureReturn 0 : EndIf
 If PeekQ($FFFF0000001A0040)<>0 : ProcedureReturn 0 : EndIf
 znsWidth=PeekQ(#ZEN_GFX_DISPLAY+$50) : znsHeight=PeekQ(#ZEN_GFX_DISPLAY+$58)
 If znsWidth<1 Or znsWidth>8192 Or znsHeight<1 Or znsHeight>8192 : ProcedureReturn 0 : EndIf
 znsState=1
 If AnvilVkZentajiDisplayWindow()<>#VK_SUCCESS : ProcedureReturn znsFail(1) : EndIf
 If znsObjectsCreate()<>1 : ProcedureReturn znsFail(2) : EndIf
 cfg\physicalDevice=znsPhys : cfg\device=znsDev : cfg\queue=znsQueue : cfg\commandPool=znsPool
 cfg\renderPass=znsPass : cfg\framebuffer=znsFramebuffer
 cfg\width=znsWidth : cfg\height=znsHeight : cfg\maxQuads=maxQuads
 If NeonVkLifecycleConfigureCapacities(@cfg,maxVertexQuads)<>#NEON_OK : ProcedureReturn znsFail(3) : EndIf
 If NeonVkPortCanvas(znsWidth,znsHeight,znsWidth,znsHeight)<>#NEON_OK : ProcedureReturn znsFail(4) : EndIf
 If NeonInit()<>#NEON_OK : ProcedureReturn znsFail(5) : EndIf
 znsState=2 : ProcedureReturn 1
EndProcedure

Procedure.i ZentajiNeonSurfaceStart(maxQuads.i)
 ProcedureReturn ZentajiNeonSurfaceStartCapacities(maxQuads,0)
EndProcedure

Procedure.i ZentajiNeonSurfacePresent()
 Protected token.q
 If znsState<>2 Or nvcInFrame<>0 Or NeonVkChromePresentValidate()<>1 : ProcedureReturn 0 : EndIf
 If ZentajiGraphicsDisplayOwned()<>1 : ProcedureReturn znsFail(6) : EndIf
 token=AnvilVkZentajiPresentBegin(znsImage)
 If token<1 : ProcedureReturn znsFail(7) : EndIf
 If AnvilVkZentajiPresentCommit(token,250000)<>1 : ProcedureReturn znsFail(8) : EndIf
 If NeonVkChromePresentConsume()<>1 : ProcedureReturn znsFail(9) : EndIf
 ProcedureReturn 1
EndProcedure

Procedure.i ZentajiNeonSurfaceStop()
 Protected faults.i
 If znsState<>2 Or nvcInFrame<>0 Or NeonVkChromePresentPending()<>0 : ProcedureReturn 0 : EndIf
 If ZentajiGraphicsDisplayOwned()<>1 : ProcedureReturn znsFail(10) : EndIf
 If vkDeviceWaitIdle(znsDev)<>#VK_SUCCESS : ProcedureReturn znsFail(11) : EndIf
 If ZentajiGraphicsDisplayRelease()<>1 : ProcedureReturn znsFail(12) : EndIf
 If NeonShutdown()<>#NEON_OK : ProcedureReturn znsFail(13) : EndIf
 faults=AnvilVkFaultCount()
 vkDestroyFramebuffer(znsDev,znsFramebuffer,0)
 vkDestroyRenderPass(znsDev,znsPass,0)
 vkDestroyImageView(znsDev,znsView,0)
 vkDestroyImage(znsDev,znsImage,0)
 vkFreeMemory(znsDev,znsMemory,0)
 vkDestroyCommandPool(znsDev,znsPool,0)
 vkDestroyDevice(znsDev,0) : vkDestroyInstance(znsInst,0)
 If AnvilVkFaultCount()<>faults : ProcedureReturn znsFail(14) : EndIf
 znsState=4 : ProcedureReturn 1
EndProcedure

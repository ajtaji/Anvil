; SPDX-License-Identifier: MIT
; Public Vulkan LOAD: null clear pointer, actual layout claim and full pixels.
Procedure NalPublicEmptyCase(*c.NeonVkCanvas)
  Protected att.VkAttachmentDescription,ref.VkAttachmentReference,sub.VkSubpassDescription
  Protected pi.VkRenderPassCreateInfo,fi.VkFramebufferCreateInfo,ai.VkCommandBufferAllocateInfo
  Protected bi.VkCommandBufferBeginInfo,ri.VkRenderPassBeginInfo,si.VkSubmitInfo
  Protected pass.i,fb.i,cmd.i,mapped.i,x.i,y.i,rc.i,dev.i
  Protected Dim clear.l[4]
  dev=*c\target\device
  ; Establish a defined TRANSFER_SRC layout through the existing CLEAR pass.
  NalCheck(300,NeonVkCanvasBegin(*c,@clear[0]),0)
  If NalFailure<>0 : ProcedureReturn : EndIf
  NalCheck(301,NeonVkCanvasEnd(*c),0)
  If NalFailure<>0 : ProcedureReturn : EndIf
  NalCheck(302,vkMapMemory(dev,*c\memory,0,#VK_WHOLE_SIZE,0,@mapped),0)
  If NalFailure<>0 : ProcedureReturn : EndIf
  For y=0 To *c\height-1
    For x=0 To *c\width-1 : PokeL(mapped+y* *c\pitch+x*4,NalPattern(x,y)) : Next
  Next
  vkUnmapMemory(dev,*c\memory)
  att\format=#VK_FORMAT_B8G8R8A8_UNORM : att\samples=#VK_SAMPLE_COUNT_1_BIT
  att\loadOp=#VK_ATTACHMENT_LOAD_OP_LOAD : att\storeOp=#VK_ATTACHMENT_STORE_OP_STORE
  att\stencilLoadOp=#VK_ATTACHMENT_LOAD_OP_DONT_CARE : att\stencilStoreOp=#VK_ATTACHMENT_STORE_OP_DONT_CARE
  att\finalLayout=#VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL
  ref\layout=#VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL
  sub\pipelineBindPoint=#VK_PIPELINE_BIND_POINT_GRAPHICS
  sub\colorAttachmentCount=1 : sub\pColorAttachments=@ref
  pi\sType=#VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO
  pi\attachmentCount=1 : pi\pAttachments=@att : pi\subpassCount=1 : pi\pSubpasses=@sub
  NalCheck(303,vkCreateRenderPass(dev,@pi,0,@pass),#ANVIL_VK_ERR_UNSUPPORTED)
  NalCheck(304,pass,0)
  att\initialLayout=#VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL
  NalCheck(305,vkCreateRenderPass(dev,@pi,0,@pass),0)
  If NalFailure<>0 : Goto NalPublicDone : EndIf
  fi\sType=#VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO : fi\renderPass=pass
  fi\attachmentCount=1 : fi\pAttachments=@*c\view
  fi\width=*c\width : fi\height=*c\height : fi\layers=1
  NalCheck(306,vkCreateFramebuffer(dev,@fi,0,@fb),0)
  If NalFailure<>0 : Goto NalPublicDone : EndIf
  ai\sType=#VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO : ai\commandPool=nvcCommandPool
  ai\level=#VK_COMMAND_BUFFER_LEVEL_PRIMARY : ai\commandBufferCount=1
  NalCheck(307,vkAllocateCommandBuffers(dev,@ai,@cmd),0)
  If NalFailure<>0 : Goto NalPublicDone : EndIf
  bi\sType=#VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO
  NalCheck(308,vkBeginCommandBuffer(cmd,@bi),0)
  ri\sType=#VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO : ri\renderPass=pass : ri\framebuffer=fb
  ri\renderArea\extent\width=*c\width : ri\renderArea\extent\height=*c\height
  ; LOAD ignores clear values, including the valid null pointer/count zero.
  vkCmdBeginRenderPass(cmd,@ri,#VK_SUBPASS_CONTENTS_INLINE)
  vkCmdEndRenderPass(cmd)
  NalCheck(309,vkEndCommandBuffer(cmd),0)
  If NalFailure<>0 : Goto NalPublicDone : EndIf
  si\sType=#VK_STRUCTURE_TYPE_SUBMIT_INFO : si\commandBufferCount=1 : si\pCommandBuffers=@cmd
  NalCheck(310,vkQueueSubmit(nvcQueue,1,@si,0),0)
  NalCheck(311,vkQueueWaitIdle(nvcQueue),0)
  If NalFailure<>0 : Goto NalPublicDone : EndIf
  NalPixels(*c,312,0)
  NalPublicDone:
  If cmd<>0 : vkFreeCommandBuffers(dev,nvcCommandPool,1,@cmd) : EndIf
  If fb<>0 : vkDestroyFramebuffer(dev,fb,0) : EndIf
  If pass<>0 : vkDestroyRenderPass(dev,pass,0) : EndIf
EndProcedure


Procedure NalPublicPixels(*c.NeonVkCanvas,id.i,kind.i)
  Protected mapped.i,x.i,y.i,wanted.i,bad.i,rc.i
  rc=vkMapMemory(*c\target\device,*c\memory,0,#VK_WHOLE_SIZE,0,@mapped)
  NalCheck(id,rc,0)
  If rc<>0 : ProcedureReturn : EndIf
  For y=0 To *c\height-1
    For x=0 To *c\width-1
      wanted=NalPattern(x,y)
      If kind=1 And x>=10 And x<27 And y>=9 And y<22 : wanted=$FF00FF00 : EndIf
      If kind=2 : wanted=$FF00FF00 : EndIf
      If kind<>0 And x>=20 And x<32 And y>=15 And y<25 : wanted=$FF0000FF : EndIf
      If PeekN(mapped+y* *c\pitch+x*4)<>wanted : bad=bad+1 : EndIf
    Next
  Next
  vkUnmapMemory(*c\target\device,*c\memory)
  NalCheck(id+1,bad,0)
EndProcedure

Procedure NalPublicOrderedCase(*c.NeonVkCanvas)
  Protected att.VkAttachmentDescription,ref.VkAttachmentReference,sub.VkSubpassDescription
  Protected pi.VkRenderPassCreateInfo,fi.VkFramebufferCreateInfo,ai.VkCommandBufferAllocateInfo
  Protected bi.VkCommandBufferBeginInfo,ri.VkRenderPassBeginInfo,si.VkSubmitInfo
  Protected ca.VkClearAttachment,rect.VkClearRect
  Protected pass.i,fb.i,cmd.i,mapped.i,x.i,y.i,dev.i
  Protected Dim clear.l[4]
  dev=*c\target\device
  NalCheck(400,NeonVkCanvasResizeBlank(*c,194,128),0)
  If NalFailure<>0 : ProcedureReturn : EndIf
  NalCheck(401,NeonVkCanvasBegin(*c,@clear[0]),0)
  If NalFailure<>0 : ProcedureReturn : EndIf
  NalCheck(402,NeonVkCanvasEnd(*c),0)
  If NalFailure<>0 : ProcedureReturn : EndIf
  NalCheck(403,vkMapMemory(dev,*c\memory,0,#VK_WHOLE_SIZE,0,@mapped),0)
  If NalFailure<>0 : ProcedureReturn : EndIf
  For y=0 To *c\height-1
    For x=0 To *c\width-1 : PokeL(mapped+y* *c\pitch+x*4,NalPattern(x,y)) : Next
  Next
  vkUnmapMemory(dev,*c\memory)
  att\format=#VK_FORMAT_B8G8R8A8_UNORM : att\samples=#VK_SAMPLE_COUNT_1_BIT
  att\loadOp=#VK_ATTACHMENT_LOAD_OP_LOAD : att\storeOp=#VK_ATTACHMENT_STORE_OP_STORE
  att\stencilLoadOp=#VK_ATTACHMENT_LOAD_OP_DONT_CARE : att\stencilStoreOp=#VK_ATTACHMENT_STORE_OP_DONT_CARE
  att\initialLayout=#VK_IMAGE_LAYOUT_GENERAL : att\finalLayout=#VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL
  ref\layout=#VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL
  sub\pipelineBindPoint=#VK_PIPELINE_BIND_POINT_GRAPHICS : sub\colorAttachmentCount=1 : sub\pColorAttachments=@ref
  pi\sType=#VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO : pi\attachmentCount=1 : pi\pAttachments=@att
  pi\subpassCount=1 : pi\pSubpasses=@sub
  NalCheck(404,vkCreateRenderPass(dev,@pi,0,@pass),0)
  If NalFailure<>0 : Goto NalOrderedDone : EndIf
  fi\sType=#VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO : fi\renderPass=pass
  fi\attachmentCount=1 : fi\pAttachments=@*c\view : fi\width=*c\width : fi\height=*c\height : fi\layers=1
  NalCheck(405,vkCreateFramebuffer(dev,@fi,0,@fb),0)
  ai\sType=#VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO : ai\commandPool=nvcCommandPool
  ai\level=#VK_COMMAND_BUFFER_LEVEL_PRIMARY : ai\commandBufferCount=1
  NalCheck(406,vkAllocateCommandBuffers(dev,@ai,@cmd),0)
  If NalFailure<>0 : Goto NalOrderedDone : EndIf
  bi\sType=#VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO
  ri\sType=#VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO : ri\renderPass=pass : ri\framebuffer=fb
  ri\renderArea\extent\width=*c\width : ri\renderArea\extent\height=*c\height
  si\sType=#VK_STRUCTURE_TYPE_SUBMIT_INFO : si\commandBufferCount=1 : si\pCommandBuffers=@cmd
  NalCheck(407,vkBeginCommandBuffer(cmd,@bi),0)
  vkCmdBeginRenderPass(cmd,@ri,#VK_SUBPASS_CONTENTS_INLINE) : vkCmdEndRenderPass(cmd)
  NalCheck(408,vkEndCommandBuffer(cmd),0)
  NalCheck(409,vkQueueSubmit(nvcQueue,1,@si,0),#ANVIL_VK_ERR_STATE)
  NalPublicPixels(*c,410,0)
  NalCheck(412,vkResetCommandBuffer(cmd,0),0)
  If NalFailure<>0 : Goto NalOrderedDone : EndIf
  vkDestroyFramebuffer(dev,fb,0) : fb=0 : vkDestroyRenderPass(dev,pass,0) : pass=0
  att\initialLayout=#VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL
  NalCheck(413,vkCreateRenderPass(dev,@pi,0,@pass),0)
  fi\renderPass=pass
  NalCheck(414,vkCreateFramebuffer(dev,@fi,0,@fb),0)
  If NalFailure<>0 : Goto NalOrderedDone : EndIf
  ri\renderPass=pass : ri\framebuffer=fb
  NalCheck(415,vkBeginCommandBuffer(cmd,@bi),0)
  vkCmdBeginRenderPass(cmd,@ri,#VK_SUBPASS_CONTENTS_INLINE)
  ca\aspectMask=#VK_IMAGE_ASPECT_COLOR_BIT
  PokeL(@ca+12,$3F800000) : PokeL(@ca+20,$3F800000)
  rect\layerCount=1 : rect\rect\offset\x=10 : rect\rect\offset\y=9
  rect\rect\extent\width=17 : rect\rect\extent\height=13
  vkCmdClearAttachments(cmd,1,@ca,1,@rect)
  PokeL(@ca+12,0) : PokeL(@ca+16,$3F800000)
  rect\rect\offset\x=20 : rect\rect\offset\y=15 : rect\rect\extent\width=12 : rect\rect\extent\height=10
  vkCmdClearAttachments(cmd,1,@ca,1,@rect)
  vkCmdEndRenderPass(cmd)
  NalCheck(416,vkEndCommandBuffer(cmd),0)
  If NalFailure<>0 : Goto NalOrderedDone : EndIf
  NalCheck(417,vkQueueSubmit(nvcQueue,1,@si,0),0)
  NalCheck(418,vkQueueWaitIdle(nvcQueue),0)
  NalPublicPixels(*c,419,1)
  If NalFailure<>0 : Goto NalOrderedDone : EndIf
  NalCheck(421,vkResetCommandBuffer(cmd,0),0)
  NalCheck(422,vkBeginCommandBuffer(cmd,@bi),0)
  vkCmdBeginRenderPass(cmd,@ri,#VK_SUBPASS_CONTENTS_INLINE)
  PokeL(@ca+12,$3F800000) : PokeL(@ca+16,0)
  rect\rect\offset\x=0 : rect\rect\offset\y=0 : rect\rect\extent\width=*c\width : rect\rect\extent\height=*c\height
  vkCmdClearAttachments(cmd,1,@ca,1,@rect)
  PokeL(@ca+12,0) : PokeL(@ca+16,$3F800000)
  rect\rect\offset\x=20 : rect\rect\offset\y=15 : rect\rect\extent\width=12 : rect\rect\extent\height=10
  vkCmdClearAttachments(cmd,1,@ca,1,@rect)
  vkCmdEndRenderPass(cmd)
  NalCheck(423,vkEndCommandBuffer(cmd),0)
  If NalFailure<>0 : Goto NalOrderedDone : EndIf
  NalCheck(424,vkQueueSubmit(nvcQueue,1,@si,0),0)
  NalCheck(425,vkQueueWaitIdle(nvcQueue),0)
  NalPublicPixels(*c,426,2)
  If NalFailure<>0 : Goto NalOrderedDone : EndIf
  NalCheck(428,vkResetCommandBuffer(cmd,0),0)
  NalCheck(429,vkBeginCommandBuffer(cmd,@bi),0)
  vkCmdBeginRenderPass(cmd,@ri,#VK_SUBPASS_CONTENTS_INLINE) : vkCmdEndRenderPass(cmd)
  NalCheck(430,vkEndCommandBuffer(cmd),0)
  NalCheck(431,vkQueueSubmit(nvcQueue,1,@si,0),0)
  NalCheck(432,vkQueueWaitIdle(nvcQueue),0)
  NalPublicPixels(*c,433,2)
  If NalFailure<>0 : Goto NalOrderedDone : EndIf
  NalCheck(435,vkResetCommandBuffer(cmd,0),0)
  NalCheck(436,vkBeginCommandBuffer(cmd,@bi),0)
  vkCmdBeginRenderPass(cmd,@ri,#VK_SUBPASS_CONTENTS_INLINE) : vkCmdEndRenderPass(cmd)
  NalCheck(437,vkEndCommandBuffer(cmd),0)
  vkDestroyFramebuffer(dev,fb,0) : fb=0 : vkDestroyRenderPass(dev,pass,0) : pass=0
  NalCheck(438,vkQueueSubmit(nvcQueue,1,@si,0),#ANVIL_VK_ERR_STATE)
  NalPublicPixels(*c,439,2)
  NalCheck(441,AnvilVkSubmissionOutstanding(),0)
  NalOrderedDone:
  If cmd<>0 : vkFreeCommandBuffers(dev,nvcCommandPool,1,@cmd) : EndIf
  If fb<>0 : vkDestroyFramebuffer(dev,fb,0) : EndIf
  If pass<>0 : vkDestroyRenderPass(dev,pass,0) : EndIf
  NalCheck(442,NeonVkCanvasResizeBlank(*c,193,127),0)
EndProcedure

Procedure NalPublicCase(*c.NeonVkCanvas)
  NalPublicEmptyCase(*c)
  If NalFailure=0 : NalPublicOrderedCase(*c) : EndIf
EndProcedure

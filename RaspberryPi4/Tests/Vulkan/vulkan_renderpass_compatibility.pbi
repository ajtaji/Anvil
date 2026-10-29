; SPDX-License-Identifier: MIT
; Actual shader draw through distinct compatible pipeline/framebuffer/pass owners.
Procedure NalCompatibilityPixels(*c.NeonVkCanvas,id.i)
  Protected mapped.i,x.i,y.i,wanted.i,bad.i,rc.i
  rc=vkMapMemory(*c\target\device,*c\memory,0,#VK_WHOLE_SIZE,0,@mapped)
  NalCheck(id,rc,0)
  If rc<>0 : ProcedureReturn : EndIf
  For y=0 To *c\height-1
    For x=0 To *c\width-1
      wanted=NalPattern(x,y)
      If x>=50 And x<66 And y>=40 And y<52 : wanted=$FFFF0000 : EndIf
      If PeekN(mapped+y* *c\pitch+x*4)<>wanted : bad=bad+1 : EndIf
    Next
  Next
  vkUnmapMemory(*c\target\device,*c\memory)
  NalCheck(id+1,bad,0)
EndProcedure

Procedure NalCompatibilityCase(*c.NeonVkCanvas)
  Protected att.VkAttachmentDescription,ref.VkAttachmentReference,sub.VkSubpassDescription
  Protected pi.VkRenderPassCreateInfo,fi.VkFramebufferCreateInfo,ai.VkCommandBufferAllocateInfo
  Protected bi.VkCommandBufferBeginInfo,ri.VkRenderPassBeginInfo,si.VkSubmitInfo
  Protected vp.VkViewport,sc.VkRect2D
  Protected pass.i,creationPass.i,fb.i,cmd.i,mapped.i,x.i,y.i,dev.i,i.i,address.i,buffer.i,set.i
  Protected offset.q
  Protected Dim clear.l[4]
  Protected Dim tint.l[4]
  dev=*c\target\device
  NalCheck(500,NeonVkCanvasResizeBlank(*c,194,128),0)
  If NalFailure<>0 : ProcedureReturn : EndIf
  NalCheck(501,NeonVkCanvasBegin(*c,@clear[0]),0)
  If NalFailure<>0 : ProcedureReturn : EndIf
  NalCheck(502,NeonVkCanvasEnd(*c),0)
  NalCheck(503,vkMapMemory(dev,*c\memory,0,#VK_WHOLE_SIZE,0,@mapped),0)
  If NalFailure<>0 : ProcedureReturn : EndIf
  For y=0 To *c\height-1
    For x=0 To *c\width-1 : PokeL(mapped+y* *c\pitch+x*4,NalPattern(x,y)) : Next
  Next
  vkUnmapMemory(dev,*c\memory)
  att\format=#VK_FORMAT_B8G8R8A8_UNORM : att\samples=#VK_SAMPLE_COUNT_1_BIT
  att\loadOp=#VK_ATTACHMENT_LOAD_OP_LOAD : att\storeOp=#VK_ATTACHMENT_STORE_OP_STORE
  att\stencilLoadOp=#VK_ATTACHMENT_LOAD_OP_DONT_CARE : att\stencilStoreOp=#VK_ATTACHMENT_STORE_OP_DONT_CARE
  att\initialLayout=#VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL : att\finalLayout=#VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL
  ref\layout=#VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL
  sub\pipelineBindPoint=#VK_PIPELINE_BIND_POINT_GRAPHICS : sub\colorAttachmentCount=1 : sub\pColorAttachments=@ref
  pi\sType=#VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO : pi\attachmentCount=1 : pi\pAttachments=@att
  pi\subpassCount=1 : pi\pSubpasses=@sub
  NalCheck(504,vkCreateRenderPass(dev,@pi,0,@creationPass),0)
  fi\sType=#VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO : fi\renderPass=creationPass
  fi\attachmentCount=1 : fi\pAttachments=@*c\view : fi\width=*c\width : fi\height=*c\height : fi\layers=1
  NalCheck(505,vkCreateFramebuffer(dev,@fi,0,@fb),0)
  ref\layout=#VK_IMAGE_LAYOUT_GENERAL
  NalCheck(506,vkCreateRenderPass(dev,@pi,0,@pass),0)
  If NalFailure<>0 : Goto NalCompatDone : EndIf
  ; The framebuffer must not access its creation pass after construction.
  vkDestroyRenderPass(dev,creationPass,0) : creationPass=0
  NalCheck(507,vkMapMemory(dev,nvcVertexMemory,0,#VK_WHOLE_SIZE,0,@mapped),0)
  If NalFailure<>0 : Goto NalCompatDone : EndIf
  For i=0 To 5
    x=$BF800000 : y=$BF800000
    If i=2 Or i=4 Or i=5 : x=$3F800000 : EndIf
    If i=1 Or i=2 Or i=4 : y=$3F800000 : EndIf
    address=mapped+i*24
    PokeL(address,x) : PokeL(address+4,y)
    PokeL(address+8,nvcWhiteU0) : PokeL(address+12,nvcWhiteV0)
    PokeL(address+16,$3F800000) : PokeL(address+20,$3F800000)
  Next
  vkUnmapMemory(dev,nvcVertexMemory)
  ai\sType=#VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO : ai\commandPool=nvcCommandPool
  ai\level=#VK_COMMAND_BUFFER_LEVEL_PRIMARY : ai\commandBufferCount=1
  NalCheck(508,vkAllocateCommandBuffers(dev,@ai,@cmd),0)
  bi\sType=#VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO
  NalCheck(509,vkBeginCommandBuffer(cmd,@bi),0)
  ri\sType=#VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO : ri\renderPass=pass : ri\framebuffer=fb
  ri\renderArea\extent\width=*c\width : ri\renderArea\extent\height=*c\height
  vkCmdBeginRenderPass(cmd,@ri,#VK_SUBPASS_CONTENTS_INLINE)
  PokeL(@vp\width,GraphicsF32IntBits(*c\width)) : PokeL(@vp\height,GraphicsF32IntBits(*c\height))
  PokeL(@vp\maxDepth,$3F800000)
  vkCmdSetViewport(cmd,0,1,@vp)
  sc\offset\x=50 : sc\offset\y=40 : sc\extent\width=16 : sc\extent\height=12
  vkCmdSetScissor(cmd,0,1,@sc)
  vkCmdBindPipeline(cmd,#VK_PIPELINE_BIND_POINT_GRAPHICS,nvcPipeline)
  buffer=nvcVertexBuffer : set=nvcDescriptorSet
  vkCmdBindVertexBuffers(cmd,0,1,@buffer,@offset)
  vkCmdBindDescriptorSets(cmd,#VK_PIPELINE_BIND_POINT_GRAPHICS,nvcPipelineLayout,0,1,@set,0,0)
  tint[0]=$3F800000 : tint[3]=$3F800000
  vkCmdPushConstants(cmd,nvcPipelineLayout,#VK_SHADER_STAGE_FRAGMENT_BIT,0,16,@tint[0])
  vkCmdDraw(cmd,6,1,0,0)
  vkCmdEndRenderPass(cmd)
  NalCheck(510,vkEndCommandBuffer(cmd),0)
  If NalFailure<>0 : Goto NalCompatDone : EndIf
  si\sType=#VK_STRUCTURE_TYPE_SUBMIT_INFO : si\commandBufferCount=1 : si\pCommandBuffers=@cmd
  NalCheck(511,vkQueueSubmit(nvcQueue,1,@si,0),0)
  NalCheck(512,vkQueueWaitIdle(nvcQueue),0)
  NalCompatibilityPixels(*c,513)
  If NalFailure<>0 : Goto NalCompatDone : EndIf
  NalCheck(515,vkResetCommandBuffer(cmd,0),0)
  NalCheck(516,vkBeginCommandBuffer(cmd,@bi),0)
  vkCmdBeginRenderPass(cmd,@ri,#VK_SUBPASS_CONTENTS_INLINE) : vkCmdEndRenderPass(cmd)
  NalCheck(517,vkEndCommandBuffer(cmd),0)
  vkDestroyRenderPass(dev,pass,0) : pass=0
  NalCheck(518,vkCreateRenderPass(dev,@pi,0,@pass),0)
  NalCheck(519,vkQueueSubmit(nvcQueue,1,@si,0),#ANVIL_VK_ERR_STATE)
  NalCheck(520,AnvilVkSubmissionOutstanding(),0)
  NalCompatibilityPixels(*c,521)
  NalCompatDone:
  If cmd<>0 : vkFreeCommandBuffers(dev,nvcCommandPool,1,@cmd) : EndIf
  If fb<>0 : vkDestroyFramebuffer(dev,fb,0) : EndIf
  If pass<>0 : vkDestroyRenderPass(dev,pass,0) : EndIf
  If creationPass<>0 : vkDestroyRenderPass(dev,creationPass,0) : EndIf
  NalCheck(523,NeonVkCanvasResizeBlank(*c,193,127),0)
EndProcedure

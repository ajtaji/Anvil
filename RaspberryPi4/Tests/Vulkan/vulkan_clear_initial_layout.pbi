; SPDX-License-Identifier: MIT
; CLEAR must retain a defined initial-layout claim without preserving pixels.
Procedure NalClearInitialLayoutCase(*c.NeonVkCanvas)
  Protected att.VkAttachmentDescription,ref.VkAttachmentReference,sub.VkSubpassDescription
  Protected pi.VkRenderPassCreateInfo,ai.VkCommandBufferAllocateInfo
  Protected bi.VkCommandBufferBeginInfo,ri.VkRenderPassBeginInfo,si.VkSubmitInfo
  Protected dev.i,pass.i,cmd.i,mapped.i,x.i,y.i,bad.i,i.i,id.i,layout.i
  Protected Dim clear.l[4]
  dev=*c\target\device
  clear[1]=$3F800000 : clear[3]=$3F800000
  att\format=#VK_FORMAT_B8G8R8A8_UNORM : att\samples=#VK_SAMPLE_COUNT_1_BIT
  att\loadOp=#VK_ATTACHMENT_LOAD_OP_CLEAR : att\storeOp=#VK_ATTACHMENT_STORE_OP_STORE
  att\stencilLoadOp=#VK_ATTACHMENT_LOAD_OP_DONT_CARE : att\stencilStoreOp=#VK_ATTACHMENT_STORE_OP_DONT_CARE
  ref\layout=#VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL
  sub\pipelineBindPoint=#VK_PIPELINE_BIND_POINT_GRAPHICS : sub\colorAttachmentCount=1 : sub\pColorAttachments=@ref
  pi\sType=#VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO : pi\attachmentCount=1 : pi\pAttachments=@att
  pi\subpassCount=1 : pi\pSubpasses=@sub
  ai\sType=#VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO : ai\commandPool=nvcCommandPool
  ai\level=#VK_COMMAND_BUFFER_LEVEL_PRIMARY : ai\commandBufferCount=1
  NalCheck(600,vkAllocateCommandBuffers(dev,@ai,@cmd),0)
  If NalFailure<>0 : ProcedureReturn : EndIf
  bi\sType=#VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO
  ri\sType=#VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO : ri\framebuffer=*c\framebuffer
  ri\renderArea\extent\width=*c\width : ri\renderArea\extent\height=*c\height
  ri\clearValueCount=1 : ri\pClearValues=@clear[0]
  si\sType=#VK_STRUCTURE_TYPE_SUBMIT_INFO : si\commandBufferCount=1 : si\pCommandBuffers=@cmd
  For i=0 To 2
    id=610+i*30
    layout=#VK_IMAGE_LAYOUT_GENERAL
    If i=1 : layout=#VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL : EndIf
    If i=2 : layout=#VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL : EndIf
    ; First establish the requested layout using an ordinary discard clear.
    att\initialLayout=#VK_IMAGE_LAYOUT_UNDEFINED : att\finalLayout=layout
    NalCheck(id,vkCreateRenderPass(dev,@pi,0,@pass),0)
    If NalFailure<>0 : Goto NalClearLayoutDone : EndIf
    ri\renderPass=pass
    NalCheck(id+1,vkBeginCommandBuffer(cmd,@bi),0)
    vkCmdBeginRenderPass(cmd,@ri,#VK_SUBPASS_CONTENTS_INLINE) : vkCmdEndRenderPass(cmd)
    NalCheck(id+2,vkEndCommandBuffer(cmd),0)
    NalCheck(id+3,vkQueueSubmit(nvcQueue,1,@si,0),0)
    NalCheck(id+4,vkQueueWaitIdle(nvcQueue),0)
    NalCheck(id+5,vkResetCommandBuffer(cmd,0),0)
    If NalFailure<>0 : Goto NalClearLayoutDone : EndIf
    vkDestroyRenderPass(dev,pass,0) : pass=0
    ; A wrong defined entry layout must refuse before touching the image.
    att\initialLayout=#VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL
    If i=1 : att\initialLayout=#VK_IMAGE_LAYOUT_GENERAL : EndIf
    att\finalLayout=#VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL
    NalCheck(id+6,vkCreateRenderPass(dev,@pi,0,@pass),0)
    If NalFailure<>0 : Goto NalClearLayoutDone : EndIf
    ri\renderPass=pass
    clear[0]=$3F800000 : clear[1]=0
    NalCheck(id+7,vkBeginCommandBuffer(cmd,@bi),0)
    vkCmdBeginRenderPass(cmd,@ri,#VK_SUBPASS_CONTENTS_INLINE) : vkCmdEndRenderPass(cmd)
    NalCheck(id+8,vkEndCommandBuffer(cmd),0)
    NalCheck(id+9,vkQueueSubmit(nvcQueue,1,@si,0),#ANVIL_VK_ERR_STATE)
    NalCheck(id+10,vkMapMemory(dev,*c\memory,0,#VK_WHOLE_SIZE,0,@mapped),0)
    If NalFailure<>0 : Goto NalClearLayoutDone : EndIf
    bad=0
    For y=0 To *c\height-1
      For x=0 To *c\width-1
        If PeekN(mapped+y* *c\pitch+x*4)<>$FF00FF00 : bad=bad+1 : EndIf
      Next
    Next
    vkUnmapMemory(dev,*c\memory) : NalCheck(id+11,bad,0)
    NalCheck(id+12,vkResetCommandBuffer(cmd,0),0)
    If NalFailure<>0 : Goto NalClearLayoutDone : EndIf
    vkDestroyRenderPass(dev,pass,0) : pass=0
    ; The matching defined layout clears all pixels, without a LOAD capability.
    att\initialLayout=layout
    If i=2 : att\finalLayout=#VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL : EndIf
    NalCheck(id+13,vkCreateRenderPass(dev,@pi,0,@pass),0)
    If NalFailure<>0 : Goto NalClearLayoutDone : EndIf
    ri\renderPass=pass
    NalCheck(id+14,vkBeginCommandBuffer(cmd,@bi),0)
    vkCmdBeginRenderPass(cmd,@ri,#VK_SUBPASS_CONTENTS_INLINE) : vkCmdEndRenderPass(cmd)
    NalCheck(id+15,vkEndCommandBuffer(cmd),0)
    NalCheck(id+16,vkQueueSubmit(nvcQueue,1,@si,0),0)
    NalCheck(id+17,vkQueueWaitIdle(nvcQueue),0)
    NalCheck(id+18,vkMapMemory(dev,*c\memory,0,#VK_WHOLE_SIZE,0,@mapped),0)
    If NalFailure<>0 : Goto NalClearLayoutDone : EndIf
    bad=0
    For y=0 To *c\height-1
      For x=0 To *c\width-1
        If PeekN(mapped+y* *c\pitch+x*4)<>$FFFF0000 : bad=bad+1 : EndIf
      Next
    Next
    vkUnmapMemory(dev,*c\memory) : NalCheck(id+19,bad,0)
    NalCheck(id+20,vkResetCommandBuffer(cmd,0),0)
    If NalFailure<>0 : Goto NalClearLayoutDone : EndIf
    vkDestroyRenderPass(dev,pass,0) : pass=0
    clear[0]=0 : clear[1]=$3F800000
  Next
  ; Continue from a completed COLOR_ATTACHMENT_OPTIMAL target through LOAD.
  ; Deliberately supply no clear values: the red output must survive unchanged.
  att\loadOp=#VK_ATTACHMENT_LOAD_OP_LOAD
  att\initialLayout=#VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL
  att\finalLayout=#VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL
  NalCheck(700,vkCreateRenderPass(dev,@pi,0,@pass),0)
  If NalFailure<>0 : Goto NalClearLayoutDone : EndIf
  ri\renderPass=pass : ri\clearValueCount=0 : ri\pClearValues=0
  NalCheck(701,vkBeginCommandBuffer(cmd,@bi),0)
  vkCmdBeginRenderPass(cmd,@ri,#VK_SUBPASS_CONTENTS_INLINE) : vkCmdEndRenderPass(cmd)
  NalCheck(702,vkEndCommandBuffer(cmd),0)
  NalCheck(703,vkQueueSubmit(nvcQueue,1,@si,0),0)
  NalCheck(704,vkQueueWaitIdle(nvcQueue),0)
  NalCheck(705,vkMapMemory(dev,*c\memory,0,#VK_WHOLE_SIZE,0,@mapped),0)
  If NalFailure<>0 : Goto NalClearLayoutDone : EndIf
  bad=0
  For y=0 To *c\height-1
    For x=0 To *c\width-1
      If PeekN(mapped+y* *c\pitch+x*4)<>$FFFF0000 : bad=bad+1 : EndIf
    Next
  Next
  vkUnmapMemory(dev,*c\memory) : NalCheck(706,bad,0)
  NalCheck(707,vkResetCommandBuffer(cmd,0),0)
  If NalFailure<>0 : Goto NalClearLayoutDone : EndIf
  vkDestroyRenderPass(dev,pass,0) : pass=0
  ; Forbidden final layouts still refuse and leave a null output handle.
  att\finalLayout=#VK_IMAGE_LAYOUT_UNDEFINED
  NalCheck(708,vkCreateRenderPass(dev,@pi,0,@pass),#ANVIL_VK_ERR_UNSUPPORTED)
  NalCheck(709,pass,0)
  att\finalLayout=#VK_IMAGE_LAYOUT_PREINITIALIZED
  NalCheck(710,vkCreateRenderPass(dev,@pi,0,@pass),#ANVIL_VK_ERR_UNSUPPORTED)
  NalCheck(711,pass,0)
  NalClearLayoutDone:
  vkFreeCommandBuffers(dev,nvcCommandPool,1,@cmd)
  If pass<>0 : vkDestroyRenderPass(dev,pass,0) : EndIf
EndProcedure

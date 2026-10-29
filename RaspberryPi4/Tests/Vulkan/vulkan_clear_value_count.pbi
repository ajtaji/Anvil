; SPDX-License-Identifier: MIT
; Extra VkClearValue entries must not reject or change attachment zero.
Procedure NalClearValueCountCase(*c.NeonVkCanvas)
  Protected ai.VkCommandBufferAllocateInfo,bi.VkCommandBufferBeginInfo
  Protected ri.VkRenderPassBeginInfo,si.VkSubmitInfo
  Protected cmd.i,dev.i,mapped.i,x.i,y.i,bad.i,i.i
  Protected Dim clear.l[8]
  dev=*c\target\device
  ai\sType=#VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO
  ai\commandPool=nvcCommandPool : ai\level=#VK_COMMAND_BUFFER_LEVEL_PRIMARY : ai\commandBufferCount=1
  NalCheck(500,vkAllocateCommandBuffers(dev,@ai,@cmd),0)
  If NalFailure<>0 : ProcedureReturn : EndIf
  bi\sType=#VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO
  ri\sType=#VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO
  ri\renderPass=*c\target\renderPass : ri\framebuffer=*c\framebuffer
  ri\renderArea\extent\width=*c\width : ri\renderArea\extent\height=*c\height
  si\sType=#VK_STRUCTURE_TYPE_SUBMIT_INFO : si\commandBufferCount=1 : si\pCommandBuffers=@cmd
  ; First value is opaque green. The unused second value is opaque red.
  clear[1]=$3F800000 : clear[3]=$3F800000
  clear[4]=$3F800000 : clear[7]=$3F800000
  ; Refused recordings must reset cleanly before the successful case.
  For i=0 To 2
    NalCheck(501+i*4,vkBeginCommandBuffer(cmd,@bi),0)
    ri\clearValueCount=0 : ri\pClearValues=@clear[0]
    If i=1 : ri\clearValueCount=2 : ri\pClearValues=0 : EndIf
    If i=2 : ri\clearValueCount=2 : ri\pClearValues=@clear[0] : EndIf
    vkCmdBeginRenderPass(cmd,@ri,#VK_SUBPASS_CONTENTS_INLINE)
    If i=2 : vkCmdEndRenderPass(cmd) : EndIf
    If i<2
      NalCheck(502+i*4,vkEndCommandBuffer(cmd),#ANVIL_VK_ERR_ARGS)
      NalCheck(503+i*4,vkResetCommandBuffer(cmd,0),0)
    Else
      NalCheck(510,vkEndCommandBuffer(cmd),0)
    EndIf
    If NalFailure<>0 : Goto NalClearCountDone : EndIf
  Next
  NalCheck(511,vkQueueSubmit(nvcQueue,1,@si,0),0)
  NalCheck(512,vkQueueWaitIdle(nvcQueue),0)
  If NalFailure<>0 : Goto NalClearCountDone : EndIf
  NalCheck(513,vkMapMemory(dev,*c\memory,0,#VK_WHOLE_SIZE,0,@mapped),0)
  If NalFailure<>0 : Goto NalClearCountDone : EndIf
  For y=0 To *c\height-1
    For x=0 To *c\width-1
      If PeekN(mapped+y* *c\pitch+x*4)<>$FF00FF00 : bad=bad+1 : EndIf
    Next
  Next
  vkUnmapMemory(dev,*c\memory)
  NalCheck(514,bad,0)
  NalClearCountDone:
  vkFreeCommandBuffers(dev,nvcCommandPool,1,@cmd)
EndProcedure

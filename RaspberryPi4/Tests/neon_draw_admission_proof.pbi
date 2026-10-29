; Returning physical proof of unlaunched BCL admission rollback and retry.
Procedure.i streamMemory()
 Define i.i,n.i
 For i=1 To #ANVIL_VK_MAX_MEMORY : If avkMemLive[i]<>0 : n=n+1 : EndIf : Next
 ProcedureReturn n
EndProcedure

Procedure streamCapture(base.i,pitch.i,frame.i)
 Define x.i,y.i
 For y=0 To 63
  For x=0 To 63 : PokeL($E2400000+frame*16384+(y*64+x)*4,PeekL(base+y*pitch+x*4)) : Next
 Next
EndProcedure

Procedure.i admissionIdleRefs()
 Define i.i
 If avkFlightActive<>0 Or avkFlightQuarantined<>0 Or avkFlightLedgerCommitted<>0 Or avkBackendGpuLeaseState()<>0 : ProcedureReturn 0 : EndIf
 For i=1 To #ANVIL_VK_MAX_MEMORY : If avkMemInFlight[i]<>0 : ProcedureReturn 0 : EndIf : Next
 For i=1 To #ANVIL_VK_MAX_BUFFERS : If avkBufInFlight[i]<>0 : ProcedureReturn 0 : EndIf : Next
 For i=1 To #ANVIL_VK_MAX_PIPELINES : If avkPipeInFlight[i]<>0 : ProcedureReturn 0 : EndIf : Next
 ProcedureReturn 1
EndProcedure

Procedure.i streamProof(phys.i,dev.i,queue.i,pool.i,rp.i,fb.i,base.i,pitch.i)
 Define rc.i,oldBcl.i,submits.i,completed.i,jobs.i,command.i,fence.i,waitSem.i,signalSem.i,x.i,y.i
 Define si.VkSubmitInfo
 Define sci.VkSemaphoreCreateInfo
 Define stage.l=#VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT
 NeonVkChromeDestroy() : SafetyWatchdogStart(15)
 rc=NeonVkChromeCreateWithCapacities(phys,dev,queue,pool,rp,fb,800,1280,16,64)
 If rc<>0 : ProcedureReturn 821 : EndIf
 rc=NeonVkChromeBegin(@nwClear[0])
 If rc=0 : rc=Neon_Box(4,4,24,24,$FF00FF00) : EndIf
 If rc<>0 : ProcedureReturn 822 : EndIf
 streamCapture(base,pitch,0)
 submits=AnvilVkSubmitCount() : completed=AnvilVkCompleteCount() : jobs=avkV3dJobs
 oldBcl=gNeonBclBytes : gNeonBclBytes=8192
 rc=NeonVkChromeEnd()
 gNeonBclBytes=oldBcl
 PokeI($E1C01010,rc)
 If rc<>#VK_ERROR_OUT_OF_DEVICE_MEMORY Or nvcFrameAbortable<>1 Or nvcInFrame<>0 Or admissionIdleRefs()<>1 Or AnvilVkSubmitCount()<>submits Or AnvilVkCompleteCount()<>completed Or avkV3dJobs<>jobs : ProcedureReturn 823 : EndIf
 command=nvcCommand : fence=nvcFence
 If AnvilVkCommandBufferState(command)<>#ANVIL_VK_CB_EXECUTABLE Or vkGetFenceStatus(dev,fence)<>#VK_NOT_READY : ProcedureReturn 824 : EndIf
 For y=0 To 63
  For x=0 To 63
   If PeekL($E2400000+(y*64+x)*4)<>PeekL(base+y*pitch+x*4) : ProcedureReturn 825 : EndIf
  Next
 Next
 ; Signal a binary wait semaphore through an empty public submission.
 sci\sType=#VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO
 rc=vkCreateSemaphore(dev,@sci,0,@waitSem)
 If rc=0 : rc=vkCreateSemaphore(dev,@sci,0,@signalSem) : EndIf
 If rc<>0 : ProcedureReturn 826 : EndIf
 si\sType=#VK_STRUCTURE_TYPE_SUBMIT_INFO : si\signalSemaphoreCount=1 : si\pSignalSemaphores=@waitSem
 rc=vkQueueSubmit(queue,1,@si,0) : If rc<>0 : ProcedureReturn 827 : EndIf
 si\commandBufferCount=1 : si\pCommandBuffers=@command
 si\waitSemaphoreCount=1 : si\pWaitSemaphores=@waitSem : si\pWaitDstStageMask=@stage
 si\pSignalSemaphores=@signalSem
 submits=AnvilVkSubmitCount() : completed=AnvilVkCompleteCount()
 gNeonBclBytes=8192 : rc=vkQueueSubmit(queue,1,@si,fence) : gNeonBclBytes=oldBcl
 If rc<>#VK_ERROR_OUT_OF_DEVICE_MEMORY Or admissionIdleRefs()<>1 Or AnvilVkSubmitCount()<>submits Or AnvilVkCompleteCount()<>completed : ProcedureReturn 828 : EndIf
 If avkSemaphoreState(dev,waitSem)<>#ANVIL_VK_SEM_SIGNALED Or avkSemaphoreState(dev,signalSem)<>#ANVIL_VK_SEM_UNSIGNALED Or vkGetFenceStatus(dev,fence)<>#VK_NOT_READY Or AnvilVkCommandBufferState(command)<>#ANVIL_VK_CB_EXECUTABLE : ProcedureReturn 829 : EndIf
 PokeI($E1C01018,1)
 ; Retry the exact executable command and semaphore transaction after the
 ; capacity is restored. No reset, re-recording or replacement objects.
 SafetyWatchdogPet() : rc=vkQueueSubmit(queue,1,@si,fence)
 If rc<>0 : ProcedureReturn 830 : EndIf
 rc=vkWaitForFences(dev,1,@fence,1,#NEON_VK_CHROME_WAIT_NS)
 If rc<>0 Or admissionIdleRefs()<>1 Or avkSemaphoreState(dev,waitSem)<>0 Or avkSemaphoreState(dev,signalSem)<>1 Or vkGetFenceStatus(dev,fence)<>0 : ProcedureReturn 831 : EndIf
 If AnvilVkSubmitCount()<>submits+1 Or AnvilVkCompleteCount()<>completed+1 Or avkV3dJobs<>jobs+1 : ProcedureReturn 832 : EndIf
 PokeI($E1C01020,AnvilVkSubmitCount()-submits) : PokeI($E1C01028,AnvilVkCompleteCount()-completed)
 streamCapture(base,pitch,0)
 vkDestroySemaphore(dev,waitSem,0) : vkDestroySemaphore(dev,signalSem,0)
 rc=NeonVkChromeAbort() : If rc<>0 : ProcedureReturn 833 : EndIf
 ; A normal new frame after Abort proves the adapter can be reused.
 rc=NeonVkChromeBegin(@nwClear[0])
 If rc=0 : rc=Neon_Box(32,32,16,16,$FF0000FF) : EndIf
 If rc=0 : rc=NeonVkChromeEnd() : EndIf
 If rc<>0 Or NeonVkChromePresentConsume()<>1 Or admissionIdleRefs()<>1 : ProcedureReturn 834 : EndIf
 streamCapture(base,pitch,1) : PokeI($E1C01008,2)
 PokeI($E1C01030,1) : NeonVkChromeDestroy()
 ProcedureReturn 0
EndProcedure

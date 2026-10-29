; Shared queue-contract proof. The explicit state backend has no hardware,
; writes no pixels, and can deliberately leave simulated resources retained.
Procedure vdsRecord(slot.i, value.i)
  PokeI(#VDS_REPORT + slot * 8, value)
EndProcedure

Procedure.i vdsImageUnchanged(base.i, bytes.i)
  Define i.i
  For i=0 To bytes-1
    If PeekA(base+i)<>((i*37+11) & 255) : ProcedureReturn 0 : EndIf
  Next
  ProcedureReturn 1
EndProcedure

Procedure.i VulkanDrawAdmissionStateChecks(dev.i, queue.i, cmd.i, fence.i, img.i, mem.i)
  Define sci.VkSemaphoreCreateInfo
  Define si.VkSubmitInfo
  Define waitSem.i,signalSem.i,waitSlot.i,signalSlot.i,imgSlot.i,memSlot.i,fenceSlot.i
  Define rc.i,expected.i,submits.i,completed.i,i.i,base.i,bytes.i,tx.i,retained.i
  Define stage.l=#VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT
  retained=Bool(#VDS_MODE=3 Or #VDS_MODE=4 Or #VDS_MODE=5)
  avkTbLeaseRequired=Bool(#VDS_MODE<>1)
  sci\sType=#VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO
  rc=vkCreateSemaphore(dev,@sci,0,@waitSem)
  If rc=0 : rc=vkCreateSemaphore(dev,@sci,0,@signalSem) : EndIf
  If rc<>0 : ProcedureReturn 101 : EndIf
  waitSlot=avkSemaphoreSlot(waitSem) : signalSlot=avkSemaphoreSlot(signalSem)
  imgSlot=avkImgSlot(img) : memSlot=avkMemSlot(mem) : fenceSlot=avkFenceSlot(fence)
  base=AnvilVkImageAddress(img) : bytes=avkImgSize[imgSlot]
  If bytes<1 Or bytes>4096 : ProcedureReturn 102 : EndIf
  For i=0 To bytes-1 : PokeA(base+i,(i*37+11) & 255) : Next
  si\sType=#VK_STRUCTURE_TYPE_SUBMIT_INFO : si\signalSemaphoreCount=1 : si\pSignalSemaphores=@waitSem
  rc=vkQueueSubmit(queue,1,@si,0) : If rc<>0 : ProcedureReturn 103 : EndIf
  si\commandBufferCount=1 : si\pCommandBuffers=@cmd
  si\waitSemaphoreCount=1 : si\pWaitSemaphores=@waitSem : si\pWaitDstStageMask=@stage
  si\pSignalSemaphores=@signalSem
  submits=AnvilVkSubmitCount() : completed=AnvilVkCompleteCount()
  If #VDS_MODE=4
    ; Prime the shared classifier with a real, rolled-back refusal. A raw
    ; negative status on the next attempt must not inherit that qualification.
    AnvilVkTestBackendRefuseNextDraw(#VK_ERROR_OUT_OF_DEVICE_MEMORY)
    rc=vkQueueSubmit(queue,1,@si,fence)
    If rc<>#VK_ERROR_OUT_OF_DEVICE_MEMORY Or avkFlightActive<>0 Or avkTbLeaseOwner<>0 Or AnvilVkCommandBufferState(cmd)<>#ANVIL_VK_CB_EXECUTABLE Or avkSemaphoreState(dev,waitSem)<>1 Or avkSemaphoreState(dev,signalSem)<>0 : ProcedureReturn 104 : EndIf
  EndIf
  expected=#VK_ERROR_OUT_OF_DEVICE_MEMORY
  If #VDS_MODE=3
    AnvilVkTestBackendRawDrawResultNext(-1) : expected=#VK_ERROR_DEVICE_LOST
  ElseIf #VDS_MODE=4
    AnvilVkTestBackendRawDrawResultNext(#ANVIL_VK_JOB_REFUSED) : expected=#VK_ERROR_DEVICE_LOST
  ElseIf #VDS_MODE=5
    AnvilVkTestBackendRefuseNextDraw(#VK_ERROR_OUT_OF_DEVICE_MEMORY)
    AnvilVkTestBackendFailNextLeaseRelease() : expected=#VK_ERROR_DEVICE_LOST
  ElseIf #VDS_MODE=6
    AnvilVkTestBackendRefuseNextDraw(0) : expected=#VK_ERROR_INITIALIZATION_FAILED
  Else
    AnvilVkTestBackendRefuseNextDraw(#VK_ERROR_OUT_OF_DEVICE_MEMORY)
  EndIf
  rc=vkQueueSubmit(queue,1,@si,fence)
  vdsRecord(4,rc) : vdsRecord(5,avkFlightActive) : vdsRecord(6,avkFlightQuarantined)
  vdsRecord(7,avkTbLeaseOwner) : vdsRecord(8,AnvilVkFenceStatus(dev,fence))
  vdsRecord(9,AnvilVkCommandBufferState(cmd))
  vdsRecord(10,AnvilVkSubmitCount()-submits) : vdsRecord(11,AnvilVkCompleteCount()-completed)
  vdsRecord(12,avkImgInFlight[imgSlot]) : vdsRecord(13,avkMemInFlight[memSlot])
  vdsRecord(14,avkSemaphoreState(dev,waitSem)) : vdsRecord(15,avkSemaphoreState(dev,signalSem))
  vdsRecord(16,avkSemPendingWait[waitSlot]) : vdsRecord(17,avkSemPendingSignal[signalSlot])
  vdsRecord(18,avkImgLayout[imgSlot]) : vdsRecord(19,vdsImageUnchanged(base,bytes))
  vdsRecord(20,avkBackendRefusalCode) : vdsRecord(25,avkFlightBackendAttempted)
  vdsRecord(26,avkFenceInUse[fenceSlot]) : vdsRecord(27,avkFlightLedgerCommitted)
  tx=avkSemaphoreReservationSlot(avkFlightSemaphoreReservation)
  If tx<>0 : vdsRecord(28,avkSemTxStage[tx]) : EndIf
  vdsRecord(43,vkGetFenceStatus(dev,fence))
  If rc<>expected : ProcedureReturn 110 : EndIf
  If vdsImageUnchanged(base,bytes)<>1 Or avkImgLayout[imgSlot]<>#VK_IMAGE_LAYOUT_UNDEFINED : ProcedureReturn 111 : EndIf
  If retained<>0
    If avkFlightActive<>1 Or avkFlightQuarantined<>1 Or avkTbLeaseOwner<>-1 Or avkImgInFlight[imgSlot]<>1 Or avkMemInFlight[memSlot]<>1 Or avkFenceInUse[fenceSlot]<>1 Or avkFlightLedgerCommitted<>1 : ProcedureReturn 112 : EndIf
    If AnvilVkCommandBufferState(cmd)<>#ANVIL_VK_CB_PENDING Or AnvilVkSubmitCount()<>submits+1 Or AnvilVkCompleteCount()<>completed Or avkSemPendingWait[waitSlot]<>1 Or avkSemPendingSignal[signalSlot]<>1 Or vkGetFenceStatus(dev,fence)<>#VK_ERROR_DEVICE_LOST : ProcedureReturn 113 : EndIf
    If tx=0 Or avkSemTxStage[tx]<>#ANVIL_VK_SEM_TX_COMMITTED Or avkSemaphoreState(dev,waitSem)<>0 Or avkSemaphoreState(dev,signalSem)<>0 : ProcedureReturn 114 : EndIf
    vdsRecord(24,avkTbLeaseOwner) : vdsRecord(29,avkTbCalls)
    vdsRecord(31,vdsImageUnchanged(base,bytes))
    ; Keep simulated uncertainty retained. No forced release/reset is used.
    ProcedureReturn 0
  EndIf
  If avkFlightActive<>0 Or avkFlightQuarantined<>0 Or avkTbLeaseOwner<>0 Or avkImgInFlight[imgSlot]<>0 Or avkMemInFlight[memSlot]<>0 Or avkFenceInUse[fenceSlot]<>0 Or avkFlightLedgerCommitted<>0 : ProcedureReturn 115 : EndIf
  If AnvilVkCommandBufferState(cmd)<>#ANVIL_VK_CB_EXECUTABLE Or AnvilVkSubmitCount()<>submits Or AnvilVkCompleteCount()<>completed Or avkSemPendingWait[waitSlot]<>0 Or avkSemPendingSignal[signalSlot]<>0 Or vkGetFenceStatus(dev,fence)<>#VK_NOT_READY : ProcedureReturn 116 : EndIf
  If tx<>0 Or avkSemaphoreState(dev,waitSem)<>1 Or avkSemaphoreState(dev,signalSem)<>0 : ProcedureReturn 117 : EndIf
  rc=vkQueueSubmit(queue,1,@si,fence)
  If rc<>0 Or vkGetFenceStatus(dev,fence)<>0 Or AnvilVkSubmitCount()<>submits+1 Or AnvilVkCompleteCount()<>completed+1 Or avkImgInFlight[imgSlot]<>0 Or avkMemInFlight[memSlot]<>0 Or avkTbLeaseOwner<>0 Or avkFlightActive<>0 : ProcedureReturn 118 : EndIf
  If avkSemaphoreState(dev,waitSem)<>0 Or avkSemaphoreState(dev,signalSem)<>1 Or avkImgLayout[imgSlot]<>#VK_IMAGE_LAYOUT_GENERAL Or vdsImageUnchanged(base,bytes)<>1 : ProcedureReturn 119 : EndIf
  vdsRecord(21,1) : vdsRecord(22,AnvilVkCompleteCount()-completed) : vdsRecord(23,1)
  vdsRecord(24,avkTbLeaseOwner) : vdsRecord(29,avkTbCalls) : vdsRecord(31,vdsImageUnchanged(base,bytes))
  vkDestroySemaphore(dev,waitSem,0) : vkDestroySemaphore(dev,signalSem,0)
  ProcedureReturn 0
EndProcedure

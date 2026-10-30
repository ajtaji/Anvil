; Shared cooperative queue for a copy-owning DMA transmitter. Serialized calls.
; Backend Try(frame,bytes): 1 accepted/copy retained, 0 no attempt/busy, -1 error.
; Backend Poll(): 1 completed, 0 pending, -1 failed. Completion must remain
; latched across unrelated synchronous sends until the next Try. Backend retains
; its own storage after ambiguous failure/deadline; it never retains queue memory.
; Ready and Generation must be bounded reads, without PHY polling or link setup.
#LINK_DMA_TX_DEADLINE_MS = 100
Global Dim linkDmaTxQueue.a[#LINK_TXQ_BYTES]
Global Dim linkDmaTxAt.i[#LINK_TXQ_SLOTS]
Global linkDmaTxKind.i,linkDmaTxEpoch.i,linkDmaTxDevice.i,linkDmaTxAddress.i,linkDmaTxReady.i
Global linkDmaTxBusy.i,linkDmaTxActive.i
Global *linkDmaTry,*linkDmaPoll,*linkDmaReady,*linkDmaGeneration

Procedure.i LinkDmaTxConfigure(kind.i,*submit,*poll,*ready,*generation)
 If kind<=0 Or *submit=0 Or *poll=0 Or *ready=0 Or *generation=0 : ProcedureReturn 0 : EndIf
 ; Installation is once, before any packet can be accepted.
 If linkDmaTxKind<>0 : ProcedureReturn 0 : EndIf
 linkDmaTxKind=kind : *linkDmaTry=*submit : *linkDmaPoll=*poll
 *linkDmaReady=*ready : *linkDmaGeneration=*generation
 ProcedureReturn 1
EndProcedure

Procedure.i linkDmaTxRefresh()
 Define ready.i,device.i,address.i,dropped.i
 ready=linkDmaReady() : device=linkDmaGeneration()
 address=NetIfGeneration(linkDmaTxKind)
 If linkDmaTxEpoch=0 Or ready<>linkDmaTxReady Or device<>linkDmaTxDevice Or address<>linkDmaTxAddress
  linkDmaTxEpoch=linkDmaTxEpoch+1
  dropped=LinkTxQueueInit(@linkDmaTxQueue[0],linkDmaTxEpoch)
  If dropped>0
   gLinkTxPending=gLinkTxPending-dropped : gLinkTxDropped=gLinkTxDropped+dropped
   gLinkTxFail=gLinkTxFail+dropped
  EndIf
  linkDmaTxActive=0
  linkDmaTxReady=ready : linkDmaTxDevice=device : linkDmaTxAddress=address
 EndIf
 ProcedureReturn ready
EndProcedure

Procedure LinkDmaTxProgress(kind.i)
 Define frame.i,bytes.i,ticket.i,rc.i,age.i
 If linkDmaTxKind=0 Or kind<>linkDmaTxKind Or linkDmaTxBusy<>0 : ProcedureReturn : EndIf
 linkDmaTxBusy=1
 If linkDmaTxRefresh()=0 : linkDmaTxBusy=0 : ProcedureReturn : EndIf
 frame=LinkTxQueuePeek(@linkDmaTxQueue[0],linkDmaTxEpoch)
 If frame=0 : linkDmaTxBusy=0 : ProcedureReturn : EndIf
 bytes=LinkTxQueueLength(@linkDmaTxQueue[0],linkDmaTxEpoch)
 ticket=LinkTxQueueTicket(@linkDmaTxQueue[0],linkDmaTxEpoch)
 age=(millis()-linkDmaTxAt[(ticket-1) % #LINK_TXQ_SLOTS]) & $FFFFFFFF
 rc=-1
 If age<#LINK_DMA_TX_DEADLINE_MS
  If linkDmaTxActive<>0
   rc=linkDmaPoll()
  Else
   rc=linkDmaTry(frame,bytes)
   If rc=1 : linkDmaTxActive=1 : rc=0 : EndIf
  EndIf
 EndIf
 If rc=0
  gLinkTxBusy=gLinkTxBusy+1
 Else
  LinkTxQueueFinish(@linkDmaTxQueue[0],linkDmaTxEpoch,ticket,rc)
  linkDmaTxActive=0 : gLinkTxPending=gLinkTxPending-1
  If rc=1
   gLinkTxCompleted=gLinkTxCompleted+1
  Else
   gLinkTxDropped=gLinkTxDropped+1 : gLinkTxFail=gLinkTxFail+1
  EndIf
 EndIf
 linkDmaTxBusy=0
EndProcedure

Procedure.i LinkDmaTxSubmit(kind.i,frame.i,bytes.i)
 Define rc.i,ticket.i
 If linkDmaTxKind=0 Or kind<>linkDmaTxKind : ProcedureReturn -2 : EndIf
 If linkDmaTxBusy<>0 Or linkDmaTxRefresh()=0 : ProcedureReturn 0 : EndIf
 If bytes<14 : ProcedureReturn 0 : EndIf
 If LinkTxQueueCount(@linkDmaTxQueue[0],linkDmaTxEpoch)>=#LINK_TXQ_SLOTS : LinkDmaTxProgress(kind) : EndIf
 ticket=PeekI(@linkDmaTxQueue[0]+32)
 rc=LinkTxQueueSubmit(@linkDmaTxQueue[0],linkDmaTxEpoch,frame,bytes)
 If rc<>1 : ProcedureReturn 0 : EndIf
 linkDmaTxAt[(ticket-1) % #LINK_TXQ_SLOTS]=millis()
 gLinkTxPending=gLinkTxPending+1
 If LinkTxQueueCount(@linkDmaTxQueue[0],linkDmaTxEpoch)=1 : LinkDmaTxProgress(kind) : EndIf
 ProcedureReturn 1
EndProcedure

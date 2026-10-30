; Shared CYW43 protocol-frame queue. Compose link, link_tx_queue, netif, the
; CYW43 driver and the board's HwLink backend first. Used by Pi 3 and Pi 4/5.
; Only transmit credit waiting is removed: the SDIO bus operation still runs
; synchronously. This service never receives frames or dispatches NetInput.
; Console byte-stream output keeps its existing synchronous drain contract.
#LINK_CYW_TX_DEADLINE_MS = 100
Global Dim linkCywTxQueue.a[#LINK_TXQ_BYTES]
Global Dim linkCywTxAt.i[#LINK_TXQ_SLOTS]
Global linkCywTxEpoch.i,linkCywTxRadio.i,linkCywTxAddress.i,linkCywTxReady.i
Global linkCywTxLastReceipt.i
Global linkCywTxBusy.i

Procedure.i linkCywTxRefresh()
 Define ready.i,radio.i,address.i,dropped.i
 ready=HwLinkReady(#HW_LINK_WIFI)
 radio=Cyw43TxGeneration() : address=NetIfGeneration(#HW_LINK_WIFI)
 If linkCywTxEpoch=0 Or ready<>linkCywTxReady Or radio<>linkCywTxRadio Or address<>linkCywTxAddress
  linkCywTxEpoch=linkCywTxEpoch+1
  dropped=LinkTxQueueInit(@linkCywTxQueue[0],linkCywTxEpoch)
  If dropped>0
   gLinkTxPending=gLinkTxPending-dropped : gLinkTxDropped=gLinkTxDropped+dropped
   gLinkTxFail=gLinkTxFail+dropped
  EndIf
  linkCywTxReady=ready : linkCywTxRadio=radio : linkCywTxAddress=address
 EndIf
 ProcedureReturn ready
EndProcedure

Procedure LinkCywTxProgress(kind.i)
 Define frame.i,bytes.i,ticket.i,rc.i,dst.i,i.i,age.i
 If kind<>#HW_LINK_WIFI Or linkCywTxBusy<>0 : ProcedureReturn : EndIf
 linkCywTxBusy=1
 If linkCywTxRefresh()=0 : linkCywTxBusy=0 : ProcedureReturn : EndIf
 frame=LinkTxQueuePeek(@linkCywTxQueue[0],linkCywTxEpoch)
 If frame=0 : linkCywTxBusy=0 : ProcedureReturn : EndIf
 bytes=LinkTxQueueLength(@linkCywTxQueue[0],linkCywTxEpoch)
 ticket=LinkTxQueueTicket(@linkCywTxQueue[0],linkCywTxEpoch)
 age=(millis()-linkCywTxAt[(ticket-1) % #LINK_TXQ_SLOTS]) & $FFFFFFFF
 rc=#CYW43_IO_TIMEOUT
 If age<#LINK_CYW_TX_DEADLINE_MS
  ; A missing credit does not touch the shared TX buffer, even its payload.
  rc=#CYW43_IO_AGAIN
  If Cyw43CanSend()<>0
   dst=Cyw43DataPtr()
   If dst<>0
    For i=0 To bytes-1 : PokeA(dst+i,PeekA(frame+i)) : Next
    rc=Cyw43TrySend(bytes)
   Else
    rc=#CYW43_IO_BADFRAME
   EndIf
  EndIf
 EndIf
 If rc=#CYW43_IO_AGAIN
  gLinkTxBusy=gLinkTxBusy+1
 Else
  If rc=#CYW43_IO_OK
   LinkTxQueueFinish(@linkCywTxQueue[0],linkCywTxEpoch,ticket,1)
   gLinkTxCompleted=gLinkTxCompleted+1
  Else
   LinkTxQueueFinish(@linkCywTxQueue[0],linkCywTxEpoch,ticket,rc)
   gLinkTxDropped=gLinkTxDropped+1 : gLinkTxFail=gLinkTxFail+1
  EndIf
  gLinkTxPending=gLinkTxPending-1
 EndIf
 linkCywTxBusy=0
EndProcedure

; -2 delegates other hardware kinds to their existing backend. A full queue
; is explicit backpressure; no accepted frame is overwritten to make room.
Procedure.i LinkCywTxSubmit(kind.i,frame.i,bytes.i)
 Define rc.i,ticket.i
 linkCywTxLastReceipt=0
 If kind<>#HW_LINK_WIFI : ProcedureReturn -2 : EndIf
 If linkCywTxBusy<>0 Or linkCywTxRefresh()=0 : ProcedureReturn 0 : EndIf
 If LinkTxQueueCount(@linkCywTxQueue[0],linkCywTxEpoch)>=#LINK_TXQ_SLOTS
  LinkCywTxProgress(kind)
 EndIf
 ticket=PeekI(@linkCywTxQueue[0]+32)
 rc=LinkTxQueueSubmit(@linkCywTxQueue[0],linkCywTxEpoch,frame,bytes)
 If rc<>1 : ProcedureReturn 0 : EndIf
 linkCywTxAt[(ticket-1) % #LINK_TXQ_SLOTS]=millis()
 If linkCywTxEpoch<$80000000 : linkCywTxLastReceipt=linkCywTxEpoch*$100000000+ticket : EndIf
 gLinkTxPending=gLinkTxPending+1
 If LinkTxQueueCount(@linkCywTxQueue[0],linkCywTxEpoch)=1 : LinkCywTxProgress(kind) : EndIf
 ProcedureReturn 1
EndProcedure

; Caller owns only a numeric token; no retained caller pointer or RX buffer.
Procedure.i LinkCywTxSubmitReceipt(kind.i,frame.i,bytes.i)
 Define rc.i
 If kind<>#HW_LINK_WIFI : ProcedureReturn -2 : EndIf
 If linkCywTxBusy<>0 Or linkCywTxRefresh()=0 : ProcedureReturn 0 : EndIf
 If linkCywTxEpoch>=$80000000 : ProcedureReturn 0 : EndIf
 rc=LinkCywTxSubmit(kind,frame,bytes)
 If rc<>1 : ProcedureReturn rc : EndIf
 ProcedureReturn linkCywTxLastReceipt
EndProcedure
Procedure.i LinkCywTxReceipt(kind.i,token.i)
 Define generation.i,ticket.i
 If kind<>#HW_LINK_WIFI : ProcedureReturn -2 : EndIf
 If token<=0 Or linkCywTxBusy<>0 : ProcedureReturn -2 : EndIf
 linkCywTxRefresh()
 generation=token>>32 : ticket=token&$FFFFFFFF
 ProcedureReturn LinkTxQueueResult(@linkCywTxQueue[0],generation,ticket)
EndProcedure

Procedure LinkCywTxInstall()
 LinkTxSetHooks(@LinkCywTxSubmit,@LinkCywTxProgress)
 LinkTxSetReceiptHooks(@LinkCywTxSubmitReceipt,@LinkCywTxReceipt)
EndProcedure

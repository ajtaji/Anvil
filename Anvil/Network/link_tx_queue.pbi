; Owned FIFO for cooperative link transmitters. No device or protocol dependencies.
; One context per link, zero-filled before first Init. Serialized callers only.
; Init starts a new positive generation and returns the discarded pending count.
; Submit copies the frame: 1 accepted, 0 full, -1 invalid/stale. Acceptance is
; not wire completion. A caller may reuse its input as soon as Submit returns.
; Peek/Length/Ticket describe the head. Finish requires the same generation and
; ticket: result 0 leaves it pending, 1 completes it, negative drops it with a
; recorded error. A transfer that might have reached hardware must never be
; retried by reporting 0. Only a no-attempt/would-block result may use 0.
; The consumer must finish its buffer access before Finish or Init: DMA that
; retains this pointer needs a separate completion owner, not this interface.
; A pump attempts at most one head per call and never waits for credit here.
; A receipt is (generation,ticket). NextTicket predicts the next accepted Submit
; under the serialized-caller contract; a refused Submit issues no receipt.
; Result returns 0 pending, 1 completed, -1 failed, -2 stale/unknown/expired.
; Four retired results are retained independently of the four pending slots.
; Poll promptly: expiration is never completion and must not trigger replay.
; Init invalidates old receipts, even if the new generation reuses a ticket.
#LINK_TXQ_MAGIC = $54585132
#LINK_TXQ_SLOTS = 4
#LINK_TXQ_FRAME_MAX = 1514
#LINK_TXQ_HEADER = 144
#LINK_TXQ_STRIDE = 1536
#LINK_TXQ_BYTES = #LINK_TXQ_HEADER + #LINK_TXQ_SLOTS * #LINK_TXQ_STRIDE

Procedure.i LinkTxQueueValid(q.i, generation.i)
 If q=0 Or generation<=0 : ProcedureReturn 0 : EndIf
 If PeekI(q)<>#LINK_TXQ_MAGIC Or PeekI(q+8)<>generation : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure

Procedure.i LinkTxQueueInit(q.i, generation.i)
 Define i.i,dropped.i
 If q=0 Or generation<=0 : ProcedureReturn -1 : EndIf
 dropped=0
 If PeekI(q)=#LINK_TXQ_MAGIC
  If generation<=PeekI(q+8) : ProcedureReturn -1 : EndIf
  dropped=PeekI(q+24)
 EndIf
 For i=0 To #LINK_TXQ_BYTES-1 : PokeA(q+i,0) : Next
 PokeI(q,#LINK_TXQ_MAGIC) : PokeI(q+8,generation) : PokeI(q+32,1)
 ProcedureReturn dropped
EndProcedure

Procedure.i LinkTxQueueCount(q.i, generation.i)
 If LinkTxQueueValid(q,generation)=0 : ProcedureReturn -1 : EndIf
 ProcedureReturn PeekI(q+24)
EndProcedure

Procedure.i LinkTxQueueSubmit(q.i, generation.i, frame.i, bytes.i)
 Define n.i,slot.i,p.i,i.i,ticket.i
 If LinkTxQueueValid(q,generation)=0 : ProcedureReturn -1 : EndIf
 If frame=0 Or bytes<=0 Or bytes>#LINK_TXQ_FRAME_MAX : ProcedureReturn -1 : EndIf
 ; Refuse overflow and aliasing before copying over queue metadata or a head.
 If frame+bytes<frame : ProcedureReturn -1 : EndIf
 If frame<q+#LINK_TXQ_BYTES And q<frame+bytes : ProcedureReturn -1 : EndIf
 n=PeekI(q+24)
 If n>=#LINK_TXQ_SLOTS : ProcedureReturn 0 : EndIf
 ticket=PeekI(q+32)
 ; Never reuse a ticket within a generation, even after counter exhaustion.
 If ticket<=0 Or ticket=$7FFFFFFF : ProcedureReturn -1 : EndIf
 slot=(PeekI(q+16)+n) % #LINK_TXQ_SLOTS
 p=q+#LINK_TXQ_HEADER+slot*#LINK_TXQ_STRIDE
 For i=0 To bytes-1 : PokeA(p+16+i,PeekA(frame+i)) : Next
 PokeI(p,bytes) : PokeI(p+8,ticket)
 PokeI(q+32,ticket+1) : PokeI(q+24,n+1) : PokeI(q+40,PeekI(q+40)+1)
 ProcedureReturn 1
EndProcedure

Procedure.i LinkTxQueuePeek(q.i, generation.i)
 If LinkTxQueueValid(q,generation)=0 : ProcedureReturn 0 : EndIf
 If PeekI(q+24)=0 : ProcedureReturn 0 : EndIf
 ProcedureReturn q+#LINK_TXQ_HEADER+PeekI(q+16)*#LINK_TXQ_STRIDE+16
EndProcedure

Procedure.i LinkTxQueueLength(q.i, generation.i)
 Define p.i
 p=LinkTxQueuePeek(q,generation)
 If p=0 : ProcedureReturn 0 : EndIf
 ProcedureReturn PeekI(p-16)
EndProcedure

Procedure.i LinkTxQueueTicket(q.i, generation.i)
 Define p.i
 p=LinkTxQueuePeek(q,generation)
 If p=0 : ProcedureReturn 0 : EndIf
 ProcedureReturn PeekI(p-8)
EndProcedure

Procedure.i LinkTxQueueFinish(q.i, generation.i, ticket.i, result.i)
 Define p.i,i.i,receipt.i
 p=LinkTxQueuePeek(q,generation)
 If p=0 Or ticket<=0 : ProcedureReturn -1 : EndIf
 If PeekI(p-8)<>ticket Or result>1 : ProcedureReturn -1 : EndIf
 If result=0 : ProcedureReturn 0 : EndIf
 ; Keep the exact retired ticket and normalized outcome; never infer a packet
 ; result from aggregate counters or another packet's completion.
 receipt=q+80+((PeekI(q+48)+PeekI(q+56)) % #LINK_TXQ_SLOTS)*16
 PokeI(receipt,ticket)
 If result=1 : PokeI(receipt+8,1) : Else : PokeI(receipt+8,-1) : EndIf
 ; Retired bytes cannot leak into a later shorter frame or survive reset.
 For i=0 To #LINK_TXQ_STRIDE-1 : PokeA(p-16+i,0) : Next
 PokeI(q+16,(PeekI(q+16)+1) % #LINK_TXQ_SLOTS)
 PokeI(q+24,PeekI(q+24)-1)
 If result=1
  PokeI(q+48,PeekI(q+48)+1)
 Else
  PokeI(q+56,PeekI(q+56)+1) : PokeI(q+64,result)
 EndIf
 ProcedureReturn 1
EndProcedure

Procedure.i LinkTxQueueNextTicket(q.i,generation.i)
 Define ticket.i
 If LinkTxQueueValid(q,generation)=0 : ProcedureReturn 0 : EndIf
 ticket=PeekI(q+32)
 If ticket<=0 Or ticket=$7FFFFFFF : ProcedureReturn 0 : EndIf
 ProcedureReturn ticket
EndProcedure

Procedure.i LinkTxQueueResult(q.i,generation.i,ticket.i)
 Define i.i,p.i,slot.i
 If LinkTxQueueValid(q,generation)=0 Or ticket<=0 : ProcedureReturn -2 : EndIf
 If ticket>=PeekI(q+32) : ProcedureReturn -2 : EndIf
 For i=0 To PeekI(q+24)-1
  slot=(PeekI(q+16)+i) % #LINK_TXQ_SLOTS
  p=q+#LINK_TXQ_HEADER+slot*#LINK_TXQ_STRIDE
  If PeekI(p+8)=ticket : ProcedureReturn 0 : EndIf
 Next
 For i=0 To #LINK_TXQ_SLOTS-1
  p=q+80+i*16
  If PeekI(p)=ticket : ProcedureReturn PeekI(p+8) : EndIf
 Next
 ProcedureReturn -2
EndProcedure

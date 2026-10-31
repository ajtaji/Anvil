; SPDX-License-Identifier: MIT
; Independent RFC 9000 sections13.1/13.2/19.3 handshake ACK bookkeeping.
; One state per Initial/Handshake packet-number space. Record ONLY after
; packet authentication and successful processing of every contained frame.
XIncludeFile "Anvil/Network/quic_wire.pbi"
#QUIC_ACK_ARGUMENT=-3441
#QUIC_ACK_STATE=-3442
#QUIC_ACK_LIMIT=-3443
#QUIC_ACK_CAPACITY=-3444
Structure QuicHandshakeAck
 phase.i
 level.i
 entries.i
 capacity.i
 count.i
 demand.i
 pending.i
EndStructure
Procedure.i quica_Span(p.i,n.i)
 If p<=0 Or n<0 Or p>$7FFFFFFFFFFFFFFF-n : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i quica_Overlap(a.i,n.i,b.i,m.i)
 If n>0 And m>0 And a<b+m And b<a+n : ProcedureReturn 1 : EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i quica_Ready(*s.QuicHandshakeAck)
 If quica_Span(*s,SizeOf(QuicHandshakeAck))=0 : ProcedureReturn #QUIC_ACK_ARGUMENT : EndIf
 If *s\phase<>1 : ProcedureReturn #QUIC_ACK_STATE : EndIf
 ProcedureReturn 0
EndProcedure
; Caller owns immutable context/storage between API calls. Entries are pairs
; of native integers (inclusive low,high), descending and disjoint. No pruning:
; exceeding1..64 range slots is a loud resource refusal, not forgotten history.
Procedure.i QuicHandshakeAckInit(*s.QuicHandshakeAck,level.i,entries.i,capacity.i)
 If level<>0 And level<>2 : ProcedureReturn #QUIC_ACK_ARGUMENT : EndIf
 If capacity<1 Or capacity>64 : ProcedureReturn #QUIC_ACK_ARGUMENT : EndIf
 If quica_Span(*s,SizeOf(QuicHandshakeAck))=0 Or quica_Span(entries,capacity*16)=0 : ProcedureReturn #QUIC_ACK_ARGUMENT : EndIf
 If quica_Overlap(*s,SizeOf(QuicHandshakeAck),entries,capacity*16) : ProcedureReturn #QUIC_ACK_ARGUMENT : EndIf
 *s\phase=1 : *s\level=level : *s\entries=entries : *s\capacity=capacity
 *s\count=0 : *s\demand=0 : *s\pending=0 : ProcedureReturn 0
EndProcedure
; Read-only duplicate lookup. It never marks a packet processed.
Procedure.i QuicHandshakeAckSeen(*s.QuicHandshakeAck,pn.i)
 Define rc.i,i.i,p.i
 rc=quica_Ready(*s) : If rc<0 : ProcedureReturn rc : EndIf
 If pn<0 Or pn>#QUIC_INTEGER_MAX : ProcedureReturn #QUIC_ACK_ARGUMENT : EndIf
 For i=0 To *s\count-1
  p=*s\entries+i*16
  If pn>=PeekI(p) And pn<=PeekI(p+8) : ProcedureReturn 1 : EndIf
 Next
 ProcedureReturn 0
EndProcedure
; Returns1 for new receipt,0 for duplicate. Duplicate eliciting packets still
; request an ACK. A non-eliciting packet must not create a new ACK demand.
Procedure.i QuicHandshakeAckRecord(*s.QuicHandshakeAck,pn.i,eliciting.i)
 Define rc.i,i.i,j.i,p.i,lo.i,hi.i,at.i,added.i
 rc=quica_Ready(*s) : If rc<0 : ProcedureReturn rc : EndIf
 If pn<0 Or pn>#QUIC_INTEGER_MAX Or eliciting<0 Or eliciting>1 : ProcedureReturn #QUIC_ACK_ARGUMENT : EndIf
 If eliciting<>0 And *s\demand=$7FFFFFFFFFFFFFFF : ProcedureReturn #QUIC_ACK_LIMIT : EndIf
 at=*s\count : added=1
 For i=0 To *s\count-1
  p=*s\entries+i*16 : lo=PeekI(p) : hi=PeekI(p+8)
  If pn>hi+1 : at=i : Break : EndIf
  If pn>=lo-1
   If pn>=lo And pn<=hi : added=0 : EndIf
   If pn>hi : PokeI(p+8,pn) : EndIf
   If pn<lo : PokeI(p,pn) : EndIf
   If i+1<*s\count
    If PeekI(p)<=PeekI(p+24)+1
     PokeI(p,PeekI(p+16))
     For j=i+1 To *s\count-2
      PokeI(*s\entries+j*16,PeekI(*s\entries+(j+1)*16))
      PokeI(*s\entries+j*16+8,PeekI(*s\entries+(j+1)*16+8))
     Next
     *s\count=*s\count-1
    EndIf
   EndIf
   at=-1 : Break
  EndIf
 Next
 If at>=0
  If *s\count=*s\capacity : ProcedureReturn #QUIC_ACK_LIMIT : EndIf
  For j=*s\count To at+1 Step -1
   PokeI(*s\entries+j*16,PeekI(*s\entries+(j-1)*16))
   PokeI(*s\entries+j*16+8,PeekI(*s\entries+(j-1)*16+8))
  Next
  PokeI(*s\entries+at*16,pn) : PokeI(*s\entries+at*16+8,pn) : *s\count=*s\count+1
 EndIf
 If eliciting<>0 : *s\demand=*s\demand+1 : *s\pending=1 : EndIf
 ProcedureReturn added
EndProcedure
; ACK type2, zero delay for handshake spaces, no ECN reporting yet. Writes
; atomically after capacity checks and returns bytes (0 if no receipts).
; Snapshot demand token is passed to Sent ONLY after actual send acceptance.
Procedure.i QuicHandshakeAckWrite(*s.QuicHandshakeAck,dst.i,capacity.i,token.i)
 Define rc.i,n.i,i.i,p.i,lo.i,hi.i,prev.i,need.i
 rc=quica_Ready(*s) : If rc<0 : ProcedureReturn rc : EndIf
 If quica_Span(dst,capacity)=0 Or quica_Span(token,8)=0 : ProcedureReturn #QUIC_ACK_ARGUMENT : EndIf
 If quica_Overlap(dst,capacity,token,8) Or quica_Overlap(dst,capacity,*s,SizeOf(QuicHandshakeAck)) Or quica_Overlap(token,8,*s,SizeOf(QuicHandshakeAck)) : ProcedureReturn #QUIC_ACK_ARGUMENT : EndIf
 If quica_Overlap(dst,capacity,*s\entries,*s\capacity*16) Or quica_Overlap(token,8,*s\entries,*s\capacity*16) : ProcedureReturn #QUIC_ACK_ARGUMENT : EndIf
 If *s\count=0 : PokeI(token,*s\demand) : ProcedureReturn 0 : EndIf
 need=2+QuicIntegerSize(PeekI(*s\entries+8))+QuicIntegerSize(*s\count-1)
 prev=0
 For i=0 To *s\count-1
  p=*s\entries+i*16 : lo=PeekI(p) : hi=PeekI(p+8)
  need=need+QuicIntegerSize(hi-lo)
  If i>0 : need=need+QuicIntegerSize(prev-hi-2) : EndIf
  prev=lo
 Next
 If capacity<need : ProcedureReturn #QUIC_ACK_CAPACITY : EndIf
 PokeA(dst,2) : n=1
 n=n+QuicIntegerWrite(PeekI(*s\entries+8),0,dst+n,capacity-n)
 PokeA(dst+n,0) : n=n+1
 n=n+QuicIntegerWrite(*s\count-1,0,dst+n,capacity-n)
 For i=0 To *s\count-1
  p=*s\entries+i*16 : lo=PeekI(p) : hi=PeekI(p+8)
  If i>0 : n=n+QuicIntegerWrite(prev-hi-2,0,dst+n,capacity-n) : EndIf
  n=n+QuicIntegerWrite(hi-lo,0,dst+n,capacity-n) : prev=lo
 Next
 PokeI(token,*s\demand) : ProcedureReturn n
EndProcedure
; A stale send completion cannot clear newer eliciting demand. Non-eliciting
; receipts do not change the token, avoiding ACK-only response loops.
; No receipt/retry timer or packet protection is supplied by this module.
Procedure.i QuicHandshakeAckSent(*s.QuicHandshakeAck,token.i)
 Define rc.i
 rc=quica_Ready(*s) : If rc<0 : ProcedureReturn rc : EndIf
 If token<0 Or token>*s\demand : ProcedureReturn #QUIC_ACK_ARGUMENT : EndIf
 If token=*s\demand : *s\pending=0 : ProcedureReturn 1 : EndIf
 ProcedureReturn 0
EndProcedure

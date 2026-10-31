; SPDX-License-Identifier: MIT
; Independent RFC9000 sections12.3,13.1,13.2.5,18.2 application bookkeeping.
; Serialized owner; no authentication, frame effects, clocks or I/O here.
; Inline range storage belongs to this descriptor for its whole lifetime.
XIncludeFile "Anvil/Network/quic_packet_ack.pbi"
#QUIC_APPLICATION_ARGUMENT=-3591
#QUIC_APPLICATION_STATE=-3592
#QUIC_APPLICATION_LIMIT=-3593
Structure QuicApplicationState
 phase.i
 largestAuthenticated.i
 largestProcessed.i
 receivedAt.i
 nextNumber.i
 ack.QuicPacketAck
 ranges.i[128]
EndStructure
Procedure.i quicas_Span(p.i,n.i)
 ProcedureReturn Bool(p>0 And n>=0 And p<=$7FFFFFFFFFFFFFFF-n)
EndProcedure
Procedure.i quicas_Ready(*s.QuicApplicationState)
 If quicas_Span(*s,SizeOf(QuicApplicationState))=0 : ProcedureReturn #QUIC_APPLICATION_ARGUMENT : EndIf
 If *s\phase<>1 : ProcedureReturn #QUIC_APPLICATION_STATE : EndIf
 ProcedureReturn 0
EndProcedure
; Fresh zeroed descriptor only. Never reset numbering while its keys survive.
Procedure.i QuicApplicationStateInit(*s.QuicApplicationState)
 Define i.i,rc.i
 If quicas_Span(*s,SizeOf(QuicApplicationState))=0 : ProcedureReturn #QUIC_APPLICATION_ARGUMENT : EndIf
 If *s\phase<>0 : ProcedureReturn #QUIC_APPLICATION_STATE : EndIf
 For i=0 To SizeOf(QuicApplicationState)-1 : PokeA(*s+i,0) : Next
 rc=QuicPacketAckInit(@*s\ack,4,@*s\ranges,64) : If rc<>0 : ProcedureReturn rc : EndIf
 *s\largestAuthenticated=-1 : *s\largestProcessed=-1 : *s\phase=1
 ProcedureReturn 0
EndProcedure
; Reserve BEFORE encrypting. Failure/cancellation/send refusal never returns a
; reservation to the pool. Key updates retain this state and its numbering.
Procedure.i QuicApplicationNumberReserve(*s.QuicApplicationState)
 Define rc.i,n.i
 rc=quicas_Ready(*s) : If rc<0 : ProcedureReturn rc : EndIf
 n=*s\nextNumber
 If n<0 Or n>#QUIC_INTEGER_MAX : ProcedureReturn #QUIC_APPLICATION_LIMIT : EndIf
 *s\nextNumber=n+1 : ProcedureReturn n
EndProcedure
; Call only AFTER successful packet authentication. Returns1 if already fully
; processed,0 otherwise. This does not mark receipt or apply any frame twice.
Procedure.i QuicApplicationAuthenticated(*s.QuicApplicationState,pn.i)
 Define rc.i
 rc=quicas_Ready(*s) : If rc<0 : ProcedureReturn rc : EndIf
 rc=QuicPacketAckSeen(@*s\ack,pn) : If rc<0 : ProcedureReturn rc : EndIf
 If pn>*s\largestAuthenticated : *s\largestAuthenticated=pn : EndIf
 ProcedureReturn rc
EndProcedure
; Caller certifies this PN was authenticated and every frame successfully
; processed. The upper bound alone is NOT evidence of either condition.
; receivedAt is caller's controlled receipt time in monotonic microseconds.
Procedure.i QuicApplicationProcessed(*s.QuicApplicationState,pn.i,eliciting.i,receivedAt.i)
 Define rc.i
 rc=quicas_Ready(*s) : If rc<0 : ProcedureReturn rc : EndIf
 If pn<0 Or pn>*s\largestAuthenticated Or receivedAt<0 : ProcedureReturn #QUIC_APPLICATION_ARGUMENT : EndIf
 rc=QuicPacketAckRecord(@*s\ack,pn,eliciting) : If rc<0 : ProcedureReturn rc : EndIf
 If pn>*s\largestProcessed
  *s\largestProcessed=pn : *s\receivedAt=receivedAt
 EndIf
 ProcedureReturn rc
EndProcedure
; Out-of-order/duplicate receipts do not replace the largest PN's timestamp.
; Exponent is our advertised ACK-delay exponent, not the peer's value.
Procedure.i QuicApplicationAckDelay(*s.QuicApplicationState,now.i,exponent.i)
 Define rc.i,delay.i
 rc=quicas_Ready(*s) : If rc<0 : ProcedureReturn rc : EndIf
 If *s\largestProcessed<0 : ProcedureReturn #QUIC_APPLICATION_STATE : EndIf
 If now<*s\receivedAt Or exponent<0 Or exponent>20 : ProcedureReturn #QUIC_APPLICATION_ARGUMENT : EndIf
 delay=(now-*s\receivedAt)>>exponent
 If delay>#QUIC_INTEGER_MAX : ProcedureReturn #QUIC_APPLICATION_LIMIT : EndIf
 ProcedureReturn delay
EndProcedure
; Output/token cannot overlap ANY part of this owner, including its counters.
Procedure.i QuicApplicationAckWrite(*s.QuicApplicationState,dst.i,capacity.i,token.i,now.i,exponent.i)
 Define delay.i
 delay=QuicApplicationAckDelay(*s,now,exponent) : If delay<0 : ProcedureReturn delay : EndIf
 If quicas_Span(dst,capacity)=0 Or quicas_Span(token,8)=0 : ProcedureReturn #QUIC_APPLICATION_ARGUMENT : EndIf
 If dst<*s+SizeOf(QuicApplicationState) And *s<dst+capacity : ProcedureReturn #QUIC_APPLICATION_ARGUMENT : EndIf
 If token<*s+SizeOf(QuicApplicationState) And *s<token+8 : ProcedureReturn #QUIC_APPLICATION_ARGUMENT : EndIf
 ProcedureReturn QuicPacketAckWriteDelay(@*s\ack,dst,capacity,token,delay)
EndProcedure

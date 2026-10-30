; Per-interface MLD compatibility and querier timing policy. Protocol facts
; independently implemented from RFC 9777 sections 8.2.1 and 9.12.
; Compose ipv6_mld.pbi first. Zero-fill one context per interface. Serialized.
; Call Tick even without traffic. A revision change cancels every pending
; query response and retransmission on this interface. Callers must apply it
; before emitting another report. This policy does not own per-group timers.
#IPV6_MLD_POLICY_ARGUMENT = -770
#IPV6_MLD_POLICY_STALE = -771
Structure IPv6MldInterface
 generation.i
 revision.i
 version.i
 olderUntil.i
 robustness.i
 interval.i
 response.i
 lastNow.i
EndStructure

Procedure.i IPv6MldTimeValid(now.i)
 If now<0 Or now>$7FFFFFFEFFFFFFFF : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i IPv6MldInterfaceInit(*state.IPv6MldInterface,generation.i,now.i)
 Define i.i
 If IPv6MldSpanValid(*state,SizeOf(IPv6MldInterface))=0 Or IPv6MldTimeValid(now)=0 : ProcedureReturn #IPV6_MLD_POLICY_ARGUMENT : EndIf
 If generation<=0 Or generation<=*state\generation : ProcedureReturn #IPV6_MLD_POLICY_STALE : EndIf
 For i=0 To SizeOf(IPv6MldInterface)-1 : PokeA(*state+i,0) : Next
 *state\generation=generation : *state\revision=1 : *state\version=2
 *state\robustness=2 : *state\interval=125000 : *state\response=10000
 *state\lastNow=now
 ProcedureReturn 0
EndProcedure

Procedure.i IPv6MldInterfaceTick(*state.IPv6MldInterface,generation.i,now.i)
 If IPv6MldSpanValid(*state,SizeOf(IPv6MldInterface))=0 Or IPv6MldTimeValid(now)=0 : ProcedureReturn #IPV6_MLD_POLICY_ARGUMENT : EndIf
 If generation<=0 Or generation<>*state\generation : ProcedureReturn #IPV6_MLD_POLICY_STALE : EndIf
 If now<*state\lastNow : ProcedureReturn #IPV6_MLD_POLICY_ARGUMENT : EndIf
 If *state\version=1 And now>=*state\olderUntil
  *state\version=2 : *state\olderUntil=0 : *state\revision=*state\revision+1
 EndIf
 *state\lastNow=now
 ProcedureReturn *state\version
EndProcedure

; Input must already be accepted by the interface's destination filter.
; Invalid packets, stale generations and backwards time leave state unchanged.
; Valid v1 general queries start/refresh compatibility. Specific v1 queries do
; not switch the entire interface. V2 queries cannot end an active v1 interval.
; Times are milliseconds; the wire QQI is seconds and is converted here.
Procedure.i IPv6MldInterfaceQuery(*state.IPv6MldInterface,generation.i,now.i,packet.i,bytes.i)
 Define query.IPv6MldQueryView
 Define rc.i,general.i
 If IPv6MldSpanValid(*state,SizeOf(IPv6MldInterface))=0 Or IPv6MldTimeValid(now)=0 : ProcedureReturn #IPV6_MLD_POLICY_ARGUMENT : EndIf
 If generation<=0 Or generation<>*state\generation : ProcedureReturn #IPV6_MLD_POLICY_STALE : EndIf
 If now<*state\lastNow : ProcedureReturn #IPV6_MLD_POLICY_ARGUMENT : EndIf
 If IPv6MldSpanValid(packet,bytes)=0 : ProcedureReturn #IPV6_MLD_POLICY_ARGUMENT : EndIf
 If *state<packet+bytes And packet<*state+SizeOf(IPv6MldInterface) : ProcedureReturn #IPV6_MLD_POLICY_ARGUMENT : EndIf
 rc=IPv6MldQuery(packet,bytes,@query)
 If rc<>0 : ProcedureReturn rc : EndIf
 rc=IPv6MldInterfaceTick(*state,generation,now)
 If rc<0 : ProcedureReturn rc : EndIf
 general=IPv6AddressUnspecified(query\group)
 If query\version=2
  ; Keep the querier values, with specified defaults for zero wire values.
  *state\robustness=query\robustness
  If *state\robustness=0 : *state\robustness=2 : EndIf
  *state\interval=query\interval*1000
  If *state\interval=0 : *state\interval=125000 : EndIf
 EndIf
 If general<>0
  *state\response=query\maxDelay
  If query\version=1
   If *state\version<>1
    *state\version=1 : *state\revision=*state\revision+1
   EndIf
   *state\olderUntil=now+*state\robustness*(*state\interval)+*state\response
  EndIf
 EndIf
 ProcedureReturn *state\version
EndProcedure

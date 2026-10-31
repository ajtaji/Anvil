; Any-source multicast group scheduler. Independently implemented protocol facts
; from RFC 9777 sections 6.1-6.3 and 8.2, RFC 2710 section 4.
; Compose ipv6_mld_policy.pbi first. One zero-filled context per group, owned
; source storage for its lifetime, serialized calls. No RX pointer is retained.
; Caller filters/validates received packets and supplies randomized delays.
; Sync every interface generation/revision change before emitting packets.
#IPV6_MLD_GROUP_ARGUMENT = -780
#IPV6_MLD_GROUP_STALE = -781
#IPV6_MLD_GROUP_FAILED = -782
Structure IPv6MldGroupState
 generation.i
 revision.i
 version.i
 joined.i
 changeCount.i
 changeDue.i
 changeSerial.i
 queryDue.i
 querySerial.i
 queryCount.i
 lastReporter.i
 serial.i
 awaiting.i
 flightKind.i
 flightSerial.i
 flightJoined.i
 flightVersion.i
 lastNow.i
 failed.i
 sources.i
 capacity.i
 group.IPv6AddressStorage
EndStructure
Procedure.i ipv6mld_GroupValid(*s.IPv6MldGroupState,generation.i,revision.i,now.i)
 If IPv6MldSpanValid(*s,SizeOf(IPv6MldGroupState))=0 Or IPv6MldTimeValid(now)=0 : ProcedureReturn #IPV6_MLD_GROUP_ARGUMENT : EndIf
 If generation<=0 Or generation<>*s\generation Or revision<>*s\revision : ProcedureReturn #IPV6_MLD_GROUP_STALE : EndIf
 If now<*s\lastNow : ProcedureReturn #IPV6_MLD_GROUP_ARGUMENT : EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i IPv6MldGroupInit(*s.IPv6MldGroupState,generation.i,revision.i,version.i,group.i,storage.i,capacity.i,now.i)
 Define i.i
 If IPv6MldSpanValid(*s,SizeOf(IPv6MldGroupState))=0 Or IPv6MldTimeValid(now)=0 : ProcedureReturn #IPV6_MLD_GROUP_ARGUMENT : EndIf
 If generation<=0 Or generation<=*s\generation Or revision<=0 : ProcedureReturn #IPV6_MLD_GROUP_STALE : EndIf
 If version<>1 And version<>2 : ProcedureReturn #IPV6_MLD_GROUP_ARGUMENT : EndIf
 If capacity<16 Or capacity>1424 Or (capacity % 16)<>0 : ProcedureReturn #IPV6_MLD_GROUP_ARGUMENT : EndIf
 If IPv6MldSpanValid(storage,capacity)=0 Or IPv6MldSpanValid(group,16)=0 : ProcedureReturn #IPV6_MLD_GROUP_ARGUMENT : EndIf
 If *s<storage+capacity And storage<*s+SizeOf(IPv6MldGroupState) : ProcedureReturn #IPV6_MLD_GROUP_ARGUMENT : EndIf
 If *s<group+16 And group<*s+SizeOf(IPv6MldGroupState) : ProcedureReturn #IPV6_MLD_GROUP_ARGUMENT : EndIf
 If storage<group+16 And group<storage+capacity : ProcedureReturn #IPV6_MLD_GROUP_ARGUMENT : EndIf
 If ipv6mld_Group(group)=0 : ProcedureReturn #IPV6_MLD_GROUP_ARGUMENT : EndIf
 For i=0 To SizeOf(IPv6MldGroupState)-1 : PokeA(*s+i,0) : Next
 *s\generation=generation : *s\revision=revision : *s\version=version
 *s\sources=storage : *s\capacity=capacity : *s\queryDue=-1 : *s\lastNow=now
 For i=0 To 15 : PokeA(@*s\group+i,PeekA(group+i)) : Next
 For i=0 To capacity-1 : PokeA(storage+i,0) : Next
 ProcedureReturn 0
EndProcedure

; Same interface generation; newer compatibility revision cancels pending work.
; An interface generation change requires Init and device membership renewal.
Procedure.i IPv6MldGroupSync(*s.IPv6MldGroupState,generation.i,revision.i,version.i,now.i)
 Define i.i,rc.i
 If IPv6MldSpanValid(*s,SizeOf(IPv6MldGroupState))=0 : ProcedureReturn #IPV6_MLD_GROUP_ARGUMENT : EndIf
 rc=ipv6mld_GroupValid(*s,generation,*s\revision,now) : If rc<>0 : ProcedureReturn rc : EndIf
 If revision<*s\revision Or revision<=0 : ProcedureReturn #IPV6_MLD_GROUP_STALE : EndIf
 If version<>1 And version<>2 : ProcedureReturn #IPV6_MLD_GROUP_ARGUMENT : EndIf
 If revision=*s\revision
  If version<>*s\version : ProcedureReturn #IPV6_MLD_GROUP_STALE : EndIf
 Else
  *s\revision=revision : *s\version=version : *s\changeCount=0
  *s\queryDue=-1 : *s\queryCount=0 : *s\awaiting=0 : *s\lastReporter=0
  *s\changeSerial=*s\changeSerial+1 : *s\querySerial=*s\querySerial+1
  For i=0 To *s\capacity-1 : PokeA(*s\sources+i,0) : Next
 EndIf
 *s\lastNow=now : ProcedureReturn 0
EndProcedure
Procedure.i IPv6MldGroupChange(*s.IPv6MldGroupState,generation.i,revision.i,now.i,joined.i,robustness.i)
 Define rc.i,i.i
 rc=ipv6mld_GroupValid(*s,generation,revision,now) : If rc<>0 : ProcedureReturn rc : EndIf
 If joined<0 Or joined>1 Or robustness<1 Or robustness>7 : ProcedureReturn #IPV6_MLD_GROUP_ARGUMENT : EndIf
 If *s\failed<>0 : ProcedureReturn #IPV6_MLD_GROUP_FAILED : EndIf
 If joined<>*s\joined
  *s\joined=joined : *s\changeSerial=*s\changeSerial+1
  *s\changeCount=robustness : *s\changeDue=now
  If *s\version=1
   *s\changeCount=2
   If joined=0
    ; Always send Done: suppressing it requires a user-disableable option.
    *s\changeCount=1
   EndIf
  EndIf
  If joined=0
   *s\queryDue=-1 : *s\queryCount=0 : *s\querySerial=*s\querySerial+1
   For i=0 To *s\capacity-1 : PokeA(*s\sources+i,0) : Next
  EndIf
 EndIf
 *s\lastNow=now : ProcedureReturn 0
EndProcedure

; query is a successfully validated IPv6MldQueryView. Delay is independently
; randomized for this group, 1..maxDelay (zero only for zero maxDelay).
Procedure.i IPv6MldGroupQuery(*s.IPv6MldGroupState,generation.i,revision.i,now.i,*query.IPv6MldQueryView,delay.i)
 Define rc.i,n.i,due.i,i.i
 rc=ipv6mld_GroupValid(*s,generation,revision,now) : If rc<>0 : ProcedureReturn rc : EndIf
 If *s\failed<>0 : ProcedureReturn #IPV6_MLD_GROUP_FAILED : EndIf
 If IPv6MldSpanValid(*query,SizeOf(IPv6MldQueryView))=0 : ProcedureReturn #IPV6_MLD_GROUP_ARGUMENT : EndIf
 If *query<*s+SizeOf(IPv6MldGroupState) And *s<*query+SizeOf(IPv6MldQueryView) : ProcedureReturn #IPV6_MLD_GROUP_ARGUMENT : EndIf
 If *query<*s\sources+*s\capacity And *s\sources<*query+SizeOf(IPv6MldQueryView) : ProcedureReturn #IPV6_MLD_GROUP_ARGUMENT : EndIf
 If IPv6MldSpanValid(*query\group,16)=0 : ProcedureReturn #IPV6_MLD_GROUP_ARGUMENT : EndIf
 If *query\maxDelay<0 Or *query\maxDelay>8387584 Or delay<0 Or delay>*query\maxDelay : ProcedureReturn #IPV6_MLD_GROUP_ARGUMENT : EndIf
 If delay=0 And *query\maxDelay<>0 : ProcedureReturn #IPV6_MLD_GROUP_ARGUMENT : EndIf
 If *query\sourceCount<0 Or *query\sourceCount>89 : ProcedureReturn #IPV6_MLD_GROUP_ARGUMENT : EndIf
 If *s\joined=0 : ProcedureReturn 0 : EndIf
 If IPv6AddressUnspecified(*query\group)=0 And ipv6mld_SameAddress(*query\group,@*s\group)=0 : ProcedureReturn 0 : EndIf
 n=*query\sourceCount
 If *s\version=1 : n=0 : EndIf
 If *s\queryDue>=0 And *s\queryCount=0 : n=0 : EndIf
 If n>0
  i=*s\queryCount : If *s\queryDue<0 : i=0 : EndIf
  rc=IPv6MldMergeSources(*s\sources,*s\capacity,i,*query\sources,n)
  If rc<0 : ProcedureReturn rc : EndIf
  n=rc
 Else
  For i=0 To *s\capacity-1 : PokeA(*s\sources+i,0) : Next
 EndIf
 due=now+delay
 If *s\queryDue<0 Or due<*s\queryDue : *s\queryDue=due : EndIf
 *s\queryCount=n : *s\querySerial=*s\querySerial+1
 *s\lastNow=now : ProcedureReturn 0
EndProcedure

; Returns a complete IPv6 packet or zero. Capture s.awaiting after a positive
; result, then acknowledge exactly that token. Output storage is caller-owned.
Procedure.i IPv6MldGroupStep(*s.IPv6MldGroupState,generation.i,revision.i,now.i,source.i,out.i,capacity.i)
 Define rc.i,kind.i,mode.i
 rc=ipv6mld_GroupValid(*s,generation,revision,now) : If rc<>0 : ProcedureReturn rc : EndIf
 If *s\failed<>0 : ProcedureReturn #IPV6_MLD_GROUP_FAILED : EndIf
 If *s\awaiting<>0 : ProcedureReturn 0 : EndIf
 If IPv6MldSpanValid(out,capacity)=0 : ProcedureReturn #IPV6_MLD_GROUP_ARGUMENT : EndIf
 If out<*s+SizeOf(IPv6MldGroupState) And *s<out+capacity : ProcedureReturn #IPV6_MLD_GROUP_ARGUMENT : EndIf
 If out<*s\sources+*s\capacity And *s\sources<out+capacity : ProcedureReturn #IPV6_MLD_GROUP_ARGUMENT : EndIf
 kind=0
 If *s\changeCount>0 And now>=*s\changeDue : kind=1 : EndIf
 If *s\joined<>0 And *s\queryDue>=0 And now>=*s\queryDue
  If kind=0 Or *s\queryDue<*s\changeDue : kind=2 : EndIf
 EndIf
 If kind=0 : *s\lastNow=now : ProcedureReturn 0 : EndIf
 mode=2
 If kind=1
  mode=3 : If *s\joined<>0 : mode=4 : EndIf
 EndIf
 If kind=2 And *s\version=2 And *s\queryCount>0
  rc=IPv6MldSourceReport(out,capacity,source,@*s\group,*s\sources,*s\queryCount)
 Else
  rc=IPv6MldReport(out,capacity,source,@*s\group,*s\version,mode)
 EndIf
 If rc<0 : ProcedureReturn rc : EndIf
 *s\serial=*s\serial+1 : *s\awaiting=*s\serial
 *s\flightKind=kind : *s\flightVersion=*s\version : *s\flightJoined=*s\joined
 *s\flightSerial=*s\changeSerial : If kind=2 : *s\flightSerial=*s\querySerial : EndIf
 *s\lastNow=now : ProcedureReturn rc
EndProcedure

; result=1 confirmed driver completion; 0 definitely NOT submitted, not pending.
; Negative/ambiguous completion fails the membership until a new generation Init.
; Queue acceptance alone is not an acknowledgement. Retry delay is randomized
; 1..1000 ms for v2, 1..10000 ms for v1. A pending TX does not consume a repeat.
Procedure.i IPv6MldGroupSent(*s.IPv6MldGroupState,generation.i,revision.i,now.i,token.i,result.i,retryDelay.i)
 Define rc.i,i.i,limit.i
 rc=ipv6mld_GroupValid(*s,generation,revision,now) : If rc<>0 : ProcedureReturn rc : EndIf
 If token<=0 Or token<>*s\awaiting : ProcedureReturn #IPV6_MLD_GROUP_STALE : EndIf
 limit=1000 : If *s\version=1 : limit=10000 : EndIf
 If result>1 Or retryDelay<1 Or retryDelay>limit : ProcedureReturn #IPV6_MLD_GROUP_ARGUMENT : EndIf
 *s\awaiting=0 : *s\lastNow=now
 If result<0 : *s\failed=1 : ProcedureReturn #IPV6_MLD_GROUP_FAILED : EndIf
 If result=0 : ProcedureReturn 0 : EndIf
 If *s\flightJoined<>0 And *s\joined<>0 : *s\lastReporter=1 : EndIf
 If *s\flightKind=1 And *s\flightSerial=*s\changeSerial
  *s\changeCount=*s\changeCount-1 : *s\changeDue=now+retryDelay
 EndIf
 If *s\flightKind=2 And *s\flightSerial=*s\querySerial
  *s\queryDue=-1 : *s\queryCount=0
  For i=0 To *s\capacity-1 : PokeA(*s\sources+i,0) : Next
 EndIf
 ProcedureReturn 0
EndProcedure

; Caller has validated another node's v1 Report for exactly this joined group.
; Do not call for looped-back local reports. V2 reports do not suppress our work.
Procedure.i IPv6MldGroupHeardV1(*s.IPv6MldGroupState,generation.i,revision.i,now.i)
 Define rc.i,i.i
 rc=ipv6mld_GroupValid(*s,generation,revision,now) : If rc<>0 : ProcedureReturn rc : EndIf
 If *s\version=1 And *s\joined<>0
  *s\lastReporter=0 : *s\changeCount=0 : *s\changeSerial=*s\changeSerial+1
  *s\queryDue=-1 : *s\queryCount=0 : *s\querySerial=*s\querySerial+1
  For i=0 To *s\capacity-1 : PokeA(*s\sources+i,0) : Next
 EndIf
 *s\lastNow=now : ProcedureReturn 0
EndProcedure

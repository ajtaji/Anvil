; Shared link-local IPv6 host lifecycle. Compose endpoint, MLD codec/policy/
; group scheduler first. Caller installs all-nodes and solicited-node device
; filters before Init, owns source storage, excludes local hardware loopback,
; supplies random delays and confirms each submitted frame's driver receipt.
; No device calls, RX pointers, implicit retransmission or synchronous waits.
; Protocol facts independently composed from RFC 4862 section 5.4,
; RFC 3590 section 4, RFC 9777 sections 6 and 8.
#IPV6_HOST_JOINING=1
#IPV6_HOST_DAD=2
#IPV6_HOST_READY=3
#IPV6_HOST_DUPLICATE=4
#IPV6_HOST_FAILED=5
#IPV6_HOST_ARGUMENT=-800
#IPV6_HOST_STALE=-801
Structure IPv6Host
 generation.i
 phase.i
 lastNow.i
 delay.i
 serial.i
 awaiting.i
 flight.i
 flightRevision.i
 flightToken.i
 endpoint.IPv6Endpoint
 policy.IPv6MldInterface
 membership.IPv6MldGroupState
EndStructure
Procedure.i ipv6host_Valid(*s.IPv6Host,generation.i,now.i)
 If IPv6MldSpanValid(*s,SizeOf(IPv6Host))=0 Or IPv6MldTimeValid(now)=0 : ProcedureReturn #IPV6_HOST_ARGUMENT : EndIf
 If generation<=0 Or generation<>*s\generation : ProcedureReturn #IPV6_HOST_STALE : EndIf
 If now<*s\lastNow : ProcedureReturn #IPV6_HOST_ARGUMENT : EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i IPv6HostInit(*s.IPv6Host,generation.i,address.i,mac.i,storage.i,capacity.i,now.i,delay.i)
 Define group.IPv6AddressStorage
 Define rc.i,i.i
 If IPv6MldSpanValid(*s,SizeOf(IPv6Host))=0 Or IPv6MldTimeValid(now)=0 : ProcedureReturn #IPV6_HOST_ARGUMENT : EndIf
 If generation<=0 Or generation<=*s\generation : ProcedureReturn #IPV6_HOST_STALE : EndIf
 If IPv6MldSpanValid(address,16)=0 Or IPv6MldSpanValid(mac,6)=0 : ProcedureReturn #IPV6_HOST_ARGUMENT : EndIf
 If capacity<16 Or capacity>1424 Or (capacity % 16)<>0 : ProcedureReturn #IPV6_HOST_ARGUMENT : EndIf
 If IPv6MldSpanValid(storage,capacity)=0 Or delay<0 Or delay>1000 : ProcedureReturn #IPV6_HOST_ARGUMENT : EndIf
 If IPv6EndpointSpansSeparate(*s,SizeOf(IPv6Host),storage,capacity)=0 : ProcedureReturn #IPV6_HOST_ARGUMENT : EndIf
 If IPv6EndpointSpansSeparate(*s,SizeOf(IPv6Host),address,16)=0 Or IPv6EndpointSpansSeparate(*s,SizeOf(IPv6Host),mac,6)=0 : ProcedureReturn #IPV6_HOST_ARGUMENT : EndIf
 If IPv6EndpointSpansSeparate(storage,capacity,address,16)=0 Or IPv6EndpointSpansSeparate(storage,capacity,mac,6)=0 : ProcedureReturn #IPV6_HOST_ARGUMENT : EndIf
 If IPv6MldLinkLocal(address)=0 Or (PeekA(mac)&1)<>0 : ProcedureReturn #IPV6_HOST_ARGUMENT : EndIf
 rc=0 : For i=0 To 5 : rc=rc|PeekA(mac+i) : Next
 If rc=0 : ProcedureReturn #IPV6_HOST_ARGUMENT : EndIf
 For i=0 To SizeOf(IPv6Host)-1 : PokeA(*s+i,0) : Next
 *s\generation=generation : *s\lastNow=now : *s\delay=delay
 rc=IPv6EndpointInit(@*s\endpoint,generation,address,mac,now,delay,1000,1)
 If rc=0 : rc=IPv6MldInterfaceInit(@*s\policy,generation,now) : EndIf
 If rc=0 : rc=IPv6SolicitedNode(address,@group) : EndIf
 If rc=0 : rc=IPv6MldGroupInit(@*s\membership,generation,1,2,@group,storage,capacity,now) : EndIf
 If rc=0 : rc=IPv6MldGroupChange(@*s\membership,generation,1,now,1,2) : EndIf
 If rc<>0 : *s\phase=#IPV6_HOST_FAILED : ProcedureReturn rc : EndIf
 *s\phase=#IPV6_HOST_JOINING : ProcedureReturn 0
EndProcedure
Procedure.i ipv6host_Output(*s.IPv6Host,out.i,capacity.i)
 If capacity<90 Or capacity>1514 Or IPv6MldSpanValid(out,capacity)=0 : ProcedureReturn #IPV6_HOST_ARGUMENT : EndIf
 If IPv6EndpointSpansSeparate(*s,SizeOf(IPv6Host),out,capacity)=0 : ProcedureReturn #IPV6_HOST_ARGUMENT : EndIf
 If IPv6EndpointSpansSeparate(*s\membership\sources,*s\membership\capacity,out,capacity)=0 : ProcedureReturn #IPV6_HOST_ARGUMENT : EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i ipv6host_Sync(*s.IPv6Host,now.i)
 Define rc.i
 rc=IPv6MldInterfaceTick(@*s\policy,*s\generation,now)
 If rc<0 : ProcedureReturn rc : EndIf
 rc=IPv6MldGroupSync(@*s\membership,*s\generation,*s\policy\revision,*s\policy\version,now)
 *s\lastNow=now : ProcedureReturn rc
EndProcedure
; Schedule a current-state report, including after a source-address change.
; Keep query and membership revisions separate from an outstanding frame.
Procedure ipv6host_Refresh(*s.IPv6Host,now.i)
 *s\membership\queryDue=now : *s\membership\queryCount=0
 *s\membership\querySerial=*s\membership\querySerial+1
EndProcedure
Procedure.i IPv6HostStep(*s.IPv6Host,generation.i,now.i,out.i,capacity.i)
 Define zero.IPv6AddressStorage
 Define rc.i,n.i,source.i,i.i
 rc=ipv6host_Valid(*s,generation,now) : If rc<>0 : ProcedureReturn rc : EndIf
 rc=ipv6host_Output(*s,out,capacity) : If rc<>0 : ProcedureReturn rc : EndIf
 rc=ipv6host_Sync(*s,now) : If rc<>0 : ProcedureReturn rc : EndIf
 If *s\phase=#IPV6_HOST_FAILED Or *s\phase=#IPV6_HOST_DUPLICATE : ProcedureReturn 0 : EndIf
 If *s\awaiting<>0 : ProcedureReturn 0 : EndIf
 If *s\phase=#IPV6_HOST_DAD
  rc=IPv6EndpointStep(@*s\endpoint,generation,now,out,capacity)
  If rc<0 : *s\phase=#IPV6_HOST_FAILED : ProcedureReturn rc : EndIf
  If rc>0
   *s\flight=2 : *s\serial=*s\serial+1 : *s\awaiting=*s\serial
   ProcedureReturn rc
  EndIf
  If *s\endpoint\state=#IPV6_EP_PREFERRED
   *s\phase=#IPV6_HOST_READY : ipv6host_Refresh(*s,now)
  EndIf
 EndIf
 If *s\phase=#IPV6_HOST_JOINING And *s\membership\changeCount=0 And *s\membership\queryDue<0
  ; Hearing another report cannot prove our switch port has been learned.
  ipv6host_Refresh(*s,now)
 EndIf
 zero\high=0 : zero\low=0 : source=@zero
 If *s\phase=#IPV6_HOST_READY : source=@*s\endpoint\address : EndIf
 n=IPv6MldGroupStep(@*s\membership,generation,*s\policy\revision,now,source,out+14,capacity-14)
 If n<0 : *s\phase=#IPV6_HOST_FAILED : ProcedureReturn n : EndIf
 If n=0 : ProcedureReturn 0 : EndIf
 PokeA(out,51) : PokeA(out+1,51)
 For i=0 To 3 : PokeA(out+2+i,PeekA(out+50+i)) : Next
 For i=0 To 5 : PokeA(out+6+i,PeekA(@*s\endpoint\mac+i)) : Next
 NetWriteBE16(out+12,$86DD)
 *s\flight=1 : *s\flightRevision=*s\policy\revision : *s\flightToken=*s\membership\awaiting
 *s\serial=*s\serial+1 : *s\awaiting=*s\serial
 ProcedureReturn n+14
EndProcedure
; Pending queue receipts must NOT call Sent. Result0 is definitely unsent;
; result1 is confirmed driver completion; negative/ambiguous fails this host.
Procedure.i IPv6HostSent(*s.IPv6Host,generation.i,now.i,token.i,result.i,retryDelay.i)
 Define rc.i
 rc=ipv6host_Valid(*s,generation,now) : If rc<>0 : ProcedureReturn rc : EndIf
 If token<=0 Or token<>*s\awaiting : ProcedureReturn #IPV6_HOST_STALE : EndIf
 If result>1 Or retryDelay<1 Or retryDelay>1000 : ProcedureReturn #IPV6_HOST_ARGUMENT : EndIf
 rc=ipv6host_Sync(*s,now) : If rc<>0 : ProcedureReturn rc : EndIf
 *s\awaiting=0
 If result<0 : *s\phase=#IPV6_HOST_FAILED : ProcedureReturn result : EndIf
 If *s\phase=#IPV6_HOST_DUPLICATE : ProcedureReturn 0 : EndIf
 If *s\flight=1
  If *s\flightRevision<>*s\policy\revision : ProcedureReturn 0 : EndIf
  rc=IPv6MldGroupSent(@*s\membership,generation,*s\policy\revision,now,*s\flightToken,result,retryDelay)
  If rc<>0 : *s\phase=#IPV6_HOST_FAILED : ProcedureReturn rc : EndIf
  If result=1 And *s\phase=#IPV6_HOST_JOINING
   *s\phase=#IPV6_HOST_DAD : *s\endpoint\deadline=now+*s\delay
  EndIf
 ElseIf *s\flight=2
  rc=IPv6EndpointSent(@*s\endpoint,generation,now,result)
  If rc<>0 : *s\phase=#IPV6_HOST_FAILED : EndIf
  ProcedureReturn rc
 EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i IPv6HostInput(*s.IPv6Host,generation.i,now.i,frame.i,bytes.i,out.i,capacity.i,queryDelay.i)
 Define ip.IPv6PacketView,query.IPv6MldQueryView
 Define zero.IPv6AddressStorage
 Define rc.i,toGroup.i,toAll.i,source.i,kind.i
 rc=ipv6host_Valid(*s,generation,now) : If rc<>0 : ProcedureReturn rc : EndIf
 rc=ipv6host_Output(*s,out,capacity) : If rc<>0 : ProcedureReturn rc : EndIf
 If bytes<54 Or bytes>1514 Or IPv6MldSpanValid(frame,bytes)=0 : ProcedureReturn #IPV6_HOST_ARGUMENT : EndIf
 If IPv6EndpointSpansSeparate(frame,bytes,*s,SizeOf(IPv6Host))=0 Or IPv6EndpointSpansSeparate(frame,bytes,out,capacity)=0 : ProcedureReturn #IPV6_HOST_ARGUMENT : EndIf
 If IPv6EndpointSpansSeparate(frame,bytes,*s\membership\sources,*s\membership\capacity)=0 : ProcedureReturn #IPV6_HOST_ARGUMENT : EndIf
 If *s\phase=#IPV6_HOST_FAILED Or *s\phase=#IPV6_HOST_DUPLICATE : ProcedureReturn 0 : EndIf
 If NetReadBE16(frame+12)<>$86DD Or (PeekA(frame+6)&1)<>0 : ProcedureReturn 0 : EndIf
 If IPv6EndpointBytesEqual(frame+6,@*s\endpoint\mac,6)<>0 : ProcedureReturn 0 : EndIf
 rc=IPv6PacketParse(frame+14,bytes-14,@ip) : If rc<>0 : ProcedureReturn rc : EndIf
 zero\high=0 : zero\low=0 : PokeA(@zero,255) : PokeA(@zero+1,2) : PokeA(@zero+15,1)
 toAll=IPv6EndpointBytesEqual(ip\destination,@zero,16)
 toGroup=IPv6EndpointBytesEqual(ip\destination,@*s\membership\group,16)
 If ip\protocol=58 And ip\payloadBytes>=1 And (toAll<>0 Or toGroup<>0)
  If PeekA(frame)<>51 Or PeekA(frame+1)<>51 Or IPv6EndpointBytesEqual(frame+2,ip\destination+12,4)=0 : ProcedureReturn 0 : EndIf
  kind=PeekA(ip\payload)
  If kind=130
   rc=IPv6MldQuery(frame+14,bytes-14,@query) : If rc<>0 : ProcedureReturn rc : EndIf
   If queryDelay<0 Or queryDelay>query\maxDelay Or (queryDelay=0 And query\maxDelay<>0) : ProcedureReturn #IPV6_HOST_ARGUMENT : EndIf
   If IPv6AddressUnspecified(query\group)<>0
    If toAll=0 : ProcedureReturn 0 : EndIf
   Else
    If toGroup=0 Or IPv6EndpointBytesEqual(query\group,@*s\membership\group,16)=0 : ProcedureReturn 0 : EndIf
   EndIf
   rc=IPv6MldInterfaceQuery(@*s\policy,generation,now,frame+14,bytes-14) : If rc<0 : ProcedureReturn rc : EndIf
   rc=ipv6host_Sync(*s,now) : If rc<>0 : ProcedureReturn rc : EndIf
   ProcedureReturn IPv6MldGroupQuery(@*s\membership,generation,*s\policy\revision,now,@query,queryDelay)
  ElseIf kind=131 And toGroup<>0
   zero\high=0 : zero\low=0 : source=@zero
   If *s\phase=#IPV6_HOST_READY : source=@*s\endpoint\address : EndIf
   rc=IPv6MldHeardReport(frame+14,bytes-14,@*s\membership\group,source) : If rc<>0 : ProcedureReturn rc : EndIf
   rc=ipv6host_Sync(*s,now) : If rc<>0 : ProcedureReturn rc : EndIf
   ProcedureReturn IPv6MldGroupHeardV1(@*s\membership,generation,*s\policy\revision,now)
  EndIf
 EndIf
 rc=IPv6EndpointInput(@*s\endpoint,generation,frame,bytes,out,capacity)
 *s\lastNow=now
 If *s\endpoint\state=#IPV6_EP_DUPLICATE : *s\phase=#IPV6_HOST_DUPLICATE : EndIf
 ProcedureReturn rc
EndProcedure

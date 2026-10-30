; SLAAC lifetime plus DAD owner, RFC 4862 sections 5.4/5.5.
; Compose ipv6_slaac and ipv6_endpoint first. One zero-filled owner per /64.
; The caller keeps link-local DAD and the supplied solicited-node membership
; ready throughout use. This owner copies the link-local IID and checks that
; its solicited group is identical, so no additional membership is inferred.
; If link-local ownership fails or its generation changes, discard this owner.
#IPV6_OWNER_ARGUMENT=-860
#IPV6_OWNER_STALE=-861
Structure IPv6AddressOwner
 generation.i
 serial.i
 awaiting.i
 endpointGeneration.i
 mac.q
 lifetime.IPv6Slaac
 endpoint.IPv6Endpoint
EndStructure
Procedure.i ipv6owner_Span(p.i,n.i)
 If p<=0 Or n<=0 : ProcedureReturn 0 : EndIf
 If p>$7FFFFFFFFFFFFFFF-n : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i ipv6owner_Valid(*s.IPv6AddressOwner,generation.i,now.i)
 If ipv6owner_Span(*s,SizeOf(IPv6AddressOwner))=0 : ProcedureReturn #IPV6_OWNER_ARGUMENT : EndIf
 If generation<=0 Or generation<>*s\generation : ProcedureReturn #IPV6_OWNER_STALE : EndIf
 If now<0 Or now>$7FFFFFFEFFFFFFFF Or now<*s\lifetime\lastNow : ProcedureReturn #IPV6_OWNER_ARGUMENT : EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i IPv6AddressOwnerInit(*s.IPv6AddressOwner,generation.i,prefix.i,linklocal.i,joinedGroup.i,mac.i,now.i)
 Define candidate.IPv6AddressOwner,group.IPv6AddressStorage
 Define rc.i,i.i,nonzero.i
 If ipv6owner_Span(*s,SizeOf(IPv6AddressOwner))=0 : ProcedureReturn #IPV6_OWNER_ARGUMENT : EndIf
 If generation<=0 Or generation<=*s\generation : ProcedureReturn #IPV6_OWNER_STALE : EndIf
 If now<0 Or now>$7FFFFFFEFFFFFFFF : ProcedureReturn #IPV6_OWNER_ARGUMENT : EndIf
 If ipv6owner_Span(prefix,16)=0 Or ipv6owner_Span(linklocal,16)=0 Or ipv6owner_Span(joinedGroup,16)=0 Or ipv6owner_Span(mac,6)=0 : ProcedureReturn #IPV6_OWNER_ARGUMENT : EndIf
 If IPv6EndpointSpansSeparate(*s,SizeOf(IPv6AddressOwner),prefix,16)=0 Or IPv6EndpointSpansSeparate(*s,SizeOf(IPv6AddressOwner),linklocal,16)=0 Or IPv6EndpointSpansSeparate(*s,SizeOf(IPv6AddressOwner),joinedGroup,16)=0 Or IPv6EndpointSpansSeparate(*s,SizeOf(IPv6AddressOwner),mac,6)=0 : ProcedureReturn #IPV6_OWNER_ARGUMENT : EndIf
 If PeekA(linklocal)<>254 Or PeekA(linklocal+1)<>128 Or (PeekA(mac)&1)<>0 : ProcedureReturn #IPV6_OWNER_ARGUMENT : EndIf
 For i=2 To 7 : If PeekA(linklocal+i)<>0 : ProcedureReturn #IPV6_OWNER_ARGUMENT : EndIf : Next
 nonzero=0 : For i=0 To 5 : nonzero=nonzero|PeekA(mac+i) : Next
 If nonzero=0 : ProcedureReturn #IPV6_OWNER_ARGUMENT : EndIf
 For i=0 To SizeOf(IPv6AddressOwner)-1 : PokeA(@candidate+i,0) : Next
 rc=IPv6SlaacInit(@candidate\lifetime,generation,prefix,linklocal+8,now)
 If rc<>0 : ProcedureReturn rc : EndIf
 rc=IPv6SolicitedNode(@candidate\lifetime\address,@group)
 If IPv6EndpointBytesEqual(@group,joinedGroup,16)=0 : ProcedureReturn #IPV6_OWNER_ARGUMENT : EndIf
 candidate\generation=generation
 For i=0 To 5 : PokeA(@candidate\mac+i,PeekA(mac+i)) : Next
 For i=0 To SizeOf(IPv6AddressOwner)-1 : PokeA(*s+i,PeekA(@candidate+i)) : Next
 ProcedureReturn 0
EndProcedure
; 0 absent/expired, 1 tentative, 2 preferred, 3 deprecated, 4 duplicate,
; 5 failed. Only 2/3 permit receive use; new-source choice should prefer 2.
Procedure.i IPv6AddressOwnerStatus(*s.IPv6AddressOwner,generation.i,now.i)
 Define rc.i,bits.i
 rc=ipv6owner_Valid(*s,generation,now) : If rc<>0 : ProcedureReturn rc : EndIf
 bits=IPv6SlaacStatus(@*s\lifetime,generation,now)
 If (bits&1)=0
  *s\awaiting=0 : *s\endpoint\state=0 : *s\endpoint\awaiting=0
  ProcedureReturn 0
 EndIf
 If *s\endpoint\state=#IPV6_EP_TENTATIVE : ProcedureReturn 1 : EndIf
 If *s\endpoint\state=#IPV6_EP_DUPLICATE : ProcedureReturn 4 : EndIf
 If *s\endpoint\state=#IPV6_EP_FAILED : ProcedureReturn 5 : EndIf
 If *s\endpoint\state=#IPV6_EP_PREFERRED
  If (bits&2)<>0 : ProcedureReturn 2 : EndIf
  ProcedureReturn 3
 EndIf
 ProcedureReturn 0
EndProcedure
; Apply a matching, autonomous /64 PIO. On-link lifetime belongs elsewhere.
; Return 1 when fresh DAD begins; 0 refresh/ignored. A duplicate remains a
; duplicate while its lifetime exists, regardless of subsequent refreshes.
Procedure.i IPv6AddressOwnerApply(*s.IPv6AddressOwner,generation.i,now.i,valid.i,preferred.i,authenticated.i,delay.i,retransmit.i)
 Define rc.i
 rc=ipv6owner_Valid(*s,generation,now) : If rc<>0 : ProcedureReturn rc : EndIf
 If delay<0 Or delay>1000 Or retransmit<1 Or retransmit>$FFFFFFFF : ProcedureReturn #IPV6_OWNER_ARGUMENT : EndIf
 rc=IPv6SlaacApply(@*s\lifetime,generation,now,0,1,valid,preferred,authenticated)
 If rc<>1 : ProcedureReturn rc : EndIf
 *s\awaiting=0 : *s\endpointGeneration=*s\endpointGeneration+1
 rc=IPv6EndpointInit(@*s\endpoint,*s\endpointGeneration,@*s\lifetime\address,@*s\mac,now,delay,retransmit,1)
 If rc<>0 : ProcedureReturn rc : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i ipv6owner_Output(*s.IPv6AddressOwner,out.i,capacity.i)
 If capacity<86 Or capacity>1514 Or ipv6owner_Span(out,capacity)=0 : ProcedureReturn #IPV6_OWNER_ARGUMENT : EndIf
 If IPv6EndpointSpansSeparate(*s,SizeOf(IPv6AddressOwner),out,capacity)=0 : ProcedureReturn #IPV6_OWNER_ARGUMENT : EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i IPv6AddressOwnerStep(*s.IPv6AddressOwner,generation.i,now.i,out.i,capacity.i)
 Define rc.i
 rc=ipv6owner_Valid(*s,generation,now) : If rc<>0 : ProcedureReturn rc : EndIf
 rc=ipv6owner_Output(*s,out,capacity) : If rc<>0 : ProcedureReturn rc : EndIf
 rc=IPv6AddressOwnerStatus(*s,generation,now)
 If rc<>1 : ProcedureReturn 0 : EndIf
 rc=IPv6EndpointStep(@*s\endpoint,*s\endpointGeneration,now,out,capacity)
 If rc>0 : *s\serial=*s\serial+1 : *s\awaiting=*s\serial : EndIf
 ProcedureReturn rc
EndProcedure
; Positive Step creates awaiting token. Pending driver receipts do not call
; Sent. result0 is definitely unsent, 1 confirmed, negative ambiguous failure.
Procedure.i IPv6AddressOwnerSent(*s.IPv6AddressOwner,generation.i,now.i,token.i,result.i)
 Define rc.i
 rc=ipv6owner_Valid(*s,generation,now) : If rc<>0 : ProcedureReturn rc : EndIf
 If result>1 : ProcedureReturn #IPV6_OWNER_ARGUMENT : EndIf
 If token<=0 Or token<>*s\awaiting : ProcedureReturn #IPV6_OWNER_STALE : EndIf
 rc=IPv6AddressOwnerStatus(*s,generation,now)
 If rc<>1 : *s\awaiting=0 : ProcedureReturn #IPV6_OWNER_STALE : EndIf
 *s\awaiting=0
 ProcedureReturn IPv6EndpointSent(@*s\endpoint,*s\endpointGeneration,now,result)
EndProcedure
Procedure.i IPv6AddressOwnerInput(*s.IPv6AddressOwner,generation.i,now.i,frame.i,bytes.i,out.i,capacity.i)
 Define rc.i
 rc=ipv6owner_Valid(*s,generation,now) : If rc<>0 : ProcedureReturn rc : EndIf
 rc=ipv6owner_Output(*s,out,capacity) : If rc<>0 : ProcedureReturn rc : EndIf
 If bytes<54 Or bytes>1514 Or ipv6owner_Span(frame,bytes)=0 : ProcedureReturn #IPV6_OWNER_ARGUMENT : EndIf
 If IPv6EndpointSpansSeparate(*s,SizeOf(IPv6AddressOwner),frame,bytes)=0 Or IPv6EndpointSpansSeparate(out,capacity,frame,bytes)=0 : ProcedureReturn #IPV6_OWNER_ARGUMENT : EndIf
 rc=IPv6AddressOwnerStatus(*s,generation,now)
 If rc<1 Or rc>3 : ProcedureReturn 0 : EndIf
 rc=IPv6EndpointInput(@*s\endpoint,*s\endpointGeneration,frame,bytes,out,capacity)
 If *s\endpoint\state=#IPV6_EP_DUPLICATE : *s\awaiting=0 : EndIf
 ProcedureReturn rc
EndProcedure

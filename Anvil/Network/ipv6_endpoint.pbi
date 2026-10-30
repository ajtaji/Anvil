; Ethernet IPv6 address endpoint: DAD, neighbor replies and ICMPv6 echo.
; Protocol facts: RFC 4862 section 5.4, RFC 4861 section 7.2.4,
; RFC 4443 section 4.2. Independently implemented; no device or socket state.
; Compose ipv6_neighbor.pbi first. One zero-filled context per interface/address.
; Caller joins all-nodes and solicited-node multicast before Init, supplies a
; randomized initial delay, and invalidates/reinitializes on link generation.
; Serialized calls only. All time values are monotonic 64-bit milliseconds.
#IPV6_EP_TENTATIVE = 1
#IPV6_EP_PREFERRED = 2
#IPV6_EP_DUPLICATE = 3
#IPV6_EP_FAILED = 4
#IPV6_EP_ARGUMENT = -740
#IPV6_EP_STALE = -741
Structure IPv6Endpoint
 generation.i
 state.i
 deadline.i
 retransmit.i
 remaining.i
 awaiting.i
 address.IPv6AddressStorage
 mac.q
EndStructure

Procedure.i ipv6ep_Same(a.i,b.i,n.i)
 Define i.i
 For i=0 To n-1
  If PeekA(a+i)<>PeekA(b+i) : ProcedureReturn 0 : EndIf
 Next
 ProcedureReturn 1
EndProcedure

Procedure.i ipv6ep_Span(p.i,n.i)
 If p<=0 Or n<=0 : ProcedureReturn 0 : EndIf
 If p>$7FFFFFFFFFFFFFFF-n : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure

Procedure.i ipv6ep_Separate(a.i,an.i,b.i,bn.i)
 If a<b+bn And b<a+an : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure

; Refusal leaves the old context intact. A new generation must exceed the old.
Procedure.i IPv6EndpointInit(*ep.IPv6Endpoint,generation.i,address.i,mac.i,now.i,delay.i,retransmit.i,probes.i)
 Define i.i,nonzero.i
 If ipv6ep_Span(*ep,SizeOf(IPv6Endpoint))=0 : ProcedureReturn #IPV6_EP_ARGUMENT : EndIf
 If ipv6ep_Span(address,16)=0 Or ipv6ep_Span(mac,6)=0 : ProcedureReturn #IPV6_EP_ARGUMENT : EndIf
 If ipv6ep_Separate(*ep,SizeOf(IPv6Endpoint),address,16)=0 : ProcedureReturn #IPV6_EP_ARGUMENT : EndIf
 If ipv6ep_Separate(*ep,SizeOf(IPv6Endpoint),mac,6)=0 : ProcedureReturn #IPV6_EP_ARGUMENT : EndIf
 If generation<=0 Or generation<=*ep\generation : ProcedureReturn #IPV6_EP_STALE : EndIf
 If now<0 Or now>$7FFFFFFEFFFFFFFF Or delay<0 Or delay>1000 : ProcedureReturn #IPV6_EP_ARGUMENT : EndIf
 If retransmit<1 Or retransmit>$FFFFFFFF Or probes<1 Or probes>3 : ProcedureReturn #IPV6_EP_ARGUMENT : EndIf
 If PeekA(address)=255 Or IPv6AddressUnspecified(address)<>0 : ProcedureReturn #IPV6_EP_ARGUMENT : EndIf
 If (PeekA(mac)&1)<>0 : ProcedureReturn #IPV6_EP_ARGUMENT : EndIf
 nonzero=0
 For i=0 To 5 : nonzero=nonzero|PeekA(mac+i) : Next
 If nonzero=0 : ProcedureReturn #IPV6_EP_ARGUMENT : EndIf
 For i=0 To SizeOf(IPv6Endpoint)-1 : PokeA(*ep+i,0) : Next
 *ep\generation=generation : *ep\state=#IPV6_EP_TENTATIVE
 *ep\deadline=now+delay : *ep\retransmit=retransmit : *ep\remaining=probes
 For i=0 To 15 : PokeA(@*ep\address+i,PeekA(address+i)) : Next
 For i=0 To 5 : PokeA(@*ep\mac+i,PeekA(mac+i)) : Next
 ProcedureReturn 0
EndProcedure

Procedure.i ipv6ep_Output(*ep.IPv6Endpoint,generation.i,out.i,capacity.i)
 If ipv6ep_Span(*ep,SizeOf(IPv6Endpoint))=0 : ProcedureReturn #IPV6_EP_ARGUMENT : EndIf
 If generation<=0 Or generation<>*ep\generation : ProcedureReturn #IPV6_EP_STALE : EndIf
 If ipv6ep_Span(out,capacity)=0 Or capacity<86 Or capacity>1514 : ProcedureReturn #IPV6_EP_ARGUMENT : EndIf
 If ipv6ep_Separate(*ep,SizeOf(IPv6Endpoint),out,capacity)=0 : ProcedureReturn #IPV6_EP_ARGUMENT : EndIf
 ProcedureReturn 0
EndProcedure

Procedure ipv6ep_Ether(*ep.IPv6Endpoint,out.i,destination.i)
 Define i.i
 For i=0 To 5
  PokeA(out+i,PeekA(destination+i)) : PokeA(out+6+i,PeekA(@*ep\mac+i))
 Next
 NetWriteBE16(out+12,$86DD)
EndProcedure

; Emits a DAD Ethernet frame, or zero for no action. A returned frame requires
; exactly one Sent call. No success is inferred from preparing/queuing bytes.
Procedure.i IPv6EndpointStep(*ep.IPv6Endpoint,generation.i,now.i,out.i,capacity.i)
 Define rc.i,i.i
 Define source.IPv6AddressStorage
 Define mac.q
 rc=ipv6ep_Output(*ep,generation,out,capacity) : If rc<>0 : ProcedureReturn rc : EndIf
 If now<0 Or now>$7FFFFFFEFFFFFFFF : ProcedureReturn #IPV6_EP_ARGUMENT : EndIf
 If *ep\state<>#IPV6_EP_TENTATIVE Or *ep\awaiting<>0 Or now<*ep\deadline : ProcedureReturn 0 : EndIf
 If *ep\remaining=0 : *ep\state=#IPV6_EP_PREFERRED : ProcedureReturn 0 : EndIf
 source\high=0 : source\low=0
 rc=IPv6NeighborSolicit(out+14,capacity-14,@source,@*ep\address,@*ep\mac)
 If rc<0 : ProcedureReturn rc : EndIf
 mac=0 : PokeA(@mac,51) : PokeA(@mac+1,51)
 For i=0 To 3 : PokeA(@mac+2+i,PeekA(out+14+36+i)) : Next
 ipv6ep_Ether(*ep,out,@mac)
 *ep\awaiting=1
 ProcedureReturn rc+14
EndProcedure

; result 1 means confirmed transmission, 0 means definitely not sent (retry),
; negative means failed/ambiguous (do not assign the address). Generation and
; awaiting checks reject stale acknowledgements or double completion.
Procedure.i IPv6EndpointSent(*ep.IPv6Endpoint,generation.i,now.i,result.i)
 If ipv6ep_Span(*ep,SizeOf(IPv6Endpoint))=0 : ProcedureReturn #IPV6_EP_ARGUMENT : EndIf
 If generation<=0 Or generation<>*ep\generation : ProcedureReturn #IPV6_EP_STALE : EndIf
 If now<0 Or now>$7FFFFFFEFFFFFFFF Or result>1 : ProcedureReturn #IPV6_EP_ARGUMENT : EndIf
 If *ep\state<>#IPV6_EP_TENTATIVE Or *ep\awaiting=0 : ProcedureReturn #IPV6_EP_ARGUMENT : EndIf
 *ep\awaiting=0
 If result<0 : *ep\state=#IPV6_EP_FAILED : ProcedureReturn 0 : EndIf
 If result=1
  *ep\remaining=*ep\remaining-1 : *ep\deadline=now+*ep\retransmit
 EndIf
 ProcedureReturn 0
EndProcedure

; No borrowed RX pointer survives this call. Returns an Ethernet reply length,
; zero ignored/no reply, or a negative validation error. Local-origin Ethernet
; frames are ignored; the caller must suppress hardware multicast loopback when
; peers might share a MAC, as required for reliable DAD on that link.
Procedure.i IPv6EndpointInput(*ep.IPv6Endpoint,generation.i,frame.i,bytes.i,out.i,capacity.i)
 Define ip.IPv6PacketView,nd.IPv6NeighborView
 Define solicited.IPv6AddressStorage,allnodes.IPv6AddressStorage
 Define mac.q
 Define rc.i,i.i,toLocal.i,toAll.i,toSolicited.i,unspecified.i,flags.i,n.i
 rc=ipv6ep_Output(*ep,generation,out,capacity) : If rc<>0 : ProcedureReturn rc : EndIf
 If ipv6ep_Span(frame,bytes)=0 Or bytes<54 Or bytes>1514 : ProcedureReturn #IPV6_EP_ARGUMENT : EndIf
 If ipv6ep_Separate(frame,bytes,out,capacity)=0 : ProcedureReturn #IPV6_EP_ARGUMENT : EndIf
 If ipv6ep_Separate(frame,bytes,*ep,SizeOf(IPv6Endpoint))=0 : ProcedureReturn #IPV6_EP_ARGUMENT : EndIf
 If *ep\state<>#IPV6_EP_TENTATIVE And *ep\state<>#IPV6_EP_PREFERRED : ProcedureReturn 0 : EndIf
 If NetReadBE16(frame+12)<>$86DD Or (PeekA(frame+6)&1)<>0 : ProcedureReturn 0 : EndIf
 If ipv6ep_Same(frame+6,@*ep\mac,6)<>0 : ProcedureReturn 0 : EndIf
 rc=IPv6PacketParse(frame+14,bytes-14,@ip) : If rc<>0 : ProcedureReturn rc : EndIf
 If PeekA(ip\source)=255 : ProcedureReturn #IPV6_EP_ARGUMENT : EndIf
 allnodes\high=0 : allnodes\low=0 : PokeA(@allnodes,255) : PokeA(@allnodes+1,2) : PokeA(@allnodes+15,1)
 rc=IPv6SolicitedNode(@*ep\address,@solicited)
 toLocal=ipv6ep_Same(ip\destination,@*ep\address,16)
 toAll=ipv6ep_Same(ip\destination,@allnodes,16)
 toSolicited=ipv6ep_Same(ip\destination,@solicited,16)
 If toLocal=0 And toAll=0 And toSolicited=0 : ProcedureReturn 0 : EndIf
 If toLocal<>0
  If ipv6ep_Same(frame,@*ep\mac,6)=0 : ProcedureReturn 0 : EndIf
  If *ep\state=#IPV6_EP_TENTATIVE : ProcedureReturn 0 : EndIf
 Else
  If PeekA(frame)<>51 Or PeekA(frame+1)<>51 : ProcedureReturn 0 : EndIf
  If ipv6ep_Same(frame+2,ip\destination+12,4)=0 : ProcedureReturn 0 : EndIf
 EndIf
 If ip\protocol<>58 Or ip\payloadBytes<8 : ProcedureReturn 0 : EndIf
 unspecified=IPv6AddressUnspecified(ip\source)
 n=PeekA(ip\payload)
 If n=135 Or n=136
  rc=IPv6NeighborParse(frame+14,bytes-14,@ip,@nd) : If rc<>0 : ProcedureReturn rc : EndIf
  If ipv6ep_Same(nd\target,@*ep\address,16)=0 : ProcedureReturn 0 : EndIf
  If *ep\state=#IPV6_EP_TENTATIVE
   If n=136 Or unspecified<>0 : *ep\state=#IPV6_EP_DUPLICATE : *ep\awaiting=0 : EndIf
   ProcedureReturn 0
  EndIf
  If n<>135 : ProcedureReturn 0 : EndIf
  flags=$60000000
  If unspecified<>0
   flags=$20000000
   rc=IPv6NeighborAdvertise(out+14,capacity-14,@*ep\address,@allnodes,@*ep\mac,flags)
   mac=0 : PokeA(@mac,51) : PokeA(@mac+1,51) : PokeA(@mac+5,1)
   If rc>0 : ipv6ep_Ether(*ep,out,@mac) : EndIf
  Else
   rc=IPv6NeighborAdvertise(out+14,capacity-14,@*ep\address,ip\source,@*ep\mac,flags)
   If rc>0 : ipv6ep_Ether(*ep,out,frame+6) : EndIf
  EndIf
  If rc<0 : ProcedureReturn rc : EndIf
  ProcedureReturn rc+14
 EndIf
 ; Answer echo requests only after DAD, using the address the request named.
 If *ep\state<>#IPV6_EP_PREFERRED Or n<>128 Or toLocal=0 Or unspecified<>0 : ProcedureReturn 0 : EndIf
 If PeekA(ip\payload+1)<>0 : ProcedureReturn #IPV6_EP_ARGUMENT : EndIf
 rc=IPv6TransportChecksum(ip\source,ip\destination,58,ip\payload,ip\payloadBytes)
 If rc<>0 : ProcedureReturn #IPV6_ND_CHECKSUM : EndIf
 If ip\payloadBytes>capacity-54 : ProcedureReturn #IPV6_EP_ARGUMENT : EndIf
 rc=IPv6PacketHeader(out+14,capacity-14,@*ep\address,ip\source,ip\payloadBytes,58,64,0,0)
 If rc<>40 : ProcedureReturn rc : EndIf
 For i=0 To ip\payloadBytes-1 : PokeA(out+54+i,PeekA(ip\payload+i)) : Next
 PokeA(out+54,129) : NetWriteBE16(out+56,0)
 rc=IPv6TransportChecksum(@*ep\address,ip\source,58,out+54,ip\payloadBytes)
 NetWriteBE16(out+56,rc) : ipv6ep_Ether(*ep,out,frame+6)
 ProcedureReturn ip\payloadBytes+54
EndProcedure

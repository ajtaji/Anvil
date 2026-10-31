; Shared neighbor resolution/NUD owner, RFC4861 sections7.2/7.3.
; Compose ipv6_neighbor and ipv6_reachability first. Caller owns table keys,
; assigned source addresses, queued data, interface generation and link receipts.
; No receive pointer, device operation, synchronous wait or implicit replay.
#IPV6_NEIGHBOR_OWNER_ARGUMENT=-870
#IPV6_NEIGHBOR_OWNER_STALE=-871
#IPV6_NEIGHBOR_OWNER_UNREACHABLE=-872
Structure IPv6NeighborOwner
 generation.i
 lastNow.i
 serial.i
 awaiting.i
 retransmit.i
 target.IPv6AddressStorage
 localMac.q
 policy.IPv6Reachability
EndStructure
Procedure.i ipv6no_Span(p.i,n.i)
 If p<=0 Or n<=0 Or p>$7FFFFFFFFFFFFFFF-n : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i ipv6no_Separate(a.i,an.i,b.i,bn.i)
 If a<b+bn And b<a+an : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i ipv6no_Equal(a.i,b.i,n.i)
 Define i.i
 For i=0 To n-1 : If PeekA(a+i)<>PeekA(b+i) : ProcedureReturn 0 : EndIf : Next
 ProcedureReturn 1
EndProcedure
Procedure.i ipv6no_Mac(p.i)
 Define i.i,n.i
 If ipv6no_Span(p,6)=0 : ProcedureReturn 0 : EndIf
 If (PeekA(p)&1)<>0 : ProcedureReturn 0 : EndIf
 n=0 : For i=0 To 5 : n=n|PeekA(p+i) : Next
 If n=0 : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i ipv6no_Address(p.i)
 If ipv6no_Span(p,16)=0 : ProcedureReturn 0 : EndIf
 If PeekA(p)=255 Or IPv6AddressUnspecified(p)<>0 : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i ipv6no_Valid(*s.IPv6NeighborOwner,generation.i,now.i)
 If ipv6no_Span(*s,SizeOf(IPv6NeighborOwner))=0 : ProcedureReturn #IPV6_NEIGHBOR_OWNER_ARGUMENT : EndIf
 If generation<=0 Or generation<>*s\generation : ProcedureReturn #IPV6_NEIGHBOR_OWNER_STALE : EndIf
 If now<*s\lastNow Or IPv6ReachabilityTime(now,*s\retransmit)=0 : ProcedureReturn #IPV6_NEIGHBOR_OWNER_ARGUMENT : EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i IPv6NeighborOwnerInit(*s.IPv6NeighborOwner,generation.i,target.i,localMac.i,now.i,retransmit.i)
 Define candidate.IPv6NeighborOwner
 Define i.i,rc.i
 If ipv6no_Span(*s,SizeOf(IPv6NeighborOwner))=0 : ProcedureReturn #IPV6_NEIGHBOR_OWNER_ARGUMENT : EndIf
 If generation<=0 Or generation<=*s\generation : ProcedureReturn #IPV6_NEIGHBOR_OWNER_STALE : EndIf
 If IPv6ReachabilityTime(now,retransmit)=0 Or ipv6no_Address(target)=0 Or ipv6no_Mac(localMac)=0 : ProcedureReturn #IPV6_NEIGHBOR_OWNER_ARGUMENT : EndIf
 If ipv6no_Separate(*s,SizeOf(IPv6NeighborOwner),target,16)=0 Or ipv6no_Separate(*s,SizeOf(IPv6NeighborOwner),localMac,6)=0 : ProcedureReturn #IPV6_NEIGHBOR_OWNER_ARGUMENT : EndIf
 For i=0 To SizeOf(IPv6NeighborOwner)-1 : PokeA(@candidate+i,0) : Next
 candidate\generation=generation : candidate\lastNow=now : candidate\retransmit=retransmit
 For i=0 To 15 : PokeA(@candidate\target+i,PeekA(target+i)) : Next
 For i=0 To 5 : PokeA(@candidate\localMac+i,PeekA(localMac+i)) : Next
 rc=IPv6ReachabilityInit(@candidate\policy,now)
 For i=0 To SizeOf(IPv6NeighborOwner)-1 : PokeA(*s+i,PeekA(@candidate+i)) : Next
 ProcedureReturn 0
EndProcedure
; Caller already validated RA/NS and matched its source to this target. A
; learned MAC is STALE, never proof of forward reachability. Missing MAC=0.
Procedure.i IPv6NeighborOwnerLearn(*s.IPv6NeighborOwner,generation.i,now.i,mac.i,router.i)
 Define rc.i
 rc=ipv6no_Valid(*s,generation,now) : If rc<>0 : ProcedureReturn rc : EndIf
 If router<>-1 And router<>1 : ProcedureReturn #IPV6_NEIGHBOR_OWNER_ARGUMENT : EndIf
 If mac<>0
  If ipv6no_Mac(mac)=0 Or ipv6no_Separate(*s,SizeOf(IPv6NeighborOwner),mac,6)=0 : ProcedureReturn #IPV6_NEIGHBOR_OWNER_ARGUMENT : EndIf
 EndIf
 rc=IPv6ReachabilityLearn(@*s\policy,mac,router) : *s\lastNow=now
 If *s\policy\state<>#IPV6_NC_INCOMPLETE And *s\policy\state<>#IPV6_NC_PROBE : *s\awaiting=0 : EndIf
 ProcedureReturn rc
EndProcedure
Procedure.i IPv6NeighborOwnerUse(*s.IPv6NeighborOwner,generation.i,now.i)
 Define rc.i
 rc=ipv6no_Valid(*s,generation,now) : If rc<>0 : ProcedureReturn rc : EndIf
 *s\lastNow=now : ProcedureReturn IPv6ReachabilityUse(@*s\policy,now)
EndProcedure
; Only confirmation of newly sent upper-layer traffic may call this API.
Procedure.i IPv6NeighborOwnerConfirm(*s.IPv6NeighborOwner,generation.i,now.i,reachable.i)
 Define rc.i
 rc=ipv6no_Valid(*s,generation,now) : If rc<>0 : ProcedureReturn rc : EndIf
 If IPv6ReachabilityTime(now,reachable)=0 : ProcedureReturn #IPV6_NEIGHBOR_OWNER_ARGUMENT : EndIf
 rc=IPv6ReachabilityConfirm(@*s\policy,now,reachable) : *s\lastNow=now
 If rc=1 : *s\awaiting=0 : EndIf
 ProcedureReturn rc
EndProcedure
; 86-byte complete Ethernet NS, 0 idle, -872 resolution failed (queued data
; and dependent routes must fail). A positive result creates awaiting token.
Procedure.i IPv6NeighborOwnerStep(*s.IPv6NeighborOwner,generation.i,now.i,source.i,out.i,capacity.i)
 Define candidate.IPv6Reachability
 Define rc.i,action.i,i.i,n.i
 rc=ipv6no_Valid(*s,generation,now) : If rc<>0 : ProcedureReturn rc : EndIf
 If capacity<86 Or capacity>1514 Or ipv6no_Span(out,capacity)=0 Or ipv6no_Address(source)=0 : ProcedureReturn #IPV6_NEIGHBOR_OWNER_ARGUMENT : EndIf
 If ipv6no_Separate(*s,SizeOf(IPv6NeighborOwner),out,capacity)=0 Or ipv6no_Separate(*s,SizeOf(IPv6NeighborOwner),source,16)=0 Or ipv6no_Separate(out,capacity,source,16)=0 : ProcedureReturn #IPV6_NEIGHBOR_OWNER_ARGUMENT : EndIf
 If *s\serial=$7FFFFFFFFFFFFFFF : ProcedureReturn #IPV6_NEIGHBOR_OWNER_ARGUMENT : EndIf
 If *s\awaiting<>0 : *s\lastNow=now : ProcedureReturn 0 : EndIf
 For i=0 To SizeOf(IPv6Reachability)-1 : PokeA(@candidate+i,PeekA(@*s\policy+i)) : Next
 action=IPv6ReachabilityTick(@candidate,now,*s\retransmit)
 If action=1 Or action=2
  If action=1
   n=IPv6NeighborSolicit(out+14,capacity-14,source,@*s\target,@*s\localMac)
  Else
   n=IPv6NeighborProbe(out+14,capacity-14,source,@*s\target,@*s\localMac)
  EndIf
  If n<>72 : ProcedureReturn n : EndIf
  For i=0 To 5 : PokeA(out+6+i,PeekA(@*s\localMac+i)) : Next
  NetWriteBE16(out+12,$86DD)
  If action=1
   PokeA(out,51) : PokeA(out+1,51)
   For i=0 To 3 : PokeA(out+2+i,PeekA(out+50+i)) : Next
  Else
   For i=0 To 5 : PokeA(out+i,PeekA(@candidate\mac+i)) : Next
  EndIf
  *s\serial=*s\serial+1 : *s\awaiting=*s\serial
 EndIf
 For i=0 To SizeOf(IPv6Reachability)-1 : PokeA(@*s\policy+i,PeekA(@candidate+i)) : Next
 *s\lastNow=now
 If action=1 Or action=2 : ProcedureReturn 86 : EndIf
 If action=3 : ProcedureReturn #IPV6_NEIGHBOR_OWNER_UNREACHABLE : EndIf
 ProcedureReturn action
EndProcedure
; Pending receipt: do not call. A definite no-attempt refusal0 restores the
; probe budget; an ambiguous failure<0 consumes it. Both back off by RetransTimer
; without spinning. Caller owns queued-data/operation deadlines. A completed
; send starts its full interval here, not at queue acceptance.
Procedure.i IPv6NeighborOwnerSent(*s.IPv6NeighborOwner,generation.i,now.i,token.i,result.i)
 Define rc.i
 rc=ipv6no_Valid(*s,generation,now) : If rc<>0 : ProcedureReturn rc : EndIf
 If result>1 : ProcedureReturn #IPV6_NEIGHBOR_OWNER_ARGUMENT : EndIf
 If token<=0 Or token<>*s\awaiting : ProcedureReturn #IPV6_NEIGHBOR_OWNER_STALE : EndIf
 *s\awaiting=0 : *s\lastNow=now : *s\policy\deadline=now+*s\retransmit
 If result=0 And *s\policy\probes>0 : *s\policy\probes=*s\policy\probes-1 : EndIf
 ProcedureReturn 0
EndProcedure
; Caller supplies an actually assigned destination on this interface, and a
; randomized reachable interval. All-nodes unsolicited NA is accepted too.
; Return2 requires invalidating routes whose next-hop ceased being a router.
Procedure.i IPv6NeighborOwnerInput(*s.IPv6NeighborOwner,generation.i,now.i,local.i,frame.i,bytes.i,reachable.i)
 Define ip.IPv6PacketView,nd.IPv6NeighborView,allnodes.IPv6AddressStorage
 Define rc.i,toLocal.i,toAll.i
 rc=ipv6no_Valid(*s,generation,now) : If rc<>0 : ProcedureReturn rc : EndIf
 If bytes<54 Or bytes>1514 Or ipv6no_Span(frame,bytes)=0 Or ipv6no_Address(local)=0 Or IPv6ReachabilityTime(now,reachable)=0 : ProcedureReturn #IPV6_NEIGHBOR_OWNER_ARGUMENT : EndIf
 If ipv6no_Separate(*s,SizeOf(IPv6NeighborOwner),frame,bytes)=0 Or ipv6no_Separate(*s,SizeOf(IPv6NeighborOwner),local,16)=0 : ProcedureReturn #IPV6_NEIGHBOR_OWNER_ARGUMENT : EndIf
 If NetReadBE16(frame+12)<>$86DD Or ipv6no_Mac(frame+6)=0 : ProcedureReturn 0 : EndIf
 If ipv6no_Equal(frame+6,@*s\localMac,6)<>0 : ProcedureReturn 0 : EndIf
 rc=IPv6NeighborParse(frame+14,bytes-14,@ip,@nd) : If rc<>0 : ProcedureReturn rc : EndIf
 If nd\kind<>136 Or ipv6no_Equal(nd\target,@*s\target,16)=0 : ProcedureReturn 0 : EndIf
 allnodes\high=0 : allnodes\low=0 : PokeA(@allnodes,255) : PokeA(@allnodes+1,2) : PokeA(@allnodes+15,1)
 toLocal=ipv6no_Equal(ip\destination,local,16) : toAll=ipv6no_Equal(ip\destination,@allnodes,16)
 If toLocal<>0
  If ipv6no_Equal(frame,@*s\localMac,6)=0 : ProcedureReturn 0 : EndIf
 ElseIf toAll<>0
  If PeekA(frame)<>51 Or PeekA(frame+1)<>51 Or ipv6no_Equal(frame+2,ip\destination+12,4)=0 : ProcedureReturn 0 : EndIf
 Else
  ProcedureReturn 0
 EndIf
 If nd\targetMac<>0
  If ipv6no_Mac(nd\targetMac)=0 : ProcedureReturn #IPV6_NEIGHBOR_OWNER_ARGUMENT : EndIf
 EndIf
 rc=IPv6ReachabilityAdvertise(@*s\policy,nd\targetMac,nd\flags,now,reachable) : *s\lastNow=now
 If *s\policy\state<>#IPV6_NC_INCOMPLETE And *s\policy\state<>#IPV6_NC_PROBE : *s\awaiting=0 : EndIf
 ProcedureReturn rc
EndProcedure

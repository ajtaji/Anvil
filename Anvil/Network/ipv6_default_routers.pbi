; Shared default-router list, RFC 4861 sections 6.3.4-6.3.6 and RFC 4191
; sections 2.2/3.2/3.5. Caller owns 2..16 entries per interface, receives
; validated RA fields, and supplies neighbor failures at next-hop selection.
; No cache, packet, timer reads or device access. All times are monotonic ms.
#IPV6_ROUTES_ARGUMENT=-840
#IPV6_ROUTES_STALE=-841
Structure IPv6DefaultRouter
 address.IPv6AddressStorage
 until.i
 preference.i
EndStructure
Structure IPv6DefaultRouters
 generation.i
 lastNow.i
 revision.i
 entries.i
 capacity.i
 cursor.i
 probeMask.i
EndStructure
Procedure.i ipv6routes_Span(p.i,n.i)
 If p<=0 Or n<=0 : ProcedureReturn 0 : EndIf
 If p>$7FFFFFFFFFFFFFFF-n : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i ipv6routes_Valid(*s.IPv6DefaultRouters,generation.i,now.i)
 If ipv6routes_Span(*s,SizeOf(IPv6DefaultRouters))=0 : ProcedureReturn #IPV6_ROUTES_ARGUMENT : EndIf
 If now<0 Or now>$7FFFFFFEFFFFFFFF Or now<*s\lastNow : ProcedureReturn #IPV6_ROUTES_ARGUMENT : EndIf
 If generation<=0 Or generation<>*s\generation : ProcedureReturn #IPV6_ROUTES_STALE : EndIf
 If *s\capacity<2 Or *s\capacity>16 : ProcedureReturn #IPV6_ROUTES_ARGUMENT : EndIf
 If ipv6routes_Span(*s\entries,*s\capacity*SizeOf(IPv6DefaultRouter))=0 : ProcedureReturn #IPV6_ROUTES_ARGUMENT : EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i IPv6DefaultRoutersInit(*s.IPv6DefaultRouters,generation.i,entries.i,capacity.i,now.i)
 Define i.i,n.i
 If ipv6routes_Span(*s,SizeOf(IPv6DefaultRouters))=0 : ProcedureReturn #IPV6_ROUTES_ARGUMENT : EndIf
 If now<0 Or now>$7FFFFFFEFFFFFFFF Or capacity<2 Or capacity>16 : ProcedureReturn #IPV6_ROUTES_ARGUMENT : EndIf
 n=capacity*SizeOf(IPv6DefaultRouter)
 If ipv6routes_Span(entries,n)=0 : ProcedureReturn #IPV6_ROUTES_ARGUMENT : EndIf
 If *s<entries+n And entries<*s+SizeOf(IPv6DefaultRouters) : ProcedureReturn #IPV6_ROUTES_ARGUMENT : EndIf
 If generation<=0 Or generation<=*s\generation : ProcedureReturn #IPV6_ROUTES_STALE : EndIf
 For i=0 To n-1 : PokeA(entries+i,0) : Next
 *s\generation=generation : *s\lastNow=now : *s\revision=1
 *s\entries=entries : *s\capacity=capacity : *s\cursor=0 : *s\probeMask=0
 ProcedureReturn 0
EndProcedure
; Expiry changes revision; the owner invalidates cached next hops when it
; changes. Slots never move, so neighbor-status masks remain stable for a call.
Procedure.i IPv6DefaultRoutersTick(*s.IPv6DefaultRouters,generation.i,now.i)
 Define *row.IPv6DefaultRouter
 Define rc.i,i.i,removed.i
 rc=ipv6routes_Valid(*s,generation,now) : If rc<>0 : ProcedureReturn rc : EndIf
 *s\lastNow=now : removed=0
 For i=0 To *s\capacity-1
  *row=*s\entries+i*SizeOf(IPv6DefaultRouter)
  If *row\until<>0 And *row\until<=now
   *row\until=0 : *s\revision=*s\revision+1 : removed=removed+1
  EndIf
 Next
 *s\probeMask=0
 ProcedureReturn removed
EndProcedure
; Return 0 applied/ignored withdrawal, 1 new router not retained (table full).
; A full list never evicts a live router. Source is a validated RA link-local
; address; lifetime is its 16-bit seconds and flags include the preference bits.
Procedure.i IPv6DefaultRoutersApply(*s.IPv6DefaultRouters,generation.i,now.i,source.i,lifetime.i,flags.i)
 Define *row.IPv6DefaultRouter
 Define rc.i,i.i,j.i,same.i,found.i,empty.i,preference.i,n.i
 rc=ipv6routes_Valid(*s,generation,now) : If rc<>0 : ProcedureReturn rc : EndIf
 If ipv6routes_Span(source,16)=0 Or lifetime<0 Or lifetime>65535 Or flags<0 Or flags>255 : ProcedureReturn #IPV6_ROUTES_ARGUMENT : EndIf
 If PeekA(source)<>254 Or (PeekA(source+1)&192)<>128 : ProcedureReturn #IPV6_ROUTES_ARGUMENT : EndIf
 n=*s\capacity*SizeOf(IPv6DefaultRouter)
 If source<*s+SizeOf(IPv6DefaultRouters) And *s<source+16 : ProcedureReturn #IPV6_ROUTES_ARGUMENT : EndIf
 If source<*s\entries+n And *s\entries<source+16 : ProcedureReturn #IPV6_ROUTES_ARGUMENT : EndIf
 rc=IPv6DefaultRoutersTick(*s,generation,now)
 found=-1 : empty=-1
 For i=0 To *s\capacity-1
  *row=*s\entries+i*SizeOf(IPv6DefaultRouter)
  If *row\until=0
   If empty<0 : empty=i : EndIf
  Else
   same=1
   For j=0 To 15 : If PeekA(@*row\address+j)<>PeekA(source+j) : same=0 : EndIf : Next
   If same=1 : found=i : EndIf
  EndIf
 Next
 If lifetime=0
  If found>=0
   *row=*s\entries+found*SizeOf(IPv6DefaultRouter)
   *row\until=0 : *s\revision=*s\revision+1
  EndIf
  ProcedureReturn 0
 EndIf
 If found<0
  If empty<0 : ProcedureReturn 1 : EndIf
  found=empty : *s\revision=*s\revision+1
 EndIf
 *row=*s\entries+found*SizeOf(IPv6DefaultRouter)
 preference=(flags>>3)&3
 If preference=3 : preference=-1 : ElseIf preference=2 : preference=0 : EndIf
 If *row\until<>0 And *row\preference<>preference : *s\revision=*s\revision+1 : EndIf
 For j=0 To 15 : PokeA(@*row\address+j,PeekA(source+j)) : Next
 *row\until=now+lifetime*1000 : *row\preference=preference
 ProcedureReturn 0
EndProcedure
; Returns slot+1, 0 no default route, negative refusal. failedMask marks only
; known-unreachable neighbors: unknown reachability is assumed reachable.
; Equal-ranked choices rotate. The owner uses probeMask to probe avoided,
; higher-preference failed routers only for actual traffic, rate-limited to
; one probe/minute/router (RFC 4191 3.5); selection itself never sends a probe.
Procedure.i IPv6DefaultRoutersSelect(*s.IPv6DefaultRouters,generation.i,now.i,failedMask.i)
 Define *row.IPv6DefaultRouter,*chosen.IPv6DefaultRouter
 Define rc.i,i.i,slot.i,rank.i,best.i,bestRank.i
 rc=ipv6routes_Valid(*s,generation,now) : If rc<>0 : ProcedureReturn rc : EndIf
 If failedMask<0 Or failedMask>=(1<<*s\capacity) : ProcedureReturn #IPV6_ROUTES_ARGUMENT : EndIf
 rc=IPv6DefaultRoutersTick(*s,generation,now)
 best=-1 : bestRank=-9
 For i=0 To *s\capacity-1
  slot=(*s\cursor+i) % *s\capacity
  *row=*s\entries+slot*SizeOf(IPv6DefaultRouter)
  If *row\until>now
   rank=*row\preference
   If (failedMask&(1<<slot))=0 : rank=rank+4 : EndIf
   If rank>bestRank : best=slot : bestRank=rank : EndIf
  EndIf
 Next
 If best<0 : ProcedureReturn 0 : EndIf
 *chosen=*s\entries+best*SizeOf(IPv6DefaultRouter)
 *s\cursor=(best+1) % *s\capacity
 For i=0 To *s\capacity-1
  *row=*s\entries+i*SizeOf(IPv6DefaultRouter)
  If *row\until>now And *row\preference>*chosen\preference And (failedMask&(1<<i))<>0
   *s\probeMask=*s\probeMask|(1<<i)
  EndIf
 Next
 ProcedureReturn best+1
EndProcedure

; Shared on-link prefix list, RFC 4861 sections 6.3.4/6.3.5.
; One caller-owned table per interface; advertisements merge by normalized
; prefix and length, not by advertising router. Omission and L=0 do not remove
; prior information. Independent from SLAAC address lifetimes and DAD.
#IPV6_PREFIX_ARGUMENT=-850
#IPV6_PREFIX_STALE=-851
Structure IPv6OnLinkPrefix
 prefix.IPv6AddressStorage
 length.i
 until.i
EndStructure
Structure IPv6PrefixList
 generation.i
 lastNow.i
 revision.i
 entries.i
 capacity.i
EndStructure
Procedure.i ipv6prefix_Span(p.i,n.i)
 If p<=0 Or n<=0 : ProcedureReturn 0 : EndIf
 If p>$7FFFFFFFFFFFFFFF-n : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i ipv6prefix_Valid(*s.IPv6PrefixList,generation.i,now.i)
 If ipv6prefix_Span(*s,SizeOf(IPv6PrefixList))=0 : ProcedureReturn #IPV6_PREFIX_ARGUMENT : EndIf
 If now<0 Or now>$7FFFF00000000000 Or now<*s\lastNow : ProcedureReturn #IPV6_PREFIX_ARGUMENT : EndIf
 If generation<=0 Or generation<>*s\generation : ProcedureReturn #IPV6_PREFIX_STALE : EndIf
 If *s\capacity<1 Or *s\capacity>64 : ProcedureReturn #IPV6_PREFIX_ARGUMENT : EndIf
 If ipv6prefix_Span(*s\entries,*s\capacity*SizeOf(IPv6OnLinkPrefix))=0 : ProcedureReturn #IPV6_PREFIX_ARGUMENT : EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i IPv6PrefixListInit(*s.IPv6PrefixList,generation.i,entries.i,capacity.i,now.i)
 Define n.i,i.i
 If ipv6prefix_Span(*s,SizeOf(IPv6PrefixList))=0 : ProcedureReturn #IPV6_PREFIX_ARGUMENT : EndIf
 If now<0 Or now>$7FFFF00000000000 Or capacity<1 Or capacity>64 : ProcedureReturn #IPV6_PREFIX_ARGUMENT : EndIf
 n=capacity*SizeOf(IPv6OnLinkPrefix)
 If ipv6prefix_Span(entries,n)=0 : ProcedureReturn #IPV6_PREFIX_ARGUMENT : EndIf
 If *s<entries+n And entries<*s+SizeOf(IPv6PrefixList) : ProcedureReturn #IPV6_PREFIX_ARGUMENT : EndIf
 If generation<=0 Or generation<=*s\generation : ProcedureReturn #IPV6_PREFIX_STALE : EndIf
 For i=0 To n-1 : PokeA(entries+i,0) : Next
 *s\generation=generation : *s\lastNow=now : *s\revision=1 : *s\entries=entries : *s\capacity=capacity
 ProcedureReturn 0
EndProcedure
Procedure.i IPv6PrefixListTick(*s.IPv6PrefixList,generation.i,now.i)
 Define *row.IPv6OnLinkPrefix
 Define rc.i,i.i,count.i
 rc=ipv6prefix_Valid(*s,generation,now) : If rc<>0 : ProcedureReturn rc : EndIf
 *s\lastNow=now : count=0
 For i=0 To *s\capacity-1
  *row=*s\entries+i*SizeOf(IPv6OnLinkPrefix)
  If *row\until<>0 And *row\until<=now
   *row\until=0 : count=count+1 : *s\revision=*s\revision+1
  EndIf
 Next
 ProcedureReturn count
EndProcedure
; 0 applied/ignored, 1 capacity exhausted without evicting a live prefix.
; Negative argument refusals leave all state unchanged. Source may be a PIO
; prefix with host bits set; canonical identity is formed here before lookup.
Procedure.i IPv6PrefixListApply(*s.IPv6PrefixList,generation.i,now.i,source.i,bits.i,onlink.i,seconds.i)
 Define prefix.IPv6AddressStorage
 Define *row.IPv6OnLinkPrefix
 Define rc.i,n.i,i.i,part.i,value.i,found.i,empty.i
 rc=ipv6prefix_Valid(*s,generation,now) : If rc<>0 : ProcedureReturn rc : EndIf
 If ipv6prefix_Span(source,16)=0 Or bits<0 Or bits>128 Or onlink<0 Or onlink>1 Or seconds<0 Or seconds>$FFFFFFFF : ProcedureReturn #IPV6_PREFIX_ARGUMENT : EndIf
 n=*s\capacity*SizeOf(IPv6OnLinkPrefix)
 If source<*s+SizeOf(IPv6PrefixList) And *s<source+16 : ProcedureReturn #IPV6_PREFIX_ARGUMENT : EndIf
 If source<*s\entries+n And *s\entries<source+16 : ProcedureReturn #IPV6_PREFIX_ARGUMENT : EndIf
 rc=IPv6PrefixListTick(*s,generation,now)
 If onlink=0 : ProcedureReturn 0 : EndIf
 If bits>=8 And PeekA(source)=255 : ProcedureReturn 0 : EndIf
 If bits>=10 And PeekA(source)=254 And (PeekA(source+1)&192)=128 : ProcedureReturn 0 : EndIf
 For i=0 To 15
  part=bits-i*8 : value=0
  If part>=8
   value=PeekA(source+i)
  ElseIf part>0
   value=PeekA(source+i)&(255<<(8-part))
  EndIf
  PokeA(@prefix+i,value)
 Next
 found=-1 : empty=-1
 For i=0 To *s\capacity-1
  *row=*s\entries+i*SizeOf(IPv6OnLinkPrefix)
  If *row\until=0
   If empty<0 : empty=i : EndIf
  ElseIf *row\length=bits
   If IPv6AddressPrefix(@*row\prefix,@prefix,128)=1 : found=i : EndIf
  EndIf
 Next
 If seconds=0
  If found>=0
   *row=*s\entries+found*SizeOf(IPv6OnLinkPrefix)
   *row\until=0 : *s\revision=*s\revision+1
  EndIf
  ProcedureReturn 0
 EndIf
 If found<0
  If empty<0 : ProcedureReturn 1 : EndIf
  found=empty : *s\revision=*s\revision+1
 EndIf
 *row=*s\entries+found*SizeOf(IPv6OnLinkPrefix)
 *row\prefix\high=prefix\high : *row\prefix\low=prefix\low : *row\length=bits
 If seconds=$FFFFFFFF
  *row\until=$7FFFFFFFFFFFFFFF
 Else
  *row\until=now+seconds*1000
 EndIf
 ProcedureReturn 0
EndProcedure
; Returns longest matching prefix length + 1 (so /0 is 1), or 0 for no
; advertised on-link match. Link-local reachability is inherent to the link
; and handled by the caller, not installed from advertisements into this list.
Procedure.i IPv6PrefixListMatch(*s.IPv6PrefixList,generation.i,now.i,address.i)
 Define *row.IPv6OnLinkPrefix
 Define rc.i,i.i,best.i
 rc=ipv6prefix_Valid(*s,generation,now) : If rc<>0 : ProcedureReturn rc : EndIf
 If ipv6prefix_Span(address,16)=0 : ProcedureReturn #IPV6_PREFIX_ARGUMENT : EndIf
 If address<*s+SizeOf(IPv6PrefixList) And *s<address+16 : ProcedureReturn #IPV6_PREFIX_ARGUMENT : EndIf
 If address<*s\entries+*s\capacity*SizeOf(IPv6OnLinkPrefix) And *s\entries<address+16 : ProcedureReturn #IPV6_PREFIX_ARGUMENT : EndIf
 rc=IPv6PrefixListTick(*s,generation,now) : best=0
 For i=0 To *s\capacity-1
  *row=*s\entries+i*SizeOf(IPv6OnLinkPrefix)
  If *row\until>now And *row\length+1>best
   If IPv6AddressPrefix(@*row\prefix,address,*row\length)=1 : best=*row\length+1 : EndIf
  EndIf
 Next
 ProcedureReturn best
EndProcedure

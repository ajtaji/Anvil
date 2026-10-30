; Per-interface recursive DNS repository, RFC 8106 sections 5.1 and 6.
; Caller owns storage and supplies extended monotonic milliseconds. No I/O.
XIncludeFile "Anvil/Network/ipv6_rdnss.pbi"
#IPV6_RDNSS_LIST_ARGUMENT=-913
#IPV6_RDNSS_LIST_STALE=-914
Structure IPv6RdnssEntry
 address.IPv6AddressStorage
 until.i
EndStructure
Structure IPv6RdnssList
 generation.i
 kind.i
 lastNow.i
 revision.i
 entries.i
 capacity.i
 count.i
EndStructure
Procedure.i ipv6rdlist_Span(p.i,n.i)
 If p<=0 Or n<=0 : ProcedureReturn 0 : EndIf
 If p>$7FFFFFFFFFFFFFFF-n : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i ipv6rdlist_Separate(a.i,an.i,b.i,bn.i)
 If a<b+bn And b<a+an : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i ipv6rdlist_Valid(*s.IPv6RdnssList,kind.i,generation.i,now.i)
 If ipv6rdlist_Span(*s,SizeOf(IPv6RdnssList))=0 : ProcedureReturn #IPV6_RDNSS_LIST_ARGUMENT : EndIf
 If kind<=0 Or generation<=0 Or kind<>*s\kind Or generation<>*s\generation : ProcedureReturn #IPV6_RDNSS_LIST_STALE : EndIf
 If now<0 Or now>$7FFFF00000000000 Or now<*s\lastNow : ProcedureReturn #IPV6_RDNSS_LIST_ARGUMENT : EndIf
 If *s\capacity<3 Or *s\capacity>16 Or *s\count<0 Or *s\count>*s\capacity : ProcedureReturn #IPV6_RDNSS_LIST_ARGUMENT : EndIf
 If ipv6rdlist_Span(*s\entries,*s\capacity*SizeOf(IPv6RdnssEntry))=0 : ProcedureReturn #IPV6_RDNSS_LIST_ARGUMENT : EndIf
 If ipv6rdlist_Separate(*s,SizeOf(IPv6RdnssList),*s\entries,*s\capacity*SizeOf(IPv6RdnssEntry))=0 : ProcedureReturn #IPV6_RDNSS_LIST_ARGUMENT : EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i IPv6RdnssListInit(*s.IPv6RdnssList,kind.i,generation.i,entries.i,capacity.i,now.i)
 Define i.i,n.i
 If ipv6rdlist_Span(*s,SizeOf(IPv6RdnssList))=0 : ProcedureReturn #IPV6_RDNSS_LIST_ARGUMENT : EndIf
 If kind<=0 Or now<0 Or now>$7FFFF00000000000 Or capacity<3 Or capacity>16 : ProcedureReturn #IPV6_RDNSS_LIST_ARGUMENT : EndIf
 If generation<=0 Or generation<=*s\generation : ProcedureReturn #IPV6_RDNSS_LIST_STALE : EndIf
 n=capacity*SizeOf(IPv6RdnssEntry)
 If ipv6rdlist_Span(entries,n)=0 : ProcedureReturn #IPV6_RDNSS_LIST_ARGUMENT : EndIf
 If ipv6rdlist_Separate(*s,SizeOf(IPv6RdnssList),entries,n)=0 : ProcedureReturn #IPV6_RDNSS_LIST_ARGUMENT : EndIf
 For i=0 To n-1 : PokeA(entries+i,0) : Next
 *s\generation=generation : *s\kind=kind : *s\lastNow=now : *s\revision=1
 *s\entries=entries : *s\capacity=capacity : *s\count=0
 ProcedureReturn 0
EndProcedure
Procedure ipv6rdlist_Remove(*s.IPv6RdnssList,index.i)
 Define i.i,p.i,n.i
 p=*s\entries+index*SizeOf(IPv6RdnssEntry)
 n=(*s\count-index-1)*SizeOf(IPv6RdnssEntry)
 For i=0 To n-1 : PokeA(p+i,PeekA(p+SizeOf(IPv6RdnssEntry)+i)) : Next
 *s\count=*s\count-1
 p=*s\entries+*s\count*SizeOf(IPv6RdnssEntry)
 For i=0 To SizeOf(IPv6RdnssEntry)-1 : PokeA(p+i,0) : Next
 *s\revision=*s\revision+1
EndProcedure
Procedure.i IPv6RdnssListTick(*s.IPv6RdnssList,kind.i,generation.i,now.i)
 Define *row.IPv6RdnssEntry
 Define rc.i,i.i,removed.i
 rc=ipv6rdlist_Valid(*s,kind,generation,now) : If rc<>0 : ProcedureReturn rc : EndIf
 *s\lastNow=now : i=0 : removed=0
 While i<*s\count
  *row=*s\entries+i*SizeOf(IPv6RdnssEntry)
  If *row\until<=now
   ipv6rdlist_Remove(*s,i) : removed=removed+1
  Else
   i=i+1
  EndIf
 Wend
 ProcedureReturn removed
EndProcedure
; Validate the complete batch before changing anything. Updates preserve an
; existing address's position. Newly retained addresses precede older entries
; in their input order. Full storage evicts the earliest-expiring entry.
Procedure.i IPv6RdnssListApply(*s.IPv6RdnssList,kind.i,generation.i,now.i,records.i,count.i)
 Define *input.IPv6RdnssAdvertisement,*row.IPv6RdnssEntry,*victim.IPv6RdnssEntry
 Define rc.i,n.i,i.i,j.i,k.i,value.i,found.i,front.i,earliest.i,expiry.i,p.i
 rc=ipv6rdlist_Valid(*s,kind,generation,now) : If rc<>0 : ProcedureReturn rc : EndIf
 If count<0 Or count>4096 : ProcedureReturn #IPV6_RDNSS_LIST_ARGUMENT : EndIf
 If count>0
  n=count*SizeOf(IPv6RdnssAdvertisement)
  If ipv6rdlist_Span(records,n)=0 : ProcedureReturn #IPV6_RDNSS_LIST_ARGUMENT : EndIf
  If ipv6rdlist_Separate(records,n,*s,SizeOf(IPv6RdnssList))=0 : ProcedureReturn #IPV6_RDNSS_LIST_ARGUMENT : EndIf
  If ipv6rdlist_Separate(records,n,*s\entries,*s\capacity*SizeOf(IPv6RdnssEntry))=0 : ProcedureReturn #IPV6_RDNSS_LIST_ARGUMENT : EndIf
  For i=0 To count-1
   *input=records+i*SizeOf(IPv6RdnssAdvertisement)
   If *input\seconds<0 Or *input\seconds>$FFFFFFFF Or PeekA(@*input\address)=255 : ProcedureReturn #IPV6_RDNSS_LIST_ARGUMENT : EndIf
   value=0
   For j=0 To 15 : value=value|PeekA(@*input\address+j) : Next
   If value=0 : ProcedureReturn #IPV6_RDNSS_LIST_ARGUMENT : EndIf
  Next
 EndIf
 rc=IPv6RdnssListTick(*s,kind,generation,now) : front=0
 For i=0 To count-1
  *input=records+i*SizeOf(IPv6RdnssAdvertisement) : found=-1
  For j=0 To *s\count-1
   *row=*s\entries+j*SizeOf(IPv6RdnssEntry)
   If IPv6AddressPrefix(@*row\address,@*input\address,128)=1 : found=j : EndIf
  Next
  If *input\seconds=0
   If found>=0
    ipv6rdlist_Remove(*s,found) : If found<front : front=front-1 : EndIf
   EndIf
  Else
   If found<0
    If *s\count=*s\capacity
     earliest=0 : *victim=*s\entries
     For j=1 To *s\count-1
      *row=*s\entries+j*SizeOf(IPv6RdnssEntry)
      If *row\until<=*victim\until : earliest=j : *victim=*row : EndIf
     Next
     ipv6rdlist_Remove(*s,earliest) : If earliest<front : front=front-1 : EndIf
    EndIf
    p=*s\entries+front*SizeOf(IPv6RdnssEntry)
    n=(*s\count-front)*SizeOf(IPv6RdnssEntry) : k=n-1
    While k>=0 : PokeA(p+SizeOf(IPv6RdnssEntry)+k,PeekA(p+k)) : k=k-1 : Wend
    found=front : front=front+1 : *s\count=*s\count+1
   EndIf
   *row=*s\entries+found*SizeOf(IPv6RdnssEntry)
   For j=0 To 15 : PokeA(@*row\address+j,PeekA(@*input\address+j)) : Next
   expiry=$7FFFFFFFFFFFFFFF
   If *input\seconds<>$FFFFFFFF : expiry=now+*input\seconds*1000 : EndIf
   *row\until=expiry : *s\revision=*s\revision+1
  EndIf
 Next
 ProcedureReturn 0
EndProcedure
; Copy a currently eligible address; interface and generation must match.
; 16 copied, 0 no such live index, negative refusal. No output on refusal.
Procedure.i IPv6RdnssListGet(*s.IPv6RdnssList,kind.i,generation.i,now.i,index.i,out.i)
 Define rc.i,i.i,p.i
 rc=ipv6rdlist_Valid(*s,kind,generation,now) : If rc<>0 : ProcedureReturn rc : EndIf
 If index<0 Or index>=*s\capacity Or ipv6rdlist_Span(out,16)=0 : ProcedureReturn #IPV6_RDNSS_LIST_ARGUMENT : EndIf
 If ipv6rdlist_Separate(out,16,*s,SizeOf(IPv6RdnssList))=0 : ProcedureReturn #IPV6_RDNSS_LIST_ARGUMENT : EndIf
 If ipv6rdlist_Separate(out,16,*s\entries,*s\capacity*SizeOf(IPv6RdnssEntry))=0 : ProcedureReturn #IPV6_RDNSS_LIST_ARGUMENT : EndIf
 rc=IPv6RdnssListTick(*s,kind,generation,now)
 If index>=*s\count : ProcedureReturn 0 : EndIf
 p=*s\entries+index*SizeOf(IPv6RdnssEntry)
 For i=0 To 15 : PokeA(out+i,PeekA(p+i)) : Next
 ProcedureReturn 16
EndProcedure

; Discard learned state when this link becomes unusable within its epoch.
; A later epoch still requires Init, which rejects callbacks from the old one.
Procedure.i IPv6RdnssListClear(*s.IPv6RdnssList,kind.i,generation.i,now.i)
 Define rc.i,i.i
 rc=ipv6rdlist_Valid(*s,kind,generation,now) : If rc<>0 : ProcedureReturn rc : EndIf
 For i=0 To *s\capacity*SizeOf(IPv6RdnssEntry)-1 : PokeA(*s\entries+i,0) : Next
 If *s\count>0 : *s\revision=*s\revision+1 : EndIf
 *s\count=0 : *s\lastNow=now
 ProcedureReturn 0
EndProcedure

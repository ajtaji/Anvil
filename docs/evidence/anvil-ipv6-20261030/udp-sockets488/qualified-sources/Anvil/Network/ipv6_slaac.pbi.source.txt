; Shared per-prefix SLAAC lifetime policy, RFC 4862 sections 5.5.3/5.5.4
; and RFC 4861 section 6.3.4. One caller-owned /64 and 64-bit interface ID.
; The caller validates RA/PIO wire format, scopes entries by interface, runs
; DAD for each newly created address and owns routing/cache invalidation.
; Eligibility is not DAD success. No receive pointers or device state retained.
; All deadlines use monotonic milliseconds; infinity has an explicit sentinel.
#IPV6_SLAAC_INFINITY=$7FFFFFFFFFFFFFFF
#IPV6_SLAAC_ARGUMENT=-820
#IPV6_SLAAC_STALE=-821
Structure IPv6Slaac
 generation.i
 lastNow.i
 onLinkUntil.i
 validUntil.i
 preferredUntil.i
 address.IPv6AddressStorage
EndStructure
Procedure.i ipv6slaac_Span(p.i,n.i)
 If p<=0 Or n<=0 : ProcedureReturn 0 : EndIf
 If p>$7FFFFFFFFFFFFFFF-n : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i ipv6slaac_Time(now.i)
 ; Leave room for the largest finite 32-bit seconds value converted to ms.
 If now<0 Or now>$7FFFF00000000000 : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i ipv6slaac_Deadline(now.i,seconds.i)
 If seconds=$FFFFFFFF : ProcedureReturn #IPV6_SLAAC_INFINITY : EndIf
 ProcedureReturn now+seconds*1000
EndProcedure
Procedure.i ipv6slaac_Valid(*s.IPv6Slaac,generation.i,now.i)
 If ipv6slaac_Span(*s,SizeOf(IPv6Slaac))=0 Or ipv6slaac_Time(now)=0 : ProcedureReturn #IPV6_SLAAC_ARGUMENT : EndIf
 If generation<=0 Or generation<>*s\generation : ProcedureReturn #IPV6_SLAAC_STALE : EndIf
 If now<*s\lastNow : ProcedureReturn #IPV6_SLAAC_ARGUMENT : EndIf
 ProcedureReturn 0
EndProcedure
; prefix points to 16 bytes, iid to 8. Host bits in prefix are ignored.
; Refusal preserves the complete old context. Generation must increase.
Procedure.i IPv6SlaacInit(*s.IPv6Slaac,generation.i,prefix.i,iid.i,now.i)
 Define i.i,nonzero.i
 If ipv6slaac_Span(*s,SizeOf(IPv6Slaac))=0 Or ipv6slaac_Time(now)=0 : ProcedureReturn #IPV6_SLAAC_ARGUMENT : EndIf
 If ipv6slaac_Span(prefix,16)=0 Or ipv6slaac_Span(iid,8)=0 : ProcedureReturn #IPV6_SLAAC_ARGUMENT : EndIf
 If *s<prefix+16 And prefix<*s+SizeOf(IPv6Slaac) : ProcedureReturn #IPV6_SLAAC_ARGUMENT : EndIf
 If *s<iid+8 And iid<*s+SizeOf(IPv6Slaac) : ProcedureReturn #IPV6_SLAAC_ARGUMENT : EndIf
 If generation<=0 Or generation<=*s\generation : ProcedureReturn #IPV6_SLAAC_STALE : EndIf
 If PeekA(prefix)=255 : ProcedureReturn #IPV6_SLAAC_ARGUMENT : EndIf
 If PeekA(prefix)=254 And (PeekA(prefix+1)&192)=128 : ProcedureReturn #IPV6_SLAAC_ARGUMENT : EndIf
 nonzero=0
 For i=0 To 7 : nonzero=nonzero|PeekA(prefix+i)|PeekA(iid+i) : Next
 If nonzero=0 : ProcedureReturn #IPV6_SLAAC_ARGUMENT : EndIf
 For i=0 To SizeOf(IPv6Slaac)-1 : PokeA(*s+i,0) : Next
 *s\generation=generation : *s\lastNow=now
 For i=0 To 7
  PokeA(@*s\address+i,PeekA(prefix+i)) : PokeA(@*s\address+8+i,PeekA(iid+i))
 Next
 ProcedureReturn 0
EndProcedure
; Apply a validated PIO for this entry's prefix. L and A are independent.
; Return 1 when an address lifetime is newly created (owner MUST perform DAD),
; 0 otherwise. A malformed A lifetime does not discard valid L information.
; authenticated must be 1 only after actual SEND authentication, never merely
; because the source is the current router or the Wi-Fi link is encrypted.
Procedure.i IPv6SlaacApply(*s.IPv6Slaac,generation.i,now.i,onlink.i,autonomous.i,valid.i,preferred.i,authenticated.i)
 Define rc.i,created.i,remaining.i,deadline.i
 rc=ipv6slaac_Valid(*s,generation,now) : If rc<>0 : ProcedureReturn rc : EndIf
 If onlink<0 Or onlink>1 Or autonomous<0 Or autonomous>1 : ProcedureReturn #IPV6_SLAAC_ARGUMENT : EndIf
 If authenticated<0 Or authenticated>1 : ProcedureReturn #IPV6_SLAAC_ARGUMENT : EndIf
 If valid<0 Or valid>$FFFFFFFF Or preferred<0 Or preferred>$FFFFFFFF : ProcedureReturn #IPV6_SLAAC_ARGUMENT : EndIf
 *s\lastNow=now : created=0
 If onlink=1 : *s\onLinkUntil=ipv6slaac_Deadline(now,valid) : EndIf
 If autonomous=0 Or preferred>valid : ProcedureReturn 0 : EndIf
 deadline=ipv6slaac_Deadline(now,valid)
 If *s\validUntil<=now
  If valid=0 : ProcedureReturn 0 : EndIf
  *s\validUntil=deadline : created=1
 Else
  remaining=*s\validUntil-now
  ; Unauthenticated reductions cannot immediately invalidate an address.
  If valid>7200 Or valid*1000>remaining
   *s\validUntil=deadline
  ElseIf remaining<=7200000
   If authenticated=1 : *s\validUntil=deadline : EndIf
  Else
   *s\validUntil=now+7200000
  EndIf
 EndIf
 *s\preferredUntil=ipv6slaac_Deadline(now,preferred)
 ProcedureReturn created
EndProcedure
; Bits: 1 valid lifetime, 2 preferred lifetime, 4 on-link prefix.
; Caller still excludes tentative/duplicate addresses and applies source choice.
Procedure.i IPv6SlaacStatus(*s.IPv6Slaac,generation.i,now.i)
 Define rc.i,status.i
 rc=ipv6slaac_Valid(*s,generation,now) : If rc<>0 : ProcedureReturn rc : EndIf
 *s\lastNow=now : status=0
 If *s\validUntil>now
  status=1 : If *s\preferredUntil>now : status=status|2 : EndIf
 EndIf
 If *s\onLinkUntil>now : status=status|4 : EndIf
 ProcedureReturn status
EndProcedure

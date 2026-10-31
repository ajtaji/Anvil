; RFC 6724 source comparison for assigned public addresses on one selected
; outgoing interface. The caller excludes tentative/expired/foreign addresses.
; No mobility or temporary addresses are assigned by the current owner; router
; to prefix associations are not retained. Equal candidates keep their order.
XIncludeFile "Anvil/Network/ipv6_address.pbi"
Procedure.i ipv6src_Equal(a.i,b.i)
 Define i.i
 For i=0 To 15 : If PeekA(a+i)<>PeekA(b+i) : ProcedureReturn 0 : EndIf : Next
 ProcedureReturn 1
EndProcedure
Procedure.i ipv6src_ZeroPrefix(a.i,n.i)
 Define i.i
 For i=0 To n-1 : If PeekA(a+i)<>0 : ProcedureReturn 0 : EndIf : Next
 ProcedureReturn 1
EndProcedure
Procedure.i IPv6SourceScope(a.i)
 If a=0 : ProcedureReturn -1 : EndIf
 If PeekA(a)=255 : ProcedureReturn PeekA(a+1)&15 : EndIf
 If ipv6src_ZeroPrefix(a,15)<>0 And PeekA(a+15)=1 : ProcedureReturn 2 : EndIf
 If PeekA(a)=254
  If (PeekA(a+1)&192)=128 : ProcedureReturn 2 : EndIf
  If (PeekA(a+1)&192)=192 : ProcedureReturn 5 : EndIf
 EndIf
 ProcedureReturn 14
EndProcedure
Procedure.i IPv6SourceLabel(a.i)
 If a=0 : ProcedureReturn -1 : EndIf
 If ipv6src_ZeroPrefix(a,12)<>0
  If ipv6src_ZeroPrefix(a,15)<>0 And PeekA(a+15)=1 : ProcedureReturn 0 : EndIf
  ProcedureReturn 3
 EndIf
 If ipv6src_ZeroPrefix(a,10)<>0 And PeekA(a+10)=255 And PeekA(a+11)=255 : ProcedureReturn 4 : EndIf
 If PeekA(a)=$20 And PeekA(a+1)=2 : ProcedureReturn 2 : EndIf
 If PeekA(a)=$20 And PeekA(a+1)=1 And PeekA(a+2)=0 And PeekA(a+3)=0 : ProcedureReturn 5 : EndIf
 If (PeekA(a)&254)=$fc : ProcedureReturn 13 : EndIf
 If PeekA(a)=$fe And (PeekA(a+1)&192)=192 : ProcedureReturn 11 : EndIf
 If PeekA(a)=$3f And PeekA(a+1)=$fe : ProcedureReturn 12 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i IPv6SourceCommon(a.i,b.i,prefix.i)
 Define i.i,bit.i,x.i,n.i
 If a=0 Or b=0 Or prefix<0 Or prefix>128 : ProcedureReturn -1 : EndIf
 n=0
 For i=0 To 15
  x=PeekA(a+i)!PeekA(b+i)
  For bit=7 To 0 Step -1
   If n=prefix Or (x&(1<<bit))<>0 : ProcedureReturn n : EndIf
   n=n+1
  Next
 Next
 ProcedureReturn n
EndProcedure
; Returns 1 if candidate beats current, 0 for current/tie, negative for error.
; deprecated flags are 0 preferred, 1 deprecated; prefix lengths cap rule 8.
Procedure.i IPv6SourceBetter(destination.i,candidate.i,candidateDeprecated.i,candidatePrefix.i,current.i,currentDeprecated.i,currentPrefix.i)
 Define a.i,b.i,d.i,sa.i,sb.i
 If destination=0 Or candidate=0 Or current=0 : ProcedureReturn -894 : EndIf
 If candidateDeprecated<0 Or candidateDeprecated>1 Or currentDeprecated<0 Or currentDeprecated>1 : ProcedureReturn -894 : EndIf
 If candidatePrefix<0 Or candidatePrefix>128 Or currentPrefix<0 Or currentPrefix>128 : ProcedureReturn -894 : EndIf
 If PeekA(candidate)=255 Or PeekA(current)=255 Or ipv6src_ZeroPrefix(candidate,16)<>0 Or ipv6src_ZeroPrefix(current,16)<>0 : ProcedureReturn -894 : EndIf
 a=ipv6src_Equal(candidate,destination) : b=ipv6src_Equal(current,destination)
 If a<>b : ProcedureReturn a : EndIf
 sa=IPv6SourceScope(candidate) : sb=IPv6SourceScope(current) : d=IPv6SourceScope(destination)
 If sa<sb : If sa<d : ProcedureReturn 0 : Else : ProcedureReturn 1 : EndIf : EndIf
 If sb<sa : If sb<d : ProcedureReturn 1 : Else : ProcedureReturn 0 : EndIf : EndIf
 If candidateDeprecated<>currentDeprecated : ProcedureReturn 1-candidateDeprecated : EndIf
 d=IPv6SourceLabel(destination)
 a=Bool(IPv6SourceLabel(candidate)=d) : b=Bool(IPv6SourceLabel(current)=d)
 If a<>b : ProcedureReturn a : EndIf
 a=IPv6SourceCommon(candidate,destination,candidatePrefix)
 b=IPv6SourceCommon(current,destination,currentPrefix)
 ProcedureReturn Bool(a>b)
EndProcedure

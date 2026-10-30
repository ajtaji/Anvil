; MLD listener wire codec, independently implemented from protocol facts in
; RFC 9777 sections 5 and 8, RFC 2710 section 3, and RFC 3590 section 4.
; Compose ipv6_neighbor.pbi first. No interface, timer, random or link state.
; Caller owns membership, query destination filtering and report scheduling.
#IPV6_MLD_INVALID = -760
Structure IPv6MldQueryView
 version.i
 maxDelay.i
 robustness.i
 interval.i
 group.i
 sources.i
 sourceCount.i
EndStructure
Procedure.i ipv6mld_Span(p.i,n.i)
 If p<=0 Or n<=0 : ProcedureReturn 0 : EndIf
 If p>$7FFFFFFFFFFFFFFF-n : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i ipv6mld_LinkLocal(p.i)
 If PeekA(p)=254 And (PeekA(p+1)&192)=128 : ProcedureReturn 1 : EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i ipv6mld_Group(p.i)
 Define scope.i,i.i,allnodes.i
 If PeekA(p)<>255 : ProcedureReturn 0 : EndIf
 scope=PeekA(p+1)&15
 If scope<2 Or scope=15 : ProcedureReturn 0 : EndIf
 ; ff02::1 is permanently joined and never reported.
 allnodes=1
 If PeekA(p+1)<>2 Or PeekA(p+15)<>1 : allnodes=0 : EndIf
 For i=2 To 14
  If PeekA(p+i)<>0 : allnodes=0 : EndIf
 Next
 ProcedureReturn 1-allnodes
EndProcedure

; One any-source record: mode 2 current EXCLUDE{}, 4 join EXCLUDE{},
; 3 leave INCLUDE{}. Version 1 maps current/join to Report and leave to Done.
; Returns packet length (72 v1, 76 v2), or INVALID with output unchanged.
Procedure.i IPv6MldReport(out.i,capacity.i,source.i,group.i,version.i,mode.i)
 Define dst.IPv6AddressStorage
 Define n.i,rc.i,i.i,body.i
 If ipv6mld_Span(out,capacity)=0 Or capacity>1500 : ProcedureReturn #IPV6_MLD_INVALID : EndIf
 If ipv6mld_Span(source,16)=0 Or ipv6mld_Span(group,16)=0 : ProcedureReturn #IPV6_MLD_INVALID : EndIf
 If out<source+16 And source<out+capacity : ProcedureReturn #IPV6_MLD_INVALID : EndIf
 If out<group+16 And group<out+capacity : ProcedureReturn #IPV6_MLD_INVALID : EndIf
 If version<>1 And version<>2 : ProcedureReturn #IPV6_MLD_INVALID : EndIf
 If mode<>2 And mode<>3 And mode<>4 : ProcedureReturn #IPV6_MLD_INVALID : EndIf
 If ipv6mld_Group(group)=0 : ProcedureReturn #IPV6_MLD_INVALID : EndIf
 If ipv6mld_LinkLocal(source)=0 And IPv6AddressUnspecified(source)=0 : ProcedureReturn #IPV6_MLD_INVALID : EndIf
 n=24 : If version=2 : n=28 : EndIf
 If capacity<n+48 : ProcedureReturn #IPV6_MLD_INVALID : EndIf
 dst\high=0 : dst\low=0
 If version=2 Or mode=3
  PokeA(@dst,255) : PokeA(@dst+1,2)
  If version=2 : PokeA(@dst+15,22) : Else : PokeA(@dst+15,2) : EndIf
 Else
  For i=0 To 15 : PokeA(@dst+i,PeekA(group+i)) : Next
 EndIf
 rc=IPv6PacketHeader(out,capacity,source,@dst,n+8,0,1,0,0)
 If rc<>40 : ProcedureReturn rc : EndIf
 ; Hop-by-Hop Router Alert value zero, then PadN length zero.
 PokeA(out+40,58) : PokeA(out+41,0) : PokeA(out+42,5) : PokeA(out+43,2)
 PokeA(out+44,0) : PokeA(out+45,0) : PokeA(out+46,1) : PokeA(out+47,0)
 body=out+48
 For i=0 To n-1 : PokeA(body+i,0) : Next
 If version=1
  If mode=3 : PokeA(body,132) : Else : PokeA(body,131) : EndIf
  For i=0 To 15 : PokeA(body+8+i,PeekA(group+i)) : Next
 Else
  PokeA(body,143) : NetWriteBE16(body+6,1) : PokeA(body+8,mode)
  For i=0 To 15 : PokeA(body+12+i,PeekA(group+i)) : Next
 EndIf
 rc=IPv6TransportChecksum(source,@dst,58,body,n) : NetWriteBE16(body+2,rc)
 ProcedureReturn n+48
EndProcedure

; A validated query view borrows packet storage until the caller returns.
; Failure leaves view untouched. Destination ownership belongs to the caller.
; V2 trailing data contributes to checksum but is otherwise ignored.
Procedure.i IPv6MldQuery(packet.i,bytes.i,*query.IPv6MldQueryView)
 Define view.IPv6PacketView
 Define rc.i,at.i,end.i,n.i,kind.i,alerts.i,body.i,version.i,count.i,i.i,delay.i,interval.i
 If ipv6mld_Span(packet,bytes)=0 Or bytes>1500 : ProcedureReturn #IPV6_MLD_INVALID : EndIf
 If ipv6mld_Span(*query,SizeOf(IPv6MldQueryView))=0 : ProcedureReturn #IPV6_MLD_INVALID : EndIf
 If *query<packet+bytes And packet<*query+SizeOf(IPv6MldQueryView) : ProcedureReturn #IPV6_MLD_INVALID : EndIf
 rc=IPv6PacketParse(packet,bytes,@view)
 If rc<>0 : ProcedureReturn #IPV6_MLD_INVALID : EndIf
 If view\protocol<>58 Or view\hopLimit<>1 Or view\fragmented<>0 : ProcedureReturn #IPV6_MLD_INVALID : EndIf
 If ipv6mld_LinkLocal(view\source)=0 Or PeekA(packet+6)<>0 : ProcedureReturn #IPV6_MLD_INVALID : EndIf
 ; Parser has bounded this first Hop-by-Hop header and every option span.
 end=40+(PeekA(packet+41)+1)*8 : at=42 : alerts=0
 While at<end
  kind=PeekA(packet+at)
  If kind=0
   at=at+1
  Else
   n=PeekA(packet+at+1)
   If kind=5
    If n<>2 : ProcedureReturn #IPV6_MLD_INVALID : EndIf
    If NetReadBE16(packet+at+2)<>0 : ProcedureReturn #IPV6_MLD_INVALID : EndIf
    alerts=alerts+1
   EndIf
   at=at+n+2
  EndIf
 Wend
 If alerts<>1 Or view\payloadBytes<24 : ProcedureReturn #IPV6_MLD_INVALID : EndIf
 body=view\payload
 If PeekA(body)<>130 : ProcedureReturn #IPV6_MLD_INVALID : EndIf
 If IPv6TransportChecksum(view\source,view\destination,58,body,view\payloadBytes)<>0 : ProcedureReturn #IPV6_MLD_INVALID : EndIf
 version=1 : count=0 : interval=0
 delay=NetReadBE16(body+4)
 If view\payloadBytes<>24
  If view\payloadBytes<28 : ProcedureReturn #IPV6_MLD_INVALID : EndIf
  version=2 : count=NetReadBE16(body+26)
  If count>(view\payloadBytes-28)/16 : ProcedureReturn #IPV6_MLD_INVALID : EndIf
  If delay>=32768 : delay=((delay&4095)|4096)<<(((delay>>12)&7)+3) : EndIf
  interval=PeekA(body+25)
  If interval>=128 : interval=((interval&15)|16)<<(((interval>>4)&7)+3) : EndIf
  For i=0 To count-1
   at=body+28+i*16
   If PeekA(at)=255 Or IPv6AddressUnspecified(at)<>0 : ProcedureReturn #IPV6_MLD_INVALID : EndIf
  Next
 EndIf
 If IPv6AddressUnspecified(body+8)<>0
  If count<>0 : ProcedureReturn #IPV6_MLD_INVALID : EndIf
 Else
  If PeekA(body+8)<>255 : ProcedureReturn #IPV6_MLD_INVALID : EndIf
 EndIf
 *query\version=version : *query\maxDelay=delay : *query\interval=interval
 *query\robustness=0 : If version=2 : *query\robustness=PeekA(body+24)&7 : EndIf
 *query\group=body+8 : *query\sources=0 : *query\sourceCount=count
 If count>0 : *query\sources=body+28 : EndIf
 ProcedureReturn 0
EndProcedure

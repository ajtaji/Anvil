; Shared Ethernet neighbor-discovery message validation (RFC 4861 sections
; 6.1 and 7.1; RFC 6980 prohibits even atomic fragments in ND messages).
; This codec owns no cache, routes, timers, address configuration or link I/O.
XIncludeFile "Anvil/Network/ipv6_address.pbi"
XIncludeFile "Anvil/Network/ipv6_packet.pbi"
#IPV6_ND_INVALID = -720
#IPV6_ND_CHECKSUM = -721
#IPV6_ND_TYPE = -722
Structure IPv6NeighborView
 kind.i
 body.i
 bytes.i
 target.i
 flags.i
 options.i
 optionBytes.i
 sourceMac.i
 targetMac.i
EndStructure

Procedure.i IPv6AddressUnspecified(address.i)
 Define i.i
 If address=0 : ProcedureReturn -1 : EndIf
 For i=0 To 15
  If PeekA(address+i)<>0 : ProcedureReturn 0 : EndIf
 Next
 ProcedureReturn 1
EndProcedure

; RFC 4861 section 4.1: ask all routers on this link for advertisements.
; Before address assignment, omit the source link-layer option. The caller
; owns source-address selection, interface membership and solicitation timing.
Procedure.i IPv6RouterSolicit(out.i,capacity.i,source.i,mac.i)
 Define dst.IPv6AddressStorage
 Define i.i,n.i,rc.i,unspecified.i
 If out=0 Or source=0 : ProcedureReturn #IPV6_ND_INVALID : EndIf
 If capacity<48 : ProcedureReturn #IPV6_ND_INVALID : EndIf
 If out<source+16 And source<out+capacity : ProcedureReturn #IPV6_ND_INVALID : EndIf
 If PeekA(source)=255 : ProcedureReturn #IPV6_ND_INVALID : EndIf
 unspecified=IPv6AddressUnspecified(source) : n=8
 If unspecified=0
  If mac=0 Or capacity<56 : ProcedureReturn #IPV6_ND_INVALID : EndIf
  If out<mac+6 And mac<out+capacity : ProcedureReturn #IPV6_ND_INVALID : EndIf
  If (PeekA(mac)&1)<>0 : ProcedureReturn #IPV6_ND_INVALID : EndIf
  n=16
 EndIf
 dst\high=0 : dst\low=0
 PokeA(@dst,255) : PokeA(@dst+1,2) : PokeA(@dst+15,2)
 rc=IPv6PacketHeader(out,capacity,source,@dst,n,58,255,0,0)
 If rc<>40 : ProcedureReturn rc : EndIf
 For i=0 To n-1 : PokeA(out+40+i,0) : Next
 PokeA(out+40,133)
 If n=16
  PokeA(out+48,1) : PokeA(out+49,1)
  For i=0 To 5 : PokeA(out+50+i,PeekA(mac+i)) : Next
 EndIf
 rc=IPv6TransportChecksum(source,@dst,58,out+40,n)
 NetWriteBE16(out+42,rc)
 ProcedureReturn n+40
EndProcedure

; Build a complete IPv6 Neighbor Solicitation. An unspecified source emits
; the DAD form without a link-layer option. Other sources require a six-byte
; Ethernet MAC. Input spans must be separate from the output capacity.
Procedure.i IPv6NeighborSolicit(out.i,capacity.i,source.i,target.i,mac.i)
 Define dst.IPv6AddressStorage
 Define i.i,n.i,rc.i,unspecified.i
 If out=0 Or source=0 Or target=0 : ProcedureReturn #IPV6_ND_INVALID : EndIf
 If capacity<64 : ProcedureReturn #IPV6_ND_INVALID : EndIf
 If out<source+16 And source<out+capacity : ProcedureReturn #IPV6_ND_INVALID : EndIf
 If out<target+16 And target<out+capacity : ProcedureReturn #IPV6_ND_INVALID : EndIf
 If PeekA(source)=255 Or PeekA(target)=255 : ProcedureReturn #IPV6_ND_INVALID : EndIf
 rc=IPv6AddressUnspecified(target)
 If rc<>0 : ProcedureReturn #IPV6_ND_INVALID : EndIf
 unspecified=IPv6AddressUnspecified(source) : n=24
 If unspecified=0
  If mac=0 Or capacity<72 : ProcedureReturn #IPV6_ND_INVALID : EndIf
  If out<mac+6 And mac<out+capacity : ProcedureReturn #IPV6_ND_INVALID : EndIf
  If (PeekA(mac)&1)<>0 : ProcedureReturn #IPV6_ND_INVALID : EndIf
  n=32
 EndIf
 rc=IPv6SolicitedNode(target,@dst)
 rc=IPv6PacketHeader(out,capacity,source,@dst,n,58,255,0,0)
 If rc<>40 : ProcedureReturn rc : EndIf
 For i=0 To n-1 : PokeA(out+40+i,0) : Next
 PokeA(out+40,135)
 For i=0 To 15 : PokeA(out+48+i,PeekA(target+i)) : Next
 If n=32
  PokeA(out+64,1) : PokeA(out+65,1)
  For i=0 To 5 : PokeA(out+66+i,PeekA(mac+i)) : Next
 EndIf
 rc=IPv6TransportChecksum(source,@dst,58,out+40,n)
 NetWriteBE16(out+42,rc)
 ProcedureReturn n+40
EndProcedure

; Build an Ethernet Neighbor Advertisement for an address owned by this
; interface. Flags are the R/S/O bits in positions 31/30/29; reserved bits
; must be zero. A multicast destination forbids the solicited flag.
Procedure.i IPv6NeighborAdvertise(out.i,capacity.i,source.i,destination.i,mac.i,flags.i)
 Define i.i,rc.i
 If out=0 Or source=0 Or destination=0 : ProcedureReturn #IPV6_ND_INVALID : EndIf
 If mac=0 Or capacity<72 : ProcedureReturn #IPV6_ND_INVALID : EndIf
 If (flags & $FFFFFFFF)<>flags : ProcedureReturn #IPV6_ND_INVALID : EndIf
 If (flags & $1FFFFFFF)<>0 : ProcedureReturn #IPV6_ND_INVALID : EndIf
 If out<source+16 And source<out+capacity : ProcedureReturn #IPV6_ND_INVALID : EndIf
 If out<destination+16 And destination<out+capacity : ProcedureReturn #IPV6_ND_INVALID : EndIf
 If out<mac+6 And mac<out+capacity : ProcedureReturn #IPV6_ND_INVALID : EndIf
 If PeekA(source)=255 Or (PeekA(mac)&1)<>0 : ProcedureReturn #IPV6_ND_INVALID : EndIf
 rc=IPv6AddressUnspecified(source)
 If rc<>0 : ProcedureReturn #IPV6_ND_INVALID : EndIf
 rc=IPv6AddressUnspecified(destination)
 If rc<>0 : ProcedureReturn #IPV6_ND_INVALID : EndIf
 If PeekA(destination)=255
  If (flags & $40000000)<>0 : ProcedureReturn #IPV6_ND_INVALID : EndIf
 EndIf
 rc=IPv6PacketHeader(out,capacity,source,destination,32,58,255,0,0)
 If rc<>40 : ProcedureReturn rc : EndIf
 For i=0 To 31 : PokeA(out+40+i,0) : Next
 PokeA(out+40,136) : NetWriteBE32(out+44,flags)
 For i=0 To 15 : PokeA(out+48+i,PeekA(source+i)) : Next
 PokeA(out+64,2) : PokeA(out+65,1)
 For i=0 To 5 : PokeA(out+66+i,PeekA(mac+i)) : Next
 rc=IPv6TransportChecksum(source,destination,58,out+40,32)
 NetWriteBE16(out+42,rc)
 ProcedureReturn 72
EndProcedure

; Caller supplies separate readable target and writable 16-byte result.
Procedure.i IPv6SolicitedNode(target.i,out.i)
 Define i.i
 If target=0 Or out=0 : ProcedureReturn -1 : EndIf
 If out<target+16 And target<out+16 : ProcedureReturn -1 : EndIf
 For i=0 To 15 : PokeA(out+i,0) : Next
 PokeA(out,255) : PokeA(out+1,2) : PokeA(out+11,1) : PokeA(out+12,255)
 For i=13 To 15 : PokeA(out+i,PeekA(target+i)) : Next
 ProcedureReturn 0
EndProcedure

; 0 valid, negative refusal. Views borrow the immutable packet span.
; A valid message still requires endpoint state/policy before any cache update.
Procedure.i IPv6NeighborParse(packet.i,bytes.i,*ip.IPv6PacketView,*nd.IPv6NeighborView)
 Define rc.i,p.i,n.i,kind.i,base.i,i.i,at.i,option.i,length.i,unspecified.i
 Define solicited.IPv6AddressStorage
 If *nd=0 Or *ip=0 : ProcedureReturn #IPV6_ND_INVALID : EndIf
 If *nd<*ip+SizeOf(IPv6PacketView) And *ip<*nd+SizeOf(IPv6NeighborView) : ProcedureReturn #IPV6_ND_INVALID : EndIf
 If packet<>0 And bytes>0
  If *nd<packet+bytes And packet<*nd+SizeOf(IPv6NeighborView) : ProcedureReturn #IPV6_ND_INVALID : EndIf
 EndIf
 For i=0 To SizeOf(IPv6NeighborView)-1 : PokeA(*nd+i,0) : Next
 rc=IPv6PacketParse(packet,bytes,*ip)
 If rc<>0 : ProcedureReturn rc : EndIf
 If *ip\protocol<>58 Or *ip\hopLimit<>255 : ProcedureReturn #IPV6_ND_INVALID : EndIf
 ; The packet view's fragment flag includes atomic fragments.
 If *ip\fragmented<>0 : ProcedureReturn #IPV6_ND_INVALID : EndIf
 p=*ip\payload : n=*ip\payloadBytes
 If n<8 : ProcedureReturn #IPV6_ND_INVALID : EndIf
 If PeekA(p+1)<>0 : ProcedureReturn #IPV6_ND_INVALID : EndIf
 If PeekA(*ip\source)=255 : ProcedureReturn #IPV6_ND_INVALID : EndIf
 rc=IPv6TransportChecksum(*ip\source,*ip\destination,58,p,n)
 If rc<>0 : ProcedureReturn #IPV6_ND_CHECKSUM : EndIf
 kind=PeekA(p) : unspecified=IPv6AddressUnspecified(*ip\source)
 Select kind
  Case 133
   base=8
  Case 134
   base=16
   If PeekA(*ip\source)<>254 : ProcedureReturn #IPV6_ND_INVALID : EndIf
   If (PeekA(*ip\source+1)&192)<>128 : ProcedureReturn #IPV6_ND_INVALID : EndIf
  Case 135
   base=24
  Case 136
   base=24
   If unspecified<>0 : ProcedureReturn #IPV6_ND_INVALID : EndIf
  Default
   ProcedureReturn #IPV6_ND_TYPE
 EndSelect
 If n<base : ProcedureReturn #IPV6_ND_INVALID : EndIf
 If kind=135 Or kind=136
  If PeekA(p+8)=255 : ProcedureReturn #IPV6_ND_INVALID : EndIf
  rc=IPv6AddressUnspecified(p+8)
  If rc<>0 : ProcedureReturn #IPV6_ND_INVALID : EndIf
  *nd\target=p+8
 EndIf
 If kind=136
  *nd\flags=NetReadBE32(p+4)
  If PeekA(*ip\destination)=255
   If (*nd\flags & $40000000)<>0 : ProcedureReturn #IPV6_ND_INVALID : EndIf
  EndIf
 EndIf
 at=base
 While at<n
  If n-at<2 : ProcedureReturn #IPV6_ND_INVALID : EndIf
  option=PeekA(p+at) : length=PeekA(p+at+1)*8
  If length=0 Or length>n-at : ProcedureReturn #IPV6_ND_INVALID : EndIf
  If option=1 Or option=2
   If length<>8 : ProcedureReturn #IPV6_ND_INVALID : EndIf
   If (PeekA(p+at+2)&1)<>0 : ProcedureReturn #IPV6_ND_INVALID : EndIf
   If option=1
    If *nd\sourceMac<>0 : ProcedureReturn #IPV6_ND_INVALID : EndIf
    *nd\sourceMac=p+at+2
   Else
    If *nd\targetMac<>0 : ProcedureReturn #IPV6_ND_INVALID : EndIf
    *nd\targetMac=p+at+2
   EndIf
  EndIf
  at=at+length
 Wend
 If unspecified<>0
  If *nd\sourceMac<>0 : ProcedureReturn #IPV6_ND_INVALID : EndIf
  If kind=135
   rc=IPv6SolicitedNode(p+8,@solicited)
   rc=IPv6AddressPrefix(@solicited,*ip\destination,128)
   If rc<>1 : ProcedureReturn #IPV6_ND_INVALID : EndIf
  EndIf
 EndIf
 *nd\kind=kind : *nd\body=p : *nd\bytes=n
 *nd\options=p+base : *nd\optionBytes=n-base
 ProcedureReturn 0
EndProcedure

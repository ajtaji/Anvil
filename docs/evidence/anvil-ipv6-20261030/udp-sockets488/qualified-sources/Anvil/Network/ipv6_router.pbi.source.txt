; Router Advertisement copy-out codec, RFC 4861 sections 4.2, 4.6, 6.1.2,
; 6.3.4. Compose ipv6_neighbor first. No route/address/timer/device ownership.
; The caller filters Ethernet destination and scopes results to its interface.
; Unspecified fields stay zero; the owner must preserve previously learned
; values in that case. Prefix records preserve wire order, including repeats.
#IPV6_RA_ARGUMENT=-830
#IPV6_RA_CAPACITY=-831
#IPV6_RA_DESTINATION=-832
Structure IPv6RouterAdvertisement
 source.IPv6AddressStorage
 mac.q
 hasMac.i
 hopLimit.i
 flags.i
 lifetime.i
 reachable.i
 retransmit.i
 mtu.i
 prefixCount.i
EndStructure
Structure IPv6RouterPrefix
 length.i
 onlink.i
 autonomous.i
 valid.i
 preferred.i
 prefix.IPv6AddressStorage
EndStructure
Procedure.i ipv6ra_Span(p.i,n.i)
 If p<=0 Or n<=0 : ProcedureReturn 0 : EndIf
 If p>$7FFFFFFFFFFFFFFF-n : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i ipv6ra_Separate(a.i,an.i,b.i,bn.i)
 If a<b+bn And b<a+an : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
; PIOs with unusable length or link-local/multicast prefixes are ignored.
; Other prefix lengths remain usable for on-link routing even when SLAAC
; cannot combine them with this interface's identifier length.
Procedure.i ipv6ra_Prefix(option.i,bytes.i)
 If bytes<>32 : ProcedureReturn 0 : EndIf
 If PeekA(option+2)>128 : ProcedureReturn 0 : EndIf
 If PeekA(option+2)>=8 And PeekA(option+16)=255 : ProcedureReturn 0 : EndIf
 If PeekA(option+2)>=10 And PeekA(option+16)=254 And (PeekA(option+17)&192)=128 : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
; local=0 accepts all-nodes multicast only. Otherwise local points to an
; assigned unicast address. prefixCapacity counts 56-byte records, 0..2048.
; Every refusal preserves both output spans. Successful output has no pointers
; into the packet. Unknown and unusable known options are ignored, not exposed.
Procedure.i IPv6RouterDecode(packet.i,bytes.i,local.i,linkMtu.i,*out.IPv6RouterAdvertisement,prefixes.i,prefixCapacity.i)
 Define ip.IPv6PacketView,nd.IPv6NeighborView,allnodes.IPv6AddressStorage
 Define *row.IPv6RouterPrefix
 Define rc.i,i.i,p.i,n.i,at.i,length.i,count.i,mtu.i,bits.i,value.i,capacityBytes.i
 If bytes<40 Or bytes>65575 Or ipv6ra_Span(packet,bytes)=0 : ProcedureReturn #IPV6_RA_ARGUMENT : EndIf
 If ipv6ra_Span(*out,SizeOf(IPv6RouterAdvertisement))=0 : ProcedureReturn #IPV6_RA_ARGUMENT : EndIf
 If linkMtu<1280 Or linkMtu>65535 Or prefixCapacity<0 Or prefixCapacity>2048 : ProcedureReturn #IPV6_RA_ARGUMENT : EndIf
 If ipv6ra_Separate(packet,bytes,*out,SizeOf(IPv6RouterAdvertisement))=0 : ProcedureReturn #IPV6_RA_ARGUMENT : EndIf
 capacityBytes=prefixCapacity*SizeOf(IPv6RouterPrefix)
 If prefixCapacity>0
  If ipv6ra_Span(prefixes,capacityBytes)=0 : ProcedureReturn #IPV6_RA_ARGUMENT : EndIf
  If ipv6ra_Separate(packet,bytes,prefixes,capacityBytes)=0 Or ipv6ra_Separate(*out,SizeOf(IPv6RouterAdvertisement),prefixes,capacityBytes)=0 : ProcedureReturn #IPV6_RA_ARGUMENT : EndIf
 EndIf
 If local<>0
  If ipv6ra_Span(local,16)=0 : ProcedureReturn #IPV6_RA_ARGUMENT : EndIf
  If PeekA(local)=255 Or IPv6AddressUnspecified(local)<>0 : ProcedureReturn #IPV6_RA_ARGUMENT : EndIf
  If ipv6ra_Separate(local,16,*out,SizeOf(IPv6RouterAdvertisement))=0 : ProcedureReturn #IPV6_RA_ARGUMENT : EndIf
  If prefixCapacity>0
   If ipv6ra_Separate(local,16,prefixes,capacityBytes)=0 : ProcedureReturn #IPV6_RA_ARGUMENT : EndIf
  EndIf
 EndIf
 rc=IPv6NeighborParse(packet,bytes,@ip,@nd) : If rc<>0 : ProcedureReturn rc : EndIf
 If nd\kind<>134 : ProcedureReturn #IPV6_ND_TYPE : EndIf
 allnodes\high=0 : allnodes\low=0
 PokeA(@allnodes,255) : PokeA(@allnodes+1,2) : PokeA(@allnodes+15,1)
 rc=IPv6AddressPrefix(ip\destination,@allnodes,128)
 If rc<>1
  If local=0 : ProcedureReturn #IPV6_RA_DESTINATION : EndIf
  If IPv6AddressPrefix(ip\destination,local,128)<>1 : ProcedureReturn #IPV6_RA_DESTINATION : EndIf
 EndIf
 ; First pass guarantees capacity before touching either output.
 p=nd\options : n=nd\optionBytes : at=0 : count=0 : mtu=0
 While at<n
  length=PeekA(p+at+1)*8
  If PeekA(p+at)=3
   If ipv6ra_Prefix(p+at,length)<>0 : count=count+1 : EndIf
  ElseIf PeekA(p+at)=5 And length=8
   value=NetReadBE32(p+at+4)
   If value>=1280 And value<=linkMtu : mtu=value : EndIf
  EndIf
  at=at+length
 Wend
 If count>prefixCapacity : ProcedureReturn #IPV6_RA_CAPACITY : EndIf
 For i=0 To SizeOf(IPv6RouterAdvertisement)-1 : PokeA(*out+i,0) : Next
 For i=0 To 15 : PokeA(@*out\source+i,PeekA(ip\source+i)) : Next
 If nd\sourceMac<>0
  *out\hasMac=1
  For i=0 To 5 : PokeA(@*out\mac+i,PeekA(nd\sourceMac+i)) : Next
 EndIf
 *out\hopLimit=PeekA(nd\body+4) : *out\flags=PeekA(nd\body+5)
 *out\lifetime=NetReadBE16(nd\body+6)
 *out\reachable=NetReadBE32(nd\body+8) : *out\retransmit=NetReadBE32(nd\body+12)
 *out\mtu=mtu : *out\prefixCount=count
 at=0 : count=0
 While at<n
  length=PeekA(p+at+1)*8
  If PeekA(p+at)=3 And ipv6ra_Prefix(p+at,length)<>0
   *row=prefixes+count*SizeOf(IPv6RouterPrefix) : count=count+1
   *row\length=PeekA(p+at+2) : *row\onlink=(PeekA(p+at+3)>>7)&1
   *row\autonomous=(PeekA(p+at+3)>>6)&1
   *row\valid=NetReadBE32(p+at+4) : *row\preferred=NetReadBE32(p+at+8)
   ; Host bits are not prefix identity, including for non-octet lengths.
   For i=0 To 15
    bits=*row\length-i*8 : value=0
    If bits>=8
     value=PeekA(p+at+16+i)
    ElseIf bits>0
     value=PeekA(p+at+16+i)&(255<<(8-bits))
    EndIf
    PokeA(@*row\prefix+i,value)
   Next
  EndIf
  at=at+length
 Wend
 ProcedureReturn 0
EndProcedure

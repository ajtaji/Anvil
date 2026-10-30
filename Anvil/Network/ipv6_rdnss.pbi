; Recursive DNS server advertisement copy-out, RFC 8106 sections 5.1/5.3.1.
; Independent codec: no resolver, interface, timer or device ownership.
; The caller retains the receiving link identity and applies each lifetime.
XIncludeFile "Anvil/Network/ipv6_neighbor.pbi"
#IPV6_RDNSS_ARGUMENT=-910
#IPV6_RDNSS_CAPACITY=-911
#IPV6_RDNSS_DESTINATION=-912
Structure IPv6RdnssAdvertisement
 address.IPv6AddressStorage
 seconds.i
EndStructure
Procedure.i ipv6rdnss_Span(p.i,n.i)
 If p<=0 Or n<=0 : ProcedureReturn 0 : EndIf
 If p>$7FFFFFFFFFFFFFFF-n : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i ipv6rdnss_Separate(a.i,an.i,b.i,bn.i)
 If a<b+bn And b<a+an : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
; An invalid address discards its entire option, not just that address.
; The ND parser already bounds every option, including unknown types.
Procedure.i ipv6rdnss_Option(option.i,bytes.i)
 Define i.i,j.i,value.i
 If bytes<24 Or ((bytes-8) % 16)<>0 : ProcedureReturn 0 : EndIf
 For i=8 To bytes-1 Step 16
  If PeekA(option+i)=255 : ProcedureReturn 0 : EndIf
  value=0
  For j=0 To 15 : value=value|PeekA(option+i+j) : Next
  If value=0 : ProcedureReturn 0 : EndIf
 Next
 ProcedureReturn (bytes-8)/16
EndProcedure
; Returns copied record count or a negative refusal. Output is unchanged
; on every refusal. Invalid DNS options are skipped; invalid ND envelopes
; refuse the whole packet. Multiple options and duplicates retain wire order.
; Zero and infinite lifetimes are copied exactly for the repository owner.
Procedure.i IPv6RdnssDecode(packet.i,bytes.i,local.i,rows.i,capacity.i)
 Define ip.IPv6PacketView,nd.IPv6NeighborView,allnodes.IPv6AddressStorage
 Define *row.IPv6RdnssAdvertisement
 Define rc.i,p.i,n.i,at.i,length.i,count.i,valid.i,i.i,j.i,span.i
 If bytes<40 Or bytes>65575 Or ipv6rdnss_Span(packet,bytes)=0 : ProcedureReturn #IPV6_RDNSS_ARGUMENT : EndIf
 If capacity<0 Or capacity>4096 : ProcedureReturn #IPV6_RDNSS_ARGUMENT : EndIf
 span=capacity*SizeOf(IPv6RdnssAdvertisement)
 If capacity>0
  If ipv6rdnss_Span(rows,span)=0 : ProcedureReturn #IPV6_RDNSS_ARGUMENT : EndIf
  If ipv6rdnss_Separate(packet,bytes,rows,span)=0 : ProcedureReturn #IPV6_RDNSS_ARGUMENT : EndIf
 EndIf
 If local<>0
  If ipv6rdnss_Span(local,16)=0 : ProcedureReturn #IPV6_RDNSS_ARGUMENT : EndIf
  If PeekA(local)=255 Or IPv6AddressUnspecified(local)<>0 : ProcedureReturn #IPV6_RDNSS_ARGUMENT : EndIf
  If capacity>0
   If ipv6rdnss_Separate(local,16,rows,span)=0 : ProcedureReturn #IPV6_RDNSS_ARGUMENT : EndIf
  EndIf
 EndIf
 rc=IPv6NeighborParse(packet,bytes,@ip,@nd) : If rc<>0 : ProcedureReturn rc : EndIf
 If nd\kind<>134 : ProcedureReturn #IPV6_ND_TYPE : EndIf
 allnodes\high=0 : allnodes\low=0
 PokeA(@allnodes,255) : PokeA(@allnodes+1,2) : PokeA(@allnodes+15,1)
 If IPv6AddressPrefix(ip\destination,@allnodes,128)<>1
  If local=0 : ProcedureReturn #IPV6_RDNSS_DESTINATION : EndIf
  If IPv6AddressPrefix(ip\destination,local,128)<>1 : ProcedureReturn #IPV6_RDNSS_DESTINATION : EndIf
 EndIf
 p=nd\options : n=nd\optionBytes : at=0 : count=0
 While at<n
  length=PeekA(p+at+1)*8
  If PeekA(p+at)=25 : count=count+ipv6rdnss_Option(p+at,length) : EndIf
  at=at+length
 Wend
 If count>capacity : ProcedureReturn #IPV6_RDNSS_CAPACITY : EndIf
 ; No output write precedes complete validation and capacity accounting.
 at=0 : count=0
 While at<n
  length=PeekA(p+at+1)*8
  If PeekA(p+at)=25
   valid=ipv6rdnss_Option(p+at,length)
   For i=0 To valid-1
    *row=rows+count*SizeOf(IPv6RdnssAdvertisement)
    For j=0 To 15 : PokeA(@*row\address+j,PeekA(p+at+8+i*16+j)) : Next
    *row\seconds=NetReadBE32(p+at+4) : count=count+1
   Next
  EndIf
  at=at+length
 Wend
 ProcedureReturn count
EndProcedure

; Shared UDP/IPv6 wire boundary, RFC 768 and RFC 8200 section 8.1.
; Reuses the IPv6 extension parser and checksum implementation. No socket,
; route, neighbor, link or allocation state. Address ownership/scope, port
; binding and multicast membership remain endpoint responsibilities.
XIncludeFile "Anvil/Network/ipv6_packet.pbi"
#IPV6_UDP_ARGUMENT=-3501
#IPV6_UDP_HEADER=-3502
#IPV6_UDP_CHECKSUM=-3503
#IPV6_UDP_PROTOCOL=-3504
Structure IPv6UdpView
 datagram.i
 datagramBytes.i
 source.i
 destination.i
 sourcePort.i
 destinationPort.i
 data.i
 dataBytes.i
EndStructure
Procedure.i IPv6UdpSpanValid(p.i,n.i)
 If p<=0 Or n<0 Or p>$7FFFFFFFFFFFFFFF-n : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
; Caller prepares ports and data at out+40. Length/checksum are overwritten
; on every emission, including a computed checksum of zero (sent as FFFF).
; Address storage must be separate from the entire output capacity. Refusal
; changes nothing. This ordinary-packet API does not support jumbograms.
Procedure.i IPv6UdpBuild(out.i,capacity.i,source.i,destination.i,datagramBytes.i,hops.i)
 Define rc.i
 If capacity<48 Or capacity>65575 Or datagramBytes<8 Or datagramBytes>capacity-40 Or hops<1 Or hops>255 : ProcedureReturn #IPV6_UDP_ARGUMENT : EndIf
 If IPv6UdpSpanValid(out,capacity)=0 Or IPv6UdpSpanValid(source,16)=0 Or IPv6UdpSpanValid(destination,16)=0 : ProcedureReturn #IPV6_UDP_ARGUMENT : EndIf
 If (out<source+16 And source<out+capacity) Or (out<destination+16 And destination<out+capacity) : ProcedureReturn #IPV6_UDP_ARGUMENT : EndIf
 rc=IPv6PacketHeader(out,capacity,source,destination,datagramBytes,17,hops,0,0)
 If rc<>40 : ProcedureReturn rc : EndIf
 NetWriteBE16(out+44,datagramBytes) : NetWriteBE16(out+46,0)
 rc=IPv6TransportChecksum(source,destination,17,out+40,datagramBytes)
 If rc=0 : rc=65535 : EndIf
 NetWriteBE16(out+46,rc)
 ProcedureReturn 40+datagramBytes
EndProcedure
; On failure the borrowed view is unchanged. A zero checksum is refused:
; this API does not implement the special zero-checksum tunnel exceptions.
; Bytes beyond the UDP length, or beyond the IPv6 packet, are not UDP data
; and do not enter its checksum. Non-atomic fragments need reassembly first.
Procedure.i IPv6UdpParse(packet.i,bytes.i,*view.IPv6UdpView)
 Define ip.IPv6PacketView,n.i,rc.i
 If bytes<0 Or bytes>65575 Or IPv6UdpSpanValid(packet,bytes)=0 Or IPv6UdpSpanValid(*view,SizeOf(IPv6UdpView))=0 : ProcedureReturn #IPV6_UDP_ARGUMENT : EndIf
 If *view<packet+bytes And packet<*view+SizeOf(IPv6UdpView) : ProcedureReturn #IPV6_UDP_ARGUMENT : EndIf
 rc=IPv6PacketParse(packet,bytes,@ip)
 If rc<>0 : ProcedureReturn rc : EndIf
 If ip\protocol<>17 : ProcedureReturn #IPV6_UDP_PROTOCOL : EndIf
 If ip\payloadBytes<8 : ProcedureReturn #IPV6_UDP_HEADER : EndIf
 n=NetReadBE16(ip\payload+4)
 If n<8 Or n>ip\payloadBytes : ProcedureReturn #IPV6_UDP_HEADER : EndIf
 If NetReadBE16(ip\payload+6)=0 : ProcedureReturn #IPV6_UDP_CHECKSUM : EndIf
 rc=IPv6TransportChecksum(ip\source,ip\destination,17,ip\payload,n)
 If rc<>0 : ProcedureReturn #IPV6_UDP_CHECKSUM : EndIf
 *view\datagram=ip\payload : *view\datagramBytes=n
 *view\source=ip\source : *view\destination=ip\destination
 *view\sourcePort=NetReadBE16(ip\payload) : *view\destinationPort=NetReadBE16(ip\payload+2)
 *view\data=ip\payload+8 : *view\dataBytes=n-8
 ProcedureReturn 0
EndProcedure

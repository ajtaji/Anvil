; Shared TCP-over-IPv6 wire boundary, RFC 8200 section 8.1 and RFC 9293.
; No socket, route, neighbor, allocation or link ownership. The endpoint
; must verify destination ownership and select its assigned source.
XIncludeFile "Anvil/Network/ipv6_packet.pbi"
#IPV6_TCP_ARGUMENT = -890
#IPV6_TCP_HEADER = -891
#IPV6_TCP_CHECKSUM = -892
#IPV6_TCP_PROTOCOL = -893
Structure IPv6TcpView
 segment.i
 segmentBytes.i
 source.i
 destination.i
 sourcePort.i
 destinationPort.i
 headerBytes.i
 data.i
 dataBytes.i
EndStructure

Procedure.i ipv6tcp_Unicast(address.i)
 ProcedureReturn IPv6UnicastAddress(address)
EndProcedure

; Addresses must be separate from the complete writable packet. The caller
; has already built a TCP segment at out+40. Refusal leaves it unchanged.
; Repeated emission overwrites the old checksum, including a legitimate zero.
Procedure.i IPv6TcpBuild(out.i,capacity.i,source.i,destination.i,segmentBytes.i,hops.i)
 Define header.i,rc.i
 If out=0 Or capacity<60 Or capacity>65575 : ProcedureReturn #IPV6_TCP_ARGUMENT : EndIf
 If segmentBytes<20 Or segmentBytes>capacity-40 : ProcedureReturn #IPV6_TCP_ARGUMENT : EndIf
 If hops<1 Or hops>255 : ProcedureReturn #IPV6_TCP_ARGUMENT : EndIf
 If ipv6tcp_Unicast(source)=0 Or ipv6tcp_Unicast(destination)=0 : ProcedureReturn #IPV6_TCP_ARGUMENT : EndIf
 If out<source+16 And source<out+capacity : ProcedureReturn #IPV6_TCP_ARGUMENT : EndIf
 If out<destination+16 And destination<out+capacity : ProcedureReturn #IPV6_TCP_ARGUMENT : EndIf
 header=(PeekA(out+52)>>4)*4
 If header<20 Or header>segmentBytes : ProcedureReturn #IPV6_TCP_HEADER : EndIf
 rc=IPv6PacketHeader(out,capacity,source,destination,segmentBytes,6,hops,0,0)
 If rc<>40 : ProcedureReturn rc : EndIf
 NetWriteBE16(out+56,0)
 rc=IPv6TransportChecksum(source,destination,6,out+40,segmentBytes)
 NetWriteBE16(out+56,rc)
 ProcedureReturn segmentBytes+40
EndProcedure

; Packet extensions are validated by the shared packet parser. Reassembly
; is required for non-atomic fragments; padding after the IPv6 packet is
; never part of the TCP checksum or application payload. On failure the
; view is unchanged. It borrows packet storage until the caller releases it.
Procedure.i IPv6TcpParse(packet.i,bytes.i,*view.IPv6TcpView)
 Define ip.IPv6PacketView
 Define rc.i,header.i
 If packet=0 Or *view=0 Or bytes<0 Or bytes>65575 : ProcedureReturn #IPV6_TCP_ARGUMENT : EndIf
 If *view<packet+bytes And packet<*view+SizeOf(IPv6TcpView) : ProcedureReturn #IPV6_TCP_ARGUMENT : EndIf
 rc=IPv6PacketParse(packet,bytes,@ip)
 If rc<>0 : ProcedureReturn rc : EndIf
 If ip\protocol<>6 : ProcedureReturn #IPV6_TCP_PROTOCOL : EndIf
 If ipv6tcp_Unicast(ip\source)=0 Or ipv6tcp_Unicast(ip\destination)=0 : ProcedureReturn #IPV6_TCP_ARGUMENT : EndIf
 If ip\payloadBytes<20 : ProcedureReturn #IPV6_TCP_HEADER : EndIf
 header=(PeekA(ip\payload+12)>>4)*4
 If header<20 Or header>ip\payloadBytes : ProcedureReturn #IPV6_TCP_HEADER : EndIf
 rc=IPv6TransportChecksum(ip\source,ip\destination,6,ip\payload,ip\payloadBytes)
 If rc<>0 : ProcedureReturn #IPV6_TCP_CHECKSUM : EndIf
 *view\segment=ip\payload : *view\segmentBytes=ip\payloadBytes
 *view\source=ip\source : *view\destination=ip\destination
 *view\sourcePort=NetReadBE16(ip\payload) : *view\destinationPort=NetReadBE16(ip\payload+2)
 *view\headerBytes=header : *view\data=ip\payload+header : *view\dataBytes=ip\payloadBytes-header
 ProcedureReturn 0
EndProcedure

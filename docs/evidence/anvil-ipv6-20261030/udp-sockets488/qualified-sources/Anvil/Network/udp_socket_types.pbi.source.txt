; Shared datagram ABI records. Native integers are 64-bit on Anvil targets;
; addresses are network-order bytes (IPv4 first four bytes, remaining zero).
; No routing, device, allocation or socket state lives here.
XIncludeFile "Anvil/Network/ipv6_udp.pbi"
Structure UdpEndpoint
 family.i
 kind.i
 port.i
 address.a[16]
EndStructure
Structure UdpDatagramInfo
 family.i
 kind.i
 localPort.i
 peerPort.i
 localAddress.a[16]
 peerAddress.a[16]
 bytes.i
 receivedUs.i
EndStructure
#UDP_TX_IDLE=0
#UDP_TX_QUEUED=1
#UDP_TX_LINK=2
#UDP_TX_SENT=3
#UDP_TX_FAILED=4
Structure UdpSocketStatus
 family.i
 kind.i
 port.i
 rxQueued.i
 rxDropped.i
 txTicket.i
 txState.i
 txError.i
 txBytes.i
 submittedUs.i
 completedUs.i
 localAddress.a[16]
 maxSend.i
EndStructure
Procedure.i UdpEndpointValid(*endpoint.UdpEndpoint)
 Define i.i
 If IPv6UdpSpanValid(*endpoint,SizeOf(UdpEndpoint))=0 : ProcedureReturn 0 : EndIf
 If *endpoint\kind<0 Or *endpoint\kind>65535 Or *endpoint\port<1 Or *endpoint\port>65535 : ProcedureReturn 0 : EndIf
 If *endpoint\family=4
  ; Read network bytes explicitly, matching the shared wire parsers.
  i=PeekA(@*endpoint\address)
  If i=0 Or i>=224 : ProcedureReturn 0 : EndIf
  For i=4 To 15
   If PeekA(@*endpoint\address+i)<>0 : ProcedureReturn 0 : EndIf
  Next
  ProcedureReturn 1
 EndIf
 If *endpoint\family=6 : ProcedureReturn IPv6UnicastAddress(@*endpoint\address) : EndIf
 ProcedureReturn 0
EndProcedure

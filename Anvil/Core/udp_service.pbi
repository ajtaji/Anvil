; Resident datagram owner, shared by every networking composition.
; Requires the existing network/link, clock and service-error seams.
; Four interface-bound wildcard sockets, eight whole RX datagrams each,
; one copied outbound datagram each. No receive/send/neighbor wait occurs.
XIncludeFile "Anvil/Hal/service_errors.pbi"
XIncludeFile "Anvil/Network/udp_socket_types.pbi"
#UDP_SERVICE_SOCKETS=4
#UDP_SERVICE_RX=8
#UDP_SERVICE_BYTES=1472
Structure UdpServiceSocket
 tag.i
 family.i
 kind.i
 port.i
 head.i
 count.i
 dropped.i
 ticket.i
 state.i
 error.i
 bytes.i
 receipt.i
 arpReceipt.i
 deadline.i
 retry.i
 submitted.i
 completed.i
 peer.UdpEndpoint
 source.a[16]
EndStructure
Global Dim udpSockets.UdpServiceSocket[#UDP_SERVICE_SOCKETS]
Global Dim udpInfo.UdpDatagramInfo[#UDP_SERVICE_SOCKETS*#UDP_SERVICE_RX]
Global Dim udpRx.a[#UDP_SERVICE_SOCKETS*#UDP_SERVICE_RX*#UDP_SERVICE_BYTES]
Global Dim udpTx.a[#UDP_SERVICE_SOCKETS*#UDP_SERVICE_BYTES]
Structure UdpServiceControl
 serial.i
 port.i
 cursor.i
 busy.i
EndStructure
Global udpControl.UdpServiceControl
Procedure udp_Copy(dst.i,src.i,bytes.i)
 Define i.i
 If bytes>0
  For i=0 To bytes-1 : PokeA(dst+i,PeekA(src+i)) : Next
 EndIf
EndProcedure
Procedure udp_Zero(dst.i,bytes.i)
 Define i.i
 For i=0 To bytes-1 : PokeA(dst+i,0) : Next
EndProcedure
Procedure.i udp_Overlap(a.i,n.i,b.i,m.i)
 If n=0 Or m=0 : ProcedureReturn 0 : EndIf
 If a<b+m And b<a+n : ProcedureReturn 1 : EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i udp_ClientSpan(p.i,n.i)
 If IPv6UdpSpanValid(p,n)=0 : ProcedureReturn 0 : EndIf
 If udp_Overlap(p,n,@udpControl,SizeOf(UdpServiceControl))<>0 : ProcedureReturn 0 : EndIf
 If udp_Overlap(p,n,@udpSockets[0],SizeOf(UdpServiceSocket)*#UDP_SERVICE_SOCKETS)<>0 : ProcedureReturn 0 : EndIf
 If udp_Overlap(p,n,@udpInfo[0],SizeOf(UdpDatagramInfo)*#UDP_SERVICE_SOCKETS*#UDP_SERVICE_RX)<>0 : ProcedureReturn 0 : EndIf
 If udp_Overlap(p,n,@udpRx[0],#UDP_SERVICE_SOCKETS*#UDP_SERVICE_RX*#UDP_SERVICE_BYTES)<>0 : ProcedureReturn 0 : EndIf
 If udp_Overlap(p,n,@udpTx[0],#UDP_SERVICE_SOCKETS*#UDP_SERVICE_BYTES)<>0 : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i udp_Index(handle.i)
 Define i.i
 If handle<9 : ProcedureReturn -1 : EndIf
 i=(handle&7)-1
 If i<0 Or i>=#UDP_SERVICE_SOCKETS : ProcedureReturn -1 : EndIf
 If udpSockets[i]\tag<>handle : ProcedureReturn -1 : EndIf
 ProcedureReturn i
EndProcedure
; Kernel control ports and fixed DNS/NTP client ports are not application
; binds, even when their protocol is temporarily idle. Automatic allocation
; uses 50000..65535; it does not claim unpredictable-port security.
Procedure.i udp_Reserved(port.i)
 If port=67 Or port=68 Or port=5555 : ProcedureReturn 1 : EndIf
 If port>=49200 And port<=49263 : ProcedureReturn 1 : EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i UdpServiceOpen(family.i,kind.i,port.i)
 Define i.i,j.i,tag.i
 If family<>4 And family<>6 : ProcedureReturn #SVC_EARG : EndIf
 If kind=0 : kind=LinkKind() : EndIf
 If kind<1 Or kind>=#NET_IF_KINDS Or port<0 Or port>65535 : ProcedureReturn #SVC_EARG : EndIf
 If HwLinkHas(kind)=0 : ProcedureReturn #SVC_ENOCAP : EndIf
 If udp_Reserved(port)<>0 : ProcedureReturn #SVC_EPERM : EndIf
 i=0
 While i<#UDP_SERVICE_SOCKETS
  If udpSockets[i]\tag=0 : Break : EndIf
  i=i+1
 Wend
 If i=#UDP_SERVICE_SOCKETS Or udpControl\serial>=$0FFFFFFFFFFFFFFF : ProcedureReturn #SVC_EBUSY : EndIf
 tag=((udpControl\serial+1)<<3)|(i+1)
 If port=0
  For j=0 To 31
   udpControl\port=udpControl\port+1 : If udpControl\port>65535 Or udpControl\port<50000 : udpControl\port=50000 : EndIf
   If NetUdpPortOwner(kind,udpControl\port)=0 And NetUdpBoundPort(kind)<>udpControl\port
    port=udpControl\port : Break
   EndIf
  Next
  If port=0 : ProcedureReturn #SVC_EBUSY : EndIf
 EndIf
 If NetUdpClaim(kind,port,tag)=0 : ProcedureReturn #SVC_EBUSY : EndIf
 udpControl\serial=udpControl\serial+1
 udp_Zero(@udpSockets[i],SizeOf(UdpServiceSocket))
 udpSockets[i]\tag=tag : udpSockets[i]\family=family : udpSockets[i]\kind=kind : udpSockets[i]\port=port
 NetServiceSetDatagramHook(@UdpServiceInput)
 ProcedureReturn tag
EndProcedure
Procedure.i UdpServiceClose(handle.i)
 Define i.i
 i=udp_Index(handle) : If i<0 : ProcedureReturn #SVC_ESTATE : EndIf
 ; A link-accepted packet cannot be unsent; forgetting its receipt never
 ; schedules it again. Releasing a stale socket cannot release a new owner.
 NetUdpRelease(udpSockets[i]\kind,udpSockets[i]\port,handle)
 udp_Zero(@udpSockets[i],SizeOf(UdpServiceSocket))
 udp_Zero(@udpInfo[i*#UDP_SERVICE_RX],SizeOf(UdpDatagramInfo)*#UDP_SERVICE_RX)
 udp_Zero(@udpRx[i*#UDP_SERVICE_RX*#UDP_SERVICE_BYTES],#UDP_SERVICE_RX*#UDP_SERVICE_BYTES)
 udp_Zero(@udpTx[i*#UDP_SERVICE_BYTES],#UDP_SERVICE_BYTES)
 ProcedureReturn 0
EndProcedure
Procedure UdpServiceCloseAll()
 Define i.i
 For i=0 To #UDP_SERVICE_SOCKETS-1
  If udpSockets[i]\tag<>0 : UdpServiceClose(udpSockets[i]\tag) : EndIf
 Next
EndProcedure
Procedure.i UdpServiceSendTo(handle.i,*peer.UdpEndpoint,data.i,bytes.i)
 Define i.i,maximum.i
 i=udp_Index(handle) : If i<0 : ProcedureReturn #SVC_ESTATE : EndIf
 If udp_ClientSpan(*peer,SizeOf(UdpEndpoint))=0 : ProcedureReturn #SVC_EARG : EndIf
 If UdpEndpointValid(*peer)=0 Or *peer\family<>udpSockets[i]\family : ProcedureReturn #SVC_EARG : EndIf
 If *peer\kind<>0 And *peer\kind<>udpSockets[i]\kind : ProcedureReturn #SVC_EARG : EndIf
 maximum=#UDP_SERVICE_BYTES : If *peer\family=6 : maximum=1232 : EndIf
 If bytes<0 Or bytes>maximum : ProcedureReturn #SVC_EARG : EndIf
 If bytes>0
  If udp_ClientSpan(data,bytes)=0 : ProcedureReturn #SVC_EARG : EndIf
 EndIf
 If udpSockets[i]\state=#UDP_TX_QUEUED Or udpSockets[i]\state=#UDP_TX_LINK : ProcedureReturn #SVC_EAGAIN : EndIf
 If NetUdpPortOwner(udpSockets[i]\kind,udpSockets[i]\port)<>handle : ProcedureReturn #SVC_ESTATE : EndIf
 If udpSockets[i]\ticket=$7FFFFFFFFFFFFFFF : ProcedureReturn #SVC_EBUSY : EndIf
 udp_Copy(@udpSockets[i]\peer,*peer,SizeOf(UdpEndpoint))
 udp_Copy(@udpTx[i*#UDP_SERVICE_BYTES],data,bytes)
 udp_Zero(@udpSockets[i]\source,16)
 udpSockets[i]\bytes=bytes : udpSockets[i]\ticket=udpSockets[i]\ticket+1
 udpSockets[i]\state=#UDP_TX_QUEUED : udpSockets[i]\error=0 : udpSockets[i]\receipt=0
 udpSockets[i]\deadline=HwMicros()+5000000 : udpSockets[i]\retry=0
 udpSockets[i]\submitted=0 : udpSockets[i]\completed=0
 ProcedureReturn udpSockets[i]\ticket
EndProcedure
Procedure.i UdpServiceInput(kind.i)
 Define i.i,slot.i,n.i,now.i
 Define *info.UdpDatagramInfo
 For i=0 To #UDP_SERVICE_SOCKETS-1
  If udpSockets[i]\tag<>0 And udpSockets[i]\kind=kind And udpSockets[i]\family=NetUdpRxFamily() And udpSockets[i]\port=NetUdpRxDstPort()
   If NetUdpPortOwner(kind,udpSockets[i]\port)<>udpSockets[i]\tag : ProcedureReturn 0 : EndIf
   n=NetUdpRxLen()
   If udpSockets[i]\count=#UDP_SERVICE_RX Or n<0 Or n>#UDP_SERVICE_BYTES
    If udpSockets[i]\dropped<$7FFFFFFFFFFFFFFF : udpSockets[i]\dropped=udpSockets[i]\dropped+1 : EndIf
    ProcedureReturn 1
   EndIf
   slot=i*#UDP_SERVICE_RX+(udpSockets[i]\head+udpSockets[i]\count) % #UDP_SERVICE_RX
   *info=@udpInfo[slot] : udp_Zero(*info,SizeOf(UdpDatagramInfo))
   *info\family=NetUdpRxFamily() : *info\kind=kind
   *info\localPort=NetUdpRxDstPort() : *info\peerPort=NetUdpRxPort()
   *info\bytes=n : *info\receivedUs=HwMicros()
   If *info\family=4
    NetWriteBE32(@*info\localAddress,NetRxTo()) : NetWriteBE32(@*info\peerAddress,NetUdpRxFrom())
   Else
    udp_Copy(@*info\localAddress,NetUdpRxTo6(),16) : udp_Copy(@*info\peerAddress,NetUdpRxFrom6(),16)
   EndIf
   udp_Copy(@udpRx[slot*#UDP_SERVICE_BYTES],NetUdpRxData(),n)
   udpSockets[i]\count=udpSockets[i]\count+1 : ProcedureReturn 1
  EndIf
 Next
 ProcedureReturn 0
EndProcedure
Procedure.i UdpServicePeek(handle.i,info.i)
 Define i.i,slot.i
 i=udp_Index(handle) : If i<0 : ProcedureReturn #SVC_ESTATE : EndIf
 If udp_ClientSpan(info,SizeOf(UdpDatagramInfo))=0 : ProcedureReturn #SVC_EARG : EndIf
 If udpSockets[i]\count=0 : ProcedureReturn #SVC_EAGAIN : EndIf
 slot=i*#UDP_SERVICE_RX+udpSockets[i]\head
 udp_Copy(info,@udpInfo[slot],SizeOf(UdpDatagramInfo)) : ProcedureReturn 0
EndProcedure
Procedure.i UdpServiceDiscard(handle.i)
 Define i.i,slot.i,n.i
 i=udp_Index(handle) : If i<0 : ProcedureReturn #SVC_ESTATE : EndIf
 If udpSockets[i]\count=0 : ProcedureReturn #SVC_EAGAIN : EndIf
 slot=i*#UDP_SERVICE_RX+udpSockets[i]\head : n=udpInfo[slot]\bytes
 udpSockets[i]\head=(udpSockets[i]\head+1) % #UDP_SERVICE_RX
 udpSockets[i]\count=udpSockets[i]\count-1 : ProcedureReturn n
EndProcedure
Procedure.i UdpServiceReceive(handle.i,info.i,data.i,capacity.i)
 Define i.i,slot.i,n.i
 i=udp_Index(handle) : If i<0 : ProcedureReturn #SVC_ESTATE : EndIf
 If capacity<0 Or capacity>#UDP_SERVICE_BYTES Or udp_ClientSpan(info,SizeOf(UdpDatagramInfo))=0 : ProcedureReturn #SVC_EARG : EndIf
 If capacity>0
  If udp_ClientSpan(data,capacity)=0 : ProcedureReturn #SVC_EARG : EndIf
  If udp_Overlap(info,SizeOf(UdpDatagramInfo),data,capacity)<>0 : ProcedureReturn #SVC_EARG : EndIf
 EndIf
 If udpSockets[i]\count=0 : ProcedureReturn #SVC_EAGAIN : EndIf
 slot=i*#UDP_SERVICE_RX+udpSockets[i]\head : n=udpInfo[slot]\bytes
 ; No truncation and no consumption on a short buffer. Peek exposes length.
 If capacity<n : ProcedureReturn #SVC_EARG : EndIf
 udp_Copy(info,@udpInfo[slot],SizeOf(UdpDatagramInfo))
 udp_Copy(data,@udpRx[slot*#UDP_SERVICE_BYTES],n)
 udpSockets[i]\head=(udpSockets[i]\head+1) % #UDP_SERVICE_RX
 udpSockets[i]\count=udpSockets[i]\count-1
 ProcedureReturn n
EndProcedure
Procedure.i UdpServiceStatus(handle.i,*status.UdpSocketStatus)
 Define i.i
 i=udp_Index(handle) : If i<0 : ProcedureReturn #SVC_ESTATE : EndIf
 If udp_ClientSpan(*status,SizeOf(UdpSocketStatus))=0 : ProcedureReturn #SVC_EARG : EndIf
 *status\family=udpSockets[i]\family : *status\kind=udpSockets[i]\kind : *status\port=udpSockets[i]\port
 *status\rxQueued=udpSockets[i]\count : *status\rxDropped=udpSockets[i]\dropped
 *status\txTicket=udpSockets[i]\ticket : *status\txState=udpSockets[i]\state : *status\txError=udpSockets[i]\error
 *status\txBytes=udpSockets[i]\bytes : *status\submittedUs=udpSockets[i]\submitted : *status\completedUs=udpSockets[i]\completed
 udp_Copy(@*status\localAddress,@udpSockets[i]\source,16)
 *status\maxSend=#UDP_SERVICE_BYTES : If *status\family=6 : *status\maxSend=1232 : EndIf
 ProcedureReturn 0
EndProcedure
Procedure udp_Fail(index.i,error.i,now.i)
 udpSockets[index]\state=#UDP_TX_FAILED : udpSockets[index]\error=error
 udpSockets[index]\completed=now : udpSockets[index]\receipt=0 : udpSockets[index]\arpReceipt=0
EndProcedure
; Poll at most four receipts and try one queued datagram per call. Once a
; link accepts a packet, an expired/failed receipt is never a replay trigger.
Procedure UdpServiceAdvance()
 Define i.i,k.i,rc.i,now.i,ip.i,hop.i,ready.i
 If udpControl\busy<>0 : ProcedureReturn : EndIf
 udpControl\busy=1 : now=HwMicros()
 For i=0 To #UDP_SERVICE_SOCKETS-1
  If udpSockets[i]\tag<>0 And udpSockets[i]\arpReceipt>0
   rc=LinkTxReceipt(udpSockets[i]\kind,udpSockets[i]\arpReceipt)
   If rc<>0 : udpSockets[i]\arpReceipt=0 : EndIf
  EndIf
  If udpSockets[i]\tag<>0 And udpSockets[i]\state=#UDP_TX_LINK
   rc=LinkTxReceipt(udpSockets[i]\kind,udpSockets[i]\receipt)
   If rc=1
    udpSockets[i]\state=#UDP_TX_SENT : udpSockets[i]\completed=now : udpSockets[i]\receipt=0
   ElseIf rc<0
    udp_Fail(i,#SVC_EIO,now)
   ElseIf now>=udpSockets[i]\deadline
    udp_Fail(i,#SVC_ETIMEOUT,now)
   EndIf
  EndIf
 Next
 i=udpControl\cursor : udpControl\cursor=(udpControl\cursor+1) % #UDP_SERVICE_SOCKETS
 If udpSockets[i]\tag<>0 And udpSockets[i]\state=#UDP_TX_QUEUED
  k=udpSockets[i]\kind
  If NetUdpPortOwner(k,udpSockets[i]\port)<>udpSockets[i]\tag Or HwLinkReady(k)=0
   udp_Fail(i,#SVC_ESTATE,now)
  ElseIf now>=udpSockets[i]\deadline
   udp_Fail(i,#SVC_ETIMEOUT,now)
  ElseIf now>=udpSockets[i]\retry And udpSockets[i]\arpReceipt=0
   ready=0
   If udpSockets[i]\family=6
    rc=NetTcp6SelectOn(k,@udpSockets[i]\peer\address,@udpSockets[i]\source)
    If rc<>k
     udp_Fail(i,#SVC_ESTATE,now)
    Else
     ready=NetUdp6BuildFrom(k,@udpSockets[i]\source,@udpSockets[i]\peer\address,udpSockets[i]\peer\port,udpSockets[i]\port,@udpTx[i*#UDP_SERVICE_BYTES],udpSockets[i]\bytes)
     If ready=0 And NetError()<0 : udp_Fail(i,#SVC_EIO,now) : EndIf
    EndIf
   Else
    ip=NetReadBE32(@udpSockets[i]\peer\address)
    NetWriteBE32(@udpSockets[i]\source,NetSrcFor(k,ip))
    ready=NetUdpBuild(k,ip,udpSockets[i]\peer\port,udpSockets[i]\port,@udpTx[i*#UDP_SERVICE_BYTES],udpSockets[i]\bytes)
    If ready=0
     If NetError()=#NET_E_NO_ARP
      hop=NetNextHop(k,ip)
      If hop<>0 And NetArpRequest(k,hop)<>0
       rc=LinkSendTracked(k,NetOutBuf(),NetOutLen())
       If rc>0 : udpSockets[i]\arpReceipt=rc : EndIf
       If rc<0 : udp_Fail(i,#SVC_ENOSYS,now) : EndIf
      EndIf
      udpSockets[i]\retry=now+1000000
     Else
      udp_Fail(i,#SVC_EIO,now)
     EndIf
    EndIf
   EndIf
   If ready<>0
    rc=LinkSendTracked(k,NetOutBuf(),NetOutLen())
    If rc>0
     udpSockets[i]\receipt=rc : udpSockets[i]\state=#UDP_TX_LINK : udpSockets[i]\submitted=now
    ElseIf rc<0
     udp_Fail(i,#SVC_ENOSYS,now)
    EndIf
   EndIf
  EndIf
 EndIf
 udpControl\busy=0
EndProcedure

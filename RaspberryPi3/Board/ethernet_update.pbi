; Raspberry Pi 3 scheduler-step Ethernet updater.
;
; DWC2 owns the LAN9514 USB function. The shared net/DHCP libraries own wire
; formats only. This file is the board composition and is the only place that
; moves frames between those layers. Every call from the serial idle hook is
; bounded to one controller transaction or one already-received frame.
;
; UDP port 5556 carries P3N1 requests and P3R1 replies. The complete image is
; still admitted, hashed, written and selected only by update_ab.pbi. A random
; host session and exact peer binding reject stale/crossed datagrams; this is
; not a claim of authentication against another machine on the same LAN.

#PI3_NET_KIND = 1
#PI3_NET_UPDATE_PORT = 5556
#PI3_NET_MAGIC = $314E3350 ; P3N1 in little-endian memory
#PI3_NET_REPLY = $31523350 ; P3R1
#PI3_NET_BEGIN = 1
#PI3_NET_DATA = 2
#PI3_NET_COMMIT = 3
#PI3_NET_ABORT = 4
#PI3_NET_STATUS = 5
#PI3_NET_RESET = 6
#PI3_NET_HEADER = 24
#PI3_NET_REPLY_BYTES = 40
#PI3_NET_E_PACKET = -2001
#PI3_NET_E_SESSION = -2002
#PI3_NET_E_STATE = -2003
#PI3_NET_DHCP_RETRIES = 8
#PI3_NET_DHCP_RETRY_MS = 1000

Global Dim p3net_setup.l[4]
Global Dim p3net_control.l[132]
Global Dim p3net_tx.l[384]
Global Dim p3net_rx.l[640]
Global Dim p3net_mac.a[8]
Global Dim p3net_reply.a[#PI3_NET_REPLY_BYTES]
Global p3net_state.i
Global p3net_error.i
Global p3net_io.i
Global p3net_rx_frame.i
Global p3net_rx_length.i
Global p3net_rx_more.i
Global p3net_dhcp_deadline.i
Global p3net_dhcp_retries.i
Global p3net_dhcp_pending.i
Global p3net_peer_ip.i
Global p3net_peer_port.i
Global p3net_session.i
Global p3net_total.i
Global p3net_committed_session.i
Global p3net_reset_pending.i
Global p3net_reset_at.i

Procedure.i Pi3NetLe16(p.i)
  ProcedureReturn PeekA(p) | (PeekA(p+1)<<8)
EndProcedure

Procedure.i Pi3NetLe32(p.i)
  ProcedureReturn PeekA(p) | (PeekA(p+1)<<8) | (PeekA(p+2)<<16) | (PeekA(p+3)<<24)
EndProcedure

Procedure.i Pi3NetLe64(p.i)
  ProcedureReturn (Pi3NetLe32(p)&$FFFFFFFF) | (Pi3NetLe32(p+4)<<32)
EndProcedure

Procedure Pi3NetPut32(p.i,value.i)
  PokeA(p,value&$FF) : PokeA(p+1,(value>>8)&$FF)
  PokeA(p+2,(value>>16)&$FF) : PokeA(p+3,(value>>24)&$FF)
EndProcedure

Procedure Pi3NetPut64(p.i,value.i)
  Pi3NetPut32(p,value&$FFFFFFFF)
  Pi3NetPut32(p+4,(value>>32)&$FFFFFFFF)
EndProcedure

Procedure.i Pi3NetFail(code.i,text.i)
  p3net_error=code
  p3net_state=-1
  If text<>0 : pi3ut_WriteLine(text) : EndIf
  ProcedureReturn 0
EndProcedure

Procedure Pi3NetPrintIp(ip.i)
  pi3ut_WriteDec((ip>>24)&$FF) : pi3ut_WriteByte(46)
  pi3ut_WriteDec((ip>>16)&$FF) : pi3ut_WriteByte(46)
  pi3ut_WriteDec((ip>>8)&$FF) : pi3ut_WriteByte(46)
  pi3ut_WriteDec(ip&$FF)
EndProcedure

Procedure.i Pi3NetTx(frame.i,length.i)
  If p3net_io<>0 Or frame=0 Or length<14 Or length>1536 : ProcedureReturn 0 : EndIf
  If Pi3LanBulkTxBegin(frame,length,8)<>1 : ProcedureReturn Pi3NetFail(p3lan_bulk_error,"Ethernet transmit refused; serial recovery remains available") : EndIf
  p3net_io=#P3_LAN_BULK_TX
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3NetDhcpSend(action.i,nowMs.i)
  Protected bytes.i=DhcpClientBuild(#PI3_NET_KIND,action)
  Protected source.i
  Protected made.i
  If bytes<=0 : ProcedureReturn Pi3NetFail(-2010,"DHCP message build refused; serial recovery remains available") : EndIf
  If action=#DHCPC_ACT_RENEW
    made=NetUdpBuild(#PI3_NET_KIND,DhcpClientServer(#PI3_NET_KIND),#DHCP_PORT_SERVER,#DHCP_PORT_CLIENT,DhcpBuf(),bytes)
  Else
    If action=#DHCPC_ACT_REBIND : source=DhcpClientIp(#PI3_NET_KIND) : EndIf
    made=NetUdpBuildBcast(#PI3_NET_KIND,source,#DHCP_PORT_SERVER,#DHCP_PORT_CLIENT,DhcpBuf(),bytes)
  EndIf
  If made=0 And action=#DHCPC_ACT_RENEW And NetError()=#NET_E_NO_ARP
    If NetArpRequest(#PI3_NET_KIND,DhcpClientServer(#PI3_NET_KIND))=0 : ProcedureReturn Pi3NetFail(NetError(),"DHCP renewal ARP build refused; serial recovery remains available") : EndIf
    p3net_dhcp_pending=action
    If Pi3NetTx(NetOutBuf(),NetOutLen())=0 : ProcedureReturn 0 : EndIf
    p3net_dhcp_deadline=(nowMs+#PI3_NET_DHCP_RETRY_MS)&$FFFFFFFF
    ProcedureReturn 1
  EndIf
  If made=0 : ProcedureReturn Pi3NetFail(NetError(),"DHCP Ethernet frame build refused; serial recovery remains available") : EndIf
  p3net_dhcp_pending=0
  If Pi3NetTx(NetOutBuf(),NetOutLen())=0 : ProcedureReturn 0 : EndIf
  p3net_dhcp_deadline=(nowMs+#PI3_NET_DHCP_RETRY_MS)&$FFFFFFFF
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3NetReply(op.i,session.i,status.i,toIp.i,toPort.i)
  Protected i.i
  For i=0 To #PI3_NET_REPLY_BYTES-1 : p3net_reply[i]=0 : Next
  Pi3NetPut32(@p3net_reply[0],#PI3_NET_REPLY)
  Pi3NetPut32(@p3net_reply[4],op)
  Pi3NetPut64(@p3net_reply[8],session)
  Pi3NetPut32(@p3net_reply[16],Pi3UpdateReceived())
  Pi3NetPut32(@p3net_reply[20],status)
  Pi3NetPut32(@p3net_reply[24],Pi3UpdateSlot())
  Pi3NetPut32(@p3net_reply[28],Pi3UpdatePendingSlot())
  Pi3NetPut64(@p3net_reply[32],Pi3UpdatePendingGeneration())
  If NetUdpBuild(#PI3_NET_KIND,toIp,toPort,#PI3_NET_UPDATE_PORT,@p3net_reply[0],#PI3_NET_REPLY_BYTES)=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn Pi3NetTx(NetOutBuf(),NetOutLen())
EndProcedure

Procedure.i Pi3NetPeer(session.i,fromIp.i,fromPort.i)
  ProcedureReturn Bool(session<>0 And session=p3net_session And fromIp=p3net_peer_ip And fromPort=p3net_peer_port)
EndProcedure

Procedure Pi3NetUpdatePacket(data.i,length.i,fromIp.i,fromPort.i)
  Protected op.i
  Protected session.i
  Protected offset.i
  Protected bytes.i
  Protected status.i
  If data=0 Or length<#PI3_NET_HEADER Or Pi3NetLe32(data)<>#PI3_NET_MAGIC Or Pi3NetLe16(data+22)<>0
    Pi3NetReply(0,0,#PI3_NET_E_PACKET,fromIp,fromPort) : ProcedureReturn
  EndIf
  op=Pi3NetLe32(data+4) : session=Pi3NetLe64(data+8)
  offset=Pi3NetLe32(data+16)&$FFFFFFFF : bytes=Pi3NetLe16(data+20)
  If length<>#PI3_NET_HEADER+bytes Or bytes>1024
    Pi3NetReply(op,session,#PI3_NET_E_PACKET,fromIp,fromPort) : ProcedureReturn
  EndIf
  If op=#PI3_NET_STATUS
    If bytes<>0 Or offset<>0 : status=#PI3_NET_E_PACKET : EndIf
    Pi3NetReply(op,session,status,fromIp,fromPort) : ProcedureReturn
  EndIf
  If op=#PI3_NET_BEGIN
    If session=0 Or bytes<>32 Or offset=0
      status=#PI3_NET_E_PACKET
    ElseIf Pi3UpdateSource()=#PI3_UPDATE_SOURCE_ETHERNET And Pi3NetPeer(session,fromIp,fromPort)<>0 And offset=p3net_total
      status=0 ; lost BEGIN reply
    ElseIf Pi3UpdateSource()<>#PI3_UPDATE_SOURCE_NONE
      status=#PI3_NET_E_STATE
    ElseIf Pi3UpdateBeginFrom(#PI3_UPDATE_SOURCE_ETHERNET,offset,data+#PI3_NET_HEADER)=0
      status=Pi3UpdateError()
    Else
      p3net_session=session : p3net_peer_ip=fromIp : p3net_peer_port=fromPort : p3net_total=offset
    EndIf
    Pi3NetReply(op,session,status,fromIp,fromPort) : ProcedureReturn
  EndIf
  If Pi3NetPeer(session,fromIp,fromPort)=0
    Pi3NetReply(op,session,#PI3_NET_E_SESSION,fromIp,fromPort) : ProcedureReturn
  EndIf
  If op=#PI3_NET_DATA
    If bytes=0 Or offset>p3net_total Or bytes>p3net_total-offset
      status=#PI3_NET_E_PACKET
    ElseIf Pi3UpdateChunkFrom(#PI3_UPDATE_SOURCE_ETHERNET,offset,data+#PI3_NET_HEADER,bytes)=0
      status=Pi3UpdateError()
    EndIf
  ElseIf op=#PI3_NET_COMMIT
    If bytes<>0 Or offset<>Pi3UpdateReceived()
      status=#PI3_NET_E_PACKET
    ElseIf session=p3net_committed_session
      status=0 ; lost COMMIT reply
    ElseIf Pi3UpdateCommitFrom(#PI3_UPDATE_SOURCE_ETHERNET)=0
      status=Pi3UpdateError()
    Else
      p3net_committed_session=session
    EndIf
  ElseIf op=#PI3_NET_ABORT
    If bytes<>0 Or offset<>0
      status=#PI3_NET_E_PACKET
    ElseIf Pi3UpdateAbortFrom(#PI3_UPDATE_SOURCE_ETHERNET)=0
      status=Pi3UpdateError()
    Else
      p3net_session=0 : p3net_total=0
    EndIf
  ElseIf op=#PI3_NET_RESET
    If bytes<>0 Or offset<>0 Or session<>p3net_committed_session Or Pi3UpdateResetReady()=0
      status=#PI3_NET_E_STATE
    Else
      p3net_reset_pending=1
      p3net_reset_at=(Pi3Micros()/1000+150)&$FFFFFFFF
    EndIf
  Else
    status=#PI3_NET_E_PACKET
  EndIf
  Pi3NetReply(op,session,status,fromIp,fromPort)
EndProcedure

Procedure Pi3NetTakeFrame(nowMs.i)
  Protected result.i=NetInput(#PI3_NET_KIND,p3net_rx_frame,p3net_rx_length)
  Protected action.i
  If result=#NET_IN_REPLY
    Pi3NetTx(NetOutBuf(),NetOutLen())
  ElseIf result=#NET_IN_LEARNED And p3net_dhcp_pending<>0
    action=p3net_dhcp_pending : p3net_dhcp_pending=0
    Pi3NetDhcpSend(action,nowMs)
  ElseIf result=#NET_IN_UDP
    If NetUdpRxDstPort()=#DHCP_PORT_CLIENT And DhcpClientState(#PI3_NET_KIND)<>#DHCPC_BOUND
      action=DhcpClientInput(#PI3_NET_KIND,NetUdpRxData(),NetUdpRxLen(),nowMs)
      If action=#DHCPC_ACT_SELECT
        Pi3NetDhcpSend(action,nowMs)
      ElseIf action=#DHCPC_ACT_BOUND
        If NetSetIPv4(#PI3_NET_KIND,DhcpClientIp(#PI3_NET_KIND),DhcpClientMask(#PI3_NET_KIND),DhcpClientGateway(#PI3_NET_KIND))=0
          Pi3NetFail(NetError(),"DHCP lease could not be installed; serial recovery remains available")
        Else
          NetDhcpMode(#PI3_NET_KIND,0) : NetUdpListen(#PI3_NET_KIND,#DHCP_PORT_CLIENT,0)
          NetUdpListen(#PI3_NET_KIND,#PI3_NET_UPDATE_PORT,1)
          p3net_state=100
          pi3ut_WriteText("Pi 3 Ethernet update ready at ") : Pi3NetPrintIp(DhcpClientIp(#PI3_NET_KIND))
          pi3ut_WriteText(":") : pi3ut_WriteDec(#PI3_NET_UPDATE_PORT) : pi3ut_WriteByte(13) : pi3ut_WriteByte(10)
        EndIf
      EndIf
    ElseIf NetUdpRxDstPort()=#PI3_NET_UPDATE_PORT And p3net_state=100
      Pi3NetUpdatePacket(NetUdpRxData(),NetUdpRxLen(),NetUdpRxFrom(),NetUdpRxPort())
    EndIf
  EndIf
EndProcedure

Procedure.i Pi3EthernetStart()
  Protected setup.i=((@p3net_setup[0]+3)>>2)<<2
  Protected control.i=((@p3net_control[0]+3)>>2)<<2
  Protected tx.i=((@p3net_tx[0]+3)>>2)<<2
  Protected rx.i=((@p3net_rx[0]+3)>>2)<<2
  If p3net_state<>0 Or Pi3UpdateResetReady()=0 Or Pi3UsbNativeContext()=0 : ProcedureReturn 0 : EndIf
  If setup<$1100000 Or rx+2560>$1E00000 Or tx+1536>$1E00000 Or control+512>$1E00000
    ProcedureReturn Pi3NetFail(-2004,"Ethernet DMA buffer layout refused; serial recovery remains available")
  EndIf
  p3net_state=10 : p3net_error=0
  pi3ut_WriteLine("Pi 3 Ethernet starting in background; serial recovery remains available")
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3EthernetIdle()
  Protected nowUs.i=Pi3Micros()
  Protected nowMs.i
  Protected result.i
  Protected setup.i=((@p3net_setup[0]+3)>>2)<<2
  Protected control.i=((@p3net_control[0]+3)>>2)<<2
  Protected tx.i=((@p3net_tx[0]+3)>>2)<<2
  Protected rx.i=((@p3net_rx[0]+3)>>2)<<2
  If nowUs<0 Or p3net_state<=0 : ProcedureReturn 0 : EndIf
  nowMs=(nowUs/1000)&$FFFFFFFF
  If p3net_state=10
    If Pi3UsbHostInit()=0 : ProcedureReturn Pi3NetFail(p3usb_host_error,"Ethernet USB host initialization refused; serial recovery remains available") : EndIf
    p3net_state=11 : ProcedureReturn 1
  ElseIf p3net_state=11
    If Pi3UsbRootPortReset()=0 : ProcedureReturn Pi3NetFail(p3usb_host_error,"Ethernet USB root-port reset refused; serial recovery remains available") : EndIf
    If Pi3UsbEnumerationBegin(Pi3UsbRead($440),0,setup,setup|$C0000000,control,control|$C0000000,512,8,10,100000)=0
      ProcedureReturn Pi3NetFail(p3usb_enum_error,"Ethernet USB enumeration start refused; serial recovery remains available")
    EndIf
    Pi3UsbWrite(8,(Pi3UsbRead(8)&~1)|$20)
    If (Pi3UsbRead(8)&$21)<>$20 : ProcedureReturn Pi3NetFail(-2005,"Ethernet USB DMA enable refused; serial recovery remains available") : EndIf
    p3net_state=12 : ProcedureReturn 1
  ElseIf p3net_state=12
    result=Pi3UsbEnumerationStep(nowUs)
    If result<0 : ProcedureReturn Pi3NetFail(result,"LAN9514 enumeration failed; serial recovery remains available") : EndIf
    If result<>#P3_USB_ENUM_READY : ProcedureReturn 1 : EndIf
    If Pi3LanTransportAttach(0,p3usb_enum_lan_address,setup,setup|$C0000000,control,control|$C0000000,8,100000)<>1
      ProcedureReturn Pi3NetFail(p3lan_io_error,"LAN9514 control transport refused; serial recovery remains available")
    EndIf
    If Pi3LanRuntimeBuffers(tx,tx|$C0000000,1536,rx,rx|$C0000000,2560)<>1
      ProcedureReturn Pi3NetFail(p3lan_runtime_error,"LAN9514 frame buffers refused; serial recovery remains available")
    EndIf
    If Pi3LanRuntimeBegin(@p3net_mac[0],100,5000,1000)<>1
      ProcedureReturn Pi3NetFail(p3lan_runtime_error,"LAN9514 link start refused; serial recovery remains available")
    EndIf
    p3net_state=13 : ProcedureReturn 1
  ElseIf p3net_state=13
    result=Pi3LanRuntimeStep(nowUs)
    If result<0 : ProcedureReturn Pi3NetFail(result,"LAN9514 link negotiation failed; serial recovery remains available") : EndIf
    If result<>#P3_LAN_RUNTIME_READY : ProcedureReturn 1 : EndIf
    NetInit()
    If NetSetMac(#PI3_NET_KIND,@p3net_mac[0])=0 : ProcedureReturn Pi3NetFail(NetError(),"LAN9514 MAC admission failed; serial recovery remains available") : EndIf
    NetUdpListen(#PI3_NET_KIND,#DHCP_PORT_CLIENT,1) : NetDhcpMode(#PI3_NET_KIND,1)
    If DhcpClientBegin(#PI3_NET_KIND,@p3net_mac[0],nowMs)<>#DHCPC_ACT_DISCOVER : ProcedureReturn Pi3NetFail(-2010,"DHCP client start refused; serial recovery remains available") : EndIf
    p3net_dhcp_retries=#PI3_NET_DHCP_RETRIES : p3net_state=14
    ProcedureReturn Pi3NetDhcpSend(#DHCPC_ACT_DISCOVER,nowMs)
  EndIf

  If p3net_reset_pending<>0 And p3net_io=0 And ((nowMs-p3net_reset_at)&$FFFFFFFF)<$80000000
    Pi3UpdateResetNow()
    p3net_reset_pending=0
  EndIf
  If p3net_io<>0
    result=Pi3LanBulkStep()
    If result<0
      p3net_io=0
      If p3lan_runtime_quarantine<>0 : ProcedureReturn Pi3NetFail(result,"LAN9514 transfer ownership was lost; serial recovery remains available") : EndIf
      ProcedureReturn 1
    EndIf
    If result<>#P3_LAN_RUNTIME_READY : ProcedureReturn 1 : EndIf
    If p3net_io=#P3_LAN_BULK_RX
      p3net_rx_frame=p3lan_bulk_frame : p3net_rx_length=p3lan_bulk_frame_length
      p3net_rx_more=1
    EndIf
    p3net_io=0
  EndIf
  If p3net_io=0 And p3net_rx_frame=0 And p3net_rx_more<>0
    result=Pi3LanBulkRxNext()
    If result<0 : ProcedureReturn Pi3NetFail(result,"LAN9514 receive aggregate malformed; serial recovery remains available") : EndIf
    If result=1
      p3net_rx_frame=p3lan_bulk_frame : p3net_rx_length=p3lan_bulk_frame_length
    Else
      p3net_rx_more=0
    EndIf
  EndIf
  If p3net_rx_frame<>0
    Pi3NetTakeFrame(nowMs)
    p3net_rx_frame=0 : p3net_rx_length=0
    If p3net_io=0 And p3net_rx_more<>0
      result=Pi3LanBulkRxNext()
      If result<0 : ProcedureReturn Pi3NetFail(result,"LAN9514 receive aggregate malformed; serial recovery remains available") : EndIf
      If result=1
        p3net_rx_frame=p3lan_bulk_frame : p3net_rx_length=p3lan_bulk_frame_length
      Else
        p3net_rx_more=0
      EndIf
    EndIf
    ProcedureReturn 1
  EndIf
  If p3net_state=14 And ((nowMs-p3net_dhcp_deadline)&$FFFFFFFF)<$80000000
    If p3net_dhcp_retries=0
      NetClearIPv4(#PI3_NET_KIND)
      If DhcpClientBegin(#PI3_NET_KIND,@p3net_mac[0],nowMs)<>#DHCPC_ACT_DISCOVER : ProcedureReturn Pi3NetFail(-2010,"DHCP restart refused; serial recovery remains available") : EndIf
      p3net_dhcp_retries=#PI3_NET_DHCP_RETRIES
      pi3ut_WriteLine("DHCP has not answered; retrying in background; serial recovery remains available")
      ProcedureReturn Pi3NetDhcpSend(#DHCPC_ACT_DISCOVER,nowMs)
    EndIf
    p3net_dhcp_retries-1
    If DhcpClientState(#PI3_NET_KIND)=#DHCPC_REQUESTING
      ProcedureReturn Pi3NetDhcpSend(#DHCPC_ACT_SELECT,nowMs)
    ElseIf DhcpClientState(#PI3_NET_KIND)=#DHCPC_RENEWING
      ProcedureReturn Pi3NetDhcpSend(#DHCPC_ACT_RENEW,nowMs)
    ElseIf DhcpClientState(#PI3_NET_KIND)=#DHCPC_REBINDING
      ProcedureReturn Pi3NetDhcpSend(#DHCPC_ACT_REBIND,nowMs)
    ElseIf DhcpClientState(#PI3_NET_KIND)=#DHCPC_REBOOTING
      ProcedureReturn Pi3NetDhcpSend(#DHCPC_ACT_REBOOT,nowMs)
    EndIf
    ProcedureReturn Pi3NetDhcpSend(#DHCPC_ACT_DISCOVER,nowMs)
  EndIf
  If p3net_state=100 And p3net_io=0 And p3net_rx_more=0
    result=DhcpClientTick(#PI3_NET_KIND,nowMs,p3lan_runtime_link)
    If result=#DHCPC_ACT_DROP
      NetClearIPv4(#PI3_NET_KIND)
      NetDhcpMode(#PI3_NET_KIND,1) : NetUdpListen(#PI3_NET_KIND,#DHCP_PORT_CLIENT,1)
      result=DhcpClientBegin(#PI3_NET_KIND,@p3net_mac[0],nowMs)
      If result<>#DHCPC_ACT_DISCOVER : ProcedureReturn Pi3NetFail(-2010,"DHCP lease restart refused; serial recovery remains available") : EndIf
      p3net_dhcp_retries=#PI3_NET_DHCP_RETRIES : p3net_state=14
      ProcedureReturn Pi3NetDhcpSend(result,nowMs)
    ElseIf result=#DHCPC_ACT_RENEW Or result=#DHCPC_ACT_REBIND Or result=#DHCPC_ACT_REBOOT
      NetDhcpMode(#PI3_NET_KIND,1) : NetUdpListen(#PI3_NET_KIND,#DHCP_PORT_CLIENT,1)
      p3net_dhcp_retries=#PI3_NET_DHCP_RETRIES : p3net_state=14
      ProcedureReturn Pi3NetDhcpSend(result,nowMs)
    EndIf
  EndIf
  If p3net_io=0 And p3net_rx_more=0
    result=Pi3LanBulkRxBegin(8)
    If result=1 : p3net_io=#P3_LAN_BULK_RX : EndIf
  EndIf
  ProcedureReturn 1
EndProcedure

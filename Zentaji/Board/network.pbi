; The Ethernet NIC supplies frames to the shared Anvil link, IPv4, TCP,
; DNS, DHCP, and datagram layers.
Procedure.i Micros()
 ProcedureReturn HwMicros()
EndProcedure

Procedure.i millis()
 ProcedureReturn HwMicros()/1000
EndProcedure

Procedure.i delayMicroseconds(us.i)
 Protected start.q=HwMicros(),now.q,prior.q=start,stagnant.i
 If us<1 : ProcedureReturn 0 : EndIf
 Repeat
  now=HwMicros()
  If now<prior : ProcedureReturn 0 : EndIf
  If now-start>=us : ProcedureReturn 1 : EndIf
  If now=prior
   stagnant=stagnant+1
   If stagnant=4096 : ProcedureReturn 0 : EndIf
  Else
   stagnant=0 : prior=now
  EndIf
  If us-(now-start)>=2000 And HwPromptIdleReady()<>0 : HwPromptIdleWait() : EndIf
 ForEver
EndProcedure

XIncludeFile "Zentaji/Board/ethernet.pbi"
#ANVIL_NET_USE_BOARD_CLOCK=1
#ANVIL_NET_IPV4_ONLY=1
#ANVIL_LINK_SYNCHRONOUS=1
#ANVIL_NET_NO_LINKLOCAL=1
#ANVIL_NET_NO_LEGACY_UDP_HOOK=1
XIncludeFile "Anvil/Network/net.pbi"
XIncludeFile "Anvil/Core/netif.pbi"
XIncludeFile "Anvil/Network/dhcp.pbi"
XIncludeFile "Anvil/Network/dns_codec.pbi"
XIncludeFile "Anvil/Core/dhcpd.pbi"
#ANVIL_NET_NO_LEGACY_DIAGNOSTICS=1
XIncludeFile "Anvil/Core/netfmt.pbi"
XIncludeFile "Anvil/Network/link.pbi"
XIncludeFile "Anvil/Network/link_tx_queue.pbi"
XIncludeFile "Anvil/Core/sntp_codec.pbi"
XIncludeFile "Anvil/Core/ntp_service.pbi"
XIncludeFile "Anvil/Core/netconsole.pbi"
XIncludeFile "Anvil/Core/net_address.pbi"
XIncludeFile "Anvil/Network/tcp.pbi"

; Compatibility accounting for the existing shared IPv4 commands.
#ETH_ARP_MS=500
#ETH_ARP_TRIES=8
Global Dim gEthPeer.a[6]
Global gEthFrames.i,gEthArpOut.i
XIncludeFile "Anvil/Core/net_ipv4_cmd.pbi"

Global Dim zeTracked.q[(#LINK_TXQ_BYTES+7)/8]
#ZE_TX_GENERATION=1

Procedure.i HwLinkHas(kind.i)
 ProcedureReturn Bool(kind=#HW_LINK_WIRED And ZentajiEthernetPresent()<>0)
EndProcedure
Procedure.i HwLinkReady(kind.i)
 ProcedureReturn Bool(kind=#HW_LINK_WIRED And ZentajiEthernetCarrier()<>0 And ZentajiEthernetOwned()<>0)
EndProcedure
Procedure.i HwLinkName(kind.i)
 If kind=#HW_LINK_WIRED : ProcedureReturn "Zentaji Ethernet" : EndIf
 ProcedureReturn "an interface this board does not have"
EndProcedure
Procedure.i HwLinkMacPtr(kind.i)
 If HwLinkReady(kind)<>0 : ProcedureReturn @zeMac[0] : EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i HwLinkTxMax(kind.i)
 If HwLinkReady(kind)<>0 : ProcedureReturn #ZEN_ETH_FRAME : EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i HwLinkSpeed(kind.i)
 ProcedureReturn #HW_LINK_SPEED_UNKNOWN
EndProcedure
Procedure.i HwLinkDuplex(kind.i)
 ProcedureReturn #HW_LINK_DUPLEX_UNKNOWN
EndProcedure
Procedure.i HwLinkWhyText(kind.i)
 If kind<>#HW_LINK_WIRED : ProcedureReturn "" : EndIf
 If ZentajiEthernetCarrier()=0 : ProcedureReturn "the machine description has no net attachment" : EndIf
 If ZentajiEthernetOwned()=0 : ProcedureReturn "the Ethernet queue is unavailable or owned elsewhere" : EndIf
 ProcedureReturn ""
EndProcedure

Procedure.i HwLinkSend(kind.i,frame.i,bytes.i,ms.i)
 If HwLinkReady(kind)=0 : ProcedureReturn 0 : EndIf
 ProcedureReturn ZentajiEthernetSend(frame,bytes)
EndProcedure
Procedure.i HwLinkRecv(kind.i,frame.i,capacity.i,ms.i)
 If HwLinkReady(kind)=0 : ProcedureReturn 0 : EndIf
 ProcedureReturn ZentajiEthernetReceive(frame,capacity,ms)
EndProcedure
Procedure.i HwLinkRxPtr(kind.i)
 ; Receive wrote into the supplied frame buffer.
 ProcedureReturn 0
EndProcedure
Procedure.i HwLinkOfferRaw(kind.i,frame.i,bytes.i)
 ProcedureReturn 0
EndProcedure
Procedure.i HwLinkOfferUdp(kind.i,frame.i)
 ProcedureReturn NetConsoleOfferUdp(frame,kind)
EndProcedure
Procedure HwLinkNoteRx(kind.i,result.i)
EndProcedure
Procedure HwLinkAddressBound(kind.i,ip.i,mask.i,gw.i)
EndProcedure
Procedure HwLinkConsoleArmed(kind.i,armed.i)
EndProcedure

; The synchronous doorbell produces a completed receipt on return. Use the
; shared queue's bounded receipt history for payload datagram callers.
Procedure.i zeSendTracked(kind.i,frame.i,bytes.i)
 Protected q.i=@zeTracked[0],ticket.i,result.i
 If HwLinkReady(kind)=0 : ProcedureReturn -1 : EndIf
 ticket=LinkTxQueueNextTicket(q,#ZE_TX_GENERATION)
 If ticket<1 : ProcedureReturn -1 : EndIf
 If LinkTxQueueSubmit(q,#ZE_TX_GENERATION,frame,bytes)<>1 : ProcedureReturn -1 : EndIf
 result=2*HwLinkSend(kind,LinkTxQueuePeek(q,#ZE_TX_GENERATION),bytes,0)-1
 LinkTxQueueFinish(q,#ZE_TX_GENERATION,ticket,result)
 ProcedureReturn ticket
EndProcedure
Procedure.i zeTrackedResult(kind.i,ticket.i)
 If HwLinkReady(kind)=0 : ProcedureReturn -2 : EndIf
 ProcedureReturn LinkTxQueueResult(@zeTracked[0],#ZE_TX_GENERATION,ticket)
EndProcedure

Procedure.i HwLinkOpen(needIp.i)
 Protected first.i=Bool(zeOpen=0),kind.i=#HW_LINK_WIRED
 If ZentajiEthernetOpen()=0
  Print("!! Zentaji Ethernet could not be opened. ")
  UartWriteStr(HwLinkWhyText(kind)) : PrintNl()
  ProcedureReturn 0
 EndIf
 If first<>0
  NetSetMac(kind,@zeMac[0])
 EndIf
 LinkUseKind(kind)
 If needIp<>0 And NetIfUsable(kind)=0
  If NetDhcpAcquire(kind,12000,0)=0
   PrintN("!! The Zentaji link is up, but DHCP supplied no IPv4 address.")
   ProcedureReturn 0
  EndIf
 EndIf
 ProcedureReturn 1
EndProcedure

Procedure.i HwLinkClose()
 If ZentajiEthernetClose()=0 : ProcedureReturn 0 : EndIf
 NetDhcpCancel(#HW_LINK_WIRED)
 NetAddressLost(#HW_LINK_WIRED)
 LinkForget()
 ProcedureReturn 1
EndProcedure
Procedure.i HwLinkStaticUp()
 ProcedureReturn #HW_LINK_NONE
EndProcedure
Procedure HwLinkSayDetail()
 If zeOpen<>0 : PrintN("  The Zentaji Ethernet queue is enabled.") : EndIf
EndProcedure
Procedure HwLinkSayCounters()
 If zeOpen<>0
  Print("  Device drops ") : PrintDec(PeekQ(#ZEN_ETH_BASE+$98))
  Print(", rejected receives ") : PrintDec(zeRxRejects) : PrintNl()
 EndIf
EndProcedure

Procedure.i ZentajiNetworkPump(operation.i)
 If zeOpen<>0 : NetConsolePump() : EndIf
 ProcedureReturn 0
EndProcedure

Procedure.i ZentajiNetworkService(operation.i)
 If zeOpen=0 : ProcedureReturn 0 : EndIf
 Select operation
  Case #APS_DHCP : NetDhcpTick()
  Case #APS_NTP : NtpServiceTick()
  Case #APS_NET_REARM : NetConsoleRearm()
  Case #APS_HTTP : TcpTick()
 EndSelect
 ProcedureReturn 0
EndProcedure

Procedure ZentajiNetworkInit()
 LinkTxQueueInit(@zeTracked[0],#ZE_TX_GENERATION)
 LinkTxSetReceiptHooks(@zeSendTracked,@zeTrackedResult)
 NetWaitSetProgressHook(@HwPromptIdleWait)
 NetSetProtocolTickHook(@UdpServiceAdvance)
 TcpInit()
 NtpServiceBoot()
 AnvilPromptPumpBind(@ZentajiNetworkPump)
EndProcedure

Procedure ZentajiNetworkStatus()
 If ZentajiEthernetCarrier()=0
  PrintN("Zentaji Ethernet is disconnected. Attach net in the machine description.")
 ElseIf zeOpen=0
  PrintN("Zentaji Ethernet is attached. Use dhcp to open it and request a lease.")
 Else
  Print("Zentaji Ethernet MAC ") : PutLinkMac() : PrintNl()
  If NetIfUsable(#HW_LINK_WIRED)<>0
   Print("  IPv4 ") : PutIp(NetIPv4(#HW_LINK_WIRED))
   Print("  netmask ") : PutIp(NetMask(#HW_LINK_WIRED))
   Print("  gateway ") : PutIp(NetGateway(#HW_LINK_WIRED)) : PrintNl()
  EndIf
  NetDhcpSay(#HW_LINK_WIRED)
  HwLinkSayCounters()
 EndIf
EndProcedure

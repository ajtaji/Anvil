; Resident shared link-local IPv6 service. Compose ipv6_host.pbi, link receipts,
; random_service.pbi and netconsole.pbi first. All work runs on core 0 between
; receive dispatches. Device hooks supply generation and bounded filter setup.
; The service owns every host context, source list and outstanding link receipt.
Global *ipv6svcGeneration,*ipv6svcPrepare
Global ipv6svcBusy.i,ipv6svcCursor.i=1,ipv6svcClock.i,ipv6svcRaw.i,ipv6svcClockSet.i
Global Dim ipv6svcHost.IPv6Host[#NET_IF_KINDS]
Global Dim ipv6svcSources.a[#NET_IF_KINDS*1424]
Global Dim ipv6svcAddresses.a[#NET_IF_KINDS*16]
Global Dim ipv6svcPhysical.i[#NET_IF_KINDS]
Global Dim ipv6svcEpoch.i[#NET_IF_KINDS]
Global Dim ipv6svcState.i[#NET_IF_KINDS]
Global Dim ipv6svcError.i[#NET_IF_KINDS]
Global Dim ipv6svcReceipt.i[#NET_IF_KINDS]
Global Dim ipv6svcToken.i[#NET_IF_KINDS]
Global Dim ipv6svcDue.i[#NET_IF_KINDS]
Global Dim ipv6svcFrame.a[1514]
Global Dim ipv6svcRouters.IPv6DefaultRouters[#NET_IF_KINDS]
Global Dim ipv6svcRouterRows.a[#NET_IF_KINDS*128]
Global Dim ipv6svcRa.IPv6RouterAdvertisement[#NET_IF_KINDS]
Global Dim ipv6svcPrefixes.a[#NET_IF_KINDS*2520]
Global Dim ipv6svcRaCount.i[#NET_IF_KINDS]
Global Dim ipv6svcRaError.i[#NET_IF_KINDS]
Global Dim ipv6svcRsStarted.i[#NET_IF_KINDS]
Global Dim ipv6svcRsSent.i[#NET_IF_KINDS]
Global Dim ipv6svcRsRouterSeen.i[#NET_IF_KINDS]
Global Dim ipv6svcRsLeft.i[#NET_IF_KINDS]
Global Dim ipv6svcRsDue.i[#NET_IF_KINDS]
Global Dim ipv6svcRsReceipt.i[#NET_IF_KINDS]
Global Dim ipv6svcRsError.i[#NET_IF_KINDS]
Global Dim ipv6svcHop.i[#NET_IF_KINDS]
Global Dim ipv6svcReachable.i[#NET_IF_KINDS]
Global Dim ipv6svcRetransmit.i[#NET_IF_KINDS]
Global Dim ipv6svcMtu.i[#NET_IF_KINDS]
Procedure.i ipv6svc_Now()
 Define raw.i,elapsed.i
 raw=millis()&$FFFFFFFF
 If ipv6svcClockSet=0
  ipv6svcClockSet=1 : ipv6svcRaw=raw : ipv6svcClock=raw
 Else
  elapsed=(raw-ipv6svcRaw)&$FFFFFFFF
  ipv6svcClock=ipv6svcClock+elapsed : ipv6svcRaw=raw
 EndIf
 ProcedureReturn ipv6svcClock
EndProcedure
Procedure.i ipv6svc_Delay(limit.i)
 Define value.l,rc.i
 If limit=0 : ProcedureReturn 0 : EndIf
 If limit<0 : ProcedureReturn -810 : EndIf
 rc=RandomServiceBytes(@value,4)
 If rc<>4 : ProcedureReturn -810 : EndIf
 ProcedureReturn 1+((value&$FFFFFFFF) % limit)
EndProcedure
Procedure ipv6svc_DiscoveryTick(kind.i,now.i)
 Define rc.i,n.i,mac.i,p.i,i.i,delay.i
 rc=IPv6DefaultRoutersTick(@ipv6svcRouters[kind],ipv6svcEpoch[kind],now)
 If ipv6svcRsReceipt[kind]>0
  LinkTxProgress(kind) : rc=LinkTxReceipt(kind,ipv6svcRsReceipt[kind])
  If rc=0 : ProcedureReturn : EndIf
  ipv6svcRsReceipt[kind]=0
  If rc<0 : ipv6svcRsError[kind]=rc : ProcedureReturn : EndIf
  ipv6svcRsSent[kind]=ipv6svcRsSent[kind]+1
  If ipv6svcRsLeft[kind]>0 : ipv6svcRsLeft[kind]=ipv6svcRsLeft[kind]-1 : EndIf
  ipv6svcRsDue[kind]=now+4000
 EndIf
 If ipv6svcHost[kind]\phase<>#IPV6_HOST_READY Or ipv6svcRsError[kind]<>0 : ProcedureReturn : EndIf
 ; RFC 4861 6.3.7: zero-lifetime RAs do not stop solicitation. Even when a
 ; router advertises first, confirm at least one solicitation before stopping.
 If ipv6svcRsRouterSeen[kind]>0 And ipv6svcRsSent[kind]>0 : ProcedureReturn : EndIf
 If ipv6svcRsStarted[kind]=0
  delay=ipv6svc_Delay(1000)
  If delay<0 : ipv6svcRsError[kind]=delay : ProcedureReturn : EndIf
  ipv6svcRsStarted[kind]=1 : ipv6svcRsLeft[kind]=3 : ipv6svcRsDue[kind]=now+delay
 EndIf
 If ipv6svcRsLeft[kind]=0 Or now<ipv6svcRsDue[kind] : ProcedureReturn : EndIf
 mac=HwLinkMacPtr(kind) : p=@ipv6svcFrame[0]
 n=IPv6RouterSolicit(p+14,1500,@ipv6svcAddresses[kind*16],mac)
 If n<0 : ipv6svcRsError[kind]=n : ProcedureReturn : EndIf
 PokeA(p,51) : PokeA(p+1,51) : PokeA(p+2,0) : PokeA(p+3,0) : PokeA(p+4,0) : PokeA(p+5,2)
 For i=0 To 5 : PokeA(p+6+i,PeekA(mac+i)) : Next
 NetWriteBE16(p+12,$86DD)
 rc=LinkSendTracked(kind,p,n+14)
 If rc>0
  ipv6svcRsReceipt[kind]=rc
 ElseIf rc=0
  ipv6svcRsDue[kind]=now+100
 Else
  ipv6svcRsError[kind]=rc
 EndIf
EndProcedure
Procedure.i IPv6ServiceInput(kind.i,frame.i,bytes.i,out.i,capacity.i)
 Define query.IPv6MldQueryView,ip.IPv6PacketView
 Define delay.i,rc.i,now.i
 If kind<1 Or kind>=#NET_IF_KINDS : ProcedureReturn -800 : EndIf
 If ipv6svcState[kind]<>2 : ProcedureReturn 0 : EndIf
 ; Never configure filters or receive another frame while this RX span lives.
 now=ipv6svc_Now() : delay=0
 If bytes>=54 And bytes<=1514 And ipv6svcHost[kind]\phase=#IPV6_HOST_READY
  If NetReadBE16(frame+12)=$86DD And (PeekA(frame+6)&1)=0
   If IPv6EndpointBytesEqual(frame+6,HwLinkMacPtr(kind),6)=0
    rc=IPv6PacketParse(frame+14,bytes-14,@ip)
    If rc=0 And ip\protocol=58 And ip\payloadBytes>=1
     If PeekA(ip\payload)=134
      rc=IPv6RouterDecode(frame+14,bytes-14,@ipv6svcAddresses[kind*16],HwLinkTxMax(kind)-14,@ipv6svcRa[kind],@ipv6svcPrefixes[kind*2520],45)
      If rc=0
       rc=IPv6DefaultRoutersApply(@ipv6svcRouters[kind],ipv6svcEpoch[kind],now,@ipv6svcRa[kind]\source,ipv6svcRa[kind]\lifetime,ipv6svcRa[kind]\flags)
       ipv6svcRaError[kind]=rc
       ipv6svcRaCount[kind]=ipv6svcRaCount[kind]+1
       If ipv6svcRa[kind]\lifetime>0 : ipv6svcRsRouterSeen[kind]=1 : EndIf
       If ipv6svcRa[kind]\hopLimit<>0 : ipv6svcHop[kind]=ipv6svcRa[kind]\hopLimit : EndIf
       If ipv6svcRa[kind]\reachable>0 And ipv6svcRa[kind]\reachable<=3600000 : ipv6svcReachable[kind]=ipv6svcRa[kind]\reachable : EndIf
       If ipv6svcRa[kind]\retransmit<>0 : ipv6svcRetransmit[kind]=ipv6svcRa[kind]\retransmit : EndIf
       If ipv6svcRa[kind]\mtu<>0 : ipv6svcMtu[kind]=ipv6svcRa[kind]\mtu : EndIf
      Else
       ipv6svcRaError[kind]=rc
      EndIf
      ProcedureReturn 0
     EndIf
    EndIf
   EndIf
  EndIf
 EndIf
 If bytes>=54
  rc=IPv6MldQuery(frame+14,bytes-14,@query)
  If rc=0
   delay=ipv6svc_Delay(query\maxDelay) : If delay<0 : ProcedureReturn delay : EndIf
  EndIf
 EndIf
 ProcedureReturn IPv6HostInput(@ipv6svcHost[kind],ipv6svcEpoch[kind],now,frame,bytes,out,capacity,delay)
EndProcedure
Procedure IPv6ServiceTick()
 Define kind.i,now.i,generation.i,mac.i,p.i,i.i,rc.i,n.i,delay.i,token.i
 If ipv6svcBusy<>0 Or ipv6svcGeneration=0 Or ipv6svcPrepare=0 : ProcedureReturn : EndIf
 ipv6svcBusy=1
 kind=ipv6svcCursor : ipv6svcCursor=ipv6svcCursor+1
 If ipv6svcCursor>=#NET_IF_KINDS : ipv6svcCursor=1 : EndIf
 now=ipv6svc_Now()
 generation=ipv6svcGeneration(kind)
 If generation<=0
  ipv6svcState[kind]=0 : ipv6svcPhysical[kind]=0 : ipv6svcReceipt[kind]=0
  ipv6svcBusy=0 : ProcedureReturn
 EndIf
 If generation<>ipv6svcPhysical[kind]
  ipv6svcPhysical[kind]=generation : ipv6svcEpoch[kind]=ipv6svcEpoch[kind]+1
  ipv6svcState[kind]=1 : ipv6svcError[kind]=0 : ipv6svcReceipt[kind]=0 : ipv6svcDue[kind]=now
  ipv6svcRaCount[kind]=0 : ipv6svcRaError[kind]=0 : ipv6svcRsStarted[kind]=0
  ipv6svcRsLeft[kind]=0 : ipv6svcRsReceipt[kind]=0 : ipv6svcRsError[kind]=0
  ipv6svcRsSent[kind]=0 : ipv6svcRsRouterSeen[kind]=0
  ipv6svcHop[kind]=64 : ipv6svcReachable[kind]=30000 : ipv6svcRetransmit[kind]=1000 : ipv6svcMtu[kind]=HwLinkTxMax(kind)-14
  rc=IPv6DefaultRoutersInit(@ipv6svcRouters[kind],ipv6svcEpoch[kind],@ipv6svcRouterRows[kind*128],4,now)
  mac=HwLinkMacPtr(kind) : p=@ipv6svcAddresses[kind*16]
  If mac=0
   ipv6svcState[kind]=-1 : ipv6svcError[kind]=-800
  Else
   ; RFC 4291 appendix A modified EUI-64 link-local interface identifier.
   For i=0 To 15 : PokeA(p+i,0) : Next
   PokeA(p,254) : PokeA(p+1,128)
   PokeA(p+8,PeekA(mac)!2) : PokeA(p+9,PeekA(mac+1)) : PokeA(p+10,PeekA(mac+2))
   PokeA(p+11,255) : PokeA(p+12,254)
   For i=3 To 5 : PokeA(p+10+i,PeekA(mac+i)) : Next
  EndIf
 EndIf
 If ipv6svcState[kind]=1
  If now>=ipv6svcDue[kind]
   ipv6svcDue[kind]=now+20
   rc=ipv6svcPrepare(kind,generation,@ipv6svcAddresses[kind*16])
   If rc=1
    delay=ipv6svc_Delay(1000)
    If delay<0
     rc=delay
    Else
     rc=IPv6HostInit(@ipv6svcHost[kind],ipv6svcEpoch[kind],@ipv6svcAddresses[kind*16],HwLinkMacPtr(kind),@ipv6svcSources[kind*1424],1424,now,delay)
     If rc=0 : ipv6svcState[kind]=2 : EndIf
    EndIf
   EndIf
   If rc<0 : ipv6svcState[kind]=-1 : ipv6svcError[kind]=rc : EndIf
  EndIf
 ElseIf ipv6svcState[kind]=2
  If ipv6svcReceipt[kind]>0
   LinkTxProgress(kind)
   rc=LinkTxReceipt(kind,ipv6svcReceipt[kind])
   If rc<>0
    delay=ipv6svc_Delay(1000)
    If delay<0 : rc=delay : delay=1 : EndIf
    rc=IPv6HostSent(@ipv6svcHost[kind],ipv6svcEpoch[kind],now,ipv6svcToken[kind],rc,delay)
    ipv6svcReceipt[kind]=0
    If rc<0 : ipv6svcState[kind]=-1 : ipv6svcError[kind]=rc : EndIf
   EndIf
  Else
   n=IPv6HostStep(@ipv6svcHost[kind],ipv6svcEpoch[kind],now,@ipv6svcFrame[0],1514)
   If n>0
    token=ipv6svcHost[kind]\awaiting
    rc=LinkSendTracked(kind,@ipv6svcFrame[0],n)
    If rc>0
     ipv6svcReceipt[kind]=rc : ipv6svcToken[kind]=token
    Else
     rc=IPv6HostSent(@ipv6svcHost[kind],ipv6svcEpoch[kind],now,token,rc,1)
     If rc<0 : ipv6svcState[kind]=-1 : ipv6svcError[kind]=rc : EndIf
    EndIf
   ElseIf n<0
    ipv6svcState[kind]=-1 : ipv6svcError[kind]=n
   EndIf
  EndIf
 EndIf
 If ipv6svcState[kind]=2 : ipv6svc_DiscoveryTick(kind,now) : EndIf
 ipv6svcBusy=0
EndProcedure
Procedure.i IPv6ServiceBind(generation.i,prepare.i)
 If generation=0 Or prepare=0 Or ipv6svcGeneration<>0 : ProcedureReturn -800 : EndIf
 ipv6svcGeneration=generation : ipv6svcPrepare=prepare
 NetSetIPv6InputHook(@IPv6ServiceInput)
 NetSetProtocolTickHook(@IPv6ServiceTick)
 ProcedureReturn 0
EndProcedure

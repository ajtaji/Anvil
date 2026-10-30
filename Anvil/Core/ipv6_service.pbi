; Resident shared link-local IPv6 service. Compose ipv6_host.pbi, link receipts,
; random_service.pbi and netconsole.pbi first. All work runs on core 0 between
; receive dispatches. Device hooks supply generation and bounded filter setup.
; The service owns every host context, source list and outstanding link receipt.
XIncludeFile "Anvil/Network/ipv6_source.pbi"
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
; Four independently owned SLAAC addresses and eight on-link prefixes per link.
; Every address uses the confirmed LL membership's IID/group. No extra filter
; setup or borrowed receive storage is needed for these addresses.
#IPV6_SERVICE_ADDRESSES=4
#IPV6_SERVICE_PREFIXES=8
Global Dim ipv6svcOnLink.IPv6PrefixList[#NET_IF_KINDS]
Global Dim ipv6svcOnLinkRows.IPv6OnLinkPrefix[#NET_IF_KINDS*#IPV6_SERVICE_PREFIXES]
Global Dim ipv6svcOwner.IPv6AddressOwner[#NET_IF_KINDS*#IPV6_SERVICE_ADDRESSES]
Global Dim ipv6svcOwnerUsed.i[#NET_IF_KINDS*#IPV6_SERVICE_ADDRESSES]
Global Dim ipv6svcOwnerReceipt.i[#NET_IF_KINDS*#IPV6_SERVICE_ADDRESSES]
Global Dim ipv6svcOwnerToken.i[#NET_IF_KINDS*#IPV6_SERVICE_ADDRESSES]
Global Dim ipv6svcOwnerCursor.i[#NET_IF_KINDS]
Global Dim ipv6svcAddressError.i[#NET_IF_KINDS]
#IPV6_SERVICE_NEIGHBORS=8
Global Dim ipv6svcNeighbor.IPv6NeighborOwner[#NET_IF_KINDS*#IPV6_SERVICE_NEIGHBORS]
Global Dim ipv6svcNeighborUsed.i[#NET_IF_KINDS*#IPV6_SERVICE_NEIGHBORS]
Global Dim ipv6svcNeighborReceipt.i[#NET_IF_KINDS*#IPV6_SERVICE_NEIGHBORS]
Global Dim ipv6svcNeighborToken.i[#NET_IF_KINDS*#IPV6_SERVICE_NEIGHBORS]
Global Dim ipv6svcNeighborSource.IPv6AddressStorage[#NET_IF_KINDS*#IPV6_SERVICE_NEIGHBORS]
Global Dim ipv6svcNeighborCursor.i[#NET_IF_KINDS]
Global Dim ipv6svcNeighborError.i[#NET_IF_KINDS]
; One explicit diagnostic job. Network protocols will own their own data queues.
Global ipv6svcEchoState.i,ipv6svcEchoKind.i,ipv6svcEchoEpoch.i,ipv6svcEchoSlot.i,ipv6svcEchoGeneration.i
Global ipv6svcEchoStarted.i,ipv6svcEchoDeadline.i,ipv6svcEchoDue.i,ipv6svcEchoReceipt.i,ipv6svcEchoElapsed.i,ipv6svcEchoSerial.i
Global ipv6svcEchoSource.IPv6AddressStorage,ipv6svcEchoDestination.IPv6AddressStorage,ipv6svcEchoHop.IPv6AddressStorage
Global Dim ipv6svcEchoData.a[64]
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
Procedure.i ipv6svc_Assigned(kind.i,now.i,address.i)
 Define i.i,slot.i,state.i
 If ipv6svcState[kind]<>2 Or ipv6svcHost[kind]\phase<>#IPV6_HOST_READY : ProcedureReturn 0 : EndIf
 If IPv6EndpointBytesEqual(address,@ipv6svcAddresses[kind*16],16)<>0 : ProcedureReturn 1 : EndIf
 For i=0 To #IPV6_SERVICE_ADDRESSES-1
  slot=kind*#IPV6_SERVICE_ADDRESSES+i
  If ipv6svcOwnerUsed[slot]<>0
   state=IPv6AddressOwnerStatus(@ipv6svcOwner[slot],ipv6svcOwner[slot]\generation,now)
   If state=2 Or state=3
    If IPv6EndpointBytesEqual(address,@ipv6svcOwner[slot]\lifetime\address,16)<>0 : ProcedureReturn 1 : EndIf
   EndIf
  EndIf
 Next
 ProcedureReturn 0
EndProcedure
Procedure.i ipv6svc_NeighborFind(kind.i,address.i)
 Define i.i,slot.i
 For i=0 To #IPV6_SERVICE_NEIGHBORS-1
  slot=kind*#IPV6_SERVICE_NEIGHBORS+i
  If ipv6svcNeighborUsed[slot]<>0
   If IPv6EndpointBytesEqual(address,@ipv6svcNeighbor[slot]\target,16)<>0 : ProcedureReturn slot : EndIf
  EndIf
 Next
 ProcedureReturn -1
EndProcedure
; Reuse only an unused/failed slot. Live cache entries and their receipts are
; never silently evicted. force starts fresh resolution for an explicit request.
Procedure.i ipv6svc_NeighborGet(kind.i,now.i,address.i,source.i,force.i)
 Define i.i,slot.i,rc.i,generation.i
 slot=ipv6svc_NeighborFind(kind,address)
 If slot>=0
  If ipv6svcNeighbor[slot]\policy\state<>#IPV6_NC_FAILED Or force=0 : ProcedureReturn slot : EndIf
 Else
  For i=0 To #IPV6_SERVICE_NEIGHBORS-1
   rc=kind*#IPV6_SERVICE_NEIGHBORS+i
   If ipv6svcNeighborUsed[rc]=0 Or ipv6svcNeighbor[rc]\policy\state=#IPV6_NC_FAILED
    slot=rc : Break
   EndIf
  Next
 EndIf
 If slot<0 : ProcedureReturn -880 : EndIf
 generation=ipv6svcNeighbor[slot]\generation+1
 rc=IPv6NeighborOwnerInit(@ipv6svcNeighbor[slot],generation,address,HwLinkMacPtr(kind),now,ipv6svcRetransmit[kind])
 If rc<>0 : ProcedureReturn rc : EndIf
 ipv6svcNeighborUsed[slot]=1 : ipv6svcNeighborReceipt[slot]=0 : ipv6svcNeighborToken[slot]=0
 For i=0 To 15 : PokeA(@ipv6svcNeighborSource[slot]+i,PeekA(source+i)) : Next
 ProcedureReturn slot
EndProcedure
Procedure ipv6svc_NeighborLearn(kind.i,now.i,address.i,mac.i,router.i)
 Define slot.i,rc.i,i.i,nonzero.i
 If mac<>0
  If (PeekA(mac)&1)<>0 : ProcedureReturn : EndIf
  nonzero=0 : For i=0 To 5 : nonzero=nonzero|PeekA(mac+i) : Next
  If nonzero=0 : ProcedureReturn : EndIf
 EndIf
 slot=ipv6svc_NeighborFind(kind,address)
 If slot<0 And mac<>0 : slot=ipv6svc_NeighborGet(kind,now,address,@ipv6svcAddresses[kind*16],0) : EndIf
 If slot>=0
  rc=IPv6NeighborOwnerLearn(@ipv6svcNeighbor[slot],ipv6svcNeighbor[slot]\generation,now,mac,router)
  If rc<0 : ipv6svcNeighborError[kind]=rc : EndIf
  If ipv6svcNeighbor[slot]\awaiting=0 : ipv6svcNeighborReceipt[slot]=0 : EndIf
 EndIf
EndProcedure
Procedure ipv6svc_NeighborTick(kind.i,now.i)
 Define i.i,slot.i,rc.i,n.i,token.i
 If ipv6svcHost[kind]\phase<>#IPV6_HOST_READY : ProcedureReturn : EndIf
 For i=0 To #IPV6_SERVICE_NEIGHBORS-1
  slot=kind*#IPV6_SERVICE_NEIGHBORS+i
  If ipv6svcNeighborUsed[slot]<>0 And ipv6svcNeighborReceipt[slot]>0
   rc=LinkTxReceipt(kind,ipv6svcNeighborReceipt[slot])
   If rc<>0
    ipv6svcNeighborReceipt[slot]=0
    rc=IPv6NeighborOwnerSent(@ipv6svcNeighbor[slot],ipv6svcNeighbor[slot]\generation,now,ipv6svcNeighborToken[slot],rc)
    If rc<0 And rc<>#IPV6_NEIGHBOR_OWNER_STALE : ipv6svcNeighborError[kind]=rc : EndIf
   EndIf
  EndIf
 Next
 slot=kind*#IPV6_SERVICE_NEIGHBORS+ipv6svcNeighborCursor[kind]
 ipv6svcNeighborCursor[kind]=(ipv6svcNeighborCursor[kind]+1) % #IPV6_SERVICE_NEIGHBORS
 If ipv6svcNeighborUsed[slot]=0 Or ipv6svcNeighborReceipt[slot]<>0 : ProcedureReturn : EndIf
 If ipv6svc_Assigned(kind,now,@ipv6svcNeighborSource[slot])=0
  ; A solicitation must always use an assigned source. Fall back to the
  ; confirmed LL address if a prior data source expired between packets.
  For i=0 To 15 : PokeA(@ipv6svcNeighborSource[slot]+i,PeekA(@ipv6svcAddresses[kind*16]+i)) : Next
 EndIf
 n=IPv6NeighborOwnerStep(@ipv6svcNeighbor[slot],ipv6svcNeighbor[slot]\generation,now,@ipv6svcNeighborSource[slot],@ipv6svcFrame[0],1514)
 If n>0
  token=ipv6svcNeighbor[slot]\awaiting
  rc=LinkSendTracked(kind,@ipv6svcFrame[0],n)
  If rc>0
   ipv6svcNeighborReceipt[slot]=rc : ipv6svcNeighborToken[slot]=token
  Else
   rc=IPv6NeighborOwnerSent(@ipv6svcNeighbor[slot],ipv6svcNeighbor[slot]\generation,now,token,rc)
   If rc<0 : ipv6svcNeighborError[kind]=rc : EndIf
  EndIf
 ElseIf n<0
  ipv6svcNeighborError[kind]=n
 EndIf
EndProcedure
Procedure ipv6svc_NeighborInput(kind.i,now.i,frame.i,bytes.i)
 Define ip.IPv6PacketView,nd.IPv6NeighborView,group.IPv6AddressStorage
 Define slot.i,rc.i,reachable.i,i.i,local.i
 If ipv6svcHost[kind]\phase<>#IPV6_HOST_READY Or bytes<54 : ProcedureReturn : EndIf
 rc=IPv6NeighborParse(frame+14,bytes-14,@ip,@nd) : If rc<>0 : ProcedureReturn : EndIf
 If nd\kind=135 And nd\sourceMac<>0 And IPv6AddressUnspecified(ip\source)=0
  If ipv6svc_Assigned(kind,now,nd\target)<>0
   rc=IPv6SolicitedNode(nd\target,@group)
   If IPv6EndpointBytesEqual(ip\destination,nd\target,16)<>0 Or IPv6EndpointBytesEqual(ip\destination,@group,16)<>0
    ipv6svc_NeighborLearn(kind,now,ip\source,nd\sourceMac,-1)
   EndIf
  EndIf
 ElseIf nd\kind=136
  slot=ipv6svc_NeighborFind(kind,nd\target) : If slot<0 : ProcedureReturn : EndIf
  local=@ipv6svcAddresses[kind*16]
  If ipv6svc_Assigned(kind,now,ip\destination)<>0 : local=ip\destination : EndIf
  reachable=ipv6svc_Delay(ipv6svcReachable[kind])
  If reachable<0 : ipv6svcNeighborError[kind]=reachable : ProcedureReturn : EndIf
  reachable=ipv6svcReachable[kind]/2+reachable
  rc=IPv6NeighborOwnerInput(@ipv6svcNeighbor[slot],ipv6svcNeighbor[slot]\generation,now,local,frame,bytes,reachable)
  If ipv6svcNeighbor[slot]\awaiting=0 : ipv6svcNeighborReceipt[slot]=0 : EndIf
  If rc=2
   rc=IPv6DefaultRoutersApply(@ipv6svcRouters[kind],ipv6svcEpoch[kind],now,nd\target,0,0)
   If ipv6svcEchoState>0 And ipv6svcEchoState<4 And ipv6svcEchoKind=kind
    If IPv6EndpointBytesEqual(@ipv6svcEchoHop,nd\target,16)<>0 And IPv6EndpointBytesEqual(@ipv6svcEchoDestination,nd\target,16)=0 : ipv6svcEchoState=-885 : EndIf
   EndIf
  EndIf
 EndIf
EndProcedure
; Explicit source avoids pretending the unfinished RFC6724 automatic source
; selection policy is complete. Caller selects a currently assigned source.
; Shared TCP callbacks: no receive pumping, waiting or borrowed output.
Procedure.i IPv6ServiceSourceValid(kind.i,source.i)
 If kind<1 Or kind>=#NET_IF_KINDS Or source=0 : ProcedureReturn 0 : EndIf
 If HwLinkReady(kind)=0 : ProcedureReturn 0 : EndIf
 ProcedureReturn ipv6svc_Assigned(kind,ipv6svc_Now(),source)
EndProcedure
Procedure.i IPv6ServiceResolve(kind.i,source.i,destination.i,mac.i)
 Define hop.IPv6AddressStorage
 Define now.i,rc.i,i.i,j.i,slot.i,failed.i,index.i
 Define *router.IPv6DefaultRouter
 If IPv6ServiceSourceValid(kind,source)<>1 Or destination=0 Or mac=0 : ProcedureReturn -881 : EndIf
 If PeekA(destination)=255 Or IPv6AddressUnspecified(destination)<>0 : ProcedureReturn -881 : EndIf
 now=ipv6svc_Now()
 For i=0 To 15 : PokeA(@hop+i,PeekA(destination+i)) : Next
 rc=IPv6PrefixListMatch(@ipv6svcOnLink[kind],ipv6svcEpoch[kind],now,destination)
 If PeekA(destination)=254 And (PeekA(destination+1)&192)=128 : rc=1 : EndIf
 If rc<0 : ProcedureReturn rc : EndIf
 If rc=0
  If PeekA(source)=254 And (PeekA(source+1)&192)=128 : ProcedureReturn -883 : EndIf
  failed=0
  For j=0 To 3
   *router=@ipv6svcRouterRows[kind*128+j*32]
   slot=ipv6svc_NeighborFind(kind,@*router\address)
   If slot>=0
    If ipv6svcNeighbor[slot]\policy\state=#IPV6_NC_FAILED : failed=failed|(1<<j) : EndIf
   EndIf
  Next
  index=IPv6DefaultRoutersSelect(@ipv6svcRouters[kind],ipv6svcEpoch[kind],now,failed)
  If index<=0 : ProcedureReturn -883 : EndIf
  *router=@ipv6svcRouterRows[kind*128+(index-1)*32]
  For i=0 To 15 : PokeA(@hop+i,PeekA(@*router\address+i)) : Next
 EndIf
 slot=ipv6svc_NeighborGet(kind,now,@hop,source,0)
 If slot<0 : ProcedureReturn slot : EndIf
 rc=IPv6NeighborOwnerUse(@ipv6svcNeighbor[slot],ipv6svcNeighbor[slot]\generation,now)
 If rc<0 : ProcedureReturn -888 : EndIf
 If rc=0 : ProcedureReturn 0 : EndIf
 For i=0 To 5 : PokeA(mac+i,PeekA(@ipv6svcNeighbor[slot]\policy\mac+i)) : Next
 ProcedureReturn 1
EndProcedure

; Route first, then RFC6724 comparison of this interface's assigned
; public addresses. Longest on-link route wins; selected link breaks equal
; route ties. Scoped literals without a zone follow that selected interface.
Procedure.i IPv6ServiceSelect(destination.i,source.i)
 Define chosen.IPv6AddressStorage,candidate.IPv6AddressStorage
 Define kind.i,now.i,route.i,bestRoute.i,bestKind.i,bestDeprecated.i
 Define i.i,j.i,slot.i,state.i,deprecated.i,failed.i,index.i,rc.i
 Define *router.IPv6DefaultRouter
 If destination=0 Or source=0 : ProcedureReturn -881 : EndIf
 If PeekA(destination)=255 Or IPv6AddressUnspecified(destination)<>0 : ProcedureReturn -881 : EndIf
 If IPv6SourceLabel(destination)=0 Or IPv6SourceLabel(destination)=3 Or IPv6SourceLabel(destination)=4 : ProcedureReturn -881 : EndIf
 now=ipv6svc_Now() : bestKind=0 : bestRoute=-1
 For kind=1 To #NET_IF_KINDS-1
  If HwLinkReady(kind)<>0 And ipv6svcState[kind]=2 And ipv6svcHost[kind]\phase=#IPV6_HOST_READY
   route=IPv6PrefixListMatch(@ipv6svcOnLink[kind],ipv6svcEpoch[kind],now,destination)
   If IPv6SourceScope(destination)=2 : route=129 : EndIf
   If route=0
    failed=0
    For j=0 To 3
     *router=@ipv6svcRouterRows[kind*128+j*32]
     slot=ipv6svc_NeighborFind(kind,@*router\address)
     If slot>=0
      If ipv6svcNeighbor[slot]\policy\state=#IPV6_NC_FAILED : failed=failed|(1<<j) : EndIf
     EndIf
    Next
    index=IPv6DefaultRoutersSelect(@ipv6svcRouters[kind],ipv6svcEpoch[kind],now,failed)
    If index<=0 : route=-1 : EndIf
   EndIf
   If route>=0
    For i=0 To 15 : PokeA(@candidate+i,ipv6svcAddresses[kind*16+i]) : Next
    deprecated=0
    For j=0 To #IPV6_SERVICE_ADDRESSES-1
     slot=kind*#IPV6_SERVICE_ADDRESSES+j
     If ipv6svcOwnerUsed[slot]<>0
      state=IPv6AddressOwnerStatus(@ipv6svcOwner[slot],ipv6svcOwner[slot]\generation,now)
      If state=2 Or state=3
       rc=IPv6SourceBetter(destination,@ipv6svcOwner[slot]\lifetime\address,Bool(state=3),64,@candidate,deprecated,64)
       If rc=1
        For i=0 To 15 : PokeA(@candidate+i,PeekA(@ipv6svcOwner[slot]\lifetime\address+i)) : Next
        deprecated=Bool(state=3)
       EndIf
      EndIf
     EndIf
    Next
    If IPv6SourceScope(@candidate)>=IPv6SourceScope(destination)
     rc=0
     If bestKind=0 Or route>bestRoute
      rc=1
     ElseIf route=bestRoute
      If kind=LinkKind() And bestKind<>LinkKind() : rc=1 : EndIf
     EndIf
     If rc=1
      For i=0 To 15 : PokeA(@chosen+i,PeekA(@candidate+i)) : Next
      bestKind=kind : bestRoute=route
     EndIf
    EndIf
   EndIf
  EndIf
 Next
 If bestKind=0 : ProcedureReturn -883 : EndIf
 For i=0 To 15 : PokeA(source+i,PeekA(@chosen+i)) : Next
 ProcedureReturn bestKind
EndProcedure

Procedure.i IPv6ServiceEchoStart(source.i,destination.i)
 Define kind.i,found.i,now.i,rc.i,i.i,slot.i,failed.i,j.i,index.i
 Define *router.IPv6DefaultRouter
 If source=0 Or destination=0 : ProcedureReturn -881 : EndIf
 If IPv6AddressUnspecified(source)<>0 Or IPv6AddressUnspecified(destination)<>0 Or PeekA(source)=255 Or PeekA(destination)=255 : ProcedureReturn -881 : EndIf
 If ipv6svcEchoState>0 And ipv6svcEchoState<4 : ProcedureReturn -882 : EndIf
 now=ipv6svc_Now() : found=0
 For kind=1 To #NET_IF_KINDS-1
  If ipv6svc_Assigned(kind,now,source)<>0
   If found<>0 : ProcedureReturn -881 : EndIf
   found=kind
  EndIf
 Next
 If found=0 : ProcedureReturn -881 : EndIf
 kind=found
 For i=0 To 15
  PokeA(@ipv6svcEchoSource+i,PeekA(source+i)) : PokeA(@ipv6svcEchoDestination+i,PeekA(destination+i))
  PokeA(@ipv6svcEchoHop+i,PeekA(destination+i))
 Next
 rc=IPv6PrefixListMatch(@ipv6svcOnLink[kind],ipv6svcEpoch[kind],now,destination)
 If PeekA(destination)=254 And (PeekA(destination+1)&192)=128 : rc=1 : EndIf
 If rc=0
  ; Link-local source addresses must never cross a router.
  If PeekA(source)=254 And (PeekA(source+1)&192)=128 : ProcedureReturn -883 : EndIf
  failed=0
  For j=0 To 3
   *router=@ipv6svcRouterRows[kind*128+j*32]
   slot=ipv6svc_NeighborFind(kind,@*router\address)
   If slot>=0
    If ipv6svcNeighbor[slot]\policy\state=#IPV6_NC_FAILED : failed=failed|(1<<j) : EndIf
   EndIf
  Next
  index=IPv6DefaultRoutersSelect(@ipv6svcRouters[kind],ipv6svcEpoch[kind],now,failed)
  If index<=0 : ProcedureReturn -883 : EndIf
  *router=@ipv6svcRouterRows[kind*128+(index-1)*32]
  For i=0 To 15 : PokeA(@ipv6svcEchoHop+i,PeekA(@*router\address+i)) : Next
 ElseIf rc<0
  ProcedureReturn rc
 EndIf
 slot=ipv6svc_NeighborGet(kind,now,@ipv6svcEchoHop,source,1) : If slot<0 : ProcedureReturn slot : EndIf
 For i=0 To 15 : PokeA(@ipv6svcNeighborSource[slot]+i,PeekA(source+i)) : Next
 rc=RandomServiceBytes(@ipv6svcEchoData[0],64) : If rc<>64 : ProcedureReturn -810 : EndIf
 ipv6svcEchoData[0]=128 : ipv6svcEchoData[1]=0 : ipv6svcEchoData[2]=0 : ipv6svcEchoData[3]=0
 ipv6svcEchoKind=kind : ipv6svcEchoEpoch=ipv6svcEpoch[kind] : ipv6svcEchoSlot=slot
 ipv6svcEchoGeneration=ipv6svcNeighbor[slot]\generation
 ipv6svcEchoStarted=now : ipv6svcEchoDeadline=now+10000 : ipv6svcEchoDue=now : ipv6svcEchoReceipt=0 : ipv6svcEchoElapsed=0
 ipv6svcEchoSerial=ipv6svcEchoSerial+1 : ipv6svcEchoState=1
 ProcedureReturn 0
EndProcedure
Procedure ipv6svc_EchoTick(kind.i,now.i)
 Define rc.i,slot.i,p.i,i.i,routeValid.i
 Define *router.IPv6DefaultRouter
 If ipv6svcEchoState<1 Or ipv6svcEchoState>3 Or ipv6svcEchoKind<>kind : ProcedureReturn : EndIf
 If ipv6svcEchoEpoch<>ipv6svcEpoch[kind] Or ipv6svc_Assigned(kind,now,@ipv6svcEchoSource)=0 : ipv6svcEchoState=-886 : ProcedureReturn : EndIf
 If now>=ipv6svcEchoDeadline : ipv6svcEchoState=-887 : ProcedureReturn : EndIf
 routeValid=0
 If IPv6EndpointBytesEqual(@ipv6svcEchoHop,@ipv6svcEchoDestination,16)<>0
  routeValid=IPv6PrefixListMatch(@ipv6svcOnLink[kind],ipv6svcEpoch[kind],now,@ipv6svcEchoDestination)
  If PeekA(@ipv6svcEchoDestination)=254 And (PeekA(@ipv6svcEchoDestination+1)&192)=128 : routeValid=1 : EndIf
 Else
  For i=0 To 3
   *router=@ipv6svcRouterRows[kind*128+i*32]
   If *router\until>now And IPv6EndpointBytesEqual(@*router\address,@ipv6svcEchoHop,16)<>0 : routeValid=1 : EndIf
  Next
 EndIf
 If routeValid<=0 : ipv6svcEchoState=-883 : ProcedureReturn : EndIf
 slot=ipv6svcEchoSlot
 If ipv6svcNeighborUsed[slot]=0 Or ipv6svcNeighbor[slot]\generation<>ipv6svcEchoGeneration : ipv6svcEchoState=-888 : ProcedureReturn : EndIf
 If ipv6svcEchoState=2
  rc=LinkTxReceipt(kind,ipv6svcEchoReceipt)
  If rc<0 : ipv6svcEchoState=-884 : ElseIf rc=1 : ipv6svcEchoState=3 : EndIf
  ProcedureReturn
 EndIf
 If ipv6svcEchoState<>1 Or now<ipv6svcEchoDue : ProcedureReturn : EndIf
 rc=IPv6NeighborOwnerUse(@ipv6svcNeighbor[slot],ipv6svcEchoGeneration,now)
 If rc<0 : ipv6svcEchoState=-888 : ProcedureReturn : EndIf
 If rc=0 : ProcedureReturn : EndIf
 p=@ipv6svcFrame[0]
 rc=IPv6PacketHeader(p+14,1500,@ipv6svcEchoSource,@ipv6svcEchoDestination,64,58,ipv6svcHop[kind],0,0)
 If rc<>40 : ipv6svcEchoState=rc : ProcedureReturn : EndIf
 For i=0 To 5
  PokeA(p+i,PeekA(@ipv6svcNeighbor[slot]\policy\mac+i)) : PokeA(p+6+i,PeekA(HwLinkMacPtr(kind)+i))
 Next
 NetWriteBE16(p+12,$86DD)
 For i=0 To 63 : PokeA(p+54+i,ipv6svcEchoData[i]) : Next
 rc=IPv6TransportChecksum(@ipv6svcEchoSource,@ipv6svcEchoDestination,58,p+54,64)
 NetWriteBE16(p+56,rc)
 rc=LinkSendTracked(kind,p,118)
 If rc>0
  ipv6svcEchoReceipt=rc : ipv6svcEchoState=2
 ElseIf rc<0
  ipv6svcEchoState=-884
 Else
  ipv6svcEchoDue=now+100
 EndIf
EndProcedure
Procedure ipv6svc_EchoInput(kind.i,now.i,frame.i,bytes.i)
 Define ip.IPv6PacketView
 Define rc.i,slot.i,reachable.i
 If ipv6svcEchoState<2 Or ipv6svcEchoState>3 Or ipv6svcEchoKind<>kind : ProcedureReturn : EndIf
 If ipv6svcEchoEpoch<>ipv6svcEpoch[kind] Or now>=ipv6svcEchoDeadline : ProcedureReturn : EndIf
 If ipv6svc_Assigned(kind,now,@ipv6svcEchoSource)=0 : ProcedureReturn : EndIf
 If IPv6EndpointBytesEqual(frame,HwLinkMacPtr(kind),6)=0 : ProcedureReturn : EndIf
 rc=IPv6PacketParse(frame+14,bytes-14,@ip) : If rc<>0 : ProcedureReturn : EndIf
 If ip\protocol<>58 Or ip\payloadBytes<>64 Or PeekA(ip\payload)<>129 Or PeekA(ip\payload+1)<>0 : ProcedureReturn : EndIf
 If IPv6EndpointBytesEqual(ip\source,@ipv6svcEchoDestination,16)=0 Or IPv6EndpointBytesEqual(ip\destination,@ipv6svcEchoSource,16)=0 : ProcedureReturn : EndIf
 If IPv6EndpointBytesEqual(ip\payload+4,@ipv6svcEchoData[4],60)=0 : ProcedureReturn : EndIf
 rc=IPv6TransportChecksum(ip\source,ip\destination,58,ip\payload,64) : If rc<>0 : ProcedureReturn : EndIf
 ipv6svcEchoElapsed=now-ipv6svcEchoStarted : ipv6svcEchoState=4
 slot=ipv6svcEchoSlot
 If ipv6svcNeighborUsed[slot]<>0 And ipv6svcNeighbor[slot]\generation=ipv6svcEchoGeneration
  reachable=ipv6svc_Delay(ipv6svcReachable[kind])
  If reachable>0
   rc=IPv6NeighborOwnerConfirm(@ipv6svcNeighbor[slot],ipv6svcEchoGeneration,now,ipv6svcReachable[kind]/2+reachable)
   ipv6svcNeighborReceipt[slot]=0
  EndIf
 EndIf
EndProcedure
Procedure ipv6svc_DiscardAddresses(kind.i)
 Define i.i,slot.i
 For i=0 To #IPV6_SERVICE_ADDRESSES-1
  slot=kind*#IPV6_SERVICE_ADDRESSES+i
  ipv6svcOwnerUsed[slot]=0 : ipv6svcOwnerReceipt[slot]=0 : ipv6svcOwnerToken[slot]=0
 Next
 ipv6svcOwnerCursor[kind]=0
 For i=0 To #IPV6_SERVICE_NEIGHBORS-1
  slot=kind*#IPV6_SERVICE_NEIGHBORS+i
  ipv6svcNeighborUsed[slot]=0 : ipv6svcNeighborReceipt[slot]=0 : ipv6svcNeighborToken[slot]=0
 Next
 ipv6svcNeighborCursor[kind]=0
 If ipv6svcEchoKind=kind And ipv6svcEchoState>0 And ipv6svcEchoState<4 : ipv6svcEchoState=-886 : EndIf
EndProcedure
; Merge only the advertised information. Omission never withdraws another
; router's address/prefix, and L/A are independently applied.
Procedure ipv6svc_ApplyPrefixes(kind.i,now.i)
 Define *pio.IPv6RouterPrefix
 Define i.i,j.i,slot.i,found.i,empty.i,rc.i,state.i,delay.i,generation.i
 ipv6svcAddressError[kind]=0
 For i=0 To ipv6svcRa[kind]\prefixCount-1
  *pio=@ipv6svcPrefixes[kind*2520+i*SizeOf(IPv6RouterPrefix)]
  rc=IPv6PrefixListApply(@ipv6svcOnLink[kind],ipv6svcEpoch[kind],now,@*pio\prefix,*pio\length,*pio\onlink,*pio\valid)
  If rc<>0 : ipv6svcAddressError[kind]=rc : EndIf
  If *pio\autonomous=1 And *pio\length=64 And *pio\preferred<=*pio\valid
   found=-1 : empty=-1
   For j=0 To #IPV6_SERVICE_ADDRESSES-1
    slot=kind*#IPV6_SERVICE_ADDRESSES+j
    If ipv6svcOwnerUsed[slot]<>0
     If IPv6EndpointBytesEqual(@ipv6svcOwner[slot]\lifetime\address,@*pio\prefix,8)<>0
      found=slot
     Else
      state=IPv6AddressOwnerStatus(@ipv6svcOwner[slot],ipv6svcOwner[slot]\generation,now)
      If state=0 : ipv6svcOwnerUsed[slot]=0 : ipv6svcOwnerReceipt[slot]=0 : EndIf
     EndIf
    EndIf
    If ipv6svcOwnerUsed[slot]=0 And empty<0 : empty=slot : EndIf
   Next
   If found<0 And *pio\valid>0
    If empty<0
     ipv6svcAddressError[kind]=1
    Else
     generation=ipv6svcOwner[empty]\generation+1
     rc=IPv6AddressOwnerInit(@ipv6svcOwner[empty],generation,@*pio\prefix,@ipv6svcAddresses[kind*16],@ipv6svcHost[kind]\membership\group,HwLinkMacPtr(kind),now)
     If rc=0
      found=empty : ipv6svcOwnerUsed[found]=1 : ipv6svcOwnerReceipt[found]=0 : ipv6svcOwnerToken[found]=0
     Else
      ipv6svcAddressError[kind]=rc
     EndIf
    EndIf
   EndIf
   If found>=0
    delay=ipv6svc_Delay(1000)
    If delay<0
     ipv6svcAddressError[kind]=delay
    Else
     ; Wi-Fi authentication is not SEND authentication. Preserve RFC4862's
     ; two-hour lifetime rule for all ordinary Router Advertisements.
     rc=IPv6AddressOwnerApply(@ipv6svcOwner[found],ipv6svcOwner[found]\generation,now,*pio\valid,*pio\preferred,0,delay,ipv6svcRetransmit[kind])
     If rc<0 : ipv6svcAddressError[kind]=rc : EndIf
     If rc=1 : ipv6svcOwnerReceipt[found]=0 : ipv6svcOwnerToken[found]=0 : EndIf
    EndIf
   EndIf
  EndIf
 Next
EndProcedure
Procedure ipv6svc_AddressTick(kind.i,now.i)
 Define i.i,slot.i,rc.i,n.i,state.i,token.i
 If ipv6svcHost[kind]\phase<>#IPV6_HOST_READY
  ipv6svc_DiscardAddresses(kind) : ProcedureReturn
 EndIf
 rc=IPv6PrefixListTick(@ipv6svcOnLink[kind],ipv6svcEpoch[kind],now)
 ; Consume all receipts before issuing at most one new DAD frame. Never let
 ; later frames displace an unobserved completion in the bounded link queue.
 For i=0 To #IPV6_SERVICE_ADDRESSES-1
  slot=kind*#IPV6_SERVICE_ADDRESSES+i
  If ipv6svcOwnerUsed[slot]<>0
   state=IPv6AddressOwnerStatus(@ipv6svcOwner[slot],ipv6svcOwner[slot]\generation,now)
   If state=0
    ipv6svcOwnerUsed[slot]=0 : ipv6svcOwnerReceipt[slot]=0
   ElseIf ipv6svcOwnerReceipt[slot]>0
    rc=LinkTxReceipt(kind,ipv6svcOwnerReceipt[slot])
    If rc<>0
     ipv6svcOwnerReceipt[slot]=0
     rc=IPv6AddressOwnerSent(@ipv6svcOwner[slot],ipv6svcOwner[slot]\generation,now,ipv6svcOwnerToken[slot],rc)
     If rc<0 And rc<>#IPV6_OWNER_STALE : ipv6svcAddressError[kind]=rc : EndIf
    EndIf
   EndIf
  EndIf
 Next
 slot=kind*#IPV6_SERVICE_ADDRESSES+ipv6svcOwnerCursor[kind]
 ipv6svcOwnerCursor[kind]=(ipv6svcOwnerCursor[kind]+1) % #IPV6_SERVICE_ADDRESSES
 If ipv6svcOwnerUsed[slot]=0 Or ipv6svcOwnerReceipt[slot]<>0 : ProcedureReturn : EndIf
 n=IPv6AddressOwnerStep(@ipv6svcOwner[slot],ipv6svcOwner[slot]\generation,now,@ipv6svcFrame[0],1514)
 If n>0
  token=ipv6svcOwner[slot]\awaiting
  rc=LinkSendTracked(kind,@ipv6svcFrame[0],n)
  If rc>0
   ipv6svcOwnerReceipt[slot]=rc : ipv6svcOwnerToken[slot]=token
  Else
   rc=IPv6AddressOwnerSent(@ipv6svcOwner[slot],ipv6svcOwner[slot]\generation,now,token,rc)
   If rc<0 : ipv6svcAddressError[kind]=rc : EndIf
  EndIf
 ElseIf n<0
  ipv6svcAddressError[kind]=n
 EndIf
EndProcedure
; An RA may be unicast to any assigned address, including a deprecated one.
Procedure.i ipv6svc_RaLocal(kind.i,now.i,destination.i)
 Define i.i,slot.i,state.i
 For i=0 To #IPV6_SERVICE_ADDRESSES-1
  slot=kind*#IPV6_SERVICE_ADDRESSES+i
  If ipv6svcOwnerUsed[slot]<>0
   state=IPv6AddressOwnerStatus(@ipv6svcOwner[slot],ipv6svcOwner[slot]\generation,now)
   If state=2 Or state=3
    If IPv6EndpointBytesEqual(destination,@ipv6svcOwner[slot]\lifetime\address,16)<>0
     ProcedureReturn @ipv6svcOwner[slot]\lifetime\address
    EndIf
   EndIf
  EndIf
 Next
 ProcedureReturn @ipv6svcAddresses[kind*16]
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
 Define delay.i,rc.i,now.i,i.i,slot.i,local.i
 If kind<1 Or kind>=#NET_IF_KINDS : ProcedureReturn -800 : EndIf
 If ipv6svcState[kind]<>2 : ProcedureReturn 0 : EndIf
 ; Never configure filters or receive another frame while this RX span lives.
 now=ipv6svc_Now() : delay=0
 If bytes>=54 And bytes<=1514 And ipv6svcHost[kind]\phase=#IPV6_HOST_READY
  If NetReadBE16(frame+12)=$86DD And (PeekA(frame+6)&1)=0
   If IPv6EndpointBytesEqual(frame+6,HwLinkMacPtr(kind),6)=0
    rc=IPv6PacketParse(frame+14,bytes-14,@ip)
    If rc=0 And ip\protocol=6
     rc=NetTcp6Input(kind,frame,bytes)
     If rc=#NET_IN_TCP : ProcedureReturn #NET_IN_TCP : EndIf
     If rc<0 : ProcedureReturn rc : EndIf
     ProcedureReturn 0
    EndIf
    If rc=0 And ip\protocol=58 And ip\payloadBytes>=1
     If PeekA(ip\payload)=134
      local=ipv6svc_RaLocal(kind,now,ip\destination)
      rc=IPv6RouterDecode(frame+14,bytes-14,local,HwLinkTxMax(kind)-14,@ipv6svcRa[kind],@ipv6svcPrefixes[kind*2520],45)
      If rc=0
       rc=IPv6DefaultRoutersApply(@ipv6svcRouters[kind],ipv6svcEpoch[kind],now,@ipv6svcRa[kind]\source,ipv6svcRa[kind]\lifetime,ipv6svcRa[kind]\flags)
       ipv6svcRaError[kind]=rc
       ipv6svcRaCount[kind]=ipv6svcRaCount[kind]+1
       If ipv6svcRa[kind]\lifetime>0 : ipv6svcRsRouterSeen[kind]=1 : EndIf
       If ipv6svcRa[kind]\hopLimit<>0 : ipv6svcHop[kind]=ipv6svcRa[kind]\hopLimit : EndIf
       If ipv6svcRa[kind]\reachable>0 And ipv6svcRa[kind]\reachable<=3600000 : ipv6svcReachable[kind]=ipv6svcRa[kind]\reachable : EndIf
       If ipv6svcRa[kind]\retransmit<>0 : ipv6svcRetransmit[kind]=ipv6svcRa[kind]\retransmit : EndIf
       If ipv6svcRa[kind]\mtu<>0 : ipv6svcMtu[kind]=ipv6svcRa[kind]\mtu : EndIf
       ipv6svc_ApplyPrefixes(kind,now)
       local=0 : If ipv6svcRa[kind]\hasMac<>0 : local=@ipv6svcRa[kind]\mac : EndIf
       ipv6svc_NeighborLearn(kind,now,@ipv6svcRa[kind]\source,local,1)
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
  ipv6svc_NeighborInput(kind,now,frame,bytes)
  ipv6svc_EchoInput(kind,now,frame,bytes)
  rc=IPv6MldQuery(frame+14,bytes-14,@query)
  If rc=0
   delay=ipv6svc_Delay(query\maxDelay) : If delay<0 : ProcedureReturn delay : EndIf
  EndIf
 EndIf
 rc=IPv6HostInput(@ipv6svcHost[kind],ipv6svcEpoch[kind],now,frame,bytes,out,capacity,delay)
 If ipv6svcHost[kind]\phase<>#IPV6_HOST_READY
  ipv6svc_DiscardAddresses(kind) : ProcedureReturn rc
 EndIf
 If rc<>0 : ProcedureReturn rc : EndIf
 For i=0 To #IPV6_SERVICE_ADDRESSES-1
  slot=kind*#IPV6_SERVICE_ADDRESSES+i
  If ipv6svcOwnerUsed[slot]<>0
   rc=IPv6AddressOwnerInput(@ipv6svcOwner[slot],ipv6svcOwner[slot]\generation,now,frame,bytes,out,capacity)
   If rc<>0 : ProcedureReturn rc : EndIf
  EndIf
 Next
 ProcedureReturn 0
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
  ipv6svc_DiscardAddresses(kind)
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
  rc=IPv6PrefixListInit(@ipv6svcOnLink[kind],ipv6svcEpoch[kind],@ipv6svcOnLinkRows[kind*#IPV6_SERVICE_PREFIXES],#IPV6_SERVICE_PREFIXES,now)
  ipv6svc_DiscardAddresses(kind) : ipv6svcAddressError[kind]=0
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
 If ipv6svcState[kind]=2
  ipv6svc_AddressTick(kind,now)
  ipv6svc_NeighborTick(kind,now)
  ipv6svc_EchoTick(kind,now)
  ipv6svc_DiscoveryTick(kind,now)
 ElseIf ipv6svcState[kind]<0
  ipv6svc_DiscardAddresses(kind)
 EndIf
 ipv6svcBusy=0
EndProcedure
Procedure.i IPv6ServiceAddressStatus(kind.i,index.i)
 Define slot.i
 If kind<1 Or kind>=#NET_IF_KINDS Or index<0 Or index>=#IPV6_SERVICE_ADDRESSES : ProcedureReturn -800 : EndIf
 If ipv6svcState[kind]<>2 Or ipv6svcHost[kind]\phase<>#IPV6_HOST_READY : ProcedureReturn 0 : EndIf
 slot=kind*#IPV6_SERVICE_ADDRESSES+index
 If ipv6svcOwnerUsed[slot]=0 : ProcedureReturn 0 : EndIf
 ProcedureReturn IPv6AddressOwnerStatus(@ipv6svcOwner[slot],ipv6svcOwner[slot]\generation,ipv6svc_Now())
EndProcedure
Procedure.i IPv6ServiceBind(generation.i,prepare.i)
 If generation=0 Or prepare=0 Or ipv6svcGeneration<>0 : ProcedureReturn -800 : EndIf
 ipv6svcGeneration=generation : ipv6svcPrepare=prepare
 NetSetIPv6InputHook(@IPv6ServiceInput)
 NetSetTcp6Hooks(@IPv6ServiceSourceValid,@IPv6ServiceResolve)
 NetSetTcp6SelectHook(@IPv6ServiceSelect)
 NetSetProtocolTickHook(@IPv6ServiceTick)
 ProcedureReturn 0
EndProcedure

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
Procedure.i IPv6ServiceInput(kind.i,frame.i,bytes.i,out.i,capacity.i)
 Define query.IPv6MldQueryView
 Define delay.i,rc.i,now.i
 If kind<1 Or kind>=#NET_IF_KINDS : ProcedureReturn -800 : EndIf
 If ipv6svcState[kind]<>2 : ProcedureReturn 0 : EndIf
 ; Never configure filters or receive another frame while this RX span lives.
 now=ipv6svc_Now() : delay=0
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
 ipv6svcBusy=0
EndProcedure
Procedure.i IPv6ServiceBind(generation.i,prepare.i)
 If generation=0 Or prepare=0 Or ipv6svcGeneration<>0 : ProcedureReturn -800 : EndIf
 ipv6svcGeneration=generation : ipv6svcPrepare=prepare
 NetSetIPv6InputHook(@IPv6ServiceInput)
 NetSetProtocolTickHook(@IPv6ServiceTick)
 ProcedureReturn 0
EndProcedure

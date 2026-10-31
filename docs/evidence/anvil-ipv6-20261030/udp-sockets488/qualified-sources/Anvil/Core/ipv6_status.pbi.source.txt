; Optional status renderer for the shared resident IPv6 service.
Procedure IPv6ServiceSay()
 Define kind.i,n.i,phase.i,state.i,error.i,i.i,slot.i,addressState.i
 Define now.i
 Define *dns.IPv6RdnssEntry
 Define *row.IPv6DefaultRouter
 Define Dim text.a[48]
 now=ipv6svcClock
 For kind=1 To #NET_IF_KINDS-1
  state=ipv6svcState[kind]
  If state<>0
   phase=ipv6svcHost[kind]\phase : error=ipv6svcError[kind]
   n=IPv6AddressFormat(@ipv6svcAddresses[kind*16],@text[0],48)
   Print("IPv6 on ") : UartWriteStr(HwLinkName(kind)) : Print(": ")
   If n>0 : UartWriteStr(@text[0]) : Print("  ") : EndIf
   If state<0
    Print("failed, code ") : PrintDec(error)
   ElseIf state=1
    Print("configuring multicast reception")
   ElseIf phase=#IPV6_HOST_JOINING
    Print("joining multicast membership")
   ElseIf phase=#IPV6_HOST_DAD
    Print("checking duplicate address")
   ElseIf phase=#IPV6_HOST_READY
    Print("link-local ready")
   ElseIf phase=#IPV6_HOST_DUPLICATE
    Print("duplicate address; inactive")
   Else
    Print("inactive")
   EndIf
   PrintNl()
   Print("  router advertisements ") : PrintDec(ipv6svcRaCount[kind])
   Print(", last error ") : PrintDec(ipv6svcRaError[kind])
   Print(", solicitations sent ") : PrintDec(ipv6svcRsSent[kind])
   Print(", solicitation error ") : PrintDec(ipv6svcRsError[kind]) : PrintNl()
   For i=0 To 3
    *row=@ipv6svcRouterRows[kind*128+i*32]
    If *row\until>ipv6svcClock
     n=IPv6AddressFormat(@*row\address,@text[0],48)
     Print("  default router ") : UartWriteStr(@text[0])
     Print("  remaining ms ") : PrintDec(*row\until-ipv6svcClock) : PrintNl()
    EndIf
   Next
   If NetIfDns(kind)<>0
    Print("  DHCP IPv4 DNS ") : PutIp(NetIfDns(kind)) : PrintNl()
   EndIf
   Print("  RDNSS decode/storage result ") : PrintDec(ipv6svcDnsError[kind]) : PrintNl()
   For i=0 To ipv6svcDns[kind]\count-1
    *dns=@ipv6svcDnsRows[kind*#IPV6_SERVICE_DNS+i]
    If ipv6svcDns[kind]\generation=ipv6svcEpoch[kind] And *dns\until>now
     n=IPv6AddressFormat(@*dns\address,@text[0],48)
     Print("  advertised DNS ") : UartWriteStr(@text[0])
     Print("  generation ") : PrintDec(ipv6svcDns[kind]\generation)
     If *dns\until=$7FFFFFFFFFFFFFFF
      PrintN("  lifetime infinite")
     Else
      Print("  remaining ms ") : PrintDec(*dns\until-now) : PrintNl()
     EndIf
    EndIf
   Next
   If ipv6svcRaCount[kind]>0
    Print("  latest advertised prefixes ") : PrintDec(ipv6svcRa[kind]\prefixCount)
    Print(", address error ") : PrintDec(ipv6svcAddressError[kind]) : PrintNl()
    For i=0 To #IPV6_SERVICE_ADDRESSES-1
     slot=kind*#IPV6_SERVICE_ADDRESSES+i
     If ipv6svcOwnerUsed[slot]<>0 And phase=#IPV6_HOST_READY And state=2
      addressState=IPv6ServiceAddressStatus(kind,i)
      n=IPv6AddressFormat(@ipv6svcOwner[slot]\lifetime\address,@text[0],48)
      Print("  address ") : UartWriteStr(@text[0]) : Print("  ")
      Select addressState
       Case 0 : Print("expired")
       Case 1 : Print("tentative")
       Case 2 : Print("preferred")
       Case 3 : Print("deprecated")
       Case 4 : Print("duplicate")
       Default : Print("failed")
      EndSelect
      PrintNl()
     EndIf
    Next
   EndIf
  EndIf
 Next
 If dnsTrace\sequence>0
  Print("Last network DNS query ") : PrintDec(dnsTrace\sequence)
  Print(" on ") : UartWriteStr(HwLinkName(dnsTrace\kind)) : Print(": ")
  Select dnsTrace\origin
   Case 1 : Print("configured IPv4")
   Case 2 : Print("DHCP IPv4")
   Case 3 : Print("configured IPv6")
   Case 4 : Print("router-advertised IPv6")
  EndSelect
  Print(" resolver ")
  If dnsTrace\family=6
   n=IPv6AddressFormat(@dnsTrace\server6,@text[0],48) : UartWriteStr(@text[0])
  Else
   PutIp(dnsTrace\server4)
  EndIf
  Print("  query type ") : PrintDec(dnsTrace\qtype)
  Print("  result ") : PrintDec(dnsTrace\result) : PrintNl()
  PrintN("  Result 0: matching answer accepted; -110: pending; other negatives: failure or cancellation.")
 EndIf
EndProcedure

; Diagnostic uses explicit source and destination; no DNS or source-selection
; claim is implied. The resident protocol tick owns all network progress.
Procedure IPv6ServiceCommand()
 Define action.i,source.i,destination.i,n.i,rc.i,i.i,kind.i,slot.i
 Define from.IPv6AddressStorage,to.IPv6AddressStorage
 Define Dim text.a[48]
 action=ArgWord()
 If action<>0
  If StrLenZ(action)=4
   If PeekA(action)=112 And PeekA(action+1)=105 And PeekA(action+2)=110 And PeekA(action+3)=103 And PeekA(action+4)=0
   source=ArgWord() : destination=ArgWord()
   If source=0 Or destination=0
    PrintN("net ipv6 ping <assigned-source> <destination>") : ProcedureReturn
   EndIf
   n=0 : While PeekA(source+n)<>0 And n<46 : n=n+1 : Wend
   rc=IPv6AddressParse(source,n,@from)
   If rc=0
    n=0 : While PeekA(destination+n)<>0 And n<46 : n=n+1 : Wend
    rc=IPv6AddressParse(destination,n,@to)
   EndIf
   If rc=0 : rc=IPv6ServiceEchoStart(@from,@to) : EndIf
   If rc=0
    PrintN("IPv6 echo queued; use net ipv6 for its result. The console remains available.")
   Else
    Print("IPv6 echo refused, code ") : PrintDec(rc) : PrintNl()
   EndIf
   ProcedureReturn
  EndIf
  EndIf
  PrintN("net ipv6  - address/cache and last echo status")
  PrintN("net ipv6 ping <assigned-source> <destination>  - one asynchronous echo")
  ProcedureReturn
 EndIf
 IPv6ServiceSay()
 For kind=1 To #NET_IF_KINDS-1
  For i=0 To #IPV6_SERVICE_NEIGHBORS-1
   slot=kind*#IPV6_SERVICE_NEIGHBORS+i
   If ipv6svcNeighborUsed[slot]<>0
    n=IPv6AddressFormat(@ipv6svcNeighbor[slot]\target,@text[0],48)
    Print("  neighbor ") : UartWriteStr(@text[0]) : Print(" state ") : PrintDec(ipv6svcNeighbor[slot]\policy\state)
    Print(" probes ") : PrintDec(ipv6svcNeighbor[slot]\policy\probes) : PrintNl()
   EndIf
  Next
 Next
 Print("IPv6 echo state ") : PrintDec(ipv6svcEchoState) : Print(", elapsed ms ") : PrintDec(ipv6svcEchoElapsed)
 Print(", job ") : PrintDec(ipv6svcEchoSerial) : PrintNl()
 PrintN("  0 idle, 1 resolving, 2 queued, 3 awaiting reply, 4 reply verified; negative is failure.")
EndProcedure

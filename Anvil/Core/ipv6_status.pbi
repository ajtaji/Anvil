; Optional status renderer for the shared resident IPv6 service.
Procedure IPv6ServiceSay()
 Define kind.i,n.i,phase.i,state.i,error.i,i.i
 Define *row.IPv6DefaultRouter
 Define Dim text.a[48]
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
   If ipv6svcRaCount[kind]>0
    Print("  latest advertised prefixes ") : PrintDec(ipv6svcRa[kind]\prefixCount)
    Print("; address configuration pending") : PrintNl()
   EndIf
  EndIf
 Next
EndProcedure

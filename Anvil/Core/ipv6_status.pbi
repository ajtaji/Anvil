; Optional status renderer for the shared resident IPv6 service.
Procedure IPv6ServiceSay()
 Define kind.i,n.i,phase.i,state.i,error.i
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
  EndIf
 Next
EndProcedure

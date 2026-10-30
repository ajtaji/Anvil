XIncludeFile "Anvil/Network/ipv6_address.pbi"
; One resolver selection policy for console, payload and time-service DNS.
; An explicit setting belongs only to the interface that routes to it.
; Never silently use a different resolver for an invalid/unreachable override.
; Removing net.dns restores the resolver supplied by each interface's lease.
Procedure.i NetDnsResolverFor(kind.i)
 Define text.i,ip.i
 If kind<=0 : ProcedureReturn 0 : EndIf
 text=SettingsGet(EthKeyDns())
 If text<>0
  ip=ParseDotted(text)
  If ip<=0 Or ip=$FFFFFFFF : ProcedureReturn 0 : EndIf
  If NetIfForDest(ip)<>kind : ProcedureReturn 0 : EndIf
  ProcedureReturn ip
 EndIf
 ProcedureReturn NetIfDns(kind)
EndProcedure

; Explicit IPv6 DNS resolver, used by the shared asynchronous payload owner.
; 0 unset, 16 copied, -1 invalid; output is unchanged on refusal.
; TCP is a first-choice DNS transport (RFC 7766 section 5). IPv4 policy
; remains separate so time synchronization can keep its current resolver.
Procedure.i NetDnsResolver6(destination.i)
 Define text.i,n.i,i.i,nonzero.i
 Define address.IPv6AddressStorage
 text=SettingsGet("net.dns6")
 If text=0 : ProcedureReturn 0 : EndIf
 If destination=0 : ProcedureReturn -1 : EndIf
 n=0
 While n<=45
  If PeekA(text+n)=0 : Break : EndIf
  n=n+1
 Wend
 If IPv6AddressParse(text,n,@address)<>0 : ProcedureReturn -1 : EndIf
 If PeekA(@address)=255 : ProcedureReturn -1 : EndIf
 nonzero=0
 For i=0 To 15 : nonzero=nonzero|PeekA(@address+i) : Next
 If nonzero=0 : ProcedureReturn -1 : EndIf
 For i=0 To 15 : PokeA(destination+i,PeekA(@address+i)) : Next
 ProcedureReturn 16
EndProcedure

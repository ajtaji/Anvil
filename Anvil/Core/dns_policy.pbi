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

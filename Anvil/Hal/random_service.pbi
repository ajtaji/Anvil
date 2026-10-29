; SPDX-License-Identifier: MIT
; Core0-only resident entropy provider. Registration is kernel-owned.
; Return vocabulary matches ABI errors; no dependency on a board or network.
#RANDOM_SERVICE_MAX = 4096
Global *randomSvcReadyFn,*randomSvcGenerateFn
Global randomServiceBusy.i
Procedure.i RandomServiceBind(ready.i,generate.i)
  If ready<=0 Or generate<=0 : ProcedureReturn -102 : EndIf
  If randomSvcReadyFn<>0 Or randomServiceBusy<>0 : ProcedureReturn -103 : EndIf
  randomSvcReadyFn=ready : randomSvcGenerateFn=generate
  ProcedureReturn 0
EndProcedure
Procedure.i RandomServiceReady()
  Define rc.i
  If randomSvcReadyFn=0 : ProcedureReturn -101 : EndIf
  If randomServiceBusy<>0 : ProcedureReturn -103 : EndIf
  randomServiceBusy=1 : rc=randomSvcReadyFn() : randomServiceBusy=0
  If rc=0 Or rc=1 : ProcedureReturn rc : EndIf
  ProcedureReturn -105
EndProcedure
Procedure.i RandomServiceBytes(dst.i,n.i)
  Define rc.i,i.i
  If dst<=0 Or n<1 Or n>#RANDOM_SERVICE_MAX : ProcedureReturn -102 : EndIf
  If randomSvcGenerateFn=0 : ProcedureReturn -101 : EndIf
  If randomServiceBusy<>0 : ProcedureReturn -103 : EndIf
  randomServiceBusy=1
  rc=randomSvcReadyFn()
  If rc=1
    rc=randomSvcGenerateFn(dst,n)
    If rc<>n : rc=-105 : EndIf
  ElseIf rc=0
    rc=-110
  Else
    rc=-105
  EndIf
  If rc<0
    For i=0 To n-1 : PokeA(dst+i,0) : Next
  EndIf
  randomServiceBusy=0 : ProcedureReturn rc
EndProcedure

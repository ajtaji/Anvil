; SPDX-License-Identifier: MIT
; Resident graphics registration and payload scope, no hardware or renderer.
; Include neon_service_api.pbi first. A failed leave latches ownership; a later
; enter cannot silently discard it. Recover is an explicit kernel operation.
Procedure.i gsrUnbound(op.i,context.i,request.i,bytes.i)
  ProcedureReturn #NEON_SERVICE_ERR_UNBOUND
EndProcedure
Procedure.i gsrResetUnbound()
  ProcedureReturn 0
EndProcedure
Global gsrDispatch.i=@gsrUnbound,gsrReset.i=@gsrResetUnbound
Global gsrBound.i,gsrScope.i,gsrBusy.i,gsrFailure.i

Procedure.i GraphicsServiceBind(dispatch.i,reset.i)
  If dispatch=0 Or reset=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
  If gsrBound<>0 Or gsrScope<>0 Or gsrBusy<>0 : ProcedureReturn #NEON_SERVICE_ERR_BUSY : EndIf
  gsrDispatch=dispatch : gsrReset=reset : gsrBound=1
  ProcedureReturn 0
EndProcedure
Procedure.i GraphicsServiceAvailable()
  ProcedureReturn gsrBound
EndProcedure
Procedure.i GraphicsServiceState()
  ProcedureReturn gsrScope
EndProcedure
Procedure.i GraphicsServiceCall(op.i,context.i,request.i,bytes.i)
  Protected rc.i
  If gsrBusy<>0 : ProcedureReturn #NEON_SERVICE_ERR_BUSY : EndIf
  If op<>#NEON_SERVICE_QUERY And gsrScope<>1 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
  gsrBusy=1 : rc=gsrDispatch(op,context,request,bytes) : gsrBusy=0
  ProcedureReturn rc
EndProcedure
Procedure.i GraphicsServiceEnter()
  If gsrBusy<>0 Or gsrScope=1 : ProcedureReturn #NEON_SERVICE_ERR_BUSY : EndIf
  If gsrScope=2 : ProcedureReturn gsrFailure : EndIf
  gsrFailure=0 : gsrScope=1 : ProcedureReturn 0
EndProcedure
Procedure.i GraphicsServiceLeave()
  Protected rc.i
  If gsrBusy<>0 : ProcedureReturn #NEON_SERVICE_ERR_BUSY : EndIf
  If gsrScope=0 : ProcedureReturn 0 : EndIf
  If gsrScope=2 : ProcedureReturn gsrFailure : EndIf
  gsrBusy=1 : rc=gsrReset() : gsrBusy=0
  If rc>0 : rc=#NEON_SERVICE_ERR_PROVIDER : EndIf
  If rc=0
    gsrScope=0 : gsrFailure=0
  Else
    gsrScope=2 : gsrFailure=rc
  EndIf
  ProcedureReturn rc
EndProcedure
Procedure.i GraphicsServiceRecover()
  Protected rc.i
  If gsrBusy<>0 Or gsrScope=1 : ProcedureReturn #NEON_SERVICE_ERR_BUSY : EndIf
  If gsrScope=0 : ProcedureReturn 0 : EndIf
  gsrBusy=1 : rc=gsrReset() : gsrBusy=0
  If rc>0 : rc=#NEON_SERVICE_ERR_PROVIDER : EndIf
  If rc=0 : gsrScope=0 : gsrFailure=0 : Else : gsrFailure=rc : EndIf
  ProcedureReturn rc
EndProcedure

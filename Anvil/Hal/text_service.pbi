; SPDX-License-Identifier: MIT
; One registered text provider and one payload scope, independent of any ISA.
XIncludeFile "Anvil/Hal/text_service_api.pbi"
Procedure.i ntsUnbound(op.i,context.i,request.i,bytes.i)
 ProcedureReturn #NTX_ERR_UNBOUND
EndProcedure
Procedure.i ntsResetUnbound()
 ProcedureReturn 0
EndProcedure
Global ntsDispatch.i=@ntsUnbound,ntsReset.i=@ntsResetUnbound
Global ntsBound.i,ntsScope.i,ntsBusy.i,ntsFailure.i,ntsContext.i
Procedure.i TextServiceAvailable()
 ProcedureReturn ntsBound
EndProcedure
Procedure.i TextServiceBind(dispatch.i,reset.i)
 If dispatch<=0 Or reset<=0 : ProcedureReturn #NTX_ERR_ARGS : EndIf
 If ntsBound<>0 Or ntsScope<>0 Or ntsBusy<>0 : ProcedureReturn #NTX_ERR_BUSY : EndIf
 ntsDispatch=dispatch : ntsReset=reset : ntsBound=1
 ProcedureReturn 0
EndProcedure
Procedure.i TextServiceEnter()
 If ntsBusy<>0 Or ntsScope=1 : ProcedureReturn #NTX_ERR_BUSY : EndIf
 If ntsScope=2 : ProcedureReturn ntsFailure : EndIf
 ntsContext=0 : ntsScope=1 : ntsFailure=0
 ProcedureReturn 0
EndProcedure
Procedure.i TextServiceCall(op.i,context.i,request.i,bytes.i)
 Protected rc.i
 If ntsBusy<>0 : ProcedureReturn #NTX_ERR_BUSY : EndIf
 If op<#NTX_QUERY Or op>#NTX_CLOSE : ProcedureReturn #NTX_ERR_ARGS : EndIf
 If op<>#NTX_QUERY And ntsScope<>1 : ProcedureReturn #NTX_ERR_STATE : EndIf
 If op=#NTX_QUERY Or op=#NTX_OPEN
  If context<>0 : ProcedureReturn #NTX_ERR_ARGS : EndIf
  If op=#NTX_OPEN And ntsContext<>0 : ProcedureReturn #NTX_ERR_BUSY : EndIf
 Else
  If context<=0 Or context<>ntsContext : ProcedureReturn #NTX_ERR_STATE : EndIf
 EndIf
 ntsBusy=1 : rc=ntsDispatch(op,context,request,bytes) : ntsBusy=0
 If op=#NTX_OPEN
  If rc>0 : ntsContext=rc : ElseIf rc=0 : rc=#NTX_ERR_PROVIDER : EndIf
 Else
  If rc>0 : rc=#NTX_ERR_PROVIDER : EndIf
  If op=#NTX_CLOSE And rc=0 : ntsContext=0 : EndIf
 EndIf
 ProcedureReturn rc
EndProcedure
Procedure.i TextServiceLeave()
 Protected rc.i
 If ntsBusy<>0 : ProcedureReturn #NTX_ERR_BUSY : EndIf
 If ntsScope=0 : ProcedureReturn 0 : EndIf
 If ntsScope=2 : ProcedureReturn ntsFailure : EndIf
 ntsBusy=1 : rc=ntsReset() : ntsBusy=0
 If rc>0 : rc=#NTX_ERR_PROVIDER : EndIf
 If rc=0
  ntsScope=0 : ntsContext=0 : ntsFailure=0
 Else
  ntsScope=2 : ntsFailure=rc
 EndIf
 ProcedureReturn rc
EndProcedure

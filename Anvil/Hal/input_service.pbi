; SPDX-License-Identifier: MIT
; Resident input registration and payload lifetime, independent of graphics.
XIncludeFile "Anvil/Hal/input_service_api.pbi"
Procedure.i nisUnbound(op.i,context.i,request.i,bytes.i)
  ProcedureReturn #NUI_ERR_UNBOUND
EndProcedure
Procedure.i nisResetUnbound()
  ProcedureReturn 0
EndProcedure
Global nisDispatch.i=@nisUnbound,nisReset.i=@nisResetUnbound
Global nisBound.i,nisScope.i,nisBusy.i,nisFailure.i,nisContext.i
Procedure.i InputServiceAvailable()
  ProcedureReturn nisBound
EndProcedure
Procedure.i InputServiceState()
  ProcedureReturn nisScope
EndProcedure
Procedure.i InputServiceClaimed()
  ProcedureReturn Bool(nisContext>0)
EndProcedure
Procedure.i InputServiceBind(dispatch.i,reset.i)
  If dispatch<=0 Or reset<=0 : ProcedureReturn #NUI_ERR_ARGS : EndIf
  If nisBound<>0 Or nisScope<>0 Or nisBusy<>0 : ProcedureReturn #NUI_ERR_BUSY : EndIf
  nisDispatch=dispatch : nisReset=reset : nisBound=1
  ProcedureReturn 0
EndProcedure
Procedure.i InputServiceEnter()
  If nisBusy<>0 Or nisScope=1 : ProcedureReturn #NUI_ERR_BUSY : EndIf
  If nisScope=2 : ProcedureReturn nisFailure : EndIf
  nisContext=0 : nisScope=1 : nisFailure=0 : ProcedureReturn 0
EndProcedure
Procedure.i InputServiceCall(op.i,context.i,request.i,bytes.i)
  Protected rc.i
  If nisBusy<>0 : ProcedureReturn #NUI_ERR_BUSY : EndIf
  If op<#NUI_QUERY Or op>#NUI_CLOSE : ProcedureReturn #NUI_ERR_ARGS : EndIf
  If op<>#NUI_QUERY And nisScope<>1 : ProcedureReturn #NUI_ERR_STATE : EndIf
  If op=#NUI_QUERY Or op=#NUI_OPEN
    If context<>0 : ProcedureReturn #NUI_ERR_ARGS : EndIf
    If op=#NUI_OPEN And nisContext<>0 : ProcedureReturn #NUI_ERR_BUSY : EndIf
  Else
    If context<=0 Or context<>nisContext : ProcedureReturn #NUI_ERR_STATE : EndIf
  EndIf
  nisBusy=1 : rc=nisDispatch(op,context,request,bytes) : nisBusy=0
  If op=#NUI_OPEN
    If rc>0 : nisContext=rc : ElseIf rc=0 : rc=#NUI_ERR_PROVIDER : EndIf
  ElseIf op=#NUI_POLL
    If rc>1 : rc=#NUI_ERR_PROVIDER : EndIf
  Else
    If rc>0 : rc=#NUI_ERR_PROVIDER : EndIf
    If op=#NUI_CLOSE And rc=0 : nisContext=0 : EndIf
  EndIf
  ProcedureReturn rc
EndProcedure
Procedure.i InputServiceLeave()
  Protected rc.i
  If nisBusy<>0 : ProcedureReturn #NUI_ERR_BUSY : EndIf
  If nisScope=0 : ProcedureReturn 0 : EndIf
  If nisScope=2 : ProcedureReturn nisFailure : EndIf
  nisBusy=1 : rc=nisReset() : nisBusy=0
  If rc>0 : rc=#NUI_ERR_PROVIDER : EndIf
  If rc=0
    nisScope=0 : nisContext=0 : nisFailure=0
  Else
    nisScope=2 : nisFailure=rc
  EndIf
  ProcedureReturn rc
EndProcedure
Procedure.i InputServiceRecover()
  Protected rc.i
  If nisBusy<>0 Or nisScope=1 : ProcedureReturn #NUI_ERR_BUSY : EndIf
  If nisScope=0 : ProcedureReturn 0 : EndIf
  nisBusy=1 : rc=nisReset() : nisBusy=0
  If rc>0 : rc=#NUI_ERR_PROVIDER : EndIf
  If rc=0 : nisScope=0 : nisContext=0 : nisFailure=0 : Else : nisFailure=rc : EndIf
  ProcedureReturn rc
EndProcedure

; TCP scheduler/input service boundary shared by all compositions.
; Missing service: input is unhandled and the scheduler has no work.
; The TCP engine installs both callbacks only after TcpInit completes.
; Registration is serialized by the composition; callback lifetimes must
; cover every dispatch. A partial pair is rejected without changing state.
Global *gTcpServiceInput = 0
Global *gTcpServiceTick = 0

Procedure.i TcpServiceInstall(inputFn.i, tickFn.i)
  If inputFn = 0 And tickFn <> 0
    ProcedureReturn 0
  EndIf
  If inputFn <> 0 And tickFn = 0
    ProcedureReturn 0
  EndIf
  gTcpServiceInput = inputFn
  gTcpServiceTick = tickFn
  ProcedureReturn 1
EndProcedure

Procedure.i TcpServiceReady()
  If gTcpServiceInput = 0 Or gTcpServiceTick = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i TcpInput()
  If gTcpServiceInput = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn gTcpServiceInput()
EndProcedure

Procedure TcpTick()
  If gTcpServiceTick <> 0
    gTcpServiceTick()
  EndIf
EndProcedure

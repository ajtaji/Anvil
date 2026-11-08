; Service-table scope for compositions that include the real shared ABI.
; No chip or CPU register selection belongs to the container engine.
Global svcPayloadScope.i
Procedure.i HwPayloadServicesReady() : ProcedureReturn 1 : EndProcedure
Procedure.i HwPayloadServicesOpen(mayReturn.i)
 If svcPayloadScope<>0 Or (mayReturn<>0 And mayReturn<>1) : ProcedureReturn 0 : EndIf
 gSvcMayReturn=mayReturn
 BuildServiceTable() : SvcFileHReset()
 CompilerIf #CAP_NET=1
  UdpServiceCloseAll()
 CompilerEndIf
 svcPayloadScope=1
 ProcedureReturn SvcTableAddr()
EndProcedure
Procedure HwPayloadServicesClose()
 If svcPayloadScope<>0
  SvcFileHReset()
  CompilerIf #CAP_NET=1
   UdpServiceCloseAll()
  CompilerEndIf
 EndIf
 gSvcMayReturn=0 : svcPayloadScope=0
EndProcedure

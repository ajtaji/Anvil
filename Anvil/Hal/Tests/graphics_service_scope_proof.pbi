; SPDX-License-Identifier: MIT
; Controlled ownership proof. No GPU, driver, display or hardware failure.
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Hal/graphics_service.pbi"
Global gssResetN.i,gssCallN.i,gssResetResult.i,gssChecks.i,gssFailure.i
Procedure.i GssDispatch(op.i,context.i,request.i,bytes.i)
  gssCallN = gssCallN + 1
  ProcedureReturn 4242
EndProcedure
Procedure.i GssReset()
  gssResetN = gssResetN + 1
  ProcedureReturn gssResetResult
EndProcedure
Procedure GssCheck(actual.i,expected.i)
  gssChecks = gssChecks + 1
  PokeI(#GSS_REPORT + 64 + gssChecks * 16,actual)
  PokeI(#GSS_REPORT + 72 + gssChecks * 16,expected)
  If actual <> expected And gssFailure = 0 : gssFailure = gssChecks : EndIf
EndProcedure
Procedure.i Main(services.i)
  Define i.i
  For i = 0 To 4095 Step 8 : PokeI(#GSS_REPORT + i,0) : Next
  GssCheck(GraphicsServiceAvailable(),0)
  GssCheck(GraphicsServiceBind(0,@GssReset),#NEON_SERVICE_ERR_ARGS)
  GssCheck(GraphicsServiceBind(@GssDispatch,0),#NEON_SERVICE_ERR_ARGS)
  GssCheck(GraphicsServiceCall(1,0,0,0),#NEON_SERVICE_ERR_STATE)
  GssCheck(GraphicsServiceCall(0,0,0,0),#NEON_SERVICE_ERR_UNBOUND)
  GssCheck(GraphicsServiceLeave(),0)
  GssCheck(GraphicsServiceBind(@GssDispatch,@GssReset),0)
  GssCheck(GraphicsServiceAvailable(),1)
  GssCheck(GraphicsServiceBind(@GssDispatch,@GssReset),#NEON_SERVICE_ERR_BUSY)
  GssCheck(GraphicsServiceCall(0,0,0,0),4242)
  GssCheck(GraphicsServiceCall(1,0,0,0),#NEON_SERVICE_ERR_STATE)
  GssCheck(gssCallN,1)
  GssCheck(GraphicsServiceEnter(),0)
  GssCheck(GraphicsServiceState(),1)
  GssCheck(GraphicsServiceEnter(),#NEON_SERVICE_ERR_BUSY)
  GssCheck(GraphicsServiceRecover(),#NEON_SERVICE_ERR_BUSY)
  GssCheck(GraphicsServiceCall(1,0,0,0),4242)
  gssResetResult = -77
  GssCheck(GraphicsServiceLeave(),-77)
  GssCheck(GraphicsServiceState(),2)
  GssCheck(GraphicsServiceLeave(),-77)
  GssCheck(gssResetN,1)
  GssCheck(GraphicsServiceEnter(),-77)
  GssCheck(GraphicsServiceCall(1,0,0,0),#NEON_SERVICE_ERR_STATE)
  GssCheck(gssCallN,2)
  GssCheck(GraphicsServiceRecover(),-77)
  GssCheck(gssResetN,2)
  gssResetResult = 7
  GssCheck(GraphicsServiceRecover(),#NEON_SERVICE_ERR_PROVIDER)
  GssCheck(GraphicsServiceEnter(),#NEON_SERVICE_ERR_PROVIDER)
  GssCheck(GraphicsServiceLeave(),#NEON_SERVICE_ERR_PROVIDER)
  GssCheck(gssResetN,3)
  gssResetResult = 0
  GssCheck(GraphicsServiceRecover(),0)
  GssCheck(GraphicsServiceState(),0)
  GssCheck(GraphicsServiceLeave(),0)
  GssCheck(gssResetN,4)
  GssCheck(GraphicsServiceEnter(),0)
  GssCheck(GraphicsServiceLeave(),0)
  GssCheck(gssResetN,5)
  GssCheck(GraphicsServiceState(),0)
  GssCheck(GraphicsServiceRecover(),0)
  GssCheck(gssResetN,5)
  PokeI(#GSS_REPORT,$47535331) : PokeI(#GSS_REPORT + 8,gssFailure)
  PokeI(#GSS_REPORT + 16,gssChecks) : PokeI(#GSS_REPORT + 24,gssResetN)
  PokeI(#GSS_REPORT + 32,gssCallN) : PokeI(#GSS_REPORT + 40,GraphicsServiceState())
  ProcedureReturn gssFailure
EndProcedure

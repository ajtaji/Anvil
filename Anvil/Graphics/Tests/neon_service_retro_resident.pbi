; SPDX-License-Identifier: MIT
; Resident CRT client, with no GPU implementation linked into the payload.
EnableFloatingPoint
XIncludeFile "Anvil/Math/float32.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_targets.pbi"
Global nrrCount.i,nrrFailure.i
Procedure NrrCheck(value.i,expected.i)
 PokeI($E1C00400+nrrCount*16,value) : PokeI($E1C00408+nrrCount*16,expected)
 nrrCount=nrrCount+1
 If value<>expected And nrrFailure=0 : nrrFailure=nrrCount : EndIf
 PokeI($E1C00010,nrrFailure) : PokeI($E1C00018,nrrCount)
EndProcedure
Procedure.i Main(services.i)
 Protected i.i,target.i
 For i=0 To 16383 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$4E525232) : PokeI($E1C00008,1)
 NrrCheck(NeonServiceBind(services,#NEON_SERVICE_TARGETS|#NEON_SERVICE_TARGET_RETRO),0)
 If nrrFailure<>0 : ProcedureReturn nrrFailure : EndIf
 NrrCheck(NeonServiceOpen(),0)
 If nrrFailure<>0 : ProcedureReturn nrrFailure : EndIf
 NrrCheck(NeonServiceWidth(),1280) : NrrCheck(NeonServiceHeight(),800)
 target=NeonServiceTargetCreate(64,64,0) : NrrCheck(Bool(target>0),1)
 NrrCheck(NeonServiceTargetBind(target),0)
 NrrCheck(NeonServiceBegin(0.0,0.0,0.0,1.0),0)
 NrrCheck(NeonServiceBox(0.0,0.0,64.0,64.0,0.5019608,0.5019608,0.5019608,1.0),0)
 NrrCheck(NeonServiceEnd(),0)
 NrrCheck(NeonServiceTargetUnbind(target),0)
 NrrCheck(NeonServiceTargetRetroPrepare(target),0)
 NrrCheck(NeonServiceTargetDrawRetro(target,0.125),#NEON_SERVICE_ERR_STATE)
 NrrCheck(NeonServiceBegin(0.0,0.0,0.0,1.0),0)
 NrrCheck(NeonServiceTargetRetroPrepare(target),#NEON_SERVICE_ERR_STATE)
 NrrCheck(NeonServiceTargetDrawRetro(target,0.125),0)
 NrrCheck(NeonServiceEnd(),0)
 NrrCheck(NeonServiceFrameOpen(),0)
 NrrCheck(Bool(NeonServiceContext()>0),1)
 ; Loader captures the result before retiring the resident graphics scope.
 If nrrFailure<>0 : NeonServiceClose() : EndIf
 ProcedureReturn nrrFailure
EndProcedure

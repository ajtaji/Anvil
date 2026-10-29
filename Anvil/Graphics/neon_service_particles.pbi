; SPDX-License-Identifier: MIT
; Optional pure particle service client. Prepare copies caller-owned records
; outside a frame; DrawPrepared emits them in array order inside a frame.
XIncludeFile "Anvil/Graphics/neon_particle_types.pbi"
Procedure.i NeonServiceParticleLimitsGet(*limits.NeonServiceParticleLimits)
  Protected rc.i
  If *limits=0 Or (*limits & 7)<>0 : ProcedureReturn NeonServiceExtensionStatus(#NEON_SERVICE_ERR_ARGS) : EndIf
  *limits\maxCount=0 : *limits\recordBytes=0 : *limits\coordinateFractionBits=0
  rc=NeonServiceRequestExtension(#NEON_SERVICE_PARTICLE_LIMITS,*limits,SizeOf(NeonServiceParticleLimits),-1,#NEON_SERVICE_PARTICLES,#NEON_SERVICE_PARTICLE_MINOR,0)
  If rc<>0 : ProcedureReturn NeonServiceExtensionStatus(rc) : EndIf
  If *limits\maxCount<1 Or *limits\maxCount>#NEON_SERVICE_MAX_PARTICLES Or *limits\recordBytes<>SizeOf(NeonParticleRecord) Or *limits\coordinateFractionBits<>8 : ProcedureReturn NeonServiceExtensionStatus(#NEON_SERVICE_ERR_PROVIDER) : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i NeonServiceParticlesPrepare(data.i,sourceBytes.i,count.i)
  Protected request.NeonServiceParticlePrepareRequest
  If count<0 Or count>#NEON_SERVICE_MAX_PARTICLES Or sourceBytes<count*32 : ProcedureReturn NeonServiceExtensionStatus(#NEON_SERVICE_ERR_ARGS) : EndIf
  If count>0 And (data<1 Or (data & 3)<>0) : ProcedureReturn NeonServiceExtensionStatus(#NEON_SERVICE_ERR_ARGS) : EndIf
  request\data=data : request\sourceBytes=sourceBytes : request\count=count
  ProcedureReturn NeonServiceExtensionStatus(NeonServiceRequestExtension(#NEON_SERVICE_PARTICLE_PREPARE,@request,SizeOf(NeonServiceParticlePrepareRequest),0,#NEON_SERVICE_PARTICLES,#NEON_SERVICE_PARTICLE_MINOR,0))
EndProcedure
Procedure.i NeonServiceParticlesDrawPrepared()
  ProcedureReturn NeonServiceExtensionStatus(NeonServiceRequestExtension(#NEON_SERVICE_PARTICLE_DRAW,0,0,1,#NEON_SERVICE_PARTICLES,#NEON_SERVICE_PARTICLE_MINOR,0))
EndProcedure

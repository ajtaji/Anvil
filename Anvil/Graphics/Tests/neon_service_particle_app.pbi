; SPDX-License-Identifier: MIT
; Returning pure particle application: full-capacity and fractional scenes.
EnableFloatingPoint
XIncludeFile "Anvil/Math/float32.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_sprite.pbi"
XIncludeFile "Anvil/Graphics/neon_particle_list.pbi"
XIncludeFile "Anvil/Graphics/neon_service_particles.pbi"
Global Dim nppItems.NeonParticleRecord[10000]
Global nppList.NeonParticleList,nppChecks.i,nppFailure.i
Procedure.i NppNoClock()
  ProcedureReturn -1
EndProcedure
Global nppClock.i=@NppNoClock
Procedure NppCheck(actual.i,expected.i)
  nppChecks=nppChecks+1
  PokeI(#NPP_REPORT+256+nppChecks*16,actual) : PokeI(#NPP_REPORT+264+nppChecks*16,expected)
  If actual<>expected And nppFailure=0 : nppFailure=nppChecks : EndIf
  PokeI(#NPP_REPORT+16,nppFailure) : PokeI(#NPP_REPORT+24,nppChecks)
EndProcedure
Procedure.i NppUnavailable(op.i,context.i,request.i,bytes.i)
  ProcedureReturn #NEON_SERVICE_ERR_UNBOUND
EndProcedure
; Invert the fixed mixed-scene camera so the independent host oracle works
; in screen space, without borrowing the renderer's geometry calculations.
Procedure NppScreen(x.f,y.f,size.f,angle.f,r.f,g.f,b.f,a.f)
  NppCheck(NeonParticleListAdd(@nppList,520.25+x*0.5,300.375+y*0.5,size*0.5,angle,r,g,b,a),0)
EndProcedure
Procedure.i Main(services.i)
  Protected i.i,bad.i,started.i,drawStart.i,frameStart.i,api.NeonServiceApi
  Protected limits.NeonServiceParticleLimits,request.NeonServiceParticlePrepareRequest
  For i=0 To 4095 Step 8 : PokeI(#NPP_REPORT+i,0) : Next
  PokeI(#NPP_REPORT,$4E505031) : PokeI(#NPP_REPORT+8,1)
  NppCheck(SizeOf(NeonParticleRecord),32)
  NppCheck(SizeOf(NeonServiceParticleLimits),24)
  NppCheck(SizeOf(NeonServiceParticlePrepareRequest),24)
  api\magic=#NEON_SERVICE_MAGIC : api\major=1 : api\minor=2 : api\bytes=48
  api\flags=31 : api\maxFonts=32 : api\dispatch=@NppUnavailable
  NppCheck(NeonServiceBindApi(@api,48,16),#NEON_SERVICE_ERR_ABI)
  NppCheck(NeonServiceBind(services,21),0)
  NppCheck(NeonServiceOpen(),0)
  If nppFailure<>0 : ProcedureReturn nppFailure : EndIf
  nppClock=PeekI(services+16+11*8)
  NppCheck(NeonServiceParticleLimitsGet(@limits),0)
  NppCheck(limits\maxCount,10000) : NppCheck(limits\recordBytes,32)
  NppCheck(limits\coordinateFractionBits,8)
  NppCheck(NeonParticleListConfigure(@nppList,@nppItems[0],320000,10001),#NEON_PARTICLE_ERR_ARGS)
  NppCheck(NeonParticleListConfigure(@nppList,@nppItems[0],320000,10000),0)
  NppCheck(NeonParticleListAdd(@nppList,1.0,2.0,0.0,0.0,1.0,0.0,0.0,1.0),#NEON_PARTICLE_ERR_ARGS)
  NppCheck(nppList\count,0)
  NppCheck(NeonServiceBegin(0.0,0.0,0.0,1.0),0)
  NppCheck(NeonServiceParticlesDrawPrepared(),#NEON_SERVICE_ERR_STATE)
  NppCheck(NeonServiceAbort(),0)
  NppCheck(NeonServiceParticlesPrepare(0,0,0),0)
  NppCheck(NeonServiceBegin(0.0,0.0,0.0,1.0),0)
  NppCheck(NeonServiceParticlesDrawPrepared(),0)
  NppCheck(NeonServiceEnd(),0)
  request\data=$FE000000 : request\sourceBytes=32 : request\count=1
  NppCheck(NeonServiceRequestExtension(#NEON_SERVICE_PARTICLE_PREPARE,@request,24,0,16,3,0),#NEON_SERVICE_ERR_ARGS)
  NppCheck(NeonServiceParticlesPrepare(@nppItems[0],31,1),#NEON_SERVICE_ERR_ARGS)
  PokeL(@nppItems[0],$7FC00001)
  NppCheck(NeonServiceParticlesPrepare(@nppItems[0],32,1),-21201)
  NppCheck(NeonServiceCamera(0.0,0.0,1.0),0)
  started=nppClock()
  For i=0 To 9999
    If NeonParticleListAdd(@nppList,MathFFromInt(100+(i % 100)*10)+0.375,MathFFromInt(100+(i/100)*5)+0.625,2.75,0.0,1.0,0.0,0.0,1.0)<>0 : bad=bad+1 : EndIf
  Next
  PokeI(#NPP_REPORT+64,nppClock()-started)
  NppCheck(bad,0) : NppCheck(nppList\count,10000)
  NppCheck(NeonParticleListAdd(@nppList,1.0,2.0,1.0,0.0,1.0,0.0,0.0,1.0),#NEON_PARTICLE_ERR_CAPACITY)
  started=nppClock()
  NppCheck(NeonServiceParticlesPrepare(nppList\data,nppList\bytes,nppList\count),0)
  PokeI(#NPP_REPORT+72,nppClock()-started)
  started=nppClock()
  NppCheck(NeonServiceParticlesPrepare(nppList\data,nppList\bytes,nppList\count),0)
  PokeI(#NPP_REPORT+104,nppClock()-started)
  For i=0 To 319999 : PokeA(@nppItems[0]+i,0) : Next
  NppCheck(NeonServiceCamera(1.0,0.0,1.0),0)
  NppCheck(NeonServiceBegin(0.0,0.0,0.0,1.0),0)
  NppCheck(NeonServiceParticlesDrawPrepared(),#NEON_SERVICE_ERR_STATE)
  NppCheck(NeonServiceAbort(),0)
  NppCheck(NeonServiceCamera(0.0,0.0,1.0),0)
  frameStart=nppClock()
  NppCheck(NeonServiceBegin(0.0,0.0,0.0,1.0),0)
  NppCheck(NeonServiceParticlesPrepare(0,0,0),#NEON_SERVICE_ERR_STATE)
  drawStart=nppClock()
  NppCheck(NeonServiceParticlesDrawPrepared(),0)
  PokeI(#NPP_REPORT+80,nppClock()-drawStart)
  NppCheck(NeonServiceEnd(),0)
  PokeI(#NPP_REPORT+88,nppClock()-frameStart)
  CompilerIf #NPP_DENSE=1
    PokeI(#NPP_REPORT+32,1)
    ProcedureReturn nppFailure
  CompilerEndIf
  NppCheck(NeonServiceClose(),0) : NppCheck(NeonServiceOpen(),0)
  NppCheck(NeonParticleListClear(@nppList),0)
  NppCheck(NeonServiceCamera(200.25,100.375,2.0),0)
  NppScreen(100.25,100.75,46.5,0.0,1.0,0.0,0.0,1.0)
  NppScreen(250.5,100.25,63.5,0.4,0.0,1.0,0.0,1.0)
  NppScreen(400.25,100.75,80.0,0.0,0.0,0.0,1.0,1.0)
  NppScreen(410.75,110.25,70.5,0.0,1.0,0.0,0.0,0.5)
  NppScreen(540.5,120.5,0.001,0.0,1.0,1.0,0.0,1.0)
  NppScreen(1200.25,760.75,100.5,0.55,0.0,1.0,1.0,1.0)
  NppScreen(600.0,350.0,160.0,0.125,1.0,1.0,0.0,0.75)
  NppScreen(640.0,340.0,100.0,-0.7,1.0,0.0,1.0,0.5)
  NppScreen(-15.25,200.0,80.0,-0.4,0.0,1.0,1.0,1.0)
  NppScreen(1100.0,100.0,12.25,1.57079632679,1.0,1.0,1.0,1.0)
  NppCheck(nppList\count,10)
  started=nppClock()
  NppCheck(NeonServiceParticlesPrepare(nppList\data,nppList\bytes,nppList\count),0)
  PokeI(#NPP_REPORT+96,nppClock()-started)
  For i=0 To 319999 : PokeA(@nppItems[0]+i,0) : Next
  NppCheck(NeonServiceBegin(0.0,0.0,0.0,1.0),0)
  NppCheck(NeonServiceParticlesDrawPrepared(),0)
  NppCheck(NeonServiceEnd(),0)
  PokeI(#NPP_REPORT+32,2)
  ProcedureReturn nppFailure
EndProcedure

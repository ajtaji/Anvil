; SPDX-License-Identifier: MIT
; Public-client qualification of resident offscreen targets, without GPU imports.
EnableFloatingPoint
XIncludeFile "Anvil/Math/float32.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_mapping.pbi"
XIncludeFile "Anvil/Graphics/neon_service_sprite.pbi"
XIncludeFile "Anvil/Graphics/neon_service_particles.pbi"
XIncludeFile "Anvil/Graphics/neon_service_targets.pbi"
Global nstpReport.i,nstpCount.i,nstpFailure.i,nstpMockCalls.i
Global Dim nstpHandles.i[16]
Global nstpParticle.NeonParticleRecord
Procedure.i NstpMock(op.i,context.i,request.i,bytes.i)
  nstpMockCalls=nstpMockCalls+1
  ProcedureReturn #NEON_SERVICE_ERR_PROVIDER
EndProcedure
Procedure NstpCheck(id.i,actual.i,wanted.i)
  If nstpCount>=400 : nstpFailure=9999 : ProcedureReturn : EndIf
  PokeI(nstpReport+256+nstpCount*24,id)
  PokeI(nstpReport+264+nstpCount*24,actual)
  PokeI(nstpReport+272+nstpCount*24,wanted)
  nstpCount=nstpCount+1
  If actual<>wanted And nstpFailure=0 : nstpFailure=id : EndIf
  PokeI(nstpReport+8,nstpFailure) : PokeI(nstpReport+16,nstpCount)
EndProcedure
Procedure.i NstpDraw(handle.i,x.f,y.f,w.f,h.f,scaled.i)
  ProcedureReturn NeonServiceTargetDraw(handle,x,y,0.0,1.0,1.0,1.0,1.0,1.0,scaled,0.0,0.0,w,h,0)
EndProcedure
Procedure.i NeonServiceTargetContinuationProof(services.i,report.i)
  Protected api.NeonServiceApi,limits.NeonServiceTargetLimits,i.i,old.i,a.i,b.i,c.i,d.i,pixel.l=$FFFFFFFF,nan.f
  If report=0 Or (report & 7)<>0 : ProcedureReturn 9998 : EndIf
  nstpReport=report : nstpCount=0 : nstpFailure=0 : nstpMockCalls=0
  PokeI(report,$4E535431)
  api\magic=#NEON_SERVICE_MAGIC : api\major=1 : api\minor=8
  api\bytes=SizeOf(NeonServiceApi) : api\flags=#NEON_SERVICE_TARGETS
  api\maxFonts=16 : api\dispatch=@NstpMock
  NstpCheck(1,NeonServiceBindApi(@api,SizeOf(NeonServiceApi),#NEON_SERVICE_TARGETS),#NEON_SERVICE_ERR_ABI)
  api\minor=9 : api\flags=0
  NstpCheck(2,NeonServiceBindApi(@api,SizeOf(NeonServiceApi),#NEON_SERVICE_TARGETS),#NEON_SERVICE_ERR_PROVIDER)
  NstpCheck(3,nstpMockCalls,0)
  api\minor=9 : api\flags=#NEON_SERVICE_TARGETS | #NEON_SERVICE_TARGET_CONTINUATION
  NstpCheck(198,NeonServiceBindApi(@api,SizeOf(NeonServiceApi),#NEON_SERVICE_TARGET_CONTINUATION),#NEON_SERVICE_ERR_ABI)
  api\minor=10 : api\flags=#NEON_SERVICE_TARGET_CONTINUATION
  NstpCheck(199,NeonServiceBindApi(@api,SizeOf(NeonServiceApi),#NEON_SERVICE_TARGET_CONTINUATION),#NEON_SERVICE_ERR_ABI)
  NstpCheck(4,NeonServiceBind(services,#NEON_SERVICE_TARGET_CONTINUATION|#NEON_SERVICE_TARGETS|#NEON_SERVICE_MAPPING|#NEON_SERVICE_PARTICLES|#NEON_SERVICE_SPRITES|#NEON_SERVICE_FONT_REFS),0)
  If nstpFailure=0 : NstpCheck(5,NeonServiceOpen(),0) : EndIf
  If nstpFailure=0
    NstpCheck(6,NeonServiceWidth(),1280) : NstpCheck(7,NeonServiceHeight(),800)
    NstpCheck(8,NeonServiceTargetLimitsGet(@limits),0)
    NstpCheck(9,limits\slots,16) : NstpCheck(10,limits\maxDimension,2048)
    NstpCheck(11,NeonServiceTargetCreate(0,8,0),0) : NstpCheck(12,NeonServiceError(),#NEON_SERVICE_ERR_ARGS)
    For i=0 To 15
      nstpHandles[i]=NeonServiceTargetCreate(8,8,i & 1)
      NstpCheck(100+i,Bool(nstpHandles[i]>0),1)
    Next
    NstpCheck(13,NeonServiceTargetCreate(8,8,0),0) : NstpCheck(14,NeonServiceError(),#NEON_SERVICE_ERR_CAPACITY)
    NstpCheck(15,NeonServiceSpriteUpload(1,@pixel,4,1,1,0),0) : NstpCheck(16,NeonServiceError(),#NEON_SERVICE_ERR_BUSY)
    old=nstpHandles[15]
    NstpCheck(200,NeonServiceBegin(0.0,0.0,0.0,1.0),0)
    NstpCheck(201,NeonServiceBox(30.0,30.0,40.0,40.0,1.0,0.0,0.0,1.0),0)
    NstpCheck(17,NeonServiceTargetBind(old),0)
    NstpCheck(202,NeonServiceFrameOpen(),0)
    NstpCheck(18,NeonServiceWidth(),8) : NstpCheck(19,NeonServiceHeight(),8)
    NstpCheck(20,NeonServiceTargetFree(nstpHandles[0]),#NEON_SERVICE_ERR_STATE)
    NstpCheck(21,NeonServiceClose(),0)
    NstpCheck(22,NeonServiceContext(),0) : NstpCheck(23,NeonServiceReady(),0)
  EndIf
  If nstpFailure=0
    NstpCheck(230,NeonServiceOpen(),0)
    d=NeonServiceTargetCreate(8,8,0) : NstpCheck(231,Bool(d>old),1)
    NstpCheck(232,NeonServiceBegin(0.0,0.0,0.0,1.0),0)
    NstpCheck(233,NeonServiceBox(10.0,10.0,20.0,20.0,1.0,0.0,0.0,1.0),0)
    NstpCheck(234,NeonServiceClose(),0)
    NstpCheck(235,NeonServiceContext(),0)
    NstpCheck(236,NeonServiceReady(),0)
    NstpCheck(237,NeonServiceFrameOpen(),0)
  EndIf
  If nstpFailure=0 : NstpCheck(24,NeonServiceOpen(),0) : EndIf
  If nstpFailure=0
    NstpCheck(25,NeonServicePrepare(0,"Target"),0)
    a=NeonServiceTargetCreate(160,100,1) : NstpCheck(26,Bool(a>old),1)
    NstpCheck(27,NeonServiceTargetFree(old),#NEON_SERVICE_ERR_STALE)
    b=NeonServiceTargetCreate(96,64,0) : NstpCheck(28,Bool(b>a),1)
    NstpCheck(29,NeonServiceCanvas(640,400),0) : NstpCheck(30,NeonServiceCamera(10.0,20.0,1.0),0)
    NstpCheck(31,NeonServiceBegin(0.0,0.0,0.0,1.0),0)
    NstpCheck(32,NstpDraw(a,40.0,40.0,160.0,100.0,1),#NEON_SERVICE_ERR_STATE)
    NstpCheck(33,NeonServiceAbort(),0)
    NstpCheck(34,NeonServiceTargetBind(a),0)
    NstpCheck(35,NeonServiceWidth(),160) : NstpCheck(36,NeonServiceHeight(),100)
    NstpCheck(37,NeonServicePrepare(0,"Target"),0)
    nstpParticle\x=80.0 : nstpParticle\y=50.0 : nstpParticle\size=12.0 : nstpParticle\angle=0.0
    nstpParticle\r=1.0 : nstpParticle\g=1.0 : nstpParticle\b=0.0 : nstpParticle\a=1.0
    NstpCheck(38,NeonServiceParticlesPrepare(@nstpParticle,32,1),0)
    NstpCheck(39,NeonServiceBegin(0.0,0.0,1.0,1.0),0)
    NstpCheck(40,NeonServiceBox(0.0,0.0,80.0,100.0,1.0,0.0,0.0,1.0),0)
    NstpCheck(41,NeonServiceParticlesDrawPrepared(),0)
    NstpCheck(42,NeonServiceText(0,4.0,75.0,"Target",1.0,1.0,1.0,1.0),0)
    NstpCheck(43,NeonServiceEnd(),0) : NstpCheck(44,NeonServiceFrameOpen(),0)
    NstpCheck(45,NeonServiceCamera(0.0,0.0,1.0),0)
    NstpCheck(46,NeonServiceBegin(0.0,1.0,0.0,1.0),0)
    NstpCheck(47,NeonServiceBox(0.0,0.0,160.0,100.0,0.0,1.0,0.0,1.0),0)
    NstpCheck(48,NeonServiceAbort(),0) : NstpCheck(49,NeonServiceTargetUnbind(a),0)
    NstpCheck(50,NeonServiceWidth(),1280) : NstpCheck(51,NeonServiceHeight(),800)
    NstpCheck(52,NeonServiceTargetResize(b,0,80),#NEON_SERVICE_ERR_ARGS)
    NstpCheck(53,NeonServiceTargetBind(b),0)
    NstpCheck(54,NeonServiceWidth(),96) : NstpCheck(55,NeonServiceHeight(),64)
    NstpCheck(56,NeonServiceTargetUnbind(b),0)
    NstpCheck(57,NeonServiceTargetResize(b,120,80),0) : NstpCheck(58,NeonServiceTargetBind(b),0)
    NstpCheck(59,NeonServiceWidth(),120) : NstpCheck(60,NeonServiceHeight(),80)
    NstpCheck(61,NeonServiceBegin(0.0,1.0,0.0,1.0),0)
    NstpCheck(62,NeonServiceBox(1.0,0.0,1.0,2.0,0.0,0.0,1.0,1.0),0)
    NstpCheck(63,NeonServiceEnd(),0) : NstpCheck(64,NeonServiceTargetUnbind(b),0)
    c=NeonServiceTargetCreate(320,200,1) : NstpCheck(65,Bool(c>b),1)
    NstpCheck(66,NeonServiceTargetBind(c),0) : NstpCheck(67,NeonServiceBegin(0.0,0.0,0.0,1.0),0)
    NstpCheck(68,NstpDraw(a,0.0,0.0,160.0,100.0,0),0)
    NstpCheck(69,NstpDraw(b,180.0,0.0,120.0,80.0,0),0)
    NstpCheck(70,NeonServiceTargetDraw(b,180.0,100.0,0.0,2.0,1.0,1.0,1.0,1.0,0,0.0,0.0,2.0,2.0,0),0)
    PokeL(@nan,$7FC00000)
    NstpCheck(71,NeonServiceTargetDraw(a,nan,0.0,0.0,1.0,1.0,1.0,1.0,1.0,0,0.0,0.0,160.0,100.0,0),#NEON_SERVICE_ERR_ARGS)
    NstpCheck(72,NeonServiceEnd(),0) : NstpCheck(73,NeonServiceBegin(0.0,1.0,0.0,1.0),0)
    NstpCheck(74,NstpDraw(c,0.0,0.0,320.0,200.0,0),#NEON_SERVICE_ERR_STATE)
    NstpCheck(75,NeonServiceAbort(),0) : NstpCheck(76,NeonServiceTargetUnbind(c),0)
    NstpCheck(203,NeonServiceBegin(0.0,0.0,0.0,1.0),0)
    NstpCheck(204,NeonServiceTargetBind(old),#NEON_SERVICE_ERR_STALE)
    NstpCheck(205,NeonServiceFrameOpen(),1)
    NstpCheck(206,NeonServiceTargetBind(a),0)
    NstpCheck(207,NeonServiceFrameOpen(),0)
    NstpCheck(208,NeonServiceTargetBind(b),#NEON_SERVICE_ERR_STATE)
    NstpCheck(209,NeonServiceBegin(0.0,1.0,0.0,1.0),0)
    NstpCheck(210,NeonServiceTargetUnbind(a),#NEON_SERVICE_ERR_STATE)
    NstpCheck(211,NeonServiceAbort(),0)
    NstpCheck(212,NeonServiceTargetUnbind(a),0)
    NstpCheck(213,NeonServiceFrameOpen(),1)
    NstpCheck(214,NeonServiceWidth(),1280)
    NstpCheck(215,NeonServiceAbort(),0)
    NstpCheck(216,NeonServiceFrameOpen(),0)
    NstpCheck(77,NeonServiceBegin(0.0,0.0,0.0,1.0),0)
    NstpCheck(217,NeonServiceBoxMapped(900.0,100.0,100.0,100.0,1.0,0.0,0.0,1.0,0,1),0)
    NstpCheck(218,NeonServiceTargetBind(b),0)
    NstpCheck(219,NeonServiceFrameOpen(),0)
    NstpCheck(220,NeonServiceBegin(0.0,1.0,0.0,1.0),0)
    NstpCheck(221,NeonServiceBox(30.0,20.0,60.0,40.0,1.0,1.0,0.0,1.0),0)
    NstpCheck(222,NeonServiceEnd(),0)
    NstpCheck(223,NeonServiceTargetUnbind(b),0)
    NstpCheck(224,NeonServiceFrameOpen(),1)
    NstpCheck(225,NeonServiceBoxMapped(1040.0,100.0,100.0,100.0,0.0,0.0,1.0,1.0,0,1),0)
    NstpCheck(226,NstpDraw(b,450.0,140.0,120.0,80.0,1),0)
    NstpCheck(78,NstpDraw(c,40.0,40.0,320.0,200.0,1),0) : NstpCheck(79,NeonServiceEnd(),0)
    NstpCheck(80,NeonServiceTargetFree(b),0) : NstpCheck(81,NeonServiceTargetFree(b),#NEON_SERVICE_ERR_STALE)
    NstpCheck(82,NeonServiceBegin(0.0,1.0,0.0,1.0),0)
    NstpCheck(83,NstpDraw(b,0.0,0.0,120.0,80.0,0),#NEON_SERVICE_ERR_STALE)
    NstpCheck(84,NeonServiceAbort(),0)
    d=NeonServiceTargetCreate(8,8,0) : NstpCheck(85,Bool(d>c),1)
    NstpCheck(86,NeonServiceTargetFree(d),0)
    NstpCheck(87,NeonServiceTargetBind(old),#NEON_SERVICE_ERR_STALE)
  EndIf
  ; Explicit selected-scope Close and reuse were checked in the first context.
  ; Retain this final scene until the loader captures it, then its graphics
  ; scope retires the context and remaining targets before restoring the console.
  If nstpFailure<>0 And NeonServiceContext()<>0 : NeonServiceClose() : EndIf
  NstpCheck(88,NeonServiceFrameOpen(),0)
  NstpCheck(89,Bool(NeonServiceContext()>0),1) : NstpCheck(90,NeonServiceReady(),1)
  NstpCheck(91,NeonServiceFrameOpen(),0) : NstpCheck(92,NeonServiceWidth(),1280)
  PokeI(report+24,1)
  ProcedureReturn nstpFailure
EndProcedure

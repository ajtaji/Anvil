; SPDX-License-Identifier: MIT
; Returning pure application exercising virtual UI clipping and world drawing.
EnableFloatingPoint
XIncludeFile "Anvil/Math/float32.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_sprite.pbi"
XIncludeFile "Anvil/Graphics/neon_service_mapping.pbi"
XIncludeFile "Anvil/Graphics/neon_service_particles.pbi"
Global nmpChecks.i,nmpFailure.i
Global Dim nmpXY.f[6]
Global Dim nmpPixels.l[4]
Procedure NmpCheck(actual.i,expected.i)
  nmpChecks=nmpChecks+1
  PokeI(#NMP_REPORT+256+nmpChecks*16,actual) : PokeI(#NMP_REPORT+264+nmpChecks*16,expected)
  If actual<>expected And nmpFailure=0 : nmpFailure=nmpChecks : EndIf
  PokeI(#NMP_REPORT+16,nmpFailure) : PokeI(#NMP_REPORT+24,nmpChecks)
EndProcedure
Procedure.i NmpUnavailable(op.i,context.i,request.i,bytes.i)
  ProcedureReturn #NEON_SERVICE_ERR_UNBOUND
EndProcedure
Procedure.i Main(services.i)
  Protected i.i,api.NeonServiceApi,font.i,sprite.i
  Protected box.NeonServiceMappedBoxRequest,clip.NeonServiceScissorRequest
  Protected lines.NeonServiceStaticLinesRequest,canvas.NeonServiceCanvasRequest
  For i=0 To 4095 Step 8 : PokeI(#NMP_REPORT+i,0) : Next
  PokeI(#NMP_REPORT,$4E4D5031) : PokeI(#NMP_REPORT+8,1)
  NmpCheck(SizeOf(NeonServiceMappedBoxRequest),48)
  NmpCheck(SizeOf(NeonServiceMappedPolygonRequest),64)
  NmpCheck(SizeOf(NeonServiceMappedTextRequest),56)
  NmpCheck(SizeOf(NeonServiceStaticLinesRequest),48)
  api\magic=#NEON_SERVICE_MAGIC : api\major=1 : api\minor=3 : api\bytes=48
  api\flags=63 : api\maxFonts=32 : api\dispatch=@NmpUnavailable
  NmpCheck(NeonServiceBindApi(@api,48,32),#NEON_SERVICE_ERR_ABI)
  NmpCheck(NeonServiceBind(services,55),0) : NmpCheck(NeonServiceOpen(),0)
  If nmpFailure<>0 : ProcedureReturn nmpFailure : EndIf
  NmpCheck(NeonServiceWidth(),1280) : NmpCheck(NeonServiceHeight(),800)
  NmpCheck(NeonServiceScissorClear(),#NEON_SERVICE_ERR_STATE)
  NmpCheck(NeonServiceClose(),0) : NmpCheck(NeonServiceOpen(),0)
  NmpCheck(NeonServiceParticlesPrepare(0,0,0),0)
  NmpCheck(NeonServiceCanvas(640,400),0)
  NmpCheck(NeonServiceCanvas(0,400),#NEON_SERVICE_ERR_ARGS)
  canvas\width=8193 : canvas\height=400
  NmpCheck(NeonServiceRequestExtension(27,@canvas,16,0,32,4,0),#NEON_SERVICE_ERR_ARGS)
  NmpCheck(NeonServiceCamera(20.0,10.0,2.0),0)
  font=NeonServiceFontRegister(0,0,16) : NmpCheck(Bool(font>0),1)
  PokeI(#NMP_REPORT+32,font)
  NmpCheck(NeonServicePrepare(font,"Canvas text"),0)
  For i=0 To 3 : nmpPixels[i]=$FFFFFFFF : Next
  sprite=NeonServiceSpriteUpload(1,@nmpPixels[0],16,2,2,0) : NmpCheck(Bool(sprite>0),1)
  For i=0 To 3 : nmpPixels[i]=0 : Next
  NmpCheck(NeonServiceBegin(0.0,0.0,0.0,1.0),0)
  NmpCheck(NeonServiceParticlesDrawPrepared(),#NEON_SERVICE_ERR_STATE)
  NmpCheck(NeonServiceCanvas(320,200),#NEON_SERVICE_ERR_STATE)
  NmpCheck(NeonServiceSpriteBatchBegin(sprite),0)
  NmpCheck(NeonServiceScissorSet(0.0,0.0,10.0,10.0),#NEON_SERVICE_ERR_STATE)
  NmpCheck(NeonServiceSpriteBatchEnd(),0)
  NmpCheck(NeonServiceScissorSet(1.0,1.0,1.0,1.0),0)
  NmpCheck(NeonServiceAbort(),0)
  NmpCheck(NeonServiceBegin(0.0,0.0,0.0,1.0),0)
  ; Begin after Abort clears the old clip: this white marker must be visible.
  NmpCheck(NeonServiceBoxMapped(10.0,10.0,10.0,10.0,1.0,1.0,1.0,1.0,0,1),0)
  NmpCheck(NeonServiceBoxMapped(0.0,0.0,1.0,1.0,1.0,1.0,1.0,1.0,2,1),#NEON_SERVICE_ERR_ARGS)
  NmpCheck(NeonServiceRequestExtension(30,@box,40,1,32,4,0),#NEON_SERVICE_ERR_ARGS)
  clip\x=0.0 : clip\y=0.0 : clip\w=1.0 : clip\h=1.0 : PokeL(@clip,$7FC00001)
  NmpCheck(NeonServiceRequestExtension(28,@clip,16,1,32,4,0),#NEON_SERVICE_ERR_ARGS)
  lines\data=$FE000000 : lines\sourceBytes=16 : lines\vertexCount=2
  lines\r=1.0 : lines\g=1.0 : lines\b=1.0 : lines\a=1.0 : lines\limitVertices=0
  NmpCheck(NeonServiceRequestExtension(33,@lines,48,1,32,4,0),#NEON_SERVICE_ERR_ARGS)
  NmpCheck(NeonServiceStaticLines(@nmpXY[0],15,2,1.0,1.0,1.0,1.0,0),#NEON_SERVICE_ERR_ARGS)
  PokeL(@nmpXY[0],$7F800000)
  NmpCheck(NeonServiceStaticLines(@nmpXY[0],16,2,1.0,1.0,1.0,1.0,0),#NEON_SERVICE_ERR_ARGS)
  NmpCheck(NeonServiceScissorSet(50.0,40.0,60.0,40.0),0)
  NmpCheck(NeonServiceBox(0.0,0.0,640.0,400.0,1.0,0.0,0.0,1.0),0)
  NmpCheck(NeonServicePolygonMapped(100.0,60.0,30.0,20.0,4,0.0,1.0,1.0,1.0,1,1,1),0)
  NmpCheck(NeonServiceScissorClear(),0)
  NmpCheck(NeonServiceBoxMapped(230.0,150.0,20.0,10.0,0.0,1.0,0.0,1.0,1,0),0)
  NmpCheck(NeonServiceBoxMapped(500.0,350.0,10.0,10.0,0.0,0.0,1.0,1.0,0,0),0)
  NmpCheck(NeonServiceBoxMapped(500.0,50.0,30.0,20.0,1.0,1.0,0.0,1.0,0,1),0)
  nmpXY[0]=25.0 : nmpXY[1]=110.0 : nmpXY[2]=150.0 : nmpXY[3]=110.0
  nmpXY[4]=0.0 : nmpXY[5]=0.0
  NmpCheck(NeonServiceStaticLines(@nmpXY[0],24,3,1.0,1.0,1.0,1.0,0),0)
  nmpXY[1]=130.0 : nmpXY[3]=130.0
  NmpCheck(NeonServiceStaticLines(@nmpXY[0],24,3,1.0,0.0,0.0,1.0,1),0)
  For i=0 To 5 : nmpXY[i]=0.0 : Next
  NmpCheck(NeonServiceScissorSet(190.0,50.0,10.0,20.0),0)
  NmpCheck(NeonServiceSprite(sprite,190.0,50.0,0.0,10.0,0.0,0.0,1.0,1.0,1,-1.0,0.0,0.0,0.0,1),0)
  NmpCheck(NeonServiceScissorSet(0.0,0.0,-1.0,100.0),0)
  NmpCheck(NeonServiceBox(0.0,0.0,640.0,400.0,1.0,0.0,1.0,1.0),0)
  NmpCheck(NeonServiceScissorClear(),0)
  NmpCheck(NeonServiceTextMapped(font,30.0,250.0,"Canvas text",1.0,1.0,1.0,1.0,1,1),0)
  NmpCheck(NeonServiceTextMapped(font,670.0,460.0,"Canvas text",1.0,1.0,1.0,1.0,0,0),0)
  NmpCheck(NeonServicePolygonMapped(350.0,200.0,10.0,5.0,4,1.0,0.0,1.0,1.0,1,1,0),0)
  NmpCheck(NeonServiceScissorSet(30.0,325.0,50.0,40.0),0)
  NmpCheck(NeonServiceTextMapped(font,30.0,325.0,"Canvas text",1.0,1.0,1.0,1.0,1,1),0)
  NmpCheck(NeonServiceScissorSet(330.0,325.0,50.0,40.0),0)
  NmpCheck(NeonServiceTextMapped(font,670.0,535.0,"Canvas text",1.0,1.0,1.0,1.0,0,0),0)
  NmpCheck(NeonServiceScissorClear(),0)
  NmpCheck(NeonServiceEnd(),0)
  ProcedureReturn nmpFailure
EndProcedure

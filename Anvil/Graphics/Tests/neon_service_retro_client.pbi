EnableFloatingPoint
XIncludeFile "Anvil/Math/float32.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_targets.pbi"
Global api.NeonServiceApi,row.i,calls.i,prepared.i,drawn.i
Procedure.i NrtDispatch(op.i,context.i,request.i,bytes.i)
 Protected *surface.NeonServiceSurface,*handle.NeonServiceSpriteHandleRequest,*draw.NeonServiceTargetRetroRequest
 calls=calls+1
 If op=#NEON_SERVICE_OPEN
  *surface=request : *surface\logicalW=1280 : *surface\logicalH=800
  *surface\flags=api\flags : *surface\maxFonts=32
  ProcedureReturn 7
 EndIf
 If context<>7 : ProcedureReturn -999 : EndIf
 If op=#NEON_SERVICE_TARGET_RETRO_PREPARE
  If bytes<>SizeOf(NeonServiceSpriteHandleRequest) : ProcedureReturn -998 : EndIf
  *handle=request : If *handle\handle<>9 : ProcedureReturn -997 : EndIf
  prepared=prepared+1
 EndIf
 If op=#NEON_SERVICE_TARGET_RETRO_DRAW
  If bytes<>SizeOf(NeonServiceTargetRetroRequest) : ProcedureReturn -996 : EndIf
  *draw=request
  If *draw\handle<>9 Or MathBitsOf(*draw\time)<>$3E000000 Or *draw\reserved<>0 : ProcedureReturn -995 : EndIf
  drawn=drawn+1
 EndIf
 ProcedureReturn 0
EndProcedure
Procedure NrtSave(value.i)
 PokeI($E1C00040+row*8,value) : row=row+1
EndProcedure
Procedure.i Main(services.i)
 Protected i.i,t.f
 For i=0 To 16383 : PokeA($E1C00000+i,0) : Next
 api\magic=#NEON_SERVICE_MAGIC : api\major=1 : api\minor=11
 api\bytes=SizeOf(NeonServiceApi) : api\maxFonts=32 : api\dispatch=@NrtDispatch
 api\flags=#NEON_SERVICE_TARGET_RETRO
 NrtSave(NeonServiceBindApi(@api,SizeOf(NeonServiceApi),#NEON_SERVICE_TARGET_RETRO))
 api\flags=api\flags | #NEON_SERVICE_TARGETS
 NrtSave(NeonServiceBindApi(@api,SizeOf(NeonServiceApi),#NEON_SERVICE_TARGET_RETRO))
 api\minor=12
 NrtSave(NeonServiceBindApi(@api,SizeOf(NeonServiceApi),#NEON_SERVICE_TARGET_RETRO))
 NrtSave(NeonServiceOpen())
 NrtSave(NeonServiceTargetRetroPrepare(0))
 NrtSave(NeonServiceTargetRetroPrepare(9))
 NrtSave(NeonServiceTargetDrawRetro(9,0.125))
 NrtSave(NeonServiceBegin(0.0,0.0,0.0,1.0))
 NrtSave(NeonServiceTargetRetroPrepare(9))
 PokeL(@t,$7FC00000) : NrtSave(NeonServiceTargetDrawRetro(9,t))
 NrtSave(NeonServiceTargetDrawRetro(9,0.125))
 NrtSave(NeonServiceEnd())
 NrtSave(NeonServiceClose())
 NrtSave(NeonServiceUnbind())
 NrtSave(prepared) : NrtSave(drawn) : NrtSave(calls)
 PokeI($E1C00000,$4E525431) : PokeI($E1C00008,row)
 ProcedureReturn 0
EndProcedure

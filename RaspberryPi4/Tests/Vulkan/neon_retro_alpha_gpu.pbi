XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_port.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_sprite_port.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_service_targets.pbi"
Global NcdFailure.i,NcdChecks.i
Global Dim NcdClear.l[4]
Procedure NcdCheck(actual.i,expected.i)
 PokeI($E1C00400+NcdChecks*16,actual) : PokeI($E1C00408+NcdChecks*16,expected)
 NcdChecks=NcdChecks+1
 If actual<>expected And NcdFailure=0 : NcdFailure=NcdChecks : EndIf
 PokeI($E1C00010,NcdFailure) : PokeI($E1C00018,NcdChecks)
EndProcedure
Procedure.i NcdFrame(dev.i,renderPass.i,framebuffer.i,base.i,pitch.i)
 Protected create.NeonServiceTargetCreateRequest,bind.NeonServiceTargetBindRequest
 Protected handle.NeonServiceSpriteHandleRequest,draw.NeonServiceTargetRetroRequest
 Protected token.i,rc.i,scratch.i
 NcdCheck(NeonVkChromeRebind(framebuffer,1280,800,800,1280,pitch,90),0)
 NcdCheck(NeonVkPortCanvas(1280,800,1280,800),0)
 NcdCheck(NeonVkTargetsOpen(17),0)
 create\width=64 : create\height=64 : create\linear=0
 token=NeonVkTargetsDispatch(#NEON_SERVICE_TARGET_CREATE,17,@create,SizeOf(NeonServiceTargetCreateRequest),0)
 NcdCheck(Bool(token>0),1)
 If NcdFailure<>0 : Goto NrDone : EndIf
 handle\handle=token : bind\handle=token : draw\handle=token : draw\time=0.125
 NcdCheck(NeonVkTargetsDispatch(#NEON_SERVICE_TARGET_RETRO_PREPARE,18,@handle,SizeOf(NeonServiceSpriteHandleRequest),0),#NEON_SERVICE_ERR_STATE)
 NcdCheck(NeonVkTargetsDispatch(#NEON_SERVICE_TARGET_RETRO_PREPARE,17,@handle,0,0),#NEON_SERVICE_ERR_ARGS)
 handle\handle=token+1
 NcdCheck(NeonVkTargetsDispatch(#NEON_SERVICE_TARGET_RETRO_PREPARE,17,@handle,SizeOf(NeonServiceSpriteHandleRequest),0),#NEON_SERVICE_ERR_STALE)
 handle\handle=token
 NcdCheck(NeonVkTargetsDispatch(#NEON_SERVICE_TARGET_RETRO_PREPARE,17,@handle,SizeOf(NeonServiceSpriteHandleRequest),0),#NEON_CANVAS_ERR_STATE)
 NcdCheck(NeonVkTargetsDispatch(#NEON_SERVICE_TARGET_BIND,17,@bind,SizeOf(NeonServiceTargetBindRequest),0),0)
 NcdCheck(NeonVkTargetsFrameBegin(@NcdClear[0]),0)
 NcdCheck(NeonVkChromeBox(0,0,64,64,$FF808080),0)
 NcdCheck(NeonVkChromeBox(0,0,64,64,$CC0000FF),0)
 NcdCheck(NeonVkTargetsFrameEnd(),0)
 NcdCheck(NeonVkTargetsDispatch(#NEON_SERVICE_TARGET_UNBIND,17,@handle,SizeOf(NeonServiceSpriteHandleRequest),0),0)
 NcdCheck(NeonVkTargetsDispatch(#NEON_SERVICE_TARGET_RETRO_PREPARE,17,@handle,SizeOf(NeonServiceSpriteHandleRequest),0),0)
 NcdCheck(NeonVkTargetsDispatch(#NEON_SERVICE_TARGET_RETRO_DRAW,17,@draw,SizeOf(NeonServiceTargetRetroRequest),0),#NEON_SERVICE_ERR_STATE)
 NcdCheck(NeonVkChromeBegin(@NcdClear[0]),0)
 NcdCheck(NeonVkTargetsDispatch(#NEON_SERVICE_TARGET_RETRO_PREPARE,17,@handle,SizeOf(NeonServiceSpriteHandleRequest),1),#NEON_SERVICE_ERR_STATE)
 draw\reserved=1
 NcdCheck(NeonVkTargetsDispatch(#NEON_SERVICE_TARGET_RETRO_DRAW,17,@draw,SizeOf(NeonServiceTargetRetroRequest),1),#NEON_SERVICE_ERR_ARGS)
 draw\reserved=0 : PokeL(@draw\time,$7FC00000)
 NcdCheck(NeonVkTargetsDispatch(#NEON_SERVICE_TARGET_RETRO_DRAW,17,@draw,SizeOf(NeonServiceTargetRetroRequest),1),#NEON_SERVICE_ERR_ARGS)
 draw\time=0.125
 NcdCheck(NeonVkTargetsDispatch(#NEON_SERVICE_TARGET_RETRO_DRAW,17,@draw,SizeOf(NeonServiceTargetRetroRequest),1),0)
 NcdCheck(NeonVkChromeEnd(),0)
 NcdCheck(NeonVkChromeFinish(),0)
 NcdCheck(NeonVkChromePresentValidate(),1)
 NcdCheck(DisplayAdopt(#NW_DSI_SCAN,#NW_SURFACE_PITCH,#NVWA_WIDTH,#NVWA_HEIGHT,32),1)
 scratch=@nwDmaScratch[0]+255 : scratch=scratch-(scratch%256)
 NcdCheck(DmaSetScratch(scratch,512),1) : NcdCheck(DisplayDmaBind(),1) : NcdCheck(DmaInit(),1)
 DisplayDmaReadback(1) : DisplayUseDma(1)
 DisplayBlit(base,pitch,0,0,800,1280)
 NcdCheck(NeonVkChromePresentConsume(),1)
 NrDone:
 If NeonVkChromeFramePending()<>0 : NeonVkChromeFinish() : EndIf
 If NeonVkChromeFrameAbortable()<>0 : NeonVkChromeAbort() : EndIf
 If NeonVkChromePresentPending()<>0 : NeonVkChromePresentConsume() : EndIf
 NcdCheck(NeonVkTargetsClose(17),0)
 NcdCheck(NeonVkTargetsBound(),0)
 DisplayUseDma(0) : DisplayFlush()
 ProcedureReturn NcdFailure
EndProcedure

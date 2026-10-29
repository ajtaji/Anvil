; SPDX-License-Identifier: MIT
; Optional CRT canvas composition. Frame ownership remains with the caller.
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_canvas.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_retro.pbi"
XIncludeFile "Anvil/Graphics/neon_canvas_retro.pbi"
Procedure.i ncrCanvasReady(*c.NeonVkCanvas,needsFrame.i)
  If ncvValid(*c)=0 : ProcedureReturn #NEON_CANVAS_ERR_ARGS : EndIf
  If ncvSlot(*c)=0 Or *c\phase<>#NEON_VK_CANVAS_IDLE Or (needsFrame<>0 And *c\hasFrame=0) : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STATE) : EndIf
  If NeonVkChromeTargetCurrent(*c\target\framebuffer,*c\target\generation)=0 Or NeonVkChromeImageSpriteGenerationId(*c\sprite)<>*c\textureGeneration : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STALE) : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i NeonVkCanvasRetroPrepare(*c.NeonVkCanvas)
  ; Pipeline construction does not sample the canvas. Permit it before the
  ; first source frame, while retaining ownership/generation/idle checks.
  Protected rc.i=ncrCanvasReady(*c,0)
  If rc<>0 : ProcedureReturn rc : EndIf
  ProcedureReturn ncvFail(*c,NeonVkChromeRetroPrepare())
EndProcedure
Procedure.i NeonVkCanvasDrawRetro(*c.NeonVkCanvas,timeBits.i)
  Protected rc.i=ncrCanvasReady(*c,1)
  If rc<>0 : ProcedureReturn rc : EndIf
  rc=NeonVkChromeRetroDrawId(*c\sprite,*c\viewport\x,*c\viewport\y,*c\viewport\width,*c\viewport\height,timeBits)
  ProcedureReturn ncvFail(*c,rc)
EndProcedure
Procedure.i NeonVkCanvasMapRetroPoint(*c.NeonVkCanvas,x.i,y.i,*out.NeonCanvasPoint)
  Protected rc.i=ncrCanvasReady(*c,1)
  If rc<>0 : ProcedureReturn rc : EndIf
  If (*out & 7)<>0 Or NeonByteSpan(*out,SizeOf(NeonCanvasPoint))=0 : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_ARGS) : EndIf
  If NeonByteOverlap(*c,SizeOf(NeonVkCanvas),*out,SizeOf(NeonCanvasPoint))<>0 : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_ARGS) : EndIf
  ProcedureReturn NeonCanvasMapRetroPoint(@*c\viewport,x,y,*out)
EndProcedure

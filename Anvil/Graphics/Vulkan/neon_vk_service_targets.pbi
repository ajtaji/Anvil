; SPDX-License-Identifier: MIT
; Target-neutral resident target ownership. Only opaque tokens cross the API.
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_canvas_retro.pbi"
XIncludeFile "Anvil/Graphics/neon_service_validation.pbi"
Global nvstContext.i,nvstClock.i,nvstActive.i,nvstFailed.i,nvstParentFrame.i
Global nvstCanvasW.i,nvstCanvasH.i,nvstTargetW.i,nvstTargetH.i
Global Dim nvstTarget.NeonVkCanvas[#NEON_SERVICE_MAX_TARGETS]
Global Dim nvstToken.i[#NEON_SERVICE_MAX_TARGETS]
Global Dim nvstLinear.i[#NEON_SERVICE_MAX_TARGETS]
Procedure.i nvstRecord(request.i,bytes.i,wanted.i)
  ProcedureReturn Bool(bytes=wanted And (request & 7)=0 And NeonByteSpan(request,wanted)<>0)
EndProcedure
Procedure.i nvstIndex(token.i)
  Protected i.i
  If token<1 : ProcedureReturn -1 : EndIf
  For i=0 To #NEON_SERVICE_MAX_TARGETS-1
    If nvstToken[i]=token : ProcedureReturn i : EndIf
  Next
  ProcedureReturn -1
EndProcedure
Procedure.i nvstRestoreMapping()
  Protected x.f,y.f,zoom.f,rc.i
  ; The original target scope changes base/window dimensions, not camera
  ; state. Preserve camera changes made inside the target scope as well.
  x=NeonVkPortCameraX() : y=NeonVkPortCameraY() : zoom=NeonVkPortCameraZoom()
  rc=NeonVkPortCanvas(nvstCanvasW,nvstCanvasH,nvstTargetW,nvstTargetH)
  If rc=0 : rc=NeonVkPortCamera(x,y,zoom) : EndIf
  ProcedureReturn rc
EndProcedure
Procedure.i NeonVkTargetsOpen(context.i)
  Protected i.i,rc.i
  If context<1 Or nvstContext<>0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
  For i=0 To #NEON_SERVICE_MAX_TARGETS-1
    If nvstTarget[i]\phase<>#NEON_VK_CANVAS_CLOSED : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
  Next
  nvstContext=context : nvstActive=0 : nvstFailed=0 : nvstParentFrame=0
  For i=0 To #NEON_SERVICE_MAX_TARGETS-1
    rc=NeonVkCanvasInit(@nvstTarget[i],SizeOf(NeonVkCanvas))
    If rc<>0 : nvstFailed=1 : ProcedureReturn rc : EndIf
    nvstToken[i]=0 : nvstLinear[i]=0
  Next
  ProcedureReturn 0
EndProcedure
Procedure.i NeonVkTargetsClose(context.i)
  Protected i.i,rc.i
  If nvstContext=0 : ProcedureReturn 0 : EndIf
  If context<>nvstContext : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
  ; Context close owns the window recording as well as its retained targets.
  ; Retire that unsubmitted frame before idle target lifetime checks.
  If NeonVkChromeFrameAbortable()<>0
    If nvstActive=0
      rc=NeonVkChromeAbort()
      If rc<>0 : nvstFailed=1 : ProcedureReturn rc : EndIf
    ElseIf nvstParentFrame<>0 And nvstTarget[nvstActive-1]\phase=#NEON_VK_CANVAS_IDLE
      rc=NeonVkChromeAbort()
      If rc<>0 : nvstFailed=1 : ProcedureReturn rc : EndIf
    EndIf
  EndIf
  If nvstActive>0
    i=nvstActive-1
    rc=NeonVkCanvasCloseContextScope(@nvstTarget[i])
    If rc<>0 : nvstFailed=1 : ProcedureReturn rc : EndIf
    rc=nvstRestoreMapping()
    If rc<>0 : nvstFailed=1 : ProcedureReturn rc : EndIf
    nvstToken[i]=0 : nvstActive=0
  EndIf
  If nvstParentFrame<>0
    rc=NeonVkChromeCancelSuspended()
    If rc<>0 : nvstFailed=1 : ProcedureReturn rc : EndIf
    nvstParentFrame=0
  EndIf
  For i=0 To #NEON_SERVICE_MAX_TARGETS-1
    If nvstTarget[i]\phase<>#NEON_VK_CANVAS_CLOSED
      rc=NeonVkCanvasClose(@nvstTarget[i])
      If rc<>0 : nvstFailed=1 : ProcedureReturn rc : EndIf
    EndIf
    nvstToken[i]=0 : nvstLinear[i]=0
  Next
  nvstContext=0 : nvstFailed=0
  ProcedureReturn 0
EndProcedure
Procedure.i NeonVkTargetsParentFrame()
  ProcedureReturn nvstParentFrame
EndProcedure
Procedure.i NeonVkTargetsBound()
  ProcedureReturn Bool(nvstActive>0)
EndProcedure
Procedure.i NeonVkTargetsBoundWidth()
  If nvstActive<1 : ProcedureReturn 0 : EndIf
  ProcedureReturn nvstTarget[nvstActive-1]\width
EndProcedure
Procedure.i NeonVkTargetsBoundHeight()
  If nvstActive<1 : ProcedureReturn 0 : EndIf
  ProcedureReturn nvstTarget[nvstActive-1]\height
EndProcedure
Procedure.i NeonVkTargetsOwnsSprite(sprite.i)
  Protected i.i
  For i=0 To #NEON_SERVICE_MAX_TARGETS-1
    If nvstTarget[i]\phase<>#NEON_VK_CANVAS_CLOSED And nvstTarget[i]\sprite=sprite : ProcedureReturn 1 : EndIf
  Next
  ProcedureReturn 0
EndProcedure
Procedure.i NeonVkTargetsFailed()
  Protected i.i
  If nvstFailed<>0 Or NeonVkChromeReady()=0 Or NeonVkChromeUpdatesQuarantined()<>0 : ProcedureReturn 1 : EndIf
  For i=0 To #NEON_SERVICE_MAX_TARGETS-1
    If nvstTarget[i]\phase=#NEON_VK_CANVAS_BROKEN : ProcedureReturn 1 : EndIf
  Next
  ProcedureReturn 0
EndProcedure
Procedure.i NeonVkTargetsFrameBegin(clear.i)
  If nvstContext=0 Or nvstActive=0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
  ProcedureReturn NeonVkCanvasBegin(@nvstTarget[nvstActive-1],clear)
EndProcedure
Procedure.i NeonVkTargetsFrameBeginLoad()
  If nvstContext=0 Or nvstActive=0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
  If nvstTarget[nvstActive-1]\hasFrame=0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
  ProcedureReturn NeonVkCanvasBeginLoad(@nvstTarget[nvstActive-1])
EndProcedure
Procedure.i NeonVkTargetsFrameEnd()
  If nvstContext=0 Or nvstActive=0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
  ProcedureReturn NeonVkCanvasEnd(@nvstTarget[nvstActive-1])
EndProcedure
Procedure.i NeonVkTargetsFrameAbort()
  If nvstContext=0 Or nvstActive=0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
  ProcedureReturn NeonVkCanvasAbort(@nvstTarget[nvstActive-1])
EndProcedure
Procedure.i nvstFilter(index.i)
  If nvstTarget[index]\linear=nvstLinear[index] : ProcedureReturn 0 : EndIf
  ProcedureReturn NeonVkCanvasSetLinear(@nvstTarget[index],nvstLinear[index])
EndProcedure
Procedure.i NeonVkTargetsDispatch(op.i,context.i,request.i,bytes.i,frame.i)
  Protected i.i,slot.i,rc.i,cleanup.i,x.f,y.f,zoom.f
  Protected *create.NeonServiceTargetCreateRequest,*resize.NeonServiceTargetResizeRequest
  Protected *bind.NeonServiceTargetBindRequest,*handle.NeonServiceSpriteHandleRequest
  Protected *limits.NeonServiceTargetLimits,*draw.NeonServiceSpriteDrawRequest
  Protected *retro.NeonServiceTargetRetroRequest
  Protected sprite.NeonVkPortSpriteRef
  If context<1 Or context<>nvstContext Or nvstFailed<>0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
  If op=#NEON_SERVICE_TARGET_RETRO_PREPARE
    If frame<>0 Or nvstActive<>0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
    If nvstRecord(request,bytes,SizeOf(NeonServiceSpriteHandleRequest))=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    *handle=request : i=nvstIndex(*handle\handle)
    If i<0 : ProcedureReturn #NEON_SERVICE_ERR_STALE : EndIf
    ProcedureReturn NeonVkCanvasRetroPrepare(@nvstTarget[i])
  EndIf
  If op=#NEON_SERVICE_TARGET_RETRO_DRAW
    If frame<>1 Or nvstActive<>0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
    If nvstRecord(request,bytes,SizeOf(NeonServiceTargetRetroRequest))=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    *retro=request
    If *retro\reserved<>0 Or (MathBitsOf(*retro\time) & $7F800000)=$7F800000 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    i=nvstIndex(*retro\handle)
    If i<0 : ProcedureReturn #NEON_SERVICE_ERR_STALE : EndIf
    ProcedureReturn NeonVkCanvasDrawRetro(@nvstTarget[i],MathBitsOf(*retro\time))
  EndIf
  If op=#NEON_SERVICE_TARGET_LIMITS
    If nvstRecord(request,bytes,SizeOf(NeonServiceTargetLimits))=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    *limits=request : *limits\slots=#NEON_SERVICE_MAX_TARGETS : *limits\maxDimension=#NEON_SERVICE_TARGET_DIMENSION
    ProcedureReturn 0
  EndIf
  If op=#NEON_SERVICE_TARGET_CREATE
    If frame<>0 Or nvstActive<>0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
    If nvstRecord(request,bytes,SizeOf(NeonServiceTargetCreateRequest))=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    *create=request
    If *create\width<1 Or *create\height<1 Or *create\width>#NEON_SERVICE_TARGET_DIMENSION Or *create\height>#NEON_SERVICE_TARGET_DIMENSION Or (*create\linear<>0 And *create\linear<>1) : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    If nvstClock=$7FFFFFFFFFFFFFFF : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
    i=0
    While i<#NEON_SERVICE_MAX_TARGETS
      If nvstTarget[i]\phase=#NEON_VK_CANVAS_CLOSED : Break : EndIf
      i=i+1
    Wend
    If i=#NEON_SERVICE_MAX_TARGETS : ProcedureReturn #NEON_SERVICE_ERR_CAPACITY : EndIf
    slot=1
    While slot<=#NEON_SERVICE_MAX_SPRITES And NeonVkChromeImageSpriteAllocatedId(slot)<>0 : slot=slot+1 : Wend
    If slot>#NEON_SERVICE_MAX_SPRITES : ProcedureReturn #NEON_SERVICE_ERR_CAPACITY : EndIf
    rc=NeonVkCanvasCreateBlank(@nvstTarget[i],*create\width,*create\height,slot)
    If rc=0
      nvstLinear[i]=*create\linear : rc=nvstFilter(i)
    EndIf
    If rc<>0
      If nvstTarget[i]\phase<>#NEON_VK_CANVAS_CLOSED
        cleanup=NeonVkCanvasClose(@nvstTarget[i])
        If cleanup<>0 : nvstFailed=1 : EndIf
      EndIf
      ProcedureReturn rc
    EndIf
    nvstClock=nvstClock+1 : nvstToken[i]=nvstClock
    ProcedureReturn nvstToken[i]
  EndIf
  If op=#NEON_SERVICE_TARGET_DRAW
    If frame<>1 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
    If nvstRecord(request,bytes,SizeOf(NeonServiceSpriteDrawRequest))=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    If NeonServiceFloatsValid(request+8,8)=0 Or NeonServiceFloatsValid(request+48,4)=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    *draw=request
    If (*draw\scaled<>0 And *draw\scaled<>1) Or (*draw\ignoreCamera<>0 And *draw\ignoreCamera<>1) : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    i=nvstIndex(*draw\handle)
    If i<0 : ProcedureReturn #NEON_SERVICE_ERR_STALE : EndIf
    If nvstActive=i+1 Or nvstTarget[i]\hasFrame=0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
    sprite\id=nvstTarget[i]\sprite : sprite\width=nvstTarget[i]\width : sprite\height=nvstTarget[i]\height : sprite\generation=nvstTarget[i]\textureGeneration
    ProcedureReturn NeonVkPortSprite(@sprite,*draw\x,*draw\y,*draw\angle,*draw\scale,*draw\r,*draw\g,*draw\b,*draw\a,*draw\scaled,*draw\srcX,*draw\srcY,*draw\srcW,*draw\srcH,*draw\ignoreCamera)
  EndIf
  If frame<>0 And (op<>#NEON_SERVICE_TARGET_BIND Or frame<>1) : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
  If op=#NEON_SERVICE_TARGET_BIND
    If nvstActive<>0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
    If nvstRecord(request,bytes,SizeOf(NeonServiceTargetBindRequest))=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    *bind=request : i=nvstIndex(*bind\handle)
    If i<0 : ProcedureReturn #NEON_SERVICE_ERR_STALE : EndIf
    rc=NeonVkCanvasBindCheck(@nvstTarget[i])
    If rc<>0 : ProcedureReturn rc : EndIf
    nvstCanvasW=NeonVkPortCanvasWidth() : nvstCanvasH=NeonVkPortCanvasHeight()
    nvstTargetW=NeonVkPortTargetWidth() : nvstTargetH=NeonVkPortTargetHeight()
    x=NeonVkPortCameraX() : y=NeonVkPortCameraY() : zoom=NeonVkPortCameraZoom()
    nvstParentFrame=frame
    If frame=1
      rc=NeonVkChromeSuspend()
      If rc<>0 : nvstFailed=1 : ProcedureReturn #NEON_SERVICE_ERR_PROVIDER : EndIf
    EndIf
    rc=NeonVkCanvasBind(@nvstTarget[i])
    If rc<>0
      If nvstParentFrame<>0 : nvstFailed=1 : ProcedureReturn #NEON_SERVICE_ERR_PROVIDER : EndIf
      ProcedureReturn rc
    EndIf
    nvstActive=i+1
    rc=NeonVkPortCanvas(nvstTarget[i]\width,nvstTarget[i]\height,nvstTarget[i]\width,nvstTarget[i]\height)
    If rc=0 : rc=NeonVkPortCamera(x,y,zoom) : EndIf
    If rc<>0 : nvstFailed=1 : ProcedureReturn #NEON_SERVICE_ERR_PROVIDER : EndIf
    *bind\width=nvstTarget[i]\width : *bind\height=nvstTarget[i]\height
    ProcedureReturn 0
  EndIf
  If op=#NEON_SERVICE_TARGET_RESIZE
    If nvstActive<>0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
    If nvstRecord(request,bytes,SizeOf(NeonServiceTargetResizeRequest))=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    *resize=request : i=nvstIndex(*resize\handle)
    If i<0 : ProcedureReturn #NEON_SERVICE_ERR_STALE : EndIf
    If *resize\width<1 Or *resize\height<1 Or *resize\width>#NEON_SERVICE_TARGET_DIMENSION Or *resize\height>#NEON_SERVICE_TARGET_DIMENSION : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    rc=NeonVkCanvasResizeBlank(@nvstTarget[i],*resize\width,*resize\height)
    If rc=0 : rc=nvstFilter(i) : EndIf
    If nvstTarget[i]\phase=#NEON_VK_CANVAS_CLOSED : nvstToken[i]=0 : EndIf
    ProcedureReturn rc
  EndIf
  If op<>#NEON_SERVICE_TARGET_FREE And op<>#NEON_SERVICE_TARGET_UNBIND : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
  If nvstRecord(request,bytes,SizeOf(NeonServiceSpriteHandleRequest))=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
  *handle=request : i=nvstIndex(*handle\handle)
  If i<0 : ProcedureReturn #NEON_SERVICE_ERR_STALE : EndIf
  If op=#NEON_SERVICE_TARGET_UNBIND
    If nvstActive<>i+1 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
    rc=NeonVkCanvasUnbind(@nvstTarget[i])
    If rc<>0 : ProcedureReturn rc : EndIf
    rc=nvstRestoreMapping()
    If rc<>0 : nvstFailed=1 : ProcedureReturn #NEON_SERVICE_ERR_PROVIDER : EndIf
    If nvstParentFrame<>0
      rc=NeonVkChromeResume()
      If rc<>0 : nvstFailed=1 : ProcedureReturn #NEON_SERVICE_ERR_PROVIDER : EndIf
    EndIf
    nvstParentFrame=0 : nvstActive=0 : ProcedureReturn 0
  EndIf
  If nvstActive<>0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
  rc=NeonVkCanvasClose(@nvstTarget[i])
  If rc=0 : nvstToken[i]=0 : nvstLinear[i]=0 : EndIf
  ProcedureReturn rc
EndProcedure

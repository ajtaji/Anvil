; SPDX-License-Identifier: MIT
; Shared resident Neon service protocol, extracted from the Pi 4 console.
; Owns context/font epochs, request validation, target/sprite scopes and
; dispatch onto the existing public Neon Vulkan ports. No device registers.
; The composition supplies AvsSurfaceStart (0 success), Stop (1 success),
; Present (0 success), PresentError, RetireReady (1 safe) and Flags. Start publishes logical W/H;
; Present publishes optional copy timing components. Close retires all targets
; before the board retires/reset its Chrome owner, then releases font bytes.
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_service_targets.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_service_caret.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_resident_state.pbi"

Procedure.i avsRestoreFont()
  If avsPreviousFont<0
    If AnvilTrueTypeSlotDeselect()=0 : ProcedureReturn #NEON_SERVICE_ERR_PROVIDER : EndIf
    ProcedureReturn 0
  EndIf
  If AnvilTrueTypeSlotBytes(avsPreviousFont)<1 Or AnvilTrueTypeSlotGeneration(avsPreviousFont)<>avsPreviousFontGeneration
    ProcedureReturn #NEON_SERVICE_ERR_STALE
  EndIf
  If AnvilTrueTypeSlotSelect(avsPreviousFont)=0 : ProcedureReturn #NEON_SERVICE_ERR_PROVIDER : EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i avsClose()
  Define i.i
  Define rc.i
  avsReady = 0
  If avsContext = 0 : ProcedureReturn 0 : EndIf
  ; Refuse before touching target allocations as well as Chrome resources.
  ; A foreign bus-master owner may still name any of their backing storage.
  If AvsSurfaceRetireReady()<>1
    avsError=#NEON_SERVICE_ERR_PROVIDER : ProcedureReturn avsError
  EndIf
  rc=NeonVkTargetsClose(avsContext)
  If rc<>0 : avsError=rc : ProcedureReturn rc : EndIf
  If AvsSurfaceStop() = 0
    avsError = AvsSurfacePresentError() : ProcedureReturn avsError
  EndIf
  ; GPU/device retirement precedes font-byte retirement. A failed restore or
  ; release retains the context and all not-yet-released generation tokens.
  rc=avsRestoreFont()
  If rc<>0 : avsError=rc : ProcedureReturn rc : EndIf
  For i=0 To #NEON_SERVICE_MAX_FONT_ASSETS-1
    If avsOwnedFont[i]<>0
      If AnvilFontReleaseMemory(i,avsOwnedFont[i])=0 : avsError=#NEON_SERVICE_ERR_STALE : ProcedureReturn avsError : EndIf
      avsOwnedFont[i]=0
    EndIf
  Next
  NeonVkPortSpriteFrameRetired()
  For i=0 To #NEON_SERVICE_MAX_SPRITES-1 : avsSpriteHandle[i]=0 : Next
  avsBatch=0
  avsParticleReady=0 : avsParticleCount=0
  avsContext = 0 : avsFrame = 0 : avsFontCount = 0 : avsError = 0
  ProcedureReturn 0
EndProcedure

Procedure.i VulkanNeonServiceReset()
  ProcedureReturn avsClose()
EndProcedure

Procedure.i avsRecord(request.i, bytes.i, expected.i)
  If bytes <> expected : ProcedureReturn 0 : EndIf
  If expected = 0 : ProcedureReturn Bool(request = 0) : EndIf
  ProcedureReturn Bool(request <> 0 And (request & 7) = 0)
EndProcedure

; Reject NaN/infinity before conversion to coordinates or packed channels.
Procedure.i avsFloats(request.i,count.i)
  ProcedureReturn NeonServiceFloatsValid(request,count)
EndProcedure

Procedure.i avsFontIndex(font.i)
  Define index.i
  If font >= 0 And font <= 3 : ProcedureReturn 0 : EndIf
  If (font >> 16) <> avsContext : ProcedureReturn -1 : EndIf
  index = font & $FFFF
  If index < 1 Or index > avsFontCount : ProcedureReturn -1 : EndIf
  ProcedureReturn index
EndProcedure

Procedure.i avsFontBytesRequest(op.i,request.i,bytes.i)
  Define *load.NeonServiceFontLoadRequest,*unload.NeonServiceFontUnloadRequest
  Define slot.i,index.i,generation.i,rc.i
  If avsFrame<>0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
  If op=#NEON_SERVICE_FONT_LOAD
    If avsRecord(request,bytes,SizeOf(NeonServiceFontLoadRequest))=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    *load=request
    If *load\data<1 Or *load\bytes<1 Or *load\bytes>#NEON_SERVICE_MAX_FONT_BYTES Or *load\role<0 Or *load\role>3 Or *load\pixels<1 Or *load\pixels>512
      ProcedureReturn #NEON_SERVICE_ERR_ARGS
    EndIf
    If *load\data+*load\bytes-1<*load\data : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    If InPayload(*load\data,*load\data+*load\bytes-1)=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    If avsFontCount>=32 : ProcedureReturn #NEON_SERVICE_ERR_CAPACITY : EndIf
    slot=0
    While slot<#NEON_SERVICE_MAX_FONT_ASSETS
      If avsOwnedFont[slot]=0 And AnvilTrueTypeSlotBytes(slot)=0 : Break : EndIf
      slot=slot+1
    Wend
    If slot>=#NEON_SERVICE_MAX_FONT_ASSETS : ProcedureReturn #NEON_SERVICE_ERR_CAPACITY : EndIf
    generation=AnvilFontLoadMemory(slot,*load\data,*load\bytes)
    If generation<1 : ProcedureReturn #NEON_SERVICE_ERR_FORMAT : EndIf
    avsOwnedFont[slot]=generation
    rc=NeonVkPortFontBind(@avsFont[avsFontCount],slot,*load\role,*load\pixels)
    If rc<>0
      If AnvilFontReleaseMemory(slot,generation)<>0 : avsOwnedFont[slot]=0 : EndIf
      ProcedureReturn rc
    EndIf
    avsFontCount=avsFontCount+1
    ProcedureReturn (avsContext << 16) | avsFontCount
  EndIf
  If op=#NEON_SERVICE_FONT_UNLOAD
    If avsRecord(request,bytes,SizeOf(NeonServiceFontUnloadRequest))=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    *unload=request : index=avsFontIndex(*unload\font)
    If index<1 : ProcedureReturn #NEON_SERVICE_ERR_STALE : EndIf
    slot=avsFont[index-1]\slot : generation=avsFont[index-1]\generation
    If slot<0 Or slot>=#NEON_SERVICE_MAX_FONT_ASSETS : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
    If avsOwnedFont[slot]=0 Or avsOwnedFont[slot]<>generation : ProcedureReturn #NEON_SERVICE_ERR_STALE : EndIf
    If AnvilTrueTypeSlotSelected()=slot
      rc=avsRestoreFont() : If rc<>0 : ProcedureReturn rc : EndIf
    EndIf
    If AnvilFontReleaseMemory(slot,generation)=0 : ProcedureReturn #NEON_SERVICE_ERR_STALE : EndIf
    avsOwnedFont[slot]=0 : ProcedureReturn 0
  EndIf
  ProcedureReturn #NEON_SERVICE_ERR_ARGS
EndProcedure

Procedure.i avsMeasure(font.i, text.i, height.i)
  Define index.i, measured.i
  Define width.f
  index = avsFontIndex(font)
  If index < 0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
  If height <> 0
    If index = 0
      measured = NeonVkChromeMeasureLineHeight(font)
    Else
      measured = NeonVkPortFontLineHeight(@avsFont[index - 1])
    EndIf
    If measured < 0 : ProcedureReturn measured : EndIf
    ProcedureReturn measured * 65536
  EndIf
  If text = 0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
  If index = 0
    width = NeonVkPortTextWidth(font, text, 1)
  Else
    width = NeonVkPortFontTextWidth(@avsFont[index - 1], text, 1)
  EndIf
  If width < 0.0 Or width > 1000000.0 : ProcedureReturn #NEON_SERVICE_ERR_PROVIDER : EndIf
  ProcedureReturn MathFToInt(width * 65536.0)
EndProcedure

Procedure.i avsSpriteIndex(handle.i)
  Define i.i
  If handle<1 : ProcedureReturn -1 : EndIf
  For i=0 To #NEON_SERVICE_MAX_SPRITES-1
    If avsSpriteHandle[i]=handle : ProcedureReturn i : EndIf
  Next
  ProcedureReturn -1
EndProcedure

Procedure.i avsSpriteRequest(op.i,request.i,bytes.i)
  Define *limits.NeonServiceSpriteLimits,*upload.NeonServiceSpriteUploadRequest
  Define *handle.NeonServiceSpriteHandleRequest,*draw.NeonServiceSpriteDrawRequest
  Define *camera.NeonServiceCameraRequest,*batch.NeonServiceSpriteBatchRequest
  Define candidate.NeonVkPortSpriteRef,index.i,rc.i,needed.i
  Select op
    Case #NEON_SERVICE_SPRITE_LIMITS
      If avsRecord(request,bytes,SizeOf(NeonServiceSpriteLimits))=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      *limits=request : *limits\slots=#NEON_SERVICE_MAX_SPRITES
      *limits\maxDimension=#NEON_SERVICE_MAX_SPRITE_DIM : *limits\maxUploadBytes=#NEON_SERVICE_MAX_SPRITE_BYTES
      *limits\maxBatch=#NEON_SERVICE_MAX_SPRITE_BATCH
      ProcedureReturn 0
    Case #NEON_SERVICE_SPRITE_UPLOAD
      If avsFrame<>0 Or avsBatch<>0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
      If avsRecord(request,bytes,SizeOf(NeonServiceSpriteUploadRequest))=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      *upload=request
      If *upload\slot<1 Or *upload\slot>#NEON_SERVICE_MAX_SPRITES Or *upload\pixels<1 Or *upload\width<1 Or *upload\height<1 Or *upload\width>#NEON_SERVICE_MAX_SPRITE_DIM Or *upload\height>#NEON_SERVICE_MAX_SPRITE_DIM Or (*upload\bgra<>0 And *upload\bgra<>1)
        ProcedureReturn #NEON_SERVICE_ERR_ARGS
      EndIf
      If NeonVkTargetsOwnsSprite(*upload\slot)<>0 : ProcedureReturn #NEON_SERVICE_ERR_BUSY : EndIf
      needed=*upload\width * *upload\height * 4
      If *upload\sourceBytes<needed Or *upload\pixels+needed-1<*upload\pixels : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      If InPayload(*upload\pixels,*upload\pixels+needed-1)=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      If avsSpriteClock=$7FFFFFFFFFFFFFFF : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
      rc=NeonVkPortSpriteUpload(@candidate,*upload\slot,*upload\pixels,*upload\width,*upload\height,*upload\bgra)
      If rc<>0 : ProcedureReturn rc : EndIf
      index=*upload\slot-1
      avsSprite[index]\id=candidate\id : avsSprite[index]\width=candidate\width
      avsSprite[index]\height=candidate\height : avsSprite[index]\generation=candidate\generation
      avsSpriteClock=avsSpriteClock+1 : avsSpriteHandle[index]=avsSpriteClock
      ProcedureReturn avsSpriteClock
    Case #NEON_SERVICE_SPRITE_CLEAR
      If avsFrame<>0 Or avsBatch<>0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
      If avsRecord(request,bytes,SizeOf(NeonServiceSpriteHandleRequest))=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      *handle=request : index=avsSpriteIndex(*handle\handle)
      If index<0 : ProcedureReturn #NEON_SERVICE_ERR_STALE : EndIf
      rc=NeonVkPortSpriteClear(@avsSprite[index])
      If rc=0 : avsSpriteHandle[index]=0 : EndIf
      ProcedureReturn rc
    Case #NEON_SERVICE_SPRITE_DRAW
      If avsFrame<>1 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
      If avsRecord(request,bytes,SizeOf(NeonServiceSpriteDrawRequest))=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      *draw=request
      If avsFloats(request+8,8)=0 Or avsFloats(request+48,4)=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      If (*draw\scaled<>0 And *draw\scaled<>1) Or (*draw\ignoreCamera<>0 And *draw\ignoreCamera<>1) : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      index=avsSpriteIndex(*draw\handle)
      If index<0 : ProcedureReturn #NEON_SERVICE_ERR_STALE : EndIf
      ProcedureReturn NeonVkPortSprite(@avsSprite[index],*draw\x,*draw\y,*draw\angle,*draw\scale,*draw\r,*draw\g,*draw\b,*draw\a,*draw\scaled,*draw\srcX,*draw\srcY,*draw\srcW,*draw\srcH,*draw\ignoreCamera)
    Case #NEON_SERVICE_CAMERA
      If avsFrame=2 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
      If avsRecord(request,bytes,SizeOf(NeonServiceCameraRequest))=0 Or avsFloats(request,3)=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      *camera=request
      If *camera\reserved<>0 Or *camera\zoom<=0.0 Or *camera\zoom>16.0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      ProcedureReturn NeonVkPortCamera(*camera\x,*camera\y,*camera\zoom)
    Case #NEON_SERVICE_SPRITE_BATCH_BEGIN
      If avsFrame<>1 Or avsBatch<>0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
      If avsRecord(request,bytes,SizeOf(NeonServiceSpriteHandleRequest))=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      *handle=request : index=avsSpriteIndex(*handle\handle)
      If index<0 : ProcedureReturn #NEON_SERVICE_ERR_STALE : EndIf
      rc=NeonVkPortSpriteBatchBegin(@avsSprite[index])
      If rc=0 : avsBatch=1 : EndIf
      ProcedureReturn rc
    Case #NEON_SERVICE_SPRITE_BATCH_ADD
      If avsFrame<>1 Or avsBatch<>1 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
      If avsRecord(request,bytes,SizeOf(NeonServiceSpriteBatchRequest))=0 Or avsFloats(request,9)=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      *batch=request
      If *batch\reserved<>0 Or (*batch\ignoreCamera<>0 And *batch\ignoreCamera<>1) : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      ProcedureReturn NeonVkPortSpriteBatchAdd(*batch\x,*batch\y,*batch\w,*batch\h,*batch\angle,*batch\r,*batch\g,*batch\b,*batch\a,*batch\ignoreCamera)
    Case #NEON_SERVICE_SPRITE_BATCH_END
      If avsFrame<>1 Or avsBatch<>1 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
      If avsRecord(request,bytes,0)=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      rc=NeonVkPortSpriteBatchEnd()
      If rc=0 : avsBatch=0 : Else : avsFrame=2 : EndIf
      ProcedureReturn rc
  EndSelect
  ProcedureReturn #NEON_SERVICE_ERR_ARGS
EndProcedure

; Optional mapped drawing reuses the resident port and its single GPU owner.
Procedure.i avsMappingRequest(op.i,request.i,bytes.i)
  Define *canvas.NeonServiceCanvasRequest,*clip.NeonServiceScissorRequest
  Define *box.NeonServiceMappedBoxRequest,*poly.NeonServiceMappedPolygonRequest
  Define *text.NeonServiceMappedTextRequest,*lines.NeonServiceStaticLinesRequest
  Define index.i,rc.i,count.i,needed.i
  If op=#NEON_SERVICE_CANVAS
    If avsFrame<>0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
    If avsRecord(request,bytes,16)=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    *canvas=request
    If *canvas\width<1 Or *canvas\height<1 Or *canvas\width>8192 Or *canvas\height>8192 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    rc=NeonVkTargetsBoundWidth() : count=NeonVkTargetsBoundHeight()
    If rc=0 : rc=avsLogicalW : count=avsLogicalH : EndIf
    rc=NeonVkPortCanvas(*canvas\width,*canvas\height,rc,count)
    If rc=0 : avsParticleReady=0 : EndIf
    ProcedureReturn rc
  EndIf
  If avsFrame<>1 Or avsBatch<>0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
  Select op
    Case #NEON_SERVICE_SCISSOR_SET
      If avsRecord(request,bytes,16)=0 Or avsFloats(request,4)=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      *clip=request
      rc=NeonVkPortScissorSet(*clip\x,*clip\y,*clip\w,*clip\h)
      If rc=0 : rc=NeonVkChromeError() : EndIf
    Case #NEON_SERVICE_SCISSOR_CLEAR
      If avsRecord(request,bytes,0)=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      rc=NeonVkPortScissorClear()
      If rc=0 : rc=NeonVkChromeError() : EndIf
    Case #NEON_SERVICE_BOX_MAPPED
      If avsRecord(request,bytes,48)=0 Or avsFloats(request,8)=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      *box=request
      If (*box\scaled<>0 And *box\scaled<>1) Or (*box\ignoreCamera<>0 And *box\ignoreCamera<>1) : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      rc=NeonVkPortBox(*box\x,*box\y,*box\w,*box\h,*box\r,*box\g,*box\b,*box\a,*box\scaled,*box\ignoreCamera)
    Case #NEON_SERVICE_POLYGON_MAPPED
      If avsRecord(request,bytes,64)=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      If avsFloats(request,4)=0 Or avsFloats(request+24,4)=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      *poly=request
      If (*poly\scaled<>0 And *poly\scaled<>1) Or (*poly\ignoreCamera<>0 And *poly\ignoreCamera<>1) Or (*poly\solid<>0 And *poly\solid<>1) : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      rc=NeonVkPortPolygon(*poly\x,*poly\y,*poly\rx,*poly\ry,*poly\sides,*poly\r,*poly\g,*poly\b,*poly\a,*poly\solid,*poly\scaled,*poly\ignoreCamera)
    Case #NEON_SERVICE_TEXT_MAPPED
      If avsRecord(request,bytes,56)=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      If avsFloats(request+8,2)=0 Or avsFloats(request+24,4)=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      *text=request : index=avsFontIndex(*text\font)
      If index<0 Or *text\text=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      If (*text\scaled<>0 And *text\scaled<>1) Or (*text\ignoreCamera<>0 And *text\ignoreCamera<>1) : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      If index=0
        rc=NeonVkPortText(*text\font,*text\x,*text\y,*text\text,*text\r,*text\g,*text\b,*text\a,*text\scaled,*text\ignoreCamera)
      Else
        rc=NeonVkPortFontText(@avsFont[index-1],*text\x,*text\y,*text\text,*text\r,*text\g,*text\b,*text\a,*text\scaled,*text\ignoreCamera)
      EndIf
    Case #NEON_SERVICE_STATIC_LINES
      If avsRecord(request,bytes,48)=0 Or avsFloats(request+24,4)=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      *lines=request
      If *lines\vertexCount<0 Or *lines\vertexCount>#NEON_SERVICE_MAX_STATIC_LINE_VERTICES Or *lines\limitVertices<0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      needed=*lines\vertexCount*8
      If *lines\sourceBytes<needed : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      If needed>0
        If *lines\data<1 Or (*lines\data & 3)<>0 Or *lines\data+needed-1<*lines\data : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
        If InPayload(*lines\data,*lines\data+needed-1)=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
        If avsFloats(*lines\data,*lines\vertexCount*2)=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      EndIf
      rc=NeonVkPortStaticLines(*lines\data,*lines\vertexCount,*lines\r,*lines\g,*lines\b,*lines\a,*lines\limitVertices)
    Default
      ProcedureReturn #NEON_SERVICE_ERR_ARGS
  EndSelect
  ProcedureReturn rc
EndProcedure

Procedure avsEndProfile(start.i,afterGpu.i,result.i)
  Define finish.i,total.i,gpu.i,other.i
  finish=Ticks() : total=finish-start : gpu=afterGpu-start
  other=total-gpu-avsCopyDmaTicks-avsCopyCleanTicks-avsCopyPublishTicks
  avsEndFrames=avsEndFrames+1
  If result<>0 : avsEndFailed=avsEndFailed+1 : EndIf
  avsEndTotal[0]=avsEndTotal[0]+gpu
  avsEndTotal[1]=avsEndTotal[1]+avsCopyDmaTicks
  avsEndTotal[2]=avsEndTotal[2]+avsCopyCleanTicks
  avsEndTotal[3]=avsEndTotal[3]+avsCopyPublishTicks
  avsEndTotal[4]=avsEndTotal[4]+other
  avsEndTotal[5]=avsEndTotal[5]+total
  If avsEndFrames=1 Or total>avsEndWorst[5]
    avsEndWorstFrame=avsEndFrames : avsEndWorstRc=result
    avsEndWorst[0]=gpu : avsEndWorst[1]=avsCopyDmaTicks
    avsEndWorst[2]=avsCopyCleanTicks : avsEndWorst[3]=avsCopyPublishTicks
    avsEndWorst[4]=other : avsEndWorst[5]=total
  EndIf
EndProcedure

Procedure.i VulkanNeonServiceDispatch(op.i, context.i, request.i, bytes.i)
  Define *api.NeonServiceApi, *surface.NeonServiceSurface
  Define *box.NeonServiceBoxRequest, *text.NeonServiceTextRequest
  Define *measure.NeonServiceMeasureRequest, *polygon.NeonServicePolygonRequest
  Define *font.NeonServiceFontRequest, index.i, rc.i, pixels.i
  Define *spacing.NeonServiceFontAdvanceRequest
  Define *snap.NeonServiceFontSnapRequest
  Define *controls.NeonServiceFontControlsRequest
  Define *derive.NeonServiceFontDeriveRequest
  Define *caret.NeonServiceFontCaretRequest
  Define endStart.i,endAfterGpu.i,profileIndex.i,parentFrame.i
  Define *particleLimits.NeonServiceParticleLimits,*particlePrepare.NeonServiceParticlePrepareRequest,needed.i
  If op = #NEON_SERVICE_QUERY
    If context <> 0 Or avsRecord(request, bytes, SizeOf(NeonServiceApi)) = 0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    *api = request
    *api\magic = #NEON_SERVICE_MAGIC : *api\major = #NEON_SERVICE_MAJOR : *api\minor = #NEON_SERVICE_ROLE_CARETS_MINOR
    *api\bytes = SizeOf(NeonServiceApi) : *api\flags = AvsSurfaceFlags()
    *api\maxFonts = 32 : *api\dispatch = @GraphicsServiceCall
    ProcedureReturn 0
  EndIf
  If op = #NEON_SERVICE_OPEN
    If context <> 0 Or avsRecord(request, bytes, SizeOf(NeonServiceSurface)) = 0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    If avsContext <> 0 : ProcedureReturn #NEON_SERVICE_ERR_BUSY : EndIf
    If avsEpoch >= $7FFFFFFF : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
    avsEpoch = avsEpoch + 1 : avsContext = avsEpoch
    avsReady = 0 : avsFrame = 0 : avsFontCount = 0
    avsEndFrames=0 : avsEndFailed=0 : avsEndWorstFrame=0 : avsEndWorstRc=0
    For profileIndex=0 To 5 : avsEndTotal[profileIndex]=0 : avsEndWorst[profileIndex]=0 : Next
    avsParticleReady=0 : avsParticleCount=0
    avsPreviousFont=AnvilTrueTypeSlotSelected()
    avsPreviousFontGeneration=AnvilTrueTypeSlotGeneration(avsPreviousFont)
    *surface = request
    *surface\bytes = SizeOf(NeonServiceSurface) : *surface\logicalW = 0 : *surface\logicalH = 0
    *surface\flags = 0 : *surface\maxFonts = 0
    rc=NeonVkTargetsOpen(avsContext)
    If rc=0 : rc=AvsSurfaceStart() : EndIf
    If rc = 0 : rc = NeonVkPortCanvas(avsLogicalW, avsLogicalH, avsLogicalW, avsLogicalH) : EndIf
    If rc = 0
      avsReady = 1 : avsError = 0
      *surface\logicalW = avsLogicalW : *surface\logicalH = avsLogicalH
      *surface\flags = AvsSurfaceFlags() : *surface\maxFonts = 32
    Else
      avsError = rc
    EndIf
    ; Even failed startup returns ownership: invalid surface forces checked
    ; Close in the client. A refused Close must retain this context.
    ProcedureReturn avsContext
  EndIf
  If context = 0 Or context <> avsContext : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
  If op = #NEON_SERVICE_CLOSE
    If avsRecord(request, bytes, 0) = 0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    ProcedureReturn avsClose()
  EndIf
  If op = #NEON_SERVICE_ERROR
    If avsRecord(request, bytes, 0) = 0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    ProcedureReturn avsError
  EndIf
  If avsReady = 0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
  If (op>=#NEON_SERVICE_TARGET_CREATE And op<=#NEON_SERVICE_TARGET_LIMITS) Or op=#NEON_SERVICE_TARGET_RETRO_PREPARE Or op=#NEON_SERVICE_TARGET_RETRO_DRAW
    If (op=#NEON_SERVICE_TARGET_BIND Or op=#NEON_SERVICE_TARGET_UNBIND) And avsBatch<>0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
    parentFrame=NeonVkTargetsParentFrame()
    rc=NeonVkTargetsDispatch(op,context,request,bytes,avsFrame)
    If rc=0 And op=#NEON_SERVICE_TARGET_BIND : avsFrame=0 : EndIf
    If rc=0 And op=#NEON_SERVICE_TARGET_UNBIND : avsFrame=parentFrame : EndIf
    If op=#NEON_SERVICE_TARGET_BIND Or op=#NEON_SERVICE_TARGET_UNBIND : avsParticleReady=0 : EndIf
    If rc<0 And NeonVkTargetsFailed()<>0 : avsReady=0 : EndIf
    If op=#NEON_SERVICE_TARGET_CREATE And rc>0 : avsError=0 : ProcedureReturn rc : EndIf
    If rc>0 : rc=#NEON_SERVICE_ERR_PROVIDER : EndIf
    avsError=rc : ProcedureReturn rc
  EndIf
  If op>=#NEON_SERVICE_FONT_CARET_POINT And op<=#NEON_SERVICE_FONT_TEXT_COLUMN
    If avsFrame=2 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
    If avsRecord(request,bytes,SizeOf(NeonServiceFontCaretRequest))=0 Or NeonByteSpan(request,bytes)=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    If InPayload(request,request+bytes-1)=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    *caret=request : index=avsFontIndex(*caret\font)
    If index<0 : ProcedureReturn #NEON_SERVICE_ERR_STALE : EndIf
    If *caret\textBytes<1 Or *caret\textBytes>4096 Or NeonByteSpan(*caret\text,*caret\textBytes)=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    If InPayload(*caret\text,*caret\text+*caret\textBytes-1)=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    If index=0
      rc=NeonVkServiceCaret(op,0,*caret,bytes)
    Else
      rc=NeonVkServiceCaret(op,@avsFont[index-1],*caret,bytes)
    EndIf
    If rc>0 : rc=#NEON_SERVICE_ERR_PROVIDER : EndIf
    avsError=rc : ProcedureReturn rc
  EndIf
  If op=#NEON_SERVICE_FONT_DERIVE_CREATE
    If avsFrame<>0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
    If avsRecord(request,bytes,SizeOf(NeonServiceFontDeriveRequest))=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    *derive=request : index=avsFontIndex(*derive\font)
    If index<1 Or *derive\role<0 Or *derive\role>3 Or *derive\pixels<1 Or *derive\pixels>512 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    If avsFontCount>=32 : ProcedureReturn #NEON_SERVICE_ERR_CAPACITY : EndIf
    rc=NeonVkPortFontDerive(@avsFont[avsFontCount],@avsFont[index-1],*derive\role,*derive\pixels)
    If rc<>0 : avsError=rc : ProcedureReturn rc : EndIf
    avsFontCount=avsFontCount+1 : avsError=0
    ProcedureReturn (avsContext << 16) | avsFontCount
  EndIf
  If op=#NEON_SERVICE_FONT_CONTROLS_SET
    If avsFrame<>0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
    If avsRecord(request,bytes,SizeOf(NeonServiceFontControlsRequest))=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    *controls=request : index=avsFontIndex(*controls\font)
    If index<1 Or *controls\mode<0 Or *controls\mode>2 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    rc=NeonVkPortFontSetControlMode(@avsFont[index-1],*controls\mode)
    If rc>0 : rc=#NEON_SERVICE_ERR_PROVIDER : EndIf
    avsError=rc : ProcedureReturn rc
  EndIf
  If op=#NEON_SERVICE_FONT_SNAP_SET
    If avsFrame<>0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
    If avsRecord(request,bytes,SizeOf(NeonServiceFontSnapRequest))=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    *snap=request : index=avsFontIndex(*snap\font)
    If index<1 Or *snap\enabled<0 Or *snap\enabled>1 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    rc=NeonVkPortFontSetSnapToPixel(@avsFont[index-1],*snap\enabled)
    If rc>0 : rc=#NEON_SERVICE_ERR_PROVIDER : EndIf
    avsError=rc : ProcedureReturn rc
  EndIf
  If op=#NEON_SERVICE_FONT_ADVANCE
    If avsFrame<>0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
    If avsRecord(request,bytes,SizeOf(NeonServiceFontAdvanceRequest))=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    *spacing=request : index=avsFontIndex(*spacing\font)
    If index<1 Or *spacing\advanceQ16<0 Or *spacing\advanceQ16>536870912 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    rc=NeonVkPortFontSetFixedAdvanceQ16(@avsFont[index-1],*spacing\advanceQ16)
    If rc>0 : rc=#NEON_SERVICE_ERR_PROVIDER : EndIf
    avsError=rc : ProcedureReturn rc
  EndIf
  If op>=#NEON_SERVICE_CANVAS And op<=#NEON_SERVICE_STATIC_LINES
    rc=avsMappingRequest(op,request,bytes)
    If rc>0 : rc=#NEON_SERVICE_ERR_PROVIDER : EndIf
    avsError=rc : ProcedureReturn rc
  EndIf
  If op>=#NEON_SERVICE_PARTICLE_LIMITS And op<=#NEON_SERVICE_PARTICLE_DRAW
    If (AvsSurfaceFlags() & #NEON_SERVICE_PARTICLES)=0 : ProcedureReturn #NEON_SERVICE_ERR_PROVIDER : EndIf
  EndIf
  If op=#NEON_SERVICE_PARTICLE_LIMITS
    If avsRecord(request,bytes,SizeOf(NeonServiceParticleLimits))=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    *particleLimits=request : *particleLimits\maxCount=#NEON_SERVICE_MAX_PARTICLES
    *particleLimits\recordBytes=#NEON_SERVICE_PARTICLE_RECORD_BYTES : *particleLimits\coordinateFractionBits=8
    avsError=0 : ProcedureReturn 0
  EndIf
  If op=#NEON_SERVICE_PARTICLE_PREPARE
    If avsFrame<>0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
    avsParticleReady=0
    If avsRecord(request,bytes,SizeOf(NeonServiceParticlePrepareRequest))=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    *particlePrepare=request
    If *particlePrepare\count<0 Or *particlePrepare\count>#NEON_SERVICE_MAX_PARTICLES Or *particlePrepare\sourceBytes<0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    needed=*particlePrepare\count*#NEON_SERVICE_PARTICLE_RECORD_BYTES
    If *particlePrepare\sourceBytes<needed : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    If needed>0
      If *particlePrepare\data<1 Or (*particlePrepare\data & 3)<>0 Or *particlePrepare\data+needed-1<*particlePrepare\data : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      If InPayload(*particlePrepare\data,*particlePrepare\data+needed-1)=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    EndIf
    avsParticleCameraX=NeonVkPortCameraX() : avsParticleCameraY=NeonVkPortCameraY() : avsParticleCameraZoom=NeonVkPortCameraZoom()
    rc=NeonVkChromeParticlesPrepareFloat32(*particlePrepare\data,*particlePrepare\count,avsParticleCameraX,avsParticleCameraY,avsParticleCameraZoom)
    If rc=0 : avsParticleReady=1 : avsParticleCount=*particlePrepare\count : EndIf
    avsError=rc : ProcedureReturn rc
  EndIf
  If op=#NEON_SERVICE_PARTICLE_DRAW
    If avsFrame<>1 Or avsBatch<>0 Or avsParticleReady=0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
    If avsRecord(request,bytes,0)=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    If NeonVkPortCameraX()<>avsParticleCameraX Or NeonVkPortCameraY()<>avsParticleCameraY Or NeonVkPortCameraZoom()<>avsParticleCameraZoom : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
    rc=0
    If avsParticleCount>0 : rc=NeonVkChromeParticlesDrawPrepared() : EndIf
    avsError=rc : ProcedureReturn rc
  EndIf
  If op=#NEON_SERVICE_FONT_LOAD Or op=#NEON_SERVICE_FONT_UNLOAD
    rc=avsFontBytesRequest(op,request,bytes)
    If op=#NEON_SERVICE_FONT_LOAD And rc>0 : avsError=0 : ProcedureReturn rc : EndIf
    If rc>0 : rc=#NEON_SERVICE_ERR_PROVIDER : EndIf
    avsError=rc : ProcedureReturn rc
  EndIf
  If op>=#NEON_SERVICE_SPRITE_LIMITS And op<=#NEON_SERVICE_SPRITE_BATCH_END
    rc=avsSpriteRequest(op,request,bytes)
    If op=#NEON_SERVICE_SPRITE_UPLOAD And rc>0 : avsError=0 : ProcedureReturn rc : EndIf
    If rc>0 : rc=#NEON_SERVICE_ERR_PROVIDER : EndIf
    avsError=rc : ProcedureReturn rc
  EndIf
  If op = #NEON_SERVICE_WIDTH Or op = #NEON_SERVICE_HEIGHT Or op = #NEON_SERVICE_PREPARE
    If avsFrame = 2 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
    If avsRecord(request, bytes, 16) = 0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    *measure = request
    index = avsFontIndex(*measure\font)
    If index < 0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    If op <> #NEON_SERVICE_PREPARE : ProcedureReturn avsMeasure(*measure\font, *measure\text, Bool(op = #NEON_SERVICE_HEIGHT)) : EndIf
    If avsFrame <> 0 Or *measure\text = 0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
    If index = 0
      ; Raster cache keys use the face's pixel size, not its line-box spacing.
      pixels = NeonVkChromeFontPixelHeight(*measure\font)
      If pixels < 1 Or NeonVkChromeMeasureLineHeight(*measure\font) < 1 : ProcedureReturn #NEON_SERVICE_ERR_PROVIDER : EndIf
      rc = NeonVkChromeWarmTrueTypeText(pixels, *measure\text)
      If rc >= 0 : rc = 0 : EndIf
    Else
      rc = NeonVkPortFontWarm(@avsFont[index - 1], *measure\text)
    EndIf
    If rc > 0 : rc = #NEON_SERVICE_ERR_PROVIDER : EndIf
    avsError = rc : ProcedureReturn rc
  EndIf
  Select op
    Case #NEON_SERVICE_TARGET_BEGIN_LOAD
      If avsFrame<>0 Or NeonVkTargetsBound()=0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
      If avsRecord(request,bytes,0)=0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      rc=NeonVkTargetsFrameBeginLoad()
      If rc=0 : avsFrame=1 : EndIf
    Case #NEON_SERVICE_BEGIN
      If avsFrame <> 0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
      If avsRecord(request, bytes, 16) = 0 Or avsFloats(request, 4) = 0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      If NeonVkTargetsBound()<>0 : rc=NeonVkTargetsFrameBegin(request)
      Else : rc=NeonVkChromeBegin(request) : EndIf
      If rc = 0 : avsFrame = 1 : EndIf
    Case #NEON_SERVICE_END
      If avsFrame <> 1 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
      If avsBatch<>0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
      If avsRecord(request, bytes, 0) = 0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      If NeonVkTargetsBound()<>0
        endStart=Ticks()
        rc=NeonVkTargetsFrameEnd()
        avsCopyDmaTicks=0 : avsCopyCleanTicks=0 : avsCopyPublishTicks=0
        If rc=0 : avsFrame=0 : Else : avsFrame=2 : EndIf
        avsEndProfile(endStart,Ticks(),rc)
        avsError=rc : ProcedureReturn rc
      EndIf
      avsFrame = 2
      avsCopyDmaTicks=0 : avsCopyCleanTicks=0 : avsCopyPublishTicks=0
      endStart=Ticks()
      rc = NeonVkChromeEnd()
      endAfterGpu=Ticks()
      If rc = 0
        rc = AvsSurfacePresent()
        If rc = 0 : avsFrame = 0 : EndIf
      EndIf
      avsEndProfile(endStart,endAfterGpu,rc)
    Case #NEON_SERVICE_ABORT
      If avsFrame = 0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
      If avsRecord(request, bytes, 0) = 0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      If NeonVkTargetsBound()<>0 : rc=NeonVkTargetsFrameAbort()
      Else : rc=NeonVkChromeAbort() : EndIf
      If rc = 0
        NeonVkPortSpriteFrameRetired() : avsBatch=0 : avsFrame=0
      Else
        avsFrame=2
      EndIf
    Case #NEON_SERVICE_FONT_REGISTER
      If avsFrame <> 0 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
      If avsRecord(request, bytes, 24) = 0 Or avsFontCount >= 32 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      *font = request
      rc = NeonVkPortFontBind(@avsFont[avsFontCount], *font\slot, *font\role, *font\pixels)
      If rc <> 0 : ProcedureReturn rc : EndIf
      avsFontCount = avsFontCount + 1
      ProcedureReturn (avsContext << 16) | avsFontCount
    Case #NEON_SERVICE_BOX
      If avsFrame <> 1 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
      If avsRecord(request, bytes, 32) = 0 Or avsFloats(request, 8) = 0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      *box = request
      rc = NeonVkPortBox(*box\x, *box\y, *box\w, *box\h, *box\r, *box\g, *box\b, *box\a, 1, 1)
    Case #NEON_SERVICE_TEXT
      If avsFrame <> 1 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
      If avsRecord(request, bytes, 40) = 0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      If avsFloats(request + 8, 2) = 0 Or avsFloats(request + 24, 4) = 0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      *text = request : index = avsFontIndex(*text\font)
      If index < 0 Or *text\text = 0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      If index = 0
        rc = NeonVkPortText(*text\font, *text\x, *text\y, *text\text, *text\r, *text\g, *text\b, *text\a, 1, 1)
      Else
        rc = NeonVkPortFontText(@avsFont[index - 1], *text\x, *text\y, *text\text, *text\r, *text\g, *text\b, *text\a, 1, 1)
      EndIf
    Case #NEON_SERVICE_POLYGON
      If avsFrame <> 1 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
      If avsRecord(request, bytes, 48) = 0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      If avsFloats(request, 4) = 0 Or avsFloats(request + 24, 4) = 0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      *polygon = request
      rc = NeonVkPortPolygon(*polygon\x, *polygon\y, *polygon\rx, *polygon\ry, *polygon\sides, *polygon\r, *polygon\g, *polygon\b, *polygon\a, *polygon\solid, 1, 1)
    Default
      ProcedureReturn #NEON_SERVICE_ERR_ARGS
  EndSelect
  If rc > 0 : rc = #NEON_SERVICE_ERR_PROVIDER : EndIf
  avsError = rc
  ProcedureReturn rc
EndProcedure


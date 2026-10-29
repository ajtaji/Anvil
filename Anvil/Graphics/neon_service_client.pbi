; SPDX-License-Identifier: MIT
; Pure application-side binding. Include the service API and float32 first.
; No hardware driver, native graphics context or Vulkan backend is linked here.
; Calls are serialized. A failed cleanup retains its context for an explicit retry.

Procedure.i nscUnbound(op.i,context.i,request.i,bytes.i)
  ProcedureReturn #NEON_SERVICE_ERR_UNBOUND
EndProcedure
Global nscDispatch.i=@nscUnbound,nscQuery.i=@nscUnbound
Global nscCallBusy.i
Global nscBound.i,nscContext.i,nscReady.i,nscFrame.i,nscLastError.i,nscFlags.i,nscMaxFonts.i
Global nscNativeMinor.i
Global nscBoundTarget.i,nscParentWidth.i,nscParentHeight.i,nscParentFrame.i
Global nscSurface.NeonServiceSurface

Procedure.i nscFail(code.i)
  If code>0 : code=#NEON_SERVICE_ERR_PROVIDER : EndIf
  nscLastError=code : ProcedureReturn code
EndProcedure
Procedure.i nscInvoke(op.i,request.i,bytes.i)
  Protected rc.i
  If nscCallBusy<>0 : ProcedureReturn #NEON_SERVICE_ERR_BUSY : EndIf
  nscCallBusy=1 : rc=nscDispatch(op,nscContext,request,bytes) : nscCallBusy=0
  ProcedureReturn rc
EndProcedure

Procedure.i NeonServiceError()
  ProcedureReturn nscLastError
EndProcedure
Procedure.i NeonServiceContext()
  ProcedureReturn nscContext
EndProcedure
Procedure.i NeonServiceReady()
  ProcedureReturn nscReady
EndProcedure
Procedure.i NeonServiceFrameOpen()
  ProcedureReturn Bool(nscFrame<>0)
EndProcedure
Procedure.i NeonServiceWidth()
  If nscReady=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn nscSurface\logicalW
EndProcedure
Procedure.i NeonServiceHeight()
  If nscReady=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn nscSurface\logicalH
EndProcedure
Procedure.i NeonServiceBindApi(*api.NeonServiceApi,capacity.i,requiredFlags.i)
  If nscCallBusy<>0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_BUSY) : EndIf
  If nscContext<>0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_BUSY) : EndIf
  If *api=0 Or (*api & 7)<>0 Or capacity<SizeOf(NeonServiceApi) Or requiredFlags<0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_ARGS) : EndIf
  If *api\magic<>#NEON_SERVICE_MAGIC Or *api\major<>#NEON_SERVICE_MAJOR Or *api\minor<#NEON_SERVICE_MINOR Or *api\bytes<>SizeOf(NeonServiceApi)
    ProcedureReturn nscFail(#NEON_SERVICE_ERR_ABI)
  EndIf
  If (*api\flags & requiredFlags)<>requiredFlags Or *api\maxFonts<1 Or *api\maxFonts>65535
    ProcedureReturn nscFail(#NEON_SERVICE_ERR_PROVIDER)
  EndIf
  If (requiredFlags & #NEON_SERVICE_SPRITES)<>0 And *api\minor<#NEON_SERVICE_SPRITE_MINOR
    ProcedureReturn nscFail(#NEON_SERVICE_ERR_ABI)
  EndIf
  If (requiredFlags & #NEON_SERVICE_FONT_BYTES)<>0 And *api\minor<#NEON_SERVICE_FONT_BYTES_MINOR
    ProcedureReturn nscFail(#NEON_SERVICE_ERR_ABI)
  EndIf
  If (requiredFlags & #NEON_SERVICE_PARTICLES)<>0 And *api\minor<#NEON_SERVICE_PARTICLE_MINOR
    ProcedureReturn nscFail(#NEON_SERVICE_ERR_ABI)
  EndIf
  If (requiredFlags & #NEON_SERVICE_MAPPING)<>0 And *api\minor<#NEON_SERVICE_MAPPING_MINOR
    ProcedureReturn nscFail(#NEON_SERVICE_ERR_ABI)
  EndIf
  If *api\dispatch=0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_PROVIDER) : EndIf
  If (requiredFlags & #NEON_SERVICE_FONT_SPACING)<>0 And *api\minor<#NEON_SERVICE_FONT_SPACING_MINOR
    ProcedureReturn nscFail(#NEON_SERVICE_ERR_ABI)
  EndIf
  If (requiredFlags & #NEON_SERVICE_FONT_SNAP)<>0 And *api\minor<#NEON_SERVICE_FONT_SNAP_MINOR
    ProcedureReturn nscFail(#NEON_SERVICE_ERR_ABI)
  EndIf
  If (requiredFlags & #NEON_SERVICE_FONT_CONTROLS)<>0 And *api\minor<#NEON_SERVICE_FONT_CONTROLS_MINOR
    ProcedureReturn nscFail(#NEON_SERVICE_ERR_ABI)
  EndIf
  If (requiredFlags & #NEON_SERVICE_FONT_DERIVE)<>0 And *api\minor<#NEON_SERVICE_FONT_DERIVE_MINOR
    ProcedureReturn nscFail(#NEON_SERVICE_ERR_ABI)
  EndIf
  If (requiredFlags & #NEON_SERVICE_TARGETS)<>0 And *api\minor<#NEON_SERVICE_TARGET_MINOR
    ProcedureReturn nscFail(#NEON_SERVICE_ERR_ABI)
  EndIf
  If (requiredFlags & #NEON_SERVICE_TARGET_CONTINUATION)<>0 And (*api\minor<#NEON_SERVICE_TARGET_CONTINUATION_MINOR Or (*api\flags & #NEON_SERVICE_TARGETS)=0)
    ProcedureReturn nscFail(#NEON_SERVICE_ERR_ABI)
  EndIf
  If (requiredFlags & #NEON_SERVICE_TARGET_LOAD)<>0 And (*api\minor<#NEON_SERVICE_TARGET_LOAD_MINOR Or (*api\flags & #NEON_SERVICE_TARGETS)=0)
    ProcedureReturn nscFail(#NEON_SERVICE_ERR_ABI)
  EndIf
  If (requiredFlags & #NEON_SERVICE_TARGET_RETRO)<>0 And (*api\minor<#NEON_SERVICE_TARGET_RETRO_MINOR Or (*api\flags & #NEON_SERVICE_TARGETS)=0)
    ProcedureReturn nscFail(#NEON_SERVICE_ERR_ABI)
  EndIf
  If (requiredFlags & #NEON_SERVICE_FONT_CARETS)<>0 And (*api\minor<#NEON_SERVICE_FONT_CARETS_MINOR Or (*api\flags & #NEON_SERVICE_FONT_REFS)=0)
    ProcedureReturn nscFail(#NEON_SERVICE_ERR_ABI)
  EndIf
  If (requiredFlags & #NEON_SERVICE_ROLE_CARETS)<>0 And (*api\minor<#NEON_SERVICE_ROLE_CARETS_MINOR Or (*api\flags & #NEON_SERVICE_FONT_CARETS)=0 Or (*api\flags & #NEON_SERVICE_FONT_REFS)=0)
    ProcedureReturn nscFail(#NEON_SERVICE_ERR_ABI)
  EndIf
  ; Publish the dispatch only after every advertised-version check succeeds.
  nscDispatch=*api\dispatch
  nscFlags=*api\flags : nscMaxFonts=*api\maxFonts : nscNativeMinor=*api\minor : nscBound=1
  ProcedureReturn nscFail(0)
EndProcedure
Procedure.i NeonServiceBind(services.i,requiredFlags.i)
  Protected api.NeonServiceApi,rc.i,query.i,i.i
  If nscCallBusy<>0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_BUSY) : EndIf
  If nscContext<>0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_BUSY) : EndIf
  If services=0 Or (services & 7)<>0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_ARGS) : EndIf
  If (PeekL(services)&$FFFFFFFF)<>$53564E41 Or PeekL(services+4)<>#NEON_SERVICE_ABI_MAJOR Or PeekL(services+8)<#NEON_SERVICE_ABI_MINOR Or (PeekL(services+12)&$FFFFFFFF)<=#NEON_SERVICE_SLOT
    ProcedureReturn nscFail(#NEON_SERVICE_ERR_ABI)
  EndIf
  query=PeekI(services+16+#NEON_SERVICE_SLOT*8)
  If query=0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_UNBOUND) : EndIf
  For i=0 To SizeOf(NeonServiceApi)-8 Step 8 : PokeI(@api+i,0) : Next
  nscQuery=query : nscCallBusy=1 : rc=nscQuery(#NEON_SERVICE_QUERY,0,@api,SizeOf(NeonServiceApi)) : nscCallBusy=0
  If rc<0 : ProcedureReturn nscFail(rc) : EndIf
  If rc<>0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_PROVIDER) : EndIf
  ProcedureReturn NeonServiceBindApi(@api,SizeOf(NeonServiceApi),requiredFlags)
EndProcedure
Procedure.i NeonServiceClose()
  Protected rc.i
  If nscCallBusy<>0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_BUSY) : EndIf
  If nscContext=0 : ProcedureReturn nscFail(0) : EndIf
  nscReady=0
  rc=nscInvoke(#NEON_SERVICE_CLOSE,0,0)
  If rc<>0 : ProcedureReturn nscFail(rc) : EndIf
  nscContext=0 : nscReady=0 : nscFrame=0
  nscBoundTarget=0 : nscParentWidth=0 : nscParentHeight=0 : nscParentFrame=0
  ProcedureReturn nscFail(0)
EndProcedure
Procedure.i NeonServiceOpen()
  Protected context.i,rc.i
  If nscCallBusy<>0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_BUSY) : EndIf
  If nscContext<>0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_BUSY) : EndIf
  If nscBound=0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_UNBOUND) : EndIf
  nscSurface\bytes=SizeOf(NeonServiceSurface) : nscSurface\logicalW=0 : nscSurface\logicalH=0 : nscSurface\flags=0 : nscSurface\maxFonts=0
  context=nscInvoke(#NEON_SERVICE_OPEN,@nscSurface,SizeOf(NeonServiceSurface))
  If context<1
    If context=0 : context=#NEON_SERVICE_ERR_PROVIDER : EndIf
    ProcedureReturn nscFail(context)
  EndIf
  nscContext=context : nscReady=0 : nscFrame=0
  If nscSurface\bytes<>SizeOf(NeonServiceSurface) Or nscSurface\logicalW<1 Or nscSurface\logicalW>8192 Or nscSurface\logicalH<1 Or nscSurface\logicalH>8192 Or nscSurface\flags<>nscFlags Or nscSurface\maxFonts<>nscMaxFonts
    rc=NeonServiceClose()
    If rc<>0 : ProcedureReturn rc : EndIf
    ProcedureReturn nscFail(#NEON_SERVICE_ERR_PROVIDER)
  EndIf
  nscReady=1 : ProcedureReturn nscFail(0)
EndProcedure
Procedure.i NeonServiceBegin(r.f,g.f,b.f,a.f)
  Protected request.NeonServiceColour,rc.i
  If nscCallBusy<>0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_BUSY) : EndIf
  If nscReady=0 Or nscFrame<>0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_STATE) : EndIf
  request\r=r : request\g=g : request\b=b : request\a=a
  rc=nscInvoke(#NEON_SERVICE_BEGIN,@request,SizeOf(NeonServiceColour))
  If rc=0 : nscFrame=1 : EndIf
  ProcedureReturn nscFail(rc)
EndProcedure
; Load is limited to a selected target; window continuation uses Unbind.
Procedure.i NeonServiceTargetBeginLoad()
  Protected rc.i
  If nscCallBusy<>0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_BUSY) : EndIf
  If nscReady=0 Or nscFrame<>0 Or nscBoundTarget=0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_STATE) : EndIf
  If nscNativeMinor<#NEON_SERVICE_TARGET_LOAD_MINOR Or (nscFlags & #NEON_SERVICE_TARGET_LOAD)=0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_ABI) : EndIf
  rc=nscInvoke(#NEON_SERVICE_TARGET_BEGIN_LOAD,0,0)
  If rc=0 : nscFrame=1 : EndIf
  ProcedureReturn nscFail(rc)
EndProcedure
Procedure.i NeonServiceEnd()
  Protected rc.i
  If nscCallBusy<>0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_BUSY) : EndIf
  If nscReady=0 Or nscFrame<>1 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_STATE) : EndIf
  rc=nscInvoke(#NEON_SERVICE_END,0,0)
  If rc=0 : nscFrame=0 : Else : nscFrame=2 : EndIf
  ProcedureReturn nscFail(rc)
EndProcedure
Procedure.i NeonServiceAbort()
  Protected rc.i
  If nscCallBusy<>0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_BUSY) : EndIf
  If nscContext=0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_STATE) : EndIf
  If nscFrame=0 : ProcedureReturn nscFail(0) : EndIf
  rc=nscInvoke(#NEON_SERVICE_ABORT,0,0)
  If rc=0 : nscFrame=0 : Else : nscFrame=2 : EndIf
  ProcedureReturn nscFail(rc)
EndProcedure
Procedure.i NeonServiceBox(x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
  Protected request.NeonServiceBoxRequest,rc.i
  If nscCallBusy<>0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_BUSY) : EndIf
  If nscReady=0 Or nscFrame<>1 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_STATE) : EndIf
  request\x=x : request\y=y : request\w=w : request\h=h : request\r=r : request\g=g : request\b=b : request\a=a
  rc=nscInvoke(#NEON_SERVICE_BOX,@request,SizeOf(NeonServiceBoxRequest))
  ProcedureReturn nscFail(rc)
EndProcedure
Procedure.i NeonServiceText(font.i,x.f,y.f,*text,r.f,g.f,b.f,a.f)
  Protected request.NeonServiceTextRequest,rc.i
  If nscCallBusy<>0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_BUSY) : EndIf
  If nscReady=0 Or nscFrame<>1 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_STATE) : EndIf
  request\font=font : request\x=x : request\y=y : request\text=*text : request\r=r : request\g=g : request\b=b : request\a=a
  rc=nscInvoke(#NEON_SERVICE_TEXT,@request,SizeOf(NeonServiceTextRequest))
  ProcedureReturn nscFail(rc)
EndProcedure
Procedure.i NeonServicePolygon(x.f,y.f,rx.f,ry.f,sides.i,r.f,g.f,b.f,a.f,solid.i)
  Protected request.NeonServicePolygonRequest,rc.i
  If nscCallBusy<>0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_BUSY) : EndIf
  If nscReady=0 Or nscFrame<>1 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_STATE) : EndIf
  request\x=x : request\y=y : request\rx=rx : request\ry=ry : request\sides=sides : request\r=r : request\g=g : request\b=b : request\a=a : request\solid=solid
  rc=nscInvoke(#NEON_SERVICE_POLYGON,@request,SizeOf(NeonServicePolygonRequest))
  ProcedureReturn nscFail(rc)
EndProcedure
Procedure.f NeonServiceTextWidth(font.i,*text)
  Protected request.NeonServiceMeasureRequest,value.f,metric.i
  If nscCallBusy<>0 : nscFail(#NEON_SERVICE_ERR_BUSY) : ProcedureReturn -1.0 : EndIf
  If nscReady=0 : nscFail(#NEON_SERVICE_ERR_STATE) : ProcedureReturn -1.0 : EndIf
  request\font=font : request\text=*text
  metric=nscInvoke(#NEON_SERVICE_WIDTH,@request,SizeOf(NeonServiceMeasureRequest))
  If metric<0 : nscFail(metric) : ProcedureReturn -1.0 : EndIf
  value=MathFFromInt(metric)/65536.0
  nscFail(0) : ProcedureReturn value
EndProcedure
Procedure.f NeonServiceLineHeight(font.i)
  Protected request.NeonServiceMeasureRequest,value.f,metric.i
  If nscCallBusy<>0 : nscFail(#NEON_SERVICE_ERR_BUSY) : ProcedureReturn -1.0 : EndIf
  If nscReady=0 : nscFail(#NEON_SERVICE_ERR_STATE) : ProcedureReturn -1.0 : EndIf
  request\font=font : request\text=0
  metric=nscInvoke(#NEON_SERVICE_HEIGHT,@request,SizeOf(NeonServiceMeasureRequest))
  If metric<0 : nscFail(metric) : ProcedureReturn -1.0 : EndIf
  value=MathFFromInt(metric)/65536.0
  nscFail(0) : ProcedureReturn value
EndProcedure
Procedure.i NeonServicePrepare(font.i,*text)
  Protected request.NeonServiceMeasureRequest,rc.i
  If nscCallBusy<>0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_BUSY) : EndIf
  If nscReady=0 Or nscFrame<>0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_STATE) : EndIf
  request\font=font : request\text=*text
  rc=nscInvoke(#NEON_SERVICE_PREPARE,@request,SizeOf(NeonServiceMeasureRequest))
  ProcedureReturn nscFail(rc)
EndProcedure
Procedure.i NeonServiceFontRegister(slot.i,role.i,pixels.i)
  Protected request.NeonServiceFontRequest,font.i
  If nscCallBusy<>0 : nscFail(#NEON_SERVICE_ERR_BUSY) : ProcedureReturn 0 : EndIf
  If nscReady=0 Or nscFrame<>0 : nscFail(#NEON_SERVICE_ERR_STATE) : ProcedureReturn 0 : EndIf
  request\slot=slot : request\role=role : request\pixels=pixels
  font=nscInvoke(#NEON_SERVICE_FONT_REGISTER,@request,SizeOf(NeonServiceFontRequest))
  If font<0 : nscFail(font) : ProcedureReturn 0 : EndIf
  If font<=3 : nscFail(#NEON_SERVICE_ERR_PROVIDER) : ProcedureReturn 0 : EndIf
  nscFail(0) : ProcedureReturn font
EndProcedure

Procedure.i NeonServiceUnbind()
  If nscCallBusy<>0 Or nscContext<>0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_BUSY) : EndIf
  nscBound=0 : nscFlags=0 : nscMaxFonts=0 : nscNativeMinor=0
  ProcedureReturn nscFail(0)
EndProcedure
Procedure.i NeonServiceProviderError()
  Protected rc.i
  If nscCallBusy<>0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_BUSY) : EndIf
  If nscContext=0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_STATE) : EndIf
  rc=nscInvoke(#NEON_SERVICE_ERROR,0,0)
  ProcedureReturn nscFail(rc)
EndProcedure

; Versioned feature clients use this boundary instead of borrowing private
; dispatcher/state globals. Extension operations cannot open/close a context.
; phase -1 permits idle/recording, 0 requires idle, 1 requires recording.
Procedure.i NeonServiceRequestExtension(op.i,request.i,bytes.i,phase.i,requiredFlags.i,requiredMinor.i,retainOnFailure.i)
  Protected rc.i
  If nscCallBusy<>0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_BUSY) : EndIf
  If nscReady=0 Or nscFrame=2 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_STATE) : EndIf
  If op<14 Or phase < -1 Or phase>1 Or requiredFlags<0 Or requiredMinor<0 Or bytes<0
    ProcedureReturn nscFail(#NEON_SERVICE_ERR_ARGS)
  EndIf
  If (nscFlags & requiredFlags)<>requiredFlags Or nscNativeMinor<requiredMinor
    ProcedureReturn nscFail(#NEON_SERVICE_ERR_ABI)
  EndIf
  If phase=0 And nscFrame<>0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_STATE) : EndIf
  If phase=1 And nscFrame<>1 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_STATE) : EndIf
  If bytes=0
    If request<>0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_ARGS) : EndIf
  Else
    If request=0 Or (request & 7)<>0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_ARGS) : EndIf
  EndIf
  rc=nscInvoke(op,request,bytes)
  If rc<>0 And retainOnFailure<>0 : nscFrame=2 : EndIf
  If rc<0 : ProcedureReturn nscFail(rc) : EndIf
  nscFail(0) : ProcedureReturn rc
EndProcedure

Procedure.i NeonServiceExtensionStatus(status.i)
  ProcedureReturn nscFail(status)
EndProcedure

; A bound target is an idle scope. A capable provider can first suspend an
; open window frame; Unbind restores that recording phase after child End or
; Abort. Providers with only minor 9 still support idle binding unchanged.
Procedure.i NeonServiceTargetBind(handle.i)
  Protected request.NeonServiceTargetBindRequest,rc.i,required.i,minor.i,parent.i
  If handle<1 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_ARGS) : EndIf
  If nscBoundTarget<>0 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_STATE) : EndIf
  request\handle=handle : request\width=0 : request\height=0
  parent=nscFrame : required=#NEON_SERVICE_TARGETS : minor=#NEON_SERVICE_TARGET_MINOR
  If parent=1
    required=required | #NEON_SERVICE_TARGET_CONTINUATION : minor=#NEON_SERVICE_TARGET_CONTINUATION_MINOR
  EndIf
  rc=NeonServiceRequestExtension(#NEON_SERVICE_TARGET_BIND,@request,SizeOf(NeonServiceTargetBindRequest),-1,required,minor,0)
  If rc<>0
    If rc=#NEON_SERVICE_ERR_PROVIDER : nscFrame=2 : EndIf
    ProcedureReturn nscFail(rc)
  EndIf
  nscParentFrame=parent : nscFrame=0
  nscBoundTarget=handle
  nscParentWidth=nscSurface\logicalW : nscParentHeight=nscSurface\logicalH
  If request\width<1 Or request\height<1 Or request\width>#NEON_SERVICE_TARGET_DIMENSION Or request\height>#NEON_SERVICE_TARGET_DIMENSION
    nscFrame=2 : ProcedureReturn nscFail(#NEON_SERVICE_ERR_PROVIDER)
  EndIf
  nscSurface\logicalW=request\width : nscSurface\logicalH=request\height
  ProcedureReturn nscFail(0)
EndProcedure
Procedure.i NeonServiceTargetUnbind(handle.i)
  Protected request.NeonServiceSpriteHandleRequest,rc.i
  If handle<1 Or nscBoundTarget<>handle : ProcedureReturn nscFail(#NEON_SERVICE_ERR_STATE) : EndIf
  request\handle=handle
  rc=NeonServiceRequestExtension(#NEON_SERVICE_TARGET_UNBIND,@request,SizeOf(NeonServiceSpriteHandleRequest),0,#NEON_SERVICE_TARGETS,#NEON_SERVICE_TARGET_MINOR,0)
  If rc<>0
    If rc=#NEON_SERVICE_ERR_PROVIDER : nscFrame=2 : EndIf
    ProcedureReturn nscFail(rc)
  EndIf
  nscFrame=nscParentFrame
  nscSurface\logicalW=nscParentWidth : nscSurface\logicalH=nscParentHeight
  nscBoundTarget=0 : nscParentWidth=0 : nscParentHeight=0 : nscParentFrame=0
  ProcedureReturn nscFail(0)
EndProcedure

; SPDX-License-Identifier: MIT
; Retained Neon controls. Caller owns arena, renderer, frame and font lifetimes.
; Text is copied into the arena; handles become stale on Reset/Configure.
; Enable floating point before inclusion. Calls are serialized; event handlers
; may reset/rebuild UI, but may not reenter input, preparation or drawing.
XIncludeFile "Anvil/Math/float32.pbi"

#NRU_OK = 0
#NRU_ERR_CONFIG = -21400
#NRU_ERR_ARGS = -21401
#NRU_ERR_CAPACITY = -21402
#NRU_ERR_STALE = -21403
#NRU_ERR_RENDERER = -21404
#NRU_ERR_BUSY = -21405
#NRU_ERR_TEXT = -21406
#NRU_ERR_HANDLER = -21407
#NRU_ERR_METRICS = -21408
#NRU_ERR_GENERATION = -21409
#NRU_BUTTON = 0
#NRU_SLIDER = 2
#NRU_TOGGLE = 3
#NRU_METER = 4
#NRU_LABEL = 5
#NRU_BREADCRUMB = 6
#NRU_DIPBANK = 7
#NRU_CAROUSEL = 8
#NRU_MAX_GADGETS = 65535 ; nonzero low sixteen handle bits
#NRU_MAX_TEXT = 4096    ; includes the terminating byte

Structure NeonRetainedGadget Align #PB_Structure_AlignC
  id.i : kind.i : style.i : font.i : eventTag.i
  x.f : y.f : w.f : h.f : value.f : hoverAlpha.f : focusPulse.f
  isActive.i : isHovered.i : isFocused.i : subFocus.i
  text.i
EndStructure

Global nruArena.i, nruCapacity.i, nruTextBytes.i, nruCount.i, nruEpoch.i
Global nruError.i, nruFont.i = -1
; Renderer return values own the draw verdict; a handled refused callback
; mutation may update last-error without silently truncating the draw.
Global nruDrawError.i
Global nruFocus.i, nruInputBusy.i, nruCallbackBusy.i, nruDrawBusy.i, nruPrepareBusy.i, nruMutationBusy.i
Global nruPointerDown.i
Global nruViewportX.f, nruViewportY.f, nruViewportW.f, nruViewportH.f
Global nruCanvasW.f, nruCanvasH.f, nruMouseX.f, nruMouseY.f
Global nruEventPending.i, nruEventId.i, nruEventType.i, nruEventTag.i
Global Dim nruScratch.a[#NRU_MAX_TEXT]
Global Dim nruDigits.a[4]
Global Dim nruLeft.a[2]
Global Dim nruRight.a[2]

Procedure.i nruFail(code.i)
  nruError = code : ProcedureReturn code
EndProcedure

Procedure.i nruFinite(value.f)
  ProcedureReturn Bool((MathBitsOf(value) & $7F800000) <> $7F800000)
EndProcedure

Procedure.i nruBoxUnbound(x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
  ProcedureReturn #NRU_ERR_RENDERER
EndProcedure
Procedure.i nruTextUnbound(font.i,x.f,y.f,*text,r.f,g.f,b.f,a.f)
  ProcedureReturn #NRU_ERR_RENDERER
EndProcedure
Procedure.f nruWidthUnbound(font.i,*text)
  ProcedureReturn -1.0
EndProcedure
Procedure.f nruHeightUnbound(font.i)
  ProcedureReturn -1.0
EndProcedure
Procedure.i nruPolygonUnbound(x.f,y.f,rx.f,ry.f,sides.i,r.f,g.f,b.f,a.f,solid.i)
  ProcedureReturn #NRU_ERR_RENDERER
EndProcedure
Procedure.i nruPrepareUnbound(font.i,*text)
  ProcedureReturn #NRU_ERR_RENDERER
EndProcedure
Procedure nruEventUnbound(id.i,eventType.i,tag.i)
EndProcedure
Global nruBox.i = @nruBoxUnbound
Global nruText.i = @nruTextUnbound
Global nruWidth.i = @nruWidthUnbound
Global nruHeight.i = @nruHeightUnbound
Global nruPolygon.i = @nruPolygonUnbound
Global nruPrepare.i = @nruPrepareUnbound
Global nruHandler.i = @nruEventUnbound
Global nruRendererActive.i, nruHandlerActive.i

Procedure.i NeonRetainedError()
  ProcedureReturn nruError
EndProcedure

Procedure.i nruMutable()
  If nruDrawBusy <> 0 Or nruPrepareBusy <> 0 Or nruMutationBusy <> 0 : ProcedureReturn 0 : EndIf
  If nruInputBusy <> 0 And nruCallbackBusy = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

; Adapter-owned CPU configuration follows the same mutation boundary as
; controls. Callback-driven screen rebuilding is allowed; renderer reentry is not.
Procedure.i NeonRetainedMutationAllowed()
  ProcedureReturn nruMutable()
EndProcedure

Procedure.i NeonRetainedRendererInstall(boxProc.i,textProc.i,widthProc.i,heightProc.i,polygonProc.i,prepareProc.i)
  If nruDrawBusy <> 0 Or nruInputBusy <> 0 Or nruPrepareBusy <> 0 Or nruMutationBusy <> 0 : ProcedureReturn nruFail(#NRU_ERR_BUSY) : EndIf
  If boxProc = 0 Or textProc = 0 Or widthProc = 0 Or heightProc = 0 Or polygonProc = 0 Or prepareProc = 0
    ProcedureReturn nruFail(#NRU_ERR_ARGS)
  EndIf
  nruBox=boxProc : nruText=textProc : nruWidth=widthProc : nruHeight=heightProc
  nruPolygon=polygonProc : nruPrepare=prepareProc : nruRendererActive=1
  ProcedureReturn nruFail(#NRU_OK)
EndProcedure

Procedure.i NeonRetainedEventHandlerInstall(proc.i)
  If nruMutable() = 0 : ProcedureReturn nruFail(#NRU_ERR_BUSY) : EndIf
  If proc = 0
    nruHandler=@nruEventUnbound : nruHandlerActive=0
  Else
    nruHandler=proc : nruHandlerActive=1
  EndIf
  ProcedureReturn nruFail(#NRU_OK)
EndProcedure

Procedure.i NeonRetainedRequiredBytes(capacity.i,textBytes.i)
  If capacity < 1 Or capacity > #NRU_MAX_GADGETS Or textBytes < 1 Or textBytes > #NRU_MAX_TEXT
    ProcedureReturn 0
  EndIf
  ProcedureReturn capacity * (SizeOf(NeonRetainedGadget) + textBytes)
EndProcedure

Procedure.i NeonRetainedReset()
  If nruMutable() = 0 : ProcedureReturn nruFail(#NRU_ERR_BUSY) : EndIf
  If nruEpoch >= $7FFFFFFF : ProcedureReturn nruFail(#NRU_ERR_GENERATION) : EndIf
  nruEpoch=nruEpoch+1 : nruCount=0 : nruFocus=0 : nruEventPending=0 : nruPointerDown=0
  ProcedureReturn nruFail(#NRU_OK)
EndProcedure

Procedure.i NeonRetainedConfigure(arena.i,bytes.i,capacity.i,textBytes.i)
  Protected needed.i=NeonRetainedRequiredBytes(capacity,textBytes)
  If nruMutable() = 0 : ProcedureReturn nruFail(#NRU_ERR_BUSY) : EndIf
  If needed=0 Or arena<1 Or (arena & 7)<>0 Or bytes<needed Or arena+needed<arena
    ProcedureReturn nruFail(#NRU_ERR_ARGS)
  EndIf
  If nruEpoch >= $7FFFFFFF : ProcedureReturn nruFail(#NRU_ERR_GENERATION) : EndIf
  nruArena=arena : nruCapacity=capacity : nruTextBytes=textBytes
  ProcedureReturn NeonRetainedReset()
EndProcedure

Procedure.i NeonRetainedViewport(x.f,y.f,w.f,h.f,canvasW.f,canvasH.f)
  If nruMutable() = 0 : ProcedureReturn nruFail(#NRU_ERR_BUSY) : EndIf
  If nruFinite(x)=0 Or nruFinite(y)=0 Or nruFinite(w)=0 Or nruFinite(h)=0 Or nruFinite(canvasW)=0 Or nruFinite(canvasH)=0
    ProcedureReturn nruFail(#NRU_ERR_ARGS)
  EndIf
  If w<=0.0 Or h<=0.0 Or canvasW<=0.0 Or canvasH<=0.0 Or canvasW>8192.0 Or canvasH>8192.0
    ProcedureReturn nruFail(#NRU_ERR_ARGS)
  EndIf
  nruViewportX=x : nruViewportY=y : nruViewportW=w : nruViewportH=h
  nruCanvasW=canvasW : nruCanvasH=canvasH
  ProcedureReturn nruFail(#NRU_OK)
EndProcedure

Procedure.i NeonRetainedFontSet(font.i)
  If nruMutable()=0 : ProcedureReturn nruFail(#NRU_ERR_BUSY) : EndIf
  If font < -1 : ProcedureReturn nruFail(#NRU_ERR_ARGS) : EndIf
  nruFont=font : ProcedureReturn nruFail(#NRU_OK)
EndProcedure

Procedure.i NeonRetainedCount()
  ProcedureReturn nruCount
EndProcedure

Procedure.i NeonRetainedHandleAt(index.i)
  If index<0 Or index>=nruCount : nruFail(#NRU_ERR_STALE) : ProcedureReturn 0 : EndIf
  ProcedureReturn (nruEpoch << 16) | (index+1)
EndProcedure

; Borrowed read-only record, valid only until the next UI mutation.
Procedure.i NeonRetainedGet(handle.i)
  Protected index.i=(handle & $FFFF)-1
  If nruArena=0 Or handle<1 Or (handle >> 16)<>nruEpoch Or index<0 Or index>=nruCount
    nruFail(#NRU_ERR_STALE) : ProcedureReturn 0
  EndIf
  ProcedureReturn nruArena+index*SizeOf(NeonRetainedGadget)
EndProcedure

Procedure.i nruLength(*text)
  Protected i.i
  If *text=0 : ProcedureReturn 0 : EndIf
  For i=0 To nruTextBytes-1
    If PeekA(*text+i)=0 : ProcedureReturn i : EndIf
  Next
  ProcedureReturn -1
EndProcedure

Procedure.i nruOptions(*text)
  Protected i.i,n.i=1
  For i=0 To nruTextBytes-1
    If PeekA(*text+i)=0 : Break : EndIf
    If PeekA(*text+i)=124 : n=n+1 : EndIf
  Next
  ProcedureReturn n
EndProcedure

Procedure.i nruAdd(kind.i,id.i,x.f,y.f,w.f,h.f,*text,value.f,active.i,style.i,tag.i)
  Protected length.i,i.i,dst.i,options.i
  Protected width.f,oldW.f
  Protected *g.NeonRetainedGadget
  If nruMutable()=0 : nruFail(#NRU_ERR_BUSY) : ProcedureReturn 0 : EndIf
  If nruArena=0 : nruFail(#NRU_ERR_CONFIG) : ProcedureReturn 0 : EndIf
  If nruCount>=nruCapacity : nruFail(#NRU_ERR_CAPACITY) : ProcedureReturn 0 : EndIf
  If nruFinite(x)=0 Or nruFinite(y)=0 Or nruFinite(w)=0 Or nruFinite(h)=0 Or nruFinite(value)=0
    nruFail(#NRU_ERR_ARGS) : ProcedureReturn 0
  EndIf
  If (kind<>#NRU_LABEL And kind<>#NRU_BREADCRUMB) And (w<=0.0 Or h<=0.0)
    nruFail(#NRU_ERR_ARGS) : ProcedureReturn 0
  EndIf
  length=nruLength(*text)
  If length<0 : nruFail(#NRU_ERR_TEXT) : ProcedureReturn 0 : EndIf
  If (kind=#NRU_SLIDER Or kind=#NRU_METER) And (value<0.0 Or value>1.0)
    nruFail(#NRU_ERR_ARGS) : ProcedureReturn 0
  EndIf
  If kind=#NRU_DIPBANK And (value<1.0 Or value>64.0)
    nruFail(#NRU_ERR_ARGS) : ProcedureReturn 0
  EndIf
  If kind=#NRU_CAROUSEL
    options=1
    If *text<>0 : options=nruOptions(*text) : EndIf
    If value<0.0 Or value>=MathFFromInt(options) Or value<>MathFFromInt(Int(value))
      nruFail(#NRU_ERR_ARGS) : ProcedureReturn 0
    EndIf
  EndIf
  nruMutationBusy=1
  If nruFont>=0 And (kind=#NRU_BUTTON Or kind=#NRU_TOGGLE Or kind=#NRU_DIPBANK Or (kind=#NRU_SLIDER And length>0))
    If nruRendererActive=0 : nruMutationBusy=0 : nruFail(#NRU_ERR_RENDERER) : ProcedureReturn 0 : EndIf
    width=nruWidth(nruFont,*text)
    If nruFinite(width)=0 Or width<0.0 : nruMutationBusy=0 : nruFail(#NRU_ERR_METRICS) : ProcedureReturn 0 : EndIf
    If kind=#NRU_BUTTON : width=width+40.0 : EndIf
    If kind=#NRU_TOGGLE : width=width+80.0 : EndIf
    If w<width : oldW=w : w=width : x=x-(w-oldW)/2.0 : EndIf
  EndIf
  ; A finite metric/coordinate can still overflow during recentering or
  ; extent calculation. Refuse before publishing or copying a partial record.
  If nruFinite(x)=0 Or nruFinite(y)=0 Or nruFinite(w)=0 Or nruFinite(h)=0 Or nruFinite(x+w)=0 Or nruFinite(y+h)=0
    nruMutationBusy=0 : nruFail(#NRU_ERR_ARGS) : ProcedureReturn 0
  EndIf
  *g=nruArena+nruCount*SizeOf(NeonRetainedGadget)
  dst=nruArena+nruCapacity*SizeOf(NeonRetainedGadget)+nruCount*nruTextBytes
  For i=0 To length-1 : PokeA(dst+i,PeekA(*text+i)) : Next
  PokeA(dst+length,0)
  *g\id=id : *g\kind=kind : *g\style=style : *g\font=nruFont : *g\eventTag=tag
  *g\x=x : *g\y=y : *g\w=w : *g\h=h : *g\value=value
  *g\hoverAlpha=0.0 : *g\focusPulse=0.0 : *g\isActive=active
  *g\isHovered=0 : *g\isFocused=0 : *g\subFocus=0 : *g\text=dst
  nruCount=nruCount+1 : nruMutationBusy=0 : nruError=#NRU_OK
  ProcedureReturn (nruEpoch << 16) | nruCount
EndProcedure

Procedure.i NeonRetainedAddLabel(id.i,x.f,y.f,*text)
  ProcedureReturn nruAdd(#NRU_LABEL,id,x,y,0.0,0.0,*text,0.0,0,0,0)
EndProcedure
Procedure.i NeonRetainedAddBreadcrumb(id.i,x.f,y.f,*text)
  ProcedureReturn nruAdd(#NRU_BREADCRUMB,id,x,y,0.0,0.0,*text,0.0,0,0,0)
EndProcedure
Procedure.i NeonRetainedAddButton(id.i,x.f,y.f,w.f,h.f,*text,style.i,tag.i)
  If style<0 Or style>2 : nruFail(#NRU_ERR_ARGS) : ProcedureReturn 0 : EndIf
  ProcedureReturn nruAdd(#NRU_BUTTON,id,x,y,w,h,*text,0.0,0,style,tag)
EndProcedure
Procedure.i NeonRetainedAddSlider(id.i,x.f,y.f,w.f,h.f,value.f,*text,tag.i)
  ProcedureReturn nruAdd(#NRU_SLIDER,id,x,y,w,h,*text,value,0,0,tag)
EndProcedure
Procedure.i NeonRetainedAddToggle(id.i,x.f,y.f,w.f,h.f,*text,active.i,tag.i)
  If active<>0 And active<>1 : nruFail(#NRU_ERR_ARGS) : ProcedureReturn 0 : EndIf
  ProcedureReturn nruAdd(#NRU_TOGGLE,id,x,y,w,h,*text,0.0,active,0,tag)
EndProcedure
Procedure.i NeonRetainedAddMeter(id.i,x.f,y.f,w.f,h.f,value.f,*text)
  ProcedureReturn nruAdd(#NRU_METER,id,x,y,w,h,*text,value,0,0,0)
EndProcedure
Procedure.i NeonRetainedAddDipBank(id.i,x.f,y.f,switches.i,mask.i,*text,tag.i)
  If switches<1 Or switches>64 : nruFail(#NRU_ERR_ARGS) : ProcedureReturn 0 : EndIf
  ProcedureReturn nruAdd(#NRU_DIPBANK,id,x,y,MathFFromInt(switches)*40.0+20.0,70.0,*text,MathFFromInt(switches),mask,0,tag)
EndProcedure
Procedure.i NeonRetainedAddCarousel(id.i,x.f,y.f,w.f,h.f,*options,index.i,tag.i)
  ProcedureReturn nruAdd(#NRU_CAROUSEL,id,x,y,w,h,*options,MathFFromInt(index),0,0,tag)
EndProcedure

Procedure.i NeonRetainedGadgetFontSet(handle.i,font.i)
  Protected *g.NeonRetainedGadget
  If nruMutable()=0 : ProcedureReturn nruFail(#NRU_ERR_BUSY) : EndIf
  *g=NeonRetainedGet(handle) : If *g=0 : ProcedureReturn nruError : EndIf
  If font < -1 : ProcedureReturn nruFail(#NRU_ERR_ARGS) : EndIf
  *g\font=font : ProcedureReturn nruFail(#NRU_OK)
EndProcedure

Procedure.i NeonRetainedValueSet(handle.i,value.f)
  Protected *g.NeonRetainedGadget
  If nruMutable()=0 : ProcedureReturn nruFail(#NRU_ERR_BUSY) : EndIf
  *g=NeonRetainedGet(handle) : If *g=0 : ProcedureReturn nruError : EndIf
  If nruFinite(value)=0 : ProcedureReturn nruFail(#NRU_ERR_ARGS) : EndIf
  If *g\kind=#NRU_SLIDER Or *g\kind=#NRU_METER
    If value<0.0 Or value>1.0 : ProcedureReturn nruFail(#NRU_ERR_ARGS) : EndIf
  ElseIf *g\kind=#NRU_CAROUSEL
    If value<0.0 Or value>=MathFFromInt(nruOptions(*g\text)) Or value<>MathFFromInt(Int(value)) : ProcedureReturn nruFail(#NRU_ERR_ARGS) : EndIf
  Else
    ProcedureReturn nruFail(#NRU_ERR_ARGS)
  EndIf
  *g\value=value : ProcedureReturn nruFail(#NRU_OK)
EndProcedure

Procedure.i NeonRetainedActiveSet(handle.i,value.i)
  Protected *g.NeonRetainedGadget
  If nruMutable()=0 : ProcedureReturn nruFail(#NRU_ERR_BUSY) : EndIf
  *g=NeonRetainedGet(handle) : If *g=0 : ProcedureReturn nruError : EndIf
  If *g\kind<>#NRU_DIPBANK And (value<>0 And value<>1) : ProcedureReturn nruFail(#NRU_ERR_ARGS) : EndIf
  *g\isActive=value : ProcedureReturn nruFail(#NRU_OK)
EndProcedure

Procedure.i NeonRetainedTextSet(handle.i,*text)
  Protected *g.NeonRetainedGadget
  Protected length.i,i.i
  If nruMutable()=0 : ProcedureReturn nruFail(#NRU_ERR_BUSY) : EndIf
  *g=NeonRetainedGet(handle) : If *g=0 : ProcedureReturn nruError : EndIf
  length=nruLength(*text) : If length<0 : ProcedureReturn nruFail(#NRU_ERR_TEXT) : EndIf
  For i=0 To length-1 : PokeA(*g\text+i,PeekA(*text+i)) : Next
  PokeA(*g\text+length,0)
  If *g\kind=#NRU_CAROUSEL And *g\value>=MathFFromInt(nruOptions(*g\text)) : *g\value=0.0 : EndIf
  ProcedureReturn nruFail(#NRU_OK)
EndProcedure

Procedure.i NeonRetainedEventGet(*idOut,*typeOut,*tagOut)
  If nruEventPending=0 : ProcedureReturn 0 : EndIf
  If *idOut<>0 : PokeI(*idOut,nruEventId) : EndIf
  If *typeOut<>0 : PokeI(*typeOut,nruEventType) : EndIf
  If *tagOut<>0 : PokeI(*tagOut,nruEventTag) : EndIf
  nruEventPending=0 : ProcedureReturn 1
EndProcedure

Procedure.i nruNotify(*g.NeonRetainedGadget)
  Protected id.i=*g\id,tag.i=*g\eventTag
  nruEventId=id : nruEventType=1 : nruEventTag=tag : nruEventPending=1
  If tag=0 Or nruHandlerActive=0 : ProcedureReturn 0 : EndIf
  nruCallbackBusy=1 : nruHandler(id,1,tag) : nruCallbackBusy=0
  ; The handler may have replaced every record. Never touch *g again.
  ProcedureReturn 1
EndProcedure

; Read-only hit identity for pointer adapters. Returning an epoch handle lets a
; captured press reject a release against a rebuilt screen or another control.
Procedure.i NeonRetainedHit(mouseX.f,mouseY.f)
  Protected x.f,y.f,i.i,hit.i
  Protected *g.NeonRetainedGadget
  If nruArena=0 Or nruViewportW<=0.0 Or nruViewportH<=0.0 : ProcedureReturn 0 : EndIf
  If nruFinite(mouseX)=0 Or nruFinite(mouseY)=0 : ProcedureReturn 0 : EndIf
  x=(mouseX-nruViewportX)*(nruCanvasW/nruViewportW)
  y=(mouseY-nruViewportY)*(nruCanvasH/nruViewportH)
  If nruFinite(x)=0 Or nruFinite(y)=0 : ProcedureReturn 0 : EndIf
  For i=0 To nruCount-1
    *g=nruArena+i*SizeOf(NeonRetainedGadget)
    If *g\kind<>#NRU_LABEL And *g\kind<>#NRU_BREADCRUMB
      If x<*g\x+*g\w And x+1.0>*g\x And y<*g\y+*g\h And y+1.0>*g\y
        hit=(nruEpoch << 16) | (i+1)
      EndIf
    EndIf
  Next
  ProcedureReturn hit
EndProcedure

Procedure.i NeonRetainedUpdateInput(mouseX.f,mouseY.f,mouseDown.i,mouseReleased.i,dpadX.i,dpadY.i,action.i)
  Protected i.i,steps.i,count.i,bit.i,notified.i,pressEdge.i,hover.i
  Protected left.f,local.f,mappedX.f,mappedY.f
  Protected *g.NeonRetainedGadget
  If nruInputBusy<>0 Or nruDrawBusy<>0 Or nruPrepareBusy<>0 Or nruMutationBusy<>0 : ProcedureReturn nruFail(#NRU_ERR_BUSY) : EndIf
  If nruArena=0 Or nruViewportW<=0.0 Or nruViewportH<=0.0 : ProcedureReturn nruFail(#NRU_ERR_CONFIG) : EndIf
  If nruFinite(mouseX)=0 Or nruFinite(mouseY)=0 Or dpadX < -1 Or dpadX>1 Or dpadY < -1 Or dpadY>1 : ProcedureReturn nruFail(#NRU_ERR_ARGS) : EndIf
  ; Form the scale ratio first, and validate the derived coordinates before any
  ; hover/focus/state change. Finite inputs alone do not guarantee this.
  mappedX=(mouseX-nruViewportX)*(nruCanvasW/nruViewportW)
  mappedY=(mouseY-nruViewportY)*(nruCanvasH/nruViewportH)
  If nruFinite(mappedX)=0 Or nruFinite(mappedY)=0 : ProcedureReturn nruFail(#NRU_ERR_ARGS) : EndIf
  nruError=0 : nruInputBusy=1
  pressEdge=Bool(mouseDown<>0 And nruPointerDown=0)
  nruPointerDown=Bool(mouseDown<>0)
  hover=NeonRetainedHit(mouseX,mouseY)
  nruMouseX=mappedX : nruMouseY=mappedY
  If dpadY<>0 And nruCount>0
    steps=0
    Repeat
      nruFocus=nruFocus+dpadY
      If nruFocus<0 : nruFocus=nruCount-1 : EndIf
      If nruFocus>=nruCount : nruFocus=0 : EndIf
      *g=nruArena+nruFocus*SizeOf(NeonRetainedGadget)
      steps=steps+1
    Until (*g\kind<>#NRU_LABEL And *g\kind<>#NRU_BREADCRUMB) Or steps>=nruCount
  EndIf
  For i=0 To nruCount-1
    *g=nruArena+i*SizeOf(NeonRetainedGadget) : *g\isHovered=0
    If *g\kind<>#NRU_LABEL And *g\kind<>#NRU_BREADCRUMB
      If hover=((nruEpoch << 16) | (i+1))
        *g\isHovered=1 : nruFocus=i
      EndIf
    EndIf
    If i=nruFocus And *g\kind<>#NRU_LABEL And *g\kind<>#NRU_BREADCRUMB
      *g\isFocused=1
      If dpadX<>0
        Select *g\kind
          Case #NRU_SLIDER
            *g\value=*g\value+MathFFromInt(dpadX)*0.05
            If *g\value<0.0 : *g\value=0.0 : EndIf
            If *g\value>1.0 : *g\value=1.0 : EndIf
          Case #NRU_DIPBANK
            *g\subFocus=*g\subFocus+dpadX : count=Int(*g\value)
            If *g\subFocus<0 : *g\subFocus=count-1 : EndIf
            If *g\subFocus>=count : *g\subFocus=0 : EndIf
          Case #NRU_CAROUSEL
            count=nruOptions(*g\text) : *g\value=*g\value+MathFFromInt(dpadX)
            If *g\value<0.0 : *g\value=MathFFromInt(count-1) : EndIf
            If *g\value>=MathFFromInt(count) : *g\value=0.0 : EndIf
        EndSelect
      EndIf
      If *g\isHovered<>0
        If mouseDown<>0
          Select *g\kind
            Case #NRU_DIPBANK
              count=Int(*g\value) : left=*g\x+*g\w/2.0-MathFFromInt(count)*20.0
              local=nruMouseX-left
              If local>=0.0 And local<=MathFFromInt(count)*40.0
                bit=Int(local/40.0)
                If pressEdge<>0 And bit>=0 And bit<count : *g\isActive=*g\isActive ! (1 << bit) : *g\subFocus=bit : EndIf
              EndIf
            Case #NRU_CAROUSEL
              If pressEdge<>0
                count=nruOptions(*g\text)
                If nruMouseX<*g\x+*g\w/2.0 : *g\value=*g\value-1.0 : Else : *g\value=*g\value+1.0 : EndIf
                If *g\value<0.0 : *g\value=MathFFromInt(count-1) : EndIf
                If *g\value>=MathFFromInt(count) : *g\value=0.0 : EndIf
              EndIf
            Case #NRU_SLIDER
              *g\value=(nruMouseX-*g\x) / *g\w
              If *g\value<0.0 : *g\value=0.0 : EndIf
              If *g\value>1.0 : *g\value=1.0 : EndIf
            Case #NRU_TOGGLE
              ; Toggle changes on release, not while held.
            Default
              *g\isActive=1
          EndSelect
        EndIf
        If mouseReleased<>0
          If *g\kind=#NRU_TOGGLE
            *g\isActive=1-*g\isActive
          ElseIf *g\kind<>#NRU_DIPBANK
            *g\isActive=0
          EndIf
          notified=nruNotify(*g)
          If notified<>0 : nruInputBusy=0 : ProcedureReturn #NRU_OK : EndIf
        EndIf
      EndIf
      If action<>0
        Select *g\kind
          Case #NRU_DIPBANK
            *g\isActive=*g\isActive ! (1 << *g\subFocus)
          Case #NRU_TOGGLE
            *g\isActive=1-*g\isActive
          Case #NRU_BUTTON
            *g\isActive=0 : *g\hoverAlpha=1.5
            notified=nruNotify(*g)
            If notified<>0 : nruInputBusy=0 : ProcedureReturn #NRU_OK : EndIf
        EndSelect
      EndIf
      If mouseDown=0 And *g\kind<>#NRU_TOGGLE And *g\kind<>#NRU_DIPBANK : *g\isActive=0 : EndIf
    Else
      *g\isFocused=0
      If *g\kind<>#NRU_TOGGLE And *g\kind<>#NRU_DIPBANK : *g\isActive=0 : EndIf
    EndIf
  Next
  nruInputBusy=0 : ProcedureReturn #NRU_OK
EndProcedure

; Selection and numeric labels use fixed scratch owned by this serialized UI.
Procedure.i nruSelection(*text,index.i)
  Protected i.i,n.i=0,j.i=0,c.i
  For i=0 To nruTextBytes-1
    c=PeekA(*text+i)
    If c=0 : Break : EndIf
    If c=124
      If n=index : Break : EndIf
      n=n+1
    ElseIf n=index
      PokeA(@nruScratch[0]+j,c) : j=j+1
    EndIf
  Next
  PokeA(@nruScratch[0]+j,0)
  ProcedureReturn @nruScratch[0]
EndProcedure
Procedure.i nruNumber(n.i)
  If n>=10
    PokeA(@nruDigits[0],48+n/10) : PokeA(@nruDigits[0]+1,48+n-(n/10)*10) : PokeA(@nruDigits[0]+2,0)
  Else
    PokeA(@nruDigits[0],48+n) : PokeA(@nruDigits[0]+1,0)
  EndIf
  ProcedureReturn @nruDigits[0]
EndProcedure
Procedure.i nruFontOf(*g.NeonRetainedGadget)
  If *g\font>=0 : ProcedureReturn *g\font : EndIf
  ProcedureReturn nruFont
EndProcedure
Procedure.i NeonRetainedPrepare()
  Protected i.i,j.i,font.i,rc.i,n.i
  Protected *g.NeonRetainedGadget
  If nruDrawBusy<>0 Or nruInputBusy<>0 Or nruPrepareBusy<>0 Or nruMutationBusy<>0 : ProcedureReturn nruFail(#NRU_ERR_BUSY) : EndIf
  If nruArena=0 : ProcedureReturn nruFail(#NRU_ERR_CONFIG) : EndIf
  If nruRendererActive=0 : ProcedureReturn nruFail(#NRU_ERR_RENDERER) : EndIf
  nruPrepareBusy=1 : rc=0
  PokeA(@nruLeft[0],60) : PokeA(@nruLeft[0]+1,0)
  PokeA(@nruRight[0],62) : PokeA(@nruRight[0]+1,0)
  For i=0 To nruCount-1
    *g=nruArena+i*SizeOf(NeonRetainedGadget) : font=nruFontOf(*g)
    If font>=0
      If *g\kind=#NRU_CAROUSEL
        n=nruOptions(*g\text)
        For j=0 To n-1
          rc=nruPrepare(font,nruSelection(*g\text,j)) : If rc<0 : Break : EndIf
        Next
        If rc>=0 : rc=nruPrepare(font,@nruLeft[0]) : EndIf
        If rc>=0 : rc=nruPrepare(font,@nruRight[0]) : EndIf
      Else
        rc=nruPrepare(font,*g\text)
        If rc>=0 And *g\kind=#NRU_DIPBANK
          n=Int(*g\value)
          For j=1 To n
            rc=nruPrepare(font,nruNumber(j)) : If rc<0 : Break : EndIf
          Next
        EndIf
      EndIf
      If rc<0 : Break : EndIf
    EndIf
  Next
  nruPrepareBusy=0
  If rc<0 : ProcedureReturn nruFail(rc) : EndIf
  ProcedureReturn nruFail(#NRU_OK)
EndProcedure
Procedure nruDrawBox(x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
  Protected rc.i
  If nruDrawError<0 : ProcedureReturn : EndIf
  rc=nruBox(x,y,w,h,r,g,b,a)
  If rc<0 : nruDrawError=rc : EndIf
EndProcedure
Procedure nruDrawText(font.i,x.f,y.f,*text,r.f,g.f,b.f,a.f)
  Protected rc.i
  If nruDrawError<0 Or font<0 : ProcedureReturn : EndIf
  rc=nruText(font,x,y,*text,r,g,b,a)
  If rc<0 : nruDrawError=rc : EndIf
EndProcedure
Procedure.f nruMeasure(font.i,*text)
  Protected w.f
  If font<0 Or nruDrawError<0 : ProcedureReturn 0.0 : EndIf
  w=nruWidth(font,*text)
  If nruFinite(w)=0 Or w<0.0 : nruDrawError=#NRU_ERR_METRICS : ProcedureReturn 0.0 : EndIf
  ProcedureReturn w
EndProcedure
Procedure nruDrawPoly(x.f,y.f,radius.f,r.f,g.f,b.f)
  Protected rc.i
  If nruDrawError<0 : ProcedureReturn : EndIf
  rc=nruPolygon(x,y,radius,radius,16,r,g,b,1.0,1)
  If rc<0 : nruDrawError=rc : EndIf
EndProcedure
; Keep the pulse bounded for an indefinitely focused control. MathSinCos
; intentionally refuses angles above12867; accumulating seconds would reach
; that limit after about54minutes. Reduce elapsed time before multiplying,
; so even a finite very large dt cannot overflow. Each loop is bounded by
; the binary32 exponent range, independent of session length.
Procedure.f nruPhaseAdvance(old.f,dt.f)
  Protected remainder.f=dt,divisor.f=1.570796326795,resultPhase.f
  If remainder>=divisor
    While divisor<=remainder/2.0 : divisor=divisor*2.0 : Wend
    While divisor>=1.570796326795
      If remainder>=divisor : remainder=remainder-divisor : EndIf
      divisor=divisor/2.0
    Wend
  EndIf
  resultPhase=old+remainder*4.0
  If resultPhase>=6.28318530718 : resultPhase=resultPhase-6.28318530718 : EndIf
  ProcedureReturn resultPhase
EndProcedure
Procedure.i NeonRetainedDrawUI(dt.f)
  Protected i.i,j.i,font.i,n.i,selected.i
  Protected x.f,y.f,w.f,h.f,th.f,tw.f,pulse.f,sx.f,seg.f,v.f,green.f
  Protected *g.NeonRetainedGadget
  If nruDrawBusy<>0 Or nruInputBusy<>0 Or nruPrepareBusy<>0 Or nruMutationBusy<>0 : ProcedureReturn nruFail(#NRU_ERR_BUSY) : EndIf
  If nruArena=0 : ProcedureReturn nruFail(#NRU_ERR_CONFIG) : EndIf
  If nruRendererActive=0 : ProcedureReturn nruFail(#NRU_ERR_RENDERER) : EndIf
  If nruFinite(dt)=0 Or dt<0.0 : ProcedureReturn nruFail(#NRU_ERR_ARGS) : EndIf
  nruDrawBusy=1 : nruDrawError=0
  PokeA(@nruLeft[0],60) : PokeA(@nruLeft[0]+1,0)
  PokeA(@nruRight[0],62) : PokeA(@nruRight[0]+1,0)
  For i=0 To nruCount-1
    *g=nruArena+i*SizeOf(NeonRetainedGadget)
    x=*g\x : y=*g\y : w=*g\w : h=*g\h : font=nruFontOf(*g) : th=0.0
    If font>=0
      th=nruHeight(font)
      If nruFinite(th)=0 Or th<0.0 : nruDrawError=#NRU_ERR_METRICS : Break : EndIf
    EndIf
    If *g\isHovered<>0 Or *g\isFocused<>0
      *g\hoverAlpha=*g\hoverAlpha+dt*6.0
      If *g\hoverAlpha>1.0 : *g\hoverAlpha=1.0 : EndIf
    Else
      *g\hoverAlpha=*g\hoverAlpha-dt*6.0
      If *g\hoverAlpha<0.0 : *g\hoverAlpha=0.0 : EndIf
      *g\focusPulse=0.0
    EndIf
    If *g\isFocused<>0 : *g\focusPulse=nruPhaseAdvance(*g\focusPulse,dt) : EndIf
    pulse=0.5+0.5*MathSinCos(*g\focusPulse,0)
    Select *g\kind
      Case #NRU_LABEL
        nruDrawText(font,x,y,*g\text,1.0,0.8,0.2,1.0)
      Case #NRU_BREADCRUMB
        If font>=0
          tw=nruMeasure(font,*g\text)
          nruDrawText(font,x,y,*g\text,0.4,0.8,1.0,1.0)
          nruDrawBox(x,y+th+4.0,tw,2.0,0.2,0.4,0.8,1.0)
        EndIf
      Case #NRU_BUTTON
        If *g\isFocused<>0 : nruDrawBox(x-4.0,y-4.0,w+8.0,h+8.0,0.0,1.0,1.0,pulse) : EndIf
        nruDrawBox(x+4.0,y+4.0,w,h,0.0,0.0,0.0,0.4)
        nruDrawBox(x,y,w,h,0.4,0.4,0.4,1.0)
        nruDrawBox(x+2.0,y+2.0,w-4.0,h-4.0,0.15+*g\hoverAlpha*0.2,0.2,0.6,1.0)
        tw=nruMeasure(font,*g\text)
        nruDrawText(font,x+(w-tw)/2.0,y+(h-th)/2.0,*g\text,0.902,0.902,0.902,1.0)
      Case #NRU_SLIDER
        If PeekA(*g\text)<>0 : nruDrawText(font,x,y-th-6.0,*g\text,0.6,0.8,1.0,1.0) : EndIf
        nruDrawBox(x,y+h/2.0-5.0,w,10.0,0.1,0.1,0.15,1.0)
        nruDrawBox(x,y+h/2.0-5.0,w* *g\value,10.0,0.0,0.8,1.0,1.0)
        v=0.6+*g\hoverAlpha*0.4
        nruDrawBox(x+w* *g\value-8.0,y,16.0,h,v,v,v,1.0)
        If *g\isFocused<>0 : nruDrawBox(x+w* *g\value-12.0,y-4.0,24.0,h+8.0,0.0,1.0,1.0,pulse) : EndIf
      Case #NRU_TOGGLE
        nruDrawText(font,x,y+(h-th)/2.0,*g\text,0.8,0.8,0.8,1.0)
        sx=x+w-60.0
        nruDrawBox(sx,y+5.0,60.0,h-10.0,0.1,0.1,0.1,1.0)
        If *g\isActive<>0
          nruDrawBox(sx+30.0,y+5.0,30.0,h-10.0,0.2,0.9,0.2,1.0)
          nruDrawBox(sx+30.0,y+5.0,30.0,h-10.0,0.6,1.0,0.6,1.0)
        Else
          nruDrawBox(sx,y+5.0,30.0,h-10.0,0.8,0.1,0.1,1.0)
          nruDrawBox(sx,y+5.0,30.0,h-10.0,1.0,0.5,0.5,1.0)
        EndIf
        If *g\isFocused<>0 : nruDrawBox(sx-4.0,y+1.0,68.0,h-2.0,0.0,1.0,1.0,pulse) : EndIf
      Case #NRU_METER
        nruDrawText(font,x,y-th-10.0,*g\text,0.8,0.8,0.8,1.0)
        nruDrawBox(x,y,w,h,0.05,0.05,0.05,1.0)
        seg=(w-6.0)/20.0
        For j=0 To 19
          green=0.8 : If MathFFromInt(j)/20.0>*g\value : green=0.1 : EndIf
          nruDrawBox(x+3.0+MathFFromInt(j)*seg,y+3.0,seg-2.0,h-6.0,0.0,green,green*0.5,1.0)
        Next
      Case #NRU_DIPBANK
        nruDrawText(font,x,y-th-6.0,*g\text,0.8,0.8,0.8,1.0)
        nruDrawBox(x,y,w,h,0.1,0.1,0.1,1.0)
        nruDrawBox(x+4.0,y+4.0,w-8.0,h-8.0,0.02,0.02,0.02,1.0)
        n=Int(*g\value)
        For j=0 To n-1
          sx=x+w/2.0-MathFFromInt(n)*20.0+MathFFromInt(j)*40.0
          If *g\isFocused<>0 And *g\subFocus=j : nruDrawBox(sx-3.0,y+15.0,26.0,48.0,0.0,1.0,1.0,0.4+0.4*MathSinCos(*g\focusPulse,0)) : EndIf
          nruDrawBox(sx+6.0,y+6.0,8.0,8.0,0.0,0.0,0.0,1.0)
          nruDrawBox(sx,y+18.0,20.0,42.0,0.0,0.0,0.0,1.0)
          If (*g\isActive & (1 << j))<>0
            nruDrawBox(sx+2.0,y+20.0,16.0,20.0,0.8,0.9,1.0,1.0)
            nruDrawPoly(sx+10.0,y+10.0,3.0,0.1,1.0,0.2)
          Else
            nruDrawBox(sx+2.0,y+38.0,16.0,20.0,0.8,0.9,1.0,1.0)
            nruDrawPoly(sx+10.0,y+10.0,3.0,0.3,0.0,0.0)
          EndIf
          selected=nruNumber(j+1) : tw=nruMeasure(font,selected)
          nruDrawText(font,sx+10.0-tw/2.0,y+h+5.0,selected,0.5,0.5,0.5,1.0)
        Next
      Case #NRU_CAROUSEL
        nruDrawBox(x,y,w,h,0.05,0.05,0.05,1.0)
        If *g\isFocused<>0 : nruDrawBox(x-2.0,y-2.0,w+4.0,h+4.0,0.0,1.0,1.0,pulse) : EndIf
        tw=nruMeasure(font,@nruLeft[0])
        nruDrawText(font,x+20.0-tw/2.0,y+(h-th)/2.0,@nruLeft[0],0.5,0.5,0.5,1.0)
        tw=nruMeasure(font,@nruRight[0])
        nruDrawText(font,x+w-20.0-tw/2.0,y+(h-th)/2.0,@nruRight[0],0.5,0.5,0.5,1.0)
        selected=nruSelection(*g\text,Int(*g\value)) : tw=nruMeasure(font,selected)
        nruDrawText(font,x+(w-tw)/2.0,y+(h-th)/2.0,selected,0.902,0.902,0.902,1.0)
    EndSelect
    If nruDrawError<0 : Break : EndIf
  Next
  nruDrawPoly(nruMouseX,nruMouseY,4.0,1.0,0.0,0.0)
  nruDrawBusy=0 : ProcedureReturn nruFail(nruDrawError)
EndProcedure

; SPDX-License-Identifier: MIT
; Renderer-neutral immediate Neon scrollbars. Caller owns one shared state per UI.
; Frame input is already in virtual-canvas units. Calls are serialized.
XIncludeFile "Anvil/Math/float32.pbi"
XIncludeFile "Anvil/Graphics/neon_chrome_style.pbi"
XIncludeFile "Anvil/Graphics/neon_chrome_hotzones.pbi"
XIncludeFile "Anvil/Math/float32_convert.pbi"
#NCS_MAGIC = $4E435331
#NCS_ERR_ARGS = -21600
#NCS_ERR_STATE = -21601
#NCS_ERR_BUSY = -21602
#NCS_ERR_RENDERER = -21603
; Native-width scalar layout; callers may pass the address of a .i offset.
Structure NeonChromeScrollOffset Align #PB_Structure_AlignC
  value.i
EndStructure
Structure NeonChromeScrollState Align #PB_Structure_AlignC
  magic.i : reserved.i : dragId.i : busy.i : error.i
  inputReady.i : down.i : pressed.i
  mouseX.f : mouseY.f : grab.f : scale.f
EndStructure
Procedure.i ncsBoxUnbound(x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
  ProcedureReturn #NCS_ERR_RENDERER
EndProcedure
Global ncsDraw.i=@ncsBoxUnbound,ncsDrawBusy.i,ncsRendererActive.i
Procedure.i NeonChromeScrollRendererInstall(boxProc.i)
  If ncsDrawBusy<>0 : ProcedureReturn #NCS_ERR_BUSY : EndIf
  If boxProc=0 : ProcedureReturn #NCS_ERR_ARGS : EndIf
  ncsDraw=boxProc : ncsRendererActive=1 : ProcedureReturn 0
EndProcedure
Procedure.i ncsValid(*s.NeonChromeScrollState)
  If *s=0 Or (*s & 7)<>0 : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool(*s\magic=#NCS_MAGIC)
EndProcedure
Procedure.i ncsFinite(v.f)
  ProcedureReturn Bool((MathBitsOf(v) & $7FFFFFFF)<=$49742400)
EndProcedure
Procedure.i ncsFail(*s.NeonChromeScrollState,code.i)
  *s\error=code : ProcedureReturn code
EndProcedure
Procedure.i NeonChromeScrollConfigure(*s.NeonChromeScrollState,scale.f)
  If *s=0 Or (*s & 7)<>0 : ProcedureReturn #NCS_ERR_ARGS : EndIf
  If *s\magic<>0 And *s\magic<>#NCS_MAGIC : ProcedureReturn #NCS_ERR_STATE : EndIf
  If *s\busy<>0 Or ncsDrawBusy<>0 : ProcedureReturn #NCS_ERR_BUSY : EndIf
  If ncsFinite(scale)=0 Or scale<=0.0 Or scale>64.0 : ProcedureReturn #NCS_ERR_ARGS : EndIf
  *s\magic=#NCS_MAGIC : *s\scale=scale
  *s\dragId=0 : *s\grab=0.0 : *s\inputReady=0 : *s\down=0 : *s\pressed=0 : *s\error=0
  ProcedureReturn 0
EndProcedure
Procedure.i NeonChromeScrollInput(*s.NeonChromeScrollState,x.f,y.f,down.i)
  If ncsValid(*s)=0 : ProcedureReturn #NCS_ERR_STATE : EndIf
  If *s\busy<>0 Or ncsDrawBusy<>0 : ProcedureReturn ncsFail(*s,#NCS_ERR_BUSY) : EndIf
  If ncsFinite(x)=0 Or ncsFinite(y)=0 Or (down<>0 And down<>1) : ProcedureReturn ncsFail(*s,#NCS_ERR_ARGS) : EndIf
  *s\mouseX=x : *s\mouseY=y : *s\pressed=Bool(down<>0 And *s\down=0) : *s\down=down : *s\inputReady=1
  ; Release even if the former owner's widget is omitted this frame.
  If down=0 : *s\dragId=0 : *s\grab=0.0 : EndIf
  ProcedureReturn ncsFail(*s,0)
EndProcedure
Procedure.i NeonChromeScrollDragOwner(*s.NeonChromeScrollState)
  If ncsValid(*s)=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn *s\dragId
EndProcedure
Procedure.i NeonChromeScrollError(*s.NeonChromeScrollState)
  If ncsValid(*s)=0 : ProcedureReturn #NCS_ERR_STATE : EndIf
  ProcedureReturn *s\error
EndProcedure
; axis=0 horizontal / 1 vertical. Result: negative refusal, 0 unchanged, 1 changed.
; Renderer refusal leaves offset and drag owner unchanged; caller aborts its frame.
Procedure.i ncsBar(*s.NeonChromeScrollState,id.i,x.f,y.f,w.f,h.f,total.i,visible.i,*offset.NeonChromeScrollOffset,axis.i,mode.i)
  Protected pos.f,span.f,cross.f,mouse.f,thumb.f,travel.f,thumbPos.f,want.f,grab.f
  Protected candidate.i,original.i,maxOffset.i,owner.i,over.i,onThumb.i,rc.i,changed.i,inert.i
  Protected tx.f,ty.f,tw.f,th.f,tr.f,tg.f,tb.f
  If ncsValid(*s)=0 : ProcedureReturn #NCS_ERR_STATE : EndIf
  If *s\busy<>0 Or ncsDrawBusy<>0 : ProcedureReturn ncsFail(*s,#NCS_ERR_BUSY) : EndIf
  If mode<0 Or mode>2 : ProcedureReturn ncsFail(*s,#NCS_ERR_ARGS) : EndIf
  If mode<>1 And ncsRendererActive=0 : ProcedureReturn ncsFail(*s,#NCS_ERR_RENDERER) : EndIf
  If *s\inputReady=0 : ProcedureReturn ncsFail(*s,#NCS_ERR_STATE) : EndIf
  If id<1 Or *offset=0 Or (*offset & 7)<>0 Or *offset+7<*offset : ProcedureReturn ncsFail(*s,#NCS_ERR_ARGS) : EndIf
  If *offset<*s+SizeOf(NeonChromeScrollState) And *offset+8>*s : ProcedureReturn ncsFail(*s,#NCS_ERR_ARGS) : EndIf
  If total<0 Or total>2147483647 Or visible<0 Or visible>2147483647 : ProcedureReturn ncsFail(*s,#NCS_ERR_ARGS) : EndIf
  If ncsFinite(x)=0 Or ncsFinite(y)=0 Or ncsFinite(w)=0 Or ncsFinite(h)=0 Or w<=4.0 Or h<=4.0 Or w>8192.0 Or h>8192.0 : ProcedureReturn ncsFail(*s,#NCS_ERR_ARGS) : EndIf
  original=*offset\value : candidate=original : owner=*s\dragId : grab=*s\grab
  inert=Bool(total<=visible Or total=0)
  If inert<>0
    candidate=0 : If owner=id : owner=0 : grab=0.0 : EndIf
  Else
    maxOffset=total-visible
    If candidate<0 : candidate=0 : EndIf
    If candidate>maxOffset : candidate=maxOffset : EndIf
    pos=x : span=w : cross=h : mouse=*s\mouseX
    If axis=1 : pos=y : span=h : cross=w : mouse=*s\mouseY : EndIf
    thumb=span*(MathFFromInt(visible)/MathFFromInt(total))
    If thumb<18.0* *s\scale : thumb=18.0* *s\scale : EndIf
    ; A minimum thumb must never escape a short track.
    If thumb>span : thumb=span : EndIf
    travel=span-thumb
    thumbPos=pos+travel*(MathFFromInt(candidate)/MathFFromInt(maxOffset))
    over=Bool(*s\mouseX>=x And *s\mouseX<x+w And *s\mouseY>=y And *s\mouseY<y+h)
    onThumb=Bool(over<>0 And mouse>=thumbPos And mouse<thumbPos+thumb)
    If mode<>2 And *s\pressed<>0 And over<>0
      If onThumb<>0
        owner=id : grab=mouse-thumbPos
      Else
        If mouse<thumbPos : candidate=candidate-visible : Else : candidate=candidate+visible : EndIf
      EndIf
    EndIf
    If mode<>2 And owner=id And *s\down<>0 And travel>0.0
      want=(mouse-grab-pos)/travel
      If want<0.0 : want=0.0 : EndIf
      If want>1.0 : want=1.0 : EndIf
      candidate=MathFToI32(want*MathFFromInt(maxOffset)+0.5)
    EndIf
    If candidate<0 : candidate=0 : EndIf
    If candidate>maxOffset : candidate=maxOffset : EndIf
    thumbPos=pos+travel*(MathFFromInt(candidate)/MathFFromInt(maxOffset))
    tx=x+2.0 : ty=thumbPos : tw=w-4.0 : th=thumb
    If axis=0 : tx=thumbPos : ty=y+2.0 : tw=thumb : th=h-4.0 : EndIf
  EndIf
  If mode<>1
  nstyEnter() : *s\busy=1 : ncsDrawBusy=1
  rc=0
  If inert=0 : rc=nhzEmit(8-axis,*s,id,tx,ty,tw,th) : EndIf
  If rc=0 : rc=ncsDraw(x,y,w,h,nstyPalette\bg\r,nstyPalette\bg\g,nstyPalette\bg\b,1.0) : EndIf
  If rc=0 And inert=0
    tr=nstyPalette\thumb\r : tg=nstyPalette\thumb\g : tb=nstyPalette\thumb\b
    If onThumb<>0 Or owner=id : tr=nstyPalette\accent\r*0.8 : tg=nstyPalette\accent\g*0.8 : tb=nstyPalette\accent\b*0.8 : EndIf
    rc=ncsDraw(tx,ty,tw,th,tr,tg,tb,1.0)
  EndIf
  *s\busy=0 : ncsDrawBusy=0 : nstyLeave()
  If rc>0 : rc=#NCS_ERR_RENDERER : EndIf
  If rc<0 : ProcedureReturn ncsFail(*s,rc) : EndIf
  EndIf
  If mode=2 : ProcedureReturn ncsFail(*s,0) : EndIf
  *offset\value=candidate : *s\dragId=owner : *s\grab=grab : *s\error=0
  If inert<>0 : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool(candidate<>original)
EndProcedure
Procedure.i NeonChromeScrollBarV(*s.NeonChromeScrollState,id.i,x.f,y.f,w.f,h.f,total.i,visible.i,*top.NeonChromeScrollOffset)
  ProcedureReturn ncsBar(*s,id,x,y,w,h,total,visible,*top,1,0)
EndProcedure
Procedure.i NeonChromeScrollBarH(*s.NeonChromeScrollState,id.i,x.f,y.f,w.f,h.f,total.i,visible.i,*left.NeonChromeScrollOffset)
  ProcedureReturn ncsBar(*s,id,x,y,w,h,total,visible,*left,0,0)
EndProcedure

; Split phase: Update has no renderer calls; Paint never commits offset/drag changes.
; Feed one shared ScrollInput per UI frame, then update before opening the frame.
Procedure.i NeonChromeScrollUpdateV(*s.NeonChromeScrollState,id.i,x.f,y.f,w.f,h.f,total.i,visible.i,*top.NeonChromeScrollOffset)
  ProcedureReturn ncsBar(*s,id,x,y,w,h,total,visible,*top,1,1)
EndProcedure
Procedure.i NeonChromeScrollPaintV(*s.NeonChromeScrollState,id.i,x.f,y.f,w.f,h.f,total.i,visible.i,*top.NeonChromeScrollOffset)
  ProcedureReturn ncsBar(*s,id,x,y,w,h,total,visible,*top,1,2)
EndProcedure
Procedure.i NeonChromeScrollUpdateH(*s.NeonChromeScrollState,id.i,x.f,y.f,w.f,h.f,total.i,visible.i,*left.NeonChromeScrollOffset)
  ProcedureReturn ncsBar(*s,id,x,y,w,h,total,visible,*left,0,1)
EndProcedure
Procedure.i NeonChromeScrollPaintH(*s.NeonChromeScrollState,id.i,x.f,y.f,w.f,h.f,total.i,visible.i,*left.NeonChromeScrollOffset)
  ProcedureReturn ncsBar(*s,id,x,y,w,h,total,visible,*left,0,2)
EndProcedure

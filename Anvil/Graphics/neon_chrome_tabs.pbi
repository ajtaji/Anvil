; SPDX-License-Identifier: MIT
; Prepared, renderer-neutral chrome tab strips. Caller owns storage and frame.
XIncludeFile "Anvil/Math/float32.pbi"
XIncludeFile "Anvil/Graphics/neon_chrome_style.pbi"
XIncludeFile "Anvil/Graphics/neon_chrome_hotzones.pbi"
XIncludeFile "Anvil/Graphics/neon_utf8.pbi"
#NCT_MAGIC=$4E435431
#NCT_SCROLL=1
#NCT_REVEAL=2
#NCT_NORMAL=0
#NCT_ITALIC=1
#NCT_PINNED=2
#NCT_ERR_ARGS=-22000
#NCT_ERR_STATE=-22001
#NCT_ERR_BUSY=-22002
#NCT_ERR_CAPACITY=-22003
#NCT_ERR_RENDERER=-22004
#NCT_ERR_METRICS=-22005
#NCT_ERR_TEXT=-22006
#NCT_ERR_LAYOUT=-22007
Structure NeonChromeTabConfig Align #PB_Structure_AlignC
  x.f : y.f : w.f : h.f : scale.f
  font.i : smallFont.i : italicFont.i : withClose.i : flags.i : activeId.i : tail.i
EndStructure
Structure NeonChromeTab Align #PB_Structure_AlignC
  id.i : font.i : style.i : label.i : shown.i : labelBytes.i : shownBytes.i
  width.f : pos.f : labelW.f : shownW.f : visibleX.f : visibleW.f : hover.f
EndStructure
Structure NeonChromeTabState Align #PB_Structure_AlignC
  magic.i : arena.i : bytes.i : capacity.i : textBytes.i : count.i : ready.i
  font.i : smallFont.i : italicFont.i : withClose.i : flags.i : activeId.i
  hoverIndex.i : closedId.i : pinId.i : down.i : pressed.i : blocked.i : wheelRemaining.i
  error.i : cleanupError.i : layoutKnown.i : needsRedraw.i : indicatorReady.i : tail.i : tailBytes.i
  x.f : y.f : w.f : h.f : scale.f : uiH.f : smallH.f : side.f : arrowW.f
  maxWidth.f : total.f : maxScroll.f : scroll.f : viewL.f : viewR.f
  crossW.f : leftW.f : rightW.f : indicatorX.f : indicatorW.f : leftHover.f : rightHover.f : mouseX.f : mouseY.f
  styleRevision.i
EndStructure
Procedure.i nctBoxUnbound(x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
  ProcedureReturn #NCT_ERR_RENDERER
EndProcedure
Procedure.i nctTextUnbound(font.i,x.f,y.f,text.i,r.f,g.f,b.f,a.f)
  ProcedureReturn #NCT_ERR_RENDERER
EndProcedure
Procedure.f nctWidthUnbound(font.i,text.i)
  ProcedureReturn -1.0
EndProcedure
Procedure.f nctHeightUnbound(font.i)
  ProcedureReturn -1.0
EndProcedure
Procedure.i nctPrepareUnbound(font.i,text.i)
  ProcedureReturn #NCT_ERR_RENDERER
EndProcedure
Procedure.i nctClipUnbound(x.f,y.f,w.f,h.f)
  ProcedureReturn #NCT_ERR_RENDERER
EndProcedure
Procedure.i nctClearUnbound()
  ProcedureReturn #NCT_ERR_RENDERER
EndProcedure
Global nctBox.i=@nctBoxUnbound,nctText.i=@nctTextUnbound,nctWidth.i=@nctWidthUnbound,nctHeight.i=@nctHeightUnbound
Global nctPrepare.i=@nctPrepareUnbound,nctClip.i=@nctClipUnbound,nctClear.i=@nctClearUnbound
Global nctBusy.i,nctActive.i,nctDrawError.i
Procedure.i NeonChromeTabsRendererInstall(boxProc.i,textProc.i,widthProc.i,heightProc.i,prepareProc.i,clipProc.i,clearProc.i)
  If nctBusy<>0 : ProcedureReturn #NCT_ERR_BUSY : EndIf
  If boxProc=0 Or textProc=0 Or widthProc=0 Or heightProc=0 Or prepareProc=0 Or clipProc=0 Or clearProc=0 : ProcedureReturn #NCT_ERR_ARGS : EndIf
  nctBox=boxProc : nctText=textProc : nctWidth=widthProc : nctHeight=heightProc
  nctPrepare=prepareProc : nctClip=clipProc : nctClear=clearProc : nctActive=1 : ProcedureReturn 0
EndProcedure
Procedure.i nctValid(*s.NeonChromeTabState)
  If *s=0 Or (*s & 7)<>0 : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool(*s\magic=#NCT_MAGIC)
EndProcedure
Procedure.i nctFinite(v.f)
  ProcedureReturn Bool((MathBitsOf(v) & $7FFFFFFF)<=$49742400)
EndProcedure
Procedure.i nctFail(*s.NeonChromeTabState,rc.i)
  *s\error=rc : ProcedureReturn rc
EndProcedure
Procedure.i nctStatus(rc.i)
  If rc>0 : ProcedureReturn #NCT_ERR_RENDERER : EndIf
  ProcedureReturn rc
EndProcedure
Procedure.i nctNode(*s.NeonChromeTabState,index.i)
  ProcedureReturn *s\arena+index*SizeOf(NeonChromeTab)
EndProcedure
Procedure.i nctFind(*s.NeonChromeTabState,id.i)
  Protected i.i,*n.NeonChromeTab
  For i=0 To *s\count-1
    *n=nctNode(*s,i) : If *n\id=id : ProcedureReturn i : EndIf
  Next
  ProcedureReturn -1
EndProcedure
Procedure.i NeonChromeTabsRequiredBytes(capacity.i,textBytes.i)
  If capacity<1 Or capacity>1024 Or textBytes<4 Or textBytes>512 : ProcedureReturn 0 : EndIf
  ProcedureReturn capacity*(SizeOf(NeonChromeTab)+2*textBytes)+16
EndProcedure
Procedure.i NeonChromeTabsConfigure(*s.NeonChromeTabState,arena.i,bytes.i,capacity.i,textBytes.i,*c.NeonChromeTabConfig)
  Protected needed.i=NeonChromeTabsRequiredBytes(capacity,textBytes),i.i,tail.i,tailN.i
  If nctBusy<>0 : ProcedureReturn #NCT_ERR_BUSY : EndIf
  If *s=0 Or (*s & 7)<>0 Or *c=0 Or (*c & 7)<>0 : ProcedureReturn #NCT_ERR_ARGS : EndIf
  If needed=0 Or arena<1 Or (arena & 7)<>0 Or bytes<needed Or arena+needed-1<arena Or *s+SizeOf(NeonChromeTabState)-1<*s : ProcedureReturn #NCT_ERR_ARGS : EndIf
  If arena<*s+SizeOf(NeonChromeTabState) And arena+needed>*s : ProcedureReturn #NCT_ERR_ARGS : EndIf
  If *c<*s+SizeOf(NeonChromeTabState) And *c+SizeOf(NeonChromeTabConfig)>*s : ProcedureReturn #NCT_ERR_ARGS : EndIf
  If nctFinite(*c\x)=0 Or nctFinite(*c\y)=0 Or nctFinite(*c\w)=0 Or nctFinite(*c\h)=0 Or nctFinite(*c\scale)=0 : ProcedureReturn #NCT_ERR_ARGS : EndIf
  If *c\w<=0.0 Or *c\w>8192.0 Or *c\h<=1.0 Or *c\h>8192.0 Or *c\scale<=0.0 Or *c\scale>16.0 Or nctFinite(*c\x+*c\w)=0 Or nctFinite(*c\y+*c\h)=0 : ProcedureReturn #NCT_ERR_ARGS : EndIf
  If *c\font<0 Or *c\smallFont<0 Or *c\italicFont < -1 Or *c\flags<0 Or *c\flags>3 Or (*c\withClose<>0 And *c\withClose<>1) Or *c\activeId<0 : ProcedureReturn #NCT_ERR_ARGS : EndIf
  tail=*c\tail : If tail=0 : tail="..." : EndIf
  tailN=NeonUtf8Length(tail,16)
  If tailN<0 Or tailN>=textBytes : ProcedureReturn #NCT_ERR_TEXT : EndIf
  If (tail<arena+needed And tail+tailN+1>arena) Or (tail<*s+SizeOf(NeonChromeTabState) And tail+tailN+1>*s) : ProcedureReturn #NCT_ERR_ARGS : EndIf
  For i=0 To SizeOf(NeonChromeTabState)-8 Step 8 : PokeI(*s+i,0) : Next
  *s\magic=#NCT_MAGIC : *s\arena=arena : *s\bytes=needed : *s\capacity=capacity : *s\textBytes=textBytes
  *s\x=*c\x : *s\y=*c\y : *s\w=*c\w : *s\h=*c\h : *s\scale=*c\scale
  *s\font=*c\font : *s\smallFont=*c\smallFont : *s\italicFont=*c\italicFont
  *s\withClose=*c\withClose : *s\flags=*c\flags : *s\activeId=*c\activeId : *s\hoverIndex=-1
  *s\tail=arena+capacity*(SizeOf(NeonChromeTab)+2*textBytes) : *s\tailBytes=tailN
  For i=0 To tailN : PokeA(*s\tail+i,PeekA(tail+i)) : Next
  ProcedureReturn 0
EndProcedure
Procedure.i NeonChromeTabsBeginBuild(*s.NeonChromeTabState)
  If nctValid(*s)=0 : ProcedureReturn #NCT_ERR_STATE : EndIf
  If nctBusy<>0 : ProcedureReturn nctFail(*s,#NCT_ERR_BUSY) : EndIf
  *s\count=0 : *s\ready=0 : *s\closedId=0 : *s\pinId=0 : *s\hoverIndex=-1
  ProcedureReturn nctFail(*s,0)
EndProcedure
Procedure.i NeonChromeTabsAdd(*s.NeonChromeTabState,id.i,label.i,style.i)
  Protected len.i,i.i,dest.i,*n.NeonChromeTab
  If nctValid(*s)=0 : ProcedureReturn #NCT_ERR_STATE : EndIf
  If nctBusy<>0 : ProcedureReturn nctFail(*s,#NCT_ERR_BUSY) : EndIf
  If *s\ready<>0 : ProcedureReturn nctFail(*s,#NCT_ERR_STATE) : EndIf
  If id<1 Or nctFind(*s,id)>=0 Or style<0 Or style>2 : ProcedureReturn nctFail(*s,#NCT_ERR_ARGS) : EndIf
  If *s\count>=*s\capacity : ProcedureReturn nctFail(*s,#NCT_ERR_CAPACITY) : EndIf
  len=NeonUtf8Length(label,*s\textBytes) : If len<0 : ProcedureReturn nctFail(*s,#NCT_ERR_TEXT) : EndIf
  *n=nctNode(*s,*s\count) : dest=*s\arena+*s\capacity*SizeOf(NeonChromeTab)+*s\count*2* *s\textBytes
  If (label<*n+SizeOf(NeonChromeTab) And label+len+1>*n) Or (label<dest+2* *s\textBytes And label+len+1>dest) : ProcedureReturn nctFail(*s,#NCT_ERR_ARGS) : EndIf
  For i=0 To SizeOf(NeonChromeTab)-8 Step 8 : PokeI(*n+i,0) : Next
  *n\id=id : *n\style=style : *n\font=*s\font
  If style=#NCT_ITALIC And *s\italicFont>=0 : *n\font=*s\italicFont : EndIf
  *n\label=dest : *n\shown=dest+*s\textBytes : *n\labelBytes=len
  For i=0 To len : PokeA(dest+i,PeekA(label+i)) : Next
  *s\count=*s\count+1 : ProcedureReturn nctFail(*s,0)
EndProcedure
Procedure.i nctFit(*s.NeonChromeTabState,*n.NeonChromeTab,room.f)
  Protected low.i,high.i,half.i,cut.i,best.i,i.i,width.f,tailW.f
  If *n\labelW<=room
    For i=0 To *n\labelBytes : PokeA(*n\shown+i,PeekA(*n\label+i)) : Next
    *n\shownBytes=*n\labelBytes : *n\shownW=*n\labelW : ProcedureReturn 0
  EndIf
  *n\shownBytes=0 : *n\shownW=0.0 : PokeA(*n\shown,0)
  tailW=nctWidth(*n\font,*s\tail)
  If nctFinite(tailW)=0 Or tailW<0.0 : ProcedureReturn #NCT_ERR_METRICS : EndIf
  If room<tailW : ProcedureReturn 0 : EndIf
  high=*n\labelBytes-1
  While low<high
    half=(low+high+1)/2 : cut=NeonUtf8Prefix(*n\label,*n\labelBytes,half)
    If cut+*s\tailBytes>=*s\textBytes : high=half-1 : Continue : EndIf
    For i=0 To cut-1 : PokeA(*n\shown+i,PeekA(*n\label+i)) : Next
    For i=0 To *s\tailBytes : PokeA(*n\shown+cut+i,PeekA(*s\tail+i)) : Next
    width=nctWidth(*n\font,*n\shown)
    If nctFinite(width)=0 Or width<0.0 : ProcedureReturn #NCT_ERR_METRICS : EndIf
    If width<=room : low=half : best=cut : Else : high=half-1 : EndIf
  Wend
  For i=0 To best-1 : PokeA(*n\shown+i,PeekA(*n\label+i)) : Next
  For i=0 To *s\tailBytes : PokeA(*n\shown+best+i,PeekA(*s\tail+i)) : Next
  *n\shownBytes=best+*s\tailBytes : *n\shownW=nctWidth(*n\font,*n\shown)
  If nctFinite(*n\shownW)=0 Or *n\shownW<0.0 Or *n\shownW>room : ProcedureReturn #NCT_ERR_METRICS : EndIf
  ProcedureReturn 0
EndProcedure
Procedure nctLayout(*s.NeonChromeTabState)
  Protected i.i,x.f,r.f,*n.NeonChromeTab
  If *s\scroll<0.0 : *s\scroll=0.0 : EndIf
  If *s\scroll>*s\maxScroll : *s\scroll=*s\maxScroll : EndIf
  *s\viewL=*s\x : *s\viewR=*s\x+*s\w
  If *s\maxScroll>0.0
    If *s\scroll>0.0 : *s\viewL=*s\viewL+*s\arrowW : EndIf
    If *s\scroll<*s\maxScroll : *s\viewR=*s\viewR-*s\arrowW : EndIf
  EndIf
  For i=0 To *s\count-1
    *n=nctNode(*s,i) : x=*s\x+4.0* *s\scale+*n\pos-*s\scroll : r=x+*n\width
    If x<*s\viewL : x=*s\viewL : EndIf
    If r>*s\viewR : r=*s\viewR : EndIf
    *n\visibleX=x : *n\visibleW=r-x : If *n\visibleW<0.0 : *n\visibleW=0.0 : EndIf
  Next
EndProcedure
Procedure nctReveal(*s.NeonChromeTabState,index.i)
  Protected *n.NeonChromeTab=nctNode(*s,index),l.f,r.f
  If *s\maxScroll<=0.0 : ProcedureReturn : EndIf
  nctLayout(*s) : l=*s\x+4.0* *s\scale+*n\pos-*s\scroll : r=l+*n\width
  If l<*s\viewL-0.01 : *s\scroll=4.0* *s\scale+*n\pos-*s\arrowW
  ElseIf r>*s\viewR+0.01 : *s\scroll=4.0* *s\scale+*n\pos+*n\width-(*s\w-*s\arrowW) : EndIf
  nctLayout(*s)
EndProcedure
Procedure.i NeonChromeTabsSeal(*s.NeonChromeTabState)
  Protected i.i,index.i,rc.i,room.f,*n.NeonChromeTab
  If nctValid(*s)=0 : ProcedureReturn #NCT_ERR_STATE : EndIf
  If nctBusy<>0 : ProcedureReturn nctFail(*s,#NCT_ERR_BUSY) : EndIf
  If *s\ready<>0 : ProcedureReturn nctFail(*s,#NCT_ERR_STATE) : EndIf
  If nctActive=0 : ProcedureReturn nctFail(*s,#NCT_ERR_RENDERER) : EndIf
  nctBusy=1 : *s\uiH=nctHeight(*s\font) : *s\smallH=nctHeight(*s\smallFont)
  If nctFinite(*s\uiH)=0 Or nctFinite(*s\smallH)=0 Or *s\uiH<=0.0 Or *s\smallH<=0.0 : rc=#NCT_ERR_METRICS : EndIf
  *s\side=18.0* *s\scale
  If *s\smallH+2.0* *s\scale>*s\side : *s\side=*s\smallH+2.0* *s\scale : EndIf
  If *s\side>*s\h-1.0 : *s\side=*s\h-1.0 : EndIf
  *s\arrowW=*s\side+4.0* *s\scale
  *s\maxWidth=300.0* *s\scale : If *s\uiH*26.0>*s\maxWidth : *s\maxWidth=*s\uiH*26.0 : EndIf
  room=*s\w-8.0* *s\scale : If (*s\flags & #NCT_SCROLL)<>0 : room=room-2.0* *s\arrowW : EndIf
  If *s\maxWidth>room : *s\maxWidth=room : EndIf
  room=20.0* *s\scale
  If *s\withClose<>0 : room=19.0* *s\scale+*s\side : EndIf
  If *s\count>0 And *s\maxWidth<room : rc=#NCT_ERR_LAYOUT : EndIf
  *s\total=0.0
  For i=0 To *s\count-1
    If rc<>0 : Break : EndIf
    *n=nctNode(*s,i) : *n\labelW=nctWidth(*n\font,*n\label)
    If nctFinite(*n\labelW)=0 Or *n\labelW<0.0 : rc=#NCT_ERR_METRICS : Break : EndIf
    *n\width=*n\labelW+26.0* *s\scale : If *s\withClose<>0 : *n\width=*n\width+*s\side : EndIf
    If *n\width>*s\maxWidth : *n\width=*s\maxWidth : EndIf
    room=*n\width-20.0* *s\scale
    If *s\withClose<>0 : room=*n\width-19.0* *s\scale-*s\side : EndIf
    rc=nctFit(*s,*n,room) : If rc<>0 : Break : EndIf
    rc=nctStatus(nctPrepare(*n\font,*n\shown))
    *n\pos=*s\total : *s\total=*s\total+*n\width
  Next
  If rc=0
    rc=nctStatus(nctPrepare(*s\smallFont,"x<>"))
    *s\crossW=nctWidth(*s\smallFont,"x") : *s\leftW=nctWidth(*s\smallFont,"<") : *s\rightW=nctWidth(*s\smallFont,">")
    If nctFinite(*s\crossW)=0 Or nctFinite(*s\leftW)=0 Or nctFinite(*s\rightW)=0 Or *s\crossW<0.0 Or *s\leftW<0.0 Or *s\rightW<0.0 : rc=#NCT_ERR_METRICS : EndIf
  EndIf
  nctBusy=0 : If rc<>0 : ProcedureReturn nctFail(*s,rc) : EndIf
  *s\maxScroll=0.0
  If (*s\flags & #NCT_SCROLL)<>0 : *s\maxScroll=4.0* *s\scale+*s\total-*s\w : EndIf
  If *s\maxScroll<0.0 : *s\maxScroll=0.0 : EndIf
  index=nctFind(*s,*s\activeId)
  If index<0 : *s\activeId=0 : EndIf
  nctLayout(*s)
  If index>=0 And (*s\layoutKnown=0 Or (*s\flags & #NCT_REVEAL)<>0) : nctReveal(*s,index) : EndIf
  *s\flags=*s\flags & (0-1-#NCT_REVEAL)
  If index>=0 And *s\indicatorReady=0
    *n=nctNode(*s,index) : *s\indicatorX=*s\x+4.0* *s\scale+*n\pos : *s\indicatorW=*n\width : *s\indicatorReady=1
  EndIf
  *s\ready=1 : *s\layoutKnown=1 : *s\needsRedraw=1 : ProcedureReturn nctFail(*s,0)
EndProcedure
Procedure.i NeonChromeTabsGet(*s.NeonChromeTabState,id.i)
  Protected index.i
  If nctValid(*s)=0 : ProcedureReturn 0 : EndIf
  index=nctFind(*s,id) : If index<0 : ProcedureReturn 0 : EndIf
  ProcedureReturn nctNode(*s,index)
EndProcedure
Procedure.i NeonChromeTabAt(*s.NeonChromeTabState,x.f,y.f)
  Protected i.i,*n.NeonChromeTab
  If nctValid(*s)=0 : ProcedureReturn 0 : EndIf
  If *s\ready=0 Or nctFinite(x)=0 Or nctFinite(y)=0 Or x<*s\viewL Or x>=*s\viewR Or y<*s\y Or y>=*s\y+*s\h-1.0 : ProcedureReturn 0 : EndIf
  For i=0 To *s\count-1
    *n=nctNode(*s,i)
    If *n\visibleW>0.0 And x>=*n\visibleX And x<*n\visibleX+*n\visibleW : ProcedureReturn *n\id : EndIf
  Next
  ProcedureReturn 0
EndProcedure
Procedure.i NeonChromeTabsSelect(*s.NeonChromeTabState,id.i,reveal.i)
  Protected index.i
  If nctValid(*s)=0 : ProcedureReturn #NCT_ERR_STATE : EndIf
  If nctBusy<>0 : ProcedureReturn nctFail(*s,#NCT_ERR_BUSY) : EndIf
  If *s\ready<>0 And id=0 And (reveal=0 Or reveal=1)
    *s\activeId=0 : *s\indicatorReady=0 : *s\needsRedraw=1 : ProcedureReturn nctFail(*s,0)
  EndIf
  index=nctFind(*s,id)
  If *s\ready=0 Or index<0 Or (reveal<>0 And reveal<>1) : ProcedureReturn nctFail(*s,#NCT_ERR_ARGS) : EndIf
  *s\activeId=id : If reveal<>0 : nctReveal(*s,index) : EndIf
  *s\needsRedraw=1 : ProcedureReturn nctFail(*s,0)
EndProcedure
Procedure.f nctEase(*s.NeonChromeTabState,current.f,target.f,speed.f,dt.f)
  If current=target Or nstyAnimations=0 : ProcedureReturn target : EndIf
  current=current+(target-current)*(1.0-Exp(0.0-speed*dt))
  If MathFAbs(target-current)<0.002 : ProcedureReturn target : EndIf
  *s\needsRedraw=1 : ProcedureReturn current
EndProcedure
Procedure.i NeonChromeTabsInput(*s.NeonChromeTabState,x.f,y.f,down.i,wheel.i,blocked.i,dt.f)
  Protected i.i,index.i,steps.i,used.i,over.i,left.i,right.i,id.i,*n.NeonChromeTab
  Protected bx.f,by.f,hx.f,hw.f,cx.f,r.f,oldScroll.f
  If nctValid(*s)=0 : ProcedureReturn #NCT_ERR_STATE : EndIf
  If nctBusy<>0 : ProcedureReturn nctFail(*s,#NCT_ERR_BUSY) : EndIf
  If *s\ready=0 : ProcedureReturn nctFail(*s,#NCT_ERR_STATE) : EndIf
  If nctFinite(x)=0 Or nctFinite(y)=0 Or nctFinite(dt)=0 Or dt<0.0 Or (down<>0 And down<>1) Or (blocked<>0 And blocked<>1) Or wheel < -128 Or wheel>128 : ProcedureReturn nctFail(*s,#NCT_ERR_ARGS) : EndIf
  If dt>0.05 : dt=0.05 : EndIf
  *s\mouseX=x : *s\mouseY=y
  *s\needsRedraw=0 : *s\pressed=Bool(down<>0 And *s\down=0) : *s\down=down : *s\blocked=blocked : *s\wheelRemaining=wheel
  *s\closedId=0 : *s\pinId=0 : oldScroll=*s\scroll
  nctLayout(*s) : over=Bool(x>=*s\x And x<*s\x+*s\w And y>=*s\y And y<*s\y+*s\h)
  If blocked=0 And *s\maxScroll>0.0
    If *s\pressed<>0 And y>=*s\y And y<*s\y+*s\h-1.0
      If *s\scroll>0.0 And x>=*s\x And x<*s\x+*s\arrowW : steps=-1 : used=1
      ElseIf *s\scroll<*s\maxScroll And x>=*s\x+*s\w-*s\arrowW And x<*s\x+*s\w : steps=1 : used=1 : EndIf
    EndIf
    If wheel<>0 And over<>0 : steps=0-wheel : If steps>8 : steps=8 : EndIf : If steps < -8 : steps=-8 : EndIf : *s\wheelRemaining=0 : EndIf
    While steps<>0
      nctLayout(*s) : index=-1
      If steps>0
        For i=0 To *s\count-1
          *n=nctNode(*s,i) : r=*s\x+4.0* *s\scale+*n\pos+*n\width-*s\scroll
          If r>*s\viewR+0.5 : index=i : Break : EndIf
        Next
        steps=steps-1
      Else
        For i=*s\count-1 To 0 Step -1
          *n=nctNode(*s,i) : cx=*s\x+4.0* *s\scale+*n\pos-*s\scroll
          If cx<*s\viewL-0.5 : index=i : Break : EndIf
        Next
        steps=steps+1
      EndIf
      If index>=0 : nctReveal(*s,index) : EndIf
    Wend
  EndIf
  nctLayout(*s) : id=0 : If blocked=0 : id=NeonChromeTabAt(*s,x,y) : EndIf
  *s\hoverIndex=-1 : If id>0 : *s\hoverIndex=nctFind(*s,id) : EndIf
  If id>0 And used=0 And *s\pressed<>0
    index=nctFind(*s,id) : *n=nctNode(*s,index)
    cx=*s\x+4.0* *s\scale+*n\pos-*s\scroll : bx=cx+*n\width-*s\side-*s\scale : by=*s\y+(*s\h-1.0-*s\side)/2.0
    hx=bx : hw=*s\side
    If hx<*s\viewL : hw=hw-(*s\viewL-hx) : hx=*s\viewL : EndIf
    If hx+hw>*s\viewR : hw=*s\viewR-hx : EndIf
    If *s\withClose<>0 And hw>0.0 And x>=hx And x<hx+hw And y>=by And y<by+*s\side
      If *n\style=#NCT_PINNED : *s\pinId=id : Else : *s\closedId=id : EndIf
    Else
      *s\activeId=id
    EndIf
  EndIf
  For i=0 To *s\count-1
    *n=nctNode(*s,i)
    *n\hover=nctEase(*s,*n\hover,MathFFromInt(Bool(i=*s\hoverIndex)),18.0,dt)
  Next
  left=Bool(blocked=0 And *s\scroll>0.0 And x>=*s\x And x<*s\x+*s\arrowW And y>=*s\y And y<*s\y+*s\h-1.0)
  right=Bool(blocked=0 And *s\scroll<*s\maxScroll And x>=*s\x+*s\w-*s\arrowW And x<*s\x+*s\w And y>=*s\y And y<*s\y+*s\h-1.0)
  *s\leftHover=nctEase(*s,*s\leftHover,MathFFromInt(left),18.0,dt) : *s\rightHover=nctEase(*s,*s\rightHover,MathFFromInt(right),18.0,dt)
  index=nctFind(*s,*s\activeId)
  If index>=0
    *n=nctNode(*s,index)
    If *s\indicatorReady=0 : *s\indicatorX=*s\x+4.0* *s\scale+*n\pos : *s\indicatorW=*n\width : *s\indicatorReady=1 : EndIf
    *s\indicatorX=nctEase(*s,*s\indicatorX,*s\x+4.0* *s\scale+*n\pos,22.0,dt)
    *s\indicatorW=nctEase(*s,*s\indicatorW,*n\width,22.0,dt)
  EndIf
  If *s\scroll<>oldScroll Or (*s\pressed<>0 And id>0) : *s\needsRedraw=1 : EndIf
  ProcedureReturn nctFail(*s,0)
EndProcedure
Procedure.i NeonChromeTabsCloseGet(*s.NeonChromeTabState)
  Protected id.i
  If nctValid(*s)=0 : ProcedureReturn #NCT_ERR_STATE : EndIf
  If nctBusy<>0 : ProcedureReturn nctFail(*s,#NCT_ERR_BUSY) : EndIf
  id=*s\closedId : *s\closedId=0 : ProcedureReturn id
EndProcedure
Procedure.i NeonChromeTabsPinGet(*s.NeonChromeTabState)
  Protected id.i
  If nctValid(*s)=0 : ProcedureReturn #NCT_ERR_STATE : EndIf
  If nctBusy<>0 : ProcedureReturn nctFail(*s,#NCT_ERR_BUSY) : EndIf
  id=*s\pinId : *s\pinId=0 : ProcedureReturn id
EndProcedure

Procedure nctDrawBox(x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
  Protected rc.i
  If nctDrawError<>0 : ProcedureReturn : EndIf
  rc=nctStatus(nctBox(x,y,w,h,r,g,b,a)) : If rc<>0 : nctDrawError=rc : EndIf
EndProcedure
Procedure nctDrawText(font.i,x.f,y.f,text.i,r.f,g.f,b.f)
  Protected rc.i
  If nctDrawError<>0 : ProcedureReturn : EndIf
  rc=nctStatus(nctText(font,x,y,text,r,g,b,1.0)) : If rc<>0 : nctDrawError=rc : EndIf
EndProcedure
Procedure nctDrawClip(x.f,y.f,w.f,h.f)
  Protected rc.i
  If nctDrawError<>0 : ProcedureReturn : EndIf
  rc=nctStatus(nctClip(x,y,w,h)) : If rc<>0 : nctDrawError=rc : EndIf
EndProcedure
Procedure.i NeonChromeTabsDraw(*s.NeonChromeTabState)
  Protected i.i,active.i,onX.i,rc.i,side.i,*n.NeonChromeTab
  Protected cx.f,bx.f,by.f,hx.f,hw.f,u.f,r.f,g.f,b.f,ax.f,hover.f,arrowText.i,arrowWidth.f
  If nctValid(*s)=0 : ProcedureReturn #NCT_ERR_STATE : EndIf
  If nctBusy<>0 : ProcedureReturn nctFail(*s,#NCT_ERR_BUSY) : EndIf
  If *s\ready=0 : ProcedureReturn nctFail(*s,#NCT_ERR_STATE) : EndIf
  If nctActive=0 : ProcedureReturn nctFail(*s,#NCT_ERR_RENDERER) : EndIf
  nstyEnter() : nctBusy=1 : nctDrawError=0 : *s\cleanupError=0
  rc=nctStatus(nctClear()) : If rc<>0 : nctDrawError=rc : EndIf
  nctDrawBox(*s\x,*s\y,*s\w,*s\h,nstyPalette\bg\r,nstyPalette\bg\g,nstyPalette\bg\b,1.0)
  nctDrawBox(*s\x,*s\y+*s\h-1.0,*s\w,1.0,nstyPalette\line\r,nstyPalette\line\g,nstyPalette\line\b,1.0)
  nctDrawClip(*s\viewL,*s\y,*s\viewR-*s\viewL,*s\h)
  For i=0 To *s\count-1
    *n=nctNode(*s,i)
    If *n\visibleW<=0.0 : Continue : EndIf
    cx=*s\x+4.0* *s\scale+*n\pos-*s\scroll : active=Bool(*n\id=*s\activeId)
    If nctDrawError=0 : nctDrawError=nhzEmitClip(5,*s,*n\id,cx,*s\y,*n\width,*s\h-1.0,*s\viewL,*s\y,*s\viewR-*s\viewL,*s\h) : EndIf
    r=nstyPalette\dim\r : g=nstyPalette\dim\g : b=nstyPalette\dim\b
    If active<>0
      nctDrawBox(cx,*s\y,*n\width,*s\h-1.0,nstyPalette\panel\r,nstyPalette\panel\g,nstyPalette\panel\b,1.0)
      nctDrawBox(cx,*s\y,1.0,*s\h-1.0,nstyPalette\line\r,nstyPalette\line\g,nstyPalette\line\b,1.0)
      nctDrawBox(cx+*n\width-1.0,*s\y,1.0,*s\h-1.0,nstyPalette\line\r,nstyPalette\line\g,nstyPalette\line\b,1.0)
      r=nstyPalette\text\r : g=nstyPalette\text\g : b=nstyPalette\text\b
    ElseIf *n\hover>0.0
      nctDrawBox(cx,*s\y+2.0,*n\width,*s\h-3.0,nstyPalette\head\r,nstyPalette\head\g,nstyPalette\head\b,*n\hover)
    EndIf
    nctDrawText(*n\font,cx+12.0* *s\scale,*s\y+(*s\h-*s\uiH)/2.0,*n\shown,r,g,b)
    If *s\withClose<>0
      bx=cx+*n\width-*s\side-*s\scale : by=*s\y+(*s\h-1.0-*s\side)/2.0
      hx=bx : hw=*s\side
      If hx<*s\viewL : hw=hw-(*s\viewL-hx) : hx=*s\viewL : EndIf
      If hx+hw>*s\viewR : hw=*s\viewR-hx : EndIf
      If hw>0.0
        If nctDrawError=0 : nctDrawError=nhzEmit(6,*s,*n\id,hx,by,hw,*s\side) : EndIf
        onX=Bool(*s\blocked=0 And *s\hoverIndex=i And *s\mouseX>=hx And *s\mouseX<hx+hw And *s\mouseY>=by And *s\mouseY<by+*s\side)
        If *n\style=#NCT_PINNED
          r=nstyPalette\dim\r : g=nstyPalette\dim\g : b=nstyPalette\dim\b
          If onX<>0
            nctDrawBox(hx,by,hw,*s\side,nstyPalette\head\r,nstyPalette\head\g,nstyPalette\head\b,1.0) : r=nstyPalette\text\r : g=nstyPalette\text\g : b=nstyPalette\text\b
          ElseIf active<>0 : r=nstyPalette\accent\r : g=nstyPalette\accent\g : b=nstyPalette\accent\b : EndIf
          u=*s\side/9.0
          nctDrawBox(bx+3.0*u,by+1.5*u,3.0*u,3.0*u,r,g,b,1.0)
          nctDrawBox(bx+2.0*u,by+4.5*u,5.0*u,1.0*u,r,g,b,1.0)
          nctDrawBox(bx+4.0*u,by+5.5*u,1.0*u,2.5*u,r,g,b,1.0)
        Else
          If onX<>0 : nctDrawBox(hx,by,hw,*s\side,nstyPalette\red\r*0.5,nstyPalette\red\g*0.35,nstyPalette\red\b*0.35,1.0) : EndIf
          nctDrawText(*s\smallFont,bx+(*s\side-*s\crossW)/2.0,by+(*s\side-*s\smallH)/2.0,"x",nstyPalette\dim\r,nstyPalette\dim\g,nstyPalette\dim\b)
        EndIf
      EndIf
    EndIf
  Next
  If *s\activeId>0 And *s\indicatorReady<>0 : nctDrawBox(*s\indicatorX-*s\scroll,*s\y,*s\indicatorW,2.0,nstyPalette\accent\r,nstyPalette\accent\g,nstyPalette\accent\b,1.0) : EndIf
  If *s\maxScroll>0.0
    nctDrawClip(*s\x,*s\y,*s\w,*s\h)
    For side=0 To 1
      If (side=0 And *s\scroll<=0.0) Or (side=1 And *s\scroll>=*s\maxScroll) : Continue : EndIf
      ax=*s\x : hover=*s\leftHover : arrowText="<" : arrowWidth=*s\leftW
      If side=1 : ax=*s\x+*s\w-*s\arrowW : hover=*s\rightHover : arrowText=">" : arrowWidth=*s\rightW : EndIf
      If nctDrawError=0 : nctDrawError=nhzEmit(11,*s,side,ax,*s\y,*s\arrowW,*s\h-1.0) : EndIf
      nctDrawBox(ax,*s\y,*s\arrowW,*s\h-1.0,nstyPalette\bg\r,nstyPalette\bg\g,nstyPalette\bg\b,1.0)
      If hover>0.0 : nctDrawBox(ax,*s\y+2.0,*s\arrowW,*s\h-3.0,nstyPalette\head\r,nstyPalette\head\g,nstyPalette\head\b,hover) : EndIf
      bx=ax : If side=0 : bx=ax+*s\arrowW-1.0 : EndIf
      nctDrawBox(bx,*s\y,1.0,*s\h-1.0,nstyPalette\line\r,nstyPalette\line\g,nstyPalette\line\b,1.0)
      nctDrawText(*s\smallFont,ax+(*s\arrowW-arrowWidth)/2.0,*s\y+(*s\h-1.0-*s\smallH)/2.0,arrowText,nstyPalette\dim\r,nstyPalette\dim\g,nstyPalette\dim\b)
    Next
  EndIf
  *s\cleanupError=nctStatus(nctClear()) : If nctDrawError=0 : nctDrawError=*s\cleanupError : EndIf
  If nctDrawError=0 : *s\styleRevision=NeonChromeStyleRevision() : EndIf
  nctBusy=0 : nstyLeave() : ProcedureReturn nctFail(*s,nctDrawError)
EndProcedure
Procedure.i NeonChromeTabsError(*s.NeonChromeTabState)
  If nctValid(*s)=0 : ProcedureReturn #NCT_ERR_STATE : EndIf
  ProcedureReturn *s\error
EndProcedure
Procedure.i NeonChromeTabsNeedsRedraw(*s.NeonChromeTabState)
  If nctValid(*s)=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool(*s\needsRedraw<>0 Or *s\styleRevision<>NeonChromeStyleRevision())
EndProcedure

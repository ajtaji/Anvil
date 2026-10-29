; SPDX-License-Identifier: MIT
; Prepared list/tree pane. Host owns flattened tree visibility and selection.
XIncludeFile "Anvil/Math/float32.pbi"
XIncludeFile "Anvil/Graphics/neon_chrome_style.pbi"
XIncludeFile "Anvil/Graphics/neon_chrome_hotzones.pbi"
XIncludeFile "Anvil/Graphics/neon_utf8.pbi"
XIncludeFile "Anvil/Graphics/neon_chrome_scroll.pbi"
#NCL_MAGIC=$4E434C31
#NCL_ERR_ARGS=-22200
#NCL_ERR_STATE=-22201
#NCL_ERR_BUSY=-22202
#NCL_ERR_CAPACITY=-22203
#NCL_ERR_RENDERER=-22204
#NCL_ERR_METRICS=-22205
#NCL_ERR_TEXT=-22206
Structure NeonChromeListConfig Align #PB_Structure_AlignC
  id.i : font.i : tail.i : scrollState.i
  x.f : y.f : w.f : h.f : rowH.f : scale.f
EndStructure
Structure NeonChromeListRow Align #PB_Structure_AlignC
  id.i : depth.i : selected.i : group.i : label.i : detail.i : shownLabel.i : shownDetail.i
  labelBytes.i : detailBytes.i : shownLabelBytes.i : shownDetailBytes.i
  labelW.f : detailW.f : hover.f
EndStructure
Structure NeonChromeListState Align #PB_Structure_AlignC
  magic.i : id.i : font.i : scrollState.i : arena.i : bytes.i : capacity.i : textBytes.i
  count.i : ready.i : top.i : visible.i : maxTop.i : eventId.i : hoverIndex.i
  error.i : cleanupError.i : needsRedraw.i : animating.i : wheelRemaining.i : tail.i : tailBytes.i
  x.f : y.f : w.f : h.f : rowH.f : scale.f : lineH.f
  styleRevision.i
EndStructure
Procedure.i nclBoxUnbound(x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
  ProcedureReturn #NCL_ERR_RENDERER
EndProcedure
Procedure.i nclTextUnbound(font.i,x.f,y.f,text.i,r.f,g.f,b.f,a.f)
  ProcedureReturn #NCL_ERR_RENDERER
EndProcedure
Procedure.f nclWidthUnbound(font.i,text.i)
  ProcedureReturn -1.0
EndProcedure
Procedure.f nclHeightUnbound(font.i)
  ProcedureReturn -1.0
EndProcedure
Procedure.i nclPrepareUnbound(font.i,text.i)
  ProcedureReturn #NCL_ERR_RENDERER
EndProcedure
Procedure.i nclClipUnbound(x.f,y.f,w.f,h.f)
  ProcedureReturn #NCL_ERR_RENDERER
EndProcedure
Procedure.i nclClearUnbound()
  ProcedureReturn #NCL_ERR_RENDERER
EndProcedure
Global nclBox.i=@nclBoxUnbound,nclText.i=@nclTextUnbound,nclWidth.i=@nclWidthUnbound,nclHeight.i=@nclHeightUnbound
Global nclPrepare.i=@nclPrepareUnbound,nclClip.i=@nclClipUnbound,nclClear.i=@nclClearUnbound
Global nclBusy.i,nclActive.i,nclDrawError.i
Procedure.i nclInstall(boxProc.i,textProc.i,widthProc.i,heightProc.i,prepareProc.i,clipProc.i,clearProc.i)
  If nclBusy<>0 : ProcedureReturn #NCL_ERR_BUSY : EndIf
  If boxProc=0 Or textProc=0 Or widthProc=0 Or heightProc=0 Or prepareProc=0 Or clipProc=0 Or clearProc=0 : ProcedureReturn #NCL_ERR_ARGS : EndIf
  nclBox=boxProc : nclText=textProc : nclWidth=widthProc : nclHeight=heightProc
  nclPrepare=prepareProc : nclClip=clipProc : nclClear=clearProc : nclActive=1 : ProcedureReturn 0
EndProcedure

Procedure.i nclScrollBox(x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
  ProcedureReturn nclBox(x,y,w,h,r,g,b,a)
EndProcedure
Procedure.i NeonChromeListRendererInstall(boxProc.i,textProc.i,widthProc.i,heightProc.i,prepareProc.i,clipProc.i,clearProc.i)
  Protected rc.i
  If nclBusy<>0 : ProcedureReturn #NCL_ERR_BUSY : EndIf
  If boxProc=0 Or textProc=0 Or widthProc=0 Or heightProc=0 Or prepareProc=0 Or clipProc=0 Or clearProc=0 : ProcedureReturn #NCL_ERR_ARGS : EndIf
  rc=NeonChromeScrollRendererInstall(@nclScrollBox) : If rc<>0 : ProcedureReturn rc : EndIf
  ProcedureReturn nclInstall(boxProc,textProc,widthProc,heightProc,prepareProc,clipProc,clearProc)
EndProcedure
Procedure.i nclValid(*s.NeonChromeListState)
  If *s=0 Or (*s & 7)<>0 : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool(*s\magic=#NCL_MAGIC)
EndProcedure
Procedure.i nclFail(*s.NeonChromeListState,rc.i)
  *s\error=rc : ProcedureReturn rc
EndProcedure
Procedure.i nclFinite(v.f)
  ProcedureReturn Bool((MathBitsOf(v) & $7FFFFFFF)<=$49742400)
EndProcedure
Procedure.i nclStatus(rc.i)
  If rc>0 : ProcedureReturn #NCL_ERR_RENDERER : EndIf
  ProcedureReturn rc
EndProcedure
Procedure.i nclRow(*s.NeonChromeListState,index.i)
  ProcedureReturn *s\arena+index*SizeOf(NeonChromeListRow)
EndProcedure
Procedure.i NeonChromeListGet(*s.NeonChromeListState,id.i)
  Protected i.i,*row.NeonChromeListRow
  If nclValid(*s)=0 Or id<1 : ProcedureReturn 0 : EndIf
  For i=0 To *s\count-1
    *row=nclRow(*s,i) : If *row\id=id : ProcedureReturn *row : EndIf
  Next
  ProcedureReturn 0
EndProcedure
Procedure.i NeonChromeListRequiredBytes(capacity.i,textBytes.i)
  If capacity<1 Or capacity>4096 Or textBytes<4 Or textBytes>512 : ProcedureReturn 0 : EndIf
  ProcedureReturn capacity*(SizeOf(NeonChromeListRow)+4*textBytes)+16
EndProcedure
Procedure.i nclOverlap(a.i,n.i,b.i,m.i)
  ProcedureReturn Bool(a<b+m And b<a+n)
EndProcedure
Procedure.i NeonChromeListConfigure(*s.NeonChromeListState,arena.i,bytes.i,capacity.i,textBytes.i,*c.NeonChromeListConfig)
  Protected needed.i=NeonChromeListRequiredBytes(capacity,textBytes),i.i,tail.i,tailN.i,*scroll.NeonChromeScrollState
  If nclBusy<>0 : ProcedureReturn #NCL_ERR_BUSY : EndIf
  If *s=0 Or (*s & 7)<>0 Or *c=0 Or (*c & 7)<>0 : ProcedureReturn #NCL_ERR_ARGS : EndIf
  If needed=0 Or arena<1 Or (arena & 7)<>0 Or bytes<needed Or arena+needed-1<arena : ProcedureReturn #NCL_ERR_ARGS : EndIf
  If nclOverlap(arena,needed,*s,SizeOf(NeonChromeListState)) Or nclOverlap(arena,needed,*c,SizeOf(NeonChromeListConfig)) Or nclOverlap(*s,SizeOf(NeonChromeListState),*c,SizeOf(NeonChromeListConfig)) : ProcedureReturn #NCL_ERR_ARGS : EndIf
  If *c\id<1 Or *c\id>2146583647 Or *c\font<0 Or ncsValid(*c\scrollState)=0 : ProcedureReturn #NCL_ERR_ARGS : EndIf
  *scroll=*c\scrollState
  If *scroll\scale<>*c\scale : ProcedureReturn #NCL_ERR_ARGS : EndIf
  If nclOverlap(arena,needed,*c\scrollState,SizeOf(NeonChromeScrollState)) Or nclOverlap(*s,SizeOf(NeonChromeListState),*c\scrollState,SizeOf(NeonChromeScrollState)) : ProcedureReturn #NCL_ERR_ARGS : EndIf
  If nclFinite(*c\x)=0 Or nclFinite(*c\y)=0 Or nclFinite(*c\w)=0 Or nclFinite(*c\h)=0 Or nclFinite(*c\rowH)=0 Or nclFinite(*c\scale)=0 : ProcedureReturn #NCL_ERR_ARGS : EndIf
  If *c\scale<=0.4 Or *c\scale>16.0 Or *c\w<=24.0* *c\scale Or *c\w>8192.0 Or *c\h<=4.0 Or *c\h>8192.0 Or *c\rowH<1.0 Or *c\rowH>*c\h Or nclFinite(*c\x+*c\w)=0 Or nclFinite(*c\y+*c\h)=0 : ProcedureReturn #NCL_ERR_ARGS : EndIf
  tail=*c\tail : If tail=0 : tail="..." : EndIf
  tailN=NeonUtf8Length(tail,16) : If tailN<0 Or tailN>=textBytes : ProcedureReturn #NCL_ERR_TEXT : EndIf
  If nclOverlap(tail,tailN+1,arena,needed) Or nclOverlap(tail,tailN+1,*s,SizeOf(NeonChromeListState)) : ProcedureReturn #NCL_ERR_ARGS : EndIf
  For i=0 To SizeOf(NeonChromeListState)-8 Step 8 : PokeI(*s+i,0) : Next
  *s\magic=#NCL_MAGIC : *s\id=*c\id : *s\font=*c\font : *s\scrollState=*c\scrollState : *s\arena=arena : *s\bytes=needed : *s\capacity=capacity : *s\textBytes=textBytes
  *s\x=*c\x : *s\y=*c\y : *s\w=*c\w : *s\h=*c\h : *s\rowH=*c\rowH : *s\scale=*c\scale
  *s\visible=Int(*s\h / *s\rowH) : *s\hoverIndex=-1 : *s\needsRedraw=1
  *s\tail=arena+capacity*(SizeOf(NeonChromeListRow)+4*textBytes) : *s\tailBytes=tailN
  For i=0 To tailN : PokeA(*s\tail+i,PeekA(tail+i)) : Next
  ProcedureReturn 0
EndProcedure
Procedure.i NeonChromeListBeginBuild(*s.NeonChromeListState)
  If nclValid(*s)=0 : ProcedureReturn #NCL_ERR_STATE : EndIf
  If nclBusy<>0 : ProcedureReturn nclFail(*s,#NCL_ERR_BUSY) : EndIf
  *s\count=0 : *s\ready=0 : *s\animating=0 : *s\eventId=0 : *s\hoverIndex=-1 : *s\needsRedraw=1
  ProcedureReturn nclFail(*s,0)
EndProcedure
Procedure.i NeonChromeListAdd(*s.NeonChromeListState,id.i,label.i,depth.i,selected.i,group.i,detail.i)
  Protected n.i,m.i,i.i,dest.i,*row.NeonChromeListRow
  If nclValid(*s)=0 : ProcedureReturn #NCL_ERR_STATE : EndIf
  If nclBusy<>0 : ProcedureReturn nclFail(*s,#NCL_ERR_BUSY) : EndIf
  If *s\ready<>0 : ProcedureReturn nclFail(*s,#NCL_ERR_STATE) : EndIf
  If id<1 Or NeonChromeListGet(*s,id)<>0 Or depth<0 Or depth>4096 Or (selected<>0 And selected<>1) Or (group<>0 And group<>1) : ProcedureReturn nclFail(*s,#NCL_ERR_ARGS) : EndIf
  If *s\count>=*s\capacity : ProcedureReturn nclFail(*s,#NCL_ERR_CAPACITY) : EndIf
  If detail=0 : detail="" : EndIf
  n=NeonUtf8Length(label,*s\textBytes) : m=NeonUtf8Length(detail,*s\textBytes)
  If n<0 Or m<0 : ProcedureReturn nclFail(*s,#NCL_ERR_TEXT) : EndIf
  dest=*s\arena+*s\capacity*SizeOf(NeonChromeListRow)+*s\count*4* *s\textBytes : *row=nclRow(*s,*s\count)
  If nclOverlap(label,n+1,*s\arena,*s\bytes) Or nclOverlap(detail,m+1,*s\arena,*s\bytes) Or nclOverlap(label,n+1,*s,SizeOf(NeonChromeListState)) Or nclOverlap(detail,m+1,*s,SizeOf(NeonChromeListState)) : ProcedureReturn nclFail(*s,#NCL_ERR_ARGS) : EndIf
  For i=0 To SizeOf(NeonChromeListRow)-8 Step 8 : PokeI(*row+i,0) : Next
  *row\id=id : *row\depth=depth : *row\selected=selected : *row\group=group
  *row\label=dest : *row\detail=dest+*s\textBytes : *row\shownLabel=dest+2* *s\textBytes : *row\shownDetail=dest+3* *s\textBytes
  *row\labelBytes=n : *row\detailBytes=m
  For i=0 To n : PokeA(*row\label+i,PeekA(label+i)) : Next
  For i=0 To m : PokeA(*row\detail+i,PeekA(detail+i)) : Next
  *s\count=*s\count+1 : ProcedureReturn nclFail(*s,0)
EndProcedure
Procedure.i nclFit(*s.NeonChromeListState,source.i,bytes.i,dest.i,room.f)
  Protected low.i,high.i,half.i,cut.i,best.i,i.i,width.f,tailW.f
  PokeA(dest,0) : If room<=0.0 : ProcedureReturn 0 : EndIf
  width=nclWidth(*s\font,source)
  If nclFinite(width)=0 Or width<0.0 : ProcedureReturn #NCL_ERR_METRICS : EndIf
  If width<=room
    For i=0 To bytes : PokeA(dest+i,PeekA(source+i)) : Next
    ProcedureReturn bytes
  EndIf
  tailW=nclWidth(*s\font,*s\tail)
  If nclFinite(tailW)=0 Or tailW<0.0 : ProcedureReturn #NCL_ERR_METRICS : EndIf
  If room<tailW : ProcedureReturn 0 : EndIf
  high=bytes-1
  While low<high
    half=(low+high+1)/2 : cut=NeonUtf8Prefix(source,bytes,half)
    If cut+*s\tailBytes>=*s\textBytes : high=half-1 : Continue : EndIf
    For i=0 To cut-1 : PokeA(dest+i,PeekA(source+i)) : Next
    For i=0 To *s\tailBytes : PokeA(dest+cut+i,PeekA(*s\tail+i)) : Next
    width=nclWidth(*s\font,dest)
    If nclFinite(width)=0 Or width<0.0 : ProcedureReturn #NCL_ERR_METRICS : EndIf
    If width<=room : low=half : best=cut : Else : high=half-1 : EndIf
  Wend
  For i=0 To best-1 : PokeA(dest+i,PeekA(source+i)) : Next
  For i=0 To *s\tailBytes : PokeA(dest+best+i,PeekA(*s\tail+i)) : Next
  width=nclWidth(*s\font,dest)
  If nclFinite(width)=0 Or width<0.0 Or width>room : ProcedureReturn #NCL_ERR_METRICS : EndIf
  ProcedureReturn best+*s\tailBytes
EndProcedure
Procedure nclClamp(*s.NeonChromeListState)
  *s\maxTop=*s\count-*s\visible : If *s\maxTop<0 : *s\maxTop=0 : EndIf
  If *s\top<0 : *s\top=0 : EndIf
  If *s\top>*s\maxTop : *s\top=*s\maxTop : EndIf
EndProcedure
Procedure.i NeonChromeListSeal(*s.NeonChromeListState)
  Protected i.i,n.i,rc.i,*row.NeonChromeListRow,lx.f,room.f,h.f
  If nclValid(*s)=0 : ProcedureReturn #NCL_ERR_STATE : EndIf
  If nclBusy<>0 : ProcedureReturn nclFail(*s,#NCL_ERR_BUSY) : EndIf
  If nclActive=0 : ProcedureReturn nclFail(*s,#NCL_ERR_RENDERER) : EndIf
  *s\ready=0 : nclBusy=1 : h=nclHeight(*s\font)
  If nclFinite(h)=0 Or h<=0.0 Or h>8192.0 : rc=#NCL_ERR_METRICS : EndIf
  For i=0 To *s\count-1
    If rc<>0 : Break : EndIf
    *row=nclRow(*s,i) : room=*s\w-(24.0+MathFFromInt(*row\depth)*14.0)* *s\scale
    n=nclFit(*s,*row\label,*row\labelBytes,*row\shownLabel,room)
    If n<0 : rc=n : Break : EndIf
    *row\shownLabelBytes=n : *row\labelW=nclWidth(*s\font,*row\shownLabel)
    If nclFinite(*row\labelW)=0 Or *row\labelW<0.0 : rc=#NCL_ERR_METRICS : Break : EndIf
    n=nclFit(*s,*row\detail,*row\detailBytes,*row\shownDetail,room-*row\labelW-12.0* *s\scale)
    If n<0 : rc=n : Break : EndIf
    *row\shownDetailBytes=n : *row\detailW=nclWidth(*s\font,*row\shownDetail)
    If nclFinite(*row\detailW)=0 Or *row\detailW<0.0 : rc=#NCL_ERR_METRICS : Break : EndIf
    rc=nclStatus(nclPrepare(*s\font,*row\shownLabel))
    If rc=0 : rc=nclStatus(nclPrepare(*s\font,*row\shownDetail)) : EndIf
  Next
  nclBusy=0
  If rc=0 : *s\lineH=h : *s\ready=1 : nclClamp(*s) : *s\needsRedraw=1 : EndIf
  ProcedureReturn nclFail(*s,rc)
EndProcedure
Procedure.i NeonChromeListItemState(*s.NeonChromeListState,id.i,selected.i,group.i)
  Protected *row.NeonChromeListRow
  If nclValid(*s)=0 : ProcedureReturn #NCL_ERR_STATE : EndIf
  If nclBusy<>0 : ProcedureReturn nclFail(*s,#NCL_ERR_BUSY) : EndIf
  *row=NeonChromeListGet(*s,id)
  If *row=0 Or (selected<>0 And selected<>1) Or (group<>0 And group<>1) : ProcedureReturn nclFail(*s,#NCL_ERR_ARGS) : EndIf
  *row\selected=selected : *row\group=group : *s\needsRedraw=1 : ProcedureReturn nclFail(*s,0)
EndProcedure
Procedure.i NeonChromeListScrollTo(*s.NeonChromeListState,top.i)
  If nclValid(*s)=0 : ProcedureReturn #NCL_ERR_STATE : EndIf
  If nclBusy<>0 : ProcedureReturn nclFail(*s,#NCL_ERR_BUSY) : EndIf
  If *s\ready=0 : ProcedureReturn nclFail(*s,#NCL_ERR_STATE) : EndIf
  *s\top=top : nclClamp(*s) : *s\needsRedraw=1 : ProcedureReturn nclFail(*s,0)
EndProcedure
Procedure.i NeonChromeListAt(*s.NeonChromeListState,x.f,y.f)
  Protected index.i,*row.NeonChromeListRow
  If nclValid(*s)=0 Or *s\ready=0 Or nclFinite(x)=0 Or nclFinite(y)=0 : ProcedureReturn 0 : EndIf
  If x<*s\x Or x>=*s\x+*s\w-10.0* *s\scale Or y<*s\y Or y>=*s\y+*s\h : ProcedureReturn 0 : EndIf
  index=*s\top+Int((y-*s\y) / *s\rowH)
  If index<0 Or index>=*s\count : ProcedureReturn 0 : EndIf
  *row=nclRow(*s,index) : ProcedureReturn *row\id
EndProcedure
Procedure.i NeonChromeListInput(*s.NeonChromeListState,wheel.i,blocked.i,dt.f)
  Protected *scroll.NeonChromeScrollState,i.i,rc.i,over.i,id.i,old.i,weight.f,target.f,*row.NeonChromeListRow
  If nclValid(*s)=0 : ProcedureReturn #NCL_ERR_STATE : EndIf
  If nclBusy<>0 : ProcedureReturn nclFail(*s,#NCL_ERR_BUSY) : EndIf
  If *s\ready=0 : ProcedureReturn nclFail(*s,#NCL_ERR_STATE) : EndIf
  If wheel < -128 Or wheel>128 Or (blocked<>0 And blocked<>1) Or nclFinite(dt)=0 Or dt<0.0 : ProcedureReturn nclFail(*s,#NCL_ERR_ARGS) : EndIf
  *scroll=*s\scrollState
  If ncsValid(*scroll)=0 Or *scroll\inputReady=0 : ProcedureReturn nclFail(*s,#NCL_ERR_STATE) : EndIf
  *s\eventId=0 : *s\animating=0 : *s\wheelRemaining=wheel : old=*s\top
  over=Bool(*scroll\mouseX>=*s\x And *scroll\mouseX<*s\x+*s\w And *scroll\mouseY>=*s\y And *scroll\mouseY<*s\y+*s\h)
  If blocked=0 And over<>0 And wheel<>0 : *s\top=*s\top-wheel*3 : *s\wheelRemaining=0 : nclClamp(*s) : EndIf
  If blocked=0
    rc=NeonChromeScrollUpdateV(*scroll,*s\id+900000,*s\x+*s\w-10.0* *s\scale,*s\y,10.0* *s\scale,*s\h,*s\count,*s\visible,@*s\top)
    If rc<0 : ProcedureReturn nclFail(*s,rc) : EndIf
  EndIf
  If old<>*s\top : *s\needsRedraw=1 : EndIf
  id=0 : If blocked=0 : id=NeonChromeListAt(*s,*scroll\mouseX,*scroll\mouseY) : EndIf
  *s\hoverIndex=-1
  If dt>0.05 : dt=0.05 : EndIf
  weight=1.0-Exp(-20.0*dt)
  If nstyAnimations=0 : weight=1.0 : EndIf
  For i=0 To *s\count-1
    *row=nclRow(*s,i) : target=0.0
    If *row\id=id : target=1.0 : *s\hoverIndex=i : EndIf
    If *row\hover<>target
      *row\hover=*row\hover+(target-*row\hover)*weight
      If Abs(*row\hover-target)<0.002 : *row\hover=target : EndIf
      *s\needsRedraw=1
      If *row\hover<>target : *s\animating=1 : EndIf
    EndIf
  Next
  If id<>0 And *scroll\pressed<>0 : *s\eventId=id : EndIf
  ProcedureReturn nclFail(*s,0)
EndProcedure
Procedure.i NeonChromeListEventGet(*s.NeonChromeListState)
  Protected id.i
  If nclValid(*s)=0 : ProcedureReturn 0 : EndIf
  If nclBusy<>0 : ProcedureReturn #NCL_ERR_BUSY : EndIf
  id=*s\eventId : *s\eventId=0 : ProcedureReturn id
EndProcedure
Procedure nclDrawBox(x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
  Protected rc.i
  If nclDrawError<>0 : ProcedureReturn : EndIf
  rc=nclStatus(nclBox(x,y,w,h,r,g,b,a)) : If rc<>0 : nclDrawError=rc : EndIf
EndProcedure
Procedure nclDrawText(font.i,x.f,y.f,text.i,r.f,g.f,b.f)
  Protected rc.i
  If nclDrawError<>0 : ProcedureReturn : EndIf
  rc=nclStatus(nclText(font,x,y,text,r,g,b,1.0)) : If rc<>0 : nclDrawError=rc : EndIf
EndProcedure
Procedure nclDrawClip(x.f,y.f,w.f,h.f)
  Protected rc.i
  If nclDrawError<>0 : ProcedureReturn : EndIf
  rc=nclStatus(nclClip(x,y,w,h)) : If rc<>0 : nclDrawError=rc : EndIf
EndProcedure

Procedure.i NeonChromeListDraw(*s.NeonChromeListState)
  Protected i.i,rc.i,*row.NeonChromeListRow,y.f,x.f,r.f,g.f,b.f
  If nclValid(*s)=0 : ProcedureReturn #NCL_ERR_STATE : EndIf
  If nclBusy<>0 : ProcedureReturn nclFail(*s,#NCL_ERR_BUSY) : EndIf
  If *s\ready=0 : ProcedureReturn nclFail(*s,#NCL_ERR_STATE) : EndIf
  If nclActive=0 : ProcedureReturn nclFail(*s,#NCL_ERR_RENDERER) : EndIf
  nstyEnter() : nclBusy=1 : nclDrawError=0 : *s\cleanupError=0
  rc=nclStatus(nclClear()) : If rc<>0 : nclDrawError=rc : EndIf
  nclDrawBox(*s\x,*s\y,*s\w,*s\h,nstyPalette\list\r,nstyPalette\list\g,nstyPalette\list\b,1.0)
  nclDrawClip(*s\x,*s\y,*s\w-10.0* *s\scale,*s\h)
  For i=*s\top To *s\count-1
    y=*s\y+MathFFromInt(i-*s\top)* *s\rowH : If y>=*s\y+*s\h : Break : EndIf
    *row=nclRow(*s,i)
    If nclDrawError=0 : nclDrawError=nhzEmitClip(10,*s,*row\id,*s\x,y,*s\w-10.0* *s\scale,*s\rowH,*s\x,*s\y,*s\w-10.0* *s\scale,*s\h) : EndIf
    If *row\selected<>0
      nclDrawBox(*s\x,y,*s\w-10.0* *s\scale,*s\rowH,nstyPalette\accent\r*0.30,nstyPalette\accent\g*0.30,nstyPalette\accent\b*0.34,1.0)
      nclDrawBox(*s\x,y,2.0* *s\scale,*s\rowH,nstyPalette\accent\r,nstyPalette\accent\g,nstyPalette\accent\b,1.0)
    ElseIf *row\hover>0.0 : nclDrawBox(*s\x,y,*s\w-10.0* *s\scale,*s\rowH,nstyPalette\head\r,nstyPalette\head\g,nstyPalette\head\b,*row\hover) : EndIf
    r=nstyPalette\text\r : g=nstyPalette\text\g : b=nstyPalette\text\b
    If *row\group<>0 : r=nstyPalette\amber\r : g=nstyPalette\amber\g : b=nstyPalette\amber\b
    ElseIf *row\selected<>0 : r=nstyPalette\accent\r : g=nstyPalette\accent\g : b=nstyPalette\accent\b : EndIf
    x=*s\x+(8.0+MathFFromInt(*row\depth)*14.0)* *s\scale
    nclDrawText(*s\font,x,y+(*s\rowH-*s\lineH)/2.0,*row\shownLabel,r,g,b)
    If *row\detailBytes>0 : nclDrawText(*s\font,*s\x+*s\w-16.0* *s\scale-*row\detailW,y+(*s\rowH-*s\lineH)/2.0,*row\shownDetail,nstyPalette\faint\r,nstyPalette\faint\g,nstyPalette\faint\b) : EndIf
  Next
  *s\cleanupError=nclStatus(nclClear())
  If nclDrawError=0 : nclDrawError=*s\cleanupError : EndIf
  If nclDrawError=0
    rc=NeonChromeScrollPaintV(*s\scrollState,*s\id+900000,*s\x+*s\w-10.0* *s\scale,*s\y,10.0* *s\scale,*s\h,*s\count,*s\visible,@*s\top)
    If rc<0 : nclDrawError=rc : EndIf
  EndIf
  *s\cleanupError=nclStatus(nclClear()) : If nclDrawError=0 : nclDrawError=*s\cleanupError : EndIf
  If nclDrawError=0 : *s\styleRevision=NeonChromeStyleRevision() : EndIf
  nclBusy=0 : nstyLeave() : If nclDrawError=0 : *s\needsRedraw=*s\animating : EndIf
  ProcedureReturn nclFail(*s,nclDrawError)
EndProcedure
Procedure.i NeonChromeListNeedsRedraw(*s.NeonChromeListState)
  If nclValid(*s)=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool(*s\needsRedraw<>0 Or *s\styleRevision<>NeonChromeStyleRevision())
EndProcedure

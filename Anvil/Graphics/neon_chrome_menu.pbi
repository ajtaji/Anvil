; SPDX-License-Identifier: MIT
; Prepared Neon chrome menu model. Caller owns storage, input and frame lifetime.
; Build/Seal runs outside a frame; Draw borrows no caller strings or driver state.
XIncludeFile "Anvil/Math/float32.pbi"
XIncludeFile "Anvil/Graphics/neon_chrome_style.pbi"
XIncludeFile "Anvil/Graphics/neon_chrome_hotzones.pbi"
XIncludeFile "Anvil/Math/float32_convert.pbi"
#NCM_MAGIC=$4E434D31
#NCM_ROOT=0
#NCM_SUB=1
#NCM_ITEM=2
#NCM_SEPARATOR=3
#NCM_ERR_ARGS=-21800
#NCM_ERR_STATE=-21801
#NCM_ERR_BUSY=-21802
#NCM_ERR_CAPACITY=-21803
#NCM_ERR_RENDERER=-21804
#NCM_ERR_METRICS=-21805
#NCM_ERR_TEXT=-21806
Structure NeonChromeMenuNode Align #PB_Structure_AlignC
  id.i : parent.i : kind.i : enabled.i : checked.i : label.i : shortcut.i
  labelW.f : shortcutW.f : rowsH.f : panelW.f : rowOffset.f : scroll.f : tabX.f : tabW.f
EndStructure
Structure NeonChromeMenuPanel Align #PB_Structure_AlignC
  x.f : y.f : w.f : h.f : viewY.f : viewH.f : maxScroll.f
  scrolls.i
EndStructure
Structure NeonChromeMenuState Align #PB_Structure_AlignC
  magic.i : arena.i : bytes.i : capacity.i : textBytes.i : count.i : roots.i : ready.i
  font.i : smallFont.i : openRoot.i : openSub.i : down.i : pressed.i : blocked.i
  eventId.i : eventPending.i : error.i : hoverId.i : needsRedraw.i : wheelRemaining.i
  cleanupError.i : savedRoot.i : savedSub.i : hoverRoot.i
  canvasW.f : canvasH.f : scale.f : barX.f : barY.f : barW.f : barH.f
  uiH.f : smallH.f : mouseX.f : mouseY.f : savedRootScroll.f : savedSubScroll.f
  arrowW.f : upW.f : downW.f : reserved.f
  rootPanel.NeonChromeMenuPanel : subPanel.NeonChromeMenuPanel
  styleRevision.i
EndStructure
Procedure.i ncmBoxUnbound(x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
  ProcedureReturn #NCM_ERR_RENDERER
EndProcedure
Procedure.i ncmTextUnbound(font.i,x.f,y.f,text.i,r.f,g.f,b.f,a.f)
  ProcedureReturn #NCM_ERR_RENDERER
EndProcedure
Procedure.f ncmWidthUnbound(font.i,text.i)
  ProcedureReturn -1.0
EndProcedure
Procedure.f ncmHeightUnbound(font.i)
  ProcedureReturn -1.0
EndProcedure
Procedure.i ncmPrepareUnbound(font.i,text.i)
  ProcedureReturn #NCM_ERR_RENDERER
EndProcedure
Procedure.i ncmClipUnbound(x.f,y.f,w.f,h.f)
  ProcedureReturn #NCM_ERR_RENDERER
EndProcedure
Procedure.i ncmClearUnbound()
  ProcedureReturn #NCM_ERR_RENDERER
EndProcedure
Global ncmBox.i=@ncmBoxUnbound,ncmText.i=@ncmTextUnbound,ncmWidth.i=@ncmWidthUnbound,ncmHeight.i=@ncmHeightUnbound
Global ncmPrepare.i=@ncmPrepareUnbound,ncmClip.i=@ncmClipUnbound,ncmClear.i=@ncmClearUnbound
Global ncmBusy.i,ncmActive.i,ncmRenderError.i
Procedure.i NeonChromeMenuRendererInstall(boxProc.i,textProc.i,widthProc.i,heightProc.i,prepareProc.i,clipProc.i,clearProc.i)
  If ncmBusy<>0 : ProcedureReturn #NCM_ERR_BUSY : EndIf
  If boxProc=0 Or textProc=0 Or widthProc=0 Or heightProc=0 Or prepareProc=0 Or clipProc=0 Or clearProc=0 : ProcedureReturn #NCM_ERR_ARGS : EndIf
  ncmBox=boxProc : ncmText=textProc : ncmWidth=widthProc : ncmHeight=heightProc
  ncmPrepare=prepareProc : ncmClip=clipProc : ncmClear=clearProc : ncmActive=1
  ProcedureReturn 0
EndProcedure
Procedure.i ncmValid(*s.NeonChromeMenuState)
  If *s=0 Or (*s & 7)<>0 : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool(*s\magic=#NCM_MAGIC)
EndProcedure
Procedure.i ncmFinite(v.f)
  ProcedureReturn Bool((MathBitsOf(v) & $7FFFFFFF)<=$49742400)
EndProcedure
Procedure.i ncmFail(*s.NeonChromeMenuState,rc.i)
  *s\error=rc : ProcedureReturn rc
EndProcedure
Procedure.i ncmStatus(rc.i)
  If rc>0 : ProcedureReturn #NCM_ERR_RENDERER : EndIf
  ProcedureReturn rc
EndProcedure
Procedure.i ncmNode(*s.NeonChromeMenuState,index.i)
  ProcedureReturn *s\arena+index*SizeOf(NeonChromeMenuNode)
EndProcedure
Procedure.i ncmFind(*s.NeonChromeMenuState,id.i)
  Protected i.i,*n.NeonChromeMenuNode
  For i=0 To *s\count-1
    *n=ncmNode(*s,i)
    If *n\id=id And *n\kind<>#NCM_SEPARATOR : ProcedureReturn i : EndIf
  Next
  ProcedureReturn -1
EndProcedure
Procedure.i NeonChromeMenuRequiredBytes(capacity.i,textBytes.i)
  If capacity<1 Or capacity>1024 Or textBytes<1 Or textBytes>512 : ProcedureReturn 0 : EndIf
  ProcedureReturn capacity*(SizeOf(NeonChromeMenuNode)+2*textBytes)
EndProcedure
Procedure.i NeonChromeMenuConfigure(*s.NeonChromeMenuState,arena.i,bytes.i,capacity.i,textBytes.i,canvasW.i,canvasH.i,scale.f,font.i,smallFont.i)
  Protected needed.i=NeonChromeMenuRequiredBytes(capacity,textBytes),i.i
  If ncmBusy<>0 : ProcedureReturn #NCM_ERR_BUSY : EndIf
  If *s=0 Or (*s & 7)<>0 : ProcedureReturn #NCM_ERR_ARGS : EndIf
  If needed=0 Or arena<1 Or (arena & 7)<>0 Or bytes<needed Or arena+needed-1<arena : ProcedureReturn #NCM_ERR_ARGS : EndIf
  If *s+SizeOf(NeonChromeMenuState)-1<*s Or (arena<*s+SizeOf(NeonChromeMenuState) And arena+needed>*s) : ProcedureReturn #NCM_ERR_ARGS : EndIf
  If canvasW<32 Or canvasW>8192 Or canvasH<32 Or canvasH>8192 Or ncmFinite(scale)=0 Or scale<=0.0 Or scale>16.0 Or font<0 Or smallFont<0 : ProcedureReturn #NCM_ERR_ARGS : EndIf
  If MathFFromInt(canvasH)<62.0*scale+17.0 : ProcedureReturn #NCM_ERR_ARGS : EndIf
  For i=0 To SizeOf(NeonChromeMenuState)-8 Step 8 : PokeI(*s+i,0) : Next
  *s\magic=#NCM_MAGIC : *s\arena=arena : *s\bytes=needed : *s\capacity=capacity : *s\textBytes=textBytes
  *s\canvasW=MathFFromInt(canvasW) : *s\canvasH=MathFFromInt(canvasH) : *s\scale=scale
  *s\font=font : *s\smallFont=smallFont : *s\barW=*s\canvasW : *s\barH=30.0*scale
  *s\openRoot=-1 : *s\openSub=-1 : *s\hoverRoot=-1 : ProcedureReturn 0
EndProcedure
Procedure.i NeonChromeMenuBeginBuild(*s.NeonChromeMenuState)
  Protected *n.NeonChromeMenuNode
  If ncmValid(*s)=0 : ProcedureReturn #NCM_ERR_STATE : EndIf
  If ncmBusy<>0 : ProcedureReturn ncmFail(*s,#NCM_ERR_BUSY) : EndIf
  If *s\ready<>0
    *s\savedRoot=0 : *s\savedSub=0
    If *s\openRoot>=0 : *n=ncmNode(*s,*s\openRoot) : *s\savedRoot=*n\id : *s\savedRootScroll=*n\scroll : EndIf
    If *s\openSub>=0 : *n=ncmNode(*s,*s\openSub) : *s\savedSub=*n\id : *s\savedSubScroll=*n\scroll : EndIf
  EndIf
  *s\ready=0 : *s\count=0 : *s\roots=0 : *s\openRoot=-1 : *s\openSub=-1
  *s\eventPending=0 : *s\hoverId=0 : *s\needsRedraw=1
  ProcedureReturn ncmFail(*s,0)
EndProcedure
Procedure.i NeonChromeMenuBarRect(*s.NeonChromeMenuState,x.f,y.f,w.f,h.f)
  If ncmValid(*s)=0 : ProcedureReturn #NCM_ERR_STATE : EndIf
  If ncmBusy<>0 : ProcedureReturn ncmFail(*s,#NCM_ERR_BUSY) : EndIf
  If *s\ready<>0 : ProcedureReturn ncmFail(*s,#NCM_ERR_STATE) : EndIf
  If ncmFinite(x)=0 Or ncmFinite(y)=0 Or ncmFinite(w)=0 Or ncmFinite(h)=0 Or x<0.0 Or y<0.0 Or w<=0.0 Or h<=0.0 Or x+w>*s\canvasW Or y+h+32.0* *s\scale+17.0>*s\canvasH : ProcedureReturn ncmFail(*s,#NCM_ERR_ARGS) : EndIf
  *s\barX=x : *s\barY=y : *s\barW=w : *s\barH=h : ProcedureReturn ncmFail(*s,0)
EndProcedure
Procedure.i ncmLength(text.i,limit.i)
  Protected i.i
  If text=0 : ProcedureReturn 0 : EndIf
  For i=0 To limit-1
    If (PeekA(text+i) & 255)=0 : ProcedureReturn i : EndIf
  Next
  ProcedureReturn -1
EndProcedure
Procedure.i ncmAdd(*s.NeonChromeMenuState,id.i,parentId.i,kind.i,label.i,shortcut.i,enabled.i,checked.i)
  Protected parent.i=-1,ll.i,sl.i,i.i,dest.i,*n.NeonChromeMenuNode,*p.NeonChromeMenuNode
  If ncmValid(*s)=0 : ProcedureReturn #NCM_ERR_STATE : EndIf
  If ncmBusy<>0 : ProcedureReturn ncmFail(*s,#NCM_ERR_BUSY) : EndIf
  If *s\ready<>0 : ProcedureReturn ncmFail(*s,#NCM_ERR_STATE) : EndIf
  If kind<>#NCM_SEPARATOR And (id<1 Or ncmFind(*s,id)>=0) : ProcedureReturn ncmFail(*s,#NCM_ERR_ARGS) : EndIf
  If (enabled<>0 And enabled<>1) Or (checked<>0 And checked<>1) : ProcedureReturn ncmFail(*s,#NCM_ERR_ARGS) : EndIf
  If kind<>#NCM_ROOT
    parent=ncmFind(*s,parentId)
    If parent<0 : ProcedureReturn ncmFail(*s,#NCM_ERR_ARGS) : EndIf
    *p=ncmNode(*s,parent)
    If *p\kind<>#NCM_ROOT And *p\kind<>#NCM_SUB : ProcedureReturn ncmFail(*s,#NCM_ERR_ARGS) : EndIf
    If kind=#NCM_SUB And *p\kind<>#NCM_ROOT : ProcedureReturn ncmFail(*s,#NCM_ERR_ARGS) : EndIf
  EndIf
  If *s\count>=*s\capacity Or (kind=#NCM_ROOT And *s\roots>=32) : ProcedureReturn ncmFail(*s,#NCM_ERR_CAPACITY) : EndIf
  ll=ncmLength(label,*s\textBytes) : sl=ncmLength(shortcut,*s\textBytes)
  If ll<0 Or sl<0 : ProcedureReturn ncmFail(*s,#NCM_ERR_TEXT) : EndIf
  *n=ncmNode(*s,*s\count) : dest=*s\arena+*s\capacity*SizeOf(NeonChromeMenuNode)+*s\count*2* *s\textBytes
  If label<>0
    If label+ll<label Or (label<*n+SizeOf(NeonChromeMenuNode) And label+ll+1>*n) Or (label<dest+2* *s\textBytes And label+ll+1>dest) : ProcedureReturn ncmFail(*s,#NCM_ERR_ARGS) : EndIf
  EndIf
  If shortcut<>0
    If shortcut+sl<shortcut Or (shortcut<*n+SizeOf(NeonChromeMenuNode) And shortcut+sl+1>*n) Or (shortcut<dest+2* *s\textBytes And shortcut+sl+1>dest) : ProcedureReturn ncmFail(*s,#NCM_ERR_ARGS) : EndIf
  EndIf
  For i=0 To SizeOf(NeonChromeMenuNode)-8 Step 8 : PokeI(*n+i,0) : Next
  *n\id=id : *n\parent=parent : *n\kind=kind : *n\enabled=enabled : *n\checked=checked : *n\label=dest : *n\shortcut=dest+*s\textBytes
  For i=0 To ll-1 : PokeA(dest+i,PeekA(label+i)) : Next : PokeA(dest+ll,0)
  For i=0 To sl-1 : PokeA(*n\shortcut+i,PeekA(shortcut+i)) : Next : PokeA(*n\shortcut+sl,0)
  *s\count=*s\count+1 : If kind=#NCM_ROOT : *s\roots=*s\roots+1 : EndIf
  ProcedureReturn ncmFail(*s,0)
EndProcedure
Procedure.i NeonChromeMenuAddRoot(*s.NeonChromeMenuState,id.i,label.i)
  ProcedureReturn ncmAdd(*s,id,0,#NCM_ROOT,label,0,1,0)
EndProcedure
Procedure.i NeonChromeMenuAddSubmenu(*s.NeonChromeMenuState,id.i,parent.i,label.i)
  ProcedureReturn ncmAdd(*s,id,parent,#NCM_SUB,label,0,1,0)
EndProcedure
Procedure.i NeonChromeMenuAddItem(*s.NeonChromeMenuState,id.i,parent.i,label.i,shortcut.i,enabled.i,checked.i)
  ProcedureReturn ncmAdd(*s,id,parent,#NCM_ITEM,label,shortcut,enabled,checked)
EndProcedure
Procedure.i NeonChromeMenuAddSeparator(*s.NeonChromeMenuState,parent.i)
  ProcedureReturn ncmAdd(*s,0,parent,#NCM_SEPARATOR,0,0,0,0)
EndProcedure
Procedure.i NeonChromeMenuItemState(*s.NeonChromeMenuState,id.i,enabled.i,checked.i)
  Protected index.i,*n.NeonChromeMenuNode
  If ncmValid(*s)=0 : ProcedureReturn #NCM_ERR_STATE : EndIf
  If ncmBusy<>0 : ProcedureReturn ncmFail(*s,#NCM_ERR_BUSY) : EndIf
  index=ncmFind(*s,id)
  If index<0 Or (enabled<>0 And enabled<>1) Or (checked<>0 And checked<>1) : ProcedureReturn ncmFail(*s,#NCM_ERR_ARGS) : EndIf
  *n=ncmNode(*s,index) : If *n\kind<>#NCM_ITEM : ProcedureReturn ncmFail(*s,#NCM_ERR_ARGS) : EndIf
  *n\enabled=enabled : *n\checked=checked : *s\needsRedraw=1 : ProcedureReturn ncmFail(*s,0)
EndProcedure
Procedure.i NeonChromeMenuSeal(*s.NeonChromeMenuState)
  Protected i.i,j.i,rc.i,cursor.f,need.f,rows.f,*n.NeonChromeMenuNode,*p.NeonChromeMenuNode
  If ncmValid(*s)=0 : ProcedureReturn #NCM_ERR_STATE : EndIf
  If ncmBusy<>0 : ProcedureReturn ncmFail(*s,#NCM_ERR_BUSY) : EndIf
  If ncmActive=0 : ProcedureReturn ncmFail(*s,#NCM_ERR_RENDERER) : EndIf
  If *s\ready<>0 : ProcedureReturn ncmFail(*s,#NCM_ERR_STATE) : EndIf
  ncmBusy=1 : *s\uiH=ncmHeight(*s\font) : *s\smallH=ncmHeight(*s\smallFont)
  If ncmFinite(*s\uiH)=0 Or ncmFinite(*s\smallH)=0 Or *s\uiH<=0.0 Or *s\smallH<=0.0 : rc=#NCM_ERR_METRICS : EndIf
  For i=0 To *s\count-1
    If rc<>0 : Break : EndIf
    *n=ncmNode(*s,i)
    rc=ncmStatus(ncmPrepare(*s\font,*n\label))
    If rc=0 : rc=ncmStatus(ncmPrepare(*s\smallFont,*n\shortcut)) : EndIf
    If rc<>0 : Break : EndIf
    *n\labelW=ncmWidth(*s\font,*n\label) : *n\shortcutW=ncmWidth(*s\smallFont,*n\shortcut)
    If ncmFinite(*n\labelW)=0 Or ncmFinite(*n\shortcutW)=0 Or *n\labelW<0.0 Or *n\shortcutW<0.0 : rc=#NCM_ERR_METRICS : Break : EndIf
    *n\rowsH=0.0 : *n\panelW=160.0* *s\scale
    If *n\kind=#NCM_SUB : *n\panelW=180.0* *s\scale : EndIf
  Next
  If rc=0
    cursor=*s\barX+8.0* *s\scale
    For i=0 To *s\count-1
      *n=ncmNode(*s,i)
      If *n\kind=#NCM_ROOT
        *n\tabX=cursor : *n\tabW=*n\labelW+24.0* *s\scale : cursor=cursor+*n\tabW
      Else
        *p=ncmNode(*s,*n\parent) : *n\rowOffset=*p\rowsH
        If *n\kind=#NCM_SEPARATOR
          *p\rowsH=*p\rowsH+9.0* *s\scale
        Else
          *p\rowsH=*p\rowsH+24.0* *s\scale
          need=46.0* *s\scale+*n\labelW
          If *n\kind=#NCM_SUB : need=68.0* *s\scale+*n\labelW : EndIf
          If *n\shortcutW>0.0 : need=need+46.0* *s\scale+*n\shortcutW : EndIf
          If need>*p\panelW : *p\panelW=need : EndIf
        EndIf
      EndIf
    Next
    rc=ncmStatus(ncmPrepare(*s\font,">"))
    If rc=0 : rc=ncmStatus(ncmPrepare(*s\smallFont,"^v")) : EndIf
    If rc=0
      *s\arrowW=ncmWidth(*s\font,">") : *s\upW=ncmWidth(*s\smallFont,"^") : *s\downW=ncmWidth(*s\smallFont,"v")
      If ncmFinite(*s\arrowW)=0 Or ncmFinite(*s\upW)=0 Or ncmFinite(*s\downW)=0 Or *s\arrowW<0.0 Or *s\upW<0.0 Or *s\downW<0.0 : rc=#NCM_ERR_METRICS : EndIf
    EndIf
  EndIf
  ncmBusy=0
  If rc<>0 : ProcedureReturn ncmFail(*s,rc) : EndIf
  *s\openRoot=-1 : *s\openSub=-1
  If *s\savedRoot>0
    i=ncmFind(*s,*s\savedRoot)
    If i>=0
      *n=ncmNode(*s,i)
      If *n\kind=#NCM_ROOT : *s\openRoot=i : *n\scroll=*s\savedRootScroll : EndIf
    EndIf
  EndIf
  If *s\savedSub>0 And *s\openRoot>=0
    i=ncmFind(*s,*s\savedSub)
    If i>=0
      *n=ncmNode(*s,i)
      If *n\kind=#NCM_SUB And *n\parent=*s\openRoot : *s\openSub=i : *n\scroll=*s\savedSubScroll : EndIf
    EndIf
  EndIf
  *s\ready=1 : *s\needsRedraw=1 : ProcedureReturn ncmFail(*s,0)
EndProcedure
Procedure.i ncmHit(mx.f,my.f,x.f,y.f,w.f,h.f)
  ProcedureReturn Bool(mx>=x And mx<x+w And my>=y And my<y+h)
EndProcedure
Procedure ncmPanel(*s.NeonChromeMenuState,*n.NeonChromeMenuNode,*p.NeonChromeMenuPanel,x.f,y.f)
  Protected wanted.f=*n\rowsH,avail.f
  *p\w=*n\panelW : If *p\w>*s\canvasW-6.0 : *p\w=*s\canvasW-6.0 : EndIf
  If x+*p\w>*s\canvasW-4.0 : x=*s\canvasW-4.0-*p\w : EndIf
  If x<2.0 : x=2.0 : EndIf
  If y<*s\barY+*s\barH : y=*s\barY+*s\barH : EndIf
  *p\x=x : *p\y=y : avail=*s\canvasH-y-8.0
  If wanted<24.0* *s\scale : wanted=24.0* *s\scale : EndIf
  *p\scrolls=Bool(wanted>avail) : *p\viewY=y+4.0 : *p\viewH=wanted
  If *p\scrolls<>0 : *p\viewY=*p\viewY+16.0* *s\scale : *p\viewH=avail-8.0-32.0* *s\scale : EndIf
  If *p\viewH<1.0 : *p\viewH=1.0 : EndIf
  *p\h=*p\viewH+8.0 : If *p\scrolls<>0 : *p\h=*p\h+32.0* *s\scale : EndIf
  *p\maxScroll=wanted-*p\viewH : If *p\maxScroll<0.0 : *p\maxScroll=0.0 : EndIf
  If *n\scroll<0.0 : *n\scroll=0.0 : EndIf
  If *n\scroll>*p\maxScroll : *n\scroll=*p\maxScroll : EndIf
EndProcedure
Procedure ncmLayout(*s.NeonChromeMenuState)
  Protected *root.NeonChromeMenuNode,*sub.NeonChromeMenuNode,x.f,y.f,w.f,wanted.f,available.f
  If *s\openRoot<0 : ProcedureReturn : EndIf
  *root=ncmNode(*s,*s\openRoot) : ncmPanel(*s,*root,@*s\rootPanel,*root\tabX,*s\barY+*s\barH)
  If *s\openSub<0 : ProcedureReturn : EndIf
  *sub=ncmNode(*s,*s\openSub) : w=*sub\panelW : If w>*s\canvasW-6.0 : w=*s\canvasW-6.0 : EndIf
  x=*s\rootPanel\x+*s\rootPanel\w-2.0
  If x+w>*s\canvasW-4.0 : x=*s\rootPanel\x-w+2.0 : EndIf
  y=*s\rootPanel\viewY+*sub\rowOffset-*root\scroll-4.0
  wanted=*sub\rowsH : If wanted<24.0* *s\scale : wanted=24.0* *s\scale : EndIf
  wanted=wanted+8.0 : available=*s\canvasH-(*s\barY+*s\barH)-8.0
  If wanted>available : wanted=available : EndIf
  If y+wanted>*s\canvasH-8.0 : y=*s\canvasH-8.0-wanted : EndIf
  ncmPanel(*s,*sub,@*s\subPanel,x,y)
EndProcedure
Procedure.i ncmRowHit(*s.NeonChromeMenuState,parent.i,*p.NeonChromeMenuPanel)
  Protected i.i,rowY.f,*n.NeonChromeMenuNode,*owner.NeonChromeMenuNode=ncmNode(*s,parent)
  If *s\mouseY<*p\viewY Or *s\mouseY>=*p\viewY+*p\viewH : ProcedureReturn -1 : EndIf
  For i=0 To *s\count-1
    *n=ncmNode(*s,i)
    If *n\parent=parent And *n\kind<>#NCM_SEPARATOR
      rowY=*p\viewY+*n\rowOffset-*owner\scroll
      If ncmHit(*s\mouseX,*s\mouseY,*p\x,rowY,*p\w,24.0* *s\scale)<>0 : ProcedureReturn i : EndIf
    EndIf
  Next
  ProcedureReturn -1
EndProcedure
Procedure ncmScrollInput(*s.NeonChromeMenuState,index.i,*p.NeonChromeMenuPanel)
  Protected *n.NeonChromeMenuNode=ncmNode(*s,index),old.f=*n\scroll
  If *p\scrolls=0 Or ncmHit(*s\mouseX,*s\mouseY,*p\x,*p\y,*p\w,*p\h)=0 : ProcedureReturn : EndIf
  If *s\wheelRemaining<>0 : *n\scroll=*n\scroll-MathFFromInt(*s\wheelRemaining)*MathFFromInt(MathFToI32(48.0* *s\scale)) : *s\wheelRemaining=0 : EndIf
  If ncmHit(*s\mouseX,*s\mouseY,*p\x,*p\y+4.0,*p\w,16.0* *s\scale)<>0 : *n\scroll=*n\scroll-6.0 : EndIf
  If ncmHit(*s\mouseX,*s\mouseY,*p\x,*p\y+*p\h-4.0-16.0* *s\scale,*p\w,16.0* *s\scale)<>0 : *n\scroll=*n\scroll+6.0 : EndIf
  If *n\scroll<0.0 : *n\scroll=0.0 : EndIf
  If *n\scroll>*p\maxScroll : *n\scroll=*p\maxScroll : EndIf
  If *n\scroll<>old : *s\needsRedraw=1 : EndIf
EndProcedure
Procedure.i NeonChromeMenuInput(*s.NeonChromeMenuState,x.f,y.f,down.i,wheel.i,escape.i)
  Protected i.i,target.i=-1,row.i=-1,wasOpen.i,oldRoot.i,oldSub.i,oldHover.i,oldHoverRoot.i,onBar.i,onPanels.i,*n.NeonChromeMenuNode
  If ncmValid(*s)=0 : ProcedureReturn #NCM_ERR_STATE : EndIf
  If ncmBusy<>0 : ProcedureReturn ncmFail(*s,#NCM_ERR_BUSY) : EndIf
  If *s\ready=0 : ProcedureReturn ncmFail(*s,#NCM_ERR_STATE) : EndIf
  If ncmFinite(x)=0 Or ncmFinite(y)=0 Or (down<>0 And down<>1) Or (escape<>0 And escape<>1) Or wheel < -128 Or wheel>128 : ProcedureReturn ncmFail(*s,#NCM_ERR_ARGS) : EndIf
  oldHoverRoot=*s\hoverRoot : oldRoot=*s\openRoot : oldSub=*s\openSub : oldHover=*s\hoverId : wasOpen=Bool(oldRoot>=0)
  *s\mouseX=x : *s\mouseY=y : *s\pressed=Bool(down<>0 And *s\down=0) : *s\down=down
  *s\wheelRemaining=wheel : *s\needsRedraw=0 : *s\hoverId=0
  onBar=ncmHit(x,y,*s\barX,*s\barY,*s\barW,*s\barH) : *s\blocked=Bool(wasOpen<>0 Or onBar<>0)
  If escape<>0
    *s\openRoot=-1 : *s\openSub=-1
  Else
    If onBar<>0
      For i=0 To *s\count-1
        *n=ncmNode(*s,i)
        If *n\kind=#NCM_ROOT And ncmHit(x,y,*n\tabX,*s\barY,*n\tabW,*s\barH)<>0 : target=i : Break : EndIf
      Next
    EndIf
    *s\hoverRoot=target
    If target>=0
      If *s\openRoot>=0 And *s\openRoot<>target
        *s\openRoot=target : *s\openSub=-1 : *n=ncmNode(*s,target) : *n\scroll=0.0
      ElseIf *s\pressed<>0
        If *s\openRoot=target : *s\openRoot=-1 : *s\openSub=-1
        Else : *s\openRoot=target : *s\openSub=-1 : *n=ncmNode(*s,target) : *n\scroll=0.0 : EndIf
      EndIf
    EndIf
    ncmLayout(*s)
    If *s\openRoot>=0
      If *s\openSub>=0 And ncmHit(x,y,*s\subPanel\x,*s\subPanel\y,*s\subPanel\w,*s\subPanel\h)<>0
        ncmScrollInput(*s,*s\openSub,@*s\subPanel) : row=ncmRowHit(*s,*s\openSub,@*s\subPanel)
      Else
        ncmScrollInput(*s,*s\openRoot,@*s\rootPanel) : row=ncmRowHit(*s,*s\openRoot,@*s\rootPanel)
      EndIf
      If row>=0
        *n=ncmNode(*s,row)
        If *n\kind=#NCM_SUB
          If *s\openSub<>row : *n\scroll=0.0 : EndIf
          *s\openSub=row : *s\hoverId=*n\id
        ElseIf *n\enabled<>0
          *s\hoverId=*n\id
          If *s\pressed<>0 : *s\eventId=*n\id : *s\eventPending=1 : *s\openRoot=-1 : *s\openSub=-1 : EndIf
        EndIf
      EndIf
      ncmLayout(*s)
      If *s\openRoot>=0 And *s\pressed<>0 And onBar=0
        onPanels=ncmHit(x,y,*s\rootPanel\x,*s\rootPanel\y,*s\rootPanel\w,*s\rootPanel\h)
        If *s\openSub>=0 And ncmHit(x,y,*s\subPanel\x,*s\subPanel\y,*s\subPanel\w,*s\subPanel\h)<>0 : onPanels=1 : EndIf
        If onPanels=0 : *s\openRoot=-1 : *s\openSub=-1 : EndIf
      EndIf
    EndIf
  EndIf
  If oldHoverRoot<>*s\hoverRoot Or oldRoot<>*s\openRoot Or oldSub<>*s\openSub Or oldHover<>*s\hoverId : *s\needsRedraw=1 : EndIf
  ProcedureReturn ncmFail(*s,0)
EndProcedure
Procedure.i NeonChromeMenuEventGet(*s.NeonChromeMenuState)
  If ncmValid(*s)=0 : ProcedureReturn #NCM_ERR_STATE : EndIf
  If ncmBusy<>0 : ProcedureReturn ncmFail(*s,#NCM_ERR_BUSY) : EndIf
  If *s\eventPending=0 : ProcedureReturn 0 : EndIf
  *s\eventPending=0 : ProcedureReturn *s\eventId
EndProcedure
Procedure.i NeonChromeMenuGet(*s.NeonChromeMenuState,id.i)
  Protected i.i
  If ncmValid(*s)=0 : ProcedureReturn 0 : EndIf
  i=ncmFind(*s,id) : If i<0 : ProcedureReturn 0 : EndIf
  ProcedureReturn ncmNode(*s,i)
EndProcedure
Procedure.i NeonChromeMenuError(*s.NeonChromeMenuState)
  If ncmValid(*s)=0 : ProcedureReturn #NCM_ERR_STATE : EndIf
  ProcedureReturn *s\error
EndProcedure
Procedure.i NeonChromeMenuBlocksMouse(*s.NeonChromeMenuState)
  If ncmValid(*s)=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn *s\blocked
EndProcedure
Procedure.i NeonChromeMenuIsOpen(*s.NeonChromeMenuState)
  If ncmValid(*s)=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool(*s\openRoot>=0)
EndProcedure
Procedure.i NeonChromeMenuNeedsRedraw(*s.NeonChromeMenuState)
  If ncmValid(*s)=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool(*s\needsRedraw<>0 Or *s\styleRevision<>NeonChromeStyleRevision())
EndProcedure
Procedure ncmDrawBox(x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
  Protected rc.i
  If ncmRenderError<>0 : ProcedureReturn : EndIf
  rc=ncmStatus(ncmBox(x,y,w,h,r,g,b,a)) : If rc<>0 : ncmRenderError=rc : EndIf
EndProcedure
Procedure ncmDrawText(font.i,x.f,y.f,text.i,r.f,g.f,b.f)
  Protected rc.i
  If ncmRenderError<>0 : ProcedureReturn : EndIf
  rc=ncmStatus(ncmText(font,x,y,text,r,g,b,1.0)) : If rc<>0 : ncmRenderError=rc : EndIf
EndProcedure
Procedure ncmDrawClip(*p.NeonChromeMenuPanel)
  Protected rc.i
  If ncmRenderError<>0 : ProcedureReturn : EndIf
  rc=ncmStatus(ncmClip(*p\x,*p\viewY,*p\w,*p\viewH)) : If rc<>0 : ncmRenderError=rc : EndIf
EndProcedure
Procedure ncmDrawPanel(*s.NeonChromeMenuState,parent.i,*p.NeonChromeMenuPanel)
  Protected i.i,j.i,rowY.f,ty.f,need.f,markU.f,markY.f,tr.f,tg.f,tb.f
  Protected *n.NeonChromeMenuNode,*owner.NeonChromeMenuNode=ncmNode(*s,parent)
  For j=1 To 4 : ncmDrawBox(*p\x-MathFFromInt(j),*p\y-MathFFromInt(j),*p\w+MathFFromInt(j*2),*p\h+MathFFromInt(j*2),0.0,0.0,0.0,0.45/(MathFFromInt(j)*1.5)) : Next
  If ncmRenderError=0 : ncmRenderError=nhzBlock(*p\x,*p\y,*p\w,*p\h) : EndIf
  ncmDrawBox(*p\x,*p\y,*p\w,*p\h,nstyPalette\head\r,nstyPalette\head\g,nstyPalette\head\b,1.0)
  ncmDrawBox(*p\x,*p\y,*p\w,1.0,nstyPalette\accent\r*0.55,nstyPalette\accent\g*0.55,nstyPalette\accent\b*0.55,1.0)
  ncmDrawBox(*p\x,*p\y+*p\h-1.0,*p\w,1.0,nstyPalette\accent\r*0.55,nstyPalette\accent\g*0.55,nstyPalette\accent\b*0.55,1.0)
  ncmDrawBox(*p\x,*p\y,1.0,*p\h,nstyPalette\accent\r*0.55,nstyPalette\accent\g*0.55,nstyPalette\accent\b*0.55,1.0)
  ncmDrawBox(*p\x+*p\w-1.0,*p\y,1.0,*p\h,nstyPalette\accent\r*0.55,nstyPalette\accent\g*0.55,nstyPalette\accent\b*0.55,1.0)
  If *p\scrolls<>0
    ncmDrawBox(*p\x+1.0,*p\y+4.0,*p\w-2.0,16.0* *s\scale,nstyPalette\line\r,nstyPalette\line\g,nstyPalette\line\b,1.0)
    ncmDrawBox(*p\x+1.0,*p\y+*p\h-4.0-16.0* *s\scale,*p\w-2.0,16.0* *s\scale,nstyPalette\line\r,nstyPalette\line\g,nstyPalette\line\b,1.0)
    need=*s\upW
    If ncmFinite(need)=0 Or need<0.0 : ncmRenderError=#NCM_ERR_METRICS : Else : ncmDrawText(*s\smallFont,*p\x+(*p\w-need)/2.0,*p\y+4.0,"^",nstyPalette\accent\r,nstyPalette\accent\g,nstyPalette\accent\b) : EndIf
    need=*s\downW
    If ncmFinite(need)=0 Or need<0.0 : ncmRenderError=#NCM_ERR_METRICS : Else : ncmDrawText(*s\smallFont,*p\x+(*p\w-need)/2.0,*p\y+*p\h-4.0-16.0* *s\scale,"v",nstyPalette\accent\r,nstyPalette\accent\g,nstyPalette\accent\b) : EndIf
  EndIf
  ncmDrawClip(*p)
  For i=0 To *s\count-1
    *n=ncmNode(*s,i)
    If *n\parent=parent
      rowY=*p\viewY+*n\rowOffset-*owner\scroll
      If rowY+24.0* *s\scale>=*p\viewY And rowY<=*p\viewY+*p\viewH
        If *n\kind=#NCM_SEPARATOR
          ncmDrawBox(*p\x+10.0,rowY+4.5* *s\scale,*p\w-20.0,1.0,nstyPalette\line\r,nstyPalette\line\g,nstyPalette\line\b,1.0)
        Else
          If *n\enabled<>0 And ncmRenderError=0 : ncmRenderError=nhzEmitClip(3,*s,*n\id,*p\x,rowY,*p\w,24.0* *s\scale,*p\x,*p\viewY,*p\w,*p\viewH) : EndIf
          If *n\enabled<>0 And (*s\hoverId=*n\id Or (i=*s\openSub And *n\kind=#NCM_SUB)) : ncmDrawBox(*p\x+1.0,rowY,*p\w-2.0,24.0* *s\scale,nstyPalette\accent\r*0.28,nstyPalette\accent\g*0.28,nstyPalette\accent\b*0.32,1.0) : EndIf
          tr=nstyPalette\text\r : tg=nstyPalette\text\g : tb=nstyPalette\text\b
          If *n\enabled=0 : tr=nstyPalette\faint\r : tg=nstyPalette\faint\g : tb=nstyPalette\faint\b : EndIf
          ty=rowY+(24.0* *s\scale-*s\uiH)/2.0
          If *n\checked<>0
            markU=1.5* *s\scale : If markU<1.5 : markU=1.5 : EndIf
            markY=rowY+(24.0* *s\scale-markU*7.0)/2.0
            For j=0 To 6
              need=MathFFromInt(4-Abs(j-2)) : If j<2 : need=MathFFromInt(j+2) : EndIf
              ncmDrawBox(*p\x+4.0* *s\scale+MathFFromInt(j)*markU,markY+need*markU,markU,markU*3.0,nstyPalette\green\r,nstyPalette\green\g,nstyPalette\green\b,1.0)
            Next
          EndIf
          ncmDrawText(*s\font,*p\x+14.0* *s\scale+4.0,ty,*n\label,tr,tg,tb)
          If *n\shortcutW>0.0 : ncmDrawText(*s\smallFont,*p\x+*p\w-14.0* *s\scale-*n\shortcutW,ty+1.0,*n\shortcut,nstyPalette\faint\r,nstyPalette\faint\g,nstyPalette\faint\b) : EndIf
          If *n\kind=#NCM_SUB
            need=*s\arrowW
            If ncmFinite(need)=0 Or need<0.0 : ncmRenderError=#NCM_ERR_METRICS : Else : ncmDrawText(*s\font,*p\x+*p\w-8.0-need,ty,">",nstyPalette\dim\r,nstyPalette\dim\g,nstyPalette\dim\b) : EndIf
          EndIf
        EndIf
      EndIf
    EndIf
  Next
EndProcedure
Procedure.i NeonChromeMenuDraw(*s.NeonChromeMenuState)
  Protected i.i,rc.i,*n.NeonChromeMenuNode,tr.f,tg.f,tb.f
  If ncmValid(*s)=0 : ProcedureReturn #NCM_ERR_STATE : EndIf
  If ncmBusy<>0 : ProcedureReturn ncmFail(*s,#NCM_ERR_BUSY) : EndIf
  If *s\ready=0 : ProcedureReturn ncmFail(*s,#NCM_ERR_STATE) : EndIf
  If ncmActive=0 : ProcedureReturn ncmFail(*s,#NCM_ERR_RENDERER) : EndIf
  nstyEnter() : ncmBusy=1 : ncmRenderError=0 : *s\cleanupError=0
  rc=ncmStatus(ncmClear()) : If rc<>0 : ncmRenderError=rc : EndIf
  ncmDrawBox(*s\barX,*s\barY,*s\barW,*s\barH,nstyPalette\head\r,nstyPalette\head\g,nstyPalette\head\b,1.0)
  ncmDrawBox(*s\barX,*s\barY+*s\barH-1.0,*s\barW,1.0,nstyPalette\line\r,nstyPalette\line\g,nstyPalette\line\b,1.0)
  rc=ncmStatus(ncmClip(*s\barX,*s\barY,*s\barW,*s\barH))
  If rc<>0 And ncmRenderError=0 : ncmRenderError=rc : EndIf
  For i=0 To *s\count-1
    *n=ncmNode(*s,i)
    If *n\kind=#NCM_ROOT
      If ncmRenderError=0 : ncmRenderError=nhzEmitClip(2,*s,*n\id,*n\tabX,*s\barY,*n\tabW,*s\barH,*s\barX,*s\barY,*s\barW,*s\barH) : EndIf
      tr=nstyPalette\text\r : tg=nstyPalette\text\g : tb=nstyPalette\text\b
      If i=*s\openRoot
        ncmDrawBox(*n\tabX,*s\barY,*n\tabW,*s\barH,nstyPalette\accent\r*0.30,nstyPalette\accent\g*0.30,nstyPalette\accent\b*0.34,1.0)
        ncmDrawBox(*n\tabX,*s\barY+*s\barH-2.0,*n\tabW,2.0,nstyPalette\accent\r,nstyPalette\accent\g,nstyPalette\accent\b,1.0)
        tr=nstyPalette\accent\r : tg=nstyPalette\accent\g : tb=nstyPalette\accent\b
      ElseIf ncmHit(*s\mouseX,*s\mouseY,*n\tabX,*s\barY,*n\tabW,*s\barH)<>0
        ncmDrawBox(*n\tabX,*s\barY,*n\tabW,*s\barH,nstyPalette\line\r,nstyPalette\line\g,nstyPalette\line\b,1.0)
      EndIf
      ncmDrawText(*s\font,*n\tabX+(*n\tabW-*n\labelW)/2.0,*s\barY+(*s\barH-*s\uiH)/2.0,*n\label,tr,tg,tb)
    EndIf
  Next
  rc=ncmStatus(ncmClear()) : If rc<>0 And ncmRenderError=0 : ncmRenderError=rc : EndIf
  ncmLayout(*s)
  If *s\openRoot>=0 : ncmDrawPanel(*s,*s\openRoot,@*s\rootPanel) : EndIf
  rc=ncmStatus(ncmClear()) : If rc<>0 And ncmRenderError=0 : ncmRenderError=rc : EndIf
  If *s\openSub>=0 : ncmDrawPanel(*s,*s\openSub,@*s\subPanel) : EndIf
  *s\cleanupError=ncmStatus(ncmClear())
  If ncmRenderError=0 : ncmRenderError=*s\cleanupError : EndIf
  If ncmRenderError=0 : *s\styleRevision=NeonChromeStyleRevision() : EndIf
  ncmBusy=0 : nstyLeave() : ProcedureReturn ncmFail(*s,ncmRenderError)
EndProcedure

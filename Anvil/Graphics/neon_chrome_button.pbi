; SPDX-License-Identifier: MIT
; Prepared chrome button and decorative box helpers. Reference: GlUIChrome.
XIncludeFile "Anvil/Graphics/neon_chrome_hotzones.pbi"
XIncludeFile "Anvil/Graphics/neon_utf8.pbi"
#NCB_MAGIC=$4E434231
#NCB_ERR_ARGS=-22800
#NCB_ERR_STATE=-22801
#NCB_ERR_BUSY=-22802
#NCB_ERR_CAPACITY=-22803
#NCB_ERR_RENDERER=-22804
#NCB_ERR_METRICS=-22805
#NCB_ERR_TEXT=-22806
Structure NeonChromeButtonConfig Align #PB_Structure_AlignC
  id.i : font.i : label.i : lit.i : enabled.i
  x.f : y.f : w.f : h.f
EndStructure
Structure NeonChromeButtonState Align #PB_Structure_AlignC
  magic.i : id.i : font.i : label.i : bytes.i : length.i : lit.i : enabled.i
  ready.i : event.i : error.i : redraw.i : styleRevision.i : animating.i
  x.f : y.f : w.f : h.f : lineH.f : textW.f : hover.f
EndStructure
Procedure.i ncbBoxUnbound(x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
  ProcedureReturn #NCB_ERR_RENDERER
EndProcedure
Procedure.i ncbTextUnbound(font.i,x.f,y.f,text.i,r.f,g.f,b.f,a.f)
  ProcedureReturn #NCB_ERR_RENDERER
EndProcedure
Procedure.f ncbWidthUnbound(font.i,text.i)
  ProcedureReturn -1.0
EndProcedure
Procedure.f ncbHeightUnbound(font.i)
  ProcedureReturn -1.0
EndProcedure
Procedure.i ncbPrepareUnbound(font.i,text.i)
  ProcedureReturn #NCB_ERR_RENDERER
EndProcedure
Global ncbBox.i=@ncbBoxUnbound,ncbText.i=@ncbTextUnbound,ncbWidth.i=@ncbWidthUnbound,ncbHeight.i=@ncbHeightUnbound,ncbPrepare.i=@ncbPrepareUnbound
Global ncbActive.i,ncbBusy.i,ncbRenderError.i
Procedure.i ncbStatus(rc.i)
  If rc>0 : ProcedureReturn #NCB_ERR_RENDERER : EndIf
  ProcedureReturn rc
EndProcedure
Procedure.i ncbFinite(v.f)
  ProcedureReturn Bool((MathBitsOf(v) & $7FFFFFFF)<=$49742400)
EndProcedure
Procedure.i ncbGeometry(x.f,y.f,w.f,h.f,margin.f)
  ProcedureReturn Bool(ncbFinite(x)<>0 And ncbFinite(y)<>0 And ncbFinite(w)<>0 And ncbFinite(h)<>0 And w>0.0 And h>0.0 And w<=8192.0 And h<=8192.0 And ncbFinite(x-margin)<>0 And ncbFinite(y-margin)<>0 And ncbFinite(x+w+margin)<>0 And ncbFinite(y+h+margin)<>0)
EndProcedure
Procedure.i ncbColour(v.f)
  ProcedureReturn Bool(ncbFinite(v)<>0 And v>=0.0 And v<=1.0)
EndProcedure
Procedure.f ncbClamp(v.f)
  If v<0.0 : ProcedureReturn 0.0 : EndIf
  If v>1.0 : ProcedureReturn 1.0 : EndIf
  ProcedureReturn v
EndProcedure
Procedure.i ncbValid(*s.NeonChromeButtonState)
  If *s=0 Or (*s & 7)<>0 Or *s+SizeOf(NeonChromeButtonState)<=*s : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool(*s\magic=#NCB_MAGIC)
EndProcedure
Procedure.i ncbFail(*s.NeonChromeButtonState,rc.i)
  *s\error=rc : ProcedureReturn rc
EndProcedure
Procedure.i NeonChromeButtonRendererInstall(box.i,text.i,width.i,height.i,prepare.i)
  If ncbBusy<>0 Or nstyBusy<>0 : ProcedureReturn #NCB_ERR_BUSY : EndIf
  If box=0 Or text=0 Or width=0 Or height=0 Or prepare=0 : ProcedureReturn #NCB_ERR_ARGS : EndIf
  ncbBox=box : ncbText=text : ncbWidth=width : ncbHeight=height : ncbPrepare=prepare : ncbActive=1
  ProcedureReturn 0
EndProcedure
Procedure.i NeonChromeButtonConfigure(*s.NeonChromeButtonState,arena.i,bytes.i,*c.NeonChromeButtonConfig)
  Protected length.i,i.i
  If ncbBusy<>0 Or nstyBusy<>0 : ProcedureReturn #NCB_ERR_BUSY : EndIf
  If *s=0 Or (*s & 7)<>0 Or *c=0 Or (*c & 7)<>0 Or arena=0 Or bytes<4 Or bytes>512 Or arena+bytes<=arena Or *s+SizeOf(NeonChromeButtonState)<=*s Or *c+SizeOf(NeonChromeButtonConfig)<=*c : ProcedureReturn #NCB_ERR_ARGS : EndIf
  If nhzOverlap(*s,SizeOf(NeonChromeButtonState),arena,bytes)<>0 Or nhzOverlap(*c,SizeOf(NeonChromeButtonConfig),*s,SizeOf(NeonChromeButtonState))<>0 Or nhzOverlap(*c,SizeOf(NeonChromeButtonConfig),arena,bytes)<>0 : ProcedureReturn #NCB_ERR_ARGS : EndIf
  If *c\id<1 Or *c\font<0 Or (*c\lit<>0 And *c\lit<>1) Or (*c\enabled<>0 And *c\enabled<>1) Or ncbGeometry(*c\x,*c\y,*c\w,*c\h,4.0)=0 : ProcedureReturn #NCB_ERR_ARGS : EndIf
  length=NeonUtf8Length(*c\label,bytes)
  If length<0 : ProcedureReturn #NCB_ERR_TEXT : EndIf
  If nhzOverlap(*c\label,length+1,*s,SizeOf(NeonChromeButtonState))<>0 Or nhzOverlap(*c\label,length+1,arena,bytes)<>0 : ProcedureReturn #NCB_ERR_ARGS : EndIf
  For i=0 To SizeOf(NeonChromeButtonState)-1 : PokeA(*s+i,0) : Next
  *s\magic=#NCB_MAGIC : *s\id=*c\id : *s\font=*c\font : *s\lit=*c\lit : *s\enabled=*c\enabled
  *s\label=arena : *s\bytes=bytes : *s\length=length : *s\x=*c\x : *s\y=*c\y : *s\w=*c\w : *s\h=*c\h : *s\redraw=1
  For i=0 To length : PokeA(arena+i,PeekA(*c\label+i)) : Next
  ProcedureReturn 0
EndProcedure
Procedure.i NeonChromeButtonLabelSet(*s.NeonChromeButtonState,text.i)
  Protected n.i,i.i
  If ncbValid(*s)=0 : ProcedureReturn #NCB_ERR_STATE : EndIf
  If ncbBusy<>0 Or nstyBusy<>0 : ProcedureReturn ncbFail(*s,#NCB_ERR_BUSY) : EndIf
  n=NeonUtf8Length(text,*s\bytes) : If n<0 : ProcedureReturn ncbFail(*s,#NCB_ERR_TEXT) : EndIf
  If text=*s\label : ProcedureReturn ncbFail(*s,0) : EndIf
  If nhzOverlap(text,n+1,*s,SizeOf(NeonChromeButtonState))<>0 Or nhzOverlap(text,n+1,*s\label,*s\bytes)<>0 : ProcedureReturn ncbFail(*s,#NCB_ERR_ARGS) : EndIf
  For i=0 To n : PokeA(*s\label+i,PeekA(text+i)) : Next
  *s\length=n : *s\ready=0 : *s\redraw=1 : *s\event=0 : ProcedureReturn ncbFail(*s,0)
EndProcedure
Procedure.i NeonChromeButtonFlagsSet(*s.NeonChromeButtonState,lit.i,enabled.i)
  If ncbValid(*s)=0 : ProcedureReturn #NCB_ERR_STATE : EndIf
  If ncbBusy<>0 Or nstyBusy<>0 : ProcedureReturn ncbFail(*s,#NCB_ERR_BUSY) : EndIf
  If (lit<>0 And lit<>1) Or (enabled<>0 And enabled<>1) : ProcedureReturn ncbFail(*s,#NCB_ERR_ARGS) : EndIf
  If *s\lit<>lit Or *s\enabled<>enabled : *s\redraw=1 : EndIf
  *s\lit=lit : *s\enabled=enabled : If enabled=0 : *s\event=0 : EndIf
  ProcedureReturn ncbFail(*s,0)
EndProcedure
Procedure.i NeonChromeButtonSeal(*s.NeonChromeButtonState)
  Protected rc.i,w.f,h.f
  If ncbValid(*s)=0 : ProcedureReturn #NCB_ERR_STATE : EndIf
  If ncbBusy<>0 Or nstyBusy<>0 : ProcedureReturn ncbFail(*s,#NCB_ERR_BUSY) : EndIf
  If ncbActive=0 : ProcedureReturn ncbFail(*s,#NCB_ERR_RENDERER) : EndIf
  *s\ready=0 : ncbBusy=1
  rc=ncbStatus(ncbPrepare(*s\font,*s\label))
  If rc=0
    w=ncbWidth(*s\font,*s\label) : h=ncbHeight(*s\font)
    If ncbFinite(w)=0 Or w<0.0 Or ncbFinite(h)=0 Or h<=0.0 Or h>8192.0 Or ncbFinite(*s\x+(*s\w-w)/2.0)=0 Or ncbFinite(*s\y+(*s\h-h)/2.0)=0 : rc=#NCB_ERR_METRICS : EndIf
  EndIf
  ncbBusy=0
  If rc=0 : *s\textW=w : *s\lineH=h : *s\ready=1 : EndIf
  ProcedureReturn ncbFail(*s,rc)
EndProcedure
; pressed is the host's shared edge, not a held level. It avoids per-widget phantom presses.
Procedure.i NeonChromeButtonInput(*s.NeonChromeButtonState,x.f,y.f,pressed.i,blocked.i,dt.f)
  Protected over.i,old.f
  If ncbValid(*s)=0 : ProcedureReturn #NCB_ERR_STATE : EndIf
  If ncbBusy<>0 Or nstyBusy<>0 : ProcedureReturn ncbFail(*s,#NCB_ERR_BUSY) : EndIf
  If *s\ready=0 : ProcedureReturn ncbFail(*s,#NCB_ERR_STATE) : EndIf
  If ncbFinite(x)=0 Or ncbFinite(y)=0 Or ncbFinite(dt)=0 Or dt<0.0 Or (pressed<>0 And pressed<>1) Or (blocked<>0 And blocked<>1) : ProcedureReturn ncbFail(*s,#NCB_ERR_ARGS) : EndIf
  If dt>0.05 : dt=0.05 : EndIf
  over=Bool(*s\enabled<>0 And blocked=0 And x>=*s\x And x<*s\x+*s\w And y>=*s\y And y<*s\y+*s\h)
  *s\event=Bool(over<>0 And pressed<>0) : old=*s\hover
  If NeonChromeStyleAnimationsGet()=0 : *s\hover=MathFFromInt(over)
  Else
    *s\hover=*s\hover+(MathFFromInt(over)-*s\hover)*(1.0-Exp(-18.0*dt))
    If Abs(MathFFromInt(over)-*s\hover)<0.002 : *s\hover=MathFFromInt(over) : EndIf
  EndIf
  *s\animating=Bool(*s\hover<>MathFFromInt(over))
  If old<>*s\hover : *s\redraw=1 : EndIf
  ProcedureReturn ncbFail(*s,0)
EndProcedure
Procedure.i NeonChromeButtonEventGet(*s.NeonChromeButtonState)
  Protected value.i
  If ncbValid(*s)=0 : ProcedureReturn #NCB_ERR_STATE : EndIf
  If ncbBusy<>0 Or nstyBusy<>0 : ProcedureReturn #NCB_ERR_BUSY : EndIf
  value=*s\event : *s\event=0 : ProcedureReturn value
EndProcedure
Procedure ncbIssueBox(x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
  If ncbRenderError=0 : ncbRenderError=ncbStatus(ncbBox(x,y,w,h,r,g,b,a)) : EndIf
EndProcedure
Procedure ncbGlow(x.f,y.f,w.f,h.f,r.f,g.f,b.f,strength.f)
  Protected i.i,f.f
  For i=1 To 4
    f=MathFFromInt(i) : ncbIssueBox(x-f,y-f,w+2.0*f,h+2.0*f,r,g,b,strength/(f*1.5))
  Next
EndProcedure
Procedure ncbFrame(x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
  ncbIssueBox(x,y,w,1.0,r,g,b,a) : ncbIssueBox(x,y+h-1.0,w,1.0,r,g,b,a)
  ncbIssueBox(x,y,1.0,h,r,g,b,a) : ncbIssueBox(x+w-1.0,y,1.0,h,r,g,b,a)
EndProcedure
Procedure.i NeonChromeGlow(x.f,y.f,w.f,h.f,r.f,g.f,b.f,strength.f)
  If ncbBusy<>0 Or nstyBusy<>0 : ProcedureReturn #NCB_ERR_BUSY : EndIf
  If ncbActive=0 : ProcedureReturn #NCB_ERR_RENDERER : EndIf
  If ncbGeometry(x,y,w,h,4.0)=0 Or ncbColour(r)=0 Or ncbColour(g)=0 Or ncbColour(b)=0 Or ncbColour(strength)=0 : ProcedureReturn #NCB_ERR_ARGS : EndIf
  nstyEnter() : ncbBusy=1 : ncbRenderError=0 : ncbGlow(x,y,w,h,r,g,b,strength)
  ncbBusy=0 : nstyLeave() : ProcedureReturn ncbRenderError
EndProcedure
Procedure.i NeonChromeFrame(x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
  If ncbBusy<>0 Or nstyBusy<>0 : ProcedureReturn #NCB_ERR_BUSY : EndIf
  If ncbActive=0 : ProcedureReturn #NCB_ERR_RENDERER : EndIf
  If ncbGeometry(x,y,w,h,0.0)=0 Or ncbColour(r)=0 Or ncbColour(g)=0 Or ncbColour(b)=0 Or ncbColour(a)=0 : ProcedureReturn #NCB_ERR_ARGS : EndIf
  nstyEnter() : ncbBusy=1 : ncbRenderError=0 : ncbFrame(x,y,w,h,r,g,b,a)
  ncbBusy=0 : nstyLeave() : ProcedureReturn ncbRenderError
EndProcedure
Procedure.i NeonChromeButtonDraw(*s.NeonChromeButtonState)
  Protected br.f,bg.f,bb.f,tr.f,tg.f,tb.f
  If ncbValid(*s)=0 : ProcedureReturn #NCB_ERR_STATE : EndIf
  If ncbBusy<>0 Or nstyBusy<>0 : ProcedureReturn ncbFail(*s,#NCB_ERR_BUSY) : EndIf
  If *s\ready=0 : ProcedureReturn ncbFail(*s,#NCB_ERR_STATE) : EndIf
  If ncbActive=0 : ProcedureReturn ncbFail(*s,#NCB_ERR_RENDERER) : EndIf
  nstyEnter() : ncbBusy=1 : ncbRenderError=0
  If *s\enabled<>0 : ncbRenderError=nhzEmit(1,*s,*s\id,*s\x,*s\y,*s\w,*s\h) : EndIf
  br=nstyPalette\line\r : bg=nstyPalette\line\g : bb=nstyPalette\line\b
  tr=nstyPalette\text\r : tg=nstyPalette\text\g : tb=nstyPalette\text\b
  If *s\lit<>0 : br=0.157 : bg=0.365 : bb=0.408 : tr=0.588 : tg=0.816 : tb=0.867 : EndIf
  If *s\enabled=0 : tr=nstyPalette\faint\r : tg=nstyPalette\faint\g : tb=nstyPalette\faint\b : EndIf
  If *s\hover>0.0
    br=ncbClamp(br+0.06* *s\hover) : bg=ncbClamp(bg+0.07* *s\hover) : bb=ncbClamp(bb+0.08* *s\hover)
    ncbGlow(*s\x,*s\y,*s\w,*s\h,nstyPalette\accent\r,nstyPalette\accent\g,nstyPalette\accent\b,0.16* *s\hover)
  EndIf
  ncbIssueBox(*s\x,*s\y,*s\w,*s\h,br,bg,bb,1.0)
  ncbIssueBox(*s\x,*s\y,*s\w,1.0,0.216,0.259,0.325,1.0)
  ncbIssueBox(*s\x,*s\y+*s\h-1.0,*s\w,1.0,nstyPalette\bg\r,nstyPalette\bg\g,nstyPalette\bg\b,1.0)
  If ncbRenderError=0 : ncbRenderError=ncbStatus(ncbText(*s\font,*s\x+(*s\w-*s\textW)/2.0,*s\y+(*s\h-*s\lineH)/2.0,*s\label,tr,tg,tb,1.0)) : EndIf
  If ncbRenderError=0 : *s\redraw=0 : *s\styleRevision=NeonChromeStyleRevision() : EndIf
  ncbBusy=0 : nstyLeave() : ProcedureReturn ncbFail(*s,ncbRenderError)
EndProcedure
Procedure.i NeonChromeButtonNeedsRedraw(*s.NeonChromeButtonState)
  If ncbValid(*s)=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool(*s\redraw<>0 Or *s\animating<>0 Or *s\styleRevision<>NeonChromeStyleRevision())
EndProcedure
Procedure.i NeonChromeButtonLabel(*s.NeonChromeButtonState)
  If ncbValid(*s)=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn *s\label
EndProcedure

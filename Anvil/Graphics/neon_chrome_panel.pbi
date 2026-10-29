; SPDX-License-Identifier: MIT
; Prepared counterpart of the engine's titled panel composition.
XIncludeFile "Anvil/Graphics/neon_chrome_style.pbi"
XIncludeFile "Anvil/Graphics/neon_text_upper.pbi"
#NCP_MAGIC=$4E435031
#NCP_ERR_ARGS=-23300
#NCP_ERR_STATE=-23301
#NCP_ERR_BUSY=-23302
#NCP_ERR_CAPACITY=-23303
#NCP_ERR_RENDERER=-23304
#NCP_ERR_TEXT=-23305
#NEON_PANEL_HEADER_HEIGHT=26.0
#NEON_PANEL_MAX_TITLE_BYTES=196608
Structure NeonChromePanelConfig Align #PB_Structure_AlignC
  font.i : title.i : titleBudget.i
  x.f : y.f : w.f : h.f : headerH.f : ar.f : ag.f : ab.f
EndStructure
Structure NeonChromePanelState Align #PB_Structure_AlignC
  magic.i : font.i : title.i : bytes.i : length.i
  ready.i : error.i : redraw.i : styleRevision.i
  x.f : y.f : w.f : h.f : headerH.f : ar.f : ag.f : ab.f
EndStructure
Procedure.i ncpBoxUnbound(x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
  ProcedureReturn #NCP_ERR_RENDERER
EndProcedure
Procedure.i ncpTextUnbound(font.i,x.f,y.f,text.i,r.f,g.f,b.f,a.f)
  ProcedureReturn #NCP_ERR_RENDERER
EndProcedure
Procedure.i ncpPrepareUnbound(font.i,text.i)
  ProcedureReturn #NCP_ERR_RENDERER
EndProcedure
Global ncpBox.i=@ncpBoxUnbound,ncpText.i=@ncpTextUnbound,ncpPrepare.i=@ncpPrepareUnbound
Global ncpActive.i,ncpBusy.i,ncpRenderError.i
Procedure.i ncpStatus(rc.i)
  If rc>0 : ProcedureReturn #NCP_ERR_RENDERER : EndIf
  ProcedureReturn rc
EndProcedure
Procedure.i ncpUpperStatus(rc.i)
  If rc=#NEON_UPPER_ERR_TEXT : ProcedureReturn #NCP_ERR_TEXT : EndIf
  If rc=#NEON_UPPER_ERR_CAPACITY : ProcedureReturn #NCP_ERR_CAPACITY : EndIf
  If rc<0 : ProcedureReturn #NCP_ERR_ARGS : EndIf
  ProcedureReturn rc
EndProcedure
Procedure.i ncpFinite(v.f)
  ProcedureReturn Bool((MathBitsOf(v) & $7FFFFFFF)<=$49742400)
EndProcedure
Procedure.i ncpColour(v.f)
  ProcedureReturn Bool(ncpFinite(v)<>0 And v>=0.0 And v<=1.0)
EndProcedure
Procedure.i ncpGeometry(x.f,y.f,w.f,h.f,headerH.f)
  ProcedureReturn Bool(ncpFinite(x)<>0 And ncpFinite(y)<>0 And ncpFinite(w)<>0 And ncpFinite(h)<>0 And ncpFinite(headerH)<>0 And w>0.0 And h>0.0 And w<=8192.0 And h<=8192.0 And headerH>=0.0 And headerH<=8192.0 And ncpFinite(x+w)<>0 And ncpFinite(y+h)<>0 And ncpFinite(y+headerH)<>0 And ncpFinite(x+12.0)<>0 And ncpFinite(y+5.0)<>0)
EndProcedure
Procedure.i ncpValid(*s.NeonChromePanelState)
  If *s=0 Or (*s & 7)<>0 Or NeonByteSpan(*s,SizeOf(NeonChromePanelState))=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool(*s\magic=#NCP_MAGIC)
EndProcedure
Procedure.i ncpFail(*s.NeonChromePanelState,rc.i)
  *s\error=rc : ProcedureReturn rc
EndProcedure
Procedure.i NeonChromePanelTitleBytes(source.i,budget.i)
  Protected n.i=ncpUpperStatus(NeonTextUpperBytes(source,budget))
  If n<0 : ProcedureReturn n : EndIf
  ProcedureReturn n+1
EndProcedure
Procedure.i NeonChromePanelRendererInstall(box.i,text.i,prepare.i)
  If ncpBusy<>0 Or nstyBusy<>0 : ProcedureReturn #NCP_ERR_BUSY : EndIf
  If box=0 Or text=0 Or prepare=0 : ProcedureReturn #NCP_ERR_ARGS : EndIf
  ncpBox=box : ncpText=text : ncpPrepare=prepare : ncpActive=1
  ProcedureReturn 0
EndProcedure
Procedure.i NeonChromePanelConfigure(*s.NeonChromePanelState,arena.i,bytes.i,*c.NeonChromePanelConfig)
  Protected need.i,n.i,i.i
  If ncpBusy<>0 Or nstyBusy<>0 : ProcedureReturn #NCP_ERR_BUSY : EndIf
  If *s=0 Or (*s & 7)<>0 Or *c=0 Or (*c & 7)<>0 Or bytes<1 Or bytes>#NEON_PANEL_MAX_TITLE_BYTES Or NeonByteSpan(*s,SizeOf(NeonChromePanelState))=0 Or NeonByteSpan(*c,SizeOf(NeonChromePanelConfig))=0 Or NeonByteSpan(arena,bytes)=0
    ProcedureReturn #NCP_ERR_ARGS
  EndIf
  If NeonByteOverlap(*s,SizeOf(NeonChromePanelState),arena,bytes)<>0 Or NeonByteOverlap(*c,SizeOf(NeonChromePanelConfig),*s,SizeOf(NeonChromePanelState))<>0 Or NeonByteOverlap(*c,SizeOf(NeonChromePanelConfig),arena,bytes)<>0
    ProcedureReturn #NCP_ERR_ARGS
  EndIf
  If *c\font<0 Or ncpGeometry(*c\x,*c\y,*c\w,*c\h,*c\headerH)=0 Or ncpColour(*c\ar)=0 Or ncpColour(*c\ag)=0 Or ncpColour(*c\ab)=0 : ProcedureReturn #NCP_ERR_ARGS : EndIf
  need=NeonChromePanelTitleBytes(*c\title,*c\titleBudget)
  If need<0 : ProcedureReturn need : EndIf
  If need>bytes : ProcedureReturn #NCP_ERR_CAPACITY : EndIf
  If NeonByteOverlap(*c\title,*c\titleBudget,*s,SizeOf(NeonChromePanelState))<>0 Or NeonByteOverlap(*c\title,*c\titleBudget,arena,bytes)<>0 : ProcedureReturn #NCP_ERR_ARGS : EndIf
  n=ncpUpperStatus(NeonTextUpper(arena,bytes,*c\title,*c\titleBudget))
  If n<0 : ProcedureReturn n : EndIf
  For i=0 To SizeOf(NeonChromePanelState)-1 : PokeA(*s+i,0) : Next
  *s\magic=#NCP_MAGIC : *s\font=*c\font : *s\title=arena : *s\bytes=bytes : *s\length=n
  *s\x=*c\x : *s\y=*c\y : *s\w=*c\w : *s\h=*c\h : *s\headerH=*c\headerH
  *s\ar=*c\ar : *s\ag=*c\ag : *s\ab=*c\ab : *s\redraw=1
  ProcedureReturn 0
EndProcedure
Procedure.i NeonChromePanelTitleSet(*s.NeonChromePanelState,source.i,budget.i)
  Protected need.i,n.i
  If ncpValid(*s)=0 : ProcedureReturn #NCP_ERR_STATE : EndIf
  If ncpBusy<>0 Or nstyBusy<>0 : ProcedureReturn ncpFail(*s,#NCP_ERR_BUSY) : EndIf
  need=NeonChromePanelTitleBytes(source,budget)
  If need<0 : ProcedureReturn ncpFail(*s,need) : EndIf
  If need>*s\bytes : ProcedureReturn ncpFail(*s,#NCP_ERR_CAPACITY) : EndIf
  If NeonByteOverlap(source,budget,*s,SizeOf(NeonChromePanelState))<>0 Or NeonByteOverlap(source,budget,*s\title,*s\bytes)<>0 : ProcedureReturn ncpFail(*s,#NCP_ERR_ARGS) : EndIf
  n=ncpUpperStatus(NeonTextUpper(*s\title,*s\bytes,source,budget))
  If n<0 : ProcedureReturn ncpFail(*s,n) : EndIf
  *s\length=n : *s\ready=0 : *s\redraw=1
  ProcedureReturn ncpFail(*s,0)
EndProcedure
Procedure.i NeonChromePanelGeometrySet(*s.NeonChromePanelState,x.f,y.f,w.f,h.f,headerH.f)
  If ncpValid(*s)=0 : ProcedureReturn #NCP_ERR_STATE : EndIf
  If ncpBusy<>0 Or nstyBusy<>0 : ProcedureReturn ncpFail(*s,#NCP_ERR_BUSY) : EndIf
  If ncpGeometry(x,y,w,h,headerH)=0 : ProcedureReturn ncpFail(*s,#NCP_ERR_ARGS) : EndIf
  If *s\x<>x Or *s\y<>y Or *s\w<>w Or *s\h<>h Or *s\headerH<>headerH : *s\redraw=1 : EndIf
  *s\x=x : *s\y=y : *s\w=w : *s\h=h : *s\headerH=headerH
  ProcedureReturn ncpFail(*s,0)
EndProcedure
Procedure.i NeonChromePanelAccentSet(*s.NeonChromePanelState,r.f,g.f,b.f)
  If ncpValid(*s)=0 : ProcedureReturn #NCP_ERR_STATE : EndIf
  If ncpBusy<>0 Or nstyBusy<>0 : ProcedureReturn ncpFail(*s,#NCP_ERR_BUSY) : EndIf
  If ncpColour(r)=0 Or ncpColour(g)=0 Or ncpColour(b)=0 : ProcedureReturn ncpFail(*s,#NCP_ERR_ARGS) : EndIf
  If *s\ar<>r Or *s\ag<>g Or *s\ab<>b : *s\redraw=1 : EndIf
  *s\ar=r : *s\ag=g : *s\ab=b
  ProcedureReturn ncpFail(*s,0)
EndProcedure
Procedure.i NeonChromePanelSeal(*s.NeonChromePanelState)
  Protected rc.i
  If ncpValid(*s)=0 : ProcedureReturn #NCP_ERR_STATE : EndIf
  If ncpBusy<>0 Or nstyBusy<>0 : ProcedureReturn ncpFail(*s,#NCP_ERR_BUSY) : EndIf
  If ncpActive=0 : ProcedureReturn ncpFail(*s,#NCP_ERR_RENDERER) : EndIf
  *s\ready=0 : ncpBusy=1
  If *s\length>0 : rc=ncpStatus(ncpPrepare(*s\font,*s\title)) : EndIf
  ncpBusy=0
  If rc=0 : *s\ready=1 : EndIf
  ProcedureReturn ncpFail(*s,rc)
EndProcedure
Procedure ncpIssueBox(x.f,y.f,w.f,h.f,r.f,g.f,b.f)
  If ncpRenderError=0 And w>0.0 And h>0.0 : ncpRenderError=ncpStatus(ncpBox(x,y,w,h,r,g,b,1.0)) : EndIf
EndProcedure
Procedure.i NeonChromePanelDraw(*s.NeonChromePanelState)
  Protected palette.NeonChromePalette,rc.i
  If ncpValid(*s)=0 : ProcedureReturn #NCP_ERR_STATE : EndIf
  If ncpBusy<>0 Or nstyBusy<>0 : ProcedureReturn ncpFail(*s,#NCP_ERR_BUSY) : EndIf
  If *s\ready=0 : ProcedureReturn ncpFail(*s,#NCP_ERR_STATE) : EndIf
  If ncpActive=0 : ProcedureReturn ncpFail(*s,#NCP_ERR_RENDERER) : EndIf
  rc=NeonChromeStylePaletteGet(@palette)
  If rc<>0 : ProcedureReturn ncpFail(*s,rc) : EndIf
  nstyEnter() : ncpBusy=1 : ncpRenderError=0
  ncpIssueBox(*s\x,*s\y,*s\w,*s\h,palette\panel\r,palette\panel\g,palette\panel\b)
  If *s\length>0
    ncpIssueBox(*s\x,*s\y,*s\w,*s\headerH,palette\head\r,palette\head\g,palette\head\b)
    ncpIssueBox(*s\x,*s\y,3.0,*s\headerH,*s\ar,*s\ag,*s\ab)
    ncpIssueBox(*s\x,*s\y+*s\headerH,*s\w,1.0,palette\line\r,palette\line\g,palette\line\b)
    If ncpRenderError=0 : ncpRenderError=ncpStatus(ncpText(*s\font,*s\x+12.0,*s\y+5.0,*s\title,*s\ar,*s\ag,*s\ab,1.0)) : EndIf
  EndIf
  ncpIssueBox(*s\x,*s\y,*s\w,1.0,palette\line\r,palette\line\g,palette\line\b)
  ncpIssueBox(*s\x,*s\y+*s\h-1.0,*s\w,1.0,palette\line\r,palette\line\g,palette\line\b)
  ncpIssueBox(*s\x,*s\y,1.0,*s\h,palette\line\r,palette\line\g,palette\line\b)
  ncpIssueBox(*s\x+*s\w-1.0,*s\y,1.0,*s\h,palette\line\r,palette\line\g,palette\line\b)
  If ncpRenderError=0 : *s\redraw=0 : *s\styleRevision=NeonChromeStyleRevision() : EndIf
  ncpBusy=0 : nstyLeave()
  ProcedureReturn ncpFail(*s,ncpRenderError)
EndProcedure
Procedure.i NeonChromePanelNeedsRedraw(*s.NeonChromePanelState)
  If ncpValid(*s)=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool(*s\redraw<>0 Or *s\styleRevision<>NeonChromeStyleRevision())
EndProcedure
Procedure.i NeonChromePanelTitle(*s.NeonChromePanelState)
  If ncpValid(*s)=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn *s\title
EndProcedure
Procedure.i NeonChromePanelError(*s.NeonChromePanelState)
  If ncpValid(*s)=0 : ProcedureReturn #NCP_ERR_STATE : EndIf
  ProcedureReturn *s\error
EndProcedure

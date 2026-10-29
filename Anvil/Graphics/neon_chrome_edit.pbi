; SPDX-License-Identifier: MIT
; Single-line UTF8 chrome editing. Caller owns text arena, input and frame.
XIncludeFile "Anvil/Math/float32.pbi"
XIncludeFile "Anvil/Graphics/neon_chrome_style.pbi"
XIncludeFile "Anvil/Graphics/neon_chrome_hotzones.pbi"
XIncludeFile "Anvil/Graphics/neon_utf8.pbi"
#NCE_MAGIC=$4E434531
#NCE_ERR_ARGS=-22100
#NCE_ERR_STATE=-22101
#NCE_ERR_BUSY=-22102
#NCE_ERR_CAPACITY=-22103
#NCE_ERR_RENDERER=-22104
#NCE_ERR_METRICS=-22105
#NCE_ERR_TEXT=-22106
#NCE_BACK=1
#NCE_DELETE=2
#NCE_LEFT=3
#NCE_RIGHT=4
#NCE_HOME=5
#NCE_END=6
#NCE_RETURN=7
#NCE_ESCAPE=8
#NCE_A=9
#NCE_C=10
#NCE_X=11
#NCE_V=12
Structure NeonChromeEditConfig Align #PB_Structure_AlignC
  id.i : font.i : text.i : placeholder.i
  x.f : y.f : w.f : h.f : scale.f
EndStructure
Structure NeonChromeEditInput Align #PB_Structure_AlignC
  down.i : blocked.i : key.i : ctrl.i : scalar.i : paste.i : pasteBudget.i
  x.f : y.f : dt.f
EndStructure
Structure NeonChromeEditState Align #PB_Structure_AlignC
  magic.i : id.i : font.i : arena.i : bytes.i : capacity.i
  text.i : placeholder.i : work.i : paste.i : clipboard.i
  length.i : placeholderLength.i : caret.i : all.i : down.i : over.i
  ready.i : submitted.i : changed.i : clipboardEvent.i : keyUsed.i : charUsed.i
  error.i : cleanupError.i : redraw.i
  x.f : y.f : w.f : h.f : scale.f : lineH.f : textW.f : caretW.f : phase.f
  styleRevision.i
EndStructure
Procedure.i nceBoxUnbound(x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
  ProcedureReturn #NCE_ERR_RENDERER
EndProcedure
Procedure.i nceTextUnbound(font.i,x.f,y.f,text.i,r.f,g.f,b.f,a.f)
  ProcedureReturn #NCE_ERR_RENDERER
EndProcedure
Procedure.f nceWidthUnbound(font.i,text.i)
  ProcedureReturn -1.0
EndProcedure
Procedure.f nceHeightUnbound(font.i)
  ProcedureReturn -1.0
EndProcedure
Procedure.i ncePrepareUnbound(font.i,text.i)
  ProcedureReturn #NCE_ERR_RENDERER
EndProcedure
Procedure.i nceClipUnbound(x.f,y.f,w.f,h.f)
  ProcedureReturn #NCE_ERR_RENDERER
EndProcedure
Procedure.i nceClearUnbound()
  ProcedureReturn #NCE_ERR_RENDERER
EndProcedure
Global nceBox.i=@nceBoxUnbound,nceText.i=@nceTextUnbound,nceWidth.i=@nceWidthUnbound,nceHeight.i=@nceHeightUnbound
Global ncePrepare.i=@ncePrepareUnbound,nceClip.i=@nceClipUnbound,nceClear.i=@nceClearUnbound
Procedure.f nceCaretUnbound(font.i,text.i,bytes.i,offset.i)
  ProcedureReturn -1.0
EndProcedure
Global nceCaret.i=@nceCaretUnbound,nceCaretActive.i
Global nceBusy.i,nceActive.i,nceDrawError.i
Procedure.i NeonChromeEditRendererInstall(boxProc.i,textProc.i,widthProc.i,heightProc.i,prepareProc.i,clipProc.i,clearProc.i)
  If nceBusy<>0 : ProcedureReturn #NCE_ERR_BUSY : EndIf
  If boxProc=0 Or textProc=0 Or widthProc=0 Or heightProc=0 Or prepareProc=0 Or clipProc=0 Or clearProc=0 : ProcedureReturn #NCE_ERR_ARGS : EndIf
  nceBox=boxProc : nceText=textProc : nceWidth=widthProc : nceHeight=heightProc
  ncePrepare=prepareProc : nceClip=clipProc : nceClear=clearProc : nceCaretActive=0 : nceActive=1 : ProcedureReturn 0
EndProcedure

 ; Optional whole-text caret callback; offset is a validated UTF8 byte boundary.
; Reinstalling the base renderer clears this binding to avoid a stale provider.
Procedure.i NeonChromeEditCaretRendererInstall(caretProc.i)
  If nceBusy<>0 : ProcedureReturn #NCE_ERR_BUSY : EndIf
  If nceActive=0 : ProcedureReturn #NCE_ERR_RENDERER : EndIf
  If caretProc=0 : ProcedureReturn #NCE_ERR_ARGS : EndIf
  nceCaret=caretProc : nceCaretActive=1 : ProcedureReturn 0
EndProcedure

Global nceFocus.i
Procedure.i nceValid(*s.NeonChromeEditState)
  If *s=0 Or (*s & 7)<>0 : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool(*s\magic=#NCE_MAGIC)
EndProcedure
Procedure.i nceFail(*s.NeonChromeEditState,rc.i)
  *s\error=rc : ProcedureReturn rc
EndProcedure
Procedure.i nceFinite(v.f)
  ProcedureReturn Bool((MathBitsOf(v) & $7FFFFFFF)<=$49742400)
EndProcedure
Procedure.i nceStatus(rc.i)
  If rc>0 : ProcedureReturn #NCE_ERR_RENDERER : EndIf
  ProcedureReturn rc
EndProcedure
Procedure.i nceLine(text.i,budget.i)
  Protected n.i=NeonUtf8Length(text,budget),i.i,cp.i
  If n<0 : ProcedureReturn #NCE_ERR_TEXT : EndIf
  While i<n
    cp=nutfScalar(text,i)
    If cp<32 Or cp=127 : ProcedureReturn #NCE_ERR_TEXT : EndIf
    i=NeonUtf8Next(text,n,i)
  Wend
  ProcedureReturn n
EndProcedure
Procedure.i nceOverlap(a.i,n.i,b.i,m.i)
  ProcedureReturn Bool(a<b+m And b<a+n)
EndProcedure
Procedure.i NeonChromeEditRequiredBytes(capacity.i)
  If capacity<4 Or capacity>4096 : ProcedureReturn 0 : EndIf
  ProcedureReturn capacity*5
EndProcedure
Procedure.i NeonChromeEditConfigure(*s.NeonChromeEditState,arena.i,bytes.i,capacity.i,*c.NeonChromeEditConfig)
  Protected needed.i=NeonChromeEditRequiredBytes(capacity),n.i,p.i,i.i,text.i,placeholder.i
  If nceBusy<>0 : ProcedureReturn #NCE_ERR_BUSY : EndIf
  If *s=0 Or (*s & 7)<>0 Or *c=0 Or (*c & 7)<>0 : ProcedureReturn #NCE_ERR_ARGS : EndIf
  If needed=0 Or arena<1 Or (arena & 7)<>0 Or bytes<needed Or arena+needed-1<arena : ProcedureReturn #NCE_ERR_ARGS : EndIf
  If nceOverlap(arena,needed,*s,SizeOf(NeonChromeEditState)) Or nceOverlap(arena,needed,*c,SizeOf(NeonChromeEditConfig)) Or nceOverlap(*c,SizeOf(NeonChromeEditConfig),*s,SizeOf(NeonChromeEditState)) : ProcedureReturn #NCE_ERR_ARGS : EndIf
  If *c\id<=0 Or *c\font<0 Or nceFinite(*c\x)=0 Or nceFinite(*c\y)=0 Or nceFinite(*c\w)=0 Or nceFinite(*c\h)=0 Or nceFinite(*c\scale)=0 : ProcedureReturn #NCE_ERR_ARGS : EndIf
  If *c\w<=2.0 Or *c\w>8192.0 Or *c\h<=2.0 Or *c\h>8192.0 Or *c\scale<=0.0 Or *c\scale>16.0 Or nceFinite(*c\x+*c\w)=0 Or nceFinite(*c\y+*c\h)=0 : ProcedureReturn #NCE_ERR_ARGS : EndIf
  text=*c\text : If text=0 : text="" : EndIf
  placeholder=*c\placeholder : If placeholder=0 : placeholder="" : EndIf
  n=nceLine(text,capacity) : p=nceLine(placeholder,capacity)
  If n<0 Or p<0 : ProcedureReturn #NCE_ERR_TEXT : EndIf
  If nceOverlap(text,n+1,arena,needed) Or nceOverlap(placeholder,p+1,arena,needed) Or nceOverlap(text,n+1,*s,SizeOf(NeonChromeEditState)) Or nceOverlap(placeholder,p+1,*s,SizeOf(NeonChromeEditState)) : ProcedureReturn #NCE_ERR_ARGS : EndIf
  For i=0 To SizeOf(NeonChromeEditState)-8 Step 8 : PokeI(*s+i,0) : Next
  *s\magic=#NCE_MAGIC : *s\id=*c\id : *s\font=*c\font : *s\arena=arena : *s\bytes=needed : *s\capacity=capacity
  *s\text=arena : *s\placeholder=arena+capacity : *s\work=arena+2*capacity : *s\paste=arena+3*capacity : *s\clipboard=arena+4*capacity
  For i=0 To n : PokeA(*s\text+i,PeekA(text+i)) : Next
  For i=0 To p : PokeA(*s\placeholder+i,PeekA(placeholder+i)) : Next
  PokeA(*s\clipboard,0) : *s\length=n : *s\placeholderLength=p : *s\caret=n
  *s\x=*c\x : *s\y=*c\y : *s\w=*c\w : *s\h=*c\h : *s\scale=*c\scale : *s\redraw=1
  ProcedureReturn 0
EndProcedure
Procedure.i NeonChromeEditSetText(*s.NeonChromeEditState,text.i,budget.i)
  Protected n.i,i.i
  If nceValid(*s)=0 : ProcedureReturn #NCE_ERR_STATE : EndIf
  If nceBusy<>0 : ProcedureReturn nceFail(*s,#NCE_ERR_BUSY) : EndIf
  If budget<1 Or budget>*s\capacity : ProcedureReturn nceFail(*s,#NCE_ERR_ARGS) : EndIf
  n=nceLine(text,budget) : If n<0 : ProcedureReturn nceFail(*s,n) : EndIf
  If nceOverlap(text,n+1,*s\arena,*s\bytes) Or nceOverlap(text,n+1,*s,SizeOf(NeonChromeEditState)) : ProcedureReturn nceFail(*s,#NCE_ERR_ARGS) : EndIf
  For i=0 To n : PokeA(*s\text+i,PeekA(text+i)) : Next
  *s\length=n : *s\caret=n : *s\all=0 : *s\ready=0 : *s\phase=0.0 : *s\changed=1 : *s\redraw=1
  ProcedureReturn nceFail(*s,0)
EndProcedure
Procedure.i NeonChromeEditFocus(*s.NeonChromeEditState,focused.i)
  If nceValid(*s)=0 : ProcedureReturn #NCE_ERR_STATE : EndIf
  If nceBusy<>0 : ProcedureReturn nceFail(*s,#NCE_ERR_BUSY) : EndIf
  If focused<>0 And focused<>1 : ProcedureReturn nceFail(*s,#NCE_ERR_ARGS) : EndIf
  If focused<>0 : nceFocus=*s\id : ElseIf nceFocus=*s\id : nceFocus=0 : EndIf
  *s\all=0 : *s\phase=0.0 : *s\redraw=1 : ProcedureReturn nceFail(*s,0)
EndProcedure
; Caret byte offsets must land on a UTF8 scalar boundary.
Procedure.i NeonChromeEditCaret(*s.NeonChromeEditState,offset.i)
  If nceValid(*s)=0 : ProcedureReturn #NCE_ERR_STATE : EndIf
  If nceBusy<>0 : ProcedureReturn nceFail(*s,#NCE_ERR_BUSY) : EndIf
  If offset<0 Or offset>*s\length : ProcedureReturn nceFail(*s,#NCE_ERR_ARGS) : EndIf
  If offset<*s\length And (PeekA(*s\text+offset) & 192)=128 : ProcedureReturn nceFail(*s,#NCE_ERR_ARGS) : EndIf
  *s\caret=offset : *s\all=0 : *s\ready=0 : *s\phase=0.0 : *s\redraw=1 : ProcedureReturn nceFail(*s,0)
EndProcedure
Procedure.i ncePrevious(text.i,offset.i)
  If offset<=0 : ProcedureReturn 0 : EndIf
  offset=offset-1
  While offset>0
    If (PeekA(text+offset) & 192)<>128 : Break : EndIf
    offset=offset-1
  Wend
  ProcedureReturn offset
EndProcedure
; Source is validated before any byte is published; newline terminates paste, tab becomes space.
Procedure.i ncePaste(*s.NeonChromeEditState,text.i,budget.i)
  Protected n.i=NeonUtf8Length(text,budget),i.i,j.i,b.i
  If n<0 : ProcedureReturn #NCE_ERR_TEXT : EndIf
  While i<n
    b=PeekA(text+i) & 255
    If b=10 Or b=13 : Break : EndIf
    If b<32 And b<>9 Or b=127 : ProcedureReturn #NCE_ERR_TEXT : EndIf
    If j>=*s\capacity-1 : ProcedureReturn #NCE_ERR_CAPACITY : EndIf
    If b=9 : b=32 : EndIf
    PokeA(*s\paste+j,b) : i=i+1 : j=j+1
  Wend
  PokeA(*s\paste+j,0) : ProcedureReturn j
EndProcedure
Procedure.i nceScalar(*s.NeonChromeEditState,cp.i)
  Protected n.i
  If cp<32 Or cp=127 Or cp>1114111 Or (cp>=55296 And cp<=57343) : ProcedureReturn #NCE_ERR_TEXT : EndIf
  If cp<128 : n=1 : ElseIf cp<2048 : n=2 : ElseIf cp<65536 : n=3 : Else : n=4 : EndIf
  If n>=*s\capacity : ProcedureReturn #NCE_ERR_CAPACITY : EndIf
  If cp<128 : n=1 : PokeA(*s\paste,cp)
  ElseIf cp<2048 : n=2 : PokeA(*s\paste,192 | (cp>>6)) : PokeA(*s\paste+1,128 | (cp & 63))
  ElseIf cp<65536
    n=3 : PokeA(*s\paste,224 | (cp>>12)) : PokeA(*s\paste+1,128 | ((cp>>6) & 63)) : PokeA(*s\paste+2,128 | (cp & 63))
  Else
    n=4 : PokeA(*s\paste,240 | (cp>>18)) : PokeA(*s\paste+1,128 | ((cp>>12) & 63)) : PokeA(*s\paste+2,128 | ((cp>>6) & 63)) : PokeA(*s\paste+3,128 | (cp & 63))
  EndIf
  PokeA(*s\paste+n,0) : ProcedureReturn n
EndProcedure
Procedure.i nceReplace(*s.NeonChromeEditState,first.i,last.i,insertBytes.i)
  Protected i.i,j.i,n.i=*s\length-(last-first)+insertBytes
  If n>=*s\capacity : ProcedureReturn #NCE_ERR_CAPACITY : EndIf
  For i=0 To first-1 : PokeA(*s\work+i,PeekA(*s\text+i)) : Next
  For i=0 To insertBytes-1 : PokeA(*s\work+first+i,PeekA(*s\paste+i)) : Next
  j=first+insertBytes
  For i=last To *s\length : PokeA(*s\work+j,PeekA(*s\text+i)) : j=j+1 : Next
  For i=0 To n : PokeA(*s\text+i,PeekA(*s\work+i)) : Next
  *s\length=n : *s\caret=first+insertBytes : *s\all=0 : *s\ready=0 : *s\changed=1 : *s\redraw=1 : *s\phase=0.0
  ProcedureReturn 0
EndProcedure
Procedure.i NeonChromeEditInput(*s.NeonChromeEditState,*e.NeonChromeEditInput)
  Protected clicked.i,focused.i,key.i,first.i,last.i,n.i,i.i,rc.i,dt.f
  If nceValid(*s)=0 : ProcedureReturn #NCE_ERR_STATE : EndIf
  If nceBusy<>0 : ProcedureReturn nceFail(*s,#NCE_ERR_BUSY) : EndIf
  If *e=0 Or (*e & 7)<>0 : ProcedureReturn nceFail(*s,#NCE_ERR_ARGS) : EndIf
  If *e\scalar<0 Or *e\scalar>1114111 Or (*e\scalar>=55296 And *e\scalar<=57343) : ProcedureReturn nceFail(*s,#NCE_ERR_TEXT) : EndIf
  If (*e\down<>0 And *e\down<>1) Or (*e\blocked<>0 And *e\blocked<>1) Or (*e\ctrl<>0 And *e\ctrl<>1) Or *e\key<0 Or *e\key>12 Or nceFinite(*e\x)=0 Or nceFinite(*e\y)=0 Or nceFinite(*e\dt)=0 Or *e\dt<0.0 : ProcedureReturn nceFail(*s,#NCE_ERR_ARGS) : EndIf
  *s\submitted=0 : *s\changed=0 : *s\clipboardEvent=0 : *s\keyUsed=0 : *s\charUsed=0
  first=*s\over
  clicked=Bool(*e\down<>0 And *s\down=0) : *s\down=*e\down
  *s\over=Bool(*e\blocked=0 And *e\x>=*s\x And *e\x<*s\x+*s\w And *e\y>=*s\y And *e\y<*s\y+*s\h)
  If first<>*s\over : *s\redraw=1 : EndIf
  If clicked<>0 And *e\blocked=0
    If *s\over<>0 : nceFocus=*s\id : ElseIf nceFocus=*s\id : nceFocus=0 : EndIf
    *s\all=0 : *s\redraw=1
  EndIf
  focused=Bool(nceFocus=*s\id)
  If focused=0 : *s\all=0 : ProcedureReturn nceFail(*s,0) : EndIf
  dt=*e\dt : If dt>0.05 : dt=0.05 : EndIf
  *s\phase=*s\phase+dt*3.4 : If *s\phase>6.283185 : *s\phase=*s\phase-6.283185 : EndIf
  *s\redraw=1
  If *e\blocked<>0 : ProcedureReturn nceFail(*s,0) : EndIf
  key=*e\key
  If *e\ctrl<>0
    If key=#NCE_A
      *s\all=1 : *s\caret=*s\length : *s\ready=0 : *s\keyUsed=1
    ElseIf key=#NCE_C Or key=#NCE_X
      *s\keyUsed=1
      If key=#NCE_C Or *s\all<>0
        For i=0 To *s\length : PokeA(*s\clipboard+i,PeekA(*s\text+i)) : Next
        *s\clipboardEvent=1
        If key=#NCE_X : *s\clipboardEvent=2 : rc=nceReplace(*s,0,*s\length,0) : EndIf
      EndIf
    ElseIf key=#NCE_V
      If *e\pasteBudget<1 Or *e\pasteBudget>65536 Or *e\paste=0 : ProcedureReturn nceFail(*s,#NCE_ERR_ARGS) : EndIf
      If nceOverlap(*e\paste,*e\pasteBudget,*s\arena,*s\bytes) Or nceOverlap(*e\paste,*e\pasteBudget,*s,SizeOf(NeonChromeEditState)) : ProcedureReturn nceFail(*s,#NCE_ERR_ARGS) : EndIf
      n=ncePaste(*s,*e\paste,*e\pasteBudget) : If n<0 : ProcedureReturn nceFail(*s,n) : EndIf
      first=*s\caret : last=first : If *s\all<>0 : first=0 : last=*s\length : EndIf
      rc=nceReplace(*s,first,last,n) : If rc<>0 : ProcedureReturn nceFail(*s,rc) : EndIf
      *s\keyUsed=1
    EndIf
    *s\charUsed=Bool(*e\scalar<>0) : ProcedureReturn nceFail(*s,0)
  EndIf
  If key>=#NCE_BACK And key<=#NCE_ESCAPE
    *s\keyUsed=1
    If key=#NCE_BACK Or key=#NCE_DELETE
      first=*s\caret : last=first
      If *s\all<>0 : first=0 : last=*s\length
      ElseIf key=#NCE_BACK : first=ncePrevious(*s\text,first)
      ElseIf last<*s\length : last=NeonUtf8Next(*s\text,*s\length,last) : EndIf
      If first<>last : rc=nceReplace(*s,first,last,0) : EndIf
      *s\all=0
    ElseIf key=#NCE_LEFT Or key=#NCE_RIGHT Or key=#NCE_HOME Or key=#NCE_END
      *s\all=0
      If key=#NCE_LEFT : *s\caret=ncePrevious(*s\text,*s\caret)
      ElseIf key=#NCE_RIGHT And *s\caret<*s\length : *s\caret=NeonUtf8Next(*s\text,*s\length,*s\caret)
      ElseIf key=#NCE_HOME : *s\caret=0
      ElseIf key=#NCE_END : *s\caret=*s\length : EndIf
      *s\ready=0
    ElseIf key=#NCE_RETURN : *s\submitted=1
    ElseIf key=#NCE_ESCAPE : nceFocus=0 : *s\all=0 : EndIf
  EndIf
  If *e\scalar>=32 And *e\scalar<>127
    n=nceScalar(*s,*e\scalar) : If n<0 : ProcedureReturn nceFail(*s,n) : EndIf
    first=*s\caret : last=first : If *s\all<>0 : first=0 : last=*s\length : EndIf
    rc=nceReplace(*s,first,last,n) : If rc<>0 : ProcedureReturn nceFail(*s,rc) : EndIf
    *s\charUsed=1
  EndIf
  ProcedureReturn nceFail(*s,0)
EndProcedure
Procedure.i NeonChromeEditSeal(*s.NeonChromeEditState)
  Protected rc.i,i.i,h.f,w.f,c.f
  If nceValid(*s)=0 : ProcedureReturn #NCE_ERR_STATE : EndIf
  If nceBusy<>0 : ProcedureReturn nceFail(*s,#NCE_ERR_BUSY) : EndIf
  If nceActive=0 : ProcedureReturn nceFail(*s,#NCE_ERR_RENDERER) : EndIf
  *s\ready=0 : nceBusy=1
  rc=nceStatus(ncePrepare(*s\font,*s\text))
  If rc=0 : rc=nceStatus(ncePrepare(*s\font,*s\placeholder)) : EndIf
  If rc=0
    h=nceHeight(*s\font) : w=nceWidth(*s\font,*s\text)
    If nceCaretActive<>0
      c=nceCaret(*s\font,*s\text,*s\length,*s\caret)
    Else
      For i=0 To *s\caret-1 : PokeA(*s\work+i,PeekA(*s\text+i)) : Next
      PokeA(*s\work+*s\caret,0) : c=nceWidth(*s\font,*s\work)
    EndIf
    If nceFinite(h)=0 Or nceFinite(w)=0 Or nceFinite(c)=0 Or h<=0.0 Or h>8192.0 Or w<0.0 Or c<0.0 Or c>w : rc=#NCE_ERR_METRICS : EndIf
  EndIf
  nceBusy=0
  If rc=0 : *s\lineH=h : *s\textW=w : *s\caretW=c : *s\ready=1 : EndIf
  ProcedureReturn nceFail(*s,rc)
EndProcedure
Procedure nceDrawBox(x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
  Protected rc.i
  If nceDrawError<>0 : ProcedureReturn : EndIf
  rc=nceStatus(nceBox(x,y,w,h,r,g,b,a)) : If rc<>0 : nceDrawError=rc : EndIf
EndProcedure
Procedure nceDrawText(font.i,x.f,y.f,text.i,r.f,g.f,b.f)
  Protected rc.i
  If nceDrawError<>0 : ProcedureReturn : EndIf
  rc=nceStatus(nceText(font,x,y,text,r,g,b,1.0)) : If rc<>0 : nceDrawError=rc : EndIf
EndProcedure
Procedure nceDrawClip(x.f,y.f,w.f,h.f)
  Protected rc.i
  If nceDrawError<>0 : ProcedureReturn : EndIf
  rc=nceStatus(nceClip(x,y,w,h)) : If rc<>0 : nceDrawError=rc : EndIf
EndProcedure

Procedure.i NeonChromeEditDraw(*s.NeonChromeEditState)
  Protected focused.i,rc.i,ty.f,r.f,g.f,b.f
  If nceValid(*s)=0 : ProcedureReturn #NCE_ERR_STATE : EndIf
  If nceBusy<>0 : ProcedureReturn nceFail(*s,#NCE_ERR_BUSY) : EndIf
  If *s\ready=0 : ProcedureReturn nceFail(*s,#NCE_ERR_STATE) : EndIf
  If nceActive=0 : ProcedureReturn nceFail(*s,#NCE_ERR_RENDERER) : EndIf
  nstyEnter() : nceBusy=1 : nceDrawError=0 : *s\cleanupError=0 : focused=Bool(nceFocus=*s\id)
  nceDrawError=nhzEmit(9,*s,*s\id,*s\x,*s\y,*s\w,*s\h)
  rc=nceStatus(nceClear()) : If rc<>0 : nceDrawError=rc : EndIf
  nceDrawBox(*s\x,*s\y,*s\w,*s\h,nstyPalette\field\r,nstyPalette\field\g,nstyPalette\field\b,1.0)
  r=nstyPalette\line\r : g=nstyPalette\line\g : b=nstyPalette\line\b
  If focused<>0 : r=nstyPalette\accent\r : g=nstyPalette\accent\g : b=nstyPalette\accent\b
  ElseIf *s\over<>0 : r=nstyPalette\dim\r : g=nstyPalette\dim\g : b=nstyPalette\dim\b : EndIf
  nceDrawBox(*s\x,*s\y,*s\w,1.0,r,g,b,1.0)
  nceDrawBox(*s\x,*s\y+*s\h-1.0,*s\w,1.0,r,g,b,1.0)
  nceDrawBox(*s\x,*s\y+1.0,1.0,*s\h-2.0,r,g,b,1.0)
  nceDrawBox(*s\x+*s\w-1.0,*s\y+1.0,1.0,*s\h-2.0,r,g,b,1.0)
  ty=*s\y+(*s\h-*s\lineH)/2.0
  nceDrawClip(*s\x+1.0,*s\y+1.0,*s\w-2.0,*s\h-2.0)
  If focused<>0 And *s\all<>0 And *s\length>0 : nceDrawBox(*s\x+6.0* *s\scale,ty,*s\textW+4.0* *s\scale,*s\lineH,nstyPalette\accent\r,nstyPalette\accent\g,nstyPalette\accent\b,0.35) : EndIf
  If *s\length=0 And focused=0
    nceDrawText(*s\font,*s\x+8.0* *s\scale,ty,*s\placeholder,nstyPalette\faint\r,nstyPalette\faint\g,nstyPalette\faint\b)
  Else
    nceDrawText(*s\font,*s\x+8.0* *s\scale,ty,*s\text,nstyPalette\text\r,nstyPalette\text\g,nstyPalette\text\b)
  EndIf
  If focused<>0 And (nstyAnimations=0 Or Sin(*s\phase)>-0.2) : nceDrawBox(*s\x+8.0* *s\scale+*s\caretW,ty,1.5* *s\scale,*s\lineH,nstyPalette\accent\r,nstyPalette\accent\g,nstyPalette\accent\b,1.0) : EndIf
  *s\cleanupError=nceStatus(nceClear()) : If nceDrawError=0 : nceDrawError=*s\cleanupError : EndIf
  If nceDrawError=0 : *s\styleRevision=NeonChromeStyleRevision() : EndIf
  nceBusy=0 : nstyLeave() : If nceDrawError=0 : *s\redraw=0 : EndIf
  ProcedureReturn nceFail(*s,nceDrawError)
EndProcedure
Procedure.i NeonChromeEditText(*s.NeonChromeEditState)
  If nceValid(*s)=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn *s\text
EndProcedure
Procedure.i NeonChromeEditClipboard(*s.NeonChromeEditState)
  If nceValid(*s)=0 Or *s\clipboardEvent=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn *s\clipboard
EndProcedure
Procedure.i NeonChromeEditFocused(*s.NeonChromeEditState)
  If nceValid(*s)=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool(nceFocus=*s\id)
EndProcedure
Procedure.i NeonChromeEditNeedsRedraw(*s.NeonChromeEditState)
  If nceValid(*s)=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool((nceFocus=*s\id And nstyAnimations<>0) Or *s\redraw<>0 Or *s\styleRevision<>NeonChromeStyleRevision())
EndProcedure

; SPDX-License-Identifier: MIT
; Draw-owned double-buffered hover regions. Reference: GlUIChrome hot zones.
XIncludeFile "Anvil/Graphics/neon_chrome_style.pbi"
#NHZ_MAGIC=$4E485A31
#NHZ_ERR_ARGS=-22700
#NHZ_ERR_STATE=-22701
#NHZ_ERR_CAPACITY=-22702
#NHZ_ERR_BUSY=-22703
Structure NeonChromeHotIdentity Align #PB_Structure_AlignC
  family.i : owner.i : item.i
EndStructure
Structure NeonChromeHotRegion Align #PB_Structure_AlignC
  identity.NeonChromeHotIdentity
  x.f : y.f : w.f : h.f
EndStructure
Structure NeonChromeHotState Align #PB_Structure_AlignC
  magic.i : arena.i : bytes.i : capacity.i : current.i : previous.i : count.i : previousCount.i : open.i : error.i
EndStructure
Global nhzBound.i
Procedure.i nhzValid(*s.NeonChromeHotState)
  If *s=0 Or (*s & 7)<>0 : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool(*s\magic=#NHZ_MAGIC)
EndProcedure
Procedure.i nhzOverlap(a.i,ab.i,b.i,bb.i)
  ProcedureReturn Bool(a<b+bb And b<a+ab)
EndProcedure
Procedure.i NeonChromeHotBytes(capacity.i)
  If capacity<1 Or capacity>4096 : ProcedureReturn #NHZ_ERR_ARGS : EndIf
  ProcedureReturn capacity*2*SizeOf(NeonChromeHotRegion)
EndProcedure
Procedure.i NeonChromeHotConfigure(*s.NeonChromeHotState,arena.i,bytes.i,capacity.i)
  Protected need.i=NeonChromeHotBytes(capacity),i.i
  If nstyBusy<>0 : ProcedureReturn #NHZ_ERR_BUSY : EndIf
  If *s=0 Or (*s & 7)<>0 Or need<0 Or arena=0 Or (arena & 7)<>0 Or bytes<need Or arena+need<arena Or nhzOverlap(*s,SizeOf(NeonChromeHotState),arena,need)<>0 : ProcedureReturn #NHZ_ERR_ARGS : EndIf
  If nhzValid(*s)<>0 : If *s\open<>0 : ProcedureReturn #NHZ_ERR_STATE : EndIf : EndIf
  For i=0 To SizeOf(NeonChromeHotState)-1 : PokeA(*s+i,0) : Next
  *s\magic=#NHZ_MAGIC : *s\arena=arena : *s\bytes=need : *s\capacity=capacity
  *s\current=arena : *s\previous=arena+capacity*SizeOf(NeonChromeHotRegion)
  ProcedureReturn 0
EndProcedure
Procedure.i NeonChromeHotBind(*s.NeonChromeHotState)
  Protected *old.NeonChromeHotState=nhzBound
  If nstyBusy<>0 : ProcedureReturn #NHZ_ERR_BUSY : EndIf
  If *s<>0 : If nhzValid(*s)=0 : ProcedureReturn #NHZ_ERR_STATE : EndIf : If *s\open<>0 : ProcedureReturn #NHZ_ERR_STATE : EndIf : EndIf
  If *old<>0 : If *old\open<>0 : ProcedureReturn #NHZ_ERR_STATE : EndIf : EndIf
  nhzBound=*s : ProcedureReturn 0
EndProcedure
Procedure.i NeonChromeHotBegin(*s.NeonChromeHotState)
  If nstyBusy<>0 : ProcedureReturn #NHZ_ERR_BUSY : EndIf
  If nhzValid(*s)=0 : ProcedureReturn #NHZ_ERR_STATE : EndIf
  If *s\open<>0 : ProcedureReturn #NHZ_ERR_STATE : EndIf
  *s\count=0 : *s\error=0 : *s\open=1 : ProcedureReturn 0
EndProcedure
Procedure.i nhzAdd(*s.NeonChromeHotState,family.i,owner.i,item.i,x.f,y.f,w.f,h.f)
  Protected *n.NeonChromeHotRegion
  If nhzValid(*s)=0 : ProcedureReturn #NHZ_ERR_STATE : EndIf
  If *s\open=0 : ProcedureReturn #NHZ_ERR_STATE : EndIf
  If family<0 Or (family=0 And (owner<>0 Or item<>0)) Or (family>0 And owner=0) Or item<0 Or (MathBitsOf(x) & $7FFFFFFF)>$49742400 Or (MathBitsOf(y) & $7FFFFFFF)>$49742400 Or (MathBitsOf(w) & $7FFFFFFF)>$49742400 Or (MathBitsOf(h) & $7FFFFFFF)>$49742400 Or w<0.0 Or h<0.0 : *s\error=#NHZ_ERR_ARGS : ProcedureReturn #NHZ_ERR_ARGS : EndIf
  If w=0.0 Or h=0.0 : ProcedureReturn 0 : EndIf
  If *s\count=*s\capacity : *s\error=#NHZ_ERR_CAPACITY : ProcedureReturn #NHZ_ERR_CAPACITY : EndIf
  *n=*s\current+*s\count*SizeOf(NeonChromeHotRegion)
  *n\identity\family=family : *n\identity\owner=owner : *n\identity\item=item
  *n\x=x : *n\y=y : *n\w=w : *n\h=h : *s\count=*s\count+1
  ProcedureReturn 0
EndProcedure
Procedure.i NeonChromeHotAdd(*s.NeonChromeHotState,family.i,owner.i,item.i,x.f,y.f,w.f,h.f)
  If nstyBusy<>0 : ProcedureReturn #NHZ_ERR_BUSY : EndIf
  If family<1 : ProcedureReturn #NHZ_ERR_ARGS : EndIf
  ProcedureReturn nhzAdd(*s,family,owner,item,x,y,w,h)
EndProcedure
Procedure.i nhzEmit(family.i,owner.i,item.i,x.f,y.f,w.f,h.f)
  If nhzBound=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn nhzAdd(nhzBound,family,owner,item,x,y,w,h)
EndProcedure
Procedure.i nhzBlock(x.f,y.f,w.f,h.f)
  If nhzBound=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn nhzAdd(nhzBound,0,0,0,x,y,w,h)
EndProcedure
Procedure.i nhzEmitClip(family.i,owner.i,item.i,x.f,y.f,w.f,h.f,cx.f,cy.f,cw.f,ch.f)
  Protected right.f=x+w,bottom.f=y+h
  If nhzBound=0 : ProcedureReturn 0 : EndIf
  If x<cx : x=cx : EndIf
  If y<cy : y=cy : EndIf
  If right>cx+cw : right=cx+cw : EndIf
  If bottom>cy+ch : bottom=cy+ch : EndIf
  If right<=x Or bottom<=y : ProcedureReturn 0 : EndIf
  ProcedureReturn nhzAdd(nhzBound,family,owner,item,x,y,right-x,bottom-y)
EndProcedure
Procedure.i NeonChromeHotCommit(*s.NeonChromeHotState)
  Protected old.i
  If nstyBusy<>0 : ProcedureReturn #NHZ_ERR_BUSY : EndIf
  If nhzValid(*s)=0 : ProcedureReturn #NHZ_ERR_STATE : EndIf
  If *s\open=0 : ProcedureReturn #NHZ_ERR_STATE : EndIf
  If *s\error<>0 : ProcedureReturn *s\error : EndIf
  old=*s\previous : *s\previous=*s\current : *s\current=old
  *s\previousCount=*s\count : *s\count=0 : *s\error=0 : *s\open=0 : ProcedureReturn 0
EndProcedure
Procedure.i NeonChromeHotAbort(*s.NeonChromeHotState)
  If nstyBusy<>0 : ProcedureReturn #NHZ_ERR_BUSY : EndIf
  If nhzValid(*s)=0 : ProcedureReturn #NHZ_ERR_STATE : EndIf
  If *s\open=0 : ProcedureReturn #NHZ_ERR_STATE : EndIf
  *s\count=0 : *s\error=0 : *s\open=0 : ProcedureReturn 0
EndProcedure
Procedure.i NeonChromeHotAt(*s.NeonChromeHotState,x.f,y.f,*out.NeonChromeHotIdentity)
  Protected i.i,*n.NeonChromeHotRegion
  If nhzValid(*s)=0 : ProcedureReturn #NHZ_ERR_STATE : EndIf
  If (MathBitsOf(x) & $7FFFFFFF)>$49742400 Or (MathBitsOf(y) & $7FFFFFFF)>$49742400 : ProcedureReturn #NHZ_ERR_ARGS : EndIf
  If *out<>0
    If (*out & 7)<>0 Or *out+SizeOf(NeonChromeHotIdentity)<*out Or nhzOverlap(*out,SizeOf(NeonChromeHotIdentity),*s,SizeOf(NeonChromeHotState))<>0 Or nhzOverlap(*out,SizeOf(NeonChromeHotIdentity),*s\arena,*s\bytes)<>0 : ProcedureReturn #NHZ_ERR_ARGS : EndIf
    *out\family=0 : *out\owner=0 : *out\item=0
  EndIf
  For i=*s\previousCount-1 To 0 Step -1
    *n=*s\previous+i*SizeOf(NeonChromeHotRegion)
    If x>=*n\x And x<*n\x+*n\w And y>=*n\y And y<*n\y+*n\h
      If *n\identity\family=0 : ProcedureReturn 0 : EndIf
      If *out<>0 : *out\family=*n\identity\family : *out\owner=*n\identity\owner : *out\item=*n\identity\item : EndIf
      ProcedureReturn 1
    EndIf
  Next
  ProcedureReturn 0
EndProcedure
Procedure.i NeonChromeHotChanged(*s.NeonChromeHotState,oldX.f,oldY.f,x.f,y.f)
  Protected a.NeonChromeHotIdentity,b.NeonChromeHotIdentity,rc.i
  rc=NeonChromeHotAt(*s,oldX,oldY,@a) : If rc<0 : ProcedureReturn rc : EndIf
  rc=NeonChromeHotAt(*s,x,y,@b) : If rc<0 : ProcedureReturn rc : EndIf
  ProcedureReturn Bool(a\family<>b\family Or a\owner<>b\owner Or a\item<>b\item)
EndProcedure

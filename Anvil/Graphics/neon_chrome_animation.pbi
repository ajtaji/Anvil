; SPDX-License-Identifier: MIT
; Bounded keyed chrome easing. Semantic reference: GlUIChrome Neon_Animate.
XIncludeFile "Anvil/Graphics/neon_utf8.pbi"
XIncludeFile "Anvil/Graphics/neon_chrome_style.pbi"
#NAN_MAGIC=$4E414E31
#NAN_ERR_ARGS=-22600
#NAN_ERR_STATE=-22601
#NAN_ERR_CAPACITY=-22602
#NAN_ERR_KEY=-22603
Structure NeonChromeAnimationSlot Align #PB_Structure_AlignC
  used.i : length.i : key.i : value.f
EndStructure
Structure NeonChromeAnimationState Align #PB_Structure_AlignC
  magic.i : arena.i : bytes.i : capacity.i : keyBytes.i : count.i : open.i : active.i
  dt.f
EndStructure
Structure NeonChromeAnimationValue Align #PB_Structure_AlignC
  value.f : moving.i
EndStructure
Procedure.i nanOverlap(a.i,ab.i,b.i,bb.i)
  ProcedureReturn Bool(a<b+bb And b<a+ab)
EndProcedure
Procedure.i nanValid(*s.NeonChromeAnimationState)
  If *s=0 Or (*s & 7)<>0 : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool(*s\magic=#NAN_MAGIC)
EndProcedure
Procedure.i NeonChromeAnimationBytes(capacity.i,keyBytes.i)
  If capacity<1 Or capacity>4096 Or keyBytes<4 Or keyBytes>256 : ProcedureReturn #NAN_ERR_ARGS : EndIf
  ProcedureReturn capacity*(SizeOf(NeonChromeAnimationSlot)+keyBytes)
EndProcedure
Procedure.i NeonChromeAnimationConfigure(*s.NeonChromeAnimationState,arena.i,bytes.i,capacity.i,keyBytes.i)
  Protected need.i=NeonChromeAnimationBytes(capacity,keyBytes),i.i
  If *s=0 Or (*s & 7)<>0 Or need<0 Or arena=0 Or (arena & 7)<>0 Or bytes<need Or arena+need<arena : ProcedureReturn #NAN_ERR_ARGS : EndIf
  If nanOverlap(*s,SizeOf(NeonChromeAnimationState),arena,need)<>0 : ProcedureReturn #NAN_ERR_ARGS : EndIf
  If nanValid(*s)<>0 : If *s\open<>0 : ProcedureReturn #NAN_ERR_STATE : EndIf : EndIf
  For i=0 To SizeOf(NeonChromeAnimationState)-1 : PokeA(*s+i,0) : Next
  For i=0 To need-1 : PokeA(arena+i,0) : Next
  *s\magic=#NAN_MAGIC : *s\arena=arena : *s\bytes=need : *s\capacity=capacity : *s\keyBytes=keyBytes
  ProcedureReturn 0
EndProcedure
Procedure.i NeonChromeAnimationBegin(*s.NeonChromeAnimationState,dt.f)
  If nanValid(*s)=0 : ProcedureReturn #NAN_ERR_STATE : EndIf
  If *s\open<>0 : ProcedureReturn #NAN_ERR_STATE : EndIf
  If (MathBitsOf(dt) & $7FFFFFFF)>$49742400 : ProcedureReturn #NAN_ERR_ARGS : EndIf
  If dt<0.0 : dt=0.0 : EndIf
  If dt>0.05 : dt=0.05 : EndIf
  *s\dt=dt : *s\open=1 : *s\active=0 : ProcedureReturn 0
EndProcedure
Procedure.i nanSlot(*s.NeonChromeAnimationState,key.i,length.i)
  Protected i.i,j.i,*n.NeonChromeAnimationSlot,same.i
  For i=0 To *s\capacity-1
    *n=*s\arena+i*SizeOf(NeonChromeAnimationSlot)
    If *n\used=0 Or *n\length<>length : Continue : EndIf
    same=1
    For j=0 To length-1 : If PeekA(*n\key+j)<>PeekA(key+j) : same=0 : Break : EndIf : Next
    If same<>0 : ProcedureReturn *n : EndIf
  Next
  ProcedureReturn 0
EndProcedure
Procedure.i NeonChromeAnimationStep(*s.NeonChromeAnimationState,key.i,target.f,speed.f,initial.f,useInitial.i,*out.NeonChromeAnimationValue)
  Protected length.i,*n.NeonChromeAnimationSlot,i.i,value.f,moving.i
  If nanValid(*s)=0 : ProcedureReturn #NAN_ERR_STATE : EndIf
  If *s\open=0 : ProcedureReturn #NAN_ERR_STATE : EndIf
  If key=0 Or *out=0 Or (*out & 7)<>0 Or *out+SizeOf(NeonChromeAnimationValue)<*out : ProcedureReturn #NAN_ERR_ARGS : EndIf
  If nanOverlap(*out,SizeOf(NeonChromeAnimationValue),*s,SizeOf(NeonChromeAnimationState))<>0 Or nanOverlap(*out,SizeOf(NeonChromeAnimationValue),*s\arena,*s\bytes)<>0 : ProcedureReturn #NAN_ERR_ARGS : EndIf
  If (MathBitsOf(target) & $7FFFFFFF)>$49742400 Or (MathBitsOf(initial) & $7FFFFFFF)>$49742400 Or (MathBitsOf(speed) & $7FFFFFFF)>$447A0000 Or speed<0.0 Or (useInitial<>0 And useInitial<>1) : ProcedureReturn #NAN_ERR_ARGS : EndIf
  length=NeonUtf8Length(key,*s\keyBytes)
  If length<0 : ProcedureReturn #NAN_ERR_KEY : EndIf
  If nanOverlap(*out,SizeOf(NeonChromeAnimationValue),key,length+1)<>0 Or nanOverlap(key,length+1,*s,SizeOf(NeonChromeAnimationState))<>0 Or nanOverlap(key,length+1,*s\arena,*s\bytes)<>0 : ProcedureReturn #NAN_ERR_ARGS : EndIf
  *n=nanSlot(*s,key,length)
  If *n=0
    If *s\count=*s\capacity : ProcedureReturn #NAN_ERR_CAPACITY : EndIf
    For i=0 To *s\capacity-1
      *n=*s\arena+i*SizeOf(NeonChromeAnimationSlot)
      If *n\used=0 : Break : EndIf
    Next
    value=target : If useInitial<>0 : value=initial : EndIf
  Else : value=*n\value : EndIf
  If NeonChromeStyleAnimationsGet()=0
    value=target
  Else
    value=value+(target-value)*(1.0-Exp(0.0-speed* *s\dt))
    If Abs(target-value)<0.002 : value=target : Else : moving=1 : EndIf
  EndIf
  If *n\used=0
    *n\key=*s\arena+*s\capacity*SizeOf(NeonChromeAnimationSlot)+( (*n-*s\arena)/SizeOf(NeonChromeAnimationSlot))* *s\keyBytes
    For i=0 To length : PokeA(*n\key+i,PeekA(key+i)) : Next
    *n\length=length : *n\used=1 : *s\count=*s\count+1
  EndIf
  *n\value=value : If moving<>0 : *s\active=1 : EndIf
  *out\value=value : *out\moving=moving : ProcedureReturn 0
EndProcedure
Procedure.i NeonChromeAnimationEnd(*s.NeonChromeAnimationState)
  If nanValid(*s)=0 : ProcedureReturn #NAN_ERR_STATE : EndIf
  If *s\open=0 : ProcedureReturn #NAN_ERR_STATE : EndIf
  *s\open=0 : ProcedureReturn 0
EndProcedure
Procedure.i NeonChromeAnimationActive(*s.NeonChromeAnimationState)
  If nanValid(*s)=0 : ProcedureReturn #NAN_ERR_STATE : EndIf
  ProcedureReturn *s\active
EndProcedure
Procedure.i NeonChromeAnimationForget(*s.NeonChromeAnimationState,key.i)
  Protected length.i,*n.NeonChromeAnimationSlot
  If nanValid(*s)=0 : ProcedureReturn #NAN_ERR_STATE : EndIf
  If *s\open<>0 : ProcedureReturn #NAN_ERR_STATE : EndIf
  length=NeonUtf8Length(key,*s\keyBytes) : If length<0 : ProcedureReturn #NAN_ERR_KEY : EndIf
  *n=nanSlot(*s,key,length)
  If *n<>0 : *n\used=0 : *s\count=*s\count-1 : EndIf
  ProcedureReturn 0
EndProcedure

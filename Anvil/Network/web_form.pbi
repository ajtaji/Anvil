; Bounded incremental application/x-www-form-urlencoded field serializer.
; WHATWG URL section 5.2; inputs are byte spans already encoded as UTF-8.
; Emits spaces as '+', literal '+' as '%2B', and uppercase percent escapes.
; No allocation, transport, Unicode conversion or newline normalization.
#WEB_FORM_ARGUMENT=-650
#WEB_FORM_STATE=-651
#WEB_FORM_MAX=1048576
Structure WebForm
 name.i
 nameBytes.i
 value.i
 valueBytes.i
 offset.i
 phase.i
 escaped.i
 digit.i
 length.i
EndStructure

Procedure.i wfSafe(c.i)
 ProcedureReturn Bool((c>=65 And c<=90) Or (c>=97 And c<=122) Or (c>=48 And c<=57) Or c=42 Or c=45 Or c=46 Or c=95)
EndProcedure

Procedure.i WebFormInit(*s.WebForm,name.i,nameBytes.i,value.i,valueBytes.i,separator.i)
 Define i.i,c.i,n.i
 If *s=0 : ProcedureReturn #WEB_FORM_ARGUMENT : EndIf
 For i=0 To SizeOf(WebForm)-1 : PokeA(*s+i,0) : Next
 *s\phase=-1
 If nameBytes<0 Or nameBytes>#WEB_FORM_MAX Or valueBytes<0 Or valueBytes>#WEB_FORM_MAX Or (nameBytes>0 And name=0) Or (valueBytes>0 And value=0) Or (separator<>0 And separator<>1)
  ProcedureReturn #WEB_FORM_ARGUMENT
 EndIf
 n=1+separator
 For i=0 To nameBytes-1
  c=PeekA(name+i) & 255
  If wfSafe(c) Or c=32 : n=n+1 : Else : n=n+3 : EndIf
 Next
 For i=0 To valueBytes-1
  c=PeekA(value+i) & 255
  If wfSafe(c) Or c=32 : n=n+1 : Else : n=n+3 : EndIf
 Next
 *s\name=name : *s\nameBytes=nameBytes : *s\value=value : *s\valueBytes=valueBytes
 *s\phase=1-separator : *s\length=n
 ProcedureReturn n
EndProcedure

; Return bytes written, or a negative error. phase=4 means complete.
; Input buffers remain unchanged/alive until complete, and must not overlap
; the output or context. Zero capacity is ordinary backpressure, not EOF.
Procedure.i WebFormOutput(*s.WebForm,dst.i,capacity.i)
 Define n.i,c.i,p.i,bytes.i,h.i
 If *s=0 Or capacity<0 Or capacity>#WEB_FORM_MAX Or (capacity>0 And dst=0) : ProcedureReturn #WEB_FORM_ARGUMENT : EndIf
 If *s\phase<0 Or *s\phase>4 : ProcedureReturn #WEB_FORM_STATE : EndIf
 While n<capacity And *s\phase<4
  If *s\digit>0
   If *s\digit=2 : h=(*s\escaped>>4) & 15 : Else : h=*s\escaped & 15 : EndIf
   If h<10 : c=48+h : Else : c=65+h-10 : EndIf
   *s\digit=*s\digit-1
  ElseIf *s\phase=0
   c=38 : *s\phase=1
  ElseIf *s\phase=2
   c=61 : *s\phase=3 : *s\offset=0
  Else
   If *s\phase=1 : p=*s\name : bytes=*s\nameBytes : Else : p=*s\value : bytes=*s\valueBytes : EndIf
   If *s\offset=bytes : *s\phase=*s\phase+1 : Continue : EndIf
   c=PeekA(p+*s\offset) & 255 : *s\offset=*s\offset+1
   If c=32
    c=43
   ElseIf wfSafe(c)=0
    *s\escaped=c : *s\digit=2 : c=37
   EndIf
  EndIf
  PokeA(dst+n,c) : n=n+1
 Wend
 ; Mark exact-capacity completion without needing one extra output call.
 If *s\phase=3 And *s\offset=*s\valueBytes And *s\digit=0 : *s\phase=4 : EndIf
 ProcedureReturn n
EndProcedure

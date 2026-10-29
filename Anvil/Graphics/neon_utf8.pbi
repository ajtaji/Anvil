; SPDX-License-Identifier: MIT
; Bounded UTF8 scalar and prefix helpers for chrome labels and editing.
#NEON_UTF8_ERR=-22006
Procedure.i NeonUtf8Next(text.i,bytes.i,index.i)
  Protected b.i,c.i,n.i,i.i,cp.i,min.i
  If text=0 Or bytes<0 Or index<0 Or index>=bytes : ProcedureReturn #NEON_UTF8_ERR : EndIf
  b=PeekA(text+index) & 255
  If b<128 : ProcedureReturn index+1 : EndIf
  If b>=194 And b<=223 : n=2 : cp=b & 31 : min=128
  ElseIf b>=224 And b<=239 : n=3 : cp=b & 15 : min=2048
  ElseIf b>=240 And b<=244 : n=4 : cp=b & 7 : min=65536
  Else : ProcedureReturn #NEON_UTF8_ERR : EndIf
  If n>bytes-index : ProcedureReturn #NEON_UTF8_ERR : EndIf
  For i=1 To n-1
    c=PeekA(text+index+i) & 255
    If c<128 Or c>191 : ProcedureReturn #NEON_UTF8_ERR : EndIf
    cp=(cp<<6) | (c & 63)
  Next
  If cp<min Or cp>1114111 Or (cp>=55296 And cp<=57343) : ProcedureReturn #NEON_UTF8_ERR : EndIf
  ProcedureReturn index+n
EndProcedure
; Decode one validated scalar at an explicit byte boundary. Invalid pointers,
; spans, indices, continuation-byte starts and malformed sequences refuse.
Procedure.i NeonUtf8ScalarAt(text.i,bytes.i,index.i)
  If text<1 Or bytes<1 Or text+bytes<=text : ProcedureReturn #NEON_UTF8_ERR : EndIf
  If NeonUtf8Next(text,bytes,index)<0 : ProcedureReturn #NEON_UTF8_ERR : EndIf
  ProcedureReturn nutfScalar(text,index)
EndProcedure
Procedure.i NeonUtf8Length(text.i,budget.i)
  Protected bytes.i,i.i,nextEnd.i
  If text=0 Or budget<1 Or text+budget-1<text : ProcedureReturn #NEON_UTF8_ERR : EndIf
  While bytes<budget
    If (PeekA(text+bytes) & 255)=0 : Break : EndIf
    bytes=bytes+1
  Wend
  If bytes=budget : ProcedureReturn #NEON_UTF8_ERR : EndIf
  While i<bytes
    nextEnd=NeonUtf8Next(text,bytes,i)
    If nextEnd<0 : ProcedureReturn nextEnd : EndIf
    i=nextEnd
  Wend
  ProcedureReturn bytes
EndProcedure
Procedure.i nutfScalar(text.i,index.i)
  Protected b.i,n.i,cp.i,i.i
  b=PeekA(text+index) & 255
  If b<128 : ProcedureReturn b : EndIf
  If b<224 : n=2 : cp=b & 31 : ElseIf b<240 : n=3 : cp=b & 15 : Else : n=4 : cp=b & 7 : EndIf
  For i=1 To n-1 : cp=(cp<<6) | (PeekA(text+index+i) & 63) : Next
  ProcedureReturn cp
EndProcedure
; The caller first validates the full string. These boundaries cover UTF8,
; desktop combining/variation ranges and joiners, not all grapheme rules.
Procedure.i NeonUtf8Prefix(text.i,bytes.i,cut.i)
  Protected previous.i,nextCp.i,prevCp.i,joined.i
  If text=0 Or bytes<0 : ProcedureReturn #NEON_UTF8_ERR : EndIf
  If cut<0 : cut=0 : EndIf
  If cut>bytes : cut=bytes : EndIf
  While cut>0 And cut<bytes
    If (PeekA(text+cut) & 192)<>128 : Break : EndIf
    cut=cut-1
  Wend
  While cut>0
    previous=cut-1
    While previous>0
      If (PeekA(text+previous) & 192)<>128 : Break : EndIf
      previous=previous-1
    Wend
    nextCp=0 : If cut<bytes : nextCp=nutfScalar(text,cut) : EndIf
    prevCp=nutfScalar(text,previous)
    joined=Bool((nextCp>=768 And nextCp<=879) Or (nextCp>=65024 And nextCp<=65039) Or nextCp=8205 Or prevCp=8205)
    If joined=0 : Break : EndIf
    cut=previous
  Wend
  While cut>0
    If (PeekA(text+cut-1) & 255)<>32 : Break : EndIf
    cut=cut-1
  Wend
  ProcedureReturn cut
EndProcedure

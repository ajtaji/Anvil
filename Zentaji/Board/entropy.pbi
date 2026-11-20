; Only the optional host source is suitable for a live entropy request.
; The legacy seeded registers retain their reproducible machine behavior.
#ZEN_ENTROPY_BASE=$FFFF000000090000
Procedure.i HwEntropyAvailable()
 ProcedureReturn Bool(PeekQ(#ZEN_ENTROPY_BASE+$60)=1)
EndProcedure

Procedure.i HwEntropyRead(dst.i,n.i)
 Protected word.q,i.i,j.i
 If dst<=0 Or n<1 Or n>zenMemoryRam Or dst>zenMemoryRam-n : ProcedureReturn -1 : EndIf
 i=0
 If HwEntropyAvailable()<>0
  While i<n
   word=PeekQ(#ZEN_ENTROPY_BASE+$68)
   If word<0 Or word>$FFFFFFFF : Break : EndIf
   For j=0 To 3
    PokeA(dst+i,word&255) : i=i+1
    If i=n : ProcedureReturn n : EndIf
    word=word>>8
   Next
  Wend
 EndIf
 For i=0 To n-1 : PokeA(dst+i,0) : Next
 ProcedureReturn -1
EndProcedure

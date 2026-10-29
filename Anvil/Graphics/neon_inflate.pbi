; SPDX-License-Identifier: MIT
; Caller-owned, one-shot raw DEFLATE/zlib decoder for encoded sprite data.
; Output is disposable on error; no success is returned before stream checks.
XIncludeFile "Anvil/Graphics/neon_byte_ranges.pbi"
#NEON_INFLATE_WORK_BYTES=8192
#NEON_INFLATE_MAX_BYTES=16777216
#NEON_INFLATE_ERR_ARGUMENT=-22900
#NEON_INFLATE_ERR_TRUNCATED=-22901
#NEON_INFLATE_ERR_FORMAT=-22902
#NEON_INFLATE_ERR_CAPACITY=-22903
#NEON_INFLATE_ERR_CHECKSUM=-22904
#NEON_INFLATE_ERR_DICTIONARY=-22905
Structure NeonInflateState Align #PB_Structure_AlignC
  source.i : sourceBytes.i : offset.i : bits.i : bitCount.i
  target.i : capacity.i : produced.i : error.i : window.i : work.i
EndStructure
Procedure.i ndiStart(*s.NeonInflateState,work.i,workBytes.i,source.i,sourceBytes.i,target.i,capacity.i)
  Protected i.i,span.i=capacity
  If *s=0 Or (*s & 7)<>0 Or work=0 Or (work & 7)<>0 Or workBytes<#NEON_INFLATE_WORK_BYTES Or sourceBytes<1 Or sourceBytes>#NEON_INFLATE_MAX_BYTES Or capacity<0 Or capacity>#NEON_INFLATE_MAX_BYTES
    ProcedureReturn #NEON_INFLATE_ERR_ARGUMENT
  EndIf
  If span=0 : span=1 : EndIf
  If NeonByteSpan(*s,SizeOf(NeonInflateState))=0 Or NeonByteSpan(work,#NEON_INFLATE_WORK_BYTES)=0 Or NeonByteSpan(source,sourceBytes)=0 Or NeonByteSpan(target,span)=0 : ProcedureReturn #NEON_INFLATE_ERR_ARGUMENT : EndIf
  If NeonByteOverlap(*s,SizeOf(NeonInflateState),work,#NEON_INFLATE_WORK_BYTES)<>0 Or NeonByteOverlap(*s,SizeOf(NeonInflateState),source,sourceBytes)<>0 Or NeonByteOverlap(*s,SizeOf(NeonInflateState),target,span)<>0 : ProcedureReturn #NEON_INFLATE_ERR_ARGUMENT : EndIf
  If NeonByteOverlap(work,#NEON_INFLATE_WORK_BYTES,source,sourceBytes)<>0 Or NeonByteOverlap(work,#NEON_INFLATE_WORK_BYTES,target,span)<>0 Or NeonByteOverlap(source,sourceBytes,target,span)<>0 : ProcedureReturn #NEON_INFLATE_ERR_ARGUMENT : EndIf
  For i=0 To SizeOf(NeonInflateState)-1 : PokeA(*s+i,0) : Next
  *s\source=source : *s\sourceBytes=sourceBytes : *s\target=target : *s\capacity=capacity : *s\work=work : *s\window=32768
  ProcedureReturn 0
EndProcedure
Procedure.i ndiBits(*s.NeonInflateState,n.i)
  Protected result.i
  If *s\error<>0 : ProcedureReturn 0 : EndIf
  While *s\bitCount<n
    If *s\offset>=*s\sourceBytes : *s\error=#NEON_INFLATE_ERR_TRUNCATED : ProcedureReturn 0 : EndIf
    *s\bits=*s\bits | ((PeekA(*s\source+*s\offset) & 255)<<*s\bitCount)
    *s\offset=*s\offset+1 : *s\bitCount=*s\bitCount+8
  Wend
  result=*s\bits & ((1<<n)-1) : *s\bits=*s\bits>>n : *s\bitCount=*s\bitCount-n
  ProcedureReturn result
EndProcedure
; A tree holds sixteen counts and at most288 canonical-order symbols.
; kind0 requires a complete code-length tree; kind1 allows a sole one-bit
; symbol; kind2 also allows an empty distance tree, until a match needs it.
Procedure.i ndiTree(*s.NeonInflateState,tree.i,lengths.i,n.i,kind.i)
  Protected i.i,b.i,left.i=1,used.i,max.i,offsets.i=*s\work+7616,k.i
  For i=0 To 15 : PokeI(tree+i*8,0) : PokeI(offsets+i*8,0) : Next
  For i=0 To n-1
    b=PeekA(lengths+i) & 255 : If b>15 : ProcedureReturn #NEON_INFLATE_ERR_FORMAT : EndIf
    If b>0 : PokeI(tree+b*8,PeekI(tree+b*8)+1) : used=used+1 : If b>max : max=b : EndIf : EndIf
  Next
  If used=0 : If kind=2 : ProcedureReturn 0 : Else : ProcedureReturn #NEON_INFLATE_ERR_FORMAT : EndIf : EndIf
  For i=1 To 15
    left=left*2-PeekI(tree+i*8) : If left<0 : ProcedureReturn #NEON_INFLATE_ERR_FORMAT : EndIf
  Next
  If left<>0 And (kind=0 Or used<>1 Or max<>1) : ProcedureReturn #NEON_INFLATE_ERR_FORMAT : EndIf
  For i=2 To 15 : PokeI(offsets+i*8,PeekI(offsets+(i-1)*8)+PeekI(tree+(i-1)*8)) : Next
  For i=0 To n-1
    b=PeekA(lengths+i) & 255
    If b>0 : k=PeekI(offsets+b*8) : PokeI(tree+128+k*8,i) : PokeI(offsets+b*8,k+1) : EndIf
  Next
  ProcedureReturn 0
EndProcedure
Procedure.i ndiSymbol(*s.NeonInflateState,tree.i)
  Protected code.i,first.i,index.i,n.i,count.i
  For n=1 To 15
    code=(code<<1) | ndiBits(*s,1)
    If *s\error<>0 : ProcedureReturn 0 : EndIf
    count=PeekI(tree+n*8)
    If code>=first And code<first+count : ProcedureReturn PeekI(tree+128+(index+code-first)*8) : EndIf
    index=index+count : first=(first+count)<<1
  Next
  *s\error=#NEON_INFLATE_ERR_FORMAT : ProcedureReturn 0
EndProcedure
Procedure.i ndiDynamic(*s.NeonInflateState)
  Protected nl.i,nd.i,nc.i,i.i,symbol.i,previous.i,repeatCount.i,rc.i,lens.i=*s\work+7296
  nl=257+ndiBits(*s,5) : nd=1+ndiBits(*s,5) : nc=4+ndiBits(*s,4)
  If *s\error<>0 : ProcedureReturn *s\error : EndIf
  If nl>286 : ProcedureReturn #NEON_INFLATE_ERR_FORMAT : EndIf
  For i=0 To 18 : PokeA(lens+i,0) : Next
  For i=0 To nc-1 : PokeA(lens+(PeekA(?ndiCodeOrder+i) & 255),ndiBits(*s,3)) : Next
  If *s\error<>0 : ProcedureReturn *s\error : EndIf
  rc=ndiTree(*s,*s\work+4864,lens,19,0) : If rc<>0 : ProcedureReturn rc : EndIf
  i=0
  While i<nl+nd
    symbol=ndiSymbol(*s,*s\work+4864) : If *s\error<>0 : ProcedureReturn *s\error : EndIf
    If symbol<16
      PokeA(lens+i,symbol) : previous=symbol : i=i+1
    Else
      If symbol=16
        If i=0 : ProcedureReturn #NEON_INFLATE_ERR_FORMAT : EndIf
        repeatCount=3+ndiBits(*s,2)
      ElseIf symbol=17
        previous=0 : repeatCount=3+ndiBits(*s,3)
      ElseIf symbol=18
        previous=0 : repeatCount=11+ndiBits(*s,7)
      Else
        ProcedureReturn #NEON_INFLATE_ERR_FORMAT
      EndIf
      If *s\error<>0 : ProcedureReturn *s\error : EndIf
      If repeatCount>nl+nd-i : ProcedureReturn #NEON_INFLATE_ERR_FORMAT : EndIf
      While repeatCount>0 : PokeA(lens+i,previous) : i=i+1 : repeatCount=repeatCount-1 : Wend
    EndIf
  Wend
  If (PeekA(lens+256) & 255)=0 : ProcedureReturn #NEON_INFLATE_ERR_FORMAT : EndIf
  rc=ndiTree(*s,*s\work,lens,nl,1) : If rc<>0 : ProcedureReturn rc : EndIf
  ProcedureReturn ndiTree(*s,*s\work+2432,lens+nl,nd,2)
EndProcedure
Procedure.i ndiFixed(*s.NeonInflateState)
  Protected i.i,rc.i,lens.i=*s\work+7296
  For i=0 To 143 : PokeA(lens+i,8) : Next
  For i=144 To 255 : PokeA(lens+i,9) : Next
  For i=256 To 279 : PokeA(lens+i,7) : Next
  For i=280 To 287 : PokeA(lens+i,8) : Next
  rc=ndiTree(*s,*s\work,lens,288,1) : If rc<>0 : ProcedureReturn rc : EndIf
  For i=0 To 31 : PokeA(lens+i,5) : Next
  ProcedureReturn ndiTree(*s,*s\work+2432,lens,32,2)
EndProcedure
Procedure.i ndiU16(p.i)
  ProcedureReturn (PeekA(p) & 255) | ((PeekA(p+1) & 255)<<8)
EndProcedure
Procedure.i ndiDecode(*s.NeonInflateState)
  Protected final.i,kind.i,n.i,other.i,i.i,rc.i,symbol.i,length.i,distance.i,extra.i
  Repeat
    final=ndiBits(*s,1) : kind=ndiBits(*s,2)
    If *s\error<>0 : ProcedureReturn *s\error : EndIf
    If kind=0
      *s\bits=0 : *s\bitCount=0
      n=ndiBits(*s,16) : other=ndiBits(*s,16)
      If *s\error<>0 : ProcedureReturn *s\error : EndIf
      If (n ! other)<>65535 : ProcedureReturn #NEON_INFLATE_ERR_FORMAT : EndIf
      If n>*s\sourceBytes-*s\offset : ProcedureReturn #NEON_INFLATE_ERR_TRUNCATED : EndIf
      If n>*s\capacity-*s\produced : ProcedureReturn #NEON_INFLATE_ERR_CAPACITY : EndIf
      For i=0 To n-1 : PokeA(*s\target+*s\produced+i,PeekA(*s\source+*s\offset+i)) : Next
      *s\produced=*s\produced+n : *s\offset=*s\offset+n
    Else
      If kind=1 : rc=ndiFixed(*s) : ElseIf kind=2 : rc=ndiDynamic(*s) : Else : ProcedureReturn #NEON_INFLATE_ERR_FORMAT : EndIf
      If rc<>0 : ProcedureReturn rc : EndIf
      Repeat
        symbol=ndiSymbol(*s,*s\work) : If *s\error<>0 : ProcedureReturn *s\error : EndIf
        If symbol<256
          If *s\produced>=*s\capacity : ProcedureReturn #NEON_INFLATE_ERR_CAPACITY : EndIf
          PokeA(*s\target+*s\produced,symbol) : *s\produced=*s\produced+1
        ElseIf symbol=256
          Break
        Else
          If symbol>285 : ProcedureReturn #NEON_INFLATE_ERR_FORMAT : EndIf
          symbol=symbol-257 : extra=PeekA(?ndiLengthExtra+symbol) & 255
          length=ndiU16(?ndiLengthBase+symbol*2)+ndiBits(*s,extra)
          symbol=ndiSymbol(*s,*s\work+2432) : If *s\error<>0 : ProcedureReturn *s\error : EndIf
          If symbol>29 : ProcedureReturn #NEON_INFLATE_ERR_FORMAT : EndIf
          extra=PeekA(?ndiDistanceExtra+symbol) & 255
          distance=ndiU16(?ndiDistanceBase+symbol*2)+ndiBits(*s,extra)
          If *s\error<>0 : ProcedureReturn *s\error : EndIf
          If distance>*s\produced Or distance>*s\window : ProcedureReturn #NEON_INFLATE_ERR_FORMAT : EndIf
          If length>*s\capacity-*s\produced : ProcedureReturn #NEON_INFLATE_ERR_CAPACITY : EndIf
          For i=0 To length-1
            PokeA(*s\target+*s\produced,PeekA(*s\target+*s\produced-distance)) : *s\produced=*s\produced+1
          Next
        EndIf
      ForEver
    EndIf
  Until final<>0
  If *s\offset<>*s\sourceBytes : ProcedureReturn #NEON_INFLATE_ERR_FORMAT : EndIf
  ProcedureReturn *s\produced
EndProcedure
Procedure.i NeonInflateRaw(*s.NeonInflateState,work.i,workBytes.i,source.i,sourceBytes.i,target.i,capacity.i)
  Protected rc.i=ndiStart(*s,work,workBytes,source,sourceBytes,target,capacity)
  If rc<>0 : ProcedureReturn rc : EndIf
  rc=ndiDecode(*s) : If rc<0 : *s\error=rc : EndIf
  ProcedureReturn rc
EndProcedure
Procedure.i NeonInflateZlib(*s.NeonInflateState,work.i,workBytes.i,source.i,sourceBytes.i,target.i,capacity.i)
  Protected rc.i,cmf.i,flags.i,adler.i,a.i=1,b.i,i.i
  rc=ndiStart(*s,work,workBytes,source,sourceBytes,target,capacity) : If rc<>0 : ProcedureReturn rc : EndIf
  If sourceBytes<6 : *s\error=#NEON_INFLATE_ERR_TRUNCATED : ProcedureReturn *s\error : EndIf
  cmf=PeekA(source) & 255 : flags=PeekA(source+1) & 255
  If (cmf & 15)<>8 Or (cmf>>4)>7 Or ((cmf<<8)+flags)%31<>0 : *s\error=#NEON_INFLATE_ERR_FORMAT : ProcedureReturn *s\error : EndIf
  If (flags & 32)<>0 : *s\error=#NEON_INFLATE_ERR_DICTIONARY : ProcedureReturn *s\error : EndIf
  *s\window=1<<((cmf>>4)+8) : *s\source=source+2 : *s\sourceBytes=sourceBytes-6
  rc=ndiDecode(*s)
  If rc<0 : *s\error=rc : ProcedureReturn rc : EndIf
  For i=0 To *s\produced-1
    a=a+(PeekA(target+i) & 255) : If a>=65521 : a=a-65521 : EndIf
    b=b+a : If b>=65521 : b=b-65521 : EndIf
  Next
  For i=sourceBytes-4 To sourceBytes-1 : adler=(adler<<8) | (PeekA(source+i) & 255) : Next
  If adler<>((b<<16) | a) : *s\error=#NEON_INFLATE_ERR_CHECKSUM : ProcedureReturn *s\error : EndIf
  ProcedureReturn *s\produced
EndProcedure
DataSection
ndiCodeOrder:
  Data.a 16,17,18,0,8,7,9,6,10,5,11,4,12,3,13,2,14,1,15
ndiLengthBase:
  Data.w 3,4,5,6,7,8,9,10,11,13,15,17,19,23,27,31,35,43,51,59,67,83,99,115,131,163,195,227,258
ndiLengthExtra:
  Data.a 0,0,0,0,0,0,0,0,1,1,1,1,2,2,2,2,3,3,3,3,4,4,4,4,5,5,5,5,0
ndiDistanceBase:
  Data.w 1,2,3,4,5,7,9,13,17,25,33,49,65,97,129,193,257,385,513,769,1025,1537,2049,3073,4097,6145,8193,12289,16385,24577
ndiDistanceExtra:
  Data.a 0,0,0,0,1,1,2,2,3,3,4,4,5,5,6,6,7,7,8,8,9,9,10,10,11,11,12,12,13,13
EndDataSection

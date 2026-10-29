; Incremental DEFLATE decoding, RFC 1951 sections 3.1 and 3.2.
; Independently implemented from format facts, no copied implementation.
; Caller owns context, 32768-byte history and 11008-byte table workspace aligned to eight bytes.
; No allocation, transport, board dependency or unbounded output buffering.
#WEB_INFLATE_ARGUMENT=-580
#WEB_INFLATE_FORMAT=-581
#WEB_INFLATE_DISTANCE=-582
#WEB_INFLATE_LIMIT=-583
#WEB_INFLATE_INCOMPLETE=-584
#WEB_INFLATE_WINDOW=32768
#WEB_INFLATE_WORK=11008
Structure WebInflate
  window.i
  work.i
  state.i
  error.i
  consumed.i
  written.i
  source.i
  sourceBytes.i
  destination.i
  capacity.i
  bits.i
  bitCount.i
  value.i
  needsInput.i
  windowLimit.i
  finalBlock.i
  position.i
  available.i
  total.i
  limit.i
  remaining.i
  distance.i
  extra.i
  literalCount.i
  distanceCount.i
  codeCount.i
  index.i
  repeatValue.i
  huffCode.i
  huffLength.i
EndStructure

Procedure.i wiFail(*s.WebInflate,code.i)
  *s\error=code : *s\state=-1 : ProcedureReturn code
EndProcedure

; Table: counts[16], first canonical codes[16], symbol offsets[16],
; symbols[288], all native integers. Lengths live at work+8064.
Procedure.i wiBuild(table.i,lengths.i,count.i,allowEmpty.i,allowSingle.i)
  Define i.i,n.i,left.i,code.i,offset.i,j.i,cursor.i,maximum.i
  For i=0 To 335 : PokeI(table+i*8,0) : Next
  For i=0 To count-1
    n=PeekI(lengths+i*8)
    If n<0 Or n>15 : ProcedureReturn -1 : EndIf
    If n>0 : PokeI(table+n*8,PeekI(table+n*8)+1) : If n>maximum : maximum=n : EndIf : EndIf
  Next
  If maximum=0
    If allowEmpty : ProcedureReturn 0 : Else : ProcedureReturn -1 : EndIf
  EndIf
  left=1
  For i=1 To 15
    left=left*2-PeekI(table+i*8)
    If left<0 : ProcedureReturn -1 : EndIf
    code=(code+PeekI(table+(i-1)*8))*2
    PokeI(table+128+i*8,code) : PokeI(table+256+i*8,offset)
    offset=offset+PeekI(table+i*8)
  Next
  If left>0 And (allowSingle=0 Or maximum<>1 Or offset<>1) : ProcedureReturn -1 : EndIf
  ; At most 288*15 visits; sorting needs no auxiliary allocation.
  cursor=0
  For n=1 To 15
    For j=0 To count-1
      If PeekI(lengths+j*8)=n : PokeI(table+384+cursor*8,j) : cursor=cursor+1 : EndIf
    Next
  Next
  ProcedureReturn 0
EndProcedure

Procedure.i wiBits(*s.WebInflate,count.i)
  While *s\bitCount<count
    If *s\consumed=*s\sourceBytes : *s\needsInput=1 : ProcedureReturn 0 : EndIf
    *s\bits=*s\bits | ((PeekA(*s\source+*s\consumed) & 255)<<*s\bitCount)
    *s\bitCount=*s\bitCount+8 : *s\consumed=*s\consumed+1
  Wend
  *s\value=*s\bits & ((1<<count)-1)
  *s\bits=*s\bits>>count : *s\bitCount=*s\bitCount-count
  ProcedureReturn 1
EndProcedure

; A suspended symbol retains its canonical prefix across input fragments.
; -1 means input needed; -2 means invalid coding; nonnegative is a symbol.
Procedure.i wiSymbol(*s.WebInflate,table.i)
  Define offset.i,count.i
  While *s\huffLength<15
    If wiBits(*s,1)=0 : ProcedureReturn -1 : EndIf
    *s\huffCode=*s\huffCode*2+*s\value : *s\huffLength=*s\huffLength+1
    offset=*s\huffCode-PeekI(table+128+*s\huffLength*8)
    count=PeekI(table+*s\huffLength*8)
    If offset>=0 And offset<count
      offset=PeekI(table+384+(PeekI(table+256+*s\huffLength*8)+offset)*8)
      *s\huffCode=0 : *s\huffLength=0 : ProcedureReturn offset
    EndIf
  Wend
  ProcedureReturn -2
EndProcedure

Procedure.i wiEmit(*s.WebInflate,byte.i)
  If *s\total>=*s\limit : ProcedureReturn wiFail(*s,#WEB_INFLATE_LIMIT) : EndIf
  PokeA(*s\destination+*s\written,byte) : *s\written=*s\written+1
  PokeA(*s\window+*s\position,byte) : *s\position=(*s\position+1) & 32767
  If *s\available<32768 : *s\available=*s\available+1 : EndIf
  *s\total=*s\total+1 : ProcedureReturn 0
EndProcedure

Procedure.i WebInflateInit(*s.WebInflate,window.i,windowCapacity.i,work.i,workCapacity.i,outputLimit.i)
  Define i.i
  If *s=0 : ProcedureReturn #WEB_INFLATE_ARGUMENT : EndIf
  For i=0 To SizeOf(WebInflate)-1 : PokeA(*s+i,0) : Next
  If window=0 Or work=0 Or (work & 7)<>0 Or windowCapacity<32768 Or workCapacity<#WEB_INFLATE_WORK Or outputLimit<0
    ProcedureReturn wiFail(*s,#WEB_INFLATE_ARGUMENT)
  EndIf
  *s\window=window : *s\work=work : *s\limit=outputLimit : *s\windowLimit=32768
  ProcedureReturn 0
EndProcedure

; 0 pending, 1 complete, negative failure. Always consume written bytes and
; advance input by consumed. It stops at the compressed stream boundary,
; leaving wrapper checksums or a following stream untouched. Zero output
; capacity applies backpressure. Each call performs at most 4096 state steps.
Procedure.i WebInflateFeed(*s.WebInflate,source.i,bytes.i,destination.i,capacity.i)
  Define steps.i,rc.i,n.i,i.i,lengths.i,kind.i,value.i,base.i
  If *s=0 : ProcedureReturn #WEB_INFLATE_ARGUMENT : EndIf
  *s\consumed=0 : *s\written=0 : *s\needsInput=0
  If *s\error<0 : ProcedureReturn *s\error : EndIf
  If *s\state=99 : ProcedureReturn 1 : EndIf
  If bytes<0 Or capacity<0 Or (bytes>0 And source=0) Or (capacity>0 And destination=0)
    ProcedureReturn wiFail(*s,#WEB_INFLATE_ARGUMENT)
  EndIf
  *s\source=source : *s\sourceBytes=bytes : *s\destination=destination : *s\capacity=capacity
  lengths=*s\work+8064
  While steps<4096
    steps=steps+1
    Select *s\state
      Case 0
        If wiBits(*s,3)=0 : ProcedureReturn 0 : EndIf
        *s\finalBlock=*s\value & 1 : kind=*s\value>>1
        If kind=3 : ProcedureReturn wiFail(*s,#WEB_INFLATE_FORMAT) : EndIf
        If kind=0
          *s\bits=0 : *s\bitCount=0 : *s\state=1
        ElseIf kind=1
          For i=0 To 287
            n=8 : If i>=144 And i<=255 : n=9 : ElseIf i>=256 And i<=279 : n=7 : EndIf
            PokeI(lengths+i*8,n)
          Next
          If wiBuild(*s\work,lengths,288,0,0)<0 : ProcedureReturn wiFail(*s,#WEB_INFLATE_FORMAT) : EndIf
          For i=0 To 31 : PokeI(lengths+i*8,5) : Next
          If wiBuild(*s\work+2688,lengths,32,0,0)<0 : ProcedureReturn wiFail(*s,#WEB_INFLATE_FORMAT) : EndIf
          *s\state=3
        Else
          *s\state=10
        EndIf
      Case 1
        If wiBits(*s,32)=0 : ProcedureReturn 0 : EndIf
        *s\remaining=*s\value & 65535
        If (*s\remaining ! 65535)<>((*s\value>>16) & 65535) : ProcedureReturn wiFail(*s,#WEB_INFLATE_FORMAT) : EndIf
        *s\state=2
      Case 2
        If *s\remaining=0
          If *s\finalBlock : *s\state=99 : ProcedureReturn 1 : EndIf
          *s\state=0
        Else
          If *s\written=capacity : ProcedureReturn 0 : EndIf
          If wiBits(*s,8)=0 : ProcedureReturn 0 : EndIf
          If wiEmit(*s,*s\value)<0 : ProcedureReturn *s\error : EndIf
          *s\remaining=*s\remaining-1
        EndIf
      Case 3
        If *s\written=capacity : ProcedureReturn 0 : EndIf
        n=wiSymbol(*s,*s\work)
        If n=-1 : ProcedureReturn 0 : EndIf
        If n<0 Or n>285 : ProcedureReturn wiFail(*s,#WEB_INFLATE_FORMAT) : EndIf
        If n<256
          If wiEmit(*s,n)<0 : ProcedureReturn *s\error : EndIf
        ElseIf n=256
          If *s\finalBlock : *s\state=99 : ProcedureReturn 1 : EndIf
          *s\state=0
        Else
          n=n-257
          *s\remaining=PeekW(?wiLengthBase+n*2) & 65535
          *s\extra=PeekA(?wiLengthExtra+n) : *s\state=4
        EndIf
      Case 4
        If wiBits(*s,*s\extra)=0 : ProcedureReturn 0 : EndIf
        *s\remaining=*s\remaining+*s\value : *s\state=5
      Case 5
        n=wiSymbol(*s,*s\work+2688)
        If n=-1 : ProcedureReturn 0 : EndIf
        If n<0 Or n>29 : ProcedureReturn wiFail(*s,#WEB_INFLATE_FORMAT) : EndIf
        *s\distance=PeekW(?wiDistanceBase+n*2) & 65535
        *s\extra=PeekA(?wiDistanceExtra+n) : *s\state=6
      Case 6
        If wiBits(*s,*s\extra)=0 : ProcedureReturn 0 : EndIf
        *s\distance=*s\distance+*s\value
        If *s\distance<1 Or *s\distance>*s\available Or *s\distance>*s\windowLimit : ProcedureReturn wiFail(*s,#WEB_INFLATE_DISTANCE) : EndIf
        *s\state=7
      Case 7
        If *s\written=capacity : ProcedureReturn 0 : EndIf
        n=PeekA(*s\window+((*s\position-*s\distance) & 32767)) & 255
        If wiEmit(*s,n)<0 : ProcedureReturn *s\error : EndIf
        *s\remaining=*s\remaining-1
        If *s\remaining=0 : *s\state=3 : EndIf
      Case 10
        If wiBits(*s,14)=0 : ProcedureReturn 0 : EndIf
        *s\literalCount=257+(*s\value & 31) : *s\distanceCount=1+((*s\value>>5) & 31) : *s\codeCount=4+((*s\value>>10) & 15)
        If *s\literalCount>286 : ProcedureReturn wiFail(*s,#WEB_INFLATE_FORMAT) : EndIf
        For i=0 To 318 : PokeI(lengths+i*8,0) : Next
        *s\index=0 : *s\state=11
      Case 11
        If wiBits(*s,3)=0 : ProcedureReturn 0 : EndIf
        i=PeekA(?wiCodeOrder+*s\index) : PokeI(lengths+i*8,*s\value)
        *s\index=*s\index+1
        If *s\index=*s\codeCount
          If wiBuild(*s\work+5376,lengths,19,0,0)<0 : ProcedureReturn wiFail(*s,#WEB_INFLATE_FORMAT) : EndIf
          *s\index=0 : *s\state=12
        EndIf
      Case 12
        If *s\index=*s\literalCount+*s\distanceCount
          If PeekI(lengths+256*8)=0 : ProcedureReturn wiFail(*s,#WEB_INFLATE_FORMAT) : EndIf
          If wiBuild(*s\work,lengths,*s\literalCount,0,1)<0 : ProcedureReturn wiFail(*s,#WEB_INFLATE_FORMAT) : EndIf
          If wiBuild(*s\work+2688,lengths+*s\literalCount*8,*s\distanceCount,1,1)<0 : ProcedureReturn wiFail(*s,#WEB_INFLATE_FORMAT) : EndIf
          *s\state=3
        Else
          n=wiSymbol(*s,*s\work+5376)
          If n=-1 : ProcedureReturn 0 : EndIf
          If n<0 Or n>18 : ProcedureReturn wiFail(*s,#WEB_INFLATE_FORMAT) : EndIf
          If n<=15
            PokeI(lengths+*s\index*8,n) : *s\index=*s\index+1
          Else
            *s\repeatValue=0
            If n=16
              If *s\index=0 : ProcedureReturn wiFail(*s,#WEB_INFLATE_FORMAT) : EndIf
              *s\repeatValue=PeekI(lengths+(*s\index-1)*8) : *s\remaining=3 : *s\extra=2
            ElseIf n=17
              *s\remaining=3 : *s\extra=3
            Else
              *s\remaining=11 : *s\extra=7
            EndIf
            *s\state=13
          EndIf
        EndIf
      Case 13
        If wiBits(*s,*s\extra)=0 : ProcedureReturn 0 : EndIf
        n=*s\remaining+*s\value
        If n>*s\literalCount+*s\distanceCount-*s\index : ProcedureReturn wiFail(*s,#WEB_INFLATE_FORMAT) : EndIf
        For i=0 To n-1 : PokeI(lengths+*s\index*8,*s\repeatValue) : *s\index=*s\index+1 : Next
        *s\state=12
      Default
        ProcedureReturn wiFail(*s,#WEB_INFLATE_FORMAT)
    EndSelect
  Wend
  ProcedureReturn 0
EndProcedure

Procedure.i WebInflateEof(*s.WebInflate)
  If *s=0 : ProcedureReturn #WEB_INFLATE_ARGUMENT : EndIf
  If *s\error<0 : ProcedureReturn *s\error : EndIf
  If *s\state=99 : ProcedureReturn 0 : EndIf
  ProcedureReturn wiFail(*s,#WEB_INFLATE_INCOMPLETE)
EndProcedure

DataSection
wiCodeOrder:
 Data.a 16,17,18,0,8,7,9,6,10,5,11,4,12,3,13,2,14,1,15
wiLengthBase:
 Data.w 3,4,5,6,7,8,9,10,11,13,15,17,19,23,27,31,35,43,51,59,67,83,99,115,131,163,195,227,258
wiLengthExtra:
 Data.a 0,0,0,0,0,0,0,0,1,1,1,1,2,2,2,2,3,3,3,3,4,4,4,4,5,5,5,5,0
wiDistanceBase:
 Data.w 1,2,3,4,5,7,9,13,17,25,33,49,65,97,129,193,257,385,513,769,1025,1537,2049,3073,4097,6145,8193,12289,16385,24577
wiDistanceExtra:
 Data.a 0,0,0,0,1,1,2,2,3,3,4,4,5,5,6,6,7,7,8,8,9,9,10,10,11,11,12,12,13,13
EndDataSection

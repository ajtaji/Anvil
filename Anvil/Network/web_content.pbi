; Streaming HTTP gzip / deflate content decoding.
; RFC 1950, 1951 and 1952 format facts; no copied implementation.
; Uses the existing shared CRC owner and bounded DEFLATE decoder.
XIncludeFile "Anvil/Network/web_inflate.pbi"
XIncludeFile "Anvil/Core/crc.pbi"
#WEB_CONTENT_IDENTITY=0
#WEB_CONTENT_GZIP=1
#WEB_CONTENT_DEFLATE=2
#WEB_CONTENT_HEADER=-590
#WEB_CONTENT_CHECKSUM=-591
#WEB_CONTENT_DICTIONARY=-592
#WEB_CONTENT_TRAILING=-593
#WEB_CONTENT_METADATA_LIMIT=65536
Structure WebContent
  decoder.WebInflate
  mode.i
  state.i
  error.i
  consumed.i
  written.i
  total.i
  limit.i
  members.i
  flags.i
  index.i
  remaining.i
  headerBytes.i
  headerCrc.i
  crc.i
  adlerA.i
  adlerB.i
  trailer.i
  trailerSize.i
  memberBytes.i
EndStructure

Procedure.i wzFail(*s.WebContent,code.i)
  *s\state=-1 : *s\error=code : ProcedureReturn code
EndProcedure

Procedure.i wzMember(*s.WebContent)
  Define rc.i
  rc=WebInflateInit(@*s\decoder,*s\decoder\window,32768,*s\decoder\work,#WEB_INFLATE_WORK,*s\limit-*s\total)
  If rc<0 : ProcedureReturn wzFail(*s,rc) : EndIf
  *s\flags=0 : *s\index=0 : *s\remaining=0 : *s\headerBytes=0
  *s\headerCrc=$FFFFFFFF : *s\crc=$FFFFFFFF : *s\adlerA=1 : *s\adlerB=0
  *s\trailer=0 : *s\trailerSize=0 : *s\memberBytes=0
  If *s\mode=#WEB_CONTENT_GZIP : *s\state=0 : Else : *s\state=10 : EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i WebContentInit(*s.WebContent,mode.i,window.i,windowCapacity.i,work.i,workCapacity.i,outputLimit.i)
  Define i.i,rc.i
  If *s=0 : ProcedureReturn #WEB_INFLATE_ARGUMENT : EndIf
  For i=0 To SizeOf(WebContent)-1 : PokeA(*s+i,0) : Next
  If mode<>#WEB_CONTENT_IDENTITY And mode<>#WEB_CONTENT_GZIP And mode<>#WEB_CONTENT_DEFLATE : ProcedureReturn wzFail(*s,#WEB_CONTENT_HEADER) : EndIf
  If outputLimit<0 : ProcedureReturn wzFail(*s,#WEB_INFLATE_ARGUMENT) : EndIf
  *s\mode=mode : *s\limit=outputLimit
  If mode=#WEB_CONTENT_IDENTITY : ProcedureReturn 0 : EndIf
  rc=WebInflateInit(@*s\decoder,window,windowCapacity,work,workCapacity,outputLimit)
  If rc<0 : ProcedureReturn wzFail(*s,rc) : EndIf
  ProcedureReturn wzMember(*s)
EndProcedure

; endInput means the supplied span is the last one. Repeat it while draining
; unconsumed input/output. Return 0 pending, 1 verified complete, negative error.
; A gzip member boundary is not EOF: concatenated members are decoded and each
; checksum/size is checked. zlib deflate has one stream and rejects trailing data.
; Decoded bytes precede checksum validation; do not commit a download until 1.
Procedure.i WebContentFeed(*s.WebContent,source.i,bytes.i,endInput.i,destination.i,capacity.i)
  Define steps.i,c.i,rc.i,i.i,n.i,at.i,header.i,value.i
  If *s=0 : ProcedureReturn #WEB_INFLATE_ARGUMENT : EndIf
  *s\consumed=0 : *s\written=0
  If *s\error<0 : ProcedureReturn *s\error : EndIf
  If bytes<0 Or capacity<0 Or (bytes>0 And source=0) Or (capacity>0 And destination=0)
    ProcedureReturn wzFail(*s,#WEB_INFLATE_ARGUMENT)
  EndIf
  If *s\state=99
    If bytes>0 : ProcedureReturn wzFail(*s,#WEB_CONTENT_TRAILING) : EndIf
    ProcedureReturn 1
  EndIf
  If *s\mode=#WEB_CONTENT_IDENTITY
    n=bytes : If n>capacity : n=capacity : EndIf
    If n>*s\limit-*s\total : ProcedureReturn wzFail(*s,#WEB_INFLATE_LIMIT) : EndIf
    For i=0 To n-1 : PokeA(destination+i,PeekA(source+i)) : Next
    *s\consumed=n : *s\written=n : *s\total=*s\total+n
    If endInput And n=bytes : *s\state=99 : ProcedureReturn 1 : EndIf
    ProcedureReturn 0
  EndIf
  While steps<4096
    steps=steps+1
    If *s\state=6
      at=*s\written
      rc=WebInflateFeed(@*s\decoder,source+*s\consumed,bytes-*s\consumed,destination+at,capacity-at)
      *s\consumed=*s\consumed+*s\decoder\consumed : n=*s\decoder\written
      If *s\mode=#WEB_CONTENT_GZIP
        *s\crc=Crc32Part(*s\crc,destination+at,n)
      Else
        For i=0 To n-1
          *s\adlerA=(*s\adlerA+(PeekA(destination+at+i) & 255)) % 65521
          *s\adlerB=(*s\adlerB+*s\adlerA) % 65521
        Next
      EndIf
      *s\written=at+n : *s\total=*s\total+n : *s\memberBytes=(*s\memberBytes+n) & $FFFFFFFF
      If rc<0 : ProcedureReturn wzFail(*s,rc) : EndIf
      If rc=0
        If endInput And *s\consumed=bytes And *s\decoder\needsInput : ProcedureReturn wzFail(*s,#WEB_INFLATE_INCOMPLETE) : EndIf
        ProcedureReturn 0
      EndIf
      *s\state=7 : *s\index=0 : *s\trailer=0 : *s\trailerSize=0
    ElseIf *s\state=8
      If *s\consumed=bytes
        If endInput : *s\state=99 : ProcedureReturn 1 : EndIf
        ProcedureReturn 0
      EndIf
      If *s\mode=#WEB_CONTENT_DEFLATE : ProcedureReturn wzFail(*s,#WEB_CONTENT_TRAILING) : EndIf
      rc=wzMember(*s) : If rc<0 : ProcedureReturn rc : EndIf
    ElseIf *s\state=1 And (*s\flags & 4)=0
      *s\state=3
    ElseIf *s\state=3 And (*s\flags & 8)=0
      *s\state=4
    ElseIf *s\state=4 And (*s\flags & 16)=0
      *s\state=5 : *s\index=0 : *s\trailer=0
    ElseIf *s\state=5 And (*s\flags & 2)=0
      *s\state=6
    Else
      If *s\consumed=bytes
        If endInput : ProcedureReturn wzFail(*s,#WEB_INFLATE_INCOMPLETE) : EndIf
        ProcedureReturn 0
      EndIf
      c=PeekA(source+*s\consumed) & 255
      If *s\state<5
        *s\headerBytes=*s\headerBytes+1
        If *s\headerBytes>#WEB_CONTENT_METADATA_LIMIT : ProcedureReturn wzFail(*s,#WEB_INFLATE_LIMIT) : EndIf
        *s\headerCrc=Crc32Part(*s\headerCrc,source+*s\consumed,1)
      EndIf
      *s\consumed=*s\consumed+1
      Select *s\state
        Case 0
          If (*s\index=0 And c<>31) Or (*s\index=1 And c<>139) Or (*s\index=2 And c<>8) : ProcedureReturn wzFail(*s,#WEB_CONTENT_HEADER) : EndIf
          If *s\index=3
            If (c & 224)<>0 : ProcedureReturn wzFail(*s,#WEB_CONTENT_HEADER) : EndIf
            *s\flags=c
          EndIf
          *s\index=*s\index+1
          If *s\index=10 : *s\state=1 : *s\index=0 : EndIf
        Case 1
          *s\remaining=*s\remaining | (c<<(*s\index*8)) : *s\index=*s\index+1
          If *s\index=2
            If *s\remaining=0 : *s\state=3 : Else : *s\state=2 : EndIf
          EndIf
        Case 2
          *s\remaining=*s\remaining-1
          If *s\remaining=0 : *s\state=3 : EndIf
        Case 3
          If c=0 : *s\state=4 : EndIf
        Case 4
          If c=0 : *s\state=5 : *s\index=0 : *s\trailer=0 : EndIf
        Case 5
          *s\trailer=*s\trailer | (c<<(*s\index*8)) : *s\index=*s\index+1
          If *s\index=2
            If *s\trailer<>((*s\headerCrc ! $FFFFFFFF) & 65535) : ProcedureReturn wzFail(*s,#WEB_CONTENT_CHECKSUM) : EndIf
            *s\state=6
          EndIf
        Case 7
          If *s\mode=#WEB_CONTENT_GZIP
            If *s\index<4 : *s\trailer=*s\trailer | (c<<(*s\index*8)) : Else : *s\trailerSize=*s\trailerSize | (c<<((*s\index-4)*8)) : EndIf
            *s\index=*s\index+1
            If *s\index=8
              If *s\trailer<>(*s\crc ! $FFFFFFFF) Or *s\trailerSize<>*s\memberBytes : ProcedureReturn wzFail(*s,#WEB_CONTENT_CHECKSUM) : EndIf
              *s\members=*s\members+1 : *s\state=8
            EndIf
          Else
            *s\trailer=(*s\trailer<<8) | c : *s\index=*s\index+1
            If *s\index=4
              If *s\trailer<>((*s\adlerB<<16) | *s\adlerA) : ProcedureReturn wzFail(*s,#WEB_CONTENT_CHECKSUM) : EndIf
              *s\members=1 : *s\state=8
            EndIf
          EndIf
        Case 10
          If *s\index=0
            If (c & 15)<>8 Or (c>>4)>7 : ProcedureReturn wzFail(*s,#WEB_CONTENT_HEADER) : EndIf
            *s\decoder\windowLimit=1<<((c>>4)+8) : *s\trailer=c<<8 : *s\index=1
          Else
            If ((*s\trailer | c) % 31)<>0 : ProcedureReturn wzFail(*s,#WEB_CONTENT_HEADER) : EndIf
            If (c & 32)<>0 : ProcedureReturn wzFail(*s,#WEB_CONTENT_DICTIONARY) : EndIf
            *s\state=6
          EndIf
        Default
          ProcedureReturn wzFail(*s,#WEB_CONTENT_HEADER)
      EndSelect
    EndIf
  Wend
  ProcedureReturn 0
EndProcedure

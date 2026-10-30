; SPDX-License-Identifier: MIT
; HTTP/2 encoding of the existing finalized WebRequest contract.
; Independently implemented from RFC 9113 8.2/8.3 and RFC 7541 5/6.
; https://www.rfc-editor.org/rfc/rfc9113.html
; No dynamic encoder table. Fields use never-indexed literals; names lowercase.
XIncludeFile "Anvil/Network/web_request.pbi"
#H2_REQUEST_ARGUMENT=-3260
#H2_REQUEST_SYNTAX=-3261
#H2_REQUEST_LIMIT=-3262
#H2_REQUEST_ORIGIN=-3263
Structure H2RequestHeaders
 output.i
 capacity.i
 length.i
 listSize.i
 listLimit.i
 error.i
 headOnly.i
EndStructure
Procedure h2qByte(*w.H2RequestHeaders,value.i)
 If *w\error<>0 : ProcedureReturn : EndIf
 If *w\length>=*w\capacity : *w\error=#H2_REQUEST_LIMIT : ProcedureReturn : EndIf
 PokeA(*w\output+*w\length,value) : *w\length=*w\length+1
EndProcedure
Procedure h2qString(*w.H2RequestHeaders,text.i,bytes.i,lower.i)
 Define n.i,i.i,ch.i
 n=bytes
 If n>=127
  h2qByte(*w,127) : n=n-127
  While n>=128 : h2qByte(*w,(n & 127)|128) : n=n>>7 : Wend
 EndIf
 h2qByte(*w,n)
 For i=0 To bytes-1
  ch=PeekA(text+i) : If lower<>0 : ch=webUrlLower(ch) : EndIf
  h2qByte(*w,ch)
 Next
EndProcedure
Procedure h2qField(*w.H2RequestHeaders,name.i,nameBytes.i,value.i,valueBytes.i,index.i)
 *w\listSize=*w\listSize+32+nameBytes+valueBytes
 If *w\listSize>*w\listLimit : *w\error=#H2_REQUEST_LIMIT : ProcedureReturn : EndIf
 ; Static indexes used here are 1,2,4,6, all representable with this prefix.
 h2qByte(*w,16|index)
 If index=0 : h2qString(*w,name,nameBytes,1) : EndIf
 h2qString(*w,value,valueBytes,0)
EndProcedure
Procedure.i h2qLine(source.i,at.i,bytes.i)
 While at+1<bytes
  If PeekA(source+at)=13 And PeekA(source+at+1)=10 : ProcedureReturn at : EndIf
  at=at+1
 Wend
 ProcedureReturn -1
EndProcedure
Procedure.i h2qOrigin(host.i,hostBytes.i,port.i,value.i,bytes.i)
 Define i.i,n.i,ch.i
 If bytes<hostBytes : ProcedureReturn 0 : EndIf
 For i=0 To hostBytes-1
  If webUrlLower(PeekA(host+i))<>webUrlLower(PeekA(value+i)) : ProcedureReturn 0 : EndIf
 Next
 If bytes=hostBytes : ProcedureReturn Bool(port=443) : EndIf
 If PeekA(value+hostBytes)<>58 Or bytes=hostBytes+1 : ProcedureReturn 0 : EndIf
 n=0
 For i=hostBytes+1 To bytes-1
  ch=PeekA(value+i) : If ch<48 Or ch>57 : ProcedureReturn 0 : EndIf
  n=n*10+ch-48 : If n>65535 : ProcedureReturn 0 : EndIf
 Next
 ProcedureReturn Bool(n=port)
EndProcedure
; Request is unchanged on success or refusal. Output must not alias headers.
Procedure.i H2RequestEncode(*r.WebRequest,host.i,hostBytes.i,port.i,output.i,capacity.i,listLimit.i,*w.H2RequestHeaders)
 Define i.i,p.i,bytes.i,line.i,methodBytes.i,path.i,pathBytes.i,first.i,at.i,last.i,colon.i,value.i,valueEnd.i,ch.i,authority.i,authorityBytes.i,skip.i
 If *w=0 : ProcedureReturn #H2_REQUEST_ARGUMENT : EndIf
 For i=0 To SizeOf(H2RequestHeaders)-1 : PokeA(*w+i,0) : Next
 If *r=0 Or host=0 Or hostBytes<1 Or hostBytes>255 Or port<1 Or port>65535 Or output=0 Or capacity<1 Or capacity>65536 Or listLimit<0 : ProcedureReturn #H2_REQUEST_ARGUMENT : EndIf
 If *r\state<>1 Or *r\error<>0 Or *r\offset<>0 Or *r\headers=0 Or *r\length<4 Or *r\length>*r\capacity Or *r\length>32768 Or *r\remaining< -1 : ProcedureReturn #H2_REQUEST_ARGUMENT : EndIf
 If *r\chunked<>Bool(*r\remaining= -1) : ProcedureReturn #H2_REQUEST_ARGUMENT : EndIf
 p=*r\headers : bytes=*r\length : line=h2qLine(p,0,bytes)
 If line<1 : ProcedureReturn #H2_REQUEST_SYNTAX : EndIf
 methodBytes=0
 While methodBytes<line And PeekA(p+methodBytes)<>32
  If wqToken(PeekA(p+methodBytes))=0 : ProcedureReturn #H2_REQUEST_SYNTAX : EndIf
  methodBytes=methodBytes+1
 Wend
 If methodBytes<1 Or methodBytes>32 Or wqEqual(p,methodBytes,"connect") : ProcedureReturn #H2_REQUEST_SYNTAX : EndIf
 path=methodBytes+1 : at=path
 While at<line And PeekA(p+at)<>32
  ch=PeekA(p+at) : If ch<=32 Or ch>=127 Or ch=35 : ProcedureReturn #H2_REQUEST_SYNTAX : EndIf
  at=at+1
 Wend
 pathBytes=at-path
 If pathBytes<1 Or pathBytes>=3072 Or PeekA(p+path)<>47 Or line-at<>9 : ProcedureReturn #H2_REQUEST_SYNTAX : EndIf
 If wqEqual(p+at+1,8,"http/1.1")=0 : ProcedureReturn #H2_REQUEST_SYNTAX : EndIf
 *w\headOnly=Bool(methodBytes=4 And PeekA(p)=72 And PeekA(p+1)=69 And PeekA(p+2)=65 And PeekA(p+3)=68)
 first=line+2 : at=first : authority=0
 ; Validate every field and identify Host before emitting any pseudo headers.
 While at+1<bytes
  last=h2qLine(p,at,bytes) : If last<0 : ProcedureReturn #H2_REQUEST_SYNTAX : EndIf
  If last=at : Break : EndIf
  colon=at
  While colon<last And PeekA(p+colon)<>58
   If wqToken(PeekA(p+colon))=0 : ProcedureReturn #H2_REQUEST_SYNTAX : EndIf
   colon=colon+1
  Wend
  If colon=at Or colon=last : ProcedureReturn #H2_REQUEST_SYNTAX : EndIf
  value=colon+1 : valueEnd=last
  While value<valueEnd And (PeekA(p+value)=32 Or PeekA(p+value)=9) : value=value+1 : Wend
  While valueEnd>value And (PeekA(p+valueEnd-1)=32 Or PeekA(p+valueEnd-1)=9) : valueEnd=valueEnd-1 : Wend
  For i=value To valueEnd-1
   ch=PeekA(p+i) : If (ch<32 And ch<>9) Or ch=127 : ProcedureReturn #H2_REQUEST_SYNTAX : EndIf
  Next
  If wqEqual(p+at,colon-at,"host")
   If authority<>0 : ProcedureReturn #H2_REQUEST_SYNTAX : EndIf
   authority=p+value : authorityBytes=valueEnd-value
  EndIf
  If wqEqual(p+at,colon-at,"connection") And wqEqual(p+value,valueEnd-value,"close")=0 : ProcedureReturn #H2_REQUEST_SYNTAX : EndIf
  If wqEqual(p+at,colon-at,"transfer-encoding")
   If *r\chunked=0 Or wqEqual(p+value,valueEnd-value,"chunked")=0 : ProcedureReturn #H2_REQUEST_SYNTAX : EndIf
  EndIf
  If wqEqual(p+at,colon-at,"te") And wqEqual(p+value,valueEnd-value,"trailers")=0 : ProcedureReturn #H2_REQUEST_SYNTAX : EndIf
  If wqEqual(p+at,colon-at,"upgrade") : ProcedureReturn #H2_REQUEST_SYNTAX : EndIf
  at=last+2
 Wend
 If at+2<>bytes Or authority=0 : ProcedureReturn #H2_REQUEST_SYNTAX : EndIf
 If h2qOrigin(host,hostBytes,port,authority,authorityBytes)=0 : ProcedureReturn #H2_REQUEST_ORIGIN : EndIf
 *w\output=output : *w\capacity=capacity : *w\listLimit=listLimit
 h2qField(*w,0,7,p,methodBytes,2)
 h2qField(*w,0,7,"https",5,6)
 h2qField(*w,0,5,p+path,pathBytes,4)
 h2qField(*w,0,10,authority,authorityBytes,1)
 at=first
 While at+1<bytes And *w\error=0
  last=h2qLine(p,at,bytes) : If last=at : Break : EndIf
  colon=at : While PeekA(p+colon)<>58 : colon=colon+1 : Wend
  value=colon+1 : valueEnd=last
  While value<valueEnd And (PeekA(p+value)=32 Or PeekA(p+value)=9) : value=value+1 : Wend
  While valueEnd>value And (PeekA(p+valueEnd-1)=32 Or PeekA(p+valueEnd-1)=9) : valueEnd=valueEnd-1 : Wend
  skip=Bool(wqEqual(p+at,colon-at,"host") Or wqEqual(p+at,colon-at,"connection") Or wqEqual(p+at,colon-at,"transfer-encoding") Or wqEqual(p+at,colon-at,"proxy-connection") Or wqEqual(p+at,colon-at,"keep-alive"))
  If skip=0 : h2qField(*w,p+at,colon-at,p+value,valueEnd-value,0) : EndIf
  at=last+2
 Wend
 ProcedureReturn *w\error
EndProcedure

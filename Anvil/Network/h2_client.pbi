; SPDX-License-Identifier: MIT
; Incremental HTTP/2 HTTPS connections, independently implemented from
; RFC 9113 sections 3-8: https://www.rfc-editor.org/rfc/rfc9113.html
; Caller pumps network service and consumes events; no waits or polling loops.
; Caller buffers: tx/rx 16384 each, compressed headers 65536, dynamic table4096,
; field workspace8192, and streamCount*SizeOf(H2Stream) bytes. Keep disjoint.
; WebRequest supplies methods/fields and fixed or unknown body lengths.
XIncludeFile "Anvil/Network/web_url.pbi"
XIncludeFile "Anvil/Network/web_transport.pbi"
XIncludeFile "Anvil/Network/h2_frame.pbi"
XIncludeFile "Anvil/Network/hpack_decode.pbi"
XIncludeFile "Anvil/Network/h2_request.pbi"
#H2_ARGUMENT=-3250
#H2_STATE=-3251
#H2_PROTOCOL=-3252
#H2_FLOW=-3253
#H2_LIMIT=-3254
#H2_TIMEOUT=-3255
#H2_CANCELLED=-3256
#H2_CLOSED=-3257
#H2_BUSY=-110
#H2_FIELD=1
#H2_DATA=2
#H2_END=3
#H2_RESET=4
#H2_GOAWAY=5
Structure H2Stream
 id.i
 state.i
 status.i
 received.q
 contentLength.q
 window.i
 sendWindow.i
 resetCode.i
 uploadRemaining.i
 localClosed.i
 headOnly.i
 request.i
EndStructure
Structure H2Buffers
 tx.i
 rx.i
 block.i
 dynamic.i
 field.i
 streams.i
 streamCount.i
EndStructure
Structure H2Client
 allowHttp1.i
 sent.i
 received.i
 connection.WebConnection
 buffers.H2Buffers
 frame.H2FrameHeader
 decoder.HpackDecoder
 state.i
 error.i
 started.i
 timeout.i
 hostLength.i
 txLength.i
 txOffset.i
 requestHeaderBytes.i
 requestHeaderOffset.i
 requestHeaderStream.i
 requestHeaderEnd.i
 payloadUsed.i
 settingsSeen.i
 settingsPending.i
 peerStreams.i
 peerHeaderLimit.i
 activeStreams.i
 nextStream.i
 window.i
 sendWindow.i
 peerInitialWindow.i
 goaway.i
 lastPeerStream.i
 peerError.i
 continuation.i
 blockUsed.i
 blockStream.i
 blockEnd.i
 blockStatus.i
 blockRegular.i
 blockTrailers.i
 blockDiscard.i
 decoding.i
 event.i
 eventStream.i
 data.i
 dataBytes.i
 credit.i
 finishStream.i
 name.i
 nameLength.i
 value.i
 valueLength.i
 sensitive.i
EndStructure
Procedure.i h2cFail(*c.H2Client,error.i)
 If *c\state>0 : WebTransportClose(@*c\connection) : EndIf
 *c\state=-1 : *c\error=error : *c\event=0
 ProcedureReturn error
EndProcedure
Procedure.i h2cStream(*c.H2Client,id.i)
 Define i.i,*s.H2Stream
 For i=0 To *c\buffers\streamCount-1
  *s=*c\buffers\streams+i*SizeOf(H2Stream)
  If *s\state<>0 And *s\id=id : ProcedureReturn *s : EndIf
 Next
 ProcedureReturn 0
EndProcedure
Procedure.i h2cEqual(p.i,bytes.i,text.i)
 Define i.i
 For i=0 To bytes-1
  If PeekA(text+i)=0 Or PeekA(p+i)<>PeekA(text+i) : ProcedureReturn 0 : EndIf
 Next
 If PeekA(text+bytes)<>0 : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i h2cField(*c.H2Client)
 Define *d.HpackDecoder,*s.H2Stream,i.i,ch.i,n.q
 *d=@*c\decoder : *s=*c\blockStream
 If *d\nameLength=0 : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
 For i=0 To *d\nameLength-1
  ch=PeekA(*d\name+i)
  If ch=58 And i=0
  Else
   If (ch<97 Or ch>122) And (ch<48 Or ch>57)
    If ch<>33 And ch<>35 And ch<>36 And ch<>37 And ch<>38 And ch<>39 And ch<>42 And ch<>43 And ch<>45 And ch<>46 And ch<>94 And ch<>95 And ch<>96 And ch<>124 And ch<>126 : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
   EndIf
  EndIf
 Next
 For i=0 To *d\valueLength-1
  ch=PeekA(*d\value+i)
  If (ch<32 And ch<>9) Or ch=127 : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
  If (i=0 Or i=*d\valueLength-1) And (ch=32 Or ch=9) : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
 Next
 If PeekA(*d\name)=58
  If *c\blockTrailers<>0 Or *c\blockRegular<>0 Or *c\blockStatus<>0 Or h2cEqual(*d\name,*d\nameLength,":status")=0 Or *d\valueLength<>3 : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
  n=0
  For i=0 To 2
   ch=PeekA(*d\value+i) : If ch<48 Or ch>57 : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
   n=n*10+ch-48
  Next
  If n<100 Or n>599 Or n=101 : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
  *c\blockStatus=n
 Else
  *c\blockRegular=1
  If h2cEqual(*d\name,*d\nameLength,"connection") Or h2cEqual(*d\name,*d\nameLength,"proxy-connection") Or h2cEqual(*d\name,*d\nameLength,"keep-alive") Or h2cEqual(*d\name,*d\nameLength,"transfer-encoding") Or h2cEqual(*d\name,*d\nameLength,"upgrade") Or h2cEqual(*d\name,*d\nameLength,"te") : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
  If h2cEqual(*d\name,*d\nameLength,"content-length")
   If *c\blockTrailers<>0 Or *c\blockStatus<200 Or *c\blockStatus=204 Or *d\valueLength=0 : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
   n=0
   For i=0 To *d\valueLength-1
    ch=PeekA(*d\value+i) : If ch<48 Or ch>57 : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
    If n>($7FFFFFFFFFFFFFFF-(ch-48))/10 : ProcedureReturn h2cFail(*c,#H2_LIMIT) : EndIf
    n=n*10+ch-48
   Next
   If *s\contentLength>=0 And *s\contentLength<>n : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
   *s\contentLength=n
  EndIf
 EndIf
 *c\name=*d\name : *c\nameLength=*d\nameLength : *c\value=*d\value : *c\valueLength=*d\valueLength : *c\sensitive=*d\sensitive
 *c\event=#H2_FIELD : *c\eventStream=*s\id
 ProcedureReturn *c\event
EndProcedure
Procedure.i h2cFinish(*c.H2Client,*s.H2Stream)
 Define *request.WebRequest
 If *s\state<>1 Or *s\status<200 : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
 If *s\headOnly=0 And *s\status<>304 And *s\contentLength>=0 And *s\received<>*s\contentLength : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
 If *s\localClosed=0
  ; A final response can arrive before the upload finishes. Preserve the
  ; response and close only the unfinished request side with NO_ERROR.
  H2FrameWrite(*c\buffers\tx,16384,4,3,0,*s\id)
  NetWriteBE32(*c\buffers\tx+9,0) : *c\txLength=13 : *c\txOffset=0
  *s\localClosed=1
 EndIf
 *request=*s\request : If *request<>0 : *request\state=2 : EndIf
 *s\state=2 : *c\activeStreams=*c\activeStreams-1
 *c\event=#H2_END : *c\eventStream=*s\id : *c\finishStream=0
 ProcedureReturn *c\event
EndProcedure
Procedure.i h2cStartMode(*c.H2Client,*url.WebUrl,*buffers.H2Buffers,now.i,timeout.i,allowHttp1.i)
 Define i.i,rc.i,bytes.i,protocol.i
 If *c=0 : ProcedureReturn #H2_ARGUMENT : EndIf
 For i=0 To SizeOf(H2Client)-1 : PokeA(*c+i,0) : Next
 If *url=0 Or *buffers=0 : ProcedureReturn h2cFail(*c,#H2_ARGUMENT) : EndIf
 If *url\secure<>1 Or *url\host=0 Or *url\hostLength<1 Or *url\hostLength>255 Or timeout<1 Or timeout>$7FFFFFFF : ProcedureReturn h2cFail(*c,#H2_ARGUMENT) : EndIf
 If *buffers\tx=0 Or *buffers\rx=0 Or *buffers\block=0 Or *buffers\dynamic=0 Or *buffers\field=0 Or *buffers\streams=0 Or *buffers\streamCount<1 Or *buffers\streamCount>16 : ProcedureReturn h2cFail(*c,#H2_ARGUMENT) : EndIf
 For i=0 To SizeOf(H2Buffers)-1 : PokeA(@*c\buffers+i,PeekA(*buffers+i)) : Next
 For i=0 To *buffers\streamCount*SizeOf(H2Stream)-1 : PokeA(*buffers\streams+i,0) : Next
 *c\connection\secure=1 : *c\connection\host=*url\host : *c\connection\port=*url\port : *c\hostLength=*url\hostLength
 *c\started=now : *c\timeout=timeout : *c\nextStream=1 : *c\window=65535 : *c\sendWindow=65535 : *c\peerInitialWindow=65535
 *c\peerStreams=$7FFFFFFF : *c\peerHeaderLimit=$7FFFFFFF : *c\lastPeerStream=$7FFFFFFF
 rc=HpackInit(@*c\decoder,*buffers\dynamic,4096) : If rc<>0 : ProcedureReturn h2cFail(*c,rc) : EndIf
 H2FrameInit(@*c\frame,16384)
 PokeA(*buffers\tx,2) : PokeA(*buffers\tx+1,104) : PokeA(*buffers\tx+2,50)
 bytes=3 : *c\allowHttp1=allowHttp1
 If allowHttp1<>0
  PokeA(*buffers\tx+3,8) : protocol="http/1.1"
  For i=0 To 7 : PokeA(*buffers\tx+4+i,PeekA(protocol+i)) : Next
  bytes=12
 EndIf
 *c\state=1 : rc=WebTransportOpenAlpn(@*c\connection,*buffers\tx,bytes)
 If rc<>0 : ProcedureReturn h2cFail(*c,rc) : EndIf
 ProcedureReturn 0
EndProcedure
; Existing explicit HTTP/2 callers still require an h2 selection.
Procedure.i H2ClientStart(*c.H2Client,*url.WebUrl,*buffers.H2Buffers,now.i,timeout.i)
 ProcedureReturn h2cStartMode(*c,*url,*buffers,now,timeout,0)
EndProcedure
; Offers h2 followed by http/1.1. State 4 means a verified HTTP/1 connection
; is ready for TakeHttp1; no HTTP/2 preface or request has been transmitted.
Procedure.i H2ClientStartNegotiated(*c.H2Client,*url.WebUrl,*buffers.H2Buffers,now.i,timeout.i)
 ProcedureReturn h2cStartMode(*c,*url,*buffers,now,timeout,1)
EndProcedure
; Move ownership into a fresh/closed, disjoint WebConnection. Failure preserves
; ownership. Close on this context after a successful take cannot close the moved handle.
Procedure.i H2ClientTakeHttp1(*c.H2Client,*destination.WebConnection)
 Define i.i
 If *c=0 Or *destination=0 : ProcedureReturn #H2_ARGUMENT : EndIf
 If *destination=@*c\connection : ProcedureReturn #H2_ARGUMENT : EndIf
 If *destination\handle<>0 : ProcedureReturn #H2_STATE : EndIf
 If *c\state<>4 : ProcedureReturn #H2_STATE : EndIf
 For i=0 To SizeOf(WebConnection)-1
  PokeA(*destination+i,PeekA(@*c\connection+i)) : PokeA(@*c\connection+i,0)
 Next
 *c\state=0
 ProcedureReturn 0
EndProcedure
Procedure.i H2ClientCancel(*c.H2Client)
 If *c=0 : ProcedureReturn #H2_ARGUMENT : EndIf
 ProcedureReturn h2cFail(*c,#H2_CANCELLED)
EndProcedure
Procedure H2ClientClose(*c.H2Client)
 If *c=0 : ProcedureReturn : EndIf
 If *c\state>0 : WebTransportClose(@*c\connection) : EndIf
 *c\state=0 : *c\event=0
EndProcedure
Procedure h2cLiteral(*c.H2Client,index.i,text.i,bytes.i)
 Define n.i,i.i
 PokeA(*c\buffers\tx+*c\txLength,index) : *c\txLength=*c\txLength+1
 n=bytes
 If n>=127
  PokeA(*c\buffers\tx+*c\txLength,127) : *c\txLength=*c\txLength+1 : n=n-127
  While n>=128
   PokeA(*c\buffers\tx+*c\txLength,(n & 127)|128) : *c\txLength=*c\txLength+1 : n=n>>7
  Wend
 EndIf
 PokeA(*c\buffers\tx+*c\txLength,n) : *c\txLength=*c\txLength+1
 For i=0 To bytes-1 : PokeA(*c\buffers\tx+*c\txLength+i,PeekA(text+i)) : Next
 *c\txLength=*c\txLength+bytes
EndProcedure
; Positive stream ID or BUSY; buffers are copied before returning. Same origin.
Procedure.i H2ClientGet(*c.H2Client,target.i,bytes.i)
 Define *s.H2Stream,i.i,p.i,n.i,digits.i,divisor.i,port.i,ch.i
 If *c=0 : ProcedureReturn #H2_ARGUMENT : EndIf
 If *c\state=-1 : ProcedureReturn *c\error : EndIf
 If *c\state<>3 Or *c\goaway<>0 : ProcedureReturn #H2_STATE : EndIf
 If *c\event<>0 Or *c\txLength<>0 Or *c\requestHeaderBytes<>0 Or *c\activeStreams>=*c\peerStreams : ProcedureReturn #H2_BUSY : EndIf
 If target=0 Or bytes<1 Or bytes>3072 Or PeekA(target)<>47 : ProcedureReturn #H2_ARGUMENT : EndIf
 For i=0 To bytes-1
  ch=PeekA(target+i) : If ch<=32 Or ch=127 Or ch=35 : ProcedureReturn #H2_ARGUMENT : EndIf
 Next
 If *c\nextStream>$7FFFFFFF : ProcedureReturn #H2_STATE : EndIf
 *s=0
 For i=0 To *c\buffers\streamCount-1
  p=*c\buffers\streams+i*SizeOf(H2Stream)
  If PeekI(p+OffsetOf(H2Stream\state))=0 : *s=p : Break : EndIf
 Next
 If *s=0 : ProcedureReturn #H2_BUSY : EndIf
 p=*c\buffers\tx+8192 : n=*c\hostLength
 For i=0 To n-1 : PokeA(p+i,PeekA(*c\connection\host+i)) : Next
 port=*c\connection\port
 If port<>443
  PokeA(p+n,58) : n=n+1 : divisor=10000
  While divisor>1 And port<divisor : divisor=divisor/10 : Wend
  While divisor>0
   PokeA(p+n,48+port/divisor) : n=n+1 : port=port % divisor : divisor=divisor/10
  Wend
 EndIf
 If 128+7+3+7+5+5+bytes+10+n>*c\peerHeaderLimit : ProcedureReturn #H2_LIMIT : EndIf
 *c\txLength=9 : *c\txOffset=0
 PokeA(*c\buffers\tx+9,$82) : PokeA(*c\buffers\tx+10,$87) : *c\txLength=11
 h2cLiteral(*c,4,target,bytes) : h2cLiteral(*c,1,p,n)
 For i=0 To SizeOf(H2Stream)-1 : PokeA(*s+i,0) : Next
 *s\id=*c\nextStream : *c\nextStream=*c\nextStream+2 : *s\state=1 : *s\localClosed=1 : *s\contentLength=-1 : *s\window=65535 : *s\sendWindow=*c\peerInitialWindow
 *c\activeStreams=*c\activeStreams+1
 H2FrameWrite(*c\buffers\tx,16384,*c\txLength-9,1,5,*s\id)
 ProcedureReturn *s\id
EndProcedure

Procedure h2cRequestHeaderFrame(*c.H2Client)
 Define n.i,kind.i,flags.i,i.i
 n=*c\requestHeaderBytes-*c\requestHeaderOffset
 If n>16375 : n=16375 : EndIf
 kind=9 : flags=0
 If *c\requestHeaderOffset=0 : kind=1 : flags=*c\requestHeaderEnd : EndIf
 If *c\requestHeaderOffset+n=*c\requestHeaderBytes : flags=flags|4 : EndIf
 H2FrameWrite(*c\buffers\tx,16384,n,kind,flags,*c\requestHeaderStream)
 For i=0 To n-1 : PokeA(*c\buffers\tx+9+i,PeekA(*c\buffers\block+*c\requestHeaderOffset+i)) : Next
 *c\requestHeaderOffset=*c\requestHeaderOffset+n
 *c\txLength=9+n : *c\txOffset=0
 If *c\requestHeaderOffset=*c\requestHeaderBytes : *c\requestHeaderBytes=0 : EndIf
EndProcedure
; Same finalized WebRequest used by HTTP/1. Headers are copied before return.
; It remains caller-owned for upload counters until the stream is closed.
Procedure.i H2ClientRequest(*c.H2Client,*request.WebRequest)
 Define encoded.H2RequestHeaders,*s.H2Stream,i.i,p.i,rc.i
 If *c=0 Or *request=0 : ProcedureReturn #H2_ARGUMENT : EndIf
 If *c\state=-1 : ProcedureReturn *c\error : EndIf
 If *c\state<>3 Or *c\goaway<>0 : ProcedureReturn #H2_STATE : EndIf
 If *c\event<>0 Or *c\txLength<>0 Or *c\requestHeaderBytes<>0 Or *c\decoding<>0 Or *c\continuation<>0 Or *c\activeStreams>=*c\peerStreams : ProcedureReturn #H2_BUSY : EndIf
 If *c\nextStream>$7FFFFFFF : ProcedureReturn #H2_STATE : EndIf
 *s=0
 For i=0 To *c\buffers\streamCount-1
  p=*c\buffers\streams+i*SizeOf(H2Stream)
  If PeekI(p+OffsetOf(H2Stream\state))=0 : *s=p : Break : EndIf
 Next
 If *s=0 : ProcedureReturn #H2_BUSY : EndIf
 rc=H2RequestEncode(*request,*c\connection\host,*c\hostLength,*c\connection\port,*c\buffers\block,65536,*c\peerHeaderLimit,@encoded)
 If rc<>0 : ProcedureReturn rc : EndIf
 For i=0 To SizeOf(H2Stream)-1 : PokeA(*s+i,0) : Next
 *s\id=*c\nextStream : *c\nextStream=*c\nextStream+2 : *s\state=1
 *s\contentLength=-1 : *s\window=65535 : *s\sendWindow=*c\peerInitialWindow
 *s\uploadRemaining=*request\remaining : *s\localClosed=Bool(*request\remaining=0)
 *s\headOnly=encoded\headOnly : *s\request=*request
 *request\offset=*request\length : If *s\localClosed<>0 : *request\state=2 : EndIf
 *c\activeStreams=*c\activeStreams+1
 *c\requestHeaderBytes=encoded\length : *c\requestHeaderOffset=0
 *c\requestHeaderStream=*s\id : *c\requestHeaderEnd=*s\localClosed
 h2cRequestHeaderFrame(*c)
 ProcedureReturn *s\id
EndProcedure
; Returns copied body bytes, BUSY, or an argument/state error. END with zero
; bytes is permitted even with zero send credit. Unknown lengths use DATA,
; never HTTP/1 chunk framing. Retain unconsumed input and repeat endBody.
Procedure.i H2ClientData(*c.H2Client,id.i,body.i,bytes.i,endBody.i)
 Define *s.H2Stream,*request.WebRequest,n.i,i.i,ending.i
 If *c=0 Or bytes<0 Or (bytes>0 And body=0) Or (endBody<>0 And endBody<>1) : ProcedureReturn #H2_ARGUMENT : EndIf
 If *c\state=-1 : ProcedureReturn *c\error : EndIf
 If *c\state<>3 : ProcedureReturn #H2_STATE : EndIf
 *s=h2cStream(*c,id) : If *s=0 : ProcedureReturn #H2_STATE : EndIf
 If *s\state<>1 Or *s\localClosed<>0 : ProcedureReturn #H2_STATE : EndIf
 If *c\event<>0 Or *c\txLength<>0 Or *c\requestHeaderBytes<>0 Or *s\status>=200 : ProcedureReturn #H2_BUSY : EndIf
 If *s\uploadRemaining>=0
  If bytes>*s\uploadRemaining : ProcedureReturn #H2_ARGUMENT : EndIf
  If endBody<>0 And bytes<>*s\uploadRemaining : ProcedureReturn #H2_ARGUMENT : EndIf
 EndIf
 If bytes=0 And endBody=0 : ProcedureReturn 0 : EndIf
 n=bytes : If n>16375 : n=16375 : EndIf
 If n>*c\sendWindow : n=*c\sendWindow : EndIf
 If n>*s\sendWindow : n=*s\sendWindow : EndIf
 If bytes>0 And n<=0 : ProcedureReturn #H2_BUSY : EndIf
 If bytes=0 : n=0 : EndIf
 ending=Bool(endBody<>0 And n=bytes)
 If *s\uploadRemaining>=0
  *s\uploadRemaining=*s\uploadRemaining-n
  If *s\uploadRemaining=0 : ending=1 : EndIf
 EndIf
 H2FrameWrite(*c\buffers\tx,16384,n,0,ending,id)
 For i=0 To n-1 : PokeA(*c\buffers\tx+9+i,PeekA(body+i)) : Next
 *c\txLength=9+n : *c\txOffset=0
 *c\sendWindow=*c\sendWindow-n : *s\sendWindow=*s\sendWindow-n
 If ending<>0 : *s\localClosed=1 : EndIf
 *request=*s\request
 If *request<>0
  *request\consumed=n : *request\remaining=*s\uploadRemaining
  If ending<>0 : *request\state=2 : EndIf
 EndIf
 ProcedureReturn n
EndProcedure
 ; Cancellation queues RST_STREAM(CANCEL); consume the RESET event normally.
; BUSY preserves all state: finish pending output/events, then retry.
Procedure.i H2ClientCancelStream(*c.H2Client,id.i)
 Define *s.H2Stream
 If *c=0 : ProcedureReturn #H2_ARGUMENT : EndIf
 If *c\state=-1 : ProcedureReturn *c\error : EndIf
 If *c\state<>3 : ProcedureReturn #H2_STATE : EndIf
 *s=h2cStream(*c,id) : If *s=0 : ProcedureReturn #H2_STATE : EndIf
 If *s\state<>1 : ProcedureReturn #H2_STATE : EndIf
 If *c\txLength<>0 Or *c\requestHeaderBytes<>0 Or *c\event<>0 Or *c\finishStream=*s : ProcedureReturn #H2_BUSY : EndIf
 H2FrameWrite(*c\buffers\tx,16384,4,3,0,id)
 NetWriteBE32(*c\buffers\tx+9,8) : *c\txLength=13 : *c\txOffset=0
 *s\state=3 : *s\resetCode=8 : *c\activeStreams=*c\activeStreams-1
 If *c\blockStream=*s And (*c\decoding<>0 Or *c\continuation<>0)
  *c\blockDiscard=1 : *c\blockStream=0
 EndIf
 *c\event=#H2_RESET : *c\eventStream=id
 ProcedureReturn 0
EndProcedure
Procedure.i H2ClientRelease(*c.H2Client,id.i)
 Define *s.H2Stream
 If *c=0 : ProcedureReturn #H2_ARGUMENT : EndIf
 *s=h2cStream(*c,id)
 If *s=0 : ProcedureReturn #H2_STATE : EndIf
 If *s\state=1 Or (*c\event<>0 And *c\eventStream=id) : ProcedureReturn #H2_BUSY : EndIf
 *s\state=0 : ProcedureReturn 0
EndProcedure
; Events remain stable until consumed. Body credit includes DATA padding.
Procedure.i H2ClientConsume(*c.H2Client)
 Define *s.H2Stream
 If *c=0 : ProcedureReturn #H2_ARGUMENT : EndIf
 If *c\state=-1 : ProcedureReturn *c\error : EndIf
 If *c\event=#H2_DATA And *c\credit>0
  If *c\txLength<>0 : ProcedureReturn #H2_BUSY : EndIf
  *s=h2cStream(*c,*c\eventStream) : If *s=0 : ProcedureReturn h2cFail(*c,#H2_STATE) : EndIf
  H2FrameWrite(*c\buffers\tx,16384,4,8,0,0) : NetWriteBE32(*c\buffers\tx+9,*c\credit)
  *c\txLength=13 : *c\txOffset=0 : *c\window=*c\window+*c\credit
  If *c\finishStream=0
   H2FrameWrite(*c\buffers\tx+13,16371,4,8,0,*s\id) : NetWriteBE32(*c\buffers\tx+22,*c\credit)
   *c\txLength=26 : *s\window=*s\window+*c\credit
  EndIf
 EndIf
 *c\event=0 : *c\credit=0 : ProcedureReturn 0
EndProcedure
Procedure.i h2cDecode(*c.H2Client)
 Define rc.i,*s.H2Stream
 rc=HpackNext(@*c\decoder)
 If rc<0 : ProcedureReturn h2cFail(*c,rc) : EndIf
 If rc=2 : ProcedureReturn 0 : EndIf
 If rc=1
  If *c\blockDiscard<>0 : ProcedureReturn 0 : EndIf
  ProcedureReturn h2cField(*c)
 EndIf
 *s=*c\blockStream : *c\decoding=0 : *c\blockUsed=0
 If *c\blockDiscard<>0 : *c\blockStream=0 : ProcedureReturn 0 : EndIf
 If *c\blockTrailers=0
  If *c\blockStatus=0 : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
  If *c\blockStatus<200
   If *c\blockEnd<>0 : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
   ProcedureReturn 0
  EndIf
  *s\status=*c\blockStatus
 EndIf
 If *c\blockEnd<>0 : *c\finishStream=*s : EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i h2cFrame(*c.H2Client)
 Define *h.H2FrameHeader,*s.H2Stream,p.i,i.i,n.i,v.i,offset.i,padding.i,rc.i,j.i,*other.H2Stream,closed.i
 *h=@*c\frame : p=*c\buffers\rx
 If *c\settingsSeen=0 And (*h\kind<>4 Or (*h\flags & 1)<>0) : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
 If *c\continuation<>0 And (*h\kind<>9 Or *h\stream<>*c\continuation) : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
 *s=h2cStream(*c,*h\stream)
 ; IDs are consecutive odd integers. Released older IDs remain closed without
 ; retaining unbounded tombstones. RFC 9113 5.1 permits minimal processing.
 closed=0
 If *h\stream<>0
  If *h\stream>=*c\nextStream Or (*h\stream & 1)=0
   closed=-1
  Else
   If *s=0
    closed=1
   Else
    If *s\state<>1 : closed=1 : EndIf
   EndIf
  EndIf
 EndIf
 Select *h\kind
  Case 4
   If (*h\flags & 1)<>0
    If *c\settingsPending=0 : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
    *c\settingsPending=0
   Else
    For i=0 To *h\length-1 Step 6
     n=NetReadBE16(p+i) : v=NetReadBE32(p+i+2)
     If n=2 : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
     If n=4 And v>$7FFFFFFF : ProcedureReturn h2cFail(*c,#H2_FLOW) : EndIf
     If n=4
      For j=0 To *c\buffers\streamCount-1
       *other=*c\buffers\streams+j*SizeOf(H2Stream)
       If *other\state=1
        If *other\sendWindow+v-*c\peerInitialWindow>$7FFFFFFF : ProcedureReturn h2cFail(*c,#H2_FLOW) : EndIf
        *other\sendWindow=*other\sendWindow+v-*c\peerInitialWindow
       EndIf
      Next
      *c\peerInitialWindow=v
     EndIf
     If n=5 And (v<16384 Or v>16777215) : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
     If n=3 : *c\peerStreams=v : EndIf
     If n=6 : *c\peerHeaderLimit=v : EndIf
    Next
    *c\settingsSeen=1 : *c\state=3
    H2FrameWrite(*c\buffers\tx,16384,0,4,1,0) : *c\txLength=9 : *c\txOffset=0
   EndIf
  Case 1
   If closed=-1 : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
   *c\blockDiscard=closed : *c\blockStream=0
   *c\blockEnd=*h\flags & 1 : *c\blockStatus=0 : *c\blockRegular=0 : *c\blockTrailers=0
   If closed=0
    *c\blockStream=*s : If *s\status<>0 : *c\blockTrailers=1 : EndIf
    If *c\blockTrailers<>0 And *c\blockEnd=0 : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
   EndIf
   offset=0 : padding=0
   If (*h\flags & 8)<>0 : padding=PeekA(p) : offset=1 : EndIf
   If (*h\flags & 32)<>0
    If (NetReadBE32(p+offset) & $7FFFFFFF)=*h\stream : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
    offset=offset+5
   EndIf
   n=*h\length-offset-padding
   If n<0 Or n>65536 : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
   For i=0 To n-1 : PokeA(*c\buffers\block+i,PeekA(p+offset+i)) : Next
   *c\blockUsed=n : *c\continuation=*h\stream
   If (*h\flags & 4)<>0 : *c\continuation=0 : *c\decoding=1 : EndIf
  Case 9
   If *c\continuation=0 Or *c\blockUsed+*h\length>65536 : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
   For i=0 To *h\length-1 : PokeA(*c\buffers\block+*c\blockUsed+i,PeekA(p+i)) : Next
   *c\blockUsed=*c\blockUsed+*h\length
   If (*h\flags & 4)<>0 : *c\continuation=0 : *c\decoding=1 : EndIf
  Case 0
   If closed=-1 : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
   If *h\length>*c\window : ProcedureReturn h2cFail(*c,#H2_FLOW) : EndIf
   offset=0 : padding=0
   If (*h\flags & 8)<>0 : offset=1 : padding=PeekA(p) : EndIf
   n=*h\length-offset-padding : If n<0 : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
   If closed<>0
    ; Discarded content still consumes connection credit, never stream credit.
    ; Parsing resumes only after the queued WINDOW_UPDATE is fully sent.
    If *h\length>0
     H2FrameWrite(*c\buffers\tx,16384,4,8,0,0)
     NetWriteBE32(*c\buffers\tx+9,*h\length) : *c\txLength=13 : *c\txOffset=0
    EndIf
   Else
    If *s\status=0 : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
    If *h\length>*s\window : ProcedureReturn h2cFail(*c,#H2_FLOW) : EndIf
    If n>0 And (*s\headOnly<>0 Or *s\status=204 Or *s\status=304) : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
    If *s\received>$7FFFFFFFFFFFFFFF-n : ProcedureReturn h2cFail(*c,#H2_LIMIT) : EndIf
    *s\received=*s\received+n
    If *s\contentLength>=0 And *s\status<>304 And *s\received>*s\contentLength : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
    *c\window=*c\window-*h\length : *s\window=*s\window-*h\length
    *c\credit=*h\length : *c\data=p+offset : *c\dataBytes=n : *c\eventStream=*s\id : *c\event=#H2_DATA
    If (*h\flags & 1)<>0 : *c\finishStream=*s : EndIf
   EndIf
  Case 2
   If (NetReadBE32(p) & $7FFFFFFF)=*h\stream : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
  Case 3
   If *s=0
    If *h\stream>=*c\nextStream Or (*h\stream & 1)=0 : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
   Else
    If *s\state=1
     *s\state=3 : *s\resetCode=NetReadBE32(p) : *c\activeStreams=*c\activeStreams-1
     *c\event=#H2_RESET : *c\eventStream=*s\id
    EndIf
   EndIf
  Case 5
   ProcedureReturn h2cFail(*c,#H2_PROTOCOL)
  Case 6
   If (*h\flags & 1)=0
    H2FrameWrite(*c\buffers\tx,16384,8,6,1,0)
    For i=0 To 7 : PokeA(*c\buffers\tx+9+i,PeekA(p+i)) : Next
    *c\txLength=17 : *c\txOffset=0
   EndIf
  Case 7
   n=NetReadBE32(p) & $7FFFFFFF
   If n>*c\lastPeerStream : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
   *c\lastPeerStream=n : *c\peerError=NetReadBE32(p+4) : *c\goaway=1
   *c\event=#H2_GOAWAY : *c\eventStream=0
  Case 8
   n=NetReadBE32(p) & $7FFFFFFF
   If n=0 : ProcedureReturn h2cFail(*c,#H2_FLOW) : EndIf
   If *h\stream=0
    If *c\sendWindow>$7FFFFFFF-n : ProcedureReturn h2cFail(*c,#H2_FLOW) : EndIf
    *c\sendWindow=*c\sendWindow+n
   Else
    If *s<>0
     If *s\state=1
      If *s\sendWindow>$7FFFFFFF-n : ProcedureReturn h2cFail(*c,#H2_FLOW) : EndIf
      *s\sendWindow=*s\sendWindow+n
     EndIf
    EndIf
   EndIf
   If *h\stream<>0 And *s=0
    If *h\stream>=*c\nextStream Or (*h\stream & 1)=0 : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
   EndIf
 EndSelect
 If *c\decoding<>0
  rc=HpackBegin(@*c\decoder,*c\buffers\block,*c\blockUsed,*c\buffers\field,8192,65536)
  If rc<>0 : ProcedureReturn h2cFail(*c,rc) : EndIf
 EndIf
 H2FrameInit(@*c\frame,16384) : *c\payloadUsed=0
 ProcedureReturn *c\event
EndProcedure
; Each step performs at most one send OR receive OR bounded HPACK step.
; An event blocks parsing until Consume. Pump underlying Service separately.
Procedure.i H2ClientStep(*c.H2Client,now.i)
 Define rc.i,st.i,n.i,i.i,*s.H2Stream
 If *c=0 : ProcedureReturn #H2_ARGUMENT : EndIf
 If *c\state=-1 : ProcedureReturn *c\error : EndIf
 If *c\state=0 : ProcedureReturn #H2_STATE : EndIf
 If ((now-*c\started) & $FFFFFFFF)>=*c\timeout : ProcedureReturn h2cFail(*c,#H2_TIMEOUT) : EndIf
 If *c\state=4 : ProcedureReturn 0 : EndIf
 If *c\event<>0 : ProcedureReturn *c\event : EndIf
 If *c\finishStream<>0 And *c\txLength=0 And *c\requestHeaderBytes=0 : ProcedureReturn h2cFinish(*c,*c\finishStream) : EndIf
 If *c\goaway<>0
  For i=0 To *c\buffers\streamCount-1
   *s=*c\buffers\streams+i*SizeOf(H2Stream)
   If *s\state=1 And *s\id>*c\lastPeerStream
    *s\state=3 : *s\resetCode=7 : *c\activeStreams=*c\activeStreams-1
    *c\event=#H2_RESET : *c\eventStream=*s\id : ProcedureReturn *c\event
   EndIf
  Next
 EndIf
 If *c\decoding<>0 : ProcedureReturn h2cDecode(*c) : EndIf
 st=WebTransportState(@*c\connection)
 If st<0 : ProcedureReturn h2cFail(*c,st) : EndIf
 If *c\state=1
  If st=0 : ProcedureReturn 0 : EndIf
  If st<>1 : ProcedureReturn h2cFail(*c,#H2_CLOSED) : EndIf
  rc=WebTransportAlpn(@*c\connection,*c\buffers\tx,16)
  If rc<0 : ProcedureReturn h2cFail(*c,rc) : EndIf
  If *c\allowHttp1<>0 And (rc=0 Or (rc=8 And h2cEqual(*c\buffers\tx,8,"http/1.1")))
   *c\state=4 : ProcedureReturn 0
  EndIf
  If rc<>2 Or PeekA(*c\buffers\tx)<>104 Or PeekA(*c\buffers\tx+1)<>50 : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
  H2ClientPreface(*c\buffers\tx,16384) : H2FrameWrite(*c\buffers\tx+24,16360,12,4,0,0)
  NetWriteBE16(*c\buffers\tx+33,2) : NetWriteBE32(*c\buffers\tx+35,0)
  NetWriteBE16(*c\buffers\tx+39,6) : NetWriteBE32(*c\buffers\tx+41,65536)
  *c\txLength=45 : *c\txOffset=0 : *c\settingsPending=1 : *c\state=2
  ProcedureReturn 0
 EndIf
 If *c\txLength<>0
  rc=WebTransportSend(@*c\connection,*c\buffers\tx+*c\txOffset,*c\txLength-*c\txOffset)
  If rc<0 And rc<>-110 : ProcedureReturn h2cFail(*c,rc) : EndIf
  If rc>0
   If rc>*c\txLength-*c\txOffset : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
   *c\sent=*c\sent+rc
   *c\txOffset=*c\txOffset+rc
   If *c\txOffset=*c\txLength : *c\txOffset=0 : *c\txLength=0 : EndIf
  EndIf
  ProcedureReturn 0
 EndIf
 If *c\requestHeaderBytes<>0
  h2cRequestHeaderFrame(*c) : ProcedureReturn 0
 EndIf
 If *c\frame\used<9
  n=9-*c\frame\used
  rc=WebTransportRecv(@*c\connection,*c\buffers\rx,n)
  If rc<0 : ProcedureReturn h2cFail(*c,rc) : EndIf
  If rc>n : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
  If rc=0
   If st=2 : ProcedureReturn h2cFail(*c,#H2_CLOSED) : EndIf
   ProcedureReturn 0
  EndIf
  *c\received=*c\received+rc
  rc=H2FrameFeed(@*c\frame,*c\buffers\rx,rc) : If rc<0 : ProcedureReturn h2cFail(*c,rc) : EndIf
  If *c\frame\used=9 And *c\frame\length=0 : ProcedureReturn h2cFrame(*c) : EndIf
  ProcedureReturn 0
 EndIf
 n=*c\frame\length-*c\payloadUsed
 rc=WebTransportRecv(@*c\connection,*c\buffers\rx+*c\payloadUsed,n)
 If rc<0 : ProcedureReturn h2cFail(*c,rc) : EndIf
 If rc>n : ProcedureReturn h2cFail(*c,#H2_PROTOCOL) : EndIf
 If rc=0
  If st=2 : ProcedureReturn h2cFail(*c,#H2_CLOSED) : EndIf
  ProcedureReturn 0
 EndIf
 *c\payloadUsed=*c\payloadUsed+rc
 *c\received=*c\received+rc
 If *c\payloadUsed=*c\frame\length : ProcedureReturn h2cFrame(*c) : EndIf
 ProcedureReturn 0
EndProcedure

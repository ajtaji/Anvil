; HTTP redirect URI resolution and policy, shared by all transports.
; RFC 3986 section 5; RFC 9110 sections 15.4 and 9.2. No copied implementation.
; Resolve explicit byte spans through the existing strict HTTP(S) URL parser.
XIncludeFile "Anvil/Network/web_url.pbi"
XIncludeFile "Anvil/Network/web_request.pbi"
#WEB_REDIRECT_STATUS=-560
#WEB_REDIRECT_DOWNGRADE=-561
#WEB_REDIRECT_REPLAY=-562
#WEB_REDIRECT_LIMIT=-563
#WEB_REDIRECT_UNSAFE=-564
#WEB_REDIRECT_GET=1
#WEB_REDIRECT_KEEP=2

Procedure.i wdAppend(destination.i,capacity.i,used.i,source.i,bytes.i)
  Define i.i
  If used<0 : ProcedureReturn used : EndIf
  If bytes>capacity-used-1 : ProcedureReturn #WEB_URL_CAPACITY : EndIf
  For i=0 To bytes-1 : PokeA(destination+used+i,PeekA(source+i)) : Next
  used=used+bytes : PokeA(destination+used,0)
  ProcedureReturn used
EndProcedure

; The target is an absolute path followed by an optional opaque query. Compact
; path segments in place; empty segments and trailing slashes stay significant.
Procedure wdNormalize(*url.WebUrl)
  Define pathEnd.i,start.i,finish.i,write.i,i.i,n.i,p.i
  p=*url\target : pathEnd=*url\targetLength
  For i=0 To *url\targetLength-1
    If PeekA(p+i)=63 : pathEnd=i : Break : EndIf
  Next
  start=1 : write=1
  While start<=pathEnd
    finish=start
    While finish<pathEnd
      If PeekA(p+finish)=47 : Break : EndIf
      finish=finish+1
    Wend
    n=finish-start
    If n=1 And PeekA(p+start)=46
      ; Drop a complete dot segment, retaining the preceding slash.
    ElseIf n=2 And PeekA(p+start)=46 And PeekA(p+start+1)=46
      If write>1
        write=write-1
        While write>1
          If PeekA(p+write-1)=47 : Break : EndIf
          write=write-1
        Wend
      EndIf
    Else
      For i=start To finish-1 : PokeA(p+write,PeekA(p+i)) : write=write+1 : Next
      If finish<pathEnd : PokeA(p+write,47) : write=write+1 : EndIf
    EndIf
    If finish=pathEnd : Break : EndIf
    start=finish+1
  Wend
  For i=pathEnd To *url\targetLength-1 : PokeA(p+write,PeekA(p+i)) : write=write+1 : Next
  PokeA(p+write,0) : *url\targetLength=write
EndProcedure

; scratch must not overlap the URL/input buffers. Output uses its own caller
; buffers as for WebUrlParse. The base is a previously validated HTTP(S) URL.
Procedure.i WebUrlResolve(*base.WebUrl,location.i,bytes.i,*out.WebUrl,scratch.i,capacity.i)
  Define i.i,c.i,absolute.i,network.i,used.i,copy.i,pathEnd.i,divisor.i,digit.i,rc.i
  If *base=0 Or *out=0 Or scratch=0 Or capacity<16 Or bytes<0 Or bytes>#WEB_URL_LIMIT Or (bytes>0 And location=0)
    ProcedureReturn #WEB_URL_ARGUMENT
  EndIf
  If *base\host=0 Or *base\target=0 Or *base\hostLength<1 Or *base\hostLength>=*base\hostCapacity Or *base\targetLength<1 Or *base\targetLength>=*base\targetCapacity Or *base\port<1 Or *base\port>65535
    ProcedureReturn #WEB_URL_ARGUMENT
  EndIf
  For i=0 To bytes-1
    c=PeekA(location+i)
    If c=58 : absolute=1 : Break : EndIf
    If c=47 Or c=63 Or c=35 : Break : EndIf
  Next
  If absolute
    rc=WebUrlParse(location,bytes,*base\secure,*out)
    If rc=0 : wdNormalize(*out) : EndIf
    ProcedureReturn rc
  EndIf
  If bytes>=2
    If PeekA(location)=47 And PeekA(location+1)=47 : network=1 : EndIf
  EndIf
  If *base\secure : used=wdAppend(scratch,capacity,0,"https:",6) : Else : used=wdAppend(scratch,capacity,0,"http:",5) : EndIf
  If network=0
    used=wdAppend(scratch,capacity,used,"//",2)
    used=wdAppend(scratch,capacity,used,*base\host,*base\hostLength)
    If *base\explicitPort
      used=wdAppend(scratch,capacity,used,":",1)
      If used<0 : ProcedureReturn used : EndIf
      divisor=10000
      While divisor>1 And *base\port/divisor=0 : divisor=divisor/10 : Wend
      While divisor>0
        If used>=capacity-1 : ProcedureReturn #WEB_URL_CAPACITY : EndIf
        digit=(*base\port/divisor) % 10 : PokeA(scratch+used,48+digit) : used=used+1
        divisor=divisor/10
      Wend
    EndIf
    pathEnd=*base\targetLength
    For i=0 To *base\targetLength-1
      If PeekA(*base\target+i)=63 : pathEnd=i : Break : EndIf
    Next
    If bytes=0
      copy=*base\targetLength
    ElseIf PeekA(location)=35
      copy=*base\targetLength
    ElseIf PeekA(location)=63
      copy=pathEnd
    ElseIf PeekA(location)<>47
      For i=0 To pathEnd-1
        If PeekA(*base\target+i)=47 : copy=i+1 : EndIf
      Next
    EndIf
    used=wdAppend(scratch,capacity,used,*base\target,copy)
  EndIf
  used=wdAppend(scratch,capacity,used,location,bytes)
  If used<0 : ProcedureReturn used : EndIf
  rc=WebUrlParse(scratch,used,*base\secure,*out)
  If rc=0 : wdNormalize(*out) : EndIf
  ProcedureReturn rc
EndProcedure

Procedure.i WebUrlSameOrigin(*a.WebUrl,*b.WebUrl)
  Define i.i
  If *a=0 Or *b=0 : ProcedureReturn 0 : EndIf
  If *a\secure<>*b\secure Or *a\port<>*b\port Or *a\hostLength<>*b\hostLength : ProcedureReturn 0 : EndIf
  For i=0 To *a\hostLength-1
    If webUrlLower(PeekA(*a\host+i))<>webUrlLower(PeekA(*b\host+i)) : ProcedureReturn 0 : EndIf
  Next
  ProcedureReturn 1
EndProcedure

; Pure policy: no request is sent here. A caller must discard credentials on
; origin changes, rebuild Host/framing, and supply replayable data when keeping
; a body. Never reuse a connection for a changed origin.
Procedure.i WebRedirectPlan(status.i,isGet.i,isHead.i,isPost.i,hasBody.i,replayable.i,*from.WebUrl,*to.WebUrl,hops.i,maximum.i,allowDowngrade.i,allowUnsafe.i)
  If *from=0 Or *to=0 Or maximum<0 Or hops<0 : ProcedureReturn #WEB_URL_ARGUMENT : EndIf
  If status<>301 And status<>302 And status<>303 And status<>307 And status<>308 : ProcedureReturn #WEB_REDIRECT_STATUS : EndIf
  If hops>=maximum : ProcedureReturn #WEB_REDIRECT_LIMIT : EndIf
  If *from\secure And *to\secure=0 And allowDowngrade=0 : ProcedureReturn #WEB_REDIRECT_DOWNGRADE : EndIf
  If (status=303 And isHead=0) Or ((status=301 Or status=302) And isPost)
    ProcedureReturn #WEB_REDIRECT_GET
  EndIf
  If hasBody And replayable=0 : ProcedureReturn #WEB_REDIRECT_REPLAY : EndIf
  If isGet=0 And isHead=0 And allowUnsafe=0 : ProcedureReturn #WEB_REDIRECT_UNSAFE : EndIf
  ProcedureReturn #WEB_REDIRECT_KEEP
EndProcedure

Structure WebRedirectOptions
  bodyLength.i
  replayable.i
  allowUnsafe.i
  hops.i
  maximum.i
  allowDowngrade.i
  keepAlive.i
EndStructure

; Build a separate finalized request after a redirect. Return GET or KEEP,
; or a negative refusal. Input bodyLength is the ORIGINAL declared length,
; not the serializer's remaining count after an upload. No bytes are replayed
; here; the caller must provide the original body again only for KEEP.
; Cross-origin redirects carry only content negotiation and User-Agent fields;
; arbitrary custom fields can contain credentials and are not copied blindly.
Procedure.i WebRequestRedirect(*previous.WebRequest,*from.WebUrl,*to.WebUrl,status.i,*options.WebRedirectOptions,*next.WebRequest,headers.i,capacity.i)
  Define method.i,methodLength.i,action.i,rc.i,at.i,finish.i,colon.i,start.i,last.i,i.i,c.i,copy.i,same.i,length.i
  If *previous=0 Or *from=0 Or *to=0 Or *options=0 Or *next=0 Or *next=*previous Or headers=0 Or headers=*previous\headers
    ProcedureReturn #WEB_URL_ARGUMENT
  EndIf
  If *previous\headers=0 Or *previous\length<1 Or *previous\error<0 Or *previous\state=0
    ProcedureReturn #WEB_REQUEST_STATE
  EndIf
  method=*previous\headers
  While methodLength<*previous\length
    If PeekA(method+methodLength)=32 : Break : EndIf
    methodLength=methodLength+1
  Wend
  action=WebRedirectPlan(status,wqEqual(method,methodLength,"get"),wqEqual(method,methodLength,"head"),wqEqual(method,methodLength,"post"),Bool(*options\bodyLength<>0),*options\replayable,*from,*to,*options\hops,*options\maximum,*options\allowDowngrade,*options\allowUnsafe)
  If action<0 : ProcedureReturn action : EndIf
  length=*options\bodyLength
  If action=#WEB_REDIRECT_GET : method="GET" : methodLength=3 : length=0 : EndIf
  rc=WebRequestInit(*next,*to,method,methodLength,length,*options\keepAlive,headers,capacity)
  If rc<0 : ProcedureReturn rc : EndIf
  same=WebUrlSameOrigin(*from,*to)
  ; Skip the old request line, then walk complete bounded header lines.
  at=0
  While at+1<*previous\length
    If PeekA(*previous\headers+at)=13 And PeekA(*previous\headers+at+1)=10 : at=at+2 : Break : EndIf
    at=at+1
  Wend
  While at+1<*previous\length
    finish=at
    While finish+1<*previous\length
      If PeekA(*previous\headers+finish)=13 And PeekA(*previous\headers+finish+1)=10 : Break : EndIf
      finish=finish+1
    Wend
    If finish=at : Break : EndIf
    If finish+1>=*previous\length : ProcedureReturn #WEB_REQUEST_SYNTAX : EndIf
    colon=at
    While colon<finish
      If PeekA(*previous\headers+colon)=58 : Break : EndIf
      colon=colon+1
    Wend
    If colon=finish : ProcedureReturn #WEB_REQUEST_SYNTAX : EndIf
    start=colon+1 : last=finish
    While start<last
      c=PeekA(*previous\headers+start) : If c<>32 And c<>9 : Break : EndIf
      start=start+1
    Wend
    copy=1
    If wqEqual(*previous\headers+at,colon-at,"host") Or wqEqual(*previous\headers+at,colon-at,"content-length") Or wqEqual(*previous\headers+at,colon-at,"transfer-encoding") Or wqEqual(*previous\headers+at,colon-at,"connection") Or wqEqual(*previous\headers+at,colon-at,"expect") Or wqEqual(*previous\headers+at,colon-at,"upgrade") Or wqEqual(*previous\headers+at,colon-at,"proxy-authorization")
      copy=0
    EndIf
    If same=0
      copy=0
      If wqEqual(*previous\headers+at,colon-at,"accept") Or wqEqual(*previous\headers+at,colon-at,"accept-encoding") Or wqEqual(*previous\headers+at,colon-at,"accept-language") Or wqEqual(*previous\headers+at,colon-at,"user-agent") : copy=1 : EndIf
      ; Representation metadata is necessary when an explicitly permitted
      ; replay preserves the body; it does not identify origin credentials.
      If action=#WEB_REDIRECT_KEEP
        If wqEqual(*previous\headers+at,colon-at,"content-type") Or wqEqual(*previous\headers+at,colon-at,"content-encoding") Or wqEqual(*previous\headers+at,colon-at,"content-language") : copy=1 : EndIf
      EndIf
    EndIf
    If action=#WEB_REDIRECT_GET
      If wqEqual(*previous\headers+at,colon-at,"content-type") Or wqEqual(*previous\headers+at,colon-at,"content-encoding") Or wqEqual(*previous\headers+at,colon-at,"content-language") Or wqEqual(*previous\headers+at,colon-at,"content-location") Or wqEqual(*previous\headers+at,colon-at,"content-md5") Or wqEqual(*previous\headers+at,colon-at,"digest") : copy=0 : EndIf
    EndIf
    If wqEqual(*previous\headers+at,colon-at,"if-match") Or wqEqual(*previous\headers+at,colon-at,"if-none-match") Or wqEqual(*previous\headers+at,colon-at,"if-modified-since") Or wqEqual(*previous\headers+at,colon-at,"if-unmodified-since") Or wqEqual(*previous\headers+at,colon-at,"if-range") Or wqEqual(*previous\headers+at,colon-at,"range") : copy=0 : EndIf
    If copy
      rc=WebRequestHeader(*next,*previous\headers+at,colon-at,*previous\headers+start,last-start)
      If rc<0 : ProcedureReturn rc : EndIf
    EndIf
    at=finish+2
  Wend
  rc=WebRequestFinishHeaders(*next)
  If rc<0 : ProcedureReturn rc : EndIf
  ProcedureReturn action
EndProcedure

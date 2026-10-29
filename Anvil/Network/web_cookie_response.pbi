; Explicit response-to-cookie-jar integration. No automatic credential replay.
XIncludeFile "Anvil/Network/web_cookies.pbi"
XIncludeFile "Anvil/Network/web_response.pbi"
; Process separate Set-Cookie fields after final response headers arrive.
; Returns fields accepted, or the first error. Earlier accepted fields remain
; committed on error. Scratch is disjoint and may contain session secrets.
Procedure.i WebCookiesCapture(*jar.WebCookies,*url.WebUrl,*response.WebResponse,now.i,scratch.i,capacity.i)
 Define i.i,n.i,rc.i
 If *response=0 Or scratch=0 Or capacity<2 Or capacity>8193 : ProcedureReturn #WEB_COOKIE_ARGUMENT : EndIf
 If *response\status<200 Or *response\state<#WEB_RESPONSE_LENGTH Or *response\error<0 : ProcedureReturn #WEB_COOKIE_ARGUMENT : EndIf
 While i<1024
  n=WebResponseHeader(*response,"set-cookie",i,scratch,capacity)
  If n=#WEB_RESPONSE_NOTFOUND : ProcedureReturn i : EndIf
  If n<0 : ProcedureReturn n : EndIf
  rc=WebCookieStore(*jar,*url,scratch,n,now)
  wckWipe(scratch,n)
  If rc<0 : ProcedureReturn rc : EndIf
  i=i+1
 Wend
 ProcedureReturn #WEB_COOKIE_LIMIT
EndProcedure

; Replace every prior Cookie field with the jar's current selection. Call
; before any request output; accepts adding-fields or finalized-unsent state.
; This refreshes same-origin redirect headers after a Set-Cookie deletion.
Procedure.i WebCookiesApply(*jar.WebCookies,*url.WebUrl,*request.WebRequest,now.i,sameSite.i,topLevelSafe.i,scratch.i,capacity.i)
 Define n.i,rc.i,pass.i,at.i,finish.i,colon.i,keep.i,written.i,i.i,limit.i,original.i,finalized.i,first.i,needed.i
 If *request=0 Or scratch=0 Or capacity<1 Or capacity>8192 : ProcedureReturn #WEB_COOKIE_ARGUMENT : EndIf
 If *request\error<0 : ProcedureReturn *request\error : EndIf
 If *request\state<0 Or *request\state>1 Or *request\offset<>0 Or *request\headers=0 Or *request\length<2 Or *request\length>*request\capacity : ProcedureReturn #WEB_REQUEST_STATE : EndIf
 n=WebCookieHeader(*jar,*url,now,sameSite,topLevelSafe,scratch,capacity)
 If n<0 : ProcedureReturn n : EndIf
 original=*request\length : finalized=*request\state : limit=original-finalized*2
 For pass=0 To 1
  at=0 : written=0 : first=1
  While at<limit
   finish=at
   While finish+1<limit
    If PeekA(*request\headers+finish)=13 And PeekA(*request\headers+finish+1)=10 : Break : EndIf
    finish=finish+1
   Wend
   If finish+1>=limit : wckWipe(scratch,n) : ProcedureReturn #WEB_REQUEST_SYNTAX : EndIf
   colon=at
   While colon<finish
    If PeekA(*request\headers+colon)=58 : Break : EndIf
    colon=colon+1
   Wend
   keep=1
   If first=0
    If wqEqual(*request\headers+at,colon-at,"cookie") : keep=0 : EndIf
   EndIf
   If keep
    If pass=1
     For i=at To finish+1 : PokeA(*request\headers+written,PeekA(*request\headers+i)) : written=written+1 : Next
    Else
     written=written+finish+2-at
    EndIf
   EndIf
   first=0 : at=finish+2
  Wend
  If pass=0
   needed=written+finalized*2
   If n>0 : needed=needed+n+10 : EndIf
   If needed>*request\capacity : wckWipe(scratch,n) : ProcedureReturn #WEB_REQUEST_LIMIT : EndIf
  EndIf
 Next
 *request\length=written : *request\state=0
 If n>0 : rc=WebRequestHeader(*request,"Cookie",6,scratch,n) : EndIf
 wckWipe(scratch,n)
 If rc=0 And finalized : rc=WebRequestFinishHeaders(*request) : EndIf
 If *request\length<original : wckWipe(*request\headers+*request\length,original-*request\length) : EndIf
 ProcedureReturn rc
EndProcedure

; Redirect continuation for the shared cooperative HTTP exchange.
; Call after Step returns 1. Intermediate bodies are drained by Step, then
; this helper resolves Location, rebuilds the request and begins the next hop.
; Every hop shares the original deadline. It never retries a failed upload.
XIncludeFile "Anvil/Network/web_client.pbi"
XIncludeFile "Anvil/Network/web_redirect.pbi"
#WEB_REDIRECT_LOCATION=-565

; Return 0 for a new active exchange, 1 for a non-redirect final response,
; negative for refusal/failure. options.bodyLength becomes zero on a switch
; to GET; when it stays nonzero, caller must restart its replayable body.
; nextUrl/request/response and all their buffers must be separate from the
; current contexts. nextResponse is initialized by the caller before this call.
; Keep current URL host storage alive until the previous connection is closed.
Procedure.i WebClientFollowRedirect(*client.WebClient,*currentUrl.WebUrl,*nextUrl.WebUrl,*nextRequest.WebRequest,*nextResponse.WebResponse,*options.WebRedirectOptions,headers.i,headerCapacity.i,location.i,locationCapacity.i,scratch.i,scratchCapacity.i,now.i)
  Define *response.WebResponse,*request.WebRequest,status.i,length.i,rc.i,action.i,started.i,budget.i,elapsed.i,tx.i,rx.i,txCapacity.i,rxCapacity.i
  If *client=0 Or *currentUrl=0 Or *nextUrl=0 Or *nextRequest=0 Or *nextResponse=0 Or *options=0
    ProcedureReturn #WEB_CLIENT_ARGUMENT
  EndIf
  If *client\state<>2 : ProcedureReturn #WEB_CLIENT_STATE : EndIf
  *response=*client\response : *request=*client\request : status=*response\status
  If status<>301 And status<>302 And status<>303 And status<>307 And status<>308 : ProcedureReturn 1 : EndIf
  If *currentUrl=*nextUrl Or *request=*nextRequest Or *response=*nextResponse Or location=0 Or locationCapacity<2
    ProcedureReturn wcFail(*client,#WEB_CLIENT_ARGUMENT)
  EndIf
  started=*client\started : budget=*client\timeout : elapsed=(now-started) & $FFFFFFFF
  If elapsed>=budget : ProcedureReturn wcFail(*client,#WEB_CLIENT_TIMEOUT) : EndIf
  length=WebResponseHeader(*response,"location",0,location,locationCapacity)
  If length<0 : ProcedureReturn wcFail(*client,#WEB_REDIRECT_LOCATION) : EndIf
  rc=WebResponseHeader(*response,"location",1,0,0)
  If rc<>#WEB_RESPONSE_NOTFOUND : ProcedureReturn wcFail(*client,#WEB_REDIRECT_LOCATION) : EndIf
  rc=WebUrlResolve(*currentUrl,location,length,*nextUrl,scratch,scratchCapacity)
  If rc<0 : ProcedureReturn wcFail(*client,rc) : EndIf
  action=WebRequestRedirect(*request,*currentUrl,*nextUrl,status,*options,*nextRequest,headers,headerCapacity)
  If action<0 : ProcedureReturn wcFail(*client,action) : EndIf
  If *nextResponse\state<>#WEB_RESPONSE_STATUS Or *nextResponse\error<>0
    ProcedureReturn wcFail(*client,#WEB_CLIENT_STATE)
  EndIf
  ; Reuse only an intact, completely drained connection to the same origin.
  rc=#WEB_CLIENT_STATE
  If WebUrlSameOrigin(*currentUrl,*nextUrl) And *response\reusable
    rc=WebClientNext(*client,*nextRequest,*nextResponse,started,budget)
  EndIf
  If rc<>0
    tx=*client\tx : rx=*client\rx : txCapacity=*client\txCapacity : rxCapacity=*client\rxCapacity
    WebClientClose(*client)
    rc=WebClientStart(*client,*nextUrl,*nextRequest,*nextResponse,tx,txCapacity,rx,rxCapacity,started,budget)
  EndIf
  If rc<0 : ProcedureReturn rc : EndIf
  *client\connection\host=*nextUrl\host
  *options\hops=*options\hops+1
  If action=#WEB_REDIRECT_GET : *options\bodyLength=0 : EndIf
  ProcedureReturn 0
EndProcedure

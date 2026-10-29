; Select bounded HTTP content decoding from completed response headers.
XIncludeFile "Anvil/Network/web_response.pbi"
XIncludeFile "Anvil/Network/web_content.pbi"
#WEB_CONTENT_UNSUPPORTED=-594
Structure WebContentName
  first.i
  second.i
EndStructure

; Call after response headers complete, before feeding any transfer body bytes.
; Missing encoding means identity. gzip and zlib-wrapped deflate are supported;
; stacked/duplicate/unknown encodings are explicit refusals, not raw data passed
; to a caller expecting decoded content. No-body responses need no decoder.
Procedure.i WebContentFromResponse(*s.WebContent,*response.WebResponse,window.i,windowCapacity.i,work.i,workCapacity.i,outputLimit.i)
  Define length.i,other.i,mode.i,name.WebContentName
  If *s=0 Or *response=0 : ProcedureReturn #WEB_INFLATE_ARGUMENT : EndIf
  If *response\state<#WEB_RESPONSE_LENGTH Or *response\error<>0 : ProcedureReturn #WEB_RESPONSE_ARGUMENT : EndIf
  mode=#WEB_CONTENT_IDENTITY
  If *response\headOnly=0 And *response\status<>204 And *response\status<>304
    length=WebResponseHeader(*response,"content-encoding",0,0,0)
    If length<>#WEB_RESPONSE_NOTFOUND
      If length<1 Or length>15 : ProcedureReturn #WEB_CONTENT_UNSUPPORTED : EndIf
      other=WebResponseHeader(*response,"content-encoding",1,0,0)
      If other<>#WEB_RESPONSE_NOTFOUND : ProcedureReturn #WEB_CONTENT_UNSUPPORTED : EndIf
      other=WebResponseHeader(*response,"content-encoding",0,@name,16)
      If other<>length : ProcedureReturn #WEB_CONTENT_UNSUPPORTED : EndIf
      If wrEqual(@name,length,"gzip")
        mode=#WEB_CONTENT_GZIP
      ElseIf wrEqual(@name,length,"deflate")
        mode=#WEB_CONTENT_DEFLATE
      ElseIf wrEqual(@name,length,"identity")=0
        ProcedureReturn #WEB_CONTENT_UNSUPPORTED
      EndIf
    EndIf
  EndIf
  ProcedureReturn WebContentInit(*s,mode,window,windowCapacity,work,workCapacity,outputLimit)
EndProcedure

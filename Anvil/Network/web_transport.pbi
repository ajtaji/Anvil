; One HTTP transport adapter over Anvil's existing network services.
; WEB_KERNEL_BINDING=1 calls the kernel owners; 0 calls ABI 1.6 slots.
; Only the call boundary differs. DNS retry, handle state and close ownership
; are shared. No register access, waits, or disabled TLS verification.
Structure WebConnection
  secure.i
  handle.i
  address.i
  host.i
  port.i
  dialAt.i
  dial4.i
  dial6.i
  dns4.i
  dns6.i
  error4.i
  error6.i
  allow6.i
  address6.IPv6AddressStorage
EndStructure

CompilerIf #WEB_KERNEL_BINDING=0
Global *webpDns,*webpOpen,*webpState,*webpSend,*webpRecv,*webpClose
Global *webpTlsOpen,*webpTlsState,*webpTlsSend,*webpTlsRecv,*webpTlsClose
Global *webpService
Global *webpOpen6,*webpDns6,*webpTime
Global webpBound.i

Procedure.i webpWord(table.i,offset.i)
  ProcedureReturn PeekA(table+offset) | (PeekA(table+offset+1)<<8) | (PeekA(table+offset+2)<<16) | (PeekA(table+offset+3)<<24)
EndProcedure

Procedure.i WebPayloadBind(table.i)
  webpBound=0
  *webpOpen6=0 : *webpDns6=0 : *webpTime=0
  If table=0 : ProcedureReturn -109 : EndIf
  If webpWord(table,0)<>$53564E41 Or webpWord(table,4)<>1 Or webpWord(table,8)<6 Or webpWord(table,12)<88 : ProcedureReturn -109 : EndIf
  *webpDns=PeekI(table+16+75*8)
  *webpTime=PeekI(table+16+11*8)
  *webpOpen=PeekI(table+16+76*8) : *webpSend=PeekI(table+16+77*8)
  *webpRecv=PeekI(table+16+78*8) : *webpClose=PeekI(table+16+79*8)
  *webpTlsOpen=PeekI(table+16+80*8) : *webpTlsSend=PeekI(table+16+81*8)
  *webpTlsRecv=PeekI(table+16+82*8) : *webpTlsClose=PeekI(table+16+83*8)
  *webpState=PeekI(table+16+86*8) : *webpService=PeekI(table+16+85*8)
  *webpTlsState=PeekI(table+16+87*8)
  If webpWord(table,8)>=11 And webpWord(table,12)>=89 : *webpOpen6=PeekI(table+16+88*8) : EndIf
  If webpWord(table,8)>=12 And webpWord(table,12)>=90 : *webpDns6=PeekI(table+16+89*8) : EndIf
  If *webpTime=0 Or *webpDns=0 Or *webpOpen=0 Or *webpSend=0 Or *webpRecv=0 Or *webpClose=0 Or *webpTlsOpen=0 Or *webpTlsSend=0 Or *webpTlsRecv=0 Or *webpTlsClose=0 Or *webpState=0 Or *webpService=0 Or *webpTlsState=0 : ProcedureReturn -109 : EndIf
  webpBound=1 : ProcedureReturn 0
EndProcedure

Procedure.i WebPayloadService(sliceMs.i)
  If webpBound=0 : ProcedureReturn -109 : EndIf
  ProcedureReturn webpService(sliceMs)
EndProcedure

CompilerEndIf

Procedure.i webDialTime()
 CompilerIf #WEB_KERNEL_BINDING=1
  ProcedureReturn millis()
 CompilerElse
  ProcedureReturn webpTime()/1000
 CompilerEndIf
EndProcedure

Procedure.i webDialState(handle.i)
 CompilerIf #WEB_KERNEL_BINDING=1
  ProcedureReturn PayNetTcpState(handle)
 CompilerElse
  ProcedureReturn webpState(handle)
 CompilerEndIf
EndProcedure

Procedure webDialClose(handle.i)
 If handle<=0 : ProcedureReturn : EndIf
 CompilerIf #WEB_KERNEL_BINDING=1
  PayNetTcpClose(handle)
 CompilerElse
  webpClose(handle)
 CompilerEndIf
EndProcedure

Procedure webDialWin(*c.WebConnection,handle.i)
 If *c\dial4<>handle : webDialClose(*c\dial4) : EndIf
 If *c\dial6<>handle : webDialClose(*c\dial6) : EndIf
 *c\handle=handle : *c\dial4=0 : *c\dial6=0
EndProcedure

; Numeric IPv4 authorities must never be reinterpreted as DNS names for AAAA.
Procedure.i webDialLiteral4(host.i)
 Define i.i,parts.i,digits.i,value.i,ch.i
 If host=0 : ProcedureReturn 0 : EndIf
 For i=0 To 15
  ch=PeekA(host+i)
  If ch=0 Or ch=46
   If digits=0 Or value>255 : ProcedureReturn 0 : EndIf
   parts=parts+1
   If ch=0 : ProcedureReturn Bool(parts=4) : EndIf
   If parts>=4 : ProcedureReturn 0 : EndIf
   value=0 : digits=0
  Else
   If ch<48 Or ch>57 Or digits>=3 : ProcedureReturn 0 : EndIf
   value=value*10+ch-48 : digits=digits+1
  EndIf
 Next
 ProcedureReturn 0
EndProcedure

Procedure.i WebTransportOpen(*c.WebConnection)
  Define literal.IPv6AddressStorage
  Define n.i,rc.i
  *c\handle=0 : *c\address=0
  *c\dial4=0 : *c\dial6=0 : *c\dns4=0 : *c\dns6=0
  *c\error4=0 : *c\error6=0 : *c\allow6=0
  If PeekA(*c\host)=91
    n=0 : While n<48 And PeekA(*c\host+n)<>0 : n=n+1 : Wend
    rc=WebUrlHostIPv6(*c\host,n,@literal)
    If rc<>0 : ProcedureReturn rc : EndIf
    ; Literal certificate verification still requires separate TLS support.
    If *c\secure<>0 : ProcedureReturn #WEB_URL_HOST_UNSUPPORTED : EndIf
    CompilerIf #WEB_KERNEL_BINDING=1
      *c\handle=PayNetTcpOpen6(@literal,*c\port)
      If *c\handle<0 : ProcedureReturn *c\handle : EndIf
      ProcedureReturn 0
    CompilerElse
      If webpBound=0 Or webpOpen6=0 : ProcedureReturn #WEB_URL_HOST_UNSUPPORTED : EndIf
      *c\handle=webpOpen6(@literal,*c\port)
      If *c\handle<0 : ProcedureReturn *c\handle : EndIf
      ProcedureReturn 0
    CompilerEndIf
  EndIf
  CompilerIf #WEB_KERNEL_BINDING=0
    If webpBound=0 : ProcedureReturn -109 : EndIf
  CompilerEndIf
  *c\dialAt=webDialTime()
  CompilerIf #WEB_KERNEL_BINDING=1
    *c\allow6=1
  CompilerElse
    If webpDns6<>0 And webpOpen6<>0 : *c\allow6=1 : EndIf
  CompilerEndIf
  If webDialLiteral4(*c\host) : *c\allow6=0 : EndIf
  If *c\secure
  CompilerIf #WEB_KERNEL_BINDING=1
    *c\handle=TlsClientOpen(*c\host,*c\port)
  CompilerElse
    *c\handle=webpTlsOpen(*c\host,*c\port)
  CompilerEndIf
    If *c\handle<0 : ProcedureReturn *c\handle : EndIf
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i WebTransportState(*c.WebConnection)
  Define rc.i
  If *c\secure
  CompilerIf #WEB_KERNEL_BINDING=1
    rc=TlsClientState(*c\handle)
  CompilerElse
    rc=webpTlsState(*c\handle)
  CompilerEndIf
    If rc<0 : ProcedureReturn rc : EndIf
    If rc=4 : ProcedureReturn 1 : EndIf
    If rc=5 : ProcedureReturn 2 : EndIf
    ProcedureReturn 0
  EndIf
  If *c\handle>0
    rc=webDialState(*c\handle)
    If rc<0 : ProcedureReturn rc : EndIf
    If rc=2 : ProcedureReturn 1 : EndIf
    If rc=3 : ProcedureReturn 2 : EndIf
    ProcedureReturn 0
  EndIf
  ; Poll both attempts on every call, even while the other DNS type is busy.
  If *c\dial4>0
    rc=webDialState(*c\dial4)
    If rc=2 Or rc=3
      webDialWin(*c,*c\dial4) : ProcedureReturn rc-1
    EndIf
    If rc<0
      webDialClose(*c\dial4) : *c\dial4=0 : *c\dns4=3 : *c\error4=rc
    EndIf
  EndIf
  If *c\dial6>0
    rc=webDialState(*c\dial6)
    If rc=2 Or rc=3
      webDialWin(*c,*c\dial6) : ProcedureReturn rc-1
    EndIf
    If rc<0
      webDialClose(*c\dial6) : *c\dial6=0 : *c\dns6=3 : *c\error6=rc
    EndIf
  EndIf
  If *c\dns4<2
    CompilerIf #WEB_KERNEL_BINDING=1
      rc=PayNetDnsResolve(*c\host)
    CompilerElse
      rc=webpDns(*c\host)
    CompilerEndIf
    If rc=-110 Or rc=-103
      *c\dns4=1
    ElseIf rc>0
      *c\address=rc : *c\dns4=2
    Else
      *c\error4=rc : *c\dns4=3
    EndIf
  EndIf
  If *c\dns4=2 And *c\dial4=0
    CompilerIf #WEB_KERNEL_BINDING=1
      rc=PayNetTcpOpen(*c\address,*c\port)
    CompilerElse
      rc=webpOpen(*c\address,*c\port)
    CompilerEndIf
    If rc>0
      *c\dial4=rc
    ElseIf rc<>-103
      *c\error4=rc : *c\dns4=3
    EndIf
  EndIf
  ; IPv4 starts immediately. IPv6 is eligible after 250 ms or an IPv4
  ; failure. The resolver serializes uncached queries, but both connection
  ; attempts progress without waiting for the other family to time out.
  If *c\allow6 And (*c\dns4=3 Or ((webDialTime()-*c\dialAt) & $FFFFFFFF)>=250)
    If *c\dns6<2
      CompilerIf #WEB_KERNEL_BINDING=1
        rc=PayNetDnsResolve6(*c\host,@*c\address6)
      CompilerElse
        rc=webpDns6(*c\host,@*c\address6)
      CompilerEndIf
      If rc=-110 Or rc=-103
        *c\dns6=1
      ElseIf rc=16
        *c\dns6=2
      Else
        *c\error6=rc : *c\dns6=3
      EndIf
    EndIf
    If *c\dns6=2 And *c\dial6=0
      CompilerIf #WEB_KERNEL_BINDING=1
        rc=PayNetTcpOpen6(@*c\address6,*c\port)
      CompilerElse
        rc=webpOpen6(@*c\address6,*c\port)
      CompilerEndIf
      If rc>0
        *c\dial6=rc
      ElseIf rc<>-103
        *c\error6=rc : *c\dns6=3
      EndIf
    EndIf
  EndIf
  If *c\dns4=3 And (*c\allow6=0 Or *c\dns6=3)
    If *c\error6<0 : ProcedureReturn *c\error6 : EndIf
    If *c\error4<0 : ProcedureReturn *c\error4 : EndIf
    ProcedureReturn -105
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i WebTransportSend(*c.WebConnection,source.i,bytes.i)
  If *c\secure
  CompilerIf #WEB_KERNEL_BINDING=1
    ProcedureReturn TlsClientSend(*c\handle,source,bytes)
  CompilerElse
    ProcedureReturn webpTlsSend(*c\handle,source,bytes)
  CompilerEndIf
  EndIf
  CompilerIf #WEB_KERNEL_BINDING=1
  ProcedureReturn PayNetTcpSend(*c\handle,source,bytes)
  CompilerElse
  ProcedureReturn webpSend(*c\handle,source,bytes)
  CompilerEndIf
EndProcedure

Procedure.i WebTransportRecv(*c.WebConnection,destination.i,capacity.i)
  If *c\secure
  CompilerIf #WEB_KERNEL_BINDING=1
    ProcedureReturn TlsClientRecv(*c\handle,destination,capacity)
  CompilerElse
    ProcedureReturn webpTlsRecv(*c\handle,destination,capacity)
  CompilerEndIf
  EndIf
  CompilerIf #WEB_KERNEL_BINDING=1
  ProcedureReturn PayNetTcpRecv(*c\handle,destination,capacity)
  CompilerElse
  ProcedureReturn webpRecv(*c\handle,destination,capacity)
  CompilerEndIf
EndProcedure

Procedure WebTransportClose(*c.WebConnection)
  webDialClose(*c\dial4) : webDialClose(*c\dial6)
  *c\dial4=0 : *c\dial6=0 : *c\dns4=3 : *c\dns6=3
  If *c\handle>0
    If *c\secure
  CompilerIf #WEB_KERNEL_BINDING=1
      TlsClientClose(*c\handle)
  CompilerElse
      webpTlsClose(*c\handle)
  CompilerEndIf
    Else
  CompilerIf #WEB_KERNEL_BINDING=1
      PayNetTcpClose(*c\handle)
  CompilerElse
      webpClose(*c\handle)
  CompilerEndIf
    EndIf
  EndIf
  *c\handle=0
EndProcedure

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
EndStructure

CompilerIf #WEB_KERNEL_BINDING=0
Global *webpDns,*webpOpen,*webpState,*webpSend,*webpRecv,*webpClose
Global *webpTlsOpen,*webpTlsState,*webpTlsSend,*webpTlsRecv,*webpTlsClose
Global *webpService
Global webpBound.i

Procedure.i webpWord(table.i,offset.i)
  ProcedureReturn PeekA(table+offset) | (PeekA(table+offset+1)<<8) | (PeekA(table+offset+2)<<16) | (PeekA(table+offset+3)<<24)
EndProcedure

Procedure.i WebPayloadBind(table.i)
  webpBound=0
  If table=0 : ProcedureReturn -109 : EndIf
  If webpWord(table,0)<>$53564E41 Or webpWord(table,4)<>1 Or webpWord(table,8)<6 Or webpWord(table,12)<88 : ProcedureReturn -109 : EndIf
  *webpDns=PeekI(table+16+75*8)
  *webpOpen=PeekI(table+16+76*8) : *webpSend=PeekI(table+16+77*8)
  *webpRecv=PeekI(table+16+78*8) : *webpClose=PeekI(table+16+79*8)
  *webpTlsOpen=PeekI(table+16+80*8) : *webpTlsSend=PeekI(table+16+81*8)
  *webpTlsRecv=PeekI(table+16+82*8) : *webpTlsClose=PeekI(table+16+83*8)
  *webpState=PeekI(table+16+86*8) : *webpService=PeekI(table+16+85*8)
  *webpTlsState=PeekI(table+16+87*8)
  If *webpDns=0 Or *webpOpen=0 Or *webpSend=0 Or *webpRecv=0 Or *webpClose=0 Or *webpTlsOpen=0 Or *webpTlsSend=0 Or *webpTlsRecv=0 Or *webpTlsClose=0 Or *webpState=0 Or *webpService=0 Or *webpTlsState=0 : ProcedureReturn -109 : EndIf
  webpBound=1 : ProcedureReturn 0
EndProcedure

Procedure.i WebPayloadService(sliceMs.i)
  If webpBound=0 : ProcedureReturn -109 : EndIf
  ProcedureReturn webpService(sliceMs)
EndProcedure

CompilerEndIf

Procedure.i WebTransportOpen(*c.WebConnection)
  *c\handle=0 : *c\address=0
  CompilerIf #WEB_KERNEL_BINDING=0
    If webpBound=0 : ProcedureReturn -109 : EndIf
  CompilerEndIf
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
  If *c\handle=0
  CompilerIf #WEB_KERNEL_BINDING=1
    rc=PayNetDnsResolve(*c\host)
  CompilerElse
    rc=webpDns(*c\host)
  CompilerEndIf
    If rc=-110 Or rc=-103 : ProcedureReturn 0 : EndIf
    If rc<0 : ProcedureReturn rc : EndIf
    *c\address=rc
  CompilerIf #WEB_KERNEL_BINDING=1
    *c\handle=PayNetTcpOpen(rc,*c\port)
  CompilerElse
    *c\handle=webpOpen(rc,*c\port)
  CompilerEndIf
    If *c\handle<0 : ProcedureReturn *c\handle : EndIf
  EndIf
  CompilerIf #WEB_KERNEL_BINDING=1
  rc=PayNetTcpState(*c\handle)
  CompilerElse
  rc=webpState(*c\handle)
  CompilerEndIf
  If rc<0 : ProcedureReturn rc : EndIf
  If rc=2 : ProcedureReturn 1 : EndIf
  If rc=3 : ProcedureReturn 2 : EndIf
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

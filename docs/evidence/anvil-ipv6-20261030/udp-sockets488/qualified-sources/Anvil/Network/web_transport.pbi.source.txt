; One HTTP transport adapter over Anvil's existing network services.
; WEB_KERNEL_BINDING=1 calls the kernel owners; 0 calls ABI 1.6 slots.
; Only the call boundary differs. DNS retry, handle state and close ownership
; are shared. No register access, waits, or disabled TLS verification.
CompilerIf #WEB_KERNEL_BINDING=1
 XIncludeFile "Anvil/Core/tcp_dial.pbi"
CompilerElse
 #TCP_DIAL_KERNEL=0
 XIncludeFile "Anvil/Network/tcp_dial.pbi"
CompilerEndIf
Structure WebConnection
 secure.i
 handle.i
 address.i
 host.i
 port.i
 dial.TcpDial
EndStructure

CompilerIf #WEB_KERNEL_BINDING=0
Global *webpDns,*webpOpen,*webpState,*webpSend,*webpRecv,*webpClose
Global *webpTlsOpen,*webpTlsState,*webpTlsSend,*webpTlsRecv,*webpTlsClose
Global *webpService
Global *webpOpen6,*webpDns6,*webpTime
Global *webpTlsOpenAlpn,*webpTlsAlpn,*webpTlsDrain
Global webpBound.i

Procedure.i webpWord(table.i,offset.i)
  ProcedureReturn PeekA(table+offset) | (PeekA(table+offset+1)<<8) | (PeekA(table+offset+2)<<16) | (PeekA(table+offset+3)<<24)
EndProcedure

Procedure.i WebPayloadBind(table.i)
  webpBound=0
  *webpOpen6=0 : *webpDns6=0 : *webpTime=0
  *webpTlsOpenAlpn=0 : *webpTlsAlpn=0 : *webpTlsDrain=0
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
  If webpWord(table,8)>=13 And webpWord(table,12)>=92
    *webpTlsOpenAlpn=PeekI(table+16+90*8) : *webpTlsAlpn=PeekI(table+16+91*8)
  EndIf
  If webpWord(table,8)>=14 And webpWord(table,12)>=93 : *webpTlsDrain=PeekI(table+16+92*8) : EndIf
  If *webpTime=0 Or *webpDns=0 Or *webpOpen=0 Or *webpSend=0 Or *webpRecv=0 Or *webpClose=0 Or *webpTlsOpen=0 Or *webpTlsSend=0 Or *webpTlsRecv=0 Or *webpTlsClose=0 Or *webpState=0 Or *webpService=0 Or *webpTlsState=0 : ProcedureReturn -109 : EndIf
  webpBound=1 : ProcedureReturn 0
EndProcedure

Procedure.i WebPayloadService(sliceMs.i)
  If webpBound=0 : ProcedureReturn -109 : EndIf
  ProcedureReturn webpService(sliceMs)
EndProcedure

CompilerEndIf

Procedure.i webtOpen(*c.WebConnection,protocols.i,bytes.i)
  Define literal.IPv6AddressStorage
  Define n.i,rc.i
  If *c=0 : ProcedureReturn -102 : EndIf
  If *c\host=0 Or bytes<0 Or bytes>256 Or (bytes>0 And protocols=0) : ProcedureReturn -102 : EndIf
  If bytes>0 And *c\secure=0 : ProcedureReturn -102 : EndIf
  *c\handle=0 : *c\address=0
  For n=0 To SizeOf(TcpDial)-1 : PokeA(@*c\dial+n,0) : Next
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
  If *c\secure
  CompilerIf #WEB_KERNEL_BINDING=1
    If bytes>0
      *c\handle=TlsClientOpenAlpn(*c\host,*c\port,protocols,bytes)
    Else
      *c\handle=TlsClientOpen(*c\host,*c\port)
    EndIf
  CompilerElse
    If bytes>0
      If *webpTlsOpenAlpn=0 : ProcedureReturn -109 : EndIf
      *c\handle=webpTlsOpenAlpn(*c\host,*c\port,protocols,bytes)
    Else
      *c\handle=webpTlsOpen(*c\host,*c\port)
    EndIf
  CompilerEndIf
    If *c\handle<0 : ProcedureReturn *c\handle : EndIf
  EndIf
  If *c\secure=0
  CompilerIf #WEB_KERNEL_BINDING=1
    ProcedureReturn NetDialStart(@*c\dial,*c\host,*c\port)
  CompilerElse
    tcpdTime=webpTime : tcpdDns4=webpDns : tcpdDns6=webpDns6
    tcpdOpen4=webpOpen : tcpdOpen6=webpOpen6
    tcpdState=webpState : tcpdClose=webpClose
    ProcedureReturn TcpDialStart(@*c\dial,*c\host,*c\port)
  CompilerEndIf
  EndIf
  ProcedureReturn 0
EndProcedure

; Legacy callers retain no-offer behavior. Only a protocol-aware caller opts in.
Procedure.i WebTransportOpen(*c.WebConnection)
  ProcedureReturn webtOpen(*c,0,0)
EndProcedure

Procedure.i WebTransportOpenAlpn(*c.WebConnection,protocols.i,bytes.i)
  ProcedureReturn webtOpen(*c,protocols,bytes)
EndProcedure

; Returns opaque selected bytes, zero for no selection, or a service error.
; Does not advance the handshake. Service/State retain progress ownership.
Procedure.i WebTransportAlpn(*c.WebConnection,destination.i,capacity.i)
  If *c=0 : ProcedureReturn -102 : EndIf
  If *c\secure=0 : ProcedureReturn -102 : EndIf
  CompilerIf #WEB_KERNEL_BINDING=1
    ProcedureReturn TlsClientAlpn(*c\handle,destination,capacity)
  CompilerElse
    If webpBound=0 Or *webpTlsAlpn=0 : ProcedureReturn -109 : EndIf
    ProcedureReturn webpTlsAlpn(*c\handle,destination,capacity)
  CompilerEndIf
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
  CompilerIf #WEB_KERNEL_BINDING=1
    rc=PayNetTcpState(*c\handle)
  CompilerElse
    rc=webpState(*c\handle)
  CompilerEndIf
    If rc<0 : ProcedureReturn rc : EndIf
    If rc=2 : ProcedureReturn 1 : EndIf
    If rc=3 : ProcedureReturn 2 : EndIf
    ProcedureReturn 0
  EndIf
  rc=TcpDialPoll(@*c\dial)
  If rc>0 : *c\handle=TcpDialTake(@*c\dial) : EndIf
  ProcedureReturn rc
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

 ; Accepted plaintext is not necessarily protected or handed to TCP yet.
Procedure.i WebTransportDrain(*c.WebConnection)
  If *c\secure=0 : ProcedureReturn 1 : EndIf
  CompilerIf #WEB_KERNEL_BINDING=1
    ProcedureReturn TlsClientDrain(*c\handle)
  CompilerElse
    If *webpTlsDrain=0 : ProcedureReturn -109 : EndIf
    ProcedureReturn webpTlsDrain(*c\handle)
  CompilerEndIf
EndProcedure

Procedure WebTransportClose(*c.WebConnection)
  TcpDialClose(@*c\dial)
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

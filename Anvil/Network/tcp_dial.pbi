; Shared bounded IPv4/IPv6 connection selection, independent of TLS and HTTP.
; The caller owns callbacks/context storage and drives network services outside Poll.
; State results: 0 pending, 1 open, 2 peer closed, negative service error.
XIncludeFile "Anvil/Network/ipv6_address.pbi"
Structure TcpDial
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
  family.i
EndStructure
CompilerIf #TCP_DIAL_KERNEL=0
 Global *tcpdTime,*tcpdDns4,*tcpdDns6,*tcpdOpen4,*tcpdOpen6,*tcpdState,*tcpdClose
CompilerEndIf
Procedure.i tcpdial_Time(*d.TcpDial)
 CompilerIf #TCP_DIAL_KERNEL=1
  ProcedureReturn millis()
 CompilerElse
  ProcedureReturn tcpdTime()/1000
 CompilerEndIf
EndProcedure
Procedure.i tcpdial_State(*d.TcpDial,handle.i)
 CompilerIf #TCP_DIAL_KERNEL=1
  ProcedureReturn PayNetTcpState(handle)
 CompilerElse
  ProcedureReturn tcpdState(handle)
 CompilerEndIf
EndProcedure
Procedure tcpdial_Close(*d.TcpDial,handle.i)
 If handle<=0 : ProcedureReturn : EndIf
 CompilerIf #TCP_DIAL_KERNEL=1
  PayNetTcpClose(handle)
 CompilerElse
  tcpdClose(handle)
 CompilerEndIf
EndProcedure
Procedure tcpdial_Win(*d.TcpDial,handle.i)
 If *d\dial4<>handle : tcpdial_Close(*d,*d\dial4) : EndIf
 If *d\dial6<>handle : tcpdial_Close(*d,*d\dial6) : EndIf
 *d\family=4 : If handle=*d\dial6 : *d\family=6 : EndIf
 *d\handle=handle : *d\dial4=0 : *d\dial6=0
EndProcedure
Procedure.i tcpdial_Literal4(host.i)
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
Procedure.i TcpDialStart(*d.TcpDial,host.i,port.i)
 Define i.i
 If *d=0 Or host=0 Or port<1 Or port>65535 : ProcedureReturn -102 : EndIf
 CompilerIf #TCP_DIAL_KERNEL=0
  If tcpdTime=0 Or tcpdDns4=0 Or tcpdOpen4=0 Or tcpdState=0 Or tcpdClose=0 : ProcedureReturn -109 : EndIf
 CompilerEndIf
 For i=0 To SizeOf(TcpDial)-1 : PokeA(*d+i,0) : Next
 *d\host=host : *d\port=port : *d\dialAt=tcpdial_Time(*d)
 CompilerIf #TCP_DIAL_KERNEL=1
  *d\allow6=1
 CompilerElse
  If tcpdDns6<>0 And tcpdOpen6<>0 : *d\allow6=1 : EndIf
 CompilerEndIf
 If tcpdial_Literal4(host) : *d\allow6=0 : EndIf
 ProcedureReturn 0
EndProcedure

Procedure.i TcpDialPoll(*d.TcpDial)
 Define rc.i
 If *d=0 Or *d\host=0 : ProcedureReturn -102 : EndIf
  If *d\handle>0
    rc=tcpdial_State(*d,*d\handle)
    If rc<0 : ProcedureReturn rc : EndIf
    If rc=2 : ProcedureReturn 1 : EndIf
    If rc=3 : ProcedureReturn 2 : EndIf
    ProcedureReturn 0
  EndIf
  ; Poll both attempts on every call, even while the other DNS type is busy.
  If *d\dial4>0
    rc=tcpdial_State(*d,*d\dial4)
    If rc=2 Or rc=3
      tcpdial_Win(*d,*d\dial4) : ProcedureReturn rc-1
    EndIf
    If rc<0
      tcpdial_Close(*d,*d\dial4) : *d\dial4=0 : *d\dns4=3 : *d\error4=rc
    EndIf
  EndIf
  If *d\dial6>0
    rc=tcpdial_State(*d,*d\dial6)
    If rc=2 Or rc=3
      tcpdial_Win(*d,*d\dial6) : ProcedureReturn rc-1
    EndIf
    If rc<0
      tcpdial_Close(*d,*d\dial6) : *d\dial6=0 : *d\dns6=3 : *d\error6=rc
    EndIf
  EndIf
  If *d\dns4<2
    CompilerIf #TCP_DIAL_KERNEL=1
 rc=PayNetDnsResolve(*d\host)
 CompilerElse
 rc=tcpdDns4(*d\host)
 CompilerEndIf
    If rc=-110 Or rc=-103
      *d\dns4=1
    ElseIf rc>0
      *d\address=rc : *d\dns4=2
    Else
      *d\error4=rc : *d\dns4=3
    EndIf
  EndIf
  If *d\dns4=2 And *d\dial4=0
    CompilerIf #TCP_DIAL_KERNEL=1
 rc=PayNetTcpOpen(*d\address,*d\port)
 CompilerElse
 rc=tcpdOpen4(*d\address,*d\port)
 CompilerEndIf
    If rc>0
      *d\dial4=rc
    ElseIf rc<>-103
      *d\error4=rc : *d\dns4=3
    EndIf
  EndIf
  ; IPv4 starts immediately. IPv6 is eligible after 250 ms or an IPv4
  ; failure. The resolver serializes uncached queries, but both connection
  ; attempts progress without waiting for the other family to time out.
  If *d\allow6 And (*d\dns4=3 Or ((tcpdial_Time(*d)-*d\dialAt) & $FFFFFFFF)>=250)
    If *d\dns6<2
      CompilerIf #TCP_DIAL_KERNEL=1
 rc=PayNetDnsResolve6(*d\host,@*d\address6)
 CompilerElse
 rc=tcpdDns6(*d\host,@*d\address6)
 CompilerEndIf
      If rc=-110 Or rc=-103
        *d\dns6=1
      ElseIf rc=16
        *d\dns6=2
      Else
        *d\error6=rc : *d\dns6=3
      EndIf
    EndIf
    If *d\dns6=2 And *d\dial6=0
      CompilerIf #TCP_DIAL_KERNEL=1
 rc=PayNetTcpOpen6(@*d\address6,*d\port)
 CompilerElse
 rc=tcpdOpen6(@*d\address6,*d\port)
 CompilerEndIf
      If rc>0
        *d\dial6=rc
      ElseIf rc<>-103
        *d\error6=rc : *d\dns6=3
      EndIf
    EndIf
  EndIf
  If *d\dns4=3 And (*d\allow6=0 Or *d\dns6=3)
    If *d\error6<0 : ProcedureReturn *d\error6 : EndIf
    If *d\error4<0 : ProcedureReturn *d\error4 : EndIf
    ProcedureReturn -105
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure TcpDialClose(*d.TcpDial)
 If *d=0 : ProcedureReturn : EndIf
 tcpdial_Close(*d,*d\dial4) : tcpdial_Close(*d,*d\dial6) : tcpdial_Close(*d,*d\handle)
 *d\dial4=0 : *d\dial6=0 : *d\handle=0 : *d\dns4=3 : *d\dns6=3
EndProcedure
Procedure.i TcpDialTake(*d.TcpDial)
 Define h.i
 h=*d\handle : *d\handle=0 : ProcedureReturn h
EndProcedure

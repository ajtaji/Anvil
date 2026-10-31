; Step-driven CRYPTO feed, traffic-key transitions, peer parameters and
; Finished output. Uses the connection snapshot, never foreground TLS globals.
; Caller saves the initialized TLS context before Begin, checks the connection
; deadline and drives UDP separately. No network I/O or wait loops here.
#QUIC_FEED_STATE=-3561
#QUIC_FEED_ARGUMENT=-3562
#QUIC_FEED_PARAMETERS=-3563
Procedure.i quiccf_Valid(*c.QuicConnection)
 ProcedureReturn Bool(*c>0 And *c<=$7FFFFFFFFFFFFFFF-SizeOf(QuicConnection))
EndProcedure
Procedure.i quiccf_Fail(*c.QuicConnection,rc.i)
 Define n.i
 *c\feed\phase=-1 : *c\feed\result=rc : n=QuicConnectionClose(*c,rc)
 ProcedureReturn rc
EndProcedure
Procedure.i QuicConnectionTlsBegin(*c.QuicConnection,level.i,peerBytes.i,timeoutUs.i)
 If quiccf_Valid(*c)=0 Or (level<>0 And level<>2) Or peerBytes<0 Or peerBytes>20 Or timeoutUs<=0 : ProcedureReturn #QUIC_FEED_ARGUMENT : EndIf
 If *c\phase<>1 Or (*c\feed\phase<>0 And *c\feed\phase<>12) : ProcedureReturn #QUIC_FEED_STATE : EndIf
 If *c\peerIdKnown<>1 Or peerBytes<>*c\peerIdBytes : ProcedureReturn #QUIC_FEED_ARGUMENT : EndIf
 If *c\incoming\phase>=1 And *c\incoming\phase<=3 : ProcedureReturn #QUIC_FEED_STATE : EndIf
 If *c\outgoing\phase<>0 And *c\outgoing\phase<>6 : ProcedureReturn #QUIC_FEED_STATE : EndIf
 If *c\acknowledge\phase>=1 And *c\acknowledge\phase<=4 : ProcedureReturn #QUIC_FEED_STATE : EndIf
 If *c\tlsOp\phase<>0 And *c\tlsOp\phase<>2 : ProcedureReturn #QUIC_FEED_STATE : EndIf
 If TlsWorkerBusy()<>0 : ProcedureReturn #TLSWORK_BUSY : EndIf
 If Tls13ContextMatchesBuffers(QuicConnectionBuffer(*c,7),#TLS13_CONTEXT_SIZE,QuicConnectionBuffer(*c,8),QuicConnectionBuffer(*c,9),QuicConnectionBuffer(*c,11))<>1 : ProcedureReturn #QUIC_FEED_STATE : EndIf
 *c\feed\phase=1 : *c\feed\result=0 : *c\feed\level=level : *c\feed\peerBytes=peerBytes : *c\feed\timeout=timeoutUs
 ProcedureReturn 0
EndProcedure
; 0 pending,1 done,negative failure. Each call admits or advances one TLS/key
; operation, parses one parameter, or copies <=256 bytes of Finished output.
; Per-operation timeouts supplement the caller's overall connection deadline.
Procedure.i QuicConnectionTlsStep(*c.QuicConnection)
 Define rc.i,snapshot.i,state.i,config.i,secret.i,*keys.QuicKeys,*s.QuicConnectionSpace
 If quiccf_Valid(*c)=0 : ProcedureReturn #QUIC_FEED_ARGUMENT : EndIf
 If *c\phase<>1 : ProcedureReturn #QUIC_FEED_STATE : EndIf
 If *c\feed\phase=12 : ProcedureReturn 1 : EndIf
 snapshot=QuicConnectionBuffer(*c,7) : config=QuicConnectionBuffer(*c,11)
 If *c\feed\level=0 : *s=@*c\initial : Else : *s=@*c\handshake : EndIf
 Select *c\feed\phase
  Case 1
   rc=QuicTlsOperationBegin(@*c\tlsOp,snapshot,#TLS13_CONTEXT_SIZE,3,@*s\rx,0,0,0,*c\feed\timeout)
   If rc=#TLSWORK_BUSY : ProcedureReturn 0 : EndIf
   If rc<>1 : ProcedureReturn quiccf_Fail(*c,rc) : EndIf
   *c\feed\phase=2
  Case 2
   rc=QuicTlsOperationStep(@*c\tlsOp)
   If rc=0 : ProcedureReturn 0 : EndIf
   If rc<>1 : ProcedureReturn quiccf_Fail(*c,rc) : EndIf
   rc=*c\tlsOp\result
   If rc<0 : ProcedureReturn quiccf_Fail(*c,rc) : EndIf
   *c\feed\phase=1 : If rc=0 : *c\feed\phase=3 : EndIf
  Case 3
   state=Tls13ContextState(snapshot,#TLS13_CONTEXT_SIZE)
   If state>=#TLS13_ST_WAIT_EE And state<=#TLS13_ST_CONNECTED
    If *c\handshake\readKeys\ready<>1 : *c\feed\keyTarget=0 : *c\feed\phase=4 : ProcedureReturn 0 : EndIf
    If *c\handshake\writeKeys\ready<>1 : *c\feed\keyTarget=1 : *c\feed\phase=4 : ProcedureReturn 0 : EndIf
   EndIf
   *c\feed\phase=6
  Case 4
   *keys=@*c\handshake\readKeys
   If *c\feed\keyTarget=1 : *keys=@*c\handshake\writeKeys : EndIf
   If *c\feed\keyTarget=2 : *keys=@*c\appRead : EndIf
   secret=Tls13ContextTrafficSecret(snapshot,#TLS13_CONTEXT_SIZE,Bool(*c\feed\keyTarget<>1),Bool(*c\feed\keyTarget=2))
   rc=QuicTlsOperationBegin(@*c\tlsOp,snapshot,#TLS13_CONTEXT_SIZE,4,@*c\keyjob,*keys,secret,32,*c\feed\timeout)
   If rc=#TLSWORK_BUSY : ProcedureReturn 0 : EndIf
   If rc<>1 : ProcedureReturn quiccf_Fail(*c,rc) : EndIf
   *c\feed\phase=5
  Case 5
   rc=QuicTlsOperationStep(@*c\tlsOp)
   If rc=0 : ProcedureReturn 0 : EndIf
   If rc<>1 : ProcedureReturn quiccf_Fail(*c,rc) : EndIf
   If *c\tlsOp\result<>1 : ProcedureReturn quiccf_Fail(*c,*c\tlsOp\result) : EndIf
   *c\feed\phase=3
  Case 6
   If *c\feed\parametersReady=0 And PeekI(config+40)<>0
    rc=QuicParametersBegin(@*c\params,QuicConnectionBuffer(*c,13),PeekI(config+32),1,QuicConnectionBuffer(*c,14),64)
    If rc<>0 : ProcedureReturn quiccf_Fail(*c,rc) : EndIf
    *c\feed\phase=7
   Else
    *c\feed\phase=8
   EndIf
  Case 7
   rc=QuicParametersStep(@*c\params)
   If rc=0 : ProcedureReturn 0 : EndIf
   If rc<>1 : ProcedureReturn quiccf_Fail(*c,rc) : EndIf
   rc=QuicParametersCheckIds(@*c\params,QuicConnectionBuffer(*c,19),*c\feed\peerBytes,QuicConnectionBuffer(*c,17),8,0,0,0)
   If rc<>1 : ProcedureReturn quiccf_Fail(*c,rc) : EndIf
   *c\feed\parametersReady=1 : *c\feed\phase=8
  Case 8
   If Tls13ContextState(snapshot,#TLS13_CONTEXT_SIZE)=#TLS13_ST_SEND_FINISHED
    If *c\feed\parametersReady<>1 : ProcedureReturn quiccf_Fail(*c,#QUIC_FEED_PARAMETERS) : EndIf
    If *c\appRead\ready<>1 : *c\feed\keyTarget=2 : *c\feed\phase=4 : ProcedureReturn 0 : EndIf
    *c\feed\phase=9
   Else
    *c\feed\phase=12 : ProcedureReturn 1
   EndIf
  Case 9
   rc=QuicTlsOperationBegin(@*c\tlsOp,snapshot,#TLS13_CONTEXT_SIZE,2,@*c\handshake\tx,@*c\tlsOutput,QuicConnectionBuffer(*c,10),2048,*c\feed\timeout)
   If rc=#TLSWORK_BUSY : ProcedureReturn 0 : EndIf
   If rc<>1 : ProcedureReturn quiccf_Fail(*c,rc) : EndIf
   *c\feed\phase=10
  Case 10
   rc=QuicTlsOperationStep(@*c\tlsOp)
   If rc=0 : ProcedureReturn 0 : EndIf
   If rc<>1 : ProcedureReturn quiccf_Fail(*c,rc) : EndIf
   If *c\tlsOp\result<>1 : ProcedureReturn quiccf_Fail(*c,#QUIC_FEED_STATE) : EndIf
   *c\feed\phase=11
  Case 11
   rc=QuicTlsOutputStep(@*c\tlsOutput)
   If rc<0 : ProcedureReturn quiccf_Fail(*c,rc) : EndIf
   If rc=0 : *c\feed\phase=12 : ProcedureReturn 1 : EndIf
  Default : ProcedureReturn #QUIC_FEED_STATE
 EndSelect
 ProcedureReturn 0
EndProcedure

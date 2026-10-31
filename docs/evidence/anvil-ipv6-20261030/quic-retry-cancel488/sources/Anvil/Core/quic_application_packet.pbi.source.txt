; Cooperative ownership of one protected QUIC 1-RTT packet operation.
; Compose quic_crypto and tls_worker first. Caller binds connection/keys/CID,
; supplies the last authenticated PN or a unique outgoing PN, and serializes
; protocol state. Keys and packet remain exclusive/alive until terminal return.
; No UDP or frame processing. Cancellation discards the packet, not its keys.
#QUIC_APP_PACKET_STATE=-3581
#QUIC_APP_PACKET_ARGUMENT=-3582
#QUIC_APP_PACKET_CANCELLED=-3583
Structure QuicApplicationPacket
 worker.TlsWorkerJob
 crypto.QuicPacketJob
 phase.i ; 0 fresh,1 pending,2 terminal result,-1 cancelled
 result.i
 keys.i
 packet.i
 bytes.i
 idBytes.i
 number.i
 encrypt.i
EndStructure
Procedure.i quicap_Span(p.i,n.i)
 ProcedureReturn Bool(p>0 And n>=0 And p<=$7FFFFFFFFFFFFFFF-n)
EndProcedure
Procedure.i quicap_Overlap(a.i,n.i,b.i,m.i)
 ProcedureReturn Bool(a<b+m And b<a+n)
EndProcedure
Procedure.i quicap_Entry()
 Define *op.QuicApplicationPacket,rc.i
 *op=ScArgument()
 rc=QuicPacketJobBegin(@*op\crypto,*op\keys,*op\packet,*op\bytes,*op\idBytes,*op\number,*op\encrypt)
 While rc=0
  rc=QuicPacketJobStep(@*op\crypto)
  If rc=0 : TlsWorkerCheckpoint() : EndIf
 Wend
 *op\result=rc
 ProcedureReturn 1
EndProcedure
; 0 admitted,negative refusal with descriptor and packet unchanged.
Procedure.i QuicApplicationPacketBegin(*op.QuicApplicationPacket,*keys.QuicKeys,packet.i,bytes.i,idBytes.i,number.i,encrypt.i)
 Define h.QuicPacketHeader,rc.i
 If quicap_Span(*op,SizeOf(QuicApplicationPacket))=0 Or quicap_Span(*keys,SizeOf(QuicKeys))=0 Or quicap_Span(packet,bytes)=0 : ProcedureReturn #QUIC_APP_PACKET_ARGUMENT : EndIf
 If bytes<1 Or bytes>#QUIC_CRYPTO_MAX_PACKET Or idBytes<0 Or idBytes>20 Or encrypt<0 Or encrypt>1 : ProcedureReturn #QUIC_APP_PACKET_ARGUMENT : EndIf
 If number< -1 Or number>#QUIC_INTEGER_MAX Or (encrypt=1 And number<0) : ProcedureReturn #QUIC_APP_PACKET_ARGUMENT : EndIf
 If quicap_Overlap(*op,SizeOf(QuicApplicationPacket),*keys,SizeOf(QuicKeys)) Or quicap_Overlap(*op,SizeOf(QuicApplicationPacket),packet,bytes) Or quicap_Overlap(*keys,SizeOf(QuicKeys),packet,bytes) : ProcedureReturn #QUIC_APP_PACKET_ARGUMENT : EndIf
 If (*op\phase<>0 And *op\phase<>2) Or *op\crypto\phase<>0 Or *keys\ready<>1 : ProcedureReturn #QUIC_APP_PACKET_STATE : EndIf
 rc=QuicPacketRead(@h,packet,bytes,idBytes)
 If rc<>1 : ProcedureReturn rc : EndIf
 If h\kind<>#QUIC_PACKET_SHORT : ProcedureReturn #QUIC_APP_PACKET_ARGUMENT : EndIf
 rc=TlsWorkerBegin(@*op\worker,@quicap_Entry,*op)
 If rc<>1 : ProcedureReturn rc : EndIf
 *op\phase=1 : *op\result=0 : *op\keys=*keys : *op\packet=packet : *op\bytes=bytes
 *op\idBytes=idBytes : *op\number=number : *op\encrypt=encrypt
 ProcedureReturn 0
EndProcedure
; Stop/reap first. If stopping refuses, retain all ownership and retry/diagnose.
Procedure.i QuicApplicationPacketCancel(*op.QuicApplicationPacket)
 Define rc.i
 If quicap_Span(*op,SizeOf(QuicApplicationPacket))=0 : ProcedureReturn #QUIC_APP_PACKET_ARGUMENT : EndIf
 If *op\phase<>1 : ProcedureReturn #QUIC_APP_PACKET_STATE : EndIf
 If *op\worker\task<>0
  rc=TlsWorkerCancel(@*op\worker) : If rc<>1 : ProcedureReturn rc : EndIf
 EndIf
 If *op\crypto\phase<>0
  rc=QuicPacketJobCancel(@*op\crypto) : If rc<>#QUIC_CRYPTO_CANCELLED : ProcedureReturn rc : EndIf
 EndIf
 *op\phase=-1 : *op\result=#QUIC_APP_PACKET_CANCELLED
 ProcedureReturn #QUIC_APP_PACKET_CANCELLED
EndProcedure
; 0 pending,1 authenticated/encrypted,negative failure. Terminal reads stable.
; Caller must not consume plaintext until1 or reuse a cancelled packet.
Procedure.i QuicApplicationPacketStep(*op.QuicApplicationPacket)
 Define rc.i,n.i
 If quicap_Span(*op,SizeOf(QuicApplicationPacket))=0 : ProcedureReturn #QUIC_APP_PACKET_ARGUMENT : EndIf
 If *op\phase=2 Or *op\phase=-1 : ProcedureReturn *op\result : EndIf
 If *op\phase<>1 : ProcedureReturn #QUIC_APP_PACKET_STATE : EndIf
 rc=TlsWorkerStep(@*op\worker)
 If rc=0 : ProcedureReturn 0 : EndIf
 If rc<>1
  n=QuicApplicationPacketCancel(*op)
  If n<>#QUIC_APP_PACKET_CANCELLED : ProcedureReturn n : EndIf
  *op\result=rc : ProcedureReturn rc
 EndIf
 *op\phase=2
 ProcedureReturn *op\result
EndProcedure

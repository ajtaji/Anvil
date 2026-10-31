; Shared QUIC TLS operation scheduling, with explicit connection snapshots.
; Include full TLS, tls_context_worker, quic_tls_send and quic_tls_receive.
; Serialized dispatcher only. Initialized streams, descriptors, snapshot and
; referenced buffers remain exclusive/alive until completion or cancellation.
; No network calls or wait loops run here. The dispatcher owns fairness, UDP,
; connection close, packet/key lifecycle and overall handshake deadlines.
#QUIC_OP_STATE=-3501
#QUIC_OP_CANCELLED=-3502
#QUIC_OP_TIMEOUT=-3503
#QUIC_OP_TLS=-3504
Structure QuicTlsOperation
 context.TlsContextWorkerJob
 phase.i ; 0 fresh, 1 pending, 2 completed, -1 terminal abandonment
 kind.i ; 1 key share, 2 output Begin, 3 receive feed, 4 QUIC traffic keys
 result.i
 started.i
 timeout.i
 stream.i
 outputJob.i
 output.i
 capacity.i
EndStructure
Procedure.i quicop_Span(p.i,n.i)
 ProcedureReturn Bool(p>0 And n>=0 And p<=$7FFFFFFFFFFFFFFF-n)
EndProcedure
Procedure.i quicop_Overlap(a.i,n.i,b.i,m.i)
 ProcedureReturn Bool(a<b+m And b<a+n)
EndProcedure
Procedure.i quicop_Storage(op.i,snapshot.i,size.i,p.i,n.i)
 If quicop_Span(p,n)=0 : ProcedureReturn 0 : EndIf
 If quicop_Overlap(op,SizeOf(QuicTlsOperation),p,n) Or quicop_Overlap(snapshot,size,p,n) : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i quicop_Entry()
 Define *op.QuicTlsOperation,rc.i
 *op=ScArgument()
 Select *op\kind
  Case 1
   *op\result=Tls13NewKeyShare()
   If *op\result<>1 : *op\result=#QUIC_OP_TLS : EndIf
  Case 2 : *op\result=QuicTlsOutputBegin(*op\outputJob,*op\stream,*op\output,*op\capacity)
  Case 3 : *op\result=QuicCryptoTlsStep(*op\stream)
  Case 4
   rc=QuicTrafficKeysBegin(*op\stream,*op\outputJob,*op\output,*op\capacity)
   While rc=0
    rc=QuicKeyJobStep(*op\stream)
    If rc=0 : TlsWorkerCheckpoint() : EndIf
   Wend
   *op\result=rc
  Default : *op\result=#QUIC_OP_STATE
 EndSelect
 ProcedureReturn 1
EndProcedure
; Admission refuses without changing the operation, snapshot or TLS globals.
; Success reserves the shared worker; no cryptographic operation runs yet.
Procedure.i QuicTlsOperationBegin(*op.QuicTlsOperation,snapshot.i,size.i,kind.i,stream.i,outputJob.i,output.i,capacity.i,timeoutUs.i)
 Define rc.i,*rx.QuicCryptoRx,*tx.QuicCryptoTx
 If quicop_Span(*op,SizeOf(QuicTlsOperation))=0 Or quicop_Span(snapshot,size)=0 Or size<#TLS13_CONTEXT_SIZE Or timeoutUs<=0 : ProcedureReturn #QUIC_OP_STATE : EndIf
 If quicop_Overlap(*op,SizeOf(QuicTlsOperation),snapshot,size) Or (*op\phase<>0 And *op\phase<>2) : ProcedureReturn #QUIC_OP_STATE : EndIf
 Select kind
  Case 1
   If stream<>0 Or outputJob<>0 Or output<>0 Or capacity<>0 : ProcedureReturn #QUIC_OP_STATE : EndIf
  Case 2
   If quicop_Storage(*op,snapshot,size,stream,SizeOf(QuicCryptoTx))=0 Or quicop_Storage(*op,snapshot,size,outputJob,SizeOf(QuicTlsOutput))=0 Or quicop_Storage(*op,snapshot,size,output,capacity)=0 : ProcedureReturn #QUIC_OP_STATE : EndIf
   *tx=stream
   If quicop_Storage(*op,snapshot,size,*tx\data,*tx\capacity)=0 Or quicop_Storage(*op,snapshot,size,*tx\states,*tx\capacity/4)=0 : ProcedureReturn #QUIC_OP_STATE : EndIf
  Case 3
   If outputJob<>0 Or output<>0 Or capacity<>0 : ProcedureReturn #QUIC_OP_STATE : EndIf
   If quicop_Storage(*op,snapshot,size,stream,SizeOf(QuicCryptoRx))=0 : ProcedureReturn #QUIC_OP_STATE : EndIf
   *rx=stream
   If quicop_Storage(*op,snapshot,size,*rx\data,*rx\capacity)=0 Or quicop_Storage(*op,snapshot,size,*rx\bits,*rx\capacity/8)=0 : ProcedureReturn #QUIC_OP_STATE : EndIf
  Case 4
   If capacity<>32 Or quicop_Span(output,32)=0 : ProcedureReturn #QUIC_OP_STATE : EndIf
   If quicop_Storage(*op,snapshot,size,stream,SizeOf(QuicKeyJob))=0 Or quicop_Storage(*op,snapshot,size,outputJob,SizeOf(QuicKeys))=0 : ProcedureReturn #QUIC_OP_STATE : EndIf
   If quicop_Overlap(stream,SizeOf(QuicKeyJob),outputJob,SizeOf(QuicKeys)) Or quicop_Overlap(output,32,stream,SizeOf(QuicKeyJob)) Or quicop_Overlap(output,32,outputJob,SizeOf(QuicKeys)) Or quicop_Overlap(output,32,*op,SizeOf(QuicTlsOperation)) : ProcedureReturn #QUIC_OP_STATE : EndIf
  Default : ProcedureReturn #QUIC_OP_STATE
 EndSelect
 rc=TlsContextWorkerBegin(@*op\context,snapshot,size,@quicop_Entry,*op)
 If rc<>1 : ProcedureReturn rc : EndIf
 *op\phase=1 : *op\kind=kind : *op\result=0 : *op\started=HwMicros() : *op\timeout=timeoutUs
 *op\stream=stream : *op\outputJob=outputJob : *op\output=output : *op\capacity=capacity
 ProcedureReturn 1
EndProcedure
; Stop first, then invalidate snapshot and transport work. A refusal to stop
; leaves ownership intact: caller must retry/diagnose, never release buffers.
Procedure.i quicop_Abandon(*op.QuicTlsOperation,reason.i)
 Define rc.i,*out.QuicTlsOutput,*tx.QuicCryptoTx
 If *op\context\worker\task<>0
  rc=TlsContextWorkerCancel(@*op\context)
  If rc<>1 : ProcedureReturn rc : EndIf
 Else
  rc=Tls13ContextWipe(*op\context\snapshot,*op\context\capacity)
 EndIf
 If *op\kind=2
  *out=*op\outputJob : *tx=*op\stream
  If *out\phase=1 Or *out\phase=3 : rc=QuicTlsOutputAbandon(*out) : EndIf
  ; Also forbid sending queued output when timeout/cancel precedes Begin.
  rc=QuicCryptoTxAbandon(*tx)
 ElseIf *op\kind=3
  rc=QuicCryptoTlsAbandon(*op\stream)
 ElseIf *op\kind=4
  QuicKeyJobCancel(*op\stream) : QuicKeysWipe(*op\outputJob)
 EndIf
 *op\phase=-1 : *op\result=reason
 ProcedureReturn reason
EndProcedure
Procedure.i QuicTlsOperationCancel(*op.QuicTlsOperation)
 If quicop_Span(*op,SizeOf(QuicTlsOperation))=0 : ProcedureReturn #QUIC_OP_STATE : EndIf
 If *op\phase<>1 : ProcedureReturn #QUIC_OP_STATE : EndIf
 ProcedureReturn quicop_Abandon(*op,#QUIC_OP_CANCELLED)
EndProcedure
; 0 pending, 1 completed (read result), negative refusal or abandonment.
; Completed protocol errors remain in result for caller diagnosis/retry rules.
; Deadlines are checked before AND after a soft slice, not by preemption.
Procedure.i QuicTlsOperationStep(*op.QuicTlsOperation)
 Define rc.i
 If quicop_Span(*op,SizeOf(QuicTlsOperation))=0 : ProcedureReturn #QUIC_OP_STATE : EndIf
 If *op\phase=2 : ProcedureReturn 1 : EndIf
 If *op\phase=-1 : ProcedureReturn *op\result : EndIf
 If *op\phase<>1 : ProcedureReturn #QUIC_OP_STATE : EndIf
 If HwMicros()-*op\started>=*op\timeout : ProcedureReturn quicop_Abandon(*op,#QUIC_OP_TIMEOUT) : EndIf
 rc=TlsContextWorkerStep(@*op\context)
 If rc<0 : ProcedureReturn rc : EndIf
 If HwMicros()-*op\started>=*op\timeout : ProcedureReturn quicop_Abandon(*op,#QUIC_OP_TIMEOUT) : EndIf
 If rc=1 : *op\phase=2 : EndIf
 ProcedureReturn rc
EndProcedure

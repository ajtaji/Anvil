; Cooperative TLS operation with explicit connection-state switching.
; Include the complete TLS implementation, tls13_context and tls_worker first.
; This is an execution adapter, not a connection/transport lifecycle manager.
; The supplied snapshot is initialized by Tls13ContextSave before Begin. Its
; referenced buffers and this descriptor remain exclusive/alive until terminal.
; All crypto users must honor the underlying worker owner across suspension.
; The caller owns transport poisoning/close after cancellation or failure.
Structure TlsContextWorkerJob
 worker.TlsWorkerJob
 snapshot.i
 capacity.i
EndStructure
Global tlsctxw_inside.i
Global Dim tlsctxw_caller.a[#TLS13_CONTEXT_SIZE]
Procedure.i tlsctxw_Span(p.i,n.i)
 If p<=0 Or n<0 Or p>$7FFFFFFFFFFFFFFF-n : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i tlsctxw_Overlap(a.i,n.i,b.i,m.i)
 ProcedureReturn Bool(a<b+m And b<a+n)
EndProcedure
Procedure.i tlsctxw_Storage(job.i,snapshot.i,capacity.i)
 If tlsctxw_Span(job,SizeOf(TlsContextWorkerJob))=0 Or capacity<#TLS13_CONTEXT_SIZE Or tlsctxw_Span(snapshot,capacity)=0 : ProcedureReturn 0 : EndIf
 If tlsctxw_Overlap(job,SizeOf(TlsContextWorkerJob),snapshot,capacity) Or tlsctxw_Overlap(snapshot,capacity,@tlsctxw_caller[0],#TLS13_CONTEXT_SIZE) Or tlsctxw_Overlap(job,SizeOf(TlsContextWorkerJob),@tlsctxw_caller[0],#TLS13_CONTEXT_SIZE) : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
; Admission does not select or change TLS globals. Refusal leaves storage intact.
Procedure.i TlsContextWorkerBegin(*job.TlsContextWorkerJob,snapshot.i,capacity.i,entry.i,argument.i)
 Define rc.i
 If tlsctxw_inside<>0 : ProcedureReturn #TLSWORK_BUSY : EndIf
 If tlsctxw_Storage(*job,snapshot,capacity)=0 : ProcedureReturn #TLSWORK_STATE : EndIf
 rc=TlsWorkerBegin(@*job\worker,entry,argument)
 If rc<>1 : ProcedureReturn rc : EndIf
 *job\snapshot=snapshot : *job\capacity=capacity
 ProcedureReturn 1
EndProcedure
; 0 yielded, 1 complete, negative refused/faulted. Protocol results remain in
; caller-owned storage. Foreground TLS globals are restored on every return.
; Saving/restoring metadata never releases the underlying crypto scratch owner.
Procedure.i TlsContextWorkerStep(*job.TlsContextWorkerJob)
 Define rc.i,n.i,snapshot.i,capacity.i
 If tlsctxw_inside<>0 : ProcedureReturn #TLSWORK_BUSY : EndIf
 If tlsctxw_Span(*job,SizeOf(TlsContextWorkerJob))=0 : ProcedureReturn #TLSWORK_STATE : EndIf
 If TlsWorkerOwns(@*job\worker)=0 : ProcedureReturn #TLSWORK_OWNER : EndIf
 snapshot=*job\snapshot : capacity=*job\capacity
 If tlsctxw_Storage(*job,snapshot,capacity)=0 : ProcedureReturn #TLSWORK_STATE : EndIf
 tlsctxw_inside=1
 n=Tls13ContextSave(@tlsctxw_caller[0],#TLS13_CONTEXT_SIZE)
 n=Tls13ContextRestore(snapshot,capacity)
 rc=TlsWorkerStep(@*job\worker)
 n=Tls13ContextSave(snapshot,capacity)
 n=Tls13ContextRestore(@tlsctxw_caller[0],#TLS13_CONTEXT_SIZE)
 n=Tls13ContextWipe(@tlsctxw_caller[0],#TLS13_CONTEXT_SIZE)
 tlsctxw_inside=0
 ProcedureReturn rc
EndProcedure
; Cancelling a partially executed TLS operation invalidates its connection.
; Wipe only that snapshot after its coroutine is stopped and reaped. Do not
; wipe the currently selected foreground connection or another owner's state.
Procedure.i TlsContextWorkerCancel(*job.TlsContextWorkerJob)
 Define rc.i,n.i
 If tlsctxw_inside<>0 : ProcedureReturn #TLSWORK_BUSY : EndIf
 If tlsctxw_Span(*job,SizeOf(TlsContextWorkerJob))=0 : ProcedureReturn #TLSWORK_STATE : EndIf
 If TlsWorkerOwns(@*job\worker)=0 : ProcedureReturn #TLSWORK_OWNER : EndIf
 If tlsctxw_Storage(*job,*job\snapshot,*job\capacity)=0 : ProcedureReturn #TLSWORK_STATE : EndIf
 rc=TlsWorkerCancel(@*job\worker)
 If rc<>1 : ProcedureReturn rc : EndIf
 n=Tls13ContextWipe(*job\snapshot,*job\capacity)
 ProcedureReturn 1
EndProcedure

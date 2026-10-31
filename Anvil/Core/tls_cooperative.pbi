; Private continuation of the tls_client module: tlsc_ owns both files.
; Stream TLS adapter for the shared, exclusive TLS/QUIC crypto worker.
XIncludeFile "Anvil/Core/tls_worker.pbi"
Global tlsw_job.TlsWorkerJob
Global tlsw_slot.i,tlsw_fault.i
Procedure.i tlsc_RunCooperative()
 tlsc_AdvanceWork()
 ProcedureReturn 1
EndProcedure
Procedure tlsw_Cancel(h.i)
 If tlsw_job\task=0 : ProcedureReturn : EndIf
 If tlsc_handles[tlsw_slot]<>h : ProcedureReturn : EndIf
 If TlsWorkerCancel(@tlsw_job)<>1 : tlsw_fault=1 : ProcedureReturn : EndIf
 TlsRootsCancelLoad()
EndProcedure
Procedure tlsw_Advance()
 Define caller.i,rc.i
 caller=tlsc_slot
 If tlsw_fault<>0 Or TlsWorkerFaulted()<>0
  tlsc_Refuse(#SVC_EIO,"TLS cooperative context failed its ownership or stack check")
  ProcedureReturn
 EndIf
 If tlsw_job\task=0
  ; Another protocol retains scratch across suspension. Defer without touching
  ; its context; the dispatcher must continue servicing that owner fairly.
  If TlsWorkerBusy()<>0 : ProcedureReturn : EndIf
  tlsw_slot=caller : rc=TlsWorkerBegin(@tlsw_job,@tlsc_RunCooperative,0)
  If rc<>1
   tlsc_Refuse(#SVC_EBUSY,"TLS cooperative worker could not acquire a task context")
   ProcedureReturn
  EndIf
 EndIf
 tlsc_Select(tlsw_slot)
 If tlsc_state=#TLSC_PREPARE Or tlsc_state=#TLSC_RESOLVING Or tlsc_state=#TLSC_TCP Or tlsc_state=#TLSC_HS
  If ((millis()-tlsc_t0) & $FFFFFFFF)>#TLSC_HS_MS
   tlsw_Cancel(tlsc_handles[tlsw_slot])
   tlsc_Refuse(#SVC_EIO,"TLS handshake deadline expired during cooperative arithmetic")
   tlsc_Select(caller) : ProcedureReturn
  EndIf
 EndIf
 rc=TlsWorkerStep(@tlsw_job)
 If rc<0
  tlsw_fault=1 : TlsRootsCancelLoad()
  tlsc_Refuse(#SVC_EIO,"TLS cooperative worker failed")
 EndIf
 tlsc_Select(caller)
EndProcedure
; Install while stream TLS and the shared worker are idle. Failure leaves
; the previous synchronous driver in place for diagnosis.
Procedure.i TlsCooperativeInstall(code.i,bytes.i)
 Define i.i
 If tlsw_job\task<>0 Or tlsc_advanceHook<>0 : ProcedureReturn 0 : EndIf
 For i=0 To #TLSC_CONNECTIONS-1
  If tlsc_handles[i]<>0 : ProcedureReturn 0 : EndIf
 Next
 If TlsWorkerInstall(code,bytes)=0 : ProcedureReturn 0 : EndIf
 tlsc_profileHook=@TlsWorkerShowProfile
 tlsw_fault=0 : tlsc_advanceHook=@tlsw_Advance : tlsc_closeHook=@tlsw_Cancel
 ProcedureReturn 1
EndProcedure

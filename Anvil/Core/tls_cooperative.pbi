; Private continuation of the tls_client module: tlsc_ owns both files.
; Shared TLS cooperative arithmetic driver. Requires tls_client, crypto jobs,
; scheduler and cooperative_a64. One worker exclusively owns crypto scratch.
; It uses the calling core/EL/address space and needs no timer or IRQ changes.
Global tlsw_handle.i
Global tlsw_slot.i
Global tlsw_fault.i
Global tlsw_sliceStart.i
Global tlsw_sliceTicks.i

Procedure tlsw_ClearHooks()
 X509PauseHook=0 : TlsRootsPauseHook=0
 EcdsaVerifyHook=0 : RsaPublicHook=0 : X25519ComputeHook=0
EndProcedure

Procedure.i tlsw_YieldDue()
 If A64CounterReadOrdered()-tlsw_sliceStart<tlsw_sliceTicks : ProcedureReturn 1 : EndIf
 ProcedureReturn ScYield()
EndProcedure

Procedure.i tlsw_Ecdsa(curve.i,hash.i,hashBytes.i,key.i,keyBytes.i,sig.i,sigBytes.i)
 Define rc.i,i.i,raw.i
 If curve=#ECDSA_CURVE_P256
  rc=EcdsaJobBegin(hash,hashBytes,key,keyBytes,sig,sigBytes,1)
  While rc=0
   If tlsw_YieldDue()=0 : EcdsaJobCancel() : ProcedureReturn -1 : EndIf
   rc=EcdsaJobStep()
  Wend
  If rc<0 : ProcedureReturn -1 : EndIf
  ProcedureReturn EcdsaJobResult
 EndIf
 EcdsaLastErr=#ECDSA_ERR_CURVE
 If curve<>#ECDSA_CURVE_P384 And curve<>#ECDSA_CURVE_P521 : ProcedureReturn -1 : EndIf
 EcdsaLastErr=#ECDSA_ERR_MALFORMED
 If sigBytes<=0 Or sigBytes>#ECDSA_SIGMAX : ProcedureReturn 0 : EndIf
 For i=0 To sigBytes-1 : PokeA(@EcdsaRsig+i,PeekA(sig+i)) : Next
 raw=EcdsaAsn1ToRaw(@EcdsaRsig,sigBytes)
 If raw=0 : ProcedureReturn 0 : EndIf
 rc=EcpJobBegin(curve,hash,hashBytes,key,keyBytes,@EcdsaRsig,raw)
 While rc=0
  If tlsw_YieldDue()=0 : EcpJobCancel() : ProcedureReturn -1 : EndIf
  rc=EcpJobStep()
 Wend
 EcdsaLastErr=EcpLastErr
 If rc<0 : ProcedureReturn -1 : EndIf
 ProcedureReturn EcpJobResult
EndProcedure

Procedure.i tlsw_Rsa(out.i,bytes.i,modulus.i,modBytes.i,exponent.i,expBytes.i)
 Define rc.i,i.i
 rc=RsaJobBegin(out,bytes,modulus,modBytes,exponent,expBytes)
 While rc=0
  If tlsw_YieldDue()=0 : RsaJobCancel() : ProcedureReturn 0 : EndIf
  rc=RsaJobStep()
 Wend
 If rc<0 Or RsaJobResult<>1 : ProcedureReturn 0 : EndIf
 For i=0 To bytes-1 : PokeA(out+i,RsaSig[i]) : Next
 ProcedureReturn 1
EndProcedure

Procedure.i tlsw_X25519(out.i,scalar.i,point.i)
 Define rc.i
 rc=X25519JobBegin(out,scalar,point)
 While rc=0
  If tlsw_YieldDue()=0 : X25519JobCancel() : ProcedureReturn 0 : EndIf
  rc=X25519JobStep()
 Wend
 ProcedureReturn Bool(rc=1)
EndProcedure

Procedure.i tlsc_RunCooperative()
 X509PauseHook=@tlsw_YieldDue : TlsRootsPauseHook=@tlsw_YieldDue
 EcdsaVerifyHook=@tlsw_Ecdsa : RsaPublicHook=@tlsw_Rsa : X25519ComputeHook=@tlsw_X25519
 tlsc_AdvanceWork()
 tlsw_ClearHooks()
 ProcedureReturn 1
EndProcedure

Procedure tlsw_Cancel(h.i)
 Define rc.i
 If tlsw_handle=0 : ProcedureReturn : EndIf
 If tlsc_handles[tlsw_slot]<>h : ProcedureReturn : EndIf
 rc=SchedCancel(tlsw_handle)
 If rc=0 : tlsw_fault=1 : ProcedureReturn : EndIf
 rc=ScReap(tlsw_handle)
 If rc=0 : tlsw_fault=1 : ProcedureReturn : EndIf
 tlsw_handle=0 : tlsw_ClearHooks()
 EcdsaJobCancel() : EcpJobCancel() : RsaJobCancel() : X25519JobCancel()
EndProcedure

Procedure tlsw_Advance()
 Define caller.i,ran.i,state.i,rc.i
 caller=tlsc_slot
 If tlsw_fault<>0
  tlsc_Refuse(#SVC_EIO,"TLS cooperative context failed its ownership or stack check")
  ProcedureReturn
 EndIf
 If tlsw_handle=0
  tlsw_slot=caller : tlsw_handle=ScCreate(@tlsc_RunCooperative,0)
  If tlsw_handle=0
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
 tlsw_sliceStart=A64CounterReadOrdered()
 ran=ScRunOne() : state=SchedState(tlsw_handle)
 If state=#SCHED_DONE Or state=#SCHED_CANCELLED
  If state<>#SCHED_DONE Or ScResult(tlsw_handle)<>1
   tlsw_fault=1 : tlsc_Refuse(#SVC_EIO,"TLS cooperative worker failed")
  EndIf
  rc=ScReap(tlsw_handle)
  If rc=0 : tlsw_fault=1 : EndIf
  tlsw_handle=0 : tlsw_ClearHooks()
 EndIf
 tlsc_Select(caller)
EndProcedure

; Composition supplies its executable interval. Install only while TLS is
; idle. Failure leaves the previous synchronous driver in place for diagnosis.
Procedure.i TlsCooperativeInstall(code.i,bytes.i)
 Define i.i
 If tlsw_handle<>0 Or tlsc_advanceHook<>0 : ProcedureReturn 0 : EndIf
 For i=0 To #TLSC_CONNECTIONS-1
  If tlsc_handles[i]<>0 : ProcedureReturn 0 : EndIf
 Next
 tlsw_sliceTicks=A64CounterFrequency()/500
 If tlsw_sliceTicks<1 : ProcedureReturn 0 : EndIf
 If ScConfigure(code,bytes)=0 : ProcedureReturn 0 : EndIf
 tlsw_fault=0 : tlsc_advanceHook=@tlsw_Advance : tlsc_closeHook=@tlsw_Cancel
 ProcedureReturn 1
EndProcedure

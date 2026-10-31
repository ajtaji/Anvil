; Private continuation of the tls_client module: tlsc_ owns both files.
; Shared TLS cooperative arithmetic driver. Requires tls_client, crypto jobs,
; scheduler and cooperative_a64. One worker exclusively owns crypto scratch.
; It uses the calling core/EL/address space and needs no timer or IRQ changes.
Global tlsw_handle.i
Global tlsw_slot.i
Global tlsw_fault.i
Global tlsw_sliceStart.i
Global tlsw_sliceTicks.i
Global tlsw_gapStart.i
Global tlsw_gapMax.i
Global tlsw_gapFrom.i
Global tlsw_gapTo.i
Global tlsw_lastCheck.i
; Interval endpoints: -1 worker entry, 0 roots, 1 X509, 2 P256, 3 wide EC,
; 4 RSA, 5 X25519, 6 decrypt, 7 encrypt, 8 worker return, 9 transcript hashing, 10 key-share setup.
Procedure tlsw_CheckGap(kind.i)
 Define now.i,gap.i
 now=HwMicros() : gap=now-tlsw_gapStart : tlsw_gapStart=now
 If gap>tlsw_gapMax
  tlsw_gapMax=gap : tlsw_gapFrom=tlsw_lastCheck : tlsw_gapTo=kind
 EndIf
 tlsw_lastCheck=kind
EndProcedure
Global Dim tlsw_jobCount.i[12]
Global Dim tlsw_jobTotal.i[12]
Global Dim tlsw_jobMax.i[12]

; These spans contain one atomic Begin/Step and never a cooperative yield.
Procedure tlsw_JobTime(kind.i,started.i)
 Define elapsed.i
 elapsed=HwMicros()-started
 tlsw_jobCount[kind]=tlsw_jobCount[kind]+1
 tlsw_jobTotal[kind]=tlsw_jobTotal[kind]+elapsed
 If elapsed>tlsw_jobMax[kind] : tlsw_jobMax[kind]=elapsed : EndIf
EndProcedure

Procedure tlsw_ShowProfile()
 Define i.i
 PrintN("TLS arithmetic steps (calls / total us / maximum us):")
 For i=0 To 11
  Select i
   Case 0 : Print("  P256 begin: ")
   Case 1 : Print("  P256 step: ")
   Case 2 : Print("  P384/P521 begin: ")
   Case 3 : Print("  P384/P521 step: ")
   Case 4 : Print("  RSA begin: ")
   Case 5 : Print("  RSA step: ")
   Case 6 : Print("  X25519 begin: ")
   Case 7 : Print("  X25519 step: ")
   Case 8 : Print("  GCM decrypt begin: ")
   Case 9 : Print("  GCM decrypt step: ")
   Case 10 : Print("  GCM encrypt begin: ")
   Case 11 : Print("  GCM encrypt step: ")
  EndSelect
  PrintDec(tlsw_jobCount[i]) : Print(" / ") : PrintDec(tlsw_jobTotal[i]) : Print(" / ") : PrintDec(tlsw_jobMax[i]) : PrintNl()
 Next
 Print("TLS longest interval without a yield check, microseconds: ") : PrintDec(tlsw_gapMax) : PrintNl()
 Print("TLS longest interval endpoints: ") : PrintDec(tlsw_gapFrom) : Print(" -> ") : PrintDec(tlsw_gapTo) : PrintNl()
EndProcedure

Procedure tlsw_ClearHooks()
 X509PauseHook=0 : TlsRootsPauseHook=0 : TlsRecDecryptHook=0 : TlsRecEncryptHook=0 : Tls13PauseHook=0 : Tls13SetupPauseHook=0
 EcdsaVerifyHook=0 : RsaPublicHook=0 : X25519ComputeHook=0
EndProcedure

Procedure.i tlsw_YieldKind(kind.i)
 tlsw_CheckGap(kind)
 If A64CounterReadOrdered()-tlsw_sliceStart<tlsw_sliceTicks : ProcedureReturn 1 : EndIf
 ProcedureReturn ScYield()
EndProcedure
Procedure.i tlsw_RootYield()
 ProcedureReturn tlsw_YieldKind(0)
EndProcedure
Procedure.i tlsw_SetupYield()
 ProcedureReturn tlsw_YieldKind(10)
EndProcedure
Procedure.i tlsw_TranscriptYield()
 ProcedureReturn tlsw_YieldKind(9)
EndProcedure
Procedure.i tlsw_X509Yield()
 ProcedureReturn tlsw_YieldKind(1)
EndProcedure

Procedure.i tlsw_Ecdsa(curve.i,hash.i,hashBytes.i,key.i,keyBytes.i,sig.i,sigBytes.i)
 Define started.i
 Define rc.i,i.i,raw.i
 If curve=#ECDSA_CURVE_P256
  started=HwMicros() : rc=EcdsaJobBegin(hash,hashBytes,key,keyBytes,sig,sigBytes,1) : tlsw_JobTime(0,started)
  While rc=0
   If tlsw_YieldKind(2)=0 : EcdsaJobCancel() : ProcedureReturn -1 : EndIf
   started=HwMicros() : rc=EcdsaJobStep() : tlsw_JobTime(1,started)
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
 started=HwMicros() : rc=EcpJobBegin(curve,hash,hashBytes,key,keyBytes,@EcdsaRsig,raw) : tlsw_JobTime(2,started)
 While rc=0
  If tlsw_YieldKind(3)=0 : EcpJobCancel() : ProcedureReturn -1 : EndIf
  started=HwMicros() : rc=EcpJobStep() : tlsw_JobTime(3,started)
 Wend
 EcdsaLastErr=EcpLastErr
 If rc<0 : ProcedureReturn -1 : EndIf
 ProcedureReturn EcpJobResult
EndProcedure

Procedure.i tlsw_Rsa(out.i,bytes.i,modulus.i,modBytes.i,exponent.i,expBytes.i)
 Define started.i
 Define rc.i,i.i
 started=HwMicros() : rc=RsaJobBegin(out,bytes,modulus,modBytes,exponent,expBytes) : tlsw_JobTime(4,started)
 While rc=0
  If tlsw_YieldKind(4)=0 : RsaJobCancel() : ProcedureReturn 0 : EndIf
  started=HwMicros() : rc=RsaJobStep() : tlsw_JobTime(5,started)
 Wend
 If rc<0 Or RsaJobResult<>1 : ProcedureReturn 0 : EndIf
 For i=0 To bytes-1 : PokeA(out+i,RsaSig[i]) : Next
 ProcedureReturn 1
EndProcedure

Procedure.i tlsw_X25519(out.i,scalar.i,point.i)
 Define started.i
 Define rc.i
 started=HwMicros() : rc=X25519JobBegin(out,scalar,point) : tlsw_JobTime(6,started)
 While rc=0
  If tlsw_YieldKind(5)=0 : X25519JobCancel() : ProcedureReturn 0 : EndIf
  started=HwMicros() : rc=X25519JobStep() : tlsw_JobTime(7,started)
 Wend
 ProcedureReturn Bool(rc=1)
EndProcedure

Procedure.i tlsw_GcmDecrypt(key.i,nonce.i,aad.i,aadBytes.i,cipher.i,bytes.i,plain.i,tag.i)
 Define started.i
 Define rc.i
 started=HwMicros() : rc=GcmJobBeginDecrypt(key,16,nonce,aad,aadBytes,cipher,bytes,plain,tag) : tlsw_JobTime(8,started)
 While rc=0
  If tlsw_YieldKind(6)=0 : GcmJobCancel() : ProcedureReturn 0 : EndIf
  started=HwMicros() : rc=GcmJobStep() : tlsw_JobTime(9,started)
 Wend
 If rc<>1 Or GcmJobResult<>1 : ProcedureReturn 0 : EndIf
 ProcedureReturn $FFFFFFFF
EndProcedure

Procedure.i tlsw_GcmEncrypt(key.i,nonce.i,aad.i,aadBytes.i,plain.i,bytes.i,cipher.i,tag.i)
 Define started.i
 Define rc.i
 started=HwMicros() : rc=GcmJobBeginEncrypt(key,16,nonce,aad,aadBytes,plain,bytes,cipher,tag) : tlsw_JobTime(10,started)
 While rc=0
  If tlsw_YieldKind(7)=0 : GcmJobCancel() : ProcedureReturn 0 : EndIf
  started=HwMicros() : rc=GcmJobStep() : tlsw_JobTime(11,started)
 Wend
 ProcedureReturn Bool(rc=1 And GcmJobResult=1)
EndProcedure


Procedure tlsw_SetHooks()
 X509PauseHook=@tlsw_X509Yield : TlsRootsPauseHook=@tlsw_RootYield : TlsRecDecryptHook=@tlsw_GcmDecrypt : TlsRecEncryptHook=@tlsw_GcmEncrypt : Tls13PauseHook=@tlsw_TranscriptYield : Tls13SetupPauseHook=@tlsw_SetupYield
 EcdsaVerifyHook=@tlsw_Ecdsa : RsaPublicHook=@tlsw_Rsa : X25519ComputeHook=@tlsw_X25519
EndProcedure

Procedure.i tlsc_RunCooperative()
 tlsw_SetHooks()
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
 TlsRootsCancelLoad() : GcmJobCancel()
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
 ; Hooks belong only to the running worker. Leaving them installed across
 ; a yield would let unrelated callers try to suspend the scheduler's caller.
 tlsw_SetHooks()
 tlsw_gapStart=HwMicros() : tlsw_lastCheck=-1
 ran=ScRunHandle(tlsw_handle)
 tlsw_CheckGap(8)
 tlsw_ClearHooks()
 state=SchedState(tlsw_handle)
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
 ; A one-millisecond soft slice; an atomic unit may exceed the remainder.
 tlsw_sliceTicks=A64CounterFrequency()/1000
 If tlsw_sliceTicks<1 : ProcedureReturn 0 : EndIf
 If ScConfigure(code,bytes)=0 : ProcedureReturn 0 : EndIf
 tlsc_profileHook=@tlsw_ShowProfile
 tlsw_fault=0 : tlsc_advanceHook=@tlsw_Advance : tlsc_closeHook=@tlsw_Cancel
 ProcedureReturn 1
EndProcedure

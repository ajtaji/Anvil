; Shared cooperative TLS arithmetic execution for stream TLS and QUIC.
; Requires the crypto jobs, TLS/root hook declarations and cooperative_a64.
; Serialized dispatcher on the configured core/EL/address space only.
; One caller-owned descriptor and all its input/output buffers stay alive
; until completion/cancellation. All protocol users must respect Busy while
; suspended: clearing callbacks does NOT release the shared crypto scratch.
; Entries return 1 after normal execution; protocol results live in caller
; storage. Any other return is an execution fault, latched until restart.
; The caller owns connection snapshots, I/O, deadlines and root-store work.
; Completion preserves crypto results. Cancellation wipes job scratch, not
; caller buffers. This layer never cancels another connection's root loader.
#TLSWORK_BUSY=-3551
#TLSWORK_OWNER=-3552
#TLSWORK_STATE=-3553
#TLSWORK_CONTEXT=-3554
#TLSWORK_FAULT=-3555
Structure TlsWorkerJob
 task.i
 phase.i ; 1 active, 2 completed, 3 cancelled, -1 execution fault
 result.i
EndStructure
Global tlsjob_active.i,tlsjob_running.i,tlsjob_ready.i,tlsjob_fault.i
Global tlsjob_sliceStart.i
Global tlsjob_sliceTicks.i
Global tlsjob_gapStart.i
Global tlsjob_gapMax.i
Global tlsjob_gapFrom.i
Global tlsjob_gapTo.i
Global tlsjob_lastCheck.i
; Interval endpoints: -1 worker entry, 0 roots, 1 X509, 2 P256, 3 wide EC,
; 4 RSA, 5 X25519, 6 decrypt, 7 encrypt, 8 worker return, 9 transcript hashing, 10 key-share setup.
Procedure tlsjob_CheckGap(kind.i)
 Define now.i,gap.i
 now=HwMicros() : gap=now-tlsjob_gapStart : tlsjob_gapStart=now
 If gap>tlsjob_gapMax
  tlsjob_gapMax=gap : tlsjob_gapFrom=tlsjob_lastCheck : tlsjob_gapTo=kind
 EndIf
 tlsjob_lastCheck=kind
EndProcedure
Global Dim tlsjob_jobCount.i[12]
Global Dim tlsjob_jobTotal.i[12]
Global Dim tlsjob_jobMax.i[12]

; These spans contain one atomic Begin/Step and never a cooperative yield.
Procedure tlsjob_JobTime(kind.i,started.i)
 Define elapsed.i
 elapsed=HwMicros()-started
 tlsjob_jobCount[kind]=tlsjob_jobCount[kind]+1
 tlsjob_jobTotal[kind]=tlsjob_jobTotal[kind]+elapsed
 If elapsed>tlsjob_jobMax[kind] : tlsjob_jobMax[kind]=elapsed : EndIf
EndProcedure

Procedure TlsWorkerShowProfile()
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
  PrintDec(tlsjob_jobCount[i]) : Print(" / ") : PrintDec(tlsjob_jobTotal[i]) : Print(" / ") : PrintDec(tlsjob_jobMax[i]) : PrintNl()
 Next
 Print("TLS longest interval without a yield check, microseconds: ") : PrintDec(tlsjob_gapMax) : PrintNl()
 Print("TLS longest interval endpoints: ") : PrintDec(tlsjob_gapFrom) : Print(" -> ") : PrintDec(tlsjob_gapTo) : PrintNl()
EndProcedure

Procedure tlsjob_ClearHooks()
 X509PauseHook=0 : TlsRootsPauseHook=0 : TlsRecDecryptHook=0 : TlsRecEncryptHook=0 : Tls13PauseHook=0 : Tls13SetupPauseHook=0
 EcdsaVerifyHook=0 : RsaPublicHook=0 : X25519ComputeHook=0
EndProcedure

Procedure.i tlsjob_YieldKind(kind.i)
 tlsjob_CheckGap(kind)
 If A64CounterReadOrdered()-tlsjob_sliceStart<tlsjob_sliceTicks : ProcedureReturn 1 : EndIf
 ProcedureReturn ScYield()
EndProcedure
Procedure.i tlsjob_RootYield()
 ProcedureReturn tlsjob_YieldKind(0)
EndProcedure
Procedure.i tlsjob_SetupYield()
 ProcedureReturn tlsjob_YieldKind(10)
EndProcedure
Procedure.i tlsjob_TranscriptYield()
 ProcedureReturn tlsjob_YieldKind(9)
EndProcedure
Procedure.i tlsjob_X509Yield()
 ProcedureReturn tlsjob_YieldKind(1)
EndProcedure

Procedure.i tlsjob_Ecdsa(curve.i,hash.i,hashBytes.i,key.i,keyBytes.i,sig.i,sigBytes.i)
 Define started.i
 Define rc.i,i.i,raw.i
 If curve=#ECDSA_CURVE_P256
  started=HwMicros() : rc=EcdsaJobBegin(hash,hashBytes,key,keyBytes,sig,sigBytes,1) : tlsjob_JobTime(0,started)
  While rc=0
   If tlsjob_YieldKind(2)=0 : EcdsaJobCancel() : ProcedureReturn -1 : EndIf
   started=HwMicros() : rc=EcdsaJobStep() : tlsjob_JobTime(1,started)
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
 started=HwMicros() : rc=EcpJobBegin(curve,hash,hashBytes,key,keyBytes,@EcdsaRsig,raw) : tlsjob_JobTime(2,started)
 While rc=0
  If tlsjob_YieldKind(3)=0 : EcpJobCancel() : ProcedureReturn -1 : EndIf
  started=HwMicros() : rc=EcpJobStep() : tlsjob_JobTime(3,started)
 Wend
 EcdsaLastErr=EcpLastErr
 If rc<0 : ProcedureReturn -1 : EndIf
 ProcedureReturn EcpJobResult
EndProcedure

Procedure.i tlsjob_Rsa(out.i,bytes.i,modulus.i,modBytes.i,exponent.i,expBytes.i)
 Define started.i
 Define rc.i,i.i
 started=HwMicros() : rc=RsaJobBegin(out,bytes,modulus,modBytes,exponent,expBytes) : tlsjob_JobTime(4,started)
 While rc=0
  If tlsjob_YieldKind(4)=0 : RsaJobCancel() : ProcedureReturn 0 : EndIf
  started=HwMicros() : rc=RsaJobStep() : tlsjob_JobTime(5,started)
 Wend
 If rc<0 Or RsaJobResult<>1 : ProcedureReturn 0 : EndIf
 For i=0 To bytes-1 : PokeA(out+i,RsaSig[i]) : Next
 ProcedureReturn 1
EndProcedure

Procedure.i tlsjob_X25519(out.i,scalar.i,point.i)
 Define started.i
 Define rc.i
 started=HwMicros() : rc=X25519JobBegin(out,scalar,point) : tlsjob_JobTime(6,started)
 While rc=0
  If tlsjob_YieldKind(5)=0 : X25519JobCancel() : ProcedureReturn 0 : EndIf
  started=HwMicros() : rc=X25519JobStep() : tlsjob_JobTime(7,started)
 Wend
 ProcedureReturn Bool(rc=1)
EndProcedure

Procedure.i tlsjob_GcmDecrypt(key.i,nonce.i,aad.i,aadBytes.i,cipher.i,bytes.i,plain.i,tag.i)
 Define started.i
 Define rc.i
 started=HwMicros() : rc=GcmJobBeginDecrypt(key,16,nonce,aad,aadBytes,cipher,bytes,plain,tag) : tlsjob_JobTime(8,started)
 While rc=0
  If tlsjob_YieldKind(6)=0 : GcmJobCancel() : ProcedureReturn 0 : EndIf
  started=HwMicros() : rc=GcmJobStep() : tlsjob_JobTime(9,started)
 Wend
 If rc<>1 Or GcmJobResult<>1 : ProcedureReturn 0 : EndIf
 ProcedureReturn $FFFFFFFF
EndProcedure

Procedure.i tlsjob_GcmEncrypt(key.i,nonce.i,aad.i,aadBytes.i,plain.i,bytes.i,cipher.i,tag.i)
 Define started.i
 Define rc.i
 started=HwMicros() : rc=GcmJobBeginEncrypt(key,16,nonce,aad,aadBytes,plain,bytes,cipher,tag) : tlsjob_JobTime(10,started)
 While rc=0
  If tlsjob_YieldKind(7)=0 : GcmJobCancel() : ProcedureReturn 0 : EndIf
  started=HwMicros() : rc=GcmJobStep() : tlsjob_JobTime(11,started)
 Wend
 ProcedureReturn Bool(rc=1 And GcmJobResult=1)
EndProcedure


Procedure tlsjob_SetHooks()
 X509PauseHook=@tlsjob_X509Yield : TlsRootsPauseHook=@tlsjob_RootYield : TlsRecDecryptHook=@tlsjob_GcmDecrypt : TlsRecEncryptHook=@tlsjob_GcmEncrypt : Tls13PauseHook=@tlsjob_TranscriptYield : Tls13SetupPauseHook=@tlsjob_SetupYield
 EcdsaVerifyHook=@tlsjob_Ecdsa : RsaPublicHook=@tlsjob_Rsa : X25519ComputeHook=@tlsjob_X25519
EndProcedure


Procedure.i tlsjob_HooksBusy()
 ProcedureReturn Bool(X509PauseHook<>0 Or TlsRootsPauseHook<>0 Or TlsRecDecryptHook<>0 Or TlsRecEncryptHook<>0 Or Tls13PauseHook<>0 Or Tls13SetupPauseHook<>0 Or EcdsaVerifyHook<>0 Or RsaPublicHook<>0 Or X25519ComputeHook<>0)
EndProcedure
Procedure.i tlsjob_CryptoBusy()
 ProcedureReturn Bool(GcmJobBusy()<>0 Or EcdsaJobPhase<>0 Or EcpJobPhase<>0 Or RsaJobPhase<>0 Or X25519JobPhase<>0)
EndProcedure
Procedure tlsjob_CancelCrypto()
 GcmJobCancel() : EcdsaJobCancel() : EcpJobCancel() : RsaJobCancel() : X25519JobCancel()
EndProcedure
Procedure.i TlsWorkerBusy()
 ProcedureReturn Bool(tlsjob_active<>0)
EndProcedure
Procedure.i TlsWorkerFaulted()
 ProcedureReturn tlsjob_fault
EndProcedure
; Optional checkpoint for protocol loops between bounded operations.
; Only the executing owner may call it; 1 also means resumed successfully.
Procedure.i TlsWorkerCheckpoint()
 If tlsjob_running=0 : ProcedureReturn 0 : EndIf
 ProcedureReturn tlsjob_YieldKind(11)
EndProcedure
Procedure.i TlsWorkerInstall(code.i,bytes.i)
 If tlsjob_ready<>0 Or tlsjob_active<>0 Or tlsjob_HooksBusy()<>0 Or tlsjob_CryptoBusy()<>0 : ProcedureReturn 0 : EndIf
 tlsjob_sliceTicks=A64CounterFrequency()/1000
 If tlsjob_sliceTicks<1 : ProcedureReturn 0 : EndIf
 If ScConfigure(code,bytes)=0 : ProcedureReturn 0 : EndIf
 tlsjob_ready=1 : ProcedureReturn 1
EndProcedure
; Admission refusals leave the descriptor, queue and current owner unchanged.
Procedure.i TlsWorkerBegin(*job.TlsWorkerJob,entry.i,argument.i)
 Define task.i
 If tlsjob_fault<>0 : ProcedureReturn #TLSWORK_FAULT : EndIf
 If tlsjob_ready=0 Or *job=0 : ProcedureReturn #TLSWORK_STATE : EndIf
 If tlsjob_active<>0 Or tlsjob_HooksBusy()<>0 Or tlsjob_CryptoBusy()<>0 : ProcedureReturn #TLSWORK_BUSY : EndIf
 If *job\task<>0 Or *job\phase=1 : ProcedureReturn #TLSWORK_STATE : EndIf
 task=ScCreate(entry,argument)
 If task=0 : ProcedureReturn #TLSWORK_CONTEXT : EndIf
 *job\task=task : *job\phase=1 : *job\result=0 : tlsjob_active=*job
 ProcedureReturn 1
EndProcedure
; 0 yielded, 1 complete, negative refused/faulted. Only the named context runs.
; A soft 1 ms slice ends at a crypto checkpoint, not an interrupt deadline.
Procedure.i TlsWorkerStep(*job.TlsWorkerJob)
 Define ran.i,state.i,result.i
 If *job=0 Or tlsjob_active<>*job : ProcedureReturn #TLSWORK_OWNER : EndIf
 If tlsjob_fault<>0 : ProcedureReturn #TLSWORK_FAULT : EndIf
 If tlsjob_running<>0 Or tlsjob_HooksBusy()<>0 : ProcedureReturn #TLSWORK_BUSY : EndIf
 If *job\phase<>1 Or *job\task=0 : ProcedureReturn #TLSWORK_STATE : EndIf
 tlsjob_running=1 : tlsjob_sliceStart=A64CounterReadOrdered()
 tlsjob_SetHooks() : tlsjob_gapStart=HwMicros() : tlsjob_lastCheck=-1
 ran=ScRunHandle(*job\task)
 tlsjob_CheckGap(8) : tlsjob_ClearHooks() : tlsjob_running=0
 If ran=0 : ProcedureReturn #TLSWORK_CONTEXT : EndIf
 state=SchedState(*job\task)
 If state=#SCHED_READY Or state=#SCHED_WAITING : ProcedureReturn 0 : EndIf
 result=ScResult(*job\task)
 If state<>#SCHED_DONE Or result<>1 Or tlsjob_CryptoBusy()<>0
  tlsjob_fault=1 : *job\phase=-1 : tlsjob_CancelCrypto()
 Else
  *job\phase=2
 EndIf
 *job\result=result
 If ScReap(*job\task)=0
  tlsjob_fault=1 : *job\phase=-1 : ProcedureReturn #TLSWORK_FAULT
 EndIf
 *job\task=0 : tlsjob_active=0
 If tlsjob_fault<>0 : ProcedureReturn #TLSWORK_FAULT : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i TlsWorkerCancel(*job.TlsWorkerJob)
 Define state.i
 If *job=0 Or tlsjob_active<>*job : ProcedureReturn #TLSWORK_OWNER : EndIf
 If tlsjob_running<>0 Or tlsjob_HooksBusy()<>0 : ProcedureReturn #TLSWORK_BUSY : EndIf
 state=SchedState(*job\task)
 If state<>#SCHED_DONE And state<>#SCHED_CANCELLED
  If SchedCancel(*job\task)=0 : tlsjob_fault=1 : ProcedureReturn #TLSWORK_FAULT : EndIf
 EndIf
 If ScReap(*job\task)=0 : tlsjob_fault=1 : ProcedureReturn #TLSWORK_FAULT : EndIf
 tlsjob_CancelCrypto()
 *job\task=0 : *job\phase=3 : *job\result=0 : tlsjob_active=0
 ProcedureReturn 1
EndProcedure

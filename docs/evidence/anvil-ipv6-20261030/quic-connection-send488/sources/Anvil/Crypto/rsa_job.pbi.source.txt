; Cooperative RSA public operation using the shared BearSSL-derived i15
; arithmetic. Original notice: licenses/BearSSL-LICENSE.txt. Include rsa.pbi
; and bignum_job.pbi first. Owns Rsa scratch exclusively until completion.
Global RsaJobPhase.i
Global RsaJobResult.i
Global RsaJobBytes.i
Global RsaJobPow.BnPowJob
Global Dim RsaJobExponent.a[#RsaMaxBytes]

Procedure RsaJobCancel()
 Define i.i
 BnPowClear(@RsaJobPow)
 For i=0 To #RsaMaxBytes-1 : RsaJobExponent[i]=0 : Next
 RsaJobPhase=0 : RsaJobResult=0 : RsaJobBytes=0
EndProcedure

; Copies all inputs. 0 pending, 1 completed/refused, -2 busy. Read Result
; only after completion. RsaSig then holds the recovered representative;
; the caller MUST apply PKCS#1/PSS validation and compare the expected hash.
Procedure.i RsaJobBegin(sig.i,bytes.i,modulus.i,modBytes.i,exponent.i,expBytes.i)
 Define i.i,inverse.i,rc.i
 If RsaJobPhase<>0 : ProcedureReturn -2 : EndIf
 RsaJobResult=0 : RsaJobBytes=0
 If sig=0 Or modulus=0 Or exponent=0 : ProcedureReturn 1 : EndIf
 If modBytes<1 Or modBytes>#RsaMaxBytes Or expBytes<1 Or expBytes>#RsaMaxBytes : ProcedureReturn 1 : EndIf
 While modBytes>0
  If PeekA(modulus)<>0 : Break : EndIf
  modulus=modulus+1 : modBytes=modBytes-1
 Wend
 If modBytes=0 Or bytes<>modBytes : ProcedureReturn 1 : EndIf
 For i=0 To bytes-1 : RsaSig[i]=PeekA(sig+i) : Next
 For i=0 To expBytes-1 : RsaJobExponent[i]=PeekA(exponent+i) : Next
 RsaClear(@RsaM,#RsaMaxWords) : RsaClear(@RsaA,#RsaMaxWords)
 RsaClear(@RsaT1,#RsaMaxWords) : RsaClear(@RsaT2,#RsaMaxWords)
 BnDecode(@RsaM,modulus,modBytes)
 inverse=BnNinv15(BnGw(@RsaM,1))
 If (inverse & 1)=0 : RsaJobCancel() : ProcedureReturn 1 : EndIf
 If RsaDecodeMod(@RsaA,@RsaSig,bytes,@RsaM)=0 : RsaJobCancel() : ProcedureReturn 1 : EndIf
 rc=BnPowBeginDeferred(@RsaJobPow,@RsaA,@RsaJobExponent,expBytes,@RsaM,inverse,@RsaT1,@RsaT2)
 If rc<0 : RsaJobCancel() : ProcedureReturn 1 : EndIf
 RsaJobBytes=bytes : RsaJobPhase=1 : ProcedureReturn 0
EndProcedure

Procedure.i RsaJobStep()
 Define rc.i,bytes.i
 If RsaJobPhase=0 : ProcedureReturn -1 : EndIf
 rc=BnPowStep(@RsaJobPow,1)
 If rc=0 : ProcedureReturn 0 : EndIf
 If rc<0 : RsaJobCancel() : ProcedureReturn 1 : EndIf
 bytes=RsaJobBytes : BnEncode(@RsaSig,bytes,@RsaA)
 RsaJobCancel() : RsaJobBytes=bytes : RsaJobResult=1
 ProcedureReturn 1
EndProcedure

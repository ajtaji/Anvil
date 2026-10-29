; Scheduling uses existing shared bignum arithmetic; BearSSL reference.
; Original arithmetic notices: licenses/BearSSL-LICENSE.txt.
; Cooperative modular exponentiation. Caller-owned state and scratch permit
; independent jobs to alternate without retaining shared arithmetic state.
; Step performs at most bitBudget exponent bits, with two Montgomery
; multiplies per bit regardless of the exponent value. Begin still performs
; the bounded base conversion; this is not a complete asynchronous TLS API.

Structure BnPowJob
 x.i
 exponent.i
 bytes.i
 modulus.i
 inverse.i
 power.i
 scratch.i
 words.i
 bit.i
 state.i
EndStructure

; Storage and all operands must remain valid, separate, and unmodified until
; completion or cancellation. x is reduced modulo the odd modulus on entry,
; as for BnModpow. The buffers have the same capacity contract as BnModpow.
; A zero-length exponent is allowed with a null exponent pointer.
Procedure.i BnPowBegin(*job.BnPowJob,x.i,e.i,bytes.i,m.i,inverse.i,power.i,scratch.i)
 If *job=0 : ProcedureReturn -1 : EndIf
 If *job\state=1 : ProcedureReturn -2 : EndIf
 If x=0 Or m=0 Or power=0 Or scratch=0 : ProcedureReturn -1 : EndIf
 If bytes<0 Or bytes>8192 : ProcedureReturn -1 : EndIf
 If bytes>0
  If e=0 : ProcedureReturn -1 : EndIf
 EndIf
 If x=m Or x=power Or x=scratch Or m=power Or m=scratch Or power=scratch
  ProcedureReturn -1
 EndIf
 *job\x=x : *job\exponent=e : *job\bytes=bytes
 *job\modulus=m : *job\inverse=inverse
 *job\power=power : *job\scratch=scratch
 *job\words=(BnGw(m,0)+31)>>4 : *job\bit=0
 BnCopyWords(power,x,*job\words) : BnToMonty(power,m)
 BnZero(x,BnGw(m,0)) : BnSw(x,1,1)
 *job\state=1
 If bytes=0 : *job\state=2 : EndIf
 ProcedureReturn *job\state-1
EndProcedure

; Return 0 pending, 1 complete, -1 invalid/inactive. Invalid budgets do not
; advance or discard a job. The scheduling budget must not depend on secrets.
Procedure.i BnPowStep(*job.BnPowJob,bitBudget.i)
 Define limit.i,byte.i,ctl.i,k.i
 If *job=0 : ProcedureReturn -1 : EndIf
 If bitBudget<1 Or bitBudget>65536 : ProcedureReturn -1 : EndIf
 If *job\state=2 : ProcedureReturn 1 : EndIf
 If *job\state<>1 : ProcedureReturn -1 : EndIf
 k=*job\bit : limit=k+bitBudget
 If limit>(*job\bytes<<3) : limit=*job\bytes<<3 : EndIf
 While k<limit
  byte=PeekA(*job\exponent+*job\bytes-1-(k>>3)) & 255
  ctl=(byte>>(k & 7)) & 1
  BnMontmul(*job\scratch,*job\x,*job\power,*job\modulus,*job\inverse)
  BnCcopy(ctl,*job\x,*job\scratch,*job\words)
  BnMontmul(*job\scratch,*job\power,*job\power,*job\modulus,*job\inverse)
  BnCopyWords(*job\power,*job\scratch,*job\words)
  k=k+1
 Wend
 *job\bit=k
 If k=(*job\bytes<<3) : *job\state=2 : EndIf
 ProcedureReturn *job\state-1
EndProcedure

; Wipe intermediate arithmetic and the descriptor, including cancellation.
; The output and caller's exponent/modulus remain caller-owned.
Procedure BnPowClear(*job.BnPowJob)
 Define i.i,p.i
 If *job=0 : ProcedureReturn : EndIf
 If *job\state=1 Or *job\state=2
  For i=0 To *job\words-1
   BnSw(*job\power,i,0) : BnSw(*job\scratch,i,0)
  Next
 EndIf
 p=*job
 For i=0 To SizeOf(BnPowJob)-1 : PokeA(p+i,0) : Next
EndProcedure

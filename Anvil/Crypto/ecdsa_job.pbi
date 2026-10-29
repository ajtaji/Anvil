; Scheduling uses existing shared ecdsa/ec256 arithmetic; BearSSL reference.
; Original arithmetic notices: licenses/BearSSL-LICENSE.txt.
; Resumable P-256 verification. This job exclusively owns the existing
; ECDSA and ec256 scratch until completion or cancellation. It is NOT
; reentrant with synchronous ECDSA/ec256 calls. The transport scheduler
; must serialize their use. No private-scalar operation uses this path.

Global EcdsaJobPhase.i
Global EcdsaJobIndex.i
Global EcdsaJobResult.i
Global EcdsaJobPow.BnPowJob
Global Dim EcdsaJobHash.u[#ECDSA_NWORDS]

Procedure EcdsaJobCancel()
 BnPowClear(@EcdsaJobPow)
 EcdsaJobPhase=0 : EcdsaJobIndex=0 : EcdsaJobResult=0
EndProcedure

; 0 pending, 1 completed (inspect Result), -2 existing job still owns scratch.
; Caller inputs are copied/decoded here, so may be released after Begin.
Procedure.i EcdsaJobBegin(hash.i,hashBytes.i,key.i,keyBytes.i,sig.i,sigBytes.i,der.i)
 Define i.i,rlen.i,borrow.i,rc.i
 If EcdsaJobPhase<>0 : ProcedureReturn -2 : EndIf
 EcdsaJobResult=0 : EcdsaEnsureInit()
 EcdsaLastErr=#ECDSA_ERR_BADSIG
 If hashBytes<0 Or hashBytes>64 Or keyBytes<>65 Or sigBytes<=0 : ProcedureReturn 1 : EndIf
 If key=0 Or sig=0 : ProcedureReturn 1 : EndIf
 If hashBytes>0
  If hash=0 : ProcedureReturn 1 : EndIf
 EndIf
 If der<>0
  EcdsaLastErr=#ECDSA_ERR_MALFORMED
  If sigBytes>#ECDSA_SIGMAX : ProcedureReturn 1 : EndIf
  For i=0 To sigBytes-1 : PokeA(@EcdsaRsig+i,PeekA(sig+i)) : Next
  sigBytes=EcdsaAsn1ToRaw(@EcdsaRsig,sigBytes)
  If sigBytes=0 : ProcedureReturn 1 : EndIf
  sig=@EcdsaRsig
 EndIf
 EcdsaLastErr=#ECDSA_ERR_BADSIG
 If (sigBytes & 1)<>0 : ProcedureReturn 1 : EndIf
 rlen=sigBytes>>1
 If EcdsaDecodeMod(@EcdsaR,sig,rlen,@EcdsaN)=0 : ProcedureReturn 1 : EndIf
 If EcdsaDecodeMod(@EcdsaS,sig+rlen,rlen,@EcdsaN)=0 : ProcedureReturn 1 : EndIf
 If BnIsZero(@EcdsaS)<>0 : ProcedureReturn 1 : EndIf
 EcdsaBits2Int(@EcdsaJobHash,hash,hashBytes,BnGw(@EcdsaN,0))
 borrow=BnSub(@EcdsaJobHash,@EcdsaN,0)
 BnSub(@EcdsaJobHash,@EcdsaN,borrow ! 1)
 For i=0 To 64 : PokeA(@EcdsaU+i,PeekA(key+i)) : Next
 BnFromMonty(@EcdsaS,@EcdsaN,EcdsaN0i)
 rc=BnPowBegin(@EcdsaJobPow,@EcdsaS,@EcdsaExp,32,@EcdsaN,EcdsaN0i,@EcdsaT1,@EcdsaT2)
 If rc<0 : EcdsaJobCancel() : ProcedureReturn 1 : EndIf
 EcdsaJobPhase=1 : EcdsaJobIndex=0 : ProcedureReturn 0
EndProcedure

; One bounded arithmetic unit per call. Point operations contain no inverse;
; scalar and affine inverses advance eight bits per call. Return 1 complete,
; 0 pending, -1 inactive. Result is set only after the full verification.
Procedure.i EcdsaJobStep()
 Define rc.i,stride.i,p1.i,p2.i,i.i,j.i,entry.i,bit.i,index.i,xb.i,yb.i
 Define op.i,opc.i,dp.i,ap.i,bp.i,borrow.i
 If EcdsaJobPhase=0 : ProcedureReturn -1 : EndIf
 stride=6 * #EC_WORDS : p1=@EcdsaJoint+stride : p2=@EcdsaJoint+4*stride
 Select EcdsaJobPhase
 Case 1
  rc=BnPowStep(@EcdsaJobPow,8)
  If rc=0 : ProcedureReturn 0 : EndIf
  BnPowClear(@EcdsaJobPow)
  BnMontmul(@EcdsaT2,@EcdsaJobHash,@EcdsaS,@EcdsaN,EcdsaN0i)
  BnEncode(@EcdsaTy,32,@EcdsaT2)
  BnMontmul(@EcdsaT1,@EcdsaR,@EcdsaS,@EcdsaN,EcdsaN0i)
  BnEncode(@EcdsaTx,32,@EcdsaT1)
  EcdsaJobPhase=2
 Case 2
  Select EcdsaJobIndex
  Case 0
   EcPointZero(@EcdsaJoint)
   If EcPointDecode(p1,@EcdsaU,65)=0 : EcdsaJobCancel() : ProcedureReturn 1 : EndIf
  Case 1
   If EcPointDecode(p2,@EcGen,65)=0 : EcdsaJobCancel() : ProcedureReturn 1 : EndIf
  Case 2
   EcPointCopy(p1+stride,p1) : EcPointDouble(p1+stride)
  Case 3
   EcPointCopy(p1+2*stride,p1+stride) : EcdsaPublicAdd(p1+2*stride,p1)
  Case 4
   EcPointCopy(p2+4*stride,p2) : EcPointDouble(p2+4*stride)
  Case 5
   EcPointCopy(p2+8*stride,p2+4*stride) : EcdsaPublicAdd(p2+8*stride,p2)
  EndSelect
  EcdsaJobIndex=EcdsaJobIndex+1
  If EcdsaJobIndex=6 : EcdsaJobIndex=0 : EcdsaJobPhase=3 : EndIf
 Case 3
  i=1+EcdsaJobIndex%3 : j=1+EcdsaJobIndex/3
  entry=@EcdsaJoint+(i+4*j)*stride
  EcPointCopy(entry,@EcdsaJoint+i*stride) : EcdsaPublicAdd(entry,@EcdsaJoint+4*j*stride)
  EcdsaJobIndex=EcdsaJobIndex+1
  If EcdsaJobIndex=9
   EcPointZero(@EcdsaPpt) : EcdsaJobIndex=0 : EcdsaJobPhase=4
  EndIf
 Case 4
  i=EcdsaJobIndex>>2 : bit=6-2*(EcdsaJobIndex & 3)
  xb=PeekA(@EcdsaTx+i) & 255 : yb=PeekA(@EcdsaTy+i) & 255
  EcPointDouble(@EcdsaPpt) : EcPointDouble(@EcdsaPpt)
  index=((xb>>bit) & 3) | (((yb>>bit) & 3)<<2)
  If index<>0 : EcdsaPublicAdd(@EcdsaPpt,@EcdsaJoint+index*stride) : EndIf
  EcdsaJobIndex=EcdsaJobIndex+1
  If EcdsaJobIndex=128
   If BnIsZero(EcCoord(@EcdsaPpt,2))<>0 : EcdsaJobCancel() : ProcedureReturn 1 : EndIf
   EcPointCopy(@EcAffT,@EcdsaPpt) : EcSetOne(EcCoord(@EcCheckQ,2))
   BnCopyWords(EcRegP(#EcP1x),EcCoord(@EcAffT,0),3 * #EC_WORDS)
   BnCopyWords(EcRegP(#EcP2x),EcCoord(@EcCheckQ,0),3 * #EC_WORDS)
   EcdsaJobIndex=0 : EcdsaJobPhase=5
  EndIf
 Case 5
  op=PeekU(@EcCodeAff+(EcdsaJobIndex<<1))
  If op=0
   BnCopyWords(EcCoord(@EcAffT,0),EcRegP(#EcP1x),3 * #EC_WORDS)
   BnEncode(@EcdsaU+1,32,EcCoord(@EcAffT,0))
   BnZero(@EcdsaT1,BnGw(@EcdsaN,0)) : BnDecode(@EcdsaT1,@EcdsaU+1,32)
   BnSw(@EcdsaT1,0,BnGw(@EcdsaN,0))
   borrow=BnSub(@EcdsaT1,@EcdsaN,0) : BnSub(@EcdsaT1,@EcdsaN,borrow ! 1)
   rc=BnNot(BnSub(@EcdsaT1,@EcdsaR,1))
   rc=rc & BnIsZero(@EcdsaT1)
   EcdsaJobPhase=0 : EcdsaJobResult=rc
   If rc<>0 : EcdsaLastErr=#ECDSA_ERR_OK : EndIf
   ProcedureReturn 1
  EndIf
  dp=EcRegP((op>>8) & 15) : ap=EcRegP((op>>4) & 15) : bp=EcRegP(op & 15)
  opc=(op>>12) & 15
  Select opc
  Case 0 : BnCopyWords(dp,ap,#EC_WORDS)
  Case 1 : EcMAdd(dp,ap)
  Case 2 : EcMSub(dp,ap)
  Case 3 : BnMontmul(dp,ap,bp,@EcConstP,#EC_P0I)
  Case 4
   rc=BnPowBegin(@EcdsaJobPow,dp,@EcExp,32,@EcConstP,#EC_P0I,ap,bp)
   If rc<0 : EcdsaJobCancel() : ProcedureReturn 1 : EndIf
   EcdsaJobPhase=6
  Default
   ; The affine stream contains no flag instruction. Refuse unknown opcodes.
   EcdsaJobCancel() : ProcedureReturn 1
  EndSelect
  EcdsaJobIndex=EcdsaJobIndex+1
 Case 6
  rc=BnPowStep(@EcdsaJobPow,8)
  If rc=0 : ProcedureReturn 0 : EndIf
  ; Interpreter registers are live after this inverse. Drop the descriptor
  ; without clearing registers which the remaining affine opcodes may read.
  EcdsaJobPow\state=0 : BnPowClear(@EcdsaJobPow)
  EcdsaJobPhase=5
 EndSelect
 ProcedureReturn 0
EndProcedure

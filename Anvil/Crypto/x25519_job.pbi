; Resumable X25519 using the existing shared BearSSL-derived ladder.
; Original notice: licenses/BearSSL-LICENSE.txt. Include x25519.pbi first.
; Exclusive owner of X25519 scratch. One constant-work ladder bit per call;
; inversion scheduling depends only on a fixed public exponent.
Global X25519JobPhase.i
Global X25519JobIndex.i
Global X25519JobSwap.i
Global X25519JobOutput.i

Procedure X25519JobCancel()
 Define i.i
 For i=0 To #X_WORDS-1 : BnSw(@Xx1,i,0) : Next
 For i=0 To #X_WORDS-1 : BnSw(@Xx2,i,0) : Next
 For i=0 To #X_WORDS-1 : BnSw(@Xx3,i,0) : Next
 For i=0 To #X_WORDS-1 : BnSw(@Xz2,i,0) : Next
 For i=0 To #X_WORDS-1 : BnSw(@Xz3,i,0) : Next
 For i=0 To #X_WORDS-1 : BnSw(@Xfa,i,0) : Next
 For i=0 To #X_WORDS-1 : BnSw(@Xaa,i,0) : Next
 For i=0 To #X_WORDS-1 : BnSw(@Xfb,i,0) : Next
 For i=0 To #X_WORDS-1 : BnSw(@Xbb,i,0) : Next
 For i=0 To #X_WORDS-1 : BnSw(@Xfc,i,0) : Next
 For i=0 To #X_WORDS-1 : BnSw(@Xfd,i,0) : Next
 For i=0 To #X_WORDS-1 : BnSw(@Xfe,i,0) : Next
 For i=0 To #X_WORDS-1 : BnSw(@Xda,i,0) : Next
 For i=0 To #X_WORDS-1 : BnSw(@Xcb,i,0) : Next
 For i=0 To #X_WORDS-1 : BnSw(@Xsyn,i,0) : Next
 For i=0 To #X_WORDS-1 : BnSw(@XTmp,i,0) : Next
 For i=0 To 31 : PokeA(@SecK+i,0) : PokeA(@XWG+i,0) : Next
 X25519JobPhase=0 : X25519JobIndex=0 : X25519JobSwap=0 : X25519JobOutput=0
EndProcedure
Procedure.i X25519JobBegin(out.i,secScalar.i,point.i)
 Define i.i
 If X25519JobPhase<>0 : ProcedureReturn -2 : EndIf
 If out=0 Or secScalar=0 Or point=0 : ProcedureReturn -1 : EndIf
 X25519Init()
  ; Copy the point, clear its high bit, and byteswap to big-endian for the
  ; generic decoder.
  i = 0
  While i < 32
    PokeB(@XWG + i, PeekA(point + i) & 255)
    i = i + 1
  Wend
  PokeB(@XWG + 31, PeekA(@XWG + 31) & $7F)
  XByteswap(@XWG)

  ; Decode the u coordinate modulo a synthetic 2^255 (avoids a dependency
  ; on a decode-reduce against p), then subtract p once if needed.
  BnZero(@Xsyn, $111)
  BnSw(@Xsyn, 18, 1)
  BnDecodeReduce(@Xfa, @XWG, 32, @Xsyn)
  BnSw(@Xfa, 0, #X_MENC)
  BnSub(@Xfa, @XConstP, BnNot(BnSub(@Xfa, @XConstP, 0)))

  ; Initialise the ladder in Montgomery representation. Montgomery 1 is
  ; R mod p = 19 here (R = 2^255, and 2^255 = p + 19).
  BnMontmul(@Xx1, @Xfa, @XConstR2, @XConstP, #X_P0I)
  XCopy(@Xx3, @Xx1)
  BnZero(@Xz2, #X_MENC)
  XCopy(@Xx2, @Xz2)
  BnSw(@Xx2, 1, 19)
  XCopy(@Xz3, @Xx2)

  ; Build the clamped scalar (RFC 7748) in big-endian order. The incoming
  ; scalar is little-endian, so reverse it, then apply the clamp: on the
  ; big-endian buffer that is the last byte &= 0xF8, first byte &= 0x7F,
  ; first byte |= 0x40.
  i = 0
  While i < 32
    PokeB(@SecK + i, PeekA(secScalar + 31 - i) & 255)
    i = i + 1
  Wend
  PokeB(@SecK + 31, PeekA(@SecK + 31) & $F8)
  PokeB(@SecK + 0, PeekA(@SecK + 0) & $7F)
  PokeB(@SecK + 0, PeekA(@SecK + 0) | $40)

 X25519JobOutput=out : X25519JobSwap=0 : X25519JobIndex=254 : X25519JobPhase=1
 ProcedureReturn 0
EndProcedure
Procedure.i X25519JobStep()
 Define i.i,j.i,secKt.i,out.i
 If X25519JobPhase=0 : ProcedureReturn -1 : EndIf
 i=X25519JobIndex
 Select X25519JobPhase
 Case 1
    secKt = (PeekA(@SecK + 31 - (i >> 3)) >> (i & 7)) & 1
    X25519JobSwap = X25519JobSwap ! secKt
    XCswap(X25519JobSwap, @Xx2, @Xx3)
    XCswap(X25519JobSwap, @Xz2, @Xz3)
    X25519JobSwap = secKt

    XAdd(@Xfa, @Xx2, @Xz2)
    XMul(@Xaa, @Xfa, @Xfa)
    XSub(@Xfb, @Xx2, @Xz2)
    XMul(@Xbb, @Xfb, @Xfb)
    XSub(@Xfe, @Xaa, @Xbb)
    XAdd(@Xfc, @Xx3, @Xz3)
    XSub(@Xfd, @Xx3, @Xz3)
    XMul(@Xda, @Xfd, @Xfa)
    XMul(@Xcb, @Xfc, @Xfb)

    XAdd(@Xx3, @Xda, @Xcb)
    XMul(@Xx3, @Xx3, @Xx3)
    XSub(@Xz3, @Xda, @Xcb)
    XMul(@Xz3, @Xz3, @Xz3)
    XMul(@Xz3, @Xz3, @Xx1)
    XMul(@Xx2, @Xaa, @Xbb)
    XMul(@Xz2, @XConstA24, @Xfe)
    XAdd(@Xz2, @Xz2, @Xaa)
    XMul(@Xz2, @Xfe, @Xz2)

  X25519JobIndex=i-1
  If X25519JobIndex<0
   XCswap(X25519JobSwap,@Xx2,@Xx3) : XCswap(X25519JobSwap,@Xz2,@Xz3)
   XCopy(@Xfa,@Xz2) : X25519JobIndex=0 : X25519JobPhase=2
  EndIf
 Case 2
  XMul(@Xfa,@Xfa,@Xfa) : XMul(@Xfa,@Xfa,@Xz2)
  X25519JobIndex=i+1
  If X25519JobIndex=15
   XCopy(@Xfb,@Xfa) : X25519JobIndex=0 : X25519JobPhase=3
  EndIf
 Case 3
  For j=0 To 15 : XMul(@Xfb,@Xfb,@Xfb) : Next
  XMul(@Xfb,@Xfb,@Xfa) : X25519JobIndex=i+1
  If X25519JobIndex=14 : X25519JobIndex=14 : X25519JobPhase=4 : EndIf
 Case 4
  XMul(@Xfb,@Xfb,@Xfb)
  If (($FFEB>>i) & 1)<>0 : XMul(@Xfb,@Xz2,@Xfb) : EndIf
  X25519JobIndex=i-1
  If X25519JobIndex<0 : X25519JobPhase=5 : EndIf
 Case 5
  XMul(@Xfb,@Xx2,@Xfb)
  BnZero(@Xfa,#X_MENC) : BnSw(@Xfa,1,1)
  BnMontmul(@Xx2,@Xfa,@Xfb,@XConstP,#X_P0I)
  BnEncode(@XWG,32,@Xx2) : XByteswap(@XWG)
  out=X25519JobOutput
  For i=0 To 31 : PokeA(out+i,PeekA(@XWG+i)) : Next
  X25519JobCancel() : ProcedureReturn 1
 EndSelect
 ProcedureReturn 0
EndProcedure

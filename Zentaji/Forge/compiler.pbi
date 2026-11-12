; Bounded PureMetal-to-Zentaji compiler. The caller supplies guest-owned source
; and output spans. Each accepted expression emits scalar CPU instructions.
#ZF_SOURCE_BYTES=8192
#ZF_CODE_BYTES=65536
#ZF_VARIABLES=32
#ZF_TEMP_FIRST=48
#ZF_TEMPS=32
#ZF_OPERATORS=64

; Zentaji v1 scalar instruction fields. The native compiler check verifies
; these encodings against tools/zentaji/opcodes.py.
#ZF_LIQ=$34
#ZF_ADD=$10
#ZF_SUB=$11
#ZF_MUL=$1D
#ZF_JR=$9C

Structure ZfVariable
 start.i
 length.i
EndStructure
Global Dim zfVariables.ZfVariable[#ZF_VARIABLES]
Global Dim zfOperators.a[#ZF_OPERATORS]
Global zfSource.i,zfPos.i,zfEnd.i,zfLine.i,zfLineStart.i
Global zfCode.i,zfCapacity.i,zfUsed.i,zfVariableCount.i,zfValues.i,zfOps.i
Global zfError.i

Procedure.i ZfFail(*reason)
 zfError=*reason
 ProcedureReturn 0
EndProcedure

Procedure.i ZfLower(c.i)
 If c>=65 And c<=90 : ProcedureReturn c+32 : EndIf
 ProcedureReturn c
EndProcedure

Procedure.i ZfByte()
 If zfPos>=zfEnd : ProcedureReturn 0 : EndIf
 ProcedureReturn PeekA(zfSource+zfPos)
EndProcedure

Procedure ZfSpace()
 Protected c.i
 While zfPos<zfEnd
  c=ZfByte()
  If c<>32 And c<>9 : Break : EndIf
  zfPos=zfPos+1
 Wend
EndProcedure

Procedure.i ZfNameByte(c.i)
 c=ZfLower(c)
 ProcedureReturn Bool((c>=97 And c<=122) Or c=95 Or (c>=48 And c<=57))
EndProcedure

Procedure.i ZfName()
 Protected start.i=zfPos,c.i=ZfLower(ZfByte())
 If (c<97 Or c>122) And c<>95 : ProcedureReturn 0 : EndIf
 While ZfNameByte(ZfByte())<>0 : zfPos=zfPos+1 : Wend
 ProcedureReturn zfPos-start
EndProcedure

Procedure.i ZfKeyword(*word)
 Protected i.i,c.i
 While PeekA(*word+i)<>0
  If zfPos+i>=zfEnd : ProcedureReturn 0 : EndIf
  c=ZfLower(PeekA(zfSource+zfPos+i))
  If c<>PeekA(*word+i) : ProcedureReturn 0 : EndIf
  i=i+1
 Wend
 If zfPos+i<zfEnd
  If ZfNameByte(PeekA(zfSource+zfPos+i))<>0 : ProcedureReturn 0 : EndIf
 EndIf
 zfPos=zfPos+i
 ProcedureReturn 1
EndProcedure

Procedure.i ZfTake(c.i)
 ZfSpace()
 If ZfLower(ZfByte())<>c : ProcedureReturn 0 : EndIf
 zfPos=zfPos+1
 ProcedureReturn 1
EndProcedure

Procedure.i ZfLineDone()
 ZfSpace()
 ProcedureReturn Bool(zfPos=zfEnd Or ZfByte()=59)
EndProcedure

Procedure.i ZfFind(start.i,n.i)
 Protected v.i,k.i,a.i,b.i
 For v=0 To zfVariableCount-1
  If zfVariables[v]\length=n
   k=0
   While k<n
    a=ZfLower(PeekA(zfSource+start+k))
    b=ZfLower(PeekA(zfSource+zfVariables[v]\start+k))
    If a<>b : Break : EndIf
    k=k+1
   Wend
   If k=n : ProcedureReturn v+16 : EndIf
  EndIf
 Next
 ProcedureReturn 0
EndProcedure

Procedure.i ZfEmit(word.q)
 If zfUsed>zfCapacity-8 : ProcedureReturn ZfFail("generated code is too large") : EndIf
 PokeQ(zfCode+zfUsed,word)
 zfUsed=zfUsed+8
 ProcedureReturn 1
EndProcedure

Procedure.i ZfAlu(op.i,rd.i,ra.i,rb.i)
 ProcedureReturn ZfEmit(op|(rd<<8)|(ra<<16)|(rb<<24))
EndProcedure

Procedure.i ZfNumber(rd.i)
 Protected base.i=10,c.i,digit.i,start.i,value.q
 If ZfByte()=36 : base=16 : zfPos=zfPos+1 : EndIf
 start=zfPos
 While zfPos<zfEnd
  c=ZfLower(ZfByte())
  digit=c-48
  If c>=97 And c<=102 : digit=c-87 : EndIf
  If (c<48 Or c>57) And (c<97 Or c>102) : Break : EndIf
  If digit>=base : Break : EndIf
  If base=16
   If zfPos-start>=16 : ProcedureReturn ZfFail("hex literal exceeds 64 bits") : EndIf
   value=(value<<4)|digit
  Else
   If value>($7FFFFFFFFFFFFFFF-digit)/10
    ; The one extra magnitude is legal when consumed by unary minus.
    If value=922337203685477580 And digit=8 And zfOps>0
     If zfOperators[zfOps-1]=126
      value=$8000000000000000
      zfPos=zfPos+1
      Break
     EndIf
    EndIf
    ProcedureReturn ZfFail("decimal literal exceeds signed 64-bit range")
   EndIf
   value=value*10+digit
  EndIf
  zfPos=zfPos+1
 Wend
 If zfPos=start : ProcedureReturn ZfFail("expected digits") : EndIf
 If ZfNameByte(ZfByte())<>0 : ProcedureReturn ZfFail("invalid integer literal") : EndIf
 If ZfEmit(#ZF_LIQ|(rd<<8))=0 : ProcedureReturn 0 : EndIf
 ProcedureReturn ZfEmit(value)
EndProcedure

; '(' is a stack barrier. Unary '-' is represented by '~' on this stack.
Procedure.i ZfPrecedence(c.i)
 Select c
  Case 126 : ProcedureReturn 3
  Case 42 : ProcedureReturn 2
  Case 43,45 : ProcedureReturn 1
 EndSelect
 ProcedureReturn 0
EndProcedure

Procedure.i ZfPush(c.i)
 If zfOps>=#ZF_OPERATORS : ProcedureReturn ZfFail("expression nesting is too deep") : EndIf
 zfOperators[zfOps]=c
 zfOps=zfOps+1
 ProcedureReturn 1
EndProcedure

Procedure.i ZfReduce()
 Protected c.i,op.i,left.i,right.i
 zfOps=zfOps-1 : c=zfOperators[zfOps]
 If c=126
  right=#ZF_TEMP_FIRST+zfValues-1
  ProcedureReturn ZfAlu(#ZF_SUB,right,0,right)
 EndIf
 If c=40 : ProcedureReturn ZfFail("missing closing parenthesis") : EndIf
 right=#ZF_TEMP_FIRST+zfValues-1 : left=right-1
 Select c
  Case 43 : op=#ZF_ADD
  Case 45 : op=#ZF_SUB
  Case 42 : op=#ZF_MUL
 EndSelect
 zfValues=zfValues-1
 ProcedureReturn ZfAlu(op,left,left,right)
EndProcedure

Procedure.i ZfExpression(destination.i)
 Protected need.i=1,c.i,rd.i,start.i,n.i,reg.i
 zfValues=0 : zfOps=0
 While ZfLineDone()=0
  c=ZfByte()
  If need<>0
   If c=40 Or c=45
    If c=45 : c=126 : EndIf
    If ZfPush(c)=0 : ProcedureReturn 0 : EndIf
    zfPos=zfPos+1
   ElseIf c=43
    zfPos=zfPos+1
   Else
    If zfValues>=#ZF_TEMPS : ProcedureReturn ZfFail("too many pending expression values") : EndIf
    rd=#ZF_TEMP_FIRST+zfValues
    If c=36 Or (c>=48 And c<=57)
     If ZfNumber(rd)=0 : ProcedureReturn 0 : EndIf
    Else
     start=zfPos : n=ZfName()
     If n=0 : ProcedureReturn ZfFail("expected an integer, variable, or parenthesis") : EndIf
     reg=ZfFind(start,n)
     If reg=0 : ProcedureReturn ZfFail("unknown variable") : EndIf
     If ZfAlu(#ZF_ADD,rd,reg,0)=0 : ProcedureReturn 0 : EndIf
    EndIf
    zfValues=zfValues+1 : need=0
   EndIf
  ElseIf c=41
   While zfOps>0
    If zfOperators[zfOps-1]=40 : Break : EndIf
    If ZfReduce()=0 : ProcedureReturn 0 : EndIf
   Wend
   If zfOps=0 : ProcedureReturn ZfFail("unexpected closing parenthesis") : EndIf
   zfOps=zfOps-1 : zfPos=zfPos+1
  Else
   If c<>43 And c<>45 And c<>42 : ProcedureReturn ZfFail("expected +, -, *, or end of expression") : EndIf
   While zfOps>0
    If ZfPrecedence(zfOperators[zfOps-1])<ZfPrecedence(c) : Break : EndIf
    If ZfReduce()=0 : ProcedureReturn 0 : EndIf
   Wend
   If ZfPush(c)=0 : ProcedureReturn 0 : EndIf
   zfPos=zfPos+1 : need=1
  EndIf
 Wend
 If need<>0 : ProcedureReturn ZfFail("expression ends before an operand") : EndIf
 While zfOps>0
  If ZfReduce()=0 : ProcedureReturn 0 : EndIf
 Wend
 ProcedureReturn ZfAlu(#ZF_ADD,destination,#ZF_TEMP_FIRST,0)
EndProcedure

Procedure.i ZfAssignment(declare.i)
 Protected start.i,n.i,reg.i
 ZfSpace()
 start=zfPos : n=ZfName()
 If n=0 : ProcedureReturn ZfFail("expected a variable name") : EndIf
 reg=ZfFind(start,n)
 If declare<>0
  If reg<>0 : ProcedureReturn ZfFail("variable is already declared") : EndIf
  If ZfTake(46)=0 Or ZfTake(113)=0 : ProcedureReturn ZfFail("Protected variables require .q") : EndIf
  If zfVariableCount>=#ZF_VARIABLES : ProcedureReturn ZfFail("too many local variables") : EndIf
  reg=16+zfVariableCount
 ElseIf reg=0
  ProcedureReturn ZfFail("assignment requires a declared variable")
 EndIf
 If ZfTake(61)=0 : ProcedureReturn ZfFail("expected =") : EndIf
 If ZfExpression(reg)=0 : ProcedureReturn 0 : EndIf
 If declare<>0
  zfVariables[zfVariableCount]\start=start : zfVariables[zfVariableCount]\length=n
  zfVariableCount=zfVariableCount+1
 EndIf
 ProcedureReturn 1
EndProcedure

; A program has exactly one returning Procedure.q Main(). Immediate mode
; compiles one expression using the same emitter and the same return ABI.
Procedure.i ZfCompile(source.i,bytes.i,code.i,capacity.i,immediate.i)
 Protected nextLine.i,phase.i
 zfSource=source : zfCode=code : zfCapacity=capacity : zfUsed=0
 zfPos=0 : zfEnd=bytes : zfLine=1 : zfLineStart=0 : zfVariableCount=0 : zfError=0
 If source=0 Or bytes<1 Or bytes>#ZF_SOURCE_BYTES Or code=0 Or capacity<8 Or (code&7)<>0
  ProcedureReturn ZfFail("invalid compiler input or output span")
 EndIf
 If immediate<>0
  If ZfExpression(1)=0 : ProcedureReturn 0 : EndIf
 Else
  While zfPos<bytes
   zfLineStart=zfPos
   zfEnd=zfPos
   While zfEnd<bytes
    If PeekA(source+zfEnd)=10 Or PeekA(source+zfEnd)=13 : Break : EndIf
    zfEnd=zfEnd+1
   Wend
   nextLine=zfEnd+1
   If nextLine<bytes And PeekA(source+zfEnd)=13 And PeekA(source+nextLine)=10 : nextLine=nextLine+1 : EndIf
   If ZfLineDone()=0
    Select phase
     Case 0
      If ZfKeyword("procedure")=0 Or ZfTake(46)=0 Or ZfTake(113)=0 : ProcedureReturn ZfFail("expected Procedure.q Main()") : EndIf
      ZfSpace()
      If ZfKeyword("main")=0 Or ZfTake(40)=0 Or ZfTake(41)=0 Or ZfLineDone()=0 : ProcedureReturn ZfFail("expected Procedure.q Main()") : EndIf
      phase=1
     Case 1
      If ZfKeyword("procedurereturn")<>0
       If ZfExpression(1)=0 : ProcedureReturn 0 : EndIf
       phase=2
      ElseIf ZfKeyword("protected")<>0
       If ZfAssignment(1)=0 : ProcedureReturn 0 : EndIf
      Else
       If ZfAssignment(0)=0 : ProcedureReturn 0 : EndIf
      EndIf
     Case 2
      If ZfKeyword("endprocedure")=0 Or ZfLineDone()=0 : ProcedureReturn ZfFail("expected EndProcedure after ProcedureReturn") : EndIf
      phase=3
     Case 3
      ProcedureReturn ZfFail("unexpected source after EndProcedure")
    EndSelect
   EndIf
   zfPos=nextLine : zfLine=zfLine+1
  Wend
  zfLineStart=zfPos
  If phase<>3 : ProcedureReturn ZfFail("program requires Procedure.q Main(), ProcedureReturn, and EndProcedure") : EndIf
 EndIf
 If ZfEmit(#ZF_JR|(254<<8))=0 : ProcedureReturn 0 : EndIf
 ProcedureReturn zfUsed
EndProcedure

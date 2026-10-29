; SPDX-License-Identifier: MIT
; Returning CPU validation of shared logical types and selection contracts.
XIncludeFile "Anvil/Graphics/Vulkan/vk_ir.pbi"
Global bm.AvkIrModule
Global bb.AvkIrBlock
Global Dim bt.AvkIrType[8]
Global Dim bc.AvkIrConstant[7]
Global Dim bn.AvkIrNode[7]
Global bchecks.i,bfailed.i
Procedure BCheck(actual.i,expected.i)
  PokeI($E1C00040+bchecks*16,actual)
  PokeI($E1C00048+bchecks*16,expected)
  bchecks=bchecks+1
  If actual<>expected : bfailed=bfailed+1 : EndIf
EndProcedure
Procedure BInit(lanes.i)
  Protected i.i,f.i=3,b.i=4,z.i=7
  For i=0 To SizeOf(AvkIrModule)-1 : PokeA(@bm+i,0) : Next
  For i=0 To SizeOf(AvkIrBlock)-1 : PokeA(@bb+i,0) : Next
  For i=0 To SizeOf(AvkIrType)*8-1 : PokeA(@bt[0]+i,0) : Next
  For i=0 To SizeOf(AvkIrConstant)*7-1 : PokeA(@bc[0]+i,0) : Next
  For i=0 To SizeOf(AvkIrNode)*7-1 : PokeA(@bn[0]+i,0) : Next
  bm\idBound=80 : bm\sourceVersion=$10000 : bm\stage=#ANVIL_IR_STAGE_FRAGMENT
  bm\types=@bt[0] : bm\typeCount=8 : bm\constants=@bc[0] : bm\constantCount=7
  bm\nodes=@bn[0] : bm\nodeCount=7 : bm\blocks=@bb : bm\blockCount=1
  bm\entryFunctionId=70 : bm\entryFunctionOpcode=54 : bm\functionTypeId=2
  bm\returnTypeId=1 : bm\entryBlockId=71
  bb\sourceId=71 : bb\sourceOpcode=248 : bb\nodeCount=7
  For i=0 To 7 : bt[i]\sourceId=i+1 : Next
  bt[0]\kind=#ANVIL_IR_TYPE_VOID : bt[0]\sourceOpcode=19
  bt[1]\kind=#ANVIL_IR_TYPE_FUNCTION : bt[1]\sourceOpcode=33 : bt[1]\returnType=1
  bt[2]\kind=#ANVIL_IR_TYPE_FLOAT : bt[2]\sourceOpcode=22 : bt[2]\width=32
  bt[3]\kind=#ANVIL_IR_TYPE_BOOL : bt[3]\sourceOpcode=20
  bt[4]\kind=#ANVIL_IR_TYPE_VECTOR : bt[4]\sourceOpcode=23 : bt[4]\componentType=3
  bt[5]\kind=#ANVIL_IR_TYPE_VECTOR : bt[5]\sourceOpcode=23 : bt[5]\componentType=4
  bt[6]\kind=#ANVIL_IR_TYPE_INT : bt[6]\sourceOpcode=21 : bt[6]\width=32
  bt[7]\kind=#ANVIL_IR_TYPE_VECTOR : bt[7]\sourceOpcode=23 : bt[7]\componentType=7
  bt[4]\componentCount=lanes : bt[5]\componentCount=lanes : bt[7]\componentCount=lanes
  If lanes=1
    bt[4]\componentCount=2 : bt[5]\componentCount=2 : bt[7]\componentCount=2
  Else
    f=5 : b=6 : z=8
  EndIf
  For i=0 To 6 : bc[i]\sourceId=10+i : Next
  bc[0]\typeId=3 : bc[0]\sourceOpcode=43 : bc[0]\wordCount=1 : bc[0]\word0=$3F000000
  bc[1]\typeId=4 : bc[1]\sourceOpcode=41 : bc[1]\word0=1
  bc[2]\typeId=4 : bc[2]\sourceOpcode=42
  bc[3]\typeId=5 : bc[3]\sourceOpcode=44 : bc[3]\componentCount=bt[4]\componentCount
  bc[3]\component0=10 : bc[3]\component1=10 : bc[3]\component2=10 : bc[3]\component3=10
  bc[4]\typeId=6 : bc[4]\sourceOpcode=44 : bc[4]\componentCount=bt[5]\componentCount
  bc[4]\component0=11 : bc[4]\component1=12 : bc[4]\component2=11 : bc[4]\component3=12
  bc[5]\typeId=7 : bc[5]\sourceOpcode=43 : bc[5]\wordCount=1 : bc[5]\word0=$FFFFFFFF
  bc[6]\typeId=8 : bc[6]\sourceOpcode=44 : bc[6]\componentCount=bt[7]\componentCount
  bc[6]\component0=15 : bc[6]\component1=15 : bc[6]\component2=15 : bc[6]\component3=15
  For i=0 To 5 : bn[i]\sourceId=30+i : bn[i]\blockId=71 : Next
  bn[0]\kind=#ANVIL_IR_OP_FORD_LESS : bn[0]\sourceOpcode=184
  bn[1]\kind=#ANVIL_IR_OP_FORD_GREATER : bn[1]\sourceOpcode=186
  For i=0 To 1
    bn[i]\resultType=b : bn[i]\operandCount=2
    bn[i]\operand0=10 : bn[i]\operand1=10
    If lanes>1 : bn[i]\operand0=13 : bn[i]\operand1=13 : EndIf
  Next
  bn[2]\kind=#ANVIL_IR_OP_LOGICAL_OR : bn[2]\sourceOpcode=166
  bn[2]\resultType=b : bn[2]\operandCount=2 : bn[2]\operand0=30 : bn[2]\operand1=31
  For i=3 To 5
    bn[i]\kind=#ANVIL_IR_OP_SELECT : bn[i]\sourceOpcode=169 : bn[i]\operandCount=3
    bn[i]\operand0=32
  Next
  bn[3]\resultType=f : bn[3]\operand1=bn[0]\operand0 : bn[3]\operand2=bn[0]\operand1
  bn[4]\resultType=b : bn[4]\operand1=11 : bn[4]\operand2=12
  bn[5]\resultType=z : bn[5]\operand1=15 : bn[5]\operand2=15
  If lanes>1
    bn[4]\operand1=14 : bn[4]\operand2=14 : bn[5]\operand1=16 : bn[5]\operand2=16
  EndIf
  bn[6]\kind=#ANVIL_IR_OP_RETURN : bn[6]\sourceOpcode=253 : bn[6]\blockId=71
EndProcedure
Procedure.i Main(services.i)
  Protected i.i,lanes.i
  For i=0 To 16383 : PokeA($E1C00000+i,0) : Next
  PokeI($E1C00000,$424F4F31)
  For lanes=1 To 4
    BInit(lanes) : BCheck(AnvilVkIrVerify(@bm),0)
    bn[0]\resultType=3 : BCheck(AnvilVkIrVerify(@bm),#ANVIL_IR_ERR_TYPE)
    BInit(lanes) : bn[0]\operand1=11 : BCheck(AnvilVkIrVerify(@bm),#ANVIL_IR_ERR_TYPE)
    BInit(lanes) : bn[1]\operandCount=1 : BCheck(AnvilVkIrVerify(@bm),#ANVIL_IR_ERR_TYPE)
    BInit(lanes) : bn[2]\operand1=10 : BCheck(AnvilVkIrVerify(@bm),#ANVIL_IR_ERR_TYPE)
    BInit(lanes) : bn[3]\operand0=10 : BCheck(AnvilVkIrVerify(@bm),#ANVIL_IR_ERR_TYPE)
    BInit(lanes) : bn[3]\operand2=11 : BCheck(AnvilVkIrVerify(@bm),#ANVIL_IR_ERR_TYPE)
    BInit(lanes) : bn[3]\operandCount=2 : BCheck(AnvilVkIrVerify(@bm),#ANVIL_IR_ERR_TYPE)
    BInit(lanes) : bn[0]\operand0=31 : BCheck(AnvilVkIrVerify(@bm),#ANVIL_IR_ERR_DOMINANCE)
    BInit(lanes) : bn[0]\operand0=69 : BCheck(AnvilVkIrVerify(@bm),#ANVIL_IR_ERR_UNDEFINED)
    BInit(lanes) : bn[0]\sourceOpcode=186 : BCheck(AnvilVkIrVerify(@bm),#ANVIL_IR_ERR_UNSUPPORTED)
    BInit(lanes) : bn[0]\literalCount=1 : BCheck(AnvilVkIrVerify(@bm),#ANVIL_IR_ERR_TYPE)
    BInit(lanes) : bn[3]\operand0=11
    If lanes=1 : BCheck(AnvilVkIrVerify(@bm),0) : Else : BCheck(AnvilVkIrVerify(@bm),#ANVIL_IR_ERR_TYPE) : EndIf
    bm\sourceVersion=$10400 : BCheck(AnvilVkIrVerify(@bm),0)
    bm\sourceVersion=0 : BCheck(AnvilVkIrVerify(@bm),0)
  Next
  BInit(2) : bt[3]\width=32 : BCheck(AnvilVkIrVerify(@bm),#ANVIL_IR_ERR_TYPE)
  BInit(2) : bc[1]\word0=0 : BCheck(AnvilVkIrVerify(@bm),#ANVIL_IR_ERR_TYPE)
  BInit(2) : bc[2]\word0=1 : BCheck(AnvilVkIrVerify(@bm),#ANVIL_IR_ERR_TYPE)
  BInit(2) : bc[1]\wordCount=1 : BCheck(AnvilVkIrVerify(@bm),#ANVIL_IR_ERR_TYPE)
  BInit(2) : bc[1]\sourceOpcode=43 : BCheck(AnvilVkIrVerify(@bm),#ANVIL_IR_ERR_TYPE)
  BInit(2) : bc[4]\component1=10 : BCheck(AnvilVkIrVerify(@bm),#ANVIL_IR_ERR_TYPE)
  BInit(2) : bt[5]\componentType=1 : BCheck(AnvilVkIrVerify(@bm),#ANVIL_IR_ERR_TYPE)
  BInit(2) : bn[3]\resultType=7 : BCheck(AnvilVkIrVerify(@bm),#ANVIL_IR_ERR_TYPE)
  PokeI($E1C00008,bchecks) : PokeI($E1C00010,bfailed)
  ProcedureReturn bfailed
EndProcedure

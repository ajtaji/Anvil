; SPDX-License-Identifier: MIT
; Returning physical CPU checks for register lifetimes and alias ownership.
XIncludeFile "Anvil/Graphics/Vulkan/vk_ir_v3d42.pbi"
Global reuseModule.AvkIrModule
Global reuseNode.AvkIrNode
Global reuseConstant.AvkIrConstant
Global Dim reuseDotTypes.AvkIrType[2]
Global Dim reuseDotConstants.AvkIrConstant[2]
Global reuseDot.AvkIrNode
Global reuseChecks.i,reuseFailed.i
Procedure ReuseCheck(actual.i,expected.i)
  PokeI($E1C00040+reuseChecks*16,actual)
  PokeI($E1C00048+reuseChecks*16,expected)
  reuseChecks=reuseChecks+1
  If actual<>expected : reuseFailed=reuseFailed+1 : EndIf
EndProcedure
Procedure.i Main(services.i)
  Protected i.i
  For i=0 To 16383 : PokeA($E1C00000+i,0) : Next
  PokeI($E1C00000,$52555331)
  reuseModule\nodes=@reuseNode : reuseModule\nodeCount=1
  reuseModule\constants=@reuseConstant : reuseModule\constantCount=1
  reuseConstant\sourceId=13
  reuseNode\sourceId=20 : reuseNode\operandCount=1 : reuseNode\operand0=11
  avk42Live[20]=1 : avk42Reuse=1 : avk42FixedRegs=14 : avk42NextReg=24
  avk42DirectValue=30
  avk42SetRegs(10,2,14,15,0,0)
  avk42SetRegs(11,1,15,0,0,0)
  avk42SetRegs(12,1,16,0,0,0)
  avk42SetRegs(13,1,18,0,0,0)
  avk42SetRegs(30,4,20,21,22,23)
  avk42Reclaim(@reuseModule,0)
  ReuseCheck(avk42Count[10],0)
  ReuseCheck(avk42Count[11],1)
  ReuseCheck(avk42Count[12],0)
  ReuseCheck(avk42Count[13],1)
  ReuseCheck(avk42Count[30],4)
  ReuseCheck(avk42Occupied[13],1)
  ReuseCheck(avk42Occupied[14],0)
  ReuseCheck(avk42Occupied[15],1)
  ReuseCheck(avk42Occupied[18],1)
  ReuseCheck(avk42Occupied[23],1)
  ReuseCheck(avk42Alloc(2,40,129),16)
  ReuseCheck(avk42Alloc(1,41,129),14)
  ReuseCheck(avk42Alloc(4,42,129),24)
  ReuseCheck(avk42NextReg,28)
  avk42Reclaim(@reuseModule,1)
  ReuseCheck(avk42Count[11],0)
  ReuseCheck(avk42Count[30],4)
  ReuseCheck(avk42Occupied[24],0)
  ReuseCheck(avk42Occupied[18],1)
  ReuseCheck(avk42Alloc(2,43,129),14)
  ReuseCheck(avk42NextReg,28)
  For i=0 To 63 : avk42Occupied[i]=1 : Next
  ReuseCheck(avk42Alloc(1,44,129),#ANVIL_IR_V3D42_ERR_RANGE)
  ReuseCheck(avk42Alloc(0,45,129),#ANVIL_IR_V3D42_ERR_RANGE)
  ReuseCheck(avk42Alloc(5,46,129),#ANVIL_IR_V3D42_ERR_RANGE)
  avk42Reuse=0 : avk42NextReg=10
  ReuseCheck(avk42Alloc(2,47,129),10)
  ReuseCheck(avk42NextReg,12)
  ; Dot's accumulator need not immediately follow its temporary vector.
  For i=0 To 192 : avk42Count[i]=0 : Next
  For i=0 To 63 : avk42Occupied[i]=0 : Next
  avk42Reuse=1 : avk42FixedRegs=14 : avk42NextReg=20
  avk42Occupied[16]=1 : avk42Occupied[18]=1 : avk42Occupied[19]=1
  reuseDotTypes[0]\sourceId=3 : reuseDotTypes[0]\kind=#ANVIL_IR_TYPE_FLOAT
  reuseDotTypes[0]\width=32
  reuseDotTypes[1]\sourceId=4 : reuseDotTypes[1]\kind=#ANVIL_IR_TYPE_VECTOR
  reuseDotTypes[1]\componentType=3 : reuseDotTypes[1]\componentCount=2
  reuseDotConstants[0]\sourceId=10 : reuseDotConstants[0]\typeId=4
  reuseDotConstants[1]\sourceId=11 : reuseDotConstants[1]\typeId=4
  reuseModule\types=@reuseDotTypes[0] : reuseModule\typeCount=2
  reuseModule\constants=@reuseDotConstants[0] : reuseModule\constantCount=2
  avk42SetRegs(10,2,18,19,0,0) : avk42SetRegs(11,2,18,19,0,0)
  reuseDot\sourceId=40 : reuseDot\sourceOpcode=148
  reuseDot\operand0=10 : reuseDot\operand1=11
  ReuseCheck(V3dQpuProgramBeginSeg($E1C01000,1024,0),0)
  ReuseCheck(avk42EmitDot(@reuseModule,@reuseDot),0)
  ReuseCheck(avk42Reg[160],17)
  ReuseCheck(avk42Count[40],1)
  ReuseCheck(V3dQpuProgramBytes(),24)
  ReuseCheck(avk42Occupied[16],1)
  ; A later input load still borrows the original cached register map.
  reuseModule\nodeCount=0 : avk42DirectValue=0
  avk42SetRegs(50,2,24,25,0,0) : avk42InputValueId[0]=50
  avk42Reclaim(@reuseModule,0)
  ReuseCheck(avk42Count[50],2)
  ReuseCheck(avk42Occupied[24],1)
  ReuseCheck(avk42Occupied[25],1)
  avk42InputValueId[0]=0
  avk42Reclaim(@reuseModule,0)
  ReuseCheck(avk42Count[50],0)
  ReuseCheck(avk42Occupied[24],0)
  PokeI($E1C00008,reuseChecks) : PokeI($E1C00010,reuseFailed)
  ProcedureReturn reuseFailed
EndProcedure

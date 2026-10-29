; SPDX-License-Identifier: MIT
; Retained SPIR-V types, operands and strict refusal boundaries.
XIncludeFile "Anvil/Graphics/Vulkan/vk_spirv.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_ir.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_spirv_ir_adapter.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_spirv_fixtures.pbi"
Global Dim bpWords.l[512]
Global bpStore.AvkSpirvIrStorage
Global bpChecks.i,bpFailed.i
Global bpLess.i,bpSelect.i,bpTrue.i,bpBool.i,bpReturn.i
Procedure BPCheck(actual.i,expected.i)
  PokeI($E1C00040+bpChecks*16,actual) : PokeI($E1C00048+bpChecks*16,expected)
  bpChecks=bpChecks+1
  If actual<>expected : bpFailed=bpFailed+1 : EndIf
EndProcedure
Procedure.i BPBuild(lanes.i)
  Protected i.i,n.i=lanes,f.i=3,b.i=4,z.i=10,o.i=11,t.i=12,e.i=13,value.i=33
  If n=1 : n=2 : EndIf
  If lanes>1 : f=5 : b=6 : z=14 : o=15 : t=16 : e=17 : value=35 : EndIf
  vtpBuf=@bpWords[0] : vtpHeader(80)
  vtpIns(17,1) : vtpW(1)
  vtpIns(14,2) : vtpW(0) : vtpW(1)
  vtpIns(15,5) : vtpW(4) : vtpW(70) : vtpW($6E69616D) : vtpW(0) : vtpW(9)
  vtpIns(16,2) : vtpW(70) : vtpW(7)
  vtpIns(71,3) : vtpW(9) : vtpW(30) : vtpW(0)
  vtpIns(19,1) : vtpW(1)
  vtpIns(33,2) : vtpW(2) : vtpW(1)
  vtpIns(22,2) : vtpW(3) : vtpW(32)
  bpBool=vtpN : vtpIns(20,1) : vtpW(4)
  vtpIns(23,3) : vtpW(5) : vtpW(3) : vtpW(n)
  vtpIns(23,3) : vtpW(6) : vtpW(4) : vtpW(n)
  vtpIns(23,3) : vtpW(7) : vtpW(3) : vtpW(4)
  vtpIns(32,3) : vtpW(8) : vtpW(3) : vtpW(7)
  vtpIns(59,3) : vtpW(8) : vtpW(9) : vtpW(3)
  vtpIns(43,3) : vtpW(3) : vtpW(10) : vtpW(0)
  vtpIns(43,3) : vtpW(3) : vtpW(11) : vtpW($3F800000)
  bpTrue=vtpN : vtpIns(41,2) : vtpW(4) : vtpW(12)
  vtpIns(42,2) : vtpW(4) : vtpW(13)
  vtpIns(44,2+n) : vtpW(5) : vtpW(14) : For i=1 To n : vtpW(10) : Next
  vtpIns(44,2+n) : vtpW(5) : vtpW(15) : For i=1 To n : vtpW(11) : Next
  vtpIns(44,2+n) : vtpW(6) : vtpW(16) : For i=1 To n : vtpW(12) : Next
  vtpIns(44,2+n) : vtpW(6) : vtpW(17) : For i=1 To n : vtpW(13) : Next
  vtpIns(54,4) : vtpW(1) : vtpW(70) : vtpW(0) : vtpW(2)
  vtpIns(248,1) : vtpW(71)
  bpLess=vtpN : vtpIns(184,4) : vtpW(b) : vtpW(30) : vtpW(z) : vtpW(o)
  vtpIns(186,4) : vtpW(b) : vtpW(31) : vtpW(z) : vtpW(o)
  vtpIns(166,4) : vtpW(b) : vtpW(32) : vtpW(30) : vtpW(31)
  bpSelect=vtpN : vtpIns(169,5) : vtpW(f) : vtpW(33) : vtpW(32) : vtpW(z) : vtpW(o)
  vtpIns(169,5) : vtpW(b) : vtpW(34) : vtpW(32) : vtpW(t) : vtpW(e)
  If lanes>1 : vtpIns(81,4) : vtpW(3) : vtpW(35) : vtpW(33) : vtpW(0) : EndIf
  vtpIns(80,6) : vtpW(7) : vtpW(36) : vtpW(value) : vtpW(value) : vtpW(value) : vtpW(11)
  vtpIns(62,2) : vtpW(9) : vtpW(36)
  bpReturn=vtpN : vtpIns(253,0)
  vtpIns(56,0)
  ProcedureReturn vtpN*4
EndProcedure
Procedure.i Main(services.i)
  Protected i.i,lanes.i,bytes.i,rc.i,saved.i
  Protected *n.AvkIrNode
  Protected *t.AvkIrType
  Protected *c.AvkIrConstant
  For i=0 To 16383 : PokeA($E1C00000+i,0) : Next
  PokeI($E1C00000,$42535031)
  For lanes=1 To 4
    bytes=BPBuild(lanes)
    rc=avkSpvWalk(@bpWords[0],bytes,1) : BPCheck(rc,0)
    If rc<>0 : Goto BPDone : EndIf
    rc=AnvilVkSpirvIrAdapt(@bpStore) : BPCheck(rc,0)
    If rc<>0 : Goto BPDone : EndIf
    BPCheck(bpStore\valid,1) : BPCheck(AnvilVkIrVerify(@bpStore\module),0)
    *t=avkIrFindType(@bpStore\module,4) : BPCheck(*t\kind,10)
    *c=avkIrFindConstant(@bpStore\module,12) : BPCheck(*c\word0,1) : BPCheck(*c\wordCount,0)
    *c=avkIrFindConstant(@bpStore\module,13) : BPCheck(*c\word0,0)
    *n=avkIrFindNode(@bpStore\module,30) : BPCheck(*n\kind,16)
    *n=avkIrFindNode(@bpStore\module,31) : BPCheck(*n\kind,17)
    *n=avkIrFindNode(@bpStore\module,32) : BPCheck(*n\kind,18)
    *n=avkIrFindNode(@bpStore\module,33)
    BPCheck(*n\kind,19) : BPCheck(*n\operandCount,3) : BPCheck(*n\operand0,32)
    If lanes=1 : BPCheck(*n\operand1,10) : BPCheck(*n\operand2,11)
    Else : BPCheck(*n\operand1,14) : BPCheck(*n\operand2,15) : EndIf
    ; Failed parsing must not invalidate the copied, self-contained IR.
    bpWords[bpLess+3]=69
    BPCheck(avkSpvWalk(@bpWords[0],bytes,1),-20001)
    BPCheck(AnvilVkSpirvRecordsValid(),0)
    BPCheck(AnvilVkIrVerify(@bpStore\module),0)
    bytes=BPBuild(lanes)
    BPCheck(avkSpvWalk(@bpWords[0],bytes,0),-20005)
  Next
  bytes=BPBuild(2) : bpWords[bpSelect+3]=12
  BPCheck(avkSpvWalk(@bpWords[0],bytes,1),-20005)
  bpWords[1]=$00010400
  BPCheck(avkSpvWalk(@bpWords[0],bytes,1),0)
  BPCheck(AnvilVkSpirvIrAdapt(@bpStore),0)
  bytes=BPBuild(2) : bpWords[bpLess+1]=3
  BPCheck(avkSpvWalk(@bpWords[0],bytes,1),-20005)
  bytes=BPBuild(2) : bpWords[bpLess+2]=12
  BPCheck(avkSpvWalk(@bpWords[0],bytes,1),-20001)
  bytes=BPBuild(2) : bpWords[bpSelect+5]=12
  BPCheck(avkSpvWalk(@bpWords[0],bytes,1),-20005)
  bytes=BPBuild(2) : bpWords[bpLess]=(4<<16)|184
  BPCheck(avkSpvWalk(@bpWords[0],bytes,1),-20001)
  bytes=BPBuild(2) : bpWords[bpTrue+1]=3
  BPCheck(avkSpvWalk(@bpWords[0],bytes,1),-20005)
  bytes=BPBuild(2) : bpWords[bpBool]=(1<<16)|20
  BPCheck(avkSpvWalk(@bpWords[0],bytes,1),-20001)
  bytes=BPBuild(2) : bpWords[bpTrue]=(2<<16)|41
  BPCheck(avkSpvWalk(@bpWords[0],bytes,1),-20001)
  ; A comparison after the terminator is refused before publication.
  bytes=BPBuild(2) : vtpN=bpReturn+1
  vtpIns(184,4) : vtpW(4) : vtpW(40) : vtpW(10) : vtpW(11) : vtpIns(56,0)
  BPCheck(avkSpvWalk(@bpWords[0],vtpN*4,1),-20005)
  BPDone:
  PokeI($E1C00008,bpChecks) : PokeI($E1C00010,bpFailed)
  ProcedureReturn bpFailed
EndProcedure

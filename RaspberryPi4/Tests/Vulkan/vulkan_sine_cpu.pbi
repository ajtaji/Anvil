; Returning physical CPU qualification: retained SPIR-V -> typed IR -> QPU.
; LoadSineCase is generated from independent host SPIR-V fixtures.
XIncludeFile "Anvil/Graphics/Vulkan/vk_spirv.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_ir_v3d42.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_spirv_ir_adapter.pbi"
Global Dim subWords.l[1024]
Global subStorage.AvkSpirvIrStorage
Global subRecord.AvkSpvRecord
Global subTarget.AvkIrV3d42Target
Global subOutput.AvkIrV3d42Io
Global subResult.AvkIrV3d42Result

Procedure.i Main(services.i)
  Protected trial.i,bytes.i,rc.i,adapt.i,b.i,i.i,j.i,magic.i,failed.i
  Protected *n.AvkIrNode
  For i=0 To 16383 : PokeA($E1C00000+i,0) : Next
  PokeI($E1C00000,$53494E31) : PokeI($E1C00008,12)
  For trial=0 To 11
    bytes=LoadSineCase(trial,@subWords[0])
    For j=0 To SizeOf(AvkSpirvIrStorage)-1 : PokeA(@subStorage+j,$A5) : Next
    rc=AnvilVkSpirvWalkIr(@subWords[0],bytes)
    b=$E1C00040+trial*192
    PokeI(b,rc) : PokeI(b+8,AnvilVkSpirvRecordsValid())
    PokeL(@subWords[0],0)
    magic=0 : PokeI(b+32,AnvilVkSpirvRecordWordRead(0,@magic)) : PokeI(b+40,magic)
    For i=0 To AnvilVkSpirvRecordCount()-1
      AnvilVkSpirvRecordRead(i,@subRecord)
      If subRecord\sourceOpcode=12
        PokeI(b+48,subRecord\sourceId) : PokeI(b+56,subRecord\sourceOpcode)
        PokeI(b+64,subRecord\resultType) : PokeI(b+72,subRecord\idCount)
        PokeI(b+80,subRecord\id0) : PokeI(b+88,subRecord\id1)
      EndIf
    Next
    adapt=AnvilVkSpirvIrAdapt(@subStorage)
    PokeI(b+16,adapt) : PokeI(b+24,subStorage\valid)
    If trial<4 And rc=0 And adapt=0
      *n=avkIrFindNode(@subStorage\module,PeekI(b+48))
      If *n=0 : failed=failed+1 : Continue : EndIf
      PokeI(b+96,*n\kind) : PokeI(b+104,*n\resultType)
      PokeI(b+112,*n\sourceId) : PokeI(b+120,*n\operand0) : PokeI(b+128,*n\operand1)
      For i=0 To SizeOf(AvkIrV3d42Target)-1 : PokeA(@subTarget+i,0) : Next
      subOutput\member=-1 : subOutput\firstSlot=0 : subOutput\components=4
      For i=0 To subStorage\module\variableCount-1
        Protected *v.AvkIrVariable
        *v=avkIrVariableAt(@subStorage\module,i)
        If *v\storageClass=3 : subOutput\variableId=*v\sourceId : EndIf
      Next
      subTarget\role=2 : subTarget\outputs=@subOutput : subTarget\outputCount=1
      subTarget\codeBase=$E1C01000+trial*1024 : subTarget\codeCapacity=1024
      subTarget\uniformBase=$E1C02000+trial*256 : subTarget\uniformCapacity=256
      subTarget\tlbConfig=$FFFFFFFF
      rc=AnvilVkIrV3d42Lower(@subStorage\module,@subTarget,@subResult)
      PokeI(b+136,rc) : PokeI(b+144,subResult\codeBytes)
      PokeI(b+152,subResult\uniformWords) : PokeI(b+160,subResult\registerCount)
      *n\operandCount=2
      PokeI(b+168,AnvilVkIrVerify(@subStorage\module))
      *n\operandCount=1 : *n\operand0=*n\sourceId
      PokeI(b+176,AnvilVkIrVerify(@subStorage\module))
      PokeI(b+184,AnvilVkIrV3d42Stage())
      If rc<>0 : failed=failed+1 : EndIf
    ElseIf trial<4 Or rc=0 Or adapt=0 Or subStorage\valid<>0
      failed=failed+1
    EndIf
  Next
  PokeI($E1C00010,failed)
  ProcedureReturn failed
EndProcedure

; SPIR-V retained semantic records -> passive typed IR.
; Include vk_spirv.pbi, then vk_ir.pbi, then this file.
; SPDX-License-Identifier: MIT

#ANVIL_SPV_IR_ERR_RECORD = -23301
#ANVIL_SPV_IR_ERR_RANGE  = -23302

; Compute analysis is deliberately separate from the legacy graphics walker.
; Its output is passive typed dataflow, never a public shader-module success.
#ANVIL_COMPUTE_ERR = -23401
#AVK_CTYPE_VOID = 1
#AVK_CTYPE_UINT = 2
#AVK_CTYPE_SINT = 3
#AVK_CTYPE_FLOAT = 4
#AVK_CTYPE_VECTOR = 5
#AVK_CTYPE_STRUCT = 6
#AVK_CTYPE_RUNTIME = 7
#AVK_CTYPE_POINTER = 8
#AVK_CTYPE_FUNCTION = 9
#AVK_CVALUE_POINTER = 1
#AVK_CVALUE_INT = 2
#AVK_CVALUE_FLOAT = 3
#AVK_CVALUE_COMPOSITE = 4
#AVK_CVALUE_META = 5

Structure AvkComputeSlot Align #PB_Structure_AlignC
  typeKind.i
  elem.i
  count.i
  storage.i
  stride.i
  bufferBlock.i
  builtin.i
  binding.i
  descriptorSet.i
  nonWritable.i
  nonReadable.i
  decorated.i
  memberDecorationMask.i
  named.i
  memberNameMask.i
  valueKind.i
  valueType.i
  base.i
  scale.i
  offset.i
  sourceKind.i
  bits.i
EndStructure

Global Dim avkComputeSlot.AvkComputeSlot[#ANVIL_SPV_MAX_ID]
Global Dim avkCMType.i[#ANVIL_SPV_MAX_ID*4+3]
Global Dim avkCMOffset.i[#ANVIL_SPV_MAX_ID*4+3]
Global avkComputeLastPos.i
Global avkComputeLastOpcode.i

Procedure avkComputeClear(*where, bytes.i)
  Protected j.i
  For j=0 To bytes-1
    PokeA(*where+j,0)
  Next
EndProcedure

Procedure.i avkComputeWord(*code, word.i)
  ProcedureReturn PeekL(*code + word * 4) & $FFFFFFFF
EndProcedure

Procedure.i avkComputeId(id.i, bound.i)
  If (id > 0) & (id < bound)
         ProcedureReturn 1
         EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i avkComputeFloatType(typeId.i)
  If (typeId > 0) & (avkComputeSlot(typeId)\typeKind = #AVK_CTYPE_FLOAT)
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

; Converts an entire straight-line GLCompute function into an affine,
; typed summary. Every accepted executable opcode contributes to the result.
; Array bounds, descriptor layout and SSA dependencies are checked before a
; store is recorded. No opcode is accepted by binary identity or source ID.
Procedure.i AnvilVkSpirvComputeAdapt(*code, bytes.i, *out.AvkComputeIr)
  Protected bound.i, words.i, pos.i, wc.i, op.i, dispatchOp.i, a.i, b.i, c.i, d.i
  Protected id.i, ty.i, elem.i, idx.i, member.i, current.i, base.i
  Protected scale.i, off.i, k.i, value.i, source.i, target.i
  Protected entryId.i, functionId.i, localSeen.i, entrySeen.i, modelSeen.i
  Protected capabilitySeen.i, functionSeen.i, labelSeen.i, returnSeen.i
  Protected functionEndSeen.i, inputVar.i, outputVar.i, builtinVar.i
  Protected inputArray.i, outputArray.i, inputRecord.i, inputType.i
  Protected outputType.i, inputPtr.i, outputPtr.i, hasTerminator.i
  Protected functionType.i, nameEnd.i, terminated.i, storeCount.i
  Protected *slot.AvkComputeSlot, *other.AvkComputeSlot
  If *out = 0
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
  avkComputeClear(*out,SizeOf(AvkComputeIr))
  If (*code = 0) | (bytes < 20) | ((bytes & 3) <> 0) | (bytes > #ANVIL_SPV_MAX_WORDS * 4)
    ProcedureReturn #ANVIL_COMPUTE_ERR
  EndIf
  words = bytes / 4
  If (avkComputeWord(*code,0) <> #ANVIL_SPV_MAGIC) | (avkComputeWord(*code,1) < $00010000) | (avkComputeWord(*code,1) > #ANVIL_SPV_VERSION_MAX) | (avkComputeWord(*code,4) <> 0)
    ProcedureReturn #ANVIL_COMPUTE_ERR
  EndIf
  bound = avkComputeWord(*code,3)
  If (bound < 2) | (bound > #ANVIL_SPV_MAX_ID)
    ProcedureReturn #ANVIL_COMPUTE_ERR
  EndIf
  For id=0 To #ANVIL_SPV_MAX_ID
    avkComputeClear(@avkComputeSlot(id),SizeOf(AvkComputeSlot))
    avkComputeSlot(id)\builtin=-1
    avkComputeSlot(id)\binding=-1
    avkComputeSlot(id)\descriptorSet=-1
    avkComputeSlot(id)\stride=-1
    For k=0 To 3
      avkCMType(id*4+k)=0
      avkCMOffset(id*4+k)=-1
    Next
  Next
  pos=5
  While pos < words
    wc=avkComputeWord(*code,pos) >> 16
    op=avkComputeWord(*code,pos) & $FFFF
    avkComputeLastPos=pos
    avkComputeLastOpcode=op
    If (wc < 1) | (pos + wc > words) | (functionEndSeen)
      ProcedureReturn #ANVIL_COMPUTE_ERR
    EndIf
    a=0
        b=0
        c=0
        d=0
    If wc > 1
         a=avkComputeWord(*code,pos+1)
         EndIf
    If wc > 2
         b=avkComputeWord(*code,pos+2)
         EndIf
    If wc > 3
         c=avkComputeWord(*code,pos+3)
         EndIf
    If wc > 4
         d=avkComputeWord(*code,pos+4)
         EndIf
    ; Reject physical IDs before any table lookup. Bitwise condition operators
    ; below are eager, so a compound test alone is not an OOB guard.
    If (op=#SpvOpExtInstImport) | (op=#SpvOpDecorate) | (op=#SpvOpMemberDecorate) | (op=#SpvOpName) | (op=#SpvOpMemberName) | (op=#SpvOpTypeVoid) | (op=#SpvOpTypeInt) | (op=#SpvOpTypeFloat) | (op=#SpvOpTypeVector) | (op=#SpvOpTypeStruct) | (op=#SpvOpTypeRuntimeArray) | (op=#SpvOpTypePointer) | (op=#SpvOpTypeFunction) | (op=#SpvOpLabel) | (op=#SpvOpExecutionMode)
      If Not avkComputeId(a,bound) : ProcedureReturn #ANVIL_COMPUTE_ERR : EndIf
    EndIf
    If (op=#SpvOpEntryPoint) | (op=#SpvOpConstant) | (op=#SpvOpConstantComposite) | (op=#SpvOpVariable) | (op=#SpvOpFunction) | (op=#SpvOpAccessChain) | (op=#SpvOpLoad) | (op=#SpvOpCompositeExtract) | (op=#SpvOpIAdd) | (op=#SpvOpIMul) | (op=#SpvOpStore)
      If Not avkComputeId(b,bound) : ProcedureReturn #ANVIL_COMPUTE_ERR : EndIf
    EndIf
    If (op=#SpvOpConstant) | (op=#SpvOpConstantComposite) | (op=#SpvOpVariable) | (op=#SpvOpFunction) | (op=#SpvOpAccessChain) | (op=#SpvOpLoad) | (op=#SpvOpCompositeExtract) | (op=#SpvOpIAdd) | (op=#SpvOpIMul) | (op=#SpvOpStore)
      If Not avkComputeId(a,bound) : ProcedureReturn #ANVIL_COMPUTE_ERR : EndIf
    EndIf
    If (op=#SpvOpTypePointer) | (op=#SpvOpAccessChain) | (op=#SpvOpLoad) | (op=#SpvOpCompositeExtract) | (op=#SpvOpIAdd) | (op=#SpvOpIMul)
      If Not avkComputeId(c,bound) : ProcedureReturn #ANVIL_COMPUTE_ERR : EndIf
    EndIf
    If (op=#SpvOpTypeVector) | (op=#SpvOpTypeRuntimeArray) | (op=#SpvOpTypeFunction) | (op=#SpvOpTypeStruct)
      If Not avkComputeId(b,bound) : ProcedureReturn #ANVIL_COMPUTE_ERR : EndIf
    EndIf
    If (op=#SpvOpFunction) | (op=#SpvOpIAdd) | (op=#SpvOpIMul)
      If Not avkComputeId(d,bound) : ProcedureReturn #ANVIL_COMPUTE_ERR : EndIf
    EndIf
    If op=#SpvOpTypeStruct
      For k=2 To wc-1
        If Not avkComputeId(avkComputeWord(*code,pos+k),bound) : ProcedureReturn #ANVIL_COMPUTE_ERR : EndIf
      Next
    EndIf
    If op=#SpvOpConstantComposite
      For k=3 To wc-1
        If Not avkComputeId(avkComputeWord(*code,pos+k),bound) : ProcedureReturn #ANVIL_COMPUTE_ERR : EndIf
      Next
    EndIf
    If op=#SpvOpAccessChain
      For k=4 To wc-1
        If Not avkComputeId(avkComputeWord(*code,pos+k),bound) : ProcedureReturn #ANVIL_COMPUTE_ERR : EndIf
      Next
    EndIf
    dispatchOp=op
    If (op=#SpvOpTypeInt) | (op=#SpvOpTypeFloat) | (op=#SpvOpTypeVector) | (op=#SpvOpTypeStruct) | (op=#SpvOpTypeRuntimeArray) | (op=#SpvOpTypePointer) | (op=#SpvOpTypeFunction)
      dispatchOp=#SpvOpTypeVoid
    EndIf
    If op=#SpvOpIMul
      dispatchOp=#SpvOpIAdd
    EndIf
    Select dispatchOp
      Case #SpvOpCapability
        If (wc <> 2) | (a <> #SpvCapabilityShader) | (capabilitySeen) | (functionSeen)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
        capabilitySeen=1
      Case #SpvOpExtInstImport
        ; An unused extended-instruction import is valid metadata.
        If (wc < 3) | (Not avkComputeId(a,bound)) | (functionSeen) | (avkComputeSlot(a)\valueKind <> 0) | (avkComputeSlot(a)\typeKind <> 0)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
        avkComputeSlot(a)\valueKind=#AVK_CVALUE_META
      Case #SpvOpMemoryModel
        If (wc <> 3) | (a <> #SpvAddressingModelLogical) | (b <> #SpvMemoryModelGLSL450) | (modelSeen) | (functionSeen)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
        modelSeen=1
      Case #SpvOpEntryPoint
        If (wc < 6) | (a <> #SpvExecutionModelGLCompute) | (Not avkComputeId(b,bound)) | (entrySeen) | (functionSeen)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
        ; Pipeline creation currently names only main. Require the module's
        ; actual NUL-terminated entry name, not merely a caller-supplied name.
        If wc <> 6 Or avkComputeWord(*code,pos+3) <> $6E69616D Or avkComputeWord(*code,pos+4) <> 0
         ProcedureReturn #ANVIL_COMPUTE_ERR
        EndIf
        nameEnd=3
        While nameEnd < wc
          value=avkComputeWord(*code,pos+nameEnd)
          nameEnd=nameEnd+1
          If ((value & $FF)=0) | ((value & $FF00)=0) | ((value & $FF0000)=0) | ((value & $FF000000)=0)
         Break
         EndIf
        Wend
        If (nameEnd >= wc) | (wc-nameEnd <> 1)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
        builtinVar=avkComputeWord(*code,pos+nameEnd)
        If Not avkComputeId(builtinVar,bound)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
        entryId = b
        entrySeen = 1
      Case #SpvOpExecutionMode
        If (wc <> 6) | (a <> entryId) | (b <> #SpvExecutionModeLocalSize) | (localSeen) | (c <> 16) | (d <> 1) | (avkComputeWord(*code,pos+5) <> 1)
          ProcedureReturn #ANVIL_COMPUTE_ERR
        EndIf
        *out\localX=c
        *out\localY=d
        *out\localZ=1
        localSeen=1
      Case #SpvOpSource
        If (functionSeen) | (wc < 3)
          ProcedureReturn #ANVIL_COMPUTE_ERR
        EndIf
      Case #SpvOpName
        If (functionSeen) | (wc < 3)
          ProcedureReturn #ANVIL_COMPUTE_ERR
        EndIf
        nameEnd=2
        terminated=0
        While nameEnd < wc
          value=avkComputeWord(*code,pos+nameEnd)
          nameEnd=nameEnd+1
          If ((value & $FF)=0) | ((value & $FF00)=0) | ((value & $FF0000)=0) | ((value & $FF000000)=0)
            terminated=1
            Break
          EndIf
        Wend
        If (terminated=0) | (nameEnd <> wc)
          ProcedureReturn #ANVIL_COMPUTE_ERR
        EndIf
        avkComputeSlot(a)\named=1
      Case #SpvOpMemberName
        If (functionSeen) | (wc < 4) | (b > 3)
          ProcedureReturn #ANVIL_COMPUTE_ERR
        EndIf
        nameEnd=3
        terminated=0
        While nameEnd < wc
          value=avkComputeWord(*code,pos+nameEnd)
          nameEnd=nameEnd+1
          If ((value & $FF)=0) | ((value & $FF00)=0) | ((value & $FF0000)=0) | ((value & $FF000000)=0)
            terminated=1
            Break
          EndIf
        Wend
        If (terminated=0) | (nameEnd <> wc)
          ProcedureReturn #ANVIL_COMPUTE_ERR
        EndIf
        avkComputeSlot(a)\memberNameMask=avkComputeSlot(a)\memberNameMask | (1 << b)
      Case #SpvOpDecorate
        If (wc < 3) | (Not avkComputeId(a,bound)) | (functionSeen)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
        *slot=@avkComputeSlot(a)
        *slot\decorated=1
        Select b
          Case #SpvDecorationBuiltIn
            If (wc <> 4) | (*slot\builtin >= 0)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
            *slot\builtin=c
          Case #SpvDecorationArrayStride
            If (wc <> 4) | (*slot\stride >= 0) | (c < 1) | (c > 256)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
            *slot\stride=c
          Case #SpvDecorationBufferBlock
            If (wc <> 3) | (*slot\bufferBlock)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
            *slot\bufferBlock=1
          Case #SpvDecorationNonWritable
            If (wc <> 3) | (*slot\nonWritable)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
            *slot\nonWritable=1
          Case #SpvDecorationNonReadable
            If (wc <> 3) | (*slot\nonReadable)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
            *slot\nonReadable=1
          Case #SpvDecorationBinding
            If (wc <> 4) | (*slot\binding >= 0)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
            *slot\binding=c
          Case #SpvDecorationDescriptorSet
            If (wc <> 4) | (*slot\descriptorSet >= 0)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
            *slot\descriptorSet=c
          Default
            ProcedureReturn #ANVIL_COMPUTE_ERR
        EndSelect
      Case #SpvOpMemberDecorate
        If (Not avkComputeId(a,bound)) | (functionSeen)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
        If b > 3
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
        avkComputeSlot(a)\decorated=1
        avkComputeSlot(a)\memberDecorationMask=avkComputeSlot(a)\memberDecorationMask | (1 << b)
        If c = #SpvDecorationOffset
          If (wc <> 5) | (avkCMOffset((a)*4+b) >= 0)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
          avkCMOffset((a)*4+b)=d
        ElseIf (c = #SpvDecorationNonWritable) | (c = #SpvDecorationNonReadable)
          If (wc <> 4) | (b <> 0)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
          If c = #SpvDecorationNonWritable
         avkComputeSlot(a)\nonWritable=1
         Else
         avkComputeSlot(a)\nonReadable=1
         EndIf
        Else
          ProcedureReturn #ANVIL_COMPUTE_ERR
        EndIf
      Case #SpvOpTypeVoid
        id=a
        If (Not avkComputeId(id,bound)) | (avkComputeSlot(id)\typeKind) | (avkComputeSlot(id)\valueKind) | (functionSeen)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
        *slot=@avkComputeSlot(id)
        Select op
          Case #SpvOpTypeVoid
            If wc <> 2
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
            *slot\typeKind=#AVK_CTYPE_VOID
          Case #SpvOpTypeInt
            If (wc <> 4) | (b <> 32) | (c > 1)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
            If c=0
         *slot\typeKind=#AVK_CTYPE_UINT
         Else
         *slot\typeKind=#AVK_CTYPE_SINT
         EndIf
          Case #SpvOpTypeFloat
            If (wc <> 3) | (b <> 32)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
            *slot\typeKind=#AVK_CTYPE_FLOAT
          Case #SpvOpTypeVector
            If (wc <> 4) | (Not avkComputeId(b,bound)) | (c < 2) | (c > 4)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
             If (avkComputeSlot(b)\typeKind <> #AVK_CTYPE_FLOAT) & (avkComputeSlot(b)\typeKind <> #AVK_CTYPE_UINT)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
            *slot\typeKind=#AVK_CTYPE_VECTOR
        *slot\elem=b
        *slot\count=c
          Case #SpvOpTypeStruct
            If (wc < 3) | (wc > 6)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
            *slot\typeKind=#AVK_CTYPE_STRUCT
        *slot\count=wc-2
            If (Not avkComputeId(b,bound)) | (avkComputeSlot(b)\typeKind=0)
              ProcedureReturn #ANVIL_COMPUTE_ERR
            EndIf
            avkCMType(id*4+0)=b
            If wc > 3
              If (Not avkComputeId(c,bound)) | (avkComputeSlot(c)\typeKind=0)
              ProcedureReturn #ANVIL_COMPUTE_ERR
              EndIf
              avkCMType(id*4+1)=c
            EndIf
            If wc > 4
              If (Not avkComputeId(d,bound)) | (avkComputeSlot(d)\typeKind=0)
              ProcedureReturn #ANVIL_COMPUTE_ERR
              EndIf
              avkCMType(id*4+2)=d
            EndIf
            If wc > 5
              value=avkComputeWord(*code,pos+5)
              If (Not avkComputeId(value,bound)) | (avkComputeSlot(value)\typeKind=0)
              ProcedureReturn #ANVIL_COMPUTE_ERR
              EndIf
              avkCMType(id*4+3)=value
            EndIf
          Case #SpvOpTypeRuntimeArray
            If (wc <> 3) | (Not avkComputeId(b,bound)) | (avkComputeSlot(b)\typeKind=0)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
            *slot\typeKind=#AVK_CTYPE_RUNTIME
        *slot\elem=b
          Case #SpvOpTypePointer
            If (wc <> 4) | (Not avkComputeId(c,bound)) | (avkComputeSlot(c)\typeKind=0)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
             If (b <> #SpvStorageClassInput) & (b <> #SpvStorageClassUniform)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
            *slot\typeKind=#AVK_CTYPE_POINTER
        *slot\elem=c
        *slot\storage=b
          Case #SpvOpTypeFunction
            If (wc <> 3) | (Not avkComputeId(b,bound)) | (avkComputeSlot(b)\typeKind <> #AVK_CTYPE_VOID)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
            *slot\typeKind=#AVK_CTYPE_FUNCTION
        *slot\elem=b
        EndSelect
      Case #SpvOpConstant
        If (wc <> 4) | (Not avkComputeId(a,bound)) | (Not avkComputeId(b,bound)) | (avkComputeSlot(b)\valueKind) | (avkComputeSlot(b)\typeKind) | (functionSeen)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
        If avkComputeSlot(a)\typeKind=#AVK_CTYPE_FLOAT
          avkComputeSlot(b)\valueKind=#AVK_CVALUE_FLOAT
        ElseIf (avkComputeSlot(a)\typeKind=#AVK_CTYPE_UINT) | (avkComputeSlot(a)\typeKind=#AVK_CTYPE_SINT)
          avkComputeSlot(b)\valueKind=#AVK_CVALUE_INT
        Else
          ProcedureReturn #ANVIL_COMPUTE_ERR
        EndIf
        avkComputeSlot(b)\valueType=a
        avkComputeSlot(b)\bits=c
        avkComputeSlot(b)\offset=c
      Case #SpvOpConstantComposite
        If (wc <> 6) | (functionSeen) | (Not avkComputeId(a,bound)) | (Not avkComputeId(b,bound)) | (avkComputeSlot(b)\valueKind) | (avkComputeSlot(b)\typeKind) | (avkComputeSlot(a)\typeKind <> #AVK_CTYPE_VECTOR) | (avkComputeSlot(a)\count <> 3) | (avkComputeSlot(avkComputeSlot(a)\elem)\typeKind <> #AVK_CTYPE_UINT)
          ProcedureReturn #ANVIL_COMPUTE_ERR
        EndIf
        For k=3 To 5
          value=avkComputeWord(*code,pos+k)
          If (Not avkComputeId(value,bound)) | (avkComputeSlot(value)\valueKind <> #AVK_CVALUE_INT) | (avkComputeSlot(value)\valueType <> avkComputeSlot(a)\elem)
            ProcedureReturn #ANVIL_COMPUTE_ERR
          EndIf
        Next
        If avkComputeSlot(b)\builtin=#SpvBuiltInWorkgroupSize
          If (avkComputeSlot(c)\offset <> 16) | (avkComputeSlot(d)\offset <> 1) | (avkComputeSlot(avkComputeWord(*code,pos+5))\offset <> 1)
            ProcedureReturn #ANVIL_COMPUTE_ERR
          EndIf
        ElseIf avkComputeSlot(b)\builtin >= 0
          ProcedureReturn #ANVIL_COMPUTE_ERR
        EndIf
        avkComputeSlot(b)\valueKind=#AVK_CVALUE_COMPOSITE
        avkComputeSlot(b)\valueType=a
      Case #SpvOpVariable
        If (wc <> 4) | (functionSeen) | (Not avkComputeId(a,bound)) | (Not avkComputeId(b,bound)) | (avkComputeSlot(b)\valueKind) | (avkComputeSlot(b)\typeKind) | (avkComputeSlot(a)\typeKind <> #AVK_CTYPE_POINTER) | (avkComputeSlot(a)\storage <> c)
          ProcedureReturn #ANVIL_COMPUTE_ERR
        EndIf
        avkComputeSlot(b)\valueKind=#AVK_CVALUE_POINTER
        avkComputeSlot(b)\valueType=a
        avkComputeSlot(b)\base=b
        If b <> builtinVar
          If (avkComputeSlot(b)\descriptorSet <> 0) | (avkComputeSlot(a)\storage <> #SpvStorageClassUniform)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
          If avkComputeSlot(b)\binding=0
            If inputVar
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
            inputVar=b
        inputType=avkComputeSlot(a)\elem
            If avkComputeSlot(inputType)\typeKind <> #AVK_CTYPE_STRUCT
              ProcedureReturn #ANVIL_COMPUTE_ERR
            EndIf
            inputArray=avkCMType((inputType)*4+0)
            inputRecord=avkComputeSlot(inputArray)\elem
          ElseIf avkComputeSlot(b)\binding=1
            If outputVar
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
            outputVar=b
        outputType=avkComputeSlot(a)\elem
          Else
            ProcedureReturn #ANVIL_COMPUTE_ERR
          EndIf
        EndIf
      Case #SpvOpFunction
        If (wc <> 5) | (functionSeen) | (Not avkComputeId(a,bound)) | (Not avkComputeId(b,bound)) | (b <> entryId) | (c <> 0) | (Not avkComputeId(d,bound)) | (avkComputeSlot(a)\typeKind <> #AVK_CTYPE_VOID) | (avkComputeSlot(d)\typeKind <> #AVK_CTYPE_FUNCTION) | (avkComputeSlot(d)\elem <> a)
          ProcedureReturn #ANVIL_COMPUTE_ERR
        EndIf
        If (avkComputeSlot(b)\valueKind <> 0) | (avkComputeSlot(b)\typeKind <> 0)
          ProcedureReturn #ANVIL_COMPUTE_ERR
        EndIf
        avkComputeSlot(b)\valueKind=#AVK_CVALUE_META
        functionId=b
        functionType=d
        functionSeen=1
      Case #SpvOpLabel
        If (wc <> 2) | (Not functionSeen) | (labelSeen) | (Not avkComputeId(a,bound)) | (avkComputeSlot(a)\valueKind <> 0) | (avkComputeSlot(a)\typeKind <> 0)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
        avkComputeSlot(a)\valueKind=#AVK_CVALUE_META
        labelSeen=1
      Case #SpvOpAccessChain
        If (wc < 5) | (Not labelSeen) | (returnSeen) | (Not avkComputeId(a,bound)) | (Not avkComputeId(b,bound)) | (Not avkComputeId(c,bound)) | (avkComputeSlot(b)\valueKind) | (avkComputeSlot(b)\typeKind) | (avkComputeSlot(a)\typeKind <> #AVK_CTYPE_POINTER) | (avkComputeSlot(c)\valueKind <> #AVK_CVALUE_POINTER)
          ProcedureReturn #ANVIL_COMPUTE_ERR
        EndIf
        current=avkComputeSlot(avkComputeSlot(c)\valueType)\elem
        base=avkComputeSlot(c)\base
        scale=avkComputeSlot(c)\scale
        off=avkComputeSlot(c)\offset
        For k=4 To wc-1
          idx=avkComputeWord(*code,pos+k)
          If (Not avkComputeId(idx,bound)) | (avkComputeSlot(idx)\valueKind <> #AVK_CVALUE_INT)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
          Select avkComputeSlot(current)\typeKind
            Case #AVK_CTYPE_STRUCT
              If (avkComputeSlot(idx)\scale <> 0) | (avkComputeSlot(idx)\offset >= avkComputeSlot(current)\count)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
              member=avkComputeSlot(idx)\offset
              If avkCMOffset((current)*4+member) < 0
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
              off=off+avkCMOffset((current)*4+member)
              current=avkCMType((current)*4+member)
            Case #AVK_CTYPE_RUNTIME
              If avkComputeSlot(current)\stride < 1
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
              scale=scale+avkComputeSlot(idx)\scale * avkComputeSlot(current)\stride
              off=off+avkComputeSlot(idx)\offset * avkComputeSlot(current)\stride
              current=avkComputeSlot(current)\elem
            Case #AVK_CTYPE_VECTOR
              If (avkComputeSlot(idx)\scale <> 0) | (avkComputeSlot(idx)\offset >= avkComputeSlot(current)\count)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
              off=off+avkComputeSlot(idx)\offset*4
              current=avkComputeSlot(current)\elem
            Default
              ProcedureReturn #ANVIL_COMPUTE_ERR
          EndSelect
          If (scale > 4096) | (off > 4096)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
        Next
        If (current <> avkComputeSlot(a)\elem) | (avkComputeSlot(a)\storage <> avkComputeSlot(avkComputeSlot(c)\valueType)\storage)
          ProcedureReturn #ANVIL_COMPUTE_ERR
        EndIf
        avkComputeSlot(b)\valueKind=#AVK_CVALUE_POINTER
        avkComputeSlot(b)\valueType=a
        avkComputeSlot(b)\base=base
        avkComputeSlot(b)\scale=scale
        avkComputeSlot(b)\offset=off
      Case #SpvOpLoad
        If (wc <> 4) | (Not labelSeen) | (returnSeen) | (Not avkComputeId(a,bound)) | (Not avkComputeId(b,bound)) | (Not avkComputeId(c,bound)) | (avkComputeSlot(b)\valueKind) | (avkComputeSlot(b)\typeKind) | (avkComputeSlot(c)\valueKind <> #AVK_CVALUE_POINTER) | (avkComputeSlot(avkComputeSlot(c)\valueType)\elem <> a)
          ProcedureReturn #ANVIL_COMPUTE_ERR
        EndIf
        If (avkComputeSlot(c)\base=builtinVar) & (avkComputeSlot(a)\typeKind=#AVK_CTYPE_UINT) & (avkComputeSlot(c)\offset=0) & (avkComputeSlot(c)\scale=0)
          avkComputeSlot(b)\valueKind=#AVK_CVALUE_INT
        avkComputeSlot(b)\scale=1
        avkComputeSlot(b)\offset=0
        ElseIf (avkComputeSlot(c)\base=inputVar) & (a=inputRecord) & (avkComputeSlot(c)\scale=48) & (avkComputeSlot(c)\offset=0)
          avkComputeSlot(b)\valueKind=#AVK_CVALUE_COMPOSITE
        avkComputeSlot(b)\scale=48
        avkComputeSlot(b)\offset=0
        avkComputeSlot(b)\sourceKind=#ANVIL_COMPUTE_SOURCE_INPUT
        Else
          ProcedureReturn #ANVIL_COMPUTE_ERR
        EndIf
        avkComputeSlot(b)\valueType=a
      Case #SpvOpCompositeExtract
        If (wc <> 5) | (Not labelSeen) | (returnSeen) | (Not avkComputeId(a,bound)) | (Not avkComputeId(b,bound)) | (Not avkComputeId(c,bound)) | (avkComputeSlot(b)\valueKind) | (avkComputeSlot(b)\typeKind) | (avkComputeSlot(c)\valueKind <> #AVK_CVALUE_COMPOSITE) | (avkComputeSlot(c)\sourceKind <> #ANVIL_COMPUTE_SOURCE_INPUT)
          ProcedureReturn #ANVIL_COMPUTE_ERR
        EndIf
        current=avkComputeSlot(c)\valueType
        If avkComputeSlot(current)\typeKind=#AVK_CTYPE_STRUCT
          If d >= avkComputeSlot(current)\count
            ProcedureReturn #ANVIL_COMPUTE_ERR
          EndIf
          If avkCMOffset(current*4+d) < 0
            ProcedureReturn #ANVIL_COMPUTE_ERR
          EndIf
          off=avkComputeSlot(c)\offset+avkCMOffset((current)*4+d)
          current=avkCMType((current)*4+d)
        ElseIf avkComputeSlot(current)\typeKind=#AVK_CTYPE_VECTOR
          If d >= avkComputeSlot(current)\count
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
          off=avkComputeSlot(c)\offset+d*4
          current=avkComputeSlot(current)\elem
        Else
          ProcedureReturn #ANVIL_COMPUTE_ERR
        EndIf
        If (current <> a) | (off >= 48)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
        avkComputeSlot(b)\valueType=a
        avkComputeSlot(b)\offset=off
        avkComputeSlot(b)\scale=avkComputeSlot(c)\scale
        avkComputeSlot(b)\sourceKind=#ANVIL_COMPUTE_SOURCE_INPUT
        If avkComputeSlot(a)\typeKind=#AVK_CTYPE_VECTOR
          avkComputeSlot(b)\valueKind=#AVK_CVALUE_COMPOSITE
        ElseIf avkComputeFloatType(a)
          avkComputeSlot(b)\valueKind=#AVK_CVALUE_FLOAT
        Else
          ProcedureReturn #ANVIL_COMPUTE_ERR
        EndIf
      Case #SpvOpIAdd
        If (wc <> 5) | (Not labelSeen) | (returnSeen) | (Not avkComputeId(a,bound)) | (Not avkComputeId(b,bound)) | (Not avkComputeId(c,bound)) | (Not avkComputeId(d,bound)) | (avkComputeSlot(a)\typeKind <> #AVK_CTYPE_UINT) | (avkComputeSlot(b)\valueKind) | (avkComputeSlot(b)\typeKind) | (avkComputeSlot(c)\valueKind <> #AVK_CVALUE_INT) | (avkComputeSlot(d)\valueKind <> #AVK_CVALUE_INT) | (avkComputeSlot(c)\valueType <> a) | (avkComputeSlot(d)\valueType <> a)
          ProcedureReturn #ANVIL_COMPUTE_ERR
        EndIf
        If op=#SpvOpIAdd
          scale=avkComputeSlot(c)\scale+avkComputeSlot(d)\scale
          off=avkComputeSlot(c)\offset+avkComputeSlot(d)\offset
        Else
          If (avkComputeSlot(c)\scale <> 0) & (avkComputeSlot(d)\scale <> 0)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
          scale=avkComputeSlot(c)\scale*avkComputeSlot(d)\offset+avkComputeSlot(d)\scale*avkComputeSlot(c)\offset
          off=avkComputeSlot(c)\offset*avkComputeSlot(d)\offset
        EndIf
        If (scale > 4096) | (off > 4096)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
        avkComputeSlot(b)\valueKind=#AVK_CVALUE_INT
        avkComputeSlot(b)\valueType=a
        avkComputeSlot(b)\scale=scale
        avkComputeSlot(b)\offset=off
      Case #SpvOpStore
        If (wc <> 3) | (Not labelSeen) | (returnSeen) | (Not avkComputeId(a,bound)) | (Not avkComputeId(b,bound)) | (storeCount >= #ANVIL_COMPUTE_MAX_STORES) | (avkComputeSlot(a)\valueKind <> #AVK_CVALUE_POINTER) | (avkComputeSlot(a)\base <> outputVar) | (avkComputeSlot(a)\scale <> 144) | (avkComputeSlot(a)\offset <> storeCount*4) | (avkComputeSlot(b)\valueKind <> #AVK_CVALUE_FLOAT) | (Not avkComputeFloatType(avkComputeSlot(b)\valueType)) | (avkComputeSlot(avkComputeSlot(a)\valueType)\elem <> avkComputeSlot(b)\valueType)
          ProcedureReturn #ANVIL_COMPUTE_ERR
        EndIf
        *out\stores[storeCount]\outputWord=storeCount
        *out\stores[storeCount]\sourceKind=avkComputeSlot(b)\sourceKind
        If avkComputeSlot(b)\sourceKind=#ANVIL_COMPUTE_SOURCE_INPUT
          If (avkComputeSlot(b)\scale <> 48) | (avkComputeSlot(b)\offset > 44) | ((avkComputeSlot(b)\offset & 3) <> 0)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
          *out\stores[storeCount]\inputByte=avkComputeSlot(b)\offset
        ElseIf avkComputeSlot(b)\sourceKind=0
          *out\stores[storeCount]\sourceKind=#ANVIL_COMPUTE_SOURCE_CONSTANT
          *out\stores[storeCount]\constantBits=avkComputeSlot(b)\bits
        Else
          ProcedureReturn #ANVIL_COMPUTE_ERR
        EndIf
        storeCount=storeCount+1
      Case #SpvOpReturn
        If (wc <> 1) | (Not labelSeen) | (returnSeen)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
        returnSeen=1
      Case #SpvOpFunctionEnd
        If (wc <> 1) | (Not returnSeen)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
        functionEndSeen=1
      Default
        ProcedureReturn #ANVIL_COMPUTE_ERR
    EndSelect
    pos=pos+wc
  Wend
  If (Not capabilitySeen) | (Not modelSeen) | (Not entrySeen) | (Not localSeen) | (Not functionEndSeen) | (storeCount <> #ANVIL_COMPUTE_MAX_STORES) | (builtinVar=0)
    ProcedureReturn #ANVIL_COMPUTE_ERR
  EndIf
  ; Resolve descriptor variables independently of physical IDs.
  For id=1 To bound-1
    If avkComputeSlot(id)\decorated
      If (avkComputeSlot(id)\typeKind=0) & (avkComputeSlot(id)\valueKind=0)
        ProcedureReturn #ANVIL_COMPUTE_ERR
      EndIf
    EndIf
    If avkComputeSlot(id)\memberDecorationMask
      If avkComputeSlot(id)\typeKind <> #AVK_CTYPE_STRUCT
        ProcedureReturn #ANVIL_COMPUTE_ERR
      EndIf
      For k=0 To 3
        If (avkComputeSlot(id)\memberDecorationMask & (1 << k)) <> 0
          If k >= avkComputeSlot(id)\count
            ProcedureReturn #ANVIL_COMPUTE_ERR
          EndIf
        EndIf
      Next
    EndIf
    If avkComputeSlot(id)\named
      If (avkComputeSlot(id)\typeKind=0) & (avkComputeSlot(id)\valueKind=0)
        ProcedureReturn #ANVIL_COMPUTE_ERR
      EndIf
    EndIf
    If avkComputeSlot(id)\memberNameMask
      If avkComputeSlot(id)\typeKind <> #AVK_CTYPE_STRUCT
        ProcedureReturn #ANVIL_COMPUTE_ERR
      EndIf
      For k=0 To 3
        If (avkComputeSlot(id)\memberNameMask & (1 << k)) <> 0
          If k >= avkComputeSlot(id)\count
            ProcedureReturn #ANVIL_COMPUTE_ERR
          EndIf
        EndIf
      Next
    EndIf
    If (avkComputeSlot(id)\builtin >= 0) & (id <> builtinVar)
      If (avkComputeSlot(id)\builtin <> #SpvBuiltInWorkgroupSize) | (avkComputeSlot(id)\valueKind <> #AVK_CVALUE_COMPOSITE)
        ProcedureReturn #ANVIL_COMPUTE_ERR
      EndIf
    EndIf
    If (avkComputeSlot(id)\valueKind=#AVK_CVALUE_POINTER) & (avkComputeSlot(id)\base=id)
      ty=avkComputeSlot(avkComputeSlot(id)\valueType)\elem
      If id=builtinVar
        If (avkComputeSlot(id)\builtin <> #SpvBuiltInGlobalInvocationId) | (avkComputeSlot(avkComputeSlot(id)\valueType)\storage <> #SpvStorageClassInput) | (avkComputeSlot(ty)\typeKind <> #AVK_CTYPE_VECTOR) | (avkComputeSlot(ty)\count <> 3) | (avkComputeSlot(avkComputeSlot(ty)\elem)\typeKind <> #AVK_CTYPE_UINT)
          ProcedureReturn #ANVIL_COMPUTE_ERR
        EndIf
      ElseIf (avkComputeSlot(id)\binding=0) & (avkComputeSlot(id)\descriptorSet=0)
        If (inputVar <> 0) & (inputVar <> id)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
        inputVar=id
        inputType=ty
      ElseIf (avkComputeSlot(id)\binding=1) & (avkComputeSlot(id)\descriptorSet=0)
        If (outputVar <> 0) & (outputVar <> id)
         ProcedureReturn #ANVIL_COMPUTE_ERR
         EndIf
        outputVar=id
        outputType=ty
      Else
        ProcedureReturn #ANVIL_COMPUTE_ERR
      EndIf
    EndIf
  Next
  If (inputVar=0) | (outputVar=0) | (avkComputeSlot(inputVar)\nonWritable=0) | (avkComputeSlot(outputVar)\nonReadable=0)
    ProcedureReturn #ANVIL_COMPUTE_ERR
  EndIf
  If (avkComputeSlot(inputType)\typeKind <> #AVK_CTYPE_STRUCT) | (avkComputeSlot(inputType)\count <> 1) | (avkComputeSlot(inputType)\bufferBlock=0) | (avkCMOffset((inputType)*4+0) <> 0)
    ProcedureReturn #ANVIL_COMPUTE_ERR
  EndIf
  If (avkComputeSlot(outputType)\typeKind <> #AVK_CTYPE_STRUCT) | (avkComputeSlot(outputType)\count <> 1) | (avkComputeSlot(outputType)\bufferBlock=0) | (avkCMOffset((outputType)*4+0) <> 0)
    ProcedureReturn #ANVIL_COMPUTE_ERR
  EndIf
  inputArray=avkCMType((inputType)*4+0)
        outputArray=avkCMType((outputType)*4+0)
  If (avkComputeSlot(inputArray)\typeKind <> #AVK_CTYPE_RUNTIME) | (avkComputeSlot(inputArray)\stride <> 48) | (avkComputeSlot(outputArray)\typeKind <> #AVK_CTYPE_RUNTIME) | (avkComputeSlot(outputArray)\stride <> 4)
    ProcedureReturn #ANVIL_COMPUTE_ERR
  EndIf
  inputRecord=avkComputeSlot(inputArray)\elem
  If (avkComputeSlot(inputRecord)\typeKind <> #AVK_CTYPE_STRUCT) | (avkComputeSlot(inputRecord)\count <> 3) | (avkCMOffset((inputRecord)*4+0) <> 0) | (avkCMOffset((inputRecord)*4+1) <> 16) | (avkCMOffset((inputRecord)*4+2) <> 32) | (Not avkComputeFloatType(avkComputeSlot(outputArray)\elem))
    ProcedureReturn #ANVIL_COMPUTE_ERR
  EndIf
  For k=0 To 2
    ty=avkCMType((inputRecord)*4+k)
    If (avkComputeSlot(ty)\typeKind <> #AVK_CTYPE_VECTOR) | (avkComputeSlot(ty)\count <> 4) | (Not avkComputeFloatType(avkComputeSlot(ty)\elem))
      ProcedureReturn #ANVIL_COMPUTE_ERR
    EndIf
  Next
  *out\valid=1
        *out\inputStride=48
        *out\outputStride=4
  *out\inputIndexScale=1
        *out\outputIndexScale=36
  *out\inputBinding=0
        *out\outputBinding=1
        *out\storeCount=storeCount
  ProcedureReturn 0
EndProcedure

Structure AvkSpirvIrStorage Align #PB_Structure_AlignC
  module.AvkIrModule
  types.AvkIrType[#ANVIL_IR_MAX_TYPES + 1]
  constants.AvkIrConstant[#ANVIL_IR_MAX_CONSTANTS + 1]
  variables.AvkIrVariable[#ANVIL_IR_MAX_VARIABLES + 1]
  interfaces.i[#ANVIL_IR_MAX_VARIABLES + 1]
  decorations.AvkIrDecoration[#ANVIL_IR_MAX_DECORATIONS + 1]
  blocks.AvkIrBlock[#ANVIL_IR_MAX_BLOCKS + 1]
  nodes.AvkIrNode[#ANVIL_IR_MAX_NODES + 1]
  valid.i
EndStructure

Global avkSpvIrScratch.AvkSpirvIrStorage
Global avkSpvIrLastCode.i = 0
Global avkSpvIrLastId.i = 0
Global avkSpvIrLastOpcode.i = 0
Global avkSpvIrLastIndex.i = -1

Procedure.i AnvilVkSpirvIrLastCode()
  ProcedureReturn avkSpvIrLastCode
EndProcedure
Procedure.i AnvilVkSpirvIrLastId()
  ProcedureReturn avkSpvIrLastId
EndProcedure
Procedure.i AnvilVkSpirvIrLastOpcode()
  ProcedureReturn avkSpvIrLastOpcode
EndProcedure
Procedure.i AnvilVkSpirvIrLastIndex()
  ProcedureReturn avkSpvIrLastIndex
EndProcedure

Procedure.i avkSpvIrFail(code.i, id.i, opcode.i, index.i)
  avkSpvIrLastCode=code
  avkSpvIrLastId=id
  avkSpvIrLastOpcode=opcode
  avkSpvIrLastIndex=index
  ProcedureReturn code
EndProcedure

Procedure avkSpvIrClear(*s.AvkSpirvIrStorage)
  Protected i.i=0
  While i<SizeOf(AvkSpirvIrStorage):PokeA(*s+i,0):i=i+1:Wend
  *s\module\types=*s+OffsetOf(AvkSpirvIrStorage\types)
  *s\module\constants=*s+OffsetOf(AvkSpirvIrStorage\constants)
  *s\module\variables=*s+OffsetOf(AvkSpirvIrStorage\variables)
  *s\module\interfaces=*s+OffsetOf(AvkSpirvIrStorage\interfaces)
  *s\module\decorations=*s+OffsetOf(AvkSpirvIrStorage\decorations)
  *s\module\blocks=*s+OffsetOf(AvkSpirvIrStorage\blocks)
  *s\module\nodes=*s+OffsetOf(AvkSpirvIrStorage\nodes)
EndProcedure

; Copy the exact EntryPoint interface operands from retained source words.
; AvkSpvRecord's nine inline IDs are deliberately only a convenience
; projection and must never narrow this authoritative list.
Procedure.i avkSpvIrEntryInterface(*r.AvkSpvRecord, *m.AvkIrModule, index.i)
  Protected k.i = 3
  Protected word.i
  Protected count.i
  Protected id.i
  Protected rc.i
  Protected terminated.i = 0
  If *r\sourceOpcode <> #SpvOpEntryPoint Or *r\sourceWordCount < 4
    ProcedureReturn avkSpvIrFail(#ANVIL_SPV_IR_ERR_RECORD, *r\sourceId, *r\sourceOpcode, index)
  EndIf
  rc = AnvilVkSpirvRecordWordRead(*r\wordOffset, @word)
  If rc <> #ANVIL_VK_OK Or (word & $FFFF) <> #SpvOpEntryPoint Or (word >> 16) <> *r\sourceWordCount
    ProcedureReturn avkSpvIrFail(#ANVIL_SPV_IR_ERR_RECORD, *r\sourceId, *r\sourceOpcode, index)
  EndIf
  While k < *r\sourceWordCount
    rc = AnvilVkSpirvRecordWordRead(*r\wordOffset + k, @word)
    If rc <> #ANVIL_VK_OK
      ProcedureReturn avkSpvIrFail(#ANVIL_SPV_IR_ERR_RECORD, *r\sourceId, *r\sourceOpcode, index)
    EndIf
    k = k + 1
    If (word & $FF) = 0 Or (word & $FF00) = 0 Or (word & $FF0000) = 0 Or (word & $FF000000) = 0
      terminated = 1
      Break
    EndIf
  Wend
  If terminated = 0
    ProcedureReturn avkSpvIrFail(#ANVIL_SPV_IR_ERR_RECORD, *r\sourceId, *r\sourceOpcode, index)
  EndIf
  count = *r\sourceWordCount - k
  If count < 0 Or count > #ANVIL_IR_MAX_VARIABLES
    ProcedureReturn avkSpvIrFail(#ANVIL_SPV_IR_ERR_RANGE, *r\sourceId, *r\sourceOpcode, index)
  EndIf
  *m\interfaceCount = count
  count = 0
  While k < *r\sourceWordCount
    rc = AnvilVkSpirvRecordWordRead(*r\wordOffset + k, @id)
    If rc <> #ANVIL_VK_OK
      ProcedureReturn avkSpvIrFail(#ANVIL_SPV_IR_ERR_RECORD, *r\sourceId, *r\sourceOpcode, index)
    EndIf
    PokeI(*m\interfaces + (count * SizeOf(.i)), id)
    count = count + 1
    k = k + 1
  Wend
  ProcedureReturn #ANVIL_IR_OK
EndProcedure

Procedure.i avkSpvIrDecorationKind(spvKind.i)
  If spvKind = #SpvDecorationRelaxedPrecision : ProcedureReturn #ANVIL_IR_DEC_RELAXED_PRECISION : EndIf
  If spvKind = #SpvDecorationBlock : ProcedureReturn #ANVIL_IR_DEC_BLOCK : EndIf
  If spvKind = #SpvDecorationColMajor : ProcedureReturn #ANVIL_IR_DEC_COL_MAJOR : EndIf
  If spvKind = #SpvDecorationArrayStride : ProcedureReturn #ANVIL_IR_DEC_ARRAY_STRIDE : EndIf
  If spvKind = #SpvDecorationMatrixStride : ProcedureReturn #ANVIL_IR_DEC_MATRIX_STRIDE : EndIf
  If spvKind = #SpvDecorationBuiltIn : ProcedureReturn #ANVIL_IR_DEC_BUILTIN : EndIf
  If spvKind = #SpvDecorationLocation : ProcedureReturn #ANVIL_IR_DEC_LOCATION : EndIf
  If spvKind = #SpvDecorationDescriptorSet : ProcedureReturn #ANVIL_IR_DEC_DESCRIPTOR_SET : EndIf
  If spvKind = #SpvDecorationBinding : ProcedureReturn #ANVIL_IR_DEC_BINDING : EndIf
  If spvKind = #SpvDecorationOffset : ProcedureReturn #ANVIL_IR_DEC_OFFSET : EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i avkSpvIrNodeKind(op.i)
  If op = #SpvOpLoad : ProcedureReturn #ANVIL_IR_OP_LOAD : EndIf
  If op = #SpvOpAccessChain : ProcedureReturn #ANVIL_IR_OP_ACCESS_CHAIN : EndIf
  If op = #SpvOpCompositeExtract : ProcedureReturn #ANVIL_IR_OP_COMPOSITE_EXTRACT : EndIf
  If op = #SpvOpCompositeConstruct : ProcedureReturn #ANVIL_IR_OP_COMPOSITE_CONSTRUCT : EndIf
  If op = #SpvOpImageSampleImplicitLod : ProcedureReturn #ANVIL_IR_OP_IMAGE_SAMPLE_IMPLICIT_LOD : EndIf
  If op = #SpvOpStore : ProcedureReturn #ANVIL_IR_OP_STORE : EndIf
  If op = #SpvOpReturn : ProcedureReturn #ANVIL_IR_OP_RETURN : EndIf
  If op = #SpvOpFAdd : ProcedureReturn #ANVIL_IR_OP_FADD : EndIf
  If op = #SpvOpFMul : ProcedureReturn #ANVIL_IR_OP_FMUL : EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i avkSpvIrType(*r.AvkSpvRecord, index.i)
  Protected *m.AvkIrModule=@avkSpvIrScratch\module
  Protected *t.AvkIrType
  Protected n.i=*m\typeCount
  If n >= #ANVIL_IR_MAX_TYPES
    ProcedureReturn avkSpvIrFail(#ANVIL_SPV_IR_ERR_RANGE, *r\sourceId, *r\sourceOpcode, index)
  EndIf
  *t=@avkSpvIrScratch\types[n]
  *t\sourceId=*r\sourceId
  *t\sourceOpcode=*r\sourceOpcode
  If *r\sourceOpcode = #SpvOpTypeVoid
    *t\kind = #ANVIL_IR_TYPE_VOID
  EndIf
  If *r\sourceOpcode = #SpvOpTypeInt
    *t\kind = #ANVIL_IR_TYPE_INT
    *t\width = *r\literal0
    *t\signedness = *r\literal1
  EndIf
  If *r\sourceOpcode = #SpvOpTypeFloat
    *t\kind = #ANVIL_IR_TYPE_FLOAT
    *t\width = *r\literal0
  EndIf
  If *r\sourceOpcode = #SpvOpTypeVector
    *t\kind = #ANVIL_IR_TYPE_VECTOR
    *t\componentType = *r\id0
    *t\componentCount = *r\literal0
  EndIf
  If *r\sourceOpcode=#SpvOpTypeStruct
    *t\kind = #ANVIL_IR_TYPE_STRUCT
    *t\memberCount = *r\idCount
    *t\member0 = *r\id0
    *t\member1 = *r\id1
    *t\member2 = *r\id2
    *t\member3 = *r\id3
  EndIf
  If *r\sourceOpcode = #SpvOpTypePointer
    *t\kind = #ANVIL_IR_TYPE_POINTER
    *t\storageClass = *r\literal0
    *t\pointeeType = *r\id0
  EndIf
  If *r\sourceOpcode = #SpvOpTypeFunction
    *t\kind = #ANVIL_IR_TYPE_FUNCTION
    *t\returnType = *r\id0
  EndIf
  If *r\sourceOpcode=#SpvOpTypeImage
    *t\kind = #ANVIL_IR_TYPE_IMAGE
    *t\componentType = *r\id0
    *t\imageDim = *r\literal0
    *t\imageDepth = *r\literal1
    *t\imageArrayed = *r\literal2
    *t\imageMultisampled = *r\literal3
    *t\imageSampled = *r\literal4
    *t\imageFormat = *r\literal5
  EndIf
  If *r\sourceOpcode = #SpvOpTypeSampledImage
    *t\kind = #ANVIL_IR_TYPE_SAMPLED_IMAGE
    *t\componentType = *r\id0
  EndIf
  If *t\kind = 0
    ProcedureReturn avkSpvIrFail(#ANVIL_SPV_IR_ERR_RECORD, *r\sourceId, *r\sourceOpcode, index)
  EndIf
  *m\typeCount=n+1
  ProcedureReturn 0
EndProcedure

Procedure.i avkSpvIrConstant(*r.AvkSpvRecord,index.i)
  Protected *m.AvkIrModule=@avkSpvIrScratch\module
  Protected *c.AvkIrConstant
  Protected n.i=*m\constantCount
  If n >= #ANVIL_IR_MAX_CONSTANTS
    ProcedureReturn avkSpvIrFail(#ANVIL_SPV_IR_ERR_RANGE, *r\sourceId, *r\sourceOpcode, index)
  EndIf
  *c=@avkSpvIrScratch\constants[n]
  *c\sourceId = *r\sourceId
  *c\sourceOpcode = *r\sourceOpcode
  *c\typeId = *r\resultType
  If *r\sourceOpcode = #SpvOpConstant
    *c\wordCount = 1
    *c\word0 = *r\literal0
  EndIf
  If *r\sourceOpcode=#SpvOpConstantComposite
    *c\componentCount = *r\idCount
    *c\component0 = *r\id0
    *c\component1 = *r\id1
    *c\component2 = *r\id2
    *c\component3 = *r\id3
  EndIf
  *m\constantCount=n+1
  ProcedureReturn 0
EndProcedure

Procedure.i avkSpvIrVariable(*r.AvkSpvRecord,index.i)
  Protected *m.AvkIrModule=@avkSpvIrScratch\module
  Protected *v.AvkIrVariable
  Protected n.i=*m\variableCount
  If n >= #ANVIL_IR_MAX_VARIABLES
    ProcedureReturn avkSpvIrFail(#ANVIL_SPV_IR_ERR_RANGE, *r\sourceId, *r\sourceOpcode, index)
  EndIf
  *v=@avkSpvIrScratch\variables[n]
  *v\sourceId = *r\sourceId
  *v\sourceOpcode = *r\sourceOpcode
  *v\pointerType = *r\resultType
  *v\storageClass = *r\literal0
  *m\variableCount=n+1
  ProcedureReturn 0
EndProcedure

Procedure.i avkSpvIrDecoration(*r.AvkSpvRecord,index.i)
  Protected *m.AvkIrModule=@avkSpvIrScratch\module
  Protected *d.AvkIrDecoration
  Protected n.i=*m\decorationCount
  Protected kind.i
  Protected value.i
  Protected member.i=-1
  If n >= #ANVIL_IR_MAX_DECORATIONS
    ProcedureReturn avkSpvIrFail(#ANVIL_SPV_IR_ERR_RANGE, *r\sourceId, *r\sourceOpcode, index)
  EndIf
  If *r\sourceOpcode = #SpvOpMemberDecorate
    member = *r\literal0
    kind = avkSpvIrDecorationKind(*r\literal1)
    value = *r\literal2
  Else
    kind = avkSpvIrDecorationKind(*r\literal0)
    value = *r\literal1
  EndIf
  If kind = 0
    ProcedureReturn avkSpvIrFail(#ANVIL_SPV_IR_ERR_RECORD, *r\sourceId, *r\sourceOpcode, index)
  EndIf
  *d=@avkSpvIrScratch\decorations[n]
  *d\sourceId = *r\sourceId
  *d\sourceOpcode = *r\sourceOpcode
  *d\member = member
  *d\kind = kind
  *d\value = value
  *m\decorationCount=n+1
  ProcedureReturn 0
EndProcedure

Procedure.i avkSpvIrNode(*r.AvkSpvRecord,index.i)
  Protected *m.AvkIrModule=@avkSpvIrScratch\module
  Protected *n.AvkIrNode
  Protected at.i=*m\nodeCount
  Protected kind.i=avkSpvIrNodeKind(*r\sourceOpcode)
  If at >= #ANVIL_IR_MAX_NODES
    ProcedureReturn avkSpvIrFail(#ANVIL_SPV_IR_ERR_RANGE, *r\sourceId, *r\sourceOpcode, index)
  EndIf
  If kind = 0 Or *m\entryBlockId = 0
    ProcedureReturn avkSpvIrFail(#ANVIL_SPV_IR_ERR_RECORD, *r\sourceId, *r\sourceOpcode, index)
  EndIf
  *n=@avkSpvIrScratch\nodes[at]
  *n\sourceId = *r\sourceId
  *n\sourceOpcode = *r\sourceOpcode
  *n\kind = kind
  *n\resultType = *r\resultType
  *n\blockId = *m\entryBlockId
  *n\operandCount = *r\idCount
  *n\operand0 = *r\id0
  *n\operand1 = *r\id1
  *n\operand2 = *r\id2
  *n\operand3 = *r\id3
  *n\literalCount = *r\literalCount
  *n\literal0 = *r\literal0
  *m\nodeCount=at+1
  ProcedureReturn 0
EndProcedure

Procedure.i AnvilVkSpirvIrAdapt(*out.AvkSpirvIrStorage)
  Protected r.AvkSpvRecord
  Protected *m.AvkIrModule=@avkSpvIrScratch\module
  Protected *b.AvkIrBlock
  Protected i.i
  Protected rc.i
  Protected bytes.i
  avkSpvIrLastCode = 0
  avkSpvIrLastId = 0
  avkSpvIrLastOpcode = 0
  avkSpvIrLastIndex = -1
  If *out = 0
    ProcedureReturn avkSpvIrFail(#ANVIL_IR_ERR_ARGS, 0, 0, -1)
  EndIf
  ; A caller can reuse one destination across walks. Invalidate it before
  ; consulting the retained stream; no failed adaptation leaves yesterday's
  ; verified module looking current.
  avkSpvIrClear(*out)
  If AnvilVkSpirvRecordsValid() = 0
    ProcedureReturn avkSpvIrFail(#ANVIL_IR_ERR_ARGS, 0, 0, -1)
  EndIf
  avkSpvIrClear(@avkSpvIrScratch)
  *m\sourceVersion=AnvilVkSpirvVersion()
  *m\idBound=AnvilVkSpirvBound()
  i=0
  While i<AnvilVkSpirvRecordCount()
    rc=AnvilVkSpirvRecordRead(i,@r)
    If rc <> 0
      ProcedureReturn avkSpvIrFail(#ANVIL_SPV_IR_ERR_RECORD, 0, 0, i)
    EndIf
    If r\section=#ANVIL_SPV_REC_ENTRY
      If r\literal0 = #SpvExecutionModelVertex
        *m\stage = #ANVIL_IR_STAGE_VERTEX
      ElseIf r\literal0 = #SpvExecutionModelFragment
        *m\stage = #ANVIL_IR_STAGE_FRAGMENT
      Else
        ProcedureReturn avkSpvIrFail(#ANVIL_SPV_IR_ERR_RECORD, r\sourceId, r\sourceOpcode, i)
      EndIf
      *m\entryFunctionId=r\sourceId
      rc=avkSpvIrEntryInterface(@r,*m,i)
    ElseIf r\section = #ANVIL_SPV_REC_TYPE
      rc = avkSpvIrType(@r, i)
    ElseIf r\section = #ANVIL_SPV_REC_CONSTANT
      rc = avkSpvIrConstant(@r, i)
    ElseIf r\section = #ANVIL_SPV_REC_VARIABLE
      rc = avkSpvIrVariable(@r, i)
    ElseIf r\section = #ANVIL_SPV_REC_DECORATION
      rc = avkSpvIrDecoration(@r, i)
    ElseIf r\section=#ANVIL_SPV_REC_FUNCTION
      If r\literal0 <> 0
        ProcedureReturn avkSpvIrFail(#ANVIL_SPV_IR_ERR_RECORD, r\sourceId, r\sourceOpcode, i)
      EndIf
      *m\entryFunctionId = r\sourceId
      *m\entryFunctionOpcode = r\sourceOpcode
      *m\returnTypeId = r\resultType
      *m\functionTypeId = r\id0
    ElseIf r\section=#ANVIL_SPV_REC_BLOCK
      If *m\blockCount >= #ANVIL_IR_MAX_BLOCKS
        ProcedureReturn avkSpvIrFail(#ANVIL_SPV_IR_ERR_RANGE, r\sourceId, r\sourceOpcode, i)
      EndIf
      *b = @avkSpvIrScratch\blocks[*m\blockCount]
      *b\sourceId = r\sourceId
      *b\sourceOpcode = r\sourceOpcode
      *b\firstNode = *m\nodeCount
      *m\entryBlockId = r\sourceId
      *m\blockCount = *m\blockCount + 1
    ElseIf r\section = #ANVIL_SPV_REC_NODE
      rc = avkSpvIrNode(@r, i)
    ElseIf r\section=#ANVIL_SPV_REC_END
      If *m\blockCount <> 1
        ProcedureReturn avkSpvIrFail(#ANVIL_SPV_IR_ERR_RECORD, r\sourceId, r\sourceOpcode, i)
      EndIf
      *b = @avkSpvIrScratch\blocks[0]
      *b\nodeCount = *m\nodeCount - *b\firstNode
    ElseIf r\section=#ANVIL_SPV_REC_ENVIRONMENT
      If r\sourceOpcode = #SpvOpExtInstImport
        ProcedureReturn avkSpvIrFail(#ANVIL_IR_ERR_UNSUPPORTED, r\sourceId, r\sourceOpcode, i)
      EndIf
    EndIf
    If rc <> 0
      ProcedureReturn rc
    EndIf
    i=i+1
  Wend
  rc=AnvilVkIrVerify(*m)
  If rc <> #ANVIL_IR_OK
    ProcedureReturn avkSpvIrFail(rc, AnvilVkIrLastId(), AnvilVkIrLastOpcode(), AnvilVkIrLastIndex())
  EndIf
  bytes = SizeOf(AvkSpirvIrStorage)
  i = 0
  While i < bytes
    PokeA(*out + i, PeekA(@avkSpvIrScratch + i))
    i = i + 1
  Wend
  *out\module\types = *out+OffsetOf(AvkSpirvIrStorage\types)
  *out\module\constants = *out+OffsetOf(AvkSpirvIrStorage\constants)
  *out\module\variables = *out+OffsetOf(AvkSpirvIrStorage\variables)
  *out\module\interfaces = *out+OffsetOf(AvkSpirvIrStorage\interfaces)
  *out\module\decorations = *out+OffsetOf(AvkSpirvIrStorage\decorations)
  *out\module\blocks = *out+OffsetOf(AvkSpirvIrStorage\blocks)
  *out\module\nodes = *out+OffsetOf(AvkSpirvIrStorage\nodes)
  ; Publish last, after both verification and pointer rebinding. The output
  ; contains no pointer into parser storage, adapter scratch or caller code.
  *out\valid = 1
  ProcedureReturn #ANVIL_IR_OK
EndProcedure

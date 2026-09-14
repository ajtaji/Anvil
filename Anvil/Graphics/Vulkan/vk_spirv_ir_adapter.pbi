; SPIR-V retained semantic records -> passive typed IR.
; Include vk_spirv.pbi, then vk_ir.pbi, then this file.
; SPDX-License-Identifier: MIT

#ANVIL_SPV_IR_ERR_RECORD = -23301
#ANVIL_SPV_IR_ERR_RANGE  = -23302

Structure AvkSpirvIrStorage Align #PB_Structure_AlignC
  module.AvkIrModule
  types.AvkIrType[#ANVIL_IR_MAX_TYPES + 1]
  constants.AvkIrConstant[#ANVIL_IR_MAX_CONSTANTS + 1]
  variables.AvkIrVariable[#ANVIL_IR_MAX_VARIABLES + 1]
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
  *s\module\decorations=*s+OffsetOf(AvkSpirvIrStorage\decorations)
  *s\module\blocks=*s+OffsetOf(AvkSpirvIrStorage\blocks)
  *s\module\nodes=*s+OffsetOf(AvkSpirvIrStorage\nodes)
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
  *out\module\decorations = *out+OffsetOf(AvkSpirvIrStorage\decorations)
  *out\module\blocks = *out+OffsetOf(AvkSpirvIrStorage\blocks)
  *out\module\nodes = *out+OffsetOf(AvkSpirvIrStorage\nodes)
  ; Publish last, after both verification and pointer rebinding. The output
  ; contains no pointer into parser storage, adapter scratch or caller code.
  *out\valid = 1
  ProcedureReturn #ANVIL_IR_OK
EndProcedure

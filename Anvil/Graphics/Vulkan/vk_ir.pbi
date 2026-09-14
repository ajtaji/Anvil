; ======================================================================
;  Target-neutral typed SSA/control-flow IR -- passive first tranche
; ======================================================================
; SPDX-License-Identifier: MIT
;
; This file defines a passive schema and a total verifier. It does not parse
; SPIR-V, emit V3D code, allocate storage or change the current Vulkan path.
; A future parser may populate these records only after it proves that every
; accepted SPIR-V instruction has one represented semantic operation.
;
; The original represented subset mirrors what vk_spirv.pbi accepts: one
; Vertex or Fragment entry function, void/no parameters, one basic block, and
; Load, one-index AccessChain, CompositeExtract, CompositeConstruct,
; ImageSampleImplicitLod, Store and Return. This passive tranche additionally
; defines exact float32 FAdd/FMul nodes for later parser/lowerer integration;
; the current parser still refuses those opcodes, so verification here alone
; makes no public shader-support claim. Phi and multi-block control flow remain
; deliberately unrepresentable.
;
; Khronos SPIR-V specification/registry semantics consulted: physical IDs and
; SSA (2.3), types (3.32), storage classes (3.7), decorations (3.20), and the
; instruction definitions for the represented operations above. Numeric source
; opcodes are retained only for deterministic diagnostics; the represented
; operations use their own target-neutral IR enum.

#ANVIL_IR_OK              = 0
#ANVIL_IR_ERR_ARGS        = -23201
#ANVIL_IR_ERR_BOUNDS      = -23202
#ANVIL_IR_ERR_DUPLICATE   = -23203
#ANVIL_IR_ERR_UNDEFINED   = -23204
#ANVIL_IR_ERR_TYPE        = -23205
#ANVIL_IR_ERR_STORAGE     = -23206
#ANVIL_IR_ERR_DECORATION  = -23207
#ANVIL_IR_ERR_CFG         = -23208
#ANVIL_IR_ERR_TERMINATOR  = -23209
#ANVIL_IR_ERR_UNSUPPORTED = -23210
#ANVIL_IR_ERR_DOMINANCE   = -23211

; Current front-end storage bounds, not SPIR-V or IR architectural limits.
#ANVIL_IR_MAX_ID          = 192
#ANVIL_IR_MAX_TYPES       = 64
#ANVIL_IR_MAX_CONSTANTS   = 64
#ANVIL_IR_MAX_VARIABLES   = 32
#ANVIL_IR_MAX_DECORATIONS = 64
#ANVIL_IR_MAX_BLOCKS      = 8
#ANVIL_IR_MAX_NODES       = 128
#ANVIL_IR_MAX_MEMBERS     = 4

#ANVIL_IR_STAGE_VERTEX   = 1
#ANVIL_IR_STAGE_FRAGMENT = 2

#ANVIL_IR_TYPE_VOID          = 1
#ANVIL_IR_TYPE_INT           = 2
#ANVIL_IR_TYPE_FLOAT         = 3
#ANVIL_IR_TYPE_VECTOR        = 4
#ANVIL_IR_TYPE_STRUCT        = 5
#ANVIL_IR_TYPE_POINTER       = 6
#ANVIL_IR_TYPE_FUNCTION      = 7
#ANVIL_IR_TYPE_IMAGE         = 8
#ANVIL_IR_TYPE_SAMPLED_IMAGE = 9

#ANVIL_IR_STORAGE_UNIFORM_CONSTANT = 0
#ANVIL_IR_STORAGE_INPUT            = 1
#ANVIL_IR_STORAGE_UNIFORM          = 2
#ANVIL_IR_STORAGE_OUTPUT           = 3
#ANVIL_IR_STORAGE_PUSH_CONSTANT    = 9

#ANVIL_IR_DEC_RELAXED_PRECISION = 1
#ANVIL_IR_DEC_BLOCK             = 2
#ANVIL_IR_DEC_COL_MAJOR         = 3
#ANVIL_IR_DEC_ARRAY_STRIDE      = 4
#ANVIL_IR_DEC_MATRIX_STRIDE     = 5
#ANVIL_IR_DEC_BUILTIN          = 6
#ANVIL_IR_DEC_LOCATION         = 7
#ANVIL_IR_DEC_DESCRIPTOR_SET   = 8
#ANVIL_IR_DEC_BINDING          = 9
#ANVIL_IR_DEC_OFFSET           = 10
#ANVIL_IR_DEC_NO_CONTRACTION   = 11
#ANVIL_IR_DEC_FP_FAST_MATH_MODE = 12

#ANVIL_IR_BUILTIN_POSITION = 0

#ANVIL_IR_OP_LOAD             = 1
#ANVIL_IR_OP_ACCESS_CHAIN     = 2
#ANVIL_IR_OP_COMPOSITE_EXTRACT = 3
#ANVIL_IR_OP_COMPOSITE_CONSTRUCT = 4
#ANVIL_IR_OP_IMAGE_SAMPLE_IMPLICIT_LOD = 5
#ANVIL_IR_OP_STORE            = 6
#ANVIL_IR_OP_RETURN           = 7
#ANVIL_IR_OP_FADD              = 8
#ANVIL_IR_OP_FMUL              = 9

; Source opcode values from the Khronos grammar, retained in every record.
#ANVIL_IR_SPV_TYPE_VOID = 19
#ANVIL_IR_SPV_TYPE_INT = 21
#ANVIL_IR_SPV_TYPE_FLOAT = 22
#ANVIL_IR_SPV_TYPE_VECTOR = 23
#ANVIL_IR_SPV_TYPE_IMAGE = 25
#ANVIL_IR_SPV_TYPE_SAMPLED_IMAGE = 27
#ANVIL_IR_SPV_TYPE_STRUCT = 30
#ANVIL_IR_SPV_TYPE_POINTER = 32
#ANVIL_IR_SPV_TYPE_FUNCTION = 33
#ANVIL_IR_SPV_CONSTANT = 43
#ANVIL_IR_SPV_CONSTANT_COMPOSITE = 44
#ANVIL_IR_SPV_FUNCTION = 54
#ANVIL_IR_SPV_VARIABLE = 59
#ANVIL_IR_SPV_LOAD = 61
#ANVIL_IR_SPV_STORE = 62
#ANVIL_IR_SPV_ACCESS_CHAIN = 65
#ANVIL_IR_SPV_DECORATE = 71
#ANVIL_IR_SPV_MEMBER_DECORATE = 72
#ANVIL_IR_SPV_COMPOSITE_CONSTRUCT = 80
#ANVIL_IR_SPV_COMPOSITE_EXTRACT = 81
#ANVIL_IR_SPV_IMAGE_SAMPLE_IMPLICIT_LOD = 87
#ANVIL_IR_SPV_FADD = 129
#ANVIL_IR_SPV_FMUL = 133
#ANVIL_IR_SPV_LABEL = 248
#ANVIL_IR_SPV_RETURN = 253

Structure AvkIrType Align #PB_Structure_AlignC
  sourceId.i
  sourceOpcode.i
  kind.i
  width.i
  signedness.i
  componentType.i
  componentCount.i
  storageClass.i
  pointeeType.i
  returnType.i
  memberCount.i
  member0.i
  member1.i
  member2.i
  member3.i
  imageDim.i
  imageDepth.i
  imageArrayed.i
  imageMultisampled.i
  imageSampled.i
  imageFormat.i
EndStructure

Structure AvkIrConstant Align #PB_Structure_AlignC
  sourceId.i
  sourceOpcode.i
  typeId.i
  wordCount.i
  word0.i
  componentCount.i
  component0.i
  component1.i
  component2.i
  component3.i
EndStructure

Structure AvkIrVariable Align #PB_Structure_AlignC
  sourceId.i
  sourceOpcode.i
  pointerType.i
  storageClass.i
EndStructure

Structure AvkIrDecoration Align #PB_Structure_AlignC
  sourceId.i              ; decorated SPIR-V id, for deterministic diagnostics
  sourceOpcode.i          ; OpDecorate or OpMemberDecorate
  member.i                ; -1 for whole-id decoration
  kind.i
  value.i
EndStructure

Structure AvkIrBlock Align #PB_Structure_AlignC
  sourceId.i
  sourceOpcode.i
  firstNode.i
  nodeCount.i
  predecessorCount.i
  successorCount.i
EndStructure

Structure AvkIrNode Align #PB_Structure_AlignC
  sourceId.i              ; zero for Store and Return, which have no result id
  sourceOpcode.i
  kind.i
  resultType.i
  blockId.i
  operandCount.i
  operand0.i
  operand1.i
  operand2.i
  operand3.i
  literalCount.i
  literal0.i
EndStructure

Structure AvkIrModule Align #PB_Structure_AlignC
  idBound.i
  stage.i
  entryFunctionId.i
  entryFunctionOpcode.i
  functionTypeId.i
  returnTypeId.i
  entryBlockId.i
  typeCount.i
  types.i
  constantCount.i
  constants.i
  variableCount.i
  variables.i
  decorationCount.i
  decorations.i
  blockCount.i
  blocks.i
  nodeCount.i
  nodes.i
EndStructure

Global avkIrLastError.i = 0
Global avkIrLastId.i = 0
Global avkIrLastOpcode.i = 0
Global avkIrLastIndex.i = -1

Procedure.i AnvilVkIrLastError() : ProcedureReturn avkIrLastError : EndProcedure
Procedure.i AnvilVkIrLastId() : ProcedureReturn avkIrLastId : EndProcedure
Procedure.i AnvilVkIrLastOpcode() : ProcedureReturn avkIrLastOpcode : EndProcedure
Procedure.i AnvilVkIrLastIndex() : ProcedureReturn avkIrLastIndex : EndProcedure

Procedure.i avkIrFail(code.i, id.i, opcode.i, index.i)
  avkIrLastError = code
  avkIrLastId = id
  avkIrLastOpcode = opcode
  avkIrLastIndex = index
  ProcedureReturn code
EndProcedure

Procedure.i avkIrIdOk(*m.AvkIrModule, id.i)
  If id < 1 Or id >= *m\idBound : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i avkIrStorageOk(storage.i)
  If storage = #ANVIL_IR_STORAGE_UNIFORM_CONSTANT Or storage = #ANVIL_IR_STORAGE_INPUT Or storage = #ANVIL_IR_STORAGE_UNIFORM Or storage = #ANVIL_IR_STORAGE_OUTPUT Or storage = #ANVIL_IR_STORAGE_PUSH_CONSTANT
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i avkIrTypeAt(*m.AvkIrModule, index.i)
  ProcedureReturn *m\types + (index * SizeOf(AvkIrType))
EndProcedure
Procedure.i avkIrConstantAt(*m.AvkIrModule, index.i)
  ProcedureReturn *m\constants + (index * SizeOf(AvkIrConstant))
EndProcedure
Procedure.i avkIrVariableAt(*m.AvkIrModule, index.i)
  ProcedureReturn *m\variables + (index * SizeOf(AvkIrVariable))
EndProcedure
Procedure.i avkIrDecorationAt(*m.AvkIrModule, index.i)
  ProcedureReturn *m\decorations + (index * SizeOf(AvkIrDecoration))
EndProcedure
Procedure.i avkIrBlockAt(*m.AvkIrModule, index.i)
  ProcedureReturn *m\blocks + (index * SizeOf(AvkIrBlock))
EndProcedure
Procedure.i avkIrNodeAt(*m.AvkIrModule, index.i)
  ProcedureReturn *m\nodes + (index * SizeOf(AvkIrNode))
EndProcedure

Procedure.i avkIrFindType(*m.AvkIrModule, id.i)
  Protected i.i
  Protected *t.AvkIrType
  i = 0
  While i < *m\typeCount
    *t = avkIrTypeAt(*m, i)
    If *t\sourceId = id : ProcedureReturn *t : EndIf
    i = i + 1
  Wend
  ProcedureReturn 0
EndProcedure

Procedure.i avkIrFindConstant(*m.AvkIrModule, id.i)
  Protected i.i
  Protected *c.AvkIrConstant
  i = 0
  While i < *m\constantCount
    *c = avkIrConstantAt(*m, i)
    If *c\sourceId = id : ProcedureReturn *c : EndIf
    i = i + 1
  Wend
  ProcedureReturn 0
EndProcedure

Procedure.i avkIrFindVariable(*m.AvkIrModule, id.i)
  Protected i.i
  Protected *v.AvkIrVariable
  i = 0
  While i < *m\variableCount
    *v = avkIrVariableAt(*m, i)
    If *v\sourceId = id : ProcedureReturn *v : EndIf
    i = i + 1
  Wend
  ProcedureReturn 0
EndProcedure

Procedure.i avkIrFindNode(*m.AvkIrModule, id.i)
  Protected i.i
  Protected *n.AvkIrNode
  i = 0
  While i < *m\nodeCount
    *n = avkIrNodeAt(*m, i)
    If *n\sourceId = id : ProcedureReturn *n : EndIf
    i = i + 1
  Wend
  ProcedureReturn 0
EndProcedure

Procedure.i avkIrNodeIndex(*m.AvkIrModule, id.i)
  Protected i.i
  Protected *n.AvkIrNode
  i = 0
  While i < *m\nodeCount
    *n = avkIrNodeAt(*m, i)
    If *n\sourceId = id : ProcedureReturn i : EndIf
    i = i + 1
  Wend
  ProcedureReturn -1
EndProcedure

Procedure.i avkIrValueType(*m.AvkIrModule, id.i)
  Protected *c.AvkIrConstant
  Protected *v.AvkIrVariable
  Protected *n.AvkIrNode
  *c = avkIrFindConstant(*m, id)
  If *c <> 0 : ProcedureReturn *c\typeId : EndIf
  *v = avkIrFindVariable(*m, id)
  If *v <> 0 : ProcedureReturn *v\pointerType : EndIf
  *n = avkIrFindNode(*m, id)
  If *n <> 0 : ProcedureReturn *n\resultType : EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i avkIrDefined(*m.AvkIrModule, id.i)
  Protected i.i
  Protected *b.AvkIrBlock
  If avkIrFindType(*m, id) <> 0 Or avkIrFindConstant(*m, id) <> 0 Or avkIrFindVariable(*m, id) <> 0 Or avkIrFindNode(*m, id) <> 0
    ProcedureReturn 1
  EndIf
  If *m\entryFunctionId = id : ProcedureReturn 1 : EndIf
  i = 0
  While i < *m\blockCount
    *b = avkIrBlockAt(*m, i)
    If *b\sourceId = id : ProcedureReturn 1 : EndIf
    i = i + 1
  Wend
  ProcedureReturn 0
EndProcedure

Procedure.i avkIrMemberType(*t.AvkIrType, index.i)
  If index = 0 : ProcedureReturn *t\member0 : EndIf
  If index = 1 : ProcedureReturn *t\member1 : EndIf
  If index = 2 : ProcedureReturn *t\member2 : EndIf
  If index = 3 : ProcedureReturn *t\member3 : EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i avkIrOperand(*n.AvkIrNode, index.i)
  If index = 0 : ProcedureReturn *n\operand0 : EndIf
  If index = 1 : ProcedureReturn *n\operand1 : EndIf
  If index = 2 : ProcedureReturn *n\operand2 : EndIf
  If index = 3 : ProcedureReturn *n\operand3 : EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i avkIrConstantComponent(*c.AvkIrConstant, index.i)
  If index = 0 : ProcedureReturn *c\component0 : EndIf
  If index = 1 : ProcedureReturn *c\component1 : EndIf
  If index = 2 : ProcedureReturn *c\component2 : EndIf
  If index = 3 : ProcedureReturn *c\component3 : EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i avkIrExpectedTypeOpcode(kind.i)
  If kind = #ANVIL_IR_TYPE_VOID : ProcedureReturn #ANVIL_IR_SPV_TYPE_VOID : EndIf
  If kind = #ANVIL_IR_TYPE_INT : ProcedureReturn #ANVIL_IR_SPV_TYPE_INT : EndIf
  If kind = #ANVIL_IR_TYPE_FLOAT : ProcedureReturn #ANVIL_IR_SPV_TYPE_FLOAT : EndIf
  If kind = #ANVIL_IR_TYPE_VECTOR : ProcedureReturn #ANVIL_IR_SPV_TYPE_VECTOR : EndIf
  If kind = #ANVIL_IR_TYPE_STRUCT : ProcedureReturn #ANVIL_IR_SPV_TYPE_STRUCT : EndIf
  If kind = #ANVIL_IR_TYPE_POINTER : ProcedureReturn #ANVIL_IR_SPV_TYPE_POINTER : EndIf
  If kind = #ANVIL_IR_TYPE_FUNCTION : ProcedureReturn #ANVIL_IR_SPV_TYPE_FUNCTION : EndIf
  If kind = #ANVIL_IR_TYPE_IMAGE : ProcedureReturn #ANVIL_IR_SPV_TYPE_IMAGE : EndIf
  If kind = #ANVIL_IR_TYPE_SAMPLED_IMAGE : ProcedureReturn #ANVIL_IR_SPV_TYPE_SAMPLED_IMAGE : EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i avkIrExpectedNodeOpcode(kind.i)
  If kind = #ANVIL_IR_OP_LOAD : ProcedureReturn #ANVIL_IR_SPV_LOAD : EndIf
  If kind = #ANVIL_IR_OP_ACCESS_CHAIN : ProcedureReturn #ANVIL_IR_SPV_ACCESS_CHAIN : EndIf
  If kind = #ANVIL_IR_OP_COMPOSITE_EXTRACT : ProcedureReturn #ANVIL_IR_SPV_COMPOSITE_EXTRACT : EndIf
  If kind = #ANVIL_IR_OP_COMPOSITE_CONSTRUCT : ProcedureReturn #ANVIL_IR_SPV_COMPOSITE_CONSTRUCT : EndIf
  If kind = #ANVIL_IR_OP_IMAGE_SAMPLE_IMPLICIT_LOD : ProcedureReturn #ANVIL_IR_SPV_IMAGE_SAMPLE_IMPLICIT_LOD : EndIf
  If kind = #ANVIL_IR_OP_STORE : ProcedureReturn #ANVIL_IR_SPV_STORE : EndIf
  If kind = #ANVIL_IR_OP_RETURN : ProcedureReturn #ANVIL_IR_SPV_RETURN : EndIf
  If kind = #ANVIL_IR_OP_FADD : ProcedureReturn #ANVIL_IR_SPV_FADD : EndIf
  If kind = #ANVIL_IR_OP_FMUL : ProcedureReturn #ANVIL_IR_SPV_FMUL : EndIf
  ProcedureReturn 0
EndProcedure

; Return the number of float32 lanes represented by typeId, or zero for
; anything outside scalar/vec2/vec3/vec4 binary32. SPIR-V arithmetic requires
; both operands and the result to have the same type; the caller checks the
; exact type ID as well as this shape.
Procedure.i avkIrFloatLanes(*m.AvkIrModule, typeId.i)
  Protected *t.AvkIrType
  Protected *component.AvkIrType
  *t = avkIrFindType(*m, typeId)
  If *t = 0 : ProcedureReturn 0 : EndIf
  If *t\kind = #ANVIL_IR_TYPE_FLOAT
    If *t\width = 32 : ProcedureReturn 1 : EndIf
    ProcedureReturn 0
  EndIf
  If *t\kind <> #ANVIL_IR_TYPE_VECTOR Or *t\componentCount < 2 Or *t\componentCount > 4
    ProcedureReturn 0
  EndIf
  *component = avkIrFindType(*m, *t\componentType)
  If *component = 0
    ProcedureReturn 0
  EndIf
  If *component\kind <> #ANVIL_IR_TYPE_FLOAT Or *component\width <> 32
    ProcedureReturn 0
  EndIf
  ProcedureReturn *t\componentCount
EndProcedure

; Is id defined by an instruction that dominates nodeIndex? Global constants
; and variables dominate the entry block; a node value must be earlier in the
; same sole block. This becomes a general dominator relation when CFG expands.
Procedure.i avkIrUseBefore(*m.AvkIrModule, id.i, nodeIndex.i, blockId.i)
  Protected def.i
  Protected *n.AvkIrNode
  If avkIrFindConstant(*m, id) <> 0 Or avkIrFindVariable(*m, id) <> 0
    ProcedureReturn 1
  EndIf
  def = avkIrNodeIndex(*m, id)
  If def < 0 : ProcedureReturn 0 : EndIf
  *n = avkIrNodeAt(*m, def)
  If *n\blockId <> blockId Or def >= nodeIndex : ProcedureReturn -1 : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i avkIrCheckCounts(*m.AvkIrModule)
  If *m\idBound < 2 Or *m\idBound > (#ANVIL_IR_MAX_ID + 1)
    ProcedureReturn avkIrFail(#ANVIL_IR_ERR_BOUNDS, *m\idBound, 0, -1)
  EndIf
  If *m\typeCount < 1 Or *m\typeCount > #ANVIL_IR_MAX_TYPES Or *m\types = 0
    ProcedureReturn avkIrFail(#ANVIL_IR_ERR_BOUNDS, 0, 0, -1)
  EndIf
  If *m\constantCount < 0 Or *m\constantCount > #ANVIL_IR_MAX_CONSTANTS Or (*m\constantCount > 0 And *m\constants = 0)
    ProcedureReturn avkIrFail(#ANVIL_IR_ERR_BOUNDS, 0, 0, -1)
  EndIf
  If *m\variableCount < 0 Or *m\variableCount > #ANVIL_IR_MAX_VARIABLES Or (*m\variableCount > 0 And *m\variables = 0)
    ProcedureReturn avkIrFail(#ANVIL_IR_ERR_BOUNDS, 0, 0, -1)
  EndIf
  If *m\decorationCount < 0 Or *m\decorationCount > #ANVIL_IR_MAX_DECORATIONS Or (*m\decorationCount > 0 And *m\decorations = 0)
    ProcedureReturn avkIrFail(#ANVIL_IR_ERR_BOUNDS, 0, 0, -1)
  EndIf
  If *m\blockCount < 1 Or *m\blockCount > #ANVIL_IR_MAX_BLOCKS Or *m\blocks = 0
    ProcedureReturn avkIrFail(#ANVIL_IR_ERR_BOUNDS, 0, 0, -1)
  EndIf
  If *m\nodeCount < 1 Or *m\nodeCount > #ANVIL_IR_MAX_NODES Or *m\nodes = 0
    ProcedureReturn avkIrFail(#ANVIL_IR_ERR_BOUNDS, 0, 0, -1)
  EndIf
  ProcedureReturn #ANVIL_IR_OK
EndProcedure

; Return 1 when an id appears anywhere in the module, 0 when absent. The
; duplicate pass calls this only against records preceding the current one.
Procedure.i avkIrPriorId(*m.AvkIrModule, id.i, section.i, index.i)
  Protected i.i
  Protected *t.AvkIrType
  Protected *c.AvkIrConstant
  Protected *v.AvkIrVariable
  Protected *b.AvkIrBlock
  Protected *n.AvkIrNode
  If section > 0
    i = 0 : While i < *m\typeCount : *t = avkIrTypeAt(*m, i) : If *t\sourceId = id : ProcedureReturn 1 : EndIf : i = i + 1 : Wend
  Else
    i = 0 : While i < index : *t = avkIrTypeAt(*m, i) : If *t\sourceId = id : ProcedureReturn 1 : EndIf : i = i + 1 : Wend
  EndIf
  If section > 1
    i = 0 : While i < *m\constantCount : *c = avkIrConstantAt(*m, i) : If *c\sourceId = id : ProcedureReturn 1 : EndIf : i = i + 1 : Wend
  ElseIf section = 1
    i = 0 : While i < index : *c = avkIrConstantAt(*m, i) : If *c\sourceId = id : ProcedureReturn 1 : EndIf : i = i + 1 : Wend
  EndIf
  If section > 2
    i = 0 : While i < *m\variableCount : *v = avkIrVariableAt(*m, i) : If *v\sourceId = id : ProcedureReturn 1 : EndIf : i = i + 1 : Wend
  ElseIf section = 2
    i = 0 : While i < index : *v = avkIrVariableAt(*m, i) : If *v\sourceId = id : ProcedureReturn 1 : EndIf : i = i + 1 : Wend
  EndIf
  If section > 3 And *m\entryFunctionId = id : ProcedureReturn 1 : EndIf
  If section > 4
    i = 0 : While i < *m\blockCount : *b = avkIrBlockAt(*m, i) : If *b\sourceId = id : ProcedureReturn 1 : EndIf : i = i + 1 : Wend
  ElseIf section = 4
    i = 0 : While i < index : *b = avkIrBlockAt(*m, i) : If *b\sourceId = id : ProcedureReturn 1 : EndIf : i = i + 1 : Wend
  EndIf
  If section = 5
    i = 0 : While i < index : *n = avkIrNodeAt(*m, i) : If *n\sourceId <> 0 And *n\sourceId = id : ProcedureReturn 1 : EndIf : i = i + 1 : Wend
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i avkIrCheckUniqueIds(*m.AvkIrModule)
  Protected i.i
  Protected id.i
  Protected op.i
  Protected *t.AvkIrType
  Protected *c.AvkIrConstant
  Protected *v.AvkIrVariable
  Protected *b.AvkIrBlock
  Protected *n.AvkIrNode
  i = 0
  While i < *m\typeCount
    *t = avkIrTypeAt(*m, i) : id = *t\sourceId : op = *t\sourceOpcode
    If avkIrIdOk(*m, id) = 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_BOUNDS, id, op, i) : EndIf
    If avkIrPriorId(*m, id, 0, i) <> 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_DUPLICATE, id, op, i) : EndIf
    i = i + 1
  Wend
  i = 0
  While i < *m\constantCount
    *c = avkIrConstantAt(*m, i) : id = *c\sourceId : op = *c\sourceOpcode
    If avkIrIdOk(*m, id) = 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_BOUNDS, id, op, i) : EndIf
    If avkIrPriorId(*m, id, 1, i) <> 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_DUPLICATE, id, op, i) : EndIf
    i = i + 1
  Wend
  i = 0
  While i < *m\variableCount
    *v = avkIrVariableAt(*m, i) : id = *v\sourceId : op = *v\sourceOpcode
    If avkIrIdOk(*m, id) = 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_BOUNDS, id, op, i) : EndIf
    If avkIrPriorId(*m, id, 2, i) <> 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_DUPLICATE, id, op, i) : EndIf
    i = i + 1
  Wend
  id = *m\entryFunctionId
  If avkIrIdOk(*m, id) = 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_BOUNDS, id, *m\entryFunctionOpcode, -1) : EndIf
  If avkIrPriorId(*m, id, 3, 0) <> 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_DUPLICATE, id, *m\entryFunctionOpcode, -1) : EndIf
  i = 0
  While i < *m\blockCount
    *b = avkIrBlockAt(*m, i) : id = *b\sourceId : op = *b\sourceOpcode
    If avkIrIdOk(*m, id) = 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_BOUNDS, id, op, i) : EndIf
    If avkIrPriorId(*m, id, 4, i) <> 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_DUPLICATE, id, op, i) : EndIf
    i = i + 1
  Wend
  i = 0
  While i < *m\nodeCount
    *n = avkIrNodeAt(*m, i)
    If *n\sourceId <> 0
      id = *n\sourceId : op = *n\sourceOpcode
      If avkIrIdOk(*m, id) = 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_BOUNDS, id, op, i) : EndIf
      If avkIrPriorId(*m, id, 5, i) <> 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_DUPLICATE, id, op, i) : EndIf
    EndIf
    i = i + 1
  Wend
  ProcedureReturn #ANVIL_IR_OK
EndProcedure

Procedure.i avkIrCheckTypes(*m.AvkIrModule)
  Protected i.i
  Protected k.i
  Protected id.i
  Protected member.i
  Protected *t.AvkIrType
  Protected *u.AvkIrType
  i = 0
  While i < *m\typeCount
    *t = avkIrTypeAt(*m, i)
    id = *t\sourceId
    If avkIrExpectedTypeOpcode(*t\kind) = 0 Or *t\sourceOpcode <> avkIrExpectedTypeOpcode(*t\kind)
      ProcedureReturn avkIrFail(#ANVIL_IR_ERR_UNSUPPORTED, id, *t\sourceOpcode, i)
    EndIf
    If *t\kind = #ANVIL_IR_TYPE_INT
      If *t\width <> 32 Or (*t\signedness <> 0 And *t\signedness <> 1) : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, id, *t\sourceOpcode, i) : EndIf
    ElseIf *t\kind = #ANVIL_IR_TYPE_FLOAT
      If *t\width <> 32 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, id, *t\sourceOpcode, i) : EndIf
    ElseIf *t\kind = #ANVIL_IR_TYPE_VECTOR
      *u = avkIrFindType(*m, *t\componentType)
      If *u = 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_UNDEFINED, *t\componentType, *t\sourceOpcode, i) : EndIf
      If (*u\kind <> #ANVIL_IR_TYPE_INT And *u\kind <> #ANVIL_IR_TYPE_FLOAT) Or *t\componentCount < 2 Or *t\componentCount > 4
        ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, id, *t\sourceOpcode, i)
      EndIf
    ElseIf *t\kind = #ANVIL_IR_TYPE_STRUCT
      If *t\memberCount < 1 Or *t\memberCount > #ANVIL_IR_MAX_MEMBERS : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, id, *t\sourceOpcode, i) : EndIf
      k = 0
      While k < *t\memberCount
        member = avkIrMemberType(*t, k)
        If avkIrFindType(*m, member) = 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_UNDEFINED, member, *t\sourceOpcode, i) : EndIf
        k = k + 1
      Wend
    ElseIf *t\kind = #ANVIL_IR_TYPE_POINTER
      If avkIrStorageOk(*t\storageClass) = 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_STORAGE, id, *t\sourceOpcode, i) : EndIf
      If avkIrFindType(*m, *t\pointeeType) = 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_UNDEFINED, *t\pointeeType, *t\sourceOpcode, i) : EndIf
    ElseIf *t\kind = #ANVIL_IR_TYPE_FUNCTION
      *u = avkIrFindType(*m, *t\returnType)
      If *u = 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_UNDEFINED, *t\returnType, *t\sourceOpcode, i) : EndIf
      If *u\kind <> #ANVIL_IR_TYPE_VOID Or *t\componentCount <> 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, id, *t\sourceOpcode, i) : EndIf
    ElseIf *t\kind = #ANVIL_IR_TYPE_IMAGE
      *u = avkIrFindType(*m, *t\componentType)
      If *u = 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_UNDEFINED, *t\componentType, *t\sourceOpcode, i) : EndIf
      If *u\kind <> #ANVIL_IR_TYPE_FLOAT Or *u\width <> 32 Or *t\imageDim <> 1 Or *t\imageDepth <> 0 Or *t\imageArrayed <> 0 Or *t\imageMultisampled <> 0 Or *t\imageSampled <> 1 Or *t\imageFormat <> 0
        ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, id, *t\sourceOpcode, i)
      EndIf
    ElseIf *t\kind = #ANVIL_IR_TYPE_SAMPLED_IMAGE
      *u = avkIrFindType(*m, *t\componentType)
      If *u = 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_UNDEFINED, *t\componentType, *t\sourceOpcode, i) : EndIf
      If *u\kind <> #ANVIL_IR_TYPE_IMAGE : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, id, *t\sourceOpcode, i) : EndIf
    EndIf
    i = i + 1
  Wend
  ProcedureReturn #ANVIL_IR_OK
EndProcedure

Procedure.i avkIrCheckConstants(*m.AvkIrModule)
  Protected i.i
  Protected k.i
  Protected cid.i
  Protected *c.AvkIrConstant
  Protected *part.AvkIrConstant
  Protected *t.AvkIrType
  i = 0
  While i < *m\constantCount
    *c = avkIrConstantAt(*m, i)
    *t = avkIrFindType(*m, *c\typeId)
    If *t = 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_UNDEFINED, *c\typeId, *c\sourceOpcode, i) : EndIf
    If *t\kind = #ANVIL_IR_TYPE_INT Or *t\kind = #ANVIL_IR_TYPE_FLOAT
      If *c\sourceOpcode <> #ANVIL_IR_SPV_CONSTANT Or *c\wordCount <> 1 Or *c\componentCount <> 0
        ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, *c\sourceId, *c\sourceOpcode, i)
      EndIf
    ElseIf *t\kind = #ANVIL_IR_TYPE_VECTOR
      If *c\sourceOpcode <> #ANVIL_IR_SPV_CONSTANT_COMPOSITE Or *c\wordCount <> 0 Or *c\componentCount <> *t\componentCount
        ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, *c\sourceId, *c\sourceOpcode, i)
      EndIf
      k = 0
      While k < *c\componentCount
        cid = avkIrConstantComponent(*c, k)
        *part = avkIrFindConstant(*m, cid)
        If *part = 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_UNDEFINED, cid, *c\sourceOpcode, i) : EndIf
        If *part\typeId <> *t\componentType : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, cid, *c\sourceOpcode, i) : EndIf
        k = k + 1
      Wend
    Else
      ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, *c\sourceId, *c\sourceOpcode, i)
    EndIf
    i = i + 1
  Wend
  ProcedureReturn #ANVIL_IR_OK
EndProcedure

Procedure.i avkIrCheckVariables(*m.AvkIrModule)
  Protected i.i
  Protected *v.AvkIrVariable
  Protected *t.AvkIrType
  i = 0
  While i < *m\variableCount
    *v = avkIrVariableAt(*m, i)
    If *v\sourceOpcode <> #ANVIL_IR_SPV_VARIABLE : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_UNSUPPORTED, *v\sourceId, *v\sourceOpcode, i) : EndIf
    If avkIrStorageOk(*v\storageClass) = 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_STORAGE, *v\sourceId, *v\sourceOpcode, i) : EndIf
    *t = avkIrFindType(*m, *v\pointerType)
    If *t = 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_UNDEFINED, *v\pointerType, *v\sourceOpcode, i) : EndIf
    If *t\kind <> #ANVIL_IR_TYPE_POINTER Or *t\storageClass <> *v\storageClass
      ProcedureReturn avkIrFail(#ANVIL_IR_ERR_STORAGE, *v\sourceId, *v\sourceOpcode, i)
    EndIf
    i = i + 1
  Wend
  ProcedureReturn #ANVIL_IR_OK
EndProcedure

Procedure.i avkIrCheckDecorations(*m.AvkIrModule)
  Protected i.i
  Protected j.i
  Protected targetKind.i
  Protected *d.AvkIrDecoration
  Protected *prior.AvkIrDecoration
  Protected *t.AvkIrType
  Protected *v.AvkIrVariable
  i = 0
  While i < *m\decorationCount
    *d = avkIrDecorationAt(*m, i)
    If avkIrIdOk(*m, *d\sourceId) = 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_BOUNDS, *d\sourceId, *d\sourceOpcode, i) : EndIf
    If *d\sourceOpcode <> #ANVIL_IR_SPV_DECORATE And *d\sourceOpcode <> #ANVIL_IR_SPV_MEMBER_DECORATE
      ProcedureReturn avkIrFail(#ANVIL_IR_ERR_UNSUPPORTED, *d\sourceId, *d\sourceOpcode, i)
    EndIf
    *t = avkIrFindType(*m, *d\sourceId)
    *v = avkIrFindVariable(*m, *d\sourceId)
    If avkIrDefined(*m, *d\sourceId) = 0
      ProcedureReturn avkIrFail(#ANVIL_IR_ERR_UNDEFINED, *d\sourceId, *d\sourceOpcode, i)
    EndIf
    If *d\member >= 0
      If *d\sourceOpcode <> #ANVIL_IR_SPV_MEMBER_DECORATE Or *t = 0 Or *t\kind <> #ANVIL_IR_TYPE_STRUCT Or *d\member >= *t\memberCount
        ProcedureReturn avkIrFail(#ANVIL_IR_ERR_DECORATION, *d\sourceId, *d\sourceOpcode, i)
      EndIf
    ElseIf *d\sourceOpcode <> #ANVIL_IR_SPV_DECORATE
      ProcedureReturn avkIrFail(#ANVIL_IR_ERR_DECORATION, *d\sourceId, *d\sourceOpcode, i)
    EndIf
    If *d\kind < #ANVIL_IR_DEC_RELAXED_PRECISION Or *d\kind > #ANVIL_IR_DEC_FP_FAST_MATH_MODE
      ProcedureReturn avkIrFail(#ANVIL_IR_ERR_UNSUPPORTED, *d\sourceId, *d\sourceOpcode, i)
    EndIf
    If *d\kind = #ANVIL_IR_DEC_BLOCK
      If *d\member >= 0 Or *t = 0 Or *t\kind <> #ANVIL_IR_TYPE_STRUCT : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_DECORATION, *d\sourceId, *d\sourceOpcode, i) : EndIf
    ElseIf *d\kind = #ANVIL_IR_DEC_RELAXED_PRECISION
      If *d\member < 0 And *v = 0 And avkIrFindConstant(*m, *d\sourceId) = 0 And avkIrFindNode(*m, *d\sourceId) = 0
        ProcedureReturn avkIrFail(#ANVIL_IR_ERR_DECORATION, *d\sourceId, *d\sourceOpcode, i)
      EndIf
    ElseIf *d\kind = #ANVIL_IR_DEC_LOCATION
      If *d\member >= 0 Or *v = 0 Or (*v\storageClass <> #ANVIL_IR_STORAGE_INPUT And *v\storageClass <> #ANVIL_IR_STORAGE_OUTPUT) : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_DECORATION, *d\sourceId, *d\sourceOpcode, i) : EndIf
    ElseIf *d\kind = #ANVIL_IR_DEC_DESCRIPTOR_SET Or *d\kind = #ANVIL_IR_DEC_BINDING
      If *d\member >= 0 Or *v = 0 Or (*v\storageClass <> #ANVIL_IR_STORAGE_UNIFORM And *v\storageClass <> #ANVIL_IR_STORAGE_UNIFORM_CONSTANT) : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_DECORATION, *d\sourceId, *d\sourceOpcode, i) : EndIf
    ElseIf *d\kind = #ANVIL_IR_DEC_BUILTIN
      If *v = 0 And *d\member < 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_DECORATION, *d\sourceId, *d\sourceOpcode, i) : EndIf
      If *v <> 0 And *v\storageClass <> #ANVIL_IR_STORAGE_INPUT And *v\storageClass <> #ANVIL_IR_STORAGE_OUTPUT : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_DECORATION, *d\sourceId, *d\sourceOpcode, i) : EndIf
    ElseIf *d\kind = #ANVIL_IR_DEC_OFFSET
      If *d\member < 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_DECORATION, *d\sourceId, *d\sourceOpcode, i) : EndIf
    ElseIf *d\kind = #ANVIL_IR_DEC_ARRAY_STRIDE
      ; Arrays are outside this tranche, so no valid target can carry this.
      ProcedureReturn avkIrFail(#ANVIL_IR_ERR_UNSUPPORTED, *d\sourceId, *d\sourceOpcode, i)
    ElseIf *d\kind = #ANVIL_IR_DEC_COL_MAJOR Or *d\kind = #ANVIL_IR_DEC_MATRIX_STRIDE
      ; Matrix types are outside this tranche, so these cannot be valid here.
      ProcedureReturn avkIrFail(#ANVIL_IR_ERR_UNSUPPORTED, *d\sourceId, *d\sourceOpcode, i)
    ElseIf *d\kind = #ANVIL_IR_DEC_NO_CONTRACTION Or *d\kind = #ANVIL_IR_DEC_FP_FAST_MATH_MODE
      ; These control the permitted floating-point transformation contract.
      ; Until the parser and every lowerer preserve that contract, recognizing
      ; and refusing them is safer than silently emitting different arithmetic.
      ProcedureReturn avkIrFail(#ANVIL_IR_ERR_UNSUPPORTED, *d\sourceId, *d\sourceOpcode, i)
    EndIf
    j = 0
    While j < i
      *prior = avkIrDecorationAt(*m, j)
      If *prior\sourceId = *d\sourceId And *prior\member = *d\member And *prior\kind = *d\kind
        ProcedureReturn avkIrFail(#ANVIL_IR_ERR_DECORATION, *d\sourceId, *d\sourceOpcode, i)
      EndIf
      j = j + 1
    Wend
    i = i + 1
  Wend
  ProcedureReturn #ANVIL_IR_OK
EndProcedure

Procedure.i avkIrCheckUse(*m.AvkIrModule, id.i, nodeIndex.i, *n.AvkIrNode)
  Protected d.i
  d = avkIrUseBefore(*m, id, nodeIndex, *n\blockId)
  If d = 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_UNDEFINED, id, *n\sourceOpcode, nodeIndex) : EndIf
  If d < 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_DOMINANCE, id, *n\sourceOpcode, nodeIndex) : EndIf
  ProcedureReturn #ANVIL_IR_OK
EndProcedure

Procedure.i avkIrCheckNodes(*m.AvkIrModule)
  Protected i.i
  Protected k.i
  Protected rc.i
  Protected index.i
  Protected lanes.i
  Protected valueType.i
  Protected *n.AvkIrNode
  Protected *t.AvkIrType
  Protected *u.AvkIrType
  Protected *v.AvkIrVariable
  Protected *baseNode.AvkIrNode
  Protected *c.AvkIrConstant
  i = 0
  While i < *m\nodeCount
    *n = avkIrNodeAt(*m, i)
    If avkIrExpectedNodeOpcode(*n\kind) = 0 Or *n\sourceOpcode <> avkIrExpectedNodeOpcode(*n\kind)
      ProcedureReturn avkIrFail(#ANVIL_IR_ERR_UNSUPPORTED, *n\sourceId, *n\sourceOpcode, i)
    EndIf
    If *n\blockId <> *m\entryBlockId : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_CFG, *n\blockId, *n\sourceOpcode, i) : EndIf
    If *n\operandCount < 0 Or *n\operandCount > 4 Or *n\literalCount < 0 Or *n\literalCount > 1
      ProcedureReturn avkIrFail(#ANVIL_IR_ERR_BOUNDS, *n\sourceId, *n\sourceOpcode, i)
    EndIf
    k = 0
    While k < *n\operandCount
      rc = avkIrCheckUse(*m, avkIrOperand(*n, k), i, *n)
      If rc <> #ANVIL_IR_OK : ProcedureReturn rc : EndIf
      k = k + 1
    Wend

    If *n\kind = #ANVIL_IR_OP_LOAD
      If *n\sourceId = 0 Or *n\operandCount <> 1 Or *n\literalCount <> 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, *n\sourceId, *n\sourceOpcode, i) : EndIf
      *t = avkIrFindType(*m, avkIrValueType(*m, *n\operand0))
      If *t = 0 Or *t\kind <> #ANVIL_IR_TYPE_POINTER Or *n\resultType <> *t\pointeeType : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, *n\sourceId, *n\sourceOpcode, i) : EndIf
      *v = avkIrFindVariable(*m, *n\operand0)
      If *v <> 0
        If *v\storageClass <> #ANVIL_IR_STORAGE_INPUT And *v\storageClass <> #ANVIL_IR_STORAGE_UNIFORM_CONSTANT : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_STORAGE, *v\sourceId, *n\sourceOpcode, i) : EndIf
      Else
        *baseNode = avkIrFindNode(*m, *n\operand0)
        If *baseNode = 0 Or *baseNode\kind <> #ANVIL_IR_OP_ACCESS_CHAIN : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_STORAGE, *n\operand0, *n\sourceOpcode, i) : EndIf
        *v = avkIrFindVariable(*m, *baseNode\operand0)
        If *v = 0 Or (*v\storageClass <> #ANVIL_IR_STORAGE_UNIFORM And *v\storageClass <> #ANVIL_IR_STORAGE_PUSH_CONSTANT) : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_STORAGE, *baseNode\operand0, *n\sourceOpcode, i) : EndIf
      EndIf
    ElseIf *n\kind = #ANVIL_IR_OP_ACCESS_CHAIN
      If *n\sourceId = 0 Or *n\operandCount <> 2 Or *n\literalCount <> 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, *n\sourceId, *n\sourceOpcode, i) : EndIf
      *v = avkIrFindVariable(*m, *n\operand0)
      *c = avkIrFindConstant(*m, *n\operand1)
      If *v = 0 Or *c = 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, *n\sourceId, *n\sourceOpcode, i) : EndIf
      *t = avkIrFindType(*m, *v\pointerType)
      If *t = 0 Or *t\kind <> #ANVIL_IR_TYPE_POINTER : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, *v\sourceId, *n\sourceOpcode, i) : EndIf
      *u = avkIrFindType(*m, *t\pointeeType)
      If *u = 0 Or *u\kind <> #ANVIL_IR_TYPE_STRUCT : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, *v\sourceId, *n\sourceOpcode, i) : EndIf
      *t = avkIrFindType(*m, *c\typeId)
      If *t = 0 Or *t\kind <> #ANVIL_IR_TYPE_INT Or *t\width <> 32 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, *c\sourceId, *n\sourceOpcode, i) : EndIf
      index = *c\word0
      If index < 0 Or index >= *u\memberCount : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_BOUNDS, *c\sourceId, *n\sourceOpcode, i) : EndIf
      *t = avkIrFindType(*m, *n\resultType)
      If *t = 0 Or *t\kind <> #ANVIL_IR_TYPE_POINTER Or *t\storageClass <> *v\storageClass Or *t\pointeeType <> avkIrMemberType(*u, index)
        ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, *n\sourceId, *n\sourceOpcode, i)
      EndIf
    ElseIf *n\kind = #ANVIL_IR_OP_COMPOSITE_EXTRACT
      If *n\sourceId = 0 Or *n\operandCount <> 1 Or *n\literalCount <> 1 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, *n\sourceId, *n\sourceOpcode, i) : EndIf
      *t = avkIrFindType(*m, avkIrValueType(*m, *n\operand0))
      If *t = 0 Or *t\kind <> #ANVIL_IR_TYPE_VECTOR Or *n\literal0 < 0 Or *n\literal0 >= *t\componentCount Or *n\resultType <> *t\componentType
        ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, *n\sourceId, *n\sourceOpcode, i)
      EndIf
    ElseIf *n\kind = #ANVIL_IR_OP_COMPOSITE_CONSTRUCT
      If *n\sourceId = 0 Or *n\literalCount <> 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, *n\sourceId, *n\sourceOpcode, i) : EndIf
      *t = avkIrFindType(*m, *n\resultType)
      If *t = 0 Or *t\kind <> #ANVIL_IR_TYPE_VECTOR Or *n\operandCount <> *t\componentCount : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, *n\sourceId, *n\sourceOpcode, i) : EndIf
      k = 0
      While k < *n\operandCount
        If avkIrValueType(*m, avkIrOperand(*n, k)) <> *t\componentType : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, avkIrOperand(*n, k), *n\sourceOpcode, i) : EndIf
        k = k + 1
      Wend
    ElseIf *n\kind = #ANVIL_IR_OP_FADD Or *n\kind = #ANVIL_IR_OP_FMUL
      If *n\sourceId = 0 Or *n\operandCount <> 2 Or *n\literalCount <> 0
        ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, *n\sourceId, *n\sourceOpcode, i)
      EndIf
      lanes = avkIrFloatLanes(*m, *n\resultType)
      If lanes < 1
        ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, *n\sourceId, *n\sourceOpcode, i)
      EndIf
      If avkIrValueType(*m, *n\operand0) <> *n\resultType
        ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, *n\operand0, *n\sourceOpcode, i)
      EndIf
      If avkIrValueType(*m, *n\operand1) <> *n\resultType
        ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, *n\operand1, *n\sourceOpcode, i)
      EndIf
    ElseIf *n\kind = #ANVIL_IR_OP_IMAGE_SAMPLE_IMPLICIT_LOD
      If *n\sourceId = 0 Or *n\operandCount <> 2 Or *n\literalCount <> 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, *n\sourceId, *n\sourceOpcode, i) : EndIf
      *t = avkIrFindType(*m, avkIrValueType(*m, *n\operand0))
      If *t = 0 Or *t\kind <> #ANVIL_IR_TYPE_SAMPLED_IMAGE : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, *n\operand0, *n\sourceOpcode, i) : EndIf
      *baseNode = avkIrFindNode(*m, *n\operand0)
      If *baseNode = 0 Or *baseNode\kind <> #ANVIL_IR_OP_LOAD : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, *n\operand0, *n\sourceOpcode, i) : EndIf
      *v = avkIrFindVariable(*m, *baseNode\operand0)
      If *v = 0 Or *v\storageClass <> #ANVIL_IR_STORAGE_UNIFORM_CONSTANT : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_STORAGE, *baseNode\operand0, *n\sourceOpcode, i) : EndIf
      *t = avkIrFindType(*m, avkIrValueType(*m, *n\operand1))
      If *t = 0 Or *t\kind <> #ANVIL_IR_TYPE_VECTOR Or *t\componentCount <> 2 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, *n\operand1, *n\sourceOpcode, i) : EndIf
      *u = avkIrFindType(*m, *t\componentType)
      If *u = 0 Or *u\kind <> #ANVIL_IR_TYPE_FLOAT Or *u\width <> 32 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, *n\operand1, *n\sourceOpcode, i) : EndIf
      *baseNode = avkIrFindNode(*m, *n\operand1)
      If *baseNode = 0 Or *baseNode\kind <> #ANVIL_IR_OP_LOAD : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, *n\operand1, *n\sourceOpcode, i) : EndIf
      *v = avkIrFindVariable(*m, *baseNode\operand0)
      If *v = 0 Or *v\storageClass <> #ANVIL_IR_STORAGE_INPUT : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_STORAGE, *baseNode\operand0, *n\sourceOpcode, i) : EndIf
      *t = avkIrFindType(*m, *n\resultType)
      If *t = 0 Or *t\kind <> #ANVIL_IR_TYPE_VECTOR Or *t\componentCount <> 4 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, *n\sourceId, *n\sourceOpcode, i) : EndIf
      *u = avkIrFindType(*m, *t\componentType)
      If *u = 0 Or *u\kind <> #ANVIL_IR_TYPE_FLOAT Or *u\width <> 32 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, *n\sourceId, *n\sourceOpcode, i) : EndIf
    ElseIf *n\kind = #ANVIL_IR_OP_STORE
      If *n\sourceId <> 0 Or *n\resultType <> 0 Or *n\operandCount <> 2 Or *n\literalCount <> 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, *n\operand0, *n\sourceOpcode, i) : EndIf
      *t = avkIrFindType(*m, avkIrValueType(*m, *n\operand0))
      If *t = 0 Or *t\kind <> #ANVIL_IR_TYPE_POINTER Or *t\storageClass <> #ANVIL_IR_STORAGE_OUTPUT Or avkIrValueType(*m, *n\operand1) <> *t\pointeeType
        ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, *n\operand0, *n\sourceOpcode, i)
      EndIf
    ElseIf *n\kind = #ANVIL_IR_OP_RETURN
      If *n\sourceId <> 0 Or *n\resultType <> 0 Or *n\operandCount <> 0 Or *n\literalCount <> 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TERMINATOR, 0, *n\sourceOpcode, i) : EndIf
      If i <> (*m\nodeCount - 1) : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TERMINATOR, 0, *n\sourceOpcode, i) : EndIf
    EndIf
    i = i + 1
  Wend
  *n = avkIrNodeAt(*m, *m\nodeCount - 1)
  If *n\kind <> #ANVIL_IR_OP_RETURN : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TERMINATOR, *n\sourceId, *n\sourceOpcode, *m\nodeCount - 1) : EndIf
  ProcedureReturn #ANVIL_IR_OK
EndProcedure

Procedure.i avkIrCheckCfg(*m.AvkIrModule)
  Protected *b.AvkIrBlock
  Protected *ft.AvkIrType
  Protected *rt.AvkIrType
  If *m\stage <> #ANVIL_IR_STAGE_VERTEX And *m\stage <> #ANVIL_IR_STAGE_FRAGMENT
    ProcedureReturn avkIrFail(#ANVIL_IR_ERR_UNSUPPORTED, *m\entryFunctionId, *m\entryFunctionOpcode, -1)
  EndIf
  If *m\entryFunctionOpcode <> #ANVIL_IR_SPV_FUNCTION
    ProcedureReturn avkIrFail(#ANVIL_IR_ERR_UNSUPPORTED, *m\entryFunctionId, *m\entryFunctionOpcode, -1)
  EndIf
  *ft = avkIrFindType(*m, *m\functionTypeId)
  *rt = avkIrFindType(*m, *m\returnTypeId)
  If *ft = 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_UNDEFINED, *m\functionTypeId, *m\entryFunctionOpcode, -1) : EndIf
  If *rt = 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_UNDEFINED, *m\returnTypeId, *m\entryFunctionOpcode, -1) : EndIf
  If *ft\kind <> #ANVIL_IR_TYPE_FUNCTION Or *rt\kind <> #ANVIL_IR_TYPE_VOID Or *ft\returnType <> *m\returnTypeId
    ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, *m\entryFunctionId, *m\entryFunctionOpcode, -1)
  EndIf
  ; Current accepted subset: exactly one reachable block. Multiple blocks,
  ; edges and Phi require a real CFG/dominator implementation and are refused.
  If *m\blockCount <> 1 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_UNSUPPORTED, *m\entryBlockId, #ANVIL_IR_SPV_LABEL, -1) : EndIf
  *b = avkIrBlockAt(*m, 0)
  If *b\sourceOpcode <> #ANVIL_IR_SPV_LABEL Or *b\sourceId <> *m\entryBlockId
    ProcedureReturn avkIrFail(#ANVIL_IR_ERR_CFG, *b\sourceId, *b\sourceOpcode, 0)
  EndIf
  If *b\predecessorCount <> 0 Or *b\successorCount <> 0 Or *b\firstNode <> 0 Or *b\nodeCount <> *m\nodeCount
    ProcedureReturn avkIrFail(#ANVIL_IR_ERR_CFG, *b\sourceId, *b\sourceOpcode, 0)
  EndIf
  ProcedureReturn #ANVIL_IR_OK
EndProcedure

Procedure.i AnvilVkIrVerify(*m.AvkIrModule)
  Protected rc.i
  avkIrLastError = 0
  avkIrLastId = 0
  avkIrLastOpcode = 0
  avkIrLastIndex = -1
  If *m = 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_ARGS, 0, 0, -1) : EndIf
  rc = avkIrCheckCounts(*m) : If rc <> 0 : ProcedureReturn rc : EndIf
  rc = avkIrCheckUniqueIds(*m) : If rc <> 0 : ProcedureReturn rc : EndIf
  rc = avkIrCheckTypes(*m) : If rc <> 0 : ProcedureReturn rc : EndIf
  rc = avkIrCheckConstants(*m) : If rc <> 0 : ProcedureReturn rc : EndIf
  rc = avkIrCheckVariables(*m) : If rc <> 0 : ProcedureReturn rc : EndIf
  rc = avkIrCheckDecorations(*m) : If rc <> 0 : ProcedureReturn rc : EndIf
  rc = avkIrCheckCfg(*m) : If rc <> 0 : ProcedureReturn rc : EndIf
  ProcedureReturn avkIrCheckNodes(*m)
EndProcedure

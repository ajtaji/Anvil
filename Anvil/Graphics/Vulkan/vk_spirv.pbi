; ======================================================================
;  The SPIR-V front end -- parse, validate, refuse by name, and lower
; ======================================================================
; SPDX-License-Identifier: MIT
;
; Target-neutral. Nothing here knows a QPU register, a VPM slot, a
; control-list packet or a display. It reads a SPIR-V module, decides
; whether every word of it is inside the subset this implementation
; actually executes, and when it is, it writes a small PLAN that a
; backend can lower without ever reading the module again.
;
; The plan is deliberately not an IR. An IR is what the fourth item on
; the compatibility path asks for and it is not what exists here: this
; front end walks a module whose shape is declared, and refuses
; everything else out loud. Calling it a compiler would be a claim about
; arbitrary shaders that nothing in this file supports.
;
; THE WALK IS ITERATIVE AND THAT IS A CHOICE, not a limitation. The
; compiler now has automatic per-invocation frames, so a recursive walker
; would work; SPIR-V's physical layout does not need one. A module is a
; flat instruction stream in which every id is defined before it is used,
; so one pass over it and a table indexed by result id carry all the data
; flow an accepted shader has. Recursion becomes worth having when there
; are expression trees to walk, and the day this file gains arithmetic it
; will gain them - the one place the shape was already tempting is
; avkSpvIsFloatish(), which is written flat with a comment saying why.
;
; ======================================================================
;  WHAT IT ACCEPTS
; ======================================================================
;  One module, one entry point, one function, no control flow.
;
;  A VERTEX shader:
;    * inputs at Location 0..n-1, float or floatN, n <= 4
;    * one output that is BuiltIn Position, written with the x and y of
;      one input, z = the constant 0.0 and w = the constant 1.0
;    * zero or more outputs at a Location, each written with a whole
;      input load - a pass-through varying
;
;  A FRAGMENT shader:
;    * zero or more inputs at a Location
;    * exactly one output at Location 0, of four components, written
;      with either a whole input load (the interpolated varying), a load
;      of member 0 of the push-constant block (the uniform colour), or a
;      constant composite of four floats
;
;  Everything else is refused. The refusal is a whole sentence, it names
;  the opcode, capability, decoration, built-in or storage class that
;  caused it, and it says what to do instead.
;
; ======================================================================
;  PROVENANCE
; ======================================================================
;  The binary layout, the opcode numbers and the operand orders come from
;  the Khronos SPIR-V specification and its registry:
;    https://registry.khronos.org/SPIR-V/            (the specification,
;      section 2.3 for the physical layout and 3.x for the enumerants)
;    https://docs.vulkan.org/spec/latest/appendices/spirvenv.html
;      (the Vulkan environment: which capabilities, execution models,
;      addressing and memory models a Vulkan implementation must accept,
;      and which validation rules apply to a shader module)
;  Both were CONSULTED, in the sense docs/PROVENANCE_INVENTORY.md defines:
;  the numeric values below are the specification's own, transcribed the
;  way a header's values are; no code from any SPIR-V tool, from
;  SPIRV-Tools, from glslang or from any driver was read, translated or
;  copied. The walker, the validation rules, the refusal set and the plan
;  are this tree's own and are documented as such.

XIncludeFile "Anvil/Graphics/Vulkan/vk_foundation.pbi"

; ----------------------------------------------------------------------
;  The physical layout. SPIR-V specification section 2.3.
; ----------------------------------------------------------------------
#ANVIL_SPV_MAGIC = $07230203
; The same magic seen through a byte swap. A module produced on a
; big-endian host is a real thing to be handed and it is worth naming,
; because the alternative diagnosis - "this is not SPIR-V at all" - sends
; a reader looking in completely the wrong place.
#ANVIL_SPV_MAGIC_SWAPPED = $03022307
#ANVIL_SPV_VERSION_MAX = $00010600      ; SPIR-V 1.6
#ANVIL_SPV_HEADER_WORDS = 5

; Bounds. A module larger than this is refused rather than truncated: a
; front end that stops reading half way through a module and reports
; success is the one failure mode that cannot be caught downstream.
#ANVIL_SPV_MAX_ID = 192
#ANVIL_SPV_MAX_WORDS = 2048             ; 8 KiB of module
#ANVIL_SPV_MAX_ATTRS = 4
#ANVIL_SPV_MAX_VARYINGS = 4
#ANVIL_SPV_MAX_MEMBERS = 4

; ----------------------------------------------------------------------
;  Opcodes. Only the ones this file names are listed; the rest are
;  refused by number through AnvilVkSpirvLastOpcode().
; ----------------------------------------------------------------------
#SpvOpNop = 0
#SpvOpUndef = 1
#SpvOpSourceContinued = 2
#SpvOpSource = 3
#SpvOpSourceExtension = 4
#SpvOpName = 5
#SpvOpMemberName = 6
#SpvOpString = 7
#SpvOpLine = 8
#SpvOpExtension = 10
#SpvOpExtInstImport = 11
#SpvOpExtInst = 12
#SpvOpMemoryModel = 14
#SpvOpEntryPoint = 15
#SpvOpExecutionMode = 16
#SpvOpCapability = 17
#SpvOpTypeVoid = 19
#SpvOpTypeBool = 20
#SpvOpTypeInt = 21
#SpvOpTypeFloat = 22
#SpvOpTypeVector = 23
#SpvOpTypeMatrix = 24
#SpvOpTypeImage = 25
#SpvOpTypeSampler = 26
#SpvOpTypeSampledImage = 27
#SpvOpTypeArray = 28
#SpvOpTypeRuntimeArray = 29
#SpvOpTypeStruct = 30
#SpvOpTypePointer = 32
#SpvOpTypeFunction = 33
#SpvOpConstantTrue = 41
#SpvOpConstantFalse = 42
#SpvOpConstant = 43
#SpvOpConstantComposite = 44
#SpvOpConstantNull = 46
#SpvOpFunction = 54
#SpvOpFunctionParameter = 55
#SpvOpFunctionEnd = 56
#SpvOpFunctionCall = 57
#SpvOpVariable = 59
#SpvOpLoad = 61
#SpvOpStore = 62
#SpvOpAccessChain = 65
#SpvOpDecorate = 71
#SpvOpMemberDecorate = 72
#SpvOpDecorationGroup = 73
#SpvOpVectorShuffle = 79
#SpvOpCompositeConstruct = 80
#SpvOpCompositeExtract = 81
#SpvOpImageSampleImplicitLod = 87
#SpvOpConvertFToU = 109
#SpvOpConvertFToS = 110
#SpvOpConvertSToF = 111
#SpvOpConvertUToF = 112
#SpvOpFNegate = 127
#SpvOpIAdd = 128
#SpvOpFAdd = 129
#SpvOpISub = 130
#SpvOpFSub = 131
#SpvOpIMul = 132
#SpvOpFMul = 133
#SpvOpFDiv = 136
#SpvOpVectorTimesScalar = 142
#SpvOpMatrixTimesVector = 145
#SpvOpMatrixTimesMatrix = 146
#SpvOpDot = 148
#SpvOpLoopMerge = 246
#SpvOpSelectionMerge = 247
#SpvOpLabel = 248
#SpvOpBranch = 249
#SpvOpBranchConditional = 250
#SpvOpKill = 252
#SpvOpReturn = 253
#SpvOpReturnValue = 254
#SpvOpUnreachable = 255
#SpvOpNoLine = 317

; Execution models (specification 3.3).
#SpvExecutionModelVertex = 0
#SpvExecutionModelTessellationControl = 1
#SpvExecutionModelTessellationEvaluation = 2
#SpvExecutionModelGeometry = 3
#SpvExecutionModelFragment = 4
#SpvExecutionModelGLCompute = 5
#SpvExecutionModelKernel = 6

; Addressing and memory models (3.4, 3.5).
#SpvAddressingModelLogical = 0
#SpvMemoryModelGLSL450 = 1

; Execution modes (3.6).
#SpvExecutionModeOriginUpperLeft = 7
#SpvExecutionModeOriginLowerLeft = 8
#SpvExecutionModeDepthReplacing = 12
#SpvExecutionModeLocalSize = 17

; Storage classes (3.7).
#SpvStorageClassUniformConstant = 0
#SpvStorageClassInput = 1
#SpvStorageClassUniform = 2
#SpvStorageClassOutput = 3
#SpvStorageClassWorkgroup = 4
#SpvStorageClassPrivate = 6
#SpvStorageClassFunction = 7
#SpvStorageClassPushConstant = 9
#SpvStorageClassStorageBuffer = 12

; Decorations (3.20).
#SpvDecorationRelaxedPrecision = 0
#SpvDecorationBlock = 2
#SpvDecorationBufferBlock = 3
#SpvDecorationColMajor = 5
#SpvDecorationArrayStride = 6
#SpvDecorationMatrixStride = 7
#SpvDecorationBuiltIn = 11
#SpvDecorationNoPerspective = 13
#SpvDecorationFlat = 14
#SpvDecorationLocation = 30
#SpvDecorationComponent = 31
#SpvDecorationBinding = 33
#SpvDecorationDescriptorSet = 34
#SpvDecorationOffset = 35

; Built-ins (3.21).
#SpvBuiltInPosition = 0
#SpvBuiltInPointSize = 1
#SpvBuiltInClipDistance = 3
#SpvBuiltInCullDistance = 4
#SpvBuiltInFragCoord = 15
#SpvBuiltInPointCoord = 16
#SpvBuiltInFrontFacing = 17
#SpvBuiltInFragDepth = 22
#SpvBuiltInVertexIndex = 42
#SpvBuiltInInstanceIndex = 43

; Capabilities (3.31).
#SpvCapabilityMatrix = 0
#SpvCapabilityShader = 1
#SpvCapabilityGeometry = 2
#SpvCapabilityTessellation = 3
#SpvCapabilityFloat16 = 9
#SpvCapabilityFloat64 = 10
#SpvCapabilityInt64 = 11
#SpvCapabilityInt16 = 22
#SpvCapabilityInt8 = 39

; ----------------------------------------------------------------------
;  The type classes this walker distinguishes.
; ----------------------------------------------------------------------
#ANVIL_SPV_T_NONE = 0
#ANVIL_SPV_T_VOID = 1
#ANVIL_SPV_T_FLOAT = 2
#ANVIL_SPV_T_INT = 3
#ANVIL_SPV_T_VECTOR = 4
#ANVIL_SPV_T_STRUCT = 5
#ANVIL_SPV_T_POINTER = 6
#ANVIL_SPV_T_FUNCTION = 7

; What an id is.
#ANVIL_SPV_K_NONE = 0
#ANVIL_SPV_K_TYPE = 1
#ANVIL_SPV_K_CONST = 2
#ANVIL_SPV_K_VARIABLE = 3
#ANVIL_SPV_K_VALUE = 4
#ANVIL_SPV_K_FUNCTION = 5
#ANVIL_SPV_K_EXTSET = 6
#ANVIL_SPV_K_LABEL = 7

; Where an SSA value came from. This is the whole of the data flow this
; front end models, and it is a provenance tag rather than an expression
; tree because every accepted shader is a permutation of loads.
#ANVIL_SPV_V_NONE = 0
#ANVIL_SPV_V_INPUT = 1        ; a whole load of an Input variable
#ANVIL_SPV_V_PUSH = 2         ; a load of one member of the push block
#ANVIL_SPV_V_CONST = 3        ; a constant, scalar or composite
#ANVIL_SPV_V_COMPOSITE = 4    ; OpCompositeConstruct
#ANVIL_SPV_V_EXTRACT = 5      ; OpCompositeExtract of one component
#ANVIL_SPV_V_CHAIN = 6        ; OpAccessChain into a block variable

; The colour sources a fragment plan can name.
#ANVIL_SPV_COLOUR_VARYING = 0
#ANVIL_SPV_COLOUR_PUSH = 1
#ANVIL_SPV_COLOUR_CONST = 2

; ----------------------------------------------------------------------
;  WALK STATE. One module is parsed at a time and the result is copied
;  into the caller's plan slot, so these tables are scratch and nothing
;  outside this file may read them.
; ----------------------------------------------------------------------
Global Dim spvKind.i[#ANVIL_SPV_MAX_ID + 1]
Global Dim spvTypeClass.i[#ANVIL_SPV_MAX_ID + 1]
Global Dim spvTypeComp.i[#ANVIL_SPV_MAX_ID + 1]     ; vector component type / pointer pointee
Global Dim spvTypeCount.i[#ANVIL_SPV_MAX_ID + 1]    ; vector length / struct members / float width
Global Dim spvTypeStorage.i[#ANVIL_SPV_MAX_ID + 1]
Global Dim spvValueType.i[#ANVIL_SPV_MAX_ID + 1]
Global Dim spvValueSrc.i[#ANVIL_SPV_MAX_ID + 1]
Global Dim spvValueA.i[#ANVIL_SPV_MAX_ID + 1]
Global Dim spvValueB.i[#ANVIL_SPV_MAX_ID + 1]
Global Dim spvConstWord.i[#ANVIL_SPV_MAX_ID + 1]
Global Dim spvComposite.i[(#ANVIL_SPV_MAX_ID + 1) * 4]
Global Dim spvDecLocation.i[#ANVIL_SPV_MAX_ID + 1]
Global Dim spvDecBuiltIn.i[#ANVIL_SPV_MAX_ID + 1]
Global Dim spvDecBlock.a[#ANVIL_SPV_MAX_ID + 1]
Global Dim spvMemberBuiltIn.i[(#ANVIL_SPV_MAX_ID + 1) * #ANVIL_SPV_MAX_MEMBERS]
Global Dim spvStructMember.i[(#ANVIL_SPV_MAX_ID + 1) * #ANVIL_SPV_MAX_MEMBERS]

Global spvBound.i = 0
Global spvVersion.i = 0
Global spvGenerator.i = 0
Global spvStage.i = -1
Global spvEntry.i = 0
Global spvInstructions.i = 0
Global spvLastOpcode.i = 0
Global spvPushVar.i = 0
Global spvPosVar.i = 0          ; the Output variable that carries Position
Global spvPosMember.i = -1      ; -1 when Position is the variable itself
Global spvPosValue.i = 0        ; the value stored into it
Global spvOriginUpperLeft.i = 0

; The plan the walk produces, before it is copied into a slot.
Global spvPlanAttrCount.i = 0
Global spvPlanVaryCount.i = 0
Global spvPlanPosAttr.i = -1
Global spvPlanColourSrc.i = -1
Global spvPlanColourIdx.i = -1
Global Dim spvPlanAttrLoc.i[#ANVIL_SPV_MAX_ATTRS]
Global Dim spvPlanAttrComp.i[#ANVIL_SPV_MAX_ATTRS]
Global Dim spvPlanAttrVar.i[#ANVIL_SPV_MAX_ATTRS]
Global Dim spvPlanVaryLoc.i[#ANVIL_SPV_MAX_VARYINGS]
Global Dim spvPlanVaryComp.i[#ANVIL_SPV_MAX_VARYINGS]
Global Dim spvPlanVarySrc.i[#ANVIL_SPV_MAX_VARYINGS]
Global Dim spvPlanConst.i[4]

Procedure.i AnvilVkSpirvLastOpcode()
  ProcedureReturn spvLastOpcode
EndProcedure

Procedure.i avkSpvRefuse(op.i, text.i)
  spvLastOpcode = op
  ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, text)
EndProcedure

Procedure.i avkSpvMalformed(text.i)
  ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, text)
EndProcedure

Procedure.i avkSpvWord(*words, index.i)
  ProcedureReturn PeekL(*words + (index * 4)) & $FFFFFFFF
EndProcedure

Procedure avkSpvResetTables()
  Define i.i
  Define k.i
  i = 0
  While i <= #ANVIL_SPV_MAX_ID
    spvKind[i] = #ANVIL_SPV_K_NONE
    spvTypeClass[i] = #ANVIL_SPV_T_NONE
    spvTypeComp[i] = 0
    spvTypeCount[i] = 0
    spvTypeStorage[i] = -1
    spvValueType[i] = 0
    spvValueSrc[i] = #ANVIL_SPV_V_NONE
    spvValueA[i] = 0
    spvValueB[i] = 0
    spvConstWord[i] = 0
    spvDecLocation[i] = -1
    spvDecBuiltIn[i] = -1
    spvDecBlock[i] = 0
    k = 0
    While k < 4
      spvComposite[(i * 4) + k] = 0
      k = k + 1
    Wend
    k = 0
    While k < #ANVIL_SPV_MAX_MEMBERS
      spvMemberBuiltIn[(i * #ANVIL_SPV_MAX_MEMBERS) + k] = -1
      spvStructMember[(i * #ANVIL_SPV_MAX_MEMBERS) + k] = 0
      k = k + 1
    Wend
    i = i + 1
  Wend
  spvBound = 0
  spvVersion = 0
  spvGenerator = 0
  spvStage = -1
  spvEntry = 0
  spvInstructions = 0
  spvPushVar = 0
  spvPosVar = 0
  spvPosMember = -1
  spvPosValue = 0
  spvOriginUpperLeft = 0
  spvPlanAttrCount = 0
  spvPlanVaryCount = 0
  spvPlanPosAttr = -1
  spvPlanColourSrc = -1
  spvPlanColourIdx = -1
  k = 0
  While k < #ANVIL_SPV_MAX_ATTRS
    spvPlanAttrLoc[k] = -1
    spvPlanAttrComp[k] = 0
    spvPlanAttrVar[k] = 0
    k = k + 1
  Wend
  k = 0
  While k < #ANVIL_SPV_MAX_VARYINGS
    spvPlanVaryLoc[k] = -1
    spvPlanVaryComp[k] = 0
    spvPlanVarySrc[k] = -1
    k = k + 1
  Wend
  k = 0
  While k < 4
    spvPlanConst[k] = 0
    k = k + 1
  Wend
EndProcedure

; A result id must be inside the module's own bound AND inside this
; front end's tables. The two limits are different questions and both
; are refused separately, because "your module declares more ids than
; Anvil can hold" and "your module used an id it never declared" send a
; reader to different places.
Procedure.i avkSpvIdOk(id.i)
  If id < 1 Or id >= spvBound : ProcedureReturn 0 : EndIf
  If id > #ANVIL_SPV_MAX_ID : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

; How many components a type has: 1 for a scalar, n for a vector.
Procedure.i avkSpvComponents(typeId.i)
  If avkSpvIdOk(typeId) = 0 : ProcedureReturn 0 : EndIf
  If spvTypeClass[typeId] = #ANVIL_SPV_T_FLOAT : ProcedureReturn 1 : EndIf
  If spvTypeClass[typeId] = #ANVIL_SPV_T_INT : ProcedureReturn 1 : EndIf
  If spvTypeClass[typeId] = #ANVIL_SPV_T_VECTOR : ProcedureReturn spvTypeCount[typeId] : EndIf
  ProcedureReturn 0
EndProcedure

; 1 when the type is a 32-bit float or a vector of them. Written flat
; rather than recursively because a vector of vectors is not a SPIR-V
; type: one step down from a vector is always the scalar.
Procedure.i avkSpvIsFloatish(typeId.i)
  Define t.i
  If avkSpvIdOk(typeId) = 0 : ProcedureReturn 0 : EndIf
  t = typeId
  If spvTypeClass[t] = #ANVIL_SPV_T_VECTOR
    t = spvTypeComp[t]
    If avkSpvIdOk(t) = 0 : ProcedureReturn 0 : EndIf
  EndIf
  If spvTypeClass[t] <> #ANVIL_SPV_T_FLOAT : ProcedureReturn 0 : EndIf
  If spvTypeCount[t] <> 32 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  THE REFUSALS THAT HAVE NAMES.
;
;  Every one of these is a real thing a shader author writes and expects
;  to work, so each says what is missing rather than "unsupported". The
;  ones without a sentence of their own fall through to the last case,
;  which names the numeric opcode through AnvilVkSpirvLastOpcode().
; ----------------------------------------------------------------------
Procedure.i avkSpvRefuseOpcode(op.i)
  If op = #SpvOpExtInst
    ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused the opcode OpExtInst (Anvil code -20005, unsupported instruction); no extended instruction set is executed, so GLSL.std.450 calls such as mix, clamp, pow and normalize cannot be lowered. Write the shader without extended instructions, or wait for the arithmetic lowering this slice does not have.")
  EndIf
  If op = #SpvOpTypeMatrix Or op = #SpvOpMatrixTimesVector Or op = #SpvOpMatrixTimesMatrix
    ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused a matrix opcode - OpTypeMatrix, OpMatrixTimesVector or OpMatrixTimesMatrix (Anvil code -20005, unsupported instruction); there is no matrix type and no transform in this slice, so a model-view-projection multiply cannot be lowered. Pass positions already in clip space until a vertex arithmetic lowering exists.")
  EndIf
  If op = #SpvOpTypeImage Or op = #SpvOpTypeSampler Or op = #SpvOpTypeSampledImage Or op = #SpvOpImageSampleImplicitLod
    ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused an image or sampler opcode - OpTypeImage, OpTypeSampler, OpTypeSampledImage or OpImageSampleImplicitLod (Anvil code -20005, unsupported instruction); there is no VkImageView, no VkSampler and no descriptor set in this implementation, so nothing can be sampled. Use a per-vertex colour or the push-constant colour instead.")
  EndIf
  If op = #SpvOpFAdd Or op = #SpvOpFSub Or op = #SpvOpFMul Or op = #SpvOpFDiv Or op = #SpvOpFNegate Or op = #SpvOpVectorTimesScalar Or op = #SpvOpDot
    ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused a floating-point arithmetic opcode - OpFAdd, OpFSub, OpFMul, OpFDiv, OpFNegate, OpVectorTimesScalar or OpDot (Anvil code -20005, unsupported instruction); this slice lowers a shader that only moves values, so a shader that computes one cannot be emitted. The QPU arithmetic lowering is the next piece of work and it is not written yet.")
  EndIf
  If op = #SpvOpIAdd Or op = #SpvOpISub Or op = #SpvOpIMul Or op = #SpvOpConvertFToU Or op = #SpvOpConvertFToS Or op = #SpvOpConvertSToF Or op = #SpvOpConvertUToF
    ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused an integer arithmetic or conversion opcode - OpIAdd, OpISub, OpIMul, OpConvertFToU, OpConvertFToS, OpConvertSToF or OpConvertUToF (Anvil code -20005, unsupported instruction); the only integers this slice understands are the literal indices of an access chain and a composite extract.")
  EndIf
  If op = #SpvOpBranch Or op = #SpvOpBranchConditional Or op = #SpvOpSelectionMerge Or op = #SpvOpLoopMerge Or op = #SpvOpKill Or op = #SpvOpUnreachable
    ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused a control-flow opcode - OpBranch, OpBranchConditional, OpSelectionMerge, OpLoopMerge, OpKill or OpUnreachable (Anvil code -20005, unsupported instruction); an accepted shader is one basic block ending in OpReturn, because there is no block ordering, no phi and no discard in this slice.")
  EndIf
  If op = #SpvOpFunctionCall Or op = #SpvOpFunctionParameter
    ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused OpFunctionCall or OpFunctionParameter (Anvil code -20005, unsupported instruction); an accepted module holds exactly one function, the entry point, and it takes no parameters. Inline every helper before compiling to SPIR-V.")
  EndIf
  If op = #SpvOpVectorShuffle
    ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused the opcode OpVectorShuffle (Anvil code -20005, unsupported instruction); components may be taken apart with OpCompositeExtract and put back together with OpCompositeConstruct, but a shuffle is not lowered. A swizzle in the source language usually becomes one of these two instead.")
  EndIf
  If op = #SpvOpTypeArray Or op = #SpvOpTypeRuntimeArray
    ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused OpTypeArray or OpTypeRuntimeArray (Anvil code -20005, unsupported instruction); there are no arrays in this slice, so gl_ClipDistance, an array of varyings and a storage-buffer array all fall outside it.")
  EndIf
  If op = #SpvOpTypeBool Or op = #SpvOpConstantTrue Or op = #SpvOpConstantFalse
    ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused a boolean opcode - OpTypeBool, OpConstantTrue or OpConstantFalse (Anvil code -20005, unsupported instruction); there are no conditions in an accepted shader, so a boolean has nothing to be used for.")
  EndIf
  If op = #SpvOpUndef Or op = #SpvOpConstantNull
    ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused OpUndef or OpConstantNull (Anvil code -20005, unsupported instruction); a value with no defined bits cannot be lowered into a shader whose whole contract is that the bytes it writes are the bytes the caller asked for.")
  EndIf
  If op = #SpvOpExtension
    ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused the opcode OpExtension (Anvil code -20005, unsupported instruction); no SPIR-V extension is implemented, so a module that declares one is asking for behaviour that is not here. Compile the shader against core SPIR-V for Vulkan 1.0.")
  EndIf
  ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused an opcode it does not implement (Anvil code -20005, unsupported instruction); AnvilVkSpirvLastOpcode() returns its numeric value, which the SPIR-V specification's instruction table names. The accepted subset is a pass-through vertex shader and a flat or interpolated fragment shader, and nothing else is lowered.")
EndProcedure

; ----------------------------------------------------------------------
;  THE HEADER.
; ----------------------------------------------------------------------
Procedure.i avkSpvHeader(*words, wordCount.i)
  Define magic.i
  If wordCount < #ANVIL_SPV_HEADER_WORDS
    ProcedureReturn avkSpvMalformed("vkCreateShaderModule was given fewer than the five header words a SPIR-V module begins with (Anvil code -20001, truncated module); VkShaderModuleCreateInfo.codeSize must be at least twenty bytes and a multiple of four.")
  EndIf
  magic = avkSpvWord(*words, 0)
  If magic = #ANVIL_SPV_MAGIC_SWAPPED
    ProcedureReturn avkSpvMalformed("vkCreateShaderModule was given a SPIR-V module whose words are byte swapped (Anvil code -20001, wrong endianness); the magic number read back as $03022307 instead of $07230203. Anvil reads little-endian words only, so byte-swap the module on the host that produced it.")
  EndIf
  If magic <> #ANVIL_SPV_MAGIC
    ProcedureReturn avkSpvMalformed("vkCreateShaderModule was given code whose first word is not the SPIR-V magic number $07230203 (Anvil code -20001, not a SPIR-V module); check that pCode points at the compiled module and not at the GLSL source, an ELF object or a padded header.")
  EndIf
  spvVersion = avkSpvWord(*words, 1)
  If spvVersion > #ANVIL_SPV_VERSION_MAX
    ProcedureReturn avkSpvMalformed("vkCreateShaderModule was given a SPIR-V module newer than version 1.6 (Anvil code -20001, unsupported SPIR-V version); Vulkan 1.0 shaders are SPIR-V 1.0, and this front end reads up to 1.6. Recompile with an older target version.")
  EndIf
  spvGenerator = avkSpvWord(*words, 2)
  spvBound = avkSpvWord(*words, 3)
  If spvBound < 1
    ProcedureReturn avkSpvMalformed("vkCreateShaderModule was given a SPIR-V module whose id bound is zero (Anvil code -20001, malformed header); the fourth header word must be one more than the largest result id the module uses.")
  EndIf
  If spvBound > (#ANVIL_SPV_MAX_ID + 1)
    ProcedureReturn avkSpvMalformed("vkCreateShaderModule was given a SPIR-V module with more result ids than Anvil's front end can hold (Anvil code -20001, module too large); the id bound must be at most 193. This is a limit of the implementation and not of SPIR-V, so a smaller shader is the answer today.")
  EndIf
  If avkSpvWord(*words, 4) <> 0
    ProcedureReturn avkSpvMalformed("vkCreateShaderModule was given a SPIR-V module that declares an instruction schema (Anvil code -20001, unsupported schema); the fifth header word must be zero, which is the only schema the SPIR-V specification defines.")
  EndIf
  ProcedureReturn #ANVIL_VK_OK
EndProcedure

; ----------------------------------------------------------------------
;  ONE INSTRUCTION. Returns #ANVIL_VK_OK, or a refusal code.
;
;  `at` is the word index of the instruction's first word and `count` its
;  word count, both already validated by the caller.
; ----------------------------------------------------------------------
Procedure.i avkSpvDecl(*words, at.i, count.i, op.i)
  Define id.i
  Define a.i
  Define b.i
  Define k.i
  Define n.i
  Define base.i

  Select op
    ; --- modes, and the debug instructions that carry no meaning here ---
    Case #SpvOpNop
      ProcedureReturn #ANVIL_VK_OK
    Case #SpvOpSource
      ProcedureReturn #ANVIL_VK_OK
    Case #SpvOpSourceContinued
      ProcedureReturn #ANVIL_VK_OK
    Case #SpvOpSourceExtension
      ProcedureReturn #ANVIL_VK_OK
    Case #SpvOpName
      ProcedureReturn #ANVIL_VK_OK
    Case #SpvOpMemberName
      ProcedureReturn #ANVIL_VK_OK
    Case #SpvOpString
      ProcedureReturn #ANVIL_VK_OK
    Case #SpvOpLine
      ProcedureReturn #ANVIL_VK_OK
    Case #SpvOpNoLine
      ProcedureReturn #ANVIL_VK_OK
    Case #SpvOpDecorationGroup
      ProcedureReturn #ANVIL_VK_OK

    Case #SpvOpCapability
      a = avkSpvWord(*words, at + 1)
      If a = #SpvCapabilityShader : ProcedureReturn #ANVIL_VK_OK : EndIf
      If a = #SpvCapabilityMatrix : ProcedureReturn #ANVIL_VK_OK : EndIf
      If a = #SpvCapabilityGeometry Or a = #SpvCapabilityTessellation
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused the capability Geometry or Tessellation declared by OpCapability (Anvil code -20005, unsupported capability); the only pipeline stages this implementation runs are vertex and fragment, so a module that declares another stage's capability cannot be executed.")
      EndIf
      If a = #SpvCapabilityFloat64 Or a = #SpvCapabilityInt64 Or a = #SpvCapabilityFloat16 Or a = #SpvCapabilityInt16 Or a = #SpvCapabilityInt8
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused a width capability declared by OpCapability - Float64, Int64, Float16, Int16 or Int8 (Anvil code -20005, unsupported capability); the only scalar widths this slice lowers are 32-bit float and 32-bit integer, because those are the widths the QPU emitter writes.")
      EndIf
      ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused a capability it does not implement, declared by OpCapability (Anvil code -20005, unsupported capability); only Shader and Matrix are accepted. A module must not declare a capability whose instructions this implementation would then have to execute.")

    Case #SpvOpExtInstImport
      id = avkSpvWord(*words, at + 1)
      If avkSpvIdOk(id) = 0
        ProcedureReturn avkSpvMalformed("a SPIR-V OpExtInstImport declared a result id outside the module's own bound (Anvil code -20001, malformed module); every result id must be at least one and less than the bound in the header.")
      EndIf
      spvKind[id] = #ANVIL_SPV_K_EXTSET
      ProcedureReturn #ANVIL_VK_OK

    Case #SpvOpMemoryModel
      If avkSpvWord(*words, at + 1) <> #SpvAddressingModelLogical
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused the addressing model named by OpMemoryModel (Anvil code -20005, unsupported addressing model); Vulkan shaders use Logical addressing, and a physical address space would mean pointers into memory this implementation does not map for a shader.")
      EndIf
      If avkSpvWord(*words, at + 2) <> #SpvMemoryModelGLSL450
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused the memory model named by OpMemoryModel (Anvil code -20005, unsupported memory model); this implementation accepts GLSL450, which is what a Vulkan 1.0 shader declares. The Vulkan memory model needs the availability and visibility operations that are not implemented here.")
      EndIf
      ProcedureReturn #ANVIL_VK_OK

    Case #SpvOpEntryPoint
      If spvEntry <> 0
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused a module with more than one OpEntryPoint (Anvil code -20005, unsupported module shape); one shader module holds one entry point here, so that vkCreateGraphicsPipelines needs no name lookup to know which function to lower.")
      EndIf
      a = avkSpvWord(*words, at + 1)
      If a = #SpvExecutionModelVertex Or a = #SpvExecutionModelFragment
        spvStage = a
      ElseIf a = #SpvExecutionModelGLCompute Or a = #SpvExecutionModelKernel
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused a compute entry point named by OpEntryPoint (Anvil code -20005, unsupported execution model); there is no VkComputePipeline and no compute queue in this implementation, so a GLCompute or Kernel module has nothing to run on.")
      Else
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused the execution model named by OpEntryPoint (Anvil code -20005, unsupported execution model); only Vertex and Fragment are implemented, because those are the two QPU program kinds the V3D shader record carries.")
      EndIf
      spvEntry = avkSpvWord(*words, at + 2)
      ProcedureReturn #ANVIL_VK_OK

    Case #SpvOpExecutionMode
      a = avkSpvWord(*words, at + 2)
      If a = #SpvExecutionModeOriginUpperLeft
        spvOriginUpperLeft = 1
        ProcedureReturn #ANVIL_VK_OK
      EndIf
      If a = #SpvExecutionModeOriginLowerLeft
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused the execution mode OriginLowerLeft (Anvil code -20005, unsupported execution mode); Vulkan fragment shaders declare OriginUpperLeft, and the V3D rasteriser this backend drives has its origin at the top left of the render target.")
      EndIf
      If a = #SpvExecutionModeDepthReplacing
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused the execution mode DepthReplacing (Anvil code -20005, unsupported execution mode); there is no depth buffer in this pipeline, so a shader that writes gl_FragDepth has nothing to write into.")
      EndIf
      If a = #SpvExecutionModeLocalSize
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused the execution mode LocalSize (Anvil code -20005, unsupported execution mode); a local size belongs to a compute shader and this implementation has no compute pipeline.")
      EndIf
      ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused an execution mode it does not implement (Anvil code -20005, unsupported execution mode); the only mode accepted here is OriginUpperLeft on a fragment entry point.")

    ; --- types ---
    Case #SpvOpTypeVoid
      id = avkSpvWord(*words, at + 1)
      If avkSpvIdOk(id) = 0
        ProcedureReturn avkSpvMalformed("a SPIR-V type declaration used a result id outside the module's own bound (Anvil code -20001, malformed module); every result id must be at least one and less than the bound in the header.")
      EndIf
      spvKind[id] = #ANVIL_SPV_K_TYPE
      spvTypeClass[id] = #ANVIL_SPV_T_VOID
      ProcedureReturn #ANVIL_VK_OK

    Case #SpvOpTypeInt
      id = avkSpvWord(*words, at + 1)
      If avkSpvIdOk(id) = 0
        ProcedureReturn avkSpvMalformed("a SPIR-V OpTypeInt used a result id outside the module's own bound (Anvil code -20001, malformed module); every result id must be at least one and less than the bound in the header.")
      EndIf
      If avkSpvWord(*words, at + 2) <> 32
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused an OpTypeInt of a width other than 32 bits (Anvil code -20005, unsupported scalar width); the only integer this slice understands is a 32-bit literal index, and a module that declares another width has declared a capability that was already refused.")
      EndIf
      spvKind[id] = #ANVIL_SPV_K_TYPE
      spvTypeClass[id] = #ANVIL_SPV_T_INT
      spvTypeCount[id] = 32
      ProcedureReturn #ANVIL_VK_OK

    Case #SpvOpTypeFloat
      id = avkSpvWord(*words, at + 1)
      If avkSpvIdOk(id) = 0
        ProcedureReturn avkSpvMalformed("a SPIR-V OpTypeFloat used a result id outside the module's own bound (Anvil code -20001, malformed module); every result id must be at least one and less than the bound in the header.")
      EndIf
      If avkSpvWord(*words, at + 2) <> 32
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused an OpTypeFloat of a width other than 32 bits (Anvil code -20005, unsupported scalar width); every value the QPU emitter moves is a binary32, so a half or a double has no register to live in.")
      EndIf
      spvKind[id] = #ANVIL_SPV_K_TYPE
      spvTypeClass[id] = #ANVIL_SPV_T_FLOAT
      spvTypeCount[id] = 32
      ProcedureReturn #ANVIL_VK_OK

    Case #SpvOpTypeVector
      id = avkSpvWord(*words, at + 1)
      a = avkSpvWord(*words, at + 2)
      n = avkSpvWord(*words, at + 3)
      If avkSpvIdOk(id) = 0 Or avkSpvIdOk(a) = 0
        ProcedureReturn avkSpvMalformed("a SPIR-V OpTypeVector named a result id or a component type outside the module's own bound (Anvil code -20001, malformed module); every id an instruction names must be declared earlier in the module.")
      EndIf
      If n < 2 Or n > 4
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused an OpTypeVector of a length other than two, three or four (Anvil code -20005, unsupported vector length); the vertex fetcher reads at most four components per attribute and the tile buffer takes four, so a longer vector has nowhere to go.")
      EndIf
      spvKind[id] = #ANVIL_SPV_K_TYPE
      spvTypeClass[id] = #ANVIL_SPV_T_VECTOR
      spvTypeComp[id] = a
      spvTypeCount[id] = n
      ProcedureReturn #ANVIL_VK_OK

    Case #SpvOpTypeStruct
      id = avkSpvWord(*words, at + 1)
      If avkSpvIdOk(id) = 0
        ProcedureReturn avkSpvMalformed("a SPIR-V OpTypeStruct used a result id outside the module's own bound (Anvil code -20001, malformed module); every result id must be at least one and less than the bound in the header.")
      EndIf
      n = count - 2
      If n < 1 Or n > #ANVIL_SPV_MAX_MEMBERS
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused an OpTypeStruct with no members or with more than four (Anvil code -20005, unsupported structure); the two structures this slice knows are the gl_PerVertex block and a push-constant block, and neither needs more than four members.")
      EndIf
      spvKind[id] = #ANVIL_SPV_K_TYPE
      spvTypeClass[id] = #ANVIL_SPV_T_STRUCT
      spvTypeCount[id] = n
      k = 0
      While k < n
        spvStructMember[(id * #ANVIL_SPV_MAX_MEMBERS) + k] = avkSpvWord(*words, at + 2 + k)
        k = k + 1
      Wend
      ProcedureReturn #ANVIL_VK_OK

    Case #SpvOpTypePointer
      id = avkSpvWord(*words, at + 1)
      a = avkSpvWord(*words, at + 2)
      b = avkSpvWord(*words, at + 3)
      If avkSpvIdOk(id) = 0 Or avkSpvIdOk(b) = 0
        ProcedureReturn avkSpvMalformed("a SPIR-V OpTypePointer named a result id or a pointee type outside the module's own bound (Anvil code -20001, malformed module); every id an instruction names must be declared earlier in the module.")
      EndIf
      spvKind[id] = #ANVIL_SPV_K_TYPE
      spvTypeClass[id] = #ANVIL_SPV_T_POINTER
      spvTypeStorage[id] = a
      spvTypeComp[id] = b
      ProcedureReturn #ANVIL_VK_OK

    Case #SpvOpTypeFunction
      id = avkSpvWord(*words, at + 1)
      If avkSpvIdOk(id) = 0
        ProcedureReturn avkSpvMalformed("a SPIR-V OpTypeFunction used a result id outside the module's own bound (Anvil code -20001, malformed module); every result id must be at least one and less than the bound in the header.")
      EndIf
      If count <> 3
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused an OpTypeFunction that takes parameters (Anvil code -20005, unsupported function type); the one function an accepted module holds is the entry point, and an entry point takes none.")
      EndIf
      spvKind[id] = #ANVIL_SPV_K_TYPE
      spvTypeClass[id] = #ANVIL_SPV_T_FUNCTION
      spvTypeComp[id] = avkSpvWord(*words, at + 2)
      ProcedureReturn #ANVIL_VK_OK

    ; --- constants ---
    Case #SpvOpConstant
      a = avkSpvWord(*words, at + 1)
      id = avkSpvWord(*words, at + 2)
      If avkSpvIdOk(id) = 0 Or avkSpvIdOk(a) = 0
        ProcedureReturn avkSpvMalformed("a SPIR-V OpConstant named a result id or a result type outside the module's own bound (Anvil code -20001, malformed module); every id an instruction names must be declared earlier in the module.")
      EndIf
      If count <> 4
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused an OpConstant carrying more than one literal word (Anvil code -20005, unsupported constant width); a wider constant belongs to a 64-bit type, and those are refused where they are declared.")
      EndIf
      spvKind[id] = #ANVIL_SPV_K_CONST
      spvValueType[id] = a
      spvValueSrc[id] = #ANVIL_SPV_V_CONST
      spvConstWord[id] = avkSpvWord(*words, at + 3)
      ProcedureReturn #ANVIL_VK_OK

    Case #SpvOpConstantComposite
      a = avkSpvWord(*words, at + 1)
      id = avkSpvWord(*words, at + 2)
      If avkSpvIdOk(id) = 0 Or avkSpvIdOk(a) = 0
        ProcedureReturn avkSpvMalformed("a SPIR-V OpConstantComposite named a result id or a result type outside the module's own bound (Anvil code -20001, malformed module); every id an instruction names must be declared earlier in the module.")
      EndIf
      n = count - 3
      If n < 1 Or n > 4
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused an OpConstantComposite of more than four components (Anvil code -20005, unsupported constant); the widest value this slice carries is a four-component vector.")
      EndIf
      spvKind[id] = #ANVIL_SPV_K_CONST
      spvValueType[id] = a
      spvValueSrc[id] = #ANVIL_SPV_V_CONST
      k = 0
      While k < n
        b = avkSpvWord(*words, at + 3 + k)
        If avkSpvIdOk(b) = 0 Or spvKind[b] <> #ANVIL_SPV_K_CONST
          ProcedureReturn avkSpvMalformed("a SPIR-V OpConstantComposite named a component that is not a constant declared earlier in the module (Anvil code -20001, malformed module); the operands of a constant composite must themselves be constant instructions.")
        EndIf
        spvComposite[(id * 4) + k] = spvConstWord[b]
        k = k + 1
      Wend
      ProcedureReturn #ANVIL_VK_OK

    ; --- decorations ---
    Case #SpvOpDecorate
      id = avkSpvWord(*words, at + 1)
      a = avkSpvWord(*words, at + 2)
      If avkSpvIdOk(id) = 0
        ProcedureReturn avkSpvMalformed("a SPIR-V OpDecorate named a target id outside the module's own bound (Anvil code -20001, malformed module); a decoration must name an id the module declares.")
      EndIf
      If a = #SpvDecorationLocation
        spvDecLocation[id] = avkSpvWord(*words, at + 3)
        ProcedureReturn #ANVIL_VK_OK
      EndIf
      If a = #SpvDecorationBuiltIn
        spvDecBuiltIn[id] = avkSpvWord(*words, at + 3)
        ProcedureReturn #ANVIL_VK_OK
      EndIf
      If a = #SpvDecorationBlock
        spvDecBlock[id] = 1
        ProcedureReturn #ANVIL_VK_OK
      EndIf
      ; Decorations that change nothing this implementation does.
      If a = #SpvDecorationRelaxedPrecision Or a = #SpvDecorationOffset Or a = #SpvDecorationColMajor Or a = #SpvDecorationMatrixStride Or a = #SpvDecorationArrayStride
        ProcedureReturn #ANVIL_VK_OK
      EndIf
      If a = #SpvDecorationDescriptorSet Or a = #SpvDecorationBinding
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused the decoration DescriptorSet or Binding on OpDecorate (Anvil code -20005, unsupported decoration); there is no VkDescriptorSetLayout, no VkDescriptorPool and no vkCmdBindDescriptorSets in this implementation, so a bound resource could never be supplied. Use the push-constant block for a uniform colour.")
      EndIf
      If a = #SpvDecorationFlat Or a = #SpvDecorationNoPerspective
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused the interpolation decoration Flat or NoPerspective (Anvil code -20005, unsupported decoration); every varying this slice emits is interpolated the one way the emitted V3D shader record declares, so a module that asks for another would get a picture that did not match what it asked for.")
      EndIf
      If a = #SpvDecorationBufferBlock
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused the decoration BufferBlock (Anvil code -20005, unsupported decoration); there are no storage buffers in this implementation.")
      EndIf
      If a = #SpvDecorationComponent
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused the decoration Component (Anvil code -20005, unsupported decoration); a location is not subdivided here, so two variables cannot share one location.")
      EndIf
      ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused a decoration it does not implement, on OpDecorate (Anvil code -20005, unsupported decoration); the decorations this slice reads are Location, BuiltIn and Block, and it ignores RelaxedPrecision and Offset.")

    Case #SpvOpMemberDecorate
      id = avkSpvWord(*words, at + 1)
      k = avkSpvWord(*words, at + 2)
      a = avkSpvWord(*words, at + 3)
      If avkSpvIdOk(id) = 0
        ProcedureReturn avkSpvMalformed("a SPIR-V OpMemberDecorate named a structure id outside the module's own bound (Anvil code -20001, malformed module); a member decoration must name a structure the module declares.")
      EndIf
      If k < 0 Or k >= #ANVIL_SPV_MAX_MEMBERS
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused an OpMemberDecorate on a member past the fourth (Anvil code -20005, unsupported structure); a structure this slice reads has at most four members.")
      EndIf
      If a = #SpvDecorationBuiltIn
        spvMemberBuiltIn[(id * #ANVIL_SPV_MAX_MEMBERS) + k] = avkSpvWord(*words, at + 4)
        ProcedureReturn #ANVIL_VK_OK
      EndIf
      If a = #SpvDecorationOffset Or a = #SpvDecorationRelaxedPrecision Or a = #SpvDecorationColMajor Or a = #SpvDecorationMatrixStride
        ProcedureReturn #ANVIL_VK_OK
      EndIf
      ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused a member decoration it does not implement, on OpMemberDecorate (Anvil code -20005, unsupported decoration); the member decorations this slice reads are BuiltIn and Offset.")

    ; --- variables ---
    Case #SpvOpVariable
      a = avkSpvWord(*words, at + 1)
      id = avkSpvWord(*words, at + 2)
      b = avkSpvWord(*words, at + 3)
      If avkSpvIdOk(id) = 0 Or avkSpvIdOk(a) = 0
        ProcedureReturn avkSpvMalformed("a SPIR-V OpVariable named a result id or a result type outside the module's own bound (Anvil code -20001, malformed module); every id an instruction names must be declared earlier in the module.")
      EndIf
      If spvTypeClass[a] <> #ANVIL_SPV_T_POINTER
        ProcedureReturn avkSpvMalformed("a SPIR-V OpVariable has a result type that is not a pointer (Anvil code -20001, malformed module); the specification requires the result type of OpVariable to be OpTypePointer.")
      EndIf
      If count > 4
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused an OpVariable with an initialiser (Anvil code -20005, unsupported variable); an accepted shader writes its outputs with OpStore, so a variable that arrives already holding a value has a second way to be set and only one of them would be lowered.")
      EndIf
      If b = #SpvStorageClassFunction Or b = #SpvStorageClassPrivate Or b = #SpvStorageClassWorkgroup
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused an OpVariable in the Function, Private or Workgroup storage class (Anvil code -20005, unsupported storage class); there is no scratch memory for a shader in this slice, so a local variable has nowhere to live. An accepted shader moves values between its inputs and its outputs directly.")
      EndIf
      If b = #SpvStorageClassUniform Or b = #SpvStorageClassStorageBuffer Or b = #SpvStorageClassUniformConstant
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused an OpVariable in the Uniform, StorageBuffer or UniformConstant storage class (Anvil code -20005, unsupported storage class); reaching one needs a descriptor set, and there is no descriptor machinery in this implementation. The push-constant block is the one uniform path that exists.")
      EndIf
      If b <> #SpvStorageClassInput And b <> #SpvStorageClassOutput And b <> #SpvStorageClassPushConstant
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused an OpVariable in a storage class it does not implement (Anvil code -20005, unsupported storage class); the three accepted classes are Input, Output and PushConstant.")
      EndIf
      spvKind[id] = #ANVIL_SPV_K_VARIABLE
      spvValueType[id] = spvTypeComp[a]
      spvTypeStorage[id] = b
      If b = #SpvStorageClassPushConstant
        If spvPushVar <> 0
          ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused a second push-constant variable (Anvil code -20005, unsupported module shape); Vulkan permits one push-constant block per stage, and this slice carries exactly that one.")
        EndIf
        spvPushVar = id
      EndIf
      ProcedureReturn #ANVIL_VK_OK

    ; --- the function body ---
    Case #SpvOpFunction
      id = avkSpvWord(*words, at + 2)
      If id <> spvEntry
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused an OpFunction that is not the entry point (Anvil code -20005, unsupported module shape); an accepted module holds exactly one function. Inline every helper before compiling to SPIR-V.")
      EndIf
      If avkSpvIdOk(id) = 0
        ProcedureReturn avkSpvMalformed("a SPIR-V OpFunction used a result id outside the module's own bound (Anvil code -20001, malformed module); every result id must be at least one and less than the bound in the header.")
      EndIf
      spvKind[id] = #ANVIL_SPV_K_FUNCTION
      ProcedureReturn #ANVIL_VK_OK

    Case #SpvOpLabel
      id = avkSpvWord(*words, at + 1)
      If avkSpvIdOk(id) = 0
        ProcedureReturn avkSpvMalformed("a SPIR-V OpLabel used a result id outside the module's own bound (Anvil code -20001, malformed module); every result id must be at least one and less than the bound in the header.")
      EndIf
      If spvKind[id] = #ANVIL_SPV_K_LABEL
        ProcedureReturn avkSpvMalformed("a SPIR-V module declared the same label id twice (Anvil code -20001, malformed module); every result id is defined exactly once.")
      EndIf
      spvKind[id] = #ANVIL_SPV_K_LABEL
      ProcedureReturn #ANVIL_VK_OK

    Case #SpvOpLoad
      a = avkSpvWord(*words, at + 1)
      id = avkSpvWord(*words, at + 2)
      b = avkSpvWord(*words, at + 3)
      If avkSpvIdOk(id) = 0 Or avkSpvIdOk(b) = 0
        ProcedureReturn avkSpvMalformed("a SPIR-V OpLoad named a result id or a pointer outside the module's own bound (Anvil code -20001, malformed module); every id an instruction names must be declared earlier in the module.")
      EndIf
      spvKind[id] = #ANVIL_SPV_K_VALUE
      spvValueType[id] = a
      If spvKind[b] = #ANVIL_SPV_K_VARIABLE
        If spvTypeStorage[b] = #SpvStorageClassInput
          spvValueSrc[id] = #ANVIL_SPV_V_INPUT
          spvValueA[id] = b
          ProcedureReturn #ANVIL_VK_OK
        EndIf
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused an OpLoad of a variable that is not an Input (Anvil code -20005, unsupported load); a shader may read its inputs and the push-constant block, and it may not read back an output it has written.")
      EndIf
      If spvValueSrc[b] = #ANVIL_SPV_V_CHAIN
        If spvValueA[b] = spvPushVar And spvPushVar <> 0
          spvValueSrc[id] = #ANVIL_SPV_V_PUSH
          spvValueA[id] = spvValueB[b]
          ProcedureReturn #ANVIL_VK_OK
        EndIf
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused an OpLoad through an access chain into something other than the push-constant block (Anvil code -20005, unsupported load); the only member this slice reads through a chain is a member of the push-constant block.")
      EndIf
      ProcedureReturn avkSpvMalformed("a SPIR-V OpLoad named a pointer that is neither a variable nor an access chain declared earlier in the module (Anvil code -20001, malformed module); the pointer operand of OpLoad must be a pointer-valued id the module defines.")

    Case #SpvOpAccessChain
      a = avkSpvWord(*words, at + 1)
      id = avkSpvWord(*words, at + 2)
      b = avkSpvWord(*words, at + 3)
      If avkSpvIdOk(id) = 0 Or avkSpvIdOk(b) = 0
        ProcedureReturn avkSpvMalformed("a SPIR-V OpAccessChain named a result id or a base outside the module's own bound (Anvil code -20001, malformed module); every id an instruction names must be declared earlier in the module.")
      EndIf
      If count <> 5
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused an OpAccessChain with anything other than exactly one index (Anvil code -20005, unsupported access chain); the only chains this slice follows select one member of a block, so a nested or an array index has no meaning here.")
      EndIf
      k = avkSpvWord(*words, at + 4)
      If avkSpvIdOk(k) = 0 Or spvKind[k] <> #ANVIL_SPV_K_CONST
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused an OpAccessChain whose index is not a constant (Anvil code -20005, unsupported access chain); a dynamically indexed member would need addressing this slice does not emit.")
      EndIf
      If spvKind[b] <> #ANVIL_SPV_K_VARIABLE
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused an OpAccessChain whose base is not a variable (Anvil code -20005, unsupported access chain); a chain into the result of another chain is not followed.")
      EndIf
      spvKind[id] = #ANVIL_SPV_K_VALUE
      spvValueType[id] = a
      spvValueSrc[id] = #ANVIL_SPV_V_CHAIN
      spvValueA[id] = b
      spvValueB[id] = spvConstWord[k]
      ProcedureReturn #ANVIL_VK_OK

    Case #SpvOpCompositeExtract
      a = avkSpvWord(*words, at + 1)
      id = avkSpvWord(*words, at + 2)
      b = avkSpvWord(*words, at + 3)
      If avkSpvIdOk(id) = 0 Or avkSpvIdOk(b) = 0
        ProcedureReturn avkSpvMalformed("a SPIR-V OpCompositeExtract named a result id or a composite outside the module's own bound (Anvil code -20001, malformed module); every id an instruction names must be declared earlier in the module.")
      EndIf
      If count <> 5
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused an OpCompositeExtract with anything other than exactly one index (Anvil code -20005, unsupported extract); the composites this slice holds are vectors, so one index reaches every component there is.")
      EndIf
      spvKind[id] = #ANVIL_SPV_K_VALUE
      spvValueType[id] = a
      spvValueSrc[id] = #ANVIL_SPV_V_EXTRACT
      spvValueA[id] = b
      spvValueB[id] = avkSpvWord(*words, at + 4)
      ProcedureReturn #ANVIL_VK_OK

    Case #SpvOpCompositeConstruct
      a = avkSpvWord(*words, at + 1)
      id = avkSpvWord(*words, at + 2)
      If avkSpvIdOk(id) = 0 Or avkSpvIdOk(a) = 0
        ProcedureReturn avkSpvMalformed("a SPIR-V OpCompositeConstruct named a result id or a result type outside the module's own bound (Anvil code -20001, malformed module); every id an instruction names must be declared earlier in the module.")
      EndIf
      n = count - 3
      If n < 2 Or n > 4
        ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused an OpCompositeConstruct of fewer than two or more than four components (Anvil code -20005, unsupported composite); the widest value this slice builds is a four-component vector, and every operand must be one scalar.")
      EndIf
      spvKind[id] = #ANVIL_SPV_K_VALUE
      spvValueType[id] = a
      spvValueSrc[id] = #ANVIL_SPV_V_COMPOSITE
      base = id * 4
      k = 0
      While k < n
        b = avkSpvWord(*words, at + 3 + k)
        If avkSpvIdOk(b) = 0
          ProcedureReturn avkSpvMalformed("a SPIR-V OpCompositeConstruct named a component id outside the module's own bound (Anvil code -20001, malformed module); every id an instruction names must be declared earlier in the module.")
        EndIf
        spvComposite[base + k] = b
        k = k + 1
      Wend
      spvValueB[id] = n
      ProcedureReturn #ANVIL_VK_OK

    Case #SpvOpStore
      a = avkSpvWord(*words, at + 1)
      b = avkSpvWord(*words, at + 2)
      If avkSpvIdOk(a) = 0 Or avkSpvIdOk(b) = 0
        ProcedureReturn avkSpvMalformed("a SPIR-V OpStore named a pointer or an object outside the module's own bound (Anvil code -20001, malformed module); every id an instruction names must be declared earlier in the module.")
      EndIf
      ; A store into a Location-decorated Output is a varying or the
      ; colour; a store through a chain into a Position member, or into a
      ; Position-decorated variable, is the position. The distinction is
      ; made here and the plan is built from it after the walk.
      If spvKind[a] = #ANVIL_SPV_K_VARIABLE
        If spvTypeStorage[a] <> #SpvStorageClassOutput
          ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused an OpStore into a variable that is not an Output (Anvil code -20005, unsupported store); a shader may write its outputs and nothing else, and an Input and the push-constant block are both read only.")
        EndIf
        If spvDecBuiltIn[a] = #SpvBuiltInPosition
          spvPosVar = a
          spvPosMember = -1
          spvPosValue = b
          ProcedureReturn #ANVIL_VK_OK
        EndIf
        If spvDecBuiltIn[a] <> -1
          ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused an OpStore into a built-in output other than Position (Anvil code -20005, unsupported built-in); PointSize, ClipDistance, CullDistance and FragDepth are not implemented, so a shader that writes one is asking for behaviour this pipeline does not have.")
        EndIf
        If spvDecLocation[a] < 0
          ProcedureReturn avkSpvMalformed("a SPIR-V OpStore wrote an Output variable that carries neither a Location nor a BuiltIn decoration (Anvil code -20001, malformed module); a Vulkan shader interface variable must carry one or the other.")
        EndIf
        ; A Location output: remembered in the plan tables below.
        If spvPlanVaryCount >= #ANVIL_SPV_MAX_VARYINGS
          ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused a shader with more than four Location outputs (Anvil code -20005, too many outputs); four varyings is what the emitted V3D shader record and the VPM layout carry in this slice.")
        EndIf
        spvPlanVaryLoc[spvPlanVaryCount] = spvDecLocation[a]
        spvPlanVaryComp[spvPlanVaryCount] = avkSpvComponents(spvValueType[a])
        spvPlanVarySrc[spvPlanVaryCount] = b
        spvPlanVaryCount = spvPlanVaryCount + 1
        ProcedureReturn #ANVIL_VK_OK
      EndIf
      If spvValueSrc[a] = #ANVIL_SPV_V_CHAIN
        n = spvValueA[a]
        If avkSpvIdOk(n) = 0 Or spvTypeStorage[n] <> #SpvStorageClassOutput
          ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused an OpStore through an access chain into something that is not an Output block (Anvil code -20005, unsupported store); the one chained store this slice lowers is the write to gl_Position inside the gl_PerVertex block.")
        EndIf
        k = spvValueB[a]
        a = spvValueType[n]
        If avkSpvIdOk(a) = 0 Or spvTypeClass[a] <> #ANVIL_SPV_T_STRUCT
          ProcedureReturn avkSpvMalformed("a SPIR-V OpStore used an access chain whose base variable is not a structure (Anvil code -20001, malformed module); a member index only has meaning inside an OpTypeStruct.")
        EndIf
        If k < 0 Or k >= #ANVIL_SPV_MAX_MEMBERS
          ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused an OpStore into a block member past the fourth (Anvil code -20005, unsupported structure); a structure this slice reads has at most four members.")
        EndIf
        If spvMemberBuiltIn[(a * #ANVIL_SPV_MAX_MEMBERS) + k] <> #SpvBuiltInPosition
          ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused an OpStore into a gl_PerVertex member other than Position (Anvil code -20005, unsupported built-in); gl_PointSize, gl_ClipDistance and gl_CullDistance have no hardware behind them in this pipeline.")
        EndIf
        spvPosVar = n
        spvPosMember = k
        spvPosValue = b
        ProcedureReturn #ANVIL_VK_OK
      EndIf
      ProcedureReturn avkSpvMalformed("a SPIR-V OpStore named a pointer that is neither a variable nor an access chain declared earlier in the module (Anvil code -20001, malformed module); the pointer operand of OpStore must be a pointer-valued id the module defines.")

    Case #SpvOpReturn
      ProcedureReturn #ANVIL_VK_OK

    Case #SpvOpReturnValue
      ProcedureReturn avkSpvRefuse(op, "the SPIR-V front end refused the opcode OpReturnValue (Anvil code -20005, unsupported instruction); the entry point of a graphics shader returns void, so a value returned from it has no destination.")

    Case #SpvOpFunctionEnd
      ProcedureReturn #ANVIL_VK_OK

    Default
      ProcedureReturn avkSpvRefuseOpcode(op)
  EndSelect
EndProcedure

; ----------------------------------------------------------------------
;  Register an Input variable as an attribute (vertex) or an incoming
;  varying (fragment). The table is kept in Location order and a repeat
;  is a malformed module, not a silent overwrite.
; ----------------------------------------------------------------------
Procedure.i avkSpvAddInput(id.i)
  Define n.i
  Define comps.i
  n = spvPlanAttrCount
  If n >= #ANVIL_SPV_MAX_ATTRS
    ProcedureReturn avkSpvRefuse(#SpvOpVariable, "the SPIR-V front end refused a shader with more than four Location inputs (Anvil code -20005, too many inputs); this slice binds four vertex attributes, which is what the emitted attribute records and the VPM input layout carry.")
  EndIf
  comps = avkSpvComponents(spvValueType[id])
  If comps < 1 Or comps > 4
    ProcedureReturn avkSpvRefuse(#SpvOpVariable, "the SPIR-V front end refused an interface variable that is neither a 32-bit float nor a vector of two to four of them (Anvil code -20005, unsupported interface type); every attribute and every varying this emitter moves is binary32.")
  EndIf
  If avkSpvIsFloatish(spvValueType[id]) = 0
    ProcedureReturn avkSpvRefuse(#SpvOpVariable, "the SPIR-V front end refused an interface variable whose component type is not a 32-bit float (Anvil code -20005, unsupported interface type); integer and boolean attributes and varyings are not lowered by this slice.")
  EndIf
  spvPlanAttrLoc[n] = spvDecLocation[id]
  spvPlanAttrComp[n] = comps
  spvPlanAttrVar[n] = id
  spvPlanAttrCount = n + 1
  ProcedureReturn #ANVIL_VK_OK
EndProcedure

; The attribute index whose variable this value is a whole load of, or
; -1. Both a direct OpLoad and an OpCompositeExtract of one are followed.
Procedure.i avkSpvAttrOfValue(v.i)
  Define k.i
  Define src.i
  If avkSpvIdOk(v) = 0 : ProcedureReturn -1 : EndIf
  If spvValueSrc[v] <> #ANVIL_SPV_V_INPUT : ProcedureReturn -1 : EndIf
  src = spvValueA[v]
  k = 0
  While k < spvPlanAttrCount
    If spvPlanAttrVar[k] = src : ProcedureReturn k : EndIf
    k = k + 1
  Wend
  ProcedureReturn -1
EndProcedure

; Every Location output of a vertex shader must be a WHOLE load of one
; input. A varying built out of pieces would need the emitter to hold an
; expression, and it does not hold one.
Procedure.i avkSpvCheckVertexVaryings()
  Define k.i
  Define a.i
  k = 0
  While k < spvPlanVaryCount
    a = avkSpvAttrOfValue(spvPlanVarySrc[k])
    If a < 0
      ProcedureReturn avkSpvRefuse(#SpvOpStore, "the SPIR-V front end refused a vertex shader whose Location output is not a whole load of one input (Anvil code -20005, unsupported varying); a varying is passed through here, not computed, so write it as a plain assignment from one attribute.")
    EndIf
    If spvPlanAttrComp[a] <> spvPlanVaryComp[k]
      ProcedureReturn avkSpvMalformed("a SPIR-V vertex module stores a value of one width into an output of another (Anvil code -20001, malformed module); the type of the object stored must match the pointee type of the variable it is stored into.")
    EndIf
    If spvPlanVaryLoc[k] <> k
      ProcedureReturn avkSpvRefuse(#SpvOpStore, "the SPIR-V front end refused a vertex shader whose output locations are not 0, 1, 2 in the order they are written (Anvil code -20005, unsupported interface layout); this slice maps output location n to varying n, so a gap or a reordering would deliver the wrong value to the fragment stage.")
    EndIf
    spvPlanVarySrc[k] = a
    k = k + 1
  Wend
  ProcedureReturn #ANVIL_VK_OK
EndProcedure

; ----------------------------------------------------------------------
;  THE VERTEX PLAN.
;
;  Position must be four components built from the x and y of ONE input,
;  a zero z and a one w. That is not a shortcut taken to save work: this
;  pipeline has no depth buffer and no perspective divide worth the name,
;  so a shader that asks for another z or another w would be asking for
;  behaviour the render pass does not have, and a front end that accepted
;  it would be promising something the picture would not show.
; ----------------------------------------------------------------------
Procedure.i avkSpvBuildVertexPlan()
  Define v.i
  Define n.i
  Define k.i
  Define c0.i
  Define c1.i
  Define c2.i
  Define c3.i
  Define a0.i
  Define a1.i

  If spvPosVar = 0
    ProcedureReturn avkSpvMalformed("a SPIR-V vertex module never writes gl_Position (Anvil code -20001, incomplete vertex shader); a vertex shader must store a four-component clip position into the Position built-in, or nothing can be rasterised.")
  EndIf
  v = spvPosValue
  If avkSpvIdOk(v) = 0
    ProcedureReturn avkSpvMalformed("a SPIR-V vertex module stored an undeclared id into gl_Position (Anvil code -20001, malformed module); the object operand of OpStore must be a value the module defines.")
  EndIf
  If spvValueSrc[v] = #ANVIL_SPV_V_INPUT
    ; gl_Position = a whole vec4 input.
    k = avkSpvAttrOfValue(v)
    If k < 0
      ProcedureReturn avkSpvMalformed("a SPIR-V vertex module stored a load of a variable that is not one of its declared Location inputs into gl_Position (Anvil code -20001, malformed module); an interface variable must be listed in the entry point's interface.")
    EndIf
    If spvPlanAttrComp[k] <> 4
      ProcedureReturn avkSpvRefuse(#SpvOpStore, "the SPIR-V front end refused a vertex shader that writes gl_Position from an input of other than four components (Anvil code -20005, unsupported position); either supply a four-component clip position, or build one with OpCompositeConstruct from two components, the constant 0.0 and the constant 1.0.")
    EndIf
    spvPlanPosAttr = k
    ProcedureReturn avkSpvCheckVertexVaryings()
  EndIf
  If spvValueSrc[v] <> #ANVIL_SPV_V_COMPOSITE
    ProcedureReturn avkSpvRefuse(#SpvOpStore, "the SPIR-V front end refused a vertex shader whose gl_Position is neither a whole input load nor an OpCompositeConstruct (Anvil code -20005, unsupported position); this slice moves a position, it does not compute one, so a transformed position cannot be lowered.")
  EndIf
  n = spvValueB[v]
  If n <> 4
    ProcedureReturn avkSpvMalformed("a SPIR-V vertex module built gl_Position from other than four components (Anvil code -20001, malformed module); the Position built-in is a four-component vector.")
  EndIf
  c0 = spvComposite[(v * 4) + 0]
  c1 = spvComposite[(v * 4) + 1]
  c2 = spvComposite[(v * 4) + 2]
  c3 = spvComposite[(v * 4) + 3]
  If avkSpvIdOk(c0) = 0 Or avkSpvIdOk(c1) = 0 Or avkSpvIdOk(c2) = 0 Or avkSpvIdOk(c3) = 0
    ProcedureReturn avkSpvMalformed("a SPIR-V vertex module built gl_Position from an undeclared id (Anvil code -20001, malformed module); every operand of OpCompositeConstruct must be a value the module defines.")
  EndIf
  ; z and w are the constants this pipeline can render.
  If spvKind[c2] <> #ANVIL_SPV_K_CONST Or spvConstWord[c2] <> 0
    ProcedureReturn avkSpvRefuse(#SpvOpStore, "the SPIR-V front end refused a vertex shader whose gl_Position.z is not the constant 0.0 (Anvil code -20005, unsupported position); there is no depth buffer and no depth test in this render pass, so a depth other than zero would be written nowhere and silently ignored.")
  EndIf
  If spvKind[c3] <> #ANVIL_SPV_K_CONST Or spvConstWord[c3] <> $3F800000
    ProcedureReturn avkSpvRefuse(#SpvOpStore, "the SPIR-V front end refused a vertex shader whose gl_Position.w is not the constant 1.0 (Anvil code -20005, unsupported position); this slice emits no perspective divide, so a w other than one would change the picture in a way the emitted shader would not carry out.")
  EndIf
  If spvValueSrc[c0] <> #ANVIL_SPV_V_EXTRACT Or spvValueSrc[c1] <> #ANVIL_SPV_V_EXTRACT
    ProcedureReturn avkSpvRefuse(#SpvOpStore, "the SPIR-V front end refused a vertex shader whose gl_Position.x or .y is not one component taken out of an input (Anvil code -20005, unsupported position); write gl_Position as vec4(inPosition.x, inPosition.y, 0.0, 1.0) over a two-component clip-space attribute.")
  EndIf
  If spvValueB[c0] <> 0 Or spvValueB[c1] <> 1
    ProcedureReturn avkSpvRefuse(#SpvOpStore, "the SPIR-V front end refused a vertex shader that puts components other than x and y, in that order, into gl_Position.xy (Anvil code -20005, unsupported position); a swizzle is not lowered by this slice.")
  EndIf
  a0 = avkSpvAttrOfValue(spvValueA[c0])
  a1 = avkSpvAttrOfValue(spvValueA[c1])
  If a0 < 0 Or a1 < 0 Or a0 <> a1
    ProcedureReturn avkSpvRefuse(#SpvOpStore, "the SPIR-V front end refused a vertex shader whose gl_Position.x and .y do not come from the same input attribute (Anvil code -20005, unsupported position); one attribute carries the whole clip position in this slice.")
  EndIf
  spvPlanPosAttr = a0
  ProcedureReturn avkSpvCheckVertexVaryings()
EndProcedure

; ----------------------------------------------------------------------
;  THE FRAGMENT PLAN. One output at Location 0, four components.
; ----------------------------------------------------------------------
Procedure.i avkSpvBuildFragmentPlan()
  Define v.i
  Define k.i
  Define src.i

  If spvPosVar <> 0
    ProcedureReturn avkSpvRefuse(#SpvOpStore, "the SPIR-V front end refused a fragment shader that writes a built-in output (Anvil code -20005, unsupported built-in); a fragment shader in this slice writes exactly one Location output and nothing else.")
  EndIf
  If spvPlanVaryCount <> 1
    ProcedureReturn avkSpvRefuse(#SpvOpStore, "the SPIR-V front end refused a fragment shader that does not write exactly one Location output (Anvil code -20005, unsupported fragment interface); there is one render target in this render pass, so a shader must write Location 0 and only Location 0.")
  EndIf
  If spvPlanVaryLoc[0] <> 0
    ProcedureReturn avkSpvRefuse(#SpvOpStore, "the SPIR-V front end refused a fragment shader whose one output is not at Location 0 (Anvil code -20005, unsupported fragment interface); the single colour attachment of this render pass is Location 0.")
  EndIf
  If spvPlanVaryComp[0] <> 4
    ProcedureReturn avkSpvRefuse(#SpvOpStore, "the SPIR-V front end refused a fragment shader whose output is not four components (Anvil code -20005, unsupported fragment interface); the render target is VK_FORMAT_B8G8R8A8_UNORM, so the shader must produce red, green, blue and alpha.")
  EndIf
  v = spvPlanVarySrc[0]
  If avkSpvIdOk(v) = 0
    ProcedureReturn avkSpvMalformed("a SPIR-V fragment module stored an undeclared id into its colour output (Anvil code -20001, malformed module); the object operand of OpStore must be a value the module defines.")
  EndIf
  src = spvValueSrc[v]
  If src = #ANVIL_SPV_V_INPUT
    k = avkSpvAttrOfValue(v)
    If k < 0
      ProcedureReturn avkSpvMalformed("a SPIR-V fragment module wrote its colour from a variable that is not one of its declared Location inputs (Anvil code -20001, malformed module); an interface variable must be listed in the entry point's interface.")
    EndIf
    If spvPlanAttrComp[k] <> 4
      ProcedureReturn avkSpvRefuse(#SpvOpStore, "the SPIR-V front end refused a fragment shader that writes its four-component colour from an input of fewer components (Anvil code -20005, unsupported fragment interface); the interpolated colour varying must itself be four components.")
    EndIf
    spvPlanColourSrc = #ANVIL_SPV_COLOUR_VARYING
    spvPlanColourIdx = k
    ProcedureReturn #ANVIL_VK_OK
  EndIf
  If src = #ANVIL_SPV_V_PUSH
    If spvValueA[v] <> 0
      ProcedureReturn avkSpvRefuse(#SpvOpStore, "the SPIR-V front end refused a fragment shader that reads a push-constant member other than the first (Anvil code -20005, unsupported push constant); the push-constant block this slice supplies is one four-component colour at offset zero.")
    EndIf
    spvPlanColourSrc = #ANVIL_SPV_COLOUR_PUSH
    spvPlanColourIdx = 0
    ProcedureReturn #ANVIL_VK_OK
  EndIf
  If src = #ANVIL_SPV_V_CONST
    spvPlanColourSrc = #ANVIL_SPV_COLOUR_CONST
    spvPlanColourIdx = 0
    k = 0
    While k < 4
      spvPlanConst[k] = spvComposite[(v * 4) + k]
      k = k + 1
    Wend
    ProcedureReturn #ANVIL_VK_OK
  EndIf
  ProcedureReturn avkSpvRefuse(#SpvOpStore, "the SPIR-V front end refused a fragment shader whose colour is neither an interpolated input, a push-constant member nor a constant (Anvil code -20005, unsupported fragment shader); this slice moves a colour into the tile buffer, it does not compute one.")
EndProcedure

; ----------------------------------------------------------------------
;  AnvilVkSpirvWalk - the whole module, front to back.
;
;  The caller has already checked that `bytes` is a multiple of four and
;  not zero; everything else about the module is checked here.
; ----------------------------------------------------------------------
Procedure.i AnvilVkSpirvWalk(*code, bytes.i)
  Define words.i
  Define at.i
  Define first.i
  Define op.i
  Define count.i
  Define rc.i
  Define id.i
  Define seenFunction.i

  avkSpvResetTables()
  spvLastOpcode = 0
  If *code = 0
    ProcedureReturn avkSpvMalformed("vkCreateShaderModule was given a null pCode (Anvil code -20001, invalid argument); VkShaderModuleCreateInfo.pCode must point at the module's first word.")
  EndIf
  If bytes <= 0 Or (bytes % 4) <> 0
    ProcedureReturn avkSpvMalformed("vkCreateShaderModule was given a codeSize that is zero or not a multiple of four (Anvil code -20001, invalid argument); a SPIR-V module is a stream of 32-bit words, so its byte length is always a multiple of four.")
  EndIf
  words = bytes / 4
  If words > #ANVIL_SPV_MAX_WORDS
    ProcedureReturn avkSpvMalformed("vkCreateShaderModule was given a SPIR-V module larger than Anvil's front end accepts (Anvil code -20001, module too large); the limit is 8192 bytes, which is a limit of this implementation and not of SPIR-V.")
  EndIf
  rc = avkSpvHeader(*code, words)
  If rc <> #ANVIL_VK_OK : ProcedureReturn rc : EndIf

  at = #ANVIL_SPV_HEADER_WORDS
  seenFunction = 0
  While at < words
    first = avkSpvWord(*code, at)
    op = first & $FFFF
    count = (first >> 16) & $FFFF
    If count = 0
      ProcedureReturn avkSpvMalformed("a SPIR-V instruction declared a word count of zero (Anvil code -20001, malformed module); the high half of an instruction's first word is its length in words and it is never less than one, so the stream cannot be walked past this point.")
    EndIf
    If (at + count) > words
      ProcedureReturn avkSpvMalformed("a SPIR-V instruction declared a word count that runs past the end of the module (Anvil code -20001, truncated module); the last instruction claims more words than codeSize supplies, so either the module was cut short or codeSize is wrong.")
    EndIf
    If op = #SpvOpFunction : seenFunction = 1 : EndIf
    rc = avkSpvDecl(*code, at, count, op)
    If rc <> #ANVIL_VK_OK : ProcedureReturn rc : EndIf
    spvInstructions = spvInstructions + 1
    at = at + count
  Wend

  If spvEntry = 0
    ProcedureReturn avkSpvMalformed("a SPIR-V module declares no entry point (Anvil code -20001, incomplete module); every shader module Vulkan accepts carries at least one OpEntryPoint, and this implementation requires exactly one.")
  EndIf
  If seenFunction = 0
    ProcedureReturn avkSpvMalformed("a SPIR-V module declares an entry point but holds no function body (Anvil code -20001, incomplete module); the entry point must be defined by an OpFunction in the same module.")
  EndIf

  ; Every Input variable becomes an attribute or an incoming varying, in
  ; declaration order, and the locations must then be 0..n-1. A sparse
  ; set is refused rather than packed: packing would silently move an
  ; attribute the caller bound by location.
  id = 1
  While id < spvBound
    If spvKind[id] = #ANVIL_SPV_K_VARIABLE
      If spvTypeStorage[id] = #SpvStorageClassInput
        If spvDecBuiltIn[id] <> -1
          ProcedureReturn avkSpvRefuse(#SpvOpVariable, "the SPIR-V front end refused a built-in input (Anvil code -20005, unsupported built-in); gl_VertexIndex, gl_InstanceIndex, gl_FragCoord, gl_FrontFacing and gl_PointCoord are not supplied by this implementation, so a shader that reads one would read nothing.")
        EndIf
        If spvDecLocation[id] < 0
          ProcedureReturn avkSpvMalformed("a SPIR-V module declares an Input variable with neither a Location nor a BuiltIn decoration (Anvil code -20001, malformed module); a Vulkan shader interface variable must carry one or the other.")
        EndIf
        rc = avkSpvAddInput(id)
        If rc <> #ANVIL_VK_OK : ProcedureReturn rc : EndIf
      EndIf
    EndIf
    id = id + 1
  Wend
  at = 0
  While at < spvPlanAttrCount
    If spvPlanAttrLoc[at] <> at
      ProcedureReturn avkSpvRefuse(#SpvOpVariable, "the SPIR-V front end refused a shader whose input locations are not 0, 1, 2 in order (Anvil code -20005, unsupported interface layout); this slice maps location n to vertex attribute n and to varying n, so a gap or a reordering would bind the wrong data.")
    EndIf
    at = at + 1
  Wend

  If spvStage = #SpvExecutionModelVertex
    ProcedureReturn avkSpvBuildVertexPlan()
  EndIf
  If spvOriginUpperLeft = 0
    ProcedureReturn avkSpvMalformed("a SPIR-V fragment module does not declare the execution mode OriginUpperLeft (Anvil code -20001, incomplete fragment shader); the Vulkan environment requires a fragment entry point to declare its origin, and OriginUpperLeft is the only one this implementation renders.")
  EndIf
  ProcedureReturn avkSpvBuildFragmentPlan()
EndProcedure

; ----------------------------------------------------------------------
;  Readers for the plan the last successful walk produced. The pipeline
;  layer copies these into its own slot; nothing else may hold them
;  across another walk.
; ----------------------------------------------------------------------
Procedure.i AnvilVkSpirvStage()
  ProcedureReturn spvStage
EndProcedure

Procedure.i AnvilVkSpirvBound()
  ProcedureReturn spvBound
EndProcedure

Procedure.i AnvilVkSpirvVersion()
  ProcedureReturn spvVersion
EndProcedure

Procedure.i AnvilVkSpirvInstructions()
  ProcedureReturn spvInstructions
EndProcedure

Procedure.i AnvilVkSpirvInputCount()
  ProcedureReturn spvPlanAttrCount
EndProcedure

Procedure.i AnvilVkSpirvInputComponents(k.i)
  If k < 0 Or k >= spvPlanAttrCount : ProcedureReturn 0 : EndIf
  ProcedureReturn spvPlanAttrComp[k]
EndProcedure

Procedure.i AnvilVkSpirvOutputCount()
  ProcedureReturn spvPlanVaryCount
EndProcedure

Procedure.i AnvilVkSpirvOutputLocation(k.i)
  If k < 0 Or k >= spvPlanVaryCount : ProcedureReturn -1 : EndIf
  ProcedureReturn spvPlanVaryLoc[k]
EndProcedure

Procedure.i AnvilVkSpirvOutputComponents(k.i)
  If k < 0 Or k >= spvPlanVaryCount : ProcedureReturn 0 : EndIf
  ProcedureReturn spvPlanVaryComp[k]
EndProcedure

; For a vertex shader: the attribute index each Location output is a
; pass-through of, or -1 when it is not a pass-through.
Procedure.i AnvilVkSpirvOutputSourceAttr(k.i)
  If spvStage <> #SpvExecutionModelVertex : ProcedureReturn -1 : EndIf
  If k < 0 Or k >= spvPlanVaryCount : ProcedureReturn -1 : EndIf
  ProcedureReturn spvPlanVarySrc[k]
EndProcedure

Procedure.i AnvilVkSpirvPositionAttr()
  ProcedureReturn spvPlanPosAttr
EndProcedure

Procedure.i AnvilVkSpirvColourSource()
  ProcedureReturn spvPlanColourSrc
EndProcedure

Procedure.i AnvilVkSpirvColourIndex()
  ProcedureReturn spvPlanColourIdx
EndProcedure

Procedure.i AnvilVkSpirvColourConstant(k.i)
  If k < 0 Or k > 3 : ProcedureReturn 0 : EndIf
  ProcedureReturn spvPlanConst[k]
EndProcedure

Procedure.i AnvilVkSpirvUsesPushConstants()
  If spvPushVar <> 0 : ProcedureReturn 1 : EndIf
  ProcedureReturn 0
EndProcedure

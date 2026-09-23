; ======================================================================
;  Hand-assembled SPIR-V modules
; ======================================================================
; SPDX-License-Identifier: MIT
;
; The seven shader modules the board diagnostics feed Anvil's SPIR-V front
; end, written out word by word so a reader can check them against the
; specification without a tool.
;
; THEY LIVE HERE RATHER THAN IN A DIAGNOSTIC because the desk gate walks
; the SAME modules and compares them, byte for byte, against modules
; a Python assembler builds independently. If they lived in a diagnostic,
; the board would be the first place anybody discovered that one of these
; words was wrong.
;
;   VsA  position-only vertex        VsB  position and colour vertex
;   FsA  push-constant fragment      FsB  interpolated fragment
;   FsC  uniform-buffer fragment
;   VsD  position and vec2 UV vertex FsD  combined-sampler fragment
;
; PROVENANCE. The binary layout, the opcode numbers and the enumerants
; are the Khronos SPIR-V specification's own (registry.khronos.org/SPIR-V,
; section 2.3 for the physical layout and 3.x for the enumerants),
; transcribed the way a header's values are. Nothing is copied from any
; SPIR-V tool, from SPIRV-Tools, from glslang or from any driver.

; The five modules, and the cursor the assembler below appends through.
; One kilobyte each is far more than any of them needs, and the front end
; refuses a module longer than eight.
Global Dim vtpVsA.l[256]
Global Dim vtpFsA.l[256]
Global Dim vtpVsB.l[256]
Global Dim vtpFsB.l[256]
Global Dim vtpFsC.l[256]
Global Dim vtpVsD.l[256]
Global Dim vtpFsD.l[256]
Global vtpBuf.i = 0
Global vtpN.i = 0

; ======================================================================
;  THE SPIR-V ASSEMBLER
; ======================================================================
;  Section 2.3 of the specification: a module is a five-word header -
;  magic, version, generator, id bound, schema - and then a stream of
;  instructions, each of which begins with a word whose low half is the
;  opcode and whose high half is the instruction's length in words.
;
;  The numbers below are the specification's own, transcribed the way a
;  header's values are. Nothing is copied from any tool.
; ======================================================================
; The two float constants every one of these modules carries.
#VTP_SPV_F_ZERO = $00000000
#VTP_SPV_F_ONE = $3F800000

#VTP_SPV_MAGIC = $07230203
#VTP_SPV_VERSION = $00010000

#VTP_OpCapability = 17
#VTP_OpMemoryModel = 14
#VTP_OpEntryPoint = 15
#VTP_OpExecutionMode = 16
#VTP_OpTypeVoid = 19
#VTP_OpTypeInt = 21
#VTP_OpTypeFloat = 22
#VTP_OpTypeVector = 23
#VTP_OpTypeImage = 25
#VTP_OpTypeSampledImage = 27
#VTP_OpTypeStruct = 30
#VTP_OpTypePointer = 32
#VTP_OpTypeFunction = 33
#VTP_OpConstant = 43
#VTP_OpFunction = 54
#VTP_OpFunctionEnd = 56
#VTP_OpVariable = 59
#VTP_OpLoad = 61
#VTP_OpStore = 62
#VTP_OpAccessChain = 65
#VTP_OpDecorate = 71
#VTP_OpMemberDecorate = 72
#VTP_OpCompositeConstruct = 80
#VTP_OpCompositeExtract = 81
#VTP_OpImageSampleImplicitLod = 87
#VTP_OpLabel = 248
#VTP_OpReturn = 253

#VTP_CapShader = 1
#VTP_AddrLogical = 0
#VTP_MemGLSL450 = 1
#VTP_EmVertex = 0
#VTP_EmFragment = 4
#VTP_ModeOriginUpperLeft = 7
#VTP_ScUniform = 2
#VTP_ScUniformConstant = 0
#VTP_ScInput = 1
#VTP_ScOutput = 3
#VTP_ScPushConstant = 9
#VTP_DecBlock = 2
#VTP_DecBuiltIn = 11
#VTP_DecLocation = 30
#VTP_DecBinding = 33
#VTP_DecDescriptorSet = 34
#VTP_DecOffset = 35
#VTP_BuiltInPosition = 0

; "main", NUL terminated and padded to two whole words.
#VTP_NAME0 = $6E69616D                 ; 'm','a','i','n'
#VTP_NAME1 = $00000000

Procedure vtpW(v.i)
  PokeL(vtpBuf + (vtpN * 4), v)
  vtpN = vtpN + 1
EndProcedure

; The texture fixtures are kept beside the opcode declarations. These two
; builders are defined below them, before the shared assembler helpers' bodies.
Declare vtpIns(op.i, n.i)
Declare vtpHeader(bound.i)

; ----------------------------------------------------------------------
;  The TEXTURE-COORDINATE vertex shader:
;      layout(location = 0) in vec2 inPosition;
;      layout(location = 1) in vec2 inUv;
;      layout(location = 0) out vec2 vUv;
; ----------------------------------------------------------------------
Procedure.i vtpBuildVsD()
  vtpBuf = @vtpVsD[0]
  vtpHeader(28)
  vtpIns(#VTP_OpCapability, 1) : vtpW(#VTP_CapShader)
  vtpIns(#VTP_OpMemoryModel, 2) : vtpW(#VTP_AddrLogical) : vtpW(#VTP_MemGLSL450)
  vtpIns(#VTP_OpEntryPoint, 8) : vtpW(#VTP_EmVertex) : vtpW(19) : vtpW(#VTP_NAME0) : vtpW(#VTP_NAME1) : vtpW(15) : vtpW(16) : vtpW(17) : vtpW(18)
  vtpIns(#VTP_OpMemberDecorate, 4) : vtpW(9) : vtpW(0) : vtpW(#VTP_DecBuiltIn) : vtpW(#VTP_BuiltInPosition)
  vtpIns(#VTP_OpDecorate, 2) : vtpW(9) : vtpW(#VTP_DecBlock)
  vtpIns(#VTP_OpDecorate, 3) : vtpW(15) : vtpW(#VTP_DecLocation) : vtpW(0)
  vtpIns(#VTP_OpDecorate, 3) : vtpW(16) : vtpW(#VTP_DecLocation) : vtpW(1)
  vtpIns(#VTP_OpDecorate, 3) : vtpW(17) : vtpW(#VTP_DecLocation) : vtpW(0)
  vtpIns(#VTP_OpTypeVoid, 1) : vtpW(1)
  vtpIns(#VTP_OpTypeFunction, 2) : vtpW(2) : vtpW(1)
  vtpIns(#VTP_OpTypeFloat, 2) : vtpW(3) : vtpW(32)
  vtpIns(#VTP_OpTypeVector, 3) : vtpW(4) : vtpW(3) : vtpW(2)
  vtpIns(#VTP_OpTypeVector, 3) : vtpW(5) : vtpW(3) : vtpW(4)
  vtpIns(#VTP_OpTypePointer, 3) : vtpW(6) : vtpW(#VTP_ScInput) : vtpW(4)
  vtpIns(#VTP_OpTypePointer, 3) : vtpW(7) : vtpW(#VTP_ScInput) : vtpW(4)
  vtpIns(#VTP_OpTypePointer, 3) : vtpW(8) : vtpW(#VTP_ScOutput) : vtpW(4)
  vtpIns(#VTP_OpTypeStruct, 2) : vtpW(9) : vtpW(5)
  vtpIns(#VTP_OpTypePointer, 3) : vtpW(10) : vtpW(#VTP_ScOutput) : vtpW(9)
  vtpIns(#VTP_OpTypePointer, 3) : vtpW(27) : vtpW(#VTP_ScOutput) : vtpW(5)
  vtpIns(#VTP_OpTypeInt, 3) : vtpW(11) : vtpW(32) : vtpW(1)
  vtpIns(#VTP_OpConstant, 3) : vtpW(11) : vtpW(12) : vtpW(0)
  vtpIns(#VTP_OpConstant, 3) : vtpW(3) : vtpW(13) : vtpW(#VTP_SPV_F_ZERO)
  vtpIns(#VTP_OpConstant, 3) : vtpW(3) : vtpW(14) : vtpW(#VTP_SPV_F_ONE)
  vtpIns(#VTP_OpVariable, 3) : vtpW(6) : vtpW(15) : vtpW(#VTP_ScInput)
  vtpIns(#VTP_OpVariable, 3) : vtpW(7) : vtpW(16) : vtpW(#VTP_ScInput)
  vtpIns(#VTP_OpVariable, 3) : vtpW(8) : vtpW(17) : vtpW(#VTP_ScOutput)
  vtpIns(#VTP_OpVariable, 3) : vtpW(10) : vtpW(18) : vtpW(#VTP_ScOutput)
  vtpIns(#VTP_OpFunction, 4) : vtpW(1) : vtpW(19) : vtpW(0) : vtpW(2)
  vtpIns(#VTP_OpLabel, 1) : vtpW(20)
  vtpIns(#VTP_OpLoad, 3) : vtpW(4) : vtpW(21) : vtpW(15)
  vtpIns(#VTP_OpCompositeExtract, 4) : vtpW(3) : vtpW(22) : vtpW(21) : vtpW(0)
  vtpIns(#VTP_OpCompositeExtract, 4) : vtpW(3) : vtpW(23) : vtpW(21) : vtpW(1)
  vtpIns(#VTP_OpCompositeConstruct, 6) : vtpW(5) : vtpW(24) : vtpW(22) : vtpW(23) : vtpW(13) : vtpW(14)
  vtpIns(#VTP_OpAccessChain, 4) : vtpW(27) : vtpW(25) : vtpW(18) : vtpW(12)
  vtpIns(#VTP_OpStore, 2) : vtpW(25) : vtpW(24)
  vtpIns(#VTP_OpLoad, 3) : vtpW(4) : vtpW(26) : vtpW(16)
  vtpIns(#VTP_OpStore, 2) : vtpW(17) : vtpW(26)
  vtpIns(#VTP_OpReturn, 0)
  vtpIns(#VTP_OpFunctionEnd, 0)
  ProcedureReturn vtpN * 4
EndProcedure

; ----------------------------------------------------------------------
;  The COMBINED-SAMPLER fragment shader:
;      layout(set = 0, binding = 0) uniform sampler2D tex;
;      layout(location = 0) in vec2 vUv;
;      layout(location = 0) out vec4 outColour;
;      void main() { outColour = texture(tex, vUv); }
; ----------------------------------------------------------------------
Procedure.i vtpBuildFsD()
  vtpBuf = @vtpFsD[0]
  vtpHeader(19)
  vtpIns(#VTP_OpCapability, 1) : vtpW(#VTP_CapShader)
  vtpIns(#VTP_OpMemoryModel, 2) : vtpW(#VTP_AddrLogical) : vtpW(#VTP_MemGLSL450)
  vtpIns(#VTP_OpEntryPoint, 6) : vtpW(#VTP_EmFragment) : vtpW(14) : vtpW(#VTP_NAME0) : vtpW(#VTP_NAME1) : vtpW(12) : vtpW(13)
  vtpIns(#VTP_OpExecutionMode, 2) : vtpW(14) : vtpW(#VTP_ModeOriginUpperLeft)
  vtpIns(#VTP_OpDecorate, 3) : vtpW(11) : vtpW(#VTP_DecDescriptorSet) : vtpW(0)
  vtpIns(#VTP_OpDecorate, 3) : vtpW(11) : vtpW(#VTP_DecBinding) : vtpW(0)
  vtpIns(#VTP_OpDecorate, 3) : vtpW(12) : vtpW(#VTP_DecLocation) : vtpW(0)
  vtpIns(#VTP_OpDecorate, 3) : vtpW(13) : vtpW(#VTP_DecLocation) : vtpW(0)
  vtpIns(#VTP_OpTypeVoid, 1) : vtpW(1)
  vtpIns(#VTP_OpTypeFunction, 2) : vtpW(2) : vtpW(1)
  vtpIns(#VTP_OpTypeFloat, 2) : vtpW(3) : vtpW(32)
  vtpIns(#VTP_OpTypeVector, 3) : vtpW(4) : vtpW(3) : vtpW(2)
  vtpIns(#VTP_OpTypeVector, 3) : vtpW(5) : vtpW(3) : vtpW(4)
  vtpIns(#VTP_OpTypeImage, 8) : vtpW(6) : vtpW(3) : vtpW(1) : vtpW(0) : vtpW(0) : vtpW(0) : vtpW(1) : vtpW(0)
  vtpIns(#VTP_OpTypeSampledImage, 2) : vtpW(7) : vtpW(6)
  vtpIns(#VTP_OpTypePointer, 3) : vtpW(8) : vtpW(#VTP_ScUniformConstant) : vtpW(7)
  vtpIns(#VTP_OpTypePointer, 3) : vtpW(9) : vtpW(#VTP_ScInput) : vtpW(4)
  vtpIns(#VTP_OpTypePointer, 3) : vtpW(10) : vtpW(#VTP_ScOutput) : vtpW(5)
  vtpIns(#VTP_OpVariable, 3) : vtpW(8) : vtpW(11) : vtpW(#VTP_ScUniformConstant)
  vtpIns(#VTP_OpVariable, 3) : vtpW(9) : vtpW(12) : vtpW(#VTP_ScInput)
  vtpIns(#VTP_OpVariable, 3) : vtpW(10) : vtpW(13) : vtpW(#VTP_ScOutput)
  vtpIns(#VTP_OpFunction, 4) : vtpW(1) : vtpW(14) : vtpW(0) : vtpW(2)
  vtpIns(#VTP_OpLabel, 1) : vtpW(15)
  vtpIns(#VTP_OpLoad, 3) : vtpW(7) : vtpW(16) : vtpW(11)
  vtpIns(#VTP_OpLoad, 3) : vtpW(4) : vtpW(17) : vtpW(12)
  vtpIns(#VTP_OpImageSampleImplicitLod, 4) : vtpW(5) : vtpW(18) : vtpW(16) : vtpW(17)
  vtpIns(#VTP_OpStore, 2) : vtpW(13) : vtpW(18)
  vtpIns(#VTP_OpReturn, 0)
  vtpIns(#VTP_OpFunctionEnd, 0)
  ProcedureReturn vtpN * 4
EndProcedure

; One instruction header: `n` is the number of operand words after it.
Procedure vtpIns(op.i, n.i)
  vtpW(((n + 1) << 16) | op)
EndProcedure

Procedure vtpHeader(bound.i)
  vtpN = 0
  vtpW(#VTP_SPV_MAGIC)
  vtpW(#VTP_SPV_VERSION)
  vtpW(0)
  vtpW(bound)
  vtpW(0)
EndProcedure

; ----------------------------------------------------------------------
;  The POSITION-ONLY vertex shader:
;      layout(location = 0) in vec2 inPosition;
;      void main() { gl_Position = vec4(inPosition.x, inPosition.y,
;                                       0.0, 1.0); }
; ----------------------------------------------------------------------
Procedure.i vtpBuildVsA()
  vtpBuf = @vtpVsA[0]
  vtpHeader(23)
  vtpIns(#VTP_OpCapability, 1) : vtpW(#VTP_CapShader)
  vtpIns(#VTP_OpMemoryModel, 2) : vtpW(#VTP_AddrLogical) : vtpW(#VTP_MemGLSL450)
  vtpIns(#VTP_OpEntryPoint, 6) : vtpW(#VTP_EmVertex) : vtpW(16) : vtpW(#VTP_NAME0) : vtpW(#VTP_NAME1) : vtpW(13) : vtpW(14)
  vtpIns(#VTP_OpMemberDecorate, 4) : vtpW(8) : vtpW(0) : vtpW(#VTP_DecBuiltIn) : vtpW(#VTP_BuiltInPosition)
  vtpIns(#VTP_OpDecorate, 2) : vtpW(8) : vtpW(#VTP_DecBlock)
  vtpIns(#VTP_OpDecorate, 3) : vtpW(13) : vtpW(#VTP_DecLocation) : vtpW(0)
  vtpIns(#VTP_OpTypeVoid, 1) : vtpW(1)
  vtpIns(#VTP_OpTypeFunction, 2) : vtpW(2) : vtpW(1)
  vtpIns(#VTP_OpTypeFloat, 2) : vtpW(3) : vtpW(32)
  vtpIns(#VTP_OpTypeVector, 3) : vtpW(4) : vtpW(3) : vtpW(2)
  vtpIns(#VTP_OpTypeVector, 3) : vtpW(5) : vtpW(3) : vtpW(4)
  vtpIns(#VTP_OpTypePointer, 3) : vtpW(6) : vtpW(#VTP_ScInput) : vtpW(4)
  vtpIns(#VTP_OpTypeStruct, 2) : vtpW(8) : vtpW(5)
  vtpIns(#VTP_OpTypePointer, 3) : vtpW(9) : vtpW(#VTP_ScOutput) : vtpW(8)
  vtpIns(#VTP_OpTypePointer, 3) : vtpW(7) : vtpW(#VTP_ScOutput) : vtpW(5)
  vtpIns(#VTP_OpTypeInt, 3) : vtpW(10) : vtpW(32) : vtpW(1)
  vtpIns(#VTP_OpConstant, 3) : vtpW(10) : vtpW(11) : vtpW(0)
  vtpIns(#VTP_OpConstant, 3) : vtpW(3) : vtpW(12) : vtpW(#VTP_SPV_F_ZERO)
  vtpIns(#VTP_OpConstant, 3) : vtpW(3) : vtpW(15) : vtpW(#VTP_SPV_F_ONE)
  vtpIns(#VTP_OpVariable, 3) : vtpW(6) : vtpW(13) : vtpW(#VTP_ScInput)
  vtpIns(#VTP_OpVariable, 3) : vtpW(9) : vtpW(14) : vtpW(#VTP_ScOutput)
  vtpIns(#VTP_OpFunction, 4) : vtpW(1) : vtpW(16) : vtpW(0) : vtpW(2)
  vtpIns(#VTP_OpLabel, 1) : vtpW(17)
  vtpIns(#VTP_OpLoad, 3) : vtpW(4) : vtpW(18) : vtpW(13)
  vtpIns(#VTP_OpCompositeExtract, 4) : vtpW(3) : vtpW(19) : vtpW(18) : vtpW(0)
  vtpIns(#VTP_OpCompositeExtract, 4) : vtpW(3) : vtpW(20) : vtpW(18) : vtpW(1)
  vtpIns(#VTP_OpCompositeConstruct, 6) : vtpW(5) : vtpW(21) : vtpW(19) : vtpW(20) : vtpW(12) : vtpW(15)
  vtpIns(#VTP_OpAccessChain, 4) : vtpW(7) : vtpW(22) : vtpW(14) : vtpW(11)
  vtpIns(#VTP_OpStore, 2) : vtpW(22) : vtpW(21)
  vtpIns(#VTP_OpReturn, 0)
  vtpIns(#VTP_OpFunctionEnd, 0)
  ProcedureReturn vtpN * 4
EndProcedure

; ----------------------------------------------------------------------
;  The PUSH-CONSTANT fragment shader:
;      layout(push_constant) uniform P { vec4 colour; } pc;
;      layout(location = 0) out vec4 outColour;
;      void main() { outColour = pc.colour; }
; ----------------------------------------------------------------------
Procedure.i vtpBuildFsA()
  vtpBuf = @vtpFsA[0]
  vtpHeader(17)
  vtpIns(#VTP_OpCapability, 1) : vtpW(#VTP_CapShader)
  vtpIns(#VTP_OpMemoryModel, 2) : vtpW(#VTP_AddrLogical) : vtpW(#VTP_MemGLSL450)
  vtpIns(#VTP_OpEntryPoint, 5) : vtpW(#VTP_EmFragment) : vtpW(13) : vtpW(#VTP_NAME0) : vtpW(#VTP_NAME1) : vtpW(9)
  vtpIns(#VTP_OpExecutionMode, 2) : vtpW(13) : vtpW(#VTP_ModeOriginUpperLeft)
  vtpIns(#VTP_OpDecorate, 2) : vtpW(5) : vtpW(#VTP_DecBlock)
  vtpIns(#VTP_OpMemberDecorate, 4) : vtpW(5) : vtpW(0) : vtpW(#VTP_DecOffset) : vtpW(0)
  vtpIns(#VTP_OpDecorate, 3) : vtpW(9) : vtpW(#VTP_DecLocation) : vtpW(0)
  vtpIns(#VTP_OpTypeVoid, 1) : vtpW(1)
  vtpIns(#VTP_OpTypeFunction, 2) : vtpW(2) : vtpW(1)
  vtpIns(#VTP_OpTypeFloat, 2) : vtpW(3) : vtpW(32)
  vtpIns(#VTP_OpTypeVector, 3) : vtpW(4) : vtpW(3) : vtpW(4)
  vtpIns(#VTP_OpTypeStruct, 2) : vtpW(5) : vtpW(4)
  vtpIns(#VTP_OpTypePointer, 3) : vtpW(6) : vtpW(#VTP_ScPushConstant) : vtpW(5)
  vtpIns(#VTP_OpTypePointer, 3) : vtpW(7) : vtpW(#VTP_ScOutput) : vtpW(4)
  vtpIns(#VTP_OpTypePointer, 3) : vtpW(12) : vtpW(#VTP_ScPushConstant) : vtpW(4)
  vtpIns(#VTP_OpTypeInt, 3) : vtpW(10) : vtpW(32) : vtpW(1)
  vtpIns(#VTP_OpConstant, 3) : vtpW(10) : vtpW(11) : vtpW(0)
  vtpIns(#VTP_OpVariable, 3) : vtpW(6) : vtpW(8) : vtpW(#VTP_ScPushConstant)
  vtpIns(#VTP_OpVariable, 3) : vtpW(7) : vtpW(9) : vtpW(#VTP_ScOutput)
  vtpIns(#VTP_OpFunction, 4) : vtpW(1) : vtpW(13) : vtpW(0) : vtpW(2)
  vtpIns(#VTP_OpLabel, 1) : vtpW(14)
  vtpIns(#VTP_OpAccessChain, 4) : vtpW(12) : vtpW(15) : vtpW(8) : vtpW(11)
  vtpIns(#VTP_OpLoad, 3) : vtpW(4) : vtpW(16) : vtpW(15)
  vtpIns(#VTP_OpStore, 2) : vtpW(9) : vtpW(16)
  vtpIns(#VTP_OpReturn, 0)
  vtpIns(#VTP_OpFunctionEnd, 0)
  ProcedureReturn vtpN * 4
EndProcedure

; ----------------------------------------------------------------------
;  The PASS-THROUGH vertex shader:
;      layout(location = 0) in vec2 inPosition;
;      layout(location = 1) in vec4 inColour;
;      layout(location = 0) out vec4 vColour;
;      void main() { gl_Position = vec4(inPosition.x, inPosition.y,
;                                       0.0, 1.0);
;                    vColour = inColour; }
; ----------------------------------------------------------------------
Procedure.i vtpBuildVsB()
  vtpBuf = @vtpVsB[0]
  vtpHeader(27)
  vtpIns(#VTP_OpCapability, 1) : vtpW(#VTP_CapShader)
  vtpIns(#VTP_OpMemoryModel, 2) : vtpW(#VTP_AddrLogical) : vtpW(#VTP_MemGLSL450)
  vtpIns(#VTP_OpEntryPoint, 8) : vtpW(#VTP_EmVertex) : vtpW(19) : vtpW(#VTP_NAME0) : vtpW(#VTP_NAME1) : vtpW(15) : vtpW(16) : vtpW(17) : vtpW(18)
  vtpIns(#VTP_OpMemberDecorate, 4) : vtpW(9) : vtpW(0) : vtpW(#VTP_DecBuiltIn) : vtpW(#VTP_BuiltInPosition)
  vtpIns(#VTP_OpDecorate, 2) : vtpW(9) : vtpW(#VTP_DecBlock)
  vtpIns(#VTP_OpDecorate, 3) : vtpW(15) : vtpW(#VTP_DecLocation) : vtpW(0)
  vtpIns(#VTP_OpDecorate, 3) : vtpW(16) : vtpW(#VTP_DecLocation) : vtpW(1)
  vtpIns(#VTP_OpDecorate, 3) : vtpW(17) : vtpW(#VTP_DecLocation) : vtpW(0)
  vtpIns(#VTP_OpTypeVoid, 1) : vtpW(1)
  vtpIns(#VTP_OpTypeFunction, 2) : vtpW(2) : vtpW(1)
  vtpIns(#VTP_OpTypeFloat, 2) : vtpW(3) : vtpW(32)
  vtpIns(#VTP_OpTypeVector, 3) : vtpW(4) : vtpW(3) : vtpW(2)
  vtpIns(#VTP_OpTypeVector, 3) : vtpW(5) : vtpW(3) : vtpW(4)
  vtpIns(#VTP_OpTypePointer, 3) : vtpW(6) : vtpW(#VTP_ScInput) : vtpW(4)
  vtpIns(#VTP_OpTypePointer, 3) : vtpW(7) : vtpW(#VTP_ScInput) : vtpW(5)
  vtpIns(#VTP_OpTypePointer, 3) : vtpW(8) : vtpW(#VTP_ScOutput) : vtpW(5)
  vtpIns(#VTP_OpTypeStruct, 2) : vtpW(9) : vtpW(5)
  vtpIns(#VTP_OpTypePointer, 3) : vtpW(10) : vtpW(#VTP_ScOutput) : vtpW(9)
  vtpIns(#VTP_OpTypeInt, 3) : vtpW(11) : vtpW(32) : vtpW(1)
  vtpIns(#VTP_OpConstant, 3) : vtpW(11) : vtpW(12) : vtpW(0)
  vtpIns(#VTP_OpConstant, 3) : vtpW(3) : vtpW(13) : vtpW(#VTP_SPV_F_ZERO)
  vtpIns(#VTP_OpConstant, 3) : vtpW(3) : vtpW(14) : vtpW(#VTP_SPV_F_ONE)
  vtpIns(#VTP_OpVariable, 3) : vtpW(6) : vtpW(15) : vtpW(#VTP_ScInput)
  vtpIns(#VTP_OpVariable, 3) : vtpW(7) : vtpW(16) : vtpW(#VTP_ScInput)
  vtpIns(#VTP_OpVariable, 3) : vtpW(8) : vtpW(17) : vtpW(#VTP_ScOutput)
  vtpIns(#VTP_OpVariable, 3) : vtpW(10) : vtpW(18) : vtpW(#VTP_ScOutput)
  vtpIns(#VTP_OpFunction, 4) : vtpW(1) : vtpW(19) : vtpW(0) : vtpW(2)
  vtpIns(#VTP_OpLabel, 1) : vtpW(20)
  vtpIns(#VTP_OpLoad, 3) : vtpW(4) : vtpW(21) : vtpW(15)
  vtpIns(#VTP_OpCompositeExtract, 4) : vtpW(3) : vtpW(22) : vtpW(21) : vtpW(0)
  vtpIns(#VTP_OpCompositeExtract, 4) : vtpW(3) : vtpW(23) : vtpW(21) : vtpW(1)
  vtpIns(#VTP_OpCompositeConstruct, 6) : vtpW(5) : vtpW(24) : vtpW(22) : vtpW(23) : vtpW(13) : vtpW(14)
  vtpIns(#VTP_OpAccessChain, 4) : vtpW(8) : vtpW(25) : vtpW(18) : vtpW(12)
  vtpIns(#VTP_OpStore, 2) : vtpW(25) : vtpW(24)
  vtpIns(#VTP_OpLoad, 3) : vtpW(5) : vtpW(26) : vtpW(16)
  vtpIns(#VTP_OpStore, 2) : vtpW(17) : vtpW(26)
  vtpIns(#VTP_OpReturn, 0)
  vtpIns(#VTP_OpFunctionEnd, 0)
  ProcedureReturn vtpN * 4
EndProcedure

; ----------------------------------------------------------------------
;  The INTERPOLATED fragment shader:
;      layout(location = 0) in vec4 vColour;
;      layout(location = 0) out vec4 outColour;
;      void main() { outColour = vColour; }
; ----------------------------------------------------------------------
Procedure.i vtpBuildFsB()
  vtpBuf = @vtpFsB[0]
  vtpHeader(12)
  vtpIns(#VTP_OpCapability, 1) : vtpW(#VTP_CapShader)
  vtpIns(#VTP_OpMemoryModel, 2) : vtpW(#VTP_AddrLogical) : vtpW(#VTP_MemGLSL450)
  vtpIns(#VTP_OpEntryPoint, 6) : vtpW(#VTP_EmFragment) : vtpW(9) : vtpW(#VTP_NAME0) : vtpW(#VTP_NAME1) : vtpW(7) : vtpW(8)
  vtpIns(#VTP_OpExecutionMode, 2) : vtpW(9) : vtpW(#VTP_ModeOriginUpperLeft)
  vtpIns(#VTP_OpDecorate, 3) : vtpW(7) : vtpW(#VTP_DecLocation) : vtpW(0)
  vtpIns(#VTP_OpDecorate, 3) : vtpW(8) : vtpW(#VTP_DecLocation) : vtpW(0)
  vtpIns(#VTP_OpTypeVoid, 1) : vtpW(1)
  vtpIns(#VTP_OpTypeFunction, 2) : vtpW(2) : vtpW(1)
  vtpIns(#VTP_OpTypeFloat, 2) : vtpW(3) : vtpW(32)
  vtpIns(#VTP_OpTypeVector, 3) : vtpW(4) : vtpW(3) : vtpW(4)
  vtpIns(#VTP_OpTypePointer, 3) : vtpW(5) : vtpW(#VTP_ScInput) : vtpW(4)
  vtpIns(#VTP_OpTypePointer, 3) : vtpW(6) : vtpW(#VTP_ScOutput) : vtpW(4)
  vtpIns(#VTP_OpVariable, 3) : vtpW(5) : vtpW(7) : vtpW(#VTP_ScInput)
  vtpIns(#VTP_OpVariable, 3) : vtpW(6) : vtpW(8) : vtpW(#VTP_ScOutput)
  vtpIns(#VTP_OpFunction, 4) : vtpW(1) : vtpW(9) : vtpW(0) : vtpW(2)
  vtpIns(#VTP_OpLabel, 1) : vtpW(10)
  vtpIns(#VTP_OpLoad, 3) : vtpW(4) : vtpW(11) : vtpW(7)
  vtpIns(#VTP_OpStore, 2) : vtpW(8) : vtpW(11)
  vtpIns(#VTP_OpReturn, 0)
  vtpIns(#VTP_OpFunctionEnd, 0)
  ProcedureReturn vtpN * 4
EndProcedure

; ----------------------------------------------------------------------
;  The UNIFORM-BUFFER fragment shader:
;      layout(set = 0, binding = 0) uniform U { vec4 colour; } ubo;
;      layout(location = 0) out vec4 outColour;
;      void main() { outColour = ubo.colour; }
;
;  Word for word the push-constant shader above with three differences,
;  and they are the whole of what a descriptor is in SPIR-V: the storage
;  class is Uniform rather than PushConstant, and the variable carries
;  DescriptorSet and Binding. The Block decoration on the structure and
;  the Offset on its member are unchanged, because a push-constant block
;  and a uniform block are the same kind of structure - which is exactly
;  why the two can be compared against each other on the bench.
; ----------------------------------------------------------------------
Procedure.i vtpBuildFsC()
  vtpBuf = @vtpFsC[0]
  vtpHeader(17)
  vtpIns(#VTP_OpCapability, 1) : vtpW(#VTP_CapShader)
  vtpIns(#VTP_OpMemoryModel, 2) : vtpW(#VTP_AddrLogical) : vtpW(#VTP_MemGLSL450)
  vtpIns(#VTP_OpEntryPoint, 5) : vtpW(#VTP_EmFragment) : vtpW(13) : vtpW(#VTP_NAME0) : vtpW(#VTP_NAME1) : vtpW(9)
  vtpIns(#VTP_OpExecutionMode, 2) : vtpW(13) : vtpW(#VTP_ModeOriginUpperLeft)
  vtpIns(#VTP_OpDecorate, 2) : vtpW(5) : vtpW(#VTP_DecBlock)
  vtpIns(#VTP_OpMemberDecorate, 4) : vtpW(5) : vtpW(0) : vtpW(#VTP_DecOffset) : vtpW(0)
  vtpIns(#VTP_OpDecorate, 3) : vtpW(8) : vtpW(#VTP_DecDescriptorSet) : vtpW(0)
  vtpIns(#VTP_OpDecorate, 3) : vtpW(8) : vtpW(#VTP_DecBinding) : vtpW(0)
  vtpIns(#VTP_OpDecorate, 3) : vtpW(9) : vtpW(#VTP_DecLocation) : vtpW(0)
  vtpIns(#VTP_OpTypeVoid, 1) : vtpW(1)
  vtpIns(#VTP_OpTypeFunction, 2) : vtpW(2) : vtpW(1)
  vtpIns(#VTP_OpTypeFloat, 2) : vtpW(3) : vtpW(32)
  vtpIns(#VTP_OpTypeVector, 3) : vtpW(4) : vtpW(3) : vtpW(4)
  vtpIns(#VTP_OpTypeStruct, 2) : vtpW(5) : vtpW(4)
  vtpIns(#VTP_OpTypePointer, 3) : vtpW(6) : vtpW(#VTP_ScUniform) : vtpW(5)
  vtpIns(#VTP_OpTypePointer, 3) : vtpW(7) : vtpW(#VTP_ScOutput) : vtpW(4)
  vtpIns(#VTP_OpTypePointer, 3) : vtpW(12) : vtpW(#VTP_ScUniform) : vtpW(4)
  vtpIns(#VTP_OpTypeInt, 3) : vtpW(10) : vtpW(32) : vtpW(1)
  vtpIns(#VTP_OpConstant, 3) : vtpW(10) : vtpW(11) : vtpW(0)
  vtpIns(#VTP_OpVariable, 3) : vtpW(6) : vtpW(8) : vtpW(#VTP_ScUniform)
  vtpIns(#VTP_OpVariable, 3) : vtpW(7) : vtpW(9) : vtpW(#VTP_ScOutput)
  vtpIns(#VTP_OpFunction, 4) : vtpW(1) : vtpW(13) : vtpW(0) : vtpW(2)
  vtpIns(#VTP_OpLabel, 1) : vtpW(14)
  vtpIns(#VTP_OpAccessChain, 4) : vtpW(12) : vtpW(15) : vtpW(8) : vtpW(11)
  vtpIns(#VTP_OpLoad, 3) : vtpW(4) : vtpW(16) : vtpW(15)
  vtpIns(#VTP_OpStore, 2) : vtpW(9) : vtpW(16)
  vtpIns(#VTP_OpReturn, 0)
  vtpIns(#VTP_OpFunctionEnd, 0)
  ProcedureReturn vtpN * 4
EndProcedure

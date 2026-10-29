; SPDX-License-Identifier: MIT
; Include after neon_vk_chrome.pbi. Optional final-canvas CRT pass.
Procedure.i nvrBuildFragmentShader()
  vtpBuf = @nvcFs[0]
  vtpHeader(98)
  vtpIns(#VTP_OpCapability, 1) : vtpW(#VTP_CapShader)
  vtpIns(11, 5) : vtpW($27) : vtpW($4C534C47) : vtpW($6474732E) : vtpW($3035342E) : vtpW($0)
  vtpIns(#VTP_OpMemoryModel, 2) : vtpW(#VTP_AddrLogical) : vtpW(#VTP_MemGLSL450)
  vtpIns(#VTP_OpEntryPoint, 6) : vtpW(#VTP_EmFragment) : vtpW(24) : vtpW(#VTP_NAME0) : vtpW(#VTP_NAME1) : vtpW(12) : vtpW(13)
  vtpIns(#VTP_OpExecutionMode, 2) : vtpW(24) : vtpW(#VTP_ModeOriginUpperLeft)
  vtpIns(#VTP_OpDecorate, 3) : vtpW(11) : vtpW(#VTP_DecDescriptorSet) : vtpW(0)
  vtpIns(#VTP_OpDecorate, 3) : vtpW(11) : vtpW(#VTP_DecBinding) : vtpW(1)
  vtpIns(#VTP_OpDecorate, 3) : vtpW(12) : vtpW(#VTP_DecLocation) : vtpW(0)
  vtpIns(#VTP_OpDecorate, 3) : vtpW(13) : vtpW(#VTP_DecLocation) : vtpW(0)
  vtpIns(#VTP_OpDecorate, 2) : vtpW(20) : vtpW(#VTP_DecBlock)
  vtpIns(#VTP_OpMemberDecorate, 4) : vtpW(20) : vtpW(0) : vtpW(#VTP_DecOffset) : vtpW(0)
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
  vtpIns(#VTP_OpTypeInt, 3) : vtpW(18) : vtpW(32) : vtpW(1)
  vtpIns(#VTP_OpConstant, 3) : vtpW(18) : vtpW(19) : vtpW(0)
  vtpIns(#VTP_OpTypeStruct, 2) : vtpW(20) : vtpW(5)
  vtpIns(#VTP_OpTypePointer, 3) : vtpW(21) : vtpW(#VTP_ScPushConstant) : vtpW(20)
  vtpIns(#VTP_OpTypePointer, 3) : vtpW(23) : vtpW(#VTP_ScPushConstant) : vtpW(5)
  vtpIns(#VTP_OpVariable, 3) : vtpW(8) : vtpW(11) : vtpW(#VTP_ScUniformConstant)
  vtpIns(#VTP_OpVariable, 3) : vtpW(9) : vtpW(12) : vtpW(#VTP_ScInput)
  vtpIns(#VTP_OpVariable, 3) : vtpW(10) : vtpW(13) : vtpW(#VTP_ScOutput)
  vtpIns(#VTP_OpVariable, 3) : vtpW(21) : vtpW(22) : vtpW(#VTP_ScPushConstant)
  vtpIns(43, 3) : vtpW($3) : vtpW($28) : vtpW($3E800000)
  vtpIns(43, 3) : vtpW($3) : vtpW($2C) : vtpW($44480000)
  vtpIns(43, 3) : vtpW($3) : vtpW($2D) : vtpW($41200000)
  vtpIns(43, 3) : vtpW($3) : vtpW($2E) : vtpW($3D23D70A)
  vtpIns(43, 3) : vtpW($3) : vtpW($2F) : vtpW($0)
  vtpIns(43, 3) : vtpW($3) : vtpW($3C) : vtpW($40000000)
  vtpIns(43, 3) : vtpW($3) : vtpW($3D) : vtpW($3F800000)
  vtpIns(43, 3) : vtpW($3) : vtpW($3E) : vtpW($3F000000)
  vtpIns(44, 4) : vtpW($4) : vtpW($40) : vtpW($3D) : vtpW($3D)
  vtpIns(44, 4) : vtpW($4) : vtpW($41) : vtpW($3E) : vtpW($3E)
  vtpIns(43, 3) : vtpW($3) : vtpW($51) : vtpW($3E99999A)
  vtpIns(43, 3) : vtpW($3) : vtpW($52) : vtpW($3F4CCCCD)
  vtpIns(20, 1) : vtpW($53)
  vtpIns(23, 3) : vtpW($54) : vtpW($53) : vtpW($2)
  vtpIns(23, 3) : vtpW($55) : vtpW($53) : vtpW($4)
  vtpIns(44, 4) : vtpW($4) : vtpW($56) : vtpW($2F) : vtpW($2F)
  vtpIns(44, 4) : vtpW($4) : vtpW($57) : vtpW($3D) : vtpW($3D)
  vtpIns(44, 6) : vtpW($5) : vtpW($58) : vtpW($2F) : vtpW($2F) : vtpW($2F) : vtpW($3D)
  vtpIns(#VTP_OpFunction, 4) : vtpW(1) : vtpW(24) : vtpW(0) : vtpW(2)
  vtpIns(#VTP_OpLabel, 1) : vtpW(25)
  vtpIns(#VTP_OpLoad, 3) : vtpW(7) : vtpW(26) : vtpW(11)
  vtpIns(#VTP_OpLoad, 3) : vtpW(4) : vtpW(27) : vtpW(12)
  vtpIns(#VTP_OpAccessChain, 4) : vtpW(23) : vtpW(29) : vtpW(22) : vtpW(19)
  vtpIns(#VTP_OpLoad, 3) : vtpW(5) : vtpW(30) : vtpW(29)
  vtpIns(81, 4) : vtpW($3) : vtpW($4A) : vtpW($1E) : vtpW($2)
  vtpIns(142, 4) : vtpW($4) : vtpW($42) : vtpW($1B) : vtpW($3C)
  vtpIns(131, 4) : vtpW($4) : vtpW($43) : vtpW($42) : vtpW($40)
  vtpIns(148, 4) : vtpW($3) : vtpW($44) : vtpW($43) : vtpW($43)
  vtpIns(142, 4) : vtpW($4) : vtpW($45) : vtpW($43) : vtpW($44)
  vtpIns(142, 4) : vtpW($4) : vtpW($46) : vtpW($45) : vtpW($4A)
  vtpIns(129, 4) : vtpW($4) : vtpW($47) : vtpW($43) : vtpW($46)
  vtpIns(142, 4) : vtpW($4) : vtpW($48) : vtpW($47) : vtpW($3E)
  vtpIns(129, 4) : vtpW($4) : vtpW($49) : vtpW($48) : vtpW($41)
  vtpIns(#VTP_OpImageSampleImplicitLod, 4) : vtpW(5) : vtpW(28) : vtpW(26) : vtpW(73)
  vtpIns(81, 4) : vtpW($3) : vtpW($2B) : vtpW($49) : vtpW($1)
  vtpIns(133, 4) : vtpW($3) : vtpW($30) : vtpW($2B) : vtpW($2C)
  vtpIns(81, 4) : vtpW($3) : vtpW($31) : vtpW($1E) : vtpW($0)
  vtpIns(133, 4) : vtpW($3) : vtpW($32) : vtpW($31) : vtpW($2D)
  vtpIns(131, 4) : vtpW($3) : vtpW($33) : vtpW($30) : vtpW($32)
  vtpIns(12, 5) : vtpW($3) : vtpW($34) : vtpW($27) : vtpW($D) : vtpW($33)
  vtpIns(133, 4) : vtpW($3) : vtpW($35) : vtpW($34) : vtpW($2E)
  vtpIns(81, 4) : vtpW($3) : vtpW($36) : vtpW($1E) : vtpW($1)
  vtpIns(133, 4) : vtpW($3) : vtpW($37) : vtpW($35) : vtpW($36)
  vtpIns(80, 6) : vtpW($5) : vtpW($38) : vtpW($37) : vtpW($37) : vtpW($37) : vtpW($2F)
  vtpIns(131, 4) : vtpW($5) : vtpW($4B) : vtpW($1C) : vtpW($38)
  vtpIns(12, 6) : vtpW($3) : vtpW($4C) : vtpW($27) : vtpW($43) : vtpW($49) : vtpW($41)
  vtpIns(12, 7) : vtpW($3) : vtpW($4D) : vtpW($27) : vtpW($31) : vtpW($51) : vtpW($52) : vtpW($4C)
  vtpIns(133, 4) : vtpW($3) : vtpW($4E) : vtpW($4D) : vtpW($36)
  vtpIns(131, 4) : vtpW($3) : vtpW($4F) : vtpW($3D) : vtpW($4E)
  vtpIns(80, 6) : vtpW($5) : vtpW($50) : vtpW($4F) : vtpW($4F) : vtpW($4F) : vtpW($3D)
  vtpIns(133, 4) : vtpW($5) : vtpW($22) : vtpW($4B) : vtpW($50)
  vtpIns(184, 4) : vtpW($54) : vtpW($5A) : vtpW($49) : vtpW($56)
  vtpIns(186, 4) : vtpW($54) : vtpW($5B) : vtpW($49) : vtpW($57)
  vtpIns(166, 4) : vtpW($54) : vtpW($5C) : vtpW($5A) : vtpW($5B)
  vtpIns(81, 4) : vtpW($53) : vtpW($5D) : vtpW($5C) : vtpW($0)
  vtpIns(81, 4) : vtpW($53) : vtpW($5E) : vtpW($5C) : vtpW($1)
  vtpIns(166, 4) : vtpW($53) : vtpW($5F) : vtpW($5D) : vtpW($5E)
  vtpIns(80, 6) : vtpW($55) : vtpW($60) : vtpW($5F) : vtpW($5F) : vtpW($5F) : vtpW($5F)
  vtpIns(169, 5) : vtpW($5) : vtpW($61) : vtpW($60) : vtpW($58) : vtpW($22)
  vtpIns(#VTP_OpStore, 2) : vtpW(13) : vtpW(97)
  vtpIns(#VTP_OpReturn, 0)
  vtpIns(#VTP_OpFunctionEnd, 0)
  ProcedureReturn vtpN * 4
EndProcedure

Procedure.i NeonVkChromeRetroPrepare()
  Protected bytes.i,rc.i
  If nvcReady=0 Or nvcInFrame<>0 Or nvcFramePending<>0 : ProcedureReturn nvcFail(#NEON_VK_CHROME_ERR_STATE) : EndIf
  If nvcRetroPipeline<>0 : ProcedureReturn #VK_SUCCESS : EndIf
  bytes=nvrBuildFragmentShader()
  ; The source is a completed composition, not another translucent primitive.
  rc=nvcCreateDrawPipelineBlend(bytes,#VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST,@nvcRetroPipeline,#VK_FALSE)
  If rc<>0 : ProcedureReturn nvcFail(rc) : EndIf
  ProcedureReturn #VK_SUCCESS
EndProcedure

; Composite the complete source canvas. Parameters are captured per draw;
; no shared uniform memory changes while recorded or pending draws use it.
Procedure.i NeonVkChromeRetroDrawId(id.i,x.i,y.i,width.i,height.i,timeBits.i)
  Protected setHandle.i,first.i,rc.i
  Protected Dim push.l[4]
  If nvcReady=0 Or nvcInFrame=0 Or nvcRetroPipeline=0 Or nvcMapped=0
    ProcedureReturn nvcFail(#NEON_VK_CHROME_ERR_STATE)
  EndIf
  If id<1 Or id>#NVC_MULTI_SPRITE_MAX Or width<1 Or height<1 Or (timeBits & $7F800000)=$7F800000
    ProcedureReturn nvcFail(#NEON_VK_CHROME_ERR_ARGS)
  EndIf
  If nvcGridBatchActive<>0 Or nvcBoxBatchActive<>0 Or nvcPathKind<>#NVC_PATH_NONE
    ProcedureReturn nvcFail(#NEON_VK_CHROME_ERR_STATE)
  EndIf
  setHandle=nvcImageSpriteSets[id]
  If id=1 : setHandle=nvcImageSpriteSet : EndIf
  If setHandle=0 : ProcedureReturn nvcFail(#NEON_VK_CHROME_ERR_STATE) : EndIf
  If nvcVertices+6>nvcMaxVertexQuads*6 Or nvcBudgetCan(1,1,6)=0
    ProcedureReturn nvcFail(#NEON_VK_CHROME_ERR_CAPACITY)
  EndIf
  rc=nvcDrawState($FFFFFFFF,setHandle,nvcPipelineLayout)
  If rc<>0 : ProcedureReturn rc : EndIf
  first=nvcVertices
  nvcQuad(first,x,y,x+width,y+height,0,0,#NEON_VK_CHROME_F_ONE,#NEON_VK_CHROME_F_ONE)
  nvcVertices=nvcVertices+6 : nvcBudgetVertices(1,6)
  push[0]=timeBits : push[1]=$3F800000 : push[2]=$3C75C28F : push[3]=0
  vkCmdBindPipeline(nvcCommand,#VK_PIPELINE_BIND_POINT_GRAPHICS,nvcRetroPipeline)
  vkCmdPushConstants(nvcCommand,nvcPipelineLayout,#VK_SHADER_STAGE_FRAGMENT_BIT,0,16,@push[0])
  vkCmdDraw(nvcCommand,6,1,first,0)
  vkCmdBindPipeline(nvcCommand,#VK_PIPELINE_BIND_POINT_GRAPHICS,nvcPipeline)
  nvcDrawCount=nvcDrawCount+1 : nvcTexDraws=nvcTexDraws+1
  ProcedureReturn #VK_SUCCESS
EndProcedure

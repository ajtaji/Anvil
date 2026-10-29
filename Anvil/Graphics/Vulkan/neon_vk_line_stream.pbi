; Compact exact-corner line stream over public Vulkan. Included after
; Chrome's coordinate conversion and draw-state helpers.
; A record is four clip X values followed by four clip Y values (32 bytes).
; One-hot vertex weights select the exact corners, preserving quad coverage.
Global nvcLinePipeline.i, nvcLineLayout.i
Global nvcLineSelector.i, nvcLineSelectorMemory.i
Global Dim nvcLineVs.l[512]

Procedure.i nvcLineBuildVertexShader()
  vtpBuf = @nvcLineVs[0] : vtpHeader(100)
  vtpIns(#VTP_OpCapability, 1) : vtpW(1)
  vtpIns(#VTP_OpMemoryModel, 2) : vtpW(0) : vtpW(1)
  vtpIns(#VTP_OpEntryPoint, 8) : vtpW(0) : vtpW(30) : vtpW($6E69616D) : vtpW(0) : vtpW(20) : vtpW(21) : vtpW(22) : vtpW(23)
  vtpIns(#VTP_OpMemberDecorate, 4) : vtpW(8) : vtpW(0) : vtpW(11) : vtpW(0)
  vtpIns(#VTP_OpDecorate, 2) : vtpW(8) : vtpW(2)
  vtpIns(#VTP_OpDecorate, 3) : vtpW(20) : vtpW(30) : vtpW(0)
  vtpIns(#VTP_OpDecorate, 3) : vtpW(21) : vtpW(30) : vtpW(1)
  vtpIns(#VTP_OpDecorate, 3) : vtpW(22) : vtpW(30) : vtpW(2)
  vtpIns(#VTP_OpTypeVoid, 1) : vtpW(1)
  vtpIns(#VTP_OpTypeFunction, 2) : vtpW(2) : vtpW(1)
  vtpIns(#VTP_OpTypeFloat, 2) : vtpW(3) : vtpW(32)
  vtpIns(#VTP_OpTypeVector, 3) : vtpW(4) : vtpW(3) : vtpW(4)
  vtpIns(#VTP_OpTypePointer, 3) : vtpW(5) : vtpW(1) : vtpW(4)
  vtpIns(#VTP_OpTypeStruct, 2) : vtpW(8) : vtpW(4)
  vtpIns(#VTP_OpTypePointer, 3) : vtpW(9) : vtpW(3) : vtpW(8)
  vtpIns(#VTP_OpTypePointer, 3) : vtpW(10) : vtpW(3) : vtpW(4)
  vtpIns(#VTP_OpTypeInt, 3) : vtpW(11) : vtpW(32) : vtpW(1)
  vtpIns(#VTP_OpConstant, 3) : vtpW(11) : vtpW(12) : vtpW(0)
  vtpIns(#VTP_OpConstant, 3) : vtpW(3) : vtpW(13) : vtpW(0)
  vtpIns(#VTP_OpConstant, 3) : vtpW(3) : vtpW(14) : vtpW($3F800000)
  vtpIns(#VTP_OpVariable, 3) : vtpW(5) : vtpW(20) : vtpW(1)
  vtpIns(#VTP_OpVariable, 3) : vtpW(5) : vtpW(21) : vtpW(1)
  vtpIns(#VTP_OpVariable, 3) : vtpW(5) : vtpW(22) : vtpW(1)
  vtpIns(#VTP_OpVariable, 3) : vtpW(9) : vtpW(23) : vtpW(3)
  vtpIns(#VTP_OpFunction, 4) : vtpW(1) : vtpW(30) : vtpW(0) : vtpW(2)
  vtpIns(#VTP_OpLabel, 1) : vtpW(31)
  vtpIns(#VTP_OpLoad, 3) : vtpW(4) : vtpW(32) : vtpW(20)
  vtpIns(#VTP_OpLoad, 3) : vtpW(4) : vtpW(33) : vtpW(21)
  vtpIns(#VTP_OpLoad, 3) : vtpW(4) : vtpW(34) : vtpW(22)
  vtpIns(#VTP_OpCompositeExtract, 4) : vtpW(3) : vtpW(40) : vtpW(32) : vtpW(0)
  vtpIns(#VTP_OpCompositeExtract, 4) : vtpW(3) : vtpW(41) : vtpW(32) : vtpW(1)
  vtpIns(#VTP_OpCompositeExtract, 4) : vtpW(3) : vtpW(42) : vtpW(32) : vtpW(2)
  vtpIns(#VTP_OpCompositeExtract, 4) : vtpW(3) : vtpW(43) : vtpW(32) : vtpW(3)
  vtpIns(#VTP_OpCompositeExtract, 4) : vtpW(3) : vtpW(44) : vtpW(33) : vtpW(0)
  vtpIns(#VTP_OpCompositeExtract, 4) : vtpW(3) : vtpW(45) : vtpW(33) : vtpW(1)
  vtpIns(#VTP_OpCompositeExtract, 4) : vtpW(3) : vtpW(46) : vtpW(33) : vtpW(2)
  vtpIns(#VTP_OpCompositeExtract, 4) : vtpW(3) : vtpW(47) : vtpW(33) : vtpW(3)
  vtpIns(#VTP_OpCompositeExtract, 4) : vtpW(3) : vtpW(48) : vtpW(34) : vtpW(0)
  vtpIns(#VTP_OpCompositeExtract, 4) : vtpW(3) : vtpW(49) : vtpW(34) : vtpW(1)
  vtpIns(#VTP_OpCompositeExtract, 4) : vtpW(3) : vtpW(50) : vtpW(34) : vtpW(2)
  vtpIns(#VTP_OpCompositeExtract, 4) : vtpW(3) : vtpW(51) : vtpW(34) : vtpW(3)
  vtpIns(#VTP_OpFMul, 4) : vtpW(3) : vtpW(60) : vtpW(40) : vtpW(44)
  vtpIns(#VTP_OpFMul, 4) : vtpW(3) : vtpW(61) : vtpW(41) : vtpW(45)
  vtpIns(#VTP_OpFMul, 4) : vtpW(3) : vtpW(62) : vtpW(42) : vtpW(46)
  vtpIns(#VTP_OpFMul, 4) : vtpW(3) : vtpW(63) : vtpW(43) : vtpW(47)
  vtpIns(#VTP_OpFAdd, 4) : vtpW(3) : vtpW(70) : vtpW(60) : vtpW(61)
  vtpIns(#VTP_OpFAdd, 4) : vtpW(3) : vtpW(71) : vtpW(62) : vtpW(63)
  vtpIns(#VTP_OpFAdd, 4) : vtpW(3) : vtpW(72) : vtpW(70) : vtpW(71)
  vtpIns(#VTP_OpFMul, 4) : vtpW(3) : vtpW(64) : vtpW(40) : vtpW(48)
  vtpIns(#VTP_OpFMul, 4) : vtpW(3) : vtpW(65) : vtpW(41) : vtpW(49)
  vtpIns(#VTP_OpFMul, 4) : vtpW(3) : vtpW(66) : vtpW(42) : vtpW(50)
  vtpIns(#VTP_OpFMul, 4) : vtpW(3) : vtpW(67) : vtpW(43) : vtpW(51)
  vtpIns(#VTP_OpFAdd, 4) : vtpW(3) : vtpW(73) : vtpW(64) : vtpW(65)
  vtpIns(#VTP_OpFAdd, 4) : vtpW(3) : vtpW(74) : vtpW(66) : vtpW(67)
  vtpIns(#VTP_OpFAdd, 4) : vtpW(3) : vtpW(75) : vtpW(73) : vtpW(74)
  vtpIns(#VTP_OpCompositeConstruct, 6) : vtpW(4) : vtpW(80) : vtpW(72) : vtpW(75) : vtpW(13) : vtpW(14)
  vtpIns(#VTP_OpAccessChain, 4) : vtpW(10) : vtpW(81) : vtpW(23) : vtpW(12)
  vtpIns(#VTP_OpStore, 2) : vtpW(81) : vtpW(80)
  vtpIns(#VTP_OpReturn, 0)
  vtpIns(#VTP_OpFunctionEnd, 0)
  ProcedureReturn vtpN * 4
EndProcedure

Procedure.i nvcLineStreamCreate()
 Define pcr.VkPushConstantRange
 Define plci.VkPipelineLayoutCreateInfo
 Define k.i
  Define smci.VkShaderModuleCreateInfo
  Define Dim stages.VkPipelineShaderStageCreateInfo[2]
  Define Dim cbinding.VkVertexInputBindingDescription[2]
  Define Dim attrs.VkVertexInputAttributeDescription[3]
  Define vi.VkPipelineVertexInputStateCreateInfo
  Define ia.VkPipelineInputAssemblyStateCreateInfo
  Define vp.VkViewport
  Define vpstate.VkPipelineViewportStateCreateInfo
  Define rs.VkPipelineRasterizationStateCreateInfo
  Define ms.VkPipelineMultisampleStateCreateInfo
  Define cba.VkPipelineColorBlendAttachmentState
  Define cb.VkPipelineColorBlendStateCreateInfo
  Define dyn.VkPipelineDynamicStateCreateInfo
  ; VkDynamicState is a Vulkan enum (32 bits); native-width .i entries make
  ; the API's 4-byte walk read the high half of VIEWPORT twice.
  Dim dynStates.l[2]
  Define gp.VkGraphicsPipelineCreateInfo
  Define vs.i
  Define fs.i
  Define layoutArray.i
  Define mapped.i
  Define rc.i
  Define vsBytes.i
  Define fsBytes.i

  rc=nvcBufferCreate(64,#VK_BUFFER_USAGE_VERTEX_BUFFER_BIT,@nvcLineSelector,@nvcLineSelectorMemory)
  If rc<>0 : ProcedureReturn rc : EndIf
  rc=vkMapMemory(nvcDevice,nvcLineSelectorMemory,0,64,0,@mapped)
  If rc<>0 : ProcedureReturn rc : EndIf
  For k=0 To 15 : PokeL(mapped+k*4,0) : Next
  ; Strip order c1,c0,c2,c3 preserves the same two triangle regions.
  PokeL(mapped+4,$3F800000) : PokeL(mapped+16,$3F800000)
  PokeL(mapped+32+8,$3F800000) : PokeL(mapped+48+12,$3F800000)
  vkUnmapMemory(nvcDevice,nvcLineSelectorMemory)
  pcr\stageFlags=#VK_SHADER_STAGE_FRAGMENT_BIT : pcr\size=16
  plci\sType=#VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO
  plci\pushConstantRangeCount=1 : plci\pPushConstantRanges=@pcr
  rc=vkCreatePipelineLayout(nvcDevice,@plci,0,@nvcLineLayout)
  If rc<>0 : ProcedureReturn rc : EndIf
  vsBytes = nvcLineBuildVertexShader()
  fsBytes = vtpBuildFsA()
  smci\sType = #VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO
  smci\pCode = @nvcLineVs[0] : smci\codeSize = vsBytes
  rc = vkCreateShaderModule(nvcDevice, @smci, 0, @vs)
  If rc = #VK_SUCCESS
    smci\pCode = @vtpFsA[0] : smci\codeSize = fsBytes
    rc = vkCreateShaderModule(nvcDevice, @smci, 0, @fs)
  EndIf
  If rc <> #VK_SUCCESS
    If vs <> 0 : vkDestroyShaderModule(nvcDevice, vs, 0) : EndIf
    If fs <> 0 : vkDestroyShaderModule(nvcDevice, fs, 0) : EndIf
    ProcedureReturn rc
  EndIf

  stages[0]\sType = #VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO
  stages[0]\stage = #VK_SHADER_STAGE_VERTEX_BIT : stages[0]\module = vs
  stages[1]\sType = #VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO
  stages[1]\stage = #VK_SHADER_STAGE_FRAGMENT_BIT : stages[1]\module = fs
  cbinding[0]\binding=0 : cbinding[0]\stride=16 : cbinding[0]\inputRate=#VK_VERTEX_INPUT_RATE_VERTEX
  cbinding[1]\binding=1 : cbinding[1]\stride=32 : cbinding[1]\inputRate=#VK_VERTEX_INPUT_RATE_INSTANCE
  attrs[0]\location=0 : attrs[0]\binding=0 : attrs[0]\format=#VK_FORMAT_R32G32B32A32_SFLOAT
  attrs[1]\location=1 : attrs[1]\binding=1 : attrs[1]\format=#VK_FORMAT_R32G32B32A32_SFLOAT
  attrs[2]\location=2 : attrs[2]\binding=1 : attrs[2]\format=#VK_FORMAT_R32G32B32A32_SFLOAT : attrs[2]\offset=16
  vi\sType=#VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO
  vi\vertexBindingDescriptionCount=2 : vi\pVertexBindingDescriptions=@cbinding[0]
  vi\vertexAttributeDescriptionCount=3 : vi\pVertexAttributeDescriptions=@attrs[0]
  ia\sType = #VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO
  ia\topology = #VK_PRIMITIVE_TOPOLOGY_TRIANGLE_STRIP
  PokeL(@vp\width, GraphicsF32IntBits(nvcWidth))
  PokeL(@vp\height, GraphicsF32IntBits(nvcHeight))
  PokeL(@vp\maxDepth, #NEON_VK_CHROME_F_ONE)
  vpstate\sType = #VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO
  vpstate\viewportCount = 1 : vpstate\pViewports = @vp
  vpstate\scissorCount = 1 : vpstate\pScissors = 0
  dynStates[0] = #VK_DYNAMIC_STATE_VIEWPORT
  dynStates[1] = #VK_DYNAMIC_STATE_SCISSOR
  dyn\sType = #VK_STRUCTURE_TYPE_PIPELINE_DYNAMIC_STATE_CREATE_INFO
  dyn\dynamicStateCount = 2 : dyn\pDynamicStates = @dynStates[0]
  rs\sType = #VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO
  rs\polygonMode = #VK_POLYGON_MODE_FILL : rs\cullMode = #VK_CULL_MODE_NONE
  rs\frontFace = #VK_FRONT_FACE_COUNTER_CLOCKWISE
  PokeL(@rs\lineWidth, #NEON_VK_CHROME_F_ONE)
  ms\sType = #VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO
  ms\rasterizationSamples = #VK_SAMPLE_COUNT_1_BIT
  cba\blendEnable = #VK_TRUE
  cba\srcColorBlendFactor = #VK_BLEND_FACTOR_SRC_ALPHA
  cba\dstColorBlendFactor = #VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA
  cba\colorBlendOp = #VK_BLEND_OP_ADD
  cba\srcAlphaBlendFactor = #VK_BLEND_FACTOR_SRC_ALPHA
  cba\dstAlphaBlendFactor = #VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA
  cba\alphaBlendOp = #VK_BLEND_OP_ADD
  cba\colorWriteMask = #VK_COLOR_COMPONENT_R_BIT | #VK_COLOR_COMPONENT_G_BIT | #VK_COLOR_COMPONENT_B_BIT | #VK_COLOR_COMPONENT_A_BIT
  cb\sType = #VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO
  cb\attachmentCount = 1 : cb\pAttachments = @cba
  gp\sType = #VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO
  gp\stageCount = 2 : gp\pStages = @stages[0]
  gp\pVertexInputState = @vi : gp\pInputAssemblyState = @ia
  gp\pViewportState = @vpstate : gp\pRasterizationState = @rs
  gp\pMultisampleState = @ms : gp\pColorBlendState = @cb : gp\pDynamicState = @dyn
  gp\layout = nvcLineLayout : gp\renderPass = nvcRenderPass : gp\subpass = 0 : gp\basePipelineIndex = -1
  rc = vkCreateGraphicsPipelines(nvcDevice, 0, 1, @gp, 0, @nvcLinePipeline)
  vkDestroyShaderModule(nvcDevice, vs, 0)
  vkDestroyShaderModule(nvcDevice, fs, 0)
  ProcedureReturn rc
EndProcedure

Procedure nvcLineStreamRelease()
  If nvcLinePipeline <> 0 : vkDestroyPipeline(nvcDevice, nvcLinePipeline, 0) : EndIf
  If nvcLineLayout <> 0 : vkDestroyPipelineLayout(nvcDevice, nvcLineLayout, 0) : EndIf
  If nvcLineSelector <> 0 : vkDestroyBuffer(nvcDevice, nvcLineSelector, 0) : EndIf
  If nvcLineSelectorMemory <> 0 : vkFreeMemory(nvcDevice, nvcLineSelectorMemory, 0) : EndIf
  nvcLinePipeline = 0 : nvcLineLayout = 0 : nvcLineSelector = 0 : nvcLineSelectorMemory = 0
EndProcedure

Procedure nvcLineRecordAt(p.i, x.i, y.i, px.i, py.i)
  Define dx.i, dy.i, c0.i, c1.i, c2.i, c3.i
  dx = Abs(px - x) : dy = Abs(py - y)
  If dx = 0 And dy = 0
    c0 = nvcLinePos(x * 2, y * 2) : c1 = nvcLinePos(x * 2 + 2, y * 2)
    c2 = nvcLinePos(x * 2 + 2, y * 2 + 2) : c3 = nvcLinePos(x * 2, y * 2 + 2)
  ElseIf dx >= dy
    c0 = nvcLinePos(x * 2, y * 2) : c1 = nvcLinePos(px * 2, py * 2)
    c2 = nvcLinePos(px * 2, py * 2 + 2) : c3 = nvcLinePos(x * 2, y * 2 + 2)
  Else
    c0 = nvcLinePos(x * 2, y * 2) : c1 = nvcLinePos(px * 2, py * 2)
    c2 = nvcLinePos(px * 2 + 2, py * 2) : c3 = nvcLinePos(x * 2 + 2, y * 2)
  EndIf
  PokeL(p, c0) : PokeL(p + 4, c1) : PokeL(p + 8, c2) : PokeL(p + 12, c3)
  PokeL(p + 16, c0 >> 32) : PokeL(p + 20, c1 >> 32)
  PokeL(p + 24, c2 >> 32) : PokeL(p + 28, c3 >> 32)
EndProcedure

; The caller has reserved its complete storage range and logical draw.
; Buffer and pipeline state are restored before any later primitive records.
Procedure.i nvcLineStreamDraw(first.i, count.i, colour.i)
  Define Dim buffers.i[2]
  Define Dim offsets.i[2]
  Define rc.i
  buffers[0] = nvcLineSelector : buffers[1] = nvcVertexBuffer
  offsets[0] = 0 : offsets[1] = first * #NEON_VK_CHROME_VERTEX_BYTES
  vkCmdBindVertexBuffers(nvcCommand, 0, 2, @buffers[0], @offsets[0])
  vkCmdBindPipeline(nvcCommand, #VK_PIPELINE_BIND_POINT_GRAPHICS, nvcLinePipeline)
  rc = nvcDrawSetRawWithInstances(0, 4, colour, 0, nvcLineLayout, count)
  buffers[0] = nvcVertexBuffer : offsets[0] = 0
  vkCmdBindVertexBuffers(nvcCommand, 0, 1, @buffers[0], @offsets[0])
  vkCmdBindPipeline(nvcCommand, #VK_PIPELINE_BIND_POINT_GRAPHICS, nvcPipeline)
  If rc = 0 : nvcFlatDraws = nvcFlatDraws + 1 : EndIf
  ProcedureReturn rc
EndProcedure

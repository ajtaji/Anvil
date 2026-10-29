; Immutable indexed outlines share point corners with subsequent fan fills.
; Each point has four exact vec2 positions: base,+x,+y,+xy. Stable open-chain
; indices append; closing edges are immutable per geometry version. Repeated
; unchanged outlines reuse both ranges. Resources are lazy and device-owned.
Global nvcOutlineBuffer.i, nvcOutlineMemory.i, nvcOutlineMapped.i
Global nvcOutlineListPipeline.i, nvcOutlineFanPipeline.i
Global nvcOutlinePointCapacity.i, nvcOutlinePointBase.i
Global nvcOutlineTriangleBase.i, nvcOutlineClosingBase.i
Global nvcOutlinePointsUsed.i, nvcOutlineEdgesUsed.i, nvcOutlineClosingsUsed.i
Global nvcFanIndexedStart.i = -1
Global nvcFanIndexedCached.i, nvcFanIndexedEdgeStart.i
Global nvcFanIndexedClose.i = -1
Global nvcFanIndexedCloseCount.i
; Direct no-fan fills need one ordinary vertex per point and three indices
; per triangle. Do not allocate the four-corner outline cache for this case.
Global nvcFanListBuffer.i, nvcFanListMemory.i, nvcFanListMapped.i
Global nvcFanListIndexCapacity.i, nvcFanListIndicesUsed.i

Procedure nvcFanListRelease()
  If nvcFanListMapped <> 0 : vkUnmapMemory(nvcDevice, nvcFanListMemory) : EndIf
  If nvcFanListBuffer <> 0 : vkDestroyBuffer(nvcDevice, nvcFanListBuffer, 0) : EndIf
  If nvcFanListMemory <> 0 : vkFreeMemory(nvcDevice, nvcFanListMemory, 0) : EndIf
  nvcFanListBuffer = 0 : nvcFanListMemory = 0 : nvcFanListMapped = 0
  nvcFanListIndexCapacity = 0 : nvcFanListIndicesUsed = 0
EndProcedure

Procedure.i nvcFanListDraw(colour.i)
  Define points.i, count.i, first.i, i.i, p.i, rc.i, buffer.i, offset.i
  points = nvcMaxVertexQuads * 6
  If points > #NEON_MAX_VERTS : points = #NEON_MAX_VERTS : EndIf
  count = (nvcPathCount - 2) * 3
  If nvcBoxBatchActive <> 0 : ProcedureReturn nvcFail(#NEON_VK_CHROME_ERR_STATE) : EndIf
  If nvcBudgetCan(0, 1, 0) = 0 Or nvcDrawCount >= nvcMaxQuads Or avkRecordedDrawFreeCount < 1 Or nvcPathCount > nvcMaxVertexQuads * 6 - nvcVertices Or count > points * 3 - nvcFanListIndicesUsed
    ProcedureReturn nvcFail(#NEON_VK_CHROME_ERR_CAPACITY)
  EndIf
  If nvcFanListBuffer = 0
    rc = nvcBufferCreate(points * 12, #VK_BUFFER_USAGE_INDEX_BUFFER_BIT, @nvcFanListBuffer, @nvcFanListMemory)
    If rc = #VK_SUCCESS : rc = vkMapMemory(nvcDevice, nvcFanListMemory, 0, points * 12, 0, @nvcFanListMapped) : EndIf
    If rc <> #VK_SUCCESS
      nvcFanListRelease()
      ProcedureReturn nvcFail(rc)
    EndIf
    nvcFanListIndexCapacity = points * 3
  EndIf
  rc = nvcDrawState(colour, nvcDescriptorSet, nvcPipelineLayout)
  If rc <> 0 : ProcedureReturn rc : EndIf
  first = nvcVertices
  For i = 0 To nvcPathCount - 1
    nvcVertex(first + i, nvcPathX[i], nvcPathY[i], nvcWhiteU0, nvcWhiteV0)
  Next
  p = nvcFanListMapped + nvcFanListIndicesUsed * 4
  For i = 1 To nvcPathCount - 2
    PokeL(p, first) : PokeL(p + 4, first + i) : PokeL(p + 8, first + i + 1)
    p = p + 12
  Next
  buffer = nvcVertexBuffer : offset = 0
  vkCmdBindVertexBuffers(nvcCommand, 0, 1, @buffer, @offset)
  vkCmdBindPipeline(nvcCommand, #VK_PIPELINE_BIND_POINT_GRAPHICS, nvcPipeline)
  vkCmdBindIndexBuffer(nvcCommand, nvcFanListBuffer, 0, #VK_INDEX_TYPE_UINT32)
  vkCmdDrawIndexed(nvcCommand, count, 1, nvcFanListIndicesUsed, 0, 0)
  nvcVertices = nvcVertices + nvcPathCount
  nvcFanListIndicesUsed = nvcFanListIndicesUsed + count
  nvcDrawCount = nvcDrawCount + 1 : nvcFlatDraws = nvcFlatDraws + 1
  ProcedureReturn #NEON_VK_CHROME_OK
EndProcedure

Procedure nvcOutlinePathReset()
  nvcFanIndexedStart = -1 : nvcFanIndexedCached = 0
  nvcFanIndexedEdgeStart = 0 : nvcFanIndexedClose = -1 : nvcFanIndexedCloseCount = 0
EndProcedure

Procedure nvcOutlineResetFrame()
  nvcFanListIndicesUsed = 0
  nvcOutlinePointsUsed = 0 : nvcOutlineEdgesUsed = 0 : nvcOutlineClosingsUsed = 0
  nvcOutlinePathReset()
EndProcedure

Procedure nvcOutlineRelease()
  nvcFanListRelease()
  If nvcOutlineListPipeline <> 0 : vkDestroyPipeline(nvcDevice, nvcOutlineListPipeline, 0) : EndIf
  If nvcOutlineFanPipeline <> 0 : vkDestroyPipeline(nvcDevice, nvcOutlineFanPipeline, 0) : EndIf
  If nvcOutlineMapped <> 0 : vkUnmapMemory(nvcDevice, nvcOutlineMemory) : EndIf
  If nvcOutlineBuffer <> 0 : vkDestroyBuffer(nvcDevice, nvcOutlineBuffer, 0) : EndIf
  If nvcOutlineMemory <> 0 : vkFreeMemory(nvcDevice, nvcOutlineMemory, 0) : EndIf
  nvcOutlineListPipeline = 0 : nvcOutlineFanPipeline = 0
  nvcOutlineBuffer = 0 : nvcOutlineMemory = 0 : nvcOutlineMapped = 0
  nvcOutlinePointCapacity = 0 : nvcOutlinePointBase = 0
  nvcOutlineTriangleBase = 0 : nvcOutlineClosingBase = 0
  nvcOutlineResetFrame()
EndProcedure

Procedure.i nvcOutlinePointLimit()
  Define points.i
  points = (nvcMaxVertexQuads * 6 * #NEON_VK_CHROME_VERTEX_BYTES) / 32
  If points > #NEON_MAX_VERTS : points = #NEON_MAX_VERTS : EndIf
  ProcedureReturn points
EndProcedure

Procedure.i nvcOutlinePipelinesCreate()
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

  vsBytes = vtpBuildVsA()
  fsBytes = vtpBuildFsA()
  smci\sType = #VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO
  smci\pCode = @vtpVsA[0] : smci\codeSize = vsBytes
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
  cbinding[0]\binding=0 : cbinding[0]\stride=8 : cbinding[0]\inputRate=#VK_VERTEX_INPUT_RATE_VERTEX
  cbinding[1]\binding=1 : cbinding[1]\stride=32 : cbinding[1]\inputRate=#VK_VERTEX_INPUT_RATE_INSTANCE
  attrs[0]\location=0 : attrs[0]\binding=0 : attrs[0]\format=#VK_FORMAT_R32G32_SFLOAT
  attrs[1]\location=1 : attrs[1]\binding=1 : attrs[1]\format=#VK_FORMAT_R32G32B32A32_SFLOAT
  attrs[2]\location=2 : attrs[2]\binding=1 : attrs[2]\format=#VK_FORMAT_R32G32B32A32_SFLOAT : attrs[2]\offset=16
  vi\sType=#VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO
  vi\vertexBindingDescriptionCount=1 : vi\pVertexBindingDescriptions=@cbinding[0]
  vi\vertexAttributeDescriptionCount=1 : vi\pVertexAttributeDescriptions=@attrs[0]
  ia\sType = #VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO
  ia\topology = #VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST
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
  rc = vkCreateGraphicsPipelines(nvcDevice, 0, 1, @gp, 0, @nvcOutlineListPipeline)
  If rc = #VK_SUCCESS And nvcFanPipeline <> 0
    ia\topology = #VK_PRIMITIVE_TOPOLOGY_TRIANGLE_FAN
    rc = vkCreateGraphicsPipelines(nvcDevice, 0, 1, @gp, 0, @nvcOutlineFanPipeline)
  EndIf
  vkDestroyShaderModule(nvcDevice, vs, 0)
  vkDestroyShaderModule(nvcDevice, fs, 0)
  ProcedureReturn rc
EndProcedure

Procedure.i nvcOutlineEnsure()
  Define points.i, pointBase.i, triangleBase.i, closingBase.i, bytes.i, rc.i
  If nvcOutlineBuffer <> 0 : ProcedureReturn #VK_SUCCESS : EndIf
  points = nvcOutlinePointLimit()
  If points < 2 : ProcedureReturn #NEON_VK_CHROME_ERR_CAPACITY : EndIf
  pointBase = points * 24 : triangleBase = pointBase + points * 4
  closingBase = triangleBase
  If nvcFanPipeline = 0 : closingBase = closingBase + points * 12 : EndIf
  bytes = closingBase + #NEON_MAX_DRAWS * 24
  rc = nvcBufferCreate(bytes, #VK_BUFFER_USAGE_INDEX_BUFFER_BIT, @nvcOutlineBuffer, @nvcOutlineMemory)
  If rc = #VK_SUCCESS : rc = vkMapMemory(nvcDevice, nvcOutlineMemory, 0, bytes, 0, @nvcOutlineMapped) : EndIf
  If rc = #VK_SUCCESS : rc = nvcOutlinePipelinesCreate() : EndIf
  If rc <> #VK_SUCCESS
    nvcOutlineRelease()
    ProcedureReturn rc
  EndIf
  nvcOutlinePointCapacity = points : nvcOutlinePointBase = pointBase
  nvcOutlineTriangleBase = triangleBase : nvcOutlineClosingBase = closingBase
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure nvcOutlineEdgeAt(p.i, x.i, y.i, px.i, py.i, a.i, b.i)
  Define axis.i
  If x = px And y = py
    PokeL(p, a) : PokeL(p + 4, a + 1) : PokeL(p + 8, a + 3)
    PokeL(p + 12, a) : PokeL(p + 16, a + 3) : PokeL(p + 20, a + 2)
  Else
    axis = 1 : If Abs(px - x) >= Abs(py - y) : axis = 2 : EndIf
    PokeL(p, a) : PokeL(p + 4, b) : PokeL(p + 8, b + axis)
    PokeL(p + 12, a) : PokeL(p + 16, b + axis) : PokeL(p + 20, a + axis)
  EndIf
EndProcedure

; Reserve all data and raw rows before resource preparation or mapped writes.
Procedure.i nvcOutlinePrepare(closing.i, rawRows.i)
  Define delta.i, needed.i, points.i, first.i, i.i, g.i, p.i, a.i, b.i, c.i, rc.i
  If nvcBoxBatchActive <> 0 : ProcedureReturn nvcFail(#NEON_VK_CHROME_ERR_STATE) : EndIf
  delta = nvcPathCount - nvcFanIndexedCached
  needed = (delta * 32 + #NEON_VK_CHROME_VERTEX_BYTES - 1) / #NEON_VK_CHROME_VERTEX_BYTES
  points = nvcOutlinePointLimit()
  If delta < 0 Or nvcBudgetCan(0, 1, 0) = 0 Or rawRows > nvcMaxQuads - nvcDrawCount Or rawRows > avkRecordedDrawFreeCount Or needed > nvcMaxVertexQuads * 6 - nvcVertices Or delta > points - nvcOutlinePointsUsed
    ProcedureReturn nvcFail(#NEON_VK_CHROME_ERR_CAPACITY)
  EndIf
  If closing <> 0 And nvcFanIndexedCloseCount <> nvcPathCount And nvcOutlineClosingsUsed >= #NEON_MAX_DRAWS
    ProcedureReturn nvcFail(#NEON_VK_CHROME_ERR_CAPACITY)
  EndIf
  rc = nvcOutlineEnsure()
  If rc <> #VK_SUCCESS : ProcedureReturn nvcFail(rc) : EndIf
  If nvcFanIndexedStart < 0
    nvcFanIndexedStart = nvcOutlinePointsUsed
    nvcFanIndexedEdgeStart = nvcOutlineEdgesUsed
  EndIf
  first = nvcVertices
  For i = nvcFanIndexedCached To nvcPathCount - 1
    g = nvcFanIndexedStart + i
    p = nvcMapped + first * #NEON_VK_CHROME_VERTEX_BYTES + (i - nvcFanIndexedCached) * 32
    b = (first * #NEON_VK_CHROME_VERTEX_BYTES + (i - nvcFanIndexedCached) * 32) / 8
    PokeI(p, nvcLinePos(nvcPathX[i] * 2, nvcPathY[i] * 2))
    PokeI(p + 8, nvcLinePos(nvcPathX[i] * 2 + 2, nvcPathY[i] * 2))
    PokeI(p + 16, nvcLinePos(nvcPathX[i] * 2, nvcPathY[i] * 2 + 2))
    PokeI(p + 24, nvcLinePos(nvcPathX[i] * 2 + 2, nvcPathY[i] * 2 + 2))
    PokeL(nvcOutlineMapped + nvcOutlinePointBase + g * 4, b)
    If i > 0
      a = PeekL(nvcOutlineMapped + nvcOutlinePointBase + (g - 1) * 4)
      nvcOutlineEdgeAt(nvcOutlineMapped + nvcOutlineEdgesUsed * 24, nvcPathX[i - 1], nvcPathY[i - 1], nvcPathX[i], nvcPathY[i], a, b)
      nvcOutlineEdgesUsed = nvcOutlineEdgesUsed + 1
      If i > 1 And nvcFanPipeline = 0
        c = PeekL(nvcOutlineMapped + nvcOutlinePointBase + nvcFanIndexedStart * 4)
        p = nvcOutlineMapped + nvcOutlineTriangleBase + g * 12
        PokeL(p, c) : PokeL(p + 4, a) : PokeL(p + 8, b)
      EndIf
    EndIf
  Next
  nvcOutlinePointsUsed = nvcOutlinePointsUsed + delta
  nvcVertices = nvcVertices + needed : nvcFanIndexedCached = nvcPathCount
  If closing <> 0 And nvcFanIndexedCloseCount <> nvcPathCount
    i = nvcPathCount - 1
    a = PeekL(nvcOutlineMapped + nvcOutlinePointBase + (nvcFanIndexedStart + i) * 4)
    b = PeekL(nvcOutlineMapped + nvcOutlinePointBase + nvcFanIndexedStart * 4)
    p = nvcOutlineMapped + nvcOutlineClosingBase + nvcOutlineClosingsUsed * 24
    nvcOutlineEdgeAt(p, nvcPathX[i], nvcPathY[i], nvcPathX[0], nvcPathY[0], a, b)
    nvcFanIndexedClose = nvcOutlineClosingBase / 4 + nvcOutlineClosingsUsed * 6
    nvcFanIndexedCloseCount = nvcPathCount : nvcOutlineClosingsUsed = nvcOutlineClosingsUsed + 1
  EndIf
  ProcedureReturn #NEON_VK_CHROME_OK
EndProcedure

Procedure.i nvcOutlineDrawRange(first.i, count.i, colour.i)
  Define rc.i
  rc = nvcDrawState(colour, 0, nvcLineLayout)
  If rc <> 0 : ProcedureReturn rc : EndIf
  vkCmdDrawIndexed(nvcCommand, count, 1, first, 0, 0)
  nvcDrawCount = nvcDrawCount + 1
  ProcedureReturn #NEON_VK_CHROME_OK
EndProcedure

Procedure.i nvcOutlineDraw(colour.i, filled.i)
  Define first.i, count.i, rc.i, rows.i, buffer.i, offset.i
  rows = 1 : If filled = 0 : rows = 2 : EndIf
  rc = nvcOutlinePrepare(1 - filled, rows)
  If rc <> 0 : ProcedureReturn rc : EndIf
  buffer = nvcVertexBuffer : offset = 0
  vkCmdBindVertexBuffers(nvcCommand, 0, 1, @buffer, @offset)
  vkCmdBindIndexBuffer(nvcCommand, nvcOutlineBuffer, 0, #VK_INDEX_TYPE_UINT32)
  vkCmdBindPipeline(nvcCommand, #VK_PIPELINE_BIND_POINT_GRAPHICS, nvcOutlineListPipeline)
  If filled = 0
    rc = nvcOutlineDrawRange(nvcFanIndexedEdgeStart * 6, (nvcPathCount - 1) * 6, colour)
    If rc = 0 : rc = nvcOutlineDrawRange(nvcFanIndexedClose, 6, colour) : EndIf
  Else
    first = nvcOutlineTriangleBase / 4 + (nvcFanIndexedStart + 2) * 3
    count = (nvcPathCount - 2) * 3
    If nvcOutlineFanPipeline <> 0
      vkCmdBindPipeline(nvcCommand, #VK_PIPELINE_BIND_POINT_GRAPHICS, nvcOutlineFanPipeline)
      first = nvcOutlinePointBase / 4 + nvcFanIndexedStart : count = nvcPathCount
    EndIf
    rc = nvcOutlineDrawRange(first, count, colour)
  EndIf
  vkCmdBindPipeline(nvcCommand, #VK_PIPELINE_BIND_POINT_GRAPHICS, nvcPipeline)
  If rc = 0 : nvcFlatDraws = nvcFlatDraws + 1 : EndIf
  ProcedureReturn rc
EndProcedure

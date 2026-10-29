; Current production geometry with controlled Vulkan recording/allocation.
; Real position/record/index writers use the shared numeric converter.
; Pipeline creation, mapped storage and draw calls are finite providers, not
; a GPU implementation. Case reset is not production recovery.
XIncludeFile "Anvil/Graphics/float_bits.pbi"
#NVG_REPORT = 0
#NVG_REPORT_BYTES = 32768
; @GEOMETRY_DECLARATIONS@
Global nvgChecks.i,nvgFailures.i,nvgFirstFailure.i,nvgProviderFault.i
Global nvgRecords.i,nvgPipeline.i,nvgVertex0.i,nvgVertex1.i,nvgOffset0.i,nvgOffset1.i,nvgIndexBuffer.i,nvgColour.i
Global nvgCreates.i,nvgMaps.i,nvgPipelineCreates.i,nvgBufferDestroys.i,nvgFrees.i
Global nvgCreateRc.i,nvgMapRc.i,nvgPipelineRc.i,nvgDrawStateRc.i
Global Dim nvgVertex.a[4224]
Global Dim nvgIndex.a[131200]
Global Dim nvgRecord.i[768]
Procedure NvgCheck(value.i,wanted.i)
 If nvgChecks >= (#NVG_REPORT_BYTES-64)/16 : nvgFirstFailure=99999 : ProcedureReturn : EndIf
 nvgChecks=nvgChecks+1
 If #NVG_REPORT <> 0
  PokeI(#NVG_REPORT+64+(nvgChecks-1)*16,nvgChecks)
  PokeI(#NVG_REPORT+72+(nvgChecks-1)*16,value)
 EndIf
 If value<>wanted
  nvgFailures=nvgFailures+1
  If nvgFirstFailure=0 : nvgFirstFailure=nvgChecks : EndIf
 EndIf
EndProcedure
Procedure NvgRecordDraw(kind.i,first.i,count.i,instances.i)
 Define p.i
 If nvgRecords>=64 : nvgProviderFault=1 : ProcedureReturn : EndIf
 p=nvgRecords*12
 nvgRecord[p]=kind : nvgRecord[p+1]=first : nvgRecord[p+2]=count : nvgRecord[p+3]=instances
 nvgRecord[p+4]=nvgPipeline : nvgRecord[p+5]=nvgVertex0 : nvgRecord[p+6]=nvgVertex1
 nvgRecord[p+7]=nvgOffset0 : nvgRecord[p+8]=nvgOffset1 : nvgRecord[p+9]=nvgIndexBuffer
 nvgRecord[p+10]=nvgColour : nvgRecord[p+11]=nvcCommand
 nvgRecords=nvgRecords+1 : avkRecordedDrawFreeCount=avkRecordedDrawFreeCount-1
EndProcedure
; Real position transforms, controlled cache misses with the shared converter.
; Cache population itself requires separate coverage.
Procedure.i nvcClipXBits2(x.i)
 ProcedureReturn GraphicsF32RatioBits(x-nvcPhysicalW,nvcPhysicalW)
EndProcedure
Procedure.i nvcClipYBits2(y.i)
 ProcedureReturn GraphicsF32RatioBits(y-nvcPhysicalH,nvcPhysicalH)
EndProcedure
Procedure.i nvcBufferCreate(bytes.i,usage.i,*buffer,*memory)
 nvgCreates=nvgCreates+1
 If bytes<1 Or bytes>131072 Or usage<>#VK_BUFFER_USAGE_INDEX_BUFFER_BIT : nvgProviderFault=1 : ProcedureReturn -2 : EndIf
 If nvgCreateRc<>0 : ProcedureReturn nvgCreateRc : EndIf
 PokeI(*buffer,501) : PokeI(*memory,502) : ProcedureReturn #VK_SUCCESS
EndProcedure
Procedure.i vkMapMemory(device.i,memory.i,offset.i,bytes.i,flags.i,*mapped)
 nvgMaps=nvgMaps+1
 If device<>88 Or memory<>502 Or offset<>0 Or bytes<1 Or bytes>131072 Or flags<>0 : nvgProviderFault=1 : ProcedureReturn -5 : EndIf
 If nvgMapRc<>0 : ProcedureReturn nvgMapRc : EndIf
 PokeI(*mapped,@nvgIndex[64]) : ProcedureReturn #VK_SUCCESS
EndProcedure
Procedure.i nvcOutlinePipelinesCreate()
 nvgPipelineCreates=nvgPipelineCreates+1
 If nvgPipelineRc<>0 : ProcedureReturn nvgPipelineRc : EndIf
 nvcOutlineListPipeline=601
 If nvcFanPipeline<>0 : nvcOutlineFanPipeline=602 : EndIf
 ProcedureReturn #VK_SUCCESS
EndProcedure
Procedure vkUnmapMemory(device.i,memory.i) : EndProcedure
Procedure vkDestroyPipeline(device.i,pipeline.i,alloc.i) : EndProcedure
Procedure vkDestroyBuffer(device.i,buffer.i,alloc.i) : nvgBufferDestroys=nvgBufferDestroys+1 : EndProcedure
Procedure vkFreeMemory(device.i,memory.i,alloc.i) : nvgFrees=nvgFrees+1 : EndProcedure
Procedure vkCmdBindVertexBuffers(command.i,first.i,count.i,*buffers,*offsets)
 If command<>77 Or first<>0 Or count<1 Or count>2 : nvgProviderFault=1 : ProcedureReturn : EndIf
 nvgVertex0=PeekI(*buffers) : nvgOffset0=PeekI(*offsets)
 If count=2 : nvgVertex1=PeekI(*buffers+8) : nvgOffset1=PeekI(*offsets+8) : EndIf
EndProcedure
Procedure vkCmdBindPipeline(command.i,point.i,pipeline.i)
 If command<>77 Or point<>0 : nvgProviderFault=1 : EndIf
 nvgPipeline=pipeline
EndProcedure
Procedure vkCmdBindIndexBuffer(command.i,buffer.i,offset.i,kind.i)
 If command<>77 Or offset<>0 Or kind<>#VK_INDEX_TYPE_UINT32 : nvgProviderFault=1 : EndIf
 nvgIndexBuffer=buffer
EndProcedure
Procedure vkCmdDrawIndexed(command.i,count.i,instances.i,first.i,vertexOffset.i,firstInstance.i)
 If command<>77 Or vertexOffset<>0 Or firstInstance<>0 : nvgProviderFault=1 : EndIf
 NvgRecordDraw(1,first,count,instances)
EndProcedure
Procedure.i nvcDrawState(colour.i,set.i,layout.i)
 nvgColour=colour : ProcedureReturn nvgDrawStateRc
EndProcedure
Procedure.i nvcDraw(first.i,count.i,colour.i)
 nvgColour=colour : NvgRecordDraw(0,first,count,1)
 nvcDrawCount=nvcDrawCount+1 : nvcFlatDraws=nvcFlatDraws+1
 ProcedureReturn #VK_SUCCESS
EndProcedure
Procedure.i nvcDrawSetRawWithInstances(first.i,count.i,colour.i,set.i,layout.i,instances.i)
 nvgColour=colour : NvgRecordDraw(0,first,count,instances)
 nvcDrawCount=nvcDrawCount+1 : ProcedureReturn #VK_SUCCESS
EndProcedure
; @PRODUCTION_GEOMETRY@
; @GEOMETRY_RESET@
Procedure.i NvgGeometryContract()
 nvgChecks=0 : nvgFailures=0 : nvgFirstFailure=0
 ; @GEOMETRY_CASES@
 ProcedureReturn nvgFirstFailure
EndProcedure
Procedure.i Main()
 ProcedureReturn NvgGeometryContract()
EndProcedure

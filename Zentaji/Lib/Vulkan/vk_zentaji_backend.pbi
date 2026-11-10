; Native Zentaji Vulkan backend. Requires vk_api.pbi, prompt_idle.pbi and
; graphics_queue.pbi, explicitly included before this file by the composition.
; The boot owner supplies an already protected, permanently pinned RAM window.
; Its first page belongs to commands/fences; only later pages are Vulkan memory.
; Hardware completion orders coherent RAM writes before fences/status. No CPU
; pixel fallback is used. Draw uses typed-IR native shader lowering and the
; real ROM TEX2D sampler. Transfer remains absent. This backend does not own display.
#ANVIL_VULKAN_BACKEND_PRESENT=3
#AVK_ZEN_IMAGE_LAYOUT=3
#AVK_ZEN_DISPLAY=$FFFF0000000C0000
Global avkZenQueue.ZentajiGraphicsQueue
Global avkZenUp.i,avkZenHeapBase.i,avkZenHeapBytes.i,avkZenLease.i,avkZenPending.i,avkZenNativeError.i
Global avkZenListActive.i,avkZenListBase.i,avkZenListCount.i,avkZenListIndex.i
Global Dim avkZenCommand.q[8]

Procedure.i AnvilVkZentajiWindow(base.i,bytes.i)
 Protected ram.i=PeekQ($FFFF000000010018)
 If avkZenUp<>0 Or avkZenQueue\state<>0 : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
 If base<1 Or (base&4095)<>0 Or bytes<8192 Or (bytes&4095)<>0 Or base>ram Or bytes>ram-base : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
 If ZentajiGraphicsBind(@avkZenQueue,15,base,4096,base,2048,base+2048)=0 : ProcedureReturn #VK_ERROR_INITIALIZATION_FAILED : EndIf
 avkZenHeapBase=base+4096 : avkZenHeapBytes=bytes-4096 : avkZenUp=1
 ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkZenOffscreen(base.i,bytes.i)
 Protected n.i,buffer.i,pitch.i,height.i,span.i
 If (PeekQ(#AVK_ZEN_DISPLAY+$10)&1)=0 : ProcedureReturn 1 : EndIf
 pitch=PeekQ(#AVK_ZEN_DISPLAY+$70) : height=PeekQ(#AVK_ZEN_DISPLAY+$58)
 If pitch<1 Or height<1 Or height>$7FFFFFFFFFFFFFFF/pitch : ProcedureReturn 0 : EndIf
 span=pitch*height
 For n=0 To 2
  buffer=PeekQ(#AVK_ZEN_DISPLAY+$78+n*8)
  If buffer<0 Or buffer>avkZenQueue\ram : ProcedureReturn 0 : EndIf
  If span>avkZenQueue\ram-buffer : ProcedureReturn 0 : EndIf
  If buffer<>0 And buffer<=base+bytes-1 And (buffer>base Or span>base-buffer) : ProcedureReturn 0 : EndIf
 Next
 ProcedureReturn 1
EndProcedure

Procedure.i avkBackendCaps()
 If avkZenUp=0 Or avkZenQueue\lost<>0 : ProcedureReturn 0 : EndIf
 ProcedureReturn #ANVIL_VK_CAP_DEVICE | #ANVIL_VK_CAP_CLEAR_COLOR | #ANVIL_VK_CAP_GPU | #ANVIL_VK_CAP_DRAW | #ANVIL_VK_CAP_ATTACHMENT_LOAD | #ANVIL_VK_CAP_OPTIMAL_COLOR_ATTACHMENT | #ANVIL_VK_CAP_BLEND_ALPHA_ONE | #ANVIL_VK_CAP_DRAW_LIST | #ANVIL_VK_CAP_CLEAR_ATTACHMENT_RECT
EndProcedure

Procedure.i avkBackendName()
 ProcedureReturn "Zentaji native 3D command backend"
EndProcedure

Procedure.i avkBackendPrepare()
 If avkZenUp=0 Or ZentajiGraphicsOwned(@avkZenQueue)=0 : ProcedureReturn #VK_ERROR_INITIALIZATION_FAILED : EndIf
 ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkBackendComputeCanLower(*ir)
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendComputeScratchBytes()
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendSubmitCompute(*job.AnvilVkBackendComputeJob, *result.AnvilVkBackendComputeResult)
 ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_FEATURE_NOT_PRESENT)
EndProcedure

Procedure.i avkBackendGpuLeaseAcquire(owner.i)
 If (owner<>#ANVIL_VK_GPU_LEASE_QUEUE And owner<>#ANVIL_VK_GPU_LEASE_EXTERNAL) Or avkZenLease<>0 Or avkZenPending<>0 Or avkZenListActive<>0 Or avkZenQueue\state<>1 : ProcedureReturn 0 : EndIf
 If ZentajiGraphicsOwned(@avkZenQueue)=0 : ProcedureReturn 0 : EndIf
 avkZenLease=owner : ProcedureReturn 1
EndProcedure

Procedure.i avkBackendGpuLeaseRelease(owner.i)
 If owner<1 Or avkZenLease<>owner Or avkZenPending<>0 Or avkZenListActive<>0 Or avkZenQueue\state<>1 Or avkZenQueue\lost<>0 : ProcedureReturn 0 : EndIf
 If ZentajiGraphicsOwned(@avkZenQueue)=0 : ProcedureReturn 0 : EndIf
 avkZenLease=0 : ProcedureReturn 1
EndProcedure

Procedure.i avkBackendGpuLeaseQuarantine(owner.i)
 If owner<1 Or avkZenLease<>owner : ProcedureReturn 0 : EndIf
 avkZenLease=-owner : ProcedureReturn 1
EndProcedure

Procedure.i avkBackendGpuLeaseState()
 ProcedureReturn avkZenLease
EndProcedure

Procedure.i avkBackendGpuLeaseRequired()
 ProcedureReturn 1
EndProcedure

Procedure.i avkBackendHeapBase()
 ProcedureReturn avkZenHeapBase
EndProcedure

Procedure.i avkBackendHeapBytes()
 ProcedureReturn avkZenHeapBytes
EndProcedure

Procedure.i avkBackendMemoryTypeCount()
 ProcedureReturn Bool(avkZenUp<>0)
EndProcedure

Procedure.i avkBackendMemoryTypeFlags(index.i)
 If index<>0 Or avkZenUp=0 : ProcedureReturn 0 : EndIf
 ProcedureReturn #VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT | #VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | #VK_MEMORY_PROPERTY_HOST_COHERENT_BIT
EndProcedure

Procedure.i avkBackendMemoryTypeHeap(index.i)
 ProcedureReturn 0
EndProcedure

Procedure.i avkBackendHeapCount()
 ProcedureReturn Bool(avkZenUp<>0)
EndProcedure

Procedure.i avkBackendHeapSizeOf(index.i)
 If index<>0 : ProcedureReturn 0 : EndIf
 ProcedureReturn avkZenHeapBytes
EndProcedure

Procedure.i avkBackendHeapFlagsOf(index.i)
 If index<>0 Or avkZenUp=0 : ProcedureReturn 0 : EndIf
 ProcedureReturn #VK_MEMORY_HEAP_DEVICE_LOCAL_BIT
EndProcedure

Procedure.i avkBackendImageAlignment()
  ProcedureReturn 4096
EndProcedure

Procedure.i avkBackendImageCopySourceAlignment()
  ProcedureReturn 1
EndProcedure

Procedure.i avkBackendRowPitchFor(width.i)
 If width<1 Or width>16384 : ProcedureReturn 0 : EndIf
 ProcedureReturn width*4
EndProcedure

Procedure.i avkBackendMaxImageDimension2D()
 ProcedureReturn 16384
EndProcedure

Procedure avkBackendRenderAreaGranularity(*out.VkExtent2D)
  *out\width = 1
  *out\height = 1
EndProcedure

Procedure.i avkBackendSampledMaxDimension2D(tiling.i)
  If tiling=#VK_IMAGE_TILING_LINEAR Or tiling=#VK_IMAGE_TILING_OPTIMAL : ProcedureReturn 16384 : EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendImagePlan(width.i, height.i, format.i, tiling.i, usage.i, *plan.AnvilVkBackendImagePlan)
 If *plan=0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
 *plan\bytes=0 : *plan\alignment=0 : *plan\rowPitch=0
 *plan\backendLayout=0 : *plan\paddedWidth=0 : *plan\paddedHeight=0
 If width<1 Or height<1 Or width>16384 Or height>16384 Or format<>#VK_FORMAT_B8G8R8A8_UNORM : ProcedureReturn #VK_ERROR_FORMAT_NOT_SUPPORTED : EndIf
 If tiling<>#VK_IMAGE_TILING_LINEAR And tiling<>#VK_IMAGE_TILING_OPTIMAL : ProcedureReturn #VK_ERROR_FORMAT_NOT_SUPPORTED : EndIf
 If (usage&~(#VK_IMAGE_USAGE_TRANSFER_DST_BIT|#VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT|#VK_IMAGE_USAGE_SAMPLED_BIT))<>0 : ProcedureReturn #VK_ERROR_FORMAT_NOT_SUPPORTED : EndIf
 *plan\bytes=width*height*4 : *plan\alignment=4096
 *plan\paddedWidth=width : *plan\paddedHeight=height
 If tiling=#VK_IMAGE_TILING_LINEAR
  *plan\rowPitch=width*4
 Else
  *plan\backendLayout=#AVK_ZEN_IMAGE_LAYOUT
 EndIf
 ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkBackendImageCopyValidate(*copy.AnvilVkBackendImageCopy)
    ProcedureReturn -1
  EndProcedure

Procedure.i avkBackendImageCopyBatchReady()
    ProcedureReturn 0
  EndProcedure

Procedure.i avkBackendSubmitImageCopy(*copy.AnvilVkBackendImageCopy)
 ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_FEATURE_NOT_PRESENT)
EndProcedure

Procedure.i avkBackendTiledImageCopyValidate(*copy.AnvilVkBackendTiledImageCopy)
    ProcedureReturn -1
  EndProcedure

Procedure.i avkBackendSubmitTiledImageCopy(*copy.AnvilVkBackendTiledImageCopy)
 ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_FEATURE_NOT_PRESENT)
EndProcedure

Procedure.i avkBackendTiledRectCopyValidate(*copy.AnvilVkBackendTiledRectCopy)
    ProcedureReturn -1
  EndProcedure

Procedure.i avkBackendSubmitTiledRectCopy(*copy.AnvilVkBackendTiledRectCopy)
 ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_FEATURE_NOT_PRESENT)
EndProcedure

Procedure.i avkBackendTiledEdgeTailCopyValidate(*copy.AnvilVkBackendTiledRectCopy)
    ProcedureReturn -1
  EndProcedure

Procedure.i avkBackendSubmitTiledEdgeTailCopy(*copy.AnvilVkBackendTiledRectCopy)
 ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_FEATURE_NOT_PRESENT)
EndProcedure

Procedure.i avkBackendTiledMicroCopyValidate(*copy.AnvilVkBackendTiledRectCopy)
    ProcedureReturn -1
  EndProcedure

Procedure.i avkBackendSubmitTiledMicroCopy(*copy.AnvilVkBackendTiledRectCopy)
 ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_FEATURE_NOT_PRESENT)
EndProcedure

Procedure.i avkBackendLinearTiledRectCopyValidate(*copy.AnvilVkBackendLinearTiledRectCopy)
    ProcedureReturn -1
  EndProcedure

Procedure.i avkBackendSubmitLinearTiledRectCopy(*copy.AnvilVkBackendLinearTiledRectCopy)
 ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_FEATURE_NOT_PRESENT)
EndProcedure

Procedure.i avkBackendLinearTiledMicroCopyValidate(*copy.AnvilVkBackendLinearTiledRectCopy)
    ProcedureReturn -1
  EndProcedure

Procedure.i avkBackendSubmitLinearTiledMicroCopy(*copy.AnvilVkBackendLinearTiledRectCopy)
 ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_FEATURE_NOT_PRESENT)
EndProcedure

Procedure.i avkBackendLinearTiledGridCopyValidate(*copy.AnvilVkBackendLinearTiledRectCopy)
    ProcedureReturn -1
  EndProcedure

Procedure.i avkBackendSubmitLinearTiledGridCopy(*copy.AnvilVkBackendLinearTiledRectCopy)
 ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_FEATURE_NOT_PRESENT)
EndProcedure

Procedure.i avkBackendTiledReadbackValidate(*copy.AnvilVkBackendTiledReadback)
    ProcedureReturn -1
  EndProcedure

Procedure.i avkBackendSubmitTiledReadback(*copy.AnvilVkBackendTiledReadback)
 ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_FEATURE_NOT_PRESENT)
EndProcedure

Procedure.i avkBackendTiledMicroReadbackValidate(*copy.AnvilVkBackendTiledReadback)
    ProcedureReturn -1
  EndProcedure

Procedure.i avkBackendSubmitTiledMicroReadback(*copy.AnvilVkBackendTiledReadback)
 ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_FEATURE_NOT_PRESENT)
EndProcedure

Procedure.i avkBackendSubmitBufferCopy(source.i, destination.i, bytes.i)
 ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_FEATURE_NOT_PRESENT)
EndProcedure

Procedure.i avkBackendSubmitBufferCopyRows(source.i, sourcePitch.i, destination.i, destinationPitch.i, rowBytes.i, rows.i)
 ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_FEATURE_NOT_PRESENT)
EndProcedure

Procedure.i avkBackendSubmitBufferFill(destination.i, bytes.i, data.i)
 ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_FEATURE_NOT_PRESENT)
EndProcedure

Procedure.i avkBackendClearSupported(base.i, bytes.i, w.i, h.i, pitch.i)
 If pitch=0 : pitch=w*4 : EndIf
 If avkZenUp=0 Or avkZenQueue\lost<>0 : ProcedureReturn #VK_ERROR_DEVICE_LOST : EndIf
 If w<1 Or h<1 Or w>16384 Or h>16384 Or pitch<w*4 Or pitch>$FFFFFFFF Or (pitch&3)<>0 : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
 If bytes<1 Or bytes>avkZenHeapBytes Or base<avkZenHeapBase Or base>avkZenHeapBase+avkZenHeapBytes-bytes : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
 If h>bytes/pitch Or (base&4095)<>0 : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
 If avkZenOffscreen(base,bytes)=0 : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
 ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkBackendSubmitClear(base.i, bytes.i, w.i, h.i, pitch.i, bgra.i, loadColor.i)
 Protected n.i,result.i
 If pitch=0 : pitch=w*4 : EndIf
 result=avkBackendClearSupported(base,bytes,w,h,pitch)
 If result<>#VK_SUCCESS : ProcedureReturn avkBackendRefuseBeforeLaunch(result) : EndIf
 If (loadColor<>0 And loadColor<>1) Or avkZenLease<>#ANVIL_VK_GPU_LEASE_QUEUE Or avkZenPending<>0 Or avkZenQueue\state<>1
  ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_INITIALIZATION_FAILED)
 EndIf
 If ZentajiGraphicsBegin(@avkZenQueue)=0 : ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_DEVICE_LOST) : EndIf
 For n=0 To 7 : avkZenCommand[n]=0 : Next
 avkZenCommand[0]=1 : avkZenCommand[1]=base
 PokeL(@avkZenCommand[0]+16,pitch) : PokeW(@avkZenCommand[0]+20,w) : PokeW(@avkZenCommand[0]+22,h)
 PokeA(@avkZenCommand[0]+24,2)
 If ZentajiGraphicsAppend(@avkZenQueue,@avkZenCommand[0])=0 : ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_DEVICE_LOST) : EndIf
 ; Controller state survives submissions. Reset the full-target scissor
 ; before a load clear, even when a preceding draw installed a smaller one.
 For n=0 To 7 : avkZenCommand[n]=0 : Next
 avkZenCommand[0]=4 : PokeL(@avkZenCommand[0]+16,w) : PokeL(@avkZenCommand[0]+20,h)
 If ZentajiGraphicsAppend(@avkZenQueue,@avkZenCommand[0])=0 : ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_DEVICE_LOST) : EndIf
 If loadColor=0
  For n=0 To 7 : avkZenCommand[n]=0 : Next
  avkZenCommand[0]=$105 : PokeL(@avkZenCommand[0]+8,bgra)
  If ZentajiGraphicsAppend(@avkZenQueue,@avkZenCommand[0])=0 : ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_DEVICE_LOST) : EndIf
 EndIf
 If ZentajiGraphicsSubmit(@avkZenQueue)=0 : ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_DEVICE_LOST) : EndIf
 avkZenPending=1 : avkZenNativeError=0
 ProcedureReturn #ANVIL_VK_JOB_PENDING
EndProcedure

Procedure.i avkZenPollOne()
 Protected result.i
 If avkZenPending=0 : ProcedureReturn 1 : EndIf
 result=ZentajiGraphicsPoll(@avkZenQueue)
 If result=0 And HwPromptIdleReady()<>0
  HwPromptIdleWait()
  result=ZentajiGraphicsPoll(@avkZenQueue)
 EndIf
 If result<0
  avkZenNativeError=(avkZenQueue\error<<32)|(avkZenQueue\deviceStatus&$FFFFFFFF)
  If avkZenQueue\state=1 : avkZenPending=0 : EndIf
 ElseIf result>0
  avkZenPending=0 : avkZenNativeError=0
 EndIf
 ProcedureReturn result
EndProcedure

Procedure.i avkBackendLastNativeError()
 ProcedureReturn avkZenNativeError
EndProcedure

Procedure.i avkBackendTicksUs()
 ProcedureReturn HwMicros()
EndProcedure

XIncludeFile "Zentaji/Lib/Vulkan/vk_zentaji_draw.pbi"
XIncludeFile "Zentaji/Lib/Vulkan/vk_zentaji_list.pbi"

; Native Vulkan image -> managed private display plane. Include after vk_api,
; vk_zentaji_backend and backend_select; the composition starts the managed
; display outside the Vulkan heap BEFORE creating any resources.
; Begin pins both image and memory and takes the external GPU lease. Abort
; releases only an unsubmitted writer. Commit copies with native DMA and waits
; through the real display latch using timer/WFI. No CPU pixel fallback.
; Uncertain DMA/display retirement retains both pins and quarantines the lease
; until machine reset. This is not a swapchain or the resident Neon adapter.
XIncludeFile "Zentaji/Board/graphics_display.pbi"
Global avkZenPresentState.i,avkZenPresentImage.i,avkZenPresentMemory.i
Global avkZenPresentSource.i,avkZenPresentPitch.i,avkZenPresentToken.q

; Split the existing permanently protected arena before Vulkan heap discovery.
; Commands/fences retain its first page. Exactly the descriptor's two or three
; page-rounded display planes occupy its end; only the middle becomes the heap.
; A small arena is refused before writing any GPU, DMA or display register.
Procedure.i AnvilVkZentajiDisplayWindow()
 Protected w.i,h.i,span.i,buffers.i,displayBytes.i,windowBytes.i,base.i,rc.i
 If avkZenUp<>0 Or avkHeapReady<>0 Or avkZenPresentState<>0 Or zgdUp<>0 Or zgdLost<>0 : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
 If ZenCpuStatus()<>0 Or ZenCpuCoreId()<>0 Or zenMemoryGraphicsBase=0 Or zenMemoryGraphicsBytes<8192 : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
 buffers=ZentajiGraphicsDisplayBufferCount()
 If buffers=0 : ProcedureReturn #VK_ERROR_INITIALIZATION_FAILED : EndIf
 w=PeekQ(#ZEN_GFX_DISPLAY+$50) : h=PeekQ(#ZEN_GFX_DISPLAY+$58)
 If w<1 Or w>16384 Or h<1 Or h>16384 : ProcedureReturn #VK_ERROR_INITIALIZATION_FAILED : EndIf
 span=(w*h*4+4095)&-4096 : displayBytes=span*buffers
 If displayBytes>zenMemoryGraphicsBytes-8192 : ProcedureReturn #VK_ERROR_OUT_OF_DEVICE_MEMORY : EndIf
 windowBytes=zenMemoryGraphicsBytes-displayBytes : base=zenMemoryGraphicsBase+windowBytes
 If ZentajiGraphicsDisplayManagedStart(base)<>1 : ProcedureReturn #VK_ERROR_INITIALIZATION_FAILED : EndIf
 rc=AnvilVkZentajiWindow(zenMemoryGraphicsBase,windowBytes)
 If rc<>#VK_SUCCESS
  ; No copy was submitted; release only our admitted, still disabled display.
  ZentajiGraphicsDisplayRelease() : ProcedureReturn rc
 EndIf
 ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure avkZenPresentUnpin()
 avkImgInFlight[avkZenPresentImage]=avkImgInFlight[avkZenPresentImage]-1
 avkMemInFlight[avkZenPresentMemory]=avkMemInFlight[avkZenPresentMemory]-1
 avkZenPresentState=0 : avkZenPresentImage=0 : avkZenPresentMemory=0
 avkZenPresentSource=0 : avkZenPresentPitch=0 : avkZenPresentToken=0
EndProcedure

Procedure.q AnvilVkZentajiPresentBegin(image.i)
 Protected s.i,m.i,source.i,pitch.i,token.q
 If avkZenPresentState<>0 Or zgdManaged=0 Or ZentajiGraphicsDisplayOwned()=0 : ProcedureReturn 0 : EndIf
 ; Check the entire reserved display extent, including currently unshown planes.
 If zgdBase<avkZenHeapBase+avkZenHeapBytes And avkZenHeapBase<zgdBase+zgdSpan*zgdBuffers : ProcedureReturn 0 : EndIf
 s=avkImgSlot(image)
 If s=0 : ProcedureReturn 0 : EndIf
 If avkImgBound[s]=0 Or avkImgInFlight[s]<>0 Or avkImgFormat[s]<>#VK_FORMAT_B8G8R8A8_UNORM : ProcedureReturn 0 : EndIf
 If avkImgW[s]<>zgdWidth Or avkImgH[s]<>zgdHeight Or (avkImgUsage[s]&#VK_IMAGE_USAGE_TRANSFER_SRC_BIT)=0 : ProcedureReturn 0 : EndIf
 If avkImgLayout[s]<>#VK_IMAGE_LAYOUT_GENERAL And avkImgLayout[s]<>#VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL : ProcedureReturn 0 : EndIf
 If avkImgOwnerQf[s]<>#ANVIL_VK_QUEUE_FAMILY : ProcedureReturn 0 : EndIf
 m=avkImgMemSlot[s]
 If m<1 Or m>#ANVIL_VK_MAX_MEMORY : ProcedureReturn 0 : EndIf
 If avkMemLive[m]=0 Or avkMemMapped[m]<>0 Or avkMemInFlight[m]<>0 : ProcedureReturn 0 : EndIf
 pitch=avkImgPitch[s]
 If avkImgTiling[s]=#VK_IMAGE_TILING_OPTIMAL
  If avkImgBackendLayout[s]<>#AVK_ZEN_IMAGE_LAYOUT Or avkImgPaddedW[s]<>zgdWidth Or avkImgPaddedH[s]<>zgdHeight : ProcedureReturn 0 : EndIf
  pitch=zgdWidth*4
 ElseIf avkImgTiling[s]<>#VK_IMAGE_TILING_LINEAR
  ProcedureReturn 0
 EndIf
 source=AnvilVkImageAddress(image)
 If pitch<zgdPitch Or avkZenHeapRange(source,(zgdHeight-1)*pitch+zgdPitch)=0 : ProcedureReturn 0 : EndIf
 If avkBackendGpuLeaseAcquire(#ANVIL_VK_GPU_LEASE_EXTERNAL)<>1 : ProcedureReturn 0 : EndIf
 token=ZentajiGraphicsDisplayAcquireWrite()
 If token=0
  avkBackendGpuLeaseRelease(#ANVIL_VK_GPU_LEASE_EXTERNAL) : ProcedureReturn 0
 EndIf
 avkImgInFlight[s]=avkImgInFlight[s]+1 : avkMemInFlight[m]=avkMemInFlight[m]+1
 avkZenPresentImage=s : avkZenPresentMemory=m : avkZenPresentToken=token
 avkZenPresentSource=source : avkZenPresentPitch=pitch : avkZenPresentState=1
 ProcedureReturn token
EndProcedure

Procedure.i AnvilVkZentajiPresentAbort(token.q)
 If ZenCpuStatus()<>0 Or ZenCpuCoreId()<>0 : ProcedureReturn 0 : EndIf
 If avkZenPresentState<>1 Or token<1 Or token<>avkZenPresentToken : ProcedureReturn 0 : EndIf
 If ZentajiGraphicsDisplayWriteAbort(token)<>1 : ProcedureReturn 0 : EndIf
 If avkBackendGpuLeaseRelease(#ANVIL_VK_GPU_LEASE_EXTERNAL)<>1
  avkZenPresentState=2 : avkBackendGpuLeaseQuarantine(#ANVIL_VK_GPU_LEASE_EXTERNAL) : ProcedureReturn 0
 EndIf
 avkZenPresentUnpin() : ProcedureReturn 1
EndProcedure

Procedure.i AnvilVkZentajiPresentCommit(token.q,timeoutUs.i)
 If ZenCpuStatus()<>0 Or ZenCpuCoreId()<>0 : ProcedureReturn 0 : EndIf
 If avkZenPresentState<>1 Or token<1 Or token<>avkZenPresentToken : ProcedureReturn 0 : EndIf
 If timeoutUs<1 Or timeoutUs>250000 Or HwPromptIdleReady()=0 : ProcedureReturn 0 : EndIf
 If ZentajiGraphicsDisplayCopyWrite(token,@avkZenDma,avkZenPresentSource,avkZenPresentPitch,@avkZenQueue,timeoutUs)<>1
  ; A refusal before submission may be aborted. An uncertain writer stays pinned.
  If zgdWriter=1 And zgdLost=0 : AnvilVkZentajiPresentAbort(token) : ProcedureReturn 0 : EndIf
  If zgdWriter>=2 : ZentajiGraphicsDisplayWriteQuarantine(token) : EndIf
  avkZenPresentState=2 : avkBackendGpuLeaseQuarantine(#ANVIL_VK_GPU_LEASE_EXTERNAL) : ProcedureReturn 0
 EndIf
 If ZentajiGraphicsDisplayPresent(@avkZenQueue,zgdWriteIndex)<>1 Or ZentajiGraphicsDisplayWait(timeoutUs)<>1
  avkZenPresentState=2 : avkBackendGpuLeaseQuarantine(#ANVIL_VK_GPU_LEASE_EXTERNAL) : ProcedureReturn 0
 EndIf
 If avkBackendGpuLeaseRelease(#ANVIL_VK_GPU_LEASE_EXTERNAL)<>1
  avkZenPresentState=2 : avkBackendGpuLeaseQuarantine(#ANVIL_VK_GPU_LEASE_EXTERNAL) : ProcedureReturn 0
 EndIf
 avkZenPresentUnpin() : ProcedureReturn 1
EndProcedure

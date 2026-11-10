; Native coherent DMA uploads. Shared submission retains every resource and
; serializes the GPU lease. Destination pixels are written only by hardware.
Procedure.i avkZenTransferRowsValid(source.i,sourcePitch.i,destination.i,destinationPitch.i,rowBytes.i,rows.i,fill.i)
 Protected span.i
 If avkZenDma\state<>1 Or avkZenDma\lost<>0 : ProcedureReturn 0 : EndIf
 If ZentajiDmaRowsValid(@avkZenDma,source,sourcePitch,destination,destinationPitch,rowBytes,rows,fill)=0 : ProcedureReturn 0 : EndIf
 span=(rows-1)*destinationPitch+rowBytes
 If avkZenHeapRange(destination,span)=0 Or avkZenOffscreen(destination,span)=0 : ProcedureReturn 0 : EndIf
 If fill=0
  span=(rows-1)*sourcePitch+rowBytes
  If avkZenClientRange(source,span)=0 Or avkZenOffscreen(source,span)=0 : ProcedureReturn 0 : EndIf
 EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i avkZenTransferRows(source.i,sourcePitch.i,destination.i,destinationPitch.i,rowBytes.i,rows.i,fill.i)
 If avkZenLease<>#ANVIL_VK_GPU_LEASE_QUEUE Or avkZenPending<>0 Or avkZenListActive<>0 Or avkZenQueue\state<>1 Or ZentajiGraphicsOwned(@avkZenQueue)=0 : ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_DEVICE_LOST) : EndIf
 If avkZenTransferRowsValid(source,sourcePitch,destination,destinationPitch,rowBytes,rows,fill)=0 : ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_FEATURE_NOT_PRESENT) : EndIf
 If ZentajiDmaRows(@avkZenDma,source,sourcePitch,destination,destinationPitch,rowBytes,rows,fill,250000)<>1
  avkZenNativeError=(avkZenDma\error<<32)|(avkZenDma\status&$FFFFFFFF)
  ProcedureReturn -1
 EndIf
 avkZenNativeError=0
 ProcedureReturn #ANVIL_VK_JOB_DONE
EndProcedure
Procedure.i avkBackendSubmitBufferCopy(source.i,destination.i,bytes.i)
 ProcedureReturn avkZenTransferRows(source,bytes,destination,bytes,bytes,1,0)
EndProcedure
Procedure.i avkBackendSubmitBufferCopyRows(source.i,sourcePitch.i,destination.i,destinationPitch.i,rowBytes.i,rows.i)
 ProcedureReturn avkZenTransferRows(source,sourcePitch,destination,destinationPitch,rowBytes,rows,0)
EndProcedure
Procedure.i avkBackendSubmitBufferFill(destination.i,bytes.i,data.i)
 ProcedureReturn avkZenTransferRows(data,0,destination,bytes,bytes,1,1)
EndProcedure
Procedure.i avkBackendImageCopyBatchReady()
 ProcedureReturn Bool(avkZenDma\state=1 And avkZenDma\lost=0)
EndProcedure
Procedure.i avkBackendImageCopyValidate(*copy.AnvilVkBackendImageCopy)
 Protected bytes.i,span.i
 If avkZenClientRange(*copy,SizeOf(AnvilVkBackendImageCopy))=0 : ProcedureReturn -1 : EndIf
 If *copy\windowBase<>avkZenHeapBase Or *copy\windowBytes<>avkZenHeapBytes Or *copy\destinationLayout<>#AVK_ZEN_IMAGE_LAYOUT : ProcedureReturn -1 : EndIf
 If *copy\width<1 Or *copy\width>16384 Or *copy\height<1 Or *copy\height>16384 Or *copy\paddedWidth<>*copy\width Or *copy\paddedHeight<>*copy\height : ProcedureReturn -1 : EndIf
 bytes=*copy\width*4
 If avkZenTransferRowsValid(*copy\sourceBase,*copy\sourcePitch,*copy\destinationBase,bytes,bytes,*copy\height,0)=0 : ProcedureReturn -1 : EndIf
 span=(*copy\height-1)* *copy\sourcePitch+bytes
 If *copy\sourceBytes<span Or *copy\destinationBytes<bytes* *copy\height : ProcedureReturn -1 : EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i avkBackendSubmitImageCopy(*copy.AnvilVkBackendImageCopy)
 If avkBackendImageCopyValidate(*copy)<>0 : ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_FEATURE_NOT_PRESENT) : EndIf
 ProcedureReturn avkZenTransferRows(*copy\sourceBase,*copy\sourcePitch,*copy\destinationBase,*copy\width*4,*copy\width*4,*copy\height,0)
EndProcedure
Procedure.i avkBackendTiledImageCopyValidate(*copy.AnvilVkBackendTiledImageCopy)
 Protected bytes.i
 If avkZenClientRange(*copy,SizeOf(AnvilVkBackendTiledImageCopy))=0 : ProcedureReturn -1 : EndIf
 If *copy\windowBase<>avkZenHeapBase Or *copy\windowBytes<>avkZenHeapBytes Or *copy\sourceLayout<>#AVK_ZEN_IMAGE_LAYOUT Or *copy\destinationLayout<>#AVK_ZEN_IMAGE_LAYOUT : ProcedureReturn -1 : EndIf
 If *copy\width<1 Or *copy\width>16384 Or *copy\height<1 Or *copy\height>16384 Or *copy\paddedWidth<>*copy\width Or *copy\paddedHeight<>*copy\height : ProcedureReturn -1 : EndIf
 bytes=*copy\width* *copy\height*4
 If *copy\sourceBytes<bytes Or *copy\destinationBytes<bytes : ProcedureReturn -1 : EndIf
 If avkZenTransferRowsValid(*copy\sourceBase,bytes,*copy\destinationBase,bytes,bytes,1,0)=0 : ProcedureReturn -1 : EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i avkBackendSubmitTiledImageCopy(*copy.AnvilVkBackendTiledImageCopy)
 Protected bytes.i
 If avkBackendTiledImageCopyValidate(*copy)<>0 : ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_FEATURE_NOT_PRESENT) : EndIf
 bytes=*copy\width* *copy\height*4
 ProcedureReturn avkZenTransferRows(*copy\sourceBase,bytes,*copy\destinationBase,bytes,bytes,1,0)
EndProcedure

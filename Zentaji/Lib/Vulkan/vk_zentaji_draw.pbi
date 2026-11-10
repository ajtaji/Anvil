; Native Vulkan pipeline publication and one closed draw submission.
; SPDX-License-Identifier: MIT
; Included after vk_zentaji_backend.pbi's queue, heap and polling owners.
; The shared resource engine pins all referenced allocations until retirement.
; Independently recheck required physical extents before touching the controller.
XIncludeFile "Zentaji/Lib/Vulkan/vk_zentaji_shader.pbi"
Structure AvkZenPipeline
 base.i : bytes.i : varyings.i : pushBytes.i : uniformBytes.i : sampledBinding.i
EndStructure
#AVK_ZEN_TEXTURE_DESCRIPTOR=2432
Global Dim avkZenPipelines.AvkZenPipeline[#ANVIL_VK_MAX_PIPELINES+1]
Global Dim avkZenAttributes.AvkZenShaderAttribute[#ANVIL_SPV_MAX_ATTRS]
Global avkZenShaderTarget.AvkZenShaderTarget,avkZenVertex.AvkZenShaderResult,avkZenFragment.AvkZenShaderResult

Procedure.i avkZenHeapRange(base.i,bytes.i)
 If avkZenUp=0 Or bytes<1 Or bytes>avkZenHeapBytes Or base<avkZenHeapBase : ProcedureReturn 0 : EndIf
 ProcedureReturn Bool(base<=avkZenHeapBase+avkZenHeapBytes-bytes)
EndProcedure
Procedure.i avkZenRamRange(base.i,bytes.i)
 If base<1 Or bytes<1 Or bytes>avkZenQueue\ram : ProcedureReturn 0 : EndIf
 ProcedureReturn Bool(base<=avkZenQueue\ram-bytes)
EndProcedure
Procedure.i avkZenOverlaps(base.i,bytes.i,other.i,otherBytes.i)
 If bytes<1 Or otherBytes<1 : ProcedureReturn 0 : EndIf
 ; All intervals have already passed bounded RAM/heap-range validation.
 ProcedureReturn Bool(base<other+otherBytes And other<base+bytes)
EndProcedure
; Portable flight snapshots must not reside in the private command page:
; staging the next hardware list would overwrite them before the GPU reads them.
Procedure.i avkZenClientRange(base.i,bytes.i)
 If avkZenRamRange(base,bytes)=0 : ProcedureReturn 0 : EndIf
 ProcedureReturn Bool(avkZenOverlaps(base,bytes,avkZenQueue\list,4096)=0)
EndProcedure
Procedure.i avkZenU32Float(value.i)
 Protected exponent.i=127,shift.i,n.i=value
 ; Exact IEEE binary32 encoding of a nonnegative whole viewport coordinate.
 ; Values are bounded to 16384; no rounding or host float mode is involved.
 If value=0 : ProcedureReturn 0 : EndIf
 While n>1 : n=n>>1 : exponent=exponent+1 : shift=shift+1 : Wend
 ProcedureReturn (exponent<<23)|((value<<(23-shift))&$7FFFFF)
EndProcedure
Procedure avkZenBlankCommand()
 Protected n.i
 For n=0 To 7 : avkZenCommand[n]=0 : Next
EndProcedure
Procedure.i avkZenAppendCommand()
 ProcedureReturn ZentajiGraphicsAppend(@avkZenQueue,@avkZenCommand[0])
EndProcedure
Procedure.i avkBackendPipelineBytes()
 ProcedureReturn 2*#AVK_ZEN_SHADER_CODE_BYTES
EndProcedure
Procedure.i avkBackendPipelineBuild(*build.AnvilVkBackendPipelineBuildInfo)
 Protected pipe.i,n.i,binding.i,rc.i,uniformBinding.i=-1
 If *build=0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
 pipe=*build\pipeline
 If pipe<1 Or pipe>#ANVIL_VK_MAX_PIPELINES Or *build\vertexIr=0 Or *build\fragmentIr=0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
 If avkZenPipelines[pipe]\base<>0 Or avkZenPending<>0 Or avkZenListActive<>0 : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
 If *build\bytes<>avkBackendPipelineBytes() Or (*build\base&4095)<>0 Or avkZenHeapRange(*build\base,*build\bytes)=0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
 avkZenShaderTarget\attributeCount=AnvilVkPipelineAttrCount(pipe)
 avkZenShaderTarget\attributes=@avkZenAttributes[0] : avkZenShaderTarget\invertY=1
 If avkZenShaderTarget\attributeCount<1 Or avkZenShaderTarget\attributeCount>#ANVIL_SPV_MAX_ATTRS : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
 For n=0 To avkZenShaderTarget\attributeCount-1
  binding=AnvilVkPipelineAttrBinding(pipe,n)
  avkZenAttributes[n]\location=n : avkZenAttributes[n]\binding=binding
  avkZenAttributes[n]\offset=AnvilVkPipelineAttrOffset(pipe,n)
  avkZenAttributes[n]\components=AnvilVkPipelineAttrComponents(pipe,n)
  avkZenAttributes[n]\stride=AnvilVkPipelineBindingStride(pipe,binding)
  avkZenAttributes[n]\instanceRate=AnvilVkPipelineBindingRate(pipe,binding)
 Next
 avkZenShaderTarget\code=*build\base : avkZenShaderTarget\capacity=#AVK_ZEN_SHADER_CODE_BYTES
 rc=AnvilVkZentajiShaderCompile(*build\vertexIr,@avkZenShaderTarget,@avkZenVertex)
 If rc<>0 : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
 avkZenShaderTarget\code=*build\base+#AVK_ZEN_SHADER_CODE_BYTES
 rc=AnvilVkZentajiShaderCompile(*build\fragmentIr,@avkZenShaderTarget,@avkZenFragment)
 If rc<>0 : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
 If avkZenVertex\sampledBinding>=0 Or Bool(avkZenFragment\sampledBinding>=0)<>AnvilVkPipelineUsesSampledImage(pipe) : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
 If avkZenFragment\sampledBinding>=0 And avkZenFragment\sampledBinding<>AnvilVkPipelineSampleBinding(pipe) : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
 If avkZenVertex\uniformBytes<>0 : uniformBinding=avkZenVertex\uniformBinding : EndIf
 If avkZenFragment\uniformBytes<>0
  If uniformBinding<>-1 And uniformBinding<>avkZenFragment\uniformBinding : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
 EndIf
 ; Publish only executable addresses and bounded resource requirements.
 ; Neither IR pointer nor caller-owned shader bytes survive this transaction.
 avkZenPipelines[pipe]\bytes=*build\bytes
 avkZenPipelines[pipe]\varyings=avkZenVertex\varyingCount
 avkZenPipelines[pipe]\pushBytes=avkZenVertex\pushBytes
 If avkZenFragment\pushBytes>avkZenPipelines[pipe]\pushBytes : avkZenPipelines[pipe]\pushBytes=avkZenFragment\pushBytes : EndIf
 avkZenPipelines[pipe]\uniformBytes=avkZenVertex\uniformBytes
 If avkZenFragment\uniformBytes>avkZenPipelines[pipe]\uniformBytes : avkZenPipelines[pipe]\uniformBytes=avkZenFragment\uniformBytes : EndIf
 avkZenPipelines[pipe]\sampledBinding=avkZenFragment\sampledBinding
 avkZenPipelines[pipe]\base=*build\base
 ProcedureReturn #VK_SUCCESS
EndProcedure
Procedure avkBackendPipelineRelease(pipe.i)
 If pipe<1 Or pipe>#ANVIL_VK_MAX_PIPELINES : ProcedureReturn : EndIf
 avkZenPipelines[pipe]\base=0 : avkZenPipelines[pipe]\bytes=0
 avkZenPipelines[pipe]\varyings=0 : avkZenPipelines[pipe]\pushBytes=0 : avkZenPipelines[pipe]\uniformBytes=0
 avkZenPipelines[pipe]\sampledBinding=-1
EndProcedure
Procedure.i avkBackendDrawSupported(base.i,bytes.i,w.i,h.i,pitch.i)
 ProcedureReturn avkBackendClearSupported(base,bytes,w,h,pitch)
EndProcedure
; A descriptor is already resolved and retained by the portable engine, but
; the native backend independently bounds every byte the ROM may read. Optimal
; images use this backend's tightly packed row-major layout; their Vulkan pitch
; remains zero. The ROM has one non-mipmapped filter, so differing min/mag
; filters are explicitly refused rather than choosing one silently.
Procedure.i avkZenSamplePitch(*s.AnvilVkBackendSampledImage)
 Protected pitch.i,span.i
 If avkZenClientRange(*s,SizeOf(AnvilVkBackendSampledImage))=0 : ProcedureReturn 0 : EndIf
 If *s\width<1 Or *s\width>16384 Or *s\height<1 Or *s\height>16384 : ProcedureReturn 0 : EndIf
 If *s\format<>#VK_FORMAT_B8G8R8A8_UNORM Or *s\layout<>#VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL : ProcedureReturn 0 : EndIf
 If *s\magFilter<>*s\minFilter Or (*s\minFilter<>#VK_FILTER_NEAREST And *s\minFilter<>#VK_FILTER_LINEAR) : ProcedureReturn 0 : EndIf
 If *s\paddedWidth<>*s\width Or *s\paddedHeight<>*s\height : ProcedureReturn 0 : EndIf
 pitch=*s\pitch
 If *s\tiling=#VK_IMAGE_TILING_OPTIMAL
  If *s\backendLayout<>#AVK_ZEN_IMAGE_LAYOUT Or pitch<>0 : ProcedureReturn 0 : EndIf
  pitch=*s\width*4
 ElseIf *s\tiling=#VK_IMAGE_TILING_LINEAR
  If *s\backendLayout<>0 : ProcedureReturn 0 : EndIf
 Else
  ProcedureReturn 0
 EndIf
 If pitch<*s\width*4 Or pitch>$FFFFFFFF Or (pitch&3)<>0 Or (*s\base&3)<>0 : ProcedureReturn 0 : EndIf
 span=(*s\height-1)*pitch+*s\width*4
 If *s\bytes<span Or avkZenHeapRange(*s\base,*s\bytes)=0 : ProcedureReturn 0 : EndIf
 If avkZenOffscreen(*s\base,span)=0 : ProcedureReturn 0 : EndIf
 ProcedureReturn pitch
EndProcedure
Procedure.i avkZenDrawPreflight(*d.AnvilVkBackendDraw)
 Protected pipe.i,n.i,width.i,maxIndex.i,last.i,indexBytes.i,value.i,bytes.i,first.i,rate.i
 Protected *bind.AnvilVkBackendBinding
 Protected *sample.AnvilVkBackendSampledImage,pitch.i
 If avkZenClientRange(*d,SizeOf(AnvilVkBackendDraw))=0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
 pipe=*d\pipeline
 If pipe<1 Or pipe>#ANVIL_VK_MAX_PIPELINES : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
 If avkZenPipelines[pipe]\base=0 Or avkZenHeapRange(avkZenPipelines[pipe]\base,avkZenPipelines[pipe]\bytes)=0 : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
 If *d\kind<>#ANVIL_VK_RENDER_OP_DRAW Or (*d\loadColor<>0 And *d\loadColor<>1) Or (*d\sampleMask<>0 And *d\sampleMask<>1) : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
 If *d\blendMode<>#ANVIL_VK_BLEND_DISABLED And *d\blendMode<>#ANVIL_VK_BLEND_ALPHA_ONE : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
 If avkBackendDrawSupported(*d\targetBase,*d\targetBytes,*d\width,*d\height,*d\pitch)<>#VK_SUCCESS : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
 If avkZenOverlaps(*d\targetBase,*d\targetBytes,*d,SizeOf(AnvilVkBackendDraw))<>0 : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
 If avkZenOverlaps(*d\targetBase,*d\targetBytes,avkZenPipelines[pipe]\base,avkZenPipelines[pipe]\bytes)<>0 : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
 If avkZenPipelines[pipe]\sampledBinding>=0
  *sample=*d\sampledImage : pitch=avkZenSamplePitch(*sample)
  If pitch=0 Or avkZenOverlaps(*d\targetBase,*d\targetBytes,*sample,SizeOf(AnvilVkBackendSampledImage))<>0 : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
  If avkZenOverlaps(*d\targetBase,*d\targetBytes,*sample\base,(*sample\height-1)*pitch+*sample\width*4)<>0 : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
 ElseIf *d\sampledImage<>0
  ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT
 EndIf
 If *d\viewportX<0 Or *d\viewportY<0 Or *d\viewportW<1 Or *d\viewportH<1 Or *d\viewportW>*d\width Or *d\viewportH>*d\height Or *d\viewportX>*d\width-*d\viewportW Or *d\viewportY>*d\height-*d\viewportH : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
 If *d\scissorW<0 Or *d\scissorW>$FFFFFFFF Or *d\scissorH<0 Or *d\scissorH>$FFFFFFFF Or *d\scissorX<-$80000000 Or *d\scissorX>$7FFFFFFF Or *d\scissorY<-$80000000 Or *d\scissorY>$7FFFFFFF : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
 If *d\vertexCount<1 Or *d\vertexCount>$1000000 Or *d\instanceCount<1 Or *d\instanceCount>$1000000/ *d\vertexCount Or *d\firstVertex<0 Or *d\firstVertex>$FFFFFFFF-*d\vertexCount Or *d\firstInstance<0 Or *d\firstInstance>$FFFFFFFF : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
 If AnvilVkPipelineTopology(pipe)<#VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST Or AnvilVkPipelineTopology(pipe)>#VK_PRIMITIVE_TOPOLOGY_TRIANGLE_FAN : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
 maxIndex=*d\firstVertex+*d\vertexCount-1
 If *d\indexBase<>0
  width=0
  If *d\indexType=#VK_INDEX_TYPE_UINT16 : width=2 : EndIf
  If *d\indexType=#VK_INDEX_TYPE_UINT32 : width=4 : EndIf
  If width=0 : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
  last=*d\firstVertex+*d\vertexCount
  If *d\indexBytes<width Or last>*d\indexBytes/width Or avkZenHeapRange(*d\indexBase,*d\indexBytes)=0 : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
  If avkZenOverlaps(*d\targetBase,*d\targetBytes,*d\indexBase+*d\firstVertex*width,*d\vertexCount*width)<>0 : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
  maxIndex=0
  For n=*d\firstVertex To last-1
   If width=2 : value=PeekU(*d\indexBase+n*2) : Else : value=PeekL(*d\indexBase+n*4)&$FFFFFFFF : EndIf
   If value>maxIndex : maxIndex=value : EndIf
  Next
  If maxIndex<>*d\maxVertex : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
 EndIf
 If *d\bindingCount<1 Or *d\bindingCount>#ANVIL_VK_MAX_BINDINGS Or *d\bindingCount<>AnvilVkPipelineBindingCount(pipe) Or *d\bindings=0 : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
 If avkZenClientRange(*d\bindings,*d\bindingCount*SizeOf(AnvilVkBackendBinding))=0 : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
 If avkZenOverlaps(*d\targetBase,*d\targetBytes,*d\bindings,*d\bindingCount*SizeOf(AnvilVkBackendBinding))<>0 : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
 For n=0 To *d\bindingCount-1
  *bind=*d\bindings+n*SizeOf(AnvilVkBackendBinding)
  If *bind\stride<1 Or *bind\stride<>AnvilVkPipelineBindingStride(pipe,n) : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
  rate=AnvilVkPipelineBindingRate(pipe,n) : last=maxIndex+1 : first=0
  If *d\indexBase=0 : first=*d\firstVertex : EndIf
  If rate=#VK_VERTEX_INPUT_RATE_INSTANCE : first=*d\firstInstance : last=first+*d\instanceCount : EndIf
  If last>avkZenHeapBytes/ *bind\stride : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
  bytes=last* *bind\stride
  If avkZenHeapRange(*bind\base,bytes)=0 Or avkZenOverlaps(*d\targetBase,*d\targetBytes,*bind\base+first* *bind\stride,(last-first)* *bind\stride)<>0 : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
 Next
 bytes=avkZenPipelines[pipe]\pushBytes
 If bytes<>0
  If *d\pushBytes<bytes Or avkZenClientRange(*d\pushBase,bytes)=0 : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
  If avkZenOverlaps(*d\targetBase,*d\targetBytes,*d\pushBase,bytes)<>0 : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
 EndIf
 bytes=avkZenPipelines[pipe]\uniformBytes
 If bytes<>0
  If *d\uniformBytes<bytes Or avkZenHeapRange(*d\uniformBase,bytes)=0 : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
  If avkZenOverlaps(*d\targetBase,*d\targetBytes,*d\uniformBase,bytes)<>0 : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
 EndIf
 ProcedureReturn #VK_SUCCESS
EndProcedure
Procedure.i avkZenSubmitOne(*d.AnvilVkBackendDraw,preserve.i)
 Protected rc.i,n.i,pipe.i,meta.i,pitch.i,x.i,y.i,right.i,bottom.i,width.i,texture.i
 Protected *bind.AnvilVkBackendBinding
 Protected *sample.AnvilVkBackendSampledImage
 rc=avkZenDrawPreflight(*d)
 If rc<>#VK_SUCCESS : ProcedureReturn avkBackendRefuseBeforeLaunch(rc) : EndIf
 If avkZenLease<>#ANVIL_VK_GPU_LEASE_QUEUE Or avkZenPending<>0 Or avkZenQueue\state<>1 Or ZentajiGraphicsOwned(@avkZenQueue)=0 : ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_DEVICE_LOST) : EndIf
 pipe=*d\pipeline : meta=avkZenQueue\list+2112 : pitch=*d\pitch : If pitch=0 : pitch=*d\width*4 : EndIf
 ; This private page is pinned until the queue retires. The resource engine
 ; retains push/UBO/binding allocations; the GPU sees no application handles.
 For n=0 To 31 : PokeQ(meta+n*8,0) : Next
 PokeQ(meta,*d\pushBase) : PokeQ(meta+8,*d\uniformBase)
 ; One frozen 32-byte ROM descriptor lives between metadata (ending2368)
 ; and GPU scratch (starting2560), in the same permanently pinned page.
 ; The ROM performs all sampling; these writes describe input storage only.
 texture=0
 If avkZenPipelines[pipe]\sampledBinding>=0
  *sample=*d\sampledImage : texture=avkZenQueue\list+#AVK_ZEN_TEXTURE_DESCRIPTOR
  For n=0 To 3 : PokeQ(texture+n*8,0) : Next
  PokeQ(texture,*sample\base) : PokeW(texture+8,*sample\width) : PokeW(texture+10,*sample\height)
  PokeL(texture+12,avkZenSamplePitch(*sample))
  PokeA(texture+16,2) : PokeA(texture+17,1) : PokeA(texture+18,*sample\minFilter)
 EndIf
 For n=0 To *d\bindingCount-1
  *bind=*d\bindings+n*SizeOf(AnvilVkBackendBinding)
  x=*bind\base
  If AnvilVkPipelineBindingRate(pipe,n)=#VK_VERTEX_INPUT_RATE_INSTANCE : x=x+*d\firstInstance* *bind\stride : EndIf
  PokeQ(meta+32+n*8,x)
 Next
 If ZentajiGraphicsBegin(@avkZenQueue)=0 : ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_DEVICE_LOST) : EndIf
 avkZenBlankCommand() : avkZenCommand[0]=1 : avkZenCommand[1]=*d\targetBase
 PokeL(@avkZenCommand[0]+16,pitch) : PokeW(@avkZenCommand[0]+20,*d\width) : PokeW(@avkZenCommand[0]+22,*d\height) : PokeA(@avkZenCommand[0]+24,2)
 If avkZenAppendCommand()=0 : ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_DEVICE_LOST) : EndIf
 avkZenBlankCommand() : avkZenCommand[0]=4
 PokeL(@avkZenCommand[0]+16,*d\width) : PokeL(@avkZenCommand[0]+20,*d\height)
 If avkZenAppendCommand()=0 : ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_DEVICE_LOST) : EndIf
 If *d\loadColor=0 And preserve=0
  avkZenBlankCommand() : avkZenCommand[0]=$105 : PokeL(@avkZenCommand[0]+8,*d\clearBgra)
  If avkZenAppendCommand()=0 : ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_DEVICE_LOST) : EndIf
 EndIf
 avkZenBlankCommand() : avkZenCommand[0]=3
 PokeL(@avkZenCommand[0]+8,avkZenU32Float(*d\viewportX)) : PokeL(@avkZenCommand[0]+12,avkZenU32Float(*d\viewportY))
 PokeL(@avkZenCommand[0]+16,avkZenU32Float(*d\viewportW)) : PokeL(@avkZenCommand[0]+20,avkZenU32Float(*d\viewportH))
 PokeL(@avkZenCommand[0]+28,$3F800000)
 If avkZenAppendCommand()=0 : ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_DEVICE_LOST) : EndIf
 x=*d\scissorX : y=*d\scissorY : right=x+*d\scissorW : bottom=y+*d\scissorH
 If x<0 : x=0 : EndIf : If y<0 : y=0 : EndIf
 If right>*d\width : right=*d\width : EndIf : If bottom>*d\height : bottom=*d\height : EndIf
 If right<x : right=x : EndIf : If bottom<y : bottom=y : EndIf
 avkZenBlankCommand() : avkZenCommand[0]=4
 PokeL(@avkZenCommand[0]+8,x) : PokeL(@avkZenCommand[0]+12,y)
 PokeL(@avkZenCommand[0]+16,right) : PokeL(@avkZenCommand[0]+20,bottom)
 If avkZenAppendCommand()=0 : ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_DEVICE_LOST) : EndIf
 avkZenBlankCommand() : avkZenCommand[0]=6
 avkZenCommand[1]=avkZenPipelines[pipe]\base : avkZenCommand[2]=avkZenCommand[1]+#AVK_ZEN_SHADER_CODE_BYTES
 PokeA(@avkZenCommand[0]+26,avkZenPipelines[pipe]\varyings)
 ; Native blend1 uses source alpha for RGB and ONE for alpha. The portable
 ; mode is deliberately distinct from SRC_ALPHA-for-alpha, which this device
 ; cannot execute. A disabled draw always clears the hardware blend byte.
 If *d\blendMode=#ANVIL_VK_BLEND_ALPHA_ONE : PokeA(@avkZenCommand[0]+29,1) : EndIf
 avkZenCommand[5]=avkZenQueue\list+2560 : avkZenCommand[6]=256
 If avkZenAppendCommand()=0 : ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_DEVICE_LOST) : EndIf
 avkZenBlankCommand() : avkZenCommand[0]=7 : avkZenCommand[1]=meta
 If avkZenAppendCommand()=0 : ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_DEVICE_LOST) : EndIf
 ; Reset r5's hardware texture table even for a following untextured pipeline.
 avkZenBlankCommand() : avkZenCommand[0]=8 : avkZenCommand[1]=texture
 If avkZenAppendCommand()=0 : ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_DEVICE_LOST) : EndIf
 If *d\sampleMask<>0
  avkZenBlankCommand() : avkZenCommand[0]=9
  PokeL(@avkZenCommand[0]+16,*d\firstVertex) : PokeL(@avkZenCommand[0]+20,*d\vertexCount) : PokeL(@avkZenCommand[0]+24,*d\instanceCount)
  PokeA(@avkZenCommand[0]+28,AnvilVkPipelineTopology(pipe)-#VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST)
  avkZenCommand[4]=*d\indexBase
  width=0 : If *d\indexType=#VK_INDEX_TYPE_UINT16 : width=2 : EndIf : If *d\indexType=#VK_INDEX_TYPE_UINT32 : width=4 : EndIf
  PokeA(@avkZenCommand[0]+40,width)
  If avkZenAppendCommand()=0 : ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_DEVICE_LOST) : EndIf
 EndIf
 If ZentajiGraphicsSubmit(@avkZenQueue)=0 : ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_DEVICE_LOST) : EndIf
 avkZenPending=1 : avkZenNativeError=0
 ProcedureReturn #ANVIL_VK_JOB_PENDING
EndProcedure

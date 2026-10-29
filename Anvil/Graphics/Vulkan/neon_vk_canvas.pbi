; SPDX-License-Identifier: MIT
; Fixed virtual canvas over native Chrome's public Vulkan/resource contracts.
; Caller owns Chrome/device/pass/display attachment and final frame/presentation.
; Close this owner before destroying those resources. Calls are serialized.
XIncludeFile "Anvil/Graphics/neon_canvas_viewport.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_target_info.pbi"
#NEON_VK_CANVAS_MAGIC = $4E564341
#NEON_VK_CANVAS_CLOSED = 0
#NEON_VK_CANVAS_BUILDING = 1
#NEON_VK_CANVAS_IDLE = 2
#NEON_VK_CANVAS_DRAWING = 3
#NEON_VK_CANVAS_FINISHING = 4
#NEON_VK_CANVAS_BROKEN = 5
#NEON_VK_CANVAS_SELECTED = 6
Structure NeonVkCanvas Align #PB_Structure_AlignC
  magic.i : phase.i : error.i
  width.i : height.i : sprite.i : textureGeneration.i : textureOwned.i : hasFrame.i
  image.i : memory.i : view.i : framebuffer.i : pitch.i : selectedGeneration.i
  idleScope.i : linear.i
  target.NeonVkTargetInfo
  viewport.NeonCanvasViewport
EndStructure
#NEON_VK_CANVAS_MAX_TARGETS = #ANVIL_VK_RENDER_TARGET_SLOTS
Global Dim ncvOwners.i[#NEON_VK_CANVAS_MAX_TARGETS]
Global ncvSelectedOwner.i
Procedure.i ncvSlot(owner.i)
  Protected i.i
  For i=0 To #NEON_VK_CANVAS_MAX_TARGETS-1
    If ncvOwners[i]=owner And owner<>0 : ProcedureReturn i+1 : EndIf
  Next
  ProcedureReturn 0
EndProcedure
Procedure.i ncvCount()
  Protected i.i,count.i
  For i=0 To #NEON_VK_CANVAS_MAX_TARGETS-1
    If ncvOwners[i]<>0 : count=count+1 : EndIf
  Next
  ProcedureReturn count
EndProcedure
Declare.i NeonVkCanvasClose(*c.NeonVkCanvas)
Procedure.i ncvValid(*c.NeonVkCanvas)
  If (*c & 7)<>0 Or NeonByteSpan(*c,SizeOf(NeonVkCanvas))=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool(*c\magic=#NEON_VK_CANVAS_MAGIC)
EndProcedure
Procedure.i ncvFail(*c.NeonVkCanvas,code.i)
  *c\error=code : ProcedureReturn code
EndProcedure
Procedure.i NeonVkCanvasInit(*c.NeonVkCanvas,bytes.i)
  Protected i.i
  If (*c & 7)<>0 Or bytes<SizeOf(NeonVkCanvas) Or NeonByteSpan(*c,SizeOf(NeonVkCanvas))=0 : ProcedureReturn #NEON_CANVAS_ERR_ARGS : EndIf
  For i=0 To #NEON_VK_CANVAS_MAX_TARGETS-1
    If ncvOwners[i]<>0
      If NeonByteOverlap(*c,SizeOf(NeonVkCanvas),ncvOwners[i],SizeOf(NeonVkCanvas))<>0 : ProcedureReturn #NEON_CANVAS_ERR_STATE : EndIf
    EndIf
  Next
  For i=0 To SizeOf(NeonVkCanvas)-8 Step 8 : PokeI(*c+i,0) : Next
  *c\magic=#NEON_VK_CANVAS_MAGIC : ProcedureReturn 0
EndProcedure
Procedure.i ncvRestore(*c.NeonVkCanvas)
  Protected rc.i,target.NeonVkTargetInfo,prior.i,i.i,*other.NeonVkCanvas
  prior=*c\target\generation
  If NeonVkChromeTargetCurrent(*c\target\framebuffer,prior)=0
    rc=NeonVkChromeRebind(*c\target\framebuffer,*c\target\logicalW,*c\target\logicalH,*c\target\physicalW,*c\target\physicalH,*c\target\pitch,*c\target\rotation)
    If rc<>0 : ProcedureReturn rc : EndIf
    rc=NeonVkChromeTargetSnapshot(@target,SizeOf(NeonVkTargetInfo))
    If rc<>0 : ProcedureReturn rc : EndIf
    For i=0 To #NEON_VK_CANVAS_MAX_TARGETS-1
      *other=ncvOwners[i]
      If *other<>0
        If *other\target\device=target\device And *other\target\framebuffer=target\framebuffer And *other\target\generation=prior
          *other\target\generation=target\generation
        EndIf
      EndIf
    Next
  EndIf
  If *c\idleScope<>0
    If NeonVkChromeSuspended()=2
      rc=NeonVkChromeResumeIdle()
      If rc<>0 : ProcedureReturn rc : EndIf
    ElseIf NeonVkChromeSuspended()<>0
      ProcedureReturn #NEON_CANVAS_ERR_STATE
    EndIf
    ; A caller may explicitly cancel a failed idle scope before retrying Close.
    *c\idleScope=0
  EndIf
  ProcedureReturn 0
EndProcedure
; Scratch is used only for initial texture allocation/upload and can be reused
; afterwards. Its initial pixels are never presented before a complete source
; frame has been copied. Repeated source frames do not use scratch or allocate.
Procedure.i ncvCreate(*c.NeonVkCanvas,width.i,height.i,sprite.i,scratch.i,scratchBytes.i,blank.i,linear.i)
  Protected target.NeonVkTargetInfo,viewport.NeonCanvasViewport
  Protected ci.VkImageCreateInfo,req.VkMemoryRequirements,alloc.VkMemoryAllocateInfo
  Protected vi.VkImageViewCreateInfo,fi.VkFramebufferCreateInfo,rc.i,kind.i,i.i,slot.i
  If ncvValid(*c)=0 : ProcedureReturn #NEON_CANVAS_ERR_ARGS : EndIf
  If ncvSelectedOwner<>0 Or ncvSlot(*c)<>0 Or *c\phase<>#NEON_VK_CANVAS_CLOSED : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STATE) : EndIf
  If width<1 Or height<1 Or width>2048 Or height>2048 Or sprite<1 Or sprite>16 Or blank<0 Or blank>1 Or linear<0 Or linear>1 : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_ARGS) : EndIf
  If blank=0
    If scratchBytes<width*height*4 Or NeonByteSpan(scratch,width*height*4)=0 : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_ARGS) : EndIf
    If NeonByteOverlap(*c,SizeOf(NeonVkCanvas),scratch,width*height*4)<>0 : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_ARGS) : EndIf
  ElseIf scratch<>0 Or scratchBytes<>0
    ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_ARGS)
  EndIf
  If NeonVkChromeImageSpriteAllocatedId(sprite)<>0 : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STATE) : EndIf
  rc=NeonVkChromeTargetSnapshot(@target,SizeOf(NeonVkTargetInfo))
  If rc<>0 : ProcedureReturn ncvFail(*c,rc) : EndIf
  If target\wsi<>0 And NeonVkChromeTargetRecordingAllowed()=0 : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STATE) : EndIf
  rc=NeonCanvasFit(@viewport,width,height,target\logicalW,target\logicalH)
  If rc<>0 : ProcedureReturn ncvFail(*c,rc) : EndIf
  For i=0 To #NEON_VK_CANVAS_MAX_TARGETS-1
    If ncvOwners[i]=0 And slot=0 : slot=i+1 : EndIf
  Next
  If slot=0 : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STATE) : EndIf
  If ncvCount()=0
    rc=NeonVkChromeResourceRetain()
    If rc<>0 : ProcedureReturn ncvFail(*c,rc) : EndIf
  EndIf
  ncvOwners[slot-1]=*c : *c\phase=#NEON_VK_CANVAS_BUILDING
  *c\width=width : *c\height=height : *c\sprite=sprite
  For i=0 To SizeOf(NeonVkTargetInfo)-8 Step 8 : PokeI(@*c\target+i,PeekI(@target+i)) : Next
  For i=0 To SizeOf(NeonCanvasViewport)-8 Step 8 : PokeI(@*c\viewport+i,PeekI(@viewport+i)) : Next
  ci\sType=#VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO
  ci\imageType=#VK_IMAGE_TYPE_2D : ci\format=#VK_FORMAT_B8G8R8A8_UNORM
  ci\extent\width=width : ci\extent\height=height : ci\extent\depth=1
  ci\mipLevels=1 : ci\arrayLayers=1 : ci\samples=#VK_SAMPLE_COUNT_1_BIT
  ci\tiling=#VK_IMAGE_TILING_LINEAR
  ci\usage=#VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | #VK_IMAGE_USAGE_TRANSFER_SRC_BIT
  ci\sharingMode=#VK_SHARING_MODE_EXCLUSIVE : ci\initialLayout=#VK_IMAGE_LAYOUT_UNDEFINED
  rc=vkCreateImage(target\device,@ci,0,@*c\image)
  If rc=0
    vkGetImageMemoryRequirements(target\device,*c\image,@req)
    kind=0
    While kind<32 And (req\memoryTypeBits & (1<<kind))=0 : kind=kind+1 : Wend
    If kind=32
      rc=#NEON_CANVAS_ERR_STATE
    Else
      alloc\sType=#VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO
      alloc\allocationSize=req\size : alloc\memoryTypeIndex=kind
      rc=vkAllocateMemory(target\device,@alloc,0,@*c\memory)
    EndIf
  EndIf
  If rc=0 : rc=vkBindImageMemory(target\device,*c\image,*c\memory,0) : EndIf
  If rc=0
    *c\pitch=AnvilVkImageRowPitch(*c\image)
    vi\sType=#VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO
    vi\image=*c\image : vi\viewType=#VK_IMAGE_VIEW_TYPE_2D : vi\format=#VK_FORMAT_B8G8R8A8_UNORM
    vi\subresourceRange\aspectMask=#VK_IMAGE_ASPECT_COLOR_BIT
    vi\subresourceRange\levelCount=1 : vi\subresourceRange\layerCount=1
    rc=vkCreateImageView(target\device,@vi,0,@*c\view)
  EndIf
  If rc=0
    fi\sType=#VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO
    fi\renderPass=target\renderPass : fi\attachmentCount=1 : fi\pAttachments=@*c\view
    fi\width=width : fi\height=height : fi\layers=1
    rc=vkCreateFramebuffer(target\device,@fi,0,@*c\framebuffer)
  EndIf
  If rc=0
    If blank=0 : rc=NeonVkChromeImageSpriteReplaceBGRAId(sprite,scratch,width,height)
    Else : rc=NeonVkChromeImageSpriteBlankId(sprite,width,height) : EndIf
  EndIf
  If rc=0
    *c\textureOwned=1 : *c\textureGeneration=NeonVkChromeImageSpriteGenerationId(sprite)
    rc=NeonVkChromeImageSpriteLinearId(sprite,linear)
  EndIf
  If rc<>0
    ; A failed cleanup leaves every remaining handle in caller-owned state.
    *c\phase=#NEON_VK_CANVAS_BROKEN : NeonVkCanvasClose(*c)
    ProcedureReturn ncvFail(*c,rc)
  EndIf
  *c\textureOwned=1 : *c\textureGeneration=NeonVkChromeImageSpriteGenerationId(sprite)
  *c\linear=linear : *c\phase=#NEON_VK_CANVAS_IDLE : ProcedureReturn ncvFail(*c,0)
EndProcedure
Procedure.i NeonVkCanvasCreate(*c.NeonVkCanvas,width.i,height.i,sprite.i,scratch.i,scratchBytes.i)
  ProcedureReturn ncvCreate(*c,width,height,sprite,scratch,scratchBytes,0,1)
EndProcedure
Procedure.i NeonVkCanvasCreateBlank(*c.NeonVkCanvas,width.i,height.i,sprite.i)
  ProcedureReturn ncvCreate(*c,width,height,sprite,0,0,1,1)
EndProcedure
; Select sampling between frames through the canvas owner. Descriptor mutation
; advances the sprite epoch only after the renderer establishes idle.
Procedure.i NeonVkCanvasSetLinear(*c.NeonVkCanvas,enabled.i)
  Protected rc.i
  If ncvValid(*c)=0 : ProcedureReturn #NEON_CANVAS_ERR_ARGS : EndIf
  If enabled<0 Or enabled>1 : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_ARGS) : EndIf
  If ncvSlot(*c)=0 Or *c\phase<>#NEON_VK_CANVAS_IDLE Or ncvSelectedOwner<>0 Or NeonVkChromeSuspended()<>0 : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STATE) : EndIf
  If NeonVkChromeTargetCurrent(*c\target\framebuffer,*c\target\generation)=0 Or NeonVkChromeImageSpriteGenerationId(*c\sprite)<>*c\textureGeneration : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STALE) : EndIf
  rc=NeonVkChromeImageSpriteLinearId(*c\sprite,enabled)
  If rc<>0 : ProcedureReturn ncvFail(*c,rc) : EndIf
  *c\textureGeneration=NeonVkChromeImageSpriteGenerationId(*c\sprite)
  *c\linear=enabled
  ProcedureReturn ncvFail(*c,0)
EndProcedure
; Explicit adoption after the caller has rebound/resized its display target.
Procedure.i NeonVkCanvasRetarget(*c.NeonVkCanvas)
  Protected target.NeonVkTargetInfo,v.NeonCanvasViewport,rc.i,i.i
  If ncvValid(*c)=0 : ProcedureReturn #NEON_CANVAS_ERR_ARGS : EndIf
  If ncvSelectedOwner<>0 Or ncvSlot(*c)=0 Or *c\phase<>#NEON_VK_CANVAS_IDLE : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STATE) : EndIf
  rc=NeonVkChromeTargetSnapshot(@target,SizeOf(NeonVkTargetInfo))
  If rc<>0 : ProcedureReturn ncvFail(*c,rc) : EndIf
  If target\device<>*c\target\device Or target\renderPass<>*c\target\renderPass Or target\framebuffer=*c\framebuffer : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_ARGS) : EndIf
  If target\wsi<>0 And NeonVkChromeTargetRecordingAllowed()=0 : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STATE) : EndIf
  rc=NeonCanvasFit(@v,*c\width,*c\height,target\logicalW,target\logicalH)
  If rc<>0 : ProcedureReturn ncvFail(*c,rc) : EndIf
  For i=0 To SizeOf(NeonVkTargetInfo)-8 Step 8 : PokeI(@*c\target+i,PeekI(@target+i)) : Next
  For i=0 To SizeOf(NeonCanvasViewport)-8 Step 8 : PokeI(@*c\viewport+i,PeekI(@v+i)) : Next
  ProcedureReturn ncvFail(*c,0)
EndProcedure
Procedure.i NeonVkCanvasBindCheck(*c.NeonVkCanvas)
  If ncvValid(*c)=0 : ProcedureReturn #NEON_CANVAS_ERR_ARGS : EndIf
  If ncvSelectedOwner<>0 Or ncvSlot(*c)=0 Or *c\phase<>#NEON_VK_CANVAS_IDLE : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STATE) : EndIf
  If NeonVkChromeFramePending()<>0 Or NeonVkChromePresentPending()<>0 : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STATE) : EndIf
  If NeonVkChromeTargetCurrent(*c\target\framebuffer,*c\target\generation)=0 Or NeonVkChromeImageSpriteGenerationId(*c\sprite)<>*c\textureGeneration : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STALE) : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i ncvSelect(*c.NeonVkCanvas)
  Protected target.NeonVkTargetInfo,rc.i,restoreResult.i
  rc=NeonVkChromeTargetSnapshot(@target,SizeOf(NeonVkTargetInfo))
  If rc<>0 : ProcedureReturn rc : EndIf
  If target\wsi<>0
    rc=NeonVkChromeSuspendIdle()
    If rc<>0 : ProcedureReturn rc : EndIf
    *c\idleScope=1
  EndIf
  rc=NeonVkChromeRebind(*c\framebuffer,*c\width,*c\height,*c\width,*c\height,*c\pitch,0)
  If rc<>0 And *c\idleScope<>0
    restoreResult=NeonVkChromeResumeIdle()
    If restoreResult<>0 : *c\phase=#NEON_VK_CANVAS_BROKEN : ProcedureReturn restoreResult : EndIf
    *c\idleScope=0
  EndIf
  ProcedureReturn rc
EndProcedure
; Validate target ownership before a caller submits its suspended parent.
Procedure.i NeonVkCanvasBind(*c.NeonVkCanvas)
  Protected rc.i,target.NeonVkTargetInfo
  rc=NeonVkCanvasBindCheck(*c)
  If rc<>0 : ProcedureReturn rc : EndIf
  If NeonVkChromeFrameAbortable()<>0 : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STATE) : EndIf
  rc=ncvSelect(*c)
  If rc<>0 : ProcedureReturn ncvFail(*c,rc) : EndIf
  ncvSelectedOwner=*c : *c\phase=#NEON_VK_CANVAS_SELECTED
  rc=NeonVkChromeTargetSnapshot(@target,SizeOf(NeonVkTargetInfo))
  If rc<>0 : *c\phase=#NEON_VK_CANVAS_BROKEN : ProcedureReturn ncvFail(*c,rc) : EndIf
  *c\selectedGeneration=target\generation
  ProcedureReturn ncvFail(*c,0)
EndProcedure
Procedure.i NeonVkCanvasUnbind(*c.NeonVkCanvas)
  Protected rc.i
  If ncvValid(*c)=0 : ProcedureReturn #NEON_CANVAS_ERR_ARGS : EndIf
  If ncvSelectedOwner<>*c Or ncvSlot(*c)=0 Or *c\phase<>#NEON_VK_CANVAS_SELECTED : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STATE) : EndIf
  If NeonVkChromeFrameAbortable()<>0 Or NeonVkChromeFramePending()<>0 Or NeonVkChromePresentPending()<>0 : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STATE) : EndIf
  If NeonVkChromeTargetCurrent(*c\framebuffer,*c\selectedGeneration)=0 : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STALE) : EndIf
  rc=ncvRestore(*c)
  If rc<>0 : *c\phase=#NEON_VK_CANVAS_BROKEN : ProcedureReturn ncvFail(*c,rc) : EndIf
  ncvSelectedOwner=0 : *c\selectedGeneration=0 : *c\phase=#NEON_VK_CANVAS_IDLE
  ProcedureReturn ncvFail(*c,0)
EndProcedure
Procedure.i ncvBegin(*c.NeonVkCanvas,clear.i,preserve.i)
  Protected rc.i
  If ncvValid(*c)=0 : ProcedureReturn #NEON_CANVAS_ERR_ARGS : EndIf
  If ncvSlot(*c)=0 Or (*c\phase<>#NEON_VK_CANVAS_IDLE And *c\phase<>#NEON_VK_CANVAS_SELECTED) : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STATE) : EndIf
  If ncvSelectedOwner<>0 And ncvSelectedOwner<>*c : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STATE) : EndIf
  If NeonVkChromeFrameAbortable()<>0 Or NeonVkChromeFramePending()<>0 Or NeonVkChromePresentPending()<>0 : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STATE) : EndIf
  If preserve<>0
    If *c\hasFrame=0 : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STATE) : EndIf
  Else
    If (clear & 3)<>0 Or NeonByteSpan(clear,16)=0 : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_ARGS) : EndIf
    If NeonByteOverlap(*c,SizeOf(NeonVkCanvas),clear,16)<>0 : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_ARGS) : EndIf
  EndIf
  If NeonVkChromeImageSpriteGenerationId(*c\sprite)<>*c\textureGeneration : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STALE) : EndIf
  If *c\phase=#NEON_VK_CANVAS_SELECTED
    If ncvSelectedOwner<>*c Or NeonVkChromeTargetCurrent(*c\framebuffer,*c\selectedGeneration)=0 : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STALE) : EndIf
  Else
    If NeonVkChromeTargetCurrent(*c\target\framebuffer,*c\target\generation)=0 : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STALE) : EndIf
    rc=ncvSelect(*c)
    If rc<>0 : ProcedureReturn ncvFail(*c,rc) : EndIf
  EndIf
  *c\phase=#NEON_VK_CANVAS_DRAWING
  If preserve<>0 : rc=NeonVkChromeBeginLoad()
  Else : rc=NeonVkChromeBegin(clear) : EndIf
  If rc<>0 : *c\phase=#NEON_VK_CANVAS_BROKEN : EndIf
  ProcedureReturn ncvFail(*c,rc)
EndProcedure
Procedure.i NeonVkCanvasBegin(*c.NeonVkCanvas,clear.i)
  ProcedureReturn ncvBegin(*c,clear,0)
EndProcedure
Procedure.i NeonVkCanvasBeginLoad(*c.NeonVkCanvas)
  ProcedureReturn ncvBegin(*c,0,1)
EndProcedure
; Finish is retryable if an asynchronous source-frame wait has not completed.
Procedure.i NeonVkCanvasEnd(*c.NeonVkCanvas)
  Protected rc.i,layout.i
  If ncvValid(*c)=0 : ProcedureReturn #NEON_CANVAS_ERR_ARGS : EndIf
  If ncvSlot(*c)=0 Or (*c\phase<>#NEON_VK_CANVAS_DRAWING And *c\phase<>#NEON_VK_CANVAS_FINISHING) : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STATE) : EndIf
  If *c\phase=#NEON_VK_CANVAS_DRAWING
    rc=NeonVkChromeEnd()
    If rc<>0 : *c\phase=#NEON_VK_CANVAS_BROKEN : ProcedureReturn ncvFail(*c,rc) : EndIf
    *c\phase=#NEON_VK_CANVAS_FINISHING
  EndIf
  If NeonVkChromeFramePending()<>0
    rc=NeonVkChromeFinish()
    If rc<>0 : ProcedureReturn ncvFail(*c,rc) : EndIf
  EndIf
  If NeonVkChromePresentConsume()<>1 : *c\phase=#NEON_VK_CANVAS_BROKEN : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STATE) : EndIf
  layout=AnvilVkImageLayout(*c\image)
  rc=NeonVkChromeImageSpriteCopyId(*c\sprite,*c\image,layout)
  If rc=0
    *c\textureGeneration=NeonVkChromeImageSpriteGenerationId(*c\sprite)
    *c\hasFrame=1
    If ncvSelectedOwner<>*c : rc=ncvRestore(*c) : EndIf
  EndIf
  If rc<>0 : *c\phase=#NEON_VK_CANVAS_BROKEN : ProcedureReturn ncvFail(*c,rc) : EndIf
  If ncvSelectedOwner=*c : *c\phase=#NEON_VK_CANVAS_SELECTED
  Else : *c\phase=#NEON_VK_CANVAS_IDLE : EndIf
  ProcedureReturn ncvFail(*c,0)
EndProcedure
; Abort only a recorded, unsubmitted source frame. Completed source contents
; and the sampled image are preserved. Submitted work must finish or close.
Procedure.i NeonVkCanvasAbort(*c.NeonVkCanvas)
  Protected rc.i
  If ncvValid(*c)=0 : ProcedureReturn #NEON_CANVAS_ERR_ARGS : EndIf
  If ncvSlot(*c)=0 Or *c\phase<>#NEON_VK_CANVAS_DRAWING : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STATE) : EndIf
  If NeonVkChromeFramePending()<>0 Or NeonVkChromePresentPending()<>0 : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STATE) : EndIf
  rc=NeonVkChromeAbort()
  If rc<>0 : *c\phase=#NEON_VK_CANVAS_BROKEN : ProcedureReturn ncvFail(*c,rc) : EndIf
  If ncvSelectedOwner=*c
    *c\phase=#NEON_VK_CANVAS_SELECTED
  Else
    rc=ncvRestore(*c)
    If rc<>0 : *c\phase=#NEON_VK_CANVAS_BROKEN : ProcedureReturn ncvFail(*c,rc) : EndIf
    *c\phase=#NEON_VK_CANVAS_IDLE
  EndIf
  ProcedureReturn ncvFail(*c,0)
EndProcedure
; Record inside the caller's final frame. Begin's clear supplies letterbox bars.
; Frame End and display transfer/presentation remain caller-owned.
Procedure.i NeonVkCanvasDrawPassthrough(*c.NeonVkCanvas)
  Protected rc.i
  If ncvValid(*c)=0 : ProcedureReturn #NEON_CANVAS_ERR_ARGS : EndIf
  If ncvSlot(*c)=0 Or *c\phase<>#NEON_VK_CANVAS_IDLE Or *c\hasFrame=0 : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STATE) : EndIf
  If NeonVkChromeTargetCurrent(*c\target\framebuffer,*c\target\generation)=0 Or NeonVkChromeImageSpriteGenerationId(*c\sprite)<>*c\textureGeneration : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STALE) : EndIf
  rc=NeonVkChromeImageSpriteDrawId(*c\sprite,*c\viewport\x,*c\viewport\y,0,0,*c\width,*c\height,*c\viewport\width,*c\viewport\height,$FFFFFFFF)
  ProcedureReturn ncvFail(*c,rc)
EndProcedure
Procedure.i NeonVkCanvasMapPoint(*c.NeonVkCanvas,x.i,y.i,*out.NeonCanvasPoint)
  If ncvValid(*c)=0 : ProcedureReturn #NEON_CANVAS_ERR_ARGS : EndIf
  If ncvSlot(*c)=0 Or *c\phase<>#NEON_VK_CANVAS_IDLE : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STATE) : EndIf
  If (*out & 7)<>0 Or NeonByteSpan(*out,SizeOf(NeonCanvasPoint))=0 : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_ARGS) : EndIf
  If NeonByteOverlap(*c,SizeOf(NeonVkCanvas),*out,SizeOf(NeonCanvasPoint))<>0 : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_ARGS) : EndIf
  ProcedureReturn NeonCanvasMapPoint(@*c\viewport,x,y,*out)
EndProcedure
Procedure.i ncvClose(*c.NeonVkCanvas,discardParent.i)
  Protected rc.i,before.i,i.i
  If ncvValid(*c)=0 : ProcedureReturn #NEON_CANVAS_ERR_ARGS : EndIf
  If *c\phase=#NEON_VK_CANVAS_CLOSED : ProcedureReturn 0 : EndIf
  If ncvSlot(*c)=0 : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STATE) : EndIf
  If ncvSelectedOwner<>0 And ncvSelectedOwner<>*c : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STATE) : EndIf
  ; An idle canvas does not own the caller's active or pending final frame.
  If *c\phase=#NEON_VK_CANVAS_IDLE And (NeonVkChromeFrameAbortable()<>0 Or NeonVkChromeFramePending()<>0 Or NeonVkChromePresentPending()<>0) : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STATE) : EndIf
  If *c\phase=#NEON_VK_CANVAS_IDLE And NeonVkChromeReady()<>0 And NeonVkChromeTargetCurrent(*c\target\framebuffer,*c\target\generation)=0 : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STALE) : EndIf
  If NeonVkChromeFramePending()<>0
    rc=NeonVkChromeFinish() : If rc<>0 : ProcedureReturn ncvFail(*c,rc) : EndIf
  EndIf
  If NeonVkChromeFrameAbortable()<>0
    rc=NeonVkChromeAbort() : If rc<>0 : ProcedureReturn ncvFail(*c,rc) : EndIf
  EndIf
  If NeonVkChromePresentPending()<>0
    If NeonVkChromePresentConsume()<>1 : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STATE) : EndIf
  EndIf
  rc=vkDeviceWaitIdle(*c\target\device)
  If rc<>0 : ProcedureReturn ncvFail(*c,rc) : EndIf
  If discardParent<>0 And *c\idleScope<>0
    If NeonVkChromeSuspended()=2
      rc=NeonVkChromeCancelSuspended()
      If rc<>0 : ProcedureReturn ncvFail(*c,rc) : EndIf
    ElseIf NeonVkChromeSuspended()<>0
      ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STATE)
    EndIf
    ; Explicit cancellation may already have released the idle parent.
    *c\idleScope=0
  EndIf
  If NeonVkChromeReady()<>0
    rc=ncvRestore(*c) : If rc<>0 : ProcedureReturn ncvFail(*c,rc) : EndIf
    ; A replaced slot belongs to the replacement's caller, not this canvas.
    If *c\textureOwned<>0 And NeonVkChromeImageSpriteGenerationId(*c\sprite)=*c\textureGeneration
      rc=NeonVkChromeImageSpriteClearId(*c\sprite)
      If rc<>0 : ProcedureReturn ncvFail(*c,rc) : EndIf
    EndIf
  EndIf
  ; When Chrome is poisoned its texture remains owned there until DestroyChecked.
  *c\textureOwned=0
  If *c\framebuffer<>0
    before=AnvilVkFaultCount() : vkDestroyFramebuffer(*c\target\device,*c\framebuffer,0)
    If AnvilVkFaultCount()<>before : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STATE) : EndIf
    *c\framebuffer=0
  EndIf
  If *c\view<>0
    before=AnvilVkFaultCount() : vkDestroyImageView(*c\target\device,*c\view,0)
    If AnvilVkFaultCount()<>before : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STATE) : EndIf
    *c\view=0
  EndIf
  If *c\image<>0
    before=AnvilVkFaultCount() : vkDestroyImage(*c\target\device,*c\image,0)
    If AnvilVkFaultCount()<>before : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STATE) : EndIf
    *c\image=0
  EndIf
  If *c\memory<>0
    before=AnvilVkFaultCount() : vkFreeMemory(*c\target\device,*c\memory,0)
    If AnvilVkFaultCount()<>before : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STATE) : EndIf
    *c\memory=0
  EndIf
  If ncvCount()=1
    rc=NeonVkChromeResourceRelease()
    If rc<>0 : ProcedureReturn ncvFail(*c,rc) : EndIf
  EndIf
  If ncvSelectedOwner=*c : ncvSelectedOwner=0 : EndIf
  ncvOwners[ncvSlot(*c)-1]=0
  For i=0 To SizeOf(NeonVkCanvas)-8 Step 8 : PokeI(*c+i,0) : Next
  *c\magic=#NEON_VK_CANVAS_MAGIC : ProcedureReturn 0
EndProcedure

Procedure.i NeonVkCanvasClose(*c.NeonVkCanvas)
  ProcedureReturn ncvClose(*c,0)
EndProcedure
; Whole-context retirement may discard an unpublished idle parent acquisition.
Procedure.i NeonVkCanvasCloseContextScope(*c.NeonVkCanvas)
  ProcedureReturn ncvClose(*c,1)
EndProcedure
; Resize discards the old contents, as the original engine contract does.
; Validate caller arguments first. Once retirement succeeds, an allocation
; failure is explicit and leaves either CLOSED or the retained failed-cleanup
; state; it never publishes the previous image as a newly sized target.
Procedure.i ncvResize(*c.NeonVkCanvas,width.i,height.i,scratch.i,scratchBytes.i,blank.i)
  Protected sprite.i,rc.i,linear.i
  If ncvValid(*c)=0 : ProcedureReturn #NEON_CANVAS_ERR_ARGS : EndIf
  If ncvSlot(*c)=0 Or *c\phase<>#NEON_VK_CANVAS_IDLE : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STATE) : EndIf
  If width<1 Or height<1 Or width>2048 Or height>2048 Or blank<0 Or blank>1 : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_ARGS) : EndIf
  If blank=0
    If scratchBytes<width*height*4 Or NeonByteSpan(scratch,width*height*4)=0 : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_ARGS) : EndIf
    If NeonByteOverlap(*c,SizeOf(NeonVkCanvas),scratch,width*height*4)<>0 : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_ARGS) : EndIf
  ElseIf scratch<>0 Or scratchBytes<>0
    ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_ARGS)
  EndIf
  If NeonVkChromeImageSpriteGenerationId(*c\sprite)<>*c\textureGeneration : ProcedureReturn ncvFail(*c,#NEON_CANVAS_ERR_STALE) : EndIf
  sprite=*c\sprite : linear=*c\linear
  rc=NeonVkCanvasClose(*c)
  If rc<>0 : ProcedureReturn rc : EndIf
  ProcedureReturn ncvCreate(*c,width,height,sprite,scratch,scratchBytes,blank,linear)
EndProcedure

Procedure.i NeonVkCanvasResize(*c.NeonVkCanvas,width.i,height.i,scratch.i,scratchBytes.i)
  ProcedureReturn ncvResize(*c,width,height,scratch,scratchBytes,0)
EndProcedure
Procedure.i NeonVkCanvasResizeBlank(*c.NeonVkCanvas,width.i,height.i)
  ProcedureReturn ncvResize(*c,width,height,0,0,1)
EndProcedure

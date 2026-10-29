; SPDX-License-Identifier: MIT
; Install after the caller creates Chrome. Prepare before Begin; caller owns frames.
; Legacy roles0..3 retain active-face semantics. Register references for controls
; whose loaded face/size must be independent of another control's font.
XIncludeFile "Anvil/Graphics/neon_retained_ui.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_port.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_font_port.pbi"

#NVR_FONT_TAG = $0001000000000000
Global nvrFontArena.i,nvrFontCapacity.i,nvrFontCount.i,nvrFontEpoch.i,nvrFontError.i
Procedure.i nvrFontFail(code.i)
  nvrFontError=code : ProcedureReturn code
EndProcedure
Procedure.i NeonVkRetainedFontError()
  ProcedureReturn nvrFontError
EndProcedure
Procedure.i NeonVkRetainedFontBytes(capacity.i)
  If capacity<1 Or capacity>65535 : ProcedureReturn 0 : EndIf
  ProcedureReturn capacity*SizeOf(NeonVkPortFontRef)
EndProcedure
Procedure.i NeonVkRetainedFontsConfigure(arena.i,bytes.i,capacity.i)
  Protected needed.i=NeonVkRetainedFontBytes(capacity)
  If NeonRetainedMutationAllowed()=0 : ProcedureReturn nvrFontFail(#NRU_ERR_BUSY) : EndIf
  If needed=0 Or arena<1 Or (arena & 7)<>0 Or bytes<needed Or arena+needed<arena
    ProcedureReturn nvrFontFail(#NRU_ERR_ARGS)
  EndIf
  If nvrFontEpoch>=$7FFFFFFF : ProcedureReturn nvrFontFail(#NRU_ERR_GENERATION) : EndIf
  nvrFontEpoch=nvrFontEpoch+1 : nvrFontArena=arena : nvrFontCapacity=capacity : nvrFontCount=0
  ProcedureReturn nvrFontFail(#NEON_OK)
EndProcedure
Procedure.i NeonVkRetainedFontRegister(slot.i,face.i,pixelHeight.i)
  Protected rc.i
  Protected *font.NeonVkPortFontRef
  If NeonRetainedMutationAllowed()=0 : nvrFontFail(#NRU_ERR_BUSY) : ProcedureReturn 0 : EndIf
  If nvrFontArena=0 : nvrFontFail(#NRU_ERR_CONFIG) : ProcedureReturn 0 : EndIf
  If nvrFontCount>=nvrFontCapacity : nvrFontFail(#NRU_ERR_CAPACITY) : ProcedureReturn 0 : EndIf
  *font=nvrFontArena+nvrFontCount*SizeOf(NeonVkPortFontRef)
  rc=NeonVkPortFontBind(*font,slot,face,pixelHeight)
  If rc<>#NEON_OK : nvrFontFail(rc) : ProcedureReturn 0 : EndIf
  nvrFontCount=nvrFontCount+1 : nvrFontError=0
  ProcedureReturn #NVR_FONT_TAG | (nvrFontEpoch << 16) | nvrFontCount
EndProcedure
Procedure.i nvrFontRef(font.i)
  Protected index.i=(font & $FFFF)-1
  Protected *ref.NeonVkPortFontRef
  If (font >> 48)<>1
    nvrFontFail(#NEON_VK_FONT_ERR_HANDLE) : ProcedureReturn 0
  EndIf
  If font<>(#NVR_FONT_TAG | (nvrFontEpoch << 16) | (index+1))
    nvrFontFail(#NEON_VK_FONT_ERR_STALE) : ProcedureReturn 0
  EndIf
  If nvrFontArena=0 Or index<0 Or index>=nvrFontCount
    nvrFontFail(#NEON_VK_FONT_ERR_HANDLE) : ProcedureReturn 0
  EndIf
  *ref=nvrFontArena+index*SizeOf(NeonVkPortFontRef)
  If *ref\slot<0 Or *ref\slot>=#ANVIL_TTS_MAX_SLOTS Or *ref\face<0 Or *ref\face>3 Or *ref\pixelHeight<1 Or *ref\pixelHeight>512 Or *ref\fixedAdvanceQ16<0 Or *ref\fixedAdvanceQ16>536870912 Or *ref\snapToPixel<0 Or *ref\snapToPixel>1 Or *ref\controlMode<0 Or *ref\controlMode>2
    nvrFontFail(#NEON_VK_FONT_ERR_HANDLE) : ProcedureReturn 0
  EndIf
  If *ref\generation<1 Or AnvilTrueTypeSlotGeneration(*ref\slot)<>*ref\generation Or AnvilTrueTypeSlotBytes(*ref\slot)<1
    nvrFontFail(#NEON_VK_FONT_ERR_STALE) : ProcedureReturn 0
  EndIf
  nvrFontError=0 : ProcedureReturn *ref
EndProcedure
Procedure.i NeonVkRetainedFontStatus(font.i)
  If font>=0 And font<=3 : ProcedureReturn nvrFontFail(#NEON_OK) : EndIf
  If nvrFontRef(font)=0 : ProcedureReturn nvrFontError : EndIf
  ProcedureReturn #NEON_OK
EndProcedure
Procedure.i NeonVkRetainedFontSetFixedAdvance(font.i,advance.f)
  Protected ref.i,rc.i
  If NeonRetainedMutationAllowed()=0 : ProcedureReturn nvrFontFail(#NRU_ERR_BUSY) : EndIf
  ref=nvrFontRef(font) : If ref=0 : ProcedureReturn nvrFontError : EndIf
  rc=NeonVkPortFontSetFixedAdvance(ref,advance)
  ProcedureReturn nvrFontFail(rc)
EndProcedure

Procedure.i NeonVkRetainedFontSetSnapToPixel(font.i,enabled.i)
  Protected ref.i,rc.i
  If NeonRetainedMutationAllowed()=0 : ProcedureReturn nvrFontFail(#NRU_ERR_BUSY) : EndIf
  ref=nvrFontRef(font) : If ref=0 : ProcedureReturn nvrFontError : EndIf
  rc=NeonVkPortFontSetSnapToPixel(ref,enabled)
  ProcedureReturn nvrFontFail(rc)
EndProcedure

Procedure.i NeonVkRetainedFontSetControlMode(font.i,mode.i)
  Protected ref.i,rc.i
  If NeonRetainedMutationAllowed()=0 : ProcedureReturn nvrFontFail(#NRU_ERR_BUSY) : EndIf
  ref=nvrFontRef(font) : If ref=0 : ProcedureReturn nvrFontError : EndIf
  rc=NeonVkPortFontSetControlMode(ref,mode)
  ProcedureReturn nvrFontFail(rc)
EndProcedure
Procedure.i NeonVkRetainedFontSetShowControls(font.i,enabled.i)
  If enabled<0 Or enabled>1 : ProcedureReturn nvrFontFail(#NEON_VK_FONT_ERR_METRICS) : EndIf
  ProcedureReturn NeonVkRetainedFontSetControlMode(font,enabled+1)
EndProcedure

Procedure.i nvrBox(x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
  ProcedureReturn NeonVkPortBox(x,y,w,h,r,g,b,a,1,1)
EndProcedure
Procedure.i nvrText(font.i,x.f,y.f,*text,r.f,g.f,b.f,a.f)
  Protected *ref.NeonVkPortFontRef
  If font>=0 And font<=3 : ProcedureReturn NeonVkPortText(font,x,y,*text,r,g,b,a,1,1) : EndIf
  *ref=nvrFontRef(font) : If *ref=0 : ProcedureReturn nvrFontError : EndIf
  ProcedureReturn NeonVkPortFontText(*ref,x,y,*text,r,g,b,a,1,1)
EndProcedure
Procedure.f NeonVkRetainedFontTextWidth(font.i,*text)
  Protected *ref.NeonVkPortFontRef
  If font>=0 And font<=3 : ProcedureReturn NeonVkPortTextWidth(font,*text,1) : EndIf
  *ref=nvrFontRef(font) : If *ref=0 : ProcedureReturn -1.0 : EndIf
  ProcedureReturn NeonVkPortFontTextWidth(*ref,*text,1)
EndProcedure
Procedure.i NeonVkRetainedFontLineHeight(font.i)
  Protected *ref.NeonVkPortFontRef
  If font>=0 And font<=3 : ProcedureReturn Neon_LineHeight(font) : EndIf
  *ref=nvrFontRef(font) : If *ref=0 : ProcedureReturn nvrFontError : EndIf
  ProcedureReturn NeonVkPortFontLineHeight(*ref)
EndProcedure
Procedure.f nvrWidth(font.i,*text)
  ProcedureReturn NeonVkRetainedFontTextWidth(font,*text)
EndProcedure
Procedure.f nvrHeight(font.i)
  ProcedureReturn MathFFromInt(NeonVkRetainedFontLineHeight(font))
EndProcedure
Procedure.i nvrPolygon(x.f,y.f,rx.f,ry.f,sides.i,r.f,g.f,b.f,a.f,solid.i)
  ProcedureReturn NeonVkPortPolygon(x,y,rx,ry,sides,r,g,b,a,solid,1,1)
EndProcedure
Procedure.i NeonVkRetainedFontWarm(font.i,*text)
  Protected height.i,rc.i
  Protected *ref.NeonVkPortFontRef
  If font<0 Or font>3
    *ref=nvrFontRef(font) : If *ref=0 : ProcedureReturn nvrFontError : EndIf
    ProcedureReturn NeonVkPortFontWarm(*ref,*text)
  EndIf
  If AnvilTrueTypeSlotSelected()<0 : ProcedureReturn 0 : EndIf
  height=NeonVkChromeFontPixelHeight(font)
  If height<0 : ProcedureReturn height : EndIf
  rc=NeonVkChromeWarmTrueTypeText(height,*text)
  If rc<0 : ProcedureReturn rc : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i nvrPrepare(font.i,*text)
  ProcedureReturn NeonVkRetainedFontWarm(font,*text)
EndProcedure
Procedure.i NeonVkRetainedInstall()
  If NeonVkChromeReady()=0 : ProcedureReturn #NRU_ERR_RENDERER : EndIf
  ProcedureReturn NeonRetainedRendererInstall(@nvrBox,@nvrText,@nvrWidth,@nvrHeight,@nvrPolygon,@nvrPrepare)
EndProcedure

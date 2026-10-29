; SPDX-License-Identifier: MIT
; Real Vulkan retained UI scene. Included by the widget diagnostic builder.
; Caller creates/retire Vulkan and owns the frame; this code never resets it.
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_retained_ui.pbi"
Global Dim nrgArena.q[1024]
; The public builder supplies NRG_FONT_KIND:0bitmap,1mixed TrueType.
CompilerIf #NRG_FONT_KIND=1
Global Dim nrgFontArena.q[56]
Global Dim nrgFonts.i[4]
Global nrgProbeFontId.i,nrgTTChecks.i,nrgTTFailure.i,nrgTTBusy.i,nrgTTAllowed.i,nrgTTRegisterBusy.i
#NRG_TT_REPORT=$E1C00400
Procedure NrgTTCheck(actual.i,expected.i)
  nrgTTChecks=nrgTTChecks+1
  If actual<>expected And nrgTTFailure=0 : nrgTTFailure=nrgTTChecks : EndIf
  ; Preserve progress even if a later operation reaches the watchdog.
  PokeI(#NRG_TT_REPORT,$4E524754) : PokeI(#NRG_TT_REPORT+8,1)
  PokeI(#NRG_TT_REPORT+16,nrgTTFailure) : PokeI(#NRG_TT_REPORT+24,nrgTTChecks)
EndProcedure
Procedure.i NrgSpyBox(x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
  ProcedureReturn #NRU_ERR_RENDERER
EndProcedure
Procedure.i NrgSpyText(font.i,x.f,y.f,*text,r.f,g.f,b.f,a.f)
  ProcedureReturn #NRU_ERR_RENDERER
EndProcedure
Procedure.f NrgSpyWidth(font.i,*text)
  nrgTTAllowed=NeonRetainedMutationAllowed()
  nrgTTBusy=NeonVkRetainedFontsConfigure(@nrgFontArena[0],448,8)
  nrgTTRegisterBusy=NeonVkRetainedFontRegister(0,0,24)
  ProcedureReturn 16.0
EndProcedure
Procedure.f NrgSpyHeight(font.i)
  ProcedureReturn 16.0
EndProcedure
Procedure.i NrgSpyPoly(x.f,y.f,rx.f,ry.f,sides.i,r.f,g.f,b.f,a.f,solid.i)
  ProcedureReturn #NRU_ERR_RENDERER
EndProcedure
Procedure.i NrgSpyPrepare(font.i,*text)
  ProcedureReturn #NRU_ERR_RENDERER
EndProcedure
Procedure.i NrgFontSetup()
  Protected old.i,control.i,role.i,px.i
  NrgTTCheck(NeonVkRetainedFontBytes(8),448)
  NrgTTCheck(NeonVkRetainedFontsConfigure(@nrgFontArena[0]+1,447,8),#NRU_ERR_ARGS)
  NrgTTCheck(NeonVkRetainedFontsConfigure(@nrgFontArena[0],448,1),0)
  old=NeonVkRetainedFontRegister(0,0,24)
  NrgTTCheck(Bool(old<>0),1)
  NrgTTCheck(NeonVkRetainedFontRegister(0,1,16),0)
  NrgTTCheck(NeonVkRetainedFontError(),#NRU_ERR_CAPACITY)
  NrgTTCheck(NeonVkRetainedFontStatus(old),0)
  NrgTTCheck(NeonRetainedRendererInstall(@NrgSpyBox,@NrgSpyText,@NrgSpyWidth,@NrgSpyHeight,@NrgSpyPoly,@NrgSpyPrepare),0)
  NrgTTCheck(NeonRetainedFontSet(0),0)
  control=NeonRetainedAddButton(-1,0.0,0.0,100.0,30.0,"probe",0,0)
  NrgTTCheck(Bool(control<>0),1)
  NrgTTCheck(nrgTTAllowed,0) : NrgTTCheck(nrgTTBusy,#NRU_ERR_BUSY)
  NrgTTCheck(nrgTTRegisterBusy,0) : NrgTTCheck(NeonVkRetainedFontError(),#NRU_ERR_BUSY)
  NrgTTCheck(NeonVkRetainedFontStatus(old),0)
  NrgTTCheck(NeonVkRetainedFontStatus(control),#NEON_VK_FONT_ERR_HANDLE)
  NrgTTCheck(NeonRetainedReset(),0)
  NrgTTCheck(NeonVkRetainedInstall(),0)
  NrgTTCheck(AnvilTrueTypeSlotLoad(0,?nrgProbeFont,#NRG_PROBE_FONT_BYTES),0)
  NrgTTCheck(NeonVkRetainedFontStatus(old),0)
  NrgTTCheck(AnvilTrueTypeSlotSelect(1),1)
  NrgTTCheck(AnvilTrueTypeSlotLoad(0,?nrgProbeFont,#NRG_PROBE_FONT_BYTES),1)
  NrgTTCheck(NeonVkRetainedFontStatus(old),#NEON_VK_FONT_ERR_STALE)
  NrgTTCheck(AnvilTrueTypeSlotLoad(0,?anvilBootTtf,#ANVIL_BOOT_TTF_BYTES),1)
  NrgTTCheck(NeonVkRetainedFontStatus(old),#NEON_VK_FONT_ERR_STALE)
  NrgTTCheck(AnvilTrueTypeSlotSelect(0),1)
  NrgTTCheck(AnvilTrueTypeSlotLoad(1,?nrgProbeFont,#NRG_PROBE_FONT_BYTES),1)
  NrgTTCheck(AnvilTrueTypeSlotLoad(1,?nrgProbeFont,#NRG_PROBE_FONT_BYTES),1)
  NrgTTCheck(AnvilTrueTypeSlotGeneration(0),AnvilTrueTypeSlotGeneration(1))
  NrgTTCheck(NeonVkRetainedFontsConfigure(@nrgFontArena[0],448,8),0)
  NrgTTCheck(NeonVkRetainedFontStatus(old),#NEON_VK_FONT_ERR_STALE)
  For role=0 To 3
    px=24
    If role=1 : px=16 : EndIf
    If role=2 : px=20 : EndIf
    If role=3 : px=32 : EndIf
    nrgFonts[role]=NeonVkRetainedFontRegister(0,role,px)
    NrgTTCheck(Bool(nrgFonts[role]<>0),1)
  Next
  nrgProbeFontId=NeonVkRetainedFontRegister(1,1,16)
  NrgTTCheck(Bool(nrgProbeFontId<>0),1)
  NrgTTCheck(NeonVkRetainedFontStatus(nrgProbeFontId),0)
  CompilerIf #NRG_FONT_SETUP_ONLY=1
    If nrgTTFailure<>0 : ProcedureReturn #NW_ERR_COUNTS : EndIf
    ProcedureReturn 0
  CompilerEndIf
  NrgTTCheck(NeonVkRetainedFontWarm(nrgFonts[1],"AB"),0)
  NrgTTCheck(NeonVkRetainedFontWarm(nrgProbeFontId,"AB"),0)
  PokeI(#NRG_TT_REPORT,$4E524754) : PokeI(#NRG_TT_REPORT+8,1)
  PokeI(#NRG_TT_REPORT+16,nrgTTFailure) : PokeI(#NRG_TT_REPORT+24,nrgTTChecks)
  PokeI(#NRG_TT_REPORT+48,nrgTTRegisterBusy) : PokeI(#NRG_TT_REPORT+56,nrgTTBusy)
  If nrgTTFailure<>0 : ProcedureReturn #NW_ERR_COUNTS : EndIf
  ProcedureReturn 0
EndProcedure
Procedure NrgFontRecord()
  Protected i.i,id.i,base.i,font.i,slot.i,px.i
  Protected *g.NeonRetainedGadget
  For i=0 To 4
    slot=0 : px=24 : font=i
    If i=1 : px=16 : EndIf
    If i=2 : px=20 : EndIf
    If i=3 : px=32 : EndIf
    If i=4 : slot=1 : font=1 : px=16 : EndIf
    base=#NRG_TT_REPORT+64+i*64
    PokeI(base,slot) : PokeI(base+8,AnvilTrueTypeSlotGeneration(slot))
    PokeI(base+16,font) : PokeI(base+24,px)
    If i=4 : id=nrgProbeFontId : Else : id=nrgFonts[i] : EndIf
    PokeI(base+32,NeonVkRetainedFontLineHeight(id))
    PokeI(base+40,Int(NeonVkRetainedFontTextWidth(id,"A")*65536.0))
    PokeI(base+48,Int(NeonVkRetainedFontTextWidth(id,"B")*65536.0))
    PokeI(base+56,NeonVkRetainedFontStatus(id))
  Next
  For i=0 To 7
    *g=NeonRetainedGet(NeonRetainedHandleAt(i))
    base=#NRG_TT_REPORT+384+i*64
    PokeI(base,*g\id) : PokeI(base+8,*g\font)
    PokeI(base+16,MathBitsOf(*g\x)) : PokeI(base+24,MathBitsOf(*g\y))
    PokeI(base+32,MathBitsOf(*g\w)) : PokeI(base+40,MathBitsOf(*g\h))
    PokeI(base+48,NeonVkRetainedFontStatus(*g\font))
  Next
  PokeI(#NRG_TT_REPORT+112*8,AnvilTrueTypeSlotSelected())
EndProcedure
CompilerEndIf

#NRG_REPORT = $E1C00200
Procedure NrgPut(slot.i,value.i)
  PokeI(#NRG_REPORT+slot*8,value)
EndProcedure
Procedure.i NrgRun(imageBase.i,pitch.i,framebuffer.i)
  Protected rc.i,i.i,j.i,capture.i,slider.i,toggle.i,bank.i,carousel.i
  Protected Dim clear.l[4]
  Protected *g.NeonRetainedGadget
  Protected base.i,consumed.i,copied.i,poisonTotal.i,copyTotal.i
  If pitch<>3200 Or (imageBase & 7)<>0 : ProcedureReturn #NW_ERR_WINDOW : EndIf
  NrgPut(3,1) : NrgPut(4,8) : NrgPut(6,#NEON_FONT_SMALL)
  NrgPut(7,AnvilTrueTypeSlotSelected())
  NrgPut(8,$07000000) : NrgPut(9,$07400000) : NrgPut(10,pitch)
  NrgPut(11,800) : NrgPut(12,1280) : NrgPut(13,4096000)
  rc=NeonVkRetainedInstall() : If rc<0 : ProcedureReturn rc : EndIf
  rc=NeonVkPortCanvas(800,1280,800,1280) : If rc<0 : ProcedureReturn rc : EndIf
  rc=NeonRetainedConfigure(@nrgArena[0],8192,8,128) : If rc<0 : ProcedureReturn rc : EndIf
  rc=NeonRetainedViewport(0.0,0.0,800.0,1280.0,800.0,1280.0) : If rc<0 : ProcedureReturn rc : EndIf
  CompilerIf #NRG_FONT_KIND=1
    rc=NrgFontSetup() : If rc<0 : ProcedureReturn rc : EndIf
    CompilerIf #NRG_FONT_SETUP_ONLY=1
      ProcedureReturn 0
    CompilerEndIf
    rc=NeonRetainedFontSet(nrgFonts[0])
  CompilerElse
    rc=NeonRetainedFontSet(#NEON_FONT_SMALL)
  CompilerEndIf
  If rc<0 : ProcedureReturn rc : EndIf
  CompilerIf #NRG_FONT_KIND=1
    If NeonRetainedAddLabel(1,40.0,40.0,"Anvil retained — café")=0 : ProcedureReturn NeonRetainedError() : EndIf
    rc=NeonRetainedFontSet(nrgProbeFontId) : If rc<0 : ProcedureReturn rc : EndIf
    If NeonRetainedAddBreadcrumb(2,40.0,70.0,"AB")=0 : ProcedureReturn NeonRetainedError() : EndIf
    rc=NeonRetainedFontSet(nrgFonts[3]) : If rc<0 : ProcedureReturn rc : EndIf
  CompilerElse
  If NeonRetainedAddLabel(1,40.0,40.0,"Anvil retained controls")=0 : ProcedureReturn NeonRetainedError() : EndIf
    If NeonRetainedAddBreadcrumb(2,40.0,70.0,"Neon / Vulkan / UI")=0 : ProcedureReturn NeonRetainedError() : EndIf
  CompilerEndIf
  If NeonRetainedAddButton(3,40.0,120.0,200.0,40.0,"Start",0,0)=0 : ProcedureReturn NeonRetainedError() : EndIf
  CompilerIf #NRG_FONT_KIND=1
    rc=NeonRetainedFontSet(nrgFonts[0]) : If rc<0 : ProcedureReturn rc : EndIf
  CompilerEndIf
  slider=NeonRetainedAddSlider(4,40.0,230.0,240.0,30.0,0.25,"Volume",0)
  CompilerIf #NRG_FONT_KIND=1
    rc=NeonRetainedFontSet(nrgFonts[1]) : If rc<0 : ProcedureReturn rc : EndIf
  CompilerEndIf
  toggle=NeonRetainedAddToggle(5,360.0,120.0,220.0,40.0,"Sound",0,0)
  CompilerIf #NRG_FONT_KIND=1
    rc=NeonRetainedFontSet(nrgFonts[2]) : If rc<0 : ProcedureReturn rc : EndIf
  CompilerEndIf
  If NeonRetainedAddMeter(6,360.0,230.0,240.0,30.0,0.6,"Load")=0 : ProcedureReturn NeonRetainedError() : EndIf
  CompilerIf #NRG_FONT_KIND=1
    rc=NeonRetainedFontSet(nrgFonts[1]) : If rc<0 : ProcedureReturn rc : EndIf
  CompilerEndIf
  bank=NeonRetainedAddDipBank(7,40.0,340.0,4,5,"Options",0)
  CompilerIf #NRG_FONT_KIND=1
    rc=NeonRetainedFontSet(nrgFonts[0]) : If rc<0 : ProcedureReturn rc : EndIf
  CompilerEndIf
  CompilerIf #NRG_FONT_KIND=1
    carousel=NeonRetainedAddCarousel(8,360.0,340.0,240.0,40.0,"Low|Médium|High",1,0)
  CompilerElse
  carousel=NeonRetainedAddCarousel(8,360.0,340.0,240.0,40.0,"Low|Medium|High",1,0)
  CompilerEndIf
  If slider=0 Or toggle=0 Or bank=0 Or carousel=0 : ProcedureReturn NeonRetainedError() : EndIf
  CompilerIf #NRG_FONT_KIND=1
    PokeI(#NRG_TT_REPORT+32,AnvilTrueTypeRasterCount())
  CompilerEndIf
  rc=NeonRetainedPrepare() : If rc<0 : ProcedureReturn rc : EndIf
  CompilerIf #NRG_FONT_KIND=1
    PokeI(#NRG_TT_REPORT+40,AnvilTrueTypeRasterCount())
    NrgFontRecord()
  CompilerEndIf
  rc=NeonVkChromeRebind(framebuffer,800,1280,800,1280,pitch,0) : If rc<0 : ProcedureReturn rc : EndIf
  clear[0]=0 : clear[1]=0 : clear[2]=0 : clear[3]=$3F800000
  NrgPut(3,2)
  For i=0 To 1
    If i=1
      rc=NeonRetainedValueSet(slider,0.75) : If rc<0 : ProcedureReturn rc : EndIf
      rc=NeonRetainedActiveSet(toggle,1) : If rc<0 : ProcedureReturn rc : EndIf
      rc=NeonRetainedActiveSet(bank,10) : If rc<0 : ProcedureReturn rc : EndIf
      rc=NeonRetainedValueSet(carousel,2.0) : If rc<0 : ProcedureReturn rc : EndIf
    EndIf
    rc=NeonRetainedUpdateInput(700.0,700.0,0,0,0,0,0) : If rc<0 : ProcedureReturn rc : EndIf
    rc=NeonVkChromeBegin(@clear[0]) : If rc<0 : ProcedureReturn rc : EndIf
    rc=NeonRetainedDrawUI(0.0)
    If rc<0
      NeonVkChromeAbort()
      ProcedureReturn rc
    EndIf
    rc=NeonVkChromeEnd() : If rc<0 : ProcedureReturn rc : EndIf
    If NeonVkChromeFrameRasterDelta()<>0 Or NeonVkChromeFrameUploadDelta()<>0 : ProcedureReturn #NW_ERR_COUNTS : EndIf
    CompilerIf #NRG_FONT_KIND=1
      PokeI(#NRG_TT_REPORT+(113+i)*8,AnvilTrueTypeSlotSelected())
    CompilerEndIf
    base=16+i*16
    NrgPut(base,NeonVkChromeDrawCount()) : NrgPut(base+1,NeonVkChromeVertexCount())
    NrgPut(base+2,NeonVkChromeFrameRasterDelta()) : NrgPut(base+3,NeonVkChromeFrameUploadDelta())
    NrgPut(base+4,NeonVkChromePresentPending())
    consumed=NeonVkChromePresentConsume()
    NrgPut(base+5,consumed) : NrgPut(base+6,NeonVkChromePresentPending())
    NrgPut(base+7,NeonVkChromeError()) : NrgPut(base+8,NeonRetainedCount())
    *g=NeonRetainedGet(slider) : NrgPut(base+9,MathBitsOf(*g\value))
    *g=NeonRetainedGet(toggle) : NrgPut(base+10,*g\isActive)
    *g=NeonRetainedGet(bank) : NrgPut(base+11,*g\isActive)
    *g=NeonRetainedGet(carousel) : NrgPut(base+12,MathBitsOf(*g\value))
    NrgPut(base+13,Neon_LineHeight(#NEON_FONT_SMALL))
    NrgPut(base+14,Neon_CharWidth(#NEON_FONT_SMALL))
    If consumed<>1 : ProcedureReturn #NW_ERR_PRESENT : EndIf
    capture=$07000000+i*$00400000
    ; Poison the complete destination before each copy, so retained bytes
    ; from a previous run cannot masquerade as this frame. Both endpoints
    ; and lengths are eight-byte aligned; counters prove the full span ran.
    For j=0 To 4095992 Step 8
      PokeI(capture+j,$A5A5A5A5A5A5A5A5) : poisonTotal=poisonTotal+8
    Next
    copied=0
    For j=0 To 4095992 Step 8
      PokeI(capture+j,PeekI(imageBase+j)) : copied=copied+8
    Next
    copyTotal=copyTotal+copied
    NrgPut(base+15,copied) : NrgPut(14,poisonTotal) : NrgPut(15,copyTotal)
    NrgPut(5,i+1) : NrgPut(3,3+i)
  Next
  ProcedureReturn 0
EndProcedure

Procedure.i NrgFrame(imageBase.i,pitch.i,framebuffer.i)
  Protected rc.i
  NrgPut(0,$4E524732) : NrgPut(1,2+#NRG_FONT_KIND) : NrgPut(2,1) : NrgPut(63,$3247524E)
  rc=NrgRun(imageBase,pitch,framebuffer) : NrgPut(2,rc)
  If rc=0 : NrgPut(3,9) : EndIf
  ProcedureReturn rc
EndProcedure

; Observe parent invalidation through public APIs after the caller's teardown,
; rather than treating a shutdown flag as proof that destruction succeeded.
Procedure NrgRetired(report.i)
  Protected count.l=12345
  NrgPut(48,AnvilVkFaultCount())
  NrgPut(49,NeonVkChromeReady()) : NrgPut(50,NeonDrawBackendActive())
  NrgPut(51,Neon_Ready())
  NrgPut(52,vkDeviceWaitIdle(PeekL(report+#NW_S_DEVICE*4)))
  NrgPut(53,vkEnumeratePhysicalDevices(PeekL(report+#NW_S_INSTANCE*4),@count,0))
  NrgPut(54,count) : NrgPut(55,AnvilVkFaultCount())
EndProcedure

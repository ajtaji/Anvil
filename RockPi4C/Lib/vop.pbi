; RK3399 little VOP scanout path. The exact Rock Pi 4C graph routes
; vopl -> cdn_dp. Mode selection supplies a validated base-block DTD through
; the rock_mode_* ABI; this layer independently bounds every packed VOP field
; and the compiler-owned 32-bpp scan buffer before touching VOP MMIO.

#ROCK_VOPL = $FF8F0000
#ROCK_VOPB = $FF900000
#ROCK_VOPB_MMU = $FF903F00
#ROCK_VOP_MAX_HDMI_WIDTH = 1920
#ROCK_VOP_MAX_HDMI_HEIGHT = 1080
#ROCK_VOP_MAX_HDMI_PIXEL_HZ = 148500000
#ROCK_VOP_MAX_WIDTH = 2560
#ROCK_VOP_MAX_HEIGHT = 1600
#ROCK_VOP_TIMING_MAX = 8191
#ROCK_VOP_STRIDE_WORD_MAX = 16383
#ROCK_FB_MAX_WORDS = #ROCK_VOP_MAX_WIDTH*#ROCK_VOP_MAX_HEIGHT
#ROCK_FB_MAX_BYTES = #ROCK_FB_MAX_WORDS*4
#ROCK_FB_ALIGNMENT = 16

; WIN0_CTRL0 line-buffer modes used by the shipped Rockchip RGB helper.
#VOP_WIN_ENABLE = 1
#VOP_WIN_LB_MODE_SHIFT = 5
#VOP_LB_RGB_2560X4 = 3
#VOP_LB_RGB_1920X5 = 4
#VOP_WIN0_CTRL0_RGB_BASE = $3A000000
#VOP_WIN0_CTRL1_RGB_UNITY = $00400000
#VOP_WIN0_SRC_ALPHA_OPAQUE = $00FF0000
#VOP_DSP_P888_PRE_DITHER = $00000002
; DSP_CTRL0.out_mode[3:0]. VOPL -> MiniDP is a 24-bit parallel P888 output.
; VOPB -> HDMI is the RK3399's 30-bit RGB101010 internal bus: the released
; ROCK Pi 4C 5.10.110 kernel's dw_hdmi_rockchip_select_output stores
; ROCKCHIP_OUT_MODE_AAAA (15) for every RGB mode, and vop_update_csc keeps it
; on VOPB because rk3399_vop_big.feature has OUTPUT_10BIT (0x45; VOPL 0x44
; lacks it and is forced to P888). The DW HDMI sampler (TX_INVID0=RGB 8-bit)
; takes the top 8 bits of each 10-bit lane, so P888 on VOPB scrambles pixel
; bits across lanes: correct framebuffer, wrong hues, speckled ramps and text.
; The same function writes pre_dither_down = (out_mode <> AAAA).
#VOP_DSP_OUT_MODE_P888 = $00000000
#VOP_DSP_OUT_MODE_AAAA = $0000000F
; Software image of the VOP register window (Linux vop->regsbak). Every
; writable VOP control register is double-buffered until CFG_DONE and an MMIO
; read returns the ACTIVE bank, so a read-modify-write before CFG_DONE would
; silently discard fields written earlier in the same commit.
#VOP_SHADOW_WORDS = $400 >> 2
#VOP_DSP_LAYER_LITTLE = $0000E400
#VOP_GLOBAL_REGDONE_ENABLE = $00000800
#VOP_HDMI_ENABLE = $00002000
#VOP_FRAME_WAIT_US = 50000

#VOP_CFG_DONE = $000
#VOP_SYS_CTRL = $008
#VOP_SYS_CTRL1 = $00C
#VOP_DSP_CTRL0 = $010
#VOP_DSP_CTRL1 = $014
#VOP_DSP_BG = $018
#VOP_WIN0_CTRL0 = $030
#VOP_WIN0_CTRL1 = $034
#VOP_WIN0_VIR = $03C
#VOP_WIN0_YRGB_MST = $040
#VOP_WIN0_ACT_INFO = $048
#VOP_WIN0_DSP_INFO = $04C
#VOP_WIN0_DSP_ST = $050
#VOP_WIN0_SCL_FACTOR = $054
#VOP_WIN0_SRC_ALPHA_CTRL = $060
#VOP_WIN2_CTRL0 = $0B0
#VOP_POST_HACT = $170
#VOP_POST_VACT = $174
#VOP_POST_SCL_FACTOR = $178
#VOP_POST_SCL_CTRL = $180
#VOP_HTOTAL = $188
#VOP_HACT = $18C
#VOP_VTOTAL = $190
#VOP_VACT = $194
#VOP_BCSH_COLOR_BAR = $1B0
#VOP_BCSH_CTRL = $1BC
#VOP_CABC_CTRL0 = $1C0
#VOP_CABC_CTRL1 = $1C4
#VOP_CABC_CTRL2 = $1C8
#VOP_CABC_CTRL3 = $1CC
#VOP_AFBCD0_CTRL = $200
#VOP_INTR_CLEAR0 = $284
#VOP_INTR_RAW_STATUS0 = $28C
#VOP_STATUS = $2A4
#VOP_YUV2YUV_WIN = $2C0

#VOP_INTR_FS = $0001
#VOP_INTR_BUS_ERROR = $0020
#VOP_INTR_WIN0_EMPTY = $0040
#VOP_INTR_POST_EMPTY = $0800

; scl_vop_cal_scl_fac() in the pinned RK3399 DRM driver writes a 12-bit
; unity factor on both axes even when both scale modes are SCALE_NONE.
; NONE selects the scaler algorithm; it does not make these factors optional.
#VOP_SCALE_UNITY_XY = $10001000

Global rock_vop_ready.i
Global rock_vop_error.i
Global rock_vop_prepared.i
Global rock_vop_configured.i
Global rock_vop_win0_ctrl0_pending.i
Global rock_vop_raw_version.i
Global rock_vop_raw_sys_ctrl.i
Global rock_vop_raw_sys_ctrl1.i
Global rock_vop_raw_dsp_ctrl0.i
Global rock_vop_raw_dsp_ctrl1.i
Global rock_vop_raw_win0_ctrl0.i
Global rock_vop_raw_win0_vir.i
Global rock_vop_raw_win0_mst.i
Global rock_vop_raw_htotal.i
Global rock_vop_raw_hact.i
Global rock_vop_raw_vtotal.i
Global rock_vop_raw_vact.i
Global rock_vop_raw_status.i
Global rock_vop_raw_intr.i
Global rock_vop_mmu_dte.i
Global rock_vop_mmu_status.i
Global rock_vop_mmu_fault.i
Global rock_vop_mmu_raw.i
Global rock_vop_mmu_mask.i
Global rock_vop_mmu_irq.i
Global rock_vop_mmu_gating.i
; Default stays on the existing MiniDP path. HDMI chooses the board's VOPB.
Global rock_vop_base.i = #ROCK_VOPL
Global rock_vop_output.i
; Global ordering is not an alignment contract. Reserve one alignment unit
; of slack and derive the scanout base within this compiler-owned object.
Global Dim rock_vop_framebuffer.l[#ROCK_FB_MAX_WORDS+4]
; One register image per VOP (index rock_vop_output: 0 VOPL, 1 VOPB).
Global Dim rock_vop_shadow.l[2*#VOP_SHADOW_WORDS]
Global Dim rock_vop_shadow_ready.i[2]

Procedure.i RockVopFramebuffer()
  ProcedureReturn (@rock_vop_framebuffer[0]+#ROCK_FB_ALIGNMENT-1) & $FFFFFFFFFFFFFFF0
EndProcedure

Procedure.i RockVopRead(offset.i)
  ProcedureReturn PeekL(rock_vop_base+offset) & $FFFFFFFF
EndProcedure

Procedure RockVopShadowAdopt()
  ; Linux vop_initial() copies the whole register window into regsbak once the
  ; VOP is clocked and out of reset. Do the same on this VOP's first owned
  ; access; from then on every RockVopWrite keeps the image current.
  Protected index.i
  Protected slot.i = rock_vop_output*#VOP_SHADOW_WORDS
  For index=0 To #VOP_SHADOW_WORDS-1
    rock_vop_shadow[slot+index]=PeekL(rock_vop_base+index*4)
  Next
  rock_vop_shadow_ready[rock_vop_output]=1
EndProcedure

Procedure RockVopWrite(offset.i, value.i)
  If rock_vop_shadow_ready[rock_vop_output]=0 : RockVopShadowAdopt() : EndIf
  PokeL(rock_vop_base+offset,value & $FFFFFFFF)
  If offset>=0 And offset<#VOP_SHADOW_WORDS*4 And (offset & 3)=0
    rock_vop_shadow[rock_vop_output*#VOP_SHADOW_WORDS+(offset >> 2)]=value & $FFFFFFFF
  EndIf
EndProcedure

Procedure RockVopCaptureTelemetry()
  ; Fixed, non-polling snapshot. Keep this in the VOP owner so the HDMI
  ; facade can report exactly what the scanout block latched after CFG_DONE.
  rock_vop_raw_version=RockVopRead($004)
  rock_vop_raw_sys_ctrl=RockVopRead(#VOP_SYS_CTRL)
  rock_vop_raw_sys_ctrl1=RockVopRead(#VOP_SYS_CTRL1)
  rock_vop_raw_dsp_ctrl0=RockVopRead(#VOP_DSP_CTRL0)
  rock_vop_raw_dsp_ctrl1=RockVopRead(#VOP_DSP_CTRL1)
  rock_vop_raw_win0_ctrl0=RockVopRead(#VOP_WIN0_CTRL0)
  rock_vop_raw_win0_vir=RockVopRead(#VOP_WIN0_VIR)
  rock_vop_raw_win0_mst=RockVopRead(#VOP_WIN0_YRGB_MST)
  rock_vop_raw_htotal=RockVopRead(#VOP_HTOTAL)
  rock_vop_raw_hact=RockVopRead(#VOP_HACT)
  rock_vop_raw_vtotal=RockVopRead(#VOP_VTOTAL)
  rock_vop_raw_vact=RockVopRead(#VOP_VACT)
  rock_vop_raw_status=RockVopRead(#VOP_STATUS)
  rock_vop_raw_intr=RockVopRead(#VOP_INTR_RAW_STATUS0)
  ; The RK3399 DTS exposes VOPB's Rockchip IOMMU at FF903F00. These are the
  ; read-only registers defined by rockchip-iommu.c; capture them before any
  ; recovery decision so a paging or page-fault state is evidence, not a
  ; guessed reason for an AXI bus error.
  If rock_vop_output=1
    rock_vop_mmu_dte=PeekL(#ROCK_VOPB_MMU+$00) & $FFFFFFFF
    rock_vop_mmu_status=PeekL(#ROCK_VOPB_MMU+$04) & $FFFFFFFF
    rock_vop_mmu_fault=PeekL(#ROCK_VOPB_MMU+$0C) & $FFFFFFFF
    rock_vop_mmu_raw=PeekL(#ROCK_VOPB_MMU+$14) & $FFFFFFFF
    rock_vop_mmu_mask=PeekL(#ROCK_VOPB_MMU+$1C) & $FFFFFFFF
    rock_vop_mmu_irq=PeekL(#ROCK_VOPB_MMU+$20) & $FFFFFFFF
    rock_vop_mmu_gating=PeekL(#ROCK_VOPB_MMU+$24) & $FFFFFFFF
  EndIf
EndProcedure

Procedure RockVopSelectMiniDp()
  rock_vop_base=#ROCK_VOPL
  rock_vop_output=0
EndProcedure

Procedure RockVopSelectHdmiVopB()
  rock_vop_base=#ROCK_VOPB
  rock_vop_output=1
EndProcedure

Procedure RockVopField(offset.i, mask.i, value.i)
  ; Merge into the software image, never the MMIO read: the read returns the
  ; ACTIVE bank and would drop fields still pending in this commit (live
  ; build 133 lost DSP_CTRL1.pre_dither_down exactly this way).
  Protected prior.i
  If rock_vop_shadow_ready[rock_vop_output]=0 : RockVopShadowAdopt() : EndIf
  If offset>=0 And offset<#VOP_SHADOW_WORDS*4 And (offset & 3)=0
    prior=rock_vop_shadow[rock_vop_output*#VOP_SHADOW_WORDS+(offset >> 2)] & $FFFFFFFF
  Else
    prior=RockVopRead(offset)
  EndIf
  RockVopWrite(offset,(prior & ~mask) | (value & mask))
EndProcedure

Procedure.i RockVopLineBufferMode(width.i)
  ; The old fixed $A1 selected LB_RGB_1280X8 and was valid only for the
  ; proven 1024-pixel milestone. Match scl_vop_cal_lb_mode() exactly for the
  ; unscaled RGB modes that fit RK3399's little-VOP output limit.
  If width < 1 Or width > #ROCK_VOP_MAX_WIDTH : ProcedureReturn -1 : EndIf
  If width > 1920 : ProcedureReturn #VOP_LB_RGB_2560X4 : EndIf
  ProcedureReturn #VOP_LB_RGB_1920X5
EndProcedure

Procedure.i RockVopGlyphRow(character.i, row.i)
  If row < 0 Or row > 6 : ProcedureReturn 0 : EndIf
  Select character
    Case 65 ; A
      If row=0 : ProcedureReturn $0E : EndIf : If row=1 Or row=2 : ProcedureReturn $11 : EndIf : If row=3 : ProcedureReturn $1F : EndIf : ProcedureReturn $11
    Case 67 ; C
      If row=0 Or row=6 : ProcedureReturn $0E : EndIf : If row=1 Or row=5 : ProcedureReturn $11 : EndIf : ProcedureReturn $10
    Case 73 ; I
      If row=0 Or row=6 : ProcedureReturn $1F : EndIf : ProcedureReturn $04
    Case 75 ; K
      If row=0 Or row=6 : ProcedureReturn $11 : EndIf : If row=1 Or row=5 : ProcedureReturn $12 : EndIf : If row=2 Or row=4 : ProcedureReturn $14 : EndIf : ProcedureReturn $18
    Case 76 ; L
      If row=6 : ProcedureReturn $1F : EndIf : ProcedureReturn $10
    Case 78 ; N
      If row=0 Or row=6 : ProcedureReturn $11 : EndIf : If row=1 : ProcedureReturn $19 : EndIf : If row=2 : ProcedureReturn $15 : EndIf : If row=3 : ProcedureReturn $13 : EndIf : ProcedureReturn $11
    Case 79 ; O
      If row=0 Or row=6 : ProcedureReturn $0E : EndIf : ProcedureReturn $11
    Case 80 ; P
      If row=0 Or row=3 : ProcedureReturn $1E : EndIf : If row=1 Or row=2 : ProcedureReturn $11 : EndIf : ProcedureReturn $10
    Case 82 ; R
      If row=0 Or row=3 : ProcedureReturn $1E : EndIf : If row=1 Or row=2 : ProcedureReturn $11 : EndIf : If row=4 : ProcedureReturn $14 : EndIf : If row=5 : ProcedureReturn $12 : EndIf : ProcedureReturn $11
    Case 86 ; V
      If row < 5 : ProcedureReturn $11 : EndIf : If row=5 : ProcedureReturn $0A : EndIf : ProcedureReturn $04
    Case 52 ; 4
      If row=0 : ProcedureReturn $02 : EndIf : If row=1 : ProcedureReturn $06 : EndIf : If row=2 : ProcedureReturn $0A : EndIf : If row=3 : ProcedureReturn $12 : EndIf : If row=4 : ProcedureReturn $1F : EndIf : ProcedureReturn $02
  EndSelect
  ProcedureReturn 0
EndProcedure

Procedure RockVopGlyph(character.i, x0.i, y0.i, scale.i, colour.i)
  Protected row.i
  Protected column.i
  Protected dx.i
  Protected dy.i
  Protected bits.i
  Protected address.i
  Protected pixelX.i
  Protected pixelY.i
  If scale <= 0 : ProcedureReturn 0 : EndIf
  For row=0 To 6
    bits=RockVopGlyphRow(character,row)
    For column=0 To 4
      If (bits & (16 >> column)) <> 0
        For dy=0 To scale-1
          pixelY=y0+row*scale+dy
          For dx=0 To scale-1
            pixelX=x0+column*scale+dx
            If pixelX >= 0 And pixelX < rock_mode_width And pixelY >= 0 And pixelY < rock_mode_height
              address=RockVopFramebuffer()+pixelY*rock_mode_pitch+pixelX*4
              PokeL(address,colour)
            EndIf
          Next
        Next
      EndIf
    Next
  Next
EndProcedure

Procedure RockVopText(text.i, x.i, y.i, scale.i, colour.i)
  Protected character.i
  Protected index.i
  For index=0 To 63
    character=PeekA(text+index) & 255
    If character=0 : Break : EndIf
    RockVopGlyph(character,x+index*6*scale,y,scale,colour)
  Next
EndProcedure

Procedure RockVopFirstFrame()
  Protected x.i
  Protected y.i
  Protected band.i
  Protected colour.i
  Protected address.i
  Protected rowWords.i = rock_mode_pitch >> 2
  Protected footerStart.i = rock_mode_height-(rock_mode_height/6)
  Protected footerHeight.i = rock_mode_height-footerStart
  Protected labelScale.i = rock_mode_height/192
  Protected labelWidth.i
  Protected labelHeight.i
  Protected labelX.i
  Protected labelY.i
  If labelScale < 1 : labelScale=1 : EndIf
  If labelScale > 6 : labelScale=6 : EndIf
  labelWidth=95*labelScale
  labelHeight=7*labelScale
  While labelScale > 1 And (labelWidth > rock_mode_width Or labelHeight > footerHeight)
    labelScale=labelScale-1
    labelWidth=95*labelScale
    labelHeight=7*labelScale
  Wend
  For y=0 To rock_mode_height-1
    For x=0 To rowWords-1
      band=(x*8)/rock_mode_width
      Select band
        Case 0 : colour=$FFFFFFFF
        Case 1 : colour=$FFFFFF00
        Case 2 : colour=$FF00FFFF
        Case 3 : colour=$FF00FF00
        Case 4 : colour=$FFFF00FF
        Case 5 : colour=$FFFF0000
        Case 6 : colour=$FF0000FF
        Default : colour=$FF101010
      EndSelect
      If x >= rock_mode_width Or y >= footerStart : colour=$FF101010 : EndIf
      address=RockVopFramebuffer()+y*rock_mode_pitch+x*4
      PokeL(address,colour)
    Next
    ; A completed scanline is real forward progress through the large CPU
    ; framebuffer fill. Feed in coarse batches; never feed inside a VOP status
    ; poll, where doing so could conceal a wedged display engine.
    If (y & 31)=31 Or y=rock_mode_height-1 : RockWatchdogPet() : EndIf
  Next
  labelX=(rock_mode_width-labelWidth)/2
  labelY=footerStart+(footerHeight-labelHeight)/2
  If labelX < 0 : labelX=0 : EndIf
  If labelY < 0 : labelY=0 : EndIf
  RockVopText("ANVIL ROCK PI 4C",labelX,labelY,labelScale,$FF40FF40)
  ASM
    dsb sy
  ENDASM
EndProcedure

Procedure.i RockVopModeValid()
  Protected hsyncLength.i
  Protected vsyncLength.i
  Protected hactiveStart.i
  Protected hactiveEnd.i
  Protected vactiveStart.i
  Protected vactiveEnd.i
  If rock_mode_valid=0
    rock_vop_error=79
    ProcedureReturn 0
  EndIf
  If rock_mode_width < 1 Or rock_mode_width > #ROCK_VOP_MAX_WIDTH Or rock_mode_height < 1 Or rock_mode_height > #ROCK_VOP_MAX_HEIGHT
    rock_vop_error=72
    ProcedureReturn 0
  EndIf
  If rock_vop_output=1 And (rock_mode_width > #ROCK_VOP_MAX_HDMI_WIDTH Or rock_mode_height > #ROCK_VOP_MAX_HDMI_HEIGHT Or rock_mode_pixel_hz > #ROCK_VOP_MAX_HDMI_PIXEL_HZ)
    rock_vop_error=85
    ProcedureReturn 0
  EndIf
  If rock_mode_pixel_hz < 1 Or rock_mode_width > rock_mode_hsync_start Or rock_mode_hsync_start >= rock_mode_hsync_end Or rock_mode_hsync_end > rock_mode_htotal
    rock_vop_error=73
    ProcedureReturn 0
  EndIf
  If rock_mode_height > rock_mode_vsync_start Or rock_mode_vsync_start >= rock_mode_vsync_end Or rock_mode_vsync_end > rock_mode_vtotal
    rock_vop_error=74
    ProcedureReturn 0
  EndIf
  hsyncLength=rock_mode_hsync_end-rock_mode_hsync_start
  vsyncLength=rock_mode_vsync_end-rock_mode_vsync_start
  hactiveStart=rock_mode_htotal-rock_mode_hsync_start
  hactiveEnd=hactiveStart+rock_mode_width
  vactiveStart=rock_mode_vtotal-rock_mode_vsync_start
  vactiveEnd=vactiveStart+rock_mode_height
  If rock_mode_htotal > #ROCK_VOP_TIMING_MAX Or hsyncLength > #ROCK_VOP_TIMING_MAX Or hactiveStart > #ROCK_VOP_TIMING_MAX Or hactiveEnd > #ROCK_VOP_TIMING_MAX
    rock_vop_error=75
    ProcedureReturn 0
  EndIf
  If rock_mode_vtotal > #ROCK_VOP_TIMING_MAX Or vsyncLength > #ROCK_VOP_TIMING_MAX Or vactiveStart > #ROCK_VOP_TIMING_MAX Or vactiveEnd > #ROCK_VOP_TIMING_MAX
    rock_vop_error=76
    ProcedureReturn 0
  EndIf
  If rock_mode_pitch < rock_mode_width*4 Or (rock_mode_pitch & 15) <> 0 Or (rock_mode_pitch >> 2) > #ROCK_VOP_STRIDE_WORD_MAX
    rock_vop_error=77
    ProcedureReturn 0
  EndIf
  If rock_mode_pitch*rock_mode_height > #ROCK_FB_MAX_BYTES
    rock_vop_error=78
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i RockVopLatchFrame()
  Protected start.i
  Protected now.i
  Protected timeoutTicks.i
  Protected attempt.i
  If rock_timer_frequency < 1000000 : ProcedureReturn 0 : EndIf
  ; RAW frame-start is used only as a bounded frame boundary witness. Interrupt
  ; delivery remains disabled. RK3399 interrupt clear uses high-half write mask.
  RockVopWrite(#VOP_INTR_CLEAR0,$00010001)
  ASM
    dsb sy
  ENDASM
  RockVopWrite(#VOP_CFG_DONE,1)
  ASM
    dsb sy
  ENDASM
  timeoutTicks=(rock_timer_frequency/1000000)*#VOP_FRAME_WAIT_US
  start=RockTimerTicks()
  For attempt=0 To 9999999
    If (RockVopRead(#VOP_INTR_RAW_STATUS0) & #VOP_INTR_FS) <> 0
      RockVopWrite(#VOP_INTR_CLEAR0,$00010001)
      ProcedureReturn 1
    EndIf
    now=RockTimerTicks()
    If now < start Or now-start >= timeoutTicks : ProcedureReturn 0 : EndIf
  Next
  ProcedureReturn 0
EndProcedure

Procedure.i RockVopPrepareMode()
  Protected pinPolarity.i
  Protected hsyncLength.i
  Protected vsyncLength.i
  Protected hactiveStart.i
  Protected hactiveEnd.i
  Protected vactiveStart.i
  Protected vactiveEnd.i
  Protected pixelTotal.i
  Protected outMode.i
  Protected ditherCtrl.i
  rock_vop_ready=0
  rock_vop_prepared=0
  rock_vop_configured=0
  rock_vop_error=0
  If RockVopModeValid()=0 : ProcedureReturn 0 : EndIf
  If rock_vop_output=1
    If RockCruVopBRelease()=0 : rock_vop_error=71 : ProcedureReturn 0 : EndIf
  Else
    If RockCruVopRelease()=0 : rock_vop_error=71 : ProcedureReturn 0 : EndIf
  EndIf
  hsyncLength=rock_mode_hsync_end-rock_mode_hsync_start
  vsyncLength=rock_mode_vsync_end-rock_mode_vsync_start
  hactiveStart=rock_mode_htotal-rock_mode_hsync_start
  hactiveEnd=hactiveStart+rock_mode_width
  vactiveStart=rock_mode_vtotal-rock_mode_vsync_start
  vactiveEnd=vactiveStart+rock_mode_height
  pixelTotal=rock_mode_width*rock_mode_height
  pinPolarity=0
  If rock_mode_hsync_positive <> 0 : pinPolarity=pinPolarity | 1 : EndIf
  If rock_mode_vsync_positive <> 0 : pinPolarity=pinPolarity | 2 : EndIf

  ; Shipped Linux enables HCLK/DCLK/ACLK before every VOP access and never
  ; toggles the DCLK reset after CFG_DONE. RockCruVopRelease deasserts the
  ; bare-metal AXI/AHB/DCLK resets; all following state is owned while live.
  ; VOPL declares only WIN0 primary and WIN2 cursor. Disable them and AFBCD
  ; before starting the CRTC background stage.
  RockVopField(#VOP_AFBCD0_CTRL,$00000001,0)
  RockVopWrite(#VOP_WIN0_CTRL0,#VOP_WIN0_CTRL0_RGB_BASE)
  RockVopWrite(#VOP_WIN0_CTRL1,#VOP_WIN0_CTRL1_RGB_UNITY)
  RockVopField(#VOP_WIN2_CTRL0,$00000011,0)

  ; vop_initial(): unblank, leave DMA running, select one physical output,
  ; and allow thirty global AXI reads outstanding. The pinned Radxa 4.4
  ; vop_initial() also sets global_regdone_en at SYS_CTRL[11]. RK3399 VOPB is
  ; VOP 3.5, where this bit remains required for HDMI CFG_DONE commits. Do not
  ; clear it while changing the physical output enable. RGB overlay/output and
  ; progressive scan leave every other DSP_CTRL0 functional field zero; only
  ; out_mode differs per route (see #VOP_DSP_OUT_MODE_AAAA).
  If rock_vop_output=1
    outMode=#VOP_DSP_OUT_MODE_AAAA
    ditherCtrl=0
  Else
    outMode=#VOP_DSP_OUT_MODE_P888
    ditherCtrl=#VOP_DSP_P888_PRE_DITHER
  EndIf
  If rock_vop_output=1
    RockVopField(#VOP_SYS_CTRL,$0063F800,#VOP_GLOBAL_REGDONE_ENABLE | #VOP_HDMI_ENABLE)
  Else
    RockVopField(#VOP_SYS_CTRL,$0063F800,#VOP_GLOBAL_REGDONE_ENABLE)
  EndIf
  RockVopField(#VOP_SYS_CTRL1,$0003F000,$0003D000)
  RockVopWrite(#VOP_DSP_CTRL0,outMode)
  RockVopWrite(#VOP_DSP_CTRL1,ditherCtrl)
  If rock_vop_output=1
    ; RK3399 VOPB HDMI polarity uses DSP_CTRL1[23:20], unlike DP[18:16].
    RockVopField(#VOP_DSP_CTRL1,$00F00000,(pinPolarity | $00000008) << 20)
  Else
    RockVopField(#VOP_DSP_CTRL1,$00070000,pinPolarity << 16)
  EndIf
  RockVopWrite(#VOP_DSP_BG,0)

  ; Exact progressive CRTC and full-size post path. The shipped driver sets
  ; the pixel clock before CFG_DONE; RockCruVpllMode owns that earlier phase.
  RockVopWrite(#VOP_HTOTAL,hsyncLength | (rock_mode_htotal << 16))
  RockVopWrite(#VOP_HACT,hactiveEnd | (hactiveStart << 16))
  RockVopWrite(#VOP_VTOTAL,vsyncLength | (rock_mode_vtotal << 16))
  RockVopWrite(#VOP_VACT,vactiveEnd | (vactiveStart << 16))
  RockVopWrite(#VOP_POST_HACT,hactiveEnd | (hactiveStart << 16))
  RockVopWrite(#VOP_POST_VACT,vactiveEnd | (vactiveStart << 16))
  RockVopWrite(#VOP_POST_SCL_FACTOR,#VOP_SCALE_UNITY_XY)
  RockVopField(#VOP_POST_SCL_CTRL,$00000007,0)

  ; The shipped RK3399 VOPL node exposes its CABC resource. Its disabled-mode
  ; path still programs the selected frame pixel count, stage-by-stage mode,
  ; and the global down-limit field on every mode set.
  RockVopWrite(#VOP_CABC_CTRL0,(pixelTotal << 4) | $00000008)
  RockVopWrite(#VOP_CABC_CTRL1,pixelTotal << 4)
  RockVopField(#VOP_CABC_CTRL2,$00080000,0)
  RockVopField(#VOP_CABC_CTRL3,$00000100,$00000100)

  ; RGB output bypasses BCSH and per-window YUV conversion. Own the bypasses
  ; explicitly instead of inheriting a previous boot display pipeline.
  RockVopField(#VOP_BCSH_COLOR_BAR,$00000001,0)
  RockVopField(#VOP_BCSH_CTRL,$00000011,0)
  RockVopField(#VOP_YUV2YUV_WIN,$00000007,0)

  ; Latch a background-only CRTC frame before the encoder is enabled. The
  ; display facade owns the GRF route as part of its encoder-enable phase.
  If RockVopLatchFrame()=0 : rock_vop_error=81 : ProcedureReturn 0 : EndIf
  rock_vop_prepared=1
  ProcedureReturn 1
EndProcedure

Procedure.i RockVopConfigurePrimary()
  Protected lineBufferMode.i
  Protected hactiveStart.i
  Protected vactiveStart.i
  rock_vop_configured=0
  rock_vop_win0_ctrl0_pending=0
  If rock_vop_prepared=0 : rock_vop_error=82 : ProcedureReturn 0 : EndIf
  If RockVopModeValid()=0 : ProcedureReturn 0 : EndIf
  lineBufferMode=RockVopLineBufferMode(rock_mode_width)
  If lineBufferMode < 0 : rock_vop_error=80 : ProcedureReturn 0 : EndIf
  hactiveStart=rock_mode_htotal-rock_mode_hsync_start
  vactiveStart=rock_mode_vtotal-rock_mode_vsync_start
  RockVopFirstFrame()

  ; Complete shipped WIN0 RGB-primary state while enable remains clear. The
  ; no-scale helper selects BIC vertical-up coefficients, unity factors, and
  ; LB4 through 1920 pixels (LB3 above it). It does not enable AXI gather.
  rock_vop_win0_ctrl0_pending=#VOP_WIN0_CTRL0_RGB_BASE | (lineBufferMode << #VOP_WIN_LB_MODE_SHIFT)
  RockVopWrite(#VOP_WIN0_CTRL0,rock_vop_win0_ctrl0_pending)
  RockVopWrite(#VOP_WIN0_CTRL1,#VOP_WIN0_CTRL1_RGB_UNITY)
  RockVopWrite(#VOP_WIN0_VIR,rock_mode_pitch >> 2)
  RockVopWrite(#VOP_WIN0_YRGB_MST,RockVopFramebuffer())
  RockVopWrite(#VOP_WIN0_ACT_INFO,(rock_mode_width-1) | ((rock_mode_height-1) << 16))
  RockVopWrite(#VOP_WIN0_DSP_INFO,(rock_mode_width-1) | ((rock_mode_height-1) << 16))
  RockVopWrite(#VOP_WIN0_DSP_ST,hactiveStart | (vactiveStart << 16))
  RockVopWrite(#VOP_WIN0_SCL_FACTOR,#VOP_SCALE_UNITY_XY)
  RockVopWrite(#VOP_WIN0_SRC_ALPHA_CTRL,#VOP_WIN0_SRC_ALPHA_OPAQUE)
  RockVopField(#VOP_DSP_CTRL1,$0000FF00,#VOP_DSP_LAYER_LITTLE)
  RockVopField(#VOP_YUV2YUV_WIN,$00000007,0)
  rock_vop_configured=1
  ProcedureReturn 1
EndProcedure

Procedure.i RockVopStartPrimary()
  rock_vop_ready=0
  If rock_vop_prepared=0 Or rock_vop_configured=0
    rock_vop_error=83
    ProcedureReturn 0
  EndIf
  ; WIN0 state above is still in VOP's pending bank until CFG_DONE. A live
  ; MMIO read here returns the previous active CTRL0, so read/modify/write
  ; would discard the pending line-buffer mode. Linux avoids that with its
  ; software regsbak; U-Boot writes LB, format and enable together before
  ; CFG_DONE. Re-emit the complete saved CTRL0 image for the same contract.
  RockVopWrite(#VOP_WIN0_CTRL0,rock_vop_win0_ctrl0_pending | #VOP_WIN_ENABLE)
  If RockVopLatchFrame()=0 : rock_vop_error=84 : ProcedureReturn 0 : EndIf
  rock_vop_ready=1
  ProcedureReturn 1
EndProcedure

; Compatibility wrapper for isolated VOP tests. The display facade uses the
; three lifecycle phases so the encoder is enabled between background CRTC and
; primary-plane commit, matching rockchip_atomic_commit_complete().
Procedure.i RockVopUpMode()
  If RockVopPrepareMode()=0 : ProcedureReturn 0 : EndIf
  If RockVopConfigurePrimary()=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn RockVopStartPrimary()
EndProcedure

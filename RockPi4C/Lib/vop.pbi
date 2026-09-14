; RK3399 little VOP scanout path. The exact Rock Pi 4C graph routes
; vopl -> cdn_dp. Mode selection supplies a validated base-block DTD through
; the rock_mode_* ABI; this layer independently bounds every packed VOP field
; and the compiler-owned 32-bpp scan buffer before touching VOP MMIO.

#ROCK_VOPL = $FF8F0000
#ROCK_VOP_MAX_WIDTH = 2560
#ROCK_VOP_MAX_HEIGHT = 1600
#ROCK_VOP_TIMING_MAX = 8191
#ROCK_VOP_STRIDE_WORD_MAX = 16383
#ROCK_FB_MAX_WORDS = #ROCK_VOP_MAX_WIDTH*#ROCK_VOP_MAX_HEIGHT
#ROCK_FB_MAX_BYTES = #ROCK_FB_MAX_WORDS*4
#ROCK_FB_ALIGNMENT = 16

; WIN0_CTRL0 line-buffer modes used by the pinned Rockchip RGB helper.
#VOP_WIN_ENABLE = 1
#VOP_WIN_LB_MODE_SHIFT = 5
#VOP_WIN0_FORMAT_LB_ENABLE_MASK = $000000FF
#VOP_LB_RGB_2560X4 = 3
#VOP_LB_RGB_1920X5 = 4
; Rockchip's RK3368/RK3399-generation VOP driver programs both gather enables
; and uses three YRGB gathers plus one CBCR gather for ARGB8888 scanout.
#VOP_WIN0_GATHER_MASK = $00007F03
#VOP_WIN0_ARGB8888_GATHER = $00001303
#VOP_WIN0_YRGB_VSU_MODE_MASK = $00400000
#VOP_WIN0_YRGB_VSU_BIC = $00400000
#VOP_DSP_P888_PRE_DITHER = $00000002

#VOP_CFG_DONE = $000
#VOP_SYS_CTRL = $008
#VOP_SYS_CTRL1 = $00C
#VOP_DSP_CTRL0 = $010
#VOP_DSP_CTRL1 = $014
#VOP_WIN0_CTRL0 = $030
#VOP_WIN0_CTRL1 = $034
#VOP_WIN0_COLOR_KEY = $038
#VOP_WIN0_VIR = $03C
#VOP_WIN0_YRGB_MST = $040
#VOP_WIN0_ACT_INFO = $048
#VOP_WIN0_DSP_INFO = $04C
#VOP_WIN0_DSP_ST = $050
#VOP_WIN0_SCL_FACTOR = $054
#VOP_WIN2_CTRL0 = $0B0
#VOP_POST_HACT = $170
#VOP_POST_VACT = $174
#VOP_POST_SCL_FACTOR = $178
#VOP_POST_SCL_CTRL = $180
#VOP_HTOTAL = $188
#VOP_HACT = $18C
#VOP_VTOTAL = $190
#VOP_VACT = $194
#VOP_AFBCD0_CTRL = $200
#VOP_INTR_CLEAR0 = $284
#VOP_INTR_RAW_STATUS0 = $28C

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
; Global ordering is not an alignment contract. Reserve one alignment unit
; of slack and derive the scanout base within this compiler-owned object.
Global Dim rock_vop_framebuffer.l[#ROCK_FB_MAX_WORDS+4]

Procedure.i RockVopFramebuffer()
  ProcedureReturn (@rock_vop_framebuffer[0]+#ROCK_FB_ALIGNMENT-1) & $FFFFFFFFFFFFFFF0
EndProcedure

Procedure.i RockVopRead(offset.i)
  ProcedureReturn PeekL(#ROCK_VOPL+offset) & $FFFFFFFF
EndProcedure

Procedure RockVopWrite(offset.i, value.i)
  PokeL(#ROCK_VOPL+offset,value & $FFFFFFFF)
EndProcedure

Procedure RockVopField(offset.i, mask.i, value.i)
  Protected prior.i = RockVopRead(offset)
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

Procedure.i RockVopUpMode()
  Protected value.i
  Protected pinPolarity.i
  Protected lineBufferMode.i
  Protected hsyncLength.i
  Protected vsyncLength.i
  Protected hactiveStart.i
  Protected hactiveEnd.i
  Protected vactiveStart.i
  Protected vactiveEnd.i
  rock_vop_ready=0
  rock_vop_error=0
  If RockVopModeValid()=0 : ProcedureReturn 0 : EndIf
  lineBufferMode=RockVopLineBufferMode(rock_mode_width)
  If lineBufferMode < 0 : rock_vop_error=80 : ProcedureReturn 0 : EndIf
  hsyncLength=rock_mode_hsync_end-rock_mode_hsync_start
  vsyncLength=rock_mode_vsync_end-rock_mode_vsync_start
  hactiveStart=rock_mode_htotal-rock_mode_hsync_start
  hactiveEnd=hactiveStart+rock_mode_width
  vactiveStart=rock_mode_vtotal-rock_mode_vsync_start
  vactiveEnd=vactiveStart+rock_mode_height
  If RockCruVopRelease()=0 : rock_vop_error=71 : ProcedureReturn 0 : EndIf
  ; The reference driver pulses the HCLK reset after clocks and power exist.
  RockCruReset(279,1)
  RockTimerWaitUs(20)
  RockCruReset(279,0)
  ; vop_initial() in the pinned RK3399 driver enables the maximum 30 AXI
  ; reads outstanding. Reset defaults can feed the proven 1024x768 mode but
  ; build 57 latched POST_BUF_EMPTY at 1080p. Program the documented VOP
  ; throughput contract explicitly before scanout is armed.
  RockVopField(#VOP_SYS_CTRL1,$0003F000,$0003D000)
  ; vop_initial()/vop_disable_allwin() in the pinned RK3399 Linux driver
  ; explicitly disables AFBCD and every declared little-VOP plane before the
  ; new primary plane is configured.  VOPL has WIN0 and WIN2; WIN1/WIN3/HWC
  ; are not members of its topology.  Establish that same clean state after
  ; the now-released DCLK reset instead of depending on a bootloader shadow.
  RockVopField(#VOP_AFBCD0_CTRL,$00000001,0)
  RockVopField(#VOP_WIN0_CTRL0,$00000001,0)
  ; WIN2's declared cursor plane has a separate gate bit (b0) and enable bit
  ; (b4). vop_disable_allwin() clears both; inheriting either from a previous
  ; firmware owner violates the Linux clean-start sequence.
  RockVopField(#VOP_WIN2_CTRL0,$00000011,0)
  ; Route the Cadence transmitter from the little VOP (GRF SOC_CON9 bit12).
  PokeL(#ROCK_GRF+$6224,$10001000)
  RockVopFirstFrame()
  ; RK3399 VOP pin polarity uses positive-pulse bits; Cadence's independent
  ; MSA/framer polarity fields use negative-pulse semantics.
  pinPolarity=0
  If rock_mode_hsync_positive <> 0 : pinPolarity=pinPolarity | 1 : EndIf
  If rock_mode_vsync_positive <> 0 : pinPolarity=pinPolarity | 2 : EndIf
  ; cdn_dp requests AAAA, but RK3399 VOPL has no 10-bit-output feature.
  ; The pinned DRM driver therefore selects P888 and unconditionally enables
  ; pre-dither for that mode before the post/output formatter is started.
  RockVopField(#VOP_DSP_CTRL1,$000F0012,(pinPolarity << 16) | #VOP_DSP_P888_PRE_DITHER)
  value=RockVopRead(#VOP_SYS_CTRL)
  value=(value & $FFBF07FF) | $00000800
  RockVopWrite(#VOP_SYS_CTRL,value)
  RockVopField(#VOP_DSP_CTRL0,$F,0)
  RockVopWrite(#VOP_HTOTAL,hsyncLength | (rock_mode_htotal << 16))
  RockVopWrite(#VOP_HACT,hactiveEnd | (hactiveStart << 16))
  RockVopWrite(#VOP_VTOTAL,vsyncLength | (rock_mode_vtotal << 16))
  RockVopWrite(#VOP_VACT,vactiveEnd | (vactiveStart << 16))
  RockVopWrite(#VOP_POST_HACT,hactiveEnd | (hactiveStart << 16))
  RockVopWrite(#VOP_POST_VACT,vactiveEnd | (vactiveStart << 16))
  RockVopWrite(#VOP_POST_SCL_FACTOR,#VOP_SCALE_UNITY_XY)
  RockVopField(#VOP_POST_SCL_CTRL,$3,0)
  RockVopWrite(#VOP_WIN0_ACT_INFO,(rock_mode_width-1) | ((rock_mode_height-1) << 16))
  RockVopWrite(#VOP_WIN0_DSP_ST,hactiveStart | (vactiveStart << 16))
  RockVopWrite(#VOP_WIN0_DSP_INFO,(rock_mode_width-1) | ((rock_mode_height-1) << 16))
  RockVopWrite(#VOP_WIN0_SCL_FACTOR,#VOP_SCALE_UNITY_XY)
  RockVopWrite(#VOP_WIN0_COLOR_KEY,0)
  RockVopWrite(#VOP_WIN0_VIR,rock_mode_pitch >> 2)
  ; scl_vop_cal_scl_fac() selects the 5-line RGB buffer at 1920 pixels and
  ; programs YRGB vertical-up mode BIC even when the scale modes themselves
  ; are NONE. Own that active-path field instead of inheriting its reset value.
  RockVopField(#VOP_WIN0_CTRL1,#VOP_WIN0_GATHER_MASK | #VOP_WIN0_YRGB_VSU_MODE_MASK,#VOP_WIN0_ARGB8888_GATHER | #VOP_WIN0_YRGB_VSU_BIC)
  ; VOP_LIT WIN0_CTRL0 resets to $3A000040: bits29:25 carry the documented
  ; per-window AXI outstanding limit ($1D). Linux programs format, line-buffer
  ; mode and enable through field updates, preserving those throughput bits.
  ; A full $81 write erased them and the live 1080p path then starved only the
  ; post FIFO. Own the low functional byte while retaining the reset-owned AXI
  ; contract established by RockCruVopRelease().
  RockVopField(#VOP_WIN0_CTRL0,#VOP_WIN0_FORMAT_LB_ENABLE_MASK,#VOP_WIN_ENABLE | (lineBufferMode << #VOP_WIN_LB_MODE_SHIFT))
  RockVopWrite(#VOP_WIN0_YRGB_MST,RockVopFramebuffer())
  RockVopWrite(#VOP_CFG_DONE,1)
  ; Linux writel()/U-Boot writel() order device MMIO before the following CRU
  ; reset write.  Preserve that contract explicitly: CFG_DONE must reach VOPL
  ; before the real DCLK assert/deassert pulse is started.
  ASM
    dsb sy
  ENDASM
  ; Latch the new pixel clock into the VOP only after every timing register and
  ; scan address is valid.
  RockCruReset(281,1)
  RockTimerWaitUs(20)
  RockCruReset(281,0)
  RockVopWrite(#VOP_CFG_DONE,1)
  ASM
    dsb sy
  ENDASM
  rock_vop_ready=1
  ProcedureReturn 1
EndProcedure

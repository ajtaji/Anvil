; RK3399 little VOP first-light path. The exact Rock Pi 4C graph routes
; vopl -> cdn_dp. This milestone intentionally accepts only the standard
; EDID-established 1024x768@60 mode: 65 MHz, 1344x806 totals, negative sync.
; The static 32-bpp scan buffer stays inside the compiler-owned BSS window.

#ROCK_VOPL = $FF8F0000
#ROCK_FB_WIDTH = 1024
#ROCK_FB_HEIGHT = 768
#ROCK_FB_WORDS = 786432

#VOP_CFG_DONE = $000
#VOP_SYS_CTRL = $008
#VOP_DSP_CTRL0 = $010
#VOP_DSP_CTRL1 = $014
#VOP_WIN0_CTRL0 = $030
#VOP_WIN0_COLOR_KEY = $038
#VOP_WIN0_VIR = $03C
#VOP_WIN0_YRGB_MST = $040
#VOP_WIN0_ACT_INFO = $048
#VOP_WIN0_DSP_INFO = $04C
#VOP_WIN0_DSP_ST = $050
#VOP_POST_HACT = $170
#VOP_POST_VACT = $174
#VOP_HTOTAL = $188
#VOP_HACT = $18C
#VOP_VTOTAL = $190
#VOP_VACT = $194

Global rock_vop_ready.i
Global rock_vop_error.i
Global Dim rock_vop_framebuffer.l[#ROCK_FB_WORDS]

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
  For row=0 To 6
    bits=RockVopGlyphRow(character,row)
    For column=0 To 4
      If (bits & (16 >> column)) <> 0
        For dy=0 To scale-1
          address=@rock_vop_framebuffer[0]+((y0+row*scale+dy)*#ROCK_FB_WIDTH+x0+column*scale)*4
          For dx=0 To scale-1
            PokeL(address+dx*4,colour)
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
  Protected colour.i
  Protected address.i
  For y=0 To #ROCK_FB_HEIGHT-1
    For x=0 To #ROCK_FB_WIDTH-1
      Select x >> 7
        Case 0 : colour=$FFFFFFFF
        Case 1 : colour=$FFFFFF00
        Case 2 : colour=$FF00FFFF
        Case 3 : colour=$FF00FF00
        Case 4 : colour=$FFFF00FF
        Case 5 : colour=$FFFF0000
        Case 6 : colour=$FF0000FF
        Default : colour=$FF101010
      EndSelect
      If y >= 640 : colour=$FF101010 : EndIf
      address=@rock_vop_framebuffer[0]+(y*#ROCK_FB_WIDTH+x)*4
      PokeL(address,colour)
    Next
  Next
  RockVopText("ANVIL ROCK PI 4C",32,684,4,$FF40FF40)
  ASM
    dsb sy
  ENDASM
EndProcedure

Procedure.i RockVopUp1024x768()
  Protected value.i
  rock_vop_ready=0
  rock_vop_error=0
  If RockCruVopRelease()=0 : rock_vop_error=71 : ProcedureReturn 0 : EndIf
  ; The reference driver pulses the HCLK reset after clocks and power exist.
  RockCruReset(279,1)
  RockTimerWaitUs(20)
  RockCruReset(279,0)
  ; Route the Cadence transmitter from the little VOP (GRF SOC_CON9 bit12).
  PokeL(#ROCK_GRF+$6224,$10001000)
  RockVopFirstFrame()
  ; Negative H/V sync and inverted DCLK: DP polarity nibble 8 at bits19:16.
  RockVopField(#VOP_DSP_CTRL1,$000F0000,$00080000)
  value=RockVopRead(#VOP_SYS_CTRL)
  value=(value & $FFBF07FF) | $00000800
  RockVopWrite(#VOP_SYS_CTRL,value)
  RockVopField(#VOP_DSP_CTRL0,$F,0)
  RockVopWrite(#VOP_HTOTAL,136 | (1344 << 16))
  RockVopWrite(#VOP_HACT,1320 | (296 << 16))
  RockVopWrite(#VOP_VTOTAL,6 | (806 << 16))
  RockVopWrite(#VOP_VACT,803 | (35 << 16))
  RockVopWrite(#VOP_POST_HACT,1320 | (296 << 16))
  RockVopWrite(#VOP_POST_VACT,803 | (35 << 16))
  RockVopWrite(#VOP_WIN0_ACT_INFO,1023 | (767 << 16))
  RockVopWrite(#VOP_WIN0_DSP_ST,296 | (35 << 16))
  RockVopWrite(#VOP_WIN0_DSP_INFO,1023 | (767 << 16))
  RockVopWrite(#VOP_WIN0_COLOR_KEY,0)
  RockVopWrite(#VOP_WIN0_VIR,1024)
  RockVopWrite(#VOP_WIN0_CTRL0,$A1)
  RockVopWrite(#VOP_WIN0_YRGB_MST,@rock_vop_framebuffer[0])
  RockVopWrite(#VOP_CFG_DONE,1)
  ; Latch the new pixel clock into the VOP only after every timing register and
  ; scan address is valid.
  RockCruReset(281,1)
  RockTimerWaitUs(20)
  RockCruReset(281,0)
  RockVopWrite(#VOP_CFG_DONE,1)
  rock_vop_ready=1
  ProcedureReturn 1
EndProcedure

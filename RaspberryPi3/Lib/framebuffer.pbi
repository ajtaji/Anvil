; Pi 3 HDMI display memory. Allocate firmware scanout once during EL3 cold
; start, then draw only to the reserved NC render buffer. The scanout is
; updated only by DMA; a refused or unsafe DMA channel disables graphics
; instead of allowing CPU writes to the visible framebuffer.
Global Dim pi3_fb_message.l[48]
Global pi3_fb.i
Global pi3_fb_scanout.i
; A normal-sized 1920x1200 32-bit display fits. This monitor refuses larger
; pitch*height allocations rather than falling back to CPU writes on scanout.
#PI3_FB_RENDER_BASE = $3000000
#PI3_FB_RENDER_BYTES = 9216000
Global pi3_fb_render_bytes.i
Global pi3_fb_dirty.i
Global pi3_fb_dirty_left.i
Global pi3_fb_dirty_top.i
Global pi3_fb_dirty_right.i
Global pi3_fb_dirty_bottom.i
Global pi3_fb_present_pending.i
Global pi3_fb_present_left.i
Global pi3_fb_present_top.i
Global pi3_fb_present_right.i
Global pi3_fb_present_bottom.i
Global pi3_fb_clear_pending.i
Global pi3_fb_pitch.i
Global pi3_fb_size.i
Global pi3_fb_attempted.i
Global pi3_fb_attached.i
Global pi3_fb_boot_dtb.i
Global pi3_fb_boot_dtb_end.i
Global pi3_fb_boot_ram_base.i
Global pi3_fb_boot_ram_end.i
Global pi3_fb_vc_base.i
Global pi3_fb_vc_bytes.i
Global pi3_fb_deferred_ready.i
Global pi3_fb_ddc_clock.i
Global pi3_fb_attach_phase.i
Global pi3_fb_attach_reconnect.i
; Preserve the first failed attach transaction across quarantine cleanup.
; DETACH submits its own BLANK request through the shared property buffer, so
; reading that buffer after quarantine otherwise reports cleanup, not cause.
Global pi3_fb_attach_error_phase.i
Global pi3_fb_attach_error_rc.i
Global pi3_fb_attach_error_size.i
Global pi3_fb_attach_error_code.i
Global pi3_fb_attach_error_tag.i
Global pi3_fb_attach_error_value_bytes.i
Global pi3_fb_attach_error_reply.i
Global pi3_fb_attach_error_value0.i
Global pi3_fb_attach_error_value1.i
Global pi3_fb_edid_phase.i
Global pi3_fb_edid_got.i
Global pi3_fb_edid_start.i
Global pi3_fb_t_clock.i
Global pi3_fb_t_w.i : Global pi3_fb_t_h.i
Global pi3_fb_t_hs.i : Global pi3_fb_t_he.i : Global pi3_fb_t_ht.i
Global pi3_fb_t_vs.i : Global pi3_fb_t_ve.i : Global pi3_fb_t_vt.i
Global pi3_fb_t_flags.i
Global pi3_fb_detach_phase.i
Global pi3_fb_blank_expected.i
Global pi3_fb_initial_probe=1
Global pi3_fb_initial_connected.i
Global pi3_fb_column.i
Global pi3_fb_row.i
Global pi3_fb_width.i
Global pi3_fb_height.i
Global pi3_fb_pixel_order.i
Global pi3_fb_alpha_mode.i
Global pi3_fb_error.i
Global pi3_fb_edid_status.i
Global pi3_fb_mode_source.i
Global pi3_fb_requested_width.i
Global pi3_fb_requested_height.i
Global pi3_fb_dma_state.i
Global pi3_fb_dma_error.i
Global pi3_fb_dma_active.i
Global pi3_fb_dma_cb.i
Global pi3_fb_dma_start_us.i
; Diagnostics are latched before abort/reset; these never affect DMA policy.
Global pi3_fb_dma_submissions.i
Global pi3_fb_dma_completions.i
Global pi3_fb_dma_last_us.i
Global pi3_fb_dma_fail_cs.i
Global pi3_fb_dma_fail_conblk.i
Global pi3_fb_dma_fail_debug.i
Global pi3_fb_dma_fail_ti.i
Global pi3_fb_dma_fail_src.i
Global pi3_fb_dma_fail_dst.i
Global pi3_fb_dma_fail_length.i
Global pi3_fb_dma_fail_stride.i
Global pi3_fb_dma_fail_elapsed_us.i
Global pi3_fb_dma_fail_current_ti.i
Global pi3_fb_dma_fail_current_src.i
Global pi3_fb_dma_fail_current_dst.i
Global pi3_fb_dma_fail_current_length.i
Global pi3_fb_dma_fail_current_stride.i
Global pi3_fb_scroll_phase.i
Global pi3_fb_scroll_top.i
Global pi3_fb_scroll_height.i
Global pi3_fb_scroll_keep.i
Global pi3_fb_scroll_lines.i
Global pi3_fb_scroll_next_row.i
Global pi3_fb_scroll_next_word.i
Global pi3_fb_scroll_colour.i
Global Dim pi3_fb_edid_blocks.a[#ANVIL_EDID_MAX_BLOCKS * #ANVIL_EDID_BLOCK_BYTES]
Declare.i Pi3FbDmaStopSafe(channel.i)
Declare.i Pi3FbDmaPoll()
Declare.i Pi3FbPresentPoll()
Declare.i Pi3FbScrollPoll()

#PI3_FB_EDID_NONE = 0
#PI3_FB_EDID_VALID = 1
#PI3_FB_EDID_ABSENT = 2
#PI3_FB_EDID_INVALID = 3
#PI3_FB_EDID_TRUNCATED = 4
#PI3_FB_EDID_TRANSPORT = 5

#PI3_FB_MODE_EDID_PREFERRED = 1
#PI3_FB_MODE_FIRMWARE_CURRENT = 2
#PI3_FB_MODE_SAFE_FALLBACK = 3
#PI3_FB_MODE_FIRMWARE_ADJUSTED = 4
#PI3_FB_MODE_FIRMWARE_INHERITED = 5
#PI3_FB_EDID_BUDGET_US = 250000
#PI3_FB_PROPERTY_BUDGET_US = 250000
#PI3_FB_DDC_BASE = $3F805000
#PI3_FB_I2C_C = 0
#PI3_FB_I2C_S = 4
#PI3_FB_I2C_DLEN = 8
#PI3_FB_I2C_A = 12
#PI3_FB_I2C_FIFO = 16
#PI3_FB_I2C_DIV = 20
#PI3_FB_I2C_DEL = 24
#PI3_FB_I2C_CLKT = 28
#PI3_FB_I2C_C_READ = 1
#PI3_FB_I2C_C_CLEAR = $30
#PI3_FB_I2C_C_ST = $80
#PI3_FB_I2C_C_INTD = $100
#PI3_FB_I2C_C_INTT = $200
#PI3_FB_I2C_C_INTR = $400
#PI3_FB_I2C_C_I2CEN = $8000
#PI3_FB_I2C_S_TA = 1
#PI3_FB_I2C_S_DONE = 2
#PI3_FB_I2C_S_TXD = $10
#PI3_FB_I2C_S_RXD = $20
#PI3_FB_I2C_S_ERR = $100
#PI3_FB_I2C_S_CLKT = $200
#PI3_FB_DDC_ADDR_EDID = $50
#PI3_FB_DDC_ADDR_SEGMENT = $30
#PI3_FB_DDC_HZ = 100000

#PI3_FB_ERR_NONE        = 0
#PI3_FB_ERR_OWNERSHIP   = 1
#PI3_FB_ERR_MAILBOX     = 2
#PI3_FB_ERR_TAG_REPLY   = 3
#PI3_FB_ERR_GEOMETRY    = 4
#PI3_FB_ERR_PIXEL_ORDER = 5
#PI3_FB_ERR_ALPHA_MODE  = 6
#PI3_FB_ERR_ALLOCATION  = 7
#PI3_FB_ERR_VC_RANGE    = 8
#PI3_FB_ERR_OVERLAP     = 9

; ======================================================================
; BOUNDED DISPLAY SCROLL DMA
;
; The firmware framebuffer and the CB/pattern scratch below are in the
; monitor's Normal-NC map. That is deliberate: this path does not guess
; about Cortex-A53 cache maintenance or hand a stale CB to a bus master.
; Channel 5 is a general full DMA channel. Linux's BCM2835 binding lists
; firmware channels 1/3/6/7 as reserved and marks 0/2/3 special; we still
; inspect the live channel before enabling it and fall back if it is busy.
;
; Full-width upward console scroll and large solid fills use this interface.
; Scroll copies rows top-to-bottom because each destination precedes its
; source, then fills the vacated rows. Any setup
; refusal uses bounded CPU row copies. A timeout that cannot prove channel
; quiescence quarantines the surface; callers must stop drawing there.
; ======================================================================

#PI3_FB_DMA_BASE = $3F007000
#PI3_FB_DMA_CHAN = 5
#PI3_FB_DMA_CS = 0
#PI3_FB_DMA_CONBLK = 4
#PI3_FB_DMA_TI = $08
#PI3_FB_DMA_SOURCE = $0C
#PI3_FB_DMA_DEST = $10
#PI3_FB_DMA_LENGTH = $14
#PI3_FB_DMA_STRIDE = $18
#PI3_FB_DMA_DEBUG = $20
#PI3_FB_DMA_GLOBAL_ENABLE = $FF0
#PI3_FB_DMA_ACTIVE = 1
#PI3_FB_DMA_END = 2
#PI3_FB_DMA_ERROR = $100
#PI3_FB_DMA_WAITING_WRITES = $40
#PI3_FB_DMA_RESET = $80000000
#PI3_FB_DMA_ABORT = $40000000
#PI3_FB_DMA_TI_TDMODE = 2
#PI3_FB_DMA_TI_WAIT_RESP = 8
#PI3_FB_DMA_TI_D_WIDTH = $20
#PI3_FB_DMA_TI_S_WIDTH = $200
#PI3_FB_DMA_BURST_SIZE = 2
#PI3_FB_DMA_TI_BURST = #PI3_FB_DMA_BURST_SIZE<<12
#PI3_FB_DMA_FILL_TILE_BYTES = 48
#PI3_FB_DMA_TI_DEST_INC = $10
#PI3_FB_DMA_TI_SRC_INC = $100
#PI3_FB_DMA_BUS_ALIAS = $C0000000
#PI3_FB_DMA_BUS_MASK = $3FFFFFFF
#PI3_FB_DMA_TIMEOUT_US = 100000
#PI3_FB_DMA_STOP_TIMEOUT_US = 2000
#PI3_FB_DMA_MIN_BYTES = 32768

#PI3_FB_DMA_E_NONE = 0
#PI3_FB_DMA_E_BUSY = 1
#PI3_FB_DMA_E_TIMEOUT = 2
#PI3_FB_DMA_E_ENGINE = 3
#PI3_FB_DMA_E_UNSAFE = 4

; 0 = not probed, 1 = channel available, 2 = DMA refused (graphics off),
; 3 = another/uncertain owner prevents safe use (graphics off).
Procedure.i Pi3FbPack(red.i,green.i,blue.i)
  Protected alpha.i
  red=red & 255 : green=green & 255 : blue=blue & 255
  ; Alpha mode 0 defines zero as opaque; mode 1 reverses it. Mode 2 ignores
  ; the byte. The firmware is allowed to return any of the three even when
  ; the caller requested another, so the stored word follows the reply.
  alpha=0
  If pi3_fb_alpha_mode=1 : alpha=255 : EndIf
  If pi3_fb_pixel_order=1
    ; RGB means byte order R,G,B in little-endian framebuffer memory.
    ProcedureReturn red | (green << 8) | (blue << 16) | (alpha << 24)
  EndIf
  ; BGR means byte order B,G,R.  Both orders are valid firmware replies.
  ProcedureReturn blue | (green << 8) | (red << 16) | (alpha << 24)
EndProcedure

Procedure Pi3FbTag(buffer.i,offset.i,tag.i,length.i,a.i,b.i)
  PokeL(buffer+offset,tag) : PokeL(buffer+offset+4,length)
  PokeL(buffer+offset+8,0) : PokeL(buffer+offset+12,a)
  If length=8 : PokeL(buffer+offset+16,b) : EndIf
EndProcedure

Procedure Pi3FbChar(code.i,x.i,y.i)
  Protected glyph.i
  Protected row.i
  Protected col.i
  Protected sx.i
  Protected sy.i
  Protected foreground.i
  If pi3_fb=0
    ProcedureReturn
  EndIf
    foreground=Pi3FbPack(240,224,192)
    glyph=AnvilTextGlyph(code)
    For row=0 To 6
      For col=0 To 3
        If (glyph & (1 << ((6-row)*4+3-col)))<>0
          For sy=0 To 2
            For sx=0 To 2 : Pi3FbPixel(x+col*3+sx,y+row*3+sy,foreground) : Next
          Next
        EndIf
      Next
    Next
EndProcedure

Procedure Pi3FbNewline()
  Protected y.i
  Protected x.i
  Protected background.i
  pi3_fb_column=0 : pi3_fb_row=pi3_fb_row+1
  If pi3_fb_row<pi3_fb_height/24 : ProcedureReturn 0 : EndIf
  ; Upward copy is forward: source is always above destination, no clobber.
  For y=0 To pi3_fb_height-25
    For x=0 To pi3_fb_width-1
      PokeL(pi3_fb+y*pi3_fb_pitch+x*4,PeekL(pi3_fb+(y+24)*pi3_fb_pitch+x*4))
    Next
  Next
  background=Pi3FbPack(24,12,8)
  For y=pi3_fb_height-24 To pi3_fb_height-1
    For x=0 To pi3_fb_width-1 : PokeL(pi3_fb+y*pi3_fb_pitch+x*4,background) : Next
  Next
  Pi3FbDirtyAdd(0,0,pi3_fb_width,pi3_fb_height)
  pi3_fb_row=pi3_fb_height/24-1
EndProcedure

Procedure Pi3FbLine(text.i)
  Protected n.i
  Protected code.i
  If pi3_fb=0 : ProcedureReturn 0 : EndIf
  For n=0 To 255
    code=PeekA(text+n) : If code=0 : Break : EndIf
    If code=10
      Pi3FbNewline()
    ElseIf code<>13
      If pi3_fb_column>=pi3_fb_width/15 : Pi3FbNewline() : EndIf
      Pi3FbChar(code,pi3_fb_column*15,pi3_fb_row*24)
      pi3_fb_column=pi3_fb_column+1
    EndIf
  Next
  Pi3FbNewline()
  If Pi3FbPresentBegin()=1
    While Pi3FbPresentPending()<>0
      If Pi3FbPresentPoll()<0 : Break : EndIf
    Wend
  EndIf
EndProcedure

Procedure.i Pi3FbReply(buffer.i,offset.i,tag.i,length.i)
  Protected reply.i
  If PeekL(buffer+offset)<>tag Or PeekL(buffer+offset+4)<>length : ProcedureReturn 0 : EndIf
  reply=PeekL(buffer+offset+8) & $FFFFFFFF
  If (reply & $80000000)=0 : ProcedureReturn 0 : EndIf
  ; The official property contract permits a future response length larger
  ; than the supplied value buffer. Fields through the known prefix remain
  ; valid; requiring exact equality would reject a compatible firmware.
  ProcedureReturn Bool((reply & $7FFFFFFF)>=length)
EndProcedure

; SET_TIMING is a no-payload set operation on the deployed Pi 3 firmware: a
; successful overall property response may leave its tag length at zero.  A
; flagged response must still cover the known structure.  Callers always
; follow this acceptance with strict GET_TIMING field-for-field validation.
Procedure.i Pi3FbSetTimingReply(buffer.i,offset.i)
  Protected reply.i
  If PeekL(buffer+offset)<>$48017 Or PeekL(buffer+offset+4)<>36 : ProcedureReturn 0 : EndIf
  reply=PeekL(buffer+offset+8)&$FFFFFFFF
  If reply=0 : ProcedureReturn 1 : EndIf
  ProcedureReturn Bool((reply&$80000000)<>0 And (reply&$7FFFFFFF)>=36)
EndProcedure

; Read one BSC2 transmit packet with an overall transaction deadline.
Procedure.i pi3_fb_DdcWrite(address.i, value.i, startUs.i)
  Protected reg.i = #PI3_FB_DDC_BASE
  Protected status.i
  Protected now.i
  Protected sent.i = 0
  PokeL(reg+#PI3_FB_I2C_S, #PI3_FB_I2C_S_DONE|#PI3_FB_I2C_S_ERR|#PI3_FB_I2C_S_CLKT)
  PokeL(reg+#PI3_FB_I2C_C, #PI3_FB_I2C_C_I2CEN|#PI3_FB_I2C_C_CLEAR)
  PokeL(reg+#PI3_FB_I2C_A, address)
  PokeL(reg+#PI3_FB_I2C_DLEN, 1)
  PokeL(reg+#PI3_FB_I2C_C, #PI3_FB_I2C_C_I2CEN|#PI3_FB_I2C_C_ST|#PI3_FB_I2C_C_INTT|#PI3_FB_I2C_C_INTD)
  Repeat
    status=PeekL(reg+#PI3_FB_I2C_S)
    If (status & (#PI3_FB_I2C_S_ERR|#PI3_FB_I2C_S_CLKT))<>0 : ProcedureReturn 0 : EndIf
    If sent=0 And (status & #PI3_FB_I2C_S_TXD)<>0
      PokeL(reg+#PI3_FB_I2C_FIFO, value & 255) : sent=1
    EndIf
    If (status & #PI3_FB_I2C_S_DONE)<>0 : Break : EndIf
    now=Pi3Micros()
    If now<startUs Or now-startUs>=#PI3_FB_EDID_BUDGET_US : ProcedureReturn 0 : EndIf
  ForEver
  PokeL(reg+#PI3_FB_I2C_S, #PI3_FB_I2C_S_DONE)
  ProcedureReturn Bool(sent=1)
EndProcedure

; Read a bounded FIFO transaction. The caller drains bytes continuously while
; the peripheral fills its 16-byte FIFO, all against the same boot deadline.
Procedure.i pi3_fb_DdcRead(address.i, *dst, count.i, startUs.i)
  Protected reg.i = #PI3_FB_DDC_BASE
  Protected status.i
  Protected now.i
  Protected got.i = 0
  If count<1 Or count>128 : ProcedureReturn 0 : EndIf
  PokeL(reg+#PI3_FB_I2C_S, #PI3_FB_I2C_S_DONE|#PI3_FB_I2C_S_ERR|#PI3_FB_I2C_S_CLKT)
  PokeL(reg+#PI3_FB_I2C_C, #PI3_FB_I2C_C_I2CEN|#PI3_FB_I2C_C_CLEAR)
  PokeL(reg+#PI3_FB_I2C_A, address)
  PokeL(reg+#PI3_FB_I2C_DLEN, count)
  PokeL(reg+#PI3_FB_I2C_C, #PI3_FB_I2C_C_I2CEN|#PI3_FB_I2C_C_ST|#PI3_FB_I2C_C_READ|#PI3_FB_I2C_C_INTR|#PI3_FB_I2C_C_INTD)
  Repeat
    status=PeekL(reg+#PI3_FB_I2C_S)
    If (status & (#PI3_FB_I2C_S_ERR|#PI3_FB_I2C_S_CLKT))<>0 : ProcedureReturn 0 : EndIf
    While got<count And (status & #PI3_FB_I2C_S_RXD)<>0
      PokeA(*dst+got,PeekL(reg+#PI3_FB_I2C_FIFO)) : got=got+1
      status=PeekL(reg+#PI3_FB_I2C_S)
    Wend
    If (status & #PI3_FB_I2C_S_DONE)<>0 : Break : EndIf
    now=Pi3Micros()
    If now<startUs Or now-startUs>=#PI3_FB_EDID_BUDGET_US : ProcedureReturn 0 : EndIf
  ForEver
  PokeL(reg+#PI3_FB_I2C_S, #PI3_FB_I2C_S_DONE)
  ProcedureReturn Bool(got=count)
EndProcedure

; Native Pi3 HDMI DDC is BCM2835 BSC2 at physical 0x3F805000, bound to the
; dedicated HDMI_SDA/SCL pins. The firmware mailbox is never asked for EDID.
Procedure.i Pi3FbReadEdid(vpuClockCeilingHz.i)
  Protected block.i
  Protected received.i
  Protected expected.i
  Protected truncated.i
  Protected start.i
  Protected now.i
  Protected divider.i
  Protected redl.i
  Protected segment.i
  Protected offset.i
  Protected copyByte.i
  Protected Dim edidBlock.a[128]
  AnvilEdidReset()
  pi3_fb_edid_status=#PI3_FB_EDID_TRANSPORT
  If vpuClockCeilingHz<1000000 : ProcedureReturn 0 : EndIf
  ; Firmware may still own an HDMI DDC transaction. Do not reset or steal an
  ; active BSC2 controller; an idle timeout is a safe discovery failure.
  If (PeekL(#PI3_FB_DDC_BASE+#PI3_FB_I2C_S) & #PI3_FB_I2C_S_TA)<>0 : ProcedureReturn 0 : EndIf
  divider=(vpuClockCeilingHz+#PI3_FB_DDC_HZ-1)/#PI3_FB_DDC_HZ
  If divider & 1 : divider=divider+1 : EndIf
  If divider<2 Or divider>65534 : ProcedureReturn 0 : EndIf
  PokeL(#PI3_FB_DDC_BASE+#PI3_FB_I2C_C, #PI3_FB_I2C_C_I2CEN|#PI3_FB_I2C_C_CLEAR)
  PokeL(#PI3_FB_DDC_BASE+#PI3_FB_I2C_CLKT, 0)
  PokeL(#PI3_FB_DDC_BASE+#PI3_FB_I2C_DIV, divider)
  redl=divider/4 : If redl<1 : redl=1 : EndIf
  PokeL(#PI3_FB_DDC_BASE+#PI3_FB_I2C_DEL, ((divider/16)<<16)|redl)
  received=0 : expected=1 : truncated=0
  start=Pi3Micros()
  If start<0
    pi3_fb_edid_status=#PI3_FB_EDID_TRANSPORT
    ProcedureReturn 0
  EndIf
  For block=0 To #ANVIL_EDID_MAX_BLOCKS-1
    If block>=expected : Break : EndIf
    now=Pi3Micros()
    If now<start Or now-start>=#PI3_FB_EDID_BUDGET_US
      truncated=1
      If block=0 : pi3_fb_edid_status=#PI3_FB_EDID_TRANSPORT : ProcedureReturn 0 : EndIf
      Break
    EndIf
    segment=block/2 : offset=(block & 1)*128
    If block>1
      If pi3_fb_DdcWrite(#PI3_FB_DDC_ADDR_SEGMENT,segment,start)=0
        If block=0 : pi3_fb_edid_status=#PI3_FB_EDID_TRANSPORT : ProcedureReturn 0 : EndIf
        truncated=1 : Break
      EndIf
    EndIf
    If pi3_fb_DdcWrite(#PI3_FB_DDC_ADDR_EDID,offset,start)=0 Or pi3_fb_DdcRead(#PI3_FB_DDC_ADDR_EDID,@edidBlock[0],128,start)=0
      If block=0 : pi3_fb_edid_status=#PI3_FB_EDID_TRANSPORT : ProcedureReturn 0 : EndIf
      truncated=1 : Break
    EndIf
    For copyByte=0 To #ANVIL_EDID_BLOCK_BYTES-1
      PokeA(@pi3_fb_edid_blocks[received*#ANVIL_EDID_BLOCK_BYTES]+copyByte,PeekA(@edidBlock[copyByte]))
    Next
    received=received+1
    If block=0
      ; Validate the base block before trusting its extension count.
      If AnvilEdidParse(@pi3_fb_edid_blocks[0],128,1,0)=0
        pi3_fb_edid_status=#PI3_FB_EDID_INVALID
        ProcedureReturn 0
      EndIf
      expected=AnvilEdidExtensionCount()+1
      If expected>#ANVIL_EDID_MAX_BLOCKS
        expected=#ANVIL_EDID_MAX_BLOCKS
        truncated=1
      EndIf
    EndIf
  Next
  If AnvilEdidParse(@pi3_fb_edid_blocks[0],received*128,received,truncated)=0
    pi3_fb_edid_status=#PI3_FB_EDID_INVALID
    ProcedureReturn 0
  EndIf
  If truncated<>0 Or AnvilEdidTruncated()<>0 Or AnvilEdidError()<>#ANVIL_EDID_E_NONE
    pi3_fb_edid_status=#PI3_FB_EDID_TRUNCATED
  Else
    pi3_fb_edid_status=#PI3_FB_EDID_VALID
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3FbCurrentMode(*width,*height)
  Protected p.i
  Protected w.i
  Protected h.i
  p=((@pi3_fb_message[0]+15)>>4)<<4
  For w=0 To 31 Step 4 : PokeL(p+w,0) : Next
  PokeL(p,32) : PokeL(p+4,0)
  PokeL(p+8,$40003) : PokeL(p+12,8)
  PokeL(p+16,0) : PokeL(p+20,0) : PokeL(p+24,0) : PokeL(p+28,0)
  If Pi3MailboxCallTimeout(p,32,#PI3_FB_EDID_BUDGET_US)=0 Or Pi3FbReply(p,8,$40003,8)=0
    ProcedureReturn 0
  EndIf
  w=PeekL(p+20)&$FFFFFFFF : h=PeekL(p+24)&$FFFFFFFF
  If w<1 Or w>8192 Or h<1 Or h>8192 : ProcedureReturn 0 : EndIf
  PokeI(*width,w) : PokeI(*height,h)
  ProcedureReturn 1
EndProcedure

; Firmware KMS uses display 2 for HDMI0. SET_TIMING is the firmware-owned
; modeset path; SET_PHYSICAL_SIZE alone only changes framebuffer geometry.
; The EDID base preferred DTD supplies every timing field used here. Read the
; timing back before allowing a framebuffer to become visible.
Procedure.i Pi3FbSetPreferredTiming()
  Protected p.i,n.i,flags.i
  Protected clock.i,w.i,h.i
  Protected hs.i,he.i,ht.i,vs.i,ve.i,vt.i
  If AnvilEdidPreferredTimingValid()=0 Or AnvilEdidPreferredInterlaced()<>0 Or AnvilEdidPreferredSeparateSync()=0
    ProcedureReturn 0
  EndIf
  clock=AnvilEdidPreferredTimingPixelClockKHz()
  w=AnvilEdidPreferredWidth() : h=AnvilEdidPreferredHeight()
  hs=AnvilEdidPreferredHSyncStart() : he=AnvilEdidPreferredHSyncEnd() : ht=AnvilEdidPreferredHTotal()
  vs=AnvilEdidPreferredVSyncStart() : ve=AnvilEdidPreferredVSyncEnd() : vt=AnvilEdidPreferredVTotal()
  If clock<1000 Or w<1 Or w>4096 Or h<1 Or h>2160 Or w>8388608/h Or w*4*h>#PI3_FB_RENDER_BYTES Or hs<=w Or he<=hs Or ht<=he Or vs<=h Or ve<=vs Or vt<=ve
    ProcedureReturn 0
  EndIf
  If AnvilEdidPreferredHSyncPositive()<>0 : flags=flags|1 : EndIf
  If AnvilEdidPreferredVSyncPositive()<>0 : flags=flags|2 : EndIf
  p=((@pi3_fb_message[0]+15)>>4)<<4
  For n=0 To 59 Step 4 : PokeL(p+n,0) : Next
  PokeL(p,60) : PokeL(p+8,$48017) : PokeL(p+12,36) : PokeL(p+16,0)
  PokeA(p+20,2) : PokeW(p+22,0) : PokeL(p+24,clock)
  PokeW(p+28,w) : PokeW(p+30,hs) : PokeW(p+32,he) : PokeW(p+34,ht)
  PokeW(p+36,0) : PokeW(p+38,h) : PokeW(p+40,vs) : PokeW(p+42,ve)
  PokeW(p+44,vt) : PokeW(p+46,0) : PokeW(p+48,(clock*1000)/(ht*vt))
  PokeW(p+50,0) : PokeL(p+52,flags) : PokeL(p+56,0)
  If Pi3MailboxCallTimeout(p,60,#PI3_FB_PROPERTY_BUDGET_US)=0 : ProcedureReturn -1 : EndIf
  If Pi3FbSetTimingReply(p,8)=0 : ProcedureReturn -1 : EndIf
  ; Readback is the proof that output timing, rather than only FB dimensions,
  ; changed. The GET payload has the identical firmware KMS structure.
  For n=0 To 59 Step 4 : PokeL(p+n,0) : Next
  PokeL(p,60) : PokeL(p+8,$40017) : PokeL(p+12,36) : PokeL(p+16,0)
  PokeA(p+20,2) : PokeL(p+56,0)
  If Pi3MailboxCallTimeout(p,60,#PI3_FB_PROPERTY_BUDGET_US)=0 Or Pi3FbReply(p,8,$40017,36)=0
    ProcedureReturn -1
  EndIf
  If (PeekA(p+20)&255)<>2 Or PeekL(p+24)<>clock Or PeekW(p+28)<>w Or PeekW(p+30)<>hs Or PeekW(p+32)<>he Or PeekW(p+34)<>ht Or PeekW(p+38)<>h Or PeekW(p+40)<>vs Or PeekW(p+42)<>ve Or PeekW(p+44)<>vt Or (PeekL(p+52)&7)<>(flags&7)
    ProcedureReturn -1
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3FbDisplayTimingMode(*width,*height)
  Protected p.i,n.i,w.i,h.i
  p=((@pi3_fb_message[0]+15)>>4)<<4
  For n=0 To 59 Step 4 : PokeL(p+n,0) : Next
  PokeL(p,60) : PokeL(p+8,$40017) : PokeL(p+12,36) : PokeL(p+16,0)
  PokeA(p+20,2) : PokeL(p+56,0)
  If Pi3MailboxCallTimeout(p,60,#PI3_FB_PROPERTY_BUDGET_US)=0 Or Pi3FbReply(p,8,$40017,36)=0
    ProcedureReturn 0
  EndIf
  w=PeekW(p+28)&$FFFF : h=PeekW(p+38)&$FFFF
  If PeekL(p+24)=0 Or w<1 Or w>4096 Or h<1 Or h>2160 : ProcedureReturn 0 : EndIf
  PokeI(*width,w) : PokeI(*height,h)
  ProcedureReturn 1
EndProcedure

; Cold boot reserves coherent address ranges only. No framebuffer allocation
; or display initialization occurs here.
Procedure.i Pi3FbDeferredPrepare(dtb.i,dtbEnd.i,ramBase.i,ramEnd.i)
  Protected p.i,n.i,vc.i,bytes.i
  pi3_fb_boot_dtb=dtb : pi3_fb_boot_dtb_end=dtbEnd
  pi3_fb_boot_ram_base=ramBase : pi3_fb_boot_ram_end=ramEnd
  pi3_fb_ddc_clock=Pi3ClockMaxRate(4)
  If pi3_fb_ddc_clock<1000000 : ProcedureReturn 0 : EndIf
  p=((@pi3_fb_message[0]+15)>>4)<<4
  For n=0 To 31 Step 4 : PokeL(p+n,0) : Next
  PokeL(p,32) : PokeL(p+8,$10006) : PokeL(p+12,8) : PokeL(p+16,0) : PokeL(p+28,0)
  If Pi3MailboxCallTimeout(p,32,#PI3_FB_PROPERTY_BUDGET_US)=0 Or Pi3FbReply(p,8,$10006,8)=0
    ProcedureReturn 0
  EndIf
  vc=PeekL(p+20)&$FFFFFFFF : bytes=PeekL(p+24)&$FFFFFFFF
  If bytes=0 Or vc>$40000000-bytes : ProcedureReturn 0 : EndIf
  ; The firmware-owned reservation must be disjoint from the complete ARM
  ; RAM extent that contains the resident monitor, BSS, stacks and payloads.
  If vc<ramEnd And vc+bytes>ramBase : ProcedureReturn 0 : EndIf
  If #PI3_FB_RENDER_BASE<ramBase Or #PI3_FB_RENDER_BASE>$3F000000-#PI3_FB_RENDER_BYTES Or #PI3_FB_RENDER_BASE+#PI3_FB_RENDER_BYTES>ramEnd : ProcedureReturn 0 : EndIf
  If #PI3_FB_RENDER_BASE<dtbEnd And #PI3_FB_RENDER_BASE+#PI3_FB_RENDER_BYTES>dtb : ProcedureReturn 0 : EndIf
  If #PI3_FB_RENDER_BASE<vc+bytes And #PI3_FB_RENDER_BASE+#PI3_FB_RENDER_BYTES>vc : ProcedureReturn 0 : EndIf
  pi3_fb_vc_base=vc : pi3_fb_vc_bytes=bytes : pi3_fb_deferred_ready=1
  ProcedureReturn 1
EndProcedure

; Base EDID is acquired cooperatively: each call performs one controller
; status sample and drains at most sixteen FIFO bytes. Extension blocks are
; reported truncated; only the validated base preferred DTD drives a modeset.
Procedure Pi3FbEdidAbort()
  PokeL(#PI3_FB_DDC_BASE+#PI3_FB_I2C_C,#PI3_FB_I2C_C_I2CEN|#PI3_FB_I2C_C_CLEAR)
  PokeL(#PI3_FB_DDC_BASE+#PI3_FB_I2C_S,#PI3_FB_I2C_S_DONE|#PI3_FB_I2C_S_ERR|#PI3_FB_I2C_S_CLKT)
  pi3_fb_edid_phase=0
EndProcedure

Procedure.i Pi3FbEdidBaseStep(vpuClockHz.i)
  Protected reg.i=#PI3_FB_DDC_BASE,status.i,divider.i,redl.i,n.i,now.i
  If pi3_fb_edid_phase=0
    AnvilEdidReset() : pi3_fb_edid_status=#PI3_FB_EDID_TRANSPORT
    If vpuClockHz<1000000 Or (PeekL(reg+#PI3_FB_I2C_S)&#PI3_FB_I2C_S_TA)<>0 : ProcedureReturn 2 : EndIf
    divider=(vpuClockHz+#PI3_FB_DDC_HZ-1)/#PI3_FB_DDC_HZ : If divider&1 : divider=divider+1 : EndIf
    If divider<2 Or divider>65534 : ProcedureReturn 2 : EndIf
    PokeL(reg+#PI3_FB_I2C_C,#PI3_FB_I2C_C_I2CEN|#PI3_FB_I2C_C_CLEAR)
    PokeL(reg+#PI3_FB_I2C_CLKT,0) : PokeL(reg+#PI3_FB_I2C_DIV,divider)
    redl=divider/4 : If redl<1 : redl=1 : EndIf
    PokeL(reg+#PI3_FB_I2C_DEL,((divider/16)<<16)|redl)
    PokeL(reg+#PI3_FB_I2C_S,#PI3_FB_I2C_S_DONE|#PI3_FB_I2C_S_ERR|#PI3_FB_I2C_S_CLKT)
    PokeL(reg+#PI3_FB_I2C_A,#PI3_FB_DDC_ADDR_EDID) : PokeL(reg+#PI3_FB_I2C_DLEN,1)
    PokeL(reg+#PI3_FB_I2C_C,#PI3_FB_I2C_C_I2CEN|#PI3_FB_I2C_C_ST|#PI3_FB_I2C_C_INTT|#PI3_FB_I2C_C_INTD)
    pi3_fb_edid_start=Pi3Micros() : pi3_fb_edid_phase=1 : ProcedureReturn 0
  EndIf
  now=Pi3Micros()
  If now<pi3_fb_edid_start Or now-pi3_fb_edid_start>=#PI3_FB_EDID_BUDGET_US : Pi3FbEdidAbort() : ProcedureReturn 2 : EndIf
  status=PeekL(reg+#PI3_FB_I2C_S)
  If (status&(#PI3_FB_I2C_S_ERR|#PI3_FB_I2C_S_CLKT))<>0 : Pi3FbEdidAbort() : ProcedureReturn 2 : EndIf
  If pi3_fb_edid_phase=1
    If (status&#PI3_FB_I2C_S_TXD)<>0 : PokeL(reg+#PI3_FB_I2C_FIFO,0) : pi3_fb_edid_phase=2 : EndIf
    ProcedureReturn 0
  EndIf
  If pi3_fb_edid_phase=2
    If (status&#PI3_FB_I2C_S_DONE)=0 : ProcedureReturn 0 : EndIf
    PokeL(reg+#PI3_FB_I2C_S,#PI3_FB_I2C_S_DONE|#PI3_FB_I2C_S_ERR|#PI3_FB_I2C_S_CLKT)
    PokeL(reg+#PI3_FB_I2C_C,#PI3_FB_I2C_C_I2CEN|#PI3_FB_I2C_C_CLEAR)
    PokeL(reg+#PI3_FB_I2C_A,#PI3_FB_DDC_ADDR_EDID) : PokeL(reg+#PI3_FB_I2C_DLEN,128)
    PokeL(reg+#PI3_FB_I2C_C,#PI3_FB_I2C_C_I2CEN|#PI3_FB_I2C_C_ST|#PI3_FB_I2C_C_READ|#PI3_FB_I2C_C_INTR|#PI3_FB_I2C_C_INTD)
    pi3_fb_edid_got=0 : pi3_fb_edid_phase=3 : ProcedureReturn 0
  EndIf
  n=0
  While pi3_fb_edid_got<128 And n<16 And (status&#PI3_FB_I2C_S_RXD)<>0
    PokeA(@pi3_fb_edid_blocks[pi3_fb_edid_got],PeekL(reg+#PI3_FB_I2C_FIFO))
    pi3_fb_edid_got=pi3_fb_edid_got+1 : n=n+1 : status=PeekL(reg+#PI3_FB_I2C_S)
  Wend
  If (status&#PI3_FB_I2C_S_DONE)=0 : ProcedureReturn 0 : EndIf
  pi3_fb_edid_phase=0
  If pi3_fb_edid_got<>128 : ProcedureReturn 2 : EndIf
  If AnvilEdidParse(@pi3_fb_edid_blocks[0],128,1,Bool((PeekA(@pi3_fb_edid_blocks[126])&255)>0))=0
    pi3_fb_edid_status=#PI3_FB_EDID_INVALID : ProcedureReturn 2
  EndIf
  If (PeekA(@pi3_fb_edid_blocks[126])&255)>0 : pi3_fb_edid_status=#PI3_FB_EDID_TRUNCATED : Else : pi3_fb_edid_status=#PI3_FB_EDID_VALID : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3FbTimingPrepare()
  If AnvilEdidPreferredTimingValid()=0 Or AnvilEdidPreferredInterlaced()<>0 Or AnvilEdidPreferredSeparateSync()=0 : ProcedureReturn 0 : EndIf
  pi3_fb_t_clock=AnvilEdidPreferredTimingPixelClockKHz()
  pi3_fb_t_w=AnvilEdidPreferredWidth() : pi3_fb_t_h=AnvilEdidPreferredHeight()
  pi3_fb_t_hs=AnvilEdidPreferredHSyncStart() : pi3_fb_t_he=AnvilEdidPreferredHSyncEnd() : pi3_fb_t_ht=AnvilEdidPreferredHTotal()
  pi3_fb_t_vs=AnvilEdidPreferredVSyncStart() : pi3_fb_t_ve=AnvilEdidPreferredVSyncEnd() : pi3_fb_t_vt=AnvilEdidPreferredVTotal()
  pi3_fb_t_flags=$200
  If AnvilEdidPreferredHSyncPositive()<>0 : pi3_fb_t_flags=pi3_fb_t_flags|1 : EndIf
  If AnvilEdidPreferredVSyncPositive()<>0 : pi3_fb_t_flags=pi3_fb_t_flags|2 : EndIf
  If pi3_fb_t_clock<1000 Or pi3_fb_t_w<1 Or pi3_fb_t_w>4096 Or pi3_fb_t_h<1 Or pi3_fb_t_h>2160 Or pi3_fb_t_w>8388608/pi3_fb_t_h Or pi3_fb_t_w*4*pi3_fb_t_h>#PI3_FB_RENDER_BYTES : ProcedureReturn 0 : EndIf
  If pi3_fb_t_hs<=pi3_fb_t_w Or pi3_fb_t_he<=pi3_fb_t_hs Or pi3_fb_t_ht<=pi3_fb_t_he Or pi3_fb_t_vs<=pi3_fb_t_h Or pi3_fb_t_ve<=pi3_fb_t_vs Or pi3_fb_t_vt<=pi3_fb_t_ve : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3FbTimingBegin(tag.i)
  Protected p.i=((@pi3_fb_message[0]+15)>>4)<<4, n.i
  If pi3_mailbox_begin_waiting<>0 : ProcedureReturn Pi3MailboxBegin(p,PeekL(p),#PI3_FB_PROPERTY_BUDGET_US) : EndIf
  If pi3_mailbox_outstanding<>0 : ProcedureReturn -1 : EndIf
  For n=0 To 59 Step 4 : PokeL(p+n,0) : Next
  PokeL(p,60) : PokeL(p+8,tag) : PokeL(p+12,36) : PokeL(p+16,0) : PokeA(p+20,2)
  If tag=$48017
    PokeL(p+24,pi3_fb_t_clock)
    PokeW(p+28,pi3_fb_t_w) : PokeW(p+30,pi3_fb_t_hs) : PokeW(p+32,pi3_fb_t_he) : PokeW(p+34,pi3_fb_t_ht)
    PokeW(p+36,0) : PokeW(p+38,pi3_fb_t_h) : PokeW(p+40,pi3_fb_t_vs) : PokeW(p+42,pi3_fb_t_ve)
    PokeW(p+44,pi3_fb_t_vt) : PokeW(p+46,0) : PokeW(p+48,(pi3_fb_t_clock*1000)/(pi3_fb_t_ht*pi3_fb_t_vt))
    PokeW(p+50,0) : PokeL(p+52,pi3_fb_t_flags)
  EndIf
  PokeL(p+56,0)
  ProcedureReturn Pi3MailboxBegin(p,60,#PI3_FB_PROPERTY_BUDGET_US)
EndProcedure

Procedure.i Pi3FbTimingPoll(tag.i)
  Protected p.i=((@pi3_fb_message[0]+15)>>4)<<4,rc.i=Pi3MailboxPoll()
  If rc<=0 : ProcedureReturn rc : EndIf
  If tag=$48017
    ; Pi 3 firmware accepts SET_TIMING with a successful overall property
    ; response while leaving this set tag's response-length word at zero.
    ; Accept only that no-payload form or the ordinary flagged 36-byte form.
    ; The following GET_TIMING phase remains mandatory and validates every
    ; timing field before framebuffer allocation or visible publication.
    If Pi3FbSetTimingReply(p,8)=0 : ProcedureReturn -1 : EndIf
  Else
    If Pi3FbReply(p,8,tag,36)=0 : ProcedureReturn -1 : EndIf
    If (PeekA(p+20)&255)<>2 Or PeekL(p+24)<>pi3_fb_t_clock Or PeekW(p+28)<>pi3_fb_t_w Or PeekW(p+30)<>pi3_fb_t_hs Or PeekW(p+32)<>pi3_fb_t_he Or PeekW(p+34)<>pi3_fb_t_ht Or PeekW(p+38)<>pi3_fb_t_h Or PeekW(p+40)<>pi3_fb_t_vs Or PeekW(p+42)<>pi3_fb_t_ve Or PeekW(p+44)<>pi3_fb_t_vt Or (PeekL(p+52)&$207)<>(pi3_fb_t_flags&$207)
      ProcedureReturn -1
    EndIf
  EndIf
  ProcedureReturn 1
EndProcedure

; Record only the first definitive HPD observation after cold preparation.
; A later replug cannot claim the firmware's boot-established display state.
Procedure Pi3FbInitialPresence(present.i)
  If pi3_fb_initial_probe<>0
    pi3_fb_initial_probe=0
    pi3_fb_initial_connected=Bool(present<>0)
  EndIf
EndProcedure

Procedure.i Pi3FbPhysicalBegin()
  Protected p.i=((@pi3_fb_message[0]+15)>>4)<<4,n.i
  If pi3_mailbox_begin_waiting<>0 : ProcedureReturn Pi3MailboxBegin(p,PeekL(p),#PI3_FB_PROPERTY_BUDGET_US) : EndIf
  If pi3_mailbox_outstanding<>0 : ProcedureReturn -1 : EndIf
  For n=0 To 31 Step 4 : PokeL(p+n,0) : Next
  PokeL(p,32) : PokeL(p+8,$40003) : PokeL(p+12,8) : PokeL(p+16,0)
  ProcedureReturn Pi3MailboxBegin(p,32,#PI3_FB_PROPERTY_BUDGET_US)
EndProcedure

Procedure.i Pi3FbPhysicalPoll()
  Protected p.i=((@pi3_fb_message[0]+15)>>4)<<4,rc.i=Pi3MailboxPoll()
  If rc<=0 : ProcedureReturn rc : EndIf
  If Pi3FbReply(p,8,$40003,8)=0 : ProcedureReturn -1 : EndIf
  If PeekL(p+20)<>pi3_fb_t_w Or PeekL(p+24)<>pi3_fb_t_h : ProcedureReturn -1 : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3FbBlankBegin(state.i)
  Protected p.i=((@pi3_fb_message[0]+15)>>4)<<4,n.i
  If pi3_mailbox_begin_waiting<>0 : ProcedureReturn Pi3MailboxBegin(p,PeekL(p),#PI3_FB_PROPERTY_BUDGET_US) : EndIf
  If pi3_mailbox_outstanding<>0 : ProcedureReturn -1 : EndIf
  pi3_fb_blank_expected=state&1
  For n=0 To 27 Step 4 : PokeL(p+n,0) : Next
  PokeL(p,28) : PokeL(p+8,$40002) : PokeL(p+12,4) : PokeL(p+16,4)
  PokeL(p+20,state) : PokeL(p+24,0)
  ProcedureReturn Pi3MailboxBegin(p,28,#PI3_FB_PROPERTY_BUDGET_US)
EndProcedure

Procedure.i Pi3FbBlankPoll()
  Protected p.i=((@pi3_fb_message[0]+15)>>4)<<4,rc.i=Pi3MailboxPoll()
  If rc<=0 : ProcedureReturn rc : EndIf
  If Pi3FbReply(p,8,$40002,4)=0 : ProcedureReturn -1 : EndIf
  If (PeekL(p+20)&1)<>pi3_fb_blank_expected : ProcedureReturn -1 : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3FbPowerBegin(state.i)
  Protected p.i=((@pi3_fb_message[0]+15)>>4)<<4,n.i
  If pi3_mailbox_begin_waiting<>0 : ProcedureReturn Pi3MailboxBegin(p,PeekL(p),#PI3_FB_PROPERTY_BUDGET_US) : EndIf
  If pi3_mailbox_outstanding<>0 : ProcedureReturn -1 : EndIf
  For n=0 To 31 Step 4 : PokeL(p+n,0) : Next
  PokeL(p,32) : PokeL(p+8,$48019) : PokeL(p+12,8) : PokeL(p+16,0)
  PokeL(p+20,2) : PokeL(p+24,Bool(state<>0))
  ProcedureReturn Pi3MailboxBegin(p,32,#PI3_FB_PROPERTY_BUDGET_US)
EndProcedure

Procedure.i Pi3FbPowerPoll()
  Protected p.i=((@pi3_fb_message[0]+15)>>4)<<4,rc.i=Pi3MailboxPoll(),reply.i
  If rc<=0 : ProcedureReturn rc : EndIf
  ; Deployed Pi 3 firmware returns four bytes for this eight-byte set request
  ; and rewrites the first payload word. Linux does not interpret the setter
  ; payload on return, so accept only the transport/tag/length contract.
  reply=PeekL(p+16)&$FFFFFFFF
  If PeekL(p+8)<>$48019 Or PeekL(p+12)<>8 Or (reply&$80000000)=0 Or (reply&$7FFFFFFF)<4 : ProcedureReturn -1 : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3FbAllocationBegin()
  Protected p.i=((@pi3_fb_message[0]+15)>>4)<<4,n.i
  If pi3_mailbox_begin_waiting<>0 : ProcedureReturn Pi3MailboxBegin(p,PeekL(p),#PI3_FB_PROPERTY_BUDGET_US) : EndIf
  If pi3_mailbox_outstanding<>0 : ProcedureReturn -1 : EndIf
  For n=0 To 175 Step 4 : PokeL(p+n,0) : Next
  PokeL(p,176)
  Pi3FbTag(p,8,$48003,8,pi3_fb_t_w,pi3_fb_t_h)
  Pi3FbTag(p,28,$48004,8,pi3_fb_t_w,pi3_fb_t_h)
  Pi3FbTag(p,48,$48005,4,32,0) : Pi3FbTag(p,64,$48009,8,0,0)
  Pi3FbTag(p,84,$40001,8,4096,0) : Pi3FbTag(p,104,$40008,4,0,0)
  Pi3FbTag(p,120,$40006,4,0,0) : Pi3FbTag(p,136,$40007,4,0,0)
  Pi3FbTag(p,152,$10006,8,0,0)
  ProcedureReturn Pi3MailboxBegin(p,176,#PI3_FB_PROPERTY_BUDGET_US)
EndProcedure

Procedure.i Pi3FbAllocationPollCommit()
  Protected p.i=((@pi3_fb_message[0]+15)>>4)<<4,rc.i,base.i,size.i,pitch.i,vc.i,vcSize.i,renderBase.i
  rc=Pi3MailboxPoll() : If rc<=0 : ProcedureReturn rc : EndIf
  If Pi3FbReply(p,8,$48003,8)=0 Or Pi3FbReply(p,28,$48004,8)=0 Or Pi3FbReply(p,48,$48005,4)=0 Or Pi3FbReply(p,64,$48009,8)=0 Or Pi3FbReply(p,84,$40001,8)=0 Or Pi3FbReply(p,104,$40008,4)=0 Or Pi3FbReply(p,120,$40006,4)=0 Or Pi3FbReply(p,136,$40007,4)=0 Or Pi3FbReply(p,152,$10006,8)=0
    ProcedureReturn -1
  EndIf
  If PeekL(p+20)<>pi3_fb_t_w Or PeekL(p+24)<>pi3_fb_t_h Or PeekL(p+40)<>pi3_fb_t_w Or PeekL(p+44)<>pi3_fb_t_h Or PeekL(p+60)<>32 Or PeekL(p+76)<>0 Or PeekL(p+80)<>0 : ProcedureReturn -1 : EndIf
  pi3_fb_pixel_order=PeekL(p+132)&$FFFFFFFF : pi3_fb_alpha_mode=PeekL(p+148)&$FFFFFFFF
  If (pi3_fb_pixel_order<>0 And pi3_fb_pixel_order<>1) Or pi3_fb_alpha_mode<0 Or pi3_fb_alpha_mode>2 : ProcedureReturn -1 : EndIf
  base=(PeekL(p+96)&$FFFFFFFF)&$3FFFFFFF : size=PeekL(p+100)&$FFFFFFFF : pitch=PeekL(p+116)&$FFFFFFFF
  vc=PeekL(p+164)&$FFFFFFFF : vcSize=PeekL(p+168)&$FFFFFFFF
  If pitch<pi3_fb_t_w*4 Or pitch>16384 Or (pitch&3)<>0 Or size<pitch*pi3_fb_t_h Or size>33554432 Or base>$3F000000-size : ProcedureReturn -1 : EndIf
  If vc<>pi3_fb_vc_base Or vcSize<>pi3_fb_vc_bytes Or base<vc Or base+size>vc+vcSize Or (base&4095)<>0 : ProcedureReturn -1 : EndIf
  If base<pi3_fb_boot_dtb_end And base+size>pi3_fb_boot_dtb : ProcedureReturn -1 : EndIf
  renderBase=#PI3_FB_RENDER_BASE
  If pitch*pi3_fb_t_h>#PI3_FB_RENDER_BYTES Or renderBase<pi3_fb_boot_ram_base Or renderBase+pitch*pi3_fb_t_h>pi3_fb_boot_ram_end : ProcedureReturn -1 : EndIf
  If renderBase<pi3_fb_boot_dtb_end And renderBase+#PI3_FB_RENDER_BYTES>pi3_fb_boot_dtb : ProcedureReturn -1 : EndIf
  If renderBase<base+size And renderBase+#PI3_FB_RENDER_BYTES>base : ProcedureReturn -1 : EndIf
  If MmuIsNcRange(renderBase,renderBase+#PI3_FB_RENDER_BYTES-1)=0 Or MmuIsNcRange(base,base+size-1)=0 : ProcedureReturn -1 : EndIf
  pi3_fb_pitch=pitch : pi3_fb_size=size : pi3_fb_width=pi3_fb_t_w : pi3_fb_height=pi3_fb_t_h
  pi3_fb_scanout=base : pi3_fb=renderBase : pi3_fb_render_bytes=pitch*pi3_fb_t_h
  pi3_fb_requested_width=pi3_fb_t_w : pi3_fb_requested_height=pi3_fb_t_h
  If pi3_fb_mode_source<>#PI3_FB_MODE_FIRMWARE_INHERITED
    pi3_fb_mode_source=#PI3_FB_MODE_EDID_PREFERRED
  EndIf
  pi3_fb_dirty=1 : pi3_fb_dirty_left=0 : pi3_fb_dirty_top=0 : pi3_fb_dirty_right=pi3_fb_t_w : pi3_fb_dirty_bottom=pi3_fb_t_h
  pi3_fb_present_pending=0 : pi3_fb_dma_state=0 : pi3_fb_dma_error=0
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3FbReleaseBegin()
  Protected p.i=((@pi3_fb_message[0]+15)>>4)<<4,n.i
  If pi3_mailbox_begin_waiting<>0 : ProcedureReturn Pi3MailboxBegin(p,PeekL(p),#PI3_FB_PROPERTY_BUDGET_US) : EndIf
  If pi3_mailbox_outstanding<>0 : ProcedureReturn -1 : EndIf
  For n=0 To 23 Step 4 : PokeL(p+n,0) : Next
  PokeL(p,24) : PokeL(p+8,$48001) : PokeL(p+12,0) : PokeL(p+16,0) : PokeL(p+20,0)
  ProcedureReturn Pi3MailboxBegin(p,24,#PI3_FB_PROPERTY_BUDGET_US)
EndProcedure

Procedure.i Pi3FbReleasePoll()
  Protected p.i=((@pi3_fb_message[0]+15)>>4)<<4,rc.i=Pi3MailboxPoll()
  If rc<=0 : ProcedureReturn rc : EndIf
  If Pi3FbReply(p,8,$48001,0)=0 : ProcedureReturn -1 : EndIf
  pi3_fb=0 : pi3_fb_scanout=0 : pi3_fb_size=0 : pi3_fb_width=0 : pi3_fb_height=0 : pi3_fb_attached=0
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3FbAttachFail(phase.i,rc.i)
  Protected p.i=((@pi3_fb_message[0]+15)>>4)<<4
  pi3_fb_attach_error_phase=phase : pi3_fb_attach_error_rc=rc
  pi3_fb_attach_error_size=PeekL(p)&$FFFFFFFF
  pi3_fb_attach_error_code=PeekL(p+4)&$FFFFFFFF
  pi3_fb_attach_error_tag=PeekL(p+8)&$FFFFFFFF
  pi3_fb_attach_error_value_bytes=PeekL(p+12)&$FFFFFFFF
  pi3_fb_attach_error_reply=PeekL(p+16)&$FFFFFFFF
  pi3_fb_attach_error_value0=PeekL(p+20)&$FFFFFFFF
  pi3_fb_attach_error_value1=PeekL(p+24)&$FFFFFFFF
  pi3_fb_attach_phase=0
  ProcedureReturn -1
EndProcedure

; One bounded hardware action per lifecycle tick. No callback waits for DDC
; or mailbox completion; submitted property requests are polled on later
; calls. Only the first definitive connected HPD sample may adopt firmware boot
; geometry. An absent-first boot or later reconnect retries without allocation.
Procedure.i Pi3FbAttachStep()
  Protected rc.i
  Select pi3_fb_attach_phase
    Case 0
      rc=Pi3FbEdidBaseStep(pi3_fb_ddc_clock)
      If rc=0 : ProcedureReturn 0 : EndIf
      If rc<>1 Or Pi3FbTimingPrepare()=0 : pi3_fb_attach_phase=0 : ProcedureReturn 2 : EndIf
      If pi3_fb_initial_connected=0
        ; This firmware did not apply a late SET_TIMING even after the exact
        ; FKMS selector, plane and power sequence. Keep late attach retryable
        ; without allocating or pretending an inherited mode is current.
        pi3_fb_attach_phase=0 : ProcedureReturn 2
      EndIf
      pi3_fb_initial_connected=0
      pi3_fb_mode_source=#PI3_FB_MODE_FIRMWARE_INHERITED
      pi3_fb_attach_phase=12
    Case 12
      rc=Pi3FbPhysicalBegin()
      If rc=0 : ProcedureReturn 0 : EndIf
      If rc<0 : ProcedureReturn Pi3FbAttachFail(12,rc) : EndIf
      pi3_fb_attach_phase=13 : ProcedureReturn 0
    Case 13
      rc=Pi3FbPhysicalPoll()
      If rc=0 : ProcedureReturn 0 : EndIf
      If rc<0 : ProcedureReturn Pi3FbAttachFail(13,rc) : EndIf
      pi3_fb_attach_phase=6
    Case 10
      rc=Pi3FbBlankBegin(1)
      If rc=0 : ProcedureReturn 0 : EndIf
      If rc<0 : ProcedureReturn Pi3FbAttachFail(10,rc) : EndIf
      pi3_fb_attach_phase=11 : ProcedureReturn 0
    Case 11
      rc=Pi3FbBlankPoll()
      If rc=0 : ProcedureReturn 0 : EndIf
      If rc<0 : ProcedureReturn Pi3FbAttachFail(11,rc) : EndIf
      pi3_fb_attach_phase=1
    Case 1
      rc=Pi3FbTimingBegin($48017)
      If rc=0 : ProcedureReturn 0 : EndIf
      If rc<0 : ProcedureReturn Pi3FbAttachFail(1,rc) : EndIf
      pi3_fb_attach_phase=2 : ProcedureReturn 0
    Case 2
      rc=Pi3FbTimingPoll($48017)
      If rc=0 : ProcedureReturn 0 : EndIf
      If rc<0 : ProcedureReturn Pi3FbAttachFail(2,rc) : EndIf
      pi3_fb_attach_phase=3
    Case 3
      rc=Pi3FbTimingBegin($40017)
      If rc=0 : ProcedureReturn 0 : EndIf
      If rc<0 : ProcedureReturn Pi3FbAttachFail(3,rc) : EndIf
      pi3_fb_attach_phase=4 : ProcedureReturn 0
    Case 4
      rc=Pi3FbTimingPoll($40017)
      If rc=0 : ProcedureReturn 0 : EndIf
      If rc<0 : ProcedureReturn Pi3FbAttachFail(4,rc) : EndIf
      If pi3_fb<>0 And pi3_fb_scanout<>0
        If pi3_fb_width=pi3_fb_t_w And pi3_fb_height=pi3_fb_t_h
          pi3_fb_attach_phase=8
        Else
          pi3_fb_attach_phase=5
        EndIf
      Else
        pi3_fb_attach_phase=6
      EndIf
    Case 5
      rc=Pi3FbReleaseBegin()
      If rc=0 : ProcedureReturn 0 : EndIf
      If rc<0 : ProcedureReturn Pi3FbAttachFail(5,rc) : EndIf
      pi3_fb_attach_phase=7 : ProcedureReturn 0
    Case 7
      rc=Pi3FbReleasePoll()
      If rc=0 : ProcedureReturn 0 : EndIf
      If rc<0 : ProcedureReturn Pi3FbAttachFail(7,rc) : EndIf
      pi3_fb_attach_phase=6
    Case 6
      rc=Pi3FbAllocationBegin()
      If rc=0 : ProcedureReturn 0 : EndIf
      If rc<0 : ProcedureReturn Pi3FbAttachFail(6,rc) : EndIf
      pi3_fb_attach_phase=9 : ProcedureReturn 0
    Case 9
      rc=Pi3FbAllocationPollCommit()
      If rc=0 : ProcedureReturn 0 : EndIf
      If rc<0 : ProcedureReturn Pi3FbAttachFail(9,rc) : EndIf
      pi3_fb_attach_phase=8
    Case 8
      pi3_fb_attached=1
      pi3_fb_dirty=1 : pi3_fb_dirty_left=0 : pi3_fb_dirty_top=0
      pi3_fb_dirty_right=pi3_fb_width : pi3_fb_dirty_bottom=pi3_fb_height
      pi3_fb_attach_phase=0 : ProcedureReturn 1
  EndSelect
  ProcedureReturn 0
EndProcedure

Procedure.i Pi3FbInit(dtb.i,dtbEnd.i,ramBase.i,ramEnd.i)
  Protected p.i
  Protected base.i
  Protected size.i
  Protected pitch.i
  Protected vc.i
  Protected vcSize.i
  Protected n.i
  Protected requestWidth.i
  Protected requestHeight.i
  Protected currentWidth.i
  Protected currentHeight.i
  Protected ddcClockCeilingHz.i
  Protected actualWidth.i
  Protected actualHeight.i
  Protected renderBase.i
  ; A connected sink owns one allocation attempt. Cold boot only reserved
  ; NC spans and captured these bounds; ABSENT never reaches this routine.
  pi3_fb_error=#PI3_FB_ERR_NONE
  If pi3_fb_attempted<>0 Or pi3_mailbox_outstanding<>0
    pi3_fb_error=#PI3_FB_ERR_OWNERSHIP
    ProcedureReturn 0
  EndIf
  pi3_fb_attempted=1
  pi3_fb=0
  pi3_fb_width=0 : pi3_fb_height=0
  pi3_fb_mode_source=#PI3_FB_MODE_FIRMWARE_CURRENT
  pi3_fb_requested_width=0 : pi3_fb_requested_height=0
  pi3_fb_edid_status=#PI3_FB_EDID_NONE
  requestWidth=0 : requestHeight=0
  currentWidth=0 : currentHeight=0
  ; BSC2 is clocked from the VPU clock. Linux's BCM2835 clock provider uses
  ; the firmware maximum CORE rate as its VPU parent rate when it has the
  ; firmware interface, so use the same conservative ceiling for CDIV. This
  ; one bounded clock query only configures native DDC timing; the EDID bytes
  ; themselves are read from BSC2 at 0x3F805000, never from firmware.
  ddcClockCeilingHz=Pi3ClockMaxRate(4)
  Pi3FbReadEdid(ddcClockCeilingHz)
  If AnvilEdidValid()<>0
    n=Pi3FbSetPreferredTiming()
    If n<0
      pi3_fb_error=#PI3_FB_ERR_MAILBOX : ProcedureReturn 0
    ElseIf n>0
      pi3_fb_mode_source=#PI3_FB_MODE_EDID_PREFERRED
    EndIf
  EndIf
  ; Invalid/unreadable EDID is still a connected sink. In that case retain
  ; and verify the firmware's live timing rather than inventing absence or a
  ; blind 640x480 fallback.
  If Pi3FbDisplayTimingMode(@currentWidth,@currentHeight)<>0
    requestWidth=currentWidth : requestHeight=currentHeight
  ElseIf pi3_mailbox_outstanding<>0
    ; Do not reuse the NC property buffer while firmware may still own it.
    pi3_fb_error=#PI3_FB_ERR_MAILBOX
    ProcedureReturn 0
  Else
    pi3_fb_error=#PI3_FB_ERR_GEOMETRY : ProcedureReturn 0
  EndIf
  pi3_fb_requested_width=requestWidth : pi3_fb_requested_height=requestHeight
  p=((@pi3_fb_message[0]+15)>>4)<<4
  For n=0 To 175 Step 4 : PokeL(p+n,0) : Next
  PokeL(p,176)
  ; This is the same old-scheme framebuffer transaction used by the pinned
  ; Raspberry Pi Linux bcm2708_fb driver: set geometry/depth/offset, allocate,
  ; then query pitch. Pixel order, alpha mode and VC memory are GETs so the
  ; firmware—not a caller preference—defines how returned pixels are packed.
  Pi3FbTag(p,8,$48003,8,requestWidth,requestHeight)
  Pi3FbTag(p,28,$48004,8,requestWidth,requestHeight)
  Pi3FbTag(p,48,$48005,4,32,0)
  Pi3FbTag(p,64,$48009,8,0,0)
  Pi3FbTag(p,84,$40001,8,4096,0)
  Pi3FbTag(p,104,$40008,4,0,0)
  Pi3FbTag(p,120,$40006,4,0,0)
  Pi3FbTag(p,136,$40007,4,0,0)
  Pi3FbTag(p,152,$10006,8,0,0)
  If Pi3MailboxCallTimeout(p,176,#PI3_FB_PROPERTY_BUDGET_US)=0
    pi3_fb_error=#PI3_FB_ERR_MAILBOX
    ProcedureReturn 0
  EndIf
  If Pi3FbReply(p,8,$48003,8)=0 Or Pi3FbReply(p,28,$48004,8)=0 Or Pi3FbReply(p,48,$48005,4)=0 Or Pi3FbReply(p,64,$48009,8)=0
    pi3_fb_error=#PI3_FB_ERR_TAG_REPLY
    ProcedureReturn 0
  EndIf
  If Pi3FbReply(p,84,$40001,8)=0 Or Pi3FbReply(p,104,$40008,4)=0 Or Pi3FbReply(p,120,$40006,4)=0 Or Pi3FbReply(p,136,$40007,4)=0 Or Pi3FbReply(p,152,$10006,8)=0
    pi3_fb_error=#PI3_FB_ERR_TAG_REPLY
    ProcedureReturn 0
  EndIf
  actualWidth=PeekL(p+20)&$FFFFFFFF : actualHeight=PeekL(p+24)&$FFFFFFFF
  If actualWidth<1 Or actualWidth>4096 Or actualHeight<1 Or actualHeight>2160 Or actualWidth>8388608/actualHeight Or PeekL(p+40)<>actualWidth Or PeekL(p+44)<>actualHeight Or PeekL(p+60)<>32 Or PeekL(p+76)<>0 Or PeekL(p+80)<>0
    pi3_fb_error=#PI3_FB_ERR_GEOMETRY
    ProcedureReturn 0
  EndIf
  If actualWidth<>requestWidth Or actualHeight<>requestHeight
    pi3_fb_mode_source=#PI3_FB_MODE_FIRMWARE_ADJUSTED
  EndIf
  ; The property interface may report either supported byte order. Query it
  ; instead of trying to force RGB: current Pi firmware may retain BGR.
  pi3_fb_pixel_order=PeekL(p+132)&$FFFFFFFF
  If pi3_fb_pixel_order<>0 And pi3_fb_pixel_order<>1
    pi3_fb_error=#PI3_FB_ERR_PIXEL_ORDER
    ProcedureReturn 0
  EndIf
  pi3_fb_alpha_mode=PeekL(p+148)&$FFFFFFFF
  If pi3_fb_alpha_mode<0 Or pi3_fb_alpha_mode>2
    pi3_fb_error=#PI3_FB_ERR_ALPHA_MODE
    ProcedureReturn 0
  EndIf
  base=PeekL(p+96)&$FFFFFFFF : size=PeekL(p+100)&$FFFFFFFF
  pitch=PeekL(p+116)&$FFFFFFFF
  vc=PeekL(p+164)&$FFFFFFFF : vcSize=PeekL(p+168)&$FFFFFFFF
  ; Linux's bcm2708_fb driver accepts the firmware's returned bus alias and
  ; clears the top two alias bits before mapping it for the ARM. Requiring the
  ; $C alias rejected otherwise valid firmware allocations on real Pi 3s.
  base=base & $3FFFFFFF
  If pitch<actualWidth*4 Or pitch>16384 Or (pitch & 3)<>0 Or size<pitch*actualHeight Or size>33554432 Or base>$3F000000-size
    pi3_fb_error=#PI3_FB_ERR_ALLOCATION
    ProcedureReturn 0
  EndIf
  ; VC RAM may legally end at the 1 GiB boundary. The BCM2837 peripheral
  ; window begins at $3F000000, so the FRAMEBUFFER itself must end below it,
  ; but rejecting the whole enclosing VC reservation for extending to
  ; $40000000 refused ordinary 1 GiB Pi 3 firmware layouts.
  If vcSize=0 Or vc>$40000000-vcSize Or base<vc Or (pi3_fb_deferred_ready<>0 And (vc<>pi3_fb_vc_base Or vcSize<>pi3_fb_vc_bytes))
    pi3_fb_error=#PI3_FB_ERR_VC_RANGE
    ProcedureReturn 0
  EndIf
  If base+size>vc+vcSize Or (base & 4095)<>0
    pi3_fb_error=#PI3_FB_ERR_VC_RANGE
    ProcedureReturn 0
  EndIf
  If base<$200000 And base+size>$80000
    pi3_fb_error=#PI3_FB_ERR_OVERLAP
    ProcedureReturn 0
  EndIf
  If base<dtbEnd And base+size>dtb
    pi3_fb_error=#PI3_FB_ERR_OVERLAP
    ProcedureReturn 0
  EndIf
  renderBase=#PI3_FB_RENDER_BASE
  If pitch*actualHeight>#PI3_FB_RENDER_BYTES Or renderBase<ramBase Or renderBase>$3F000000-#PI3_FB_RENDER_BYTES Or renderBase+pitch*actualHeight>ramEnd
    pi3_fb_error=#PI3_FB_ERR_ALLOCATION
    ProcedureReturn 0
  EndIf
  If renderBase<dtbEnd And renderBase+#PI3_FB_RENDER_BYTES>dtb
    pi3_fb_error=#PI3_FB_ERR_OVERLAP
    ProcedureReturn 0
  EndIf
  If renderBase<base+size And renderBase+#PI3_FB_RENDER_BYTES>base
    pi3_fb_error=#PI3_FB_ERR_OVERLAP
    ProcedureReturn 0
  EndIf
  pi3_fb_pitch=pitch : pi3_fb_size=size : pi3_fb_width=actualWidth : pi3_fb_height=actualHeight
  pi3_fb_scanout=base : pi3_fb=renderBase : pi3_fb_render_bytes=pitch*actualHeight
  If Pi3MailboxContextState()=2 And (MmuIsNcRange(pi3_fb,pi3_fb+#PI3_FB_RENDER_BYTES-1)=0 Or MmuIsNcRange(pi3_fb_scanout,pi3_fb_scanout+pi3_fb_size-1)=0)
    pi3_fb=0 : pi3_fb_scanout=0 : pi3_fb_error=#PI3_FB_ERR_VC_RANGE : ProcedureReturn 0
  EndIf
  pi3_fb_attached=1
  pi3_fb_dirty=0 : pi3_fb_present_pending=0
  pi3_fb_dma_state=0 : pi3_fb_dma_error=0
  ; The first present copies the initialized render surface in full.
  pi3_fb_dirty=1 : pi3_fb_dirty_left=0 : pi3_fb_dirty_top=0
  pi3_fb_dirty_right=actualWidth : pi3_fb_dirty_bottom=actualHeight
  ; The caller adds this validated extent to the NC map and enables the MMU
  ; before touching pixel memory. That keeps pre-translation work to bounded
  ; firmware transactions and makes all later framebuffer stores Normal-NC.
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3FbError()
  ProcedureReturn pi3_fb_error
EndProcedure

; Public screen-owner seam. The returned framebuffer address is the ARM
; physical/identity address accepted by the MMU builder; color words must
; be packed with Pi3FbPack so the firmware-selected byte order is respected.
Procedure.i Pi3FbReady()
  ProcedureReturn Bool(pi3_fb_attached<>0 And pi3_fb<>0 And pi3_fb_scanout<>0 And pi3_fb_dma_state<>2 And pi3_fb_dma_state<>3)
EndProcedure
Procedure.i Pi3FbBase()
  ProcedureReturn pi3_fb
EndProcedure
Procedure.i Pi3FbScanoutBase()
  ProcedureReturn pi3_fb_scanout
EndProcedure
Procedure.i Pi3FbRenderSize()
  ProcedureReturn pi3_fb_render_bytes
EndProcedure
Procedure.i Pi3FbPitch()
  ProcedureReturn pi3_fb_pitch
EndProcedure
Procedure.i Pi3FbSize()
  ProcedureReturn pi3_fb_size
EndProcedure
Procedure.i Pi3FbWidth()
  ProcedureReturn pi3_fb_width
EndProcedure
Procedure.i Pi3FbHeight()
  ProcedureReturn pi3_fb_height
EndProcedure
Procedure.i Pi3FbEdidStatus()
  ProcedureReturn pi3_fb_edid_status
EndProcedure
Procedure.i Pi3FbModeSource()
  ProcedureReturn pi3_fb_mode_source
EndProcedure
Procedure.i Pi3FbRequestedWidth()
  ProcedureReturn pi3_fb_requested_width
EndProcedure
Procedure.i Pi3FbRequestedHeight()
  ProcedureReturn pi3_fb_requested_height
EndProcedure

; Disconnect stops presentation before removing the surface from board-visible
; readiness. Firmware storage is retained, so the same timing can reconnect
; without leaking repeated VC allocations.
Procedure.i Pi3FbDetachStep()
  Protected rc.i
  ; Hide the surface immediately. Existing DMA may still be polled below,
  ; but no new renderer or presenter can enter while blank is in flight.
  pi3_fb_attached=0
  If pi3_fb_present_pending<>0
    rc=Pi3FbPresentPoll()
    If rc=0 : ProcedureReturn 0 : EndIf
    If rc<0 : ProcedureReturn -1 : EndIf
  EndIf
  If pi3_fb_dma_active<>0
    rc=Pi3FbDmaPoll()
    If rc=0 : ProcedureReturn 0 : EndIf
    If rc<0 : ProcedureReturn -1 : EndIf
  EndIf
  If pi3_fb_scroll_phase<>0
    rc=Pi3FbScrollPoll()
    If rc=0 : ProcedureReturn 0 : EndIf
    If rc<0 : ProcedureReturn -1 : EndIf
  EndIf
  ; All bus ownership is now quiescent. Do not carry completion markers for
  ; the old geometry into a reconnect.
  pi3_fb_clear_pending=0 : pi3_fb_scroll_phase=0
  If pi3_fb_detach_phase=0
    rc=Pi3FbBlankBegin(1)
    If rc=0 : ProcedureReturn 0 : EndIf
    If rc<0 : ProcedureReturn -1 : EndIf
    pi3_fb_detach_phase=1 : ProcedureReturn 0
  EndIf
  rc=Pi3FbBlankPoll()
  If rc=0 : ProcedureReturn 0 : EndIf
  pi3_fb_detach_phase=0
  If rc<0 : ProcedureReturn -1 : EndIf
  pi3_fb_attached=0
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3FbClear(colour.i)
  If pi3_fb=0 Or pi3_fb_dma_state>=2 Or pi3_fb_present_pending<>0 : ProcedureReturn 0 : EndIf
  ProcedureReturn Pi3FbFillRect(0,0,pi3_fb_width,pi3_fb_height,colour)
EndProcedure

; Initialize the render store through DMA so boot never performs millions of
; uncached CPU stores before the UART prompt. Poll from the screen service.
Procedure.i Pi3FbClearStart(colour.i)
  Protected rowBytes.i
  Protected gap.i
  Protected lenWord.i
  Protected stride.i
  Protected rc.i
  Protected tileOffset.i
  If Pi3FbPropertyBusy()<>0 Or pi3_fb=0 Or pi3_fb_dma_state>=2 Or pi3_fb_clear_pending<>0 Or pi3_fb_present_pending<>0 Or pi3_fb_dma_active<>0
    ProcedureReturn 0
  EndIf
  If Pi3FbDmaInit()=0 : ProcedureReturn 0 : EndIf
  rowBytes=pi3_fb_width*4 : gap=pi3_fb_pitch-rowBytes
  If rowBytes<4 Or rowBytes>$FFFF Or pi3_fb_height>$3FFF Or gap<0 Or gap>32767
    pi3_fb_dma_error=#PI3_FB_DMA_E_BUSY : ProcedureReturn 0
  EndIf
  ; Channel-5 wide bursts can fetch three 128-bit beats from a fixed source.
  ; Seed the full 48-byte read footprint so the burst cannot sample adjacent
  ; mailbox-property words from this shared scratch allocation.
  For tileOffset=0 To #PI3_FB_DMA_FILL_TILE_BYTES-4 Step 4
    PokeL(pi3_fb_dma_cb+32+tileOffset,colour&$FFFFFFFF)
  Next
  ; BCM2708's 2D DMA YLENGTH field stores row-count minus one.
  lenWord=((pi3_fb_height-1)<<16)|(rowBytes&$FFFF)
  stride=(gap&$FFFF)<<16
  rc=Pi3FbDmaBegin(pi3_fb_dma_cb+32,pi3_fb,lenWord,stride,#PI3_FB_DMA_TI_DEST_INC)
  If rc<>1 : ProcedureReturn 0 : EndIf
  pi3_fb_clear_pending=1
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3FbClearPoll()
  Protected rc.i
  If pi3_fb_clear_pending=0 : ProcedureReturn 1 : EndIf
  rc=Pi3FbDmaPoll()
  If rc=0 : ProcedureReturn 0 : EndIf
  pi3_fb_clear_pending=0
  If rc<0
    pi3_fb_error=#PI3_FB_ERR_OWNERSHIP : ProcedureReturn -1
  EndIf
  pi3_fb_dirty=1 : pi3_fb_dirty_left=0 : pi3_fb_dirty_top=0
  pi3_fb_dirty_right=pi3_fb_width : pi3_fb_dirty_bottom=pi3_fb_height
  ProcedureReturn 1
EndProcedure

Procedure Pi3FbDirtyAdd(x.i,y.i,w.i,h.i)
  Protected right.i, bottom.i
  If w<=0 Or h<=0
    ProcedureReturn
  EndIf
  If x<0 Or y<0 Or x>pi3_fb_width-w Or y>pi3_fb_height-h
    ProcedureReturn
  EndIf
  right=x+w : bottom=y+h
  If pi3_fb_dirty=0
    pi3_fb_dirty=1 : pi3_fb_dirty_left=x : pi3_fb_dirty_top=y
    pi3_fb_dirty_right=right : pi3_fb_dirty_bottom=bottom
  Else
    If x<pi3_fb_dirty_left : pi3_fb_dirty_left=x : EndIf
    If y<pi3_fb_dirty_top : pi3_fb_dirty_top=y : EndIf
    If right>pi3_fb_dirty_right : pi3_fb_dirty_right=right : EndIf
    If bottom>pi3_fb_dirty_bottom : pi3_fb_dirty_bottom=bottom : EndIf
  EndIf
EndProcedure

Procedure.i Pi3FbRenderCapacity()
  ProcedureReturn #PI3_FB_RENDER_BYTES
EndProcedure

Procedure.i Pi3FbPropertyBusy()
  Protected p.i=((@pi3_fb_message[0]+15)>>4)<<4
  ProcedureReturn Bool(pi3_mailbox_outstanding<>0 And pi3_mailbox_async_buffer=p)
EndProcedure

Procedure.i Pi3FbWriteAllowed()
  ProcedureReturn Bool(pi3_fb_attached<>0 And Pi3FbPropertyBusy()=0 And pi3_fb<>0 And pi3_fb_dma_state<2 And pi3_fb_dma_active=0 And pi3_fb_clear_pending=0 And pi3_fb_present_pending=0 And pi3_fb_scroll_phase=0)
EndProcedure

Procedure.i Pi3FbPresentPending()
  ProcedureReturn pi3_fb_present_pending
EndProcedure

; Start a nonblocking copy from the NC render buffer to firmware scanout.
; The renderer must not modify the buffer until Pi3FbPresentPoll completes.
Procedure.i Pi3FbPresentBegin()
  Protected x.i,y.i,w.i,h.i,rowBytes.i,gap.i,lenWord.i,stride.i,rc.i
  If pi3_fb_attached=0 Or Pi3FbPropertyBusy()<>0 Or pi3_fb=0 Or pi3_fb_scanout=0 Or pi3_fb_dma_state>=2
    ProcedureReturn 0
  EndIf
  If pi3_fb_present_pending<>0
    ProcedureReturn 0
  EndIf
  If pi3_fb_dirty=0 : ProcedureReturn 1 : EndIf
  If Pi3FbDmaInit()=0 : ProcedureReturn 0 : EndIf
  x=pi3_fb_dirty_left : y=pi3_fb_dirty_top
  w=pi3_fb_dirty_right-x : h=pi3_fb_dirty_bottom-y
  rowBytes=w*4 : gap=pi3_fb_pitch-rowBytes
  If x<0 Or y<0 Or w<1 Or h<1 Or rowBytes>$FFFF Or h>$3FFF Or gap<0 Or gap>32767
    pi3_fb_dma_error=#PI3_FB_DMA_E_BUSY
    ProcedureReturn 0
  EndIf
  ; BCM2708's 2D DMA YLENGTH field stores row-count minus one.
  lenWord=((h-1)<<16)|(rowBytes&$FFFF)
  stride=((gap&$FFFF)<<16)|(gap&$FFFF)
  pi3_fb_present_left=x : pi3_fb_present_top=y
  pi3_fb_present_right=x+w : pi3_fb_present_bottom=y+h
  rc=Pi3FbDmaBegin(pi3_fb+y*pi3_fb_pitch+x*4,pi3_fb_scanout+y*pi3_fb_pitch+x*4,lenWord,stride,#PI3_FB_DMA_TI_SRC_INC|#PI3_FB_DMA_TI_DEST_INC)
  If rc<>1 : ProcedureReturn 0 : EndIf
  pi3_fb_present_pending=1
  ProcedureReturn 1
EndProcedure

; Poll one asynchronous present. No pixel writes occur while this is active.
Procedure.i Pi3FbPresentPoll()
  Protected rc.i
  If pi3_fb_present_pending=0 : ProcedureReturn 1 : EndIf
  rc=Pi3FbDmaPoll()
  If rc=0 : ProcedureReturn 0 : EndIf
  pi3_fb_present_pending=0
  If rc<0
    pi3_fb_error=#PI3_FB_ERR_OWNERSHIP
    ProcedureReturn -1
  EndIf
  pi3_fb_dirty=0
  Pi3MailboxBarrier()
  ProcedureReturn 1
EndProcedure

; Compatibility entry now starts a DMA present; it never copies on the CPU.
Procedure.i Pi3FbPresent()
  ProcedureReturn Pi3FbPresentBegin()
EndProcedure

Procedure.i Pi3FbPixel(x.i,y.i,colour.i)
  If Pi3FbWriteAllowed()=0 Or x<0 Or x>=pi3_fb_width Or y<0 Or y>=pi3_fb_height : ProcedureReturn 0 : EndIf
  PokeL(pi3_fb+y*pi3_fb_pitch+x*4,colour)
  Pi3FbDirtyAdd(x,y,1,1)
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3FbDmaBusAddress(address.i)
  ProcedureReturn (address & #PI3_FB_DMA_BUS_MASK) | #PI3_FB_DMA_BUS_ALIAS
EndProcedure

Procedure.i Pi3FbDmaInit()
  Protected channel.i
  Protected globalEnable.i
  Protected channelMask.i
  Protected cbBase.i
  Protected messageBase.i
  If pi3_fb_dma_state<>0 : ProcedureReturn Bool(pi3_fb_dma_state=1) : EndIf
  If pi3_fb=0 Or pi3_fb_scanout=0
    pi3_fb_dma_state=2 : pi3_fb_dma_error=#PI3_FB_DMA_E_BUSY
    ProcedureReturn 0
  EndIf
  channel=#PI3_FB_DMA_BASE+(#PI3_FB_DMA_CHAN<<8)
  ; CONBLK_AD as well as ACTIVE matters: firmware can leave a completed
  ; descriptor address behind, and this monitor must not reset its owner.
  If (PeekL(channel+#PI3_FB_DMA_CS)&(#PI3_FB_DMA_ACTIVE|#PI3_FB_DMA_ERROR))<>0 Or PeekL(channel+#PI3_FB_DMA_CONBLK)<>0
    ; We cannot inspect another owner's descriptor to prove its destination.
    ; Quarantine scanout rather than assume an active channel is unrelated.
    pi3_fb_dma_state=3 : pi3_fb_dma_error=#PI3_FB_DMA_E_UNSAFE
    ProcedureReturn 0
  EndIf
  globalEnable=#PI3_FB_DMA_BASE+#PI3_FB_DMA_GLOBAL_ENABLE
  channelMask=1<<#PI3_FB_DMA_CHAN
  If (PeekL(globalEnable)&channelMask)=0
    PokeL(globalEnable,PeekL(globalEnable)|channelMask)
    Pi3MailboxBarrier()
    If (PeekL(globalEnable)&channelMask)=0
      pi3_fb_dma_state=2 : pi3_fb_dma_error=#PI3_FB_DMA_E_BUSY
      ProcedureReturn 0
    EndIf
  EndIf
  ; The mailbox property buffer remains mapped NC after framebuffer
  ; allocation. Round into that same 192-byte reservation for a 32-byte
  ; control block followed by its scratch word; no new memory window or
  ; cached DMA metadata is introduced.
  messageBase=((@pi3_fb_message[0]+15)&~15)
  cbBase=((messageBase+31)&~31)
  If messageBase<@pi3_fb_message[0] Or messageBase+176>@pi3_fb_message[0]+192 Or cbBase<messageBase Or cbBase+32+#PI3_FB_DMA_FILL_TILE_BYTES>messageBase+176
    pi3_fb_dma_state=2 : pi3_fb_dma_error=#PI3_FB_DMA_E_BUSY
    ProcedureReturn 0
  EndIf
  pi3_fb_dma_cb=cbBase
  pi3_fb_dma_state=1
  pi3_fb_dma_error=#PI3_FB_DMA_E_NONE
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3FbDmaStopSafe(channel.i)
  Protected attempt.i
  Protected cs.i
  Protected quiesced.i = 0
  Protected start.i
  Protected now.i
  ; Abort this channel, then wait until both ACTIVE and outstanding writes
  ; clear before resetting it. A timeout must never fall through to CPU writes.
  PokeL(channel+#PI3_FB_DMA_CS,#PI3_FB_DMA_ABORT)
  start=Pi3Micros()
  If start<0 : ProcedureReturn 0 : EndIf
  For attempt=0 To 100000
    cs=PeekL(channel+#PI3_FB_DMA_CS)
    If (cs&#PI3_FB_DMA_ACTIVE)=0 And (cs&#PI3_FB_DMA_WAITING_WRITES)=0
      quiesced=1 : Break
    EndIf
    now=Pi3Micros()
    If now<start Or now-start>=#PI3_FB_DMA_STOP_TIMEOUT_US : Break : EndIf
  Next
  If quiesced=0 : ProcedureReturn 0 : EndIf
  PokeL(channel+#PI3_FB_DMA_CS,#PI3_FB_DMA_RESET)
  quiesced=0
  start=Pi3Micros()
  If start<0 : ProcedureReturn 0 : EndIf
  For attempt=0 To 100000
    cs=PeekL(channel+#PI3_FB_DMA_CS)
    If (cs&#PI3_FB_DMA_ACTIVE)=0 And PeekL(channel+#PI3_FB_DMA_CONBLK)=0
      quiesced=1 : Break
    EndIf
    now=Pi3Micros()
    If now<start Or now-start>=#PI3_FB_DMA_STOP_TIMEOUT_US : Break : EndIf
  Next
  ProcedureReturn quiesced
EndProcedure

; Save the failed transfer state while the live registers and descriptor still
; exist. The caller invokes this immediately before abort/reset.
Procedure.i Pi3FbDmaLatchFailure(channel.i, elapsedUs.i)
  Protected cb.i=pi3_fb_dma_cb
  pi3_fb_dma_fail_cs=PeekL(channel+#PI3_FB_DMA_CS)
  pi3_fb_dma_fail_conblk=PeekL(channel+#PI3_FB_DMA_CONBLK)
  pi3_fb_dma_fail_debug=PeekL(channel+#PI3_FB_DMA_DEBUG)
  pi3_fb_dma_fail_current_ti=PeekL(channel+#PI3_FB_DMA_TI)
  pi3_fb_dma_fail_current_src=PeekL(channel+#PI3_FB_DMA_SOURCE)
  pi3_fb_dma_fail_current_dst=PeekL(channel+#PI3_FB_DMA_DEST)
  pi3_fb_dma_fail_current_length=PeekL(channel+#PI3_FB_DMA_LENGTH)
  pi3_fb_dma_fail_current_stride=PeekL(channel+#PI3_FB_DMA_STRIDE)
  pi3_fb_dma_fail_ti=PeekL(cb)
  pi3_fb_dma_fail_src=PeekL(cb+4)
  pi3_fb_dma_fail_dst=PeekL(cb+8)
  pi3_fb_dma_fail_length=PeekL(cb+12)
  pi3_fb_dma_fail_stride=PeekL(cb+16)
  pi3_fb_dma_fail_elapsed_us=elapsedUs
  pi3_fb_dma_last_us=elapsedUs
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3FbDmaRun(src.i,dst.i,length.i,stride.i,transferInfo.i)
  Protected channel.i
  Protected start.i
  Protected now.i
  Protected cs.i
  Protected cb.i
  Protected attempt.i
  If Pi3FbDmaInit()=0
    If pi3_fb_dma_state=3 : ProcedureReturn -1 : EndIf
    ProcedureReturn 0
  EndIf
  If pi3_fb_dma_active<>0
    pi3_fb_dma_error=#PI3_FB_DMA_E_BUSY
    ProcedureReturn 0
  EndIf
  channel=#PI3_FB_DMA_BASE+(#PI3_FB_DMA_CHAN<<8)
  If (PeekL(channel+#PI3_FB_DMA_CS)&(#PI3_FB_DMA_ACTIVE|#PI3_FB_DMA_ERROR))<>0 Or PeekL(channel+#PI3_FB_DMA_CONBLK)<>0
    pi3_fb_dma_state=3 : pi3_fb_dma_error=#PI3_FB_DMA_E_UNSAFE
    ProcedureReturn -1
  EndIf
  cb=pi3_fb_dma_cb
  PokeL(cb,transferInfo|#PI3_FB_DMA_TI_TDMODE|#PI3_FB_DMA_TI_WAIT_RESP|#PI3_FB_DMA_TI_S_WIDTH|#PI3_FB_DMA_TI_D_WIDTH|#PI3_FB_DMA_TI_BURST)
  PokeL(cb+4,Pi3FbDmaBusAddress(src))
  PokeL(cb+8,Pi3FbDmaBusAddress(dst))
  ; BCM2835 2D-mode TXFR_LEN.YLENGTH stores row-count minus one; callers
  ; encode multirow transfers as (rows-1) in the high half of length.
  PokeL(cb+12,length)
  PokeL(cb+16,stride)
  PokeL(cb+20,0) : PokeL(cb+24,0) : PokeL(cb+28,0)
  Pi3MailboxBarrier()
  pi3_fb_dma_active=1
  pi3_fb_dma_submissions+1
  PokeL(channel+#PI3_FB_DMA_DEBUG,7)
  PokeL(channel+#PI3_FB_DMA_CONBLK,Pi3FbDmaBusAddress(cb))
  Pi3MailboxBarrier()
  PokeL(channel+#PI3_FB_DMA_CS,#PI3_FB_DMA_ACTIVE)
  start=Pi3Micros()
  If start<0 : start=0 : EndIf
  For attempt=0 To 5000000
    cs=PeekL(channel+#PI3_FB_DMA_CS)
    If (cs&#PI3_FB_DMA_ERROR)<>0 Or (PeekL(channel+#PI3_FB_DMA_DEBUG)&7)<>0
      pi3_fb_dma_error=#PI3_FB_DMA_E_ENGINE
      Break
    EndIf
    If (cs&#PI3_FB_DMA_END)<>0 And PeekL(channel+#PI3_FB_DMA_CONBLK)=0
      PokeL(channel+#PI3_FB_DMA_CS,#PI3_FB_DMA_END)
      Pi3MailboxBarrier()
      pi3_fb_dma_active=0
      pi3_fb_dma_error=#PI3_FB_DMA_E_NONE
      pi3_fb_dma_completions+1
      now=Pi3Micros()
      If now>=start And start>=0 : pi3_fb_dma_last_us=now-start : EndIf
      ProcedureReturn 1
    EndIf
    now=Pi3Micros()
    If now<0 Or now<start Or now-start>#PI3_FB_DMA_TIMEOUT_US
      pi3_fb_dma_error=#PI3_FB_DMA_E_TIMEOUT
      Break
    EndIf
  Next
  now=Pi3Micros()
  If now>=start And start>=0
    Pi3FbDmaLatchFailure(channel,now-start)
  Else
    Pi3FbDmaLatchFailure(channel,0)
  EndIf
  If Pi3FbDmaStopSafe(channel)=0
    pi3_fb_dma_state=3 : pi3_fb_dma_error=#PI3_FB_DMA_E_UNSAFE
    ; Leave active set: all pixel APIs refuse to touch the framebuffer.
    ProcedureReturn -1
  EndIf
  pi3_fb_dma_active=0
  pi3_fb_dma_state=2
  ProcedureReturn 0
EndProcedure

; Start one descriptor and return immediately. The resident monitor's UART
; mirror only enqueues bytes; its round-robin screen service polls this state
; and never waits for the DMA engine to finish.
Procedure.i Pi3FbDmaBegin(src.i,dst.i,length.i,stride.i,transferInfo.i)
  Protected channel.i
  Protected cb.i
  If Pi3FbPropertyBusy()<>0 : ProcedureReturn 0 : EndIf
  If Pi3FbDmaInit()=0
    If pi3_fb_dma_state=3 : ProcedureReturn -1 : EndIf
    ProcedureReturn 0
  EndIf
  If pi3_fb_dma_active<>0
    pi3_fb_dma_error=#PI3_FB_DMA_E_BUSY
    ProcedureReturn 0
  EndIf
  channel=#PI3_FB_DMA_BASE+(#PI3_FB_DMA_CHAN<<8)
  If (PeekL(channel+#PI3_FB_DMA_CS)&(#PI3_FB_DMA_ACTIVE|#PI3_FB_DMA_ERROR))<>0 Or PeekL(channel+#PI3_FB_DMA_CONBLK)<>0
    pi3_fb_dma_state=3 : pi3_fb_dma_error=#PI3_FB_DMA_E_UNSAFE
    ProcedureReturn -1
  EndIf
  cb=pi3_fb_dma_cb
  PokeL(cb,transferInfo|#PI3_FB_DMA_TI_TDMODE|#PI3_FB_DMA_TI_WAIT_RESP|#PI3_FB_DMA_TI_S_WIDTH|#PI3_FB_DMA_TI_D_WIDTH|#PI3_FB_DMA_TI_BURST)
  PokeL(cb+4,Pi3FbDmaBusAddress(src))
  PokeL(cb+8,Pi3FbDmaBusAddress(dst))
  PokeL(cb+12,length) : PokeL(cb+16,stride)
  PokeL(cb+20,0) : PokeL(cb+24,0) : PokeL(cb+28,0)
  Pi3MailboxBarrier()
  pi3_fb_dma_active=1 : pi3_fb_dma_start_us=Pi3Micros()
  PokeL(channel+#PI3_FB_DMA_DEBUG,7)
  PokeL(channel+#PI3_FB_DMA_CONBLK,Pi3FbDmaBusAddress(cb))
  Pi3MailboxBarrier()
  PokeL(channel+#PI3_FB_DMA_CS,#PI3_FB_DMA_ACTIVE)
  pi3_fb_dma_submissions+1
  ProcedureReturn 1
EndProcedure

; 0 remains in flight, 1 completed, -1 is quarantined/unsafe. No busy poll.
Procedure.i Pi3FbDmaPoll()
  Protected channel.i
  Protected cs.i
  Protected now.i
  If pi3_fb_dma_active=0 : ProcedureReturn 1 : EndIf
  channel=#PI3_FB_DMA_BASE+(#PI3_FB_DMA_CHAN<<8)
  cs=PeekL(channel+#PI3_FB_DMA_CS)
  If (cs&#PI3_FB_DMA_ERROR)<>0 Or (PeekL(channel+#PI3_FB_DMA_DEBUG)&7)<>0
    pi3_fb_dma_error=#PI3_FB_DMA_E_ENGINE
  ElseIf (cs&#PI3_FB_DMA_END)<>0 And PeekL(channel+#PI3_FB_DMA_CONBLK)=0
    PokeL(channel+#PI3_FB_DMA_CS,#PI3_FB_DMA_END)
    Pi3MailboxBarrier()
    pi3_fb_dma_active=0 : pi3_fb_dma_error=#PI3_FB_DMA_E_NONE
    now=Pi3Micros()
    If now>=pi3_fb_dma_start_us And pi3_fb_dma_start_us>=0
      pi3_fb_dma_last_us=now-pi3_fb_dma_start_us
    EndIf
    pi3_fb_dma_completions+1
    ProcedureReturn 1
  Else
    now=Pi3Micros()
    If now>=0 And pi3_fb_dma_start_us>=0 And now>=pi3_fb_dma_start_us And now-pi3_fb_dma_start_us<=#PI3_FB_DMA_TIMEOUT_US
      ProcedureReturn 0
    EndIf
    pi3_fb_dma_error=#PI3_FB_DMA_E_TIMEOUT
  EndIf
  now=Pi3Micros()
  If now>=pi3_fb_dma_start_us And pi3_fb_dma_start_us>=0
    Pi3FbDmaLatchFailure(channel,now-pi3_fb_dma_start_us)
  Else
    Pi3FbDmaLatchFailure(channel,0)
  EndIf
  If Pi3FbDmaStopSafe(channel)=0
    pi3_fb_dma_state=3 : pi3_fb_dma_error=#PI3_FB_DMA_E_UNSAFE
    ProcedureReturn -1
  EndIf
  pi3_fb_dma_active=0 : pi3_fb_dma_state=2
  ProcedureReturn -1
EndProcedure

; Fill a clipped 32-bit rectangle. TDMODE leaves source fixed and advances
; the destination by the visible row width plus the framebuffer pitch gap.
; Small rectangles stay on the CPU to avoid programming a DMA channel per cell.
Procedure.i Pi3FbFillRect(x.i,y.i,w.i,h.i,colour.i)
  Protected rowBytes.i
  Protected dst.i
  Protected xx.i,yy.i
  If Pi3FbWriteAllowed()=0 Or x<0 Or y<0 Or w<=0 Or h<=0
    ProcedureReturn 0
  EndIf
  If x>pi3_fb_width-w Or y>pi3_fb_height-h
    ProcedureReturn 0
  EndIf
  rowBytes=w*4
  If rowBytes<4 Or (rowBytes&3)<>0
    ProcedureReturn 0
  EndIf
  For yy=y To y+h-1
    dst=pi3_fb+yy*pi3_fb_pitch+x*4
    For xx=0 To rowBytes-4 Step 4
      PokeL(dst+xx,colour&$FFFFFFFF)
    Next
  Next
  Pi3FbDirtyAdd(x,y,w,h)
  ProcedureReturn 1
EndProcedure

; Move the visible rows up and fill the newly exposed band. CPU fallback is
; used only if DMA did not begin or was safely quiesced after an error. A
; channel whose writes might still be in flight returns -1 and pixel APIs
; refuse all later stores.
Procedure.i Pi3FbScrollUp(lines.i,colour.i)
  ProcedureReturn Pi3FbScrollRegionUp(0,pi3_fb_height,lines,colour)
EndProcedure

; Scroll a bounded full-width row region upward without disturbing pixels
; before `y` (the monitor's compact status row uses this contract).
Procedure.i Pi3FbScrollRegionUp(y.i,height.i,lines.i,colour.i)
  Protected keepRows.i
  Protected rowBytes.i
  Protected src.i
  Protected dst.i
  Protected cbStride.i
  Protected lenWord.i
  Protected rc.i
  Protected tileOffset.i
  Protected x.i,top.i
  If Pi3FbPropertyBusy()<>0 : ProcedureReturn 0 : EndIf
  If pi3_fb_dma_state=3 : ProcedureReturn -1 : EndIf
  If pi3_fb=0 Or y<0 Or height<1 Or y>pi3_fb_height Or height>pi3_fb_height-y Or lines<1 Or lines>=height Or (pi3_fb_pitch&3)<>0
    ProcedureReturn 0
  EndIf
  keepRows=height-lines
  rowBytes=pi3_fb_pitch
  If rowBytes<pi3_fb_width*4 Or rowBytes>$FFFF Or keepRows>$4000 Or lines>$4000
    ProcedureReturn 0
  EndIf
  ; For an upward scroll each source row is above its destination. Copy
  ; top-to-bottom so a destination cannot destroy a source row still needed.
  top=y
  src=pi3_fb+(top+lines)*pi3_fb_pitch
  dst=pi3_fb+top*pi3_fb_pitch
  ; In BCM2835 TDMODE, X transfers already advance each row by X length;
  ; stride fields are additional signed adjustments, so contiguous pitches use 0.
  cbStride=0
  lenWord=((keepRows-1)<<16)|(rowBytes&$FFFF)
  rc=0
  If rowBytes*keepRows>=#PI3_FB_DMA_MIN_BYTES
    rc=Pi3FbDmaRun(src,dst,lenWord,cbStride,#PI3_FB_DMA_TI_SRC_INC|#PI3_FB_DMA_TI_DEST_INC)
    If rc<0 : ProcedureReturn -1 : EndIf
  EndIf
  If rc=0
    ; Copy top row first. Each source is above its destination in address
    ; order, and this ascending loop preserves unread rows.
    For y=0 To keepRows-1
      src=pi3_fb+(top+y+lines)*pi3_fb_pitch
      dst=pi3_fb+(top+y)*pi3_fb_pitch
      For x=0 To rowBytes-4 Step 4
        PokeL(dst+x,PeekL(src+x))
      Next
    Next
  EndIf
  If pi3_fb_dma_state=3 : ProcedureReturn -1 : EndIf
  If rowBytes*lines>=#PI3_FB_DMA_MIN_BYTES
    Pi3FbDmaInit()
    ; Fill uses a fixed 32-bit source word, with full pitch rows so padding
    ; is included and every transfer remains one contiguous safe rectangle.
    If pi3_fb_dma_state=1
      For tileOffset=0 To #PI3_FB_DMA_FILL_TILE_BYTES-4 Step 4
        PokeL(pi3_fb_dma_cb+32+tileOffset,colour&$FFFFFFFF)
      Next
      lenWord=((lines-1)<<16)|(rowBytes&$FFFF)
      rc=Pi3FbDmaRun(pi3_fb_dma_cb+32,pi3_fb+(top+keepRows)*pi3_fb_pitch,lenWord,0,#PI3_FB_DMA_TI_DEST_INC)
      If rc<0 : ProcedureReturn -1 : EndIf
    Else
      rc=0
    EndIf
  Else
    rc=0
  EndIf
  If rc=0
    For y=keepRows To height-1
      dst=pi3_fb+(top+y)*pi3_fb_pitch
      For x=0 To rowBytes-4 Step 4 : PokeL(dst+x,colour&$FFFFFFFF) : Next
    Next
  EndIf
  Pi3MailboxBarrier()
  ProcedureReturn 1
EndProcedure

; Nonblocking counterpart for the monitor's scroll path. The DMA copy and
; newly exposed fill band are separate phases so the scheduler can service
; PL011 input between polls. If DMA is unavailable, one CPU row is copied or
; filled per poll, keeping fallback work bounded as well.
Procedure.i Pi3FbScrollRegionStart(y.i,height.i,lines.i,colour.i)
  Protected rowBytes.i
  Protected rc.i
  Protected lenWord.i
  Protected src.i
  Protected dst.i
  Protected tileOffset.i
  If Pi3FbPropertyBusy()<>0 Or pi3_fb_scroll_phase<>0 Or pi3_fb_dma_state>=2 Or pi3_fb_present_pending<>0
    ProcedureReturn 0
  EndIf
  If pi3_fb=0 Or y<0 Or height<1 Or y>pi3_fb_height Or height>pi3_fb_height-y Or lines<1 Or lines>=height Or (pi3_fb_pitch&3)<>0
    ProcedureReturn 0
  EndIf
  rowBytes=pi3_fb_pitch
  If rowBytes<pi3_fb_width*4 Or rowBytes>$FFFF Or height-lines>$4000 Or lines>$4000
    ProcedureReturn 0
  EndIf
  pi3_fb_scroll_top=y : pi3_fb_scroll_height=height
  pi3_fb_scroll_keep=height-lines : pi3_fb_scroll_lines=lines
  pi3_fb_scroll_next_row=0 : pi3_fb_scroll_next_word=0 : pi3_fb_scroll_colour=colour&$FFFFFFFF
  Pi3FbDmaInit()
  If pi3_fb_dma_state=3 : ProcedureReturn -1 : EndIf
  If pi3_fb_dma_state=1
    src=pi3_fb+(y+lines)*pi3_fb_pitch : dst=pi3_fb+y*pi3_fb_pitch
    lenWord=((pi3_fb_scroll_keep-1)<<16)|(rowBytes&$FFFF)
    rc=Pi3FbDmaBegin(src,dst,lenWord,0,#PI3_FB_DMA_TI_SRC_INC|#PI3_FB_DMA_TI_DEST_INC)
    If rc<0 : ProcedureReturn -1 : EndIf
    If rc>0 : pi3_fb_scroll_phase=1 : ProcedureReturn 1 : EndIf
  EndIf
  pi3_fb_scroll_phase=3
  ProcedureReturn 1
EndProcedure

; Poll returns 0 while work remains, 1 when the scroll is complete, and -1
; after an unsafe DMA condition. It never waits for a DMA completion.
Procedure.i Pi3FbScrollPoll()
  Protected rc.i
  Protected rowBytes.i
  Protected src.i,dst.i,x.i,done.i
  If pi3_fb_scroll_phase=0 : ProcedureReturn 1 : EndIf
  If pi3_fb_dma_state=3 : pi3_fb_scroll_phase=0 : ProcedureReturn -1 : EndIf
  If pi3_fb_scroll_phase=1
    rc=Pi3FbDmaPoll()
    If rc=0 : ProcedureReturn 0 : EndIf
    If rc<0 : pi3_fb_scroll_phase=0 : ProcedureReturn -1 : EndIf
    Pi3FbDmaInit()
    If pi3_fb_dma_state=3 : pi3_fb_scroll_phase=0 : ProcedureReturn -1 : EndIf
    If pi3_fb_dma_state=1
      For tileOffset=0 To #PI3_FB_DMA_FILL_TILE_BYTES-4 Step 4
        PokeL(pi3_fb_dma_cb+32+tileOffset,pi3_fb_scroll_colour&$FFFFFFFF)
      Next
      rowBytes=pi3_fb_pitch
      rc=Pi3FbDmaBegin(pi3_fb_dma_cb+32,pi3_fb+(pi3_fb_scroll_top+pi3_fb_scroll_keep)*pi3_fb_pitch,((pi3_fb_scroll_lines-1)<<16)|(rowBytes&$FFFF),0,#PI3_FB_DMA_TI_DEST_INC)
      If rc<0 : pi3_fb_scroll_phase=0 : ProcedureReturn -1 : EndIf
      If rc>0 : pi3_fb_scroll_phase=2 : ProcedureReturn 0 : EndIf
    EndIf
    pi3_fb_scroll_phase=4 : pi3_fb_scroll_next_row=0 : pi3_fb_scroll_next_word=0
    ProcedureReturn 0
  ElseIf pi3_fb_scroll_phase=2
    rc=Pi3FbDmaPoll()
    If rc=0 : ProcedureReturn 0 : EndIf
    If rc<0 : pi3_fb_scroll_phase=0 : ProcedureReturn -1 : EndIf
    pi3_fb_scroll_phase=0
    Pi3FbDirtyAdd(0,pi3_fb_scroll_top,pi3_fb_width,pi3_fb_scroll_height)
    Pi3MailboxBarrier()
    ProcedureReturn 1
  EndIf
  rowBytes=pi3_fb_pitch
  If pi3_fb_scroll_phase=3
    src=pi3_fb+(pi3_fb_scroll_top+pi3_fb_scroll_next_row+pi3_fb_scroll_lines)*rowBytes
    dst=pi3_fb+(pi3_fb_scroll_top+pi3_fb_scroll_next_row)*rowBytes
    done=0
    While pi3_fb_scroll_next_word<rowBytes/4 And done<512
      x=pi3_fb_scroll_next_word*4
      PokeL(dst+x,PeekL(src+x))
      pi3_fb_scroll_next_word=pi3_fb_scroll_next_word+1 : done=done+1
    Wend
    If pi3_fb_scroll_next_word<rowBytes/4 : ProcedureReturn 0 : EndIf
    pi3_fb_scroll_next_word=0 : pi3_fb_scroll_next_row=pi3_fb_scroll_next_row+1
    If pi3_fb_scroll_next_row<pi3_fb_scroll_keep : ProcedureReturn 0 : EndIf
    pi3_fb_scroll_phase=4 : pi3_fb_scroll_next_row=0
    ProcedureReturn 0
  EndIf
  If pi3_fb_scroll_phase=4
    dst=pi3_fb+(pi3_fb_scroll_top+pi3_fb_scroll_keep+pi3_fb_scroll_next_row)*rowBytes
    done=0
    While pi3_fb_scroll_next_word<rowBytes/4 And done<512
      x=pi3_fb_scroll_next_word*4
      PokeL(dst+x,pi3_fb_scroll_colour)
      pi3_fb_scroll_next_word=pi3_fb_scroll_next_word+1 : done=done+1
    Wend
    If pi3_fb_scroll_next_word<rowBytes/4 : ProcedureReturn 0 : EndIf
    pi3_fb_scroll_next_word=0 : pi3_fb_scroll_next_row=pi3_fb_scroll_next_row+1
    If pi3_fb_scroll_next_row<pi3_fb_scroll_lines : ProcedureReturn 0 : EndIf
    pi3_fb_scroll_phase=0
    Pi3FbDirtyAdd(0,pi3_fb_scroll_top,pi3_fb_width,pi3_fb_scroll_height)
    Pi3MailboxBarrier()
    ProcedureReturn 1
  EndIf
  pi3_fb_scroll_phase=0
  ProcedureReturn -1
EndProcedure

Procedure.i Pi3FbDmaState()
  ProcedureReturn pi3_fb_dma_state
EndProcedure
Procedure.i Pi3FbDmaError()
  ProcedureReturn pi3_fb_dma_error
EndProcedure

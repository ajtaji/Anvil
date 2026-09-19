; Firmware-owned early framebuffer, serialized cache-off boot only.
; Include timer and mailbox first. No DMA, VC4 acceleration or V3D claim.
Global Dim pi3_fb_message.l[48]
Global pi3_fb.i
Global pi3_fb_pitch.i
Global pi3_fb_size.i
Global pi3_fb_attempted.i
Global pi3_fb_column.i
Global pi3_fb_row.i
Global pi3_fb_pixel_order.i
Global pi3_fb_alpha_mode.i
Global pi3_fb_error.i

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
  If pi3_fb_row<20 : ProcedureReturn 0 : EndIf
  ; Upward copy is forward: source is always above destination, no clobber.
  For y=0 To 455
    For x=0 To 639
      PokeL(pi3_fb+y*pi3_fb_pitch+x*4,PeekL(pi3_fb+(y+24)*pi3_fb_pitch+x*4))
    Next
  Next
  background=Pi3FbPack(24,12,8)
  For y=456 To 479
    For x=0 To 639 : PokeL(pi3_fb+y*pi3_fb_pitch+x*4,background) : Next
  Next
  pi3_fb_row=19
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
      If pi3_fb_column>=42 : Pi3FbNewline() : EndIf
      Pi3FbChar(code,pi3_fb_column*15,pi3_fb_row*24)
      pi3_fb_column=pi3_fb_column+1
    EndIf
  Next
  Pi3FbNewline()
  Pi3MailboxBarrier()
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
Procedure.i Pi3FbInit(dtb.i,dtbEnd.i)
  Protected p.i
  Protected base.i
  Protected size.i
  Protected pitch.i
  Protected vc.i
  Protected vcSize.i
  Protected n.i
  Protected background.i
  ; Cold boot owns one allocation attempt. Never replace a known framebuffer
  ; or implicitly free firmware storage under a renderer on a repeated call.
  pi3_fb_error=#PI3_FB_ERR_NONE
  If pi3_fb_attempted<>0 Or pi3_mailbox_outstanding<>0
    pi3_fb_error=#PI3_FB_ERR_OWNERSHIP
    ProcedureReturn 0
  EndIf
  pi3_fb_attempted=1
  pi3_fb=0
  p=((@pi3_fb_message[0]+15)>>4)<<4
  For n=0 To 175 Step 4 : PokeL(p+n,0) : Next
  PokeL(p,176)
  ; This is the same old-scheme framebuffer transaction used by the pinned
  ; Raspberry Pi Linux bcm2708_fb driver: set geometry/depth/offset, allocate,
  ; then query pitch. Pixel order, alpha mode and VC memory are GETs so the
  ; firmware—not a caller preference—defines how returned pixels are packed.
  Pi3FbTag(p,8,$48003,8,640,480)
  Pi3FbTag(p,28,$48004,8,640,480)
  Pi3FbTag(p,48,$48005,4,32,0)
  Pi3FbTag(p,64,$48009,8,0,0)
  Pi3FbTag(p,84,$40001,8,4096,0)
  Pi3FbTag(p,104,$40008,4,0,0)
  Pi3FbTag(p,120,$40006,4,0,0)
  Pi3FbTag(p,136,$40007,4,0,0)
  Pi3FbTag(p,152,$10006,8,0,0)
  If Pi3MailboxCall(p,176)=0
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
  If PeekL(p+20)<>640 Or PeekL(p+24)<>480 Or PeekL(p+40)<>640 Or PeekL(p+44)<>480 Or PeekL(p+60)<>32 Or PeekL(p+76)<>0 Or PeekL(p+80)<>0
    pi3_fb_error=#PI3_FB_ERR_GEOMETRY
    ProcedureReturn 0
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
  If pitch<2560 Or pitch>4096 Or (pitch & 3)<>0 Or size<pitch*480 Or size>16777216 Or base>$3F000000-size
    pi3_fb_error=#PI3_FB_ERR_ALLOCATION
    ProcedureReturn 0
  EndIf
  ; VC RAM may legally end at the 1 GiB boundary. The BCM2837 peripheral
  ; window begins at $3F000000, so the FRAMEBUFFER itself must end below it,
  ; but rejecting the whole enclosing VC reservation for extending to
  ; $40000000 refused ordinary 1 GiB Pi 3 firmware layouts.
  If vcSize=0 Or vc>$40000000-vcSize Or base<vc
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
  pi3_fb_pitch=pitch : pi3_fb_size=size : pi3_fb=base
  ; Every write is inside the validated pixel rows; no stride padding touched.
  background=Pi3FbPack(24,12,8)
  For n=0 To 479
    For p=0 To 639 : PokeL(base+n*pitch+p*4,background) : Next
  Next
  Pi3MailboxBarrier()
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3FbError()
  ProcedureReturn pi3_fb_error
EndProcedure

Procedure.i Pi3FbPixel(x.i,y.i,colour.i)
  If pi3_fb=0 Or x<0 Or x>=640 Or y<0 Or y>=480 : ProcedureReturn 0 : EndIf
  PokeL(pi3_fb+y*pi3_fb_pitch+x*4,colour)
  ProcedureReturn 1
EndProcedure

; Firmware-owned early framebuffer, serialized cache-off boot only.
; Include timer and mailbox first. No DMA, VC4 acceleration or V3D claim.
Global Dim pi3_fb_message.l[48]
Global pi3_fb.i
Global pi3_fb_pitch.i
Global pi3_fb_size.i
Global pi3_fb_attempted.i
Global pi3_fb_column.i
Global pi3_fb_row.i

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
  If pi3_fb=0
    ProcedureReturn
  EndIf
    glyph=AnvilTextGlyph(code)
    For row=0 To 6
      For col=0 To 3
        If (glyph & (1 << ((6-row)*4+3-col)))<>0
          For sy=0 To 2
            For sx=0 To 2 : Pi3FbPixel(x+col*3+sx,y+row*3+sy,$00F0E0C0) : Next
          Next
        EndIf
      Next
    Next
EndProcedure

Procedure Pi3FbNewline()
  Protected y.i
  Protected x.i
  pi3_fb_column=0 : pi3_fb_row=pi3_fb_row+1
  If pi3_fb_row<20 : ProcedureReturn 0 : EndIf
  ; Upward copy is forward: source is always above destination, no clobber.
  For y=0 To 455
    For x=0 To 639
      PokeL(pi3_fb+y*pi3_fb_pitch+x*4,PeekL(pi3_fb+(y+24)*pi3_fb_pitch+x*4))
    Next
  Next
  For y=456 To 479
    For x=0 To 639 : PokeL(pi3_fb+y*pi3_fb_pitch+x*4,$00180C08) : Next
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
  If PeekL(buffer+offset)<>tag Or PeekL(buffer+offset+4)<>length : ProcedureReturn 0 : EndIf
  ProcedureReturn (PeekL(buffer+offset+8) & $FFFFFFFF) = ($80000000 | length)
EndProcedure
Procedure.i Pi3FbInit(dtb.i,dtbEnd.i)
  Protected p.i
  Protected base.i
  Protected size.i
  Protected pitch.i
  Protected vc.i
  Protected vcSize.i
  Protected n.i
  ; Cold boot owns one allocation attempt. Never replace a known framebuffer
  ; or implicitly free firmware storage under a renderer on a repeated call.
  If pi3_fb_attempted<>0 : ProcedureReturn 0 : EndIf
  If pi3_mailbox_outstanding<>0 : ProcedureReturn 0 : EndIf
  pi3_fb_attempted=1
  pi3_fb=0
  p=((@pi3_fb_message[0]+15)>>4)<<4
  For n=0 To 159 Step 4 : PokeL(p+n,0) : Next
  PokeL(p,156)
  Pi3FbTag(p,8,$48003,8,640,480)
  Pi3FbTag(p,28,$48004,8,640,480)
  Pi3FbTag(p,48,$48005,4,32,0)
  Pi3FbTag(p,64,$48006,4,1,0)
  Pi3FbTag(p,80,$40001,8,4096,0)
  Pi3FbTag(p,100,$40008,4,0,0)
  Pi3FbTag(p,116,$10006,8,0,0)
  Pi3FbTag(p,136,$48007,4,2,0)
  If Pi3MailboxCall(p,156)=0 : ProcedureReturn 0 : EndIf
  If Pi3FbReply(p,8,$48003,8)=0 Or Pi3FbReply(p,28,$48004,8)=0 Or Pi3FbReply(p,48,$48005,4)=0 Or Pi3FbReply(p,64,$48006,4)=0
    ProcedureReturn 0
  EndIf
  If Pi3FbReply(p,80,$40001,8)=0 Or Pi3FbReply(p,100,$40008,4)=0 Or Pi3FbReply(p,116,$10006,8)=0 Or Pi3FbReply(p,136,$48007,4)=0
    ProcedureReturn 0
  EndIf
  If PeekL(p+20)<>640 Or PeekL(p+24)<>480 Or PeekL(p+40)<>640 Or PeekL(p+44)<>480 Or PeekL(p+60)<>32 Or PeekL(p+76)<>1 Or PeekL(p+148)<>2
    ProcedureReturn 0
  EndIf
  base=PeekL(p+92)&$FFFFFFFF : size=PeekL(p+96)&$FFFFFFFF
  pitch=PeekL(p+112)&$FFFFFFFF
  vc=PeekL(p+128)&$FFFFFFFF : vcSize=PeekL(p+132)&$FFFFFFFF
  ; Require the coherent/direct VideoCore bus alias before translation.
  If (base & $C0000000)<>$C0000000 : ProcedureReturn 0 : EndIf
  base=base & $3FFFFFFF
  If pitch<2560 Or pitch>4096 Or (pitch & 3)<>0 Or size<pitch*480 Or size>16777216
    ProcedureReturn 0
  EndIf
  If vcSize=0 Or vc> $3F000000-vcSize Or base<vc Or base>$3F000000-size
    ProcedureReturn 0
  EndIf
  If base+size>vc+vcSize Or (base & 4095)<>0 : ProcedureReturn 0 : EndIf
  If base<$200000 And base+size>$80000 : ProcedureReturn 0 : EndIf
  If base<dtbEnd And base+size>dtb : ProcedureReturn 0 : EndIf
  pi3_fb_pitch=pitch : pi3_fb_size=size : pi3_fb=base
  ; Every write is inside the validated pixel rows; no stride padding touched.
  For n=0 To 479
    For p=0 To 639 : PokeL(base+n*pitch+p*4,$00180C08) : Next
  Next
  Pi3MailboxBarrier()
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3FbPixel(x.i,y.i,colour.i)
  If pi3_fb=0 Or x<0 Or x>=640 Or y<0 Or y>=480 : ProcedureReturn 0 : EndIf
  PokeL(pi3_fb+y*pi3_fb_pitch+x*4,colour)
  ProcedureReturn 1
EndProcedure

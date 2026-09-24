; RK3399 RGA2 glyph blitter for Anvil's shared TrueType atlas.
; Linux rga-hw.c/rga-buf.c define the command and one-level page tables.
; Opaque 12x20 glyph cells are composed once from TrueType coverage. RGA2
; requires a crop of at least 34x34, so the glyph atlas is copied by the CPU;
; a separate 40-line row publish can use RGA without touching adjacent cells.
; Include after font_atlas.pbi, before screen_console.pbi.

#ROCK_RGA_BASE = $FF680000
#ROCK_RGA_PMU = $FF310000
#ROCK_RGA_CRU = $FF760000
#ROCK_RGA_VERSION = $03218218
#ROCK_RGA_MIN_COPY_W = 34
#ROCK_RGA_MIN_COPY_H = 34
#ROCK_RGA_GLYPH_W = 12
#ROCK_RGA_GLYPH_H = 20
#ROCK_RGA_ATLAS_W = #ROCK_RGA_GLYPH_W * 16
#ROCK_RGA_ATLAS_H = #ROCK_RGA_GLYPH_H * 6
#ROCK_RGA_ATLAS_PIXELS = #ROCK_RGA_ATLAS_W * #ROCK_RGA_ATLAS_H
#ROCK_RGA_ATLAS_BYTES = #ROCK_RGA_ATLAS_PIXELS * 4
#ROCK_RGA_ROW_H = 40
#ROCK_RGA_MAX_ROW_BYTES = 2560 * #ROCK_RGA_ROW_H * 4
#ROCK_RGA_POLL_LIMIT = 100000

Global Dim rock_rga_normal.l[#ROCK_RGA_ATLAS_PIXELS]
Global Dim rock_rga_prompt.l[#ROCK_RGA_ATLAS_PIXELS]
Global Dim rock_rga_src_pages.a[272]
Global Dim rock_rga_alt_pages.a[272]
Global Dim rock_rga_dst_pages.a[432]
Global Dim rock_rga_scanout_pages.a[432]
Global Dim rock_rga_command.a[256]
Global rock_rga_ready.i
Global rock_rga_atlas_ready.i
Global rock_rga_error.i
Global rock_rga_jobs.i
Global rock_rga_failures.i
Global rock_rga_normal_offset.i
Global rock_rga_prompt_offset.i
Global rock_rga_dst_offset.i
Global rock_rga_src_table.i
Global rock_rga_alt_table.i
Global rock_rga_dst_table.i
Global rock_rga_scanout_table.i
Global rock_rga_command_addr.i
Global rock_rga_row_addr.i
Global rock_rga_row_pitch.i
Global rock_rga_row_width.i

Procedure.i RockRgaMapPages(table.i,buffer.i,bytes.i)
  Protected first.i
  Protected offset.i
  Protected pages.i
  Protected index.i
  If table=0 Or buffer=0 Or bytes<1 : ProcedureReturn -1 : EndIf
  first=buffer & ~$FFF
  offset=buffer-first
  pages=(offset+bytes+4095)/4096
  If pages<1 Or pages>104 : ProcedureReturn -1 : EndIf
  For index=0 To pages-1
    PokeL(table+index*4,first+index*4096)
  Next
  ProcedureReturn offset
EndProcedure

Procedure.i RockRgaColour(coverage.i,fg.i,bg.i)
  Protected inverse.i=255-coverage
  Protected red.i
  Protected green.i
  Protected blue.i
  red=((((fg >> 16) & 255)*coverage)+(((bg >> 16) & 255)*inverse)+127)/255
  green=((((fg >> 8) & 255)*coverage)+(((bg >> 8) & 255)*inverse)+127)/255
  blue=(((fg & 255)*coverage)+((bg & 255)*inverse)+127)/255
  ProcedureReturn $FF000000 | (red << 16) | (green << 8) | blue
EndProcedure

Procedure RockRgaComposeAtlas(normalFg.i,promptFg.i,bg.i)
  Protected code.i
  Protected index.i
  Protected x.i
  Protected y.i
  Protected srcX.i
  Protected srcY.i
  Protected dstX.i
  Protected dstY.i
  Protected alpha.i
  Protected src.i
  Protected dst.i
  For code=32 To 126
    index=code-32
    srcX=(index % 16)*#ROCK_FONT_CELL+(#ROCK_FONT_CELL-#ROCK_RGA_GLYPH_W)/2
    srcY=(index / 16)*#ROCK_FONT_CELL
    dstX=(index % 16)*#ROCK_RGA_GLYPH_W
    dstY=(index / 16)*#ROCK_RGA_GLYPH_H
    For y=0 To #ROCK_RGA_GLYPH_H-1
      For x=0 To #ROCK_RGA_GLYPH_W-1
        src=(srcY+y)*#ROCK_FONT_ATLAS_W+srcX+x
        dst=(dstY+y)*#ROCK_RGA_ATLAS_W+dstX+x
        alpha=(rock_font_atlas[src] >> 24) & 255
        rock_rga_normal[dst]=RockRgaColour(alpha,normalFg,bg)
        rock_rga_prompt[dst]=RockRgaColour(alpha,promptFg,bg)
      Next
    Next
    RockWatchdogPet()
  Next
EndProcedure

Procedure.i RockRgaInit(normalFg.i,promptFg.i,bg.i,rowBuffer.i,pitch.i,width.i)
  Protected blocked.i
  Protected source.i
  Protected prompt.i
  Protected previous.i
  If rock_rga_ready<>0 : ProcedureReturn 1 : EndIf
  rock_rga_error=0
  If rock_current_el<>12 Or (rock_sctlr_el3 & $1005)<>0 : rock_rga_error=1 : ProcedureReturn 0 : EndIf
  If rowBuffer=0 Or pitch<>width*4 Or pitch*#ROCK_RGA_ROW_H>#ROCK_RGA_MAX_ROW_BYTES Or width<320 Or width>2560
    rock_rga_error=2 : ProcedureReturn 0
  EndIf
  If RockFontPrepareAtlas()=0 : rock_rga_error=3 : ProcedureReturn 0 : EndIf
  RockRgaComposeAtlas(normalFg,promptFg,bg)
  rock_rga_atlas_ready=1
  ; The 1920x1080 HDMI path is the currently verified full-width mode.
  If width<>1920 Or pitch<>7680 : rock_rga_error=16 : ProcedureReturn 0 : EndIf
  blocked=0
  If ((PeekL(#ROCK_RGA_PMU+$14) | PeekL(#ROCK_RGA_PMU+$18)) & (1 << 18))<>0 : blocked=blocked | 1 : EndIf
  If ((PeekL(#ROCK_RGA_PMU+$60) | PeekL(#ROCK_RGA_PMU+$64) | PeekL(#ROCK_RGA_PMU+$68)) & (1 << 5))<>0 : blocked=blocked | 2 : EndIf
  If (PeekL(#ROCK_RGA_CRU+$310) & $700)<>0 : blocked=blocked | 4 : EndIf
  If (PeekL(#ROCK_RGA_CRU+$340) & $F00)<>0 : blocked=blocked | 8 : EndIf
  If (PeekL(#ROCK_RGA_CRU+$418) & $680)<>0 : blocked=blocked | 16 : EndIf
  If blocked<>0 : rock_rga_error=$100 | blocked : ProcedureReturn 0 : EndIf
  If (PeekL(#ROCK_RGA_BASE+$28) & $FFFFFFFF)<>#ROCK_RGA_VERSION : rock_rga_error=4 : ProcedureReturn 0 : EndIf
  source=@rock_rga_normal[0]
  prompt=@rock_rga_prompt[0]
  rock_rga_src_table=(@rock_rga_src_pages[0]+15) & ~$F
  rock_rga_alt_table=(@rock_rga_alt_pages[0]+15) & ~$F
  rock_rga_dst_table=(@rock_rga_dst_pages[0]+15) & ~$F
  rock_rga_scanout_table=(@rock_rga_scanout_pages[0]+15) & ~$F
  rock_rga_command_addr=(@rock_rga_command[0]+15) & ~$F
  If source<0 Or prompt<0 Or rowBuffer<0 Or rock_rga_src_table<0 Or rock_rga_alt_table<0 Or rock_rga_dst_table<0 Or rock_rga_scanout_table<0 Or rock_rga_command_addr<0
    rock_rga_error=5 : ProcedureReturn 0
  EndIf
  If source>$FFFFFFFF Or prompt>$FFFFFFFF Or rowBuffer>$FFFFFFFF Or rock_rga_scanout_table>$FFFFFFFF Or rock_rga_command_addr>$FFFFFFFF
    rock_rga_error=6 : ProcedureReturn 0
  EndIf
  rock_rga_normal_offset=RockRgaMapPages(rock_rga_src_table,source,#ROCK_RGA_ATLAS_BYTES)
  rock_rga_prompt_offset=RockRgaMapPages(rock_rga_alt_table,prompt,#ROCK_RGA_ATLAS_BYTES)
  rock_rga_dst_offset=RockRgaMapPages(rock_rga_dst_table,rowBuffer,pitch*#ROCK_RGA_ROW_H)
  If rock_rga_normal_offset<0 Or rock_rga_prompt_offset<0 Or rock_rga_dst_offset<0
    rock_rga_error=7 : ProcedureReturn 0
  EndIf
  rock_rga_row_addr=rowBuffer
  rock_rga_row_pitch=pitch
  rock_rga_row_width=width
  previous=PeekL(#ROCK_RGA_BASE+$10) & $FFFFFFFF
  If (previous & 15)<>0
    PokeL(#ROCK_RGA_BASE+$10,(previous & 15) << 4)
    If (PeekL(#ROCK_RGA_BASE+$10) & 15)<>0 : rock_rga_error=8 : ProcedureReturn 0 : EndIf
  EndIf
  rock_rga_ready=1
  ProcedureReturn 1
EndProcedure

; The hardware crop minimum is larger than a glyph. Copy the precomposed
; TrueType coverage cell instead of dividing RGB channels for every pixel.
Procedure.i RockRgaAtlasGlyph(code.i,x.i,target.i,pitch.i,width.i,height.i,style.i)
  Protected atlas.i
  Protected source.i
  Protected row.i
  Protected column.i
  Protected index.i
  Protected atlasRow.i
  Protected atlasColumn.i
  If rock_rga_atlas_ready=0 Or target=0 Or height<#ROCK_RGA_GLYPH_H
    ProcedureReturn 0
  EndIf
  If x<0 Or x+#ROCK_RGA_GLYPH_W>width Or pitch<width*4
    ProcedureReturn 0
  EndIf
  If code<32 Or code>126 : code=63 : EndIf
  atlas=@rock_rga_normal[0]
  If style<>0 : atlas=@rock_rga_prompt[0] : EndIf
  index=code-32
  atlasRow=index / 16
  atlasColumn=index % 16
  source=atlas+(atlasRow*#ROCK_RGA_GLYPH_H*#ROCK_RGA_ATLAS_W+atlasColumn*#ROCK_RGA_GLYPH_W)*4
  For row=0 To #ROCK_RGA_GLYPH_H-1
    For column=0 To #ROCK_RGA_GLYPH_W-1
      PokeL(target+row*pitch+(x+column)*4,PeekL(source+row*#ROCK_RGA_ATLAS_W*4+column*4))
    Next
  Next
  ProcedureReturn 1
EndProcedure

; Publish a complete 40-line tile. The caller owns the lower 20 lines and
; must fill them with the existing scanout bytes before this copy. A single
; RGA transaction then updates the text row without disturbing its neighbor.
Procedure.i RockRgaCopyRow(destination.i,framebuffer.i,frameBytes.i)
  Protected destinationOffset.i
  Protected command.i
  Protected word.i
  Protected interrupt.i
  Protected poll.i
  If rock_rga_ready=0 : ProcedureReturn 0 : EndIf
  If rock_rga_row_width<#ROCK_RGA_MIN_COPY_W Or #ROCK_RGA_ROW_H<#ROCK_RGA_MIN_COPY_H
    rock_rga_error=12 : ProcedureReturn 0
  EndIf
  If destination<framebuffer Or destination+rock_rga_row_pitch*#ROCK_RGA_ROW_H>framebuffer+frameBytes Or destination+rock_rga_row_pitch*#ROCK_RGA_ROW_H<destination
    rock_rga_error=13 : ProcedureReturn 0
  EndIf
  destinationOffset=RockRgaMapPages(rock_rga_scanout_table,destination,rock_rga_row_pitch*#ROCK_RGA_ROW_H)
  If destinationOffset<0 : rock_rga_error=14 : ProcedureReturn 0 : EndIf
  command=rock_rga_command_addr
  For word=0 To 31 : PokeL(command+word*4,0) : Next
  PokeL(command+$00,$40)
  PokeL(command+$04,$10)
  PokeL(command+$08,rock_rga_dst_offset)
  PokeL(command+$18,(rock_rga_row_width << 16) | rock_rga_row_width)
  PokeL(command+$1C,((#ROCK_RGA_ROW_H-1) << 16) | (rock_rga_row_width-1))
  PokeL(command+$38,$10)
  PokeL(command+$3C,destinationOffset)
  PokeL(command+$48,rock_rga_row_pitch/4)
  PokeL(command+$4C,((#ROCK_RGA_ROW_H-1) << 16) | (rock_rga_row_width-1))
  PokeL(command+$6C,$777)
  PokeL(command+$70,rock_rga_dst_table >> 4)
  PokeL(command+$74,rock_rga_scanout_table >> 4)
  PokeL(command+$78,rock_rga_scanout_table >> 4)
  ASM
    dsb sy
  ENDASM
  PokeL(#ROCK_RGA_BASE+$08,command)
  PokeL(#ROCK_RGA_BASE+$00,0)
  PokeL(#ROCK_RGA_BASE+$00,$22)
  PokeL(#ROCK_RGA_BASE+$10,$600)
  ASM
    dsb sy
  ENDASM
  PokeL(#ROCK_RGA_BASE+$04,1)
  interrupt=0
  For poll=0 To #ROCK_RGA_POLL_LIMIT-1
    interrupt=PeekL(#ROCK_RGA_BASE+$10) & $FFFFFFFF
    If (interrupt & 15)<>0 : Break : EndIf
    If (poll & $FFF)=0 : RockWatchdogPet() : EndIf
  Next
  If (interrupt & 15)<>0 : PokeL(#ROCK_RGA_BASE+$10,(interrupt & 15) << 4) : EndIf
  If (interrupt & 4)=0 Or (interrupt & 3)<>0
    PokeL(#ROCK_RGA_BASE+$00,0)
    rock_rga_error=15
    rock_rga_failures=rock_rga_failures+1
    rock_rga_ready=0
    ProcedureReturn 0
  EndIf
  rock_rga_jobs=rock_rga_jobs+1
  ProcedureReturn 1
EndProcedure

Procedure.i RockRgaCopyGlyph(code.i,x.i,style.i)
  Protected sourceTable.i
  Protected sourceOffset.i
  Protected index.i
  Protected atlasRow.i
  Protected atlasCol.i
  Protected command.i
  Protected interrupt.i
  Protected poll.i
  Protected word.i
  If #ROCK_RGA_GLYPH_W<#ROCK_RGA_MIN_COPY_W Or #ROCK_RGA_GLYPH_H<#ROCK_RGA_MIN_COPY_H
    rock_rga_error=11 : ProcedureReturn 0
  EndIf
  If rock_rga_ready=0 : ProcedureReturn 0 : EndIf
  If x<0 Or x+#ROCK_RGA_GLYPH_W>rock_rga_row_width
    rock_rga_error=9 : ProcedureReturn 0
  EndIf
  If code<32 Or code>126 : code=63 : EndIf
  sourceTable=rock_rga_src_table
  sourceOffset=rock_rga_normal_offset
  If style<>0
    sourceTable=rock_rga_alt_table
    sourceOffset=rock_rga_prompt_offset
  EndIf
  index=code-32
  atlasRow=index / 16
  atlasCol=index % 16
  sourceOffset=sourceOffset+(atlasRow*#ROCK_RGA_GLYPH_H*#ROCK_RGA_ATLAS_W+atlasCol*#ROCK_RGA_GLYPH_W)*4
  command=rock_rga_command_addr
  For word=0 To 31 : PokeL(command+word*4,0) : Next
  PokeL(command+$00,$40)
  PokeL(command+$04,$10)
  PokeL(command+$08,sourceOffset)
  PokeL(command+$18,(#ROCK_RGA_ATLAS_W << 16) | #ROCK_RGA_ATLAS_W)
  PokeL(command+$1C,((#ROCK_RGA_GLYPH_H-1) << 16) | (#ROCK_RGA_GLYPH_W-1))
  PokeL(command+$38,$10)
  PokeL(command+$3C,rock_rga_dst_offset+x*4)
  PokeL(command+$48,rock_rga_row_pitch/4)
  PokeL(command+$4C,((#ROCK_RGA_GLYPH_H-1) << 16) | (#ROCK_RGA_GLYPH_W-1))
  PokeL(command+$6C,$777)
  PokeL(command+$70,sourceTable >> 4)
  PokeL(command+$74,rock_rga_dst_table >> 4)
  PokeL(command+$78,rock_rga_dst_table >> 4)
  ASM
    dsb sy
  ENDASM
  PokeL(#ROCK_RGA_BASE+$08,command)
  PokeL(#ROCK_RGA_BASE+$00,0)
  PokeL(#ROCK_RGA_BASE+$00,$22)
  PokeL(#ROCK_RGA_BASE+$10,$600)
  ASM
    dsb sy
  ENDASM
  PokeL(#ROCK_RGA_BASE+$04,1)
  interrupt=0
  For poll=0 To #ROCK_RGA_POLL_LIMIT-1
    interrupt=PeekL(#ROCK_RGA_BASE+$10) & $FFFFFFFF
    If (interrupt & 15)<>0 : Break : EndIf
    If (poll & $FFF)=0 : RockWatchdogPet() : EndIf
  Next
  If (interrupt & 15)<>0 : PokeL(#ROCK_RGA_BASE+$10,(interrupt & 15) << 4) : EndIf
  If (interrupt & 4)=0 Or (interrupt & 3)<>0
    rock_rga_error=10
    rock_rga_failures=rock_rga_failures+1
    rock_rga_ready=0
    ProcedureReturn 0
  EndIf
  rock_rga_jobs=rock_rga_jobs+1
  ProcedureReturn 1
EndProcedure

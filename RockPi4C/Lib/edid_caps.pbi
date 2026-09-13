; Bounded EDID capability inventory. This reports only timings explicitly
; encoded by the monitor; it never manufactures a mode or changes selection.

#ROCK_EDID_MAX_BLOCKS = 256
; A CTA block can encode at most 119 SVDs in its 123-byte data-block
; collection. 255 extensions plus every base timing therefore fit without
; truncation. Keep the collector fail-closed if this bound ever changes.
#ROCK_EDID_CAP_MAX = 30400

#ROCK_EDID_CAP_ESTABLISHED = 1
#ROCK_EDID_CAP_STANDARD = 2
#ROCK_EDID_CAP_BASE_DTD = 3
#ROCK_EDID_CAP_CTA_SVD = 4
#ROCK_EDID_CAP_CTA_DTD = 5

#ROCK_EDID_ERROR_NONE = 0
#ROCK_EDID_ERROR_BLOCK_COUNT = 1
#ROCK_EDID_ERROR_BASE = 2
#ROCK_EDID_ERROR_CHECKSUM = 3
#ROCK_EDID_ERROR_EXTENSION_TAG = 4
#ROCK_EDID_ERROR_CTA_REVISION = 5
#ROCK_EDID_ERROR_CTA_OFFSET = 6
#ROCK_EDID_ERROR_CTA_BLOCK = 7
#ROCK_EDID_ERROR_DTD = 8
#ROCK_EDID_ERROR_CAPACITY = 9

Global rock_edid_block_count.i
Global rock_edid_cap_count.i
Global rock_edid_error.i
Global rock_edid_range_valid.i
Global rock_edid_range_min_v_hz.i
Global rock_edid_range_max_v_hz.i
Global rock_edid_range_min_h_khz.i
Global rock_edid_range_max_h_khz.i
Global rock_edid_range_max_pixel_hz.i
Global rock_edid_range_count.i

Global Dim rock_edid_range_min_v.i[3]
Global Dim rock_edid_range_max_v.i[3]
Global Dim rock_edid_range_min_h.i[3]
Global Dim rock_edid_range_max_h.i[3]
Global Dim rock_edid_range_max_pixel.i[3]

Global Dim rock_edid_extension_tag.i[#ROCK_EDID_MAX_BLOCKS-1]
Global Dim rock_edid_extension_parsed.i[#ROCK_EDID_MAX_BLOCKS-1]

Global Dim rock_edid_cap_source.i[#ROCK_EDID_CAP_MAX-1]
Global Dim rock_edid_cap_code.i[#ROCK_EDID_CAP_MAX-1]
Global Dim rock_edid_cap_native.i[#ROCK_EDID_CAP_MAX-1]
Global Dim rock_edid_cap_mapped.i[#ROCK_EDID_CAP_MAX-1]
Global Dim rock_edid_cap_width.i[#ROCK_EDID_CAP_MAX-1]
Global Dim rock_edid_cap_height.i[#ROCK_EDID_CAP_MAX-1]
Global Dim rock_edid_cap_refresh_millihz.i[#ROCK_EDID_CAP_MAX-1]
Global Dim rock_edid_cap_pixel_hz.i[#ROCK_EDID_CAP_MAX-1]
Global Dim rock_edid_cap_htotal.i[#ROCK_EDID_CAP_MAX-1]
Global Dim rock_edid_cap_vtotal.i[#ROCK_EDID_CAP_MAX-1]
Global Dim rock_edid_cap_interlaced.i[#ROCK_EDID_CAP_MAX-1]
Global Dim rock_edid_cap_hsync_positive.i[#ROCK_EDID_CAP_MAX-1]
Global Dim rock_edid_cap_vsync_positive.i[#ROCK_EDID_CAP_MAX-1]

Procedure RockEdidCapsReset()
  Protected block.i
  rock_edid_block_count=0
  rock_edid_cap_count=0
  rock_edid_error=#ROCK_EDID_ERROR_NONE
  rock_edid_range_valid=0
  rock_edid_range_min_v_hz=0
  rock_edid_range_max_v_hz=0
  rock_edid_range_min_h_khz=0
  rock_edid_range_max_h_khz=0
  rock_edid_range_max_pixel_hz=0
  rock_edid_range_count=0
  For block=0 To #ROCK_EDID_MAX_BLOCKS-1
    rock_edid_extension_tag[block]=0
    rock_edid_extension_parsed[block]=0
  Next
EndProcedure

Procedure.i RockEdidBlockChecksum(block.i)
  Protected index.i
  Protected sum.i
  For index=0 To 127
    sum=(sum+(PeekA(block+index) & 255)) & 255
  Next
  ProcedureReturn Bool(sum=0)
EndProcedure

Procedure.i RockEdidCapAdd(source.i,code.i,native.i,mapped.i,width.i,height.i,refreshMilliHz.i,pixelHz.i,hTotal.i,vTotal.i,interlaced.i,hPositive.i,vPositive.i)
  Protected slot.i=rock_edid_cap_count
  If slot<0 Or slot>=#ROCK_EDID_CAP_MAX
    rock_edid_error=#ROCK_EDID_ERROR_CAPACITY
    ProcedureReturn 0
  EndIf
  rock_edid_cap_source[slot]=source
  rock_edid_cap_code[slot]=code
  rock_edid_cap_native[slot]=native
  rock_edid_cap_mapped[slot]=mapped
  rock_edid_cap_width[slot]=width
  rock_edid_cap_height[slot]=height
  rock_edid_cap_refresh_millihz[slot]=refreshMilliHz
  rock_edid_cap_pixel_hz[slot]=pixelHz
  rock_edid_cap_htotal[slot]=hTotal
  rock_edid_cap_vtotal[slot]=vTotal
  rock_edid_cap_interlaced[slot]=interlaced
  rock_edid_cap_hsync_positive[slot]=hPositive
  rock_edid_cap_vsync_positive[slot]=vPositive
  rock_edid_cap_count=slot+1
  ProcedureReturn 1
EndProcedure

Procedure.i RockEdidCapDtd(dtd.i,source.i,code.i,native.i)
  Protected pixelHz.i=((PeekA(dtd) & 255) | ((PeekA(dtd+1) & 255) << 8))*10000
  Protected width.i
  Protected hBlank.i
  Protected height.i
  Protected vBlank.i
  Protected hOffset.i
  Protected hWidth.i
  Protected vOffset.i
  Protected vWidth.i
  Protected hTotal.i
  Protected vTotal.i
  Protected flags.i
  Protected hPositive.i=-1
  Protected vPositive.i=-1
  Protected refreshMilliHz.i
  If pixelHz=0 : ProcedureReturn 1 : EndIf
  width=(PeekA(dtd+2) & 255) | ((PeekA(dtd+4) & $F0) << 4)
  hBlank=(PeekA(dtd+3) & 255) | ((PeekA(dtd+4) & $0F) << 8)
  height=(PeekA(dtd+5) & 255) | ((PeekA(dtd+7) & $F0) << 4)
  vBlank=(PeekA(dtd+6) & 255) | ((PeekA(dtd+7) & $0F) << 8)
  hOffset=(PeekA(dtd+8) & 255) | ((PeekA(dtd+11) & $C0) << 2)
  hWidth=(PeekA(dtd+9) & 255) | ((PeekA(dtd+11) & $30) << 4)
  vOffset=((PeekA(dtd+10) & $F0) >> 4) | ((PeekA(dtd+11) & $0C) << 2)
  vWidth=(PeekA(dtd+10) & $0F) | ((PeekA(dtd+11) & $03) << 4)
  If width<1 Or height<1 Or hBlank<1 Or vBlank<1 Or hWidth<1 Or vWidth<1 Or hOffset+hWidth>hBlank Or vOffset+vWidth>vBlank
    rock_edid_error=#ROCK_EDID_ERROR_DTD
    ProcedureReturn 0
  EndIf
  hTotal=width+hBlank
  vTotal=height+vBlank
  refreshMilliHz=(pixelHz*1000)/(hTotal*vTotal)
  flags=PeekA(dtd+17) & 255
  If (flags & $18)=$18
    hPositive=Bool((flags & 2)<>0)
    vPositive=Bool((flags & 4)<>0)
  EndIf
  ProcedureReturn RockEdidCapAdd(source,code,native,1,width,height,refreshMilliHz,pixelHz,hTotal,vTotal,Bool((flags & $80)<>0),hPositive,vPositive)
EndProcedure

Procedure.i RockEdidCapEstablished(code.i,width.i,height.i,refreshHz.i,interlaced.i)
  ProcedureReturn RockEdidCapAdd(#ROCK_EDID_CAP_ESTABLISHED,code,0,1,width,height,refreshHz*1000,0,0,0,interlaced,-1,-1)
EndProcedure

Procedure.i RockEdidCapsEstablished(base.i)
  Protected byte35.i=PeekA(base+35) & 255
  Protected byte36.i=PeekA(base+36) & 255
  Protected byte37.i=PeekA(base+37) & 255
  If (byte35 & $80)<>0 : If RockEdidCapEstablished(0,720,400,70,0)=0 : ProcedureReturn 0 : EndIf : EndIf
  If (byte35 & $40)<>0 : If RockEdidCapEstablished(1,720,400,88,0)=0 : ProcedureReturn 0 : EndIf : EndIf
  If (byte35 & $20)<>0 : If RockEdidCapEstablished(2,640,480,60,0)=0 : ProcedureReturn 0 : EndIf : EndIf
  If (byte35 & $10)<>0 : If RockEdidCapEstablished(3,640,480,67,0)=0 : ProcedureReturn 0 : EndIf : EndIf
  If (byte35 & $08)<>0 : If RockEdidCapEstablished(4,640,480,72,0)=0 : ProcedureReturn 0 : EndIf : EndIf
  If (byte35 & $04)<>0 : If RockEdidCapEstablished(5,640,480,75,0)=0 : ProcedureReturn 0 : EndIf : EndIf
  If (byte35 & $02)<>0 : If RockEdidCapEstablished(6,800,600,56,0)=0 : ProcedureReturn 0 : EndIf : EndIf
  If (byte35 & $01)<>0 : If RockEdidCapEstablished(7,800,600,60,0)=0 : ProcedureReturn 0 : EndIf : EndIf
  If (byte36 & $80)<>0 : If RockEdidCapEstablished(8,800,600,72,0)=0 : ProcedureReturn 0 : EndIf : EndIf
  If (byte36 & $40)<>0 : If RockEdidCapEstablished(9,800,600,75,0)=0 : ProcedureReturn 0 : EndIf : EndIf
  If (byte36 & $20)<>0 : If RockEdidCapEstablished(10,832,624,75,0)=0 : ProcedureReturn 0 : EndIf : EndIf
  If (byte36 & $10)<>0 : If RockEdidCapEstablished(11,1024,768,87,1)=0 : ProcedureReturn 0 : EndIf : EndIf
  If (byte36 & $08)<>0 : If RockEdidCapEstablished(12,1024,768,60,0)=0 : ProcedureReturn 0 : EndIf : EndIf
  If (byte36 & $04)<>0 : If RockEdidCapEstablished(13,1024,768,70,0)=0 : ProcedureReturn 0 : EndIf : EndIf
  If (byte36 & $02)<>0 : If RockEdidCapEstablished(14,1024,768,75,0)=0 : ProcedureReturn 0 : EndIf : EndIf
  If (byte36 & $01)<>0 : If RockEdidCapEstablished(15,1280,1024,75,0)=0 : ProcedureReturn 0 : EndIf : EndIf
  If (byte37 & $80)<>0 : If RockEdidCapEstablished(16,1152,870,75,0)=0 : ProcedureReturn 0 : EndIf : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i RockEdidCapsStandard(base.i)
  Protected slot.i
  Protected first.i
  Protected second.i
  Protected width.i
  Protected height.i
  Protected aspect.i
  Protected refreshHz.i
  For slot=0 To 7
    first=PeekA(base+38+slot*2) & 255
    second=PeekA(base+39+slot*2) & 255
    If first<>1 Or second<>1
      width=(first+31)*8
      aspect=(second >> 6) & 3
      If aspect=0
        If (PeekA(base+19) & 255)<3 : height=width : Else : height=width*10/16 : EndIf
      ElseIf aspect=1
        height=width*3/4
      ElseIf aspect=2
        height=width*4/5
      Else
        height=width*9/16
      EndIf
      refreshHz=(second & 63)+60
      If RockEdidCapAdd(#ROCK_EDID_CAP_STANDARD,slot,0,1,width,height,refreshHz*1000,0,0,0,0,-1,-1)=0 : ProcedureReturn 0 : EndIf
    EndIf
  Next
  ProcedureReturn 1
EndProcedure

Procedure RockEdidCapsRange(descriptor.i)
  Protected slot.i=rock_edid_range_count
  If slot>=4 : rock_edid_error=#ROCK_EDID_ERROR_CAPACITY : ProcedureReturn 0 : EndIf
  rock_edid_range_valid=1
  rock_edid_range_min_v_hz=PeekA(descriptor+5) & 255
  rock_edid_range_max_v_hz=PeekA(descriptor+6) & 255
  rock_edid_range_min_h_khz=PeekA(descriptor+7) & 255
  rock_edid_range_max_h_khz=PeekA(descriptor+8) & 255
  rock_edid_range_max_pixel_hz=(PeekA(descriptor+9) & 255)*10000000
  rock_edid_range_min_v[slot]=rock_edid_range_min_v_hz
  rock_edid_range_max_v[slot]=rock_edid_range_max_v_hz
  rock_edid_range_min_h[slot]=rock_edid_range_min_h_khz
  rock_edid_range_max_h[slot]=rock_edid_range_max_h_khz
  rock_edid_range_max_pixel[slot]=rock_edid_range_max_pixel_hz
  rock_edid_range_count=slot+1
  ProcedureReturn 1
EndProcedure

Procedure.i RockEdidCapsBaseDescriptors(base.i)
  Protected slot.i
  Protected descriptor.i
  Protected pixel.i
  For slot=0 To 3
    descriptor=base+54+slot*18
    pixel=(PeekA(descriptor) & 255) | ((PeekA(descriptor+1) & 255) << 8)
    If pixel<>0
      If RockEdidCapDtd(descriptor,#ROCK_EDID_CAP_BASE_DTD,slot,Bool(slot=0))=0 : ProcedureReturn 0 : EndIf
    ElseIf (PeekA(descriptor+2) & 255)=0 And (PeekA(descriptor+3) & 255)=$FD
      If RockEdidCapsRange(descriptor)=0 : ProcedureReturn 0 : EndIf
    EndIf
  Next
  ProcedureReturn 1
EndProcedure

Procedure.i RockEdidCapCtaSvd(svd.i)
  Protected vic.i=svd & $7F
  Protected native.i=Bool((svd & $80)<>0)
  Protected width.i
  Protected height.i
  Protected refresh.i
  Protected interlaced.i
  Protected mapped.i=1
  Select vic
    Case 1 : width=640 : height=480 : refresh=60000
    Case 2 : width=720 : height=480 : refresh=60000
    Case 3 : width=720 : height=480 : refresh=60000
    Case 4 : width=1280 : height=720 : refresh=60000
    Case 5 : width=1920 : height=1080 : refresh=60000 : interlaced=1
    Case 16 : width=1920 : height=1080 : refresh=60000
    Case 17 : width=720 : height=576 : refresh=50000
    Case 18 : width=720 : height=576 : refresh=50000
    Case 19 : width=1280 : height=720 : refresh=50000
    Case 20 : width=1920 : height=1080 : refresh=50000 : interlaced=1
    Case 31 : width=1920 : height=1080 : refresh=50000
    Case 32 : width=1920 : height=1080 : refresh=24000
    Case 33 : width=1920 : height=1080 : refresh=25000
    Case 34 : width=1920 : height=1080 : refresh=30000
    Case 93 : width=3840 : height=2160 : refresh=24000
    Case 94 : width=3840 : height=2160 : refresh=25000
    Case 95 : width=3840 : height=2160 : refresh=30000
    Case 96 : width=3840 : height=2160 : refresh=50000
    Case 97 : width=3840 : height=2160 : refresh=60000
    Default : mapped=0
  EndSelect
  ProcedureReturn RockEdidCapAdd(#ROCK_EDID_CAP_CTA_SVD,vic,native,mapped,width,height,refresh,0,0,0,interlaced,-1,-1)
EndProcedure

Procedure.i RockEdidCapsCta(extension.i)
  Protected revision.i=PeekA(extension+1) & 255
  Protected dtdOffset.i=PeekA(extension+2) & 255
  Protected nativeDtds.i=PeekA(extension+3) & 15
  Protected offset.i=4
  Protected header.i
  Protected tag.i
  Protected length.i
  Protected index.i
  Protected dtdIndex.i
  If revision<3 Or revision>4
    rock_edid_error=#ROCK_EDID_ERROR_CTA_REVISION : ProcedureReturn 0
  EndIf
  If dtdOffset=0 : ProcedureReturn 1 : EndIf
  If dtdOffset<4 Or dtdOffset>127
    rock_edid_error=#ROCK_EDID_ERROR_CTA_OFFSET : ProcedureReturn 0
  EndIf
  While offset<dtdOffset
    header=PeekA(extension+offset) & 255
    tag=(header >> 5) & 7
    length=header & 31
    If offset+1+length>dtdOffset
      rock_edid_error=#ROCK_EDID_ERROR_CTA_BLOCK : ProcedureReturn 0
    EndIf
    If tag=2
      For index=0 To length-1
        If RockEdidCapCtaSvd(PeekA(extension+offset+1+index) & 255)=0 : ProcedureReturn 0 : EndIf
      Next
    EndIf
    offset=offset+1+length
  Wend
  dtdIndex=0
  offset=dtdOffset
  While offset+18<=127
    If (PeekA(extension+offset) & 255)=0 And (PeekA(extension+offset+1) & 255)=0 : Break : EndIf
    If RockEdidCapDtd(extension+offset,#ROCK_EDID_CAP_CTA_DTD,dtdIndex,Bool(dtdIndex<nativeDtds))=0 : ProcedureReturn 0 : EndIf
    dtdIndex=dtdIndex+1
    offset=offset+18
  Wend
  ProcedureReturn 1
EndProcedure

Procedure.i RockEdidCapsCollect(edid.i,blocks.i)
  Protected extensionCount.i
  Protected block.i
  Protected extension.i
  Protected tag.i
  RockEdidCapsReset()
  If edid=0 Or blocks<1 Or blocks>#ROCK_EDID_MAX_BLOCKS
    rock_edid_error=#ROCK_EDID_ERROR_BLOCK_COUNT : ProcedureReturn 0
  EndIf
  If RockModeEdidBaseReason(edid)<>#ROCK_MODE_REASON_PREFERRED
    rock_edid_error=#ROCK_EDID_ERROR_BASE : ProcedureReturn 0
  EndIf
  extensionCount=PeekA(edid+126) & 255
  If blocks<>extensionCount+1
    rock_edid_error=#ROCK_EDID_ERROR_BLOCK_COUNT : ProcedureReturn 0
  EndIf
  rock_edid_block_count=blocks
  If RockEdidCapsEstablished(edid)=0 : ProcedureReturn 0 : EndIf
  If RockEdidCapsStandard(edid)=0 : ProcedureReturn 0 : EndIf
  If RockEdidCapsBaseDescriptors(edid)=0 : ProcedureReturn 0 : EndIf
  If extensionCount>0
    For block=1 To extensionCount
      extension=edid+block*128
      If RockEdidBlockChecksum(extension)=0
        rock_edid_error=#ROCK_EDID_ERROR_CHECKSUM : ProcedureReturn 0
      EndIf
      tag=PeekA(extension) & 255
      rock_edid_extension_tag[block]=tag
      If tag=2
        If RockEdidCapsCta(extension)=0 : ProcedureReturn 0 : EndIf
        rock_edid_extension_parsed[block]=1
      EndIf
    Next
  EndIf
  ProcedureReturn 1
EndProcedure

; Fail-closed EDID base-block mode selection for the RK3399 little VOP.
; The first detailed timing is the EDID preferred timing. Only timings that
; fit the pinned Radxa VOPL limits and either an exact VPLL table entry or the
; Rockchip RK3399 automatic PLL contract are admitted. 1024x768@60 is a
; fallback only when the same valid EDID base block advertises that
; established timing in byte 36 bit 3.

#ROCK_MODE_SOURCE_NONE = -1
#ROCK_MODE_SOURCE_FALLBACK = 0
#ROCK_MODE_SOURCE_PREFERRED_DTD = 1

#ROCK_MODE_REASON_PREFERRED = 0
#ROCK_MODE_REASON_EDID_NULL = 1
#ROCK_MODE_REASON_EDID_HEADER = 2
#ROCK_MODE_REASON_EDID_CHECKSUM = 3
#ROCK_MODE_REASON_EDID_VERSION = 4
#ROCK_MODE_REASON_DTD_MISSING = 5
#ROCK_MODE_REASON_INTERLACE = 6
#ROCK_MODE_REASON_SYNC = 7
#ROCK_MODE_REASON_STEREO = 8
#ROCK_MODE_REASON_H_GEOMETRY = 9
#ROCK_MODE_REASON_V_GEOMETRY = 10
#ROCK_MODE_REASON_VOP_LIMIT = 11
#ROCK_MODE_REASON_PITCH = 12
#ROCK_MODE_REASON_VPLL_RATE = 13
#ROCK_MODE_REASON_LINK_RATE = 14
#ROCK_MODE_REASON_NO_ESTABLISHED_FALLBACK = 15

Global rock_mode_width.i
Global rock_mode_height.i
Global rock_mode_pixel_hz.i
Global rock_mode_htotal.i
Global rock_mode_hsync_start.i
Global rock_mode_hsync_end.i
Global rock_mode_vtotal.i
Global rock_mode_vsync_start.i
Global rock_mode_vsync_end.i
Global rock_mode_hsync_positive.i
Global rock_mode_vsync_positive.i
Global rock_mode_pitch.i
Global rock_mode_source.i = #ROCK_MODE_SOURCE_NONE
Global rock_mode_reason.i
Global rock_mode_valid.i

; Raw preferred-DTD identity is diagnostic only. It remains available when a
; valid EDID falls back because that preferred timing is not representable.
Global rock_mode_preferred_width.i
Global rock_mode_preferred_height.i
Global rock_mode_preferred_pixel_hz.i

; VPLL plan consumed by cru.pbi. Exact pinned-table entries take priority;
; otherwise Rockchip's documented automatic RK3399 calculation is used.
Global rock_mode_vpll_ref.i
Global rock_mode_vpll_fb.i
Global rock_mode_vpll_post1.i
Global rock_mode_vpll_post2.i
Global rock_mode_vpll_dsmpd.i
Global rock_mode_vpll_frac.i
Global rock_mode_vpll_actual_hz.i

Procedure.i RockModeEdidBaseReason(edid.i)
  Protected index.i
  Protected sum.i
  If edid=0 : ProcedureReturn #ROCK_MODE_REASON_EDID_NULL : EndIf
  If (PeekA(edid) & 255)<>$00 Or (PeekA(edid+1) & 255)<>$FF Or (PeekA(edid+2) & 255)<>$FF Or (PeekA(edid+3) & 255)<>$FF
    ProcedureReturn #ROCK_MODE_REASON_EDID_HEADER
  EndIf
  If (PeekA(edid+4) & 255)<>$FF Or (PeekA(edid+5) & 255)<>$FF Or (PeekA(edid+6) & 255)<>$FF Or (PeekA(edid+7) & 255)<>$00
    ProcedureReturn #ROCK_MODE_REASON_EDID_HEADER
  EndIf
  For index=0 To 127
    sum=(sum+(PeekA(edid+index) & 255)) & 255
  Next
  If sum<>0 : ProcedureReturn #ROCK_MODE_REASON_EDID_CHECKSUM : EndIf
  ; Detailed timing layout used below is defined by EDID 1.x. Revisions above
  ; 1.4 are not silently treated as the same wire contract.
  If (PeekA(edid+18) & 255)<>1 Or (PeekA(edid+19) & 255)>4
    ProcedureReturn #ROCK_MODE_REASON_EDID_VERSION
  EndIf
  ProcedureReturn #ROCK_MODE_REASON_PREFERRED
EndProcedure

Procedure.i RockModeGcd(first.i,second.i)
  Protected temporary.i
  While first>0
    If second>first : temporary=first : first=second : second=temporary : EndIf
    first=first-second
  Wend
  ProcedureReturn second
EndProcedure

Procedure RockModeVpllPublish(refDivider.i,feedbackDivider.i,postDivider1.i,postDivider2.i,dsmpd.i,fraction.i,actualHz.i)
  rock_mode_vpll_ref=refDivider
  rock_mode_vpll_fb=feedbackDivider
  rock_mode_vpll_post1=postDivider1
  rock_mode_vpll_post2=postDivider2
  rock_mode_vpll_dsmpd=dsmpd
  rock_mode_vpll_frac=fraction
  rock_mode_vpll_actual_hz=actualHz
EndProcedure

Procedure.i RockModeVpllPlan(pixelHz.i)
  Protected refDivider.i
  Protected feedbackDivider.i
  Protected postDivider1.i
  Protected postDivider2.i
  Protected dsmpd.i
  Protected fraction.i
  Protected vco.i
  Protected vcoMHz.i
  Protected remainder.i
  Protected divisor.i
  Protected common.i
  Protected scaled.i
  Protected actualHz.i
  Protected found.i

  ; The pinned automatic planner explicitly refuses FOUT equal to its 24 MHz
  ; reference rather than synthesizing an equivalent divided VCO.
  If pixelHz=24000000 : ProcedureReturn 0 : EndIf

  ; Preserve every exact member of Radxa's VPLL-specific RK3399 table.
  Select pixelHz
    Case 594000000 : refDivider=1 : feedbackDivider=123 : postDivider1=5 : postDivider2=1 : dsmpd=0 : fraction=$C00000
    Case 593406593 : refDivider=1 : feedbackDivider=123 : postDivider1=5 : postDivider2=1 : dsmpd=0 : fraction=10508804
    Case 297000000 : refDivider=1 : feedbackDivider=123 : postDivider1=5 : postDivider2=2 : dsmpd=0 : fraction=$C00000
    Case 296703297 : refDivider=1 : feedbackDivider=123 : postDivider1=5 : postDivider2=2 : dsmpd=0 : fraction=10508807
    Case 148500000 : refDivider=1 : feedbackDivider=129 : postDivider1=7 : postDivider2=3 : dsmpd=0 : fraction=$F00000
    Case 148351648 : refDivider=1 : feedbackDivider=123 : postDivider1=5 : postDivider2=4 : dsmpd=0 : fraction=10508800
    Case 106500000 : refDivider=1 : feedbackDivider=124 : postDivider1=7 : postDivider2=4 : dsmpd=0 : fraction=$400000
    Case 74250000 : refDivider=1 : feedbackDivider=129 : postDivider1=7 : postDivider2=6 : dsmpd=0 : fraction=$F00000
    Case 74175824 : refDivider=1 : feedbackDivider=129 : postDivider1=7 : postDivider2=6 : dsmpd=0 : fraction=13550823
    Case 65000000 : refDivider=1 : feedbackDivider=113 : postDivider1=7 : postDivider2=6 : dsmpd=0 : fraction=$C00000
    Case 59340659 : refDivider=1 : feedbackDivider=121 : postDivider1=7 : postDivider2=7 : dsmpd=0 : fraction=2581098
    Case 54000000 : refDivider=1 : feedbackDivider=110 : postDivider1=7 : postDivider2=7 : dsmpd=0 : fraction=$400000
    Case 27000000 : refDivider=1 : feedbackDivider=55 : postDivider1=7 : postDivider2=7 : dsmpd=0 : fraction=$200000
    Case 26973027 : refDivider=1 : feedbackDivider=55 : postDivider1=7 : postDivider2=7 : dsmpd=0 : fraction=1173232
    Default
      ; Rockchip's automatic RK3399 planner tries post-divider pairs in this
      ; order and accepts the first VCO from 800 through 2000 MHz.
      For postDivider1=1 To 7
        For postDivider2=1 To 7
          vco=pixelHz*postDivider1*postDivider2
          If vco>=800000000 And vco<=2000000000
            found=1
            Break
          EndIf
        Next
        If found<>0 : Break : EndIf
      Next
      If found=0 : ProcedureReturn 0 : EndIf
      If (pixelHz % 1000000)=0
        common=RockModeGcd(24,vco/1000000)
        refDivider=24/common
        feedbackDivider=(vco/1000000)/common
        dsmpd=1
        fraction=0
      Else
        vcoMHz=vco/1000000
        common=RockModeGcd(24,vcoMHz)
        refDivider=24/common
        feedbackDivider=vcoMHz/common
        remainder=vco % 1000000
        divisor=24000000/refDivider
        fraction=(remainder << 24)/divisor
        dsmpd=1
        If fraction>0 : dsmpd=0 : EndIf
      EndIf
  EndSelect
  If refDivider<1 Or refDivider>63 Or feedbackDivider<16 Or feedbackDivider>3200 Or postDivider1<1 Or postDivider1>7 Or postDivider2<1 Or postDivider2>7
    ProcedureReturn 0
  EndIf
  scaled=feedbackDivider*16777216+fraction
  actualHz=(24000000*scaled/refDivider)/(16777216*postDivider1*postDivider2)
  ; The source calculation truncates its 24-bit fraction. Over the EDID
  ; 10-kHz domain its result is exact or one hertz below the requested rate.
  If actualHz>pixelHz Or pixelHz-actualHz>1 : ProcedureReturn 0 : EndIf
  RockModeVpllPublish(refDivider,feedbackDivider,postDivider1,postDivider2,dsmpd,fraction,actualHz)
  ProcedureReturn 1
EndProcedure

Procedure.i RockModeVpllRateSupported(pixelHz.i)
  ProcedureReturn RockModeVpllPlan(pixelHz)
EndProcedure

Procedure RockModeCommit(width.i,height.i,pixelHz.i,hTotal.i,hSyncStart.i,hSyncEnd.i,vTotal.i,vSyncStart.i,vSyncEnd.i,hPositive.i,vPositive.i,pitch.i,source.i,reason.i)
  ; Publish validity last so no caller can observe a partly selected mode.
  rock_mode_valid=0
  rock_mode_width=width
  rock_mode_height=height
  rock_mode_pixel_hz=pixelHz
  rock_mode_htotal=hTotal
  rock_mode_hsync_start=hSyncStart
  rock_mode_hsync_end=hSyncEnd
  rock_mode_vtotal=vTotal
  rock_mode_vsync_start=vSyncStart
  rock_mode_vsync_end=vSyncEnd
  rock_mode_hsync_positive=hPositive
  rock_mode_vsync_positive=vPositive
  rock_mode_pitch=pitch
  rock_mode_source=source
  rock_mode_reason=reason
  rock_mode_valid=1
EndProcedure

Procedure.i RockModeFallback(edid.i,reason.i)
  Protected edidReason.i=RockModeEdidBaseReason(edid)
  rock_mode_valid=0
  If edidReason<>#ROCK_MODE_REASON_PREFERRED
    rock_mode_source=#ROCK_MODE_SOURCE_NONE
    rock_mode_reason=edidReason
    ProcedureReturn 0
  EndIf
  If ((PeekA(edid+36) & 255) & 8)=0
    rock_mode_source=#ROCK_MODE_SOURCE_NONE
    If reason=#ROCK_MODE_REASON_PREFERRED
      rock_mode_reason=#ROCK_MODE_REASON_NO_ESTABLISHED_FALLBACK
    Else
      rock_mode_reason=reason
    EndIf
    ProcedureReturn 0
  EndIf
  ; EDID established 1024x768@60: 65 MHz, 1344x806, negative sync.
  RockModeCommit(1024,768,65000000,1344,1048,1184,806,771,777,0,0,4096,#ROCK_MODE_SOURCE_FALLBACK,reason)
  ProcedureReturn 1
EndProcedure

Procedure.i RockModeSelect(edid.i)
  Protected reason.i=RockModeEdidBaseReason(edid)
  Protected dtd.i
  Protected pixelHz.i
  Protected width.i
  Protected hBlank.i
  Protected height.i
  Protected vBlank.i
  Protected hOffset.i
  Protected hWidth.i
  Protected vOffset.i
  Protected vWidth.i
  Protected hTotal.i
  Protected hSyncStart.i
  Protected hSyncEnd.i
  Protected vTotal.i
  Protected vSyncStart.i
  Protected vSyncEnd.i
  Protected pitch.i
  Protected flags.i
  Protected hPositive.i
  Protected vPositive.i

  rock_mode_valid=0
  rock_mode_source=#ROCK_MODE_SOURCE_NONE
  rock_mode_reason=reason
  rock_mode_preferred_width=0
  rock_mode_preferred_height=0
  rock_mode_preferred_pixel_hz=0
  If reason<>#ROCK_MODE_REASON_PREFERRED : ProcedureReturn 0 : EndIf

  dtd=edid+54
  pixelHz=((PeekA(dtd) & 255) | ((PeekA(dtd+1) & 255) << 8))*10000
  If pixelHz=0
    reason=#ROCK_MODE_REASON_DTD_MISSING
    ProcedureReturn RockModeFallback(edid,reason)
  EndIf
  width=(PeekA(dtd+2) & 255) | ((PeekA(dtd+4) & $F0) << 4)
  hBlank=(PeekA(dtd+3) & 255) | ((PeekA(dtd+4) & $0F) << 8)
  height=(PeekA(dtd+5) & 255) | ((PeekA(dtd+7) & $F0) << 4)
  vBlank=(PeekA(dtd+6) & 255) | ((PeekA(dtd+7) & $0F) << 8)
  hOffset=(PeekA(dtd+8) & 255) | ((PeekA(dtd+11) & $C0) << 2)
  hWidth=(PeekA(dtd+9) & 255) | ((PeekA(dtd+11) & $30) << 4)
  vOffset=((PeekA(dtd+10) & $F0) >> 4) | ((PeekA(dtd+11) & $0C) << 2)
  vWidth=(PeekA(dtd+10) & $0F) | ((PeekA(dtd+11) & $03) << 4)
  flags=PeekA(dtd+17) & 255
  rock_mode_preferred_width=width
  rock_mode_preferred_height=height
  rock_mode_preferred_pixel_hz=pixelHz

  If (flags & $80)<>0
    reason=#ROCK_MODE_REASON_INTERLACE
    ProcedureReturn RockModeFallback(edid,reason)
  EndIf
  If (flags & $18)<>$18
    reason=#ROCK_MODE_REASON_SYNC
    ProcedureReturn RockModeFallback(edid,reason)
  EndIf
  If (flags & $61)<>0
    reason=#ROCK_MODE_REASON_STEREO
    ProcedureReturn RockModeFallback(edid,reason)
  EndIf
  If width<=0 Or hBlank<=0 Or hWidth<=0 Or hOffset+hWidth>hBlank
    reason=#ROCK_MODE_REASON_H_GEOMETRY
    ProcedureReturn RockModeFallback(edid,reason)
  EndIf
  If height<=0 Or vBlank<=0 Or vWidth<=0 Or vOffset+vWidth>vBlank
    reason=#ROCK_MODE_REASON_V_GEOMETRY
    ProcedureReturn RockModeFallback(edid,reason)
  EndIf
  hTotal=width+hBlank
  hSyncStart=width+hOffset
  hSyncEnd=hSyncStart+hWidth
  vTotal=height+vBlank
  vSyncStart=height+vOffset
  vSyncEnd=vSyncStart+vWidth
  ; Pinned RK3399 VOP little v3.6 max output is 2560x1600. Its timing
  ; fields are 13 bits, so every programmed total/sync coordinate must fit.
  If width>2560 Or height>1600 Or hTotal>8191 Or hSyncStart>8191 Or hSyncEnd>8191 Or vTotal>8191 Or vSyncStart>8191 Or vSyncEnd>8191
    reason=#ROCK_MODE_REASON_VOP_LIMIT
    ProcedureReturn RockModeFallback(edid,reason)
  EndIf
  pitch=(width*4+15) & ~15
  ; WIN0_VIR is a 14-bit count of 32-bit words. This owner additionally uses
  ; 16-byte scanline alignment so framebuffer writes and VOP fetch agree.
  If pitch<width*4 Or (pitch & 15)<>0 Or pitch/4>$3FFF Or pitch*height>$FA0000
    reason=#ROCK_MODE_REASON_PITCH
    ProcedureReturn RockModeFallback(edid,reason)
  EndIf
  ; The board routes two lanes. HBR2 with 8b/10b encoding carries at most
  ; 360 MHz at RGB888; sink-specific trained bandwidth is checked later.
  If pixelHz*24>2*540000000*8
    reason=#ROCK_MODE_REASON_LINK_RATE
    ProcedureReturn RockModeFallback(edid,reason)
  EndIf
  If RockModeVpllRateSupported(pixelHz)=0
    reason=#ROCK_MODE_REASON_VPLL_RATE
    ProcedureReturn RockModeFallback(edid,reason)
  EndIf
  hPositive=0
  vPositive=0
  If (flags & 2)<>0 : hPositive=1 : EndIf
  If (flags & 4)<>0 : vPositive=1 : EndIf
  RockModeCommit(width,height,pixelHz,hTotal,hSyncStart,hSyncEnd,vTotal,vSyncStart,vSyncEnd,hPositive,vPositive,pitch,#ROCK_MODE_SOURCE_PREFERRED_DTD,#ROCK_MODE_REASON_PREFERRED)
  ProcedureReturn 1
EndProcedure

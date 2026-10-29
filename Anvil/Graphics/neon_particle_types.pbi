; SPDX-License-Identifier: MIT
; Portable particle input, matching desktop centre/size/radian/RGBA fields.
; Records are caller-owned. A renderer copies them during preparation.
XIncludeFile "Anvil/Math/float32.pbi"
XIncludeFile "Anvil/Math/float32_convert.pbi"
#NEON_PARTICLE_MAX = 10000
#NEON_PARTICLE_ERR_ARGS = -21600
#NEON_PARTICLE_ERR_CAPACITY = -21601
Structure NeonParticleRecord Align #PB_Structure_AlignC
  x.f : y.f : size.f : angle.f
  r.f : g.f : b.f : a.f
EndStructure

Procedure.i NeonParticleRecordValid(*p.NeonParticleRecord)
  Protected i.i,bits.i
  If *p=0 Or (*p & 3)<>0 : ProcedureReturn 0 : EndIf
  For i=0 To 7
    bits=PeekL(*p+i*4)
    If (bits & $7F800000)=$7F800000 : ProcedureReturn 0 : EndIf
  Next
  If *p\x < -20000.0 Or *p\x>20000.0 Or *p\y < -20000.0 Or *p\y>20000.0 Or *p\size<=0.0 Or *p\size>4096.0 Or *p\angle < -100.53 Or *p\angle>100.53 : ProcedureReturn 0 : EndIf
  If *p\r<0.0 Or *p\r>1.0 Or *p\g<0.0 Or *p\g>1.0 Or *p\b<0.0 Or *p\b>1.0 Or *p\a<0.0 Or *p\a>1.0 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure
Procedure.i NeonParticlePackedColour(*p.NeonParticleRecord)
  Protected red.i,green.i,blue.i,alpha.i
  alpha=MathFToI32(*p\a*255.0+0.5) : red=MathFToI32(*p\r*255.0+0.5)
  green=MathFToI32(*p\g*255.0+0.5) : blue=MathFToI32(*p\b*255.0+0.5)
  ProcedureReturn (alpha<<24) | (red<<16) | (green<<8) | blue
EndProcedure

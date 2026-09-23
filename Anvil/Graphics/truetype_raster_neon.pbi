; BCM2711-only in-place alpha conversion for already validated coverage counts.
; Invalid data and short capacity are rejected before any output byte changes.

Procedure.i AnvilTrueTypeCoverageCountsToAlphaNeon(buffer.i,pixelCount.i,capacity.i)
  Protected n.i,pos.i,value.i
  If pixelCount<0 Or capacity<pixelCount Or (pixelCount>0 And buffer=0)
    ProcedureReturn 0
  EndIf
  n=0
  While n<pixelCount
    value=PeekA(buffer+n)&$FF
    If value>16 : ProcedureReturn 0 : EndIf
    n+1
  Wend
  pos=0
  While pos+16<=pixelCount
    a64_neon_coverage_alpha16(buffer+pos)
    pos+16
  Wend
  While pos<pixelCount
    value=PeekA(buffer+pos)&$FF
    PokeA(buffer+pos,(value*255+8)/16)
    pos+1
  Wend
  ProcedureReturn 1
EndProcedure

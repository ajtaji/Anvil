; BCM2711-only in-place alpha conversion for already validated coverage counts.
; Invalid data and short capacity are rejected before any output byte changes.

Procedure AnvilTrueTypeCoverageAlpha16Neon(buffer.i)
  ; The caller validates all sixteen counts before this writes any byte.
  ; AAPCS64 passes buffer in x0; x9 and v0-v4 are caller-saved registers.
  ; The buffer is only byte-aligned. Wide vector loads/stores fault under the
  ; monitor's alignment mode, so the memory edge is deliberately bytewise.
  ASM
    ldrb    w9, [x0, #0]
    ins     v0.b[0], w9
    ldrb    w9, [x0, #1]
    ins     v0.b[1], w9
    ldrb    w9, [x0, #2]
    ins     v0.b[2], w9
    ldrb    w9, [x0, #3]
    ins     v0.b[3], w9
    ldrb    w9, [x0, #4]
    ins     v0.b[4], w9
    ldrb    w9, [x0, #5]
    ins     v0.b[5], w9
    ldrb    w9, [x0, #6]
    ins     v0.b[6], w9
    ldrb    w9, [x0, #7]
    ins     v0.b[7], w9
    ldrb    w9, [x0, #8]
    ins     v0.b[8], w9
    ldrb    w9, [x0, #9]
    ins     v0.b[9], w9
    ldrb    w9, [x0, #10]
    ins     v0.b[10], w9
    ldrb    w9, [x0, #11]
    ins     v0.b[11], w9
    ldrb    w9, [x0, #12]
    ins     v0.b[12], w9
    ldrb    w9, [x0, #13]
    ins     v0.b[13], w9
    ldrb    w9, [x0, #14]
    ins     v0.b[14], w9
    ldrb    w9, [x0, #15]
    ins     v0.b[15], w9
    movi    v1.16b, #255
    umull   v2.8h, v0.8b, v1.8b
    umull2  v3.8h, v0.16b, v1.16b
    movi    v4.8h, #8
    add     v2.8h, v2.8h, v4.8h
    add     v3.8h, v3.8h, v4.8h
    ushr    v2.8h, v2.8h, #4
    ushr    v3.8h, v3.8h, #4
    uqxtn   v0.8b, v2.8h
    uqxtn2  v0.16b, v3.8h
    umov    w9, v0.b[0]
    strb    w9, [x0, #0]
    umov    w9, v0.b[1]
    strb    w9, [x0, #1]
    umov    w9, v0.b[2]
    strb    w9, [x0, #2]
    umov    w9, v0.b[3]
    strb    w9, [x0, #3]
    umov    w9, v0.b[4]
    strb    w9, [x0, #4]
    umov    w9, v0.b[5]
    strb    w9, [x0, #5]
    umov    w9, v0.b[6]
    strb    w9, [x0, #6]
    umov    w9, v0.b[7]
    strb    w9, [x0, #7]
    umov    w9, v0.b[8]
    strb    w9, [x0, #8]
    umov    w9, v0.b[9]
    strb    w9, [x0, #9]
    umov    w9, v0.b[10]
    strb    w9, [x0, #10]
    umov    w9, v0.b[11]
    strb    w9, [x0, #11]
    umov    w9, v0.b[12]
    strb    w9, [x0, #12]
    umov    w9, v0.b[13]
    strb    w9, [x0, #13]
    umov    w9, v0.b[14]
    strb    w9, [x0, #14]
    umov    w9, v0.b[15]
    strb    w9, [x0, #15]
  EndASM
EndProcedure

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
    AnvilTrueTypeCoverageAlpha16Neon(buffer+pos)
    pos+16
  Wend
  While pos<pixelCount
    value=PeekA(buffer+pos)&$FF
    PokeA(buffer+pos,(value*255+8)/16)
    pos+1
  Wend
  ProcedureReturn 1
EndProcedure

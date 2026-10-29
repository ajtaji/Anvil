; SPDX-License-Identifier: MIT
; Bounded measured UTF8 fitting. Caller prepares glyphs and selects a supported
; marker (ellipsis or three dots). No renderer/frame/allocator ownership.
XIncludeFile "Anvil/Math/float32.pbi"
XIncludeFile "Anvil/Graphics/neon_utf8.pbi"
XIncludeFile "Anvil/Graphics/neon_byte_ranges.pbi"
#NEON_TEXT_FIT_ERR_ARGS=-23100
#NEON_TEXT_FIT_ERR_TEXT=-23101
#NEON_TEXT_FIT_ERR_CAPACITY=-23102
#NEON_TEXT_FIT_ERR_METRICS=-23103
#NEON_TEXT_FIT_ERR_BUSY=-23104
#NEON_TEXT_FIT_ERR_UNBOUND=-23105
Procedure.f ntfWidthUnbound(font.i,text.i)
  ProcedureReturn -1.0
EndProcedure
Global ntfWidth.i=@ntfWidthUnbound,ntfActive.i,ntfBusy.i
Procedure.i NeonTextFitBind(measure.i)
  If ntfBusy<>0 : ProcedureReturn #NEON_TEXT_FIT_ERR_BUSY : EndIf
  If measure=0 : ProcedureReturn #NEON_TEXT_FIT_ERR_ARGS : EndIf
  ntfWidth=measure : ntfActive=1 : ProcedureReturn 0
EndProcedure
Procedure.i NeonTextFitUnbind()
  If ntfBusy<>0 : ProcedureReturn #NEON_TEXT_FIT_ERR_BUSY : EndIf
  ntfWidth=@ntfWidthUnbound : ntfActive=0 : ProcedureReturn 0
EndProcedure
Procedure.i ntfMetric(v.f)
  ProcedureReturn Bool(v>=0.0 And (MathBitsOf(v) & $7FFFFFFF)<=$4B800000)
EndProcedure
; Return the published byte count excluding NUL, or a negative error. Source
; and marker budgets include NUL. Scratch is disposable; output is unchanged
; on every refusal. The selected marker follows the caller's font glyph policy.
; Measurements must describe immutable prepared text with nonnegative advances.
Procedure.i NeonTextFit(output.i,capacity.i,scratch.i,scratchCapacity.i,source.i,sourceBudget.i,marker.i,markerBudget.i,font.i,room.f)
  Protected bytes.i,tailBytes.i,low.i,high.i,half.i,cut.i,best.i,n.i,i.i,rc.i
  Protected width.f,tailWidth.f
  If ntfBusy<>0 : ProcedureReturn #NEON_TEXT_FIT_ERR_BUSY : EndIf
  If sourceBudget<1 Or sourceBudget>4096 Or markerBudget<1 Or markerBudget>16 Or font<0 Or room<0.0 Or (MathBitsOf(room) & $7FFFFFFF)>$49742400
    ProcedureReturn #NEON_TEXT_FIT_ERR_ARGS
  EndIf
  If NeonByteSpan(output,capacity)=0 Or NeonByteSpan(scratch,scratchCapacity)=0 Or NeonByteSpan(source,sourceBudget)=0 Or NeonByteSpan(marker,markerBudget)=0
    ProcedureReturn #NEON_TEXT_FIT_ERR_ARGS
  EndIf
  If NeonByteOverlap(output,capacity,scratch,scratchCapacity)<>0 Or NeonByteOverlap(output,capacity,source,sourceBudget)<>0 Or NeonByteOverlap(output,capacity,marker,markerBudget)<>0 Or NeonByteOverlap(scratch,scratchCapacity,source,sourceBudget)<>0 Or NeonByteOverlap(scratch,scratchCapacity,marker,markerBudget)<>0
    ProcedureReturn #NEON_TEXT_FIT_ERR_ARGS
  EndIf
  bytes=NeonUtf8Length(source,sourceBudget) : tailBytes=NeonUtf8Length(marker,markerBudget)
  If bytes<0 Or tailBytes<0 : ProcedureReturn #NEON_TEXT_FIT_ERR_TEXT : EndIf
  If scratchCapacity<bytes+tailBytes+1 : ProcedureReturn #NEON_TEXT_FIT_ERR_CAPACITY : EndIf
  If ntfActive=0 : ProcedureReturn #NEON_TEXT_FIT_ERR_UNBOUND : EndIf
  ntfBusy=1
  width=ntfWidth(font,source)
  If ntfMetric(width)=0 : rc=#NEON_TEXT_FIT_ERR_METRICS
  ElseIf width<=room Or bytes=0
    n=bytes
    For i=0 To bytes : PokeA(scratch+i,PeekA(source+i)) : Next
  Else
    tailWidth=ntfWidth(font,marker)
    If ntfMetric(tailWidth)=0 : rc=#NEON_TEXT_FIT_ERR_METRICS
    ElseIf tailWidth>room
      PokeA(scratch,0) : n=0
    Else
      high=bytes-1
      While low<high
        half=(low+high+1)/2 : cut=NeonUtf8Prefix(source,bytes,half)
        For i=0 To cut-1 : PokeA(scratch+i,PeekA(source+i)) : Next
        For i=0 To tailBytes : PokeA(scratch+cut+i,PeekA(marker+i)) : Next
        width=ntfWidth(font,scratch)
        If ntfMetric(width)=0 : rc=#NEON_TEXT_FIT_ERR_METRICS : Break : EndIf
        If width<=room : low=half : best=cut : Else : high=half-1 : EndIf
      Wend
      If rc=0
        For i=0 To best-1 : PokeA(scratch+i,PeekA(source+i)) : Next
        For i=0 To tailBytes : PokeA(scratch+best+i,PeekA(marker+i)) : Next
        n=best+tailBytes : width=ntfWidth(font,scratch)
        If ntfMetric(width)=0 Or width>room : rc=#NEON_TEXT_FIT_ERR_METRICS : EndIf
      EndIf
    EndIf
  EndIf
  If rc=0 And n>=capacity : rc=#NEON_TEXT_FIT_ERR_CAPACITY : EndIf
  If rc=0
    For i=0 To n : PokeA(output+i,PeekA(scratch+i)) : Next
  EndIf
  ntfBusy=0
  If rc<>0 : ProcedureReturn rc : EndIf
  ProcedureReturn n
EndProcedure

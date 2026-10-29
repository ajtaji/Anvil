; SPDX-License-Identifier: MIT
; Locale-independent Unicode17 default full uppercase with caller-owned UTF8.
; No normalization, allocator, callbacks, renderer or device dependency.
XIncludeFile "Anvil/Graphics/neon_utf8.pbi"
XIncludeFile "Anvil/Graphics/neon_byte_ranges.pbi"
XIncludeFile "Anvil/Graphics/neon_unicode_upper_data.pbi"
#NEON_UPPER_ERR_ARGS=-23200
#NEON_UPPER_ERR_TEXT=-23201
#NEON_UPPER_ERR_CAPACITY=-23202
#NEON_UPPER_MAX_SOURCE=65536
; Byte reads keep generated rows safe regardless of surrounding data alignment.
Procedure.i ntuWord(p.i)
  ProcedureReturn (PeekA(p) & 255) | ((PeekA(p+1) & 255)<<8) | ((PeekA(p+2) & 255)<<16) | ((PeekA(p+3) & 255)<<24)
EndProcedure
Procedure.i ntuLookup(cp.i)
  Protected low.i,high.i=#NEON_UNICODE_UPPER_COUNT-1,half.i,value.i
  While low<=high
    half=(low+high)/2 : value=ntuWord(?nuuRows+half*12)
    If value=cp : ProcedureReturn half : EndIf
    If value<cp : low=half+1 : Else : high=half-1 : EndIf
  Wend
  ProcedureReturn -1
EndProcedure
; Required output bytes excluding NUL, or negative error. Budget includes NUL.
Procedure.i NeonTextUpperBytes(source.i,budget.i)
  Protected bytes.i,i.i,nextEnd.i,cp.i,row.i,wanted.i
  If budget<1 Or budget>#NEON_UPPER_MAX_SOURCE Or NeonByteSpan(source,budget)=0
    ProcedureReturn #NEON_UPPER_ERR_ARGS
  EndIf
  bytes=NeonUtf8Length(source,budget)
  If bytes<0 : ProcedureReturn #NEON_UPPER_ERR_TEXT : EndIf
  While i<bytes
    nextEnd=NeonUtf8Next(source,bytes,i) : cp=NeonUtf8ScalarAt(source,bytes,i)
    row=ntuLookup(cp)
    If row<0 : wanted=wanted+nextEnd-i
    Else : wanted=wanted+ntuWord(?nuuRows+row*12+8) : EndIf
    i=nextEnd
  Wend
  ProcedureReturn wanted
EndProcedure
; Refusals preserve the whole destination. Inputs remain immutable for the
; two-pass operation; output may not overlap the borrowed source budget.
Procedure.i NeonTextUpper(output.i,capacity.i,source.i,budget.i)
  Protected wanted.i,bytes.i,i.i,nextEnd.i,cp.i,row.i,offset.i,n.i,j.i,at.i
  If output<1 Or capacity<0 : ProcedureReturn #NEON_UPPER_ERR_ARGS : EndIf
  If capacity=0 : ProcedureReturn #NEON_UPPER_ERR_CAPACITY : EndIf
  If NeonByteSpan(output,capacity)=0 Or budget<1 Or budget>#NEON_UPPER_MAX_SOURCE Or NeonByteSpan(source,budget)=0
    ProcedureReturn #NEON_UPPER_ERR_ARGS
  EndIf
  If NeonByteOverlap(output,capacity,source,budget)<>0 : ProcedureReturn #NEON_UPPER_ERR_ARGS : EndIf
  wanted=NeonTextUpperBytes(source,budget)
  If wanted<0 : ProcedureReturn wanted : EndIf
  If wanted>=capacity : ProcedureReturn #NEON_UPPER_ERR_CAPACITY : EndIf
  bytes=NeonUtf8Length(source,budget)
  While i<bytes
    nextEnd=NeonUtf8Next(source,bytes,i) : cp=NeonUtf8ScalarAt(source,bytes,i)
    row=ntuLookup(cp)
    If row<0
      For j=i To nextEnd-1 : PokeA(output+at,PeekA(source+j)) : at=at+1 : Next
    Else
      offset=ntuWord(?nuuRows+row*12+4) : n=ntuWord(?nuuRows+row*12+8)
      For j=0 To n-1 : PokeA(output+at,PeekA(?nuuBytes+offset+j)) : at=at+1 : Next
    EndIf
    i=nextEnd
  Wend
  PokeA(output+at,0)
  ProcedureReturn wanted
EndProcedure

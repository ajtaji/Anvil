; SPDX-License-Identifier: MIT
; Optional ABI1.10 entropy binding for web nonces and frame masks.
; Does not change the ABI1.6 transport requirements for older callers.
Global *webRandomReadyFn,*webRandomBytesFn
Global webRandomBound.i
Procedure.i WebRandomBind(table.i)
  webRandomBound=0 : webRandomReadyFn=0 : webRandomBytesFn=0
  If table<=0 : ProcedureReturn -109 : EndIf
  If PeekN(table)<>$53564E41 Or PeekN(table+4)<>1 Or PeekN(table+8)<10 Or PeekN(table+12)<177
    ProcedureReturn -109
  EndIf
  webRandomBytesFn=PeekI(table+16+175*8) : webRandomReadyFn=PeekI(table+16+176*8)
  If webRandomBytesFn<=0 Or webRandomReadyFn<=0 : ProcedureReturn -109 : EndIf
  webRandomBound=1 : ProcedureReturn 0
EndProcedure
Procedure.i WebRandomReady()
  If webRandomBound=0 : ProcedureReturn -109 : EndIf
  ProcedureReturn webRandomReadyFn()
EndProcedure
Procedure.i WebRandomBytes(dst.i,n.i)
  If webRandomBound=0 : ProcedureReturn -109 : EndIf
  ProcedureReturn webRandomBytesFn(dst,n)
EndProcedure

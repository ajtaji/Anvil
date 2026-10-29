; SPDX-License-Identifier: MIT
; Shared finite/range validation for the serialized graphics service.
XIncludeFile "Anvil/Graphics/neon_byte_ranges.pbi"
Procedure.i NeonServiceFloatsValid(request.i,count.i)
  Protected i.i,bits.i
  If count<0 Or count>64 : ProcedureReturn 0 : EndIf
  If count=0 : ProcedureReturn 1 : EndIf
  If (request & 3)<>0 Or NeonByteSpan(request,count*4)=0 : ProcedureReturn 0 : EndIf
  For i=0 To count-1
    bits=PeekL(request+i*4)
    If (bits & $7FFFFFFF)>$49742400 : ProcedureReturn 0 : EndIf
  Next
  ProcedureReturn 1
EndProcedure

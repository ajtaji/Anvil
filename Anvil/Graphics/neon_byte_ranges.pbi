; SPDX-License-Identifier: MIT
; Positive, representable byte spans and overlap after span validation.
Procedure.i NeonByteSpan(pointer.i,bytes.i)
  ProcedureReturn Bool(pointer>0 And bytes>0 And pointer+bytes>pointer)
EndProcedure
Procedure.i NeonByteOverlap(a.i,aBytes.i,b.i,bBytes.i)
  ProcedureReturn Bool(a<b+bBytes And b<a+aBytes)
EndProcedure

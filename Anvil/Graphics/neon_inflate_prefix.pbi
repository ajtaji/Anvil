; SPDX-License-Identifier: MIT
; A verified zlib prefix with optional trailing container bytes. The strict
; decoder remains the acceptance authority. On its end-offset format refusal,
; retry once at that candidate boundary and require a complete checksum pass.
XIncludeFile "Anvil/Graphics/neon_inflate.pbi"
Procedure.i NeonInflateZlibPrefix(*state.NeonInflateState,work.i,workBytes.i,source.i,bytes.i,target.i,capacity.i)
  Protected rc.i,complete.i
  rc=NeonInflateZlib(*state,work,workBytes,source,bytes,target,capacity)
  If rc=#NEON_INFLATE_ERR_FORMAT
    complete=*state\offset+6
    If complete>=8 And complete<bytes
      rc=NeonInflateZlib(*state,work,workBytes,source,complete,target,capacity)
    EndIf
  EndIf
  ProcedureReturn rc
EndProcedure

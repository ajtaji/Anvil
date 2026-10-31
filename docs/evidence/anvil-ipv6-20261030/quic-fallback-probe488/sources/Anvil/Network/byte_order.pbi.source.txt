; SPDX-License-Identifier: MIT
; Network-order integers through byte loads/stores, including unaligned fields.
; The caller supplies two or four valid bytes. No packet, driver or global state.
Procedure.i NetReadBE16(*p)
  ProcedureReturn ((PeekA(*p) << 8) | PeekA(*p + 1)) & $FFFF
EndProcedure

Procedure.i NetReadBE32(*p)
  Protected v.i
  v = PeekA(*p)
  v = (v << 8) | PeekA(*p + 1)
  v = (v << 8) | PeekA(*p + 2)
  v = (v << 8) | PeekA(*p + 3)
  ProcedureReturn v & $FFFFFFFF
EndProcedure

Procedure NetWriteBE16(*p, v.i)
  PokeB(*p + 0, (v >> 8) & $FF)
  PokeB(*p + 1, v & $FF)
EndProcedure

Procedure NetWriteBE32(*p, v.i)
  PokeB(*p + 0, (v >> 24) & $FF)
  PokeB(*p + 1, (v >> 16) & $FF)
  PokeB(*p + 2, (v >> 8) & $FF)
  PokeB(*p + 3, v & $FF)
EndProcedure

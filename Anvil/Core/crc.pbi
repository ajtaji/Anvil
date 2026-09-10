
; ======================================================================
;  CRC32 - IEEE 802.3, reflected, $EDB88320
;
;  The accumulator starts at $FFFFFFFF and is shifted RIGHT with zero
;  fill. Held in a 64-bit .i that bit pattern is a positive 4294967295
;  with bits 63:32 clear, and an arithmetic shift right of a positive
;  value is a logical one. The masking that keeps it inside 32 bits is
;  done by the polynomial xor itself - the value never leaves
;  [0, $FFFFFFFF].
;
;  Bitwise, no table. 120k iterations for a 15 KB image is under a
;  millisecond, and it runs after the transfer, where nothing is waiting
;  on it. A 256-entry table would have to be built at startup or emitted
;  as data, which is one more thing to get wrong for a saving nobody can
;  measure.
; ======================================================================

; ----------------------------------------------------------------------
;  Crc32Part - the running accumulator, NOT finalised.
;
;  SPLIT OUT OF Crc32 on 2026-08-26 so the new `crc32` command can cover
;  a whole boot image - megabytes, not the 15 KB the b command sees -
;  and still check OutBreak() between chunks. The alternative was a
;  second copy of the polynomial loop inside that command, and two
;  copies of a CRC are two chances to disagree with tools/anvil.py.
;
;  The caller starts it at $FFFFFFFF, feeds it any number of adjoining
;  ranges, and finishes with "! $FFFFFFFF". Crc32() below is exactly
;  that for one range, so nothing that already called it has changed.
; ----------------------------------------------------------------------
Procedure.i Crc32Part(crc.i, addr.i, len.i)
  Define i.i
  Define k.i
  Define b.i
  i = 0
  While i < len
    b = PeekA(addr + i)
    crc = crc ! b
    For k = 0 To 7
      ; (crc >> 1) - the parentheses are load bearing. "!" binds TIGHTER
      ; than ">>" here, so "crc >> 1 ! #CRC_POLY" would mean
      ; "crc >> (1 ! #CRC_POLY)" and would assemble cleanly while
      ; computing nonsense.
      If (crc & 1) <> 0
        crc = (crc >> 1) ! #CRC_POLY
      Else
        crc = crc >> 1
      EndIf
    Next
    i = i + 1
  Wend
  ProcedureReturn crc
EndProcedure

Procedure.i Crc32(addr.i, len.i)
  ProcedureReturn Crc32Part($FFFFFFFF, addr, len) ! $FFFFFFFF
EndProcedure


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
;  A BYTE AT A TIME FROM A 256-ENTRY TABLE, since 2026-09-16. This header
;  used to say "bitwise, no table", because a table was "one more thing to
;  get wrong for a saving nobody can measure". The saving was measured on
;  that date, under tools/a64 with the monitor's own compiler: the bitwise
;  loop cost 252 instructions a byte, which was 59% of everything a bulk
;  `readback` does per byte and put a megabyte-sized checksum in seconds
;  on a board whose caches are off - which is how this monitor boots. The
;  `crc32` command and `version full`'s image checksum paid the same.
;
;  THE TABLE IS DERIVED, NOT WRITTEN. crc_Build computes every entry with
;  the bitwise loop that used to be the whole of this file, from #CRC_POLY,
;  on the first call. The polynomial is still stated in one place, and
;  there are no 256 typed constants that could hold one wrong digit. The
;  answer is the same function of the same bytes, and
;  tools/a64/a64_wificon_check.py grades it against Python's zlib.crc32
;  on every byte value and on chained ranges (case L7).
; ======================================================================

Global Dim crc_Tab.i[256]
Global crc_TabReady.i = 0

; ----------------------------------------------------------------------
;  crc_Build - the table, by the bitwise definition.
;
;  Entry n is the accumulator after feeding the single byte n into an
;  accumulator of zero: eight shifts, with the polynomial folded in on
;  every one-bit that falls off the bottom.
; ----------------------------------------------------------------------
Procedure crc_Build()
  Define n.i
  Define k.i
  Define c.i
  For n = 0 To 255
    c = n
    For k = 0 To 7
      ; (c >> 1) - the parentheses are load bearing. "!" binds TIGHTER
      ; than ">>" here, so "c >> 1 ! #CRC_POLY" would mean
      ; "c >> (1 ! #CRC_POLY)" and would assemble cleanly while
      ; computing nonsense.
      If (c & 1) <> 0
        c = (c >> 1) ! #CRC_POLY
      Else
        c = c >> 1
      EndIf
    Next
    crc_Tab[n] = c
  Next
  crc_TabReady = 1
EndProcedure

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
  If crc_TabReady = 0
    crc_Build()
  EndIf
  i = 0
  While i < len
    crc = (crc >> 8) ! crc_Tab[(crc ! PeekA(addr + i)) & $FF]
    i = i + 1
  Wend
  ProcedureReturn crc
EndProcedure

Procedure.i Crc32(addr.i, len.i)
  ProcedureReturn Crc32Part($FFFFFFFF, addr, len) ! $FFFFFFFF
EndProcedure

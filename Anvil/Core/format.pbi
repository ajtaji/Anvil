; ======================================================================
;  Hex output.
;
;  THE ONE FORMATTER THIS FILE STILL OWNS. See WHAT IS STILL
;  HAND-WRITTEN in the header: string.pi4's Hex() formats a SIXTEEN-bit
;  .w into a buffer and DisplayPrintHex() writes to glass. Neither is
;  this. Decimal comes from uart.pi4's PrintDec().
; ======================================================================

Procedure PutHexN(v.i, digits.i)
  Define k.i
  Define n.i
  k = (digits - 1) * 4
  While k >= 0
    ; MASK AFTER THE SHIFT. >> is arithmetic on a signed .i, but the
    ; sign only ever fills bits ABOVE the nibble being printed, so & 15
    ; makes it irrelevant. This is why $FE201000 prints as FE201000 and
    ; why a genuinely negative value prints as its 16-digit two's
    ; complement rather than as a minus sign.
    n = (v >> k) & 15
    If n < 10
      UartWrite(48 + n)
    Else
      UartWrite(55 + n)
    EndIf
    k = k - 4
  Wend
EndProcedure

; ONE BYTE IN LOWERCASE HEX, for a cryptographic digest.
;
; PutHex2 below is UPPERCASE and stays that way: it is for addresses and
; register words, which this monitor has always printed in upper case and
; which host tools grep for. A digest is a different kind of number - it
; exists to be compared against what sha256sum printed on somebody's PC,
; and every one of those tools prints lower case. A checksum you have to
; case-fold before comparing is a checksum with a trap in it.
;
; Two printers rather than one flag, because the choice is a property of
; WHAT is being printed and never of the moment, so a caller that had to
; pass the case could pass the wrong one.
;
; IT LIVED IN Anvil/Core/hash_cmd.pbi until the bootloader pass, when
; Anvil/Core/pmfboot.pbi needed to print a digest while verifying a
; payload container. A board can build the bootloader without building
; the sha1sum/sha256sum commands, and on that board the procedure simply
; would not have existed.
Procedure PutHexLower2(b.i)
  Define hi.i
  Define lo.i
  hi = (b >> 4) & 15
  lo = b & 15
  If hi < 10
    UartWrite(48 + hi)
  Else
    UartWrite(87 + hi)             ; 87 + 10 = 97 = 'a'
  EndIf
  If lo < 10
    UartWrite(48 + lo)
  Else
    UartWrite(87 + lo)
  EndIf
EndProcedure

Procedure PutHex2(v.i)
  PutHexN(v, 2)
EndProcedure

Procedure PutHex8(v.i)
  PutHexN(v, 8)
EndProcedure

Procedure PutHex16(v.i)
  PutHexN(v, 16)
EndProcedure

Procedure PutAddr(a.i)
  ; ADDRESSES MUST NOT TRUNCATE, and sixteen digits everywhere would
  ; make every line of a dump of low memory eight characters of leading
  ; zero. So: eight digits while the value genuinely fits in 32 bits,
  ; sixteen when it does not. The negative case cannot arise from
  ; hardware - BCM2711 physical addresses are 40 bits - but it can
  ; arise from a typed number with the top bit set, and printing that as
  ; eight digits would be exactly the truncation this exists to avoid.
  If a < 0 Or a > $FFFFFFFF
    PutHex16(a)
  Else
    PutHex8(a)
  EndIf
EndProcedure

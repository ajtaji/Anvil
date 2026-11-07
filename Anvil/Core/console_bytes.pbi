; Portable console byte formatting. UartWrite is the selected transport seam.
; Keep one UTF-8 byte walk and CR/LF convention across every console.
Procedure UartWriteStr(*s)
  Define i.i
  Define c.i
  i = 0
  Repeat
    c = PeekB(*s + i) & $FF
    If c = 0
      Break
    EndIf
    UartWrite(c)
    i = i + 1
  ForEver
EndProcedure

Procedure UartWriteNl()
  UartWrite(13)
  UartWrite(10)
EndProcedure

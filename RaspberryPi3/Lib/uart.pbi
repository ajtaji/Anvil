; BCM2837 PL011 UART0, GPIO14 TX/GPIO15 RX ALT0. Include timer.pbi first.
; Firmware must route PL011 away from Bluetooth (disable-bt overlay), and
; caller supplies verified UART clock Hz, e.g. firmware Get clock rate ID2.
; 3.3V TTL only, not RS232. No pin ownership is silently taken elsewhere.
#PI3_UART = $3F201000
#PI3_GPIO = $3F200000
Global pi3_uart_ready.i
Procedure.i Pi3UartWaitClear(mask.i)
  Protected start.i
  Protected now.i
  Protected n.i
  start = Pi3Micros()
  If start < 0
    ProcedureReturn 0
  EndIf
  For n = 0 To 999999
    If (PeekL(#PI3_UART + $18) & mask) = 0
      ProcedureReturn 1
    EndIf
    now = Pi3Micros()
    If now < start Or now - start >= 100000
      ProcedureReturn 0
    EndIf
  Next
  ProcedureReturn 0
EndProcedure
Procedure.i Pi3UartInit(clockHz.i, baud.i)
  Protected divider.i
  Protected pins.i
  pi3_uart_ready = 0
  If clockHz < 1000000 Or clockHz > 100000000 Or baud < 1200 Or baud > 3000000
    ProcedureReturn 0
  EndIf
  divider = (clockHz * 4 + baud / 2) / baud
  If divider < 64 Or divider > 4194303
    ProcedureReturn 0
  EndIf
  If Pi3UartWaitClear(8) = 0
    ProcedureReturn 0
  EndIf
  PokeL(#PI3_UART + $30, 0)
  PokeL(#PI3_UART + $38, 0)
  pins = PeekL(#PI3_GPIO + 4) & $FFFFFFFF
  pins = (pins & $FFFC0FFF) | $24000
  PokeL(#PI3_GPIO + 4, pins)
  ; BCM2837 uses old GPPUD/GPPUDCLK, not Pi4 GPPUPPDN registers.
  PokeL(#PI3_GPIO + $94, 0)
  If Pi3DelayUs(1) = 0
    ProcedureReturn 0
  EndIf
  PokeL(#PI3_GPIO + $98, $C000)
  If Pi3DelayUs(1) = 0
    PokeL(#PI3_GPIO + $98, 0)
    ProcedureReturn 0
  EndIf
  PokeL(#PI3_GPIO + $98, 0)
  PokeL(#PI3_UART + $44, $7FF)
  PokeL(#PI3_UART + $24, divider >> 6)
  PokeL(#PI3_UART + $28, divider & 63)
  PokeL(#PI3_UART + $2C, $70)
  PokeL(#PI3_UART + $30, $301)
  pi3_uart_ready = 1
  ProcedureReturn 1
EndProcedure
Procedure.i Pi3UartWrite(value.i)
  If pi3_uart_ready = 0 Or value < 0 Or value > 255
    ProcedureReturn 0
  EndIf
  If Pi3UartWaitClear($20) = 0
    ProcedureReturn 0
  EndIf
  PokeL(#PI3_UART, value)
  ProcedureReturn 1
EndProcedure
Procedure.i Pi3UartRead()
  Protected value.i
  If pi3_uart_ready = 0
    ProcedureReturn -2
  EndIf
  If (PeekL(#PI3_UART + $18) & $10) <> 0
    ProcedureReturn -1
  EndIf
  value = PeekL(#PI3_UART)
  If (value & $F00) <> 0
    PokeL(#PI3_UART + 4, 0)
    ProcedureReturn -2
  EndIf
  ProcedureReturn value & 255
EndProcedure

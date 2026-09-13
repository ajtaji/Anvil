; Adopt the UART2 configuration made by the exact U-Boot handoff. The board
; DT says serial2:1500000n8 and the RK3399 node says 32-bit I/O, shift 2.
; This layer does not touch CRU, GRF, reset or divisor registers: doing so
; before those ownership contracts exist would be a destructive guess.
Global rock_uart_ready.i
Global rock_uart_error.i

Procedure.i RockUartAdopt()
  Protected status.i
  rock_uart_ready = 0
  status = PeekN(#ROCK_UART2 + #ROCK_UART_USR) & $FFFFFFFF
  If status = $FFFFFFFF
    rock_uart_error = 1
    ProcedureReturn 0
  EndIf
  rock_uart_ready = 1
  rock_uart_error = 0
  ProcedureReturn 1
EndProcedure

Procedure.i RockUartByte(value.i)
  Protected start.i
  Protected now.i
  Protected attempt.i
  If rock_uart_ready = 0 Or value < 0 Or value > 255
    ProcedureReturn 0
  EndIf
  start = RockTimerTicks()
  For attempt = 0 To 999999
    If (PeekN(#ROCK_UART2 + #ROCK_UART_LSR) & #ROCK_UART_LSR_THRE) <> 0
      PokeL(#ROCK_UART2 + #ROCK_UART_THR, value)
      ProcedureReturn 1
    EndIf
    now = RockTimerTicks()
    If now < start Or now - start >= rock_timer_frequency / 10
      rock_uart_error = 2
      ProcedureReturn 0
    EndIf
  Next
  rock_uart_error = 2
  ProcedureReturn 0
EndProcedure

Procedure.i RockUartText(text.i)
  Protected index.i
  Protected value.i
  For index = 0 To 511
    value = PeekA(text + index)
    If value = 0 : ProcedureReturn 1 : EndIf
    If RockUartByte(value) = 0 : ProcedureReturn 0 : EndIf
  Next
  rock_uart_error = 3
  ProcedureReturn 0
EndProcedure

Procedure.i RockUartLine(text.i)
  If RockUartText(text) = 0 : ProcedureReturn 0 : EndIf
  If RockUartByte(13) = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn RockUartByte(10)
EndProcedure

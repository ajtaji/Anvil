; Adopt the UART2 configuration prepared by the direct-SD loader. The board
; DT says serial2:1500000n8 and the RK3399 node says 32-bit I/O, shift 2.
; This layer does not touch CRU, GRF, reset or divisor registers: doing so
; before those ownership contracts exist would be a destructive guess.
Global rock_uart_ready.i
Global rock_uart_error.i
Global *rock_uart_mirror_hook
#ROCK_UART_RX_RING_MASK = 1023
Global Dim rock_uart_rx_ring.a[1024]
Global rock_uart_rx_head.i
Global rock_uart_rx_tail.i
Global rock_uart_rx_error_pending.i
Global rock_uart_rx_last_pump_end.i
Global rock_uart_rx_max_outside_ticks.i
Global rock_uart_rx_context.i
Global rock_uart_rx_max_context.i

#ROCK_UART_LSR_DR = $01
#ROCK_UART_LSR_RX_ERRORS = $1E
#ROCK_UART_LSR_TEMT = $40

; Optional board-owned text-console tap.  The UART driver remains usable by
; diagnostics that do not link a display, while the full monitor can install
; the screen ring producer after HDMI has published a complete first frame.
; Returning the previous hook lets binary transports suppress mirroring for
; their exact wire payload and restore it on every exit path.
Procedure.i RockUartSetMirrorHook(*hook)
  Protected *old
  *old = *rock_uart_mirror_hook
  *rock_uart_mirror_hook = *hook
  ProcedureReturn *old
EndProcedure

Procedure.i RockUartAdopt()
  Protected status.i
  rock_uart_ready = 0
  rock_uart_rx_head = 0
  rock_uart_rx_tail = 0
  rock_uart_rx_error_pending = 0
  rock_uart_rx_last_pump_end = 0
  rock_uart_rx_max_outside_ticks = 0
  rock_uart_rx_context = 0
  rock_uart_rx_max_context = 0
  status = PeekL(#ROCK_UART2 + #ROCK_UART_USR) & $FFFFFFFF
  If status = $FFFFFFFF
    rock_uart_error = 1
    ProcedureReturn 0
  EndIf
  rock_uart_ready = 1
  rock_uart_error = 0
  ProcedureReturn 1
EndProcedure

; Move at most one hardware-FIFO worth of bytes into software storage before
; running the slower command parser. Both byte and burst consumers pop this
; ring first, so prefetched command framing stays visible to file transfers.
Procedure.i RockUartPumpRaw(limit.i)
  Protected status.i
  Protected nextHead.i
  Protected count.i
  If rock_uart_ready = 0 Or limit <= 0 : ProcedureReturn 0 : EndIf
  If rock_uart_rx_error_pending <> 0 : ProcedureReturn -2 : EndIf
  While count < limit
    status = PeekL(#ROCK_UART2 + #ROCK_UART_LSR) & $FFFFFFFF
    If status = $FFFFFFFF
      rock_uart_error = 4
      rock_uart_rx_error_pending = 1
      ProcedureReturn -2
    EndIf
    If (status & #ROCK_UART_LSR_RX_ERRORS) <> 0
      If (status & #ROCK_UART_LSR_DR) <> 0
        status = PeekL(#ROCK_UART2 + #ROCK_UART_THR) & $FFFFFFFF
      EndIf
      rock_uart_error = 5
      rock_uart_rx_error_pending = 1
      ProcedureReturn -2
    EndIf
    If (status & #ROCK_UART_LSR_DR) = 0 : Break : EndIf
    nextHead = (rock_uart_rx_head + 1) & #ROCK_UART_RX_RING_MASK
    If nextHead = rock_uart_rx_tail
      rock_uart_error = 7
      rock_uart_rx_error_pending = 1
      ProcedureReturn -2
    EndIf
    rock_uart_rx_ring[rock_uart_rx_head] = PeekL(#ROCK_UART2 + #ROCK_UART_THR) & 255
    rock_uart_rx_head = nextHead
    count = count + 1
  Wend
  ProcedureReturn count
EndProcedure

Procedure.i RockUartPump(limit.i)
  Protected start.i
  Protected gap.i
  Protected result.i
  start = RockTimerTicks()
  If rock_uart_rx_last_pump_end <> 0 And start >= rock_uart_rx_last_pump_end
    gap = start - rock_uart_rx_last_pump_end
    If gap > rock_uart_rx_max_outside_ticks
      rock_uart_rx_max_outside_ticks = gap
      rock_uart_rx_max_context = rock_uart_rx_context
    EndIf
  EndIf
  result = RockUartPumpRaw(limit)
  rock_uart_rx_last_pump_end = RockTimerTicks()
  ProcedureReturn result
EndProcedure

; CRLF is one terminator. Before a synchronous binary receiver starts, consume
; its LF from the shared ring or FIFO; a bare CR gets a 100 us bounded wait.
Procedure.i RockUartDropOptionalLf()
  Protected start.i
  Protected now.i
  start = RockTimerTicks()
  Repeat
    If rock_uart_rx_tail <> rock_uart_rx_head
      If (rock_uart_rx_ring[rock_uart_rx_tail] & 255) = 10
        rock_uart_rx_tail = (rock_uart_rx_tail + 1) & #ROCK_UART_RX_RING_MASK
        ProcedureReturn 1
      EndIf
      ProcedureReturn 0
    EndIf
    If rock_uart_rx_error_pending <> 0 : ProcedureReturn 0 : EndIf
    RockUartPump(2)
    now = RockTimerTicks()
    If now < start Or now - start >= rock_timer_frequency / 10000
      ProcedureReturn 0
    EndIf
  ForEver
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
    If ((PeekL(#ROCK_UART2 + #ROCK_UART_LSR) & $FFFFFFFF) & #ROCK_UART_LSR_THRE) <> 0
      PokeL(#ROCK_UART2 + #ROCK_UART_THR, value)
      If *rock_uart_mirror_hook <> 0
        ; A pointer variable is declared with '*', but called without it.
        ; The starred call spelling dereferences the callback's return value;
        ; for this void hook it emitted a stray low-address LDR after BLR.
        rock_uart_mirror_hook(value)
      EndIf
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

Procedure.i RockUartReceive()
  Protected status.i
  If rock_uart_ready=0 : ProcedureReturn -1 : EndIf
  If rock_uart_rx_tail <> rock_uart_rx_head
    status = rock_uart_rx_ring[rock_uart_rx_tail] & 255
    rock_uart_rx_tail = (rock_uart_rx_tail + 1) & #ROCK_UART_RX_RING_MASK
    ProcedureReturn status
  EndIf
  If rock_uart_rx_error_pending <> 0
    rock_uart_rx_error_pending = 0
    ProcedureReturn -2
  EndIf
  ; RK3399's UART node requires 32-bit accesses. A receive error contaminates
  ; the command line even when RBR still contains a byte, so consume that byte
  ; and return a distinct error instead of exposing it to the parser.
  status=PeekL(#ROCK_UART2+#ROCK_UART_LSR) & $FFFFFFFF
  If status=$FFFFFFFF
    rock_uart_error=4
    ProcedureReturn -2
  EndIf
  If (status & #ROCK_UART_LSR_RX_ERRORS)<>0
    If (status & #ROCK_UART_LSR_DR)<>0
      status=PeekL(#ROCK_UART2+#ROCK_UART_THR) & $FFFFFFFF
    EndIf
    rock_uart_error=5
    ProcedureReturn -2
  EndIf
  If (status & #ROCK_UART_LSR_DR)=0 : ProcedureReturn -1 : EndIf
  ProcedureReturn PeekL(#ROCK_UART2+#ROCK_UART_THR) & 255
EndProcedure

; Drain as much of the hardware RX FIFO as is present into one caller-owned
; memory range. File transfer uses this tight loop so the timer and procedure
; overhead are paid once per FIFO drain, not once per byte. The UART remains
; the flow-control boundary: 0 means empty now, -2 means a hardware/error
; read, and a positive result is the exact number of bytes stored.
Procedure.i RockUartReceiveBurst(*dst, capacity.i)
  Protected status.i
  Protected count.i
  If rock_uart_ready = 0 Or *dst = 0 Or capacity <= 0 : ProcedureReturn 0 : EndIf
  count = 0
  While count < capacity And rock_uart_rx_tail <> rock_uart_rx_head
    PokeA(*dst + count, rock_uart_rx_ring[rock_uart_rx_tail] & 255)
    rock_uart_rx_tail = (rock_uart_rx_tail + 1) & #ROCK_UART_RX_RING_MASK
    count = count + 1
  Wend
  If count = capacity : ProcedureReturn count : EndIf
  If rock_uart_rx_error_pending <> 0
    rock_uart_rx_error_pending = 0
    ProcedureReturn -2
  EndIf
  While count < capacity
    status = PeekL(#ROCK_UART2 + #ROCK_UART_LSR) & $FFFFFFFF
    If status = $FFFFFFFF
      rock_uart_error = 4
      ProcedureReturn -2
    EndIf
    If (status & #ROCK_UART_LSR_RX_ERRORS) <> 0
      If (status & #ROCK_UART_LSR_DR) <> 0
        status = PeekL(#ROCK_UART2 + #ROCK_UART_THR) & $FFFFFFFF
      EndIf
      rock_uart_error = 5
      ProcedureReturn -2
    EndIf
    If (status & #ROCK_UART_LSR_DR) = 0 : Break : EndIf
    PokeA(*dst + count, PeekL(#ROCK_UART2 + #ROCK_UART_THR) & 255)
    count = count + 1
  Wend
  ProcedureReturn count
EndProcedure

Procedure.i RockUartDrain()
  Protected start.i
  Protected now.i
  Protected status.i
  Protected attempt.i
  If rock_uart_ready=0 Or rock_timer_frequency=0 : ProcedureReturn 0 : EndIf
  start=RockTimerTicks()
  For attempt=0 To 999999
    status=PeekL(#ROCK_UART2+#ROCK_UART_LSR) & $FFFFFFFF
    If status=$FFFFFFFF
      rock_uart_error=4
      ProcedureReturn 0
    EndIf
    ; THRE says only that the holding register is empty. TEMT additionally
    ; proves that the shift register has put the final stop bit on the wire.
    If (status & #ROCK_UART_LSR_TEMT)<>0 : ProcedureReturn 1 : EndIf
    now=RockTimerTicks()
    If now<start Or now-start>=rock_timer_frequency/10
      rock_uart_error=6
      ProcedureReturn 0
    EndIf
  Next
  rock_uart_error=6
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

; Shared HAL capability refusals print untyped names/reasons through this seam.
Procedure.i UartWriteStr(text.i)
  ProcedureReturn RockUartText(text)
EndProcedure

Procedure UartWriteNl()
  RockUartByte(13)
  RockUartByte(10)
EndProcedure

Procedure.i RockUartLine(text.i)
  If RockUartText(text) = 0 : ProcedureReturn 0 : EndIf
  If RockUartByte(13) = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn RockUartByte(10)
EndProcedure

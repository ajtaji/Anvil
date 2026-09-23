; Shared Rock Pi 4C display state and serial diagnostics.
; Kept separate from the deferred MiniDP facade so the HDMI/storage recovery
; image does not carry the CDN-DP and TC-PHY implementation.

Global rock_display_ready.i
Global rock_display_width.i
Global rock_display_height.i
Global rock_display_pitch.i
Global rock_display_buffer.i
Global rock_display_error.i

Procedure RockDisplayStage(text.i)
  If rock_uart_ready <> 0 : RockUartLine(text) : EndIf
EndProcedure

Procedure.i RockDisplayFail(code.i, text.i)
  rock_display_error=code
  RockDisplayStage(text)
  ProcedureReturn 0
EndProcedure

Procedure RockDisplayDecimal(value.i)
  Protected divisor.i = 1
  While value / divisor >= 10
    divisor = divisor * 10
  Wend
  Repeat
    RockUartByte(48 + value / divisor)
    value = value % divisor
    divisor = divisor / 10
  Until divisor = 0
EndProcedure

Procedure RockDisplayModeTelemetry(text.i)
  If rock_uart_ready = 0 : ProcedureReturn 0 : EndIf
  RockUartText(text)
  RockDisplayDecimal(rock_mode_width)
  RockUartByte(88)
  RockDisplayDecimal(rock_mode_height)
  RockUartText(" PIXEL HZ ")
  RockDisplayDecimal(rock_mode_pixel_hz)
  RockUartText(" SOURCE ")
  RockDisplayDecimal(rock_mode_source)
  RockUartText(" REASON ")
  RockDisplayDecimal(rock_mode_reason)
  If rock_mode_source = #ROCK_MODE_SOURCE_PREFERRED_DTD
    RockUartText(" EDID PREFERRED")
  Else
    RockUartText(" ADVERTISED FALLBACK; PREFERRED ")
    RockDisplayDecimal(rock_mode_preferred_width)
    RockUartByte(88)
    RockDisplayDecimal(rock_mode_preferred_height)
    RockUartText(" AT HZ ")
    RockDisplayDecimal(rock_mode_preferred_pixel_hz)
  EndIf
  RockUartByte(13)
  RockUartByte(10)
EndProcedure

Procedure RockDisplayHexByte(value.i)
  Protected digit.i = (value >> 4) & 15
  If digit < 10
    RockUartByte(48+digit)
  Else
    RockUartByte(55+digit)
  EndIf
  digit = value & 15
  If digit < 10
    RockUartByte(48+digit)
  Else
    RockUartByte(55+digit)
  EndIf
EndProcedure

Procedure RockDisplayHexWord(value.i)
  RockDisplayHexByte((value >> 8) & 255)
  RockDisplayHexByte(value & 255)
EndProcedure

Procedure RockDisplayHexLong(value.i)
  RockDisplayHexWord((value >> 16) & $FFFF)
  RockDisplayHexWord(value & $FFFF)
EndProcedure

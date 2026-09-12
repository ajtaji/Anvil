; Raspberry Pi 3 PL011 transport for the safe A/B updater.
;
; Include after uart.pbi, crc.pbi and update.pbi.  This file owns only the
; wire protocol and the small command loop.  Card selection, slot ownership,
; hashing and commit ordering remain in update.pbi; moving any of those rules
; here would create a second updater with different failure behavior.
;
; ASCII control:
;   update begin <decimal length> <64 lowercase/uppercase SHA-256 hex>
;   update status
;   update commit
;   update abort
;
; After a successful begin the board prints exactly `rdy 0`, then accepts:
;   "P3D1" | offset u32le | length u16le | payload CRC32 u32le | payload
; and answers every frame with:
;   "P3A1" | next offset u32le | status u32le
; A frame is at most 1024 bytes.  update.pbi decides whether a retransmitted
; earlier frame is the identical lost-ACK retry; the transport never guesses.
; After all data is acknowledged, a header with offset=total, length=0 and
; CRC=0 ends binary mode; its acknowledgement is the `staged <total>` line.

#PI3_UT_LINE_BYTES = 160
#PI3_UT_FRAME_BYTES = 1024
#PI3_UT_HEADER_BYTES = 14
#PI3_UT_FRAME_TIMEOUT_US = 30000000

#PI3_UT_STATUS_OK = 0
#PI3_UT_STATUS_HEADER = 1001
#PI3_UT_STATUS_LENGTH = 1002
#PI3_UT_STATUS_CRC = 1003
#PI3_UT_STATUS_UART = 1004

Global Dim pi3_ut_line.a[#PI3_UT_LINE_BYTES]
Global Dim pi3_ut_header.a[#PI3_UT_HEADER_BYTES]
Global Dim pi3_ut_payload.a[#PI3_UT_FRAME_BYTES]
Global Dim pi3_ut_digest.a[32]
Global pi3_ut_line_len.i
Global pi3_ut_parse.i
Global pi3_ut_line_overflow.i
Global pi3_ut_rx_quarantine.i

Procedure.i pi3ut_WriteByte(value.i)
  ProcedureReturn Pi3UartWrite(value & $FF)
EndProcedure

Procedure.i pi3ut_WriteText(text.i)
  Protected i.i
  Protected value.i
  If text = 0 : ProcedureReturn 0 : EndIf
  For i = 0 To 511
    value = PeekA(text + i)
    If value = 0 : ProcedureReturn 1 : EndIf
    If pi3ut_WriteByte(value) = 0 : ProcedureReturn 0 : EndIf
  Next
  ProcedureReturn 0
EndProcedure

Procedure.i pi3ut_WriteLine(text.i)
  If pi3ut_WriteText(text) = 0 : ProcedureReturn 0 : EndIf
  If pi3ut_WriteByte(13) = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn pi3ut_WriteByte(10)
EndProcedure

Procedure.i pi3ut_WriteDec(value.i)
  Protected Dim digits.a[24]
  Protected n.i
  Protected q.i
  If value < 0 : ProcedureReturn 0 : EndIf
  If value = 0 : ProcedureReturn pi3ut_WriteByte(48) : EndIf
  While value > 0 And n < 24
    q = value / 10
    digits[n] = 48 + value - q * 10
    value = q
    n = n + 1
  Wend
  While n > 0
    n = n - 1
    If pi3ut_WriteByte(digits[n]) = 0 : ProcedureReturn 0 : EndIf
  Wend
  ProcedureReturn 1
EndProcedure

Procedure.i pi3ut_WriteInt(value.i)
  If value < 0
    If pi3ut_WriteByte(45) = 0 : ProcedureReturn 0 : EndIf
    value = 0 - value
  EndIf
  ProcedureReturn pi3ut_WriteDec(value)
EndProcedure

Procedure pi3ut_Prompt()
  ; ANSI bright green on serial, then restore the terminal's normal colour.
  ; The framebuffer text stays in its own theme; escape bytes never reach it.
  pi3ut_WriteByte(27) : pi3ut_WriteText("[92mpmf> ")
  pi3ut_WriteByte(27) : pi3ut_WriteText("[0m")
EndProcedure

Procedure.i pi3ut_ReadLine()
  Protected value.i
  pi3_ut_line_len = 0
  pi3_ut_line_overflow = 0
  Repeat
    value = Pi3UartRead()
    If value = -2 : ProcedureReturn 0 : EndIf
    If value = -1
      Pi3DelayUs(1000)
    ElseIf value = 13 Or (value = 10 And pi3_ut_line_len > 0)
      pi3_ut_line[pi3_ut_line_len] = 0
      pi3ut_WriteByte(13) : pi3ut_WriteByte(10)
      ProcedureReturn 1
    ElseIf value = 8 Or value = 127
      If pi3_ut_line_len > 0
        pi3_ut_line_len = pi3_ut_line_len - 1
        pi3ut_WriteByte(8) : pi3ut_WriteByte(32) : pi3ut_WriteByte(8)
      EndIf
    ElseIf value >= 32 And value <= 126
      If pi3_ut_line_len < #PI3_UT_LINE_BYTES - 1
        pi3_ut_line[pi3_ut_line_len] = value
        pi3_ut_line_len = pi3_ut_line_len + 1
        pi3ut_WriteByte(value)
      Else
        ; Keep consuming through the terminator, but never parse the prefix of
        ; an overlong command as though the missing tail had not existed.
        pi3_ut_line_overflow = 1
      EndIf
    EndIf
  ForEver
EndProcedure

Procedure pi3ut_SkipSpaces()
  While pi3_ut_parse < pi3_ut_line_len And pi3_ut_line[pi3_ut_parse] = 32
    pi3_ut_parse = pi3_ut_parse + 1
  Wend
EndProcedure

Procedure.i pi3ut_End()
  pi3ut_SkipSpaces()
  ProcedureReturn Bool(pi3_ut_parse = pi3_ut_line_len)
EndProcedure

Procedure.i pi3ut_Match(word.i)
  Protected pos.i
  Protected value.i
  Protected found.i
  pi3ut_SkipSpaces()
  pos = pi3_ut_parse
  Repeat
    value = PeekA(word + found)
    If value = 0 : Break : EndIf
    If pos >= pi3_ut_line_len Or pi3_ut_line[pos] <> value
      ProcedureReturn 0
    EndIf
    pos = pos + 1
    found = found + 1
  ForEver
  If pos < pi3_ut_line_len And pi3_ut_line[pos] <> 32
    ProcedureReturn 0
  EndIf
  pi3_ut_parse = pos
  ProcedureReturn 1
EndProcedure

Procedure.i pi3ut_ParseDec()
  Protected value.i
  Protected digit.i
  Protected found.i
  pi3ut_SkipSpaces()
  While pi3_ut_parse < pi3_ut_line_len
    digit = pi3_ut_line[pi3_ut_parse] - 48
    If digit < 0 Or digit > 9 : Break : EndIf
    If value > 429496729 Or (value = 429496729 And digit > 5)
      ProcedureReturn -1
    EndIf
    value = value * 10 + digit
    pi3_ut_parse = pi3_ut_parse + 1
    found = 1
  Wend
  If found = 0 : ProcedureReturn -1 : EndIf
  ProcedureReturn value
EndProcedure

Procedure.i pi3ut_HexNibble(value.i)
  If value >= 48 And value <= 57 : ProcedureReturn value - 48 : EndIf
  If value >= 65 And value <= 70 : ProcedureReturn value - 55 : EndIf
  If value >= 97 And value <= 102 : ProcedureReturn value - 87 : EndIf
  ProcedureReturn -1
EndProcedure

Procedure.i pi3ut_ParseDigest()
  Protected i.i
  Protected hi.i
  Protected lo.i
  pi3ut_SkipSpaces()
  If pi3_ut_line_len - pi3_ut_parse <> 64 : ProcedureReturn 0 : EndIf
  For i = 0 To 31
    hi = pi3ut_HexNibble(pi3_ut_line[pi3_ut_parse + i * 2])
    lo = pi3ut_HexNibble(pi3_ut_line[pi3_ut_parse + i * 2 + 1])
    If hi < 0 Or lo < 0 : ProcedureReturn 0 : EndIf
    pi3_ut_digest[i] = (hi << 4) | lo
  Next
  pi3_ut_parse = pi3_ut_line_len
  ProcedureReturn 1
EndProcedure

Procedure.i pi3ut_ReadExact(dst.i, bytes.i)
  Protected began.i
  Protected now.i
  Protected got.i
  Protected value.i
  Protected spin.i
  began = Pi3Micros()
  If began < 0 : ProcedureReturn 0 : EndIf
  While got < bytes And spin < 20000000
    spin = spin + 1
    value = Pi3UartRead()
    If value = -2 : ProcedureReturn 0 : EndIf
    If value >= 0
      PokeB(dst + got, value)
      got = got + 1
    Else
      now = Pi3Micros()
      If now < began Or now - began >= #PI3_UT_FRAME_TIMEOUT_US
        ProcedureReturn 0
      EndIf
    EndIf
  Wend
  ProcedureReturn Bool(got = bytes)
EndProcedure

Procedure pi3ut_DrainAfterFault()
  Protected quietAt.i
  Protected now.i
  Protected value.i
  Protected count.i
  Protected spin.i
  quietAt = Pi3Micros()
  If quietAt < 0
    pi3_ut_rx_quarantine = 1
    ProcedureReturn
  EndIf
  While count < 16384 And spin < 2000000
    spin = spin + 1
    value = Pi3UartRead()
    If value = -2
      pi3_ut_rx_quarantine = 1
      ProcedureReturn
    EndIf
    now = Pi3Micros()
    If now < quietAt
      pi3_ut_rx_quarantine = 1
      ProcedureReturn
    EndIf
    If value >= 0
      count = count + 1
      quietAt = now
    ElseIf now - quietAt >= 100000
      ProcedureReturn
    EndIf
  Wend
  ; No proved quiet interval: do not reinterpret residual binary as commands.
  pi3_ut_rx_quarantine = 1
EndProcedure

Procedure.i pi3ut_U16(p.i)
  ProcedureReturn PeekA(p) | (PeekA(p + 1) << 8)
EndProcedure

Procedure.i pi3ut_U32(p.i)
  ProcedureReturn PeekA(p) | (PeekA(p + 1) << 8) | (PeekA(p + 2) << 16) | (PeekA(p + 3) << 24)
EndProcedure

Procedure.i pi3ut_Ack(nextOffset.i, status.i)
  Protected i.i
  Protected Dim reply.a[12]
  reply[0] = 80 : reply[1] = 51 : reply[2] = 65 : reply[3] = 49 ; P3A1
  For i = 0 To 3
    reply[4 + i] = (nextOffset >> (i * 8)) & $FF
    reply[8 + i] = (status >> (i * 8)) & $FF
  Next
  For i = 0 To 11
    If pi3ut_WriteByte(reply[i]) = 0 : ProcedureReturn 0 : EndIf
  Next
  ProcedureReturn 1
EndProcedure

Procedure.i pi3ut_ReceiveFrames(total.i)
  Protected offset.i
  Protected bytes.i
  Protected want.i
  Protected made.i
  Protected status.i
  Repeat
    If pi3ut_ReadExact(@pi3_ut_header[0], #PI3_UT_HEADER_BYTES) = 0
      Pi3UpdateAbort()
      pi3ut_DrainAfterFault()
      ProcedureReturn 0
    EndIf
    offset = pi3ut_U32(@pi3_ut_header[4])
    bytes = pi3ut_U16(@pi3_ut_header[8])
    want = pi3ut_U32(@pi3_ut_header[10]) & $FFFFFFFF
    status = #PI3_UT_STATUS_OK
    If pi3_ut_header[0] <> 80 Or pi3_ut_header[1] <> 51 Or pi3_ut_header[2] <> 68 Or pi3_ut_header[3] <> 49
      status = #PI3_UT_STATUS_HEADER
    ElseIf bytes = 0
      ; FIN is a header with the exact completed offset and a zero CRC. It has
      ; no binary acknowledgement: the following `staged N` text is its proof.
      ; Keeping binary mode until FIN makes a lost final data ACK retryable.
      If offset = total And want = 0 And Pi3UpdateReceived() = total
        ProcedureReturn 1
      EndIf
      status = #PI3_UT_STATUS_LENGTH
    ElseIf bytes < 1 Or bytes > #PI3_UT_FRAME_BYTES Or offset > total Or bytes > total - offset
      status = #PI3_UT_STATUS_LENGTH
    ElseIf pi3ut_ReadExact(@pi3_ut_payload[0], bytes) = 0
      status = #PI3_UT_STATUS_UART
    Else
      made = Crc32(@pi3_ut_payload[0], bytes) & $FFFFFFFF
      If made <> want
        status = #PI3_UT_STATUS_CRC
      ElseIf Pi3UpdateChunk(offset, @pi3_ut_payload[0], bytes) = 0
        status = Pi3UpdateError()
        If status = 0 : status = #PI3_UT_STATUS_LENGTH : EndIf
      EndIf
    EndIf
    pi3ut_Ack(Pi3UpdateReceived(), status)
    If status <> #PI3_UT_STATUS_OK
      Pi3UpdateAbort()
      ; A header/length refusal can leave payload bytes already queued by the
      ; USB-to-serial adapter. Drain to a bounded quiet interval so those bytes
      ; cannot become commands at the returned prompt.
      pi3ut_DrainAfterFault()
      ProcedureReturn 0
    EndIf
  ForEver
EndProcedure

Procedure pi3ut_Status()
  pi3ut_WriteText("received ") : pi3ut_WriteDec(Pi3UpdateReceived())
  pi3ut_WriteText(" error ") : pi3ut_WriteInt(Pi3UpdateError())
  pi3ut_WriteText(" slot ")
  If Pi3UpdateSlot() = 0
    pi3ut_WriteText("A")
  ElseIf Pi3UpdateSlot() = 1
    pi3ut_WriteText("B")
  Else
    pi3ut_WriteText("none")
  EndIf
  pi3ut_WriteText(" generation ") : pi3ut_WriteDec(Pi3UpdateGeneration())
  pi3ut_WriteText(" pending ")
  If Pi3UpdatePendingSlot() = 0
    pi3ut_WriteText("A")
  ElseIf Pi3UpdatePendingSlot() = 1
    pi3ut_WriteText("B")
  Else
    pi3ut_WriteText("none")
  EndIf
  If Pi3UpdatePendingSlot() >= 0
    pi3ut_WriteText(" generation ") : pi3ut_WriteDec(Pi3UpdatePendingGeneration())
  EndIf
  pi3ut_WriteByte(13) : pi3ut_WriteByte(10)
EndProcedure

; Optional serialized command extension: Procedure.i Handler(), no parameters.
; Return 1 only for a completely parsed/handled command, otherwise 0. The
; transport restores the parser before standard dispatch. Register before Serve.
; The real default handler returns unhandled; the loader registers nothing.
Procedure.i Pi3NoCommandExtension()
  ProcedureReturn 0
EndProcedure
Global pi3_ut_command_extension.i=@Pi3NoCommandExtension
Global pi3_ut_extension_registered.i
Procedure.i Pi3UpdateRegisterCommand(handler.i)
  If handler=0 Or pi3_ut_extension_registered<>0 : ProcedureReturn 0 : EndIf
  pi3_ut_command_extension=handler
  pi3_ut_extension_registered=1
  ProcedureReturn 1
EndProcedure

Procedure pi3ut_Command()
  Protected total.i
  If pi3_ut_rx_quarantine <> 0
    pi3ut_WriteLine("!! serial receive quarantined; hardware restart required")
    ProcedureReturn
  EndIf
  pi3_ut_parse = 0
  If pi3_ut_command_extension<>0
    total=pi3_ut_command_extension()
    If total=1
      ProcedureReturn
    EndIf
    pi3_ut_parse=0
  EndIf
  If pi3ut_Match("help") <> 0 And pi3ut_End() <> 0
    pi3ut_WriteLine("update begin <length> <sha256> | status | commit | abort; reset")
    ProcedureReturn
  EndIf
  pi3_ut_parse = 0
  If pi3ut_Match("reset") <> 0 And pi3ut_End() <> 0
    If Pi3UpdateResetReady() = 0
      pi3ut_WriteLine("!! reset refused: receive or unconfirmed/uncertain storage state")
      ProcedureReturn
    EndIf
    If pi3ut_WriteLine("resetting") = 0
      ProcedureReturn
    EndIf
    If Pi3UartWaitClear(8) = 0
      pi3ut_WriteLine("!! reset refused: UART did not drain") : ProcedureReturn
    EndIf
    Pi3UpdateResetNow()
    pi3ut_WriteLine("!! reset did not occur")
    ProcedureReturn
  EndIf
  pi3_ut_parse = 0
  If pi3ut_Match("update") = 0
    pi3ut_WriteLine("!! unknown command; type help")
    ProcedureReturn
  EndIf
  If pi3ut_Match("status") <> 0 And pi3ut_End() <> 0
    pi3ut_Status()
    ProcedureReturn
  EndIf
  If pi3ut_Match("abort") <> 0 And pi3ut_End() <> 0
    Pi3UpdateAbort()
    pi3ut_WriteLine("aborted; the selected boot slot did not change")
    ProcedureReturn
  EndIf
  If pi3ut_Match("commit") <> 0 And pi3ut_End() <> 0
    If Pi3UpdateCommit() = 0
      pi3ut_WriteText("!! commit refused, error ") : pi3ut_WriteInt(Pi3UpdateError())
      pi3ut_WriteByte(13) : pi3ut_WriteByte(10)
      ProcedureReturn
    EndIf
    pi3ut_WriteText("committed slot ")
    If Pi3UpdatePendingSlot() = 0 : pi3ut_WriteText("A") : Else : pi3ut_WriteText("B") : EndIf
    pi3ut_WriteText(" generation ") : pi3ut_WriteDec(Pi3UpdatePendingGeneration())
    pi3ut_WriteByte(13) : pi3ut_WriteByte(10)
    ProcedureReturn
  EndIf
  If pi3ut_Match("begin") <> 0
    total = pi3ut_ParseDec()
    If total <= 0 Or pi3ut_ParseDigest() = 0 Or pi3ut_End() = 0
      pi3ut_WriteLine("!! usage: update begin <decimal length> <64 hex sha256>")
      ProcedureReturn
    EndIf
    If Pi3UpdateBegin(total, @pi3_ut_digest[0]) = 0
      pi3ut_WriteText("!! update begin refused, error ") : pi3ut_WriteInt(Pi3UpdateError())
      pi3ut_WriteByte(13) : pi3ut_WriteByte(10)
      ProcedureReturn
    EndIf
    pi3ut_WriteLine("rdy 0")
    If pi3ut_ReceiveFrames(total) = 0
      ; Binary acknowledgement already named the exact failure. Returning to
      ; the prompt is the recovery contract; no slot selection changed.
      ProcedureReturn
    EndIf
    pi3ut_WriteText("staged ") : pi3ut_WriteDec(total)
    pi3ut_WriteByte(13) : pi3ut_WriteByte(10)
    ProcedureReturn
  EndIf
  pi3ut_WriteLine("!! usage: update begin|status|commit|abort")
EndProcedure

Procedure Pi3UpdateServe()
  pi3ut_WriteLine("Pi 3 safe A/B update monitor ready")
  Repeat
    pi3ut_Prompt()
    If pi3ut_ReadLine() <> 0
      If pi3_ut_line_overflow <> 0
        pi3ut_WriteLine("!! command is longer than 159 bytes; nothing was done")
      ElseIf pi3_ut_line_len > 0
        pi3ut_Command()
        If pi3_ut_rx_quarantine <> 0
          pi3ut_WriteLine("STOP: serial drain could not prove a quiet interval")
          ProcedureReturn
        EndIf
      EndIf
    EndIf
  ForEver
EndProcedure

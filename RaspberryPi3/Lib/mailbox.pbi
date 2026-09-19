; BCM2837 property channel, exclusive primary boot owner. Include timer first.
; Caller buffer must be resident, 16-byte aligned, uncached low ARM RAM.
; Does not pretend a cache-off diagnostic path supports cached DMA ownership.
#PI3_MBOX = $3F00B880
Global Dim pi3_property.l[12]
; A timed-out submitted buffer remains firmware-owned until reboot. No retry
; or reuse is safe without observing its completion; refuse later requests.
Global pi3_mailbox_outstanding.i

; Pi 3B's activity LED is not BCM GPIO47.  The board device tree names
; firmware-expander line 2 STATUS_LED; the firmware GPIO service numbers its
; eight expander lines from 128, so the board status LED is firmware GPIO 130.
; SET_GPIO_STATE returns zero in the gpio payload word on success (it does not
; echo 130).  This optional boot diagnostic must never become a boot
; prerequisite.  Protocol facts were checked against the pinned Raspberry Pi
; Linux DTS, gpio-raspberrypi-exp driver and firmware tag definitions.
#PI3_FIRMWARE_STATUS_LED = 130
Procedure.i Pi3MailboxContext()
  ASM
    mrs x0, mpidr_el1
    movz x1, #255
    and x0, x0, x1
    cbnz x0, pi3_mbx_bad
    mrs x0, currentel
    cmp x0, #8
    b.eq pi3_mbx_el2
    cmp x0, #12
    b.ne pi3_mbx_bad
    mrs x0, sctlr_el3
    b pi3_mbx_check
pi3_mbx_el2:
    mrs x0, sctlr_el2
pi3_mbx_check:
    movz x1, #5
    and x0, x0, x1
    cbnz x0, pi3_mbx_bad
    movz x0, #1
    b pi3_mbx_done
pi3_mbx_bad:
    movz x0, #0
pi3_mbx_done:
  EndASM
  ProcedureReturn
EndProcedure
Procedure Pi3MailboxBarrier()
  ASM
    dsb sy
    isb
  EndASM
EndProcedure
Procedure.i Pi3MailboxCall(buffer.i, bytes.i)
  Protected request.i
  Protected start.i
  Protected now.i
  Protected response.i
  Protected n.i
  If pi3_mailbox_outstanding <> 0
    ProcedureReturn 0
  EndIf
  If buffer < $1000 Or (buffer & 15) <> 0 Or bytes < 12 Or bytes > 4096 Or (bytes & 3) <> 0
    ProcedureReturn 0
  EndIf
  If buffer > $3F000000 - bytes Or Pi3MailboxContext() = 0
    ProcedureReturn 0
  EndIf
  If (PeekL(buffer) & $FFFFFFFF) <> bytes Or PeekL(buffer + 4) <> 0
    ProcedureReturn 0
  EndIf
  start = Pi3Micros()
  If start < 0
    ProcedureReturn 0
  EndIf
  request = buffer | $C0000008
  Pi3MailboxBarrier()
  ; Linux gives a firmware transaction three seconds. Framebuffer allocation
  ; is a cold display operation, not a register read; the former 100 ms limit
  ; rejected a merely slow valid reply. The iteration cap remains as a second
  ; bound if the system timer itself stops advancing.
  For n = 0 To 9999999
    If (PeekL(#PI3_MBOX + $38) & $80000000) = 0
      Break
    EndIf
    now = Pi3Micros()
    If now < start Or now - start >= 3000000
      ProcedureReturn 0
    EndIf
  Next
  If n > 9999999
    ProcedureReturn 0
  EndIf
  pi3_mailbox_outstanding = 1
  PokeL(#PI3_MBOX + $20, request)
  For n = 0 To 9999999
    If (PeekL(#PI3_MBOX + $18) & $40000000) = 0
      response = PeekL(#PI3_MBOX) & $FFFFFFFF
      If response = request
        Pi3MailboxBarrier()
        pi3_mailbox_outstanding = 0
        If (PeekL(buffer + 4) & $FFFFFFFF) = $80000000
          ProcedureReturn 1
        EndIf
        ProcedureReturn 0
      EndIf
    EndIf
    now = Pi3Micros()
    If now < start Or now - start >= 3000000
      ProcedureReturn 0
    EndIf
  Next
  ProcedureReturn 0
EndProcedure

Procedure.i Pi3StatusLed(state.i)
  Protected buffer.i
  If pi3_mailbox_outstanding <> 0
    ProcedureReturn 0
  EndIf
  If state <> 0 : state = 1 : EndIf
  buffer = ((@pi3_property[0] + 15) >> 4) << 4
  PokeL(buffer,32) : PokeL(buffer + 4,0)
  PokeL(buffer + 8,$38041) : PokeL(buffer + 12,8)
  PokeL(buffer + 16,8) : PokeL(buffer + 20,#PI3_FIRMWARE_STATUS_LED)
  PokeL(buffer + 24,state) : PokeL(buffer + 28,0)
  If Pi3MailboxCall(buffer,32) = 0 : ProcedureReturn 0 : EndIf
  If PeekL(buffer + 8) <> $38041 Or PeekL(buffer + 12) <> 8 Or (PeekL(buffer + 16) & $FFFFFFFF) <> $80000008
    ProcedureReturn 0
  EndIf
  ; Firmware replaces the requested GPIO id with its status: zero is success.
  ProcedureReturn Bool(PeekL(buffer + 20) = 0)
EndProcedure

Procedure.i Pi3ClockRate(id.i)
  Protected buffer.i
  If pi3_mailbox_outstanding <> 0 Or id < 1 Or id > 14
    ProcedureReturn -1
  EndIf
  buffer = ((@pi3_property[0] + 15) >> 4) << 4
  PokeL(buffer, 32)
  PokeL(buffer + 4, 0)
  PokeL(buffer + 8, $30002)
  PokeL(buffer + 12, 8)
  PokeL(buffer + 16, 4)
  PokeL(buffer + 20, id)
  PokeL(buffer + 24, 0)
  PokeL(buffer + 28, 0)
  If Pi3MailboxCall(buffer, 32) = 0
    ProcedureReturn -1
  EndIf
  If PeekL(buffer + 8) <> $30002 Or PeekL(buffer + 12) <> 8 Or (PeekL(buffer + 16) & $FFFFFFFF) <> $80000008 Or PeekL(buffer + 20) <> id
    ProcedureReturn -1
  EndIf
  ProcedureReturn PeekL(buffer + 24) & $FFFFFFFF
EndProcedure

; Pi3ClockMeasuredRate(id) - hardware-measured rate when firmware supports
; GET_CLOCK_RATE_MEASURED. -1 means the optional tag was rejected/unsupported.
Procedure.i Pi3ClockMeasuredRate(id.i)
  Protected buffer.i
  If pi3_mailbox_outstanding <> 0 Or id < 1 Or id > 14
    ProcedureReturn -1
  EndIf
  buffer = ((@pi3_property[0] + 15) >> 4) << 4
  PokeL(buffer, 32) : PokeL(buffer + 4, 0)
  PokeL(buffer + 8, $30047) : PokeL(buffer + 12, 8)
  PokeL(buffer + 16, 4) : PokeL(buffer + 20, id)
  PokeL(buffer + 24, 0) : PokeL(buffer + 28, 0)
  If Pi3MailboxCall(buffer, 32) = 0 : ProcedureReturn -1 : EndIf
  If PeekL(buffer + 8) <> $30047 Or PeekL(buffer + 12) <> 8 Or (PeekL(buffer + 16) & $FFFFFFFF) <> $80000008 Or PeekL(buffer + 20) <> id
    ProcedureReturn -1
  EndIf
  If (PeekL(buffer + 24) & $FFFFFFFF) < 1 : ProcedureReturn -1 : EndIf
  ProcedureReturn PeekL(buffer + 24) & $FFFFFFFF
EndProcedure

; Pi3ClockMaxRate(id) - firmware's supported ceiling, not a set operation.
; The caller must still set a rate and use the returned rate from that set as
; the authority: firmware may clamp it for thermal or policy reasons.
Procedure.i Pi3ClockMaxRate(id.i)
  Protected buffer.i
  If pi3_mailbox_outstanding <> 0 Or id < 1 Or id > 14
    ProcedureReturn -1
  EndIf
  buffer = ((@pi3_property[0] + 15) >> 4) << 4
  PokeL(buffer, 32) : PokeL(buffer + 4, 0)
  PokeL(buffer + 8, $30004) : PokeL(buffer + 12, 8)
  PokeL(buffer + 16, 4) : PokeL(buffer + 20, id)
  PokeL(buffer + 24, 0) : PokeL(buffer + 28, 0)
  If Pi3MailboxCall(buffer, 32) = 0 : ProcedureReturn -1 : EndIf
  If PeekL(buffer + 8) <> $30004 Or PeekL(buffer + 12) <> 8 Or (PeekL(buffer + 16) & $FFFFFFFF) <> $80000008 Or PeekL(buffer + 20) <> id
    ProcedureReturn -1
  EndIf
  ProcedureReturn PeekL(buffer + 24) & $FFFFFFFF
EndProcedure

; Pi3ClockSetRate(id, rate, skipTurbo) - request a firmware clock rate.
; The positive return is the firmware's actual accepted rate, which may be
; below the request. Zero is failure; callers must not substitute the request.
Procedure.i Pi3ClockSetRate(id.i, rate.i, skipTurbo.i)
  Protected buffer.i
  If pi3_mailbox_outstanding <> 0 Or id < 1 Or id > 14 Or rate < 1 Or rate > 4294967295 Or skipTurbo < 0 Or skipTurbo > 1
    ProcedureReturn 0
  EndIf
  buffer = ((@pi3_property[0] + 15) >> 4) << 4
  PokeL(buffer, 36) : PokeL(buffer + 4, 0)
  PokeL(buffer + 8, $38002) : PokeL(buffer + 12, 12)
  PokeL(buffer + 16, 12) : PokeL(buffer + 20, id)
  PokeL(buffer + 24, rate) : PokeL(buffer + 28, skipTurbo)
  PokeL(buffer + 32, 0)
  If Pi3MailboxCall(buffer, 36) = 0 : ProcedureReturn 0 : EndIf
  If PeekL(buffer + 8) <> $38002 Or PeekL(buffer + 12) <> 12 Or (PeekL(buffer + 16) & $FFFFFFFF) <> $80000008 Or PeekL(buffer + 20) <> id
    ProcedureReturn 0
  EndIf
  If (PeekL(buffer + 24) & $FFFFFFFF) < 1 : ProcedureReturn 0 : EndIf
  ProcedureReturn PeekL(buffer + 24) & $FFFFFFFF
EndProcedure

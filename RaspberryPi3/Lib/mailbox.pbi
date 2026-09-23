; BCM2837 property channel, exclusive primary boot owner. Include timer first.
; Caller buffer must be resident, 16-byte aligned, uncached low ARM RAM.
; Does not pretend a cache-off diagnostic path supports cached DMA ownership.
#PI3_MBOX = $3F00B880
; Largest used property payload is SET_GPIO_CONFIG (24 B): after up to
; 15 B alignment padding, keep the full 48 B message inside this buffer.
; First aligned 64 bytes remain the synchronous property lane. The next
; aligned 64 bytes are exclusively HPD, so a command that prepares another
; property request cannot overwrite an in-flight connector sample.
Global Dim pi3_property.l[40]
; A timed-out submitted buffer remains firmware-owned until reboot. No retry
; or reuse is safe without observing its completion; refuse later requests.
Global pi3_mailbox_outstanding.i
Global pi3_mailbox_async_request.i
Global pi3_mailbox_async_buffer.i
Global pi3_mailbox_async_start.i
Global pi3_mailbox_async_timeout.i
Global pi3_mailbox_begin_waiting.i

; Pi 3B's activity LED is not BCM GPIO47. The board device tree names
; firmware-expander line 2 STATUS_LED; the firmware GPIO service numbers its
; eight expander lines from 128, so the board status LED is firmware GPIO 130.
; SET_GPIO_STATE returns zero in the gpio payload word on success (it does not
; echo 130).  This optional boot diagnostic must never become a boot
; prerequisite.  Protocol facts were checked against the pinned Raspberry Pi
; Linux DTS, gpio-raspberrypi-exp driver and firmware tag definitions.
#PI3_FIRMWARE_STATUS_LED = 130
#PI3_FIRMWARE_HDMI0_HPD = 132
Procedure.i Pi3MailboxContextState()
  ASM
    mrs x0, mpidr_el1
    movz x1, #255
    and x0, x0, x1
    cbnz x0, pi3_mbx_bad
    mrs x0, currentel
    cmp x0, #12
    b.ne pi3_mbx_bad
    mrs x0, sctlr_el3
    movz x1, #5
    and x0, x0, x1
    cbz x0, pi3_mbx_cold
    cmp x0, #5
    b.eq pi3_mbx_cached
    b pi3_mbx_bad
pi3_mbx_cold:
    movz x0, #1
    b pi3_mbx_done
pi3_mbx_cached:
    movz x0, #2
    b pi3_mbx_done
pi3_mbx_bad:
    movz x0, #0
  pi3_mbx_done:
  EndASM
  ProcedureReturn
EndProcedure

; Read one firmware-expander input without touching the HDMI controller.
; Pi 3 Model B routes HDMI0 HPD to expander line 4 and describes it as
; active-low in its DT, so callers invert the returned physical level.
Procedure.i Pi3FirmwareGpioGetStateTimeout(gpioId.i, timeoutUs.i)
  Protected buffer.i
  If pi3_mailbox_outstanding <> 0 Or gpioId < 128 Or gpioId > 135
    ProcedureReturn -1
  EndIf
  buffer = ((@pi3_property[0] + 15) >> 4) << 4
  PokeL(buffer,32) : PokeL(buffer + 4,0)
  PokeL(buffer + 8,$30041) : PokeL(buffer + 12,8)
  PokeL(buffer + 16,8) : PokeL(buffer + 20,gpioId)
  PokeL(buffer + 24,0) : PokeL(buffer + 28,0)
  If Pi3MailboxCallTimeout(buffer,32,timeoutUs)=0 : ProcedureReturn -1 : EndIf
  If PeekL(buffer + 8)<>$30041 Or PeekL(buffer + 12)<>8
    ProcedureReturn -1
  EndIf
  If (PeekL(buffer + 16)&$FFFFFFFF)<>8 And (PeekL(buffer + 16)&$FFFFFFFF)<>$80000008
    ProcedureReturn -1
  EndIf
  ; As in gpio-raspberrypi-exp, firmware clears the id word on success and
  ; returns the raw physical value in the second payload word.
  If PeekL(buffer + 20)<>0 : ProcedureReturn -1 : EndIf
  If PeekL(buffer + 24)<>0 And PeekL(buffer + 24)<>1 : ProcedureReturn -1 : EndIf
  ProcedureReturn PeekL(buffer + 24)
EndProcedure

Procedure.i Pi3MailboxContext()
  If Pi3MailboxContextState() = 1 : ProcedureReturn 1 : EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i Pi3MailboxBufferContext(buffer.i, bytes.i)
  Protected state.i
  state = Pi3MailboxContextState()
  ; The cache-off cold path is retained. With M/C active, accept only a
  ; complete buffer span explicitly registered Normal Non-Cacheable before
  ; MmuBuildTables(); this is coherent for the VideoCore property channel.
  If state = 1 : ProcedureReturn 1 : EndIf
  If state = 2 And bytes >= 12 And MmuIsNcRange(buffer, buffer + bytes - 1) <> 0
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure
Procedure Pi3MailboxBarrier()
  ASM
    dsb sy
    isb
  EndASM
EndProcedure
Procedure.i Pi3MailboxCallTimeout(buffer.i, bytes.i, timeoutUs.i)
  Protected request.i
  Protected start.i
  Protected now.i
  Protected response.i
  Protected n.i
  If pi3_mailbox_outstanding <> 0
    ProcedureReturn 0
  EndIf
  If timeoutUs < 1 Or timeoutUs > 3000000 Or buffer < $1000 Or (buffer & 15) <> 0 Or bytes < 12 Or bytes > 4096 Or (bytes & 3) <> 0
    ProcedureReturn 0
  EndIf
  If buffer > $3F000000 - bytes Or Pi3MailboxBufferContext(buffer, bytes) = 0
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
    If now < start Or now - start >= timeoutUs
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
    If now < start Or now - start >= timeoutUs
      ProcedureReturn 0
    EndIf
  Next
  ProcedureReturn 0
EndProcedure

; Cooperative property transaction. Begin performs at most one FIFO status
; check and Poll consumes at most one reply; callers return PENDING between
; them so serial/network service is never held in a mailbox spin loop.
Procedure.i Pi3MailboxBegin(buffer.i,bytes.i,timeoutUs.i)
  Protected request.i,now.i
  If pi3_mailbox_begin_waiting<>0
    If buffer<>pi3_mailbox_async_buffer Or timeoutUs<>pi3_mailbox_async_timeout : ProcedureReturn -1 : EndIf
    If (PeekL(#PI3_MBOX+$38)&$80000000)<>0
      now=Pi3Micros()
      If now<pi3_mailbox_async_start Or now-pi3_mailbox_async_start>=timeoutUs
        pi3_mailbox_begin_waiting=0 : pi3_mailbox_outstanding=0 : ProcedureReturn -1
      EndIf
      ProcedureReturn 0
    EndIf
    request=buffer|$C0000008 : pi3_mailbox_async_request=request
    pi3_mailbox_begin_waiting=0
    Pi3MailboxBarrier() : PokeL(#PI3_MBOX+$20,request)
    ProcedureReturn 1
  EndIf
  If pi3_mailbox_outstanding<>0 : ProcedureReturn -1 : EndIf
  If timeoutUs<1 Or timeoutUs>3000000 Or buffer<$1000 Or (buffer&15)<>0 Or bytes<12 Or bytes>4096 Or (bytes&3)<>0
    ProcedureReturn -1
  EndIf
  If buffer>$3F000000-bytes Or Pi3MailboxBufferContext(buffer,bytes)=0 Or (PeekL(buffer)&$FFFFFFFF)<>bytes Or PeekL(buffer+4)<>0
    ProcedureReturn -1
  EndIf
  pi3_mailbox_async_start=Pi3Micros()
  If pi3_mailbox_async_start<0 : ProcedureReturn -1 : EndIf
  pi3_mailbox_async_buffer=buffer : pi3_mailbox_async_timeout=timeoutUs : pi3_mailbox_outstanding=1
  If (PeekL(#PI3_MBOX+$38)&$80000000)<>0
    pi3_mailbox_begin_waiting=1 : ProcedureReturn 0
  EndIf
  request=buffer|$C0000008 : pi3_mailbox_async_request=request
  Pi3MailboxBarrier() : PokeL(#PI3_MBOX+$20,request)
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3MailboxPoll()
  Protected response.i,now.i
  If pi3_mailbox_outstanding=0 Or pi3_mailbox_async_request=0 : ProcedureReturn -1 : EndIf
  If (PeekL(#PI3_MBOX+$18)&$40000000)=0
    response=PeekL(#PI3_MBOX)&$FFFFFFFF
    If response=pi3_mailbox_async_request
      Pi3MailboxBarrier() : pi3_mailbox_outstanding=0 : pi3_mailbox_async_request=0
      If (PeekL(pi3_mailbox_async_buffer+4)&$FFFFFFFF)=$80000000 : ProcedureReturn 1 : EndIf
      ProcedureReturn -1
    EndIf
  EndIf
  now=Pi3Micros()
  If now<pi3_mailbox_async_start Or now-pi3_mailbox_async_start>=pi3_mailbox_async_timeout
    ; A submitted timeout remains firmware-owned and quarantined.
    ProcedureReturn -1
  EndIf
  ProcedureReturn 0
EndProcedure

Global pi3_gpio_get_pending.i
Procedure.i Pi3FirmwareGpioGetStateStep(gpioId.i,*state)
  Protected buffer.i,rc.i,value.i
  buffer=((@pi3_property[0]+15)>>4)<<4 : buffer=buffer+64
  If pi3_gpio_get_pending=0
    PokeL(buffer,32) : PokeL(buffer+4,0)
    PokeL(buffer+8,$30041) : PokeL(buffer+12,8) : PokeL(buffer+16,8)
    PokeL(buffer+20,gpioId) : PokeL(buffer+24,0) : PokeL(buffer+28,0)
    rc=Pi3MailboxBegin(buffer,32,5000)
    If rc<=0 : ProcedureReturn rc : EndIf
    pi3_gpio_get_pending=1 : ProcedureReturn 0
  EndIf
  rc=Pi3MailboxPoll()
  If rc=0 : ProcedureReturn 0 : EndIf
  If rc<0 : ProcedureReturn -1 : EndIf
  pi3_gpio_get_pending=0
  If PeekL(buffer+8)<>$30041 Or PeekL(buffer+12)<>8 Or PeekL(buffer+20)<>0 : ProcedureReturn -1 : EndIf
  If (PeekL(buffer+16)&$FFFFFFFF)<>8 And (PeekL(buffer+16)&$FFFFFFFF)<>$80000008 : ProcedureReturn -1 : EndIf
  value=PeekL(buffer+24)
  If value<>0 And value<>1 : ProcedureReturn -1 : EndIf
  PokeI(*state,value)
  ProcedureReturn 1
EndProcedure

; Existing firmware property callers retain the three-second transaction
; bound. Display capability discovery uses the explicit shorter form above
; so unplugged or slow DDC cannot hold cold startup for a timeout per block.
Procedure.i Pi3MailboxCall(buffer.i, bytes.i)
  ProcedureReturn Pi3MailboxCallTimeout(buffer,bytes,3000000)
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

; Set one firmware-owned expander GPIO level. The board-profile layer
; owns which line means radio reset/power and its active polarity; this
; helper only provides the bounded, validated property transaction.
Procedure.i Pi3FirmwareGpioSetState(gpioId.i, state.i)
  Protected buffer.i
  If pi3_mailbox_outstanding <> 0 Or gpioId < 128 Or gpioId > 135 Or state < 0 Or state > 1
    ProcedureReturn 0
  EndIf
  buffer = ((@pi3_property[0] + 15) >> 4) << 4
  PokeL(buffer, 32) : PokeL(buffer + 4, 0)
  PokeL(buffer + 8, $38041) : PokeL(buffer + 12, 8)
  PokeL(buffer + 16, 8) : PokeL(buffer + 20, gpioId)
  PokeL(buffer + 24, state) : PokeL(buffer + 28, 0)
  If Pi3MailboxCall(buffer, 32) = 0 : ProcedureReturn 0 : EndIf
  ; Raspberry Pi firmware returns the SET_GPIO_STATE payload successfully
  ; with an 8-byte tag length that may omit the per-tag response bit. Linux's
  ; rpi_firmware_property validates the overall response and the expander
  ; driver validates that firmware cleared the GPIO ID; mirror those checks
  ; without weakening the validation for other property tags.
  If PeekL(buffer + 8) <> $38041 Or PeekL(buffer + 12) <> 8
    ProcedureReturn 0
  EndIf
  If (PeekL(buffer + 16) & $FFFFFFFF) <> 8 And (PeekL(buffer + 16) & $FFFFFFFF) <> $80000008
    ProcedureReturn 0
  EndIf
  ; Firmware reports zero in the GPIO payload word for success.
  ProcedureReturn Bool(PeekL(buffer + 20) = 0)
EndProcedure

; Match gpio-raspberrypi-exp direction_output(): read the expander's current
; polarity, retain it, then request output direction with the requested
; physical initial state. The GET response uses a five-word structure and
; SET uses six words. This is deliberately scoped to these firmware GPIO
; tags; it does not weaken validation for other mailbox properties.
Procedure.i Pi3FirmwareGpioConfigureOutput(gpioId.i, state.i)
  Protected buffer.i
  Protected polarity.i
  If pi3_mailbox_outstanding <> 0 Or gpioId < 128 Or gpioId > 135 Or state < 0 Or state > 1
    ProcedureReturn 0
  EndIf
  buffer = ((@pi3_property[0] + 15) >> 4) << 4
  PokeL(buffer, 44) : PokeL(buffer + 4, 0)
  PokeL(buffer + 8, $30043) : PokeL(buffer + 12, 20)
  PokeL(buffer + 16, 20) : PokeL(buffer + 20, gpioId)
  PokeL(buffer + 24, 0) : PokeL(buffer + 28, 0)
  PokeL(buffer + 32, 0) : PokeL(buffer + 36, 0)
  PokeL(buffer + 40, 0)
  If Pi3MailboxCall(buffer, 44) = 0 : ProcedureReturn 0 : EndIf
  If PeekL(buffer + 8) <> $30043 Or PeekL(buffer + 12) <> 20
    ProcedureReturn 0
  EndIf
  If (PeekL(buffer + 16) & $FFFFFFFF) <> 20 And (PeekL(buffer + 16) & $FFFFFFFF) <> $80000014
    ProcedureReturn 0
  EndIf
  If PeekL(buffer + 20) <> 0 : ProcedureReturn 0 : EndIf
  polarity = PeekL(buffer + 28)

  PokeL(buffer, 48) : PokeL(buffer + 4, 0)
  PokeL(buffer + 8, $38043) : PokeL(buffer + 12, 24)
  PokeL(buffer + 16, 24) : PokeL(buffer + 20, gpioId)
  PokeL(buffer + 24, 1) : PokeL(buffer + 28, polarity)
  PokeL(buffer + 32, 0) : PokeL(buffer + 36, 0)
  PokeL(buffer + 40, state) : PokeL(buffer + 44, 0)
  If Pi3MailboxCall(buffer, 48) = 0 : ProcedureReturn 0 : EndIf
  If PeekL(buffer + 8) <> $38043 Or PeekL(buffer + 12) <> 24
    ProcedureReturn 0
  EndIf
  If (PeekL(buffer + 16) & $FFFFFFFF) <> 24 And (PeekL(buffer + 16) & $FFFFFFFF) <> $80000018
    ProcedureReturn 0
  EndIf
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

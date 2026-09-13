; Shared setup for the immutable loader and serial updater composition.
XIncludeFile "RaspberryPi3/Lib/timer.pbi"
XIncludeFile "RaspberryPi3/Lib/uart.pbi"
XIncludeFile "RaspberryPi3/Lib/mailbox.pbi"
XIncludeFile "Anvil/Graphics/text_glyph.pbi"
XIncludeFile "RaspberryPi3/Lib/framebuffer.pbi"
XIncludeFile "RaspberryPi3/Lib/boot_memory.pbi"
XIncludeFile "RaspberryPi3/Lib/sdhost.pbi"
XIncludeFile "Anvil/Storage/fat32.pbi"
XIncludeFile "Anvil/Core/sha256.pbi"
#CRC_POLY = $EDB88320
XIncludeFile "Anvil/Core/crc.pbi"
XIncludeFile "RaspberryPi3/Lib/update_ab.pbi"
XIncludeFile "RaspberryPi3/Lib/update_watchdog.pbi"
XIncludeFile "RaspberryPi3/Lib/update_transport.pbi"
Global pi3_dtb.i
Global pi3_dtb_end.i
Global pi3_ram_base.i
Global pi3_ram_end.i
Global pi3_boot_status.i
Global Dim pi3_build_text.a[32]

Procedure Pi3Park()
  ASM
    msr daifset, #15
pi3_cold_park:
    wfe
    b pi3_cold_park
  EndASM
EndProcedure

Procedure.i Pi3BootMaxCoreClock()
  Protected buffer.i
  If pi3_mailbox_outstanding <> 0 : ProcedureReturn 0 : EndIf
  buffer = ((@pi3_property[0] + 15) >> 4) << 4
  PokeL(buffer, 32) : PokeL(buffer + 4, 0)
  PokeL(buffer + 8, $30004) : PokeL(buffer + 12, 8)
  PokeL(buffer + 16, 4) : PokeL(buffer + 20, 4)
  PokeL(buffer + 24, 0) : PokeL(buffer + 28, 0)
  If Pi3MailboxCall(buffer, 32) = 0 : ProcedureReturn 0 : EndIf
  If PeekL(buffer + 8) <> $30004 Or PeekL(buffer + 12) <> 8 Or (PeekL(buffer + 16) & $FFFFFFFF) <> $80000008 Or PeekL(buffer + 20) <> 4 : ProcedureReturn 0 : EndIf
  ProcedureReturn PeekL(buffer + 24) & $FFFFFFFF
EndProcedure

; The immutable loader owns a separate, never-fed watchdog around the exact
; cold storage interval that build 7 could enter without recovery coverage.
; Candidate/updater entry (display=0) already inherits the loader's trial
; watchdog and must neither restart nor stop it here.
Procedure.i Pi3BootStorage(display.i)
  Protected clock.i
  Protected mounted.i
  Protected ready.i
  If display<>0
    Pi3Say("E0: arm early 15-second storage watchdog")
    If Pi3UpdateWatchdogArmEarly()=0
      Pi3Say("STOP: early storage watchdog could not be armed")
      ProcedureReturn 0
    EndIf
    Pi3Say("E1: request firmware maximum core clock")
  EndIf
  clock=Pi3BootMaxCoreClock()
  If clock<1000000
    Pi3Say("STOP: maximum core clock request refused")
  Else
    If display<>0 : Pi3Say("E2: maximum core clock ready") : Pi3Say("E3: initialize native SDHOST") : EndIf
    If Pi3SdInit(clock,0,pi3_ram_end)=0
      Pi3Say("STOP: SDHOST initialization refused")
    Else
      If display<>0 : Pi3Say("E4: native SDHOST ready") : EndIf
      If Pi3UpdateConfigure($2000000,$E00000,0,pi3_ram_end,pi3_dtb,pi3_dtb_end-pi3_dtb)=0
        Pi3Say("STOP: A/B fixed arenas refused")
      Else
        If display<>0 : Pi3Say("E5: mount and verify A/B volume") : EndIf
        If display<>0 : mounted=Pi3UpdateMount() : Else : mounted=Pi3UpdateMountHandoff() : EndIf
        If mounted=0
          Pi3Say("STOP: A/B mount refused; no valid confirmed fallback or unsafe volume")
          pi3ut_WriteDec(Pi3UpdateError()) : pi3ut_WriteByte(13) : pi3ut_WriteByte(10)
        Else
          ready=1
        EndIf
      EndIf
    EndIf
  EndIf
  If display<>0
    ; Every ordinary refusal stops the early timer and remains parked for
    ; diagnosis. Only a genuinely wedged call is recovered by its expiry.
    If Pi3UpdateWatchdogStopEarly()=0
      Pi3Say("STOP: early storage watchdog could not be stopped")
      Pi3Park()
    EndIf
    Pi3Say("E6: early storage watchdog stopped")
  EndIf
  ProcedureReturn ready
EndProcedure

Procedure.i Pi3UpdateBootStart(display.i)
  Protected clock.i
  If p3sdContext() = 0 : ProcedureReturn 0 : EndIf
  ; Only the cold immutable loader adopts/stops watchdog reset residue.
  ; A running trial updater retains its watchdog until confirmation.
  If display <> 0
    If Pi3UpdateWatchdogColdStop() = 0 : ProcedureReturn 0 : EndIf
  EndIf
  clock = Pi3ClockRate(2)
  If clock <= 0 Or Pi3UartInit(clock, 115200) = 0 : ProcedureReturn 0 : EndIf
  If Pi3BootMemory() = 0 Or pi3_ram_base <> 0 Or pi3_ram_end < $3000000 Or pi3_dtb <> $1000000
    Pi3Say("STOP: ARM RAM/DTB boot layout refused") : ProcedureReturn 0
  EndIf
  If Pi3BootRanges(pi3_dtb, pi3_dtb_end - pi3_dtb) = 0
    Pi3Say("STOP: DTB reservations conflict with A/B boot arenas") : ProcedureReturn 0
  EndIf
  ; Only the immutable loader allocates a framebuffer. The updater is a
  ; serial health/recovery console; it does not leak a second allocation.
  If display <> 0
    If Pi3FbInit(pi3_dtb, pi3_dtb_end) = 0 : Pi3SayFramebufferError(Pi3FbError()) : EndIf
  EndIf
  Pi3Say("Anvil Pi3 A/B boot: validated memory, SDHOST next")
  Pi3PrintBuild()
  ProcedureReturn Pi3BootStorage(display)
EndProcedure

Procedure Pi3UpdateEnter()
  ASM
    dsb sy
    ic iallu
    dsb sy
    isb
    movz x0, #256, lsl #16
    movz x1, #32, lsl #16
    br x1
  EndASM
EndProcedure

Procedure.i Pi3BootSignal(stage.i)
  Protected pulse.i
  If stage<1 Or stage>9 : ProcedureReturn 0 : EndIf
  For pulse=1 To stage
    If Pi3StatusLed(1)=0 : ProcedureReturn 0 : EndIf
    If Pi3DelayUs(140000)=0 : ProcedureReturn 0 : EndIf
    If Pi3StatusLed(0)=0 : ProcedureReturn 0 : EndIf
    If Pi3DelayUs(140000)=0 : ProcedureReturn 0 : EndIf
  Next
  ProcedureReturn Pi3DelayUs(700000)
EndProcedure

Procedure Pi3DiagnosticPark(stage.i)
  Protected repeat.i
  ; Repeat only five times, then reach the same low-impact WFE park.  If a
  ; mailbox request itself timed out its buffer remains firmware-owned, so the
  ; signal refuses rather than retrying an unsafe transaction.
  For repeat=1 To 5 : Pi3BootSignal(stage) : Next
  Pi3Park()
EndProcedure

Procedure.i Pi3Say(text.i)
  Protected n.i
  Protected value.i
  Pi3FbLine(text)
  For n = 0 To 255
    value = PeekA(text + n)
    If value = 0
      If Pi3UartWrite(13) = 0 : ProcedureReturn 0 : EndIf
      ProcedureReturn Pi3UartWrite(10)
    EndIf
    If Pi3UartWrite(value) = 0 : ProcedureReturn 0 : EndIf
  Next
  ProcedureReturn 0
EndProcedure

Procedure.i Pi3ReadBe32(address.i)
  ProcedureReturn (PeekA(address) << 24) | (PeekA(address + 1) << 16) | (PeekA(address + 2) << 8) | PeekA(address + 3)
EndProcedure

Procedure Pi3PrintBuild()
  Protected value.i
  Protected index.i
  Protected quotient.i
  value=#ANVIL_BUILD : index=30
  pi3_build_text[31]=0
  Repeat
    quotient=value/10
    pi3_build_text[index]=48+value-quotient*10
    index=index-1 : value=quotient
  Until value=0
  pi3_build_text[index]=32 : index=index-1
  pi3_build_text[index]=100 : index=index-1
  pi3_build_text[index]=108 : index=index-1
  pi3_build_text[index]=105 : index=index-1
  pi3_build_text[index]=117 : index=index-1
  pi3_build_text[index]=66
  Pi3Say(@pi3_build_text[index])
EndProcedure

Procedure Pi3SayFramebufferError(code.i)
  Select code
    Case #PI3_FB_ERR_OWNERSHIP   : Pi3Say("STOP framebuffer: mailbox or allocation already owned")
    Case #PI3_FB_ERR_MAILBOX     : Pi3Say("STOP framebuffer: firmware mailbox transaction failed")
    Case #PI3_FB_ERR_TAG_REPLY   : Pi3Say("STOP framebuffer: required property tag was not returned")
    Case #PI3_FB_ERR_GEOMETRY    : Pi3Say("STOP framebuffer: firmware refused 640x480x32 offset zero")
    Case #PI3_FB_ERR_PIXEL_ORDER : Pi3Say("STOP framebuffer: invalid pixel-order response")
    Case #PI3_FB_ERR_ALPHA_MODE  : Pi3Say("STOP framebuffer: invalid alpha-mode response")
    Case #PI3_FB_ERR_ALLOCATION  : Pi3Say("STOP framebuffer: invalid base size or pitch")
    Case #PI3_FB_ERR_VC_RANGE    : Pi3Say("STOP framebuffer: allocation outside VideoCore memory")
    Case #PI3_FB_ERR_OVERLAP     : Pi3Say("STOP framebuffer: allocation overlaps Anvil or DTB")
    Default                      : Pi3Say("STOP framebuffer: unclassified refusal")
  EndSelect
EndProcedure

Procedure.i Pi3BootMemory()
  Protected buffer.i
  Protected size.i
  Protected total.i
  If pi3_mailbox_outstanding <> 0 : ProcedureReturn 0 : EndIf
  buffer = ((@pi3_property[0] + 15) >> 4) << 4
  PokeL(buffer,32) : PokeL(buffer + 4,0)
  PokeL(buffer + 8,$10005) : PokeL(buffer + 12,8)
  PokeL(buffer + 16,0) : PokeL(buffer + 20,0)
  PokeL(buffer + 24,0) : PokeL(buffer + 28,0)
  If Pi3MailboxCall(buffer,32) = 0 : ProcedureReturn 0 : EndIf
  If PeekL(buffer + 8) <> $10005 Or PeekL(buffer + 12) <> 8 Or (PeekL(buffer + 16) & $FFFFFFFF) <> $80000008
    ProcedureReturn 0
  EndIf
  pi3_ram_base = PeekL(buffer + 20) & $FFFFFFFF
  size = PeekL(buffer + 24) & $FFFFFFFF
  If pi3_ram_base > $80000 Or size < $200000 Or size > $3F000000
    ProcedureReturn 0
  EndIf
  pi3_ram_end = pi3_ram_base + size
  If pi3_ram_end < $200000 Or pi3_ram_end > $3F000000 : ProcedureReturn 0 : EndIf
  ; Do not dereference a firmware pointer until its minimum header is in RAM.
  If pi3_dtb < $1000 Or pi3_dtb < pi3_ram_base Or pi3_dtb > pi3_ram_end - 40 Or (pi3_dtb & 7) <> 0
    ProcedureReturn 0
  EndIf
  If pi3_dtb >= $80000 And pi3_dtb < $200000 : ProcedureReturn 0 : EndIf
  If Pi3ReadBe32(pi3_dtb) <> $D00DFEED : ProcedureReturn 0 : EndIf
  total = Pi3ReadBe32(pi3_dtb + 4)
  If total < 40 Or total > 1048576 Or total > pi3_ram_end - pi3_dtb
    ProcedureReturn 0
  EndIf
  pi3_dtb_end = pi3_dtb + total
  If pi3_dtb < $200000 And pi3_dtb_end > $80000 : ProcedureReturn 0 : EndIf
  ; All RAM remains unallocated. Preserve the entire DTB including reservations.
  ; This validates its outer span only, not its nodes or reserve-map contents.
  ProcedureReturn 1
EndProcedure

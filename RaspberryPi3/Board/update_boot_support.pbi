; Shared setup for the immutable loader and serial updater composition.
XIncludeFile "RaspberryPi3/Lib/timer.pbi"
XIncludeFile "RaspberryPi3/Lib/uart.pbi"
; The shared primary-core exception capture, not a second set of vectors for
; this board. Until it was installed here, a synchronous abort in early boot
; produced no output at all: there was no vector base register write anywhere in
; this tree, so a fault and a wedge looked identical on the wire, and one of
; them was chased for a week. See the public record for that defect.
XIncludeFile "Anvil/Kernel/exceptions.pbi"
XIncludeFile "RaspberryPi3/Lib/mailbox.pbi"
XIncludeFile "Anvil/Graphics/text_glyph.pbi"
XIncludeFile "RaspberryPi3/Lib/framebuffer.pbi"
XIncludeFile "RaspberryPi3/Lib/boot_memory.pbi"
XIncludeFile "RaspberryPi3/Lib/sdhost.pbi"
XIncludeFile "Anvil/Storage/fat32.pbi"
XIncludeFile "Anvil/Storage/exfat.pbi"
XIncludeFile "Anvil/Storage/filesystem.pbi"
XIncludeFile "Anvil/Core/sha256.pbi"
#CRC_POLY = $EDB88320
XIncludeFile "Anvil/Core/crc.pbi"
XIncludeFile "Anvil/Storage/ab_record.pbi"
XIncludeFile "RaspberryPi3/Lib/boot_record.pbi"
XIncludeFile "RaspberryPi3/Lib/update_ab.pbi"
XIncludeFile "RaspberryPi3/Lib/update_watchdog.pbi"
XIncludeFile "RaspberryPi3/Lib/update_transport.pbi"
Global pi3_dtb.i
Global pi3_dtb_end.i
Global pi3_ram_base.i
Global pi3_ram_end.i
Global pi3_boot_status.i
Global Dim pi3_build_text.a[32]
Global pi3_fault_vectors.i
XIncludeFile "RaspberryPi3/Board/pi3_boot_primitives.pbi"

; The fault reporter. It writes ONLY to the UART, never through Pi3Say: Pi3Say
; draws to the framebuffer first, and the whole point of this path is that it
; has to work when the framebuffer is not up yet, or is exactly what faulted.
; Every value is assembled a nibble at a time, so the reporter itself cannot
; take the alignment fault it is trying to describe.
Procedure Pi3FaultText(text.i)
  Protected n.i
  Protected value.i
  For n = 0 To 255
    value = PeekA(text + n)
    If value = 0 : Break : EndIf
    Pi3UartWrite(value)
  Next
EndProcedure

Procedure Pi3FaultHex(label.i, value.i)
  Protected n.i
  Protected digit.i
  Pi3FaultText(label)
  Pi3UartWrite(36)
  For n = 15 To 0 Step -1
    digit = (value >> (n * 4)) & 15
    If digit < 10
      Pi3UartWrite(48 + digit)
    Else
      Pi3UartWrite(55 + digit)
    EndIf
  Next
  Pi3UartWrite(13) : Pi3UartWrite(10)
EndProcedure

Procedure Pi3FaultReport()
  Pi3UartWrite(13) : Pi3UartWrite(10)
  Pi3FaultText("STOP: the processor took an exception during early boot, so the boot was abandoned rather than continued on unknown state.")
  Pi3UartWrite(13) : Pi3UartWrite(10)
  Pi3FaultText("  The four registers below say what happened: ESR is the syndrome (its top six bits are the exception class), ELR is the instruction that faulted, FAR is the address it touched, SPSR is the state it faulted in.")
  Pi3UartWrite(13) : Pi3UartWrite(10)
  Pi3FaultHex("  vector slot ", ExceptionSlot())
  Pi3FaultHex("  ESR  ", ExceptionEsr())
  Pi3FaultHex("  ELR  ", ExceptionElr())
  Pi3FaultHex("  FAR  ", ExceptionFar())
  Pi3FaultHex("  SPSR ", ExceptionSpsr())
  Pi3FaultHex("  SP   ", ExceptionSp())
  Pi3FaultText("  Check ELR against the loader's map first. An exception class of $25 is a data abort from this level; with the MMU off that is most often an unaligned wide access, which is a fault on this part whatever the strict-alignment bit says.")
  Pi3UartWrite(13) : Pi3UartWrite(10)
  Pi3FaultText("  The boot stops here. If the early storage watchdog was armed it will reset the board shortly; otherwise power-cycle it.")
  Pi3UartWrite(13) : Pi3UartWrite(10)
EndProcedure

; Installed as early as the UART allows, because everything worth reporting
; happens after it and nothing before it could be reported anyway.
Procedure.i Pi3InstallFaultVectors()
  If pi3_fault_vectors <> 0 : ProcedureReturn 1 : EndIf
  ExceptionSetReporter(@Pi3FaultReport)
  If ExceptionInstall() = 0 : ProcedureReturn 0 : EndIf
  pi3_fault_vectors = 1
  ProcedureReturn 1
EndProcedure

; The CURRENT core rate, tag $00030002, as against the maximum the divisor is
; computed from. The divisor deliberately uses the maximum so the card clock can
; only come out below what was asked for, never above it if the core boosts
; later - the reference driver uses the current rate because it is told when
; that changes, and a loader is not. Reading the current rate once turns that
; conservative choice from a silent slow card clock into a line in the log.
Procedure.i Pi3BootCurrentCoreClock()
  Protected buffer.i
  If pi3_mailbox_outstanding <> 0 : ProcedureReturn 0 : EndIf
  buffer = ((@pi3_property[0] + 15) >> 4) << 4
  PokeL(buffer, 32) : PokeL(buffer + 4, 0)
  PokeL(buffer + 8, $30002) : PokeL(buffer + 12, 8)
  PokeL(buffer + 16, 4) : PokeL(buffer + 20, 4)
  PokeL(buffer + 24, 0) : PokeL(buffer + 28, 0)
  If Pi3MailboxCall(buffer, 32) = 0 : ProcedureReturn 0 : EndIf
  If PeekL(buffer + 8) <> $30002 Or PeekL(buffer + 12) <> 8 Or (PeekL(buffer + 16) & $FFFFFFFF) <> $80000008 Or PeekL(buffer + 20) <> 4 : ProcedureReturn 0 : EndIf
  ProcedureReturn PeekL(buffer + 24) & $FFFFFFFF
EndProcedure

Procedure Pi3SayClockGap(assumed.i, actual.i)
  pi3ut_WriteText("E2a: the SD divisor assumes a core clock of ")
  pi3ut_WriteDec(assumed)
  pi3ut_WriteText(" Hz but the core is running at ")
  pi3ut_WriteDec(actual)
  pi3ut_WriteText(" Hz, so the card clock is that much slower than the 25000000 Hz asked for. This is the conservative choice - it can never overclock the card - not a fault.")
  pi3ut_WriteByte(13) : pi3ut_WriteByte(10)
EndProcedure

; Cold-loader-only mount breadcrumbs. The callback is installed by the
; display path before E5 and cleared immediately after the bounded mount;
; recovery/candidate paths remain quiet and keep their existing transcript.
Global pi3_boot_mount_started.i

Global pi3_boot_progress_reported.i

; This handler is installed only while the immutable loader owns work.
; Watchdog service follows a completed unit, never a UART/timer polling loop.
Procedure.i Pi3BootWorkProgress(completed.i)
  Protected now.i
  If Pi3UpdateWatchdogProgress(completed)=0 : ProcedureReturn 0 : EndIf
  now=Pi3Micros()
  If now<0 : ProcedureReturn 0 : EndIf
  If now-pi3_boot_progress_reported>=1000000
    Pi3FaultHex("completed work units ",completed)
    Pi3FaultHex("elapsed-us ",now-pi3_boot_mount_started)
    pi3_boot_progress_reported=now
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure Pi3BootWorkBegin()
  pi3_boot_mount_started=Pi3Micros()
  pi3_boot_progress_reported=pi3_boot_mount_started
  Pi3UpdateWorkProgressHandler(@Pi3BootWorkProgress)
  Pi3SdSetProgressHook(@Pi3UpdateSdProgress)
EndProcedure
Procedure Pi3BootWorkEnd()
  Pi3SdSetProgressHook(0)
  Pi3UpdateWorkProgressHandler(0)
  Pi3UpdateMountProgressHandler(0)
EndProcedure

Procedure Pi3BootMountProgress()
  Protected now.i
  Protected elapsed.i
  now = Pi3Micros()
  elapsed = now - pi3_boot_mount_started
  Select Pi3UpdateMountPhase()
    Case 1 : Pi3Say("E5a: filesystem mount")
    Case 2 : Pi3Say("E5b: file extents")
    Case 12 : Pi3Say("E5b0: map ANVILA.BIN")
    Case 13 : Pi3Say("E5b1: map ANVILB.BIN")
    Case 14 : Pi3Say("E5b2: map P3CTRLA.BIN")
    Case 15 : Pi3Say("E5b3: map P3CTRLB.BIN")
    Case 16 : Pi3Say("E5b4: map KERNEL8.IMG")
    Case 50 : Pi3Say("E5p: hash container payload")
    Case 51 : Pi3Say("E5q: hash container wrapper")
    Case 60 : Pi3Say("E5r: read record A")
    Case 61 : Pi3Say("E5s: read record B")
    Case 3 : Pi3Say("E5c: root allocation")
    Case 4 : Pi3Say("E5d: foreign allocation")
    Case 5 : Pi3Say("E5e: control records")
    Case 10 : Pi3Say("E5f: verify slot A")
    Case 11 : Pi3Say("E5g: verify slot B")
    Case 20 : Pi3Say("E5i: read slot A")
    Case 21 : Pi3Say("E5j: read slot B")
    Case 30 : Pi3Say("E5k: validate container A")
    Case 31 : Pi3Say("E5l: validate container B")
    Case 40 : Pi3Say("E5m: hash RAM slot A")
    Case 41 : Pi3Say("E5n: hash RAM slot B")
    Case 8 : Pi3Say("E5h: mount complete")
  EndSelect
  Pi3FaultHex(" elapsed-us ", elapsed)
EndProcedure

; The immutable loader owns a separate, never-fed watchdog around the exact
; cold storage interval that build 7 could enter without recovery coverage.
; Candidate/updater entry (display=0) already inherits the loader's trial
; watchdog and must neither restart nor stop it here.
Procedure.i Pi3BootStorage(display.i)
  Protected clock.i
  Protected running.i
  Protected mounted.i
  Protected ready.i
  If display<>0
    Pi3Say("E0: arm early 15-second storage watchdog")
    If Pi3UpdateWatchdogArmEarly()=0
      Pi3Say("STOP: early storage watchdog could not be armed")
      ProcedureReturn 0
    EndIf
    Pi3BootWorkBegin()
    Pi3Say("E1: set stock ARM 1200000000 Hz and CORE 400000000 Hz")
  EndIf
  If Pi3BootSetStockClocks() <> 0
    clock=Pi3BootMaxCoreClock()
    If display<>0
      If Pi3BootStockClockIsMeasured()<>0
        Pi3FaultHex("ARM measured Hz ", Pi3BootStockArmActual())
        Pi3FaultHex("CORE measured Hz ", Pi3BootStockCoreActual())
      Else
        Pi3FaultHex("ARM configured Hz ", Pi3BootStockArmActual())
        Pi3FaultHex("CORE configured Hz ", Pi3BootStockCoreActual())
      EndIf
    EndIf
  EndIf
  If clock<1000000
    Pi3Say("STOP: stock ARM/CORE clock setup or ceiling query refused")
  Else
    If display<>0
      Pi3Say("E2: stock clocks requested and read back; SD clock ceiling ready")
      running=Pi3BootCurrentCoreClock()
      If running<1
        Pi3Say("E2a: the current core clock could not be read, so how far below 25000000 Hz the card clock lands is unknown.")
      ElseIf running<>clock
        Pi3SayClockGap(clock,running)
      EndIf
      Pi3Say("E3: initialize native SDHOST")
    EndIf
    If Pi3SdInit(clock,0,pi3_ram_end)=0
      Pi3Say("STOP: SDHOST initialization refused")
    Else
      If display<>0 : Pi3Say("E4: native SDHOST ready") : EndIf
      If Pi3UpdateConfigure($2000000,$E00000,0,pi3_ram_end,pi3_dtb,pi3_dtb_end-pi3_dtb)=0
        Pi3Say("STOP: A/B fixed arenas refused")
      Else
        If display<>0 : Pi3Say("E5: mount and verify A/B volume") : pi3_boot_mount_started=Pi3Micros() : Pi3UpdateMountProgressHandler(@Pi3BootMountProgress) : EndIf
        If display<>0 : mounted=Pi3UpdateMount() : Else : mounted=Pi3UpdateMountHandoff() : EndIf
        If display<>0 : Pi3UpdateMountProgressHandler(0) : EndIf
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
    Pi3BootWorkEnd()
    If Pi3UpdateWatchdogStopEarly()=0
      Pi3Say("STOP: early storage watchdog could not be stopped")
      Pi3Park()
    EndIf
    Pi3Say("E6: early storage watchdog stopped")
  EndIf
  ProcedureReturn ready
EndProcedure

; Split from Pi3UpdateBootStart so the immutable loader can offer its recovery
; window BEFORE it touches storage. Everything here is the port, the processor
; state and memory: nothing that reads the card, and nothing that has ever taken
; minutes. Whatever this leaves working is what recovery can rely on.
Procedure.i Pi3UpdateBootBegin(display.i)
  Protected clock.i
  If p3sdContext() = 0 : ProcedureReturn 0 : EndIf
  ; Only the cold immutable loader adopts/stops watchdog reset residue.
  ; A running trial updater retains its watchdog until confirmation.
  If display <> 0
    If Pi3UpdateWatchdogColdStop() = 0 : ProcedureReturn 0 : EndIf
  EndIf
  clock = Pi3ClockRate(2)
  If clock <= 0 Or Pi3UartInit(clock, 115200) = 0 : ProcedureReturn 0 : EndIf
  ; FIRST thing after the port exists, and before memory validation, the
  ; framebuffer, storage or the mount. Every failure this boot chain has ever
  ; had happened after this line, and every one of them was silent.
  If Pi3InstallFaultVectors() = 0
    Pi3Say("STOP: exception vectors could not be installed, so a fault later in this boot would be silent. Refusing to continue blind.")
    ProcedureReturn 0
  EndIf
  If Pi3LoaderBootMemory() = 0 Or pi3_ram_base <> 0 Or pi3_ram_end < $3000000 Or pi3_dtb <> $1000000
    Pi3Say("STOP: ARM RAM/DTB boot layout refused") : ProcedureReturn 0
  EndIf
  If Pi3BootRanges(pi3_dtb, pi3_dtb_end - pi3_dtb) = 0
    Pi3Say("STOP: DTB reservations conflict with A/B boot arenas") : ProcedureReturn 0
  EndIf
  ; Only the immutable loader allocates a framebuffer. The updater is a
  ; serial health/recovery console; it does not leak a second allocation.
  If display <> 0
    If Pi3FbInit(pi3_dtb, pi3_dtb_end, pi3_ram_base, pi3_ram_end) = 0 : Pi3SayFramebufferError(Pi3FbError()) : EndIf
  EndIf
  Pi3Say("Anvil Pi3 A/B boot: validated memory, SDHOST next")
  Pi3PrintBuild()
  ProcedureReturn 1
EndProcedure

; The whole cold sequence, for the running candidate, which has no window to
; offer and inherits the loader's trial watchdog.
Procedure.i Pi3UpdateBootStart(display.i)
  If Pi3UpdateBootBegin(display) = 0 : ProcedureReturn 0 : EndIf
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

Procedure.i Pi3LoaderBootMemory()
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

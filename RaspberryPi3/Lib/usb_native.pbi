; Original BCM2837 DWC2 native adapter. Include timer/mailbox first.
; Facts only: raspberrypi/linux 7d1826930811232688a50c99c540fbb137aed081,
; BCM2835 ARM Peripherals address map and Raspberry Pi firmware property wiki.
; No external implementation code copied.
; BCM283x peripheral bus 0x7e980000 -> Pi3 ARM physical 0x3f980000.
; Cold, serialized primary owner only: EL2/EL3, DAIF masked, MMU/cache off.
; A device access can stall the interconnect: loop bounds cannot cure that.
#PI3_USB_BASE = $3F980000
Global p3usb_native_power.i
Global p3usb_native_error.i
Global Dim p3usb_power_packet.l[12]

Procedure.i Pi3UsbNativeContext()
  ASM
    mrs x0, mpidr_el1
    movz x1, #65535
    movk x1, #255, lsl #16
    and x1, x0, x1
    cbnz x1, p3usb_context_bad
    lsr x0, x0, #32
    movz x1, #255
    and x0, x0, x1
    cbnz x0, p3usb_context_bad
    mrs x0, daif
    movz x1, #960
    and x0, x0, x1
    cmp x0, #960
    b.ne p3usb_context_bad
    mrs x0, currentel
    cmp x0, #8
    b.eq p3usb_context_el2
    cmp x0, #12
    b.ne p3usb_context_bad
    mrs x0, sctlr_el3
    b p3usb_context_check
p3usb_context_el2:
    mrs x0, sctlr_el2
p3usb_context_check:
    movz x1, #5
    and x0, x0, x1
    cbnz x0, p3usb_context_bad
    movz x0, #1
    b p3usb_context_done
p3usb_context_bad:
    movz x0, #0
p3usb_context_done:
  EndASM
  ProcedureReturn
EndProcedure

Procedure.i Pi3UsbPowerAcquire()
  Protected buffer.i=(@p3usb_power_packet[0]+15)&~15
  If p3usb_native_error<>0 Or Pi3UsbNativeContext()=0
    p3usb_native_error=-20
    ProcedureReturn 0
  EndIf
  If p3usb_native_power=1
  ProcedureReturn 1
  EndIf
  ; Old firmware USB power domain 3, SET_POWER_STATE with ON+WAIT.
  ; Never power-cycle a live controller or switch off firmware-owned power.
  PokeL(buffer,32)
  PokeL(buffer+4,0)
  PokeL(buffer+8,$28001)
  PokeL(buffer+12,8)
  PokeL(buffer+16,8)
  PokeL(buffer+20,3)
  PokeL(buffer+24,3)
  PokeL(buffer+28,0)
  If Pi3MailboxCall(buffer,32)=0
    p3usb_native_error=-21
    ProcedureReturn 0
  EndIf
  If PeekL(buffer+8)<>$28001 Or PeekL(buffer+12)<>8 Or (PeekL(buffer+16)&$FFFFFFFF)<>$80000008 Or PeekL(buffer+20)<>3 Or (PeekL(buffer+24)&3)<>1
    p3usb_native_error=-21
    ProcedureReturn 0
  EndIf
  p3usb_native_power=1
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3UsbRead(offset.i)
  Protected value.i
  If p3usb_native_power<>1 Or p3usb_native_error<>0 Or offset<0 Or offset>$FFC Or (offset&3)<>0 Or Pi3UsbNativeContext()=0
    p3usb_native_error=-22
    ProcedureReturn -1
  EndIf
  ASM
    dsb sy
    isb
  EndASM
  value=PeekL(#PI3_USB_BASE+offset)&$FFFFFFFF
  ASM
    dsb sy
    isb
  EndASM
  ProcedureReturn value
EndProcedure

Procedure Pi3UsbWrite(offset.i,value.i)
  If p3usb_native_power<>1 Or p3usb_native_error<>0 Or offset<0 Or offset>$FFC Or (offset&3)<>0 Or Pi3UsbNativeContext()=0
    p3usb_native_error=-22
    ProcedureReturn
  EndIf
  ASM
    dsb sy
    isb
  EndASM
  PokeL(#PI3_USB_BASE+offset,value)
  ASM
    dsb sy
    isb
  EndASM
EndProcedure

Procedure.i Pi3UsbTime()
  ProcedureReturn Pi3Micros()
EndProcedure

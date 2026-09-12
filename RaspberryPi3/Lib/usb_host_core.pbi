; Original BCM2837 DWC2 register-state foundation, not an enumerating host.
; Facts: raspberrypi/linux 7d1826930811232688a50c99c540fbb137aed081
; drivers/usb/dwc2/hw.h and core.c. No implementation code copied.
; Caller supplies serialized Pi3UsbRead(offset), Pi3UsbWrite(offset,value),
; Pi3UsbTime() microseconds. Services must use ordered MMIO; no IRQ reentry.
; Requires exclusive cold ownership, clocks/power and valid MMIO established.
; Refuses already enabled DMA/interrupts or active channels; never seizes them.
Global p3usb_state.i
Global p3usb_error.i
Global p3usb_planned_packets.i

#P3_USB_HC_XFER_COMPLETE = $0001
#P3_USB_HC_HALTED        = $0002
#P3_USB_HC_AHB_ERROR     = $0004
#P3_USB_HC_STALL         = $0008
#P3_USB_HC_NAK           = $0010
#P3_USB_HC_ACK           = $0020
#P3_USB_HC_NYET          = $0040
#P3_USB_HC_XACT_ERROR    = $0080
#P3_USB_HC_BABBLE        = $0100
#P3_USB_HC_FRAME_OVERRUN = $0200
#P3_USB_HC_TOGGLE_ERROR  = $0400

; Return the stable control bits for HPRT0.  Connection, enable and
; over-current change bits are write-one-to-clear and therefore must never be
; reflected by an ordinary read/modify/write.  Linux's dwc2_read_hprt0 applies
; the same ownership rule at its register boundary.
Procedure.i Pi3UsbPortControl(current.i,setMask.i,clearMask.i)
  Protected writable.i=$000011C0 ; power, reset, suspend and resume only
  Protected value.i=current & $FFFFFFFF
  value=value & $FFFFFFD5 ; strip CONNDET, ENACHG and OVRCURRCHG
  value=value & ~(clearMask & writable)
  value=value | (setMask & writable)
  ProcedureReturn value
EndProcedure

; Build HCCHAR without CHENA/CHDIS.  The transport submits that final state
; only after HCTSIZ and HCDMA are visible to the controller.
Procedure.i Pi3UsbChannelCharWord(deviceAddress.i,endpointAddress.i,endpointType.i,maxPacket.i,lowSpeed.i)
  Protected result.i
  p3usb_error=0
  If deviceAddress<0 Or deviceAddress>127 Or endpointAddress<0 Or endpointAddress>255
    p3usb_error=-6 : ProcedureReturn -1
  EndIf
  If endpointType<0 Or endpointType>3 Or maxPacket<1 Or maxPacket>1024
    p3usb_error=-6 : ProcedureReturn -1
  EndIf
  If lowSpeed<>0 And lowSpeed<>1 : p3usb_error=-6 : ProcedureReturn -1 : EndIf
  If (endpointAddress & $70)<>0 : p3usb_error=-6 : ProcedureReturn -1 : EndIf
  result=(deviceAddress << 22) | (endpointType << 18) | ((endpointAddress & 15) << 11) | maxPacket
  If endpointAddress & $80 : result=result | $00008000 : EndIf
  If lowSpeed : result=result | $00020000 : EndIf
  ProcedureReturn result
EndProcedure

; BCM2835 parameters in the pinned Raspberry Pi driver cap one submission at
; 65,535 bytes and 511 packets.  Zero-length status stages still consume one
; transaction packet.
Procedure.i Pi3UsbChannelSizeWord(byteCount.i,maxPacket.i,pid.i)
  Protected packets.i
  p3usb_error=0 : p3usb_planned_packets=0
  If byteCount<0 Or byteCount>65535 Or maxPacket<1 Or maxPacket>1024 Or pid<0 Or pid>3
    p3usb_error=-6 : ProcedureReturn -1
  EndIf
  packets=1
  If byteCount>0 : packets=(byteCount+maxPacket-1)/maxPacket : EndIf
  If packets>511 : p3usb_error=-6 : ProcedureReturn -1 : EndIf
  p3usb_planned_packets=packets
  ProcedureReturn byteCount | (packets << 19) | (pid << 29)
EndProcedure

; Decode a channel halt without hiding a fatal condition behind NAK retry.
;  1 = complete, 0 = retryable NAK/NYET, negative = named transport failure.
Procedure.i Pi3UsbChannelHaltStatus(interrupts.i)
  If (interrupts & #P3_USB_HC_HALTED)=0 : ProcedureReturn -6 : EndIf
  If interrupts & #P3_USB_HC_AHB_ERROR : ProcedureReturn -7 : EndIf
  If interrupts & #P3_USB_HC_STALL : ProcedureReturn -8 : EndIf
  If interrupts & #P3_USB_HC_BABBLE : ProcedureReturn -9 : EndIf
  If interrupts & (#P3_USB_HC_XACT_ERROR | #P3_USB_HC_FRAME_OVERRUN | #P3_USB_HC_TOGGLE_ERROR)
    ProcedureReturn -10
  EndIf
  If interrupts & (#P3_USB_HC_NAK | #P3_USB_HC_NYET) : ProcedureReturn 0 : EndIf
  If interrupts & #P3_USB_HC_XFER_COMPLETE : ProcedureReturn 1 : EndIf
  ProcedureReturn -11
EndProcedure

Procedure.i Pi3UsbWait(mask.i, expected.i)
  Protected began.i=Pi3UsbTime()
  Protected now.i
  Protected n.i
  If began<0 : ProcedureReturn 0 : EndIf
  For n=0 To 999999
    If (Pi3UsbRead($10) & mask)=expected : ProcedureReturn 1 : EndIf
    now=Pi3UsbTime()
    If now<began Or now-began>=10000 : ProcedureReturn 0 : EndIf
  Next
  ProcedureReturn 0
EndProcedure

Procedure.i Pi3UsbCoreReset()
  Protected ident.i
  Protected channels.i
  Protected n.i
  Protected cfg.i
  p3usb_error=0
  If p3usb_state<>0 : p3usb_error=-1 : ProcedureReturn 0 : EndIf
  ident=Pi3UsbRead($40)
  ; This first backend deliberately excludes the 4.20 reset-done protocol.
  If (ident & $FFFF0000)<>$4F540000 Or (ident & $FFFF)>=$420A
    p3usb_error=-2 : ProcedureReturn 0
  EndIf
  cfg=Pi3UsbRead($08)
  If (cfg & $21)<>0 : p3usb_error=-3 : ProcedureReturn 0 : EndIf
  channels=((Pi3UsbRead($48)>>14)&15)+1
  For n=0 To channels-1
    If (Pi3UsbRead($500+n*$20) & $80000000)<>0
      p3usb_error=-3 : ProcedureReturn 0
    EndIf
  Next
  If Pi3UsbWait($80000000,$80000000)=0
    p3usb_error=-4 : ProcedureReturn 0
  EndIf
  ; Crossing this write permanently consumes cold ownership, even on timeout.
  p3usb_state=-1
  Pi3UsbWrite($10,1)
  If Pi3UsbWait(1,0)=0 Or Pi3UsbWait($80000000,$80000000)=0
    p3usb_error=-5 : ProcedureReturn 0
  EndIf
  p3usb_state=1
  ProcedureReturn 1
EndProcedure

; Text for these codes belongs at the console boundary.  PureMetal targets do
; not return strings, so the hardware library exports the exact numeric cause
; rather than a host-only Procedure.s that can never be emitted.
Procedure.i Pi3UsbCoreErrorCode()
  ProcedureReturn p3usb_error
EndProcedure

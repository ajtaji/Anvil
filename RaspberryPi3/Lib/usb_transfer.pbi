; Serialized, polling DWC2 buffer-DMA channel transport for the Pi 3.
; It owns one host channel only for the duration of one submitted transaction.
; The caller supplies a validated 32-bit DMA bus address in resident, coherent
; memory.  This library never converts an arbitrary CPU pointer into a bus
; address and never retries NAK/NYET behind the scheduler's back.

Global p3usb_transfer_owner.i
Global p3usb_transfer_actual.i
Global p3usb_transfer_next_pid.i

Procedure.i Pi3UsbChannelRegister(channel.i,registerOffset.i)
  ProcedureReturn $500+channel*$20+registerOffset
EndProcedure

Procedure.i Pi3UsbChannelTransfer(channel.i,deviceAddress.i,endpointAddress.i,endpointType.i,maxPacket.i,lowSpeed.i,dmaBusAddress.i,byteCount.i,pid.i,timeoutUs.i)
  Protected hcchar.i
  Protected hctsiz.i
  Protected began.i
  Protected now.i
  Protected interrupts.i
  Protected remaining.i
  Protected status.i
  Protected loops.i
  p3usb_transfer_actual=0 : p3usb_transfer_next_pid=pid
  If p3usb_state<>1 Or p3usb_transfer_owner<>0
    p3usb_error=-1 : ProcedureReturn -1
  EndIf
  If channel<0 Or channel>15 Or dmaBusAddress<0 Or dmaBusAddress>$FFFFFFFF Or (dmaBusAddress & 3)<>0
    p3usb_error=-6 : ProcedureReturn -6
  EndIf
  If byteCount>0 And dmaBusAddress=0 : p3usb_error=-6 : ProcedureReturn -6 : EndIf
  If timeoutUs<1 Or timeoutUs>10000000 : p3usb_error=-6 : ProcedureReturn -6 : EndIf
  hcchar=Pi3UsbChannelCharWord(deviceAddress,endpointAddress,endpointType,maxPacket,lowSpeed)
  If hcchar<0 : ProcedureReturn -6 : EndIf
  hctsiz=Pi3UsbChannelSizeWord(byteCount,maxPacket,pid)
  If hctsiz<0 : ProcedureReturn -6 : EndIf
  began=Pi3UsbTime()
  If began<0 : p3usb_error=-12 : ProcedureReturn -12 : EndIf
  p3usb_transfer_owner=channel+1
  Pi3UsbWrite(Pi3UsbChannelRegister(channel,8),$000007FF)
  Pi3UsbWrite(Pi3UsbChannelRegister(channel,4),0)
  Pi3UsbWrite(Pi3UsbChannelRegister(channel,16),hctsiz)
  Pi3UsbWrite(Pi3UsbChannelRegister(channel,20),dmaBusAddress)
  Pi3UsbWrite(Pi3UsbChannelRegister(channel,0),hcchar | $80000000)
  For loops=0 To 9999999
    interrupts=Pi3UsbRead(Pi3UsbChannelRegister(channel,8))
    If interrupts & #P3_USB_HC_HALTED
      remaining=Pi3UsbRead(Pi3UsbChannelRegister(channel,16))
      p3usb_transfer_actual=byteCount-(remaining & $7FFFF)
      If p3usb_transfer_actual<0 Or p3usb_transfer_actual>byteCount
        p3usb_transfer_actual=0 : p3usb_error=-11 : status=-11
      Else
        p3usb_transfer_next_pid=(remaining >> 29) & 3
        status=Pi3UsbChannelHaltStatus(interrupts)
        If status<0 : p3usb_error=status : EndIf
      EndIf
      Pi3UsbWrite(Pi3UsbChannelRegister(channel,8),interrupts & $000007FF)
      p3usb_transfer_owner=0
      ProcedureReturn status
    EndIf
    now=Pi3UsbTime()
    If now<began Or now-began>=timeoutUs
      ; DWC2 channel halt is CHDIS+CHENA.  The channel remains unavailable
      ; until hardware acknowledges by clearing CHENA; no second transfer may
      ; overlap this recovery.
      hcchar=Pi3UsbRead(Pi3UsbChannelRegister(channel,0))
      Pi3UsbWrite(Pi3UsbChannelRegister(channel,0),hcchar | $C0000000)
      For remaining=0 To 99999
        If (Pi3UsbRead(Pi3UsbChannelRegister(channel,0)) & $80000000)=0
          p3usb_transfer_owner=0 : p3usb_error=-12 : ProcedureReturn -12
        EndIf
      Next
      p3usb_error=-13
      ProcedureReturn -13
    EndIf
  Next
  p3usb_error=-13
  ProcedureReturn -13
EndProcedure

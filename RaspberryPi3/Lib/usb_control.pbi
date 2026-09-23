; Scheduler-owned USB control transfers above Pi3UsbChannelTransfer().
; One call to Pi3UsbControlStep() submits at most one bounded DWC2 channel
; transaction.  NAK/NYET is returned to the scheduler; this code never spins.
; PID encodings are DWC2 HCTSIZ values from the pinned Linux hw.h.
; Cross-checks: drivers/usb/dwc2/hw.h and v2025.01_uboot_usb.c.

#P3_USB_PID_DATA1 = 2
#P3_USB_PID_SETUP = 3

#P3_USB_CONTROL_IDLE     = 0
#P3_USB_CONTROL_SETUP    = 1
#P3_USB_CONTROL_DATA     = 2
#P3_USB_CONTROL_STATUS   = 3
#P3_USB_CONTROL_COMPLETE = 4
#P3_USB_CONTROL_FAILED   = -1

#P3_USB_CONTROL_PROGRESS = 1
#P3_USB_CONTROL_DONE     = 2
#P3_USB_CONTROL_RETRY    = 3

Global p3usb_control_phase.i
Global p3usb_control_error.i
Global p3usb_control_channel.i
Global p3usb_control_device.i
Global p3usb_control_max_packet.i
Global p3usb_control_low_speed.i
Global p3usb_control_setup_cpu.i
Global p3usb_control_setup_bus.i
Global p3usb_control_data_cpu.i
Global p3usb_control_data_bus.i
Global p3usb_control_length.i
Global p3usb_control_actual.i
Global p3usb_control_data_offset.i
Global p3usb_control_data_remaining.i
Global p3usb_control_data_pid.i
Global p3usb_control_direction_in.i
Global p3usb_control_timeout_us.i
Global p3usb_control_retries_left.i

Procedure.i Pi3UsbControlFail(code.i)
  p3usb_control_error=code
  p3usb_control_phase=#P3_USB_CONTROL_FAILED
  ProcedureReturn code
EndProcedure

Procedure.i Pi3UsbControlBegin(channel.i,device.i,maxPacket.i,lowSpeed.i,setupCpu.i,setupBus.i,dataCpu.i,dataBus.i,retryBudget.i,timeoutUs.i)
  Protected length.i
  p3usb_control_error=0 : p3usb_control_actual=0
  p3usb_control_data_offset=0 : p3usb_control_data_remaining=0
  p3usb_control_data_pid=#P3_USB_PID_DATA1
  p3usb_control_phase=#P3_USB_CONTROL_IDLE
  If channel<0 Or channel>15 Or device<0 Or device>127
    ProcedureReturn Pi3UsbControlFail(-20)
  EndIf
  If maxPacket<>8 And maxPacket<>16 And maxPacket<>32 And maxPacket<>64
    ProcedureReturn Pi3UsbControlFail(-20)
  EndIf
  If lowSpeed<>0 And lowSpeed<>1 : ProcedureReturn Pi3UsbControlFail(-20) : EndIf
  If setupCpu=0 Or setupBus<=0 Or setupBus>$FFFFFFFF Or (setupBus & 3)<>0
    ProcedureReturn Pi3UsbControlFail(-20)
  EndIf
  length=Pi3UsbReadLe16(setupCpu+6)
  If length<0 Or length>$FFFF : ProcedureReturn Pi3UsbControlFail(-20) : EndIf
  If length>0
    If dataCpu=0 Or dataBus<=0 Or dataBus>$FFFFFFFF Or (dataBus & 3)<>0
      ProcedureReturn Pi3UsbControlFail(-20)
    EndIf
  EndIf
  If retryBudget<0 Or retryBudget>100 Or timeoutUs<1 Or timeoutUs>10000000
    ProcedureReturn Pi3UsbControlFail(-20)
  EndIf
  p3usb_control_channel=channel : p3usb_control_device=device
  p3usb_control_max_packet=maxPacket : p3usb_control_low_speed=lowSpeed
  p3usb_control_setup_cpu=setupCpu : p3usb_control_setup_bus=setupBus
  p3usb_control_data_cpu=dataCpu : p3usb_control_data_bus=dataBus
  p3usb_control_length=length
  p3usb_control_data_remaining=length
  p3usb_control_direction_in=0
  If (PeekA(setupCpu) & $80)<>0 : p3usb_control_direction_in=1 : EndIf
  p3usb_control_timeout_us=timeoutUs
  p3usb_control_retries_left=retryBudget
  p3usb_control_phase=#P3_USB_CONTROL_SETUP
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3UsbControlTransferResult(result.i,required.i)
  If result=0
    ; SETUP and status are single packets (or zero length).  Partial progress
    ; cannot be resumed safely there and indicates a broken transport report.
    If p3usb_transfer_actual<>0 : ProcedureReturn Pi3UsbControlFail(-22) : EndIf
    If p3usb_control_retries_left=0
      ProcedureReturn Pi3UsbControlFail(-21)
    EndIf
    p3usb_control_retries_left-1
    ProcedureReturn #P3_USB_CONTROL_RETRY
  EndIf
  If result<0 : ProcedureReturn Pi3UsbControlFail(result) : EndIf
  If p3usb_transfer_actual<>required
    ProcedureReturn Pi3UsbControlFail(-22)
  EndIf
  ProcedureReturn #P3_USB_CONTROL_PROGRESS
EndProcedure

Procedure.i Pi3UsbControlStep()
  Protected result.i
  Protected checked.i
  Protected endpoint.i
  Select p3usb_control_phase
    Case #P3_USB_CONTROL_SETUP
      result=Pi3UsbChannelTransfer(p3usb_control_channel,p3usb_control_device,0,#P3_USB_EP_CONTROL,p3usb_control_max_packet,p3usb_control_low_speed,p3usb_control_setup_bus,8,#P3_USB_PID_SETUP,p3usb_control_timeout_us)
      checked=Pi3UsbControlTransferResult(result,8)
      If checked<>#P3_USB_CONTROL_PROGRESS : ProcedureReturn checked : EndIf
      If p3usb_control_length>0
        p3usb_control_phase=#P3_USB_CONTROL_DATA
      Else
        p3usb_control_phase=#P3_USB_CONTROL_STATUS
      EndIf
      ProcedureReturn #P3_USB_CONTROL_PROGRESS

    Case #P3_USB_CONTROL_DATA
      endpoint=0
      If p3usb_control_direction_in : endpoint=$80 : EndIf
      result=Pi3UsbChannelTransfer(p3usb_control_channel,p3usb_control_device,endpoint,#P3_USB_EP_CONTROL,p3usb_control_max_packet,p3usb_control_low_speed,p3usb_control_data_bus+p3usb_control_data_offset,p3usb_control_data_remaining,p3usb_control_data_pid,p3usb_control_timeout_us)
      If result=0
        If p3usb_transfer_actual<0 Or p3usb_transfer_actual>=p3usb_control_data_remaining
          ProcedureReturn Pi3UsbControlFail(-22)
        EndIf
        If p3usb_transfer_actual>0
          p3usb_control_data_offset+p3usb_transfer_actual
          p3usb_control_data_remaining-p3usb_transfer_actual
          If p3usb_transfer_next_pid<>0 And p3usb_transfer_next_pid<>#P3_USB_PID_DATA1
            ProcedureReturn Pi3UsbControlFail(-22)
          EndIf
          p3usb_control_data_pid=p3usb_transfer_next_pid
        EndIf
        If p3usb_control_retries_left=0 : ProcedureReturn Pi3UsbControlFail(-21) : EndIf
        p3usb_control_retries_left-1
        ProcedureReturn #P3_USB_CONTROL_RETRY
      EndIf
      If result<0 : ProcedureReturn Pi3UsbControlFail(result) : EndIf
      If p3usb_transfer_actual<0 Or p3usb_transfer_actual>p3usb_control_data_remaining
        ProcedureReturn Pi3UsbControlFail(-22)
      EndIf
      If p3usb_control_direction_in=0 And p3usb_transfer_actual<>p3usb_control_data_remaining
        ProcedureReturn Pi3UsbControlFail(-22)
      EndIf
      p3usb_control_data_offset+p3usb_transfer_actual
      p3usb_control_data_remaining-p3usb_transfer_actual
      p3usb_control_actual=p3usb_control_data_offset
      p3usb_control_phase=#P3_USB_CONTROL_STATUS
      ProcedureReturn #P3_USB_CONTROL_PROGRESS

    Case #P3_USB_CONTROL_STATUS
      ; Status direction is opposite the data stage.  For no-data standard
      ; requests the setup direction is OUT, therefore status is IN.
      endpoint=$80
      If p3usb_control_length>0 And p3usb_control_direction_in<>0 : endpoint=0 : EndIf
      result=Pi3UsbChannelTransfer(p3usb_control_channel,p3usb_control_device,endpoint,#P3_USB_EP_CONTROL,p3usb_control_max_packet,p3usb_control_low_speed,0,0,#P3_USB_PID_DATA1,p3usb_control_timeout_us)
      checked=Pi3UsbControlTransferResult(result,0)
      If checked<>#P3_USB_CONTROL_PROGRESS : ProcedureReturn checked : EndIf
      p3usb_control_phase=#P3_USB_CONTROL_COMPLETE
      ProcedureReturn #P3_USB_CONTROL_DONE

    Case #P3_USB_CONTROL_COMPLETE
      ProcedureReturn #P3_USB_CONTROL_DONE
  EndSelect
  ProcedureReturn Pi3UsbControlFail(-23)
EndProcedure

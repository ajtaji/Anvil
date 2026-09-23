; Controller-independent, scheduler-stepped enumeration of the Pi 3's fixed
; LAN9514 topology: root port 1 -> 0424:9514 hub -> port 1 -> 0424:ec00 LAN.
; The pinned bcm283x-rpi-smsc9514.dtsi is the topology authority.  USB request,
; delay and status rules follow the pinned Linux 6.12 and U-Boot 2025.01 files.

#P3_USB_ENUM_PROGRESS = 1
#P3_USB_ENUM_RETRY    = 2
#P3_USB_ENUM_WAIT     = 3
#P3_USB_ENUM_READY    = 4

#P3_USB_ENUM_HUB_ADDRESS = 1
#P3_USB_ENUM_LAN_ADDRESS = 2
#P3_USB_ENUM_PORT        = 1
#P3_USB_ENUM_CONFIG_MAX  = 512

#P3_USB_PORT_CONNECTION = $0001
#P3_USB_PORT_ENABLE     = $0002
#P3_USB_PORT_OVERCURRENT = $0008
#P3_USB_PORT_RESET      = $0010
#P3_USB_PORT_POWER      = $0100
#P3_USB_PORT_LOW_SPEED  = $0200
#P3_USB_PORT_HIGH_SPEED = $0400
#P3_USB_PORT_C_CONNECTION = $0001
#P3_USB_PORT_C_ENABLE     = $0002
#P3_USB_PORT_C_RESET      = $0010
#P3_USB_HUB_C_CONNECTION  = 16
#P3_USB_HUB_C_ENABLE      = 17
#P3_USB_HUB_C_RESET       = 20

#P3_USB_ENUM_IDLE = 0
#P3_USB_ENUM_HUB8_BEGIN = 10
#P3_USB_ENUM_HUB8_WAIT = 11
#P3_USB_ENUM_HUB_ADDR_BEGIN = 12
#P3_USB_ENUM_HUB_ADDR_WAIT = 13
#P3_USB_ENUM_HUB_ADDR_SETTLE = 14
#P3_USB_ENUM_HUB18_BEGIN = 15
#P3_USB_ENUM_HUB18_WAIT = 16
#P3_USB_ENUM_HUB_CFG9_BEGIN = 17
#P3_USB_ENUM_HUB_CFG9_WAIT = 18
#P3_USB_ENUM_HUB_CFG_BEGIN = 19
#P3_USB_ENUM_HUB_CFG_WAIT = 20
#P3_USB_ENUM_HUB_SET_CFG_BEGIN = 21
#P3_USB_ENUM_HUB_SET_CFG_WAIT = 22
#P3_USB_ENUM_HUB_DESC_BEGIN = 23
#P3_USB_ENUM_HUB_DESC_WAIT = 24
#P3_USB_ENUM_PORT_POWER_BEGIN = 25
#P3_USB_ENUM_PORT_POWER_WAIT = 26
#P3_USB_ENUM_PORT_POWER_SETTLE = 27
#P3_USB_ENUM_PORT_STATUS_BEGIN = 28
#P3_USB_ENUM_PORT_STATUS_WAIT = 29
#P3_USB_ENUM_PORT_RESET_BEGIN = 30
#P3_USB_ENUM_PORT_RESET_WAIT = 31
#P3_USB_ENUM_PORT_RESET_SETTLE = 32
#P3_USB_ENUM_PORT_RESET_STATUS_BEGIN = 33
#P3_USB_ENUM_PORT_RESET_STATUS_WAIT = 34
#P3_USB_ENUM_CLEAR_RESET_BEGIN = 35
#P3_USB_ENUM_CLEAR_RESET_WAIT = 36
#P3_USB_ENUM_CLEAR_CONNECT_BEGIN = 37
#P3_USB_ENUM_CLEAR_CONNECT_WAIT = 38
#P3_USB_ENUM_CLEAR_ENABLE_BEGIN = 39
#P3_USB_ENUM_CLEAR_ENABLE_WAIT = 390
#P3_USB_ENUM_LAN8_BEGIN = 40
#P3_USB_ENUM_LAN8_WAIT = 41
#P3_USB_ENUM_LAN_ADDR_BEGIN = 42
#P3_USB_ENUM_LAN_ADDR_WAIT = 43
#P3_USB_ENUM_LAN_ADDR_SETTLE = 44
#P3_USB_ENUM_LAN18_BEGIN = 45
#P3_USB_ENUM_LAN18_WAIT = 46
#P3_USB_ENUM_LAN_CFG9_BEGIN = 47
#P3_USB_ENUM_LAN_CFG9_WAIT = 48
#P3_USB_ENUM_LAN_CFG_BEGIN = 49
#P3_USB_ENUM_LAN_CFG_WAIT = 50
#P3_USB_ENUM_LAN_SET_CFG_BEGIN = 51
#P3_USB_ENUM_LAN_SET_CFG_WAIT = 52
#P3_USB_ENUM_FINAL_STATUS_BEGIN = 53
#P3_USB_ENUM_FINAL_STATUS_WAIT = 54
#P3_USB_ENUM_PUBLISH = 55
#P3_USB_ENUM_COMPLETE = 100
#P3_USB_ENUM_FAILED = -1

Global p3usb_enum_state.i
Global p3usb_enum_error.i
Global p3usb_enum_wait_until.i
Global p3usb_enum_retry_budget.i
Global p3usb_enum_poll_budget.i
Global p3usb_enum_polls_left.i
Global p3usb_enum_channel.i
Global p3usb_enum_setup_cpu.i
Global p3usb_enum_setup_bus.i
Global p3usb_enum_data_cpu.i
Global p3usb_enum_data_bus.i
Global p3usb_enum_data_capacity.i
Global p3usb_enum_timeout_us.i
Global p3usb_enum_ep0_mps.i
Global p3usb_enum_hub_address.i
Global p3usb_enum_lan_address.i
Global p3usb_enum_hub_configuration.i
Global p3usb_enum_lan_configuration.i
Global p3usb_enum_hub_ports.i
Global p3usb_enum_root_port_status.i
Global p3usb_enum_hub_port_status.i
Global p3usb_enum_hub_port_change.i
Global p3usb_enum_candidate_interface.i
Global p3usb_enum_candidate_bulk_in.i
Global p3usb_enum_candidate_bulk_out.i
Global p3usb_enum_candidate_interrupt_in.i
Global p3usb_enum_candidate_bulk_in_mps.i
Global p3usb_enum_candidate_bulk_out_mps.i
Global p3usb_enum_candidate_interrupt_mps.i

Procedure.i Pi3UsbEnumFail(code.i)
  p3usb_enum_error=code
  p3usb_enum_state=#P3_USB_ENUM_FAILED
  ; An incomplete or disconnected walk never leaves a usable endpoint set.
  p3usb_lan_configuration=0 : p3usb_lan_interface=-1
  p3usb_lan_bulk_in=0 : p3usb_lan_bulk_out=0 : p3usb_lan_interrupt_in=0
  p3usb_lan_bulk_in_mps=0 : p3usb_lan_bulk_out_mps=0 : p3usb_lan_interrupt_mps=0
  ProcedureReturn code
EndProcedure

Procedure.i Pi3UsbEnumBeginControl(nextState.i,device.i,maxPacket.i)
  If Pi3UsbControlBegin(p3usb_enum_channel,device,maxPacket,0,p3usb_enum_setup_cpu,p3usb_enum_setup_bus,p3usb_enum_data_cpu,p3usb_enum_data_bus,p3usb_enum_retry_budget,p3usb_enum_timeout_us)<>1
    ProcedureReturn Pi3UsbEnumFail(p3usb_control_error)
  EndIf
  p3usb_enum_state=nextState
  ProcedureReturn #P3_USB_ENUM_PROGRESS
EndProcedure

Procedure.i Pi3UsbEnumControlStatus()
  Protected result.i=Pi3UsbControlStep()
  If result=#P3_USB_CONTROL_RETRY : ProcedureReturn #P3_USB_ENUM_RETRY : EndIf
  If result=#P3_USB_CONTROL_DONE : ProcedureReturn 0 : EndIf
  If result=#P3_USB_CONTROL_PROGRESS : ProcedureReturn #P3_USB_ENUM_PROGRESS : EndIf
  ProcedureReturn Pi3UsbEnumFail(result)
EndProcedure

Procedure.i Pi3UsbEnumConfigHeader(length.i)
  Protected total.i
  If length<9 Or (PeekA(p3usb_enum_data_cpu) & 255)<9 Or (PeekA(p3usb_enum_data_cpu+1) & 255)<>#P3_USB_DESC_CONFIGURATION
    ProcedureReturn Pi3UsbEnumFail(-31)
  EndIf
  total=Pi3UsbReadLe16(p3usb_enum_data_cpu+2)
  If total<9 Or total>p3usb_enum_data_capacity Or (PeekA(p3usb_enum_data_cpu+5) & 255)=0
    ProcedureReturn Pi3UsbEnumFail(-31)
  EndIf
  ProcedureReturn total
EndProcedure

Procedure.i Pi3UsbEnumHubConfig(length.i)
  Protected total.i=Pi3UsbEnumConfigHeader(length)
  Protected offset.i
  Protected size.i
  Protected kind.i
  Protected active.i
  Protected hubInterfaces.i
  Protected interruptIn.i
  If total<0 Or length<total : ProcedureReturn Pi3UsbEnumFail(-31) : EndIf
  offset=PeekA(p3usb_enum_data_cpu) & 255
  While offset<total
    If total-offset<2 : ProcedureReturn Pi3UsbEnumFail(-31) : EndIf
    size=PeekA(p3usb_enum_data_cpu+offset) & 255
    kind=PeekA(p3usb_enum_data_cpu+offset+1) & 255
    If size<2 Or size>total-offset : ProcedureReturn Pi3UsbEnumFail(-31) : EndIf
    If kind=#P3_USB_DESC_INTERFACE
      If size<9 : ProcedureReturn Pi3UsbEnumFail(-31) : EndIf
      active=0
      If (PeekA(p3usb_enum_data_cpu+offset+3) & 255)=0 And (PeekA(p3usb_enum_data_cpu+offset+5) & 255)=9
        active=1 : hubInterfaces+1
      EndIf
    ElseIf kind=#P3_USB_DESC_ENDPOINT And active<>0
      If size<7 : ProcedureReturn Pi3UsbEnumFail(-31) : EndIf
      If ((PeekA(p3usb_enum_data_cpu+offset+2) & $80)<>0) And ((PeekA(p3usb_enum_data_cpu+offset+3) & 3)=#P3_USB_EP_INTERRUPT)
        If (Pi3UsbReadLe16(p3usb_enum_data_cpu+offset+4) & $7FF)=0 : ProcedureReturn Pi3UsbEnumFail(-31) : EndIf
        interruptIn+1
      EndIf
    EndIf
    offset+size
  Wend
  If offset<>total Or hubInterfaces<>1 Or interruptIn<>1 : ProcedureReturn Pi3UsbEnumFail(-31) : EndIf
  p3usb_enum_hub_configuration=PeekA(p3usb_enum_data_cpu+5) & 255
  ProcedureReturn 1
EndProcedure

; Parse into private candidates.  Nothing becomes driver-visible until the
; configured child passes a final hub-port connection/status check.
Procedure.i Pi3UsbEnumLanConfig(length.i)
  Protected total.i=Pi3UsbEnumConfigHeader(length)
  Protected offset.i
  Protected size.i
  Protected kind.i
  Protected active.i
  Protected vendorInterfaces.i
  Protected ep.i
  Protected attributes.i
  Protected mps.i
  p3usb_enum_candidate_interface=-1
  p3usb_enum_candidate_bulk_in=0 : p3usb_enum_candidate_bulk_out=0
  p3usb_enum_candidate_interrupt_in=0
  p3usb_enum_candidate_bulk_in_mps=0 : p3usb_enum_candidate_bulk_out_mps=0
  p3usb_enum_candidate_interrupt_mps=0
  If total<0 Or length<total : ProcedureReturn Pi3UsbEnumFail(-31) : EndIf
  p3usb_enum_lan_configuration=PeekA(p3usb_enum_data_cpu+5) & 255
  offset=PeekA(p3usb_enum_data_cpu) & 255
  While offset<total
    If total-offset<2 : ProcedureReturn Pi3UsbEnumFail(-31) : EndIf
    size=PeekA(p3usb_enum_data_cpu+offset) & 255
    kind=PeekA(p3usb_enum_data_cpu+offset+1) & 255
    If size<2 Or size>total-offset : ProcedureReturn Pi3UsbEnumFail(-31) : EndIf
    If kind=#P3_USB_DESC_INTERFACE
      If size<9 : ProcedureReturn Pi3UsbEnumFail(-31) : EndIf
      active=0
      If (PeekA(p3usb_enum_data_cpu+offset+3) & 255)=0 And (PeekA(p3usb_enum_data_cpu+offset+5) & 255)=$FF
        active=1 : vendorInterfaces+1
        p3usb_enum_candidate_interface=PeekA(p3usb_enum_data_cpu+offset+2) & 255
      EndIf
    ElseIf kind=#P3_USB_DESC_ENDPOINT And active<>0
      If size<7 : ProcedureReturn Pi3UsbEnumFail(-31) : EndIf
      ep=PeekA(p3usb_enum_data_cpu+offset+2) & 255
      attributes=(PeekA(p3usb_enum_data_cpu+offset+3) & 255) & 3
      mps=Pi3UsbReadLe16(p3usb_enum_data_cpu+offset+4) & $7FF
      If mps=0 Or mps>512 : ProcedureReturn Pi3UsbEnumFail(-31) : EndIf
      If attributes=#P3_USB_EP_BULK
        If (ep & $80)<>0
          If p3usb_enum_candidate_bulk_in<>0 : ProcedureReturn Pi3UsbEnumFail(-31) : EndIf
          p3usb_enum_candidate_bulk_in=ep : p3usb_enum_candidate_bulk_in_mps=mps
        Else
          If p3usb_enum_candidate_bulk_out<>0 : ProcedureReturn Pi3UsbEnumFail(-31) : EndIf
          p3usb_enum_candidate_bulk_out=ep : p3usb_enum_candidate_bulk_out_mps=mps
        EndIf
      ElseIf attributes=#P3_USB_EP_INTERRUPT And (ep & $80)<>0
        If p3usb_enum_candidate_interrupt_in<>0 : ProcedureReturn Pi3UsbEnumFail(-31) : EndIf
        p3usb_enum_candidate_interrupt_in=ep : p3usb_enum_candidate_interrupt_mps=mps
      EndIf
    EndIf
    offset+size
  Wend
  If offset<>total Or vendorInterfaces<>1 Or p3usb_enum_candidate_bulk_in=0 Or p3usb_enum_candidate_bulk_out=0
    ProcedureReturn Pi3UsbEnumFail(-31)
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3UsbEnumerationBegin(rootPortStatus.i,channel.i,setupCpu.i,setupBus.i,dataCpu.i,dataBus.i,dataCapacity.i,retryBudget.i,pollBudget.i,timeoutUs.i)
  p3usb_enum_error=0 : p3usb_enum_state=#P3_USB_ENUM_IDLE
  p3usb_enum_hub_address=0 : p3usb_enum_lan_address=0
  p3usb_lan_configuration=0 : p3usb_lan_interface=-1
  p3usb_lan_bulk_in=0 : p3usb_lan_bulk_out=0 : p3usb_lan_interrupt_in=0
  p3usb_lan_bulk_in_mps=0 : p3usb_lan_bulk_out_mps=0 : p3usb_lan_interrupt_mps=0
  If (rootPortStatus & (#P3_USB_PORT_CONNECTION | #P3_USB_PORT_ENABLE | #P3_USB_PORT_HIGH_SPEED))<>(#P3_USB_PORT_CONNECTION | #P3_USB_PORT_ENABLE | #P3_USB_PORT_HIGH_SPEED)
    ProcedureReturn Pi3UsbEnumFail(-30)
  EndIf
  If (rootPortStatus & #P3_USB_PORT_LOW_SPEED)<>0 : ProcedureReturn Pi3UsbEnumFail(-30) : EndIf
  If channel<0 Or channel>15 Or setupCpu=0 Or dataCpu=0 Or setupBus<=0 Or dataBus<=0 Or setupBus>$FFFFFFFF Or dataBus>$FFFFFFFF Or (setupBus & 3)<>0 Or (dataBus & 3)<>0
    ProcedureReturn Pi3UsbEnumFail(-30)
  EndIf
  If dataCapacity<#P3_USB_ENUM_CONFIG_MAX Or retryBudget<0 Or retryBudget>100 Or pollBudget<1 Or pollBudget>100 Or timeoutUs<1 Or timeoutUs>10000000
    ProcedureReturn Pi3UsbEnumFail(-30)
  EndIf
  p3usb_enum_root_port_status=rootPortStatus
  p3usb_enum_channel=channel : p3usb_enum_setup_cpu=setupCpu : p3usb_enum_setup_bus=setupBus
  p3usb_enum_data_cpu=dataCpu : p3usb_enum_data_bus=dataBus : p3usb_enum_data_capacity=dataCapacity
  p3usb_enum_retry_budget=retryBudget : p3usb_enum_poll_budget=pollBudget : p3usb_enum_polls_left=pollBudget
  p3usb_enum_timeout_us=timeoutUs : p3usb_enum_ep0_mps=8
  p3usb_enum_state=#P3_USB_ENUM_HUB8_BEGIN
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3UsbEnumerationStep(nowUs.i)
  Protected result.i
  Protected total.i
  Protected delayUs.i
  Protected status.i
  Protected change.i
  If nowUs<0 : ProcedureReturn Pi3UsbEnumFail(-30) : EndIf
  Select p3usb_enum_state
    Case #P3_USB_ENUM_HUB8_BEGIN
      If Pi3UsbGetDescriptorSetup(p3usb_enum_setup_cpu,#P3_USB_DESC_DEVICE,0,8)<>1 : ProcedureReturn Pi3UsbEnumFail(-31) : EndIf
      ProcedureReturn Pi3UsbEnumBeginControl(#P3_USB_ENUM_HUB8_WAIT,0,8)
    Case #P3_USB_ENUM_HUB8_WAIT
      result=Pi3UsbEnumControlStatus() : If result<>0 : ProcedureReturn result : EndIf
      If p3usb_control_actual<>8 Or (PeekA(p3usb_enum_data_cpu)&255)<8 Or (PeekA(p3usb_enum_data_cpu+1)&255)<>#P3_USB_DESC_DEVICE
        ProcedureReturn Pi3UsbEnumFail(-31)
      EndIf
      p3usb_enum_ep0_mps=PeekA(p3usb_enum_data_cpu+7)&255
      If p3usb_enum_ep0_mps<>64 : ProcedureReturn Pi3UsbEnumFail(-31) : EndIf
      p3usb_enum_state=#P3_USB_ENUM_HUB_ADDR_BEGIN : ProcedureReturn #P3_USB_ENUM_PROGRESS
    Case #P3_USB_ENUM_HUB_ADDR_BEGIN
      If Pi3UsbSetAddressSetup(p3usb_enum_setup_cpu,#P3_USB_ENUM_HUB_ADDRESS)<>1 : ProcedureReturn Pi3UsbEnumFail(-31) : EndIf
      ProcedureReturn Pi3UsbEnumBeginControl(#P3_USB_ENUM_HUB_ADDR_WAIT,0,p3usb_enum_ep0_mps)
    Case #P3_USB_ENUM_HUB_ADDR_WAIT
      result=Pi3UsbEnumControlStatus() : If result<>0 : ProcedureReturn result : EndIf
      p3usb_enum_hub_address=#P3_USB_ENUM_HUB_ADDRESS
      p3usb_enum_wait_until=nowUs+10000 : p3usb_enum_state=#P3_USB_ENUM_HUB_ADDR_SETTLE
      ProcedureReturn #P3_USB_ENUM_WAIT
    Case #P3_USB_ENUM_HUB_ADDR_SETTLE
      If nowUs<p3usb_enum_wait_until : ProcedureReturn #P3_USB_ENUM_WAIT : EndIf
      p3usb_enum_state=#P3_USB_ENUM_HUB18_BEGIN : ProcedureReturn #P3_USB_ENUM_PROGRESS
    Case #P3_USB_ENUM_HUB18_BEGIN
      If Pi3UsbGetDescriptorSetup(p3usb_enum_setup_cpu,#P3_USB_DESC_DEVICE,0,18)<>1 : ProcedureReturn Pi3UsbEnumFail(-31) : EndIf
      ProcedureReturn Pi3UsbEnumBeginControl(#P3_USB_ENUM_HUB18_WAIT,p3usb_enum_hub_address,p3usb_enum_ep0_mps)
    Case #P3_USB_ENUM_HUB18_WAIT
      result=Pi3UsbEnumControlStatus() : If result<>0 : ProcedureReturn result : EndIf
      If p3usb_control_actual<>18 Or Pi3UsbDeviceIs(p3usb_enum_data_cpu,18,#P3_USB_LAN_VID,#P3_USB_LAN_HUB_PID)<>1 Or (PeekA(p3usb_enum_data_cpu+4)&255)<>9 Or (PeekA(p3usb_enum_data_cpu+17)&255)=0
        ProcedureReturn Pi3UsbEnumFail(-31)
      EndIf
      p3usb_enum_state=#P3_USB_ENUM_HUB_CFG9_BEGIN : ProcedureReturn #P3_USB_ENUM_PROGRESS
    Case #P3_USB_ENUM_HUB_CFG9_BEGIN
      If Pi3UsbGetDescriptorSetup(p3usb_enum_setup_cpu,#P3_USB_DESC_CONFIGURATION,0,9)<>1 : ProcedureReturn Pi3UsbEnumFail(-31) : EndIf
      ProcedureReturn Pi3UsbEnumBeginControl(#P3_USB_ENUM_HUB_CFG9_WAIT,p3usb_enum_hub_address,p3usb_enum_ep0_mps)
    Case #P3_USB_ENUM_HUB_CFG9_WAIT
      result=Pi3UsbEnumControlStatus() : If result<>0 : ProcedureReturn result : EndIf
      total=Pi3UsbEnumConfigHeader(p3usb_control_actual) : If total<0 : ProcedureReturn total : EndIf
      Pi3UsbGetDescriptorSetup(p3usb_enum_setup_cpu,#P3_USB_DESC_CONFIGURATION,0,total)
      result=Pi3UsbEnumBeginControl(#P3_USB_ENUM_HUB_CFG_WAIT,p3usb_enum_hub_address,p3usb_enum_ep0_mps)
      If result<0 : ProcedureReturn result : EndIf
      p3usb_enum_state=#P3_USB_ENUM_HUB_CFG_WAIT : ProcedureReturn #P3_USB_ENUM_PROGRESS
    Case #P3_USB_ENUM_HUB_CFG_WAIT
      result=Pi3UsbEnumControlStatus() : If result<>0 : ProcedureReturn result : EndIf
      If Pi3UsbEnumHubConfig(p3usb_control_actual)<>1 : ProcedureReturn p3usb_enum_error : EndIf
      p3usb_enum_state=#P3_USB_ENUM_HUB_SET_CFG_BEGIN : ProcedureReturn #P3_USB_ENUM_PROGRESS
    Case #P3_USB_ENUM_HUB_SET_CFG_BEGIN
      Pi3UsbSetConfigurationSetup(p3usb_enum_setup_cpu,p3usb_enum_hub_configuration)
      ProcedureReturn Pi3UsbEnumBeginControl(#P3_USB_ENUM_HUB_SET_CFG_WAIT,p3usb_enum_hub_address,p3usb_enum_ep0_mps)
    Case #P3_USB_ENUM_HUB_SET_CFG_WAIT
      result=Pi3UsbEnumControlStatus() : If result<>0 : ProcedureReturn result : EndIf
      p3usb_enum_state=#P3_USB_ENUM_HUB_DESC_BEGIN : ProcedureReturn #P3_USB_ENUM_PROGRESS
    Case #P3_USB_ENUM_HUB_DESC_BEGIN
      Pi3UsbHubDescriptorSetup(p3usb_enum_setup_cpu,9)
      ProcedureReturn Pi3UsbEnumBeginControl(#P3_USB_ENUM_HUB_DESC_WAIT,p3usb_enum_hub_address,p3usb_enum_ep0_mps)
    Case #P3_USB_ENUM_HUB_DESC_WAIT
      result=Pi3UsbEnumControlStatus() : If result<>0 : ProcedureReturn result : EndIf
      p3usb_enum_hub_ports=Pi3UsbHubPortCount(p3usb_enum_data_cpu,p3usb_control_actual)
      If p3usb_enum_hub_ports<#P3_USB_ENUM_PORT : ProcedureReturn Pi3UsbEnumFail(-31) : EndIf
      delayUs=(PeekA(p3usb_enum_data_cpu+5)&255)*2000
      If delayUs<100000 : delayUs=100000 : EndIf
      p3usb_enum_wait_until=delayUs
      p3usb_enum_state=#P3_USB_ENUM_PORT_POWER_BEGIN : ProcedureReturn #P3_USB_ENUM_PROGRESS
    Case #P3_USB_ENUM_PORT_POWER_BEGIN
      Pi3UsbHubPortFeatureSetup(p3usb_enum_setup_cpu,#P3_USB_ENUM_PORT,#P3_USB_HUB_PORT_POWER,1)
      ProcedureReturn Pi3UsbEnumBeginControl(#P3_USB_ENUM_PORT_POWER_WAIT,p3usb_enum_hub_address,p3usb_enum_ep0_mps)
    Case #P3_USB_ENUM_PORT_POWER_WAIT
      result=Pi3UsbEnumControlStatus() : If result<>0 : ProcedureReturn result : EndIf
      p3usb_enum_wait_until=nowUs+p3usb_enum_wait_until
      p3usb_enum_state=#P3_USB_ENUM_PORT_POWER_SETTLE : ProcedureReturn #P3_USB_ENUM_WAIT
    Case #P3_USB_ENUM_PORT_POWER_SETTLE
      If nowUs<p3usb_enum_wait_until : ProcedureReturn #P3_USB_ENUM_WAIT : EndIf
      p3usb_enum_state=#P3_USB_ENUM_PORT_STATUS_BEGIN : ProcedureReturn #P3_USB_ENUM_PROGRESS
    Case #P3_USB_ENUM_PORT_STATUS_BEGIN
      Pi3UsbHubPortStatusSetup(p3usb_enum_setup_cpu,#P3_USB_ENUM_PORT)
      ProcedureReturn Pi3UsbEnumBeginControl(#P3_USB_ENUM_PORT_STATUS_WAIT,p3usb_enum_hub_address,p3usb_enum_ep0_mps)
    Case #P3_USB_ENUM_PORT_STATUS_WAIT
      result=Pi3UsbEnumControlStatus() : If result<>0 : ProcedureReturn result : EndIf
      If p3usb_control_actual<>4 : ProcedureReturn Pi3UsbEnumFail(-32) : EndIf
      status=Pi3UsbReadLe16(p3usb_enum_data_cpu) : change=Pi3UsbReadLe16(p3usb_enum_data_cpu+2)
      p3usb_enum_hub_port_status=status : p3usb_enum_hub_port_change=change
      If (status & #P3_USB_PORT_CONNECTION)=0 Or (status & #P3_USB_PORT_POWER)=0 Or (status & #P3_USB_PORT_OVERCURRENT)<>0 : ProcedureReturn Pi3UsbEnumFail(-33) : EndIf
      p3usb_enum_state=#P3_USB_ENUM_PORT_RESET_BEGIN : ProcedureReturn #P3_USB_ENUM_PROGRESS
    Case #P3_USB_ENUM_PORT_RESET_BEGIN
      Pi3UsbHubPortFeatureSetup(p3usb_enum_setup_cpu,#P3_USB_ENUM_PORT,#P3_USB_HUB_PORT_RESET,1)
      ProcedureReturn Pi3UsbEnumBeginControl(#P3_USB_ENUM_PORT_RESET_WAIT,p3usb_enum_hub_address,p3usb_enum_ep0_mps)
    Case #P3_USB_ENUM_PORT_RESET_WAIT
      result=Pi3UsbEnumControlStatus() : If result<>0 : ProcedureReturn result : EndIf
      p3usb_enum_wait_until=nowUs+20000 : p3usb_enum_state=#P3_USB_ENUM_PORT_RESET_SETTLE
      ProcedureReturn #P3_USB_ENUM_WAIT
    Case #P3_USB_ENUM_PORT_RESET_SETTLE
      If nowUs<p3usb_enum_wait_until : ProcedureReturn #P3_USB_ENUM_WAIT : EndIf
      p3usb_enum_state=#P3_USB_ENUM_PORT_RESET_STATUS_BEGIN : ProcedureReturn #P3_USB_ENUM_PROGRESS
    Case #P3_USB_ENUM_PORT_RESET_STATUS_BEGIN
      Pi3UsbHubPortStatusSetup(p3usb_enum_setup_cpu,#P3_USB_ENUM_PORT)
      ProcedureReturn Pi3UsbEnumBeginControl(#P3_USB_ENUM_PORT_RESET_STATUS_WAIT,p3usb_enum_hub_address,p3usb_enum_ep0_mps)
    Case #P3_USB_ENUM_PORT_RESET_STATUS_WAIT
      result=Pi3UsbEnumControlStatus() : If result<>0 : ProcedureReturn result : EndIf
      If p3usb_control_actual<>4 : ProcedureReturn Pi3UsbEnumFail(-32) : EndIf
      status=Pi3UsbReadLe16(p3usb_enum_data_cpu) : change=Pi3UsbReadLe16(p3usb_enum_data_cpu+2)
      p3usb_enum_hub_port_status=status : p3usb_enum_hub_port_change=change
      If (status & #P3_USB_PORT_CONNECTION)=0 : ProcedureReturn Pi3UsbEnumFail(-33) : EndIf
      If (status & #P3_USB_PORT_RESET)<>0
        If p3usb_enum_polls_left=0 : ProcedureReturn Pi3UsbEnumFail(-34) : EndIf
        p3usb_enum_polls_left-1
        delayUs=20000 : If p3usb_enum_polls_left<p3usb_enum_poll_budget-2 : delayUs=200000 : EndIf
        p3usb_enum_wait_until=nowUs+delayUs : p3usb_enum_state=#P3_USB_ENUM_PORT_RESET_SETTLE
        ProcedureReturn #P3_USB_ENUM_WAIT
      EndIf
      If (status & (#P3_USB_PORT_ENABLE | #P3_USB_PORT_POWER | #P3_USB_PORT_HIGH_SPEED))<>(#P3_USB_PORT_ENABLE | #P3_USB_PORT_POWER | #P3_USB_PORT_HIGH_SPEED) Or (status & (#P3_USB_PORT_LOW_SPEED | #P3_USB_PORT_OVERCURRENT))<>0
        ProcedureReturn Pi3UsbEnumFail(-33)
      EndIf
      If (change & #P3_USB_PORT_C_RESET)<>0
        p3usb_enum_state=#P3_USB_ENUM_CLEAR_RESET_BEGIN
      ElseIf (change & #P3_USB_PORT_C_CONNECTION)<>0
        p3usb_enum_state=#P3_USB_ENUM_CLEAR_CONNECT_BEGIN
      ElseIf (change & #P3_USB_PORT_C_ENABLE)<>0
        p3usb_enum_state=#P3_USB_ENUM_CLEAR_ENABLE_BEGIN
      Else
        p3usb_enum_state=#P3_USB_ENUM_LAN8_BEGIN
      EndIf
      ProcedureReturn #P3_USB_ENUM_PROGRESS
    Case #P3_USB_ENUM_CLEAR_RESET_BEGIN
      Pi3UsbHubPortFeatureSetup(p3usb_enum_setup_cpu,#P3_USB_ENUM_PORT,#P3_USB_HUB_C_RESET,0)
      ProcedureReturn Pi3UsbEnumBeginControl(#P3_USB_ENUM_CLEAR_RESET_WAIT,p3usb_enum_hub_address,p3usb_enum_ep0_mps)
    Case #P3_USB_ENUM_CLEAR_RESET_WAIT
      result=Pi3UsbEnumControlStatus() : If result<>0 : ProcedureReturn result : EndIf
      If (p3usb_enum_hub_port_change & #P3_USB_PORT_C_CONNECTION)<>0
        p3usb_enum_state=#P3_USB_ENUM_CLEAR_CONNECT_BEGIN
      ElseIf (p3usb_enum_hub_port_change & #P3_USB_PORT_C_ENABLE)<>0
        p3usb_enum_state=#P3_USB_ENUM_CLEAR_ENABLE_BEGIN
      Else
        p3usb_enum_state=#P3_USB_ENUM_LAN8_BEGIN
      EndIf
      ProcedureReturn #P3_USB_ENUM_PROGRESS
    Case #P3_USB_ENUM_CLEAR_CONNECT_BEGIN
      Pi3UsbHubPortFeatureSetup(p3usb_enum_setup_cpu,#P3_USB_ENUM_PORT,#P3_USB_HUB_C_CONNECTION,0)
      ProcedureReturn Pi3UsbEnumBeginControl(#P3_USB_ENUM_CLEAR_CONNECT_WAIT,p3usb_enum_hub_address,p3usb_enum_ep0_mps)
    Case #P3_USB_ENUM_CLEAR_CONNECT_WAIT
      result=Pi3UsbEnumControlStatus() : If result<>0 : ProcedureReturn result : EndIf
      If (p3usb_enum_hub_port_change & #P3_USB_PORT_C_ENABLE)<>0
        p3usb_enum_state=#P3_USB_ENUM_CLEAR_ENABLE_BEGIN
      Else
        p3usb_enum_state=#P3_USB_ENUM_LAN8_BEGIN
      EndIf
      ProcedureReturn #P3_USB_ENUM_PROGRESS
    Case #P3_USB_ENUM_CLEAR_ENABLE_BEGIN
      Pi3UsbHubPortFeatureSetup(p3usb_enum_setup_cpu,#P3_USB_ENUM_PORT,#P3_USB_HUB_C_ENABLE,0)
      ProcedureReturn Pi3UsbEnumBeginControl(#P3_USB_ENUM_CLEAR_ENABLE_WAIT,p3usb_enum_hub_address,p3usb_enum_ep0_mps)
    Case #P3_USB_ENUM_CLEAR_ENABLE_WAIT
      result=Pi3UsbEnumControlStatus() : If result<>0 : ProcedureReturn result : EndIf
      p3usb_enum_state=#P3_USB_ENUM_LAN8_BEGIN : ProcedureReturn #P3_USB_ENUM_PROGRESS
    Case #P3_USB_ENUM_LAN8_BEGIN
      p3usb_enum_ep0_mps=8
      Pi3UsbGetDescriptorSetup(p3usb_enum_setup_cpu,#P3_USB_DESC_DEVICE,0,8)
      ProcedureReturn Pi3UsbEnumBeginControl(#P3_USB_ENUM_LAN8_WAIT,0,8)
    Case #P3_USB_ENUM_LAN8_WAIT
      result=Pi3UsbEnumControlStatus() : If result<>0 : ProcedureReturn result : EndIf
      If p3usb_control_actual<>8 Or (PeekA(p3usb_enum_data_cpu)&255)<8 Or (PeekA(p3usb_enum_data_cpu+1)&255)<>#P3_USB_DESC_DEVICE : ProcedureReturn Pi3UsbEnumFail(-31) : EndIf
      p3usb_enum_ep0_mps=PeekA(p3usb_enum_data_cpu+7)&255
      If p3usb_enum_ep0_mps<>64 : ProcedureReturn Pi3UsbEnumFail(-31) : EndIf
      p3usb_enum_state=#P3_USB_ENUM_LAN_ADDR_BEGIN : ProcedureReturn #P3_USB_ENUM_PROGRESS
    Case #P3_USB_ENUM_LAN_ADDR_BEGIN
      Pi3UsbSetAddressSetup(p3usb_enum_setup_cpu,#P3_USB_ENUM_LAN_ADDRESS)
      ProcedureReturn Pi3UsbEnumBeginControl(#P3_USB_ENUM_LAN_ADDR_WAIT,0,p3usb_enum_ep0_mps)
    Case #P3_USB_ENUM_LAN_ADDR_WAIT
      result=Pi3UsbEnumControlStatus() : If result<>0 : ProcedureReturn result : EndIf
      p3usb_enum_lan_address=#P3_USB_ENUM_LAN_ADDRESS
      p3usb_enum_wait_until=nowUs+10000 : p3usb_enum_state=#P3_USB_ENUM_LAN_ADDR_SETTLE
      ProcedureReturn #P3_USB_ENUM_WAIT
    Case #P3_USB_ENUM_LAN_ADDR_SETTLE
      If nowUs<p3usb_enum_wait_until : ProcedureReturn #P3_USB_ENUM_WAIT : EndIf
      p3usb_enum_state=#P3_USB_ENUM_LAN18_BEGIN : ProcedureReturn #P3_USB_ENUM_PROGRESS
    Case #P3_USB_ENUM_LAN18_BEGIN
      Pi3UsbGetDescriptorSetup(p3usb_enum_setup_cpu,#P3_USB_DESC_DEVICE,0,18)
      ProcedureReturn Pi3UsbEnumBeginControl(#P3_USB_ENUM_LAN18_WAIT,p3usb_enum_lan_address,p3usb_enum_ep0_mps)
    Case #P3_USB_ENUM_LAN18_WAIT
      result=Pi3UsbEnumControlStatus() : If result<>0 : ProcedureReturn result : EndIf
      If p3usb_control_actual<>18 Or Pi3UsbDeviceIs(p3usb_enum_data_cpu,18,#P3_USB_LAN_VID,#P3_USB_LAN_PID)<>1 Or (PeekA(p3usb_enum_data_cpu+17)&255)=0
        ProcedureReturn Pi3UsbEnumFail(-31)
      EndIf
      p3usb_enum_state=#P3_USB_ENUM_LAN_CFG9_BEGIN : ProcedureReturn #P3_USB_ENUM_PROGRESS
    Case #P3_USB_ENUM_LAN_CFG9_BEGIN
      Pi3UsbGetDescriptorSetup(p3usb_enum_setup_cpu,#P3_USB_DESC_CONFIGURATION,0,9)
      ProcedureReturn Pi3UsbEnumBeginControl(#P3_USB_ENUM_LAN_CFG9_WAIT,p3usb_enum_lan_address,p3usb_enum_ep0_mps)
    Case #P3_USB_ENUM_LAN_CFG9_WAIT
      result=Pi3UsbEnumControlStatus() : If result<>0 : ProcedureReturn result : EndIf
      total=Pi3UsbEnumConfigHeader(p3usb_control_actual) : If total<0 : ProcedureReturn total : EndIf
      Pi3UsbGetDescriptorSetup(p3usb_enum_setup_cpu,#P3_USB_DESC_CONFIGURATION,0,total)
      result=Pi3UsbEnumBeginControl(#P3_USB_ENUM_LAN_CFG_WAIT,p3usb_enum_lan_address,p3usb_enum_ep0_mps)
      If result<0 : ProcedureReturn result : EndIf
      p3usb_enum_state=#P3_USB_ENUM_LAN_CFG_WAIT : ProcedureReturn #P3_USB_ENUM_PROGRESS
    Case #P3_USB_ENUM_LAN_CFG_WAIT
      result=Pi3UsbEnumControlStatus() : If result<>0 : ProcedureReturn result : EndIf
      If Pi3UsbEnumLanConfig(p3usb_control_actual)<>1 : ProcedureReturn p3usb_enum_error : EndIf
      p3usb_enum_state=#P3_USB_ENUM_LAN_SET_CFG_BEGIN : ProcedureReturn #P3_USB_ENUM_PROGRESS
    Case #P3_USB_ENUM_LAN_SET_CFG_BEGIN
      Pi3UsbSetConfigurationSetup(p3usb_enum_setup_cpu,p3usb_enum_lan_configuration)
      ProcedureReturn Pi3UsbEnumBeginControl(#P3_USB_ENUM_LAN_SET_CFG_WAIT,p3usb_enum_lan_address,p3usb_enum_ep0_mps)
    Case #P3_USB_ENUM_LAN_SET_CFG_WAIT
      result=Pi3UsbEnumControlStatus() : If result<>0 : ProcedureReturn result : EndIf
      p3usb_enum_state=#P3_USB_ENUM_FINAL_STATUS_BEGIN : ProcedureReturn #P3_USB_ENUM_PROGRESS
    Case #P3_USB_ENUM_FINAL_STATUS_BEGIN
      Pi3UsbHubPortStatusSetup(p3usb_enum_setup_cpu,#P3_USB_ENUM_PORT)
      ProcedureReturn Pi3UsbEnumBeginControl(#P3_USB_ENUM_FINAL_STATUS_WAIT,p3usb_enum_hub_address,64)
    Case #P3_USB_ENUM_FINAL_STATUS_WAIT
      result=Pi3UsbEnumControlStatus() : If result<>0 : ProcedureReturn result : EndIf
      If p3usb_control_actual<>4 : ProcedureReturn Pi3UsbEnumFail(-32) : EndIf
      status=Pi3UsbReadLe16(p3usb_enum_data_cpu) : change=Pi3UsbReadLe16(p3usb_enum_data_cpu+2)
      If (status & (#P3_USB_PORT_CONNECTION | #P3_USB_PORT_ENABLE | #P3_USB_PORT_POWER | #P3_USB_PORT_HIGH_SPEED))<>(#P3_USB_PORT_CONNECTION | #P3_USB_PORT_ENABLE | #P3_USB_PORT_POWER | #P3_USB_PORT_HIGH_SPEED) Or (status & (#P3_USB_PORT_RESET | #P3_USB_PORT_LOW_SPEED))<>0
        ProcedureReturn Pi3UsbEnumFail(-33)
      EndIf
      If (status & #P3_USB_PORT_OVERCURRENT)<>0 Or (change & (#P3_USB_PORT_C_CONNECTION | #P3_USB_PORT_C_ENABLE | #P3_USB_PORT_C_RESET))<>0
        ProcedureReturn Pi3UsbEnumFail(-33)
      EndIf
      p3usb_enum_state=#P3_USB_ENUM_PUBLISH : ProcedureReturn #P3_USB_ENUM_PROGRESS
    Case #P3_USB_ENUM_PUBLISH
      p3usb_lan_configuration=p3usb_enum_lan_configuration
      p3usb_lan_interface=p3usb_enum_candidate_interface
      p3usb_lan_bulk_in=p3usb_enum_candidate_bulk_in
      p3usb_lan_bulk_out=p3usb_enum_candidate_bulk_out
      p3usb_lan_interrupt_in=p3usb_enum_candidate_interrupt_in
      p3usb_lan_bulk_in_mps=p3usb_enum_candidate_bulk_in_mps
      p3usb_lan_bulk_out_mps=p3usb_enum_candidate_bulk_out_mps
      p3usb_lan_interrupt_mps=p3usb_enum_candidate_interrupt_mps
      p3usb_enum_state=#P3_USB_ENUM_COMPLETE
      ProcedureReturn #P3_USB_ENUM_READY
    Case #P3_USB_ENUM_COMPLETE
      ProcedureReturn #P3_USB_ENUM_READY
  EndSelect
  ProcedureReturn Pi3UsbEnumFail(-30)
EndProcedure

Procedure.i Pi3UsbEnumerationRetriesLeft()
  ProcedureReturn p3usb_control_retries_left
EndProcedure

Procedure.i Pi3UsbEnumerationPollsLeft()
  ProcedureReturn p3usb_enum_polls_left
EndProcedure

; Scheduler-stepped SMSC9514 register, MAC and PHY transport.
; Facts cross-checked against pinned drivers/net/usb/smsc95xx.c/.h; no code
; copied.  Every USB action delegates once to usb_control.pbi per Step call.

#P3_LAN_IO_PROGRESS = 1
#P3_LAN_IO_RETRY = 2
#P3_LAN_IO_WAIT = 3
#P3_LAN_IO_DONE = 4

#P3_LAN_OWNER_NONE = 0
#P3_LAN_OWNER_REGISTER = 1
#P3_LAN_OWNER_MAC = 2
#P3_LAN_OWNER_PHY = 3

#P3_LAN_MII_WRITE = 2
#P3_LAN_MII_BUSY = 1

Global p3lan_io_owner.i
Global p3lan_io_error.i
Global p3lan_io_channel.i
Global p3lan_io_device.i
Global p3lan_io_setup_cpu.i
Global p3lan_io_setup_bus.i
Global p3lan_io_data_cpu.i
Global p3lan_io_data_bus.i
Global p3lan_io_retry_budget.i
Global p3lan_io_timeout_us.i
Global p3lan_reg_active.i
Global p3lan_reg_reading.i
Global p3lan_reg_value.i
Global p3lan_reg_index.i
Global p3lan_mac_state.i
Global p3lan_mac_low.i
Global p3lan_mac_high.i
Global p3lan_mac_valid.i
Global p3lan_phy_state.i
Global p3lan_phy_reading.i
Global p3lan_phy_id.i
Global p3lan_phy_index.i
Global p3lan_phy_value.i
Global p3lan_phy_polls_left.i
Global p3lan_phy_poll_interval_us.i
Global p3lan_io_wait_until.i

Procedure.i Pi3LanIoFail(code.i)
  p3lan_io_error=code : p3lan_io_owner=#P3_LAN_OWNER_NONE
  p3lan_reg_active=0 : p3lan_mac_state=0 : p3lan_phy_state=0
  ProcedureReturn code
EndProcedure

Procedure.i Pi3LanIoReject(code.i)
  p3lan_io_error=code
  ProcedureReturn code
EndProcedure

Procedure.i Pi3LanTransportAttach(channel.i,device.i,setupCpu.i,setupBus.i,dataCpu.i,dataBus.i,retryBudget.i,timeoutUs.i)
  If p3lan_io_owner<>#P3_LAN_OWNER_NONE : ProcedureReturn Pi3LanIoReject(-42) : EndIf
  p3lan_io_error=0
  If channel<0 Or channel>15 Or device<1 Or device>127 Or setupCpu=0 Or dataCpu=0
    ProcedureReturn Pi3LanIoFail(-40)
  EndIf
  If setupBus<=0 Or setupBus>$FFFFFFFF Or dataBus<=0 Or dataBus>$FFFFFFFF Or (setupBus & 3)<>0 Or (dataBus & 3)<>0
    ProcedureReturn Pi3LanIoFail(-40)
  EndIf
  If retryBudget<0 Or retryBudget>100 Or timeoutUs<1 Or timeoutUs>10000000
    ProcedureReturn Pi3LanIoFail(-40)
  EndIf
  ; Transport attaches only to the fully enumerated child, never address zero
  ; or an address whose endpoint set has not been atomically published.
  If device<>p3usb_enum_lan_address Or p3usb_lan_bulk_in=0 Or p3usb_lan_bulk_out=0
    ProcedureReturn Pi3LanIoFail(-41)
  EndIf
  p3lan_io_channel=channel : p3lan_io_device=device
  p3lan_io_setup_cpu=setupCpu : p3lan_io_setup_bus=setupBus
  p3lan_io_data_cpu=dataCpu : p3lan_io_data_bus=dataBus
  p3lan_io_retry_budget=retryBudget : p3lan_io_timeout_us=timeoutUs
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3LanRegStart(reg.i,reading.i,value.i)
  If p3lan_reg_active<>0 : ProcedureReturn Pi3LanIoFail(-42) : EndIf
  If Pi3LanRegisterSetup(p3lan_io_setup_cpu,reg,reading)<>1
    ProcedureReturn Pi3LanIoFail(-43)
  EndIf
  If reading=0 : Pi3LanWriteLe32(p3lan_io_data_cpu,value) : EndIf
  If Pi3UsbControlBegin(p3lan_io_channel,p3lan_io_device,64,0,p3lan_io_setup_cpu,p3lan_io_setup_bus,p3lan_io_data_cpu,p3lan_io_data_bus,p3lan_io_retry_budget,p3lan_io_timeout_us)<>1
    ProcedureReturn Pi3LanIoFail(p3usb_control_error)
  EndIf
  p3lan_reg_index=reg : p3lan_reg_reading=reading : p3lan_reg_active=1
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3LanRegStepInternal()
  Protected result.i=Pi3UsbControlStep()
  If result=#P3_USB_CONTROL_RETRY : ProcedureReturn #P3_LAN_IO_RETRY : EndIf
  If result=#P3_USB_CONTROL_PROGRESS : ProcedureReturn #P3_LAN_IO_PROGRESS : EndIf
  If result<>#P3_USB_CONTROL_DONE : ProcedureReturn Pi3LanIoFail(result) : EndIf
  If p3usb_control_actual<>4 : ProcedureReturn Pi3LanIoFail(-44) : EndIf
  If p3lan_reg_reading<>0 : p3lan_reg_value=Pi3LanReadLe32(p3lan_io_data_cpu) : EndIf
  p3lan_reg_active=0
  ProcedureReturn #P3_LAN_IO_DONE
EndProcedure

Procedure.i Pi3LanRegisterBegin(reg.i,reading.i,value.i)
  If p3lan_io_owner<>#P3_LAN_OWNER_NONE : ProcedureReturn Pi3LanIoReject(-42) : EndIf
  If reading<>0 And reading<>1 : ProcedureReturn Pi3LanIoFail(-43) : EndIf
  p3lan_io_owner=#P3_LAN_OWNER_REGISTER
  If Pi3LanRegStart(reg,reading,value)<>1 : ProcedureReturn p3lan_io_error : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3LanRegisterStep()
  Protected result.i
  If p3lan_io_owner<>#P3_LAN_OWNER_REGISTER : ProcedureReturn Pi3LanIoReject(-42) : EndIf
  result=Pi3LanRegStepInternal()
  If result=#P3_LAN_IO_DONE : p3lan_io_owner=#P3_LAN_OWNER_NONE : EndIf
  ProcedureReturn result
EndProcedure

Procedure.i Pi3LanMiiCommand(phyId.i,registerIndex.i,writing.i)
  Protected result.i
  If phyId<0 Or phyId>31 Or registerIndex<0 Or registerIndex>31 : ProcedureReturn -1 : EndIf
  If writing<>0 And writing<>1 : ProcedureReturn -1 : EndIf
  result=((phyId & 31) << 11) | ((registerIndex & 31) << 6) | #P3_LAN_MII_BUSY
  If writing<>0 : result=result | #P3_LAN_MII_WRITE : EndIf
  ProcedureReturn result
EndProcedure

Procedure.i Pi3LanMacValid(address.i)
  Protected index.i
  Protected anyNonZero.i
  Protected anyNotFF.i
  If address=0 Or (PeekA(address) & 1)<>0 : ProcedureReturn 0 : EndIf
  For index=0 To 5
    If (PeekA(address+index) & 255)<>0 : anyNonZero=1 : EndIf
    If (PeekA(address+index) & 255)<>255 : anyNotFF=1 : EndIf
  Next
  If anyNonZero=0 Or anyNotFF=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

; operation: 1 read ADDRL/ADDRH, 2 write caller's six-byte unicast address.
Procedure.i Pi3LanMacBegin(operation.i,address.i)
  If p3lan_io_owner<>#P3_LAN_OWNER_NONE : ProcedureReturn Pi3LanIoReject(-42) : EndIf
  If address=0 : ProcedureReturn Pi3LanIoFail(-42) : EndIf
  If operation<>1 And operation<>2 : ProcedureReturn Pi3LanIoFail(-45) : EndIf
  If operation=2 And Pi3LanMacValid(address)=0 : ProcedureReturn Pi3LanIoFail(-45) : EndIf
  p3lan_io_owner=#P3_LAN_OWNER_MAC : p3lan_mac_state=operation*10
  p3lan_mac_valid=0
  If operation=2
    p3lan_mac_low=(PeekA(address)&255) | ((PeekA(address+1)&255)<<8) | ((PeekA(address+2)&255)<<16) | ((PeekA(address+3)&255)<<24)
    p3lan_mac_high=(PeekA(address+4)&255) | ((PeekA(address+5)&255)<<8)
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure Pi3LanMacStore(address.i)
  PokeA(address,p3lan_mac_low & 255) : PokeA(address+1,(p3lan_mac_low>>8)&255)
  PokeA(address+2,(p3lan_mac_low>>16)&255) : PokeA(address+3,(p3lan_mac_low>>24)&255)
  PokeA(address+4,p3lan_mac_high & 255) : PokeA(address+5,(p3lan_mac_high>>8)&255)
EndProcedure

Procedure.i Pi3LanMacStep(address.i)
  Protected result.i
  If p3lan_io_owner<>#P3_LAN_OWNER_MAC : ProcedureReturn Pi3LanIoReject(-42) : EndIf
  If address=0 : ProcedureReturn Pi3LanIoFail(-42) : EndIf
  Select p3lan_mac_state
    Case 10
      If Pi3LanRegStart(#P3_LAN_ADDRL,1,0)<>1 : ProcedureReturn p3lan_io_error : EndIf
      p3lan_mac_state=11 : ProcedureReturn #P3_LAN_IO_PROGRESS
    Case 11
      result=Pi3LanRegStepInternal() : If result<>#P3_LAN_IO_DONE : ProcedureReturn result : EndIf
      p3lan_mac_low=p3lan_reg_value : p3lan_mac_state=12 : ProcedureReturn #P3_LAN_IO_PROGRESS
    Case 12
      If Pi3LanRegStart(#P3_LAN_ADDRH,1,0)<>1 : ProcedureReturn p3lan_io_error : EndIf
      p3lan_mac_state=13 : ProcedureReturn #P3_LAN_IO_PROGRESS
    Case 13
      result=Pi3LanRegStepInternal() : If result<>#P3_LAN_IO_DONE : ProcedureReturn result : EndIf
      p3lan_mac_high=p3lan_reg_value & $FFFF : Pi3LanMacStore(address)
      If Pi3LanMacValid(address)=0 : ProcedureReturn Pi3LanIoFail(-45) : EndIf
      p3lan_mac_valid=1 : p3lan_mac_state=0 : p3lan_io_owner=#P3_LAN_OWNER_NONE
      ProcedureReturn #P3_LAN_IO_DONE
    Case 20
      If Pi3LanRegStart(#P3_LAN_ADDRL,0,p3lan_mac_low)<>1 : ProcedureReturn p3lan_io_error : EndIf
      p3lan_mac_state=21 : ProcedureReturn #P3_LAN_IO_PROGRESS
    Case 21
      result=Pi3LanRegStepInternal() : If result<>#P3_LAN_IO_DONE : ProcedureReturn result : EndIf
      p3lan_mac_state=22 : ProcedureReturn #P3_LAN_IO_PROGRESS
    Case 22
      If Pi3LanRegStart(#P3_LAN_ADDRH,0,p3lan_mac_high)<>1 : ProcedureReturn p3lan_io_error : EndIf
      p3lan_mac_state=23 : ProcedureReturn #P3_LAN_IO_PROGRESS
    Case 23
      result=Pi3LanRegStepInternal() : If result<>#P3_LAN_IO_DONE : ProcedureReturn result : EndIf
      Pi3LanMacStore(address) : p3lan_mac_valid=1
      p3lan_mac_state=0 : p3lan_io_owner=#P3_LAN_OWNER_NONE
      ProcedureReturn #P3_LAN_IO_DONE
  EndSelect
  ProcedureReturn Pi3LanIoFail(-45)
EndProcedure

; operation: 1 read, 2 write.  Busy waits are scheduler-visible and bounded.
Procedure.i Pi3LanPhyBegin(operation.i,phyId.i,registerIndex.i,value.i,pollBudget.i,pollIntervalUs.i)
  Protected writing.i
  If p3lan_io_owner<>#P3_LAN_OWNER_NONE : ProcedureReturn Pi3LanIoReject(-42) : EndIf
  If operation<>1 And operation<>2 : ProcedureReturn Pi3LanIoFail(-46) : EndIf
  If operation=2 : writing=1 : EndIf
  If Pi3LanMiiCommand(phyId,registerIndex,writing)<0 Or value<0 Or value>$FFFF
    ProcedureReturn Pi3LanIoFail(-46)
  EndIf
  If pollBudget<1 Or pollBudget>10000 Or pollIntervalUs<1 Or pollIntervalUs>1000000
    ProcedureReturn Pi3LanIoFail(-46)
  EndIf
  p3lan_io_owner=#P3_LAN_OWNER_PHY : p3lan_phy_state=10
  p3lan_phy_reading=0 : If operation=1 : p3lan_phy_reading=1 : EndIf
  p3lan_phy_id=phyId : p3lan_phy_index=registerIndex : p3lan_phy_value=value
  p3lan_phy_polls_left=pollBudget : p3lan_phy_poll_interval_us=pollIntervalUs
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3LanPhyBusy(nowUs.i,nextState.i,delayState.i)
  If (p3lan_reg_value & #P3_LAN_MII_BUSY)=0
    p3lan_phy_state=nextState : ProcedureReturn #P3_LAN_IO_PROGRESS
  EndIf
  If p3lan_phy_polls_left=0 : ProcedureReturn Pi3LanIoFail(-47) : EndIf
  p3lan_phy_polls_left-1 : p3lan_io_wait_until=nowUs+p3lan_phy_poll_interval_us
  p3lan_phy_state=delayState : ProcedureReturn #P3_LAN_IO_WAIT
EndProcedure

Procedure.i Pi3LanPhyStep(nowUs.i)
  Protected result.i
  Protected command.i
  If p3lan_io_owner<>#P3_LAN_OWNER_PHY : ProcedureReturn Pi3LanIoReject(-42) : EndIf
  If nowUs<0 : ProcedureReturn Pi3LanIoFail(-42) : EndIf
  Select p3lan_phy_state
    Case 10
      If Pi3LanRegStart(#P3_LAN_MII_ADDR,1,0)<>1 : ProcedureReturn p3lan_io_error : EndIf
      p3lan_phy_state=11 : ProcedureReturn #P3_LAN_IO_PROGRESS
    Case 11
      result=Pi3LanRegStepInternal() : If result<>#P3_LAN_IO_DONE : ProcedureReturn result : EndIf
      ProcedureReturn Pi3LanPhyBusy(nowUs,20,12)
    Case 12
      If nowUs<p3lan_io_wait_until : ProcedureReturn #P3_LAN_IO_WAIT : EndIf
      p3lan_phy_state=10 : ProcedureReturn #P3_LAN_IO_PROGRESS
    Case 20
      If p3lan_phy_reading<>0
        command=Pi3LanMiiCommand(p3lan_phy_id,p3lan_phy_index,0)
      Else
        command=p3lan_phy_value : p3lan_phy_state=21
        If Pi3LanRegStart(#P3_LAN_MII_DATA,0,command)<>1 : ProcedureReturn p3lan_io_error : EndIf
        ProcedureReturn #P3_LAN_IO_PROGRESS
      EndIf
      If Pi3LanRegStart(#P3_LAN_MII_ADDR,0,command)<>1 : ProcedureReturn p3lan_io_error : EndIf
      p3lan_phy_state=30 : ProcedureReturn #P3_LAN_IO_PROGRESS
    Case 21
      result=Pi3LanRegStepInternal() : If result<>#P3_LAN_IO_DONE : ProcedureReturn result : EndIf
      command=Pi3LanMiiCommand(p3lan_phy_id,p3lan_phy_index,1)
      If Pi3LanRegStart(#P3_LAN_MII_ADDR,0,command)<>1 : ProcedureReturn p3lan_io_error : EndIf
      p3lan_phy_state=30 : ProcedureReturn #P3_LAN_IO_PROGRESS
    Case 30
      result=Pi3LanRegStepInternal() : If result<>#P3_LAN_IO_DONE : ProcedureReturn result : EndIf
      p3lan_phy_state=31 : p3lan_io_wait_until=nowUs+p3lan_phy_poll_interval_us
      ProcedureReturn #P3_LAN_IO_WAIT
    Case 31
      If nowUs<p3lan_io_wait_until : ProcedureReturn #P3_LAN_IO_WAIT : EndIf
      If Pi3LanRegStart(#P3_LAN_MII_ADDR,1,0)<>1 : ProcedureReturn p3lan_io_error : EndIf
      p3lan_phy_state=32 : ProcedureReturn #P3_LAN_IO_PROGRESS
    Case 32
      result=Pi3LanRegStepInternal() : If result<>#P3_LAN_IO_DONE : ProcedureReturn result : EndIf
      result=Pi3LanPhyBusy(nowUs,40,31)
      If result=#P3_LAN_IO_WAIT : p3lan_phy_state=31 : EndIf
      ProcedureReturn result
    Case 40
      If p3lan_phy_reading=0
        p3lan_phy_state=0 : p3lan_io_owner=#P3_LAN_OWNER_NONE
        ProcedureReturn #P3_LAN_IO_DONE
      EndIf
      If Pi3LanRegStart(#P3_LAN_MII_DATA,1,0)<>1 : ProcedureReturn p3lan_io_error : EndIf
      p3lan_phy_state=41 : ProcedureReturn #P3_LAN_IO_PROGRESS
    Case 41
      result=Pi3LanRegStepInternal() : If result<>#P3_LAN_IO_DONE : ProcedureReturn result : EndIf
      p3lan_phy_value=p3lan_reg_value & $FFFF
      p3lan_phy_state=0 : p3lan_io_owner=#P3_LAN_OWNER_NONE
      ProcedureReturn #P3_LAN_IO_DONE
  EndSelect
  ProcedureReturn Pi3LanIoFail(-46)
EndProcedure

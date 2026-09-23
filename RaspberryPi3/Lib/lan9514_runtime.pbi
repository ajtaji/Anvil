; Scheduler-owned SMSC9514 bring-up and bulk Ethernet frame transport.
; Hardware facts were cross-checked against the pinned Raspberry Pi Linux
; drivers/net/usb/smsc95xx.c/.h and U-Boot generic PHY definitions.  No
; implementation was copied.  This layer performs no controller init and
; never claims USB or network capability.

#P3_LAN_RUNTIME_PROGRESS = 1
#P3_LAN_RUNTIME_RETRY = 2
#P3_LAN_RUNTIME_WAIT = 3
#P3_LAN_RUNTIME_READY = 4

#P3_LAN_BULK_TX = 1
#P3_LAN_BULK_RX = 2

#P3_LAN_RX_CFG = $00C
#P3_LAN_BURST_CAP = $038
#P3_LAN_INT_EP_CTL = $068
#P3_LAN_BULK_IN_DLY = $06C
#P3_LAN_VLAN1 = $120

#P3_LAN_HW_CFG_BIR = $00001000
#P3_LAN_HW_CFG_RXDOFF = $00000600
#P3_LAN_HW_CFG_MEF = $00000020
#P3_LAN_HW_CFG_BCE = $00000002
#P3_LAN_LED_DEFAULT = $01110000
#P3_LAN_AFC_DEFAULT = $00F830A1
#P3_LAN_INT_PHY = $00008000
#P3_LAN_RX_BURST_BYTES = 2560
#P3_LAN_RX_BURST_PACKETS = 5
#P3_LAN_BULK_DELAY = $00002000
#P3_LAN_VLAN_ETHERTYPE = $00008100

#P3_LAN_PHY_ID = 1
#P3_LAN_MII_BMCR = 0
#P3_LAN_MII_BMSR = 1
#P3_LAN_PHY_SPECIAL = 31
#P3_LAN_BMCR_ANRESTART = $0200
#P3_LAN_BMCR_ISOLATE = $0400
#P3_LAN_BMCR_ANENABLE = $1000
#P3_LAN_BMSR_LINK = $0004
#P3_LAN_BMSR_ANEG_COMPLETE = $0020
#P3_LAN_PHY_SPEED_MASK = $001C
#P3_LAN_PHY_10_HALF = $0004
#P3_LAN_PHY_10_FULL = $0014
#P3_LAN_PHY_100_HALF = $0008
#P3_LAN_PHY_100_FULL = $0018
#P3_LAN_MAC_FULL_DUPLEX = $00100000
#P3_LAN_MAC_RECEIVE_OWN = $00800000

Global p3lan_runtime_state.i
Global p3lan_runtime_error.i
Global p3lan_runtime_ready.i
Global p3lan_runtime_link.i
Global p3lan_runtime_speed_mbps.i
Global p3lan_runtime_full_duplex.i
Global p3lan_runtime_quarantine.i
Global p3lan_runtime_wait_until.i
Global p3lan_runtime_reset_polls_left.i
Global p3lan_runtime_link_polls_left.i
Global p3lan_runtime_link_poll_budget.i
Global p3lan_runtime_poll_interval_us.i
Global p3lan_runtime_mac_cpu.i
Global p3lan_runtime_mac_cr.i
Global p3lan_runtime_value.i
Global p3lan_runtime_device.i
Global p3lan_runtime_bulk_in.i
Global p3lan_runtime_bulk_out.i
Global p3lan_runtime_bulk_in_mps.i
Global p3lan_runtime_bulk_out_mps.i
Global p3lan_runtime_tx_cpu.i
Global p3lan_runtime_tx_bus.i
Global p3lan_runtime_tx_capacity.i
Global p3lan_runtime_rx_cpu.i
Global p3lan_runtime_rx_bus.i
Global p3lan_runtime_rx_capacity.i
Global p3lan_runtime_tx_pid.i
Global p3lan_runtime_rx_pid.i

Global p3lan_bulk_owner.i
Global p3lan_bulk_error.i
Global p3lan_bulk_offset.i
Global p3lan_bulk_remaining.i
Global p3lan_bulk_actual.i
Global p3lan_bulk_pid.i
Global p3lan_bulk_retries_left.i
Global p3lan_bulk_retry_budget.i
Global p3lan_bulk_frame.i
Global p3lan_bulk_frame_length.i
Global p3lan_bulk_rx_cursor.i

Procedure.i Pi3LanRuntimeFail(code.i)
  p3lan_runtime_error=code : p3lan_runtime_ready=0 : p3lan_runtime_link=0
  p3lan_runtime_state=-1
  If p3usb_transfer_owner<>0 : p3lan_runtime_quarantine=1 : EndIf
  ProcedureReturn code
EndProcedure

Procedure.i Pi3LanRuntimeReject(code.i)
  p3lan_runtime_error=code
  ProcedureReturn code
EndProcedure

Procedure.i Pi3LanRuntimeStillAttached()
  If p3usb_enum_lan_address<>p3lan_runtime_device : ProcedureReturn 0 : EndIf
  If p3usb_lan_bulk_in<>p3lan_runtime_bulk_in Or p3usb_lan_bulk_out<>p3lan_runtime_bulk_out : ProcedureReturn 0 : EndIf
  If p3usb_lan_bulk_in_mps<>p3lan_runtime_bulk_in_mps Or p3usb_lan_bulk_out_mps<>p3lan_runtime_bulk_out_mps : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3LanRuntimeBuffers(txCpu.i,txBus.i,txCapacity.i,rxCpu.i,rxBus.i,rxCapacity.i)
  If p3lan_runtime_state<>0 Or p3lan_bulk_owner<>0 Or p3usb_transfer_owner<>0
    ProcedureReturn Pi3LanRuntimeReject(-50)
  EndIf
  If txCpu=0 Or rxCpu=0 Or txBus<=0 Or rxBus<=0 Or txBus>$FFFFFFFF Or rxBus>$FFFFFFFF
    ProcedureReturn Pi3LanRuntimeFail(-50)
  EndIf
  If (txBus & 3)<>0 Or (rxBus & 3)<>0 Or txCapacity<1526 Or rxCapacity<#P3_LAN_RX_BURST_BYTES
    ProcedureReturn Pi3LanRuntimeFail(-50)
  EndIf
  p3lan_runtime_tx_cpu=txCpu : p3lan_runtime_tx_bus=txBus : p3lan_runtime_tx_capacity=txCapacity
  p3lan_runtime_rx_cpu=rxCpu : p3lan_runtime_rx_bus=rxBus : p3lan_runtime_rx_capacity=rxCapacity
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3LanRuntimeBegin(macCpu.i,resetPollBudget.i,linkPollBudget.i,pollIntervalUs.i)
  p3lan_runtime_error=0 : p3lan_runtime_ready=0 : p3lan_runtime_link=0
  p3lan_runtime_speed_mbps=0 : p3lan_runtime_full_duplex=0 : p3lan_runtime_quarantine=0
  If p3lan_runtime_state<>0 Or p3lan_io_owner<>#P3_LAN_OWNER_NONE Or p3usb_transfer_owner<>0
    ProcedureReturn Pi3LanRuntimeReject(-51)
  EndIf
  If p3lan_runtime_tx_cpu=0 Or p3lan_runtime_rx_cpu=0 Or Pi3LanMacValid(macCpu)=0
    ProcedureReturn Pi3LanRuntimeFail(-51)
  EndIf
  If resetPollBudget<1 Or resetPollBudget>1000 Or linkPollBudget<1 Or linkPollBudget>10000
    ProcedureReturn Pi3LanRuntimeFail(-51)
  EndIf
  If pollIntervalUs<1000 Or pollIntervalUs>1000000 : ProcedureReturn Pi3LanRuntimeFail(-51) : EndIf
  If p3usb_enum_lan_address<1 Or p3usb_lan_bulk_in=0 Or p3usb_lan_bulk_out=0
    ProcedureReturn Pi3LanRuntimeFail(-52)
  EndIf
  If p3usb_lan_bulk_in_mps<1 Or p3usb_lan_bulk_in_mps>512 Or p3usb_lan_bulk_out_mps<1 Or p3usb_lan_bulk_out_mps>512
    ProcedureReturn Pi3LanRuntimeFail(-52)
  EndIf
  p3lan_runtime_device=p3usb_enum_lan_address
  p3lan_runtime_bulk_in=p3usb_lan_bulk_in : p3lan_runtime_bulk_out=p3usb_lan_bulk_out
  p3lan_runtime_bulk_in_mps=p3usb_lan_bulk_in_mps : p3lan_runtime_bulk_out_mps=p3usb_lan_bulk_out_mps
  ; SET_CONFIGURATION reset each endpoint's data toggle to DATA0.
  p3lan_runtime_tx_pid=0 : p3lan_runtime_rx_pid=0
  p3lan_runtime_mac_cpu=macCpu : p3lan_runtime_reset_polls_left=resetPollBudget
  p3lan_runtime_link_polls_left=linkPollBudget : p3lan_runtime_link_poll_budget=linkPollBudget
  p3lan_runtime_poll_interval_us=pollIntervalUs : p3lan_runtime_state=10
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3LanRuntimeRegStart(reg.i,reading.i,value.i,nextState.i)
  If Pi3LanRuntimeStillAttached()=0 : ProcedureReturn Pi3LanRuntimeFail(-52) : EndIf
  If Pi3LanRegisterBegin(reg,reading,value)<>1 : ProcedureReturn Pi3LanRuntimeFail(p3lan_io_error) : EndIf
  p3lan_runtime_state=nextState
  ProcedureReturn #P3_LAN_RUNTIME_PROGRESS
EndProcedure

Procedure.i Pi3LanRuntimeRegFinish(nextState.i)
  Protected result.i=Pi3LanRegisterStep()
  If result=#P3_LAN_IO_RETRY : ProcedureReturn #P3_LAN_RUNTIME_RETRY : EndIf
  If result=#P3_LAN_IO_PROGRESS Or result=#P3_LAN_IO_WAIT : ProcedureReturn result : EndIf
  If result<>#P3_LAN_IO_DONE : ProcedureReturn Pi3LanRuntimeFail(result) : EndIf
  p3lan_runtime_value=p3lan_reg_value : p3lan_runtime_state=nextState
  ProcedureReturn #P3_LAN_RUNTIME_PROGRESS
EndProcedure

Procedure.i Pi3LanRuntimePhyStart(operation.i,index.i,value.i,nextState.i)
  If Pi3LanRuntimeStillAttached()=0 : ProcedureReturn Pi3LanRuntimeFail(-52) : EndIf
  If Pi3LanPhyBegin(operation,#P3_LAN_PHY_ID,index,value,100,1000)<>1
    ProcedureReturn Pi3LanRuntimeFail(p3lan_io_error)
  EndIf
  p3lan_runtime_state=nextState
  ProcedureReturn #P3_LAN_RUNTIME_PROGRESS
EndProcedure

Procedure.i Pi3LanRuntimePhyFinish(nowUs.i,nextState.i)
  Protected result.i=Pi3LanPhyStep(nowUs)
  If result=#P3_LAN_IO_RETRY : ProcedureReturn #P3_LAN_RUNTIME_RETRY : EndIf
  If result=#P3_LAN_IO_PROGRESS Or result=#P3_LAN_IO_WAIT : ProcedureReturn result : EndIf
  If result<>#P3_LAN_IO_DONE : ProcedureReturn Pi3LanRuntimeFail(result) : EndIf
  p3lan_runtime_value=p3lan_phy_value : p3lan_runtime_state=nextState
  ProcedureReturn #P3_LAN_RUNTIME_PROGRESS
EndProcedure

; One call advances at most one USB register/PHY transaction or one delay.
Procedure.i Pi3LanRuntimeStep(nowUs.i)
  Protected value.i
  Protected result.i
  If nowUs<0 Or p3lan_runtime_state<=0 : ProcedureReturn Pi3LanRuntimeFail(-51) : EndIf
  If p3usb_transfer_owner<>0 And p3lan_io_owner=#P3_LAN_OWNER_NONE
    p3lan_runtime_error=-53 : ProcedureReturn #P3_LAN_RUNTIME_RETRY
  EndIf
  Select p3lan_runtime_state
    Case 10 : ProcedureReturn Pi3LanRuntimeRegStart(#P3_LAN_HW_CFG,0,#P3_LAN_HW_CFG_LRST,11)
    Case 11
      result=Pi3LanRuntimeRegFinish(12)
      If result=#P3_LAN_RUNTIME_PROGRESS : p3lan_runtime_wait_until=nowUs+10000 : ProcedureReturn #P3_LAN_RUNTIME_WAIT : EndIf
      ProcedureReturn result
    Case 12
      If nowUs<p3lan_runtime_wait_until : ProcedureReturn #P3_LAN_RUNTIME_WAIT : EndIf
      ProcedureReturn Pi3LanRuntimeRegStart(#P3_LAN_HW_CFG,1,0,13)
    Case 13
      result=Pi3LanRuntimeRegFinish(14)
      If result<>#P3_LAN_RUNTIME_PROGRESS : ProcedureReturn result : EndIf
      If (p3lan_runtime_value & #P3_LAN_HW_CFG_LRST)<>0
        If p3lan_runtime_reset_polls_left=0 : ProcedureReturn Pi3LanRuntimeFail(-54) : EndIf
        p3lan_runtime_reset_polls_left-1 : p3lan_runtime_wait_until=nowUs+10000 : p3lan_runtime_state=12
        ProcedureReturn #P3_LAN_RUNTIME_WAIT
      EndIf
      ProcedureReturn #P3_LAN_RUNTIME_PROGRESS
    Case 14
      If Pi3LanMacBegin(2,p3lan_runtime_mac_cpu)<>1 : ProcedureReturn Pi3LanRuntimeFail(p3lan_io_error) : EndIf
      p3lan_runtime_state=15 : ProcedureReturn #P3_LAN_RUNTIME_PROGRESS
    Case 15
      result=Pi3LanMacStep(p3lan_runtime_mac_cpu)
      If result=#P3_LAN_IO_RETRY : ProcedureReturn #P3_LAN_RUNTIME_RETRY : EndIf
      If result=#P3_LAN_IO_PROGRESS Or result=#P3_LAN_IO_WAIT : ProcedureReturn result : EndIf
      If result<>#P3_LAN_IO_DONE : ProcedureReturn Pi3LanRuntimeFail(result) : EndIf
      p3lan_runtime_state=20 : ProcedureReturn #P3_LAN_RUNTIME_PROGRESS
    Case 20 : ProcedureReturn Pi3LanRuntimeRegStart(#P3_LAN_HW_CFG,1,0,21)
    Case 21 : ProcedureReturn Pi3LanRuntimeRegFinish(22)
    Case 22 : ProcedureReturn Pi3LanRuntimeRegStart(#P3_LAN_HW_CFG,0,p3lan_runtime_value | #P3_LAN_HW_CFG_BIR,23)
    Case 23 : ProcedureReturn Pi3LanRuntimeRegFinish(24)
    Case 24 : ProcedureReturn Pi3LanRuntimeRegStart(#P3_LAN_BURST_CAP,0,#P3_LAN_RX_BURST_PACKETS,25)
    Case 25 : ProcedureReturn Pi3LanRuntimeRegFinish(26)
    Case 26 : ProcedureReturn Pi3LanRuntimeRegStart(#P3_LAN_BULK_IN_DLY,0,#P3_LAN_BULK_DELAY,27)
    Case 27 : ProcedureReturn Pi3LanRuntimeRegFinish(28)
    Case 28 : ProcedureReturn Pi3LanRuntimeRegStart(#P3_LAN_HW_CFG,1,0,29)
    Case 29 : ProcedureReturn Pi3LanRuntimeRegFinish(30)
    Case 30
      value=(p3lan_runtime_value & ~#P3_LAN_HW_CFG_RXDOFF) | #P3_LAN_HW_CFG_BIR | #P3_LAN_HW_CFG_MEF | #P3_LAN_HW_CFG_BCE | $400
      ProcedureReturn Pi3LanRuntimeRegStart(#P3_LAN_HW_CFG,0,value,31)
    Case 31 : ProcedureReturn Pi3LanRuntimeRegFinish(32)
    Case 32 : ProcedureReturn Pi3LanRuntimeRegStart(#P3_LAN_INT_STS,0,$FFFFFFFF,33)
    Case 33 : ProcedureReturn Pi3LanRuntimeRegFinish(34)
    Case 34 : ProcedureReturn Pi3LanRuntimeRegStart(#P3_LAN_ID_REV,1,0,35)
    Case 35
      result=Pi3LanRuntimeRegFinish(36)
      If result=#P3_LAN_RUNTIME_PROGRESS And Pi3LanIdSupported(p3lan_runtime_value)=0 : ProcedureReturn Pi3LanRuntimeFail(-55) : EndIf
      ProcedureReturn result
    Case 36 : ProcedureReturn Pi3LanRuntimeRegStart(#P3_LAN_LED_GPIO_CFG,1,0,37)
    Case 37 : ProcedureReturn Pi3LanRuntimeRegFinish(38)
    Case 38 : ProcedureReturn Pi3LanRuntimeRegStart(#P3_LAN_LED_GPIO_CFG,0,p3lan_runtime_value | #P3_LAN_LED_DEFAULT,39)
    Case 39 : ProcedureReturn Pi3LanRuntimeRegFinish(40)
    Case 40 : ProcedureReturn Pi3LanRuntimeRegStart(#P3_LAN_FLOW,0,0,41)
    Case 41 : ProcedureReturn Pi3LanRuntimeRegFinish(42)
    Case 42 : ProcedureReturn Pi3LanRuntimeRegStart(#P3_LAN_AFC_CFG,0,#P3_LAN_AFC_DEFAULT,43)
    Case 43 : ProcedureReturn Pi3LanRuntimeRegFinish(44)
    Case 44 : ProcedureReturn Pi3LanRuntimeRegStart(#P3_LAN_MAC_CR,1,0,45)
    Case 45
      result=Pi3LanRuntimeRegFinish(46)
      If result=#P3_LAN_RUNTIME_PROGRESS : p3lan_runtime_mac_cr=p3lan_runtime_value : EndIf
      ProcedureReturn result
    Case 46 : ProcedureReturn Pi3LanRuntimeRegStart(#P3_LAN_VLAN1,0,#P3_LAN_VLAN_ETHERTYPE,47)
    Case 47 : ProcedureReturn Pi3LanRuntimeRegFinish(48)
    Case 48 : ProcedureReturn Pi3LanRuntimeRegStart(#P3_LAN_INT_EP_CTL,1,0,49)
    Case 49 : ProcedureReturn Pi3LanRuntimeRegFinish(50)
    Case 50 : ProcedureReturn Pi3LanRuntimeRegStart(#P3_LAN_INT_EP_CTL,0,p3lan_runtime_value | #P3_LAN_INT_PHY,51)
    Case 51 : ProcedureReturn Pi3LanRuntimeRegFinish(52)
    Case 52 : ProcedureReturn Pi3LanRuntimePhyStart(1,#P3_LAN_MII_BMCR,0,53)
    Case 53 : ProcedureReturn Pi3LanRuntimePhyFinish(nowUs,54)
    Case 54
      value=(p3lan_runtime_value | #P3_LAN_BMCR_ANENABLE | #P3_LAN_BMCR_ANRESTART) & ~#P3_LAN_BMCR_ISOLATE
      ProcedureReturn Pi3LanRuntimePhyStart(2,#P3_LAN_MII_BMCR,value,55)
    Case 55
      result=Pi3LanRuntimePhyFinish(nowUs,56)
      If result=#P3_LAN_RUNTIME_PROGRESS : p3lan_runtime_wait_until=nowUs+p3lan_runtime_poll_interval_us : ProcedureReturn #P3_LAN_RUNTIME_WAIT : EndIf
      ProcedureReturn result
    Case 56
      If nowUs<p3lan_runtime_wait_until : ProcedureReturn #P3_LAN_RUNTIME_WAIT : EndIf
      ProcedureReturn Pi3LanRuntimePhyStart(1,#P3_LAN_MII_BMSR,0,57)
    Case 57 : ProcedureReturn Pi3LanRuntimePhyFinish(nowUs,58)
    Case 58 : ProcedureReturn Pi3LanRuntimePhyStart(1,#P3_LAN_MII_BMSR,0,59)
    Case 59
      result=Pi3LanRuntimePhyFinish(nowUs,60)
      If result<>#P3_LAN_RUNTIME_PROGRESS : ProcedureReturn result : EndIf
      If (p3lan_runtime_value & (#P3_LAN_BMSR_LINK | #P3_LAN_BMSR_ANEG_COMPLETE))<>(#P3_LAN_BMSR_LINK | #P3_LAN_BMSR_ANEG_COMPLETE)
        If p3lan_runtime_link_polls_left=0 : ProcedureReturn Pi3LanRuntimeFail(-56) : EndIf
        p3lan_runtime_link_polls_left-1 : p3lan_runtime_wait_until=nowUs+p3lan_runtime_poll_interval_us : p3lan_runtime_state=56
        ProcedureReturn #P3_LAN_RUNTIME_WAIT
      EndIf
      p3lan_runtime_link=1 : ProcedureReturn #P3_LAN_RUNTIME_PROGRESS
    Case 60 : ProcedureReturn Pi3LanRuntimePhyStart(1,#P3_LAN_PHY_SPECIAL,0,61)
    Case 61
      result=Pi3LanRuntimePhyFinish(nowUs,62)
      If result<>#P3_LAN_RUNTIME_PROGRESS : ProcedureReturn result : EndIf
      value=p3lan_runtime_value & #P3_LAN_PHY_SPEED_MASK
      If value=#P3_LAN_PHY_10_HALF
        p3lan_runtime_speed_mbps=10 : p3lan_runtime_full_duplex=0
      ElseIf value=#P3_LAN_PHY_10_FULL
        p3lan_runtime_speed_mbps=10 : p3lan_runtime_full_duplex=1
      ElseIf value=#P3_LAN_PHY_100_HALF
        p3lan_runtime_speed_mbps=100 : p3lan_runtime_full_duplex=0
      ElseIf value=#P3_LAN_PHY_100_FULL
        p3lan_runtime_speed_mbps=100 : p3lan_runtime_full_duplex=1
      Else
        ProcedureReturn Pi3LanRuntimeFail(-57)
      EndIf
      If p3lan_runtime_full_duplex
        p3lan_runtime_mac_cr=(p3lan_runtime_mac_cr | #P3_LAN_MAC_FULL_DUPLEX) & ~#P3_LAN_MAC_RECEIVE_OWN
      Else
        p3lan_runtime_mac_cr=(p3lan_runtime_mac_cr | #P3_LAN_MAC_RECEIVE_OWN) & ~#P3_LAN_MAC_FULL_DUPLEX
      EndIf
      ProcedureReturn #P3_LAN_RUNTIME_PROGRESS
    Case 62 : ProcedureReturn Pi3LanRuntimeRegStart(#P3_LAN_MAC_CR,0,p3lan_runtime_mac_cr | #P3_LAN_MAC_TXEN,63)
    Case 63 : ProcedureReturn Pi3LanRuntimeRegFinish(64)
    Case 64 : ProcedureReturn Pi3LanRuntimeRegStart(#P3_LAN_TX_CFG,0,#P3_LAN_TX_CFG_ON,65)
    Case 65 : ProcedureReturn Pi3LanRuntimeRegFinish(66)
    Case 66 : ProcedureReturn Pi3LanRuntimeRegStart(#P3_LAN_MAC_CR,0,p3lan_runtime_mac_cr | #P3_LAN_MAC_TXEN | #P3_LAN_MAC_RXEN,67)
    Case 67
      result=Pi3LanRuntimeRegFinish(68)
      If result=#P3_LAN_RUNTIME_PROGRESS
        p3lan_runtime_ready=1 : p3lan_runtime_state=100 : ProcedureReturn #P3_LAN_RUNTIME_READY
      EndIf
      ProcedureReturn result
    Case 100
      ProcedureReturn #P3_LAN_RUNTIME_READY
  EndSelect
  ProcedureReturn Pi3LanRuntimeFail(-51)
EndProcedure

Procedure.i Pi3LanBulkFail(code.i)
  p3lan_bulk_error=code
  If p3usb_transfer_owner<>0 : p3lan_runtime_quarantine=1 : p3lan_runtime_ready=0 : EndIf
  p3lan_bulk_owner=0
  ProcedureReturn code
EndProcedure

Procedure.i Pi3LanBulkCanStart()
  If p3lan_runtime_ready=0 Or p3lan_runtime_link=0 Or p3lan_runtime_quarantine<>0 : ProcedureReturn 0 : EndIf
  If p3lan_bulk_owner<>0 Or p3lan_io_owner<>#P3_LAN_OWNER_NONE Or p3usb_transfer_owner<>0 : ProcedureReturn -1 : EndIf
  If Pi3LanRuntimeStillAttached()=0 : p3lan_runtime_ready=0 : p3lan_runtime_link=0 : ProcedureReturn -2 : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3LanBulkTxBegin(frame.i,frameLength.i,retryBudget.i)
  Protected packed.i
  Protected available.i=Pi3LanBulkCanStart()
  If available<0 : p3lan_bulk_error=-60 : ProcedureReturn -60 : EndIf
  If available=0 : ProcedureReturn Pi3LanBulkFail(-60) : EndIf
  If retryBudget<0 Or retryBudget>100 : ProcedureReturn Pi3LanBulkFail(-60) : EndIf
  packed=Pi3LanTxFrame(p3lan_runtime_tx_cpu,p3lan_runtime_tx_capacity,frame,frameLength)
  If packed=0 : ProcedureReturn Pi3LanBulkFail(-61) : EndIf
  p3lan_bulk_owner=#P3_LAN_BULK_TX : p3lan_bulk_offset=0 : p3lan_bulk_remaining=packed
  p3lan_bulk_actual=0 : p3lan_bulk_pid=p3lan_runtime_tx_pid : p3lan_bulk_retries_left=retryBudget : p3lan_bulk_retry_budget=retryBudget
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3LanBulkRxBegin(retryBudget.i)
  Protected available.i=Pi3LanBulkCanStart()
  If available<0 : p3lan_bulk_error=-60 : ProcedureReturn -60 : EndIf
  If available=0 : ProcedureReturn Pi3LanBulkFail(-60) : EndIf
  If retryBudget<0 Or retryBudget>100 : ProcedureReturn Pi3LanBulkFail(-60) : EndIf
  p3lan_bulk_owner=#P3_LAN_BULK_RX : p3lan_bulk_offset=0 : p3lan_bulk_remaining=#P3_LAN_RX_BURST_BYTES
  p3lan_bulk_actual=0 : p3lan_bulk_pid=p3lan_runtime_rx_pid : p3lan_bulk_retries_left=retryBudget : p3lan_bulk_retry_budget=retryBudget
  p3lan_bulk_frame=0 : p3lan_bulk_frame_length=0 : p3lan_bulk_rx_cursor=0
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3LanBulkStep()
  Protected endpoint.i
  Protected maxPacket.i
  Protected cpu.i
  Protected bus.i
  Protected result.i
  Protected actual.i
  If p3lan_bulk_owner<>#P3_LAN_BULK_TX And p3lan_bulk_owner<>#P3_LAN_BULK_RX : ProcedureReturn Pi3LanBulkFail(-60) : EndIf
  If p3lan_runtime_quarantine<>0 : ProcedureReturn Pi3LanBulkFail(-60) : EndIf
  If p3usb_transfer_owner<>0 : p3lan_bulk_error=-60 : ProcedureReturn #P3_LAN_RUNTIME_RETRY : EndIf
  If Pi3LanRuntimeStillAttached()=0 : p3lan_runtime_ready=0 : p3lan_runtime_link=0 : ProcedureReturn Pi3LanBulkFail(-62) : EndIf
  If p3lan_bulk_owner=#P3_LAN_BULK_TX
    endpoint=p3lan_runtime_bulk_out : maxPacket=p3lan_runtime_bulk_out_mps
    cpu=p3lan_runtime_tx_cpu : bus=p3lan_runtime_tx_bus
  Else
    endpoint=p3lan_runtime_bulk_in : maxPacket=p3lan_runtime_bulk_in_mps
    cpu=p3lan_runtime_rx_cpu : bus=p3lan_runtime_rx_bus
  EndIf
  result=Pi3UsbChannelTransfer(p3lan_io_channel,p3lan_runtime_device,endpoint,#P3_USB_EP_BULK,maxPacket,0,bus+p3lan_bulk_offset,p3lan_bulk_remaining,p3lan_bulk_pid,p3lan_io_timeout_us)
  actual=p3usb_transfer_actual
  If actual<0 Or actual>p3lan_bulk_remaining : ProcedureReturn Pi3LanBulkFail(-63) : EndIf
  If result<0
    ; The current transfer primitive does not expose confirmed packet/toggle
    ; progress on a fatal halt or timeout.  Reuse would therefore guess.
    p3lan_runtime_quarantine=1 : p3lan_runtime_ready=0
    ProcedureReturn Pi3LanBulkFail(result)
  EndIf
  If p3usb_transfer_next_pid<>0 And p3usb_transfer_next_pid<>2 : ProcedureReturn Pi3LanBulkFail(-63) : EndIf
  p3lan_bulk_pid=p3usb_transfer_next_pid
  If p3lan_bulk_owner=#P3_LAN_BULK_TX
    p3lan_runtime_tx_pid=p3lan_bulk_pid
  Else
    p3lan_runtime_rx_pid=p3lan_bulk_pid
  EndIf
  If actual>0
    p3lan_bulk_offset+actual : p3lan_bulk_remaining-actual : p3lan_bulk_actual+actual
  EndIf
  If result=0
    If actual>0 : ProcedureReturn #P3_LAN_RUNTIME_PROGRESS : EndIf
    If p3lan_bulk_retries_left=0 : ProcedureReturn Pi3LanBulkFail(-64) : EndIf
    p3lan_bulk_retries_left-1 : ProcedureReturn #P3_LAN_RUNTIME_RETRY
  EndIf
  If p3lan_bulk_owner=#P3_LAN_BULK_TX
    If p3lan_bulk_remaining<>0 : ProcedureReturn Pi3LanBulkFail(-65) : EndIf
    p3lan_bulk_owner=0 : ProcedureReturn #P3_LAN_RUNTIME_READY
  EndIf
  If p3lan_bulk_actual=0 Or Pi3LanRxFrame(p3lan_runtime_rx_cpu,p3lan_bulk_actual)=0
    ProcedureReturn Pi3LanBulkFail(-66)
  EndIf
  p3lan_bulk_frame=p3lan_rx_frame : p3lan_bulk_frame_length=p3lan_rx_length
  p3lan_bulk_rx_cursor=p3lan_rx_consumed : p3lan_bulk_owner=0
  ProcedureReturn #P3_LAN_RUNTIME_READY
EndProcedure

; Advance through a completed RX aggregate without touching USB again.
; 1 publishes the next valid frame, 0 means exact end, negative is malformed.
Procedure.i Pi3LanBulkRxNext()
  Protected remaining.i=p3lan_bulk_actual-p3lan_bulk_rx_cursor
  If p3lan_bulk_owner<>0 Or p3lan_bulk_actual<=0 : ProcedureReturn -66 : EndIf
  If remaining=0 : p3lan_bulk_frame=0 : p3lan_bulk_frame_length=0 : ProcedureReturn 0 : EndIf
  If remaining<0 Or Pi3LanRxFrame(p3lan_runtime_rx_cpu+p3lan_bulk_rx_cursor,remaining)=0
    p3lan_bulk_frame=0 : p3lan_bulk_frame_length=0 : ProcedureReturn -66
  EndIf
  p3lan_bulk_frame=p3lan_rx_frame : p3lan_bulk_frame_length=p3lan_rx_length
  p3lan_bulk_rx_cursor+p3lan_rx_consumed
  ProcedureReturn 1
EndProcedure

Procedure Pi3LanRuntimeDisconnect()
  If p3usb_transfer_owner<>0 : p3lan_runtime_quarantine=1 : EndIf
  p3lan_runtime_ready=0 : p3lan_runtime_link=0 : p3lan_runtime_state=0
  p3lan_runtime_tx_pid=0 : p3lan_runtime_rx_pid=0
  p3lan_bulk_owner=0 : p3lan_bulk_frame=0 : p3lan_bulk_frame_length=0
EndProcedure

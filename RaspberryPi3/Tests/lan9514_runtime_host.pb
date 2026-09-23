; Hostile desk fixture for scheduler-owned LAN9514 bring-up and bulk frames.
#P3_LAN_OWNER_NONE=0
#P3_LAN_IO_PROGRESS=1
#P3_LAN_IO_RETRY=2
#P3_LAN_IO_WAIT=3
#P3_LAN_IO_DONE=4
#P3_USB_EP_BULK=2

Global p3lan_io_owner.i,p3lan_io_error.i,p3lan_reg_value.i,p3lan_phy_value.i
Global p3lan_io_channel.i=3,p3lan_io_timeout_us.i=50000
Global p3usb_transfer_owner.i,p3usb_transfer_actual.i,p3usb_transfer_next_pid.i
Global p3usb_enum_lan_address.i=2,p3usb_lan_bulk_in.i=$81,p3usb_lan_bulk_out.i=2
Global p3usb_lan_bulk_in_mps.i=512,p3usb_lan_bulk_out_mps.i=512
Global testReg.i,testReading.i,testValue.i,testResetReads.i,testWriteCount.i
Global testHwCfg.i,testLed.i,testMacCr.i,testIntCtl.i,testTxCfg.i,testBurst.i,testDelay.i,testAfc.i,testVlan.i
Global testPhyOperation.i,testPhyIndex.i,testPhyValue.i,testBmsrReads.i,testBmcr.i=$0400
Global testMac.i,testTransferMode.i,testTransferCalls.i,testLastBus.i,testLastLength.i,testRxActual.i

Procedure.i Pi3LanMacValid(address.i)
  If address=0 Or (PeekA(address)&1)<>0 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure
Procedure.i Pi3LanRegisterBegin(reg.i,reading.i,value.i)
  If p3lan_io_owner<>0 : p3lan_io_error=-42 : ProcedureReturn -42 : EndIf
  p3lan_io_owner=1 : testReg=reg : testReading=reading : testValue=value
  ProcedureReturn 1
EndProcedure
Procedure.i Pi3LanRegisterStep()
  If testReading
    Select testReg
      Case $014
        If testResetReads>0 : testResetReads-1 : p3lan_reg_value=$8 : Else : p3lan_reg_value=testHwCfg : EndIf
      Case $000 : p3lan_reg_value=$EC001234
      Case $024 : p3lan_reg_value=testLed
      Case $100 : p3lan_reg_value=testMacCr
      Case $068 : p3lan_reg_value=testIntCtl
      Default : p3lan_reg_value=0
    EndSelect
  Else
    testWriteCount+1
    Select testReg
      Case $014
        If testValue=$8 : testResetReads=2 : Else : testHwCfg=testValue : EndIf
      Case $024 : testLed=testValue
      Case $100 : testMacCr=testValue
      Case $068 : testIntCtl=testValue
      Case $010 : testTxCfg=testValue
      Case $038 : testBurst=testValue
      Case $06C : testDelay=testValue
      Case $02C : testAfc=testValue
      Case $120 : testVlan=testValue
    EndSelect
  EndIf
  p3lan_io_owner=0 : ProcedureReturn #P3_LAN_IO_DONE
EndProcedure
Procedure.i Pi3LanMacBegin(operation.i,address.i)
  If p3lan_io_owner<>0 Or operation<>2 Or Pi3LanMacValid(address)=0 : p3lan_io_error=-45 : ProcedureReturn -45 : EndIf
  p3lan_io_owner=2 : testMac=address : ProcedureReturn 1
EndProcedure
Procedure.i Pi3LanMacStep(address.i)
  If p3lan_io_owner<>2 Or address<>testMac : ProcedureReturn -45 : EndIf
  p3lan_io_owner=0 : ProcedureReturn #P3_LAN_IO_DONE
EndProcedure
Procedure.i Pi3LanPhyBegin(operation.i,phy.i,index.i,value.i,polls.i,delay.i)
  If p3lan_io_owner<>0 Or phy<>1 : p3lan_io_error=-46 : ProcedureReturn -46 : EndIf
  p3lan_io_owner=3 : testPhyOperation=operation : testPhyIndex=index : testPhyValue=value
  ProcedureReturn 1
EndProcedure
Procedure.i Pi3LanPhyStep(nowUs.i)
  If p3lan_io_owner<>3 : ProcedureReturn -46 : EndIf
  If testPhyOperation=1
    Select testPhyIndex
      Case 0 : p3lan_phy_value=testBmcr
      Case 1
        testBmsrReads+1
        If testBmsrReads>=4 : p3lan_phy_value=$24 : Else : p3lan_phy_value=0 : EndIf
      Case 31 : p3lan_phy_value=$18
    EndSelect
  ElseIf testPhyIndex=0
    testBmcr=testPhyValue
  EndIf
  p3lan_io_owner=0 : ProcedureReturn #P3_LAN_IO_DONE
EndProcedure

Procedure.i Pi3UsbChannelTransfer(channel.i,device.i,endpoint.i,kind.i,mps.i,low.i,bus.i,length.i,pid.i,timeout.i)
  testTransferCalls+1 : testLastBus=bus : testLastLength=length
  p3usb_transfer_actual=0 : p3usb_transfer_next_pid=pid
  Select testTransferMode
    Case 1
      If testTransferCalls=1 : p3usb_transfer_actual=64 : p3usb_transfer_next_pid=2 : ProcedureReturn 0 : EndIf
      p3usb_transfer_actual=length : p3usb_transfer_next_pid=0 : ProcedureReturn 1
    Case 2
      p3usb_transfer_actual=length-1 : ProcedureReturn 1
    Case 3
      ProcedureReturn 0
    Case 4
      p3usb_transfer_owner=channel+1 : ProcedureReturn -13
    Case 5
      p3usb_transfer_actual=testRxActual : p3usb_transfer_next_pid=2 : ProcedureReturn 1
    Case 6
      ProcedureReturn -12
    Default
      p3usb_transfer_actual=length : ProcedureReturn 1
  EndSelect
EndProcedure

IncludeFile "../Lib/lan9514_protocol.pbi"
IncludeFile "../Lib/lan9514_runtime.pbi"

Procedure.i RunBringup()
  Protected result.i,now.i
  For n.i=0 To 500
    result=Pi3LanRuntimeStep(now)
    If result=#P3_LAN_RUNTIME_WAIT : now=p3lan_runtime_wait_until : EndIf
    If result=#P3_LAN_RUNTIME_READY Or result<0 : ProcedureReturn result : EndIf
  Next
  ProcedureReturn -99
EndProcedure

Procedure.i WriteRxRecord(address.i,frameLength.i,seed.i)
  Protected wire.i=frameLength+4
  Protected consumed.i=4+((wire+2+3)&$FFFFFFFC)
  Pi3LanWriteLe32(address,wire<<16)
  For n.i=0 To frameLength-1 : PokeA(address+6+n,(seed+n)&255) : Next
  ProcedureReturn consumed
EndProcedure

Define *setup=AllocateMemory(8),*control=AllocateMemory(512)
Define *tx=AllocateMemory(2048),*rx=AllocateMemory(4096),*mac=AllocateMemory(6),*frame=AllocateMemory(100)
PokeA(*mac,2):PokeA(*mac+1,$11):PokeA(*mac+2,$22):PokeA(*mac+3,$33):PokeA(*mac+4,$44):PokeA(*mac+5,$55)
For n.i=0 To 69 : PokeA(*frame+n,n) : Next

If Pi3LanRuntimeBuffers(*tx,$C0302000,2048,*rx,$C0303000,4096)<>1 : End 10 : EndIf
If Pi3LanRuntimeBegin(*mac,4,4,10000)<>1 Or RunBringup()<>#P3_LAN_RUNTIME_READY : End 11 : EndIf
If p3lan_runtime_ready<>1 Or p3lan_runtime_link<>1 Or p3lan_runtime_speed_mbps<>100 Or p3lan_runtime_full_duplex<>1 : End 12 : EndIf
If testBurst<>5 Or testDelay<>$2000 Or testAfc<>$00F830A1 Or testVlan<>$8100 : End 13 : EndIf
If (testHwCfg&$1622)<>$1422 Or (testLed&$01110000)<>$01110000 Or (testIntCtl&$8000)=0 : End 14 : EndIf
If (testBmcr&$1200)<>$1200 Or (testBmcr&$400)<>0 : End 15 : EndIf
If (testMacCr&$10000C)<>$10000C Or (testMacCr&$800000)<>0 Or testTxCfg<>4 : End 16 : EndIf

; TX NAK after a 64-byte accepted prefix resumes at the advanced DMA address.
testTransferMode=1 : testTransferCalls=0
If Pi3LanBulkTxBegin(*frame,70,2)<>1 : End 20 : EndIf
If Pi3LanBulkStep()<>#P3_LAN_RUNTIME_PROGRESS Or p3lan_bulk_actual<>64 Or p3lan_bulk_pid<>2 : End 21 : EndIf
If Pi3LanBulkStep()<>#P3_LAN_RUNTIME_READY Or testLastBus<>$C0302040 Or testLastLength<>14 : End 22 : EndIf
If PeekA(*tx+8)<>0 Or PeekA(*tx+77)<>69 : End 23 : EndIf

; Two validated records are published one at a time from one RX aggregate.
Define first.i=WriteRxRecord(*rx,60,$20)
Define second.i=WriteRxRecord(*rx+first,64,$60)
testTransferMode=0 : testTransferCalls=0
If Pi3LanBulkRxBegin(2)<>1 : End 30 : EndIf
; Mock a short bulk-IN completion containing exactly the aggregate.
testTransferMode=5 : testRxActual=first+second
If Pi3LanBulkStep()<>#P3_LAN_RUNTIME_READY : End 31 : EndIf
If p3lan_bulk_frame_length<>60 Or PeekA(p3lan_bulk_frame)<>$20 : End 32 : EndIf
If Pi3LanBulkRxNext()<>1 Or p3lan_bulk_frame_length<>64 Or PeekA(p3lan_bulk_frame)<>$60 : End 33 : EndIf
If Pi3LanBulkRxNext()<>0 : End 34 : EndIf

; Short TX completion, exhausted NAKs, detach, and stuck halt ownership fail closed.
testTransferMode=2 : testTransferCalls=0
If Pi3LanBulkTxBegin(*frame,70,1)<>1 Or Pi3LanBulkStep()<>-65 : End 40 : EndIf
testTransferMode=3 : testTransferCalls=0
If Pi3LanBulkTxBegin(*frame,70,1)<>1 : End 41 : EndIf
If Pi3LanBulkStep()<>#P3_LAN_RUNTIME_RETRY Or Pi3LanBulkStep()<>-64 : End 42 : EndIf
testTransferMode=0 : p3usb_lan_bulk_out=3
If Pi3LanBulkTxBegin(*frame,70,1)<>-60 Or p3lan_runtime_ready<>0 : End 43 : EndIf
p3usb_lan_bulk_out=2 : p3lan_runtime_ready=1 : p3lan_runtime_link=1
testTransferMode=5 : testRxActual=3
If Pi3LanBulkRxBegin(1)<>1 Or Pi3LanBulkStep()<>-66 : End 46 : EndIf
testTransferMode=0 : p3usb_transfer_owner=9
If Pi3LanBulkTxBegin(*frame,70,1)<>-60 Or p3lan_runtime_ready<>1 Or p3lan_runtime_quarantine<>0 : End 47 : EndIf
p3usb_transfer_owner=0 : testTransferMode=6
If Pi3LanBulkTxBegin(*frame,70,1)<>1 Or Pi3LanBulkStep()<>-12 : End 48 : EndIf
If p3lan_runtime_quarantine<>1 Or p3lan_runtime_ready<>0 Or p3usb_transfer_owner<>0 : End 49 : EndIf
p3lan_runtime_quarantine=0 : p3lan_runtime_ready=1 : p3lan_runtime_link=1
testTransferMode=4 : testTransferCalls=0 : p3usb_transfer_owner=0
If Pi3LanBulkTxBegin(*frame,70,1)<>1 Or Pi3LanBulkStep()<>-13 : End 44 : EndIf
If p3lan_runtime_quarantine<>1 Or p3lan_runtime_ready<>0 Or p3usb_transfer_owner=0 : End 45 : EndIf
End 0

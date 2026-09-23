; Hostile desk gate for the production control/enumeration state machines.
Global mockSetup.i, mockData.i, mockSetupBus.i, mockDataBus.i
Global mockCalls.i, mockBadCall.i, mockMutant.i, mockResetPoll.i
Global mockCurrentRequest.i, mockCurrentValue.i, mockCurrentLength.i
Global mockCurrentDirection.i, mockDefaultIsLan.i, mockNakLeft.i
Global mockPartialDataNak.i
Global mockPortChange.i, mockLanConfigured.i
Global p3usb_transfer_actual.i, p3usb_transfer_next_pid.i

Procedure MockLe16(address.i,value.i)
  PokeA(address,value & 255) : PokeA(address+1,(value >> 8) & 255)
EndProcedure

Procedure MockDevice(address.i,hub.i)
  FillMemory(address,18,0)
  PokeA(address,18) : PokeA(address+1,1) : MockLe16(address+2,$0200)
  If hub : PokeA(address+4,9) : EndIf
  PokeA(address+7,64) : MockLe16(address+8,$0424)
  If hub : MockLe16(address+10,$9514) : Else : MockLe16(address+10,$EC00) : EndIf
  PokeA(address+17,1)
EndProcedure

Procedure MockHubConfig(address.i)
  FillMemory(address,25,0)
  PokeA(address,9) : PokeA(address+1,2) : MockLe16(address+2,25)
  PokeA(address+4,1) : PokeA(address+5,1)
  PokeA(address+9,9) : PokeA(address+10,4) : PokeA(address+13,1) : PokeA(address+14,9)
  PokeA(address+18,7) : PokeA(address+19,5) : PokeA(address+20,$81) : PokeA(address+21,3)
  MockLe16(address+22,1) : PokeA(address+24,12)
EndProcedure

Procedure MockLanConfig(address.i)
  FillMemory(address,39,0)
  PokeA(address,9) : PokeA(address+1,2) : MockLe16(address+2,39)
  PokeA(address+4,1) : PokeA(address+5,2)
  PokeA(address+9,9) : PokeA(address+10,4) : PokeA(address+11,4)
  PokeA(address+13,3) : PokeA(address+14,$FF)
  PokeA(address+18,7) : PokeA(address+19,5) : PokeA(address+20,$84) : PokeA(address+21,2) : MockLe16(address+22,512)
  PokeA(address+25,7) : PokeA(address+26,5) : PokeA(address+27,5) : PokeA(address+28,2) : MockLe16(address+29,512)
  PokeA(address+32,7) : PokeA(address+33,5) : PokeA(address+34,$86) : PokeA(address+35,3) : MockLe16(address+36,16)
EndProcedure

Procedure.i Pi3UsbChannelTransfer(channel.i,deviceAddress.i,endpointAddress.i,endpointType.i,maxPacket.i,lowSpeed.i,dmaBusAddress.i,byteCount.i,pid.i,timeoutUs.i)
  Protected descriptor.i,status.i,change.i,actual.i
  mockCalls+1 : p3usb_transfer_actual=0 : p3usb_transfer_next_pid=pid
  If mockMutant=7 : ProcedureReturn -12 : EndIf
  If mockNakLeft>0 : mockNakLeft-1 : ProcedureReturn 0 : EndIf
  If channel<>2 Or endpointType<>0 Or lowSpeed<>0 Or timeoutUs<>50000
    mockBadCall=1 : ProcedureReturn -90
  EndIf
  If byteCount=8 And pid=3
    If endpointAddress<>0 Or dmaBusAddress<>mockSetupBus : mockBadCall=2 : ProcedureReturn -90 : EndIf
    mockCurrentDirection=PeekA(mockSetup) & $80
    mockCurrentRequest=PeekA(mockSetup+1) & 255
    mockCurrentValue=(PeekA(mockSetup+2)&255) | ((PeekA(mockSetup+3)&255)<<8)
    mockCurrentLength=(PeekA(mockSetup+6)&255) | ((PeekA(mockSetup+7)&255)<<8)
    If mockCurrentRequest=5 And mockCurrentValue=1 : mockDefaultIsLan=1 : EndIf
    If mockCurrentRequest=3 And mockCurrentValue=4 : mockResetPoll=1 : EndIf
    If mockCurrentRequest=1 And mockCurrentValue=20 : mockPortChange=mockPortChange & ~$0010 : EndIf
    If mockCurrentRequest=1 And mockCurrentValue=16 : mockPortChange=mockPortChange & ~$0001 : EndIf
    If mockCurrentRequest=1 And mockCurrentValue=17 : mockPortChange=mockPortChange & ~$0002 : EndIf
    If mockCurrentRequest=9 And deviceAddress=2 : mockLanConfigured=1 : EndIf
    p3usb_transfer_actual=8 : ProcedureReturn 1
  EndIf
  If byteCount>0
    If mockPartialDataNak=1
      If pid<>2 Or dmaBusAddress<>mockDataBus Or byteCount<>16 : mockBadCall=9 : ProcedureReturn -90 : EndIf
      p3usb_transfer_actual=8 : p3usb_transfer_next_pid=0 : mockPartialDataNak=2
      ProcedureReturn 0
    ElseIf mockPartialDataNak=2
      If pid<>0 Or dmaBusAddress<>mockDataBus+8 Or byteCount<>8 : mockBadCall=10 : ProcedureReturn -90 : EndIf
      p3usb_transfer_actual=8 : mockPartialDataNak=3
      ProcedureReturn 1
    EndIf
    If pid<>2 Or dmaBusAddress<>mockDataBus Or endpointAddress<>$80 Or mockCurrentDirection=0 Or byteCount<>mockCurrentLength
      mockBadCall=3 : ProcedureReturn -90
    EndIf
    actual=byteCount
    If mockCurrentRequest=6
      descriptor=mockCurrentValue >> 8
      If descriptor=1
        If deviceAddress=1 Or (deviceAddress=0 And mockDefaultIsLan=0)
          MockDevice(mockData,1)
        Else
          MockDevice(mockData,0)
        EndIf
        If mockMutant=1 And deviceAddress=1 : PokeA(mockData+8,$25) : EndIf
        If mockMutant=8 And deviceAddress=2 : PokeA(mockData+8,$25) : EndIf
      ElseIf descriptor=2
        If deviceAddress=1 : MockHubConfig(mockData) : Else : MockLanConfig(mockData) : EndIf
        If mockMutant=2 And deviceAddress=1 And byteCount>9 : PokeA(mockData+18,0) : EndIf
        If mockMutant=9 And byteCount=9 : MockLe16(mockData+2,513) : EndIf
        If mockMutant=10 And deviceAddress=2 And byteCount>9 : PokeA(mockData+27,$84) : EndIf
        If mockMutant=3 And deviceAddress=2 And byteCount>9 : actual=byteCount-1 : EndIf
      ElseIf descriptor=$29
        FillMemory(mockData,9,0) : PokeA(mockData,9) : PokeA(mockData+1,$29)
        PokeA(mockData+2,5) : PokeA(mockData+5,10)
      EndIf
    ElseIf mockCurrentRequest=0
      status=$0101 : change=0
      If mockResetPoll
        If mockResetPoll=1
          status=$0511 : mockResetPoll=2
        ElseIf mockResetPoll=2
          status=$0503 : mockPortChange=$0011 : change=mockPortChange : mockResetPoll=3
        Else
          status=$0503
        EndIf
      EndIf
      If mockMutant=4 And mockResetPoll=2 : status=$0100 : EndIf
      change=mockPortChange
      If mockMutant=5 And deviceAddress=1 And mockDefaultIsLan And mockResetPoll=3 : status=$0100 : EndIf
      If mockMutant=11 And mockLanConfigured : change=change | $0001 : EndIf
      MockLe16(mockData,status) : MockLe16(mockData+2,change)
    EndIf
    p3usb_transfer_actual=actual : ProcedureReturn 1
  EndIf
  If byteCount=0 And pid=2
    If dmaBusAddress<>0 : mockBadCall=4 : ProcedureReturn -90 : EndIf
    If mockCurrentLength>0
      If mockCurrentDirection And endpointAddress<>0 : mockBadCall=5 : ProcedureReturn -90 : EndIf
      If mockCurrentDirection=0 And endpointAddress<>$80 : mockBadCall=6 : ProcedureReturn -90 : EndIf
    ElseIf endpointAddress<>$80
      mockBadCall=7 : ProcedureReturn -90
    EndIf
    p3usb_transfer_actual=0 : ProcedureReturn 1
  EndIf
  mockBadCall=8 : ProcedureReturn -90
EndProcedure

IncludeFile "../Lib/usb_protocol.pbi"
IncludeFile "../Lib/usb_control.pbi"
IncludeFile "../Lib/usb_enumeration.pbi"

Procedure ResetMock(mutant.i)
  mockCalls=0 : mockBadCall=0 : mockMutant=mutant : mockResetPoll=0
  mockCurrentRequest=0 : mockCurrentValue=0 : mockCurrentLength=0
  mockCurrentDirection=0 : mockDefaultIsLan=0 : mockNakLeft=0
  mockPartialDataNak=0
  mockPortChange=0 : mockLanConfigured=0
EndProcedure

Procedure.i RunEnumeration(mutant.i)
  Protected result.i,now.i,steps.i
  ResetMock(mutant)
  result=Pi3UsbEnumerationBegin($0503,2,mockSetup,mockSetupBus,mockData,mockDataBus,512,2,5,50000)
  If result<>1 : ProcedureReturn result : EndIf
  For steps=0 To 999
    result=Pi3UsbEnumerationStep(now)
    If result=#P3_USB_ENUM_WAIT : now=p3usb_enum_wait_until : EndIf
    If result=#P3_USB_ENUM_READY Or result<0 : ProcedureReturn result : EndIf
  Next
  ProcedureReturn -99
EndProcedure

mockSetup=AllocateMemory(8) : mockData=AllocateMemory(512)
mockSetupBus=$C0200000 : mockDataBus=$C0201000
If mockSetup=0 Or mockData=0 : End 10 : EndIf

; Exact three-stage IN control transfer, then scheduler-visible NAK budget.
ResetMock(0)
Pi3UsbGetDescriptorSetup(mockSetup,1,0,8)
If Pi3UsbControlBegin(2,0,8,0,mockSetup,mockSetupBus,mockData,mockDataBus,1,50000)<>1 : End 11 : EndIf
If Pi3UsbControlStep()<>#P3_USB_CONTROL_PROGRESS : End 12 : EndIf
If Pi3UsbControlStep()<>#P3_USB_CONTROL_PROGRESS : End 13 : EndIf
If Pi3UsbControlStep()<>#P3_USB_CONTROL_DONE Or mockCalls<>3 Or mockBadCall : End 14 : EndIf
ResetMock(0) : mockNakLeft=2
Pi3UsbGetDescriptorSetup(mockSetup,1,0,8)
If Pi3UsbControlBegin(2,0,8,0,mockSetup,mockSetupBus,mockData,mockDataBus,1,50000)<>1 : End 15 : EndIf
If Pi3UsbControlStep()<>#P3_USB_CONTROL_RETRY Or p3usb_control_retries_left<>0 : End 16 : EndIf
If Pi3UsbControlStep()<>-21 Or mockCalls<>2 : End 17 : EndIf

; A NAK after an acknowledged packet resumes at the advanced DMA address and
; hardware-reported data toggle.  It never retransmits the accepted bytes.
ResetMock(0) : mockPartialDataNak=1
Pi3UsbGetDescriptorSetup(mockSetup,1,0,16)
If Pi3UsbControlBegin(2,0,8,0,mockSetup,mockSetupBus,mockData,mockDataBus,2,50000)<>1 : End 18 : EndIf
If Pi3UsbControlStep()<>#P3_USB_CONTROL_PROGRESS : End 19 : EndIf
If Pi3UsbControlStep()<>#P3_USB_CONTROL_RETRY Or p3usb_control_data_offset<>8 : End 20 : EndIf
If Pi3UsbControlStep()<>#P3_USB_CONTROL_PROGRESS Or p3usb_control_actual<>16 : End 21 : EndIf
If Pi3UsbControlStep()<>#P3_USB_CONTROL_DONE Or mockCalls<>4 Or mockBadCall : End 22 : EndIf

; Complete topology publishes only after the final port revalidation.
Define happyResult.i=RunEnumeration(0)
If happyResult<>#P3_USB_ENUM_READY : End 90 : EndIf
If mockBadCall<>0 : End 91 : EndIf
If p3usb_enum_hub_address<>1 Or p3usb_enum_lan_address<>2 : End 24 : EndIf
If p3usb_lan_configuration<>2 Or p3usb_lan_interface<>4 : End 25 : EndIf
If p3usb_lan_bulk_in<>$84 Or p3usb_lan_bulk_out<>5 Or p3usb_lan_interrupt_in<>$86 : End 26 : EndIf

; Hostile identities, malformed/truncated descriptors, disconnects, timeout,
; and duplicate endpoints all fail closed with no published endpoint set.
Define mutant.i
For mutant=1 To 11
  If mutant=6 : Continue : EndIf
  If RunEnumeration(mutant)>=0 : End 30+mutant : EndIf
  If p3usb_lan_bulk_in<>0 Or p3usb_lan_bulk_out<>0 Or p3usb_lan_configuration<>0 : End 50+mutant : EndIf
Next

; A transient NAK is observable and resumes at the same stage when scheduled.
ResetMock(0) : mockNakLeft=1
If Pi3UsbEnumerationBegin($0503,2,mockSetup,mockSetupBus,mockData,mockDataBus,512,2,5,50000)<>1 : End 70 : EndIf
If Pi3UsbEnumerationStep(0)<>#P3_USB_ENUM_PROGRESS : End 71 : EndIf
If Pi3UsbEnumerationStep(0)<>#P3_USB_ENUM_RETRY Or Pi3UsbEnumerationRetriesLeft()<>1 : End 72 : EndIf
If Pi3UsbEnumerationStep(0)<>#P3_USB_ENUM_PROGRESS : End 73 : EndIf

; Invalid root state and undersized descriptor storage are rejected pre-I/O.
ResetMock(0)
If Pi3UsbEnumerationBegin($0101,2,mockSetup,mockSetupBus,mockData,mockDataBus,512,2,5,50000)>=0 Or mockCalls<>0 : End 80 : EndIf
If Pi3UsbEnumerationBegin($0503,2,mockSetup,mockSetupBus,mockData,mockDataBus,511,2,5,50000)>=0 Or mockCalls<>0 : End 81 : EndIf
End 0

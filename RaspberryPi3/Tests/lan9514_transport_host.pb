Global testSetup.i, testData.i, testSetupBus.i=$C0300000, testDataBus.i=$C0301000
Global testCalls.i, testNak.i, testTimeout.i, testRequest.i, testReg.i
Global testShort.i
Global testRegId.i=$EC001234, testRegLow.i=$44332202, testRegHigh.i=$6655
Global testMiiAddr.i, testMiiData.i=$ABCD, testMiiBusyReads.i
Global p3usb_transfer_actual.i, p3usb_transfer_next_pid.i

Procedure TestWrite32(address.i,value.i)
  PokeA(address,value&255) : PokeA(address+1,(value>>8)&255)
  PokeA(address+2,(value>>16)&255) : PokeA(address+3,(value>>24)&255)
EndProcedure
Procedure.i TestRead32(address.i)
  ProcedureReturn (PeekA(address)&255)|((PeekA(address+1)&255)<<8)|((PeekA(address+2)&255)<<16)|((PeekA(address+3)&255)<<24)
EndProcedure
Procedure.i TestGetReg(reg.i)
  Select reg
    Case 0 : ProcedureReturn testRegId
    Case $104 : ProcedureReturn testRegHigh
    Case $108 : ProcedureReturn testRegLow
    Case $114
      If testMiiBusyReads>0 : testMiiBusyReads-1 : ProcedureReturn testMiiAddr|1 : EndIf
      ProcedureReturn testMiiAddr & ~$01
    Case $118 : ProcedureReturn testMiiData
  EndSelect
  ProcedureReturn 0
EndProcedure
Procedure TestSetReg(reg.i,value.i)
  Select reg
    Case $104 : testRegHigh=value
    Case $108 : testRegLow=value
    Case $114
      testMiiAddr=value
      If value&1
        testMiiBusyReads=2
        If (value&2)=0 : testMiiData=$ABCD : EndIf
      EndIf
    Case $118 : testMiiData=value&$FFFF
  EndSelect
EndProcedure
Procedure.i Pi3UsbChannelTransfer(channel.i,deviceAddress.i,endpointAddress.i,endpointType.i,maxPacket.i,lowSpeed.i,dmaBusAddress.i,byteCount.i,pid.i,timeoutUs.i)
  testCalls+1 : p3usb_transfer_actual=0 : p3usb_transfer_next_pid=pid
  If testTimeout : ProcedureReturn -12 : EndIf
  If testNak>0 : testNak-1 : ProcedureReturn 0 : EndIf
  If byteCount=8 And pid=3
    If dmaBusAddress<>testSetupBus Or endpointAddress<>0 : ProcedureReturn -90 : EndIf
    testRequest=PeekA(testSetup+1)&255
    testReg=(PeekA(testSetup+4)&255)|((PeekA(testSetup+5)&255)<<8)
    p3usb_transfer_actual=8 : ProcedureReturn 1
  EndIf
  If byteCount=4 And pid=2
    If dmaBusAddress<>testDataBus : ProcedureReturn -91 : EndIf
    If testRequest=$A1
      If endpointAddress<>$80 : ProcedureReturn -92 : EndIf
      TestWrite32(testData,TestGetReg(testReg))
    ElseIf testRequest=$A0
      If endpointAddress<>0 : ProcedureReturn -93 : EndIf
      TestSetReg(testReg,TestRead32(testData))
    Else
      ProcedureReturn -94
    EndIf
    If testShort : p3usb_transfer_actual=3 : Else : p3usb_transfer_actual=4 : EndIf
    ProcedureReturn 1
  EndIf
  If byteCount=0 And pid=2
    If testRequest=$A1 And endpointAddress<>0 : ProcedureReturn -95 : EndIf
    If testRequest=$A0 And endpointAddress<>$80 : ProcedureReturn -96 : EndIf
    ProcedureReturn 1
  EndIf
  ProcedureReturn -97
EndProcedure

IncludeFile "../Lib/usb_protocol.pbi"
IncludeFile "../Lib/lan9514_protocol.pbi"
IncludeFile "../Lib/usb_control.pbi"
IncludeFile "../Lib/usb_enumeration.pbi"
IncludeFile "../Lib/lan9514_transport.pbi"

Procedure.i RunRegister()
  Protected result.i
  For count.i=0 To 20
    result=Pi3LanRegisterStep()
    If result=#P3_LAN_IO_DONE Or result<0 : ProcedureReturn result : EndIf
  Next
  ProcedureReturn -99
EndProcedure
Procedure.i RunMac(address.i)
  Protected result.i
  For count.i=0 To 40
    result=Pi3LanMacStep(address)
    If result=#P3_LAN_IO_DONE Or result<0 : ProcedureReturn result : EndIf
  Next
  ProcedureReturn -99
EndProcedure
Procedure.i RunPhy()
  Protected result.i,now.i
  For count.i=0 To 100
    result=Pi3LanPhyStep(now)
    If result=#P3_LAN_IO_WAIT : now=p3lan_io_wait_until : EndIf
    If result=#P3_LAN_IO_DONE Or result<0 : ProcedureReturn result : EndIf
  Next
  ProcedureReturn -99
EndProcedure

testSetup=AllocateMemory(8) : testData=AllocateMemory(512)
p3usb_enum_lan_address=2 : p3usb_lan_bulk_in=$81 : p3usb_lan_bulk_out=2
If Pi3LanTransportAttach(3,2,testSetup,testSetupBus,testData,testDataBus,2,50000)<>1 : End 10 : EndIf

If Pi3LanRegisterBegin(0,1,0)<>1 Or RunRegister()<>#P3_LAN_IO_DONE : End 11 : EndIf
If p3lan_reg_value<>$EC001234 Or testCalls<>3 : End 12 : EndIf
If Pi3LanRegisterBegin($10,0,$12345678)<>1 Or RunRegister()<>#P3_LAN_IO_DONE : End 13 : EndIf

Define *mac=AllocateMemory(6)
PokeA(*mac,2):PokeA(*mac+1,$11):PokeA(*mac+2,$22):PokeA(*mac+3,$33):PokeA(*mac+4,$44):PokeA(*mac+5,$55)
If Pi3LanMacBegin(2,*mac)<>1 Or RunMac(*mac)<>#P3_LAN_IO_DONE : End 14 : EndIf
If testRegLow<>$33221102 Or testRegHigh<>$5544 Or p3lan_mac_valid<>1 : End 15 : EndIf
FillMemory(*mac,6,0)
If Pi3LanMacBegin(1,*mac)<>1 Or RunMac(*mac)<>#P3_LAN_IO_DONE : End 16 : EndIf
If PeekA(*mac)<>2 Or PeekA(*mac+5)<>$55 : End 17 : EndIf
PokeA(*mac,1)
If Pi3LanMacBegin(2,*mac)<>-45 Or testCalls<>18 : End 18 : EndIf

testMiiBusyReads=0 : testMiiAddr=0 : testMiiData=$ABCD
If Pi3LanPhyBegin(1,1,3,0,8,1000)<>1 Or RunPhy()<>#P3_LAN_IO_DONE : End 20 : EndIf
If p3lan_phy_value<>$ABCD Or p3lan_phy_polls_left>=8 : End 21 : EndIf
testMiiBusyReads=0
If Pi3LanPhyBegin(2,1,4,$55AA,8,1000)<>1 Or RunPhy()<>#P3_LAN_IO_DONE : End 22 : EndIf
If testMiiData<>$55AA Or (testMiiAddr&$7C0)<>(4<<6) Or (testMiiAddr&3)<>3 : End 23 : EndIf

; NAK is surfaced one submission at a time; a timeout fails and releases owner.
testNak=1
If Pi3LanRegisterBegin(0,1,0)<>1 : End 24 : EndIf
If Pi3LanRegisterStep()<>#P3_LAN_IO_RETRY Or p3usb_control_retries_left<>1 : End 25 : EndIf
If RunRegister()<>#P3_LAN_IO_DONE : End 26 : EndIf
testTimeout=1
If Pi3LanRegisterBegin(0,1,0)<>1 Or Pi3LanRegisterStep()<>-12 Or p3lan_io_owner<>0 : End 27 : EndIf
testTimeout=0

testShort=1
If Pi3LanRegisterBegin(0,1,0)<>1 Or RunRegister()<>-44 Or p3lan_io_owner<>0 : End 31 : EndIf
testShort=0

testMiiBusyReads=100
If Pi3LanPhyBegin(1,1,3,0,2,1000)<>1 Or RunPhy()<>-47 Or p3lan_io_owner<>0 : End 32 : EndIf

; An overlapping request is refused without cancelling the current owner.
If Pi3LanRegisterBegin(0,1,0)<>1 : End 28 : EndIf
If Pi3LanMacBegin(1,*mac)<>-42 Or p3lan_io_owner<>#P3_LAN_OWNER_REGISTER : End 29 : EndIf
If RunRegister()<>#P3_LAN_IO_DONE : End 30 : EndIf
End 0

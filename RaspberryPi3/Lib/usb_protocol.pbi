; USB 2.0 protocol framing for the Raspberry Pi 3 host path.
; This file performs no MMIO and owns no transfer buffers.  It is the strict
; byte-level boundary between the DWC2 transport and USB enumeration.
; Facts: USB 2.0 specification chapters 9 and 11, plus the pinned Raspberry
; Pi device tree which identifies 0424:9514 at root port 1 and 0424:ec00
; behind hub port 1.  No implementation code is copied.

#P3_USB_DESC_DEVICE        = 1
#P3_USB_DESC_CONFIGURATION = 2
#P3_USB_DESC_INTERFACE     = 4
#P3_USB_DESC_ENDPOINT      = 5
#P3_USB_DESC_HUB           = $29

#P3_USB_REQ_GET_STATUS        = 0
#P3_USB_REQ_CLEAR_FEATURE     = 1
#P3_USB_REQ_SET_FEATURE       = 3
#P3_USB_REQ_SET_ADDRESS       = 5
#P3_USB_REQ_GET_DESCRIPTOR    = 6
#P3_USB_REQ_SET_CONFIGURATION = 9

#P3_USB_RT_DEVICE_IN    = $80
#P3_USB_RT_DEVICE_OUT   = $00
#P3_USB_RT_HUB_IN       = $A0
#P3_USB_RT_HUB_OUT      = $20
#P3_USB_RT_HUB_PORT_IN  = $A3
#P3_USB_RT_HUB_PORT_OUT = $23

#P3_USB_EP_CONTROL   = 0
#P3_USB_EP_ISO       = 1
#P3_USB_EP_BULK      = 2
#P3_USB_EP_INTERRUPT = 3

#P3_USB_HUB_PORT_POWER = 8
#P3_USB_HUB_PORT_RESET = 4

#P3_USB_LAN_VID     = $0424
#P3_USB_LAN_HUB_PID = $9514
#P3_USB_LAN_PID     = $EC00

Global p3usb_proto_error.i
Global p3usb_lan_configuration.i
Global p3usb_lan_interface.i
Global p3usb_lan_bulk_in.i
Global p3usb_lan_bulk_out.i
Global p3usb_lan_interrupt_in.i
Global p3usb_lan_bulk_in_mps.i
Global p3usb_lan_bulk_out_mps.i
Global p3usb_lan_interrupt_mps.i

Procedure.i Pi3UsbReadLe16(address.i)
  If address=0 : ProcedureReturn -1 : EndIf
  ProcedureReturn (PeekA(address) & 255) | ((PeekA(address+1) & 255) << 8)
EndProcedure

Procedure Pi3UsbWriteLe16(address.i,value.i)
  PokeA(address,value & 255)
  PokeA(address+1,(value >> 8) & 255)
EndProcedure

Procedure Pi3UsbWriteLe32(address.i,value.i)
  PokeA(address,value & 255)
  PokeA(address+1,(value >> 8) & 255)
  PokeA(address+2,(value >> 16) & 255)
  PokeA(address+3,(value >> 24) & 255)
EndProcedure

Procedure.i Pi3UsbSetupPacket(setup.i,requestType.i,request.i,value.i,index.i,length.i)
  p3usb_proto_error=0
  If setup=0 : p3usb_proto_error=-1 : ProcedureReturn 0 : EndIf
  If requestType<0 Or requestType>255 Or request<0 Or request>255
    p3usb_proto_error=-2 : ProcedureReturn 0
  EndIf
  If value<0 Or value>$FFFF Or index<0 Or index>$FFFF Or length<0 Or length>$FFFF
    p3usb_proto_error=-2 : ProcedureReturn 0
  EndIf
  PokeA(setup,requestType) : PokeA(setup+1,request)
  Pi3UsbWriteLe16(setup+2,value)
  Pi3UsbWriteLe16(setup+4,index)
  Pi3UsbWriteLe16(setup+6,length)
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3UsbGetDescriptorSetup(setup.i,descriptorType.i,descriptorIndex.i,length.i)
  If descriptorType<1 Or descriptorType>255 Or descriptorIndex<0 Or descriptorIndex>255
    p3usb_proto_error=-2 : ProcedureReturn 0
  EndIf
  ProcedureReturn Pi3UsbSetupPacket(setup,#P3_USB_RT_DEVICE_IN,#P3_USB_REQ_GET_DESCRIPTOR,(descriptorType << 8) | descriptorIndex,0,length)
EndProcedure

Procedure.i Pi3UsbSetAddressSetup(setup.i,address.i)
  If address<1 Or address>127 : p3usb_proto_error=-2 : ProcedureReturn 0 : EndIf
  ProcedureReturn Pi3UsbSetupPacket(setup,#P3_USB_RT_DEVICE_OUT,#P3_USB_REQ_SET_ADDRESS,address,0,0)
EndProcedure

Procedure.i Pi3UsbSetConfigurationSetup(setup.i,configuration.i)
  If configuration<1 Or configuration>255 : p3usb_proto_error=-2 : ProcedureReturn 0 : EndIf
  ProcedureReturn Pi3UsbSetupPacket(setup,#P3_USB_RT_DEVICE_OUT,#P3_USB_REQ_SET_CONFIGURATION,configuration,0,0)
EndProcedure

Procedure.i Pi3UsbHubDescriptorSetup(setup.i,length.i)
  ProcedureReturn Pi3UsbSetupPacket(setup,#P3_USB_RT_HUB_IN,#P3_USB_REQ_GET_DESCRIPTOR,#P3_USB_DESC_HUB << 8,0,length)
EndProcedure

Procedure.i Pi3UsbHubPortStatusSetup(setup.i,port.i)
  If port<1 Or port>127 : p3usb_proto_error=-2 : ProcedureReturn 0 : EndIf
  ProcedureReturn Pi3UsbSetupPacket(setup,#P3_USB_RT_HUB_PORT_IN,#P3_USB_REQ_GET_STATUS,0,port,4)
EndProcedure

Procedure.i Pi3UsbHubPortFeatureSetup(setup.i,port.i,feature.i,setFeature.i)
  Protected request.i
  If port<1 Or port>127 Or feature<0 Or feature>$FFFF
    p3usb_proto_error=-2 : ProcedureReturn 0
  EndIf
  If setFeature<>0 And setFeature<>1 : p3usb_proto_error=-2 : ProcedureReturn 0 : EndIf
  request=#P3_USB_REQ_CLEAR_FEATURE
  If setFeature : request=#P3_USB_REQ_SET_FEATURE : EndIf
  ProcedureReturn Pi3UsbSetupPacket(setup,#P3_USB_RT_HUB_PORT_OUT,request,feature,port,0)
EndProcedure

Procedure.i Pi3UsbDeviceIs(address.i,length.i,vendor.i,product.i)
  p3usb_proto_error=0
  If address=0 Or length<18 : p3usb_proto_error=-3 : ProcedureReturn 0 : EndIf
  If (PeekA(address) & 255)<18 Or (PeekA(address+1) & 255)<>#P3_USB_DESC_DEVICE
    p3usb_proto_error=-4 : ProcedureReturn 0
  EndIf
  If vendor<0 Or vendor>$FFFF Or product<0 Or product>$FFFF
    p3usb_proto_error=-2 : ProcedureReturn 0
  EndIf
  If Pi3UsbReadLe16(address+8)<>vendor Or Pi3UsbReadLe16(address+10)<>product
    p3usb_proto_error=-5 : ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3UsbHubPortCount(address.i,length.i)
  p3usb_proto_error=0
  If address=0 Or length<7 : p3usb_proto_error=-3 : ProcedureReturn 0 : EndIf
  If (PeekA(address) & 255)<7 Or (PeekA(address) & 255)>length Or (PeekA(address+1) & 255)<>#P3_USB_DESC_HUB
    p3usb_proto_error=-4 : ProcedureReturn 0
  EndIf
  If (PeekA(address+2) & 255)=0 Or (PeekA(address+2) & 255)>31
    p3usb_proto_error=-4 : ProcedureReturn 0
  EndIf
  ProcedureReturn PeekA(address+2) & 255
EndProcedure

; Parse the one configuration which contains the SMSC95xx data interface.
; Endpoint addresses and packet sizes are exported only after the entire
; descriptor stream has been validated.  A partially parsed stream never
; leaves a usable endpoint behind.
Procedure.i Pi3UsbLanEndpoints(configuration.i,length.i)
  Protected total.i
  Protected offset.i
  Protected descLength.i
  Protected descType.i
  Protected active.i
  Protected interfaceNumber.i
  Protected alternate.i
  Protected ep.i
  Protected attributes.i
  Protected mps.i
  Protected cfg.i
  Protected bulkIn.i
  Protected bulkOut.i
  Protected interruptIn.i
  Protected bulkInMps.i
  Protected bulkOutMps.i
  Protected interruptMps.i
  Protected vendorInterfaces.i
  p3usb_proto_error=0
  p3usb_lan_configuration=0 : p3usb_lan_interface=-1
  p3usb_lan_bulk_in=0 : p3usb_lan_bulk_out=0 : p3usb_lan_interrupt_in=0
  p3usb_lan_bulk_in_mps=0 : p3usb_lan_bulk_out_mps=0 : p3usb_lan_interrupt_mps=0
  If configuration=0 Or length<9 : p3usb_proto_error=-3 : ProcedureReturn 0 : EndIf
  If (PeekA(configuration) & 255)<9 Or (PeekA(configuration+1) & 255)<>#P3_USB_DESC_CONFIGURATION
    p3usb_proto_error=-4 : ProcedureReturn 0
  EndIf
  total=Pi3UsbReadLe16(configuration+2)
  If total<9 Or total>length : p3usb_proto_error=-3 : ProcedureReturn 0 : EndIf
  If (PeekA(configuration) & 255)>total : p3usb_proto_error=-4 : ProcedureReturn 0 : EndIf
  cfg=PeekA(configuration+5) & 255
  If cfg=0 : p3usb_proto_error=-4 : ProcedureReturn 0 : EndIf
  offset=PeekA(configuration) & 255
  While offset<total
    If total-offset<2 : p3usb_proto_error=-3 : ProcedureReturn 0 : EndIf
    descLength=PeekA(configuration+offset) & 255
    descType=PeekA(configuration+offset+1) & 255
    If descLength<2 Or descLength>total-offset : p3usb_proto_error=-4 : ProcedureReturn 0 : EndIf
    If descType=#P3_USB_DESC_INTERFACE
      If descLength<9 : p3usb_proto_error=-4 : ProcedureReturn 0 : EndIf
      active=0
      interfaceNumber=PeekA(configuration+offset+2) & 255
      alternate=PeekA(configuration+offset+3) & 255
      ; SMSC95xx exposes a vendor-specific interface.  Alternate zero is the
      ; only shape accepted by this first owner; accepting any class would bind
      ; an unrelated bulk device as Ethernet.
      If alternate=0 And (PeekA(configuration+offset+5) & 255)=$FF
        active=1 : vendorInterfaces+1
      EndIf
    ElseIf descType=#P3_USB_DESC_ENDPOINT And active<>0
      If descLength<7 : p3usb_proto_error=-4 : ProcedureReturn 0 : EndIf
      ep=PeekA(configuration+offset+2) & 255
      attributes=(PeekA(configuration+offset+3) & 255) & 3
      mps=Pi3UsbReadLe16(configuration+offset+4) & $7FF
      If mps=0 Or mps>512 : p3usb_proto_error=-4 : ProcedureReturn 0 : EndIf
      If attributes=#P3_USB_EP_BULK
        If ep & $80
          If bulkIn<>0 : p3usb_proto_error=-6 : ProcedureReturn 0 : EndIf
          bulkIn=ep : bulkInMps=mps
        Else
          If bulkOut<>0 : p3usb_proto_error=-6 : ProcedureReturn 0 : EndIf
          bulkOut=ep : bulkOutMps=mps
        EndIf
      ElseIf attributes=#P3_USB_EP_INTERRUPT And (ep & $80)<>0
        If interruptIn<>0 : p3usb_proto_error=-6 : ProcedureReturn 0 : EndIf
        interruptIn=ep : interruptMps=mps
      EndIf
    EndIf
    offset+descLength
  Wend
  If offset<>total Or vendorInterfaces<>1 Or bulkIn=0 Or bulkOut=0
    p3usb_proto_error=-7 : ProcedureReturn 0
  EndIf
  p3usb_lan_configuration=cfg : p3usb_lan_interface=interfaceNumber
  p3usb_lan_bulk_in=bulkIn : p3usb_lan_bulk_out=bulkOut : p3usb_lan_interrupt_in=interruptIn
  p3usb_lan_bulk_in_mps=bulkInMps : p3usb_lan_bulk_out_mps=bulkOutMps : p3usb_lan_interrupt_mps=interruptMps
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3UsbProtocolErrorCode()
  ProcedureReturn p3usb_proto_error
EndProcedure

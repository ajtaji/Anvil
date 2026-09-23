; Host mock services execute the original production state/protocol routines.
Global scenario, writes, ticks, lastOffset, lastValue
Procedure.i Pi3UsbTime()
  ticks+100
  ProcedureReturn ticks
EndProcedure
Procedure.i Pi3UsbRead(offset.i)
  Select offset
    Case $40
      If scenario=1 : ProcedureReturn 0 : EndIf
      ProcedureReturn $4F54280A
    Case $08
      If scenario=2 : ProcedureReturn 32 : EndIf
    Case $10
      If scenario=3 : ProcedureReturn 0 : EndIf
      If scenario=4 And writes : ProcedureReturn $80000001 : EndIf
      ProcedureReturn $80000000
    Case $500
      If scenario=5 : ProcedureReturn $80000000 : EndIf
      ProcedureReturn 0
    Case $508
      If scenario=100 : ProcedureReturn $0003 : EndIf
    Case $510
      If scenario=100 : ProcedureReturn 0 : EndIf
  EndSelect
  ProcedureReturn 0
EndProcedure
Procedure Pi3UsbWrite(offset.i,value.i)
  If scenario<6 And (offset<>$10 Or value<>1) : End 20 : EndIf
  writes+1
  lastOffset=offset : lastValue=value
EndProcedure
IncludeFile "../Lib/usb_host_core.pbi"
IncludeFile "../Lib/usb_protocol.pbi"
IncludeFile "../Lib/lan9514_protocol.pbi"
IncludeFile "../Lib/usb_transfer.pbi"
Define result, n
For scenario=0 To 5
  writes=0 : ticks=0 : p3usb_state=0
  result=Pi3UsbCoreReset()
  If scenario=0
    If result<>1 Or writes<>1 Or p3usb_state<>1 : End 21 : EndIf
  Else
    If result<>0 : End 22 : EndIf
    If scenario=4
      If writes<>1 Or p3usb_state<>-1 : End 23 : EndIf
      If Pi3UsbCoreReset()<>0 Or writes<>1 : End 24 : EndIf
    Else
      If writes<>0 : End 25 : EndIf
    EndIf
  EndIf
Next
Define *buffer=AllocateMemory(10)
FillMemory(*buffer,10,$AA)
If Pi3LanRegisterSetup(*buffer+1,$114,1)<>1 : End 26 : EndIf
If PeekA(*buffer+1)&255<>$C0 Or PeekA(*buffer+2)&255<>$A1 : End 27 : EndIf
If PeekA(*buffer+5)<>$14 Or PeekA(*buffer+6)<>1 Or PeekA(*buffer+7)<>4 : End 28 : EndIf
If PeekA(*buffer)&255<>$AA Or PeekA(*buffer+9)&255<>$AA : End 29 : EndIf
If Pi3LanRegisterSetup(*buffer+1,3,0)<>0 : End 30 : EndIf
If Pi3LanRegisterSetup(*buffer+1,$114,0)<>1 : End 31 : EndIf
If PeekA(*buffer+1)<>$40 Or PeekA(*buffer+2)&255<>$A0 : End 32 : EndIf

; Exact USB setup packets, including hub class port ownership.
If Pi3UsbGetDescriptorSetup(*buffer+1,#P3_USB_DESC_DEVICE,0,18)<>1 : End 33 : EndIf
If PeekA(*buffer+1)&255<>$80 Or PeekA(*buffer+2)&255<>6 : End 34 : EndIf
If PeekA(*buffer+4)&255<>1 Or PeekA(*buffer+7)&255<>18 : End 35 : EndIf
If Pi3UsbSetAddressSetup(*buffer+1,128)<>0 Or p3usb_proto_error<>-2 : End 36 : EndIf
If Pi3UsbHubPortFeatureSetup(*buffer+1,1,#P3_USB_HUB_PORT_POWER,1)<>1 : End 37 : EndIf
If PeekA(*buffer+1)&255<>$23 Or PeekA(*buffer+2)&255<>3 Or PeekA(*buffer+5)&255<>1 : End 38 : EndIf

; Device and hub descriptors refuse truncation, wrong identity and bad port counts.
Define *device=AllocateMemory(18)
PokeA(*device,18) : PokeA(*device+1,#P3_USB_DESC_DEVICE)
Pi3UsbWriteLe16(*device+8,#P3_USB_LAN_VID) : Pi3UsbWriteLe16(*device+10,#P3_USB_LAN_PID)
If Pi3UsbDeviceIs(*device,18,#P3_USB_LAN_VID,#P3_USB_LAN_PID)<>1 : End 39 : EndIf
If Pi3UsbDeviceIs(*device,17,#P3_USB_LAN_VID,#P3_USB_LAN_PID)<>0 Or p3usb_proto_error<>-3 : End 40 : EndIf
Define *hub=AllocateMemory(9)
PokeA(*hub,9) : PokeA(*hub+1,#P3_USB_DESC_HUB) : PokeA(*hub+2,5)
If Pi3UsbHubPortCount(*hub,9)<>5 : End 41 : EndIf
PokeA(*hub+2,0)
If Pi3UsbHubPortCount(*hub,9)<>0 Or p3usb_proto_error<>-4 : End 42 : EndIf

; A complete vendor-specific SMSC interface is discovered by descriptor type,
; direction and transfer type, not by assumed endpoint numbers.
Define *config=AllocateMemory(64)
PokeA(*config,9) : PokeA(*config+1,#P3_USB_DESC_CONFIGURATION)
Pi3UsbWriteLe16(*config+2,39) : PokeA(*config+4,1) : PokeA(*config+5,2)
PokeA(*config+9,9) : PokeA(*config+10,#P3_USB_DESC_INTERFACE)
PokeA(*config+11,4) : PokeA(*config+12,0) : PokeA(*config+13,3) : PokeA(*config+14,$FF)
PokeA(*config+18,7) : PokeA(*config+19,#P3_USB_DESC_ENDPOINT) : PokeA(*config+20,$84) : PokeA(*config+21,#P3_USB_EP_BULK) : Pi3UsbWriteLe16(*config+22,512)
PokeA(*config+25,7) : PokeA(*config+26,#P3_USB_DESC_ENDPOINT) : PokeA(*config+27,5) : PokeA(*config+28,#P3_USB_EP_BULK) : Pi3UsbWriteLe16(*config+29,512)
PokeA(*config+32,7) : PokeA(*config+33,#P3_USB_DESC_ENDPOINT) : PokeA(*config+34,$86) : PokeA(*config+35,#P3_USB_EP_INTERRUPT) : Pi3UsbWriteLe16(*config+36,16)
If Pi3UsbLanEndpoints(*config,39)<>1 : End 43 : EndIf
If p3usb_lan_configuration<>2 Or p3usb_lan_interface<>4 : End 44 : EndIf
If p3usb_lan_bulk_in<>$84 Or p3usb_lan_bulk_out<>5 Or p3usb_lan_interrupt_in<>$86 : End 45 : EndIf
If p3usb_lan_bulk_in_mps<>512 Or p3usb_lan_bulk_out_mps<>512 Or p3usb_lan_interrupt_mps<>16 : End 46 : EndIf
PokeA(*config+26,0)
If Pi3UsbLanEndpoints(*config,39)<>0 Or p3usb_proto_error<>-7 : End 47 : EndIf
If p3usb_lan_bulk_in<>0 Or p3usb_lan_bulk_out<>0 : End 48 : EndIf

; SMSC95xx register identity, bulk-OUT prefix and aggregate bulk-IN framing.
If Pi3LanIdSupported($EC001234)<>1 Or Pi3LanIdSupported($95001234)<>0 : End 49 : EndIf
Define *frame=AllocateMemory(64), *tx=AllocateMemory(80), i
For i=0 To 59 : PokeA(*frame+i,i) : Next
If Pi3LanTxFrame(*tx,80,*frame,60)<>68 : End 50 : EndIf
If Pi3LanReadLe32(*tx)<>(60 | #P3_LAN_TX_FIRST | #P3_LAN_TX_LAST) Or Pi3LanReadLe32(*tx+4)<>60 : End 51 : EndIf
For i=0 To 59 : If (PeekA(*tx+8+i)&255)<>i : End 52 : EndIf : Next
Define *rx=AllocateMemory(80)
Pi3LanWriteLe32(*rx,64 << 16)
PokeA(*rx+4,$AA) : PokeA(*rx+5,$BB)
For i=0 To 59 : PokeA(*rx+6+i,i) : Next
If Pi3LanRxFrame(*rx,72)<>1 : End 53 : EndIf
If p3lan_rx_frame<>*rx+6 Or p3lan_rx_length<>60 Or p3lan_rx_consumed<>72 : End 54 : EndIf
Pi3LanWriteLe32(*rx,(64 << 16) | #P3_LAN_RX_ERROR)
If Pi3LanRxFrame(*rx,72)<>0 Or p3lan_error<>-4 Or p3lan_rx_frame<>0 : End 55 : EndIf

; DWC2 transfer programming is built as data before any controller ownership
; write.  Invalid fields and fatal halt causes remain distinguishable.
Define word
word=Pi3UsbChannelCharWord(7,$83,#P3_USB_EP_INTERRUPT,64,0)
If word<>((7<<22) | (3<<18) | (3<<11) | $8000 | 64) : End 56 : EndIf
If Pi3UsbChannelCharWord(128,1,#P3_USB_EP_BULK,64,0)<>-1 Or p3usb_error<>-6 : End 57 : EndIf
word=Pi3UsbChannelSizeWord(65535,512,2)
If word<>(65535 | (128<<19) | (2<<29)) Or p3usb_planned_packets<>128 : End 58 : EndIf
If Pi3UsbChannelSizeWord(65535,64,0)<>-1 Or p3usb_error<>-6 : End 59 : EndIf
If Pi3UsbChannelHaltStatus(#P3_USB_HC_HALTED | #P3_USB_HC_XFER_COMPLETE)<>1 : End 60 : EndIf
If Pi3UsbChannelHaltStatus(#P3_USB_HC_HALTED | #P3_USB_HC_NAK)<>0 : End 61 : EndIf
If Pi3UsbChannelHaltStatus(#P3_USB_HC_HALTED | #P3_USB_HC_AHB_ERROR)<>-7 : End 62 : EndIf
If Pi3UsbPortControl($113F,$1000,0)<>$1111 : End 63 : EndIf
If Pi3UsbPortControl(4,$1000,0)<>$1000 : End 163 : EndIf
If Pi3UsbPortControl($1004,$100,$1000)<>$100 : End 164 : EndIf

; A complete buffer-DMA submission reaches a terminal halt, reports actual
; length, and releases its serialized owner.  No automatic retry is hidden.
scenario=100 : writes=0 : ticks=0 : p3usb_state=1 : p3usb_transfer_owner=0
If Pi3UsbChannelTransfer(0,1,$81,#P3_USB_EP_BULK,512,0,$C0200000,64,0,10000)<>1 : End 64 : EndIf
If writes<>6 Or lastOffset<>$508 Or p3usb_transfer_actual<>64 Or p3usb_transfer_owner<>0 : End 65 : EndIf
End 0

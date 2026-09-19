; Explicit, one-shot diagnostic owner. Never runs during update confirmation.
; BCM2837 dma-ranges fact: pinned raspberrypi/linux 7d182693,
; arch/arm/boot/dts/broadcom/bcm2837.dtsi: C0000000 -> ARM 0, size3F000000.
; No source code copied. Cold uncached context is mandatory throughout.
Global Dim p3diag_setup.l[4]
Global Dim p3diag_data.l[132]
Global p3diag_used.i

Procedure.i Pi3UsbDiagCommand()
  If pi3ut_Match("usbdiag")<>0 And pi3ut_End()<>0
    Pi3UsbDiagnostic()
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure Pi3UsbDiagValue(label.i,value.i)
  pi3ut_WriteText(label)
  pi3ut_WriteInt(value)
  pi3ut_WriteByte(13)
  pi3ut_WriteByte(10)
EndProcedure

Procedure Pi3UsbDiagRegisters()
  Pi3UsbDiagValue("native error=",p3usb_native_error)
  Pi3UsbDiagValue("core error=",p3usb_error)
  Pi3UsbDiagValue("host error=",p3usb_host_error)
  If p3usb_native_power=1 And p3usb_native_error=0
    Pi3UsbDiagValue("GSNPSID=",Pi3UsbRead($40))
    Pi3UsbDiagValue("GAHBCFG=",Pi3UsbRead(8))
    Pi3UsbDiagValue("GUSBCFG=",Pi3UsbRead($C))
    Pi3UsbDiagValue("GRSTCTL=",Pi3UsbRead($10))
    Pi3UsbDiagValue("GINTSTS=",Pi3UsbRead($14))
    Pi3UsbDiagValue("HPRT0=",Pi3UsbRead($440))
    Pi3UsbDiagValue("HCCHAR0=",Pi3UsbRead($500))
    Pi3UsbDiagValue("HCINT0=",Pi3UsbRead($508))
  EndIf
EndProcedure

Procedure.i Pi3UsbDiagnostic()
  Protected setup.i
  Protected data.i
  Protected port.i
  Protected result.i
  Protected began.i
  Protected now.i
  Protected step.i
  Protected last.i=-999
  If p3diag_used<>0
    pi3ut_WriteLine("usbdiag refused, error -1: this one-shot cold diagnostic has already run since the last reset, so its channel ownership and buffers are spent. Reset the board to run it again.")
    ProcedureReturn 0
  EndIf
  If Pi3UpdateResetReady()=0
    pi3ut_WriteLine("usbdiag refused, error -2: an update transaction is open or the storage state is unconfirmed, and a diagnostic must not run beside one. Finish or abort the update first.")
    ProcedureReturn 0
  EndIf
  If Pi3UsbNativeContext()=0
    pi3ut_WriteLine("usbdiag refused, error -3: this must run on the primary core with interrupts masked, which is the context the updater prompt itself runs in. Check that nothing has moved the prompt.")
    ProcedureReturn 0
  EndIf
  ; The controller is claimed by the background network bring-up during boot,
  ; long before anyone can type. Entering the cold path anyway only reaches the
  ; initializer's own already-initialized refusal one line later, and spends the
  ; one-shot on the way. Report what the live controller says instead: that is
  ; the half of this command which still means something once it is owned.
  If p3usb_host_state<>0 Or p3usb_state<>0
    pi3ut_WriteText("usbdiag: the USB controller is already owned, host state ")
    pi3ut_WriteInt(p3usb_host_state)
    pi3ut_WriteText(", core state ")
    pi3ut_WriteInt(p3usb_state)
    pi3ut_WriteLine("; the network bring-up claims it at boot. Reporting the live controller; a cold diagnostic needs a reset, and this one-shot is still unspent.")
    Pi3UsbDiagRegisters()
    ProcedureReturn 0
  EndIf
  setup=((@p3diag_setup[0]+3)>>2)<<2
  data=((@p3diag_data[0]+3)>>2)<<2
  ; Buffers are resident globals in the source-owned updater BSS interval.
  ; They never alias staging, stack, DTB or the firmware framebuffer.
  If setup<$1100000 Or setup>$1DFFFF8 Or data<$1100000 Or data>$1DFFE00 Or (setup<data+512 And data<setup+8)
    pi3ut_WriteLine("usbdiag refused, error -4: the diagnostic's own DMA buffers are not inside the updater's resident interval, so the controller would be pointed at memory this image does not own. Check the build's BSS placement.")
    ProcedureReturn 0
  EndIf
  p3diag_used=1
  pi3ut_WriteLine("USB 1: firmware power, core/PHY/FIFO initialization")
  If Pi3UsbHostInit()=0
    pi3ut_WriteText("usbdiag stopped: the controller would not initialize, host error ")
    pi3ut_WriteInt(p3usb_host_error)
    pi3ut_WriteLine(". The registers below are the state it stopped in; the updater prompt remains available.")
    Pi3UsbDiagRegisters()
    ProcedureReturn 0
  EndIf
  Pi3UsbDiagRegisters()
  pi3ut_WriteLine("USB 2: root port reset, DMA still disabled")
  If Pi3UsbRootPortReset()=0
    Pi3UsbDiagRegisters()
    ProcedureReturn 0
  EndIf
  port=Pi3UsbRead($440)
  ; HPRT0 is not a USB hub-class status word. Translate, do not cast.
  If (port&$1005)<>$1005 Or (port&$110)<>0 Or ((port>>17)&3)<>0
    pi3ut_WriteLine("USB refused: root not enabled high-speed")
    Pi3UsbDiagRegisters()
    ProcedureReturn 0
  EndIf
  If Pi3UsbEnumerationBegin($503,0,setup,setup|$C0000000,data,data|$C0000000,512,8,10,100000)=0
    Pi3UsbDiagValue("enumeration begin error=",p3usb_enum_error)
    ProcedureReturn 0
  EndIf
  pi3ut_WriteLine("USB 3: enable polled buffer DMA; serialized enumeration")
  Pi3UsbWrite(8,(Pi3UsbRead(8)&~1)|$20)
  If (Pi3UsbRead(8)&$21)<>$20
    pi3ut_WriteLine("USB refused: DMA enable readback")
    ProcedureReturn 0
  EndIf
  began=Pi3UsbTime()
  result=-90
  For step=0 To 1999999
    now=Pi3UsbTime()
    If now<began Or now-began>=15000000
      result=-90
      Break
    EndIf
    If p3usb_enum_state<>last
      last=p3usb_enum_state
      Pi3UsbDiagValue("USB state=",last)
    EndIf
    result=Pi3UsbEnumerationStep(now)
    If result<0 Or result=#P3_USB_ENUM_READY
      Break
    EndIf
  Next
  Pi3UsbDiagValue("USB result=",result)
  Pi3UsbDiagValue("enumeration error=",p3usb_enum_error)
  Pi3UsbDiagValue("control error=",p3usb_control_error)
  Pi3UsbDiagRegisters()
  ; Never reuse a buffer or reset an owner after an unacknowledged halt.
  ; The globals stay reserved until reboot, even after this command returns.
  If p3usb_transfer_owner<>0 Or (Pi3UsbRead($500)&$80000000)<>0
    pi3ut_WriteLine("USB quarantined: channel ownership retained; buffers reserved")
    ProcedureReturn 0
  EndIf
  Pi3UsbWrite(8,Pi3UsbRead(8)&~$21)
  If (Pi3UsbRead(8)&$21)<>0
    pi3ut_WriteLine("USB quarantined: DMA disable readback")
    ProcedureReturn 0
  EndIf
  If result<>#P3_USB_ENUM_READY
    pi3ut_WriteLine("USB diagnostic failed; updater remains available")
    ProcedureReturn 0
  EndIf
  Pi3UsbDiagValue("LAN bulk IN=",p3usb_lan_bulk_in)
  Pi3UsbDiagValue("LAN bulk OUT=",p3usb_lan_bulk_out)
  pi3ut_WriteLine("USB descriptors accepted; DMA off; no network capability claimed")
  ProcedureReturn 1
EndProcedure

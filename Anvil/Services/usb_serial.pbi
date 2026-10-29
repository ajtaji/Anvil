; Shared USB serial transport. A board binds one synchronous provider before
; opening a receiver. This is an internal service, not a payload ABI extension.
; Provider dispatch receives (operation, argument, count). READ/WRITE return
; byte counts or -1; other operations preserve the existing serial contract.
; KIND_TEXT returns a borrowed NUL-terminated string with provider lifetime.
; Binding requires the caller to have stopped existing users first.
#USB_SERIAL_KIND=1
#USB_SERIAL_KIND_TEXT=2
#USB_SERIAL_NEEDS_BAUD=3
#USB_SERIAL_SET_BAUD=4
#USB_SERIAL_ERROR=5
#USB_SERIAL_FIND=6
#USB_SERIAL_READ=7
#USB_SERIAL_WRITE=8
#USB_SERIAL_VID=9
#USB_SERIAL_PID=10
#USB_SERIAL_SLOT=11
Global *usbserialProvider=0

Procedure UsbSerialBind(*provider)
  *usbserialProvider=*provider
EndProcedure

Procedure.i UsbSerialAvailable()
  ProcedureReturn Bool(*usbserialProvider<>0)
EndProcedure

Procedure.i UsbSerialKind()
  If *usbserialProvider=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn usbserialProvider(#USB_SERIAL_KIND,0,0)
EndProcedure
Procedure.i UsbSerialKindText(kind.i)
  If *usbserialProvider=0 : ProcedureReturn "unavailable" : EndIf
  ProcedureReturn usbserialProvider(#USB_SERIAL_KIND_TEXT,kind,0)
EndProcedure
Procedure.i UsbSerialNeedsBaud()
  If *usbserialProvider=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn usbserialProvider(#USB_SERIAL_NEEDS_BAUD,0,0)
EndProcedure
Procedure.i UsbSerialSetBaud(baud.i)
  If *usbserialProvider=0 Or baud<=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn usbserialProvider(#USB_SERIAL_SET_BAUD,baud,0)
EndProcedure
Procedure.i UsbSerialError()
  If *usbserialProvider=0 : ProcedureReturn 1 : EndIf
  ProcedureReturn usbserialProvider(#USB_SERIAL_ERROR,0,0)
EndProcedure
Procedure.i UsbSerialFind()
  If *usbserialProvider=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn usbserialProvider(#USB_SERIAL_FIND,0,0)
EndProcedure
Procedure.i UsbSerialRead(*dst,capacity.i)
  If *usbserialProvider=0 Or *dst=0 Or capacity<=0 : ProcedureReturn -1 : EndIf
  ProcedureReturn usbserialProvider(#USB_SERIAL_READ,*dst,capacity)
EndProcedure
Procedure.i UsbSerialWrite(*src,count.i)
  If *usbserialProvider=0 Or *src=0 Or count<=0 : ProcedureReturn -1 : EndIf
  ProcedureReturn usbserialProvider(#USB_SERIAL_WRITE,*src,count)
EndProcedure
Procedure.i UsbSerialVid()
  If *usbserialProvider=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn usbserialProvider(#USB_SERIAL_VID,0,0)
EndProcedure
Procedure.i UsbSerialPid()
  If *usbserialProvider=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn usbserialProvider(#USB_SERIAL_PID,0,0)
EndProcedure
Procedure.i UsbSerialSlot()
  If *usbserialProvider=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn usbserialProvider(#USB_SERIAL_SLOT,0,0)
EndProcedure

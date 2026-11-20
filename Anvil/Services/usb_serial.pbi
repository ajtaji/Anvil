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
Procedure.i usbserial_Unbound(operation.i,argument.i,count.i)
  Select operation
    Case #USB_SERIAL_KIND_TEXT : ProcedureReturn "unavailable"
    Case #USB_SERIAL_ERROR : ProcedureReturn 1
    Case #USB_SERIAL_READ,#USB_SERIAL_WRITE : ProcedureReturn -1
  EndSelect
  ProcedureReturn 0
EndProcedure

Global usbserialProvider.i=@usbserial_Unbound

Procedure UsbSerialBind(*provider)
  If *provider=0 : usbserialProvider=@usbserial_Unbound : Else : usbserialProvider=*provider : EndIf
EndProcedure

Procedure.i UsbSerialAvailable()
  ProcedureReturn Bool(usbserialProvider<>@usbserial_Unbound)
EndProcedure

Procedure.i UsbSerialKind()
  ProcedureReturn usbserialProvider(#USB_SERIAL_KIND,0,0)
EndProcedure
Procedure.i UsbSerialKindText(kind.i)
  ProcedureReturn usbserialProvider(#USB_SERIAL_KIND_TEXT,kind,0)
EndProcedure
Procedure.i UsbSerialNeedsBaud()
  ProcedureReturn usbserialProvider(#USB_SERIAL_NEEDS_BAUD,0,0)
EndProcedure
Procedure.i UsbSerialSetBaud(baud.i)
  If baud<=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn usbserialProvider(#USB_SERIAL_SET_BAUD,baud,0)
EndProcedure
Procedure.i UsbSerialError()
  ProcedureReturn usbserialProvider(#USB_SERIAL_ERROR,0,0)
EndProcedure
Procedure.i UsbSerialFind()
  ProcedureReturn usbserialProvider(#USB_SERIAL_FIND,0,0)
EndProcedure
Procedure.i UsbSerialRead(*dst,capacity.i)
  If *dst=0 Or capacity<=0 : ProcedureReturn -1 : EndIf
  ProcedureReturn usbserialProvider(#USB_SERIAL_READ,*dst,capacity)
EndProcedure
Procedure.i UsbSerialWrite(*src,count.i)
  If *src=0 Or count<=0 : ProcedureReturn -1 : EndIf
  ProcedureReturn usbserialProvider(#USB_SERIAL_WRITE,*src,count)
EndProcedure
Procedure.i UsbSerialVid()
  ProcedureReturn usbserialProvider(#USB_SERIAL_VID,0,0)
EndProcedure
Procedure.i UsbSerialPid()
  ProcedureReturn usbserialProvider(#USB_SERIAL_PID,0,0)
EndProcedure
Procedure.i UsbSerialSlot()
  ProcedureReturn usbserialProvider(#USB_SERIAL_SLOT,0,0)
EndProcedure

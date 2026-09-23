XIncludeFile "usb_host_model.pbi"
Define n.i,result.i
For n=0 To 8
  result=UsbHostScenario(n)
  If result<>1:End 10+n:EndIf
Next
End 0

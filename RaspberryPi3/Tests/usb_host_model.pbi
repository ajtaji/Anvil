; Hostile ordered-register model for the actual host-init routines.
Global model_case.i
Global model_ticks.i
Global model_writes.i
Global model_power.i
Global model_cfg.i
Global model_ahb.i
Global model_hcfg.i
Global model_rx.i
Global model_np.i
Global model_pt.i
Global model_port.i
Global model_otg.i
Global model_reset.i
Global model_violations.i
Procedure.i Pi3UsbPowerAcquire()
  If model_case=1
  ProcedureReturn 0
  EndIf
  model_power=1
  ProcedureReturn 1
EndProcedure
Procedure.i Pi3UsbTime()
  If model_case<>7
  model_ticks+1000
  EndIf
  ProcedureReturn model_ticks
EndProcedure
Procedure.i Pi3UsbRead(offset.i)
  If model_power=0
  model_violations+1
  EndIf
  Select offset
    Case 0
    ProcedureReturn model_otg
    Case 8
    ProcedureReturn model_ahb
    Case $C
    ProcedureReturn model_cfg
    Case $10
      If model_case=3 And model_reset=$420
      ProcedureReturn $80000020
      EndIf
      ProcedureReturn $80000000
    Case $14
      If model_case=2
      ProcedureReturn 0
      EndIf
      ProcedureReturn 1
    Case $24
    ProcedureReturn model_rx
    Case $28
    ProcedureReturn model_np
    Case $100
    ProcedureReturn model_pt
    Case $400
    ProcedureReturn model_hcfg
    Case $440
    ProcedureReturn model_port
    Case $40
    ProcedureReturn $4F54280A
    Case $48
    ProcedureReturn $9C050
    Case $4C
      If model_case=4
      ProcedureReturn 512<<16
      EndIf
      ProcedureReturn 2048<<16
    Case $50
    ProcedureReturn 0
  EndSelect
  ProcedureReturn 0
EndProcedure
Procedure Pi3UsbWrite(offset.i,value.i)
  If model_power=0
  model_violations+1
  EndIf
  model_writes+1
  Select offset
    Case 0
    model_otg=value
    Case 8
      If value&$21
      model_violations+1
      EndIf
      model_ahb=value
    Case $C
    model_cfg=value
    Case $10
    model_reset=value
    Case $24
      If model_case<>5
      model_rx=value
      EndIf
    Case $28
    model_np=value
    Case $100
    model_pt=value
    Case $400
    model_hcfg=value
    Case $440
      If model_case=8 And (value&$100)<>0
        ProcedureReturn
      EndIf
      If value&$2E
      model_violations+1
      EndIf
      If (model_port&$100)<>0 And (value&$100)=0 And model_case<>6
      value=value|4
      EndIf
      model_port=value
  EndSelect
EndProcedure
XIncludeFile "../Lib/usb_host_core.pbi"
XIncludeFile "../Lib/usb_host_init.pbi"
Procedure.i UsbHostScenario(which.i)
  Protected result.i
  model_case=which
  model_ticks=0
  model_writes=0
  model_power=0
  model_cfg=0
  model_ahb=0
  model_hcfg=0
  model_rx=0
  model_np=256<<16
  model_pt=512<<16
  model_port=1
  model_otg=0
  model_reset=0
  model_violations=0
  p3usb_state=0
  p3usb_host_state=0
  result=Pi3UsbHostInit()
  If which=0 Or which=6 Or which=8
    If result<>1
    ProcedureReturn 10
    EndIf
    If model_rx<>774 Or model_np<>((256<<16)|774) Or model_pt<>((512<<16)|1030)
    ProcedureReturn 11
    EndIf
    result=Pi3UsbRootPortReset()
    If which=0 And result<>1
    ProcedureReturn 12
    EndIf
    If which=6 And (result<>0 Or p3usb_host_error<>-39)
    ProcedureReturn 13
    EndIf
    If which=8 And (result<>0 Or p3usb_host_error<>-33)
      ProcedureReturn 14
    EndIf
  Else
    If result<>0
    ProcedureReturn 20
    EndIf
    If which=1 And (model_writes<>0 Or p3usb_host_error<>-31)
    ProcedureReturn 21
    EndIf
    If which=2 And p3usb_host_error<>-34
    ProcedureReturn 22
    EndIf
    If which=3 And p3usb_host_error<>-36
    ProcedureReturn 23
    EndIf
    If which=4 And p3usb_host_error<>-35
    ProcedureReturn 24
    EndIf
    If which=5 And p3usb_host_error<>-33
    ProcedureReturn 25
    EndIf
    If which=7 And p3usb_host_error<>-36
    ProcedureReturn 26
    EndIf
  EndIf
  If model_violations<>0
  ProcedureReturn 30
  EndIf
  ProcedureReturn 1
EndProcedure

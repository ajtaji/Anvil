; Monitor-internal control boundary, separate from frame transport/maintenance.
; Bind one synchronous provider at composition startup, while command callers
; are stopped. The provider returns zero on success or its negative driver error.
; An unbound composition refuses explicitly; it never pretends a radio acted.
; Manual event operations record an already-owned synchronous join attempt.
#WIFI_CONTROL_MANUAL_BEGIN=1
#WIFI_CONTROL_MANUAL_FAILED=2
#WIFI_CONTROL_RECOVERED=3
#WIFI_CONTROL_DEAF=4
#WIFI_CONTROL_REKEY=5
#WIFI_CONTROL_UNAVAILABLE=-30001
#WIFI_CONTROL_ARGUMENT=-30002
Global *wifiControlProvider=0

Procedure WifiControlBind(*provider)
  *wifiControlProvider=*provider
EndProcedure

Procedure.i WifiControlAvailable()
  ProcedureReturn Bool(*wifiControlProvider<>0)
EndProcedure

Procedure.i WifiControlCall(operation.i,first.i,second.i)
  If operation<#WIFI_CONTROL_MANUAL_BEGIN Or operation>#WIFI_CONTROL_REKEY : ProcedureReturn #WIFI_CONTROL_ARGUMENT : EndIf
  If operation=#WIFI_CONTROL_MANUAL_BEGIN Or operation=#WIFI_CONTROL_MANUAL_FAILED
    If first<1 Or first>2 : ProcedureReturn #WIFI_CONTROL_ARGUMENT : EndIf
    If operation=#WIFI_CONTROL_MANUAL_FAILED And (second<1 Or second>2) : ProcedureReturn #WIFI_CONTROL_ARGUMENT : EndIf
  EndIf
  If operation=#WIFI_CONTROL_DEAF And (first<1 Or first>600 Or second<0 Or second>1) : ProcedureReturn #WIFI_CONTROL_ARGUMENT : EndIf
  If operation=#WIFI_CONTROL_REKEY And (first<0 Or first>1) : ProcedureReturn #WIFI_CONTROL_ARGUMENT : EndIf
  If *wifiControlProvider=0 : ProcedureReturn #WIFI_CONTROL_UNAVAILABLE : EndIf
  ProcedureReturn wifiControlProvider(operation,first,second)
EndProcedure
